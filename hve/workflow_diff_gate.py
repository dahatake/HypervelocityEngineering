"""G-DIFF: Workflow の出力宣言と PR 変更パスを決定的に照合する。

ネットワーク I/O は本モジュールの責務外とする。GitHub API から取得した最小の
``ChangedPath`` 集合を入力にし、registry / fan-out 宣言から構築した閉じた policy
だけで ``PASS`` / ``BLOCKED`` を判定する。
"""

from __future__ import annotations

import re
import importlib.util
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from .catalog_parsers import CatalogParseError
from .fanout_expander import (
    _KEY_ALIAS_PLACEHOLDERS_BY_PARSER,
    expand_workflow_fanout,
    resolve_output_path_prefix_gates,
)
from .workflow_registry import canonicalize_workflow_id, get_workflow, list_workflows

_VALID_STATUSES = frozenset(
    {"added", "removed", "modified", "renamed", "copied", "changed", "unchanged"}
)
_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}|<([^<>]+)>")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:")

# 現行 registry に実在し、単一 path segment としてのみ解決してよい名前。
# fan-out キー別名は既存 SSOT から導出し、ここへ複製しない。
_SINGLE_SEGMENT_PLACEHOLDERS = frozenset(
    {
        "module-name",
        "service",
        "jobId",
        "jobNameSlug",
        "screenNameSlug",
        "serviceNameSlug",
    }
)
_MULTI_SEGMENT_PLACEHOLDERS = frozenset({"relative-path"})
_FANOUT_PLACEHOLDERS = frozenset(
    {"key"}
    | {
        alias
        for aliases in _KEY_ALIAS_PLACEHOLDERS_BY_PARSER.values()
        for alias in aliases
    }
)
_KNOWN_PLACEHOLDERS = (
    _SINGLE_SEGMENT_PLACEHOLDERS
    | _MULTI_SEGMENT_PLACEHOLDERS
    | _FANOUT_PLACEHOLDERS
)
_COMMON_GLOB_PATHS = ("qa/**/*.md",)
_WORKFLOW_MARKER_RE = re.compile(
    r"<!--\s*hve-workflow-id\s*:\s*([^>]*?)\s*-->", re.IGNORECASE
)
_WORKFLOW_MARKER_COMMENT_RE = re.compile(
    r"<!--\s*hve-workflow-id\b", re.IGNORECASE
)
_TITLE_PREFIX_RE = re.compile(r"^\s*\[([^\]\r\n]+)\]")
_STATE_LABEL_SUFFIXES = frozenset(
    {"initialized", "ready", "running", "done", "blocked", "qa-ready", "qa-drafting"}
)


class WorkflowDiffPolicyError(ValueError):
    """Workflow の閉じた許可 policy を構築できない場合。"""


@dataclass(frozen=True)
class ChangedPath:
    """GitHub Pull Request Files API の最小変更パス表現。"""

    path: str
    status: str
    previous_path: str | None = None


@dataclass(frozen=True)
class WorkflowIdentityResult:
    """PR metadata からの Workflow ID 解決結果。"""

    status: str
    workflow_id: str | None = None
    errors: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class WorkflowDiffPolicy:
    """Workflow 1 件の閉じた変更パス許可集合。"""

    workflow_id: str
    exact_paths: tuple[str, ...] = ()
    directory_paths: tuple[str, ...] = ()
    glob_paths: tuple[str, ...] = ()
    prefix_paths: tuple[str, ...] = ()
    constrained_paths: tuple[str, ...] = ()
    provenance: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "exact_paths", tuple(self.exact_paths))
        object.__setattr__(self, "directory_paths", tuple(self.directory_paths))
        object.__setattr__(self, "glob_paths", tuple(self.glob_paths))
        object.__setattr__(self, "prefix_paths", tuple(self.prefix_paths))
        object.__setattr__(self, "constrained_paths", tuple(self.constrained_paths))
        copied = {
            str(key): tuple(str(item) for item in value)
            for key, value in dict(self.provenance).items()
        }
        object.__setattr__(self, "provenance", MappingProxyType(copied))


