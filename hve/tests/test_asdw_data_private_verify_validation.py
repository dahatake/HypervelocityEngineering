"""ASDW-WEB Step.1.2/1.3 private-aware verifier の静的 gate 契約。"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

import pytest

from hve.artifact_validation import (
    validate_asdw_data_registration_script,
    validate_asdw_data_verify_script,
)
from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner
from hve.tests.asdw_data_verify_fixtures import PRIVATE_VERIFIER


_PRIVATE_VERIFIER = PRIVATE_VERIFIER

_REGISTRATION_ACI = r"""#!/usr/bin/env bash
set -euo pipefail
: "${DATA_REGISTER_RUN_ID:?}"
aci_name="data-register-$DATA_REGISTER_RUN_ID"
aci_created=0
cleanup_aci() {
    if [[ "$aci_created" == "1" ]]; then
        aci_owner="$(az container show --resource-group "$RESOURCE_GROUP" --name "$aci_name" --query "tags.hveRegisterRunId" --output tsv 2>/dev/null || true)"
        if [[ "$aci_owner" == "$DATA_REGISTER_RUN_ID" ]]; then
            az container delete --resource-group "$RESOURCE_GROUP" --name "$aci_name" --yes || true
        fi
    fi
}
trap cleanup_aci EXIT INT TERM
if az container show --resource-group "$RESOURCE_GROUP" --name "$aci_name" --only-show-errors; then
    exit 1
