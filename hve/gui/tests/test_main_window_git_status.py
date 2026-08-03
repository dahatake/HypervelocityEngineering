"""MainWindow 下部ステータスバーの local Git 表示テスト。

要件:
- 画面下部に現在作業中の local Git リポジトリ名と local branch を表示する。
- remote branch は表示しない。
- detached HEAD / git 取得失敗でも GUI を落とさない。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_format_git_status_text_uses_repo_name_and_local_branch() -> None:
    from hve.gui.main_window import _format_git_status_text

    text = _format_git_status_text(Path("C:/work/RoyalytyService2ndGen"), "feature/local")

    assert text == "Git: RoyalytyService2ndGen @ feature/local"


def test_format_git_status_text_uses_unknown_when_branch_missing() -> None:
    from hve.gui.main_window import _format_git_status_text

    text = _format_git_status_text(Path("C:/work/RoyalytyService2ndGen"), None)

    assert text == "Git: RoyalytyService2ndGen @ 不明"


def test_resolve_local_git_branch_reads_local_branch_only(monkeypatch, tmp_path) -> None:
    from hve.gui import main_window

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    calls: list[list[str]] = []

    def fake_run(args, **_kwargs):
        calls.append(list(args))
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="feature/local\n",
            stderr="",
        )

    monkeypatch.setattr(main_window.subprocess, "run", fake_run)

    assert main_window._resolve_local_git_branch(repo_root) == "feature/local"
    assert calls == [["git", "branch", "--show-current"]]
    assert all("origin" not in arg for call in calls for arg in call)


def test_resolve_local_git_branch_uses_short_sha_for_detached_head(monkeypatch, tmp_path) -> None:
    from hve.gui import main_window

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    def fake_run(args, **_kwargs):
        if list(args) == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="\n", stderr="")
        if list(args) == ["git", "rev-parse", "--short", "HEAD"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="abc1234\n", stderr="")
        raise AssertionError(f"unexpected git command: {args!r}")

    monkeypatch.setattr(main_window.subprocess, "run", fake_run)

    assert main_window._resolve_local_git_branch(repo_root) == "detached:abc1234"


def test_resolve_local_git_branch_returns_none_on_failure(monkeypatch, tmp_path) -> None:
    from hve.gui import main_window

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    def fake_run(*_args, **_kwargs):
        raise OSError("git not found")

    monkeypatch.setattr(main_window.subprocess, "run", fake_run)

    assert main_window._resolve_local_git_branch(repo_root) is None


def test_resolve_local_git_branch_skips_non_git_directory(monkeypatch, tmp_path) -> None:
    from hve.gui import main_window

    def fake_run(*_args, **_kwargs):
        raise AssertionError("git command must not run for non-git directories")

    monkeypatch.setattr(main_window.subprocess, "run", fake_run)

    assert main_window._resolve_local_git_branch(tmp_path) is None


def test_main_window_status_bar_contains_git_repo_and_local_branch(
    qapp,
    monkeypatch,
    tmp_path,
) -> None:
    from hve.gui import settings_store
    from hve.gui import main_window

    repo_root = tmp_path / "RoyalytyService2ndGen"
    repo_root.mkdir()
    monkeypatch.setattr(
        settings_store,
        "settings_path",
        lambda: tmp_path / ".settings.txt",
    )
    monkeypatch.setattr(
        main_window,
        "_resolve_local_git_branch",
        lambda root: "feature/local" if root == repo_root else None,
    )

    win = main_window.MainWindow(repo_root=repo_root)
    try:
        labels = [label.text() for label in win.statusBar().findChildren(QLabel)]
    finally:
        win.close()
        win.deleteLater()

    git_labels = [text for text in labels if text.startswith("Git:")]
    assert git_labels == ["Git: RoyalytyService2ndGen @ feature/local"]
    assert "origin/" not in git_labels[0]


def test_refresh_git_status_label_updates_branch_text(
    qapp,
    monkeypatch,
    tmp_path,
) -> None:
    from hve.gui import settings_store
    from hve.gui import main_window

    repo_root = tmp_path / "RoyalytyService2ndGen"
    repo_root.mkdir()
    monkeypatch.setattr(
        settings_store,
        "settings_path",
        lambda: tmp_path / ".settings.txt",
    )
    branches = iter(["feature/old", "feature/new"])
    monkeypatch.setattr(
        main_window,
        "_resolve_local_git_branch",
        lambda _root: next(branches),
    )

    win = main_window.MainWindow(repo_root=repo_root)
    try:
        assert win._git_status_label.text() == "Git: RoyalytyService2ndGen @ feature/old"

        win._refresh_git_status_label()

        assert win._git_status_label.text() == "Git: RoyalytyService2ndGen @ feature/new"
    finally:
        win.close()
        win.deleteLater()
