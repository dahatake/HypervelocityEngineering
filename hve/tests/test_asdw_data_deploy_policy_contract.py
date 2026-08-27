"""ASDW-WEB Step.1.3 の Policy-aware private deploy 契約テスト。"""
from __future__ import annotations

from pathlib import Path
import re

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCUMENTS = (
    _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-DataDeploy.prompt.md",
    _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web" / "step-1.3.prompt.md",
)
_AZURE_CLI_SKILL = (
    _REPO_ROOT
    / ".github"
    / "skills"
    / "azure-skills"
    / "azure-cli-deploy-scripts"
    / "SKILL.md"
)
_SHARED_CONTRACT = (
    _AZURE_CLI_SKILL.parent
    / "references"
    / "asdw-data-verifier-contract.md"
)
_SHARED_CONTRACT_REPO_PATH = (
    ".github/skills/azure-skills/azure-cli-deploy-scripts/"
    "references/asdw-data-verifier-contract.md"
)
_DEPLOY_HEADING = "## Step 1.3 DataDeploy network contract"
_DEPLOY_HEADING_RE = re.compile(
    rf"^{re.escape(_DEPLOY_HEADING)}$",
    re.MULTILINE,
)
_PUBLIC_ROUTE_HEADING = "#### `public` route"
_PUBLIC_ROUTE_HEADING_RE = re.compile(
    rf"^{re.escape(_PUBLIC_ROUTE_HEADING)}$",
    re.MULTILINE,
)
_COMBINED_MODES_HEADING = "### `public` / `nsp` / `blocked` mode"
_COMBINED_MODES_HEADING_RE = re.compile(
    rf"^{re.escape(_COMBINED_MODES_HEADING)}$",
    re.MULTILINE,
)
_DEPLOY_DELEGATION_SENTENCE = (
    "Skill `azure-cli-deploy-scripts` の `"
    f"{_SHARED_CONTRACT_REPO_PATH}` にある Step 1.3 DataDeploy 契約を適用する。"
)
_NETWORK_KEYS = {
    "DATA_NETWORK_MODE",
    "DATA_VNET_NAME",
    "DATA_PRIVATE_ENDPOINT_SUBNET_ID",
    "DATA_ACI_SUBNET_ID",
    "DATA_NAT_GATEWAY_NAME",
    "DATA_DEPLOY_IDENTITY_ID",
    "DATA_DEPLOY_IDENTITY_CLIENT_ID",
    "SQL_PRIVATE_ENDPOINT_NAME",
    "COSMOS_PRIVATE_ENDPOINT_NAME",
    "SQL_PRIVATE_DNS_ZONE",
    "COSMOS_PRIVATE_DNS_ZONE",
}
_DEPLOY_NETWORK_DETAILS = (
    "az container create",
    "az container delete",
    "aci_created",
    "aci_wait_failed",
    "aci_name",
    "cleanup_aci",
    "trap cleanup_aci",
    "timeout 600 az container logs",
    "DATA_REGISTER_RUN_ID",
    "hveRegisterRunId",
    "登録ACI cleanup完了後",
    "UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID",
    "DefaultAzureCredential(managed_identity_client_id",
    "mssql-python",
    "azure-cosmos",
)
_STEP_12_FAIL_CLOSED_SENTENCE = (
    "固定 evidence schema が未定義のため、最初の Azure CLI / SDK / "
    "data-plane 呼び出しより前に `[ERROR]` を出力して非ゼロ終了する。"
)
_STEP_12_NO_ROUTE_ATTEMPT_SENTENCE = (
    "直接接続、一時 ACI、retry、fallback を開始しない。"
)
_POLICY_PREP_LAUNCHER_SENTENCE = (
    "Policy pre-flight は、HVE所有 `python -m hve.asdw_data_script_launcher prep` "
    "が実行する prep script の先頭 read-only 処理として実施する。"
)


def _without_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _without_fenced_code(text: str) -> str:
    return re.sub(r"^```.*?^```\s*$", "", text, flags=re.DOTALL | re.MULTILINE)


def _shared_contract_text() -> str:
    assert _SHARED_CONTRACT.is_file(), (
        "ASDW data network contract must have one Skill-owned SSOT: "
        f"{_SHARED_CONTRACT}"
    )
    return _SHARED_CONTRACT.read_text(encoding="utf-8")


def _deploy_contract(text: str) -> str:
    visible = _without_fenced_code(_without_html_comments(text))
    headings = list(_DEPLOY_HEADING_RE.finditer(visible))
    assert len(headings) == 1, (
        f"expected exactly one {_DEPLOY_HEADING!r}, found {len(headings)}"
    )
    section = visible[headings[0].end() :]
    next_heading = re.search(r"^## (?!#)", section, re.MULTILINE)
    return section if next_heading is None else section[: next_heading.start()]


