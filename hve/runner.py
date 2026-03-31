"""runner.py — StepRunner: 1 ステップを CopilotSession で実行する"""

from __future__ import annotations

import asyncio
import copy
import sys
import time
from typing import Any, Dict, List, Optional

# 並列ステップ間で stdin 読み取りが競合しないよう排他制御する Lock
_stdin_lock = asyncio.Lock()

try:
    from .config import SDKConfig
    from .console import Console, timestamp_prefix
    from .prompts import QA_PROMPT, QA_APPLY_PROMPT, REVIEW_PROMPT, ADVERSARIAL_RECHECK_PROMPT
except ImportError:
    from config import SDKConfig  # type: ignore[no-redef]
    from console import Console, timestamp_prefix  # type: ignore[no-redef]
    from prompts import QA_PROMPT, QA_APPLY_PROMPT, REVIEW_PROMPT, ADVERSARIAL_RECHECK_PROMPT  # type: ignore[no-redef]


def _is_review_fail(content: str) -> bool:
    """合格判定行のトークンから FAIL 判定かどうかを判定する。

    - 「合格判定」を含む行のみを対象にすることで、
      本文中に "fail" が含まれる場合の誤検知を防ぐ。
    - 合否行は「✅ PASS」または「❌ FAIL」といった一意なトークンを前提とし、
      テンプレート由来の「PASS / FAIL」併記行は FAIL とみなさない。

    敵対的レビューではサマリー/合格判定が必須のため、
    合格判定行が 1 行も見つからない場合はフォーマット不備として
    FAIL 扱い（再レビュー実行側に倒す）とする。
    """
    has_judgement_line = False
    for line in content.splitlines():
        if "合格判定" not in line:
            continue
        has_judgement_line = True

        # 明示的な ✅ PASS トークンがあれば FAIL ではない
        if "✅" in line and "PASS" in line.upper():
            return False

        # 明示的な ❌ FAIL トークンがある場合は FAIL
        if "❌" in line and "FAIL" in line.upper():
            return True

        # フォールバック: 絵文字なしでも大文字小文字を問わず FAIL を検出
        if "FAIL" in line.upper():
            return True

    # 合格判定行が存在しない場合は安全側に倒して FAIL 扱いとする
    return not has_judgement_line


