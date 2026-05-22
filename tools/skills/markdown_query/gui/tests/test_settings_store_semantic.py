"""Tests for semantic_paragraph settings_store helpers (Phase 0 / T01)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.skills.markdown_query.gui import settings_store


def _seed(tmp_path: Path, mdq_overrides: dict) -> dict:
    """Build a settings dict with the given [mdq] overrides applied to defaults."""
    base = {"mdq": dict(settings_store.defaults())}
    base["mdq"].update(mdq_overrides)
    return base


def test_defaults_contains_semantic_keys(tmp_path: Path):
    d = settings_store.defaults()
    for key in (
        "semantic_max_chunk_chars",
        "semantic_min_chars",
        "semantic_breakpoint_percentile_lo",
        "semantic_breakpoint_percentile_hi",
        "semantic_embed_provider",
        "semantic_embed_model",
        "semantic_contextualize",
        "semantic_late_chunking",
        "semantic_fusion_alpha",
        "semantic_bge_m3_warning_dismissed",
    ):
        assert key in d, f"defaults() must contain {key}"


def test_runtime_config_drops_zero_values(tmp_path: Path):
    s = _seed(tmp_path, {
        "semantic_max_chunk_chars": 0,
        "semantic_min_chars": 0,
        "semantic_breakpoint_percentile_lo": 0.0,
        "semantic_breakpoint_percentile_hi": 0.0,
        "semantic_embed_provider": "",
        "semantic_embed_model": "",
    })
    cfg = settings_store.get_semantic_runtime_config(tmp_path, settings=s)
    # Zero / empty values must be omitted so SEMANTIC_* defaults kick in.
    for k in (
        "max_chars", "min_chars", "percentile_lo", "percentile_hi",
        "embed_provider", "embed_model",
    ):
        assert k not in cfg
    # Bools are always present.
    assert cfg["contextualize"] is True
    assert cfg["late_chunking"] is False


def test_runtime_config_passes_through_explicit_values(tmp_path: Path):
    s = _seed(tmp_path, {
        "semantic_max_chunk_chars": 1500,
        "semantic_min_chars": 250,
        "semantic_breakpoint_percentile_lo": 55.0,
        "semantic_breakpoint_percentile_hi": 90.0,
        "semantic_embed_provider": "fastembed",
        "semantic_embed_model": "BAAI/bge-small-en-v1.5",
        "semantic_contextualize": False,
        "semantic_late_chunking": True,
    })
    cfg = settings_store.get_semantic_runtime_config(tmp_path, settings=s)
    assert cfg["max_chars"] == 1500
    assert cfg["min_chars"] == 250
    assert cfg["percentile_lo"] == 55.0
    assert cfg["percentile_hi"] == 90.0
    assert cfg["embed_provider"] == "fastembed"
    assert cfg["embed_model"] == "BAAI/bge-small-en-v1.5"
    assert cfg["contextualize"] is False
    assert cfg["late_chunking"] is True


def test_fusion_alpha_valid_range(tmp_path: Path):
    s = _seed(tmp_path, {"semantic_fusion_alpha": 0.3})
    assert settings_store.get_semantic_fusion_alpha(tmp_path, settings=s) == 0.3
    s = _seed(tmp_path, {"semantic_fusion_alpha": 0.0})
    assert settings_store.get_semantic_fusion_alpha(tmp_path, settings=s) == 0.0
    s = _seed(tmp_path, {"semantic_fusion_alpha": 1.0})
    assert settings_store.get_semantic_fusion_alpha(tmp_path, settings=s) == 1.0


def test_fusion_alpha_out_of_range_returns_none(tmp_path: Path):
    s = _seed(tmp_path, {"semantic_fusion_alpha": 1.5})
    assert settings_store.get_semantic_fusion_alpha(tmp_path, settings=s) is None
    s = _seed(tmp_path, {"semantic_fusion_alpha": -0.1})
    assert settings_store.get_semantic_fusion_alpha(tmp_path, settings=s) is None


def test_fusion_alpha_garbage_returns_none(tmp_path: Path):
    s = _seed(tmp_path, {"semantic_fusion_alpha": "not-a-number"})
    assert settings_store.get_semantic_fusion_alpha(tmp_path, settings=s) is None


def test_runtime_config_handles_garbage_numeric(tmp_path: Path):
    s = _seed(tmp_path, {
        "semantic_max_chunk_chars": "garbage",
        "semantic_breakpoint_percentile_lo": "x",
    })
    cfg = settings_store.get_semantic_runtime_config(tmp_path, settings=s)
    assert "max_chars" not in cfg
    assert "percentile_lo" not in cfg


def test_semantic_keys_persist_roundtrip(tmp_path: Path, monkeypatch):
    """save() → load() must preserve all semantic_* keys with correct types."""
    # Force standalone mode (avoid HVE settings dependency).
    monkeypatch.setattr(settings_store, "_try_hve_settings_store", lambda: None)
    payload = {"mdq": dict(settings_store.defaults())}
    payload["mdq"]["semantic_max_chunk_chars"] = 1200
    payload["mdq"]["semantic_breakpoint_percentile_lo"] = 60.5
    payload["mdq"]["semantic_embed_provider"] = "fastembed"
    payload["mdq"]["semantic_contextualize"] = False
    payload["mdq"]["semantic_late_chunking"] = True
    payload["mdq"]["semantic_fusion_alpha"] = 0.75
    settings_store.save(tmp_path, payload)
    loaded = settings_store.load(tmp_path)
    assert loaded["mdq"]["semantic_max_chunk_chars"] == 1200
    assert loaded["mdq"]["semantic_breakpoint_percentile_lo"] == 60.5
    assert loaded["mdq"]["semantic_embed_provider"] == "fastembed"
    assert loaded["mdq"]["semantic_contextualize"] is False
    assert loaded["mdq"]["semantic_late_chunking"] is True
    assert loaded["mdq"]["semantic_fusion_alpha"] == 0.75
