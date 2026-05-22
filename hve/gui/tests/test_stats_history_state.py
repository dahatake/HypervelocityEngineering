"""WorkbenchState.stats_history のテスト（T1）。"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.workbench_state import (  # noqa: E402
    StepStatsSnapshot,
    WorkbenchState,
    WorkflowStatsSnapshot,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def _state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf1", run_id="r1", model="gpt-x")


def test_initial_stats_history_empty(qapp):
    s = _state()
    assert s.stats_history == []


def test_step_done_pushes_snapshot(qapp):
    s = _state()
    s.steps.append(__import__("hve.gui.workbench_state", fromlist=["StepView"]).StepView(id="step1", title="Step 1"))
    s.update_identity(workflow_id="wf1", workflow_name="Workflow A", run_id="r1")
    s.set_step_status("step1", "running")
    s.set_context(1000, 10000, 5)
    s.record_tool_call("step1", "read_file")
    s.record_skill_invoked("step1", "task-questionnaire")
    s.set_step_status("step1", "done")

    assert len(s.stats_history) == 1
    wf = s.stats_history[0]
    assert wf.workflow_id == "wf1"
    assert wf.workflow_name == "Workflow A"
    assert not wf.finalized
    assert len(wf.steps) == 1
    snap = wf.steps[0]
    assert snap.step_id == "step1"
    assert snap.status == "done"
    assert snap.model == "gpt-x"
    assert snap.context_current == 1000
    assert snap.context_limit == 10000
    assert snap.tool_counts == {"read_file": 1}
    assert snap.skill_counts == {"task-questionnaire": 1}
    assert snap.elapsed_sec is not None and snap.elapsed_sec >= 0.0


def test_mark_all_done_finalizes_workflow(qapp):
    s = _state()
    s.update_identity(workflow_id="wf1", workflow_name="A", run_id="r1")
    s.set_step_status("step1", "running")
    s.set_step_status("step1", "done")
    s.set_context(5000, 10000, 10)
    s.mark_all_done()

    assert len(s.stats_history) == 1
    wf = s.stats_history[0]
    assert wf.finalized
    assert wf.finished_at is not None
    assert wf.elapsed_sec is not None and wf.elapsed_sec >= 0.0
    assert wf.context_current == 5000


def test_new_workflow_id_appends_snapshot(qapp):
    """別 workflow_id への遷移で新エントリが追加される。"""
    s = _state()
    s.update_identity(workflow_id="wf1", workflow_name="A", run_id="r1")
    s.set_step_status("s1", "running")
    s.set_step_status("s1", "done")
    s.mark_all_done()

    # 別ワークフローへ
    s.all_done = False  # 次の Workflow を許容
    s.update_identity(workflow_id="wf2", workflow_name="B", run_id="r2")
    s.set_step_status("s2", "running")
    s.set_step_status("s2", "done")

    assert len(s.stats_history) == 2
    assert s.stats_history[0].workflow_id == "wf1"
    assert s.stats_history[0].finalized
    assert s.stats_history[1].workflow_id == "wf2"
    assert not s.stats_history[1].finalized
    assert s.stats_history[1].steps[0].step_id == "s2"


def test_signal_emitted_on_step_snapshot(qapp):
    s = _state()
    received = []
    s.signals().stats_history_updated.connect(lambda: received.append(1))
    s.update_identity(workflow_id="wf1", workflow_name="A", run_id="r1")  # 1
    s.set_step_status("s1", "running")
    s.set_step_status("s1", "done")  # +1
    s.mark_all_done()  # +1
    assert len(received) >= 3


def test_running_status_does_not_push(qapp):
    s = _state()
    s.update_identity(workflow_id="wf1", workflow_name="A", run_id="r1")
    s.set_step_status("s1", "running")
    assert s.stats_history and s.stats_history[0].steps == []


def test_history_store_callback_invoked(qapp):
    calls = []

    class FakeStore:
        def save_step_snapshot(self, wf, step):
            calls.append(("step", wf.workflow_id, step.step_id))

        def save_workflow_snapshot(self, wf):
            calls.append(("workflow", wf.workflow_id, None))

    s = _state()
    s.set_history_store(FakeStore())
    s.update_identity(workflow_id="wf1", workflow_name="A", run_id="r1")
    s.set_step_status("s1", "running")
    s.set_step_status("s1", "done")
    s.mark_all_done()
    assert ("step", "wf1", "s1") in calls
    assert ("workflow", "wf1", None) in calls


def test_history_store_exception_does_not_break(qapp):
    class BadStore:
        def save_step_snapshot(self, wf, step):
            raise RuntimeError("disk full")

        def save_workflow_snapshot(self, wf):
            raise RuntimeError("disk full")

    s = _state()
    s.set_history_store(BadStore())
    s.update_identity(workflow_id="wf1", workflow_name="A", run_id="r1")
    s.set_step_status("s1", "running")
    s.set_step_status("s1", "done")  # should not raise
    s.mark_all_done()
    assert s.stats_history[0].finalized


def test_snapshot_to_dict_serializable(qapp):
    snap = StepStatsSnapshot(
        step_id="s1",
        step_title="Step 1",
        status="done",
        model="gpt-x",
        started_at=1.0,
        finished_at=2.0,
        elapsed_sec=1.0,
        context_current=100,
        context_limit=1000,
        tool_counts={"read_file": 2},
        skill_counts={"sk": 1},
    )
    d = snap.to_dict()
    assert d["step_id"] == "s1"
    assert d["tool_counts"] == {"read_file": 2}

    wf = WorkflowStatsSnapshot(
        workflow_id="wf1",
        workflow_name="A",
        run_id="r1",
        model="gpt-x",
        started_at=0.0,
        steps=[snap],
    )
    wd = wf.to_dict()
    assert wd["workflow_id"] == "wf1"
    assert wd["steps"][0]["step_id"] == "s1"
