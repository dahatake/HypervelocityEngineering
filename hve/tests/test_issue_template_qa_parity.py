"""Issue Template / Actions の auto-qa パリティ検証。"""

from __future__ import annotations

import unittest
import re
import textwrap
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
_WORKFLOW_DIR = _REPO_ROOT / ".github" / "workflows"


class TestIssueTemplateQaControls(unittest.TestCase):
    """今回対象の Issue Template が enable_qa を持つことを検証する。"""

    _TEMPLATES_WITH_QA = [
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

    _TEMPLATES_OUT_OF_SCOPE = [
        "setup-labels.yml",
        "self-improve.yml",
    ]

    def _read_template(self, filename: str) -> str:
        return (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")

    def test_target_templates_have_enable_qa(self) -> None:
        for template in self._TEMPLATES_WITH_QA:
            with self.subTest(template=template):
                self.assertIn("id: enable_qa", self._read_template(template))

    def test_out_of_scope_templates_are_not_changed(self) -> None:
        for template in self._TEMPLATES_OUT_OF_SCOPE:
            with self.subTest(template=template):
                self.assertNotIn("id: enable_qa", self._read_template(template))


class TestWorkflowAutoQaParity(unittest.TestCase):
    """AKM/AQOD Actions が auto-qa を固定値ではなく入力から反映することを検証する。"""

    def _read_workflow(self, filename: str) -> str:
        return (_WORKFLOW_DIR / filename).read_text(encoding="utf-8")

    def test_akm_workflow_propagates_auto_qa(self) -> None:
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('("auto-qa", auto_qa)', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_aqod_workflow_uses_template_auto_qa_value(self) -> None:
        content = self._read_workflow("auto-aqod.yml")
        self.assertIn('qa_section = section("質問票設定")', content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('("auto-qa", auto_qa)', content)
        self.assertIn('f"<!-- auto-qa: {os.environ.get(\'AUTO_QA\', \'false\')} -->"', content)
        self.assertIn('add_label "${ISSUE_NUMBER}" "auto-qa"', content)
        self.assertNotIn('"<!-- auto-qa: true -->"', content)
        self.assertNotIn('LABELS=\'["aqod:ready","auto-context-review","auto-qa"]\'', content)

    def test_aas_workflow_auto_qa_dynamic(self) -> None:
        """AAS ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-app-selection-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_aad_web_workflow_auto_qa_dynamic(self) -> None:
        """AAD-WEB ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-app-detail-design-web-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_asdw_web_workflow_auto_qa_dynamic(self) -> None:
        """ASDW-WEB ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-app-dev-microservice-web-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_asdw_web_workflow_has_step_3_3_e2e_transition(self) -> None:
        """ASDW-WEB に Step.3.3 E2E が追加され、3.2→3.3→4.1/4.2 の遷移であること。"""
        content = self._read_workflow("auto-app-dev-microservice-web-reusable.yml")
        self.assertIn("[ASDW-WEB] Step.3.3: E2E テスト (Playwright)", content)
        self.assertIn("Step.3.2 完了 → Step.3.3 を起動", content)
        self.assertIn(
            "Step.3.3 完了 → Step.3 コンテナに asdw-web:done → Step.4.1 + Step.4.2 を並列起動",
            content,
        )

    def test_abd_workflow_auto_qa_dynamic(self) -> None:
        """ABD ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-batch-design-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_abdv_workflow_auto_qa_dynamic(self) -> None:
        """ABDV ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-batch-dev-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_aag_workflow_auto_qa_dynamic(self) -> None:
        """AAG ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-ai-agent-design-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_aagd_workflow_auto_qa_dynamic(self) -> None:
        """AAGD ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-ai-agent-dev-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_adoc_workflow_auto_qa_dynamic(self) -> None:
        """ADOC ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-app-documentation-reusable.yml")
        self.assertIn('質問票設定', content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_reusable_workflows_embed_validation_marker_in_prompt(self) -> None:
        """Copilot向け追加入力セクションに検証マーカー指示が含まれることを検証する。"""
        targets = [
            "auto-ai-agent-design-reusable.yml",
            "auto-ai-agent-dev-reusable.yml",
            "auto-app-detail-design-web-reusable.yml",
            "auto-app-dev-microservice-web-reusable.yml",
            "auto-app-documentation-reusable.yml",
            "auto-app-selection-reusable.yml",
            "auto-batch-design-reusable.yml",
            "auto-batch-dev-reusable.yml",
            "auto-knowledge-management-reusable.yml",
        ]
        for filename in targets:
            with self.subTest(filename=filename):
                content = self._read_workflow(filename)
                self.assertIn("## 検証結果（PR本文に必須）", content)
                self.assertIn("<!-- validation-confirmed -->", content)
                m = re.search(
                    r"QA_REVIEW_SECTION=\$\(printf '(?P<section>.*?)'\)",
                    content,
                    re.DOTALL,
                )
                self.assertIsNotNone(m, "QA_REVIEW_SECTION が見つかりません")
                section = m.group("section")
                self.assertIn("## 追加コンテキストの参照", section)
                self.assertIn("## 検証結果（PR本文に必須）", section)
                self.assertIn("<!-- validation-confirmed -->", section)

    def test_akm_aqod_python_heredoc_blocks_are_compilable(self) -> None:
        """AKM/AQODワークフローのPython heredocブロックが構文的に有効であることを検証する。"""
        pattern = re.compile(
            r"<<'(?P<marker>PY(?:EOF|TAGS|MERGE))'\n(?P<code>.*?)\n\s*(?P=marker)",
            re.DOTALL,
        )
        for filename in ("auto-knowledge-management-reusable.yml", "auto-aqod.yml"):
            content = self._read_workflow(filename)
            blocks = list(pattern.finditer(content))
            self.assertGreater(len(blocks), 0, filename)
            for idx, match in enumerate(blocks, start=1):
                with self.subTest(filename=filename, marker=match.group("marker"), idx=idx):
                    compile(
                        textwrap.dedent(match.group("code")),
                        f"{filename}:{match.group('marker')}:{idx}",
                        "exec",
                    )


if __name__ == "__main__":
    unittest.main()
