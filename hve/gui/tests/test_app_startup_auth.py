"""hve.gui.tests.test_app_startup_auth

FR-GUI-24: `run_app` が起動時に GitHub 認証解決を 1 回だけ実行し、
未認証のままでも GUI 起動を継続することを検証する（offscreen）。
"""

from __future__ import annotations

import os
from typing import Any, List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def stubbed_app(qapp, monkeypatch):
    """`run_app` の重い副作用（ウィンドウ生成・索引更新・イベントループ）を無効化する。"""
    from hve.gui import app as app_module

    opened: List[Any] = []
    monkeypatch.setattr(
        app_module, "_open_first_window", lambda initial_catalog=None: opened.append(initial_catalog)
    )
    monkeypatch.setattr(app_module, "start_startup_index_refresh", lambda _root: False)
    monkeypatch.setattr(QApplication, "exec", lambda _self: 0)
    return app_module, opened


class TestRunAppStartupAuth:
    def test_calls_startup_auth_once(self, stubbed_app, monkeypatch) -> None:
        app_module, opened = stubbed_app
        calls: List[Any] = []
        monkeypatch.setattr(
            app_module, "_run_startup_github_auth", lambda: calls.append("called")
        )

        assert app_module.run_app(None) == 0
        assert calls == ["called"]
        assert opened == [None]

    def test_declined_auth_still_opens_window(self, stubbed_app, monkeypatch) -> None:
        app_module, opened = stubbed_app
        from hve.gui import startup_auth

        monkeypatch.setattr(startup_auth, "resolve_startup_token", lambda: False)
        monkeypatch.setattr(startup_auth, "_prompt_login", lambda _parent: False)

        assert app_module.run_app(None) == 0
        assert opened == [None]

    def test_auth_exception_does_not_block_startup(self, stubbed_app, monkeypatch, capsys) -> None:
        """認証解決が例外を投げても GUI 起動を継続すること（FR-GUI-24）。"""
        app_module, opened = stubbed_app
        from hve.gui import startup_auth

        def _boom(*_a, **_kw):
            raise RuntimeError("gh exploded")

        monkeypatch.setattr(startup_auth, "ensure_startup_authentication", _boom)

        assert app_module.run_app(None) == 0
        assert opened == [None]
        assert "gh exploded" in capsys.readouterr().err

    def test_autopilot_child_skips_startup_auth(self, qapp, monkeypatch) -> None:
        """`--autopilot-child` の子 GUI では認証解決を行わないこと。"""
        from hve.gui import app as app_module

        calls: List[Any] = []
        monkeypatch.setattr(
            app_module, "_run_startup_github_auth", lambda: calls.append("called")
        )
        monkeypatch.setattr(app_module, "_open_autopilot_child_window", lambda _args: 0)
        monkeypatch.setattr(QApplication, "exec", lambda _self: 0)

        class _Args:
            autopilot_child = True

        assert app_module.run_app(_Args()) == 0
        assert calls == []


class TestRunStartupGithubAuth:
    def test_uses_first_window_as_parent(self, qapp, monkeypatch) -> None:
        from hve.gui import app as app_module
        from hve.gui import startup_auth

        sentinel = object()
        monkeypatch.setattr(app_module, "_open_windows", [sentinel])
        seen: List[Any] = []
        monkeypatch.setattr(
            startup_auth,
            "ensure_startup_authentication",
            lambda parent=None: seen.append(parent) or True,
        )

        app_module._run_startup_github_auth()
        assert seen == [sentinel]

    def test_no_window_passes_none(self, qapp, monkeypatch) -> None:
        from hve.gui import app as app_module
        from hve.gui import startup_auth

        monkeypatch.setattr(app_module, "_open_windows", [])
        seen: List[Any] = []
        monkeypatch.setattr(
            startup_auth,
            "ensure_startup_authentication",
            lambda parent=None: seen.append(parent) or True,
        )

        app_module._run_startup_github_auth()
        assert seen == [None]
