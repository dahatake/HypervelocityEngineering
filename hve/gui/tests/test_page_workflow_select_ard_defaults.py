"""ARD ワークフロー選択時、Step 2/3/4 が既定 ON / Step 1 が既定 OFF であることを検証する。

要件: GUI Step 1 で `ard` を選択した際の「実行ステップ」チェックリスト初期状態は
{"2", "3", "4"} であること。
"""
from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

from hve.gui.page_workflow_select import WorkflowSelectPage, _WorkflowStepsGroup


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_ard_default_groups_definition() -> None:
    """`_ARD_GROUPS` の既定 ON フラグが Step 2/3/4 で True、Step 1 のみ False。"""
    defaults = {gid: on for gid, _title, on in _WorkflowStepsGroup._ARD_GROUPS}
    assert defaults == {"1": False, "2": True, "3": True, "4": True}


def test_ard_enabled_step_ids_default(qapp) -> None:
    """GUI 上で ARD を選択直後の `enabled_step_ids` が ["2", "3", "4"] になる。"""
    page = WorkflowSelectPage()

    for btn in page._group.buttons():  # type: ignore[attr-defined]
        if btn.property("workflow_id") == "ard":
            btn.setChecked(True)
            break

    grp = page._step_groups.get("ard")  # type: ignore[attr-defined]
    assert grp is not None
    assert grp.enabled_step_ids() == ["2", "3", "4"]
