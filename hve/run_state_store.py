"""Durable SQLite control-state store for local HVE executions.

This module owns the FR-STATE-04 storage boundary and the FR-STATE-05 /
NFR-CONC-02 registration, fenced-lease, transition, and heartbeat primitives.
The process-level heartbeat scheduler and crash-injection acceptance flow are
integrated by later orchestration tasks rather than by this storage module.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sqlite3
import threading
import time
import unicodedata
from typing import Any

from platformdirs import user_state_path


SCHEMA_VERSION = 1
HEARTBEAT_INTERVAL_SECONDS = 5.0
LEASE_TTL_SECONDS = 20.0
BUSY_TIMEOUT_SECONDS = 1.0

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_MISSING_REPLAY_KEY_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
_CONTROL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/#:-]*\Z")
_OWNER_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*\Z")
_RUN_OR_HEAD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_SESSION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_EXCEPTION_TYPE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*\Z")
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_SECRET_TOKEN_RE = re.compile(
    r"(?i)(?:^|[^A-Za-z0-9])(?:ghp|github_pat|gho|ghu|ghs|ghr|copilot_pat)_[A-Za-z0-9_]+"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(?:^|[\s,;])(?:gh_token|copilot_pat|token|password|passwd|secret|"
    r"accountkey|connectionstring|credential|api_key)\s*[=:]"
)
_PHASES = frozenset({"pre-qa", "main", "split-fork", "review", "self-improve"})
_PHASE_STATES = frozenset(
    {"pending", "started", "running", "completed", "succeeded", "failed", "skipped", "blocked"}
)
_TABLES = ("executions", "workflow_instances", "step_instances")

_WORKFLOW_STATUSES = (
    "pending",
    "running",
    "suspended",
    "succeeded",
    "failed",
    "skipped",
    "blocked",
)
_STEP_STATUSES = (
    "pending",
    "running",
    "succeeded",
    "failed",
    "skipped",
    "blocked",
)
_EXECUTION_SURFACES = frozenset({"cli", "gui", "orchestrate", "prompt"})

_SCHEMA_SQL = (
    """
    CREATE TABLE executions (
        execution_id TEXT NOT NULL PRIMARY KEY,
        repo_key TEXT NOT NULL,
        surface TEXT NOT NULL,
        plan_schema_version INTEGER NOT NULL,
        launch_plan_hash TEXT NOT NULL,
        plan_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    f"""
    CREATE TABLE workflow_instances (
        execution_id TEXT NOT NULL,
        instance_id TEXT NOT NULL,
        workflow_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
        mode TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN {repr(_WORKFLOW_STATUSES)}),
        state_version INTEGER NOT NULL CHECK (state_version >= 0),
        heartbeat_at REAL,
        checkpoint_head TEXT,
        current_run_id TEXT,
        attempt_no INTEGER NOT NULL CHECK (attempt_no >= 0),
        lease_owner TEXT,
        lease_generation INTEGER NOT NULL CHECK (lease_generation >= 0),
        lease_expires_at REAL,
        PRIMARY KEY (execution_id, instance_id),
        FOREIGN KEY (execution_id)
            REFERENCES executions (execution_id) ON DELETE CASCADE
    )
    """,
    f"""
    CREATE TABLE step_instances (
        execution_id TEXT NOT NULL,
        instance_id TEXT NOT NULL,
        step_id TEXT NOT NULL,
        record_kind TEXT NOT NULL CHECK (record_kind IN ('step', 'approval')),
        status TEXT NOT NULL CHECK (status IN {repr(_STEP_STATUSES)}),
        phase TEXT,
        phase_state TEXT,
        session_id TEXT,
        state_version INTEGER NOT NULL CHECK (state_version >= 0),
        updated_at TEXT NOT NULL,
        last_error_type TEXT,
        PRIMARY KEY (execution_id, instance_id, step_id),
        FOREIGN KEY (execution_id, instance_id)
            REFERENCES workflow_instances (execution_id, instance_id)
            ON DELETE CASCADE
    )
    """,
)

