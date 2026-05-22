"""gui-workbench-autopilot-display: Autopilot 経路の Workbench 表示回帰テスト。

T1〜T5 を以下の純ロジック単位で検証する:

- T6.1 _merge_seeds_into_workflow_plan の純関数挙動
- T6.2 prepopulate_workflow_instances 後に Header1 plan が反映される
- T6.3 update_identity_from_session で state.run_id が更新される
- T6.4 placeholder seed が追加できる（chain_continuation 経路の事前表示）
- T6.5 remove_workflow_instance で placeholder が削除される
- T6.6 step_id "1.1" の running ログでステータスが反映される
- T6.7 step_id "4" の running ログで container step が反映される
"""

from __future__ import annotations

import json
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.page_workbench import WorkbenchPage  # noqa: E402
from hve.gui.workbench_state import (  # noqa: E402
    StepSeed,
    WorkflowInstanceSeed,
)


@pytest.fixture(scope="module")
def _qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def page(_qapp):
    """WorkbenchPage を生成し、teardown で QTimer を停止してリークを防ぐ。

    レビュー #9: 500ms 周期 _update_timer が tests 終了後も走り続けないように停止する。
    """
    from hve.gui.page_workbench import WorkbenchPage

    p = WorkbenchPage()
    yield p
    try:
        if hasattr(p, "_update_timer"):
            p._update_timer.stop()
    except RuntimeError:
        pass
    try:
        p.deleteLater()
    except RuntimeError:
        pass


def _make_seed(
    workflow_id: str,
    instance_id: str = None,
    app_id: str = None,
    steps=None,
) -> WorkflowInstanceSeed:
    return WorkflowInstanceSeed(
        instance_id=instance_id or workflow_id,
        workflow_id=workflow_id,
        label=workflow_id,
        app_id=app_id,
        steps=steps or [],
    )


# ----------------------------------------------------------------------
# T6.1: _merge_seeds_into_workflow_plan 純関数
# ----------------------------------------------------------------------


def test_merge_seeds_into_workflow_plan_new(_qapp):
    page = WorkbenchPage()
    seeds = [
        _make_seed("ard"),
        _make_seed("aas"),
        _make_seed("aad-web"),
    ]
    merged = page._merge_seeds_into_workflow_plan(seeds)
    assert [wf["workflow_id"] for wf in merged] == ["ard", "aas", "aad-web"]


def test_merge_seeds_dedup_existing(_qapp):
    page = WorkbenchPage()
    page._workflow_plan = [{"workflow_id": "ard", "workflow_name": "ARD", "steps": []}]
    merged = page._merge_seeds_into_workflow_plan(
        [_make_seed("ard"), _make_seed("aas")]
    )
    ids = [wf["workflow_id"] for wf in merged]
    # 既存 ard は重複追加されない
    assert ids == ["ard", "aas"]


def test_merge_seeds_dedup_same_workflow_diff_app(_qapp):
    page = WorkbenchPage()
    merged = page._merge_seeds_into_workflow_plan(
        [
            _make_seed("aad-web", instance_id="aad-web#APP-01", app_id="APP-01"),
            _make_seed("aad-web", instance_id="aad-web#APP-02", app_id="APP-02"),
        ]
    )
    ids = [wf["workflow_id"] for wf in merged]
    # workflow_id 単位に集約される
    assert ids == ["aad-web"]


# ----------------------------------------------------------------------
# T6.2: prepopulate_workflow_instances 後の workflow plan 反映
# ----------------------------------------------------------------------


def test_prepopulate_pushes_plan(_qapp):
    page = WorkbenchPage()
    seeds = [_make_seed("ard"), _make_seed("aas")]
    page.prepopulate_workflow_instances(seeds)
    plan = page._workflow_plan
    assert plan is not None and len(plan) >= 2
    ids = [str(wf.get("workflow_id", "")) for wf in plan]
    assert "ard" in ids and "aas" in ids


# ----------------------------------------------------------------------
# T6.3: update_identity_from_session
# ----------------------------------------------------------------------


