"""Azure 関連 prompt/template の Microsoft Learn MCP 参照契約テスト。

Azure サービス選定・Azure CLI・Azure SDK・REST API 等を扱う Step が、
Microsoft Learn MCP 利用可能時の必須参照と根拠記録を明示し続けるための回帰ガード。
"""

from __future__ import annotations

import re
from pathlib import Path

from hve.template_engine import render_template
from hve.workflow_registry import list_workflows

_REPO_ROOT = Path(__file__).resolve().parents[2]

_ASDW_ADD_SERVICE_FILES = (
    _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web" / "step-2.1.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web" / "step-2.2.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web" / "step-2.3.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web" / "step-2.4.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AddServiceDesign.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AddServiceDeploy.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AddServiceTestCoding.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AddServiceTesting.prompt.md",
)

_ASDW_COMPUTE_FILES = (
    _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web" / "step-3.1.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web" / "step-3.3.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web" / "step-3.4.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web" / "step-4.3.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-ComputeDesign.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-ServiceCoding-AzureFunctions.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md",
)

_ASDW_AZURE_REVIEW_FILES = (
    _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web" / "step-5.1.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web" / "step-5.2.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "QA-AzureArchitectureReview.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "QA-AzureDependencyReview.prompt.md",
)

_AAD_AZURE_FILES = (
    _REPO_ROOT / ".github" / "prompts" / "steps" / "aad-web" / "step-2.5.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AddServiceDesign.prompt.md",
)

_ADFDV_AZURE_FILES = (
    _REPO_ROOT / ".github" / "prompts" / "steps" / "adfdv" / "step-1.1.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "adfdv" / "step-1.2.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "adfdv" / "step-3.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "adfdv" / "step-4.1.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "adfdv" / "step-4.2.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Dataflow-DataServiceSelect.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Dataflow-DataDeploy.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Dataflow-FunctionsDeploy.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "QA-AzureArchitectureReview.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "QA-AzureDependencyReview.prompt.md",
)

_AAGD_AZURE_FILES = (
    _REPO_ROOT / ".github" / "prompts" / "steps" / "aagd" / "step-2.2.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "aagd" / "step-2.3.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "aagd" / "step-3.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AgentTestCoding.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AgentCoding.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AgentDeploy.prompt.md",
)

_ADD_SERVICE_DESIGN_PROMPT = (
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AddServiceDesign.prompt.md"
)
_ADD_SERVICE_DEPLOY_PROMPT = (
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AddServiceDeploy.prompt.md"
)
_FOUNDRY_SELECTION_PROMPTS = (
    _ADD_SERVICE_DESIGN_PROMPT,
    _ADD_SERVICE_DEPLOY_PROMPT,
)


