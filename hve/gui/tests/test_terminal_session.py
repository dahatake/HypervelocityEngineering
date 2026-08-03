"""hve.gui.tests.test_terminal_session

TerminalSessionController の単体テスト（offscreen / QWebEngine 非依存）。

Fake PtySession と Fake view（QObject + Signals）で配線を決定論的に検証する。
QTimer の発火を待たず、内部スロット ``_on_poll`` を直接呼ぶことで離散化する。
"""

from __future__ import annotations

import os
import time
import threading
from typing import List, Optional, Tuple

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, QThread, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeView(QObject):
    """``feed_output`` と ``user_input`` / ``resized`` を持つ最小ビュー。"""

    user_input = Signal(bytes)
    resized = Signal(int, int)

    def __init__(self, *, main_thread: Optional[QThread] = None) -> None:
        super().__init__()
        self._main_thread = main_thread
        self.fed: List[bytes] = []
        self.feed_in_main_thread: List[bool] = []

    def feed_output(self, data: bytes) -> None:
        if self._main_thread is not None:
            self.feed_in_main_thread.append(QThread.currentThread() == self._main_thread)
        self.fed.append(data)


class _FakeSession:
    """PtySession インターフェース互換の Fake。"""

    def __init__(
        self,
        reads: Optional[List[bytes]] = None,
        *,
        alive: bool = True,
        exit_code: Optional[int] = 0,
        raise_on_read: bool = False,
        main_thread: Optional[QThread] = None,
    ) -> None:
        self._reads: List[bytes] = list(reads or [])
        self._alive = alive
        self._exit_code = exit_code
        self._raise_on_read = raise_on_read
        self._main_thread = main_thread
        self.read_in_main_thread: List[bool] = []
        self.written: List[bytes] = []
        self.resizes: List[Tuple[int, int]] = []
        self.closed = False

    def read_nowait(self, max_bytes: int = 4096) -> bytes:
        if self._main_thread is not None:
            self.read_in_main_thread.append(QThread.currentThread() == self._main_thread)
        if self._raise_on_read:
            raise OSError("boom")
        if self._reads:
            return self._reads.pop(0)
        return b""

    def write(self, data: bytes) -> int:
        self.written.append(data)
        return len(data)

    def resize(self, cols: int, rows: int) -> None:
        self.resizes.append((cols, rows))

    def is_alive(self) -> bool:
        return self._alive

    def set_dead(self) -> None:
        self._alive = False

    def exit_code(self) -> Optional[int]:
        return self._exit_code

    def close(self, *, grace_seconds: float = 2.0) -> Optional[int]:
        self.closed = True
        return self._exit_code


class _BlockingReadSession(_FakeSession):
    """read_nowait が write/close まで戻らない対話プロンプト待ち Fake。"""

    def __init__(self) -> None:
        super().__init__()
        self._unblock = threading.Event()

    def read_nowait(self, max_bytes: int = 4096) -> bytes:
        self._unblock.wait(1.5)
        return b""

    def write(self, data: bytes) -> int:
        result = super().write(data)
        self._unblock.set()
        return result

    def close(self, *, grace_seconds: float = 2.0) -> Optional[int]:
        self._unblock.set()
        return super().close(grace_seconds=grace_seconds)


def _make_controller(session, view):
    from hve.gui.widgets.terminal_session import TerminalSessionController

    return TerminalSessionController(session, view)


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


def test_output_is_fed_to_view(qapp) -> None:
    """生存中の poll で read 出力が view.feed_output へ流れる。"""
    session = _FakeSession([b"hello"])
    view = _FakeView()
    ctrl = _make_controller(session, view)
    ctrl.start()
    try:
        assert _process_events_until(qapp, lambda: view.fed == [b"hello"])
    finally:
        ctrl.stop()


def test_reader_does_not_poll_on_gui_thread(qapp) -> None:
    """PTY 読み取りは GUI スレッド外で行い、描画だけ GUI スレッドへ戻す。"""
    main_thread = qapp.thread()
    session = _FakeSession([b"hello"], main_thread=main_thread)
    view = _FakeView(main_thread=main_thread)
    ctrl = _make_controller(session, view)
    ctrl.start()
    try:
        assert _process_events_until(qapp, lambda: view.fed == [b"hello"])
        assert session.read_in_main_thread
        assert all(flag is False for flag in session.read_in_main_thread)
        assert view.feed_in_main_thread == [True]
    finally:
        ctrl.stop()


def test_user_input_forwarded_to_session(qapp) -> None:
    """view.user_input シグナルが session.write へ転送される。"""
    session = _FakeSession()
    view = _FakeView()
    ctrl = _make_controller(session, view)  # GC 防止のため参照を保持
    assert ctrl is not None
    ctrl.start()
    try:
        view.user_input.emit(b"abc")
        assert _process_events_until(qapp, lambda: session.written == [b"abc"])
    finally:
        ctrl.stop()


