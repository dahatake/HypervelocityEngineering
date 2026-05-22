"""hve.gui.activity_bar — VS Code 風の縦アクティビティバー。

幅 48px 固定、上端から ``QToolButton(checkable=True)`` を縦に並べる。
本フェーズでは [📂 エクスプローラ] / [📄 プレビュー] の 2 ボタン構成。

各ボタンは外部から ``DockToggleBinder.bind(dock, button)`` で対応する Dock と
結線される（バインドは ``MainWindow`` 側の責務）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSizePolicy, QToolButton, QVBoxLayout, QWidget


_BAR_WIDTH = 48
_BUTTON_SIZE = 36
_ICON_SIZE = 22

_QSS = """
QToolButton {
    background: transparent;
    border: none;
    padding: 4px;
}
QToolButton:hover {
    background: rgba(0, 0, 0, 0.08);
}
QToolButton:checked {
    background: rgba(0, 0, 0, 0.15);
    border-left: 2px solid #007acc;
}
"""

_ICONS_PACKAGE_DIR = Path(__file__).parent / "icons"


def _load_icon(name: str) -> QIcon:
    """``hve/gui/icons/<name>`` を読み込む。存在しなければ空 QIcon。"""
    p = _ICONS_PACKAGE_DIR / name
    if p.is_file():
        icon = QIcon(str(p))
        if not icon.isNull():
            return icon
    return QIcon()


class ActivityBar(QWidget):
    """縦並びトグルボタンバー。

    Attributes:
        btn_explorer: ファイルツリー Dock 用のトグルボタン。
        btn_preview:  Markdown プレビュー Dock 用のトグルボタン。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(_BAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(_QSS)
        self.setObjectName("ActivityBar")

        self.btn_explorer = self._make_button(
            icon=_load_icon("folder.svg"),
            tooltip=self.tr("ファイル一覧の表示/非表示"),
        )
        self.btn_preview = self._make_button(
            icon=_load_icon("preview.svg"),
            tooltip=self.tr("Markdown プレビューの表示/非表示"),
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(4)
        layout.addWidget(self.btn_explorer, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.btn_preview, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

    def _make_button(self, *, icon: QIcon, tooltip: str) -> QToolButton:
        btn = QToolButton(self)
        btn.setCheckable(True)
        btn.setChecked(True)
        btn.setAutoRaise(True)
        btn.setIcon(icon)
        btn.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
        btn.setFixedSize(_BUTTON_SIZE, _BUTTON_SIZE)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn
