"""hve.gui.tests.test_gh_login_dialog

GhLoginDialog の単体テスト（offscreen）。

実 ``gh`` は一切起動しない。``find_gh_binary`` / ``is_pty_available`` /
``pty_backend.spawn`` / ``XtermTerminalView`` を mock し、事前チェック分岐と
端末配線・終了ハンドラを決定論的に検証する。
"""

from __future__ import annotations

import os
import time
from typing import List, Optional

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _label_texts(dlg) -> str:
    """ダイアログ内の全 QLabel テキストを連結して返す（案内文の内容検証用）。"""
    return "\n".join(lbl.text() for lbl in dlg.findChildren(QLabel))


def _process_events_until(qapp, predicate, *, timeout_ms: int = 1000) -> bool:
    """Qt イベントを処理しながら ``predicate`` が真になるまで短時間待つ。"""
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    qapp.processEvents()
    return bool(predicate())


class _FakeView(QWidget):
    """XtermTerminalView 互換の最小ビュー（QtWebEngine 非依存）。"""

    user_input = Signal(bytes)
    resized = Signal(int, int)
    ready = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.fed: List[bytes] = []

    def feed_output(self, data: bytes) -> None:
        self.fed.append(data)


class _FakeSession:
    """PtySession 互換の Fake。"""

    def __init__(self) -> None:
        self.closed = False
        self.close_count = 0
        self.read_count = 0

    def read_nowait(self, max_bytes: int = 4096) -> bytes:
        self.read_count += 1
        return b""

    def write(self, data: bytes) -> int:
        return len(data)

    def resize(self, cols: int, rows: int) -> None:
        pass

    def is_alive(self) -> bool:
        return True

    def exit_code(self) -> Optional[int]:
        return None

    def close(self, *, grace_seconds: float = 2.0) -> Optional[int]:
        self.closed = True
        self.close_count += 1
        return 0


def _patch_available(monkeypatch, *, spawn=None):
    """gh あり / pty 利用可 / XtermTerminalView を Fake に差し替える共通設定。"""
    import hve.gui.gh_login_dialog as mod

    monkeypatch.setattr(mod.gh_cli, "find_gh_binary", lambda: "/usr/bin/gh")
    monkeypatch.setattr(mod.pty_backend, "is_pty_available", lambda: True)
    monkeypatch.setattr(
        "hve.gui.widgets.xterm_terminal_view.XtermTerminalView", _FakeView
    )
    if spawn is not None:
        monkeypatch.setattr(mod.pty_backend, "spawn", spawn)
    return mod


def _start_terminal_dialog(qapp, monkeypatch):
    """端末起動済みの GhLoginDialog と Fake session を返す。"""
    session = _FakeSession()
    mod = _patch_available(monkeypatch, spawn=lambda *_a, **_k: session)
    dlg = mod.GhLoginDialog()
    view = dlg.findChild(_FakeView)
    assert view is not None
    view.ready.emit()
    assert _process_events_until(qapp, lambda: session.read_count > 0)
    return dlg, session


def _terminal_thread_stopped(dlg) -> bool:
    controller = getattr(dlg, "_controller", None)
    return controller is None or not controller._thread.isRunning()


def _force_cleanup_dialog(dlg) -> None:
    controller = getattr(dlg, "_controller", None)
    if controller is not None:
        controller.stop()
    dlg.close()


# ---------------------------------------------------------------------------
# 事前チェック分岐
# ---------------------------------------------------------------------------
def test_gh_missing_shows_guidance_and_no_spawn(qapp, monkeypatch) -> None:
    import hve.gui.gh_login_dialog as mod

    monkeypatch.setattr(mod.gh_cli, "find_gh_binary", lambda: None)
    called = {"spawn": False}
    monkeypatch.setattr(
        mod.pty_backend, "spawn", lambda *_a, **_k: called.__setitem__("spawn", True)
    )
    dlg = mod.GhLoginDialog()
    try:
        assert dlg.terminal_started is False
        assert called["spawn"] is False
        assert "gh" in _label_texts(dlg)
    finally:
        dlg.close()


