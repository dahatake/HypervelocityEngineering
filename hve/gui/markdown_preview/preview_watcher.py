"""hve.gui.markdown_preview.preview_watcher — プレビュー中ファイルの変更検出。

責務:
    - 表示中の 1 ファイルのみを ``QFileSystemWatcher`` で監視する。
    - ファイル更新を検出すると ``reload_requested(path)`` シグナルを emit する。
    - 別ファイルへ切替時は古いパスの監視を解除する。

注意:
    Windows / WSL では ``QFileSystemWatcher`` の検知が遅延 / 取りこぼしする
    ケースがあるため、本ウォッチャはあくまで「表示中ファイル 1 件」専用。
    ツリー全体の監視は別系統（FileTreePanel）で実施する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QFileSystemWatcher, QObject, Signal


class PreviewWatcher(QObject):
    """単一ファイル監視ラッパ。

    Signals:
        reload_requested(str): 監視中ファイルが変更された / 削除された時に
            該当パス（文字列）を emit する。
    """

    reload_requested = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._current: Optional[Path] = None

    def watch(self, path: Path) -> None:
        """監視対象を切り替える。既存監視は解除される。"""
        self.clear()
        p = Path(path)
        self._current = p
        if p.exists() and p.is_file():
            self._watcher.addPath(str(p))

    def clear(self) -> None:
        """監視を停止する。"""
        if self._current is not None:
            try:
                self._watcher.removePath(str(self._current))
            except Exception:
                pass
        self._current = None

    def current(self) -> Optional[Path]:
        return self._current

    def _on_file_changed(self, path: str) -> None:
        # Windows のエディタは「削除→再作成」で保存することがあるため、
        # 一度ファイル監視リストから外れた場合は再登録を試みる。
        p = Path(path)
        if p.exists() and p.is_file() and str(p) not in self._watcher.files():
            self._watcher.addPath(str(p))
        self.reload_requested.emit(path)
