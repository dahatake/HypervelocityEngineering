"""hve.gui.tests.test_main_window_settings_fetch_wiring

「HVE 設定」ダイアログの C1「基本設定」にある「利用できるモデルの取得」ボタンが、
MainWindow のステータスバーにある同名ボタンと**全く同じ処理**
（`MainWindow._on_login_clicked`）を起動することを検証する。

実際のモデル取得スレッドは起動させず、`_on_login_clicked` が呼ばれることのみを確認する。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def main_window(qapp, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from hve.gui.main_window import MainWindow
    win = MainWindow()
    yield win
    win.close()
    win.deleteLater()


def test_settings_window_fetch_button_triggers_same_handler_as_status_bar(
    main_window, monkeypatch
):
    called = {"n": 0}
    monkeypatch.setattr(
        main_window, "_on_login_clicked", lambda: called.__setitem__("n", called["n"] + 1)
    )

    main_window._open_settings_window()
    c1_widget = main_window._settings_window._sections["C1"]
    c1_widget.fetch_models_button.click()

    assert called["n"] == 1


def test_reopening_settings_window_does_not_duplicate_connection(
    main_window, monkeypatch
):
    """設定ダイアログを閉じずに再度開いても、同一シグナル接続が重複しないこと。"""
    called = {"n": 0}
    monkeypatch.setattr(
        main_window, "_on_login_clicked", lambda: called.__setitem__("n", called["n"] + 1)
    )

    main_window._open_settings_window()
    # 既存インスタンスが可視のまま再度呼び出す（新規 SettingsWindow は生成されない）。
    main_window._open_settings_window()

    c1_widget = main_window._settings_window._sections["C1"]
    c1_widget.fetch_models_button.click()

    assert called["n"] == 1
