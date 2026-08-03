"""Azure CLI deploy Skill の Policy/private connectivity 契約テスト。"""
from __future__ import annotations

from pathlib import Path
import re


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL = (
    _REPO_ROOT
    / ".github"
    / "skills"
    / "azure-skills"
    / "azure-cli-deploy-scripts"
    / "SKILL.md"
)
# network key の SSOT（SKILL.md §2.5 はここへ委譲する）
_CONTRACT = _SKILL.parent / "references" / "asdw-data-verifier-contract.md"


def _skill_text() -> str:
    return _SKILL.read_text(encoding="utf-8")


def _section(text: str, heading: str, next_heading: str) -> str:
    return text.split(heading, 1)[1].split(next_heading, 1)[0]


def test_policy_preflight_runs_before_azure_write_and_fails_closed() -> None:
    text = _skill_text()
    section = _section(text, "### §1.2.1", "### §1.3")

    required = (
        "最初の Azure write",
        "direct assignment",
        "inherited assignment",
        "notScopes",
        "resourceSelectors",
        "policyExemptions",
        "policyAssignmentId",
        "userPrincipalId",
        "groupPrincipalId",
        "enforcementMode",
        "definitionVersion",
        "definition の `mode`",
        "policySetDefinitions",
        "policyDefinitions",
        "policyDefinitionReferenceId",
        "reference mapping",
        "overrides",
        "effective effect",
        "`append.details`",
        "対象 field 自体が不在",
        "親 property",
        "planned API version",
        "Modifiable",
        "conflictEffect",
        "fail-closed",
    )
    for phrase in required:
        assert phrase in section

    assert section.index("planned request") < section.index("§2.3 の経路")


def test_policy_decision_matrix_has_only_the_four_planned_routes() -> None:
    text = _skill_text()
    section = _section(text, "### §2.3", "### §2.4")
    routes = {
        cells[0].strip("` ")
        for line in section.splitlines()
        if line.startswith("|")
        for cells in [[cell.strip() for cell in line.strip("|").split("|")]]
        if cells and cells[0] not in {"Route", "---"}
    }

    assert routes == {"public", "private", "nsp", "blocked"}
    assert "特定組織の Policy 名や assignment 名による判定は禁止" in text
    assert "Policy exemption を自動" in section
    assert "許可タグを自動" in section

    private_row = next(
        line for line in section.splitlines() if line.startswith("| `private`")
    )
    assert "effective `append`" in private_row
    assert "無効値を補完" in private_row
    assert "競合して deny" in private_row
    assert "planned payload" in private_row
    assert "`blocked`" in private_row


def test_nsp_route_requires_enforced_mode_and_preview_approval() -> None:
    text = _skill_text()
    section = _section(text, "### §2.3", "### §2.4")

    assert "provisioningState=Succeeded" in section
    assert "access mode=`Enforced`" in section
    assert "Transition mode" in section
    assert "Public Preview" in section
    assert "明示承認済み" in section


def test_private_route_requires_separate_subnets_dns_nat_and_managed_identity() -> None:
    text = _skill_text()
    section = _section(text, "### §2.4", "### §2.5")

    assert "Private Endpoint 専用 subnet" in section
    assert "Azure Container Instances 専用 subnet" in section
    assert "Microsoft.ContainerInstance/containerGroups" in section
    assert "NAT Gateway" in section
    assert "Private DNS zone" in section
    assert "User-assigned Managed Identity" in section
    assert "固定 CIDR" in section
    assert "人手承認" in section
    assert "az cloud show --query name" in section
    assert "AzureCloud" in section
    assert "他 cloud" in section
    assert "`blocked`" in section
    assert "--disable-private-endpoint-network-policies false" in section
    assert "既定は network policy を有効化" in section


