"""test_run_lock_crossproc.py — Phase 2 (Major #19): クロスプロセス排他テスト。

`subprocess.Popen` で別 Python プロセスを起動し、同 run_id への 2 つ目のロック
取得が `RunLockError` で失敗することを実機検証する。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


HVE_DIR = Path(__file__).resolve().parent.parent


def _spawn_lock_holder(work_dir: Path, run_id: str, hold_seconds: float) -> subprocess.Popen:
    """子プロセスで RunLock を取得し、hold_seconds 秒保持してから解放する。"""
    script = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(HVE_DIR)!r})
        from run_lock import RunLock
        lock = RunLock({run_id!r}, {str(work_dir)!r})
        lock.acquire()
        print("ACQUIRED", flush=True)
        time.sleep({hold_seconds})
        lock.release()
        print("RELEASED", flush=True)
    """)
    return subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class TestCrossProcessLock(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"
        self.work_dir.mkdir(parents=True)
        self.run_id = "20260512T000000-crossproc01"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_second_process_fails_to_acquire(self) -> None:
        """子プロセスが lock 保持中、別 Python プロセスは取得失敗する。"""
        child = _spawn_lock_holder(self.work_dir, self.run_id, hold_seconds=3.0)
        try:
            # 子プロセスが lock 取得完了するまで待つ
            for _ in range(30):
                line = child.stdout.readline()
                if line and "ACQUIRED" in line:
                    break
                time.sleep(0.1)
            else:
                self.fail("子プロセスが lock を取得できなかった")

            # 親プロセスから 2 つ目の取得を試みる → RunLockError
            from run_lock import RunLock, RunLockError  # type: ignore[import-not-found]

            lock2 = RunLock(self.run_id, self.work_dir)
            with self.assertRaises(RunLockError):
                lock2.acquire(allow_stale_steal=False)
        finally:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()

    def test_acquire_succeeds_after_child_release(self) -> None:
        """子プロセス release 後に親プロセスは取得できる。"""
        child = _spawn_lock_holder(self.work_dir, self.run_id, hold_seconds=0.5)
        try:
            # 子プロセスが lock 取得完了まで待つ
            for _ in range(30):
                line = child.stdout.readline()
                if line and "ACQUIRED" in line:
                    break
                time.sleep(0.1)
            child.wait(timeout=10)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()

        # 子プロセス終了後、親プロセスから取得成功するはず
        from run_lock import RunLock  # type: ignore[import-not-found]

        lock2 = RunLock(self.run_id, self.work_dir)
        lock2.acquire()
        try:
            self.assertTrue(lock2.acquired)
        finally:
            lock2.release()


if __name__ == "__main__":
    unittest.main()
