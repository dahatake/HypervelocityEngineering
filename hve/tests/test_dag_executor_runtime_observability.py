"""FR-RTO-05: DAG の終端状態をすべて観測できること。

RED 先行。inactive skip / fan-out empty skip / 未解決 blocked は
`step_status` イベントを発火していない。
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dag_executor import DAGExecutor  # noqa: E402
from dag_planner import build_dag_plan  # noqa: E402


@dataclass
class _StepDef:
    id: str
    title: str
    custom_agent: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    is_container: bool = False
    body_template_path: Optional[str] = None
    skip_fallback_deps: List[str] = field(default_factory=list)
    block_unless: List[str] = field(default_factory=list)


class _WorkflowDef:
    def __init__(self, steps: List[_StepDef]) -> None:
        self.steps = steps
        self._index = {s.id: s for s in steps}

    def get_next_steps(self, completed_step_ids, skipped_step_ids=None):
        completed = set(completed_step_ids)
        skipped = set(skipped_step_ids or [])
        effective_done = completed | skipped
        existing = set(self._index)
        result = []
        for step in self.steps:
            if step.is_container or step.id in effective_done:
                continue
            if not step.depends_on or all(
                dep in effective_done or dep not in existing for dep in step.depends_on
            ):
                result.append(step)
        return result


class _RecordingConsole:
    def __init__(self) -> None:
        self.stats_events: List[tuple] = []

    def stats_event(self, kind: str, step_id: str = "", **fields) -> None:
        self.stats_events.append((kind, step_id, dict(fields)))

    def status(self, msg: str) -> None:
        return None

    def warning(self, msg: str) -> None:
        return None

    def error(self, msg: str) -> None:
        return None

    def event(self, msg: str) -> None:
        return None

    def dag_wave_start(self, *_args, **_kwargs) -> None:
        return None

    def dag_progress(self, *_args, **_kwargs) -> None:
        return None

    def step_elapsed(self, *_args, **_kwargs) -> None:
        return None

    def statuses_for(self, step_id: str) -> List[str]:
        return [
            fields.get("status")
            for kind, sid, fields in self.stats_events
            if kind == "step_status" and sid == step_id
        ]


def _run(coro):
    return asyncio.run(coro)


async def _ok(step_id, title, prompt, custom_agent=None, **_kwargs):
    return True


def test_inactive_step_emits_skipped_status() -> None:
    workflow = _WorkflowDef(
        [
            _StepDef(id="1", title="Step 1"),
            _StepDef(id="2", title="Step 2", depends_on=["1"]),
        ]
    )
    console = _RecordingConsole()
    executor = DAGExecutor(
        workflow=workflow,
        run_step_fn=_ok,
        active_step_ids={"2"},
        console=console,
    )
    _run(executor.execute())

    assert "1" in executor.skipped
    assert "skipped" in console.statuses_for("1")


def test_blocked_step_emits_blocked_status() -> None:
    # Step.1 が失敗すると Step.2 は最後まで実行可能にならず blocked として確定する。
    workflow = _WorkflowDef(
        [
            _StepDef(id="1", title="Step 1"),
            _StepDef(id="2", title="Step 2", depends_on=["1"]),
        ]
    )
    console = _RecordingConsole()

    async def _fail_first(step_id, title, prompt, custom_agent=None, **_kwargs):
        return step_id != "1"

    executor = DAGExecutor(
        workflow=workflow,
        run_step_fn=_fail_first,
        active_step_ids={"1", "2"},
        console=console,
        dag_plan=build_dag_plan(workflow, {"1", "2"}),
    )
    _run(executor.execute())

    assert "2" in executor.blocked
    assert "blocked" in console.statuses_for("2")


def test_fanout_empty_base_emits_skipped_status() -> None:
    workflow = _WorkflowDef([_StepDef(id="3", title="Fanout base")])
    console = _RecordingConsole()
    executor = DAGExecutor(
        workflow=workflow,
        run_step_fn=_ok,
        active_step_ids={"3"},
        console=console,
        enable_fanout=False,
    )
    executor._fanout_empty_ids = ["3"]
    _run(executor.execute())

    assert "3" in executor.skipped
    assert "skipped" in console.statuses_for("3")
