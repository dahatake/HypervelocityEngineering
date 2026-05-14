"""StepDef.output_paths に基づく既存成果物スナップショット生成。"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from .workflow_registry import StepDef


def _run_git(repo_root: Path, args: List[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _latest_commit_for_path(repo_root: Path, path: str, revision: Optional[str] = None) -> str:
    cmd = ["log", "-1", "--format=%H"]
    if revision:
        cmd.append(revision)
    cmd.extend(["--", path])
    return _run_git(repo_root, cmd)


def _resolve_previous_revision(repo_root: Path) -> Optional[str]:
    previous = _run_git(repo_root, ["rev-parse", "--verify", "HEAD~1"])
    return previous or None


def _format_table(rows: List[Dict[str, str]]) -> str:
    def _esc(value: str) -> str:
        return value.replace("|", "\\|")

    lines = [
        "## 既存成果物の現状",
        "",
        "| path | status | commit | note |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {_esc(row['path'])} | {_esc(row['status'])} | {_esc(row['commit'])} | {_esc(row['note'])} |"
        )
    return "\n".join(lines)


def _append_unique(target: List[str], value: str) -> None:
    if value not in target:
        target.append(value)


def _build_path_row(repo_root: Path, path: str, previous_revision: Optional[str]) -> Dict[str, str]:
    normalized_path = path.replace("\\", "/")
    abs_path = repo_root / normalized_path
    exists = abs_path.exists()
    if not exists:
        return {
            "path": normalized_path,
            "status": "missing",
            "commit": "-",
            "note": "missing",
        }

    commit_full = _latest_commit_for_path(repo_root, normalized_path)
    commit_short = commit_full[:7] if commit_full else "-"
    note = "existing"
    if normalized_path.startswith("knowledge/"):
        if not commit_full or not previous_revision:
            note = "comparison unavailable（比較対象なし）"
        else:
            previous_commit = _latest_commit_for_path(repo_root, normalized_path, revision=previous_revision)
            if not previous_commit:
                note = "comparison unavailable（比較対象なし）"
            elif previous_commit == commit_full:
                note = "unchanged（更新なし）"
            else:
                note = "updated（更新あり）"

    return {
        "path": normalized_path,
        "status": "existing",
        "commit": commit_short,
        "note": note,
    }


def build_existing_output_snapshot_section(step: "StepDef", repo_root: Path) -> str:
    output_paths: List[str] = list(getattr(step, "output_paths", []) or [])
    output_paths_template: List[str] = list(getattr(step, "output_paths_template", []) or [])
    rows: List[Dict[str, str]] = []

    previous_revision = _resolve_previous_revision(repo_root)
    for path in output_paths:
        rows.append(_build_path_row(repo_root, path, previous_revision))

    for template_path in output_paths_template:
        rows.append(
            {
                "path": template_path,
                "status": "dynamic",
                "commit": "-",
                "note": "dynamic output template",
            }
        )

    if not rows:
        rows.append(
            {
                "path": "-",
                "status": "n/a",
                "commit": "-",
                "note": "no output_paths defined",
            }
        )

    return _format_table(rows)


def summarize_knowledge_output_updates(
    steps: Iterable["StepDef"],
    repo_root: Path,
    active_steps: Optional[Set[str]] = None,
) -> Dict[str, List[str]]:
    previous_revision = _resolve_previous_revision(repo_root)
    tracked: List[str] = []
    updated: List[str] = []
    unchanged: List[str] = []
    comparison_unavailable: List[str] = []

    for step in steps:
        step_id = getattr(step, "id", None)
        if active_steps and step_id not in active_steps:
            continue
        for raw_path in (getattr(step, "output_paths", None) or []):
            path = str(raw_path).replace("\\", "/")
            if not path.startswith("knowledge/"):
                continue
            _append_unique(tracked, path)
            if not (repo_root / path).exists():
                _append_unique(comparison_unavailable, path)
                continue
            current_commit = _latest_commit_for_path(repo_root, path)
            if not current_commit:
                _append_unique(comparison_unavailable, path)
                continue
            if not previous_revision:
                _append_unique(comparison_unavailable, path)
                continue
            previous_commit = _latest_commit_for_path(repo_root, path, revision=previous_revision)
            if not previous_commit:
                _append_unique(comparison_unavailable, path)
            elif previous_commit == current_commit:
                _append_unique(unchanged, path)
            else:
                _append_unique(updated, path)

    return {
        "tracked": tracked,
        "updated": updated,
        "unchanged": unchanged,
        "comparison_unavailable": comparison_unavailable,
    }
