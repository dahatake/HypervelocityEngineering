"""Execute one ASDW Step 1.3 script only after validating the same bytes.

This module is intentionally a narrow local execution boundary. It does not
discover scripts or invoke Azure itself. As the verify contract's caller it
provisions the stage-scoped run ID when the environment lacks a valid one and,
for the verify stage, validates the same sanitized parent environment used by
the preceding stages. No intermediate environment file is read or sourced, so
stale values from a previous run cannot override current inputs. Loader and
PATH injection knobs are rejected fail-closed and Bash startup hooks are never
sourced. The calling HVE session must request one exact ``python -m`` stage
command; the Step 1.3 permission handler validates the generated artifacts
immediately before this launcher starts.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import shutil
import stat
import subprocess
import sys
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

if __package__:
    from .artifact_validation import (
        _ASDW_DATA_DEPLOY_NETWORK_KEYS,
        validate_asdw_data_create_scripts,
        validate_asdw_data_registration_script,
        validate_asdw_data_verify_script,
    )
else:  # pragma: no cover - top-level runner compatibility
    from artifact_validation import (  # type: ignore[import-not-found,no-redef]
        _ASDW_DATA_DEPLOY_NETWORK_KEYS,
        validate_asdw_data_create_scripts,
        validate_asdw_data_registration_script,
        validate_asdw_data_verify_script,
    )

_PREP = "src/infra/azure/create-azure-data-resources-prep.sh"
_CREATE = "src/infra/azure/create-azure-data-resources.sh"
_REGISTRATION = "src/data/azure/data-registration-script.sh"
_VERIFY = "src/infra/azure/verify-data-resources.sh"
_DESIGN = "docs/azure/azure-services-data.md"
_SAMPLE = "src/data/sample-data.json"
_STAGES = frozenset({"prep", "create", "registration", "verify"})
_STAGE_METADATA_PREFIX = ".hve-asdw-data-"
_STAGE_SUCCESS_MARKERS = {
    "prep": "prep-success",
    "create": "create-success",
    "registration": "registration-success",
    "verify": "verify-success",
}
_STAGE_PREDECESSORS = {
    "create": "prep",
    "registration": "create",
    "verify": "registration",
}
_STAGE_MARKER_INVALIDATIONS = {
    # prep is deliberately retained for the second create pass in the same
    # pipeline; every downstream marker is invalidated before its next attempt.
    "prep": ("prep", "create", "registration", "verify"),
    "create": ("create", "registration", "verify"),
    "registration": ("registration", "verify"),
    "verify": (),
}
_STAGE_EXECUTION_LOCK = ".hve-asdw-data-stage.lock"
_PREP_SUCCESS_MARKER = _STAGE_SUCCESS_MARKERS["prep"]
_CREATE_SUCCESS_MARKER = _STAGE_SUCCESS_MARKERS["create"]
_REGISTRATION_SUCCESS_MARKER = _STAGE_SUCCESS_MARKERS["registration"]
_STAGE_RUN_ID_KEYS = {
    "create": "DATA_CREATE_RUN_ID",
    "registration": "DATA_REGISTER_RUN_ID",
    "verify": "DATA_VERIFY_RUN_ID",
}
_RUN_ID_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
_ASDW_DATA_DEPLOY_CHILD_CONTEXT_KEYS = frozenset(
    {
        "RESOURCE_GROUP",
        "LOCATION",
        "SUBSCRIPTION_ID",
        *_ASDW_DATA_DEPLOY_NETWORK_KEYS,
        # 宣言済みの CIDR は prep が VNet / サブネットを作成するときに適用する。
        # これらを配らないと Azure CLI の既定アドレス空間で作成されてしまう。
        "DATA_VNET_CIDR",
        "DATA_PRIVATE_ENDPOINT_SUBNET_CIDR",
        "DATA_ACI_SUBNET_CIDR",
        "DATA_VERIFY_ACI_IMAGE",
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
        # 台帳は既定 location 非対応のため別 location へ fallback する。
        "CONFIDENTIAL_LEDGER_LOCATION",
        *_STAGE_RUN_ID_KEYS.values(),
    }
)
# The registry name and image name are only meaningful while prep builds the
# verification image, so they are not distributed to the later stages.
_ASDW_DATA_DEPLOY_PREP_ONLY_CONTEXT_KEYS = frozenset(
    {
        "DATA_VERIFY_ACR_NAME",
        "DATA_VERIFY_IMAGE_NAME",
    }
)
# Non-secret host paths the replaced child environment still needs: without a
# home variable the Azure CLI resolves its configuration relative to the
# working directory, and without TEMP/TMP the child falls back to the shared
# system temporary directory.
_HOST_RUNTIME_CONTEXT_KEYS: tuple[str, ...] = (
    ("USERPROFILE", "HOMEDRIVE", "HOMEPATH", "TEMP", "TMP")
    if os.name == "nt"
    else ("HOME", "TMPDIR")
)


class ScriptLauncherError(RuntimeError):
    """Raised when a script cannot be safely validated for local execution."""


@dataclass(frozen=True)
class _Snapshot:
    path: Path
    raw: bytes
    text: str


@dataclass
class _StageExecutionLock:
    """One OS-owned lock descriptor held for a protected HVE stage."""

    descriptor: int
    path: Path


@dataclass(frozen=True)
class StageResult:
    """Bounded outcome from one HVE-owned DataDeploy pipeline stage."""

    stage: str
    attempt: int
    exit_code: int
    reached: bool
    evidence: str


def _validate_direct_repo_directory(repo_root: Path, directory: Path, label: str) -> Path:
    """Return one lexical, non-reparse directory directly under this repository."""
    expected_root = Path(os.path.abspath(directory))
    try:
        relative = expected_root.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ScriptLauncherError(f"{label} escapes the repository.") from exc

    current = repo_root.resolve()
    reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))
    try:
        for part in relative.parts:
            current = current / part
            current_stat = os.lstat(current)
            if (
                not stat.S_ISDIR(current_stat.st_mode)
                or stat.S_ISLNK(current_stat.st_mode)
                or int(getattr(current_stat, "st_file_attributes", 0)) & reparse
            ):
                raise ScriptLauncherError(
                    f"{label} must not contain a symlink or reparse point."
                )
        resolved = expected_root.resolve(strict=True)
    except OSError as exc:
        raise ScriptLauncherError(f"{label} is unavailable.") from exc
    if os.path.normcase(os.path.normpath(resolved)) != os.path.normcase(
        os.path.normpath(expected_root)
    ):
        raise ScriptLauncherError(f"{label} must be lexical and direct.")
    return expected_root


def _validate_hve_run_root(repo_root: Path, run_id: str, work_root: str) -> Path:
    """Validate one lexical HVE run root before each stage attempt."""
    expected_root = Path(os.path.abspath(repo_root / "work" / "run" / run_id))
    actual_root = Path(os.path.abspath(work_root))
    if os.path.normcase(os.path.normpath(actual_root)) != os.path.normcase(
        os.path.normpath(expected_root)
    ):
        raise ScriptLauncherError("HVE data stage work root does not match the current run.")
    if os.name == "nt":
        try:
            case_matches = [
                entry.name
                for entry in expected_root.parent.iterdir()
                if entry.name.casefold() == run_id.casefold()
            ]
        except OSError as exc:
            raise ScriptLauncherError("HVE data stage work root is unavailable.") from exc
        if case_matches != [run_id]:
            raise ScriptLauncherError(
                "HVE data stage run ID must match the existing run directory case."
            )
    return _validate_direct_repo_directory(
        repo_root,
        expected_root,
        "HVE data stage work root",
    )


def _stage_success_marker_paths(
    repo_root: Path,
    environment: Mapping[str, str],
) -> Optional[dict[str, Path]]:
    """Return HVE-owned stage markers, or None outside an HVE run.

    The agent may write only inside its own Issue directory; these markers
    live in the validated work/run namespace outside that run root and are
    created only by this launcher after each protected stage exits successfully.
    """
    run_id = str(environment.get("HVE_RUN_ID", "") or "")
    work_root = str(environment.get("HVE_WORK_ROOT", "") or "")
    if not run_id and not work_root:
        return None
    if (
        not run_id
        or not re.fullmatch(r"[A-Za-z0-9_-]+", run_id)
        or not work_root
        or work_root != work_root.strip()
        or "\x00" in work_root
        or not Path(work_root).is_absolute()
    ):
        raise ScriptLauncherError("HVE data stage requires a canonical run context.")
    resolved_repo_root = repo_root.resolve()
    _validate_hve_run_root(resolved_repo_root, run_id, work_root)
    metadata_root = _validate_direct_repo_directory(
        resolved_repo_root,
        resolved_repo_root / "work" / "run",
        "HVE data stage metadata root",
    )
    return {
        stage: metadata_root / f"{_STAGE_METADATA_PREFIX}{run_id}-{marker_name}"
        for stage, marker_name in _STAGE_SUCCESS_MARKERS.items()
    }


def _stage_execution_lock_path(stage_markers: Mapping[str, Path]) -> Path:
    """Return the HVE-owned run lock next to the private stage markers."""
    return stage_markers["prep"].with_name(
        stage_markers["prep"].name + "-" + _STAGE_EXECUTION_LOCK
    )


def _validate_stage_execution_lock_path(lock_path: Path, descriptor: int) -> None:
    """Require one regular non-linked lock file matching its opened descriptor."""
    try:
        opened = os.fstat(descriptor)
        path_stat = os.lstat(lock_path)
    except OSError as exc:
        raise ScriptLauncherError("HVE data stage lock is unreadable.") from exc
    reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
        or stat.S_ISLNK(path_stat.st_mode)
        or int(getattr(path_stat, "st_file_attributes", 0)) & reparse
        or not os.path.samestat(opened, path_stat)
    ):
        raise ScriptLauncherError("HVE data stage lock is not a regular file.")


def _acquire_stage_execution_lock(lock_path: Path) -> _StageExecutionLock:
    """Acquire one non-waiting OS lock released automatically on process exit.

    A concurrent stage can observe a predecessor marker only after that marker
    is committed.  The lock covers predecessor validation through the process
    result and marker commit, so another stage must fail closed instead of
    racing that transition.
    """
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(
        os, "O_CLOEXEC", 0
    ) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    acquired = False
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        _validate_stage_execution_lock_path(lock_path, descriptor)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            fcntl = __import__("fcntl")

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        acquired = True
        return _StageExecutionLock(descriptor=descriptor, path=lock_path)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, errno.EDEADLK}:
            raise ScriptLauncherError(
                "HVE data stage is already running for the current run."
            ) from exc
        raise ScriptLauncherError("HVE data stage lock cannot be acquired.") from exc
    finally:
        if descriptor >= 0 and not acquired:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _release_stage_execution_lock(lock: _StageExecutionLock) -> None:
    """Release the OS lock; descriptor close also releases it after crashes."""
    unlock_error: Optional[OSError] = None
    try:
        os.lseek(lock.descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.descriptor, msvcrt.LK_UNLCK, 1)
        else:
            fcntl = __import__("fcntl")

            fcntl.flock(lock.descriptor, fcntl.LOCK_UN)
    except OSError as exc:
        unlock_error = exc
    finally:
        try:
            os.close(lock.descriptor)
        except OSError as exc:
            if unlock_error is None:
                unlock_error = exc
    if unlock_error is not None:
        raise ScriptLauncherError("HVE data stage lock cannot be released.") from unlock_error


def _release_stage_execution_lock_after_stage(
    lock: _StageExecutionLock,
    primary_error: Optional[BaseException],
    stage_return_code: Optional[int],
    stage_markers: Optional[Mapping[str, Path]],
    stage: str,
) -> None:
    """Release a lock without masking a preceding stage error.

    A cleanup failure is itself fatal after a successful stage.  In that case
    successor markers are invalidated because lock ownership is no longer
    trustworthy. When the stage already failed, retain that actionable error
    and attach the cleanup failure as diagnostic context instead.
    """
    try:
        _release_stage_execution_lock(lock)
    except ScriptLauncherError as cleanup_error:
        if primary_error is None:
            if stage_return_code not in (None, 0):
                print(
                    "[WARN] HVE data stage lock cleanup failed after stage "
                    f"exit {stage_return_code}: {cleanup_error}",
                    file=sys.stderr,
                )
                return
            if stage_markers is not None and stage in _STAGE_SUCCESS_MARKERS:
                try:
                    for invalidated_stage in _STAGE_MARKER_INVALIDATIONS[stage]:
                        _clear_stage_success_marker(
                            stage_markers[invalidated_stage],
                            invalidated_stage,
                        )
                except ScriptLauncherError as marker_error:
                    if hasattr(cleanup_error, "add_note"):
                        cleanup_error.add_note(str(marker_error))
            raise
        if hasattr(primary_error, "add_note"):
            primary_error.add_note(str(cleanup_error))


def _validate_stage_success_marker(marker: Path, stage: str) -> os.stat_result:
    """Require one regular, non-linked HVE-owned marker file."""
    try:
        marker_stat = os.lstat(marker)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ScriptLauncherError(f"HVE {stage} success marker is unreadable.") from exc
    reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))
    if (
        not stat.S_ISREG(marker_stat.st_mode)
        or marker_stat.st_nlink != 1
        or stat.S_ISLNK(marker_stat.st_mode)
        or int(getattr(marker_stat, "st_file_attributes", 0)) & reparse
    ):
        raise ScriptLauncherError(f"HVE {stage} success marker is not a regular file.")
    return marker_stat


def _clear_stage_success_marker(marker: Path, stage: str) -> None:
    """Invalidate a stage result before that stage is attempted again."""
    try:
        _validate_stage_success_marker(marker, stage)
    except FileNotFoundError:
        return
    try:
        marker.unlink()
    except OSError as exc:
        raise ScriptLauncherError(f"HVE {stage} success marker cannot be cleared.") from exc


def _require_stage_success_marker(
    marker: Path,
    *,
    required_stage: str,
    requested_stage: str,
    run_id: str,
) -> None:
    """Require the successful predecessor record for the current HVE run."""
    try:
        _validate_stage_success_marker(marker, required_stage)
        with marker.open("r", encoding="utf-8", newline="") as stream:
            payload = stream.read()
    except FileNotFoundError as exc:
        raise ScriptLauncherError(
            f"HVE {requested_stage} stage requires a successful {required_stage} "
            "stage in the current run."
        ) from exc
    except OSError as exc:
        raise ScriptLauncherError(
            f"HVE {required_stage} success marker is unreadable."
        ) from exc
    if payload != f"{run_id}\n":
        raise ScriptLauncherError(
            f"HVE {required_stage} success marker does not match the current run."
        )


def _write_stage_success_marker(marker: Path, stage: str, run_id: str) -> None:
    """Atomically record that this launcher's stage process completed successfully."""
    try:
        descriptor = os.open(
            marker,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except OSError as exc:
        raise ScriptLauncherError(f"HVE {stage} success marker cannot be created.") from exc
    try:
        os.write(descriptor, f"{run_id}\n".encode("ascii"))
    except OSError as exc:
        raise ScriptLauncherError(f"HVE {stage} success marker cannot be written.") from exc
    finally:
        os.close(descriptor)


def _read_stable_utf8_file(
    path: Path,
    repo_root: Path,
    label: str,
    *,
    allow_crlf: bool = False,
) -> _Snapshot:
    """Read a stable, regular UTF-8 file that stays under ``repo_root``.

    ``allow_crlf`` mirrors the generator contract: HVE-generated producers stay
    LF-strict, while human-authored inputs (the design document and the sample
    data) are normalized. Git only pins ``eol=lf`` for ``*.sh``, so on a Windows
    checkout with ``core.autocrlf=true`` those inputs are always CRLF on disk.
    """
    root = repo_root.resolve()
    lexical = Path(os.path.abspath(path))
    try:
        lexical.relative_to(root)
    except ValueError as exc:
        raise ScriptLauncherError(f"{label} path escapes the repository root.") from exc

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(lexical, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ScriptLauncherError(f"{label} is not a regular file.")
        if opened.st_nlink != 1:
            raise ScriptLauncherError(f"{label} must not be a hard-linked file.")
        path_stat = os.lstat(lexical)
        reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))
        if (
            stat.S_ISLNK(path_stat.st_mode)
            or int(getattr(path_stat, "st_file_attributes", 0)) & reparse
            or not stat.S_ISREG(path_stat.st_mode)
            or not os.path.samestat(opened, path_stat)
        ):
            raise ScriptLauncherError(f"{label} must not be a symlink or reparse point.")
        resolved = lexical.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ScriptLauncherError(f"{label} resolves outside the repository root.") from exc
        if os.path.normcase(str(resolved)) != os.path.normcase(str(lexical)):
            raise ScriptLauncherError(f"{label} path must not contain a symlink or junction.")
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            raw = stream.read()
        final = os.fstat(descriptor)
        final_path_stat = os.lstat(lexical)
        if (
            not os.path.samestat(opened, final)
            or opened.st_size != final.st_size
            or opened.st_mtime_ns != final.st_mtime_ns
            or stat.S_ISLNK(final_path_stat.st_mode)
            or int(getattr(final_path_stat, "st_file_attributes", 0)) & reparse
            or not os.path.samestat(opened, final_path_stat)
        ):
            raise ScriptLauncherError(f"{label} changed while it was read.")
        final_resolved = lexical.resolve(strict=True)
        try:
            final_resolved.relative_to(root)
        except ValueError as exc:
            raise ScriptLauncherError(
                f"{label} resolves outside the repository root after it was read."
            ) from exc
        if os.path.normcase(str(final_resolved)) != os.path.normcase(str(lexical)):
            raise ScriptLauncherError(f"{label} path changed while it was read.")
        if not os.path.samestat(opened, os.stat(final_resolved, follow_symlinks=False)):
            raise ScriptLauncherError(f"{label} changed during final path validation.")
    except (OSError, UnicodeError) as exc:
        raise ScriptLauncherError(f"{label} is unreadable.") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    if raw.startswith(b"\xef\xbb\xbf"):
        raise ScriptLauncherError(f"{label} must be UTF-8 without BOM and use LF only.")
    normalized = raw.replace(b"\r\n", b"\n") if allow_crlf else raw
    if b"\r" in normalized:
        raise ScriptLauncherError(f"{label} must be UTF-8 without BOM and use LF only.")
    try:
        text = normalized.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScriptLauncherError(f"{label} must be valid UTF-8.") from exc
    return _Snapshot(path=lexical, raw=raw, text=text)


