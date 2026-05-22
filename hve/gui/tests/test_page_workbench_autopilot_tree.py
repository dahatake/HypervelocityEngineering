"""Autopilot 経路で _on_update_timer 経由でツリーが反映されるかの統合テスト。

旧来 ``append_log`` だけでは ``_progress_widget`` が更新されず、Autopilot 実行時に
作業状況ツリーが空のまま表示される回帰があった。本テストは page_workbench の
``_update_ui`` が ``state.workflows`` を検出して ``update_workflow_instances`` を
自動呼び出しすることを保証する。
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def page(qapp, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from hve.gui.page_workbench import WorkbenchPage
    p = WorkbenchPage()
    # 周期タイマー (500ms _on_update_timer) を停止し、テスト中の発火順序を確定化する。
    p._update_timer.stop()
    yield p
    p.deleteLater()


def test_update_timer_reflects_autopilot_logs_into_tree(page):
    """append_log → _on_update_timer 起動 → ツリーに WorkflowInstance が描画される。"""
    page.append_log("wf-a#APP-01", "step1", "a-line")
    page.append_log("wf-b#APP-02", "step1", "b-line")
    # _workflow_plan は空 (Autopilot 経路)
    assert page._workflow_plan == []
    # タイマー Slot を手動 invoke
    page._on_update_timer()
    tree = page._progress_widget._tree
    assert tree.topLevelItemCount() == 2
    labels = [tree.topLevelItem(i).text(0) for i in range(2)]
    assert any("wf-a#APP-01" in t for t in labels)
    assert any("wf-b#APP-02" in t for t in labels)
    assert page._progress_widget._instances_mode is True


def test_update_timer_skips_when_no_workflows(page):
    """workflows 空かつ plan 空 → 何も描画されない（旧来の初期状態維持）。"""
    page._on_update_timer()
    assert page._progress_widget._tree.topLevelItemCount() == 0


def test_plan_mode_takes_precedence_over_instances(page):
    """Plan モード入力（``_mirror_plan_to_state`` 経由）がツリーに反映される。

    Phase 3a/3b: Plan/Instances レンダリングは ``state.workflows`` 単一 source に統一された。
    Plan モード側は ``start_orchestrators`` 内の ``_mirror_plan_to_state`` で
    ``state.workflows`` に流し込まれる。本テストでは外部 set_plan 入力を
    state にも反映してツリーに描画されることを確認する。
    """
    page._workflow_plan = [
        {"workflow_id": "wf-x", "workflow_name": "WfX", "steps": [("s1", "Step1")]}
    ]
    page._workflow_status = {"wf-x": ""}
    page._workflow_step_status = {"wf-x": {"s1": ""}}
    page._workflow_subtask_status = {"wf-x": {}}
    # Phase 3b: Plan モードでも state へミラーする必要がある
    page._mirror_plan_to_state()
    # state.workflows に同時混入する別 instance
    page.append_log("wf-other#APP-01", "step1", "x")
    page._on_update_timer()
    tree = page._progress_widget._tree
    labels = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    # Plan モード由来の "WF-X" (format_workflow_label の大文字化) が含まれる
    assert any("WF-X" in t for t in labels)
    # state.workflows 側 (wf-other#APP-01) も同時表示される（統合 source の挙動）
    assert any("wf-other" in t for t in labels)


def test_reset_for_autopilot_clears_plan_state(page):
    """reset_for_autopilot で plan モード残骸がクリアされる。"""
    page._workflow_plan = [
        {"workflow_id": "wf-x", "workflow_name": "WfX", "steps": [("s1", "Step1")]}
    ]
    page._workflow_status = {"wf-x": "実行中"}
    page._workflow_step_status = {"wf-x": {"s1": "実行中"}}
    page._workflow_subtask_status = {"wf-x": {}}
    page._progress_widget.set_plan(
        page._workflow_plan,
        page._workflow_status,
        page._workflow_step_status,
        page._workflow_subtask_status,
    )
    assert page._progress_widget._tree.topLevelItemCount() == 1

    page.reset_for_autopilot()

    assert page._workflow_plan == []
    assert page._workflow_status == {}
    assert page._workflow_step_status == {}
    assert page._workflow_subtask_status == {}
    assert page._progress_widget._tree.topLevelItemCount() == 0
    assert page._progress_widget._instances_mode is False


def test_reset_for_autopilot_clears_state_workflows(page):
    """連続 Autopilot 実行で前回の state.workflows 残骸が累積しないこと。"""
    page.append_log("wf-prev#APP-99", "step1", "old")
    assert "wf-prev#APP-99" in page._state.workflows

    page.reset_for_autopilot()

    assert dict(page._state.workflows) == {}
    # 新規 Autopilot のログのみが反映される
    page.append_log("wf-new#APP-01", "step1", "new")
    page._on_update_timer()
    tree = page._progress_widget._tree
    assert tree.topLevelItemCount() == 1
    assert "wf-new#APP-01" in tree.topLevelItem(0).text(0)
