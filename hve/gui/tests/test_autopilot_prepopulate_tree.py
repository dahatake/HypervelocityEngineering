"""Issue tree-unification Phase 1 / Q4=A / Q14=a:

`MainWindow._build_autopilot_workflow_seeds` と
`WorkbenchPage.prepopulate_workflow_instances` が
``AutopilotPlan`` 全体（pre_phases + app_chains + main_workflows）を
``WorkbenchState.workflows`` に pending 状態で事前登録することを検証する。

これにより Step 1 で選択した全ワークフローが、Autopilot 実行開始直後から
Step 2 ツリーに pending 状態で並ぶ。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from hve.autopilot.plan_model import AppChain, AutopilotPlan
from hve.gui.main_window import MainWindow
from hve.gui.workbench_state import WorkbenchState, WorkflowInstanceSeed


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _make_plan(*, pre_phases=None, app_chains=None, main_workflows=None) -> AutopilotPlan:
    return AutopilotPlan(
        catalog_path=__import__("pathlib").Path("/tmp/catalog.md"),
        catalog_exists=True,
        requires_aas=False,
        app_chains=list(app_chains or []),
        skipped=[],
        max_parallel=4,
        pre_phases=list(pre_phases or []),
        main_workflows=list(main_workflows or []),
        ignored_workflows=[],
        pre_phase_only=False,
    )


def _bare_main_window() -> MainWindow:
    """`__init__` をスキップした最小 MainWindow。"""
    return MainWindow.__new__(MainWindow)


# ---------------------------------------------------------------------------
# _build_autopilot_workflow_seeds: 命名規約と順序
# ---------------------------------------------------------------------------


def test_seeds_pre_phases_use_workflow_id_only(qapp):
    """pre_phases (ARD/AAS) は instance_id = workflow_id (app_id なし)。"""
    mw = _bare_main_window()
    plan = _make_plan(pre_phases=["ard", "aas"])
    seeds = mw._build_autopilot_workflow_seeds(plan)

    ids = [s.instance_id for s in seeds]
    assert ids == ["ard", "aas"]
    for s in seeds:
        assert s.app_id is None
        assert s.workflow_id == s.instance_id


def test_seeds_app_chains_use_workflow_hash_app_id(qapp):
    """app_chains は instance_id = f'{workflow_id}#{app_id}' (Q14=a)。"""
    mw = _bare_main_window()
    plan = _make_plan(
        app_chains=[
            AppChain(app_id="APP-01", architecture="web-cloud",
                     workflows=["aad-web", "asdw-web"]),
            AppChain(app_id="APP-02", architecture="dataflow",
                     workflows=["abd"]),
        ]
    )
    seeds = mw._build_autopilot_workflow_seeds(plan)

    ids = [s.instance_id for s in seeds]
    assert ids == ["aad-web#APP-01", "asdw-web#APP-01", "abd#APP-02"]

    s0 = seeds[0]
    assert s0.workflow_id == "aad-web"
    assert s0.app_id == "APP-01"
    assert s0.label == "aad-web (APP-01)"


def test_seeds_execution_order_pre_then_chains(qapp):
    """Q5=A: pre_phases → main_workflows → app_chains の順で並ぶ。"""
    mw = _bare_main_window()
    plan = _make_plan(
        pre_phases=["ard"],
        main_workflows=[],
        app_chains=[
            AppChain(app_id="APP-01", architecture="web",
                     workflows=["aad-web"]),
        ],
    )
    seeds = mw._build_autopilot_workflow_seeds(plan)
    assert [s.instance_id for s in seeds] == ["ard", "aad-web#APP-01"]


def test_seeds_dedupes_overlapping_workflow_ids(qapp):
    """main_workflows と pre_phases に同じ workflow_id があれば 1 件のみ。"""
    mw = _bare_main_window()
    plan = _make_plan(pre_phases=["ard"], main_workflows=["ard"])
    seeds = mw._build_autopilot_workflow_seeds(plan)
    assert [s.instance_id for s in seeds] == ["ard"]


def test_seeds_steps_populated_from_workflow_registry(qapp):
    """seed.steps は WorkflowDef.steps の階層構造（StepSeed）で充填される。

    Phase 2 (Q3=B): container Step は親ノードとして展開され、非 container Step は
    container 配下に StepSeed.children として配置される。
    """
    from hve.gui.workbench_state import StepSeed

    mw = _bare_main_window()
    plan = _make_plan(pre_phases=["ard"])
    seeds = mw._build_autopilot_workflow_seeds(plan)
    # ard ワークフローは実在し、何らかの Step を持つ
    assert len(seeds) == 1
    assert isinstance(seeds[0].steps, list)
    assert len(seeds[0].steps) >= 1
    # 各エントリは StepSeed
    first = seeds[0].steps[0]
    assert isinstance(first, StepSeed)
    assert isinstance(first.id, str) and first.id
    assert isinstance(first.title, str)
    assert first.kind in ("step", "container", "subagent", "fanout_child")


# ---------------------------------------------------------------------------
# _prepopulate_workbench_with_seeds: WorkbenchPage 連携
# ---------------------------------------------------------------------------


def test_prepopulate_helper_calls_page_workbench_api(qapp):
    mw = _bare_main_window()
    mw._page_workbench = MagicMock()
    seeds = [WorkflowInstanceSeed("ard", "ard", "ard", None, [])]

    mw._prepopulate_workbench_with_seeds(seeds)

    mw._page_workbench.prepopulate_workflow_instances.assert_called_once_with(seeds)


def test_prepopulate_helper_no_op_on_empty_seeds(qapp):
    mw = _bare_main_window()
    mw._page_workbench = MagicMock()
    mw._prepopulate_workbench_with_seeds([])
    mw._page_workbench.prepopulate_workflow_instances.assert_not_called()


def test_prepopulate_helper_swallows_attr_error_for_old_workbench(qapp):
    """古い WorkbenchPage 実装 (API 未提供) でも例外を投げない。"""
    mw = _bare_main_window()
    legacy = MagicMock(spec=[])  # prepopulate_workflow_instances 属性なし
    mw._page_workbench = legacy
    # 例外を投げないこと
    mw._prepopulate_workbench_with_seeds(
        [WorkflowInstanceSeed("ard", "ard", "ard", None, [])]
    )


# ---------------------------------------------------------------------------
# WorkbenchPage.prepopulate_workflow_instances 統合
# ---------------------------------------------------------------------------


def test_workbench_state_population_reflects_seeds(qapp):
    """DagStatusWidget へ移行後、WorkbenchState の pre-population が
    ``update_workflow_instances`` 経由で全 instance を描画対象に取り込むこと。"""
    from hve.gui.widgets.dag_status_widget import DagStatusWidget

    state = WorkbenchState(workflow_id="root", run_id="run1", model="test")
    seeds = [
        WorkflowInstanceSeed("ard", "ard", "ard", None, [("s1", "T1")]),
        WorkflowInstanceSeed("aas", "aas", "aas", None, []),
        WorkflowInstanceSeed(
            "aad-web#APP-01", "aad-web", "aad-web (APP-01)", "APP-01",
            [("ui", "UI 設計")],
        ),
    ]
    state.prepopulate_workflow_instances(seeds)

    widget = DagStatusWidget()
    widget.update_workflow_instances(state)

    # 3 instance がエントリ化されていること
    assert len(widget._entries) == 3
    labels = [e.label for e in widget._entries]
    assert any("ard" in t for t in labels)
    assert any("aas" in t for t in labels)
    assert any("aad-web (APP-01)" in t for t in labels)
