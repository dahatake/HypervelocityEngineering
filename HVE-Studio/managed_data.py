"""FR-1090: disposable display data, separate from the repository's authoritative documents."""
from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import eabk_model

DIRECTORY = ".hve-studio"
FILENAME = "managed-data.json"
RELATIVE_PATH = DIRECTORY + "/" + FILENAME
OWNER = "HVE Studio display data"
SCHEMA = 1


class DataError(ValueError):
    pass


def _bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _path(root: Path) -> Path:
    path = root / RELATIVE_PATH
    for candidate in (path.parent, path):
        attributes = candidate.lstat().st_file_attributes if os.name == "nt" and os.path.lexists(candidate) else 0
        if candidate.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise DataError(f"refusing linked generated-data path: {candidate}")
    if path.parent.exists() and not path.parent.is_dir():
        raise DataError(f"generated-data directory is not a directory: {path.parent}")
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise DataError(f"generated data is not a single regular file: {path}")
    return path


def stamp(root: Path) -> str:
    """Include generated-file changes in the viewer cache, not the source fingerprint."""
    try:
        path = _path(root)
        st = path.stat()
        return f"{st.st_mtime_ns}:{st.st_size}"
    except FileNotFoundError:
        return "missing"
    except (OSError, DataError) as exc:
        return "error:" + str(exc)


def _read(root: Path) -> dict | None:
    path = _path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_bytes())
        if not isinstance(data, dict):
            raise DataError("generated data must be an object")
        digest = data.pop("sha256", None)
        if (data.get("owner") != OWNER or data.get("schema") != SCHEMA
                or not isinstance(data.get("model"), dict)
                or digest != hashlib.sha256(_bytes(data)).hexdigest()):
            raise DataError("generated data was modified, is unowned, or uses an unsupported format")
        return data
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DataError(f"cannot read generated data: {exc}") from exc


def inspect(root: Path, source_fingerprint: str | None = None) -> tuple[dict, dict | None]:
    root = root.resolve()
    result = {"exists": os.path.lexists(root / RELATIVE_PATH), "path": str(root / RELATIVE_PATH),
              "state": "missing", "generatedAt": None, "error": None}
    try:
        data = _read(root)
        if data is None:
            return result, None
        fingerprint = source_fingerprint if source_fingerprint is not None else eabk_model.fingerprint(root)
        current = (data.get("repo") == str(root) and data.get("sourceFingerprint") == fingerprint
                   and data.get("studio") == eabk_model.STUDIO_VERSION)
        result.update(state="current" if current else "stale", generatedAt=data.get("generatedAt"))
        return result, data["model"] if current else None
    except (OSError, DataError) as exc:
        result.update(state="conflict", error=str(exc))
        return result, None


def _progress(callback, phase: str, completed: int, total: int, detail: str = "") -> None:
    if callback:
        callback({"phase": phase, "completed": completed, "total": total, "detail": detail})


def _remove_empty_directory(path: Path) -> None:
    try:
        path.rmdir()
    except OSError as exc:
        if exc.errno not in (errno.ENOTEMPTY, errno.EEXIST):
            raise


@contextmanager
def _exclusive(root: Path):
    path = _path(root)
    path.parent.mkdir(exist_ok=True)
    _path(root)
    lock = path.parent / ".operation-lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise DataError(f"another data operation is active; if interrupted, inspect and remove {lock}") from exc
    try:
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
        yield path
    finally:
        lock.unlink()
        _remove_empty_directory(path.parent)


def sync(root: Path, progress=None) -> dict:
    root = root.resolve()
    _progress(progress, "prepare", 0, 1)
    with _exclusive(root) as path:
        original = path.read_bytes() if path.exists() else None
        _read(root)  # Only an intact file produced by Studio may be replaced.
        before = eabk_model.fingerprint(root)
        _progress(progress, "prepare", 1, 1)
        model = eabk_model.build_model(root, progress=progress)
        if model["meta"].get("error"):
            raise DataError("no management data or local Git repository to analyze")
        after = eabk_model.fingerprint(root)
        if before != after:
            raise DataError("repository changed during synchronization; retry")
        data = {"owner": OWNER, "schema": SCHEMA, "repo": str(root),
                "studio": eabk_model.STUDIO_VERSION, "sourceFingerprint": after,
                "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model}
        data["sha256"] = hashlib.sha256(_bytes(data)).hexdigest()
        _progress(progress, "write", 0, 1, str(path))
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".sync-", delete=False) as handle:
                temp = Path(handle.name)
                handle.write(_bytes(data) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            _path(root)
            current = path.read_bytes() if path.exists() else None
            if current != original or eabk_model.fingerprint(root) != after:
                raise DataError("repository or generated data changed before saving; retry")
            os.replace(temp, path)
            temp = None
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
        _progress(progress, "write", 1, 1, str(path))
    _progress(progress, "done", 1, 1, str(path))
    return inspect(root)[0]


def delete(root: Path, progress=None) -> dict:
    root = root.resolve()
    _progress(progress, "delete", 0, 1)
    with _exclusive(root) as path:
        if path.exists():
            _read(root)  # Never remove an existing foreign or modified file.
            path.unlink()
    _progress(progress, "done", 1, 1, str(path))
    return inspect(root)[0]


def console_progress():
    last = None

    def report(event):
        nonlocal last
        completed, total = event["completed"], event["total"]
        filled = int(20 * completed / max(1, total))
        key = (event["phase"], filled)
        if key == last:
            return
        last = key
        print(f"[{'#' * filled}{'-' * (20 - filled)}] {event['phase']} "
              f"{completed}/{total} {event.get('detail', '')}", flush=True)

    return report