class StepRunner:
    """1 ステップを CopilotSession で実行する。

    フロー (1ステップ内、同一セッション):
    ┌──────────────────────────────────────────────────┐
    │ CopilotSession (同一セッション = コンテキスト保持)   │
    │                                                    │
    │  Phase 1: session.send_and_wait(prompt)            │
    │    → Agent がメインタスク実行                        │
    │                                                    │
    │  [auto_qa=True の場合]                              │
    │  Phase 2a: session.send_and_wait(QA_PROMPT)        │
    │    → Agent が質問票生成                              │
    │  Phase 2b: CLI stdin でユーザー回答入力              │
    │    → skip 入力でデフォルト回答案適用                  │
    │  Phase 2c: session.send_and_wait(QA_APPLY_PROMPT)  │
    │    → Agent がユーザー回答を成果物に反映              │
    │                                                    │
    │  [auto_contents_review=True の場合]                 │
    │  Phase 3: session.send_and_wait(REVIEW_PROMPT)     │
    │    → 敵対的レビュー（5軸検証 + PASS/FAIL判定）       │
    │    → FAIL時: 再レビューサイクル（最大2回）            │
    │                                                    │
    │  session.disconnect()                              │
    └──────────────────────────────────────────────────┘
    """

    def __init__(self, config: SDKConfig, console: Console) -> None:
        self.config = config
        self.console = console

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    async def run_step(
        self,
        step_id: str,
        title: str,
        prompt: str,
        custom_agent: Optional[str] = None,
    ) -> bool:
        """ステップを実行する。

        Args:
            step_id: ステップ識別子（例: "1.1", "2.3"）
            title: ステップタイトル（表示用）
            prompt: メインタスクのプロンプト文字列
            custom_agent: 使用する Custom Agent 名（省略可）

        Returns:
            True: 成功, False: 失敗
        """
        start = time.time()

        # --- dry_run ---
        if self.config.dry_run:
            self.console.step_start(step_id, title, agent=custom_agent)
            self.console.event(f"[DRY-RUN] Step.{step_id} would execute: {title}")
            elapsed = time.time() - start
            self.console.step_end(step_id, "success", elapsed=elapsed)
            return True

        # --- SDK インポート確認 ---
        try:
            from copilot import CopilotClient, PermissionHandler  # type: ignore[import]
            from copilot import SubprocessConfig, ExternalServerConfig  # type: ignore[import]
        except ImportError:
            self.console.error(
                "GitHub Copilot SDK がインストールされていません。\n"
                "  pip install github-copilot-sdk  # または適切なパッケージ名で再試行してください。"
            )
            return False

        self.console.step_start(step_id, title, agent=custom_agent)
        self._current_step_id = step_id

        session = None
        client = None
        try:
            # SDK v0.2.0: CopilotClient(config=SubprocessConfig|ExternalServerConfig)
            if self.config.cli_url:
                sdk_config = ExternalServerConfig(url=self.config.cli_url)
            else:
                sdk_config = SubprocessConfig(
                    cli_path=self.config.cli_path,
                    github_token=self.config.resolve_token() or None,
                    log_level=self.config.log_level,
                )
            client = CopilotClient(config=sdk_config)
            await client.start()

            # セッション構築オプション
            session_opts: Dict[str, Any] = {
                "model": self.config.model,
                "on_permission_request": PermissionHandler.approve_all,
                "streaming": True,
            }

            # MCP Servers
            if self.config.mcp_servers:
                session_opts["mcp_servers"] = self.config.mcp_servers

            # Custom Agents (グローバル定義)
            custom_agents: List[Dict[str, Any]] = copy.deepcopy(
                self.config.custom_agents_config or []
            )

            # additional_prompt をグローバル定義の各 agent の prompt に追記
            if self.config.additional_prompt:
                suffix = self.config.additional_prompt
                for agent_def in custom_agents:
                    existing = agent_def.get("prompt", "")
                    if existing:
                        agent_def["prompt"] = existing + "\n\n" + suffix
                    else:
                        agent_def["prompt"] = suffix

            # ステップ固有 Custom Agent を先頭に追加し、agent で pre-select
            if custom_agent:
                # グローバル定義に同名がなければ最小定義を追加
                existing_names = {a.get("name") for a in custom_agents}
                if custom_agent not in existing_names:
                    base_prompt = f"You are {custom_agent}."
                    if self.config.additional_prompt:
                        base_prompt = base_prompt + "\n\n" + self.config.additional_prompt
                    custom_agents.insert(
                        0,
                        {
                            "name": custom_agent,
                            "display_name": custom_agent,
                            "description": f"Custom agent: {custom_agent}",
                            "tools": ["*"],
                            "prompt": base_prompt,
                        },
                    )
                session_opts["agent"] = custom_agent

            if custom_agents:
                session_opts["custom_agents"] = custom_agents

            session = await client.create_session(**session_opts)

            # イベント購読 (常に購読 — Console 側で出力レベルを制御)
            session.on(self._handle_session_event)

            # ストリーム表示の開始マーカー
            if self.console.show_stream:
                self.console.stream_start(step_id)

            # フェーズ総数を動的算出
            total_phases = 1
            if self.config.auto_qa:
                total_phases += 1
            if self.config.auto_contents_review:
                total_phases += 1
            current_phase = 0

            # Phase 1: メインタスク
            current_phase += 1
            phase1_start = time.time()
            self.console.step_phase_start(step_id, current_phase, total_phases, "メインタスク")
            await session.send_and_wait(prompt, timeout=self.config.timeout_seconds)
            self.console.step_phase_end(
                step_id, current_phase, total_phases, "メインタスク",
                elapsed=time.time() - phase1_start,
            )

            # Phase 2: QA（auto_qa=True の場合）
            if self.config.auto_qa:
                current_phase += 1
                phase2_start = time.time()
                self.console.step_phase_start(step_id, current_phase, total_phases, "QA レビュー")
                qa_response = await session.send_and_wait(QA_PROMPT, timeout=self.config.timeout_seconds)
                qa_content = _extract_text(qa_response)
                self.console.qa_prompt(qa_content)

                # stdin でユーザー回答を受け付ける
                user_answers = await _read_stdin_async(
                    prompt_msg=f"[Step.{step_id}] QA 回答を入力してください（Enterのみで skip／デフォルト回答適用）:",
                    console=self.console,
                    timeout=self.config.timeout_seconds,
                )

                if user_answers.strip().lower() in ("", "skip"):
                    user_answers = "(デフォルト回答を採用)"

                apply_prompt = QA_APPLY_PROMPT.format(user_answers=user_answers)
                await session.send_and_wait(apply_prompt, timeout=self.config.timeout_seconds)
                self.console.step_phase_end(
                    step_id, current_phase, total_phases, "QA レビュー",
                    elapsed=time.time() - phase2_start,
                )

            # Phase 3: 敵対的レビュー（auto_contents_review=True の場合）
            # 同一セッション内で実行する（成果物のコンテキストを保持するため）
            if self.config.auto_contents_review:
                current_phase += 1
                phase3_start = time.time()
                self.console.step_phase_start(step_id, current_phase, total_phases, "敵対的レビュー")
                # 1回目: 敵対的レビュー実行
                review_response = await session.send_and_wait(
                    REVIEW_PROMPT, timeout=self.config.timeout_seconds
                )
                review_content = _extract_text(review_response)
                self.console.review_result(review_content)

                # 初回 PASS 判定
                if not _is_review_fail(review_content):
                    self.console.event(
                        "✅ 敵対的レビュー PASS（初回） — 再レビュー不要"
                    )
                    self.console.step_phase_end(
                        step_id, current_phase, total_phases, "敵対的レビュー",
                        elapsed=time.time() - phase3_start, result="PASS",
                    )
                else:
                    # 再レビューサイクル（最大2回）
                    review_passed = False
                    for cycle in range(1, 3):  # cycle 1, 2
                        self.console.event(
                            f"❌ 敵対的レビュー FAIL — 再レビューサイクル {cycle}/2 を実行"
                        )
                        recheck_prompt = ADVERSARIAL_RECHECK_PROMPT.format(cycle=cycle)
                        recheck_response = await session.send_and_wait(
                            recheck_prompt, timeout=self.config.timeout_seconds
                        )
                        review_content = _extract_text(recheck_response)
                        self.console.review_result(review_content)

                        if not _is_review_fail(review_content):
                            self.console.event(
                                f"✅ 敵対的レビュー PASS（再レビューサイクル {cycle}/2 後）"
                            )
                            self.console.step_phase_end(
                                step_id, current_phase, total_phases, "敵対的レビュー",
                                elapsed=time.time() - phase3_start, result="PASS",
                            )
                            review_passed = True
                            break

                    if not review_passed:
                        self.console.step_phase_end(
                            step_id, current_phase, total_phases, "敵対的レビュー",
                            elapsed=time.time() - phase3_start, result="FAIL",
                        )
                        self.console.event(
                            "⚠️ 最大再レビューサイクル到達 — Critical が残存しています"
                        )
                        # Critical が残存している場合はステップ失敗として扱う
                        raise RuntimeError(
                            "Critical issues remain after maximum adversarial review cycles."
                        )

        except Exception as exc:
            self.console.error(f"Step.{step_id} 実行中にエラーが発生しました: {exc}")
            elapsed = time.time() - start
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False
        finally:
            if session is not None:
                try:
                    await session.disconnect()
                except Exception as cleanup_exc:
                    self.console.warning(f"[cleanup] session.disconnect() failed: {cleanup_exc}")
            if client is not None:
                try:
                    await client.stop()
                except Exception as cleanup_exc:
                    self.console.warning(f"[cleanup] client.stop() failed: {cleanup_exc}")

        elapsed = time.time() - start
        self.console.step_end(step_id, "success", elapsed=elapsed)
        return True

    # ------------------------------------------------------------------
    # 内部ヘルパー — SDK data 属性の安全取得
    # ------------------------------------------------------------------

    @staticmethod
    def _get(data: Any, *names: str, default: Any = "") -> Any:
        """data オブジェクトから属性を安全に取得する。

        SDK v0.2.0 Python では snake_case 属性名を使用するが、
        将来の変更に備え camelCase もフォールバックで試す。
        """
        if data is None:
            return default
        for name in names:
            val = getattr(data, name, None)
            if val is not None:
                return val
        return default

    # ------------------------------------------------------------------
    # 内部イベントハンドラー
    # ------------------------------------------------------------------

    def _handle_session_event(self, event: Any) -> None:
        """CopilotSession のイベントを受け取り Console に出力する。

        SDK v0.2.0 のイベントタイプ一覧:
        https://github.com/github/copilot-sdk/blob/main/docs/features/streaming-events.md
        """
        # SDK v0.2.0: event.type は SessionEventType enum、.value で文字列取得
        etype = getattr(getattr(event, "type", None), "value", "") or ""
        data = getattr(event, "data", None)
        step_id = getattr(self, "_current_step_id", "")
        _get = self._get

        # ディスパッチテーブルを使わず if-elif で処理する。
        # etype の出現頻度が高いものを上に配置。

        # --- ストリーム系 (高頻度、show_stream ガード) ---
        if etype == "assistant.message_delta":
            token = _get(data, "delta_content", "content") or ""
            if token:
                self.console.stream_token(step_id, token)
            return

        if etype == "assistant.streaming_delta":
            # バイト進捗 — 表示不要
            return

        # --- ツール実行 (高頻度) ---
        if etype == "tool.execution_start":
            tool_name = _get(data, "tool_name", "toolName", default="unknown")
            args = _get(data, "arguments", default=None)
            args_summary = ""
            if args and isinstance(args, dict):
                # ツールの種類に応じて主要引数を要約表示
                for key in ("command", "path", "filePath", "file_path", "query", "pattern", "url"):
                    val = args.get(key)
                    if val:
                        val_str = str(val)
                        args_summary = val_str[:80] + "..." if len(val_str) > 80 else val_str
                        break
            self.console.tool(tool_name, step_id=step_id, args_summary=args_summary)
            return

        if etype == "tool.execution_complete":
            success = _get(data, "success", default=False)
            error = _get(data, "error", default=None)
            error_msg = ""
            if error and not success:
                error_msg = _get(error, "message", default=str(error))
            self.console.tool_result(step_id, bool(success), error_msg=error_msg)
            return

        if etype == "tool.execution_partial_result":
            output = _get(data, "partial_output", "partialOutput") or ""
            if output:
                self.console.tool_output(step_id, output)
            return

        if etype == "tool.execution_progress":
            msg = _get(data, "progress_message", "progressMessage") or ""
            if msg:
                self.console.event(f"  ⏳ [{step_id}] {msg}")
            return

        # --- アシスタント応答 ---
        if etype == "assistant.intent":
            intent_text = _get(data, "intent") or ""
            if intent_text:
                self.console.intent(step_id, intent_text)
            return

        if etype == "assistant.turn_start":
            turn_id = _get(data, "turn_id", "turnId") or ""
            self.console.turn_start(step_id, turn_id)
            return

        if etype == "assistant.turn_end":
            self.console.stream_end(step_id)
            self.console.turn_end(step_id)
            return

        if etype == "assistant.message":
            content = _get(data, "content") or ""
            tool_reqs = _get(data, "tool_requests", "toolRequests", default=None) or []
            self.console.assistant_message(step_id, len(content), len(tool_reqs))
            return

        if etype == "assistant.reasoning":
            content = _get(data, "content") or ""
            self.console.event(f"💭 [{step_id}] 推論完了 ({len(content)} chars)")
            return

        if etype == "assistant.reasoning_delta":
            # 推論ストリーム — show_stream 時のみ表示
            token = _get(data, "delta_content", "deltaContent") or ""
            if token:
                self.console.stream_token(step_id, token)
            return

        if etype == "assistant.usage":
            model = _get(data, "model") or "?"
            inp = _get(data, "input_tokens", "inputTokens", default=0) or 0
            out = _get(data, "output_tokens", "outputTokens", default=0) or 0
            dur = _get(data, "duration", default=None)
            self.console.usage(step_id, model, int(inp), int(out),
                               duration_ms=int(dur) if dur else None)
            return

        # --- サブエージェント / スキル ---
        if etype == "subagent.started":
            name = _get(data, "agent_display_name", "agentDisplayName") or etype
            self.console.subagent_started(step_id, name)
            return

        if etype == "subagent.completed":
            name = _get(data, "agent_display_name", "agentDisplayName") or etype
            self.console.subagent_completed(step_id, name)
            return

        if etype == "subagent.failed":
            name = _get(data, "agent_display_name", "agentDisplayName") or etype
            err = _get(data, "error") or ""
            self.console.subagent_failed(step_id, name, error=str(err))
            return

        if etype == "subagent.selected":
            name = _get(data, "agent_display_name", "agentDisplayName") or ""
            self.console.subagent_selected(step_id, name)
            return

        if etype == "subagent.deselected":
            self.console.event(f"🤖 [{step_id}] Agent 解除")
            return

        if etype == "skill.invoked":
            name = _get(data, "name") or ""
            self.console.skill_invoked(step_id, name)
            return

        # --- セッション ---
        if etype == "session.error":
            err_type = _get(data, "error_type", "errorType") or ""
            message = _get(data, "message") or ""
            self.console.session_error(err_type, message)
            return

        if etype == "session.usage_info":
            limit = int(_get(data, "token_limit", "tokenLimit", default=0) or 0)
            current = int(_get(data, "current_tokens", "currentTokens", default=0) or 0)
            msgs = int(_get(data, "messages_length", "messagesLength", default=0) or 0)
            self.console.context_usage(step_id, current, limit, msgs)
            return

        if etype == "session.compaction_start":
            self.console.compaction(step_id, "start")
            return

        if etype == "session.compaction_complete":
            pre = int(_get(data, "pre_compaction_tokens", "preCompactionTokens", default=0) or 0)
            post = int(_get(data, "post_compaction_tokens", "postCompactionTokens", default=0) or 0)
            self.console.compaction(step_id, "complete", pre_tokens=pre, post_tokens=post)
            return

        if etype == "session.task_complete":
            summary = _get(data, "summary") or ""
            self.console.task_complete(step_id, summary=str(summary))
            return

        if etype == "session.shutdown":
            changes = _get(data, "code_changes", "codeChanges", default=None)
            reqs = int(_get(data, "total_premium_requests", "totalPremiumRequests", default=0) or 0)
            dur_ms = int(_get(data, "total_api_duration_ms", "totalApiDurationMs", default=0) or 0)
            lines_added = int(_get(changes, "lines_added", "linesAdded", default=0) or 0) if changes else 0
            lines_removed = int(_get(changes, "lines_removed", "linesRemoved", default=0) or 0) if changes else 0
            files_mod = int(_get(changes, "files_modified", "filesModified", default=0) or 0) if changes else 0
            self.console.shutdown_stats(step_id, lines_added, lines_removed,
                                        files_mod, reqs, dur_ms)
            return

        # --- パーミッション ---
        if etype == "permission.requested":
            req = _get(data, "permission_request", "permissionRequest", default=None)
            kind_obj = _get(req, "kind", default="") if req else ""
            kind_str = getattr(kind_obj, "value", str(kind_obj)) if kind_obj else ""
            self.console.permission(step_id, kind_str, resolved=False)
            return

        if etype == "permission.completed":
            result_obj = _get(data, "result", default=None)
            kind_str = _get(result_obj, "kind", default="") if result_obj else ""
            kind_val = getattr(kind_str, "value", str(kind_str)) if kind_str else ""
            self.console.permission(step_id, "", resolved=True, result=kind_val)
            return

        # --- その他 (既知だが詳細表示不要なイベント) ---
        if etype in (
            "session.idle",
            "session.title_changed",
            "session.context_changed",
            "user.message",
            "system.message",
            "tool.user_requested",
            "abort",
            "command.queued",
            "command.completed",
            "user_input.requested",
            "user_input.completed",
            "elicitation.requested",
            "elicitation.completed",
            "external_tool.requested",
            "external_tool.completed",
            "exit_plan_mode.requested",
            "exit_plan_mode.completed",
        ):
            return

        # 未知のイベントタイプ: 将来の SDK 更新に備え verbose で表示
        self.console.event(f"[{step_id}] event: {etype}")


