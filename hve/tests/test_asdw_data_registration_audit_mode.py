"""ASDW-WEB Step 1.3 AuditRecord registration mode contract tests."""
from __future__ import annotations

import json
import sys
import types
from collections import UserDict
from pathlib import Path

import pytest

from hve.artifact_validation import (
    _ASDW_ACL_AUDIT_REGISTRATION_SOURCE,
    _ASDW_SQL_AUDIT_REGISTRATION_SOURCE,
    validate_asdw_data_registration_script,
)


_SQL_MODE = "sql-ledger-digest"
_DIRECT_MODE = "acl-direct"
_CONTRACT = Path(
    ".github/skills/azure-skills/azure-cli-deploy-scripts/references/"
    "asdw-data-verifier-contract.md"
)

_REGISTRATION_LIFECYCLE = r'''#!/usr/bin/env bash
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
aci_wait_failed=0
aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)" || aci_wait_failed=1
aci_exit_code="$(az container show --resource-group "$RESOURCE_GROUP" --name "$aci_name" --query "containers[0].instanceView.currentState.exitCode" --output tsv)"
if [[ "$aci_wait_failed" != "0" || "$aci_exit_code" != "0" || "$aci_logs" != "HVE_AUDIT_REGISTRATION_OK" ]]; then
    exit 1
fi
'''


def _design_document(mode: str) -> str:
    if mode == _SQL_MODE:
        chosen = (
            "Azure SQL Database の append-only ledger table（SVC-12 の監査証拠 SoT）+ "
            "Azure confidential ledger（信頼済み database digest 保管先、条件付き）"
        )
    elif mode == _DIRECT_MODE:
        chosen = "Azure confidential ledger（AuditRecord を直接格納）"
    else:
        chosen = "Azure Blob Storage immutable storage"
    headers = (
        "Entity",
        "Data characteristics（構造/更新頻度/サイズ）",
        "Access patterns（主要クエリ/ホットパス）",
        "Consistency（強/最終/要件根拠）",
        "Chosen Azure service（正式名称）",
        "Partition/Key/Index（要点）",
        "Rationale（3〜6行）",
        "Alternatives（最大2つ）",
        "Evidence（根拠リンク）",
    )
    return "\n".join(
        (
            "# Azure data design",
            "",
            "## 1. エンティティ別ストア選定",
            "",
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            "| AuditRecord | 追記 | ID検索 | 強整合 | "
            + chosen
            + " | auditEventId | 監査 | 代替 | link |",
            "",
        )
    )


def _sql_registration_source() -> str:
    return _ASDW_SQL_AUDIT_REGISTRATION_SOURCE


def _direct_registration_source() -> str:
    return _ASDW_ACL_AUDIT_REGISTRATION_SOURCE


def _registration_script_from_source(mode: str, source: str) -> str:
    source = source.replace('"', r'\"')
    assignment = f'aci_command="python -c \'{source}\'"\n'
    common_guards = (
        ': "${RESOURCE_GROUP:?}"\n'
        ': "${DATA_ACI_SUBNET_ID:?}"\n'
        ': "${DATA_DEPLOY_IDENTITY_ID:?}"\n'
        ': "${DATA_DEPLOY_IDENTITY_CLIENT_ID:?}"\n'
        ': "${DATA_VERIFY_ACI_IMAGE:?}"\n'
        ': "${AUDIT_RECORD_JSON:?}"\n'
    )
    if mode == _SQL_MODE:
        mode_guards = (
            ': "${SQL_HOST:?}"\n'
            ': "${SQL_DB_SVC12:?}"\n'
            ': "${SQL_AUDIT_TABLE:?}"\n'
        )
        mode_environment = (
            ' SQL_HOST="$SQL_HOST" SQL_DB_SVC12="$SQL_DB_SVC12" '
            'SQL_AUDIT_TABLE="$SQL_AUDIT_TABLE"'
        )
    else:
        mode_guards = (
            ': "${CONFIDENTIAL_LEDGER_ENDPOINT:?}"\n'
            ': "${CONFIDENTIAL_LEDGER_COLLECTION:?}"\n'
        )
        mode_environment = (
            ' CONFIDENTIAL_LEDGER_ENDPOINT="$CONFIDENTIAL_LEDGER_ENDPOINT" '
            'CONFIDENTIAL_LEDGER_COLLECTION="$CONFIDENTIAL_LEDGER_COLLECTION"'
        )
    create = (
        'az container create --resource-group "$RESOURCE_GROUP" '
        '--name "$aci_name" --tags hveRegisterRunId="$DATA_REGISTER_RUN_ID"'
    )
    script = _REGISTRATION_LIFECYCLE.replace(
        'aci_name="data-register-$DATA_REGISTER_RUN_ID"\n',
        common_guards + mode_guards + 'aci_name="data-register-$DATA_REGISTER_RUN_ID"\n',
        1,
    )
    audit_block = script.replace(
        create,
        assignment
        + create
        + ' --image "$DATA_VERIFY_ACI_IMAGE"'
        + ' --subnet "$DATA_ACI_SUBNET_ID"'
        + ' --acr-identity "$DATA_DEPLOY_IDENTITY_ID"'
        + ' --assign-identity "$DATA_DEPLOY_IDENTITY_ID"'
        + ' --restart-policy Never --os-type Linux --cpu 1 --memory 1'
        + ' --secure-environment-variables AUDIT_RECORD_JSON="$AUDIT_RECORD_JSON"'
        + ' --environment-variables AZURE_CLIENT_ID="$DATA_DEPLOY_IDENTITY_CLIENT_ID"'
        + mode_environment
        + ' --command-line "$aci_command"',
        1,
    )
    shebang = "#!/usr/bin/env bash\n"
    assert audit_block.startswith(shebang)
    return (
        shebang
        + "# HVE-AUDIT-REGISTRATION-BEGIN\n"
        + audit_block[len(shebang) :]
        + "# HVE-AUDIT-REGISTRATION-END\n"
    )


