"""hve.gui.stats_history_view — 「今回の実行履歴」タブビュー。

`WorkbenchState.stats_history` の `WorkflowStatsSnapshot` を QTreeWidget で表示する。
- 親行: Workflow（合計値）
- 子行: 各 Step（完了時のスナップショット）
- 列: Workflow/Step, Context, Model, 実行時間, AI Credit, Tools, Skills

FR-RTO-07: Step 行の値は当該 Step へ帰属したイベントだけから算出する。
- AI Credit: 当該 Step 帰属の ``usage_credit`` 合計（``aiu_nano_own``）。
  帰属イベントが無ければ ``-``。隣接 Step の累積差分などの推定値で補わない。
- Model: 当該 Step 帰属のモデル別呼び出し回数。
- Workflow 親行の AI Credit は Workflow 累積（Step へ帰属できない Fleet wave の
  消費を含む真値）のため、子行の合計と一致しないことがある。理由は凡例へ明示する。
- Workflow 親行の Context は瞬間値のため合算せず、最後に完了した Step の値を示す。

リアルタイム更新:
- `stats_history_updated` シグナルを購読し、1 秒スロットルで再描画する。
- 関連シグナル（context_updated / tool_counts_updated / skill_counts_updated）も同様。

Tools / Skills / Model は Top-5 + ``+N more`` 形式。セル D-click で全件ポップアップを表示する。

CSV エクスポート:
- ツリー上部の 📋 ボタンで全行（ヘッダー + Workflow 親 + Step 子）を CSV としてクリップボードへ。
- 詳細フォーマットは ``build_csv`` 関数 docstring 参照。
"""

from __future__ import annotations

import csv
import io
import time
from typing import Iterable, List, Optional, Sequence

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .copy_button import CopyButton
from .workbench_state import (
    StepStatsSnapshot,
    WorkbenchState,
    WorkflowStatsSnapshot,
)


_DASH = "-"
_TOPN = 5
_THROTTLE_MS = 1000
_NANO_PER_AIU = 1_000_000_000

