"""RED contracts for the durable SQLite run-state store.

Traceability: FR-STATE-04, FR-STATE-05, NFR-REL-03, NFR-CONC-02.
The production module is imported inside each test so a missing implementation
produces named failures instead of aborting test collection.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time
from typing import Any

import pytest


_MODULE_NAME = "hve.run_state_store"
_REQUIRED_API = (
    "SCHEMA_VERSION",
    "HEARTBEAT_INTERVAL_SECONDS",
    "LEASE_TTL_SECONDS",
    "BUSY_TIMEOUT_SECONDS",
    "DurableStateError",
    "LeaseToken",
    "RunStateStore",
    "HeartbeatWorker",
    "default_state_path",
    "compute_repo_key",
)
_REAL_MONOTONIC = time.monotonic


def _api(requirement: str) -> Any:
    try:
        module = importlib.import_module(_MODULE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name == _MODULE_NAME:
            pytest.fail(
                f"{requirement}: missing production module {_MODULE_NAME}",
                pytrace=False,
            )
        raise

    missing = [name for name in _REQUIRED_API if not hasattr(module, name)]
    if missing:
        pytest.fail(
            f"{requirement}: {_MODULE_NAME} is missing API: {', '.join(missing)}",
            pytrace=False,
        )
    if not issubclass(module.DurableStateError, RuntimeError):
        pytest.fail(
            f"{requirement}: DurableStateError must derive from RuntimeError",
            pytrace=False,
        )
    return module


def _owned_connection(store: Any) -> sqlite3.Connection:
    state = getattr(store, "__dict__", {})
    connections = [
        value for value in state.values() if isinstance(value, sqlite3.Connection)
    ]
    if len(connections) != 1:
        pytest.fail(
            "RunStateStore must own exactly one inspectable sqlite3.Connection; "
            f"found {len(connections)}",
        )
    return connections[0]


def _row_value(row: Any, name: str) -> Any:
    try:
        return row[name]
    except (IndexError, KeyError, TypeError):
        return getattr(row, name)


def _instance(
    instance_id: str = "ard-1",
    *,
    workflow_id: str = "ard",
    ordinal: int = 0,
) -> dict[str, Any]:
    return {
        "instance_id": instance_id,
        "workflow_id": workflow_id,
        "ordinal": ordinal,
        "mode": "standard",
        "argv": ["--workflow", workflow_id],
        "missing_replay_keys": [],
    }


def _register(
    store: Any,
    *,
    execution_id: str = "exec-1",
    repo_key: str = "a" * 64,
    instances: list[dict[str, Any]] | None = None,
) -> None:
    registered_instances = instances or [_instance()]
    plan_json = json.dumps(
        {"instances": registered_instances},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    store.register_execution(
        execution_id,
        repo_key,
        "cli",
        "b" * 64,
        plan_json,
        registered_instances,
    )


def _state_version(store: Any, execution_id: str = "exec-1") -> int:
    row = store.get_instance(execution_id, "ard-1")
    assert row is not None
    value = _row_value(row, "state_version")
    assert isinstance(value, int) and not isinstance(value, bool)
    return value


def _lease_token(api: Any) -> Any:
    return api.LeaseToken(
        execution_id="exec-1",
        instance_id="ard-1",
        owner="owner-a",
        generation=1,
        state_version=0,
    )


class TestStoreBootstrap:
    """FR-STATE-04: path, privacy, schema, PRAGMA, and permissions."""

    def test_default_path_is_platformdirs_user_state_database(self) -> None:
        api = _api("FR-STATE-04 default user-state path")
        from platformdirs import user_state_path

        expected = Path(user_state_path("hve", appauthor=False)) / "state.sqlite3"

        actual = Path(api.default_state_path())

        assert actual == expected
        assert actual.name == "state.sqlite3"

    def test_repo_key_is_stable_sha256_without_raw_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _api("FR-STATE-04 normalized repository key")
        repo_root = tmp_path / "Repo"
        repo_root.mkdir()
        monkeypatch.chdir(tmp_path)

        absolute_key = api.compute_repo_key(repo_root.resolve())
        relative_key = api.compute_repo_key(Path("Repo"))

        assert absolute_key == relative_key
        assert re.fullmatch(r"[0-9a-f]{64}", absolute_key)
        assert str(repo_root.resolve()).casefold() not in absolute_key.casefold()

    def test_bootstrap_creates_exactly_three_tables_and_schema_v1(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-04 three-table schema")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path):
            pass

        with sqlite3.connect(database_path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            user_version = connection.execute("PRAGMA user_version").fetchone()[0]

        assert api.SCHEMA_VERSION == 1
        assert user_version == api.SCHEMA_VERSION
        assert tables == {"executions", "workflow_instances", "step_instances"}

    def test_schema_has_declared_primary_and_foreign_keys(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-04 declared table keys")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path):
            pass

        expected_columns = {
            "executions": {
                "execution_id", "repo_key", "surface", "plan_schema_version",
                "launch_plan_hash", "plan_json", "created_at", "updated_at",
            },
            "workflow_instances": {
                "execution_id", "instance_id", "workflow_id", "ordinal", "mode",
                "status", "state_version", "heartbeat_at", "checkpoint_head",
                "current_run_id", "attempt_no", "lease_owner", "lease_generation",
                "lease_expires_at",
            },
            "step_instances": {
                "execution_id", "instance_id", "step_id", "record_kind", "status",
                "phase", "phase_state", "session_id", "state_version", "updated_at",
                "last_error_type",
            },
        }
        expected_primary_keys = {
            "executions": ("execution_id",),
            "workflow_instances": ("execution_id", "instance_id"),
            "step_instances": ("execution_id", "instance_id", "step_id"),
        }
        with sqlite3.connect(database_path) as connection:
            for table, columns in expected_columns.items():
                info = connection.execute(f"PRAGMA table_info({table})").fetchall()
                assert {row[1] for row in info} == columns
                primary_key = tuple(
                    row[1] for row in sorted(info, key=lambda row: row[5]) if row[5]
                )
                assert primary_key == expected_primary_keys[table]

            workflow_foreign_keys = connection.execute(
                "PRAGMA foreign_key_list(workflow_instances)"
            ).fetchall()
            step_foreign_keys = connection.execute(
                "PRAGMA foreign_key_list(step_instances)"
            ).fetchall()

        assert {(row[2], row[3], row[4]) for row in workflow_foreign_keys} == {
            ("executions", "execution_id", "execution_id"),
        }
        assert {(row[2], row[3], row[4]) for row in step_foreign_keys} == {
            ("workflow_instances", "execution_id", "execution_id"),
            ("workflow_instances", "instance_id", "instance_id"),
        }

    def test_store_connection_applies_required_effective_pragmas(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-04 effective SQLite PRAGMAs")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path) as store:
            connection = _owned_connection(store)
            actual = {
                name: connection.execute(f"PRAGMA {name}").fetchone()[0]
                for name in (
                    "journal_mode",
                    "synchronous",
                    "foreign_keys",
                    "trusted_schema",
                    "busy_timeout",
                )
            }

        assert api.BUSY_TIMEOUT_SECONDS == 1.0
        assert str(actual["journal_mode"]).casefold() == "delete"
        assert actual["synchronous"] == 3  # SQLite EXTRA
        assert actual["foreign_keys"] == 1
        assert actual["trusted_schema"] == 0
        assert actual["busy_timeout"] == 1_000

    def test_raw_repository_path_is_rejected_as_repo_key_and_not_persisted(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-04 raw repository path exclusion")
        database_path = tmp_path / "state.sqlite3"
        repo_root = tmp_path / "private-repository"
        repo_root.mkdir()

        with api.RunStateStore(database_path) as store:
            with pytest.raises(api.DurableStateError):
                _register(store, repo_key=str(repo_root.resolve()))

            connection = _owned_connection(store)
            execution_count = connection.execute(
                "SELECT COUNT(*) FROM executions"
            ).fetchone()[0]
            execution_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(executions)")
            }

        assert execution_count == 0
        assert "repo_key" in execution_columns
        assert not {
            "repo_root",
            "repository_root",
            "repo_path",
            "repository_path",
        }.intersection(execution_columns)

    @pytest.mark.skipif(os.name == "nt", reason="POSIX file modes do not apply on Windows")
    def test_posix_state_directory_and_database_are_private(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-04 POSIX state permissions")
        state_directory = tmp_path / "state"
        database_path = state_directory / "state.sqlite3"

        with api.RunStateStore(database_path):
            pass

        assert stat.S_IMODE(state_directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(database_path.stat().st_mode) == 0o600


class TestStoreIntegrity:
    """FR-STATE-04/05: fail-closed integrity and transaction boundaries."""

    def test_unknown_schema_fails_closed_without_delete_or_repair(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-04 unknown schema fail-closed")
        database_path = tmp_path / "state.sqlite3"
        unknown_version = api.SCHEMA_VERSION + 1
        with sqlite3.connect(database_path) as connection:
            connection.execute("CREATE TABLE sentinel(value TEXT NOT NULL)")
            connection.execute("INSERT INTO sentinel VALUES ('keep-me')")
            connection.execute(f"PRAGMA user_version = {unknown_version}")

        with pytest.raises(api.DurableStateError):
            with api.RunStateStore(database_path):
                pass

        assert database_path.exists()
        with sqlite3.connect(database_path) as connection:
            version_after = connection.execute("PRAGMA user_version").fetchone()[0]
            sentinel_after = connection.execute(
                "SELECT value FROM sentinel"
            ).fetchall()
            tables_after = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }

        assert version_after == unknown_version
        assert sentinel_after == [("keep-me",)]
        assert tables_after == {"sentinel"}

    def test_corrupt_database_fails_closed_without_delete_or_repair(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-04 corrupt database fail-closed")
        database_path = tmp_path / "state.sqlite3"
        corrupt_bytes = b"not-a-sqlite-database\x00keep-this-evidence"
        database_path.write_bytes(corrupt_bytes)

        with pytest.raises(api.DurableStateError):
            with api.RunStateStore(database_path):
                pass

        assert database_path.exists()
        assert database_path.read_bytes() == corrupt_bytes

    def test_candidate_read_runs_quick_check_and_rejects_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _api("FR-STATE-04 candidate quick_check")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path) as store:
            _register(store)
            checked: list[Any] = []

            def failed_quick_check(current_store: Any) -> bool:
                checked.append(current_store)
                return False

            monkeypatch.setattr(
                api.RunStateStore, "quick_check", failed_quick_check
            )

            with pytest.raises(api.DurableStateError):
                store.list_candidates("a" * 64)

        assert checked == [store]

    def test_register_execution_rolls_back_all_rows_on_instance_failure(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-05 atomic execution registration")
        database_path = tmp_path / "state.sqlite3"
        duplicate_instances = [
            _instance("duplicate", ordinal=0),
            _instance("duplicate", workflow_id="aas", ordinal=1),
        ]

        with api.RunStateStore(database_path) as store:
            with pytest.raises(api.DurableStateError):
                _register(store, instances=duplicate_instances)

            connection = _owned_connection(store)
            counts = {
                table: connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in (
                    "executions",
                    "workflow_instances",
                    "step_instances",
                )
            }

        assert counts == {
            "executions": 0,
            "workflow_instances": 0,
            "step_instances": 0,
        }

    def test_low_level_registration_rejects_sensitive_descriptor_values(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-SEC-01 low-level durable persistence boundary")
        database_path = tmp_path / "state.sqlite3"
        instance = _instance()
        instance["argv"] = [
            "orchestrate",
            "--workflow",
            "ard",
            "--additional-prompt",
            "token=DO-NOT-PERSIST",
        ]
        plan_json = json.dumps({"instances": [instance]})

        with api.RunStateStore(database_path) as store:
            with pytest.raises(api.DurableStateError):
                store.register_execution(
                    "exec-sensitive",
                    "a" * 64,
                    "cli",
                    "b" * 64,
                    plan_json,
                    [instance],
                )

            connection = _owned_connection(store)
            assert connection.execute(
                "SELECT COUNT(*) FROM executions"
            ).fetchone()[0] == 0

    def test_low_level_registration_rejects_embedded_data_uri(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-SEC-01 embedded URI persistence boundary")
        database_path = tmp_path / "state.sqlite3"
        instance = _instance()
        instance["argv"] = [
            "orchestrate",
            "--workflow",
            "ard",
            "--model",
            "data:text/plain;base64,U0VDUkVU",
        ]
        plan_json = json.dumps({"instances": [instance]})

        with api.RunStateStore(database_path) as store:
            with pytest.raises(api.DurableStateError):
                store.register_execution(
                    "exec-data-uri",
                    "a" * 64,
                    "cli",
                    "b" * 64,
                    plan_json,
                    [instance],
                )

    def test_low_level_registration_rejects_unknown_surface(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-05 canonical registration boundary")
        database_path = tmp_path / "state.sqlite3"
        instances = [_instance("ard-1", ordinal=0)]
        plan_json = json.dumps({"instances": instances})

        with api.RunStateStore(database_path) as store:
            with pytest.raises(api.DurableStateError):
                store.register_execution(
                    "exec-gap",
                    "a" * 64,
                    "unknown-surface",
                    "b" * 64,
                    plan_json,
                    instances,
                )

            connection = _owned_connection(store)
            assert connection.execute(
                "SELECT COUNT(*) FROM executions"
            ).fetchone()[0] == 0

    def test_low_level_registration_rejects_ordinal_gaps(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-05 contiguous workflow order")
        database_path = tmp_path / "state.sqlite3"
        instances = [
            _instance("ard-1", ordinal=0),
            _instance("aas-1", workflow_id="aas", ordinal=2),
        ]
        plan_json = json.dumps({"instances": instances})

        with api.RunStateStore(database_path) as store:
            with pytest.raises(api.DurableStateError):
                store.register_execution(
                    "exec-gap",
                    "a" * 64,
                    "cli",
                    "b" * 64,
                    plan_json,
                    instances,
                )

            connection = _owned_connection(store)
            assert connection.execute(
                "SELECT COUNT(*) FROM executions"
            ).fetchone()[0] == 0

    def test_candidates_are_returned_newest_updated_first(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-CLI-90 latest candidate ordering")
        database_path = tmp_path / "state.sqlite3"
        repo_key = "a" * 64

        with api.RunStateStore(database_path) as store:
            _register(store, execution_id="execution-old", repo_key=repo_key)
            _register(store, execution_id="execution-new", repo_key=repo_key)
            connection = _owned_connection(store)
            connection.execute(
                "UPDATE executions SET updated_at = ? WHERE execution_id = ?",
                ("2026-08-28T01:00:00+00:00", "execution-old"),
            )
            connection.execute(
                "UPDATE executions SET updated_at = ? WHERE execution_id = ?",
                ("2026-08-28T02:00:00+00:00", "execution-new"),
            )
            connection.commit()

            candidates = store.list_candidates(repo_key)

        assert [_row_value(row, "execution_id") for row in candidates] == [
            "execution-new",
            "execution-old",
        ]

    def test_context_exit_preserves_body_error_when_close_also_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _api("FR-STATE-04 context cleanup failure ordering")
        store = api.RunStateStore(tmp_path / "state.sqlite3")
        connection = _owned_connection(store)

        def failed_close() -> None:
            raise api.DurableStateError("injected close failure")

        monkeypatch.setattr(store, "close", failed_close)
        try:
            with pytest.raises(ValueError, match="body failure") as captured:
                with store:
                    raise ValueError("body failure")
        finally:
            connection.close()

        assert any(
            "injected close failure" in note
            for note in getattr(captured.value, "__notes__", ())
        )


class TestLeaseAndCas:
    """NFR-CONC-02: BEGIN IMMEDIATE, state CAS, TTL, and fencing."""

    def test_acquire_lease_uses_begin_immediate_and_expected_version_cas(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-CONC-02 lease acquisition CAS")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path) as store:
            _register(store)
            expected_version = _state_version(store)

            with pytest.raises(api.DurableStateError):
                store.acquire_lease(
                    "exec-1",
                    "ard-1",
                    expected_version + 1,
                    "owner-a",
                    now=100.0,
                )

            statements: list[str] = []
            connection = _owned_connection(store)
            connection.set_trace_callback(statements.append)
            try:
                token = store.acquire_lease(
                    "exec-1",
                    "ard-1",
                    expected_version,
                    "owner-a",
                    now=100.0,
                )
            finally:
                connection.set_trace_callback(None)

            store.release_lease(token, now=101.0)

        normalized = {" ".join(statement.upper().split()) for statement in statements}
        assert any(statement.startswith("BEGIN IMMEDIATE") for statement in normalized)
        assert token.execution_id == "exec-1"
        assert token.instance_id == "ard-1"
        assert token.owner == "owner-a"

    def test_lease_ttl_requires_explicit_takeover_and_increments_generation(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-CONC-02 lease TTL and explicit takeover")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path) as first, api.RunStateStore(
            database_path
        ) as second:
            _register(first)
            expected_version = _state_version(first)
            first_token = first.acquire_lease(
                "exec-1",
                "ard-1",
                expected_version,
                "owner-a",
                now=100.0,
            )

            with pytest.raises(api.DurableStateError):
                second.acquire_lease(
                    "exec-1",
                    "ard-1",
                    first_token.state_version,
                    "owner-b",
                    now=119.999,
                    allow_takeover=True,
                )
            with pytest.raises(api.DurableStateError):
                second.acquire_lease(
                    "exec-1",
                    "ard-1",
                    first_token.state_version,
                    "owner-b",
                    now=120.0,
                    allow_takeover=False,
                )

            second_token = second.acquire_lease(
                "exec-1",
                "ard-1",
                first_token.state_version,
                "owner-b",
                now=120.0,
                allow_takeover=True,
            )
            second.release_lease(second_token, now=121.0)

        assert api.LEASE_TTL_SECONDS == 20.0
        assert second_token.owner == "owner-b"
        assert second_token.generation == first_token.generation + 1
        assert second_token.generation > 1

    def test_old_generation_and_wrong_owner_cannot_write_after_takeover(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-CONC-02 fenced owner and generation")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path) as first, api.RunStateStore(
            database_path
        ) as second:
            _register(first)
            old_token = first.acquire_lease(
                "exec-1",
                "ard-1",
                _state_version(first),
                "shared-owner",
                now=100.0,
            )
            current_token = second.acquire_lease(
                "exec-1",
                "ard-1",
                old_token.state_version,
                "shared-owner",
                now=121.0,
                allow_takeover=True,
            )
            wrong_owner = dataclasses.replace(current_token, owner="wrong-owner")

            with pytest.raises(api.DurableStateError):
                first.heartbeat(old_token, now=122.0)
            with pytest.raises(api.DurableStateError):
                first.transition_workflow(old_token, "running")
            with pytest.raises(api.DurableStateError):
                first.transition_step(old_token, "1.1", "running")
            with pytest.raises(api.DurableStateError):
                second.heartbeat(wrong_owner, now=122.0)

            second.heartbeat(current_token, now=122.0)
            second.release_lease(current_token, now=123.0)

    def test_transitions_increment_state_version_and_reject_stale_token(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-CONC-02 transition state_version CAS")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path) as store:
            _register(store)
            token = store.acquire_lease(
                "exec-1",
                "ard-1",
                _state_version(store),
                "owner-a",
                now=time.time(),
            )
            workflow_token = store.transition_workflow(token, "running")

            with pytest.raises(api.DurableStateError):
                store.transition_step(token, "1.1", "running")
            assert store.list_steps("exec-1", "ard-1") == []

            step_token = store.transition_step(
                workflow_token,
                "1.1",
                "running",
                phase="main",
                phase_state="started",
            )
            steps = store.list_steps("exec-1", "ard-1")
            store.release_lease(step_token)

        assert workflow_token.state_version == token.state_version + 1
        assert step_token.state_version == workflow_token.state_version + 1
        assert len(steps) == 1
        assert _row_value(steps[0], "step_id") == "1.1"
        assert _row_value(steps[0], "status") == "running"

    def test_status_only_transition_preserves_committed_main_checkpoint(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-CLI-90 persisted Main checkpoint survives DAG callbacks")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path) as store:
            _register(store)
            token = store.acquire_lease(
                "exec-1",
                "ard-1",
                _state_version(store),
                "owner-a",
                now=time.time(),
            )
            token = store.transition_step(
                token,
                "1",
                "running",
                phase="main",
                phase_state="running",
                session_id="session_main_1",
            )

            token = store.transition_step(token, "1", "running")
            token = store.transition_step(
                token,
                "1",
                "failed",
                last_error_type="StepExecutionError",
            )
            step = store.list_steps("exec-1", "ard-1")[0]
            store.release_lease(token)

        assert _row_value(step, "status") == "failed"
        assert _row_value(step, "phase") == "main"
        assert _row_value(step, "phase_state") == "running"
        assert _row_value(step, "session_id") == "session_main_1"
        assert _row_value(step, "last_error_type") == "StepExecutionError"

    def test_acquisition_token_can_heartbeat_and_release_after_state_transition(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-CONC-02 owner-generation heartbeat and release fencing")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path) as store:
            _register(store)
            acquired = store.acquire_lease(
                "exec-1",
                "ard-1",
                _state_version(store),
                "owner-a",
                now=time.time(),
            )
            transitioned = store.transition_workflow(acquired, "running")
            after_transition = store.get_instance("exec-1", "ard-1")
            heartbeat_at = float(_row_value(after_transition, "heartbeat_at")) + 1.0

            store.heartbeat(acquired, now=heartbeat_at)
            store.release_lease(acquired)
            instance = store.get_instance("exec-1", "ard-1")

        assert transitioned.state_version == acquired.state_version + 1
        assert _row_value(instance, "state_version") == transitioned.state_version
        assert _row_value(instance, "heartbeat_at") == heartbeat_at
        assert _row_value(instance, "lease_owner") is None

    def test_heartbeat_never_moves_lease_time_backward(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-CONC-02 non-decreasing lease timestamps")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path) as store:
            _register(store)
            token = store.acquire_lease(
                "exec-1",
                "ard-1",
                _state_version(store),
                "owner-a",
                now=100.0,
            )
            store.heartbeat(token, now=110.0)
            after_forward = store.get_instance("exec-1", "ard-1")
            forward_heartbeat = _row_value(after_forward, "heartbeat_at")
            forward_expiry = _row_value(after_forward, "lease_expires_at")

            store.heartbeat(token, now=90.0)
            after_backward = store.get_instance("exec-1", "ard-1")
            store.release_lease(token, now=111.0)

        assert _row_value(after_backward, "heartbeat_at") == forward_heartbeat
        assert _row_value(after_backward, "lease_expires_at") == forward_expiry

    def test_live_owner_heartbeat_renews_the_twenty_second_lease(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-CONC-02 live-owner sliding lease renewal")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path) as first, api.RunStateStore(
            database_path
        ) as second:
            _register(first)
            token = first.acquire_lease(
                "exec-1", "ard-1", 0, "owner-a", now=100.0
            )
            first.heartbeat(token, now=110.0)
            renewed = first.get_instance("exec-1", "ard-1")

            with pytest.raises(api.DurableStateError):
                second.acquire_lease(
                    "exec-1",
                    "ard-1",
                    token.state_version,
                    "owner-b",
                    now=129.999,
                    allow_takeover=True,
                )
            takeover = second.acquire_lease(
                "exec-1",
                "ard-1",
                token.state_version,
                "owner-b",
                now=130.0,
                allow_takeover=True,
            )
            second.release_lease(takeover, now=131.0)

        assert _row_value(renewed, "heartbeat_at") == 110.0
        assert _row_value(renewed, "lease_expires_at") == 130.0

    def test_expired_owner_cannot_heartbeat_itself_back_to_life(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-CONC-02 expired heartbeat fencing")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path) as store:
            _register(store)
            token = store.acquire_lease(
                "exec-1",
                "ard-1",
                _state_version(store),
                "owner-a",
                now=100.0,
            )

            with pytest.raises(api.DurableStateError):
                store.heartbeat(token, now=120.0)

            instance = store.get_instance("exec-1", "ard-1")
            with pytest.raises(api.DurableStateError):
                store.release_lease(token, now=120.0)

        assert _row_value(instance, "heartbeat_at") == 100.0
        assert _row_value(instance, "lease_expires_at") == 120.0

    def test_expired_owner_cannot_release_away_the_takeover_requirement(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _api("NFR-CONC-02 expired release fencing")
        database_path = tmp_path / "state.sqlite3"

        with api.RunStateStore(database_path) as store:
            _register(store)
            token = store.acquire_lease(
                "exec-1",
                "ard-1",
                _state_version(store),
                "owner-a",
                now=100.0,
            )
            original_clock = api._clock_value
            monkeypatch.setattr(
                api,
                "_clock_value",
                lambda now: 120.0 if now is None else original_clock(now),
            )

            with pytest.raises(api.DurableStateError):
                store.release_lease(token)
            with pytest.raises(api.DurableStateError):
                store.acquire_lease(
                    "exec-1",
                    "ard-1",
                    token.state_version,
                    "owner-b",
                    now=120.0,
                    allow_takeover=False,
                )

            takeover = store.acquire_lease(
                "exec-1",
                "ard-1",
                token.state_version,
                "owner-b",
                now=120.0,
                allow_takeover=True,
            )
            store.release_lease(takeover, now=121.0)

    def test_expired_owner_cannot_commit_workflow_or_step_transitions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _api("NFR-CONC-02 expired transition fencing")
        database_path = tmp_path / "state.sqlite3"
        instances = [
            _instance("ard-1", ordinal=0),
            _instance("aas-1", workflow_id="aas", ordinal=1),
        ]

        with api.RunStateStore(database_path) as store:
            _register(store, instances=instances)
            workflow_token = store.acquire_lease(
                "exec-1", "ard-1", 0, "owner-workflow", now=100.0
            )
            step_token = store.acquire_lease(
                "exec-1", "aas-1", 0, "owner-step", now=100.0
            )
            original_clock = api._clock_value
            monkeypatch.setattr(
                api,
                "_clock_value",
                lambda now: 120.0 if now is None else original_clock(now),
            )

            with pytest.raises(api.DurableStateError):
                store.transition_workflow(workflow_token, "running")
            with pytest.raises(api.DurableStateError):
                store.transition_step(step_token, "1", "running")

            assert store.list_steps("exec-1", "aas-1") == []
            with pytest.raises(api.DurableStateError):
                store.release_lease(workflow_token, now=120.0)
            with pytest.raises(api.DurableStateError):
                store.release_lease(step_token, now=120.0)


class TestHeartbeatWorker:
    """NFR-REL-03: independent connection, monotonic cadence, and shutdown."""

    def test_worker_uses_a_thread_owned_connection_not_the_caller_connection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _api("NFR-REL-03 heartbeat thread-owned connection")
        database_path = tmp_path / "state.sqlite3"
        heartbeat_attempted = threading.Event()
        observations: list[tuple[int, int]] = []
        callback_failures: list[BaseException] = []
        original_heartbeat = api.RunStateStore.heartbeat

        def observed_heartbeat(
            current_store: Any, token: Any, *, now: float | None = None
        ) -> Any:
            try:
                result = original_heartbeat(current_store, token, now=now)
                observations.append(
                    (threading.get_ident(), id(_owned_connection(current_store)))
                )
                return result
            finally:
                heartbeat_attempted.set()

        monkeypatch.setattr(api.RunStateStore, "heartbeat", observed_heartbeat)
        main_thread = threading.get_ident()

        with api.RunStateStore(database_path) as store:
            _register(store)
            token = store.acquire_lease(
                "exec-1",
                "ard-1",
                _state_version(store),
                "owner-a",
                now=time.time(),
            )
            caller_connection_id = id(_owned_connection(store))
            worker = api.HeartbeatWorker(
                database_path,
                token,
                interval_seconds=0.01,
                on_failure=callback_failures.append,
            )

            worker.start()
            assert heartbeat_attempted.wait(timeout=2.0)
            worker.stop(timeout=1.0)
            worker.raise_if_failed()
            store.release_lease(token)

        assert callback_failures == []
        assert len(observations) >= 1
        worker_thread, worker_connection_id = observations[0]
        assert worker_thread != main_thread
        assert worker_connection_id != caller_connection_id

    def test_worker_uses_monotonic_recurring_schedule_and_five_second_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _api("NFR-REL-03 monotonic five-second heartbeat schedule")
        database_path = tmp_path / "state.sqlite3"
        interval = 0.02
        three_heartbeats = threading.Event()
        heartbeat_times: list[float] = []
        monotonic_calls: list[float] = []
        failures: list[BaseException] = []

        class RecordingStore:
            def __init__(self, path: Path) -> None:
                self.path = Path(path)

            def __enter__(self) -> "RecordingStore":
                return self

            def __exit__(self, *exc_info: Any) -> None:
                return None

            def heartbeat(self, token: Any, *, now: float | None = None) -> None:
                heartbeat_times.append(_REAL_MONOTONIC())
                if len(heartbeat_times) >= 3:
                    three_heartbeats.set()

        def tracked_monotonic() -> float:
            value = _REAL_MONOTONIC()
            monotonic_calls.append(value)
            return value

        monkeypatch.setattr(api, "RunStateStore", RecordingStore)
        if hasattr(api, "time") and hasattr(api.time, "monotonic"):
            monkeypatch.setattr(api.time, "monotonic", tracked_monotonic)
        elif hasattr(api, "monotonic"):
            monkeypatch.setattr(api, "monotonic", tracked_monotonic)
        else:
            pytest.fail("HeartbeatWorker does not expose a time.monotonic dependency")

        worker = api.HeartbeatWorker(
            database_path,
            _lease_token(api),
            interval_seconds=interval,
            on_failure=failures.append,
        )
        worker.start()
        assert three_heartbeats.wait(timeout=2.0)
        worker.stop(timeout=1.0)
        worker.raise_if_failed()

        interval_default = inspect.signature(api.HeartbeatWorker).parameters[
            "interval_seconds"
        ].default
        gaps = [
            later - earlier
            for earlier, later in zip(heartbeat_times[:2], heartbeat_times[1:3])
        ]
        assert api.HEARTBEAT_INTERVAL_SECONDS == 5.0
        assert interval_default == api.HEARTBEAT_INTERVAL_SECONDS
        assert failures == []
        assert monotonic_calls
        assert all(gap >= interval * 0.5 for gap in gaps)
        assert all(gap < 0.5 for gap in gaps)

    def test_worker_notifies_and_rethrows_heartbeat_write_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _api("NFR-REL-03 heartbeat failure notification")
        database_path = tmp_path / "state.sqlite3"
        callback_called = threading.Event()
        callback_failures: list[BaseException] = []

        class FailingStore:
            def __init__(self, path: Path) -> None:
                self.path = Path(path)

            def __enter__(self) -> "FailingStore":
                return self

            def __exit__(self, *exc_info: Any) -> None:
                return None

            def heartbeat(self, token: Any, *, now: float | None = None) -> None:
                raise api.DurableStateError("injected heartbeat write failure")

        def on_failure(exc: BaseException) -> None:
            callback_failures.append(exc)
            callback_called.set()

        monkeypatch.setattr(api, "RunStateStore", FailingStore)
        worker = api.HeartbeatWorker(
            database_path,
            _lease_token(api),
            interval_seconds=0.01,
            on_failure=on_failure,
        )

        worker.start()
        assert callback_called.wait(timeout=2.0)
        worker.stop(timeout=1.0)

        assert len(callback_failures) == 1
        assert isinstance(callback_failures[0], api.DurableStateError)
        with pytest.raises(api.DurableStateError, match="heartbeat write failure"):
            worker.raise_if_failed()

    def test_stop_respects_timeout_when_heartbeat_call_is_blocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _api("NFR-REL-03 bounded heartbeat worker stop")
        database_path = tmp_path / "state.sqlite3"
        heartbeat_entered = threading.Event()
        release_heartbeat = threading.Event()
        worker_exited = threading.Event()

        class BlockingStore:
            def __init__(self, path: Path) -> None:
                self.path = Path(path)

            def __enter__(self) -> "BlockingStore":
                return self

            def __exit__(self, *exc_info: Any) -> None:
                worker_exited.set()
                return None

            def heartbeat(self, token: Any, *, now: float | None = None) -> None:
                heartbeat_entered.set()
                release_heartbeat.wait(timeout=2.0)

        monkeypatch.setattr(api, "RunStateStore", BlockingStore)
        worker = api.HeartbeatWorker(
            database_path,
            _lease_token(api),
            interval_seconds=0.001,
        )
        worker.start()
        assert heartbeat_entered.wait(timeout=2.0)

        started = _REAL_MONOTONIC()
        try:
            with pytest.raises(
                api.DurableStateError,
                match="did not stop within the timeout",
            ):
                worker.stop(timeout=0.05)
        finally:
            elapsed = _REAL_MONOTONIC() - started
            release_heartbeat.set()
            worker.stop(timeout=1.0)

        assert elapsed < 0.5
        assert worker_exited.wait(timeout=1.0)