def test_update_identity_from_session_sets_run_id(_qapp):
    page = WorkbenchPage()
    page.update_identity_from_session("20260520T010203-abc123")
    assert page._state.run_id == "20260520T010203-abc123"


def test_update_identity_from_session_ignores_empty(_qapp):
    page = WorkbenchPage()
    original = page._state.run_id
    page.update_identity_from_session("")
    page.update_identity_from_session(None)
    assert page._state.run_id == original


# ----------------------------------------------------------------------
# T6.4 / T6.5: placeholder seed と削除
# ----------------------------------------------------------------------


def test_placeholder_then_replace(_qapp):
    page = WorkbenchPage()
    # placeholder 投入
    page.prepopulate_workflow_instances(
        [_make_seed("aad-web")]  # instance_id = "aad-web"
    )
    assert "aad-web" in page._state.workflows
    # placeholder 削除
    page.remove_workflow_instance("aad-web")
    assert "aad-web" not in page._state.workflows
    # 本 seed (wf#app) を再投入
    page.prepopulate_workflow_instances(
        [_make_seed("aad-web", instance_id="aad-web#APP-01", app_id="APP-01")]
    )
    assert "aad-web#APP-01" in page._state.workflows


def test_remove_unknown_instance_is_noop(_qapp):
    page = WorkbenchPage()
    # 例外を出さず no-op
    page.remove_workflow_instance("nonexistent")
    page.remove_workflow_instance("")


# ----------------------------------------------------------------------
# T6.6 / T6.7: step_id 解決と bubble-up
# ----------------------------------------------------------------------


def _seed_with_steps(workflow_id: str, instance_id: str) -> WorkflowInstanceSeed:
    """container "4" 配下に "4.1" / "4.3" を持つ seed を生成。"""
    return WorkflowInstanceSeed(
        instance_id=instance_id,
        workflow_id=workflow_id,
        label=workflow_id,
        app_id=None,
        steps=[
            StepSeed(id="1", title="Step 1", kind="step"),
            StepSeed(
                id="4",
                title="Step 4",
                kind="container",
                children=[
                    StepSeed(id="4.1", title="Step 4.1", kind="step"),
                    StepSeed(id="4.3", title="Step 4.3", kind="step"),
                ],
            ),
        ],
    )


def _stats_line(step: str, status: str) -> str:
    payload = {"kind": "step_status", "step": step, "status": status}
    return f'[hve:stats] {json.dumps(payload)}'


def test_apply_step_status_direct_hit(_qapp):
    page = WorkbenchPage()
    page.prepopulate_workflow_instances(
        [_seed_with_steps("ard", instance_id="ard")]
    )
    page._apply_log_line_to_instance_tree("ard", _stats_line("4.3", "running"))
    node = page._state.find_step_in_instance("ard", "4.3")
    assert node is not None
    assert node.status == "running"


def test_apply_step_status_bubble_up(_qapp):
    """seed に存在しない "1.1" を受けたら親 "1" にフォールバックする (T4)。"""
    page = WorkbenchPage()
    page.prepopulate_workflow_instances(
        [_seed_with_steps("ard", instance_id="ard")]
    )
    page._apply_log_line_to_instance_tree("ard", _stats_line("1.1", "running"))
    parent = page._state.find_step_in_instance("ard", "1")
    assert parent is not None
    assert parent.status == "running"


def test_apply_step_status_container_direct(_qapp):
    """container step "4" の running イベントが反映される (T4)。"""
    page = WorkbenchPage()
    page.prepopulate_workflow_instances(
        [_seed_with_steps("ard", instance_id="ard")]
    )
    page._apply_log_line_to_instance_tree("ard", _stats_line("4", "running"))
    node = page._state.find_step_in_instance("ard", "4")
    assert node is not None
    assert node.status == "running"


