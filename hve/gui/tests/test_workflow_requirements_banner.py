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
from hve.gui.workflow_step_requirements import summarize_requirements  # noqa: E402


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
