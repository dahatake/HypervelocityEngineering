"""test_prompts.py — プロンプト定数が空でないことのテスト"""

from __future__ import annotations

import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from prompts import (
    ADVERSARIAL_RECHECK_PROMPT,
    CODE_REVIEW_AGENT_FIX_PROMPT,
    MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT,
    PRE_EXECUTION_QA_COMMENT_MARKER,
    PRE_EXECUTION_QA_PROMPT_V2,
    QA_PROMPT_V2,
    REVIEW_PROMPT,
    render_pre_execution_qa_comment_body,
)

# FR-QA-01 / FR-QA-02 で全経路が共有する説明項目名と、深さルールの必須語。
_DEPTH_FIELD_NAMES = ("背景と根拠", "判断の観点")
_DEPTH_RULE_PHRASES = ("記述の深さ", "出典", "未確認", "評価軸", "他の選択肢", "1 行で記述")


class TestPromptsNotEmpty(unittest.TestCase):
    """プロンプト定数が文字列であり、空でないことを検証する。"""

    def test_review_prompt_is_str(self) -> None:
        self.assertIsInstance(REVIEW_PROMPT, str)

    def test_review_prompt_not_empty(self) -> None:
        self.assertTrue(REVIEW_PROMPT.strip(), "REVIEW_PROMPT should not be empty")

    def test_review_prompt_mentions_adversarial_review(self) -> None:
        """REVIEW_PROMPT には敵対的レビューの6軸検証に関する記述が含まれる。"""
        self.assertIn("敵対的レビュアー", REVIEW_PROMPT)
        self.assertIn("要件充足性", REVIEW_PROMPT)
        self.assertIn("合格判定", REVIEW_PROMPT)


class TestCodeReviewAgentFixPrompt(unittest.TestCase):
    """CODE_REVIEW_AGENT_FIX_PROMPT の検証。"""

    def test_code_review_agent_fix_prompt_is_str(self) -> None:
        self.assertIsInstance(CODE_REVIEW_AGENT_FIX_PROMPT, str)

    def test_code_review_agent_fix_prompt_not_empty(self) -> None:
        self.assertTrue(CODE_REVIEW_AGENT_FIX_PROMPT.strip(), "CODE_REVIEW_AGENT_FIX_PROMPT should not be empty")

    def test_code_review_agent_fix_prompt_has_placeholder(self) -> None:
        """{review_comments} プレースホルダーが含まれることを確認。"""
        self.assertIn("{review_comments}", CODE_REVIEW_AGENT_FIX_PROMPT)


class TestAdversarialRecheckPrompt(unittest.TestCase):
    """ADVERSARIAL_RECHECK_PROMPT の検証。"""

    def test_adversarial_recheck_prompt_is_str(self) -> None:
        self.assertIsInstance(ADVERSARIAL_RECHECK_PROMPT, str)

    def test_adversarial_recheck_prompt_not_empty(self) -> None:
        self.assertTrue(ADVERSARIAL_RECHECK_PROMPT.strip(), "ADVERSARIAL_RECHECK_PROMPT should not be empty")

    def test_adversarial_recheck_prompt_has_cycle_placeholder(self) -> None:
        """{cycle} プレースホルダーが含まれることを確認。"""
        self.assertIn("{cycle}", ADVERSARIAL_RECHECK_PROMPT)