@dataclass(frozen=True)
class WorkflowDiffResult:
    """G-DIFF の機械可読な判定結果。"""

    status: str
    workflow_id: str | None = None
    checked_paths: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    reason: str = ""
    allowed_by: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_paths", tuple(self.checked_paths))
        object.__setattr__(self, "violations", tuple(self.violations))
        object.__setattr__(self, "errors", tuple(self.errors))
        copied = {
            str(key): tuple(str(item) for item in value)
            for key, value in dict(self.allowed_by).items()
        }
        object.__setattr__(self, "allowed_by", MappingProxyType(copied))


class _FanoutKeyView:
    """既存 prefix resolver へ fan-out key だけを付加する非破壊ビュー。"""

    def __init__(self, step: Any, key: str) -> None:
        self._step = step
        self.fanout_key = key

    def __getattr__(self, name: str) -> Any:
        return getattr(self._step, name)


def _canonical_title_or_label_id(value: str, registered: frozenset[str]) -> str | None:
    canonical = canonicalize_workflow_id(value.strip().lower())
    return canonical if canonical in registered else None


def _workflow_from_title(title: object, registered: frozenset[str]) -> str | None:
    if not isinstance(title, str):
        return None
    match = _TITLE_PREFIX_RE.match(title)
    if match is None:
        return None
    return _canonical_title_or_label_id(match.group(1), registered)


def resolve_managed_workflow_id(
    *,
    pr_body: str | None,
    pr_title: str | None,
    issue_titles: Sequence[str] = (),
    issue_labels: Sequence[str] = (),
) -> WorkflowIdentityResult:
    """PR / linked Issue metadata から canonical Workflow ID を解決する。

    marker は HVE 管理を明示する強い根拠なので、不正値・複数記載を ``N/A`` へ
    退避させない。title / state label は既知 prefix だけを候補にし、通常 PR の
    ``[BUG]`` 等は unmanaged として無視する。複数面の候補が矛盾すれば
    優先順位で握り潰さず ``BLOCKED`` とする。
    """

    if not isinstance(pr_title, str):
        return WorkflowIdentityResult(
            status="BLOCKED",
            errors=("PR title must be a string",),
            reason="invalid pull request metadata",
        )
    if isinstance(issue_titles, (str, bytes)) or not isinstance(issue_titles, Sequence):
        return WorkflowIdentityResult(
            status="BLOCKED",
            errors=("issue_titles must be a sequence of strings",),
            reason="invalid linked issue metadata",
        )
    if isinstance(issue_labels, (str, bytes)) or not isinstance(issue_labels, Sequence):
        return WorkflowIdentityResult(
            status="BLOCKED",
            errors=("issue_labels must be a sequence of strings",),
            reason="invalid linked issue metadata",
        )
    if any(not isinstance(item, str) for item in issue_titles):
        return WorkflowIdentityResult(
            status="BLOCKED",
            errors=("issue_titles contains a non-string value",),
            reason="invalid linked issue metadata",
        )
    if any(not isinstance(item, str) for item in issue_labels):
        return WorkflowIdentityResult(
            status="BLOCKED",
            errors=("issue_labels contains a non-string value",),
            reason="invalid linked issue metadata",
        )

    registered = frozenset(workflow.id for workflow in list_workflows())
    body = pr_body if isinstance(pr_body, str) else ""
    markers = _WORKFLOW_MARKER_RE.findall(body)
    marker_comment_count = len(_WORKFLOW_MARKER_COMMENT_RE.findall(body))
    if marker_comment_count and (marker_comment_count != 1 or len(markers) != 1):
        return WorkflowIdentityResult(
            status="BLOCKED",
            errors=("PR body must contain exactly one valid hve-workflow-id marker",),
            reason="invalid workflow marker cardinality",
        )

    evidence: list[tuple[str, str]] = []
    if markers:
        raw_marker = markers[0].strip().lower()
        # marker は canonical registry ID だけを許可し、legacy alias は title / label
        # fallback に限定する。
        if raw_marker not in registered:
            return WorkflowIdentityResult(
                status="BLOCKED",
                errors=("workflow marker is not a registered canonical workflow ID",),
                reason="workflow marker is not registered",
            )
        evidence.append(("body-marker", raw_marker))

    for index, title in enumerate(issue_titles):
        resolved = _workflow_from_title(title, registered)
        if resolved is not None:
            evidence.append((f"issue-title[{index}]", resolved))

    for index, label in enumerate(issue_labels):
        if not isinstance(label, str) or ":" not in label:
            continue
        prefix, suffix = label.rsplit(":", 1)
        if suffix.lower() not in _STATE_LABEL_SUFFIXES:
            continue
        resolved = _canonical_title_or_label_id(prefix, registered)
        if resolved is not None:
            evidence.append((f"issue-label[{index}]", resolved))

    title_resolved = _workflow_from_title(pr_title, registered)
    if title_resolved is not None:
        evidence.append(("pr-title", title_resolved))

    candidates = {workflow_id for _, workflow_id in evidence}
    if len(candidates) > 1:
        summary = ", ".join(f"{source}={workflow_id}" for source, workflow_id in evidence)
        return WorkflowIdentityResult(
            status="BLOCKED",
            errors=(f"conflicting workflow identity evidence: {summary}",),
            reason="workflow identity evidence conflicts",
        )
    if not candidates:
        return WorkflowIdentityResult(
            status="N/A",
            reason="unmanaged pull request",
        )
    workflow_id = next(iter(candidates))
    return WorkflowIdentityResult(
        status="PASS",
        workflow_id=workflow_id,
        reason="managed workflow identity resolved",
    )


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _safe_error_value(value: object) -> str:
    text = str(value).replace("\x00", "\\0").replace("\r", "\\r").replace("\n", "\\n")
    return text if len(text) <= 240 else text[:237] + "..."


