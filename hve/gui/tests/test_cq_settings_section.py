"""FR-GUI-04: GUI 設定画面の Code-Query セクションの契約。

RED 先行。実装 (`hve/gui/cq_settings_section.py`) は Sub-006 で追加する。

検証観点:
  (a) 3 タブ構成（基本 / インデックス管理 / 検索品質）
  (b) `settings_apply` が参照する `cq_watch` / `cq_watch_debounce_ms` の公開
  (c) profile コンボが `cq` の設定ファイル由来であること
  (d) 設定不在時に索引操作を無効化し、設定ファイル候補を表示すること
  (e) debounce の既定値表示が `cq.watcher.DEFAULT_DEBOUNCE_MS` から導出されること
      （Sub-001 敵対的レビュー指摘 No.3: 既定値の二重管理禁止）
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from cq.config import CONFIG_FILENAMES  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def patched_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from hve.gui import settings_store

    fake = tmp_path / ".settings.txt"
    monkeypatch.setattr(settings_store, "settings_path", lambda: fake)
    return fake


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[profiles.main]\nroots = ['pkg']\n\n[profiles.extra]\nroots = ['other']\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "b.py").write_text("class Beta:\n    pass\n", encoding="utf-8")
    return tmp_path


def _make_section(repo_root: Path):
    from hve.gui.cq_settings_section import CqIndexSection

    return CqIndexSection(repo_root=repo_root)


@pytest.fixture()
def indexed_repo(repo: Path) -> Path:
    """JavaScript と C# はどちらも `tree-sitter` パーサなので、パーサ別表示では区別できない。"""
    from cq import config, indexer, store

    (repo / "pkg" / "c.js").write_text(
        "function gamma() {\n    return 3;\n}\n", encoding="utf-8"
    )
    (repo / "pkg" / "d.cs").write_text(
        "class Delta\n{\n    void Run()\n    {\n    }\n}\n", encoding="utf-8"
    )
    profile = config.resolve_profile(repo, "main")
    indexer.build_index(
        repo, profile, db_path=repo / store.db_path_for("main")
    )
    return repo


