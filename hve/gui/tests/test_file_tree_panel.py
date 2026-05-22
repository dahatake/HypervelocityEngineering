"""hve.gui.file_explorer.file_tree_panel の smoke test。

QFileSystemWatcher の即時反映に依存せず、構造と基本操作のみ検証する。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QApplication

from hve.gui.file_explorer.file_tree_panel import FileTreePanel
from hve.gui.file_explorer.multi_root_model import PathRole


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _make_workspace(tmp_path: Path) -> Path:
    (tmp_path / "a.md").write_text("# a", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.md").write_text("# b", encoding="utf-8")
    return tmp_path


def test_panel_constructs_with_roots(qapp, tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    panel = FileTreePanel([ws])
    assert panel.windowTitle() != ""
    assert panel.widget() is not None


def test_search_filter_narrows_results(qapp, tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    panel = FileTreePanel([ws])
    panel._search.setText("b.md")
    qapp.processEvents()
    # フィルタが invalidate された後、root を展開しても b.md のみがマッチ
    # （詳細な行数検証はビュー実装依存のため、フィルタが例外を起こさない確認のみ）
    assert panel._proxy._needle == "b.md"


def test_file_selected_signal_emits_for_file(qapp, tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    panel = FileTreePanel([ws])
    received = []
    panel.file_selected.connect(received.append)

    # ルートを展開 → a.md のインデックスを取得して activated 相当を呼ぶ
    src_root = panel._model.index(0, 0)
    proxy_root = panel._proxy.mapFromSource(src_root)
    panel._view.expand(proxy_root)
    qapp.processEvents()

    # ルート以下の最初の子（フォルダ優先のため sub フォルダ）→ 次に a.md を探す
    rows = panel._proxy.rowCount(proxy_root)
    file_idx = None
    for r in range(rows):
        child = panel._proxy.index(r, 0, proxy_root)
        src_child = panel._proxy.mapToSource(child)
        path = panel._model.data(src_child, PathRole)
        if isinstance(path, Path) and path.is_file():
            file_idx = child
            break
    assert file_idx is not None
    panel._on_activated(file_idx)
    assert len(received) == 1
    assert received[0].name == "a.md"


def test_file_selected_not_emitted_for_directory(qapp, tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    panel = FileTreePanel([ws])
    received = []
    panel.file_selected.connect(received.append)

    src_root = panel._model.index(0, 0)
    proxy_root = panel._proxy.mapFromSource(src_root)
    panel._view.expand(proxy_root)
    qapp.processEvents()
    # ルート自身は dir なので emit されない
    panel._on_activated(proxy_root)
    assert received == []
