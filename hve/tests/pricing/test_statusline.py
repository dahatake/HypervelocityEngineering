"""Wave 5 CUI: StatusLine のテスト (Qt 非依存)。"""

from __future__ import annotations

import io
import time

import pytest

from hve.statusline import StatusLine, StatusLineState, format_status_line


# ------------------------------------------------------------------
# format_status_line
# ------------------------------------------------------------------

def test_format_status_line_minimal():
    s = StatusLineState()
    line = format_status_line(s)
    assert line.startswith("[hve]")
    assert "cost -" in line
    assert "reqs 0" in line


def test_format_status_line_with_workflow_and_step():
    s = StatusLineState(
        workflow_started_at=1000.0,
        step_id="prep",
        step_started_at=1050.0,
        context_current=12345,
        context_limit=200000,
        cost_usd_total=0.4,
        cost_jpy_total=60.0,
        premium_requests_total=10,
    )
    line = format_status_line(s, now=1083.0)
    assert "WF 00:01:23" in line
    assert "Step prep 00:00:33" in line
    assert "ctx 12,345/200,000 (6%)" in line
    assert "$" in line and "¥60" in line
    assert "reqs 10" in line


def test_format_status_line_sub_segment():
    s = StatusLineState(
        workflow_started_at=0.0,
        sub_name="impl",
        sub_started_at=10.0,
    )
    line = format_status_line(s, now=70.0)
    assert "Sub impl 00:01:00" in line


def test_format_status_line_no_context_when_limit_zero():
    s = StatusLineState(context_current=100, context_limit=0)
    line = format_status_line(s)
    assert "ctx" not in line


def test_format_status_line_no_fabrication_when_cost_unknown():
    s = StatusLineState(cost_usd_total=None, cost_jpy_total=None)
    line = format_status_line(s)
    assert "cost -" in line
    assert "$" not in line
    assert "¥" not in line


# ------------------------------------------------------------------
# StatusLine class
# ------------------------------------------------------------------

def test_statusline_disabled_when_not_tty(monkeypatch):
    monkeypatch.delenv("HVE_NO_STATUSLINE", raising=False)
    buf = io.StringIO()  # isatty() → False
    sl = StatusLine(stream=buf)
    assert sl.enabled is False
    sl.start()
    sl.update_state(StatusLineState(premium_requests_total=5))
    out = sl.render_once()
    assert out == ""
    assert buf.getvalue() == ""
    sl.stop()


def test_statusline_disabled_by_env(monkeypatch):
    monkeypatch.setenv("HVE_NO_STATUSLINE", "1")

    class _TTY(io.StringIO):
        def isatty(self) -> bool:
            return True

    sl = StatusLine(stream=_TTY())
    assert sl.enabled is False


def test_statusline_enabled_override_writes_to_stream(monkeypatch):
    monkeypatch.delenv("HVE_NO_STATUSLINE", raising=False)
    buf = io.StringIO()
    sl = StatusLine(stream=buf, enabled=True)
    assert sl.enabled is True
    sl.update_state(StatusLineState(premium_requests_total=3))
    out = sl.render_once()
    assert "reqs 3" in out
    rendered = buf.getvalue()
    assert "\r\x1b[2K" in rendered
    assert "reqs 3" in rendered


def test_statusline_stop_clears_line(monkeypatch):
    monkeypatch.delenv("HVE_NO_STATUSLINE", raising=False)
    buf = io.StringIO()
    sl = StatusLine(stream=buf, enabled=True, interval=0.05)
    sl.start()
    sl.update_state(StatusLineState(premium_requests_total=1))
    time.sleep(0.15)  # 数回 render
    sl.stop()
    # stop 後に最終 clear が書かれていること
    assert buf.getvalue().endswith("\r\x1b[2K")


def test_statusline_update_fields():
    buf = io.StringIO()
    sl = StatusLine(stream=buf, enabled=True)
    sl.update_fields(premium_requests_total=7, cost_usd_total=1.5, cost_jpy_total=225.0)
    snap = sl.snapshot()
    assert snap.premium_requests_total == 7
    assert snap.cost_usd_total == 1.5
    out = sl.render_once()
    assert "reqs 7" in out


def test_statusline_context_manager(monkeypatch):
    monkeypatch.delenv("HVE_NO_STATUSLINE", raising=False)
    buf = io.StringIO()
    with StatusLine(stream=buf, enabled=True, interval=0.05) as sl:
        sl.update_state(StatusLineState(premium_requests_total=2))
        sl.render_once()  # 確実に最新状態を 1 回描画する (スケジューラ非依存)
        time.sleep(0.1)
    # __exit__ で stop → clear が末尾に
    assert "reqs 2" in buf.getvalue()
