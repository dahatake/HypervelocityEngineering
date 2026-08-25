"""ASDW Step 1.3 production producer generator contract tests."""
from __future__ import annotations

import importlib
import builtins
import dis
import io
import inspect
import os
from pathlib import Path
from queue import Empty, Queue
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from threading import Thread
from typing import BinaryIO, cast

import pytest

from hve.artifact_validation import (
    validate_asdw_data_create_scripts,
    validate_asdw_data_registration_script,
)


_PRODUCER_PATHS = (
    "src/infra/azure/create-azure-data-resources-prep.sh",
    "src/infra/azure/create-azure-data-resources.sh",
    "src/data/azure/data-registration-script.sh",
)
_EXPECTED_PATHS = set(_PRODUCER_PATHS)
_SAMPLE_DATA = """{
  "entities": {
        "Member": [{"memberId": "member-1"}],
        "ConsentRecord": [{"consentRecordId": "consent-1"}],
        "DataRightsRequest": [{"requestId": "request-1"}],
        "LoyaltyAccount": [{"loyaltyAccountId": "loyalty-1"}],
        "PointTransaction": [{"pointTransactionId": "transaction-1"}],
        "Reward": [{"rewardId": "reward-1"}],
        "RewardExchange": [{"rewardExchangeId": "exchange-1"}],
        "PaidMembershipContract": [{"contractId": "contract-1"}],
        "SupportCase": [{"supportCaseId": "case-1"}],
        "CaseResolution": [{"resolutionId": "resolution-1"}],
        "VocRecord": [{"sourceRecordId": "voc-1"}],
        "AuditRecord": [{"auditEventId": "audit-1"}]
  }
}
"""


def _design_document(chosen_service: str) -> str:
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
    non_audit_rows = [
        ("Member", "Azure SQL Database"),
        ("ConsentRecord", "Azure SQL Database"),
        ("DataRightsRequest", "Azure SQL Database"),
        ("LoyaltyAccount", "Azure SQL Database"),
        ("PointTransaction", "Azure SQL Database"),
        ("Reward", "Azure SQL Database"),
        ("RewardExchange", "Azure SQL Database"),
        ("PaidMembershipContract", "Azure SQL Database"),
        ("SupportCase", "Azure SQL Database"),
        ("CaseResolution", "Azure SQL Database"),
        ("VocRecord", "Azure Cosmos DB for NoSQL"),
    ]
    rows = [
        f"| {entity} | structured | lookup | strong | {service} | id | "
        "selected | alternative | evidence |"
        for entity, service in non_audit_rows
    ]
    rows.append(
        "| AuditRecord | append-only | lookup | strong | "
        + chosen_service
        + " | auditEventId | audit | alternative | evidence |"
    )
    return "\n".join(
        [
            "# Azure data design",
            "",
            "## 1. エンティティ別ストア選定",
            "",
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *rows,
            "",
        ]
    )


_SQL_DESIGN = _design_document(
    "Azure SQL Database の append-only ledger table（SVC-12 の監査証拠 SoT）+ "
    "Azure confidential ledger（信頼済み database digest 保管先、条件付き）"
)
_ACL_DESIGN = _design_document(
    "Azure confidential ledger（AuditRecord を直接格納）"
)


def _generator_module():
    return importlib.import_module("hve.asdw_data_script_generator")


def _render(design_text: str = _SQL_DESIGN, sample_text: str = _SAMPLE_DATA):
    return _generator_module().render_asdw_data_producers(
        design_text=design_text,
        sample_data_text=sample_text,
    )


def _write_repo_file(repo_root: Path, relative_path: str, payload: bytes) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _prepare_promotion_repo(
    repo_root: Path,
    producer_bytes: dict[str, bytes] | None,
    *,
    crlf_inputs: bool = False,
) -> None:
    design = _SQL_DESIGN.encode("utf-8")
    sample = _SAMPLE_DATA.encode("utf-8")
    if crlf_inputs:
        design = design.replace(b"\n", b"\r\n")
        sample = sample.replace(b"\n", b"\r\n")
    _write_repo_file(repo_root, "docs/azure/azure-services-data.md", design)
    _write_repo_file(repo_root, "src/data/sample-data.json", sample)
    if producer_bytes is not None:
        for relative_path in _PRODUCER_PATHS:
            _write_repo_file(repo_root, relative_path, producer_bytes[relative_path])


def _producer_snapshot(repo_root: Path) -> dict[str, bytes]:
    return {
        relative_path: (repo_root / relative_path).read_bytes()
        for relative_path in _PRODUCER_PATHS
        if (repo_root / relative_path).is_file()
    }


def _producer_mtimes(repo_root: Path) -> dict[str, int]:
    return {
        relative_path: (repo_root / relative_path).stat().st_mtime_ns
        for relative_path in _PRODUCER_PATHS
        if (repo_root / relative_path).is_file()
    }


def _input_snapshot(repo_root: Path) -> dict[str, bytes]:
    return {
        relative_path: (repo_root / relative_path).read_bytes()
        for relative_path in (
            "docs/azure/azure-services-data.md",
            "src/data/sample-data.json",
        )
    }


def _repo_entry_set(repo_root: Path) -> set[tuple[str, str]]:
    return {
        (
            path.relative_to(repo_root).as_posix(),
            "dir" if path.is_dir() and not path.is_symlink() else "file",
        )
        for path in repo_root.rglob("*")
    }


def _repo_state(repo_root: Path) -> dict[str, tuple[object, ...]]:
    state: dict[str, tuple[object, ...]] = {}
    for path in sorted(repo_root.rglob("*")):
        relative = path.relative_to(repo_root).as_posix()
        metadata = os.lstat(path)
        payload = path.read_bytes() if stat.S_ISREG(metadata.st_mode) else None
        link_target = os.readlink(path) if stat.S_ISLNK(metadata.st_mode) else None
        state[relative] = (
            metadata.st_mode,
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_nlink,
            metadata.st_size,
            metadata.st_mtime_ns,
            link_target,
            payload,
        )
    return state


def _assert_result(result, status: str, repo_root: Path) -> None:
    assert result.status == status
    assert type(result.audit_mode) is str
    assert result.audit_mode in {"sql-ledger-digest", "acl-direct"}
    assert result.summary == " ".join(result.summary.split())
    assert 0 < len(result.summary) <= 280
    assert str(repo_root) not in result.summary
    assert "SECRET_REPO_COMPONENT_DO_NOT_LOG" not in result.summary
    assert "\n" not in result.summary


def _readline_with_timeout(
    process: subprocess.Popen[str],
    timeout: float = 10,
) -> str:
    stdout = process.stdout
    assert stdout is not None
    outcome: Queue[tuple[str, object]] = Queue(maxsize=1)

    def read_line() -> None:
        try:
            outcome.put(("line", stdout.readline()))
        except BaseException as exc:
            outcome.put(("error", exc))

    reader = Thread(target=read_line, daemon=True)
    reader.start()
    try:
        kind, value = outcome.get(timeout=timeout)
    except Empty:
        _terminate_process(process)
        reader.join(timeout=1)
        raise TimeoutError("child process did not emit a line in time") from None
    if kind == "error":
        raise cast(BaseException, value)
    reader.join(timeout=1)
    return cast(str, value)


def _communicate_with_kill(
    process: subprocess.Popen[str],
    timeout: float = 10,
) -> tuple[str, str]:
    try:
        return process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_process(process)
        return "", ""


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                    timeout=3,
                )
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
        else:
            process.kill()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass


def _validate_rendered(rendered, design_text: str) -> list[str]:
    assert set(rendered) == _EXPECTED_PATHS
    assert all(isinstance(value, bytes) for value in rendered.values())
    texts = {
        path: value.decode("utf-8")
        for path, value in rendered.items()
    }
    errors = validate_asdw_data_create_scripts(
        "src/infra/azure/create-azure-data-resources-prep.sh",
        "src/infra/azure/create-azure-data-resources.sh",
        design_doc_path="docs/azure/azure-services-data.md",
        sample_data_path="src/data/sample-data.json",
        prep_text=texts[
            "src/infra/azure/create-azure-data-resources-prep.sh"
        ],
        create_text=texts[
            "src/infra/azure/create-azure-data-resources.sh"
        ],
        design_doc_text=design_text,
        sample_data_text=_SAMPLE_DATA,
    )
    errors.extend(
        validate_asdw_data_registration_script(
            "src/data/azure/data-registration-script.sh",
            design_doc_path="docs/azure/azure-services-data.md",
            script_text=texts[
                "src/data/azure/data-registration-script.sh"
            ],
            design_doc_text=design_text,
        )
    )
    return errors


def _bash_executable() -> str | None:
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    if git_bash.is_file():
        return str(git_bash)
    return shutil.which("bash")


