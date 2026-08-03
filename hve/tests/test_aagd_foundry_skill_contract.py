"""AAGD Foundry-required Step のmeta skill Prompt契約。"""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CODING_PROMPT = (
    _REPO_ROOT
    / ".github"
    / "prompts"
    / "Dev-Microservice-Azure-AgentCoding.prompt.md"
)
_DEPLOY_PROMPT = (
    _REPO_ROOT
    / ".github"
    / "prompts"
    / "Dev-Microservice-Azure-AgentDeploy.prompt.md"
)
_RED_PROMPT = (
    _REPO_ROOT
    / ".github"
    / "prompts"
    / "Dev-Microservice-Azure-AgentTestCoding.prompt.md"
)


def _foundry_required_section(text: str, heading: str) -> str:
    """Return a bounded Foundry-required Prompt section."""
    marker = f"### {heading}\n"
    _, separator, remainder = text.partition(marker)
    assert separator, heading
    return marker + remainder.partition("\n# ")[0]


def test_aagd_agent_coding_reads_meta_skill_then_discovers_tools_and_samples() -> None:
    """AAGD GREEN codingはmeta skill、Azure MCP、Learn sampleを順に使う。"""
    text = _foundry_required_section(
        _CODING_PROMPT.read_text(encoding="utf-8"),
        "Microsoft Foundry required meta skill workflow（必須）",
    )

    for required_text in (
        "`microsoft-foundry` meta skillを必ず最初に読む",
        "repository-pinned Azure MCP",
        "利用可能な Foundry関連toolを最初に発見",
        "Microsoft Learn MCP の `microsoft_code_sample_search`",
        "最新の公式実装例",
        "作成に一致する guidance だけを読む",
        "sub-skill 名を推測・列挙しない",
        "既存のHVE成果物、TDD、AC、GitHub Actions contractを優先",
        "`azd` lifecycleへ移行しない",
        "official evaluation suiteは今回の成果物へ追加せず、後続案として記録する",
    ):
        assert required_text in text
    assert (
        text.index("`microsoft-foundry` meta skillを必ず最初に読む")
        < text.index("repository-pinned Azure MCP")
        < text.index("Microsoft Learn MCP の `microsoft_code_sample_search`")
        < text.index("作成に一致する guidance だけを読む")
    )


def test_aagd_agent_deploy_reads_meta_skill_for_deploy_then_invoke_only() -> None:
    """AAGD Deployはmeta skillのdeploy/invoke guidanceだけを使い既存契約を守る。"""
    text = _foundry_required_section(
        _DEPLOY_PROMPT.read_text(encoding="utf-8"),
        "Microsoft Foundry required meta skill workflow（必須）",
    )

    for required_text in (
        "`microsoft-foundry` meta skillを必ず最初に読む",
        "repository-pinned Azure MCP",
        "利用可能な Foundry関連toolを最初に発見",
        "Microsoft Learn MCP の `microsoft_code_sample_search`",
        "最新の公式実装例",
        "deploy → invokeに一致する guidance だけを読む",
        "sub-skill 名を推測・列挙しない",
        "既存のHVE成果物、TDD、AC、GitHub Actions contractを優先",
        "`azd` lifecycleへ移行しない",
        "official evaluation suiteは今回の成果物へ追加せず、後続案として記録する",
    ):
        assert required_text in text
    assert (
        text.index("`microsoft-foundry` meta skillを必ず最初に読む")
        < text.index("repository-pinned Azure MCP")
        < text.index("Microsoft Learn MCP の `microsoft_code_sample_search`")
        < text.index("deploy → invokeに一致する guidance だけを読む")
    )


def test_aagd_required_prompts_do_not_change_mcp_configuration_or_red_step_scope() -> None:
    """AAGD required Stepは既接続MCPだけを発見し、REDへlive skillを広げない。"""
    for path in (_CODING_PROMPT, _DEPLOY_PROMPT):
        text = _foundry_required_section(
            path.read_text(encoding="utf-8"),
            "Microsoft Foundry required meta skill workflow（必須）",
        )
        assert "MCP server を新規追加・接続構成変更しない" in text
        assert "既に接続済みの official MCP だけを discovery 対象" in text

    red = _RED_PROMPT.read_text(encoding="utf-8")
    assert "microsoft-foundry" not in red
    assert "Foundry required meta skill workflow" not in red
    assert "repository-pinned Azure MCP" not in red
    assert "Foundry Skill" not in red
    assert "mock/stub/fake" in red
    assert "実接続しない" in red
