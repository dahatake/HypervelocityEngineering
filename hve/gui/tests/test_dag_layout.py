"""``hve.gui.widgets.dag_layout.compute_layout`` の単体テスト（純関数）。"""
from __future__ import annotations

from hve.gui.widgets.dag_layout import (
    compute_layout,
    compute_row_y_offsets,
    grid_dimensions,
)


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


# ---------------------------------------------------------------------------
# compute_row_y_offsets: Fanout 展開時の行レイアウト計算（純関数）
# ---------------------------------------------------------------------------


def test_row_y_offsets_empty_inputs_return_empty_dicts():
    row_top_y, within = compute_row_y_offsets(
        {}, {}, {}, node_h=56, row_gap=10
    )
    assert row_top_y == {}
    assert within == {}


def test_row_y_offsets_no_expansion_uses_node_h_and_row_gap_only():
    # 3 行・各行 1 step・展開なし
    rank = {"A": 0, "B": 0, "C": 0}
    order = {"A": 0, "B": 1, "C": 2}
    row_top_y, within = compute_row_y_offsets(
        rank, order, {}, node_h=56, row_gap=10
    )
    assert row_top_y == {0: 0, 1: 66, 2: 132}
    # 子なし step も dict に必ず含まれ、すべて 0
    assert within == {"A": 0, "B": 0, "C": 0}


def test_row_y_offsets_single_expansion_pushes_subsequent_rows_down():
    # row 0 に 100px の expansion → row 1 が node_h(56)+100+row_gap(10)=166 下にずれる
    rank = {"A": 0, "B": 0}
    order = {"A": 0, "B": 1}
    row_top_y, within = compute_row_y_offsets(
        rank, order, {"A": 100}, node_h=56, row_gap=10
    )
    assert row_top_y == {0: 0, 1: 166}
    # 同一行内に他の step がいないので within["A"] は 0
    assert within == {"A": 0, "B": 0}


def test_row_y_offsets_multiple_expansions_same_row_stack_by_rank():
    # row 0 に rank=0 (h=30), rank=1 (h=20), rank=2 (h=0) → A, B, C
    rank = {"A": 0, "B": 1, "C": 2}
    order = {"A": 0, "B": 0, "C": 0}
    row_top_y, within = compute_row_y_offsets(
        rank, order, {"A": 30, "B": 20}, node_h=50, row_gap=5
    )
    # row 0 のみ。row_top_y は {0: 0}
    assert row_top_y == {0: 0}
    # rank 0 (A) は 0、rank 1 (B) は A の 30 ぶん下、rank 2 (C) は A+B の 50 ぶん下
    assert within == {"A": 0, "B": 30, "C": 50}


def test_row_y_offsets_expansions_in_multiple_rows_propagate_downward():
    # row 0 に A (h=40)、row 1 に B (h=60)、row 2 に C (h=0)
    rank = {"A": 0, "B": 0, "C": 0}
    order = {"A": 0, "B": 1, "C": 2}
    row_top_y, within = compute_row_y_offsets(
        rank, order, {"A": 40, "B": 60}, node_h=50, row_gap=10
    )
    # row 0 top = 0
    # row 1 top = node_h(50) + A_child(40) + row_gap(10) = 100
    # row 2 top = row1 + node_h(50) + B_child(60) + row_gap(10) = 220
    assert row_top_y == {0: 0, 1: 100, 2: 220}
    assert within == {"A": 0, "B": 0, "C": 0}


def test_row_y_offsets_unknown_step_ids_in_child_heights_are_ignored():
    # ghost が within に入らないことに加え、row 1 を追加して row_top_y にも
    # 影響しないことを検証する（余剰 child_heights が行高さ計算に混入しないこと）。
    rank = {"A": 0, "B": 0}
    order = {"A": 0, "B": 1}
    row_top_y, within = compute_row_y_offsets(
        rank, order, {"A": 50, "ghost": 999}, node_h=56, row_gap=10
    )
    # row 1 top は node_h(56) + A_child(50) + row_gap(10) = 116 になるはずで、
    # ghost(999) が混入していれば 1115 になるため強い回帰検出になる。
    assert row_top_y == {0: 0, 1: 116}
    assert "ghost" not in within
    assert within == {"A": 0, "B": 0}


