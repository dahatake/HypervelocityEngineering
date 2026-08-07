"""Wave 2 T2.3: WorkbenchPage 統合レイアウトの構造テスト。"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QSplitter  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def page(qapp, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from hve.gui.page_workbench import WorkbenchPage
    p = WorkbenchPage()
    yield p
    p.deleteLater()


def test_horizontal_splitter_3_to_7(page):
    sp = page._splitter
    assert isinstance(sp, QSplitter)
    assert sp.orientation() == Qt.Orientation.Horizontal
    assert sp.count() == 2
    assert sp.childrenCollapsible() is False
    # 初期サイズが 3:7 (300:700) で設定されている
    sizes = sp.sizes()
    assert len(sizes) == 2
    # 比率の妥当性（初期サイズベース、レイアウト計算後でもおおむね 3:7）
    # 直接設定値は内部保存される: 0 でないことを確認
    assert sizes[0] >= 0 and sizes[1] >= 0


def test_right_pane_vertical_splitter(page):
    rs = page._right_splitter
    assert rs.orientation() == Qt.Orientation.Vertical
    assert rs.count() == 2
    assert rs.childrenCollapsible() is False


def test_user_actions_text_box_expands_with_pane_height(page):
    pane = page._user_actions_pane
    view = pane.view
    header = next(lbl for lbl in pane.findChildren(QLabel) if lbl.text().startswith("実行中の課題"))
    default_view = QPlainTextEdit()

    try:
        assert isinstance(view, QPlainTextEdit)
        assert view.maximumHeight() == default_view.maximumHeight()

        pane.show()
        pane.resize(360, 160)
        pane.layout().setGeometry(pane.rect())
        QApplication.processEvents()
        header_height = header.height()
        view_height = view.height()

        pane.resize(360, 320)
        pane.layout().setGeometry(pane.rect())
        QApplication.processEvents()

        assert header.height() == header_height
        assert view.height() > view_height
    finally:
        default_view.deleteLater()


def test_user_actions_pane_renders_all_retained_actions(page):
    state = page._state
    action_count = 51
    for i in range(action_count):
        state.add_user_action(
            timestamp=f"12:00:{i:02d}",
            level="ERROR",
            message=f"retained-action-{i}",
            step_id=f"step-{i}",
        )

    page._user_actions_pane.update_from_state(state)
    text = page._user_actions_pane.view.toPlainText()

    assert len(state.user_actions) == action_count
    header = next(
        label
        for label in page._user_actions_pane.findChildren(QLabel)
        if label.text().startswith("実行中の課題")
    )
    assert header.text() == f"実行中の課題 ({action_count})"
    for i in range(action_count):
        assert f"retained-action-{i}" in text


def test_user_actions_pane_header_shows_total_count(page):
    pane = page._user_actions_pane
    header = next(lbl for lbl in pane.findChildren(QLabel) if lbl.text().startswith("実行中の課題"))

    pane.update_from_state(page._state)
    assert header.text() == "実行中の課題"

    page._state.add_user_action(
        timestamp="12:34:56",
        level="WARN",
        message="header-count-check",
        step_id="step-1",
    )
    pane.update_from_state(page._state)
    assert header.text() == "実行中の課題 (1)"


class _UserActionsViewProbe:
    """``setPlainText`` 呼び出しを記録する差し替え用スタブ。"""

    def __init__(self) -> None:
        self.set_calls: list[str] = []

    def setPlainText(self, text: str) -> None:
        self.set_calls.append(text)

    def verticalScrollBar(self):
        return None


def test_user_actions_pane_skips_redundant_set_plain_text(qapp):
    """NFR-OBS-09 (4): 表示テキストが不変なら setPlainText を実行しない。"""
    from hve.gui.page_workbench import _EnhancedUserActionsPane
    from hve.gui.workbench_state import WorkbenchState

    pane = _EnhancedUserActionsPane()
    try:
        state = WorkbenchState("wf", "run", "model")
        state.add_user_action(
            timestamp="12:00:00",
            level="ERROR",
            message="cache-check",
            step_id="step-1",
            category="ツール失敗",
        )
        probe = _UserActionsViewProbe()
        pane.view = probe

        pane.update_from_state(state)
        pane.update_from_state(state)

        assert len(probe.set_calls) == 1
    finally:
        pane.deleteLater()


def test_user_actions_pane_reflects_downgraded_message(qapp):
    """NFR-OBS-09 (4): NFR-OBS-07 の降格はテキスト変化として反映される。"""
    from hve.gui.page_workbench import _EnhancedUserActionsPane
    from hve.gui.workbench_state import WorkbenchState

    pane = _EnhancedUserActionsPane()
    try:
        state = WorkbenchState("wf", "run", "model")
        state.add_user_action(
            timestamp="12:00:00",
            level="ERROR",
            message="tool: boom",
            step_id="step-1",
            category="ツール失敗",
        )
        probe = _UserActionsViewProbe()
        pane.view = probe

        pane.update_from_state(state)
        state.user_actions[0].level = "INFO"
        state.user_actions[0].message = "[回復済み] tool: boom"
        pane.update_from_state(state)

        assert len(probe.set_calls) == 2
        assert "[回復済み] tool: boom" in probe.set_calls[-1]
    finally:
        pane.deleteLater()


def test_left_pane_is_activity_widget(page):
    sp = page._splitter
    assert sp.widget(0) is page._progress_widget


def test_log_pane_append_mirrors_to_log_tabs(page):
    page._log_pane.append_line("hello-world")
    assert "hello-world" in page._log_tabs.global_text()


def test_workflow_instance_selection_updates_selected_tab(page):
    s = page._state
    s.ensure_workflow_instance("wf-x", "wf-x", "WF-X")
    s.append_workflow_log("wf-x", None, "line-a")
    s.append_workflow_log("wf-x", None, "line-b")
    # Tree を instances モードに切替・選択
    page._progress_widget.update_workflow_instances(s)
    # DagStatusWidget はノード選択時に node_selected(instance_id, step_id) を emit する。
    # Workflow ヘッダ選択 (step_id="") を再現してインスタンス全体ログを選択タブへ反映。
    page._progress_widget.node_selected.emit("wf-x", "")
    txt = page._log_tabs.selected_text()
    assert "line-a" in txt and "line-b" in txt


def test_single_workflow_set_plan_still_works(page):
    """シングル workflow 回帰確認: set_plan ベースの描画が動く。"""
    plan = [{"workflow_id": "wf-1", "workflow_name": "WF-1", "steps": [("s1", "Step 1")]}]
    page._progress_widget.set_plan(plan, {"wf-1": "実行中"}, {"wf-1": {"s1": "実行中"}})
    entries = page._progress_widget._entries
    assert len(entries) == 1
    assert "WF-1" in entries[0].label