def _registration_script(mode: str) -> str:
    source = (
        _sql_registration_source()
        if mode == _SQL_MODE
        else _direct_registration_source()
    )
    return _registration_script_from_source(mode, source)


def _write_case(
    tmp_path: Path,
    *,
    script_mode: str,
    design_mode: str,
) -> tuple[Path, Path]:
    script = tmp_path / "data-registration-script.sh"
    script.write_text(_registration_script(script_mode), encoding="utf-8")
    design = tmp_path / "azure-services-data.md"
    design.write_text(_design_document(design_mode), encoding="utf-8")
    return script, design


def test_shared_contract_requires_top_level_audit_marker_boundary() -> None:
    text = _CONTRACT.read_text(encoding="utf-8")

    assert "# HVE-AUDIT-REGISTRATION-BEGIN" in text
    assert "# HVE-AUDIT-REGISTRATION-END" in text
    assert "top-level" in text
    assert "block外" in text and "重複実装しない" in text


def test_shared_contract_matches_canonical_post_marker_log_grammar() -> None:
    text = _CONTRACT.read_text(encoding="utf-8")

    assert "`printf '%s\\n' '<single-quoted literal>'`" in text
    assert "`echo`、別形式の`printf`、redirection" in text


def test_shared_contract_separates_static_and_runtime_registration_guarantees() -> None:
    text = _CONTRACT.read_text(encoding="utf-8")

    for phrase in (
        "静的artifact gateの保証範囲",
        "block外に他11エンティティの全処理が実在することや、再実行時に重複しないことを一般shell解析で推測しない",
        "`AC-1`（verifier GREEN）",
        "`AC-2`（create + registration再実行でエラー・重複なし）",
        "`AC-3`（全対象件数がsample-data期待値と一致）",
        "Runnerのpre-main deterministic gate",
        "post-mainとstep-end",
        "Agentセッション内でwriteが未実行だったことを遡及保証しない",
    ):
        assert phrase in text


def test_shared_contract_requires_registration_aci_completion_evidence() -> None:
    text = _CONTRACT.read_text(encoding="utf-8")

    for requirement in (
        "timeout 600 az container logs",
        "currentState.exitCode",
        "HVE_AUDIT_REGISTRATION_OK",
        "Run containerized tasks with restart policies",
        "Azure Container Instances states",
    ):
        assert requirement in text


def test_shared_contract_requires_idempotent_audit_registration_grammar() -> None:
    text = _CONTRACT.read_text(encoding="utf-8")

    for phrase in (
        "同一`auditEventId` + 同一canonical payloadの再実行はno-op成功",
        "同一`auditEventId` + 異なるcanonical payloadはfail-closed",
        "同一writerによる逐次再実行",
        "同時並行実行の冪等性を主張しない",
        "WITH (UPDLOCK, HOLDLOCK)",
        "list_ledger_entries",
        "未登録時だけappend",
    ):
        assert phrase in text


