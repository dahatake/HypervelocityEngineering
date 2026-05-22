"""hve.gui.copy_button — 各 UI コンポーネントに付与する共通コピーアイコン。

要件4（plan.md）: 各画面コンポーネントにコピーアイコンを表示し、クリックで
そのコンポーネントの文字列をクリップボードへコピーする。

使い方:
    btn = CopyButton(get_text=lambda: my_log_view.toPlainText())
    layout.addWidget(btn)
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QToolButton, QStyle, QWidget


class CopyButton(QToolButton):
    """クリップボードコピー用の小型ツールボタン。

    Args:
        get_text: クリック時に呼ばれ、コピー対象テキストを返す callable
        tooltip:  ホバー時のツールチップ（既定: 「クリップボードにコピー」）
        parent:   親ウィジェット
    """

    def __init__(
        self,
        get_text: Callable[[], str],
        *,
        tooltip: str = "クリップボードにコピー",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._get_text = get_text
        themed = QIcon.fromTheme("edit-copy")
        if themed.isNull():
            style = self.style()
            if style is not None:
                self.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        else:
            self.setIcon(themed)
        self.setToolTip(tooltip)
        self.setText("📋")
        self.setAutoRaise(True)
        self.clicked.connect(self._on_click)

    def _on_click(self) -> None:
        try:
            text = self._get_text() or ""
        except Exception as e:
            text = f"[CopyButton] get_text 取得失敗: {e!r}"
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
            self.setToolTip(f"コピー済み: {len(text)} 文字")
