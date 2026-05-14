"""
Issue Template と reusable workflow の自己改善設定の網羅性テスト。

Phase 8 で追加された検証:
- 全対象 Issue Template に enable_self_improve / self_improve_max_iterations / self_improve_quality_threshold がある
- setup-labels.yml / self-improve.yml は自己改善対象外
- 全対象 reusable workflow に self-improve job / Parse Self-Improve settings / Run Self-Improve がある
"""

import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
_WORKFLOW_DIR = _REPO_ROOT / ".github" / "workflows"


class TestIssueTemplateSelfImprove(unittest.TestCase):
    """Issue Template が自己改善設定フィールドを持つことを検証する。"""

    _TEMPLATES_WITH_SELF_IMPROVE = [
        "app-architecture-design.yml",
        "web-app-design.yml",
        "web-app-dev.yml",
        "ai-agent-design.yml",
        "ai-agent-dev.yml",
        "batch-design.yml",
        "batch-dev.yml",
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
        self._test_template_has_self_improve_fields("ai-agent-design.yml")

    def test_ai_agent_dev_has_self_improve(self) -> None:
        self._test_template_has_self_improve_fields("ai-agent-dev.yml")

    def test_batch_design_has_self_improve(self) -> None:
        self._test_template_has_self_improve_fields("batch-design.yml")

    def test_batch_dev_has_self_improve(self) -> None:
        self._test_template_has_self_improve_fields("batch-dev.yml")

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
        "auto-batch-design-reusable.yml",
        "auto-batch-dev-reusable.yml",
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
        self._assert_workflow_has_self_improve("auto-batch-design-reusable.yml")

    def test_auto_batch_dev_reusable(self) -> None:
        self._assert_workflow_has_self_improve("auto-batch-dev-reusable.yml")

    def test_auto_ai_agent_design_reusable(self) -> None:
        self._assert_workflow_has_self_improve("auto-ai-agent-design-reusable.yml")

    def test_auto_ai_agent_dev_reusable(self) -> None:
        self._assert_workflow_has_self_improve("auto-ai-agent-dev-reusable.yml")

    def test_auto_app_documentation_reusable(self) -> None:
        self._assert_workflow_has_self_improve("auto-app-documentation-reusable.yml")

    def test_auto_knowledge_management_reusable(self) -> None:
        self._assert_workflow_has_self_improve("auto-knowledge-management-reusable.yml")

    def test_auto_aqod(self) -> None:
        self._assert_workflow_has_self_improve("auto-aqod.yml")
