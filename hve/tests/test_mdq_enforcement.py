"""Tests for hve.mdq_enforcement and settings_store target_folders helpers."""
from __future__ import annotations

import pytest

from hve import mdq_enforcement
from hve.gui import settings_store


class TestParseTargetFolders:
    def test_empty(self) -> None:
        assert settings_store.parse_target_folders("") == []
        assert settings_store.parse_target_folders(";;;") == []

    def test_basic(self) -> None:
        assert settings_store.parse_target_folders("docs;users-guide") == [
            "docs",
            "users-guide",
        ]

    def test_dedup_and_normalize(self) -> None:
        result = settings_store.parse_target_folders(
            "docs/;docs;docs\\sub;users-guide/;"
        )
        assert result == ["docs", "docs/sub", "users-guide"]

    def test_strip_quotes_and_whitespace(self) -> None:
        result = settings_store.parse_target_folders(' "docs" ; \'users-guide\' ')
        assert result == ["docs", "users-guide"]

    def test_dot_excluded(self) -> None:
        assert settings_store.parse_target_folders(".;./;docs") == ["docs"]


class TestSerializeTargetFolders:
    def test_roundtrip(self) -> None:
        original = ["docs", "users-guide", "qa"]
        s = settings_store.serialize_target_folders(original)
        assert settings_store.parse_target_folders(s) == original

    def test_dedup(self) -> None:
        s = settings_store.serialize_target_folders(["docs", "docs", "qa"])
        assert s == "docs;qa"


class TestSaveLoadIntegration:
    def test_target_folders_persisted(self, tmp_path, monkeypatch) -> None:
        fake = tmp_path / ".settings.txt"
        monkeypatch.setattr(settings_store, "settings_path", lambda: fake)
        cur = settings_store.load()
        cur["mdq"]["target_folders"] = settings_store.serialize_target_folders(
            ["docs", "users-guide"]
        )
        settings_store.save(cur)
        reloaded = settings_store.load()
        assert (
            settings_store.parse_target_folders(reloaded["mdq"]["target_folders"])
            == ["docs", "users-guide"]
        )
        assert settings_store.get_mdq_target_folders(settings=reloaded) == [
            "docs",
            "users-guide",
        ]

    def test_default_empty(self, tmp_path, monkeypatch) -> None:
        fake = tmp_path / ".settings.txt"
        monkeypatch.setattr(settings_store, "settings_path", lambda: fake)
        assert settings_store.get_mdq_target_folders() == []


class TestBuildEnforcementPrompt:
    def test_empty_returns_none(self) -> None:
        assert mdq_enforcement.build_enforcement_prompt([]) is None
        assert mdq_enforcement.build_enforcement_prompt(None) is None  # type: ignore[arg-type]
        assert mdq_enforcement.build_enforcement_prompt(["", "  "]) is None

    def test_non_empty_returns_block(self) -> None:
        block = mdq_enforcement.build_enforcement_prompt(["docs", "users-guide"])
        assert block is not None
        assert "python -m mdq search" in block
        assert "`docs`" in block
        assert "`users-guide`" in block
        # 強制トーンであることを確認
        assert "必ず" in block


class TestRunnerInjection:
    def test_combines_when_configured(self, tmp_path, monkeypatch) -> None:
        from hve import runner as runner_module

        fake = tmp_path / ".settings.txt"
        monkeypatch.setattr(settings_store, "settings_path", lambda: fake)
        cur = settings_store.load()
        cur["mdq"]["target_folders"] = "docs;qa"
        settings_store.save(cur)

        out = runner_module._combine_additional_prompt_with_mdq("base prompt")
        assert out is not None
        assert "python -m mdq search" in out
        assert out.endswith("base prompt")

    def test_passes_through_when_empty(self, tmp_path, monkeypatch) -> None:
        from hve import runner as runner_module

        fake = tmp_path / ".settings.txt"
        monkeypatch.setattr(settings_store, "settings_path", lambda: fake)
        # 空設定: ファイル無し → get_mdq_target_folders == []
        assert runner_module._combine_additional_prompt_with_mdq("base") == "base"
        assert runner_module._combine_additional_prompt_with_mdq(None) is None
        assert runner_module._combine_additional_prompt_with_mdq("") in (None, "")
