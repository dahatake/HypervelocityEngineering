"""tests/test_models_cache.py — hve.models_cache のユニットテスト"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from hve.models_api import ModelEntry
from hve.models_cache import (
    CACHE_VERSION,
    DEFAULT_TTL_SECONDS,
    CachedModels,
    clear,
    get_cache_path,
    is_fresh,
    load,
    save,
    save_entries,
)


# =====================================================================
# get_cache_path
# =====================================================================


class TestGetCachePath:
    def test_env_override(self, monkeypatch, tmp_path):
        override = tmp_path / "custom.json"
        monkeypatch.setenv("HVE_MODELS_CACHE_PATH", str(override))
        assert get_cache_path() == override

    def test_default_uses_platformdirs(self, monkeypatch):
        monkeypatch.delenv("HVE_MODELS_CACHE_PATH", raising=False)
        p = get_cache_path()
        assert p.name == "models.json"
        assert "hve" in str(p).lower()


# =====================================================================
# save / load round-trip
# =====================================================================


class TestSaveLoad:
    def test_roundtrip(self, tmp_path):
        path = tmp_path / "models.json"
        save(["a", "b", "c"], path=path, now=1000.0)
        cached = load(path=path, now=1000.0)
        assert cached is not None
        assert cached.models == ["a", "b", "c"]
        assert cached.fetched_at == 1000.0

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "models.json"
        save(["x"], path=path)
        assert path.is_file()

    def test_save_writes_valid_json(self, tmp_path):
        path = tmp_path / "m.json"
        save(["a"], path=path, now=1234.0)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == CACHE_VERSION
        assert data["fetched_at"] == 1234.0
        assert data["models"] == ["a"]


# =====================================================================
# load — エッジケース
# =====================================================================


class TestLoad:
    def test_missing_file_returns_none(self, tmp_path):
        assert load(path=tmp_path / "nope.json") is None

    def test_corrupt_json_returns_none(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("not json{{{", encoding="utf-8")
        assert load(path=path) is None

    def test_wrong_version_returns_none(self, tmp_path):
        path = tmp_path / "m.json"
        path.write_text(
            json.dumps({"version": 999, "fetched_at": 1.0, "models": ["a"]}),
            encoding="utf-8",
        )
        assert load(path=path) is None

    def test_missing_fields_returns_none(self, tmp_path):
        path = tmp_path / "m.json"
        path.write_text(json.dumps({"version": 1}), encoding="utf-8")
        assert load(path=path) is None

    def test_non_dict_root_returns_none(self, tmp_path):
        path = tmp_path / "m.json"
        path.write_text(json.dumps(["a", "b"]), encoding="utf-8")
        assert load(path=path) is None

    def test_filters_non_string_models(self, tmp_path):
        path = tmp_path / "m.json"
        path.write_text(
            json.dumps(
                {"version": 1, "fetched_at": 1.0, "models": ["a", 123, "", "b", None]}
            ),
            encoding="utf-8",
        )
        cached = load(path=path, now=1.0)
        assert cached is not None
        assert cached.models == ["a", "b"]


# =====================================================================
# TTL / stale
# =====================================================================


class TestTTL:
    def test_fresh_within_ttl(self, tmp_path):
        path = tmp_path / "m.json"
        save(["a"], path=path, now=1000.0)
        # 23h 後 (TTL 24h 内)
        cached = load(path=path, now=1000.0 + 23 * 3600)
        assert cached is not None

    def test_stale_returns_none_by_default(self, tmp_path):
        path = tmp_path / "m.json"
        save(["a"], path=path, now=1000.0)
        # 25h 後 (TTL 切れ)
        cached = load(path=path, now=1000.0 + 25 * 3600)
        assert cached is None

    def test_stale_returns_when_allow_stale(self, tmp_path):
        path = tmp_path / "m.json"
        save(["a"], path=path, now=1000.0)
        cached = load(path=path, now=1000.0 + 25 * 3600, allow_stale=True)
        assert cached is not None
        assert cached.models == ["a"]

    def test_custom_ttl(self, tmp_path):
        path = tmp_path / "m.json"
        save(["a"], path=path, now=1000.0)
        # TTL 60秒, 100秒後 → stale
        assert load(path=path, now=1100.0, ttl_seconds=60) is None
        assert load(path=path, now=1030.0, ttl_seconds=60) is not None

    def test_is_fresh_boundary(self):
        cached = CachedModels(models=["a"], fetched_at=1000.0)
        assert is_fresh(cached, ttl_seconds=100, now=1099.9) is True
        assert is_fresh(cached, ttl_seconds=100, now=1100.0) is False


# =====================================================================
# clear
# =====================================================================


class TestClear:
    def test_removes_existing_file(self, tmp_path):
        path = tmp_path / "m.json"
        save(["a"], path=path)
        assert path.is_file()
        assert clear(path=path) is True
        assert not path.exists()

    def test_missing_file_returns_false(self, tmp_path):
        assert clear(path=tmp_path / "nope.json") is False


# =====================================================================
# CachedModels
# =====================================================================


class TestCachedModels:
    def test_age_seconds(self):
        c = CachedModels(models=["a"], fetched_at=1000.0)
        assert c.age_seconds(now=1500.0) == 500.0

    def test_frozen(self):
        c = CachedModels(models=["a"], fetched_at=1.0)
        with pytest.raises(Exception):
            c.fetched_at = 2.0  # type: ignore[misc]


# =====================================================================
# v2 フォーマット: save_entries / load (ModelEntry round-trip)
# =====================================================================


class TestSaveEntriesV2:
    def test_roundtrip_with_full_fields(self, tmp_path):
        path = tmp_path / "v2.json"
        entries = [
            ModelEntry(
                id="claude-opus-4.7",
                name="Claude Opus 4.7",
                default_reasoning_effort="medium",
                supported_reasoning_efforts=["low", "medium", "high"],
                supports_reasoning_effort=True,
                max_context_window_tokens=200000,
            ),
            ModelEntry(id="gpt-5.5", name="GPT 5.5"),
        ]
        save_entries(entries, path=path, now=1000.0)
        cached = load(path=path, now=1000.0)
        assert cached is not None
        assert cached.fetched_at == 1000.0
        assert cached.models == ["claude-opus-4.7", "gpt-5.5"]
        assert len(cached.entries) == 2

        e0 = cached.entries[0]
        assert e0.id == "claude-opus-4.7"
        assert e0.name == "Claude Opus 4.7"
        assert e0.default_reasoning_effort == "medium"
        assert e0.supported_reasoning_efforts == ["low", "medium", "high"]
        assert e0.supports_reasoning_effort is True
        assert e0.max_context_window_tokens == 200000

        e1 = cached.entries[1]
        assert e1.id == "gpt-5.5"
        assert e1.supports_reasoning_effort is False
        assert e1.supported_reasoning_efforts is None
        assert e1.max_context_window_tokens is None

    def test_v2_file_format(self, tmp_path):
        path = tmp_path / "v2.json"
        save_entries(
            [
                ModelEntry(
                    id="m1",
                    name="M1",
                    default_reasoning_effort="high",
                    supported_reasoning_efforts=["high"],
                    supports_reasoning_effort=True,
                    max_context_window_tokens=128000,
                )
            ],
            path=path,
            now=42.0,
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 2
        assert data["fetched_at"] == 42.0
        assert data["models"] == ["m1"]
        assert isinstance(data["entries"], list)
        assert data["entries"][0]["id"] == "m1"
        assert data["entries"][0]["max_context_window_tokens"] == 128000


class TestV1BackwardCompat:
    def test_load_v1_file_returns_models_with_empty_entries(self, tmp_path):
        """v1 形式（version=1）のキャッシュを読んだ場合、models は復元され entries は空。"""
        path = tmp_path / "v1.json"
        path.write_text(
            json.dumps(
                {"version": 1, "fetched_at": 1000.0, "models": ["alpha", "beta"]}
            ),
            encoding="utf-8",
        )
        cached = load(path=path, now=1000.0)
        assert cached is not None
        assert cached.models == ["alpha", "beta"]
        assert cached.entries == []


class TestFormatRoundTrip:
    def test_save_legacy_still_uses_v2_format(self, tmp_path):
        """既存 save(models) は CACHE_VERSION=2 のフォーマットで書き出す（entries は空）。"""
        path = tmp_path / "m.json"
        save(["a", "b"], path=path, now=1.0)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 2
        assert data["models"] == ["a", "b"]
        assert data["entries"] == []
