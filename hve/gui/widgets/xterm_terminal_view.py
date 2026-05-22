"""hve.gui.widgets.xterm_terminal_view — xterm.js を埋め込んだ Qt ターミナルウィジェット。

設計:
    - ``QWebEngineView`` 内で同梱の ``xterm_assets/index.html`` を読み込み、
      ``QWebChannel`` 経由で双方向通信する。
    - Python 側 (``_PyBridge``) は ``QObject`` で以下を提供:
        Slots:
          - ``user_input_b64(b64)``  : 端末からの入力を受信し ``user_input`` シグナル発火。
          - ``resized(cols, rows)``  : 端末サイズ変更を受信し ``resized`` シグナル発火。
          - ``notify_ready()``       : 初期化完了通知。``ready`` シグナル発火。
        Signals (JS 側から ``.connect`` される):
          - ``output_b64(str)``      : PTY 出力 (base64) を画面へ書き込む指示。
          - ``terminal_cleared()``   : 画面クリア指示。

    - バイナリ運搬は base64 文字列。QWebChannel は JSON-serializable のみ運ぶため。

セキュリティ:
    - ``setUrl(QUrl.fromLocalFile(...))`` でローカル限定読み込み。
    - ``LocalContentCanAccessRemoteUrls = False`` を明示設定。
    - ``acceptNavigationRequest`` を override し ``file://`` 以外の遷移を拒否。
    - CSP は同梱 ``index.html`` の ``<meta http-equiv>`` でも宣言。

依存:
    - PySide6 (QtWebEngineWidgets, QtWebEngineCore, QtWebChannel)。
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineSettings,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget

__all__ = ["XtermTerminalView"]


_ASSETS_DIR = Path(__file__).resolve().parent / "xterm_assets"
_INDEX_HTML = _ASSETS_DIR / "index.html"


class _PyBridge(QObject):
    """QWebChannel に登録される Python 側ブリッジ。

    Signal は Python → JS (JS から ``.connect`` する)。
    Slot は JS → Python (JS から関数として呼び出される)。
    JS から呼ぶメソッド名と Python Signal 名は衝突させない。
    """

    # JS 側 → Python 側 (内部 Signal、ウィジェット側でリレーされる)
    user_input = Signal(bytes)
    resized = Signal(int, int)
    ready = Signal()

    # Python 側 → JS 側 (JS で .connect される)
    output_b64 = Signal(str)
    terminal_cleared = Signal()

    @Slot(str)
    def user_input_b64(self, b64: str) -> None:
        try:
            data = base64.b64decode(b64.encode("ascii"), validate=True)
        except (ValueError, TypeError):
            return
        if data:
            self.user_input.emit(data)

    @Slot(int, int)
    def report_resize(self, cols: int, rows: int) -> None:
        """JS から端末サイズ変更を通知される Slot。"""
        self.resized.emit(int(cols), int(rows))

    @Slot()
    def notify_ready(self) -> None:
        self.ready.emit()


class _LocalOnlyPage(QWebEnginePage):
    """``file://`` 以外への遷移を拒否する WebPage。"""

    def acceptNavigationRequest(  # type: ignore[override]
        self, url: QUrl, _type, _is_main_frame: bool
    ) -> bool:
        scheme = url.scheme().lower()
        return scheme in ("file", "qrc", "")


class XtermTerminalView(QWebEngineView):
    """xterm.js ベースのターミナル描画ウィジェット。

    使い方:
        view = XtermTerminalView()
        view.ready.connect(lambda: ...)              # 初期化完了
        view.user_input.connect(pty.write)            # ユーザー入力 → PTY
        view.resized.connect(lambda c, r: pty.resize(c, r))
        # PTY 出力を流し込む:
        view.feed_output(b"hello\\r\\n")
    """

    # 公開シグナル (外部はこちらだけを使う)
    user_input = Signal(bytes)
    resized = Signal(int, int)
    ready = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # セキュリティ強化
        self._page = _LocalOnlyPage(self)
        self.setPage(self._page)
        settings = self._page.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True
        )

        # QWebChannel ブリッジ
        self._bridge = _PyBridge(self)
        self._channel = QWebChannel(self._page)
        self._channel.registerObject("py_bridge", self._bridge)
        self._page.setWebChannel(self._channel)

        # ブリッジシグナルを外部公開シグナルへ転送
        self._bridge.user_input.connect(self.user_input)
        self._bridge.resized.connect(self.resized)
        self._bridge.ready.connect(self.ready)

        # index.html をロード
        if not _INDEX_HTML.is_file():
            raise FileNotFoundError(
                f"xterm assets missing: {_INDEX_HTML}. "
                "Run `python tools/fetch_xterm_assets.py` to populate."
            )
        self.setUrl(QUrl.fromLocalFile(str(_INDEX_HTML)))

    # ------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------
    def feed_output(self, data: bytes) -> None:
        """PTY 出力をターミナルへ書き込む。"""
        if not data:
            return
        b64 = base64.b64encode(data).decode("ascii")
        self._bridge.output_b64.emit(b64)

    def clear_terminal(self) -> None:
        """画面クリア。"""
        self._bridge.terminal_cleared.emit()
