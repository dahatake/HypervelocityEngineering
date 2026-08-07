"""FR-RTO-02: 収集 / 保存 / 子プロセス配信 / 人間向け表示の分離。

RED 先行。Console 側の runtime observability 配線は本テスト作成時点で未実装。
"""

from __future__ import annotations

import pytest

from hve import runtime_observability as rto
from hve.console import Console


class _FakeWorkbench:
    def __init__(self) -> None:
        self.body_lines: list = []

    def append_body(self, line: str) -> None:
        self.body_lines.append(line)

    def set_step_status(self, *_args, **_kwargs) -> None:
        return None

    def set_context(self, *_args, **_kwargs) -> None:
        return None


def _clear_stream_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
    monkeypatch.delenv(rto.STATS_STREAM_ENV, raising=False)


class TestChildDelivery:
    """FR-RTO-02: stdout への `[hve:stats]` は子プロセスに限る。"""

    def test_plain_cli_does_not_stream_stats(self, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_stream_env(monkeypatch)
        con = Console(verbose=False)
        con.stats_event("step_status", step_id="1", status="running")

        assert "[hve:stats]" not in capsys.readouterr().out

    def test_gui_child_streams_stats(self, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_stream_env(monkeypatch)
        monkeypatch.setenv("HVE_GUI_SESSION_ID", "gui-1")
        con = Console(verbose=False)
        con.stats_event("step_status", step_id="1", status="running")

        out = capsys.readouterr().out
        assert "[hve:stats]" in out
        streamed = rto.parse_stats_line(out.strip().splitlines()[-1])
        assert streamed is not None
        assert streamed["status"] == "running"

    def test_explicit_stream_marker_streams_stats(self, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_stream_env(monkeypatch)
        monkeypatch.setenv(rto.STATS_STREAM_ENV, "1")
        con = Console(verbose=False)
        con.stats_event("tool_invoked", step_id="1", tool_name="view")

        assert "[hve:stats]" in capsys.readouterr().out

    def test_streamed_payload_carries_envelope(self, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_stream_env(monkeypatch)
        monkeypatch.setenv(rto.STATS_STREAM_ENV, "1")
        con = Console(verbose=False)
        con.set_run_id("run-9")
        con.set_runtime_identity(workflow_id="asdw-web", instance_id="asdw-web#APP-009")
        con.stats_event("step_status", step_id="2.1", status="running")

        payload = rto.parse_stats_line(capsys.readouterr().out.strip().splitlines()[-1])
        assert payload is not None
        assert payload["run_id"] == "run-9"
        assert payload["workflow_id"] == "asdw-web"
        assert payload["instance_id"] == "asdw-web#APP-009"
        assert payload["schema_version"] == rto.SCHEMA_VERSION


class TestWorkbenchBodyIsolation:
    """FR-RTO-02: CUI Workbench 本文へ stats 行を混入させない。"""

    def test_stats_line_not_appended_to_workbench_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_stream_env(monkeypatch)
        con = Console(verbose=False)
        workbench = _FakeWorkbench()
        con.attach_workbench(workbench)
        con.stats_event("step_status", step_id="1", status="running")

        assert workbench.body_lines == []


class TestCollectionAlwaysOn:
    """FR-RTO-02: quiet / final_only でも収集を継続する。"""

    @pytest.mark.parametrize("kwargs", [{"quiet": True}, {"final_only": True}])
    def test_metrics_are_collected(self, kwargs: dict, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_stream_env(monkeypatch)
        con = Console(**kwargs)
        con.stats_event("assistant_usage", step_id="1", input=10, output=2)

        totals = con.runtime_metrics().totals()
        assert totals.input_tokens_total == 10
        assert totals.output_tokens_total == 2

    @pytest.mark.parametrize("kwargs", [{"quiet": True}, {"final_only": True}])
    def test_step_lifecycle_is_collected(self, kwargs: dict, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_stream_env(monkeypatch)
        con = Console(**kwargs)
        con.step_start("1.1", "テスト")
        totals_running = con.runtime_metrics().totals()
        assert totals_running.step_status.get("1.1") == "running"

        con.step_end("1.1", "success", elapsed=1.0)
        assert con.runtime_metrics().totals().step_status.get("1.1") == "done"

    def test_skill_invocation_is_collected_in_quiet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_stream_env(monkeypatch)
        con = Console(quiet=True)
        con.step_start("1", "t")
        con.skill_invoked("1", "code-query")

        assert con.runtime_metrics().totals().current_skill_counts() == {"code-query": 1}


class TestRecorderWiring:
    """FR-RTO-03 / FR-RTO-04: 記録器へ sanitize 済み payload を渡す。"""

    def test_recorder_receives_sanitized_payload(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_stream_env(monkeypatch)
        con = Console(verbose=False)
        recorder = rto.RuntimeEventRecorder(tmp_path, repo_root=tmp_path)
        con.attach_event_recorder(recorder)
        con.stats_event("tool_invoked", step_id="1", tool_name="bash", arguments={"c": "secret"})
        recorder.close()

        stored = rto.read_events(tmp_path)
        assert len(stored) == 1
        assert stored[0]["tool_name"] == "bash"
        assert "arguments" not in stored[0]

    def test_detach_stops_recording(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_stream_env(monkeypatch)
        con = Console(verbose=False)
        recorder = rto.RuntimeEventRecorder(tmp_path, repo_root=tmp_path)
        con.attach_event_recorder(recorder)
        con.detach_event_recorder()
        con.stats_event("tool_invoked", step_id="1", tool_name="view")
        recorder.close()

        assert rto.read_events(tmp_path) == []
