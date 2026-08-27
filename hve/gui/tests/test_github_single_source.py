"""FR-GUI-28: GUI GitHub 連携は ``hve.github_api`` へ委譲する。

GUI 専用の HTTP クライアント、別の GitHub SDK、`gh` サブプロセスによる API 代替を禁じる。
認証専用の ``gh_cli`` / ``gh_login_dialog`` は GitHub CLI の責務であり検査対象外。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


_GUI_GITHUB_MODULES = (
    "github_service.py",
    "github_threads.py",
    "github_issue_panel.py",
    "github_pr_panel.py",
    "github_picker_dialog.py",
    "github_window.py",
    "startup_auth.py",
)
_FORBIDDEN_IMPORT_ROOTS = {
    "aiohttp",
    "github",  # PyGithub
    "github3",
    "http",
    "httpx",
    "requests",
    "subprocess",
    "urllib",
}
_GUI_DIR = Path(__file__).resolve().parents[1]


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


class TestNoAlternateClients:
    def test_gui_github_modules_do_not_import_alternate_clients(self) -> None:
        violations = {
            name: sorted(_import_roots(_GUI_DIR / name) & _FORBIDDEN_IMPORT_ROOTS)
            for name in _GUI_GITHUB_MODULES
        }
        assert not {name: imports for name, imports in violations.items() if imports}

    @pytest.mark.parametrize("name", _GUI_GITHUB_MODULES)
    def test_module_exists(self, name: str) -> None:
        assert (_GUI_DIR / name).is_file(), name

    @pytest.mark.parametrize("name", _GUI_GITHUB_MODULES)
    def test_no_gh_subcommand_invocation(self, name: str) -> None:
        """認証以外で `gh` サブコマンドを組み立てていないこと。"""
        source = (_GUI_DIR / name).read_text(encoding="utf-8")
        for forbidden in ("gh issue", "gh pr", "gh api"):
            assert forbidden not in source, f"{name} contains '{forbidden}'"

    def test_service_layer_delegates_to_github_api(self) -> None:
        source = (_GUI_DIR / "github_service.py").read_text(encoding="utf-8")
        assert "from hve import github_api" in source

    @pytest.mark.parametrize(
        "name",
        (
            "github_issue_panel.py",
            "github_pr_panel.py",
            "github_picker_dialog.py",
            "github_window.py",
        ),
    )
    def test_panels_go_through_the_service_layer(self, name: str) -> None:
        """パネルはサービス層を通し、API モジュールへ直接依存しないこと。"""
        source = (_GUI_DIR / name).read_text(encoding="utf-8")
        assert "github_api" not in source, name


class TestNoNewGitHubSdkDependency:
    def test_pyproject_declares_no_github_sdk(self) -> None:
        pyproject = (_GUI_DIR.parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        for package in ("pygithub", "github3.py", "ghapi"):
            assert package not in pyproject.lower(), package


class TestGitOpsIsNotAGitHubClient:
    """FR-GUI-34 の push は git 操作であり、GitHub API の代替経路ではないこと。

    ``git_ops.py`` は `subprocess` を使うため上の検査対象から外れているが、
    その除外が意図したものであることを固定する。
    """

    def test_git_ops_does_not_touch_github_api(self) -> None:
        source = (_GUI_DIR / "git_ops.py").read_text(encoding="utf-8")
        for forbidden in ("api.github.com", "gh issue", "gh pr", "gh api", "github_api"):
            assert forbidden not in source, forbidden

    def test_git_ops_only_invokes_git(self) -> None:
        tree = ast.parse(
            (_GUI_DIR / "git_ops.py").read_text(encoding="utf-8"), filename="git_ops.py"
        )
        commands = [
            node.args[0].elts[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_run"
            and node.args
            and isinstance(node.args[0], ast.List)
            and node.args[0].elts
            and isinstance(node.args[0].elts[0], ast.Constant)
        ]
        assert commands and all(cmd == "git" for cmd in commands), commands

