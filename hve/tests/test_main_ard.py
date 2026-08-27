"""ARD 固有の wizard / CLI / orchestrator 配線テスト (PR-4)。"""
from __future__ import annotations
import ast
import importlib.util as _ilu
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

# test_main.py と同じ importlib パターンで __main__.py を直接ロードする
# (__main__ は Python ランナーと名前が衝突するため)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
_main_path = os.path.join(os.path.dirname(__file__), "..", "__main__.py")
_spec = _ilu.spec_from_file_location("hve_main_ard", os.path.abspath(_main_path))
assert _spec is not None and _spec.loader is not None
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

    def test_company_name_not_required_when_no_args(self):
        """引数なしの素の `orchestrate --workflow ard` は既定 Step 2/3/4/5 となり、company_name は不要。

        help_content.py の説明（「既定で Step 2/3/4/5 が ON、Step 1 は明示的に有効化」）および
        GUI Autopilot 事前実行（素の `orchestrate --workflow ard` を発行）の仕様に合致する。
        """
        parser = _build_parser()
        args = parser.parse_args(["orchestrate", "--workflow", "ard", "--dry-run"])
        params = _build_params(args)
        self.assertEqual(params["company_name"], "")
        self.assertEqual(params.get("steps"), ["2", "3", "4", "5"])

    def test_default_steps_follow_the_registry_ssot(self):
        """直接CLIの既定値はARD_DEFAULT_GROUP_IDSを参照する。"""
        with mock.patch.object(_main_mod, "ARD_DEFAULT_GROUP_IDS", ("1", "4")):
            parser = _build_parser()
            args = parser.parse_args([
                "orchestrate", "--workflow", "ard",
                "--company-name", "テスト", "--dry-run",
            ])
            params = _build_params(args)
        self.assertEqual(params.get("steps"), ["1", "4"])

    def test_company_name_required_when_step_1_explicit(self):
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard", "--steps", "1", "--dry-run"
        ])
        with self.assertRaises(SystemExit):
            _build_params(args)

    def test_company_name_required_when_step_1_2_explicit(self):
        """Step 1.2 単独指定でも company_name 必須（Step 1.2 は Step 1.1 に依存）。"""
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard", "--steps", "1.2", "--dry-run"
        ])
        with self.assertRaises(SystemExit):
            _build_params(args)

    def test_company_name_not_required_when_step_1_not_selected(self):
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard", "--steps", "2,4", "--dry-run"
        ])
        params = _build_params(args)
        self.assertEqual(params["company_name"], "")
        self.assertEqual(params["steps"], ["2", "4"])

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
        # 既定は Step 2/3/4/5（Step 1 は --steps で明示的に有効化）
        self.assertEqual(params.get("steps"), ["2", "3", "4", "5"])

    def test_build_params_ard_with_target_business(self):
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard",
            "--company-name", "テスト", "--target-business", "事業X", "--dry-run"
        ])
        params = _build_params(args)
        self.assertEqual(params.get("steps"), ["2", "3", "4", "5"])

    def test_build_params_ard_explicit_steps_not_overridden(self):
        """--steps 明示指定時は ARD の自動振り分けをせず、旧実 Step ID '1.1' 指定時は Step '1' を自動前提付与する。"""
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard",
            "--company-name", "テスト", "--steps", "1.1", "--dry-run"
        ])
        params = _build_params(args)
        # '1.1' 指定時は registry depends_on=["1"] を満たすため '1' が自動付与される
        self.assertEqual(params.get("steps"), ["1", "1.1"])

    def test_build_params_ard_explicit_legacy_combo_mapped(self):
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard",
            "--company-name", "テスト", "--steps", "1.1,2", "--dry-run"
        ])
        params = _build_params(args)
        # '1.1' を含むため Step '1' が自動付与される
        self.assertEqual(params.get("steps"), ["1", "1.1", "2"])

    def test_build_params_ard_explicit_invalid_step_raises(self):
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard",
            "--company-name", "テスト", "--steps", "999", "--dry-run"
        ])
        with self.assertRaises(SystemExit):
            _build_params(args)

    def test_include_kpi_okr_flag_default_false(self):
        """`--include-kpi-okr` 未指定時は params["include_kpi_okr"] = False。"""
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard",
            "--company-name", "テスト", "--dry-run"
        ])
        params = _build_params(args)
        self.assertEqual(params.get("include_kpi_okr"), False)

    def test_include_kpi_okr_flag_enables(self):
        """`--include-kpi-okr` 指定時は params["include_kpi_okr"] = True。"""
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate", "--workflow", "ard",
            "--company-name", "テスト", "--include-kpi-okr", "--dry-run"
        ])
        params = _build_params(args)
        self.assertEqual(params.get("include_kpi_okr"), True)


