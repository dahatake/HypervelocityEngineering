"""GUI Step 1 ワークフロー選択のカテゴリー表示（FR-GUI-21）。

`AI Agent` カテゴリーの見出しと、その直下に並ぶ AAG / AAGD / AAR、
および各行のヘルプボタン生成を検証する。
"""

from __future__ import annotations

import sys
from typing import List, Tuple

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel

from hve.gui.help_popup import HelpPopupButton
from hve.gui.page_workflow_select import WorkflowSelectPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _entries(page: WorkflowSelectPage) -> List[Tuple[str, str]]:
    """ワークフロー一覧の並びを ``("header", 見出し)`` / ``("workflow", id)`` で返す。"""
    buttons = page._group.buttons()  # type: ignore[attr-defined]
    assert buttons, "ワークフローのチェックボックスが 1 つも生成されていない"
    container = buttons[0].parentWidget().parentWidget()
    layout = container.layout()
    assert layout is not None

    entries: List[Tuple[str, str]] = []
    for i in range(layout.count()):
        widget = layout.itemAt(i).widget()
        if widget is None:
            continue
        if isinstance(widget, QLabel):
            if widget.property("hveRole") == "sectionHeader":
                entries.append(("header", widget.text()))
            continue
        for checkbox in widget.findChildren(QCheckBox):
            wf_id = checkbox.property("workflow_id")
            if isinstance(wf_id, str):
                entries.append(("workflow", wf_id))
    return entries


class TestAiAgentCategory:
    """`AI Agent` カテゴリーの見出しと構成員。"""

    def test_ai_agent_header_is_present(self, qapp) -> None:
        headers = [text for kind, text in _entries(WorkflowSelectPage()) if kind == "header"]
        assert any("AI Agent" in text for text in headers)

    def test_other_bucket_is_not_rendered(self, qapp) -> None:
        headers = [text for kind, text in _entries(WorkflowSelectPage()) if kind == "header"]
        assert not any("その他" in text for text in headers)

    def test_ai_agent_workflows_follow_the_header(self, qapp) -> None:
        entries = _entries(WorkflowSelectPage())
        header_index = next(
            i for i, (kind, text) in enumerate(entries)
            if kind == "header" and "AI Agent" in text
        )
        following = [
            wf_id for kind, wf_id in entries[header_index + 1:] if kind == "workflow"
        ]
        assert following[:4] == ["ada", "aag", "aagd", "aar"]

    def test_ai_agent_workflows_have_help_buttons(self, qapp) -> None:
        page = WorkflowSelectPage()
        by_id = {
            btn.property("workflow_id"): btn
            for btn in page._group.buttons()  # type: ignore[attr-defined]
        }
        for wf_id in ("aag", "aagd", "aar"):
            row = by_id[wf_id].parentWidget()
            assert row.findChildren(HelpPopupButton), f"{wf_id} のヘルプボタンが無い"

    def test_every_registered_workflow_is_listed(self, qapp) -> None:
        from hve.workflow_registry import list_workflows

        listed = [wf_id for kind, wf_id in _entries(WorkflowSelectPage()) if kind == "workflow"]
        assert sorted(listed) == sorted(wf.id for wf in list_workflows())
