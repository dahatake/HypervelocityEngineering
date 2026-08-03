"""Contracts for cq configuration and profile resolution (FR-CQ-01 / FR-CQ-03)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cq import config

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_config(root: Path, text: str, name: str = "cq.toml") -> Path:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


MINIMAL = """
[profiles.hve]
roots = ["hve", "mdq"]

[profiles.app]
roots = ["src"]
"""


class TestFailClosed:
    def test_missing_config_is_rejected(self, tmp_path: Path) -> None:
        """既定ルートを推測して索引しない（FR-CQ-01）。"""
        with pytest.raises(config.ConfigError, match="no cq configuration"):
            config.resolve_profiles(tmp_path)

    def test_config_without_profiles_is_rejected(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "[index]\nmax_file_bytes = 10\n")
        with pytest.raises(config.ConfigError, match="profiles"):
            config.resolve_profiles(tmp_path)

    def test_profile_without_roots_is_rejected(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "[profiles.hve]\nroots = []\n")
        with pytest.raises(config.ConfigError, match="roots"):
            config.resolve_profiles(tmp_path)

    def test_unparsable_config_is_rejected(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "this is not toml = = =")
        with pytest.raises(config.ConfigError):
            config.resolve_profiles(tmp_path)

    def test_unknown_profile_lookup_is_rejected(self, tmp_path: Path) -> None:
        _write_config(tmp_path, MINIMAL)
        with pytest.raises(config.ConfigError, match="unknown profile"):
            config.resolve_profile(tmp_path, "nope")


class TestResolution:
    def test_profiles_are_parsed(self, tmp_path: Path) -> None:
        _write_config(tmp_path, MINIMAL)
        profiles = config.resolve_profiles(tmp_path)
        assert set(profiles) == {"hve", "app"}
        assert profiles["hve"].roots == ("hve/", "mdq/")
        assert profiles["app"].roots == ("src/",)

    def test_dot_directory_config_is_also_accepted(self, tmp_path: Path) -> None:
        _write_config(tmp_path, MINIMAL, name=".cq/config.toml")
        assert set(config.resolve_profiles(tmp_path)) == {"hve", "app"}

    def test_root_config_wins_over_dot_directory(self, tmp_path: Path) -> None:
        _write_config(tmp_path, MINIMAL)
        _write_config(tmp_path, "[profiles.other]\nroots = ['x']\n", name=".cq/config.toml")
        assert set(config.resolve_profiles(tmp_path)) == {"hve", "app"}

    def test_builtin_excludes_are_always_present(self, tmp_path: Path) -> None:
        _write_config(tmp_path, MINIMAL)
        profile = config.resolve_profile(tmp_path, "hve")
        assert set(config.BUILTIN_EXCLUDES) <= set(profile.exclude)

    def test_declared_excludes_extend_builtins(self, tmp_path: Path) -> None:
        _write_config(tmp_path, MINIMAL + '\nexclude = ["hve/gui/i18n/**"]\n')
        profile = config.resolve_profile(tmp_path, "app")
        assert "hve/gui/i18n/**" in profile.exclude
        assert set(config.BUILTIN_EXCLUDES) <= set(profile.exclude)

    def test_max_file_bytes_has_a_default_and_is_overridable(self, tmp_path: Path) -> None:
        _write_config(tmp_path, MINIMAL)
        assert config.resolve_profile(tmp_path, "hve").max_file_bytes == config.DEFAULT_MAX_FILE_BYTES
        _write_config(tmp_path, "[index]\nmax_file_bytes = 4096\n" + MINIMAL)
        assert config.resolve_profile(tmp_path, "hve").max_file_bytes == 4096

    def test_roots_are_normalised_to_posix_directory_prefixes(self, tmp_path: Path) -> None:
        _write_config(tmp_path, '[profiles.hve]\nroots = ["hve/", "tools"]\n')
        assert config.resolve_profile(tmp_path, "hve").roots == ("hve/", "tools/")

    def test_absolute_or_escaping_roots_are_rejected(self, tmp_path: Path) -> None:
        for bad in ("/abs", "../up", "a//b", "a\\b"):
            # TOML literal string: バックスラッシュをエスケープとして解釈させない
            _write_config(tmp_path, f"[profiles.hve]\nroots = ['{bad}']\n")
            with pytest.raises(config.ConfigError):
                config.resolve_profile(tmp_path, "hve")


class TestRepositoryConfiguration:
    def test_repository_declares_both_profiles(self) -> None:
        profiles = config.resolve_profiles(REPO_ROOT)
        assert set(profiles) == {"hve", "app"}

    def test_hve_profile_covers_the_hve_application(self) -> None:
        roots = config.resolve_profile(REPO_ROOT, "hve").roots
        assert {"hve/", "mdq/", "cq/"} <= set(roots)

    def test_app_profile_covers_generated_sources_only(self) -> None:
        assert config.resolve_profile(REPO_ROOT, "app").roots == ("src/",)
