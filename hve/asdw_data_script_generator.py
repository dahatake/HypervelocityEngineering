from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import tempfile
from types import MappingProxyType
from typing import BinaryIO

from hve.artifact_validation import (
    _ASDW_ACL_AUDIT_REGISTRATION_SOURCE,
    _ASDW_APP009_SQL_COVERAGE,
    _ASDW_AUDIT_MODE_ACL_DIRECT,
    _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST,
    _ASDW_NON_AUDIT_ID_FIELDS,
    _ASDW_SQL_AUDIT_REGISTRATION_SOURCE,
    _build_asdw_non_audit_aci_command,
    _load_asdw_sample_counts,
    _resolve_asdw_audit_storage_mode,
    validate_asdw_data_create_scripts,
    validate_asdw_data_registration_script,
)
from hve.asdw_data_script_launcher import (
    ScriptLauncherError,
    _validate_stage_execution_lock_path,
    _validate_direct_repo_directory,
)

_PREP_PATH = "src/infra/azure/create-azure-data-resources-prep.sh"
_CREATE_PATH = "src/infra/azure/create-azure-data-resources.sh"
_REGISTRATION_PATH = "src/data/azure/data-registration-script.sh"
_PRODUCER_PATHS = (_PREP_PATH, _CREATE_PATH, _REGISTRATION_PATH)
_DESIGN_PATH = "docs/azure/azure-services-data.md"
_SAMPLE_DATA_PATH = "src/data/sample-data.json"
_REQUIRED_ENTITIES = tuple(
    entity for entity, _database, _table in _ASDW_APP009_SQL_COVERAGE
) + ("VocRecord", "AuditRecord")
_REQUIRED_ID_FIELDS = {
    **{
        entity: _ASDW_NON_AUDIT_ID_FIELDS[entity]
        for entity in _REQUIRED_ENTITIES
        if entity != "AuditRecord"
    },
    "AuditRecord": "auditEventId",
}


class AsdwDataScriptGenerationError(RuntimeError):
    """Raised when the ASDW data producer scripts cannot be generated safely."""


class _ProducerConcurrentModificationError(AsdwDataScriptGenerationError):
    """Raised when a fixed producer changes after the initial snapshot."""


@dataclass(frozen=True)
class AsdwDataScriptGenerationResult:
    """Sanitized outcome of the fixed-path producer freshness gate."""

    status: str
    summary: str
    audit_mode: str


@dataclass(frozen=True)
class _StableFileSnapshot:
    raw: bytes
    text: str
    identity: os.stat_result


@dataclass(frozen=True)
class _OwnedPath:
    path: Path
    identity: os.stat_result | None


@dataclass
class _ProducerLockGuard:
    path: Path
    stream: BinaryIO | None = None
    descriptor: int = -1
    acquired: bool = False

    def acquire(self) -> None:
        try:
            self.stream = open(
                self.path,
                "a+b",
                buffering=0,
            )
            self.descriptor = self.stream.fileno()
            _validate_stage_execution_lock_path(self.path, self.descriptor)
            if os.fstat(self.descriptor).st_size == 0:
                os.write(self.descriptor, b"\0")
            os.lseek(self.descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.descriptor, msvcrt.LK_NBLCK, 1)
            else:
                fcntl = __import__("fcntl")

                fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.acquired = True
        except BaseException as primary_error:
            try:
                self.close()
            except BaseException as cleanup_error:
                primary_error.add_note("lock acquisition cleanup also failed")
                primary_error.__context__ = cleanup_error
            raise

    def close(self) -> None:
        descriptor = self.descriptor
        stream = self.stream
        if stream is None:
            return
        self.stream = None
        self.descriptor = -1
        unlock_error: BaseException | None = None
        if self.acquired and descriptor >= 0:
            try:
                os.lseek(descriptor, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl = __import__("fcntl")

                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            except BaseException as exc:
                unlock_error = exc
        self.acquired = False
        close_error: BaseException | None = None
        for _attempt in range(2):
            try:
                stream.close()
                break
            except BaseException as exc:
                if close_error is None:
                    close_error = exc
        if close_error is not None:
            if unlock_error is None:
                unlock_error = close_error
            else:
                unlock_error.add_note("lock descriptor close also failed")
        if unlock_error is not None:
            if not isinstance(unlock_error, OSError):
                raise unlock_error
            raise ScriptLauncherError(
                "ASDW data producer generation lock cannot be released."
            ) from unlock_error


def ensure_asdw_data_producers(
    repo_root: Path,
) -> AsdwDataScriptGenerationResult:
    """Reuse valid producers or safely promote one validated fixed-path set."""
    root = Path(repo_root).resolve()
    lock = _ProducerLockGuard(_producer_lock_path(root))
    primary_error: BaseException | None = None
    try:
        lock.acquire()
    except (OSError, ScriptLauncherError):
        raise AsdwDataScriptGenerationError(
            "ASDW data producer generation lock is unavailable."
        ) from None
    try:
        return _ensure_asdw_data_producers_locked(root)
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            lock.close()
        except BaseException as cleanup_error:
            if primary_error is not None:
                primary_error.add_note(
                    "ASDW data producer generation lock cleanup also failed."
                )
                primary_error.__context__ = cleanup_error
            else:
                if not isinstance(cleanup_error, ScriptLauncherError):
                    raise
                raise AsdwDataScriptGenerationError(
                    "ASDW data producer generation lock cleanup failed."
                ) from None


def _ensure_asdw_data_producers_locked(
    root: Path,
) -> AsdwDataScriptGenerationResult:
    stage = "input-validation"
    try:
        design_text, sample_data_text = _read_generation_inputs(root)
        audit_mode = _resolve_audit_mode(design_text)
        originals = _read_existing_producer_snapshots(root)
        if len(originals) == len(_PRODUCER_PATHS):
            stage = "current-artifact-validation"
            current_texts = {
                relative_path: snapshot.text
                for relative_path, snapshot in originals.items()
            }
            if not _producer_validation_errors(
                design_text=design_text,
                sample_data_text=sample_data_text,
                texts=current_texts,
            ):
                _assert_current_producer_set(root, originals)
                return AsdwDataScriptGenerationResult(
                    status="reused",
                    summary=(
                        "ASDW data producers passed current validation and were reused."
                    ),
                    audit_mode=audit_mode,
                )

        stage = "producer-rendering"
        rendered = render_asdw_data_producers(
            design_text=design_text,
            sample_data_text=sample_data_text,
        )
        stage = "generated-artifact-validation"
        generated = _validated_generated_bytes(
            rendered,
            design_text=design_text,
            sample_data_text=sample_data_text,
        )
        stage = "producer-promotion"
        _promote_generated_set(root, originals, generated)
        return AsdwDataScriptGenerationResult(
            status="regenerated",
            summary="ASDW data producers were regenerated from validated inputs.",
            audit_mode=audit_mode,
        )
    except AsdwDataScriptGenerationError:
        raise
    except Exception as exc:
        raise AsdwDataScriptGenerationError(
            "ASDW data producer generation failed during "
            f"{stage} with {exc.__class__.__name__}."
        ) from None


def _producer_lock_path(repo_root: Path) -> Path:
    try:
        lock_root = (
            Path(tempfile.gettempdir()).resolve()
            / "hve-asdw-producer-locks"
        )
        lock_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root_stat = os.lstat(lock_root)
        reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or stat.S_ISLNK(root_stat.st_mode)
            or int(getattr(root_stat, "st_file_attributes", 0)) & reparse
        ):
            raise OSError("producer lock root is unsafe")
        if os.name != "nt":
            geteuid = vars(os).get("geteuid")
            if not callable(geteuid) or (
                root_stat.st_uid != geteuid()
                or stat.S_IMODE(root_stat.st_mode) & 0o077
            ):
                raise OSError("producer lock root ownership or mode is unsafe")
    except (OSError, RuntimeError):
        raise AsdwDataScriptGenerationError(
            "ASDW producer generation lock directory is unavailable."
        ) from None
    identity = hashlib.sha256(
        os.path.normcase(str(repo_root)).encode("utf-8")
    ).hexdigest()
    return lock_root / f"{identity}.lock"


