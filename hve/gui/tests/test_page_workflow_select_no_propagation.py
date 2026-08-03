"""T1: 実行ステップの依存伝播を撤廃したことの回帰防止。

要件: 非 ARD ワークフロー（例: asdw-web）でステップを ON/OFF しても、
他のステップ（前段・後段とも）のチェック状態が連動して変化しないこと。
依存伝播削除により、前段ステップを OFF にしたまま途中ステップ（例: 2.1）
だけを選択できる。
"""
from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

from hve.gui.page_workflow_select import WorkflowSelectPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _select_workflow(page: WorkflowSelectPage, wf_id: str) -> None:
    for btn in page._group.buttons():  # type: ignore[attr-defined]
        if btn.property("workflow_id") == wf_id:
            btn.setChecked(True)
            return
    raise AssertionError(f"workflow checkbox not found: {wf_id}")


def test_unchecking_predecessor_does_not_disable_successor(qapp) -> None:
    """前段 1.1 を OFF にしても後段 2.1 は ON のまま（OFF→後段自動 OFF の撤廃）。"""
    page = WorkflowSelectPage()
    _select_workflow(page, "asdw-web")
    grp = page._step_groups.get("asdw-web")  # type: ignore[attr-defined]
    assert grp is not None

    # 前提（捏造防止）: 1.1 と 2.1 はいずれも存在し初期 ON。
    assert "1.1" in grp._checkboxes and "2.1" in grp._checkboxes
    cb_11 = grp._checkboxes["1.1"]
    cb_21 = grp._checkboxes["2.1"]
    assert cb_11.isChecked() and cb_21.isChecked()

    # 1.1 を OFF にする
    cb_11.setChecked(False)

    # 後段 2.1 は影響を受けず ON のまま（依存伝播なし）
    assert cb_21.isChecked() is True
    assert "2.1" in grp.enabled_step_ids()
    assert "1.1" not in grp.enabled_step_ids()


def test_checking_successor_does_not_enable_predecessor(qapp) -> None:
    """途中ステップ 2.1 を ON にしても前段 1.1 は自動 ON されない（ON→前段自動 ON の撤廃）。"""
    page = WorkflowSelectPage()
    _select_workflow(page, "asdw-web")
    grp = page._step_groups.get("asdw-web")  # type: ignore[attr-defined]
    assert grp is not None

    # いったん全 OFF にしてから 2.1 のみ ON にする
    for cb in grp._checkboxes.values():
        cb.setChecked(False)
    assert grp.enabled_step_ids() == []

    grp._checkboxes["2.1"].setChecked(True)

    # 2.1 のみが ON。前段 1.1/1.2/1.3 は OFF のまま（依存元を自動 ON しない）。
    assert grp.enabled_step_ids() == ["2.1"]
    assert grp._checkboxes["1.1"].isChecked() is False
    assert grp._checkboxes["1.3"].isChecked() is False
