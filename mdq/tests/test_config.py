"""Tests for mdq.config."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mdq import config as cfg


def test_resolve_roots_defaults_when_no_config(tmp_path: Path) -> None:
    assert cfg.resolve_roots(tmp_path) == cfg.GENERIC_DEFAULT_ROOTS


def test_resolve_roots_cli_overrides_config(tmp_path: Path) -> None:
    (tmp_path / "mdq.toml").write_text(
        '[index]\nroots = ["docs", "knowledge"]\n', encoding="utf-8"
    )
    assert cfg.resolve_roots(tmp_path, cli_roots=["custom"]) == ["custom"]


def test_resolve_roots_reads_mdq_toml(tmp_path: Path) -> None:
    (tmp_path / "mdq.toml").write_text(
        '[index]\nroots = ["docs", "knowledge", "qa"]\n', encoding="utf-8"
    )
    assert cfg.resolve_roots(tmp_path) == ["docs", "knowledge", "qa"]


def test_resolve_roots_reads_dot_mdq_config_toml(tmp_path: Path) -> None:
    sub = tmp_path / ".mdq"
    sub.mkdir()
    (sub / "config.toml").write_text(
        '[index]\nroots = ["a", "b"]\n', encoding="utf-8"
    )
    assert cfg.resolve_roots(tmp_path) == ["a", "b"]


def test_mdq_toml_takes_precedence_over_dot_mdq(tmp_path: Path) -> None:
    (tmp_path / "mdq.toml").write_text(
        '[index]\nroots = ["root-top"]\n', encoding="utf-8"
    )
    sub = tmp_path / ".mdq"
    sub.mkdir()
    (sub / "config.toml").write_text(
        '[index]\nroots = ["root-dot"]\n', encoding="utf-8"
    )
    assert cfg.resolve_roots(tmp_path) == ["root-top"]


def test_empty_roots_falls_back_to_default(tmp_path: Path) -> None:
    (tmp_path / "mdq.toml").write_text(
        "[index]\nroots = []\n", encoding="utf-8"
    )
    assert cfg.resolve_roots(tmp_path) == cfg.GENERIC_DEFAULT_ROOTS
