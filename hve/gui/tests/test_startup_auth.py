"""hve.gui.tests.test_startup_auth

FR-GUI-24: GUI 起動時の GitHub 認証解決の単体テスト（offscreen）。

`gh` サブプロセスと GhLoginDialog は mock し、実 gh / 実ダイアログを起動しない。
"""

from __future__ import annotations

import os
from typing import List, Optional

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _clear_tokens():
    """テスト間でトークン環境変数を隔離する。

    `inject_token_into_env` は `os.environ` を直接書き換えるため、
    `monkeypatch.delenv` だけでは値が復元されず後続モジュールへ漏れる。
    """
    saved = {name: os.environ.get(name) for name in ("GH_TOKEN", "GITHUB_TOKEN")}
    for name in saved:
        os.environ.pop(name, None)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class _FakeDialog:
    """GhLoginDialog の代替（exec のみ提供）。"""

    instances: "List[_FakeDialog]" = []

    def __init__(self, parent=None) -> None:
        self.parent = parent
        _FakeDialog.instances.append(self)

    def exec(self) -> int:
        return 0


class TestResolveStartupToken:
    def test_env_token_short_circuits_gh(self, monkeypatch) -> None:
        from hve.gui import startup_auth

        os.environ["GH_TOKEN"] = "already"
        calls: List[str] = []

        def _capture(**_kw):
            calls.append("captured")
            return "unused"

        monkeypatch.setattr(startup_auth.gh_cli, "capture_gh_token", _capture)

        assert startup_auth.resolve_startup_token() is True
        assert calls == []
        assert os.environ["GH_TOKEN"] == "already"

    def test_github_token_env_also_counts(self, monkeypatch) -> None:
        from hve.gui import startup_auth

        os.environ["GITHUB_TOKEN"] = "gh-actions"
        monkeypatch.setattr(
            startup_auth.gh_cli,
            "capture_gh_token",
            lambda **_kw: pytest.fail("must not call gh when a token exists"),
        )

        assert startup_auth.resolve_startup_token() is True

    def test_captures_and_injects_when_env_missing(self, monkeypatch) -> None:
        from hve.gui import startup_auth

        monkeypatch.setattr(
            startup_auth.gh_cli, "capture_gh_token", lambda **_kw: "captured-token"
        )

        assert startup_auth.resolve_startup_token() is True
        assert os.environ["GH_TOKEN"] == "captured-token"

    def test_returns_false_when_gh_has_no_token(self, monkeypatch) -> None:
        from hve.gui import startup_auth

        monkeypatch.setattr(startup_auth.gh_cli, "capture_gh_token", lambda **_kw: None)

        assert startup_auth.resolve_startup_token() is False
        assert "GH_TOKEN" not in os.environ


class TestEnsureStartupAuthentication:
    def test_no_prompt_when_already_resolved(self, qapp, monkeypatch) -> None:
        from hve.gui import startup_auth

        os.environ["GH_TOKEN"] = "already"
        monkeypatch.setattr(
            startup_auth,
            "_prompt_login",
            lambda _parent: pytest.fail("must not prompt when a token exists"),
        )

        assert startup_auth.ensure_startup_authentication() is True

    def test_prompts_once_when_unresolved(self, qapp, monkeypatch) -> None:
        from hve.gui import startup_auth

        monkeypatch.setattr(startup_auth.gh_cli, "capture_gh_token", lambda **_kw: None)
        prompts: List[Optional[object]] = []
        monkeypatch.setattr(
            startup_auth, "_prompt_login", lambda parent: prompts.append(parent) or False
        )

        assert startup_auth.ensure_startup_authentication() is False
        assert len(prompts) == 1

    def test_decline_keeps_startup_usable(self, qapp, monkeypatch) -> None:
        """利用者が拒否しても例外を送出せず False を返すだけであること。"""
        from hve.gui import startup_auth

        _FakeDialog.instances.clear()
        monkeypatch.setattr(startup_auth.gh_cli, "capture_gh_token", lambda **_kw: None)
        monkeypatch.setattr(
            startup_auth,
            "_ask_login_confirmation",
            lambda _parent: QMessageBox.StandardButton.No,
        )
        monkeypatch.setattr(startup_auth, "_login_dialog_factory", lambda parent: _FakeDialog(parent))

        assert startup_auth.ensure_startup_authentication() is False
        assert _FakeDialog.instances == []

    def test_accept_runs_login_dialog_and_injects(self, qapp, monkeypatch) -> None:
        from hve.gui import startup_auth

        _FakeDialog.instances.clear()
        tokens = iter([None, "post-login-token"])
        monkeypatch.setattr(
            startup_auth.gh_cli, "capture_gh_token", lambda **_kw: next(tokens)
        )
        monkeypatch.setattr(
            startup_auth,
            "_ask_login_confirmation",
            lambda _parent: QMessageBox.StandardButton.Yes,
        )
        monkeypatch.setattr(startup_auth, "_login_dialog_factory", lambda parent: _FakeDialog(parent))

        assert startup_auth.ensure_startup_authentication() is True
        assert len(_FakeDialog.instances) == 1
        assert os.environ["GH_TOKEN"] == "post-login-token"

    def test_accept_but_still_unauthenticated_returns_false(self, qapp, monkeypatch) -> None:
        from hve.gui import startup_auth

        _FakeDialog.instances.clear()
        monkeypatch.setattr(startup_auth.gh_cli, "capture_gh_token", lambda **_kw: None)
        monkeypatch.setattr(
            startup_auth,
            "_ask_login_confirmation",
            lambda _parent: QMessageBox.StandardButton.Yes,
        )
        monkeypatch.setattr(startup_auth, "_login_dialog_factory", lambda parent: _FakeDialog(parent))

        assert startup_auth.ensure_startup_authentication() is False
        assert "GH_TOKEN" not in os.environ


class TestNoAutomaticGhAuthLogin:
    def test_module_does_not_spawn_processes_itself(self) -> None:
        """`gh auth login` の自動実行を行わないこと（FR-GUI-24）。

        起動時解決モジュールは自前でプロセスを起動せず、トークン捕捉は
        `gh_cli`、対話ログインは `GhLoginDialog` へ委譲する。
        """
        import ast
        from pathlib import Path

        import hve.gui.startup_auth as startup_auth

        source = Path(startup_auth.__file__).read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "subprocess" not in imported
        assert "os" in imported  # 環境変数の参照だけは行う