class TestQaPromptV2(unittest.TestCase):
    """QA_PROMPT_V2 の検証。"""

    def test_qa_prompt_v2_is_str(self) -> None:
        self.assertIsInstance(QA_PROMPT_V2, str)

    def test_qa_prompt_v2_not_empty(self) -> None:
        self.assertTrue(QA_PROMPT_V2.strip(), "QA_PROMPT_V2 should not be empty")

    def test_qa_prompt_v2_mentions_priority(self) -> None:
        """QA_PROMPT_V2 には重要度の記述が含まれる。"""
        self.assertIn("重要度", QA_PROMPT_V2)

    def test_qa_prompt_v2_mentions_default_candidate(self) -> None:
        """QA_PROMPT_V2 には既定値候補の記述が含まれる。"""
        self.assertIn("既定値候補", QA_PROMPT_V2)

    def test_qa_prompt_v2_mentions_category(self) -> None:
        """QA_PROMPT_V2 には分類項目の記述が含まれる。"""
        self.assertIn("分類項目", QA_PROMPT_V2)

    def test_qa_prompt_v2_no_fabrication(self) -> None:
        """QA_PROMPT_V2 には捏造禁止の記述が含まれる。"""
        self.assertIn("捏造", QA_PROMPT_V2)

    def test_qa_prompt_v2_alpha_labels(self) -> None:
        """QA_PROMPT_V2 にはアルファベットラベル (A. または A/B/C) の記述が含まれる。"""
        self.assertTrue(
            "A." in QA_PROMPT_V2 or "A/B/C" in QA_PROMPT_V2,
            "QA_PROMPT_V2 should mention alphabetic labels (A. or A/B/C)",
        )

    def test_qa_prompt_v2_requires_background_field(self) -> None:
        """FR-QA-01: 質問テンプレートに「背景と根拠」フィールドがある。"""
        self.assertIn("- 背景と根拠:", QA_PROMPT_V2)

    def test_qa_prompt_v2_requires_viewpoints_field(self) -> None:
        """FR-QA-01: 質問テンプレートに「判断の観点」フィールドがある。"""
        self.assertIn("- 判断の観点:", QA_PROMPT_V2)

    def test_qa_prompt_v2_requires_depth_rules(self) -> None:
        """FR-QA-01: 説明の深さ（出典・未確定・評価軸・他選択肢）を指示する。"""
        for phrase in _DEPTH_RULE_PHRASES:
            self.assertIn(
                phrase, QA_PROMPT_V2,
                msg=f"QA_PROMPT_V2 に深さルールの語が無い: {phrase}",
            )


class TestPreExecutionQaPromptV2(unittest.TestCase):
    def test_is_string(self) -> None:
        self.assertIsInstance(PRE_EXECUTION_QA_PROMPT_V2, str)

    def test_not_empty(self) -> None:
        self.assertGreater(len(PRE_EXECUTION_QA_PROMPT_V2.strip()), 0)

    def test_contains_required_keywords(self) -> None:
        self.assertIn("重要度", PRE_EXECUTION_QA_PROMPT_V2)
        self.assertIn("分類項目", PRE_EXECUTION_QA_PROMPT_V2)
        self.assertIn("既定値候補", PRE_EXECUTION_QA_PROMPT_V2)
        self.assertIn("捏造", PRE_EXECUTION_QA_PROMPT_V2)

    def test_contains_pre_execution_specific_text(self) -> None:
        self.assertIn("成果物はまだ存在しません", PRE_EXECUTION_QA_PROMPT_V2)

    def test_different_from_qa_prompt_v2(self) -> None:
        self.assertNotEqual(PRE_EXECUTION_QA_PROMPT_V2, QA_PROMPT_V2)

    def test_contains_issue_comment_replication_instruction(self) -> None:
        self.assertIn("この Issue のコメントとしても投稿してください", PRE_EXECUTION_QA_PROMPT_V2)

    def test_requires_background_field(self) -> None:
        """FR-QA-01: 質問テンプレートに「背景と根拠」フィールドがある。"""
        self.assertIn("- 背景と根拠:", PRE_EXECUTION_QA_PROMPT_V2)

    def test_requires_viewpoints_field(self) -> None:
        """FR-QA-01: 質問テンプレートに「判断の観点」フィールドがある。"""
        self.assertIn("- 判断の観点:", PRE_EXECUTION_QA_PROMPT_V2)

    def test_requires_depth_rules(self) -> None:
        """FR-QA-01: 説明の深さ（出典・未確定・評価軸・他選択肢）を指示する。"""
        for phrase in _DEPTH_RULE_PHRASES:
            self.assertIn(
                phrase, PRE_EXECUTION_QA_PROMPT_V2,
                msg=f"PRE_EXECUTION_QA_PROMPT_V2 に深さルールの語が無い: {phrase}",
            )


class TestQuestionnaireSkillFieldParity(unittest.TestCase):
    """FR-QA-02: Skill 側テンプレートがプロンプトと同一の説明項目を宣言する。"""

    _SKILL_FILES = (
        ".github/skills/task-questionnaire/SKILL.md",
        ".github/skills/task-questionnaire/references/standalone-protocol.md",
        ".github/skills/task-questionnaire/references/pr-protocol.md",
    )

    def test_skill_templates_declare_same_depth_fields_as_prompts(self) -> None:
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        for rel in self._SKILL_FILES:
            path = repo_root / rel
            self.assertTrue(path.is_file(), msg=f"Skill ファイルが見つからない: {rel}")
            text = path.read_text(encoding="utf-8")
            for field in _DEPTH_FIELD_NAMES:
                self.assertIn(field, text, msg=f"{rel} が '{field}' を宣言していない")


