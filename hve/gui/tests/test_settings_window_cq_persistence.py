"""FR-GUI-04: `[options]` の自動保存が `[cq]` セクションを消さないことの契約。

RED 先行。`settings_store.defaults()` への `[cq]` 追加は Sub-004 で行う。

`SettingsWindow._on_widget_changed()` は保存直前に `settings_store.load()` で
最新値を読み直してから `options` だけをマージする。`CqIndexSection` は
`[cq]` を別経路で直接書き込むため、両経路が競合しても値が失われないことを
`[mdq]` 版 (`test_settings_window_mdq_persistence.py`) と同じ 3 シナリオで確認する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from hve.gui import settings_store


@pytest.fixture
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_path = tmp_path / ".settings.txt"
    monkeypatch.setattr(settings_store, "settings_path", lambda: fake_path)
    return fake_path


def _simulate_on_widget_changed(
    snapshot: Dict[str, Dict[str, Any]],
    new_options: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """`SettingsWindow._on_widget_changed()` の保存ロジックを再現する。"""
    latest = settings_store.load()
    snapshot.clear()
    snapshot.update(latest)
    snapshot.setdefault("options", {}).update(new_options)
    settings_store.save(snapshot)
    return snapshot


class TestCqSectionDefaults:
    def test_cq_section_exists_with_expected_keys(self, tmp_settings: Path) -> None:
        cq_defaults = settings_store.defaults()["cq"]

        # 特定の profile 名を GUI 側の既定値として持たない（他リポジトリでは存在しない）。
        assert cq_defaults["profile"] == ""
        assert cq_defaults["build_profiles"] == ""
        assert set(cq_defaults) == {"profile", "build_profiles"}

    def test_watch_keys_live_in_the_options_section(self, tmp_settings: Path) -> None:
        """`settings_apply._SECTION_FIELDS` は `[options]` だけを読み書きする。"""
        options = settings_store.defaults()["options"]

        assert options["cq_watch"] == ""
        assert options["cq_watch_debounce_ms"] == 0


class TestCqSectionPersistence:
    def test_concurrent_cq_update_is_preserved_after_options_change(
        self, tmp_settings: Path
    ) -> None:
        initial = settings_store.defaults()
        initial["cq"]["profile"] = "hve"
        settings_store.save(initial)
        snapshot = settings_store.load()
        assert snapshot["cq"]["profile"] == "hve"

        cur = settings_store.load()
        cur["cq"]["profile"] = "app"
        cur["cq"]["build_profiles"] = "hve;app"
        settings_store.save(cur)

        _simulate_on_widget_changed(snapshot, {"cq_watch": "off"})

        result = settings_store.load()
        assert result["cq"]["profile"] == "app"
        assert result["cq"]["build_profiles"] == "hve;app"
        assert result["options"]["cq_watch"] == "off"

    def test_reverse_order_options_then_cq(self, tmp_settings: Path) -> None:
        settings_store.save(settings_store.defaults())
        snapshot = settings_store.load()

        _simulate_on_widget_changed(snapshot, {"cq_watch_debounce_ms": 900})

        cur = settings_store.load()
        cur["cq"]["build_profiles"] = "app"
        settings_store.save(cur)

        result = settings_store.load()
        assert result["cq"]["build_profiles"] == "app"
        assert result["options"]["cq_watch_debounce_ms"] == 900

    def test_options_change_does_not_clobber_existing_cq_on_disk(
        self, tmp_settings: Path
    ) -> None:
        initial = settings_store.defaults()
        initial["cq"]["build_profiles"] = "hve"
        settings_store.save(initial)

        snapshot = settings_store.load()
        assert snapshot["cq"]["build_profiles"] == "hve"

        cur = settings_store.load()
        cur["cq"]["build_profiles"] = "hve;app"
        settings_store.save(cur)

        _simulate_on_widget_changed(snapshot, {"verbose": True})

        result = settings_store.load()
        assert result["cq"]["build_profiles"] == "hve;app"
        assert result["options"]["verbose"] is True

    def test_mdq_and_cq_sections_survive_each_other(self, tmp_settings: Path) -> None:
        """`[mdq]` と `[cq]` が相互に消去されないこと（FR-GUI-04）。"""
        initial = settings_store.defaults()
        initial["mdq"]["target_folders"] = "docs/usecase"
        initial["cq"]["build_profiles"] = "hve"
        settings_store.save(initial)

        snapshot = settings_store.load()
        _simulate_on_widget_changed(snapshot, {"verbose": True})

        result = settings_store.load()
        assert result["mdq"]["target_folders"] == "docs/usecase"
        assert result["cq"]["build_profiles"] == "hve"


class TestSemicolonListHelpers:
    """`;` 区切りリストの分解・整形は単一実装であること（FR-MAINT-07）。"""

    def test_parse_and_serialize_roundtrip(self, tmp_settings: Path) -> None:
        parsed = settings_store.parse_semicolon_list(" hve ; app ; hve ; ")

        assert parsed == ["hve", "app"]
        assert settings_store.serialize_semicolon_list(parsed) == "hve;app"

    def test_empty_value_yields_an_empty_list(self, tmp_settings: Path) -> None:
        assert settings_store.parse_semicolon_list("") == []
        assert settings_store.serialize_semicolon_list([]) == ""

    def test_target_folders_still_normalise_paths(self, tmp_settings: Path) -> None:
        """既存の path 正規化つき解析が汎用ヘルパへ寄せても壊れないこと。"""
        assert settings_store.parse_target_folders(
            r'docs\usecase; "docs/agent/" ; . ; docs/usecase'
        ) == ["docs/usecase", "docs/agent"]
        assert settings_store.serialize_target_folders(
            ["docs/usecase", "docs/usecase", "docs/agent/"]
        ) == "docs/usecase;docs/agent"
