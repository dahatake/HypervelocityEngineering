"""ARD 固有の wizard / CLI / orchestrator 配線テスト (PR-4)。"""
from __future__ import annotations
import importlib.util as _ilu
import os
import sys
import unittest
from unittest import mock

# test_main.py と同じ importlib パターンで __main__.py を直接ロードする
# (__main__ は Python ランナーと名前が衝突するため)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
_main_path = os.path.join(os.path.dirname(__file__), "..", "__main__.py")
_spec = _ilu.spec_from_file_location("hve_main_ard", os.path.abspath(_main_path))
_main_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_main_mod)

_build_parser = _main_mod._build_parser
_build_params = _main_mod._build_params
_collect_ard_wizard_params = _main_mod._collect_ard_wizard_params
_ARD_DEFAULT_SURVEY_PERIOD_YEARS = _main_mod._ARD_DEFAULT_SURVEY_PERIOD_YEARS
_ARD_DEFAULT_TARGET_REGION = _main_mod._ARD_DEFAULT_TARGET_REGION
_ARD_DEFAULT_ANALYSIS_PURPOSE = _main_mod._ARD_DEFAULT_ANALYSIS_PURPOSE


class TestARDCLIArgs(unittest.TestCase):
    def test_company_name_arg(self):
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard", "--company-name", "株式会社サンプル", "--dry-run"
        ])
        self.assertEqual(args.company_name, "株式会社サンプル")

    def test_target_business_arg(self):
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard",
            "--company-name", "テスト", "--target-business", "ロイヤルティ事業", "--dry-run"
        ])
        self.assertEqual(args.target_business, "ロイヤルティ事業")

    def test_target_recommendation_id_arg(self):
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard",
            "--company-name", "テスト", "--target-recommendation-id", "SR-2", "--dry-run"
        ])
        params = _build_params(args)
        self.assertEqual(params.get("target_recommendation_id"), "SR-2")

    def test_company_name_required_in_build_params(self):
        parser = _build_parser()
        args = parser.parse_args(["orchestrate", "--workflow", "ard", "--dry-run"])
        with self.assertRaises(SystemExit):
            _build_params(args)

    def test_company_name_not_required_when_step_1_not_selected(self):
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard", "--steps", "2,3", "--dry-run"
        ])
        params = _build_params(args)
        self.assertEqual(params["company_name"], "")
        self.assertEqual(params["steps"], ["2", "3"])

    def test_build_params_ard_defaults(self):
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard",
            "--company-name", "テスト株式会社", "--dry-run"
        ])
        params = _build_params(args)
        self.assertEqual(params["company_name"], "テスト株式会社")
        self.assertEqual(params["target_business"], "")
        self.assertIn("survey_period_years", params)
        self.assertIn("target_region", params)
        self.assertIn("analysis_purpose", params)
        # target_business が空 → steps は 1,2,3
        self.assertEqual(params.get("steps"), ["1", "2", "3"])

    def test_build_params_ard_with_target_business(self):
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard",
            "--company-name", "テスト", "--target-business", "事業X", "--dry-run"
        ])
        params = _build_params(args)
        self.assertEqual(params.get("steps"), ["2", "3"])

    def test_build_params_ard_explicit_steps_not_overridden(self):
        """--steps 明示指定時は ARD の自動振り分けをせず、旧IDは互換変換する。"""
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard",
            "--company-name", "テスト", "--steps", "1.1", "--dry-run"
        ])
        params = _build_params(args)
        # --steps が明示された場合は自動振り分けせず、旧IDは新IDに変換する
        self.assertEqual(params.get("steps"), ["1"])

    def test_build_params_ard_explicit_legacy_combo_mapped(self):
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard",
            "--company-name", "テスト", "--steps", "1.1,2", "--dry-run"
        ])
        params = _build_params(args)
        self.assertEqual(params.get("steps"), ["1", "3"])

    def test_build_params_ard_explicit_invalid_step_raises(self):
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard",
            "--company-name", "テスト", "--steps", "999", "--dry-run"
        ])
        with self.assertRaises(SystemExit):
            _build_params(args)