class TestPreExecutionQaCommentBody(unittest.TestCase):
    def test_contains_marker_and_copilot_mention(self) -> None:
        comment_body = render_pre_execution_qa_comment_body()
        self.assertTrue(comment_body.startswith(f"{PRE_EXECUTION_QA_COMMENT_MARKER}\n@copilot\n\n"))

    def test_contains_canonical_prompt_body(self) -> None:
        comment_body = render_pre_execution_qa_comment_body()
        self.assertIn(PRE_EXECUTION_QA_PROMPT_V2, comment_body)


class TestMainArtifactImprovementApplyPrompt(unittest.TestCase):
    """MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT の検証。"""

    def test_is_str(self) -> None:
        self.assertIsInstance(MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT, str)

    def test_not_empty(self) -> None:
        self.assertGreater(len(MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT.strip()), 0)

    def test_required_placeholders(self) -> None:
        """必須プレースホルダーがすべて含まれる。"""
        for ph in (
            "{source_phase}", "{workflow_id}", "{step_id}", "{step_title}",
            "{custom_agent}", "{original_prompt}", "{main_output}", "{improvement_context}",
        ):
            self.assertIn(ph, MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT, msg=f"Missing placeholder: {ph}")

    def test_contains_no_fabrication_rule(self) -> None:
        """捏造禁止の記述が含まれる。"""
        self.assertIn("捏造", MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT)

    def test_contains_work_iq(self) -> None:
        """Work IQ への言及が含まれる。"""
        self.assertIn("Work IQ", MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT)

    def test_contains_work_iq_status_unavailable(self) -> None:
        self.assertIn("STATUS: UNAVAILABLE", MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT)

    def test_contains_work_iq_status_not_found(self) -> None:
        self.assertIn("STATUS: NOT_FOUND", MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT)

    def test_contains_work_iq_status_found(self) -> None:
        self.assertIn("STATUS: FOUND", MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT)

    def test_contains_work_iq_status_partial(self) -> None:
        self.assertIn("STATUS: PARTIAL", MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT)

    def test_contains_original_docs_rule(self) -> None:
        """docs-original/ 変更禁止の記述が含まれる。"""
        self.assertIn("docs-original/", MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT)

    def test_contains_readme_prohibition(self) -> None:
        """/README.md 変更禁止の記述が含まれる。"""
        self.assertIn("/README.md", MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT)

    def test_contains_adi_questionnaire_format_rule(self) -> None:
        """ADI Step 1.1 / 1.2 の原本質問票形式維持ルールが含まれる。"""
        self.assertIn("ADI 原本質問票", MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT)
        self.assertIn("`1.1` または `1.2`", MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT)
        self.assertNotIn("aq" + "od", MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT.lower())

    def test_format_with_placeholders_works(self) -> None:
        """プレースホルダーを埋めた場合、KeyError が発生しないことを確認。"""
        try:
            result = MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT.format(
                source_phase="Phase 3",
                workflow_id="adi",
                step_id="1.1",
                step_title="テスト",
                custom_agent="TestAgent",
                original_prompt="プロンプト",
                main_output="成果物",
                improvement_context="改善材料",
            )
            self.assertIsInstance(result, str)
            self.assertGreater(len(result), 0)
        except KeyError as e:
            self.fail(f"MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT.format() raised KeyError: {e}")


class TestReviewPromptNoLowerBound(unittest.TestCase):
    """レビュープロンプトが指摘数の下限を強制しないことを検証する。"""

    def test_review_prompt_no_minimum_count_enforcement(self) -> None:
        """REVIEW_PROMPT に「15〜50個」のような下限指定が含まれないこと。"""
        self.assertNotIn("15〜50", REVIEW_PROMPT,
                         "REVIEW_PROMPT に下限指定 '15〜50' が含まれています。0件を許容する形式に変更してください。")

    def test_review_prompt_allows_zero_issues(self) -> None:
        """REVIEW_PROMPT が 0 件を許容する表現を持つこと。"""
        self.assertIn("0〜30", REVIEW_PROMPT,
                      "REVIEW_PROMPT に '0〜30' の表現が含まれていません。問題がない場合を明示してください。")

    def test_review_prompt_no_fabrication(self) -> None:
        """REVIEW_PROMPT に捏造禁止の記述が含まれること。"""
        self.assertIn("捏造", REVIEW_PROMPT)


