"""hve.gui.help_popup — クリックで開閉する説明ポップアップウィジェット。

使い方::

    from .help_popup import HelpPopupButton, with_help

    btn = HelpPopupButton.from_key("options.model")
    layout.addWidget(btn)

    # フォーム行のラベル + ヘルプアイコンを一括生成
    form.addRow(with_help("使用するモデル:", "options.model"), self.model)

説明文の取得は `hve.gui.help_content` に集約されている（捏造禁止）。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .help_content import HelpEntry, guide_url


_POPUP_MAX_WIDTH = 380


class _HelpPopup(QFrame):
    """フレームレスのヘルプポップアップ本体。

    `Qt.Popup` フラグを使うことで Qt が自動的に外部クリックで閉じる挙動を提供する。
    ESC キーでも閉じる。
    """

    def __init__(self, entry: HelpEntry, anchor: QWidget) -> None:
        # 親を anchor にすると anchor が消えたとき自動で消える
        super().__init__(anchor, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("HelpPopup")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "#HelpPopup {"
            " background-color: #fffde7;"
            " border: 1px solid #fbc02d;"
            " border-radius: 6px;"
            "}"
            " QLabel { color: #424242; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        body = QLabel(entry.short or "（説明がありません）")
        body.setWordWrap(True)
        body.setMaximumWidth(_POPUP_MAX_WIDTH)
        layout.addWidget(body)

        url = guide_url(entry.guide_path, entry.guide_anchor)
        if url:
            link = QLabel(
                f'<a href="{url}" style="color:#1565c0;">'
                f"📖 詳しいガイド: {entry.guide_path}</a>"
            )
            link.setOpenExternalLinks(False)
            link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            link.linkActivated.connect(self._open_link)
            layout.addWidget(link)

        self.adjustSize()

    def _open_link(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


class HelpPopupButton(QToolButton):
    """`(?)` 形状のヘルプボタン。クリックで `_HelpPopup` を表示する。"""

    def __init__(self, entry: HelpEntry, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._entry = entry
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        style = self.style()
        if style is not None:
            self.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion))
        self.setText("")
        self.setToolTip(self.tr("クリックで詳しい説明を表示"))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(20, 20)
        self.setIconSize(self.size() * 0.8)
        self.clicked.connect(self._show_popup)

    @classmethod
    def from_key(cls, key: str, parent: Optional[QWidget] = None) -> Optional["HelpPopupButton"]:
        """説明文がある場合のみボタンを生成する。無い場合は None を返す。"""
        entry = _entry_for_key(key)
        if not entry.short:
            return None
        return cls(entry, parent)

    def _show_popup(self) -> None:
        popup = _HelpPopup(self._entry, self)
        # ボタンの右下を起点に表示
        global_pos = self.mapToGlobal(QPoint(self.width(), self.height()))
        popup.move(global_pos)
        popup.show()
        popup.setFocus()


def _entry_for_key(key: str) -> HelpEntry:
    """`"options.model"` 等のキーから HelpEntry を解決する。"""
    from . import help_content as hc

    if "." not in key:
        return HelpEntry(short="")
    scope, name = key.split(".", 1)
    if scope == "workflow":
        return hc.workflow_help(name)
    if scope == "options":
        return hc.option_help(name)
    if scope == "workbench":
        return hc.workbench_help(name)
    if scope == "category":
        return hc.category_help(name)
    if scope == "step_intro":
        try:
            return hc.step_intro(int(name))
        except ValueError:
            return HelpEntry(short="")
    return HelpEntry(short="")


def with_help(label_text: str, key: str, parent: Optional[QWidget] = None) -> QWidget:
    """`QLabel + HelpPopupButton` を横並びにまとめたコンテナを返す。

    ヘルプが無い場合は単純な `QLabel` を返す（互換のため `QWidget` 型）。
    """
    btn = HelpPopupButton.from_key(key, parent)
    if btn is None:
        return QLabel(label_text, parent)

    container = QWidget(parent)
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(QLabel(label_text))
    layout.addWidget(btn)
    layout.addStretch()
    return container
