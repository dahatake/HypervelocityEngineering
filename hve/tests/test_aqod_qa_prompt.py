"""test_aqod_qa_prompt.py — AQOD 専用 QA プロンプト・成果物検証・関連機能のテスト"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
import re
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from prompts import AQOD_QA_PROMPT, QA_APPLY_PROMPT, QA_PROMPT_V2


# ---------------------------------------------------------------------------
# 1. AQOD_QA_PROMPT 内容テスト
# ---------------------------------------------------------------------------

class TestAqodQaPrompt(unittest.TestCase):
    """AQOD_QA_PROMPT の内容検証。"""

    def test_aqod_qa_prompt_exists(self) -> None:
        self.assertIsInstance(AQOD_QA_PROMPT, str)
        self.assertTrue(AQOD_QA_PROMPT.strip())

    def test_aqod_qa_prompt_mentions_original_docs(self) -> None:
        self.assertIn("original-docs/", AQOD_QA_PROMPT)

    def test_aqod_qa_prompt_mentions_target_document(self) -> None:
        self.assertIn("対象ドキュメント", AQOD_QA_PROMPT)

    def test_aqod_qa_prompt_mentions_excerpt(self) -> None:
        self.assertIn("該当箇所", AQOD_QA_PROMPT)

    def test_aqod_qa_prompt_mentions_issue_type(self) -> None:
        self.assertIn("問題種別", AQOD_QA_PROMPT)

    def test_aqod_qa_prompt_mentions_severity(self) -> None:
        self.assertIn("重大度", AQOD_QA_PROMPT)

    def test_aqod_qa_prompt_no_fabrication(self) -> None:
        self.assertIn("捏造", AQOD_QA_PROMPT)

    def test_aqod_qa_prompt_prohibits_meta_questions(self) -> None:
        """AQOD_QA_PROMPT がメタ質問を明示的に禁止している。"""
        self.assertTrue(
            "禁止" in AQOD_QA_PROMPT or "生成しないこと" in AQOD_QA_PROMPT,
            "AQOD_QA_PROMPT should prohibit meta questions",
        )

    def test_aqod_qa_prompt_has_question_marker_format(self) -> None:
        self.assertIn("[Q", AQOD_QA_PROMPT)

    def test_aqod_qa_prompt_different_from_qa_prompt_v2(self) -> None:
        self.assertNotEqual(AQOD_QA_PROMPT, QA_PROMPT_V2)

    def test_aqod_qa_prompt_requires_body_output(self) -> None:
        """AQOD_QA_PROMPT が成果物サマリーだけで終えないよう指示している。"""
        self.assertIn("成果物サマリー", AQOD_QA_PROMPT)
        self.assertIn("直接出力", AQOD_QA_PROMPT)

    def test_qa_apply_prompt_preserves_aqod_body_format(self) -> None:
        """QA_APPLY_PROMPT が AQOD 本体成果物を [Qxx] 補助形式へ変換しないよう指示している。"""
        self.assertIn("# Original ドキュメント質問票", QA_APPLY_PROMPT)
        self.assertIn("### Qxx", QA_APPLY_PROMPT)
        self.assertIn("変換しない", QA_APPLY_PROMPT)


# ---------------------------------------------------------------------------
# 3. execution-qa-merged.md ファイル名テスト
# ---------------------------------------------------------------------------

class TestExecutionQaMergedFilename(unittest.TestCase):
    """Auto-QA マージファイルが execution-qa-merged.md になることを検証する。"""

    def _runner_src(self) -> str:
        runner_path = Path(__file__).parent.parent / "runner.py"
        return runner_path.read_text(encoding="utf-8")

    def test_execution_qa_merged_filename_in_runner(self) -> None:
        """runner.py に _EXECUTION_QA_MERGED_SUFFIX 定数と execution-qa-merged.md の記述が含まれる。"""
        content = self._runner_src()
        self.assertIn("execution-qa-merged.md", content)
        self.assertIn("_EXECUTION_QA_MERGED_SUFFIX", content)

    def test_old_qa_merged_not_used_as_file_path_stem(self) -> None:
        """runner.py で {step_id}-qa-merged.md（execution- なし）のパスが生成されない。"""
        content = self._runner_src()
        # execution-qa-merged.md は許可。qa-merged.md（ファイル名末尾）のみのパス生成を禁止。
        # パターン: }-qa-merged.md  （直前が } = step_id の置換末尾）
        old_pattern = re.search(r'\}-qa-merged\.md"', content)
        self.assertIsNone(
            old_pattern,
            "旧 -qa-merged.md のパス生成が残っています（execution-qa-merged.md を使うべき）",
        )


# ---------------------------------------------------------------------------
# 4. orchestrator が run_step に workflow_id を渡すテスト
# ---------------------------------------------------------------------------

class TestOrchestratorPassesWorkflowId(unittest.TestCase):
    """orchestrator.py が run_step に workflow_id を渡すことをソース検査で検証する。"""

    def _orchestrator_src(self) -> str:
        from orchestrator import run_workflow
        return inspect.getsource(run_workflow)

    def test_run_step_fn_passes_workflow_id(self) -> None:
        """run_step_fn が workflow_id を渡している。"""
        src = self._orchestrator_src()
        # orchestrator.py は workflow_id=workflow_id として渡す（wf.id と等価）
        self.assertTrue(
            "workflow_id=wf.id" in src or "workflow_id=workflow_id" in src,
            "run_step_fn should pass workflow_id to run_step",
        )

    def test_aqod_validation_in_orchestrator(self) -> None:
        """orchestrator.py に AQOD 成果物検証の呼び出しが含まれる。"""
        self.assertIn("validate_aqod_run", self._orchestrator_src())

    def test_aqod_validation_conditioned_on_workflow_id(self) -> None:
        """AQOD 成果物検証が workflow_id == 'aqod' 条件下にある。"""
        src = self._orchestrator_src()
        self.assertIn('workflow_id == "aqod"', src)

    def test_aqod_validation_result_in_return(self) -> None:
        """run_workflow の戻り値に aqod_validation が含まれる。"""
        src = self._orchestrator_src()
        self.assertIn("aqod_validation", src)

    def test_dry_run_returns_without_aqod_validation(self) -> None:
        """dry_run 時は aqod_validation が返されない（早期リターン）。"""
        from config import SDKConfig
        from orchestrator import run_workflow
        cfg = SDKConfig(dry_run=True)
        result = asyncio.run(run_workflow("aas", config=cfg))
        # dry_run は早期リターンするため aqod_validation を含まない
        self.assertNotIn("aqod_validation", result)


# ---------------------------------------------------------------------------
# 5. AQOD 成果物検証テスト
# ---------------------------------------------------------------------------

class TestArtifactValidation(unittest.TestCase):
    """artifact_validation.py の検証テスト。"""

    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.qa_dir = Path(self.td.name)

    def tearDown(self) -> None:
        self.td.cleanup()

    def _write(self, name: str, content: str) -> Path:
        p = self.qa_dir / name
        p.write_text(content, encoding="utf-8")
        return p

    def _valid_aqod_content(self) -> str:
        return (
            "# Original ドキュメント質問票\n\n"
            "対象スコープ: original-docs/\n\n"
            "## サマリー\n\n"
            "- 質問数: 1\n\n"
            "### Q01\n\n"
            "- 対象ドキュメント: original-docs/spec.md\n"
            "- 該当箇所: 「テスト箇所」\n"
            "- 問題種別: 矛盾\n"
            "- 重大度: major\n"
            "- 質問内容: この点について確認してください。\n"
            "- 未回答時の既定値候補: TBD\n"
            "- 既定値候補の理由: 不明\n"
            "- 未回答のまま進めた場合の影響: 設計に矛盾が残る\n"
        )

    def _auto_qa_helper_content(self) -> str:
        return (
            "[Q01]\n"
            "- 対象ドキュメント: original-docs/spec.md\n"
            "- 該当箇所: 「テスト箇所」\n"
            "- 問題種別: 不明瞭\n"
            "- 重大度: major\n"
            "- 質問内容: この点について確認してください。\n"
            "- 未回答時の既定値候補: TBD\n"
            "- 既定値候補の理由: 不明\n"
            "- 未回答のまま進めた場合の影響: 設計が未確定になる\n"
        )

    def test_valid_artifact_passes(self) -> None:
        """有効な QA-DocConsistency-*.md は PASS になる。"""
        from artifact_validation import validate_aqod_artifact
        p = self._write("QA-DocConsistency-20260101-120000.md", self._valid_aqod_content())
        result = validate_aqod_artifact(p)
        self.assertTrue(result["passed"], f"Should pass: errors={result['errors']}")

    def test_issue_filename_passes(self) -> None:
        """QA-DocConsistency-Issue-N.md 形式も PASS になる。"""
        from artifact_validation import validate_aqod_artifact
        p = self._write("QA-DocConsistency-Issue-123.md", self._valid_aqod_content())
        result = validate_aqod_artifact(p)
        self.assertTrue(result["passed"], f"Should pass: errors={result['errors']}")

    def test_execution_qa_merged_not_aqod_filename(self) -> None:
        """execution-qa-merged.md は AQOD 本体成果物ではない（ファイル名不一致）。"""
        from artifact_validation import is_aqod_artifact_filename
        self.assertFalse(is_aqod_artifact_filename("run-1-1.1-execution-qa-merged.md"))
        self.assertFalse(is_aqod_artifact_filename("20260427T040847-590ead-1-execution-qa-merged.md"))

    def test_qa_merged_not_aqod_filename(self) -> None:
        """旧 qa-merged.md も AQOD 本体成果物ではない。"""
        from artifact_validation import is_aqod_artifact_filename
        self.assertFalse(is_aqod_artifact_filename("run-1-1.1-qa-merged.md"))

    def test_missing_required_header_fails(self) -> None:
        """必須ヘッダーがない場合は FAIL になる。"""
        from artifact_validation import validate_aqod_artifact
        content = self._valid_aqod_content().replace("# Original ドキュメント質問票", "# 別のタイトル")
        p = self._write("QA-DocConsistency-20260101-120001.md", content)
        result = validate_aqod_artifact(p)
        self.assertFalse(result["passed"])

    def test_missing_question_fails(self) -> None:
        """質問ブロックがない場合は FAIL になる。"""
        from artifact_validation import validate_aqod_artifact
        content = self._valid_aqod_content().replace("### Q01", "## 見出し")
        p = self._write("QA-DocConsistency-20260101-120002.md", content)
        result = validate_aqod_artifact(p)
        self.assertFalse(result["passed"])

    def test_missing_required_fields_fails(self) -> None:
        """必須項目（問題種別など）がない場合は FAIL になる。"""
        from artifact_validation import validate_aqod_artifact
        content = self._valid_aqod_content().replace("- 問題種別: 矛盾\n", "")
        p = self._write("QA-DocConsistency-20260101-120003.md", content)
        result = validate_aqod_artifact(p)
        self.assertFalse(result["passed"])

    def test_validate_aqod_run_no_artifacts_fails(self) -> None:
        """qa/ に QA-DocConsistency-*.md がない場合は FAIL になる。"""
        from artifact_validation import validate_aqod_run
        self._write("run-1-1.1-execution-qa-merged.md", "補助 QA content")
        result = validate_aqod_run(qa_dir=self.qa_dir)
        self.assertEqual(result["overall"], "FAIL")
        self.assertFalse(result["aqod_validation"])

    def test_validate_aqod_run_with_valid_artifact_passes(self) -> None:
        """有効な QA-DocConsistency-*.md がある場合は PASS になる。"""
        from artifact_validation import validate_aqod_run
        self._write("QA-DocConsistency-20260101-120000.md", self._valid_aqod_content())
        result = validate_aqod_run(qa_dir=self.qa_dir)
        self.assertEqual(result["overall"], "PASS")
        self.assertTrue(result["aqod_validation"])

    def test_validate_aqod_run_returns_artifacts_found_count(self) -> None:
        """validate_aqod_run が見つかった成果物数を返す。"""
        from artifact_validation import validate_aqod_run
        self._write("QA-DocConsistency-20260101-120000.md", self._valid_aqod_content())
        self._write("QA-DocConsistency-Issue-42.md", self._valid_aqod_content())
        result = validate_aqod_run(qa_dir=self.qa_dir)
        self.assertEqual(result["artifacts_found"], 2)

    def test_direct_validation_skips_auto_qa_helper(self) -> None:
        """QA-DocConsistency 名でも [Qxx] 補助質問票は本体検証を skip する。"""
        from artifact_validation import validate_aqod_artifact
        p = self._write("QA-DocConsistency-20260101-120004.md", self._auto_qa_helper_content())
        result = validate_aqod_artifact(p)
        self.assertTrue(result["passed"], f"helper should not fail: {result['errors']}")
        self.assertTrue(result["skipped"])

    def test_validate_aqod_run_with_valid_and_helper_passes(self) -> None:
        """有効な本体 + 補助質問票の混在では補助を failed に含めない。"""
        from artifact_validation import validate_aqod_run
        self._write("QA-DocConsistency-20260101-120000.md", self._valid_aqod_content())
        self._write("QA-DocConsistency-20260101-120004.md", self._auto_qa_helper_content())
        result = validate_aqod_run(qa_dir=self.qa_dir)
        self.assertEqual(result["overall"], "PASS")
        self.assertEqual(result["artifacts_found"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["failed"], 0)

    def test_validate_aqod_run_only_helper_is_not_body_success(self) -> None:
        """補助質問票だけでは AQOD 本体成果物の成功扱いにしない。"""
        from artifact_validation import validate_aqod_run
        self._write("QA-DocConsistency-20260101-120004.md", self._auto_qa_helper_content())
        result = validate_aqod_run(qa_dir=self.qa_dir)
        self.assertEqual(result["overall"], "FAIL")
        self.assertFalse(result["aqod_validation"])
        self.assertEqual(result["artifacts_found"], 0)
        self.assertEqual(result["skipped"], 1)


# ---------------------------------------------------------------------------
# 6. Work IQ エラー応答のテスト
# ---------------------------------------------------------------------------

class TestWorkIqErrorHandling(unittest.TestCase):
    """Work IQ エラー応答が適切に処理されることを検証する。"""

    def test_is_workiq_error_response_detects_inaccessible(self) -> None:
        """'アクセスできない' を含むテキストは is_workiq_error_response で True になる。"""
        import workiq
        text = "workiq ツールにアクセスできないため、実検索は実行できません。"
        self.assertTrue(workiq.is_workiq_error_response(text))

    def test_is_workiq_error_response_detects_cannot_execute(self) -> None:
        """'実行できません' を含むテキストは is_workiq_error_response で True になる。"""
        import workiq
        text = "Work IQ の処理を実行できません。ツールが利用できません。"
        self.assertTrue(workiq.is_workiq_error_response(text))

    def test_is_workiq_error_response_false_for_normal_data(self) -> None:
        """正常データは is_workiq_error_response で False になる。"""
        import workiq
        text = "メール件名: 進捗報告\n送信日: 2026-01-01"
        self.assertFalse(workiq.is_workiq_error_response(text))

    def test_workiq_error_not_injected_into_prompt(self) -> None:
        """Work IQ エラー応答は enrich_prompt_with_workiq でプロンプトに注入されない。"""
        import workiq
        error_context = "workiq ツールにアクセスできないため、実検索は実行できません。"
        original = "original prompt"
        result = workiq.enrich_prompt_with_workiq(error_context, original)
        self.assertEqual(result, original)

    def test_workiq_error_saved_with_error_suffix(self) -> None:
        """Work IQ エラー応答は is_error=True で -ERROR.md サフィックス付きで保存される。"""
        import workiq
        with tempfile.TemporaryDirectory() as td:
            path = workiq.save_workiq_result(
                "run-1", "1.1", "qa-draft", "error text", is_error=True, base_dir=td
            )
            self.assertIsNotNone(path)
            assert path is not None
            self.assertIn("-ERROR", path.name)
            content = path.read_text(encoding="utf-8")
            self.assertIn("⚠️ **STATUS: ERROR**", content)

    def test_runner_uses_is_workiq_error_response_import(self) -> None:
        """runner.py が is_workiq_error_response をインポートしている。"""
        runner_path = Path(__file__).parent.parent / "runner.py"
        content = runner_path.read_text(encoding="utf-8")
        self.assertIn("is_workiq_error_response", content)

    def test_runner_filters_error_responses_before_merge(self) -> None:
        """runner.py が Work IQ エラー応答をマージ前にフィルタリングしている。"""
        runner_path = Path(__file__).parent.parent / "runner.py"
        content = runner_path.read_text(encoding="utf-8")
        # main の新実装では _clean_results で uninvestigated を除外している
        self.assertIn("_clean_results", content)
        self.assertIn("is_workiq_error_response", content)


if __name__ == "__main__":
    unittest.main()
