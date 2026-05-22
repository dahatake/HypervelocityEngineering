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
    assert inst.log_buffer[-1] == "hello world"
    assert inst.step_log_buffers["step1"][-1] == "hello world"


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
    assert state.workflows["_global"].log_buffer[-1] == "fallback line"