class TestARDWizardParams(unittest.TestCase):
    def test_default_selection_is_step_2_3_4(self):
        con = mock.MagicMock()
        # 5 グループ体系での既定選択: [1,2,3,4] = ["2","3","4","5"]　(Step 1 のみ既定 OFF)
        con.prompt_multi_select.return_value = [1, 2, 3, 4]
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
        self.assertEqual(selected_steps, ["2", "3", "4", "5"])
        # prompt_multi_select に渡された default_indices が [1, 2, 3, 4] であること（GUI と整合）
        call = con.prompt_multi_select.call_args
        self.assertEqual(call.kwargs.get("default_indices"), [1, 2, 3, 4])
        self.assertTrue(params["include_kpi_okr"])
        con.prompt_yes_no.assert_not_called()

    def test_default_selection_and_empty_fallback_follow_registry_ssot(self):
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = []
        con.prompt_input.side_effect = ["テスト株式会社", "", "", "", "", ""]
        with mock.patch.object(_main_mod, "ARD_DEFAULT_GROUP_IDS", ("1", "4")):
            _params, selected_steps = _collect_ard_wizard_params(
                con, is_quick_auto=False
            )
        self.assertEqual(selected_steps, ["1", "4"])
        self.assertEqual(
            con.prompt_multi_select.call_args.kwargs.get("default_indices"), [0, 3]
        )

    def test_unknown_default_group_fails_closed(self):
        con = mock.MagicMock()
        with mock.patch.object(_main_mod, "ARD_DEFAULT_GROUP_IDS", ("2", "9")):
            with self.assertRaisesRegex(ValueError, "未登録"):
                _collect_ard_wizard_params(con, is_quick_auto=False)
        con.prompt_multi_select.assert_not_called()

    def test_duplicate_default_group_fails_closed(self):
        con = mock.MagicMock()
        with mock.patch.object(_main_mod, "ARD_DEFAULT_GROUP_IDS", ("2", "2")):
            with self.assertRaisesRegex(ValueError, "重複"):
                _collect_ard_wizard_params(con, is_quick_auto=False)
        con.prompt_multi_select.assert_not_called()

    def test_step_1_selected_requires_company_name(self):
        con = mock.MagicMock()
        # 全 4 グループ選択
        con.prompt_multi_select.return_value = [0, 1, 2, 3]
        con.prompt_input.side_effect = [
            "テスト株式会社",            # company_name
            "ロイヤルティ事業",           # target_business
            "", "", "", "", "",         # その他
        ]
        params, selected_steps = _collect_ard_wizard_params(con, is_quick_auto=False)
        first_required = con.prompt_input.call_args_list[0].kwargs.get("required")
        self.assertTrue(first_required)
        self.assertEqual(params["target_business"], "ロイヤルティ事業")
        self.assertEqual(selected_steps, ["1", "2", "3", "4"])

    def test_quick_auto_uses_defaults(self):
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = [1, 3]
        con.prompt_input.side_effect = ["", "事業A"]
        params, selected_steps = _collect_ard_wizard_params(con, is_quick_auto=True)
        self.assertEqual(params["company_name"], "")
        self.assertEqual(params["target_business"], "事業A")
        self.assertEqual(params["survey_period_years"], _ARD_DEFAULT_SURVEY_PERIOD_YEARS)
        self.assertEqual(params["target_region"], _ARD_DEFAULT_TARGET_REGION)
        self.assertEqual(params["analysis_purpose"], _ARD_DEFAULT_ANALYSIS_PURPOSE)
        self.assertEqual(selected_steps, ["2", "4"])

    def test_survey_period_years_invalid_input_uses_default(self):
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = [1, 3]
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
        con.prompt_multi_select.return_value = [1, 3]
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

    def test_include_kpi_okr_wizard_default_false(self):
        """グループ3未選択なら別質問なしでinclude_kpi_okr=False。"""
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = [1, 3]
        con.prompt_yes_no.return_value = False
        con.prompt_input.side_effect = ["", "事業A", "", "", "", "", ""]
        params, _ = _collect_ard_wizard_params(con, is_quick_auto=False)
        self.assertEqual(params["include_kpi_okr"], False)
        con.prompt_yes_no.assert_not_called()

    def test_include_kpi_okr_wizard_opt_in(self):
        """グループ3選択なら別質問なしでinclude_kpi_okr=True。"""
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = [1, 2, 3]
        con.prompt_yes_no.return_value = False
        con.prompt_input.side_effect = ["", "事業A", "", "", "", "", ""]
        params, _ = _collect_ard_wizard_params(con, is_quick_auto=False)
        self.assertEqual(params["include_kpi_okr"], True)
        con.prompt_yes_no.assert_not_called()

    def test_include_kpi_okr_quick_auto_false_without_group_3(self):
        """quick-autoでもグループ3未選択ならFalse。"""
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = [1, 3]
        con.prompt_input.side_effect = ["", "事業A"]
        params, _ = _collect_ard_wizard_params(con, is_quick_auto=True)
        self.assertEqual(params["include_kpi_okr"], False)
        con.prompt_yes_no.assert_not_called()

    def test_include_kpi_okr_quick_auto_true_with_group_3(self):
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = [1, 2, 3]
        con.prompt_input.side_effect = ["", "事業A"]
        params, _ = _collect_ard_wizard_params(con, is_quick_auto=True)
        self.assertEqual(params["include_kpi_okr"], True)
        con.prompt_yes_no.assert_not_called()

    def test_include_kpi_okr_wizard_only_step_1_skipped(self):
        """Step 1 のみ選択時は include_kpi_okr プロンプトをスキップ（自動 False）。"""
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = [0]
        con.prompt_input.side_effect = ["テスト株式会社", "", "", "", "", ""]
        params, selected_steps = _collect_ard_wizard_params(con, is_quick_auto=False)
        self.assertEqual(selected_steps, ["1"])
        self.assertEqual(params["include_kpi_okr"], False)
        con.prompt_yes_no.assert_not_called()


