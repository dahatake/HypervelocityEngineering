"""``DagStatusWidget`` の基本的なユニットテスト。

PySide6 が未導入の環境ではスキップする。
"""
from __future__ import annotations

import time
from types import SimpleNamespace

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


def test_freeze_elapsed_keeps_summary_at_job_end_time(qapp, monkeypatch):
    """ジョブ終了後は作業状況サマリーの経過時間が増え続けない。"""
    now = 100.0
    monkeypatch.setattr(time, "monotonic", lambda: now)
    w = DagStatusWidget()
    steps = [{"id": "1", "title": "T1", "depends_on": []}]
    w.set_plan(
        _plan("wf-a", steps),
        {"wf-a": "実行中"},
        {"wf-a": {"1": "実行中"}},
    )

    now = 112.0
    w.freeze_elapsed()
    assert "[00:00:12]" in w._summary_label.text()

    # 完了後にサマリーを再計算しても、終了時刻で固定される。
    now = 3600.0
    w._update_summary_label()
    assert "[00:00:12]" in w._summary_label.text()
    w.deleteLater()


# ---------------------------------------------------------------------------
# FR-GUI-19: ジョブ終了時の経過時間停止は 4 系統すべてを対象とする
# ---------------------------------------------------------------------------


def _running_plan_widget(monkeypatch, clock):
    """Workflow / Step とも running の Plan モードウィジェットを返す。"""
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])
    w = DagStatusWidget()
    steps = [{"id": "1", "title": "T1", "depends_on": []}]
    w.set_plan(_plan("wf-a", steps), {"wf-a": "実行中"}, {"wf-a": {"1": "実行中"}})
    return w


def test_freeze_elapsed_stops_workflow_header_elapsed(qapp, monkeypatch):
    """停止後は Workflow ノードの経過時間が進まない。"""
    clock = {"now": 100.0}
    w = _running_plan_widget(monkeypatch, clock)
    header = w._wf_items["wf-a"]

    clock["now"] = 112.0
    w.freeze_elapsed()
    header.update_text(0, 1)
    assert "[00:00:12]" in header._lbl.text()

    clock["now"] = 3712.0
    header.update_text(0, 1)
    assert "[00:00:12]" in header._lbl.text()
    w.deleteLater()


def test_freeze_elapsed_stops_step_node_elapsed(qapp, monkeypatch):
    """停止後は Step ノードの経過時間が進まない。"""
    clock = {"now": 100.0}
    w = _running_plan_widget(monkeypatch, clock)
    node = w._step_items[("wf-a", "1")]

    clock["now"] = 112.0
    w.freeze_elapsed()
    node.update_text()
    assert node._lbl_elapsed.text() == "⏱ 00:00:12"

    clock["now"] = 3712.0
    node.update_text()
    assert node._lbl_elapsed.text() == "⏱ 00:00:12"
    w.deleteLater()


def _instances_state():
    """running の Workflow / Step を 1 件持つ Instances モード入力を返す。"""
    step = SimpleNamespace(
        status="running", started_at=100.0, finished_at=None, title="T1", children=[]
    )
    inst = SimpleNamespace(
        status="running",
        started_at=100.0,
        finished_at=None,
        workflow_id="wf-a",
        label="WF-A",
        steps={"1": step},
    )
    return SimpleNamespace(workflows={"wf-a": inst})


def test_freeze_elapsed_survives_instances_mode_refresh(qapp, monkeypatch):
    """停止後に表示ノードを再生成しても停止状態が維持される。"""
    clock = {"now": 100.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])
    w = DagStatusWidget()
    state = _instances_state()
    w.update_workflow_instances(state)

    clock["now"] = 112.0
    w.freeze_elapsed()

    # 停止後に 1 時間経過し、同じ state で再描画する（_update_ui 相当）。
    clock["now"] = 3712.0
    w.update_workflow_instances(state)

    node = w._step_items[("wf-a", "1")]
    node.update_text()
    assert node._lbl_elapsed.text() == "⏱ 00:00:12"
    header = w._wf_items["wf-a"]
    header.update_text(0, 1)
    assert "[00:00:12]" in header._lbl.text()
    assert "[00:00:12]" in w._summary_label.text()
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


def test_freeze_elapsed_stops_fanout_child_elapsed(qapp, monkeypatch):
    """停止後は fan-out 子ノードの経過時間が進まない。"""
    clock = {"now": 100.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])
    w = DagStatusWidget()
    subs = [("1/a", "child a", "実行中", 100.0, None)]
    _expand_step1_with_subs(w, subs)
    child = w._child_items[("wf-a", "1/a")]

    clock["now"] = 112.0
    w.freeze_elapsed()
    child.update_text()
    assert child._lbl_elapsed.text() == "⏱ 00:00:12"

    clock["now"] = 3712.0
    child.update_text()
    assert child._lbl_elapsed.text() == "⏱ 00:00:12"
    w.deleteLater()


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


