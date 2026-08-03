"""test_settings_azure_persistence.py — FR-GUI-03 Azure 設定の永続化テスト。

検証項目:
  1. ASDW-WEB Step 1.3 の `required_params` が設定ストアの既定値に含まれること
  2. `settings_apply` の AZURE セクションが同キーを網羅すること
  3. 保存 → 復元で値が失われないこと

根拠: hve-dev/requirement-definition.md §6.4 FR-GUI-03
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hve.gui import settings_apply, settings_store
from hve.workflow_registry import get_workflow


ASDW_STEP_1_3_PARAMS = tuple(get_workflow("asdw-web").get_step("1.3").required_params)


class TestAzureSettingsKeys(unittest.TestCase):
    """FR-GUI-03: 永続化キーがレジストリ宣言を網羅する。"""

    def test_default_settings_contain_every_required_param(self) -> None:
        options = settings_store.defaults()["options"]
        for key in ASDW_STEP_1_3_PARAMS:
            self.assertIn(key, options, f"{key} が設定ストア既定値に無い")

    def test_azure_section_maps_every_required_param(self) -> None:
        azure_map = settings_apply._SECTION_FIELDS["AZURE"]
        for key in ASDW_STEP_1_3_PARAMS:
            self.assertIn(key, azure_map, f"{key} が AZURE セクション表に無い")
            self.assertEqual(azure_map[key], key)

    def test_defaults_are_empty_strings(self) -> None:
        """既定値は空文字とし、レジストリ側 default_params と二重管理しない。"""
        options = settings_store.defaults()["options"]
        for key in ASDW_STEP_1_3_PARAMS:
            self.assertEqual(options[key], "")


class TestAzureSettingsRoundTrip(unittest.TestCase):
    """FR-GUI-03: 保存 → 復元で値が保持される。"""

    def test_apply_and_collect_round_trip(self) -> None:
        from PySide6.QtWidgets import QApplication

        from hve.gui.page_options import OptionsPage

        QApplication.instance() or QApplication([])
        page = OptionsPage()
        try:
            sections = {"AZURE": page.c_azure}
            saved = {
                "options": {key: f"value-{key}" for key in ASDW_STEP_1_3_PARAMS}
            }
            settings_apply.apply_to_widgets(sections, saved)
            restored = settings_apply.collect_from_widgets(sections)
            for key in ASDW_STEP_1_3_PARAMS:
                self.assertEqual(restored.get(key), f"value-{key}")
        finally:
            page.deleteLater()

    def test_round_trip_survives_store_serialization(self) -> None:
        """configparser 経由の文字列化 → 復元でも値が保持される。"""
        for key in ASDW_STEP_1_3_PARAMS:
            serialized = settings_store._to_str(f"value-{key}")
            self.assertEqual(settings_store._coerce(serialized, ""), f"value-{key}")


if __name__ == "__main__":
    unittest.main()
