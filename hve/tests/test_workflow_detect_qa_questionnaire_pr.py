"""detect-qa-questionnaire-pr workflow の opt-in 分類を検証する。"""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_WORKFLOW = "detect-qa-questionnaire-pr.yml"


def _load_workflow_yaml(filename: str) -> dict:
    return yaml.safe_load((_WORKFLOWS_DIR / filename).read_text(encoding="utf-8"))


def _get_workflow_step(filename: str, *, job_name: str, step_name: str) -> dict:
    yaml_data = _load_workflow_yaml(filename)
    steps = yaml_data.get("jobs", {}).get(job_name, {}).get("steps", [])
    return next(step for step in steps if step.get("name") == step_name)


class TestDetectQaQuestionnairePrWorkflow(unittest.TestCase):
    def test_has_pull_request_target_trigger(self):
        yaml_data = _load_workflow_yaml(_WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        pull_request_target = on_section.get("pull_request_target", {})
        self.assertEqual(pull_request_target.get("types"), ["opened", "synchronize"])

    def test_classify_step_contains_opt_in_and_manual_override_guards(self):
        step = _get_workflow_step(_WORKFLOW, job_name="detect", step_name="Classify PR and update labels")
        script = step.get("run", "")
        self.assertIn("<!-- qa-questionnaire-pr: opt-in -->", script)
        self.assertIn("<!-- qa-questionnaire-pr: manual-override -->", script)
        self.assertIn("判定スキップ", script)

    def test_classify_step_updates_labels_with_gh_pr_edit(self):
        step = _get_workflow_step(_WORKFLOW, job_name="detect", step_name="Classify PR and update labels")
        script = step.get("run", "")
        self.assertIn('--add-label "qa-questionnaire-pr"', script)
        self.assertIn('--remove-label "auto-qa"', script)
        self.assertIn('--remove-label "qa-questionnaire-pr"', script)

    def test_early_exit_without_opt_in_marker(self):
        step = _get_workflow_step(_WORKFLOW, job_name="detect", step_name="Classify PR and update labels")
        script = step.get("run", "")
        self.assertIn("if ! printf '%s' \"${PR_BODY_HEAD}\" | grep -qF '<!-- qa-questionnaire-pr: opt-in -->'; then", script)
        self.assertIn("メインタスク PR 想定（opt-in マーカー無し）", script)
        self.assertIn("exit 0", script)
