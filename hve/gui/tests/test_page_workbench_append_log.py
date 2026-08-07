"""hve.gui.tests.test_page_workbench_append_log

T3.2 (gui-unified-workbench Wave 3) — WorkbenchPage.append_log の単体テスト。
Autopilot から WorkbenchPage への統一ログ配信 API が
  - 未登録の WorkflowInstance を自動生成する
  - 該当インスタンスの log_buffer / step_log_buffers に追記する
  - "全体" タブ (_log_tabs.append_global) にもミラーする
ことを検証する。
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_append_log_creates_instance_and_appends(qapp):
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    page.append_log("app-a", "step1", "hello world")

    state = page._state
    assert "app-a" in state.workflows
    inst = state.workflows["app-a"]
    # append_workflow_log は `[WF大文字] [step_id] ` プリフィックスを付与する
    # （workbench_state.format_log_prefix / Q3=i 仕様）。
    assert inst.log_buffer[-1] == "[APP-A] [step1] hello world"
    assert inst.step_log_buffers["step1"][-1] == "[APP-A] [step1] hello world"


def test_append_log_mirrors_to_global_tab(qapp):
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    page.append_log("app-b", "", "line for global tab")

    # _log_tabs._global_view が QPlainTextEdit 系の場合 toPlainText で確認
    global_view = getattr(page._log_tabs, "_global_view", None)
    if global_view is not None and hasattr(global_view, "toPlainText"):
        assert "line for global tab" in global_view.toPlainText()


def test_append_log_empty_instance_id_uses_fallback(qapp):
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    page.append_log("", "", "fallback line")

    state = page._state
    assert "_global" in state.workflows
    # 空 instance_id は "_global"、空 step_id は "main" にフォールバックし
    # `[_GLOBAL] [main] ` プリフィックスが付与される。
    assert state.workflows["_global"].log_buffer[-1] == "[_GLOBAL] [main] fallback line"


class _ScrollBarStub:
    """スクロール操作の到達を許容するための最小スタブ。"""

    def value(self) -> int:
        return 0

    def maximum(self) -> int:
        return 0

    def setValue(self, value: int) -> None:
        return None


class _ScrollBarProbe:
    """``verticalScrollBar`` 呼び出しを検出するための差し替え用スタブ。"""

    def __init__(self) -> None:
        self.calls = 0

    def verticalScrollBar(self) -> _ScrollBarStub:
        self.calls += 1
        return _ScrollBarStub()


def test_append_line_does_not_write_to_hidden_view(qapp, tmp_path):
    """NFR-OBS-09 (2): 非表示 _LogPane の QPlainTextEdit へ追記しない。"""
    from hve.gui.page_workbench import _LogPane

    pane = _LogPane("ログ")
    run_dir = tmp_path / "run-hidden"
    run_dir.mkdir()
    try:
        pane.set_log_base_dir(run_dir)
        pane.append_line("hidden-view-check")
        assert pane.log_view.toPlainText() == ""
        content = (run_dir / "gui-logs" / "log-0001.log").read_text(encoding="utf-8")
        assert "hidden-view-check" in content
    finally:
        pane.deleteLater()


def test_scroll_log_does_not_touch_hidden_view(qapp):
    """NFR-OBS-09 (2): ログのスクロール操作が非表示ウィジェットを対象にしない。"""
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    probe = _ScrollBarProbe()
    page._log_pane.log_view = probe
    page._scroll_log(3)
    assert probe.calls == 0


def test_key_scroll_does_not_touch_hidden_view(qapp):
    """NFR-OBS-09 (2): `g` / `G` キーが非表示ウィジェットを対象にしない。"""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    probe = _ScrollBarProbe()
    page._log_pane.log_view = probe

    for key, text in ((Qt.Key.Key_G, "g"), (Qt.Key.Key_G, "G")):
        event = QKeyEvent(
            QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text
        )
        page.keyPressEvent(event)

    assert probe.calls == 0
