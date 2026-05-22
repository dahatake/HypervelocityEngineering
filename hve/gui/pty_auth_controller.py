"""hve.gui.pty_auth_controller — PTY セッション統括コントローラ。

役割:
    - 任意のコマンド (``copilot login`` / ``az login`` / MCP サーバ初期化等) を
      :class:`PtySession` (T01) で起動し、出力ストリームを Qt シグナルとして配信、
      ユーザー入力を PTY へ書き戻す。
    - manifest 指定の ``success_regex`` / ``failure_regex`` を出力に対して逐次マッチし、
      確定したら ``finished(success, message)`` を発火する。
    - 全体タイムアウトを ``QTimer`` で監視し、超過時は terminate → kill で確実に終了。

スレッドモデル:
    - 本クラスは **GUI スレッド** 上で動作する想定 (``QObject`` + ``QTimer``)。
    - PTY 読み出しは ``QTimer`` ポーリング (20ms 周期)。ブロッキング read は
      しないため UI フリーズしない。

セキュリティ:
    - argv はリスト渡し (shell 経由ではない)。
    - ``success_regex`` / ``failure_regex`` の評価は **行単位 + 行長 4KB 上限**
      で線形時間を保証。
    - 出力ログは本クラス自体では永続化しない (機密混入リスクのため呼び出し側責務)。
"""

from __future__ import annotations

import re
import time
from typing import Dict, List, Optional, Pattern

from PySide6.QtCore import QObject, QTimer, Signal

from .pty_backend import PtyBackendError, PtySession, is_pty_available, spawn

__all__ = ["PtyAuthController", "CommandSpec"]


_POLL_INTERVAL_MS = 20
_DEFAULT_TIMEOUT_S = 600.0
_LINE_MAX_BYTES = 4 * 1024
_RING_BUFFER_LIMIT = 64 * 1024  # 直近 64KB を成功/失敗判定に保持