# 列定義
COL_NAME = 0
COL_CONTEXT = 1
COL_MODEL = 2
COL_ELAPSED = 3
COL_AI_CREDIT = 4
COL_TOOLS = 5
COL_SKILLS = 6
_COLUMN_HEADERS = (
    "Workflow / Step",
    "Context",
    "Model",
    "実行時間",
    "AI Credit",
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
    return _counts_topn_text(counts, empty=_DASH, top=top)


def _counts_topn_text(counts: dict, *, empty: str, top: int = _TOPN) -> str:
    """Top-N + ``+N more`` 形式。空 dict は `empty` を返す（UI=`-` / CSV=`""`）。"""
    if not counts:
        return empty
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


# ----------------------------------------------------------------------
# AI Credit / CSV ヘルパー（純粋関数）
# ----------------------------------------------------------------------


def _fmt_aiu(nano: Optional[int], *, decimals: int = 4) -> str:
    """Nano AIU を `0.1234 AIU` 形式に整形。None / 0 / 負値は `-`。"""
    if nano is None:
        return _DASH
    try:
        n = int(nano)
    except (TypeError, ValueError):
        return _DASH
    if n <= 0:
        return _DASH
    return f"{n / _NANO_PER_AIU:.{decimals}f} AIU"


def _sorted_steps_by_finish(
    steps: Sequence[StepStatsSnapshot],
) -> List[StepStatsSnapshot]:
    """`finished_at` 昇順でソート。None は末尾。安定ソートで元順序を保持。"""
    return sorted(
        steps,
        key=lambda s: (s.finished_at is None, s.finished_at or 0.0),
    )


def _csv_pct(cur: Optional[int], lim: Optional[int]) -> str:
    try:
        if cur is None or lim is None:
            return ""
        c = int(cur)
        l = int(lim)
    except (TypeError, ValueError):
        return ""
    if l <= 0:
        return ""
    return f"{(c * 100 / l):.1f}"


def _csv_aiu(nano: Optional[int], *, decimals: int = 6) -> str:
    """CSV セル用の AIU 数値文字列。未取得は空欄。"""
    if nano is None:
        return ""
    try:
        n = int(nano)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    return f"{n / _NANO_PER_AIU:.{decimals}f}"


def _csv_counts_topn(counts: dict, top: int = _TOPN) -> str:
    """CSV セル用 (Top-N + `+N more`)。空 dict は空文字。"""
    return _counts_topn_text(counts, empty="", top=top)


# CSV formula injection 対策（OWASP CSV Injection 推奨）
_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_csv_cell(value: object) -> str:
    """Excel/Sheets での formula injection を防ぐサニタイズ。

    先頭が ``= + - @ TAB CR`` のテキスト値は ``'`` を付与してテキスト扱いに固定する。
    数値列（``_csv_aiu`` 等の出力）に対しては呼ばないこと（先頭 `-` の数値リスクは
    本実装では発生しないが、汎用性のため）。
    """
    s = "" if value is None else str(value)
    if s and s[0] in _CSV_INJECTION_PREFIXES:
        return "'" + s
    return s


def _csv_safe_int(value: object) -> str:
    """CSV セル用 int 文字列化。型不一致は空欄（捏造禁止）。"""
    if value is None:
        return ""
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return ""


_CSV_HEADERS: tuple = (
    "Type",
    "Workflow",
    "Step",
    "Context",
    "Limit",
    "Pct",
    # モデル別呼び出し回数（Top-N + `+N more`）。Step 行は当該 Step 帰属分のみ。
    "Model",
    "ElapsedSec",
    "ElapsedHMS",
    "AiuTotal",
    # FR-RTO-07: 当該 Step へ帰属した `usage_credit` の実測合計。
    # 帰属イベントが無ければ空欄（累積差分などの推定値で補わない）。
    "AiuOwn",
    "ToolsTop",
    "SkillsTop",
    "Status",
)


def build_csv(
    history: Iterable[WorkflowStatsSnapshot],
    *,
    now_monotonic: Optional[float] = None,
) -> str:
    """履歴を RFC 4180 準拠の CSV 文字列へ変換する。

    - 1 行目: ヘッダー（`_CSV_HEADERS`）
    - Workflow 親行: Type=workflow / Step=空 / AiuOwn=空 / Status=空。
      Model は子 Step のモデル別合計。
    - Step 子行: Type=step / Workflow=親 workflow 名（フィルタ用に再掲）/
      Workflow 累積 AiuTotal + Step 実測 AiuOwn
    - 改行コード: ``\\r\\n``（Excel 互換）
    - 未取得値は空欄（捏造禁止）
    - CSV formula injection 対策として、テキスト列の ``=+-@`` 先頭値は ``'`` を付与
    - 文字エンコーディング: 呼び出し側の責務（クリップボード経由は UTF-8 として渡る）

    Args:
        history: 履歴スナップショット列。
        now_monotonic: ``running`` workflow の経過秒計算用基準時刻。
            ``None`` の場合は ``time.monotonic()`` を呼ぶ（決定性が必要なテストでは明示）。
    """
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(_CSV_HEADERS)

    for wf in history:
        wf_name = wf.workflow_name or wf.workflow_id or ""
        wf_elapsed = wf.elapsed_sec
        if wf_elapsed is None and wf.started_at is not None:
            base = now_monotonic if now_monotonic is not None else time.monotonic()
            wf_elapsed = max(0.0, base - wf.started_at)
        wf_elapsed_sec = "" if wf_elapsed is None else f"{int(wf_elapsed)}"
        wf_elapsed_hms = "" if wf_elapsed is None else _fmt_elapsed(int(wf_elapsed))
        tools_total = _agg_workflow_counts(wf, "tool_counts")
        skills_total = _agg_workflow_counts(wf, "skill_counts")
        models_total = _agg_workflow_counts(wf, "model_counts")

        writer.writerow([
            "workflow",
            _sanitize_csv_cell(wf_name),
            "",
            _csv_safe_int(wf.context_current),
            _csv_safe_int(wf.context_limit),
            _csv_pct(wf.context_current, wf.context_limit),
            _sanitize_csv_cell(_csv_counts_topn(models_total)),
            wf_elapsed_sec,
            wf_elapsed_hms,
            _csv_aiu(wf.sdk_aiu_total_nano),
            "",
            _sanitize_csv_cell(_csv_counts_topn(tools_total)),
            _sanitize_csv_cell(_csv_counts_topn(skills_total)),
            "",
        ])

        sorted_steps = _sorted_steps_by_finish(wf.steps)
        for st in sorted_steps:
            elapsed_sec = "" if st.elapsed_sec is None else f"{int(st.elapsed_sec)}"
            elapsed_hms = (
                "" if st.elapsed_sec is None else _fmt_elapsed(int(st.elapsed_sec))
            )
            writer.writerow([
                "step",
                _sanitize_csv_cell(wf_name),
                _sanitize_csv_cell(st.step_id),
                _csv_safe_int(st.context_current),
                _csv_safe_int(st.context_limit),
                _csv_pct(st.context_current, st.context_limit),
                _sanitize_csv_cell(_csv_counts_topn(st.model_counts)),
                elapsed_sec,
                elapsed_hms,
                _csv_aiu(st.sdk_aiu_total_nano),
                _csv_aiu(st.aiu_nano_own),
                _sanitize_csv_cell(_csv_counts_topn(st.tool_counts)),
                _sanitize_csv_cell(_csv_counts_topn(st.skill_counts)),
                _sanitize_csv_cell(st.status or ""),
            ])

    return buf.getvalue()


# AI Credit 列を数値ソートするための SortRole（UserRole+1）
_SORT_ROLE = Qt.ItemDataRole.UserRole + 1


def _aiu_sort_key(nano: Optional[int]) -> int:
    """AI Credit 列のソート用 int キー。未取得 / 0 / 負値は ``-1``（表示の `-` と整合）。"""
    if nano is None:
        return -1
    try:
        n = int(nano)
    except (TypeError, ValueError):
        return -1
    if n <= 0:
        return -1
    return n


class _StatsTreeItem(QTreeWidgetItem):
    """AI Credit 列を数値ソートする QTreeWidgetItem。他列はデフォルトのテキスト比較。"""

    def __lt__(self, other: "QTreeWidgetItem") -> bool:  # type: ignore[override]
        tree = self.treeWidget()
        column = tree.sortColumn() if tree is not None else 0
        if column == COL_AI_CREDIT:
            a = self.data(COL_AI_CREDIT, _SORT_ROLE)
            b = other.data(COL_AI_CREDIT, _SORT_ROLE)
            # None は -1 として最小扱い（昇順時は先頭、降順時は末尾）
            return (a if isinstance(a, (int, float)) else -1) < (
                b if isinstance(b, (int, float)) else -1
            )
        # super().__lt__() は再帰になるため、デフォルトの text 比較を直接実装
        return self.text(column) < other.text(column)


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

        # --- ヘッダ行（凡例 + CSV コピー） ---
        header_bar = QHBoxLayout()
        header_bar.setContentsMargins(0, 0, 0, 0)
        header_bar.setSpacing(6)
        legend = QLabel(
            self.tr(
                "Step 行は当該 Step へ帰属したイベントだけから算出します"
                "（取得できない項目は「-」）。"
                "Workflow 行の AI Credit は累積のため、SDK Fleet mode へ委譲した並列 Wave の"
                "消費を含み、子 Step の合計と一致しないことがあります。"
                "Workflow 行の Context は最後に完了した Step の値、"
                "並列 Wave の Step の実行時間は Wave 全体の所要時間です。"
            )
        )
        legend.setStyleSheet("font-size: 8pt;")
        legend.setProperty("hveRole", "muted")
        legend.setWordWrap(True)
        header_bar.addWidget(legend, 1)
        self._csv_copy_btn = CopyButton(
            get_text=self._csv_text,
            tooltip=self.tr("今回の実行履歴を CSV としてクリップボードへコピー"),
            parent=self,
        )
        header_bar.addWidget(self._csv_copy_btn, 0)
        layout.addLayout(header_bar)

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
        header.setSectionResizeMode(COL_AI_CREDIT, QHeaderView.ResizeMode.ResizeToContents)
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

    def _csv_text(self) -> str:
        """CopyButton 用 CSV 生成。例外は CopyButton 側で握って tooltip 表示される。"""
        return build_csv(self._state.stats_history)

    def _build_workflow_item(self, wf: WorkflowStatsSnapshot) -> QTreeWidgetItem:
        name = wf.workflow_name or wf.workflow_id or "(unknown)"
        tools_total = _agg_workflow_counts(wf, "tool_counts")
        skills_total = _agg_workflow_counts(wf, "skill_counts")
        models_total = _agg_workflow_counts(wf, "model_counts")
        elapsed = wf.elapsed_sec
        if elapsed is None and wf.started_at is not None:
            elapsed = max(0.0, time.monotonic() - wf.started_at)
        item = _StatsTreeItem(
            [
                f"[Workflow] {name}",
                _fmt_context(wf.context_current, wf.context_limit),
                _fmt_counts(models_total),
                _fmt_elapsed(elapsed),
                _fmt_aiu(wf.sdk_aiu_total_nano),
                _fmt_counts(tools_total),
                _fmt_counts(skills_total),
            ]
        )
        # ソート/再利用用に raw データを保持
        item.setData(COL_TOOLS, Qt.ItemDataRole.UserRole, tools_total)
        item.setData(COL_SKILLS, Qt.ItemDataRole.UserRole, skills_total)
        item.setData(COL_MODEL, Qt.ItemDataRole.UserRole, models_total)
        item.setData(COL_NAME, Qt.ItemDataRole.UserRole, ("workflow", wf.workflow_id, wf.run_id))
        item.setData(COL_AI_CREDIT, Qt.ItemDataRole.UserRole, wf.sdk_aiu_total_nano)
        # AI Credit 列の数値ソート用キー（未取得 / 0 / 負値は -1 で表示と整合）
        item.setData(COL_AI_CREDIT, _SORT_ROLE, _aiu_sort_key(wf.sdk_aiu_total_nano))
        item.setToolTip(
            COL_CONTEXT,
            self.tr("Workflow 行の Context は瞬間値のため合算せず、最後に完了した Step の値を示します。"),
        )
        item.setToolTip(
            COL_AI_CREDIT,
            self.tr(
                "Workflow 累積（Step へ帰属できない並列 Wave の消費を含む）。"
                "子 Step の合計と一致しないことがあります。"
            ),
        )

        # Step は finished_at 昇順で並べる
        for st in _sorted_steps_by_finish(wf.steps):
            item.addChild(self._build_step_item(st))
        return item

    def _build_step_item(self, st: StepStatsSnapshot) -> QTreeWidgetItem:
        # FR-RTO-07: AI Credit セルは当該 Step へ帰属した実測消費のみ。
        # 帰属イベントが無ければ `-`（累積差分などの推定値で補わない）。
        item = _StatsTreeItem(
            [
                f"  {st.step_id}",
                _fmt_context(st.context_current, st.context_limit),
                _fmt_counts(st.model_counts),
                _fmt_elapsed(st.elapsed_sec),
                _fmt_aiu(st.aiu_nano_own),
                _fmt_counts(st.tool_counts),
                _fmt_counts(st.skill_counts),
            ]
        )
        item.setData(COL_TOOLS, Qt.ItemDataRole.UserRole, dict(st.tool_counts))
        item.setData(COL_SKILLS, Qt.ItemDataRole.UserRole, dict(st.skill_counts))
        item.setData(COL_MODEL, Qt.ItemDataRole.UserRole, dict(st.model_counts))
        item.setData(COL_NAME, Qt.ItemDataRole.UserRole, ("step", st.step_id, st.status))
        # AI Credit の raw 値（Workflow 累積, Step 実測）を保持
        item.setData(
            COL_AI_CREDIT,
            Qt.ItemDataRole.UserRole,
            {"total_nano": st.sdk_aiu_total_nano, "own_nano": st.aiu_nano_own},
        )
        # AI Credit 列の数値ソート用キー（表示と一致させるため実測値で比較）
        item.setData(COL_AI_CREDIT, _SORT_ROLE, _aiu_sort_key(st.aiu_nano_own))
        # status 表示（tooltip）
        item.setToolTip(COL_NAME, f"status: {st.status}")
        if st.aiu_nano_own is None:
            item.setToolTip(
                COL_AI_CREDIT,
                self.tr(
                    "この Step へ帰属した課金イベントがないため取得できません。"
                    "SDK Fleet mode へ委譲した並列 Wave の消費は Workflow 行にのみ計上されます。"
                ),
            )
        return item

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        if column not in (COL_TOOLS, COL_SKILLS, COL_MODEL):
            return
        counts = item.data(column, Qt.ItemDataRole.UserRole)
        if not isinstance(counts, dict) or not counts:
            return
        if column == COL_TOOLS:
            title = self.tr("Tools 全件")
        elif column == COL_SKILLS:
            title = self.tr("Skills 全件")
        else:
            title = self.tr("Model 全件")
        QMessageBox.information(self, title, _full_counts_text(counts))