def _deploy_public_route_contract(text: str) -> str:
    section = _deploy_contract(text)
    combined_headings = list(_COMBINED_MODES_HEADING_RE.finditer(section))
    assert len(combined_headings) == 1
    combined = section[combined_headings[0].end() :]
    next_combined_heading = re.search(r"^#{1,3}\s+", combined, re.MULTILINE)
    if next_combined_heading is not None:
        combined = combined[: next_combined_heading.start()]
    headings = list(_PUBLIC_ROUTE_HEADING_RE.finditer(combined))
    assert len(headings) == 1
    public = combined[headings[0].end() :]
    next_heading = re.search(r"^#{1,4}\s+", public, re.MULTILINE)
    return public if next_heading is None else public[: next_heading.start()]


def _assert_registration_then_verification_order(text: str) -> None:
    registration_cleanup = text.index("登録ACI cleanup完了後")
    snapshot = text.index("同じimmutable environment snapshot")
    verifier = text.index("verify stageを開始")
    run_id = text.index("`DATA_VERIFY_RUN_ID`だけをそのstage用に生成")
    assert registration_cleanup < snapshot < verifier < run_id
    assert "登録ACI内でverifierを実行しない" in text


def _network_contract(text: str) -> str:
    text = _without_html_comments(text)
    heading = "## HVE launcher environment contract"
    assert heading in text, f"missing network contract heading: {heading}"
    section = text.split(heading, 1)[1]
    next_heading = re.search(r"^(?:## (?!#)|<task>)", section, re.MULTILINE)
    return section if next_heading is None else section[: next_heading.start()]


def test_html_comment_only_network_contract_is_not_accepted() -> None:
    with pytest.raises(AssertionError, match="missing network contract heading"):
        _network_contract("<!--\n## HVE launcher environment contract\n-->")


def test_policy_preflight_happens_before_any_azure_write() -> None:
    for path in _DOCUMENTS:
        text = path.read_text(encoding="utf-8")
        assert "azure-cli-deploy-scripts" in text, path
        assert "最初の Azure write より前" in text, path
        assert "inherited assignment" in text, path
        assert "public access alias" in text, path
        assert "fail-closed" in text, path
        assert "`public` / `private` / `nsp` / `blocked`" in text, path
        assert "Policy pre-flight・route 決定・CIDR 承認確認" in text, path
        assert "Resource Group 作成や provider 登録を含む最初の Azure write" in text, path
        assert text.index("Policy pre-flight・route 決定・CIDR 承認確認") < text.index(
            "Resource Group 作成や provider 登録を含む最初の Azure write"
        ), path
        assert _POLICY_PREP_LAUNCHER_SENTENCE in text, path
        assert "standalone の `az policy ...` shell 要求を発行しない" in text, path


def test_app_catalog_is_required_and_missing_or_empty_stops_before_write() -> None:
    for path in _DOCUMENTS:
        text = path.read_text(encoding="utf-8")
        catalog_lines = [
            line for line in text.splitlines() if "app-catalog.md" in line
        ]
        assert any(
            "必須" in line
            and "存在しない" in line
            and "空" in line
            and "停止" in line
            for line in catalog_lines
        ), path
        assert "全件処理" not in "\n".join(catalog_lines), path


def test_prompt_and_template_consume_the_shared_network_contract() -> None:
    contract = _deploy_contract(_shared_contract_text())
    declared = re.findall(r"^- `([A-Z][A-Z0-9_]+)`$", contract, re.MULTILINE)
    assert len(declared) == len(_NETWORK_KEYS)
    assert set(declared) == _NETWORK_KEYS
    assert all(declared.count(key) == 1 for key in _NETWORK_KEYS)
    assert "全キーを実際に consume" in contract
    assert "別 mode への黙示 fallback" in contract

    for path in _DOCUMENTS:
        raw_text = path.read_text(encoding="utf-8")
        visible_text = _without_html_comments(raw_text)
        assert visible_text.count(_DEPLOY_DELEGATION_SENTENCE) == 1, path
        assert raw_text.count(_DEPLOY_DELEGATION_SENTENCE) == 1, path
        assert "## HVE launcher environment contract" not in raw_text, path
        assert not (
            _NETWORK_KEYS & set(re.findall(r"\b[A-Z][A-Z0-9_]+\b", raw_text))
        ), path
        for detail in _DEPLOY_NETWORK_DETAILS:
            assert detail not in raw_text, (path, detail)


