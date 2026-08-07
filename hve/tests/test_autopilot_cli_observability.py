"""FR-RTO-02 / FR-RTO-05: CLI Autopilot 親が子の観測イベントを集約する。

RED 先行。子 stdout の取り込みと集約は本テスト作成時点で未実装。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hve import runtime_observability as rto
from hve.autopilot.cli_runner import CliAutopilotRunner
from hve.autopilot.plan_model import AppChain, AutopilotPlan


def _plan() -> AutopilotPlan:
    return AutopilotPlan(
        catalog_path=Path("docs/catalog/app-arch-catalog.md"),
        catalog_exists=True,
        requires_aas=False,
        app_chains=[
            AppChain(app_id="APP-1", architecture="web", workflows=["aad-web"]),
            AppChain(app_id="APP-2", architecture="web", workflows=["aad-web"]),
        ],
        max_parallel=2,
    )


def _runner() -> CliAutopilotRunner:
    return CliAutopilotRunner(_plan(), popen_factory=lambda argv: None)


class TestChildEnvironment:
    """FR-RTO-02: 子プロセスにだけ stats 配信を許可する。"""

    def test_child_env_sets_stream_marker(self) -> None:
        env = _runner()._child_env()
        assert env[rto.STATS_STREAM_ENV] == "1"

    def test_child_env_inherits_parent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HVE_WORK_ROOT", "/tmp/x")
        assert _runner()._child_env()["HVE_WORK_ROOT"] == "/tmp/x"


class TestChildLineConsumption:
    """FR-RTO-05: instance 単位で集計し、通常ログはそのまま流す。"""

    def test_stats_line_is_aggregated_per_instance(self) -> None:
        runner = _runner()
        ctx = rto.RuntimeContext(instance_id="aad-web#APP-1")
        line = rto.format_stats_line(rto.build_event("assistant_usage", "1", ctx, input=10, output=2))

        runner._consume_child_line("APP-1", "aad-web", line)

        metrics = runner.runtime_metrics.for_instance("aad-web#APP-1")
        assert metrics.input_tokens_total == 10
        assert metrics.output_tokens_total == 2

    def test_instances_are_isolated(self) -> None:
        runner = _runner()
        ctx = rto.RuntimeContext(instance_id="aad-web#APP-1")
        runner._consume_child_line(
            "APP-1", "aad-web", rto.format_stats_line(rto.build_event("assistant_usage", "1", ctx, input=6))
        )

        assert runner.runtime_metrics.for_instance("aad-web#APP-2").input_tokens_total == 0
        assert runner.runtime_metrics.totals().input_tokens_total == 6

    def test_stats_line_is_not_echoed(self) -> None:
        echoed: list = []
        runner = CliAutopilotRunner(_plan(), popen_factory=lambda argv: None, echo=echoed.append)
        ctx = rto.RuntimeContext(instance_id="aad-web#APP-1")
        runner._consume_child_line(
            "APP-1", "aad-web", rto.format_stats_line(rto.build_event("step_status", "1", ctx, status="running"))
        )

        assert echoed == []

    def test_normal_line_is_echoed_with_app_prefix(self) -> None:
        echoed: list = []
        runner = CliAutopilotRunner(_plan(), popen_factory=lambda argv: None, echo=echoed.append)
        runner._consume_child_line("APP-1", "aad-web", "通常のログ")

        assert echoed == ["[APP-1][aad-web] 通常のログ"]


class TestDefaultPopen:
    """親が集約するため子 stdout をパイプで受ける。"""

    def test_default_popen_uses_pipe_and_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_popen(argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            return object()

        monkeypatch.setattr(subprocess, "Popen", fake_popen)
        CliAutopilotRunner(_plan())._default_popen(["orchestrate", "--workflow", "aad-web"])

        assert captured["kwargs"]["stdout"] is subprocess.PIPE
        assert captured["kwargs"]["stderr"] is subprocess.STDOUT
        assert captured["kwargs"]["env"][rto.STATS_STREAM_ENV] == "1"


class TestSummary:
    def test_runtime_summary_uses_core_formatter(self) -> None:
        runner = _runner()
        ctx = rto.RuntimeContext(instance_id="aad-web#APP-1")
        runner._consume_child_line(
            "APP-1", "aad-web", rto.format_stats_line(rto.build_event("assistant_usage", "1", ctx, input=3))
        )

        assert runner.runtime_summary() == rto.format_runtime_summary(runner.runtime_metrics.totals())
