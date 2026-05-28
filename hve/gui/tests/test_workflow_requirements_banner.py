"""hve.gui.tests.test_workflow_requirements_banner

Task B: WorkflowRequirementsBanner Widget の smoke テスト。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from hve.gui.workflow_requirements_banner import WorkflowRequirementsBanner  # noqa: E402
from hve.gui.workflow_step_requirements import (  # noqa: E402
    AUTOPILOT_PSEUDO_STEP_ID,
    AUTOPILOT_PSEUDO_WORKFLOW_ID,
    summarize_requirements,
    summarize_requirements_for_selection,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_default_shows_neutral_message(qapp):
    banner = WorkflowRequirementsBanner()
    # set_summary(None) は __init__ で呼ばれる
    text = banner.findChildren(QLabel)[1].text()  # 0=header, 1=guidance
    assert "ワークフロー" in text or "必要条件" in text


def test_set_summary_warn_shows_items(qapp):
    banner = WorkflowRequirementsBanner()
    s = summarize_requirements("ard", "1", input_values={"company_name": ""})
    banner.set_summary(s)
    # 項目に "company_name" の警告ラベルが含まれる
    labels = [w.text() for w in banner.findChildren(QLabel)]
    joined = "\n".join(labels)
    assert "company_name" in joined
    assert "⚠" in joined


def test_set_summary_ok_shows_check(qapp):
    banner = WorkflowRequirementsBanner()
    s = summarize_requirements(
        "asdw-web", "1.1",
        input_values={"resource_group": "rg-prod"},
        file_exists=lambda _p: True,
    )
    banner.set_summary(s)
    labels = [w.text() for w in banner.findChildren(QLabel)]
    joined = "\n".join(labels)
    assert "✅" in joined
    assert "resource_group" in joined


def test_set_summary_none_resets(qapp):
    banner = WorkflowRequirementsBanner()
    s = summarize_requirements("ard", "1", input_values={"company_name": ""})
    banner.set_summary(s)
    # 一度 warn にしてから None で戻す
    banner.set_summary(None)
    labels = [w.text() for w in banner.findChildren(QLabel)]
    joined = "\n".join(labels)
    # 警告アイコンが消えていることを確認
    assert "company_name" not in joined


# --------------------------------------------------------------------------
# v2: Autopilot 仮想ワークフロー / 共通入口テスト
# --------------------------------------------------------------------------


def test_autopilot_summary_warn_when_catalog_missing():
    s = summarize_requirements(
        AUTOPILOT_PSEUDO_WORKFLOW_ID,
        AUTOPILOT_PSEUDO_STEP_ID,
        file_exists=lambda _p: False,
    )
    assert s is not None
    assert s.overall_status == "warn"
    assert any(it.label.endswith("app-arch-catalog.md") for it in s.items)


def test_autopilot_summary_ok_when_catalog_present():
    s = summarize_requirements(
        AUTOPILOT_PSEUDO_WORKFLOW_ID,
        AUTOPILOT_PSEUDO_STEP_ID,
        file_exists=lambda _p: True,
    )
    assert s is not None
    assert s.overall_status == "ok"


def test_autopilot_summary_custom_catalog_path():
    seen: list = []

    def fe(p: str) -> bool:
        seen.append(p)
        return True

    s = summarize_requirements(
        AUTOPILOT_PSEUDO_WORKFLOW_ID,
        AUTOPILOT_PSEUDO_STEP_ID,
        file_exists=fe,
        autopilot_catalog_path="custom/my.md",
    )
    assert s is not None
    assert "custom/my.md" in seen


def test_for_selection_autopilot_mode_returns_single_summary():
    results = summarize_requirements_for_selection(
        [("aas", ["1"]), ("aad-web", ["1"])],
        file_exists=lambda _p: False,
        autopilot_mode=True,
    )
    assert len(results) == 1
    assert results[0].workflow_id == AUTOPILOT_PSEUDO_WORKFLOW_ID


def test_for_selection_normal_mode_returns_priority_workflow_only():
    """非 Autopilot モードはバナーと同じ挙動で 1 件のみ返す（最優先 WF のエントリ）。"""
    results = summarize_requirements_for_selection(
        [("ard", ["1"]), ("aas", ["1"])],
        input_values={"company_name": "Contoso"},
        file_exists=lambda _p: False,
    )
    # WORKFLOW_PRIORITY 順で ard が最優先 → 1 件のみ
    assert len(results) == 1
    assert results[0].workflow_id == "ard"


def test_for_selection_skips_priority_when_no_table_entry():
    """最優先 WF にステップ未選択なら次優先 WF が選ばれる。"""
    results = summarize_requirements_for_selection(
        [("ard", []), ("aas", ["1"])],
        file_exists=lambda _p: False,
    )
    assert len(results) == 1
    assert results[0].workflow_id == "aas"


# --------------------------------------------------------------------------
# Autopilot ON 時に SE 系 WF（aad-web/asdw-web/adfd/adfdv）が未選択なら
# Autopilot 仮想ではなく通常モード（pick_target_step）と同じ要件を返す。
# 回帰防止: バナーが ARD/AAS のみ選択時にも app-arch-catalog.md を warn 表示する
# 不具合を防止する。
# --------------------------------------------------------------------------


def test_for_selection_autopilot_mode_falls_back_when_no_se_workflows():
    """Autopilot ON + ARD/AAS のみ選択 → Autopilot 仮想ではなく ARD 要件を返す。"""
    results = summarize_requirements_for_selection(
        [("ard", ["1"]), ("aas", ["1"])],
        input_values={"company_name": "Contoso"},
        file_exists=lambda _p: False,
        autopilot_mode=True,
    )
    assert len(results) == 1
    # Autopilot 仮想ではなく通常優先順位の ARD が選ばれる
    assert results[0].workflow_id == "ard"
    # app-arch-catalog.md 由来の warn 項目は含まれない
    assert not any(
        it.label.endswith("app-arch-catalog.md") for it in results[0].items
    )


def test_for_selection_autopilot_mode_uses_pseudo_when_se_workflow_selected():
    """Autopilot ON + aad-web 選択 → Autopilot 仮想サマリー（catalog チェック実施）。"""
    results = summarize_requirements_for_selection(
        [("ard", ["1"]), ("aad-web", ["1"])],
        input_values={"company_name": "Contoso"},
        file_exists=lambda _p: False,
        autopilot_mode=True,
    )
    assert len(results) == 1
    assert results[0].workflow_id == AUTOPILOT_PSEUDO_WORKFLOW_ID
    assert results[0].overall_status == "warn"
    assert any(
        it.label.endswith("app-arch-catalog.md") for it in results[0].items
    )


def test_for_selection_autopilot_mode_ignores_se_workflow_with_empty_steps():
    """SE 系 WF が登録されてもステップ未選択なら Autopilot 仮想は使わない。"""
    results = summarize_requirements_for_selection(
        [("ard", ["1"]), ("aad-web", [])],
        input_values={"company_name": "Contoso"},
        file_exists=lambda _p: False,
        autopilot_mode=True,
    )
    assert len(results) == 1
    # aad-web はステップ未選択なので Autopilot 仮想にならず、ARD が選ばれる
    assert results[0].workflow_id == "ard"


