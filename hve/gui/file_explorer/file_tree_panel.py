"""hve.gui.file_explorer.file_tree_panel — ファイルツリーを表示する QDockWidget。

責務:
    - 複数ワークスペースルートを ``MultiRootFileModel`` で表示する。
    - 検索ボックスでファイル名フィルタ。
    - 各ルートディレクトリを ``QFileSystemWatcher`` で監視し、変更を
      ``FileChangeTracker`` に通知して行末バッジを描画する。
    - 1 秒 QTimer で ``tick()`` し、5 秒経過したバッジを消す。
    - ファイル選択時に ``file_selected(Path)`` を emit する。
    - 右クリックメニュー: パスコピー / エクスプローラで開く。

注意:
    Windows の ``QFileSystemWatcher`` は取りこぼしがある（既存
    ``qa_ipc_manager`` のコメント参照）。本パネルは Q2=A 採択
    （ポーリング無し）で実装する。E1 統合テストで取りこぼし率
    5% 超なら別途ポーリング追加判断。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set
import time

from PySide6.QtCore import QFileSystemWatcher, QModelIndex, QSortFilterProxyModel, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QDockWidget,
    QLineEdit,
    QMenu,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from .file_change_tracker import FileChangeTracker
from .file_tree_delegate import FileTreeDelegate
from .multi_root_model import MultiRootFileModel, PathRole


_TICK_INTERVAL_MS = 1000
_DEFAULT_FADE_SECONDS = 5.0


def _resolve_display_name(
    path: Path,
    display_names: Optional[Dict[Path, str]],
) -> str:
    """ルートパスに対する表示名を解決する。

    ``display_names`` に正規化済みパス（``Path.resolve()`` 済み）をキーとした
    エントリがあれば優先する。なければ ``path.name`` にフォールバックする。
    ``path.name`` が空（ドライブルート等）の場合は ``str(path)`` を返す。
    """
    if display_names:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        name = display_names.get(resolved)
        if name:
            return name
    return path.name or str(path)


class _NameFilterProxy(QSortFilterProxyModel):
    """ファイル名部分一致フィルタ（再帰的に親も表示）。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._needle = ""
        # ソート/フィルタ自体は子モデルに任せる
        self.setRecursiveFilteringEnabled(True)

    def set_needle(self, needle: str) -> None:
        self._needle = (needle or "").lower()
        self.invalidate()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._needle:
            return True
        idx = self.sourceModel().index(source_row, 0, source_parent)
        if not idx.isValid():
            return False
        name = self.sourceModel().data(idx, Qt.ItemDataRole.DisplayRole) or ""
        return self._needle in str(name).lower()


