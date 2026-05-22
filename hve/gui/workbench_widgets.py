"""hve.gui.workbench_widgets — Workbench UI ウィジェット群。

Header1, Header2, TaskTree, UserInteraction, Footer など、
各ペインに対応したウィジェットを提供。
"""

from __future__ import annotations

import html
import time
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics

from .copy_button import CopyButton
from .widgets.word_wrap_delegate import WordWrapDelegate
from .widgets.wrap_helpers import apply_cjk_wrap
from .workbench_state import WorkbenchState, StepStatus
from .workflow_display import format_workflow_label_activity


# ステップ状態グリフ
_STATUS_GLYPH = {
    "pending": "○",      # pending
    "running": "◇",      # running
    "done": "●",         # done
    "failed": "✗",       # failed
    "skipped": "⊘",      # skipped
}

_STATUS_COLOR = {
    "pending": "#888888",      # dim white
    "running": "#ffff00",      # bold yellow
    "done": "#00ff00",         # bold green
    "failed": "#ff0000",       # bold red
    "skipped": "#00ffff",      # dim cyan
}


class Header2Widget(QWidget):
    """Header2 ペイン: ステップ状態（○◇●✗⊘）を行に表示。"""

    def __init__(self, state: WorkbenchState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setStyleSheet("padding: 2px; font-size: 10pt;")
        self._update()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

    def _update(self) -> None:
        text_html = ""
        for s in self.state.steps:
            glyph = _STATUS_GLYPH.get(s.status, "?")
            color = _STATUS_COLOR.get(s.status, "#ffffff")

            # ステップラベル
            label = f"{s.id}.{s.title}"

            # Retry回数表示
            retry_n = getattr(s, "_retry_count", 0)
            if retry_n and retry_n > 0:
                label += f" (retry {retry_n})"

            # Fanout表示
            fanout_total = getattr(s, "_fanout_total", None)
            if fanout_total is not None:
                done = getattr(s, "_fanout_done", 0)
                label += f" ({done}/{fanout_total})"

            # HTML生成
            text_html += f'<span style="color: {color}; font-weight: bold;">{glyph} {label}</span>&nbsp;&nbsp;'

        self._label.setText(text_html)

    def update_state(self, state: WorkbenchState) -> None:
        self.state = state
        self._update()


class WorkflowProgressWidget(QWidget):
    """[DEPRECATED] ``DagStatusWidget`` (hve.gui.widgets.dag_status_widget) に
    置換済み。本クラスはどこからも import されておらず将来削除予定。
    内部に残る tuple 形式の steps 解釈は新 dict スキーマ
    （``{"id","title","depends_on"}``）と非互換のため呼び出さないこと。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workflow_plan: List[dict] = []
        self._workflow_status: Dict[str, str] = {}
        self._step_status: Dict[str, Dict[str, str]] = {}
        # workflow_id -> step_id -> [(subtask_id, title, status), ...]
        self._subtask_status: Dict[str, Dict[str, List[tuple]]] = {}

        title = QLabel(self.tr("ワークフロー進捗"))
        title.setStyleSheet("font-weight: bold; padding: 2px;")

        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        apply_cjk_wrap(self._view)
        self._view.setStyleSheet(
            "background: #f8f9fa; border: 1px solid #ddd; padding: 6px; font-size: 9pt;"
        )
        self._view.setMaximumHeight(260)
        self._view.setPlainText("（実行計画がありません）")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(title)
        layout.addWidget(self._view)

    def set_plan(
        self,
        workflow_plan: List[dict],
        workflow_status: Dict[str, str],
        step_status: Dict[str, Dict[str, str]],
        subtask_status: Optional[Dict[str, Dict[str, List[tuple]]]] = None,
    ) -> None:
        self._workflow_plan = list(workflow_plan)
        self._workflow_status = dict(workflow_status)
        self._step_status = {k: dict(v) for k, v in step_status.items()}
        if subtask_status is None:
            self._subtask_status = {}
        else:
            self._subtask_status = {
                wf_id: {st_id: list(subs) for st_id, subs in step_map.items()}
                for wf_id, step_map in subtask_status.items()
            }
        self._render()

    def _render(self) -> None:
        # ユーザーのスクロール位置を保持
        scrollbar = self._view.verticalScrollBar()
        prev_scroll = scrollbar.value() if scrollbar is not None else 0
        at_bottom = (
            scrollbar is not None and prev_scroll >= scrollbar.maximum()
        )

        if not self._workflow_plan:
            self._view.setPlainText("（実行計画がありません）")
            return

        total_wf = len(self._workflow_plan)
        done_wf = sum(
            1
            for wf in self._workflow_plan
            if self._workflow_status.get(str(wf.get("workflow_id", "")), "") == "完了"
        )

        lines: List[str] = []
        lines.append(f"進捗: {done_wf}/{total_wf} workflows 完了")
        lines.append("")

        for wf in self._workflow_plan:
            wf_id = str(wf.get("workflow_id", ""))
            wf_name = str(wf.get("workflow_name", wf_id))
            wf_state = self._workflow_status.get(wf_id, "")
            wf_state_text = f" [{wf_state}]" if wf_state else ""
            lines.append(f"{format_workflow_label_activity(wf_id, wf_name)}{wf_state_text}")

            step_map = self._step_status.get(wf_id, {})
            subtask_map = self._subtask_status.get(wf_id, {})
            for step_id, step_title in wf.get("steps", []):
                st = step_map.get(step_id, "")
                st_text = f" [{st}]" if st else ""
                lines.append(f"  - Step {step_id} {step_title}{st_text}")
                for _sub_id, sub_title, sub_state in subtask_map.get(step_id, []):
                    sub_state_text = f" [{sub_state}]" if sub_state else ""
                    lines.append(f"      - {sub_title}{sub_state_text}")
            lines.append("")

        self._view.setPlainText("\n".join(lines).rstrip())
        # ユーザーが手動でスクロールしている場合はその位置を維持する。
        # 末尾にいた場合のみ末尾に追従させる。
        scrollbar = self._view.verticalScrollBar()
        if scrollbar is not None:
            if at_bottom:
                scrollbar.setValue(scrollbar.maximum())
            else:
                scrollbar.setValue(min(prev_scroll, scrollbar.maximum()))


# ----------------------------------------------------------
# 作業状況 (ActivityStatusWidget)
# ----------------------------------------------------------

# 状態 → 絵文字（GUI 表示用）
_ACTIVITY_EMOJI = {
    "pending": "⚪",
    "running": "🟡",
    "done": "🟢",
    "failed": "🔴",
    "skipped": "⚫",
}


# テーマ別カラーパレット
_ACTIVITY_THEMES = {
    "dark": {
        "title": "",
        "summary": "",
        "tree": (
            "QTreeWidget {"
            " background: #252526; color: #cccccc;"
            " border: 1px solid #1e1e1e; font-size: 9pt;"
            "}"
            "QTreeWidget::item { padding: 0px 4px; }"
            "QTreeWidget::item:hover { background: #2a2d2e; }"
            "QTreeWidget::item:selected { background: #094771; color: #ffffff; }"
        ),
    },
    "light": {
        "title": "",
        "summary": "",
        "tree": (
            "QTreeWidget {"
            " background: #ffffff; color: #000000;"
            " border: 1px solid #d0d0d0; font-size: 9pt;"
            "}"
            "QTreeWidget::item { padding: 0px 4px; }"
            "QTreeWidget::item:hover { background: #e8e8e8; }"
            "QTreeWidget::item:selected { background: #0078d4; color: #ffffff; }"
        ),
    },
}


def _normalize_status(text: str) -> str:
    """日本語ステータス文字列を内部キーへ正規化する。"""
    if not text:
        return "pending"
    if text == "実行中":
        return "running"
    if text == "完了":
        return "done"
    if text == "失敗":
        return "failed"
    if text == "スキップ":
        return "skipped"
    return "pending"


def _fmt_elapsed(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--:--"
    s = max(0, int(seconds))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


class _PlanModeStateProxy:
    """``ActivityStatusWidget.set_plan`` から ``update_workflow_instances`` を呼ぶための
    軽量 state プロキシ。``workflows`` 属性のみを持つ。

    Phase 3a (Q1=C): Plan モードと Instances モードのレンダリングコードパス統合用。
    """

    __slots__ = ("workflows",)

    def __init__(self, workflows) -> None:
        self.workflows = workflows


class ActivityStatusWidget(QWidget):
    """[DEPRECATED] ``DagStatusWidget`` (hve.gui.widgets.dag_status_widget) に
    置換済み。``page_workbench`` からの参照は無くなったが、import 上の互換
    確保のためクラス自体は当面残置する（将来削除予定）。
    新規コードでは ``DagStatusWidget`` を使用すること。
    """

    # Wave 2 追加: ツリー上で WorkflowInstance ノードが選択された時に emit。
    workflow_instance_selected = Signal(str)  # instance_id

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        theme: str = "light",
    ) -> None:
        super().__init__(parent)
        self._theme = theme if theme in _ACTIVITY_THEMES else "light"
        self._workflow_plan: List[dict] = []
        self._workflow_status: Dict[str, str] = {}
        self._step_status: Dict[str, Dict[str, str]] = {}
        self._subtask_status: Dict[str, Dict[str, List[tuple]]] = {}

        # node_key -> (started_at_monotonic, finished_elapsed_or_None)
        # node_key 種別:
        #   ("wf", wf_id)
        #   ("step", wf_id, step_id)
        #   ("sub", wf_id, step_id, subtask_id)
        self._timings: Dict[tuple, Tuple[float, Optional[float]]] = {}
        self._global_started_at: Optional[float] = None

        # 展開状態の保存 (再描画時に展開・折りたたみ状態を維持)
        self._expanded: Dict[tuple, bool] = {}

        # node_key -> QTreeWidgetItem (in-place 更新用)
        self._items: Dict[tuple, "QTreeWidgetItem"] = {}

        # 直近スナップショット（_render 必要性判定用）
        self._last_snapshot: Optional[tuple] = None

        self._title_label = QLabel(self.tr("作業状況"))
        self._title_label.setStyleSheet(
            "font-size: 12pt; font-weight: bold;"
        )

        self._summary_label = QLabel(self.tr("ワークフロー: 0/0   ステップ: 0/0   [--:--:--]"))
        self._summary_label.setStyleSheet(
            _ACTIVITY_THEMES[self._theme]["summary"]
        )

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

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        # 折り返し描画のため UniformRowHeights は無効化する。
        self._tree.setUniformRowHeights(False)
        self._tree.setIndentation(16)
        self._tree.setWordWrap(True)
        self._tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        # 横スクロールは出さない（複数行折り返しで全文表示する）。
        self._tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # カスタム Delegate で複数行描画する。
        self._wrap_delegate = WordWrapDelegate(self._tree)
        self._tree.setItemDelegate(self._wrap_delegate)
        # 10 行分の高さを最低高として確保し、Splitter の縦領域に合わせて伸縮させる。
        _fm = QFontMetrics(self._tree.font())
        _row_h = _fm.lineSpacing()  # 縦余白 0 化（item padding 0px / Delegate _PAD_V=0）
        _tree_h = _row_h * 10 + 8
        self._tree.setMinimumHeight(_tree_h)
        self._tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._tree.setStyleSheet(_ACTIVITY_THEMES[self._theme]["tree"])
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemCollapsed.connect(self._on_item_collapsed)
        # ツリーの幅変更時に行高を再計算させる。
        self._tree.viewport().installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(header_row)
        layout.addWidget(self._tree)

        # 経過時間の周期更新タイマー (1 秒)
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start()

        # Wave 2: マルチ Workflow インスタンス用の選択ハンドラ。
        # _instances_mode が True のときのみ workflow_instance_selected を emit する。
        self._instances_mode: bool = False
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)

    # ---------- 公開 API ----------

    def reset(self) -> None:
        """次回 orchestrator 実行に向けて状態を初期化する。"""
        self._workflow_plan = []
        self._workflow_status = {}
        self._step_status = {}
        self._subtask_status = {}
        self._timings.clear()
        self._expanded.clear()
        self._items.clear()
        self._last_snapshot = None
        self._global_started_at = None
        self._instances_mode = False
        self._tree.clear()
        self._summary_label.setText(
            self.tr("ワークフロー: 0/0   ステップ: 0/0   [--:--:--]")
        )

    def stop(self) -> None:
        """周期タイマーを停止する（cleanup 用）。"""
        self._tick_timer.stop()

    def _export_text(self) -> str:
        """ツリー内容をインデント付きプレーンテキストへ変換する（コピー用）。"""
        lines: List[str] = [self._summary_label.text()]

        def _walk(item: "QTreeWidgetItem", depth: int) -> None:
            lines.append("  " * depth + item.text(0))
            for i in range(item.childCount()):
                _walk(item.child(i), depth + 1)

        for i in range(self._tree.topLevelItemCount()):
            _walk(self._tree.topLevelItem(i), 0)
        return "\n".join(lines)

    def set_theme(self, theme: str) -> None:
        """テーマを切り替える（"dark" / "light"）。"""
        if theme not in _ACTIVITY_THEMES or theme == self._theme:
            return
        self._theme = theme
        self._title_label.setStyleSheet(_ACTIVITY_THEMES[theme]["title"])
        self._summary_label.setStyleSheet(_ACTIVITY_THEMES[theme]["summary"])
        self._tree.setStyleSheet(_ACTIVITY_THEMES[theme]["tree"])

    def set_plan(
        self,
        workflow_plan: List[dict],
        workflow_status: Dict[str, str],
        step_status: Dict[str, Dict[str, str]],
        subtask_status: Optional[Dict[str, Dict[str, List[tuple]]]] = None,
    ) -> None:
        self._workflow_plan = list(workflow_plan)
        self._workflow_status = dict(workflow_status)
        self._step_status = {k: dict(v) for k, v in step_status.items()}
        if subtask_status is None:
            self._subtask_status = {}
        else:
            self._subtask_status = {
                wf_id: {st_id: list(subs) for st_id, subs in step_map.items()}
                for wf_id, step_map in subtask_status.items()
            }
        if self._global_started_at is None and self._workflow_plan:
            self._global_started_at = time.monotonic()
        self._update_timings()
        self._prune_stale_keys()
        self._render()

    # ---------- 内部 ----------

    def _update_timings(self) -> None:
        """ステータス変化から started_at / finished elapsed を追跡する。"""
        now = time.monotonic()

        for wf in self._workflow_plan:
            wf_id = str(wf.get("workflow_id", ""))
            wf_key = ("wf", wf_id)
            wf_st = _normalize_status(self._workflow_status.get(wf_id, ""))
            self._record_timing(wf_key, wf_st, now)

            step_map = self._step_status.get(wf_id, {})
            for step_id, _title in wf.get("steps", []):
                step_key = ("step", wf_id, step_id)
                st = _normalize_status(step_map.get(step_id, ""))
                self._record_timing(step_key, st, now)

            sub_map = self._subtask_status.get(wf_id, {})
            for step_id, sub_list in sub_map.items():
                for sub_id, _t, sub_state in sub_list:
                    key = ("sub", wf_id, step_id, sub_id)
                    self._record_timing(key, _normalize_status(sub_state), now)

            # Step が pending のままでも、子 Subtask の最早 started_at を
            # Step の started_at として擬似的に採用する（表示専用）。
            # Step status イベントが上流から届かない場合の表示欠落を防ぐ。
            for step_id, _title in wf.get("steps", []):
                step_key = ("step", wf_id, step_id)
                if step_key in self._timings:
                    continue
                earliest: Optional[float] = None
                for sub_id, _t, _s in sub_map.get(step_id, []):
                    sub_entry = self._timings.get(
                        ("sub", wf_id, step_id, sub_id)
                    )
                    if sub_entry is None:
                        continue
                    sub_started, _sub_fin = sub_entry
                    if earliest is None or sub_started < earliest:
                        earliest = sub_started
                if earliest is not None:
                    self._timings[step_key] = (earliest, None)

    def _record_timing(self, key: tuple, status: str, now: float) -> None:
        entry = self._timings.get(key)
        if status == "pending":
            return
        if status == "running":
            if entry is None:
                self._timings[key] = (now, None)
            return
        # done / failed / skipped → 確定
        if entry is None:
            # running を観測せずに完了した場合: 経過不明として 0.0 秒で確定。
            # （None のままだと _elapsed_for が now - started でカウントアップを
            #   継続するため、明示的に finished を 0.0 で確定させる）
            self._timings[key] = (now, 0.0)
        else:
            started, finished = entry
            if finished is None:
                self._timings[key] = (started, now - started)

    def _prune_stale_keys(self) -> None:
        """現在 plan に存在しないキーを _timings / _expanded から除去する。"""
        live: set = set()
        for wf in self._workflow_plan:
            wf_id = str(wf.get("workflow_id", ""))
            live.add(("wf", wf_id))
            for step_id, _ in wf.get("steps", []):
                live.add(("step", wf_id, step_id))
            for step_id, sub_list in self._subtask_status.get(wf_id, {}).items():
                for sub_id, _t, _s in sub_list:
                    live.add(("sub", wf_id, step_id, sub_id))
        for k in list(self._timings.keys()):
            if k not in live:
                self._timings.pop(k, None)
        for k in list(self._expanded.keys()):
            if k not in live:
                self._expanded.pop(k, None)

    def _elapsed_for(self, key: tuple, status: str, now: float) -> Optional[float]:
        if status == "pending":
            return None
        entry = self._timings.get(key)
        if entry is None:
            return None
        started, finished = entry
        if finished is not None:
            return finished
        return now - started

    def _snapshot_structure(self) -> tuple:
        """_render 必要性判定用の構造ハッシュ（ステータス含む）。"""
        parts: List[tuple] = []
        for wf in self._workflow_plan:
            wf_id = str(wf.get("workflow_id", ""))
            wf_st = self._workflow_status.get(wf_id, "")
            step_keys: List[tuple] = []
            for step_id, title in wf.get("steps", []):
                step_st = self._step_status.get(wf_id, {}).get(step_id, "")
                subs = tuple(
                    (sid, t, s)
                    for sid, t, s in self._subtask_status.get(wf_id, {}).get(
                        step_id, []
                    )
                )
                step_keys.append((step_id, title, step_st, subs))
            parts.append((wf_id, str(wf.get("workflow_name", "")), wf_st, tuple(step_keys)))
        return tuple(parts)

    def _current_workflow_id(self) -> Optional[str]:
        for wf in self._workflow_plan:
            wf_id = str(wf.get("workflow_id", ""))
            if _normalize_status(self._workflow_status.get(wf_id, "")) == "running":
                return wf_id
        # running が無ければ、未完了の最初の WF
        for wf in self._workflow_plan:
            wf_id = str(wf.get("workflow_id", ""))
            if _normalize_status(self._workflow_status.get(wf_id, "")) != "done":
                return wf_id
        return None

    def _render(self) -> None:
        """Plan モード経由の描画。Phase 3a (Q1=C): 統合レンダラへ委譲する。

        内部の ``_workflow_plan`` + ``_workflow_status`` + ``_step_status`` +
        ``_subtask_status`` + ``_timings`` を ``OrderedDict[str, WorkflowInstance]``
        へ変換し、``update_workflow_instances`` 経由で描画する。これにより
        Plan / Instances モードのレンダリングコードパスが 1 本化される。
        """
        proxy = _PlanModeStateProxy(self._build_workflows_from_plan_state())
        self.update_workflow_instances(proxy)
        # Plan モード固有: 現在 WF のステップ数を summary に上書きする
        self._override_summary_with_step_count()

    def _refresh_labels(self) -> None:
        """Plan モードの周期的ラベル更新。Phase 3a (Q1=C): 統合レンダラへ委譲する。

        構造に変化がない前提（``_on_tick`` から呼ばれる軽量パス）。
        ``update_workflow_instances`` 内でハッシュ一致を検出し
        ``_refresh_instances_labels`` のラベルのみ更新に分岐する。
        """
        proxy = _PlanModeStateProxy(self._build_workflows_from_plan_state())
        self.update_workflow_instances(proxy)
        self._override_summary_with_step_count()

    # ------------------------------------------------------------------
    # Phase 3a (Q1=C): Plan モード → WorkflowInstance dict 変換ヘルパ
    # ------------------------------------------------------------------

    def _build_workflows_from_plan_state(self) -> "OrderedDict[str, WorkflowInstance]":
        """``set_plan`` で蓄積された内部状態を ``OrderedDict[str, WorkflowInstance]`` に
        変換する。``update_workflow_instances`` が解釈できる形式に整える。

        - ``WorkflowInstance.steps`` (OrderedDict[step_id, StepView]) を充填
        - 各 StepView の started_at / finished_at を ``_timings`` から復元
        - Sub-agent / Fanout 子は ``StepView.children`` に格納（Phase 2 と同型）
        """
        from collections import OrderedDict as _OD
        from .workbench_state import StepView, WorkflowInstance

        workflows: "OrderedDict[str, WorkflowInstance]" = _OD()
        now = time.monotonic()

        def _timing_for(key: tuple) -> tuple:
            entry = self._timings.get(key)
            if entry is None:
                return (None, None)
            started, finished = entry
            if finished is None:
                return (started, None)
            # finished は経過秒なので started + finished で finished_at を復元
            return (started, started + finished)

        for wf in self._workflow_plan:
            wf_id = str(wf.get("workflow_id", ""))
            wf_name = str(wf.get("workflow_name", wf_id))
            wf_st = _normalize_status(self._workflow_status.get(wf_id, ""))
            wf_started, wf_finished = _timing_for(("wf", wf_id))
            inst = WorkflowInstance(
                instance_id=wf_id,
                workflow_id=wf_id,
                label=format_workflow_label_activity(wf_id, wf_name),
                app_id=None,
                status=wf_st,  # type: ignore[arg-type]
                started_at=wf_started,
                finished_at=wf_finished,
            )
            step_map = self._step_status.get(wf_id, {})
            sub_map = self._subtask_status.get(wf_id, {})
            for step_id, step_title in wf.get("steps", []):
                step_st = _normalize_status(step_map.get(step_id, ""))
                s_started, s_finished = _timing_for(("step", wf_id, step_id))
                sv = StepView(
                    id=step_id,
                    title=step_title,
                    status=step_st,  # type: ignore[arg-type]
                    started_at=s_started,
                    finished_at=s_finished,
                    parent_id=None,
                    kind="step",
                )
                for sub_id, sub_title, sub_state in sub_map.get(step_id, []):
                    sub_st = _normalize_status(sub_state)
                    sub_started, sub_finished = _timing_for(
                        ("sub", wf_id, step_id, sub_id)
                    )
                    sv.children.append(
                        StepView(
                            id=sub_id,
                            title=sub_title,
                            status=sub_st,  # type: ignore[arg-type]
                            started_at=sub_started,
                            finished_at=sub_finished,
                            parent_id=step_id,
                            kind="subagent",
                        )
                    )
                inst.steps[step_id] = sv
            workflows[wf_id] = inst
        return workflows

    def _override_summary_with_step_count(self) -> None:
        """Plan モード固有: summary ラベルに「ステップ: done/total」を反映する。

        統合レンダラ（``update_workflow_instances``）は ``"ステップ: --/--"`` を出力するため、
        Plan モードでは現在 WF のステップ数で上書きする。``_workflow_plan`` が空なら no-op。
        """
        if not self._workflow_plan:
            return
        now = time.monotonic()
        total_wf = len(self._workflow_plan)
        done_wf = sum(
            1
            for wf in self._workflow_plan
            if _normalize_status(
                self._workflow_status.get(str(wf.get("workflow_id", "")), "")
            )
            in ("done", "skipped")
        )
        cur_wf_id = self._current_workflow_id()
        cur_wf = next(
            (
                wf
                for wf in self._workflow_plan
                if str(wf.get("workflow_id", "")) == cur_wf_id
            ),
            None,
        )
        if cur_wf is not None:
            steps = list(cur_wf.get("steps", []))
            total_step = len(steps)
            step_map = self._step_status.get(cur_wf_id or "", {})
            done_step = sum(
                1
                for sid, _ in steps
                if _normalize_status(step_map.get(sid, "")) in ("done", "skipped")
            )
        else:
            total_step = 0
            done_step = 0
        global_elapsed = (
            (now - self._global_started_at)
            if self._global_started_at is not None
            else None
        )
        self._summary_label.setText(
            f"ワークフロー: {done_wf}/{total_wf}   "
            f"ステップ: {done_step}/{total_step}   "
            f"[{_fmt_elapsed(global_elapsed)}]"
        )

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key is not None:
            self._expanded[tuple(key)] = True

    def _on_item_collapsed(self, item: QTreeWidgetItem) -> None:
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key is not None:
            self._expanded[tuple(key)] = False

    def eventFilter(self, obj, event):  # type: ignore[override]
        # viewport の Resize 時にツリーの行高を再計算させる（折り返し対応）。
        if event is not None and event.type() == QEvent.Type.Resize:
            try:
                self._tree.scheduleDelayedItemsLayout()
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def _on_tick(self) -> None:
        # 構造変化がなければラベルのみ in-place 更新（経過時間更新）。
        if not self._workflow_plan:
            return
        if not self.isVisible():
            return
        self._refresh_labels()

    # ------------------------------------------------------------------
    # Wave 2: マルチ WorkflowInstance 描画
    # ------------------------------------------------------------------

    def _compute_instances_structure_hash(
        self, state: "WorkbenchState"
    ) -> tuple:
        """``state.workflows`` の構造ハッシュ。Phase 2 (Q7=B) で StepView.children を
        再帰的に取り込むよう拡張。経過時間は含めない。"""
        workflows = getattr(state, "workflows", None) or {}

        def _hash_step(sv) -> tuple:
            children = tuple(_hash_step(c) for c in getattr(sv, "children", []) or [])
            return (
                sv.id,
                getattr(sv, "kind", "step"),
                getattr(sv, "status", "pending"),
                children,
            )

        return tuple(
            (
                iid,
                getattr(inst, "label", ""),
                inst.status,
                tuple(_hash_step(sv) for sv in getattr(inst, "steps", {}).values()),
            )
            for iid, inst in workflows.items()
        )

    def update_workflow_instances(self, state: "WorkbenchState") -> None:
        """``state.workflows`` (OrderedDict[instance_id, WorkflowInstance]) を
        ルート直下のトップレベルノードとして描画する。

        Phase 2 (Q7=B 無制限ネスト): ``StepView.children`` を再帰的に walk して
        任意深さの container / Sub-agent / Fanout 子ノードを描画する。

        構造（instance_id 集合 / 各 status / children）に変化が無い場合は再構築を
        行わず、:meth:`_refresh_instances_labels` で経過時間ラベルのみ更新する
        （``tree.clear()`` による選択状態消失・性能劣化を回避するため）。
        """
        workflows = getattr(state, "workflows", None)
        if not workflows:
            return

        # 構造変化なしの場合はラベルのみ更新
        new_hash = self._compute_instances_structure_hash(state)
        if (
            self._instances_mode
            and self._last_snapshot == new_hash
            and self._items
        ):
            self._refresh_instances_labels(state)
            return
        self._last_snapshot = new_hash

        self._instances_mode = True
        # 旧 plan モードの状態をクリア
        self._workflow_plan = []
        self._workflow_status = {}
        self._step_status = {}
        self._subtask_status = {}

        sb = self._tree.verticalScrollBar()
        prev_scroll = sb.value() if sb is not None else 0

        self._tree.blockSignals(True)
        self._tree.clear()
        self._items.clear()

        now = time.monotonic()
        total = len(workflows)
        done = sum(
            1
            for inst in workflows.values()
            if inst.status in ("done", "skipped")
        )

        global_elapsed: Optional[float] = None
        starts = [
            inst.started_at for inst in workflows.values() if inst.started_at is not None
        ]
        if starts:
            global_elapsed = now - min(starts)
        self._summary_label.setText(
            f"ワークフロー: {done}/{total}   "
            f"ステップ: --/--   "
            f"[{_fmt_elapsed(global_elapsed)}]"
        )

        def _add_step_recursive(parent_item, instance_id: str, step_view) -> None:
            """StepView を再帰描画 (Q7=B 無制限ネスト)。"""
            step_key = ("wfi_step", instance_id, step_view.id)
            st = step_view.status if step_view.status in _ACTIVITY_EMOJI else "pending"
            emoji = _ACTIVITY_EMOJI.get(st, _ACTIVITY_EMOJI["pending"])
            step_elapsed: Optional[float] = None
            if getattr(step_view, "started_at", None) is not None:
                end = (
                    step_view.finished_at
                    if getattr(step_view, "finished_at", None) is not None
                    else now
                )
                step_elapsed = max(0.0, end - step_view.started_at)
            # container は title プレフィックス、step / subagent / fanout_child は通常表示
            kind = getattr(step_view, "kind", "step")
            if kind == "container":
                text = (
                    f"{emoji}  📁 {step_view.id}: {step_view.title}    "
                    f"[{_fmt_elapsed(step_elapsed)}]"
                )
            elif kind == "subagent":
                text = (
                    f"{emoji}  🤖 {step_view.title}    "
                    f"[{_fmt_elapsed(step_elapsed)}]"
                )
            elif kind == "fanout_child":
                text = (
                    f"{emoji}  ⤵ {step_view.id}: {step_view.title}    "
                    f"[{_fmt_elapsed(step_elapsed)}]"
                )
            else:
                text = (
                    f"{emoji}  {step_view.id}: {step_view.title}    "
                    f"[{_fmt_elapsed(step_elapsed)}]"
                )
            item = QTreeWidgetItem([text])
            item.setData(0, Qt.ItemDataRole.UserRole, step_key)
            parent_item.addChild(item)
            self._items[step_key] = item
            # 再帰: 任意深さの子
            for child in getattr(step_view, "children", []) or []:
                _add_step_recursive(item, instance_id, child)
            # container はデフォルト展開、その他は記憶優先
            default_expanded = (kind == "container") or (st == "running")
            item.setExpanded(self._expanded.get(step_key, default_expanded))

        for instance_id, inst in workflows.items():
            wfi_key = ("wfi", instance_id)
            emoji = _ACTIVITY_EMOJI.get(inst.status, _ACTIVITY_EMOJI["pending"])
            elapsed: Optional[float] = None
            if inst.started_at is not None:
                end = inst.finished_at if inst.finished_at is not None else now
                elapsed = max(0.0, end - inst.started_at)
            label = inst.label or inst.workflow_id or instance_id
            wf_text = f"{emoji}  {label}    [{_fmt_elapsed(elapsed)}]"
            wf_item = QTreeWidgetItem([wf_text])
            wf_item.setData(0, Qt.ItemDataRole.UserRole, wfi_key)
            self._tree.addTopLevelItem(wf_item)
            self._items[wfi_key] = wf_item

            # Step 子ノード（OrderedDict 挿入順）を再帰描画
            for step_view in inst.steps.values():
                _add_step_recursive(wf_item, instance_id, step_view)

            wf_item.setExpanded(self._expanded.get(wfi_key, True))

        self._tree.blockSignals(False)
        if sb is not None:
            sb.setValue(min(prev_scroll, sb.maximum()))

    def _refresh_instances_labels(self, state: "WorkbenchState") -> None:
        """instances モードで構造変化なし時、経過時間ラベルのみ in-place 更新する。

        選択・スクロール・展開状態を保持するため ``tree.clear()`` は行わない。
        ``update_workflow_instances`` の高頻度呼び出しに耐える軽量更新パス。
        Phase 2 (Q7=B): StepView.children も再帰的に in-place 更新。
        """
        workflows = getattr(state, "workflows", None) or {}
        now = time.monotonic()

        total = len(workflows)
        done = sum(
            1
            for inst in workflows.values()
            if inst.status in ("done", "skipped")
        )
        starts = [
            inst.started_at for inst in workflows.values() if inst.started_at is not None
        ]
        global_elapsed = (now - min(starts)) if starts else None
        self._summary_label.setText(
            f"ワークフロー: {done}/{total}   "
            f"ステップ: --/--   "
            f"[{_fmt_elapsed(global_elapsed)}]"
        )

        def _refresh_step(instance_id: str, step_view) -> None:
            step_key = ("wfi_step", instance_id, step_view.id)
            step_item = self._items.get(step_key)
            if step_item is not None:
                st = step_view.status if step_view.status in _ACTIVITY_EMOJI else "pending"
                emoji = _ACTIVITY_EMOJI.get(st, _ACTIVITY_EMOJI["pending"])
                step_elapsed: Optional[float] = None
                if getattr(step_view, "started_at", None) is not None:
                    end = (
                        step_view.finished_at
                        if getattr(step_view, "finished_at", None) is not None
                        else now
                    )
                    step_elapsed = max(0.0, end - step_view.started_at)
                kind = getattr(step_view, "kind", "step")
                if kind == "container":
                    text = f"{emoji}  📁 {step_view.id}: {step_view.title}    [{_fmt_elapsed(step_elapsed)}]"
                elif kind == "subagent":
                    text = f"{emoji}  🤖 {step_view.title}    [{_fmt_elapsed(step_elapsed)}]"
                elif kind == "fanout_child":
                    text = f"{emoji}  ⤵ {step_view.id}: {step_view.title}    [{_fmt_elapsed(step_elapsed)}]"
                else:
                    text = f"{emoji}  {step_view.id}: {step_view.title}    [{_fmt_elapsed(step_elapsed)}]"
                step_item.setText(0, text)
            for child in getattr(step_view, "children", []) or []:
                _refresh_step(instance_id, child)

        for instance_id, inst in workflows.items():
            wfi_key = ("wfi", instance_id)
            item = self._items.get(wfi_key)
            if item is not None:
                emoji = _ACTIVITY_EMOJI.get(inst.status, _ACTIVITY_EMOJI["pending"])
                elapsed: Optional[float] = None
                if inst.started_at is not None:
                    end = inst.finished_at if inst.finished_at is not None else now
                    elapsed = max(0.0, end - inst.started_at)
                label = inst.label or inst.workflow_id or instance_id
                item.setText(0, f"{emoji}  {label}    [{_fmt_elapsed(elapsed)}]")

            for step_view in inst.steps.values():
                _refresh_step(instance_id, step_view)

    def _on_selection_changed(self) -> None:
        """ツリー選択変化時、WorkflowInstance ノードが選択されていれば emit。"""
        if not self._instances_mode:
            return
        items = self._tree.selectedItems()
        if not items:
            return
        key = items[0].data(0, Qt.ItemDataRole.UserRole)
        if key is None:
            return
        try:
            key_t = tuple(key)
        except TypeError:
            return
        if len(key_t) >= 2 and key_t[0] == "wfi":
            instance_id = str(key_t[1])
            self.workflow_instance_selected.emit(instance_id)


class FooterWidget(QWidget):
    """Footer ペイン: コンテキスト使用率, モデル, 経過時間, Cost, Reqs, Tools(Step), Skills(Step)、そして「📊 詳細」ボタン。

    Wave 4 拡張:
    - 1Hz QTimer による自動再描画 (経過時間とコストを live 更新)
    - 多項目を 1 つの ``QLabel`` (wordWrap=True) に表示
    - 区切り ``|`` の前後に ZWSP を挿入し自然な折り返しを可能にする
    - Cost / Premium Requests を常時表示 (未取得値は ``-``、捏造禁止)
    """

    # 項目名（濃色 bold）と値（中間色）の配色。
    _LABEL_COLOR = "#222222"
    _VALUE_COLOR = "#666666"
    _WARN_COLOR = "#ff6600"
    _SEP_COLOR = "#bdbdbd"
    _TOPN = 5  # Tools / Skills 表示上限件数

    # 「📊 詳細」ボタンクリック時に emit。page_workbench がポップアップを開く。
    detail_clicked = Signal()

    def __init__(self, state: WorkbenchState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._label = QLabel()
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setWordWrap(True)
        self._label.setStyleSheet("padding: 2px; font-size: 9pt;")

        # 統計情報ボタン（10個以上の統計をポップアップで表示）
        self._detail_btn = QToolButton()
        self._detail_btn.setText(self.tr("📊 統計情報"))
        self._detail_btn.setToolTip(
            self.tr("現在の統計スナップショットと「今回の実行履歴」をタブで表示します。")
        )
        self._detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._detail_btn.setStyleSheet(
            "QToolButton {"
            f" color: {self._LABEL_COLOR};"
            " background: transparent;"
            " border: 1px solid #cfd3da;"
            " border-radius: 3px;"
            " padding: 1px 6px;"
            " font-size: 9pt;"
            "}"
            "QToolButton:hover { background: #eef2f7; }"
        )
        self._detail_btn.clicked.connect(self.detail_clicked)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._label, 1)
        layout.addWidget(self._detail_btn, 0, Qt.AlignmentFlag.AlignRight)

        # 表示通貨 / locale (settings から後で注入可)。デフォルト ja+both。
        self._currency: str = "auto"
        self._locale: str = "ja"

        self._update()

        # --- 1Hz ライブ更新タイマ ---
        # 経過時間と累積コストを毎秒更新する。テスト環境 (offscreen) でも
        # QTimer は動くが、可視時のみ描画する _on_tick() でコストを抑える。
        try:
            from PySide6.QtCore import QTimer  # type: ignore
            self._tick = QTimer(self)
            self._tick.setInterval(1000)
            self._tick.timeout.connect(self._on_tick)
            self._tick.start()
        except Exception:
            self._tick = None  # pragma: no cover

    # ------------------------------------------------------------------
    # 表示パラメータ
    # ------------------------------------------------------------------
    def set_display_currency(self, currency: str, *, locale: Optional[str] = None) -> None:
        """通貨表示モード ("auto"|"usd"|"jpy"|"both") を設定する。"""
        self._currency = (currency or "auto").lower()
        if locale is not None:
            self._locale = locale
        self._update()

    def _on_tick(self) -> None:
        if not self.isVisible():
            return
        self._update()

    @classmethod
    def _fmt_item(cls, label: str, value: str, *, value_color: Optional[str] = None) -> str:
        # NOTE: 既存テスト互換のため、内部 HTML 構造は維持 (font-weight:bold span 等)。
        # text_kinsoku.wrap_nowrap_unit は新規 Cost/Reqs 行で利用する。
        vc = value_color or cls._VALUE_COLOR
        return (
            f"<span style='color:{cls._LABEL_COLOR}; font-weight:bold;'>{label}:</span> "
            f"<span style='color:{vc};'>{value}</span>"
        )

    @classmethod
    def _fmt_counts(cls, counts: dict) -> str:
        if not counts:
            return "-"
        items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        top = items[: cls._TOPN]
        rest = len(items) - len(top)
        text = ", ".join(f"{name}×{cnt}" for name, cnt in top)
        if rest > 0:
            text += f" +{rest} more"
        return text

    def _update(self) -> None:
        parts = []

        # Context Window
        if self.state.context_limit > 0:
            pct = (self.state.context_current * 100) // self.state.context_limit
            value = (
                f"{self.state.context_current:,} / {self.state.context_limit:,} ({pct}%)"
            )
            value_color = self._WARN_COLOR if pct >= 80 else None
            parts.append(self._fmt_item("Context", value, value_color=value_color))

        # Model
        if self.state.model:
            parts.append(self._fmt_item("Model", self.state.model))

        # Elapsed
        import time

        now = time.monotonic()
        elapsed = now - self.state.workflow_started_at
        h = int(elapsed) // 3600
        m = (int(elapsed) % 3600) // 60
        s = int(elapsed) % 60
        parts.append(self._fmt_item("Elapsed", f"{h:02d}:{m:02d}:{s:02d}"))

        # --- Step Elapsed (現 Step) ---
        try:
            step_id = self.state.current_running_step_id or self.state.last_known_step_id
            step_started: Optional[float] = None
            if step_id:
                for sv in self.state.steps:
                    if getattr(sv, "id", None) == step_id and getattr(sv, "started_at", None):
                        step_started = float(sv.started_at)
                        break
            if step_started is not None:
                se = max(0, int(now - step_started))
                parts.append(
                    self._fmt_item(
                        f"Step {step_id}",
                        f"{se // 3600:02d}:{(se % 3600) // 60:02d}:{se % 60:02d}",
                    )
                )
        except Exception:
            pass

        # --- Cost (累積 AI Credit) ---
        try:
            from .text_kinsoku import format_cost
            cost_str = format_cost(
                getattr(self.state, "cost_usd_total", None),
                getattr(self.state, "cost_jpy_total", None),
                currency=self._currency,
                locale=self._locale,
            )
        except Exception:
            cost_str = "-"
        parts.append(self._fmt_item("Cost", cost_str))

        # --- Premium Requests 累積 ---
        reqs = int(getattr(self.state, "premium_requests_total", 0) or 0)
        parts.append(self._fmt_item("Reqs", str(reqs)))

        # Tools (Step) — 表示対象 Step の集計
        try:
            tool_counts = self.state.current_tool_counts()
        except AttributeError:
            tool_counts = {}
        parts.append(self._fmt_item("Tools (Step)", self._fmt_counts(tool_counts)))

        # Skills (Step) — 表示対象 Step の集計
        try:
            skill_counts = self.state.current_skill_counts()
        except AttributeError:
            skill_counts = {}
        parts.append(self._fmt_item("Skills (Step)", self._fmt_counts(skill_counts)))

        # 区切りに ZWSP を入れて自然な折り返しを促す (text_kinsoku.join_items と同等の形)
        sep = (
            "\u200b"
            f"<span style='color:{self._VALUE_COLOR};'> | </span>"
            "\u200b"
        )
        html = sep.join(parts)
        # 行頭禁則の簡易補正
        try:
            from .text_kinsoku import apply_cjk_kinsoku
            html = apply_cjk_kinsoku(html)
        except Exception:
            pass
        self._label.setText(html)

    def update_state(self, state: WorkbenchState) -> None:
        self.state = state
        self._update()