def test_pty_unavailable_shows_guidance_and_no_spawn(qapp, monkeypatch) -> None:
    import hve.gui.gh_login_dialog as mod

    monkeypatch.setattr(mod.gh_cli, "find_gh_binary", lambda: "/usr/bin/gh")
    monkeypatch.setattr(mod.pty_backend, "is_pty_available", lambda: False)
    called = {"spawn": False}
    monkeypatch.setattr(
        mod.pty_backend, "spawn", lambda *_a, **_k: called.__setitem__("spawn", True)
    )
    dlg = mod.GhLoginDialog()
    try:
        assert dlg.terminal_started is False
        assert called["spawn"] is False
        assert "PTY" in _label_texts(dlg)
    finally:
        dlg.close()


# ---------------------------------------------------------------------------
# 端末起動パス
# ---------------------------------------------------------------------------
def test_available_path_spawns_gh_login(qapp, monkeypatch) -> None:
    spawned: dict = {}

    def fake_spawn(argv, **_kw):
        spawned["argv"] = argv
        return _FakeSession()

    mod = _patch_available(monkeypatch, spawn=fake_spawn)
    dlg = mod.GhLoginDialog()
    try:
        assert spawned["argv"] == ["gh", "auth", "login"]
        assert dlg.terminal_started is True
    finally:
        dlg.close()


def test_ready_signal_starts_terminal_controller(qapp, monkeypatch) -> None:
    """xterm 初期化完了通知で PTY 読み取りが開始される。"""
    dlg, session = _start_terminal_dialog(qapp, monkeypatch)
    try:
        assert session.read_count > 0
    finally:
        dlg.close()


def test_accept_stops_terminal_controller(qapp, monkeypatch) -> None:
    """accept() 経路でも worker thread と PTY session を停止する。"""
    dlg, session = _start_terminal_dialog(qapp, monkeypatch)
    try:
        dlg.accept()
        assert _process_events_until(
            qapp,
            lambda: session.closed and _terminal_thread_stopped(dlg),
        )
        assert session.close_count == 1
    finally:
        _force_cleanup_dialog(dlg)


def test_reject_stops_terminal_controller(qapp, monkeypatch) -> None:
    """reject() 経路でも worker thread と PTY session を停止する。"""
    dlg, session = _start_terminal_dialog(qapp, monkeypatch)
    try:
        dlg.reject()
        assert _process_events_until(
            qapp,
            lambda: session.closed and _terminal_thread_stopped(dlg),
        )
        assert session.close_count == 1
    finally:
        _force_cleanup_dialog(dlg)


def test_spawn_failure_shows_error_and_not_started(qapp, monkeypatch) -> None:
    import hve.gui.gh_login_dialog as mod

    def boom(*_a, **_k):
        raise mod.pty_backend.PtyBackendError("spawn nope")

    _patch_available(monkeypatch, spawn=boom)
    dlg = mod.GhLoginDialog()
    try:
        assert dlg.terminal_started is False
        assert "失敗" in dlg._status_label.text()
    finally:
        dlg.close()


def test_login_finished_updates_status_and_emits(qapp, monkeypatch) -> None:
    mod = _patch_available(monkeypatch, spawn=lambda *_a, **_k: _FakeSession())
    dlg = mod.GhLoginDialog()
    try:
        codes: List[int] = []
        dlg.login_completed.connect(codes.append)

        dlg._on_login_finished(0)
        assert dlg.exit_code == 0
        assert codes == [0]

        dlg._on_login_finished(1)
        assert dlg.exit_code == 1
        assert codes == [0, 1]
        assert "exit=1" in dlg._status_label.text()
    finally:
        dlg.close()


def test_close_stops_controller(qapp, monkeypatch) -> None:
    session = _FakeSession()
    mod = _patch_available(monkeypatch, spawn=lambda *_a, **_k: session)
    dlg = mod.GhLoginDialog()
    assert dlg.terminal_started is True
    dlg.close()
    assert session.closed is True
    assert session.close_count == 1