def _trusted_bash_path() -> str:
    """Use an OS-owned absolute Bash path; never search inherited PATH.

    On Windows the Git wrapper ``Git/bin/bash.exe`` prepends ``/mingw64/bin``,
    ``/usr/bin`` and ``/c/bin`` ahead of the PATH supplied through ``env``,
    which would let a writable ``C:\\bin`` shadow the trusted roots. The
    ``Git/usr/bin`` Bash keeps the supplied PATH authoritative.
    """
    candidates = (
        (Path("C:/Program Files/Git/usr/bin/bash.exe"), Path("C:/Program Files/Git/usr/bin"))
        if os.name == "nt"
        else (Path("/usr/bin/bash"), Path("/usr/bin"))
    )
    bash_path, _runtime_bin = candidates
    try:
        path_stat = os.lstat(bash_path)
    except OSError as exc:
        raise ScriptLauncherError("trusted system Bash is unavailable.") from exc
    reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))
    if (
        not stat.S_ISREG(path_stat.st_mode)
        or stat.S_ISLNK(path_stat.st_mode)
        or int(getattr(path_stat, "st_file_attributes", 0)) & reparse
        or not os.access(bash_path, os.X_OK)
    ):
        raise ScriptLauncherError("trusted system Bash is unavailable.")
    return str(bash_path)


