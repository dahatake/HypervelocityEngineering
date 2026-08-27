"""FR-GUI-42: direct PR creation の git preflight。"""

from __future__ import annotations

import subprocess
import builtins
from pathlib import Path

import pytest

from hve.gui import git_ops
from hve.gui.git_ops import GitOpsError


def _completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(["git"], returncode, stdout, stderr)


def _runner(*, branch="feature/x", status="", base_exists=True, ahead=2, published=True, unpushed=0, files="a.py\nb.py\n", origin="https://github.com/o/r.git"):
    def run(args, timeout=git_ops._TIMEOUT, cwd=None):
        command = tuple(args)
        if command == ("git", "remote", "get-url", "origin"):
            return _completed(stdout=f"{origin}\n")
        if command == ("git", "rev-parse", "--abbrev-ref", "HEAD"):
            return _completed(stdout=f"{branch}\n")
        if command == ("git", "status", "--porcelain"):
            return _completed(stdout=status)
        if command == ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"):
            return _completed(returncode=0 if base_exists else 1)
        if command == ("git", "rev-list", "--count", "origin/main..HEAD"):
            return _completed(stdout=f"{ahead}\n")
        if command == ("git", "diff", "--name-only", "origin/main...HEAD"):
            return _completed(stdout=files)
        if command == ("git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}"):
            return _completed(returncode=0 if published else 1)
        if command == ("git", "rev-list", "--count", f"origin/{branch}..HEAD"):
            return _completed(stdout=f"{unpushed}\n")
        raise AssertionError(command)
    return run


def test_ready_preflight_reports_current_branch_and_counts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(git_ops, "_run", _runner())
    result = git_ops.inspect_pull_request(tmp_path, "main")
    assert result.head_branch == "feature/x"
    assert result.base_branch == "main"
    assert result.ahead_commits == 2
    assert result.changed_files == 2
    assert result.published is True
    assert result.unpushed_commits == 0
    assert result.origin_repo == "o/r"
    assert result.ready is True


@pytest.mark.parametrize(
    ("runner", "message"),
    [
        (_runner(branch="HEAD"), "detached"),
        (_runner(status=" M dirty.py\n"), "未コミット"),
        (_runner(branch="main"), "同じ"),
        (_runner(base_exists=False), "base"),
        (_runner(ahead=0), "commit"),
        (_runner(origin="https://example.com/o/r.git"), "origin"),
    ],
)
def test_preflight_blocks_unsafe_state(monkeypatch, tmp_path: Path, runner, message) -> None:
    monkeypatch.setattr(git_ops, "_run", runner)
    with pytest.raises(GitOpsError, match=message):
        git_ops.inspect_pull_request(tmp_path, "main")


def test_unpublished_branch_is_not_ready(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(git_ops, "_run", _runner(published=False))
    result = git_ops.inspect_pull_request(tmp_path, "main")
    assert result.published is False
    assert result.ready is False


def test_unpushed_commits_are_not_ready(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(git_ops, "_run", _runner(unpushed=3))
    result = git_ops.inspect_pull_request(tmp_path, "main")
    assert result.unpushed_commits == 3
    assert result.ready is False


def test_template_loader_reads_only_default_repository_template(tmp_path: Path) -> None:
    target = tmp_path / ".github" / "pull_request_template.md"
    target.parent.mkdir()
    target.write_text("## Summary\n", encoding="utf-8")
    assert git_ops.load_pull_request_template(tmp_path) == "## Summary\n"
    assert git_ops.load_pull_request_template(tmp_path / "missing") == ""


def test_origin_repository_does_not_import_pyside_or_page_options(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(git_ops, "_run", _runner())
    real_import = builtins.__import__

    def _guarded_import(name, *args, **kwargs):
        if name.startswith("PySide6") or name == "hve.gui.page_options":
            raise AssertionError(f"unexpected GUI import: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)
    assert git_ops.origin_repository(tmp_path) == "o/r"
