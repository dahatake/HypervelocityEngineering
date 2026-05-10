"""ARD Step 2: target_business 説明文生成プロンプト定数のテスト（PR#6）。"""
from __future__ import annotations
import unittest


class TestARDTargetBusinessPrompt(unittest.TestCase):
    def test_constant_exists(self):
        from hve.prompts import ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT
        self.assertIsInstance(ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT, str)
        self.assertGreater(len(ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT), 200)

    def test_required_placeholders_exist(self):
        from hve.prompts import ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT
        for ph in (
            "{company_name}",
            "{selected_recommendation_id}",
            "{selected_recommendation_title}",
            "{business_requirement_content}",
        ):
            self.assertIn(
                ph,
                ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT,
                f"プレースホルダ {ph} が定義されていません",
            )

    def test_format_with_all_placeholders(self):
        from hve.prompts import ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT
        rendered = ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT.format(
            company_name="テスト株式会社",
            selected_recommendation_id="SR-1",
            selected_recommendation_title="顧客データプラットフォーム構築とAI活用推進",
            business_requirement_content="（事業分析レポート本文）",
        )
        # format により全プレースホルダが解決され、{ } が残らないこと
        self.assertNotIn("{company_name}", rendered)
        self.assertNotIn("{selected_recommendation_id}", rendered)
        self.assertNotIn("{selected_recommendation_title}", rendered)
        self.assertNotIn("{business_requirement_content}", rendered)
        # 対象企業名・SR-ID が本文中に展開されていること
        self.assertIn("テスト株式会社", rendered)
        self.assertIn("SR-1", rendered)
        self.assertIn("顧客データプラットフォーム構築とAI活用推進", rendered)

    def test_anti_hallucination_clauses_present(self):
        """捏造禁止の文言が含まれていることを確認する。"""
        from hve.prompts import ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT
        # 「捏造」「創作しない」「断定しない」のいずれかが含まれていること
        text = ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT
        self.assertTrue(
            ("捏造" in text) or ("創作しない" in text) or ("断定しない" in text),
            "捏造禁止に関する文言が含まれていません",
        )

    def test_step2_intent_documented(self):
        """target_business / Step 2 / Targeted いずれかへの言及がある（用途明示）。"""
        from hve.prompts import ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT
        text = ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT
        self.assertTrue(
            ("target_business" in text)
            or ("Targeted" in text)
            or ("Step 2" in text)
            or ("対象業務" in text),
            "Step 2 / target_business / 対象業務 への言及がありません",
        )

    def test_no_extra_unintended_placeholders(self):
        """予期しない `{xxx}` プレースホルダが残っていないこと（タイポ検出）。"""
        from hve.prompts import ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT
        rendered = ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT.format(
            company_name="X",
            selected_recommendation_id="SR-1",
            selected_recommendation_title="T",
            business_requirement_content="C",
        )
        import re
        # format 後に `{xxx}` パターンが残っていないこと（=未定義のプレースホルダがない）
        remaining = re.findall(r"\{[^{}]+\}", rendered)
        self.assertEqual(
            remaining,
            [],
            f"未定義のプレースホルダが残っています: {remaining}",
        )


if __name__ == "__main__":
    unittest.main()
