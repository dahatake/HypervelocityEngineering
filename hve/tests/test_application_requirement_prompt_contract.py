"""FR-WF-ARD-04 / FR-APPREQ-01/02 のPrompt・template契約RED。"""

from __future__ import annotations

from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]
_PRODUCER_PROMPT = (
    _REPO / ".github" / "prompts" / "Arch-ApplicationRequirementDefinition.prompt.md"
)
_STEP_41 = _REPO / ".github" / "scripts" / "templates" / "ard" / "step-4.1.md"
_STEP_42 = _REPO / ".github" / "scripts" / "templates" / "ard" / "step-4.2.md"
_CANDIDATE_PROMPT = (
    _REPO / ".github" / "prompts" / "Arch-ArchitectureCandidateAnalyzer.prompt.md"
)
_CANDIDATE_TEMPLATE = (
    _REPO / ".github" / "scripts" / "templates" / "aas" / "step-1.md"
)


def test_ard_application_steps_have_templates() -> None:
    assert _STEP_41.is_file()
    assert _STEP_42.is_file()
    assert "`Arch-ApplicationAnalytics`" in _STEP_41.read_text(encoding="utf-8")
    assert "`Arch-ApplicationRequirementDefinition`" in _STEP_42.read_text(encoding="utf-8")


def test_requirement_producer_prompt_declares_stable_upsert_contract() -> None:
    text = _PRODUCER_PROMPT.read_text(encoding="utf-8")
    for token in (
        "docs/architectural-requirements-app-NNN.md",
        "APP-NNN-FR-NNN",
        "APP-NNN-NFR-NNN",
        "APP-NNN-C-NNN",
        "confirmed",
        "source-backed",
        "TBD",
        "Blocker",
        "upsert",
        "再番号",
        "orphan",
        "単一エージェント",
    ):
        assert token in text
    assert "fan-out" in text
    assert "fan-out しない" in text or "fan-outをしない" in text


def test_requirement_producer_prompt_declares_source_precedence() -> None:
    text = _PRODUCER_PROMPT.read_text(encoding="utf-8")
    assert (
        "既存 confirmed > 明示添付 / 回答済み QA > ARD 成果物 > "
        "staleness 合格済み knowledge > 推論 TBD"
    ) in text


def test_requirement_producer_prompt_protects_existing_human_content() -> None:
    text = _PRODUCER_PROMPT.read_text(encoding="utf-8")
    for token in (
        "confirmed 行の ID と内容",
        "source-backed 行の ID",
        "人手追記",
        "上位根拠と競合",
        "Blocker",
    ):
        assert token in text


def test_architecture_candidate_no_longer_defaults_when_requirement_is_missing() -> None:
    prompt = _CANDIDATE_PROMPT.read_text(encoding="utf-8")
    template = _CANDIDATE_TEMPLATE.read_text(encoding="utf-8")
    for text in (prompt, template):
        # 非 fan-out Step は fan-out キーを代入できないため、FR-APPREQ-01 の
        # canonical 表記 `NNN` を使い、未置換で残る `{appId}` を本文に書かない。
        assert "docs/architectural-requirements-app-NNN.md" in text
        assert "docs/architectural-requirements-app-{appId}.md" not in text
        assert "必須" in text
        assert "fail-closed" in text
    assert "デフォルト推薦" not in prompt
    assert "入力ファイルなし" not in prompt
