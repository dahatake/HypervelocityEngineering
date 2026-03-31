"""console.py — Console 出力制御

GitHub Copilot CLI スタイルのリッチターミナル出力を提供する。
ANSI カラー・ボックス描画・スピナー・インタラクティブメニューに対応。
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


def timestamp_prefix() -> str:
    """現在時刻のプレフィックス文字列を返す。"""
    return f"[{datetime.now().strftime('%H:%M:%S')}]"


# ------------------------------------------------------------------
# ANSI エスケープコード
# ------------------------------------------------------------------

class _Style:
    """ANSI エスケープシーケンス定数。TTY 非接続時は空文字列。"""

    def __init__(self, is_tty: bool) -> None:
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

    - verbose=True (デフォルト): 全メッセージを表示
    - verbose=False: header, step_start, step_end, summary のみ表示
    - quiet=True: error 以外の全出力を抑制
    - show_stream=True: トークンストリーム/ツール部分出力を表示
    """

    def __init__(self, verbose: bool = True, quiet: bool = False, show_stream: bool = False) -> None:
        self.verbose = verbose
        self.quiet = quiet
        self.show_stream = show_stream
        self._start_time = time.time()
        self._is_tty = sys.stdout.isatty()
        self.s = _Style(self._is_tty)
        self._spinner_thread: Optional[threading.Thread] = None
        self._spinner_stop = threading.Event()
        self._step_start_times: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _print(self, msg: str, always: bool = False, ts: bool = True) -> None:
        """quiet でも表示する場合は always=True を渡す。ts=True で現在時刻を先頭に付与する。"""
        if always or not self.quiet:
            if ts:
                print(f"{timestamp_prefix()} {msg}", flush=True)
            else:
                print(msg, flush=True)

    def _elapsed(self) -> float:
        return time.time() - self._start_time

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """秒数を人間が読みやすい形式に変換する（例: 1h 23m 45s, 2m 30s, 45.3s）。"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        if minutes < 60:
            return f"{minutes}m {secs}s"
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}h {mins}m {secs}s"

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
        """バックグラウンドスピナーを開始する。"""
        if self.quiet or not self._is_tty:
            return
        self._spinner_stop.clear()
        s = self.s
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        def _spin() -> None:
            i = 0
            while not self._spinner_stop.is_set():
                frame = frames[i % len(frames)]
                sys.stdout.write(f"{s.CLEAR_LINE}  {s.CYAN}{frame}{s.RESET} {msg}")
                sys.stdout.flush()
                i += 1
                self._spinner_stop.wait(0.08)
            sys.stdout.write(f"{s.CLEAR_LINE}")
            sys.stdout.flush()

        self._spinner_thread = threading.Thread(target=_spin, daemon=True)
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

    def step_start(self, step_id: str, title: str, agent: Optional[str] = None) -> None:
        """ステップ開始。quiet 以外で表示。"""
        s = self.s
        agent_str = f" {s.DIM}(Agent: {agent}){s.RESET}" if agent else ""
        self._print(f"  {s.CYAN}▶{s.RESET} {s.BOLD}[Step.{step_id}]{s.RESET} {title}{agent_str}")
        self._step_start_times[step_id] = time.time()

    def step_end(self, step_id: str, status: str, elapsed: float = 0.0) -> None:
        """ステップ完了。quiet 以外で表示。"""
        s = self.s
        icons = {"success": f"{s.GREEN}✅{s.RESET}", "failed": f"{s.RED}❌{s.RESET}", "skipped": f"{s.YELLOW}⏭️{s.RESET}"}
        icon = icons.get(status, "?")
        duration_str = self._format_duration(elapsed)
        self._print(f"  {icon} {s.BOLD}[Step.{step_id}]{s.RESET} {status} {s.CYAN}⏱ 実行時間: {duration_str}{s.RESET}")

    def event(self, msg: str) -> None:
        """イベント詳細。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        self._print(f"  {msg}")

    # ------------------------------------------------------------------
    # 公開メソッド — ツール
    # ------------------------------------------------------------------

    def tool(self, tool_name: str, step_id: str = "", args_summary: str = "") -> None:
        """ツール実行開始。verbose のみ表示。

        Args:
            tool_name: ツール名 (例: "bash", "edit_file", "grep")
            step_id:   ステップ ID (並列時の判別用)
            args_summary: 引数の要約 (ファイルパス等、簡潔に)
        """
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        suffix = f" {args_summary}" if args_summary else ""
        self._print(f"  🔧 {prefix}{tool_name}{suffix}")

    def tool_result(self, step_id: str, success: bool, error_msg: str = "") -> None:
        """ツール実行完了。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        if success:
            self._print(f"  ✓ {prefix}ツール完了")
        else:
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
            sys.stdout.write(output)
            sys.stdout.flush()

    # ------------------------------------------------------------------
    # 公開メソッド — アシスタント / エージェント
    # ------------------------------------------------------------------

    def intent(self, step_id: str, intent_text: str) -> None:
        """エージェントの意図表示。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        self._print(f"  💡 {prefix}{intent_text}")

    def turn_start(self, step_id: str, turn_id: str = "") -> None:
        """ターン開始。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        self._print(f"  🔄 {prefix}ターン開始")

    def turn_end(self, step_id: str) -> None:
        """ターン終了。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        self._print(f"  🔄 {prefix}ターン終了")

    def assistant_message(self, step_id: str, content_len: int, tool_count: int) -> None:
        """アシスタント応答の概要。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        tools_str = f", ツール要求: {tool_count}" if tool_count else ""
        self._print(f"  💬 {prefix}応答 ({content_len} chars{tools_str})")

    def usage(self, step_id: str, model: str, input_tokens: int, output_tokens: int,
              duration_ms: Optional[int] = None) -> None:
        """トークン使用量。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        dur_str = f" {duration_ms}ms" if duration_ms else ""
        self._print(f"  📊 {prefix}{model} in={input_tokens} out={output_tokens}{dur_str}")

    # ------------------------------------------------------------------
    # 公開メソッド — サブエージェント / スキル
    # ------------------------------------------------------------------

    def subagent_started(self, step_id: str, name: str) -> None:
        """Sub-agent 開始。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        self._print(f"  ▶ {prefix}Sub-agent: {name}")

    def subagent_completed(self, step_id: str, name: str) -> None:
        """Sub-agent 完了。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        self._print(f"  ✅ {prefix}Sub-agent 完了: {name}")

    def subagent_failed(self, step_id: str, name: str, error: str = "") -> None:
        """Sub-agent 失敗。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        err = f" - {error}" if error else ""
        self._print(f"  ❌ {prefix}Sub-agent 失敗: {name}{err}")

    def subagent_selected(self, step_id: str, name: str) -> None:
        """Agent 選択。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        self._print(f"  🤖 {prefix}Agent 選択: {name}")

    def skill_invoked(self, step_id: str, name: str) -> None:
        """Skill 読み込み。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        self._print(f"  📚 {prefix}Skill: {name}")

    # ------------------------------------------------------------------
    # 公開メソッド — セッション情報
    # ------------------------------------------------------------------

    def session_error(self, error_type: str, message: str) -> None:
        """セッションエラー。常に表示（quiet でも）。"""
        self._print(f"  ⚠️  Session error [{error_type}]: {message}", always=True)

    def context_usage(self, step_id: str, current_tokens: int, token_limit: int, msgs: int) -> None:
        """コンテキストウィンドウ使用率。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        pct = (current_tokens / token_limit * 100) if token_limit else 0
        self._print(f"  📏 {prefix}Context: {current_tokens}/{token_limit} ({pct:.0f}%) msgs={msgs}")

    def compaction(self, step_id: str, phase: str, pre_tokens: int = 0, post_tokens: int = 0) -> None:
        """コンテキスト圧縮。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        if phase == "start":
            self._print(f"  📦 {prefix}コンテキスト圧縮中...")
        else:
            self._print(f"  📦 {prefix}圧縮完了: {pre_tokens} → {post_tokens} tokens")

    def task_complete(self, step_id: str, summary: str = "") -> None:
        """タスク完了。quiet 以外で表示。"""
        prefix = f"[{step_id}] " if step_id else ""
        preview = summary[:200] if summary else ""
        self._print(f"  🏁 {prefix}タスク完了{': ' + preview if preview else ''}")

    def shutdown_stats(self, step_id: str, lines_added: int, lines_removed: int,
                       files_modified: int, premium_requests: int,
                       api_duration_ms: int) -> None:
        """セッション終了統計。quiet 以外で表示。"""
        prefix = f"[{step_id}] " if step_id else ""
        self._print(
            f"  📈 {prefix}Stats: +{lines_added}/-{lines_removed} lines, "
            f"{files_modified} files, {premium_requests} reqs, {api_duration_ms}ms"
        )

    def permission(self, step_id: str, kind: str, resolved: bool = False, result: str = "") -> None:
        """パーミッション。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        prefix = f"[{step_id}] " if step_id else ""
        if resolved:
            self._print(f"  🔐 {prefix}パーミッション: {result}")
        else:
            self._print(f"  🔐 {prefix}パーミッション要求: {kind}")

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
        duration_str = self._format_duration(elapsed)
        self.panel("実行サマリー", [
            f"合計ステップ : {s.BOLD}{total}{s.RESET}",
            f"{s.GREEN}✅ 成功{s.RESET}      : {success}",
            f"{s.RED}❌ 失敗{s.RESET}      : {failed}",
            f"{s.YELLOW}⏭️  スキップ{s.RESET}  : {skipped}",
            f"⏱️  全体の実行時間: {s.BOLD}{duration_str}{s.RESET}",
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
        duration_str = self._format_duration(elapsed)
        self._print(
            f"{s.BOLD}▸ Phase {phase_num}/{total_phases}:{s.RESET} {title} "
            f"{s.GREEN}✓{s.RESET} ⏱ {duration_str}",
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
        duration_str = self._format_duration(elapsed)
        result_str = f" {result}" if result else ""
        self._print(
            f"  {s.DIM}┊{s.RESET} Phase {phase_num}/{total_phases}: {name} "
            f"{s.GREEN}✓{s.RESET} ⏱ {duration_str}{result_str}",
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
        """実行中ステップの経過時間を表示する。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        start = self._step_start_times.get(step_id)
        if start is None:
            return
        elapsed = time.time() - start
        minutes = int(elapsed) // 60
        seconds = int(elapsed) % 60
        self._print(f"  {self.s.DIM}⏱ [Step.{step_id}] {minutes}m {seconds}s 経過...{self.s.RESET}")

    # ------------------------------------------------------------------
    # 公開メソッド — DAG / 進捗
    # ------------------------------------------------------------------

    def dag_batch(self, steps: List[Any]) -> None:
        """並列バッチ表示。verbose のみ表示。"""
        if self.quiet or not self.verbose:
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
