"""FR-DAG-10: HVE の Step 起動可能判定の単一実装。

計画段階の ``WorkflowDef.get_next_steps`` と、実行段階の ``DAGExecutor._get_next_steps`` /
``DAGExecutor._get_next_steps_from_expanded`` は、本モジュールの ``select_ready_ids`` だけで
起動可能判定を行う（``test_dag_readiness_parity.py``）。
"""

from __future__ import annotations

from typing import AbstractSet, Any, Iterable, List, Mapping


def _is_ready(
    node_id: str,
    deps: Iterable[str],
    succeeded: AbstractSet[str],
    terminal: AbstractSet[str],
) -> bool:
    """未完了・非終端で、依存がすべて解決済みのノードだけを起動可能とする。"""
    if node_id in succeeded or node_id in terminal:
        return False
    return all(dep in succeeded for dep in deps)


def select_ready_ids(
    nodes: Iterable[Mapping[str, Any]],
    *,
    known_ids: AbstractSet[str],
    completed: Iterable[str],
    skipped: Iterable[str],
    excluded: AbstractSet[str] = frozenset(),
) -> List[str]:
    """起動可能なノードの id を、入力の順序で返す（R-f）。

    ``nodes`` の要素は ``id`` / ``deps`` / ``block_unless`` / ``container`` を持つ。
    """
    completed = set(completed)
    succeeded = completed | set(skipped)  # R-a
    terminal = set(excluded)
    ready: List[str] = []
    for node in nodes:
        if node.get("container"):  # R-e
            continue
        if not set(node.get("block_unless", ())) <= completed:  # R-c
            continue
        # R-b: known_ids に無い依存は充足とみなす
        deps = [str(dep) for dep in node.get("deps", ()) if dep in known_ids]
        if _is_ready(str(node["id"]), deps, succeeded, terminal):  # R-d
            ready.append(node["id"])
    return ready