def _guarded_child_source(body: str) -> str:
    return f"""
import os
import sys
import importlib
import pathlib
import socket
import subprocess

sys.dont_write_bytecode = True
guard_state = {{"armed": False}}

class RejectAzureFinder:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "azure" or fullname.startswith("azure."):
            raise AssertionError(f"Azure SDK import is forbidden: {{fullname}}")
        return None

def audit(event, args):
    if event == "open":
        if guard_state["armed"]:
            raise AssertionError(f"filesystem access is forbidden: {{event}} {{args!r}}")
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else None
        if isinstance(mode, str) and any(token in mode for token in "wax+"):
            raise AssertionError(f"filesystem write is forbidden: {{event}} {{args!r}}")
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        if isinstance(flags, int) and flags & write_flags:
            raise AssertionError(f"filesystem write is forbidden: {{event}} {{args!r}}")
    filesystem_mutations = {{
        "os.chmod", "os.chown", "os.link", "os.mkdir", "os.mknod",
        "os.remove", "os.rename", "os.rmdir", "os.symlink",
        "os.truncate", "os.utime",
    }}
    if (
        event in filesystem_mutations
        or event == "os.system"
        or event.startswith("subprocess.")
        or event.startswith("socket.")
    ):
        raise AssertionError(f"external I/O is forbidden: {{event}} {{args!r}}")

sys.meta_path.insert(0, RejectAzureFinder())
sys.addaudithook(audit)

{body}
"""


def _run_guarded_child(
    body: str,
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-c", _guarded_child_source(body)],
        cwd=cwd or Path(__file__).resolve().parents[2],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("design_text", (_SQL_DESIGN, _ACL_DESIGN))
def test_rendered_producers_pass_current_design_aware_validators(
    design_text: str,
) -> None:
    rendered = _render(design_text)

    assert _validate_rendered(rendered, design_text) == []


def test_rendered_producer_paths_and_bytes_are_fixed_and_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _render()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")
    monkeypatch.setenv("ASDW_GENERATOR_UNRELATED", "different")
    second = _render()

    assert set(first) == _EXPECTED_PATHS
    assert first == second
    for path, payload in first.items():
        assert isinstance(path, str)
        assert isinstance(payload, bytes)
        assert payload.startswith(b"#!/usr/bin/env bash\n")
        assert not payload.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in payload


def test_rendered_producer_mapping_is_immutable() -> None:
    rendered = _render()

    with pytest.raises(TypeError):
        rendered[next(iter(rendered))] = b"changed"  # type: ignore[index]

    assert tuple(rendered) == (
        "src/infra/azure/create-azure-data-resources-prep.sh",
        "src/infra/azure/create-azure-data-resources.sh",
        "src/data/azure/data-registration-script.sh",
    )


@pytest.mark.parametrize(
    ("design_text", "database_keys"),
    (
        (
            _SQL_DESIGN,
            (
                "SQL_DB_SVC01",
                "SQL_DB_SVC02",
                "SQL_DB_SVC03",
                "SQL_DB_SVC07",
                "SQL_DB_SVC09",
                "SQL_DB_SVC12",
            ),
        ),
        (
            _ACL_DESIGN,
            (
                "SQL_DB_SVC01",
                "SQL_DB_SVC02",
                "SQL_DB_SVC03",
                "SQL_DB_SVC07",
                "SQL_DB_SVC09",
            ),
        ),
    ),
)
def test_rendered_create_provisions_every_sql_database_consumed_by_its_payload(
    design_text: str,
    database_keys: tuple[str, ...],
) -> None:
    """No ACI payload or ledger command may reference an uncreated SQL DB."""
    create = _render(design_text)[
        "src/infra/azure/create-azure-data-resources.sh"
    ].decode("utf-8")

    for database_key in database_keys:
        create_command = (
            'az sql db create --resource-group "$RESOURCE_GROUP" '
            '--server "$SQL_SERVER" --name "$' + database_key + '" --output none'
        )
        assert create.count(create_command) == 1
        if database_key == "SQL_DB_SVC12":
            assert create.index(create_command) < create.index(
                "az sql db ledger-digest-uploads enable"
            )


def test_rendered_create_observes_private_resource_dependencies() -> None:
    """Private endpoints and DNS associations must follow their prerequisites."""
    create = _render()[
        "src/infra/azure/create-azure-data-resources.sh"
    ].decode("utf-8")
    sql_server_create = "az sql server create"
    cosmos_account_create = "az cosmosdb create"
    sql_private_endpoint = (
        'az network private-endpoint create --resource-group "$RESOURCE_GROUP" '
        '--name "$SQL_PRIVATE_ENDPOINT_NAME"'
    )
    cosmos_private_endpoint = (
        'az network private-endpoint create --resource-group "$RESOURCE_GROUP" '
        '--name "$COSMOS_PRIVATE_ENDPOINT_NAME"'
    )
    sql_dns_zone = (
        'az network private-dns zone create --resource-group "$RESOURCE_GROUP" '
        '--name "$SQL_PRIVATE_DNS_ZONE"'
    )
    cosmos_dns_zone = (
        'az network private-dns zone create --resource-group "$RESOURCE_GROUP" '
        '--name "$COSMOS_PRIVATE_DNS_ZONE"'
    )
    sql_dns_group = (
        'az network private-endpoint dns-zone-group create '
        '--resource-group "$RESOURCE_GROUP" '
        '--endpoint-name "$SQL_PRIVATE_ENDPOINT_NAME"'
    )
    cosmos_dns_group = (
        'az network private-endpoint dns-zone-group create '
        '--resource-group "$RESOURCE_GROUP" '
        '--endpoint-name "$COSMOS_PRIVATE_ENDPOINT_NAME"'
    )

    assert create.index(sql_server_create) < create.index(sql_private_endpoint)
    assert create.index(cosmos_account_create) < create.index(cosmos_private_endpoint)
    assert create.index(sql_dns_zone) < create.index(sql_dns_group)
    assert create.index(cosmos_dns_zone) < create.index(cosmos_dns_group)
    assert create.index(sql_private_endpoint) < create.index(sql_dns_group)
    assert create.index(cosmos_private_endpoint) < create.index(cosmos_dns_group)


@pytest.mark.parametrize(
    ("design_text", "sample_text"),
    (
        (
            _design_document("Azure Blob Storage immutable storage"),
            _SAMPLE_DATA,
        ),
        (_SQL_DESIGN, "{not-json}"),
        (
            _SQL_DESIGN,
            _SAMPLE_DATA.replace(
                '"Member": [{"memberId": "member-1"}]',
                '"Member": []',
            ),
        ),
        (
            _SQL_DESIGN,
            _SAMPLE_DATA.replace(
                '"VocRecord": [{"sourceRecordId": "voc-1"}]',
                '"VocRecord": []',
            ),
        ),
        (
            _SQL_DESIGN,
            _SAMPLE_DATA.replace(
                '"AuditRecord": [{"auditEventId": "audit-1"}]',
                '"AuditRecord": []',
            ),
        ),
        (
            _SQL_DESIGN,
            _SAMPLE_DATA.replace(
                '    "CaseResolution": [{"resolutionId": "resolution-1"}],\n',
                "",
            ),
        ),
    ),
)
def test_render_fails_closed_for_unknown_mode_or_invalid_sample(
    design_text: str,
    sample_text: str,
) -> None:
    module = _generator_module()

    with pytest.raises(module.AsdwDataScriptGenerationError):
        module.render_asdw_data_producers(
            design_text=design_text,
            sample_data_text=sample_text,
        )


@pytest.mark.parametrize(
    "sample_text",
    (
        _SAMPLE_DATA.replace('{"memberId": "member-1"}', '{}'),
        _SAMPLE_DATA.replace('[{"memberId": "member-1"}]', '[1]'),
        _SAMPLE_DATA.replace(
            '{"resolutionId": "resolution-1"}',
            '{"resolutionId": " resolution-1"}',
        ),
        _SAMPLE_DATA.replace(
            '[{"sourceRecordId": "voc-1"}]',
            '[{"sourceRecordId": "voc-1"}, {"sourceRecordId": "voc-1"}]',
        ),
    ),
)
def test_render_rejects_samples_that_canonical_payload_cannot_execute(
    sample_text: str,
) -> None:
    module = _generator_module()

    with pytest.raises(module.AsdwDataScriptGenerationError):
        _render(sample_text=sample_text)


def test_render_tolerates_entities_beyond_app009_coverage() -> None:
    """sample-data.json is a shared ALL-APPS fixture; extra entities must not fail render."""
    sample_text = _SAMPLE_DATA.replace(
        '    "AuditRecord": [{"auditEventId": "audit-1"}]\n',
        '    "AuditRecord": [{"auditEventId": "audit-1"}],\n'
        '    "UnrelatedOtherAppEntity": [{"otherAppEntityId": "other-1"}]\n',
    )

    rendered = _render(sample_text=sample_text)

    assert set(rendered) == _EXPECTED_PATHS


def test_sample_error_does_not_echo_untrusted_entity_name() -> None:
    module = _generator_module()
    secret_marker = "SECRET_API_KEY_DO_NOT_LOG"
    sample_text = _SAMPLE_DATA.replace(
        '    "AuditRecord": [{"auditEventId": "audit-1"}]\n',
        '    "AuditRecord": [{"auditEventId": "audit-1"}],\n'
        f'    "{secret_marker}": 42\n',
    )

    with pytest.raises(module.AsdwDataScriptGenerationError) as exc_info:
        _render(sample_text=sample_text)

    assert secret_marker not in str(exc_info.value)
    assert "\n" not in str(exc_info.value)
    assert len(str(exc_info.value)) <= 280


def test_combined_errors_are_single_line_and_bounded() -> None:
    module = _generator_module()

    message = module._combine_errors(["A" * 400, "B" * 400])

    assert "\n" not in message
    assert len(message) <= 280
    assert message.endswith("...")


def test_non_object_sample_record_reports_fixed_location_without_value() -> None:
    module = _generator_module()
    sample_text = _SAMPLE_DATA.replace(
        '[{"memberId": "member-1"}]',
        '["SECRET_RECORD_VALUE"]',
    )

    with pytest.raises(module.AsdwDataScriptGenerationError) as exc_info:
        _render(sample_text=sample_text)

    message = str(exc_info.value)
    assert message == "Selected APP sample-data Member[0] must be an object."
    assert "SECRET_RECORD_VALUE" not in message


@pytest.mark.parametrize("template", ("no marker", "anchor anchor"))
def test_template_anchor_must_occur_exactly_once(template: str) -> None:
    module = _generator_module()

    with pytest.raises(
        module.AsdwDataScriptGenerationError,
        match="template anchor must occur exactly once",
    ):
        module._replace_exactly_once(template, "anchor", "replacement")


def test_generator_import_and_render_have_no_external_io() -> None:
    result = _run_guarded_child(
        f"""
from hve.asdw_data_script_generator import render_asdw_data_producers
guard_state["armed"] = True
rendered = render_asdw_data_producers(
    design_text={_SQL_DESIGN!r},
    sample_data_text={_SAMPLE_DATA!r},
)
assert set(rendered) == {_EXPECTED_PATHS!r}
assert all(isinstance(value, bytes) for value in rendered.values())
"""
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("operation", "expected_error"),
    (
        (
            'pathlib.Path("probe-write.tmp").write_text("x")',
            "filesystem access is forbidden:",
        ),
        (
            'import os; os.symlink("source", "probe-link")',
            "external I/O is forbidden:",
        ),
        ("socket.socket()", "external I/O is forbidden:"),
        (
            'importlib.import_module("azure.synthetic")',
            "Azure SDK import is forbidden:",
        ),
        (
            'subprocess.run([sys.executable, "-V"])',
            "external I/O is forbidden:",
        ),
    ),
)
def test_external_io_guard_rejects_forbidden_operations(
    operation: str,
    expected_error: str,
    tmp_path: Path,
) -> None:
    try:
        result = _run_guarded_child(
            'guard_state["armed"] = True\n' + operation,
            cwd=tmp_path,
        )
    finally:
        for child in tmp_path.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)

    assert result.returncode != 0
    assert expected_error in result.stderr


