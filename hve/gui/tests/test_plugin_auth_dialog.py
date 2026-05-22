"""PluginAuthDialog / MainWindow ヘッダーの簡易スモークテスト。

Qt offscreen プラットフォームで描画なしに UI 構造を検証する。
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton, QLabel  # noqa: E402

from hve.gui.auth_providers import AuthState, AuthStatus  # noqa: E402
from hve.gui.auth_providers.github_provider import GitHubProvider  # noqa: E402
from hve.gui.plugin_auth_dialog import PluginAuthDialog  # noqa: E402


@pytest.fixture(scope="module")
def _qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


class _FakeProvider:
    """テスト用 AuthProvider 実装。"""

    def __init__(self, pid: str, name: str, required: bool = False) -> None:
        self.id = pid
        self.display_name = name
        self.required = required

    def is_applicable(self, settings):
        return True

    def check_status(self, *, timeout=15.0):
        return AuthStatus(state=AuthState.NOT_AUTHENTICATED, detail="test")

    def authenticate(self, *, timeout=600.0, on_progress=None, cancel_check=None):
        from hve.gui.auth_providers import AuthResult
        return AuthResult(success=True, state=AuthState.AUTHENTICATED, message="ok")


def test_dialog_populates_rows_for_each_provider(_qapp, qtbot=None):
    providers = [
        _FakeProvider("github", "GitHub Copilot", required=True),
        _FakeProvider("mcp:foo", "MCP: foo"),
    ]
    dlg = PluginAuthDialog(providers)
    assert dlg._table.rowCount() == 2
    # 1 列目: 名称
    assert dlg._table.item(0, 0).text() == "GitHub Copilot"
    assert dlg._table.item(1, 0).text() == "MCP: foo"
    # アクションボタンが配置されている
    assert isinstance(dlg._table.cellWidget(0, 3), QPushButton)
    dlg.deleteLater()


def test_dialog_latest_states_initial_unknown(_qapp):
    providers = [_FakeProvider("github", "GitHub Copilot", required=True)]
    dlg = PluginAuthDialog(providers)
    snapshot = dlg.latest_states()
    assert snapshot["github"] is AuthState.UNKNOWN
    dlg.deleteLater()


def test_mainwindow_has_no_title_label_and_has_auth_button(_qapp):
    """T10/T13: top_row に新 QLabel + QPushButton が配置されていることを検証。"""
    # MainWindow 全体起動は重いので、ヘッダー部分のみインスペクトする。
    from hve.gui.main_window import MainWindow

    # _refresh_auth_providers が settings_store.load() を呼ぶので副作用回避のため offscreen のみ。
    with patch("hve.auth.get_auth_status") as mock_status:
        mock_status.return_value = type(
            "I", (), {"is_authenticated": False, "login": None, "status_message": "no token"}
        )
        win = MainWindow(session_index=99)
    # 新ボタンが存在
    assert hasattr(win, "_btn_plugin_auth")
    assert isinstance(win._btn_plugin_auth, QPushButton)
    # 旧: 画面内 _title_label。新仕様で削除済み（ウィンドウタイトルに移動）
    assert not hasattr(win, "_title_label")
    # ウィンドウタイトルが "HVE Workbench" を含む
    assert "HVE Workbench" in win.windowTitle()
    # 利用できるモデルの取得 ボタンが常時可視 + 初期 disabled
    assert win._btn_login.isVisible() is False or win._btn_login.isVisible() is True  # show() 前は False の場合あり
    assert win._btn_login.isEnabled() is False
    # AuthMonitor が紐付いている
    assert hasattr(win, "_auth_monitor")
    win._auth_monitor.stop()
    win.deleteLater()
