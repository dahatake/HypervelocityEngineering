"""hve.autopilot.precheck_runner — Step 1 事前検証の統合ランナー（Qt 非依存）。

v2 改訂（2026-05-24）:
  バナー（``hve.gui.workflow_requirements_banner``）と [次へ] 押下時 Precheck の
  判定ロジックを ``hve.gui.workflow_step_requirements.summarize_requirements_for_selection``
  に統一。FILE / WIZARD_INPUT カテゴリは本共通入口経由で評価する。
  Autopilot ON/OFF も同関数のフラグで切替。

旧版で扱っていた以下は撤去:
  - 全ステップ網羅検査（``precheck_collector.collect_missing_files``）
  - Workflow-specific 設定（``precheck_settings.collect_missing_workflow_settings``）
  - Wizard Step 2 入力検査（``wizard_input_inspector.inspect_wizard_inputs``）
  - 追加プロンプト override / LLM 自然言語判定

AUTH カテゴリは独立性が高いため ``collect_missing_auth`` を維持。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional

from hve.autopilot.precheck_model import (
    AutopilotPrecheckResult,
    PrecheckCategory,
    PrecheckItem,
)
from hve.autopilot.precheck_settings import collect_missing_auth


def run_step1_precheck(
    workflow_ids: Iterable[str],
    repo_root: Path,
    *,
    steps_by_workflow: Optional[Mapping[str, Iterable[str]]] = None,
    input_values: Optional[Mapping[str, str]] = None,
    attached_count: int = 0,
    origin_chosen: bool = False,
    autopilot_mode: bool = False,
    autopilot_catalog_path: Optional[str] = None,
    providers: Optional[Iterable[Any]] = None,
    auth_settings: Optional[Mapping[str, Any]] = None,
    auth_states: Optional[Mapping[str, Any]] = None,
    authenticated_marker: Any = None,
) -> AutopilotPrecheckResult:
    """Step 1 事前検証を実行し統合結果を返す。

    Args:
        workflow_ids: 選択中のワークフロー ID 群。
        repo_root: リポジトリルート（ファイル存在判定の基準）。
        steps_by_workflow: ワークフローごとの選択ステップ ID 群。``None`` の場合は
            各ワークフローを空ステップで扱う（バナーと同じ「対象なし」相当）。
        input_values: ``required_info_keys`` 評価用の入力値辞書
            （``company_name`` / ``target_business`` / ``resource_group`` / ``target_dirs``）。
        attached_count: ARD 添付資料の件数（autopilot_mode=True 時は無視）。
        origin_chosen: ARD 添付資料の起点が選択済みか（autopilot_mode=True 時は無視）。
        autopilot_mode: Autopilot ON フラグ。True のとき個別ワークフロー判定は
            行わず、Autopilot 仮想ワークフローのみ評価する。
        autopilot_catalog_path: Autopilot カタログファイルパス。
        providers / auth_settings / auth_states / authenticated_marker: AUTH 検査用。
            全て指定された場合のみ AUTH 検査を実行する。

    Returns:
        ``AutopilotPrecheckResult``: warn 項目のみを格納（ok は除外）。
    """
    from hve.gui.workflow_step_requirements import (
        summarize_requirements_for_selection,
    )

    selected: List = []
    steps_map = dict(steps_by_workflow or {})
    for wf in workflow_ids:
        if not wf:
            continue
        steps = list(steps_map.get(wf, []))
        selected.append((wf, steps))

    def _file_exists(rel_path: str) -> bool:
        if not rel_path:
            return False
        target = repo_root / rel_path
        if rel_path.endswith("/"):
            try:
                return target.is_dir() and any(target.iterdir())
            except OSError:
                return False
        return target.exists()

    summaries = summarize_requirements_for_selection(
        selected,
        input_values=dict(input_values or {}),
        file_exists=_file_exists,
        attached_count=attached_count,
        origin_chosen=origin_chosen,
        autopilot_mode=autopilot_mode,
        autopilot_catalog_path=autopilot_catalog_path,
    )

    items: List[PrecheckItem] = []
    for s in summaries:
        if s.overall_status != "warn":
            continue
        for ri in s.items:
            if ri.status != "warn":
                continue
            # ファイルパス（"/" を含む or .md 拡張子）は FILE カテゴリ、
            # それ以外は WIZARD_INPUT（required_info_keys / ARD ★起点）扱い。
            if "/" in ri.label or ri.label.endswith(".md"):
                category = PrecheckCategory.FILE
            else:
                category = PrecheckCategory.WIZARD_INPUT
            items.append(PrecheckItem(
                category=category,
                workflow_id=s.workflow_id,
                step_id=s.step_id,
                field_name=ri.label,
                description=ri.detail or s.guidance_text,
                remediation_hint=s.guidance_text,
            ))

    # AUTH 検査（独立カテゴリ）。
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