class TestYamlWorkflowPromptDrift(unittest.TestCase):
    """copilot-auto-feedback.yml と hve/prompts.py のプロンプトドリフト検出テスト。

    hve/prompts.py を canonical source とし、YAML 側が取得経路のみを持つことを確認する。
    """

    _YAML_PATH = str(
        pathlib.Path(__file__).resolve().parent.parent.parent
        / ".github" / "workflows" / "copilot-auto-feedback.yml"
    )

    def _read_yaml_content(self) -> str:
        """YAML ファイルの内容を返す。ファイルが存在しない場合はスキップ。"""
        path = os.path.normpath(self._YAML_PATH)
        if not os.path.exists(path):
            self.skipTest(f"YAML ファイルが見つかりません: {path}")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_yaml_review_no_minimum_count(self) -> None:
        """YAML auto-review プロンプトに '15〜50' の下限指定が含まれないこと。"""
        content = self._read_yaml_content()
        self.assertNotIn("15〜50", content,
                         "copilot-auto-feedback.yml に下限指定 '15〜50' が含まれています。"
                         "0件を許容する表現（0〜30）に統一してください。")

    def test_yaml_review_allows_zero_issues(self) -> None:
        """YAML auto-review プロンプトに '0〜30' の表現が含まれること。"""
        content = self._read_yaml_content()
        self.assertIn("0〜30", content,
                      "copilot-auto-feedback.yml に '0〜30' の表現が含まれていません。"
                      "問題がない場合は 0 件でよいことを明示してください。")

    def test_yaml_pre_qa_uses_hve_prompt_emitter(self) -> None:
        """YAML auto-qa-on-issue が hve CLI の prompt emitter を使うこと。"""
        content = self._read_yaml_content()
        self.assertIn("python3 -m hve emit-prompt pre-qa --comment-body", content)

    def test_yaml_pre_qa_does_not_inline_prompt_body(self) -> None:
        """YAML auto-qa-on-issue に pre-QA プロンプト本文が直書きされていないこと。"""
        content = self._read_yaml_content()
        self.assertNotIn(
            "これから実行するタスクのプロンプトに対して、以下の手順で事前質問票を作成してください。",
            content,
        )

    def test_yaml_review_no_fabrication_rule(self) -> None:
        """YAML auto-review プロンプトに捏造禁止の記述が含まれること。"""
        content = self._read_yaml_content()
        self.assertIn("捏造は絶対に禁止", content)


