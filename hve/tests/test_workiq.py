"""test_workiq.py — workiq モジュールのユニットテスト"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import asyncio
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import workiq  # type: ignore[import-untyped]


class TestWorkIQAvailability(unittest.TestCase):
    def setUp(self) -> None:
        workiq._workiq_available_cache = None

    def test_is_workiq_available_true_when_npx_check_succeeds(self) -> None:
        proc = mock.Mock(returncode=0)
        with mock.patch("workiq.shutil.which", side_effect=lambda x: "/usr/bin/npx" if x == "npx" else None), \
                mock.patch("workiq.subprocess.run", return_value=proc):
            self.assertTrue(workiq.is_workiq_available())

    def test_is_workiq_available_false_when_npx_missing_even_if_workiq_exists(self) -> None:
        with mock.patch("workiq.shutil.which", side_effect=lambda x: "/usr/bin/workiq" if x == "workiq" else None):
            self.assertFalse(workiq.is_workiq_available())

    def test_is_workiq_available_false_without_npx(self) -> None:
        with mock.patch("workiq.shutil.which", return_value=None):
            self.assertFalse(workiq.is_workiq_available())

    def test_is_workiq_available_uses_npx_version(self) -> None:
        proc = mock.Mock(returncode=0)
        with mock.patch("workiq.shutil.which", side_effect=lambda x: "/usr/bin/npx" if x == "npx" else None), \
                mock.patch("workiq.subprocess.run", return_value=proc):
            self.assertTrue(workiq.is_workiq_available())

    def test_is_workiq_available_cache(self) -> None:
        proc = mock.Mock(returncode=0)
        with mock.patch("workiq.shutil.which", side_effect=lambda x: "/usr/bin/npx" if x == "npx" else None), \
                mock.patch("workiq.subprocess.run", return_value=proc) as run_mock:
            self.assertTrue(workiq.is_workiq_available())
            self.assertTrue(workiq.is_workiq_available())
        self.assertEqual(run_mock.call_count, 1)

    def test_is_workiq_available_passes_shell_true_on_windows(self) -> None:
        proc = mock.Mock(returncode=0)
        with mock.patch("workiq._SHELL_ON_WINDOWS", True), \
                mock.patch("workiq.shutil.which", return_value="C:\\Program Files\\nodejs\\npx.CMD"), \
                mock.patch("workiq.subprocess.run", return_value=proc) as run_mock:
            self.assertTrue(workiq.is_workiq_available())
        self.assertTrue(run_mock.call_args.kwargs["shell"])

    def test_is_workiq_available_passes_shell_false_on_non_windows(self) -> None:
        proc = mock.Mock(returncode=0)
        with mock.patch("workiq._SHELL_ON_WINDOWS", False), \
                mock.patch("workiq.shutil.which", return_value="/usr/bin/npx"), \
                mock.patch("workiq.subprocess.run", return_value=proc) as run_mock:
            self.assertTrue(workiq.is_workiq_available())
        self.assertFalse(run_mock.call_args.kwargs["shell"])


class TestWorkIQMcpConfig(unittest.TestCase):
    def test_build_mcp_config_default(self) -> None:
        cfg = workiq.build_workiq_mcp_config()
        self.assertIn("_hve_workiq", cfg)
        self.assertEqual(cfg["_hve_workiq"]["command"], "npx")
        self.assertIn("tools", cfg["_hve_workiq"])
        self.assertNotIn("*", cfg["_hve_workiq"]["tools"])

    def test_build_mcp_config_with_tenant(self) -> None:
        cfg = workiq.build_workiq_mcp_config("tenant-123")
        self.assertIn("-t", cfg["_hve_workiq"]["args"])
        self.assertIn("tenant-123", cfg["_hve_workiq"]["args"])


class TestWorkIQSanitizeAndPrompt(unittest.TestCase):
    def test_sanitize_preserves_newline_tab_and_removes_control(self) -> None:
        src = "a\tb\nc\rd\x00\x1f\x1b[31me"
        out = workiq.sanitize_workiq_result(src)
        self.assertIn("\t", out)
        self.assertIn("\n", out)
        self.assertIn("\r", out)
        self.assertNotIn("\x00", out)
        self.assertNotIn("\x1f", out)
        self.assertNotIn("\x1b[31m", out)

    def test_enrich_prompt_empty_context_returns_original(self) -> None:
        original = "main prompt"
        self.assertEqual(workiq.enrich_prompt_with_workiq("", original), original)

    def test_enrich_prompt_injects_with_delimiter(self) -> None:
        original = "main prompt"
        enriched = workiq.enrich_prompt_with_workiq("context", original, context_type="QA")
        self.assertIn("<workiq_reference_data>", enriched)
        self.assertIn("context", enriched)
        self.assertTrue(enriched.endswith(original))

    def test_get_prompt_template_default_and_override(self) -> None:
        self.assertEqual(workiq.get_workiq_prompt_template("qa"), workiq.DEFAULT_WORKIQ_QA_PROMPT)
        self.assertEqual(workiq.get_workiq_prompt_template("km"), workiq.DEFAULT_WORKIQ_KM_PROMPT)
        self.assertEqual(workiq.get_workiq_prompt_template("review"), workiq.DEFAULT_WORKIQ_REVIEW_PROMPT)
        self.assertEqual(workiq.get_workiq_prompt_template("qa", "custom"), "custom")


class TestWorkIQSaveAndHeadless(unittest.TestCase):
    def test_save_result_empty_returns_none(self) -> None:
        self.assertIsNone(workiq.save_workiq_result("run", "1.1", "qa", ""))

    def test_save_result_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = workiq.save_workiq_result("run-1", "1.1", "qa", "hello", base_dir=td)
            self.assertIsNotNone(path)
            assert path is not None
            self.assertTrue(path.exists())
            text = path.read_text(encoding="utf-8")
            self.assertIn("Work IQ 調査結果", text)
            self.assertIn("hello", text)

    def test_save_result_truncates_large_output(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            big = "A" * 100_000
            path = workiq.save_workiq_result("run-1", "1.1", "qa", big, base_dir=td)
            self.assertIsNotNone(path)
            assert path is not None
            text = path.read_text(encoding="utf-8")
            self.assertIn("(中略: 全体 100,000 文字)", text)
            self.assertLess(len(text), 100_000)

    def test_headless_detection_ci(self) -> None:
        with mock.patch.dict(os.environ, {"CI": "true"}, clear=True):
            self.assertTrue(workiq._is_headless_environment())

    def test_headless_detection_ssh(self) -> None:
        with mock.patch.dict(os.environ, {"SSH_TTY": "/dev/pts/1"}, clear=True):
            self.assertTrue(workiq._is_headless_environment())

    def test_headless_detection_non_headless_with_display(self) -> None:
        with mock.patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True), \
                mock.patch("workiq.os.name", "posix"):
            self.assertFalse(workiq._is_headless_environment())

    def test_has_cached_token(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            (fake_home / ".workiq").mkdir()
            with mock.patch("workiq.Path.home", return_value=fake_home):
                self.assertTrue(workiq._has_cached_token())


class TestWorkIQErrorDetection(unittest.TestCase):
    def test_detects_error_response(self) -> None:
        text = "workiq ツールにアクセスできないため、実検索は実行できません。"
        self.assertTrue(workiq.is_workiq_error_response(text))

    def test_non_error_response_returns_false(self) -> None:
        text = "関連情報なし"
        self.assertFalse(workiq.is_workiq_error_response(text))

    def test_empty_string_returns_false(self) -> None:
        self.assertFalse(workiq.is_workiq_error_response(""))

    def test_error_words_with_data_indicators_returns_false(self) -> None:
        text = "アクセスできないと表示されたが、メール件名: 定例会議 と送信者: user@example.com"
        self.assertFalse(workiq.is_workiq_error_response(text))


class TestWorkIQDraftFunctions(unittest.TestCase):
    def test_format_workiq_draft_answers_with_results(self) -> None:
        questions = [{"no": 1, "question": "要件は？", "default": "A"}]
        results = {1: "メール件名: 要件確認"}
        out = workiq.format_workiq_draft_answers(questions, results)
        self.assertIn("Q1: 要件は？", out)
        self.assertIn("メール件名: 要件確認", out)
        self.assertIn("既定値候補: A", out)
        self.assertIn("人間がレビュー", out)

    def test_format_workiq_draft_answers_without_results(self) -> None:
        questions = [{"no": 2, "question": "期限は？", "default": "未定"}]
        out = workiq.format_workiq_draft_answers(questions, {})
        self.assertIn("Q2: 期限は？", out)
        self.assertIn("関連情報なし", out)
        self.assertIn("既定値候補: 未定", out)

    def test_format_workiq_draft_answers_empty_questions(self) -> None:
        out = workiq.format_workiq_draft_answers([], {})
        self.assertIn("対象質問", out)
        self.assertIn("- なし", out)

    def test_query_workiq_per_question_respects_limit_and_skips_failures(self) -> None:
        async def _run() -> None:
            with mock.patch.object(workiq, "query_workiq", side_effect=["res1", Exception("x"), "res3"]), \
                 mock.patch.object(workiq.asyncio, "sleep", new=mock.AsyncMock()):
                results = await workiq.query_workiq_per_question(
                    session=mock.Mock(),
                    questions=[(1, "Q1"), (2, "Q2"), (3, "Q3")],
                    prompt_template="質問:\n{target_content}",
                    timeout=1.0,
                    max_questions=2,
                )
            self.assertEqual(results, {1: "res1"})

        asyncio.run(_run())

    def test_query_workiq_per_question_waits_between_questions_even_on_failure(self) -> None:
        async def _run() -> None:
            sleep_mock = mock.AsyncMock()
            with mock.patch.object(workiq, "query_workiq", side_effect=[Exception("x"), "ok"]), \
                 mock.patch.object(workiq.asyncio, "sleep", new=sleep_mock):
                results = await workiq.query_workiq_per_question(
                    session=mock.Mock(),
                    questions=[(1, "Q1"), (2, "Q2")],
                    prompt_template="{target_content}",
                    timeout=1.0,
                    max_questions=2,
                )
            self.assertEqual(results, {2: "ok"})
            sleep_mock.assert_awaited_once()

        asyncio.run(_run())


class TestEnrichPromptGuard(unittest.TestCase):
    def test_rejects_error_response(self) -> None:
        original = "main prompt"
        context = "workiq ツールにアクセスできないため、実検索は実行できません。"
        self.assertEqual(workiq.enrich_prompt_with_workiq(context, original), original)

    def test_accepts_normal_response(self) -> None:
        original = "main prompt"
        context = "メール件名: 進捗報告"
        enriched = workiq.enrich_prompt_with_workiq(context, original)
        self.assertNotEqual(enriched, original)
        self.assertIn("メール件名", enriched)


class TestSaveWorkIQResultError(unittest.TestCase):
    def test_file_name_has_error_suffix_when_is_error_true(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = workiq.save_workiq_result("run-1", "1.1", "qa", "err", is_error=True, base_dir=td)
            self.assertIsNotNone(path)
            assert path is not None
            self.assertTrue(path.name.endswith("-ERROR.md"))
            text = path.read_text(encoding="utf-8")
            self.assertIn("⚠️ **STATUS: ERROR**", text)

    def test_file_name_has_no_error_suffix_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = workiq.save_workiq_result("run-1", "1.1", "qa", "ok", base_dir=td)
            self.assertIsNotNone(path)
            assert path is not None
            self.assertFalse(path.name.endswith("-ERROR.md"))


class TestWorkIQLogin(unittest.TestCase):
    def test_workiq_login_passes_shell_option(self) -> None:
        console = mock.Mock()
        run_results = [mock.Mock(returncode=0), mock.Mock(returncode=0)]
        with mock.patch("workiq._is_headless_environment", return_value=False), \
                mock.patch("workiq._SHELL_ON_WINDOWS", True), \
                mock.patch("workiq.subprocess.run", side_effect=run_results) as run_mock:
            self.assertTrue(workiq.workiq_login(console, timeout=10))

        self.assertEqual(run_mock.call_count, 2)
        self.assertTrue(run_mock.call_args_list[0].kwargs["shell"])
        self.assertTrue(run_mock.call_args_list[1].kwargs["shell"])


if __name__ == "__main__":
    unittest.main()