def _install_fake_sql_module(monkeypatch, state: dict) -> None:
    module = types.ModuleType("mssql_python")

    class Cursor:
        def __init__(self, connection) -> None:
            self.connection = connection
            self.current = (0, 0)

        def execute(self, query, parameters) -> None:
            assert "WITH (UPDLOCK, HOLDLOCK)" in query
            assert "COUNT_BIG(*)" in query
            audit_id, insert_id, payload, compare_payload, read_id = parameters
            assert audit_id == insert_id == read_id
            assert payload == compare_payload
            rows = state.setdefault("rows", [])
            effective_rows = rows + self.connection.pending
            if not any(row_id == audit_id for row_id, _ in effective_rows):
                self.connection.pending.append((audit_id, payload))
                effective_rows = rows + self.connection.pending
            matches = [
                stored_payload
                for row_id, stored_payload in effective_rows
                if row_id == read_id
            ]
            self.current = (
                len(matches),
                sum(stored_payload == compare_payload for stored_payload in matches),
            )
            state["execute_count"] = state.get("execute_count", 0) + 1

        def fetchone(self):
            return self.current

        def close(self) -> None:
            state["cursor_close_count"] = state.get("cursor_close_count", 0) + 1
            if state.get("cursor_close_raises"):
                raise RuntimeError("cursor close failed")

    class Connection:
        def __init__(self) -> None:
            self.pending: list[tuple[str, str]] = []
            self.cursor_instance = Cursor(self)

        def cursor(self):
            return self.cursor_instance

        def commit(self) -> None:
            state["commit_count"] = state.get("commit_count", 0) + 1
            if state.get("commit_raises"):
                raise RuntimeError("commit failed")
            state.setdefault("rows", []).extend(self.pending)
            self.pending.clear()

        def close(self) -> None:
            state["connection_close_count"] = state.get(
                "connection_close_count", 0
            ) + 1
            self.pending.clear()
            if state.get("connection_close_raises"):
                raise RuntimeError("connection close failed")

    def connect(_connection_string):
        return Connection()

    module.__dict__["connect"] = connect
    monkeypatch.setitem(sys.modules, "mssql_python", module)


def _install_fake_acl_modules(monkeypatch, state: dict) -> None:
    azure = types.ModuleType("azure")
    confidentialledger = types.ModuleType("azure.confidentialledger")
    identity = types.ModuleType("azure.identity")

    class Credential:
        def __init__(self, *, managed_identity_client_id) -> None:
            assert managed_identity_client_id == "$DATA_DEPLOY_IDENTITY_CLIENT_ID"

        def close(self) -> None:
            state["credential_close_count"] = state.get(
                "credential_close_count", 0
            ) + 1
            if state.get("credential_close_raises"):
                raise RuntimeError("credential close failed")

    class Poller:
        def __init__(self, entry) -> None:
            self.entry = entry

        def result(self):
            state.setdefault("entries", []).append(dict(self.entry))
            state["append_count"] = state.get("append_count", 0) + 1
            return {"transactionId": str(state["append_count"])}

    class Client:
        def __init__(self, *, endpoint, credential, ledger_certificate_path) -> None:
            assert endpoint == "https://ledger.example.invalid"
            assert credential is not None
            assert not Path(ledger_certificate_path).exists()
            state.setdefault("certificate_paths", []).append(
                ledger_certificate_path
            )

        def list_ledger_entries(self, *, collection_id):
            assert collection_id == "audit-records"
            state["list_count"] = state.get("list_count", 0) + 1

            class PagedEntries:
                def __iter__(self):
                    for entry in state.setdefault("entries", []):
                        state["yield_count"] = state.get("yield_count", 0) + 1
                        yield entry

            return PagedEntries()

        def begin_create_ledger_entry(self, entry, *, collection_id):
            assert collection_id == "audit-records"
            return Poller(entry)

        def close(self) -> None:
            state["client_close_count"] = state.get("client_close_count", 0) + 1
            if state.get("client_close_raises"):
                raise RuntimeError("client close failed")

    confidentialledger.__dict__["ConfidentialLedgerClient"] = Client
    identity.__dict__["DefaultAzureCredential"] = Credential
    azure.__dict__["confidentialledger"] = confidentialledger
    azure.__dict__["identity"] = identity
    monkeypatch.setitem(sys.modules, "azure", azure)
    monkeypatch.setitem(sys.modules, "azure.confidentialledger", confidentialledger)
    monkeypatch.setitem(sys.modules, "azure.identity", identity)


