"""hve/keybind.py — Phase 6 Resume: ショートカットキー（Ctrl+R）監視。

オーケストレーター実行中に特定キー（既定: Ctrl+R = 0x12）を検出して
登録された async コールバックを起動するためのクロスプラットフォーム実装。

設計方針:
- stdin 監視は **デーモンスレッド** で行い、main の asyncio イベントループを
  ブロックしない。
- キー検出時は `asyncio.run_coroutine_threadsafe` でメインループへ通知する。
- 端末モードを raw / cbreak に変更する POSIX では、ISIG（Ctrl+C / SIGINT）は
  維持し、ECHO と ICANON のみ無効化する。
- 例外発生時 / stop() 時に **必ず** 端末設定を復元する（try/finally）。
- 以下のいずれかに該当する環境では監視を **自動で無効化** する:
  - stdin が TTY でない（パイプ・リダイレクト・CI 等）
  - `PYTEST_CURRENT_TEST` 環境変数が設定されている（pytest 内）
  - `HVE_DISABLE_KEYBIND=1` で明示的に無効化されている
  - VS Code の統合ターミナル等で stdin が直接読めないケース

`KeybindMonitor` はコンテキストマネージャとしても使えるため、orchestrator では
`async with KeybindMonitor(loop) as mon:` のように利用するのが安全。

Phase 6 (Resume) の DoD:
- pytest 内では自動的に無効化される
- 端末設定は異常終了時にも必ず復元される
- 登録キー以外は handler に渡らない（誤検出ゼロ）
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from typing import Awaitable, Callable, Dict, Optional

# ---------------------------------------------------------------------------
# 公開定数
# ---------------------------------------------------------------------------

# Ctrl+R (ASCII DC2 = 0x12)
KEY_CTRL_R: bytes = b"\x12"


# ---------------------------------------------------------------------------
# 環境判定
# ---------------------------------------------------------------------------

def is_keybind_supported() -> bool:
    """現在の環境で Keybind 監視が有効化できるかを返す。

    無効化条件（いずれか 1 つでも該当すれば False）:
      1. `HVE_DISABLE_KEYBIND` が "1" / "true" / "yes" 等の真値
      2. `PYTEST_CURRENT_TEST` が設定されている（pytest 実行中）
      3. `sys.stdin` が TTY ではない（パイプ・CI・redirected）
      4. VS Code 等の統合ターミナルで stdin が読めない
    """
    # 明示的な無効化フラグ
    flag = os.environ.get("HVE_DISABLE_KEYBIND", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return False

    # pytest 内ではスレッド + stdin 操作を行わない
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False

    # TTY でなければ raw mode を変更できない（パイプ・redirected）
    try:
        if not sys.stdin.isatty():
            return False
    except (ValueError, OSError):  # stdin が閉じられている等
        return False

    return True


# ---------------------------------------------------------------------------
# KeybindMonitor 本体
# ---------------------------------------------------------------------------

class KeybindMonitor:
    """別スレッドで stdin を監視し、登録キーが押されたら async ハンドラーを起動する。

    使い方:
        loop = asyncio.get_running_loop()
        monitor = KeybindMonitor(loop)
        monitor.register(KEY_CTRL_R, on_ctrl_r_async)
        monitor.start()
        try:
            await some_long_running_task()
        finally:
            monitor.stop()

    あるいは context manager として:
        with KeybindMonitor(loop) as monitor:
            monitor.register(KEY_CTRL_R, on_ctrl_r_async)
            await some_long_running_task()

    属性:
        enabled: 現在の環境で監視が有効化されているか（is_keybind_supported() の結果）。
    """

    # 監視ループの poll 間隔（POSIX select / Windows kbhit 共通の上限）
    _POLL_INTERVAL_SECONDS: float = 0.1

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self._loop = loop
        self._handlers: Dict[bytes, Callable[[], Awaitable[None]]] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop_event: threading.Event = threading.Event()
        self._started: bool = False
        # 環境判定はインスタンス生成時に固定する（途中で変わっても影響しない）
        self.enabled: bool = is_keybind_supported()

    # ------------------------------------------------------------------ API

    def register(self, key: bytes, async_handler: Callable[[], Awaitable[None]]) -> None:
        """キーバイトと async ハンドラーを登録する。

        Args:
            key: 1 バイトの bytes（例: KEY_CTRL_R = b"\\x12"）。
            async_handler: 引数なしの async コールバック。

        Raises:
            ValueError: key が 1 バイトの bytes でない場合。
            TypeError: async_handler が callable でない場合。
        """
        if not isinstance(key, (bytes, bytearray)) or len(key) != 1:
            raise ValueError(f"key は 1 バイトの bytes である必要があります: {key!r}")
        if not callable(async_handler):
            raise TypeError("async_handler は callable である必要があります")
        self._handlers[bytes(key)] = async_handler

    def start(self) -> None:
        """監視スレッドを開始する。enabled=False なら no-op。

        既に start() 済みの場合も no-op（idempotent）。
        """
        if not self.enabled or self._started:
            return
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                # 実行中の loop が無ければ監視できない
                self.enabled = False
                return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="hve-keybind-monitor",
            daemon=True,
        )
        self._thread.start()
        self._started = True

    def stop(self, timeout: float = 1.0) -> None:
        """監視スレッドを停止する。idempotent。

        Args:
            timeout: スレッド join のタイムアウト秒。
        """
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None
        self._started = False

    def __enter__(self) -> "KeybindMonitor":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    # ----------------------------------------------------------- スレッド本体

    def _run(self) -> None:
        """別スレッドで実行されるメインループ。"""
        try:
            if sys.platform == "win32":
                self._run_windows()
            else:
                self._run_posix()
        except Exception:  # pragma: no cover - スレッド内例外は握り潰す（main を巻き込まない）
            # 監視失敗は致命的ではない。停止するだけ。
            pass

    def _run_posix(self) -> None:
        """POSIX 系の stdin 監視。termios で cbreak モードに切り替える。"""
        import select
        import termios

        try:
            fd = sys.stdin.fileno()
        except (ValueError, OSError, AttributeError):  # pragma: no cover
            return

        try:
            old_settings = termios.tcgetattr(fd)
        except termios.error:  # pragma: no cover - non-tty 等
            return

        try:
            new_settings = termios.tcgetattr(fd)
            # ICANON / ECHO のみ無効化する。ISIG は維持して Ctrl+C を生かす。
            # tcgetattr の戻り値は [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]
            new_settings[3] = new_settings[3] & ~termios.ICANON & ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSANOW, new_settings)

            while not self._stop_event.is_set():
                try:
                    ready, _, _ = select.select(
                        [sys.stdin], [], [], self._POLL_INTERVAL_SECONDS,
                    )
                except (OSError, ValueError):  # pragma: no cover
                    break
                if not ready:
                    continue
                try:
                    ch = os.read(fd, 1)
                except (OSError, ValueError):  # pragma: no cover
                    break
                if not ch:
                    continue
                self._dispatch(ch)
        finally:
            # 端末設定を必ず復元
            try:
                termios.tcsetattr(fd, termios.TCSANOW, old_settings)
            except termios.error:  # pragma: no cover
                pass

    def _run_windows(self) -> None:
        """Windows の stdin 監視。msvcrt.kbhit() でポーリングする。"""
        try:
            import msvcrt  # type: ignore[import-not-found]
        except ImportError:  # pragma: no cover - 非 Windows
            return

        while not self._stop_event.is_set():
            try:
                if msvcrt.kbhit():
                    ch = msvcrt.getch()  # 1 バイト読み取り
                    if ch:
                        self._dispatch(ch)
                else:
                    time.sleep(self._POLL_INTERVAL_SECONDS)
            except OSError:  # pragma: no cover
                break

    def _dispatch(self, ch: bytes) -> None:
        """キーが登録ハンドラーに合致すれば asyncio ループへ投入する。

        合致しない場合は無視（通常入力は破棄される — 実行中はキー入力を
        受け付けない設計）。
        """
        handler = self._handlers.get(ch)
        if handler is None or self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(handler(), self._loop)
        except RuntimeError:  # pragma: no cover - loop が閉じられている
            pass