class TestARDWizardParams(unittest.TestCase):
    def test_default_selection_is_step_2_3(self):
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = [1, 2]
        con.prompt_input.side_effect = [
            "",                  # company_name (Step 1 未選択なので未入力可)
            "ロイヤルティ事業",  # target_business
            "",                  # survey_base_date
            "",                  # survey_period_years
            "",                  # target_region
            "",                  # analysis_purpose
            "",                  # attached_docs
        ]
        params, selected_steps = _collect_ard_wizard_params(con, is_quick_auto=False)
        self.assertEqual(params["company_name"], "")
        self.assertEqual(params["target_business"], "ロイヤルティ事業")
        self.assertEqual(selected_steps, ["2", "3"])

    def test_step_1_selected_requires_company_name(self):
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = [0, 1, 2]
        con.prompt_input.side_effect = [
            "テスト株式会社",            # company_name
            "ロイヤルティ事業",           # target_business
            "", "", "", "", "",         # その他
        ]
        params, selected_steps = _collect_ard_wizard_params(con, is_quick_auto=False)
        first_required = con.prompt_input.call_args_list[0].kwargs.get("required")
        self.assertTrue(first_required)
        self.assertEqual(params["target_business"], "ロイヤルティ事業")
        self.assertEqual(selected_steps, ["1", "2", "3"])

    def test_quick_auto_uses_defaults(self):
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = [1, 2]
        con.prompt_input.side_effect = ["", "事業A"]
        params, selected_steps = _collect_ard_wizard_params(con, is_quick_auto=True)
        self.assertEqual(params["company_name"], "")
        self.assertEqual(params["target_business"], "事業A")
        self.assertEqual(params["survey_period_years"], _ARD_DEFAULT_SURVEY_PERIOD_YEARS)
        self.assertEqual(params["target_region"], _ARD_DEFAULT_TARGET_REGION)
        self.assertEqual(params["analysis_purpose"], _ARD_DEFAULT_ANALYSIS_PURPOSE)
        self.assertEqual(selected_steps, ["2", "3"])

    def test_survey_period_years_invalid_input_uses_default(self):
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = [1, 2]
        con.prompt_input.side_effect = [
            "",                  # company_name
            "ロイヤルティ事業",  # target_business
            "",                  # survey_base_date
            "not-a-number",      # survey_period_years (invalid)
            "",                  # target_region
            "",                  # analysis_purpose
            "",                  # attached_docs
        ]
        params, _ = _collect_ard_wizard_params(con, is_quick_auto=False)
        self.assertEqual(params["survey_period_years"], _ARD_DEFAULT_SURVEY_PERIOD_YEARS)

    def test_attached_docs_csv_parsing(self):
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = [1, 2]
        con.prompt_input.side_effect = [
            "",                          # company_name
            "ロイヤルティ事業",          # target_business
            "",                          # survey_base_date
            "",                          # survey_period_years
            "",                          # target_region
            "",                          # analysis_purpose
            "docs/a.pdf,docs/b.xlsx",    # attached_docs
        ]
        params, _ = _collect_ard_wizard_params(con, is_quick_auto=False)
        self.assertEqual(params["attached_docs"], ["docs/a.pdf", "docs/b.xlsx"])


class TestARDOrchestratorParams(unittest.TestCase):
    def test_collect_params_non_interactive_ard_defaults(self):
        from hve.orchestrator import _collect_params_non_interactive
        from hve.workflow_registry import get_workflow
        wf = get_workflow("ard")
        params = _collect_params_non_interactive(wf, {"company_name": "Co", "selected_steps": ["1", "3"]})
        self.assertEqual(params["company_name"], "Co")
        self.assertEqual(params["survey_period_years"], 30)
        self.assertEqual(params["target_region"], "グローバル全体")
        self.assertEqual(params["analysis_purpose"], "中長期成長戦略の立案")
        self.assertEqual(params["attached_docs"], [])
        self.assertFalse(params["ard_workiq_enabled"])
        # survey_base_date は today() のフォールバック
        self.assertRegex(params["survey_base_date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_collect_params_non_interactive_ard_custom_values(self):
        from hve.orchestrator import _collect_params_non_interactive
        from hve.workflow_registry import get_workflow
        wf = get_workflow("ard")
        params = _collect_params_non_interactive(wf, {
            "company_name": "テスト株式会社",
            "target_business": "事業A",
            "ard_workiq_enabled": True,
            "survey_base_date": "2026-01-01",
            "survey_period_years": 10,
            "target_region": "日本",
            "analysis_purpose": "コスト削減",
            "attached_docs": ["docs/a.pdf"],
        })
        self.assertEqual(params["company_name"], "テスト株式会社")
        self.assertEqual(params["target_business"], "事業A")
        self.assertEqual(params["survey_base_date"], "2026-01-01")
        self.assertEqual(params["survey_period_years"], 10)
        self.assertEqual(params["target_region"], "日本")
        self.assertEqual(params["analysis_purpose"], "コスト削減")
        self.assertEqual(params["attached_docs"], ["docs/a.pdf"])
        self.assertTrue(params["ard_workiq_enabled"])


class TestARDPromptConstant(unittest.TestCase):
    def test_workiq_usecase_prompt_exists(self):
        from hve.prompts import ARD_WORKIQ_USECASE_PROMPT
        self.assertIn("{business_requirement_content}", ARD_WORKIQ_USECASE_PROMPT)
        self.assertIn("{workiq_result}", ARD_WORKIQ_USECASE_PROMPT)
        self.assertIn("{company_name}", ARD_WORKIQ_USECASE_PROMPT)
        self.assertIn("docs/company-business-requirement.md", ARD_WORKIQ_USECASE_PROMPT)
        self.assertIn("docs/catalog/use-case-catalog.md", ARD_WORKIQ_USECASE_PROMPT)


class TestARDWorkflowRegistryBodyTemplatePaths(unittest.TestCase):
    def test_step_1_body_template_path(self):
        from hve.workflow_registry import get_workflow
        wf = get_workflow("ard")
        s = wf.get_step("1")
        self.assertEqual(s.body_template_path, "templates/ard/step-1.md")

    def test_step_2_body_template_path(self):
        from hve.workflow_registry import get_workflow
        wf = get_workflow("ard")
        s = wf.get_step("2")
        self.assertEqual(s.body_template_path, "templates/ard/step-2.md")

    def test_step_3_body_template_path(self):
        from hve.workflow_registry import get_workflow
        wf = get_workflow("ard")
        s = wf.get_step("3")
        self.assertEqual(s.body_template_path, "templates/ard/step-3.md")


if __name__ == "__main__":
    unittest.main()
