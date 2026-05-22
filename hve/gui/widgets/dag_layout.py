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