fi
az container create --resource-group "$RESOURCE_GROUP" --name "$aci_name" --tags hveRegisterRunId="$DATA_REGISTER_RUN_ID"
aci_created=1
"""


def test_registration_aci_owner_gate_accepts_fixed_lifecycle(tmp_path: Path) -> None:
    script = tmp_path / "data-registration-script.sh"
    script.write_text(_REGISTRATION_ACI, encoding="utf-8")

    assert validate_asdw_data_registration_script(script) == []


@pytest.mark.parametrize(
    "source",
    (
        '--tags hveRegisterRunId="$DATA_REGISTER_RUN_ID"',
        'if az container show --resource-group "$RESOURCE_GROUP" --name "$aci_name" --only-show-errors; then\n    exit 1\nfi\n',
        '"$aci_owner" == "$DATA_REGISTER_RUN_ID"',
    ),
)
def test_registration_aci_owner_gate_rejects_missing_ownership_control(
    tmp_path: Path, source: str
) -> None:
    script = tmp_path / "data-registration-script.sh"
    script.write_text(_REGISTRATION_ACI.replace(source, "", 1), encoding="utf-8")

    assert validate_asdw_data_registration_script(script)


def test_registration_aci_owner_gate_accepts_multiline_create_and_follow_up(
    tmp_path: Path,
) -> None:
    script = tmp_path / "data-registration-script.sh"
    script.write_text(
        _REGISTRATION_ACI.replace(
            'az container create --resource-group "$RESOURCE_GROUP" --name "$aci_name" --tags hveRegisterRunId="$DATA_REGISTER_RUN_ID"\naci_created=1',
            'az container create \\\n+    --resource-group "$RESOURCE_GROUP" \\\n+    --name "$aci_name" \\\n+    --tags hveRegisterRunId="$DATA_REGISTER_RUN_ID"\naci_created=1\naz container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name"',
        ),
        encoding="utf-8",
    )
    script.write_text(
        script.read_text(encoding="utf-8").replace("\n+", "\n"),
        encoding="utf-8",
    )

    assert validate_asdw_data_registration_script(script) == []


def test_private_aware_verifier_passes_private_capability_gate(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(_PRIVATE_VERIFIER, encoding="utf-8")

    assert validate_asdw_data_verify_script(
        script, private_capability_required=True
    ) == []


def test_public_only_verifier_is_rejected_when_private_capability_is_required(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        "#!/usr/bin/env bash\naz cosmosdb show --name \"$COSMOS_ACCOUNT\"\n",
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("DATA_NETWORK_MODE" in error for error in errors)
    assert any("DATA_ACI_SUBNET_ID" in error for error in errors)
    assert any("DATA_DEPLOY_IDENTITY_ID" in error for error in errors)


def test_comment_only_private_contract_is_rejected(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        "#!/usr/bin/env bash\n# " + " ".join(
            (
                "DATA_NETWORK_MODE private) DATA_PRIVATE_ENDPOINT_SUBNET_ID",
                "DATA_ACI_SUBNET_ID DATA_DEPLOY_IDENTITY_ID",
                "DATA_DEPLOY_IDENTITY_CLIENT_ID SQL_PRIVATE_ENDPOINT_NAME",
                "COSMOS_PRIVATE_ENDPOINT_NAME az container create --subnet",
                "--assign-identity DefaultAzureCredential verify_sql verify_cosmos",
            )
        ) + "\n",
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("DATA_NETWORK_MODE" in error for error in errors)


def test_identity_missing_verifier_is_rejected_when_private_capability_is_required(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(_PRIVATE_VERIFIER.replace('--assign-identity "$DATA_DEPLOY_IDENTITY_ID"', ""), encoding="utf-8")

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("--assign-identity" in error for error in errors)


def test_private_sql_aci_rejects_implicit_sqlcmd_g_authentication(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER
        .replace("python -m pip install mssql-python azure-identity azure-cosmos", "sqlcmd -G")
        .replace("UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;Authentication=ActiveDirectoryMSI", "UID=implicit;Authentication=SqlPassword"),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("ActiveDirectoryMSI" in error or "mssql-python" in error for error in errors)


def test_private_branch_must_be_an_executable_network_mode_case(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'case DATA_NETWORK_MODE in private) "
        + " ".join(
            (
                "DATA_VNET_NAME DATA_PRIVATE_ENDPOINT_SUBNET_ID DATA_ACI_SUBNET_ID",
                "DATA_NAT_GATEWAY_NAME DATA_DEPLOY_IDENTITY_ID",
                "DATA_DEPLOY_IDENTITY_CLIENT_ID SQL_PRIVATE_ENDPOINT_NAME",
                "COSMOS_PRIVATE_ENDPOINT_NAME SQL_PRIVATE_DNS_ZONE",
                "COSMOS_PRIVATE_DNS_ZONE DATA_VERIFY_ACI_IMAGE",
                "az container create --subnet --assign-identity",
                "mssql-python ActiveDirectoryMSI azure-cosmos",
                "DefaultAzureCredential CosmosClient verify_sql verify_cosmos ;; esac",
            )
        )
        + "'\n",
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("executable `case" in error and "private" in error for error in errors)


def test_private_aci_must_use_aci_subnet_not_private_endpoint_subnet(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            '--subnet "$DATA_ACI_SUBNET_ID" --acr-identity',
            '--subnet "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" --acr-identity',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("DATA_ACI_SUBNET_ID" in error and "--subnet" in error for error in errors)


def test_private_aci_must_assign_declared_user_identity(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            '--assign-identity "$DATA_DEPLOY_IDENTITY_ID"',
            '--assign-identity "$OTHER_IDENTITY_ID"',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("DATA_DEPLOY_IDENTITY_ID" in error and "--assign-identity" in error for error in errors)


def test_private_cosmos_direct_local_execution_is_rejected(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            '--command-line "$aci_command"',
            '--command-line "echo ACI-does-not-run-verifier"\n    python -c "$aci_command"',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("SQL/Cosmos" in error and "ACI" in error for error in errors)


def test_private_sql_requires_uami_client_id_in_connection_string(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;Authentication=ActiveDirectoryMSI",
            "UID=unrelated-client;Authentication=ActiveDirectoryMSI",
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("SQL" in error and "DATA_DEPLOY_IDENTITY_CLIENT_ID" in error for error in errors)


def test_private_cosmos_requires_default_credential_on_cosmos_client(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "credential=credential",
            'credential=os.environ["COSMOS_KEY"]',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("CosmosClient" in error and "credential" in error for error in errors)


def test_private_topology_requires_distinct_subnet_and_identity_comparisons(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            ' || "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" == "$DATA_ACI_SUBNET_ID"',
            "",
        ).replace(
            ' || "$identity_client_id" != "$DATA_DEPLOY_IDENTITY_CLIENT_ID"',
            "",
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("identical" in error for error in errors)
    assert any("clientId" in error for error in errors)


def test_private_topology_requires_approved_private_endpoints_and_dns_links(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace('"$sql_pe_state" != "Approved" || ', "").replace(
            'az network private-dns link vnet list',
            'echo private-dns-link-not-checked',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("Approved" in error for error in errors)
    assert any("VNet link" in error for error in errors)


def test_private_topology_requires_service_matched_dns_zone_and_vnet_link_checks(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "privateDnsZones/$SQL_PRIVATE_DNS_ZONE",
            "privateDnsZones/$COSMOS_PRIVATE_DNS_ZONE",
        ).replace(
            '--zone-name "$SQL_PRIVATE_DNS_ZONE"',
            '--zone-name "$COSMOS_PRIVATE_DNS_ZONE"',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("SQL Private Endpoint DNS" in error for error in errors)
    assert any("SQL Private DNS VNet" in error for error in errors)


def test_private_payload_requires_executed_sql_and_cosmos_count_queries(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            r'cursor.execute(\"SELECT COUNT_BIG(*) FROM [dbo].[example]\"); sql_count=cursor.fetchone()[0]; ',
            "",
        ).replace(
            r'cosmos_count=list(container.query_items(query=\"SELECT VALUE COUNT(1) FROM c\", enable_cross_partition_query=True))[0]; ',
            "",
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("SQL ACI payload" in error and "query" in error for error in errors)
    assert any("Cosmos ACI payload" in error and "query" in error for error in errors)


def test_private_payload_rejects_unreachable_count_queries(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            r'cursor.execute(\"SELECT COUNT_BIG(*) FROM [dbo].[example]\")',
            r'if False: cursor.execute(\"SELECT COUNT_BIG(*) FROM [dbo].[example]\")',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("unreachable" in error and "SQL" in error for error in errors)


def test_private_aci_requires_consistent_name_exit_code_and_logs(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace('--name "$aci_name"', "--name verify-data").replace(
            'if [[ "$aci_exit_code" != "0" || -z "$aci_logs" ]]; then',
            'if [[ -z "$aci_logs" ]]; then',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("`--name`" in error and "aci_name" in error for error in errors)
    assert any("exitCode" in error for error in errors)


def test_private_branch_rejects_unreachable_required_aci_sequence(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'vnet_id="$(az network vnet show',
            'if false; then\n        vnet_id="$(az network vnet show',
        ).replace(
            'if [[ "$aci_exit_code" != "0" || -z "$aci_logs" ]]; then',
            'fi\n        if [[ "$aci_exit_code" != "0" || -z "$aci_logs" ]]; then',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("unreachable" in error and "if false" in error for error in errors)


@pytest.mark.parametrize("guard", ("if false\nthen", "if ! true\nthen"))
def test_private_branch_rejects_multiline_unreachable_required_aci_sequence(
    tmp_path: Path,
    guard: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'vnet_id="$(az network vnet show',
            f"{guard}\n        vnet_id=\"$(az network vnet show",
        ).replace(
            'if [[ "$aci_exit_code" != "0" || -z "$aci_logs" ]]; then',
            'fi\n        if [[ "$aci_exit_code" != "0" || -z "$aci_logs" ]]; then',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("unreachable" in error and "if false" in error for error in errors)


def test_private_branch_rejects_if_not_colon_unreachable_required_aci_sequence(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'vnet_id="$(az network vnet show',
            'if ! :\nthen\n        vnet_id="$(az network vnet show',
        ).replace(
            'if [[ "$aci_exit_code" != "0" || -z "$aci_logs" ]]; then',
            'fi\n        if [[ "$aci_exit_code" != "0" || -z "$aci_logs" ]]; then',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("unreachable" in error and "if false" in error for error in errors)


def test_private_branch_rejects_uninvoked_helper_with_required_sequence(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'vnet_id="$(az network vnet show',
            'verify_private() {\n        vnet_id="$(az network vnet show',
        ).replace(
            '    ;;\n  public|nsp|blocked)',
            '        }\n    ;;\n  public|nsp|blocked)',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("only `cleanup_aci`" in error for error in errors)


def test_private_aci_cleanup_trap_must_be_registered_before_create(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        re.sub(
            r"(?m)^\s*trap cleanup_aci EXIT INT TERM\n",
            "",
            _PRIVATE_VERIFIER,
            count=1,
        ).replace(
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"',
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"\n'
            '        trap cleanup_aci EXIT INT TERM',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("cleanup_aci" in error and "Resource Group" in error for error in errors)


def test_private_aci_cleanup_must_delete_only_the_current_resource_group_aci(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            '--resource-group "$RESOURCE_GROUP" --name "$aci_name" --yes || true',
            '--name "$aci_name" --yes || true; az group delete --name "$RESOURCE_GROUP" --yes',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("cleanup_aci" in error and "Resource Group" in error for error in errors)


def test_private_aci_cleanup_rejects_command_substitution_in_delete_scope(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            '--resource-group "$RESOURCE_GROUP" --name "$aci_name" --yes || true',
            '--resource-group "$RESOURCE_GROUP$(az group delete --name victim --yes)" '
            '--name "$aci_name" --yes || true',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("cleanup_aci" in error and "Resource Group" in error for error in errors)


def test_private_aci_cleanup_accepts_the_fixed_conditional_delete(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            '''cleanup_aci() {
                    if [[ "$aci_may_exist" == "1" ]]; then
                        az container delete --resource-group "$RESOURCE_GROUP" --name "$aci_name" --yes || true
                    fi
                }''',
            """cleanup_aci() {
                if [[ "$aci_created" == "1" ]]; then
                    az container delete --resource-group "$RESOURCE_GROUP" --name "$aci_name" --yes || true
                fi
                }""",
        ),
        encoding="utf-8",
    )

    assert validate_asdw_data_verify_script(
        script, private_capability_required=True
    ) == []


@pytest.mark.parametrize(
    "replacement",
    (
        "aci_created=2",
        "aci_created=0\n                aci_created=1",
    ),
)
def test_private_aci_cleanup_requires_a_safe_creation_lifecycle(
    tmp_path: Path, replacement: str
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace("aci_created=0", replacement, 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("aci_created" in error for error in errors)


def test_private_aci_cleanup_preserves_primary_failure_status(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace("--name \"$aci_name\" --yes || true", "--name \"$aci_name\" --yes"),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("cleanup_aci" in error and "Resource Group" in error for error in errors)


def test_private_aci_cleanup_requires_create_immediately_after_lifecycle_marker(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'az container create --resource-group "$RESOURCE_GROUP" --name "$aci_name"',
            'az container create --resource-group "$RESOURCE_GROUP" --name "$aci_name"\n'
            '                az network vnet show --name "$DATA_VNET_NAME"',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("immediately following" in error for error in errors)


def test_private_aci_cleanup_rejects_ownership_before_create(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'az container create --resource-group "$RESOURCE_GROUP" --name "$aci_name"',
            'aci_created=1\n            az container create --resource-group "$RESOURCE_GROUP" --name "$aci_name"',
            1,
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("aci_created" in error for error in errors)


def test_private_aci_requires_run_id_tag_and_preexisting_name_guard(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace('--tags hveVerifyRunId="$DATA_VERIFY_RUN_ID" ', "").replace(
            'aci_name_count="$(az container list --resource-group "$RESOURCE_GROUP" '
            '--query "[?name==\'$aci_name\'] | length(@)" --output tsv)"\n'
            '                if [[ "$aci_name_count" != "0" ]]; then\n'
            '                    exit 1\n'
            '                fi\n',
            "",
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("tag" in error for error in errors)
    assert any("pre-create ACI lookup" in error for error in errors)


def test_private_aci_cleanup_requires_matching_run_id_tag(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            '"$aci_owner" == "$DATA_VERIFY_RUN_ID"',
            '"$aci_owner" == "untrusted-owner"',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("cleanup_aci" in error and "Resource Group" in error for error in errors)


@pytest.mark.parametrize(
    "wait_command",
    (
        'az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name"',
        'timeout 60 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow',
        'timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name"',
    ),
)
def test_private_aci_requires_fixed_bounded_log_follow_wait(
    tmp_path: Path, wait_command: str
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow',
            wait_command,
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("timeout 600 az container logs" in error for error in errors)


def test_private_aci_requires_timeout_failure_capture(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(" || aci_wait_failed=1", "", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("timeout 600 az container logs" in error for error in errors)


def test_private_aci_timeout_reaches_canonical_exit_code_query(
    tmp_path: Path,
) -> None:
    bash = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
    if not bash.is_file():
        pytest.skip("Git Bash is required to exercise the timeout 124 path")

    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow',
            "printf 'timeout-124\\n' >> \"$TRACE_FILE\"; exit 124",
        ),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    trace = tmp_path / "trace.txt"
    (fake_bin / "az").write_text(
        """#!/usr/bin/env bash
