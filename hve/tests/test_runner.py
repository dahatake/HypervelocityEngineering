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

from config import SDKConfig
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


# -----------------------------------------------------------------------
# run_step Phase 2: qa_prompt 呼び出し有無テスト
# -----------------------------------------------------------------------

class _FakeSdkSession:
    """CopilotSession の最小モック。send_and_wait() に定形レスポンスを返す。"""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self._idx = 0

    async def send_and_wait(self, *args, **kwargs):
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            return resp
        return None

    def on(self, handler):
        pass

    async def disconnect(self):
        pass


class _FakeSdkClient:
    """CopilotClient の最小モック。create_session() で _FakeSdkSession を返す。"""

    def __init__(self, session: "_FakeSdkSession"):
        self._session = session

    async def start(self):
        pass

    async def create_session(self, **kwargs):
        return self._session

    async def stop(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


def _install_fake_sdk(session: "_FakeSdkSession") -> dict:
    """fake_sdk モジュールを sys.modules に注入し、元の状態を返す。"""
    import types

    fake_module = types.ModuleType("copilot")

    class _SubprocessConfig:
        def __init__(self, **kw):
            pass

    class _ExternalServerConfig:
        def __init__(self, **kw):
            pass

    class _PermissionHandler:
        @staticmethod
        async def approve_all(*a, **kw):
            return True

    fake_module.CopilotClient = lambda config=None: _FakeSdkClient(session)
    fake_module.SubprocessConfig = _SubprocessConfig
    fake_module.ExternalServerConfig = _ExternalServerConfig
    fake_module.PermissionHandler = _PermissionHandler

    fake_session_module = types.ModuleType("copilot.session")
    fake_session_module.PermissionHandler = _PermissionHandler
    fake_module.session = fake_session_module

    originals = {
        k: sys.modules.get(k, _SENTINEL)
        for k in ["copilot", "copilot.session"]
    }
    sys.modules["copilot"] = fake_module
    sys.modules["copilot.session"] = fake_session_module
    return originals


def _restore_sdk(originals: dict) -> None:
    for k, v in originals.items():
        if v is _SENTINEL:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


class TestRunStepPhase2QaPrompt(unittest.TestCase):
    """run_step() の Phase 2 で qa_prompt() 呼び出し有無が正しいことを検証する。

    パース成功時: qa_prompt() は呼ばれない（整形テーブルのみ表示）
    パース失敗時: qa_prompt() が呼ばれる（生 Markdown フォールバック）
    """

    _VALID_QA_CONTENT = (
        "| No. | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 |\n"
        "|-----|------|--------|----------|----------------|\n"
        "| 1 | テスト？ | A) はい / B) いいえ | A) はい | 理由 |\n"
    )

    _LEGACY_QA_CONTENT = (
        "| No. | 質問 | 選択肢 | デフォルトの回答案 | 選択理由 |\n"
        "|-----|------|--------|-------------------|----------|\n"
        "| 1 | テスト？ | A) はい / B) いいえ | A) はい | 理由 |\n"
    )

    def _make_runner(self, qa_content: str) -> "tuple[StepRunner, Console, list, list]":
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=True,
            auto_contents_review=False,
            auto_self_improve=False,
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)
        return runner, console, qa_content

    def _run_with_fake_sdk(self, qa_content: str) -> "tuple[list, list]":
        """fake SDK を使って run_step() の Phase 2 を実行し、qa_prompt と questionnaire_table の
        呼び出し回数を返す。"""
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=True,
            auto_contents_review=False,
            auto_self_improve=False,
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        qa_prompt_calls: list = []
        questionnaire_table_calls: list = []

        # send_and_wait の応答順序:
        #   1回目: Phase 1 メインタスク → None
        #   2回目: Phase 2a QA生成 → qa_content 相当の文字列レスポンス
        #   3回目以降: save/consolidate → None
        class _FakeResponse:
            def __init__(self, text: str):
                self.data = type("D", (), {"content": text})()

        session = _FakeSdkSession([
            None,                            # Phase 1
            _FakeResponse(qa_content),       # Phase 2a
            None, None, None,                # Phase 2c save/consolidate / fallback
        ])
        originals = _install_fake_sdk(session)
        try:
            with unittest.mock.patch.object(
                console, "qa_prompt",
                side_effect=lambda *a, **kw: qa_prompt_calls.append(True),
            ), unittest.mock.patch.object(
                console, "questionnaire_table",
                side_effect=lambda *a, **kw: questionnaire_table_calls.append(True),
            ), unittest.mock.patch.object(
                console, "answer_summary",
            ), unittest.mock.patch.object(
                console, "status",
            ), unittest.mock.patch("runner._read_stdin_multiline", return_value=""),\
            unittest.mock.patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = False
                asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))
        finally:
            _restore_sdk(originals)

        return qa_prompt_calls, questionnaire_table_calls

    def test_parse_success_no_qa_prompt(self) -> None:
        """パース成功時: qa_prompt() は呼ばれず、questionnaire_table() が呼ばれる。"""
        qa_calls, table_calls = self._run_with_fake_sdk(self._VALID_QA_CONTENT)
        self.assertFalse(qa_calls, "パース成功時は qa_prompt() を呼ばないべき")
        self.assertTrue(table_calls, "パース成功時は questionnaire_table() が呼ばれるべき")

    def test_parse_failure_calls_qa_prompt(self) -> None:
        """パース失敗時（空コンテンツ）: qa_prompt() が呼ばれる（生 Markdown フォールバック）。"""
        qa_calls, table_calls = self._run_with_fake_sdk("")
        self.assertTrue(qa_calls, "パース失敗時は qa_prompt() が呼ばれるべき")
        self.assertFalse(table_calls, "パース失敗時は questionnaire_table() を呼ばないべき")

    def test_legacy_format_parsed_as_success(self) -> None:
        """旧形式（デフォルトの回答案/選択理由）はパース成功扱いになる。"""
        qa_calls, table_calls = self._run_with_fake_sdk(self._LEGACY_QA_CONTENT)
        self.assertFalse(qa_calls, "旧形式でもパース成功時は qa_prompt() を呼ばないべき")
        self.assertTrue(table_calls, "旧形式でもパース成功時は questionnaire_table() が呼ばれるべき")

    def _run_with_fake_sdk_and_config(
        self,
        qa_content: str,
        *,
        qa_auto_defaults: bool = False,
        stdin_isatty: bool = False,
        cwd: "Path | None" = None,
    ) -> "tuple[bool, list, list, unittest.mock.AsyncMock]":
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=True,
            auto_contents_review=False,
            auto_self_improve=False,
            qa_auto_defaults=qa_auto_defaults,
            run_id="testrun",
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        qa_prompt_calls: list = []
        questionnaire_table_calls: list = []

        class _FakeResponse:
            def __init__(self, text: str):
                self.data = type("D", (), {"content": text})()

        session = _FakeSdkSession([
            None,
            _FakeResponse(qa_content),
            None, None, None,
        ])
        originals = _install_fake_sdk(session)
        read_mock = unittest.mock.AsyncMock(return_value="")
        old_cwd = os.getcwd()
        try:
            if cwd is not None:
                os.chdir(cwd)
            with unittest.mock.patch.object(
                console, "qa_prompt",
                side_effect=lambda *a, **kw: qa_prompt_calls.append(True),
            ), unittest.mock.patch.object(
                console, "questionnaire_table",
                side_effect=lambda *a, **kw: questionnaire_table_calls.append(True),
            ), unittest.mock.patch.object(
                console, "answer_summary",
            ), unittest.mock.patch.object(
                console, "status",
            ), unittest.mock.patch("runner._read_stdin_multiline", new=read_mock), \
                 unittest.mock.patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = stdin_isatty
                result = asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))
        finally:
            os.chdir(old_cwd)
            _restore_sdk(originals)

        return result, qa_prompt_calls, questionnaire_table_calls, read_mock

    def test_artifact_summary_fallback_parses_referenced_qa_file(self) -> None:
        """QA 応答本文が artifacts 参照だけでも参照先 [Qxx] 質問票をパースする。"""
        helper_content = (
            "[Q01]\n"
            "- 問題種別: 不明瞭\n"
            "- 重大度: major\n"
            "- 質問内容: 代表SKUの定義はどれですか。\n"
            "- 未回答時の既定値候補: TBD\n"
            "- 既定値候補の理由: 根拠不足\n"
            "- 未回答のまま進めた場合の影響: 設計判断が分岐する\n"
        )
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            qa_dir = base / "qa"
            qa_dir.mkdir()
            (qa_dir / "QA-DocConsistency-20260101-120000.md").write_text(
                helper_content,
                encoding="utf-8",
            )
            qa_content = (
                "## 成果物サマリー\n"
                "- artifacts: qa/QA-DocConsistency-20260101-120000.md\n"
            )

            result, qa_calls, table_calls, read_mock = self._run_with_fake_sdk_and_config(
                qa_content,
                qa_auto_defaults=True,
                stdin_isatty=True,
                cwd=base,
            )

        self.assertTrue(result)
        self.assertFalse(qa_calls, "artifacts フォールバック成功時は生 Markdown 入力待ちに落ちない")
        self.assertTrue(table_calls, "参照先質問票をパースして questionnaire_table() が呼ばれるべき")
        read_mock.assert_not_awaited()

    def test_parse_failure_with_qa_auto_defaults_does_not_wait_for_stdin(self) -> None:
        """qa_auto_defaults=True ではパース失敗時でも TTY 入力待ちに入らない。"""
        result, qa_calls, table_calls, read_mock = self._run_with_fake_sdk_and_config(
            "",
            qa_auto_defaults=True,
            stdin_isatty=True,
        )

        self.assertTrue(result)
        self.assertTrue(qa_calls, "パース失敗時は生 QA 応答を表示する")
        self.assertFalse(table_calls, "質問がないため questionnaire_table() は呼ばれない")
        read_mock.assert_not_awaited()


