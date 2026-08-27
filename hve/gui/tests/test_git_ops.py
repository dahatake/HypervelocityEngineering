"""hve.gui.git_ops のユニットテスト（FR-GUI-34）。"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from hve.gui.git_ops import GitOpsError, current_branch, push_current_branch


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr=stderr)


class TestCurrentBranch:
    @patch("hve.gui.git_ops.subprocess.run")
    def test_returns_branch_name(self, mock_run) -> None:
        mock_run.return_value = _completed(stdout="feature-x\n")
        assert current_branch() == "feature-x"
        assert mock_run.call_args[0][0] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]

    @patch("hve.gui.git_ops.subprocess.run")
    def test_detached_head_returns_none(self, mock_run) -> None:
        mock_run.return_value = _completed(stdout="HEAD\n")
        assert current_branch() is None

    @patch("hve.gui.git_ops.subprocess.run")
    def test_failure_returns_none(self, mock_run) -> None:
        mock_run.return_value = _completed(returncode=128, stderr="fatal")
        assert current_branch() is None


class TestPushCurrentBranch:
    @patch("hve.gui.git_ops.subprocess.run")
    def test_pushes_current_branch_once(self, mock_run) -> None:
        mock_run.side_effect = [_completed(stdout="feature-x\n"), _completed()]
        assert push_current_branch() == "feature-x"
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[1][0][0] == ["git", "push", "-u", "origin", "feature-x"]

    @patch("hve.gui.git_ops.subprocess.run")
    def test_does_not_run_add_or_commit(self, mock_run) -> None:
        mock_run.side_effect = [_completed(stdout="b\n"), _completed()]
        push_current_branch()
        invoked = [call[0][0] for call in mock_run.call_args_list]
        assert all("add" not in args and "commit" not in args for args in invoked)

    @patch("hve.gui.git_ops.subprocess.run")
    def test_detached_head_raises(self, mock_run) -> None:
        mock_run.return_value = _completed(stdout="HEAD\n")
        with pytest.raises(GitOpsError, match="detached HEAD"):
            push_current_branch()

    @patch("hve.gui.git_ops.subprocess.run")
    def test_push_failure_includes_stderr(self, mock_run) -> None:
        mock_run.side_effect = [
            _completed(stdout="feature-x\n"),
            _completed(returncode=1, stderr="rejected: non-fast-forward"),
        ]
        with pytest.raises(GitOpsError, match="non-fast-forward"):
            push_current_branch()

    @patch("hve.gui.git_ops.subprocess.run", side_effect=FileNotFoundError())
    def test_missing_git_raises(self, _mock_run) -> None:
        with pytest.raises(GitOpsError, match="git コマンドが見つかりません"):
            push_current_branch()

    @patch(
        "hve.gui.git_ops.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="git", timeout=1),
    )
    def test_timeout_raises(self, _mock_run) -> None:
        with pytest.raises(GitOpsError, match="タイムアウト"):
            push_current_branch()


class TestNoOrchestratorDependency:
    def test_module_does_not_import_orchestrator_or_pyside(self) -> None:
        import ast
        from pathlib import Path

        import hve.gui.git_ops as mod

        path = Path(mod.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any(name.startswith("PySide6") for name in imported)
        assert not any("orchestrator" in name for name in imported)
