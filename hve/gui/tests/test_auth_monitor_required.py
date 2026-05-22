"""hve.gui.tests.test_auth_monitor_required — T14 (Wave 5).

``AuthMonitor.required_provider_ids()`` が settings に応じて動的判定されることを検証。
QObject 生成のため PySide6 が必要。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.auth_monitor import AuthMonitor  # noqa: E402


def _ensure_app() -> QApplication:
    # 他テストで MainWindow 等のウィジェット生成があるため QApplication を使用。
    # QCoreApplication を先に作ると以降のウィジェット生成が失敗する。
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


class _Provider:
    """``is_required(settings)`` を持つ軽量テスト用プロバイダ。"""

    def __init__(self, pid: str, predicate) -> None:
        self.id = pid
        self.display_name = pid
        self.required = False  # legacy field; ignored by helper when is_required exists
        self._pred = predicate

    def is_required(self, settings: dict) -> bool:
        return bool(self._pred(settings))

    def is_applicable(self, settings: dict) -> bool:  # noqa: ARG002
        return True


def test_required_ids_dynamic_workiq_off() -> None:
    _ensure_app()
    mon = AuthMonitor()
    workiq = _Provider("workiq", lambda s: bool(s.get("options", {}).get("workiq")))
    github = _Provider("github", lambda _s: True)
    mon.set_providers([github, workiq], {"options": {"workiq": False}})
    assert mon.required_provider_ids() == {"github"}


def test_required_ids_dynamic_workiq_on() -> None:
    _ensure_app()
    mon = AuthMonitor()
    workiq = _Provider("workiq", lambda s: bool(s.get("options", {}).get("workiq")))
    github = _Provider("github", lambda _s: True)
    mon.set_providers([github, workiq], {"options": {"workiq": True}})
    assert mon.required_provider_ids() == {"github", "workiq"}


def test_set_settings_changes_required_ids() -> None:
    _ensure_app()
    mon = AuthMonitor()
    workiq = _Provider("workiq", lambda s: bool(s.get("options", {}).get("workiq")))
    mon.set_providers([workiq], {"options": {"workiq": False}})
    assert mon.required_provider_ids() == set()
    mon.set_settings({"options": {"workiq": True}})
    assert mon.required_provider_ids() == {"workiq"}


def test_legacy_provider_without_is_required_falls_back_to_required_attr() -> None:
    _ensure_app()
    mon = AuthMonitor()

    class _Legacy:
        id = "legacy"
        display_name = "Legacy"
        required = True

        def is_applicable(self, s: dict) -> bool:  # noqa: ARG002
            return True

    mon.set_providers([_Legacy()], {})
    assert mon.required_provider_ids() == {"legacy"}
