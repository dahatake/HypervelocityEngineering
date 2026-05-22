"""hve.autopilot.plan_review_collector — チェック済み全ステップの入出力収集（Qt 非依存）。

`build_step1_plan_review()`（旧名: ``build_autopilot_plan_review()``）から呼び出される。

責務:
  - 選択 workflow / 有効 step の集合から
    - 全 ``required_input_paths`` を ``PlannedInput`` として列挙
    - 全 ``output_paths`` を ``PlannedOutput`` として列挙
  - 既存ファイル（mtime / size）を実測
  - ``status`` の確定は ``plan_review_gap`` 側で行う（producer 解決を伴うため）

ファイル存在判定は ``required_input_paths`` の glob を考慮した最小実装。
（既存 ``precheck_collector._path_exists`` と整合）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .plan_review_model import (
    FileStatus,
    PlannedInput,
    PlannedOutput,
)


def _path_exists(repo_root: Path, pattern: str) -> bool:
    """単純パス存在チェック（``precheck_collector`` と同等仕様）。"""
    if not pattern:
        return True
    if any(ch in pattern for ch in ("*", "?", "[")):
        try:
            return any(repo_root.glob(pattern))
        except (OSError, ValueError):
            return False
    return (repo_root / pattern).exists()


def _file_meta(repo_root: Path, rel: str) -> Tuple[Optional[str], Optional[int]]:
    """既存ファイルの mtime/size を返す。取得失敗時は (None, None)。"""
    try:
        p = repo_root / rel
        if not p.is_file():
            return None, None
        st = p.stat()
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
        return mtime, st.st_size
    except (OSError, ValueError):
        return None, None


def _iter_target_steps(
    workflow_ids: Iterable[str],
    steps_by_workflow: Dict[str, List[str]],
):
    """選択 workflow × 有効 step を ``(wf_id, StepDef)`` として yield。

    ``steps_by_workflow`` に当該 wf_id が含まれる場合のみそのリストを対象。
    含まれない場合は **対象 step ゼロ**（=明示指定なし → 列挙しない）。
    """
    try:
        from hve.workflow_registry import get_workflow
    except Exception:
        return

    for wf_id in workflow_ids:
        if wf_id not in steps_by_workflow:
            continue
        wf = get_workflow(wf_id)
        if wf is None:
            continue
        target_ids = set(steps_by_workflow[wf_id])
        for step in wf.steps:
            if step.is_container:
                continue
            if step.id not in target_ids:
                continue
            yield wf_id, step


def collect_planned_inputs(
    workflow_ids: Iterable[str],
    repo_root: Path,
    *,
    steps_by_workflow: Dict[str, List[str]],
) -> List[PlannedInput]:
    """チェック済み全ステップの ``required_input_paths`` を列挙。

    ``status`` は仮置きで以下のように決定:
      - 既存ファイルあり → ``EXISTING_REUSABLE``
      - 不在            → ``MISSING_GAP``（``MISSING_PRODUCED`` への昇格は gap 側で再判定）
    """
    results: List[PlannedInput] = []
    for wf_id, step in _iter_target_steps(workflow_ids, steps_by_workflow):
        for rel in step.required_input_paths:
            if _path_exists(repo_root, rel):
                status = FileStatus.EXISTING_REUSABLE
            else:
                status = FileStatus.MISSING_GAP
            results.append(
                PlannedInput(
                    workflow_id=wf_id,
                    step_id=step.id,
                    path=rel,
                    status=status,
                    producer=None,
                )
            )
    return results


def collect_planned_outputs(
    workflow_ids: Iterable[str],
    repo_root: Path,
    *,
    steps_by_workflow: Dict[str, List[str]],
) -> List[PlannedOutput]:
    """チェック済み全ステップの ``output_paths`` を列挙。

    ``output_paths`` が空のステップは結果に含めない（``UNKNOWN`` 表現は
    入力側の status で扱う方針）。
    """
    results: List[PlannedOutput] = []
    for wf_id, step in _iter_target_steps(workflow_ids, steps_by_workflow):
        for rel in step.output_paths:
            exists = _path_exists(repo_root, rel)
            mtime, size = _file_meta(repo_root, rel) if exists else (None, None)
            results.append(
                PlannedOutput(
                    workflow_id=wf_id,
                    step_id=step.id,
                    path=rel,
                    already_exists=exists,
                    mtime_iso=mtime,
                    size_bytes=size,
                )
            )
    return results


__all__ = [
    "collect_planned_inputs",
    "collect_planned_outputs",
    "_path_exists",
    "_file_meta",
    "_iter_target_steps",
]
