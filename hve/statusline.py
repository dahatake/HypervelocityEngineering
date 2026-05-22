"""hve.statusline — CUI 1Hz ステータスライン。

GUI Footer (Wave 4) と同じ統計情報 (Workflow 経過 / Step 経過 / Context / Cost / Reqs)
を CUI でも 1Hz で更新表示する。

設計方針:

- 単一行を ``stderr`` に対して ``\\r\\x1b[2K`` で上書き描画する。
- 既定では ``stderr.isatty()`` でない、もしくは ``HVE_NO_STATUSLINE`` 環境変数が
  設定されている、もしくは ``enabled=False`` 指定時には何も出力しない。
- 1Hz の更新は daemon thread + ``threading.Event.wait(1.0)`` で実装。
- 状態は ``StatusLineState`` (dataclass) を ``update_state()`` で受け取る純粋関数
  ``format_status_line()`` を使い、テスト容易性を確保する。
- 捏造禁止: cost が不明なら ``-`` を表示する。料金表未注入時は Cost セグメント
  を ``$- (¥-)`` 等で表示する。

このモジュールは GUI / PySide6 に依存しない (テスト時にも import 可)。
"""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import IO, Optional

# text_kinsoku は Qt 非依存のため CUI からも安全に import 可
from .gui.text_kinsoku import format_cost, format_elapsed


# ------------------------------------------------------------------
# 状態スナップショット
# ------------------------------------------------------------------

@dataclass
class StatusLineState:
    """ステータスライン描画に必要な最小スナップショット。"""

    workflow_started_at: Optional[float] = None  # time.monotonic() 基準
    step_id: Optional[str] = None
    step_started_at: Optional[float] = None
    sub_name: Optional[str] = None
    sub_started_at: Optional[float] = None
    context_current: int = 0
    context_limit: int = 0
    cost_usd_total: Optional[float] = None
    cost_jpy_total: Optional[float] = None
    premium_requests_total: int = 0
    currency: str = "auto"
    locale: str = "ja"


# ------------------------------------------------------------------
# フォーマッタ (純粋関数)
# ------------------------------------------------------------------

def format_status_line(state: StatusLineState, *, now: Optional[float] = None) -> str:
    """``StatusLineState`` を 1 行の文字列に整形する。

    例 (ja, auto): ``[hve] WF 00:01:23 | Step prep 00:00:42 | ctx 12,345/200,000 (6%) | $0.4000 (¥60) | reqs 10``
    """
    t_now = float(now) if now is not None else time.monotonic()

    parts = ["[hve]"]

    # WF 経過
    if state.workflow_started_at is not None:
        wf = max(0, int(t_now - float(state.workflow_started_at)))
        parts.append(f"WF {format_elapsed(wf)}")

    # Step 経過
    if state.step_id and state.step_started_at is not None:
        step = max(0, int(t_now - float(state.step_started_at)))
        parts.append(f"Step {state.step_id} {format_elapsed(step)}")

    # Sub 経過
    if state.sub_name and state.sub_started_at is not None:
        sub = max(0, int(t_now - float(state.sub_started_at)))
        parts.append(f"Sub {state.sub_name} {format_elapsed(sub)}")

    # Context
    if state.context_limit > 0:
        cur = max(0, int(state.context_current))
        lim = int(state.context_limit)
        pct = (cur / lim * 100.0) if lim > 0 else 0.0
        parts.append(f"ctx {cur:,}/{lim:,} ({pct:.0f}%)")

    # Cost
    parts.append(
        f"cost {format_cost(state.cost_usd_total, state.cost_jpy_total, currency=state.currency, locale=state.locale)}"
    )

    # Reqs
    parts.append(f"reqs {int(state.premium_requests_total)}")

    return " | ".join(parts)


# ------------------------------------------------------------------
# StatusLine ランナ
# ------------------------------------------------------------------

_CLEAR_LINE = "\r\x1b[2K"


class StatusLine:
    """CUI 用 1Hz ステータスライン。"""

    def __init__(
        self,
        *,
        stream: Optional[IO[str]] = None,
        enabled: Optional[bool] = None,
        interval: float = 1.0,
    ) -> None:
        self._stream: IO[str] = stream if stream is not None else sys.stderr
        self._interval = max(0.1, float(interval))
        self._state = StatusLineState()
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_rendered: str = ""
        self._enabled = self._resolve_enabled(enabled)

    # -- enabled 判定 -------------------------------------------------
    def _resolve_enabled(self, override: Optional[bool]) -> bool:
        if override is False:
            return False
        if os.environ.get("HVE_NO_STATUSLINE"):
            return False
        if override is True:
            return True
        # 既定: stream が TTY のときのみ有効
        try:
            return bool(getattr(self._stream, "isatty", lambda: False)())
        except Exception:
            return False

    @property
    def enabled(self) -> bool:
        return self._enabled

    # -- ライフサイクル ------------------------------------------------
    def start(self) -> None:
        if not self._enabled or self._thread is not None:
            return
        self._stop_event.clear()
        t = threading.Thread(target=self._run, name="hve-statusline", daemon=True)
        self._thread = t
        t.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        try:
            self._thread.join(timeout=2.0)
        except Exception:
            pass
        self._thread = None
        if self._enabled and self._last_rendered:
            try:
                self._stream.write(_CLEAR_LINE)
                self._stream.flush()
            except Exception:
                pass
            self._last_rendered = ""

    def __enter__(self) -> "StatusLine":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    # -- 状態更新 ----------------------------------------------------
    def update_state(self, state: StatusLineState) -> None:
        with self._state_lock:
            self._state = state

    def update_fields(self, **kwargs) -> None:
        """個別フィールドを更新する (キー名は ``StatusLineState`` フィールド)。"""
        with self._state_lock:
            for k, v in kwargs.items():
                if hasattr(self._state, k):
                    setattr(self._state, k, v)

    def snapshot(self) -> StatusLineState:
        with self._state_lock:
            s = self._state
            return StatusLineState(**{f.name: getattr(s, f.name) for f in _STATE_FIELDS})

    # -- 描画 --------------------------------------------------------
    def render_once(self) -> str:
        """現在の状態を 1 行に整形し、stream に出力する (テスト用にも使う)。

        ``enabled=False`` の場合は何も出力せず空文字を返す。
        """
        with self._state_lock:
            state = self._state
            line = format_status_line(state)
        if not self._enabled:
            return ""
        try:
            self._stream.write(_CLEAR_LINE + line)
            self._stream.flush()
        except Exception:
            return ""
        self._last_rendered = line
        return line

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.render_once()
            except Exception:
                pass
            if self._stop_event.wait(self._interval):
                break


# Cached dataclass fields (snapshot() で使用)
import dataclasses as _dc  # noqa: E402

_STATE_FIELDS = tuple(_dc.fields(StatusLineState))
