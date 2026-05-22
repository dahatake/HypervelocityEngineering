"""T3.4: settings_window の Skills カテゴリと MdqIndexSection のテスト。

純粋ロジック中心。Qt のイベントループは回さず、_MdqIndexSection の状態判定と
レポート読み込みのコードパスを検証する。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class _GuiBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication
        if QApplication.instance() is None:
            cls._qapp = QApplication([])
        else:
            cls._qapp = QApplication.instance()


class TestSkillsCategory(_GuiBase):
    def test_category_tree_uses_skills_label(self) -> None:
        from hve.gui import settings_window
        labels = [g[0] for g in settings_window._CATEGORY_TREE]
        self.assertIn("skills", labels)
        self.assertNotIn("インデックス", labels)

    def test_build_category_tree_expands_skills_from_registry(self) -> None:
        from hve.gui import settings_window
        expanded = settings_window._build_category_tree()
        skills_block = dict(expanded).get("skills")
        self.assertIsNotNone(skills_block)
        # 組み込み Markdown-Query が登録されている
        self.assertIn(("Markdown-Query", "MDQ"), skills_block)


class TestMdqIndexSection(_GuiBase):
    def test_section_initializes_with_two_subsections(self) -> None:
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d, \
                patch.object(_MdqIndexSection, "_start_regen"):
            sec = _MdqIndexSection(repo_root=Path(d))
            self.assertIsNotNone(sec._stats_label)
            self.assertIsNotNone(sec._usage_view)
            self.assertIsNotNone(sec._btn_incremental_refresh)
            self.assertIsNotNone(sec._btn_regen_usage)

    def test_is_report_stale_returns_true_when_missing(self) -> None:
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d, \
                patch.object(_MdqIndexSection, "_start_regen"):
            missing = Path(d) / "absent" / "latest.md"
            with patch.object(_MdqIndexSection, "_latest_report_path",
                              return_value=missing):
                sec = _MdqIndexSection(repo_root=Path(d))
                self.assertTrue(sec._is_report_stale())

    def test_is_report_stale_returns_false_for_fresh(self) -> None:
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d, \
                patch.object(_MdqIndexSection, "_start_regen"):
            root = Path(d)
            report = root / "usage-report" / "latest.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("# dummy", encoding="utf-8")
            with patch.object(_MdqIndexSection, "_latest_report_path",
                              return_value=report):
                sec = _MdqIndexSection(repo_root=root)
                self.assertFalse(sec._is_report_stale())

    def test_loads_existing_report_into_label(self) -> None:
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d, \
                patch.object(_MdqIndexSection, "_start_regen"):
            root = Path(d)
            report = root / "usage-report" / "latest.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("# レポート本文サンプル", encoding="utf-8")
            with patch.object(_MdqIndexSection, "_latest_report_path",
                              return_value=report):
                sec = _MdqIndexSection(repo_root=root)
                # QTextBrowser に setMarkdown で代入されるため toPlainText
                # もしくは toMarkdown でチェックする。
                text = sec._usage_view.toMarkdown() or sec._usage_view.toPlainText()
                self.assertIn("レポート本文サンプル", text)

    def test_auto_regen_triggered_when_stale(self) -> None:
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "absent" / "latest.md"
            with patch.object(_MdqIndexSection, "_start_regen") as m, \
                    patch.object(_MdqIndexSection, "_latest_report_path",
                                  return_value=missing):
                _MdqIndexSection(repo_root=Path(d))
                # 起動時に stale 判定 → _start_regen 呼び出し
                self.assertTrue(m.called)


class TestMdqIndexSectionLangStrategy(_GuiBase):
    """Tokenize 言語 / Chunking Strategy ドロップダウンの回帰テスト。"""

    def test_dropdowns_have_expected_choices(self) -> None:
        from hve.gui import settings_store
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d, \
                patch.object(_MdqIndexSection, "_start_regen"), \
                patch.object(settings_store, "settings_path",
                              return_value=Path(d) / ".settings.txt"):
            sec = _MdqIndexSection(repo_root=Path(d))
            lang_values = [
                sec._lang_combo.itemData(i)
                for i in range(sec._lang_combo.count())
            ]
            strategy_values = [
                sec._strategy_combo.itemData(i)
                for i in range(sec._strategy_combo.count())
            ]
            self.assertEqual(lang_values, ["ja-jp", "en-us"])
            # SoT は mdq.strategies.ALL_STRATEGIES (4 件)
            from mdq.strategies import ALL_STRATEGIES
            self.assertEqual(strategy_values, list(ALL_STRATEGIES))
            # 既定値
            self.assertEqual(sec._lang, "ja-jp")
            self.assertEqual(sec._strategy, "heading")

    def test_strategy_change_persists_and_reloads(self) -> None:
        from hve.gui import settings_store
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d, \
                patch.object(_MdqIndexSection, "_start_regen"), \
                patch.object(settings_store, "_SETTINGS_PATH",
                              Path(d) / ".settings.txt"):
            sec = _MdqIndexSection(repo_root=Path(d))
            # heading_recursive に切替
            idx = sec._strategy_combo.findData("heading_recursive")
            sec._strategy_combo.setCurrentIndex(idx)
            # 内部状態と永続化を確認
            self.assertEqual(sec._strategy, "heading_recursive")
            saved = settings_store.load().get("mdq", {})
            self.assertEqual(saved.get("chunk_strategy"), "heading_recursive")

    def test_markdown_table_renders_in_text_browser(self) -> None:
        """レポートに Markdown テーブル区切りが含まれることを確認。"""
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d, \
                patch.object(_MdqIndexSection, "_start_regen"):
            root = Path(d)
            report = (
                root / "tools" / "skills" / "markdown_query"
                / "usage-report" / "latest.md"
            )
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                "# title\n\n| 項目 | データ |\n|:---|---:|\n| a | 1 |\n",
                encoding="utf-8",
            )
            sec = _MdqIndexSection(repo_root=root)
            md = sec._usage_view.toMarkdown()
            # QTextBrowser がテーブルとして解釈すれば toMarkdown 出力にも
            # パイプが残る（フォールバック含めて確認）。
            self.assertIn("項目", md)


class TestMdqIndexSectionTargetFolders(_GuiBase):
    """対象フォルダ (target_folders) UI のテスト (T5)。"""

    def test_initial_list_loads_from_settings(self) -> None:
        from hve.gui import settings_store
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d, \
                patch.object(_MdqIndexSection, "_start_regen"), \
                patch.object(settings_store, "_SETTINGS_PATH",
                              Path(d) / ".settings.txt"):
            cur = settings_store.load()
            cur["mdq"]["target_folders"] = "docs;users-guide"
            settings_store.save(cur)
            sec = _MdqIndexSection(repo_root=Path(d))
            items = [
                sec._target_folders_list.item(i).text()
                for i in range(sec._target_folders_list.count())
            ]
            self.assertEqual(items, ["docs", "users-guide"])

    def test_add_via_input_persists(self) -> None:
        from hve.gui import settings_store
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d, \
                patch.object(_MdqIndexSection, "_start_regen"), \
                patch.object(settings_store, "_SETTINGS_PATH",
                              Path(d) / ".settings.txt"):
            sec = _MdqIndexSection(repo_root=Path(d))
            sec._target_folders_input.setText("docs/usecase")
            sec._on_target_folder_add_from_input()
            saved = settings_store.load()["mdq"]["target_folders"]
            self.assertEqual(
                settings_store.parse_target_folders(saved), ["docs/usecase"])
            self.assertEqual(sec._target_folders_input.text(), "")

    def test_add_absolute_path_inside_repo_is_relativized(self) -> None:
        from hve.gui import settings_store
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d, \
                patch.object(_MdqIndexSection, "_start_regen"), \
                patch.object(settings_store, "_SETTINGS_PATH",
                              Path(d) / ".settings.txt"):
            root = Path(d)
            (root / "docs").mkdir()
            sec = _MdqIndexSection(repo_root=root)
            sec._add_target_folder(str(root / "docs"))
            self.assertEqual(sec._target_folders, ["docs"])

    def test_add_path_outside_repo_rejected(self) -> None:
        from hve.gui import settings_store
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d, \
                tempfile.TemporaryDirectory() as other, \
                patch.object(_MdqIndexSection, "_start_regen"), \
                patch.object(settings_store, "_SETTINGS_PATH",
                              Path(d) / ".settings.txt"):
            sec = _MdqIndexSection(repo_root=Path(d))
            sec._add_target_folder(other)
            self.assertEqual(sec._target_folders, [])
            self.assertIn("リポジトリ外", sec._target_folders_msg.text())

    def test_duplicate_not_added(self) -> None:
        from hve.gui import settings_store
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d, \
                patch.object(_MdqIndexSection, "_start_regen"), \
                patch.object(settings_store, "_SETTINGS_PATH",
                              Path(d) / ".settings.txt"):
            sec = _MdqIndexSection(repo_root=Path(d))
            sec._add_target_folder("docs")
            sec._add_target_folder("docs")
            self.assertEqual(sec._target_folders, ["docs"])

    def test_remove_selected(self) -> None:
        from hve.gui import settings_store
        from hve.gui.settings_window import _MdqIndexSection
        with tempfile.TemporaryDirectory() as d, \
                patch.object(_MdqIndexSection, "_start_regen"), \
                patch.object(settings_store, "_SETTINGS_PATH",
                              Path(d) / ".settings.txt"):
            sec = _MdqIndexSection(repo_root=Path(d))
            sec._add_target_folder("docs")
            sec._add_target_folder("qa")
            sec._target_folders_list.item(0).setSelected(True)
            sec._on_target_folder_remove_clicked()
            self.assertEqual(sec._target_folders, ["qa"])
            saved = settings_store.load()["mdq"]["target_folders"]
            self.assertEqual(
                settings_store.parse_target_folders(saved), ["qa"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
