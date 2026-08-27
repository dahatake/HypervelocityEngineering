from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPT = _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AgentDeploy.prompt.md"
_TEMPLATE = _REPO_ROOT / ".github" / "prompts" / "steps" / "aagd" / "step-3.prompt.md"
_PROJECT_SHOW = (
    "az cognitiveservices account project show --name <account> "
    "--resource-group <rg> --project-name <project>"
)


def test_agent_deploy_uses_current_foundry_project_show_command() -> None:
    text = _PROMPT.read_text(encoding="utf-8")
    assert _PROJECT_SHOW in text
    assert "az ai services account show" not in text


def test_agent_deploy_does_not_own_foundry_project_creation() -> None:
    text = _PROMPT.read_text(encoding="utf-8")
    assert "Foundry Project を作成しない" in text
    assert "ASDW-WEB Step.2.2" in text
    assert "aagd:blocked" in text
    assert "az cognitiveservices account project create" not in text
    assert "az ai project create" not in text


def test_agent_deploy_does_not_substitute_account_endpoint_for_project_endpoint() -> None:
    text = _PROMPT.read_text(encoding="utf-8")
    assert "親 account endpoint を Project endpoint の代用にしない" in text


def test_agent_deploy_ac1_verifies_project_child_resource() -> None:
    text = _PROMPT.read_text(encoding="utf-8")
    assert re.search(
        r"\| \*\*AC-1[^\n]*Foundry Project[^\n]*"
        r"az cognitiveservices account project show",
        text,
    )


def test_agent_deploy_template_requires_existing_project_validation() -> None:
    text = _TEMPLATE.read_text(encoding="utf-8")
    assert _PROJECT_SHOW in text
    assert "Foundry Project を作成しない" in text
    assert "ASDW-WEB Step.2.2" in text
    assert "親 account endpoint を Project endpoint の代用にしない" in text


def test_agent_deploy_verify_contract_checks_project_succeeded() -> None:
    text = _PROMPT.read_text(encoding="utf-8")
    verify_section = text.split("## verify-agent-resources.sh", 1)[1]
    assert _PROJECT_SHOW in verify_section
    assert "provisioningState" in verify_section
    assert "Succeeded" in verify_section


def test_agent_deploy_references_io_contract_and_canonical_catalog_path() -> None:
    prompt = _PROMPT.read_text(encoding="utf-8")
    template = _TEMPLATE.read_text(encoding="utf-8")
    contract = ".github/io-contracts/Dev-Microservice-Azure-AgentDeploy--aagd--3.yaml"
    assert contract in prompt
    assert contract in template
    assert "docs/azure/azure-service-catalog.md" in template
    assert "docs/azure/service-catalog.md" not in template


def test_agent_deploy_prompt_and_template_require_provider_preflight() -> None:
    prompt = _PROMPT.read_text(encoding="utf-8")
    template = _TEMPLATE.read_text(encoding="utf-8")

    for marker in (
        "A-cap-plan",
        "A-cap-verify",
        "Section 7.0 / 7.3",
        "Provider Pre-flight",
    ):
        assert marker in prompt, marker
        assert marker in template, marker

    assert "Inventory delta" in prompt
    assert "Evidence redaction" in prompt
    assert "HVE Deploy gate" in template
    assert "RED（初回 deploy 時のみ）" in prompt
    assert "初回deploy時だけ" in template
    assert "冪等redeploy時" in template
    assert "1. verify-agent-resources.sh を実行 → 全 FAIL 確認" not in prompt
    assert "build_provider_inventory_snapshot()" in prompt
    assert "raw URL" in prompt


def test_agent_deploy_records_exact_decision_source_and_masks_dynamic_secrets() -> None:
    prompt = _PROMPT.read_text(encoding="utf-8")

    assert "docs/agent/agent-detail-{key}.md" in prompt
    assert "Section 7.0該当行" in prompt
    assert "公式資料のtitle / URL / 確認日" in prompt
    assert 'echo "::add-mask::${VALUE}"' in prompt
    assert "動的取得値" in prompt
    assert "step output" in prompt
