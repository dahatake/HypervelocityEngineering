"""[REMOVED] 旧 ActivityStatusWidget マルチ WorkflowInstance テスト。

DagStatusWidget への置換により廃止。新ウィジェットのテストは
test_dag_status_widget.py / test_dag_layout.py を参照。
"""
from __future__ import annotations

import pytest

pytest.skip(
    "ActivityStatusWidget removed; replaced by DagStatusWidget",
    allow_module_level=True,
)

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.workbench_state import (  # noqa: E402
    StepView,
    WorkbenchState,
)
from hve.gui.workbench_widgets import ActivityStatusWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _state_with_two_workflows() -> WorkbenchState:
    s = WorkbenchState(workflow_id="root", run_id="r1", model="m")
    a = s.ensure_workflow_instance("wf-a#APP-01", "wf-a", "WF-A (APP-01)", app_id="APP-01")
    a.steps["s1"] = StepView(id="s1", title="Step 1", status="running")
    a.steps["s2"] = StepView(id="s2", title="Step 2", status="pending")
    s.update_workflow_instance_status("wf-a#APP-01", "running")

    s.ensure_workflow_instance("wf-b#APP-02", "wf-b", "WF-B (APP-02)", app_id="APP-02")
    s.workflows["wf-b#APP-02"].steps["t1"] = StepView(id="t1", title="Task 1", status="done")
    return s


def test_renders_multiple_workflow_instances(qapp):
    s = _state_with_two_workflows()
    w = ActivityStatusWidget(theme="light")
    try:
        w.update_workflow_instances(s)
        tree = w._tree
        assert tree.topLevelItemCount() == 2
        top0 = tree.topLevelItem(0)
        top1 = tree.topLevelItem(1)
        assert "WF-A (APP-01)" in top0.text(0)
        assert "WF-B (APP-02)" in top1.text(0)
        # 子 Step ノードが含まれる
        assert top0.childCount() == 2
        assert "Step 1" in top0.child(0).text(0)
        assert top1.childCount() == 1
        assert "Task 1" in top1.child(0).text(0)
    finally:
        w.deleteLater()


def test_emits_instance_id_on_selection(qapp):
    s = _state_with_two_workflows()
    w = ActivityStatusWidget(theme="light")
    received: list[str] = []
    w.workflow_instance_selected.connect(received.append)
    try:
        w.update_workflow_instances(s)
        tree = w._tree
        # 1 つ目（wf-a）を選択
        tree.setCurrentItem(tree.topLevelItem(0))
        assert received == ["wf-a#APP-01"]
        # 2 つ目（wf-b）に切替
        tree.setCurrentItem(tree.topLevelItem(1))
        assert received[-1] == "wf-b#APP-02"
    finally:
        w.deleteLater()


def test_child_step_selection_does_not_emit_instance_id(qapp):
    """中間（Workflow）ノード以外の選択では emit されない。"""
    s = _state_with_two_workflows()
    w = ActivityStatusWidget(theme="light")
    received: list[str] = []
    w.workflow_instance_selected.connect(received.append)
    try:
        w.update_workflow_instances(s)
        tree = w._tree
        # ステップ子ノードを選択
        step_item = tree.topLevelItem(0).child(0)
        tree.setCurrentItem(step_item)
        assert received == []
    finally:
        w.deleteLater()


def test_empty_workflows_is_noop(qapp):
    s = WorkbenchState(workflow_id="root", run_id="r1", model="m")
    w = ActivityStatusWidget(theme="light")
    try:
        # workflows が空なら何もしない（旧 set_plan モードを壊さない）
        w.update_workflow_instances(s)
        assert w._tree.topLevelItemCount() == 0
        assert w._instances_mode is False
    finally:
        w.deleteLater()


def test_unchanged_structure_skips_rebuild(qapp):
    """構造変化なし時は tree.clear() を呼ばず、_refresh_instances_labels のみ走る。

    高頻度 ``update_workflow_instances`` 呼び出しで選択状態が消失したり、
    ``QTreeWidget.clear`` の負荷が累積したりするのを防ぐ。
    """
    s = _state_with_two_workflows()
    w = ActivityStatusWidget(theme="light")
    try:
        w.update_workflow_instances(s)
        clear_count = {"n": 0}
        orig_clear = w._tree.clear

        def _counting_clear():
            clear_count["n"] += 1
            orig_clear()

        w._tree.clear = _counting_clear  # type: ignore[assignment]
        # 同じ state を 5 回再投入（status・構造変化なし）
        for _ in range(5):
            w.update_workflow_instances(s)
        assert clear_count["n"] == 0
        # 構造変化を 1 度だけ起こす → clear が 1 回呼ばれる
        s.update_workflow_instance_status("wf-a#APP-01", "done")
        w.update_workflow_instances(s)
        assert clear_count["n"] == 1
    finally:
        w.deleteLater()
