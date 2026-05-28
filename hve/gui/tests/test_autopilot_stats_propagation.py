"""hve.gui.tests.test_autopilot_stats_propagation

gui-workbench-stats-propagation F4 — Autopilot 経路で `[hve:stats] {...}` 行が
``WorkbenchPage.append_log`` 経由で WorkbenchState へ反映されること、および
WorkflowInstance の running / finished 遷移 API が正しく動作することを検証する。

検証範囲:
  T1: stats 行が `append_log` を通過し `_apply_log_line_to_instance_tree` で
      Step ステータスが pending → running に遷移する（F1' + 既存ロジック）
  T2: stats 行が UI ログタブ (_log_tabs._global_view) に**混入しない**
      （F1' の表示抑止移植のリグレッション防止）
  T3: stats 行（tool_invoked）が `append_log` 経由で Footer 用 state を
      更新する（F2: process_subprocess_line の呼び出し）
  T4: ``update_workflow_instance_status(id, "running")`` で ``started_at`` が
      set される（F3a）
  T5: ``mark_workflow_instance_finished(id, 0)`` で ``finished_at`` と
      ``status="done"`` が確定する（F3b）
  T6: ``mark_workflow_instance_finished(id, 1)`` で ``status="failed"`` に
      なる（F3b 失敗系）
"""
from __future__ import annotations

import json

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _stats_step_status_line(step_id: str, status: str) -> str:
    payload = {"kind": "step_status", "step": step_id, "status": status, "title": "t"}
    return f"[hve:stats] {json.dumps(payload)}"


def _stats_tool_invoked_line(step_id: str, tool_name: str) -> str:
    payload = {"kind": "tool_invoked", "step": step_id, "tool_name": tool_name}
    return f"[hve:stats] {json.dumps(payload)}"


def _stats_fanout_init_line(base_id: str, child_ids: list) -> str:
    payload = {"kind": "fanout_init", "base_id": base_id, "child_ids": child_ids}
    return f"[hve:stats] {json.dumps(payload)}"


def _seed_instance(page, instance_id: str, step_id: str = "1") -> None:
    """テスト対象インスタンスを workflow_id 配下の Step 付きで pending 事前登録する。"""
    from hve.gui.workbench_state import WorkflowInstanceSeed

    page.prepopulate_workflow_instances(
        [
            WorkflowInstanceSeed(
                instance_id=instance_id,
                workflow_id=instance_id,
                label=instance_id,
                app_id=None,
                steps=[(step_id, "Step Title")],
            )
        ]
    )


def test_t1_stats_step_status_running_via_append_log(qapp):
    """T1: stats step_status 行が append_log → state.workflows へ反映される。

    加えて ``StepView.started_at`` が set されることも確認する
    （ツリー上の elapsed カウントアップの根拠）。
    """
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    _seed_instance(page, "wf-x", step_id="1")
    line = _stats_step_status_line("1", "running")

    page.append_log("wf-x", "", line)

    step = page._state.find_step_in_instance("wf-x", "1")
    assert step is not None
    assert step.status == "running"
    assert step.started_at is not None


def test_t2_stats_line_not_mirrored_to_log_tabs(qapp):
    """T2: stats 行は UI 全体タブと ``_log_pane`` に**書き込まれない**。

    F1' では `append_log` 内で `is_stats_line` ガードをかけているため、
    ファイル永続化用 `_log_pane` と UI 表示用 `_log_tabs` の両方で
    ノイズの有無を検証する。
    """
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    _seed_instance(page, "wf-y")
    stats_line = _stats_step_status_line("1", "running")
    human_line = "hello human readable"

    page.append_log("wf-y", "", stats_line)
    page.append_log("wf-y", "", human_line)

    global_view = getattr(page._log_tabs, "_global_view", None)
    assert global_view is not None and hasattr(global_view, "toPlainText")
    text = global_view.toPlainText()
    assert "hello human readable" in text
    assert "[hve:stats]" not in text

    # _log_pane （ファイル永続化用）にも混入しない
    log_pane_text = page._log_pane.log_view.toPlainText()
    assert "hello human readable" in log_pane_text
    assert "[hve:stats]" not in log_pane_text