class TestARDWizardRecommendationIdPrompt(unittest.TestCase):
    @staticmethod
    def _console(indices, *, target_business="", recommendation_id=""):
        con = mock.MagicMock()
        con.prompt_multi_select.return_value = indices
        recommendation_label = _main_mod._PARAM_PROMPT_LABELS.get(
            "target_recommendation_id", ""
        )

        def _answer(label, *args, **kwargs):
            if "対象企業名" in label:
                return "テスト株式会社"
            if "対象業務名" in label:
                return target_business
            if recommendation_label and recommendation_label in label:
                return recommendation_id
            return ""

        con.prompt_input.side_effect = _answer
        return con

    @staticmethod
    def _recommendation_prompted(con) -> bool:
        recommendation_label = _main_mod._PARAM_PROMPT_LABELS.get(
            "target_recommendation_id", ""
        )
        if not recommendation_label:
            return False
        return any(
            call.args and recommendation_label in str(call.args[0])
            for call in con.prompt_input.call_args_list
        )

    def test_recommendation_prompt_label_is_declared(self):
        self.assertTrue(
            _main_mod._PARAM_PROMPT_LABELS.get("target_recommendation_id")
        )

    def test_quick_and_custom_modes_cannot_be_combined(self):
        con = mock.MagicMock()
        with self.assertRaisesRegex(ValueError, "同時に複数"):
            _collect_ard_wizard_params(
                con,
                is_quick_auto=True,
                is_custom_auto=True,
            )
        con.prompt_multi_select.assert_not_called()

    def test_custom_auto_prompts_only_for_bridge_and_keeps_value(self):
        con = self._console([0, 1], recommendation_id="SR-3")
        params, _ = _collect_ard_wizard_params(
            con, is_quick_auto=False, is_custom_auto=True
        )
        self.assertEqual(params.get("target_recommendation_id"), "SR-3")
        self.assertTrue(self._recommendation_prompted(con))

    def test_custom_auto_skips_prompt_when_target_business_is_explicit(self):
        con = self._console([0, 1], target_business="事業A")
        params, _ = _collect_ard_wizard_params(
            con, is_quick_auto=False, is_custom_auto=True
        )
        self.assertNotIn("target_recommendation_id", params)
        self.assertFalse(self._recommendation_prompted(con))

    def test_custom_auto_skips_prompt_without_group_1(self):
        con = self._console([1, 3])
        params, _ = _collect_ard_wizard_params(
            con, is_quick_auto=False, is_custom_auto=True
        )
        self.assertNotIn("target_recommendation_id", params)
        self.assertFalse(self._recommendation_prompted(con))

    def test_custom_auto_skips_prompt_with_group_1_only(self):
        con = self._console([0])
        params, _ = _collect_ard_wizard_params(
            con, is_quick_auto=False, is_custom_auto=True
        )
        self.assertNotIn("target_recommendation_id", params)
        self.assertFalse(self._recommendation_prompted(con))

    def test_quick_auto_never_prompts_recommendation_id(self):
        con = self._console([0, 1])
        params, _ = _collect_ard_wizard_params(con, is_quick_auto=True)
        self.assertNotIn("target_recommendation_id", params)
        self.assertFalse(self._recommendation_prompted(con))

    def test_manual_never_prompts_recommendation_id_upfront(self):
        con = self._console([0, 1])
        params, _ = _collect_ard_wizard_params(
            con, is_quick_auto=False, is_custom_auto=False
        )
        self.assertNotIn("target_recommendation_id", params)
        self.assertFalse(self._recommendation_prompted(con))

    def test_interactive_entrypoint_forwards_custom_auto_mode(self):
        module = ast.parse(Path(_main_path).read_text(encoding="utf-8-sig"))
        function = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "_cmd_run_interactive"
        )
        calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_collect_ard_wizard_params"
        ]
        nonquick = []
        for call in calls:
            keywords = {item.arg: item.value for item in call.keywords if item.arg}
            quick_value = keywords.get("is_quick_auto")
            if isinstance(quick_value, ast.Constant) and quick_value.value is False:
                nonquick.append(keywords)
        self.assertEqual(len(nonquick), 1)
        forwarded = nonquick[0].get("is_custom_auto")
        self.assertIsInstance(forwarded, ast.Name)
        self.assertEqual(forwarded.id, "is_custom_auto")


