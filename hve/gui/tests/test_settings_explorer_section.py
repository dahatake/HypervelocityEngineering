"""hve.gui.settings_window._CExplorerSection のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from hve.gui.settings_window import _CExplorerSection


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_initial_state_empty(qapp, tmp_path: Path) -> None:
    sec = _CExplorerSection(tmp_path)
    assert sec.explorer_roots.text() == ""
    assert sec._list.count() == 0


def test_set_text_populates_list(qapp, tmp_path: Path) -> None:
    sec = _CExplorerSection(tmp_path)
    sec.explorer_roots.setText("docs;qa;knowledge")
    assert sec._list.count() == 3
    items = [sec._list.item(i).text() for i in range(sec._list.count())]
    assert items == ["docs", "qa", "knowledge"]


def test_set_text_strips_whitespace_and_skips_empty(qapp, tmp_path: Path) -> None:
    sec = _CExplorerSection(tmp_path)
    sec.explorer_roots.setText("docs; ;qa;;knowledge ")
    items = [sec._list.item(i).text() for i in range(sec._list.count())]
    assert items == ["docs", "qa", "knowledge"]


def test_add_via_dialog_relative_path(qapp, tmp_path: Path) -> None:
    sec = _CExplorerSection(tmp_path)
    target = tmp_path / "docs"
    target.mkdir()

    # QFileDialog をスタブ化
    class _FakeDialog:
        @staticmethod
        def getExistingDirectory(*_args, **_kwargs):
            return str(target)

    sec._file_dialog_factory = _FakeDialog
    sec._on_add_clicked()

    assert sec.explorer_roots.text() == "docs"
    assert sec._list.count() == 1


def test_add_via_dialog_absolute_path_outside_repo(qapp, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "external"
    outside.mkdir()

    sec = _CExplorerSection(repo)

    class _FakeDialog:
        @staticmethod
        def getExistingDirectory(*_args, **_kwargs):
            return str(outside)

    sec._file_dialog_factory = _FakeDialog
    sec._on_add_clicked()

    assert sec.explorer_roots.text() == outside.resolve().as_posix()


def test_add_dialog_cancelled_does_nothing(qapp, tmp_path: Path) -> None:
    sec = _CExplorerSection(tmp_path)
    sec.explorer_roots.setText("docs")

    class _FakeDialog:
        @staticmethod
        def getExistingDirectory(*_args, **_kwargs):
            return ""

    sec._file_dialog_factory = _FakeDialog
    sec._on_add_clicked()

    assert sec.explorer_roots.text() == "docs"


def test_add_skips_duplicate(qapp, tmp_path: Path) -> None:
    sec = _CExplorerSection(tmp_path)
    (tmp_path / "docs").mkdir()
    sec.explorer_roots.setText("docs")

    class _FakeDialog:
        @staticmethod
        def getExistingDirectory(*_args, **_kwargs):
            return str(tmp_path / "docs")

    sec._file_dialog_factory = _FakeDialog
    sec._on_add_clicked()

    assert sec.explorer_roots.text() == "docs"
    assert sec._list.count() == 1


def test_remove_selected(qapp, tmp_path: Path) -> None:
    sec = _CExplorerSection(tmp_path)
    sec.explorer_roots.setText("docs;qa;knowledge")
    sec._list.item(1).setSelected(True)  # qa
    sec._on_remove_clicked()
    assert sec.explorer_roots.text() == "docs;knowledge"


def test_remove_multiple(qapp, tmp_path: Path) -> None:
    sec = _CExplorerSection(tmp_path)
    sec.explorer_roots.setText("a;b;c;d")
    sec._list.item(0).setSelected(True)
    sec._list.item(2).setSelected(True)
    sec._on_remove_clicked()
    assert sec.explorer_roots.text() == "b;d"


def test_remove_with_no_selection_is_noop(qapp, tmp_path: Path) -> None:
    sec = _CExplorerSection(tmp_path)
    sec.explorer_roots.setText("docs")
    sec._on_remove_clicked()
    assert sec.explorer_roots.text() == "docs"