class TestYamlWorkflowPromptDriftPhase3(unittest.TestCase):
    """Phase 3 で追加した QA/Review 反映マーカーが copilot-auto-feedback.yml に存在することを検証する。"""

    _YAML_PATH = str(
        pathlib.Path(__file__).resolve().parent.parent.parent
        / ".github" / "workflows" / "copilot-auto-feedback.yml"
    )

    def _read_yaml_content(self) -> str:
        path = os.path.normpath(self._YAML_PATH)
        if not os.path.exists(path):
            self.skipTest(f"YAML ファイルが見つかりません: {path}")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_review_prompt_contains_improvement_application_section(self) -> None:
        """auto-review プロンプトに 'Review Improvement Application' セクションが含まれること。"""
        content = self._read_yaml_content()
        self.assertIn("Review Improvement Application", content,
                      "copilot-auto-feedback.yml に 'Review Improvement Application' が含まれていません。")

    def test_review_prompt_contains_modified_artifacts(self) -> None:
        """auto-review プロンプトに 'Modified Artifacts' セクションが含まれること。"""
        content = self._read_yaml_content()
        self.assertIn("Modified Artifacts", content,
                      "copilot-auto-feedback.yml に 'Modified Artifacts' が含まれていません。")

    def test_review_prompt_contains_remaining_findings(self) -> None:
        """auto-review プロンプトに 'Remaining Findings' セクションが含まれること。"""
        content = self._read_yaml_content()
        self.assertIn("Remaining Findings", content,
                      "copilot-auto-feedback.yml に 'Remaining Findings' が含まれていません。")

    def test_review_prompt_contains_verdict_after_fix_marker(self) -> None:
        """auto-review プロンプトに 'review-verdict-after-fix' マーカーが含まれること。"""
        content = self._read_yaml_content()
        self.assertIn("review-verdict-after-fix", content,
                      "copilot-auto-feedback.yml に 'review-verdict-after-fix' マーカーが含まれていません。")

    def test_review_prompt_preserves_existing_verdict_marker(self) -> None:
        """既存の 'review-verdict: PASS/FAIL' マーカーが維持されていること（後方互換）。"""
        content = self._read_yaml_content()
        self.assertIn("review-verdict: PASS", content,
                      "既存の 'review-verdict: PASS' マーカーが削除されています。後方互換を維持してください。")
        self.assertIn("review-verdict: FAIL", content,
                      "既存の 'review-verdict: FAIL' マーカーが削除されています。後方互換を維持してください。")

    def test_qa_prompt_contains_qa_context_usage(self) -> None:
        """SSoT の comment body に 'QA Context Usage' セクションが含まれること。"""
        content = render_pre_execution_qa_comment_body()
        self.assertIn("QA Context Usage", content)

    def test_qa_prompt_contains_qa_dir_reference(self) -> None:
        """SSoT の comment body に qa/ ディレクトリへの参照が含まれること。"""
        content = render_pre_execution_qa_comment_body()
        self.assertIn("qa/", content)

    def test_qa_prompt_contains_reflection_instruction(self) -> None:
        """SSoT の comment body に QA 回答を成果物に反映する指示が含まれること。"""
        content = render_pre_execution_qa_comment_body()
        self.assertIn("成果物に反映", content)

    def test_qa_prompt_contains_reason_recording_instruction(self) -> None:
        """SSoT の comment body に未反映理由の記録指示が含まれること。"""
        content = render_pre_execution_qa_comment_body()
        self.assertIn("理由を完了コメントまたは成果物内に記録", content)


class TestPreExecutionQaPromptV2Phase5(unittest.TestCase):
    """Phase 5: PRE_EXECUTION_QA_PROMPT_V2 に QA Context Usage / qa/ 参照 / 反映指示 / 理由記録が含まれることを検証する。

    Phase 3 で YAML 側に追加した QA Context Usage セクションが
    hve 側の canonical source にも反映されていることを静的に確認する。
    """

    def test_contains_qa_context_usage_section(self) -> None:
        """PRE_EXECUTION_QA_PROMPT_V2 に 'QA Context Usage' セクションが含まれること。"""
        self.assertIn("QA Context Usage", PRE_EXECUTION_QA_PROMPT_V2,
                      "PRE_EXECUTION_QA_PROMPT_V2 に 'QA Context Usage' セクションがありません。"
                      "Phase 3 で追加した同期対象セクションです。")

    def test_contains_qa_dir_reference(self) -> None:
        """PRE_EXECUTION_QA_PROMPT_V2 に 'qa/' ディレクトリへの参照が含まれること。"""
        self.assertIn("qa/", PRE_EXECUTION_QA_PROMPT_V2,
                      "PRE_EXECUTION_QA_PROMPT_V2 に 'qa/' への参照がありません。")

    def test_contains_prerequisite_instruction(self) -> None:
        """PRE_EXECUTION_QA_PROMPT_V2 に QA 回答を成果物の前提要件として扱う指示が含まれること。"""
        self.assertIn("成果物の前提要件として扱い", PRE_EXECUTION_QA_PROMPT_V2,
                      "PRE_EXECUTION_QA_PROMPT_V2 に成果物への前提要件反映指示がありません。")

    def test_contains_reason_recording_instruction(self) -> None:
        """PRE_EXECUTION_QA_PROMPT_V2 に未反映理由の記録指示が含まれること。"""
        self.assertIn("理由を完了コメントまたは成果物内に記録", PRE_EXECUTION_QA_PROMPT_V2,
                      "PRE_EXECUTION_QA_PROMPT_V2 に未反映理由の記録指示がありません。")


