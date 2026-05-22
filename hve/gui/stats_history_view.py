"""hve.gui.stats_history_view — 「今回の実行履歴」タブビュー。

`WorkbenchState.stats_history` の `WorkflowStatsSnapshot` を QTreeWidget で表示する。
- 親行: Workflow（合計値）
- 子行: 各 Step（完了時のスナップショット）
- 列: Workflow/Step, Context, Model, 実行時間, Tools, Skills

リアルタイム更新:
- `stats_history_updated` シグナルを購読し、1 秒スロットルで再描画する。
- 関連シグナル（context_updated / tool_counts_updated / skill_counts_updated）も同様。

Tools / Skills は Top-5 + ``+N more`` 形式。セル D-click で全件ポップアップを表示する。
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHeaderView,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .workbench_state import (
    StepStatsSnapshot,
    WorkbenchState,
    WorkflowStatsSnapshot,
)


_DASH = "-"
_TOPN = 5
_THROTTLE_MS = 1000

# 列定義
COL_NAME = 0
COL_CONTEXT = 1
COL_MODEL = 2
COL_ELAPSED = 3
COL_TOOLS = 4
COL_SKILLS = 5
_COLUMN_HEADERS = (
    "Workflow / Step",
    "Context",
    "Model",
    "実行時間",
    "Tools",
    "Skills",
)


def _fmt_context(cur: Optional[int], lim: Optional[int]) -> str:
    if cur is None and lim is None:
        return _DASH
    c = int(cur or 0)
    l = int(lim or 0)
    if l <= 0:
        return f"{c:,}"
    pct = (c * 100) // l
    return f"{c:,} / {l:,} ({pct}%)"


def _fmt_elapsed(sec: Optional[float]) -> str:
    if sec is None:
        return _DASH
    sec = max(0, int(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_counts(counts: dict, top: int = _TOPN) -> str:
    if not counts:
        return _DASH
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    head = items[:top]
    rest = len(items) - len(head)
    text = ", ".join(f"{name}×{cnt}" for name, cnt in head)
    if rest > 0:
        text += f" +{rest} more"
    return text


def _full_counts_text(counts: dict) -> str:
    if not counts:
        return _DASH
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return "\n".join(f"{name}: {cnt}" for name, cnt in items)


def _agg_workflow_counts(workflow: WorkflowStatsSnapshot, attr: str) -> dict:
    """Step を跨いだツール/スキル集計（Workflow 合計）。"""
    total: dict = {}
    for st in workflow.steps:
        for k, v in getattr(st, attr).items():
            total[k] = total.get(k, 0) + v
    return total


class StatsHistoryView(QWidget):
    """「今回の実行履歴」タブ。"""

    def __init__(self, state: WorkbenchState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._state = state
        self._pending_refresh = False
        self._last_refresh_at = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(_COLUMN_HEADERS))
        self._tree.setHeaderLabels(list(_COLUMN_HEADERS))
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setSortingEnabled(True)
        self._tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        header = self._tree.header()
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_CONTEXT, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_MODEL, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_ELAPSED, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_TOOLS, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_SKILLS, QHeaderView.ResizeMode.Stretch)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._tree)

        # スロットルタイマー
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.setInterval(_THROTTLE_MS)
        self._throttle_timer.timeout.connect(self._do_refresh)

        # シグナル購読
        sigs = state.signals()
        sigs.stats_history_updated.connect(self._schedule_refresh)
        sigs.context_updated.connect(lambda *_: self._schedule_refresh())
        sigs.tool_counts_updated.connect(lambda *_: self._schedule_refresh())
        sigs.skill_counts_updated.connect(lambda *_: self._schedule_refresh())
        sigs.step_status_changed.connect(lambda *_: self._schedule_refresh())
        sigs.header_updated.connect(self._schedule_refresh)

        self.refresh()

    # ------------------------------------------------------------------
    # 公開 API（テスト用）
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """即時再描画する（テスト/初回表示用）。"""
        self._do_refresh()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _schedule_refresh(self) -> None:
        if not self._throttle_timer.isActive():
            self._throttle_timer.start()

    def _do_refresh(self) -> None:
        self._tree.setSortingEnabled(False)
        self._tree.clear()
        for wf in self._state.stats_history:
            self._tree.addTopLevelItem(self._build_workflow_item(wf))
        self._tree.setSortingEnabled(True)
        # 全て展開
        self._tree.expandAll()
        self._last_refresh_at = time.monotonic()

    def _build_workflow_item(self, wf: WorkflowStatsSnapshot) -> QTreeWidgetItem:
        name = wf.workflow_name or wf.workflow_id or "(unknown)"
        tools_total = _agg_workflow_counts(wf, "tool_counts")
        skills_total = _agg_workflow_counts(wf, "skill_counts")
        elapsed = wf.elapsed_sec
        if elapsed is None and wf.started_at is not None:
            elapsed = max(0.0, time.monotonic() - wf.started_at)
        item = QTreeWidgetItem(
            [
                f"[Workflow] {name}",
                _fmt_context(wf.context_current, wf.context_limit),
                wf.model or _DASH,
                _fmt_elapsed(elapsed),
                _fmt_counts(tools_total),
                _fmt_counts(skills_total),
            ]
        )
        # D-click 用に raw データを保持
        item.setData(COL_TOOLS, Qt.ItemDataRole.UserRole, tools_total)
        item.setData(COL_SKILLS, Qt.ItemDataRole.UserRole, skills_total)
        item.setData(COL_NAME, Qt.ItemDataRole.UserRole, ("workflow", wf.workflow_id, wf.run_id))

        for st in wf.steps:
            item.addChild(self._build_step_item(st))
        return item

    def _build_step_item(self, st: StepStatsSnapshot) -> QTreeWidgetItem:
        item = QTreeWidgetItem(
            [
                f"  {st.step_id}",
                _fmt_context(st.context_current, st.context_limit),
                st.model or _DASH,
                _fmt_elapsed(st.elapsed_sec),
                _fmt_counts(st.tool_counts),
                _fmt_counts(st.skill_counts),
            ]
        )
        item.setData(COL_TOOLS, Qt.ItemDataRole.UserRole, dict(st.tool_counts))
        item.setData(COL_SKILLS, Qt.ItemDataRole.UserRole, dict(st.skill_counts))
        item.setData(COL_NAME, Qt.ItemDataRole.UserRole, ("step", st.step_id, st.status))
        # status 表示（tooltip）
        item.setToolTip(COL_NAME, f"status: {st.status}")
        return item

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        if column not in (COL_TOOLS, COL_SKILLS):
            return
        counts = item.data(column, Qt.ItemDataRole.UserRole)
        if not isinstance(counts, dict) or not counts:
            return
        title = self.tr("Tools 全件") if column == COL_TOOLS else self.tr("Skills 全件")
        QMessageBox.information(self, title, _full_counts_text(counts))
