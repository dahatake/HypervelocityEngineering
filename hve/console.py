"""console.py — Console 出力制御

GitHub Copilot CLI スタイルのリッチターミナル出力を提供する。
ANSI カラー・ボックス描画・スピナー・インタラクティブメニューに対応。
"""

from __future__ import annotations

import re
import shutil
import sys
import threading
import time
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from .qa_merger import QAQuestion
except ImportError:
    from qa_merger import QAQuestion  # type: ignore[no-redef]


def timestamp_prefix() -> str:
    """現在時刻のプレフィックス文字列を返す。"""
    return f"[{datetime.now().strftime('%H:%M:%S')}]"


# ------------------------------------------------------------------
# 定数
# ------------------------------------------------------------------

_SPINNER_UPDATE_THROTTLE_SECONDS: float = 0.1  # スピナーメッセージ更新の最小間隔
_SPINNER_PAUSE_TIMEOUT_SECONDS: float = 0.2    # スピナー一時停止の同期タイムアウト
_CONTEXT_WARNING_THRESHOLD_PCT: float = 80.0   # コンテキスト使用率警告閾値

# ------------------------------------------------------------------
# ANSI エスケープコード
# ------------------------------------------------------------------

class _Style:
    """ANSI エスケープシーケンス定数。TTY 非接続時は空文字列。"""

    # Windows コンソール定数
    _STD_OUTPUT_HANDLE = -11
    _ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004  # VTP フラグのみ

    def __init__(self, is_tty: bool) -> None:
        # Windows: ANSI エスケープシーケンスを有効化
        # 既存のコンソールモードを取得して ENABLE_VIRTUAL_TERMINAL_PROCESSING を OR してから設定する
        # （他フラグを上書きしないよう GetConsoleMode で現在値を読み取る）
        if is_tty and sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                handle = kernel32.GetStdHandle(self._STD_OUTPUT_HANDLE)
                current_mode = ctypes.c_ulong(0)
                if kernel32.GetConsoleMode(handle, ctypes.byref(current_mode)):
                    kernel32.SetConsoleMode(
                        handle,
                        current_mode.value | self._ENABLE_VIRTUAL_TERMINAL_PROCESSING,
                    )
            except Exception:
                pass
        if is_tty:
            self.RESET = "\033[0m"
            self.BOLD = "\033[1m"
            self.DIM = "\033[2m"
            self.ITALIC = "\033[3m"
            self.UNDERLINE = "\033[4m"
            self.CYAN = "\033[36m"
            self.GREEN = "\033[32m"
            self.YELLOW = "\033[33m"
            self.RED = "\033[31m"
            self.MAGENTA = "\033[35m"
            self.BLUE = "\033[34m"
            self.WHITE = "\033[37m"
            self.GRAY = "\033[90m"
            self.BG_CYAN = "\033[46m"
            self.BG_GREEN = "\033[42m"
            self.CLEAR_LINE = "\033[2K\r"
            self.HIDE_CURSOR = "\033[?25l"
            self.SHOW_CURSOR = "\033[?25h"
        else:
            for attr in (
                "RESET", "BOLD", "DIM", "ITALIC", "UNDERLINE",
                "CYAN", "GREEN", "YELLOW", "RED", "MAGENTA", "BLUE",
                "WHITE", "GRAY", "BG_CYAN", "BG_GREEN",
                "CLEAR_LINE", "HIDE_CURSOR", "SHOW_CURSOR",
            ):
                setattr(self, attr, "")


