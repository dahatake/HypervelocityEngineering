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
    s.record_step_context("step1", 1000, 10000)
    s.record_step_model("step1", "gpt-x")
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


# ----------------------------------------------------------------------
# FR-RTO-07: Step 単位の統計分離
# ----------------------------------------------------------------------


def _running(s: WorkbenchState, step_id: str) -> None:
    s.update_identity(workflow_id="wf1", workflow_name="A", run_id="r1")
    s.set_step_status(step_id, "running")


def test_step_snapshot_uses_per_step_context(qapp):
    """Step の Context は当該 Step 帰属イベントの値で、他 Step の値に汚染されない。"""
    s = _state()
    _running(s, "s1")
    s.record_step_context("s1", 1000, 10000)
    s.set_step_status("s1", "done")

    s.set_step_status("s2", "running")
    s.record_step_context("s2", 7000, 10000)
    s.set_step_status("s2", "done")

    steps = {st.step_id: st for st in s.stats_history[0].steps}
    assert steps["s1"].context_current == 1000
    assert steps["s2"].context_current == 7000


def test_step_snapshot_context_ignores_global_current_value(qapp):
    """グローバル現在値 (`set_context`) を Step の Context へ代用してはならない。"""
    s = _state()
    _running(s, "s1")
    s.set_context(9999, 10000, 3)  # Footer 用グローバル値のみ
    s.set_step_status("s1", "done")

    snap = s.stats_history[0].steps[0]
    assert snap.context_current is None
    assert snap.context_limit is None


def test_step_snapshot_uses_per_step_credit(qapp):
    """Step の AI Credit は当該 Step 帰属の usage_credit 合計であり Workflow 累積ではない。"""
    s = _state()
    _running(s, "s1")
    s.apply_assistant_credit(api_call_id="a1", nano_aiu=1_000_000_000, step_id="s1")
    s.set_step_status("s1", "done")

    s.set_step_status("s2", "running")
    s.apply_assistant_credit(api_call_id="a2", nano_aiu=3_000_000_000, step_id="s2")
    s.set_step_status("s2", "done")

    steps = {st.step_id: st for st in s.stats_history[0].steps}
    assert steps["s1"].aiu_nano_own == 1_000_000_000
    assert steps["s2"].aiu_nano_own == 3_000_000_000
    # Workflow 累積は両方の合計。
    assert s.sdk_aiu_total_nano == 4_000_000_000


def test_step_credit_dedupes_by_api_call_id(qapp):
    """同一 api_call_id の再送は Step 別集計でも二重計上しない。"""
    s = _state()
    _running(s, "s1")
    s.apply_assistant_credit(api_call_id="a1", nano_aiu=1_000_000_000, step_id="s1")
    s.apply_assistant_credit(api_call_id="a1", nano_aiu=1_000_000_000, step_id="s1")
    s.set_step_status("s1", "done")

    assert s.stats_history[0].steps[0].aiu_nano_own == 1_000_000_000
    assert s.sdk_aiu_total_nano == 1_000_000_000


def test_step_snapshot_records_per_step_model_counts(qapp):
    """Step スナップショットはモデル別呼び出し回数を保持する。"""
    s = _state()
    _running(s, "s1")
    s.record_step_model("s1", "claude-opus-5")
    s.record_step_model("s1", "claude-opus-5")
    s.record_step_model("s1", "gpt-5.6-terra")
    s.set_step_status("s1", "done")

    snap = s.stats_history[0].steps[0]
    assert snap.model_counts == {"claude-opus-5": 2, "gpt-5.6-terra": 1}
    # 単一値の `model` は最多モデル。
    assert snap.model == "claude-opus-5"


def test_step_snapshot_is_none_when_no_step_event(qapp):
    """Step 帰属イベントが 0 件なら Context / AI Credit / モデルは未取得のまま。"""
    s = _state()
    _running(s, "fleet-step")
    # 他 Step の消費やグローバル値が存在しても代替してはならない。
    s.set_context(5000, 10000, 4)
    s.apply_assistant_credit(api_call_id="x1", nano_aiu=5_000_000_000, step_id=None)
    s.set_model("claude-opus-5")
    s.set_step_status("fleet-step", "done")

    snap = s.stats_history[0].steps[0]
    assert snap.context_current is None
    assert snap.context_limit is None
    assert snap.aiu_nano_own is None
    assert snap.model_counts == {}
    assert snap.model == ""


def test_workflow_credit_keeps_unattributed_total(qapp):
    """Step へ帰属できない消費も Workflow 累積へ計上する（Fleet wave 相当）。"""
    s = _state()
    _running(s, "s1")
    s.apply_assistant_credit(api_call_id="a1", nano_aiu=1_000_000_000, step_id="s1")
    s.set_step_status("s1", "done")
    # Fleet 経路: step 帰属なしで累積のみ加算。
    s.apply_assistant_credit(api_call_id="f1", nano_aiu=2_000_000_000, step_id="")
    s.set_step_status("s2", "running")
    s.set_step_status("s2", "done")
    s.mark_all_done()

    wf = s.stats_history[0]
    assert wf.sdk_aiu_total_nano == 3_000_000_000
    steps = {st.step_id: st for st in wf.steps}
    assert steps["s1"].aiu_nano_own == 1_000_000_000
    assert steps["s2"].aiu_nano_own is None
    assert s.aiu_nano_by_step.get("") is None


def test_placeholder_run_id_snapshot_is_updated_in_place(qapp):
    """run_id 未確定で開始した実行は、確定後も 1 件のスナップショットに留まる。"""
    s = WorkbenchState(workflow_id="unknown", run_id="unknown", model="unknown")
    s.update_identity(workflow_id="aas", workflow_name="AAS")
    assert len(s.stats_history) == 1

    s.update_identity(run_id="20260813T135234-8427a6")

    assert len(s.stats_history) == 1
    wf = s.stats_history[0]
    assert wf.run_id == "20260813T135234-8427a6"
    assert not wf.finalized


def test_real_run_id_change_still_appends_snapshot(qapp):
    """プレースホルダでない run_id の変更は従来どおり別実行として追加する。"""
    s = _state()
    s.update_identity(workflow_id="wf1", workflow_name="A", run_id="r1")
    s.set_step_status("s1", "running")
    s.set_step_status("s1", "done")

    s.update_identity(run_id="r2")

    assert len(s.stats_history) == 2
    assert s.stats_history[0].run_id == "r1"
    assert s.stats_history[0].finalized
    assert s.stats_history[1].run_id == "r2"
