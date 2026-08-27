"""FR-MAINT-10: macOS の実 Cocoa session で HVE GUI を起動する。"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest


pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="macOS Cocoa platform plugin is required",
)


def test_hve_gui_starts_on_cocoa_without_qt_errors(monkeypatch, tmp_path) -> None:
    from PySide6.QtCore import QCoreApplication, QtMsgType, QTimer, qInstallMessageHandler
    from PySide6.QtWidgets import QApplication

    from hve import index_refresh
    from hve.gui import app as gui_app
    from hve.gui import startup_auth

    assert os.environ.get("QT_QPA_PLATFORM") == "cocoa"
    application = QApplication.instance() or QApplication(sys.argv[:1])
    assert isinstance(application, QApplication)
    assert application.platformName() == "cocoa"

<<<<<<< HEAD
    artifact_dir = Path(
        os.environ.get("HVE_MACOS_GUI_ARTIFACT_DIR", tmp_path / "artifacts")
    )
=======
    artifact_dir = Path(os.environ.get("HVE_MACOS_GUI_ARTIFACT_DIR", tmp_path / "artifacts"))
>>>>>>> 759960c3640e123b72e5f09cc9b18613554982a3
    artifact_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifact_dir / "hve-main-window.png"
    qt_log_path = artifact_dir / "qt-messages.log"

    messages: list[tuple[QtMsgType, str]] = []
    callback_errors: list[BaseException] = []
    captured = False

    def handle_qt_message(msg_type, _context, message) -> None:
        messages.append((msg_type, message))

    previous_handler = qInstallMessageHandler(handle_qt_message)
    auth_stub = Mock(return_value=False)
    refresh_stub = Mock(return_value=False)
<<<<<<< HEAD

    monkeypatch.setattr(
        startup_auth,
        "ensure_startup_authentication",
        auth_stub,
    )
    monkeypatch.setattr(
        index_refresh,
        "start_background",
        refresh_stub,
    )
=======
    monkeypatch.setattr(startup_auth, "ensure_startup_authentication", auth_stub)
    monkeypatch.setattr(index_refresh, "start_background", refresh_stub)
>>>>>>> 759960c3640e123b72e5f09cc9b18613554982a3
    monkeypatch.setattr(index_refresh, "is_running", lambda: False)

    def capture_and_close() -> None:
        nonlocal captured
        try:
            assert len(gui_app._open_windows) == 1
            window = gui_app._open_windows[0]
            application.processEvents()
            captured = window.grab().save(str(screenshot_path), "PNG")
        except Exception as exc:
            callback_errors.append(exc)
        finally:
            for window in list(gui_app._open_windows):
                window.close()
            application.quit()

    try:
        QTimer.singleShot(1000, capture_and_close)
        return_code = gui_app.run_app()
    finally:
        qInstallMessageHandler(previous_handler)
        qt_log_path.write_text(
            "".join(f"{msg_type.name}: {message}\n" for msg_type, message in messages),
            encoding="utf-8",
        )
        for window in list(gui_app._open_windows):
            window.close()
        QCoreApplication.processEvents()

    assert return_code == 0
    assert auth_stub.call_count == 1
    assert refresh_stub.call_count == 1
    assert not callback_errors
    assert captured
    assert screenshot_path.is_file()
    assert screenshot_path.stat().st_size > 0

<<<<<<< HEAD
    failing_types = {
        QtMsgType.QtWarningMsg,
        QtMsgType.QtCriticalMsg,
        QtMsgType.QtFatalMsg,
    }
    failures = [
        f"{msg_type.name}: {message}"
        for msg_type, message in messages
        if msg_type in failing_types
    ]
=======
    failing_types = {QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg}
    failures = [f"{msg_type.name}: {message}" for msg_type, message in messages if msg_type in failing_types]
>>>>>>> 759960c3640e123b72e5f09cc9b18613554982a3
    assert not failures, "Unexpected Qt messages:\n" + "\n".join(failures)
