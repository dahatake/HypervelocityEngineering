"""test_runner.py — StepRunner の dry_run テスト"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig
from console import Console
from runner import StepRunner, _is_review_fail, _make_log_handler, _StderrLogReader

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


class TestMakeCliLogHandler(unittest.TestCase):
    """StepRunner._make_cli_log_handler() のテスト。"""

    def _make_runner(self) -> StepRunner:
        config = SDKConfig()
        console = Console(verbosity=3)
        return StepRunner(config, console)

    def test_handler_calls_console_cli_log(self) -> None:
        """コールバックが console.cli_log() を呼び出す。"""
        runner = self._make_runner()
        handler = runner._make_cli_log_handler("1")
        with unittest.mock.patch.object(runner.console, 'cli_log') as mock_cli_log:
            handler("● Environment loaded: 10 agents")
            mock_cli_log.assert_called_once_with("1", "● Environment loaded: 10 agents")

    def test_handler_splits_multiline(self) -> None:
        """複数行文字列は行ごとに分割して cli_log() を呼び出す。"""
        runner = self._make_runner()
        handler = runner._make_cli_log_handler("1")
        with unittest.mock.patch.object(runner.console, 'cli_log') as mock_cli_log:
            handler("○ List directory qa\n  └ qa/")
            self.assertEqual(mock_cli_log.call_count, 2)

    def test_handler_ignores_empty_lines(self) -> None:
        """空行・空白のみの行は cli_log() を呼び出さない。"""
        runner = self._make_runner()
        handler = runner._make_cli_log_handler("1")
        with unittest.mock.patch.object(runner.console, 'cli_log') as mock_cli_log:
            handler("")
            handler("   ")
            handler("\n\n")
            mock_cli_log.assert_not_called()

    def test_handler_passes_step_id(self) -> None:
        """step_id がコールバック経由で cli_log() に渡される。"""
        runner = self._make_runner()
        handler = runner._make_cli_log_handler("2.3")
        with unittest.mock.patch.object(runner.console, 'cli_log') as mock_cli_log:
            handler("○ Search (glob)")
            mock_cli_log.assert_called_once_with("2.3", "○ Search (glob)")


class TestMakeLogHandlerStandalone(unittest.TestCase):
    """モジュールレベル _make_log_handler() のテスト（orchestrator.py からも利用）。"""

    def test_standalone_handler_calls_cli_log(self) -> None:
        """_make_log_handler() が console.cli_log() を呼び出す。"""
        console = Console(verbosity=3)
        handler = _make_log_handler(console, "review")
        with unittest.mock.patch.object(console, 'cli_log') as mock_cli_log:
            handler("● Environment loaded: 5 agents")
            mock_cli_log.assert_called_once_with("review", "● Environment loaded: 5 agents")

    def test_standalone_handler_ignores_empty(self) -> None:
        """空行は cli_log() を呼び出さない。"""
        console = Console(verbosity=3)
        handler = _make_log_handler(console, "review")
        with unittest.mock.patch.object(console, 'cli_log') as mock_cli_log:
            handler("")
            handler("  ")
            mock_cli_log.assert_not_called()


class TestStderrLogReader(unittest.TestCase):
    """_StderrLogReader のユニットテスト。"""

    def _make_fake_stderr(self, content: bytes) -> io.BytesIO:
        """bytes を BytesIO stream に包む。"""
        return io.BytesIO(content)

    def _run_reader(self, content: bytes, step_id: str = "1") -> tuple:
        """ヘルパー: リーダーを起動してストリームが EOF に達したらスレッドを join する。
        (sleep を使わず決定論的にテストするため)
        """
        console = Console(verbosity=3, quiet=False)
        fake_stderr = self._make_fake_stderr(content)
        received: list = []
        with unittest.mock.patch.object(
            console, "cli_log", side_effect=lambda sid, line: received.append((sid, line))
        ):
            reader = _StderrLogReader(fake_stderr, console, step_id)
            reader.start()
            # EOF 到達後にスレッドが自然終了するのを待つ
            if reader._thread is not None:
                reader._thread.join(timeout=5.0)
            reader.stop()
        return reader, received

    def test_reads_stderr_lines_to_cli_log(self) -> None:
        """stderr の各行が console.cli_log() に正しく渡される。"""
        content = "● Environment loaded\n○ List directory\n".encode("utf-8")
        _, received = self._run_reader(content)
        lines = [line for _, line in received]
        self.assertIn("● Environment loaded", lines)
        self.assertIn("○ List directory", lines)

    def test_empty_lines_are_skipped(self) -> None:
        """空行・空白行は cli_log() に渡されない。"""
        content = "\n\n● Test line\n\n".encode("utf-8")
        _, received = self._run_reader(content)
        lines = [line for _, line in received]
        # 空行は含まれず、"● Test line" のみが受け取られる
        self.assertTrue(all(line.strip() for line in lines))
        self.assertTrue(any("Test line" in line for line in lines))

    def test_stop_sets_event(self) -> None:
        """stop() を呼ぶと _stop イベントがセットされる。"""
        console = Console(verbosity=3, quiet=False)
        fake_stderr = self._make_fake_stderr(b"line1\n")
        reader = _StderrLogReader(fake_stderr, console, "1")
        reader.start()
        reader.stop()
        self.assertTrue(reader._stop.is_set())

    def test_stop_without_start_is_safe(self) -> None:
        """start() を呼ばずに stop() を呼んでもエラーにならない。"""
        console = Console(verbosity=3, quiet=False)
        fake_stderr = self._make_fake_stderr(b"")
        reader = _StderrLogReader(fake_stderr, console, "1")
        # start() なし
        reader.stop()  # 例外が発生しないことを確認
        self.assertTrue(reader._stop.is_set())

    def test_step_id_passed_to_cli_log(self) -> None:
        """step_id が cli_log() の第1引数として渡される。"""
        content = "Remote session established\n".encode("utf-8")
        _, received = self._run_reader(content, step_id="2.3")
        self.assertTrue(len(received) > 0)
        self.assertTrue(all(sid == "2.3" for sid, _ in received))

    def test_handles_text_mode_str_lines(self) -> None:
        """text mode の stream (readline が str を返す) も正しく処理される。"""
        console = Console(verbosity=3, quiet=False)
        received: list = []

        class _FakeTextStream:
            def __init__(self, lines):
                self._lines = iter(lines)

            def readline(self):
                try:
                    return next(self._lines)
                except StopIteration:
                    return ""

        fake_stream = _FakeTextStream(["● Loaded\n", "○ Activity\n", ""])
        with unittest.mock.patch.object(
            console, "cli_log", side_effect=lambda sid, line: received.append(line)
        ):
            reader = _StderrLogReader(fake_stream, console, "1")
            reader.start()
            if reader._thread is not None:
                reader._thread.join(timeout=5.0)
            reader.stop()
        self.assertIn("● Loaded", received)
        self.assertIn("○ Activity", received)


if __name__ == "__main__":
    unittest.main()
