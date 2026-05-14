"""Validation helpers for hve workflow DAG definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

try:
    from .orchestrator_context import OrchestratorContext  # type: ignore[import]
except ImportError:  # pragma: no cover - script execution path
    from orchestrator_context import OrchestratorContext  # type: ignore[no-redef]


@dataclass(frozen=True)
class DAGValidationIssue:
    code: str
    severity: str
    message: str
    step_id: Optional[str] = None


@dataclass(frozen=True)
class DAGValidationReport:
    workflow_id: str
    issues: Tuple[DAGValidationIssue, ...] = ()

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    def by_code(self) -> Dict[str, Tuple[DAGValidationIssue, ...]]:
        grouped: Dict[str, list[DAGValidationIssue]] = {}
        for issue in self.issues:
            grouped.setdefault(issue.code, []).append(issue)
        return {code: tuple(items) for code, items in grouped.items()}


def validate_workflow_definition(
    workflow: Any,
    *,
    template_root: str | Path | None = None,
) -> DAGValidationReport:
    """Return warning-only validation for a WorkflowDef-like object.

    The current registry intentionally treats missing dependency ids as resolved,
    so dependency-reference findings are warnings rather than hard errors.
    """
    issues: list[DAGValidationIssue] = []
    steps = list(getattr(workflow, "steps", []) or [])
    workflow_id = getattr(workflow, "id", "unknown")

    seen: set[str] = set()
    duplicate_ids: set[str] = set()
    for step in steps:
        step_id = str(getattr(step, "id", ""))
        if step_id in seen:
            duplicate_ids.add(step_id)
        seen.add(step_id)
    for step_id in sorted(duplicate_ids):
        issues.append(DAGValidationIssue(
            code="duplicate_step_id",
            severity="error",
            step_id=step_id,
            message=f"duplicate step id: {step_id}",
        ))

    existing_ids = {str(getattr(step, "id", "")) for step in steps}
    for step in steps:
        step_id = str(getattr(step, "id", ""))
        for dep in _as_tuple(getattr(step, "depends_on", [])):
            if dep not in existing_ids:
                issues.append(DAGValidationIssue(
                    code="missing_dependency_reference",
                    severity="warning",
                    step_id=step_id,
                    message=f"dependency '{dep}' is not defined; current runtime treats it as resolved",
                ))
        for dep in _as_tuple(getattr(step, "block_unless", [])):
            if dep not in existing_ids:
                issues.append(DAGValidationIssue(
                    code="missing_block_unless_reference",
                    severity="warning",
                    step_id=step_id,
                    message=f"block_unless dependency '{dep}' is not defined",
                ))
        if not getattr(step, "is_container", False) and not getattr(step, "custom_agent", None):
            issues.append(DAGValidationIssue(
                code="missing_custom_agent",
                severity="warning",
                step_id=step_id,
                message="non-container step has no custom_agent",
            ))
        if template_root and getattr(step, "body_template_path", None):
            template_path = Path(template_root) / str(getattr(step, "body_template_path"))
            if not template_path.exists():
                issues.append(DAGValidationIssue(
                    code="missing_template",
                    severity="warning",
                    step_id=step_id,
                    message=f"template not found: {template_path}",
                ))

    issues.extend(_detect_cycles(steps))
    return DAGValidationReport(workflow_id=workflow_id, issues=tuple(issues))


def _detect_cycles(steps: Iterable[Any]) -> Tuple[DAGValidationIssue, ...]:
    adjacency: Dict[str, Tuple[str, ...]] = {}
    existing_ids: set[str] = set()
    for step in steps:
        step_id = str(getattr(step, "id", ""))
        existing_ids.add(step_id)
        adjacency[step_id] = _as_tuple(getattr(step, "depends_on", []))

    visiting: set[str] = set()
    visited: set[str] = set()
    cycle_nodes: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visited:
            return
        if step_id in visiting:
            cycle_nodes.add(step_id)
            return
        visiting.add(step_id)
        for dep in adjacency.get(step_id, ()):
            if dep in existing_ids:
                visit(dep)
        visiting.discard(step_id)
        visited.add(step_id)

    for step_id in sorted(existing_ids):
        visit(step_id)

    return tuple(
        DAGValidationIssue(
            code="cycle_detected",
            severity="error",
            step_id=step_id,
            message=f"cycle detected around step '{step_id}'",
        )
        for step_id in sorted(cycle_nodes)
    )


def _as_tuple(values: Any) -> Tuple[str, ...]:
    if values is None:
        return ()
    return tuple(str(value) for value in values)


# ---------------------------------------------------------------------------
# T-05: SPLIT_REQUIRED 機械検出 (Skill task-dag-planning §2.1.2 準拠)
#
# work/**/plan.md の冒頭 5 行に以下のメタデータが必須:
#   - task_scope: <single|multi>
#   - context_size: <small|medium|large>
# task_scope=multi または context_size=large の場合は実装着手禁止。
# ---------------------------------------------------------------------------

_PLAN_META_HEAD_LINES: int = 5
_PLAN_META_REQUIRED_KEYS: Tuple[str, ...] = ("task_scope", "context_size")


def check_plan_md_metadata(
    plan_path: Path,
    *,
    orchestrator_ctx: Optional[OrchestratorContext] = None,
) -> list[str]:
    """`work/**/plan.md` の冒頭 5 行メタデータを検証する。

    違反メッセージのリストを返す。空リストなら問題なし。

    検査内容:
      1. ファイルが存在し読める
      2. 冒頭 _PLAN_META_HEAD_LINES 行に `task_scope: ` と `context_size: ` を含む
      3. `task_scope: multi` または `context_size: large` を検出した場合
         「SPLIT_REQUIRED — 実装着手禁止」警告を返す

    Args:
        plan_path: plan.md ファイルへのパス（通常 `work/**/plan.md`）
        orchestrator_ctx: Orchestrator 配下で実行されている場合のコンテキスト。
            `None` の場合は単独実行モード（従来通り SPLIT_REQUIRED で停止）。
            非 None の場合は Orchestrator が subissues.md を並列 fork する旨の
            継続可注記を追記する（task_scope=multi / context_size=large 両方が対象）。

    Returns:
        違反メッセージのリスト。空なら全条件 OK。
    """
    issues: list[str] = []
    try:
        text = plan_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        issues.append(f"{plan_path}: ファイルが存在しません")
        return issues
    except OSError as exc:
        issues.append(f"{plan_path}: 読み取りエラー ({type(exc).__name__}: {exc})")
        return issues

    head_lines = text.splitlines()[:_PLAN_META_HEAD_LINES]
    head_text = "\n".join(head_lines)

    # 1) 必須キーが冒頭 5 行に存在するか
    missing = [key for key in _PLAN_META_REQUIRED_KEYS if f"{key}:" not in head_text]
    if missing:
        issues.append(
            f"{plan_path}: 冒頭 {_PLAN_META_HEAD_LINES} 行に必須メタデータが不足しています: "
            f"{', '.join(missing)} (Skill task-dag-planning §2.1.2)"
        )
        return issues

    # 2) 値の抽出（簡易パーサ）— `key: value` のみ対応
    meta: dict[str, str] = {}
    for line in head_lines:
        for key in _PLAN_META_REQUIRED_KEYS:
            prefix = f"{key}:"
            if line.strip().startswith(prefix):
                meta[key] = line.split(":", 1)[1].strip().lower()

    # 3) SPLIT_REQUIRED 判定
    task_scope = meta.get("task_scope", "")
    context_size = meta.get("context_size", "")
    if task_scope == "multi" or context_size == "large":
        triggers = []
        if task_scope == "multi":
            triggers.append("task_scope=multi")
        if context_size == "large":
            triggers.append("context_size=large")
        message = (
            f"{plan_path}: SPLIT_REQUIRED — 実装着手禁止 ({', '.join(triggers)})。"
            " plan.md + subissues.md のみ作成して停止すること (copilot-instructions.md §0)"
        )
        # Orchestrator 配下では subissues.md からサブタスクを並列 fork するため、
        # task_scope=multi / context_size=large どちらでも継続可。
        # 単独実行モード (orchestrator_ctx is None) では従来通り停止。
        if orchestrator_ctx is not None:
            message += (
                " [Orchestrator 配下のため別 Context (Sub-issue / サブセッション) で"
                "実装継続可。本 Agent は plan.md + subissues.md 作成後に正常終了すること]"
            )
        issues.append(message)

    return issues
