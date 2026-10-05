"""test_runner_pre_qa.py — Phase 0 (事前 QA) 実装の静的検証テスト"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qa_merger import QADocument, QAQuestion
import runner as runner_module


class TestRunnerPreQaSourceInspection(unittest.TestCase):
    """runner.py のソースコードを検査し、Phase 0 実装が含まれることを確認する。"""

    def _get_runner_source(self) -> str:
        runner_path = os.path.join(os.path.dirname(__file__), "..", "runner.py")
        with open(runner_path, encoding="utf-8") as f:
            return f.read()

    def test_pre_execution_qa_prompt_imported(self) -> None:
        src = self._get_runner_source()
        self.assertIn("PRE_EXECUTION_QA_PROMPT_V2", src)

    def test_run_pre_execution_qa_method_defined(self) -> None:
        src = self._get_runner_source()
        self.assertIn("_run_pre_execution_qa", src)

    def test_phase0_called_before_phase1(self) -> None:
        src = self._get_runner_source()
        idx_phase0 = src.find("await self._run_pre_execution_qa(")
        idx_phase1 = src.find('"メインタスク"')
        self.assertGreater(idx_phase0, 0, "_run_pre_execution_qa 呼び出しが見つかりません")
        self.assertGreater(idx_phase1, 0, "メインタスク phase start が見つかりません")
        self.assertLess(
            idx_phase0, idx_phase1,
            "Phase 0 (事前 QA) は Phase 1 (メインタスク) より前に配置されなければなりません"
        )

    def test_pre_execution_qa_suffix_constant_defined(self) -> None:
        src = self._get_runner_source()
        self.assertIn("_PRE_EXECUTION_QA_SUFFIX", src)
        self.assertIn("pre-execution-qa.md", src)

    def test_pre_qa_context_injected_into_main_prompt(self) -> None:
        src = self._get_runner_source()
        # FR-PROMPT-SRC-01: 見出し本文は .github/prompts/ が正本で、runner は参照だけを持つ。
        self.assertIn("runtime/runner/phase1-pre-qa-heading.prompt.md", src)
        self.assertIn("_injected_prompt", src)
        heading = (
            Path(__file__).resolve().parents[2]
            / ".github"
            / "prompts"
            / "runtime"
            / "runner"
            / "phase1-pre-qa-heading.prompt.md"
        )
        self.assertIn("事前確認済みの前提条件・補足情報", heading.read_text(encoding="utf-8"))

    def test_context_injection_uses_sdkconfig_limit(self) -> None:
        src = self._get_runner_source()
        self.assertIn("context_injection_max_chars", src)
        self.assertNotIn("_MAX_CONTEXT_INJECTION_LENGTH", src)


# ---------------------------------------------------------------------------
# FR-QA-03: 事前 QA 保存成功後の AKM dispatch hook
# ---------------------------------------------------------------------------

class TestPreQaAkmDispatch(unittest.TestCase):
    """FR-QA-03: 保存検証成功後のファイル単位 dispatch、0 問スキップ、AKM 再帰防止。

    production の dispatch hook（想定: _dispatch_qa_akm_sync 等）を
    fake/mock 経由で検証する動的テスト。
    """

    @staticmethod
    def _doc() -> QADocument:
        return QADocument(
            title="事前 QA",
            status="回答待ち",
            header_fields=[("状態", "回答待ち")],
            questions=[QAQuestion(no=1, question="方式は？", default_answer="A")],
        )

    def _call(self, *, workflow_id: str = "aas", dispatcher=None, doc=None):
        persist = getattr(runner_module, "_persist_answered_qa_and_dispatch")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "answered.md"
            content = persist(
                doc=doc if doc is not None else self._doc(),
                user_answers_raw="",
                use_defaults=True,
                output_path=path,
                workflow_id=workflow_id,
                dispatcher=dispatcher,
            )
            return content, path.exists()

    def test_dispatch_called_after_save_success(self) -> None:
        submitted: list[Path] = []
        content, exists = self._call(dispatcher=submitted.append)
        self.assertTrue(exists)
        self.assertIn("回答済み", content)
        self.assertEqual(len(submitted), 1)
        self.assertEqual(submitted[0].name, "answered.md")

    def test_dispatch_not_called_on_zero_questions(self) -> None:
        submitted: list[Path] = []
        content, exists = self._call(
            dispatcher=submitted.append,
            doc=QADocument(questions=[]),
        )
        self.assertEqual(content, "")
        self.assertFalse(exists)
        self.assertEqual(submitted, [])

    def test_dispatch_not_called_on_save_failure(self) -> None:
        submitted: list[Path] = []
        knowledge_files = runner_module.knowledge_files

        for error in (OSError("disk full"), knowledge_files.KnowledgeFileError("lock-timeout", "busy")):
            with self.subTest(error=type(error).__name__):
                with patch.object(knowledge_files, "save_qa_text", side_effect=error):
                    with self.assertRaises(RuntimeError):
                        self._call(dispatcher=submitted.append)
        self.assertEqual(submitted, [])

    def test_dispatch_returns_without_waiting_for_completion(self) -> None:
        class NonWaitingDispatcher:
            def __init__(self) -> None:
                self.paths: list[Path] = []

            def submit(self, path: Path) -> None:
                self.paths.append(path)

        dispatcher = NonWaitingDispatcher()
        content, _ = self._call(dispatcher=dispatcher.submit)
        self.assertTrue(content)
        self.assertEqual(len(dispatcher.paths), 1)

    def test_akm_workflow_does_not_dispatch(self) -> None:
        submitted: list[Path] = []
        content, exists = self._call(
            workflow_id="akm",
            dispatcher=submitted.append,
        )
        self.assertTrue(content)
        self.assertTrue(exists)
        self.assertEqual(submitted, [])


if __name__ == "__main__":
    unittest.main()