def test_t3_stats_tool_invoked_updates_footer_state(qapp):
    """T3: stats tool_invoked が Footer 用 state（tool 集計）を更新する（F2）。"""
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    _seed_instance(page, "wf-z", step_id="2.2")
    # tool_counts_by_step は step_id ごとの dict[tool_name -> int]
    before = dict(page._state.tool_counts_by_step.get("2.2", {}))

    page.append_log("wf-z", "", _stats_tool_invoked_line("2.2", "view"))
    page.append_log("wf-z", "", _stats_tool_invoked_line("2.2", "edit"))

    after = page._state.tool_counts_by_step.get("2.2", {})
    assert after.get("view", 0) == before.get("view", 0) + 1
    assert after.get("edit", 0) == before.get("edit", 0) + 1


def test_t4_update_workflow_instance_status_running_sets_started_at(qapp):
    """T4: 公開 API で running 化すると started_at が set される（F3a）。"""
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    _seed_instance(page, "wf-a")
    inst = page._state.workflows["wf-a"]
    assert inst.started_at is None
    assert inst.status == "pending"

    page.update_workflow_instance_status("wf-a", "running")

    inst = page._state.workflows["wf-a"]
    assert inst.status == "running"
    assert inst.started_at is not None
    assert inst.finished_at is None


def test_t5_mark_finished_done_sets_finished_at(qapp):
    """T5: 公開 API で finished 化（rc=0）すると status=done / finished_at set（F3b）。"""
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    _seed_instance(page, "wf-b")
    page.update_workflow_instance_status("wf-b", "running")

    page.mark_workflow_instance_finished("wf-b", 0)

    inst = page._state.workflows["wf-b"]
    assert inst.status == "done"
    assert inst.finished_at is not None


def test_t6_mark_finished_nonzero_sets_failed(qapp):
    """T6: 公開 API で finished 化（rc!=0）すると status=failed（F3b 失敗系）。"""
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    _seed_instance(page, "wf-c")
    page.update_workflow_instance_status("wf-c", "running")

    page.mark_workflow_instance_finished("wf-c", 2)

    inst = page._state.workflows["wf-c"]
    assert inst.status == "failed"
    assert inst.finished_at is not None
    assert inst.returncode == 2


def test_t7_public_api_safe_for_unknown_instance(qapp):
    """T7: 未登録 instance_id / 無効 status への公開 API 呼び出しはエラーを送出しない。"""
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    # 未登録 instance: 例外を投げずに無視されること
    page.update_workflow_instance_status("not-registered", "running")
    page.mark_workflow_instance_finished("not-registered", 0)
    assert "not-registered" not in page._state.workflows

    # 無効 status: ValueError を握り潰して例外を投げないこと
    _seed_instance(page, "wf-valid")
    page.update_workflow_instance_status("wf-valid", "invalid-status")
    # status は変わらず pending のまま
    assert page._state.workflows["wf-valid"].status == "pending"


def test_t8_main_window_on_line_closure_no_filter(qapp):
    """T8: ``_create_autopilot_phase_window::_on_line`` クロージャが stats 行を
    破棄せず ``append_log`` に届けることの静的検証（F1' 回帰防止）。

    クロージャを直接取り出すのは難しいため、ソースコード上に旧フィルタ記述
    (`if is_stats_line(line): return`) が復活していないことと、`is_stats_line`
    import が main_window.py に存在しないことを grep ベースで確認する。
    """
    import pathlib

    here = pathlib.Path(__file__).resolve().parents[1] / "main_window.py"
    src = here.read_text(encoding="utf-8")
    # F1' で削除した旧フィルタパターンが復活していないこと
    assert "if is_stats_line(line): return" not in src
    assert "if is_stats_line(line):\n            return" not in src
    # is_stats_line import が不要になっていること
    assert "from .workbench_logger import is_stats_line" not in src


# ---------------------------------------------------------------------------
# Fanout child step_status / fanout_init propagation
# (Issue: GUI Workbench Autopilot 経路で fan-out 子イベントが base step へ反映されない)
# ---------------------------------------------------------------------------


def _seed_instance_with_step(page, instance_id: str, step_id: str) -> None:
    """fanout テスト用に instance と base step を Instances 木へ事前登録する。"""
    from hve.gui.workbench_state import WorkflowInstanceSeed

    page.prepopulate_workflow_instances(
        [
            WorkflowInstanceSeed(
                instance_id=instance_id,
                workflow_id=instance_id.split("#", 1)[0],
                label=instance_id,
                app_id=None,
                steps=[(step_id, f"Step {step_id}")],
            )
        ]
    )