def test_subscription_and_tenant_are_pinned_before_write() -> None:
    text = _skill_text()
    section = _section(text, "### §1.1", "### §1.2 Resource Group")
    lines = [line.strip() for line in section.splitlines()]
    list_line = next(line for line in lines if "az account list --all" in line)
    set_line = next(line for line in lines if "az account set --subscription" in line)
    show_line = next(line for line in lines if "az account show --query" in line)

    assert "`SUBSCRIPTION_ID` を必須入力" in section
    assert "id == SUBSCRIPTION_ID" in list_line
    assert "tenantId" in list_line
    assert "0件または複数件なら停止" in list_line
    assert "を必須実行" in set_line
    assert "代替方式は使用しない" in set_line
    assert "id == SUBSCRIPTION_ID" in show_line
    assert "tenantId == 期待値" in show_line
    assert "どちらかが一致しない場合は write を開始しない" in show_line
    assert section.index(list_line) < section.index(set_line) < section.index(show_line)


def test_network_env_contract_declaration_is_exact() -> None:
    """network key の SSOT は reference 契約側で正確に宣言される。

    SKILL.md §2.5 は SSOT へ委譲するだけで key を複製しない（重複宣言の drift 防止）。
    """
    skill_section = _section(_skill_text(), "### §2.5", "## §3")
    assert "asdw-data-verifier-contract.md" in skill_section
    assert "正本" in skill_section
    assert re.findall(r"^- `([A-Z][A-Z0-9_]+)`$", skill_section, re.MULTILINE) == []

    expected_keys = {
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
    contract_text = _CONTRACT.read_text(encoding="utf-8")
    declared_keys = re.findall(r"^- `([A-Z][A-Z0-9_]+)`$", contract_text, re.MULTILINE)

    assert set(declared_keys) == expected_keys
    assert "全キーを実際に consume" in contract_text


def test_network_env_contract_keys_match_the_validator_ssot() -> None:
    """reference 契約の key 集合が HVE 実装側 SSOT と一致する。"""
    from hve.artifact_validation import _ASDW_DATA_DEPLOY_NETWORK_KEYS

    contract_text = _CONTRACT.read_text(encoding="utf-8")
    declared_keys = set(
        re.findall(r"^- `([A-Z][A-Z0-9_]+)`$", contract_text, re.MULTILINE)
    )

    assert declared_keys == set(_ASDW_DATA_DEPLOY_NETWORK_KEYS)
    assert "未使用キー" in contract_text
    assert "DATA_VERIFY_ACI_IMAGE" in contract_text
    assert "mssql-python" in contract_text
    assert "Authentication=ActiveDirectoryMSI" in contract_text
    assert "ODBC版 `sqlcmd -G`" in contract_text


def test_verification_image_is_hve_derived_and_built_by_the_prep_stage() -> None:
    """検証イメージは呼出し側の持ち込みではなく prep stage が作成する。"""
    contract_text = _CONTRACT.read_text(encoding="utf-8")
    section = _section(
        contract_text,
        "#### prep stage の検証イメージ契約",
        "## HVE-owned producer contract",
    )

    assert "`DATA_VERIFY_ACR_NAME` の Azure Container Registry を SKU `Basic` で冪等に作成" in section
    assert "src/infra/azure/data-verify" in section
    assert "`az acr build`" in section
    assert "`acrpull`" in section
    assert "`principalId` に対して行い、`id` を使わない" in section
    assert "system-assigned managed identity による ACR pull をサポートしない" in section
    assert "`--acr-identity`" in section
    assert "global 一意・5〜50 文字・英数字のみ" in section
    assert "`RESOURCE_GROUP` と `RESOURCE_SUFFIX` から決定論的に導出" in section
    assert "admin user、共有キー、pull secret、`docker login` を使用しない" in section
    assert "https://learn.microsoft.com/azure/container-instances/using-azure-container-registry-mi" in section


def test_prep_stage_owns_the_registry_and_fails_closed() -> None:
    """registry の作成・ビルド・ロール付与は prep に閉じ、代替経路へ fallback しない。"""
    contract_text = _CONTRACT.read_text(encoding="utf-8")
    section = _section(
        contract_text,
        "#### prep stage の検証イメージ契約",
        "## HVE-owned producer contract",
    )

    assert (
        "`DATA_VERIFY_ACR_NAME` を consume するのは prep stage だけであり、"
        "create / registration / verify stage へは渡さない"
        in section
    )
    assert "ACI を作成する create / registration / verify stage より前に順序を固定" in section
    assert (
        "別 SKU への自動引き上げ、admin user の有効化、"
        "ローカル build への切り替えを行わず prep を非ゼロ終了"
        in section
    )
    assert "`DATA_VERIFY_ACR_NAME`はprep stageにだけ渡す" in contract_text


def test_derived_verification_image_keys_are_not_caller_supplied() -> None:
    """導出キーは呼出し側 environment の正本ではないことを契約が明示する。"""
    contract_text = _CONTRACT.read_text(encoding="utf-8")

    assert (
        "`DATA_VERIFY_ACR_NAME` / `DATA_VERIFY_ACI_IMAGE`を含むその他すべての"
        "resource名・resource ID・endpointの唯一の正本は、"
        "`RESOURCE_GROUP` / `RESOURCE_SUFFIX` / `SUBSCRIPTION_ID`から"
        in contract_text
    )
    assert "これらの導出キーをexport・上書きしない" in contract_text
    assert "承認済み検証イメージ" not in contract_text


def test_resource_names_are_derived_from_the_app_id_not_requested_from_the_user() -> None:
    """利用者への必須入力は Azure リソースグループ名だけであることを契約が固定する。"""
    contract_text = _CONTRACT.read_text(encoding="utf-8")

    assert (
        "`RESOURCE_SUFFIX`はworkflowがAPP-IDから導出するため、"
        "利用者がAzureリソース名を事前に決めたりexportしたりする必要はない"
        in contract_text
    )
    assert "`SUBSCRIPTION_ID`の唯一の正本は`az account show`の読み取り結果" in contract_text


def test_identity_client_id_is_read_back_between_stages() -> None:
    """Azure が採番する clientId だけは prep 後の読み戻しであることを契約が示す。"""
    contract_text = _CONTRACT.read_text(encoding="utf-8")

    assert (
        "唯一の例外は`DATA_DEPLOY_IDENTITY_CLIENT_ID`で、これはAzureがprep stageでの"
        "user-assigned identity作成時に採番するため、launcherがprep成功後に"
        "`az identity show --query clientId`で読み戻して後続stageへ注入する"
        in contract_text
    )


def test_policy_and_private_network_evidence_uses_official_sources() -> None:
    text = _skill_text()

    urls = {
        "https://learn.microsoft.com/azure/governance/policy/concepts/effect-modify#modify-evaluation",
        "https://learn.microsoft.com/azure/governance/policy/concepts/effect-append#append-evaluation",
        "https://learn.microsoft.com/azure/governance/policy/concepts/assignment-structure",
        "https://learn.microsoft.com/azure/governance/policy/concepts/initiative-definition-structure",
        "https://learn.microsoft.com/azure/governance/policy/concepts/policy-applicability",
        "https://learn.microsoft.com/azure/governance/policy/concepts/exemption-structure",
        "https://learn.microsoft.com/azure/azure-sql/database/private-endpoint-overview",
        "https://learn.microsoft.com/azure/cosmos-db/how-to-configure-private-endpoints",
        "https://learn.microsoft.com/azure/private-link/private-endpoint-dns",
        "https://learn.microsoft.com/azure/container-instances/container-instances-vnet",
        "https://learn.microsoft.com/azure/container-instances/container-instances-managed-identity",
        "https://learn.microsoft.com/azure/private-link/network-security-perimeter-concepts",
        "https://learn.microsoft.com/cli/azure/manage-azure-subscriptions-azure-cli",
        "https://learn.microsoft.com/azure/private-link/disable-private-endpoint-network-policy",
        "https://learn.microsoft.com/azure/private-link/secure-private-link#network-security",
    }
    for url in urls:
        assert f"]({url})" in text
    assert "title / URL / 確認事項" in text
