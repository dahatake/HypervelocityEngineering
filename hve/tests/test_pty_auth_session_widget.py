"""hve/tests/test_pty_auth_session_widget.py — PtyAuthSessionWidget の動作テスト。

実 PTY (T01) + xterm.js (T02) + コントローラ (T03) を統合した結合テスト。
QtWebEngine + PTY が両方利用可能な環境でのみ実行。
"""

from __future__ import annotations

import os
import sys

import pytest

try:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    pytest.skip("PySide6 / QtWebEngine not installed", allow_module_level=True)

from hve.gui import pty_backend

if not pty_backend.is_pty_available():
    pytest.skip("PTY backend not installed", allow_module_level=True)

from hve.gui.auth_providers import AuthState, InteractivePlan
from hve.gui.pty_auth_controller import CommandSpec
from hve.gui.pty_auth_session_widget import PtyAuthSessionWidget


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _shell_argv(script: str) -> list[str]:
    if sys.platform.startswith("win"):
        return ["cmd.exe", "/c", script]
    return ["/bin/sh", "-c", script]


def _wait_for_dialog(dlg: PtyAuthSessionWidget, timeout_ms: int = 30000) -> bool:
    """ダイアログが accept/reject か final_result 確定するまで待つ。"""
    loop = QEventLoop()
    finished_flag = {"v": False}

    def _check() -> None:
        if dlg._final is not None:  # type: ignore[attr-defined]
            finished_flag["v"] = True
            loop.quit()

    poll = QTimer()
    poll.setInterval(50)
    poll.timeout.connect(_check)
    poll.start()

    dl = QTimer()
    dl.setSingleShot(True)
    dl.timeout.connect(loop.quit)
    dl.start(timeout_ms)

    dlg.show()
    loop.exec()
    poll.stop()
    dl.stop()
    return finished_flag["v"]


def test_all_steps_succeed(qapp) -> None:
    """全 pre_commands が success_regex にマッチ → success=True。"""
    plan = InteractivePlan(
        display_name="test-all-ok",
        pre_commands=[
            CommandSpec(_shell_argv("echo STEP_ONE_OK"), success_regex=r"STEP_ONE_OK", timeout=10),
            CommandSpec(_shell_argv("echo STEP_TWO_OK"), success_regex=r"STEP_TWO_OK", timeout=10),
        ],
        timeout_total=60.0,
    )
    dlg = PtyAuthSessionWidget(plan)
    assert _wait_for_dialog(dlg, timeout_ms=30000), "dialog did not finalize in time"
    result = dlg.final_result()
    assert result.success is True
    assert result.state == AuthState.AUTHENTICATED


def test_failure_regex_stops_flow(qapp) -> None:
    """failure_regex がヒット → success=False。残ステップは実行されない。"""
    plan = InteractivePlan(
        display_name="test-fail-fast",
        pre_commands=[
            CommandSpec(
                _shell_argv("echo AUTHENTICATION FAILED"),
                success_regex=r"NEVER",
                failure_regex=r"AUTHENTICATION FAILED",
                timeout=10,
            ),
            CommandSpec(
                _shell_argv("echo SHOULD_NOT_RUN"),
                success_regex=r"SHOULD_NOT_RUN",
                timeout=10,
            ),
        ],
        timeout_total=60.0,
    )
    dlg = PtyAuthSessionWidget(plan)
    assert _wait_for_dialog(dlg, timeout_ms=30000)
    result = dlg.final_result()
    assert result.success is False
    assert result.state == AuthState.NOT_AUTHENTICATED
    assert "failure pattern matched" in (result.message or "").lower()


def test_empty_plan_treated_as_success(qapp) -> None:
    """pre_commands も main_command も無い plan は即 success 扱い (フォールバック相当)。"""
    plan = InteractivePlan(display_name="empty")
    dlg = PtyAuthSessionWidget(plan)
    # 即座に final_result が確定するため待機ほぼ不要
    assert _wait_for_dialog(dlg, timeout_ms=5000)
    assert dlg.final_result().success is True
