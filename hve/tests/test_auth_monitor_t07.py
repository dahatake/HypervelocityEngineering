"""hve/tests/test_auth_monitor_t07.py — T07 で追加した AuthMonitor 拡張のテスト。

検証対象:
    - ``AuthMonitor.invalidate_provider(pid)`` で状態が UNKNOWN に戻り、
      ``provider_state_changed`` / ``snapshot_changed`` が発火する。
    - ``AuthMonitor.refresh_provider(pid)`` は invalidate + force_refresh 相当。
    - ``PluginAuthDialog.provider_authenticated`` シグナルが定義されている。
"""

from __future__ import annotations

import os

import pytest

try:
    from PySide6.QtCore import QCoreApplication  # noqa: F401
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    pytest.skip("PySide6 not installed", allow_module_level=True)

from hve.gui.auth_monitor import AuthMonitor
from hve.gui.auth_providers import AuthState, AuthStatus


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _FakeProvider:
    """テスト用最小プロバイダ。"""

    def __init__(self, pid: str, required: bool = False) -> None:
        self.id = pid
        self.display_name = pid
        self.required = required

    def is_applicable(self, settings):  # noqa: ANN001, ARG002
        return True

    def check_status(self, *, timeout: float = 15.0) -> AuthStatus:  # noqa: ARG002
        return AuthStatus(state=AuthState.AUTHENTICATED)

    def authenticate(self, **_kw):
        raise NotImplementedError


def test_invalidate_provider_resets_state_and_emits(qapp) -> None:
    mon = AuthMonitor()
    mon.set_providers([_FakeProvider("p1"), _FakeProvider("p2")])
    # 直接 internal state を AUTHENTICATED にしておく
    mon._states["p1"] = AuthState.AUTHENTICATED  # type: ignore[attr-defined]
    mon._states["p2"] = AuthState.AUTHENTICATED  # type: ignore[attr-defined]

    changes: list[tuple[str, str]] = []
    mon.provider_state_changed.connect(lambda pid, st: changes.append((pid, st)))

    mon.invalidate_provider("p1")

    assert mon.latest_state("p1") is AuthState.UNKNOWN
    assert mon.latest_state("p2") is AuthState.AUTHENTICATED
    assert ("p1", AuthState.UNKNOWN.value) in changes


def test_invalidate_unknown_provider_is_noop(qapp) -> None:
    """既に UNKNOWN のプロバイダを invalidate しても何も emit しない。"""
    mon = AuthMonitor()
    mon.set_providers([_FakeProvider("p1")])
    changes: list[tuple[str, str]] = []
    mon.provider_state_changed.connect(lambda pid, st: changes.append((pid, st)))
    mon.invalidate_provider("p1")  # 既定で UNKNOWN
    assert changes == []


def test_plugin_auth_dialog_has_provider_authenticated_signal(qapp) -> None:
    """PluginAuthDialog に T07 で追加したシグナルが定義されていることを確認。"""
    from hve.gui.plugin_auth_dialog import PluginAuthDialog

    assert hasattr(PluginAuthDialog, "provider_authenticated")


def test_provider_authenticated_emits_on_auth_finished(qapp) -> None:
    """`_on_auth_finished` 呼び出しで provider_authenticated が emit される (T07 / レビュー No.15)。

    実際の認証フローを起動せず、private メソッドを直接呼んで Signal の発火配線を検証。
    """
    from hve.gui.auth_providers import AuthResult, AuthState
    from hve.gui.plugin_auth_dialog import PluginAuthDialog

    # 最小プロバイダ 1 つを渡してダイアログ初期化
    provider = _FakeProvider("p1")
    dlg = PluginAuthDialog([provider])

    emitted: list[tuple[str, bool]] = []
    dlg.provider_authenticated.connect(lambda pid, ok: emitted.append((pid, ok)))

    # 認証完了をシミュレート
    fake_result = AuthResult(
        success=True, state=AuthState.AUTHENTICATED, message="ok"
    )
    dlg._on_auth_finished("p1", fake_result)

    assert ("p1", True) in emitted
