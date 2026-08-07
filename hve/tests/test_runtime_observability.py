"""FR-RTO-01 / NFR-RTO-02: 実行時観測イベント契約の単一実装と後方互換。

RED 先行。`hve/runtime_observability.py` は本テスト作成時点で未実装。
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta

import pytest

from hve import runtime_observability as rto


class TestEnvelope:
    """FR-RTO-01: 既存キーを維持したまま envelope を付与する。"""

    def _ctx(self):
        return rto.RuntimeContext(
            run_id="run-1",
            workflow_id="asdw-web",
            instance_id="asdw-web#APP-009",
            pid=4242,
        )

    def test_envelope_keys_are_present(self) -> None:
        payload = rto.build_event("step_status", step_id="2.1", context=self._ctx(), status="running")
        for key in (
            "schema_version",
            "ts",
            "seq",
            "pid",
            "run_id",
            "workflow_id",
            "instance_id",
            "kind",
            "step",
        ):
            assert key in payload, f"missing envelope key: {key}"
        assert payload["schema_version"] == rto.SCHEMA_VERSION
        assert payload["pid"] == 4242

    def test_existing_kind_and_step_keys_are_preserved(self) -> None:
        payload = rto.build_event("tool_invoked", step_id="1.2", context=self._ctx(), tool_name="view")
        assert payload["kind"] == "tool_invoked"
        assert payload["step"] == "1.2"
        assert payload["tool_name"] == "view"

    def test_blank_step_id_keeps_empty_string(self) -> None:
        # 既存 Console.stats_event は step 未指定時に空文字を入れる。GUI 受信側の互換のため変えない。
        payload = rto.build_event("permission_count", context=self._ctx(), count=1)
        assert payload["step"] == ""

    def test_ts_is_utc_iso8601(self) -> None:
        payload = rto.build_event("step_status", step_id="1", context=self._ctx(), status="running")
        parsed = datetime.fromisoformat(payload["ts"])
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)

    def test_none_fields_are_dropped(self) -> None:
        payload = rto.build_event("assistant_usage", step_id="1", context=self._ctx(), reasoning=None)
        assert "reasoning" not in payload

    def test_seq_is_monotonic_within_context(self) -> None:
        ctx = self._ctx()
        first = rto.build_event("step_status", step_id="1", context=ctx, status="running")
        second = rto.build_event("step_status", step_id="1", context=ctx, status="done")
        assert second["seq"] > first["seq"]


class TestInstanceId:
    """FR-RTO-01: instance_id は workflow_id、APP 並列時は workflow_id#app_id。"""

    def test_without_app_id(self) -> None:
        assert rto.make_instance_id("aad-web") == "aad-web"

    def test_with_app_id(self) -> None:
        assert rto.make_instance_id("aad-web", "APP-009") == "aad-web#APP-009"

    def test_blank_app_id_is_ignored(self) -> None:
        assert rto.make_instance_id("aad-web", "  ") == "aad-web"


class TestWireFormat:
    """FR-RTO-01: `[hve:stats]` 行形式を維持する。"""

    def test_format_uses_existing_prefix(self) -> None:
        line = rto.format_stats_line({"kind": "step_status", "step": "1"})
        assert line.startswith("[hve:stats] ")
        assert json.loads(line[len("[hve:stats] "):])["kind"] == "step_status"

    def test_roundtrip(self) -> None:
        ctx = rto.RuntimeContext(run_id="r", workflow_id="w", instance_id="w", pid=1)
        payload = rto.build_event("skill_invoked", step_id="3", context=ctx, name="code-query")
        parsed = rto.parse_stats_line(rto.format_stats_line(payload))
        assert parsed is not None
        assert parsed["name"] == "code-query"
        assert parsed["kind"] == "skill_invoked"

    def test_legacy_line_without_envelope_parses(self) -> None:
        parsed = rto.parse_stats_line('[hve:stats] {"kind":"step_status","step":"2.2","status":"done"}')
        assert parsed is not None
        assert parsed["kind"] == "step_status"
        assert parsed["step"] == "2.2"

    def test_timestamp_prefixed_line_parses(self) -> None:
        parsed = rto.parse_stats_line('[13:49:27]   [hve:stats] {"kind":"permission_count","count":3}')
        assert parsed is not None
        assert parsed["count"] == 3

    @pytest.mark.parametrize(
        "line",
        ["plain log line", "[other] {}", "about [hve:stats] format", "[hve:stats] not-json"],
    )
    def test_non_matching_lines_return_none(self, line: str) -> None:
        assert rto.parse_stats_line(line) is None


class TestReducerUnknownKind:
    """FR-RTO-01: 未知 kind は無言で捨てず件数を計上する。"""

    def test_unknown_kind_is_counted(self) -> None:
        metrics = rto.RuntimeMetrics()
        metrics.apply({"kind": "totally_unknown_kind", "step": "1"})
        assert metrics.unknown_kind_count == 1
        assert "totally_unknown_kind" in metrics.unknown_kinds

    def test_known_kind_is_not_counted_as_unknown(self) -> None:
        metrics = rto.RuntimeMetrics()
        metrics.apply({"kind": "step_status", "step": "1", "status": "running"})
        assert metrics.unknown_kind_count == 0


class TestBackwardCompatibleKinds:
    """NFR-RTO-02: GUI / Autopilot が依存する既存 kind を削らない。"""

    def test_known_kinds_cover_existing_producers(self) -> None:
        required = {
            "step_status",
            "fanout_init",
            "tool_invoked",
            "tool_result",
            "skill_invoked",
            "file_io",
            "assistant_usage",
            "assistant_ttft",
            "usage_credit",
            "quota_snapshot",
            "session_usage_detail",
            "compaction_complete",
            "permission_count",
            "premium_requests",
            "model_call_failure",
        }
        assert required <= set(rto.KNOWN_KINDS)


class TestNoNewConfigSurface:
    """NFR-RTO-02: 新規 CLI オプション / SDKConfig フィールドを追加しない。"""

    def test_sdkconfig_has_no_observability_field(self) -> None:
        from hve.config import SDKConfig

        offending = [
            f.name
            for f in dataclasses.fields(SDKConfig)
            if "observab" in f.name or "dashboard" in f.name or "rto" in f.name
        ]
        assert offending == []

    def test_module_defines_single_stream_env_marker(self) -> None:
        assert rto.STATS_STREAM_ENV == "HVE_STATS_STREAM"
