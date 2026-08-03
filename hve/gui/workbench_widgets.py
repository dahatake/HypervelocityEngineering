"""hve.gui.workbench_widgets — Workbench UI ウィジェット群。

Header1, Header2, TaskTree, UserInteraction, Footer など、
各ペインに対応したウィジェットを提供。
"""

from __future__ import annotations

import html
import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .workbench_state import WorkbenchState


# ステップ状態グリフ（絵文字）
_STATUS_GLYPH = {
    "pending": "⚪",      # pending
    "running": "🔄",      # running
    "done": "✅",         # done
    "failed": "❌",       # failed
    "skipped": "⏭️",      # skipped
    "blocked": "⏸️",      # blocked (user intervention required)
}

_STATUS_COLOR = {
    "pending": "#888888",      # dim white
    "running": "#ffff00",      # bold yellow
    "done": "#00ff00",         # bold green
    "failed": "#ff0000",       # bold red
    "skipped": "#00ffff",      # dim cyan
    "blocked": "#b07ed5",      # purple (matches dag_status_widget)
}


class Header2Widget(QWidget):
    """Header2 ペイン: ステップ状態（⚪🔄✅❌⏭️）を行に表示。"""

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
        # 全タスク完了後 (mark_all_done / mark_aborted で all_done=True)
        # は task_tree.root.finished_at を end_time として固定し、カウントを停止する。
        # 前提: mark_all_done() / mark_aborted() 経由で root.finished_at が
        # 設定される (workbench_state.py L.996, L.1017)。
        # root が None または finished_at が未設定の異常ケースは仕様外として
        # now にフォールバックする (フリーズしないが例外も出さない防御)。
        import time

        now = time.monotonic()
        end_time = now
        if getattr(self.state, "all_done", False):
            root = getattr(getattr(self.state, "task_tree", None), "root", None)
            finished_at = getattr(root, "finished_at", None)
            if finished_at is not None:
                end_time = finished_at
        elapsed = max(0.0, end_time - self.state.workflow_started_at)
        h = int(elapsed) // 3600
        m = (int(elapsed) % 3600) // 60
        s = int(elapsed) % 60
        parts.append(self._fmt_item("Elapsed", f"{h:02d}:{m:02d}:{s:02d}"))

        # --- Step Elapsed (現 Step) ---
        # 対象 Step が完了している場合 (finished_at が記録されている) は
        # それを end_time として固定し、完了済み Step (last_known_step_id 経由で
        # 表示中の場合) でカウントを停止する。
        # 注意: StepView.finished_at は通常経路 (set_step_status) では設定されず、
        # SimpleTaskNode (task_tree のノード) の finished_at にのみ設定される。
        # そのため task_tree.get(step_id).finished_at を優先参照する。
        # StepView.finished_at は将来の経路追加に備えてフォールバックとして残す。
        try:
            step_id = self.state.current_running_step_id or self.state.last_known_step_id
            step_started: Optional[float] = None
            step_finished: Optional[float] = None
            if step_id:
                # task_tree (SimpleTaskNode) を優先参照
                tree = getattr(self.state, "task_tree", None)
                node = tree.get(step_id) if tree is not None else None
                if node is not None:
                    nf = getattr(node, "finished_at", None)
                    if nf is not None:
                        step_finished = float(nf)
                for sv in self.state.steps:
                    if getattr(sv, "id", None) == step_id and getattr(sv, "started_at", None):
                        step_started = float(sv.started_at)
                        if step_finished is None:
                            sf = getattr(sv, "finished_at", None)
                            if sf is not None:
                                step_finished = float(sf)
                        break
            if step_started is not None:
                step_end = step_finished if step_finished is not None else now
                se = max(0, int(step_end - step_started))
                parts.append(
                    self._fmt_item(
                        f"Step {step_id}",
                        f"{se // 3600:02d}:{(se % 3600) // 60:02d}:{se % 60:02d}",
                    )
                )
        except Exception:
            pass

        # --- AI Credit (SDK 直接値 → 累積、フォールバックで pricing 経路) ---
        # SDK の `assistant.usage.copilot_usage.total_nano_aiu` を累積した
        # `sdk_aiu_total` を最優先表示。pricing 注入時のみ USD/JPY を併記。
        try:
            aiu_total = float(getattr(self.state, "sdk_aiu_total", 0.0) or 0.0)
        except (TypeError, ValueError):
            aiu_total = 0.0
        if aiu_total > 0:
            # 小数 4 桁まで表示 (AIU は 0.0001 単位くらいで動く想定)
            cost_str = f"{aiu_total:.4f} AIU"
            # pricing 経由の USD があれば併記
            try:
                from .text_kinsoku import format_cost
                usd_total = getattr(self.state, "cost_usd_total", None)
                jpy_total = getattr(self.state, "cost_jpy_total", None)
                if usd_total is not None or jpy_total is not None:
                    extra = format_cost(
                        usd_total, jpy_total,
                        currency=self._currency, locale=self._locale,
                    )
                    if extra and extra != "-":
                        cost_str = f"{cost_str} ({extra})"
            except Exception:
                pass
        else:
            # SDK 値が無い場合の分岐 (優先順位: mc 累計 > unavailable_reason > pricing):
            # (a) sdk_multiplier_cost_total > 0:
            #     `assistant.usage.cost` (Multiplier cost) を累計した値が SDK から
            #     取得できていれば、"mc: X.X" として表示する (案 A, 捏造禁止)。
            #     Unlimited プランでも cost フィールドは届く実例あり (実機ログ確定)。
            # (b) sdk_credit_unavailable_reason が non-empty:
            #     SDK が copilot_usage=None を返し、mc も累計ゼロのケース。
            #     "N/A (AIU unavailable)" を表示し、ハイフン表示で「未取得 / 未計算」と
            #     混同させない (捏造禁止)。
            # (c) それ以外: 従来通り pricing 経路へフォールバック。
            try:
                mc_total = float(
                    getattr(self.state, "sdk_multiplier_cost_total", 0.0) or 0.0
                )
            except (TypeError, ValueError):
                mc_total = 0.0
            unavailable_reason = str(
                getattr(self.state, "sdk_credit_unavailable_reason", "") or ""
            )
            if mc_total > 0:
                # Multiplier cost は SDK の生値 (Unlimited プランでは 1.0 / call 固定)。
                # 小数 1 桁で表示 ("mc:" prefix で AIU/USD/JPY と混同を防ぐ)。
                cost_str = f"mc: {mc_total:.1f}"
            elif unavailable_reason:
                cost_str = "N/A (AIU unavailable)"
            else:
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
        parts.append(self._fmt_item("AI Credit", cost_str))

        # --- Reqs (Premium Requests / Quota delta) ---
        # 優先順位: session.shutdown 経由 > 全 quota の baseline 差分合計 > 0
        try:
            reqs = int(getattr(self.state, "display_reqs", 0) or 0)
        except (TypeError, ValueError):
            reqs = int(getattr(self.state, "premium_requests_total", 0) or 0)
        parts.append(self._fmt_item("Reqs", str(reqs) if reqs > 0 else "-"))

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
