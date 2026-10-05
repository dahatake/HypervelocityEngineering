"""FR-CLI-94: Phase 3 の評価 Prompt は修正を指示せず、校正の文言を持つ。"""

from __future__ import annotations

from hve.prompts import MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT, REVIEW_PROMPT


def test_review_prompt_has_no_fix_directive() -> None:
    assert "修正実行" not in REVIEW_PROMPT
    assert "全て修正" not in REVIEW_PROMPT
    assert "修正完了後" not in REVIEW_PROMPT
    assert "成果物を修正しない" in REVIEW_PROMPT


def test_review_prompt_forbids_self_judged_minor_approval() -> None:
    assert "軽微・範囲外と自己判断して承認へ回してはならない" in REVIEW_PROMPT
    assert "スタブ" in REVIEW_PROMPT and "Critical 候補" in REVIEW_PROMPT


def test_review_prompt_has_good_and_bad_judgment_examples() -> None:
    assert "良い判定例" in REVIEW_PROMPT
    assert "悪い判定例" in REVIEW_PROMPT


def test_review_fix_traceability_moves_to_main_improvement_prompt() -> None:
    # 反映証跡の記録は、修正を行うメインセッション側の Prompt が求める
    assert "敵対的レビュー修正内容" not in REVIEW_PROMPT
    assert "敵対的レビュー修正内容" in MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT


def test_review_prompt_reports_every_finding_and_leaves_filtering_to_hve() -> None:
    """FR-CLI-94（v3.26 / W14）: 重大度に関係なく根拠付きで報告し、絞り込みは HVE が行う。"""
    assert "重大度に関係なくすべて根拠付きで報告" in REVIEW_PROMPT
    assert "合否の絞り込みは HVE が行う" in REVIEW_PROMPT