def test_row_y_offsets_step_only_in_rank_or_only_in_order_is_ignored():
    # A は rank と order の両方、B は rank のみ、C は order のみ → A だけ処理対象
    rank = {"A": 0, "B": 0}
    order = {"A": 0, "C": 0}
    row_top_y, within = compute_row_y_offsets(
        rank, order, {}, node_h=56, row_gap=10
    )
    assert row_top_y == {0: 0}
    assert "B" not in within
    assert "C" not in within
    assert within == {"A": 0}


def test_row_y_offsets_is_deterministic_regardless_of_dict_insertion_order():
    # 行をまたぐ挿入順（row 1 → row 0 → row 2）でも row_top_y は sorted(order)
    # に従って 0, 1, 2 の順に確定することを検証する。これにより
    # `for o in sorted(rows.keys())` の sorted を外す回帰を検出できる。
    rank_a = {"A": 0, "B": 0, "C": 0}
    order_a = {"A": 0, "B": 1, "C": 2}
    ch_a = {"A": 30, "B": 20}
    # B (order 1) を最初に、A (order 0) を 2 番目に、C (order 2) を最後に挿入
    rank_b = {"B": 0, "A": 0, "C": 0}
    order_b = {"B": 1, "A": 0, "C": 2}
    ch_b = {"B": 20, "A": 30}
    out_a = compute_row_y_offsets(rank_a, order_a, ch_a, node_h=56, row_gap=10)
    out_b = compute_row_y_offsets(rank_b, order_b, ch_b, node_h=56, row_gap=10)
    assert out_a == out_b
    # 期待値も明示: row 0 top=0, row 1 top=56+30+10=96, row 2 top=96+56+20+10=182
    assert out_a[0] == {0: 0, 1: 96, 2: 182}


def test_row_y_offsets_same_rank_order_pair_uses_step_id_tiebreaker():
    # 入力 dict の挿入順を「B → A」にしても、step_id 昇順 (A → B) で
    # tie-break されることを検証する。これによりソートキー第 2 要素
    # （step_id）を削除する回帰を確実に検出できる。
    rank = {"B": 0, "A": 0}
    order = {"B": 0, "A": 0}
    row_top_y, within = compute_row_y_offsets(
        rank, order, {"A": 10, "B": 20}, node_h=56, row_gap=10
    )
    assert row_top_y == {0: 0}
    # step_id 昇順なら A が先 → within["A"] = 0、B は A の 10 ぶん下
    # 挿入順だけで決めると within["B"] = 0, within["A"] = 20 となるため強い検出になる
    assert within == {"A": 0, "B": 10}


def test_row_y_offsets_scenario_multi_row_multi_expansion_matches_screenshot():
    # スクリーンショット相当: row 0 に複数 (A, B 展開) + row 1 に複数 (C, D 展開) +
    # row 2 (E 単独・展開なし)。row_total_child_height の sum 計算と多行
    # 押し下げの両方を 1 ケースで検証する。
    rank = {"A": 0, "B": 1, "C": 0, "D": 1, "E": 0}
    order = {"A": 0, "B": 0, "C": 1, "D": 1, "E": 2}
    child_heights = {"A": 40, "B": 60, "C": 30, "D": 50}
    row_top_y, within = compute_row_y_offsets(
        rank, order, child_heights, node_h=56, row_gap=10
    )
    # row 0 top = 0
    # row 1 top = node_h(56) + A(40)+B(60) + row_gap(10) = 166
    # row 2 top = 166 + node_h(56) + C(30)+D(50) + row_gap(10) = 312
    assert row_top_y == {0: 0, 1: 166, 2: 312}
    # 行内累積: row 0 で A=0, B=40 / row 1 で C=0, D=30 / row 2 で E=0
    assert within == {"A": 0, "B": 40, "C": 0, "D": 30, "E": 0}


def test_row_y_offsets_omitted_child_heights_treated_as_zero():
    # 展開なし step を child_heights から省略しても 0 扱いになる
    rank = {"A": 0, "B": 1, "C": 2}
    order = {"A": 0, "B": 0, "C": 0}
    row_top_y, within = compute_row_y_offsets(
        rank, order, {"B": 25}, node_h=56, row_gap=10
    )
    assert row_top_y == {0: 0}
    # A は 0（前に何もない）、B は 0（A が省略 = 0）、C は 25（B のぶん）
    assert within == {"A": 0, "B": 0, "C": 25}
