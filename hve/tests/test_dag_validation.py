"""DAG validation tests."""

from __future__ import annotations

import unittest

from hve.dag_validation import validate_workflow_definition
from hve.workflow_registry import StepDef, WorkflowDef, get_workflow


class TestDAGValidation(unittest.TestCase):
    def test_validate_registry_workflow_is_warning_only(self) -> None:
        wf = get_workflow("aad-web")
        self.assertIsNotNone(wf)

        report = validate_workflow_definition(wf)

        self.assertEqual(report.workflow_id, "aad-web")
        self.assertFalse(report.has_errors)

    def test_missing_dependency_is_warning_for_current_compatibility(self) -> None:
        wf = WorkflowDef(
            id="compat",
            name="Compat",
            label_prefix="compat",
            state_labels={},
            params=[],
            steps=[StepDef(id="A", title="A", custom_agent="Agent", depends_on=["MISSING"])],
        )

        report = validate_workflow_definition(wf)

        self.assertFalse(report.has_errors)
        self.assertEqual(report.by_code()["missing_dependency_reference"][0].step_id, "A")

    def test_cycle_is_error(self) -> None:
        wf = WorkflowDef(
            id="cycle",
            name="Cycle",
            label_prefix="cycle",
            state_labels={},
            params=[],
            steps=[
                StepDef(id="A", title="A", custom_agent="Agent", depends_on=["B"]),
                StepDef(id="B", title="B", custom_agent="Agent", depends_on=["A"]),
            ],
        )

        report = validate_workflow_definition(wf)

        self.assertTrue(report.has_errors)
        self.assertIn("cycle_detected", report.by_code())


if __name__ == "__main__":
    unittest.main()
