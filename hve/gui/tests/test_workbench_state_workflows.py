"""Wave 1 (gui-unified-workbench): WorkflowInstance helpers の最小テスト。"""
from __future__ import annotations

import pytest

# QApplication が必要（Signal 利用のため）
PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.workbench_state import WorkbenchState, WorkflowInstance  # noqa: E402
from hve.gui.workbench_state import WorkflowInstanceSeed  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _new_state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf-root", run_id="run-1", model="test")


def test_ensure_creates_and_is_idempotent(qapp):
    s = _new_state()
    a = s.ensure_workflow_instance("wf-a", "wf-a", "WF-A")
    b = s.ensure_workflow_instance("wf-a", "wf-a", "WF-A-changed")
    assert isinstance(a, WorkflowInstance)
    assert a is b  # 同 instance を返す
    assert a.label == "WF-A"  # 上書きされない
    assert list(s.workflows.keys()) == ["wf-a"]


def test_append_log_routes_to_step_and_global(qapp):
    s = _new_state()
    s.ensure_workflow_instance("wf-a#APP-01", "wf-a", "WF-A", app_id="APP-01")
    s.append_workflow_log("wf-a#APP-01", "step1", "hello")
    s.append_workflow_log("wf-a#APP-01", None, "global-only")
    s.append_workflow_log("missing", "step1", "ignored")  # no-op

    inst = s.workflows["wf-a#APP-01"]
    assert inst.log_buffer == ["hello", "global-only"]
    assert inst.step_log_buffers == {"step1": ["hello"]}


def test_mark_finished_sets_status_by_returncode(qapp):
    s = _new_state()
    s.ensure_workflow_instance("wf-ok", "wf-ok", "OK")
    s.ensure_workflow_instance("wf-ng", "wf-ng", "NG")
    s.mark_workflow_instance_finished("wf-ok", 0)
    s.mark_workflow_instance_finished("wf-ng", 1)
    assert s.workflows["wf-ok"].status == "done"
    assert s.workflows["wf-ok"].finished_at is not None
    assert s.workflows["wf-ng"].status == "failed"
    assert s.workflows["wf-ng"].returncode == 1


def test_update_status_validates(qapp):
    s = _new_state()
    s.ensure_workflow_instance("x", "x", "X")
    s.update_workflow_instance_status("x", "running")
    assert s.workflows["x"].status == "running"
    assert s.workflows["x"].started_at is not None
    with pytest.raises(ValueError):
        s.update_workflow_instance_status("x", "bogus")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Issue tree-unification Phase 1 / Q4=A / Q14=a:
# WorkbenchState.prepopulate_workflow_instances
# ---------------------------------------------------------------------------


def test_prepopulate_creates_all_instances_in_seed_order(qapp):
    """seed の順序通りに ``workflows`` (OrderedDict) に並ぶこと。"""
    s = _new_state()
    seeds = [
        WorkflowInstanceSeed("ard", "ard", "ard", None, [("step1", "Step 1")]),
        WorkflowInstanceSeed("aas", "aas", "aas", None, []),
        WorkflowInstanceSeed(
            "aad-web#APP-01",
            "aad-web",
            "aad-web (APP-01)",
            "APP-01",
            [("ui-list", "画面一覧"), ("ui-detail", "画面詳細")],
        ),
    ]
    s.prepopulate_workflow_instances(seeds)

    assert list(s.workflows.keys()) == ["ard", "aas", "aad-web#APP-01"]
    assert s.workflows["ard"].status == "pending"
    assert s.workflows["aad-web#APP-01"].app_id == "APP-01"
    assert s.workflows["aad-web#APP-01"].workflow_id == "aad-web"
    assert s.workflows["aad-web#APP-01"].label == "aad-web (APP-01)"


def test_prepopulate_populates_step_views_in_order(qapp):
    """各 instance.steps が seed の (step_id, title) 順に StepView pending で並ぶ。"""
    s = _new_state()
    s.prepopulate_workflow_instances(
        [
            WorkflowInstanceSeed(
                "ard",
                "ard",
                "ard",
                None,
                [("ard-step1", "事業分析"), ("ard-step2", "ユースケース")],
            )
        ]
    )
    inst = s.workflows["ard"]
    assert list(inst.steps.keys()) == ["ard-step1", "ard-step2"]
    assert inst.steps["ard-step1"].title == "事業分析"
    assert inst.steps["ard-step1"].status == "pending"
    assert inst.steps["ard-step2"].status == "pending"


def test_prepopulate_is_idempotent_skips_existing(qapp):
    """既存 instance_id があれば上書きせずスキップする（冪等）。"""
    s = _new_state()
    seeds_v1 = [WorkflowInstanceSeed("ard", "ard", "label-v1", None, [])]
    seeds_v2 = [WorkflowInstanceSeed("ard", "ard", "label-v2", None, [("s1", "T1")])]
    s.prepopulate_workflow_instances(seeds_v1)
    s.prepopulate_workflow_instances(seeds_v2)

    inst = s.workflows["ard"]
    assert inst.label == "label-v1"  # 上書きされない
    assert list(inst.steps.keys()) == []  # steps も上書きされない


def test_prepopulate_empty_seeds_is_noop(qapp):
    s = _new_state()
    s.prepopulate_workflow_instances([])
    assert list(s.workflows.keys()) == []


def test_prepopulate_emits_workflow_instance_changed(qapp):
    """各 instance 登録ごとに workflow_instance_changed signal を emit する。"""
    s = _new_state()
    captured: list = []
    s.signals().workflow_instance_changed.connect(captured.append)
    s.prepopulate_workflow_instances(
        [
            WorkflowInstanceSeed("ard", "ard", "ard", None, []),
            WorkflowInstanceSeed("aas", "aas", "aas", None, []),
        ]
    )
    assert captured == ["ard", "aas"]
