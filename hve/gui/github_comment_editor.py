"""hve.gui.github_comment_editor — Markdown 入力欄の書式支援とプレビュー（FR-GUI-30）。

Issue 本文 / Issue コメント / Pull Request コメントの各入力欄が共有する単一実装。
入力欄は Markdown の原文をそのまま保持し、リッチテキストから再生成しない。
Markdown → HTML 変換は `markdown_preview.MarkdownHtmlRenderer` を再利用する。
"""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .markdown_preview.markdown_html_renderer import MarkdownHtmlRenderer

__all__ = ["GitHubCommentEditor", "FORMAT_ACTIONS"]

# (key, 前置き, 後置き, 行頭付与か)
_WRAP_ACTIONS = {
    "bold": ("**", "**"),
    "italic": ("*", "*"),
    "code": ("`", "`"),
}
_LINE_PREFIXES = {
    "heading": "### ",
    "quote": "> ",
    "bullet": "- ",
    "number": "1. ",
    "task": "- [ ] ",
}
# FR-GUI-30: 書式挿入は 9 種。
FORMAT_ACTIONS: Tuple[str, ...] = (
    "bold",
    "italic",
    "heading",
    "quote",
    "code",
    "link",
    "bullet",
    "number",
    "task",
)

_LINK_PLACEHOLDER = "url"

_renderer: Optional[MarkdownHtmlRenderer] = None


def _shared_renderer() -> MarkdownHtmlRenderer:
    """プロセス内で 1 つだけ生成する Markdown → HTML 変換器。"""
    global _renderer
    if _renderer is None:
        _renderer = MarkdownHtmlRenderer()
    return _renderer


class GitHubCommentEditor(QWidget):
    """書式ツールバーと Write / Preview タブを備えた Markdown 入力欄。"""

    textChanged = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        self.editor = QPlainTextEdit()
        self.editor.textChanged.connect(self.textChanged)

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)

        write_pane = QWidget()
        write_layout = QVBoxLayout(write_pane)
        write_layout.setContentsMargins(0, 0, 0, 0)
        write_layout.setSpacing(2)
        write_layout.addLayout(self._build_toolbar())
        write_layout.addWidget(self.editor, stretch=1)

        self.tabs = QTabWidget()
        self.tabs.addTab(write_pane, self.tr("編集"))
        self.tabs.addTab(self.preview, self.tr("プレビュー"))
        self.tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs, stretch=1)

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        # tr() にはリテラルを渡す（変数渡しだと lupdate が抽出できない）
        specs = (
            ("bold", self.tr("太字"), "**B**"),
            ("italic", self.tr("斜体"), "*I*"),
            ("heading", self.tr("見出し"), "H"),
            ("quote", self.tr("引用"), "❝"),
            ("code", self.tr("コード"), "</>"),
            ("link", self.tr("リンク"), "🔗"),
            ("bullet", self.tr("箇条書き"), "•"),
            ("number", self.tr("番号付きリスト"), "1."),
            ("task", self.tr("タスクリスト"), "☑"),
        )
        self.format_buttons: dict[str, QToolButton] = {}
        for key, label, glyph in specs:
            button = QToolButton()
            button.setText(glyph)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.clicked.connect(lambda _checked=False, k=key: self.apply_format(k))
            row.addWidget(button)
            self.format_buttons[key] = button
        row.addStretch(1)
        return row

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def text(self) -> str:
        """入力中の Markdown 原文を返す。"""
        return self.editor.toPlainText()

    def set_text(self, text: str) -> None:
        """Markdown 原文を設定する。"""
        self.editor.setPlainText(text or "")

    def clear(self) -> None:
        self.editor.setPlainText("")

    def set_placeholder_text(self, text: str) -> None:
        self.editor.setPlaceholderText(text)

    def set_read_only(self, read_only: bool) -> None:
        """入力欄と書式ボタンの編集可否を切り替える（プレビューは残す）。"""
        self.editor.setReadOnly(read_only)
        for button in self.format_buttons.values():
            button.setEnabled(not read_only)

    def show_write(self) -> None:
        self.tabs.setCurrentIndex(0)

    def show_preview(self) -> None:
        self.tabs.setCurrentIndex(1)

    def preview_html(self) -> str:
        """プレビューに表示中の HTML（テスト用）。"""
        return self.preview.toHtml()

    def apply_format(self, key: str) -> None:
        """書式記法を選択範囲またはキャレット位置へ挿入する。"""
        if self.editor.isReadOnly():
            return
        if key in _WRAP_ACTIONS:
            self._apply_wrap(*_WRAP_ACTIONS[key])
        elif key in _LINE_PREFIXES:
            self._apply_line_prefix(_LINE_PREFIXES[key])
        elif key == "link":
            self._apply_link()

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self._render_preview()

    def _render_preview(self) -> None:
        self.preview.setHtml(_shared_renderer().render_body(self.text()))

    def _apply_wrap(self, prefix: str, suffix: str) -> None:
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        if cursor.hasSelection():
            selected = cursor.selectedText().replace("\u2029", "\n")
            cursor.insertText(f"{prefix}{selected}{suffix}")
        else:
            cursor.insertText(f"{prefix}{suffix}")
            cursor.setPosition(cursor.position() - len(suffix))
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)

    def _apply_link(self) -> None:
        cursor = self.editor.textCursor()
        label = cursor.selectedText().replace("\u2029", "\n") if cursor.hasSelection() else ""
        cursor.beginEditBlock()
        cursor.insertText(f"[{label}]({_LINK_PLACEHOLDER})")
        cursor.endEditBlock()
        end = cursor.position() - 1
        cursor.setPosition(end - len(_LINK_PLACEHOLDER))
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)

    def _apply_line_prefix(self, prefix: str) -> None:
        cursor = self.editor.textCursor()
        document = self.editor.document()
        first = document.findBlock(cursor.selectionStart())
        last = document.findBlock(cursor.selectionEnd())
        cursor.beginEditBlock()
        block = first
        while block.isValid():
            edit = QTextCursor(block)
            edit.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            edit.insertText(prefix)
            if block.blockNumber() >= last.blockNumber():
                break
            block = block.next()
        cursor.endEditBlock()