class TestYamlWorkflowPromptDriftPhase5(unittest.TestCase):
    """Phase 5: copilot-auto-feedback.yml の同期コメント・冪等化マーカー・opt-out マーカーを検証する。

    これらのマーカーが削除・変更された場合に検出できるよう静的テストで保護する。
    """

    _YAML_PATH = str(
        pathlib.Path(__file__).resolve().parent.parent.parent
        / ".github" / "workflows" / "copilot-auto-feedback.yml"
    )

    def _read_yaml_content(self) -> str:
        path = os.path.normpath(self._YAML_PATH)
        if not os.path.exists(path):
            self.skipTest(f"YAML ファイルが見つかりません: {path}")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_yaml_has_pre_execution_qa_cli_source(self) -> None:
        """YAML が emit-prompt 経路を使い、手動同期コメントに依存しないこと。"""
        content = self._read_yaml_content()
        self.assertIn("python3 -m hve emit-prompt pre-qa --comment-body", content)
        self.assertNotIn("hve/prompts.py:PRE_EXECUTION_QA_PROMPT_V2", content)

    def test_yaml_has_auto_qa_idempotency_marker(self) -> None:
        """YAML auto-qa ジョブに冪等化マーカー 'copilot-auto-qa-posted' が含まれること。"""
        content = self._read_yaml_content()
        self.assertIn("copilot-auto-qa-posted", content,
                      "copilot-auto-feedback.yml に 'copilot-auto-qa-posted' マーカーがありません。"
                      "auto-qa ジョブの冪等化が失われています。")

    def test_yaml_has_auto_review_idempotency_marker(self) -> None:
        """YAML auto-review ジョブに冪等化マーカー 'copilot-auto-review-posted' が含まれること。"""
        content = self._read_yaml_content()
        self.assertIn("copilot-auto-review-posted", content,
                      "copilot-auto-feedback.yml に 'copilot-auto-review-posted' マーカーがありません。"
                      "auto-review ジョブの冪等化が失われています。")

    def test_yaml_has_pre_qa_on_issue_idempotency_marker(self) -> None:
        """YAML auto-qa-on-issue ジョブに冪等化マーカー 'copilot-auto-pre-qa-posted' が含まれること。"""
        content = self._read_yaml_content()
        self.assertIn("copilot-auto-pre-qa-posted", content,
                      "copilot-auto-feedback.yml に 'copilot-auto-pre-qa-posted' マーカーがありません。"
                      "auto-qa-on-issue ジョブの冪等化が失われています。")

    def test_yaml_sets_up_python_and_installs_hve_for_pre_qa_issue_job(self) -> None:
        """auto-qa-on-issue ジョブが Python 3.11 と hve editable install を設定すること。"""
        content = self._read_yaml_content()
        self.assertIn("actions/setup-python@v5", content)
        self.assertIn('python-version: "3.11"', content)
        self.assertIn("python3 -m pip install -e .", content)

    def test_yaml_assigns_copilot_to_issue_after_pre_qa_comment(self) -> None:
        """auto-qa-on-issue ジョブが feature flag 下で Copilot アサインと qa-drafting 遷移を行うこと。"""
        content = self._read_yaml_content()
        self.assertIn("Diagnostic — トリガー条件確認", content)
        self.assertIn("COMMENT_BODY preview (先頭500文字)", content)
        self.assertIn("ENABLE_COPILOT_QA_ASSIGN", content)
        self.assertIn("source \"${GITHUB_WORKSPACE}/.github/scripts/bash/lib/copilot-assign.sh\"", content)
        self.assertIn(':qa-drafting', content)
        self.assertIn("qa_state_count", content)
        self.assertIn("複数の QA 状態ラベル", content)
        drafting_add = content.index('--add-label "${QA_DRAFTING_LABEL}"')
        ready_delete = content.index('/labels/${QA_READY_LABEL}', drafting_add)
        self.assertLess(drafting_add, ready_delete)
        self.assertIn("qa-drafting をロールバック", content)
        self.assertIn("final_labels_json", content)

    def test_pre_qa_assignment_accepts_and_validates_hyphenated_branch(self) -> None:
        """pre-QA assign が feature/foo-bar を main へ誤フォールバックしないこと。"""
        content = self._read_yaml_content()
        self.assertIn("r'<!--\\s*branch:\\s*([^>]+?)\\s*-->'", content)
        self.assertIn('[[ "${BRANCH}" =~ ^[A-Za-z0-9._/-]+$', content)
        self.assertIn('"${BRANCH}" != *".."*', content)

    def test_yaml_has_adversarial_review_opt_out_marker(self) -> None:
        """YAML auto-review ジョブに専用 opt-out マーカーが含まれること。"""
        content = self._read_yaml_content()
        self.assertIn("adversarial-review: false", content,
                      "copilot-auto-feedback.yml に 'adversarial-review: false' opt-out マーカーの参照がありません。"
                      "レビューの opt-out 機能が失われています。")


