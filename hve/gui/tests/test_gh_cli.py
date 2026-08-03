"""hve.gui.tests.test_gh_cli

gh_cli ヘルパ（find_gh_binary / capture_gh_token / inject_token_into_env）の
単体テスト。subprocess / shutil.which を mock し、ネットワーク・実 gh に依存しない。
"""

from __future__ import annotations

import os
import subprocess
from types import SimpleNamespace

import pytest

from hve.gui import gh_cli


# ---------------------------------------------------------------------------
# find_gh_binary
# ---------------------------------------------------------------------------
def test_find_gh_binary_returns_which_result(monkeypatch) -> None:
    monkeypatch.setattr(gh_cli.shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
    assert gh_cli.find_gh_binary() == "/usr/bin/gh"


def test_find_gh_binary_none_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(gh_cli.shutil, "which", lambda _name: None)
    assert gh_cli.find_gh_binary() is None


# ---------------------------------------------------------------------------
# capture_gh_token
# ---------------------------------------------------------------------------
def test_capture_token_success(monkeypatch) -> None:
    monkeypatch.setattr(gh_cli, "find_gh_binary", lambda: "/usr/bin/gh")

    def fake_run(argv, **_kw):
        assert argv == ["/usr/bin/gh", "auth", "token"]
        return SimpleNamespace(returncode=0, stdout="ghp_abc123\n", stderr="")

    monkeypatch.setattr(gh_cli.subprocess, "run", fake_run)
    assert gh_cli.capture_gh_token() == "ghp_abc123"


def test_capture_token_none_when_gh_missing(monkeypatch) -> None:
    monkeypatch.setattr(gh_cli, "find_gh_binary", lambda: None)
    # find_gh_binary が None のため subprocess.run は呼ばれない。
    called = {"run": False}

    def fake_run(*_a, **_k):
        called["run"] = True
        return SimpleNamespace(returncode=0, stdout="x", stderr="")

    monkeypatch.setattr(gh_cli.subprocess, "run", fake_run)
    assert gh_cli.capture_gh_token() is None
    assert called["run"] is False


def test_capture_token_none_on_nonzero_returncode(monkeypatch) -> None:
    monkeypatch.setattr(gh_cli, "find_gh_binary", lambda: "/usr/bin/gh")
    monkeypatch.setattr(
        gh_cli.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="", stderr="not logged in"),
    )
    assert gh_cli.capture_gh_token() is None


def test_capture_token_none_on_timeout(monkeypatch) -> None:
    monkeypatch.setattr(gh_cli, "find_gh_binary", lambda: "/usr/bin/gh")

    def fake_run(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="gh auth token", timeout=15.0)

    monkeypatch.setattr(gh_cli.subprocess, "run", fake_run)
    assert gh_cli.capture_gh_token() is None


def test_capture_token_none_on_oserror(monkeypatch) -> None:
    monkeypatch.setattr(gh_cli, "find_gh_binary", lambda: "/usr/bin/gh")

    def fake_run(*_a, **_k):
        raise OSError("spawn failed")

    monkeypatch.setattr(gh_cli.subprocess, "run", fake_run)
    assert gh_cli.capture_gh_token() is None


def test_capture_token_empty_stdout_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(gh_cli, "find_gh_binary", lambda: "/usr/bin/gh")
    monkeypatch.setattr(
        gh_cli.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout="   \n", stderr=""),
    )
    assert gh_cli.capture_gh_token() is None


# ---------------------------------------------------------------------------
# inject_token_into_env
# ---------------------------------------------------------------------------
@pytest.fixture
def restore_gh_token():
    """テスト前後で os.environ['GH_TOKEN'] を退避・復元する。"""
    original = os.environ.get("GH_TOKEN")
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("GH_TOKEN", None)
        else:
            os.environ["GH_TOKEN"] = original


def test_inject_token_sets_env(restore_gh_token) -> None:
    os.environ.pop("GH_TOKEN", None)
    gh_cli.inject_token_into_env("ghp_xyz")
    assert os.environ["GH_TOKEN"] == "ghp_xyz"


def test_inject_empty_token_is_noop(restore_gh_token) -> None:
    os.environ["GH_TOKEN"] = "preexisting"
    gh_cli.inject_token_into_env("")
    # 空文字列では既存値を消さない。
    assert os.environ["GH_TOKEN"] == "preexisting"


def test_inject_token_overwrites_existing(restore_gh_token) -> None:
    # 明示ログイン操作の意図どおり、既存 GH_TOKEN を新トークンで上書きする。
    os.environ["GH_TOKEN"] = "old_token"
    gh_cli.inject_token_into_env("new_token")
    assert os.environ["GH_TOKEN"] == "new_token"
