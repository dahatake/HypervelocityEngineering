"""ASDW Step 1.3 prep/create static contract and byte-pinned launcher tests."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from hve.artifact_validation import (
    _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST,
    _build_asdw_non_audit_aci_command,
    validate_asdw_data_create_scripts,
    validate_asdw_data_registration_script,
)


_SQL_MODE = """# Azure data design

## 1. エンティティ別ストア選定

| Entity | Data characteristics（構造/更新頻度/サイズ） | Access patterns（主要クエリ/ホットパス） | Consistency（強/最終/要件根拠） | Chosen Azure service（正式名称） | Partition/Key/Index（要点） | Rationale（3〜6行） | Alternatives（最大2つ） | Evidence（根拠リンク） |
|---|---|---|---|---|---|---|---|---|
| Member | x | x | x | Azure SQL Database | x | x | x | x |
| VocRecord | x | x | x | Azure Cosmos DB for NoSQL | x | x | x | x |
| AuditRecord | x | x | x | Azure SQL Database の append-only ledger table（SVC-12 の監査証拠 SoT）+ Azure confidential ledger（信頼済み database digest 保管先、条件付き） | x | x | x | x |
"""

_SAMPLE_DATA = """{
  "entities": {
    "Member": [{}],
    "ConsentRecord": [{}],
    "DataRightsRequest": [{}],
    "LoyaltyAccount": [{}],
    "PointTransaction": [{}],
    "Reward": [{}],
    "RewardExchange": [{}],
    "PaidMembershipContract": [{}],
    "SupportCase": [{}],
    "CaseResolution": [{}],
    "VocRecord": [{}],
    "AuditRecord": [{}]
  }
}
"""
_SAMPLE_COUNTS = {
    "Member": 1,
    "ConsentRecord": 1,
    "DataRightsRequest": 1,
    "LoyaltyAccount": 1,
    "PointTransaction": 1,
    "Reward": 1,
    "RewardExchange": 1,
    "PaidMembershipContract": 1,
    "SupportCase": 1,
    "CaseResolution": 1,
    "VocRecord": 1,
    "AuditRecord": 1,
}
_NON_AUDIT_COMMAND = _build_asdw_non_audit_aci_command(
    _SAMPLE_COUNTS,
    _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST,
)

_PREP = r'''#!/usr/bin/env bash
# HVE-ASDW-DATA-PREP-BEGIN
set -euo pipefail
: "${HVE_ASDW_SCRIPT_DIR:?}"
SCRIPT_DIR="$HVE_ASDW_SCRIPT_DIR"
case "${DATA_NETWORK_MODE:?}" in
  private)
    : "${DATA_VNET_NAME:?}"
    : "${DATA_PRIVATE_ENDPOINT_SUBNET_ID:?}"
    : "${DATA_ACI_SUBNET_ID:?}"
    : "${DATA_NAT_GATEWAY_NAME:?}"
    : "${DATA_DEPLOY_IDENTITY_ID:?}"
    : "${DATA_DEPLOY_IDENTITY_CLIENT_ID:?}"
    : "${SQL_PRIVATE_ENDPOINT_NAME:?}"
    : "${COSMOS_PRIVATE_ENDPOINT_NAME:?}"
    : "${SQL_PRIVATE_DNS_ZONE:?}"
    : "${COSMOS_PRIVATE_DNS_ZONE:?}"
    : "${DATA_VNET_CIDR:?}"
    : "${DATA_PRIVATE_ENDPOINT_SUBNET_CIDR:?}"
    : "${DATA_ACI_SUBNET_CIDR:?}"
    : "${DATA_VERIFY_ACR_NAME:?}"
    : "${DATA_VERIFY_IMAGE_NAME:?}"
    policy_assignments="$(az policy assignment list --scope "/subscriptions/$SUBSCRIPTION_ID" --output json)"
    policy_exemptions="$(az policy exemption list --scope "/subscriptions/$SUBSCRIPTION_ID" --output json)"
    if [[ -z "$policy_assignments" || -z "$policy_exemptions" ]]; then
      exit 1
    fi
    hve_policy_preflight_complete=1
    az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
    az provider register --namespace Microsoft.Sql --wait --output none
    az provider register --namespace Microsoft.DocumentDB --wait --output none
    az provider register --namespace Microsoft.ConfidentialLedger --wait --output none
    az provider register --namespace Microsoft.ContainerInstance --wait --output none
    az provider register --namespace Microsoft.ContainerRegistry --wait --output none
    az network vnet create --resource-group "$RESOURCE_GROUP" --name "$DATA_VNET_NAME" --address-prefixes "$DATA_VNET_CIDR" --output none
    az network vnet subnet create --resource-group "$RESOURCE_GROUP" --vnet-name "$DATA_VNET_NAME" --name snet-private-endpoint --address-prefixes "$DATA_PRIVATE_ENDPOINT_SUBNET_CIDR" --output none
    az network vnet subnet create --resource-group "$RESOURCE_GROUP" --vnet-name "$DATA_VNET_NAME" --name snet-aci --address-prefixes "$DATA_ACI_SUBNET_CIDR" --delegations Microsoft.ContainerInstance/containerGroups --output none
    az network nat gateway create --resource-group "$RESOURCE_GROUP" --name "$DATA_NAT_GATEWAY_NAME" --output none
    az network vnet subnet update --ids "$DATA_ACI_SUBNET_ID" --delegations Microsoft.ContainerInstance/containerGroups --nat-gateway "$DATA_NAT_GATEWAY_NAME" --output none
    az identity create --resource-group "$RESOURCE_GROUP" --name data-deploy-identity --output none
    az acr create --resource-group "$RESOURCE_GROUP" --name "$DATA_VERIFY_ACR_NAME" --sku Basic --output none
    cd "$SCRIPT_DIR/data-verify"
    az acr build --registry "$DATA_VERIFY_ACR_NAME" --image "$DATA_VERIFY_IMAGE_NAME" --file Dockerfile .
    cd "$SCRIPT_DIR"
    data_identity_principal_id="$(az identity show --resource-group "$RESOURCE_GROUP" --name data-deploy-identity --query principalId --output tsv)"
    az role assignment create --assignee "$data_identity_principal_id" --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.ContainerRegistry/registries/$DATA_VERIFY_ACR_NAME" --role acrpull --output none
    ;;
  public)
    printf '[ERROR] public route is blocked\n' >&2
    exit 1
    ;;
  nsp)
    printf '[ERROR] nsp route is blocked\n' >&2
    exit 1
    ;;
  blocked)
    printf '[ERROR] blocked route\n' >&2
    exit 1
    ;;
  *)
    printf '[ERROR] invalid route\n' >&2
    exit 1
    ;;
esac
# HVE-ASDW-DATA-PREP-END
'''

_CREATE = r'''#!/usr/bin/env bash
# HVE-ASDW-DATA-CREATE-BEGIN
set -euo pipefail
: "${HVE_ASDW_SCRIPT_DIR:?}"
SCRIPT_DIR="$HVE_ASDW_SCRIPT_DIR"
case "${DATA_NETWORK_MODE:?}" in
  private)
    : "${DATA_VNET_NAME:?}"
    : "${DATA_PRIVATE_ENDPOINT_SUBNET_ID:?}"
    : "${DATA_ACI_SUBNET_ID:?}"
    : "${DATA_NAT_GATEWAY_NAME:?}"
    : "${DATA_DEPLOY_IDENTITY_ID:?}"
    : "${DATA_DEPLOY_IDENTITY_CLIENT_ID:?}"
    : "${SQL_PRIVATE_ENDPOINT_NAME:?}"
    : "${COSMOS_PRIVATE_ENDPOINT_NAME:?}"
    : "${SQL_PRIVATE_DNS_ZONE:?}"
    : "${COSMOS_PRIVATE_DNS_ZONE:?}"
        : "${DATA_VERIFY_ACI_IMAGE:?}"
        : "${DATA_CREATE_RUN_ID:?}"
        : "${HVE_ASDW_SAMPLE_DATA_JSON:?}"
        : "${SQL_SERVER:?}"
        : "${SQL_HOST:?}"
        : "${SQL_DATABASE:?}"
        : "${SQL_DB_SVC01:?}"
        : "${SQL_DB_SVC02:?}"
        : "${SQL_DB_SVC03:?}"
        : "${SQL_DB_SVC07:?}"
        : "${SQL_DB_SVC09:?}"
    : "${SQL_DB_SVC12:?}"
    : "${SQL_AUDIT_TABLE:?}"
        : "${COSMOS_ACCOUNT:?}"
        : "${COSMOS_ENDPOINT:?}"
        : "${COSMOS_DATABASE:?}"
        : "${COSMOS_CONTAINER_VOC:?}"
        : "${CONFIDENTIAL_LEDGER_NAME:?}"
        : "${CONFIDENTIAL_LEDGER_ENDPOINT:?}"
        if [[ ! "$DATA_CREATE_RUN_ID" =~ ^[0-9a-f]{32}$ ]]; then
            exit 1
        fi
        if ! command -v timeout >/dev/null 2>&1; then
            exit 1
        fi
    policy_assignments="$(az policy assignment list --scope "/subscriptions/$SUBSCRIPTION_ID" --output json)"
    policy_exemptions="$(az policy exemption list --scope "/subscriptions/$SUBSCRIPTION_ID" --output json)"
    if [[ -z "$policy_assignments" || -z "$policy_exemptions" ]]; then
      exit 1
    fi
    hve_policy_preflight_complete=1
    az network private-endpoint create --resource-group "$RESOURCE_GROUP" --name "$SQL_PRIVATE_ENDPOINT_NAME" --subnet "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" --private-connection-resource-id "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Sql/servers/$SQL_SERVER" --group-id sqlServer --output none
    az network private-endpoint create --resource-group "$RESOURCE_GROUP" --name "$COSMOS_PRIVATE_ENDPOINT_NAME" --subnet "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" --private-connection-resource-id "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.DocumentDB/databaseAccounts/$COSMOS_ACCOUNT" --group-id Sql --output none
    az network private-dns zone create --resource-group "$RESOURCE_GROUP" --name "$SQL_PRIVATE_DNS_ZONE" --output none
    az network private-dns zone create --resource-group "$RESOURCE_GROUP" --name "$COSMOS_PRIVATE_DNS_ZONE" --output none
    az network private-dns link vnet create --resource-group "$RESOURCE_GROUP" --zone-name "$SQL_PRIVATE_DNS_ZONE" --name sql-data-link --virtual-network "$DATA_VNET_NAME" --registration-enabled false --output none
    az network private-dns link vnet create --resource-group "$RESOURCE_GROUP" --zone-name "$COSMOS_PRIVATE_DNS_ZONE" --name cosmos-data-link --virtual-network "$DATA_VNET_NAME" --registration-enabled false --output none
    az network private-endpoint dns-zone-group create --resource-group "$RESOURCE_GROUP" --endpoint-name "$SQL_PRIVATE_ENDPOINT_NAME" --name default --zone-name "$SQL_PRIVATE_DNS_ZONE" --output none
    az network private-endpoint dns-zone-group create --resource-group "$RESOURCE_GROUP" --endpoint-name "$COSMOS_PRIVATE_ENDPOINT_NAME" --name default --zone-name "$COSMOS_PRIVATE_DNS_ZONE" --output none
    az sql server create --resource-group "$RESOURCE_GROUP" --name "$SQL_SERVER" --enable-ad-only-auth --external-admin-principal-type Application --external-admin-name data-deploy-identity --external-admin-sid "$DATA_DEPLOY_IDENTITY_CLIENT_ID" --enable-public-network false --output none
    az sql db create --resource-group "$RESOURCE_GROUP" --server "$SQL_SERVER" --name "$SQL_DATABASE" --output none
    az cosmosdb create --resource-group "$RESOURCE_GROUP" --name "$COSMOS_ACCOUNT" --disable-local-auth true --public-network-access Disabled --output none
    az cosmosdb sql database create --resource-group "$RESOURCE_GROUP" --account-name "$COSMOS_ACCOUNT" --name "$COSMOS_DATABASE" --output none
    az cosmosdb sql container create --resource-group "$RESOURCE_GROUP" --account-name "$COSMOS_ACCOUNT" --database-name "$COSMOS_DATABASE" --name "$COSMOS_CONTAINER_VOC" --partition-key-path /sourceRecordId --output none
    az confidentialledger create --resource-group "$RESOURCE_GROUP" --name "$CONFIDENTIAL_LEDGER_NAME" --output none
        az sql db ledger-digest-uploads enable --resource-group "$RESOURCE_GROUP" --server "$SQL_SERVER" --name "$SQL_DB_SVC12" --endpoint "$CONFIDENTIAL_LEDGER_ENDPOINT"
        non_audit_command="__NON_AUDIT_COMMAND__"
        data_aci_name="data-create-$DATA_CREATE_RUN_ID"
        data_aci_created=0
        cleanup_data_aci() {
            if [[ "$data_aci_created" == "1" ]]; then
                data_aci_owner="$(az container show --resource-group "$RESOURCE_GROUP" --name "$data_aci_name" --query "tags.hveCreateRunId" --output tsv 2>/dev/null || true)"
                if [[ "$data_aci_owner" == "$DATA_CREATE_RUN_ID" ]]; then
                    az container delete --resource-group "$RESOURCE_GROUP" --name "$data_aci_name" --yes || true
                fi
            fi
        }
        trap cleanup_data_aci EXIT INT TERM
        data_aci_name_count="$(az container list --resource-group "$RESOURCE_GROUP" --query "[?name=='$data_aci_name'] | length(@)" --output tsv)"
        if [[ "$data_aci_name_count" != "0" ]]; then
            exit 1
        fi
        az container create --resource-group "$RESOURCE_GROUP" --name "$data_aci_name" --tags hveCreateRunId="$DATA_CREATE_RUN_ID" --image "$DATA_VERIFY_ACI_IMAGE" --subnet "$DATA_ACI_SUBNET_ID" --acr-identity "$DATA_DEPLOY_IDENTITY_ID" --assign-identity "$DATA_DEPLOY_IDENTITY_ID" --restart-policy Never --os-type Linux --cpu 1 --memory 1 --secure-environment-variables NON_AUDIT_DATA_JSON="$HVE_ASDW_SAMPLE_DATA_JSON" --environment-variables AZURE_CLIENT_ID="$DATA_DEPLOY_IDENTITY_CLIENT_ID" SQL_HOST="$SQL_HOST" SQL_DB_SVC01="$SQL_DB_SVC01" SQL_DB_SVC02="$SQL_DB_SVC02" SQL_DB_SVC03="$SQL_DB_SVC03" SQL_DB_SVC07="$SQL_DB_SVC07" SQL_DB_SVC09="$SQL_DB_SVC09" SQL_DB_SVC12="$SQL_DB_SVC12" SQL_AUDIT_TABLE="$SQL_AUDIT_TABLE" COSMOS_ENDPOINT="$COSMOS_ENDPOINT" COSMOS_DATABASE="$COSMOS_DATABASE" COSMOS_CONTAINER_VOC="$COSMOS_CONTAINER_VOC" CONFIDENTIAL_LEDGER_ENDPOINT="$CONFIDENTIAL_LEDGER_ENDPOINT" DATA_DEPLOY_IDENTITY_CLIENT_ID="$DATA_DEPLOY_IDENTITY_CLIENT_ID" --command-line "$non_audit_command"
        data_aci_created=1
        data_aci_wait_failed=0
        data_aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$data_aci_name" --follow)" || data_aci_wait_failed=1
        data_aci_exit_code="$(az container show --resource-group "$RESOURCE_GROUP" --name "$data_aci_name" --query "containers[0].instanceView.currentState.exitCode" --output tsv)"
        if [[ "$data_aci_wait_failed" != "0" || "$data_aci_exit_code" != "0" || "$data_aci_logs" != "HVE_NON_AUDIT_REGISTRATION_OK" ]]; then
            exit 1
        fi
    ;;
  public)
    printf '[ERROR] public route is blocked\n' >&2
    exit 1
    ;;
  nsp)
    printf '[ERROR] nsp route is blocked\n' >&2
    exit 1
    ;;
  blocked)
    printf '[ERROR] blocked route\n' >&2
    exit 1
    ;;
  *)
    printf '[ERROR] invalid route\n' >&2
    exit 1
    ;;
esac
# HVE-ASDW-DATA-CREATE-END
'''.replace("__NON_AUDIT_COMMAND__", _NON_AUDIT_COMMAND.replace('"', r'\"'))


def _write_inputs(tmp_path: Path, *, prep: str = _PREP, create: str = _CREATE):
    prep_path = tmp_path / "src/infra/azure/create-azure-data-resources-prep.sh"
    create_path = tmp_path / "src/infra/azure/create-azure-data-resources.sh"
    design_path = tmp_path / "docs/azure/azure-services-data.md"
    sample_path = tmp_path / "src/data/sample-data.json"
    for path, text in (
        (prep_path, prep),
        (create_path, create),
        (design_path, _SQL_MODE),
        (sample_path, _SAMPLE_DATA),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return prep_path, create_path, design_path, sample_path


def _validate(tmp_path: Path, *, prep: str = _PREP, create: str = _CREATE):
    paths = _write_inputs(tmp_path, prep=prep, create=create)
    return validate_asdw_data_create_scripts(
        paths[0], paths[1], design_doc_path=paths[2], sample_data_path=paths[3]
    )


def test_accepts_private_design_aware_prep_and_create(tmp_path: Path) -> None:
    assert _validate(tmp_path) == []


def test_current_tracked_producers_pass_the_generator_contract() -> None:
    """After the controlled migration the tracked producers are generator output.

    Sub-013 replaced the stale public producers with the HVE generator's
    promoted set, so both static validators must accept the tracked files. This
    guards against a drift back to a stale/public or hand-edited producer.
    """
    repo_root = Path(__file__).resolve().parents[2]
    create_errors = validate_asdw_data_create_scripts(
        repo_root / "src/infra/azure/create-azure-data-resources-prep.sh",
        repo_root / "src/infra/azure/create-azure-data-resources.sh",
        design_doc_path=repo_root / "docs/azure/azure-services-data.md",
        sample_data_path=repo_root / "src/data/sample-data.json",
    )
    assert create_errors == []
    registration_errors = validate_asdw_data_registration_script(
        repo_root / "src/data/azure/data-registration-script.sh",
        design_doc_path=repo_root / "docs/azure/azure-services-data.md",
    )
    assert registration_errors == []


def test_current_tracked_producers_are_byte_identical_to_generator_output() -> None:
    """Sub-013 invariant: the tracked producers equal the deterministic render.

    A validator-passing check still allows a hand-edited valid variant. This
    asserts the tracked bytes are exactly the generator's render of the current
    design and sample inputs, so the only sanctioned way to change a producer
    is to regenerate it — never a manual edit and never a design/sample change
    left without regeneration.
    """
    from hve.asdw_data_script_generator import render_asdw_data_producers

    repo_root = Path(__file__).resolve().parents[2]
    design = (repo_root / "docs/azure/azure-services-data.md").read_text(
        encoding="utf-8"
    )
    sample = (repo_root / "src/data/sample-data.json").read_text(encoding="utf-8")
    rendered = render_asdw_data_producers(design_text=design, sample_data_text=sample)
    for relative_path, expected in rendered.items():
        expected_bytes = (
            expected if isinstance(expected, bytes) else expected.encode("utf-8")
        )
        assert (repo_root / relative_path).read_bytes() == expected_bytes, relative_path


def test_rejects_crlf_or_bom(tmp_path: Path) -> None:
    prep_path, create_path, design_path, sample_path = _write_inputs(tmp_path)
    prep_path.write_bytes(b"\xef\xbb\xbf" + _PREP.replace("\n", "\r\n").encode())
    errors = validate_asdw_data_create_scripts(
        prep_path,
        create_path,
        design_doc_path=design_path,
        sample_data_path=sample_path,
    )
    assert any("UTF-8 BOM" in error or "LF" in error for error in errors)