def _trusted_runtime_path() -> str:
    """Supply only system-owned command paths, never the inherited PATH."""
    if os.name == "nt":
        roots = (
            Path("C:/Program Files/Git/usr/bin"),
            Path("C:/Program Files/Git/bin"),
            Path("C:/Windows/System32"),
            Path("C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin"),
        )
        return os.pathsep.join(str(path) for path in roots if path.is_dir())
    return "/usr/bin:/bin"


def resolve_azure_cli_executable() -> str:
    """Return an absolute path to the Azure CLI launcher for this platform.

    Windows ships the CLI as ``az.CMD``; ``CreateProcess`` only appends ``.exe``
    to an extension-less command, so passing the bare name ``"az"`` to
    :func:`subprocess.run` raises ``FileNotFoundError``. ``shutil.which``
    honours ``PATHEXT`` and resolves the real launcher. The trusted roots are
    searched first so a hijacked ``PATH`` cannot redirect the CLI, and the
    inherited ``PATH`` is only consulted when the CLI lives elsewhere.
    """
    resolved = shutil.which("az", path=_trusted_runtime_path()) or shutil.which("az")
    if not resolved:
        raise ScriptLauncherError(
            "Azure CLI (az) was not found on PATH; install it and run `az login`."
        )
    return resolved


