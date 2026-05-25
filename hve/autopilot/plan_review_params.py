"""hve.autopilot.plan_review_params — パラメータ一覧収集（Qt 非依存）。

Wizard Step 2 必須入力 + Workflow-specific 設定を全件列挙する
（``precheck_*`` は「不足のみ」を返すのに対し、本モジュールは「全件 + 状態」を返す）。

Q1=a により Autopilot カタログパスは本モジュールの対象外（既存 FILE precheck の経路で扱う）。
"""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional

from .plan_review_model import ParameterCategory, ParameterEntry


# ``wizard_input_inspector._REQUIRED_BY_WORKFLOW`` を読み出してパラメータ表に展開する。
# 同モジュールは Qt 非依存のため直接 import 可。
# v2 改訂後: wizard_input_inspector モジュールは撤去済み（precheck の Wizard 検査は
# workflow_step_requirements に統一）。本 try/except は import 失敗時に空配列を返す。
def _wizard_required_fields(wf_id: str):
    try:
        from hve.gui.autopilot.wizard_input_inspector import (
            _REQUIRED_BY_WORKFLOW,  # type: ignore[attr-defined]
        )
    except Exception:
        return []
    return list(_REQUIRED_BY_WORKFLOW.get(wf_id, []))


def _setting_required_keys(wf_id: str):
    try:
        from hve.autopilot.precheck_settings import (
            _REQUIRED_SETTING_KEYS,  # type: ignore[attr-defined]
        )
    except Exception:
        return []
    return list(_REQUIRED_SETTING_KEYS.get(wf_id, []))


def _preview(value: Any) -> Optional[str]:
    """値のプレビュー文字列を返す（最大 80 文字、改行は記号化）。"""
    if value is None:
        return None
    if isinstance(value, str):
        s = value
    else:
        try:
            s = repr(value)
        except Exception:
            return None
    s = s.replace("\n", "⏎").replace("\r", "")
    if len(s) > 80:
        s = s[:77] + "..."
    return s


def _value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def collect_parameters(
    workflow_ids: Iterable[str],
    wizard_inputs_by_workflow: Optional[Mapping[str, Mapping[str, Any]]],
    settings_by_workflow: Optional[Mapping[str, Mapping[str, Any]]],
) -> List[ParameterEntry]:
    """選択 workflow について必須パラメータの状態を全件返す。

    Args:
        workflow_ids: 対象 workflow ID リスト。
        wizard_inputs_by_workflow: workflow_id → Wizard 入力 dict。
            ``None`` の場合は Wizard カテゴリを列挙しない。
        settings_by_workflow: workflow_id → Workflow Settings dict。
            ``None`` の場合は Setting カテゴリを列挙しない。
    """
    entries: List[ParameterEntry] = []

    for wf_id in workflow_ids:
        # WIZARD
        if wizard_inputs_by_workflow is not None:
            inputs = wizard_inputs_by_workflow.get(wf_id, {})
            for field in _wizard_required_fields(wf_id):
                name = getattr(field, "name", "")
                value = inputs.get(name) if isinstance(inputs, Mapping) else None
                entries.append(
                    ParameterEntry(
                        workflow_id=wf_id,
                        field_name=name,
                        category=ParameterCategory.WIZARD,
                        is_required=True,
                        value_present=_value_present(value),
                        value_preview=_preview(value),
                    )
                )

        # SETTING
        if settings_by_workflow is not None:
            values = settings_by_workflow.get(wf_id, {})
            for key in _setting_required_keys(wf_id):
                value = values.get(key) if isinstance(values, Mapping) else None
                entries.append(
                    ParameterEntry(
                        workflow_id=wf_id,
                        field_name=key,
                        category=ParameterCategory.SETTING,
                        is_required=True,
                        value_present=_value_present(value),
                        value_preview=_preview(value),
                    )
                )

    return entries


__all__ = ["collect_parameters"]
