"""Prompt 内レビュー観点と敵対的レビュー発動条件の分離契約。

各 Prompt のドメイン固有レビュー観点は通常時の単回セルフチェックとして使い、
Prompt 本文だけで Review Sub-agent や反復レビューを起動しないことを固定する。
敵対的レビューの発動条件は Skill ``adversarial-review`` が所有する。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest
import yaml  # type: ignore[import-untyped]


_REPO_ROOT = Path(__file__).resolve().parents[2]
_REVIEW_SKILL = (
    _REPO_ROOT / ".github" / "skills" / "harness" / "adversarial-review" / "SKILL.md"
)
_REVIEW_RULES = _REVIEW_SKILL.parent / "references" / "review-activation-rules.md"
_COMMON_PREAMBLE = (
    _REPO_ROOT / ".github" / "skills" / "agent-common-preamble" / "SKILL.md"
)
_CLOUD_REVIEW_WORKFLOWS = (
    _REPO_ROOT / ".github" / "workflows" / "copilot-auto-feedback.yml",
    _REPO_ROOT / ".github" / "workflows" / "auto-review-to-approve-transition.yml",
    _REPO_ROOT / ".github" / "workflows" / "auto-qa-to-review-transition.yml",
    _REPO_ROOT / ".github" / "workflows" / "auto-pr-transition-dispatcher.yml",
    _REPO_ROOT / ".github" / "workflows" / "auto-create-subissues-transition.yml",
    _REPO_ROOT / ".github" / "workflows" / "sync-issue-labels-to-pr.yml",
)
_ROOT_CLOUD_REVIEW_PRODUCERS = tuple(
    _REPO_ROOT / ".github" / "workflows" / name
    for name in (
        "auto-ai-agent-design-reusable.yml",
        "auto-ai-agent-dev-reusable.yml",
        "auto-app-detail-design-web-reusable.yml",
        "auto-app-dev-microservice-web-reusable.yml",
        "auto-app-documentation-reusable.yml",
        "auto-app-selection-reusable.yml",
        "auto-dataflow-design-reusable.yml",
        "auto-dataflow-dev-reusable.yml",
        "auto-knowledge-management-reusable.yml",
    )
)
_INHERITED_CLOUD_REVIEW_PRODUCERS = tuple(
    _REPO_ROOT / ".github" / "workflows" / name
    for name in (
        "create-subissues-from-pr.yml",
        "advance-subissues.yml",
    )
)
_CLOUD_REVIEW_PRODUCERS = (
    *_ROOT_CLOUD_REVIEW_PRODUCERS,
    *_INHERITED_CLOUD_REVIEW_PRODUCERS,
)
_REVIEW_ISSUE_TEMPLATES = tuple(
    _REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / name
    for name in (
        "ai-agent-design.yml",
        "ai-agent-dev.yml",
        "app-architecture-design.yml",
        "dataflow-design.yml",
        "dataflow-dev.yml",
        "knowledge-management.yml",
        "sourcecode-to-documentation.yml",
        "web-app-design.yml",
        "web-app-dev.yml",
    )
)
_REVIEW_CHECKLIST = _REVIEW_SKILL.parent / "references" / "five-axis-checklist.md"
_REVIEW_EVAL = (
    _REPO_ROOT / ".github" / "skills" / "_evals" / "adversarial-review.eval.yaml"
)
_LABELS = _REPO_ROOT / ".github" / "labels.json"

_CLOUD_PROMPT_REF_RE = re.compile(r'"(\.github/prompts/cloud/[^"]+\.prompt\.md)"')


def _with_referenced_cloud_prompts(workflow_text: str) -> str:
    """Workflow が実行時に読み込む外部 Prompt を連結した実効内容を返す。"""
    parts = [workflow_text]
    for rel in sorted(set(_CLOUD_PROMPT_REF_RE.findall(workflow_text))):
        path = _REPO_ROOT / rel
        assert path.is_file(), f"referenced cloud prompt is missing: {rel}"
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)
_CREATE_SUBISSUES_CONSUMER = (
    _REPO_ROOT / ".github" / "workflows" / "create-subissues-from-pr.yml"
)
_AUTO_APPROVE_WORKFLOW = (
    _REPO_ROOT / ".github" / "workflows" / "auto-approve-and-merge.yml"
)
_R03_PROMPT_RED_CONTRACT = (
    _REPO_ROOT / "hve" / "tests" / "r03_prompt_review_inline_contract.py"
)
_HVE_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "test-hve-python.yml"
_MANUAL_CLOUD_PRODUCERS = tuple(
    _REPO_ROOT / ".github" / "scripts" / platform / name
    for platform, names in (
        (
            "bash",
            ("orchestrate.sh", "advance.sh", "create-subissues.sh", "run-workflow.sh"),
        ),
        (
            "powershell",
            ("orchestrate.ps1", "advance.ps1", "create-subissues.ps1", "run-workflow.ps1"),
        ),
    )
    for name in names
)
_HVE_ISSUE_PRODUCER_FILES = (
    _REPO_ROOT / "hve" / "template_engine.py",
    _REPO_ROOT / "hve" / "orchestrator.py",
)
_REVIEW_ROUTING_FILES = (
    _REPO_ROOT / ".github" / "copilot-instructions.md",
    _REPO_ROOT / ".github" / "skills" / "_routing" / "README.md",
    _REPO_ROOT / ".github" / "skills" / "work-artifacts-layout" / "SKILL.md",
    _REPO_ROOT
    / ".github"
    / "skills"
    / "output"
    / "large-output-chunking"
    / "SKILL.md",
    _REPO_ROOT
    / ".github"
    / "skills"
    / "knowledge-management"
    / "references"
    / "detail.md",
    _REPO_ROOT
    / ".github"
    / "skills"
    / "harness"
    / "harness-verification-loop"
    / "SKILL.md",
)
_SHARED_INLINE_POLICY = (
    "通常時は、Prompt 固有の観点を1回のインライン・セルフチェックとして"
    "まとめて確認する。"
)
_PROMPT_NOT_TRIGGER_POLICY = (
    "Prompt のレビュー観点は敵対的レビューの発動条件ではない。"
)
_NO_SUBAGENT_POLICY = "通常時は Review Sub-agent を起動しない。"
_HVE_PHASE3_POLICY = (
    "HVE CLI / GUI では `auto_contents_review=true` の場合だけ Phase 3 が実施する。"
)


def test_shared_skill_owns_review_activation_policy() -> None:
    skill = _REVIEW_SKILL.read_text(encoding="utf-8")
    rules = _REVIEW_RULES.read_text(encoding="utf-8")
    for phrase in (
        _SHARED_INLINE_POLICY,
        _PROMPT_NOT_TRIGGER_POLICY,
        _NO_SUBAGENT_POLICY,
        _HVE_PHASE3_POLICY,
        "<!-- adversarial-review: true -->",
        "`adversarial-review` ラベル",
        "ユーザーが敵対的レビューを明示的に依頼した場合",
        "Cloud workflow は一般的な「レビューして」「品質を確認して」等の任意コメントを自然言語判定しない。",
        "PR body の `true` marker を `copilot-auto-feedback.yml` が専用ラベルへ正規化する。",
        "HVE の Python Issue producer（`template_engine.py` / `orchestrator.py`）は `auto_contents_review` を Cloud marker / label へ変換しない。",
        "Cloud resolver は default-disabled としてレビューを起動しない。",
        "Plan-Only は第5の runtime trigger ではなく、Runner に専用の抑止分岐を追加しない。",
        "`task_scope` だけで Runner を抑止すると、明示された HVE Phase 3 まで誤って無効化するため禁止する。",
    ):
        assert phrase in rules
    assert "references/review-activation-rules.md" in skill
    assert _PROMPT_NOT_TRIGGER_POLICY in skill


def test_common_preamble_uses_inline_check_as_the_default() -> None:
    preamble = _COMMON_PREAMBLE.read_text(encoding="utf-8")
    assert _SHARED_INLINE_POLICY in preamble
    assert _NO_SUBAGENT_POLICY in preamble
    assert _HVE_PHASE3_POLICY in preamble


def test_review_skill_metadata_and_references_do_not_broaden_activation() -> None:
    skill = _REVIEW_SKILL.read_text(encoding="utf-8")
    rules = _REVIEW_RULES.read_text(encoding="utf-8")
    checklist = _REVIEW_CHECKLIST.read_text(encoding="utf-8")
    frontmatter = skill.split("---", 2)[1]
    assert "明示的に要求された敵対的レビュー" in frontmatter
    assert "通常のセルフチェック" in frontmatter
    assert "通常のコードレビュー" in frontmatter
    assert "通常の品質確認" in frontmatter
    assert "explicit quality review" not in frontmatter
    assert "5-axis review" not in frontmatter
    assert "6-axis review" not in frontmatter
    for text in (skill, rules, checklist):
        assert "AGENTS.md" not in text
        assert "15〜100" not in text
        assert "15〜50" not in text
    assert "0〜30個" in checklist
    assert "6つの検証軸" in skill
    assert "軸6: オーバーエンジニアリング検出" in checklist


def test_review_skill_eval_matches_activation_ssot() -> None:
    skill = _REVIEW_SKILL.read_text(encoding="utf-8")
    evaluation = _REVIEW_EVAL.read_text(encoding="utf-8")
    for case_id in (
        "explicit-adversarial-review-label",
        "explicit-comment-flag-review",
        "explicit-user-adversarial-review-request",
        "hve-phase3-review",
        "plan-only-with-explicit-marker",
        "auto-context-review-only",
        "ambiguous-review-request-without-flag",
    ):
        assert f"id: {case_id}" in evaluation
    assert "本番デプロイ前という文脈だけでは発動しない" in evaluation
    assert "When to Activate に '本番デプロイ前の最終チェック'" not in evaluation
    assert "6つの検証軸" in evaluation
    assert "5軸" not in evaluation
    assert "明示triggerなしの分割モード（Plan-Only）では省略" in skill
    assert "明示時は実施" in skill


@pytest.mark.parametrize(
    ("path", "required_phrases"),
    (
        (
            _REVIEW_ROUTING_FILES[0],
            (
                "敵対的レビュー（marker / label / 明示的な敵対的レビュー依頼 / HVE Phase 3 のみ）",
                "harness-verification-loop",
            ),
        ),
        (
            _REVIEW_ROUTING_FILES[1],
            ("通常レビュー・品質確認は単回セルフチェック", "harness-verification-loop"),
        ),
        (_REVIEW_ROUTING_FILES[2], ("明示的な敵対的レビューだけ", "単回セルフチェック")),
        (_REVIEW_ROUTING_FILES[3], ("明示的な敵対的レビューだけ", "単回セルフチェック")),
        (_REVIEW_ROUTING_FILES[4], ("明示的な敵対的レビューだけ", "単回セルフチェック")),
        (_REVIEW_ROUTING_FILES[5], ("明示時のみの敵対的レビュー", "通常の自動検証")),
    ),
)
def test_repository_routing_keeps_normal_review_out_of_adversarial_skill(
    path: Path,
    required_phrases: tuple[str, ...],
) -> None:
    text = path.read_text(encoding="utf-8")
    for phrase in required_phrases:
        assert phrase in text, path
    for forbidden in (
        "成果物の品質評価・レビューは adversarial-review が担当",
        "ファイル内容の品質評価は adversarial-review が担当",
        "分割後の各 part の品質検証",
    ):
        assert forbidden not in text, path


@pytest.mark.parametrize("path", _ROOT_CLOUD_REVIEW_PRODUCERS, ids=lambda path: path.name)
def test_each_root_cloud_producer_emits_dedicated_review_contract(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "adversarial_review" in text
    assert "ADVERSARIAL_REVIEW" in text
    assert "auto_context_review" not in text
    assert "AUTO_CONTEXT_REVIEW" not in text
    assert re.search(
        r'create_label\s+"adversarial-review"\s+"B60205"\s+'
        r'"explicit adversarial review trigger for Copilot review workflow"',
        text,
    ), path
    assert "<!-- adversarial-review:" in text
    assert re.search(
        r'add_label\s+"\$\{(?:ROOT_ISSUE|ISSUE_NUMBER)\}"\s+"adversarial-review"',
        text,
    ), path
    reconciliation = re.compile(
        rf'if \[\[ "\$\{{ADVERSARIAL_REVIEW\}}" == "true" \]\]; then\s+'
        rf'add_label "\$\{{ROOT_ISSUE\}}" "adversarial-review".*?\s+else\s+'
        rf'gh issue edit "\$\{{ROOT_ISSUE\}}" --repo "\$\{{REPO\}}" '
        r'--remove-label "adversarial-review"',
        re.DOTALL,
    )
    assert reconciliation.search(text), path
    assert text.count('--remove-label "adversarial-review"') == 1, path


def test_subissue_producers_inherit_dedicated_review_contract() -> None:
    create_subissues = _INHERITED_CLOUD_REVIEW_PRODUCERS[0].read_text(encoding="utf-8")
    advance_subissues = _INHERITED_CLOUD_REVIEW_PRODUCERS[1].read_text(encoding="utf-8")
    assert "HAS_ADVERSARIAL_REVIEW" in create_subissues
    assert "HAS_CONTEXT_REVIEW" not in create_subissues
    assert (
        'gh label create "adversarial-review" --color "B60205" '
        '--description "explicit adversarial review trigger for Copilot review workflow"'
        in create_subissues
    )
    assert 'label_args="${label_args} --label adversarial-review"' in create_subissues
    assert "ADVERSARIAL_REVIEW" in advance_subissues
    assert "<!-- adversarial-review:" in advance_subissues
    assert '"adversarial-review"' in advance_subissues


def test_cloud_review_consumer_normalizes_marker_and_dedicated_label() -> None:
    auto_feedback = _CLOUD_REVIEW_WORKFLOWS[0].read_text(encoding="utf-8")
    auto_review_job = auto_feedback.split("  auto-review:", 1)[1]
    assert "types: [opened, edited, labeled, ready_for_review]" in auto_feedback
    assert 'gh api "/repos/${REPO}/pulls/${PR_NUMBER}"' in auto_review_job
    assert 'contains(["adversarial-review"])' in auto_review_job
    assert "sed '/<!-- START COPILOT ORIGINAL PROMPT -->/,$d'" in auto_review_job
    assert "<!-- adversarial-review: true -->" in auto_review_job
    assert "<!-- adversarial-review: false -->" in auto_review_job
    assert "--add-label \"adversarial-review\"" in auto_review_job
    assert "--remove-label \"adversarial-review\"" in auto_review_job
    assert "敵対的レビューの明示トリガーがないためスキップします。" in auto_review_job
    assert auto_review_job.index("<!-- adversarial-review: false -->") < auto_review_job.index(
        "<!-- adversarial-review: true -->"
    )
    assert '[ "${EVENT_NAME}" = "workflow_dispatch" ]' not in auto_review_job
    # 本文は `.github/prompts/cloud/` へ外部化済みのため、参照先を解決した実効内容を検査する。
    effective_auto_review = _with_referenced_cloud_prompts(auto_review_job)
    assert "6つの検証軸" in effective_auto_review
    assert "5つの検証軸" not in effective_auto_review


def test_cloud_review_transitions_use_dedicated_label_by_role() -> None:
    review_transition = _CLOUD_REVIEW_WORKFLOWS[1].read_text(encoding="utf-8")
    qa_transition = _CLOUD_REVIEW_WORKFLOWS[2].read_text(encoding="utf-8")
    dispatcher = _CLOUD_REVIEW_WORKFLOWS[3].read_text(encoding="utf-8")
    sync_labels = _CLOUD_REVIEW_WORKFLOWS[5].read_text(encoding="utf-8")
    assert 'contains(["adversarial-review"])' in review_transition
    assert 'contains(["adversarial-review"])' in qa_transition
    assert '--add-label "adversarial-review"' in qa_transition
    assert 'index("adversarial-review")' in dispatcher
    assert "<!-- adversarial-review: false -->" in dispatcher
    assert 'contains(["adversarial-review"])' in sync_labels
    assert '--add-label "adversarial-review"' in sync_labels
    effective_review_transition = _with_referenced_cloud_prompts(review_transition)
    assert "6軸レビュー" in effective_review_transition
    assert "5軸レビュー" not in effective_review_transition


def test_review_consumers_prefer_false_marker_over_stale_label() -> None:
    expected = {
        _CLOUD_REVIEW_WORKFLOWS[1]: ("has_adversarial_review", False),
        _CLOUD_REVIEW_WORKFLOWS[2]: ("has_issue_review_label", True),
        _CLOUD_REVIEW_WORKFLOWS[5]: ("has_adversarial_review", True),
        _CREATE_SUBISSUES_CONSUMER: ("HAS_ADVERSARIAL_REVIEW", True),
    }
    marker = (
        "<!--[[:space:]]*adversarial-review:[[:space:]]*false"
        "[[:space:]]*-->"
    )
    for path, (variable, requires_true_marker) in expected.items():
        text = path.read_text(encoding="utf-8")
        assert marker in text, path
        if requires_true_marker:
            assert (
                "<!--[[:space:]]*adversarial-review:[[:space:]]*true"
                "[[:space:]]*-->"
            ) in text, path
        assert re.search(rf'{re.escape(variable)}="?false"?', text), path

    sync_labels = _CLOUD_REVIEW_WORKFLOWS[5].read_text(encoding="utf-8")
    assert '--remove-label "adversarial-review"' in sync_labels
    qa_transition = _CLOUD_REVIEW_WORKFLOWS[2].read_text(encoding="utf-8")
    assert "PR_REVIEW_OPTED_OUT" in qa_transition
    assert 'pr_review_opted_out="true"' in qa_transition
    assert "PR body の false marker をRoot Issue設定より優先しました。" in qa_transition
    assert "PR body の false marker をRoot Issue設定より優先しました。" in sync_labels


@pytest.mark.parametrize("path", _REVIEW_ISSUE_TEMPLATES, ids=lambda path: path.name)
def test_each_review_issue_template_explains_explicit_activation(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "id: enable_review" in text
    assert "敵対的レビューを有効にする" in text
    assert "このモデル選択だけではレビューを発動しません" in text
    assert "一般 Code Review Agent の設定とは別です" in text
    assert "auto-context-review" not in text


def test_cloud_review_files_drop_legacy_context_review_trigger() -> None:
    for path in (*_CLOUD_REVIEW_WORKFLOWS, *_CLOUD_REVIEW_PRODUCERS):
        text = path.read_text(encoding="utf-8")
        assert "auto-context-review" not in text, path
        assert "auto_context_review" not in text, path
        assert "AUTO_CONTEXT_REVIEW" not in text, path
        assert "HAS_CONTEXT_REVIEW" not in text, path


def test_cloud_review_files_drop_legacy_auto_review_state_names() -> None:
    for path in (*_CLOUD_REVIEW_WORKFLOWS, *_CLOUD_REVIEW_PRODUCERS):
        text = path.read_text(encoding="utf-8")
        assert "<!-- auto-review:" not in text, path
        assert not re.search(r"\b(?:HAS_)?AUTO_REVIEW\b|\bhas_auto_review\b", text), path


def test_manual_cloud_producers_use_canonical_review_contract() -> None:
    (
        bash_orchestrate,
        bash_advance,
        bash_subissues,
        bash_launcher,
        ps_orchestrate,
        ps_advance,
        ps_subissues,
        ps_launcher,
    ) = (
        path.read_text(encoding="utf-8") for path in _MANUAL_CLOUD_PRODUCERS
    )
    for path, text in zip(
        _MANUAL_CLOUD_PRODUCERS,
        (
            bash_orchestrate,
            bash_advance,
            bash_subissues,
            bash_launcher,
            ps_orchestrate,
            ps_advance,
            ps_subissues,
            ps_launcher,
        ),
    ):
        assert "<!-- auto-review:" not in text, path
        assert "auto-context-review" not in text, path

    for text in (bash_orchestrate, ps_orchestrate):
        assert "<!-- adversarial-review:" in text
        assert "B60205" in text
        assert "explicit adversarial review trigger for Copilot review workflow" in text
        assert "adversarial-review" in text

    for text in (bash_advance, ps_advance):
        assert "adversarial-review" in text
        assert "--remove-label" in text

    for text in (bash_subissues, ps_subissues):
        assert "adversarial-review" in text
        assert "B60205" in text
        assert "false" in text
        assert "true" in text

    assert "SKIP_REVIEW" in bash_launcher
    assert "--skip-review" in bash_launcher
    assert "passthrough_args+=(--skip-review)" in bash_launcher
    assert "SkipReview" in ps_launcher
    assert "orchestrate.ps1" in ps_launcher


def test_hve_issue_producer_does_not_duplicate_phase3_cloud_trigger() -> None:
    template_engine = _HVE_ISSUE_PRODUCER_FILES[0].read_text(encoding="utf-8")
    orchestrator = _HVE_ISSUE_PRODUCER_FILES[1].read_text(encoding="utf-8")
    root_ref = template_engine.split("def _build_root_ref", 1)[1].split(
        "def _build_qa_review_context_section", 1
    )[0]
    root_body = template_engine.split("def build_root_issue_body", 1)[1].split(
        "class ", 1
    )[0]
    for source in (root_ref, root_body):
        assert "<!-- auto-review:" not in source
        assert "<!-- auto-context-review:" not in source
        assert "<!-- adversarial-review:" not in source
    assert "if not config.create_issues" in orchestrator
    assert "labels=[]" in orchestrator
    assert '"adversarial-review"' in orchestrator  # failed-PR cleanup only


def test_hve_interactive_review_choice_updates_phase3_config() -> None:
    orchestrator = _HVE_ISSUE_PRODUCER_FILES[1].read_text(encoding="utf-8")
    assert "params_were_provided = params is not None" in orchestrator
    assert "params if params_were_provided else None" in orchestrator
    assert "_apply_interactive_review_choice(config, effective_params)" in orchestrator

    from hve.config import SDKConfig
    from hve.orchestrator import (
        _apply_interactive_review_choice,
        _is_non_interactive,
    )

    config = SDKConfig(auto_contents_review=False)
    _apply_interactive_review_choice(config, {"skip_review": False})
    assert config.auto_contents_review is True
    _apply_interactive_review_choice(config, {"skip_review": True})
    assert config.auto_contents_review is False
    assert _is_non_interactive(object(), None) is False
    assert _is_non_interactive(object(), {}) is True


def test_adversarial_review_label_metadata_has_one_canonical_definition() -> None:
    labels = json.loads(_LABELS.read_text(encoding="utf-8"))
    matches = [label for label in labels if label.get("name") == "adversarial-review"]
    assert matches == [
        {
            "name": "adversarial-review",
            "color": "B60205",
            "description": "explicit adversarial review trigger for Copilot review workflow",
        }
    ]


def test_split_mode_waits_for_strict_review_gate() -> None:
    dispatcher = (
        _REPO_ROOT / ".github" / "workflows" / "auto-pr-transition-dispatcher.yml"
    ).read_text(encoding="utf-8")
    transition = (
        _REPO_ROOT
        / ".github"
        / "workflows"
        / "auto-create-subissues-transition.yml"
    ).read_text(encoding="utf-8")
    assert "types: [synchronize, labeled]" in dispatcher
    strict_dispatch = (
        'if [[ "${has_split_mode}" == "true" ]] \\\n'
        '               && [[ "${has_auto_approve_ready}" == "true" ]] \\\n'
        '               && [[ "${has_create_subissues}" != "true" ]]; then\n'
        "              target=create_subissues"
    )
    assert strict_dispatch in dispatcher
    assert dispatcher.count("target=create_subissues") == 1
    assert "PR 情報取得（常に最新状態を再取得）" in transition
    assert 'if [ "${has_auto_approve_ready}" != "true" ]; then' in transition
    assert 'if [ "${has_split_mode}" = "true" ] && [ "${has_auto_approve_ready}" = "true" ]; then' in transition
    assert "strict gate が付与した auto-approve-ready" in transition
    for forbidden in (
        "verdict マーカーなしフォールバック",
        "fallback_verdict",
        "レビュー指示後の最新コミット検知",
        "issue_comment 経路で Bot 回答検知",
        "質問なしパターンを検知",
        "ユーザー回答後に最新コミットを検知",
        "issue_comment 経路で回答検知",
        "bot_replies_after_qa",
    ):
        assert forbidden not in transition


def test_final_subissue_consumer_revalidates_strict_gate() -> None:
    consumer = _CREATE_SUBISSUES_CONSUMER.read_text(encoding="utf-8")
    auto_approve = _AUTO_APPROVE_WORKFLOW.read_text(encoding="utf-8")
    assert "Validate strict split gate" in consumer
    assert consumer.index("Validate strict split gate") < consumer.index(
        "Checkout PR head branch"
    )
    assert 'index("split-mode")' in consumer
    assert 'index("auto-approve-ready")' in consumer
    assert (
        'if [ "${has_split_mode}" != "true" ] '
        '|| [ "${has_auto_approve_ready}" != "true" ]; then'
        in consumer
    )
    assert "create-subissues requires split-mode + auto-approve-ready" in consumer
    assert "split-mode 用 create-subissues ラベル付与" not in auto_approve
    assert "--add-label create-subissues" not in auto_approve
    assert "手動で `create-subissues`" not in auto_approve
    assert "auto-approve-and-merge-subissues-missing" not in auto_approve
    assert "auto-pr-transition-dispatcher.yml" in auto_approve


def test_r03_prompt_red_contract_is_explicit_only_until_r03() -> None:
    legacy_auto_collected = (
        _REPO_ROOT / "hve" / "tests" / "test_prompt_review_inline_contract.py"
    )
    ci = _HVE_CI_WORKFLOW.read_text(encoding="utf-8")
    assert _R03_PROMPT_RED_CONTRACT.is_file()
    assert not _R03_PROMPT_RED_CONTRACT.name.startswith("test_")
    assert not legacy_auto_collected.exists()
    assert "pytest hve/tests/" in ci
    assert _R03_PROMPT_RED_CONTRACT.name not in ci


def _workflow_step_script(path: Path, job_name: str, step_name: str) -> str:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = document["jobs"][job_name]["steps"]
    return next(step["run"] for step in steps if step.get("name") == step_name)


def _bash_executable() -> str | None:
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    if git_bash.is_file():
        return str(git_bash)
    return shutil.which("bash")


@pytest.mark.parametrize(
    ("path", "job_name", "step_name"),
    (
        (
            _CLOUD_REVIEW_WORKFLOWS[0],
            "auto-review",
            "Resolve adversarial review trigger (excluding quoted sections)",
        ),
        (
            _CLOUD_REVIEW_WORKFLOWS[1],
            "transition",
            "PR 情報を取得（常に最新状態を再取得）",
        ),
    ),
)
def test_review_resolver_shell_is_syntactically_valid(
    path: Path,
    job_name: str,
    step_name: str,
) -> None:
    bash = _bash_executable()
    if bash is None:
        pytest.skip("bash is unavailable")
    assert bash is not None
    script = _workflow_step_script(path, job_name, step_name)
    result = subprocess.run(
        [bash, "-n"],
        input=script,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("explicit_skip", (False, True))
def test_bash_launcher_propagates_environment_review_opt_out(
    tmp_path: Path,
    explicit_skip: bool,
) -> None:
    bash = _bash_executable()
    if bash is None:
        pytest.skip("bash is unavailable")
    assert bash is not None
    launcher = tmp_path / "run-workflow.sh"
    producer = tmp_path / "orchestrate.sh"
    shutil.copy2(_MANUAL_CLOUD_PRODUCERS[3], launcher)
    producer.write_text(
        "#!/usr/bin/env bash\nprintf '<%s>\\n' \"$@\"\n",
        encoding="utf-8",
        newline="\n",
    )
    producer.chmod(0o755)
    args = [bash, str(launcher), "--workflow", "aas"]
    if explicit_skip:
        args.append("--skip-review")
    result = subprocess.run(
        args,
        env=dict(os.environ, SKIP_REVIEW="1"),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("<--skip-review>") == 1


def test_adoc_initialization_shell_is_syntactically_valid() -> None:
    bash = _bash_executable()
    if bash is None:
        pytest.skip("bash is unavailable")
    assert bash is not None
    script = _workflow_step_script(
        _ROOT_CLOUD_REVIEW_PRODUCERS[4],
        "orchestrate",
        "Issue 初期化と Step.1 生成",
    )
    result = subprocess.run(
        [bash, "-n"],
        input=script,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert 'if [[ " ${SKIP_STEPS} " =~ " 1 " ]]; then' in script


def test_dataflow_embedded_parser_separates_app_and_job_ids() -> None:
    script = _workflow_step_script(
        _REPO_ROOT / ".github" / "workflows" / "auto-dataflow-dev-reusable.yml",
        "orchestrate",
        "Issue 初期化とStep Issue 生成",
    )
    match = re.search(
        r"PARSED=\$\(python3 - <<'PYEOF'\n(?P<code>.*?)\nPYEOF\n\)",
        script,
        re.DOTALL,
    )
    assert match is not None
    code = match.group("code")
    compile(code, "auto-dataflow-dev-reusable.yml:PARSED", "exec")
    issue_body = "\n".join(
        (
            "### 対象ブランチ",
            "main",
            "### リソースグループ名",
            "rg-test",
            "### 対象データフローアプリ ID（カンマ区切り）",
            "BJ-001, BJ-002",
            "### 対象アプリケーション (APP-ID) — 複数指定可（任意）",
            "APP-009, APP-010",
            "",
        )
    )
    env = dict(os.environ, ISSUE_BODY=issue_body)
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["job_ids"] == "BJ-001, BJ-002"
    assert parsed["app_ids"] == ["APP-009", "APP-010"]


