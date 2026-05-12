"""restore-auto-qa-label workflow の構成を検証する。"""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_WORKFLOW = "restore-auto-qa-label.yml"


def _load_workflow_yaml(filename: str) -> dict:
    return yaml.safe_load((_WORKFLOWS_DIR / filename).read_text(encoding="utf-8"))


def _get_workflow_step(filename: str, *, job_name: str, step_name: str) -> dict:
    yaml_data = _load_workflow_yaml(filename)
    steps = yaml_data.get("jobs", {}).get(job_name, {}).get("steps", [])
    return next(step for step in steps if step.get("name") == step_name)


class TestRestoreAutoQaLabelWorkflow(unittest.TestCase):
    def test_has_expected_triggers(self):
        yaml_data = _load_workflow_yaml(_WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        pull_request_target = on_section.get("pull_request_target", {})
        self.assertEqual(pull_request_target.get("types"), ["labeled", "unlabeled", "synchronize"])
        inputs = on_section.get("workflow_dispatch", {}).get("inputs", {})
        self.assertIn("target_pr", inputs)
        self.assertIn("dry_run", inputs)

    def test_has_permissions_and_concurrency(self):
        yaml_data = _load_workflow_yaml(_WORKFLOW)
        permissions = yaml_data.get("permissions", {})
        self.assertEqual(permissions.get("contents"), "read")
        self.assertEqual(permissions.get("pull-requests"), "write")
        self.assertEqual(permissions.get("issues"), "write")
        concurrency = yaml_data.get("concurrency", {})
        self.assertIn("restore-auto-qa-label-", concurrency.get("group", ""))
        self.assertFalse(concurrency.get("cancel-in-progress"))

    def test_job_if_checks_qa_questionnaire_pr_and_auto_qa_combination(self):
        yaml_data = _load_workflow_yaml(_WORKFLOW)
        condition = yaml_data.get("jobs", {}).get("restore", {}).get("if", "")
        self.assertIn("qa-questionnaire-pr", condition)
        self.assertIn("auto-qa", condition)

    def test_run_script_contains_linked_issue_and_dry_run_and_idempotency_logic(self):
        step = _get_workflow_step(_WORKFLOW, job_name="restore", step_name="Restore auto-qa label when misclassified")
        script = step.get("run", "")
        self.assertIn("find_issue_number", script)
        self.assertIn("contains([\"auto-qa\"])", script)
        self.assertIn("<!-- auto-qa: true -->", script)
        self.assertIn("if [ \"${DRY_RUN}\" = \"true\" ]; then", script)
        self.assertIn("<!-- restore-auto-qa-label-done -->", script)
        self.assertIn('.user.login == "github-actions[bot]"', script)
