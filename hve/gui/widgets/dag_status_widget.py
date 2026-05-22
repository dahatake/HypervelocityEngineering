"""hve.gui.widgets.dag_status_widget — DAG ベースの「作業状況」ウィジェット。

旧 ``ActivityStatusWidget`` (QTreeWidget ベース) を置換する横ランク DAG ビュー。

特徴:
- 1 Workflow = 1 横ストライプ。複数 Workflow は縦方向に積み、Workflow ヘッダ
  ダブルクリックで折りたたみ/展開できる（Q4=B）。
- 各 Step ノードは ``compute_layout`` で計算された ``(rank, order)`` に従って
  グリッド配置される（rank=左→右、order=上→下）。
- Step ノード単一クリックで ``node_selected(instance_id, step_id)`` を emit
  （Q3=B）。Workflow ヘッダクリック時は ``node_selected(instance_id, "")``。
- Step ノードのダブルクリックは Fanout 詳細表示の開閉（subtask ドット表示）に
  使用する。Fanout を持たない Step では何も起きない。
- 1 Hz の ``QTimer`` で経過時間ラベルを再描画する。

公開 API は旧 ``ActivityStatusWidget`` と同名・同シグネチャを維持する
(``reset``/``set_plan``/``update_workflow_instances``/``stop``/``set_theme``)。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..copy_button import CopyButton
from .dag_layout import compute_layout, grid_dimensions


# ---------------------------------------------------------------------------
# 定数 / テーマ
# ---------------------------------------------------------------------------

NODE_W = 170
NODE_H = 56
COL_GAP = 30
ROW_GAP = 10
STRIPE_HEADER_H = 28
STRIPE_PADDING_Y = 8
STRIPE_GAP = 14
LEFT_MARGIN = 12
RIGHT_MARGIN = 12
TOP_MARGIN = 8
BOTTOM_MARGIN = 12
SUBTASK_DOT_R = 5
SUBTASK_DOT_GAP = 4

_STATUS_GLYPH = {
    "pending": "⚪",
    "running": "🔄",
    "done": "✅",
    "failed": "❌",
    "skipped": "⏭️",
}

_STATUS_COLOR_LIGHT = {
    "pending": QColor("#888888"),
    "running": QColor("#e6a700"),
    "done": QColor("#2ca02c"),
    "failed": QColor("#d62728"),
    "skipped": QColor("#17a2b8"),
}

_STATUS_COLOR_DARK = {
    "pending": QColor("#bbbbbb"),
    "running": QColor("#ffd24a"),
    "done": QColor("#7fdc7f"),
    "failed": QColor("#ff6f6f"),
    "skipped": QColor("#5ad6e8"),
}

_THEMES: Dict[str, Dict[str, Any]] = {
    "light": {
        "bg": QColor("#fafafa"),
        "stripe_bg": QColor("#ffffff"),
        "stripe_border": QColor("#dcdcdc"),
        "header_text": QColor("#222222"),
        "node_bg": QColor("#ffffff"),
        "node_border": QColor("#bdbdbd"),
        "node_border_selected": QColor("#0078d4"),
        "node_text": QColor("#222222"),
        "node_subtext": QColor("#555555"),
        "edge": QColor("#9aa3ad"),
        "title_label_css": "font-size: 12pt; font-weight: bold;",
        "summary_label_css": "color: #555555; font-size: 9pt;",
        "status_colors": _STATUS_COLOR_LIGHT,
    },
    "dark": {
        "bg": QColor("#1f1f1f"),
        "stripe_bg": QColor("#2a2a2a"),
        "stripe_border": QColor("#3a3a3a"),
        "header_text": QColor("#e6e6e6"),
        "node_bg": QColor("#333333"),
        "node_border": QColor("#5a5a5a"),
        "node_border_selected": QColor("#3aa0ff"),
        "node_text": QColor("#f0f0f0"),
        "node_subtext": QColor("#bbbbbb"),
        "edge": QColor("#888888"),
        "title_label_css": "color: #e6e6e6; font-size: 12pt; font-weight: bold;",
        "summary_label_css": "color: #bbbbbb; font-size: 9pt;",
        "status_colors": _STATUS_COLOR_DARK,
    },
}


# ---------------------------------------------------------------------------
# 内部データ型
# ---------------------------------------------------------------------------


def _normalize_status(text: str) -> str:
    """日本語ステータス文字列を内部キーへ正規化する（Plan モード入力対応）。"""
    if not text:
        return "pending"
    if text in ("実行中", "running"):
        return "running"
    if text in ("完了", "done"):
        return "done"
    if text in ("失敗", "failed"):
        return "failed"
    if text in ("スキップ", "skipped"):
        return "skipped"
    if text in ("pending", "保留"):
        return "pending"
    # "致命的 (...)" 等は failed 扱い
    if text.startswith("致命的"):
        return "failed"
    return "pending"


def _fmt_elapsed(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--:--"
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


class _WorkflowEntry:
    """1 Workflow 分のレイアウト用エントリ。

    Plan モード / Instances モードのどちらの入力からも作られる中間表現。
    """

    __slots__ = (
        "instance_id",
        "workflow_id",
        "label",
        "status",
        "steps",  # List[dict]: {"id","title","depends_on","status","started_at"}
        "subtasks",  # Dict[step_id, List[(subtask_id, title, status_norm)]]
    )

    def __init__(
        self,
        instance_id: str,
        workflow_id: str,
        label: str,
        status: str,
    ) -> None:
        self.instance_id = instance_id
        self.workflow_id = workflow_id
        self.label = label
        self.status = status
        self.steps: List[dict] = []
        self.subtasks: Dict[str, List[tuple]] = {}


# ---------------------------------------------------------------------------
# QGraphicsItem サブクラス
# ---------------------------------------------------------------------------


class _StepNodeItem(QGraphicsRectItem):
    """1 Step を表すノード。クリック/ダブルクリックをウィジェットへ伝搬する。"""

    def __init__(
        self,
        x: float,
        y: float,
        instance_id: str,
        step_id: str,
        title: str,
        status: str,
        widget: "DagStatusWidget",
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        super().__init__(0, 0, NODE_W, NODE_H, parent)
        self.setPos(x, y)
        self.instance_id = instance_id
        self.step_id = step_id
        self.title = title
        self.status = status
        self._widget = widget
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self._fanout_done: Optional[int] = None
        self._fanout_total: Optional[int] = None
        self._retry: int = 0
        self._fanout_expanded: bool = False

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        # ラベル群（位置はパターン更新で調整）
        self._lbl_main = QGraphicsSimpleTextItem("", self)
        self._lbl_elapsed = QGraphicsSimpleTextItem("", self)
        self._lbl_main.setPos(8, 6)
        self._lbl_elapsed.setPos(8, NODE_H - 18)
        self.refresh_theme()
        self.update_text()

    # ----------------------------- 描画 ---------------------------------

    def refresh_theme(self) -> None:
        theme = self._widget._theme_def
        sc = theme["status_colors"].get(self.status, theme["status_colors"]["pending"])
        border = (
            theme["node_border_selected"] if self.isSelected() else sc
        )
        self.setBrush(QBrush(theme["node_bg"]))
        pen = QPen(border)
        pen.setWidthF(2.0 if self.isSelected() else 1.5)
        self.setPen(pen)
        # ラベル色
        f_main = QFont()
        f_main.setBold(True)
        self._lbl_main.setFont(f_main)
        self._lbl_main.setBrush(QBrush(theme["node_text"]))
        self._lbl_elapsed.setBrush(QBrush(theme["node_subtext"]))

    def update_text(self) -> None:
        glyph = _STATUS_GLYPH.get(self.status, "?")
        label = f"{glyph} {self.step_id}.{self.title}"
        # retry / fanout バッジ
        suffix_parts: List[str] = []
        if self._retry and self._retry > 0:
            suffix_parts.append(f"retry {self._retry}")
        if self._fanout_total is not None:
            done = self._fanout_done or 0
            suffix_parts.append(f"{done}/{self._fanout_total}")
        if suffix_parts:
            label += "  (" + ", ".join(suffix_parts) + ")"
        # 切り詰め
        max_chars = 22
        if len(label) > max_chars:
            label = label[: max_chars - 1] + "…"
        self._lbl_main.setText(label)

        # 経過時間（完了済みなら finished_at で停止。tick で再呼び出しされても
        # finished_at が固定値のため値は変わらない）
        elapsed_text = "--:--:--"
        if self.started_at is not None:
            end = self.finished_at if self.finished_at is not None else time.monotonic()
            elapsed_text = _fmt_elapsed(max(0.0, end - self.started_at))
        self._lbl_elapsed.setText(f"⏱ {elapsed_text}")

    # ---------------------------- イベント -------------------------------

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        # 選択ハンドリング → ウィジェットへ通知
        self._widget._select_node(self.instance_id, self.step_id, self)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if self._fanout_total is not None:
            # ウィジェット層に展開状態を委譲（再レイアウト後も保持される）。
            self._widget._toggle_step_expand(self.instance_id, self.step_id)
        # Fanout を持たない Step ノードのダブルクリックは無視。
        super().mouseDoubleClickEvent(event)


class _WorkflowHeaderItem(QGraphicsRectItem):
    """Workflow ヘッダ。ダブルクリックで Workflow 配下を展開/折りたたみ。"""

    def __init__(
        self,
        x: float,
        y: float,
        width: float,
        instance_id: str,
        label: str,
        status: str,
        widget: "DagStatusWidget",
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        super().__init__(0, 0, width, STRIPE_HEADER_H, parent)
        self.setPos(x, y)
        self.instance_id = instance_id
        self._widget = widget
        self.status = status
        self.label = label
        self.setAcceptHoverEvents(True)

        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self._lbl = QGraphicsSimpleTextItem("", self)
        self._lbl.setPos(8, 5)
        self.refresh_theme()
        self.update_text(0, 0)

    def refresh_theme(self) -> None:
        theme = self._widget._theme_def
        self.setBrush(QBrush(theme["stripe_bg"]))
        self.setPen(QPen(theme["stripe_border"]))
        f = QFont()
        f.setBold(True)
        f.setPointSize(10)
        self._lbl.setFont(f)
        self._lbl.setBrush(QBrush(theme["header_text"]))

    def update_text(self, done_steps: int, total_steps: int) -> None:
        expanded = self._widget._is_workflow_expanded(self.instance_id)
        arrow = "▼" if expanded else "▶"
        glyph = _STATUS_GLYPH.get(self.status, "?")
        elapsed_text = "--:--:--"
        if self.started_at is not None:
            end = self.finished_at if self.finished_at is not None else time.monotonic()
            elapsed_text = _fmt_elapsed(max(0.0, end - self.started_at))
        text = (
            f"{arrow}  {glyph} {self.label}    "
            f"ステップ: {done_steps}/{total_steps}    [{elapsed_text}]"
        )
        self._lbl.setText(text)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self._widget._select_node(self.instance_id, "", self)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        self._widget._toggle_workflow(self.instance_id)
        super().mouseDoubleClickEvent(event)


# ---------------------------------------------------------------------------
# DagStatusWidget 本体
# ---------------------------------------------------------------------------


class DagStatusWidget(QWidget):
    """Workflow → Step を DAG 形式で描画する作業状況ビュー。

    シグナル:
        node_selected(instance_id, step_id_or_empty):
            ノード（Workflow ヘッダまたは Step）が選択された時に emit。
            Workflow ヘッダ選択時は step_id_or_empty="" になる。
    """

    node_selected = Signal(str, str)  # (instance_id, step_id_or_empty)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        theme: str = "light",
    ) -> None:
        super().__init__(parent)
        self._theme = theme if theme in _THEMES else "light"
        self._theme_def = _THEMES[self._theme]

        # 入力データ
        self._entries: List[_WorkflowEntry] = []
        # node_key -> _StepNodeItem (Step) / _WorkflowHeaderItem (Workflow)
        self._step_items: Dict[Tuple[str, str], _StepNodeItem] = {}
        self._wf_items: Dict[str, _WorkflowHeaderItem] = {}
        # Workflow 展開状態（既定: 展開）
        self._wf_expanded: Dict[str, bool] = {}
        # Step Fanout 展開状態（既定: 折りたたみ） — 再レイアウト後も保持
        self._step_expanded: Dict[Tuple[str, str], bool] = {}
        # Step タイミング保持 (instance_id, step_id) -> started_at / finished_at
        self._step_started_at: Dict[Tuple[str, str], float] = {}
        self._step_finished_at: Dict[Tuple[str, str], float] = {}
        # Workflow タイミング保持 instance_id -> started_at / finished_at
        self._wf_started_at: Dict[str, float] = {}
        self._wf_finished_at: Dict[str, float] = {}
        # 現在の選択ノード
        self._selected_node_item: Optional[QGraphicsItem] = None
        self._global_started_at: Optional[float] = None

        # --- UI ---
        self._title_label = QLabel(self.tr("作業状況"))
        self._title_label.setStyleSheet(self._theme_def["title_label_css"])

        self._summary_label = QLabel(
            self.tr("ワークフロー: 0/0   ステップ: 0/0   [--:--:--]")
        )
        self._summary_label.setStyleSheet(self._theme_def["summary_label_css"])

        self._copy_button = CopyButton(
            get_text=self._export_text,
            tooltip=self.tr("作業状況をクリップボードにコピー"),
        )

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.addWidget(self._title_label)
        header_row.addStretch(1)
        header_row.addWidget(self._summary_label)
        header_row.addWidget(self._copy_button)

        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(QBrush(self._theme_def["bg"]))
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._view.setMinimumHeight(STRIPE_HEADER_H * 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(header_row)
        layout.addWidget(self._view)

        # 1 Hz tick
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start()

    # ----------------------------------------------------------
    # 公開 API（旧 ActivityStatusWidget と同名で互換維持）
    # ----------------------------------------------------------

    def reset(self) -> None:
        self._entries = []
        self._step_items.clear()
        self._wf_items.clear()
        self._step_started_at.clear()
        self._step_finished_at.clear()
        self._wf_started_at.clear()
        self._wf_finished_at.clear()
        self._step_expanded.clear()
        self._selected_node_item = None
        self._global_started_at = None
        self._scene.clear()
        self._summary_label.setText(
            self.tr("ワークフロー: 0/0   ステップ: 0/0   [--:--:--]")
        )

    def stop(self) -> None:
        self._tick_timer.stop()

    def set_theme(self, theme: str) -> None:
        if theme not in _THEMES or theme == self._theme:
            return
        self._theme = theme
        self._theme_def = _THEMES[theme]
        self._title_label.setStyleSheet(self._theme_def["title_label_css"])
        self._summary_label.setStyleSheet(self._theme_def["summary_label_css"])
        self._scene.setBackgroundBrush(QBrush(self._theme_def["bg"]))
        self._relayout()

    def set_plan(
        self,
        workflow_plan: List[dict],
        workflow_status: Dict[str, str],
        step_status: Dict[str, Dict[str, str]],
        subtask_status: Optional[Dict[str, Dict[str, List[tuple]]]] = None,
    ) -> None:
        """Plan モード入力（旧 ActivityStatusWidget と同シグネチャ）。"""
        if self._global_started_at is None:
            self._global_started_at = time.monotonic()
        entries: List[_WorkflowEntry] = []
        for wf in workflow_plan:
            wf_id = str(wf.get("workflow_id", ""))
            wf_name = str(wf.get("workflow_name", wf_id))
            wf_status_raw = workflow_status.get(wf_id, "") if workflow_status else ""
            wf_status = _normalize_status(wf_status_raw)
            # Workflow タイミング: running で開始確定、終了状態で停止確定。
            # started_at 未設定で終了に達した場合、子ステップの最古 started_at を
            # フォールバック起点とし、無ければ now を採用する。
            if wf_status == "running" and wf_id not in self._wf_started_at:
                self._wf_started_at[wf_id] = time.monotonic()
            if (
                wf_status in ("done", "failed", "skipped")
                and wf_id not in self._wf_finished_at
            ):
                if wf_id not in self._wf_started_at:
                    child_starts = [
                        v
                        for (k_iid, _), v in self._step_started_at.items()
                        if k_iid == wf_id
                    ]
                    self._wf_started_at[wf_id] = (
                        min(child_starts) if child_starts else time.monotonic()
                    )
                self._wf_finished_at[wf_id] = time.monotonic()
            entry = _WorkflowEntry(
                instance_id=wf_id,
                workflow_id=wf_id,
                label=wf_name,
                status=wf_status,
            )
            step_map = step_status.get(wf_id, {}) if step_status else {}
            for s in wf.get("steps", []):
                sid = str(s.get("id", "")) if isinstance(s, dict) else str(s[0])
                stitle = str(s.get("title", sid)) if isinstance(s, dict) else str(s[1])
                deps = list(s.get("depends_on", [])) if isinstance(s, dict) else []
                sstatus = _normalize_status(step_map.get(sid, ""))
                # status が running に上がった瞬間に started_at を確定する
                key = (entry.instance_id, sid)
                if sstatus == "running" and key not in self._step_started_at:
                    self._step_started_at[key] = time.monotonic()
                # status が終了状態に達したら finished_at を確定（以後カウントアップ停止）
                if (
                    sstatus in ("done", "failed", "skipped")
                    and key not in self._step_finished_at
                ):
                    if key not in self._step_started_at:
                        self._step_started_at[key] = time.monotonic()
                    self._step_finished_at[key] = time.monotonic()
                started_at = self._step_started_at.get(key)
                finished_at = self._step_finished_at.get(key)
                entry.steps.append(
                    {
                        "id": sid,
                        "title": stitle,
                        "depends_on": deps,
                        "status": sstatus,
                        "started_at": started_at,
                        "finished_at": finished_at,
                    }
                )
            if subtask_status:
                sub_map = subtask_status.get(wf_id, {})
                for step_id, subs in sub_map.items():
                    entry.subtasks[step_id] = [
                        (
                            str(t[0]) if len(t) > 0 else "",
                            str(t[1]) if len(t) > 1 else "",
                            _normalize_status(str(t[2]) if len(t) > 2 else ""),
                        )
                        for t in subs
                    ]
            entries.append(entry)
        self._entries = entries
        self._relayout()

    def update_workflow_instances(self, state: Any) -> None:
        """Instances モード入力（state.workflows から構築）。"""
        if self._global_started_at is None:
            self._global_started_at = time.monotonic()
        entries: List[_WorkflowEntry] = []
        workflows = getattr(state, "workflows", None) or {}
        for instance_id, inst in workflows.items():
            wf_status = _normalize_status(getattr(inst, "status", "pending"))
            iid = str(instance_id)
            # WorkflowInstance.started_at / finished_at が正規ソース。
            # ローカル dict はキャッシュ目的のみ（Plan モードとの統合用）。
            wf_started = getattr(inst, "started_at", None)
            wf_finished = getattr(inst, "finished_at", None)
            if wf_started is not None:
                self._wf_started_at[iid] = wf_started
            elif wf_status == "running" and iid not in self._wf_started_at:
                self._wf_started_at[iid] = time.monotonic()
            if wf_finished is not None:
                self._wf_finished_at[iid] = wf_finished
            elif (
                wf_status in ("done", "failed", "skipped")
                and iid not in self._wf_finished_at
            ):
                if iid not in self._wf_started_at:
                    child_starts = [
                        v
                        for (k_iid, _), v in self._step_started_at.items()
                        if k_iid == iid
                    ]
                    self._wf_started_at[iid] = (
                        min(child_starts) if child_starts else time.monotonic()
                    )
                self._wf_finished_at[iid] = time.monotonic()
            entry = _WorkflowEntry(
                instance_id=iid,
                workflow_id=str(getattr(inst, "workflow_id", instance_id)),
                label=str(getattr(inst, "label", instance_id)),
                status=wf_status,
            )
            # Steps は WorkflowInstance.steps (OrderedDict[step_id, StepView])
            steps = getattr(inst, "steps", None) or {}
            # depends_on は state には保持されていないため、ワークフロー定義から再取得を試みる
            deps_lookup: Dict[str, List[str]] = {}
            try:
                from hve.workflow_registry import get_workflow

                wf_def = get_workflow(entry.workflow_id)
                if wf_def is not None:
                    deps_lookup = {
                        s.id: list(s.depends_on)
                        for s in wf_def.steps
                        if not s.is_container
                    }
            except Exception:
                deps_lookup = {}

            for step_id, sv in steps.items():
                sstatus = _normalize_status(getattr(sv, "status", "pending"))
                key = (entry.instance_id, str(step_id))
                started_at = getattr(sv, "started_at", None)
                if started_at is None:
                    started_at = self._step_started_at.get(key)
                else:
                    self._step_started_at[key] = started_at
                finished_at = getattr(sv, "finished_at", None)
                if finished_at is None:
                    # fallback: 実完了時刻が state 側で未設定の場合のみ。
                    # now を採用するため elapsed は実体より短くなり得るが、
                    # 少なくともカウントアップは停止する。
                    if (
                        sstatus in ("done", "failed", "skipped")
                        and key not in self._step_finished_at
                    ):
                        if key not in self._step_started_at:
                            self._step_started_at[key] = time.monotonic()
                        self._step_finished_at[key] = time.monotonic()
                    finished_at = self._step_finished_at.get(key)
                else:
                    self._step_finished_at[key] = finished_at
                entry.steps.append(
                    {
                        "id": str(step_id),
                        "title": str(getattr(sv, "title", step_id)),
                        "depends_on": deps_lookup.get(str(step_id), []),
                        "status": sstatus,
                        "started_at": started_at,
                        "finished_at": finished_at,
                    }
                )
                # children を Fanout 子として扱う（subtask 表示用）
                children = list(getattr(sv, "children", []) or [])
                if children:
                    entry.subtasks[str(step_id)] = [
                        (
                            str(getattr(c, "id", "")),
                            str(getattr(c, "title", "")),
                            _normalize_status(getattr(c, "status", "pending")),
                        )
                        for c in children
                    ]
            entries.append(entry)
        self._entries = entries
        self._relayout()

    # ----------------------------------------------------------
    # レイアウト
    # ----------------------------------------------------------

    def _is_workflow_expanded(self, instance_id: str) -> bool:
        return self._wf_expanded.get(instance_id, True)

    def _toggle_workflow(self, instance_id: str) -> None:
        cur = self._is_workflow_expanded(instance_id)
        self._wf_expanded[instance_id] = not cur
        self._relayout()

    def _is_step_expanded(self, instance_id: str, step_id: str) -> bool:
        return self._step_expanded.get((instance_id, step_id), False)

    def _toggle_step_expand(self, instance_id: str, step_id: str) -> None:
        """Fanout を持つ Step ノードの展開状態をトグルする。

        ウィジェット層に状態を保持するため、status 変化等で ``_relayout`` が
        走っても展開状態が失われない。
        """
        key = (instance_id, step_id)
        self._step_expanded[key] = not self._step_expanded.get(key, False)
        self._relayout()

    def _relayout(self) -> None:
        """シーンを再構築する。"""
        self._scene.clear()
        self._step_items.clear()
        self._wf_items.clear()
        self._selected_node_item = None  # 再描画で参照無効化

        theme = self._theme_def
        max_cols = 0
        # まず Workflow 単位の col 数の最大を求める（横幅算出用）
        per_wf_layout: List[
            Tuple[_WorkflowEntry, Dict[str, int], Dict[str, int], int, int]
        ] = []
        for entry in self._entries:
            rank, order = compute_layout(entry.steps)
            cols, rows = grid_dimensions(rank, order)
            max_cols = max(max_cols, cols)
            per_wf_layout.append((entry, rank, order, cols, rows))

        # シーン幅を決定。最小はビューポート幅
        viewport_w = max(self._view.viewport().width(), 600)
        content_w = (
            LEFT_MARGIN + RIGHT_MARGIN + max(0, max_cols) * (NODE_W + COL_GAP)
        )
        scene_w = max(viewport_w, content_w)

        y = TOP_MARGIN
        done_wf = 0
        total_steps = 0
        done_steps = 0
        for entry, rank, order, cols, rows in per_wf_layout:
            # Workflow ヘッダ
            header = _WorkflowHeaderItem(
                LEFT_MARGIN,
                y,
                scene_w - LEFT_MARGIN - RIGHT_MARGIN,
                entry.instance_id,
                entry.label,
                entry.status,
                widget=self,
            )
            self._scene.addItem(header)
            self._wf_items[entry.instance_id] = header
            header.started_at = self._wf_started_at.get(entry.instance_id)
            header.finished_at = self._wf_finished_at.get(entry.instance_id)

            wf_done = sum(1 for s in entry.steps if s["status"] in ("done", "skipped"))
            wf_total = len(entry.steps)
            total_steps += wf_total
            done_steps += wf_done
            header.update_text(wf_done, wf_total)
            if entry.status in ("done", "skipped"):
                done_wf += 1

            y += STRIPE_HEADER_H

            if self._is_workflow_expanded(entry.instance_id) and entry.steps:
                stripe_top = y + STRIPE_PADDING_Y
                # 各 Step ノードを配置
                step_to_pos: Dict[str, Tuple[float, float]] = {}
                # subtask 行高（Fanout 展開時のみ）
                row_extra: Dict[int, int] = {}  # row → 追加 px
                for s in entry.steps:
                    sid = s["id"]
                    r = rank.get(sid, 0)
                    o = order.get(sid, 0)
                    x = LEFT_MARGIN + r * (NODE_W + COL_GAP)
                    # row 高に Fanout 展開分を加算
                    base_y = stripe_top + o * (NODE_H + ROW_GAP) + row_extra.get(o, 0)
                    node = _StepNodeItem(
                        x,
                        base_y,
                        entry.instance_id,
                        sid,
                        s["title"],
                        s["status"],
                        widget=self,
                    )
                    node.started_at = s.get("started_at")
                    node.finished_at = s.get("finished_at")
                    # Fanout
                    subs = entry.subtasks.get(sid)
                    if subs:
                        sub_done = sum(
                            1 for _, _, st in subs if st in ("done", "skipped")
                        )
                        node._fanout_total = len(subs)
                        node._fanout_done = sub_done
                        # ウィジェット層に保持された展開状態を復元する。
                        node._fanout_expanded = self._is_step_expanded(
                            entry.instance_id, sid
                        )
                    # 既存の選択状態を引き継がない（_relayout でクリア）
                    node.update_text()
                    self._scene.addItem(node)
                    self._step_items[(entry.instance_id, sid)] = node
                    step_to_pos[sid] = (x, base_y)

                    # Fanout 展開時はサブタスクドットを下に描画
                    if subs and node._fanout_expanded:
                        self._draw_subtask_dots(
                            x + 8,
                            base_y + NODE_H + 4,
                            subs,
                        )

                # エッジ
                edge_pen = QPen(theme["edge"])
                edge_pen.setWidthF(1.4)
                for s in entry.steps:
                    sid = s["id"]
                    if sid not in step_to_pos:
                        continue
                    cx, cy = step_to_pos[sid]
                    child_left = QPointF(cx, cy + NODE_H / 2)
                    for parent_id in s.get("depends_on", []) or []:
                        if parent_id not in step_to_pos:
                            continue
                        px, py = step_to_pos[parent_id]
                        parent_right = QPointF(px + NODE_W, py + NODE_H / 2)
                        self._draw_edge(parent_right, child_left, edge_pen)

                # ストライプ高加算
                stripe_h = STRIPE_PADDING_Y + rows * (NODE_H + ROW_GAP) - ROW_GAP
                # Fanout 展開分の追加（簡略化のため一括 0、subtask 展開時は relayout が再呼び出しされる）
                y = stripe_top + max(stripe_h, NODE_H)
                # サブタスクドットの分 (Fanout 展開ノードがある場合) 概算 +16
                for s in entry.steps:
                    nd = self._step_items.get((entry.instance_id, s["id"]))
                    if nd is not None and nd._fanout_expanded:
                        y += SUBTASK_DOT_R * 2 + 8
                        break

            y += STRIPE_GAP

        scene_h = max(y + BOTTOM_MARGIN, self._view.viewport().height())
        self._scene.setSceneRect(QRectF(0, 0, scene_w, scene_h))

        # サマリ
        elapsed = (
            time.monotonic() - self._global_started_at
            if self._global_started_at is not None
            else 0.0
        )
        self._summary_label.setText(
            self.tr("ワークフロー: %d/%d   ステップ: %d/%d   [%s]")
            % (
                done_wf,
                len(self._entries),
                done_steps,
                total_steps,
                _fmt_elapsed(elapsed),
            )
        )

    def _draw_subtask_dots(
        self,
        x: float,
        y: float,
        subs: List[tuple],
    ) -> None:
        """Fanout 展開時のサブタスク状態ドット列。"""
        theme = self._theme_def
        for i, (_sid, _title, st) in enumerate(subs):
            color = theme["status_colors"].get(st, theme["status_colors"]["pending"])
            cx = x + i * (SUBTASK_DOT_R * 2 + SUBTASK_DOT_GAP)
            dot = QGraphicsRectItem(0, 0, SUBTASK_DOT_R * 2, SUBTASK_DOT_R * 2)
            dot.setPos(cx, y)
            dot.setBrush(QBrush(color))
            pen = QPen(color.darker(140))
            pen.setWidthF(0.8)
            dot.setPen(pen)
            self._scene.addItem(dot)

    def _draw_edge(self, src: QPointF, dst: QPointF, pen: QPen) -> None:
        """src → dst の直角折れ線エッジと終端矢印を描く。"""
        mx = (src.x() + dst.x()) / 2
        seg1 = self._scene.addLine(src.x(), src.y(), mx, src.y(), pen)
        seg2 = self._scene.addLine(mx, src.y(), mx, dst.y(), pen)
        seg3 = self._scene.addLine(mx, dst.y(), dst.x(), dst.y(), pen)
        # 矢印
        arrow = QPolygonF(
            [
                QPointF(dst.x(), dst.y()),
                QPointF(dst.x() - 7, dst.y() - 4),
                QPointF(dst.x() - 7, dst.y() + 4),
            ]
        )
        ar = self._scene.addPolygon(arrow, pen, QBrush(pen.color()))
        # ZValue を整える（既存ノードより手前に出ないように）
        for it in (seg1, seg2, seg3, ar):
            it.setZValue(-1)

    # ----------------------------------------------------------
    # 選択 / ティック
    # ----------------------------------------------------------

    def _select_node(
        self,
        instance_id: str,
        step_id: str,
        item: QGraphicsItem,
    ) -> None:
        # 旧選択を解除
        prev = self._selected_node_item
        if prev is not None and prev is not item:
            try:
                prev.setSelected(False)
                if hasattr(prev, "refresh_theme"):
                    prev.refresh_theme()  # type: ignore[attr-defined]
            except RuntimeError:
                pass
        item.setSelected(True)
        if hasattr(item, "refresh_theme"):
            item.refresh_theme()  # type: ignore[attr-defined]
        self._selected_node_item = item
        self.node_selected.emit(instance_id, step_id)

    def _on_tick(self) -> None:
        if not self.isVisible():
            return
        # 経過時間ラベルのみ更新（_relayout は呼ばない）
        for node in self._step_items.values():
            try:
                node.update_text()
            except RuntimeError:
                pass
        # Workflow ヘッダの経過時間も更新
        for entry in self._entries:
            header = self._wf_items.get(entry.instance_id)
            if header is None:
                continue
            try:
                wf_done = sum(
                    1 for s in entry.steps if s["status"] in ("done", "skipped")
                )
                header.update_text(wf_done, len(entry.steps))
            except RuntimeError:
                pass
        if self._global_started_at is not None:
            done_wf = sum(
                1 for e in self._entries if e.status in ("done", "skipped")
            )
            total_steps = sum(len(e.steps) for e in self._entries)
            done_steps = sum(
                1
                for e in self._entries
                for s in e.steps
                if s["status"] in ("done", "skipped")
            )
            elapsed = time.monotonic() - self._global_started_at
            self._summary_label.setText(
                self.tr("ワークフロー: %d/%d   ステップ: %d/%d   [%s]")
                % (
                    done_wf,
                    len(self._entries),
                    done_steps,
                    total_steps,
                    _fmt_elapsed(elapsed),
                )
            )

    # ----------------------------------------------------------
    # コピー
    # ----------------------------------------------------------

    def _export_text(self) -> str:
        lines: List[str] = [self._summary_label.text()]
        for entry in self._entries:
            wf_glyph = _STATUS_GLYPH.get(entry.status, "?")
            lines.append(f"{wf_glyph} {entry.label} [{entry.instance_id}]")
            for s in entry.steps:
                sg = _STATUS_GLYPH.get(s["status"], "?")
                line = f"  {sg} {s['id']}.{s['title']}"
                if s.get("depends_on"):
                    line += f"  ⇐ {', '.join(s['depends_on'])}"
                lines.append(line)
                subs = entry.subtasks.get(s["id"])
                if subs:
                    for sid, title, st in subs:
                        lines.append(
                            f"    {_STATUS_GLYPH.get(st, '?')} {sid} {title}"
                        )
        return "\n".join(lines)
