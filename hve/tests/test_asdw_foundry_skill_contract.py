"""ASDW AddService の条件付き Microsoft Foundry meta skill 契約。"""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DESIGN_PROMPT = (
    _REPO_ROOT
    / ".github"
    / "prompts"
    / "Dev-Microservice-Azure-AddServiceDesign.prompt.md"
)
_DEPLOY_PROMPT = (
    _REPO_ROOT
    / ".github"
    / "prompts"
    / "Dev-Microservice-Azure-AddServiceDeploy.prompt.md"
)


def _foundry_section(text: str, heading: str) -> str:
    """Return one Foundry-specific Prompt section without adjacent rules."""
    marker = f"### {heading}\n"
    _, separator, remainder = text.partition(marker)
    assert separator, heading
    return marker + remainder.partition("\n### ")[0]


def test_foundry_adopted_design_uses_meta_skill_and_official_mcp_discovery() -> None:
    """設計はFoundry該当時だけmeta skillへProject/model選定を委譲する。"""
    text = _foundry_section(
        _DESIGN_PROMPT.read_text(encoding="utf-8"),
        "Microsoft Foundry 選定時の external meta skill 利用（AI/LLM 該当時のみ）",
    )

    for required_text in (
        "Microsoft Foundry 選定時の external meta skill 利用（AI/LLM 該当時のみ）",
        "`microsoft-foundry` meta skillを最初に読み",
        "official MCP の利用可能な Foundry関連toolを最初に発見",
        "Project / model 選定に一致する guidance だけを読む",
        "sub-skill 名を推測・列挙しない",
        "Microsoft Learn MCPだけで暫定設計",
        "Foundry 非該当では `microsoft-foundry` meta skillを読まない",
    ):
        assert required_text in text


def test_foundry_adopted_deploy_requires_meta_skill_before_azure_write() -> None:
    """配置はFoundry該当時にskill未導入ならAzure write前に止める。"""
    text = _foundry_section(
        _DEPLOY_PROMPT.read_text(encoding="utf-8"),
        "Microsoft Foundry 配置時の external meta skill 利用（AI/LLM 該当時のみ）",
    )

    for required_text in (
        "Microsoft Foundry 配置時の external meta skill 利用（AI/LLM 該当時のみ）",
        "`microsoft-foundry` meta skillを必ず最初に読み",
        "official MCP の利用可能な Foundry関連toolを最初に発見",
        "resource / Project / model deploymentに一致する guidance だけを読む",
        "Azure write より前に block",
        "Azure write を実行せず",
        "`asdw-web:blocked`",
        "未導入理由・再開前提",
        "`{WORK}plan.md`",
        "必須の `{WORK}ac-verification.md`",
        "generic `azure-prepare` / `azure-deploy` / `azure-validate` で代替してはならない",
        "Foundry非該当なら `microsoft-foundry` meta skillの読込を要求しない",
    ):
        assert required_text in text


def test_asdw_foundry_prompt_missing_policies_remain_distinct() -> None:
    """DesignはTBDを残せるがDeployはAzure writeを実行せず停止する。"""
    design = _foundry_section(
        _DESIGN_PROMPT.read_text(encoding="utf-8"),
        "Microsoft Foundry 選定時の external meta skill 利用（AI/LLM 該当時のみ）",
    )
    deploy = _foundry_section(
        _DEPLOY_PROMPT.read_text(encoding="utf-8"),
        "Microsoft Foundry 配置時の external meta skill 利用（AI/LLM 該当時のみ）",
    )

    assert "TBD（要確認）" in design
    assert "Azure resource を作成しない" in design
    assert "Azure write を実行せず" in deploy
    assert "ac-verification.md" in deploy


def test_asdw_optional_foundry_does_not_change_mcp_configuration() -> None:
    """optional Foundryは既接続MCPを探索するだけで新規接続を追加しない。"""
    sections = (
        _foundry_section(
            _DESIGN_PROMPT.read_text(encoding="utf-8"),
            "Microsoft Foundry 選定時の external meta skill 利用（AI/LLM 該当時のみ）",
        ),
        _foundry_section(
            _DEPLOY_PROMPT.read_text(encoding="utf-8"),
            "Microsoft Foundry 配置時の external meta skill 利用（AI/LLM 該当時のみ）",
        ),
    )

    for section in sections:
        assert "MCP server を新規追加・接続構成変更しない" in section
        assert "既に接続済みの official MCP だけを discovery 対象" in section