class TestQaDraftingLabels(unittest.TestCase):
    """qa-drafting ラベル定義の静的検証。"""

    _LABELS_PATH = str(
        pathlib.Path(__file__).resolve().parent.parent.parent
        / ".github" / "labels.json"
    )

    def test_labels_json_has_all_qa_drafting_labels(self) -> None:
        path = os.path.normpath(self._LABELS_PATH)
        if not os.path.exists(path):
            self.fail(f"labels.json が見つかりません: {path}")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        for label in [
            "aas:qa-drafting",
            "aad:qa-drafting",
            "aad-web:qa-drafting",
            "asdw:qa-drafting",
            "asdw-web:qa-drafting",
            "adfd:qa-drafting",
            "adfdv:qa-drafting",
            "aag:qa-drafting",
            "aagd:qa-drafting",
            "akm:qa-drafting",
            "adoc:qa-drafting",
        ]:
            self.assertIn(label, content)


class TestOverEngineeringBan(unittest.TestCase):
    """質問票・レビュー系プロンプトに OE 禁止文言が含まれていること。"""

    OE_MARKER = "オーバーエンジニアリングは絶対に禁止"

    def test_oe_ban_text_constants_exist(self) -> None:
        from prompts import OVERENGINEERING_BAN_TEXT, OVERENGINEERING_BAN_TEXT_QA
        self.assertIn(self.OE_MARKER, OVERENGINEERING_BAN_TEXT)
        self.assertIn(self.OE_MARKER, OVERENGINEERING_BAN_TEXT_QA)
        self.assertIn("YAGNI", OVERENGINEERING_BAN_TEXT)

    def test_review_prompts_contain_oe_ban(self) -> None:
        from prompts import (
            ADVERSARIAL_RECHECK_PROMPT,
            CODE_REVIEW_CLI_PROMPT,
            REVIEW_PROMPT,
        )
        for name, body in [
            ("REVIEW_PROMPT", REVIEW_PROMPT),
            ("ADVERSARIAL_RECHECK_PROMPT", ADVERSARIAL_RECHECK_PROMPT),
            ("CODE_REVIEW_CLI_PROMPT", CODE_REVIEW_CLI_PROMPT),
        ]:
            self.assertIn(self.OE_MARKER, body, f"{name} missing OE ban")

    def test_questionnaire_prompts_contain_oe_ban(self) -> None:
        from prompts import (
            PRE_EXECUTION_QA_PROMPT_V2,
            QA_PROMPT_V2,
        )
        for name, body in [
            ("PRE_EXECUTION_QA_PROMPT_V2", PRE_EXECUTION_QA_PROMPT_V2),
            ("QA_PROMPT_V2", QA_PROMPT_V2),
        ]:
            self.assertIn(self.OE_MARKER, body, f"{name} missing OE ban")

    def test_review_prompt_has_sixth_axis(self) -> None:
        """REVIEW_PROMPT に第 6 軸（オーバーエンジニアリング検出）が追加されている。"""
        from prompts import REVIEW_PROMPT
        self.assertIn("6つの検証軸", REVIEW_PROMPT)
        self.assertIn("オーバーエンジニアリング検出", REVIEW_PROMPT)

    def test_fanout_common_files_contain_oe_ban(self) -> None:
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        fanout_root = repo_root / "hve" / "prompt" / "fanout"
        common_files = sorted(fanout_root.glob("*/_common.md"))
        self.assertEqual(len(common_files), 11, "Expected 11 fanout _common.md files")
        for f in common_files:
            content = f.read_text(encoding="utf-8")
            self.assertIn(self.OE_MARKER, content, f"{f} missing OE ban")


if __name__ == "__main__":
    unittest.main()
