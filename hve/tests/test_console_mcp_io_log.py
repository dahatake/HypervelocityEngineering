"""FR-MCPLOG-01 / 02: Console から MCP 通信ログへの結線。

RED 先行。`Console.attach_mcp_io_logger` / `mcp_tool_request` / `mcp_tool_response`
/ `mcp_server_status` は本テスト作成時点で未実装。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve import mcp_io_log as mio
from hve.console import Console


@pytest.fixture(autouse=True)
def _parent_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
    monkeypatch.delenv("HVE_STATS_STREAM", raising=False)


def _console(verbosity: int = 2) -> Console:
    return Console(verbosity=verbosity, no_color=True)


def _attached(tmp_path: Path, verbosity: int = 2):
    console = _console(verbosity)
    logger = mio.McpIoLogger(tmp_path)
    console.attach_mcp_io_logger(logger)
    return console, logger


def _read(tmp_path: Path, server: str) -> str:
    return (tmp_path / f"mcp-{server}.log").read_text(encoding="utf-8")


class TestConsoleLoggerAttachment:
    def test_methods_are_no_op_without_logger(self, tmp_path: Path) -> None:
        console = _console()
        console.mcp_tool_request("azure", "t", tool_call_id="c1")
        console.mcp_tool_response(tool_call_id="c1", success=True)
        console.mcp_server_status("azure", status="connected")
        console.workiq_prompt("prompt body")
        assert list(tmp_path.glob("mcp-*.log")) == []

    def test_detach_stops_recording(self, tmp_path: Path) -> None:
        console, logger = _attached(tmp_path)
        console.detach_mcp_io_logger()
        console.mcp_tool_request("azure", "t", tool_call_id="c1")
        logger.close()
        assert list(tmp_path.glob("mcp-*.log")) == []


class TestConsoleToolRecords:
    def test_tool_request_and_response_round_trip(self, tmp_path: Path) -> None:
        console, logger = _attached(tmp_path)
        console.mcp_tool_request(
            "azure", "list_groups", tool_call_id="c1", step_id="1.2",
            arguments={"subscription": "sub-1"},
        )
        console.mcp_tool_response(
            tool_call_id="c1", success=True, content="OK", step_id="1.2"
        )
        logger.close()

        text = _read(tmp_path, "azure")
        assert "sub-1" in text
        assert "| mcp_response |" in text
        assert "OK" in text

    def test_server_status_is_recorded(self, tmp_path: Path) -> None:
        console, logger = _attached(tmp_path)
        console.mcp_server_status(
            "microsoft-learn", status="connected", transport="http", source="workspace"
        )
        logger.close()
        assert "status=connected" in _read(tmp_path, "microsoft-learn")


class TestConsoleWorkIQPersistence:
    """FR-MCPLOG-01: 表示の切り詰め・抑止と記録を分離する。"""

    def test_prompt_is_recorded_in_full_beyond_display_truncation(
        self, tmp_path: Path
    ) -> None:
        prompt = "あ" * 20_000
        console, logger = _attached(tmp_path, verbosity=2)
        console.workiq_prompt(prompt, label="Work IQ プロンプト [Q1]")
        logger.close()

        text = _read(tmp_path, "_hve_workiq")
        assert prompt in text
        assert "label=Work IQ プロンプト [Q1]" in text

    def test_response_is_recorded_in_full(self, tmp_path: Path) -> None:
        response = "い" * 20_000
        console, logger = _attached(tmp_path)
        console.workiq_response(response, label="Work IQ 応答 [Q1]")
        logger.close()
        assert response in _read(tmp_path, "_hve_workiq")

    @pytest.mark.parametrize("verbosity", [0, 1, 2, 3])
    def test_recorded_regardless_of_verbosity(
        self, tmp_path: Path, verbosity: int
    ) -> None:
        console, logger = _attached(tmp_path, verbosity=verbosity)
        console.workiq_prompt("本文", label="L")
        console.workiq_response("応答", label="L")
        logger.close()

        text = _read(tmp_path, "_hve_workiq")
        assert "本文" in text
        assert "応答" in text

    def test_final_only_still_records(self, tmp_path: Path) -> None:
        console = Console(verbosity=2, no_color=True, final_only=True)
        logger = mio.McpIoLogger(tmp_path)
        console.attach_mcp_io_logger(logger)
        console.workiq_prompt("本文", label="L")
        logger.close()
        assert "本文" in _read(tmp_path, "_hve_workiq")

    def test_uses_the_shared_workiq_server_name(self, tmp_path: Path) -> None:
        from hve import workiq

        console, logger = _attached(tmp_path)
        console.workiq_prompt("本文", label="L")
        logger.close()
        expected = tmp_path / f"mcp-{workiq.WORKIQ_MCP_SERVER_NAME}.log"
        assert expected.is_file()
