"""hve.gui.panel_toggle.dock_toggle_actions — QDockWidget と QToolButton の双方向同期。

``QDockWidget.visibilityChanged`` と ``QToolButton.toggled`` を双方向に接続し、
- Dock の表示/非表示がボタンの ON/OFF と一致
- ボタンを押すと Dock の表示が切り替わる

を実現する。再帰呼び出しを防ぐためのガード付き。
"""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QDockWidget, QToolButton


class DockToggleBinder(QObject):
    """Dock と Button を結びつけるバインダ。

    バインダ自身を ``QObject`` にし、シグナル接続をオーナーシップ管理可能にする。
    """

    def __init__(self, dock: QDockWidget, button: QToolButton, parent: QObject = None) -> None:
        super().__init__(parent or dock)
        self._dock = dock
        self._button = button
        self._suppress = False

        button.setCheckable(True)
        button.setChecked(dock.isVisible())

        dock.visibilityChanged.connect(self._on_dock_visibility_changed)
        button.toggled.connect(self._on_button_toggled)

    def _on_dock_visibility_changed(self, visible: bool) -> None:
        if self._suppress:
            return
        self._suppress = True
        try:
            self._button.setChecked(visible)
        finally:
            self._suppress = False

    def _on_button_toggled(self, checked: bool) -> None:
        if self._suppress:
            return
        self._suppress = True
        try:
            self._dock.setVisible(checked)
        finally:
            self._suppress = False


def bind(dock: QDockWidget, button: QToolButton) -> DockToggleBinder:
    """``DockToggleBinder`` のショートカット。バインダはガベージコレクション防止のため返す。"""
    return DockToggleBinder(dock, button)
