"""Workbench KeyReader: 別スレッドで stdin を非ブロッキング読み取りして
WorkbenchController のスクロール API を呼び出す。

対応キー（既定）:
  - ↑ / k        : scroll_up(1)
  - ↓ / j        : scroll_down(1)
  - PageUp / b   : page_up()
  - PageDown / f : page_down() (またはスペース)
  - Home / g     : home()
  - End / G      : end()
  - q            : detach（KeyReader を停止する。プロセス中断はしない）

Windows: msvcrt.kbhit/getwch を使用。
POSIX  : termios + select で 1 文字ずつ読む。

非 TTY、quiet、HVE_NO_KEYREADER=1 のいずれかなら起動しない。
"""
from __future__ import annotations

import os
import sys
import threading
from typing import Any, Optional


class KeyReader:
    def __init__(self, controller: Any) -> None:
        self._controller = controller
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._enabled = self._can_enable()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _can_enable(self) -> bool:
        # Workbench 起動中は stdin の所有権を KeyReader が持つ前提（呼び出し元の
        # orchestrator が KeybindMonitor を起動しない構成）。デフォルト有効・
        # opt-out は `HVE_NO_KEYREADER=1` のみ。
        # 後方互換として `HVE_WORKBENCH_KEYREADER=0` も無効化として受け付ける。
        if os.environ.get("HVE_NO_KEYREADER", "").strip() in ("1", "true", "True"):
            return False
        if os.environ.get("HVE_WORKBENCH_KEYREADER", "").strip() in ("0", "false", "False"):
            return False
        try:
            if not sys.stdin.isatty():
                return False
        except Exception:
            return False
        return True

    def start(self) -> None:
        if not self._enabled:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="hve-workbench-keyreader", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        # join は短いタイムアウトで（daemon=True なのでハングしない）
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=0.5)
        self._thread = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _dispatch(self, key: str) -> None:
        wb = self._controller
        # コマンドモード中は文字入力を優先処理する（ナビ無効化）
        try:
            in_cmd = bool(getattr(wb.state, "cmd_mode", False))
        except Exception:
            in_cmd = False
        if in_cmd:
            try:
                if key == "ESC":
                    wb.cmd_cancel()
                elif key == "ENTER":
                    wb.cmd_submit()
                elif key == "BACKSPACE":
                    wb.cmd_backspace()
                elif len(key) == 1 and key >= " ":
                    wb.cmd_append(key)
            except Exception:
                pass
            return
        try:
            if key == ":":
                # コマンドモード進入
                wb.cmd_enter()
                return
            if key in ("UP", "k"):
                wb.scroll_up(1)
            elif key in ("DOWN", "j"):
                wb.scroll_down(1)
            elif key in ("PGUP", "b"):
                wb.page_up()
            elif key in ("PGDN", "f", " "):
                wb.page_down()
            elif key in ("HOME", "g"):
                wb.home()
            elif key in ("END", "G"):
                wb.end()
            elif key == "[":
                # UserActions スクロール（過去方向）
                wb.scroll_actions_up(1)
            elif key == "]":
                # UserActions スクロール（最新方向）
                wb.scroll_actions_down(1)
            elif key == "q":
                # 完了モードでは /exit の入力路を確保するため q は無効化
                try:
                    if getattr(wb.state, "all_done", False):
                        return
                except Exception:
                    pass
                # 自身を停止（プロセスは継続）
                self._stop_event.set()
        except Exception:
            # スクロール API 失敗は黙殺（UI は壊さない）
            pass

    def _run(self) -> None:
        if os.name == "nt":
            self._run_windows()
        else:
            self._run_posix()

    def _run_windows(self) -> None:  # pragma: no cover - 手動 TTY 検証
        try:
            import msvcrt
        except ImportError:
            return
        while not self._stop_event.is_set():
            try:
                if not msvcrt.kbhit():
                    self._stop_event.wait(0.05)
                    continue
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):
                    # 拡張キー: 次のバイトでマッピング
                    ch2 = msvcrt.getwch()
                    mapping = {
                        "H": "UP", "P": "DOWN",
                        "I": "PGUP", "Q": "PGDN",
                        "G": "HOME", "O": "END",
                    }
                    key = mapping.get(ch2)
                    if key:
                        self._dispatch(key)
                elif ch == "\r" or ch == "\n":
                    self._dispatch("ENTER")
                elif ch == "\x08":  # Backspace
                    self._dispatch("BACKSPACE")
                elif ch == "\x1b":  # ESC
                    self._dispatch("ESC")
                else:
                    self._dispatch(ch)
            except Exception:
                self._stop_event.wait(0.1)

    def _run_posix(self) -> None:  # pragma: no cover - 手動 TTY 検証
        try:
            import select
            import termios
            import tty
        except ImportError:
            return
        fd = sys.stdin.fileno()
        try:
            old = termios.tcgetattr(fd)
        except Exception:
            return
        try:
            tty.setcbreak(fd)
            while not self._stop_event.is_set():
                rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not rlist:
                    continue
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    # ESC シーケンス（ESC 単独 か 矢印キー [A 等）
                    rlist2, _, _ = select.select([sys.stdin], [], [], 0.02)
                    if not rlist2:
                        # 単独 ESC（コマンドキャンセル）
                        self._dispatch("ESC")
                        continue
                    seq2 = sys.stdin.read(1)
                    if seq2 == "[":
                        seq3 = sys.stdin.read(1)
                        mapping = {"A": "UP", "B": "DOWN", "5": "PGUP", "6": "PGDN", "H": "HOME", "F": "END"}
                        key = mapping.get(seq3)
                        if key in ("PGUP", "PGDN"):
                            # PageUp/Down は ~ 終端
                            try:
                                sys.stdin.read(1)
                            except Exception:
                                pass
                        if key:
                            self._dispatch(key)
                    else:
                        # その他 ESC シーケンスは無視
                        pass
                elif ch in ("\r", "\n"):
                    self._dispatch("ENTER")
                elif ch in ("\x7f", "\x08"):  # DEL / Backspace
                    self._dispatch("BACKSPACE")
                else:
                    self._dispatch(ch)
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception:
                pass
