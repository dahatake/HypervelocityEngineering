"""``format_log_prefix`` と ``append_workflow_log`` のプリフィックス検証。"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.workbench_state import (  # noqa: E402
    WorkbenchState,
    WorkflowInstanceSeed,
    StepSeed,
    format_log_prefix,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# format_log_prefix（純関数）
# ---------------------------------------------------------------------------


def test_prefix_with_step_id_and_title():
    assert format_log_prefix("wf-a", "1", "準備") == "[wf-a]-[1.準備] "


def test_prefix_without_title_uses_step_id_only():
    assert format_log_prefix("wf-a", "2", None) == "[wf-a]-[2] "


def test_prefix_without_step_id_uses_main():
    assert format_log_prefix("wf-a", None, None) == "[wf-a]-[main] "
    assert format_log_prefix("wf-a", "", None) == "[wf-a]-[main] "


def test_prefix_with_empty_workflow_id_uses_placeholder():
    assert format_log_prefix("", "1", "T") == "[?]-[1.T] "


# ---------------------------------------------------------------------------
# append_workflow_log がプリフィックスを付与すること
# ---------------------------------------------------------------------------


def _new_state(qapp) -> WorkbenchState:
    state = WorkbenchState(workflow_id="root", run_id="r1", model="m")
    return state


def test_append_workflow_log_prefixes_normal_lines(qapp):
    state = _new_state(qapp)
    state.prepopulate_workflow_instances(
        [WorkflowInstanceSeed("wf-a", "wf-a", "wf-a", None, [StepSeed("1", "準備")])]
    )
    state.append_workflow_log("wf-a", "1", "Hello")
    inst = state.workflows["wf-a"]
    assert inst.log_buffer == ["[wf-a]-[1.準備] Hello"]
    assert inst.step_log_buffers["1"] == ["[wf-a]-[1.準備] Hello"]


def test_append_workflow_log_uses_main_when_step_id_missing(qapp):
    state = _new_state(qapp)
    state.prepopulate_workflow_instances(
        [WorkflowInstanceSeed("wf-a", "wf-a", "wf-a", None, [])]
    )
    state.append_workflow_log("wf-a", None, "global")
    inst = state.workflows["wf-a"]
    assert inst.log_buffer == ["[wf-a]-[main] global"]
    # step_log_buffers には何も入らない
    assert inst.step_log_buffers == {}


def test_append_workflow_log_does_not_prefix_stats_lines(qapp):
    state = _new_state(qapp)
    state.prepopulate_workflow_instances(
        [WorkflowInstanceSeed("wf-a", "wf-a", "wf-a", None, [StepSeed("1", "S")])]
    )
    line = '[hve:stats] {"kind":"step_status","step":"1","status":"running"}'
    state.append_workflow_log("wf-a", "1", line)
    inst = state.workflows["wf-a"]
    # stats 行はプリフィックスせず生のまま保持
    assert inst.log_buffer == [line]


def test_append_workflow_log_no_op_for_unknown_instance(qapp):
    state = _new_state(qapp)
    # 例外を投げない
    state.append_workflow_log("unknown", "1", "x")


def test_append_workflow_log_returns_formatted_line(qapp):
    """append_workflow_log は呼び出し側が表示パスへ伝搬できるよう
    フォーマット済み行を返す（Critical #1 修正で追加されたコントラクト）。"""
    state = _new_state(qapp)
    state.prepopulate_workflow_instances(
        [WorkflowInstanceSeed("wf-a", "wf-a", "wf-a", None, [StepSeed("1", "準備")])]
    )
    formatted = state.append_workflow_log("wf-a", "1", "Hello")
    assert formatted == "[wf-a]-[1.準備] Hello"
    # stats 行は素通し
    stats = '[hve:stats] {"kind":"step_status"}'
    assert state.append_workflow_log("wf-a", "1", stats) == stats
    # 未登録 instance は None
    assert state.append_workflow_log("unknown", "1", "x") is None
