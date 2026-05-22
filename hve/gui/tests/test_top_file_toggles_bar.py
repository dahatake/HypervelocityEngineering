"""hve.gui.top_file_toggles_bar のユニットテスト。"""

from __future__ import annotations

import os

import pytest
from PySide6.QtWidgets import QApplication, QDockWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_bar_has_two_toggle_buttons(qapp) -> None:
    from hve.gui.top_file_toggles_bar import TopFileTogglesBar

    bar = TopFileTogglesBar()
    assert bar.btn_explorer is not None
    assert bar.btn_preview is not None
    assert bar.btn_explorer.isCheckable()
    assert bar.btn_preview.isCheckable()


def test_buttons_have_japanese_labels(qapp) -> None:
    from hve.gui.top_file_toggles_bar import TopFileTogglesBar

    bar = TopFileTogglesBar()
    assert "ファイル" in bar.btn_explorer.text()
    assert "プレビュー" in bar.btn_preview.text()


def test_bind_creates_two_binders(qapp) -> None:
    from hve.gui.top_file_toggles_bar import TopFileTogglesBar

    bar = TopFileTogglesBar()
    dock_a = QDockWidget()
    dock_b = QDockWidget()
    bar.bind(dock_a, dock_b)
    assert len(bar._binders) == 2


def test_button_toggle_changes_dock_visibility(qapp) -> None:
    """ボタン toggled → Dock setVisible が双方向同期する。"""
    from hve.gui.top_file_toggles_bar import TopFileTogglesBar

    bar = TopFileTogglesBar()
    dock_a = QDockWidget()
    dock_b = QDockWidget()
    dock_a.setVisible(False)
    dock_b.setVisible(False)
    bar.bind(dock_a, dock_b)

    bar.btn_explorer.setChecked(True)
    assert dock_a.isHidden() is False
    bar.btn_explorer.setChecked(False)
    assert dock_a.isHidden() is True
