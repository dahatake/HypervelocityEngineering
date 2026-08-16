"""test_settings_azure_persistence.py — FR-GUI-03 Azure 設定の永続化テスト。

検証項目:
  1. GUI が可視化する必須入力キー（`default_params` を持たない `required_params`）が
     設定ストアの既定値に含まれること
  2. `settings_apply` の AZURE セクションが同キーを網羅すること
  3. 既定値を持つキーは永続化対象に残らず、`_OBSOLETE_KEYS` により保存済みの値が
     load 時にファイルから除去されること
  4. 保存 → 復元で値が失われないこと

根拠: hve-dev/requirement-definition.md §6.4 FR-GUI-03
"""

from __future__ import annotations

import configparser
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hve.gui import settings_apply, settings_store
from hve.gui.workflow_step_requirements import gui_visible_required_params
from hve.workflow_registry import get_workflow


_ASDW_STEP_1_3 = get_workflow("asdw-web").get_step("1.3")
AZURE_PERSISTED_PARAMS = gui_visible_required_params(_ASDW_STEP_1_3)
AZURE_OBSOLETE_PARAMS = tuple(
    key
    for key in _ASDW_STEP_1_3.required_params
    if key in _ASDW_STEP_1_3.default_params
)


class TestAzureSettingsKeys(unittest.TestCase):
    """FR-GUI-03: 永続化キーが GUI 可視の必須キーを過不足なく網羅する。"""

    def test_default_settings_contain_every_persisted_param(self) -> None:
        options = settings_store.defaults()["options"]
        for key in AZURE_PERSISTED_PARAMS:
            self.assertIn(key, options, f"{key} が設定ストア既定値に無い")

    def test_azure_section_maps_every_persisted_param(self) -> None:
        azure_map = settings_apply._SECTION_FIELDS["AZURE"]
        for key in AZURE_PERSISTED_PARAMS:
            self.assertIn(key, azure_map, f"{key} が AZURE セクション表に無い")
            self.assertEqual(azure_map[key], key)

    def test_defaults_are_empty_strings(self) -> None:
        """既定値は空文字とし、レジストリ側 default_params と二重管理しない。"""
        options = settings_store.defaults()["options"]
        for key in AZURE_PERSISTED_PARAMS:
            self.assertEqual(options[key], "")

    def test_defaulted_params_are_not_persisted(self) -> None:
        """既定値を持つキーは入力欄が無いため永続化対象に残さない。"""
        self.assertTrue(AZURE_OBSOLETE_PARAMS)
        options = settings_store.defaults()["options"]
        azure_map = settings_apply._SECTION_FIELDS["AZURE"]
        for key in AZURE_OBSOLETE_PARAMS:
            self.assertNotIn(key, options, f"{key} が設定ストア既定値に残っている")
            self.assertNotIn(key, azure_map, f"{key} が AZURE セクション表に残っている")

    def test_defaulted_params_are_registered_as_obsolete(self) -> None:
        obsolete = settings_store._OBSOLETE_KEYS["options"]
        for key in AZURE_OBSOLETE_PARAMS:
            self.assertIn(key, obsolete, f"{key} が廃止キーとして登録されていない")


class TestObsoleteAzureKeyMigration(unittest.TestCase):
    """FR-GUI-03: UI から編集できなくなったキーは load 時にファイルから除去する。"""

    def test_saved_values_are_removed_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".settings.txt"
            body = "\n".join(
                ["[options]"]
                + [f"{key} = value-{key}" for key in AZURE_OBSOLETE_PARAMS]
            )
            path.write_text(body + "\n", encoding="utf-8")
            with mock.patch.object(settings_store, "settings_path", lambda: path):
                loaded = settings_store.load()
            for key in AZURE_OBSOLETE_PARAMS:
                self.assertNotIn(key, loaded["options"])
            cp = configparser.ConfigParser()
            cp.read(path, encoding="utf-8")
            for key in AZURE_OBSOLETE_PARAMS:
                self.assertNotIn(key, cp["options"])


class TestAzureSettingsRoundTrip(unittest.TestCase):
    """FR-GUI-03: 保存 → 復元で値が保持される。"""

    def setUp(self) -> None:
        # OptionsPage は textChanged で設定ストアへ書き込むため、実ファイルを触らせない。
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self._settings_file = Path(tmp.name) / ".settings.txt"
        patcher = mock.patch.object(
            settings_store, "settings_path", lambda: self._settings_file
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_settings_path_is_isolated_from_the_real_store(self) -> None:
        self.assertEqual(settings_store.settings_path(), self._settings_file)

    def test_apply_and_collect_round_trip(self) -> None:
        from PySide6.QtWidgets import QApplication

        from hve.gui.page_options import OptionsPage

        QApplication.instance() or QApplication([])
        page = OptionsPage()
        try:
            sections = {"AZURE": page.c_azure}
            saved = {
                "options": {key: f"value-{key}" for key in AZURE_PERSISTED_PARAMS}
            }
            settings_apply.apply_to_widgets(sections, saved)
            restored = settings_apply.collect_from_widgets(sections)
            for key in AZURE_PERSISTED_PARAMS:
                self.assertEqual(restored.get(key), f"value-{key}")
            for key in AZURE_OBSOLETE_PARAMS:
                self.assertNotIn(key, restored)
        finally:
            page.deleteLater()

    def test_round_trip_survives_store_serialization(self) -> None:
        """configparser 経由の文字列化 → 復元でも値が保持される。"""
        for key in AZURE_PERSISTED_PARAMS:
            serialized = settings_store._to_str(f"value-{key}")
            self.assertEqual(settings_store._coerce(serialized, ""), f"value-{key}")


if __name__ == "__main__":
    unittest.main()