class Console:
    """タスク実行中の Console 出力を制御するクラス。

    verbosity レベル (0〜3):
      0 (quiet)  : error のみ表示
      1 (compact): 重要イベントのみ確定行 + 中間イベントはスピナーで上書き（デフォルト）
      2 (normal) : compact + intent/subagent_completed/failed を確定行で表示
      3 (verbose): 全イベントを確定行で表示（旧 verbose=True と同等）

    後方互換:
      verbose=True/False, quiet=True/False パラメータは verbosity 未指定時に使用される。
    """

    def __init__(
        self,
        verbose: bool = True,
        quiet: bool = False,
        show_stream: bool = False,
        verbosity: Optional[int] = None,
    ) -> None:
        self.show_stream = show_stream
        self._start_time = time.time()
        self._is_tty = sys.stdout.isatty()
        self.s = _Style(self._is_tty)
        self._step_start_times: Dict[str, float] = {}

        # --- Verbosity レベル解決 (後方互換) ---
        if verbosity is not None:
            self._verbosity = verbosity
        elif quiet:
            self._verbosity = 0
        elif not verbose:
            self._verbosity = 1
        else:
            # verbose=True は旧来の「全表示」モードに相当 → Level 3
            self._verbosity = 3

        # 後方互換プロパティ
        self.verbose = self._verbosity >= 3
        self.quiet = self._verbosity == 0

        # --- スピナー状態管理 ---
        self._spinner_thread: Optional[threading.Thread] = None
        self._spinner_stop = threading.Event()
        self._spinner_pause = threading.Event()
        self._spinner_paused_ack = threading.Event()
        self._spinner_msg_lock = threading.Lock()
        self._spinner_msg: str = ""
        self._spinner_base_msg: str = ""
        self._last_spinner_update: float = 0.0

        # --- 出力排他制御 ---
        # 並列ステップが同時に _emit() を呼んでも出力が混在しないよう RLock で保護する。
        # RLock（再入可能ロック）を使う理由:
        #   _emit() が _output_lock を保持した状態で _pause_spinner() を呼び、
        #   そこから spinner_stop() → sys.stdout.write() のパスが存在するため、
        #   同一スレッドによる再取得を許容する RLock が必要。
        self._output_lock = threading.RLock()

        # --- Usage 累計 ---
        self._step_usage: Dict[str, Dict[str, int]] = {}
        self._step_tool_count: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _emit(self, msg: str, always: bool = False, ts: bool = True) -> None:
        """確定行を出力する。スピナー実行中は自動的に pause/resume する。

        並列安全性:
          - _output_lock で排他制御し、並列ステップからの同時呼び出しでも
            出力行が混在しないようにする。
        """
        if not always and self.quiet:
            return
        with self._output_lock:
            self._pause_spinner()
            try:
                if ts:
                    print(f"{timestamp_prefix()} {msg}", flush=True)
                else:
                    print(msg, flush=True)
            finally:
                self._resume_spinner()

    def _print(self, msg: str, always: bool = False, ts: bool = True) -> None:
        """_emit() の薄いラッパー（後方互換）。"""
        self._emit(msg, always=always, ts=ts)

    def _update_spinner_msg(self, msg: str) -> None:
        """スピナー行のテキスト部分を更新する（新規行を追加しない）。"""
        if self._spinner_thread is None:
            return
        now = time.monotonic()
        with self._spinner_msg_lock:
            if (now - self._last_spinner_update) < _SPINNER_UPDATE_THROTTLE_SECONDS:
                return
            self._spinner_msg = msg
            self._last_spinner_update = now

    def _pause_spinner(self) -> None:
        """確定行出力のためにスピナーを一時停止する。
        
        タイムアウト時はスピナーを強制停止して確定行とのインターリーブを防ぐ。
        """
        if self._spinner_thread is None or self._spinner_stop.is_set():
            return
        self._spinner_paused_ack.clear()
        self._spinner_pause.set()
        acknowledged = self._spinner_paused_ack.wait(timeout=_SPINNER_PAUSE_TIMEOUT_SECONDS)
        if not acknowledged:
            # タイムアウト時はスピナーを強制停止して確定行とのインターリーブを防ぐ
            try:
                self.spinner_stop()
            except Exception:
                # スピナー停止に失敗しても確定行出力は継続する
                pass

    def _resume_spinner(self) -> None:
        """スピナーを再開する。"""
        self._spinner_paused_ack.clear()
        self._spinner_pause.clear()

    def _elapsed(self) -> float:
        return time.time() - self._start_time

    @staticmethod
    def _visible_len(text: str) -> int:
        """ANSI エスケープを除去した上で、表示上の文字幅を返す。

        全角文字（Wide/Fullwidth）および Ambiguous（日本語ロケール前提）を幅2として計算する。

        Args:
            text: 幅を計算する文字列（ANSI エスケープを含んでもよい）。

        Returns:
            表示上の幅（整数）。
        """
        plain = re.sub(r"\033\[[0-9;]*[A-Za-z]", "", text)
        width = 0
        for c in plain:
            eaw = unicodedata.east_asian_width(c)
            if eaw in ("W", "F", "A"):
                width += 2
            else:
                width += 1
        return width

    # ------------------------------------------------------------------
    # ANSI スタイル付きテキスト生成
    # ------------------------------------------------------------------

    def _styled(self, text: str, *codes: str) -> str:
        """テキストにスタイルコードを適用する。"""
        if not self._is_tty:
            return text
        prefix = "".join(codes)
        return f"{prefix}{text}{self.s.RESET}"

    # ------------------------------------------------------------------
    # リッチ UI ヘルパー — バナー・ボックス・メニュー
    # ------------------------------------------------------------------

    def banner(self, title: str, subtitle: str = "") -> None:
        """GitHub Copilot CLI スタイルのウェルカムバナーを表示する。"""
        if self.quiet:
            return
        s = self.s
        width = 58
        top = f"  {s.CYAN}╭{'─' * width}╮{s.RESET}"
        bot = f"  {s.CYAN}╰{'─' * width}╯{s.RESET}"
        pad = lambda t: f"  {s.CYAN}│{s.RESET} {t}{' ' * (width - 2 - len(t))}{s.CYAN}│{s.RESET}"
        self._print(top, ts=False)
        self._print(pad(f"{s.BOLD}{s.CYAN}{title}{s.RESET}"), ts=False)
        if subtitle:
            self._print(pad(f"{s.DIM}{subtitle}{s.RESET}"), ts=False)
        self._print(bot, ts=False)
        self._print("", ts=False)

    def panel(self, title: str, lines: List[str], ts: bool = False) -> None:
        """ボックス描画パネルで情報を表示する。"""
        if self.quiet:
            return
        s = self.s
        max_len = max((len(line) for line in lines), default=0)
        max_len = max(max_len, len(title)) + 2
        width = max(max_len, 40)
        self._print(f"  {s.GRAY}┌{'─' * (width + 2)}┐{s.RESET}", ts=ts)
        self._print(f"  {s.GRAY}│{s.RESET} {s.BOLD}{title}{s.RESET}{' ' * (width - len(title) + 1)}{s.GRAY}│{s.RESET}", ts=ts)
        self._print(f"  {s.GRAY}├{'─' * (width + 2)}┤{s.RESET}", ts=ts)
        for line in lines:
            self._print(f"  {s.GRAY}│{s.RESET} {line}{' ' * (width - len(line) + 1)}{s.GRAY}│{s.RESET}", ts=ts)
        self._print(f"  {s.GRAY}└{'─' * (width + 2)}┘{s.RESET}", ts=ts)
        self._print("", ts=ts)

    def menu_select(self, title: str, options: List[str], allow_empty: bool = False) -> int:
        """インタラクティブな番号選択メニューを表示する。

        Args:
            title: メニューのタイトル
            options: 選択肢のリスト
            allow_empty: True の場合、空入力で -1 を返す

        Returns:
            選択されたインデックス (0-based)。allow_empty=True で空入力時は -1。
        """
        s = self.s
        self._print(f"\n  {s.BOLD}{title}{s.RESET}", ts=False)
        self._print(f"  {s.DIM}{'─' * 50}{s.RESET}", ts=False)
        for i, opt in enumerate(options, 1):
            self._print(f"  {s.CYAN}{i:>3}{s.RESET})  {opt}", ts=False)
        self._print("", ts=False)

        while True:
            try:
                answer = input(f"  {s.GREEN}>{s.RESET} ").strip()
            except (EOFError, KeyboardInterrupt):
                self._print("", ts=False)
                return 0 if not allow_empty else -1
            if not answer and allow_empty:
                return -1
            if answer.isdigit():
                idx = int(answer, 10)
                if 1 <= idx <= len(options):
                    return idx - 1
            self._print(f"  {s.YELLOW}⚠ 1〜{len(options)} の番号を入力してください{s.RESET}", ts=False)

    def prompt_input(self, label: str, default: str = "", required: bool = False) -> str:
        """GitHub Copilot CLI スタイルの入力プロンプト。"""
        s = self.s
        suffix = f" {s.DIM}[{default}]{s.RESET}" if default else ""
        req = f" {s.RED}(必須){s.RESET}" if required else ""
        while True:
            try:
                answer = input(f"  {s.GREEN}?{s.RESET} {label}{req}{suffix}: ").strip()
            except (EOFError, KeyboardInterrupt):
                self._print("", ts=False)
                return default
            if not answer:
                answer = default
            if required and not answer:
                self._print(f"  {s.YELLOW}⚠ 入力が必要です。{s.RESET}", ts=False)
                continue
            return answer

    def prompt_yes_no(self, label: str, default: bool = False) -> bool:
        """Y/N プロンプト。"""
        s = self.s
        hint = f"{s.BOLD}Y{s.RESET}/{s.DIM}n{s.RESET}" if default else f"{s.DIM}y{s.RESET}/{s.BOLD}N{s.RESET}"
        try:
            answer = input(f"  {s.GREEN}?{s.RESET} {label} [{hint}]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            self._print("", ts=False)
            return default
        if not answer:
            return default
        return answer in ("y", "yes")

    def prompt_multi_select(self, title: str, options: List[str]) -> List[int]:
        """複数番号のカンマ区切り選択。空入力で空リスト（＝全選択）を返す。"""
        s = self.s
        self._print(f"\n  {s.BOLD}{title}{s.RESET}", ts=False)
        self._print(f"  {s.DIM}カンマ区切りで番号を入力（Enter = 全選択）{s.RESET}", ts=False)
        self._print(f"  {s.DIM}{'─' * 50}{s.RESET}", ts=False)
        for i, opt in enumerate(options, 1):
            self._print(f"  {s.CYAN}{i:>3}{s.RESET})  {opt}", ts=False)
        self._print("", ts=False)

        while True:
            try:
                answer = input(f"  {s.GREEN}>{s.RESET} ").strip()
            except (EOFError, KeyboardInterrupt):
                self._print("", ts=False)
                return []
            if not answer:
                return []
            selected: List[int] = []
            valid = True
            for part in answer.split(","):
                part = part.strip()
                if part.isdigit():
                    idx = int(part, 10)
                    if 1 <= idx <= len(options):
                        selected.append(idx - 1)
                    else:
                        self._print(f"  {s.YELLOW}⚠ 範囲外: {idx}{s.RESET}", ts=False)
                        valid = False
                else:
                    self._print(f"  {s.YELLOW}⚠ 無効: {part!r}{s.RESET}", ts=False)
                    valid = False
            if selected:
                return selected
            if not valid:
                continue
            self._print(f"  {s.YELLOW}⚠ 有効な番号を入力してください{s.RESET}", ts=False)

    # ------------------------------------------------------------------
    # スピナー
    # ------------------------------------------------------------------

    def spinner_start(self, msg: str) -> None:
        """バックグラウンドスピナーを開始する。既に動作中の場合はメッセージのみ更新。"""
        if self.quiet or not self._is_tty:
            return
        with self._spinner_msg_lock:
            self._spinner_msg = msg
            self._spinner_base_msg = msg
            self._last_spinner_update = 0.0
        # 既にスピナーが動作中の場合はメッセージ更新のみ（ネスト防止）
        if self._spinner_thread is not None and self._spinner_thread.is_alive():
            return
        self._spinner_stop.clear()
        self._spinner_pause.clear()
        self._spinner_paused_ack.clear()
        s = self.s
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        def _spin() -> None:
            i = 0
            while not self._spinner_stop.is_set():
                # pause/resume 対応
                if self._spinner_pause.is_set():
                    sys.stdout.write(f"{s.CLEAR_LINE}")
                    sys.stdout.flush()
                    self._spinner_paused_ack.set()
                    # pause が解除されるまで待機
                    while self._spinner_pause.is_set() and not self._spinner_stop.is_set():
                        time.sleep(0.02)
                    self._spinner_paused_ack.clear()
                    if self._spinner_stop.is_set():
                        break
                frame = frames[i % len(frames)]
                with self._spinner_msg_lock:
                    current_msg = self._spinner_msg
                sys.stdout.write(f"{s.CLEAR_LINE}  {s.CYAN}{frame}{s.RESET} {current_msg}")
                sys.stdout.flush()
                i += 1
                self._spinner_stop.wait(0.08)
            sys.stdout.write(f"{s.CLEAR_LINE}")
            sys.stdout.flush()

        self._spinner_thread = threading.Thread(target=_spin, daemon=True)
        with self._output_lock:
            sys.stdout.write(self.s.HIDE_CURSOR)
            sys.stdout.flush()
        self._spinner_thread.start()

    def spinner_stop(self, result_msg: str = "") -> None:
        """スピナーを停止し、結果メッセージを表示する。"""
        if self._spinner_thread is None:
            return
        self._spinner_stop.set()
        self._spinner_thread.join(timeout=1.0)
        self._spinner_thread = None
        if self._is_tty:
            with self._output_lock:
                sys.stdout.write(self.s.SHOW_CURSOR)
                sys.stdout.flush()
        if result_msg:
            self._print(f"  {self.s.GREEN}✓{self.s.RESET} {result_msg}")

    # ------------------------------------------------------------------
    # 公開メソッド — 基本
    # ------------------------------------------------------------------

    def header(self, msg: str) -> None:
        """ヘッダー表示。quiet 以外で表示。"""
        s = self.s
        bar = f"{s.CYAN}{'━' * 60}{s.RESET}"
        self._print(f"\n{bar}")
        self._print(f"  {s.BOLD}{msg}{s.RESET}")
        self._print(f"{bar}\n")

    def status(self, msg: str) -> None:
        """重要ステータス。quiet 以外で常に確定行として表示。"""
        if self.quiet:
            return
        self._emit(f"  {msg}")

    def step_start(self, step_id: str, title: str, agent: Optional[str] = None) -> None:
        """ステップ開始。quiet 以外で表示。"""
        s = self.s
        agent_str = f" {s.DIM}(Agent: {agent}){s.RESET}" if agent else ""
        self._print(f"  {s.CYAN}▶{s.RESET} {s.BOLD}[Step.{step_id}]{s.RESET} {title}{agent_str}")
        self._step_start_times[step_id] = time.time()

    def step_end(self, step_id: str, status: str, elapsed: float = 0.0) -> None:
        """ステップ完了。quiet 以外で表示。Usage 累計サマリーを付加。"""
        self.spinner_stop()
        s = self.s
        icons = {"success": f"{s.GREEN}✅{s.RESET}", "failed": f"{s.RED}❌{s.RESET}", "skipped": f"{s.YELLOW}⏭️{s.RESET}"}
        icon = icons.get(status, "?")
        elapsed_str = f"{s.DIM}({elapsed:.1f}s){s.RESET}"
        # Usage 累計サマリーを付加
        usage_summary = ""
        if step_id in self._step_usage:
            usage_stats = self._step_usage[step_id]
            tool_count = self._step_tool_count.get(step_id, 0)
            usage_summary = (
                f" {s.DIM}[tokens: in={usage_stats['input_tokens']} out={usage_stats['output_tokens']}"
                f" tools={tool_count}]{s.RESET}"
            )
        self._print(f"  {icon} {s.BOLD}[Step.{step_id}]{s.RESET} {status} {elapsed_str}{usage_summary}")
        # クリーンアップ
        self._step_usage.pop(step_id, None)
        self._step_tool_count.pop(step_id, None)

    def event(self, msg: str) -> None:
        """イベント詳細。Level 3 (verbose) で確定行、Level 1-2 でスピナー更新。"""
        if self._verbosity == 0:
            return
        if self._verbosity >= 3:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    # ------------------------------------------------------------------
    # 公開メソッド — ツール
    # ------------------------------------------------------------------

    def tool(self, tool_name: str, step_id: str = "", args_summary: str = "") -> None:
        """ツール実行開始。Level 3 で確定行、Level 1-2 でスピナー更新。ツールカウンター付き。

        Args:
            tool_name: ツール名 (例: "bash", "edit_file", "grep")
            step_id:   ステップ ID (並列時の判別用)
            args_summary: 引数の要約 (ファイルパス等、簡潔に)
        """
        if self._verbosity == 0:
            return
        if step_id:
            self._step_tool_count[step_id] = self._step_tool_count.get(step_id, 0) + 1
            count = self._step_tool_count[step_id]
            count_str = f"({count})"
        else:
            count_str = ""
        prefix = f"[{step_id}] " if step_id else ""
        suffix = f" {args_summary}" if args_summary else ""
        msg = f"🔧 {prefix}{tool_name}{count_str}{suffix}"
        if self._verbosity >= 3:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    def tool_result(self, step_id: str, success: bool, error_msg: str = "") -> None:
        """ツール実行完了。Level 3 で成功・失敗ともに確定行、Level 1-2 で失敗のみ確定行。"""
        if self._verbosity == 0:
            return
        prefix = f"[{step_id}] " if step_id else ""
        if self._verbosity >= 3:
            if success:
                self._print(f"  ✓ {prefix}ツール完了")
            else:
                self._print(f"  ✗ {prefix}ツール失敗: {error_msg}")
        else:
            # Level 1-2: 失敗のみ確定行
            if not success:
                self._print(f"  ✗ {prefix}ツール失敗: {error_msg}")

    def tool_output(self, step_id: str, output: str, max_lines: int = 20) -> None:
        """ツールの部分出力。show_stream のみ表示。行数を制限。"""
        if self.quiet or not self.show_stream:
            return
        lines = output.splitlines()
        if len(lines) > max_lines:
            for line in lines[:max_lines]:
                self._print(f"    | {line}")
            self._print(f"    | ... ({len(lines) - max_lines} lines truncated)")
        else:
            with self._output_lock:
                sys.stdout.write(output)
                sys.stdout.flush()

    # ------------------------------------------------------------------
    # 公開メソッド — アシスタント / エージェント
    # ------------------------------------------------------------------

    def intent(self, step_id: str, intent_text: str) -> None:
        """エージェントの意図表示。Level 2+ で確定行、Level 1 でスピナー更新。"""
        if self._verbosity == 0:
            return
        prefix = f"[{step_id}] " if step_id else ""
        msg = f"💡 {prefix}{intent_text}"
        if self._verbosity >= 2:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    def turn_start(self, step_id: str, turn_id: str = "") -> None:
        """ターン開始。Level 3 で確定行、Level 1-2 でスピナー更新。"""
        if self._verbosity == 0:
            return
        prefix = f"[{step_id}] " if step_id else ""
        msg = f"🔄 {prefix}ターン開始"
        if self._verbosity >= 3:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    def turn_end(self, step_id: str) -> None:
        """ターン終了。Level 3 で確定行、それ以外は出力なし。"""
        if self._verbosity < 3:
            return
        prefix = f"[{step_id}] " if step_id else ""
        self._print(f"  🔄 {prefix}ターン終了")

    def assistant_message(self, step_id: str, content_len: int, tool_count: int) -> None:
        """アシスタント応答の概要。Level 3 で確定行、Level 1-2 でスピナー更新。"""
        if self._verbosity == 0:
            return
        prefix = f"[{step_id}] " if step_id else ""
        tools_str = f", ツール要求: {tool_count}" if tool_count else ""
        msg = f"💬 {prefix}応答 ({content_len} chars{tools_str})"
        if self._verbosity >= 3:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    def usage(self, step_id: str, model: str, input_tokens: int, output_tokens: int,
              duration_ms: Optional[int] = None) -> None:
        """トークン使用量。累計を蓄積し、Level 3 で確定行、Level 1-2 でスピナー更新。"""
        if self._verbosity == 0:
            return
        # トークン累計蓄積
        if step_id:
            if step_id not in self._step_usage:
                self._step_usage[step_id] = {"input_tokens": 0, "output_tokens": 0, "duration_ms": 0}
            self._step_usage[step_id]["input_tokens"] += input_tokens
            self._step_usage[step_id]["output_tokens"] += output_tokens
            if duration_ms:
                self._step_usage[step_id]["duration_ms"] += duration_ms
        prefix = f"[{step_id}] " if step_id else ""
        dur_str = f" {duration_ms}ms" if duration_ms else ""
        msg = f"📊 {prefix}{model} in={input_tokens} out={output_tokens}{dur_str}"
        if self._verbosity >= 3:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    # ------------------------------------------------------------------
    # 公開メソッド — サブエージェント / スキル
    # ------------------------------------------------------------------

    def subagent_started(self, step_id: str, name: str) -> None:
        """Sub-agent 開始。Level 3 で確定行、Level 1-2 でスピナー更新。"""
        if self._verbosity == 0:
            return
        prefix = f"[{step_id}] " if step_id else ""
        msg = f"▶ {prefix}Sub-agent: {name}"
        if self._verbosity >= 3:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    def subagent_completed(self, step_id: str, name: str) -> None:
        """Sub-agent 完了。Level 2+ で確定行、Level 1 でスピナー更新。"""
        if self._verbosity == 0:
            return
        prefix = f"[{step_id}] " if step_id else ""
        msg = f"✅ {prefix}Sub-agent 完了: {name}"
        if self._verbosity >= 2:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    def subagent_failed(self, step_id: str, name: str, error: str = "") -> None:
        """Sub-agent 失敗。Level 2+ で確定行、Level 1 でスピナー更新。"""
        if self._verbosity == 0:
            return
        prefix = f"[{step_id}] " if step_id else ""
        err = f" - {error}" if error else ""
        msg = f"❌ {prefix}Sub-agent 失敗: {name}{err}"
        if self._verbosity >= 2:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    def subagent_selected(self, step_id: str, name: str) -> None:
        """Agent 選択。Level 3 で確定行、Level 1-2 でスピナー更新。"""
        if self._verbosity == 0:
            return
        prefix = f"[{step_id}] " if step_id else ""
        msg = f"🤖 {prefix}Agent 選択: {name}"
        if self._verbosity >= 3:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    def skill_invoked(self, step_id: str, name: str) -> None:
        """Skill 読み込み。Level 3 で確定行、Level 1-2 でスピナー更新。"""
        if self._verbosity == 0:
            return
        prefix = f"[{step_id}] " if step_id else ""
        msg = f"📚 {prefix}Skill: {name}"
        if self._verbosity >= 3:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    # ------------------------------------------------------------------
    # 公開メソッド — セッション情報
    # ------------------------------------------------------------------

    def session_error(self, error_type: str, message: str) -> None:
        """セッションエラー。常に表示（quiet でも）。"""
        self._print(f"  ⚠️  Session error [{error_type}]: {message}", always=True)

    def context_usage(self, step_id: str, current_tokens: int, token_limit: int, msgs: int) -> None:
        """コンテキストウィンドウ使用率。80%以上は Level 1+ で警告、それ以外は Level 3 のみ。"""
        if self._verbosity == 0:
            return
        prefix = f"[{step_id}] " if step_id else ""
        pct = (current_tokens / token_limit * 100) if token_limit else 0
        msg = f"📏 {prefix}Context: {current_tokens}/{token_limit} ({pct:.0f}%) msgs={msgs}"
        if pct >= _CONTEXT_WARNING_THRESHOLD_PCT and self._verbosity >= 1:
            # 80%以上は Level 1+ で確定行警告
            self._print(f"  {msg}")
        elif self._verbosity >= 3:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    def compaction(self, step_id: str, phase: str, pre_tokens: int = 0, post_tokens: int = 0) -> None:
        """コンテキスト圧縮。Level 3 で確定行、Level 1-2 でスピナー更新。"""
        if self._verbosity == 0:
            return
        prefix = f"[{step_id}] " if step_id else ""
        if phase == "start":
            msg = f"📦 {prefix}コンテキスト圧縮中..."
        else:
            msg = f"📦 {prefix}圧縮完了: {pre_tokens} → {post_tokens} tokens"
        if self._verbosity >= 3:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    def task_complete(self, step_id: str, summary: str = "") -> None:
        """タスク完了。Level 2+ で確定行、Level 1 でスピナー更新。"""
        if self._verbosity == 0:
            return
        prefix = f"[{step_id}] " if step_id else ""
        preview = summary[:200] if summary else ""
        msg = f"🏁 {prefix}タスク完了{': ' + preview if preview else ''}"
        if self._verbosity >= 2:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    def shutdown_stats(self, step_id: str, lines_added: int, lines_removed: int,
                       files_modified: int, premium_requests: int,
                       api_duration_ms: int) -> None:
        """セッション終了統計。quiet 以外で表示。"""
        if self.quiet:
            return
        prefix = f"[{step_id}] " if step_id else ""
        self._print(
            f"  📈 {prefix}Stats: +{lines_added}/-{lines_removed} lines, "
            f"{files_modified} files, {premium_requests} reqs, {api_duration_ms}ms"
        )

    def permission(self, step_id: str, kind: str, resolved: bool = False, result: str = "") -> None:
        """パーミッション。Level 3 で確定行、Level 1-2 でスピナー更新。"""
        if self._verbosity == 0:
            return
        prefix = f"[{step_id}] " if step_id else ""
        if resolved:
            msg = f"🔐 {prefix}パーミッション: {result}"
        else:
            msg = f"🔐 {prefix}パーミッション要求: {kind}"
        if self._verbosity >= 3:
            self._print(f"  {msg}")
        else:
            self._update_spinner_msg(msg)

    # ------------------------------------------------------------------
    # 公開メソッド — CLI プロセスログ
    # ------------------------------------------------------------------

    def cli_log(self, step_id: str, line: str) -> None:
        """Copilot CLI プロセスのログ行を表示する。

        CLI プロセスが on_log コールバック経由で送出するログ行を、
        既存の hve コンソール出力と階層的にマージして表示する。

        CLI ログの種類を行頭文字で分類:
          ● (important): Environment loaded, Remote session 等の重要情報
          ○ (activity):  List directory, Search (glob) 等のツール活動
          └/├ (tree):    activity の子要素（引数詳細）

        verbosity に応じた制御:
          0 (quiet)  : 非表示
          1 (compact): ● Environment loaded のみ確定行、他の ● はスピナー更新
          2 (normal) : ● 行は確定行、○/ツリー行はスピナー更新
          3 (verbose): 全行を確定行で表示（ツリー構造を保持）

        Args:
            step_id: ステップ ID（並列時の判別用）。
            line: CLI プロセスからのログ行（1行）。
        """
        if self._verbosity == 0:
            return

        stripped = line.lstrip()
        prefix = f"[{step_id}] " if step_id else ""
        s = self.s

        # CLI ログの種類を判別
        is_important = stripped.startswith("●")
        is_activity = stripped.startswith("○")
        is_tree = stripped.startswith("└") or stripped.startswith("├")

        if self._verbosity >= 3:
            # verbose: 全行を確定行でインデント付き表示
            self._emit(f"  {s.DIM}┊{s.RESET} {s.GRAY}{prefix}{line}{s.RESET}")
        elif self._verbosity >= 2:
            # normal: ● 行は確定行、○/ツリー行はスピナー更新
            if is_important:
                self._emit(f"  {s.DIM}┊{s.RESET} {prefix}{line}")
            elif is_activity or is_tree:
                self._update_spinner_msg(f"  {s.DIM}┊{s.RESET} {prefix}{stripped}")
        else:
            # compact: ● Environment loaded は確定行、他の ● はスピナー、それ以外は無視
            if is_important and "Environment loaded" in stripped:
                self._emit(f"  {s.DIM}┊{s.RESET} {prefix}{line}")
            elif is_important:
                self._update_spinner_msg(f"  {prefix}{stripped}")

    # ------------------------------------------------------------------
    # 公開メソッド — ストリーム
    # ------------------------------------------------------------------

    def stream_start(self, step_id: str) -> None:
        """ストリーム出力開始マーカー。show_stream=True かつ quiet=False 時のみ表示。"""
        if self.quiet or not self.show_stream:
            return
        self._print(f"  📝 [Step.{step_id}] ストリーム開始 >>>")

    def stream_token(self, step_id: str, token: str) -> None:
        """トークンを逐次出力（改行なし）。show_stream=True かつ quiet=False 時のみ表示。"""
        if self.quiet or not self.show_stream:
            return
        sys.stdout.write(token)
        sys.stdout.flush()

    def stream_end(self, step_id: str) -> None:
        """ストリーム出力終了マーカー。show_stream=True かつ quiet=False 時のみ表示。"""
        if self.quiet or not self.show_stream:
            return
        self._print(f"\n  <<< [Step.{step_id}] ストリーム終了")

    # ------------------------------------------------------------------
    # 公開メソッド — QA / Review / その他
    # ------------------------------------------------------------------

    def qa_prompt(self, content: str) -> None:
        """QA 質問票表示。quiet 以外で表示。"""
        self._print("\n--- QA 質問票 ---")
        self._print(content)
        self._print("--- QA 質問票 終了 ---\n")

    def questionnaire_table(
        self,
        questions: List[QAQuestion],
        max_col_width: int = 40,
    ) -> None:
        """QA 質問票を 5列テーブル形式で表示する。

        5列: No. | 質問 | 選択肢 | デフォルトの回答案 | 回答案の理由

        TTY 接続時はボックス罫線 + ANSI カラーで描画し、
        非 TTY 時はプレーンテキストテーブル（| 区切り）を出力する。
        空リストの場合は何も表示しない。

        Args:
            questions: 表示する QAQuestion のリスト。
            max_col_width: 各列の最大表示幅（これを超えたセルは「...」で省略）。
        """
        if not questions:
            return

        headers = ["No.", "質問", "選択肢", "デフォルトの回答案", "回答案の理由"]

        # 各行のセルを構築
        rows: List[List[str]] = []
        for q in questions:
            if q.choices:
                choices_str = " / ".join(f"{c.label}) {c.text}" for c in q.choices)
            else:
                choices_str = ""
            rows.append([
                str(q.no),
                q.question,
                choices_str,
                q.default_answer,
                q.reason,
            ])

        # 列ごとの最大幅を計算（ヘッダーと全行から）
        col_widths = [self._visible_len(h) for h in headers]
        for row in rows:
            for ci, cell in enumerate(row):
                w = min(self._visible_len(cell), max_col_width)
                col_widths[ci] = max(col_widths[ci], w)

        # ターミナル幅チェック（超過時は各列を max_col_width でクリップ）
        term_width = shutil.get_terminal_size(fallback=(120, 24)).columns
        total_table_width = sum(col_widths) + 3 * len(col_widths) + 1  # borders + padding
        if total_table_width > term_width:
            # No. 列以外をクリップ
            for ci in range(1, len(col_widths)):
                col_widths[ci] = min(col_widths[ci], max_col_width)

        def _truncate(text: str, max_w: int) -> str:
            """表示幅が max_w を超えたら末尾を「...」で省略する。"""
            if self._visible_len(text) <= max_w:
                return text
            result = ""
            width = 0
            for c in text:
                eaw = unicodedata.east_asian_width(c)
                cw = 2 if eaw in ("W", "F", "A") else 1
                if width + cw > max_w - 3:
                    break
                result += c
                width += cw
            return result + "..."

        def _pad(text: str, width: int) -> str:
            """テキストを指定表示幅まで右側スペースでパディングする。"""
            vlen = self._visible_len(text)
            pad = max(0, width - vlen)
            return text + " " * pad

        s = self.s

        if self._is_tty:
            # TTY: ボックス罫線 + ANSI カラー描画
            def _hline(left: str, mid: str, right: str, fill: str) -> str:
                parts = [fill * (w + 2) for w in col_widths]
                return "  " + left + mid.join(parts) + right

            top = _hline("┌", "┬", "┐", "─")
            head_sep = _hline("├", "┼", "┤", "─")
            bottom = _hline("└", "┴", "┘", "─")

            self._print(f"{s.GRAY}{top}{s.RESET}", ts=False)

            # ヘッダー行
            header_cells = [
                f" {s.BOLD}{_pad(_truncate(h, col_widths[ci]), col_widths[ci])}{s.RESET} "
                for ci, h in enumerate(headers)
            ]
            self._print(
                f"  {s.GRAY}│{s.RESET}" + f"{s.GRAY}│{s.RESET}".join(header_cells) + f"{s.GRAY}│{s.RESET}",
                ts=False,
            )
            self._print(f"{s.GRAY}{head_sep}{s.RESET}", ts=False)

            # データ行
            for row in rows:
                cells = []
                for ci, cell in enumerate(row):
                    truncated = _truncate(cell, col_widths[ci])
                    padded = _pad(truncated, col_widths[ci])
                    if ci == 0:
                        # No. 列: CYAN + right-align (row[0] is already a str)
                        no_str = row[0].rjust(col_widths[0])
                        cells.append(f" {s.CYAN}{no_str}{s.RESET} ")
                    else:
                        cells.append(f" {padded} ")
                self._print(
                    f"  {s.GRAY}│{s.RESET}" + f"{s.GRAY}│{s.RESET}".join(cells) + f"{s.GRAY}│{s.RESET}",
                    ts=False,
                )

            self._print(f"{s.GRAY}{bottom}{s.RESET}", ts=False)

        else:
            # 非 TTY: プレーンテキストテーブル（| 区切り）
            def _plain_row(cells: List[str]) -> str:
                return "  " + " | ".join(
                    _pad(_truncate(cell, col_widths[ci]), col_widths[ci])
                    for ci, cell in enumerate(cells)
                )

            self._print(_plain_row(headers), ts=False)
            self._print(
                "  " + " | ".join("-" * col_widths[ci] for ci in range(len(headers))),
                ts=False,
            )
            for row in rows:
                self._print(_plain_row(row), ts=False)

        self._print("", ts=False)

    def prompt_answer_mode(self) -> str:
        """回答モード選択プロンプト。

        「全問まとめて回答」か「1問ずつ回答」かをユーザーに選択させる。

        Returns:
            "all" = 全問まとめて回答、"one" = 1問ずつ回答。
        """
        idx = self.menu_select(
            "回答モードを選択してください",
            [
                "全問まとめて回答（一括入力）",
                "1問ずつ回答（順番に入力）",
            ],
        )
        return "all" if idx == 0 else "one"

    def prompt_question_answer(self, question: QAQuestion) -> str:
        """1問ずつ回答プロンプト。

        5列テーブル（1行分）を表示した後、回答を入力させる。
        選択肢ラベル（例: "A"）のみを受け付ける。不正入力は再入力を促す。
        空入力はデフォルトラベルを採用する。

        選択肢がない質問（自由記述）は QAMerger がラベル入力を前提とするため
        プロンプトを省略し、デフォルト回答をそのまま返す。

        Args:
            question: 回答対象の QAQuestion。

        Returns:
            選択肢ラベル（例: "A"）。
            選択肢なし質問の場合、または空入力時はデフォルトラベルを返す。
        """
        self.questionnaire_table([question])
        s = self.s

        if not question.choices:
            # 選択肢なし質問: QAMerger がラベル入力を前提とするため自由記述は受け付けない
            # デフォルト回答のラベル部分を抽出して返す
            if question.default_answer:
                m = re.match(r"^([A-Za-z])\)", question.default_answer.strip())
                if m:
                    return m.group(1).upper()
            return ""

        valid_labels = [c.label.upper() for c in question.choices]
        labels_str = ", ".join(valid_labels)
        # デフォルト回答のラベル部分を抽出（"A) テキスト" → "A"）
        # 抽出できない場合は空文字列（full string を使うと valid_labels 検証で誤動作するため）
        default_label = ""
        if question.default_answer:
            m = re.match(r"^([A-Za-z])\)", question.default_answer.strip())
            default_label = m.group(1).upper() if m else ""

        while True:
            answer = self.prompt_input(
                f"回答 (有効な選択肢: {labels_str})",
                default=default_label,
            )
            if not answer:
                # 空入力 → デフォルトラベルを返す（空の場合は空文字のまま）
                return default_label
            answer_upper = answer.strip().upper()
            if answer_upper in valid_labels:
                return answer_upper
            self._print(
                f"  {s.YELLOW}⚠ 有効な選択肢: {labels_str} を入力してください{s.RESET}",
                ts=False,
            )

    def answer_summary(
        self,
        questions: List[QAQuestion],
        answers: Dict[int, str],
    ) -> None:
        """回答サマリーをパネル形式で表示する。

        変更数（デフォルト以外の回答）と デフォルト採用数を集計して表示する。

        Args:
            questions: QAQuestion のリスト。
            answers: {質問番号: 選択肢ラベル} の辞書。
        """
        if self.quiet:
            return
        total = len(questions)
        changed = 0
        for q in questions:
            if q.no in answers:
                # デフォルト回答のラベルと比較
                default_label = ""
                if q.default_answer:
                    m = re.match(r"^([A-Za-z])\)", q.default_answer.strip())
                    default_label = m.group(1).upper() if m else ""
                user = answers[q.no].strip().upper()
                if user and user != default_label.upper():
                    changed += 1
        defaults_used = total - changed
        self.panel("回答サマリー", [
            f"全質問数      : {total}",
            f"回答変更      : {changed}",
            f"デフォルト採用: {defaults_used}",
        ])

    def review_result(self, content: str) -> None:
        """Review 結果表示。quiet 以外で表示。"""
        self._print("\n--- Review 結果 ---")
        self._print(content)
        self._print("--- Review 結果 終了 ---\n")

    def summary(self, results: dict) -> None:
        """最終サマリー。quiet 以外で表示。Copilot CLI スタイルのパネル。"""
        s = self.s
        success = results.get("success", 0)
        failed = results.get("failed", 0)
        skipped = results.get("skipped", 0)
        total = success + failed + skipped
        elapsed = results.get("total_elapsed", self._elapsed())
        self.panel("実行サマリー", [
            f"合計ステップ : {s.BOLD}{total}{s.RESET}",
            f"{s.GREEN}✅ 成功{s.RESET}      : {success}",
            f"{s.RED}❌ 失敗{s.RESET}      : {failed}",
            f"{s.YELLOW}⏭️  スキップ{s.RESET}  : {skipped}",
            f"⏱️  合計時間  : {elapsed:.1f}s",
        ], ts=True)

    # ------------------------------------------------------------------
    # 公開メソッド — ワークフローフェーズ / DAG 進捗 / ステップ内フェーズ
    # ------------------------------------------------------------------

    def phase_start(self, phase_num: int, total_phases: int, title: str) -> None:
        """ワークフローフェーズ開始。quiet 以外で表示。"""
        if self.quiet:
            return
        s = self.s
        self._print(
            f"{s.BOLD}▸ Phase {phase_num}/{total_phases}:{s.RESET} {title}",
        )

    def phase_end(self, phase_num: int, total_phases: int, title: str, elapsed: float) -> None:
        """ワークフローフェーズ完了。quiet 以外で表示。"""
        if self.quiet:
            return
        s = self.s
        self._print(
            f"{s.BOLD}▸ Phase {phase_num}/{total_phases}:{s.RESET} {title} "
            f"{s.GREEN}✓{s.RESET} {s.DIM}({elapsed:.1f}s){s.RESET}",
        )

    def dag_wave_start(self, wave_num: int, total_waves: int, steps: List[Any]) -> None:
        """Wave (並列バッチ) 開始。quiet 以外で表示。"""
        if self.quiet:
            return
        s = self.s
        labels = []
        for step in steps:
            if hasattr(step, "id"):
                labels.append(f"Step.{step.id}")
            else:
                labels.append(str(step))
        joined = f" {s.DIM}‖{s.RESET} ".join(labels)
        bar = f"{s.DIM}{'─' * 48}{s.RESET}"
        self._print(f"\n  {s.CYAN}────{s.RESET} Wave {wave_num}/{total_waves} {bar}")
        self._print(f"  {s.CYAN}▸{s.RESET} {joined}")

    def dag_progress(self, completed: int, running: int, total: int) -> None:
        """DAG 全体の進捗バー。quiet 以外で表示。"""
        if self.quiet:
            return
        s = self.s
        remaining = total - completed - running
        bar_width = 16
        filled = int(bar_width * completed / total) if total else 0
        bar = "█" * filled + "░" * (bar_width - filled)
        self._print(
            f"  {s.DIM}進捗:{s.RESET} {bar} "
            f"{s.BOLD}{completed}/{total}{s.RESET} 完了 "
            f"{s.DIM}| 実行中 {running} | 残り {remaining}{s.RESET}",
        )

    def step_phase_start(self, step_id: str, phase_num: int, total_phases: int, name: str) -> None:
        """ステップ内フェーズ開始。quiet 以外で表示。"""
        if self.quiet:
            return
        s = self.s
        self._print(
            f"  {s.DIM}┊{s.RESET} Phase {phase_num}/{total_phases}: {name}",
        )

    def step_phase_end(
        self, step_id: str, phase_num: int, total_phases: int, name: str,
        elapsed: float, result: str = "",
    ) -> None:
        """ステップ内フェーズ完了。quiet 以外で表示。"""
        if self.quiet:
            return
        s = self.s
        result_str = f" {result}" if result else ""
        self._print(
            f"  {s.DIM}┊{s.RESET} Phase {phase_num}/{total_phases}: {name} "
            f"{s.GREEN}✓{s.RESET} {s.DIM}({elapsed:.1f}s){s.RESET}{result_str}",
        )

    def execution_plan(self, waves: List[List[Any]], total_steps: int, max_parallel: int) -> None:
        """実行計画パネルを表示する。quiet 以外で表示。"""
        if self.quiet:
            return
        lines: List[str] = []
        for i, wave_steps in enumerate(waves, 1):
            labels = []
            for step in wave_steps:
                title = getattr(step, "title", "")
                sid = getattr(step, "id", str(step))
                label = f"Step.{sid}"
                if title:
                    label += f" {title}"
                labels.append(label)
            joined = " ‖ ".join(labels)
            lines.append(f"Wave {i}: {joined}")
        lines.append(f"合計: {total_steps} ステップ / {len(waves)} Wave / 並列上限: {max_parallel}")
        self.panel("実行計画 (DAG)", lines)

    def step_elapsed(self, step_id: str) -> None:
        """実行中ステップの経過時間を表示する。Level 3 で確定行、Level 1-2 でスピナー更新。"""
        if self._verbosity == 0:
            return
        start = self._step_start_times.get(step_id)
        if start is None:
            return
        elapsed = time.time() - start
        minutes = int(elapsed) // 60
        seconds = int(elapsed) % 60
        msg = f"⏱ [Step.{step_id}] {minutes}m {seconds}s 経過..."
        if self._verbosity >= 3:
            self._print(f"  {self.s.DIM}{msg}{self.s.RESET}")
        else:
            self._update_spinner_msg(msg)

    # ------------------------------------------------------------------
    # 公開メソッド — DAG / 進捗
    # ------------------------------------------------------------------

    def dag_batch(self, steps: List[Any]) -> None:
        """並列バッチ表示。verbose のみ表示。"""
        if self._verbosity < 3:
            return
        s = self.s
        labels = []
        for step in steps:
            if hasattr(step, "id"):
                labels.append(f"Step.{step.id}")
            else:
                labels.append(str(step))
        joined = f" {s.DIM}‖{s.RESET} ".join(labels)
        self._print(f"  {s.CYAN}═══{s.RESET} 並列バッチ: {joined} {s.CYAN}═══{s.RESET}")

    def progress(self, current: int, total: int, msg: str = "") -> None:
        """プログレス表示。quiet 以外で表示。"""
        suffix = f" {msg}" if msg else ""
        self._print(f"  [{current}/{total}]{suffix}")

    def warning(self, msg: str) -> None:
        """警告表示。quiet 以外で表示。stderr に出力。"""
        if not self.quiet:
            print(f"{timestamp_prefix()} ⚠️  {msg}", file=sys.stderr, flush=True)

    def error(self, msg: str) -> None:
        """エラー表示。常に表示（quiet でも表示）。"""
        print(f"{timestamp_prefix()} ❌ ERROR: {msg}", file=sys.stderr, flush=True)

