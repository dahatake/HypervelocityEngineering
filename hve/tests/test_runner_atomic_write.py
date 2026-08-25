"""test_runner_atomic_write.py — GUI QA IPC のアトミック書き込みの RED テスト。

Windows では監視側（GUI の `QFileSystemWatcher` 通知で宛先を開く読み取り）が
ファイルを掴んでいる瞬間に `os.replace` が `PermissionError` (WinError 5) を返し、
`_collect_qa_answers_via_ipc` の書き込みが落ちることがある。
実測: `hve/gui/tests/test_qa_ipc_flow.py::TestQAIpcFlow::test_other_freetext_round_trip`
が同一環境で断続的に失敗し、再実行では成功していた。

実装前は `_atomic_write_text` が存在せず、再試行も無いため RED となる。
"""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import runner as runner_mod  # noqa: E402

_REAL_REPLACE = os.replace


class TestAtomicWriteText(unittest.TestCase):
    """IPC 書き込みは監視側との衝突で落ちてはならない。"""

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "2.1.questionnaire.md"

    def test_writes_content(self) -> None:
        runner_mod._atomic_write_text(self.path, "本文\n")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "本文\n")

    def test_no_tmp_file_is_left_behind(self) -> None:
        runner_mod._atomic_write_text(self.path, "本文\n")
        self.assertEqual(list(self.dir.glob("*.tmp")), [])

    def test_retries_on_permission_error(self) -> None:
        calls = {"n": 0}

        def flaky_replace(src, dst):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise PermissionError(5, "アクセスが拒否されました。")
            return _REAL_REPLACE(src, dst)

        with patch("os.replace", side_effect=flaky_replace), \
                patch.object(runner_mod.time, "sleep") as sleep:
            runner_mod._atomic_write_text(self.path, "再試行後の本文\n")

        self.assertEqual(calls["n"], 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(
            self.path.read_text(encoding="utf-8"), "再試行後の本文\n",
        )

    def test_raises_after_exhausting_retries(self) -> None:
        def always_denied(src, dst):
            raise PermissionError(5, "アクセスが拒否されました。")

        with patch("os.replace", side_effect=always_denied), \
                patch.object(runner_mod.time, "sleep"):
            with self.assertRaises(PermissionError):
                runner_mod._atomic_write_text(self.path, "本文\n")

    def test_other_oserror_is_not_retried(self) -> None:
        """再試行してよいのは宛先ロックに由来する PermissionError だけ。"""
        calls = {"n": 0}

        def not_a_directory(src, dst):
            calls["n"] += 1
            raise IsADirectoryError(21, "Is a directory")

        with patch("os.replace", side_effect=not_a_directory), \
                patch.object(runner_mod.time, "sleep"):
            with self.assertRaises(IsADirectoryError):
                runner_mod._atomic_write_text(self.path, "本文\n")
        self.assertEqual(calls["n"], 1)


class TestIpcWriterUsesTheHelper(unittest.TestCase):
    """IPC 書き込み経路は再試行付きヘルパーを使う（同一ルールの二重実装禁止）。"""

    def _source(self) -> str:
        return inspect.getsource(runner_mod._collect_qa_answers_via_ipc)

    def test_uses_the_shared_helper(self) -> None:
        self.assertIn("_atomic_write_text(", self._source())

    def test_does_not_define_a_local_writer(self) -> None:
        self.assertNotIn("def _atomic_write(", self._source())


if __name__ == "__main__":
    unittest.main()