# ---------------------------------------------------------------------------
# T4: サブプロセス箱が他 Step 矩形と垂直方向で重ならないことの保証
# ---------------------------------------------------------------------------


def _rect_of(item) -> tuple[float, float, float, float]:
    """item の scene 座標における (x1, y1, x2, y2) を返す。

    pen 幅や transform を考慮した正確な scene AABB を得るため、
    `sceneBoundingRect()` で計算する。
    """
    scene_rect = item.sceneBoundingRect()
    return (
        scene_rect.left(),
        scene_rect.top(),
        scene_rect.right(),
        scene_rect.bottom(),
    )


def _rects_overlap_vertically(a, b) -> bool:
    """2 つの矩形が垂直方向 (y 区間) で交差し、かつ水平にも重なるか。

    完全に y 区間が分離 (`a.y2 <= b.y1` または `b.y2 <= a.y1`) なら False。
    水平にも分離していれば視覚的には重ならないため False。
    """
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    if ax2 <= bx1 or bx2 <= ax1:
        return False
    if ay2 <= by1 or by2 <= ay1:
        return False
    return True


def _assert_no_overlapping_rects(w) -> None:
    """全 step ノード ↔ 全 child ノード ↔ child 同士の矩形非重複を assert。"""
    step_rects = {key: _rect_of(item) for key, item in w._step_items.items()}
    child_rects = {key: _rect_of(item) for key, item in w._child_items.items()}
    # step ↔ child の重なり禁止 (本不具合の主要対象)
    for s_key, s_rect in step_rects.items():
        for c_key, c_rect in child_rects.items():
            assert not _rects_overlap_vertically(s_rect, c_rect), (
                f"Step {s_key} と child {c_key} の矩形が重複: "
                f"step={s_rect}, child={c_rect}"
            )
    # step 同士の重なり禁止 (二重加算リグレッション検出用)
    step_keys = list(step_rects.keys())
    for i in range(len(step_keys)):
        for j in range(i + 1, len(step_keys)):
            assert not _rects_overlap_vertically(
                step_rects[step_keys[i]], step_rects[step_keys[j]]
            ), (
                f"Step {step_keys[i]} と Step {step_keys[j]} の矩形が重複: "
                f"{step_rects[step_keys[i]]} vs {step_rects[step_keys[j]]}"
            )
    # child 同士の重なり禁止 (within_row_child_offset の積み上げ regression 検出用)
    child_keys = list(child_rects.keys())
    for i in range(len(child_keys)):
        for j in range(i + 1, len(child_keys)):
            assert not _rects_overlap_vertically(
                child_rects[child_keys[i]], child_rects[child_keys[j]]
            ), (
                f"Child {child_keys[i]} と Child {child_keys[j]} の矩形が重複: "
                f"{child_rects[child_keys[i]]} vs {child_rects[child_keys[j]]}"
            )


def test_no_overlap_single_step_expanded_in_multi_row_workflow(qapp):
    """独立 2 root の上行 (order=0) を展開しても下行 (order=1) Step と重ならない。

    `compute_layout` は直列チェーンでは全 Step を order=0 に配置するため、
    「下行」を作るには同 rank に複数独立 root を置く必要がある。
    """
    w = DagStatusWidget()
    w._view.viewport().setFixedWidth(800)
    # 同じ rank=0 に独立 root を 2 つ置き、order=0/1 を作る
    steps = [
        {"id": "S1", "title": "S1", "depends_on": []},
        {"id": "S2", "title": "S2", "depends_on": []},
    ]
    subs1 = [(f"S1/UC-{i:02d}", f"U{i}", "実行中") for i in range(1, 5)]
    statuses = {"wf-a": "実行中"}
    step_statuses = {"wf-a": {"S1": "実行中", "S2": "待機"}}
    subtask_statuses = {"wf-a": {"S1": subs1}}
    w.set_plan(_plan("wf-a", steps), statuses, step_statuses,
               subtask_status=subtask_statuses)
    w._toggle_step_expand("wf-a", "S1")
    w.set_plan(_plan("wf-a", steps), statuses, step_statuses,
               subtask_status=subtask_statuses)
    _assert_no_overlapping_rects(w)
    w.deleteLater()