_EXPECTED_COLUMNS: dict[str, tuple[tuple[str, str, int, int], ...]] = {
    "executions": (
        ("execution_id", "TEXT", 1, 1),
        ("repo_key", "TEXT", 1, 0),
        ("surface", "TEXT", 1, 0),
        ("plan_schema_version", "INTEGER", 1, 0),
        ("launch_plan_hash", "TEXT", 1, 0),
        ("plan_json", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ),
    "workflow_instances": (
        ("execution_id", "TEXT", 1, 1),
        ("instance_id", "TEXT", 1, 2),
        ("workflow_id", "TEXT", 1, 0),
        ("ordinal", "INTEGER", 1, 0),
        ("mode", "TEXT", 1, 0),
        ("status", "TEXT", 1, 0),
        ("state_version", "INTEGER", 1, 0),
        ("heartbeat_at", "REAL", 0, 0),
        ("checkpoint_head", "TEXT", 0, 0),
        ("current_run_id", "TEXT", 0, 0),
        ("attempt_no", "INTEGER", 1, 0),
        ("lease_owner", "TEXT", 0, 0),
        ("lease_generation", "INTEGER", 1, 0),
        ("lease_expires_at", "REAL", 0, 0),
    ),
    "step_instances": (
        ("execution_id", "TEXT", 1, 1),
        ("instance_id", "TEXT", 1, 2),
        ("step_id", "TEXT", 1, 3),
        ("record_kind", "TEXT", 1, 0),
        ("status", "TEXT", 1, 0),
        ("phase", "TEXT", 0, 0),
        ("phase_state", "TEXT", 0, 0),
        ("session_id", "TEXT", 0, 0),
        ("state_version", "INTEGER", 1, 0),
        ("updated_at", "TEXT", 1, 0),
        ("last_error_type", "TEXT", 0, 0),
    ),
}

_EXPECTED_FOREIGN_KEYS: dict[
    str, set[tuple[str, str, str, str, str, str]]
] = {
    "executions": set(),
    "workflow_instances": {
        ("executions", "execution_id", "execution_id", "NO ACTION", "CASCADE", "NONE"),
    },
    "step_instances": {
        (
            "workflow_instances",
            "execution_id",
            "execution_id",
            "NO ACTION",
            "CASCADE",
            "NONE",
        ),
        (
            "workflow_instances",
            "instance_id",
            "instance_id",
            "NO ACTION",
            "CASCADE",
            "NONE",
        ),
    },
}

_PLAN_KEYS = frozenset({"instances", "checkpoint_head"})
_DESCRIPTOR_KEYS = frozenset(
    {
        "instance_id",
        "workflow_id",
        "ordinal",
        "mode",
        "argv",
        "missing_replay_keys",
    }
)


class DurableStateError(RuntimeError):
    """The durable state operation could not be completed safely."""


@dataclass(frozen=True, slots=True)
class LeaseToken:
    """Fencing token carried through lease-protected state transitions."""

    execution_id: str
    instance_id: str
    owner: str
    generation: int
    state_version: int


@dataclass(frozen=True, slots=True)
class _RegistrationInstance:
    instance_id: str
    workflow_id: str
    ordinal: int
    mode: str
    argv: tuple[str, ...]
    missing_replay_keys: tuple[str, ...]


def default_state_path() -> Path:
    """Return the process-independent user state database path."""

    return Path(user_state_path("hve", appauthor=False)) / "state.sqlite3"


def canonical_repo_root(repo_root: str | os.PathLike[str]) -> Path:
    """Return the nearest Git worktree root without invoking Git.

    A normal checkout has a ``.git`` directory and a linked worktree has a
    ``.git`` file.  Non-Git synthetic roots remain supported for library tests
    and callers that explicitly scope an isolated repository-like directory.
    """
    try:
        resolved = Path(repo_root).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise DurableStateError("repository root could not be normalized") from exc
    for candidate in (resolved, *resolved.parents):
        marker = candidate / ".git"
        try:
            if marker.is_dir() or marker.is_file():
                return candidate
        except OSError as exc:
            raise DurableStateError("Git repository root could not be inspected") from exc
    return resolved


def compute_repo_key(repo_root: str | os.PathLike[str]) -> str:
    """Hash a normalized repository root without retaining the raw path."""

    resolved = canonical_repo_root(repo_root)

    normalized = os.path.normcase(os.fspath(resolved))
    if os.name == "nt":
        normalized = normalized.replace("\\", "/")
    normalized = unicodedata.normalize("NFC", normalized)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _utc_from_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat(
        timespec="microseconds"
    )


def _clock_value(now: float | None) -> float:
    value = time.time() if now is None else now
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DurableStateError("clock value must be a finite number")
    value = float(value)
    if value < 0 or not (float("-inf") < value < float("inf")):
        raise DurableStateError("clock value must be a non-negative finite number")
    return value


def _require_non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DurableStateError(f"{field} must be a non-negative integer")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\n" in value or "\r" in value:
        raise DurableStateError(f"{field} must be a non-empty single-line string")
    return value


def reject_sensitive_persisted_text(value: Any, field: str) -> str:
    """Reject secret, payload, URL, and absolute-path shapes before persistence."""
    checked = _require_text(value, field)
    if (
        _URI_SCHEME_RE.match(checked)
        or PurePosixPath(checked).is_absolute()
        or PureWindowsPath(checked).is_absolute()
        or checked.lstrip().startswith(("{", "["))
        or _SECRET_TOKEN_RE.search(checked)
        or _SECRET_ASSIGNMENT_RE.search(checked)
    ):
        raise DurableStateError(f"{field} contains a forbidden persistent value")
    return checked


def _require_control_identifier(
    value: Any,
    field: str,
    pattern: re.Pattern[str] = _CONTROL_ID_RE,
) -> str:
    checked = reject_sensitive_persisted_text(value, field)
    if pattern.fullmatch(checked) is None:
        raise DurableStateError(f"{field} is not a valid control identifier")
    return checked


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise DurableStateError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _descriptor_value(instance: Any, field: str) -> Any:
    if isinstance(instance, Mapping):
        if field not in instance:
            raise DurableStateError(f"workflow descriptor is missing {field}")
        return instance[field]
    try:
        return getattr(instance, field)
    except AttributeError as exc:
        raise DurableStateError(f"workflow descriptor is missing {field}") from exc


def _string_sequence(value: Any, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise DurableStateError(f"{field} must be a sequence of strings")
    items = tuple(value)
    if any(
        not isinstance(item, str)
        or "\x00" in item
        or "\n" in item
        or "\r" in item
        for item in items
    ):
        raise DurableStateError(f"{field} must contain only single-line strings")
    return items


def _normalize_instance(instance: Any) -> _RegistrationInstance:
    if isinstance(instance, Mapping):
        unknown = set(instance).difference(_DESCRIPTOR_KEYS)
        if unknown:
            raise DurableStateError("workflow descriptor contains unsupported fields")

    ordinal = _descriptor_value(instance, "ordinal")
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0:
        raise DurableStateError("workflow descriptor ordinal must be a non-negative integer")

    missing_replay_keys = _string_sequence(
        _descriptor_value(instance, "missing_replay_keys"),
        "missing_replay_keys",
    )
    if any(_MISSING_REPLAY_KEY_RE.fullmatch(key) is None for key in missing_replay_keys):
        raise DurableStateError("missing replay keys must use canonical key names")
    if len(set(missing_replay_keys)) != len(missing_replay_keys):
        raise DurableStateError("missing replay keys must be unique")

    instance_id = _require_control_identifier(
        _descriptor_value(instance, "instance_id"), "instance_id"
    )
    workflow_id = _require_control_identifier(
        _descriptor_value(instance, "workflow_id"), "workflow_id"
    )
    mode = _require_control_identifier(
        _descriptor_value(instance, "mode"), "mode"
    )
    if mode != "standard":
        raise DurableStateError("workflow descriptor mode is unsupported")
    argv = _string_sequence(_descriptor_value(instance, "argv"), "argv")
    for index, value in enumerate(argv):
        reject_sensitive_persisted_text(value, f"argv[{index}]")

    return _RegistrationInstance(
        instance_id=instance_id,
        workflow_id=workflow_id,
        ordinal=ordinal,
        mode=mode,
        argv=argv,
        missing_replay_keys=missing_replay_keys,
    )


def _validate_registration(
    execution_id: Any,
    repo_key: Any,
    surface: Any,
    launch_plan_hash: Any,
    plan_json: Any,
    instances: Any,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    tuple[_RegistrationInstance, ...],
    str | None,
]:
    checked_execution_id = _require_control_identifier(
        execution_id, "execution_id"
    )
    checked_repo_key = _require_sha256(repo_key, "repo_key")
    checked_surface = _require_control_identifier(surface, "surface")
    if checked_surface not in _EXECUTION_SURFACES:
        raise DurableStateError("execution surface is unsupported")
    checked_launch_hash = _require_sha256(launch_plan_hash, "launch_plan_hash")
    if not isinstance(plan_json, str) or not plan_json:
        raise DurableStateError("plan_json must be a non-empty JSON string")
    if isinstance(instances, (str, bytes, bytearray)) or not isinstance(
        instances, Sequence
    ):
        raise DurableStateError("instances must be an ordered sequence")

    normalized_instances = tuple(_normalize_instance(item) for item in instances)
    if not normalized_instances:
        raise DurableStateError("at least one workflow instance is required")
    instance_ids = [item.instance_id for item in normalized_instances]
    ordinals = [item.ordinal for item in normalized_instances]
    if len(set(instance_ids)) != len(instance_ids):
        raise DurableStateError("workflow instance IDs must be unique")
    if len(set(ordinals)) != len(ordinals):
        raise DurableStateError("workflow ordinals must be unique")
    if ordinals != sorted(ordinals):
        raise DurableStateError("workflow instances must be ordered by ordinal")
    if ordinals != list(range(len(normalized_instances))):
        raise DurableStateError("workflow ordinals must be contiguous from zero")

    try:
        payload = json.loads(plan_json)
    except (TypeError, ValueError) as exc:
        raise DurableStateError("plan_json is not valid JSON") from exc
    if not isinstance(payload, dict) or set(payload).difference(_PLAN_KEYS):
        raise DurableStateError("plan_json contains unsupported fields")
    plan_instances = payload.get("instances")
    if not isinstance(plan_instances, list):
        raise DurableStateError("plan_json must contain an instances array")
    normalized_plan_instances = tuple(
        _normalize_instance(item) for item in plan_instances
    )
    if normalized_plan_instances != normalized_instances:
        raise DurableStateError("plan_json instances do not match registration instances")

    checkpoint_head = payload.get("checkpoint_head")
    if checkpoint_head is not None:
        checkpoint_head = _require_control_identifier(
            checkpoint_head,
            "checkpoint_head",
            _RUN_OR_HEAD_RE,
        )

    return (
        checked_execution_id,
        checked_repo_key,
        checked_surface,
        checked_launch_hash,
        plan_json,
        normalized_instances,
        checkpoint_head,
    )


class RunStateStore:
    """One-owner SQLite connection for HVE durable control state."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        try:
            self.path = default_state_path() if path is None else Path(path)
        except (TypeError, ValueError) as exc:
            raise DurableStateError("durable state path is invalid") from exc

        self._connection: sqlite3.Connection
        try:
            self._prepare_path()
            self._connection = sqlite3.connect(
                self.path,
                timeout=BUSY_TIMEOUT_SECONDS,
                isolation_level=None,
            )
            self._connection.row_factory = sqlite3.Row
            self._configure_connection()
            self._bootstrap_or_validate_schema()
            self._apply_private_file_mode()
        except DurableStateError:
            self._close_after_failed_open()
            raise
        except sqlite3.Error as exc:
            self._close_after_failed_open()
            raise DurableStateError("durable state database could not be opened") from exc
        except OSError as exc:
            self._close_after_failed_open()
            raise DurableStateError("durable state path could not be prepared") from exc

    def __enter__(self) -> RunStateStore:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        try:
            self.close()
        except DurableStateError as close_error:
            if exc is None:
                raise
            if hasattr(exc, "add_note"):
                exc.add_note(f"durable state close also failed: {close_error}")
        return False

    def close(self) -> None:
        """Close the owned SQLite connection."""

        try:
            self._connection.close()
        except sqlite3.Error as close_error:
            raise DurableStateError(
                "durable state database could not be closed"
            ) from close_error

    def _prepare_path(self) -> None:
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            os.chmod(parent, 0o700)
        try:
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_BINARY", 0),
                0o600,
            )
        except FileExistsError:
            return
        else:
            os.close(descriptor)

    def _apply_private_file_mode(self) -> None:
        if os.name != "nt":
            os.chmod(self.path, 0o600)

    def _close_after_failed_open(self) -> None:
        connection = getattr(self, "_connection", None)
        if isinstance(connection, sqlite3.Connection):
            try:
                connection.close()
            except sqlite3.Error:
                pass

    def _configure_connection(self) -> None:
        journal_mode = self._connection.execute(
            "PRAGMA journal_mode = DELETE"
        ).fetchone()
        self._connection.execute("PRAGMA synchronous = EXTRA")
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA trusted_schema = OFF")
        self._connection.execute(
            f"PRAGMA busy_timeout = {int(BUSY_TIMEOUT_SECONDS * 1000)}"
        )

        actual = {
            "journal_mode": journal_mode[0] if journal_mode else None,
            "synchronous": self._pragma_value("synchronous"),
            "foreign_keys": self._pragma_value("foreign_keys"),
            "trusted_schema": self._pragma_value("trusted_schema"),
            "busy_timeout": self._pragma_value("busy_timeout"),
        }
        expected = {
            "synchronous": 3,
            "foreign_keys": 1,
            "trusted_schema": 0,
            "busy_timeout": int(BUSY_TIMEOUT_SECONDS * 1000),
        }
        if str(actual["journal_mode"]).casefold() != "delete" or any(
            actual[name] != value for name, value in expected.items()
        ):
            raise DurableStateError("required SQLite PRAGMA values are unavailable")

    def _pragma_value(self, name: str) -> Any:
        row = self._connection.execute(f"PRAGMA {name}").fetchone()
        if row is None:
            raise DurableStateError(f"SQLite PRAGMA {name} returned no value")
        return row[0]

    def _bootstrap_or_validate_schema(self) -> None:
        version = self._pragma_value("user_version")
        objects = {
            (str(row[0]), str(row[1]))
            for row in self._connection.execute(
                "SELECT type, name FROM sqlite_schema "
                "WHERE name NOT LIKE 'sqlite_%'"
            )
        }

        if version == 0:
            if objects:
                raise DurableStateError("unversioned durable state schema is not empty")
            self._create_schema()
        elif version != SCHEMA_VERSION:
            raise DurableStateError("unsupported durable state schema version")

        self._verify_schema()
        if not self.quick_check():
            raise DurableStateError("durable state database failed quick_check")

    def _create_schema(self) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            for statement in _SCHEMA_SQL:
                self._connection.execute(statement)
            self._connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._connection.execute("COMMIT")
        except sqlite3.Error as exc:
            self._rollback_quietly()
            raise DurableStateError("durable state schema could not be created") from exc

    def _verify_schema(self) -> None:
        version = self._pragma_value("user_version")
        if version != SCHEMA_VERSION:
            raise DurableStateError("durable state schema version changed unexpectedly")

        objects = {
            (str(row[0]), str(row[1]))
            for row in self._connection.execute(
                "SELECT type, name FROM sqlite_schema "
                "WHERE name NOT LIKE 'sqlite_%'"
            )
        }
        if objects != {("table", table) for table in _TABLES}:
            raise DurableStateError("durable state schema has unexpected objects")

        for table in _TABLES:
            info = self._connection.execute(f"PRAGMA table_info({table})").fetchall()
            actual_columns = tuple(
                (str(row[1]), str(row[2]).upper(), int(row[3]), int(row[5]))
                for row in info
            )
            if actual_columns != _EXPECTED_COLUMNS[table]:
                raise DurableStateError(
                    f"durable state table {table} has an unexpected schema"
                )

            foreign_keys = self._connection.execute(
                f"PRAGMA foreign_key_list({table})"
            ).fetchall()
            actual_foreign_keys = {
                (
                    str(row[2]),
                    str(row[3]),
                    str(row[4]),
                    str(row[5]).upper(),
                    str(row[6]).upper(),
                    str(row[7]).upper(),
                )
                for row in foreign_keys
            }
            if actual_foreign_keys != _EXPECTED_FOREIGN_KEYS[table]:
                raise DurableStateError(
                    f"durable state table {table} has unexpected foreign keys"
                )

    def _rollback_quietly(self) -> None:
        if getattr(self._connection, "in_transaction", False):
            try:
                self._connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass

    def quick_check(self) -> bool:
        """Return whether SQLite reports exactly one ``ok`` quick-check row."""

        try:
            rows = self._connection.execute("PRAGMA quick_check").fetchall()
        except sqlite3.Error as exc:
            raise DurableStateError("durable state quick_check could not run") from exc
        return len(rows) == 1 and str(rows[0][0]).casefold() == "ok"

    def register_execution(
        self,
        execution_id: str,
        repo_key: str,
        surface: str,
        launch_plan_hash: str,
        plan_json: str,
        instances: Sequence[Any],
    ) -> None:
        """Atomically register an execution and every ordered workflow instance."""

        (
            execution_id,
            repo_key,
            surface,
            launch_plan_hash,
            plan_json,
            checked_instances,
            checkpoint_head,
        ) = _validate_registration(
            execution_id,
            repo_key,
            surface,
            launch_plan_hash,
            plan_json,
            instances,
        )
        timestamp = _utc_now()

        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                "INSERT INTO executions ("
                "execution_id, repo_key, surface, plan_schema_version, "
                "launch_plan_hash, plan_json, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    execution_id,
                    repo_key,
                    surface,
                    SCHEMA_VERSION,
                    launch_plan_hash,
                    plan_json,
                    timestamp,
                    timestamp,
                ),
            )
            for instance in checked_instances:
                self._connection.execute(
                    "INSERT INTO workflow_instances ("
                    "execution_id, instance_id, workflow_id, ordinal, mode, "
                    "status, state_version, heartbeat_at, checkpoint_head, "
                    "current_run_id, attempt_no, lease_owner, lease_generation, "
                    "lease_expires_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        execution_id,
                        instance.instance_id,
                        instance.workflow_id,
                        instance.ordinal,
                        instance.mode,
                        "pending",
                        0,
                        None,
                        checkpoint_head,
                        None,
                        0,
                        None,
                        0,
                        None,
                    ),
                )
            self._connection.execute("COMMIT")
        except sqlite3.Error as exc:
            self._rollback_quietly()
            raise DurableStateError(
                "durable execution registration could not be committed"
            ) from exc

    def get_execution(self, execution_id: str) -> sqlite3.Row | None:
        try:
            return self._connection.execute(
                "SELECT * FROM executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DurableStateError("durable execution could not be read") from exc

    def get_instance(
        self, execution_id: str, instance_id: str
    ) -> sqlite3.Row | None:
        try:
            return self._connection.execute(
                "SELECT * FROM workflow_instances "
                "WHERE execution_id = ? AND instance_id = ?",
                (execution_id, instance_id),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DurableStateError("durable workflow instance could not be read") from exc

    def list_instances(self, execution_id: str) -> list[sqlite3.Row]:
        try:
            return self._connection.execute(
                "SELECT * FROM workflow_instances WHERE execution_id = ? "
                "ORDER BY ordinal ASC, instance_id ASC",
                (execution_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DurableStateError("durable workflow instances could not be read") from exc

    def list_steps(self, execution_id: str, instance_id: str) -> list[sqlite3.Row]:
        try:
            return self._connection.execute(
                "SELECT * FROM step_instances "
                "WHERE execution_id = ? AND instance_id = ? "
                "ORDER BY updated_at ASC, step_id ASC",
                (execution_id, instance_id),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DurableStateError("durable step instances could not be read") from exc

    def list_candidates(self, repo_key: str) -> list[sqlite3.Row]:
        checked_repo_key = _require_sha256(repo_key, "repo_key")
        if not self.quick_check():
            raise DurableStateError("durable state database failed quick_check")
        try:
            return self._connection.execute(
                "SELECT * FROM executions WHERE repo_key = ? "
                "ORDER BY updated_at DESC, execution_id DESC",
                (checked_repo_key,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DurableStateError("durable resume candidates could not be read") from exc

    def acquire_lease(
        self,
        execution_id: str,
        instance_id: str,
        expected_state_version: int,
        owner: str,
        *,
        now: float | None = None,
        allow_takeover: bool = False,
    ) -> LeaseToken:
        execution_id = _require_text(execution_id, "execution_id")
        instance_id = _require_text(instance_id, "instance_id")
        owner = _require_control_identifier(owner, "lease owner", _OWNER_ID_RE)
        expected_state_version = _require_non_negative_int(
            expected_state_version, "expected_state_version"
        )
        if not isinstance(allow_takeover, bool):
            raise DurableStateError("allow_takeover must be a boolean")
        now_value = _clock_value(now)

        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT state_version, lease_owner, lease_generation, "
                "lease_expires_at FROM workflow_instances "
                "WHERE execution_id = ? AND instance_id = ?",
                (execution_id, instance_id),
            ).fetchone()
            if row is None:
                raise DurableStateError("durable workflow instance was not found")
            if int(row["state_version"]) != expected_state_version:
                raise DurableStateError("durable state version is stale")

            active_owner = row["lease_owner"]
            expires_at = row["lease_expires_at"]
            lease_is_active = (
                active_owner is not None
                and expires_at is not None
                and float(expires_at) > now_value
            )
            if lease_is_active:
                raise DurableStateError("durable workflow instance has an active owner")
            if active_owner is not None and not allow_takeover:
                raise DurableStateError("expired lease requires explicit takeover")

            generation = int(row["lease_generation"]) + 1
            cursor = self._connection.execute(
                "UPDATE workflow_instances SET "
                "lease_owner = ?, lease_generation = ?, lease_expires_at = ?, "
                "heartbeat_at = ?, attempt_no = attempt_no + 1 "
                "WHERE execution_id = ? AND instance_id = ? "
                "AND state_version = ? AND lease_generation = ?",
                (
                    owner,
                    generation,
                    now_value + LEASE_TTL_SECONDS,
                    now_value,
                    execution_id,
                    instance_id,
                    expected_state_version,
                    int(row["lease_generation"]),
                ),
            )
            if cursor.rowcount != 1:
                raise DurableStateError("durable lease compare-and-swap failed")
            self._touch_execution(execution_id, now_value)
            self._connection.execute("COMMIT")
        except DurableStateError:
            self._rollback_quietly()
            raise
        except sqlite3.Error as exc:
            self._rollback_quietly()
            raise DurableStateError("durable lease could not be acquired") from exc

        return LeaseToken(
            execution_id=execution_id,
            instance_id=instance_id,
            owner=owner,
            generation=generation,
            state_version=expected_state_version,
        )

    def transition_workflow(
        self,
        token: LeaseToken,
        status: str,
        *,
        run_id: str | None = None,
        checkpoint_head: str | None = None,
    ) -> LeaseToken:
        checked_token = self._validate_token(token)
        if status not in _WORKFLOW_STATUSES:
            raise DurableStateError("unsupported durable workflow status")
        if run_id is not None:
            run_id = _require_control_identifier(run_id, "run_id", _RUN_OR_HEAD_RE)
        if checkpoint_head is not None:
            checkpoint_head = _require_control_identifier(
                checkpoint_head,
                "checkpoint_head",
                _RUN_OR_HEAD_RE,
            )
        now_value = _clock_value(None)
        next_version = checked_token.state_version + 1

        assignments = [
            "status = ?",
            "state_version = ?",
            "heartbeat_at = CASE WHEN heartbeat_at IS NULL OR heartbeat_at < ? "
            "THEN ? ELSE heartbeat_at END",
            "lease_expires_at = CASE WHEN lease_expires_at IS NULL OR lease_expires_at < ? "
            "THEN ? ELSE lease_expires_at END",
        ]
        expires_at = now_value + LEASE_TTL_SECONDS
        values: list[Any] = [
            status,
            next_version,
            now_value,
            now_value,
            expires_at,
            expires_at,
        ]
        if run_id is not None:
            assignments.append("current_run_id = ?")
            values.append(run_id)
        if checkpoint_head is not None:
            assignments.append("checkpoint_head = ?")
            values.append(checkpoint_head)

        try:
            self._connection.execute("BEGIN IMMEDIATE")
            cursor = self._connection.execute(
                "UPDATE workflow_instances SET " + ", ".join(assignments) + " "
                "WHERE execution_id = ? AND instance_id = ? "
                "AND lease_owner = ? AND lease_generation = ? "
                "AND state_version = ? AND lease_expires_at IS NOT NULL "
                "AND lease_expires_at > ?",
                (
                    *values,
                    checked_token.execution_id,
                    checked_token.instance_id,
                    checked_token.owner,
                    checked_token.generation,
                    checked_token.state_version,
                    now_value,
                ),
            )
            if cursor.rowcount != 1:
                raise DurableStateError("durable workflow transition was fenced")
            self._touch_execution(checked_token.execution_id, now_value)
            self._connection.execute("COMMIT")
        except DurableStateError:
            self._rollback_quietly()
            raise
        except sqlite3.Error as exc:
            self._rollback_quietly()
            raise DurableStateError("durable workflow transition failed") from exc

        return LeaseToken(
            checked_token.execution_id,
            checked_token.instance_id,
            checked_token.owner,
            checked_token.generation,
            next_version,
        )

    def transition_step(
        self,
        token: LeaseToken,
        step_id: str,
        status: str,
        *,
        record_kind: str = "step",
        phase: str | None = None,
        phase_state: str | None = None,
        session_id: str | None = None,
        last_error_type: str | None = None,
    ) -> LeaseToken:
        checked_token = self._validate_token(token)
        step_id = _require_control_identifier(step_id, "step_id")
        if status not in _STEP_STATUSES:
            raise DurableStateError("unsupported durable step status")
        if record_kind not in {"step", "approval"}:
            raise DurableStateError("unsupported durable record kind")
        if phase is not None and phase not in _PHASES:
            raise DurableStateError("unsupported durable phase")
        if phase_state is not None and phase_state not in _PHASE_STATES:
            raise DurableStateError("unsupported durable phase state")
        if session_id is not None:
            _require_control_identifier(session_id, "session_id", _SESSION_ID_RE)
        if last_error_type is not None:
            _require_control_identifier(
                last_error_type,
                "last_error_type",
                _EXCEPTION_TYPE_RE,
            )

        now_value = _clock_value(None)
        updated_at = _utc_from_timestamp(now_value)
        next_version = checked_token.state_version + 1
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            cursor = self._connection.execute(
                "UPDATE workflow_instances SET state_version = ?, "
                "heartbeat_at = CASE WHEN heartbeat_at IS NULL OR heartbeat_at < ? "
                "THEN ? ELSE heartbeat_at END, "
                "lease_expires_at = CASE WHEN lease_expires_at IS NULL OR lease_expires_at < ? "
                "THEN ? ELSE lease_expires_at END "
                "WHERE execution_id = ? AND instance_id = ? "
                "AND lease_owner = ? AND lease_generation = ? "
                "AND state_version = ? AND lease_expires_at IS NOT NULL "
                "AND lease_expires_at > ?",
                (
                    next_version,
                    now_value,
                    now_value,
                    now_value + LEASE_TTL_SECONDS,
                    now_value + LEASE_TTL_SECONDS,
                    checked_token.execution_id,
                    checked_token.instance_id,
                    checked_token.owner,
                    checked_token.generation,
                    checked_token.state_version,
                    now_value,
                ),
            )
            if cursor.rowcount != 1:
                raise DurableStateError("durable step transition was fenced")
            self._connection.execute(
                "INSERT INTO step_instances ("
                "execution_id, instance_id, step_id, record_kind, status, "
                "phase, phase_state, session_id, state_version, updated_at, "
                "last_error_type"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(execution_id, instance_id, step_id) DO UPDATE SET "
                "record_kind = excluded.record_kind, status = excluded.status, "
                "phase = COALESCE(excluded.phase, step_instances.phase), "
                "phase_state = COALESCE("
                "excluded.phase_state, step_instances.phase_state), "
                "session_id = COALESCE("
                "excluded.session_id, step_instances.session_id), "
                "state_version = excluded.state_version, "
                "updated_at = excluded.updated_at, "
                "last_error_type = excluded.last_error_type",
                (
                    checked_token.execution_id,
                    checked_token.instance_id,
                    step_id,
                    record_kind,
                    status,
                    phase,
                    phase_state,
                    session_id,
                    next_version,
                    updated_at,
                    last_error_type,
                ),
            )
            self._touch_execution(checked_token.execution_id, now_value)
            self._connection.execute("COMMIT")
        except DurableStateError:
            self._rollback_quietly()
            raise
        except sqlite3.Error as exc:
            self._rollback_quietly()
            raise DurableStateError("durable step transition failed") from exc

        return LeaseToken(
            checked_token.execution_id,
            checked_token.instance_id,
            checked_token.owner,
            checked_token.generation,
            next_version,
        )

    def heartbeat(self, token: LeaseToken, *, now: float | None = None) -> None:
        checked_token = self._validate_token(token)
        now_value = _clock_value(now)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            cursor = self._connection.execute(
                "UPDATE workflow_instances SET "
                "heartbeat_at = CASE WHEN heartbeat_at IS NULL OR heartbeat_at < ? "
                "THEN ? ELSE heartbeat_at END, "
                "lease_expires_at = CASE WHEN lease_expires_at IS NULL OR lease_expires_at < ? "
                "THEN ? ELSE lease_expires_at END "
                "WHERE execution_id = ? AND instance_id = ? "
                "AND lease_owner = ? AND lease_generation = ? "
                "AND lease_expires_at IS NOT NULL AND lease_expires_at > ?",
                (
                    now_value,
                    now_value,
                    now_value + LEASE_TTL_SECONDS,
                    now_value + LEASE_TTL_SECONDS,
                    checked_token.execution_id,
                    checked_token.instance_id,
                    checked_token.owner,
                    checked_token.generation,
                    now_value,
                ),
            )
            if cursor.rowcount != 1:
                raise DurableStateError("durable heartbeat was fenced")
            self._touch_execution(checked_token.execution_id, now_value)
            self._connection.execute("COMMIT")
        except DurableStateError:
            self._rollback_quietly()
            raise
        except sqlite3.Error as exc:
            self._rollback_quietly()
            raise DurableStateError("durable heartbeat failed") from exc

    def release_lease(
        self,
        token: LeaseToken,
        *,
        now: float | None = None,
    ) -> None:
        checked_token = self._validate_token(token)
        now_value = _clock_value(now)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            cursor = self._connection.execute(
                "UPDATE workflow_instances SET lease_owner = NULL, "
                "lease_expires_at = NULL WHERE execution_id = ? AND instance_id = ? "
                "AND lease_owner = ? AND lease_generation = ? "
                "AND lease_expires_at IS NOT NULL AND lease_expires_at > ?",
                (
                    checked_token.execution_id,
                    checked_token.instance_id,
                    checked_token.owner,
                    checked_token.generation,
                    now_value,
                ),
            )
            if cursor.rowcount != 1:
                raise DurableStateError("durable lease release was fenced")
            self._touch_execution(checked_token.execution_id, now_value)
            self._connection.execute("COMMIT")
        except DurableStateError:
            self._rollback_quietly()
            raise
        except sqlite3.Error as exc:
            self._rollback_quietly()
            raise DurableStateError("durable lease could not be released") from exc

    @staticmethod
    def _validate_token(token: LeaseToken) -> LeaseToken:
        if not isinstance(token, LeaseToken):
            raise DurableStateError("invalid durable lease token")
        _require_text(token.execution_id, "execution_id")
        _require_text(token.instance_id, "instance_id")
        _require_control_identifier(token.owner, "lease owner", _OWNER_ID_RE)
        _require_non_negative_int(token.generation, "lease generation")
        _require_non_negative_int(token.state_version, "state version")
        return token

    def _touch_execution(self, execution_id: str, now_value: float) -> None:
        updated_at = _utc_from_timestamp(now_value)
        cursor = self._connection.execute(
            "UPDATE executions SET updated_at = CASE WHEN updated_at > ? "
            "THEN updated_at ELSE ? END WHERE execution_id = ?",
            (updated_at, updated_at, execution_id),
        )
        if cursor.rowcount != 1:
            raise DurableStateError("durable execution timestamp update failed")


class HeartbeatWorker:
    """Maintain one fenced lease from a dedicated thread and connection."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        token: LeaseToken,
        *,
        interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
        on_failure: Callable[[BaseException], None] | None = None,
    ) -> None:
        self.path = Path(path)
        self.token = token
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or float(interval_seconds) <= 0
        ):
            raise ValueError("interval_seconds must be positive")
        if on_failure is not None and not callable(on_failure):
            raise TypeError("on_failure must be callable")
        self.interval_seconds = float(interval_seconds)
        self.on_failure = on_failure
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._failure: BaseException | None = None
        self._state_lock = threading.Lock()

    def start(self) -> None:
        with self._state_lock:
            if self._thread is not None:
                raise RuntimeError("heartbeat worker can only be started once")
            self._thread = threading.Thread(
                target=self._run,
                name=f"hve-heartbeat-{self.token.instance_id}",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0:
            raise ValueError("timeout must be a non-negative number")
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=float(timeout))
            if thread.is_alive():
                raise DurableStateError(
                    "heartbeat worker did not stop within the timeout"
                )

    def raise_if_failed(self) -> None:
        with self._state_lock:
            failure = self._failure
        if failure is not None:
            raise failure

    def _run(self) -> None:
        try:
            with RunStateStore(self.path) as store:
                deadline = time.monotonic() + self.interval_seconds
                while True:
                    remaining = max(0.0, deadline - time.monotonic())
                    if self._stop_event.wait(remaining):
                        return
                    store.heartbeat(self.token, now=time.time())
                    deadline = time.monotonic() + self.interval_seconds
        except BaseException as exc:
            with self._state_lock:
                if self._failure is None:
                    self._failure = exc
            if self.on_failure is not None:
                try:
                    self.on_failure(exc)
                except BaseException:
                    pass


__all__ = [
    "BUSY_TIMEOUT_SECONDS",
    "DurableStateError",
    "HEARTBEAT_INTERVAL_SECONDS",
    "HeartbeatWorker",
    "LEASE_TTL_SECONDS",
    "LeaseToken",
    "RunStateStore",
    "SCHEMA_VERSION",
    "compute_repo_key",
    "default_state_path",
    "reject_sensitive_persisted_text",
]
