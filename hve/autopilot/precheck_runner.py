"""hve.autopilot.precheck_runner — Step 1 事前検証の統合ランナー（Qt 非依存）。

旧名: ``run_autopilot_precheck``。Step 1 [次へ] 統合 precheck へマージした際に
``run_step1_precheck`` へリネームし中立化。

Step 1 [次へ] 押下時に GUI 層から呼び出され、4 カテゴリ
(FILE / WIZARD_INPUT / SETTING / AUTH) を統合検証する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .precheck_collector import collect_missing_files
from .precheck_model import AutopilotPrecheckResult, PrecheckItem
from .precheck_settings import (
    collect_missing_auth,
    collect_missing_workflow_settings,
)


def run_step1_precheck(
    workflow_ids: Iterable[str],
    repo_root: Path,
    *,
    steps_by_workflow: Optional[Dict[str, List[str]]] = None,
    wizard_inputs_by_workflow: Optional[Mapping[str, Mapping[str, Any]]] = None,
    settings_by_workflow: Optional[Mapping[str, Mapping[str, Any]]] = None,
    providers: Optional[Iterable[Any]] = None,
    auth_settings: Optional[Mapping[str, Any]] = None,
    auth_states: Optional[Mapping[str, Any]] = None,
    authenticated_marker: Any = None,
    additional_prompts: Optional[Mapping[str, str]] = None,
    extra_provided_paths_by_workflow: Optional[Mapping[str, Iterable[str]]] = None,
    implicit_required_paths: Optional[Mapping[str, Iterable[str]]] = None,
    autopilot_required_artifacts: Optional[Iterable[str]] = None,
    use_llm_judge: bool = False,
) -> AutopilotPrecheckResult:
    """Step 1 事前検証を実行し統合結果を返す。

    旧名: ``run_autopilot_precheck``。Autopilot ON/OFF いずれも共通で使用されるため
    Step 1 統合フローに中立化した名称へリネーム済み。

    引数は全て optional で、None または空の場合は当該カテゴリ検査をスキップする
    （テスト容易性のため）。GUI 層は実際の providers / settings を必ず渡すこと。
    """
    items: List[PrecheckItem] = []

    workflow_ids_list = [w for w in workflow_ids if w]

    # 1. FILE
    items.extend(
        collect_missing_files(
            workflow_ids_list,
            repo_root,
            steps_by_workflow=steps_by_workflow,
            additional_prompts=additional_prompts,
            extra_provided_paths_by_workflow=extra_provided_paths_by_workflow,
            implicit_required_paths=implicit_required_paths,
            autopilot_required_artifacts=autopilot_required_artifacts,
            use_llm_judge=use_llm_judge,
        )
    )

    # 2. WIZARD_INPUT
    if wizard_inputs_by_workflow is not None:
        from hve.gui.autopilot.wizard_input_inspector import inspect_wizard_inputs

        items.extend(
            inspect_wizard_inputs(workflow_ids_list, wizard_inputs_by_workflow)
        )

    # 3. SETTING
    if settings_by_workflow is not None:
        items.extend(
            collect_missing_workflow_settings(workflow_ids_list, settings_by_workflow)
        )

    # 4. AUTH
    if (
        providers is not None
        and auth_settings is not None
        and auth_states is not None
        and authenticated_marker is not None
    ):
        items.extend(
            collect_missing_auth(
                providers,
                auth_settings,
                auth_states,
                authenticated_marker=authenticated_marker,
            )
        )

    return AutopilotPrecheckResult(items=items)


__all__ = ["run_step1_precheck"]
