"""parse_filter_error.py の単体テスト。旧インライン実装との挙動互換性を保証する。"""

import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "parse_filter_error.py"


def run(stdin_text: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin_text,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout


class TestParseFilterError(unittest.TestCase):
    def test_error_field_present(self):
        rc, out = run('{"error": "catalog ファイルが見つかりません"}')
        self.assertEqual(0, rc)
        self.assertEqual("catalog ファイルが見つかりません", out.strip())

    def test_error_field_absent(self):
        rc, out = run('{"matched_app_ids": ["APP-01"]}')
        self.assertEqual(0, rc)
        self.assertEqual("", out.strip())

    def test_invalid_json(self):
        rc, out = run("not a json")
        self.assertEqual(0, rc)
        self.assertEqual("", out.strip())

    def test_empty_stdin(self):
        rc, out = run("")
        self.assertEqual(0, rc)
        self.assertEqual("", out.strip())
