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

import snapshots


SOURCE = Path(__file__).resolve().parents[2]


def run(args, cwd: Path, check: bool = True):
    env = dict(os.environ, PYTHONUTF8="1", EABK_ALLOW_PRIMARY="1")
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


def _build_installed(repo: Path) -> None:
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


@pytest.fixture
def installed_repo(tmp_path: Path) -> Path:
    # install は 1 プロセスに 1 回だけ行い、各テストにはそのコピーを渡す（分離は同じ）
    return snapshots.clone("installed", _build_installed, tmp_path / "EABK system test repository with spaces")

