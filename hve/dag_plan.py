"""DAG planning data structures for hve workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Tuple


@dataclass(frozen=True)
class DAGPlanNode:
    """Immutable snapshot of one workflow step at planning time."""

    id: str
    title: str
    custom_agent: Optional[str]
    depends_on: Tuple[str, ...] = ()
    body_template_path: Optional[str] = None
    is_container: bool = False
    active: bool = False
    skip_fallback_deps: Tuple[str, ...] = ()
    block_unless: Tuple[str, ...] = ()
    skip_reason: Optional[str] = None


@dataclass(frozen=True)
class DAGEdge:
    """Directed dependency edge in a planned DAG."""

    source: str
    target: str
    missing_source: bool = False


@dataclass(frozen=True)
class DAGWave:
    """One parallel execution wave."""

    index: int
    step_ids: Tuple[str, ...]


@dataclass(frozen=True)
class DAGStepPrompt:
    """Prompt snapshot for one planned step."""

    step_id: str
    prompt: str


@dataclass(frozen=True)
class DAGPlan:
    """Immutable execution plan derived from a WorkflowDef."""

    workflow_id: str
    active_step_ids: Tuple[str, ...]
    nodes: Tuple[DAGPlanNode, ...]
    edges: Tuple[DAGEdge, ...]
    waves: Tuple[DAGWave, ...]
    step_prompts: Tuple[DAGStepPrompt, ...] = ()
    auto_skipped_step_ids: Tuple[str, ...] = ()
    max_parallel: int = 15
    max_parallel_source: str = "config"
    validation: object | None = None
    metadata: Dict[str, str] = field(default_factory=dict)

    def get_node(self, step_id: str) -> Optional[DAGPlanNode]:
        for node in self.nodes:
            if node.id == step_id:
                return node
        return None

    def prompt_for(self, step_id: str) -> str:
        for step_prompt in self.step_prompts:
            if step_prompt.step_id == step_id:
                return step_prompt.prompt
        return ""

    def non_container_nodes(self) -> Tuple[DAGPlanNode, ...]:
        return tuple(node for node in self.nodes if not node.is_container)

    def active_nodes(self) -> Tuple[DAGPlanNode, ...]:
        return tuple(node for node in self.non_container_nodes() if node.active)


def freeze_step_prompts(step_prompts: Optional[Dict[str, str]] = None) -> Tuple[DAGStepPrompt, ...]:
    """Convert a mutable prompt dict into deterministic plan entries."""
    if not step_prompts:
        return ()
    return tuple(
        DAGStepPrompt(step_id=step_id, prompt=step_prompts[step_id])
        for step_id in sorted(step_prompts)
    )


def tuple_from(values: Iterable[str]) -> Tuple[str, ...]:
    return tuple(str(value) for value in values)
