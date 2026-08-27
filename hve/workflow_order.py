"""hve.workflow_order — 複数 Workflow の依存順安定ソート（FR-PROMPT-06）。

GUI（`hve/gui/main_window.py`）と Prompt 版（`hve/prompt_execution.py`）が同じ
順序を使えるよう、Qt 非依存の単一実装をここに置く（FR-MAINT-07）。
"""

from __future__ import annotations

from typing import Dict, List, Sequence

from .workflow_registry import get_meta_dependencies


def sort_workflows_by_dependencies(selected_workflows: Sequence[str]) -> List[str]:
    """選択ワークフローを依存関係に基づいて安定ソートする。

    選択されていない依存 Workflow は追加しない。循環時は `ValueError`。
    """
    selected = [w for w in selected_workflows if w]
    if len(selected) != len(set(selected)):
        raise ValueError("同じ Workflow が重複して選択されています。")
    if len(selected) <= 1:
        return selected

    index_by_wf = {wf: i for i, wf in enumerate(selected)}
    edges: Dict[str, List[str]] = {wf: [] for wf in selected}
    indegree: Dict[str, int] = {wf: 0 for wf in selected}

    for wf in selected:
        for dep in get_meta_dependencies(wf):
            dep_wf = dep.workflow_id
            if dep_wf not in indegree:
                continue
            edges[dep_wf].append(wf)
            indegree[wf] += 1

    ready = [wf for wf, deg in indegree.items() if deg == 0]
    ready.sort(key=lambda w: index_by_wf[w])

    ordered: List[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for nxt in edges[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
                ready.sort(key=lambda w: index_by_wf[w])

    if len(ordered) != len(selected):
        raise ValueError("選択されたワークフロー間に循環依存があります。")

    return ordered
