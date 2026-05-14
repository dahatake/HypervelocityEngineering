"""動的 retry fork (fork_on_retry) の Workbench Header#2 反映テスト。

Phase 6+: dag_executor の retry 経路 → on_fork_retry_ui → Workbench.mark_retry
までの配線を検証する。
"""
from __future__ import annotations

import asyncio
from typing import Any, List

import pytest

from hve.workbench.state import StepView, WorkbenchState


# ---------- State / Layout レベル ----------

def _mk_state(step_ids: List[str]) -> WorkbenchState:
    return WorkbenchState(
        workflow_id="wf",
        run_id="r",
        model="m",
        steps=[StepView(id=sid, title=f"T{sid}", status="running") for sid in step_ids],
    )


def test_mark_retry_sets_retry_count():
    st = _mk_state(["a", "b"])
    st.mark_retry("a", 1)
    s = next(s for s in st.steps if s.id == "a")
    assert getattr(s, "_retry_count", 0) == 1


def test_mark_retry_zero_clears():
    st = _mk_state(["a"])
    st.mark_retry("a", 1)
    st.mark_retry("a", 0)
    s = st.steps[0]
    assert not hasattr(s, "_retry_count") or getattr(s, "_retry_count", 0) == 0


def test_mark_retry_unknown_step_id_is_noop():
    st = _mk_state(["a"])
    st.mark_retry("missing", 1)  # 例外なし
    assert not hasattr(st.steps[0], "_retry_count")


def test_layout_renders_retry_suffix():
    pytest.importorskip("rich")
    from rich.console import Console
    from hve.workbench.layout import render_header2
    st = WorkbenchState(
        workflow_id="wf", run_id="r", model="m",
        steps=[StepView(id="a", title="Ta", status="pending")],
    )
    st.mark_retry("a", 2)
    rendered = render_header2(st)
    console = Console(width=200, record=True, file=open("nul", "w"))
    console.print(rendered)
    out = console.export_text()
    assert "retry 2" in out


# ---------- DAGExecutor → on_fork_retry_ui 配線 ----------

class _Step:
    def __init__(self, sid: str):
        self.id = sid
        self.title = f"T{sid}"
        self.custom_agent = None
        self.is_container = False
        self.fanout_key = ""
        self.base_step_id = ""


def test_dag_executor_invokes_on_fork_retry_ui_on_retry():
    from hve.dag_executor import DAGExecutor

    ui_calls: List[tuple] = []

    call_count = {"n": 0}

    async def run_step_fn(**kwargs):
        call_count["n"] += 1
        # 初回は失敗、2回目（リトライ）は成功
        return call_count["n"] >= 2

    class _WF:
        steps = [_Step("s1")]

    executor = DAGExecutor(
        workflow=_WF(),
        run_step_fn=run_step_fn,
        active_step_ids={"s1"},
        max_parallel=1,
        enable_fanout=False,
        fork_on_retry=True,
        on_fork_retry_ui=lambda sid, n: ui_calls.append((sid, n)),
    )

    result = asyncio.run(executor._run_with_semaphore(_Step("s1")))
    assert result.success is True
    # retry 開始通知 (n=1) と完了後リセット (n=0) の2回呼ばれる
    assert ui_calls == [("s1", 1), ("s1", 0)]


def test_dag_executor_ui_hook_exception_is_swallowed():
    from hve.dag_executor import DAGExecutor

    call_count = {"n": 0}

    async def run_step_fn(**kwargs):
        call_count["n"] += 1
        return call_count["n"] >= 2

    def _bad_hook(sid, n):
        raise RuntimeError("boom")

    class _WF:
        steps = [_Step("s1")]

    executor = DAGExecutor(
        workflow=_WF(),
        run_step_fn=run_step_fn,
        active_step_ids={"s1"},
        max_parallel=1,
        enable_fanout=False,
        fork_on_retry=True,
        on_fork_retry_ui=_bad_hook,
    )
    # UI フック例外が実行を止めないこと
    result = asyncio.run(executor._run_with_semaphore(_Step("s1")))
    assert result.success is True


def test_dag_executor_no_ui_call_when_fork_off():
    from hve.dag_executor import DAGExecutor

    ui_calls: List[tuple] = []

    async def run_step_fn(**kwargs):
        return False  # 失敗

    class _WF:
        steps = [_Step("s1")]

    executor = DAGExecutor(
        workflow=_WF(),
        run_step_fn=run_step_fn,
        active_step_ids={"s1"},
        max_parallel=1,
        enable_fanout=False,
        fork_on_retry=False,  # off
        on_fork_retry_ui=lambda sid, n: ui_calls.append((sid, n)),
    )
    result = asyncio.run(executor._run_with_semaphore(_Step("s1")))
    assert result.success is False
    # fork_on_retry=False のため UI フックは呼ばれない
    assert ui_calls == []