def test_no_overlap_high_rank_step_expanded_pushes_next_row(qapp):
    """T3 review carry-over: 高 rank Step を展開した時、parent_x で計算した
    cols_per_row が小さくなっても child_heights が一致し、次行 Step と重ならない。

    検出力を確保するため、次行 Step (D) を C と同じ rank=2 に配置し、
    C の child 群と D の Step 矩形が水平方向で重なるよう構成する。
    `parent_x=0` ベース予約 (T3 review 前の不具合) では予約高が過小になり、
    実描画の child 群が D を侵食して fail するはず。
    """
    w = DagStatusWidget()
    w._view.setFixedWidth(500)
    w._view.viewport().setFixedWidth(500 - 24)
    # A -> B -> { C, D } で C/D を同 rank=2 に並べる
    steps = [
        {"id": "A", "title": "A", "depends_on": []},
        {"id": "B", "title": "B", "depends_on": ["A"]},
        {"id": "C", "title": "C", "depends_on": ["B"]},
        {"id": "D", "title": "D", "depends_on": ["B"]},
    ]
    subs_c = [(f"C/UC-{i:02d}", f"U{i}", "実行中") for i in range(1, 7)]  # 6 子
    statuses = {"wf-a": "実行中"}
    step_statuses = {
        "wf-a": {"A": "完了", "B": "完了", "C": "実行中", "D": "待機"}
    }
    subtask_statuses = {"wf-a": {"C": subs_c}}
    w.set_plan(_plan("wf-a", steps), statuses, step_statuses,
               subtask_status=subtask_statuses)
    w._toggle_step_expand("wf-a", "C")
    w.set_plan(_plan("wf-a", steps), statuses, step_statuses,
               subtask_status=subtask_statuses)
    _assert_no_overlapping_rects(w)
    w.deleteLater()


def test_no_overlap_multiple_steps_expanded_same_workflow(qapp):
    """複数 Step を同時展開しても全 Step ↔ child 矩形が重ならない (本不具合の主目的)。

    同 rank に独立 root を 2 つ置き、両方展開する。
    更にもう 1 つ下行に rank=0/order=2 の Step を置いて、
    上行の child ブロックが下行を押し下げるパスを検証する。
    """
    w = DagStatusWidget()
    w._view.viewport().setFixedWidth(800)
    steps = [
        {"id": "S1", "title": "S1", "depends_on": []},
        {"id": "S2", "title": "S2", "depends_on": []},
        {"id": "S3", "title": "S3", "depends_on": []},
    ]
    subs1 = [(f"S1/UC-{i:02d}", f"U{i}", "実行中") for i in range(1, 4)]
    subs2 = [(f"S2/UC-{i:02d}", f"U{i}", "実行中") for i in range(1, 5)]
    statuses = {"wf-a": "実行中"}
    step_statuses = {"wf-a": {"S1": "実行中", "S2": "実行中", "S3": "待機"}}
    subtask_statuses = {"wf-a": {"S1": subs1, "S2": subs2}}
    w.set_plan(_plan("wf-a", steps), statuses, step_statuses,
               subtask_status=subtask_statuses)
    w._toggle_step_expand("wf-a", "S1")
    w._toggle_step_expand("wf-a", "S2")
    w.set_plan(_plan("wf-a", steps), statuses, step_statuses,
               subtask_status=subtask_statuses)
    _assert_no_overlapping_rects(w)
    w.deleteLater()


def test_no_overlap_expansion_in_first_of_two_workflows(qapp):
    """先頭ワークフローの Step 展開が後続ワークフローの Step と重ならない。"""
    w = DagStatusWidget()
    w._view.viewport().setFixedWidth(800)
    plan = [
        {
            "workflow_id": "wf-a",
            "workflow_name": "WF-a",
            "steps": [{"id": "1", "title": "A1", "depends_on": []}],
        },
        {
            "workflow_id": "wf-b",
            "workflow_name": "WF-b",
            "steps": [{"id": "1", "title": "B1", "depends_on": []}],
        },
    ]
    subs_a = [(f"1/UC-{i:02d}", f"U{i}", "実行中") for i in range(1, 5)]
    statuses = {"wf-a": "実行中", "wf-b": "待機"}
    step_statuses = {"wf-a": {"1": "実行中"}, "wf-b": {"1": "待機"}}
    subtask_statuses = {"wf-a": {"1": subs_a}}
    w.set_plan(plan, statuses, step_statuses, subtask_status=subtask_statuses)
    w._toggle_step_expand("wf-a", "1")
    w.set_plan(plan, statuses, step_statuses, subtask_status=subtask_statuses)
    _assert_no_overlapping_rects(w)
    w.deleteLater()


# ---------------------------------------------------------------------------
# 回帰: ダブルクリックハンドラの super() 呼び出しによる shiboken
# "Internal C++ object already deleted" RuntimeError 防止
# ---------------------------------------------------------------------------