def _assert_microsoft_learn_mcp_contract(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "Microsoft Learn MCP" in text, f"{path} に Microsoft Learn MCP 参照規律が無い"
    assert "利用可能なら必ず参照" in text, f"{path} に利用可能時の必須参照規律が無い"
    assert "title / URL / 確認事項" in text, f"{path} に根拠記録形式が無い"
    assert "要確認（Microsoft Learn MCP 未取得）" in text, f"{path} に未取得時の留保表現が無い"
    assert "推測で確定しない" in text, f"{path} に推測確定禁止が無い"


def test_asdw_add_service_prompts_and_templates_require_microsoft_learn_mcp() -> None:
    """ASDW-WEB 追加 Azure サービス系 Step.2 は Microsoft Learn MCP 根拠を必須化する。"""
    for path in _ASDW_ADD_SERVICE_FILES:
        _assert_microsoft_learn_mcp_contract(path)


def test_foundry_design_prompt_requires_project_architecture_documentation() -> None:
    """Design は account と Project の概念・作成境界を公式資料で確認する。"""
    text = _ADD_SERVICE_DESIGN_PROMPT.read_text(encoding="utf-8")
    assert "検索結果から対象ページを特定" in text
    assert "全文取得" in text
    for slug in (
        "foundry/how-to/create-projects",
        "foundry/concepts/architecture",
    ):
        assert slug in text, slug


def test_foundry_deploy_prompt_requires_project_provisioning_documentation() -> None:
    """Deploy は quickstart と Project how-to の操作手順を全文確認する。"""
    text = _ADD_SERVICE_DEPLOY_PROMPT.read_text(encoding="utf-8")
    assert "検索結果から対象ページを特定" in text
    assert "全文取得" in text
    for slug in (
        "foundry/tutorials/quickstart-create-foundry-resources",
        "foundry/how-to/create-projects",
    ):
        assert slug in text, slug


def test_foundry_selection_prompts_require_model_router_and_version_guidance() -> None:
    """モデル配置・Router・version管理を別の選定根拠として確認させる。"""
    required_slugs = (
        "foundry/foundry-models/how-to/create-model-deployments",
        "foundry/openai/how-to/model-router",
        "foundry/foundry-models/concepts/model-versions",
    )
    for path in _FOUNDRY_SELECTION_PROMPTS:
        text = path.read_text(encoding="utf-8")
        for slug in required_slugs:
            assert slug in text, f"{path}: {slug}"
        assert "az cognitiveservices account list-models" in text, path


def test_foundry_selection_prompts_distinguish_quickstart_example_from_selection() -> None:
    """quickstart のモデル例を最新・推奨モデルとして採用させない。"""
    for path in _FOUNDRY_SELECTION_PROMPTS:
        text = path.read_text(encoding="utf-8")
        assert "quickstart のモデル例" in text, path
        assert "選定根拠にしない" in text, path


def test_foundry_selection_prompts_require_live_evidence_fields() -> None:
    """モデル選定証跡に取得時点と対象環境を残させる。"""
    common_fields = (
        "取得日（ISO）",
        "対象 region",
        "モデルバージョン",
        "デプロイ種別(sku-name)",
        "quota",
    )
    design_text = _ADD_SERVICE_DESIGN_PROMPT.read_text(encoding="utf-8")
    deploy_text = _ADD_SERVICE_DEPLOY_PROMPT.read_text(encoding="utf-8")
    for field in common_fields:
        assert field in design_text, f"{_ADD_SERVICE_DESIGN_PROMPT}: {field}"
        assert field in deploy_text, f"{_ADD_SERVICE_DEPLOY_PROMPT}: {field}"
    assert "対象 account" in deploy_text


def test_asdw_compute_prompts_and_templates_require_microsoft_learn_mcp() -> None:
    """ASDW-WEB Compute / Functions / Static Web Apps 系 Step は Microsoft Learn MCP 根拠を必須化する。"""
    for path in _ASDW_COMPUTE_FILES:
        _assert_microsoft_learn_mcp_contract(path)


def test_service_coding_prompt_requires_exact_azure_mcp_template_id() -> None:
    """Azure Functions template は Azure MCP の利用可能一覧にある正確な ID を使う。"""
    path = _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-ServiceCoding-AzureFunctions.prompt.md"
    text = path.read_text(encoding="utf-8")
    assert "Azure MCP" in text
    assert "Functions template" in text
    assert "正確な ID" in text
    assert "HttpTrigger" in text
    assert "推測で固定指定しない" in text


def test_asdw_azure_review_prompts_and_templates_require_microsoft_learn_mcp() -> None:
    """ASDW-WEB Azure レビュー系 Step は Microsoft Learn MCP 根拠を必須化する。"""
    for path in _ASDW_AZURE_REVIEW_FILES:
        _assert_microsoft_learn_mcp_contract(path)


def test_aad_add_service_prompt_and_template_require_microsoft_learn_mcp() -> None:
    """AAD-WEB 追加 Azure サービス選定 Step は Microsoft Learn MCP 根拠を必須化する。"""
    for path in _AAD_AZURE_FILES:
        _assert_microsoft_learn_mcp_contract(path)


def test_adfdv_azure_prompts_and_templates_require_microsoft_learn_mcp() -> None:
    """ADFDV Azure データフロー系 Step は Microsoft Learn MCP 根拠を必須化する。"""
    for path in _ADFDV_AZURE_FILES:
        _assert_microsoft_learn_mcp_contract(path)


def test_aagd_azure_prompts_and_templates_require_microsoft_learn_mcp() -> None:
    """AAGD Azure AI Foundry 系 Step は Microsoft Learn MCP 根拠を必須化する。"""
    for path in _AAGD_AZURE_FILES:
        _assert_microsoft_learn_mcp_contract(path)


def test_aagd_capability_providers_require_current_official_evidence_without_version_pinning() -> None:
    """選択providerだけを実装し、公式根拠・確認日なしにAPI versionを固定しない。"""
    test_coding = (
        _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AgentTestCoding.prompt.md"
    ).read_text(encoding="utf-8")
    coding = (
        _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AgentCoding.prompt.md"
    ).read_text(encoding="utf-8")
    deploy = (
        _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AgentDeploy.prompt.md"
    ).read_text(encoding="utf-8")

    assert "Preferred / Fallbackに選択されたproviderだけをmock/stub化" in test_coding
    assert "Section 7.0のPreferred / Fallbackに選択されたrouteだけを実装" in coding
    assert "supported` / `preview` / `limited-access`として選択されたrouteだけ" in deploy
    for text in (test_coding, coding, deploy):
        assert "title / URL / 確認事項 / 確認日" in text
    assert "API version、SKU、model、regionを実行値として固定しない" in deploy

    fixed_api_version = re.compile(
        r"(?i)(?:api[-_ ]?version|api-version)\s*[:=]\s*[\"']?20\d{2}-\d{2}-\d{2}"
    )
    for text in (test_coding, coding, deploy):
        assert not fixed_api_version.search(text)


def test_rendered_active_azure_step_templates_include_microsoft_learn_mcp_rule() -> None:
    """registry から参照される active Azure Step は render 後に Microsoft Learn MCP 規律を含む。"""
    checked = []
    checked_steps: set[tuple[str, str]] = set()
    for wf in list_workflows():
        for step in wf.steps:
            template_path = getattr(step, "body_template_path", None)
            if not template_path:
                continue
            body = render_template(
                template_path,
                root_issue_num=0,
                params={"branch": "main"},
                wf=wf,
            )
            if "Azure" not in body:
                continue
            checked.append(f"{wf.id}:{step.id}:{template_path}")
            checked_steps.add((wf.id, step.id))
            assert "Microsoft Learn MCP" in body, checked[-1]
            assert "利用可能なら必ず参照" in body, checked[-1]
            assert "title / URL / 確認事項" in body, checked[-1]
            assert "要確認（Microsoft Learn MCP 未取得）" in body, checked[-1]
            assert "推測で確定しない" in body, checked[-1]

    assert checked, "Azure 関連 active Step テンプレートが検出されていません"
    assert {("aagd", "2.2"), ("aagd", "2.3"), ("aagd", "3")} <= checked_steps
