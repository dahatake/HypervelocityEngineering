"""RED contract for the explicit ASDW Step 1.3 runtime context."""
from __future__ import annotations

import importlib
import os
import re

import pytest


_BOOTSTRAP = {
    "LOCATION": "japaneast",
    "RESOURCE_SUFFIX": "app009",
    "DATA_VNET_CIDR": "10.40.0.0/16",
    "DATA_PRIVATE_ENDPOINT_SUBNET_CIDR": "10.40.1.0/24",
    "DATA_ACI_SUBNET_CIDR": "10.40.2.0/24",
}
_SUBSCRIPTION_ID = "00000000-0000-0000-0000-000000000001"
# 検証イメージは prep stage が同一 run で作成するため、入力ではなく導出値。
_VERIFY_IMAGE_KEYS = frozenset(
    {"DATA_VERIFY_ACR_NAME", "DATA_VERIFY_IMAGE_NAME", "DATA_VERIFY_ACI_IMAGE"}
)
# リソース名・リソース ID・エンドポイントも APP-ID 由来の suffix から導出する。
_RESOURCE_NAME_KEYS = frozenset(
    {
        "SUBSCRIPTION_ID",
        "DATA_NETWORK_MODE",
        "DATA_VNET_NAME",
        "DATA_NAT_GATEWAY_NAME",
        "DATA_PRIVATE_ENDPOINT_SUBNET_ID",
        "DATA_ACI_SUBNET_ID",
        "DATA_DEPLOY_IDENTITY_ID",
        "SQL_PRIVATE_ENDPOINT_NAME",
        "COSMOS_PRIVATE_ENDPOINT_NAME",
        "SQL_PRIVATE_DNS_ZONE",
        "COSMOS_PRIVATE_DNS_ZONE",
        "SQL_SERVER",
        "SQL_HOST",
        "SQL_DATABASE",
        "SQL_DB_SVC01",
        "SQL_DB_SVC02",
        "SQL_DB_SVC03",
        "SQL_DB_SVC07",
        "SQL_DB_SVC09",
        "SQL_DB_SVC12",
        "SQL_AUDIT_TABLE",
        "COSMOS_ACCOUNT",
        "COSMOS_ENDPOINT",
        "COSMOS_DATABASE",
        "COSMOS_CONTAINER_VOC",
        "CONFIDENTIAL_LEDGER_NAME",
        "CONFIDENTIAL_LEDGER_ENDPOINT",
        "CONFIDENTIAL_LEDGER_COLLECTION",
        # 台帳は既定 location 非対応のため専用 location へ fallback する。
        "CONFIDENTIAL_LEDGER_LOCATION",
    }
)
_DERIVED_KEYS = _VERIFY_IMAGE_KEYS | _RESOURCE_NAME_KEYS
_EXPECTED_KEYS = frozenset({"RESOURCE_GROUP", *_BOOTSTRAP, *_DERIVED_KEYS})


def _module():
    return importlib.import_module("hve.asdw_data_runtime_context")


def _build(*, bootstrap=None, resource_group="rg-app009"):
    module = _module()
    return module.build_asdw_data_deploy_bootstrap_context(
        workflow_params={
            "resource_group": resource_group,
        },
        bootstrap_inputs=_BOOTSTRAP if bootstrap is None else bootstrap,
        subscription_id=_SUBSCRIPTION_ID,
    )


def test_every_azure_resource_name_is_derived_and_never_an_operator_input():
    """APP-ID 由来の suffix だけで全リソース名が決まること。"""
    context = _build()

    assert _RESOURCE_NAME_KEYS <= set(context)
    assert context["SUBSCRIPTION_ID"] == _SUBSCRIPTION_ID
    assert context["DATA_NETWORK_MODE"] == "private"
    assert context["DATA_VNET_NAME"] == "vnet-app009"
    assert context["SQL_SERVER"] == "sql-app009"
    assert context["SQL_HOST"] == "sql-app009.database.windows.net"
    assert context["SQL_DB_SVC01"] == "sqldb-svc01-app009"
    assert context["COSMOS_ACCOUNT"] == "cosmos-app009"
    assert (
        context["COSMOS_ENDPOINT"]
        == "https://cosmos-app009.documents.azure.com:443/"
    )
    assert context["DATA_ACI_SUBNET_ID"] == (
        f"/subscriptions/{_SUBSCRIPTION_ID}/resourceGroups/rg-app009"
        "/providers/Microsoft.Network/virtualNetworks/vnet-app009/subnets/snet-aci"
    )
    assert context["DATA_DEPLOY_IDENTITY_ID"].endswith(
        "/userAssignedIdentities/data-deploy-identity"
    )
    # Azure が採番する値は導出できないため、launcher の読み戻しに委ねる。
    assert "DATA_DEPLOY_IDENTITY_CLIENT_ID" not in context


def test_context_rejects_a_subscription_id_that_is_not_a_guid():
    module = _module()
    with pytest.raises(module.AsdwDataDeployContextError, match="SUBSCRIPTION_ID"):
        module.build_asdw_data_deploy_bootstrap_context(
            workflow_params={"resource_group": "rg-app009"},
            bootstrap_inputs=_BOOTSTRAP,
            subscription_id="not-a-guid",
        )


def test_context_accepts_only_declared_bootstrap_inputs_and_is_immutable():
    context = _build()

    assert set(context) == _EXPECTED_KEYS
    assert {
        key: value for key, value in context.items() if key not in _DERIVED_KEYS
    } == {"RESOURCE_GROUP": "rg-app009", **_BOOTSTRAP}
    with pytest.raises(TypeError):
        context["RESOURCE_GROUP"] = "mutated"  # type: ignore[index]


