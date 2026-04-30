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


class TestQaPhaseConfig(unittest.TestCase):
    """SDKConfig.qa_phase フィールドの検証。"""

    def test_qa_phase_default_is_pre(self) -> None:
        cfg = SDKConfig()
        self.assertEqual(cfg.qa_phase, "pre")

    def test_qa_phase_accepts_post(self) -> None:
        cfg = SDKConfig(qa_phase="post")
        self.assertEqual(cfg.qa_phase, "post")

    def test_qa_phase_accepts_both(self) -> None:
        cfg = SDKConfig(qa_phase="both")
        self.assertEqual(cfg.qa_phase, "both")

    def test_qa_phase_from_env_pre(self) -> None:
        import os
        original = os.environ.get("HVE_QA_PHASE")
        try:
            os.environ["HVE_QA_PHASE"] = "pre"
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.qa_phase, "pre")
        finally:
            if original is None:
                os.environ.pop("HVE_QA_PHASE", None)
            else:
                os.environ["HVE_QA_PHASE"] = original

    def test_qa_phase_from_env_post(self) -> None:
        import os
        original = os.environ.get("HVE_QA_PHASE")
        try:
            os.environ["HVE_QA_PHASE"] = "post"
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.qa_phase, "post")
        finally:
            if original is None:
                os.environ.pop("HVE_QA_PHASE", None)
            else:
                os.environ["HVE_QA_PHASE"] = original

    def test_qa_phase_from_env_invalid_falls_back_to_pre(self) -> None:
        import os
        original = os.environ.get("HVE_QA_PHASE")
        try:
            os.environ["HVE_QA_PHASE"] = "invalid"
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.qa_phase, "pre")
        finally:
            if original is None:
                os.environ.pop("HVE_QA_PHASE", None)
            else:
                os.environ["HVE_QA_PHASE"] = original


if __name__ == "__main__":
    unittest.main()
