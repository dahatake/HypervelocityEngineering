"""hve.gui.panel_toggle.dock_toggle_actions のユニットテスト。"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QToolButton, QWidget

from hve.gui.panel_toggle.dock_toggle_actions import DockToggleBinder, bind


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _make_dock(parent_window: QMainWindow) -> QDockWidget:
    dock = QDockWidget("test", parent_window)
    dock.setWidget(QWidget())
    parent_window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
    return dock


def test_initial_button_state_reflects_dock_visible(qapp) -> None:
    win = QMainWindow()
    dock = _make_dock(win)
    win.show()
    qapp.processEvents()
    btn = QToolButton()
    binder = bind(dock, btn)
    assert isinstance(binder, DockToggleBinder)
    assert btn.isCheckable()
    assert btn.isChecked() == dock.isVisible()


def test_button_toggle_hides_dock(qapp) -> None:
    win = QMainWindow()
    dock = _make_dock(win)
    win.show()
    qapp.processEvents()
    btn = QToolButton()
    bind(dock, btn)
    assert dock.isVisible() is True
    assert btn.isChecked() is True

    btn.setChecked(False)
    qapp.processEvents()
    assert dock.isVisible() is False


def test_dock_close_updates_button(qapp) -> None:
    win = QMainWindow()
    dock = _make_dock(win)
    win.show()
    qapp.processEvents()
    btn = QToolButton()
    bind(dock, btn)

    dock.setVisible(False)
    qapp.processEvents()
    assert btn.isChecked() is False


def test_no_recursive_signaling(qapp) -> None:
    """ボタン→Dock→ボタン の無限ループが発生しないこと。"""
    win = QMainWindow()
    dock = _make_dock(win)
    win.show()
    qapp.processEvents()
    btn = QToolButton()
    bind(dock, btn)

    toggle_count = [0]

    def _inc(_: bool) -> None:
        toggle_count[0] += 1

    btn.toggled.connect(_inc)

    dock.setVisible(False)
    qapp.processEvents()
    dock.setVisible(True)
    qapp.processEvents()
    # 上記操作で例外無く完了し、ボタン toggle は各ステップ 1 回ずつしか発火しない
    # （無限ループなら toggle_count が爆発）。
    assert toggle_count[0] == 2
