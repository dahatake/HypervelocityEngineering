"""test_workbench_state.py — WorkbenchState の単体テスト。"""

from __future__ import annotations

import pytest

from hve.workbench.state import (
    BODY_WINDOW_MAX,
    BODY_WINDOW_MIN,
    StepView,
    WorkbenchState,
    clamp_body_window,
)


def _make_state() -> WorkbenchState:
    return WorkbenchState(
        workflow_id="aad",
        run_id="run-1",
        model="claude-opus-4.7",
        steps=[
            StepView(id="1", title="DataModel"),
            StepView(id="2", title="Catalog"),
            StepView(id="3", title="ServiceSpec"),
        ],
    )


def test_clamp_body_window() -> None:
    assert clamp_body_window(5) == BODY_WINDOW_MIN
    assert clamp_body_window(100) == BODY_WINDOW_MAX
    assert clamp_body_window(12) == 12


def test_body_window_range_is_10_to_20() -> None:
    """要件: body_window の許容範囲は [10, 20]、既定値は 20。"""
    from hve.workbench.state import BODY_WINDOW_DEFAULT
    assert BODY_WINDOW_MIN == 10
    assert BODY_WINDOW_MAX == 20
    assert BODY_WINDOW_DEFAULT == 20
    assert clamp_body_window(20) == 20
    assert clamp_body_window(21) == 20
    assert clamp_body_window(10) == 10
    assert clamp_body_window(9) == 10


def test_post_init_clamps_body_window() -> None:
    s = WorkbenchState(workflow_id="x", run_id="r", model="m", body_window=99)
    assert s.body_window == BODY_WINDOW_MAX
    s2 = WorkbenchState(workflow_id="x", run_id="r", model="m", body_window=1)
    assert s2.body_window == BODY_WINDOW_MIN


def test_set_step_status_running_updates_pointer() -> None:
    s = _make_state()
    s.set_step_status("2", "running")
    assert s.steps[1].status == "running"
    assert s.current_running_step_id == "2"


def test_set_step_status_done_clears_pointer_when_match() -> None:
    s = _make_state()
    s.set_step_status("2", "running")
    s.set_step_status("2", "done")
    assert s.steps[1].status == "done"
    assert s.current_running_step_id is None


def test_set_step_status_done_keeps_pointer_when_other() -> None:
    s = _make_state()
    s.set_step_status("2", "running")
    s.set_step_status("1", "done")
    assert s.current_running_step_id == "2"


def test_set_step_status_unknown_id_is_noop() -> None:
    s = _make_state()
    s.set_step_status("nonexistent", "done")
    assert s.current_running_step_id is None


def test_set_step_status_invalid_raises() -> None:
    s = _make_state()
    with pytest.raises(ValueError):
        s.set_step_status("1", "weird")  # type: ignore[arg-type]


def test_failed_and_skipped() -> None:
    s = _make_state()
    s.set_step_status("1", "failed")
    s.set_step_status("2", "skipped")
    assert s.steps[0].status == "failed"
    assert s.steps[1].status == "skipped"


def test_append_body_and_view() -> None:
    s = _make_state()
    s.append_body("line-1")
    s.append_body("line-2")
    assert s.body.view(window=2, offset=0) == ["line-1", "line-2"]


def test_set_context_and_model() -> None:
    s = _make_state()
    s.set_context(100, 1000, 5)
    assert (s.context_current, s.context_limit, s.context_msgs) == (100, 1000, 5)
    s.set_model("gpt-5.4")
    assert s.model == "gpt-5.4"


def test_expand_steps_attaches_counters() -> None:
    s = _make_state()
    s.expand_steps("3", ["a", "b", "c"])
    target = s.steps[2]
    assert getattr(target, "_fanout_total") == 3
    assert getattr(target, "_fanout_done") == 0
    assert getattr(target, "_fanout_keys") == ["a", "b", "c"]


def test_increment_fanout_done_completes() -> None:
    s = _make_state()
    s.expand_steps("3", ["a", "b"])
    s.set_step_status("3", "running")
    s.increment_fanout_done("3")
    assert getattr(s.steps[2], "_fanout_done") == 1
    assert s.steps[2].status == "running"
    s.increment_fanout_done("3")
    assert getattr(s.steps[2], "_fanout_done") == 2
    assert s.steps[2].status == "done"


# ---------------------------------------------------------------------------
# TaskTree 経過時間: finished_at_monotonic 記録 / mark_all_done で凍結
# ---------------------------------------------------------------------------

def test_set_step_status_records_finished_at_on_terminal_status() -> None:
    s = _make_state()
    s.set_step_status("1", "running")
    node_running = s.task_tree.get("1")
    assert node_running is not None
    assert node_running.started_at_monotonic is not None
    assert node_running.finished_at_monotonic is None

    s.set_step_status("1", "done")
    node_done = s.task_tree.get("1")
    assert node_done.finished_at_monotonic is not None
    assert node_done.finished_at_monotonic >= node_done.started_at_monotonic


def test_set_step_status_records_finished_at_for_failed_and_skipped() -> None:
    s = _make_state()
    s.set_step_status("1", "failed")
    s.set_step_status("2", "skipped")
    assert s.task_tree.get("1").finished_at_monotonic is not None
    assert s.task_tree.get("2").finished_at_monotonic is not None


def test_update_subtask_status_records_finished_at() -> None:
    s = _make_state()
    s.set_step_status("1", "running")
    s.register_subtask("1", "sub-a", "Sub-agent A", kind="subagent")
    sub = s.task_tree.get("sub-a")
    assert sub.finished_at_monotonic is None
    s.update_subtask_status("sub-a", "done")
    assert s.task_tree.get("sub-a").finished_at_monotonic is not None


def test_mark_all_done_freezes_workflow_root() -> None:
    s = _make_state()
    s.set_step_status("1", "running")
    root = s.task_tree.root
    assert root is not None
    assert root.finished_at_monotonic is None
    assert s.mark_all_done() is True
    assert root.finished_at_monotonic is not None
    # 残存 running も done + finished_at 記録
    assert s.task_tree.get("1").status == "done"
    assert s.task_tree.get("1").finished_at_monotonic is not None
    # 冪等
    assert s.mark_all_done() is False