set -eu
case "$*" in
    *"container list"*) printf 'pre-create-count\n' >> "$TRACE_FILE"; printf '0\n' ;;
    *"container create"*) printf 'create\\n' >> "$TRACE_FILE" ;;
    *"tags.hveVerifyRunId"*) printf 'owner-check\\n' >> "$TRACE_FILE"; printf '%s\\n' "$DATA_VERIFY_RUN_ID" ;;
    *"container show"*) printf 'exit-code-show\\n' >> "$TRACE_FILE"; printf '0\\n' ;;
  *"container delete"*) printf 'delete\\n' >> "$TRACE_FILE" ;;
    *"contains(id,"*) printf '/subscriptions/example/vnet/subnets/verified\\n' ;;
  *"network vnet show"*) printf '/subscriptions/example/vnet\\n' ;;
  *"delegations"*) printf '1\\n' ;;
  *"natGateway.id"*) printf '/subscriptions/example/nat-gateway\\n' ;;
  *"private-endpoint show"*"status"*) printf 'Approved\\n' ;;
  *"private-endpoint show"*"subnet.id"*) printf '%s\\n' "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" ;;
  *"dns-zone-group list"*|*"private-dns link vnet list"*) printf '1\\n' ;;
  *"identity show"*) printf '%s\\n' "$DATA_DEPLOY_IDENTITY_CLIENT_ID" ;;
  *) : ;;
