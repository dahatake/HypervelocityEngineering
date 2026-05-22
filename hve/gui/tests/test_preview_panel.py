"""hve.gui.markdown_preview.preview_panel の smoke test。

QWebEngineView の Chromium 初期化は環境依存（特に CI の offscreen）で
時間がかかるため、本テストは「インスタンス化」「load_file での例外無し」
「file_loaded シグナル発火」のみに絞る。

P0-3 スパイクで offscreen 動作確認済 (PySide6 6.11.1 / 3.76s 初回起動)。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

# QtWebEngine が使えない環境では skip
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    from hve.gui.markdown_preview.preview_panel import MarkdownPreviewPanel

    _HAS_WEBENGINE = True
except Exception:  # pragma: no cover
    _HAS_WEBENGINE = False


pytestmark = pytest.mark.skipif(
    not _HAS_WEBENGINE, reason="QtWebEngine 利用不可"
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_panel_constructs(qapp) -> None:
    panel = MarkdownPreviewPanel()
    assert panel.windowTitle() != ""
    assert panel.widget() is not None


def test_load_markdown_emits_file_loaded(qapp, tmp_path: Path) -> None:
    p = tmp_path / "doc.md"
    p.write_text("# Hello", encoding="utf-8")
    panel = MarkdownPreviewPanel()

    received = []
    panel.file_loaded.connect(received.append)

    panel.load_file(p)
    qapp.processEvents()
    assert received == [p]
    assert panel._current_path == p
    assert str(p) in panel._path_label.text()


def test_load_missing_file_does_not_raise(qapp, tmp_path: Path) -> None:
    panel = MarkdownPreviewPanel()
    panel.load_file(tmp_path / "nonexistent.md")
    qapp.processEvents()


def test_load_binary_file_does_not_raise(qapp, tmp_path: Path) -> None:
    p = tmp_path / "x.bin"
    p.write_bytes(b"\x00\x01")
    panel = MarkdownPreviewPanel()
    panel.load_file(p)
    qapp.processEvents()
