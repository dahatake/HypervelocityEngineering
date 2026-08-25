"""hve.gui.tests.test_github_issue_mode

FR-GUI-25: Root Issue を「新規作成」/「既存 Issue へ連携」から選ぶ UI の単体テスト（offscreen）。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtGui import QIntValidator  # noqa: E402
from PySide6.QtWidgets import QApplication, QGroupBox, QWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _group_of(widget: QWidget):
    parent = widget.parentWidget()
    while parent is not None and not isinstance(parent, QGroupBox):
        parent = parent.parentWidget()
    return parent if isinstance(parent, QGroupBox) else None


@pytest.fixture
def section(qapp):
    from hve.gui.page_options import _C5IssuePR

    return _C5IssuePR()


class TestIssueModeWidgets:
    def test_mode_offers_new_and_existing(self, section) -> None:
        values = [
            section.issue_mode.itemData(i) for i in range(section.issue_mode.count())
        ]
        assert values == ["new", "existing"]

    def test_default_mode_is_new(self, section) -> None:
        assert section.issue_mode.currentData() == "new"

    def test_issue_number_disabled_in_new_mode(self, section) -> None:
        assert not section.issue_number.isEnabled()
        assert section.issue_title.isEnabled()

    def test_issue_number_enabled_in_existing_mode(self, section) -> None:
        section.issue_mode.setCurrentIndex(section.issue_mode.findData("existing"))
        assert section.issue_number.isEnabled()

    def test_issue_title_disabled_in_existing_mode(self, section) -> None:
        """既存 Issue 連携では Root Issue タイトルの上書きは意味を持たない。"""
        section.issue_mode.setCurrentIndex(section.issue_mode.findData("existing"))
        assert not section.issue_title.isEnabled()

    def test_switching_back_restores_new_mode(self, section) -> None:
        section.issue_mode.setCurrentIndex(section.issue_mode.findData("existing"))
        section.issue_mode.setCurrentIndex(section.issue_mode.findData("new"))
        assert not section.issue_number.isEnabled()
        assert section.issue_title.isEnabled()

    def test_issue_number_accepts_digits_only(self, section) -> None:
        assert isinstance(section.issue_number.validator(), QIntValidator)

    def test_widgets_are_in_repository_group(self, section) -> None:
        for widget in (section.issue_mode, section.issue_number):
            group = _group_of(widget)
            assert group is not None
            assert group.title() == "リポジトリ / Issue 設定"


class TestOptionsPageValidation:
    def _page(self):
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        page.set_workflows(["aad-web"], {"aad-web": "aad-web"})
        page.c3.auto_qa.set_tristate(False)
        return page

    def test_existing_mode_without_number_blocks_run(self, qapp) -> None:
        page = self._page()
        try:
            page.c5.create_issues.setChecked(True)
            page.c5.issue_mode.setCurrentIndex(page.c5.issue_mode.findData("existing"))
            page.c5.issue_number.setText("")
            ok, message = page.validate()
            assert ok is False
            assert "Issue 番号" in message
        finally:
            page.deleteLater()

    def test_existing_mode_with_number_passes(self, qapp) -> None:
        page = self._page()
        try:
            page.c5.create_issues.setChecked(True)
            page.c5.issue_mode.setCurrentIndex(page.c5.issue_mode.findData("existing"))
            page.c5.issue_number.setText("1234")
            ok, _message = page.validate()
            assert ok is True
        finally:
            page.deleteLater()

    def test_new_mode_is_unaffected(self, qapp) -> None:
        page = self._page()
        try:
            page.c5.create_issues.setChecked(True)
            page.c5.issue_number.setText("")
            ok, _message = page.validate()
            assert ok is True
        finally:
            page.deleteLater()

    def test_existing_mode_without_create_issues_is_unaffected(self, qapp) -> None:
        """`--create-issues` を伴わない場合は実行を止めない（CLI 側が警告する）。"""
        page = self._page()
        try:
            page.c5.create_issues.setChecked(False)
            page.c5.issue_mode.setCurrentIndex(page.c5.issue_mode.findData("existing"))
            page.c5.issue_number.setText("")
            ok, _message = page.validate()
            assert ok is True
        finally:
            page.deleteLater()
