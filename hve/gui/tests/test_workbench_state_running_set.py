"""WorkbenchState.running_step_ids の集合管理 / 並列 fanout 誤帰属抑止の回帰テスト。

背景:
  並列 fanout 子が複数同時に running 化したとき、単一スカラ
  ``current_running_step_id`` を append_workflow_log の fallback に使うと、
  インラインマーカー (`[hve:ctx:<step_id>]`) が欠落した行はすべて
  「最後に running 化した child」へ誤帰属する。

  本テストは:
    1. set_step_status が ``running_step_ids`` を集合として正しく維持すること
    2. 終了状態遷移で集合から除外されること
  を確認する。Plan モード側 fallback 抑止（``len >= 2`` で None）は
  page_workbench 側で実装され、本 state は判定材料を提供する責務に閉じる。
"""

from __future__ import annotations

import pytest

from hve.gui.workbench_state import WorkbenchState


def _new_state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf", run_id="rid", model="m")


def test_running_step_ids_tracks_parallel_steps():
    s = _new_state()
    s.set_step_status("base/child_1", "running")
    s.set_step_status("base/child_2", "running")
    s.set_step_status("base/child_3", "running")

    assert s.running_step_ids == {"base/child_1", "base/child_2", "base/child_3"}
    # 単一スカラは最後に running 化したものに上書きされる（既存仕様）。
    # これだけだと誤帰属の原因になるため、複数並列時は呼び出し側で
    # |running_step_ids| >= 2 を見て fallback を抑止する設計。
    assert s.current_running_step_id == "base/child_3"
    assert s.last_known_step_id == "base/child_3"


@pytest.mark.parametrize("terminal_status", ["done", "failed", "skipped"])
def test_running_step_ids_drops_on_terminal(terminal_status):
    s = _new_state()
    s.set_step_status("a", "running")
    s.set_step_status("b", "running")
    s.set_step_status("a", terminal_status)  # type: ignore[arg-type]
    assert s.running_step_ids == {"b"}
    s.set_step_status("b", terminal_status)  # type: ignore[arg-type]
    assert s.running_step_ids == set()


def test_running_step_ids_idempotent_running_transition():
    s = _new_state()
    s.set_step_status("x", "running")
    s.set_step_status("x", "running")
    assert s.running_step_ids == {"x"}


def test_running_step_ids_unknown_terminal_is_noop():
    s = _new_state()
    s.set_step_status("a", "running")
    # 未 running の step に対する terminal は集合を破壊しない
    s.set_step_status("never_ran", "done")
    assert s.running_step_ids == {"a"}


def test_current_tool_counts_aggregates_when_parallel():
    s = _new_state()
    s.set_step_status("a", "running")
    s.set_step_status("b", "running")
    s.record_tool_call("a", "view")
    s.record_tool_call("a", "view")
    s.record_tool_call("b", "view")
    s.record_tool_call("b", "edit")
    # 並列中は a, b 双方の合算
    assert s.current_tool_counts() == {"view": 3, "edit": 1}
    # 1 個 done になれば残 running の集計（または single 経路）
    s.set_step_status("a", "done")
    assert s.current_tool_counts() == {"view": 1, "edit": 1}


def test_current_skill_counts_aggregates_when_parallel():
    s = _new_state()
    s.set_step_status("a", "running")
    s.set_step_status("b", "running")
    s.record_skill_invoked("a", "task-dag-planning")
    s.record_skill_invoked("b", "task-dag-planning")
    s.record_skill_invoked("b", "knowledge-lookup")
    assert s.current_skill_counts() == {
        "task-dag-planning": 2,
        "knowledge-lookup": 1,
    }


def test_current_counts_single_running_uses_scalar():
    s = _new_state()
    s.set_step_status("a", "running")
    s.record_tool_call("a", "view")
    s.record_skill_invoked("a", "task-dag-planning")
    # 単一 running 時は従来挙動（スカラ参照）。
    assert s.current_tool_counts() == {"view": 1}
    assert s.current_skill_counts() == {"task-dag-planning": 1}