esac
""",
        encoding="utf-8",
    )
    for command in (fake_bin / "az",):
        command.chmod(0o755)
    environment = os.environ | {
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "TRACE_FILE": str(trace),
        "DATA_NETWORK_MODE": "private",
        "DATA_VNET_NAME": "data-vnet",
        "DATA_PRIVATE_ENDPOINT_SUBNET_ID": "/subscriptions/example/pe-subnet",
        "DATA_ACI_SUBNET_ID": "/subscriptions/example/aci-subnet",
        "DATA_NAT_GATEWAY_NAME": "nat-gateway",
        "DATA_DEPLOY_IDENTITY_ID": "/subscriptions/example/identity",
        "DATA_DEPLOY_IDENTITY_CLIENT_ID": "identity-client-id",
        "SQL_PRIVATE_ENDPOINT_NAME": "sql-pe",
        "COSMOS_PRIVATE_ENDPOINT_NAME": "cosmos-pe",
        "SQL_PRIVATE_DNS_ZONE": "privatelink.database.windows.net",
        "COSMOS_PRIVATE_DNS_ZONE": "privatelink.documents.azure.com",
        "DATA_VERIFY_ACI_IMAGE": "example.invalid/data-verify:latest",
        "DATA_VERIFY_RUN_ID": "0123456789abcdef0123456789abcdef",
        "RESOURCE_GROUP": "rg-example",
    }

    completed = subprocess.run(
        [str(bash), str(script)], env=environment, capture_output=True, check=False
    )

    assert completed.returncode != 0
    assert trace.exists(), (
        completed.stdout.decode("utf-8", errors="replace")
        + completed.stderr.decode("utf-8", errors="replace")
    )
    assert trace.read_text(encoding="utf-8").splitlines() == [
        "pre-create-count",
        "create",
        "timeout-124",
        "exit-code-show",
        "owner-check",
        "delete",
    ]


@pytest.mark.parametrize(
    "statement",
    ("sql_count == 1 or sys.exit(1); ", "cosmos_count == 1 or sys.exit(1); "),
)
def test_private_aci_requires_nonzero_expected_count_comparison(
    tmp_path: Path, statement: str
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(_PRIVATE_VERIFIER.replace(statement, "", 1), encoding="utf-8")

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("expected value" in error for error in errors)


@pytest.mark.parametrize("optimization", ("PYTHONOPTIMIZE=1 ", "python -O -c"))
def test_private_aci_rejects_python_optimization_for_count_check(
    tmp_path: Path, optimization: str
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    source = _PRIVATE_VERIFIER.replace("python -m pip", f"{optimization}python -m pip", 1)
    if optimization == "python -O -c":
        source = _PRIVATE_VERIFIER.replace("python -c", optimization, 1)
    script.write_text(source, encoding="utf-8")

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("optimization" in error for error in errors)


@pytest.mark.parametrize(
    "mutation",
    (
        "sys.exit=print; ",
        "sys=object(); ",
        "sys.__dict__['exit']=print; ",
        "setattr(sys, 'exit', print); ",
    ),
)
def test_private_aci_rejects_rebound_count_failure_handler(
    tmp_path: Path, mutation: str
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace("import os, sys; ", f"import os, sys; {mutation}", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("failure handler" in error for error in errors)


def test_private_aci_requires_wait_before_canonical_exit_code_query(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)" || aci_wait_failed=1\n'
            '                aci_exit_code="$(az container show --resource-group "$RESOURCE_GROUP" --name "$aci_name" --query "containers[0].instanceView.currentState.exitCode" --output tsv)"',
            'aci_exit_code="$(az container show --resource-group "$RESOURCE_GROUP" --name "$aci_name" --query "containers[0].instanceView.currentState.exitCode" --output tsv)"\n'
            '                aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)" || aci_wait_failed=1',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("fixed bounded log wait" in error or "canonical exitCode" in error for error in errors)


@pytest.mark.parametrize(
    "pre_wait_command",
    (
        'az container show --resource-group "$RESOURCE_GROUP" --name "$aci_name"',
        'az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow',
    ),
)
def test_private_aci_rejects_any_command_before_fixed_wait(
    tmp_path: Path, pre_wait_command: str
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'aci_logs="$(timeout 600 az container logs',
            f"{pre_wait_command}\n                aci_logs=\"$(timeout 600 az container logs",
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("fixed bounded log wait" in error for error in errors)


def test_private_aci_requires_result_condition_after_exit_code_query(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    exit_code = (
        'aci_exit_code="$(az container show --resource-group "$RESOURCE_GROUP" '
        '--name "$aci_name" --query "containers[0].instanceView.currentState.exitCode" '
        '--output tsv)"'
    )
    result = 'if [[ "$aci_wait_failed" != "0" || "$aci_exit_code" != "0" || -z "$aci_logs" ]]; then\n                exit 1\n            fi'
    script.write_text(
        _PRIVATE_VERIFIER.replace(f"{exit_code}\n            {result}", f"{result}\n                {exit_code}"),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("then result condition" in error for error in errors)


def test_private_aci_rejects_name_reassignment_after_create(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'aci_logs="$(timeout 600 az container logs',
            'aci_name="verify-data-$DATA_VERIFY_RUN_ID"\n                aci_logs="$(timeout 600 az container logs',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("aci_name" in error and "exactly once" in error for error in errors)


def test_private_aci_rejects_delete_outside_cleanup_handler(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "trap cleanup_aci EXIT INT TERM",
            "trap cleanup_aci EXIT INT TERM\n"
            '                az container delete --resource-group "$RESOURCE_GROUP" '
            "--name unrelated-aci --yes",
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("delete operation" in error and "cleanup_aci" in error for error in errors)


def test_private_aci_rejects_shell_concatenated_delete_outside_cleanup_handler(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "trap cleanup_aci EXIT INT TERM",
            "trap cleanup_aci EXIT INT TERM\n"
            '                az container de""lete --resource-group "$RESOURCE_GROUP" '
            "--name unrelated-aci --yes",
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("delete operation" in error and "cleanup_aci" in error for error in errors)


@pytest.mark.parametrize(
    "payload_suffix",
    (
        r'; print(\"delete is payload text\")',
        " # delete is a payload comment",
    ),
)
def test_private_aci_ignores_delete_text_in_aci_payload(
    tmp_path: Path,
    payload_suffix: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "print(int(cosmos_count))'\"",
            f"print(int(cosmos_count)){payload_suffix}'\"",
        ),
        encoding="utf-8",
    )

    assert validate_asdw_data_verify_script(
        script, private_capability_required=True
    ) == []


def test_private_aci_rejects_delete_chained_after_aci_command_assignment(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "print(int(cosmos_count))'\"",
            "print(int(cosmos_count))'\"; "
            'az group delete --name "$RESOURCE_GROUP" --yes',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("delete operation" in error and "cleanup_aci" in error for error in errors)


@pytest.mark.parametrize(
    "host_evaluation",
    (
        '$(az group delete --name "$RESOURCE_GROUP" --yes)',
        '`az group delete --name "$RESOURCE_GROUP" --yes`',
        "${!host_command}",
        '<(az group delete --name "$RESOURCE_GROUP" --yes)',
        '>(az group delete --name "$RESOURCE_GROUP" --yes)',
    ),
)
def test_private_aci_rejects_host_evaluation_inside_assignment(
    tmp_path: Path,
    host_evaluation: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'aci_command="python -m pip install',
            f'aci_command="{host_evaluation}python -m pip install',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("host-evaluated" in error and "aci_command" in error for error in errors)


@pytest.mark.parametrize(
    "host_command",
    (
        'd=de; e=lete; az group "$d$e" --name "$RESOURCE_GROUP" --yes',
        'd=de; e=lete; az_runner=az; "$az_runner" group "$d$e" '
        '--name "$RESOURCE_GROUP" --yes',
        'command -p az group de\'lete\' --name "$RESOURCE_GROUP" --yes',
        'az_prefix=a; az_suffix=z; "$az_prefix$az_suffix" group de\'lete\' '
        '--name "$RESOURCE_GROUP" --yes',
        'a\\z role assignment create --assignee victim --role Owner',
        "a$'z' role assignment create --assignee victim --role Owner",
        'az_suffix=z; a${az_suffix} role assignment create --assignee victim '
        '--role Owner',
        'a\\z container create --resource-group "$RESOURCE_GROUP" '
        '--name shadow --image "$DATA_VERIFY_ACI_IMAGE"',
        '\\a\\z role assignment create --assignee victim --role Owner',
        'com\\mand \\a\\z container create --resource-group "$RESOURCE_GROUP" '
        '--name shadow --image "$DATA_VERIFY_ACI_IMAGE"',
        '\\a\\z group de\\lete --name "$RESOURCE_GROUP" --yes',
        "a\\" + "\n                z role assignment create --assignee victim --role Owner",
        'true && a\\z role assignment create --assignee victim --role Owner',
        'false || a\\z container create --resource-group "$RESOURCE_GROUP" '
        '--name shadow --image "$DATA_VERIFY_ACI_IMAGE"',
        'true & a\\z group de\\lete --name "$RESOURCE_GROUP" --yes',
        'X=1 a\\z group de\\lete --name "$RESOURCE_GROUP" --yes',
        'X="1" "$az_runner" group de\\lete --name "$RESOURCE_GROUP" --yes',
    ),
)
def test_private_aci_rejects_dynamic_or_unapproved_host_azure_cli(
    tmp_path: Path,
    host_command: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "trap cleanup_aci EXIT INT TERM",
            f"trap cleanup_aci EXIT INT TERM\n                {host_command}",
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("host Azure CLI" in error for error in errors)


def test_private_aci_rejects_obfuscated_azure_cli_in_condition_evaluation(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'if [[ "$aci_wait_failed" != "0" || "$aci_exit_code" != "0" || -z "$aci_logs" ]]; then',
            'if [[ "$(a\\z group de\\lete --name "$RESOURCE_GROUP" --yes)" == benign ]]; then\n'
            '            :\n'
            '        fi\n'
            '        if [[ "$aci_wait_failed" != "0" || "$aci_exit_code" != "0" || -z "$aci_logs" ]]; then',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("host Azure CLI" in error for error in errors)


@pytest.mark.parametrize("operator", ("&&", "||", "&"))
def test_private_aci_rejects_obfuscated_azure_cli_after_query_line_continuation(
    tmp_path: Path,
    operator: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "trap cleanup_aci EXIT INT TERM",
            "trap cleanup_aci EXIT INT TERM\n"
            f'        az network vnet show --name "$DATA_VNET_NAME" --query id {operator} a\\\n'
            'z group de\\lete --name "$RESOURCE_GROUP" --yes',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("host Azure CLI" in error for error in errors)


@pytest.mark.parametrize(
    "host_evaluation",
    (
        "$(touch /tmp/private-gate-proof)",
        "`touch /tmp/private-gate-proof`",
        "<(touch /tmp/private-gate-proof)",
        ">(touch /tmp/private-gate-proof)",
        r"\$(touch /tmp/private-gate-proof)",
    ),
)
def test_private_aci_rejects_host_evaluation_inside_query_argument(
    tmp_path: Path,
    host_evaluation: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            '--query id --output tsv)',
            f'--query "id{host_evaluation}" --output tsv)',
            1,
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("host Azure CLI" in error for error in errors)


@pytest.mark.parametrize(
    "host_statement",
    (
        'vnet_id="$(az network vnet show --name "$DATA_VNET_NAME" --query id --output tsv)$(printf query-suffix >&2)"',
        'aci_name="verify-data-${RANDOM}$(printf assignment-evaluation >&2)"',
        'identity_client_id="$(printf assignment-evaluation >&2)"',
        "printf '%s\\n' direct-host-command >&2",
    ),
)
def test_private_aci_rejects_unapproved_host_statement(
    tmp_path: Path,
    host_statement: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "trap cleanup_aci EXIT INT TERM",
            f"trap cleanup_aci EXIT INT TERM\n        {host_statement}",
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("host Azure CLI" in error for error in errors)


@pytest.mark.parametrize(
    "host_statement",
    (
        'az network nat gateway show --name "$DATA_NAT_GATEWAY_NAME"; printf bypass >&2',
        'extra="$(az network nat gateway show --name "$DATA_NAT_GATEWAY_NAME"; printf bypass >&2)"',
    ),
)
def test_private_aci_rejects_host_command_chained_to_allowlisted_azure_cli(
    tmp_path: Path,
    host_statement: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "trap cleanup_aci EXIT INT TERM",
            f"trap cleanup_aci EXIT INT TERM\n        {host_statement}",
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("host Azure CLI" in error for error in errors)


def test_private_aci_requires_fail_fast_shell_options(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace("set -euo pipefail\n", ""),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("set -euo pipefail" in error for error in errors)


def test_private_aci_requires_fail_fast_before_network_mode_branch(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "set -euo pipefail\n", ""
        ).replace(
            'esac\n', 'esac\nset -euo pipefail\n', 1
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("set -euo pipefail" in error for error in errors)


@pytest.mark.parametrize(
    "guard",
    (
        'if [[ ! "$DATA_VERIFY_RUN_ID" =~ ^[0-9a-f]{32}$ ]]; then\n'
        '                    exit 1\n'
        '                fi\n',
        'if ! command -v timeout >/dev/null 2>&1; then\n'
        '                    exit 1\n'
        '                fi\n',
    ),
)
def test_private_aci_requires_run_id_and_timeout_preflight_before_azure(
    tmp_path: Path, guard: str
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(_PRIVATE_VERIFIER.replace(guard, "", 1), encoding="utf-8")

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("32 lowercase hex" in error and "GNU timeout" in error for error in errors)


def test_private_aci_name_preflight_must_distinguish_absent_from_lookup_error(
    tmp_path: Path,
) -> None:
    """`container show` の全非ゼロを不存在扱いして create へ進めてはならない。"""
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'aci_name_count="$(az container list --resource-group "$RESOURCE_GROUP" '
            '--query "[?name==\'$aci_name\'] | length(@)" --output tsv)"\n'
            '                if [[ "$aci_name_count" != "0" ]]; then',
            'if az container show --resource-group "$RESOURCE_GROUP" '
            '--name "$aci_name" --only-show-errors; then',
            1,
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("pre-create ACI lookup" in error for error in errors)


@pytest.mark.parametrize(
    "replacement",
    (
        '"$sql_pe_state" != "Approved" && 1 -eq 0 || ',
        '"$identity_client_id" != "$DATA_DEPLOY_IDENTITY_CLIENT_ID" && 1 -eq 0',
    ),
)
def test_private_aci_rejects_non_fail_closed_topology_condition(
    tmp_path: Path,
    replacement: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    target = (
        '"$sql_pe_state" != "Approved" || '
        if "sql_pe_state" in replacement
        else '"$identity_client_id" != "$DATA_DEPLOY_IDENTITY_CLIENT_ID"'
    )
    script.write_text(
        _PRIVATE_VERIFIER.replace(target, replacement, 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("topology condition" in error for error in errors)


def test_private_aci_rejects_unreachable_payload_queries_hidden_by_exec(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            r'cursor.execute(\"SELECT COUNT_BIG(*) FROM [dbo].[example]\"); sql_count=cursor.fetchone()[0]; ',
            r'exec(\"if 0:\\n cursor.execute(\\\"SELECT COUNT_BIG(*) FROM [dbo].[example]\\\"); sql_count=cursor.fetchone()[0]\"); sql_count=0; ',
        ).replace(
            r'cosmos_count=list(container.query_items(query=\"SELECT VALUE COUNT(1) FROM c\", enable_cross_partition_query=True))[0]; ',
            r'exec(\"if 0:\\n cosmos_count=list(container.query_items(query=\\\"SELECT VALUE COUNT(1) FROM c\\\", enable_cross_partition_query=True))[0]\"); cosmos_count=0; ',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("ACI payload" in error and "unreachable" in error for error in errors)


@pytest.mark.parametrize(
    "replacement",
    (
        "'Approved' || privateLinkServiceConnections[0].privateLinkServiceConnectionState.status",
        "'wrong-subnet' || subnet.id",
        "'wrong-client-id' || clientId",
    ),
)
def test_private_aci_rejects_noncanonical_topology_query(
    tmp_path: Path,
    replacement: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "privateLinkServiceConnections[0].privateLinkServiceConnectionState.status",
            replacement,
            1,
        ) if "Approved" in replacement else _PRIVATE_VERIFIER.replace(
            "subnet.id" if "subnet" in replacement else "clientId",
            replacement,
            1,
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("topology query" in error for error in errors)


def test_private_aci_rejects_constant_true_condition_before_topology(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'vnet_id="$(az network vnet show',
            'if [[ "$DATA_VNET_NAME" == "$DATA_VNET_NAME" ]]; then\n'
            '            exit 1\n'
            '        fi\n'
            '        vnet_id="$(az network vnet show',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("topology condition" in error for error in errors)


@pytest.mark.parametrize(
    "replacement",
    (
        r'cursor.execute(\"SELECT COUNT_BIG(*) FROM [dbo].[example]\") if 0.0 else None; sql_count=0; ',
        r'cosmos_count=list(container.query_items(query=\"SELECT VALUE COUNT(1) FROM c\", enable_cross_partition_query=True))[0] if 0.0 else 0; ',
    ),
)
def test_private_aci_rejects_payload_conditional_count_bypass(
    tmp_path: Path,
    replacement: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    source = (
        r'cursor.execute(\"SELECT COUNT_BIG(*) FROM [dbo].[example]\"); sql_count=cursor.fetchone()[0]; '
        if "cursor.execute" in replacement
        else r'cosmos_count=list(container.query_items(query=\"SELECT VALUE COUNT(1) FROM c\", enable_cross_partition_query=True))[0]; '
    )
    script.write_text(_PRIVATE_VERIFIER.replace(source, replacement), encoding="utf-8")

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("ACI payload" in error and "unreachable" in error for error in errors)


def test_private_aci_rejects_constant_true_condition_before_topology_variant(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'vnet_id="$(az network vnet show',
            'if [[ "always" == "always" ]]; then\n            exit 1\n        fi\n'
            '        vnet_id="$(az network vnet show',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("topology condition" in error for error in errors)


def test_private_aci_rejects_reassigned_private_endpoint_result(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'if [[ "$sql_pe_state" != "Approved" ||',
            'sql_pe_state="$(az network private-endpoint show --name "$COSMOS_PRIVATE_ENDPOINT_NAME" '
            '--query "privateLinkServiceConnections[0].privateLinkServiceConnectionState.status" --output tsv)"\n'
            '        if [[ "$sql_pe_state" != "Approved" ||',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("topology query" in error for error in errors)


def test_private_aci_rejects_az_override_before_network_mode_branch(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'case "${DATA_NETWORK_MODE:?}" in',
            'az() { command az "$@"; }\ncase "${DATA_NETWORK_MODE:?}" in',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("before network-mode case" in error for error in errors)


def test_private_aci_rejects_short_circuited_payload_count_query(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            r'cursor.execute(\"SELECT COUNT_BIG(*) FROM [dbo].[example]\")',
            r'1 or cursor.execute(\"SELECT COUNT_BIG(*) FROM [dbo].[example]\")',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("ACI payload" in error and "straight-line" in error for error in errors)


def test_private_aci_rejects_reversed_private_endpoint_failure_condition(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            '"$sql_pe_state" != "Approved"',
            '"$sql_pe_state" == "Approved"',
            1,
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("topology condition" in error for error in errors)


@pytest.mark.parametrize(
    "payload_mutation",
    (
        'eval("sql_count=0")',
        'eval("cosmos_count=0")',
        'SELECT COUNT_BIG(*) FROM (SELECT 1 WHERE 0) AS empty',
        'SELECT VALUE COUNT(1) FROM c WHERE false',
    ),
)
def test_private_aci_rejects_payload_that_can_fake_count_results(
    tmp_path: Path,
    payload_mutation: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    source = _PRIVATE_VERIFIER
    if payload_mutation.startswith("eval"):
        source = source.replace(
            'print(int(cosmos_count))',
            f'{payload_mutation}; print(int(cosmos_count))',
        )
    elif payload_mutation.startswith("SELECT COUNT_BIG"):
        source = source.replace(
            "SELECT COUNT_BIG(*) FROM [dbo].[example]", payload_mutation
        )
    else:
        source = source.replace(
            "SELECT VALUE COUNT(1) FROM c", payload_mutation
        )
    script.write_text(source, encoding="utf-8")

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("ACI payload" in error and "COUNT" in error for error in errors)


def test_private_aci_rejects_topology_condition_without_direct_exit(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'if [[ "$sql_pe_state" != "Approved" || "$cosmos_pe_state" != "Approved" || "$sql_pe_subnet" != "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" || "$cosmos_pe_subnet" != "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" ]]; then\n'
            '                    exit 1\n'
            '                fi',
            'if [[ "$sql_pe_state" != "Approved" ]]; then\n'
            '                    :\n'
            '                fi\n'
            '                if [[ "$cosmos_pe_state" != "Approved" || "$sql_pe_subnet" != "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" || "$cosmos_pe_subnet" != "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" ]]; then\n'
            '                    exit 1\n'
            '                fi',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("topology condition" in error and "exit 1" in error for error in errors)


@pytest.mark.parametrize("result_name", ("sql_count", "cosmos_count"))
def test_private_aci_rejects_reassigned_payload_count_result(
    tmp_path: Path,
    result_name: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            f"print(int({result_name}))",
            f"{result_name}=0; print(int({result_name}))",
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("COUNT result" in error for error in errors)


@pytest.mark.parametrize(
    ("result_name", "canonical_query"),
    (
        ("aci_delegation", "delegations[?serviceName=='Microsoft.ContainerInstance/containerGroups'] | length(@)"),
        ("aci_nat_id", "natGateway.id"),
        ("sql_dns_match", "[?privateDnsZoneConfigs[?contains(privateDnsZoneId, '/privateDnsZones/$SQL_PRIVATE_DNS_ZONE')]] | length(@)"),
        ("sql_vnet_link_count", "[?contains(virtualNetwork.id, '$vnet_id')] | length(@)"),
    ),
)
def test_private_aci_rejects_literal_first_topology_query(
    tmp_path: Path,
    result_name: str,
    canonical_query: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(canonical_query, f"'1' || {canonical_query}", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("topology query" in error and result_name in error for error in errors)


@pytest.mark.parametrize(
    ("source", "replacement"),
    (
        ('"$sql_pe_subnet" != "$DATA_PRIVATE_ENDPOINT_SUBNET_ID"', '"$sql_pe_subnet" == "$DATA_PRIVATE_ENDPOINT_SUBNET_ID"'),
        ('"$cosmos_pe_subnet" != "$DATA_PRIVATE_ENDPOINT_SUBNET_ID"', '"$cosmos_pe_subnet" == "$DATA_PRIVATE_ENDPOINT_SUBNET_ID"'),
        ('"$aci_delegation" != "1"', '"$aci_delegation" == "1"'),
        ('"${aci_nat_id##*/}" != "$DATA_NAT_GATEWAY_NAME"', '"${aci_nat_id##*/}" == "$DATA_NAT_GATEWAY_NAME"'),
        ('"$sql_dns_match" == "0"', '"$sql_dns_match" != "0"'),
    ),
)
def test_private_aci_rejects_reversed_topology_failure_condition(
    tmp_path: Path,
    source: str,
    replacement: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(_PRIVATE_VERIFIER.replace(source, replacement, 1), encoding="utf-8")

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("topology condition" in error for error in errors)


def test_private_aci_rejects_unexecuted_python_count_string(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            r'cursor.execute(\"SELECT COUNT_BIG(*) FROM [dbo].[example]\"); sql_count=cursor.fetchone()[0]; ',
            r'"cursor.execute(\\\"SELECT COUNT_BIG(*) FROM [dbo].[example]\\\"); sql_count=cursor.fetchone()[0]"; sql_count=0; ',
        ).replace(
            r'cosmos_count=list(container.query_items(query=\"SELECT VALUE COUNT(1) FROM c\", enable_cross_partition_query=True))[0]; ',
            r'"cosmos_count=list(container.query_items(query=\\\"SELECT VALUE COUNT(1) FROM c\\\", enable_cross_partition_query=True))[0]"; cosmos_count=0; ',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("ACI payload" in error and "executable" in error for error in errors)


def test_private_aci_cleanup_rejects_command_prefixed_other_aci_delete(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            '--name "$aci_name" --yes || true\n                        fi',
            '--name "$aci_name" --yes || true; '
            'command az container delete --resource-group "$RESOURCE_GROUP" '
            '--name unrelated-aci --yes\n                        fi',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("cleanup_aci" in error and "Resource Group" in error for error in errors)


def test_private_aci_cleanup_rejects_conditional_resource_group_delete(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            '--name "$aci_name" --yes || true\n                        fi',
            '--name "$aci_name" --yes || true; '
            'if true; then az group delete --name "$RESOURCE_GROUP" --yes; fi\n                        fi',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("cleanup_aci" in error and "Resource Group" in error for error in errors)


def test_private_aci_cleanup_rejects_variable_dispatched_resource_group_delete(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            '--name "$aci_name" --yes || true\n                        fi',
            '--name "$aci_name" --yes || true; '
            'deleter=az; "$deleter" group delete --name "$RESOURCE_GROUP" --yes\n                        fi',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("cleanup_aci" in error and "Resource Group" in error for error in errors)


def test_private_aci_cleanup_trap_must_handle_exit_int_and_term(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "trap cleanup_aci EXIT INT TERM",
            "trap cleanup_aci EXIT",
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("cleanup_aci" in error and "Resource Group" in error for error in errors)


def test_private_uami_client_id_cannot_be_overwritten_before_comparison(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'if [[ -z "$identity_client_id" || "$identity_client_id" != "$DATA_DEPLOY_IDENTITY_CLIENT_ID" ]]; then',
            'identity_client_id="$DATA_DEPLOY_IDENTITY_CLIENT_ID"\n'
            '        if [[ -z "$identity_client_id" || "$identity_client_id" != "$DATA_DEPLOY_IDENTITY_CLIENT_ID" ]]; then',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("UAMI clientId" in error for error in errors)


def test_private_branch_rejects_local_direct_sql_or_cosmos_after_aci(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"',
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"\n'
            '        sqlcmd -G -S "tcp:example.database.windows.net,1433"\n'
            '        python -c "from azure.cosmos import CosmosClient; CosmosClient(\"https://example.invalid\", credential=\"AccountKey=secret\")"',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("local direct SQL" in error for error in errors)
    assert any("local direct Cosmos" in error for error in errors)


def test_private_branch_rejects_shell_concatenated_local_direct_sql(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"',
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"\n'
            '        sql""cmd -G -S "tcp:example.database.windows.net,1433"',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("local direct SQL" in error for error in errors)


def test_private_branch_rejects_command_prefixed_local_direct_sql(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"',
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"\n'
            '        command sqlcmd -G -S "tcp:example.database.windows.net,1433"',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("local direct SQL" in error for error in errors)


def test_private_branch_rejects_local_replay_of_aci_command(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"',
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"\n'
            '        python -c "$aci_command"',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("aci_command" in error and "local" in error for error in errors)


def test_private_branch_rejects_indirect_local_replay_of_aci_command(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"',
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"\n'
            '        payload_slot=aci_command; /bin/bash -c "${!payload_slot}"',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("aci_command" in error and "local" in error for error in errors)


def test_private_branch_rejects_variable_dispatched_local_cosmos_python(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"',
            'aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)"\n'
            '        runtime=python; "$runtime" -c "from azure.cosmos import CosmosClient; '
            'from azure.identity import DefaultAzureCredential; CosmosClient(\"https://example.invalid\", '
            'credential=DefaultAzureCredential())"',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("SDK code" in error for error in errors)


def test_private_aci_rejects_options_hidden_after_inline_comment(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'az container create --resource-group "$RESOURCE_GROUP"',
            'az container create # --resource-group "$RESOURCE_GROUP"',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("--resource-group" in error for error in errors)


@pytest.mark.parametrize("command_group", ("container show", "container logs"))
def test_private_aci_rejects_show_or_logs_for_unrelated_aci(
    tmp_path: Path,
    command_group: str,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    extra = (
        f'unrelated="$(az {command_group} --resource-group "$RESOURCE_GROUP" '
        '--name unrelated-aci)"'
    )
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'if [[ "$aci_wait_failed" != "0" || "$aci_exit_code" != "0" || -z "$aci_logs" ]]; then',
            f"{extra}\n        if [[ \"$aci_wait_failed\" != \"0\" || \"$aci_exit_code\" != \"0\" || -z \"$aci_logs\" ]]; then",
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any(command_group in error and "aci_name" in error for error in errors)


def test_private_branch_ignores_sqlcmd_image_reference_in_comment(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            'aci_name="verify-data-${RANDOM}-${RANDOM}"',
            'aci_name="verify-data-${RANDOM}-${RANDOM}" # SQLCMD_ACI_IMAGE must not be used by the private verifier',
        ),
        encoding="utf-8",
    )

    assert validate_asdw_data_verify_script(
        script, private_capability_required=True
    ) == []


def test_private_branch_ignores_sqlcmd_image_reference_in_aci_payload_comment(
    tmp_path: Path,
) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            "print(int(cosmos_count))'\"",
            "print(int(cosmos_count)) # SQLCMD_ACI_IMAGE documentation only'\"",
        ),
        encoding="utf-8",
    )

    assert validate_asdw_data_verify_script(
        script, private_capability_required=True
    ) == []


def test_private_branch_rejects_sqlcmd_image_used_by_aci_payload(tmp_path: Path) -> None:
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        _PRIVATE_VERIFIER.replace(
            r'client_id=\"$DATA_DEPLOY_IDENTITY_CLIENT_ID\"',
            r'client_id=\"$SQLCMD_ACI_IMAGE\"',
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script, private_capability_required=True)

    assert any("SQLCMD_ACI_IMAGE" in error for error in errors)


@pytest.mark.parametrize(
    ("step_id", "agent", "expected_noun"),
    (
        ("1.2", "Dev-Microservice-Azure-DataTestCoding", "generated"),
        ("1.3", "Dev-Microservice-Azure-DataDeploy", "input"),
    ),
)
def test_runner_reuses_existing_verify_gate_with_private_capability_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    step_id: str,
    agent: str,
    expected_noun: str,
) -> None:
    calls: list[tuple[Path, Path | None, bool, Path | None]] = []
    registration_calls: list[tuple[Path, Path | None]] = []

    def fake_validator(
        path: Path,
        design_doc_path: Path | None = None,
        private_capability_required: bool = False,
        sample_data_path: Path | None = None,
    ) -> list[str]:
        calls.append(
            (path, design_doc_path, private_capability_required, sample_data_path)
        )
        return ["sentinel"]

    def fake_registration_validator(
        path: Path,
        design_doc_path: Path | None = None,
    ) -> list[str]:
        registration_calls.append((path, design_doc_path))
        return []

    sample_data = tmp_path / "src" / "data" / "sample-data.json"
    sample_data.parent.mkdir(parents=True)
    sample_data.write_text('{"entities": {}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_verify_script",
        fake_validator,
    )
    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_registration_script",
        fake_registration_validator,
    )
    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    errors = runner._run_asdw_data_verify_contract_gate(step_id, agent)

    assert calls == [
        (
            tmp_path / "src" / "infra" / "azure" / "verify-data-resources.sh",
            tmp_path / "docs" / "azure" / "azure-services-data.md",
            True,
            sample_data,
        )
    ]
    assert len(errors) == 1
    assert expected_noun in errors[0]
    expected_registration_calls = (
        [
            (
                tmp_path / "src" / "data" / "azure" / "data-registration-script.sh",
                tmp_path / "docs" / "azure" / "azure-services-data.md",
            )
        ]
        if step_id == "1.3"
        else []
    )
    assert registration_calls == expected_registration_calls


def test_runner_omits_missing_optional_sample_data_from_strict_coverage_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Path | None] = []

    def fake_validator(
        path: Path,
        design_doc_path: Path | None = None,
        private_capability_required: bool = False,
        sample_data_path: Path | None = None,
    ) -> list[str]:
        calls.append(sample_data_path)
        return []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_verify_script",
        fake_validator,
    )
    runner = StepRunner(config=SDKConfig(), console=Console(verbose=False, quiet=True))

    assert runner._run_asdw_data_verify_contract_gate(
        "1.2", "Dev-Microservice-Azure-DataTestCoding"
    ) == []
    assert calls == [None]


def test_runner_pre_gate_skips_registration_script_until_data_deploy_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sample_data = tmp_path / "src" / "data" / "sample-data.json"
    sample_data.parent.mkdir(parents=True)
    sample_data.write_text('{"entities": {}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_verify_script",
        lambda *args, **kwargs: [],
    )
    registration_calls: list[Path] = []

    def unexpected_registration_validator(
        path: Path,
        design_doc_path: Path | None = None,
    ) -> list[str]:
        registration_calls.append(path)
        return ["must not run before generation"]

    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_registration_script",
        unexpected_registration_validator,
    )
    runner = StepRunner(config=SDKConfig(), console=Console(verbose=False, quiet=True))

    assert runner._run_asdw_data_verify_contract_gate(
        "1.3", "Dev-Microservice-Azure-DataDeploy", include_registration=False
    ) == []
    assert registration_calls == []
