"""Build immutable DAG plans from hve workflow definitions."""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

try:
    from .dag_plan import DAGEdge, DAGPlan, DAGPlanNode, DAGWave, freeze_step_prompts, tuple_from
    from .dag_validation import validate_workflow_definition
except ImportError:
    from dag_plan import DAGEdge, DAGPlan, DAGPlanNode, DAGWave, freeze_step_prompts, tuple_from  # type: ignore[no-redef]
    from dag_validation import validate_workflow_definition  # type: ignore[no-redef]


def build_dag_plan(
    workflow: Any,
    active_step_ids: Set[str],
    *,
    step_prompts: Optional[Dict[str, str]] = None,
    max_parallel: int = 15,
    max_parallel_source: str = "config",
) -> DAGPlan:
    """Create an immutable execution plan for a WorkflowDef-like object."""
    active = set(active_step_ids)
    existing_ids = {step.id for step in workflow.steps}
    waves, auto_skipped = _compute_plan_waves(workflow, active)

    nodes = []
    for step in workflow.steps:
        skip_reason = None
        if step.is_container:
            skip_reason = "container"
        elif step.id in auto_skipped:
            skip_reason = "inactive"
        nodes.append(DAGPlanNode(
            id=step.id,
            title=step.title,
            custom_agent=step.custom_agent,
            depends_on=tuple_from(step.depends_on),
            body_template_path=step.body_template_path,
            is_container=step.is_container,
            active=step.id in active and not step.is_container,
            skip_fallback_deps=tuple_from(step.skip_fallback_deps),
            block_unless=tuple_from(step.block_unless),
            skip_reason=skip_reason,
        ))

    edges = tuple(
        DAGEdge(source=dep, target=step.id, missing_source=dep not in existing_ids)
        for step in workflow.steps
        for dep in step.depends_on
    )

    return DAGPlan(
        workflow_id=getattr(workflow, "id", "unknown"),
        active_step_ids=tuple(sorted(active)),
        nodes=tuple(nodes),
        edges=edges,
        waves=waves,
        step_prompts=freeze_step_prompts(step_prompts),
        auto_skipped_step_ids=tuple(sorted(auto_skipped)),
        max_parallel=max(1, int(max_parallel)),
        max_parallel_source=max_parallel_source,
        validation=validate_workflow_definition(workflow),
    )


def _compute_plan_waves(workflow: Any, active_step_ids: Set[str]) -> tuple[tuple[DAGWave, ...], set[str]]:
    completed: set[str] = set()
    skipped: set[str] = set()
    waves: list[DAGWave] = []

    while True:
        next_steps = workflow.get_next_steps(
            completed_step_ids=list(completed),
            skipped_step_ids=list(skipped),
        )

        newly_skipped = False
        for step in next_steps:
            if step.id not in active_step_ids and step.id not in skipped and step.id not in completed:
                skipped.add(step.id)
                newly_skipped = True

        executable = [
            step for step in next_steps
            if step.id in active_step_ids and step.id not in completed and step.id not in skipped
        ]

        if not executable:
            if newly_skipped:
                continue
            remaining = [
                step for step in next_steps
                if step.id not in completed and step.id not in skipped
            ]
            if not remaining:
                break
            break

        waves.append(DAGWave(index=len(waves) + 1, step_ids=tuple(step.id for step in executable)))
        for step in executable:
            completed.add(step.id)

    return tuple(waves), skipped
