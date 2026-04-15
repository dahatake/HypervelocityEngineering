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
from runner import StepRunner, _is_review_fail

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


class _FakeSdkClient:
    """CopilotClient の最小モック。create_session() で _FakeSdkSession を返す。"""

    def __init__(self, session: "_FakeSdkSession"):
        self._session = session

    async def start(self):
        pass

    async def create_session(self, **kwargs):
        return self._session

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

    originals = {
        k: sys.modules.get(k, _SENTINEL)
        for k in ["copilot"]
    }
    sys.modules["copilot"] = fake_module
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
            model="claude-opus-4.6",
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
            model="claude-opus-4.6",
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


if __name__ == "__main__":
    unittest.main()
