"""hve/tests/test_xterm_terminal_view.py — xterm.js ターミナルウィジェットの最小テスト。

QtWebEngine が利用できない CI 環境では skip する。実際の描画検証は
``loadFinished`` + ``ready`` シグナル待機 + ``runJavaScript`` での値取得で行う。
"""

from __future__ import annotations

import os

import pytest

# QtWebEngine 不在の環境は丸ごと skip。
try:
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: F401
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    pytest.skip("PySide6 QtWebEngine not installed", allow_module_level=True)


@pytest.fixture(scope="module")
def qapp():
    """QApplication のシングルトン。"""
    # QtWebEngine は offscreen platform でも動作可能。
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _run_until(predicate, timeout_ms: int = 15000) -> bool:
    """``predicate()`` が True を返すまで Qt イベントループを回す。"""
    loop = QEventLoop()
    deadline_timer = QTimer()
    deadline_timer.setSingleShot(True)
    deadline_timer.timeout.connect(loop.quit)
    deadline_timer.start(timeout_ms)
    poll = QTimer()
    poll.setInterval(50)

    def on_poll() -> None:
        if predicate():
            loop.quit()

    poll.timeout.connect(on_poll)
    poll.start()
    loop.exec()
    poll.stop()
    deadline_timer.stop()
    return predicate()


def test_xterm_terminal_view_loads_and_ready(qapp) -> None:
    """ウィジェットがロード→ready シグナルを発火するまでを検証。"""
    from hve.gui.widgets.xterm_terminal_view import XtermTerminalView

    view = XtermTerminalView()
    view.resize(640, 240)
    view.show()

    ready_flag = {"v": False}

    def on_ready() -> None:
        ready_flag["v"] = True

    view.ready.connect(on_ready)

    ok = _run_until(lambda: ready_flag["v"], timeout_ms=20000)
    assert ok, "XtermTerminalView did not emit ready within 20s"


def test_feed_output_appears_in_terminal_buffer(qapp) -> None:
    """``feed_output`` で書き込んだバイト列が xterm.js の内部バッファに反映される。"""
    from hve.gui.widgets.xterm_terminal_view import XtermTerminalView

    view = XtermTerminalView()
    view.resize(640, 240)
    view.show()

    ready_flag = {"v": False}
    view.ready.connect(lambda: ready_flag.update(v=True))

    assert _run_until(lambda: ready_flag["v"], timeout_ms=20000), "ready timeout"

    view.feed_output(b"hello-xterm\r\n")

    # xterm.js の term.buffer.active.getLine(0).translateToString() で行内容を取得。
    result = {"line": None, "debug": None}

    def js_cb(value) -> None:
        result["line"] = value

    def debug_cb(value) -> None:
        result["debug"] = value

    def query() -> None:
        view.page().runJavaScript(
            "JSON.stringify({"
            "feed_count: window.__feed_count, "
            "last_bytes: window.__last_feed_bytes, "
            "line0: (window.term && window.term.buffer && window.term.buffer.active && "
            "window.term.buffer.active.getLine(0)) ? "
            "window.term.buffer.active.getLine(0).translateToString(true) : ''"
            "})",
            debug_cb,
        )

    # write は非同期で xterm 内部にコミットされるため、ポーリングで待つ。
    QTimer.singleShot(0, query)

    def has_hello() -> bool:
        if result["debug"] is None:
            QTimer.singleShot(100, query)
            return False
        import json as _json
        try:
            d = _json.loads(str(result["debug"]))
        except Exception:
            return False
        result["line"] = d.get("line0")
        if "hello-xterm" in str(d.get("line0", "")):
            return True
        QTimer.singleShot(100, query)
        return False

    assert _run_until(has_hello, timeout_ms=10000), (
        f"feed_output content not found in xterm buffer (debug={result['debug']!r})"
    )