def _resolve_deploy_identity_client_id(environment: Mapping[str, str]) -> str:
    """Read back the client ID Azure assigned to the prep-stage identity.

    The prep stage creates ``data-deploy-identity``; its client ID is generated
    by Azure and therefore cannot be part of the run-start snapshot. Reading it
    back here keeps it out of the operator-supplied inputs.
    """
    resource_group = environment.get("RESOURCE_GROUP", "")
    if not resource_group:
        raise ScriptLauncherError(
            "launcher environment must define RESOURCE_GROUP before reading "
            "back DATA_DEPLOY_IDENTITY_CLIENT_ID."
        )
    identity_id = environment.get("DATA_DEPLOY_IDENTITY_ID", "")
    identity_name = identity_id.rsplit("/", 1)[-1]
    if not identity_name:
        raise ScriptLauncherError(
            "launcher environment must define DATA_DEPLOY_IDENTITY_ID before "
            "reading back DATA_DEPLOY_IDENTITY_CLIENT_ID."
        )
    try:
        completed = subprocess.run(
            [
                resolve_azure_cli_executable(),
                "identity",
                "show",
                "--resource-group",
                resource_group,
                "--name",
                identity_name,
                "--query",
                "clientId",
                "--output",
                "tsv",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ScriptLauncherError(
            "launcher could not run the Azure CLI to read back "
            "DATA_DEPLOY_IDENTITY_CLIENT_ID."
        ) from exc
    client_id = completed.stdout.strip() if completed.returncode == 0 else ""
    if not client_id:
        raise ScriptLauncherError(
            "launcher could not read back DATA_DEPLOY_IDENTITY_CLIENT_ID; the "
            "prep stage must create the deploy identity first."
        )
    return client_id


def _resolve_azure_config_dir(parent: Mapping[str, str]) -> Optional[str]:
    """Return the Azure CLI configuration directory the child stages must use.

    The child environment is replaced wholesale, so the home variables the CLI
    relies on are gone. Without them ``az`` resolves its configuration to the
    relative path ``~/.azure``, loses the signed-in token and creates a stray
    ``~`` directory under the working directory. Passing the directory path is
    non-secret: the parent process already owns it.
    """
    explicit = (parent.get("AZURE_CONFIG_DIR") or "").strip()
    if explicit:
        return explicit
    home_key = "USERPROFILE" if os.name == "nt" else "HOME"
    home = (parent.get(home_key) or "").strip()
    if not home:
        return None
    return str(Path(home) / ".azure")


def _build_child_environment(
    parent: Mapping[str, str],
    stage: str,
) -> dict[str, str]:
    """Build the final allowlisted, non-secret environment for one stage."""
    allowed = _ASDW_DATA_DEPLOY_CHILD_CONTEXT_KEYS
    if stage == "prep":
        allowed = allowed | _ASDW_DATA_DEPLOY_PREP_ONLY_CONTEXT_KEYS
    environment = {
        key: value
        for key, value in parent.items()
        if key in allowed
    }
    for key in _HOST_RUNTIME_CONTEXT_KEYS:
        value = (parent.get(key) or "").strip()
        if value:
            environment[key] = value
    azure_config_dir = _resolve_azure_config_dir(parent)
    if azure_config_dir:
        environment["AZURE_CONFIG_DIR"] = azure_config_dir
    if os.name == "nt":
        # MSYS rewrites POSIX-looking arguments into Windows paths before it
        # hands them to a native executable, so an ARM scope such as
        # ``/subscriptions/<id>`` arrives as ``C:/Program Files/Git/subscriptions/<id>``
        # and the Azure CLI rejects it. Every filesystem path these stages pass
        # to a native tool is already in Windows form, so the conversion is
        # never needed here and disabling it is safe.
        environment["MSYS_NO_PATHCONV"] = "1"
        environment["MSYS2_ARG_CONV_EXCL"] = "*"
    if stage != "prep" and not environment.get("DATA_DEPLOY_IDENTITY_CLIENT_ID"):
        environment["DATA_DEPLOY_IDENTITY_CLIENT_ID"] = (
            _resolve_deploy_identity_client_id(environment)
        )
    environment["PATH"] = _trusted_runtime_path()
    environment["HVE_ASDW_SCRIPT_STAGE"] = stage
    return environment


def _require_verify_environment(values: Mapping[str, str]) -> None:
    """Fail closed when the sanitized launcher environment omits verifier keys.

    All stages receive one caller-supplied environment. The private-mode key set
    is the shared network contract SSOT (``_ASDW_DATA_DEPLOY_NETWORK_KEYS``)
    plus the approved verification image. ``DATA_VERIFY_RUN_ID`` is excluded
    because the launcher provisions it after this check.
    """
    mode = values.get("DATA_NETWORK_MODE", "")
    if not mode:
        raise ScriptLauncherError(
            "launcher environment must define DATA_NETWORK_MODE for the verifier "
            "(Step 1.3 environment contract; not a verify-script bug)."
        )
    if mode == "private":
        required = tuple(_ASDW_DATA_DEPLOY_NETWORK_KEYS) + ("DATA_VERIFY_ACI_IMAGE",)
        missing = [key for key in required if not values.get(key)]
        if missing:
            raise ScriptLauncherError(
                "launcher environment is missing required private-mode verifier "
                "keys (Step 1.3 caller contract; not a verify-script bug): "
                + ", ".join(missing)
            )


def _stage_snapshots(stage: str, repo_root: Path) -> dict[str, _Snapshot]:
    stage_paths = {
        "prep": {_PREP, _CREATE, _DESIGN, _SAMPLE},
        "create": {_PREP, _CREATE, _DESIGN, _SAMPLE},
        "registration": {_REGISTRATION, _DESIGN, _SAMPLE},
        "verify": {_VERIFY, _DESIGN, _SAMPLE},
    }
    paths = stage_paths[stage]
    crlf_tolerant = {_DESIGN, _SAMPLE}
    return {
        relative: _read_stable_utf8_file(
            repo_root / relative,
            repo_root,
            relative,
            allow_crlf=relative in crlf_tolerant,
        )
        for relative in paths
    }


def _validate_stage(
    stage: str,
    repo_root: Path,
    snapshots: Mapping[str, _Snapshot],
) -> list[str]:
    design = repo_root / _DESIGN
    sample = repo_root / _SAMPLE
    if stage in {"prep", "create"}:
        return validate_asdw_data_create_scripts(
            repo_root / _PREP,
            repo_root / _CREATE,
            design_doc_path=design,
            sample_data_path=sample,
            prep_text=snapshots[_PREP].text,
            create_text=snapshots[_CREATE].text,
            sample_data_text=snapshots[_SAMPLE].text,
            design_doc_text=snapshots[_DESIGN].text,
        )
    if stage == "registration":
        return validate_asdw_data_registration_script(
            repo_root / _REGISTRATION,
            design_doc_path=design,
            script_text=snapshots[_REGISTRATION].text,
            design_doc_text=snapshots[_DESIGN].text,
        )
    return validate_asdw_data_verify_script(
        repo_root / _VERIFY,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample,
        script_text=snapshots[_VERIFY].text,
        design_doc_text=snapshots[_DESIGN].text,
        sample_data_text=snapshots[_SAMPLE].text,
    )


def _audit_record_json(sample_data_text: str) -> str:
    """Return the one canonical AuditRecord from the validated sample snapshot."""
    try:
        data = json.loads(sample_data_text)
        records = data["entities"]["AuditRecord"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ScriptLauncherError(
            "sample data does not contain the canonical AuditRecord payload."
        ) from exc
    if (
        not isinstance(records, list)
        or len(records) != 1
        or not isinstance(records[0], dict)
    ):
        raise ScriptLauncherError(
            "sample data must contain exactly one canonical AuditRecord payload."
        )
    return json.dumps(
        records[0],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def execute_stage(
    stage: str,
    *,
    repo_root: Optional[Path] = None,
    environment: Optional[Mapping[str, str]] = None,
    process_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    _held_pipeline_lock: Optional[_StageExecutionLock] = None,
) -> int:
    """Validate and execute exactly one stage from the captured script bytes."""
    if stage not in _STAGES:
        raise ScriptLauncherError(f"unsupported ASDW data script stage: {stage!r}")
    root = (repo_root or Path.cwd()).resolve()
    parent_environment = (
        dict(environment) if environment is not None else dict(os.environ)
    )
    stage_markers = _stage_success_marker_paths(root, parent_environment)
    lock_path = (
        _stage_execution_lock_path(stage_markers)
        if stage_markers is not None
        else None
    )
    stage_lock: Optional[_StageExecutionLock] = None
    owns_stage_lock = False
    primary_error: Optional[BaseException] = None
    stage_return_code: Optional[int] = None
    try:
        if lock_path is not None:
            if _held_pipeline_lock is None:
                stage_lock = _acquire_stage_execution_lock(lock_path)
                owns_stage_lock = True
            elif _held_pipeline_lock.path != lock_path:
                raise ScriptLauncherError(
                    "HVE data pipeline lock does not match the current run."
                )
            else:
                stage_lock = _held_pipeline_lock
        if stage_markers is not None:
            for invalidated_stage in _STAGE_MARKER_INVALIDATIONS[stage]:
                _clear_stage_success_marker(
                    stage_markers[invalidated_stage],
                    invalidated_stage,
                )
            predecessor = _STAGE_PREDECESSORS.get(stage)
            if predecessor is not None:
                _require_stage_success_marker(
                    stage_markers[predecessor],
                    required_stage=predecessor,
                    requested_stage=stage,
                    run_id=str(parent_environment["HVE_RUN_ID"]),
                )
        snapshots = _stage_snapshots(stage, root)
        errors = _validate_stage(stage, root, snapshots)
        if errors:
            raise ScriptLauncherError(
                "ASDW data script contract failed: " + " | ".join(errors[:5])
            )

        script_key = {
            "prep": _PREP,
            "create": _CREATE,
            "registration": _REGISTRATION,
            "verify": _VERIFY,
        }[stage]
        script = snapshots[script_key]
        bash = _trusted_bash_path()
        env = _build_child_environment(parent_environment, stage)
        if stage == "verify":
            # The verifier receives the same sanitized caller environment as
            # prep/create/registration. No intermediate file is read, avoiding
            # stale cross-run state and a second configuration source.
            _require_verify_environment(env)
        env["HVE_ASDW_SCRIPT_DIR"] = str(script.path.parent)
        env["HVE_ASDW_SCRIPT_STAGE"] = stage
        run_id_key = _STAGE_RUN_ID_KEYS.get(stage)
        if run_id_key is not None and not _RUN_ID_PATTERN.fullmatch(env.get(run_id_key, "")):
            # Every invocation owns a distinct stage-scoped run ID. In
            # particular, the second create/registration/verify pass must not
            # reuse a first-pass ACI name. No external step must export it.
            # secrets.token_hex(16) yields 32 lowercase hex chars.
            env[run_id_key] = secrets.token_hex(16)
        if stage == "create":
            env["HVE_ASDW_SAMPLE_DATA_JSON"] = snapshots[_SAMPLE].text
        if stage == "registration":
            env["AUDIT_RECORD_JSON"] = _audit_record_json(
                snapshots[_SAMPLE].text
            )
        result = process_runner(
            [bash, "--noprofile", "--norc", "-s"],
            cwd=str(root),
            env=env,
            input=script.raw,
            text=False,
            check=False,
        )
        return_code = int(result.returncode)
        stage_return_code = return_code
        if stage in _STAGE_SUCCESS_MARKERS and stage_markers is not None and return_code == 0:
            _write_stage_success_marker(
                stage_markers[stage],
                stage,
                str(parent_environment["HVE_RUN_ID"]),
            )
        return return_code
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        if stage_lock is not None and owns_stage_lock:
            _release_stage_execution_lock_after_stage(
                stage_lock,
                primary_error,
                stage_return_code,
                stage_markers,
                stage,
            )


def execute_pipeline(
    *,
    repo_root: Optional[Path] = None,
    environment: Optional[Mapping[str, str]] = None,
    process_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[StageResult, ...]:
    """Run the fixed Step 1.3 sequence and its idempotency pass under one lock."""
    root = (repo_root or Path.cwd()).resolve()
    parent_environment = (
        dict(environment) if environment is not None else dict(os.environ)
    )
    stage_markers = _stage_success_marker_paths(root, parent_environment)
    if stage_markers is None:
        raise ScriptLauncherError(
            "HVE data pipeline requires a canonical run context."
        )
    pipeline_lock = _acquire_stage_execution_lock(
        _stage_execution_lock_path(stage_markers)
    )
    results: list[StageResult] = []
    primary_error: Optional[BaseException] = None
    last_return_code: Optional[int] = None
    last_stage = "prep"
    try:
        for stage, attempt in (
            ("prep", 1),
            ("create", 1),
            ("registration", 1),
            ("verify", 1),
            ("create", 2),
            ("registration", 2),
            ("verify", 2),
        ):
            last_stage = stage
            exit_code = execute_stage(
                stage,
                repo_root=root,
                environment=parent_environment,
                process_runner=process_runner,
                _held_pipeline_lock=pipeline_lock,
            )
            last_return_code = exit_code
            results.append(
                StageResult(
                    stage=stage,
                    attempt=attempt,
                    exit_code=exit_code,
                    reached=True,
                    evidence=f"process-exit={exit_code}",
                )
            )
            if exit_code != 0:
                break
        return tuple(results)
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        _release_stage_execution_lock_after_stage(
            pipeline_lock,
            primary_error,
            last_return_code,
            stage_markers,
            last_stage,
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=sorted(_STAGES))
    args = parser.parse_args(argv)
    try:
        return execute_stage(args.stage)
    except ScriptLauncherError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