class TestRunStepWorkIqMcpHealthCheck(unittest.TestCase):
    def test_main_session_excludes_workiq_mcp(self) -> None:
        import types

        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            workiq_enabled=True,
            mcp_servers={WORKIQ_MCP_SERVER_NAME: {"command": "manual"}},
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        mcp_list = unittest.mock.AsyncMock(
            return_value=types.SimpleNamespace(
                servers=[
                    types.SimpleNamespace(
                        name="_hve_workiq",
                        status=types.SimpleNamespace(value="connected"),
                        error=None,
                    )
                ]
            )
        )

        class _FakeSession:
            def __init__(self) -> None:
                self.rpc = types.SimpleNamespace(
                    mcp=types.SimpleNamespace(list=mcp_list)
                )

            async def send_and_wait(self, *args, **kwargs):
                return None

            async def disconnect(self):
                return None

            def on(self, handler):
                return None

        class _FakeClient:
            def __init__(self) -> None:
                self.create_session_kwargs = []

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

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ), unittest.mock.patch(
            "runner.is_workiq_available", return_value=True
        ), unittest.mock.patch(
            "runner.build_workiq_mcp_config", return_value={"_hve_workiq": {}}
        ):
            result = asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertTrue(result)
        self.assertEqual(len(fake_client.create_session_kwargs), 1)
        self.assertNotIn(
            WORKIQ_MCP_SERVER_NAME,
            fake_client.create_session_kwargs[0].get("mcp_servers", {}),
        )
        mcp_list.assert_not_awaited()
        self.assertFalse(runner._workiq_mcp_connection_failed)

    def test_qa_sub_session_adds_workiq_mcp(self) -> None:
        import types

        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            workiq_enabled=True,
            auto_qa=True,
            qa_auto_defaults=True,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="run-qa-workiq",
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        qa_content = (
            "[Q01]\n"
            "- 問題種別: 不明瞭\n"
            "- 重大度: major\n"
            "- 質問内容: 会議で決まった対象範囲はどれですか。\n"
            "- 未回答時の既定値候補: TBD\n"
            "- 既定値候補の理由: 根拠不足\n"
            "- 未回答のまま進めた場合の影響: 設計判断が分岐する\n"
        )

        mcp_list = unittest.mock.AsyncMock(
            return_value=types.SimpleNamespace(
                servers=[
                    types.SimpleNamespace(
                        name=WORKIQ_MCP_SERVER_NAME,
                        status=types.SimpleNamespace(value="connected"),
                        error=None,
                    )
                ]
            )
        )

        class _FakeSession:
            def __init__(self, responses):
                self._responses = list(responses)
                self.rpc = types.SimpleNamespace(
                    mcp=types.SimpleNamespace(list=mcp_list)
                )

            async def send_and_wait(self, *args, **kwargs):
                if self._responses:
                    return self._responses.pop(0)
                return None

            async def disconnect(self):
                return None

            def on(self, handler):
                return None

        class _FakeClient:
            def __init__(self) -> None:
                self.create_session_kwargs = []
                self._sessions = [
                    _FakeSession(["main output"]),
                    _FakeSession([qa_content, "consolidated"]),
                ]

            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                self.create_session_kwargs.append(kwargs)
                return self._sessions.pop(0)

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

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ), unittest.mock.patch(
            "runner.is_workiq_available", return_value=True
        ), unittest.mock.patch(
            "runner.build_workiq_mcp_config", return_value={WORKIQ_MCP_SERVER_NAME: {}}
        ), unittest.mock.patch(
            "runner.query_workiq", new=unittest.mock.AsyncMock(return_value="m365 context")
        ) as mock_query_workiq, unittest.mock.patch(
            "runner.save_workiq_result", return_value=None
        ), unittest.mock.patch(
            "runner.QAMerger.save_merged", return_value=True
        ):
            result = asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertTrue(result)
        self.assertEqual(len(fake_client.create_session_kwargs), 2)
        self.assertNotIn(
            WORKIQ_MCP_SERVER_NAME,
            fake_client.create_session_kwargs[0].get("mcp_servers", {}),
        )
        self.assertIn(
            WORKIQ_MCP_SERVER_NAME,
            fake_client.create_session_kwargs[1].get("mcp_servers", {}),
        )
        mcp_list.assert_awaited_once()
        mock_query_workiq.assert_awaited_once()

    def test_qa_phase_ignores_configured_workiq_mcp_when_workiq_disabled(self) -> None:
        import types

        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            workiq_enabled=False,
            mcp_servers={WORKIQ_MCP_SERVER_NAME: {"command": "manual-workiq"}},
            auto_qa=True,
            qa_auto_defaults=True,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="run-qa-workiq-disabled",
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        qa_content = (
            "[Q01]\n"
            "- 問題種別: 不明瞭\n"
            "- 重大度: major\n"
            "- 質問内容: 会議で決まった対象範囲はどれですか。\n"
            "- 未回答時の既定値候補: TBD\n"
            "- 既定値候補の理由: 根拠不足\n"
            "- 未回答のまま進めた場合の影響: 設計判断が分岐する\n"
        )
        mcp_list = unittest.mock.AsyncMock()

        class _FakeSession:
            def __init__(self, responses):
                self._responses = list(responses)
                self.rpc = types.SimpleNamespace(
                    mcp=types.SimpleNamespace(list=mcp_list)
                )

            async def send_and_wait(self, *args, **kwargs):
                if self._responses:
                    return self._responses.pop(0)
                return None

            async def disconnect(self):
                return None

            def on(self, handler):
                return None

        class _FakeClient:
            def __init__(self) -> None:
                self.create_session_kwargs = []
                self._session = _FakeSession(["main output", qa_content, "consolidated"])

            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                self.create_session_kwargs.append(kwargs)
                return self._session

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

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ), unittest.mock.patch(
            "runner.is_workiq_available", return_value=True
        ), unittest.mock.patch(
            "runner.query_workiq", new=unittest.mock.AsyncMock(return_value="m365 context")
        ) as mock_query_workiq, unittest.mock.patch(
            "runner.QAMerger.save_merged", return_value=True
        ):
            result = asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertTrue(result)
        self.assertEqual(len(fake_client.create_session_kwargs), 1)
        self.assertNotIn(
            WORKIQ_MCP_SERVER_NAME,
            fake_client.create_session_kwargs[0].get("mcp_servers", {}),
        )
        mcp_list.assert_not_awaited()
        mock_query_workiq.assert_not_awaited()

    def test_qa_sub_session_allows_configured_workiq_mcp_without_cli_detection(self) -> None:
        import types

        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            workiq_enabled=True,
            mcp_servers={WORKIQ_MCP_SERVER_NAME: {"command": "manual-workiq"}},
            auto_qa=True,
            qa_auto_defaults=True,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="run-qa-manual-workiq",
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        qa_content = (
            "[Q01]\n"
            "- 問題種別: 不明瞭\n"
            "- 重大度: major\n"
            "- 質問内容: 会議で決まった対象範囲はどれですか。\n"
            "- 未回答時の既定値候補: TBD\n"
            "- 既定値候補の理由: 根拠不足\n"
            "- 未回答のまま進めた場合の影響: 設計判断が分岐する\n"
        )

        mcp_list = unittest.mock.AsyncMock(
            return_value=types.SimpleNamespace(
                servers=[
                    types.SimpleNamespace(
                        name=WORKIQ_MCP_SERVER_NAME,
                        status=types.SimpleNamespace(value="connected"),
                        error=None,
                    )
                ]
            )
        )

        class _FakeSession:
            def __init__(self, responses):
                self._responses = list(responses)
                self.rpc = types.SimpleNamespace(
                    mcp=types.SimpleNamespace(list=mcp_list)
                )

            async def send_and_wait(self, *args, **kwargs):
                if self._responses:
                    return self._responses.pop(0)
                return None

            async def disconnect(self):
                return None

            def on(self, handler):
                return None

        class _FakeClient:
            def __init__(self) -> None:
                self.create_session_kwargs = []
                self._sessions = [
                    _FakeSession(["main output"]),
                    _FakeSession([qa_content, "consolidated"]),
                ]

            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                self.create_session_kwargs.append(kwargs)
                return self._sessions.pop(0)

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

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ), unittest.mock.patch(
            "runner.is_workiq_available", return_value=False
        ), unittest.mock.patch(
            "runner.build_workiq_mcp_config", return_value={WORKIQ_MCP_SERVER_NAME: {}}
        ) as mock_build_workiq_mcp_config, unittest.mock.patch(
            "runner.query_workiq", new=unittest.mock.AsyncMock(return_value="m365 context")
        ) as mock_query_workiq, unittest.mock.patch(
            "runner.save_workiq_result", return_value=None
        ), unittest.mock.patch(
            "runner.QAMerger.save_merged", return_value=True
        ):
            result = asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertTrue(result)
        self.assertEqual(len(fake_client.create_session_kwargs), 2)
        self.assertNotIn(
            WORKIQ_MCP_SERVER_NAME,
            fake_client.create_session_kwargs[0].get("mcp_servers", {}),
        )
        self.assertEqual(
            fake_client.create_session_kwargs[1].get("mcp_servers", {}).get(WORKIQ_MCP_SERVER_NAME),
            {"command": "manual-workiq"},
        )
        mock_build_workiq_mcp_config.assert_not_called()
        mcp_list.assert_awaited_once()
        mock_query_workiq.assert_awaited_once()

    def test_review_sub_session_excludes_workiq_mcp(self) -> None:
        import types

        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            review_model="gpt-5.4",
            workiq_enabled=True,
            mcp_servers={WORKIQ_MCP_SERVER_NAME: {"command": "manual"}},
            auto_qa=False,
            auto_contents_review=True,
            auto_self_improve=False,
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        class _FakeSession:
            def __init__(self, responses):
                self._responses = list(responses)
                self.rpc = types.SimpleNamespace(mcp=types.SimpleNamespace(list=unittest.mock.AsyncMock()))

            async def send_and_wait(self, *args, **kwargs):
                if self._responses:
                    return self._responses.pop(0)
                return None

            async def disconnect(self):
                return None

            def on(self, handler):
                return None

        class _FakeClient:
            def __init__(self) -> None:
                self.create_session_kwargs = []
                self._sessions = [
                    _FakeSession(["main output"]),
                    _FakeSession(["合格判定: ✅ PASS"]),
                ]

            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                self.create_session_kwargs.append(kwargs)
                return self._sessions.pop(0)

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

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ), unittest.mock.patch("runner.is_workiq_available", return_value=True):
            result = asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertTrue(result)
        self.assertEqual(len(fake_client.create_session_kwargs), 2)
        self.assertNotIn(
            WORKIQ_MCP_SERVER_NAME,
            fake_client.create_session_kwargs[1].get("mcp_servers", {}),
        )


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