def _read_generation_inputs(repo_root: Path) -> tuple[str, str]:
    design = _read_stable_text_file(
        repo_root / _DESIGN_PATH,
        repo_root,
        "ASDW data design",
        allow_crlf=True,
    )
    sample = _read_stable_text_file(
        repo_root / _SAMPLE_DATA_PATH,
        repo_root,
        "ASDW sample data",
        allow_crlf=True,
    )
    return design.text, sample.text


def _read_existing_producer_snapshots(
    repo_root: Path,
) -> dict[str, _StableFileSnapshot]:
    snapshots: dict[str, _StableFileSnapshot] = {}
    for relative_path in _PRODUCER_PATHS:
        target = repo_root / relative_path
        try:
            os.lstat(target)
        except FileNotFoundError:
            continue
        except OSError:
            raise AsdwDataScriptGenerationError(
                "Existing ASDW data producer failed stable UTF-8 validation."
            ) from None
        snapshots[relative_path] = _read_stable_text_file(
            target,
            repo_root,
            "ASDW data producer",
            allow_crlf=False,
        )
    return snapshots


def _read_stable_text_file(
    path: Path,
    repo_root: Path,
    label: str,
    *,
    allow_crlf: bool,
) -> _StableFileSnapshot:
    """Read one stable direct regular file and optionally normalize CRLF to LF."""
    root = repo_root.resolve()
    lexical = Path(os.path.abspath(path))
    try:
        lexical.relative_to(root)
    except ValueError:
        raise AsdwDataScriptGenerationError(
            f"{label} path escapes the repository root."
        ) from None

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(lexical, flags)
        opened = os.fstat(descriptor)
        path_stat = os.lstat(lexical)
        reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or not stat.S_ISREG(path_stat.st_mode)
            or stat.S_ISLNK(path_stat.st_mode)
            or int(getattr(path_stat, "st_file_attributes", 0)) & reparse
            or not os.path.samestat(opened, path_stat)
        ):
            raise OSError("file identity is unsafe")
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root)
        if os.path.normcase(str(resolved)) != os.path.normcase(str(lexical)):
            raise OSError("file path is not lexical and direct")
        raw = _read_descriptor_bytes(descriptor)
        repeated = _read_descriptor_bytes(descriptor)
        final = os.fstat(descriptor)
        final_path_stat = os.lstat(lexical)
        if (
            not os.path.samestat(opened, final)
            or opened.st_size != final.st_size
            or opened.st_mtime_ns != final.st_mtime_ns
            or stat.S_ISLNK(final_path_stat.st_mode)
            or int(getattr(final_path_stat, "st_file_attributes", 0)) & reparse
            or not os.path.samestat(opened, final_path_stat)
            or raw != repeated
        ):
            raise OSError("file changed while it was read")
        final_resolved = lexical.resolve(strict=True)
        final_resolved.relative_to(root)
        if os.path.normcase(str(final_resolved)) != os.path.normcase(str(lexical)):
            raise OSError("file path changed while it was read")
    except (OSError, UnicodeError, ValueError):
        raise AsdwDataScriptGenerationError(
            f"{label} failed stable UTF-8 validation."
        ) from None
    finally:
        if descriptor >= 0:
            active_error = sys.exception()
            try:
                os.close(descriptor)
            except OSError:
                if active_error is None:
                    raise AsdwDataScriptGenerationError(
                        f"{label} failed stable UTF-8 validation."
                    ) from None
                active_error.add_note("stable file descriptor cleanup also failed")

    if raw.startswith(b"\xef\xbb\xbf"):
        raise AsdwDataScriptGenerationError(
            f"{label} failed stable UTF-8 validation."
        )
    normalized = raw.replace(b"\r\n", b"\n") if allow_crlf else raw
    if b"\r" in normalized:
        raise AsdwDataScriptGenerationError(
            f"{label} failed stable UTF-8 validation."
        )
    try:
        text = normalized.decode("utf-8")
    except UnicodeDecodeError:
        raise AsdwDataScriptGenerationError(
            f"{label} failed stable UTF-8 validation."
        ) from None
    return _StableFileSnapshot(
        raw=raw,
        text=text,
        identity=final_path_stat,
    )


