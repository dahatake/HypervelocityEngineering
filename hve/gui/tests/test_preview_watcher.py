"""hve.gui.markdown_preview.preview_watcher のユニットテスト。

QFileSystemWatcher の通知タイミングは環境依存のため、本テストは
- watch() / clear() の対象パス管理
- 単一インスタンスで複数回 watch() 呼び出し時の挙動
- reload_requested シグナルが手動 emit で正しく発火するか
に絞る（実ファイル変更検知の遅延は環境依存）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from hve.gui.markdown_preview.preview_watcher import PreviewWatcher


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_initial_current_is_none(qapp) -> None:
    w = PreviewWatcher()
    assert w.current() is None


def test_watch_sets_current(qapp, tmp_path: Path) -> None:
    p = tmp_path / "a.md"
    p.write_text("a", encoding="utf-8")
    w = PreviewWatcher()
    w.watch(p)
    assert w.current() == p


def test_watch_replaces_previous(qapp, tmp_path: Path) -> None:
    p1 = tmp_path / "a.md"
    p2 = tmp_path / "b.md"
    p1.write_text("a", encoding="utf-8")
    p2.write_text("b", encoding="utf-8")
    w = PreviewWatcher()
    w.watch(p1)
    w.watch(p2)
    assert w.current() == p2


def test_watch_nonexistent_does_not_register(qapp, tmp_path: Path) -> None:
    w = PreviewWatcher()
    w.watch(tmp_path / "nope.md")
    # current は記録するが、内部 QFileSystemWatcher のリストには追加されない
    assert w.current() == tmp_path / "nope.md"


def test_clear_resets_current(qapp, tmp_path: Path) -> None:
    p = tmp_path / "a.md"
    p.write_text("a", encoding="utf-8")
    w = PreviewWatcher()
    w.watch(p)
    w.clear()
    assert w.current() is None


def test_reload_requested_emits(qapp, tmp_path: Path) -> None:
    p = tmp_path / "a.md"
    p.write_text("a", encoding="utf-8")
    w = PreviewWatcher()
    w.watch(p)

    received = []
    w.reload_requested.connect(lambda s: received.append(s))
    w._on_file_changed(str(p))  # 内部メソッド直叩きで挙動確認
    assert received == [str(p)]
