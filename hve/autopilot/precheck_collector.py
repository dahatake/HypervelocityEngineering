"""hve.autopilot.precheck_collector — Workflow/Step の必須入出力ファイル収集（Qt 非依存）。

選択された workflow_ids / steps_by_workflow を受け取り、各 step の
``required_input_paths`` と、workflow 間 ``WorkflowDependency.required_artifacts``
を実存チェックして不足ファイルを `PrecheckItem` 列として返す。

判定ロジック（plan 確定済み P1〜P6 準拠）:
ある必須入力ファイル ``f`` は以下のいずれかを満たせば「不足ではない」:
  1. ``f`` が repo_root 配下に既に実存する
  2. 同じ Autopilot ランで選択中の任意の step が ``output_paths`` に ``f`` を含む
     （P2=(b) 採用: 選択集合一括、順序は問わない）
  3. 追加プロンプト本文に ``f`` / description / glob prefix が言及されている
  4. パラメータ（``attached_docs`` / ``target_business_path`` 等）で
     ``f`` または等価ファイルが指定されている
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Set

from hve.workflow_registry import (
    StepDef,
    get_artifact_description,
    get_meta_dependencies,
    get_workflow,
)

from .precheck_model import PrecheckCategory, PrecheckItem


def _path_exists(repo_root: Path, pattern: str) -> bool:
    """単純パス存在チェック。glob は ``*`` / ``?`` / ``[`` を含む場合に展開。"""
    if not pattern:
        return True
    if any(ch in pattern for ch in ("*", "?", "[")):
        try:
            return any(repo_root.glob(pattern))
        except (OSError, ValueError):
            return False
    return (repo_root / pattern).exists()


def is_overridden_in_prompt(
    prompt: Optional[str],
    pattern: str,
    description: str,
) -> bool:
    """追加プロンプトに pattern / description / glob prefix への言及があれば True。

    旧 ``hve/gui/artifact_precheck._is_overridden_in_prompt`` から移植（P4=(a) 採用）。
    """
    if not prompt:
        return False
    text = prompt
    if pattern and pattern in text:
        return True
    if description and description != pattern and description in text:
        return True
    if any(ch in pattern for ch in ("*", "?", "[")):
        prefix = pattern.split("*", 1)[0].split("?", 1)[0].split("[", 1)[0]
        if prefix and prefix in text:
            return True
    return False


def _normalize_path(p: str) -> str:
    """パス比較用に区切り文字と前後空白を正規化する。"""
    if not p:
        return ""
    return p.replace("\\", "/").strip()


def _collect_planned_outputs(
    workflow_ids: Iterable[str],
    steps_by_workflow: Optional[Dict[str, List[str]]],
) -> Set[str]:
    """選択中の全 workflow / 全選択 step が生成予定の ``output_paths`` 和集合。

    P2=(b) 採用: 順序を問わず、選択集合に含まれる全 step の output_paths を集める。
    Fan-out (``output_paths_template``) はプレースホルダ ``{...}`` を ``*`` に
    置換した glob パターンとして含める（チェーン上の後続 workflow が
    ``docs/dataflow/apps/*.md`` 等の glob で要求するケースに対応）。
    """
    steps_by_workflow = steps_by_workflow or {}
    planned: Set[str] = set()
    for wf_id in workflow_ids:
        wf = get_workflow(wf_id)
        if wf is None:
            continue
        if wf_id in steps_by_workflow:
            target_step_ids = set(steps_by_workflow[wf_id])
            steps = [
                s for s in wf.steps
                if s.id in target_step_ids and not s.is_container
            ]
        else:
            steps = [s for s in wf.steps if not s.is_container]
        for step in steps:
            for out in step.output_paths:
                # fan-out 未展開プレースホルダはスキップ
                if any(ch in out for ch in ("{", "}")):
                    continue
                planned.add(_normalize_path(out))
            # Fan-out テンプレート: {key} を * に置換した glob を planned に追加。
            # ネスト ``{a{b}}`` には非対応（実テンプレでは出現しない）。
            template_paths = step.output_paths_template or []
            for tmpl in template_paths:
                glob_pat = _template_to_glob(tmpl)
                if glob_pat:
                    planned.add(glob_pat)
    return planned


def _template_to_glob(template: str) -> str:
    """``docs/dataflow/apps/{jobId}-{slug}-spec.md`` → ``docs/dataflow/apps/*-*-spec.md`` 変換。

    各プレースホルダ ``{...}`` を ``*`` に置換する。連続プレースホルダ ``{a}-{b}``
    は ``*-*`` となる（fnmatch 上は単独 ``*`` と等価）。ネストブレースは非対応。
    """
    if not template:
        return ""
    return _normalize_path(re.sub(r"\{[^{}]+\}", "*", template))


def _collect_extra_provided(
    extra_provided_paths_by_workflow: Optional[Mapping[str, Iterable[str]]],
) -> Set[str]:
    """GUI パラメータで明示指定された全ファイルパスの和集合（正規化済み）。"""
    if not extra_provided_paths_by_workflow:
        return set()
    result: Set[str] = set()
    for paths in extra_provided_paths_by_workflow.values():
        if not paths:
            continue
        for p in paths:
            if not p:
                continue
            # カンマ区切り文字列もサポート
            for chunk in str(p).split(","):
                norm = _normalize_path(chunk)
                if norm:
                    result.add(norm)
    return result


def _is_satisfied(
    pattern: str,
    repo_root: Path,
    planned_outputs: Set[str],
    extra_provided: Set[str],
    prompt: Optional[str],
    description: str,
) -> bool:
    """単一の必須入力パターンが satisfy されているか判定する。"""
    # 1) 実存
    if _path_exists(repo_root, pattern):
        return True
    norm_pattern = _normalize_path(pattern)
    # 2) 先行 step の planned output
    if norm_pattern in planned_outputs:
        return True
    # 3) GUI パラメータ
    if norm_pattern in extra_provided:
        return True
    # glob 対応: planned / extra に prefix 一致するエントリがあれば OK
    if any(ch in pattern for ch in ("*", "?", "[")):
        prefix = pattern.split("*", 1)[0].split("?", 1)[0].split("[", 1)[0]
        prefix = _normalize_path(prefix)
        if prefix:
            for p in planned_outputs:
                if p.startswith(prefix):
                    return True
            for p in extra_provided:
                if p.startswith(prefix):
                    return True
    # 4) 追加プロンプト override
    if is_overridden_in_prompt(prompt, pattern, description):
        return True
    return False


def collect_missing_files(
    workflow_ids: Iterable[str],
    repo_root: Path,
    *,
    steps_by_workflow: Optional[Dict[str, List[str]]] = None,
    additional_prompts: Optional[Mapping[str, str]] = None,
    extra_provided_paths_by_workflow: Optional[Mapping[str, Iterable[str]]] = None,
    implicit_required_paths: Optional[Mapping[str, Iterable[str]]] = None,
    autopilot_required_artifacts: Optional[Iterable[str]] = None,
) -> List[PrecheckItem]:
    """選択 workflow/step の required ファイル不足を収集。

    Args:
        workflow_ids: 対象 workflow ID リスト（小文字想定）。
        repo_root: リポジトリルート。
        steps_by_workflow: workflow_id → 実行対象 step ID リスト。
            None または該当 workflow キー欠落時は当該 workflow の全 non-container step を対象。
            ARD のグループ ID (1/2/4) は ``hve.workflow_registry.expand_group_step_ids``
            により内部で実 step ID に展開される（呼び出し側でグループ ID のまま渡せる）。
        additional_prompts: workflow_id → 追加プロンプト本文。
        extra_provided_paths_by_workflow: workflow_id → GUI パラメータで指定されたファイルパス群
            （``attached_docs`` / ``target_business_path`` / ``autopilot_catalog_path`` 等）。
        implicit_required_paths: workflow_id → 暗黙必須 path 群（StepDef.required_input_paths
            に未宣言だが実質必須なファイル。Autopilot 経路で使用）。
        autopilot_required_artifacts: workflow 横断のグローバル必須 path 群
            （例: ``["docs/catalog/app-arch-catalog.md"]``。``workflow_id=""`` の
            PrecheckItem として返される）。
    """
    workflow_ids_list = [w for w in workflow_ids if w]
    additional_prompts = additional_prompts or {}
    steps_by_workflow = steps_by_workflow or {}

    # ARD: GUI/CLI のグループ ID を実 step ID に展開（SSOT 経由）。
    from hve.workflow_registry import expand_group_step_ids
    expanded_steps_by_workflow: Dict[str, List[str]] = {}
    for wf_id, sids in steps_by_workflow.items():
        expanded_steps_by_workflow[wf_id] = expand_group_step_ids(wf_id, list(sids))

    planned_outputs = _collect_planned_outputs(workflow_ids_list, expanded_steps_by_workflow)
    extra_provided = _collect_extra_provided(extra_provided_paths_by_workflow)

    items: List[PrecheckItem] = []

    for wf_id in workflow_ids_list:
        wf = get_workflow(wf_id)
        if wf is None:
            continue
        prompt = additional_prompts.get(wf_id)

        # --- step-level required_input_paths ---
        steps: List[StepDef]
        if wf_id in expanded_steps_by_workflow:
            target_step_ids = expanded_steps_by_workflow[wf_id]
            steps = [
                s for s in wf.steps
                if s.id in target_step_ids and not s.is_container
            ]
        else:
            steps = [s for s in wf.steps if not s.is_container]

        for step in steps:
            for rel in step.required_input_paths:
                description = get_artifact_description(rel) or rel
                if _is_satisfied(
                    rel,
                    repo_root,
                    planned_outputs,
                    extra_provided,
                    prompt,
                    description,
                ):
                    continue
                items.append(
                    PrecheckItem(
                        category=PrecheckCategory.FILE,
                        workflow_id=wf_id,
                        step_id=step.id,
                        field_name=rel,
                        description=(
                            f"Workflow '{wf_id}' Step '{step.id}' の必須入力ファイルが存在しません: {rel}"
                        ),
                        remediation_hint=(
                            f"先行ステップまたは手動で {rel} を作成してから再実行してください。"
                        ),
                    )
                )

        # --- workflow-level dependencies (WorkflowDependency.required_artifacts) ---
        for dep in get_meta_dependencies(wf_id):
            # チェーン依存ロジック: 依存先 workflow が選択集合に含まれる「かつ」、
            # 当該成果物が選択 step の output として planned_outputs に含まれる
            # 場合に satisfy。dep workflow が選択されていても、必要な step が
            # steps_by_workflow で除外されている場合は missing として検出する
            # （依存先ワークフローが当該成果物を生成することを保証するため）。
            for rel in dep.required_artifacts:
                description = get_artifact_description(rel) or rel
                if _is_satisfied(
                    rel,
                    repo_root,
                    planned_outputs,
                    extra_provided,
                    prompt,
                    description,
                ):
                    continue
                items.append(
                    PrecheckItem(
                        category=PrecheckCategory.FILE,
                        workflow_id=wf_id,
                        step_id=None,
                        field_name=rel,
                        description=(
                            f"Workflow '{wf_id}' が依存する '{dep.workflow_id}' 成果物が見つかりません: {rel}"
                            + ("（soft）" if dep.soft else "")
                        ),
                        remediation_hint=(
                            f"依存 Workflow '{dep.workflow_id}' を先に実行するか、{rel} を手動配置してください。"
                        ),
                        soft=dep.soft,
                    )
                )

        # --- workflow-level implicit required paths (Autopilot 経路で注入) ---
        # StepDef.required_input_paths に未宣言だが Autopilot 実行時に実質必須なファイル群。
        # 旧 hve.autopilot.plan_review_gap._AUTOPILOT_IMPLICIT_REQUIRED_PATHS を
        # 引数経由で受け取り、両経路で同一アルゴリズムにより検査する。
        if implicit_required_paths:
            for rel in implicit_required_paths.get(wf_id, []) or []:
                description = get_artifact_description(rel) or rel
                if _is_satisfied(
                    rel,
                    repo_root,
                    planned_outputs,
                    extra_provided,
                    prompt,
                    description,
                ):
                    continue
                items.append(
                    PrecheckItem(
                        category=PrecheckCategory.FILE,
                        workflow_id=wf_id,
                        step_id=None,
                        field_name=rel,
                        description=(
                            f"Workflow '{wf_id}' の暗黙必須入力ファイルが見つかりません: {rel}"
                        ),
                        remediation_hint=(
                            f"先行ワークフロー実行または手動配置で {rel} を準備してください。"
                        ),
                    )
                )

    # --- グローバル必須 (Autopilot 経路の app-arch-catalog.md 等) ---
    # workflow_id="" の PrecheckItem として返す。OFF 経路では空 list を渡せば発火しない。
    if autopilot_required_artifacts:
        # extra_provided の "" キー（カタログパス等）も実存判定に含めて評価。
        for rel in autopilot_required_artifacts:
            if not rel:
                continue
            description = get_artifact_description(rel) or rel
            if _is_satisfied(
                rel,
                repo_root,
                planned_outputs,
                extra_provided,
                None,
                description,
            ):
                continue
            items.append(
                PrecheckItem(
                    category=PrecheckCategory.FILE,
                    workflow_id="",
                    field_name=rel,
                    description=(
                        f"Autopilot に必須の成果物が存在しません: {rel}"
                    ),
                    remediation_hint=(
                        f"先行ワークフローまたは手動で {rel} を作成してください。"
                    ),
                )
            )

    return items


__all__ = [
    "collect_missing_files",
    "is_overridden_in_prompt",
]