def _read_descriptor_bytes(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _validated_generated_bytes(
    rendered: Mapping[str, bytes],
    *,
    design_text: str,
    sample_data_text: str,
) -> dict[str, bytes]:
    if tuple(rendered) != _PRODUCER_PATHS:
        raise AsdwDataScriptGenerationError(
            "Generated ASDW producer set failed fixed-path validation."
        )
    texts: dict[str, str] = {}
    generated: dict[str, bytes] = {}
    for relative_path in _PRODUCER_PATHS:
        payload = rendered[relative_path]
        if (
            not isinstance(payload, bytes)
            or payload.startswith(b"\xef\xbb\xbf")
            or b"\r" in payload
        ):
            raise AsdwDataScriptGenerationError(
                "Generated ASDW producer set failed UTF-8/LF validation."
            )
        try:
            texts[relative_path] = payload.decode("utf-8")
        except UnicodeDecodeError:
            raise AsdwDataScriptGenerationError(
                "Generated ASDW producer set failed UTF-8/LF validation."
            ) from None
        generated[relative_path] = payload
    if _producer_validation_errors(
        design_text=design_text,
        sample_data_text=sample_data_text,
        texts=texts,
    ):
        raise AsdwDataScriptGenerationError(
            "Generated ASDW producer set failed current artifact validation."
        )
    return generated


def _producer_validation_errors(
    *,
    design_text: str,
    sample_data_text: str,
    texts: Mapping[str, str],
) -> list[str]:
    errors = validate_asdw_data_create_scripts(
        _PREP_PATH,
        _CREATE_PATH,
        design_doc_path=_DESIGN_PATH,
        sample_data_path=_SAMPLE_DATA_PATH,
        prep_text=texts[_PREP_PATH],
        create_text=texts[_CREATE_PATH],
        design_doc_text=design_text,
        sample_data_text=sample_data_text,
    )
    errors.extend(
        validate_asdw_data_registration_script(
            _REGISTRATION_PATH,
            design_doc_path=_DESIGN_PATH,
            script_text=texts[_REGISTRATION_PATH],
            design_doc_text=design_text,
        )
    )
    return errors


def _promote_generated_set(
    repo_root: Path,
    originals: Mapping[str, _StableFileSnapshot],
    generated: Mapping[str, bytes],
) -> None:
    temporary_paths: list[_OwnedPath] = []
    created_directories: list[_OwnedPath] = []
    promoted: dict[str, _StableFileSnapshot] = {}
    attempted: tuple[str, _OwnedPath] | None = None
    try:
        for relative_path in _PRODUCER_PATHS:
            target = repo_root / relative_path
            _ensure_safe_target_parent(
                repo_root,
                target.parent,
                created_directories,
            )
            _write_same_directory_temp(
                repo_root,
                target,
                generated[relative_path],
                tracked_paths=temporary_paths,
            )
        _assert_current_producer_set(repo_root, originals)
        for relative_path, temporary in zip(
            _PRODUCER_PATHS,
            tuple(temporary_paths),
            strict=True,
        ):
            target = repo_root / relative_path
            _assert_temporary_payload(
                repo_root,
                temporary,
                generated[relative_path],
            )
            _assert_target_matches_snapshot(
                repo_root,
                target,
                originals.get(relative_path),
            )
            attempted = (relative_path, temporary)
            os.replace(temporary.path, target)
            promoted_snapshot = _read_stable_text_file(
                target,
                repo_root,
                "promoted ASDW data producer",
                allow_crlf=False,
            )
            if (
                promoted_snapshot.raw != generated[relative_path]
                or not os.path.samestat(
                    _require_owned_identity(temporary),
                    promoted_snapshot.identity,
                )
            ):
                raise _ProducerConcurrentModificationError(
                    "ASDW producer target changed after the initial snapshot."
                )
            promoted[relative_path] = promoted_snapshot
            attempted = None
            temporary_paths.remove(temporary)
        _assert_promoted_set(repo_root, promoted, generated)
    except BaseException as exc:
        ownership_lost = isinstance(exc, _ProducerConcurrentModificationError)
        if attempted is not None:
            relative_path, temporary = attempted
            target = repo_root / relative_path
            try:
                current = _read_stable_text_file(
                    target,
                    repo_root,
                    "attempted ASDW data producer",
                    allow_crlf=False,
                )
                if (
                    current.raw == generated[relative_path]
                    and os.path.samestat(
                        _require_owned_identity(temporary),
                        current.identity,
                    )
                ):
                    promoted[relative_path] = current
                elif not _target_matches_snapshot(
                    repo_root,
                    target,
                    originals.get(relative_path),
                ):
                    ownership_lost = True
            except AsdwDataScriptGenerationError:
                if not _target_matches_snapshot(
                    repo_root,
                    target,
                    originals.get(relative_path),
                ):
                    ownership_lost = True
        rollback_error = _rollback_producer_set(
            repo_root,
            originals,
            promoted,
        )
        cleanup_error = _cleanup_temporary_paths(temporary_paths)
        directory_cleanup_error = _cleanup_created_directories(created_directories)
        if not isinstance(exc, Exception):
            if ownership_lost:
                exc.add_note("producer target ownership changed during cancellation")
            if rollback_error is not None:
                exc.add_note("snapshot rollback was not completed during cancellation")
                exc.__context__ = rollback_error
            if cleanup_error or directory_cleanup_error:
                exc.add_note("temporary cleanup was incomplete during cancellation")
            raise
        if rollback_error is not None:
            if ownership_lost:
                raise AsdwDataScriptGenerationError(
                    "ASDW producer promotion failed after concurrent target ownership "
                    "change; snapshot rollback was not completed."
                ) from None
            raise AsdwDataScriptGenerationError(
                "ASDW producer promotion and snapshot rollback failed."
            ) from None
        if cleanup_error or directory_cleanup_error:
            if ownership_lost:
                raise AsdwDataScriptGenerationError(
                    "ASDW producer promotion failed after concurrent target ownership "
                    "change; temporary cleanup was incomplete."
                ) from None
            raise AsdwDataScriptGenerationError(
                "ASDW producer promotion failed; the original snapshot was restored "
                "but temporary cleanup was incomplete."
            ) from None
        if ownership_lost:
            raise _ProducerConcurrentModificationError(
                "ASDW producer target changed after the initial snapshot."
            ) from None
        if isinstance(exc, _ProducerConcurrentModificationError):
            raise exc
        if (
            isinstance(exc, AsdwDataScriptGenerationError)
            and "cleanup was incomplete" in str(exc)
        ):
            raise exc
        raise AsdwDataScriptGenerationError(
            "ASDW producer promotion failed and the original snapshot was restored."
        ) from None


def _rollback_producer_set(
    repo_root: Path,
    originals: Mapping[str, _StableFileSnapshot],
    promoted: Mapping[str, _StableFileSnapshot],
) -> BaseException | None:
    errors: list[BaseException] = []
    restored_identities: dict[str, os.stat_result] = {}
    for relative_path, owned in promoted.items():
        target = repo_root / relative_path
        try:
            current = _read_stable_text_file(
                target,
                repo_root,
                "ASDW producer rollback target",
                allow_crlf=False,
            )
            if (
                current.raw != owned.raw
                or not os.path.samestat(current.identity, owned.identity)
            ):
                raise OSError("rollback target ownership changed")
            original = originals.get(relative_path)
            if original is None:
                _unlink_owned_path(_OwnedPath(target, current.identity))
                continue
            rollback_paths: list[_OwnedPath] = []
            rollback_temp = _write_same_directory_temp(
                repo_root,
                target,
                original.raw,
                tracked_paths=rollback_paths,
            )
            try:
                _assert_owned_path(rollback_temp, require_directory=False)
                _assert_target_matches_snapshot(repo_root, target, owned)
                os.replace(rollback_temp.path, target)
                restored = _read_stable_text_file(
                    target,
                    repo_root,
                    "restored ASDW data producer",
                    allow_crlf=False,
                )
                if (
                    restored.raw != original.raw
                    or not os.path.samestat(
                        restored.identity,
                        _require_owned_identity(rollback_temp),
                    )
                ):
                    raise OSError("rollback result identity changed")
                restored_identities[relative_path] = restored.identity
            finally:
                _cleanup_temporary_paths(rollback_paths)
        except BaseException as exc:
            errors.append(exc)
    for relative_path in promoted:
        target = repo_root / relative_path
        original = originals.get(relative_path)
        try:
            if original is None:
                if target.exists() or target.is_symlink():
                    raise OSError("originally missing producer still exists")
                continue
            restored = _read_stable_text_file(
                target,
                repo_root,
                "restored ASDW data producer",
                allow_crlf=False,
            )
            expected_identity = restored_identities.get(relative_path)
            if (
                restored.raw != original.raw
                or expected_identity is None
                or not os.path.samestat(restored.identity, expected_identity)
            ):
                raise OSError("restored producer does not match snapshot")
        except BaseException as exc:
            errors.append(exc)
    return errors[0] if errors else None


def _assert_current_producer_set(
    repo_root: Path,
    originals: Mapping[str, _StableFileSnapshot],
) -> None:
    for relative_path in _PRODUCER_PATHS:
        _assert_target_matches_snapshot(
            repo_root,
            repo_root / relative_path,
            originals.get(relative_path),
        )


def _assert_promoted_set(
    repo_root: Path,
    promoted: Mapping[str, _StableFileSnapshot],
    generated: Mapping[str, bytes],
) -> None:
    if tuple(promoted) != _PRODUCER_PATHS:
        raise _ProducerConcurrentModificationError(
            "ASDW producer target changed after the initial snapshot."
        )
    for relative_path in _PRODUCER_PATHS:
        current = _read_stable_text_file(
            repo_root / relative_path,
            repo_root,
            "final ASDW data producer",
            allow_crlf=False,
        )
        if (
            current.raw != generated[relative_path]
            or not os.path.samestat(
                current.identity,
                promoted[relative_path].identity,
            )
        ):
            raise _ProducerConcurrentModificationError(
                "ASDW producer target changed after the initial snapshot."
            )


def _assert_target_matches_snapshot(
    repo_root: Path,
    target: Path,
    expected: _StableFileSnapshot | None,
) -> None:
    _validate_target_parent(repo_root, target.parent)
    if expected is None:
        try:
            os.lstat(target)
        except FileNotFoundError:
            _validate_target_parent(repo_root, target.parent)
            return
        except OSError:
            pass
        raise _ProducerConcurrentModificationError(
            "ASDW producer target changed after the initial snapshot."
        )
    try:
        current = _read_stable_text_file(
            target,
            repo_root,
            "current ASDW data producer",
            allow_crlf=False,
        )
    except AsdwDataScriptGenerationError:
        raise _ProducerConcurrentModificationError(
            "ASDW producer target changed after the initial snapshot."
        ) from None
    if (
        current.raw != expected.raw
        or not os.path.samestat(current.identity, expected.identity)
    ):
        raise _ProducerConcurrentModificationError(
            "ASDW producer target changed after the initial snapshot."
        )


def _target_matches_snapshot(
    repo_root: Path,
    target: Path,
    expected: _StableFileSnapshot | None,
) -> bool:
    if expected is None:
        try:
            os.lstat(target)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return False
    try:
        current = _read_stable_text_file(
            target,
            repo_root,
            "ASDW data producer snapshot check",
            allow_crlf=False,
        )
    except AsdwDataScriptGenerationError:
        return False
    return (
        current.raw == expected.raw
        and os.path.samestat(current.identity, expected.identity)
    )


def _assert_temporary_payload(
    repo_root: Path,
    owned: _OwnedPath,
    expected: bytes,
) -> None:
    snapshot = _read_stable_text_file(
        owned.path,
        repo_root,
        "generated ASDW producer temporary file",
        allow_crlf=False,
    )
    if (
        snapshot.raw != expected
        or not os.path.samestat(
            snapshot.identity,
            _require_owned_identity(owned),
        )
    ):
        raise AsdwDataScriptGenerationError(
            "Generated ASDW producer temporary file changed before promotion."
        )


def _ensure_safe_target_parent(
    repo_root: Path,
    parent: Path,
    created_directories: list[_OwnedPath],
) -> Path:
    root = repo_root.resolve()
    lexical_parent = Path(os.path.abspath(parent))
    try:
        relative = lexical_parent.relative_to(root)
    except ValueError:
        raise AsdwDataScriptGenerationError(
            "ASDW producer target parent escapes the repository."
        ) from None
    current = root
    for part in relative.parts:
        current = current / part
        try:
            os.lstat(current)
        except FileNotFoundError:
            existed = False
        except OSError:
            existed = True
        else:
            existed = True
        if not existed:
            pending = _OwnedPath(path=current, identity=None)
            _register_owned_path(created_directories, pending)
            try:
                current.mkdir()
            except FileExistsError:
                created_directories.remove(pending)
            else:
                current_stat = os.lstat(current)
                created_directories[created_directories.index(pending)] = _OwnedPath(
                    path=current,
                    identity=current_stat,
                )
        _validate_target_parent(root, current)
    return _validate_target_parent(root, lexical_parent)


def _validate_target_parent(repo_root: Path, parent: Path) -> Path:
    try:
        return _validate_direct_repo_directory(
            repo_root,
            parent,
            "ASDW producer target parent",
        )
    except ScriptLauncherError:
        raise AsdwDataScriptGenerationError(
            "ASDW producer target parent failed repository safety validation."
        ) from None


def _write_same_directory_temp(
    repo_root: Path,
    target: Path,
    payload: bytes,
    *,
    tracked_paths: list[_OwnedPath],
) -> _OwnedPath:
    parent = _validate_target_parent(repo_root, target.parent)
    temporary_path: Path | None = None
    stream: BinaryIO | None = None
    opened: os.stat_result | None = None
    for _attempt in range(10):
        candidate = parent / f".hve-asdw-producer-{secrets.token_hex(16)}.tmp"
        temporary_path = candidate
        pending = _OwnedPath(path=candidate, identity=None)
        _register_owned_path(tracked_paths, pending)
        try:
            stream = open(
                candidate,
                "x+b",
                buffering=0,
            )
            break
        except FileExistsError:
            tracked_paths.remove(pending)
            continue
        except BaseException as primary_error:
            cleanup_records = [pending]
            cleanup_failed = _cleanup_temporary_paths(cleanup_records)
            tracked_paths[:] = [
                item for item in tracked_paths if item.path != candidate
            ]
            if cleanup_failed:
                primary_error.add_note(
                    "temporary initialization cleanup was incomplete"
                )
            raise
    if stream is None or temporary_path is None:
        raise AsdwDataScriptGenerationError(
            "Generated ASDW producer temporary file could not be created."
        )
    try:
        opened = os.fstat(stream.fileno())
        path_stat = os.lstat(temporary_path)
        reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or not stat.S_ISREG(path_stat.st_mode)
            or stat.S_ISLNK(path_stat.st_mode)
            or int(getattr(path_stat, "st_file_attributes", 0)) & reparse
            or not os.path.samestat(opened, path_stat)
        ):
            raise OSError("temporary file identity is unsafe")
        owned = _OwnedPath(path=temporary_path, identity=opened)
        tracked_paths[tracked_paths.index(pending)] = owned
        resolved = temporary_path.resolve(strict=True)
        resolved.relative_to(repo_root.resolve())
        if os.path.normcase(str(resolved)) != os.path.normcase(
            str(Path(os.path.abspath(temporary_path)))
        ):
            raise OSError("temporary file path is not lexical")
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
        stream.close()
        final_stat = os.lstat(temporary_path)
        if not os.path.samestat(opened, final_stat):
            raise OSError("temporary file identity changed while it was written")
        final_owned = _OwnedPath(path=temporary_path, identity=final_stat)
        tracked_paths[tracked_paths.index(owned)] = final_owned
    except BaseException as primary_error:
        if stream is not None:
            try:
                stream.close()
            except BaseException as cleanup_error:
                primary_error.add_note("temporary descriptor cleanup also failed")
        cleanup_failed = False
        try:
            current_stat = os.lstat(temporary_path)
        except FileNotFoundError:
            pass
        except OSError:
            cleanup_failed = True
        else:
            if opened is not None and os.path.samestat(opened, current_stat):
                try:
                    temporary_path.unlink(missing_ok=True)
                except BaseException:
                    cleanup_failed = True
            else:
                cleanup_failed = True
        cleanup_records = [
            item for item in tracked_paths if item.path == temporary_path
        ]
        if cleanup_records:
            cleanup_failed = (
                _cleanup_temporary_paths(cleanup_records)
                or cleanup_failed
            )
        if not cleanup_failed:
            tracked_paths[:] = [
                item for item in tracked_paths if item.path != temporary_path
            ]
        if cleanup_failed:
            if not isinstance(primary_error, Exception):
                primary_error.add_note("temporary cleanup was incomplete")
                raise
            raise AsdwDataScriptGenerationError(
                "Generated ASDW producer temporary initialization failed; "
                "temporary cleanup was incomplete."
            ) from None
        raise
    return final_owned


