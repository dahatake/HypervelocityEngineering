"""test_issue_template_qa_akm_merge.py — FR-CLOUD-26 の RED テスト。

Cloud で QA 起点 AKM（FR-CLOUD-24）を起動するかどうかを Issue Form の
`enable_qa_akm_merge` で制御し、無効時は `sync_required=false` とすることを検証する。

実装前は Issue Form のフィールドと抽出スクリプトが存在しないため全件 RED となる。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
_WORKFLOW_DIR = _REPO_ROOT / ".github" / "workflows"
_SCRIPT_DIR = _REPO_ROOT / ".github" / "scripts" / "bash" / "lib"

# QA→AKM 同期の対象となる Workflow のテンプレート（AKM 自身は再帰禁止で対象外）。
_TEMPLATES_WITH_QA_AKM_MERGE = [
    "app-architecture-design.yml",
    "web-app-design.yml",
    "web-app-dev.yml",
    "ai-agent-design.yml",
    "ai-agent-dev.yml",
    "dataflow-design.yml",
    "dataflow-dev.yml",
    "sourcecode-to-documentation.yml",
]

_SECTION_LABEL = "Knowledge Management マージ設定"
_TRANSITION_WORKFLOW = "auto-issue-qa-ready-transition.yml"


def _read_template(filename: str) -> str:
    return (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")


def _read_workflow(filename: str) -> str:
    return (_WORKFLOW_DIR / filename).read_text(encoding="utf-8")


class TestQaAkmMergeIssueFormParity(unittest.TestCase):
    """Issue Form のフィールド配置と既定値。"""

    def test_target_templates_have_the_checkbox(self) -> None:
        for template in _TEMPLATES_WITH_QA_AKM_MERGE:
            with self.subTest(template=template):
                self.assertIn("id: enable_qa_akm_merge", _read_template(template))

    def test_akm_template_does_not_have_the_checkbox(self) -> None:
        """AKM 自身は QA 起点 AKM を再帰生成しないため対象外。"""
        self.assertNotIn(
            "id: enable_qa_akm_merge",
            _read_template("knowledge-management.yml"),
        )

    def test_section_label_matches_the_extractor(self) -> None:
        for template in _TEMPLATES_WITH_QA_AKM_MERGE:
            with self.subTest(template=template):
                self.assertIn(_SECTION_LABEL, _read_template(template))

    def test_checkbox_is_unchecked_by_default(self) -> None:
        """`checkboxes` は `- label:` のみで既定チェックを付けない。"""
        block = re.compile(
            r"id: enable_qa_akm_merge\b.*?options:\s*\n(?P<options>(?:[ \t]+- [^\n]*\n)+)",
            re.DOTALL,
        )
        for template in _TEMPLATES_WITH_QA_AKM_MERGE:
            with self.subTest(template=template):
                match = block.search(_read_template(template))
                self.assertIsNotNone(match, "options ブロックが見つかりません")
                self.assertNotIn("required: true", match.group("options"))
                self.assertNotIn("checked", match.group("options"))


class TestQaAkmMergeExtractor(unittest.TestCase):
    """body 抽出スクリプトと bash wrapper。"""

    def test_extract_script_exists(self) -> None:
        script = _SCRIPT_DIR / "extract-qa-akm-merge.py"
        self.assertTrue(script.is_file(), "extract-qa-akm-merge.py が存在しません")
        text = script.read_text(encoding="utf-8")
        self.assertIn(_SECTION_LABEL, text)

    def test_copilot_assign_exposes_the_wrapper(self) -> None:
        text = (_SCRIPT_DIR / "copilot-assign.sh").read_text(encoding="utf-8")
        self.assertIn("extract_qa_akm_merge()", text)
        self.assertIn("extract-qa-akm-merge.py", text)

    def test_extractor_returns_true_only_for_a_checked_box(self) -> None:
        import subprocess
        import sys

        script = _SCRIPT_DIR / "extract-qa-akm-merge.py"
        if not script.is_file():
            self.skipTest("extract-qa-akm-merge.py が未実装")
        cases = {
            f"### {_SECTION_LABEL}\n\n- [x] マージする\n": "true",
            f"### {_SECTION_LABEL}\n\n- [X] マージする\n": "true",
            f"### {_SECTION_LABEL}\n\n- [ ] マージする\n": "false",
            f"### {_SECTION_LABEL}\n\n_No response_\n": "false",
            "### 質問票設定\n\n- [x] 質問票を作成する\n": "false",
            "": "false",
        }
        for body, expected in cases.items():
            with self.subTest(body=body):
                proc = subprocess.run(
                    [sys.executable, str(script)],
                    input=body, capture_output=True, text=True, encoding="utf-8",
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.strip(), expected)


class TestQaAkmMergeTransitionWorkflow(unittest.TestCase):
    """`save-qa-answer` の `sync_required` だけが判定すること。"""

    def test_workflow_calls_the_wrapper(self) -> None:
        content = _read_workflow(_TRANSITION_WORKFLOW)
        self.assertIn(
            'source "${GITHUB_WORKSPACE}/.github/scripts/bash/lib/copilot-assign.sh"',
            content,
        )
        self.assertIn('qa_akm_merge=$(extract_qa_akm_merge "${body}")', content)
        self.assertNotIn(
            "extract-qa-akm-merge.py", content,
            "python3 直呼びが残っています（wrapper がデッドコード化します）",
        )

    def test_sync_required_is_disabled_when_unchecked(self) -> None:
        content = _read_workflow(_TRANSITION_WORKFLOW)
        self.assertIn('"${qa_akm_merge}" != "true"', content)

    def test_gate_is_not_duplicated_in_downstream_jobs(self) -> None:
        """判定は `sync_required` の 1 箇所だけ（FR-CLOUD-26）。"""
        content = _read_workflow(_TRANSITION_WORKFLOW)
        marker = "\n  dispatch-akm:"
        self.assertIn(marker, content)
        downstream = content.split(marker, 1)[1]
        self.assertNotIn("qa_akm_merge", downstream)


if __name__ == "__main__":
    unittest.main()
