"""hve/tests/test_pty_e2e_smoke.py — PTY + xterm.js + コントローラ + ダイアログの E2E スモーク。

実際の `copilot` / `az` / `gh` バイナリは存在を仮定せず、OS 標準の `echo` / `cmd.exe`
で代用してフロー全体（T01 〜 T06）が結合して動くことを確認する。

skip 条件:
    - PySide6 / QtWebEngine 不在
    - PTY バックエンド (pywinpty / ptyprocess) 不在
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


from hve.gui.auth_providers import (
    AuthState,
    InteractivePlan,
    provider_supports_interactive,
)
from hve.gui.auth_providers.mcp_generic_provider import McpGenericProvider
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


def _wait_for_final(dlg: PtyAuthSessionWidget, timeout_ms: int = 30000) -> bool:
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(50)
    dl = QTimer()
    dl.setSingleShot(True)
    dl.timeout.connect(loop.quit)
    dl.start(timeout_ms)
    poll.timeout.connect(
        lambda: loop.quit() if dlg._final is not None else None  # type: ignore[attr-defined]
    )
    poll.start()
    dlg.show()
    loop.exec()
    poll.stop()
    dl.stop()
    return dlg._final is not None  # type: ignore[attr-defined]


def test_e2e_mcp_provider_to_dialog_to_pty(qapp) -> None:
    """McpGenericProvider → build_interactive_plan → PtyAuthSessionWidget → PTY 実行
    の全層が連動することを確認 (echo 系コマンドで代用)。"""
    provider = McpGenericProvider("azure", {"command": "dummy"})
    assert provider_supports_interactive(provider)

    # 本物の `az login` は環境依存のため、plan の pre_commands を echo に差し替えて検証する。
    plan = provider.build_interactive_plan({})
    assert plan is not None
    test_plan = InteractivePlan(
        display_name=plan.display_name,
        pre_commands=[
            CommandSpec(
                _shell_argv("echo Subscription is set to test-sub"),
                success_regex=r"Subscription is set",
                timeout=10,
            )
        ],
        notes_md=plan.notes_md,
        timeout_total=30.0,
        source_manifest_id=plan.source_manifest_id,
    )

    dlg = PtyAuthSessionWidget(test_plan)
    assert _wait_for_final(dlg, timeout_ms=20000), "E2E flow did not finalize"
    result = dlg.final_result()
    assert result.success is True
    assert result.state == AuthState.AUTHENTICATED


def test_e2e_graceful_degradation_when_pty_missing(qapp, monkeypatch: pytest.MonkeyPatch) -> None:
    """PTY 不在を疑似的に再現したとき、ダイアログが即失敗終了する (graceful degradation)。"""
    monkeypatch.setattr(pty_backend, "is_pty_available", lambda: False)
    plan = InteractivePlan(
        display_name="no-pty",
        pre_commands=[CommandSpec(_shell_argv("echo x"), timeout=5)],
    )
    dlg = PtyAuthSessionWidget(plan)
    # 即時 final にマークされる (PTY 起動前にチェックして失敗扱い)
    assert dlg._final is not None  # type: ignore[attr-defined]
    assert dlg.final_result().success is False
    assert "PTY" in (dlg.final_result().message or "")