@lru_cache(maxsize=1)
def _load_hve_scope() -> Any:
    """FR-MAINT-07 の機械正本を trusted package 位置から遅延ロードする。"""

    path = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "hve_scope.py"
    if not path.is_file():
        raise WorkflowDiffPolicyError("shared HVE scope module is unavailable")
    spec = importlib.util.spec_from_file_location("_hve_workflow_diff_scope", path)
    if spec is None or spec.loader is None:
        raise WorkflowDiffPolicyError("shared HVE scope module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "is_in_scope", None)):
        raise WorkflowDiffPolicyError("shared HVE scope predicate is unavailable")
    return module


def _normalize_git_path(path: object) -> tuple[str | None, str | None]:
    if not isinstance(path, str):
        return None, "path must be a string"
    if not path:
        return None, "path must not be empty"
    if any(char in path for char in ("\x00", "\r", "\n")):
        return None, "path contains a forbidden control character"
    if "\\" in path:
        return None, "path must use POSIX separators"
    if path.startswith("/") or _WINDOWS_ABSOLUTE_RE.match(path):
        return None, "path must be repository-relative"
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None, "path contains an empty, dot, or parent segment"
    pure = PurePosixPath(path)
    if pure.is_absolute():
        return None, "path must be repository-relative"
    return path, None


def _validate_declared_path(path: object) -> str:
    if not isinstance(path, str) or not path:
        raise WorkflowDiffPolicyError("output path declaration must be a non-empty string")
    if any(char in path for char in ("\x00", "\r", "\n")) or "\\" in path:
        raise WorkflowDiffPolicyError(
            f"unsafe output path declaration: {_safe_error_value(path)}"
        )
    if path.startswith("/") or _WINDOWS_ABSOLUTE_RE.match(path):
        raise WorkflowDiffPolicyError(
            f"absolute output path declaration: {_safe_error_value(path)}"
        )
    candidate = path[:-1] if path.endswith("/") else path
    parts = candidate.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise WorkflowDiffPolicyError(
            f"unsafe output path declaration: {_safe_error_value(path)}"
        )
    return path


def _placeholder_names(path: str) -> tuple[str, ...]:
    return tuple(match.group(1) or match.group(2) for match in _PLACEHOLDER_RE.finditer(path))


def _validate_known_placeholders(path: str) -> tuple[str, ...]:
    names = _placeholder_names(path)
    unknown = sorted(set(names) - _KNOWN_PLACEHOLDERS)
    if unknown:
        raise WorkflowDiffPolicyError(
            "unknown output path placeholder: " + ", ".join(unknown)
        )
    return names


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """`*` は segment 内、`**` だけが segment 境界を越える regex を返す。"""

    chunks: list[str] = ["^"]
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                if index + 2 < len(pattern) and pattern[index + 2] == "/":
                    chunks.append("(?:[^/]+/)*")
                    index += 3
                    continue
                chunks.append(".*")
                index += 2
                continue
            chunks.append("[^/]*")
        elif char == "?":
            chunks.append("[^/]")
        else:
            chunks.append(re.escape(char))
        index += 1
    chunks.append("$")
    return re.compile("".join(chunks))


def _constrained_regex(template: str) -> re.Pattern[str]:
    chunks: list[str] = ["^"]
    cursor = 0
    for match in _PLACEHOLDER_RE.finditer(template):
        chunks.append(re.escape(template[cursor : match.start()]))
        name = match.group(1) or match.group(2)
        if name in _MULTI_SEGMENT_PLACEHOLDERS:
            chunks.append("(?:[^/]+/)*[^/]+")
        elif name in _SINGLE_SEGMENT_PLACEHOLDERS:
            chunks.append("[^/]+")
        else:
            raise WorkflowDiffPolicyError(
                f"fan-out placeholder remained unresolved: {name}"
            )
        cursor = match.end()
    chunks.append(re.escape(template[cursor:]))
    if template.endswith("/"):
        # 変更一覧はファイルだけを含むため、宣言 directory 自身と配下を受理する。
        chunks[-1] = re.escape(template[cursor:-1])
        chunks.append("(?:/.*)?")
    chunks.append("$")
    return re.compile("".join(chunks))


def _rule_key(kind: str, pattern: str) -> str:
    return f"{kind}:{pattern}"


def _add_provenance(
    provenance: dict[str, list[str]], kind: str, pattern: str, source: str
) -> None:
    key = _rule_key(kind, pattern)
    values = provenance.setdefault(key, [])
    if source not in values:
        values.append(source)


def _classify_concrete_path(
    raw_path: object,
    *,
    source: str,
    exact: list[str],
    directories: list[str],
    globs: list[str],
    constrained: list[str],
    provenance: dict[str, list[str]],
) -> None:
    path = _validate_declared_path(raw_path)
    names = _validate_known_placeholders(path)
    if names:
        if any(name in _FANOUT_PLACEHOLDERS for name in names):
            raise WorkflowDiffPolicyError(
                f"unresolved fan-out output path: {_safe_error_value(path)}"
            )
        _append_unique(constrained, path)
        _add_provenance(provenance, "constrained", path, source)
    elif "*" in path or "?" in path:
        _append_unique(globs, path)
        _add_provenance(provenance, "glob", path, source)
    elif path.endswith("/"):
        _append_unique(directories, path)
        _add_provenance(provenance, "directory", path, source)
    else:
        _append_unique(exact, path)
        _add_provenance(provenance, "exact", path, source)


def build_workflow_diff_policy(
    workflow_id: str,
    repo_root: str | Path,
    app_ids: Sequence[str] | None = None,
) -> WorkflowDiffPolicy:
    """registry と subject 側 catalog から Workflow の閉じた policy を構築する。"""

    workflow = get_workflow(workflow_id)
    if workflow is None or workflow.id != workflow_id:
        raise WorkflowDiffPolicyError(f"unknown workflow id: {_safe_error_value(workflow_id)}")
    root = Path(repo_root)
    if not root.is_dir():
        raise WorkflowDiffPolicyError("repository root does not exist or is not a directory")

    exact: list[str] = []
    directories: list[str] = []
    globs: list[str] = []
    prefixes: list[str] = []
    constrained: list[str] = []
    provenance: dict[str, list[str]] = {}

    # 固定出力と、fan-out キーに依存しない optional template を先に収集する。
    base_steps = {step.id: step for step in workflow.steps}
    for step in workflow.steps:
        if getattr(step, "is_container", False):
            continue
        for path in list(getattr(step, "output_paths", None) or []):
            _classify_concrete_path(
                path,
                source=f"{workflow.id}:{step.id}:output_paths",
                exact=exact,
                directories=directories,
                globs=globs,
                constrained=constrained,
                provenance=provenance,
            )

        parser = getattr(step, "fanout_parser", None)
        key_names = {"key"}
        if parser:
            key_names.update(_KEY_ALIAS_PLACEHOLDERS_BY_PARSER.get(parser, ()))
        is_fanout = bool(parser or getattr(step, "fanout_static_keys", None))
        for path in list(getattr(step, "output_paths_template", None) or []):
            declared = _validate_declared_path(path)
            names = _validate_known_placeholders(declared)
            if is_fanout and any(name in key_names for name in names):
                # 具体化と prefix 降格は既存 fan-out 実装へ委譲する。
                continue
            _classify_concrete_path(
                declared,
                source=f"{workflow.id}:{step.id}:output_paths_template",
                exact=exact,
                directories=directories,
                globs=globs,
                constrained=constrained,
                provenance=provenance,
            )

    try:
        expanded = expand_workflow_fanout(
            workflow,
            root,
            app_ids=list(app_ids) if app_ids else None,
        )
    except (CatalogParseError, OSError, ValueError) as exc:
        raise WorkflowDiffPolicyError(
            f"fan-out policy resolution failed: {type(exc).__name__}: {_safe_error_value(exc)}"
        ) from exc

    for child in expanded.steps:
        base_id = str(getattr(child, "base_step_id", "") or "")
        key = str(getattr(child, "fanout_key", "") or "")
        if not base_id or not key:
            continue
        for path in list(getattr(child, "output_paths", None) or []):
            _classify_concrete_path(
                path,
                source=f"{workflow.id}:{base_id}:fanout:{key}",
                exact=exact,
                directories=directories,
                globs=globs,
                constrained=constrained,
                provenance=provenance,
            )
        base = base_steps.get(base_id)
        if base is None:
            raise WorkflowDiffPolicyError(
                f"expanded fan-out references unknown base step: {base_id}"
            )
        for prefix in resolve_output_path_prefix_gates(_FanoutKeyView(base, key)):
            normalized = _validate_declared_path(prefix)
            _append_unique(prefixes, normalized)
            _add_provenance(
                provenance,
                "prefix",
                normalized,
                f"{workflow.id}:{base_id}:prefix:{key}",
            )

    for common in _COMMON_GLOB_PATHS:
        _append_unique(globs, common)
        _add_provenance(provenance, "glob", common, "common:qa-markdown")

    return WorkflowDiffPolicy(
        workflow_id=workflow.id,
        exact_paths=tuple(exact),
        directory_paths=tuple(directories),
        glob_paths=tuple(globs),
        prefix_paths=tuple(prefixes),
        constrained_paths=tuple(constrained),
        provenance={key: tuple(value) for key, value in provenance.items()},
    )


def _match_policy_path(
    policy: WorkflowDiffPolicy, path: str
) -> tuple[str, tuple[str, ...]] | None:
    for pattern in policy.exact_paths:
        if path == pattern:
            key = _rule_key("exact", pattern)
            return key, policy.provenance.get(key, (key,))
    for pattern in policy.directory_paths:
        base = pattern[:-1] if pattern.endswith("/") else pattern
        if path == base or path.startswith(base + "/"):
            key = _rule_key("directory", pattern)
            return key, policy.provenance.get(key, (key,))
    for pattern in policy.glob_paths:
        if _glob_regex(pattern).fullmatch(path):
            key = _rule_key("glob", pattern)
            return key, policy.provenance.get(key, (key,))
    for pattern in policy.prefix_paths:
        if path == pattern or (
            path.startswith(pattern)
            and len(path) > len(pattern)
            and not path[len(pattern)].isalnum()
        ):
            key = _rule_key("prefix", pattern)
            return key, policy.provenance.get(key, (key,))
    for pattern in policy.constrained_paths:
        if _constrained_regex(pattern).fullmatch(path):
            key = _rule_key("constrained", pattern)
            return key, policy.provenance.get(key, (key,))
    return None


def validate_changed_paths(
    policy: WorkflowDiffPolicy,
    changed_paths: Iterable[ChangedPath],
) -> WorkflowDiffResult:
    """変更 path を正規化し、policy 外または入力不正を fail-closed にする。"""

    checked: list[str] = []
    violations: list[str] = []
    errors: list[str] = []
    allowed_by: dict[str, tuple[str, ...]] = {}

    try:
        hve_scope = _load_hve_scope()
    except (ImportError, OSError, WorkflowDiffPolicyError) as exc:
        return WorkflowDiffResult(
            status="BLOCKED",
            workflow_id=policy.workflow_id,
            errors=(
                f"HVE scope resolution failed: {type(exc).__name__}: "
                f"{_safe_error_value(exc)}",
            ),
            reason="shared HVE scope could not be resolved",
        )

    for index, item in enumerate(changed_paths):
        if not isinstance(item, ChangedPath):
            errors.append(f"changed path entry {index} has an invalid type")
            continue
        if item.status not in _VALID_STATUSES:
            errors.append(
                f"changed path entry {index} has unknown status: "
                f"{_safe_error_value(item.status)}"
            )
            continue

        candidates: list[object] = []
        if item.status in {"renamed", "copied"}:
            if not item.previous_path:
                errors.append(
                    f"changed path entry {index} ({item.status}) has no previous path"
                )
                continue
            candidates.append(item.previous_path)
        candidates.append(item.path)

        for candidate in candidates:
            normalized, error = _normalize_git_path(candidate)
            if error or normalized is None:
                errors.append(
                    f"invalid changed path at entry {index}: {error}; "
                    f"value={_safe_error_value(candidate)}"
                )
                continue
            if normalized in checked:
                continue
            checked.append(normalized)
            try:
                if hve_scope.is_in_scope(normalized):
                    violations.append(normalized)
                    continue
            except Exception as exc:
                errors.append(
                    f"HVE scope validation failed for entry {index}: "
                    f"{type(exc).__name__}: {_safe_error_value(exc)}"
                )
                continue
            match = _match_policy_path(policy, normalized)
            if match is None:
                violations.append(normalized)
            else:
                _, sources = match
                allowed_by[normalized] = tuple(sources)

    status = "BLOCKED" if errors or violations else "PASS"
    reason = (
        "policy resolution or changed path validation failed"
        if errors
        else "one or more changed paths are outside the workflow policy"
        if violations
        else "all changed paths are covered by the workflow policy"
    )
    return WorkflowDiffResult(
        status=status,
        workflow_id=policy.workflow_id,
        checked_paths=tuple(checked),
        violations=tuple(violations),
        errors=tuple(errors),
        reason=reason,
        allowed_by=allowed_by,
    )


def validate_workflow_diff(
    workflow_id: str,
    repo_root: str | Path,
    changed_paths: Iterable[ChangedPath],
    app_ids: Sequence[str] | None = None,
) -> WorkflowDiffResult:
    """policy 構築エラーも含めて例外を安全な ``BLOCKED`` へ変換する。"""

    try:
        policy = build_workflow_diff_policy(workflow_id, repo_root, app_ids=app_ids)
    except (WorkflowDiffPolicyError, OSError, ValueError) as exc:
        return WorkflowDiffResult(
            status="BLOCKED",
            workflow_id=workflow_id if isinstance(workflow_id, str) else None,
            errors=(f"policy build failed: {type(exc).__name__}: {_safe_error_value(exc)}",),
            reason="workflow policy could not be resolved",
        )
    return validate_changed_paths(policy, changed_paths)


__all__ = [
    "ChangedPath",
    "WorkflowDiffPolicy",
    "WorkflowDiffPolicyError",
    "WorkflowDiffResult",
    "WorkflowIdentityResult",
    "build_workflow_diff_policy",
    "resolve_managed_workflow_id",
    "validate_changed_paths",
    "validate_workflow_diff",
]