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


# ---------------------------------------------------------------------------
# T-06: check_plan_md_metadata (SPLIT_REQUIRED 機械検出)
# ---------------------------------------------------------------------------

class TestCheckPlanMdMetadata(unittest.TestCase):
    """plan.md の冒頭5行メタデータを検査する関数のテスト。"""

    def _make_plan(self, tmp_path, body: str):
        from pathlib import Path
        p = Path(tmp_path) / "plan.md"
        p.write_text(body, encoding="utf-8")
        return p

    def test_missing_metadata_reports_violation(self):
        from dag_validation import check_plan_md_metadata
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = self._make_plan(tmp, "# title\n\nbody only\n")
            issues = check_plan_md_metadata(p)
        self.assertTrue(any("必須メタデータが不足" in m for m in issues))

    def test_single_small_passes(self):
        from dag_validation import check_plan_md_metadata
        import tempfile
        body = "# t\nrun_id: x\ntask_scope: single\ncontext_size: small\nmode: ok\n\nbody\n"
        with tempfile.TemporaryDirectory() as tmp:
            p = self._make_plan(tmp, body)
            issues = check_plan_md_metadata(p)
        self.assertEqual(issues, [])

    def test_multi_triggers_split_required(self):
        from dag_validation import check_plan_md_metadata
        import tempfile
        body = "# t\nrun_id: x\ntask_scope: multi\ncontext_size: small\nmode: SPLIT\n\nbody\n"
        with tempfile.TemporaryDirectory() as tmp:
            p = self._make_plan(tmp, body)
            issues = check_plan_md_metadata(p)
        self.assertTrue(any("SPLIT_REQUIRED" in m and "task_scope=multi" in m for m in issues))

    def test_large_context_triggers_split_required(self):
        from dag_validation import check_plan_md_metadata
        import tempfile
        body = "# t\nrun_id: x\ntask_scope: single\ncontext_size: large\nmode: SPLIT\n\nbody\n"
        with tempfile.TemporaryDirectory() as tmp:
            p = self._make_plan(tmp, body)
            issues = check_plan_md_metadata(p)
        self.assertTrue(any("SPLIT_REQUIRED" in m and "context_size=large" in m for m in issues))

    def test_meta_after_head_lines_is_violation(self):
        from dag_validation import check_plan_md_metadata
        import tempfile
        # 6 行目以降にメタを置く → 冒頭 5 行ルール違反
        body = "# t\n\n\n\n\ntask_scope: single\ncontext_size: small\n\nbody\n"
        with tempfile.TemporaryDirectory() as tmp:
            p = self._make_plan(tmp, body)
            issues = check_plan_md_metadata(p)
        self.assertTrue(any("必須メタデータが不足" in m for m in issues))

    def test_nonexistent_file(self):
        from dag_validation import check_plan_md_metadata
        from pathlib import Path
        issues = check_plan_md_metadata(Path("/nonexistent-path-xyz/plan.md"))
        self.assertTrue(any("ファイルが存在しません" in m for m in issues))


if __name__ == "__main__":
    unittest.main()
