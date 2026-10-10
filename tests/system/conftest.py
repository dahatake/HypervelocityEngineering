"""Fixtures for destructive system tests.

Every test installs EABK into a disposable Git repository.  Nothing below may
point clean-work.py at the source checkout.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[2]


def run(args, cwd: Path, check: bool = True):
    env = dict(os.environ, PYTHONUTF8="1")
    result = subprocess.run(
        [str(a) for a in args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if check and result.returncode:
        raise AssertionError(
            f"{' '.join(map(str, args))} exited {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


@pytest.fixture
def installed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "EABK system test repository with spaces"
    repo.mkdir()
    run(["git", "init", "-q", "-b", "main"], repo)
    run(["git", "config", "user.email", "system-test@example.invalid"], repo)
    run(["git", "config", "user.name", "EABK System Test"], repo)
    run(["git", "config", "commit.gpgsign", "false"], repo)
    (repo / "README.md").write_text("disposable repository\n", encoding="utf-8")
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-q", "-m", "initial"], repo)
    run(
        [sys.executable, SOURCE / "tools" / "install.py", "--target", repo, "--skip-verify"],
        repo,
    )
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-q", "-m", "install EABK"], repo)
    return repo

