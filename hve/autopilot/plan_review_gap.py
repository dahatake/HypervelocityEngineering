"""hve.autopilot.plan_review_gap — ギャップ計算と producer 提案（Qt 非依存）。

責務:
  1. ``PlannedInput`` リストのうち ``MISSING_GAP`` の入力を抽出
  2. 全 workflow × 全 step の ``output_paths`` から逆引きインデックスを構築
  3. 不足入力が:
       - チェック済み他ステップで生成される   → ``MISSING_PRODUCED`` へ昇格
       - チェック済みでないステップで生成される → ``GapSuggestion`` を生成
       - 生成元なし                            → 未解決として無視（提案不可）
  4. ARD のみ実 Step ID → グループ ID への逆マップを通す

旧 ``dependency_resolver`` から以下を移植:
  - ``_AUTOPILOT_IMPLICIT_REQUIRED_PATHS``: 一部 workflow の Autopilot 固有暗黙依存
  - ``_ARD_STEP_TO_GROUP``: ARD グループ ID 逆マップ
  - ``_WORKFLOW_CANONICAL_ORDER``: canonical order
    （真実源は ``hve/gui/page_options.py:_WORKFLOW_CANONICAL_ORDER`` だが、
     Qt 隔離のため本ファイルにコピーを持つ。両者を同期させること）
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .plan_review_collector import _path_exists
from .plan_review_model import (
    FileStatus,
    GapSuggestion,
    PlannedInput,
)


# canonical order (hve/gui/page_options.py:_WORKFLOW_CANONICAL_ORDER と同期必須)
_WORKFLOW_CANONICAL_ORDER: List[str] = [
    "ard", "aas", "aad-web", "asdw-web", "adfd", "adfdv",
    "akm", "aqod", "adoc",
]

# ARD: 実 Step ID → グループ ID 逆マップ。
# SSOT (hve.workflow_registry._WORKFLOW_GROUP_MAPS) から動的に構築する。
# 旧 hve/orchestrator.py:_ARD_GROUP_MAP との重複定義を撤廃済み。
def _build_ard_step_to_group() -> Dict[str, str]:
    from hve.workflow_registry import _WORKFLOW_GROUP_MAPS
    out: Dict[str, str] = {}
    for gid, members in _WORKFLOW_GROUP_MAPS.get("ard", {}).items():
        for m in members:
            out[m] = gid
    return out


_ARD_STEP_TO_GROUP: Dict[str, str] = _build_ard_step_to_group()

# Autopilot 固有の暗黙依存（StepDef.required_input_paths に未宣言だが実質必須）。
# 旧 dependency_resolver._AUTOPILOT_IMPLICIT_REQUIRED_PATHS を移植。
_AUTOPILOT_IMPLICIT_REQUIRED_PATHS: Dict[str, List[str]] = {
    "aad-web": ["docs/catalog/app-arch-catalog.md"],
    "asdw-web": ["docs/catalog/app-arch-catalog.md"],
    "adfd": ["docs/catalog/app-arch-catalog.md"],
    "adfdv": ["docs/catalog/app-arch-catalog.md"],
}


def _build_path_index() -> Dict[str, Tuple[str, str]]:
    """全 workflow × 全 step から ``{output_path: (wf_id, step_id)}`` を構築。

    canonical order の早いほうを優先（最初に登録されたものを保持）。
    """
    try:
        from hve.workflow_registry import get_workflow
    except Exception:
        return {}

    index: Dict[str, Tuple[str, str]] = {}
    for wf_id in _WORKFLOW_CANONICAL_ORDER:
        wf = get_workflow(wf_id)
        if wf is None:
            continue
        for step in wf.steps:
            if step.is_container:
                continue
            for out_path in (step.output_paths or []):
                if out_path not in index:
                    index[out_path] = (wf_id, step.id)
    return index


def _step_with_depends_closure(wf_id: str, step_id: str) -> List[str]:
    """指定ステップとその depends_on 推移閉包を返す（ARD は呼び出し側で変換）。"""
    try:
        from hve.workflow_registry import get_workflow
    except Exception:
        return [step_id]

    wf = get_workflow(wf_id)
    if wf is None:
        return [step_id]

    result: List[str] = []
    stack: List[str] = [step_id]
    seen: Set[str] = set()
    while stack:
        sid = stack.pop()
        if sid in seen:
            continue
        seen.add(sid)
        result.append(sid)
        step = wf.get_step(sid)
        if step is None:
            continue
        for dep in step.depends_on:
            if dep not in seen:
                stack.append(dep)
    return result


def _to_enable_id(wf_id: str, step_id: str) -> str:
    """実 Step ID を GUI チェックボックス用 ID に変換（ARD はグループ ID へ）。"""
    if wf_id == "ard":
        from hve.workflow_registry import group_id_for_step
        return group_id_for_step("ard", step_id) or step_id
    return step_id


def implicit_required_paths(workflow_ids: Iterable[str]) -> List[Tuple[str, str]]:
    """選択 workflow に対する Autopilot 暗黙依存パスを返す。

    Returns:
        ``(workflow_id, path)`` のリスト。
    """
    out: List[Tuple[str, str]] = []
    for wf_id in workflow_ids:
        for p in _AUTOPILOT_IMPLICIT_REQUIRED_PATHS.get(wf_id, []):
            out.append((wf_id, p))
    return out


def compute_gaps_and_resolve_inputs(
    planned_inputs: List[PlannedInput],
    workflow_ids: Iterable[str],
    repo_root: Path,
    *,
    steps_by_workflow: Dict[str, List[str]],
) -> Tuple[List[PlannedInput], List[GapSuggestion]]:
    """``PlannedInput`` の status を確定し、ギャップ提案を生成する。

    1. 暗黙依存パスを ``PlannedInput`` として追加
       （``workflow_id`` のみ持ち、``step_id`` は ``"<implicit>"``）
    2. 各 ``MISSING_*`` 入力について output_paths 逆引き
    3. 生成元がチェック済み他ステップ      → ``MISSING_PRODUCED`` に確定
    4. 生成元が未チェック workflow/step    → ``GapSuggestion`` 生成
    5. 生成元なし                          → ``MISSING_GAP`` のまま（提案不可）

    Returns:
        (確定済み planned_inputs, ギャップ提案リスト)。
    """
    # 1. 暗黙依存を追加
    extended = list(planned_inputs)
    for wf_id, rel in implicit_required_paths(workflow_ids):
        # 既に同じ (wf_id, path) が含まれていればスキップ
        if any(p.workflow_id == wf_id and p.path == rel for p in extended):
            continue
        status = (
            FileStatus.EXISTING_REUSABLE
            if _path_exists(repo_root, rel)
            else FileStatus.MISSING_GAP
        )
        extended.append(
            PlannedInput(
                workflow_id=wf_id,
                step_id="<implicit>",
                path=rel,
                status=status,
                producer=None,
            )
        )

    # 2. チェック済みステップが生成するパス集合
    produced_by_checked: Dict[str, Tuple[str, str]] = {}
    try:
        from hve.workflow_registry import get_workflow
    except Exception:
        get_workflow = None  # type: ignore[assignment]

    if get_workflow is not None:
        for wf_id, step_ids in steps_by_workflow.items():
            wf = get_workflow(wf_id)
            if wf is None:
                continue
            target_ids = set(step_ids)
            for step in wf.steps:
                if step.is_container or step.id not in target_ids:
                    continue
                for out_path in (step.output_paths or []):
                    if out_path not in produced_by_checked:
                        produced_by_checked[out_path] = (wf_id, step.id)

    # 3. 全 workflow × 全 step の逆引き
    global_index = _build_path_index()

    # 4. ループで status 確定 + ギャップ生成
    resolved: List[PlannedInput] = []
    gaps: List[GapSuggestion] = []
    gap_paths_seen: Set[str] = set()

    for inp in extended:
        if inp.status == FileStatus.EXISTING_REUSABLE:
            resolved.append(inp)
            continue

        # 不在 → producer を探す
        producer_checked = produced_by_checked.get(inp.path)
        if producer_checked is not None:
            resolved.append(
                PlannedInput(
                    workflow_id=inp.workflow_id,
                    step_id=inp.step_id,
                    path=inp.path,
                    status=FileStatus.MISSING_PRODUCED,
                    producer=producer_checked,
                )
            )
            continue

        producer_global = global_index.get(inp.path)
        if producer_global is None:
            # 生成元なし → 未解決
            resolved.append(inp)
            continue

        # 未チェック workflow/step が生成 → ギャップ提案
        prod_wf, prod_step = producer_global
        resolved.append(
            PlannedInput(
                workflow_id=inp.workflow_id,
                step_id=inp.step_id,
                path=inp.path,
                status=FileStatus.MISSING_GAP,
                producer=None,
            )
        )
        if inp.path in gap_paths_seen:
            continue
        gap_paths_seen.add(inp.path)
        closure = _step_with_depends_closure(prod_wf, prod_step)
        transitive = sorted({_to_enable_id(prod_wf, s) for s in closure})
        gaps.append(
            GapSuggestion(
                missing_path=inp.path,
                suggested_workflow_id=prod_wf,
                suggested_step_id=_to_enable_id(prod_wf, prod_step),
                transitive_steps=transitive,
            )
        )

    # canonical order でソート（提案）
    gaps.sort(
        key=lambda g: (
            _WORKFLOW_CANONICAL_ORDER.index(g.suggested_workflow_id)
            if g.suggested_workflow_id in _WORKFLOW_CANONICAL_ORDER
            else len(_WORKFLOW_CANONICAL_ORDER),
            g.suggested_step_id,
        )
    )

    return resolved, gaps


__all__ = [
    "compute_gaps_and_resolve_inputs",
    "implicit_required_paths",
    "_WORKFLOW_CANONICAL_ORDER",
    "_ARD_STEP_TO_GROUP",
    "_AUTOPILOT_IMPLICIT_REQUIRED_PATHS",
]
