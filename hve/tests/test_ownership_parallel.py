"""FR-IDL-02: 所有範囲が重ならない fan-out の子の並列化（N6-2）。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from hve.dag_executor import DAGExecutor, ownership_prefixes
from hve.workflow_registry import get_workflow


@dataclass
class _Step:
    id: str
    title: str = "t"
    custom_agent: str | None = None
    depends_on: List[str] = field(default_factory=list)
    output_paths: List[str] = field(default_factory=list)
    output_paths_template: List[str] | None = None
    fanout_key: str = ""
    base_step_id: str = ""
    is_container: bool = False
    skip_fallback_deps: List[str] = field(default_factory=list)
    block_unless: List[str] = field(default_factory=list)


@dataclass
class _Workflow:
    steps: List[_Step]
    id: str = "wf"
    max_parallel: int = 1
    ownership_parallel: int = 0


def _child(base: str, key: str, *paths: str) -> _Step:
    return _Step(id=f"{base}/{key}", output_paths=list(paths), fanout_key=key, base_step_id=base)


def test_ownership_uses_key_paths_and_ignores_shared_directories() -> None:
    step = _child("4.1", "APP-009-S001", "src/test/ui/", "src/test/ui/APP-009-S001/", "src/test/ui/APP-009-S001/README.md")
    assert ownership_prefixes(step, {}) == ("src/test/ui/APP-009-S001/", "src/test/ui/APP-009-S001/README.md")


def test_ownership_adds_ledger_prefixes() -> None:
    step = _child("3.2", "SVC-01", "src/test/api/SVC-01.Tests/")
    prefixes = ownership_prefixes(step, {"SVC-01": ("src/api/SVC-01-",)})
    assert prefixes == ("src/test/api/SVC-01.Tests/", "src/api/SVC-01-")


def test_shared_file_in_base_template_makes_children_exclusive() -> None:
    child = _child("3.3", "SVC-01")
    templates = ["src/api/{serviceId}-{serviceNameSlug}/", "src/test/api/", "src/test/api/smoke-ui/index.html"]
    assert ownership_prefixes(child, {"SVC-01": ("src/api/SVC-01-",)}, templates) is None
    red = _child("3.2", "SVC-01")
    assert ownership_prefixes(red, {"SVC-01": ("src/api/SVC-01-",)}, ["src/test/api/{serviceId}.Tests/"]) == ("src/api/SVC-01-",)


def test_shared_file_or_non_fanout_step_is_exclusive() -> None:
    shared = _child("4.2", "APP-009-S001", "src/app/", "src/app/package.json", "src/app/APP-009-S001/")
    assert ownership_prefixes(shared, {}) is None
    assert ownership_prefixes(_Step(id="1.1", output_paths=["docs/a.md"]), {}) is None


async def _run(workflow: _Workflow) -> tuple[int, list[tuple[str, str]]]:
    running: set[str] = set()
    peak = 0
    events: list[tuple[str, str]] = []

    async def run_step(step_id: str, **_kwargs) -> bool:
        nonlocal peak
        running.add(step_id)
        peak = max(peak, len(running))
        events.append(("start", step_id))
        await asyncio.sleep(0.02)
        events.append(("end", step_id))
        running.discard(step_id)
        return True

    executor = DAGExecutor(
        workflow,
        run_step,
        active_step_ids={s.id for s in workflow.steps},
        max_parallel=1,
        enable_fanout=False,
        repo_root=Path("."),
    )
    await executor.execute()
    return peak, events


def _disjoint_children(n: int) -> list[_Step]:
    return [_child("3.2", f"SVC-0{i}", f"src/test/api/SVC-0{i}.Tests/") for i in range(1, n + 1)]


def test_disjoint_children_run_in_parallel_up_to_the_cap() -> None:
    peak, _ = asyncio.run(_run(_Workflow(steps=_disjoint_children(6), ownership_parallel=3)))
    assert peak == 3


def test_zero_ownership_parallel_keeps_the_workflow_limit() -> None:
    peak, _ = asyncio.run(_run(_Workflow(steps=_disjoint_children(4), ownership_parallel=0)))
    assert peak == 1


def test_overlapping_children_are_serialized() -> None:
    steps = [
        _child("3.3", "SVC-01", "src/api/SVC-01/"),
        _child("3.3", "SVC-01X", "src/api/SVC-01/extra/"),
    ]
    peak, _ = asyncio.run(_run(_Workflow(steps=steps, ownership_parallel=4)))
    assert peak == 1


def test_exclusive_step_never_overlaps_children() -> None:
    steps = [*_disjoint_children(3), _Step(id="1.1", output_paths=["docs/a.md"])]
    peak, events = asyncio.run(_run(_Workflow(steps=steps, ownership_parallel=4)))
    order = [step for kind, step in events]
    start = order.index("1.1")
    # 1.1 の開始から終了までの間に他の Step の開始・終了が挟まらない
    assert order[start + 1] == "1.1"
    assert peak >= 2


def test_asdw_web_declares_ownership_parallel() -> None:
    workflow = get_workflow("asdw-web")
    assert workflow.max_parallel == 1
    assert workflow.ownership_parallel == 4
