"""Explicit, non-secret bootstrap inputs for ASDW-WEB Step 1.3."""
from __future__ import annotations

import hashlib
import ipaddress
import re
from types import MappingProxyType
from typing import Any, Mapping


_BOOTSTRAP_KEYS = (
    "LOCATION",
    "RESOURCE_SUFFIX",
    "DATA_VNET_CIDR",
    "DATA_PRIVATE_ENDPOINT_SUBNET_CIDR",
    "DATA_ACI_SUBNET_CIDR",
)
_RESOURCE_SUFFIX_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,22}[a-z0-9])?\Z")

# Registry names are global, 5-50 characters, and alphanumeric only, so the
# hyphens the suffix allows are dropped and a digest of the deployment scope is
# appended to keep the derived name unique across tenants.
_VERIFY_ACR_NAME_PREFIX = "hveasdw"
_VERIFY_ACR_NAME_DIGEST_LENGTH = 8
_VERIFY_IMAGE_REPOSITORY = "hve-asdw-data-verify"

# Step 1.3 only ever deploys the private network route, and the private DNS
# zone names are fixed by the Azure services themselves.
_DATA_NETWORK_MODE = "private"
_SQL_PRIVATE_DNS_ZONE = "privatelink.database.windows.net"
_COSMOS_PRIVATE_DNS_ZONE = "privatelink.documents.azure.com"
# The prep stage always creates the user-assigned identity under this name.
_DEPLOY_IDENTITY_NAME = "data-deploy-identity"
_PRIVATE_ENDPOINT_SUBNET_NAME = "snet-private-endpoint"
_ACI_SUBNET_NAME = "snet-aci"
# Entity-scoped names are part of the data contract, not of the deployment
# scope, so they stay stable across resource groups.
_SQL_AUDIT_TABLE = "AuditRecord"
_COSMOS_CONTAINER_VOC = "VocRecord"
_CONFIDENTIAL_LEDGER_COLLECTION = "AuditRecord"
# Azure Confidential Ledger はリポジトリ標準の `japaneast` / `japanwest` で提供
# されていない。`az provider show --namespace Microsoft.ConfidentialLedger` で
# `Ledgers` の対応 location を確認したところ、Skill `azure-region-policy` §1 の
# 標準優先順位（japaneast -> japanwest -> southeastasia）のうち
# `southeastasia` だけが対応していたため、同 §2 の fallback ルールに従って
# 台帳のみこの location へ退避する。他のリソースは `LOCATION` のままで、
# 監査ダイジェストだけがリージョンをまたぐことになる。
_CONFIDENTIAL_LEDGER_LOCATION = "southeastasia"
_SQL_SERVICE_DATABASE_KEYS = (
    "SQL_DB_SVC01",
    "SQL_DB_SVC02",
    "SQL_DB_SVC03",
    "SQL_DB_SVC07",
    "SQL_DB_SVC09",
    "SQL_DB_SVC12",
)
_SUBSCRIPTION_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z"
)


class AsdwDataDeployContextError(ValueError):
    """Raised when Step 1.3 bootstrap inputs are not explicit and safe."""


