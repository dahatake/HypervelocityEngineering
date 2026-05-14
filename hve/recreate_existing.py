"""recreate-existing 判定と削除計画。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Iterable, List, Mapping, Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from .workflow_registry import StepDef


_RECREATE_BODY_PATTERN = re.compile(
    r"<!--\s*recreate-existing\s*:\s*true\s*-->",
    re.IGNORECASE,
)
_RECREATE_COMMENT_PATTERN = re.compile(
    r"(^|[\s\u3000])@copilot[\s\u3000]+recreate(?:-existing)?(?=$|[\s\u3000,.;:!?)\]」』】>])",
    re.IGNORECASE,
)
_RECREATE_PROMPT_PATTERNS = [
    re.compile(r"(^|[\s\u3000\"'`「『（\[(：:])再作成して(?=$|[\s\u3000\"'`」』）\]),.;:!?])"),
    re.compile(r"(^|[\s\u3000\"'`「『（\[(：:])recreate-existing(?=$|[\s\u3000\"'`」』）\]),.;:!?])", re.IGNORECASE),
    re.compile(r"(^|[\s\u3000\"'`「『（\[(：:])recreate(?=$|[\s\u3000\"'`」』）\]),.;:!?])", re.IGNORECASE),
]
_ALLOWED_COMMENT_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}


@dataclass(frozen=True)
class RecreateExistingDecision:
    enabled: bool = False
    sources: List[str] = field(default_factory=list)


@dataclass
class RecreateExistingPlan:
    step_id: str
    delete_paths: List[str] = field(default_factory=list)
    missing_paths: List[str] = field(default_factory=list)
    skipped_templates: List[str] = field(default_factory=list)


def _append_unique(target: List[str], value: str) -> None:
    if value and value not in target:
        target.append(value)


def prompt_requests_recreate(prompt_text: str) -> bool:
    text = (prompt_text or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in _RECREATE_PROMPT_PATTERNS)


def comment_requests_recreate(
    comment_body: str,
    *,
    author_association: str = "",
    user_type: str = "User",
    user_login: str = "",
) -> bool:
    if (user_type or "").lower() == "bot":
        return False
    if (user_login or "").lower() in {
        "github-actions[bot]",
        "copilot[bot]",
        "copilot-swe-agent[bot]",
    }:
        return False
    if (author_association or "").upper() not in _ALLOWED_COMMENT_ASSOCIATIONS:
        return False
    return bool(_RECREATE_COMMENT_PATTERN.search(comment_body or ""))


def resolve_recreate_existing(
    *,
    issue_body: str = "",
    labels: Optional[Sequence[str]] = None,
    prompt_inputs: Optional[Iterable[str]] = None,
    comments: Optional[Sequence[Mapping[str, str]]] = None,
) -> RecreateExistingDecision:
    sources: List[str] = []

    if _RECREATE_BODY_PATTERN.search(issue_body or ""):
        _append_unique(sources, "body")

    label_names = {str(label).strip() for label in (labels or []) if str(label).strip()}
    if "recreate-existing" in label_names:
        _append_unique(sources, "label")

    for comment in comments or []:
        if comment_requests_recreate(
            comment.get("body", "") or "",
            author_association=comment.get("author_association", "") or "",
            user_type=comment.get("user_type", "User") or "User",
            user_login=comment.get("user_login", "") or "",
        ):
            _append_unique(sources, "comment")
            break

    for prompt_text in prompt_inputs or []:
        if prompt_requests_recreate(prompt_text or ""):
            _append_unique(sources, "prompt")
            break

    return RecreateExistingDecision(enabled=bool(sources), sources=sources)


def _normalize_repo_path(repo_root: Path, raw_path: str) -> tuple[Path, str]:
    normalized = str(raw_path).replace("\\", "/")
    repo_root_resolved = repo_root.resolve()
    candidate = (repo_root / normalized).resolve()
    candidate.relative_to(repo_root_resolved)
    return candidate, normalized


def collect_recreate_existing_plan(step: "StepDef", repo_root: Path) -> RecreateExistingPlan:
    plan = RecreateExistingPlan(step_id=str(getattr(step, "id", "")))
    for raw_path in list(getattr(step, "output_paths", None) or []):
        try:
            abs_path, normalized = _normalize_repo_path(repo_root, str(raw_path))
        except Exception:
            continue
        if abs_path.exists():
            plan.delete_paths.append(normalized)
        else:
            plan.missing_paths.append(normalized)
    for template_path in list(getattr(step, "output_paths_template", None) or []):
        plan.skipped_templates.append(str(template_path).replace("\\", "/"))
    return plan


def apply_recreate_existing_plan(plan: RecreateExistingPlan, repo_root: Path) -> None:
    for raw_path in plan.delete_paths:
        try:
            abs_path, _ = _normalize_repo_path(repo_root, raw_path)
        except Exception:
            continue
        if abs_path.is_file() or abs_path.is_symlink():
            abs_path.unlink(missing_ok=True)


def build_recreate_existing_prompt_section(
    decision: RecreateExistingDecision,
    plan: Optional[RecreateExistingPlan],
) -> str:
    if not decision.enabled or plan is None:
        return ""

    lines = [
        "## recreate-existing モード",
        "- recreate_existing=true",
        f"- source: {', '.join(decision.sources)}",
    ]
    if plan.delete_paths:
        lines.append("- 削除対象として処理した既存ファイル:")
        lines.extend(f"  - `{path}`" for path in plan.delete_paths)
    if plan.skipped_templates:
        lines.append("- dynamic output template は保守的に削除スキップ:")
        lines.extend(f"  - `{path}`" for path in plan.skipped_templates)
    if plan.missing_paths:
        lines.append("- 既存ファイル未検出:")
        lines.extend(f"  - `{path}`" for path in plan.missing_paths)
    return "\n".join(lines)
