"""hve.gui.top_file_toggles_bar — 画面上部に常時表示する ファイル/プレビュー トグル。

旧 ``ActivityBar``（縦 48px バー）と ``FileTreePanel.setup_file_section_title_bar``
（Dock タイトルバー内の横並びトグル）を統合し、画面上部 ``top_row`` の左端に
常時表示される 2 トグル（``📂 ファイル`` / ``📄 プレビュー``）を提供する。

Dock との双方向同期は ``panel_toggle.dock_toggle_actions.bind`` を再利用する。
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QHBoxLayout, QToolButton, QWidget

from .panel_toggle.dock_toggle_actions import DockToggleBinder, bind as bind_dock_toggle


_QSS = """
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    padding: 2px 8px;
}
QToolButton:hover {
    background: rgba(0, 0, 0, 0.08);
}
QToolButton:checked {
    background: rgba(0, 0, 0, 0.12);
    border: 1px solid rgba(0, 0, 0, 0.20);
}
"""


class TopFileTogglesBar(QWidget):
    """画面上部の ファイル/プレビュー トグルバー（横並び・常時表示）。

    Attributes:
        btn_explorer: ファイルツリー Dock 用のトグルボタン。
        btn_preview:  Markdown プレビュー Dock 用のトグルボタン。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopFileTogglesBar")
        self.setStyleSheet(_QSS)

        self.btn_explorer = self._make_button(
            text=self.tr("📂 ファイル"),
            tooltip=self.tr("ファイル一覧の表示/非表示"),
        )
        self.btn_preview = self._make_button(
            text=self.tr("📄 プレビュー"),
            tooltip=self.tr("Markdown プレビューの表示/非表示"),
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.btn_explorer)
        layout.addWidget(self.btn_preview)

        # Dock とのバインダ（GC 防止のため保持）
        self._binders: List[DockToggleBinder] = []

    def _make_button(self, *, text: str, tooltip: str) -> QToolButton:
        btn = QToolButton(self)
        btn.setText(text)
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setChecked(True)
        btn.setAutoRaise(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def bind(self, file_dock: QDockWidget, preview_dock: QDockWidget) -> None:
        """2 つの Dock とトグルボタンを双方向同期させる。

        本メソッドは複数回呼ばないこと（呼び出し側で 1 回だけ）。
        """
        self._binders.append(bind_dock_toggle(file_dock, self.btn_explorer))
        self._binders.append(bind_dock_toggle(preview_dock, self.btn_preview))
