"""``hve.gui.widgets.dag_layout.compute_layout`` の単体テスト（純関数）。"""
from __future__ import annotations

from hve.gui.widgets.dag_layout import compute_layout, grid_dimensions


def _s(step_id: str, *deps: str, title: str = "") -> dict:
    return {"id": step_id, "title": title or step_id, "depends_on": list(deps)}


def test_empty_input_returns_empty_dicts():
    rank, order = compute_layout([])
    assert rank == {}
    assert order == {}
    assert grid_dimensions(rank, order) == (0, 0)


def test_linear_chain_ranks_increase():
    steps = [_s("A"), _s("B", "A"), _s("C", "B")]
    rank, order = compute_layout(steps)
    assert rank == {"A": 0, "B": 1, "C": 2}
    assert order == {"A": 0, "B": 0, "C": 0}
    assert grid_dimensions(rank, order) == (3, 1)


def test_parallel_siblings_share_rank_and_get_distinct_order():
    # A → B, A → C, B,C → D
    steps = [_s("A"), _s("B", "A"), _s("C", "A"), _s("D", "B", "C")]
    rank, order = compute_layout(steps)
    assert rank["A"] == 0
    assert rank["B"] == 1
    assert rank["C"] == 1
    assert rank["D"] == 2
    # B と C は同一ランクで宣言順 B → C
    assert order["B"] == 0
    assert order["C"] == 1
    cols, rows = grid_dimensions(rank, order)
    assert cols == 3
    assert rows == 2


def test_multiple_parents_take_deepest_rank():
    # A → B(rank1), A → C → D(rank2), D depends on B → D should be rank 3
    steps = [_s("A"), _s("B", "A"), _s("C", "A"), _s("D", "B", "C")]
    rank, _ = compute_layout(steps)
    # D depends on B(1) and C(1) → rank 2 (max parent + 1)
    assert rank["D"] == 2


def test_unknown_depends_on_is_ignored():
    steps = [_s("A", "missing"), _s("B", "A")]
    rank, order = compute_layout(steps)
    # "missing" を持たない A はルート扱い
    assert rank == {"A": 0, "B": 1}
    assert order["A"] == 0


def test_cycle_falls_back_to_max_rank_plus_one():
    # A → B → A の循環、C は独立ルート
    steps = [_s("A", "B"), _s("B", "A"), _s("C")]
    rank, order = compute_layout(steps)
    # C は Kahn でランク 0 として処理される
    assert rank["C"] == 0
    # 循環内ノードは max_rank + 1 にフォールバック (= 1)
    assert rank["A"] == 1
    assert rank["B"] == 1
    # 同一ランク内の order は宣言順 (rank 0 は C のみ、rank 1 は A→B の順)
    assert order["C"] == 0
    assert order["A"] == 0
    assert order["B"] == 1
