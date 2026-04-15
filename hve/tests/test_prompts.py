"""test_prompts.py — プロンプト定数が空でないことのテスト"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from prompts import QA_PROMPT, QA_APPLY_PROMPT, REVIEW_PROMPT, CODE_REVIEW_AGENT_FIX_PROMPT, ADVERSARIAL_RECHECK_PROMPT, QA_PROMPT_V2


class TestPromptsNotEmpty(unittest.TestCase):
    """プロンプト定数が文字列であり、空でないことを検証する。"""

    def test_qa_prompt_is_str(self) -> None:
        self.assertIsInstance(QA_PROMPT, str)

    def test_qa_prompt_not_empty(self) -> None:
        self.assertTrue(QA_PROMPT.strip(), "QA_PROMPT should not be empty")

    def test_qa_apply_prompt_is_str(self) -> None:
        self.assertIsInstance(QA_APPLY_PROMPT, str)

    def test_qa_apply_prompt_not_empty(self) -> None:
        self.assertTrue(QA_APPLY_PROMPT.strip(), "QA_APPLY_PROMPT should not be empty")

    def test_review_prompt_is_str(self) -> None:
        self.assertIsInstance(REVIEW_PROMPT, str)

    def test_review_prompt_not_empty(self) -> None:
        self.assertTrue(REVIEW_PROMPT.strip(), "REVIEW_PROMPT should not be empty")

    def test_qa_apply_prompt_has_placeholder(self) -> None:
        """QA_APPLY_PROMPT には {user_answers} プレースホルダーが含まれる。"""
        self.assertIn("{user_answers}", QA_APPLY_PROMPT)

    def test_qa_prompt_mentions_selection_or_priority(self) -> None:
        """QA_PROMPT には選択式または重要度に関する記述が含まれる。"""
        self.assertTrue(
            "選択" in QA_PROMPT or "重要度" in QA_PROMPT,
            "QA_PROMPT should mention selection or priority",
        )

    def test_review_prompt_mentions_adversarial_review(self) -> None:
        """REVIEW_PROMPT には敵対的レビューの5軸検証に関する記述が含まれる。"""
        self.assertIn("敵対的レビュアー", REVIEW_PROMPT)
        self.assertIn("要件充足性", REVIEW_PROMPT)
        self.assertIn("合格判定", REVIEW_PROMPT)


class TestCodeReviewAgentFixPrompt(unittest.TestCase):
    """CODE_REVIEW_AGENT_FIX_PROMPT の検証。"""

    def test_code_review_agent_fix_prompt_is_str(self) -> None:
        self.assertIsInstance(CODE_REVIEW_AGENT_FIX_PROMPT, str)

    def test_code_review_agent_fix_prompt_not_empty(self) -> None:
        self.assertTrue(CODE_REVIEW_AGENT_FIX_PROMPT.strip(), "CODE_REVIEW_AGENT_FIX_PROMPT should not be empty")

    def test_code_review_agent_fix_prompt_has_placeholder(self) -> None:
        """{review_comments} プレースホルダーが含まれることを確認。"""
        self.assertIn("{review_comments}", CODE_REVIEW_AGENT_FIX_PROMPT)


class TestAdversarialRecheckPrompt(unittest.TestCase):
    """ADVERSARIAL_RECHECK_PROMPT の検証。"""

    def test_adversarial_recheck_prompt_is_str(self) -> None:
        self.assertIsInstance(ADVERSARIAL_RECHECK_PROMPT, str)

    def test_adversarial_recheck_prompt_not_empty(self) -> None:
        self.assertTrue(ADVERSARIAL_RECHECK_PROMPT.strip(), "ADVERSARIAL_RECHECK_PROMPT should not be empty")

    def test_adversarial_recheck_prompt_has_cycle_placeholder(self) -> None:
        """{cycle} プレースホルダーが含まれることを確認。"""
        self.assertIn("{cycle}", ADVERSARIAL_RECHECK_PROMPT)


class TestQaPromptV2(unittest.TestCase):
    """QA_PROMPT_V2 の検証。"""

    def test_qa_prompt_v2_is_str(self) -> None:
        self.assertIsInstance(QA_PROMPT_V2, str)

    def test_qa_prompt_v2_not_empty(self) -> None:
        self.assertTrue(QA_PROMPT_V2.strip(), "QA_PROMPT_V2 should not be empty")

    def test_qa_prompt_v2_mentions_priority(self) -> None:
        """QA_PROMPT_V2 には重要度の記述が含まれる。"""
        self.assertIn("重要度", QA_PROMPT_V2)

    def test_qa_prompt_v2_mentions_default_candidate(self) -> None:
        """QA_PROMPT_V2 には既定値候補の記述が含まれる。"""
        self.assertIn("既定値候補", QA_PROMPT_V2)

    def test_qa_prompt_v2_mentions_category(self) -> None:
        """QA_PROMPT_V2 には分類項目の記述が含まれる。"""
        self.assertIn("分類項目", QA_PROMPT_V2)

    def test_qa_prompt_v2_no_fabrication(self) -> None:
        """QA_PROMPT_V2 には捏造禁止の記述が含まれる。"""
        self.assertIn("捏造", QA_PROMPT_V2)

    def test_qa_prompt_v2_alpha_labels(self) -> None:
        """QA_PROMPT_V2 にはアルファベットラベル (A. または A/B/C) の記述が含まれる。"""
        self.assertTrue(
            "A." in QA_PROMPT_V2 or "A/B/C" in QA_PROMPT_V2,
            "QA_PROMPT_V2 should mention alphabetic labels (A. or A/B/C)",
        )


if __name__ == "__main__":
    unittest.main()