class FileTreePanel(QDockWidget):
    """ファイルツリーパネル。

    Signals:
        file_selected(Path): ユーザーがファイルを選択した時に emit。
    """

    file_selected = Signal(Path)

    def __init__(
        self,
        roots: List[Path],
        parent: Optional[QWidget] = None,
        *,
        display_names: Optional[Dict[Path, str]] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("FileTreePanel")
        self.setWindowTitle(self.tr("エクスプローラー"))

        self._tracker = FileChangeTracker(fade_seconds=_DEFAULT_FADE_SECONDS)
        self._model = MultiRootFileModel(self)
        for r in roots:
            self._model.add_root(r, _resolve_display_name(r, display_names))

        # 知識: 各ルートとその直下サブディレクトリを QFileSystemWatcher に登録。
        # より深い階層は、directoryChanged イベントで新規ディレクトリが
        # 検出されたときに動的に追加し、QFileSystemWatcher 起動コスト（
        # Windows ではディレクトリ毎にカーネルハンドルを取るため
        # 大量登録で起動が遅くなる）を抑える。
        self._watcher = QFileSystemWatcher(self)
        self._watched_dirs: Set[str] = set()
        # dir -> {filename: mtime}
        self._known_files: Dict[str, Dict[str, float]] = {}
        for r in self._model.root_paths():
            self._add_watch_recursive(r, depth_limit=1)

        self._watcher.directoryChanged.connect(self._on_directory_changed)

        # 1Hz tick でバッジ fade
        self._tick = QTimer(self)
        self._tick.setInterval(_TICK_INTERVAL_MS)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()

        # --- UI ---
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._search = QLineEdit(container)
        self._search.setPlaceholderText(self.tr("ファイル名で検索..."))
        self._search.setClearButtonEnabled(True)
        layout.addWidget(self._search)

        self._proxy = _NameFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self._view = QTreeView(container)
        self._view.setModel(self._proxy)
        self._view.setHeaderHidden(True)
        self._view.setUniformRowHeights(True)
        self._view.setItemDelegate(FileTreeDelegate(self._tracker, self._view))
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._on_context_menu)
        self._view.activated.connect(self._on_activated)
        self._view.clicked.connect(self._on_activated)
        layout.addWidget(self._view, 1)

        self.setWidget(container)
        # ウィンドウ全体の最小幅を押し広げないように、Dock 自身の最小幅を低めに設定。
        self.setMinimumWidth(180)

        self._search.textChanged.connect(self._proxy.set_needle)

    # ------------------------------------------------------------------
    # ルート再設定（設定変更時に呼ばれる）
    # ------------------------------------------------------------------

    def set_roots(
        self,
        roots: List[Path],
        *,
        display_names: Optional[Dict[Path, str]] = None,
    ) -> None:
        """監視ルートを丸ごと差し替える。

        モデルと QFileSystemWatcher の登録状態をクリアした後、与えられた roots を
        新規に登録する。重複は MultiRootFileModel.add_root で自動的に無視される。
        """
        # 既存 watcher エントリをすべて剥がす
        if self._watched_dirs:
            try:
                self._watcher.removePaths(list(self._watched_dirs))
            except Exception:
                pass
        self._watched_dirs = set()
        self._known_files = {}

        # モデルをリセットして新規ルートを登録
        self._model.clear_roots()
        for r in roots:
            self._model.add_root(r, _resolve_display_name(r, display_names))

        # 新しいルートを watcher に登録（既存と同じ depth_limit=1）
        for r in self._model.root_paths():
            self._add_watch_recursive(r, depth_limit=1)

        # ビューを再描画
        if self._view.viewport() is not None:
            self._view.viewport().update()

    # ------------------------------------------------------------------
    # ファイル監視
    # ------------------------------------------------------------------

    def _add_watch_recursive(self, dir_path: Path, depth_limit: int) -> None:
        """指定ディレクトリ以下を ``depth_limit`` 段まで watcher に登録する。

        QFileSystemWatcher は再帰監視を持たないため、初期段階で 2 段下まで
        登録しておく。それ以上深い変更は親ディレクトリの directoryChanged
        が発火した時点で展開する。
        """
        if depth_limit < 0:
            return
        s = str(dir_path)
        if s not in self._watched_dirs:
            try:
                self._watcher.addPath(s)
                self._watched_dirs.add(s)
                self._known_files[s] = self._snapshot_children(dir_path)
            except Exception:
                return
        if depth_limit == 0:
            return
        try:
            for entry in os.scandir(dir_path):
                if entry.name.startswith("."):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    self._add_watch_recursive(Path(entry.path), depth_limit - 1)
        except OSError:
            pass

    @staticmethod
    def _snapshot_children(dir_path: Path) -> Dict[str, float]:
        """ディレクトリ内容を {filename: mtime} スナップショットとして取得。ディレクトリは mtime=0。”"""
        result: Dict[str, float] = {}
        try:
            for e in os.scandir(dir_path):
                if e.name.startswith("."):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        result[e.name] = 0.0
                    else:
                        result[e.name] = e.stat().st_mtime
                except OSError:
                    continue
        except OSError:
            pass
        return result

    def _on_directory_changed(self, dir_str: str) -> None:
        dir_path = Path(dir_str)
        now = time.monotonic()
        new_snapshot = self._snapshot_children(dir_path)
        old_snapshot = self._known_files.get(dir_str, {})

        added = set(new_snapshot.keys()) - set(old_snapshot.keys())
        removed = set(old_snapshot.keys()) - set(new_snapshot.keys())
        common = set(new_snapshot.keys()) & set(old_snapshot.keys())
        self._known_files[dir_str] = new_snapshot

        for name in added:
            p = dir_path / name
            self._tracker.mark_created(p, now=now)
            if p.is_dir():
                # 新規ディレクトリも再帰的に追加監視
                self._add_watch_recursive(p, depth_limit=3)

        for name in removed:
            self._tracker.mark_deleted(dir_path / name)

        # 既存ファイルの mtime 差分で更新検知（誤検知防止のため #2 対応）
        for name in common:
            old_mt = old_snapshot.get(name, 0.0)
            new_mt = new_snapshot.get(name, 0.0)
            if new_mt > 0.0 and new_mt != old_mt:
                self._tracker.mark_modified(dir_path / name, now=now)

        # モデルを再走査して新規/削除を反映
        self._model.refresh_directory(dir_path)

        # 描画更新: ビューポートを invalidate
        self._view.viewport().update()

    def _on_tick(self) -> None:
        now = time.monotonic()
        faded = list(self._tracker.tick(now=now))
        if faded:
            self._view.viewport().update()

    # ------------------------------------------------------------------
    # ユーザー操作
    # ------------------------------------------------------------------

    def _on_activated(self, proxy_index: QModelIndex) -> None:
        if not proxy_index.isValid():
            return
        src_index = self._proxy.mapToSource(proxy_index)
        path = self._model.data(src_index, PathRole)
        if isinstance(path, Path) and path.is_file():
            self.file_selected.emit(path)

    def _on_context_menu(self, pos) -> None:
        idx = self._view.indexAt(pos)
        if not idx.isValid():
            return
        src_index = self._proxy.mapToSource(idx)
        path = self._model.data(src_index, PathRole)
        if not isinstance(path, Path):
            return

        menu = QMenu(self._view)
        copy_action = QAction(self.tr("パスをコピー"), menu)
        open_action = QAction(self.tr("エクスプローラで開く"), menu)
        copy_action.triggered.connect(lambda: self._copy_path(path))
        open_action.triggered.connect(lambda: self._reveal_in_filer(path))
        menu.addAction(copy_action)
        menu.addAction(open_action)
        menu.exec(self._view.viewport().mapToGlobal(pos))

    @staticmethod
    def _copy_path(path: Path) -> None:
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(str(path))

    @staticmethod
    def _reveal_in_filer(path: Path) -> None:
        if sys.platform == "win32":
            try:
                if path.is_dir():
                    subprocess.Popen(["explorer", str(path)])
                else:
                    subprocess.Popen(["explorer", "/select,", str(path)])
            except OSError:
                pass
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            target = path if path.is_dir() else path.parent
            subprocess.Popen(["xdg-open", str(target)])