@pytest.mark.parametrize("relative_path", sorted(_EXPECTED_PATHS))
def test_rendered_producers_pass_bash_syntax_and_shellcheck(
    relative_path: str,
    tmp_path: Path,
) -> None:
    bash = _bash_executable()
    shellcheck = shutil.which("shellcheck")
    assert bash is not None, "Bash is required for the producer contract"
    assert shellcheck is not None, "ShellCheck is required for the producer contract"
    rendered = _render()
    script_path = tmp_path / Path(relative_path).name
    script_path.write_bytes(rendered[relative_path])

    syntax_result = subprocess.run(
        [bash, "-n", str(script_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert syntax_result.returncode == 0, syntax_result.stdout + syntax_result.stderr

    result = subprocess.run(
        [shellcheck, str(script_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_ensure_reuses_validator_valid_noncanonical_producers_without_touching_them(
    tmp_path: Path,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "SECRET_REPO_COMPONENT_DO_NOT_LOG"
    generated = dict(_render())
    current = dict(generated)
    current[_PRODUCER_PATHS[0]] = current[_PRODUCER_PATHS[0]].replace(
        b"# HVE-ASDW-DATA-PREP-BEGIN\n",
        b"# HVE-ASDW-DATA-PREP-BEGIN\n# validator-accepted existing comment\n",
        1,
    )
    assert current != generated
    assert _validate_rendered(current, _SQL_DESIGN) == []
    _prepare_promotion_repo(repo_root, current)
    before_bytes = _producer_snapshot(repo_root)
    before_mtimes = _producer_mtimes(repo_root)
    before_inputs = _input_snapshot(repo_root)
    before_entries = _repo_entry_set(repo_root)

    result = module.ensure_asdw_data_producers(repo_root=repo_root)

    _assert_result(result, "reused", repo_root)
    assert _producer_snapshot(repo_root) == before_bytes
    assert _producer_mtimes(repo_root) == before_mtimes
    assert _input_snapshot(repo_root) == before_inputs
    assert _repo_entry_set(repo_root) == before_entries


def test_ensure_regenerates_all_three_when_one_is_invalid(tmp_path: Path) -> None:
    module = _generator_module()
    repo_root = tmp_path / "SECRET_REPO_COMPONENT_DO_NOT_LOG"
    generated = dict(_render())
    current = dict(generated)
    current[_PRODUCER_PATHS[0]] = b"invalid current prep\n"
    _prepare_promotion_repo(repo_root, current)
    fixed_mtimes: dict[str, int] = {}
    for index, relative_path in enumerate(_PRODUCER_PATHS):
        fixed_ns = 946_684_800_000_000_000 + index * 1_000_000
        os.utime(repo_root / relative_path, ns=(fixed_ns, fixed_ns))
        fixed_mtimes[relative_path] = fixed_ns
    before_inputs = _input_snapshot(repo_root)
    before_entries = _repo_entry_set(repo_root)

    result = module.ensure_asdw_data_producers(repo_root=repo_root)

    _assert_result(result, "regenerated", repo_root)
    assert _producer_snapshot(repo_root) == generated
    assert all(
        (repo_root / path).stat().st_mtime_ns != fixed_mtimes[path]
        for path in _PRODUCER_PATHS
    )
    assert _input_snapshot(repo_root) == before_inputs
    assert _repo_entry_set(repo_root) == before_entries


@pytest.mark.parametrize("invalid_path", _PRODUCER_PATHS)
def test_ensure_validates_each_generated_artifact_before_any_target_write(
    invalid_path: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    originals = {
        path: f"original invalid {index}\n".encode()
        for index, path in enumerate(_PRODUCER_PATHS)
    }
    _prepare_promotion_repo(repo_root, originals)
    before_mtimes = _producer_mtimes(repo_root)
    before_inputs = _input_snapshot(repo_root)
    before_entries = _repo_entry_set(repo_root)
    invalid = dict(_render())
    if invalid_path == _PRODUCER_PATHS[0]:
        invalid[invalid_path] = invalid[invalid_path].replace(
            b"# HVE-ASDW-DATA-PREP-BEGIN",
            b"# INVALID-PREP-BEGIN",
            1,
        )
    elif invalid_path == _PRODUCER_PATHS[1]:
        assert invalid[invalid_path].count(b"--disable-local-auth true") == 1
        invalid[invalid_path] = invalid[invalid_path].replace(
            b"--disable-local-auth true",
            b"--disable-local-auth false",
            1,
        )
    else:
        invalid[invalid_path] = invalid[invalid_path].replace(
            b"HVE_AUDIT_REGISTRATION_OK",
            b"INVALID_AUDIT_MARKER",
            1,
        )
    validation_errors = _validate_rendered(invalid, _SQL_DESIGN)
    assert validation_errors
    calls = {
        "render": 0,
        "create_validator": 0,
        "registration_validator": 0,
        "generated_prep_and_create_validated": False,
        "generated_registration_validated": False,
    }
    real_create_validator = module.validate_asdw_data_create_scripts
    real_registration_validator = module.validate_asdw_data_registration_script

    def render_invalid(**_kwargs):
        calls["render"] += 1
        return invalid

    def track_create_validator(*args, **kwargs):
        calls["create_validator"] += 1
        if (
            kwargs.get("prep_text") == invalid[_PRODUCER_PATHS[0]].decode("utf-8")
            and kwargs.get("create_text")
            == invalid[_PRODUCER_PATHS[1]].decode("utf-8")
        ):
            calls["generated_prep_and_create_validated"] = True
        return real_create_validator(*args, **kwargs)

    def track_registration_validator(*args, **kwargs):
        calls["registration_validator"] += 1
        if kwargs.get("script_text") == invalid[_PRODUCER_PATHS[2]].decode("utf-8"):
            calls["generated_registration_validated"] = True
        return real_registration_validator(*args, **kwargs)

    monkeypatch.setattr(module, "render_asdw_data_producers", render_invalid)
    monkeypatch.setattr(
        module,
        "validate_asdw_data_create_scripts",
        track_create_validator,
    )
    monkeypatch.setattr(
        module,
        "validate_asdw_data_registration_script",
        track_registration_validator,
    )
    target_write_events: list[tuple[str, Path]] = []
    real_replace = os.replace
    real_path_open = Path.open
    real_os_open = os.open
    real_builtin_open = builtins.open
    real_io_open = io.open

    def as_path(value) -> Path | None:
        if isinstance(value, int):
            return None
        try:
            return Path(os.fsdecode(os.fspath(value)))
        except (TypeError, ValueError):
            return None

    def target_path(value) -> Path | None:
        candidate = as_path(value)
        if candidate is None:
            return None
        try:
            if candidate.relative_to(repo_root).as_posix() in _PRODUCER_PATHS:
                return candidate
        except ValueError:
            pass
        return None

    def record_replace(source, target) -> None:
        candidate = target_path(target)
        if candidate is not None:
            target_write_events.append(("replace", cast(Path, candidate)))
        real_replace(source, target)

    def record_path_open(path, mode="r", *args, **kwargs):
        candidate = target_path(path)
        if candidate is not None and any(flag in mode for flag in "wax+"):
            target_write_events.append(("Path.open", cast(Path, candidate)))
        return real_path_open(path, mode, *args, **kwargs)

    def record_os_open(path, flags, *args, **kwargs):
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        candidate = target_path(path)
        if candidate is not None and flags & write_flags:
            target_write_events.append(("os.open", cast(Path, candidate)))
        return real_os_open(path, flags, *args, **kwargs)

    def record_builtin_open(path, mode="r", *args, **kwargs):
        candidate = target_path(path)
        if candidate is not None and any(flag in mode for flag in "wax+"):
            target_write_events.append(("builtins.open", cast(Path, candidate)))
        return real_builtin_open(path, mode, *args, **kwargs)

    def record_io_open(path, mode="r", *args, **kwargs):
        candidate = target_path(path)
        if candidate is not None and any(flag in mode for flag in "wax+"):
            target_write_events.append(("io.open", cast(Path, candidate)))
        return real_io_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(os, "replace", record_replace)
    monkeypatch.setattr(Path, "open", record_path_open)
    monkeypatch.setattr(os, "open", record_os_open)
    monkeypatch.setattr(builtins, "open", record_builtin_open)
    monkeypatch.setattr(io, "open", record_io_open)

    with pytest.raises(module.AsdwDataScriptGenerationError, match="validation"):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert calls["render"] == 1
    assert calls["create_validator"] >= 1
    assert calls["registration_validator"] >= 1
    assert calls["generated_prep_and_create_validated"] is True
    assert calls["generated_registration_validated"] is True
    assert target_write_events == []
    assert _producer_snapshot(repo_root) == originals
    assert _producer_mtimes(repo_root) == before_mtimes
    assert _input_snapshot(repo_root) == before_inputs
    assert _repo_entry_set(repo_root) == before_entries


def test_ensure_rolls_back_existing_set_when_second_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    originals = {
        path: f"original invalid {index}\n".encode()
        for index, path in enumerate(_PRODUCER_PATHS)
    }
    _prepare_promotion_repo(repo_root, originals)
    before_inputs = _input_snapshot(repo_root)
    before_entries = _repo_entry_set(repo_root)
    generated = dict(_render())
    real_replace = os.replace
    successful_promotions: list[str] = []
    injected = False

    def fail_second_promotion(source, target) -> None:
        nonlocal injected
        source_path = Path(source)
        target_path = Path(target)
        try:
            relative = target_path.relative_to(repo_root).as_posix()
        except ValueError:
            relative = ""
        is_promotion = (
            not injected
            and relative in _PRODUCER_PATHS
            and source_path.parent == target_path.parent
            and source_path.is_file()
            and source_path.read_bytes() == generated[relative]
        )
        if is_promotion and successful_promotions:
            injected = True
            raise OSError("injected second promotion failure")
        real_replace(source, target)
        if is_promotion:
            successful_promotions.append(relative)

    monkeypatch.setattr(os, "replace", fail_second_promotion)

    with pytest.raises(module.AsdwDataScriptGenerationError):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert injected
    assert len(successful_promotions) == 1
    assert _producer_snapshot(repo_root) == originals
    assert _input_snapshot(repo_root) == before_inputs
    assert _repo_entry_set(repo_root) == before_entries


def test_ensure_reports_incomplete_temporary_cleanup_and_preserves_originals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    originals = {
        path: f"original invalid {index}\n".encode()
        for index, path in enumerate(_PRODUCER_PATHS)
    }
    _prepare_promotion_repo(repo_root, originals)
    generated = dict(_render())
    before_entries = _repo_entry_set(repo_root)
    real_replace = os.replace
    real_path_unlink = Path.unlink
    real_os_unlink = os.unlink
    real_os_remove = os.remove
    failure_injected = False

    def fail_first_promotion(source, target) -> None:
        nonlocal failure_injected
        source_path = Path(source)
        target_path = Path(target)
        try:
            relative = target_path.relative_to(repo_root).as_posix()
        except ValueError:
            relative = ""
        if (
            not failure_injected
            and relative in _PRODUCER_PATHS
            and source_path.parent == target_path.parent
            and source_path.is_file()
            and source_path.read_bytes() == generated[relative]
        ):
            failure_injected = True
            raise OSError("injected first promotion failure")
        real_replace(source, target)

    def is_new_repo_file(path) -> bool:
        candidate = Path(path)
        try:
            relative = candidate.relative_to(repo_root).as_posix()
        except ValueError:
            return False
        return (relative, "file") not in before_entries

    secret_marker = "SECRET_CLEANUP_FAILURE_DO_NOT_LOG"

    def reject_path_unlink(path, *args, **kwargs):
        if is_new_repo_file(path):
            raise OSError(f"{secret_marker}: {repo_root}")
        return real_path_unlink(path, *args, **kwargs)

    def reject_os_unlink(path, *args, **kwargs):
        if is_new_repo_file(path):
            raise OSError(f"{secret_marker}: {repo_root}")
        return real_os_unlink(path, *args, **kwargs)

    def reject_os_remove(path, *args, **kwargs):
        if is_new_repo_file(path):
            raise OSError(f"{secret_marker}: {repo_root}")
        return real_os_remove(path, *args, **kwargs)

    monkeypatch.setattr(os, "replace", fail_first_promotion)
    monkeypatch.setattr(Path, "unlink", reject_path_unlink)
    monkeypatch.setattr(os, "unlink", reject_os_unlink)
    monkeypatch.setattr(os, "remove", reject_os_remove)

    try:
        with pytest.raises(
            module.AsdwDataScriptGenerationError,
            match="cleanup.*incomplete",
        ) as exc_info:
            module.ensure_asdw_data_producers(repo_root=repo_root)
        message = str(exc_info.value)
        assert secret_marker not in message
        assert str(repo_root) not in message
        assert "\n" not in message
        assert len(message) <= 280
        residue = [
            path
            for path in repo_root.rglob("*")
            if path.is_file()
            and (path.relative_to(repo_root).as_posix(), "file") not in before_entries
        ]
        assert failure_injected
        assert residue
        assert _producer_snapshot(repo_root) == originals
    finally:
        for path in repo_root.rglob("*"):
            if path.is_file() and is_new_repo_file(path):
                real_os_unlink(path)

    assert _repo_entry_set(repo_root) == before_entries


def test_ensure_creates_completely_missing_fixed_set(tmp_path: Path) -> None:
    module = _generator_module()
    generated = dict(_render())
    repo_root = tmp_path / "missing"
    _prepare_promotion_repo(repo_root, None)
    before_inputs = _input_snapshot(repo_root)
    before_entries = _repo_entry_set(repo_root)

    result = module.ensure_asdw_data_producers(repo_root=repo_root)

    _assert_result(result, "regenerated", repo_root)
    assert _producer_snapshot(repo_root) == generated
    assert _input_snapshot(repo_root) == before_inputs
    expected_new = {(path, "file") for path in _PRODUCER_PATHS}
    expected_new |= {
        ("src/infra", "dir"),
        ("src/infra/azure", "dir"),
        ("src/data/azure", "dir"),
    }
    assert _repo_entry_set(repo_root) == before_entries | expected_new


@pytest.mark.parametrize("missing_path", _PRODUCER_PATHS)
def test_ensure_regenerates_partial_set_with_two_valid_and_one_missing(
    missing_path: str,
    tmp_path: Path,
) -> None:
    module = _generator_module()
    generated = dict(_render())
    repo_root = tmp_path / Path(missing_path).name
    _prepare_promotion_repo(repo_root, generated)
    (repo_root / missing_path).unlink()
    fixed_mtimes: dict[str, int] = {}
    for index, relative_path in enumerate(_PRODUCER_PATHS):
        if relative_path == missing_path:
            continue
        fixed_ns = 946_684_900_000_000_000 + index * 1_000_000
        os.utime(repo_root / relative_path, ns=(fixed_ns, fixed_ns))
        fixed_mtimes[relative_path] = fixed_ns
    before_inputs = _input_snapshot(repo_root)
    before_entries = _repo_entry_set(repo_root)

    result = module.ensure_asdw_data_producers(repo_root=repo_root)

    _assert_result(result, "regenerated", repo_root)
    assert _producer_snapshot(repo_root) == generated
    assert all(
        (repo_root / path).stat().st_mtime_ns != fixed_mtimes[path]
        for path in fixed_mtimes
    )
    assert _input_snapshot(repo_root) == before_inputs
    assert _repo_entry_set(repo_root) == before_entries | {(missing_path, "file")}


def test_ensure_rolls_back_to_original_missing_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    generated = dict(_render())
    missing = _PRODUCER_PATHS[0]
    originals = {
        path: f"original invalid {index}\n".encode()
        for index, path in enumerate(_PRODUCER_PATHS)
        if path != missing
    }
    _prepare_promotion_repo(repo_root, None)
    for path, payload in originals.items():
        _write_repo_file(repo_root, path, payload)
    before_inputs = _input_snapshot(repo_root)
    before_entries = _repo_entry_set(repo_root)
    real_replace = os.replace
    injected = False

    def fail_after_missing_target_promotion(source, target) -> None:
        nonlocal injected
        source_path = Path(source)
        target_path = Path(target)
        relative = target_path.relative_to(repo_root).as_posix()
        real_replace(source, target)
        if (
            not injected
            and relative == missing
            and target_path.read_bytes() == generated[missing]
        ):
            injected = True
            raise OSError("injected post-promotion failure")

    monkeypatch.setattr(os, "replace", fail_after_missing_target_promotion)

    with pytest.raises(module.AsdwDataScriptGenerationError):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert injected
    assert _producer_snapshot(repo_root) == originals
    assert not (repo_root / missing).exists()
    assert _input_snapshot(repo_root) == before_inputs
    assert _repo_entry_set(repo_root) == before_entries


def test_ensure_accepts_crlf_inputs_without_modifying_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    generated = dict(_render())
    _prepare_promotion_repo(repo_root, None, crlf_inputs=True)
    before_inputs = _input_snapshot(repo_root)
    assert all(b"\r\n" in payload for payload in before_inputs.values())
    captured: dict[str, str] = {}
    real_render = module.render_asdw_data_producers

    def capture_normalized_inputs(*, design_text: str, sample_data_text: str):
        captured["design"] = design_text
        captured["sample"] = sample_data_text
        return real_render(
            design_text=design_text,
            sample_data_text=sample_data_text,
        )

    monkeypatch.setattr(module, "render_asdw_data_producers", capture_normalized_inputs)
    result = module.ensure_asdw_data_producers(repo_root=repo_root)

    _assert_result(result, "regenerated", repo_root)
    assert captured == {"design": _SQL_DESIGN, "sample": _SAMPLE_DATA}
    assert all("\r" not in value for value in captured.values())
    assert _producer_snapshot(repo_root) == generated
    assert _input_snapshot(repo_root) == before_inputs


@pytest.mark.parametrize("relative_path", _PRODUCER_PATHS)
@pytest.mark.parametrize("mutation", ("different-bytes", "same-bytes-new-identity"))
def test_ensure_rejects_each_concurrent_target_change_before_promotion(
    relative_path: str,
    mutation: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    originals = {
        path: f"original invalid {index}\n".encode()
        for index, path in enumerate(_PRODUCER_PATHS)
    }
    _prepare_promotion_repo(repo_root, originals)
    target = repo_root / relative_path
    initial_stat = target.stat()
    initial_mtime = initial_stat.st_mtime_ns
    real_render = module.render_asdw_data_producers
    injected_stat = None
    expected_after_injection = originals[relative_path]
    expected_snapshot = dict(originals)
    before_entries = _repo_entry_set(repo_root)
    before_inputs = _input_snapshot(repo_root)

    def render_after_external_replace(*, design_text: str, sample_data_text: str):
        nonlocal injected_stat, expected_after_injection
        rendered = real_render(
            design_text=design_text,
            sample_data_text=sample_data_text,
        )
        replacement = target.with_name(target.name + ".external")
        if mutation == "different-bytes":
            expected_after_injection = b"external concurrent bytes\n"
        replacement.write_bytes(expected_after_injection)
        os.utime(replacement, ns=(initial_stat.st_atime_ns, initial_mtime))
        os.replace(replacement, target)
        injected_stat = target.stat()
        assert target.read_bytes() == expected_after_injection
        assert injected_stat.st_mtime_ns == initial_mtime
        if os.path.samestat(initial_stat, injected_stat):
            pytest.skip("filesystem did not expose a new identity for os.replace")
        expected_snapshot[relative_path] = expected_after_injection
        return rendered

    monkeypatch.setattr(
        module,
        "render_asdw_data_producers",
        render_after_external_replace,
    )

    with pytest.raises(
        module.AsdwDataScriptGenerationError,
        match="changed after the initial snapshot",
    ):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert injected_stat is not None
    assert os.path.samestat(injected_stat, target.stat())
    assert _producer_snapshot(repo_root) == expected_snapshot
    assert _input_snapshot(repo_root) == before_inputs
    assert _repo_entry_set(repo_root) == before_entries


@pytest.mark.parametrize(
    "unsafe_path",
    (
        "docs/azure/azure-services-data.md",
        "src/infra/azure/create-azure-data-resources-prep.sh",
    ),
)
def test_ensure_rejects_nonregular_input_or_producer_path(
    unsafe_path: str,
    tmp_path: Path,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    path = repo_root / unsafe_path
    path.unlink()
    path.mkdir()
    before_state = _repo_state(repo_root)

    with pytest.raises(module.AsdwDataScriptGenerationError):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert _repo_state(repo_root) == before_state


@pytest.mark.parametrize(
    "linked_path",
    (
        "src/data/sample-data.json",
        "src/data/azure/data-registration-script.sh",
    ),
)
def test_ensure_rejects_hardlinked_input_or_producer(
    linked_path: str,
    tmp_path: Path,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    path = repo_root / linked_path
    payload = path.read_bytes()
    path.unlink()
    source = tmp_path / (path.name + ".source")
    source.write_bytes(payload)
    try:
        os.link(source, path)
    except OSError as exc:
        pytest.skip(f"hard links unavailable: {exc}")

    before_state = _repo_state(repo_root)
    source_stat = source.stat()
    path_stat = path.stat()
    assert os.path.samestat(source_stat, path_stat)

    with pytest.raises(module.AsdwDataScriptGenerationError):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert _repo_state(repo_root) == before_state
    assert os.path.samestat(source_stat, source.stat())
    assert os.path.samestat(path_stat, path.stat())
    assert os.path.samestat(source.stat(), path.stat())
    assert source.read_bytes() == payload
    assert path.read_bytes() == payload


@pytest.mark.parametrize(
    "linked_path",
    (
        "docs/azure/azure-services-data.md",
        "src/infra/azure/create-azure-data-resources.sh",
    ),
)
def test_ensure_rejects_symlinked_input_or_producer(
    linked_path: str,
    tmp_path: Path,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    path = repo_root / linked_path
    payload = path.read_bytes()
    path.unlink()
    source = tmp_path / (path.name + ".source")
    source.write_bytes(payload)
    try:
        path.symlink_to(source)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    before_state = _repo_state(repo_root)
    source_stat = source.stat()
    link_stat = os.lstat(path)
    link_target = os.readlink(path)

    with pytest.raises(module.AsdwDataScriptGenerationError):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert _repo_state(repo_root) == before_state
    assert os.path.samestat(source_stat, source.stat())
    assert os.path.samestat(link_stat, os.lstat(path))
    assert os.readlink(path) == link_target
    assert source.read_bytes() == payload


def test_ensure_rejects_symlinked_producer_parent_without_side_effects(
    tmp_path: Path,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    parent = repo_root / "src/infra/azure"
    external = tmp_path / "external-azure-symlink"
    external.mkdir()
    for child in parent.iterdir():
        shutil.move(str(child), external / child.name)
    parent.rmdir()
    try:
        parent.symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")
    before_state = _repo_state(repo_root)
    external_state = _repo_state(external)
    link_stat = os.lstat(parent)
    link_target = os.readlink(parent)

    with pytest.raises(module.AsdwDataScriptGenerationError):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert _repo_state(repo_root) == before_state
    assert _repo_state(external) == external_state
    assert os.path.samestat(link_stat, os.lstat(parent))
    assert os.readlink(parent) == link_target


@pytest.mark.skipif(os.name != "nt", reason="Windows junction contract")
def test_ensure_rejects_junctioned_producer_parent_without_side_effects(
    tmp_path: Path,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    parent = repo_root / "src/infra/azure"
    external = tmp_path / "external-azure"
    external.mkdir()
    for child in parent.iterdir():
        shutil.move(str(child), external / child.name)
    parent.rmdir()
    result = subprocess.run(
        ["cmd.exe", "/c", "mklink", "/J", str(parent), str(external)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("Windows junction creation unavailable")
    before_state = _repo_state(repo_root)
    external_state = _repo_state(external)

    with pytest.raises(module.AsdwDataScriptGenerationError):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert _repo_state(repo_root) == before_state
    assert _repo_state(external) == external_state


def test_ensure_rejects_arbitrary_output_arguments_and_preserves_sentinel(
    tmp_path: Path,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "SECRET_REPO_COMPONENT_DO_NOT_LOG"
    _prepare_promotion_repo(repo_root, dict(_render()))
    sentinel = tmp_path / "outside.txt"
    sentinel.write_bytes(b"unchanged\n")
    before_producers = _producer_snapshot(repo_root)
    before_inputs = _input_snapshot(repo_root)
    before_entries = _repo_entry_set(repo_root)

    with pytest.raises(TypeError):
        module.ensure_asdw_data_producers(repo_root=repo_root, output_path=sentinel)
    with pytest.raises(TypeError):
        module.ensure_asdw_data_producers(repo_root=repo_root, output_paths=[sentinel])

    assert sentinel.read_bytes() == b"unchanged\n"
    assert _producer_snapshot(repo_root) == before_producers
    assert _input_snapshot(repo_root) == before_inputs
    assert _repo_entry_set(repo_root) == before_entries


@pytest.mark.parametrize(
    ("relative_path", "mutate"),
    (
        (
            "docs/azure/azure-services-data.md",
            lambda payload: b"\xef\xbb\xbf" + payload,
        ),
        (
            "docs/azure/azure-services-data.md",
            lambda payload: payload + b"\r",
        ),
        (
            "src/data/sample-data.json",
            lambda payload: payload + b"\xff",
        ),
        (
            "src/infra/azure/create-azure-data-resources-prep.sh",
            lambda payload: payload.replace(b"\n", b"\r", 1),
        ),
    ),
)
def test_ensure_rejects_invalid_input_or_producer_encoding_without_side_effects(
    relative_path: str,
    mutate,
    tmp_path: Path,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    path = repo_root / relative_path
    path.write_bytes(mutate(path.read_bytes()))
    before_state = _repo_state(repo_root)

    with pytest.raises(module.AsdwDataScriptGenerationError):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert _repo_state(repo_root) == before_state


def test_stable_reader_detects_same_metadata_content_change_between_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    target = repo_root / "docs/azure/azure-services-data.md"
    original = target.read_bytes()
    metadata = target.stat()
    changed = bytes([original[0] ^ 1]) + original[1:]
    real_read = module._read_descriptor_bytes
    mutated = False

    def mutate_after_first_read(descriptor: int) -> bytes:
        nonlocal mutated
        payload = real_read(descriptor)
        if (
            not mutated
            and os.path.samestat(os.fstat(descriptor), target.stat())
        ):
            mutated = True
            target.write_bytes(changed)
            os.utime(target, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        return payload

    monkeypatch.setattr(module, "_read_descriptor_bytes", mutate_after_first_read)
    before_producers = _producer_snapshot(repo_root)

    with pytest.raises(module.AsdwDataScriptGenerationError):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert mutated
    assert target.read_bytes() == changed
    assert target.stat().st_size == metadata.st_size
    assert target.stat().st_mtime_ns == metadata.st_mtime_ns
    assert _producer_snapshot(repo_root) == before_producers


def test_ensure_rejects_interprocess_lock_contention_then_recovers(
    tmp_path: Path,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    lock_path = module._producer_lock_path(repo_root.resolve())
    holder_script = (
        "from pathlib import Path\n"
        "import sys\n"
        "from hve.asdw_data_script_launcher import "
        "_acquire_stage_execution_lock, _release_stage_execution_lock\n"
        "lock = _acquire_stage_execution_lock(Path(sys.argv[1]))\n"
        "print('READY', flush=True)\n"
        "sys.stdin.readline()\n"
        "_release_stage_execution_lock(lock)\n"
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", holder_script, str(lock_path)],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert _readline_with_timeout(holder).strip() == "READY"
        with pytest.raises(
            module.AsdwDataScriptGenerationError,
            match="lock is unavailable",
        ):
            module.ensure_asdw_data_producers(repo_root=repo_root)
    finally:
        if holder.stdin is not None:
            holder.stdin.write("\n")
            holder.stdin.flush()
        stdout, stderr = _communicate_with_kill(holder)
        assert holder.returncode == 0, stdout + stderr

    result = module.ensure_asdw_data_producers(repo_root=repo_root)
    _assert_result(result, "reused", repo_root)


def test_reuse_recheck_rejects_concurrent_identity_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    generated = dict(_render())
    _prepare_promotion_repo(repo_root, generated)
    target = repo_root / _PRODUCER_PATHS[0]
    initial = target.stat()
    real_validation = module._producer_validation_errors
    injected = False

    def validate_then_replace(**kwargs):
        nonlocal injected
        errors = real_validation(**kwargs)
        replacement = target.with_name(target.name + ".external")
        replacement.write_bytes(target.read_bytes())
        os.utime(replacement, ns=(initial.st_atime_ns, initial.st_mtime_ns))
        os.replace(replacement, target)
        injected = True
        assert not os.path.samestat(initial, target.stat())
        return errors

    monkeypatch.setattr(module, "_producer_validation_errors", validate_then_replace)

    with pytest.raises(
        module.AsdwDataScriptGenerationError,
        match="changed after the initial snapshot",
    ):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert injected
    assert _producer_snapshot(repo_root) == generated


def test_final_set_recheck_does_not_overwrite_external_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    originals = {
        path: f"original invalid {index}\n".encode()
        for index, path in enumerate(_PRODUCER_PATHS)
    }
    _prepare_promotion_repo(repo_root, originals)
    generated = dict(_render())
    target = repo_root / _PRODUCER_PATHS[0]
    external_payload = b"external owner payload\n"
    real_replace = os.replace
    forward_promotions: list[str] = []

    def replace_then_swap_after_third(source, destination) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        try:
            relative = destination_path.relative_to(repo_root).as_posix()
        except ValueError:
            relative = ""
        is_forward = (
            relative in _PRODUCER_PATHS
            and source_path.is_file()
            and source_path.read_bytes() == generated[relative]
        )
        real_replace(source, destination)
        if is_forward:
            forward_promotions.append(relative)
            if len(forward_promotions) == len(_PRODUCER_PATHS):
                replacement = target.with_name(target.name + ".external")
                replacement.write_bytes(external_payload)
                real_replace(replacement, target)

    monkeypatch.setattr(os, "replace", replace_then_swap_after_third)

    with pytest.raises(
        module.AsdwDataScriptGenerationError,
        match="rollback was not completed",
    ):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert target.read_bytes() == external_payload
    assert (repo_root / _PRODUCER_PATHS[1]).read_bytes() == originals[_PRODUCER_PATHS[1]]
    assert (repo_root / _PRODUCER_PATHS[2]).read_bytes() == originals[_PRODUCER_PATHS[2]]


def test_owned_temp_and_directory_cleanup_preserve_replaced_identity(
    tmp_path: Path,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    owned_file = repo_root / "owned.tmp"
    owned_file.write_bytes(b"owned")
    file_record = module._OwnedPath(owned_file, os.lstat(owned_file))
    file_external = repo_root / "file.external"
    file_external.write_bytes(b"external")
    os.replace(file_external, owned_file)

    owned_directory = repo_root / "owned-dir"
    owned_directory.mkdir()
    directory_record = module._OwnedPath(
        owned_directory,
        os.lstat(owned_directory),
    )
    owned_directory.rmdir()
    owned_directory.mkdir()

    file_records = [file_record]
    directory_records = [directory_record]
    assert module._cleanup_temporary_paths(file_records) is True
    assert module._cleanup_created_directories(directory_records) is True
    assert owned_file.read_bytes() == b"external"
    assert owned_directory.is_dir()
    assert file_records == [file_record]
    assert directory_records == [directory_record]


@pytest.mark.parametrize("cancel_after", (1, 2, 3))
def test_promotion_cancellation_rolls_back_complete_set_and_reraises(
    cancel_after: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    originals = {
        path: f"original invalid {index}\n".encode()
        for index, path in enumerate(_PRODUCER_PATHS)
    }
    _prepare_promotion_repo(repo_root, originals)
    before_inputs = _input_snapshot(repo_root)
    before_entries = _repo_entry_set(repo_root)
    generated = dict(_render())
    real_replace = os.replace
    promotions = 0

    def cancel_after_forward_replace(source, destination) -> None:
        nonlocal promotions
        source_path = Path(source)
        destination_path = Path(destination)
        try:
            relative = destination_path.relative_to(repo_root).as_posix()
        except ValueError:
            relative = ""
        is_forward = (
            relative in _PRODUCER_PATHS
            and source_path.is_file()
            and source_path.read_bytes() == generated[relative]
        )
        real_replace(source, destination)
        if is_forward:
            promotions += 1
            if promotions == cancel_after:
                raise KeyboardInterrupt("injected cancellation")

    monkeypatch.setattr(os, "replace", cancel_after_forward_replace)

    with pytest.raises(KeyboardInterrupt, match="injected cancellation"):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert promotions == cancel_after
    assert _producer_snapshot(repo_root) == originals
    assert _input_snapshot(repo_root) == before_inputs
    assert _repo_entry_set(repo_root) == before_entries


def test_temporary_initialization_double_failure_reports_cleanup_and_allows_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "SECRET_REPO_COMPONENT_DO_NOT_LOG"
    originals = {
        path: f"original invalid {index}\n".encode()
        for index, path in enumerate(_PRODUCER_PATHS)
    }
    _prepare_promotion_repo(repo_root, originals)
    before_entries = _repo_entry_set(repo_root)
    real_fsync = os.fsync
    real_path_unlink = Path.unlink
    residue: list[Path] = []

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("SECRET_FSYNC_DETAIL")

    def fail_temp_unlink(path, *args, **kwargs):
        candidate = Path(path)
        try:
            relative = candidate.relative_to(repo_root).as_posix()
        except ValueError:
            relative = ""
        if (relative, "file") not in before_entries:
            residue.append(candidate)
            raise OSError(f"SECRET_UNLINK_DETAIL: {repo_root}")
        return real_path_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "fsync", fail_fsync)
    monkeypatch.setattr(Path, "unlink", fail_temp_unlink)
    try:
        with pytest.raises(
            module.AsdwDataScriptGenerationError,
            match="temporary cleanup was incomplete",
        ) as exc_info:
            module.ensure_asdw_data_producers(repo_root=repo_root)
        message = str(exc_info.value)
        assert "SECRET_" not in message
        assert str(repo_root) not in message
        assert residue
        assert _producer_snapshot(repo_root) == originals
    finally:
        monkeypatch.setattr(os, "fsync", real_fsync)
        for path in residue:
            if path.exists():
                os.unlink(path)

    result = module.ensure_asdw_data_producers(repo_root=repo_root)
    _assert_result(result, "regenerated", repo_root)


def test_failed_replace_with_external_same_bytes_identity_is_not_reported_restored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    originals = {
        path: f"original invalid {index}\n".encode()
        for index, path in enumerate(_PRODUCER_PATHS)
    }
    _prepare_promotion_repo(repo_root, originals)
    generated = dict(_render())
    target = repo_root / _PRODUCER_PATHS[0]
    initial = target.stat()
    real_replace = os.replace
    injected_stat = None

    def external_swap_then_fail(source, destination) -> None:
        nonlocal injected_stat
        source_path = Path(source)
        destination_path = Path(destination)
        try:
            relative = destination_path.relative_to(repo_root).as_posix()
        except ValueError:
            relative = ""
        if (
            injected_stat is None
            and relative == _PRODUCER_PATHS[0]
            and source_path.is_file()
            and source_path.read_bytes() == generated[relative]
        ):
            replacement = target.with_name(target.name + ".external")
            replacement.write_bytes(originals[relative])
            os.utime(replacement, ns=(initial.st_atime_ns, initial.st_mtime_ns))
            real_replace(replacement, target)
            injected_stat = target.stat()
            raise OSError("injected failed replace")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", external_swap_then_fail)

    with pytest.raises(
        module.AsdwDataScriptGenerationError,
        match="changed after the initial snapshot",
    ):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert injected_stat is not None
    assert not os.path.samestat(initial, injected_stat)
    assert target.read_bytes() == originals[_PRODUCER_PATHS[0]]


def test_rollback_same_bytes_external_identity_is_reported_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    originals = {
        path: f"original invalid {index}\n".encode()
        for index, path in enumerate(_PRODUCER_PATHS)
    }
    _prepare_promotion_repo(repo_root, originals)
    generated = dict(_render())
    target = repo_root / _PRODUCER_PATHS[0]
    real_replace = os.replace
    forward_count = 0
    rollback_swapped = False

    def fail_then_swap_rollback(source, destination) -> None:
        nonlocal forward_count, rollback_swapped
        source_path = Path(source)
        destination_path = Path(destination)
        try:
            relative = destination_path.relative_to(repo_root).as_posix()
        except ValueError:
            relative = ""
        payload = source_path.read_bytes() if source_path.is_file() else b""
        if relative in _PRODUCER_PATHS and payload == generated[relative]:
            forward_count += 1
            if forward_count == 2:
                raise OSError("trigger rollback")
        real_replace(source, destination)
        if (
            not rollback_swapped
            and relative == _PRODUCER_PATHS[0]
            and payload == originals[relative]
        ):
            replacement = target.with_name(target.name + ".external")
            replacement.write_bytes(originals[relative])
            real_replace(replacement, target)
            rollback_swapped = True

    monkeypatch.setattr(os, "replace", fail_then_swap_rollback)

    with pytest.raises(
        module.AsdwDataScriptGenerationError,
        match="rollback failed",
    ):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert rollback_swapped
    assert target.read_bytes() == originals[_PRODUCER_PATHS[0]]


def test_actual_ensure_holds_interprocess_lock_during_validation(
    tmp_path: Path,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    child_script = (
        "import sys\n"
        "from pathlib import Path\n"
        "import hve.asdw_data_script_generator as module\n"
        "real = module._producer_validation_errors\n"
        "def pause(**kwargs):\n"
        "    print('READY', flush=True)\n"
        "    sys.stdin.readline()\n"
        "    return real(**kwargs)\n"
        "module._producer_validation_errors = pause\n"
        "result = module.ensure_asdw_data_producers(Path(sys.argv[1]))\n"
        "print(result.status, flush=True)\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", child_script, str(repo_root)],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert _readline_with_timeout(child).strip() == "READY"
        with pytest.raises(
            module.AsdwDataScriptGenerationError,
            match="lock is unavailable",
        ):
            module.ensure_asdw_data_producers(repo_root=repo_root)
        assert child.stdin is not None
        child.stdin.write("\n")
        child.stdin.flush()
        stdout, stderr = _communicate_with_kill(child)
        assert child.returncode == 0, stdout + stderr
        assert "reused" in stdout
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()


@pytest.mark.parametrize("primary_failure", (False, True))
def test_generator_lock_release_failure_is_fatal_without_masking_primary_error(
    primary_failure: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    if primary_failure:
        (repo_root / "src/data/sample-data.json").write_bytes(b"{not-json}")
    real_close = module._ProducerLockGuard.close

    def close_then_fail(lock) -> None:
        real_close(lock)
        raise module.ScriptLauncherError("injected release failure")

    monkeypatch.setattr(module._ProducerLockGuard, "close", close_then_fail)

    if primary_failure:
        with pytest.raises(module.AsdwDataScriptGenerationError) as exc_info:
            module.ensure_asdw_data_producers(repo_root=repo_root)
        assert "sample-data" in str(exc_info.value).casefold()
        assert any("lock cleanup" in note for note in exc_info.value.__notes__)
    else:
        with pytest.raises(
            module.AsdwDataScriptGenerationError,
            match="lock cleanup failed",
        ):
            module.ensure_asdw_data_producers(repo_root=repo_root)


def test_lock_acquire_handoff_cancellation_does_not_leak_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    real_locking = __import__("msvcrt").locking if os.name == "nt" else None
    if os.name != "nt":
        pytest.skip("Windows lock handoff regression")

    def lock_then_cancel(descriptor: int, mode: int, count: int) -> None:
        assert real_locking is not None
        real_locking(descriptor, mode, count)
        if mode == __import__("msvcrt").LK_NBLCK:
            raise KeyboardInterrupt("injected lock handoff cancellation")

    monkeypatch.setattr(__import__("msvcrt"), "locking", lock_then_cancel)

    with pytest.raises(KeyboardInterrupt, match="lock handoff"):
        module.ensure_asdw_data_producers(repo_root=repo_root)

    monkeypatch.setattr(__import__("msvcrt"), "locking", real_locking)
    result = module.ensure_asdw_data_producers(repo_root=repo_root)
    _assert_result(result, "reused", repo_root)


@pytest.mark.parametrize("handoff", ("temp", "directory"))
def test_resource_registration_handoff_cancellation_is_cleaned(
    handoff: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, None)
    before_entries = _repo_entry_set(repo_root)
    before_inputs = _input_snapshot(repo_root)
    if handoff == "temp":
        helper = module._write_same_directory_temp
        stream_store = max(
            instruction.offset
            for instruction in dis.get_instructions(helper)
            if instruction.opname == "STORE_FAST"
            and instruction.argval == "stream"
        )

        def trace(frame, event, _arg):
            if frame.f_code is helper.__code__:
                frame.f_trace_opcodes = True
                if event == "opcode" and frame.f_lasti == stream_store:
                    raise KeyboardInterrupt(
                        "injected temp registration cancellation"
                    )
            return trace

        sys.settrace(trace)
    else:
        real_lstat = os.lstat
        cancelled = False

        def lstat_then_cancel(path, *args, **kwargs):
            nonlocal cancelled
            result = real_lstat(path, *args, **kwargs)
            candidate = Path(path)
            if (
                not cancelled
                and candidate == repo_root / "src/infra"
                and candidate.is_dir()
            ):
                cancelled = True
                raise KeyboardInterrupt("injected directory registration cancellation")
            return result

        monkeypatch.setattr(os, "lstat", lstat_then_cancel)

    try:
        with pytest.raises(
            KeyboardInterrupt,
            match="registration cancellation",
        ) as exc_info:
            module.ensure_asdw_data_producers(repo_root=repo_root)
    finally:
        sys.settrace(None)

    assert _input_snapshot(repo_root) == before_inputs
    if handoff == "temp":
        assert _repo_entry_set(repo_root) == before_entries
    else:
        assert any(
            "cleanup was incomplete" in note
            for note in exc_info.value.__notes__
        )
        assert _repo_entry_set(repo_root) == before_entries | {("src/infra", "dir")}


@pytest.mark.parametrize("attribute", ("stream", "descriptor"))
def test_lock_file_object_handoff_cancellation_does_not_leak_lock(
    attribute: str,
    tmp_path: Path,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    helper = module._ProducerLockGuard.acquire
    store_offset = next(
        instruction.offset
        for instruction in dis.get_instructions(helper)
        if instruction.opname == "STORE_ATTR" and instruction.argval == attribute
    )

    def trace(frame, event, _arg):
        if frame.f_code is helper.__code__:
            frame.f_trace_opcodes = True
            if event == "opcode" and frame.f_lasti == store_offset:
                raise KeyboardInterrupt(f"injected lock {attribute} handoff")
        return trace

    sys.settrace(trace)
    try:
        with pytest.raises(KeyboardInterrupt, match=f"{attribute} handoff"):
            module.ensure_asdw_data_producers(repo_root=repo_root)
    finally:
        sys.settrace(None)

    result = module.ensure_asdw_data_producers(repo_root=repo_root)
    _assert_result(result, "reused", repo_root)


def test_lock_and_temp_file_objects_do_not_use_python_custom_openers() -> None:
    module = _generator_module()
    source = inspect.getsource(module._ProducerLockGuard.acquire)
    source += inspect.getsource(module._write_same_directory_temp)

    assert "opener=" not in source


def test_lock_close_retry_preserves_first_cancellation_and_closes_stream(
    tmp_path: Path,
) -> None:
    module = _generator_module()
    lock_path = module._producer_lock_path(tmp_path.resolve())
    guard = module._ProducerLockGuard(lock_path)
    guard.acquire()
    real_stream = guard.stream
    assert real_stream is not None

    class CancelOnceStream:
        def __init__(self) -> None:
            self.calls = 0

        def close(self) -> None:
            self.calls += 1
            if self.calls == 1:
                raise KeyboardInterrupt("injected close cancellation")
            real_stream.close()

    wrapper = CancelOnceStream()
    guard.stream = cast(BinaryIO, wrapper)

    with pytest.raises(KeyboardInterrupt, match="close cancellation"):
        guard.close()

    assert wrapper.calls == 2
    assert real_stream.closed
    retry = module._ProducerLockGuard(lock_path)
    retry.acquire()
    retry.close()


def test_lock_root_creation_failure_is_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    lock_root = Path(tempfile.gettempdir()).resolve() / "hve-asdw-producer-locks"
    real_mkdir = Path.mkdir

    def reject_lock_root(path, *args, **kwargs):
        if Path(path) == lock_root:
            raise OSError("SECRET_LOCK_ROOT_DETAIL")
        return real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", reject_lock_root)

    with pytest.raises(
        module.AsdwDataScriptGenerationError,
        match="lock directory is unavailable",
    ) as exc_info:
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert "SECRET_" not in str(exc_info.value)


def test_lock_temp_root_lookup_failure_is_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))

    def fail_gettempdir() -> str:
        raise OSError("SECRET_TEMPDIR_DETAIL")

    monkeypatch.setattr(module.tempfile, "gettempdir", fail_gettempdir)

    with pytest.raises(
        module.AsdwDataScriptGenerationError,
        match="lock directory is unavailable",
    ) as exc_info:
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert "SECRET_" not in str(exc_info.value)


@pytest.mark.parametrize("failure", ("resolve", "lstat"))
def test_lock_root_resolution_or_identity_failure_is_sanitized(
    failure: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    temp_root = Path(tempfile.gettempdir())
    lock_root = temp_root.resolve() / "hve-asdw-producer-locks"
    real_resolve = Path.resolve
    real_lstat = os.lstat

    def fail_resolve(path, *args, **kwargs):
        if failure == "resolve" and Path(path) == temp_root:
            raise OSError("SECRET_LOCK_RESOLVE_DETAIL")
        return real_resolve(path, *args, **kwargs)

    def fail_lstat(path, *args, **kwargs):
        if failure == "lstat" and Path(path) == lock_root:
            raise OSError("SECRET_LOCK_LSTAT_DETAIL")
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    monkeypatch.setattr(os, "lstat", fail_lstat)

    with pytest.raises(
        module.AsdwDataScriptGenerationError,
        match="lock directory is unavailable",
    ) as exc_info:
        module.ensure_asdw_data_producers(repo_root=repo_root)

    assert "SECRET_" not in str(exc_info.value)


@pytest.mark.parametrize("helper", ("readline", "communicate"))
def test_child_timeout_helpers_terminate_and_return_within_bound(
    helper: str,
) -> None:
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import threading; threading.Event().wait()",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    started = time.monotonic()
    if helper == "readline":
        with pytest.raises(TimeoutError):
            _readline_with_timeout(child, timeout=0.1)
    else:
        assert _communicate_with_kill(child, timeout=0.1) == ("", "")
    elapsed = time.monotonic() - started

    assert elapsed < 5
    assert child.poll() is not None


@pytest.mark.parametrize("primary_failure", (False, True))
def test_stable_reader_close_failure_is_sanitized_without_masking_primary(
    primary_failure: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _generator_module()
    repo_root = tmp_path / "repo"
    _prepare_promotion_repo(repo_root, dict(_render()))
    target = repo_root / "docs/azure/azure-services-data.md"
    real_close = os.close
    leaked: list[int] = []

    def fail_close(descriptor: int) -> None:
        leaked.append(descriptor)
        raise OSError("SECRET_CLOSE_DETAIL")

    monkeypatch.setattr(os, "close", fail_close)
    if primary_failure:
        monkeypatch.setattr(
            module,
            "_read_descriptor_bytes",
            lambda _descriptor: (_ for _ in ()).throw(
                module.AsdwDataScriptGenerationError("PRIMARY_READ_FAILURE")
            ),
        )
    try:
        with pytest.raises(module.AsdwDataScriptGenerationError) as exc_info:
            module._read_stable_text_file(
                target,
                repo_root,
                "ASDW data design",
                allow_crlf=True,
            )
    finally:
        monkeypatch.setattr(os, "close", real_close)
        for descriptor in set(leaked):
            try:
                real_close(descriptor)
            except OSError:
                pass

    message = str(exc_info.value)
    assert "SECRET_" not in message
    if primary_failure:
        assert message == "PRIMARY_READ_FAILURE"
        assert any("descriptor cleanup" in note for note in exc_info.value.__notes__)
    else:
        assert message == "ASDW data design failed stable UTF-8 validation."