# ------------------------------------------------------------------
# 内部ヘルパー
# ------------------------------------------------------------------


def _blocking_stdin_read() -> str:
    """スレッドプール内で実行するブロッキング stdin 読み取り。"""
    try:
        return sys.stdin.readline().rstrip("\n")
    except (EOFError, OSError):
        return ""


async def _read_stdin_async(
    prompt_msg: str,
    console: Any,
    timeout: float = 300.0,
) -> str:
    """asyncio イベントループをブロックせずに stdin から1行読み取る。

    - 並列ステップ間の競合を asyncio.Lock で排他制御
    - stdin が非対話的（パイプ等）の場合はスキップしてデフォルト値を返す
    - タイムアウト付きで無限ブロックを防止
    - ブロッキング I/O は run_in_executor でスレッドプールに委譲
    """
    # stdin が非対話的（パイプ、リダイレクト等）の場合はスキップ
    if not sys.stdin.isatty():
        console.warning(
            f"{prompt_msg}\n"
            "  → stdin が非対話モードのため、デフォルト回答を自動適用します。"
        )
        return ""

    async with _stdin_lock:
        # 他のステップのストリーム出力と視覚的に分離
        print(flush=True)
        print(f"{timestamp_prefix()} {"─" * 50}", flush=True)
        console.warning(prompt_msg)
        print(f"{timestamp_prefix()} {"─" * 50}", flush=True)

        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _blocking_stdin_read),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            console.warning(
                f"入力タイムアウト ({timeout:.0f}s)。デフォルト回答を自動適用します。"
            )
            result = ""

        return result


def _extract_text(response: Any) -> str:
    """SDK レスポンスからテキスト部分を取り出す。

    SDK v0.2.0: send_and_wait() は SessionEvent | None を返す。
    テキストは event.data.content に格納される。
    """
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    # SDK v0.2.0: SessionEvent.data.content
    data = getattr(response, "data", None)
    if data is not None:
        for attr in ("content", "message"):
            val = getattr(data, attr, None)
            if val is not None:
                return str(val)
    # フォールバック: response 直接の属性
    for attr in ("content", "text", "message"):
        val = getattr(response, attr, None)
        if val is not None:
            return str(val)
    # 未知の型の場合はフォールバックで空文字を返す（repr 文字列の混入を防止）
    return ""
