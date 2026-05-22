"""hve.gui.header_bar — 3 ステップの進捗バー (Header)。

設計書 §4 対応。

機能:
  - 2 ステップ（ワークフローの選択 / 実行）の現在位置を表示
  - 完了済み (●塗りつぶし) / 現在 (○太枠) / 未着手 (○細枠) を視覚的に区別
  - 各ステップに日本語ラベル表示
  - `set_current_step(int)` で外部から状態を制御
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QCoreApplication, QRect, QT_TRANSLATE_NOOP
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


# ステップ ID と日本語ラベル。モジュールレベルのため QT_TRANSLATE_NOOP でマーク。
STEP_LABELS: Tuple[Tuple[str, str], ...] = (
    ("workflow", QT_TRANSLATE_NOOP("HeaderBar", "① ワークフローの選択")),
    ("workbench", QT_TRANSLATE_NOOP("HeaderBar", "② 実行")),
)

# 描画色
_COLOR_DONE = QColor("#1976d2")        # 完了（青）
_COLOR_CURRENT = QColor("#1976d2")     # 現在（青、太枠）
_COLOR_PENDING = QColor("#bdbdbd")     # 未着手（グレー）
_COLOR_ABORTED = QColor("#d32f2f")     # 中止（赤、fatal 時）
_COLOR_LINE_DONE = QColor("#1976d2")
_COLOR_LINE_PENDING = QColor("#e0e0e0")
_COLOR_LABEL_CURRENT = QColor("#0d47a1")
_COLOR_LABEL_OTHER = QColor("#424242")

# サイズ
_CIRCLE_RADIUS = 14
_HEIGHT = 80


class HeaderBar(QWidget):
    """3 ステップ進捗バー。

    Args:
        parent: 親ウィジェット（通常 MainWindow の中央ウィジェット）

    Usage:
        bar = HeaderBar()
        bar.set_current_step(0)  # 0=workflow, 1=workbench
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_step = 0  # 0..2
        self._all_completed = False
        self._aborted = False  # fatal で実行が中止された際に True。赤 ✕ と表示する。
        self.setFixedHeight(_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # ----------------------------------------------------------
    # 公開 API
    # ----------------------------------------------------------

    def set_current_step(self, step_index: int) -> None:
        """現在のステップを設定する（0/1/2）。範囲外は丸める。

        set_current_step を呼ぶと all_completed / aborted フラグはリセットされる。
        """
        step_index = max(0, min(step_index, len(STEP_LABELS) - 1))
        needs_update = (
            (step_index != self._current_step)
            or self._all_completed
            or self._aborted
        )
        self._all_completed = False
        self._aborted = False
        self._current_step = step_index
        if needs_update:
            self.update()

    def mark_completed(self, completed: bool = True) -> None:
        """全ステップを完了状態として表示する（最終ステップも ●✓ 化）。"""
        if completed == self._all_completed and not self._aborted:
            return
        self._all_completed = completed
        if completed:
            self._aborted = False
        self.update()

    def mark_aborted(self, aborted: bool = True) -> None:
        """致命的エラー等で実行が中止された状態として表示する。

        現在ステップを赤い ✕ で表示し、`mark_completed` とは区別される。
        完了と中止は排他的。
        """
        if aborted == self._aborted:
            return
        self._aborted = aborted
        if aborted:
            self._all_completed = False
        self.update()

    def is_all_completed(self) -> bool:
        return self._all_completed

    def is_aborted(self) -> bool:
        return self._aborted

    def current_step(self) -> int:
        return self._current_step

    def step_count(self) -> int:
        return len(STEP_LABELS)

    # ----------------------------------------------------------
    # 描画
    # ----------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        n = len(STEP_LABELS)

        # ラベル文字列を先に解決し、フォントメトリクスで実幅を測る
        label_font = QFont()
        label_font.setPointSize(9)
        # 現在ステップは太字なので、太字での幅も考慮（最大幅を採用）
        label_font_bold = QFont(label_font)
        label_font_bold.setBold(True)
        fm_normal = QFontMetrics(label_font)
        fm_bold = QFontMetrics(label_font_bold)
        resolved_labels: List[str] = [
            QCoreApplication.translate("HeaderBar", STEP_LABELS[i][1]) for i in range(n)
        ]
        label_widths: List[int] = [
            max(fm_normal.horizontalAdvance(s), fm_bold.horizontalAdvance(s)) + 12
            for s in resolved_labels
        ]

        # 端ラベルがはみ出さないようマージンを動的に決定
        edge_margin = max(40, (label_widths[0] // 2) + 8, (label_widths[-1] // 2) + 8)
        left_margin = edge_margin
        right_margin = edge_margin
        usable = max(w - left_margin - right_margin, n * 60)
        if n > 1:
            step_dx = usable // (n - 1)
        else:
            step_dx = 0
        # 全体を widget 内で水平中央寄せ（極小幅で左に溢れないようクランプ）
        total_span = step_dx * (n - 1)
        start_x = max(2, (w - total_span) // 2)
        centers_x: List[int] = [start_x + step_dx * i for i in range(n)]
        center_y = h // 2 - 8  # 円はやや上寄せ、下にラベル

        # --- 1) 接続線 ---
        for i in range(n - 1):
            done = self._all_completed or i < self._current_step
            color = _COLOR_LINE_DONE if done else _COLOR_LINE_PENDING
            x1 = centers_x[i] + _CIRCLE_RADIUS
            x2 = centers_x[i + 1] - _CIRCLE_RADIUS
            pen = QPen(color, 3)
            painter.setPen(pen)
            painter.drawLine(x1, center_y, x2, center_y)

        # --- 2) 円 ---
        for i, cx in enumerate(centers_x):
            is_aborted_current = self._aborted and i == self._current_step
            if is_aborted_current:
                # 中止: 赤塗りつぶし
                painter.setBrush(_COLOR_ABORTED)
                painter.setPen(QPen(_COLOR_ABORTED, 2))
            elif self._all_completed or i < self._current_step:
                # 完了: 塗りつぶし
                painter.setBrush(_COLOR_DONE)
                painter.setPen(QPen(_COLOR_DONE, 2))
            elif i == self._current_step:
                # 現在: 太枠
                painter.setBrush(QColor("#ffffff"))
                painter.setPen(QPen(_COLOR_CURRENT, 3))
            else:
                # 未着手: 細枠
                painter.setBrush(QColor("#ffffff"))
                painter.setPen(QPen(_COLOR_PENDING, 2))
            painter.drawEllipse(
                cx - _CIRCLE_RADIUS,
                center_y - _CIRCLE_RADIUS,
                _CIRCLE_RADIUS * 2,
                _CIRCLE_RADIUS * 2,
            )

            # 完了マーク（✓）または中止マーク（✗）
            if is_aborted_current:
                painter.setPen(QPen(QColor("#ffffff"), 2))
                font = painter.font()
                font.setBold(True)
                font.setPointSize(12)
                painter.setFont(font)
                rect = QRect(
                    cx - _CIRCLE_RADIUS,
                    center_y - _CIRCLE_RADIUS,
                    _CIRCLE_RADIUS * 2,
                    _CIRCLE_RADIUS * 2,
                )
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "✗")
            elif self._all_completed or i < self._current_step:
                painter.setPen(QPen(QColor("#ffffff"), 2))
                font = painter.font()
                font.setBold(True)
                font.setPointSize(12)
                painter.setFont(font)
                rect = QRect(
                    cx - _CIRCLE_RADIUS,
                    center_y - _CIRCLE_RADIUS,
                    _CIRCLE_RADIUS * 2,
                    _CIRCLE_RADIUS * 2,
                )
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "✓")

        # --- 3) ラベル ---
        label_y = center_y + _CIRCLE_RADIUS + 6
        for i, cx in enumerate(centers_x):
            label = resolved_labels[i]
            color = _COLOR_LABEL_CURRENT if i == self._current_step else _COLOR_LABEL_OTHER
            painter.setPen(QPen(color, 1))
            font = label_font_bold if i == self._current_step else label_font
            painter.setFont(font)
            # 実測幅を使い、widget 内に収まる範囲で中央寄せ
            text_width = label_widths[i]
            x = cx - text_width // 2
            # widget 端でクリップされないように左右へクランプ
            if x < 2:
                x = 2
            if x + text_width > w - 2:
                x = max(2, w - 2 - text_width)
            rect = QRect(x, label_y, text_width, 24)
            painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)

        painter.end()