def _make_double_click_event():
    """``QGraphicsSceneMouseEvent`` のダブルクリック型を最小構成で生成する。"""
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent

    return QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseDoubleClick)


def test_step_node_double_click_with_fanout_does_not_raise_runtime_error(qapp):
    """Fanout を持つ Step ノードのダブルクリック → ``_relayout`` → ``scene.clear()``
    で self の C++ オブジェクトが破棄された後に super を呼ぶと shiboken の
    RuntimeError が stderr へ出ていた回帰の防止。
    """
    w = DagStatusWidget()
    steps = [{"id": "1", "title": "T1", "depends_on": []}]
    w.set_plan(
        _plan("wf-a", steps),
        {"wf-a": "実行中"},
        {"wf-a": {"1": "実行中"}},
        subtask_status={"wf-a": {"1": [("sub-1", "Subtask 1", "実行中")]}},
    )
    node = w._step_items[("wf-a", "1")]
    # 前提: Fanout として認識されている
    assert node._fanout_total is not None
    # 初期は折りたたみ
    assert w._is_step_expanded("wf-a", "1") is False
    event = _make_double_click_event()
    # RuntimeError("Internal C++ object ... already deleted") が出ないこと
    node.mouseDoubleClickEvent(event)
    # トグルされていること（_toggle_step_expand 経路を通った証跡）
    assert w._is_step_expanded("wf-a", "1") is True
    w.deleteLater()


def test_step_node_double_click_without_fanout_does_not_raise_runtime_error(qapp):
    """Fanout を持たない Step ノードのダブルクリックでは super() が呼ばれる経路の回帰確認。
    こちらは ``_relayout`` を経由しないため self は破棄されず、従来通り例外なしで完了する。
    """
    w = DagStatusWidget()
    steps = [{"id": "1", "title": "T1", "depends_on": []}]
    w.set_plan(_plan("wf-a", steps), {"wf-a": "実行中"}, {"wf-a": {"1": "実行中"}})
    node = w._step_items[("wf-a", "1")]
    # 前提: Fanout 扱いではない
    assert node._fanout_total is None
    event = _make_double_click_event()
    # super() に委譲されても例外なし
    node.mouseDoubleClickEvent(event)
    w.deleteLater()


def test_workflow_header_double_click_does_not_raise_runtime_error(qapp):
    """Workflow ヘッダのダブルクリック → ``_toggle_workflow`` → ``_relayout`` →
    ``scene.clear()`` で self の C++ オブジェクトが破棄された後に super を呼ぶと
    shiboken の RuntimeError が出ていた回帰の防止。
    """
    w = DagStatusWidget()
    steps = [{"id": "1", "title": "T1", "depends_on": []}]
    w.set_plan(_plan("wf-a", steps), {"wf-a": "実行中"}, {"wf-a": {"1": "実行中"}})
    header = w._wf_items["wf-a"]
    # 初期は展開
    assert w._is_workflow_expanded("wf-a") is True
    event = _make_double_click_event()
    # RuntimeError("Internal C++ object ... already deleted") が出ないこと
    header.mouseDoubleClickEvent(event)
    # トグルされていること（_toggle_workflow 経路を通った証跡）
    assert w._is_workflow_expanded("wf-a") is False
    w.deleteLater()


@pytest.mark.parametrize(
    "input_value,expected",
    [
        ("blocked", "blocked"),
        ("ブロック", "blocked"),
    ],
)
def test_normalize_status_accepts_blocked(input_value, expected):
    """``_normalize_status`` が blocked 表記 (英語/日本語) を blocked に正規化することを検証する。

    state_text が "ブロック" のときに pending に丸められて消失する回帰を防ぐ。
    """
    from hve.gui.widgets.dag_status_widget import _normalize_status

    assert _normalize_status(input_value) == expected


def test_blocked_status_has_glyph_and_color():
    """blocked status が絵文字・色 (light/dark) を持つことを検証する。

    DAG widget で blocked 状態のノードが未定義キーで KeyError を起こさないことを保証する。
    """
    from hve.gui.widgets.dag_status_widget import (
        _STATUS_GLYPH,
        _STATUS_COLOR_LIGHT,
        _STATUS_COLOR_DARK,
    )

    assert "blocked" in _STATUS_GLYPH
    assert "blocked" in _STATUS_COLOR_LIGHT
    assert "blocked" in _STATUS_COLOR_DARK
    # 空文字でないこと（実色が割り当てられていること）
    assert _STATUS_GLYPH["blocked"]
    assert _STATUS_COLOR_LIGHT["blocked"]
    assert _STATUS_COLOR_DARK["blocked"]