def _require_single_line_string(value: Any, key: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise AsdwDataDeployContextError(
            f"ASDW Step 1.3 bootstrap input {key} must be a non-empty single-line string."
        )
    return value


def _require_ipv4_network(value: str, key: str) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(value, strict=True)
    except ValueError as exc:
        raise AsdwDataDeployContextError(
            f"ASDW Step 1.3 bootstrap input {key} must be an IPv4 CIDR."
        ) from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise AsdwDataDeployContextError(
            f"ASDW Step 1.3 bootstrap input {key} must be an IPv4 CIDR."
        )
    return network


def _derive_verify_acr_name(resource_group: str, resource_suffix: str) -> str:
    """Return the registry name this deployment owns for the verification image.

    The digest covers the resource group as well as the suffix, so renaming the
    resource group produces a different registry and leaves the previous one in
    place for the operator to remove.
    """
    scope = f"{resource_group}/{resource_suffix}".encode("utf-8")
    digest = hashlib.sha256(scope).hexdigest()[:_VERIFY_ACR_NAME_DIGEST_LENGTH]
    return f"{_VERIFY_ACR_NAME_PREFIX}{resource_suffix.replace('-', '')}{digest}"


def _derive_resource_names(
    values: dict,
    *,
    subscription_id: str,
) -> None:
    """Fill in every Step 1.3 resource name that HVE itself creates.

    The names are derived from ``RESOURCE_SUFFIX`` (which the workflow derives
    from the APP-ID) so that no operator has to pre-create or hand-name an
    Azure resource before the first run. ``docs/azure/azure-services-data.md``
    prescribes the service topology but no concrete resource names, so the
    derivation below is the single authoritative source for them.
    """
    suffix = values["RESOURCE_SUFFIX"]
    resource_group = values["RESOURCE_GROUP"]
    vnet_name = f"vnet-{suffix}"
    subnet_scope = (
        f"/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Network/virtualNetworks/{vnet_name}/subnets"
    )
    sql_server = f"sql-{suffix}"
    cosmos_account = f"cosmos-{suffix}"
    ledger_name = f"acl-{suffix}"

    values["SUBSCRIPTION_ID"] = subscription_id
    values["DATA_NETWORK_MODE"] = _DATA_NETWORK_MODE
    values["DATA_VNET_NAME"] = vnet_name
    values["DATA_NAT_GATEWAY_NAME"] = f"nat-{suffix}"
    values["DATA_PRIVATE_ENDPOINT_SUBNET_ID"] = (
        f"{subnet_scope}/{_PRIVATE_ENDPOINT_SUBNET_NAME}"
    )
    values["DATA_ACI_SUBNET_ID"] = f"{subnet_scope}/{_ACI_SUBNET_NAME}"
    values["DATA_DEPLOY_IDENTITY_ID"] = (
        f"/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities"
        f"/{_DEPLOY_IDENTITY_NAME}"
    )
    values["SQL_PRIVATE_ENDPOINT_NAME"] = f"pe-sql-{suffix}"
    values["COSMOS_PRIVATE_ENDPOINT_NAME"] = f"pe-cosmos-{suffix}"
    values["SQL_PRIVATE_DNS_ZONE"] = _SQL_PRIVATE_DNS_ZONE
    values["COSMOS_PRIVATE_DNS_ZONE"] = _COSMOS_PRIVATE_DNS_ZONE

    values["SQL_SERVER"] = sql_server
    values["SQL_HOST"] = f"{sql_server}.database.windows.net"
    values["SQL_DATABASE"] = f"sqldb-{suffix}"
    for key in _SQL_SERVICE_DATABASE_KEYS:
        service = key.rsplit("_", 1)[-1].lower()
        values[key] = f"sqldb-{service}-{suffix}"
    values["SQL_AUDIT_TABLE"] = _SQL_AUDIT_TABLE

    values["COSMOS_ACCOUNT"] = cosmos_account
    values["COSMOS_ENDPOINT"] = f"https://{cosmos_account}.documents.azure.com:443/"
    values["COSMOS_DATABASE"] = f"cosmosdb-{suffix}"
    values["COSMOS_CONTAINER_VOC"] = _COSMOS_CONTAINER_VOC

    values["CONFIDENTIAL_LEDGER_NAME"] = ledger_name
    values["CONFIDENTIAL_LEDGER_ENDPOINT"] = (
        f"https://{ledger_name}.confidential-ledger.azure.com"
    )
    values["CONFIDENTIAL_LEDGER_COLLECTION"] = _CONFIDENTIAL_LEDGER_COLLECTION
    values["CONFIDENTIAL_LEDGER_LOCATION"] = _CONFIDENTIAL_LEDGER_LOCATION


def build_asdw_data_deploy_bootstrap_context(
    *,
    workflow_params: Mapping[str, Any],
    bootstrap_inputs: Mapping[str, Any],
    subscription_id: str,
) -> Mapping[str, str]:
    """Validate and freeze the declared inputs needed before the first Azure write.

    Only ``resource_group`` and the declared bootstrap inputs come from the
    caller. Every Azure resource name, resource ID and endpoint is derived here
    from ``RESOURCE_SUFFIX`` and ``subscription_id``, because Step 1.3 creates
    those resources itself and nothing exists to look up before the first run.
    ``DATA_DEPLOY_IDENTITY_CLIENT_ID`` is deliberately absent: it is a value
    Azure assigns, so the launcher reads it back after the prep stage.
    """
    if set(bootstrap_inputs) != set(_BOOTSTRAP_KEYS):
        missing = [key for key in _BOOTSTRAP_KEYS if key not in bootstrap_inputs]
        extra = sorted(set(bootstrap_inputs) - set(_BOOTSTRAP_KEYS))
        if missing:
            raise AsdwDataDeployContextError(
                "ASDW Step 1.3 bootstrap input is missing: " + missing[0]
            )
        raise AsdwDataDeployContextError(
            "ASDW Step 1.3 bootstrap input is undeclared: " + extra[0]
        )

    values = {
        "RESOURCE_GROUP": _require_single_line_string(
            workflow_params.get("resource_group"),
            "RESOURCE_GROUP",
        )
    }
    for key in _BOOTSTRAP_KEYS:
        values[key] = _require_single_line_string(bootstrap_inputs[key], key)

    if not _RESOURCE_SUFFIX_PATTERN.fullmatch(values["RESOURCE_SUFFIX"]):
        raise AsdwDataDeployContextError(
            "ASDW Step 1.3 bootstrap input RESOURCE_SUFFIX must be a lowercase deployment slug."
        )
    acr_name = _derive_verify_acr_name(
        values["RESOURCE_GROUP"],
        values["RESOURCE_SUFFIX"],
    )
    image_name = f"{_VERIFY_IMAGE_REPOSITORY}:{values['RESOURCE_SUFFIX']}"
    values["DATA_VERIFY_ACR_NAME"] = acr_name
    values["DATA_VERIFY_IMAGE_NAME"] = image_name
    values["DATA_VERIFY_ACI_IMAGE"] = f"{acr_name}.azurecr.io/{image_name}"

    vnet = _require_ipv4_network(values["DATA_VNET_CIDR"], "DATA_VNET_CIDR")
    private_endpoint_subnet = _require_ipv4_network(
        values["DATA_PRIVATE_ENDPOINT_SUBNET_CIDR"],
        "DATA_PRIVATE_ENDPOINT_SUBNET_CIDR",
    )
    aci_subnet = _require_ipv4_network(
        values["DATA_ACI_SUBNET_CIDR"],
        "DATA_ACI_SUBNET_CIDR",
    )
    if not private_endpoint_subnet.subnet_of(vnet):
        raise AsdwDataDeployContextError(
            "ASDW Step 1.3 bootstrap input DATA_PRIVATE_ENDPOINT_SUBNET_CIDR must stay inside DATA_VNET_CIDR."
        )
    if not aci_subnet.subnet_of(vnet):
        raise AsdwDataDeployContextError(
            "ASDW Step 1.3 bootstrap input DATA_ACI_SUBNET_CIDR must stay inside DATA_VNET_CIDR."
        )
    if private_endpoint_subnet.overlaps(aci_subnet):
        raise AsdwDataDeployContextError(
            "ASDW Step 1.3 bootstrap subnets must not overlap."
        )

    if not _SUBSCRIPTION_ID_PATTERN.fullmatch(
        _require_single_line_string(subscription_id, "SUBSCRIPTION_ID")
    ):
        raise AsdwDataDeployContextError(
            "ASDW Step 1.3 SUBSCRIPTION_ID must be a lowercase Azure subscription GUID."
        )
    _derive_resource_names(values, subscription_id=subscription_id)

    return MappingProxyType(values)
