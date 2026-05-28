"""T1 回帰防止: クリック順に依らず `_steps_layout` 内の表示順がワークフロー正準順になる。

要件: 画面左下「実行ステップ」のワークフロー表示順は、ユーザーがチェックを入れた
順番ではなく、ワークフロー定義の正準順（カテゴリー定義 `_WORKFLOW_CATEGORIES` 由来）
に必ず整列されること。
"""
from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

from hve.gui.page_workflow_select import WorkflowSelectPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _check_workflow(page: WorkflowSelectPage, wf_id: str) -> None:
    for btn in page._group.buttons():  # type: ignore[attr-defined]
        if btn.property("workflow_id") == wf_id:
            btn.setChecked(True)
            return
    raise AssertionError(f"workflow checkbox not found: {wf_id}")


def test_steps_panel_keeps_workflow_canonical_order(qapp) -> None:
    """AAD-WEB → ARD のクリック順でも、layout 上の表示順は ARD → AAD-WEB。"""
    page = WorkflowSelectPage()

    _check_workflow(page, "aad-web")
    _check_workflow(page, "ard")

    layout = page._steps_layout  # type: ignore[attr-defined]
    groups = page._step_groups  # type: ignore[attr-defined]

    ard_idx = layout.indexOf(groups["ard"])
    aad_idx = layout.indexOf(groups["aad-web"])

    assert ard_idx >= 0 and aad_idx >= 0
    assert ard_idx < aad_idx, (
        f"ARD ({ard_idx}) は AAD-WEB ({aad_idx}) より上に並ぶべき"
    )
