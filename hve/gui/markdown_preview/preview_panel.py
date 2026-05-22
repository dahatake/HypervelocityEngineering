"""hve.gui.markdown_preview.preview_panel — Markdown プレビュー QDockWidget。

責務:
    - ヘッダに現在表示中ファイルパス + コピー/外部で開くボタン。
    - 本体は ``QWebEngineView``。Markdown は ``MarkdownHtmlRenderer``、
      非 Markdown は ``CodeHighlighter`` で HTML 化して表示。
    - ``PreviewWatcher`` で表示中ファイルの変更を検知し再読込
      （スクロール位置は JavaScript で保存/復元）。
    - http(s) リンクは ``QDesktopServices`` で外部ブラウザに渡す。
"""

from __future__ import annotations

import html as _html
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QShowEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .code_highlighter import CodeHighlighter, get_style_css
from .markdown_html_renderer import MarkdownHtmlRenderer
from .markdown_loader import LoaderKind, MarkdownLoader
from .preview_watcher import PreviewWatcher


_ASSETS_DIR = Path(__file__).parent / "assets"


class _ExternalLinkPage:
    """Placeholder — 実体は QWebEngineView 初期化時に差し替える。"""
    pass


class MarkdownPreviewPanel(QDockWidget):
    """Markdown / コードファイルをプレビューする Dock。"""

    # 内部テスト用シグナル（ファイルを load した時に emit）
    file_loaded = Signal(Path)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("MarkdownPreviewPanel")
        self.setWindowTitle(self.tr("プレビュー"))

        self._loader = MarkdownLoader()
        self._md_renderer = MarkdownHtmlRenderer()
        self._highlighter = CodeHighlighter()
        self._watcher = PreviewWatcher(self)
        self._current_path: Optional[Path] = None

        # QWebEngineView は lazy 初期化（初回 showEvent または load_file 時）。
        # テスト・起動時間を押さえるため。
        self._view = None  # type: Optional["QWebEngineView"]
        self._pending_path: Optional[Path] = None

        # --- UI （QWebEngineView 以外） ---
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        header = QWidget(container)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        self._path_label = QLabel(self.tr("（ファイル未選択）"), header)
        self._path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._path_label.setStyleSheet("color: #555; font-size: 9pt;")
        header_layout.addWidget(self._path_label, 1)

        self._btn_copy = QToolButton(header)
        self._btn_copy.setText(self.tr("コピー"))
        self._btn_copy.setToolTip(self.tr("現在のファイルパスをクリップボードへコピー"))
        self._btn_copy.clicked.connect(self._copy_current_path)
        header_layout.addWidget(self._btn_copy)

        layout.addWidget(header)

        # View の位置は QStackedWidget で予約し、QWebEngineView 生成時に addWidget する。
        self._view_stack = QStackedWidget(container)
        self._placeholder = QLabel(
            self.tr("（初回表示時にプレビューを初期化します）"),
            self._view_stack,
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #888;")
        self._view_stack.addWidget(self._placeholder)
        layout.addWidget(self._view_stack, 1)

        self.setWidget(container)
        # MainWindow の minimumSizeHint を押し広げないよう Dock と内部 View を押さえる。
        self._view_stack.setMinimumWidth(180)
        self.setMinimumWidth(200)

        self._watcher.reload_requested.connect(self._on_file_changed)

    # ------------------------------------------------------------------
    # QWebEngineView の lazy 初期化
    # ------------------------------------------------------------------

    def _ensure_view(self) -> None:
        if self._view is not None:
            return
        # 重い import もここで実行し、テスト起動時間を短縮する。
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView

        class _LinkPage(QWebEnginePage):
            def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # type: ignore[override]
                scheme = url.scheme().lower()
                if scheme in ("http", "https") and is_main_frame:
                    QDesktopServices.openUrl(url)
                    return False
                return super().acceptNavigationRequest(url, nav_type, is_main_frame)

        view = QWebEngineView(self)
        page = _LinkPage(view)
        view.setPage(page)
        settings = view.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
        self._view = view
        self._view_stack.addWidget(view)
        self._view_stack.setCurrentWidget(view)
        # 初期表示
        self._set_inner_html(
            "<p style='color:#888;'>（左のツリーからファイルを選択するとプレビューを表示します）</p>"
        )
        # pending されていたファイルがあれば load
        if self._pending_path is not None:
            p, self._pending_path = self._pending_path, None
            self.load_file(p)

    def showEvent(self, event: QShowEvent) -> None:  # type: ignore[override]
        self._ensure_view()
        super().showEvent(event)

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def load_file(self, path: Path) -> None:
        p = Path(path)
        self._current_path = p
        self._path_label.setText(str(p))
        self._watcher.watch(p)
        if self._view is None:
            # View 未初期化なら表示時にレンダリングするため保留
            self._pending_path = p
        else:
            self._render_current()
        self.file_loaded.emit(p)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _on_file_changed(self, _path: str) -> None:
        if self._view is None:
            return
        # スクロール位置を JS で取得 → 再レンダ後復元
        def _after(scroll_y):
            try:
                y = int(scroll_y) if scroll_y is not None else 0
            except (TypeError, ValueError):
                y = 0
            self._render_current(restore_scroll=y)

        self._view.page().runJavaScript("window.scrollY", _after)

    def _render_current(self, *, restore_scroll: int = 0) -> None:
        if self._view is None:
            return
        p = self._current_path
        if p is None:
            return
        result = self._loader.load(p)

        if result.kind == LoaderKind.MARKDOWN and result.raw_text is not None:
            html = self._md_renderer.render_full(result.raw_text)
        elif result.kind == LoaderKind.CODE and result.raw_text is not None:
            inner = self._highlighter.highlight_file(p, result.raw_text)
            html = self._md_renderer.wrap_html_in_template(inner)
        elif result.kind == LoaderKind.PLAIN and result.raw_text is not None:
            escaped = _html.escape(result.raw_text)
            inner = f"<pre>{escaped}</pre>"
            html = self._md_renderer.wrap_html_in_template(inner)
        else:
            # MISSING / OVERSIZE / BINARY / ERROR
            msg = _html.escape(result.error or f"表示できません ({result.kind.value})")
            inner = f"<p style='color:#a33;'>⚠ {msg}</p>"
            html = self._md_renderer.wrap_html_in_template(inner)

        base_url = QUrl.fromLocalFile(str(_ASSETS_DIR) + "/")
        self._view.setHtml(html, base_url)

        if restore_scroll > 0:
            # ページロード完了後に scrollTo（loadFinished を待たず簡易に setTimeout で復元）
            self._view.page().runJavaScript(
                f"setTimeout(function(){{ window.scrollTo(0, {restore_scroll}); }}, 50);"
            )

    def _set_inner_html(self, inner: str) -> None:
        if self._view is None:
            return
        html = self._md_renderer.wrap_html_in_template(inner)
        base_url = QUrl.fromLocalFile(str(_ASSETS_DIR) + "/")
        self._view.setHtml(html, base_url)

    def _copy_current_path(self) -> None:
        if self._current_path is None:
            return
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(str(self._current_path))
