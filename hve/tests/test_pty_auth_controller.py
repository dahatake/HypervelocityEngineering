"""hve/tests/test_pty_auth_controller.py — PTY 認証コントローラのテスト。

実 PTY を使う統合テストのみ。``is_pty_available()`` が False なら丸ごと skip。
"""

from __future__ import annotations

import os
import sys

import pytest

try:
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    pytest.skip("PySide6 not installed", allow_module_level=True)

from hve.gui import pty_backend
from hve.gui.pty_auth_controller import CommandSpec, PtyAuthController

if not pty_backend.is_pty_available():
    pytest.skip("PTY backend not installed", allow_module_level=True)


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _run_until(predicate, timeout_ms: int = 15000) -> bool:
    loop = QEventLoop()
    dl = QTimer()
    dl.setSingleShot(True)
    dl.timeout.connect(loop.quit)
    dl.start(timeout_ms)
    poll = QTimer()
    poll.setInterval(50)

    def _check() -> None:
        if predicate():
            loop.quit()

    poll.timeout.connect(_check)
    poll.start()
    loop.exec()
    poll.stop()
    dl.stop()
    return predicate()


def _shell_argv(script: str) -> list[str]:
    if sys.platform.startswith("win"):
        return ["cmd.exe", "/c", script]
    return ["/bin/sh", "-c", script]


def test_success_pattern_match(qapp) -> None:
    """success_regex がヒットしたら finished(True, ...) を発火する。"""
    ctrl = PtyAuthController()
    result = {"success": None, "message": ""}

    def on_finished(ok: bool, msg: str) -> None:
        result["success"] = ok
        result["message"] = msg

    ctrl.finished.connect(on_finished)

    # echo で 'AUTH_OK_TOKEN' を出力して終了
    ctrl.start(
        CommandSpec(
            _shell_argv("echo AUTH_OK_TOKEN"),
            success_regex=r"AUTH_OK_TOKEN",
            timeout=10.0,
        )
    )
    assert _run_until(lambda: result["success"] is not None, timeout_ms=15000)
    assert result["success"] is True, f"expected success, got {result}"


def test_failure_pattern_match(qapp) -> None:
    """failure_regex がヒットしたら finished(False, ...) を発火する。"""
    ctrl = PtyAuthController()
    result = {"success": None, "message": ""}
    ctrl.finished.connect(lambda ok, msg: result.update(success=ok, message=msg))

    ctrl.start(
        CommandSpec(
            _shell_argv("echo AUTHENTICATION FAILED"),
            success_regex=r"SUCCESS_NEVER_APPEARS",
            failure_regex=r"AUTHENTICATION FAILED",
            timeout=10.0,
        )
    )
    assert _run_until(lambda: result["success"] is not None, timeout_ms=15000)
    assert result["success"] is False
    assert "failure pattern matched" in result["message"]


def test_timeout(qapp) -> None:
    """timeout 超過で finished(False, "timeout...") を発火する。"""
    ctrl = PtyAuthController()
    result = {"success": None, "message": ""}
    ctrl.finished.connect(lambda ok, msg: result.update(success=ok, message=msg))

    if sys.platform.startswith("win"):
        script = "ping -n 30 127.0.0.1 > NUL"
    else:
        script = "sleep 30"
    ctrl.start(
        CommandSpec(
            _shell_argv(script),
            success_regex=r"NEVER",
            timeout=1.0,
        )
    )
    assert _run_until(lambda: result["success"] is not None, timeout_ms=10000)
    assert result["success"] is False
    assert "timeout" in result["message"].lower()


def test_exit_zero_without_pattern_is_success(qapp) -> None:
    """success_regex 未指定なら exit code 0 で成功扱い。"""
    ctrl = PtyAuthController()
    result = {"success": None}
    ctrl.finished.connect(lambda ok, msg: result.update(success=ok))

    ctrl.start(CommandSpec(_shell_argv("echo done"), timeout=10.0))
    assert _run_until(lambda: result["success"] is not None, timeout_ms=15000)
    assert result["success"] is True


def test_cancel(qapp) -> None:
    """cancel() で finished(False, "cancelled...") を発火する。"""
    ctrl = PtyAuthController()
    result = {"success": None, "message": ""}
    ctrl.finished.connect(lambda ok, msg: result.update(success=ok, message=msg))

    if sys.platform.startswith("win"):
        script = "ping -n 30 127.0.0.1 > NUL"
    else:
        script = "sleep 30"
    ctrl.start(CommandSpec(_shell_argv(script), timeout=60.0))
    QTimer.singleShot(300, ctrl.cancel)
    assert _run_until(lambda: result["success"] is not None, timeout_ms=10000)
    assert result["success"] is False
    assert "cancel" in result["message"].lower()
