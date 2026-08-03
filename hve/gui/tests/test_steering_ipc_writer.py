"""test_steering_ipc_writer.py — hve.gui.steering_ipc_writer.write_steering_request の単体テスト。

T10（T9: hve/gui/steering_ipc_writer.py 新規作成 に対応するテスト）。
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from hve.gui.steering_ipc_writer import write_steering_request


class TestWriteSteeringRequest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.ipc_dir = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_writes_expected_filename_pattern(self) -> None:
        path = write_steering_request(self.ipc_dir, "1.1", "hello")
        self.assertTrue(path.exists())
        self.assertRegex(path.name, r"^steering-1\.1-\d+\.request\.json$")

    def test_writes_valid_json_content(self) -> None:
        path = write_steering_request(self.ipc_dir, "1.1", "Actually, stop using Synapse.")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["text"], "Actually, stop using Synapse.")

    def test_creates_missing_directory(self) -> None:
        nested = self.ipc_dir / "nested" / "dir"
        self.assertFalse(nested.exists())
        path = write_steering_request(nested, "1.1", "hi")
        self.assertTrue(nested.is_dir())
        self.assertTrue(path.exists())

    def test_sanitizes_unsafe_step_id_characters(self) -> None:
        """`/` を含む step_id（fan-out 子想定）でもファイルシステム上安全な名前になる。"""
        path = write_steering_request(self.ipc_dir, "1/D01", "hi")
        self.assertNotIn("/", path.name)
        self.assertTrue(path.exists())

    def test_no_temp_file_left_behind(self) -> None:
        """アトミック書き込み後に .tmp ファイルが残らない。"""
        write_steering_request(self.ipc_dir, "1.1", "hi")
        tmp_files = list(self.ipc_dir.glob("*.tmp"))
        self.assertEqual(tmp_files, [])

    def test_filename_matches_runner_polling_glob_pattern(self) -> None:
        """runner.py::_poll_steering_ipc が使う glob パターンと一致することを確認する
        （相互運用性の直接検証）。
        """
        step_id = "2.3"
        path = write_steering_request(self.ipc_dir, step_id, "hi")
        safe_step_id = re.sub(r"[^A-Za-z0-9_.-]", "-", step_id)
        matches = list(self.ipc_dir.glob(f"steering-{safe_step_id}-*.request.json"))
        self.assertIn(path, matches)


if __name__ == "__main__":
    unittest.main()