@pytest.mark.parametrize("mode", (_SQL_MODE, _DIRECT_MODE))
def test_idempotent_registration_runtime_is_noop_on_same_payload(
    monkeypatch,
    mode: str,
) -> None:
    state: dict = {}
    audit = {"auditEventId": "audit-001", "action": "created"}
    monkeypatch.setenv("AUDIT_RECORD_JSON", json.dumps(audit))
    if mode == _SQL_MODE:
        _install_fake_sql_module(monkeypatch, state)
        monkeypatch.setenv("SQL_AUDIT_TABLE", "audit_records")
        source = _sql_registration_source()
    else:
        _install_fake_acl_modules(monkeypatch, state)
        monkeypatch.setenv(
            "CONFIDENTIAL_LEDGER_ENDPOINT",
            "https://ledger.example.invalid",
        )
        monkeypatch.setenv("CONFIDENTIAL_LEDGER_COLLECTION", "audit-records")
        source = _direct_registration_source()

    exec(compile(source, "<registration>", "exec"), {})
    exec(compile(source, "<registration>", "exec"), {})

    if mode == _SQL_MODE:
        assert state["rows"] == [
            (
                "audit-001",
                json.dumps(
                    audit,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        ]
        assert state["execute_count"] == 2
        assert state["commit_count"] == 2
        assert state["cursor_close_count"] == 2
        assert state["connection_close_count"] == 2
    else:
        assert len(state["entries"]) == 1
        assert state["append_count"] == 1
        assert state["list_count"] == 2
        assert state["client_close_count"] == 2
        assert state["credential_close_count"] == 2
        assert all(
            not Path(path).exists()
            for path in state["certificate_paths"]
        )


@pytest.mark.parametrize("mode", (_SQL_MODE, _DIRECT_MODE))
def test_idempotent_registration_runtime_rejects_same_id_different_payload(
    monkeypatch,
    mode: str,
) -> None:
    state: dict = {}
    first = {"auditEventId": "audit-001", "action": "created"}
    second = {"auditEventId": "audit-001", "action": "changed"}
    if mode == _SQL_MODE:
        _install_fake_sql_module(monkeypatch, state)
        monkeypatch.setenv("SQL_AUDIT_TABLE", "audit_records")
        source = _sql_registration_source()
    else:
        _install_fake_acl_modules(monkeypatch, state)
        monkeypatch.setenv(
            "CONFIDENTIAL_LEDGER_ENDPOINT",
            "https://ledger.example.invalid",
        )
        monkeypatch.setenv("CONFIDENTIAL_LEDGER_COLLECTION", "audit-records")
        source = _direct_registration_source()
    monkeypatch.setenv("AUDIT_RECORD_JSON", json.dumps(first))
    exec(compile(source, "<registration>", "exec"), {})
    monkeypatch.setenv("AUDIT_RECORD_JSON", json.dumps(second))

    with pytest.raises(StopIteration):
        exec(compile(source, "<registration>", "exec"), {})

    if mode == _SQL_MODE:
        assert state["commit_count"] == 1
        assert len(state["rows"]) == 1
        assert state["cursor_close_count"] == 2
        assert state["connection_close_count"] == 2
    else:
        assert len(state["entries"]) == 1
        assert state["append_count"] == 1
        assert state["list_count"] == 2
        assert state["client_close_count"] == 2
        assert state["credential_close_count"] == 2


@pytest.mark.parametrize("mode", (_SQL_MODE, _DIRECT_MODE))
def test_registration_rejects_non_normalized_audit_id(
    monkeypatch,
    mode: str,
) -> None:
    state: dict = {}
    monkeypatch.setenv(
        "AUDIT_RECORD_JSON",
        json.dumps({"auditEventId": " audit-001 ", "action": "created"}),
    )
    if mode == _SQL_MODE:
        _install_fake_sql_module(monkeypatch, state)
        monkeypatch.setenv("SQL_AUDIT_TABLE", "audit_records")
        source = _sql_registration_source()
    else:
        _install_fake_acl_modules(monkeypatch, state)
        monkeypatch.setenv(
            "CONFIDENTIAL_LEDGER_ENDPOINT",
            "https://ledger.example.invalid",
        )
        monkeypatch.setenv("CONFIDENTIAL_LEDGER_COLLECTION", "audit-records")
        source = _direct_registration_source()

    with pytest.raises(StopIteration):
        exec(compile(source, "<registration>", "exec"), {})

    assert state.get("rows", []) == []
    assert state.get("entries", []) == []


@pytest.mark.parametrize("mode", (_SQL_MODE, _DIRECT_MODE))
def test_registration_canonicalizes_json_key_order(
    monkeypatch,
    mode: str,
) -> None:
    state: dict = {}
    first = {"auditEventId": "audit-001", "action": "created"}
    second = {"action": "created", "auditEventId": "audit-001"}
    if mode == _SQL_MODE:
        _install_fake_sql_module(monkeypatch, state)
        monkeypatch.setenv("SQL_AUDIT_TABLE", "audit_records")
        source = _sql_registration_source()
    else:
        _install_fake_acl_modules(monkeypatch, state)
        monkeypatch.setenv(
            "CONFIDENTIAL_LEDGER_ENDPOINT",
            "https://ledger.example.invalid",
        )
        monkeypatch.setenv("CONFIDENTIAL_LEDGER_COLLECTION", "audit-records")
        source = _direct_registration_source()
    monkeypatch.setenv("AUDIT_RECORD_JSON", json.dumps(first))
    exec(compile(source, "<registration>", "exec"), {})
    monkeypatch.setenv("AUDIT_RECORD_JSON", json.dumps(second))
    exec(compile(source, "<registration>", "exec"), {})

    assert len(state.get("rows", state.get("entries", []))) == 1


@pytest.mark.parametrize("mode", (_SQL_MODE, _DIRECT_MODE))
def test_registration_preserves_json_types_in_payload_equality(
    monkeypatch,
    mode: str,
) -> None:
    state: dict = {}
    if mode == _SQL_MODE:
        _install_fake_sql_module(monkeypatch, state)
        monkeypatch.setenv("SQL_AUDIT_TABLE", "audit_records")
        source = _sql_registration_source()
    else:
        _install_fake_acl_modules(monkeypatch, state)
        monkeypatch.setenv(
            "CONFIDENTIAL_LEDGER_ENDPOINT",
            "https://ledger.example.invalid",
        )
        monkeypatch.setenv("CONFIDENTIAL_LEDGER_COLLECTION", "audit-records")
        source = _direct_registration_source()
    monkeypatch.setenv(
        "AUDIT_RECORD_JSON",
        json.dumps({"auditEventId": "audit-001", "value": True}),
    )
    exec(compile(source, "<registration>", "exec"), {})
    monkeypatch.setenv(
        "AUDIT_RECORD_JSON",
        json.dumps({"auditEventId": "audit-001", "value": 1}),
    )

    with pytest.raises(StopIteration):
        exec(compile(source, "<registration>", "exec"), {})


def test_sql_registration_rejects_existing_duplicate_rows(monkeypatch) -> None:
    payload = json.dumps(
        {"auditEventId": "audit-001", "action": "created"},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    state = {"rows": [("audit-001", payload), ("audit-001", payload)]}
    _install_fake_sql_module(monkeypatch, state)
    monkeypatch.setenv("SQL_AUDIT_TABLE", "audit_records")
    monkeypatch.setenv("AUDIT_RECORD_JSON", payload)

    with pytest.raises(StopIteration):
        exec(compile(_sql_registration_source(), "<registration>", "exec"), {})

    assert state.get("commit_count", 0) == 0
    assert len(state["rows"]) == 2


@pytest.mark.parametrize(
    "bad_entry",
    (
        {"other": "missing contents"},
        {"contents": 1},
        {"contents": "[]"},
        {"contents": "not-json"},
    ),
)
def test_acl_registration_fails_closed_for_invalid_collection_entry(
    monkeypatch,
    bad_entry,
) -> None:
    state = {"entries": [bad_entry]}
    _install_fake_acl_modules(monkeypatch, state)
    monkeypatch.setenv(
        "CONFIDENTIAL_LEDGER_ENDPOINT",
        "https://ledger.example.invalid",
    )
    monkeypatch.setenv("CONFIDENTIAL_LEDGER_COLLECTION", "audit-records")
    monkeypatch.setenv(
        "AUDIT_RECORD_JSON",
        json.dumps({"auditEventId": "audit-001", "action": "created"}),
    )

    with pytest.raises((StopIteration, TypeError, json.JSONDecodeError)):
        exec(compile(_direct_registration_source(), "<registration>", "exec"), {})

    assert state.get("append_count", 0) == 0


def test_acl_registration_accepts_mapping_entry_from_paged_sdk(monkeypatch) -> None:
    state = {
        "entries": [
            UserDict(
                {
                    "contents": json.dumps(
                        {"auditEventId": "other-001"},
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                }
            )
        ]
    }
    _install_fake_acl_modules(monkeypatch, state)
    monkeypatch.setenv(
        "CONFIDENTIAL_LEDGER_ENDPOINT",
        "https://ledger.example.invalid",
    )
    monkeypatch.setenv("CONFIDENTIAL_LEDGER_COLLECTION", "audit-records")
    monkeypatch.setenv(
        "AUDIT_RECORD_JSON",
        json.dumps({"auditEventId": "audit-001", "action": "created"}),
    )

    exec(compile(_direct_registration_source(), "<registration>", "exec"), {})

    assert state["append_count"] == 1
    assert state["yield_count"] == 1


def test_acl_registration_bounds_collection_listing(monkeypatch) -> None:
    state = {
        "entries": [
            {"contents": json.dumps({"auditEventId": f"other-{index}"})}
            for index in range(1001)
        ]
    }
    _install_fake_acl_modules(monkeypatch, state)
    monkeypatch.setenv(
        "CONFIDENTIAL_LEDGER_ENDPOINT",
        "https://ledger.example.invalid",
    )
    monkeypatch.setenv("CONFIDENTIAL_LEDGER_COLLECTION", "audit-records")
    monkeypatch.setenv(
        "AUDIT_RECORD_JSON",
        json.dumps({"auditEventId": "audit-001", "action": "created"}),
    )

    with pytest.raises(StopIteration):
        exec(compile(_direct_registration_source(), "<registration>", "exec"), {})

    assert state["yield_count"] == 1001
    assert state.get("append_count", 0) == 0


def test_sql_registration_rolls_back_when_commit_fails(monkeypatch) -> None:
    state = {"commit_raises": True}
    _install_fake_sql_module(monkeypatch, state)
    monkeypatch.setenv("SQL_AUDIT_TABLE", "audit_records")
    monkeypatch.setenv(
        "AUDIT_RECORD_JSON",
        json.dumps({"auditEventId": "audit-001", "action": "created"}),
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        exec(compile(_sql_registration_source(), "<registration>", "exec"), {})

    assert state.get("rows", []) == []
    assert state["cursor_close_count"] == 1
    assert state["connection_close_count"] == 1


@pytest.mark.parametrize("mode", (_SQL_MODE, _DIRECT_MODE))
def test_registration_cleanup_continues_after_one_close_failure(
    monkeypatch,
    mode: str,
) -> None:
    state: dict = {}
    monkeypatch.setenv(
        "AUDIT_RECORD_JSON",
        json.dumps({"auditEventId": "audit-001", "action": "created"}),
    )
    if mode == _SQL_MODE:
        state["cursor_close_raises"] = True
        _install_fake_sql_module(monkeypatch, state)
        monkeypatch.setenv("SQL_AUDIT_TABLE", "audit_records")
        source = _sql_registration_source()
    else:
        state["client_close_raises"] = True
        _install_fake_acl_modules(monkeypatch, state)
        monkeypatch.setenv(
            "CONFIDENTIAL_LEDGER_ENDPOINT",
            "https://ledger.example.invalid",
        )
        monkeypatch.setenv("CONFIDENTIAL_LEDGER_COLLECTION", "audit-records")
        source = _direct_registration_source()

    with pytest.raises(RuntimeError, match="close failed"):
        exec(compile(source, "<registration>", "exec"), {})

    if mode == _SQL_MODE:
        assert state["cursor_close_count"] == 1
        assert state["connection_close_count"] == 1
    else:
        assert state["client_close_count"] == 1
        assert state["credential_close_count"] == 1
        assert all(
            not Path(path).exists()
            for path in state["certificate_paths"]
        )


@pytest.mark.parametrize("mode", (_SQL_MODE, _DIRECT_MODE))
def test_registration_validator_accepts_script_matching_design_mode(
    tmp_path: Path,
    mode: str,
) -> None:
    script, design = _write_case(
        tmp_path,
        script_mode=mode,
        design_mode=mode,
    )

    assert validate_asdw_data_registration_script(
        script,
        design_doc_path=design,
    ) == []
    text = script.read_text(encoding="utf-8")
    assert "DATA_VERIFY_ACI_IMAGE" in text
    assert "DATA_REGISTER_ACI_IMAGE" not in text
    assert '--subnet "$DATA_ACI_SUBNET_ID"' in text


def test_complete_registration_requires_audit_block_markers(
    tmp_path: Path,
) -> None:
    text = _registration_script(_SQL_MODE)
    text = text.replace("# HVE-AUDIT-REGISTRATION-BEGIN\n", "", 1)
    text = text.replace("# HVE-AUDIT-REGISTRATION-END\n", "", 1)
    script = tmp_path / "data-registration-script.sh"
    script.write_text(text, encoding="utf-8")
    design = tmp_path / "azure-services-data.md"
    design.write_text(_design_document(_SQL_MODE), encoding="utf-8")

    errors = validate_asdw_data_registration_script(script, design_doc_path=design)

    assert any("HVE-AUDIT-REGISTRATION markers" in error for error in errors), errors


def test_registration_allows_audit_words_in_outside_comments_and_logs(
    tmp_path: Path,
) -> None:
    outside = (
        "# AuditRecord SQL_AUDIT_TABLE begin_create_ledger_entry\n"
        "printf '%s\\n' '[INFO] AuditRecord registration completed'\n"
    )
    script = tmp_path / "data-registration-script.sh"
    script.write_text(_registration_script(_SQL_MODE) + outside, encoding="utf-8")
    design = tmp_path / "azure-services-data.md"
    design.write_text(_design_document(_SQL_MODE), encoding="utf-8")

    assert validate_asdw_data_registration_script(
        script,
        design_doc_path=design,
    ) == []


@pytest.mark.parametrize(
    "outside_replay",
    (
        'bash "$0"\n',
        '"$0"\n',
        'exec "$0"\n',
        'source "${BASH_SOURCE[0]}"\n',
        '. "${BASH_SOURCE[0]}"\n',
        'registration="$0"\nbash "$registration"\n',
        'bash src/data/azure/data-registration-script.sh\n',
        'exec ./src/data/azure/data-registration-script.sh\n',
        'registration=src/data/azure/data-registration-script.sh\n'
        'bash "$registration"\n',
        'bash "${0:0}"\n',
        'bash "${BASH_SOURCE[0]:0}"\n',
        'registration=src/data/azure/data-registration-"script".sh\n'
        'bash "$registration"\n',
        'bash src/data/azure/data-registration-?cript.sh\n',
        'python3 -c \'import subprocess; subprocess.run(["bash", "wrapper"])\'\n',
        'node -e \'require("child_process").execFile("wrapper")\'\n',
        'if [[ -z ${REPLAYED:-} ]]; then DATA_REGISTER_RUN_ID=other; '
        'REPLAYED=1 bash "$PWD/src/data/azure/data-registration-script.sh"; fi\n',
        '(sleep 1; "$PWD/src/data/azure/data-registration-script.sh") &\n',
        'cleanup_aci\n"$PWD/src/data/azure/data-registration-script.sh"\n',
        'nohup "$PWD/src/data/azure/data-registration-script.sh" &\n',
        'python3 -c \'import os; os.system("wrapper")\'\n',
        'pwsh -Command \'Start-Process wrapper\'\n',
        'cmd /d /c start wrapper\n',
    ),
)
def test_registration_rejects_self_replay_outside_audit_block(
    tmp_path: Path,
    outside_replay: str,
) -> None:
    script = tmp_path / "data-registration-script.sh"
    script.write_text(
        _registration_script(_SQL_MODE) + outside_replay,
        encoding="utf-8",
    )
    design = tmp_path / "azure-services-data.md"
    design.write_text(_design_document(_SQL_MODE), encoding="utf-8")

    errors = validate_asdw_data_registration_script(
        script,
        design_doc_path=design,
    )

    assert any(
        "must not replay" in error
        or "must not execute any statement" in error
        for error in errors
    ), errors


@pytest.mark.parametrize(
    "literal_log",
    (
        'printf \'%s\\n\' \'bash "$0"\'\n',
        "printf '%s\\n' 'data-registration-script.sh'\n",
        "printf '%s\\n' 'source ${BASH_SOURCE[0]}'\n",
    ),
)
def test_registration_allows_literal_self_reference_log_outside_audit_block(
    tmp_path: Path,
    literal_log: str,
) -> None:
    script = tmp_path / "data-registration-script.sh"
    script.write_text(
        _registration_script(_SQL_MODE) + literal_log,
        encoding="utf-8",
    )
    design = tmp_path / "azure-services-data.md"
    design.write_text(_design_document(_SQL_MODE), encoding="utf-8")

    assert validate_asdw_data_registration_script(
        script,
        design_doc_path=design,
    ) == []


@pytest.mark.parametrize(
    "active_printf",
    (
        "printf '-v' 'x' '%s' value\n",
        "printf \\-v x '%s' value\n",
        "printf '-f' descriptor '%s' value\n",
        "printf '%s\\n' 'safe' >&2\n",
        "echo 'safe'\n",
        'print("safe")\n',
    ),
)
def test_registration_rejects_noncanonical_log_statement_outside_audit_block(
    tmp_path: Path,
    active_printf: str,
) -> None:
    script = tmp_path / "data-registration-script.sh"
    script.write_text(
        _registration_script(_SQL_MODE) + active_printf,
        encoding="utf-8",
    )
    design = tmp_path / "azure-services-data.md"
    design.write_text(_design_document(_SQL_MODE), encoding="utf-8")

    errors = validate_asdw_data_registration_script(
        script,
        design_doc_path=design,
    )

    assert any("must not execute any statement" in error for error in errors), errors


def test_registration_rejects_dynamic_sql_write_target_outside_audit_block(
    tmp_path: Path,
) -> None:
    outside = 'python3 -c \'cursor.execute(f"INSERT INTO dbo.{table} VALUES (1)")\'\n'
    script = tmp_path / "data-registration-script.sh"
    script.write_text(_registration_script(_SQL_MODE) + outside, encoding="utf-8")
    design = tmp_path / "azure-services-data.md"
    design.write_text(_design_document(_SQL_MODE), encoding="utf-8")

    errors = validate_asdw_data_registration_script(script, design_doc_path=design)

    assert any("dynamic or unresolved SQL write target" in error for error in errors), errors


def test_registration_rejects_delete_alias_unknown_table_outside_audit_block(
    tmp_path: Path,
) -> None:
    outside = 'python3 -c \'cursor.execute("DELETE t FROM dbo.unknown AS t WHERE t.id = 1")\'\n'
    script = tmp_path / "data-registration-script.sh"
    script.write_text(_registration_script(_SQL_MODE) + outside, encoding="utf-8")
    design = tmp_path / "azure-services-data.md"
    design.write_text(_design_document(_SQL_MODE), encoding="utf-8")

    errors = validate_asdw_data_registration_script(script, design_doc_path=design)

    assert any("ten known non-Audit tables" in error for error in errors), errors


def test_registration_rejects_dynamic_sql_statement_outside_audit_block(
    tmp_path: Path,
) -> None:
    outside = (
        "python3 -c 'verb = \"INSERT\"; query = verb + \" INTO dbo.unknown "
        "VALUES (1)\"; cursor.execute(query)'\n"
    )
    script = tmp_path / "data-registration-script.sh"
    script.write_text(_registration_script(_SQL_MODE) + outside, encoding="utf-8")
    design = tmp_path / "azure-services-data.md"
    design.write_text(_design_document(_SQL_MODE), encoding="utf-8")

    errors = validate_asdw_data_registration_script(script, design_doc_path=design)

    assert any("dynamically constructed SQL" in error for error in errors), errors


@pytest.mark.parametrize(
    ("script_mode", "design_mode", "expected"),
    (
        (_DIRECT_MODE, _SQL_MODE, "SQL AuditRecord registration"),
        (_SQL_MODE, _DIRECT_MODE, "ACL-direct AuditRecord registration"),
    ),
)
def test_registration_validator_rejects_script_for_other_design_mode(
    tmp_path: Path,
    script_mode: str,
    design_mode: str,
    expected: str,
) -> None:
    script, design = _write_case(
        tmp_path,
        script_mode=script_mode,
        design_mode=design_mode,
    )

    errors = validate_asdw_data_registration_script(
        script,
        design_doc_path=design,
    )

    assert any(expected in error for error in errors), errors


def test_registration_validator_rejects_unknown_design_without_direct_fallback(
    tmp_path: Path,
) -> None:
    script, design = _write_case(
        tmp_path,
        script_mode=_DIRECT_MODE,
        design_mode="unknown",
    )

    errors = validate_asdw_data_registration_script(
        script,
        design_doc_path=design,
    )

    assert any("unknown storage mode" in error for error in errors), errors
    assert not any("ACL-direct AuditRecord registration" in error for error in errors), errors


def test_registration_validator_preserves_lifecycle_only_compatibility_without_design(
    tmp_path: Path,
) -> None:
    script = tmp_path / "data-registration-script.sh"
    script.write_text(_REGISTRATION_LIFECYCLE, encoding="utf-8")

    assert validate_asdw_data_registration_script(script) == []


def test_sql_mode_rejects_acl_application_payload_write_mixed_in(
    tmp_path: Path,
) -> None:
    script, design = _write_case(
        tmp_path,
        script_mode=_SQL_MODE,
        design_mode=_SQL_MODE,
    )
    text = script.read_text(encoding="utf-8")
    mixed = (
        '    ledger_client.begin_create_ledger_entry('
        '{\\"contents\\": payload}, '
        'collection_id=os.environ[\\"CONFIDENTIAL_LEDGER_COLLECTION\\"])\n'
    )
    script.write_text(
        text.replace("finally:\n", mixed + "finally:\n", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_registration_script(
        script,
        design_doc_path=design,
    )

    assert any("must not write AuditRecord to Azure confidential ledger" in error for error in errors), errors


def test_direct_mode_rejects_svc12_audit_sql_write_mixed_in(
    tmp_path: Path,
) -> None:
    script, design = _write_case(
        tmp_path,
        script_mode=_DIRECT_MODE,
        design_mode=_DIRECT_MODE,
    )
    text = script.read_text(encoding="utf-8")
    mixed = (
        '    svc12_connection = connect(\\"Server=$SQL_HOST;Database=$SQL_DB_SVC12;'
        'UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;Authentication=ActiveDirectoryMSI;'
        'Encrypt=yes;TrustServerCertificate=no\\")\n'
        '    audit_table = os.environ[\\"SQL_AUDIT_TABLE\\"]\n'
        '    svc12_cursor.execute(f\\"INSERT INTO [dbo].[{audit_table}] (id) VALUES (?)\\", (audit[\\"auditEventId\\"],))\n'
    )
    script.write_text(
        text.replace("finally:\n", mixed + "finally:\n", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_registration_script(
        script,
        design_doc_path=design,
    )

    assert any("must not require SVC-12 Audit SQL" in error for error in errors), errors


def test_direct_mode_does_not_require_svc12_or_sql_audit_table(
    tmp_path: Path,
) -> None:
    script, design = _write_case(
        tmp_path,
        script_mode=_DIRECT_MODE,
        design_mode=_DIRECT_MODE,
    )
    text = script.read_text(encoding="utf-8")
    assert "SQL_DB_SVC12" not in text
    assert "SQL_AUDIT_TABLE" not in text

    assert validate_asdw_data_registration_script(
        script,
        design_doc_path=design,
    ) == []


def test_direct_mode_requires_fresh_ledger_tls_certificate_path(
    tmp_path: Path,
) -> None:
    source = _direct_registration_source().replace(
        ", ledger_certificate_path=ledger_certificate_path",
        "",
        1,
    )
    script = tmp_path / "data-registration-script.sh"
    script.write_text(
        _registration_script_from_source(_DIRECT_MODE, source),
        encoding="utf-8",
    )
    design = tmp_path / "azure-services-data.md"
    design.write_text(_design_document(_DIRECT_MODE), encoding="utf-8")

    errors = validate_asdw_data_registration_script(
        script,
        design_doc_path=design,
    )

    assert any("ledger TLS certificate" in error for error in errors), errors


@pytest.mark.parametrize("mode", (_SQL_MODE, _DIRECT_MODE))
def test_registration_mode_inventory_ignores_opposite_mode_comments(
    tmp_path: Path,
    mode: str,
) -> None:
    script, design = _write_case(
        tmp_path,
        script_mode=mode,
        design_mode=mode,
    )
    marker = (
        "# ConfidentialLedgerClient begin_create_ledger_entry CONFIDENTIAL_LEDGER_COLLECTION\n"
        if mode == _SQL_MODE
        else "# SQL_DB_SVC12 SQL_AUDIT_TABLE INSERT INTO AuditRecord\n"
    )
    text = script.read_text(encoding="utf-8")
    text = text.replace(
        "# HVE-AUDIT-REGISTRATION-BEGIN\n",
        "# HVE-AUDIT-REGISTRATION-BEGIN\n" + marker,
        1,
    )
    script.write_text(text, encoding="utf-8")

    assert validate_asdw_data_registration_script(
        script,
        design_doc_path=design,
    ) == []
