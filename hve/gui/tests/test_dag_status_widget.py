"""``DagStatusWidget`` の基本的なユニットテスト。

PySide6 が未導入の環境ではスキップする。
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.widgets.dag_status_widget import DagStatusWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _plan(workflow_id: str, steps: list[dict]) -> list[dict]:
    return [
        {
            "workflow_id": workflow_id,
            "workflow_name": f"WF-{workflow_id}",
            "steps": steps,
        }
    ]


def test_set_plan_populates_entries(qapp):
    w = DagStatusWidget()
    steps = [
        {"id": "1", "title": "準備", "depends_on": []},
        {"id": "2", "title": "分析", "depends_on": ["1"]},
        {"id": "3", "title": "設計", "depends_on": ["2"]},
    ]
    w.set_plan(_plan("wf-a", steps), {"wf-a": "実行中"}, {"wf-a": {"2": "実行中"}})
    assert len(w._entries) == 1
    entry = w._entries[0]
    assert entry.instance_id == "wf-a"
    assert entry.status == "running"
    assert [s["id"] for s in entry.steps] == ["1", "2", "3"]
    # 内部 status 正規化
    assert entry.steps[1]["status"] == "running"
    # シーンにノードが追加されている
    assert ("wf-a", "1") in w._step_items
    assert ("wf-a", "2") in w._step_items
    w.deleteLater()


def test_node_click_emits_signal_with_step_id(qapp):
    w = DagStatusWidget()
    steps = [{"id": "1", "title": "T1", "depends_on": []}]
    w.set_plan(_plan("wf-a", steps), {"wf-a": "実行中"}, {"wf-a": {}})
    received = []
    w.node_selected.connect(lambda iid, sid: received.append((iid, sid)))
    node = w._step_items[("wf-a", "1")]
    # internal helper を直接呼んでクリック相当を再現
    w._select_node("wf-a", "1", node)
    assert received == [("wf-a", "1")]
    w.deleteLater()


def test_workflow_header_click_emits_empty_step_id(qapp):
    w = DagStatusWidget()
    steps = [{"id": "1", "title": "T1", "depends_on": []}]
    w.set_plan(_plan("wf-a", steps), {"wf-a": "実行中"}, {"wf-a": {}})
    received = []
    w.node_selected.connect(lambda iid, sid: received.append((iid, sid)))
    header = w._wf_items["wf-a"]
    w._select_node("wf-a", "", header)
    assert received == [("wf-a", "")]
    w.deleteLater()


def test_workflow_collapse_hides_step_nodes(qapp):
    w = DagStatusWidget()
    steps = [{"id": "1", "title": "T1", "depends_on": []}]
    w.set_plan(_plan("wf-a", steps), {"wf-a": "実行中"}, {"wf-a": {}})
    # 展開状態: Step ノードあり
    assert ("wf-a", "1") in w._step_items
    # トグル → 折りたたみ後は Step ノードがシーンに無い
    w._toggle_workflow("wf-a")
    assert w._is_workflow_expanded("wf-a") is False
    assert ("wf-a", "1") not in w._step_items
    # 再トグル → 復帰
    w._toggle_workflow("wf-a")
    assert ("wf-a", "1") in w._step_items
    w.deleteLater()


def test_reset_clears_entries(qapp):
    w = DagStatusWidget()
    steps = [{"id": "1", "title": "T1", "depends_on": []}]
    w.set_plan(_plan("wf-a", steps), {"wf-a": ""}, {"wf-a": {}})
    assert w._entries
    w.reset()
    assert w._entries == []
    assert w._step_items == {}
    assert w._wf_items == {}
    w.deleteLater()


def test_step_fanout_expand_persists_across_relayout(qapp):
    """Fanout を持つ Step のダブルクリック展開状態が再レイアウト後も維持される。"""
    w = DagStatusWidget()
    steps = [{"id": "1", "title": "T1", "depends_on": []}]
    # subtask_status を 1 件持たせて Fanout 扱いにする
    w.set_plan(
        _plan("wf-a", steps),
        {"wf-a": "実行中"},
        {"wf-a": {"1": "実行中"}},
        subtask_status={"wf-a": {"1": [("sub-1", "Subtask 1", "実行中")]}},
    )
    # 初期は折りたたみ
    assert w._is_step_expanded("wf-a", "1") is False
    # 展開
    w._toggle_step_expand("wf-a", "1")
    assert w._is_step_expanded("wf-a", "1") is True
    # 再レイアウト（status 更新を模倣）してもフラグが保持される
    w.set_plan(
        _plan("wf-a", steps),
        {"wf-a": "完了"},
        {"wf-a": {"1": "完了"}},
        subtask_status={"wf-a": {"1": [("sub-1", "Subtask 1", "完了")]}},
    )
    assert w._is_step_expanded("wf-a", "1") is True
    # 再度トグル → 折りたたみ
    w._toggle_step_expand("wf-a", "1")
    assert w._is_step_expanded("wf-a", "1") is False
    # reset() でクリア
    w.set_plan(
        _plan("wf-a", steps),
        {"wf-a": "実行中"},
        {"wf-a": {"1": "実行中"}},
        subtask_status={"wf-a": {"1": [("sub-1", "Subtask 1", "実行中")]}},
    )
    w._toggle_step_expand("wf-a", "1")
    assert w._is_step_expanded("wf-a", "1") is True
    w.reset()
    assert w._is_step_expanded("wf-a", "1") is False
    w.deleteLater()
