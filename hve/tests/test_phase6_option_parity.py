"""Phase 6 — Issue Template / hve オプション整合性の静的検証テスト。

外部 API / 実 GitHub Actions 実行に依存しない静的検証のみを行う。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
_WORKFLOW_DIR = _REPO_ROOT / ".github" / "workflows"
_DIFF_SPEC = _REPO_ROOT / "docs" / "design-discussions" / "orchestration-route-diff-spec.md"

# Issue Template のうち enable_review を持つべきファイル
_TEMPLATES_WITH_REVIEW = [
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

# model ドロップダウンを持つ全 Issue Template (setup-labels.yml は除外)
_TEMPLATES_WITH_MODEL = [
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
    "self-improve.yml",
]

# enable_auto_merge を持つべき Issue Template（全ワークフロー対象テンプレート）
_TEMPLATES_WITH_AUTO_MERGE = [
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
    "self-improve.yml",
]


class TestAkmAqodEnableReview(unittest.TestCase):
    """AKM / AQOD テンプレートが enable_review を持つことを検証する（Phase 6 追加）。"""

    def _read_template(self, filename: str) -> str:
        return (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")

    def test_akm_template_has_enable_review(self) -> None:
        """AKM テンプレートが enable_review チェックボックスを持つこと。"""
        content = self._read_template("knowledge-management.yml")
        self.assertIn("id: enable_review", content)

    def test_aqod_template_has_enable_review(self) -> None:
        """AQOD テンプレートが enable_review チェックボックスを持つこと。"""
        content = self._read_template("original-docs-review.yml")
        self.assertIn("id: enable_review", content)

    def test_all_target_templates_have_enable_review(self) -> None:
        """全対象テンプレートが enable_review を持つこと。"""
        for template in _TEMPLATES_WITH_REVIEW:
            with self.subTest(template=template):
                content = self._read_template(template)
                self.assertIn("id: enable_review", content)

    def test_akm_review_label_text(self) -> None:
        """AKM テンプレートの enable_review ラベルが正しいこと。"""
        content = self._read_template("knowledge-management.yml")
        self.assertIn("レビュー設定", content)
        self.assertIn("auto-context-review", content)

    def test_aqod_review_label_text(self) -> None:
        """AQOD テンプレートの enable_review ラベルが正しいこと。"""
        content = self._read_template("original-docs-review.yml")
        self.assertIn("レビュー設定", content)
        self.assertIn("auto-context-review", content)


class TestAkmWorkflowEnableReview(unittest.TestCase):
    """AKM ワークフローが enable_review を正しくパース・適用することを検証する（Phase 6 追加）。"""

    def _read_workflow(self, filename: str) -> str:
        return (_WORKFLOW_DIR / filename).read_text(encoding="utf-8")

    def test_akm_workflow_parses_review_section(self) -> None:
        """AKM ワークフローが ### レビュー設定 セクションをパースすること。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn("レビュー設定", content)
        self.assertIn("auto_context_review", content)

    def test_akm_workflow_has_auto_context_review_variable(self) -> None:
        """AKM ワークフローが AUTO_CONTEXT_REVIEW bash 変数を持つこと。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn("AUTO_CONTEXT_REVIEW", content)

    def test_akm_workflow_embeds_auto_context_review_tag(self) -> None:
        """AKM ワークフローが Root Issue body に auto-context-review タグを埋め込むこと。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn('("auto-context-review", auto_context_review)', content)

    def test_akm_workflow_adds_auto_context_review_label_conditionally(self) -> None:
        """AKM ワークフローが AUTO_CONTEXT_REVIEW 条件付きでラベルを付与すること。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-context-review"', content)
        # 条件付き（if [[ "${AUTO_CONTEXT_REVIEW}" == "true" ]]）であること
        self.assertIn('AUTO_CONTEXT_REVIEW}" == "true"', content)

    def test_akm_workflow_includes_auto_context_review_in_root_ref(self) -> None:
        """AKM ワークフローの ROOT_REF に auto-context-review が含まれること。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn("auto-context-review: %s", content)

    def test_akm_workflow_creates_auto_context_review_label(self) -> None:
        """AKM ワークフローのラベル bootstrap で auto-context-review が作成されること。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn('create_label "auto-context-review"', content)

    def test_akm_step_labels_include_auto_context_review_conditionally(self) -> None:
        """AKM ワークフローの Step Issue ラベルに auto-context-review が条件付きで含まれること。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn('"auto-context-review"', content)


