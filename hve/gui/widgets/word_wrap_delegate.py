"""hve.gui.widgets.word_wrap_delegate — QTreeWidget / QTreeView 用の複数行折り返し描画 Delegate。

ワークベンチの「作業状況」ツリー（ActivityStatusWidget）で、
長いテキストを横スクロールさせず複数行に折り返して表示するための ``QStyledItemDelegate``。

設計:
    - ``sizeHint()`` で利用可能な列幅から ``QTextDocument`` を用いて必要行数を計算する。
    - ``paint()`` で ``QAbstractTextDocumentLayout.PaintContext`` を用い、選択時の
      テキスト色を ``palette`` 経由で正しく反映する。
    - 選択ハイライト（``QStyle.StateFlag.State_Selected``）はスタイル既定の背景描画に委譲。

Notes:
    - ``QTreeWidget.setUniformRowHeights(False)`` と併用すること。
    - ``setItemDelegate`` で全列に適用する。
    - 日本語の禁則処理は Qt 標準の ``WrapAtWordBoundaryOrAnywhere`` に従う
      （行頭禁則文字に対する独自処理は未実装）。
    - 動作確認: PySide6 6.x の ``QTreeWidget`` 実装で ``option.rect.width()`` が
      インデント込みの item rect 幅を返すことに依拠している。
"""

from __future__ import annotations

from typing import Optional, Union

from PySide6.QtCore import QModelIndex, QObject, QPersistentModelIndex, QSize
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QPainter,
    QPalette,
    QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

_IndexT = Union[QModelIndex, QPersistentModelIndex]


class WordWrapDelegate(QStyledItemDelegate):
    """テキストを複数行に折り返して描画する Delegate。"""

    # 行内パディング（QTreeWidget::item の CSS padding 0px 4px に合わせる）
    _PAD_H = 4
    _PAD_V = 0

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

    # ------------------------------------------------------------------
    # 共通: テキストを描画用 QTextDocument に変換
    # ------------------------------------------------------------------

    def _make_document(
        self, text: str, width: int, option: QStyleOptionViewItem
    ) -> QTextDocument:
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        doc.setDefaultTextOption(text_option)
        # textWidth はパディング分を差し引いた幅
        effective = max(1, width - self._PAD_H * 2)
        doc.setTextWidth(effective)
        doc.setPlainText(text)
        return doc

    # ------------------------------------------------------------------
    # サイズ計算
    # ------------------------------------------------------------------

    def sizeHint(self, option: QStyleOptionViewItem, index: _IndexT) -> QSize:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        text = opt.text or ""
        width = opt.rect.width() if opt.rect.width() > 0 else 200
        doc = self._make_document(text, width, opt)
        h = int(doc.size().height()) + self._PAD_V * 2
        # 縦間隔縮小のため leading 分を含まない height() を採用 (lineSpacing より 1〜2px 小)。
        fm_h = opt.fontMetrics.height() + self._PAD_V * 2
        return QSize(width, max(h, fm_h))

    # ------------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: _IndexT,
    ) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        painter.save()
        # 下方ペインへのはみ出しを防ぐためクリップする。
        painter.setClipRect(opt.rect)

        # 背景（選択 / ホバー）はスタイル既定で描画する。
        # text は自前で折り返し描画するためスタイルには描かせない。
        text = opt.text or ""
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(
                QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget
            )
        else:
            if opt.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(opt.rect, opt.palette.highlight())

        # テキスト色: 選択時は HighlightedText、それ以外は Text
        if opt.state & QStyle.StateFlag.State_Selected:
            text_color = opt.palette.highlightedText().color()
        else:
            text_color = opt.palette.text().color()

        doc = self._make_document(text, opt.rect.width(), opt)

        painter.translate(opt.rect.left() + self._PAD_H, opt.rect.top() + self._PAD_V)
        # PaintContext.palette のテキスト色を上書きして描画する。
        # ``painter.setPen`` は QTextDocument の描画では使われないため、
        # palette 経由で色を反映するのが Qt 公式の推奨方式。
        ctx = QAbstractTextDocumentLayout.PaintContext()
        palette = QPalette(opt.palette)
        palette.setColor(QPalette.ColorRole.Text, text_color)
        ctx.palette = palette
        doc.documentLayout().draw(painter, ctx)

        painter.restore()
