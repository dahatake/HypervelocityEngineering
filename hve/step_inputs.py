"""Run-scoped Step input bundles shared by CLI, GUI, Prompt, and Cloud.

FR-INPUT-01〜06の単一実装。既存のWorkflow/Step/I/O契約を書き換えず、
利用者文書を追加資料または欠損文書入力の代替としてmaterializeする。
"""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

import yaml

if __package__:
    from .workflow_registry import (
        canonicalize_workflow_id,
        expand_group_step_ids,
        get_workflow,
    )
else:  # pragma: no cover - top-level module compatibility
    from workflow_registry import (  # type: ignore[no-redef]
        canonicalize_workflow_id,
        expand_group_step_ids,
        get_workflow,
    )


STEP_INPUT_MCP_CONSENT_PROMPT = "MCP経由で情報を補填しますか?"
_ALLOWED_ROLES = frozenset({"additional", "substitute"})
_GLOB_OR_TEMPLATE = re.compile(r"[*?\[]|\{[^{}]+\}|<[^<>]+>")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_CLOUD_UPLOAD_RE = re.compile(r"^\[([^\]]+)\]\((https://[^)]+)\)$")


class StepInputError(ValueError):
    """Step入力契約に違反した場合に実行前で停止する。"""


@dataclass(frozen=True)
class StepInputSlot:
    workflow_id: str
    step_id: str
    canonical: str
    required: bool
    runtime_required: bool
    kind: str
    producer: Optional[str]
    substitutable: bool


@dataclass(frozen=True)
class StepInputSpec:
    step_id: str
    role: str
    source: Path | str
    canonical: Optional[str] = None


@dataclass(frozen=True)
class StepInputEntry:
    role: str
    canonical: Optional[str]
    actual: str
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "canonical": self.canonical,
            "actual": self.actual,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class StepInputBundle:
    workflow_id: str
    step_id: str
    entries: tuple[StepInputEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "step_id": self.step_id,
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass(frozen=True)
class DocsOriginalCandidate:
    path: str
    score: float = 0.0


@dataclass(frozen=True)
class CandidateResult:
    candidates: tuple[DocsOriginalCandidate, ...]
    source: str
    warning: str = ""


@dataclass(frozen=True)
class CloudStepInputResult:
    supported: bool
    bundles: Mapping[str, StepInputBundle]
    manifest_path: Optional[Path]
    warning: str = ""


CandidateSearcher = Callable[[str, tuple[str, ...], int], Sequence[Mapping[str, Any]]]
CloudDownloader = Callable[[str], bytes | Path]


def _doc_convert_module() -> Any:
    """package/flat importの両方で既存の遅延変換moduleを返す。"""
    if __package__:
        from .gui import doc_convert
    else:  # pragma: no cover - legacy top-level import
        from gui import doc_convert  # type: ignore[no-redef]
    return doc_convert


def _normalize_relative(value: str, *, where: str) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if not text:
        raise StepInputError(f"{where} が空です。")
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise StepInputError(f"{where} は安全なrepository-relative pathではありません: {value}")
    return pure.as_posix()


def _path_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _contract_path(repo_root: Path, workflow_id: str, step: Any) -> Path:
    agent = str(getattr(step, "custom_agent", "") or "").strip()
    if not agent:
        raise StepInputError(
            f"Workflow '{workflow_id}' Step '{step.id}' は実行主体を持ちません。"
        )
    return (
        repo_root
        / ".github"
        / "io-contracts"
        / f"{agent}--{workflow_id}--{step.id}.yaml"
    )


def _is_document_slot(path: str, kind: str) -> bool:
    if kind in {"static", "runtime_param"} or path.endswith("/"):
        return False

    sample = _GLOB_OR_TEMPLATE.sub("sample", path)
    return _doc_convert_module().is_supported(Path(sample))


def _load_non_container_slots(
    repo_root: Path,
    workflow_id: str,
    step: Any,
) -> tuple[StepInputSlot, ...]:
    contract_path = _contract_path(repo_root, workflow_id, step)
    if not contract_path.is_file():
        raise StepInputError(f"Step I/O contract が存在しません: {contract_path}")
    try:
        payload = yaml.safe_load(contract_path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError) as exc:
        raise StepInputError(f"Step I/O contract を読み込めません: {contract_path} ({exc})") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("inputs"), list):
        raise StepInputError(f"Step I/O contract の inputs が配列ではありません: {contract_path}")

    runtime_required = {
        str(path).replace("\\", "/")
        for path in (getattr(step, "required_input_paths", None) or ())
    }
    slots: list[StepInputSlot] = []
    for index, raw in enumerate(payload["inputs"]):
        if not isinstance(raw, Mapping):
            raise StepInputError(f"{contract_path}: inputs[{index}] がobjectではありません。")
        canonical = _normalize_relative(str(raw.get("path") or ""), where=f"inputs[{index}].path")
        required = raw.get("required")
        kind = raw.get("kind")
        if not isinstance(required, bool) or not isinstance(kind, str) or not kind:
            raise StepInputError(f"{contract_path}: inputs[{index}] のrequired/kindが不正です。")
        slots.append(
            StepInputSlot(
                workflow_id=workflow_id,
                step_id=str(step.id),
                canonical=canonical,
                required=required,
                runtime_required=canonical in runtime_required,
                kind=kind,
                producer=(str(raw["producer"]) if raw.get("producer") else None),
                substitutable=_is_document_slot(canonical, kind),
            )
        )
    return tuple(slots)


