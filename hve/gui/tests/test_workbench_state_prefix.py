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
    _extract_inline_ctx,
    _extract_timestamp,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# format_log_prefix（純関数） — Q3=i 新フォーマット
# ---------------------------------------------------------------------------


def test_prefix_with_step_id_and_title():
    # 新フォーマット: [WF大文字] [step_id] [title]
    assert format_log_prefix("wf-a", "1", "準備") == "[WF-A] [1] [準備] "


def test_prefix_without_title_uses_step_id_only():
    assert format_log_prefix("wf-a", "2", None) == "[WF-A] [2] "


def test_prefix_without_step_id_uses_main():
    assert format_log_prefix("wf-a", None, None) == "[WF-A] [main] "
    assert format_log_prefix("wf-a", "", None) == "[WF-A] [main] "


def test_prefix_with_empty_workflow_id_uses_placeholder():
    assert format_log_prefix("", "1", "T") == "[?] [1] [T] "


def test_prefix_with_timestamp():
    assert (
        format_log_prefix("ard", "4.2/UC-03", "ユースケース", timestamp="11:18:10")
        == "[11:18:10] [ARD] [4.2/UC-03] [ユースケース] "
    )


# ---------------------------------------------------------------------------
# インラインマーカー抽出ヘルパー
# ---------------------------------------------------------------------------


def test_extract_inline_ctx_with_marker():
    sid, rest = _extract_inline_ctx("[hve:ctx:4.2/UC-29] [11:18:10]   ▶ body")
    assert sid == "4.2/UC-29"
    assert rest == "[11:18:10]   ▶ body"


def test_extract_inline_ctx_without_marker():
    sid, rest = _extract_inline_ctx("[11:18:10] no ctx marker")
    assert sid is None
    assert rest == "[11:18:10] no ctx marker"


def test_extract_timestamp_present():
    ts, rest = _extract_timestamp("[11:18:10]   ▶ body")
    assert ts == "11:18:10"
    assert rest == "▶ body"


def test_extract_timestamp_absent():
    ts, rest = _extract_timestamp("no timestamp here")
    assert ts is None
    assert rest == "no timestamp here"


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
    assert inst.log_buffer == ["[WF-A] [1] [準備] Hello"]
    assert inst.step_log_buffers["1"] == ["[WF-A] [1] [準備] Hello"]


def test_append_workflow_log_uses_main_when_step_id_missing(qapp):
    state = _new_state(qapp)
    state.prepopulate_workflow_instances(
        [WorkflowInstanceSeed("wf-a", "wf-a", "wf-a", None, [])]
    )
    state.append_workflow_log("wf-a", None, "global")
    inst = state.workflows["wf-a"]
    assert inst.log_buffer == ["[WF-A] [main] global"]
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
    assert formatted == "[WF-A] [1] [準備] Hello"
    # stats 行は素通し
    stats = '[hve:stats] {"kind":"step_status"}'
    assert state.append_workflow_log("wf-a", "1", stats) == stats
    # 未登録 instance は None
    assert state.append_workflow_log("unknown", "1", "x") is None


# ---------------------------------------------------------------------------
# インラインマーカー優先 — 並列 fanout の取り違え防止 (T7 観点)
# ---------------------------------------------------------------------------


def test_inline_ctx_marker_overrides_step_id_argument(qapp):
    """行頭 ``[hve:ctx:<id>]`` が引数 step_id より優先されること。

    並列 fanout で複数 child が共有ストリームに出力する状況をシミュレート:
    呼び出し側 (`current_running_step_id`) が UC-06 を指している間に、
    本来 UC-03 から発生したログが届いた場合でも、インラインマーカーが
    あれば正しく UC-03 へ帰属する。
    """
    state = _new_state(qapp)
    state.prepopulate_workflow_instances(
        [WorkflowInstanceSeed(
            "ard", "ard", "ard", None,
            [StepSeed("4.2/UC-03", "ユースケース詳細生成 (UC-03)"),
             StepSeed("4.2/UC-06", "ユースケース詳細生成 (UC-06)")],
        )]
    )
    # 引数 step_id は UC-06（古い current_running_step_id を想定）だが、
    # インラインマーカーは UC-03 → UC-03 へ帰属するべき。
    formatted = state.append_workflow_log(
        "ard", "4.2/UC-06",
        "[hve:ctx:4.2/UC-03] [11:18:19]   ┊ Phase 1/1: メインタスク",
    )
    assert formatted == (
        "[11:18:19] [ARD] [4.2/UC-03] [ユースケース詳細生成 (UC-03)] "
        "┊ Phase 1/1: メインタスク"
    )
    inst = state.workflows["ard"]
    # step_log_buffers も UC-03 側に積まれる
    assert "4.2/UC-03" in inst.step_log_buffers
    assert "4.2/UC-06" not in inst.step_log_buffers
