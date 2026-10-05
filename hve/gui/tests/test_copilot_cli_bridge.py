"""hve.gui.tests.test_copilot_cli_bridge — CopilotCliBridge ユニットテスト。

subprocess 呼び出しは ``unittest.mock.patch`` で差し替え、実 CLI は呼ばない。
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from hve.gui.copilot_cli_bridge import CopilotCliBridge


_FAKE_EXE = "/fake/bin/copilot"


def _mock_completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


# ---------------------------------------------------------------------------
# find_binary / is_available
# ---------------------------------------------------------------------------
class TestFindBinary:
    def test_returns_none_when_underlying_returns_none(self) -> None:
        with patch("hve.auth.find_copilot_binary", return_value=None):
            assert CopilotCliBridge.find_binary() is None
            assert CopilotCliBridge.is_available() is False

    def test_returns_path_when_found(self) -> None:
        with patch("hve.auth.find_copilot_binary", return_value=_FAKE_EXE):
            assert CopilotCliBridge.find_binary() == _FAKE_EXE
            assert CopilotCliBridge.is_available() is True


# ---------------------------------------------------------------------------
# FR-GUI-51 / FR-MAINT-07: Plugin / MCP 一覧は SDK discovery の単一実装だけ
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "removed",
    [
        "list_plugin_resources",
        "parse_plugin_resources_json",
        "list_mcp_servers",
        "mcp_servers_from_resources",
        "get_mcp_server",
        "list_plugins",
        "plugins_from_resources",
    ],
)
def test_cli_resource_listing_is_not_duplicated(removed: str) -> None:
    assert not hasattr(CopilotCliBridge, removed)


def test_cli_bridge_does_not_export_plugin_info() -> None:
    import hve.gui.copilot_cli_bridge as bridge

    assert "PluginInfo" not in bridge.__all__
    assert not hasattr(bridge, "PluginInfo")


# ---------------------------------------------------------------------------
# is_logged_in / run_login_blocking
# ---------------------------------------------------------------------------
class TestAuthHelpers:
    def test_is_logged_in_true(self) -> None:
        with patch("hve.auth.is_authenticated", return_value=True):
            assert CopilotCliBridge.is_logged_in() is True

    def test_is_logged_in_swallows_exception(self) -> None:
        with patch("hve.auth.is_authenticated", side_effect=RuntimeError("boom")):
            assert CopilotCliBridge.is_logged_in() is False

    def test_run_login_returns_minus_one_when_binary_missing(self) -> None:
        with patch.object(CopilotCliBridge, "find_binary", return_value=None):
            assert CopilotCliBridge.run_login_blocking() == -1

    def test_run_login_returns_minus_two_on_timeout(self) -> None:
        def _raise(*_a, **_kw):
            raise subprocess.TimeoutExpired(cmd="copilot", timeout=1)
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("hve.auth.run_login", side_effect=_raise):
            assert CopilotCliBridge.run_login_blocking(timeout=1.0) == -2

    def test_run_login_returns_subprocess_rc(self) -> None:
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("hve.auth.run_login", return_value=0):
            assert CopilotCliBridge.run_login_blocking() == 0
