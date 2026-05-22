"""auto-approve-and-merge.yml の T5 QA Reference チェック判定ロジックを静的検証する。

検証手法: ワークフロー YAML ファイルを読み込み、文字列検索と yaml.safe_load による
YAML パースを組み合わせて T5 実装（check-qa-reference ステップ）の存在・内容・
ステップ間依存・if ガードを静的に確認する。実際の GitHub Actions 環境での実行は行わない。

T5: verify-qa-reference-in-pr.yml の FAIL 結果を auto-approve-and-merge.yml の
事前条件に組み込む（required モード FAIL 時のみ Approve/Merge をスキップ）。

検証シナリオ:
  1. QA Reference コメントなし → スキップしない（後方互換）
  2. QA Reference コメントあり / warning モード / FAIL → スキップしない
  3. QA Reference コメントあり / required モード / FAIL → Approve/Merge スキップ + 案内コメント（SHA フッター付き）
  4. 同一 SHA で再走 → 案内コメント再投稿しない
  5. 新 SHA で再走 / 依然 required FAIL → 新コメント投稿
  6. QA Reference コメントあり / required モード / PASS → スキップしない
"""

import unittest
import yaml
from pathlib import Path


WORKFLOW = (
    # ファイル位置: .github/scripts/python/tests/ → .github/workflows/
    # parents[0]=tests, [1]=python, [2]=scripts, [3]=.github → .github/workflows/
    Path(__file__).resolve().parents[3]
    / "workflows"
    / "auto-approve-and-merge.yml"
)


