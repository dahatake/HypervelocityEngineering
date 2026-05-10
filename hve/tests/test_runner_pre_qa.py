"""test_runner_pre_qa.py — Phase 0 (事前 QA) 実装の静的検証テスト"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig


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
        self.assertIn("事前確認済みの前提条件・補足情報", src)
        self.assertIn("_injected_prompt", src)

    def test_context_injection_uses_sdkconfig_limit(self) -> None:
        src = self._get_runner_source()
        self.assertIn("context_injection_max_chars", src)
        self.assertNotIn("_MAX_CONTEXT_INJECTION_LENGTH", src)


if __name__ == "__main__":
    unittest.main()

