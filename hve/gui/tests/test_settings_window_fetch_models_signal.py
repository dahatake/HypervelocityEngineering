"""hve.gui.tests.test_settings_window_fetch_models_signal

「HVE 設定」ダイアログの C1「基本設定」セクションに追加した
「利用できるモデルの取得」ボタンについて、`_C1Basic.fetch_models_requested` が
`SettingsWindow.fetch_models_requested` へ正しく中継されることを検証する。

実際のフェッチ処理（QThread 起動等）は MainWindow 側に一本化されているため、
本テストではシグナル中継の配線のみを対象とする。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def settings_window(qapp, tmp_path: Path, monkeypatch):
    from hve.gui import settings_store
    from hve.gui.settings_window import SettingsWindow

    monkeypatch.setattr(
        settings_store, "settings_path", lambda: tmp_path / ".settings.txt"
    )
    win = SettingsWindow(repo_root=tmp_path)
    yield win
    win.close()
    win.deleteLater()


def test_c1_section_button_click_relays_to_settings_window_signal(settings_window):
    received: list = []
    settings_window.fetch_models_requested.connect(lambda: received.append(True))

    c1_widget = settings_window._sections["C1"]
    assert hasattr(c1_widget, "fetch_models_button")
    c1_widget.fetch_models_button.click()

    assert received == [True]


def test_c1_section_fetch_models_requested_signal_is_connected_exactly_once(
    settings_window,
):
    """二重接続で複数回イベントが発火しないことを保証する回帰テスト。"""
    call_count = {"n": 0}
    settings_window.fetch_models_requested.connect(
        lambda: call_count.__setitem__("n", call_count["n"] + 1)
    )

    c1_widget = settings_window._sections["C1"]
    c1_widget.fetch_models_requested.emit()

    assert call_count["n"] == 1