class TestAqodWorkflowEnableReview(unittest.TestCase):
    """AQOD ワークフローが enable_review を正しくパース・適用することを検証する（Phase 6 修正）。"""

    def _read_workflow(self, filename: str) -> str:
        return (_WORKFLOW_DIR / filename).read_text(encoding="utf-8")

    def test_aqod_workflow_parses_review_section(self) -> None:
        """AQOD ワークフローが ### レビュー設定 セクションをパースすること。"""
        content = self._read_workflow("auto-aqod.yml")
        self.assertIn("レビュー設定", content)
        self.assertIn("auto_context_review", content)

    def test_aqod_workflow_has_auto_context_review_variable(self) -> None:
        """AQOD ワークフローが AUTO_CONTEXT_REVIEW bash 変数を持つこと。"""
        content = self._read_workflow("auto-aqod.yml")
        self.assertIn("AUTO_CONTEXT_REVIEW", content)

    def test_aqod_workflow_step_issue_uses_dynamic_context_review(self) -> None:
        """AQOD ワークフローの Step Issue の auto-context-review がハードコード true でないこと。"""
        content = self._read_workflow("auto-aqod.yml")
        # ハードコード "<!-- auto-context-review: true -->" が除去されていること
        self.assertNotIn('"<!-- auto-context-review: true -->"', content)
        # 動的値が使われていること
        self.assertIn("auto_context_review", content)

    def test_aqod_workflow_labels_not_hardcoded_with_auto_context_review(self) -> None:
        """AQOD ワークフローの LABELS が auto-context-review を常に含まないこと。"""
        content = self._read_workflow("auto-aqod.yml")
        # 以前のハードコード: LABELS='["aqod:ready","auto-context-review"]'
        self.assertNotIn('\'["aqod:ready","auto-context-review"]\'', content)

    def test_aqod_workflow_adds_auto_context_review_label_conditionally(self) -> None:
        """AQOD ワークフローが AUTO_CONTEXT_REVIEW 条件付きでラベルを付与すること。"""
        content = self._read_workflow("auto-aqod.yml")
        self.assertIn('AUTO_CONTEXT_REVIEW}" == "true"', content)