def test_fanout_init_seeds_child_subtasks_under_base(qapp):
    """(a) fanout_init で base step 配下に kind=fanout_child の子が seed される。"""
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    inst_id = "aad-web#APP-02"
    _seed_instance_with_step(page, inst_id, "2.3")

    page.append_log(
        inst_id, "", _stats_fanout_init_line("2.3", ["2.3/SVC-14", "2.3/SVC-15"])
    )

    base = page._state.find_step_in_instance(inst_id, "2.3")
    assert base is not None
    fanout_kids = [c for c in base.children if getattr(c, "kind", "") == "fanout_child"]
    assert {c.id for c in fanout_kids} == {"2.3/SVC-14", "2.3/SVC-15"}
    assert all(c.status == "pending" for c in fanout_kids)
    # _fanout_initialized に base が登録される
    assert "2.3" in page._fanout_initialized.get(inst_id, set())


def test_fanout_child_running_marks_base_running(qapp):
    """(b) fanout_init 後に子 running を投入すると base step が running になる。

    スクリーンショットの「ログは 2.3/SVC-14 を実行中だが作業状況は step 1 のみ
    タイマー進行」現象の回帰防止。
    """
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    inst_id = "aad-web#APP-02"
    _seed_instance_with_step(page, inst_id, "2.3")

    page.append_log(
        inst_id, "", _stats_fanout_init_line("2.3", ["2.3/SVC-14", "2.3/SVC-15"])
    )
    page.append_log(inst_id, "", _stats_step_status_line("2.3/SVC-14", "running"))

    base = page._state.find_step_in_instance(inst_id, "2.3")
    assert base is not None
    assert base.status == "running"
    assert base.started_at is not None
    child = page._state.find_step_in_instance(inst_id, "2.3/SVC-14")
    assert child is not None and child.status == "running"


def test_fanout_all_children_done_aggregates_base_done(qapp):
    """(c) fanout_init 後、全 child が done になると base step も done に集約される。"""
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    inst_id = "aad-web#APP-02"
    _seed_instance_with_step(page, inst_id, "2.3")

    page.append_log(
        inst_id, "", _stats_fanout_init_line("2.3", ["2.3/A", "2.3/B"])
    )
    page.append_log(inst_id, "", _stats_step_status_line("2.3/A", "done"))
    page.append_log(inst_id, "", _stats_step_status_line("2.3/B", "done"))

    base = page._state.find_step_in_instance(inst_id, "2.3")
    assert base is not None
    assert base.status == "done"
    assert base.finished_at is not None


def test_fanout_child_status_for_unknown_base_is_ignored(qapp):
    """(d) plan 外 base_id（state 未登録）への step_status は state を変更しない（捏造防止）。"""
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    inst_id = "aad-web#APP-02"
    _seed_instance_with_step(page, inst_id, "2.3")  # base="99" は未登録

    page.append_log(inst_id, "", _stats_step_status_line("99/X", "running"))

    # 既存 base "2.3" には影響なし
    base = page._state.find_step_in_instance(inst_id, "2.3")
    assert base is not None and base.status == "pending"
    # 未登録 base "99" は引き続き未登録
    assert page._state.find_step_in_instance(inst_id, "99") is None
    # 子も登録されない
    assert page._state.find_step_in_instance(inst_id, "99/X") is None


def test_fanout_child_done_without_init_does_not_complete_base(qapp):
    """(e) fanout_init 未受信時、child done だけでは base を done にしない（早期完了防止）。"""
    from hve.gui.page_workbench import WorkbenchPage

    page = WorkbenchPage()
    inst_id = "aad-web#APP-02"
    _seed_instance_with_step(page, inst_id, "2.3")

    # fanout_init を送らず、いきなり child done
    page.append_log(inst_id, "", _stats_step_status_line("2.3/A", "done"))

    base = page._state.find_step_in_instance(inst_id, "2.3")
    assert base is not None
    # base は pending のまま（fanout_init 不在のため早期完了させない）
    assert base.status == "pending"
    # 子は seed されている
    child = page._state.find_step_in_instance(inst_id, "2.3/A")
    assert child is not None and child.status == "done"
