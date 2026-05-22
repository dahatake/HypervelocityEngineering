"""hve.autopilot.plan_review_runner — Step 1 プランレビューの統合ランナー（Qt 非依存）。

旧名: ``build_autopilot_plan_review``。Step 1 [次へ] 統合 precheck へマージした際に
``build_step1_plan_review`` へリネームし中立化。

``_run_step1_unified_precheck`` から呼び出され、4 タブ分の集約結果
``AutopilotPlanReview`` を返す。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .plan_review_collector import (
    collect_planned_inputs,
    collect_planned_outputs,
)
from .plan_review_gap import compute_gaps_and_resolve_inputs
from .plan_review_model import AutopilotPlanReview
from .plan_review_params import collect_parameters


def build_step1_plan_review(
    workflow_ids: Iterable[str],
    repo_root: Path,
    *,
    steps_by_workflow: Dict[str, List[str]],
    wizard_inputs_by_workflow: Optional[Mapping[str, Mapping[str, Any]]] = None,
    settings_by_workflow: Optional[Mapping[str, Mapping[str, Any]]] = None,
    execution_order: Optional[List[str]] = None,
) -> AutopilotPlanReview:
    """プランレビュー一式を構築する。

    旧名: ``build_autopilot_plan_review``。Autopilot ON/OFF いずれも共通で使用されるため
    Step 1 統合フローに中立化した名称へリネーム済み。

    Args:
        workflow_ids: 選択中の workflow ID リスト。
        repo_root: リポジトリルート。
        steps_by_workflow: workflow_id → 有効 step ID リスト。
            空 list は「対象 step ゼロ」を意味する。キー欠落 workflow は列挙対象外。
        wizard_inputs_by_workflow: Wizard Step 2 入力 dict。
        settings_by_workflow: Workflow-specific 設定 dict。
        execution_order: 実行順に並べた workflow ID 列（補助表示用）。
            GUI Step1PlanReviewDialog で「実行順序: ARD → AAS → ...」として表示する。
            空 list の場合は表示しない（Autopilot OFF 時の既定）。

    Returns:
        ``AutopilotPlanReview``。
    """
    wf_list = [w for w in workflow_ids if w]

    # ARD 等の GUI/CLI グループ ID を registry の実 Step ID に展開（SSOT 経由）。
    # precheck_collector.collect_missing_files / orchestrator と同じ正規化を入口で
    # 一度だけ行い、以降の collector / gap には展開済み dict を渡す。
    # 未登録 workflow（aas / aad-web 等）は passthrough のため副作用なし。
    from hve.workflow_registry import expand_group_step_ids
    expanded_steps_by_workflow: Dict[str, List[str]] = {
        wf_id: expand_group_step_ids(wf_id, list(sids))
        for wf_id, sids in steps_by_workflow.items()
    }

    # 1. 入出力収集
    inputs_raw = collect_planned_inputs(
        wf_list, repo_root, steps_by_workflow=expanded_steps_by_workflow
    )
    outputs = collect_planned_outputs(
        wf_list, repo_root, steps_by_workflow=expanded_steps_by_workflow
    )

    # 2. ギャップ計算 + status 確定
    inputs, gaps = compute_gaps_and_resolve_inputs(
        inputs_raw,
        wf_list,
        repo_root,
        steps_by_workflow=expanded_steps_by_workflow,
    )

    # 3. パラメータ収集
    parameters = collect_parameters(
        wf_list,
        wizard_inputs_by_workflow=wizard_inputs_by_workflow,
        settings_by_workflow=settings_by_workflow,
    )

    return AutopilotPlanReview(
        inputs=inputs,
        outputs=outputs,
        parameters=parameters,
        gaps=gaps,
        execution_order=list(execution_order or []),
    )


__all__ = ["build_step1_plan_review"]