class TestEnableAutoMerge(unittest.TestCase):
    """enable_auto_merge が Issue Template 専用として明記されていることを検証する（Phase 6 確認）。"""

    def _read_template(self, filename: str) -> str:
        return (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")

    def _read_diff_spec(self) -> str:
        return _DIFF_SPEC.read_text(encoding="utf-8")

    def test_all_target_templates_have_enable_auto_merge(self) -> None:
        """全対象 Issue Template が enable_auto_merge を持つこと。"""
        for template in _TEMPLATES_WITH_AUTO_MERGE:
            with self.subTest(template=template):
                content = self._read_template(template)
                self.assertIn("id: enable_auto_merge", content)

    def test_diff_spec_documents_enable_auto_merge_as_issue_template_only(self) -> None:
        """差分仕様ドキュメントに enable_auto_merge が Issue Template 専用として明記されていること。"""
        content = self._read_diff_spec()
        self.assertIn("enable_auto_merge", content)
        self.assertIn("Issue Template 専用", content)

    def test_diff_spec_documents_hve_non_support_reason(self) -> None:
        """差分仕様ドキュメントに hve 非対応の理由が記載されていること。"""
        content = self._read_diff_spec()
        # Phase 6 のセクションで hve 非対応が明記されていること
        self.assertIn("hve への大規模 auto merge 実装は Phase 6 スコープ外", content)


class TestModelDropdown(unittest.TestCase):
    """model ドロップダウンが Auto のみであることを検証する（Phase 6 確認）。"""

    def _read_template(self, filename: str) -> str:
        return (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")

    def _read_diff_spec(self) -> str:
        return _DIFF_SPEC.read_text(encoding="utf-8")

    def test_all_templates_have_model_auto_only(self) -> None:
        """全対象テンプレートの model ドロップダウンが Auto のみであること。"""
        for template in _TEMPLATES_WITH_MODEL:
            with self.subTest(template=template):
                content = self._read_template(template)
                # model フィールドの options ブロックを抽出
                m = re.search(
                    r'id:\s*model.*?options:\s*\n(.*?)(?:\n\s{2,}\w|\Z)',
                    content,
                    re.DOTALL,
                )
                self.assertIsNotNone(m, f"{template}: model フィールドが見つかりません")
                if m:
                    options_text = m.group(1)
                    # Auto が存在すること
                    self.assertIn('"Auto"', options_text)
                    # Auto 以外の選択肢が存在しないこと
                    other_options = [
                        line.strip()
                        for line in options_text.splitlines()
                        if line.strip().startswith("- ") and '"Auto"' not in line
                    ]
                    self.assertEqual(
                        other_options,
                        [],
                        f"{template}: model に Auto 以外の選択肢が存在します: {other_options}",
                    )

    def test_diff_spec_documents_model_auto_only_policy(self) -> None:
        """差分仕様ドキュメントに model=Auto のみの方針が記載されていること。"""
        content = self._read_diff_spec()
        self.assertIn("Auto", content)
        self.assertIn("HVE_MODEL_OVERRIDE", content)
        self.assertIn("将来の拡張用プレースホルダー", content)


class TestDiffSpecCompleteness(unittest.TestCase):
    """差分仕様ドキュメントに必要な Phase 6 情報が記載されていることを検証する。"""

    def _read_diff_spec(self) -> str:
        return _DIFF_SPEC.read_text(encoding="utf-8")

    def test_diff_spec_has_phase6_section(self) -> None:
        """差分仕様ドキュメントに Phase 6 セクションが存在すること。"""
        content = self._read_diff_spec()
        self.assertIn("Phase 6", content)

    def test_diff_spec_has_hve_only_options(self) -> None:
        """差分仕様ドキュメントに hve のみのオプション一覧が記載されていること。"""
        content = self._read_diff_spec()
        self.assertIn("apply_qa_improvements_to_main", content)
        self.assertIn("apply_review_improvements_to_main", content)
        self.assertIn("apply_self_improve_to_main", content)
        self.assertIn("reuse_context_filtering", content)
        self.assertIn("qa_phase", content)
        self.assertIn("auto_coding_agent_review", content)

    def test_diff_spec_has_issue_template_only_options(self) -> None:
        """差分仕様ドキュメントに Issue Template のみのオプション一覧が記載されていること。"""
        content = self._read_diff_spec()
        self.assertIn("enable_auto_merge", content)

    def test_diff_spec_work_iq_is_hve_only(self) -> None:
        """差分仕様ドキュメントに Work IQ が hve 専用として記載されていること。"""
        content = self._read_diff_spec()
        self.assertIn("Work IQ", content)
        self.assertIn("hve 経路専用", content)

    def test_diff_spec_has_qa_phase_policy(self) -> None:
        """差分仕様ドキュメントに qa_phase の hve 専用方針が記載されていること。"""
        content = self._read_diff_spec()
        self.assertIn("qa_phase", content)
        self.assertIn("hve 専用", content)


if __name__ == "__main__":
    unittest.main()