def _cleanup_temporary_paths(paths: list[_OwnedPath]) -> bool:
    failed = False
    for owned in tuple(paths):
        try:
            _unlink_owned_path(owned)
            paths.remove(owned)
        except BaseException:
            failed = True
    return failed


def _register_owned_path(paths: list[_OwnedPath], owned: _OwnedPath) -> None:
    paths.append(owned)


def _cleanup_created_directories(paths: list[_OwnedPath]) -> bool:
    failed = False
    for owned in reversed(paths):
        if owned.identity is None:
            failed = True
            continue
        try:
            _assert_owned_path(owned, require_directory=True)
            owned.path.rmdir()
        except FileNotFoundError:
            continue
        except BaseException:
            failed = True
    return failed


def _assert_owned_path(owned: _OwnedPath, *, require_directory: bool) -> None:
    if owned.identity is None:
        raise OSError("owned path identity is unconfirmed")
    current = os.lstat(owned.path)
    reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))
    expected_type = stat.S_ISDIR if require_directory else stat.S_ISREG
    if (
        not expected_type(current.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or int(getattr(current, "st_file_attributes", 0)) & reparse
        or not os.path.samestat(current, owned.identity)
    ):
        raise OSError("owned path identity changed")


def _require_owned_identity(owned: _OwnedPath) -> os.stat_result:
    if owned.identity is None:
        raise AsdwDataScriptGenerationError(
            "ASDW producer temporary ownership was not established."
        )
    return owned.identity


def _unlink_owned_path(owned: _OwnedPath) -> None:
    if owned.identity is None:
        try:
            current = os.lstat(owned.path)
        except FileNotFoundError:
            return
        reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))
        if (
            not stat.S_ISREG(current.st_mode)
            or current.st_nlink != 1
            or current.st_size != 0
            or stat.S_ISLNK(current.st_mode)
            or int(getattr(current, "st_file_attributes", 0)) & reparse
            or not owned.path.name.startswith(".hve-asdw-producer-")
            or owned.path.suffix != ".tmp"
        ):
            raise OSError("pending temporary path ownership is unconfirmed")
        owned.path.unlink()
        return
    try:
        _assert_owned_path(owned, require_directory=False)
    except FileNotFoundError:
        return
    owned.path.unlink()


