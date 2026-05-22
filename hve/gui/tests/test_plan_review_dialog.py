"""hve.gui.autopilot.plan_review_dialog のテスト（pytest-qt 不要、PySide6 直接）。"""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from hve.autopilot.plan_review_model import (
    AutopilotPlanReview,
    FileStatus,
    GapSuggestion,
    ParameterCategory,
    ParameterEntry,
    PlannedInput,
    PlannedOutput,
)
from hve.gui.autopilot.plan_review_dialog import Step1PlanReviewDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _sample_review() -> AutopilotPlanReview:
    return AutopilotPlanReview(
        inputs=[
            PlannedInput("aas", "1", "docs/a.md", FileStatus.EXISTING_REUSABLE),
            PlannedInput("aad-web", "1", "docs/b.md", FileStatus.MISSING_PRODUCED,
                         producer=("aas", "1")),
            PlannedInput("aad-web", "1", "docs/c.md", FileStatus.MISSING_GAP),
        ],
        outputs=[
            PlannedOutput("aas", "1", "docs/out1.md", already_exists=False),
            PlannedOutput("aas", "1", "docs/out2.md", already_exists=True,
                          mtime_iso="2026-01-01T00:00:00+00:00", size_bytes=42),
        ],
        parameters=[
            ParameterEntry("aas", "field_x", ParameterCategory.WIZARD,
                           is_required=True, value_present=False, value_preview=None),
        ],
        gaps=[
            GapSuggestion(missing_path="docs/c.md",
                          suggested_workflow_id="ard",
                          suggested_step_id="1",
                          transitive_steps=["1"]),
        ],
    )


def test_dialog_constructs(qapp) -> None:
    dlg = Step1PlanReviewDialog(_sample_review())
    assert dlg.windowTitle()
    assert dlg.review().inputs[0].path == "docs/a.md"


def test_dialog_empty_review(qapp) -> None:
    dlg = Step1PlanReviewDialog(AutopilotPlanReview())
    # 4 タブが揃っており、ギャップなしメッセージが表示される
    assert dlg.review().has_blocking_gaps is False


def test_regenerate_checkboxes_only_for_existing(qapp) -> None:
    dlg = Step1PlanReviewDialog(_sample_review())
    # 既存ファイル (out2) のチェックボックスは enable、out1 は disable
    cb_existing = dlg._regen_checkboxes[("aas", "1", "docs/out2.md")]
    cb_missing = dlg._regen_checkboxes[("aas", "1", "docs/out1.md")]
    assert cb_existing.isEnabled() is True
    assert cb_missing.isEnabled() is False


def test_gaps_applied_signal(qapp) -> None:
    review = _sample_review()
    dlg = Step1PlanReviewDialog(review)
    captured: list = []
    dlg.gaps_applied.connect(lambda gs: captured.extend(gs))
    # 全 gap のチェックは初期 ON
    dlg._on_apply_clicked()
    assert len(captured) == 1
    assert captured[0].suggested_workflow_id == "ard"


def test_selected_regenerate_paths(qapp) -> None:
    dlg = Step1PlanReviewDialog(_sample_review())
    cb = dlg._regen_checkboxes[("aas", "1", "docs/out2.md")]
    cb.setChecked(True)
    sel = dlg.selected_regenerate_paths()
    assert ("aas", "1", "docs/out2.md") in sel


def test_execution_order_label_shown_when_provided(qapp) -> None:
    """E=2: execution_order が指定されたとき Dialog に「実行順序: ...」ラベルが表示される。"""
    from PySide6.QtWidgets import QLabel

    review = AutopilotPlanReview(
        execution_order=["ard", "aas", "aad-web", "asdw-web"],
    )
    dlg = Step1PlanReviewDialog(review)
    labels = dlg.findChildren(QLabel)
    texts = [lbl.text() for lbl in labels]
    matching = [t for t in texts if "実行順序" in t and "ARD" in t and "AAS" in t]
    assert matching, f"実行順序ラベルが見つかりません: {texts}"
    assert "ARD → AAS → AAD-WEB → ASDW-WEB" in matching[0]


def test_execution_order_label_hidden_when_empty(qapp) -> None:
    """execution_order が空のときはラベルが表示されない（既存挙動互換）。"""
    from PySide6.QtWidgets import QLabel

    review = AutopilotPlanReview()
    dlg = Step1PlanReviewDialog(review)
    labels = dlg.findChildren(QLabel)
    texts = [lbl.text() for lbl in labels]
    assert not any("実行順序" in t for t in texts)
