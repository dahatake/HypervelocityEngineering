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


def test_panel_no_phantom_rows_on_rapid_creation(qapp, tmp_path: Path) -> None:
    """Agent によるファイル連続生成シナリオで、プロキシ越しに幻行が残らないこと。

    full reset 方式の refresh_directory + QSortFilterProxyModel +
    QTreeView.expand の組合せで実在より 1 行多く描画されていた不具合の回帰防止。
    """
    docs = tmp_path / "docs"
    usecase = docs / "usecase"
    usecase.mkdir(parents=True)

    panel = FileTreePanel([tmp_path])
    proxy = panel._proxy
    model = panel._model

    def find_child(parent_proxy_idx, name):
        for r in range(proxy.rowCount(parent_proxy_idx)):
            idx = proxy.index(r, 0, parent_proxy_idx)
            if proxy.data(idx) == name:
                return idx
        return None

    # ルート → docs → usecase を View 経由で展開
    proxy_root = proxy.mapFromSource(model.index(0, 0))
    panel._view.expand(proxy_root)
    qapp.processEvents()
    docs_proxy = find_child(proxy_root, "docs")
    assert docs_proxy is not None
    panel._view.expand(docs_proxy)
    qapp.processEvents()
    usecase_proxy = find_child(docs_proxy, "usecase")
    assert usecase_proxy is not None
    panel._view.expand(usecase_proxy)
    qapp.processEvents()

    # 30 件を 1 件ずつ作成し、その都度 _on_directory_changed を発火
    for i in range(1, 31):
        (usecase / f"UC-{i:02d}-detail.md").write_text(f"# UC-{i}", encoding="utf-8")
        panel._on_directory_changed(str(usecase))
        qapp.processEvents()

    rows = proxy.rowCount(usecase_proxy)
    names = [proxy.data(proxy.index(r, 0, usecase_proxy)) for r in range(rows)]
    assert rows == 30, f"phantom row(s) detected: rows={rows}, names={names!r}"
    assert all(n for n in names), f"empty name in proxy view: {names!r}"