def load_step_input_slots(
    repo_root: Path | str,
    workflow_id: str,
    step_id: str,
) -> tuple[StepInputSlot, ...]:
    """Step別I/O契約を読み、containerでは子Stepのslotを集約する。"""
    root = Path(repo_root)
    canonical_workflow = canonicalize_workflow_id(workflow_id)
    workflow = get_workflow(canonical_workflow)
    if workflow is None:
        raise StepInputError(f"未知のWorkflowです: {workflow_id}")
    step = workflow.get_step(str(step_id))
    if step is None:
        raise StepInputError(
            f"Workflow '{canonical_workflow}' にStep '{step_id}' が存在しません。"
        )
    if not step.is_container:
        return _load_non_container_slots(root, canonical_workflow, step)

    prefix = f"{step.id}."
    children = [
        child for child in workflow.steps
        if not child.is_container and str(child.id).startswith(prefix)
    ]
    slots: list[StepInputSlot] = []
    for child in children:
        slots.extend(_load_non_container_slots(root, canonical_workflow, child))
    return tuple(slots)


def resolve_step_input_step_ids(
    workflow_id: str,
    selected_step_ids: Sequence[str] = (),
) -> tuple[str, ...]:
    """選択されたgroup/containerを、入力を所有する実行Step列へ展開する。"""
    canonical_workflow = canonicalize_workflow_id(workflow_id)
    workflow = get_workflow(canonical_workflow)
    if workflow is None:
        raise StepInputError(f"未知のWorkflowです: {workflow_id}")
    requested = (
        expand_group_step_ids(canonical_workflow, list(selected_step_ids))
        if selected_step_ids
        else [step.id for step in workflow.steps if not step.is_container]
    )
    resolved: list[str] = []
    for step_id in requested:
        step = workflow.get_step(str(step_id))
        if step is None:
            raise StepInputError(
                f"Workflow '{canonical_workflow}' にStep '{step_id}' が存在しません。"
            )
        if not step.is_container:
            resolved.append(step.id)
            continue
        prefix = f"{step.id}."
        children = [
            child.id
            for child in workflow.steps
            if not child.is_container and child.id.startswith(prefix)
        ]
        if not children:
            raise StepInputError(
                f"Workflow '{canonical_workflow}' container Step '{step.id}' に実行Stepがありません。"
            )
        resolved.extend(children)
    return tuple(dict.fromkeys(resolved))


