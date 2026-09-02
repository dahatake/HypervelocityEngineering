"""FR-RTO-02 / FR-RTO-05: Workbench 無効時の CLI Dashboard 表示。

RED 先行。StatusLine への配線と最終サマリーは本テスト作成時点で未実装。
"""

from __future__ import annotations

import io

import pytest

from hve import orchestrator as orch
from hve import runtime_observability as rto
from hve.config import SDKConfig
from hve.console import Console
from hve.statusline import StatusLineState, format_status_line


def _registry() -> rto.RuntimeMetricsRegistry:
    registry = rto.RuntimeMetricsRegistry()
    registry.apply({"kind": "session_usage_detail", "step": "1", "current": 900, "limit": 10000, "msgs": 4})
    registry.apply({"kind": "assistant_usage", "step": "1", "input": 200, "output": 40})
    registry.apply({"kind": "usage_credit", "step": "1", "api_call_id": "a", "nano_aiu": 2_500_000_000})
    return registry


class TestStatusLineDecision:
    """FR-RTO-02: quiet / final_only では追加表示をしない。"""

    def test_disabled_for_quiet(self) -> None:
        assert orch._should_use_statusline(Console(quiet=True), SDKConfig(quiet=True)) is False

    def test_disabled_for_final_only(self) -> None:
        config = SDKConfig()
        config.final_only = True
        assert orch._should_use_statusline(Console(final_only=True), config) is False

    def test_disabled_when_pricing_statusline_option_is_off(self) -> None:
        config = SDKConfig()
        config.pricing_statusline_enabled = False
        config.no_workbench = True
        assert orch._should_use_statusline(Console(verbose=False), config) is False

    def test_disabled_when_workbench_is_the_main_surface(self) -> None:
        class _Con:
            workbench_enabled = True
            quiet = False
            final_only = False

        config = SDKConfig()
        config.no_workbench = False
        assert orch._should_use_statusline(_Con(), config) is False

    def test_enabled_when_workbench_is_off(self) -> None:
        class _Con:
            workbench_enabled = True
            quiet = False
            final_only = False

        config = SDKConfig()
        config.no_workbench = True
        assert orch._should_use_statusline(_Con(), config) is True


class TestStatusLineState:
    """FR-RTO-05: 同一集計から StatusLine 用の状態を作る。"""

    def test_build_from_metrics(self) -> None:
        state = orch._build_statusline_state(_registry().totals(), workflow_started_at=1.0)

        assert state.context_current == 900
        assert state.context_limit == 10000
        assert state.tokens_in == 200
        assert state.tokens_out == 40
        assert state.aiu_total == 2.5
        assert state.workflow_started_at == 1.0

    def test_render_includes_new_segments(self) -> None:
        line = format_status_line(
            StatusLineState(tokens_in=200, tokens_out=40, aiu_total=2.5, premium_requests_total=3),
            now=0.0,
        )
        assert "tok 200/40" in line
        assert "2.5000 AIU" in line
        assert "reqs 3" in line

    def test_render_omits_credit_when_unavailable(self) -> None:
        line = format_status_line(StatusLineState(tokens_in=1, tokens_out=1), now=0.0)
        assert "AIU" not in line


class TestFinalSummary:
    """FR-RTO-02: 非 TTY では最終サマリーを 1 回だけ出す。"""

    def test_summary_text_contains_totals(self) -> None:
        text = orch._format_runtime_summary(_registry().totals())
        assert "tokens in=200" in text
        assert "out=40" in text
        assert "2.5000 AIU" in text

    def test_summary_suppressed_for_quiet(self, capsys) -> None:
        console = Console(quiet=True)
        console.runtime_metrics().apply({"kind": "assistant_usage", "step": "1", "input": 5})
        orch._emit_runtime_summary(console, SDKConfig(quiet=True))
        assert "tokens in=" not in capsys.readouterr().out

    def test_summary_emitted_for_non_tty(self, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        console = Console(verbose=False)
        monkeypatch.setattr(console, "_is_tty", False, raising=False)
        console.runtime_metrics().apply({"kind": "assistant_usage", "step": "1", "input": 5, "output": 2})
        orch._emit_runtime_summary(console, SDKConfig())

        assert "tokens in=5" in capsys.readouterr().out

    def test_summary_not_repeated_on_tty(self, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        console = Console(verbose=False)
        monkeypatch.setattr(console, "_is_tty", True, raising=False)
        console.runtime_metrics().apply({"kind": "assistant_usage", "step": "1", "input": 5})
        orch._emit_runtime_summary(console, SDKConfig())

        assert "tokens in=" not in capsys.readouterr().out


class TestStatusLineProvider:
    """1Hz 更新のため StatusLine は state を pull できる。"""

    def test_provider_is_used_on_render(self) -> None:
        from hve.statusline import StatusLine

        buffer = io.StringIO()
        provider_calls: list = []

        def provider() -> StatusLineState:
            provider_calls.append(1)
            return StatusLineState(tokens_in=7, tokens_out=1)

        line = StatusLine(stream=buffer, enabled=True, state_provider=provider).render_once()
        assert provider_calls
        assert "tok 7/1" in line


class TestRunWorkflowWiring:
    """FR-RTO-02: run_workflow が Dashboard 表示経路を配線する。"""

    def test_statusline_and_summary_are_wired(self) -> None:
        import inspect

        source = inspect.getsource(orch._run_workflow_body)
        assert "_attach_runtime_statusline(" in source
        assert "_emit_runtime_summary(" in source
        assert "_status_line.stop()" in source
