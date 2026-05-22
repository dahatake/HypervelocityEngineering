"""hve.gui.tests.test_settings_window_no_hscroll

設定画面（SettingsWindow）の各セクションを切り替えても、ラップしている
QScrollArea が水平スクロールを表示しないことを保証する回帰テスト。

根拠: copilot からの「設定画面での横スクロールの表示がでないようにしたい」
要件。settings_window.py の QScrollArea には
``Qt.ScrollBarAlwaysOff`` が指定されているため、ポリシー値で検証する。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_all_section_scroll_areas_disable_horizontal_scroll(
    qapp, tmp_path: Path, monkeypatch
):
    from hve.gui import settings_store
    from hve.gui.settings_window import SettingsWindow

    monkeypatch.setattr(
        settings_store, "settings_path", lambda: tmp_path / ".settings.txt"
    )

    win = SettingsWindow(repo_root=tmp_path)
    try:
        stack = win._stack
        assert stack.count() > 0, "設定画面にセクションが 1 つも登録されていない"
        for i in range(stack.count()):
            page = stack.widget(i)
            assert isinstance(page, QScrollArea), (
                f"stack index={i} が QScrollArea ではない: {type(page).__name__}"
            )
            policy = page.horizontalScrollBarPolicy()
            assert policy == Qt.ScrollBarAlwaysOff, (
                f"stack index={i} の水平スクロールポリシーが ScrollBarAlwaysOff ではない: "
                f"{policy!r}"
            )
    finally:
        win.close()
        win.deleteLater()