def _slot_has_existing_file(repo_root: Path, canonical: str) -> bool:
    return bool(existing_step_input_files(repo_root, canonical))


def existing_step_input_files(
    repo_root: Path | str,
    canonical: str,
) -> tuple[str, ...]:
    """canonical入力に一致する実在ファイル名を決定的な順序で返す。"""
    root = Path(repo_root)
    pattern = _GLOB_OR_TEMPLATE.sub("*", canonical)
    if pattern != canonical:
        try:
            return tuple(
                sorted(
                    path.name
                    for path in root.glob(pattern)
                    if path.is_file()
                )
            )
        except (OSError, ValueError):
            return ()
    path = root / canonical
    return (path.name,) if path.is_file() else ()


def _resolve_source(repo_root: Path, source: Path | str) -> Path:
    raw = Path(source).expanduser()
    candidate = raw if raw.is_absolute() else repo_root / raw
    if candidate.is_symlink():
        raise StepInputError(f"Step入力sourceにsymlinkは指定できません: {source}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise StepInputError(f"Step入力sourceが存在しません: {source}") from exc
    if not resolved.is_file():
        raise StepInputError(f"Step入力sourceは通常ファイルでなければなりません: {source}")
    if not _doc_convert_module().is_supported(resolved):
        raise StepInputError(f"Step入力sourceは対応文書形式ではありません: {resolved.suffix}")
    return resolved


def _validate_target_root(repo_root: Path, target_root: Path) -> Path:
    root = repo_root.resolve()
    target = target_root if target_root.is_absolute() else root / target_root
    try:
        target.resolve().relative_to(root)
    except (OSError, ValueError) as exc:
        raise StepInputError("Step入力のmaterialize先はrepository配下でなければなりません。") from exc
    target.mkdir(parents=True, exist_ok=True)
    return target


def _materialize_one(source: Path, target: Path) -> None:
    if target.exists():
        if not target.is_file():
            raise StepInputError(f"Step入力の出力先が通常ファイルではありません: {target}")
        target.unlink()
    if source.suffix.lower() in {".md", ".markdown"}:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        return

    doc_convert = _doc_convert_module()
    result = doc_convert.convert_file(source, out_dir=target.parent, out_name=target.name)
    if not result.ok or result.converted_path is None:
        raise StepInputError(result.error or f"文書変換に失敗しました: {source}")
    if result.converted_path.resolve() != target.resolve() or not target.is_file():
        raise StepInputError(f"文書変換結果が期待した出力先にありません: {target}")


def _safe_step_dir(step_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", step_id).strip("._") or "step"


def materialize_step_inputs(
    *,
    repo_root: Path | str,
    work_root: Path | str,
    workflow_id: str,
    specs: Sequence[StepInputSpec],
    input_aliases: Sequence[Sequence[str]] = (),
) -> tuple[dict[str, StepInputBundle], Path]:
    """利用者文書をMarkdown化し、Step別bundleとmanifestを作る。"""
    root = Path(repo_root).resolve()
    canonical_workflow = canonicalize_workflow_id(workflow_id)
    workflow = get_workflow(canonical_workflow)
    if workflow is None:
        raise StepInputError(f"未知のWorkflowです: {workflow_id}")
    target_root = _validate_target_root(root, Path(work_root))

    entries_by_step: dict[str, list[StepInputEntry]] = {}
    order_by_step: dict[str, int] = {}
    for raw_spec in specs:
        step_id = str(raw_spec.step_id or "").strip()
        step = workflow.get_step(step_id)
        if step is None or step.is_container:
            raise StepInputError(
                f"Workflow '{canonical_workflow}' の実行Stepではありません: {step_id}"
            )
        role = str(raw_spec.role or "").strip().lower()
        if role not in _ALLOWED_ROLES:
            raise StepInputError(f"未知のStep入力roleです: {raw_spec.role}")
        canonical = None
        if raw_spec.canonical not in (None, "", "-"):
            canonical = _normalize_relative(str(raw_spec.canonical), where="canonical")
        if role == "substitute":
            if not canonical:
                raise StepInputError("substituteにはcanonicalが必要です。")
            slot = next(
                (
                    item for item in load_step_input_slots(root, canonical_workflow, step_id)
                    if item.canonical == canonical
                ),
                None,
            )
            if slot is None or not slot.substitutable:
                raise StepInputError(f"代替可能な文書入力ではありません: {canonical}")
            if _slot_has_existing_file(root, canonical):
                raise StepInputError(f"canonical入力が既に存在するため代替できません: {canonical}")

        source = _resolve_source(root, raw_spec.source)
        ordinal = order_by_step.get(step_id, 0) + 1
        order_by_step[step_id] = ordinal
        filename = f"{ordinal:03d}-{_doc_convert_module().safe_filename(source.name)}"
        target = (
            target_root
            / "step-inputs"
            / canonical_workflow
            / _safe_step_dir(step_id)
            / filename
        )
        _materialize_one(source, target)
        relative = target.resolve().relative_to(root).as_posix()
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        entries_by_step.setdefault(step_id, []).append(
            StepInputEntry(
                role=role,
                canonical=canonical,
                actual=relative,
                sha256=digest,
            )
        )

    bundles = {
        step_id: StepInputBundle(
            workflow_id=canonical_workflow,
            step_id=step_id,
            entries=tuple(entries),
        )
        for step_id, entries in entries_by_step.items()
    }
    validate_step_input_bundles(
        bundles,
        repo_root=root,
        input_aliases=input_aliases,
    )
    manifest = target_root / "step-inputs" / canonical_workflow / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    if manifest.exists():
        if not manifest.is_file():
            raise StepInputError(f"manifest出力先が通常ファイルではありません: {manifest}")
        manifest.unlink()
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "workflow_id": canonical_workflow,
                "bundles": [bundle.to_dict() for bundle in bundles.values()],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    return bundles, manifest


def validate_step_input_bundles(
    bundles: Mapping[str, StepInputBundle],
    *,
    repo_root: Path | str,
    input_aliases: Sequence[Sequence[str]] = (),
) -> None:
    """bundle path/digest/roleとlegacy input_alias競合をfail-closed検証する。"""
    root = Path(repo_root).resolve()
    alias_canonicals = {
        str(pair[0]).replace("\\", "/")
        for pair in input_aliases
        if isinstance(pair, Sequence) and not isinstance(pair, (str, bytes)) and len(pair) == 2
    }
    for key, bundle in bundles.items():
        if key != bundle.step_id:
            raise StepInputError("Step入力bundleのmap keyとstep_idが一致しません。")
        workflow = get_workflow(bundle.workflow_id)
        step = workflow.get_step(bundle.step_id) if workflow else None
        if step is None or step.is_container:
            raise StepInputError(f"Step入力bundleが未知の実行Stepを参照しています: {bundle.step_id}")
        for entry in bundle.entries:
            if entry.role not in _ALLOWED_ROLES:
                raise StepInputError(f"Step入力bundleのroleが不正です: {entry.role}")
            if entry.role == "substitute" and not entry.canonical:
                raise StepInputError("substitute entryにcanonicalがありません。")
            if entry.canonical and entry.canonical in alias_canonicals:
                raise StepInputError(
                    f"Step入力canonicalがlegacy input_aliasと競合します: {entry.canonical}"
                )
            actual = _normalize_relative(entry.actual, where="actual")
            target = root / actual
            if target.is_symlink() or not target.is_file() or not _path_inside(target, root):
                raise StepInputError(f"Step入力actualが安全な通常ファイルではありません: {actual}")
            if not _SHA256_RE.fullmatch(entry.sha256):
                raise StepInputError(f"Step入力SHA-256の形式が不正です: {entry.sha256}")
            actual_digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual_digest != entry.sha256:
                raise StepInputError(f"Step入力SHA-256が一致しません: {actual}")


def bundle_for_step(
    bundles: Mapping[str, StepInputBundle] | None,
    step_id: str,
) -> Optional[StepInputBundle]:
    if not bundles:
        return None
    if step_id in bundles:
        return bundles[step_id]
    base_id = str(step_id).split("/", 1)[0]
    return bundles.get(base_id)


def build_step_input_addendum(
    bundle: StepInputBundle,
    *,
    manifest_path: Path | str,
    repo_root: Path | str,
) -> str:
    """本文を埋め込まず、Agentが読むmaterialized pathだけを示す。"""
    validate_step_input_bundles({bundle.step_id: bundle}, repo_root=repo_root)
    root = Path(repo_root).resolve()
    manifest = Path(manifest_path)
    if not manifest.is_absolute():
        manifest = root / manifest
    try:
        manifest_rel = manifest.resolve().relative_to(root).as_posix()
    except (OSError, ValueError) as exc:
        raise StepInputError("Step入力manifestがrepository外です。") from exc
    lines = [
        "## 利用者指定のStep入力",
        f"- Manifest: `{manifest_rel}`",
        "- 次のmaterialized Markdownを指定順に参照してください。本文を推測で統合しないでください。",
    ]
    for entry in bundle.entries:
        canonical = f" / canonical=`{entry.canonical}`" if entry.canonical else ""
        lines.append(
            f"- role=`{entry.role}`{canonical} / actual=`{entry.actual}` / sha256=`{entry.sha256}`"
        )
    return "\n".join(lines)


def should_offer_step_input_mcp(
    *,
    has_step_inputs: bool,
    question_count: int,
    adapter_ready: bool,
    consent: Optional[bool],
) -> bool:
    return bool(
        has_step_inputs
        and question_count > 0
        and adapter_ready
        and consent is None
    )


def _default_mdq_search(
    repo_root: Path,
    query: str,
    paths: tuple[str, ...],
    limit: int,
) -> Sequence[Mapping[str, Any]]:
    from mdq import freshness, search, store

    databases = store.existing_index_dbs(repo_root)
    preferred = next(
        (path for lang, strategy, path in databases if lang == "ja-jp" and strategy == "heading"),
        None,
    )
    db_path = preferred or (repo_root / store.DEFAULT_DB_PATH)
    if not db_path.is_file():
        raise StepInputError("mdq index が存在しません。")
    with closing(store.open_store(db_path, lang="ja-jp")) as conn:
        report = freshness.check(repo_root, conn)
        if not report.is_fresh:
            raise StepInputError(
                f"mdq index is stale ({len(report.changed)} changed files)"
            )
        return [
            hit.to_dict()
            for hit in search.search(
                conn,
                query,
                top_k=limit,
                max_tokens=max(800, limit * 200),
                path_globs=list(paths),
            )
        ]


def _candidate_rank(query: str, path: str, score: float) -> tuple[int, float, str]:
    name = PurePosixPath(path).name.casefold()
    stem = PurePosixPath(path).stem.casefold()
    needle = query.strip().casefold()
    if needle and needle == stem:
        filename_rank = 0
    elif needle and needle in name:
        filename_rank = 1
    else:
        filename_rank = 2
    return filename_rank, -score, path


def find_docs_original_candidates(
    repo_root: Path | str,
    query: str,
    *,
    limit: int = 10,
    searcher: Optional[CandidateSearcher] = None,
) -> CandidateResult:
    """既存mdqを優先し、失敗時だけ実在path順へ縮退する。"""
    root = Path(repo_root).resolve()
    limit = max(0, min(int(limit), 10))
    if limit == 0:
        return CandidateResult((), "mdq")
    try:
        raw_hits = (
            searcher(query, ("docs-original/**",), limit)
            if searcher is not None
            else _default_mdq_search(root, query, ("docs-original/**",), limit)
        )
        found: dict[str, DocsOriginalCandidate] = {}
        for raw in raw_hits:
            raw_path = str(raw.get("path") or "").replace("\\", "/")
            try:
                path = _normalize_relative(raw_path, where="mdq candidate path")
            except StepInputError:
                continue
            target = root / path
            if not path.startswith("docs-original/") or not target.is_file() or not _path_inside(target, root):
                continue
            score = float(raw.get("score") or 0.0)
            found.setdefault(path, DocsOriginalCandidate(path, score))
        ordered = sorted(
            found.values(),
            key=lambda item: _candidate_rank(query, item.path, item.score),
        )[:limit]
        return CandidateResult(tuple(ordered), "mdq")
    # FR-INPUT-03は、索引欠損/staleだけでなくbackend/schemaを含む検索失敗全般を
    # 明示してfilesystemへ縮退する。候補生成は補助機構なのでfail-openを意図する。
    except Exception as exc:  # noqa: BLE001
        is_supported = _doc_convert_module().is_supported
        base = root / "docs-original"
        files = []
        if base.is_dir():
            files = sorted(
                path for path in base.rglob("*")
                if path.is_file() and not path.is_symlink() and is_supported(path)
            )
        candidates = tuple(
            DocsOriginalCandidate(path.resolve().relative_to(root).as_posix())
            for path in files[:limit]
        )
        return CandidateResult(
            candidates,
            "filesystem-fallback",
            f"mdq search unavailable ({exc}); filesystem fallback was used.",
        )


def _parse_cloud_file_lines(files_text: str) -> list[tuple[str, Optional[str]]]:
    files: list[tuple[str, Optional[str]]] = []
    for line in str(files_text or "").splitlines():
        text = line.strip()
        if not text or text == "_No response_":
            continue
        match = _CLOUD_UPLOAD_RE.fullmatch(text)
        if match:
            files.append((match.group(1), match.group(2)))
        else:
            files.append((text, None))
    return files


def _parse_cloud_bindings(bindings_text: str, file_count: int) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    for line_number, line in enumerate(str(bindings_text or "").splitlines(), start=1):
        text = line.strip()
        if not text or text == "_No response_":
            continue
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StepInputError(f"Step Input Bindings {line_number}行目がJSONではありません。") from exc
        if not isinstance(raw, dict):
            raise StepInputError(f"Step Input Bindings {line_number}行目はobjectでなければなりません。")
        unknown = sorted(set(raw) - {"step_id", "role", "file", "canonical"})
        if unknown:
            raise StepInputError(f"Step Input Bindingsに未知fieldがあります: {unknown[0]}")
        index = raw.get("file")
        if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= file_count:
            raise StepInputError(f"Step Input Bindingsのfile番号が範囲外です: {index}")
        bindings.append(raw)
    if file_count and not bindings:
        raise StepInputError("Step Input Filesが指定されていますがBindingsがありません。")
    return bindings


def materialize_cloud_step_inputs(
    *,
    repo_root: Path | str,
    work_root: Path | str,
    workflow_id: str,
    files_text: str,
    bindings_text: str,
    downloader: Optional[CloudDownloader] = None,
) -> CloudStepInputResult:
    """Cloud Issue Form textareaを同じmaterializerへ変換する。"""
    root = Path(repo_root).resolve()
    file_specs = _parse_cloud_file_lines(files_text)
    bindings = _parse_cloud_bindings(bindings_text, len(file_specs))
    if not bindings:
        return CloudStepInputResult(True, {}, None)

    downloaded: dict[int, Path] = {}
    for index, (name_or_path, url) in enumerate(file_specs, start=1):
        if url is None:
            relative = _normalize_relative(name_or_path, where="Cloud branch-relative input")
            source = _resolve_source(root, relative)
            if not _path_inside(source, root):
                raise StepInputError(
                    "Cloud branch-relative inputはrepository配下でなければなりません。"
                )
            downloaded[index] = source
            continue
        if downloader is None:
            return CloudStepInputResult(
                False,
                {},
                None,
                "Cloud upload unavailable; use an existing branch-relative path instead.",
            )
        raw = downloader(url)
        download_dir = _validate_target_root(root, Path(work_root)) / "cloud-downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name_or_path).name) or f"upload-{index}"
        target = download_dir / f"{index:03d}-{safe_name}"
        if target.exists():
            target.unlink()
        if isinstance(raw, bytes):
            target.write_bytes(raw)
        elif isinstance(raw, Path):
            source = raw
            if source.is_symlink() or not source.is_file():
                raise StepInputError(
                    "Cloud downloaderが安全な通常ファイルを返しませんでした。"
                )
            target.write_bytes(source.read_bytes())
        else:
            raise StepInputError("Cloud downloaderの戻り値型が不正です。")
        downloaded[index] = target

    specs = tuple(
        StepInputSpec(
            step_id=str(binding.get("step_id") or ""),
            role=str(binding.get("role") or ""),
            source=downloaded[int(binding["file"])],
            canonical=(
                str(binding["canonical"])
                if binding.get("canonical") not in (None, "", "-")
                else None
            ),
        )
        for binding in bindings
    )
    bundles, manifest = materialize_step_inputs(
        repo_root=root,
        work_root=work_root,
        workflow_id=workflow_id,
        specs=specs,
    )
    return CloudStepInputResult(True, bundles, manifest)


def extract_issue_form_value(body: str, label: str) -> str:
    """GitHub Issue Formが生成したlevel-3 sectionの値を取り出す。"""
    pattern = re.compile(
        rf"(?ms)^###\s+{re.escape(label)}\s*$\n(.*?)(?=^###\s+|\Z)"
    )
    match = pattern.search(str(body or "").replace("\r\n", "\n"))
    if not match:
        return ""
    value = match.group(1).strip()
    if value.startswith("```") and value.endswith("```"):
        lines = value.splitlines()
        value = "\n".join(lines[1:-1]).strip()
    return "" if value == "_No response_" else value


def build_cloud_step_input_section(body: str, workflow_id: str) -> str:
    """Issue Formの入力がある場合だけ、Cloud Agent向け固定セクションを返す。"""
    files = extract_issue_form_value(body, "Step Input Files")
    bindings = extract_issue_form_value(body, "Step Input Bindings")
    if not files and not bindings:
        return ""
    if __package__:
        from .prompt_loader import load_prompt_file
    else:  # pragma: no cover - legacy top-level import
        from prompt_loader import load_prompt_file  # type: ignore[no-redef]

    template = load_prompt_file("cloud/step-inputs.prompt.md")
    return template.format_map(
        {
            "workflow_id": canonicalize_workflow_id(workflow_id),
            "step_input_files": files or "_No response_",
            "step_input_bindings": bindings or "_No response_",
        }
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m hve.step_inputs")
    sub = parser.add_subparsers(dest="command", required=True)
    cloud = sub.add_parser("cloud-manifest")
    cloud.add_argument("--repo-root", default=".")
    cloud.add_argument("--work-root", required=True)
    cloud.add_argument("--workflow", required=True)
    cloud.add_argument("--issue-body-file", required=True)
    section = sub.add_parser("cloud-section")
    section.add_argument("--workflow", required=True)
    section.add_argument("--issue-body-file", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    body = Path(args.issue_body_file).read_text(encoding="utf-8")
    if args.command == "cloud-section":
        section = build_cloud_step_input_section(body, args.workflow)
        if section:
            print(section)
        return 0
    if args.command != "cloud-manifest":
        return 2
    result = materialize_cloud_step_inputs(
        repo_root=args.repo_root,
        work_root=args.work_root,
        workflow_id=args.workflow,
        files_text=extract_issue_form_value(body, "Step Input Files"),
        bindings_text=extract_issue_form_value(body, "Step Input Bindings"),
        downloader=None,
    )
    print(
        json.dumps(
            {
                "supported": result.supported,
                "manifest_path": (
                    str(result.manifest_path) if result.manifest_path is not None else None
                ),
                "warning": result.warning,
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.supported else 3


if __name__ == "__main__":
    raise SystemExit(main())
