"""ARD ワークフロー登録の単体テスト (PR-1 範囲)。"""
from __future__ import annotations

import unittest

try:
    from hve.workflow_registry import (
        get_workflow,
        get_root_steps,
        get_next_steps,
        list_workflows,
    )
except ImportError:  # flat import fallback
    from workflow_registry import (  # type: ignore[no-redef]
        get_workflow,
        get_root_steps,
        get_next_steps,
        list_workflows,
    )

try:
    from hve.template_engine import _WORKFLOW_DISPLAY_NAMES, _WORKFLOW_PREFIX
except ImportError:
    from template_engine import _WORKFLOW_DISPLAY_NAMES, _WORKFLOW_PREFIX  # type: ignore[no-redef]


class TestARDWorkflowRegistration(unittest.TestCase):
    def test_workflow_is_registered(self):
        wf = get_workflow("ard")
        self.assertIsNotNone(wf)
        self.assertEqual(wf.id, "ard")
        self.assertEqual(wf.name, "Auto Requirement Definition")
        self.assertEqual(wf.label_prefix, "ard")

    def test_state_labels(self):
        wf = get_workflow("ard")
        self.assertEqual(wf.state_labels, {
            "initialized": "ard:initialized",
            "ready": "ard:ready",
            "running": "ard:running",
            "done": "ard:done",
            "blocked": "ard:blocked",
        })

    def test_params_list(self):
        wf = get_workflow("ard")
        self.assertEqual(wf.params, [
            "company_name",
            "target_business",
            "survey_base_date",
            "survey_period_years",
            "target_region",
            "analysis_purpose",
            "attached_docs",
        ])

    def test_steps_ids(self):
        wf = get_workflow("ard")
        ids = [s.id for s in wf.steps]
        self.assertEqual(ids, ["1", "2", "3"])

    def test_step_1_definition(self):
        wf = get_workflow("ard")
        s = wf.get_step("1")
        self.assertIsNotNone(s)
        self.assertEqual(s.custom_agent, "Arch-ARD-BusinessAnalysis-Untargeted")
        self.assertEqual(s.depends_on, [])
        self.assertEqual(s.output_paths, ["docs/company-business-requirement.md"])

    def test_step_2_definition(self):
        wf = get_workflow("ard")
        s = wf.get_step("2")
        self.assertIsNotNone(s)
        self.assertEqual(s.custom_agent, "Arch-ARD-BusinessAnalysis-Targeted")
        self.assertEqual(s.depends_on, [])
        self.assertEqual(s.output_paths, ["docs/business-requirement.md"])

    def test_step_3_dependency(self):
        """Step.3 は depends_on / skip_fallback_deps の定義が期待どおりであること。"""
        wf = get_workflow("ard")
        s = wf.get_step("3")
        self.assertIsNotNone(s)
        self.assertEqual(s.custom_agent, "Arch-ARD-UseCaseCatalog")
        self.assertEqual(s.depends_on, ["2"])
        self.assertEqual(s.skip_fallback_deps, ["1"])
        self.assertEqual(s.output_paths, ["docs/catalog/use-case-catalog.md"])
        # required_input_paths は「いずれか/両方」を許容し、先頭が優先採用対象。
        self.assertEqual(
            s.required_input_paths,
            [
                "docs/business-requirement.md",
                "docs/company-business-requirement.md",
            ],
        )

    def test_root_steps_are_1_and_2(self):
        roots = get_root_steps("ard")
        ids = sorted(s.id for s in roots)
        self.assertEqual(ids, ["1", "2"])

    def test_next_steps_after_completing_1(self):
        """1 完了 → Step.3 が起動可能になること（2 は skipped 扱い）。"""
        nexts = get_next_steps("ard", completed_step_ids=["1"], skipped_step_ids=["2"])
        ids = [s.id for s in nexts]
        self.assertIn("3", ids)

    def test_next_steps_after_completing_2(self):
        """2 完了 → 1 が skip 扱いなら Step.3 が起動可能になること。"""
        nexts = get_next_steps("ard", completed_step_ids=["2"], skipped_step_ids=["1"])
        ids = [s.id for s in nexts]
        # depends_on=["2"] が満たされるため起動可能（skip_fallback_deps はこの判定ロジックでは参照されない）。
        self.assertIn("3", ids)


class TestARDWizardOrder(unittest.TestCase):
    def test_ard_is_first_in_list_workflows(self):
        wfs = list_workflows()
        self.assertGreater(len(wfs), 0)
        self.assertEqual(wfs[0].id, "ard",
                         "ARD must be the first workflow so that wizard shows it as #1")

    def test_existing_workflows_still_present(self):
        ids = {wf.id for wf in list_workflows()}
        for expected in ("aas", "aad-web", "asdw-web", "abd", "abdv",
                         "aag", "aagd", "akm", "aqod", "adoc"):
            self.assertIn(expected, ids)


class TestARDDisplayNames(unittest.TestCase):
    def test_display_name_registered(self):
        self.assertEqual(_WORKFLOW_DISPLAY_NAMES["ard"], "Auto Requirement Definition")

    def test_prefix_registered(self):
        self.assertEqual(_WORKFLOW_PREFIX["ard"], "ARD")


if __name__ == "__main__":
    unittest.main()
