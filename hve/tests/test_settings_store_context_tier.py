"""context_tier 設定の既定値・ラウンドトリップ・セクションマッピングテスト。"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hve.gui import settings_store
from hve.gui.settings_apply import _SECTION_FIELDS


class TestContextTierSetting(unittest.TestCase):
    def test_default_is_long_context(self) -> None:
        d = settings_store.defaults()
        self.assertEqual(d["options"]["context_tier"], "long_context")

    def test_roundtrip(self) -> None:
        with TemporaryDirectory() as d:
            p = Path(d) / ".settings.txt"
            with patch.object(settings_store, "_SETTINGS_PATH", p):
                s = settings_store.defaults()
                s["options"]["context_tier"] = "default"
                settings_store.save(s)
                loaded = settings_store.load()
                self.assertEqual(loaded["options"]["context_tier"], "default")

    def test_load_when_file_missing_returns_default(self) -> None:
        with TemporaryDirectory() as d:
            with patch.object(
                settings_store, "_SETTINGS_PATH", Path(d) / ".settings.txt"
            ):
                loaded = settings_store.load()
                self.assertEqual(loaded["options"]["context_tier"], "long_context")

    def test_section_fields_maps_context_tier(self) -> None:
        """C1 セクションが options キー context_tier をウィジェット属性 context_tier に対応付ける。"""
        self.assertEqual(_SECTION_FIELDS["C1"].get("context_tier"), "context_tier")


if __name__ == "__main__":
    unittest.main()
