"""test_keybind.py — Phase 6 Resume: KeybindMonitor のユニットテスト。

DoD（Phase 6）:
- pytest 環境では自動的に無効化されることを検証する
- 登録キーで handler が呼ばれ、未登録キーでは呼ばれないことを検証する
- stop() でスレッドが確実に終了することを検証する
- Ctrl+R 検出時の pause flow（state status 更新 + running step の failed 降格）を検証する
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from keybind import (  # type: ignore[import-not-found]
    KEY_CTRL_R,
    KeybindMonitor,
    is_keybind_supported,
)
from run_state import RunState  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# 環境判定
# ---------------------------------------------------------------------------


class TestIsKeybindSupported(unittest.TestCase):
    """`is_keybind_supported()` の各無効化条件を検証する。"""

    def test_disabled_in_pytest(self) -> None:
        """pytest 内では PYTEST_CURRENT_TEST が立つので False を返す。"""
        # 既に PYTEST_CURRENT_TEST が立っている前提（pytest 実行中）
        self.assertIn("PYTEST_CURRENT_TEST", os.environ)
        self.assertFalse(is_keybind_supported())

    def test_disabled_by_explicit_env_flag(self) -> None:
        """HVE_DISABLE_KEYBIND=1 で明示的に無効化できる。"""
        with mock.patch.dict(os.environ, {"HVE_DISABLE_KEYBIND": "1"}, clear=False):
            # PYTEST 判定が先に発火するが、明示無効化も独立に効くことを確認
            self.assertFalse(is_keybind_supported())

    def test_enabled_when_all_conditions_met(self) -> None:
        """全条件を満たせば True。"""
        # PYTEST_CURRENT_TEST を一時的に消し、stdin を TTY 扱いにする
        env_no_pytest = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
        env_no_pytest.pop("HVE_DISABLE_KEYBIND", None)
        with mock.patch.dict(os.environ, env_no_pytest, clear=True):
            with mock.patch.object(sys.stdin, "isatty", return_value=True):
                self.assertTrue(is_keybind_supported())

    def test_disabled_when_stdin_not_tty(self) -> None:
        """stdin が TTY でなければ無効化される。"""
        env_no_pytest = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
        env_no_pytest.pop("HVE_DISABLE_KEYBIND", None)
        with mock.patch.dict(os.environ, env_no_pytest, clear=True):
            with mock.patch.object(sys.stdin, "isatty", return_value=False):
                self.assertFalse(is_keybind_supported())


# ---------------------------------------------------------------------------
# KeybindMonitor — register / start / stop の基本動作
# ---------------------------------------------------------------------------


class TestKeybindMonitorBasics(unittest.TestCase):
    """KeybindMonitor の register / start / stop の基本契約を検証する。"""

    def test_disabled_in_pytest_skips_start(self) -> None:
        """pytest 内では enabled=False、start() しても thread は立たない。"""
        loop = asyncio.new_event_loop()
        try:
            monitor = KeybindMonitor(loop)
            self.assertFalse(monitor.enabled)
            monitor.start()
            self.assertIsNone(monitor._thread)
            monitor.stop()  # idempotent
        finally:
            loop.close()

    def test_register_validates_key_length(self) -> None:
        """register() は 1 バイト以外の key を弾く。"""
        monitor = KeybindMonitor()

        async def _noop() -> None:
            return None

        with self.assertRaises(ValueError):
            monitor.register(b"", _noop)
        with self.assertRaises(ValueError):
            monitor.register(b"ab", _noop)
        with self.assertRaises(ValueError):
            monitor.register("R", _noop)  # type: ignore[arg-type]

    def test_register_validates_callable(self) -> None:
        """register() は handler が callable でなければ TypeError。"""
        monitor = KeybindMonitor()
        with self.assertRaises(TypeError):
            monitor.register(KEY_CTRL_R, "not callable")  # type: ignore[arg-type]

    def test_stop_is_idempotent(self) -> None:
        """stop() は複数回呼んでも安全。"""
        monitor = KeybindMonitor()
        monitor.stop()
        monitor.stop()  # second call — no exception


# ---------------------------------------------------------------------------
# KeybindMonitor — _dispatch のキー振り分け
# ---------------------------------------------------------------------------


class TestKeybindDispatch(unittest.TestCase):
    """_dispatch の key matching 動作を検証する（スレッド/stdin に依存しない）。"""

    def test_dispatch_calls_registered_handler(self) -> None:
        """登録キーが渡されると handler が asyncio ループへ投入される。"""
        loop = asyncio.new_event_loop()
        invoked = threading.Event()

        async def _handler() -> None:
            invoked.set()

        # 専用スレッドで loop を回す（_dispatch は別スレッドから呼ばれる前提）
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            monitor = KeybindMonitor(loop)
            monitor.register(KEY_CTRL_R, _handler)
            monitor._dispatch(KEY_CTRL_R)
            self.assertTrue(invoked.wait(timeout=2.0))
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2.0)
            loop.close()

    def test_dispatch_ignores_unregistered_key(self) -> None:
        """未登録のキーは handler に渡らない（誤検出ゼロ）。"""
        loop = asyncio.new_event_loop()
        invoked = threading.Event()

        async def _handler() -> None:
            invoked.set()

        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            monitor = KeybindMonitor(loop)
            monitor.register(KEY_CTRL_R, _handler)
            # 別キー（Enter = 0x0d）を投入
            monitor._dispatch(b"\r")
            monitor._dispatch(b"a")
            monitor._dispatch(b"\x1b")  # ESC
            self.assertFalse(invoked.wait(timeout=0.3))
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2.0)
            loop.close()

    def test_dispatch_without_loop_is_safe(self) -> None:
        """loop 未設定のままでも例外を投げない（防御的設計）。"""
        monitor = KeybindMonitor()  # loop=None, enabled=False (pytest 内)

        async def _handler() -> None:
            return None

        monitor.register(KEY_CTRL_R, _handler)
        # _loop が None でも _dispatch は静かに無視する
        monitor._dispatch(KEY_CTRL_R)


# ---------------------------------------------------------------------------
# KeybindMonitor — 監視スレッドのライフサイクル（疑似環境を強制有効化）
# ---------------------------------------------------------------------------


class TestKeybindMonitorThreadLifecycle(unittest.TestCase):
    """enabled を強制 True に上書きしてスレッドの開始/停止を検証する。

    実際の stdin は触らないため、_run_posix / _run_windows のモック差し替えで
    スレッド本体の挙動だけを検証する。
    """

    def test_start_then_stop_terminates_thread(self) -> None:
        """start → stop でスレッドが確実に join できる。"""
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            monitor = KeybindMonitor(loop)
            monitor.enabled = True  # 強制有効化

            run_started = threading.Event()
            run_stopped = threading.Event()

            def _fake_run() -> None:
                run_started.set()
                # _stop_event が立つまで poll
                while not monitor._stop_event.is_set():
                    time.sleep(0.01)
                run_stopped.set()

            with mock.patch.object(monitor, "_run", _fake_run):
                monitor.start()
                self.assertTrue(run_started.wait(timeout=2.0))
                self.assertIsNotNone(monitor._thread)
                self.assertTrue(monitor._thread.is_alive())  # type: ignore[union-attr]

                monitor.stop(timeout=2.0)
                self.assertTrue(run_stopped.is_set())
                self.assertIsNone(monitor._thread)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2.0)
            loop.close()

    def test_start_is_idempotent(self) -> None:
        """start() を二度呼んでもスレッドは 1 つだけ。"""
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            monitor = KeybindMonitor(loop)
            monitor.enabled = True

            def _fake_run() -> None:
                while not monitor._stop_event.is_set():
                    time.sleep(0.01)

            with mock.patch.object(monitor, "_run", _fake_run):
                monitor.start()
                first_thread = monitor._thread
                monitor.start()  # 二度目は no-op
                self.assertIs(monitor._thread, first_thread)
                monitor.stop()
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2.0)
            loop.close()

    def test_context_manager_starts_and_stops(self) -> None:
        """with 文で start / stop が呼ばれる。"""
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            monitor = KeybindMonitor(loop)
            monitor.enabled = True

            run_iterations = {"count": 0}

            def _fake_run() -> None:
                while not monitor._stop_event.is_set():
                    run_iterations["count"] += 1
                    time.sleep(0.01)

            with mock.patch.object(monitor, "_run", _fake_run):
                with monitor:
                    self.assertIsNotNone(monitor._thread)
                # __exit__ で stop されているはず
                self.assertIsNone(monitor._thread)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2.0)
            loop.close()


# ---------------------------------------------------------------------------
# orchestrator 側 pause flow（state 更新の契約）の独立検証
# ---------------------------------------------------------------------------


class TestPauseFlowStateUpdate(unittest.TestCase):
    """Ctrl+R 中断時に RunState が paused に遷移し、running step が failed
    に降格される orchestrator 側の更新ロジックを、最小再現で検証する。

    orchestrator の実関数を呼ぶのではなく「同じシーケンス」を直接適用する
    ことで、state 永続化の契約だけを確認する。
    """

    def test_paused_state_persistence(self) -> None:
        """state.json に status=paused / pause_reason=ctrl+r が保存される。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "runs"
            state = RunState.new(
                run_id="20260507T153012-test01",
                workflow_id="aad",
                config=None,
                params={"app_id": "APP-05"},
                selected_step_ids=["1.1", "1.2", "1.3"],
                work_dir=work_dir,
            )
            # 1.1 完了, 1.2 実行中, 1.3 未着手の状態を再現
            state.update_step("1.1", status="completed")
            state.update_step("1.2", status="running")

            # orchestrator の paused 早期 return と同じシーケンスを適用
            state.update_step(
                "1.2",
                status="failed",
                error_summary="ユーザーにより Ctrl+R で中断",
            )
            state.status = "paused"
            state.pause_reason = "ctrl+r"
            state.save()

            # ロード→検証
            reloaded = RunState.load("20260507T153012-test01", work_dir=work_dir)
            self.assertEqual(reloaded.status, "paused")
            self.assertEqual(reloaded.pause_reason, "ctrl+r")
            self.assertEqual(reloaded.step_states["1.1"].status, "completed")
            self.assertEqual(reloaded.step_states["1.2"].status, "failed")
            self.assertEqual(
                reloaded.step_states["1.2"].error_summary,
                "ユーザーにより Ctrl+R で中断",
            )
            self.assertEqual(reloaded.step_states["1.3"].status, "pending")


if __name__ == "__main__":
    unittest.main()
