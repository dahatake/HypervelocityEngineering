"""hve.gui.tasktre_widget — TaskTree ウィジェット。"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .workbench_state import WorkbenchState, SimpleTaskNode


_STATUS_GLYPH = {
    "pending": "⊳",      # pending
    "running": "▶",      # running
    "done": "●",         # done
    "failed": "✗",       # failed
    "skipped": "⊘",      # skipped
}

_STATUS_COLOR = {
    "pending": "color: #888;",
    "running": "color: #b58900; font-weight: bold;",
    "done": "color: #2aa198; font-weight: bold;",
    "failed": "color: #dc322f; font-weight: bold;",
    "skipped": "color: #6c71c4;",
}


class TaskTreeWidget(QWidget):
    """TaskTree ペイン: セッションツリーを階層チェックボックスで表示（閲覧専用）。

    Step 1 の `WorkflowSelectPage` と同じチェックボックス形式の見た目に揃える。
    チェックボックスは閲覧用（読み取り専用）であり、ユーザー操作では変化しない。
    各ノードのチェック状態は status に応じて自動設定される:
        - skipped       → OFF
        - その他全状態   → ON
    """

    def __init__(self, state: WorkbenchState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._max_lines = 10

        # ヘッダ
        header = QLabel(self.tr("セッションツリー"))
        header.setStyleSheet("font-weight: bold; padding: 2px;")

        # チェックボックス階層の入る内側ウィジェット
        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(4, 4, 4, 4)
        self._inner_layout.setSpacing(2)
        self._inner_layout.addStretch()

        # スクロール対応
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._inner)
        self._scroll.setWidgetResizable(True)
        self._scroll.setMaximumHeight(180)

        # 末尾サマリ（"(N nodes)"）
        self._summary = QLabel("")
        self._summary.setStyleSheet("color: #666; padding: 2px;")

        # 既存ノードキャッシュ: id -> (checkbox, label)
        self._rows: Dict[str, tuple] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(header)
        layout.addWidget(self._scroll)
        layout.addWidget(self._summary)

        self._update()

    # ------------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------------

    def _make_row(self, node: SimpleTaskNode, indent: int) -> QWidget:
        cb = QCheckBox()
        cb.setEnabled(False)  # 閲覧専用（Q4）
        cb.setChecked(node.status != "skipped")

        glyph = _STATUS_GLYPH.get(node.status, "?")
        elapsed = node.elapsed_str(time.monotonic())
        label_text = f"{glyph}  {node.title}  ({elapsed})  [{node.status}]"
        if node.current_activity:
            label_text += f" — {node.current_activity}"

        label = QLabel(label_text)
        label.setStyleSheet(_STATUS_COLOR.get(node.status, ""))

        row_layout = QHBoxLayout()
        # インデント表現: 16px * 深さ
        row_layout.setContentsMargins(8 + indent * 16, 0, 0, 0)
        row_layout.setSpacing(4)
        row_layout.addWidget(cb)
        row_layout.addWidget(label)
        row_layout.addStretch()

        row_w = QWidget()
        row_w.setLayout(row_layout)
        return row_w

    def _clear_rows(self) -> None:
        # stretch (末尾) は残す
        while self._inner_layout.count() > 1:
            item = self._inner_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._rows.clear()

    def _update(self) -> None:
        self._clear_rows()

        nodes_flat: List[tuple] = []  # (node, indent)

        def visit(node: SimpleTaskNode, indent: int = 0) -> None:
            nodes_flat.append((node, indent))
            for child in node.children:
                visit(child, indent + 1)

        if self.state.task_tree.root is not None:
            visit(self.state.task_tree.root)

        # スクロール offset 反映（既存スクロール API 互換）
        offset = max(0, int(getattr(self.state, "task_tree_scroll", 0) or 0))
        total = len(nodes_flat)
        if total > self._max_lines:
            max_off = max(0, total - self._max_lines)
            offset = min(offset, max_off)
            start = max(0, total - self._max_lines - offset)
            visible = nodes_flat[start : start + self._max_lines]
        else:
            visible = nodes_flat

        # stretch の前に挿入
        insert_at = max(0, self._inner_layout.count() - 1)
        for node, indent in visible:
            row = self._make_row(node, indent)
            self._inner_layout.insertWidget(insert_at, row)
            insert_at += 1
            self._rows[node.id] = (row,)

        total_nodes = self.state.task_tree_total_nodes()
        self._summary.setText(f"({total_nodes} nodes)" if total_nodes else "")

    def update_state(self, state: WorkbenchState) -> None:
        self.state = state
        self._update()

    def refresh(self) -> None:
        """周期的に呼び出して経過時間を更新。"""
        self._update()


class UserInteractionWidget(QWidget):
    """UserInteraction ペイン: コマンド入力エリア + ヘルプ。"""

    def __init__(self, state: WorkbenchState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setStyleSheet("padding: 4px; font-size: 9pt; color: #666666;")
        self._update()

        header = QLabel(self.tr("入力エリア"))
        header.setStyleSheet("font-weight: bold; padding: 2px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(header)
        layout.addWidget(self._label)

    def _update(self) -> None:
        if self.state.all_done:
            text = "> /exit  （タスク完了：終了ボタンで終了）"
        else:
            text = (
                "Press `:` to enter command | /help | Esc to cancel"
                " | Scroll: ↑↓ ログ, [ ] 課題, { } ツリー, g/G top/bottom"
            )
        self._label.setText(text)

    def update_state(self, state: WorkbenchState) -> None:
        self.state = state
        self._update()

    def mark_done(self) -> None:
        self.state.mark_all_done()
        self._update()