def render_asdw_data_producers(
    *,
    design_text: str,
    sample_data_text: str,
) -> Mapping[str, bytes]:
    """Render the three ASDW Step 1.3 producer scripts as deterministic bytes."""
    stage = "audit-mode-resolution"
    try:
        audit_mode = _resolve_audit_mode(design_text)
        stage = "sample-validation"
        counts = _load_required_sample_counts(sample_data_text)
        _validate_required_sample_records(sample_data_text)
        stage = "producer-rendering"
        prep_text = _render_prep_script()
        create_text = _render_create_script(audit_mode, counts)
        registration_text = _render_registration_script(audit_mode)
        stage = "artifact-self-validation"
        _self_validate(
            design_text=design_text,
            sample_data_text=sample_data_text,
            prep_text=prep_text,
            create_text=create_text,
            registration_text=registration_text,
        )
        rendered_texts = {
            _PREP_PATH: prep_text,
            _CREATE_PATH: create_text,
            _REGISTRATION_PATH: registration_text,
        }
        return MappingProxyType(
            {
                path: _encode_lf_utf8(text)
                for path, text in rendered_texts.items()
            }
        )
    except AsdwDataScriptGenerationError:
        raise
    except Exception as exc:  # pragma: no cover - defensive normalization path
        raise AsdwDataScriptGenerationError(
            _normalize_error_message(
                "ASDW data producer generation failed during "
                f"{stage} with {exc.__class__.__name__}."
            )
        ) from None


