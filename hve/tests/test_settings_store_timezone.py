"""`run_id_timezone` 設定のラウンドトリップと既定値テスト。"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hve.gui import settings_store


class TestRunIdTimezoneSetting(unittest.TestCase):
    def test_default_is_asia_tokyo(self) -> None:
        d = settings_store.defaults()
        self.assertEqual(d["options"]["run_id_timezone"], "Asia/Tokyo")

    def test_roundtrip(self) -> None:
        with TemporaryDirectory() as d:
            p = Path(d) / ".settings.txt"
            with patch.object(settings_store, "_SETTINGS_PATH", p):
                s = settings_store.defaults()
                s["options"]["run_id_timezone"] = "America/New_York"
                settings_store.save(s)
                loaded = settings_store.load()
                self.assertEqual(
                    loaded["options"]["run_id_timezone"], "America/New_York"
                )

    def test_load_when_file_missing_returns_default(self) -> None:
        with TemporaryDirectory() as d:
            with patch.object(
                settings_store, "_SETTINGS_PATH", Path(d) / ".settings.txt"
            ):
                loaded = settings_store.load()
                self.assertEqual(
                    loaded["options"]["run_id_timezone"], "Asia/Tokyo"
                )


if __name__ == "__main__":
    unittest.main()
