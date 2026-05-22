"""hve.gui.activity_bar のユニットテスト。"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from hve.gui.activity_bar import ActivityBar


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_activity_bar_has_two_buttons(qapp) -> None:
    bar = ActivityBar()
    assert bar.btn_explorer is not None
    assert bar.btn_preview is not None


def test_buttons_are_checkable_and_initially_on(qapp) -> None:
    bar = ActivityBar()
    assert bar.btn_explorer.isCheckable()
    assert bar.btn_preview.isCheckable()
    assert bar.btn_explorer.isChecked()
    assert bar.btn_preview.isChecked()


def test_bar_has_fixed_width(qapp) -> None:
    bar = ActivityBar()
    # _BAR_WIDTH = 48 と一致
    assert bar.width() == 48 or bar.maximumWidth() == 48 or bar.minimumWidth() == 48


def test_button_tooltips_set(qapp) -> None:
    bar = ActivityBar()
    assert bar.btn_explorer.toolTip() != ""
    assert bar.btn_preview.toolTip() != ""