class TestAutoApproveAndMergeWorkflowT5(unittest.TestCase):
    """auto-approve-and-merge.yml の T5 QA Reference チェック実装を静的検証する。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.content = WORKFLOW.read_text(encoding="utf-8")
        cls.yaml_data = yaml.safe_load(cls.content)
        cls.steps = (
            cls.yaml_data.get("jobs", {})
            .get("approve-and-merge", {})
            .get("steps", [])
        )
        # check-qa-reference ステップの run スクリプトを取得（絞り込み検証用）
        qa_ref_step = next(
            (s for s in cls.steps if s.get("id") == "check-qa-reference"), None
        )
        cls.qa_ref_run = qa_ref_step.get("run", "") if qa_ref_step else ""

    # --- ステップ存在・配置 ---

    def test_t5_check_qa_reference_step_exists(self):
        """check-qa-reference ステップが存在すること。"""
        self.assertIn("id: check-qa-reference", self.content)

    def test_t5_check_qa_reference_step_after_check_validation(self):
        """check-qa-reference ステップが check-validation ステップの後に配置されていること。"""
        validation_pos = self.content.find("id: check-validation")
        qa_ref_pos = self.content.find("id: check-qa-reference")
        self.assertGreaterEqual(validation_pos, 0, "check-validation ステップが見つかりません")
        self.assertGreaterEqual(qa_ref_pos, 0, "check-qa-reference ステップが見つかりません")
        self.assertGreater(
            qa_ref_pos,
            validation_pos,
            "check-qa-reference は check-validation より後に配置される必要があります",
        )

    # --- マーカー定義 ---

    def test_t5_qa_ref_result_marker_searched(self):
        """<!-- qa-reference-check-result --> マーカー付きコメントを検索していること。"""
        self.assertIn("<!-- qa-reference-check-result -->", self.content)

    def test_t5_qa_ref_missing_marker_defined(self):
        """案内コメントに <!-- auto-approve-qa-reference-missing --> マーカーが使われていること。"""
        self.assertIn("<!-- auto-approve-qa-reference-missing -->", self.content)

    # --- モード判定ロジック ---

    def test_t5_required_mode_pattern_checked(self):
        """required モードの判定パターン（モード: `required`）が定義されていること。"""
        self.assertIn("モード: `required`", self.content)

    def test_t5_fail_pattern_checked(self):
        """FAIL パターン（❌ FAIL）が判定対象として定義されていること。"""
        self.assertIn("❌ FAIL", self.content)

    def test_t5_default_passed_is_true(self):
        """qa_reference_passed のデフォルト値が true であること（warning/コメントなし → PASS）。"""
        self.assertIn('qa_reference_passed="true"', self.content)

    def test_t5_required_fail_sets_passed_false(self):
        """required モード + FAIL 時に qa_reference_passed="false" をセットすること。"""
        self.assertIn('qa_reference_passed="false"', self.content)

    def test_t5_no_comment_falls_through_as_pass(self):
        """QA Reference コメントが存在しない場合は PASS のままであること（後方互換）。

        qa_ref_comment が空の場合は if 条件が成立せず、デフォルトの true が維持される。
        """
        self.assertIn('if [ -n "${qa_ref_comment}" ]; then', self.content)

    # --- スタール検出 ---

    def test_t5_stale_check_uses_commit_date(self):
        """FAIL コメントが HEAD コミット日時より前の場合はスタールとして PASS 扱いにすること。"""
        self.assertIn("head_commit_date=", self.content)
        self.assertIn('stale="true"', self.content)
        self.assertIn('stale="false"', self.content)

    def test_t5_stale_detection_uses_epoch_comparison(self):
        """スタール判定に epoch ベースの日時比較が使われていること。"""
        self.assertIn("qa_updated_epoch=", self.content)
        self.assertIn("head_commit_epoch=", self.content)
        self.assertIn('"${qa_updated_epoch}" -lt "${head_commit_epoch}"', self.content)

    # --- API エラー時フォールバック ---

    def test_t5_api_error_falls_through_as_pass(self):
        """PR コメント取得 API エラー時は qa_reference_passed=true（後方互換フォールバック）であること。"""
        self.assertIn(
            "QA Reference チェックをスキップします（qa_reference_passed=true）",
            self.content,
        )

    # --- SHA 単位冪等性 ---

    def test_t5_sha_marker_used_for_idempotency(self):
        """HEAD SHA フッターマーカーを使った冪等性チェックが check-qa-reference ステップに実装されていること。"""
        # check-qa-reference ステップの run 本文に限定して検証（他ステップの同名マーカーと混同しない）
        self.assertNotEqual(self.qa_ref_run, "", "check-qa-reference ステップの run スクリプトが空です")
        self.assertIn("auto-approve-and-merge-head-sha:", self.qa_ref_run)
        # jq で marker と sha_marker の両方を含むコメントを検索するロジックが存在すること
        self.assertIn("contains($marker) and contains($sha_marker)", self.qa_ref_run)

    def test_t5_same_sha_skips_comment(self):
        """同一 SHA で案内コメントが既に投稿済みの場合はスキップすること。"""
        self.assertIn(
            "QA Reference 案内コメントは同一 SHA で既に投稿済みです。スキップします。",
            self.content,
        )

    def test_t5_idempotency_comment_has_sha_footer(self):
        """案内コメント本文末尾に HEAD SHA フッターが付与されること。"""
        # QA_REF_MARKER の定義箇所以降に SHA_MARKER のフッター追加が存在する
        qa_ref_marker_def_pos = self.content.find(
            "QA_REF_MARKER='<!-- auto-approve-qa-reference-missing -->'"
        )
        sha_footer_pos = self.content.find(
            'printf \'%s\\n\' "${SHA_MARKER}"', qa_ref_marker_def_pos
        )
        self.assertGreater(
            qa_ref_marker_def_pos,
            0,
            "QA_REF_MARKER 変数定義が見つかりません",
        )
        self.assertGreater(
            sha_footer_pos,
            qa_ref_marker_def_pos,
            "check-qa-reference ステップ内で SHA フッターが付与されていません",
        )

    # --- Approve / Merge ステップの if ガード ---

    def _get_step(self, step_name: str) -> dict:
        """ステップ名でステップ辞書を取得する。"""
        step = next(
            (s for s in self.steps if s.get("name") == step_name), None
        )
        self.assertIsNotNone(step, f"ステップ '{step_name}' が見つかりません")
        assert step is not None  # 型ナローイング（上記 assertIsNotNone が失敗した場合は到達しない）
        return step

    def test_t5_approve_step_has_qa_ref_guard(self):
        """PR を Approve ステップの if ガードに qa_reference_passed 条件が含まれること。"""
        approve_step = self._get_step("PR を Approve")
        if_condition = approve_step.get("if", "")
        self.assertIn(
            "steps.check-qa-reference.outputs.qa_reference_passed != 'false'",
            if_condition,
        )

    def test_t5_merge_step_has_qa_ref_guard(self):
        """Auto-merge を有効化ステップの if ガードに qa_reference_passed 条件が含まれること。"""
        merge_step = self._get_step("Auto-merge を有効化（squash）")
        if_condition = merge_step.get("if", "")
        self.assertIn(
            "steps.check-qa-reference.outputs.qa_reference_passed != 'false'",
            if_condition,
        )

    def test_t5_summary_comment_step_has_qa_ref_guard(self):
        """サマリーコメントを PR に投稿ステップの if ガードに qa_reference_passed 条件が含まれること。"""
        summary_step = self._get_step("サマリーコメントを PR に投稿")
        if_condition = summary_step.get("if", "")
        self.assertIn(
            "steps.check-qa-reference.outputs.qa_reference_passed != 'false'",
            if_condition,
        )

    # --- 既存フロー非破壊 ---

    def test_t5_check_validation_step_unchanged(self):
        """check-validation ステップが引き続き存在すること（既存フロー非破壊）。"""
        self.assertIn("id: check-validation", self.content)
        self.assertIn("has_validation=true", self.content)
        self.assertIn("has_validation=false", self.content)

    def test_t5_done_marker_guard_unchanged(self):
        """already_done マーカーによるガードが保持されていること（既存フロー非破壊）。"""
        self.assertIn("already_done=true", self.content)
        self.assertIn("already_done=false", self.content)

    def test_t5_done_partial_failed_markers_unchanged(self):
        """done/partial/failed の各冪等化マーカーが保持されていること（既存フロー非破壊）。"""
        self.assertIn("<!-- auto-approve-and-merge-done -->", self.content)
        self.assertIn("<!-- auto-approve-and-merge-partial -->", self.content)
        self.assertIn("<!-- auto-approve-and-merge-failed -->", self.content)

    def test_t5_validation_missing_marker_unchanged(self):
        """validation-missing マーカーが保持されていること（既存フロー非破壊）。"""
        self.assertIn("<!-- auto-approve-validation-missing -->", self.content)

    # --- YAML 構造 ---

    def test_t5_yaml_is_valid(self):
        """ワークフロー YAML がパース可能であること。"""
        # setUpClass で yaml.safe_load が成功している前提で、jobs が存在すること
        self.assertIn("approve-and-merge", self.yaml_data.get("jobs", {}))

    def test_t5_approve_step_guard_preserves_existing_conditions(self):
        """Approve ステップの if ガードが既存条件（already_done, already_approved, has_validation）を保持していること。"""
        approve_step = self._get_step("PR を Approve")
        if_condition = approve_step.get("if", "")
        self.assertIn("steps.guard.outputs.already_done != 'true'", if_condition)
        self.assertIn("steps.guard.outputs.already_approved != 'true'", if_condition)
        self.assertIn(
            "steps.check-validation.outputs.has_validation != 'false'", if_condition
        )

    def test_t5_merge_step_guard_preserves_existing_conditions(self):
        """Merge ステップの if ガードが既存条件（already_done, has_validation）を保持していること。"""
        merge_step = self._get_step("Auto-merge を有効化（squash）")
        if_condition = merge_step.get("if", "")
        self.assertIn("steps.guard.outputs.already_done != 'true'", if_condition)
        self.assertIn(
            "steps.check-validation.outputs.has_validation != 'false'", if_condition
        )


if __name__ == "__main__":
    unittest.main()
