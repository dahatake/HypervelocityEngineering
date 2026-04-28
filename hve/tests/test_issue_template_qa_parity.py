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

    def test_embedded_python_heredocs_are_syntactically_valid(self) -> None:
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