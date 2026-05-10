"""test_runner.py — StepRunner の dry_run テスト"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import DEFAULT_CONTEXT_INJECTION_MAX_CHARS, SDKConfig
from console import Console
from runner import (
    StepRunner,
    _extract_safe_qa_artifact_paths,
    _is_review_fail,
    _parse_qa_content_with_artifact_fallback,
    _truncate_context,
)
from workiq import WORKIQ_MCP_SERVER_NAME  # type: ignore[import-untyped]

# Sentinel for distinguishing "key absent" vs. "key present with None value" in sys.modules.
# Used in test_returns_false_when_sdk_missing to correctly restore sys.modules after the test.
_SENTINEL = object()


class _CaptureOutput:
    """stdout / stderr を一時的にキャプチャするコンテキストマネージャー。"""

    def __enter__(self):
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        return self

    def __exit__(self, *_):
        self.stdout = sys.stdout.getvalue()
        self.stderr = sys.stderr.getvalue()
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr


def _run(coro):
    """非同期コルーチンを同期的に実行するヘルパー。"""
    return asyncio.run(coro)


class TestStepRunnerDryRun(unittest.TestCase):
    """dry_run=True の場合、SDK 呼び出しをスキップして True を返す。"""

    def _make_runner(self, verbose: bool = True, **cfg_kwargs) -> StepRunner:
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.7", **cfg_kwargs)
        console = Console(verbose=verbose, quiet=False)
        return StepRunner(config=cfg, console=console)

    def test_dry_run_returns_true(self) -> None:
        runner = self._make_runner()
        with _CaptureOutput():
            result = _run(runner.run_step("1.1", "テストステップ", "テストプロンプト"))
        self.assertTrue(result)

    def test_dry_run_outputs_dry_run_message(self) -> None:
        runner = self._make_runner(verbose=True)
        with _CaptureOutput() as cap:
            _run(runner.run_step("1.1", "テストステップ", "テストプロンプト"))
        self.assertIn("DRY-RUN", cap.stdout)
        self.assertIn("Step.1.1", cap.stdout)

    def test_dry_run_with_custom_agent(self) -> None:
        runner = self._make_runner()
        with _CaptureOutput() as cap:
            result = _run(
                runner.run_step(
                    "2.3",
                    "サービス設計",
                    "サービスを設計してください",
                    custom_agent="Arch-Microservice-ServiceCatalog",
                )
            )
        self.assertTrue(result)
        self.assertIn("Arch-Microservice-ServiceCatalog", cap.stdout)

    def test_dry_run_no_sdk_import_required(self) -> None:
        """dry_run=True では copilot SDK がなくても実行できる。"""
        runner = self._make_runner()
        # SDK が存在しない環境でも ImportError が起きないことを確認する
        with _CaptureOutput():
            result = _run(runner.run_step("9.9", "架空ステップ", "プロンプト"))
        self.assertTrue(result)

    def test_dry_run_with_auto_coding_agent_review(self) -> None:
        """dry_run=True + auto_coding_agent_review=True でも SDK 呼び出しなしで True を返す。"""
        runner = self._make_runner(auto_coding_agent_review=True)
        with _CaptureOutput():
            result = _run(runner.run_step("1.1", "テストステップ", "テストプロンプト"))
        self.assertTrue(result)

    def test_dry_run_resets_workiq_tool_called_flag(self) -> None:
        runner = self._make_runner()
        runner._workiq_tool_called = True
        with _CaptureOutput():
            result = _run(runner.run_step("1.1", "テストステップ", "テストプロンプト"))
        self.assertTrue(result)
        self.assertFalse(runner._workiq_tool_called)


class TestStepRunnerNonDryRunNoSDK(unittest.TestCase):
    """dry_run=False で SDK 未インストール時に False を返す。"""

    def test_returns_false_when_sdk_missing(self) -> None:
        cfg = SDKConfig(dry_run=False, model="claude-opus-4.7")
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        # sys.modules['copilot'] = None は Python の標準的な「存在しないモジュール」マーカーで
        # import 時に確実に ImportError を発生させる
        original = sys.modules.get("copilot", _SENTINEL)
        sys.modules["copilot"] = None  # type: ignore[assignment]
        try:
            with _CaptureOutput() as cap:
                result = _run(
                    runner.run_step("1.1", "テスト", "プロンプト")
                )
            self.assertFalse(result)
            # quiet=True でもエラーは stderr に出る
            self.assertIn("ERROR", cap.stderr)
        finally:
            if original is _SENTINEL:
                sys.modules.pop("copilot", None)
            else:
                sys.modules["copilot"] = original


class TestStepRunnerConfig(unittest.TestCase):
    """StepRunner に設定が正しく注入されることを検証する。"""

    def test_config_is_stored(self) -> None:
        cfg = SDKConfig(dry_run=True, model="gpt-5")
        console = Console()
        runner = StepRunner(config=cfg, console=console)
        self.assertIs(runner.config, cfg)

    def test_console_is_stored(self) -> None:
        cfg = SDKConfig()
        console = Console(verbose=False)
        runner = StepRunner(config=cfg, console=console)
        self.assertIs(runner.console, console)

    def test_context_injection_max_chars_default(self) -> None:
        cfg = SDKConfig()
        console = Console(verbose=False)
        runner = StepRunner(config=cfg, console=console)
        self.assertEqual(
            runner._get_context_injection_max_chars(),
            DEFAULT_CONTEXT_INJECTION_MAX_CHARS,
        )

    def test_context_injection_max_chars_invalid_runtime_value_falls_back_to_default(self) -> None:
        cfg = SDKConfig()
        cfg.context_injection_max_chars = -1
        console = Console(verbose=False)
        runner = StepRunner(config=cfg, console=console)
        self.assertEqual(
            runner._get_context_injection_max_chars(),
            DEFAULT_CONTEXT_INJECTION_MAX_CHARS,
        )


# -----------------------------------------------------------------------
# ストリームイベント処理テスト
# -----------------------------------------------------------------------


class _FakeEventType:
    """SessionEventType enum のモック。.value で文字列を返す。"""

    def __init__(self, value: str):
        self.value = value


class _FakeEventData:
    """イベントデータのモック。"""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeEvent:
    """セッションイベントのモック。"""

    def __init__(self, etype: str, data=None):
        self.type = _FakeEventType(etype)
        self.data = data


class TestStepRunnerStreamEvents(unittest.TestCase):
    """_handle_session_event のストリームイベント処理を検証する。"""

    def _make_runner(
        self,
        show_stream: bool = True,
        verbose: bool = False,
        show_reasoning: bool = True,
    ) -> StepRunner:
        cfg = SDKConfig(dry_run=True)
        console = Console(
            verbose=verbose,
            quiet=False,
            show_stream=show_stream,
            show_reasoning=show_reasoning,
        )
        runner = StepRunner(config=cfg, console=console)
        runner._current_step_id = "1.1"
        return runner

    def test_message_delta_calls_stream_token(self) -> None:
        runner = self._make_runner(show_stream=True)
        event = _FakeEvent("assistant.message_delta", _FakeEventData(delta_content="Hello"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertEqual(cap.stdout, "Hello")

    def test_message_delta_content_fallback(self) -> None:
        """data.delta_content がない場合に camelCase の deltaContent にフォールバックする。

        SDK 仕様（streaming-events.md）では assistant.message_delta は deltaContent のみ。
        Python SDK の snake_case 変換にも対応するため delta_content と deltaContent の両方を受け付ける。
        SDK 仕様に存在しない `content` フィールドへのフォールバックは削除済み。
        """
        runner = self._make_runner(show_stream=True)
        event = _FakeEvent("assistant.message_delta", _FakeEventData(deltaContent="World"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertEqual(cap.stdout, "World")

    def test_message_delta_empty_no_output(self) -> None:
        """トークンが空の場合は出力しない。"""
        runner = self._make_runner(show_stream=True)
        event = _FakeEvent("assistant.message_delta", _FakeEventData(delta_content=""))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertEqual(cap.stdout, "")

    def test_turn_end_calls_stream_end(self) -> None:
        runner = self._make_runner(show_stream=True)
        event = _FakeEvent("assistant.turn_end")
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("ストリーム終了", cap.stdout)

    def test_stream_suppressed_when_show_stream_false(self) -> None:
        """show_stream=False の場合、ストリームイベントは出力されない。"""
        runner = self._make_runner(show_stream=False)
        event = _FakeEvent("assistant.message_delta", _FakeEventData(delta_content="Hello"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertEqual(cap.stdout, "")

    def test_reasoning_delta_calls_reasoning_token(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("assistant.reasoning_delta", _FakeEventData(delta_content="検討中"))
        with unittest.mock.patch.object(runner.console, "reasoning_token") as mock_reasoning_token:
            runner._handle_session_event(event)
        mock_reasoning_token.assert_called_once_with("1.1", "検討中")

    def test_reasoning_complete_calls_reasoning_complete(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("assistant.reasoning", _FakeEventData(content="最終推論"))
        with unittest.mock.patch.object(runner.console, "reasoning_complete") as mock_reasoning_complete:
            runner._handle_session_event(event)
        mock_reasoning_complete.assert_called_once_with("1.1", "最終推論")

    def test_reasoning_delta_hidden_when_show_reasoning_false(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True, show_reasoning=False)
        event = _FakeEvent("assistant.reasoning_delta", _FakeEventData(delta_content="hidden"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertEqual(cap.stdout, "")

    def test_message_delta_still_uses_stream_token(self) -> None:
        runner = self._make_runner(show_stream=True, verbose=True)
        event = _FakeEvent("assistant.message_delta", _FakeEventData(delta_content="Hello"))
        with unittest.mock.patch.object(runner.console, "stream_token") as mock_stream_token:
            runner._handle_session_event(event)
        mock_stream_token.assert_called_once_with("1.1", "Hello")

    def test_subagent_event_still_works(self) -> None:
        """既存のイベント処理が維持されていることを確認。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("subagent.started", _FakeEventData(agent_display_name="TestAgent"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("TestAgent", cap.stdout)

    def test_tool_event_still_works(self) -> None:
        """既存の tool イベント処理が維持されていることを確認。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="grep"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("grep", cap.stdout)

    def test_workiq_tool_event_sets_called_flag(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        self.assertFalse(runner._workiq_tool_called)
        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="ask_work_iq"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("Work IQ ツール 'ask_work_iq' が呼び出されました", cap.stdout)
        self.assertTrue(runner._workiq_tool_called)

    def test_workiq_mcp_tool_event_sets_called_flag(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        self.assertFalse(runner._workiq_tool_called)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(mcp_tool_name="ask_work_iq", mcp_server_name=WORKIQ_MCP_SERVER_NAME),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("Work IQ ツール 'ask_work_iq' が呼び出されました", cap.stdout)
        self.assertTrue(runner._workiq_tool_called)
        self.assertEqual(runner._workiq_called_tools, ["ask_work_iq"])

    def test_other_mcp_server_tool_does_not_set_workiq_flag(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(mcp_tool_name="ask_work_iq", mcp_server_name="other_server"),
        )
        with _CaptureOutput():
            runner._handle_session_event(event)
        self.assertFalse(runner._workiq_tool_called)
        self.assertEqual(runner._workiq_called_tools, [])

    def test_tool_execution_complete_success(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(success=True, result_summary="12 files found"),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("12 files found", cap.stdout)

    def test_assistant_intent_calls_thinking(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("assistant.intent", _FakeEventData(intent="I'm looking into this"))
        with unittest.mock.patch.object(runner.console, "thinking") as mock_thinking:
            runner._handle_session_event(event)
        mock_thinking.assert_called_once_with("1.1", "I'm looking into this")

    def test_assistant_intent_description_fallback_calls_thinking(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "assistant.intent",
            _FakeEventData(description="I'm looking into fallback"),
        )
        with unittest.mock.patch.object(runner.console, "thinking") as mock_thinking:
            runner._handle_session_event(event)
        mock_thinking.assert_called_once_with("1.1", "I'm looking into fallback")

    def test_assistant_intent_kind_details_fallback_filters_empty(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "assistant.intent",
            _FakeEventData(
                kind="search",
                details={"query": "workiq", "empty": "", "none": None, "count": 0},
            ),
        )
        with unittest.mock.patch.object(runner.console, "thinking") as mock_thinking:
            runner._handle_session_event(event)
        mock_thinking.assert_called_once_with("1.1", "search: workiq, 0")

    def test_tool_execution_start_read_file_formats_action_name(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(tool_name="read_file", arguments={"path": "hve/workiq.py"}),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("Read workiq.py", cap.stdout)
        self.assertIn("hve/workiq.py", cap.stdout)

    def test_tool_execution_start_report_intent_calls_thinking(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(
                tool_name="report_intent",
                arguments={"intent": "I'm looking into how the hve application integrates Work IQ"},
            ),
        )
        with unittest.mock.patch.object(runner.console, "thinking") as mock_thinking, \
             unittest.mock.patch.object(runner.console, "action_start") as mock_action_start:
            runner._handle_session_event(event)
        mock_thinking.assert_called_once_with(
            "1.1",
            "I'm looking into how the hve application integrates Work IQ",
        )
        mock_action_start.assert_not_called()

    def test_tool_execution_start_report_intent_first_string_fallback(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(
                tool_name="report_intent",
                arguments={"foo": 1, "message": "", "content": "fallback intent"},
            ),
        )
        with unittest.mock.patch.object(runner.console, "thinking") as mock_thinking:
            runner._handle_session_event(event)
        mock_thinking.assert_called_once_with("1.1", "fallback intent")

    def test_tool_execution_start_task_hidden_when_not_verbose3(self) -> None:
        cfg = SDKConfig(dry_run=True)
        console = Console(verbosity=1, quiet=False, show_stream=False)
        runner = StepRunner(config=cfg, console=console)
        runner._current_step_id = "1.1"
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(tool_name="task", arguments={"description": "internal"}),
        )
        with unittest.mock.patch.object(runner.console, "event") as mock_event, \
             unittest.mock.patch.object(runner.console, "action_start") as mock_action_start:
            runner._handle_session_event(event)
        mock_event.assert_not_called()
        mock_action_start.assert_not_called()

    def test_tool_execution_start_task_shown_when_verbose3(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(tool_name="task", arguments={"description": "internal"}),
        )
        with unittest.mock.patch.object(runner.console, "event") as mock_event, \
             unittest.mock.patch.object(runner.console, "action_start") as mock_action_start:
            runner._handle_session_event(event)
        mock_event.assert_called_once()
        self.assertIn("task (internal)", mock_event.call_args.args[0])
        mock_action_start.assert_not_called()

    def test_tool_execution_start_fallback_detail_uses_intent_key(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(
                tool_name="unknown_tool",
                arguments={"intent": "searching for integration points"},
            ),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("searching for integration points", cap.stdout)

    def test_tool_execution_start_grep_detail_is_truncated(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        long_pattern = "x" * 200
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(tool_name="grep", arguments={"pattern": long_pattern, "path": "hve"}),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("...", cap.stdout)

    def test_tool_execution_start_shell_detail_is_truncated(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        long_command = "echo " + ("a" * 220)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(tool_name="bash", arguments={"command": long_command}),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("...", cap.stdout)

    def test_session_error_shown(self) -> None:
        """session.error は常に表示される。"""
        runner = self._make_runner(show_stream=False, verbose=False)
        event = _FakeEvent("session.error", _FakeEventData(error_type="rate_limit", message="Too many requests"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("rate_limit", cap.stdout)

    def test_unknown_event_verbose_only(self) -> None:
        """未知のイベントタイプは verbose 時のみ出力される。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("some.future.event", _FakeEventData())
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("some.future.event", cap.stdout)

    def test_session_idle_silent(self) -> None:
        """session.idle は出力しない。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("session.idle")
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertEqual(cap.stdout, "")
        self.assertEqual(cap.stderr, "")


class TestIsReviewFail(unittest.TestCase):
    """_is_review_fail() の境界テスト。"""

    def test_fail_on_verdict_line(self) -> None:
        """合格判定行に ❌ FAIL が含まれる場合 True を返す。"""
        content = "- 合格判定: ❌ FAIL（Critical > 0）"
        self.assertTrue(_is_review_fail(content))

    def test_pass_on_verdict_line(self) -> None:
        """合格判定行に ✅ PASS が含まれる場合 False を返す。"""
        content = "- 合格判定: ✅ PASS（Critical = 0）"
        self.assertFalse(_is_review_fail(content))

    def test_fail_case_insensitive(self) -> None:
        """FAIL の大文字小文字を問わず検出する。"""
        self.assertTrue(_is_review_fail("- 合格判定: Fail"))
        self.assertTrue(_is_review_fail("- 合格判定: fail"))
        self.assertTrue(_is_review_fail("- 合格判定: fAiL"))

    def test_fail_in_body_not_verdict(self) -> None:
        """合格判定行以外に fail が含まれていても、合格判定行が PASS なら False を返す。"""
        content = "This test may fail under load.\n- 合格判定: ✅ PASS"
        self.assertFalse(_is_review_fail(content))

    def test_fail_in_both_body_and_verdict(self) -> None:
        """本文と合格判定行の両方に fail が含まれる場合は True を返す。"""
        content = "This test may fail under load.\n- 合格判定: ❌ FAIL（Critical > 0）"
        self.assertTrue(_is_review_fail(content))

    def test_empty_content(self) -> None:
        """空文字列では FAIL 扱い（合格判定行がないため安全側に倒す）。"""
        self.assertTrue(_is_review_fail(""))

    def test_no_verdict_line(self) -> None:
        """合格判定行がない場合 FAIL 扱い（フォーマット不備として安全側に倒す）。"""
        content = "レビュー結果:\n- Critical: 0件\n- Major: 1件"
        self.assertTrue(_is_review_fail(content))

    def test_multiline_with_fail(self) -> None:
        """複数行のうち合格判定行に FAIL が含まれる場合 True を返す。"""
        content = (
            "| 1 | 要件充足性 | Critical | ... | ... | ... |\n"
            "### サマリー\n"
            "- Critical: 2件\n"
            "- Major: 1件\n"
            "- Minor: 3件\n"
            "- 合格判定: ❌ FAIL（Critical > 0）"
        )
        self.assertTrue(_is_review_fail(content))

    def test_pass_emoji_token(self) -> None:
        """✅ PASS トークンがあれば PASS 判定。"""
        content = "- 合格判定: ✅ PASS"
        self.assertFalse(_is_review_fail(content))

    def test_fail_emoji_token(self) -> None:
        """❌ FAIL トークンがあれば FAIL 判定。"""
        content = "- 合格判定: ❌ FAIL"
        self.assertTrue(_is_review_fail(content))


class TestTruncateContext(unittest.TestCase):
    """_truncate_context() のテスト。"""

    def test_returns_original_when_short(self) -> None:
        text = "abc"
        self.assertEqual(_truncate_context(text, 10), text)

    def test_truncates_with_head_and_tail(self) -> None:
        text = "A" * 100 + "B" * 100
        result = _truncate_context(text, 120)
        self.assertIn("... (中略: 全体 200 文字) ...", result)
        self.assertTrue(result.startswith("A"))
        self.assertTrue(result.endswith("B"))
        self.assertLessEqual(len(result), 120)


class TestQaArtifactFallbackHelpers(unittest.TestCase):
    """QA 応答が artifacts 参照だけの場合の補助関数テスト。"""

    _HELPER_QA_CONTENT = (
        "[Q01]\n"
        "- 問題種別: 不明瞭\n"
        "- 重大度: major\n"
        "- 質問内容: 代表SKUの定義はどれですか。\n"
        "- 未回答時の既定値候補: TBD\n"
        "- 既定値候補の理由: 根拠不足\n"
        "- 未回答のまま進めた場合の影響: 設計判断が分岐する\n"
    )

    def test_extract_safe_qa_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            qa_dir = base / "qa"
            qa_dir.mkdir()
            target = qa_dir / "QA-DocConsistency-20260101-120000.md"
            target.write_text(self._HELPER_QA_CONTENT, encoding="utf-8")

            content = "## 成果物サマリー\n- artifacts: qa/QA-DocConsistency-20260101-120000.md\n"
            paths = _extract_safe_qa_artifact_paths(content, base_dir=base)

            self.assertEqual(paths, [target])

    def test_extract_safe_qa_artifact_paths_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            qa_dir = base / "qa"
            qa_dir.mkdir()
            (qa_dir / "ok.md").write_text(self._HELPER_QA_CONTENT, encoding="utf-8")

            content = "artifacts: qa/../secret.md qa/ok.md C:/tmp/qa/bad.md"
            paths = _extract_safe_qa_artifact_paths(content, base_dir=base)

            self.assertEqual(paths, [qa_dir / "ok.md"])

    def test_parse_qa_content_with_artifact_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            qa_dir = base / "qa"
            qa_dir.mkdir()
            target = qa_dir / "QA-DocConsistency-20260101-120000.md"
            target.write_text(self._HELPER_QA_CONTENT, encoding="utf-8")

            content = "## 成果物サマリー\n- artifacts: qa/QA-DocConsistency-20260101-120000.md\n"
            doc, fallback_path = _parse_qa_content_with_artifact_fallback(content, base_dir=base)

            self.assertEqual(fallback_path, target)
            self.assertEqual(len(doc.questions), 1)
            self.assertIn("代表SKU", doc.questions[0].question)
            self.assertEqual(doc.questions[0].category, "不明瞭")
            self.assertEqual(doc.questions[0].priority, "major")


class TestStepRunnerModelSwitchDryRun(unittest.TestCase):
    """レビュー/QA モデル切替判定のドライラン系テスト。"""

    def test_review_model_different_from_model(self) -> None:
        cfg = SDKConfig(model="gpt-5.4", review_model="claude-opus-4.6")
        self.assertNotEqual(cfg.get_review_model(), cfg.model)

    def test_review_model_same_as_model(self) -> None:
        cfg = SDKConfig(model="gpt-5.4", review_model="gpt-5.4")
        self.assertEqual(cfg.get_review_model(), cfg.model)

    def test_qa_model_different_from_model(self) -> None:
        cfg = SDKConfig(model="gpt-5.4", qa_model="claude-opus-4.6")
        self.assertNotEqual(cfg.get_qa_model(), cfg.model)

    def test_build_sub_session_opts_exists(self) -> None:
        cfg = SDKConfig(dry_run=True, model="gpt-5.4")
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        self.assertTrue(hasattr(runner, "_build_sub_session_opts"))


class TestTrackToolFiles(unittest.TestCase):
    """_track_tool_files / _track_bash_files のテスト。"""

    def _make_runner(self, **kwargs: Any) -> StepRunner:
        config = SDKConfig(**kwargs) if kwargs else SDKConfig()
        console = Console(verbose=True, quiet=False)
        runner = StepRunner(config=config, console=console)
        return runner

    def test_edit_file_tracked_as_read_and_write(self) -> None:
        runner = self._make_runner()
        runner._track_tool_files("1", "edit_file", {"path": "src/main.py"})
        files = runner.console._step_files.get("1", {})
        self.assertIn(os.path.normpath("src/main.py"), files.get("read", []))
        self.assertIn(os.path.normpath("src/main.py"), files.get("write", []))

    def test_bash_redirect_tracked_as_write(self) -> None:
        import os
        runner = self._make_runner()
        runner._track_bash_files("1", "echo hello > output/result.txt")
        files = runner.console._step_files.get("1", {})
        self.assertIn(os.path.normpath("output/result.txt"), files.get("write", []))

    def test_bash_redirect_no_space_and_fd_tracked_as_write(self) -> None:
        import os
        runner = self._make_runner()
        runner._track_bash_files("1", "echo hi>out.txt; echo ng 2>err.log; tee -a tee.log")
        files = runner.console._step_files.get("1", {})
        self.assertIn(os.path.normpath("out.txt"), files.get("write", []))
        self.assertIn(os.path.normpath("err.log"), files.get("write", []))
        self.assertIn(os.path.normpath("tee.log"), files.get("write", []))

    def test_skip_tools_not_tracked(self) -> None:
        runner = self._make_runner()
        runner._track_tool_files("1", "grep", {"pattern": "TODO", "path": "src/"})
        files = runner.console._step_files.get("1", {})
        self.assertEqual(len(files.get("read", [])), 0)
        self.assertEqual(len(files.get("write", [])), 0)

    def test_rg_is_skipped(self) -> None:
        runner = self._make_runner()
        runner._track_tool_files("1", "rg", {"pattern": "TODO", "path": "src/"})
        files = runner.console._step_files.get("1", {})
        self.assertEqual(len(files.get("read", [])), 0)
        self.assertEqual(len(files.get("write", [])), 0)

    def test_powershell_dispatches_to_powershell(self) -> None:
        runner = self._make_runner()
        with unittest.mock.patch.object(runner, "_track_bash_files") as mock_bash, \
                unittest.mock.patch.object(runner, "_track_powershell_files") as mock_ps:
            runner._track_tool_files("1", "powershell", {"command": "Get-ChildItem -Path docs"})
        mock_ps.assert_called_once_with("1", "Get-ChildItem -Path docs")
        mock_bash.assert_not_called()


class TestWorkIQToolNamesConsistency(unittest.TestCase):
    """Phase 1: runner.py の _WORKIQ_TOOL_NAMES が workiq.py の定数と一致することを確認。"""

    def test_workiq_tool_names_matches_workiq_module(self) -> None:
        import workiq as _workiq_mod
        from runner import _WORKIQ_TOOL_NAMES
        self.assertEqual(_WORKIQ_TOOL_NAMES, frozenset(_workiq_mod.WORKIQ_MCP_TOOL_NAMES))

    def test_workiq_tool_names_contains_expected_tools(self) -> None:
        from runner import _WORKIQ_TOOL_NAMES
        expected = {"ask_work_iq"}
        self.assertEqual(_WORKIQ_TOOL_NAMES, frozenset(expected))

    def test_tool_execution_start_ask_work_iq_detected(self) -> None:
        """tool.execution_start イベントで ask_work_iq が Work IQ ツールとして検出されること。"""
        cfg = SDKConfig(dry_run=True, workiq_enabled=True)
        console = Console(verbose=False, quiet=True)
        step_runner = StepRunner(config=cfg, console=console)

        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="ask_work_iq"))
        step_runner._handle_session_event(event)
        self.assertTrue(step_runner._workiq_tool_called)

    def test_old_search_tool_name_not_detected(self) -> None:
        """旧 Work IQ tool 名は現行 MCP tool として扱わないこと。"""
        cfg = SDKConfig(dry_run=True, workiq_enabled=True)
        console = Console(verbose=False, quiet=True)
        step_runner = StepRunner(config=cfg, console=console)

        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="search_emails"))
        step_runner._handle_session_event(event)
        self.assertFalse(step_runner._workiq_tool_called)

    def test_tool_execution_start_non_workiq_not_detected(self) -> None:
        """Work IQ 以外のツールでは _workiq_tool_called が True にならないこと。"""
        cfg = SDKConfig(dry_run=True, workiq_enabled=True)
        console = Console(verbose=False, quiet=True)
        step_runner = StepRunner(config=cfg, console=console)

        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="edit_file"))
        step_runner._handle_session_event(event)
        self.assertFalse(step_runner._workiq_tool_called)


class TestWorkIQCustomAgentToolsWarning(unittest.TestCase):
    """Work IQ は QA フェーズ専用のため custom agent tools 制限警告を出さない。"""

    def _make_runner(self, **cfg_kwargs) -> StepRunner:
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.7", **cfg_kwargs)
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    def test_restricted_tools_no_warning_when_workiq_enabled(self) -> None:
        """Work IQ 有効 + restricted tools でも Phase 1 では警告しない。"""
        restricted_agent = {
            "name": "MyAgent",
            "tools": ["edit_file", "write_file"],
            "prompt": "agent prompt",
        }
        cfg = SDKConfig(
            dry_run=True, model="claude-opus-4.7",
            workiq_enabled=True,
            custom_agents_config=[restricted_agent],
        )
        console = Console(verbose=False, quiet=False)
        step_runner = StepRunner(config=cfg, console=console)

        with _CaptureOutput() as cap:
            _run(step_runner.run_step("1.1", "test", "prompt", custom_agent="MyAgent"))

        combined = cap.stdout + cap.stderr
        self.assertNotIn("Work IQ is enabled", combined)
        self.assertNotIn("restricted tools", combined)

    def test_wildcard_tools_no_warning(self) -> None:
        """tools=['*'] の場合は警告が出ないこと。"""
        wildcard_agent = {
            "name": "MyAgent",
            "tools": ["*"],
            "prompt": "agent prompt",
        }
        cfg = SDKConfig(
            dry_run=True, model="claude-opus-4.7",
            workiq_enabled=True,
            custom_agents_config=[wildcard_agent],
        )
        console = Console(verbose=False, quiet=False)
        step_runner = StepRunner(config=cfg, console=console)

        with _CaptureOutput() as cap:
            _run(step_runner.run_step("1.1", "test", "prompt", custom_agent="MyAgent"))

        combined = cap.stdout + cap.stderr
        self.assertNotIn("restricted tools", combined)

    def test_workiq_tool_in_tools_no_warning(self) -> None:
        """tools に Work IQ ツールが含まれる場合は警告が出ないこと。"""
        agent_with_workiq = {
            "name": "MyAgent",
            "tools": ["ask_work_iq", "edit_file"],
            "prompt": "agent prompt",
        }
        cfg = SDKConfig(
            dry_run=True, model="claude-opus-4.7",
            workiq_enabled=True,
            custom_agents_config=[agent_with_workiq],
        )
        console = Console(verbose=False, quiet=False)
        step_runner = StepRunner(config=cfg, console=console)

        with _CaptureOutput() as cap:
            _run(step_runner.run_step("1.1", "test", "prompt", custom_agent="MyAgent"))

        combined = cap.stdout + cap.stderr
        self.assertNotIn("restricted tools", combined)


# ---------------------------------------------------------------------------
# Phase 2: SDK セッション ID 安定化（Resume の前提条件）
# ---------------------------------------------------------------------------

class TestSessionIdPropagation(unittest.TestCase):
    """`StepRunner.run_step()` 内の `client.create_session()` 呼び出しが
    決定論的な `session_id` を kwargs に含めることを検証する。

    Phase 2 (Resume) の中核要件: 同じ run_id × step_id × suffix の組み合わせで
    常に同じ session_id が SDK に渡されること。
    """

    def _build_fake_sdk(self):
        """create_session の kwargs を全て記録する Fake SDK モジュールを構築する。"""
        import types

        class _FakeSession:
            async def send_and_wait(self, *args, **kwargs):
                # メインタスク 1 回のみ応答する最小モック
                return None

            async def disconnect(self):
                return None

            def on(self, handler):
                return None

        class _FakeClient:
            def __init__(self) -> None:
                self.create_session_kwargs: list = []

            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                self.create_session_kwargs.append(kwargs)
                return _FakeSession()

        fake_client = _FakeClient()
        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda config=None: fake_client
        fake_copilot.SubprocessConfig = lambda **kwargs: object()
        fake_copilot.ExternalServerConfig = lambda **kwargs: object()

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler
        return fake_client, fake_copilot, fake_copilot_session

    def test_main_session_receives_deterministic_session_id(self) -> None:
        """メインセッションに run_id + step_id 由来の決定論的 session_id が渡される。"""
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="20260507T100000-test01",
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ):
            result = asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertTrue(result)
        self.assertEqual(len(fake_client.create_session_kwargs), 1)
        kw = fake_client.create_session_kwargs[0]
        self.assertIn("session_id", kw)
        # フォーマット: "hve-{run_id}-step-{step_id}"
        self.assertEqual(kw["session_id"], "hve-20260507T100000-test01-step-1.1")

    def test_session_id_is_deterministic_across_runs(self) -> None:
        """同じ run_id + step_id で複数回 run_step() を呼ぶと常に同じ session_id が渡される。"""
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="run-determ-001",
        )
        console = Console(verbose=False, quiet=True)

        captured_ids: list = []
        for _ in range(2):
            runner = StepRunner(config=cfg, console=console)
            fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()
            with unittest.mock.patch.dict(
                sys.modules,
                {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
            ):
                asyncio.run(runner.run_step("2.3", "テスト", "プロンプト"))
            captured_ids.append(fake_client.create_session_kwargs[0]["session_id"])

        self.assertEqual(captured_ids[0], captured_ids[1])

    def test_session_id_uses_custom_prefix(self) -> None:
        """SDKConfig.session_id_prefix が設定されている場合はその prefix が使われる。"""
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="run-prefix-001",
            session_id_prefix="myapp",
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()
        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ):
            asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertTrue(
            fake_client.create_session_kwargs[0]["session_id"].startswith("myapp-")
        )

    def test_make_step_session_id_helper(self) -> None:
        """`StepRunner._make_step_session_id` が make_session_id と同じ仕様を返す。"""
        cfg = SDKConfig(model="claude-opus-4.7", run_id="run-helper-001")
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        main = runner._make_step_session_id("1.1")
        qa = runner._make_step_session_id("1.1", suffix="qa")
        review = runner._make_step_session_id("1.1", suffix="review")

        self.assertEqual(main, "hve-run-helper-001-step-1.1")
        self.assertEqual(qa, "hve-run-helper-001-step-1.1-qa")
        self.assertEqual(review, "hve-run-helper-001-step-1.1-review")
        # サブセッション ID は全て異なる
        self.assertEqual(len({main, qa, review}), 3)

    def test_qa_subsession_session_id_has_qa_suffix(self) -> None:
        """`_build_sub_session_opts(step_id=..., suffix='qa')` が qa サフィックス付き ID を返す。"""
        cfg = SDKConfig(
            model="claude-opus-4.7",
            run_id="run-qa-suffix-001",
            qa_model="claude-opus-4.6",  # メインモデルと別モデルでサブセッション化
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        # PermissionHandler のために fake_copilot_session を一時注入
        import types
        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler

        with unittest.mock.patch.dict(
            sys.modules, {"copilot.session": fake_copilot_session}
        ):
            opts_qa = runner._build_sub_session_opts(
                "claude-opus-4.6", step_id="1.1", suffix="qa"
            )
            opts_review = runner._build_sub_session_opts(
                "claude-opus-4.6", step_id="1.1", suffix="review"
            )

        self.assertEqual(opts_qa.get("session_id"), "hve-run-qa-suffix-001-step-1.1-qa")
        self.assertEqual(opts_review.get("session_id"), "hve-run-qa-suffix-001-step-1.1-review")
        # 明示モデル指定時は reasoning_effort を付与しない契約を二重保証
        self.assertNotIn("reasoning_effort", opts_qa)
        self.assertNotIn("reasoning_effort", opts_review)

    def test_sub_session_opts_without_step_id_omits_session_id(self) -> None:
        """step_id を渡さない場合は session_id を含めない（後方互換）。"""
        cfg = SDKConfig(model="claude-opus-4.7", run_id="run-back-compat")
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        import types
        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler

        with unittest.mock.patch.dict(
            sys.modules, {"copilot.session": fake_copilot_session}
        ):
            opts = runner._build_sub_session_opts("claude-opus-4.6")

        self.assertNotIn("session_id", opts)


class TestSubSessionOptsReasoningEffort(unittest.TestCase):
    """Auto モデル時の reasoning_effort 付与契約を固定する。"""

    def _make_runner_with_fake_permission(self) -> StepRunner:
        cfg = SDKConfig(model="claude-opus-4.7", run_id="run-reasoning-effort")
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    @staticmethod
    def _patched_modules():
        import types

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler
        return {"copilot.session": fake_copilot_session}

    def test_auto_model_adds_reasoning_effort_high(self) -> None:
        from config import MODEL_AUTO_VALUE

        runner = self._make_runner_with_fake_permission()
        with unittest.mock.patch.dict(sys.modules, self._patched_modules()):
            opts = runner._build_sub_session_opts(MODEL_AUTO_VALUE)
        self.assertNotIn("model", opts)
        self.assertEqual(opts.get("reasoning_effort"), "high")

    def test_explicit_model_omits_reasoning_effort(self) -> None:
        runner = self._make_runner_with_fake_permission()
        with unittest.mock.patch.dict(sys.modules, self._patched_modules()):
            opts = runner._build_sub_session_opts("claude-opus-4.7")
        self.assertEqual(opts.get("model"), "claude-opus-4.7")
        self.assertNotIn("reasoning_effort", opts)

    def test_empty_string_treated_as_auto(self) -> None:
        runner = self._make_runner_with_fake_permission()
        with unittest.mock.patch.dict(sys.modules, self._patched_modules()):
            opts = runner._build_sub_session_opts("")
        self.assertNotIn("model", opts)
        self.assertEqual(opts.get("reasoning_effort"), "high")


class TestCreateSessionAutoReasoningFallback(unittest.IsolatedAsyncioTestCase):
    """_create_session_with_auto_reasoning_fallback の TypeError 時挙動を検証する。"""

    async def test_strips_reasoning_effort_on_typeerror(self) -> None:
        from runner import _create_session_with_auto_reasoning_fallback

        calls: list[dict] = []

        class _FakeClient:
            async def create_session(self, **kwargs):
                calls.append(kwargs)
                if "reasoning_effort" in kwargs:
                    raise TypeError(
                        "create_session() got an unexpected keyword argument 'reasoning_effort'"
                    )
                return "ok-session"

        result = await _create_session_with_auto_reasoning_fallback(
            _FakeClient(), {"model": "Auto", "reasoning_effort": "high", "streaming": True}
        )
        self.assertEqual(result, "ok-session")
        self.assertEqual(len(calls), 2)
        self.assertIn("reasoning_effort", calls[0])
        self.assertNotIn("reasoning_effort", calls[1])

    async def test_passthrough_for_unrelated_typeerror(self) -> None:
        from runner import _create_session_with_auto_reasoning_fallback

        class _FakeClient:
            async def create_session(self, **kwargs):
                raise TypeError("create_session() got an unexpected keyword argument 'foobar'")

        with self.assertRaises(TypeError):
            await _create_session_with_auto_reasoning_fallback(
                _FakeClient(), {"reasoning_effort": "high"}
            )

    async def test_passthrough_for_value_validation_typeerror(self) -> None:
        """SDK 側で reasoning_effort の値検証エラー（unexpected keyword 由来でない）の場合は剥がさず raise。"""
        from runner import _create_session_with_auto_reasoning_fallback

        class _FakeClient:
            async def create_session(self, **kwargs):
                raise TypeError("reasoning_effort must be one of low/medium/high/xhigh")

        with self.assertRaises(TypeError):
            await _create_session_with_auto_reasoning_fallback(
                _FakeClient(), {"reasoning_effort": "high"}
            )


class TestWorkIQCalledToolsTracking(unittest.TestCase):
    """Phase 2: _workiq_called_tools 履歴が _handle_session_event で蓄積されることを確認。"""

    def _make_runner(self) -> StepRunner:
        cfg = SDKConfig(dry_run=True, workiq_enabled=True)
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)
        runner._current_step_id = "1"
        return runner

    def test_workiq_tool_appended_to_called_tools(self) -> None:
        """Work IQ ツール呼び出しで _workiq_called_tools にツール名が追加される。"""
        runner = self._make_runner()
        self.assertEqual(runner._workiq_called_tools, [])
        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="ask_work_iq"))
        runner._handle_session_event(event)
        self.assertEqual(runner._workiq_called_tools, ["ask_work_iq"])

    def test_mcp_workiq_tool_appended_to_called_tools(self) -> None:
        """mcp_tool_name 形式でも _workiq_called_tools にツール名が追加される。"""
        runner = self._make_runner()
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(mcp_tool_name="ask_work_iq", mcp_server_name=WORKIQ_MCP_SERVER_NAME),
        )
        runner._handle_session_event(event)
        self.assertEqual(runner._workiq_called_tools, ["ask_work_iq"])

    def test_workiq_tool_multiple_calls_all_appended(self) -> None:
        """複数回呼び出した場合、すべて _workiq_called_tools に追記される。"""
        runner = self._make_runner()
        for tool in ["ask_work_iq", "ask_work_iq"]:
            event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name=tool))
            runner._handle_session_event(event)
        self.assertEqual(runner._workiq_called_tools, ["ask_work_iq", "ask_work_iq"])

    def test_non_workiq_tool_not_appended(self) -> None:
        """Work IQ 以外のツールは _workiq_called_tools に追加されない。"""
        runner = self._make_runner()
        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="edit_file"))
        runner._handle_session_event(event)
        self.assertEqual(runner._workiq_called_tools, [])

    def test_workiq_called_tools_reset_on_run_step(self) -> None:
        """run_step() 開始時に _workiq_called_tools がリセットされる。"""
        runner = self._make_runner()
        runner._workiq_called_tools = ["ask_work_iq"]
        with _CaptureOutput():
            _run(runner.run_step("1", "テスト", "プロンプト"))
        # dry_run では run_step() 終了後に _workiq_called_tools が [] にリセットされている
        self.assertEqual(runner._workiq_called_tools, [])

    def test_diff_based_tool_detection(self) -> None:
        """呼び出し前後の差分でツール呼び出しを検出できる。"""
        runner = self._make_runner()
        runner._workiq_called_tools = ["ask_work_iq"]  # 事前に1件追加
        before = len(runner._workiq_called_tools)
        # 新たに ask_work_iq が呼ばれた
        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="ask_work_iq"))
        runner._handle_session_event(event)
        after_tools = runner._workiq_called_tools[before:]
        self.assertTrue(bool(after_tools))
        self.assertEqual(after_tools, ["ask_work_iq"])


class TestIsWorkIQToolNameHelperInRunner(unittest.TestCase):
    """runner.py が workiq.is_workiq_tool_name() ヘルパー経由で Work IQ ツールを検出すること。"""

    def _make_runner(self) -> StepRunner:
        cfg = SDKConfig(dry_run=True, workiq_enabled=True)
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    def test_is_workiq_tool_name_helper_accessible(self) -> None:
        """runner.py が workiq.is_workiq_tool_name をインポートできること。"""
        from workiq import is_workiq_tool_name
        self.assertTrue(is_workiq_tool_name("ask_work_iq"))
        self.assertFalse(is_workiq_tool_name("edit_file"))

    def test_handle_session_event_uses_is_workiq_tool_name(self) -> None:
        """_handle_session_event が is_workiq_tool_name() 経由で判定し、
        Work IQ ツールは _workiq_called_tools に追加されること。"""
        runner = self._make_runner()
        for tool in ("ask_work_iq",):
            runner._workiq_called_tools = []
            event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name=tool))
            runner._handle_session_event(event)
            self.assertIn(tool, runner._workiq_called_tools, f"{tool} は _workiq_called_tools に追加されるべき")

    def test_phase1_tool_count_does_not_affect_qa_diff_detection(self) -> None:
        """Phase 1 で Work IQ が呼ばれていても QA の差分検出に影響しないこと。

        QA フェーズでは _before_count を snapshot して差分を取るため、
        Phase 1 の _workiq_called_tools は影響しない。
        """
        runner = self._make_runner()
        # Phase 1: ask_work_iq が2回呼ばれた
        for _ in range(2):
            event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="ask_work_iq"))
            runner._handle_session_event(event)
        self.assertEqual(len(runner._workiq_called_tools), 2)

        # QA フェーズ開始前の snapshot
        before_qa = len(runner._workiq_called_tools)

        # QA フェーズ: ask_work_iq が呼ばれた
        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="ask_work_iq"))
        runner._handle_session_event(event)

        after_qa_tools = runner._workiq_called_tools[before_qa:]
        self.assertEqual(after_qa_tools, ["ask_work_iq"], "QA フェーズの差分は Phase 1 の呼び出しを含まないこと")

    def test_qa_tool_not_called_when_no_events_after_snapshot(self) -> None:
        """QA フェーズで Work IQ ツールが呼ばれなかった場合、差分は空になること。"""
        runner = self._make_runner()
        # Phase 1: ask_work_iq が呼ばれた
        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="ask_work_iq"))
        runner._handle_session_event(event)

        # QA フェーズ開始前の snapshot
        before_qa = len(runner._workiq_called_tools)

        # QA フェーズ: ツールは呼ばれなかった
        after_qa_tools = runner._workiq_called_tools[before_qa:]
        self.assertEqual(after_qa_tools, [], "QA ツール未呼び出しの場合、差分は空であること")
        self.assertFalse(bool(after_qa_tools), "ツール未観測を正しく検出できること")


# ---------------------------------------------------------------------------
# _apply_main_artifact_improvements テスト
# ---------------------------------------------------------------------------

class TestApplyMainArtifactImprovements(unittest.TestCase):
    """StepRunner._apply_main_artifact_improvements の動作を検証する。"""

    def _make_runner(self, **cfg_kwargs) -> StepRunner:
        cfg = SDKConfig(dry_run=False, model="claude-opus-4.7", **cfg_kwargs)
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    def test_method_exists(self) -> None:
        """_apply_main_artifact_improvements メソッドが StepRunner に存在する。"""
        runner = self._make_runner()
        self.assertTrue(
            callable(getattr(runner, "_apply_main_artifact_improvements", None)),
            "StepRunner に _apply_main_artifact_improvements が存在すること",
        )

    def test_returns_empty_when_context_empty(self) -> None:
        """improvement_context が空の場合は何もせず空文字を返す。"""
        runner = self._make_runner()
        mock_session = unittest.mock.AsyncMock()

        result = asyncio.run(runner._apply_main_artifact_improvements(
            session=mock_session,
            step_id="1.1",
            title="テスト",
            workflow_id=None,
            custom_agent=None,
            original_prompt="prompt",
            main_output="output",
            source_phase="Phase 3",
            improvement_context="",
            timeout=10.0,
        ))
        mock_session.send_and_wait.assert_not_awaited()
        self.assertEqual(result, "")

    def test_returns_empty_when_context_whitespace_only(self) -> None:
        """improvement_context が空白のみの場合も何もしない。"""
        runner = self._make_runner()
        mock_session = unittest.mock.AsyncMock()

        result = asyncio.run(runner._apply_main_artifact_improvements(
            session=mock_session,
            step_id="1.1",
            title="テスト",
            workflow_id=None,
            custom_agent=None,
            original_prompt="prompt",
            main_output="output",
            source_phase="Phase 3",
            improvement_context="   \n  ",
            timeout=10.0,
        ))
        mock_session.send_and_wait.assert_not_awaited()
        self.assertEqual(result, "")

    def test_sends_to_main_session(self) -> None:
        """send_and_wait をメインセッションに対して呼び出す。"""
        runner = self._make_runner()
        mock_response = unittest.mock.MagicMock()
        mock_response.data = unittest.mock.MagicMock()
        mock_response.data.content = "改善完了"
        mock_session = unittest.mock.AsyncMock()
        mock_session.send_and_wait.return_value = mock_response

        result = asyncio.run(runner._apply_main_artifact_improvements(
            session=mock_session,
            step_id="1.1",
            title="テスト",
            workflow_id="aqod",
            custom_agent="TestAgent",
            original_prompt="original",
            main_output="main output",
            source_phase="Phase 3 Adversarial Review",
            improvement_context="Critical issue found",
            timeout=30.0,
        ))
        mock_session.send_and_wait.assert_awaited_once()
        self.assertEqual(result, "改善完了")

    def test_returns_empty_on_exception(self) -> None:
        """例外が発生した場合は警告を出して空文字を返す（後続処理を継続）。"""
        runner = self._make_runner()
        mock_session = unittest.mock.AsyncMock()
        mock_session.send_and_wait.side_effect = RuntimeError("session error")

        result = asyncio.run(runner._apply_main_artifact_improvements(
            session=mock_session,
            step_id="1.1",
            title="テスト",
            workflow_id=None,
            custom_agent=None,
            original_prompt="prompt",
            main_output="output",
            source_phase="Phase 4",
            improvement_context="plan content",
            timeout=10.0,
        ))
        self.assertEqual(result, "")


class TestApplyMainArtifactImprovementsInspection(unittest.TestCase):
    """Phase 3 / 4 の共通ヘルパー呼び出し確認（ソースインスペクション）。
    Phase 2c (post-QA) は廃止済みのため該当テストは削除された。"""

    def test_phase3_calls_helper_when_fail(self) -> None:
        """Phase 3: review FAIL 時に _apply_main_artifact_improvements が呼ばれる。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("apply_review_improvements_to_main", source)
        self.assertIn("Phase 3 Adversarial Review", source)

    def test_phase4_calls_helper_when_enabled(self) -> None:
        """Phase 4: apply_self_improve_to_main=True のとき _apply_main_artifact_improvements が呼ばれる。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("apply_self_improve_to_main", source)
        self.assertIn("Phase 4 Self-Improve iteration", source)

    def test_phase3_and_4_are_workflow_independent(self) -> None:
        """Phase 3 / Phase 4 の _apply_main_artifact_improvements 呼び出しに workflow_id 条件分岐がないこと。

        これは全オーケストレーター共通処理として実装されていることを確認する。
        """
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        # Phase 3 の apply 呼び出し部分に workflow_id による条件分岐がないことを確認
        # (workflow_id を引数として渡すのは OK, if workflow_id == "xxx" で skip するのは NG)
        # 簡略化: ソース中に "if workflow_id" の後に "apply_review" が出てこないことを確認
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if "apply_review_improvements_to_main" in line or "apply_self_improve_to_main" in line:
                # 直前の数行に workflow_id == で始まる条件がないことを確認
                context = "\n".join(lines[max(0, i - 3):i])
                self.assertNotIn('workflow_id == "', context,
                                 f"Phase 3/4 should not be gated by workflow_id check near line {i}")


# ---------------------------------------------------------------------------
# _check_diff_after_improvement テスト
# ---------------------------------------------------------------------------

class TestCheckDiffAfterImprovement(unittest.TestCase):
    """StepRunner._check_diff_after_improvement の動作を検証する。"""

    def _make_runner(self) -> StepRunner:
        cfg = SDKConfig(dry_run=True)
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    def test_returns_changed_files_on_diff(self) -> None:
        """git diff に差分がある場合、変更ファイルリストを返すこと。"""
        runner = self._make_runner()
        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "hve/runner.py\nhve/config.py\n"
        with unittest.mock.patch("subprocess.run", return_value=mock_result):
            changed = runner._check_diff_after_improvement("step-1", "Phase 3 Adversarial Review")
        self.assertEqual(changed, ["hve/runner.py", "hve/config.py"])

    def test_returns_empty_and_logs_warning_when_no_diff(self) -> None:
        """git diff に差分がない場合、空リストを返し warning が記録されること。"""
        runner = self._make_runner()
        warnings: list[str] = []
        original_warning = runner.console.warning
        runner.console.warning = lambda msg: warnings.append(msg)  # type: ignore[method-assign]
        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with unittest.mock.patch("subprocess.run", return_value=mock_result):
            changed = runner._check_diff_after_improvement("step-1", "Phase 3 Adversarial Review")
        runner.console.warning = original_warning
        self.assertEqual(changed, [])
        self.assertTrue(len(warnings) > 0, "差分なし時に warning が発行されること")
        self.assertIn("差分がありません", warnings[0])

    def test_returns_empty_when_git_fails(self) -> None:
        """git diff が非ゼロ終了した場合、空リストを返し warning が記録されること。"""
        runner = self._make_runner()
        warnings: list[str] = []
        runner.console.warning = lambda msg: warnings.append(msg)  # type: ignore[method-assign]
        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        mock_result.stderr = "not a git repository"
        with unittest.mock.patch("subprocess.run", return_value=mock_result):
            changed = runner._check_diff_after_improvement("step-1", "Phase 3 Adversarial Review")
        self.assertEqual(changed, [])
        self.assertTrue(len(warnings) > 0, "git 失敗時に warning が発行されること")
        self.assertIn("git diff", warnings[0])

    def test_returns_empty_on_subprocess_error(self) -> None:
        """subprocess.run が例外を出した場合、空リストを返すこと（処理を継続）。"""
        runner = self._make_runner()
        with unittest.mock.patch("subprocess.run", side_effect=OSError("git not found")):
            changed = runner._check_diff_after_improvement("step-1", "Phase 4 Self-Improve")
        self.assertEqual(changed, [])

    def test_source_inspection_calls_diff_check_in_phase3(self) -> None:
        """Phase 3 Adversarial Review で _check_diff_after_improvement が呼ばれること（ソースインスペクション）。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("_check_diff_after_improvement", source)
        self.assertIn("Phase 3 Adversarial Review", source)

    def test_source_inspection_calls_diff_check_in_phase4(self) -> None:
        """Phase 4 Self-Improve で _check_diff_after_improvement が呼ばれること（ソースインスペクション）。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("Phase 4 Self-Improve", source)


# ---------------------------------------------------------------------------
# Phase 6: サブセッション要否判定ヘルパーのテスト
# ---------------------------------------------------------------------------

class TestShouldUseSubSession(unittest.TestCase):
    """Phase 6: _should_use_*_sub_session ヘルパーの判定ロジックを検証する。"""

    def _make_runner(self, model: str = "claude-opus-4.7", **cfg_kwargs) -> StepRunner:
        cfg = SDKConfig(model=model, **cfg_kwargs)
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    # --- Pre-QA ---

    def test_pre_qa_same_model_no_workiq_uses_main_session(self) -> None:
        """qa_model == main_model かつ WorkIQ 無効 → サブセッション不要。"""
        runner = self._make_runner(model="claude-opus-4.7")
        # qa_model 未設定 → get_qa_model() は model を返す
        self.assertFalse(
            runner._should_use_pre_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    def test_pre_qa_different_model_creates_sub_session(self) -> None:
        """qa_model != main_model → サブセッション作成。"""
        runner = self._make_runner(model="claude-opus-4.7", qa_model="gpt-5.4")
        self.assertTrue(
            runner._should_use_pre_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    def test_pre_qa_workiq_enabled_creates_sub_session_even_if_same_model(self) -> None:
        """WorkIQ 有効 → モデルが同一でもサブセッション作成（WorkIQ は QA 専用）。"""
        runner = self._make_runner(model="claude-opus-4.7")
        self.assertTrue(
            runner._should_use_pre_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=True,
            )
        )

    def test_pre_qa_auto_model_same_as_main_no_sub_session(self) -> None:
        """qa_model=Auto かつ main_model=Auto → 同一とみなしサブセッション不要。"""
        from config import MODEL_AUTO_VALUE
        runner = self._make_runner(model=MODEL_AUTO_VALUE)
        # get_qa_model() は qa_model が None の場合 model を返す → AUTO 同士
        self.assertFalse(
            runner._should_use_pre_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    def test_pre_qa_auto_model_differs_from_fixed_model_creates_sub_session(self) -> None:
        """qa_model=Auto、main_model=固定モデル → 差異あり → サブセッション作成。"""
        from config import MODEL_AUTO_VALUE
        runner = self._make_runner(model="claude-opus-4.7", qa_model=MODEL_AUTO_VALUE)
        self.assertTrue(
            runner._should_use_pre_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    # --- Post-QA ---

    def test_post_qa_same_model_no_workiq_uses_main_session(self) -> None:
        """Post-QA: qa_model == main_model かつ WorkIQ 無効 → サブセッション不要。"""
        runner = self._make_runner(model="claude-opus-4.7")
        self.assertFalse(
            runner._should_use_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    def test_post_qa_different_model_creates_sub_session(self) -> None:
        """Post-QA: qa_model != main_model → サブセッション作成。"""
        runner = self._make_runner(model="claude-opus-4.7", qa_model="gpt-5.4")
        self.assertTrue(
            runner._should_use_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    def test_post_qa_workiq_enabled_creates_sub_session(self) -> None:
        """Post-QA: WorkIQ 有効 → サブセッション作成。"""
        runner = self._make_runner(model="claude-opus-4.7")
        self.assertTrue(
            runner._should_use_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=True,
            )
        )

    def test_post_qa_auto_model_same_no_sub_session(self) -> None:
        """Post-QA: qa_model=Auto かつ main_model=Auto → サブセッション不要。"""
        from config import MODEL_AUTO_VALUE
        runner = self._make_runner(model=MODEL_AUTO_VALUE)
        self.assertFalse(
            runner._should_use_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    # --- Review ---

    def test_review_same_model_uses_main_session(self) -> None:
        """Review: review_model == main_model → サブセッション不要。"""
        runner = self._make_runner(model="claude-opus-4.7")
        # review_model 未設定 → get_review_model() は model を返す
        self.assertFalse(
            runner._should_use_review_sub_session(
                review_model=runner.config.get_review_model(),
            )
        )

    def test_review_different_model_creates_sub_session(self) -> None:
        """Review: review_model != main_model → サブセッション作成。"""
        runner = self._make_runner(model="claude-opus-4.7", review_model="gpt-5.4")
        self.assertTrue(
            runner._should_use_review_sub_session(
                review_model=runner.config.get_review_model(),
            )
        )

    def test_review_auto_model_same_no_sub_session(self) -> None:
        """Review: review_model=Auto かつ main_model=Auto → サブセッション不要。"""
        from config import MODEL_AUTO_VALUE
        runner = self._make_runner(model=MODEL_AUTO_VALUE)
        self.assertFalse(
            runner._should_use_review_sub_session(
                review_model=runner.config.get_review_model(),
            )
        )

    def test_review_auto_model_differs_from_fixed_creates_sub_session(self) -> None:
        """Review: review_model=Auto、main_model=固定モデル → サブセッション作成。"""
        from config import MODEL_AUTO_VALUE
        runner = self._make_runner(model="claude-opus-4.7", review_model=MODEL_AUTO_VALUE)
        self.assertTrue(
            runner._should_use_review_sub_session(
                review_model=runner.config.get_review_model(),
            )
        )


# ---------------------------------------------------------------------------
# Phase 6: _sub_sessions_created カウンターのテスト
# ---------------------------------------------------------------------------

class TestSubSessionsCreatedCounter(unittest.TestCase):
    """Phase 6: _sub_sessions_created カウンターの初期値・リセット・インクリメントを検証する。"""

    def _make_runner(self, **cfg_kwargs) -> StepRunner:
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.7", **cfg_kwargs)
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    def test_initial_counter_is_zero(self) -> None:
        """StepRunner 生成直後の _sub_sessions_created は 0。"""
        runner = self._make_runner()
        self.assertEqual(runner._sub_sessions_created, 0)

    def test_counter_resets_on_dry_run(self) -> None:
        """run_step() 開始時に _sub_sessions_created がリセットされる（dry_run で確認）。"""
        runner = self._make_runner()
        runner._sub_sessions_created = 99  # 意図的に汚染

        with _CaptureOutput():
            asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        # dry_run なのでサブセッション作成はなく、run_step 冒頭でリセットされる
        self.assertEqual(runner._sub_sessions_created, 0)

    def test_helper_methods_exist(self) -> None:
        """Phase 6 で追加した helper メソッドが StepRunner に存在すること。"""
        runner = self._make_runner()
        self.assertTrue(callable(getattr(runner, "_should_use_pre_qa_sub_session", None)))
        self.assertTrue(callable(getattr(runner, "_should_use_qa_sub_session", None)))
        self.assertTrue(callable(getattr(runner, "_should_use_review_sub_session", None)))
        self.assertTrue(callable(getattr(runner, "_log_sub_session_reason", None)))
        self.assertTrue(callable(getattr(runner, "_log_main_session_reuse", None)))

    def test_log_sub_session_reason_does_not_leak_secrets(self) -> None:
        """_log_sub_session_reason が token/secret 等のキーを含まないイベントを出力すること。"""
        captured_events: list[str] = []
        runner = self._make_runner()
        original_event = runner.console.event
        runner.console.event = lambda msg: captured_events.append(msg)  # type: ignore[method-assign]

        runner._log_sub_session_reason(
            "1.1", "Pre-QA",
            qa_model="gpt-5.4",
            workiq_available=True,
        )
        runner.console.event = original_event

        self.assertTrue(len(captured_events) > 0, "イベントが出力されること")
        msg = captured_events[0]
        # モデル名は含んでよい（公開情報）
        self.assertIn("gpt-5.4", msg)
        # WorkIQ 有効の旨が含まれること
        self.assertIn("WorkIQ", msg)
        # 秘密情報キーワードが含まれないこと
        for secret_token in ("token", "secret", "password", "api_key", "bearer", "credential"):
            self.assertNotIn(secret_token, msg.lower(), f"'{secret_token}' は出力に含まれてはならない")

    def test_log_sub_session_reason_does_not_include_actual_token_value(self) -> None:
        """config に github_token が設定されていても、_log_sub_session_reason の出力に含まれないこと。"""
        captured_events: list[str] = []
        # 実際のトークンを模した値を config に設定する
        _fake_token = "ghp_THIS_IS_A_FAKE_TOKEN_FOR_TESTING_1234"
        cfg = SDKConfig(
            model="claude-opus-4.7",
            qa_model="gpt-5.4",
            github_token=_fake_token,
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)
        runner.console.event = lambda msg: captured_events.append(msg)  # type: ignore[method-assign]

        runner._log_sub_session_reason(
            "1.1", "Pre-QA",
            qa_model="gpt-5.4",
            workiq_available=False,
        )

        for msg in captured_events:
            self.assertNotIn(
                _fake_token, msg,
                "github_token の実値がログに出力されてはならない",
            )

    def test_log_main_session_reuse_emits_event(self) -> None:
        """_log_main_session_reuse がイベントを出力すること。"""
        captured_events: list[str] = []
        runner = self._make_runner()
        original_event = runner.console.event
        runner.console.event = lambda msg: captured_events.append(msg)  # type: ignore[method-assign]

        runner._log_main_session_reuse("1.1", "Post-QA")
        runner.console.event = original_event

        self.assertTrue(len(captured_events) > 0, "イベントが出力されること")
        self.assertIn("Post-QA", captured_events[0])
        self.assertIn("再利用", captured_events[0])

    def test_source_inspection_sub_sessions_counter_reset_in_run_step(self) -> None:
        """run_step() 内で _sub_sessions_created = 0 でリセットされることをソース検査。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("_sub_sessions_created = 0", source)

    def test_source_inspection_counter_incremented_on_pre_qa_sub_session(self) -> None:
        """_run_pre_execution_qa 内でカウンターがインクリメントされることをソース検査。"""
        import inspect
        source = inspect.getsource(StepRunner._run_pre_execution_qa)
        self.assertIn("_sub_sessions_created += 1", source)

    def test_source_inspection_counter_incremented_on_qa_sub_session(self) -> None:
        """run_step 内 Review フェーズでカウンターがインクリメントされることをソース検査。
        Post-QA は廃止済みのため Review の1箇所のみ出現する。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertGreaterEqual(source.count("_sub_sessions_created += 1"), 1)

    def test_source_inspection_uses_helper_methods_in_pre_qa(self) -> None:
        """_run_pre_execution_qa が _should_use_pre_qa_sub_session を使用することをソース検査。"""
        import inspect
        source = inspect.getsource(StepRunner._run_pre_execution_qa)
        self.assertIn("_should_use_pre_qa_sub_session", source)

    def test_source_inspection_uses_helper_methods_in_run_step(self) -> None:
        """run_step が _should_use_review_sub_session を使用することをソース検査。
        Post-QA 廃止に伴い _should_use_qa_sub_session は run_step で使用されなくなった。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("_should_use_review_sub_session", source)

    def test_source_inspection_log_methods_called_in_pre_qa(self) -> None:
        """_run_pre_execution_qa でサブセッション作成/再利用ログが呼ばれること。"""
        import inspect
        source = inspect.getsource(StepRunner._run_pre_execution_qa)
        self.assertIn("_log_sub_session_reason", source)
        self.assertIn("_log_main_session_reuse", source)

    def test_source_inspection_log_methods_called_in_run_step(self) -> None:
        """run_step で Review のサブセッション作成/再利用ログが呼ばれること。オフ）Post-QAは廃止された。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("_log_sub_session_reason", source)
        self.assertIn("_log_main_session_reuse", source)


if __name__ == "__main__":
    unittest.main()
