"""hve.gui.tests.test_page_workbench_fanout_progress

fan-out 子イベントの集約により base step の状態が正しく更新されることを検証する。

対象修正: fan-out 子の step_id（"<base>/<key>" 形式、例: "2.1/APP-09-S006"）
が GUI 側 ``_apply_stats_step_status`` で plan 外として無音破棄されていた問題の修正。
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_page(qapp, wf_id: str = "wf-a", base_ids: tuple = ("2.1",)):
    """WorkbenchPage を生成し、最小の plan 構造を seed する。

    base_ids に挙げた step を ``_workflow_step_status[wf_id]`` に登録する（空文字で
    開始）。これにより ``_apply_fanout_child_status`` の plan 内チェックを通過する。
    """
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    page._current_workflow_id = wf_id
    page._workflow_step_status.setdefault(wf_id, {})
    for bid in base_ids:
        page._workflow_step_status[wf_id][bid] = ""
    return page


def test_fanout_init_seeds_subtasks(qapp):
    page = _make_page(qapp)
    page._apply_stats_fanout_init(
        {
            "kind": "fanout_init",
            "workflow_id": "wf-a",
            "base_id": "2.1",
            "child_ids": ["2.1/A", "2.1/B", "2.1/C"],
        }
    )
    subs = page._workflow_subtask_status["wf-a"]["2.1"]
    assert [s[0] for s in subs] == ["2.1/A", "2.1/B", "2.1/C"]
    assert all(s[2] == "pending" for s in subs)
    # 初期化済みフラグが立つ
    assert "2.1" in page._fanout_initialized["wf-a"]


def test_fanout_init_is_idempotent(qapp):
    page = _make_page(qapp)
    payload = {
        "kind": "fanout_init",
        "workflow_id": "wf-a",
        "base_id": "2.1",
        "child_ids": ["2.1/A", "2.1/B"],
    }
    page._apply_stats_fanout_init(payload)
    page._apply_stats_fanout_init(payload)
    subs = page._workflow_subtask_status["wf-a"]["2.1"]
    assert len(subs) == 2  # 重複追加なし


def test_first_child_running_promotes_base_to_running(qapp):
    page = _make_page(qapp)
    page._apply_stats_fanout_init(
        {
            "kind": "fanout_init",
            "workflow_id": "wf-a",
            "base_id": "2.1",
            "child_ids": ["2.1/A", "2.1/B"],
        }
    )
    page._apply_stats_step_status(
        {"kind": "step_status", "step": "2.1/A", "status": "running"}
    )
    assert page._workflow_step_status["wf-a"]["2.1"] == "実行中"


def test_all_children_done_promotes_base_to_done(qapp):
    page = _make_page(qapp)
    page._apply_stats_fanout_init(
        {
            "kind": "fanout_init",
            "workflow_id": "wf-a",
            "base_id": "2.1",
            "child_ids": ["2.1/A", "2.1/B"],
        }
    )
    page._apply_stats_step_status(
        {"kind": "step_status", "step": "2.1/A", "status": "running"}
    )
    page._apply_stats_step_status(
        {"kind": "step_status", "step": "2.1/A", "status": "done"}
    )
    # まだ B が pending なので「完了」にならない
    assert page._workflow_step_status["wf-a"]["2.1"] == "実行中"
    page._apply_stats_step_status(
        {"kind": "step_status", "step": "2.1/B", "status": "running"}
    )
    page._apply_stats_step_status(
        {"kind": "step_status", "step": "2.1/B", "status": "done"}
    )
    assert page._workflow_step_status["wf-a"]["2.1"] == "完了"


def test_failed_child_with_all_terminal_keeps_base_completed(qapp):
    """1 子が failed、他子が done → base は "完了" 表記（既存マッピング互換）。"""
    page = _make_page(qapp)
    page._apply_stats_fanout_init(
        {
            "kind": "fanout_init",
            "workflow_id": "wf-a",
            "base_id": "2.1",
            "child_ids": ["2.1/A", "2.1/B"],
        }
    )
    page._apply_stats_step_status(
        {"kind": "step_status", "step": "2.1/A", "status": "done"}
    )
    page._apply_stats_step_status(
        {"kind": "step_status", "step": "2.1/B", "status": "failed"}
    )
    assert page._workflow_step_status["wf-a"]["2.1"] == "完了"


def test_no_fanout_init_keeps_base_in_progress_until_workflow_end(qapp):
    """fanout_init を受信しない場合、子の done 単独で base を完了にしない（早期完了防止）。"""
    page = _make_page(qapp)
    # fanout_init を呼ばずに child イベントだけ流す
    page._apply_stats_step_status(
        {"kind": "step_status", "step": "2.1/A", "status": "running"}
    )
    assert page._workflow_step_status["wf-a"]["2.1"] == "実行中"
    page._apply_stats_step_status(
        {"kind": "step_status", "step": "2.1/A", "status": "done"}
    )
    # 初期化されていないため「完了」に遷移しない
    assert page._workflow_step_status["wf-a"]["2.1"] == "実行中"


def test_plan_outside_base_id_is_ignored(qapp):
    """plan に存在しない base_id は捏造防止のため触らない。"""
    page = _make_page(qapp, base_ids=("2.1",))
    # base_id="9.9" は plan 外
    page._apply_stats_step_status(
        {"kind": "step_status", "step": "9.9/X", "status": "running"}
    )
    assert "9.9" not in page._workflow_step_status["wf-a"]


def test_non_fanout_step_uses_existing_path(qapp):
    """`/` を含まない step_id は既存ロジックそのまま（plan 内のみ更新）。"""
    page = _make_page(qapp, base_ids=("1",))
    page._apply_stats_step_status(
        {"kind": "step_status", "step": "1", "status": "running"}
    )
    assert page._workflow_step_status["wf-a"]["1"] == "実行中"
    page._apply_stats_step_status(
        {"kind": "step_status", "step": "1", "status": "done"}
    )
    assert page._workflow_step_status["wf-a"]["1"] == "完了"
