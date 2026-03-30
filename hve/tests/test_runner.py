"""test_runner.py — StepRunner の dry_run テスト"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig
from console import Console
from runner import StepRunner

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
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.6", **cfg_kwargs)
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


class TestStepRunnerNonDryRunNoSDK(unittest.TestCase):
    """dry_run=False で SDK 未インストール時に False を返す。"""

    def test_returns_false_when_sdk_missing(self) -> None:
        cfg = SDKConfig(dry_run=False, model="claude-opus-4.6")
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

    def _make_runner(self, show_stream: bool = True, verbose: bool = False) -> StepRunner:
        cfg = SDKConfig(dry_run=True)
        console = Console(verbose=verbose, quiet=False, show_stream=show_stream)
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
        """data.delta_content がない場合に data.content にフォールバックする。"""
        runner = self._make_runner(show_stream=True)
        event = _FakeEvent("assistant.message_delta", _FakeEventData(content="World"))
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

    def test_tool_execution_complete_success(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("tool.execution_complete", _FakeEventData(success=True))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("✓", cap.stdout)

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


if __name__ == "__main__":
    unittest.main()
