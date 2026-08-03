"""WorkbenchPage の fatal 検知をサブプロセスからの実流入で検証する統合テスト。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.page_workbench import WorkbenchPage  # noqa: E402
from hve.gui.state_bridge import SubprocessReader  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


def _process_events(timeout_ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


_MOCK_SCRIPT_FATAL = """
import sys, time
sys.stdout.write('hello before fatal\\n')
sys.stdout.flush()
sys.stdout.write('[hve:fatal] {"kind":"fatal_abort","exception_type":"FileNotFoundError","message":"foo.yaml"}\\n')
sys.stdout.flush()
for _ in range(60):
    time.sleep(0.5)
    sys.stdout.write('post-dag still running\\n')
    sys.stdout.flush()
"""

_MOCK_SCRIPT_NORMAL_EXIT = """
import sys
sys.stdout.write('plain log line 1\\n')
sys.stdout.write('plain log line 2\\n')
sys.stdout.flush()
"""


class TestFatalIntegrationViaSubprocess(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.page = WorkbenchPage()

    def _spawn(self, script: str) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

    def test_fatal_marker_triggers_termination(self) -> None:
        proc = self._spawn(_MOCK_SCRIPT_FATAL)
        try:
            reader = SubprocessReader(proc, parent=self.page)
            received_codes: list = []
            self.page._is_running = True
            self.page._reader = reader
            reader.line_received.connect(self.page._on_line_received)
            reader.finished_with_code.connect(received_codes.append)
            reader.start()

            t_start = time.monotonic()
            deadline = t_start + 10.0
            while time.monotonic() < deadline:
                _process_events(50)
                if received_codes:
                    break

            elapsed = time.monotonic() - t_start
            self.assertTrue(
                received_codes,
                f"subprocess が deadline 内に終了しなかった (elapsed={elapsed:.2f}s)",
            )
            self.assertTrue(self.page.was_fatal())
            info = self.page.fatal_info() or {}
            self.assertEqual(info.get("exception_type"), "FileNotFoundError")
            self.assertEqual(info.get("message"), "foo.yaml")
            self.assertLess(elapsed, 10.0)
        finally:
            try:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=3.0)
            except OSError:
                pass

    def test_large_windows_exit_code_does_not_overflow(self) -> None:
        """Windows の符号なし 32bit 終了コードが ``finished_with_code`` emit で
        OverflowError にならないことを保証する回帰テスト。

        修正前は ``Signal(int)``（Qt 符号付き 32bit, 上限 2_147_483_647）のため
        ``0xC000013A``(=3221225786, Ctrl-C 終了) の emit で
        ``libshiboken: Overflow`` → OverflowError が発生していた。
        ``Signal("qlonglong")``(64bit) 化により解消。
        """
        win_ctrl_c_exit = 3221225786  # 0xC000013A, 2**31-1=2147483647 を超える

        class _FakeProc:
            """``returncode`` を直接注入する Popen 代替（プラットフォーム非依存）。"""

            def __init__(self, code: int) -> None:
                self.returncode = code
                self.stdout = None  # run() の「stdout is None」分岐で即 emit させる
                self.pid = -1

            def wait(self) -> int:
                return self.returncode

        reader = SubprocessReader(_FakeProc(win_ctrl_c_exit), parent=self.page)
        received: list = []
        reader.finished_with_code.connect(received.append)
        reader.run()  # 直接実行（スレッド不要）。crash していた emit 経路を通す
        self.assertEqual(received, [win_ctrl_c_exit])

    def test_no_fatal_marker_keeps_state_clean(self) -> None:
        proc = self._spawn(_MOCK_SCRIPT_NORMAL_EXIT)
        try:
            reader = SubprocessReader(proc, parent=self.page)
            received_codes: list = []
            self.page._is_running = True
            self.page._reader = reader
            reader.line_received.connect(self.page._on_line_received)
            reader.finished_with_code.connect(received_codes.append)
            reader.start()

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and not received_codes:
                _process_events(50)

            self.assertTrue(received_codes)
            self.assertFalse(self.page.was_fatal())
            self.assertFalse(self.page.was_fatal_marker_seen())
            self.assertIsNone(self.page.fatal_info())
        finally:
            try:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=3.0)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
