"""hve.gui.file_explorer.multi_root_model のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QApplication

from hve.gui.file_explorer.multi_root_model import MultiRootFileModel, PathRole


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def model(qapp) -> MultiRootFileModel:
    return MultiRootFileModel()


def test_empty_model_has_no_roots(model: MultiRootFileModel) -> None:
    assert model.rowCount() == 0
    assert model.root_paths() == []


def test_add_root_adds_top_level_row(model: MultiRootFileModel, tmp_path: Path) -> None:
    model.add_root(tmp_path, "ws")
    assert model.rowCount() == 1
    idx = model.index(0, 0)
    assert model.data(idx) == "ws"
    assert model.data(idx, PathRole) == tmp_path.resolve()


def test_add_root_skips_nonexistent_paths(model: MultiRootFileModel, tmp_path: Path) -> None:
    model.add_root(tmp_path / "nope")
    assert model.rowCount() == 0


def test_add_root_skips_duplicates(model: MultiRootFileModel, tmp_path: Path) -> None:
    model.add_root(tmp_path)
    model.add_root(tmp_path)
    assert model.rowCount() == 1


def test_children_are_lazy_loaded(model: MultiRootFileModel, tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.md").write_text("c", encoding="utf-8")
    model.add_root(tmp_path)

    root_idx = model.index(0, 0)
    assert model.hasChildren(root_idx) is True
    assert model.rowCount(root_idx) == 3  # sub (folder), a.md, b.md


def test_folders_come_before_files(model: MultiRootFileModel, tmp_path: Path) -> None:
    (tmp_path / "z.md").write_text("z", encoding="utf-8")
    (tmp_path / "a_folder").mkdir()
    model.add_root(tmp_path)
    root_idx = model.index(0, 0)
    assert model.rowCount(root_idx) == 2
    first = model.data(model.index(0, 0, root_idx))
    second = model.data(model.index(1, 0, root_idx))
    assert first == "a_folder"
    assert second == "z.md"


def test_hidden_files_are_excluded(model: MultiRootFileModel, tmp_path: Path) -> None:
    (tmp_path / ".secret").write_text("s", encoding="utf-8")
    (tmp_path / "visible.md").write_text("v", encoding="utf-8")
    model.add_root(tmp_path)
    root_idx = model.index(0, 0)
    assert model.rowCount(root_idx) == 1
    assert model.data(model.index(0, 0, root_idx)) == "visible.md"


def test_parent_index_round_trip(model: MultiRootFileModel, tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.md").write_text("c", encoding="utf-8")
    model.add_root(tmp_path)
    root_idx = model.index(0, 0)
    sub_idx = model.index(0, 0, root_idx)
    assert model.data(sub_idx) == "sub"
    file_idx = model.index(0, 0, sub_idx)
    assert model.data(file_idx) == "c.md"
    # parent() round-trip
    assert model.parent(file_idx).internalPointer() is sub_idx.internalPointer()
    assert model.parent(sub_idx).internalPointer() is root_idx.internalPointer()
    assert model.parent(root_idx) == QModelIndex()


def test_refresh_directory_picks_up_new_files(model: MultiRootFileModel, tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    model.add_root(tmp_path)
    root_idx = model.index(0, 0)
    assert model.rowCount(root_idx) == 1

    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    model.refresh_directory(tmp_path)
    assert model.rowCount(root_idx) == 2


def test_refresh_directory_outside_model_is_noop(model: MultiRootFileModel, tmp_path: Path) -> None:
    model.refresh_directory(tmp_path / "elsewhere")  # 例外を出さない


def test_refresh_directory_incremental_no_phantom_rows(
    model: MultiRootFileModel, tmp_path: Path
) -> None:
    """ファイル追加 1 件ごとに refresh_directory を呼んでも幻行が生じないこと。

    full reset 方式（beginRemoveRows(0,N-1) + beginInsertRows(0,M-1)）に戻ると
    QSortFilterProxyModel 越しに行ズレが発生する既知問題の回帰防止。
    ここではソースモデル単独で rowCount と display_name の整合のみ検証する。
    """
    model.add_root(tmp_path)
    root_idx = model.index(0, 0)
    # 30 件を 1 件ずつ追加し、その都度 refresh
    for i in range(1, 31):
        (tmp_path / f"UC-{i:02d}-detail.md").write_text(f"# UC-{i}", encoding="utf-8")
        model.refresh_directory(tmp_path)
    assert model.rowCount(root_idx) == 30
    names = [model.data(model.index(r, 0, root_idx)) for r in range(30)]
    assert all(n for n in names), f"empty name detected: {names!r}"
    # 想定どおりソート順（名前順）で並んでいること
    assert names == sorted(names)


def test_refresh_directory_removes_missing_entries(
    model: MultiRootFileModel, tmp_path: Path
) -> None:
    """refresh_directory が削除されたファイルを行から除去すること（削除分岐の回帰防止）。"""
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    model.add_root(tmp_path)
    root_idx = model.index(0, 0)
    assert model.rowCount(root_idx) == 2

    (tmp_path / "a.md").unlink()
    model.refresh_directory(tmp_path)
    assert model.rowCount(root_idx) == 1
    assert model.data(model.index(0, 0, root_idx)) == "b.md"


def test_multiple_roots(qapp, tmp_path: Path) -> None:
    m = MultiRootFileModel()
    r1 = tmp_path / "r1"
    r2 = tmp_path / "r2"
    r1.mkdir()
    r2.mkdir()
    (r1 / "x.md").write_text("x", encoding="utf-8")
    (r2 / "y.md").write_text("y", encoding="utf-8")
    m.add_root(r1, "R1")
    m.add_root(r2, "R2")
    assert m.rowCount() == 2
    assert m.data(m.index(0, 0)) == "R1"
    assert m.data(m.index(1, 0)) == "R2"
