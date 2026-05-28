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


# ---------------------------------------------------------------------------
# T6 (gui-workbench-fanout-tree): Fan-out 子ノードの階層型 DAG 表示
# ---------------------------------------------------------------------------


def _expand_step1_with_subs(w, subs):
    """Step "1" を Fan-out 扱いで展開した状態にして w を返すヘルパ。"""
    steps = [{"id": "1", "title": "T1", "depends_on": []}]
    w.set_plan(
        _plan("wf-a", steps),
        {"wf-a": "実行中"},
        {"wf-a": {"1": "実行中"}},
        subtask_status={"wf-a": {"1": subs}},
    )
    w._toggle_step_expand("wf-a", "1")
    # トグル後に再レイアウトを発火させて _child_items を構築させる
    w.set_plan(
        _plan("wf-a", steps),
        {"wf-a": "実行中"},
        {"wf-a": {"1": "実行中"}},
        subtask_status={"wf-a": {"1": subs}},
    )


def test_fanout_children_rendered_as_child_nodes(qapp):
    """展開時に `_FanoutChildNodeItem` が子数だけ scene へ追加される。"""
    from hve.gui.widgets.dag_status_widget import _FanoutChildNodeItem

    w = DagStatusWidget()
    subs = [
        ("1/UC-01", "ユースケース 1", "完了"),
        ("1/UC-02", "ユースケース 2", "実行中"),
        ("1/UC-03", "ユースケース 3", "待機"),
    ]
    _expand_step1_with_subs(w, subs)
    # _child_items が子数ぶん登録されている
    assert len(w._child_items) == 3
    for sid in ("1/UC-01", "1/UC-02", "1/UC-03"):
        assert ("wf-a", sid) in w._child_items
        assert isinstance(w._child_items[("wf-a", sid)], _FanoutChildNodeItem)
    w.deleteLater()


def test_fanout_child_node_has_label_and_tooltip(qapp):
    """子ノードの短縮ラベル表示・Tooltip 内容を検証。"""
    w = DagStatusWidget()
    subs = [("1/UC-01", "ユースケース 1: EC 会員登録", "実行中")]
    _expand_step1_with_subs(w, subs)
    child = w._child_items[("wf-a", "1/UC-01")]
    # Q2=A: 短縮ラベル `<key>` 部分のみ + ステータスグリフ
    assert "UC-01" in child._lbl_main.text()
    # Tooltip にフル ID とタイトル両方が含まれる
    tt = child.toolTip()
    assert "1/UC-01" in tt
    assert "EC 会員登録" in tt
    assert "running" in tt
    w.deleteLater()


def test_fanout_child_node_click_selects(qapp):
    """子ノードクリックで widget._select_node が呼ばれ選択遷移する。"""
    w = DagStatusWidget()
    subs = [("1/UC-01", "UC1", "実行中"), ("1/UC-02", "UC2", "待機")]
    _expand_step1_with_subs(w, subs)
    captured = []
    w.node_selected.connect(lambda iid, sid: captured.append((iid, sid)))
    child = w._child_items[("wf-a", "1/UC-01")]
    # 既存テスト test_node_click_emits_signal_with_step_id と同様に
    # _select_node を直接呼んでクリック相当を再現する。
    w._select_node(child.instance_id, child.child_id, child)
    assert captured == [("wf-a", "1/UC-01")]
    assert w._selected_node_item is child
    w.deleteLater()


def test_fanout_edges_drawn_from_parent_to_each_child(qapp):
    """Q4=B: 親 → 各子へエッジ (line アイテム) が描かれる。"""
    from PySide6.QtWidgets import QGraphicsLineItem

    w = DagStatusWidget()
    # 折りたたみ状態でのエッジ数を取得
    steps = [{"id": "1", "title": "T1", "depends_on": []}]
    subs = [("1/UC-01", "U1", "実行中"), ("1/UC-02", "U2", "実行中")]
    w.set_plan(
        _plan("wf-a", steps),
        {"wf-a": "実行中"},
        {"wf-a": {"1": "実行中"}},
        subtask_status={"wf-a": {"1": subs}},
    )
    base_lines = sum(
        1 for it in w._scene.items() if isinstance(it, QGraphicsLineItem)
    )
    # 単一ステップで depends_on も無いため、初期状態では DAG エッジ 0
    assert base_lines == 0
    # 展開して再描画
    _expand_step1_with_subs(w, subs)
    expanded_lines = sum(
        1 for it in w._scene.items() if isinstance(it, QGraphicsLineItem)
    )
    # _draw_fanout_edge は 1 エッジ = 3 線分 → 2 子 × 3 = 6 線分以上増える
    assert expanded_lines - base_lines >= 6
    w.deleteLater()


def test_fanout_children_wrap_into_multiple_rows(qapp):
    """Q6=A: viewport 幅に応じて複数行に折り返される。"""
    w = DagStatusWidget()
    # viewport 幅を意図的に狭く設定して折り返しを発生させる
    w._view.setFixedWidth(200)
    w._view.viewport().setFixedWidth(200 - 24)  # margin 込みで十分狭く
    subs = [(f"1/UC-{i:02d}", f"U{i}", "実行中") for i in range(1, 7)]  # 6 子
    _expand_step1_with_subs(w, subs)
    ys = {
        sid: w._child_items[("wf-a", sid)].y()
        for sid, _, _ in subs
    }
    # 狭い viewport では複数 Y 値（= 複数行）に分散すること
    assert len(set(ys.values())) >= 2, (
        f"狭い viewport で折り返しが発生しなかった: ys={ys}"
    )
    w.deleteLater()

