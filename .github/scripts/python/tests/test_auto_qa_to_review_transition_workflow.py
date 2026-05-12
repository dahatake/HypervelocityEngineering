"""auto-qa-to-review-transition.yml の重要判定ロジックを静的検証する。"""

import unittest
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[3]
    / "workflows"
    / "auto-qa-to-review-transition.yml"
)


class TestAutoQaToReviewTransitionWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = WORKFLOW.read_text(encoding="utf-8")

    def test_c1_has_preemptive_answer_file_path(self):
        self.assertIn('has_answer_files_in_diff="true"', self.content)
        self.assertIn(
            'elif [ "${has_default_answer:-0}" -gt 0 ] && [ "${has_answer_files_in_diff}" = "true" ]; then',
            self.content,
        )

    def test_c2_no_question_path_requires_zero_user_and_zero_auto_answer(self):
        self.assertIn(
            'if [ "${user_reply_count:-0}" -eq 0 ] && [ "${auto_answered_count:-0}" -eq 0 ]; then',
            self.content,
        )

    def test_c3_questionnaire_detection_matches_new_patterns(self):
        for needle in [
            '.body | test("\\\\*\\\\*\\\\[Q\\\\d+\\\\]\\\\*\\\\*"; "i")',
            '.body | test("\\\\*\\\\*\\\\[質問ID\\\\]\\\\*\\\\*"; "i")',
            '.body | test("^\\\\s*選択肢[:：]"; "m")',
            '.body | test("優先順位付き質問票")',
        ]:
            self.assertIn(needle, self.content)

    def test_c4_excludes_quoted_lines_and_limits_auto_answer_marker_actor(self):
        self.assertIn(
            'select((.user.type != "Bot") or (.user.login == "github-actions[bot]"))',
            self.content,
        )
        self.assertIn('| map(select(startswith(">") | not))', self.content)

    def test_m10_reason_output_uses_heredoc(self):
        self.assertIn("reason<<", self.content)

    def test_c6_manual_review_notification_step_exists(self):
        self.assertIn("QA 完了（手動レビュー待ち）通知", self.content)
        self.assertIn("<!-- qa-complete-manual-review -->", self.content)
        self.assertIn('--remove-label "auto-qa"', self.content)


if __name__ == "__main__":
    unittest.main()
