"""Cloud workflow prompt externalization の静的契約テスト。"""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]


WORKFLOW_CONTRACTS = {
    "copilot-auto-feedback.yml": {
        "path": REPO_ROOT / ".github" / "workflows" / "copilot-auto-feedback.yml",
        "prompt_paths": (
            ".github/prompts/cloud/copilot-auto-feedback-auto-qa.prompt.md",
            ".github/prompts/cloud/copilot-auto-feedback-auto-review.prompt.md",
        ),
        "forbidden_inline": (
            "あなたは、私の依頼を実行する前に",
            "あなたは今から **敵対的レビュアー**",
        ),
    },
    "auto-review-to-approve-transition.yml": {
        "path": REPO_ROOT / ".github" / "workflows" / "auto-review-to-approve-transition.yml",
        "prompt_paths": (
            ".github/prompts/cloud/auto-review-to-approve-recheck.prompt.md",
            ".github/prompts/cloud/auto-review-to-approve-fix-request.prompt.md",
        ),
        "forbidden_inline": (
            "最新コミットを対象に再レビューを実行してください。",
            "The automated adversarial review returned **FAIL**.",
        ),
    },
    "auto-qa-default-answer.yml": {
        "path": REPO_ROOT / ".github" / "workflows" / "auto-qa-default-answer.yml",
        "prompt_paths": (
            ".github/prompts/cloud/auto-qa-default-answer-pr.prompt.md",
            ".github/prompts/cloud/auto-qa-default-answer-issue.prompt.md",
        ),
        "forbidden_inline": (
            "「未回答時の既定値候補」をそのまま採用します。",
            "質問票の全質問に対して、各質問に記載された",
        ),
    },
    "auto-qa-to-review-transition.yml": {
        "path": REPO_ROOT / ".github" / "workflows" / "auto-qa-to-review-transition.yml",
        "prompt_paths": (
            ".github/prompts/cloud/auto-qa-to-review-validation-missing.prompt.md",
        ),
        "forbidden_inline": (
            "@copilot PR body に `## 検証結果` セクションと `<!-- validation-confirmed -->` マーカーを追記してください。",
        ),
    },
}


class TestCloudWorkflowPromptExternalization(unittest.TestCase):
    def test_workflows_reference_external_prompt_files_and_remove_inline_instructions(self) -> None:
        for name, contract in WORKFLOW_CONTRACTS.items():
            content = contract["path"].read_text(encoding="utf-8")
            executable_text = "\n".join(
                line for line in content.splitlines() if not line.lstrip().startswith("#")
            )
            for prompt_path in contract["prompt_paths"]:
                self.assertIn(prompt_path, content, f"{name} must reference {prompt_path}")
            for inline_text in contract["forbidden_inline"]:
                self.assertNotIn(
                    inline_text,
                    executable_text,
                    f"{name} still contains inline model-facing instruction: {inline_text}",
                )

    def test_prompt_files_exist_and_are_non_empty_utf8_markdown(self) -> None:
        prompt_paths = {
            prompt_path
            for contract in WORKFLOW_CONTRACTS.values()
            for prompt_path in contract["prompt_paths"]
        }
        for rel_path in sorted(prompt_paths):
            path = REPO_ROOT / rel_path
            self.assertTrue(path.is_file(), rel_path)
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.strip(), rel_path)

    def test_prompt_loading_is_fail_closed_before_posting(self) -> None:
        checks = {
            "copilot-auto-feedback.yml": (
                "Prompt file ${prompt_path} is missing or empty.",
                "COMMENT_BODY が空です。Prompt file ${prompt_path} を確認してください。",
            ),
            "auto-review-to-approve-transition.yml": (
                "Prompt file ${prompt_path} is missing or empty.",
                "COMMENT_BODY が空です。Prompt file ${prompt_path} を確認してください。",
            ),
            "auto-qa-default-answer.yml": (
                "Prompt file ${prompt_path} is missing or empty.",
                "COMMENT_BODY が空です。Prompt file ${prompt_path} を確認してください。",
            ),
            "auto-qa-to-review-transition.yml": (
                "Prompt file ${prompt_path} is missing or empty.",
                "MISSING_COMMENT が空です。Prompt file ${prompt_path} を確認してください。",
            ),
        }
        for name, needles in checks.items():
            content = WORKFLOW_CONTRACTS[name]["path"].read_text(encoding="utf-8")
            for needle in needles:
                self.assertIn(needle, content, f"{name} must fail closed when prompt loading fails")

    def test_dynamic_prompt_placeholders_are_preserved_in_prompt_files(self) -> None:
        placeholders = {
            ".github/prompts/cloud/auto-review-to-approve-fix-request.prompt.md": (
                "{{SHA_MARKER}}",
                "{{REVIEW_FINDINGS}}",
            ),
            ".github/prompts/cloud/auto-qa-to-review-validation-missing.prompt.md": (
                "{{VALIDATION_MISSING_MARKER}}",
            ),
        }
        for rel_path, expected_placeholders in placeholders.items():
            content = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
            for placeholder in expected_placeholders:
                self.assertIn(placeholder, content, rel_path)


if __name__ == "__main__":
    unittest.main()