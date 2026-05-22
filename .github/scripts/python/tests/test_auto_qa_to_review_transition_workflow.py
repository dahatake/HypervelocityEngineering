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

    # --- T4: 検証マーカーチェック（auto-approve-ready 付与前）---

    def test_t4_validation_missing_marker_defined(self):
        """検証不足通知コメントのマーカーが定義されていること。"""
        self.assertIn("<!-- auto-qa-to-review-validation-missing -->", self.content)

    def test_t4_validation_confirmed_marker_checked(self):
        """validation-confirmed マーカーが判定対象に含まれること。"""
        self.assertIn("<!-- validation-confirmed -->", self.content)

    def test_t4_heading_regex_matches_auto_approve_and_merge(self):
        """見出し方式の正規表現が auto-approve-and-merge.yml と同一パターンであること。"""
        self.assertIn(
            "'^#{1,6}[[:space:]]+.*(検証|Validation|Verification)'",
            self.content,
        )

    def test_t4_bullet_regex_matches_auto_approve_and_merge(self):
        """箇条書き/強調方式の正規表現が auto-approve-and-merge.yml と同一パターンであること。"""
        self.assertIn(
            "'^[[:space:]*>-]*(\\*\\*|__)?(検証|Validation|Verification)(\\*\\*|__)?[[:space:]]*[:：]'",
            self.content,
        )

    def test_t4_legacy_regex_matches_auto_approve_and_merge(self):
        """互換フォールバック正規表現が auto-approve-and-merge.yml と同一パターンであること。"""
        self.assertIn(
            "'(^#{1,6}[[:space:]]+|^)(Validation|検証)'",
            self.content,
        )

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
        """検証不足通知コメントに @copilot メンションが含まれること。"""
        self.assertIn("@copilot PR body に", self.content)

    def test_t4_validation_passes_proceeds_to_label(self):
        """検証マーカーが存在する場合にラベル付与に進む案内メッセージが存在すること。"""
        self.assertIn("検証実施記録を確認しました。auto-approve-ready ラベルを付与します。", self.content)

    def test_t4_auto_context_review_path_unaffected(self):
        """auto-context-review 付与ステップは検証チェックの影響を受けないこと。"""
        # auto-context-review 付与ステップ範囲内には VALIDATION_MISSING_MARKER や
        # has_validation 変数の参照が含まれないことを確認する
        context_review_step_start = self.content.find("- name: auto-context-review ラベルを PR に付与")
        direct_approve_step_start = self.content.find(
            "- name: auto-approve-ready ラベルを PR に付与（レビューなしパス）"
        )
        self.assertGreater(context_review_step_start, 0)
        self.assertGreater(direct_approve_step_start, 0)
        context_review_body = self.content[context_review_step_start:direct_approve_step_start]
        self.assertNotIn("VALIDATION_MISSING_MARKER", context_review_body)
        self.assertNotIn("has_validation", context_review_body)


if __name__ == "__main__":
    unittest.main()
