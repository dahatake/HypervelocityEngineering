"""hve.gui.widgets.dag_layout — DAG レイアウト計算（純関数）。

``ActivityStatusWidget`` から置き換えた ``DagStatusWidget`` のために、
Workflow Step の依存関係 (``depends_on``) から「ランク（左→右）」と
「ランク内順序（上→下）」を決める純関数を提供する。

依存ライブラリは標準ライブラリのみ。Qt / PySide6 への依存はなし。
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Sequence, Tuple


def compute_layout(
    steps: Sequence[dict],
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """``steps`` の DAG レイアウト（rank, order）を計算する。

    Args:
        steps: 各要素が ``{"id": str, "title": str, "depends_on": List[str]}``
            の dict。``page_workbench._build_workflow_plan`` が生成する形式。

    Returns:
        ``(rank, order)`` のタプル。
        ``rank[step_id]`` は 0 始まりの左→右ランク（depends_on が空＝ルートは 0）。
        ``order[step_id]`` は同一ランク内での 0 始まり上→下順序（宣言順を保持）。

    Notes:
        - 未知の依存先（``depends_on`` に列挙されているが ``steps`` 内に id がない）は
          無視する（捏造禁止のため警告等は出さない）。
        - 循環がある場合は循環内のノードを到達不能として ``rank = 最大ランク+1`` に
          フォールバック配置し、宣言順を維持する。
    """
    ids = [str(s.get("id", "")) for s in steps]
    id_set = set(ids)
    deps: Dict[str, List[str]] = {
        sid: [d for d in s.get("depends_on", []) if d in id_set]
        for sid, s in zip(ids, steps)
    }
    indeg: Dict[str, int] = {sid: len(deps[sid]) for sid in ids}
    # 逆引き: 親 → 子
    children: Dict[str, List[str]] = {sid: [] for sid in ids}
    for sid in ids:
        for p in deps[sid]:
            children[p].append(sid)

    # Kahn 法。宣言順を維持するため deque 末尾には宣言順で追加する。
    rank: Dict[str, int] = {}
    queue: deque = deque(sid for sid in ids if indeg[sid] == 0)
    for sid in queue:
        rank[sid] = 0
    while queue:
        cur = queue.popleft()
        for child in children[cur]:
            indeg[child] -= 1
            new_rank = rank[cur] + 1
            # 親が複数ある場合は最も深いランクを採用
            if child in rank:
                rank[child] = max(rank[child], new_rank)
            else:
                rank[child] = new_rank
            if indeg[child] == 0:
                queue.append(child)

    # 未配置（循環内）ノードは最大ランク+1 にまとめる
    if any(sid not in rank for sid in ids):
        max_rank = max(rank.values(), default=-1)
        fallback_rank = max_rank + 1
        for sid in ids:
            if sid not in rank:
                rank[sid] = fallback_rank

    # 同一ランク内の order を宣言順で 0 から振る
    order: Dict[str, int] = {}
    counters: Dict[int, int] = {}
    for sid in ids:
        r = rank[sid]
        order[sid] = counters.get(r, 0)
        counters[r] = counters.get(r, 0) + 1

    return rank, order


def grid_dimensions(
    rank: Dict[str, int],
    order: Dict[str, int],
) -> Tuple[int, int]:
    """``compute_layout`` の結果から ``(cols, rows)`` を返す。

    ``cols`` = ランク数（最大 rank + 1）、``rows`` = 任意ランクでの最大行数。
    両者とも 0 以上の整数。空入力時は ``(0, 0)``。
    """
    if not rank:
        return (0, 0)
    cols = max(rank.values()) + 1
    rows_per_rank: Dict[int, int] = {}
    for sid, r in rank.items():
        rows_per_rank[r] = max(rows_per_rank.get(r, 0), order[sid] + 1)
    rows = max(rows_per_rank.values()) if rows_per_rank else 0
    return (cols, rows)


def compute_row_y_offsets(
    rank: Dict[str, int],
    order: Dict[str, int],
    child_heights: Dict[str, int],
    *,
    node_h: int,
    row_gap: int,
) -> Tuple[Dict[int, int], Dict[str, int]]:
    """各行（同一 ``order`` 値のグループ）の y オフセットと、行内で同一行に属する
    各 step の子ブロック先頭の追加 y オフセットを計算する純関数。

    ``DagStatusWidget`` の Fanout 子ノード描画が、上下方向で他のノードや子ブロックと
    重ならないようにするためのレイアウト計算ヘルパー。

    Args:
        rank: ``step_id -> 0 始まり rank（左→右）``。``compute_layout`` の戻り値想定。
        order: ``step_id -> 0 始まり order（上→下の行 index）``。``compute_layout`` の戻り値想定。
        child_heights: ``step_id -> 子ブロックが行内で占有する合計垂直スペース px``。
            「親 Step 下のパディング + 子ノード行数 × (CHILD_NODE_H + CHILD_ROW_GAP) - CHILD_ROW_GAP」
            のように、呼び出し側で必要な padding を含めた合計値を渡すこと。子なし
            or 折りたたみの step は 0 を設定するか dict から省略する（省略時は 0 扱い）。
        node_h: Step ノード本体の高さ px。
        row_gap: 行間のギャップ px（最後の子ブロック下端と次行先頭 Step 上端の間隔）。

    Returns:
        ``(row_top_y, within_row_child_offset)``。
        - ``row_top_y[order_value]`` = その行の上辺 y オフセット（最上行 = 0、stripe_top
          を起点とする相対座標）。``order`` が空の場合は空 dict。隣接行間は
          ``row_top_y[o+1] - row_top_y[o] = node_h + (その行の child_heights 合計) + row_gap``
          を満たし、最後の子ブロック下端と次行 Step 上端の間隔が ``row_gap`` になる。
        - ``within_row_child_offset[step_id]`` = その step の子ブロック上辺 y の、
          「stripe_top + row_top_y[o] + node_h」 からの追加オフセット。同一行内で
          ``rank`` が小さい兄弟の ``child_heights`` 累積値（rank 最小の兄弟は 0）。
          子ブロックを持たない step も dict に必ず含まれる（用途は呼び出し側次第）。

    Notes:
        - ``rank`` と ``order`` の両方に存在する step_id のみを処理対象とする。
          どちらか片方にしか存在しない step_id は無視する（捏造禁止のため警告等は
          出さない）。``child_heights`` に余剰 step_id がある場合も無視する。
        - 同一 ``(rank, order)`` の step_id が複数あった場合は ``rank`` 昇順、
          tie-breaker として ``step_id`` 昇順で並べ、その順で縦に積み上げる。
        - 入力の鍵順序に依存しない決定的出力を保証するため、内部で
          ``(rank, step_id)`` 昇順にソートしてから累積する。
    """
    if not order:
        return ({}, {})

    valid_ids = [sid for sid in rank if sid in order]

    rows: Dict[int, List[str]] = {}
    for sid in valid_ids:
        rows.setdefault(order[sid], []).append(sid)
    for o in rows:
        rows[o].sort(key=lambda sid: (rank[sid], sid))

    within_row_child_offset: Dict[str, int] = {}
    row_total_child_height: Dict[int, int] = {}
    for o, sids in rows.items():
        cumulative = 0
        for sid in sids:
            within_row_child_offset[sid] = cumulative
            cumulative += child_heights.get(sid, 0)
        row_total_child_height[o] = cumulative

    row_top_y: Dict[int, int] = {}
    cur_y = 0
    for o in sorted(rows.keys()):
        row_top_y[o] = cur_y
        cur_y += node_h + row_total_child_height[o] + row_gap

    return row_top_y, within_row_child_offset
