"""Generated test runtime environment contract tests.

These tests pin the Prompt/Skill contract that HVE-generated tests must be
runnable locally by default, while integration/post-deploy/E2E tests may use
configured external services via environment variables or test settings.
They intentionally use keyword checks instead of exact natural-language matches.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_DIR = _REPO_ROOT / ".github" / "skills"
_PROMPTS_DIR = _REPO_ROOT / ".github" / "prompts"
_TEMPLATES_DIR = _REPO_ROOT / ".github" / "scripts" / "templates"

_TDD_REALITY_SKILL = _SKILLS_DIR / "testing" / "tdd-red-green-reality" / "SKILL.md"
_TEST_STRATEGY_SKILL = _SKILLS_DIR / "testing" / "test-strategy-template" / "SKILL.md"
_TEST_STRATEGY_DETAIL = (
    _SKILLS_DIR
    / "testing"
    / "test-strategy-template"
    / "references"
    / "test-design-principles.md"
)
_VERIFICATION_COMMANDS = (
    _SKILLS_DIR
    / "harness"
    / "harness-verification-loop"
    / "references"
    / "verification-commands.md"
)

_LOCAL_RUNTIME_PROMPTS = [
    "Dev-Microservice-Azure-DataTestCoding.prompt.md",
    "Dev-Microservice-Azure-ServiceTestCoding.prompt.md",
    "Dev-Microservice-Azure-ServiceCoding-AzureFunctions.prompt.md",
    "Dev-Microservice-Azure-UITestCoding.prompt.md",
    "Dev-Microservice-Azure-UICoding.prompt.md",
    "Dev-Microservice-Azure-AgentTestCoding.prompt.md",
    "Dev-Microservice-Azure-AgentCoding.prompt.md",
    "Dev-Dataflow-TestCoding.prompt.md",
    "Dev-Dataflow-ServiceCoding.prompt.md",
]

_EXTERNAL_RUNTIME_PROMPTS = [
    "Dev-Microservice-Azure-DataDeploy.prompt.md",
    "Dev-Microservice-Azure-AddServiceTestCoding.prompt.md",
    "Dev-Microservice-Azure-AddServiceTesting.prompt.md",
    "Dev-Microservice-Azure-ComputePostDeployTest.prompt.md",
    "E2ETesting-Playwright.prompt.md",
]

_LOCAL_RUNTIME_TEMPLATES = [
    _TEMPLATES_DIR / "asdw-web" / "step-1.2.md",
    _TEMPLATES_DIR / "asdw-web" / "step-3.2.md",
    _TEMPLATES_DIR / "asdw-web" / "step-3.3.md",
    _TEMPLATES_DIR / "asdw-web" / "step-4.1.md",
    _TEMPLATES_DIR / "asdw-web" / "step-4.2.md",
    _TEMPLATES_DIR / "adfdv" / "step-2.1.md",
    _TEMPLATES_DIR / "adfdv" / "step-2.2.md",
    _TEMPLATES_DIR / "aagd" / "step-2.2.md",
    _TEMPLATES_DIR / "aagd" / "step-2.3.md",
]

_EXTERNAL_RUNTIME_TEMPLATES = [
    _TEMPLATES_DIR / "asdw-web" / "step-1.3.md",
    _TEMPLATES_DIR / "asdw-web" / "step-2.3.md",
    _TEMPLATES_DIR / "asdw-web" / "step-2.4.md",
    _TEMPLATES_DIR / "asdw-web" / "step-3.5.md",
    _TEMPLATES_DIR / "asdw-web" / "step-4.4.md",
]

_AAGD_AGENT_DETAIL_CONSUMERS = [
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentTestCoding.prompt.md",
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentCoding.prompt.md",
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentDeploy.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.1.md",
    _TEMPLATES_DIR / "aagd" / "step-2.2.md",
    _TEMPLATES_DIR / "aagd" / "step-2.3.md",
    _TEMPLATES_DIR / "aagd" / "step-3.md",
]

_AAGD_TDD_RED_FILES = [
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentTestCoding.prompt.md",
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentCoding.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.2.md",
    _TEMPLATES_DIR / "aagd" / "step-2.3.md",
]

_AAGD_AGENT_KEY_FILES = [
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentTestCoding.prompt.md",
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentCoding.prompt.md",
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentDeploy.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.1.md",
    _TEMPLATES_DIR / "aagd" / "step-2.2.md",
    _TEMPLATES_DIR / "aagd" / "step-2.3.md",
    _TEMPLATES_DIR / "aagd" / "step-3.md",
]


def test_tdd_reality_skill_defines_runtime_environment_contract() -> None:
    text = _TDD_REALITY_SKILL.read_text(encoding="utf-8")
    for token in (
        "生成テストの実行環境契約",
        "ローカル実行可能",
        "外部サービス",
        "環境変数",
        "デプロイ先",
        "fake GREEN",
        "秘密情報",
    ):
        assert token in text


def test_test_strategy_skill_points_to_runtime_environment_contract() -> None:
    text = _TEST_STRATEGY_SKILL.read_text(encoding="utf-8")
    assert "実行環境" in text
    assert "ローカル実行可能" in text
    assert "環境変数" in text


def test_test_strategy_detail_classifies_runtime_environments() -> None:
    text = _TEST_STRATEGY_DETAIL.read_text(encoding="utf-8")
    for token in (
        "実行環境の分類",
        "Unit / Component",
        "Integration",
        "Post-deploy / E2E",
        "E2E_BASE_URL",
        "PASS 扱いしない",
    ):
        assert token in text


def test_verification_commands_do_not_skip_missing_external_service_config() -> None:
    text = _VERIFICATION_COMMANDS.read_text(encoding="utf-8")
    assert "JavaScript / UI" in text
    assert "FAIL(環境ブロッカー)" in text
    assert "未実行のまま成功扱いしない" in text


def test_local_runtime_prompts_require_local_execution_contract() -> None:
    for name in _LOCAL_RUNTIME_PROMPTS:
        text = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
        assert "TDD テスト結果レポート" in text, f"{name} is not a TDD/runtime prompt"
        assert "ローカル" in text or "local" in text, f"{name} missing local runtime wording"
        assert "環境変数" in text, f"{name} missing environment variable wording"
        assert "秘密情報" in text, f"{name} missing secret handling wording"


def test_external_runtime_prompts_require_configured_service_contract() -> None:
    for name in _EXTERNAL_RUNTIME_PROMPTS:
        text = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
        assert "環境変数" in text, f"{name} missing environment variable wording"
        assert "秘密情報" in text, f"{name} missing secret handling wording"
        assert (
            "実環境" in text or "デプロイ済み" in text or "構成済み" in text or "E2E_BASE_URL" in text
        ), f"{name} missing configured external service wording"


def test_local_runtime_templates_require_local_execution_contract() -> None:
    for path in _LOCAL_RUNTIME_TEMPLATES:
        text = path.read_text(encoding="utf-8")
        assert "TDD-Judgement" in text or "TDD" in text, f"{path.relative_to(_REPO_ROOT)} is not TDD-related"
        assert "ローカル" in text or "local" in text, f"{path.relative_to(_REPO_ROOT)} missing local runtime wording"
        assert "環境変数" in text, f"{path.relative_to(_REPO_ROOT)} missing environment variable wording"
        assert "秘密情報" in text, f"{path.relative_to(_REPO_ROOT)} missing secret handling wording"


def test_external_runtime_templates_require_configured_service_contract() -> None:
    for path in _EXTERNAL_RUNTIME_TEMPLATES:
        text = path.read_text(encoding="utf-8")
        assert "環境変数" in text, f"{path.relative_to(_REPO_ROOT)} missing environment variable wording"
        assert "秘密情報" in text, f"{path.relative_to(_REPO_ROOT)} missing secret handling wording"
        assert (
            "実環境" in text or "デプロイ済み" in text or "構成済み" in text or "E2E_BASE_URL" in text
        ), f"{path.relative_to(_REPO_ROOT)} missing configured external service wording"


def test_aagd_agent_detail_consumers_use_canonical_key_path() -> None:
    assert _TEMPLATES_DIR / "aagd" / "step-2.3.md" in _AAGD_AGENT_DETAIL_CONSUMERS
    for path in _AAGD_AGENT_DETAIL_CONSUMERS:
        text = path.read_text(encoding="utf-8")
        assert "docs/agent/agent-detail-{key}.md" in text, (
            f"{path.relative_to(_REPO_ROOT)} missing canonical Agent detail path"
        )
        assert "docs/agent/agent-detail-{agentId}-*.md" not in text
        assert "docs/agent/agent-detail-{agentId}.md" not in text


def test_aagd_step_chain_preserves_test_spec_red_green_and_deploy_inputs() -> None:
    step21 = (_TEMPLATES_DIR / "aagd" / "step-2.1.md").read_text(encoding="utf-8")
    step22 = (_TEMPLATES_DIR / "aagd" / "step-2.2.md").read_text(encoding="utf-8")
    step23 = (_TEMPLATES_DIR / "aagd" / "step-2.3.md").read_text(encoding="utf-8")
    step3 = (_TEMPLATES_DIR / "aagd" / "step-3.md").read_text(encoding="utf-8")

    assert "docs/test-specs/{key}-test-spec.md" in step21
    assert "docs/test-specs/{key}-test-spec.md" in step22
    assert "src/test/agent/{key}.Tests/" in step22
    assert "src/test/agent/{key}.Tests/" in step23
    assert "未実装production behavior" in step22
    assert "TDD GREEN" in step23
    assert "src/agent/{key}/" in step23
    assert "src/agent/{key}/" in step3


def test_aagd_tdd_red_contract_does_not_require_every_test_to_fail() -> None:
    fail_all_pattern = re.compile(
        r"(?:全\s*テスト(?![^\n]*PASS)[^\n]*FAIL|"
        r"テスト(?:が|は)?\s*全て(?![^\n]*PASS)[^\n]*FAIL|"
        r"全\s*FAIL)",
        re.IGNORECASE,
    )
    for path in _AAGD_TDD_RED_FILES:
        text = path.read_text(encoding="utf-8")
        assert "未実装production behavior" in text, (
            f"{path.relative_to(_REPO_ROOT)} missing behavior-based RED contract"
        )
        assert "全テストが FAIL" not in text
        assert "全テスト FAIL" not in text
        assert "テストが全て FAIL" not in text
        assert not fail_all_pattern.search(text), path


def test_agent_coding_prompt_pins_capability_safety_boundaries() -> None:
    """Sub-15 の実装境界をPrompt契約として直接固定する。"""
    text = (_PROMPTS_DIR / "Dev-Microservice-Azure-AgentCoding.prompt.md").read_text(
        encoding="utf-8"
    )
    required_tokens = (
        "Section 7.0のPreferred / Fallbackに選択されたrouteだけを実装",
        "単一SELECT",
        "parameterization",
        "table/view/column allowlist",
        "INSERT / UPDATE / DELETE / MERGE / DDL / stored procedure",
        "Create / Update / Deleteは既存API契約に対応するREST Function Toolだけをprimary経路",
        "SQL/direct DB writeやMCP mutation迂回を禁止",
        "Agentは選択されたMCP Serverのclientとして接続",
        "Agent自身のRemote MCP Server化を既定で行わない",
        "有限のPLAN / ACT / OBSERVE / EVALUATE / REPLAN",
        "Section 7.4の恒久的な`Decision source`で承認されていないLocation",
        "`not-required`ではSkill、loader、hook、設定flagを作らない",
    )
    for token in required_tokens:
        assert token in text, f"AgentCoding capability contract missing: {token}"

    forbidden_tokens = (
        "Section 6: Knowledge Source",
        "D16で承認",
        "src/agent/{AgentID}-{AgentName}/",
        "src/test/agent/{AgentName}.Tests/",
        "docs/test-specs/{agentId}-test-spec.md",
    )
    for token in forbidden_tokens:
        assert token not in text, f"AgentCoding stale contract remains: {token}"


def test_aagd_capability_tests_use_selected_deterministic_test_doubles() -> None:
    """TestSpec→TestCodingが選択能力だけを外部接続なしで決定的に検証する。"""
    test_spec = (_TEMPLATES_DIR / "aagd" / "step-2.1.md").read_text(encoding="utf-8")
    test_coding = (
        _PROMPTS_DIR / "Dev-Microservice-Azure-AgentTestCoding.prompt.md"
    ).read_text(encoding="utf-8")
    assert "AG-CAP-01〜10" in test_spec
    assert "AG-CAP-01〜10" in test_coding
    for contract_id in ("AG-CAP-01 / 02", "AG-CAP-03", "AG-CAP-04", "AG-CAP-05", "AG-CAP-06"):
        assert contract_id in test_coding
    for token in (
        "Contract ID、入力、test double、期待結果、必要なevidence",
        "mock / stub / fake",
        "全providerのmockを先回り生成せず",
    ):
        assert token in test_spec
    for token in (
        "Preferred / Fallbackに選択されたproviderだけをmock/stub化",
        "全provider用fixture、依存、mockを先回り生成しない",
        "実接続しない",
        "呼出順・回数",
    ):
        assert token in test_coding


def test_aag_aagd_contract_files_forbid_stale_section6_knowledge_reference() -> None:
    """旧Section 6 Knowledge Source参照を能力契約chainへ再導入しない。"""
    files = [
        _PROMPTS_DIR / "Arch-AIAgentDesign-Step1.prompt.md",
        _PROMPTS_DIR / "Arch-AIAgentDesign-Step2.prompt.md",
        _PROMPTS_DIR / "Arch-AIAgentDesign-Step3.prompt.md",
        *_AAGD_AGENT_DETAIL_CONSUMERS,
    ]
    for path in files:
        assert "Section 6: Knowledge Source" not in path.read_text(encoding="utf-8"), path


def test_aagd_agent_specific_contracts_use_only_canonical_key() -> None:
    """fan-out後も残るAgent名placeholderをAAGD契約へ再導入しない。"""
    stale_tokens = (
        "{agentId}",
        "{agentName}",
        "{AgentID}",
        "{AgentName}",
        "agent-detail-*",
    )
    for path in _AAGD_AGENT_KEY_FILES:
        text = path.read_text(encoding="utf-8")
        for token in stale_tokens:
            assert token not in text, (
                f"{path.relative_to(_REPO_ROOT)} contains stale Agent placeholder: {token}"
            )
        assert "{key}" in text, f"{path.relative_to(_REPO_ROOT)} missing canonical key"

    deploy_prompt = (
        _PROMPTS_DIR / "Dev-Microservice-Azure-AgentDeploy.prompt.md"
    ).read_text(encoding="utf-8")
    deploy_template = (_TEMPLATES_DIR / "aagd" / "step-3.md").read_text(
        encoding="utf-8"
    )
    assert ".github/workflows/deploy-agent-{key}.yml" in deploy_prompt
    assert ".github/workflows/deploy-agent-{key}.yml" in deploy_template
