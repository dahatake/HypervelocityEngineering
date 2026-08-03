"""hve.gui.tests.test_gh_login_button

C5「GitHub」セクションの「GitHub CLI でログイン」ボタンの単体テスト（offscreen）。

GhLoginDialog と gh_cli を mock し、実 gh / 実ダイアログを起動せずに
ボタンの存在・初期状態ラベル・ログイン後のトークン注入と状態更新を検証する。
"""

from __future__ import annotations

import os
from typing import List, Optional

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QGroupBox, QPushButton  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeDialog:
    """GhLoginDialog の代替（exec のみ提供）。実 gh / 実端末を起動しない。"""

    instances: "List[_FakeDialog]" = []

    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.exec_called = False
        _FakeDialog.instances.append(self)

    def exec(self) -> int:
        self.exec_called = True
        return 0


def test_login_button_exists(qapp) -> None:
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    assert isinstance(w.gh_login_button, QPushButton)
    assert "ログイン" in w.gh_login_button.text()


def test_login_group_keeps_auth_section(qapp) -> None:
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    assert isinstance(w.gh_auth_group, QGroupBox)
    assert w.gh_auth_group.title() == "認証"
    assert w.gh_login_button is w.gh_auth_group.gh_login_button
    assert w.gh_login_status is w.gh_auth_group.gh_login_status


def test_initial_status_authenticated_when_token_present(qapp, monkeypatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "x")
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    assert "認証済み" in w.gh_login_status.text()


def test_initial_status_not_logged_in_without_token(qapp, monkeypatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    assert "未ログイン" in w.gh_login_status.text()


def test_login_success_injects_token_and_updates_status(qapp, monkeypatch) -> None:
    from hve.gui.page_options import _C5IssuePR
    import hve.gui.gh_cli as gh_cli
    import hve.gui.gh_login_dialog as gld

    _FakeDialog.instances.clear()
    monkeypatch.setattr(gld, "GhLoginDialog", _FakeDialog)
    monkeypatch.setattr(gh_cli, "capture_gh_token", lambda **_k: "ghp_tok")
    injected: dict = {}
    monkeypatch.setattr(
        gh_cli, "inject_token_into_env", lambda t: injected.__setitem__("t", t)
    )
    auto_fetch_calls: List[bool] = []
    monkeypatch.setattr(
        _C5IssuePR,
        "_start_repo_metadata_fetch",
        lambda self, *, auto: auto_fetch_calls.append(auto),
    )

    w = _C5IssuePR()
    w._on_gh_login_clicked()

    assert _FakeDialog.instances and _FakeDialog.instances[-1].exec_called
    # ダイアログは C5 ウィジェットを親として生成される（modal 親子関係）。
    assert _FakeDialog.instances[-1].parent is w
    assert injected["t"] == "ghp_tok"
    assert "ログイン済み" in w.gh_login_status.text()
    assert auto_fetch_calls == [True]


def test_login_failure_shows_warning_and_no_injection(qapp, monkeypatch) -> None:
    from hve.gui.page_options import _C5IssuePR
    import hve.gui.gh_cli as gh_cli
    import hve.gui.gh_login_dialog as gld

    monkeypatch.setattr(gld, "GhLoginDialog", _FakeDialog)
    monkeypatch.setattr(gh_cli, "capture_gh_token", lambda **_k: None)
    injected = {"called": False}
    monkeypatch.setattr(
        gh_cli, "inject_token_into_env", lambda _t: injected.__setitem__("called", True)
    )
    auto_fetch_calls: List[bool] = []
    monkeypatch.setattr(
        _C5IssuePR,
        "_start_repo_metadata_fetch",
        lambda self, *, auto: auto_fetch_calls.append(auto),
    )

    w = _C5IssuePR()
    w._on_gh_login_clicked()

    assert injected["called"] is False
    assert auto_fetch_calls == []
    assert "取得できませんでした" in w.gh_login_status.text()
