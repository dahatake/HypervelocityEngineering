"""hve.gui.widgets.chat_transcript — 実行ジョブタブの会話ビュー（FR-GUI-18）。

送信メッセージ・ACK・GUI 通知・宛先の実行ログを 1 本の時系列列へ並べる。
会話バブルにしてよいのは HVE 自身が発生源の要素だけで、実行ログは生ログのまま
提示し、行を解析して発話者・役割・ターン境界を推定しない（FR-GUI-13）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple, Union

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..fonts import preferred_log_font
from .wrap_helpers import apply_cjk_wrap

__all__ = ["ChatTranscriptView"]

_LOG_POINT_SIZE = 10


class _UserEntry(QFrame):
    """利用者が実行中ジョブへ送ったメッセージと、その ACK 状態。"""

    def __init__(self, body: str, action_label: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("hveRole", "noteBox")
        self._body = body
        self._action_label = action_label
        self._status = ""
        self._detail = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(0)
        self._label = QLabel(self.text(), self)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._label)

    def set_ack(self, status: str, detail: str = "") -> None:
        self._status = status
        self._detail = detail
        self._label.setText(self.text())

    def body(self) -> str:
        return self._body

    def text(self) -> str:
        text = f"[{self._action_label}] {self._body}"
        if self._status:
            text += f"  → {self._status}"
            if self._detail:
                text += f" ({self._detail})"
        return text


class _NoticeEntry(QLabel):
    """GUI 自身が出す通知（送信不可・上限超過など）。"""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setProperty("hveRole", "description")
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)


class _LogEntry(QPlainTextEdit):
    """宛先の実行ログ。外側の 1 本のスクロールに合わせて高さを追従させる。"""

    def __init__(self, font: QFont, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFont(font)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_cjk_wrap(self)
        self._applied_height = -1
        # documentSizeChanged は setPlainText でしか発火しないため、1 行追記を拾う
        # contentsChanged も接続する（未接続だと実行中のログが 1 行分に潰れる）。
        layout = self.document().documentLayout()
        if layout is not None:
            layout.documentSizeChanged.connect(self._sync_height)
        self.document().contentsChanged.connect(self._sync_height)
        self._sync_height()

    def _sync_height(self, *_args: object) -> None:
        layout = self.document().documentLayout()
        lines = 1
        if layout is not None:
            lines = max(1, int(round(layout.documentSize().height())))
        margin = int(self.document().documentMargin())
        height = lines * self.fontMetrics().lineSpacing() + 2 * margin + 2 * self.frameWidth()
        if height != self._applied_height:
            self._applied_height = height
            self.setFixedHeight(height)


_EntryWidget = Union[_UserEntry, _NoticeEntry, _LogEntry]


class ChatTranscriptView(QScrollArea):
    """実行ジョブタブの会話ビュー。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAccessibleName(self.tr("実行ジョブの会話"))
        self._log_accessible_name = self.tr("選択したジョブの実行ログ")
        self._log_font = preferred_log_font(_LOG_POINT_SIZE)

        self._body = QWidget(self)
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(6)
        self._layout.addStretch(1)
        self.setWidget(self._body)

        self._entries: List[Tuple[str, _EntryWidget]] = []
        self._user_entries: Dict[str, _UserEntry] = {}

    # ------------------------------------------------------------------
    # 追記
    # ------------------------------------------------------------------

    def append_user(self, text: str, *, action_label: str, request_id: str) -> None:
        entry = _UserEntry(text, action_label, self._body)
        self._add("user", entry)
        self._user_entries[request_id] = entry

    def append_notice(self, text: str) -> None:
        self._add("notice", _NoticeEntry(text, self._body))

    def append_log(self, line: str) -> None:
        entry = self._trailing_log_entry()
        if entry is None:
            entry = _LogEntry(self._log_font, self._body)
            entry.setAccessibleName(self._log_accessible_name)
            self._add("log", entry)
            entry.setPlainText(line)
        else:
            entry.appendPlainText(line)
        self._follow_bottom()

    def set_log_snapshot(self, lines: Sequence[str]) -> None:
        """会話ビューを破棄して、宛先のログスナップショットだけを表示する。"""
        self.clear()
        lines = list(lines)
        if not lines:
            return
        entry = _LogEntry(self._log_font, self._body)
        entry.setAccessibleName(self._log_accessible_name)
        self._add("log", entry)
        entry.setPlainText("\n".join(lines))
        self._follow_bottom()

    def update_ack(self, request_id: str, status: str, detail: str = "") -> bool:
        """対応する送信バブルへ ACK 状態を反映する。未知の要求 ID なら False。"""
        entry = self._user_entries.get(request_id)
        if entry is None:
            return False
        entry.set_ack(status, detail)
        return True

    def clear(self) -> None:
        for _kind, widget in self._entries:
            self._layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        self._entries.clear()
        self._user_entries.clear()

    # ------------------------------------------------------------------
    # 参照
    # ------------------------------------------------------------------

    def entry_kinds(self) -> List[str]:
        return [kind for kind, _widget in self._entries]

    def plain_text(self) -> str:
        return "\n".join(self._entry_text(widget) for _kind, widget in self._entries)

    def log_font(self) -> QFont:
        return self._log_font

    # ------------------------------------------------------------------
    # ターン（利用者の送信メッセージ）
    # ------------------------------------------------------------------

    def user_turn_count(self) -> int:
        return len(self._turn_widgets())

    def user_turn_text(self, index: int) -> str:
        """送信本文だけを返す（送信方法・ACK を含まない）。範囲外は空文字列。"""
        turns = self._turn_widgets()
        if not 0 <= index < len(turns):
            return ""
        return turns[index].body()

    def current_user_turn_index(self) -> int:
        """スクロール位置から現在ターンを返す。ターンが無ければ ``-1``。"""
        turns = self._turn_widgets()
        if not turns:
            return -1
        bar = self.verticalScrollBar()
        if bar is None:
            return 0
        top = bar.value()
        maximum = bar.maximum()
        index = 0
        for i, widget in enumerate(turns):
            # 上端へ寄せきれないターンは上限位置で判定し、移動先と番号を一致させる。
            if min(widget.y(), maximum) <= top:
                index = i
        return index

    def scroll_to_user_turn(self, index: int) -> bool:
        """指定ターンをビューポート上端へ寄せる。範囲外なら ``False``。"""
        turns = self._turn_widgets()
        if not 0 <= index < len(turns):
            return False
        bar = self.verticalScrollBar()
        if bar is None:
            return False
        bar.setValue(turns[index].y())
        return True

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _turn_widgets(self) -> List[_UserEntry]:
        return [widget for _kind, widget in self._entries if isinstance(widget, _UserEntry)]

    @staticmethod
    def _entry_text(widget: _EntryWidget) -> str:
        if isinstance(widget, _LogEntry):
            return widget.toPlainText()
        return widget.text()

    def _add(self, kind: str, widget: _EntryWidget) -> None:
        self._layout.insertWidget(self._layout.count() - 1, widget)
        self._entries.append((kind, widget))
        if kind != "log":
            self._follow_bottom()

    def _trailing_log_entry(self) -> Optional[_LogEntry]:
        if self._entries:
            widget = self._entries[-1][1]
            if isinstance(widget, _LogEntry):
                return widget
        return None

    def _follow_bottom(self) -> None:
        """末尾を見ていたときだけ追従する（読み返し中はスクロール位置を保つ）。"""
        bar = self.verticalScrollBar()
        if bar is None or bar.value() < bar.maximum():
            return
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        try:
            bar = self.verticalScrollBar()
        except RuntimeError:
            # 遅延実行までにビューが破棄された場合。
            return
        if bar is not None:
            bar.setValue(bar.maximum())