def test_apply_step_status_step_prefix_stripped(_qapp):
    """`Step.4.3` prefix が除去されてヒットすること (T4 二重防御)。"""
    page = WorkbenchPage()
    page.prepopulate_workflow_instances(
        [_seed_with_steps("ard", instance_id="ard")]
    )
    page._apply_log_line_to_instance_tree("ard", _stats_line("Step.4.3", "done"))
    node = page._state.find_step_in_instance("ard", "4.3")
    assert node is not None
    assert node.status == "done"


# ----------------------------------------------------------------------
# T5: running 検知時の current_workflow_id 強調更新
# ----------------------------------------------------------------------


def test_highlight_running_workflow_on_first_running(_qapp):
    page = WorkbenchPage()
    page.prepopulate_workflow_instances(
        [_seed_with_steps("ard", "ard"), _seed_with_steps("aas", "aas")]
    )
    assert page._current_workflow_id is None
    page._apply_log_line_to_instance_tree("aas", _stats_line("1", "running"))
    assert page._current_workflow_id == "aas"


def test_highlight_running_workflow_switches_between_workflows(_qapp):
    page = WorkbenchPage()
    page.prepopulate_workflow_instances(
        [_seed_with_steps("ard", "ard"), _seed_with_steps("aas", "aas")]
    )
    page._apply_log_line_to_instance_tree("ard", _stats_line("1", "running"))
    assert page._current_workflow_id == "ard"
    page._apply_log_line_to_instance_tree("aas", _stats_line("1", "running"))
    assert page._current_workflow_id == "aas"


# ----------------------------------------------------------------------
# レビュー追加: #2 / #13 / Critical #1
# ----------------------------------------------------------------------


def test_merge_seeds_uses_empty_workflow_name_to_let_registry_resolve(_qapp):
    """レビュー #2: app_chains seed の label が "wf (APP)" 形式でも、
    Header1 の workflow_name は空文字で渡され registry/template_engine 側で
    正式名に解決される。
    """
    page = WorkbenchPage()
    seed = WorkflowInstanceSeed(
        instance_id="aad-web#APP-01",
        workflow_id="aad-web",
        label="aad-web (APP-01)",  # label に app_id が混ざるケース
        app_id="APP-01",
        steps=[],
    )
    merged = page._merge_seeds_into_workflow_plan([seed])
    assert len(merged) == 1
    # workflow_name は空文字。Header1 側で registry resolve される設計。
    assert merged[0]["workflow_name"] == ""
    assert merged[0]["workflow_id"] == "aad-web"


def test_highlight_running_workflow_stable_for_repeated_running(_qapp):
    """レビュー #13: 同一 workflow 内で複数 step が連続 running になっても
    _current_workflow_id は最初の workflow_id を維持する。
    """
    page = WorkbenchPage()
    page.prepopulate_workflow_instances(
        [_seed_with_steps("ard", "ard"), _seed_with_steps("aas", "aas")]
    )
    page._apply_log_line_to_instance_tree("ard", _stats_line("1", "running"))
    assert page._current_workflow_id == "ard"
    # 同じ ard 内で別 step が running に
    page._apply_log_line_to_instance_tree("ard", _stats_line("4", "running"))
    page._apply_log_line_to_instance_tree("ard", _stats_line("4.3", "running"))
    assert page._current_workflow_id == "ard"


def test_reset_for_autopilot_clears_state(_qapp):
    """Critical #1: reset_for_autopilot が _workflow_plan / _current_workflow_id /
    state.workflows をクリアする。
    """
    page = WorkbenchPage()
    page.prepopulate_workflow_instances([_make_seed("ard"), _make_seed("aas")])
    page._apply_log_line_to_instance_tree(
        "ard",
        _stats_line("1", "running"),
    )
    # 事前条件: 状態が入っている
    assert page._workflow_plan, "前提: _workflow_plan に seed が反映されている"
    assert "ard" in page._state.workflows
    # reset 実行
    page.reset_for_autopilot()
    # 事後条件: 全クリア
    assert page._workflow_plan == []
    assert page._current_workflow_id is None
    assert len(page._state.workflows) == 0
