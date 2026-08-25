"""ARD ワークフロー選択時、Step 2〜5 が既定 ON / Step 1 が既定 OFF であることを検証する。

要件: GUI Step 1 で `ard` を選択した際の「実行ステップ」チェックリスト初期状態は
{"2", "3", "4", "5"} であること。
"""
from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

from hve.gui.page_workflow_select import WorkflowSelectPage, _WorkflowStepsGroup
from hve import workflow_registry


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_ard_group_definition_has_the_five_required_ids() -> None:
    assert [gid for gid, _title in _WorkflowStepsGroup._ARD_GROUPS] == [
        "1",
        "2",
        "3",
        "4",
        "5",
    ]


def test_ard_enabled_step_ids_default(qapp) -> None:
    """GUI 上で ARD を選択直後の `enabled_step_ids` が ["2", "3", "4"] になる。"""
    page = WorkflowSelectPage()

    for btn in page._group.buttons():  # type: ignore[attr-defined]
        if btn.property("workflow_id") == "ard":
            btn.setChecked(True)
            break

    grp = page._step_groups.get("ard")  # type: ignore[attr-defined]
    assert grp is not None
    assert set(grp.enabled_step_ids()) == {"2", "3", "4", "5"}
    assert set(grp.enabled_step_ids()) == set(workflow_registry.ARD_DEFAULT_GROUP_IDS)


def test_ard_default_groups_are_resolved_when_the_widget_is_created(
    qapp, monkeypatch
) -> None:
    monkeypatch.setattr(workflow_registry, "ARD_DEFAULT_GROUP_IDS", ("1", "4"))
    grp = _WorkflowStepsGroup("ard", "ARD", [])
    assert grp.enabled_step_ids() == ["1", "4"]


@pytest.mark.parametrize(
    "invalid, message",
    [(("2", "2"), "重複"), (("2", "9"), "未登録")],
)
def test_invalid_ard_default_groups_fail_closed(
    qapp, monkeypatch, invalid, message
) -> None:
    monkeypatch.setattr(workflow_registry, "ARD_DEFAULT_GROUP_IDS", invalid)
    with pytest.raises(ValueError, match=message):
        _WorkflowStepsGroup("ard", "ARD", [])


def test_registry_import_failure_degrades_to_all_groups_off(qapp, monkeypatch) -> None:
    monkeypatch.setattr(
        "hve.gui.page_workflow_select._load_ard_default_group_ids",
        lambda: None,
    )
    grp = _WorkflowStepsGroup("ard", "ARD", [])
    assert grp.enabled_step_ids() == []
