"""D5: Autopilot E2E フロー GUI テスト。

main_window レベルの統合は重いため、本テストは主要 API の連携を
PySide6 widget 単体組み合わせで検証する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from hve.autopilot.precheck_model import (
    AutopilotPrecheckResult,
    PrecheckCategory,
    PrecheckItem,
)
from hve.gui.autopilot.precheck_dialog import Step1PrecheckDialog
from hve.gui.page_options import OptionsPage  # noqa: F401  (他テストで間接使用予定)
from hve.gui.page_workflow_select import WorkflowSelectPage  # noqa: F401


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_precheck_dialog_renders_items(qapp) -> None:
    items = [
        PrecheckItem(
            category=PrecheckCategory.FILE,
            workflow_id="aad-web",
            field_name="docs/missing.md",
            description="missing",
            remediation_hint="create it",
        ),
        PrecheckItem(
            category=PrecheckCategory.AUTH,
            workflow_id="",
            field_name="github",
            description="not authenticated",
            remediation_hint="auth github",
        ),
    ]
    dlg = Step1PrecheckDialog(AutopilotPrecheckResult(items=items))
    assert dlg.result_data().count() == 2
    assert dlg.windowTitle()  # タイトル設定済み
