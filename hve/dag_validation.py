"""Validation helpers for hve workflow DAG definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple


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