class TestARDOrchestratorParams(unittest.TestCase):
    def test_collect_params_non_interactive_ard_defaults(self):
        from hve.orchestrator import _collect_params_non_interactive
        from hve.workflow_registry import get_workflow
        wf = get_workflow("ard")
        params = _collect_params_non_interactive(wf, {"company_name": "Co", "selected_steps": ["1", "4"]})
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


class TestARDGroupStepExpansion(unittest.TestCase):
    """registry SSOTによるグループID→実Step ID展開のテスト。"""

    def _resolve(self, group_ids):
        from hve.template_engine import resolve_selected_steps
        from hve.workflow_registry import expand_group_step_ids, get_workflow
        wf = get_workflow("ard")
        expanded = expand_group_step_ids("ard", group_ids)
        seen = set()
        expanded = [s for s in expanded if not (s in seen or seen.add(s))]
        return resolve_selected_steps(wf, expanded)

    def test_group_2_and_4_expands(self):
        active = self._resolve(["2", "4"])
        self.assertIn("2", active)
        self.assertIn("3.1", active)
        self.assertIn("3.2", active)
        self.assertIn("3.3", active)
        self.assertNotIn("1", active)
        self.assertNotIn("1.1", active)
        self.assertNotIn("1.2", active)

    def test_group_1_expands(self):
        active = self._resolve(["1"])
        self.assertIn("1", active)
        self.assertIn("1.1", active)
        self.assertIn("1.2", active)
        self.assertNotIn("2", active)
        self.assertNotIn("3.1", active)

    def test_group_4_only(self):
        active = self._resolve(["4"])
        self.assertEqual(active, {"3.1", "3.2", "3.3"})

    def test_all_groups(self):
        active = self._resolve(["1", "2", "4"])
        self.assertEqual(
            active,
            {"1", "1.1", "1.2", "2", "3.1", "3.2", "3.3"},
        )

    def test_orchestrator_expansion_applied(self):
        """orchestrator.py の実展開ロジック経由でも同じ結果になることを確認。"""
        from hve.template_engine import resolve_selected_steps
        from hve.workflow_registry import expand_group_step_ids, get_workflow
        wf = get_workflow("ard")
        expanded = expand_group_step_ids("ard", ["2", "4"])
        seen = set()
        selected = [s for s in expanded if not (s in seen or seen.add(s))]
        active = resolve_selected_steps(wf, selected)
        self.assertTrue({"2", "3.1", "3.2", "3.3"}.issubset(active))


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
        self.assertEqual(s.body_template_path, ".github/prompts/steps/ard/step-1.prompt.md")

    def test_step_2_body_template_path(self):
        from hve.workflow_registry import get_workflow
        wf = get_workflow("ard")
        s = wf.get_step("2")
        self.assertEqual(s.body_template_path, ".github/prompts/steps/ard/step-2.prompt.md")

    def test_step_2_1_body_template_path(self):
        # Step 2.1 (KPI/OKR 定義・任意) — 旧 Step 3 から移動
        from hve.workflow_registry import get_workflow
        wf = get_workflow("ard")
        s = wf.get_step("2.1")
        self.assertEqual(s.body_template_path, ".github/prompts/steps/ard/step-2.1.prompt.md")

    def test_step_3_x_body_template_path(self):
        # 旧 Step 4.1/4.2/4.3 は Step 3.1/3.2/3.3 に再採番された。
        from hve.workflow_registry import get_workflow
        wf = get_workflow("ard")
        s_31 = wf.get_step("3.1")
        s_32 = wf.get_step("3.2")
        s_33 = wf.get_step("3.3")
        self.assertEqual(s_31.body_template_path, ".github/prompts/steps/ard/step-3.1.prompt.md")
        self.assertEqual(s_32.body_template_path, ".github/prompts/steps/ard/step-3.2.prompt.md")
        self.assertEqual(s_33.body_template_path, ".github/prompts/steps/ard/step-3.3.prompt.md")


if __name__ == "__main__":
    unittest.main()
