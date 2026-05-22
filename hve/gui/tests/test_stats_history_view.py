"""StatsHistoryView のテスト（T8）。"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.stats_history_view import (  # noqa: E402
    COL_CONTEXT,
    COL_ELAPSED,
    COL_MODEL,
    COL_NAME,
    COL_SKILLS,
    COL_TOOLS,
    StatsHistoryView,
    _agg_workflow_counts,
    _fmt_context,
    _fmt_counts,
    _fmt_elapsed,
)
from hve.gui.workbench_state import (  # noqa: E402
    StepView,
    WorkbenchState,
    WorkflowStatsSnapshot,
    StepStatsSnapshot,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def _state_with_history() -> WorkbenchState:
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="gpt-x")
    s.steps.append(StepView(id="s1", title="Step 1"))
    s.update_identity(workflow_id="wf1", workflow_name="WF A", run_id="r1")
    s.set_step_status("s1", "running")
    s.set_context(1000, 10000, 5)
    s.record_tool_call("s1", "read_file")
    s.record_tool_call("s1", "read_file")
    s.record_skill_invoked("s1", "task-questionnaire")
    s.set_step_status("s1", "done")
    s.mark_all_done()
    return s


# ----------------------------------------------------------------------
# フォーマッタ
# ----------------------------------------------------------------------


def test_fmt_context():
    assert _fmt_context(None, None) == "-"
    assert _fmt_context(0, 0) == "0"
    assert _fmt_context(1000, 10000) == "1,000 / 10,000 (10%)"


def test_fmt_elapsed():
    assert _fmt_elapsed(None) == "-"
    assert _fmt_elapsed(0) == "00:00:00"
    assert _fmt_elapsed(3661) == "01:01:01"


def test_fmt_counts_topn_and_more():
    counts = {f"t{i}": (10 - i) for i in range(8)}
    text = _fmt_counts(counts, top=5)
    # Top 5 (t0..t4) のみ + "+3 more"
    assert "t0×10" in text
    assert "t4×6" in text
    assert "t5" not in text
    assert "+3 more" in text


def test_fmt_counts_empty():
    assert _fmt_counts({}) == "-"


def test_agg_workflow_counts():
    wf = WorkflowStatsSnapshot(
        workflow_id="w", workflow_name="", run_id="r", model="m", started_at=0.0,
        steps=[
            StepStatsSnapshot(
                step_id="s1", step_title="", status="done", model="m",
                started_at=0, finished_at=1, elapsed_sec=1,
                context_current=None, context_limit=None,
                tool_counts={"a": 1, "b": 2}, skill_counts={"x": 1},
            ),
            StepStatsSnapshot(
                step_id="s2", step_title="", status="done", model="m",
                started_at=1, finished_at=2, elapsed_sec=1,
                context_current=None, context_limit=None,
                tool_counts={"a": 3}, skill_counts={"y": 2},
            ),
        ],
    )
    assert _agg_workflow_counts(wf, "tool_counts") == {"a": 4, "b": 2}
    assert _agg_workflow_counts(wf, "skill_counts") == {"x": 1, "y": 2}


# ----------------------------------------------------------------------
# View
# ----------------------------------------------------------------------


def test_view_renders_workflow_and_step_rows(qapp):
    s = _state_with_history()
    v = StatsHistoryView(s)
    v.refresh()

    assert v._tree.topLevelItemCount() == 1
    wf_item = v._tree.topLevelItem(0)
    assert "WF A" in wf_item.text(COL_NAME)
    assert wf_item.text(COL_MODEL) == "gpt-x"
    assert "10,000" in wf_item.text(COL_CONTEXT)
    assert "read_file×2" in wf_item.text(COL_TOOLS)
    assert "task-questionnaire×1" in wf_item.text(COL_SKILLS)

    # Step 子行
    assert wf_item.childCount() == 1
    step_item = wf_item.child(0)
    assert "s1" in step_item.text(COL_NAME)
    assert "read_file×2" in step_item.text(COL_TOOLS)
    assert step_item.text(COL_ELAPSED) != "-"


def test_view_updates_on_signal(qapp):
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="gpt-x")
    v = StatsHistoryView(s)
    assert v._tree.topLevelItemCount() == 0

    s.update_identity(workflow_id="wf1", workflow_name="WF A", run_id="r1")
    s.set_step_status("s1", "running")
    s.set_step_status("s1", "done")
    # スロットルなしで即時更新を確認するため refresh() を呼ぶ
    v.refresh()
    assert v._tree.topLevelItemCount() == 1
    assert v._tree.topLevelItem(0).childCount() == 1


def test_view_multiple_workflows(qapp):
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="gpt-x")
    s.update_identity(workflow_id="wf1", workflow_name="A", run_id="r1")
    s.set_step_status("s1", "running")
    s.set_step_status("s1", "done")
    s.mark_all_done()
    s.all_done = False
    s.update_identity(workflow_id="wf2", workflow_name="B", run_id="r2")
    s.set_step_status("s2", "running")
    s.set_step_status("s2", "done")

    v = StatsHistoryView(s)
    v.refresh()
    assert v._tree.topLevelItemCount() == 2


def test_view_userrole_data_for_dclick(qapp):
    s = _state_with_history()
    v = StatsHistoryView(s)
    v.refresh()
    wf_item = v._tree.topLevelItem(0)
    counts = wf_item.data(COL_TOOLS, Qt.ItemDataRole.UserRole)
    assert counts == {"read_file": 2}
    step_item = wf_item.child(0)
    sk = step_item.data(COL_SKILLS, Qt.ItemDataRole.UserRole)
    assert sk == {"task-questionnaire": 1}


def test_view_empty_state(qapp):
    s = WorkbenchState(workflow_id="wf", run_id="r", model="m")
    v = StatsHistoryView(s)
    v.refresh()
    assert v._tree.topLevelItemCount() == 0
