"""hve.gui.stats_detail_popup — Step 2 Footer の「📊 詳細」ボタンから開く統計詳細ポップアップ。

VS Code GitHub Copilot のコンテキストウィンドウ表示を踏襲したレイアウト:
- ヘッダ: 「コンテキスト ウィンドウ」+ ``current / limit (pct%)`` + プログレスバー
- カテゴリブロック（System / User Context / Reasoning & Cache / Latency / Step Activity /
  Compaction / その他）: 各行は「項目名（左・濃色 bold）……値（右・中間色）」

ノンモーダル (``Qt.Popup``) で表示し、外側クリックで自動的に閉じる。
表示時点のスナップショットを描画し、その後の状態変化は再オープンするまで反映しない。
SDK 未取得値は捏造禁止のため ``-`` で表示する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QProgressBar,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .workbench_state import WorkbenchState


# 配色（VS Code Light を踏襲した穏やかな寒色系）
_LABEL_COLOR = "#222222"   # 項目名（濃色・太字）
_VALUE_COLOR = "#5a6473"   # 値（中間色）
_SECTION_COLOR = "#0b6bcb"  # セクション見出し
_MUTED_COLOR = "#8a8f97"   # 補助テキスト
_DASH = "-"  # SDK 未取得値の表示


@dataclass(frozen=True)
class StatItem:
    label: str
    value: str


@dataclass(frozen=True)
class StatSection:
    title: str
    items: Tuple[StatItem, ...]


def _fmt_int(v: Optional[int]) -> str:
    if v is None:
        return _DASH
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return _DASH


def _fmt_pct_of(v: Optional[int], total: Optional[int]) -> str:
    if v is None or total is None or total <= 0:
        return _DASH
    return f"{(int(v) * 100 / total):.1f}%"


def _fmt_ms(v: Optional[float]) -> str:
    if v is None:
        return _DASH
    try:
        return f"{float(v):.1f} ms"
    except (TypeError, ValueError):
        return _DASH


def _fmt_counts(counts: dict, *, top: int = 5) -> str:
    if not counts:
        return _DASH
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    head = items[:top]
    rest = len(items) - len(head)
    text = ", ".join(f"{name}×{cnt}" for name, cnt in head)
    if rest > 0:
        text += f" +{rest} more"
    return text


def _fmt_elapsed(seconds: int) -> str:
    try:
        v = max(0, int(seconds))
    except (TypeError, ValueError):
        return _DASH
    return f"{v // 3600:02d}:{(v % 3600) // 60:02d}:{v % 60:02d}"


def build_snapshot(state: WorkbenchState) -> Tuple[List[StatSection], dict]:
    """WorkbenchState の現在値からスナップショットを構築する。

    Returns:
        (sections, header) のタプル。``header`` は ``{"current","limit","pct"}``。
    """
    cur = int(state.context_current or 0)
    lim = int(state.context_limit or 0)
    pct = (cur * 100 / lim) if lim > 0 else 0.0

    # --- System ---
    system_items = [
        StatItem(
            "System Instructions",
            f"{_fmt_int(state.context_system_tokens)} ({_fmt_pct_of(state.context_system_tokens, lim)})",
        ),
        StatItem(
            "Tool Definitions",
            f"{_fmt_int(state.context_tool_definitions_tokens)} ({_fmt_pct_of(state.context_tool_definitions_tokens, lim)})",
        ),
    ]
    sys_known = (state.context_system_tokens or 0) + (state.context_tool_definitions_tokens or 0)

    # --- User Context ---
    # SDK は Messages と Tool Results を分離提供しないため統合表示。
    conv = state.context_conversation_tokens
    user_items = [
        StatItem(
            "User Context (Messages + Tool Results)",
            f"{_fmt_int(conv)} ({_fmt_pct_of(conv, lim)})",
        ),
        StatItem("Messages 件数", _fmt_int(state.context_msgs)),
    ]
    user_known = conv or 0

    # --- Reasoning & Cache（累積） ---
    # SDK が assistant.usage トップレベルで cache_write_tokens / reasoning_tokens を
    # 提供しない（または常に 0）ケースがあるため、token_details (billing) 側に
    # 同名カテゴリの累積があればそちらを併記する。
    billing = state.billing_token_totals or {}
    cache_write_total = state.assistant_cache_write_total
    reasoning_total = state.assistant_reasoning_tokens_total
    cache_write_label = "Cache write (累積)"
    reasoning_label = "Reasoning tokens (累積)"
    if cache_write_total == 0 and billing.get("cache_write", 0) > 0:
        cache_write_total = int(billing["cache_write"])
        cache_write_label = "Cache write (累積, billing)"
    if reasoning_total == 0 and billing.get("reasoning", 0) > 0:
        reasoning_total = int(billing["reasoning"])
        reasoning_label = "Reasoning tokens (累積, billing)"
    rc_items = [
        StatItem("Input tokens (累積)", _fmt_int(state.assistant_input_tokens_total)),
        StatItem("Output tokens (累積)", _fmt_int(state.assistant_output_tokens_total)),
        StatItem(reasoning_label, _fmt_int(reasoning_total)),
        StatItem("Cache read (累積)", _fmt_int(state.assistant_cache_read_total)),
        StatItem(cache_write_label, _fmt_int(cache_write_total)),
        StatItem("assistant.usage 発火回数", _fmt_int(state.assistant_usage_count)),
    ]
    # 課金カテゴリ別累積（billing token_details）
    if state.billing_token_totals:
        rc_items.append(
            StatItem(
                "Billing categories",
                _fmt_counts(state.billing_token_totals, top=5),
            )
        )

    # --- Latency ---
    avg_ttft = (
        (state.ttft_sum_ms / state.ttft_count) if state.ttft_count > 0 else None
    )
    latency_items = [
        StatItem("TTFT (初回)", _fmt_ms(state.ttft_first_ms)),
        StatItem("TTFT (直近)", _fmt_ms(state.ttft_last_ms)),
        StatItem("TTFT (平均)", _fmt_ms(avg_ttft)),
        StatItem("TTFT 観測回数", _fmt_int(state.ttft_count)),
        StatItem(
            "Inter-token latency (直近)",
            _fmt_ms(state.assistant_inter_token_latency_ms_last),
        ),
    ]

    # --- Step Activity（現 Step or 最後に running だった Step） ---
    sid = state.current_running_step_id or state.last_known_step_id
    step_items = [
        StatItem("対象 Step", sid or _DASH),
        StatItem("Tools (Step)", _fmt_counts(state.current_tool_counts())),
        StatItem("Skills (Step)", _fmt_counts(state.current_skill_counts())),
    ]

    # --- Compaction ---
    compaction_items = [
        StatItem("圧縮実行回数", _fmt_int(state.compaction_count)),
        StatItem("削減トークン累積", _fmt_int(state.compaction_tokens_removed_total)),
    ]

    # --- Permission ---
    permission_items = [
        StatItem("Permission リクエスト数", _fmt_int(state.permission_count)),
    ]

    # --- Cost (Wave 4) ---
    # 料金表が未注入 / 計算不能な場合は捏造禁止のため "-" のまま表示する。
    cost_method = getattr(state, "cost_method_last", "") or _DASH
    cost_reason = getattr(state, "cost_unavailable_reason", "") or ""
    try:
        from .text_kinsoku import format_cost
        cost_usd_total = getattr(state, "cost_usd_total", None)
        cost_jpy_total = getattr(state, "cost_jpy_total", None)
        cost_disp = format_cost(cost_usd_total, cost_jpy_total, currency="both", locale="ja")
    except Exception:
        cost_disp = _DASH
    pricing_obj = getattr(state, "pricing_snapshot", None)
    pricing_fetched_at = ""
    pricing_status = ""
    if pricing_obj is not None:
        pricing_fetched_at = str(getattr(pricing_obj, "fetched_at", "") or "")
        pricing_status = str(getattr(pricing_obj, "status", "") or "")
    cost_items = [
        StatItem("累積コスト", cost_disp),
        StatItem("Premium Requests 累積", _fmt_int(getattr(state, "premium_requests_total", 0))),
        StatItem("計算方式", cost_method or _DASH),
        StatItem("USD/JPY レート", _fmt_int(int(getattr(state, "pricing_usd_jpy_rate", 0) or 0))),
        StatItem("料金表 取得日時", pricing_fetched_at or _DASH),
        StatItem("料金表 ステータス", pricing_status or _DASH),
    ]
    if cost_reason:
        cost_items.append(StatItem("未計算理由", cost_reason))

    # --- Elapsed (Wave 4) ---
    import time as _time
    now = _time.monotonic()
    wf_elapsed = max(0, int(now - float(state.workflow_started_at or now)))
    elapsed_items = [
        StatItem("Workflow 経過", _fmt_elapsed(wf_elapsed)),
    ]
    sid_for_elapsed = state.current_running_step_id or state.last_known_step_id
    if sid_for_elapsed:
        step_started: Optional[float] = None
        for sv in state.steps:
            if getattr(sv, "id", None) == sid_for_elapsed and getattr(sv, "started_at", None):
                step_started = float(sv.started_at)
                break
        if step_started is not None:
            elapsed_items.append(
                StatItem(f"Step {sid_for_elapsed} 経過", _fmt_elapsed(int(now - step_started)))
            )

    # --- その他 (差分) ---
    # 既知 = system + tool_definitions + conversation
    # SDK 未提供の場合は計算不可なので "-"
    other_label = "その他 (current − System − User Context)"
    if (
        state.context_system_tokens is not None
        and state.context_tool_definitions_tokens is not None
        and state.context_conversation_tokens is not None
        and cur > 0
    ):
        other_val = max(0, cur - sys_known - user_known)
        other_items = [StatItem(other_label, f"{_fmt_int(other_val)} ({_fmt_pct_of(other_val, lim)})")]
    else:
        other_items = [StatItem(other_label, _DASH)]

    sections: List[StatSection] = [
        StatSection("System", tuple(system_items)),
        StatSection("User Context", tuple(user_items)),
        StatSection("Reasoning & Cache", tuple(rc_items)),
        StatSection("Latency", tuple(latency_items)),
        StatSection("Step Activity", tuple(step_items)),
        StatSection("Compaction", tuple(compaction_items)),
        StatSection("Permission", tuple(permission_items)),
        StatSection("Cost (AI Credit)", tuple(cost_items)),
        StatSection("Elapsed", tuple(elapsed_items)),
        StatSection("その他", tuple(other_items)),
    ]

    header = {"current": cur, "limit": lim, "pct": pct}
    return sections, header


class StatsDetailPopup(QWidget):
    """統計情報ウィンドウ。

    ``Qt.Tool`` のノンモーダルウィンドウとして表示し、タブで
    「スナップショット」と「今回の実行履歴」を切り替える。
    スナップショットタブは開設時点のスナップショット、
    履歴タブはシグナルによりリアルタイム更新される。
    """

    def __init__(self, state: WorkbenchState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # ノンモーダルツールウィンドウ（明示的に閉じるまで表示継続）
        self.setWindowFlags(Qt.WindowType.Tool)
        self.setWindowTitle(self.tr("統計情報"))
        self.setObjectName("StatsDetailPopup")
        self.setStyleSheet(
            "#StatsDetailPopup {"
            " background-color: #ffffff;"
            "}"
        )
        self._state = state
        self._tabs: Optional[QTabWidget] = None
        self._build_ui(state)

        # --- 1Hz ライブ更新タイマ (Wave 4) ---
        # ポップアップ表示中、Cost / Elapsed セクション等を毎秒更新する。
        try:
            from PySide6.QtCore import QTimer  # type: ignore
            self._tick = QTimer(self)
            self._tick.setInterval(1000)
            self._tick.timeout.connect(self._on_tick)
            self._tick.start()
        except Exception:
            self._tick = None  # pragma: no cover

    def _on_tick(self) -> None:
        if not self.isVisible() or self._tabs is None:
            return
        # 履歴タブ表示中はスナップショットタブを再構築しない
        # (removeTab/insertTab により currentIndex が意図せず 0 に戻る不具合を回避)
        if self._tabs.currentIndex() != 0:
            return
        try:
            saved_index = self._tabs.currentIndex()
            # --- スクロール位置を保存（再構築でリセットされるのを防ぐ） ---
            saved_v = 0
            saved_h = 0
            old = self._tabs.widget(0)
            if isinstance(old, QScrollArea):
                vbar = old.verticalScrollBar()
                hbar = old.horizontalScrollBar()
                if vbar is not None:
                    saved_v = vbar.value()
                if hbar is not None:
                    saved_h = hbar.value()

            new_tab = self._build_snapshot_tab(self._state)
            idx = 0
            self._tabs.removeTab(idx)
            self._tabs.insertTab(idx, new_tab, self.tr("スナップショット"))
            self._tabs.setCurrentIndex(saved_index)
            self._snapshot_tab = new_tab
            if old is not None:
                old.deleteLater()

            # --- スクロール位置を復元 ---
            # レイアウト確定後に復元するため singleShot(0) でディスパッチ。
            # 値はスクロール範囲に自動 clamp される。
            def _restore() -> None:
                try:
                    if isinstance(new_tab, QScrollArea):
                        vbar2 = new_tab.verticalScrollBar()
                        hbar2 = new_tab.horizontalScrollBar()
                        if vbar2 is not None:
                            vbar2.setValue(saved_v)
                        if hbar2 is not None:
                            hbar2.setValue(saved_h)
                except Exception:
                    pass

            try:
                from PySide6.QtCore import QTimer  # type: ignore
                QTimer.singleShot(0, _restore)
            except Exception:
                _restore()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------
    def _build_ui(self, state: WorkbenchState) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tabs = QTabWidget()
        tabs.setObjectName("StatsDetailTabs")
        self._tabs = tabs
        root.addWidget(tabs)

        # --- タブ 1: スナップショット ---
        self._snapshot_tab = self._build_snapshot_tab(state)
        tabs.addTab(self._snapshot_tab, self.tr("スナップショット"))

        # --- タブ 2: 今回の実行履歴 ---
        try:
            from .stats_history_view import StatsHistoryView
            self._history_tab = StatsHistoryView(state)
            tabs.addTab(self._history_tab, self.tr("今回の実行履歴"))
        except Exception:
            self._history_tab = None

        self.resize(560, 640)
        self.setMinimumWidth(320)
        self.setMinimumHeight(200)

    def _build_snapshot_tab(self, state: WorkbenchState) -> QWidget:
        sections, header = build_snapshot(state)
        # 多数セクションで minimumSizeHint が縦に肥大化するのを防ぐため
        # QScrollArea でラップし、ウィンドウを自由に縮小できるようにする
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # --- ヘッダ ---
        title = QLabel(self.tr("コンテキスト ウィンドウ"))
        title.setStyleSheet(f"font-weight: bold; color: {_LABEL_COLOR}; font-size: 11pt;")
        layout.addWidget(title)

        cur = int(header.get("current", 0) or 0)
        lim = int(header.get("limit", 0) or 0)
        pct = float(header.get("pct", 0.0) or 0.0)

        usage_text = QLabel(
            f"<span style='color:{_VALUE_COLOR};'>{cur:,} / {lim:,} 個のトークン</span>"
            f"&nbsp;&nbsp;<span style='color:{_LABEL_COLOR}; font-weight:bold;'>{pct:.1f}%</span>"
            if lim > 0
            else f"<span style='color:{_MUTED_COLOR};'>未取得</span>"
        )
        usage_text.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(usage_text)

        bar = QProgressBar()
        bar.setRange(0, max(1, lim))
        bar.setValue(max(0, min(lim, cur)))
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        layout.addWidget(bar)

        # 区切り線
        layout.addWidget(_hline())

        # --- カテゴリブロック ---
        for sec in sections:
            sec_title = QLabel(sec.title)
            sec_title.setStyleSheet(
                f"color: {_SECTION_COLOR}; font-weight: bold; font-size: 9pt;"
            )
            layout.addWidget(sec_title)
            for item in sec.items:
                layout.addWidget(_item_row(item))
            layout.addSpacing(4)

        # フッタ補助
        note = QLabel(
            "<span style='color:" + _MUTED_COLOR + "; font-size: 8pt;'>"
            "スナップショット（再オープンで再取得）／"
            "SDK 未取得値は '-' で表示／"
            "Messages と Tool Results は SDK 仕様により分離不可"
            "</span>"
        )
        note.setTextFormat(Qt.TextFormat.RichText)
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        scroll.setWidget(inner)
        return scroll


def _item_row(item: StatItem) -> QWidget:
    """1 行ぶんの "項目名 … 値" レイアウト。"""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    label = QLabel(
        f"<table width='100%' cellspacing='0' cellpadding='0'>"
        f"<tr>"
        f"<td align='left'><span style='color:{_LABEL_COLOR}; font-weight:bold;'>{_escape(item.label)}</span></td>"
        f"<td align='right'><span style='color:{_VALUE_COLOR};'>{_escape(item.value)}</span></td>"
        f"</tr></table>"
    )
    label.setTextFormat(Qt.TextFormat.RichText)
    lay.addWidget(label)
    return w


def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    f.setStyleSheet("color: #e0e3e8;")
    return f


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
