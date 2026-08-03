"""
Issue Template と reusable workflow の自己改善設定の網羅性テスト。

Phase 8 で追加された検証:
- 全対象 Issue Template に enable_self_improve / self_improve_max_iterations / self_improve_quality_threshold がある
- setup-labels.yml / self-improve.yml は自己改善対象外
- 全対象 reusable workflow に self-improve job / Parse Self-Improve settings / Run Self-Improve がある
"""

import io
import json
import re
import sys
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import yaml  # type: ignore[import-untyped]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
_WORKFLOW_DIR = _REPO_ROOT / ".github" / "workflows"


class TestIssueTemplateSelfImprove(unittest.TestCase):
    """Issue Template が自己改善設定フィールドを持つことを検証する。"""

    _TEMPLATES_WITH_SELF_IMPROVE = [
        "app-architecture-design.yml",
        "web-app-design.yml",
        "web-app-dev.yml",
        "dataflow-design.yml",
        "dataflow-dev.yml",
        "sourcecode-to-documentation.yml",
        "knowledge-management.yml",
        "original-docs-review.yml",
    ]

    _TEMPLATES_EXCLUDED = [
        "setup-labels.yml",  # ラベル初期化用: 自己改善対象外
    ]

    def _read(self, filename: str) -> str:
        path = _TEMPLATE_DIR / filename
        self.assertTrue(path.exists(), f"テンプレートが見つかりません: {path}")
        return path.read_text(encoding="utf-8")

    def _assert_has_field(self, content: str, field_id: str, template: str) -> None:
        self.assertIn(
            f"id: {field_id}",
            content,
            f"{template} に `id: {field_id}` がありません",
        )

    def _test_template_has_self_improve_fields(self, template: str) -> None:
        content = self._read(template)
        for field in ("enable_self_improve", "self_improve_max_iterations", "self_improve_quality_threshold"):
            self._assert_has_field(content, field, template)

    def test_app_architecture_design_has_self_improve(self) -> None:
        self._test_template_has_self_improve_fields("app-architecture-design.yml")

    def test_web_app_design_has_self_improve(self) -> None:
        self._test_template_has_self_improve_fields("web-app-design.yml")

    def test_web_app_dev_has_self_improve(self) -> None:
        self._test_template_has_self_improve_fields("web-app-dev.yml")

    def test_ai_agent_design_has_self_improve(self) -> None:
        content = self._read("ai-agent-design.yml")
        self.assertNotIn("id: enable_self_improve", content)
        self._assert_has_field(
            content,
            "self_improve_max_iterations",
            "ai-agent-design.yml",
        )
        self._assert_has_field(
            content,
            "self_improve_quality_threshold",
            "ai-agent-design.yml",
        )
        self.assertIn("Post-DAG Self-Improve が必ず実行", content)

    def test_ai_agent_dev_has_self_improve(self) -> None:
        content = self._read("ai-agent-dev.yml")
        self.assertNotIn("id: enable_self_improve", content)
        for field in (
            "tdd_max_retries",
            "self_improve_max_iterations",
            "self_improve_quality_threshold",
        ):
            self._assert_has_field(content, field, "ai-agent-dev.yml")
        self.assertIn("Post-DAG Self-Improveが必ず実行", content)
        self.assertIn("TDD GREEN", content)

    def test_batch_design_has_self_improve(self) -> None:
        self._test_template_has_self_improve_fields("dataflow-design.yml")

    def test_batch_dev_has_self_improve(self) -> None:
        self._test_template_has_self_improve_fields("dataflow-dev.yml")

    def test_sourcecode_to_documentation_has_self_improve(self) -> None:
        self._test_template_has_self_improve_fields("sourcecode-to-documentation.yml")

    def test_knowledge_management_has_self_improve(self) -> None:
        self._test_template_has_self_improve_fields("knowledge-management.yml")

    def test_original_docs_review_has_self_improve(self) -> None:
        self._test_template_has_self_improve_fields("original-docs-review.yml")

    def test_setup_labels_excluded(self) -> None:
        """setup-labels.yml は自己改善対象外であることを確認。"""
        for template in self._TEMPLATES_EXCLUDED:
            content = self._read(template)
            self.assertNotIn(
                "id: enable_self_improve",
                content,
                f"{template} に enable_self_improve が含まれていますが、対象外テンプレートです",
            )


