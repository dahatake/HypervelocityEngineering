"""Step 1 / Step 2 / Window タイトル のワークフロー表示書式テスト。"""

from __future__ import annotations

import sys

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QCheckBox  # noqa: E402


@pytest.fixture(scope="module")
def _qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def test_workflow_select_checkbox_labels_use_unified_format(_qapp):
    from hve.gui.page_workflow_select import WorkflowSelectPage

    page = WorkflowSelectPage()
    labels = [
        btn.text()
        for btn in page._group.buttons()
        if isinstance(btn, QCheckBox)
    ]
    # registry に存在する代表的なワークフロー表記
    assert any(lbl == "Architecture Design (AAS)" for lbl in labels)
    assert any(lbl == "Auto Requirement Definition (ARD)" for lbl in labels)
    assert any(lbl == "AI Agent Design (AAG)" for lbl in labels)
    # 旧書式 ("aas  —  Architecture Design") が残っていないこと
    assert not any("  —  " in lbl for lbl in labels)


def test_options_page_title_single_workflow(_qapp):
    """OptionsPage の画面内タイトル（_title_label）は本リファクタリングで削除済み。

    タイトル表示は親ページ (WorkflowSelectPage) のヘッダに統合されたため、
    OptionsPage 自身は title 属性を持たない。set_workflows が例外なく完了することを検証。
    """
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.set_workflows(["ard"], {"ard": "Auto Requirement Definition"})
    assert not hasattr(page, "_title_label")


def test_options_page_title_multi_workflow(_qapp):
    """同上: 複数ワークフロー指定時も例外なく完了。"""
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.set_workflows(
        ["aas", "aag"],
        {"aas": "Architecture Design", "aag": "AI Agent Design"},
    )
    assert not hasattr(page, "_title_label")
    assert page._workflow_ids == ["aas", "aag"]
