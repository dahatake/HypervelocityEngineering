"""GUI が起動する HVE サブプロセスの標準入力契約（FR-GUI-23）。

GUI 側に子プロセスへ入力を送る経路が無いため、CLI 側の対話プロンプト
（認証 preflight / `--autopilot-chain` の実行確認）へ到達すると応答不能になる。
標準入力を対話不能な状態で起動することを固定する。
"""

from __future__ import annotations

import os
import subprocess
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hve.gui.state_bridge import launch_orchestrator  # noqa: E402


def test_launch_orchestrator_disables_stdin() -> None:
    with mock.patch("hve.gui.state_bridge.subprocess.Popen") as popen_mock:
        launch_orchestrator(["orchestrate", "--workflow", "aas"])
    _, kwargs = popen_mock.call_args
    assert kwargs["stdin"] is subprocess.DEVNULL
