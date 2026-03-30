"""console.py — Console 出力制御"""

from __future__ import annotations

import sys
import time
from typing import Any, Dict, List, Optional


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

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _print(self, msg: str, always: bool = False) -> None:
        """quiet でも表示する場合は always=True を渡す。"""
        if always or not self.quiet:
            print(msg, flush=True)

    def _elapsed(self) -> float:
        return time.time() - self._start_time

    # ------------------------------------------------------------------
    # 公開メソッド — 基本
    # ------------------------------------------------------------------

    def header(self, msg: str) -> None:
        """ヘッダー表示。quiet 以外で表示。"""
        self._print(f"\n{'=' * 60}")
        self._print(f"  {msg}")
        self._print(f"{'=' * 60}\n")

    def step_start(self, step_id: str, title: str, agent: Optional[str] = None) -> None:
        """ステップ開始。quiet 以外で表示。"""
        agent_str = f" (Agent: {agent})" if agent else ""
        self._print(f"▶ [Step.{step_id}] {title}{agent_str}")

    def step_end(self, step_id: str, status: str, elapsed: float = 0.0) -> None:
        """ステップ完了。quiet 以外で表示。"""
        icons = {"success": "✅", "failed": "❌", "skipped": "⏭️"}
        icon = icons.get(status, "?")
        self._print(f"{icon} [Step.{step_id}] {status} ({elapsed:.1f}s)")

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
        """最終サマリー。quiet 以外で表示。"""
        success = results.get("success", 0)
        failed = results.get("failed", 0)
        skipped = results.get("skipped", 0)
        total = success + failed + skipped
        elapsed = results.get("total_elapsed", self._elapsed())
        self._print("\n" + "=" * 60)
        self._print("  実行サマリー")
        self._print("=" * 60)
        self._print(f"  合計ステップ : {total}")
        self._print(f"  ✅ 成功      : {success}")
        self._print(f"  ❌ 失敗      : {failed}")
        self._print(f"  ⏭️  スキップ  : {skipped}")
        self._print(f"  ⏱️  合計時間  : {elapsed:.1f}s")
        self._print("=" * 60 + "\n")

    def dag_batch(self, steps: List[Any]) -> None:
        """並列バッチ表示。verbose のみ表示。"""
        if self.quiet or not self.verbose:
            return
        labels = []
        for s in steps:
            if hasattr(s, "id"):
                labels.append(f"Step.{s.id}")
            else:
                labels.append(str(s))
        joined = " ‖ ".join(labels)
        self._print(f"═══ 並列バッチ: {joined} ═══")

    def progress(self, current: int, total: int, msg: str = "") -> None:
        """プログレス表示。quiet 以外で表示。"""
        suffix = f" {msg}" if msg else ""
        self._print(f"  [{current}/{total}]{suffix}")

    def warning(self, msg: str) -> None:
        """警告表示。quiet 以外で表示。"""
        self._print(f"⚠️  {msg}")

    def error(self, msg: str) -> None:
        """エラー表示。常に表示（quiet でも表示）。"""
        print(f"❌ ERROR: {msg}", file=sys.stderr, flush=True)