class CommandSpec:
    """1 コマンド分の起動仕様。"""

    __slots__ = ("argv", "cwd", "env", "success_regex", "failure_regex", "timeout")

    def __init__(
        self,
        argv: List[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        success_regex: Optional[str] = None,
        failure_regex: Optional[str] = None,
        timeout: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        if not argv:
            raise ValueError("argv must be non-empty")
        self.argv = list(argv)
        self.cwd = cwd
        self.env = dict(env) if env is not None else None
        self.success_regex = success_regex
        self.failure_regex = failure_regex
        self.timeout = float(timeout)


class PtyAuthController(QObject):
    """単一 PTY コマンドの起動・監視・完了判定。

    シグナル:
        output(bytes)      : PTY から読み出した生バイト列。
        prompt_required(str): 将来拡張用 (現状は未発火)。
        state_changed(str) : "idle" / "running" / "matched" / "exited" / "killed"
        finished(bool, str): 完了通知。success=True ならパターンマッチで成功、
                             False は失敗 / timeout / cancel / 非ゼロ exit。
    """

    output = Signal(bytes)
    prompt_required = Signal(str)
    state_changed = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._session: Optional[PtySession] = None
        self._spec: Optional[CommandSpec] = None
        self._success_re: Optional[Pattern[bytes]] = None
        self._failure_re: Optional[Pattern[bytes]] = None
        self._ring = bytearray()
        self._state = "idle"
        self._start_time = 0.0
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._on_poll)
        self._finished_emitted = False

    # ------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------
    def state(self) -> str:
        return self._state

    def start(self, spec: CommandSpec) -> None:
        """コマンドを起動する。既に running の場合は ValueError。"""
        if self._state == "running":
            raise ValueError("already running")
        if not is_pty_available():
            self._emit_finished(False, "PTY backend not available")
            return

        self._spec = spec
        self._ring.clear()
        self._finished_emitted = False
        self._success_re = (
            re.compile(spec.success_regex.encode("utf-8"))
            if spec.success_regex
            else None
        )
        self._failure_re = (
            re.compile(spec.failure_regex.encode("utf-8"))
            if spec.failure_regex
            else None
        )

        try:
            self._session = spawn(spec.argv, cwd=spec.cwd, env=spec.env)
        except PtyBackendError as exc:
            self._emit_finished(False, f"spawn failed: {exc}")
            return

        self._start_time = time.monotonic()
        self._set_state("running")
        self._poll_timer.start()

    def send_input(self, data: bytes) -> None:
        """ユーザー入力を PTY へ書き込む。"""
        if self._session is None or self._state != "running":
            return
        try:
            self._session.write(data)
        except PtyBackendError:
            # 書き込み失敗は致命的でないが、出力ループで EOF を検知して終わるはず
            pass

    def cancel(self) -> None:
        """ユーザーキャンセル。子プロセスを terminate→kill する。"""
        if self._session is None:
            self._emit_finished(False, "cancelled (no session)")
            return
        self._session.close(grace_seconds=1.0)
        self._set_state("killed")
        self._poll_timer.stop()
        self._emit_finished(False, "cancelled by user")

    def resize(self, cols: int, rows: int) -> None:
        if self._session is not None:
            try:
                self._session.resize(cols, rows)
            except Exception:
                pass

    # ------------------------------------------------------------
    # ポーリング本体
    # ------------------------------------------------------------
    def _on_poll(self) -> None:
        if self._session is None or self._spec is None:
            self._poll_timer.stop()
            return

        # 1. 出力の読み出し
        try:
            chunk = self._session.read_nowait(8192)
        except Exception:
            chunk = b""
        if chunk:
            self.output.emit(chunk)
            self._append_to_ring(chunk)
            # 行単位スキャン (長すぎる行は先頭 _LINE_MAX_BYTES のみ評価)
            if self._match_patterns():
                return

        # 2. タイムアウト判定
        elapsed = time.monotonic() - self._start_time
        if elapsed >= self._spec.timeout:
            self._session.close(grace_seconds=1.0)
            self._set_state("exited")
            self._poll_timer.stop()
            self._emit_finished(
                False, f"timeout after {self._spec.timeout:.0f}s"
            )
            return

        # 3. プロセス終了判定
        if not self._session.is_alive():
            # 残バッファを読み切る
            try:
                tail = self._session.read_nowait(8192)
            except Exception:
                tail = b""
            if tail:
                self.output.emit(tail)
                self._append_to_ring(tail)
                if self._match_patterns():
                    return
            code = self._session.exit_code()
            self._set_state("exited")
            self._poll_timer.stop()
            # exit 0 + success_regex 未設定 ならパターン無し成功扱い
            if code == 0 and self._success_re is None:
                self._emit_finished(True, "exited with code 0")
            else:
                self._emit_finished(
                    False, f"exited with code {code} (no success pattern matched)"
                )

    # ------------------------------------------------------------
    # 内部ヘルパ
    # ------------------------------------------------------------
    def _append_to_ring(self, data: bytes) -> None:
        self._ring.extend(data)
        if len(self._ring) > _RING_BUFFER_LIMIT:
            # 古い分を捨てる
            drop = len(self._ring) - _RING_BUFFER_LIMIT
            del self._ring[:drop]

    def _match_patterns(self) -> bool:
        """ring buffer から行単位で success / failure を判定する。

        Returns:
            判定が確定して finished を発火した場合 True。
        """
        if self._success_re is None and self._failure_re is None:
            return False
        # 行末文字 \n / \r\n / \r を境界とする
        # ring を直接スキャン (バイト列)
        # 長い行は先頭 _LINE_MAX_BYTES に切り詰めて評価。
        view = bytes(self._ring)
        # 最後の改行で区切る
        start = 0
        last_nl = view.rfind(b"\n")
        if last_nl < 0:
            return False
        segment = view[: last_nl + 1]
        for line in segment.splitlines():
            head = line[:_LINE_MAX_BYTES]
            if self._failure_re is not None and self._failure_re.search(head):
                self._session.close(grace_seconds=1.0) if self._session else None
                self._set_state("matched")
                self._poll_timer.stop()
                self._emit_finished(False, f"failure pattern matched: {head[:120]!r}")
                return True
            if self._success_re is not None and self._success_re.search(head):
                self._session.close(grace_seconds=1.0) if self._session else None
                self._set_state("matched")
                self._poll_timer.stop()
                self._emit_finished(True, f"success pattern matched: {head[:120]!r}")
                return True
        # 評価済み部分は破棄
        del self._ring[: last_nl + 1]
        _ = start  # noqa
        return False

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)

    def _emit_finished(self, success: bool, message: str) -> None:
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self.finished.emit(success, message)
