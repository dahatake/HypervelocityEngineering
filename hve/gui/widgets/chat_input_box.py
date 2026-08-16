"""hve.gui.widgets.chat_input_box — 実行ジョブタブの入力ボックス（FR-GUI-18）。

複数行入力・`Enter` 送信 / `Shift+Enter` 改行・コンテキスト添付チップ・送信方法
セレクタを 1 つの枠へまとめる。添付は選択されたパスだけを送信本文へ列挙し、
ファイル本文は読み取らない。ファイル選択ダイアログは所有者（パネル）が開く。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from hve.job_interaction_ipc import ACTION_QUEUE, ACTION_STEER, ACTION_STOP_AND_SEND

from .wrap_helpers import apply_cjk_wrap

__all__ = ["ChatInputBox"]

_MAX_VISIBLE_LINES = 8
_ATTACHMENT_HEADING = "添付パス:"


class _ChatTextEdit(QPlainTextEdit):
    """`Enter` で送信し、`Shift+Enter` で改行する複数行入力。"""

    submitted = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self.submitted.emit()
                event.accept()
                return
        super().keyPressEvent(event)


class _AttachmentChip(QFrame):
    """添付 1 件を表すチップ。`×` で個別に取り消せる。"""

    removed = Signal(str)

    def __init__(self, path: str, remove_tooltip: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("hveRole", "bordered")
        self._path = path

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 2, 2)
        layout.setSpacing(4)
        label = QLabel(path.replace("\\", "/").rsplit("/", 1)[-1] or path, self)
        label.setToolTip(path)
        layout.addWidget(label)

        self._close_btn = QToolButton(self)
        self._close_btn.setText("×")
        self._close_btn.setAutoRaise(True)
        self._close_btn.setToolTip(remove_tooltip)
        self._close_btn.setAccessibleName(f"{remove_tooltip}: {path}")
        self._close_btn.clicked.connect(lambda: self.removed.emit(self._path))
        layout.addWidget(self._close_btn)

    def path(self) -> str:
        return self._path

    def close_button(self) -> QToolButton:
        return self._close_btn


class ChatInputBox(QWidget):
    """実行ジョブタブの入力枠。"""

    submitted = Signal()
    attach_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("hveRole", "bordered")
        self._attachments: List[str] = []
        self._chips: List[_AttachmentChip] = []
        self._sendable = True
        self._remove_tooltip = self.tr("添付を外す")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._chip_row = QWidget(self)
        self._chip_layout = QHBoxLayout(self._chip_row)
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(4)
        self._chip_layout.addStretch(1)
        self._chip_row.hide()
        layout.addWidget(self._chip_row)

        self._edit = _ChatTextEdit(self)
        self._edit.setAccessibleName(self.tr("実行中ジョブへ送るメッセージ"))
        self._edit.setPlaceholderText(self.tr("実行中のステップへ送るメッセージを入力..."))
        apply_cjk_wrap(self._edit)
        self._edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._edit.submitted.connect(self._on_submit)
        self._edit.textChanged.connect(self._sync_height)
        layout.addWidget(self._edit)

        tool_row = QHBoxLayout()
        tool_row.setSpacing(4)
        self._attach_btn = QToolButton(self)
        self._attach_btn.setText("+")
        self._attach_btn.setAutoRaise(True)
        self._attach_btn.setAccessibleName(self.tr("コンテキストを添付"))
        self._attach_btn.setToolTip(self.tr("コンテキストを添付"))
        self._attach_btn.clicked.connect(self.attach_requested)
        tool_row.addWidget(self._attach_btn)

        self._action_combo = QComboBox(self)
        self._action_combo.setObjectName("ChatInputActionCombo")
        self._action_combo.setAccessibleName(self.tr("送信方法"))
        self._action_combo.addItem(self.tr("キューに追加"), ACTION_QUEUE)
        self._action_combo.addItem(self.tr("いま割り込む"), ACTION_STEER)
        self._action_combo.addItem(self.tr("中断して送信"), ACTION_STOP_AND_SEND)
        tool_row.addWidget(self._action_combo)
        tool_row.addStretch(1)

        self._send_btn = QPushButton(self.tr("送信"), self)
        self._send_btn.setAccessibleName(self.tr("実行中ジョブへ送信"))
        self._send_btn.clicked.connect(self._on_submit)
        tool_row.addWidget(self._send_btn)
        layout.addLayout(tool_row)

        self._sync_height()

    # ------------------------------------------------------------------
    # 本文
    # ------------------------------------------------------------------

    def text(self) -> str:
        return self._edit.toPlainText()

    def set_text(self, text: str) -> None:
        self._edit.setPlainText(text)
        self._edit.moveCursor(QTextCursor.MoveOperation.End)

    def clear(self) -> None:
        self._edit.clear()
        self.clear_attachments()

    def compose_text(self) -> str:
        """本文へ添付パスを列挙した送信本文を返す（ファイル本文は読まない）。"""
        body = self.text()
        if not self._attachments:
            return body
        lines = [body.rstrip(), "", _ATTACHMENT_HEADING]
        lines.extend(f"- {path}" for path in self._attachments)
        return "\n".join(lines).lstrip("\n")

    # ------------------------------------------------------------------
    # 添付
    # ------------------------------------------------------------------

    def attachments(self) -> Tuple[str, ...]:
        return tuple(self._attachments)

    def attachment_chips(self) -> Tuple[_AttachmentChip, ...]:
        return tuple(self._chips)

    def add_attachment(self, path: str) -> bool:
        path = str(path)
        if not path or path in self._attachments:
            return False
        self._attachments.append(path)
        chip = _AttachmentChip(path, self._remove_tooltip, self._chip_row)
        chip.removed.connect(self.remove_attachment)
        self._chip_layout.insertWidget(self._chip_layout.count() - 1, chip)
        self._chips.append(chip)
        self._chip_row.show()
        return True

    def remove_attachment(self, path: str) -> bool:
        if path not in self._attachments:
            return False
        self._attachments.remove(path)
        for chip in list(self._chips):
            if chip.path() == path:
                self._chips.remove(chip)
                self._chip_layout.removeWidget(chip)
                chip.setParent(None)
                chip.deleteLater()
        if not self._attachments:
            self._chip_row.hide()
        return True

    def clear_attachments(self) -> None:
        for path in list(self._attachments):
            self.remove_attachment(path)

    # ------------------------------------------------------------------
    # 送信方法
    # ------------------------------------------------------------------

    def action_labels(self) -> List[str]:
        return [self._action_combo.itemText(i) for i in range(self._action_combo.count())]

    def current_action(self) -> str:
        return str(self._action_combo.currentData() or ACTION_QUEUE)

    def select_action(self, label: str) -> None:
        index = self._action_combo.findText(label)
        if index >= 0:
            self._action_combo.setCurrentIndex(index)

    def action_label(self, action: str) -> str:
        index = self._action_combo.findData(action)
        return self._action_combo.itemText(index) if index >= 0 else action

    def set_sendable(self, sendable: bool) -> None:
        self._sendable = bool(sendable)
        self._edit.setEnabled(self._sendable)
        self._action_combo.setEnabled(self._sendable)
        self._attach_btn.setEnabled(self._sendable)
        self._send_btn.setEnabled(self._sendable)

    # ------------------------------------------------------------------
    # ウィジェット参照
    # ------------------------------------------------------------------

    def text_edit(self) -> QPlainTextEdit:
        return self._edit

    def action_combo(self) -> QComboBox:
        return self._action_combo

    def send_button(self) -> QPushButton:
        return self._send_btn

    def attach_button(self) -> QToolButton:
        return self._attach_btn

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _on_submit(self) -> None:
        if not self._sendable or not self.compose_text().strip():
            return
        self.submitted.emit()

    def _sync_height(self) -> None:
        lines = min(max(1, self._edit.document().blockCount()), _MAX_VISIBLE_LINES)
        margin = int(self._edit.document().documentMargin())
        height = (
            lines * self._edit.fontMetrics().lineSpacing()
            + 2 * margin
            + 2 * self._edit.frameWidth()
        )
        self._edit.setMinimumHeight(height)
        self._edit.setMaximumHeight(height)
