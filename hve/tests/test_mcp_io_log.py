"""FR-MCPLOG-01 / 02 / 03: MCP 通信ログの記録・ファイル分離・マスク。

RED 先行。`hve/mcp_io_log.py` は本テスト作成時点で未実装。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from hve import mcp_io_log as mio


@pytest.fixture(autouse=True)
def _no_child_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """既定は「親プロセス」= pid サフィックスなしの状態で検証する。"""
    monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
    monkeypatch.delenv("HVE_STATS_STREAM", raising=False)


def _logger(tmp_path: Path, **kwargs) -> "mio.McpIoLogger":
    return mio.McpIoLogger(tmp_path, **kwargs)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestMcpIoLoggerFileLayout:
    """FR-MCPLOG-02: 出力先・ファイル名・分離。"""

    def test_one_file_per_server_directly_under_work_root(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        log.record_tool_request("azure", "list_groups", tool_call_id="c1", arguments={"a": 1})
        log.record_tool_request("_hve_workiq", "ask", tool_call_id="c2", arguments={"q": "x"})
        log.close()

        assert (tmp_path / "mcp-azure.log").is_file()
        assert (tmp_path / "mcp-_hve_workiq.log").is_file()

    def test_path_for_returns_the_open_file(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        log.record_tool_request("azure", "t", tool_call_id="c1")
        assert log.path_for("azure") == tmp_path / "mcp-azure.log"
        log.close()

    def test_server_name_is_filesystem_sanitized(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        log.record_tool_request("acme/mcp server:1", "t", tool_call_id="c1")
        log.close()

        names = sorted(p.name for p in tmp_path.glob("mcp-*.log"))
        assert names == ["mcp-acme_mcp_server_1.log"]

    def test_no_pid_suffix_for_parent_process(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        log.record_tool_request("azure", "t", tool_call_id="c1")
        log.close()
        assert log.path_for("azure").name == "mcp-azure.log"

    @pytest.mark.parametrize(
        "env_name,env_value",
        [
            ("HVE_GUI_SESSION_ID", "20260825T101010-abc"),
            ("HVE_STATS_STREAM", "1"),
            ("HVE_STATS_STREAM", "true"),
            ("HVE_STATS_STREAM", "True"),
        ],
    )
    def test_pid_suffix_for_child_process(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env_name: str, env_value: str
    ) -> None:
        monkeypatch.setenv(env_name, env_value)
        log = _logger(tmp_path)
        log.record_tool_request("azure", "t", tool_call_id="c1")
        log.close()
        assert log.path_for("azure").name == f"mcp-azure-{log.pid}.log"

    def test_falsy_stats_stream_keeps_plain_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HVE_STATS_STREAM", "0")
        log = _logger(tmp_path)
        log.record_tool_request("azure", "t", tool_call_id="c1")
        log.close()
        assert log.path_for("azure").name == "mcp-azure.log"


class TestMcpIoLoggerDisabled:
    """FR-MCPLOG-02: 無効化条件。"""

    def test_disabled_when_work_root_is_none(self) -> None:
        log = mio.McpIoLogger(None)
        assert log.enabled is False
        assert log.record_tool_request("azure", "t", tool_call_id="c1") is False
        assert log.path_for("azure") is None
        log.close()

    def test_disabled_for_dry_run(self, tmp_path: Path) -> None:
        log = _logger(tmp_path, dry_run=True)
        assert log.enabled is False
        assert log.record_tool_request("azure", "t", tool_call_id="c1") is False
        assert list(tmp_path.glob("mcp-*.log")) == []
        log.close()

    def test_from_env_is_disabled_without_work_root(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HVE_WORK_ROOT", raising=False)
        log = mio.McpIoLogger.from_env()
        assert log.enabled is False
        log.close()

    def test_from_env_uses_work_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path))
        log = mio.McpIoLogger.from_env()
        assert log.enabled is True
        log.record_tool_request("azure", "t", tool_call_id="c1")
        log.close()
        assert (tmp_path / "mcp-azure.log").is_file()

    def test_write_failure_does_not_raise(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        log.record_tool_request("azure", "t", tool_call_id="c1")

        class _Boom:
            def write(self, *_args, **_kwargs):
                raise OSError("disk full")

            def flush(self) -> None:
                pass

            def close(self) -> None:
                pass

        # `_io.TextIOWrapper.write` は読み取り専用属性のため、ハンドルごと差し替える。
        log._handles[mio.sanitize_server_name("azure")] = _Boom()  # type: ignore[attr-defined]
        assert log.record_tool_request("azure", "t", tool_call_id="c2") is False
        log.close()


class TestMcpIoLoggerRecords:
    """FR-MCPLOG-01: 各レコード種別が全文で残る。"""

    def test_request_body_keeps_full_arguments(self, tmp_path: Path) -> None:
        long_query = "あ" * 5000
        log = _logger(tmp_path)
        log.record_tool_request(
            "_hve_workiq", "ask", tool_call_id="c1", step_id="1.2",
            arguments={"query": long_query},
        )
        log.close()

        text = _read(tmp_path / "mcp-_hve_workiq.log")
        assert long_query in text
        assert "…" not in text
        header = text.splitlines()[0]
        assert header.startswith("=== ")
        assert "| mcp_request |" in header
        assert "server=_hve_workiq" in header
        assert "tool=ask" in header
        assert "call_id=c1" in header
        assert "step=1.2" in header

    def test_request_body_is_pretty_json_for_mappings(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        log.record_tool_request("azure", "t", tool_call_id="c1", arguments={"k": "値"})
        log.close()

        body = "\n".join(_read(tmp_path / "mcp-azure.log").splitlines()[1:])
        assert json.loads(body) == {"k": "値"}
        assert "\\u" not in body

    def test_response_body_keeps_full_content(self, tmp_path: Path) -> None:
        content = "行\n" * 3000
        log = _logger(tmp_path)
        log.record_tool_request("_hve_workiq", "ask", tool_call_id="c1")
        log.record_tool_response(tool_call_id="c1", success=True, content=content)
        log.close()

        text = _read(tmp_path / "mcp-_hve_workiq.log")
        assert content.strip() in text
        assert "| mcp_response |" in text
        assert "success=true" in text

    def test_response_failure_records_error(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        log.record_tool_request("azure", "t", tool_call_id="c1")
        log.record_tool_response(tool_call_id="c1", success=False, error="timeout after 300s")
        log.close()

        text = _read(tmp_path / "mcp-azure.log")
        assert "success=false" in text
        assert "timeout after 300s" in text

    def test_server_status_record(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        log.record_server_status(
            "workiq-preview", status="connected",
            plugin_name="workiq-preview", transport="stdio", source="plugin",
        )
        log.close()

        header = _read(tmp_path / "mcp-workiq-preview.log").splitlines()[0]
        assert "| mcp_server_status |" in header
        assert "status=connected" in header
        assert "plugin=workiq-preview" in header
        assert "transport=stdio" in header
        assert "source=plugin" in header

    def test_session_prompt_and_response(self, tmp_path: Path) -> None:
        prompt = "Work IQ へ送るプロンプト\n" * 500
        log = _logger(tmp_path)
        log.record_session_prompt("_hve_workiq", "Work IQ プロンプト [Q3]", prompt)
        log.record_session_response("_hve_workiq", "Work IQ 応答 [Q3]", "STATUS: FOUND")
        log.close()

        text = _read(tmp_path / "mcp-_hve_workiq.log")
        assert prompt.strip() in text
        assert "| session_prompt |" in text
        assert "label=Work IQ プロンプト [Q3]" in text
        assert "| session_response |" in text
        assert "STATUS: FOUND" in text

    def test_empty_payloads_are_not_recorded(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        assert log.record_session_prompt("_hve_workiq", "L", "") is False
        assert log.record_session_response("_hve_workiq", "L", "   ") is False
        log.close()
        assert list(tmp_path.glob("mcp-*.log")) == []


class TestMcpIoLoggerCorrelation:
    """FR-MCPLOG-01: `tool_call_id` 相関でのみ完了イベントを帰属させる。"""

    def test_response_is_routed_to_the_request_server(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        log.record_tool_request("azure", "list_groups", tool_call_id="c1", step_id="1")
        log.record_tool_response(tool_call_id="c1", success=True, content="ok", step_id="1")
        log.close()

        assert "mcp_response" in _read(tmp_path / "mcp-azure.log")

    def test_unknown_call_id_is_dropped(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        assert log.record_tool_response(tool_call_id="nope", success=True, content="x") is False
        log.close()
        assert list(tmp_path.glob("mcp-*.log")) == []

    def test_correlation_is_scoped_by_step(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        log.record_tool_request("azure", "t", tool_call_id="c1", step_id="1")
        assert log.record_tool_response(tool_call_id="c1", success=True, step_id="2") is False
        assert log.record_tool_response(tool_call_id="c1", success=True, step_id="1") is True
        log.close()

    def test_correlation_entry_is_consumed_once(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        log.record_tool_request("azure", "t", tool_call_id="c1")
        assert log.record_tool_response(tool_call_id="c1", success=True) is True
        assert log.record_tool_response(tool_call_id="c1", success=True) is False
        log.close()


class TestMcpIoLoggerEncoding:
    """FR-MCPLOG-02: UTF-8 / LF / BOM なし。"""

    def test_lf_only_and_no_bom(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        log.record_session_prompt("_hve_workiq", "L", "1 行目\r\n2 行目")
        log.close()

        raw = (tmp_path / "mcp-_hve_workiq.log").read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"\r\n" not in raw
        assert "1 行目" in raw.decode("utf-8")

    def test_header_stays_on_one_line_for_multiline_metadata(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        log.record_server_status(
            "azure", status="failed", plugin_name="bad\nname", transport="stdio"
        )
        log.close()

        lines = _read(tmp_path / "mcp-azure.log").splitlines()
        assert len([line for line in lines if line.startswith("=== ")]) == 1
        assert "plugin=bad name" in lines[0]


class TestMcpIoLoggerCap:
    """FR-MCPLOG-02: 上限到達で停止し、1 回だけ警告する。"""

    def test_stops_and_warns_once_per_file(self, tmp_path: Path) -> None:
        warnings: list = []
        # 1 レコードはヘッダ（数十バイト）+ body 400 バイト弱。
        # 1 件目は確実に収まり、2 件目で確実に超える値を選ぶ。
        log = _logger(tmp_path, max_bytes=700, warn=warnings.append)
        payload = "x" * 400
        assert log.record_session_prompt("azure", "L", payload) is True
        assert log.record_session_prompt("azure", "L", payload) is False
        assert log.record_session_prompt("azure", "L", payload) is False
        log.close()

        assert len(warnings) == 1
        assert "mcp-azure.log" in warnings[0]

    def test_cap_is_per_server(self, tmp_path: Path) -> None:
        warnings: list = []
        log = _logger(tmp_path, max_bytes=700, warn=warnings.append)
        payload = "x" * 400
        log.record_session_prompt("azure", "L", payload)
        log.record_session_prompt("azure", "L", payload)
        assert log.record_session_prompt("_hve_workiq", "L", payload) is True
        log.close()


class TestMcpIoLoggerSanitize:
    """FR-MCPLOG-03: 認証情報のマスクを既存実装へ委譲する。"""

    def test_masks_bearer_token_and_jwt(self, tmp_path: Path) -> None:
        secret = (
            "Authorization: Bearer abc.def-ghi\n"
            "api_key=SUPERSECRETVALUE\n"
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2ln"
        )
        log = _logger(tmp_path)
        log.record_session_response("_hve_workiq", "L", secret)
        log.close()

        text = _read(tmp_path / "mcp-_hve_workiq.log")
        assert "abc.def-ghi" not in text
        assert "SUPERSECRETVALUE" not in text
        assert "eyJhbGciOiJIUzI1NiJ9" not in text
        assert "[REDACTED]" in text

    def test_sanitizer_is_the_shared_workiq_helper(self) -> None:
        from hve import workiq

        assert mio._sanitize is workiq._sanitize_diagnostic_text


class TestMcpIoLoggerConcurrency:
    """同一プロセス内の追記を直列化する。"""

    def test_parallel_appends_do_not_interleave_records(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)

        def worker(n: int) -> None:
            for i in range(30):
                log.record_session_prompt("azure", f"L{n}", f"body-{n}-{i}\nsecond line")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        log.close()

        lines = _read(tmp_path / "mcp-azure.log").splitlines()
        headers = [line for line in lines if line.startswith("=== ")]
        assert len(headers) == 120
        assert len([line for line in lines if line == "second line"]) == 120


class TestAttachMcpIoEventLogger:
    """FR-MCPLOG-01: SDK セッションへの結線ヘルパー。"""

    @staticmethod
    def _event(etype: str, **fields):
        return SimpleNamespace(
            type=SimpleNamespace(value=etype), data=SimpleNamespace(**fields)
        )

    def test_records_mcp_tool_round_trip(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        handlers: list = []
        session = SimpleNamespace(on=handlers.append)

        mio.attach_mcp_io_event_logger(session, log, step_id="orchestrator")
        assert len(handlers) == 1
        handler = handlers[0]

        handler(
            self._event(
                "tool.execution_start",
                tool_call_id="c1",
                tool_name="ask",
                mcp_tool_name="ask",
                mcp_server_name="_hve_workiq",
                arguments={"query": "hello"},
            )
        )
        handler(
            self._event(
                "tool.execution_complete",
                tool_call_id="c1",
                success=True,
                result=SimpleNamespace(content="answer"),
            )
        )
        log.close()

        text = _read(tmp_path / "mcp-_hve_workiq.log")
        assert "hello" in text
        assert "answer" in text

    def test_ignores_builtin_tools_without_mcp_server(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        handlers: list = []
        mio.attach_mcp_io_event_logger(SimpleNamespace(on=handlers.append), log)
        handlers[0](
            self._event(
                "tool.execution_start", tool_call_id="c1", tool_name="view",
                arguments={"path": "a.md"},
            )
        )
        log.close()
        assert list(tmp_path.glob("mcp-*.log")) == []

    def test_records_server_status_events(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        handlers: list = []
        mio.attach_mcp_io_event_logger(SimpleNamespace(on=handlers.append), log)
        handlers[0](
            self._event(
                "session.mcp_servers_loaded",
                servers=[
                    SimpleNamespace(
                        name="_hve_workiq",
                        status=SimpleNamespace(value="connected"),
                        error=None,
                        plugin_name=None,
                        transport=SimpleNamespace(value="stdio"),
                        source=SimpleNamespace(value="user"),
                    )
                ],
            )
        )
        log.close()
        assert "status=connected" in _read(tmp_path / "mcp-_hve_workiq.log")

    def test_no_op_when_logger_is_none_or_session_has_no_on(self, tmp_path: Path) -> None:
        mio.attach_mcp_io_event_logger(SimpleNamespace(on=lambda _h: None), None)
        log = _logger(tmp_path)
        mio.attach_mcp_io_event_logger(SimpleNamespace(), log)
        log.close()

    def test_handler_failure_is_swallowed(self, tmp_path: Path) -> None:
        log = _logger(tmp_path)
        handlers: list = []
        mio.attach_mcp_io_event_logger(SimpleNamespace(on=handlers.append), log)
        handlers[0](object())
        log.close()