def _resolve_audit_mode(design_text: str) -> str:
    audit_mode, errors = _resolve_asdw_audit_storage_mode(
        _DESIGN_PATH,
        design_doc_text=design_text,
    )
    if errors or audit_mode not in {
        _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST,
        _ASDW_AUDIT_MODE_ACL_DIRECT,
    }:
        raise AsdwDataScriptGenerationError(
            _combine_errors(errors, "Invalid AuditRecord storage mode.")
        )
    return audit_mode


def _load_required_sample_counts(sample_data_text: str) -> dict[str, int]:
    counts, error = _load_asdw_sample_counts(
        _SAMPLE_DATA_PATH,
        text=sample_data_text,
    )
    if error is not None:
        raise AsdwDataScriptGenerationError(_safe_sample_error(error))
    missing = [entity for entity in _REQUIRED_ENTITIES if entity not in counts]
    non_positive = [
        entity for entity in _REQUIRED_ENTITIES if counts.get(entity, 0) <= 0
    ]
    if missing or non_positive:
        errors: list[str] = []
        if missing:
            errors.append(
                "Selected APP data coverage sample-data must contain list values for: "
                + ", ".join(missing)
                + "."
            )
        if non_positive:
            errors.append(
                "Selected APP data coverage sample-data must contain positive counts for: "
                + ", ".join(non_positive)
                + "."
            )
        raise AsdwDataScriptGenerationError(_combine_errors(errors))
    return {entity: counts[entity] for entity in _REQUIRED_ENTITIES}


