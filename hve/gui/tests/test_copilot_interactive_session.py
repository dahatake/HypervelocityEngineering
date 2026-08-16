"""hve.gui.tests.test_copilot_interactive_session

FR-GUI-10 / FR-GUI-11 の受入テスト。

Copilot パネルが使い捨ての ``copilot -p`` ではなく、GitHub Copilot CLI の対話
セッションを 1 プロセスとして維持することと、汎用チャットへ権限緩和フラグを
暗黙付与しないことを固定する。実 ``copilot`` プロセスは起動しない（PTY spawn を
差し替える）。
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, QThread, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.copilot_interactive_session import (  # noqa: E402
    CopilotInteractiveSession,
    CopilotInteractiveSessionError,
    build_interactive_argv,
)

# FR-GUI-11: 汎用チャットへ暗黙付与してはならないフラグ。
_FORBIDDEN_FLAGS = (
    "--allow-all",
    "--allow-all-tools",
    "--allow-all-paths",
    "--allow-all-urls",
    "--yolo",
    "--no-ask-user",
    "-p",
    "--prompt",
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeView(QObject):
    """``feed_output`` と ``user_input`` / ``resized`` を持つ最小ビュー。"""

    user_input = Signal(bytes)
    resized = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.fed: List[bytes] = []

    def feed_output(self, data: bytes) -> None:
        self.fed.append(data)


class _FakePtySession:
    """``PtySession`` 互換の Fake。"""

    def __init__(self, argv: List[str], cwd: Optional[str]) -> None:
        self.argv = list(argv)
        self.cwd = cwd
        self.written: List[bytes] = []
        self.resizes: List[Tuple[int, int]] = []
        self.closed = False
        self._alive = True

    def read_nowait(self, max_bytes: int = 4096) -> bytes:
        return b""

    def write(self, data: bytes) -> int:
        self.written.append(data)
        return len(data)

    def resize(self, cols: int, rows: int) -> None:
        self.resizes.append((cols, rows))

    def is_alive(self) -> bool:
        return self._alive

    def exit_code(self) -> Optional[int]:
        return None if self._alive else 0

    def terminate(self) -> None:
        self._alive = False

    def kill(self) -> None:
        self._alive = False

    def close(self, *, grace_seconds: float = 2.0) -> Optional[int]:
        self.closed = True
        self._alive = False
        return 0


class _SpawnRecorder:
    def __init__(self) -> None:
        self.calls: List[dict] = []
        self.sessions: List[_FakePtySession] = []

    def __call__(self, argv, *, cwd=None, env=None, dimensions=(80, 24)):
        self.calls.append({"argv": list(argv), "cwd": cwd, "dimensions": dimensions})
        session = _FakePtySession(argv, cwd)
        self.sessions.append(session)
        return session


def _make_session(qapp, tmp_path: Path, *, spawn=None, binary="/fake/bin/copilot",
                  pty_available=True) -> Tuple[CopilotInteractiveSession, _FakeView, _SpawnRecorder]:
    view = _FakeView()
    recorder = spawn or _SpawnRecorder()
    session = CopilotInteractiveSession(
        view,
        repo_root=tmp_path,
        binary_resolver=lambda: binary,
        pty_available=lambda: pty_available,
        spawn=recorder,
    )
    return session, view, recorder


def _process_until(qapp, predicate, *, timeout_ms: int = 1000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    qapp.processEvents()
    return bool(predicate())


# ---------------------------------------------------------------------------
# argv 契約（FR-GUI-10 / FR-GUI-11）
# ---------------------------------------------------------------------------


def test_build_argv_runs_in_repo_root_and_pins_runtime(tmp_path: Path) -> None:
    argv = build_interactive_argv("/fake/bin/copilot", tmp_path)
    assert argv[0] == "/fake/bin/copilot"
    assert "-C" in argv
    assert argv[argv.index("-C") + 1] == str(tmp_path)
    # FR-MODEL-07 と同じ理由でセッション中の自動更新を止める。
    assert "--no-auto-update" in argv


def test_build_argv_never_grants_blanket_permissions(tmp_path: Path) -> None:
    argv = build_interactive_argv("/fake/bin/copilot", tmp_path)
    for flag in _FORBIDDEN_FLAGS:
        assert flag not in argv, f"汎用チャットへ {flag} を暗黙付与してはならない"


def test_build_argv_uses_interactive_prompt_flag_not_oneshot(tmp_path: Path) -> None:
    """初期プロンプトは対話モード用 ``-i`` で渡し、使い捨て ``-p`` を使わない。"""
    argv = build_interactive_argv("/fake/bin/copilot", tmp_path, initial_prompt="hello job")
    assert "-i" in argv
    assert argv[argv.index("-i") + 1] == "hello job"
    assert "-p" not in argv
    assert "--prompt" not in argv


def test_build_argv_keeps_prompt_as_single_argument(tmp_path: Path) -> None:
    """シェル連結を行わず、プロンプト全体を 1 個の argv 要素として渡す。"""
    hostile = 'x" & del /q C:\\ & echo "'
    argv = build_interactive_argv("/fake/bin/copilot", tmp_path, initial_prompt=hostile)
    assert argv.count(hostile) == 1
    assert all(isinstance(item, str) for item in argv)


def test_build_argv_omits_prompt_flag_when_prompt_is_blank(tmp_path: Path) -> None:
    for blank in ("", "   ", None):
        argv = build_interactive_argv("/fake/bin/copilot", tmp_path, initial_prompt=blank)
        assert "-i" not in argv


# ---------------------------------------------------------------------------
# ライフサイクル（FR-GUI-10）
# ---------------------------------------------------------------------------


def test_start_spawns_one_interactive_process(qapp, tmp_path: Path) -> None:
    session, _view, recorder = _make_session(qapp, tmp_path)
    try:
        session.start()
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["cwd"] == str(tmp_path)
        assert session.is_running() is True
    finally:
        session.stop()


def test_start_while_running_does_not_spawn_again(qapp, tmp_path: Path) -> None:
    """複数ターン送信のたびにプロセスを起動し直さない。"""
    session, _view, recorder = _make_session(qapp, tmp_path)
    try:
        session.start()
        session.start()
        session.start()
        assert len(recorder.calls) == 1
    finally:
        session.stop()


def test_user_input_is_forwarded_to_the_same_process(qapp, tmp_path: Path) -> None:
    session, view, recorder = _make_session(qapp, tmp_path)
    try:
        session.start()
        view.user_input.emit(b"/model\r")
        view.user_input.emit(b"hello\r")
        pty = recorder.sessions[0]
        assert _process_until(qapp, lambda: pty.written == [b"/model\r", b"hello\r"])
    finally:
        session.stop()


def test_resize_is_forwarded_to_the_same_process(qapp, tmp_path: Path) -> None:
    session, view, recorder = _make_session(qapp, tmp_path)
    try:
        session.start()
        view.resized.emit(120, 40)
        pty = recorder.sessions[0]
        assert _process_until(qapp, lambda: pty.resizes == [(120, 40)])
    finally:
        session.stop()


def test_stop_closes_the_process_and_clears_running_state(qapp, tmp_path: Path) -> None:
    session, _view, recorder = _make_session(qapp, tmp_path)
    session.start()
    session.stop()
    assert recorder.sessions[0].closed is True
    assert session.is_running() is False


def test_restart_after_stop_spawns_a_new_process(qapp, tmp_path: Path) -> None:
    session, _view, recorder = _make_session(qapp, tmp_path)
    try:
        session.start()
        session.stop()
        session.start()
        assert len(recorder.calls) == 2
    finally:
        session.stop()


def test_stop_without_start_is_noop(qapp, tmp_path: Path) -> None:
    session, _view, recorder = _make_session(qapp, tmp_path)
    session.stop()
    assert recorder.calls == []
    assert session.is_running() is False


def test_finished_signal_reports_exit_code(qapp, tmp_path: Path) -> None:
    session, _view, recorder = _make_session(qapp, tmp_path)
    codes: List[int] = []
    session.finished.connect(codes.append)
    session.start()
    recorder.sessions[0].terminate()
    assert _process_until(qapp, lambda: codes != [])
    assert session.is_running() is False


# ---------------------------------------------------------------------------
# fail-closed（FR-GUI-10）
# ---------------------------------------------------------------------------


def test_missing_binary_fails_closed_with_setup_guidance(qapp, tmp_path: Path) -> None:
    session, _view, recorder = _make_session(qapp, tmp_path, binary=None)
    with pytest.raises(CopilotInteractiveSessionError) as excinfo:
        session.start()
    assert recorder.calls == []
    assert "setup" in str(excinfo.value).lower()


def test_missing_pty_backend_fails_closed_with_setup_guidance(qapp, tmp_path: Path) -> None:
    session, _view, recorder = _make_session(qapp, tmp_path, pty_available=False)
    with pytest.raises(CopilotInteractiveSessionError) as excinfo:
        session.start()
    assert recorder.calls == []
    assert "setup" in str(excinfo.value).lower()


def test_spawn_failure_is_reported_and_leaves_session_stopped(qapp, tmp_path: Path) -> None:
    def _boom(*_args, **_kwargs):
        raise OSError("spawn failed")

    session, _view, _recorder = _make_session(qapp, tmp_path, spawn=_boom)
    with pytest.raises(CopilotInteractiveSessionError):
        session.start()
    assert session.is_running() is False


def test_reader_does_not_poll_on_the_gui_thread(qapp, tmp_path: Path) -> None:
    """PTY 読み取りを GUI スレッドで行わない（既存 TerminalSessionController の契約）。"""
    main_thread = qapp.thread()
    observed: List[bool] = []

    class _ThreadProbeSession(_FakePtySession):
        def read_nowait(self, max_bytes: int = 4096) -> bytes:
            observed.append(QThread.currentThread() == main_thread)
            return b""

    class _ProbeSpawn(_SpawnRecorder):
        def __call__(self, argv, *, cwd=None, env=None, dimensions=(80, 24)):
            self.calls.append({"argv": list(argv), "cwd": cwd, "dimensions": dimensions})
            session = _ThreadProbeSession(argv, cwd)
            self.sessions.append(session)
            return session

    session, _view, _recorder = _make_session(qapp, tmp_path, spawn=_ProbeSpawn())
    try:
        session.start()
        assert _process_until(qapp, lambda: bool(observed))
        assert all(flag is False for flag in observed)
    finally:
        session.stop()