def test_skill_links_the_shared_contract_once() -> None:
    skill = _without_html_comments(_AZURE_CLI_SKILL.read_text(encoding="utf-8"))
    assert skill.count("](references/asdw-data-verifier-contract.md)") == 1
    assert "## HVE launcher environment contract" not in skill
    assert not (
        _NETWORK_KEYS & set(re.findall(r"\b[A-Z][A-Z0-9_]+\b", skill))
    )


def test_private_route_requires_approved_topology_and_managed_identity() -> None:
    section = _deploy_contract(_shared_contract_text())
    private = section.split("### `private` mode", 1)[1].split(
        "### `public` / `nsp` / `blocked` mode", 1
    )[0]
    for phrase in (
            "人手承認済み",
            "Private Endpoint 専用 subnet",
            "Azure Container Instances 専用 subnet",
            "NAT Gateway",
            "SQL / Cosmos の Private Endpoint",
            "Private DNS zone",
            "User-assigned Managed Identity",
            "VNet 内の一時 ACI",
            "DefaultAzureCredential",
            "DATA_VERIFY_ACI_IMAGE",
            "mssql-python",
            "Authentication=ActiveDirectoryMSI",
            "azure-cosmos",
            "接続文字列、共有キー、長期 token を保存しない",
            "DATA_NETWORK_MODE を route 分岐",
            "DATA_VNET_NAME を VNet の作成または再利用",
            "DATA_PRIVATE_ENDPOINT_SUBNET_ID を Private Endpoint subnet",
            "DATA_ACI_SUBNET_ID を registration / verify ACI の --subnet",
            "DATA_NAT_GATEWAY_NAME を ACI subnet の NAT Gateway",
            "DATA_DEPLOY_IDENTITY_ID を --assign-identity",
            "DATA_DEPLOY_IDENTITY_CLIENT_ID を AZURE_CLIENT_ID",
            "SQL_PRIVATE_ENDPOINT_NAME / COSMOS_PRIVATE_ENDPOINT_NAME を Private Endpoint 名",
            "SQL_PRIVATE_DNS_ZONE / COSMOS_PRIVATE_DNS_ZONE を DNS zone",
    ):
        assert phrase in private, phrase


def test_private_registration_uses_one_shot_aci_and_passwordless_credentials() -> None:
    section = _deploy_contract(_shared_contract_text())
    private = section.split("### `private` mode", 1)[1].split(
        "### `public` / `nsp` / `blocked` mode", 1
    )[0]
    command = (
            'az container create --resource-group "$RESOURCE_GROUP" '
            '--name "$aci_name" --image "$DATA_VERIFY_ACI_IMAGE" '
            '--subnet "$DATA_ACI_SUBNET_ID" '
            '--acr-identity "$DATA_DEPLOY_IDENTITY_ID" '
            '--assign-identity "$DATA_DEPLOY_IDENTITY_ID" '
            '--restart-policy Never --os-type Linux --cpu 1 --memory 1 '
            '--command-line "$aci_command"'
    )
    delete_command = (
            'az container delete --resource-group "$RESOURCE_GROUP" '
            '--name "$aci_name" --yes'
    )
    assert "`az container show --query \"tags.hveRegisterRunId\"`" in private
    assert command in private
    assert delete_command in private
    assert '`aci_name="data-register-$DATA_REGISTER_RUN_ID"' in private
    assert '`--tags hveRegisterRunId="$DATA_REGISTER_RUN_ID"`' in private
    assert "作成前に同名のACIが存在すれば非ゼロ終了" in private
    assert "create失敗または応答不明時には既存ACIを削除してはならない" in private
    assert "ローカル端末から SQL / Cosmos の data-plane へ直接接続しない" in private
    assert (
        "public endpoint / firewall rule / 共有キー / SAS / "
        "秘密を含む接続文字列 / 長期 token への fallback を禁止する"
        in private
    )
    assert (
        "UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;"
        "Authentication=ActiveDirectoryMSI;Encrypt=yes;"
        "TrustServerCertificate=no"
    ) in private
    assert (
        "credential = DefaultAzureCredential(managed_identity_client_id="
        "DATA_DEPLOY_IDENTITY_CLIENT_ID); client = CosmosClient(endpoint, "
        "credential=credential)"
    ) in private


