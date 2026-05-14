"""test_workbench_task_tree.py — TaskTree elapsed 凍結 / aggregate_elapsed のテスト。"""

from __future__ import annotations

from hve.workbench.task_tree import TaskNode, TaskTree


def _build_tree(now: float = 1000.0) -> TaskTree:
    t = TaskTree()
    t.add_root(
        TaskNode(
            id="__workflow__",
            title="wf",
            status="running",
            started_at_monotonic=now,
        )
    )
    return t


def test_node_elapsed_running_uses_now() -> None:
    t = _build_tree(now=1000.0)
    t.add_child(
        "__workflow__",
        TaskNode(
            id="s1", title="step1", status="running",
            started_at_monotonic=1000.0,
        ),
    )
    assert t._node_elapsed(t.get("s1"), 1005.0) == 5.0


def test_node_elapsed_frozen_when_finished() -> None:
    t = _build_tree(now=1000.0)
    t.add_child(
        "__workflow__",
        TaskNode(
            id="s1", title="step1", status="done",
            started_at_monotonic=1000.0,
            finished_at_monotonic=1003.0,
        ),
    )
    # now が進んでも finished_at で凍結される
    assert t._node_elapsed(t.get("s1"), 1100.0) == 3.0


def test_node_elapsed_pending_is_zero() -> None:
    t = _build_tree(now=1000.0)
    t.add_child(
        "__workflow__",
        TaskNode(id="s1", title="step1", status="pending"),
    )
    assert t._node_elapsed(t.get("s1"), 1100.0) == 0.0


def test_aggregate_elapsed_leaf_equals_node_elapsed() -> None:
    t = _build_tree(now=1000.0)
    t.add_child(
        "__workflow__",
        TaskNode(
            id="s1", title="step1", status="running",
            started_at_monotonic=1000.0,
        ),
    )
    assert t.aggregate_elapsed("s1", 1010.0) == 10.0


def test_aggregate_elapsed_parallel_sum_exceeds_wall() -> None:
    """並列実行を表現: 2 つの running step が同時に走ると合計 > wall。"""
    t = _build_tree(now=1000.0)
    t.add_child("__workflow__", TaskNode(
        id="s1", title="s1", status="running", started_at_monotonic=1000.0))
    t.add_child("__workflow__", TaskNode(
        id="s2", title="s2", status="running", started_at_monotonic=1000.0))
    # wall = 5s, sum = 10s
    assert t.aggregate_elapsed("__workflow__", 1005.0) == 10.0


def test_aggregate_elapsed_mixed_done_and_running() -> None:
    t = _build_tree(now=1000.0)
    t.add_child("__workflow__", TaskNode(
        id="s1", title="s1", status="done",
        started_at_monotonic=1000.0, finished_at_monotonic=1004.0))
    t.add_child("__workflow__", TaskNode(
        id="s2", title="s2", status="running",
        started_at_monotonic=1002.0))
    # s1: 4s (frozen), s2: 1008-1002=6s
    assert t.aggregate_elapsed("__workflow__", 1008.0) == 10.0


def test_render_lines_workflow_root_shows_sum_label() -> None:
    t = _build_tree(now=1000.0)
    t.add_child("__workflow__", TaskNode(
        id="s1", title="step1", status="running",
        started_at_monotonic=1000.0))
    t.add_child("__workflow__", TaskNode(
        id="s2", title="step2", status="running",
        started_at_monotonic=1000.0))
    lines = t.render_lines(1003.0, max_lines=5, max_width=200)
    root_plain = lines[0].plain
    # sum = 6s = 00:00:06, "合計" ラベル付き
    assert "合計" in root_plain
    assert "00:00:06" in root_plain


def test_render_lines_finished_node_freezes_display() -> None:
    t = _build_tree(now=1000.0)
    t.add_child("__workflow__", TaskNode(
        id="s1", title="s1", status="done",
        started_at_monotonic=1000.0, finished_at_monotonic=1002.0))
    # now を大幅に進めても s1 の表示は 00:00:02
    lines = t.render_lines(1100.0, max_lines=5, max_width=200)
    s1_line = next(l for l in lines if "s1" in l.plain)
    assert "00:00:02" in s1_line.plain