def _validate_required_sample_records(sample_data_text: str) -> None:
    """Reject sample data that the canonical registration payload cannot execute."""
    try:
        data = json.loads(sample_data_text)
        entities = data["entities"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise AsdwDataScriptGenerationError(
            "Selected APP sample-data structure is invalid."
        ) from None
    if not isinstance(entities, dict):
        raise AsdwDataScriptGenerationError(
            "Selected APP sample-data structure is invalid."
        )
    # sample-data.json is a shared, cross-APP fixture (usecaseId=ALL-APPS) that
    # may legitimately carry entities for other APPs too. Only require that the
    # APP-009 coverage set is present; do not reject extra, unrelated entities.
    missing = [
        entity
        for entity in _REQUIRED_ENTITIES
        if not isinstance(entities.get(entity), list)
    ]
    if missing:
        raise AsdwDataScriptGenerationError(
            "Selected APP sample-data must include list records for APP-009 "
            "coverage entities: " + ", ".join(missing) + "."
        )
    for entity in _REQUIRED_ENTITIES:
        id_field = _REQUIRED_ID_FIELDS[entity]
        seen_ids: set[str] = set()
        for index, record in enumerate(entities[entity]):
            if not isinstance(record, dict):
                raise AsdwDataScriptGenerationError(
                    f"Selected APP sample-data {entity}[{index}] must be an object."
                )
            record_id = record.get(id_field)
            if (
                not isinstance(record_id, str)
                or not record_id
                or record_id != record_id.strip()
            ):
                raise AsdwDataScriptGenerationError(
                    f"Selected APP sample-data {entity}[{index}].{id_field} "
                    "must be a non-empty trimmed string."
                )
            if record_id in seen_ids:
                raise AsdwDataScriptGenerationError(
                    f"Selected APP sample-data {entity}.{id_field} values must be unique."
                )
            seen_ids.add(record_id)


def _safe_sample_error(error: str) -> str:
    """Classify loader errors without echoing untrusted sample keys or values."""
    if "JSON error" in error:
        return "Selected APP sample-data JSON is malformed."
    if "root must be an object" in error:
        return "Selected APP sample-data root must be an object."
    if "`entities` must be an object" in error:
        return "Selected APP sample-data `entities` must be an object."
    if "entity values must be lists" in error:
        return "Selected APP sample-data entity values must be lists."
    return "Selected APP sample-data could not be loaded."


def _render_prep_script() -> str:
    return """#!/usr/bin/env bash
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
    # shellcheck disable=SC2034
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
        printf '[ERROR] public route is blocked\\n' >&2
    exit 1
    ;;
  nsp)
        printf '[ERROR] nsp route is blocked\\n' >&2
    exit 1
    ;;
  blocked)
        printf '[ERROR] blocked route\\n' >&2
    exit 1
    ;;
  *)
        printf '[ERROR] invalid route\\n' >&2
    exit 1
    ;;
esac
# HVE-ASDW-DATA-PREP-END
"""


def _render_create_script(audit_mode: str, counts: Mapping[str, int]) -> str:
    non_audit_command = _build_asdw_non_audit_aci_command(counts, audit_mode).replace(
        '"',
        r'\"',
    )
    (
        mode_guards,
        sql_database_steps,
        mode_steps,
        mode_environment,
    ) = _create_mode_sections(audit_mode)
    script = """#!/usr/bin/env bash
# HVE-ASDW-DATA-CREATE-BEGIN
set -euo pipefail
: "${HVE_ASDW_SCRIPT_DIR:?}"
# shellcheck disable=SC2034
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
__MODE_GUARDS__
        : "${COSMOS_ACCOUNT:?}"
        : "${COSMOS_ENDPOINT:?}"
        : "${COSMOS_DATABASE:?}"
        : "${COSMOS_CONTAINER_VOC:?}"
        : "${CONFIDENTIAL_LEDGER_NAME:?}"
        : "${CONFIDENTIAL_LEDGER_ENDPOINT:?}"
        : "${CONFIDENTIAL_LEDGER_LOCATION:?}"
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
    # shellcheck disable=SC2034
    hve_policy_preflight_complete=1
    az sql server create --resource-group "$RESOURCE_GROUP" --name "$SQL_SERVER" --enable-ad-only-auth --external-admin-principal-type Application --external-admin-name data-deploy-identity --external-admin-sid "$DATA_DEPLOY_IDENTITY_CLIENT_ID" --enable-public-network false --output none
    az sql db create --resource-group "$RESOURCE_GROUP" --server "$SQL_SERVER" --name "$SQL_DATABASE" --output none
__SQL_DATABASE_STEPS__
    az cosmosdb create --resource-group "$RESOURCE_GROUP" --name "$COSMOS_ACCOUNT" --disable-local-auth true --public-network-access Disabled --output none
    az cosmosdb sql database create --resource-group "$RESOURCE_GROUP" --account-name "$COSMOS_ACCOUNT" --name "$COSMOS_DATABASE" --output none
    az cosmosdb sql container create --resource-group "$RESOURCE_GROUP" --account-name "$COSMOS_ACCOUNT" --database-name "$COSMOS_DATABASE" --name "$COSMOS_CONTAINER_VOC" --partition-key-path /sourceRecordId --output none
    az confidentialledger create --resource-group "$RESOURCE_GROUP" --name "$CONFIDENTIAL_LEDGER_NAME" --location "$CONFIDENTIAL_LEDGER_LOCATION" --output none
    az network private-dns zone create --resource-group "$RESOURCE_GROUP" --name "$SQL_PRIVATE_DNS_ZONE" --output none
    az network private-dns zone create --resource-group "$RESOURCE_GROUP" --name "$COSMOS_PRIVATE_DNS_ZONE" --output none
    az network private-dns link vnet create --resource-group "$RESOURCE_GROUP" --zone-name "$SQL_PRIVATE_DNS_ZONE" --name sql-data-link --virtual-network "$DATA_VNET_NAME" --registration-enabled false --output none
    az network private-dns link vnet create --resource-group "$RESOURCE_GROUP" --zone-name "$COSMOS_PRIVATE_DNS_ZONE" --name cosmos-data-link --virtual-network "$DATA_VNET_NAME" --registration-enabled false --output none
    az network private-endpoint create --resource-group "$RESOURCE_GROUP" --name "$SQL_PRIVATE_ENDPOINT_NAME" --subnet "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" --private-connection-resource-id "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Sql/servers/$SQL_SERVER" --group-id sqlServer --output none
    az network private-endpoint create --resource-group "$RESOURCE_GROUP" --name "$COSMOS_PRIVATE_ENDPOINT_NAME" --subnet "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" --private-connection-resource-id "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.DocumentDB/databaseAccounts/$COSMOS_ACCOUNT" --group-id Sql --output none
    az network private-endpoint dns-zone-group create --resource-group "$RESOURCE_GROUP" --endpoint-name "$SQL_PRIVATE_ENDPOINT_NAME" --name default --zone-name "$SQL_PRIVATE_DNS_ZONE" --output none
    az network private-endpoint dns-zone-group create --resource-group "$RESOURCE_GROUP" --endpoint-name "$COSMOS_PRIVATE_ENDPOINT_NAME" --name default --zone-name "$COSMOS_PRIVATE_DNS_ZONE" --output none
__MODE_STEPS__
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
        az container create --resource-group "$RESOURCE_GROUP" --name "$data_aci_name" --tags hveCreateRunId="$DATA_CREATE_RUN_ID" --image "$DATA_VERIFY_ACI_IMAGE" --subnet "$DATA_ACI_SUBNET_ID" --acr-identity "$DATA_DEPLOY_IDENTITY_ID" --assign-identity "$DATA_DEPLOY_IDENTITY_ID" --restart-policy Never --os-type Linux --cpu 1 --memory 1 --secure-environment-variables NON_AUDIT_DATA_JSON="$HVE_ASDW_SAMPLE_DATA_JSON" --environment-variables AZURE_CLIENT_ID="$DATA_DEPLOY_IDENTITY_CLIENT_ID" SQL_HOST="$SQL_HOST" SQL_DB_SVC01="$SQL_DB_SVC01" SQL_DB_SVC02="$SQL_DB_SVC02" SQL_DB_SVC03="$SQL_DB_SVC03" SQL_DB_SVC07="$SQL_DB_SVC07" SQL_DB_SVC09="$SQL_DB_SVC09" COSMOS_ENDPOINT="$COSMOS_ENDPOINT" COSMOS_DATABASE="$COSMOS_DATABASE" COSMOS_CONTAINER_VOC="$COSMOS_CONTAINER_VOC" CONFIDENTIAL_LEDGER_ENDPOINT="$CONFIDENTIAL_LEDGER_ENDPOINT" DATA_DEPLOY_IDENTITY_CLIENT_ID="$DATA_DEPLOY_IDENTITY_CLIENT_ID"__MODE_ENVIRONMENT__ --command-line "$non_audit_command"
        data_aci_created=1
        data_aci_wait_failed=0
        data_aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$data_aci_name" --follow)" || data_aci_wait_failed=1
        data_aci_exit_code="$(az container show --resource-group "$RESOURCE_GROUP" --name "$data_aci_name" --query "containers[0].instanceView.currentState.exitCode" --output tsv)"
        if [[ "$data_aci_wait_failed" != "0" || "$data_aci_exit_code" != "0" || "$data_aci_logs" != "HVE_NON_AUDIT_REGISTRATION_OK" ]]; then
            exit 1
        fi
    ;;
  public)
        printf '[ERROR] public route is blocked\\n' >&2
    exit 1
    ;;
  nsp)
        printf '[ERROR] nsp route is blocked\\n' >&2
    exit 1
    ;;
  blocked)
        printf '[ERROR] blocked route\\n' >&2
    exit 1
    ;;
  *)
        printf '[ERROR] invalid route\\n' >&2
    exit 1
    ;;
esac
# HVE-ASDW-DATA-CREATE-END
"""
    replacements = (
        ("__MODE_GUARDS__", mode_guards),
        ("__SQL_DATABASE_STEPS__", sql_database_steps),
        ("__MODE_STEPS__", mode_steps),
        ("__MODE_ENVIRONMENT__", mode_environment),
        ("__NON_AUDIT_COMMAND__", non_audit_command),
    )
    for placeholder, replacement in replacements:
        script = _replace_exactly_once(script, placeholder, replacement)
    _reject_remaining_placeholders(script)
    return script


def _create_mode_sections(audit_mode: str) -> tuple[str, str, str, str]:
    common_database_steps = "\n".join(
        '    az sql db create --resource-group "$RESOURCE_GROUP" '
        '--server "$SQL_SERVER" --name "$' + database_key + '" --output none'
        for database_key in (
            "SQL_DB_SVC01",
            "SQL_DB_SVC02",
            "SQL_DB_SVC03",
            "SQL_DB_SVC07",
            "SQL_DB_SVC09",
        )
    )
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        return (
            '        : "${SQL_DB_SVC12:?}"\n        : "${SQL_AUDIT_TABLE:?}"',
            common_database_steps
            + '\n    az sql db create --resource-group "$RESOURCE_GROUP" '
            '--server "$SQL_SERVER" --name "$SQL_DB_SVC12" --output none',
            '    az sql db ledger-digest-uploads enable --resource-group "$RESOURCE_GROUP" --server "$SQL_SERVER" --name "$SQL_DB_SVC12" --endpoint "$CONFIDENTIAL_LEDGER_ENDPOINT"',
            ' SQL_DB_SVC12="$SQL_DB_SVC12" SQL_AUDIT_TABLE="$SQL_AUDIT_TABLE"',
        )
    if audit_mode == _ASDW_AUDIT_MODE_ACL_DIRECT:
        return (
            '        : "${CONFIDENTIAL_LEDGER_COLLECTION:?}"',
            common_database_steps,
            "",
            ' CONFIDENTIAL_LEDGER_COLLECTION="$CONFIDENTIAL_LEDGER_COLLECTION"',
        )
    raise AsdwDataScriptGenerationError("Unsupported AuditRecord storage mode.")


def _render_registration_script(audit_mode: str) -> str:
    source = _audit_registration_source(audit_mode)
    return _registration_script_from_source(audit_mode, source)


def _audit_registration_source(audit_mode: str) -> str:
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        return _ASDW_SQL_AUDIT_REGISTRATION_SOURCE
    if audit_mode == _ASDW_AUDIT_MODE_ACL_DIRECT:
        return _ASDW_ACL_AUDIT_REGISTRATION_SOURCE
    raise AsdwDataScriptGenerationError("Unsupported AuditRecord storage mode.")


def _registration_script_from_source(audit_mode: str, source: str) -> str:
    escaped_source = source.replace('"', r'\"')
    assignment = f'aci_command="python -c \'{escaped_source}\'"\n'
    common_guards = (
        ': "${RESOURCE_GROUP:?}"\n'
        ': "${DATA_ACI_SUBNET_ID:?}"\n'
        ': "${DATA_DEPLOY_IDENTITY_ID:?}"\n'
        ': "${DATA_DEPLOY_IDENTITY_CLIENT_ID:?}"\n'
        ': "${DATA_VERIFY_ACI_IMAGE:?}"\n'
        ': "${AUDIT_RECORD_JSON:?}"\n'
    )
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        mode_guards = (
            ': "${SQL_HOST:?}"\n'
            ': "${SQL_DB_SVC12:?}"\n'
            ': "${SQL_AUDIT_TABLE:?}"\n'
        )
        mode_environment = (
            ' SQL_HOST="$SQL_HOST" SQL_DB_SVC12="$SQL_DB_SVC12" '
            'SQL_AUDIT_TABLE="$SQL_AUDIT_TABLE"'
        )
    elif audit_mode == _ASDW_AUDIT_MODE_ACL_DIRECT:
        mode_guards = (
            ': "${CONFIDENTIAL_LEDGER_ENDPOINT:?}"\n'
            ': "${CONFIDENTIAL_LEDGER_COLLECTION:?}"\n'
        )
        mode_environment = (
            ' CONFIDENTIAL_LEDGER_ENDPOINT="$CONFIDENTIAL_LEDGER_ENDPOINT" '
            'CONFIDENTIAL_LEDGER_COLLECTION="$CONFIDENTIAL_LEDGER_COLLECTION"'
        )
    else:
        raise AsdwDataScriptGenerationError("Unsupported AuditRecord storage mode.")
    create = (
        'az container create --resource-group "$RESOURCE_GROUP" '
        '--name "$aci_name" --tags hveRegisterRunId="$DATA_REGISTER_RUN_ID"'
    )
    script = _replace_exactly_once(
        _REGISTRATION_LIFECYCLE,
        'aci_name="data-register-$DATA_REGISTER_RUN_ID"\n',
        common_guards + mode_guards + 'aci_name="data-register-$DATA_REGISTER_RUN_ID"\n',
    )
    audit_block = _replace_exactly_once(
        script,
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
    )
    shebang = "#!/usr/bin/env bash\n"
    return (
        shebang
        + "# HVE-AUDIT-REGISTRATION-BEGIN\n"
        + audit_block[len(shebang):]
        + "# HVE-AUDIT-REGISTRATION-END\n"
    )


def _self_validate(
    *,
    design_text: str,
    sample_data_text: str,
    prep_text: str,
    create_text: str,
    registration_text: str,
) -> None:
    errors = validate_asdw_data_create_scripts(
        _PREP_PATH,
        _CREATE_PATH,
        design_doc_path=_DESIGN_PATH,
        sample_data_path=_SAMPLE_DATA_PATH,
        prep_text=prep_text,
        create_text=create_text,
        design_doc_text=design_text,
        sample_data_text=sample_data_text,
    )
    errors.extend(
        validate_asdw_data_registration_script(
            _REGISTRATION_PATH,
            design_doc_path=_DESIGN_PATH,
            script_text=registration_text,
            design_doc_text=design_text,
        )
    )
    if errors:
        raise AsdwDataScriptGenerationError(
            _combine_errors(errors, "Generated artifacts failed validation.")
        )


def _encode_lf_utf8(text: str) -> bytes:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.encode("utf-8")


def _replace_exactly_once(text: str, anchor: str, replacement: str) -> str:
    if text.count(anchor) != 1:
        raise AsdwDataScriptGenerationError(
            "ASDW producer template anchor must occur exactly once."
        )
    return text.replace(anchor, replacement, 1)


def _reject_remaining_placeholders(text: str) -> None:
    if any(
        placeholder in text
        for placeholder in (
            "__MODE_GUARDS__",
            "__SQL_DATABASE_STEPS__",
            "__MODE_STEPS__",
            "__MODE_ENVIRONMENT__",
            "__NON_AUDIT_COMMAND__",
        )
    ):
        raise AsdwDataScriptGenerationError(
            "ASDW producer template contains an unresolved placeholder."
        )


def _combine_errors(errors: list[str], fallback: str | None = None) -> str:
    normalized = []
    for error in errors:
        normalized_error = _normalize_error_message(error)
        if normalized_error:
            normalized.append(normalized_error)
    if normalized:
        return _normalize_error_message("; ".join(normalized))
    if fallback is not None:
        return _normalize_error_message(fallback)
    return "ASDW data producer generation failed."


def _normalize_error_message(message: str) -> str:
    single_line = " ".join(str(message).split())
    if not single_line:
        return ""
    if len(single_line) > 280:
        return single_line[:277].rstrip() + "..."
    return single_line


_REGISTRATION_LIFECYCLE = """#!/usr/bin/env bash
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
"""