@pytest.mark.parametrize("missing_key", tuple(_BOOTSTRAP))
def test_context_rejects_each_missing_bootstrap_input_before_any_azure_stage(
    missing_key: str,
):
    module = _module()
    bootstrap = dict(_BOOTSTRAP)
    bootstrap.pop(missing_key)

    with pytest.raises(module.AsdwDataDeployContextError, match=missing_key):
        _build(bootstrap=bootstrap)


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("LOCATION", "eastus\nINJECTED=value"),
        ("RESOURCE_SUFFIX", " whitespace "),
        ("DATA_VNET_CIDR", "10.40.0.0/16\x00suffix"),
    ),
)
def test_context_rejects_unsafe_bootstrap_values(key: str, value: str):
    module = _module()
    bootstrap = dict(_BOOTSTRAP)
    bootstrap[key] = value

    with pytest.raises(module.AsdwDataDeployContextError, match=key):
        _build(bootstrap=bootstrap)


def test_context_rejects_verify_image_as_an_external_input():
    """検証イメージは導出値であり、呼出し側から指定させない。"""
    module = _module()
    bootstrap = {**_BOOTSTRAP, "DATA_VERIFY_ACI_IMAGE": "registry.example/verify:v1"}

    with pytest.raises(
        module.AsdwDataDeployContextError,
        match="DATA_VERIFY_ACI_IMAGE",
    ):
        _build(bootstrap=bootstrap)


def test_derived_registry_name_satisfies_azure_naming_rules():
    """ACR 名は global 一意・5〜50 文字・英数字のみ。"""
    name = _build(bootstrap={**_BOOTSTRAP, "RESOURCE_SUFFIX": "royalty-dev"})[
        "DATA_VERIFY_ACR_NAME"
    ]

    assert re.fullmatch(r"[a-z0-9]{5,50}", name)
    assert "royaltydev" in name


def test_derived_registry_name_is_deterministic_per_deployment_scope():
    same = _build()["DATA_VERIFY_ACR_NAME"]
    other_group = _build(resource_group="rg-other")["DATA_VERIFY_ACR_NAME"]

    assert same == _build()["DATA_VERIFY_ACR_NAME"]
    assert same != other_group


def test_derived_image_reference_points_at_the_derived_registry():
    context = _build()

    assert context["DATA_VERIFY_ACI_IMAGE"] == (
        f"{context['DATA_VERIFY_ACR_NAME']}.azurecr.io"
        f"/hve-asdw-data-verify:{_BOOTSTRAP['RESOURCE_SUFFIX']}"
    )
    assert "://" not in context["DATA_VERIFY_ACI_IMAGE"]
    assert "@" not in context["DATA_VERIFY_ACI_IMAGE"]


def test_context_rejects_undeclared_bootstrap_key():
    module = _module()
    bootstrap = {**_BOOTSTRAP, "UNDECLARED_VALUE": "ignored-by-default"}

    with pytest.raises(module.AsdwDataDeployContextError, match="UNDECLARED_VALUE"):
        _build(bootstrap=bootstrap)


@pytest.mark.parametrize(
    ("resource_group", "bootstrap"),
    (
        (None, _BOOTSTRAP),
        (" whitespace ", _BOOTSTRAP),
        ("rg-app009\nINJECTED=value", _BOOTSTRAP),
        (123, _BOOTSTRAP),
        (
            "rg-app009",
            {**_BOOTSTRAP, "LOCATION": 123},
        ),
    ),
)
def test_context_rejects_non_string_or_unsafe_workflow_values(
    resource_group,
    bootstrap,
):
    module = _module()

    with pytest.raises(module.AsdwDataDeployContextError):
        _build(resource_group=resource_group, bootstrap=bootstrap)


@pytest.mark.parametrize(
    "resource_suffix",
    ("../escape", "suffix/name", "suffix\\name", "-leading", "trailing-"),
)
def test_context_rejects_unsafe_resource_suffix(resource_suffix: str):
    module = _module()
    bootstrap = {**_BOOTSTRAP, "RESOURCE_SUFFIX": resource_suffix}

    with pytest.raises(module.AsdwDataDeployContextError, match="RESOURCE_SUFFIX"):
        _build(bootstrap=bootstrap)


@pytest.mark.parametrize(
    "bootstrap",
    (
        {**_BOOTSTRAP, "DATA_VNET_CIDR": "not-a-cidr"},
        {**_BOOTSTRAP, "DATA_VNET_CIDR": "2001:db8::/48"},
        {**_BOOTSTRAP, "DATA_PRIVATE_ENDPOINT_SUBNET_CIDR": "10.41.1.0/24"},
        {**_BOOTSTRAP, "DATA_ACI_SUBNET_CIDR": "10.40.1.128/25"},
    ),
)
def test_context_rejects_invalid_or_overlapping_network_ranges(bootstrap):
    module = _module()

    with pytest.raises(module.AsdwDataDeployContextError):
        _build(bootstrap=bootstrap)


def test_context_does_not_read_ambient_environment(monkeypatch):
    monkeypatch.setenv("LOCATION", "ambient-location")
    monkeypatch.setenv("DATA_VNET_CIDR", "192.0.2.0/24")

    context = _build()

    assert context["LOCATION"] == "japaneast"
    assert context["DATA_VNET_CIDR"] == "10.40.0.0/16"
    assert os.environ["LOCATION"] == "ambient-location"
