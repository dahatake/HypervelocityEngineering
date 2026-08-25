#!/usr/bin/env python3
"""Validate a pull request's changed paths against one HVE Workflow policy."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Sequence

_TRUSTED_ROOT = Path(__file__).resolve().parents[2]
# 既に後方へ登録済みでも必ず先頭へ置く。存在確認だけでは、subject を先に含む
# PYTHONPATH によって subject/hve が import され、事後の origin 検査より前に
# 任意コードが実行され得る。
sys.path.insert(0, str(_TRUSTED_ROOT))

from hve import workflow_diff_gate as _workflow_diff_gate  # noqa: E402
from hve.workflow_diff_gate import (  # noqa: E402
    ChangedPath,
    WorkflowDiffResult,
    resolve_managed_workflow_id,
    validate_workflow_diff,
)

_MAX_CHANGED_FILES = 3000


class InputError(ValueError):
    """Raised when deterministic validator input is invalid."""


def _assert_trusted_import() -> None:
    module_path = Path(_workflow_diff_gate.__file__).resolve()
    try:
        module_path.relative_to(_TRUSTED_ROOT)
    except ValueError as exc:
        raise InputError("workflow diff implementation was not loaded from trusted root") from exc


def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            return json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"cannot read JSON input: {path.name}") from exc


def _subject_root(path: Path) -> Path:
    if _is_link_like(path):
        raise InputError("subject root must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise InputError("subject root does not exist") from exc
    if not resolved.is_dir():
        raise InputError("subject root is not a directory")
    return resolved


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    try:
        reparse_tag = getattr(path.lstat(), "st_reparse_tag", 0)
    except OSError:
        return False
    return reparse_tag == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", -1)


def _assert_subject_docs_are_confined(root: Path) -> None:
    """Reject symlinks under subject docs before any catalog parser can read them."""

    docs = root / "docs"
    if _is_link_like(docs):
        raise InputError("subject docs must not be a symlink")
    if not docs.exists():
        return
    try:
        pending = [docs]
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as stream:
                entries = sorted(stream, key=lambda entry: entry.name)
            for entry in entries:
                candidate = Path(entry.path)
                relative = candidate.relative_to(root).as_posix()
                if _is_link_like(candidate):
                    raise InputError(
                        f"subject catalog path must not be a symlink: {relative}"
                    )
                candidate.resolve(strict=True).relative_to(root)
                if entry.is_dir(follow_symlinks=False):
                    pending.append(candidate)
    except (OSError, ValueError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("subject catalog path escapes repository root") from exc


def _parse_changed_files(value: Any) -> tuple[ChangedPath, ...]:
    if not isinstance(value, list):
        raise InputError("changed-files JSON root must be a list")
    if len(value) > _MAX_CHANGED_FILES:
        raise InputError("changed-files JSON exceeds the GitHub API 3,000-file limit")
    changed: list[ChangedPath] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise InputError(f"changed-files entry {index} is not an object")
        filename = entry.get("filename")
        status = entry.get("status")
        if not isinstance(filename, str) or not filename:
            raise InputError(f"changed-files entry {index} has no filename")
        if not isinstance(status, str) or not status:
            raise InputError(f"changed-files entry {index} has no status")
        previous = entry.get("previous_filename")
        if status in {"renamed", "copied"}:
            if not isinstance(previous, str) or not previous:
                raise InputError(f"changed-files entry {index} has no source filename")
        else:
            previous = None
        changed.append(
            ChangedPath(path=filename, status=status, previous_path=previous)
        )
    return tuple(changed)


def _metadata_identity(value: Any, actual_count: int) -> tuple[WorkflowDiffResult | None, str | None, tuple[str, ...]]:
    if not isinstance(value, dict):
        raise InputError("PR metadata JSON root must be an object")
    expected = value.get("changed_files")
    if expected is not None:
        if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
            raise InputError("PR metadata changed_files is invalid")
        if expected > _MAX_CHANGED_FILES:
            raise InputError("PR metadata exceeds the GitHub API 3,000-file limit")
        if expected != actual_count:
            raise InputError(
                f"PR metadata changed_files count mismatch: expected {expected}, got {actual_count}"
            )

    issue_titles = value.get("issue_titles", [])
    issue_labels = value.get("issue_labels", [])
    result = resolve_managed_workflow_id(
        pr_body=value.get("body"),
        pr_title=value.get("title"),
        issue_titles=issue_titles,
        issue_labels=issue_labels,
    )
    app_ids_value = value.get("app_ids", [])
    if isinstance(app_ids_value, (str, bytes)) or not isinstance(app_ids_value, Sequence):
        raise InputError("PR metadata app_ids must be a sequence of strings")
    if any(not isinstance(item, str) or not item for item in app_ids_value):
        raise InputError("PR metadata app_ids contains an invalid value")
    app_ids = tuple(app_ids_value)
    if result.status != "PASS":
        return (
            WorkflowDiffResult(
                status=result.status,
                workflow_id=result.workflow_id,
                errors=result.errors,
                reason=result.reason,
            ),
            None,
            app_ids,
        )
    return None, result.workflow_id, app_ids


def _result_dict(result: WorkflowDiffResult) -> dict[str, object]:
    return {
        "status": result.status,
        "workflow_id": result.workflow_id,
        "checked_paths": list(result.checked_paths),
        "violations": list(result.violations),
        "errors": list(result.errors),
        "reason": result.reason,
        "allowed_by": {
            path: list(sources) for path, sources in sorted(result.allowed_by.items())
        },
    }


def _format_text(result: WorkflowDiffResult) -> str:
    lines = [
        f"G-DIFF: {result.status}",
        f"Workflow: {result.workflow_id or '-'}",
        f"Checked-Paths: {len(result.checked_paths)}",
        f"Reason: {result.reason or '-'}",
    ]
    if result.violations:
        lines.append("Violations:")
        lines.extend(f"- {path}" for path in result.violations[:100])
        if len(result.violations) > 100:
            lines.append(f"- ... and {len(result.violations) - 100} more")
    if result.errors:
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in result.errors[:20])
        if len(result.errors) > 20:
            lines.append(f"- ... and {len(result.errors) - 20} more")
    return "\n".join(lines) + "\n"


def _blocked(message: str) -> WorkflowDiffResult:
    return WorkflowDiffResult(
        status="BLOCKED",
        errors=(message,),
        reason="validator input or policy resolution failed",
    )


def validate(args: argparse.Namespace) -> WorkflowDiffResult:
    _assert_trusted_import()
    root = _subject_root(args.root)
    _assert_subject_docs_are_confined(root)
    raw_changed = _read_json(args.changed_files_file)
    changed = _parse_changed_files(raw_changed)

    app_ids: tuple[str, ...] = tuple(args.app_id or ())
    workflow_id = args.workflow_id
    if args.pr_metadata_file is not None:
        identity_result, workflow_id, metadata_app_ids = _metadata_identity(
            _read_json(args.pr_metadata_file), len(changed)
        )
        if identity_result is not None:
            return identity_result
        app_ids = metadata_app_ids
    if workflow_id is None:
        raise InputError("workflow identity could not be resolved")
    return validate_workflow_diff(workflow_id, root, changed, app_ids=app_ids or None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--workflow-id")
    identity.add_argument("--pr-metadata-file", type=Path)
    parser.add_argument("--changed-files-file", required=True, type=Path)
    parser.add_argument("--app-id", action="append", default=[])
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        result = validate(args)
    except (InputError, OSError, ValueError) as exc:
        result = _blocked(f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # pragma: no cover - defensive trusted-code boundary
        result = _blocked(f"{type(exc).__name__}: validation failed")

    try:
        if args.format == "json":
            print(json.dumps(_result_dict(result), ensure_ascii=False, sort_keys=True))
        else:
            sys.stdout.write(_format_text(result))
    except Exception:  # pragma: no cover - last-resort output boundary
        result = _blocked("validator result serialization failed")
        if args.format == "json":
            print(json.dumps(_result_dict(result), ensure_ascii=True, sort_keys=True))
        else:
            sys.stdout.write(_format_text(result))
    return 0 if result.status in {"PASS", "N/A"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
