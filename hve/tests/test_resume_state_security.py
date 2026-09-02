"""Durable resume security contracts.

Traceability: NFR-SEC-01, FR-STATE-04, FR-CLI-90.
All databases and repository roots are temporary.  External processes and
network entry points are denied so these tests cannot contact SDK, Azure, or
GitHub services.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator, Mapping, Sequence
import http.client
import importlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import stat
import subprocess
from typing import Any
import urllib.request

import pytest


_RESUME_MODULE = "hve.resume_service"
_STATE_MODULE = "hve.run_state_store"
_TABLES = ("executions", "workflow_instances", "step_instances")

_REPLAY_INPUTS = (
    ("additional_prompt", "--additional-prompt", "prompt"),
    ("workiq_prompt_qa", "--workiq-prompt-qa", "response"),
    ("purpose", "--purpose", "reasoning"),
    ("mcp_config", "--mcp-config", "tool_args"),
    ("attached_docs", "--attached-docs", "tool_results"),
    ("company_name", "--company-name", "environment"),
    ("workiq_tenant_id", "--workiq-tenant-id", "token"),
    ("issue_title", "--issue-title", "credential"),
    ("cli_url", "--cli-url", "auth_url"),
    ("target_scope", "--target-scope", "raw_repository_path"),
)

_SANITIZE_CASES = (
    ("free-form", "--additional-prompt", "prompt", "additional_prompt"),
    ("path-gap", "--target-scope", "raw_repository_path", "target_scope"),
    ("path-reject", "--data-location", "raw_repository_path", "data_location"),
    ("auth-url", "--repo", "auth_url", "repo"),
    ("token", "--model", "token", "model"),
    ("credential", "--resource-group", "credential", "resource_group"),
    ("environment", "--branch", "environment", "branch"),
)


def _apis(requirement: str) -> tuple[Any, Any]:
    try:
        resume_api = importlib.import_module(_RESUME_MODULE)
        state_api = importlib.import_module(_STATE_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name in {_RESUME_MODULE, _STATE_MODULE}:
            pytest.fail(
                f"{requirement}: missing production module {exc.name}",
                pytrace=False,
            )
        raise

    resume_names = (
        "ResumeService",
        "WorkflowDescriptor",
        "canonical_json",
        "compute_resume_plan_hash",
    )
    state_names = (
        "DurableStateError",
        "RunStateStore",
        "SCHEMA_VERSION",
        "compute_repo_key",
    )
    missing = [
        f"{_RESUME_MODULE}.{name}"
        for name in resume_names
        if not hasattr(resume_api, name)
    ]
    missing.extend(
        f"{_STATE_MODULE}.{name}"
        for name in state_names
        if not hasattr(state_api, name)
    )
    if missing:
        pytest.fail(
            f"{requirement}: missing production API: {', '.join(missing)}",
            pytrace=False,
        )
    return resume_api, state_api


def _sentinels(repo_root: Path) -> dict[str, str]:
    """Return one distinguishable synthetic value for every forbidden class."""

    return {
        "prompt": "T34_PROMPT_23f83d40",
        "response": "T34_RESPONSE_66a2815c",
        "reasoning": "T34_REASONING_8152e77b",
        "tool_args": '{"T34_TOOL_ARGS":"1d4a8592"}',
        "tool_results": "T34_TOOL_RESULTS_b278009f",
        "environment": "GH_TOKEN=T34_ENV_5e79bc38",
        "token": "ghp_T34_TOKEN_73f6d8e3",
        "credential": "AccountKey=T34_CREDENTIAL_a8d58491",
        "auth_url": "https://user:T34_AUTH_76db2590@example.invalid/oauth",
        "raw_repository_path": str(repo_root.resolve()),
    }


def _descriptor(resume_api: Any, argv: Sequence[str]) -> Any:
    return resume_api.WorkflowDescriptor(
        instance_id="aas-1",
        workflow_id="aas",
        ordinal=0,
        mode="standard",
        argv=tuple(argv),
        missing_replay_keys=(),
    )


def _blocked_call(calls: list[str], label: str) -> Callable[..., Any]:
    def blocked(*_args: Any, **_kwargs: Any) -> Any:
        calls.append(label)
        raise AssertionError(f"T34 external call prohibited: {label}")

    return blocked


@pytest.fixture(autouse=True)
def external_call_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[list[str]]:
    """Deny process and network boundaries used by SDK/Azure/GitHub clients."""

    calls: list[str] = []
    for owner, name, label in (
        (subprocess, "Popen", "subprocess.Popen"),
        (subprocess, "run", "subprocess.run"),
        (subprocess, "call", "subprocess.call"),
        (subprocess, "check_call", "subprocess.check_call"),
        (subprocess, "check_output", "subprocess.check_output"),
        (os, "system", "os.system"),
        (os, "popen", "os.popen"),
        (asyncio, "create_subprocess_exec", "asyncio.create_subprocess_exec"),
        (asyncio, "create_subprocess_shell", "asyncio.create_subprocess_shell"),
        (socket, "create_connection", "socket.create_connection"),
        (socket, "getaddrinfo", "socket.getaddrinfo"),
        (socket.socket, "connect", "socket.socket.connect"),
        (socket.socket, "connect_ex", "socket.socket.connect_ex"),
        (urllib.request, "urlopen", "urllib.request.urlopen"),
        (http.client.HTTPConnection, "connect", "HTTPConnection.connect"),
        (http.client.HTTPSConnection, "connect", "HTTPSConnection.connect"),
    ):
        monkeypatch.setattr(owner, name, _blocked_call(calls, label))

    yield calls

    if calls:
        pytest.fail(
            "T34 external-call guard observed: " + ", ".join(sorted(set(calls))),
            pytrace=False,
        )


def _diagnostic_violations(
    sentinels: Mapping[str, str],
    exceptions: Sequence[tuple[str, BaseException]],
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> list[str]:
    """Consume captured diagnostics and report only safe category/source names."""

    captured = capsys.readouterr()
    sources = [
        (f"exception:{label}", str(exc))
        for label, exc in exceptions
    ]
    sources.extend(
        (
            ("stdout", captured.out),
            ("stderr", captured.err),
            ("log", "\n".join(record.getMessage() for record in caplog.records)),
        )
    )
    violations = [
        f"diagnostic:{source}:{category}"
        for source, text in sources
        for category, sentinel in sentinels.items()
        if sentinel and sentinel in text
    ]
    caplog.clear()
    return sorted(set(violations))


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _cell_bytes(value: Any) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    return None


def _scan_text_and_blob_cells(
    database_path: Path,
    sentinels: Mapping[str, str],
) -> tuple[set[tuple[str, str]], list[str]]:
    """Scan every declared TEXT/BLOB column without returning stored values."""

    scanned: set[tuple[str, str]] = set()
    violations: list[str] = []
    needles = {
        category: sentinel.encode("utf-8")
        for category, sentinel in sentinels.items()
        if sentinel
    }
    try:
        with sqlite3.connect(database_path) as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if tables != set(_TABLES):
                violations.append("schema:application-table-set")

            for table in _TABLES:
                if table not in tables:
                    continue
                columns = [
                    (str(row[1]), str(row[2]).upper())
                    for row in connection.execute(
                        f"PRAGMA table_info({_quote_identifier(table)})"
                    )
                ]
                for column, declared_type in columns:
                    if "TEXT" not in declared_type and "BLOB" not in declared_type:
                        continue
                    scanned.add((table, column))
                    query = (
                        f"SELECT {_quote_identifier(column)} "
                        f"FROM {_quote_identifier(table)}"
                    )
                    for row in connection.execute(query):
                        payload = _cell_bytes(row[0])
                        if payload is None:
                            continue
                        for category, needle in needles.items():
                            if needle in payload:
                                violations.append(
                                    f"sqlite:{table}.{column}:{category}"
                                )
    except sqlite3.Error as exc:
        violations.append(f"sqlite-scan:{type(exc).__name__}")

    for table in _TABLES:
        if not any(scanned_table == table for scanned_table, _ in scanned):
            violations.append(f"sqlite-scan:no-text-or-blob-column:{table}")
    return scanned, sorted(set(violations))


def _legal_metadata_violations(
    database_path: Path,
    state_api: Any,
    repo_root: Path,
    expected_missing_keys: set[str],
) -> list[str]:
    """Verify that required control metadata survived without echoing row data."""

    violations: list[str] = []
    try:
        with sqlite3.connect(database_path) as connection:
            connection.row_factory = sqlite3.Row
            execution = connection.execute(
                "SELECT * FROM executions WHERE execution_id = ?",
                ("execution-t34-security",),
            ).fetchone()
            workflow = connection.execute(
                "SELECT * FROM workflow_instances WHERE execution_id = ?",
                ("execution-t34-security",),
            ).fetchone()
            steps = connection.execute(
                "SELECT * FROM step_instances WHERE execution_id = ?",
                ("execution-t34-security",),
            ).fetchall()
    except sqlite3.Error as exc:
        return [f"metadata-read:{type(exc).__name__}"]

    if execution is None:
        violations.append("metadata:execution-row-missing")
    else:
        if execution["surface"] != "cli":
            violations.append("metadata:surface")
        if execution["plan_schema_version"] != state_api.SCHEMA_VERSION:
            violations.append("metadata:plan-schema-version")
        if execution["repo_key"] != state_api.compute_repo_key(repo_root):
            violations.append("metadata:repo-key")
        if re.fullmatch(r"[0-9a-f]{64}", execution["launch_plan_hash"]) is None:
            violations.append("metadata:launch-plan-hash")
        try:
            payload = json.loads(execution["plan_json"])
            stored = payload["instances"][0]
            stored_missing = set(stored["missing_replay_keys"])
            stored_argv = tuple(stored["argv"])
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            violations.append("metadata:plan-json-shape")
        else:
            if stored_missing != expected_missing_keys:
                violations.append("metadata:missing-replay-keys")
            if stored_argv != ("orchestrate", "--workflow", "aas"):
                violations.append("metadata:sanitized-replay-argv")

    if workflow is None:
        violations.append("metadata:workflow-row-missing")
    else:
        if workflow["workflow_id"] != "aas":
            violations.append("metadata:workflow-id")
        if workflow["status"] != "running":
            violations.append("metadata:workflow-status")
        if workflow["attempt_no"] != 1:
            violations.append("metadata:attempt-number")
        if workflow["lease_generation"] < 1:
            violations.append("metadata:lease-generation")
        if workflow["state_version"] < 2:
            violations.append("metadata:state-version")

    if len(steps) != 1:
        violations.append("metadata:step-row-count")
    elif steps[0]["record_kind"] != "step" or steps[0]["status"] != "running":
        violations.append("metadata:step-control-state")
    return violations


def _call_with_fallback(
    label: str,
    primary: Callable[[], Any],
    fallback: Callable[[], Any],
    rejection_types: tuple[type[BaseException], ...],
    exceptions: list[tuple[str, BaseException]],
    violations: list[str],
) -> Any | None:
    """Allow security rejection while keeping the remaining boundary test live."""

    try:
        return primary()
    except Exception as exc:  # deliberate safe capture of boundary diagnostics
        exceptions.append((label, exc))
        if not isinstance(exc, rejection_types):
            violations.append(f"unexpected-exception:{label}:{type(exc).__name__}")
        try:
            return fallback()
        except Exception as fallback_exc:  # deliberate safe capture
            exceptions.append((f"{label}-fallback", fallback_exc))
            violations.append(
                f"fallback-failed:{label}:{type(fallback_exc).__name__}"
            )
            return None


def _fail_if_violations(requirement: str, violations: Sequence[str]) -> None:
    if violations:
        pytest.fail(
            f"{requirement}: " + ", ".join(sorted(set(violations))),
            pytrace=False,
        )


class TestForbiddenStateValues:
    """NFR-SEC-01: forbidden plaintext never enters durable control state."""

    def test_registration_replay_and_transition_scan_all_text_blob_cells(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
        external_call_guard: list[str],
    ) -> None:
        resume_api, state_api = _apis("NFR-SEC-01 durable value boundary")
        repo_root = tmp_path / "private-repository"
        repo_root.mkdir()
        database_path = tmp_path / "state.sqlite3"
        sentinels = _sentinels(repo_root)
        expected_missing = {key for key, _, _ in _REPLAY_INPUTS}
        raw_argv = ["orchestrate", "--workflow", "aas"]
        replay_values: dict[str, str] = {}
        for key, flag, category in _REPLAY_INPUTS:
            raw_argv.extend((flag, sentinels[category]))
            replay_values[key] = sentinels[category]

        exceptions: list[tuple[str, BaseException]] = []
        violations: list[str] = []
        hash_payloads: list[str] = []
        registered = False

        with state_api.RunStateStore(database_path) as store:
            service = resume_api.ResumeService(store, repo_root)
            try:
                execution_id = service.register_execution(
                    "cli",
                    (_descriptor(resume_api, raw_argv),),
                    execution_id="execution-t34-security",
                    checkpoint_head="head-at-launch",
                )
                registered = True
            except Exception as exc:  # prevent forbidden values from traceback output
                exceptions.append(("registration", exc))
                violations.append(
                    f"registration-failed:{type(exc).__name__}"
                )

            if registered:
                original_hash = resume_api.compute_resume_plan_hash

                def capture_hash_payload(payload: Mapping[str, Any]) -> str:
                    hash_payloads.append(resume_api.canonical_json(payload))
                    return original_hash(payload)

                monkeypatch.setattr(
                    resume_api,
                    "compute_resume_plan_hash",
                    capture_hash_payload,
                )
                try:
                    plan = service.build_plan(
                        execution_id,
                        action="restart-step",
                        replay_values=replay_values,
                        current_head="head-at-launch",
                    )
                except Exception as exc:  # prevent forbidden values from traceback output
                    exceptions.append(("replay-plan", exc))
                    violations.append(
                        f"replay-plan-failed:{type(exc).__name__}"
                    )
                    plan = None

                if plan is not None:
                    transient_argv = "\0".join(plan.argv)
                    for category, sentinel in sentinels.items():
                        if sentinel not in transient_argv:
                            violations.append(
                                f"replay-input-not-exercised:{category}"
                            )
                    if not hash_payloads:
                        violations.append("resume-hash-payload:not-observed")
                    else:
                        for category, sentinel in sentinels.items():
                            if any(sentinel in payload for payload in hash_payloads):
                                violations.append(
                                    f"resume-hash-payload:{category}"
                                )

                    rejection_types = (state_api.DurableStateError, ValueError)
                    token = _call_with_fallback(
                        "lease-owner",
                        lambda: service.acquire(plan, sentinels["token"]),
                        lambda: service.acquire(plan, "resume-owner"),
                        rejection_types,
                        exceptions,
                        violations,
                    )
                    if token is not None:
                        workflow_token = _call_with_fallback(
                            "workflow-transition",
                            lambda: store.transition_workflow(
                                token,
                                "running",
                                run_id=sentinels["environment"],
                                checkpoint_head=sentinels["raw_repository_path"],
                            ),
                            lambda: store.transition_workflow(
                                token,
                                "running",
                                run_id="run-1",
                                checkpoint_head="head-at-launch",
                            ),
                            rejection_types,
                            exceptions,
                            violations,
                        )
                    else:
                        workflow_token = None

                    if workflow_token is not None:
                        combined_error = "|".join(
                            (
                                sentinels["response"],
                                sentinels["credential"],
                                sentinels["auth_url"],
                            )
                        )
                        _call_with_fallback(
                            "step-transition",
                            lambda: store.transition_step(
                                workflow_token,
                                sentinels["tool_results"],
                                "running",
                                phase=sentinels["prompt"],
                                phase_state=sentinels["reasoning"],
                                session_id=sentinels["tool_args"],
                                last_error_type=combined_error,
                            ),
                            lambda: store.transition_step(
                                workflow_token,
                                "1",
                                "running",
                                phase="main",
                                phase_state="started",
                                session_id="session-1",
                                last_error_type="RuntimeError",
                            ),
                            rejection_types,
                            exceptions,
                            violations,
                        )

        if registered:
            violations.extend(
                _legal_metadata_violations(
                    database_path,
                    state_api,
                    repo_root,
                    expected_missing,
                )
            )
            scanned, scan_violations = _scan_text_and_blob_cells(
                database_path,
                sentinels,
            )
            if not scanned:
                violations.append("sqlite-scan:no-columns")
            violations.extend(scan_violations)
        violations.extend(
            _diagnostic_violations(sentinels, exceptions, capsys, caplog)
        )
        if external_call_guard:
            violations.append("external-call:unexpected")
        _fail_if_violations("NFR-SEC-01 durable value boundary", violations)


class TestMissingReplayValues:
    """NFR-SEC-01/FR-CLI-90: unsafe replay values are key-only or rejected."""

    @pytest.mark.parametrize(
        ("case_name", "flag", "category", "expected_key"),
        _SANITIZE_CASES,
        ids=[case[0] for case in _SANITIZE_CASES],
    )
    def test_sanitize_argv_omits_sensitive_value_or_rejects_it(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
        case_name: str,
        flag: str,
        category: str,
        expected_key: str,
    ) -> None:
        resume_api, state_api = _apis("NFR-SEC-01 replay sanitization")
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        sentinels = _sentinels(repo_root)
        service = resume_api.ResumeService(object(), repo_root)
        exceptions: list[tuple[str, BaseException]] = []
        violations: list[str] = []

        try:
            safe_argv, missing = service.sanitize_argv(
                ("orchestrate", "--workflow", "aas", flag, sentinels[category])
            )
        except Exception as exc:  # rejection is an allowed security outcome
            exceptions.append((f"sanitize-{case_name}", exc))
            if not isinstance(exc, (state_api.DurableStateError, ValueError)):
                violations.append(
                    f"sanitize:{case_name}:unexpected-{type(exc).__name__}"
                )
        else:
            serialized = resume_api.canonical_json(
                {"argv": list(safe_argv), "missing_replay_keys": list(missing)}
            )
            if sentinels[category] in serialized:
                violations.append(f"sanitize:{case_name}:plaintext-returned")
            if expected_key not in missing:
                violations.append(f"sanitize:{case_name}:missing-key-absent")

        violations.extend(
            _diagnostic_violations(sentinels, exceptions, capsys, caplog)
        )
        _fail_if_violations("NFR-SEC-01 replay sanitization", violations)

    def test_key_only_gap_is_persisted_and_blocks_acquire_without_reentry(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
        external_call_guard: list[str],
    ) -> None:
        resume_api, state_api = _apis("FR-CLI-90 missing replay value")
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        database_path = tmp_path / "state.sqlite3"
        sentinels = _sentinels(repo_root)
        exceptions: list[tuple[str, BaseException]] = []
        violations: list[str] = []

        with state_api.RunStateStore(database_path) as store:
            service = resume_api.ResumeService(store, repo_root)
            execution_id = service.register_execution(
                "cli",
                (
                    _descriptor(
                        resume_api,
                        (
                            "orchestrate",
                            "--workflow",
                            "aas",
                            "--additional-prompt",
                            sentinels["prompt"],
                        ),
                    ),
                ),
                execution_id="execution-missing-replay",
                checkpoint_head="head-at-launch",
            )
            plan = service.build_plan(
                execution_id,
                current_head="head-at-launch",
            )
            if plan.missing_replay_keys != ("additional_prompt",):
                violations.append("missing-replay:incorrect-key-set")
            if "missing_replay_value" not in plan.risk_reasons:
                violations.append("missing-replay:risk-absent")
            if any(
                sentinels["prompt"] in argument
                for argument in plan.argv
            ):
                violations.append("missing-replay:plaintext-in-plan")
            try:
                service.acquire(plan, "resume-owner")
            except Exception as exc:  # fail-closed is required here
                exceptions.append(("missing-replay-acquire", exc))
                if not isinstance(exc, state_api.DurableStateError):
                    violations.append(
                        f"missing-replay:unexpected-{type(exc).__name__}"
                    )
            else:
                violations.append("missing-replay:lease-acquired")

        _, scan_violations = _scan_text_and_blob_cells(database_path, sentinels)
        violations.extend(scan_violations)
        violations.extend(
            _diagnostic_violations(sentinels, exceptions, capsys, caplog)
        )
        if external_call_guard:
            violations.append("external-call:unexpected")
        _fail_if_violations("FR-CLI-90 missing replay value", violations)


class TestStateIntegrity:
    """FR-STATE-04: integrity failures preserve evidence and fail closed."""

    def test_corrupt_database_preserves_exact_bytes_and_diagnostics_are_safe(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _, state_api = _apis("FR-STATE-04 corrupt database")
        database_path = tmp_path / "state.sqlite3"
        sentinels = _sentinels(tmp_path / "repo")
        original = (
            b"not-a-sqlite-database\x00"
            + sentinels["tool_results"].encode("utf-8")
        )
        database_path.write_bytes(original)
        exceptions: list[tuple[str, BaseException]] = []
        violations: list[str] = []

        try:
            with state_api.RunStateStore(database_path):
                pass
        except Exception as exc:  # expected fail-closed outcome
            exceptions.append(("corrupt-open", exc))
            if not isinstance(exc, state_api.DurableStateError):
                violations.append(f"corrupt:unexpected-{type(exc).__name__}")
        else:
            violations.append("corrupt:open-succeeded")

        if not database_path.exists():
            violations.append("corrupt:file-deleted")
        elif database_path.read_bytes() != original:
            violations.append("corrupt:bytes-changed")
        violations.extend(
            _diagnostic_violations(sentinels, exceptions, capsys, caplog)
        )
        _fail_if_violations("FR-STATE-04 corrupt database", violations)

    def test_unknown_schema_preserves_bytes_table_version_and_value(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _, state_api = _apis("FR-STATE-04 unknown schema")
        database_path = tmp_path / "state.sqlite3"
        sentinels = _sentinels(tmp_path / "repo")
        unknown_version = state_api.SCHEMA_VERSION + 17
        with sqlite3.connect(database_path) as connection:
            connection.execute("CREATE TABLE preserved_evidence(value TEXT NOT NULL)")
            connection.execute(
                "INSERT INTO preserved_evidence VALUES (?)",
                (sentinels["response"],),
            )
            connection.execute(f"PRAGMA user_version = {unknown_version}")
        original_bytes = database_path.read_bytes()
        exceptions: list[tuple[str, BaseException]] = []
        violations: list[str] = []

        try:
            with state_api.RunStateStore(database_path):
                pass
        except Exception as exc:  # expected fail-closed outcome
            exceptions.append(("unknown-schema-open", exc))
            if not isinstance(exc, state_api.DurableStateError):
                violations.append(
                    f"unknown-schema:unexpected-{type(exc).__name__}"
                )
        else:
            violations.append("unknown-schema:open-succeeded")

        if not database_path.exists():
            violations.append("unknown-schema:file-deleted")
        elif database_path.read_bytes() != original_bytes:
            violations.append("unknown-schema:bytes-changed")
        try:
            with sqlite3.connect(database_path) as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_schema "
                        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                    )
                }
                value = connection.execute(
                    "SELECT value FROM preserved_evidence"
                ).fetchone()
        except sqlite3.Error as exc:
            violations.append(f"unknown-schema:read-{type(exc).__name__}")
        else:
            if version != unknown_version:
                violations.append("unknown-schema:version-changed")
            if tables != {"preserved_evidence"}:
                violations.append("unknown-schema:tables-changed")
            if value is None or value[0] != sentinels["response"]:
                violations.append("unknown-schema:value-changed")
        violations.extend(
            _diagnostic_violations(sentinels, exceptions, capsys, caplog)
        )
        _fail_if_violations("FR-STATE-04 unknown schema", violations)

    def test_candidate_quick_check_failure_returns_no_candidates(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        resume_api, state_api = _apis("FR-STATE-04 candidate quick_check")
        repo_root = tmp_path / "private-repository"
        repo_root.mkdir()
        database_path = tmp_path / "state.sqlite3"
        sentinels = _sentinels(repo_root)
        exceptions: list[tuple[str, BaseException]] = []
        violations: list[str] = []

        with state_api.RunStateStore(database_path) as store:
            service = resume_api.ResumeService(store, repo_root)
            service.register_execution(
                "cli",
                (
                    _descriptor(
                        resume_api,
                        ("orchestrate", "--workflow", "aas"),
                    ),
                ),
                execution_id="execution-quick-check",
            )
            quick_check_calls: list[bool] = []

            def failed_quick_check() -> bool:
                quick_check_calls.append(True)
                return False

            monkeypatch.setattr(store, "quick_check", failed_quick_check)
            try:
                service.list_candidates()
            except Exception as exc:  # expected fail-closed outcome
                exceptions.append(("candidate-list", exc))
                if not isinstance(exc, state_api.DurableStateError):
                    violations.append(
                        f"candidate:unexpected-{type(exc).__name__}"
                    )
            else:
                violations.append("candidate:list-succeeded")
            if quick_check_calls != [True]:
                violations.append("candidate:quick-check-count")

        violations.extend(
            _diagnostic_violations(sentinels, exceptions, capsys, caplog)
        )
        _fail_if_violations("FR-STATE-04 candidate quick_check", violations)


class TestStatePermissions:
    """FR-STATE-04: private POSIX modes without a Windows ACL claim."""

    @pytest.mark.skipif(
        os.name == "nt",
        reason="POSIX 0700/0600 only; Windows ACL hardening is not asserted",
    )
    def test_posix_directory_and_database_modes_are_private(
        self,
        tmp_path: Path,
    ) -> None:
        _, state_api = _apis("FR-STATE-04 POSIX state permissions")
        state_directory = tmp_path / "state"
        database_path = state_directory / "state.sqlite3"

        with state_api.RunStateStore(database_path):
            pass

        assert stat.S_IMODE(state_directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(database_path.stat().st_mode) == 0o600