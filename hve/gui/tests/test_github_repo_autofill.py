"""hve.gui.tests.test_github_repo_autofill

GitHub 設定のリポジトリ取得・補完 UI の単体テスト。

ネットワークにはアクセスせず、git remote / GitHub API は mock で検証する。
"""

from __future__ import annotations

import os
import subprocess

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/owner/repo.git", "owner/repo"),
        ("https://github.com/owner/repo", "owner/repo"),
        ("git@github.com:owner/repo.git", "owner/repo"),
        ("ssh://git@github.com/owner/repo.git", "owner/repo"),
    ],
)
def test_parse_github_remote_url_supported_formats(url: str, expected: str) -> None:
    from hve.gui.page_options import _parse_github_remote_url

    assert _parse_github_remote_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/owner/repo.git",
        "https://github.com/owner",
        "git@github.com:owner/repo/extra.git",
        "not-a-url",
        "",
    ],
)
def test_parse_github_remote_url_rejects_unsupported_values(url: str) -> None:
    from hve.gui.page_options import _parse_github_remote_url

    assert _parse_github_remote_url(url) is None


def test_guess_repo_from_git_remote(monkeypatch) -> None:
    from hve.gui import page_options

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["git"],
            returncode=0,
            stdout="https://github.com/owner/repo.git\n",
            stderr="",
        )

    monkeypatch.setattr(page_options.subprocess, "run", fake_run)
    assert page_options._guess_repo_from_git_remote(cwd=".") == "owner/repo"


def test_guess_repo_from_git_remote_returns_none_on_failure(monkeypatch) -> None:
    from hve.gui import page_options

    def fake_run(*_args, **_kwargs):
        raise OSError("git not found")

    monkeypatch.setattr(page_options.subprocess, "run", fake_run)
    assert page_options._guess_repo_from_git_remote(cwd=".") is None


@pytest.mark.parametrize(
    ("repo", "expected"),
    [
        ("dahatake/RoyalytyService2ndGen", ("dahatake", "RoyalytyService2ndGen")),
        (" owner / repo ", ("owner", "repo")),
        ("owner", (None, None)),
        ("owner/repo/extra", (None, None)),
        ("", (None, None)),
    ],
)
def test_derive_cloud_repository_from_repo(
    repo: str,
    expected: tuple[str | None, str | None],
) -> None:
    from hve.gui.page_options import _derive_cloud_repository_from_repo

    assert _derive_cloud_repository_from_repo(repo) == expected


def _metadata(
    *,
    full_name: str = "owner/repo",
    has_issues: bool = True,
    default_branch: str = "main",
    permissions: dict | None = None,
    archived: bool = False,
) -> dict:
    return {
        "full_name": full_name,
        "has_issues": has_issues,
        "default_branch": default_branch,
        "permissions": permissions if permissions is not None else {"admin": True},
        "archived": archived,
    }


def test_repo_fetch_button_exists(qapp) -> None:
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    assert isinstance(w.fetch_repo_button, QPushButton)
    assert "リポジトリ" in w.fetch_repo_button.text()
    assert w.repo_fetch_status.text() == ""


def test_repo_metadata_success_populates_empty_repo_and_default_branch(qapp) -> None:
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    w.repo.setText("")
    w.branch.setText("main")
    w._on_repo_metadata_fetched(
        {"metadata": _metadata(full_name="owner/repo", default_branch="trunk"), "update_repo": True}
    )

    assert w.repo.text() == "owner/repo"
    assert w.branch.text() == "trunk"
    assert "owner/repo" in w.repo_fetch_status.text()
    assert "Issues" in w.repo_fetch_status.text()


def test_repo_metadata_success_updates_cloud_repository_args(qapp) -> None:
    from hve.gui.orchestrate_args import OrchestrateArgs
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    w.repo.setText("")
    w._on_repo_metadata_fetched(
        {"metadata": _metadata(full_name="owner/repo"), "update_repo": True}
    )

    args = OrchestrateArgs(workflow="aad-web")
    w.to_args(args)

    assert args.cloud_session_owner == "owner"
    assert args.cloud_session_repository_name == "repo"


def test_repo_metadata_does_not_overwrite_existing_repo(qapp) -> None:
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    w.repo.setText("manual/repo")
    w._on_repo_metadata_fetched(
        {"metadata": _metadata(full_name="api/repo"), "update_repo": False}
    )

    assert w.repo.text() == "manual/repo"
    assert "api/repo" in w.repo_fetch_status.text()


def test_repo_metadata_warns_when_issues_disabled(qapp) -> None:
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    w._on_repo_metadata_fetched(
        {"metadata": _metadata(has_issues=False), "update_repo": True}
    )

    assert "Issues" in w.repo_fetch_status.text()
    assert "無効" in w.repo_fetch_status.text()


def test_repo_metadata_warns_when_archived(qapp) -> None:
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    w._on_repo_metadata_fetched(
        {"metadata": _metadata(archived=True), "update_repo": True}
    )

    assert "アーカイブ" in w.repo_fetch_status.text()


def test_repo_metadata_error_shows_status(qapp) -> None:
    from hve.github_api import GitHubAPIError
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    w._on_repo_metadata_fetched(GitHubAPIError("not found", status=404))

    assert "not found" in w.repo_fetch_status.text()
    assert w.fetch_repo_button.isEnabled()


def test_repo_metadata_candidates_count_messages(qapp) -> None:
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    w._on_repo_metadata_fetched({"candidates": [{"full_name": "a/r"}, {"full_name": "b/r"}]})
    assert "複数" in w.repo_fetch_status.text()

    w._on_repo_metadata_fetched({"candidates": []})
    assert "見つかりません" in w.repo_fetch_status.text()
