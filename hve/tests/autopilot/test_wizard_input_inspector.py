"""D2: wizard_input_inspector の単体テスト。"""

from __future__ import annotations

from hve.autopilot.precheck_model import PrecheckCategory
from hve.gui.autopilot.wizard_input_inspector import (
    _REQUIRED_BY_WORKFLOW,
    _RequiredField,
    inspect_wizard_inputs,
)


def test_empty_required_returns_empty() -> None:
    # 既定では _REQUIRED_BY_WORKFLOW は空 → 必ず空結果
    items = inspect_wizard_inputs(["ard", "aad-web", "akm"], {})
    assert items == []


def test_required_field_missing_detected(monkeypatch) -> None:
    # 必須フィールド定義を一時注入
    sample = _RequiredField(
        name="foo",
        description="foo desc",
        remediation_hint="set foo",
    )
    monkeypatch.setitem(_REQUIRED_BY_WORKFLOW, "ard", [sample])
    items = inspect_wizard_inputs(["ard"], {"ard": {}})
    assert len(items) == 1
    it = items[0]
    assert it.category is PrecheckCategory.WIZARD_INPUT
    assert it.workflow_id == "ard"
    assert it.field_name == "foo"
    # cleanup
    _REQUIRED_BY_WORKFLOW.pop("ard", None)


def test_required_field_present_not_reported(monkeypatch) -> None:
    sample = _RequiredField(
        name="bar",
        description="bar desc",
        remediation_hint="set bar",
    )
    monkeypatch.setitem(_REQUIRED_BY_WORKFLOW, "ard", [sample])
    items = inspect_wizard_inputs(["ard"], {"ard": {"bar": "value"}})
    assert items == []
    _REQUIRED_BY_WORKFLOW.pop("ard", None)
