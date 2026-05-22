"""hve.gui.autopilot.wizard_input_inspector — Wizard Step 2 必須項目の検査（Qt 非依存）。

現状の `PageOptions` には強制必須項目はほぼ存在しないため、本モジュールは
Workflow ごとに「Autopilot 実行時に欠落していると失敗が確定する Step 2 入力」を
宣言的に定義し、収集された input dict を検査する拡張点として機能する。

入力 dict は `PageOptions.build_args_for_workflow()` 戻り値 `OrchestrateArgs` を
辞書化したもの、または同等のキー集合（``model`` / ``target_business`` 等）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping

from hve.autopilot.precheck_model import PrecheckCategory, PrecheckItem


@dataclass(frozen=True)
class _RequiredField:
    name: str
    description: str
    remediation_hint: str
    # 値が「未入力」と判定される条件。既定: None または空文字。
    predicate: Callable[[Any], bool] = lambda v: v is None or (
        isinstance(v, str) and not v.strip()
    )


# Workflow ごとの Autopilot 時必須 Wizard 入力。
# 現状はほぼ空（PageOptions が既定値を埋めるため）。将来の拡張点として残置。
_REQUIRED_BY_WORKFLOW: Dict[str, List[_RequiredField]] = {
    # 例: ARD の target_business は通常 AttachmentPane から自動補完されるため必須ではない。
    # "ard": [
    #     _RequiredField(
    #         name="target_business",
    #         description="ARD: 対象事業情報ファイル",
    #         remediation_hint="Step 2 の Attachment ペインで対象事業ファイルを指定してください。",
    #     ),
    # ],
}


def inspect_wizard_inputs(
    workflow_ids: Iterable[str],
    inputs_by_workflow: Mapping[str, Mapping[str, Any]],
) -> List[PrecheckItem]:
    """Workflow ごとに Step 2 入力 dict を検査し不足項目を返す。

    Args:
        workflow_ids: 対象 workflow ID リスト。
        inputs_by_workflow: workflow_id → 入力 dict（``OrchestrateArgs`` の vars 等）。

    Returns:
        不足 ``PrecheckItem`` リスト。
    """
    items: List[PrecheckItem] = []
    for wf_id in workflow_ids:
        required = _REQUIRED_BY_WORKFLOW.get(wf_id, [])
        if not required:
            continue
        inputs = inputs_by_workflow.get(wf_id, {})
        for field in required:
            value = inputs.get(field.name)
            if field.predicate(value):
                items.append(
                    PrecheckItem(
                        category=PrecheckCategory.WIZARD_INPUT,
                        workflow_id=wf_id,
                        step_id=None,
                        field_name=field.name,
                        description=field.description,
                        remediation_hint=field.remediation_hint,
                    )
                )
    return items


__all__ = ["inspect_wizard_inputs"]
