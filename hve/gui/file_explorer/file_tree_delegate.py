"""hve.gui.file_explorer.file_tree_delegate — ファイルツリーの行末バッジ描画。

``FileChangeTracker`` の状態を参照し、NEW = 緑、MODIFIED = 橙の小さな ●
を行末に描画する ``QStyledItemDelegate``。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from .file_change_tracker import ChangeState, FileChangeTracker
from .multi_root_model import PathRole


_BADGE_DIAMETER = 8
_BADGE_MARGIN = 6  # 行右端からの距離


_COLOR_NEW = QColor("#22aa55")
_COLOR_MODIFIED = QColor("#dd8800")


class FileTreeDelegate(QStyledItemDelegate):
    """``FileChangeTracker`` の状態を行末バッジで表示するデリゲート。"""

    def __init__(self, tracker: FileChangeTracker, parent=None) -> None:
        super().__init__(parent)
        self._tracker = tracker

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        super().paint(painter, option, index)
        path = index.data(PathRole)
        if not isinstance(path, Path):
            return
        state = self._tracker.state_of(path)
        if state == ChangeState.NORMAL:
            return

        color = _COLOR_NEW if state == ChangeState.NEW else _COLOR_MODIFIED
        rect = option.rect
        bx = rect.right() - _BADGE_MARGIN - _BADGE_DIAMETER
        by = rect.top() + (rect.height() - _BADGE_DIAMETER) // 2
        badge_rect = QRect(bx, by, _BADGE_DIAMETER, _BADGE_DIAMETER)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(badge_rect)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        # バッジ表示分の幅を確保
        size.setWidth(size.width() + _BADGE_DIAMETER + _BADGE_MARGIN * 2)
        # 行高さを font metrics ベースで圧縮し、無駄な余白を排除
        # ただしアイコンサイズ (16px) を下回らないようにする
        fm_height = option.fontMetrics.height()
        size.setHeight(max(fm_height + 2, 16))
        return size