def test_registration_and_verification_aci_ownership_is_sequential_and_not_nested() -> None:
    text = _deploy_contract(_shared_contract_text())
    assert "登録ACI cleanup完了後" in text
    assert "`DATA_VERIFY_RUN_ID`だけをそのstage用に生成" in text
    assert "Agentまたは制御hostがnetwork key、image、resource名、run IDを再exportしてはならない" in text
    assert "verifier自身に`source`/`.`を追加してはならない" in text
    assert "verify stageを開始" in text
    for key in (*sorted(_NETWORK_KEYS), "DATA_VERIFY_ACI_IMAGE"):
        assert f"`{key}`" in text, key
    assert "登録ACI内でverifierを実行しない" in text
    assert "検証ACIはStep.1.2 verifierが所有" in text
    _assert_registration_then_verification_order(text)

    verifier_contract = _network_contract(_shared_contract_text())
    private = verifier_contract.split("### `private` mode", 1)[1].split(
        "### `nsp` mode", 1
    )[0]
    assert "検証 ACI の作成と cleanup は verifier が所有" in private
    assert "DataDeploy の登録 ACI 内で verifier を実行しない" in private


@pytest.mark.parametrize(
    "text",
    (
        "同じimmutable environment snapshot\nverify stageを開始\n"
        "`DATA_VERIFY_RUN_ID`だけをそのstage用に生成\n登録ACI cleanup完了後\n"
        "登録ACI内でverifierを実行しない",
        "登録ACI cleanup完了後\n"
        "verify stageを開始\n"
        "同じimmutable environment snapshot\n"
        "`DATA_VERIFY_RUN_ID`だけをそのstage用に生成\n"
        "登録ACI内でverifierを実行しない",
        "登録ACI cleanup完了後\n同じimmutable environment snapshot\n"
        "verify stageを開始\n`DATA_VERIFY_RUN_ID`だけをそのstage用に生成",
    ),
)
def test_registration_verification_order_rejects_reversed_or_nested_contract(
    text: str,
) -> None:
    with pytest.raises((AssertionError, ValueError)):
        _assert_registration_then_verification_order(text)


def test_nsp_is_blocked_until_the_shared_evidence_schema_exists() -> None:
    section = _deploy_contract(_shared_contract_text())
    assert "現時点では固定 schema 未定義" in section
    assert "`nsp` は `blocked`" in section
    assert "NSP を自動作成しない" in section


def test_policy_incompatible_public_route_is_not_retried() -> None:
    text = _deploy_contract(_shared_contract_text())
    public_route = _deploy_public_route_contract(_shared_contract_text())
    assert "public access enable" in text
    assert "AllowAzureServices" in text
    assert "firewall rule" in text
    assert "retry 候補から除外" in text
    assert "Policy exemption" in text
    assert (
        "`public` は Policy と入力設計の両方で許可された場合だけ使用する"
        in public_route
    )
    assert _STEP_12_FAIL_CLOSED_SENTENCE not in public_route
    assert _STEP_12_NO_ROUTE_ATTEMPT_SENTENCE not in public_route
    assert "public routeを常に非ゼロ終了" not in public_route

    for path in _DOCUMENTS:
        raw_text = path.read_text(encoding="utf-8")
        assert "AllowAzureServices" not in raw_text, path
        assert "firewall rule" not in raw_text, path
        assert "retry 候補" not in raw_text, path


def test_public_route_policy_cannot_move_to_a_later_subsection() -> None:
    text = f"""
{_DEPLOY_HEADING}
### `public` / `nsp` / `blocked` mode
{_PUBLIC_ROUTE_HEADING}
- public route details
#### `nsp` route
- `public` は Policy と入力設計の両方で許可された場合だけ使用する。
"""
    public_route = _deploy_public_route_contract(text)
    assert "Policy と入力設計の両方" not in public_route


def test_public_route_heading_cannot_move_outside_combined_modes_section() -> None:
    text = f"""
{_DEPLOY_HEADING}
{_COMBINED_MODES_HEADING}
- combined mode details
### unrelated section
{_PUBLIC_ROUTE_HEADING}
- `public` は Policy と入力設計の両方で許可された場合だけ使用する。
"""
    with pytest.raises(AssertionError):
        _deploy_public_route_contract(text)


def test_service_catalog_is_created_only_after_green_ac1() -> None:
    for path in _DOCUMENTS:
        text = path.read_text(encoding="utf-8")
        assert "AC-1 `✅`" in text, path
        assert "service-catalog.md" in text, path
        assert "存在しない場合は必ず生成" in text, path
        assert "AC-1 `❌`" in text, path
        assert "docs/ / src を更新しない" in text, path
        assert "AC-1 ❌ 確定後は即終了" in text, path


def test_green_tdd_report_has_fixed_asdw_step_1_3_metadata() -> None:
    for path in _DOCUMENTS:
        text = path.read_text(encoding="utf-8")
        assert (
            "tests/run/<run-id>/asdw-web/step-1-3/<target-app-id>/GREEN/"
            "tdd-test-report.md"
        ) in text, path
        assert "Workflow: asdw-web" in text, path
        assert "Step: 1.3" in text, path
        assert "Phase: GREEN" in text, path
