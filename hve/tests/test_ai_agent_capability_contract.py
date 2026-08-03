"""Cross-layer AI Agent capability contract tests (Sub-24)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from hve.runner import StepRunner
from hve.workflow_registry import get_workflow

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL_ROOT = _REPO_ROOT / ".github" / "skills" / "ai-agent-capability-contract"
_PROMPTS = _REPO_ROOT / ".github" / "prompts"
_TEMPLATES = _REPO_ROOT / ".github" / "scripts" / "templates" / "aagd"
_IO_CONTRACT = (
    _REPO_ROOT
    / ".github"
    / "io-contracts"
    / "Arch-AIAgentDesign-Step3--aag--3.yaml"
)

_AAG_PROMPTS = {
    "step1": _PROMPTS / "Arch-AIAgentDesign-Step1.prompt.md",
    "step2": _PROMPTS / "Arch-AIAgentDesign-Step2.prompt.md",
    "step3": _PROMPTS / "Arch-AIAgentDesign-Step3.prompt.md",
}
_AAGD_FILES = {
    "test-spec": _TEMPLATES / "step-2.1.md",
    "test-code": _PROMPTS / "Dev-Microservice-Azure-AgentTestCoding.prompt.md",
    "coding": _PROMPTS / "Dev-Microservice-Azure-AgentCoding.prompt.md",
    "deploy": _PROMPTS / "Dev-Microservice-Azure-AgentDeploy.prompt.md",
}
_ALL_CONTRACT_FILES = tuple(_AAG_PROMPTS.values()) + tuple(_AAGD_FILES.values())
_CONTRACT_IDS = tuple(f"AG-CAP-0{index}" for index in range(1, 7))


def _read(path: Path) -> str:
    assert path.is_file(), path
    return path.read_text(encoding="utf-8")


def test_shared_skill_has_six_contracts_progressive_references_and_registration() -> None:
    skill = _read(_SKILL_ROOT / "SKILL.md")
    for contract_id in _CONTRACT_IDS:
        assert contract_id in skill
    for reference in (
        "capability-contract.md",
        "goal-self-improvement.md",
        "search-routing.md",
        "tool-mcp-skill-packaging.md",
    ):
        assert reference in skill
        assert (_SKILL_ROOT / "references" / reference).is_file()

    manifest = json.loads((_REPO_ROOT / "hve" / "skill_manifest.json").read_text(encoding="utf-8"))
    assert "ai-agent-capability-contract" in manifest["workflow_defaults"]["aag"]
    assert "ai-agent-capability-contract" in manifest["workflow_defaults"]["aagd"]
    routing = _read(_REPO_ROOT / ".github" / "skills" / "_routing" / "README.md")
    assert "`ai-agent-capability-contract`" in routing


def test_skill_eval_has_positive_negative_and_edge_cases() -> None:
    payload = yaml.safe_load(
        (_REPO_ROOT / ".github" / "skills" / "_evals" / "ai-agent-capability-contract.eval.yaml")
        .read_text(encoding="utf-8")
    )
    cases = payload["test_cases"]
    assert payload["skill"] == "ai-agent-capability-contract"
    assert payload["skill_path"] == ".github/skills/ai-agent-capability-contract/SKILL.md"
    seen_ids: set[str] = set()
    for case in cases:
        assert case["id"] not in seen_ids
        seen_ids.add(case["id"])
        assert len(case["input"].strip()) >= 20
        assert isinstance(case["expected_trigger"], bool)
        assert len(case["reason"].strip()) >= 10
        if case["expected_trigger"]:
            assert case.get("verify")
            for verification in case["verify"]:
                assert verification.get("type")
                assert len(verification.get("detail", "").strip()) >= 20
        else:
            assert "expected_skill" in case
    positives = [case for case in cases if case["expected_trigger"] is True]
    negatives = [case for case in cases if case["expected_trigger"] is False]
    assert len(positives) >= 3
    assert len(negatives) >= 2
    assert any("MCP" in case["input"] and "REST" in case["input"] for case in positives)
    assert any("検索、更新、MCPは使わない" in case["input"] for case in positives)


def test_aag_step1_fixes_goal_contract_and_mutation_intent() -> None:
    text = _read(_AAG_PROMPTS["step1"])
    for token in (
        "ai-agent-capability-contract",
        "### Goal Contract",
        "AG-CAP-01",
        "Mission",
        "Mutation Intent",
        "Success criteria",
        "Evaluator",
        "Evidence",
        "Failure・Partial・Handoff",
        "Q-GC-NNN",
    ):
        assert token in text
    assert "根拠不足時に限り理由付きTBD" in text


def test_aag_step2_fixes_source_rest_mcp_and_skill_boundaries() -> None:
    text = _read(_AAG_PROMPTS["step2"])
    required_columns = (
        "Request class",
        "Preferred route class",
        "Fallback route class",
        "Mutation operations",
        "REST owner service",
        "MCP client",
        "MCP adapter owner",
        "Skill candidate",
        "Decision source",
    )
    for token in ("ai-agent-capability-contract", "AG-CAP-03〜06", *required_columns):
        assert token in text
    assert "AgentやMCPが直接DB mutationを所有しない" in text
    assert "Agent自身がMCP Serverを所有する設計を既定にしない" in text
    assert "Step 2ではSkillファイルを生成しない" in text


def test_aag_step3_fixes_all_sections_reasoned_na_and_completion_gate() -> None:
    text = _read(_AAG_PROMPTS["step3"])
    fixed_sections = (
        "Goal Contract",
        "Runtime Goal Loop",
        "Knowledge & Structured Data Routing",
        "REST CRUD Matrix",
        "MCP Integration Plan",
        "Skill Packaging Decision",
    )
    assert len(fixed_sections) == len(_CONTRACT_IDS) == 6
    assert "AG-CAP-01〜06" in text
    for heading in fixed_sections:
        assert text.count(heading) >= 1
    for token in (
        "Contract ID / 理由 / Decision source / 再判定条件",
        "単語だけのN/Aを禁止",
        "C/U/Dのprimary経路はREST Function Toolだけ",
        "REST mutationを迂回させない",
        "required時だけ配置先・resources・明示load・validation",
    ):
        assert token in text
    assert "AG-CAP-01〜06が確定または理由付きN/A" in text


def test_aagd_test_spec_traces_every_contract_to_deterministic_test_doubles() -> None:
    text = _read(_AAGD_FILES["test-spec"])
    assert "AG-CAP-01〜06" in text
    for token in (
        "Contract ID、入力、test double、期待結果、必要なevidence",
        "Preferred→Fallback→Blocked",
        "SELECT-only SQL",
        "REST Function Tool",
        "MCP mutation迂回は拒否",
        "明示的loading",
        "mock / stub / fake",
        "全providerのmockを先回り生成せず",
    ):
        assert token in text


def test_aagd_test_coding_uses_selected_providers_and_no_live_services() -> None:
    text = _read(_AAGD_FILES["test-code"])
    assert "AG-CAP-01〜06" in text
    for contract_id in ("AG-CAP-01 / 02", "AG-CAP-03", "AG-CAP-04", "AG-CAP-05", "AG-CAP-06"):
        assert contract_id in text
    for token in (
        "Preferred / Fallbackに選択されたproviderだけをmock/stub化",
        "全provider用fixture、依存、mockを先回り生成しない",
        "Web IQ unavailable時のFallback",
        "Work IQ signed-in user権限拒否",
        "Fabric IQ接続・権限失敗",
        "SELECT-only SQL",
        "REST/MCP二重登録",
        "実接続しない",
    ):
        assert token in text


def test_aagd_coding_and_deploy_preserve_selected_only_and_na_absence() -> None:
    coding = _read(_AAGD_FILES["coding"])
    deploy = _read(_AAGD_FILES["deploy"])
    for token in (
        "Section 7.0のPreferred / Fallbackに選択されたrouteだけを実装",
        "Create / Update / Deleteは既存API契約に対応するREST Function Toolだけ",
        "Agentは選択されたMCP Serverのclientとして接続",
        "`not-required`ではSkill、loader、hook、設定flagを作らない",
    ):
        assert token in coding
    for token in (
        "supported` / `preview` / `limited-access`として選択されたrouteだけ",
        "理由付きN/A / `not-selected`のprovider",
        "Prompt記載時点のAPI version、SKU、model、regionを実行値として固定しない",
        "Inventory delta: zero",
        "SELECTED-PASS",
        "Decision source",
    ):
        assert token in deploy


def test_legacy_section6_knowledge_source_reference_is_absent() -> None:
    stale = "Section 6: Knowledge Source"
    for path in _ALL_CONTRACT_FILES:
        assert stale not in _read(path), path.relative_to(_REPO_ROOT)


def test_contract_files_do_not_pin_provider_api_versions() -> None:
    api_version_assignment = re.compile(
        r"(?i)(?:api[-_ ]?version|api-version)\s*[:=]\s*[\"']?20\d{2}-\d{2}-\d{2}"
    )
    assert api_version_assignment.search('API_VERSION = "2026-01-15"')
    assert not api_version_assignment.search(
        "Microsoft Learn describes API version 2026-01-15; do not pin it."
    )
    for path in _ALL_CONTRACT_FILES:
        assert not api_version_assignment.search(_read(path)), path.relative_to(_REPO_ROOT)


def test_scoped_io_registry_and_runner_paths_are_identical() -> None:
    contract = yaml.safe_load(_IO_CONTRACT.read_text(encoding="utf-8"))
    outputs = {item["path"] for item in contract["outputs"]}
    assert outputs == {
        "docs/ai-agent-catalog.md",
        "docs/agent/agent-detail-{key}.md",
    }
    assert all(
        item["required"] is True and item["mode"] == "create"
        for item in contract["outputs"]
    )
    optional_inputs = {
        item["path"] for item in contract["inputs"] if item["required"] is False
    }
    assert optional_inputs == {
        ".github/skills/agent-common-preamble/references/agent-playbook.md",
        "knowledge/",
    }

    aag = get_workflow("aag")
    aagd = get_workflow("aagd")
    assert aag is not None and aagd is not None
    aag_step3 = aag.get_step("3")
    assert aag_step3 is not None
    assert aag_step3.output_paths_template == [
        "docs/agent/agent-detail-{key}.md"
    ]
    for step_id in ("2.1", "2.2", "2.3", "3"):
        step = aagd.get_step(step_id)
        assert step is not None
        required = step.required_input_paths
        if step_id != "2.1":
            assert "docs/agent/agent-detail-{key}.md" in required
    aagd_step21 = aagd.get_step("2.1")
    aagd_step23 = aagd.get_step("2.3")
    assert aagd_step21 is not None and aagd_step23 is not None
    assert aagd_step21.output_paths_template == [
        "docs/test-specs/{key}-test-spec.md"
    ]
    assert "docs/test-specs/{key}-test-spec.md" in aagd_step23.required_input_paths

    targets = StepRunner._AI_AGENT_CAPABILITY_GATE_TARGETS
    assert targets == {
        ("aag", "3", "Arch-AIAgentDesign-Step3"): "design",
        ("aagd", "2.3", "Dev-Microservice-Azure-AgentCoding"): "implementation",
    }
