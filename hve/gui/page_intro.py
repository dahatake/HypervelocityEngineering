"""hve.gui.page_intro — 各 Step ページ上部に置く説明バナー。"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from .help_content import guide_url, step_intro


class StepIntroBanner(QFrame):
    """Step ページの最上段に表示する説明枠。"""

    def __init__(self, step_index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        entry = step_intro(step_index)
        self.setObjectName("StepIntroBanner")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "#StepIntroBanner {"
            " background-color: #e3f2fd;"
            " border: 1px solid #90caf9;"
            " border-radius: 6px;"
            "}"
            " QLabel { color: #0d47a1; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(4)

        title_text = {
            0: self.tr("ℹ️  ① ワークフロー選択"),
            1: self.tr("ℹ️  ② オプション選択"),
            2: self.tr("ℹ️  ③ 実行"),
        }.get(step_index, "ℹ️")
        title = QLabel(title_text)
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        # 縦に長くなるのを防ぐため、原文の改行を区切り記号で 1 行化して表示する。
        # 原文は tooltip で確認可能 (改行を保持)。
        raw_text = entry.short
        single_line = raw_text.replace("\n", "  ・  ")
        body = QLabel(single_line)
        body.setWordWrap(False)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setToolTip(raw_text)
        # 横方向のあふれは親レイアウトの幅にクリッピングさせる。
        from PySide6.QtWidgets import QSizePolicy
        body.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        body.setMinimumWidth(0)
        layout.addWidget(body)

        url = guide_url(entry.guide_path)
        if url:
            link = QLabel(
                f'<a href="{url}" style="color:#1565c0;">'
                + self.tr("📖 詳しいガイド: users-guide/{path}").format(path=entry.guide_path)
                + "</a>"
            )
            link.setOpenExternalLinks(False)
            link.linkActivated.connect(lambda u: QDesktopServices.openUrl(QUrl(u)))
            layout.addWidget(link)