class TestLayout:
    def test_section_has_three_tabs(self, qapp, repo: Path, patched_settings: Path) -> None:
        section = _make_section(repo)

        labels = [section._tabs.tabText(i) for i in range(section._tabs.count())]
        assert labels == ["基本", "インデックス管理", "検索品質"]

    def test_watch_widgets_are_exposed_for_settings_apply(
        self, qapp, repo: Path, patched_settings: Path
    ) -> None:
        section = _make_section(repo)

        assert hasattr(section, "cq_watch")
        assert hasattr(section, "cq_watch_debounce_ms")
        assert section.cq_watch_debounce_ms.minimum() == 0

    def test_debounce_default_hint_is_derived_from_cq(
        self, qapp, repo: Path, patched_settings: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """既定 debounce 値を GUI 側へ literal で二重管理しないこと。"""
        from cq import watcher as cq_watcher

        monkeypatch.setattr(cq_watcher, "DEFAULT_DEBOUNCE_MS", 1234)
        section = _make_section(repo)

        assert "1234" in section.cq_watch_debounce_ms.specialValueText()


class TestProfileSource:
    def test_profile_combo_matches_the_config_file(
        self, qapp, repo: Path, patched_settings: Path
    ) -> None:
        section = _make_section(repo)

        combo = section._profile_combo
        actual = [combo.itemData(i) for i in range(combo.count())]
        # cq.toml の宣言順（main → extra）をそのまま提示する。
        assert actual == ["main", "extra"]

    def test_roots_and_excludes_are_read_only(
        self, qapp, repo: Path, patched_settings: Path
    ) -> None:
        section = _make_section(repo)

        assert section._roots_view.isReadOnly()
        assert section._excludes_view.isReadOnly()

    def test_selected_profile_is_persisted(
        self, qapp, repo: Path, patched_settings: Path
    ) -> None:
        from hve.gui import settings_store

        section = _make_section(repo)
        assert section.current_profile() == "main"

        combo = section._profile_combo
        combo.setCurrentIndex(combo.findData("extra"))

        assert section.current_profile() == "extra"
        assert settings_store.load()["cq"]["profile"] == "extra"
        assert "other/" in section._roots_view.toPlainText()

    def test_unknown_saved_profile_falls_back_to_the_first_declared_one(
        self, qapp, repo: Path, patched_settings: Path
    ) -> None:
        """設定ファイル側で profile が改名・削除されても操作不能にならないこと。"""
        from hve.gui import settings_store

        saved = settings_store.defaults()
        saved["cq"]["profile"] = "gone"
        settings_store.save(saved)

        section = _make_section(repo)

        assert section.current_profile() == "main"
        assert section._profile_combo.currentData() == "main"

    def test_empty_saved_profile_falls_back_to_the_first_declared_one(
        self, qapp, repo: Path, patched_settings: Path
    ) -> None:
        section = _make_section(repo)

        assert section.current_profile() == "main"


class TestBulkBuildSelection:
    def test_unchecking_every_profile_builds_nothing(
        self, qapp, repo: Path, patched_settings: Path
    ) -> None:
        """全て外した状態で「全 profile ビルド」へ暗黙復帰しないこと。"""
        from PySide6.QtCore import Qt

        section = _make_section(repo)
        listing = section._build_profiles_list
        for i in range(listing.count()):
            listing.item(i).setCheckState(Qt.CheckState.Unchecked)

        section._on_bulk_build_clicked()

        assert section._build_thread is None
        assert section._bulk_total == 0
        assert "選択されていません" in section._bulk_message.text()

    def test_checked_state_is_persisted(
        self, qapp, repo: Path, patched_settings: Path
    ) -> None:
        from PySide6.QtCore import Qt

        from hve.gui import settings_store

        section = _make_section(repo)
        listing = section._build_profiles_list
        listing.item(listing.count() - 1).setCheckState(Qt.CheckState.Unchecked)

        assert settings_store.load()["cq"]["build_profiles"] == "main"


class TestSettingsWindowWiring:
    """設定画面の skills カテゴリへ登録され、autosave 経路に乗ること。"""

    def test_section_is_registered_in_the_skills_registry(self) -> None:
        from hve.gui import settings_window  # noqa: F401 - import で登録される
        from hve.gui import skill_sections

        entry = skill_sections.get_registry().get("CQ")

        assert entry is not None
        assert entry.label == "Code-Query"

    def test_registered_factory_builds_the_section(
        self, qapp, repo: Path, patched_settings: Path
    ) -> None:
        from hve.gui import settings_window  # noqa: F401
        from hve.gui import skill_sections
        from hve.gui.cq_settings_section import CqIndexSection

        entry = skill_sections.get_registry().get("CQ")
        assert entry is not None
        widget = entry.section_factory(repo, None)

        assert isinstance(widget, CqIndexSection)

    def test_settings_apply_maps_only_the_watch_widgets(self) -> None:
        from hve.gui.settings_apply import _SECTION_FIELDS

        assert _SECTION_FIELDS["CQ"] == {
            "cq_watch": "cq_watch",
            "cq_watch_debounce_ms": "cq_watch_debounce_ms",
        }

    def test_watch_values_round_trip_through_settings_apply(
        self, qapp, repo: Path, patched_settings: Path
    ) -> None:
        from hve.gui import settings_apply

        section = _make_section(repo)
        sections = {"CQ": section}

        settings_apply.apply_to_widgets(
            sections, {"options": {"cq_watch": "off", "cq_watch_debounce_ms": 750}}
        )
        collected = settings_apply.collect_from_widgets(sections)

        assert collected["cq_watch"] == "off"
        assert collected["cq_watch_debounce_ms"] == 750


class TestFailClosedWithoutConfig:
    def test_operations_are_disabled_and_candidates_are_shown(
        self, qapp, tmp_path: Path, patched_settings: Path
    ) -> None:
        section = _make_section(tmp_path)

        assert section.is_config_available() is False
        assert section._profile_combo.count() == 0
        for button in (
            section._btn_incremental_refresh,
            section._btn_force_rebuild,
            section._btn_delete_db,
            section._btn_bulk_build,
        ):
            assert button.isEnabled() is False

        banner = section._config_banner.text()
        assert banner
        for rel in CONFIG_FILENAMES:
            assert rel.as_posix() in banner

    def test_constructing_without_config_does_not_raise_or_create_files(
        self, qapp, tmp_path: Path, patched_settings: Path
    ) -> None:
        _make_section(tmp_path)

        assert not (tmp_path / ".cq").exists()


class TestLanguageStats:
    """FR-CQ-15 / FR-GUI-04: パーサ別集計だけを表示しないこと。"""

    @staticmethod
    def _rows(section) -> dict[str, tuple[str, ...]]:
        table = section._language_stats_table
        return {
            table.item(row, 0).text(): tuple(
                table.item(row, column).text()
                for column in range(1, table.columnCount())
            )
            for row in range(table.rowCount())
        }

    def test_table_exposes_the_language_columns(
        self, qapp, indexed_repo: Path, patched_settings: Path
    ) -> None:
        section = _make_section(indexed_repo)

        table = section._language_stats_table
        headers = [
            table.horizontalHeaderItem(column).text()
            for column in range(table.columnCount())
        ]
        assert headers == ["言語", "Files", "Symbols", "Chunks", "パーサ内訳"]

    def test_lists_every_indexed_language(
        self, qapp, indexed_repo: Path, patched_settings: Path
    ) -> None:
        section = _make_section(indexed_repo)

        assert set(self._rows(section)) == {"python", "javascript", "csharp"}

    def test_languages_sharing_a_parser_stay_separate(
        self, qapp, indexed_repo: Path, patched_settings: Path
    ) -> None:
        section = _make_section(indexed_repo)

        rows = self._rows(section)
        assert rows["javascript"][0] == "1"
        assert rows["csharp"][0] == "1"
        assert "tree-sitter" in rows["javascript"][-1]
        assert "tree-sitter" in rows["csharp"][-1]

    def test_missing_index_leaves_the_table_empty_without_creating_files(
        self, qapp, repo: Path, patched_settings: Path
    ) -> None:
        section = _make_section(repo)

        assert section._language_stats_table.rowCount() == 0
        assert not (repo / ".cq").exists()
