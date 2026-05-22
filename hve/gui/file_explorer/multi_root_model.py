"""hve.gui.file_explorer.multi_root_model — 複数ルートを束ねるツリーモデル。

設計（敵対的レビュー #2 反映）:
    ``QAbstractProxyModel`` は単一ソースモデル前提のため複数ルート集約には使えない。
    代わりに ``QAbstractItemModel`` を直接派生し、内部 ``_Node`` ツリーで複数ルートを
    保持する。子ノードは初回 ``hasChildren`` / ``rowCount`` 呼び出し時に ``os.scandir``
    で遅延ロードする。

外部からのファイル変更検知は本モデルの責務外（``FileTreePanel`` が
``QFileSystemWatcher`` を構成して ``refresh_directory(path)`` を呼ぶ）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    Qt,
)


# Qt.UserRole 拡張: 各インデックスの Path を返す。
PathRole = Qt.ItemDataRole.UserRole + 1


class _Node:
    """ツリー内ノード。"""

    __slots__ = ("path", "display_name", "parent", "_children", "_loaded", "is_dir")

    def __init__(
        self,
        path: Path,
        display_name: str,
        parent: Optional["_Node"],
        is_dir: bool,
    ) -> None:
        self.path = path
        self.display_name = display_name
        self.parent = parent
        self._children: List[_Node] = []
        self._loaded = False
        self.is_dir = is_dir

    def child_at(self, row: int) -> Optional["_Node"]:
        if 0 <= row < len(self._children):
            return self._children[row]
        return None

    def child_count(self) -> int:
        return len(self._children)

    def row_in_parent(self) -> int:
        if self.parent is None:
            return 0
        try:
            return self.parent._children.index(self)
        except ValueError:
            return 0


class MultiRootFileModel(QAbstractItemModel):
    """複数ワークスペースルートを 1 つのツリーとして公開するモデル。

    列は 1 列のみ（ファイル名）。ルート行に各ワークスペースが並ぶ。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # ルート行用の仮想ノード（インデックスを持たない隠しノード）。
        # 子要素は add_root() でのみ追加され、os.scandir は決して呼ばない。
        self._root = _Node(Path("/"), "", None, is_dir=True)
        self._root._loaded = True  # _ensure_loaded で os.scandir を走らせない
        # 重複検出用
        self._known_root_paths: Dict[Path, _Node] = {}

    # ------------------------------------------------------------------
    # ルート管理
    # ------------------------------------------------------------------

    def add_root(self, path: Path, display_name: Optional[str] = None) -> None:
        """ルート（ワークスペース）を追加する。存在しないパスは無視。"""
        p = Path(path).resolve()
        if not p.exists() or not p.is_dir():
            return
        if p in self._known_root_paths:
            return
        name = display_name or p.name or str(p)
        row = len(self._root._children)
        self.beginInsertRows(QModelIndex(), row, row)
        node = _Node(p, name, self._root, is_dir=True)
        self._root._children.append(node)
        self._known_root_paths[p] = node
        self.endInsertRows()

    def root_paths(self) -> List[Path]:
        return [n.path for n in self._root._children]

    def clear_roots(self) -> None:
        """全ルートを削除する（モデルをリセット）。

        ``_root`` は仮想ルートで実ディレクトリを持たないため ``_loaded=True`` を維持し、
        ``_ensure_loaded`` 時の ``os.scandir`` 実行を防ぐ。
        """
        self.beginResetModel()
        self._root._children = []
        self._known_root_paths = {}
        self.endResetModel()

    # ------------------------------------------------------------------
    # 子ノード遅延ロード
    # ------------------------------------------------------------------

    def _ensure_loaded(self, node: _Node) -> None:
        if node._loaded:
            return
        node._loaded = True
        if not node.is_dir:
            return
        try:
            entries = list(os.scandir(node.path))
        except OSError:
            return

        # フォルダ優先 + 名前順（敵対的レビュー #29）
        entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))

        for e in entries:
            # 隠しファイル既定非表示（敵対的レビュー #30）
            if e.name.startswith("."):
                continue
            try:
                child_is_dir = e.is_dir()
            except OSError:
                continue
            child_node = _Node(
                Path(e.path),
                e.name,
                node,
                is_dir=child_is_dir,
            )
            node._children.append(child_node)

    def refresh_directory(self, dir_path: Path) -> None:
        """指定ディレクトリの子一覧を再走査する（外部変更検知時に呼ぶ）。

        該当ディレクトリが本モデル配下にない場合は何もしない。
        """
        node = self._find_node_for_path(Path(dir_path).resolve())
        if node is None or not node.is_dir:
            return
        idx = self._index_for_node(node)
        # 既存子を全削除 → 再ロード
        if node._children:
            self.beginRemoveRows(idx, 0, len(node._children) - 1)
            node._children.clear()
            self.endRemoveRows()
        node._loaded = False
        # 子件数が判明する前に hasChildren を Qt に再評価させるため、
        # 既存 _children を再ロードしてから insertRows を発行する。
        self._ensure_loaded(node)
        if node._children:
            self.beginInsertRows(idx, 0, len(node._children) - 1)
            self.endInsertRows()

    def _find_node_for_path(self, target: Path) -> Optional[_Node]:
        """ロード済みノードからパスを検索する。未ロード領域は探索しない。"""
        for root_node in self._root._children:
            try:
                target.relative_to(root_node.path)
            except ValueError:
                continue
            return self._descend(root_node, target)
        return None

    def _descend(self, node: _Node, target: Path) -> Optional[_Node]:
        if node.path == target:
            return node
        if not node._loaded:
            return None
        for child in node._children:
            try:
                target.relative_to(child.path)
            except ValueError:
                continue
            return self._descend(child, target)
        return None

    def _index_for_node(self, node: _Node) -> QModelIndex:
        if node is self._root:
            return QModelIndex()
        return self.createIndex(node.row_in_parent(), 0, node)

    # ------------------------------------------------------------------
    # QAbstractItemModel 実装
    # ------------------------------------------------------------------

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 1

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        parent_node = self._node_from_index(parent)
        if parent_node.is_dir:
            self._ensure_loaded(parent_node)
        return parent_node.child_count()

    def hasChildren(self, parent: QModelIndex = QModelIndex()) -> bool:
        parent_node = self._node_from_index(parent)
        if not parent_node.is_dir:
            return False
        if parent_node._loaded:
            return parent_node.child_count() > 0
        # 未ロードならディレクトリには子があるとみなす（VS Code 風遅延展開）
        return True

    def index(
        self,
        row: int,
        column: int,
        parent: QModelIndex = QModelIndex(),
    ) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        parent_node = self._node_from_index(parent)
        child = parent_node.child_at(row)
        if child is None:
            return QModelIndex()
        return self.createIndex(row, column, child)

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()
        node: _Node = index.internalPointer()
        if node.parent is None or node.parent is self._root:
            return QModelIndex()
        return self.createIndex(node.parent.row_in_parent(), 0, node.parent)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node: _Node = index.internalPointer()
        if role == Qt.ItemDataRole.DisplayRole:
            return node.display_name
        if role == PathRole:
            return node.path
        return None

    def headerData(self, section: int, orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and section == 0
        ):
            return "Name"
        return None

    # ------------------------------------------------------------------
    # ヘルパ
    # ------------------------------------------------------------------

    def _node_from_index(self, index: QModelIndex) -> _Node:
        if not index.isValid():
            return self._root
        return index.internalPointer()
