"""auto-qa-to-review-transition.yml の重要判定ロジックを静的検証する。"""

import unittest
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[3]
    / "workflows"
    / "auto-qa-to-review-transition.yml"
)
PROMPT = (
    Path(__file__).resolve().parents[3]
    / "prompts"
    / "cloud"
    / "auto-qa-to-review-validation-missing.prompt.md"
)


class TestAutoQaToReviewTransitionWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = WORKFLOW.read_text(encoding="utf-8")
        cls.prompt_content = PROMPT.read_text(encoding="utf-8")

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

    # --- T4: 検証マーカーチェック（auto-approve-ready 付与前）---

    def test_t4_validation_missing_marker_defined(self):
        """検証不足通知コメントのマーカーが定義されていること。"""
        self.assertIn("<!-- auto-qa-to-review-validation-missing -->", self.content)

    def test_t4_validation_confirmed_marker_checked(self):
        """validation-confirmed マーカーが判定対象に含まれること。"""
        self.assertIn("<!-- validation-confirmed -->", self.content)

    def test_t4_validation_marker_decision_is_delegated(self):
        """検証マーカー判定を単一実装（FR-MAINT-06）へ委譲していること。"""
        self.assertIn("check_validation_marker.py", self.content)
        for name in ("HEADING_REGEX", "BULLET_REGEX", "LEGACY_REGEX"):
            self.assertNotIn(name, self.content)

    def test_t4_validation_check_before_label_assignment(self):
        """検証マーカーチェックが auto-approve-ready ラベル付与より前に来ること。"""
        validation_pos = self.content.find("VALIDATION_MISSING_MARKER=")
        label_pos = self.content.find('--add-label "auto-approve-ready"')
        self.assertGreater(label_pos, validation_pos)

    def test_t4_validation_missing_skips_label(self):
        """検証マーカーがない場合に auto-approve-ready をスキップするブランチが存在すること。"""
        self.assertIn('[ "${has_validation}" = "false" ]', self.content)
        self.assertIn("auto-approve-ready 付与をスキップします", self.content)

    def test_t4_validation_missing_comment_is_idempotent(self):
        """検証不足通知コメントが冪等化されていること（既に投稿済みならスキップ）。"""
        self.assertIn("existing_validation_comment=", self.content)
        self.assertIn("検証不足通知コメントは既に投稿済みです。スキップします。", self.content)

    def test_t4_copilot_mention_in_missing_comment(self):
        """検証不足通知コメントに @copilot メンションが含まれ、workflow は外部 prompt を参照すること。"""
        self.assertIn(
            '.github/prompts/cloud/auto-qa-to-review-validation-missing.prompt.md',
            self.content,
        )
        self.assertIn("@copilot PR body に", self.prompt_content)

    def test_t4_validation_passes_proceeds_to_label(self):
        """検証マーカーが存在する場合にラベル付与に進む案内メッセージが存在すること。"""
        self.assertIn("検証実施記録を確認しました。auto-approve-ready ラベルを付与します。", self.content)

    def test_pr_false_marker_overrides_root_review_setting(self):
        """PR bodyのfalse markerをRoot Issue設定より優先すること。"""
        self.assertIn("PR_REVIEW_OPTED_OUT", self.content)
        self.assertIn('pr_review_opted_out="true"', self.content)
        self.assertIn('--remove-label "adversarial-review"', self.content)
        self.assertIn(
            'if [ "${PR_REVIEW_OPTED_OUT:-false}" = "true" ]; then',
            self.content,
        )

    def test_issue_true_marker_restores_review_without_label(self):
        """Issue bodyのtrue marker単独でもレビュー設定を復元すること。"""
        self.assertIn(
            '<!--[[:space:]]*adversarial-review:[[:space:]]*true[[:space:]]*-->',
            self.content,
        )
        self.assertIn('has_issue_review_label="true"', self.content)


if __name__ == "__main__":
    unittest.main()
