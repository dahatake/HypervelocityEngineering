"""Work IQ 認証確認ボタンの単体テスト。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_workiq_auth_button_exists(qapp) -> None:
    from hve.gui.page_options import _C4WorkIQ

    w = _C4WorkIQ()
    try:
        assert isinstance(w.workiq_auth_button, QPushButton)
        assert "Work IQ" in w.workiq_auth_button.text()
        assert "未確認" in w.workiq_auth_status.text()
    finally:
        w.deleteLater()


def test_workiq_auth_success_updates_status(qapp) -> None:
    from hve.gui.page_options import _C4WorkIQ

    w = _C4WorkIQ()
    try:
        w.workiq_auth_button.setEnabled(False)
        w._on_workiq_auth_finished({"ok": True, "detail": ""})
        assert w.workiq_auth_button.isEnabled()
        assert "確認済み" in w.workiq_auth_status.text()
    finally:
        w.deleteLater()


def test_workiq_auth_exception_updates_status_without_thread(qapp, monkeypatch) -> None:
    from hve.gui.page_options import _C4WorkIQ

    warnings: list[str] = []
    monkeypatch.setattr(
        "hve.gui.page_options.QMessageBox.warning",
        lambda *_args, **_kwargs: warnings.append("warn"),
    )
    w = _C4WorkIQ()
    try:
        w._on_workiq_auth_finished(RuntimeError("boom"))
        assert w.workiq_auth_button.isEnabled()
        assert "失敗" in w.workiq_auth_status.text()
        assert warnings == ["warn"]
    finally:
        w.deleteLater()