def test_user_input_is_not_starved_by_blocking_read(qapp) -> None:
    """read 待ち中でも端末入力は worker event loop に詰まらず write へ届く。"""
    session = _BlockingReadSession()
    view = _FakeView()
    ctrl = _make_controller(session, view)
    ctrl.start()
    try:
        qapp.processEvents()
        view.user_input.emit(b"abc")
        assert _process_events_until(qapp, lambda: session.written == [b"abc"])
    finally:
        ctrl.stop()


def test_stop_is_not_starved_by_blocking_read(qapp) -> None:
    """read 待ち中でも stop() は queued worker slot 待ちで固まらない。"""
    session = _BlockingReadSession()
    view = _FakeView()
    ctrl = _make_controller(session, view)
    ctrl.start()
    qapp.processEvents()
    started = time.monotonic()
    ctrl.stop()
    elapsed = time.monotonic() - started
    assert session.closed is True
    assert elapsed < 0.5


def test_resize_forwarded_to_session(qapp) -> None:
    """view.resized シグナルが session.resize へ転送される。"""
    session = _FakeSession()
    view = _FakeView()
    ctrl = _make_controller(session, view)  # GC 防止のため参照を保持
    assert ctrl is not None
    ctrl.start()
    try:
        view.resized.emit(100, 40)
        assert _process_events_until(qapp, lambda: session.resizes == [(100, 40)])
    finally:
        ctrl.stop()


def test_finished_emitted_with_drain_on_death(qapp) -> None:
    """終了検知時に残バッファを全てドレインし finished(exit_code) を発火する。"""
    session = _FakeSession([b"a", b"b", b"c"], alive=False, exit_code=0)
    view = _FakeView()
    ctrl = _make_controller(session, view)
    codes: List[int] = []
    ctrl.finished.connect(codes.append)
    ctrl.start()
    assert _process_events_until(qapp, lambda: codes == [0])
    # 先頭 read で b"a"、ドレインで b"b"/b"c" を吸い出す。
    assert view.fed == [b"a", b"b", b"c"]
    assert codes == [0]


def test_finished_exit_code_none_maps_to_minus_one(qapp) -> None:
    """exit_code が None のとき finished は -1 を通知する。"""
    session = _FakeSession([], alive=False, exit_code=None)
    view = _FakeView()
    ctrl = _make_controller(session, view)
    codes: List[int] = []
    ctrl.finished.connect(codes.append)
    ctrl.start()
    assert _process_events_until(qapp, lambda: codes == [-1])
    assert codes == [-1]


def test_finished_emitted_only_once(qapp) -> None:
    """終了確定後の再ポーリングで finished が二重発火しない。"""
    session = _FakeSession([], alive=False, exit_code=0)
    view = _FakeView()
    ctrl = _make_controller(session, view)
    codes: List[int] = []
    ctrl.finished.connect(codes.append)
    ctrl.start()
    assert _process_events_until(qapp, lambda: codes == [0])
    ctrl.start()
    qapp.processEvents()
    assert codes == [0]


def test_stop_closes_session(qapp) -> None:
    """stop() で session.close が呼ばれる。"""
    session = _FakeSession()
    view = _FakeView()
    ctrl = _make_controller(session, view)
    ctrl.stop()
    assert session.closed is True


def test_read_exception_is_swallowed(qapp) -> None:
    """read_nowait の例外を握りつぶし、view へは何も流さない。"""
    session = _FakeSession(raise_on_read=True)
    view = _FakeView()
    ctrl = _make_controller(session, view)
    ctrl.start()  # 例外を投げない
    try:
        _process_events_until(qapp, lambda: bool(session.read_in_main_thread), timeout_ms=100)
        assert view.fed == []
    finally:
        ctrl.stop()


def test_start_after_finish_is_noop(qapp) -> None:
    """終了確定後に start() してもポーリングは再開しない。"""
    session = _FakeSession([], alive=False, exit_code=0)
    view = _FakeView()
    ctrl = _make_controller(session, view)
    codes: List[int] = []
    ctrl.finished.connect(codes.append)
    ctrl.start()  # finished 確定
    assert _process_events_until(qapp, lambda: codes == [0])
    ctrl.start()
    qapp.processEvents()
    assert codes == [0]


def test_user_input_write_exception_is_swallowed(qapp) -> None:
    """session.write が例外を投げても _on_user_input はクラッシュしない。"""
    session = _FakeSession()

    def _boom(_data: bytes) -> int:
        raise OSError("write failed")

    session.write = _boom  # type: ignore[assignment]
    view = _FakeView()
    ctrl = _make_controller(session, view)  # GC 防止のため参照を保持
    assert ctrl is not None
    ctrl.start()
    try:
        view.user_input.emit(b"x")  # 例外が伝播しないこと（アサーションは到達自体）
        qapp.processEvents()
    finally:
        ctrl.stop()
