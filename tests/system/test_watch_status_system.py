"""System acceptance tests for the WATCH: warning of `run-state.py status`.

The oracle is FR-1065 AC-363 and PARAM-045 (60 minutes), not the
implementation of run-state.py / watch.py.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from conftest import run

PARAM_045_MINUTES = 60


def py(repo: Path, script: str, *args: str, check: bool = True):
    return run([sys.executable, repo / "scripts" / script, *args], repo, check=check)


def start_run(repo: Path) -> str:
    result = py(repo, "run-state.py", "start", "--options", "max_hours: 24")
    match = re.search(r"\b(?:START|RESUME)\s+(\d+)", result.stdout)
    assert match, result.stdout
    return match.group(1)


def queue_path(repo: Path, run_id: str) -> Path:
    return repo / "work" / "runs" / run_id / "queue.json"


def add_doing(repo: Path, run_id: str, item: str, age_minutes: int) -> None:
    py(repo, "run-state.py", "queue", "add", "--id", item, "--req", "FR-1065", "--ac", "AC-363")
    py(repo, "run-state.py", "queue", "set", item, "--status", "doing", "--attempts", "+1")
    path = queue_path(repo, run_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc).astimezone() - timedelta(minutes=age_minutes)
    for it in data["items"]:
        if it["id"] == item:
            it["started_at"] = started.isoformat(timespec="seconds")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def watch_lines(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines() if line.startswith("WATCH:")]


# FR-1065 AC-363
def test_status_warns_item_over_limit_ac363(installed_repo: Path) -> None:
    run_id = start_run(installed_repo)
    add_doing(installed_repo, run_id, "I-01", PARAM_045_MINUTES + 5)
    result = py(installed_repo, "run-state.py", "status")
    lines = watch_lines(result.stdout)
    assert lines, result.stdout
    assert "I-01" in " ".join(lines)


# FR-1065 AC-363 (abnormal boundary: within the limit, and no suspicious process)
def test_status_no_warning_within_limit_ac363(installed_repo: Path) -> None:
    run_id = start_run(installed_repo)
    add_doing(installed_repo, run_id, "I-01", PARAM_045_MINUTES - 10)
    result = py(installed_repo, "run-state.py", "status")
    assert not watch_lines(result.stdout), result.stdout


# FR-1065 AC-363 (no doing item at all)
def test_status_no_warning_without_doing_ac363(installed_repo: Path) -> None:
    start_run(installed_repo)
    result = py(installed_repo, "run-state.py", "status")
    assert not watch_lines(result.stdout), result.stdout


# FR-1065 AC-363 (only the over-limit item is named)
def test_status_names_only_over_limit_items_ac363(installed_repo: Path) -> None:
    run_id = start_run(installed_repo)
    add_doing(installed_repo, run_id, "I-01", PARAM_045_MINUTES + 30)
    add_doing(installed_repo, run_id, "I-02", 5)
    result = py(installed_repo, "run-state.py", "status")
    text = " ".join(watch_lines(result.stdout))
    assert "I-01" in text and "I-02" not in text, result.stdout


# FR-1065 AC-363 (the WATCH line changes neither exit code nor queue)
def test_status_watch_does_not_change_exit_or_queue_ac363(installed_repo: Path) -> None:
    run_id = start_run(installed_repo)
    clean = py(installed_repo, "run-state.py", "status", check=False)
    add_doing(installed_repo, run_id, "I-01", PARAM_045_MINUTES + 5)
    before = queue_path(installed_repo, run_id).read_text(encoding="utf-8")
    warned = py(installed_repo, "run-state.py", "status", check=False)
    assert watch_lines(warned.stdout)
    assert warned.returncode == clean.returncode == 0
    assert queue_path(installed_repo, run_id).read_text(encoding="utf-8") == before
