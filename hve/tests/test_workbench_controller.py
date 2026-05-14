"""test_workbench_controller.py — WorkbenchController API のテスト（Live は起動しない）。"""

from __future__ import annotations

from hve.workbench.controller import WorkbenchController
from hve.workbench.state import StepView, WorkbenchState


def _state() -> WorkbenchState:
    return WorkbenchState(
        workflow_id="aad",
        run_id="r1",
        model="m",
        steps=[
            StepView(id="1", title="A"),
            StepView(id="2", title="B"),
        ],
        body_window=12,
    )


def test_append_body_when_inactive_buffers_fallback() -> None:
    wb = WorkbenchController(_state())
    # __enter__ せず（active=False のまま）append しても落ちない
    wb.append_body("line-1")
    wb.append_body("line-2")
    assert wb.state.body.view(window=2, offset=0) == ["line-1", "line-2"]
    assert wb._fallback_lines == ["line-1", "line-2"]


def test_set_step_status_updates_state() -> None:
    wb = WorkbenchController(_state())
    wb.set_step_status("1", "running")
    assert wb.state.steps[0].status == "running"
    wb.set_step_status("1", "done")
    assert wb.state.steps[0].status == "done"


def test_set_context_and_model() -> None:
    wb = WorkbenchController(_state())
    wb.set_context(50, 500, 3)
    assert wb.state.context_current == 50
    wb.set_model("gpt-5.4")
    assert wb.state.model == "gpt-5.4"


def test_scroll_clamps_to_max() -> None:
    wb = WorkbenchController(_state())
    for i in range(20):
        wb.append_body(f"line-{i}")
    # body_window=12, total=20 → max_offset=8
    wb.scroll_up(100)
    assert wb.state.scroll_offset == 8
    wb.scroll_down(100)
    assert wb.state.scroll_offset == 0


def test_page_up_down() -> None:
    wb = WorkbenchController(_state())
    for i in range(50):
        wb.append_body(f"line-{i}")
    wb.page_up()
    assert wb.state.scroll_offset == 12
    wb.page_down()
    assert wb.state.scroll_offset == 0


def test_home_end() -> None:
    wb = WorkbenchController(_state())
    for i in range(30):
        wb.append_body(f"line-{i}")
    wb.home()
    assert wb.state.scroll_offset == 18  # 30 - 12
    wb.end()
    assert wb.state.scroll_offset == 0


def test_expand_steps_and_increment() -> None:
    wb = WorkbenchController(_state())
    wb.expand_steps("2", ["x", "y", "z"])
    assert getattr(wb.state.steps[1], "_fanout_total") == 3
    wb.set_step_status("2", "running")
    wb.increment_fanout_done("2")
    wb.increment_fanout_done("2")
    wb.increment_fanout_done("2")
    assert wb.state.steps[1].status == "done"


def test_stop_without_start_is_safe() -> None:
    wb = WorkbenchController(_state(), flush_on_exit=False)
    wb.stop()  # 例外が出ない
    assert wb.active is False


def test_active_property_initially_false() -> None:
    wb = WorkbenchController(_state())
    assert wb.active is False


# ---------------------------------------------------------------------------
# 1 Hz tick: TaskTree elapsed の自動カウントアップ
# ---------------------------------------------------------------------------

def test_tick_loop_invokes_refresh_layout_until_stop() -> None:
    """tick_stop set 前は _refresh_layout を呼び、set 後はループ脱出する。"""
    import threading

    wb = WorkbenchController(_state())
    # Live を起動せずに tick_loop の挙動だけ検証
    wb._active = True  # tick_loop 内の active ガードを通すため
    wb._tick_interval = 0.01  # テスト高速化
    calls: list[int] = []

    def fake_refresh() -> None:
        calls.append(1)

    wb._refresh_layout = fake_refresh  # type: ignore[method-assign]
    wb._tick_stop.clear()
    t = threading.Thread(target=wb._tick_loop, daemon=True)
    t.start()
    # 50ms 走らせる → 数回 refresh が呼ばれる
    import time as _time
    _time.sleep(0.05)
    wb._tick_stop.set()
    t.join(timeout=1.0)
    assert not t.is_alive()
    assert len(calls) >= 2  # 0.01s * 数回


def test_tick_loop_skips_refresh_when_all_done() -> None:
    """state.all_done=True の間は _refresh_layout を呼ばない。"""
    import threading
    import time as _time

    wb = WorkbenchController(_state())
    wb._active = True
    wb._tick_interval = 0.01
    wb.state.mark_all_done()
    calls: list[int] = []
    wb._refresh_layout = lambda: calls.append(1)  # type: ignore[method-assign]
    wb._tick_stop.clear()
    t = threading.Thread(target=wb._tick_loop, daemon=True)
    t.start()
    _time.sleep(0.05)
    wb._tick_stop.set()
    t.join(timeout=1.0)
    assert calls == []  # all_done のため一度も呼ばれない