class TestReusableWorkflowSelfImprove(unittest.TestCase):
    """reusable workflow に self-improve job が含まれることを検証する。"""

    _WORKFLOWS_WITH_SELF_IMPROVE = [
        "auto-app-selection-reusable.yml",
        "auto-app-detail-design-web-reusable.yml",
        "auto-app-dev-microservice-web-reusable.yml",
        "auto-dataflow-design-reusable.yml",
        "auto-dataflow-dev-reusable.yml",
        "auto-ai-agent-design-reusable.yml",
        "auto-ai-agent-dev-reusable.yml",
        "auto-app-documentation-reusable.yml",
        "auto-knowledge-management-reusable.yml",
        "auto-aqod.yml",
    ]

    def _read(self, filename: str) -> str:
        path = _WORKFLOW_DIR / filename
        self.assertTrue(path.exists(), f"ワークフローが見つかりません: {path}")
        return path.read_text(encoding="utf-8")

    def _assert_workflow_has_self_improve(self, wf: str) -> None:
        content = self._read(wf)
        self.assertIn("self-improve:", content, f"{wf} に `self-improve:` job がありません")
        self.assertIn(
            "Parse Self-Improve settings",
            content,
            f"{wf} に `Parse Self-Improve settings` step がありません",
        )
        self.assertIn(
            "Run Self-Improve",
            content,
            f"{wf} に `Run Self-Improve` step がありません",
        )
        self.assertIn(
            "run_improvement_loop",
            content,
            f"{wf} に `run_improvement_loop` がありません",
        )

    def test_auto_app_selection_reusable(self) -> None:
        self._assert_workflow_has_self_improve("auto-app-selection-reusable.yml")

    def test_auto_app_detail_design_web_reusable(self) -> None:
        self._assert_workflow_has_self_improve("auto-app-detail-design-web-reusable.yml")

    def test_auto_app_dev_microservice_web_reusable(self) -> None:
        self._assert_workflow_has_self_improve("auto-app-dev-microservice-web-reusable.yml")

    def test_auto_batch_design_reusable(self) -> None:
        self._assert_workflow_has_self_improve("auto-dataflow-design-reusable.yml")

    def test_auto_batch_dev_reusable(self) -> None:
        self._assert_workflow_has_self_improve("auto-dataflow-dev-reusable.yml")

    def test_auto_ai_agent_design_reusable(self) -> None:
        content = self._read("auto-ai-agent-design-reusable.yml")
        self.assertIn("self-improve:", content)
        self.assertIn(
            "Resolve completed Root Issue and Self-Improve settings",
            content,
        )
        self.assertIn("Run mandatory AAG Post-DAG Self-Improve", content)
        self.assertIn("run_improvement_loop", content)
        self.assertNotIn("enable-self-improve", content)
        self.assertNotIn("outputs.enable", content)
        self.assertIn("aag:self-improve-ready", content)
        self.assertIn("aag-self-improve-status: running", content)
        self.assertIn("aag-self-improve-status: finalizing", content)
        self.assertIn("aag-self-improve-status: completed", content)
        self.assertIn("aag-self-improve-status: pending", content)
        self.assertIn("collect_workflow_output_paths('aag'", content)
        self.assertIn("config.workflow_id = 'aag'", content)
        self.assertIn("config._resolved_scope_ceiling_paths = output_paths", content)
        self.assertIn("_self_improve_result_succeeded(result, task_goal)", content)
        self.assertIn("actual - allowed", content)
        self.assertIn("git merge-base --is-ancestor", content)
        self.assertNotIn("git rebase", content)
        self.assertIn('ensure_no_label "aag:self-improve-ready"', content)
        self.assertIn('ensure_label "aag:done"', content)
        self.assertIn('ensure_label "aag:blocked"', content)
        self.assertEqual(content.count('create_label "auto-ai-agent-design"'), 1)
        self.assertNotIn(
            '"${LABEL_NAME}" == "auto-ai-agent-design" ||',
            content,
        )
        self.assertNotIn(r"\\\\[AAD\\\\] Step\\\\.", content)
        self.assertGreaterEqual(content.count(r"\\\\[AAG\\\\] Step\\\\."), 2)

        before_job, self_improve_job = content.split("\n  self-improve:\n", 1)
        self.assertNotIn(
            'add_label "${ROOT_ISSUE}" "aag:done"',
            before_job,
        )
        self.assertNotIn("auto_close_root_if_all_done", before_job)
        self.assertIn("auto_close_root_if_all_done", self_improve_job)

    def test_auto_ai_agent_design_cloud_state_machine_and_shell_structure(self) -> None:
        content = self._read("auto-ai-agent-design-reusable.yml")
        document = yaml.safe_load(content)
        jobs = document["jobs"]
        expected_concurrency = {
            "group": "ai-agent-root-state-${{ github.repository }}",
            "queue": "max",
            "cancel-in-progress": False,
        }
        self.assertEqual(jobs["orchestrate"]["concurrency"], expected_concurrency)
        self.assertEqual(jobs["self-improve"]["concurrency"], expected_concurrency)

        transition = next(
            step["run"]
            for step in jobs["orchestrate"]["steps"]
            if step.get("name") == "状態遷移処理"
        )
        helper_match = re.search(
            r"(?ms)^mark_root_self_improve_ready\(\) \{\n(?P<body>.*?)^\}$",
            transition,
        )
        if helper_match is None:
            self.fail("mark_root_self_improve_ready helper was not found")
        helper = helper_match.group("body")
        self.assertIn("running|finalizing|completed", helper)
        self.assertIn('== "pending"', helper)
        self.assertIn("return 0", helper)
        self.assertIn("_done_label_verified", transition)
        self.assertIn('grep -Fxq "aag:done"', transition)
        self.assertIn("closed event の aag:done を付与・確認できない", transition)
        self.assertNotIn('-d \'{"labels":["aag:done"]}\' || true', transition)

        self_improve_steps = jobs["self-improve"]["steps"]
        parse_step = next(step["run"] for step in self_improve_steps if step.get("id") == "parse")
        self.assertIn("aag-self-improve-status: running", parse_step)
        self.assertIn('"${status}" != "completed"', parse_step)
        self.assertIn('"${status}" =~ ^(running|finalizing)$', parse_step)
        success_step = next(
            step["run"]
            for step in self_improve_steps
            if step.get("name") == "Record successful AAG Self-Improve completion"
        )
        self.assertLess(
            success_step.index("aag-self-improve-status: finalizing"),
            success_step.index('ensure_label "aag:done"'),
        )
        self.assertLess(
            success_step.index('ensure_no_label "aag:self-improve-ready"'),
            success_step.index("aag-self-improve-status: completed"),
        )
        self.assertIn('ensure_no_label "aag:blocked"', success_step)
        self.assertIn("auto_merge_enabled", success_step)
        self.assertIn("AAG Root auto-close was required", success_step)
        self.assertLess(
            success_step.index('ensure_label "aag:done"'),
            success_step.index("auto_close_root_if_all_done"),
        )
        self.assertLess(
            success_step.index("auto_close_root_if_all_done"),
            success_step.index("aag-self-improve-status: completed"),
        )
        failure_step = next(
            step
            for step in self_improve_steps
            if step.get("name") == "Mark AAG Root blocked when mandatory Self-Improve fails"
        )
        self.assertIn("failure() || cancelled()", failure_step["if"])
        self.assertIn('ensure_no_label "aag:done"', failure_step["run"])
        self.assertIn('ensure_label "aag:self-improve-ready"', failure_step["run"])
        self.assertIn('ensure_label "aag:blocked"', failure_step["run"])
        self.assertIn('[[ "${state}" == "OPEN" ]]', failure_step["run"])
        self.assertEqual(
            failure_step["env"]["SELF_IMPROVE_OUTCOME"],
            "${{ steps.self_improve.outcome }}",
        )
        self.assertIn("Self-Improve本体は成功しましたが", failure_step["run"])
        self.assertIn("aag-self-improve-status: pending", failure_step["run"])

        for step in [
            item
            for job in jobs.values()
            for item in job.get("steps", [])
            if isinstance(item, dict) and isinstance(item.get("run"), str)
        ]:
            script = step["run"]
            lines = script.splitlines()
            for index, line in enumerate(lines):
                match = re.search(r"<<'(?P<marker>[A-Z][A-Z0-9_]*)'", line)
                if not match:
                    continue
                marker = match.group("marker")
                closing = next(
                    (candidate for candidate in lines[index + 1:] if candidate.strip() == marker),
                    None,
                )
                self.assertEqual(
                    closing,
                    marker,
                    f"{step.get('name')}: heredoc {marker} closing delimiter must start at column 0",
                )

        self_improve_section = content.split("\n  self-improve:\n", 1)[1]
        python_blocks = list(re.finditer(
            r"<<'PY'\n(?P<code>.*?)\n\s*PY",
            self_improve_section,
            re.DOTALL,
        ))
        self.assertEqual(len(python_blocks), 6)
        for index, block in enumerate(python_blocks, start=1):
            compile(
                textwrap.dedent(block.group("code")),
                f"auto-ai-agent-design-reusable.yml:self-improve:{index}",
                "exec",
            )

    def test_auto_ai_agent_dev_reusable(self) -> None:
        content = self._read("auto-ai-agent-dev-reusable.yml")
        required = (
            "self-improve:",
            "Resolve completed Root Issue and Self-Improve settings",
            "Run mandatory AAGD Post-DAG Self-Improve",
            "run_improvement_loop",
            "aagd:self-improve-ready",
            "aagd-self-improve-status: pending",
            "aagd-self-improve-status: running",
            "aagd-self-improve-status: finalizing",
            "aagd-self-improve-status: completed",
            "collect_workflow_output_paths('aagd'",
            "config.workflow_id = 'aagd'",
            "config._resolved_scope_ceiling_paths = output_paths",
            "_self_improve_result_succeeded(result, task_goal)",
            "python3 -m hve.cloud_aagd_gate",
            "actual - allowed",
            "git merge-base --is-ancestor",
            "actions/setup-dotnet@v4",
        )
        for token in required:
            self.assertIn(token, content)
        self.assertNotIn("enable-self-improve", content)
        self.assertNotIn("outputs.enable", content)
        self.assertNotIn("git rebase", content)
        self.assertNotIn("git add -A", content)
        self.assertEqual(content.count('create_label "auto-ai-agent-dev"'), 1)
        self.assertNotIn(
            '"${LABEL_NAME}" == "auto-ai-agent-dev" ||',
            content,
        )

        before_job, self_improve_job = content.split("\n  self-improve:\n", 1)
        self.assertNotIn('add_label "${ROOT_ISSUE}" "aagd:done"', before_job)
        self.assertNotIn("auto_close_root_if_all_done", before_job)
        self.assertIn("auto_close_root_if_all_done", self_improve_job)

    def test_auto_ai_agent_dev_cloud_state_machine_and_shell_structure(self) -> None:
        content = self._read("auto-ai-agent-dev-reusable.yml")
        document = yaml.safe_load(content)
        jobs = document["jobs"]
        concurrency = {
            "group": "ai-agent-root-state-${{ github.repository }}",
            "queue": "max",
            "cancel-in-progress": False,
        }
        self.assertEqual(jobs["orchestrate"]["concurrency"], concurrency)
        self.assertEqual(jobs["self-improve"]["concurrency"], concurrency)

        transition = next(
            step["run"] for step in jobs["orchestrate"]["steps"]
            if step.get("name") == "状態遷移処理"
        )
        helper_match = re.search(
            r"(?ms)^mark_root_self_improve_ready\(\) \{\n(?P<body>.*?)^\}$",
            transition,
        )
        if helper_match is None:
            self.fail("AAGD mark_root_self_improve_ready helper was not found")
        helper = helper_match.group("body")
        self.assertIn("hve.cloud_aagd_gate", helper)
        self.assertIn("running|finalizing|completed", helper)
        self.assertIn("_done_label_verified", transition)
        self.assertIn('grep -Fxq "aagd:done"', transition)
        self.assertIn("closed event の aagd:done を付与・確認できない", transition)
        self.assertNotIn('-d \'{"labels":["aagd:done"]}\' || true', transition)

        steps = jobs["self-improve"]["steps"]
        parse_step = next(step["run"] for step in steps if step.get("id") == "parse")
        self.assertIn('"${status}" != "completed"', parse_step)
        self.assertIn('"${status}" =~ ^(running|finalizing)$', parse_step)
        revalidate = next(
            step["run"] for step in steps
            if step.get("name") == "Revalidate AAGD TDD and Deploy gates before mutation"
        )
        self.assertIn("hve.cloud_aagd_gate", revalidate)
        self.assertIn("--allow-root-self-improve-blocked", revalidate)
        success_step = next(
            step["run"] for step in steps
            if step.get("name") == "Record successful AAGD Self-Improve completion"
        )
        self.assertIn('ensure_no_label "aagd:blocked"', success_step)
        self.assertIn('ensure_no_label "aagd:test-failed"', success_step)
        self.assertIn('ensure_label "aagd:done"', success_step)
        self.assertIn("auto_merge_enabled", success_step)
        failure_step = next(
            step for step in steps
            if step.get("name") == "Mark AAGD Root blocked when mandatory Self-Improve fails"
        )
        self.assertIn("failure() || cancelled()", failure_step["if"])
        self.assertIn('ensure_no_label "aagd:done"', failure_step["run"])
        self.assertIn('ensure_label "aagd:self-improve-ready"', failure_step["run"])
        self.assertIn('ensure_label "aagd:blocked"', failure_step["run"])
        self.assertEqual(failure_step["env"]["SELF_IMPROVE_OUTCOME"], "${{ steps.self_improve.outcome }}")
        self.assertIn("Self-Improve本体は成功しましたが", failure_step["run"])

        python_heredocs = 0
        for step in [
            item for job in jobs.values() for item in job.get("steps", [])
            if isinstance(item, dict) and isinstance(item.get("run"), str)
        ]:
            lines = step["run"].splitlines()
            for index, line in enumerate(lines):
                match = re.search(r"<<'(?P<marker>[A-Z][A-Z0-9_]*)'", line)
                if not match:
                    continue
                marker = match.group("marker")
                closing_index = next(
                    (
                        candidate_index
                        for candidate_index in range(index + 1, len(lines))
                        if lines[candidate_index].strip() == marker
                    ),
                    None,
                )
                if closing_index is None:
                    self.fail(f"{step.get('name')}: missing heredoc terminator {marker}")
                self.assertEqual(lines[closing_index], marker, step.get("name"))
                if "python" in line:
                    code = "\n".join(lines[index + 1:closing_index])
                    compile(
                        textwrap.dedent(code),
                        f"auto-ai-agent-dev-reusable.yml:{step.get('name')}:{marker}",
                        "exec",
                    )
                    python_heredocs += 1
        self.assertGreaterEqual(python_heredocs, 25)

    def test_auto_ai_agent_dev_step4_completion_requires_both_named_steps(self) -> None:
        content = self._read("auto-ai-agent-dev-reusable.yml")
        document = yaml.safe_load(content)
        transition = next(
            step["run"] for step in document["jobs"]["orchestrate"]["steps"]
            if step.get("name") == "状態遷移処理"
        )
        block = re.search(
            r"BOTH_DONE=.*?<<'PY'\n(?P<code>.*?)\nPY",
            transition,
            re.DOTALL,
        )
        if block is None:
            self.fail("AAGD Step 4.1/4.2 completion gate was not found")
        code = compile(
            textwrap.dedent(block.group("code")),
            "auto-ai-agent-dev-reusable.yml:step4-both-done",
            "exec",
        )

        def evaluate(issues: list[dict[str, object]]) -> str:
            original_stdin = sys.stdin
            output = io.StringIO()
            try:
                sys.stdin = io.StringIO(json.dumps(issues))
                with redirect_stdout(output):
                    exec(code, {})
            finally:
                sys.stdin = original_stdin
            return output.getvalue().strip()

        step_41: dict[str, object] = {
            "title": "[AAGD] Step.4.1: WAF architecture review",
            "labels": [{"name": "aagd:done"}],
        }
        step_42: dict[str, object] = {
            "title": "[AAGD] Step.4.2: dependency review",
            "labels": [{"name": "aagd:done"}],
        }
        self.assertEqual(evaluate([step_41, step_42]), "true")
        self.assertEqual(evaluate([step_41]), "false")
        self.assertEqual(
            evaluate([step_41, {"title": "unrelated", "labels": [{"name": "aagd:done"}]}]),
            "false",
        )

    def test_auto_app_documentation_reusable(self) -> None:
        self._assert_workflow_has_self_improve("auto-app-documentation-reusable.yml")

    def test_auto_knowledge_management_reusable(self) -> None:
        self._assert_workflow_has_self_improve("auto-knowledge-management-reusable.yml")

    def test_auto_aqod(self) -> None:
        self._assert_workflow_has_self_improve("auto-aqod.yml")
