"""hve.gui.settings_store の往復・既定値テスト。"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hve.gui import settings_store


class TestSettingsStore(unittest.TestCase):
    def test_load_returns_defaults_when_file_missing(self) -> None:
        with TemporaryDirectory() as d:
            with patch.object(settings_store, "_SETTINGS_PATH", Path(d) / ".settings.txt"):
                loaded = settings_store.load()
                self.assertEqual(loaded["options"]["model"], "Auto")
                self.assertEqual(loaded["options"]["max_parallel"], 15)

    def test_save_then_load_roundtrip(self) -> None:
        with TemporaryDirectory() as d:
            p = Path(d) / ".settings.txt"
            with patch.object(settings_store, "_SETTINGS_PATH", p):
                s = settings_store.defaults()
                s["options"]["model"] = "claude-opus-4.7"
                s["options"]["max_parallel"] = 8
                s["options"]["auto_qa"] = True
                s["options"]["timeout"] = 12345.0
                settings_store.save(s)
                self.assertTrue(p.exists())
                loaded = settings_store.load()
                self.assertEqual(loaded["options"]["model"], "claude-opus-4.7")
                self.assertEqual(loaded["options"]["max_parallel"], 8)
                self.assertIs(loaded["options"]["auto_qa"], True)
                self.assertAlmostEqual(loaded["options"]["timeout"], 12345.0)

    def test_corrupt_file_falls_back_to_defaults(self) -> None:
        with TemporaryDirectory() as d:
            p = Path(d) / ".settings.txt"
            p.write_text("[[[broken", encoding="utf-8")
            with patch.object(settings_store, "_SETTINGS_PATH", p):
                loaded = settings_store.load()
                self.assertEqual(loaded["options"]["model"], "Auto")

    def test_theme_default_is_dark(self) -> None:
        d = settings_store.defaults()
        self.assertEqual(d["options"]["theme"], "dark")

    def test_theme_roundtrip(self) -> None:
        with TemporaryDirectory() as d:
            p = Path(d) / ".settings.txt"
            with patch.object(settings_store, "_SETTINGS_PATH", p):
                s = settings_store.defaults()
                s["options"]["theme"] = "light"
                settings_store.save(s)
                loaded = settings_store.load()
                self.assertEqual(loaded["options"]["theme"], "light")


if __name__ == "__main__":
    unittest.main()
