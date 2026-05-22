"""hve.gui.tests.test_options_page_requirements_banner_integration

Task E: OptionsPage への必須要件サマリーバナー統合テスト。
WorkflowSelectPage 経由ではなく OptionsPage.update_requirements_banner を直接呼んで
配置先切替・状態反映を検証する（軽量テスト）。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.page_options import OptionsPage  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_page(qapp) -> OptionsPage:
    page = OptionsPage()
    page.set_workflows(["ard", "aad-web"])
    return page


def test_banner_hidden_when_no_selection(qapp):
    page = _make_page(qapp)
    page.update_requirements_banner([])
    assert page._banner_current_section is None
    assert page._requirements_banner.isVisible() is False


def test_banner_placed_in_c14_for_ard(qapp):
    page = _make_page(qapp)
    page.update_requirements_banner([("ard", ["1"])])
    assert page._banner_current_section == "C14"


def test_banner_placed_in_c10_for_aad_web(qapp):
    page = _make_page(qapp)
    page.update_requirements_banner([("aad-web", ["1"])])
    assert page._banner_current_section == "C10"


def test_priority_ard_wins_over_aad_web(qapp):
    page = _make_page(qapp)
    page.update_requirements_banner([("aad-web", ["1"]), ("ard", ["1"])])
    assert page._banner_current_section == "C14"


def test_banner_reflects_company_name_input(qapp):
    page = _make_page(qapp)
    page.update_requirements_banner([("ard", ["1"])])
    # 未入力 → warn
    page.c14.company_name.setText("")
    page._refresh_requirements_banner()
    # banner items に warn が含まれる
    summary_status_warn_count = sum(
        1 for lbl in page._requirements_banner.findChildren(
            __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel
        ) if "⚠" in lbl.text()
    )
    assert summary_status_warn_count >= 1
    # 入力後 → ok
    page.c14.company_name.setText("Acme")
    # textChanged 経由で自動更新されるはず
    qapp.processEvents()
    summary_status_warn_count2 = sum(
        1 for lbl in page._requirements_banner.findChildren(
            __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel
        ) if "⚠" in lbl.text()
    )
    assert summary_status_warn_count2 == 0


def test_banner_switches_section_dynamically(qapp):
    page = _make_page(qapp)
    page.update_requirements_banner([("ard", ["1"])])
    assert page._banner_current_section == "C14"
    page.update_requirements_banner([("aad-web", ["1"])])
    assert page._banner_current_section == "C10"
    page.update_requirements_banner([])
    assert page._banner_current_section is None
