"""FR-RTO-05: `--autopilot-child` 互換ウィンドウでも観測イベントを取り込む。

RED 先行。旧 GUI child の runtime observability 配線は本テスト作成時点で未実装。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve import runtime_observability as rto  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def window(qapp, monkeypatch: pytest.MonkeyPatch):
    from hve.gui import workbench_window as ww
    from hve.gui.wizard import WizardResult

    # 子プロセスを起動させない（起動は QTimer.singleShot 経由のため呼ばれないが二重防御）。
    monkeypatch.setattr(ww, "launch_orchestrator", lambda *a, **k: (_ for _ in ()).throw(OSError("blocked")))
    win = ww.WorkbenchWindow(WizardResult(workflow="aad-web"), session_index=1)
    yield win
    win.close()


class TestRuntimeMetricsIntake:
    def test_registry_exists(self, window) -> None:
        assert isinstance(window.runtime_metrics, rto.RuntimeMetricsRegistry)

    def test_stats_line_updates_registry(self, window) -> None:
        ctx = rto.RuntimeContext(instance_id="aad-web")
        window._on_line_received(
            rto.format_stats_line(rto.build_event("assistant_usage", "1", ctx, input=12, output=3))
        )

        totals = window.runtime_metrics.totals()
        assert totals.input_tokens_total == 12
        assert totals.output_tokens_total == 3

    def test_stats_line_is_not_shown_in_log_pane(self, window) -> None:
        ctx = rto.RuntimeContext(instance_id="aad-web")
        window._on_line_received(
            rto.format_stats_line(rto.build_event("assistant_usage", "1", ctx, input=1))
        )

        assert "[hve:stats]" not in window._log_pane.log_view.toPlainText()

    def test_normal_line_still_shown(self, window) -> None:
        window._on_line_received("通常のログ行")
        assert "通常のログ行" in window._log_pane.log_view.toPlainText()

    def test_status_bar_shows_runtime_summary(self, window) -> None:
        ctx = rto.RuntimeContext(instance_id="aad-web")
        window._on_line_received(
            rto.format_stats_line(rto.build_event("assistant_usage", "1", ctx, input=25, output=5))
        )

        assert "tokens in=25" in window._status_label.text()


class TestSummaryFormatterIsShared:
    """FR-MAINT-07: サマリー整形は core 実装に単一化する。"""

    def test_core_formatter_exists(self) -> None:
        metrics = rto.RuntimeMetrics()
        metrics.apply({"kind": "assistant_usage", "step": "1", "input": 9, "output": 2})
        text = rto.format_runtime_summary(metrics)
        assert "tokens in=9" in text
        assert "out=2" in text

    def test_orchestrator_delegates_to_core(self) -> None:
        from hve import orchestrator as orch

        metrics = rto.RuntimeMetrics()
        metrics.apply({"kind": "assistant_usage", "step": "1", "input": 4, "output": 1})
        assert orch._format_runtime_summary(metrics) == rto.format_runtime_summary(metrics)