class TestAqodWorkIQWarningSuppressionPhase1(unittest.TestCase):
    """Phase 1 ではワークフロー種別を問わず Work IQ 未呼び出し警告を出さない。"""

    def _make_runner(self, **cfg_kwargs) -> StepRunner:
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=True,
            auto_contents_review=False,
            auto_self_improve=False,
            **cfg_kwargs,
        )
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    def _run_with_mcp_connected(
        self,
        runner: StepRunner,
        workflow_id: "Optional[str]" = None,
    ) -> "tuple[list[str], list[str]]":
        """Work IQ MCP が接続済みの状態をシミュレートして run_step() を実行し、
        (logged_statuses, logged_warnings) を返す。

        _install_fake_sdk の _FakeSdkSession を拡張して rpc.mcp.list() をサポートする。
        """
        import types

        _WORKIQ_SERVER_NAME = WORKIQ_MCP_SERVER_NAME

        class _SrvStatus:
            value = "connected"

        class _FakeSrv:
            name = _WORKIQ_SERVER_NAME
            status = _SrvStatus()
            error = None

        class _FakeMcpList:
            servers = [_FakeSrv()]

        class _FakeMcp:
            async def list(self):
                return _FakeMcpList()

        class _FakeRpc:
            mcp = _FakeMcp()

        class _SessionWithMcp(_FakeSdkSession):
            rpc = _FakeRpc()

            async def disconnect(self):
                pass

        session = _SessionWithMcp([None])  # Phase 1 → None

        # copilot.session モジュールモック（PermissionHandler 提供）
        fake_session_mod = types.ModuleType("copilot.session")

        class _PH:
            @staticmethod
            async def approve_all(*a, **kw):
                return True

        fake_session_mod.PermissionHandler = _PH

        logged_statuses: list = []
        logged_warnings: list = []

        originals = {k: sys.modules.get(k, _SENTINEL) for k in ["copilot", "copilot.session"]}
        originals.update(_install_fake_sdk(session))
        sys.modules["copilot.session"] = fake_session_mod
        try:
            with unittest.mock.patch("runner.is_workiq_available", return_value=True), \
                 unittest.mock.patch(
                     "runner.build_workiq_mcp_config",
                     return_value={_WORKIQ_SERVER_NAME: {}},
                 ), \
                 unittest.mock.patch("runner._read_stdin_multiline", return_value=""), \
                 unittest.mock.patch("sys.stdin") as mock_stdin, \
                 unittest.mock.patch.object(
                     runner.console, "status", side_effect=logged_statuses.append,
                 ), \
                 unittest.mock.patch.object(
                     runner.console, "warning", side_effect=logged_warnings.append,
                 ), \
                 _CaptureOutput():
                mock_stdin.isatty.return_value = False
                _run(runner.run_step("1", "Step", "プロンプト", workflow_id=workflow_id))
        finally:
            for k, v in originals.items():
                if v is _SENTINEL:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

        return logged_statuses, logged_warnings

    def test_aqod_workiq_draft_no_warning(self) -> None:
        """AQOD + workiq_draft_mode では Work IQ 未呼び出し警告が出ない。"""
        runner = self._make_runner(workiq_enabled=True, workiq_draft_mode=True)
        _statuses, warnings = self._run_with_mcp_connected(runner, workflow_id="aqod")
        self.assertFalse(
            any("Work IQ MCP ツールが1度も呼び出されませんでした" in w for w in warnings),
            f"AQOD draft モードでは警告が出ないはず。実際の警告: {warnings}",
        )

    def test_aqod_workiq_draft_info_log(self) -> None:
        """AQOD + workiq_draft_mode では QA セッションで Work IQ 接続確認を行う。"""
        runner = self._make_runner(workiq_enabled=True, workiq_draft_mode=True)
        statuses, warnings = self._run_with_mcp_connected(runner, workflow_id="aqod")
        self.assertTrue(
            any("QA セッション" in s for s in statuses),
            f"QA セッションでの接続確認ログが出るはず。実際の status ログ: {statuses}",
        )
        # Phase 1 警告（Work IQ 未呼び出し）が出ていないことを確認（Phase 2 の warnings は許容）
        self.assertFalse(
            any("Work IQ MCP ツールが1度も呼び出されませんでした" in w for w in warnings),
            f"AQOD draft モードでは Work IQ 未呼び出し警告は出ないはず。実際: {warnings}",
        )

    def test_non_aqod_no_phase1_warning(self) -> None:
        """非 AQOD ワークフローでも Phase 1 の Work IQ 未呼び出し警告は出ない。"""
        runner = self._make_runner(workiq_enabled=True, workiq_draft_mode=True)
        _statuses, warnings = self._run_with_mcp_connected(runner, workflow_id="akm")
        self.assertFalse(
            any("Work IQ MCP ツールが1度も呼び出されませんでした" in w for w in warnings),
            f"Phase 1 では Work IQ 未呼び出し警告は出ないはず。実際の警告: {warnings}",
        )

    def test_workflow_id_none_no_phase1_warning(self) -> None:
        """workflow_id=None（デフォルト）の場合も Phase 1 の Work IQ 未呼び出し警告は出ない。"""
        runner = self._make_runner(workiq_enabled=True, workiq_draft_mode=True)
        _statuses, warnings = self._run_with_mcp_connected(runner, workflow_id=None)
        self.assertFalse(
            any("Work IQ MCP ツールが1度も呼び出されませんでした" in w for w in warnings),
            f"Phase 1 では Work IQ 未呼び出し警告は出ないはず。実際の警告: {warnings}",
        )

    def test_workflow_id_optional_default_does_not_break(self) -> None:
        """workflow_id 省略（None）で run_step() が既存通り動作する（dry_run）。"""
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.7")
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)
        with _CaptureOutput():
            result = _run(runner.run_step("1.1", "テスト", "プロンプト"))
        self.assertTrue(result)

    def test_workflow_id_passed_does_not_break(self) -> None:
        """workflow_id を明示指定しても run_step() が True を返す（dry_run）。"""
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.7")
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)
        with _CaptureOutput():
            result = _run(runner.run_step("1.1", "テスト", "プロンプト", workflow_id="akm"))
        self.assertTrue(result)


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


if __name__ == "__main__":
    unittest.main()
