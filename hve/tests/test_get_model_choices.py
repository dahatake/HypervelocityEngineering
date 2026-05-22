"""tests/test_get_model_choices.py — config.get_model_choices のユニットテスト"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from hve import config as hve_config
from hve import models_cache


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """各テストで独立したキャッシュファイルを使用する。"""
    cache_path = tmp_path / "models.json"
    monkeypatch.setenv("HVE_MODELS_CACHE_PATH", str(cache_path))
    yield cache_path


class TestGetModelChoicesFresh:
    def test_uses_fresh_cache(self, isolated_cache):
        models_cache.save(["cached-a", "cached-b"], path=isolated_cache, now=time.time())
        # SDK 呼び出しは行われないはず
        with patch("hve.models_api.fetch_models") as mock_fetch:
            result = hve_config.get_model_choices()
        mock_fetch.assert_not_called()
        assert result == ["cached-a", "cached-b"]


class TestGetModelChoicesAPISuccess:
    def test_fetches_when_no_cache(self, isolated_cache):
        with patch("hve.models_api.fetch_models", return_value=["api-1", "api-2"]):
            result = hve_config.get_model_choices()
        assert result == ["api-1", "api-2"]
        # キャッシュに書き込まれている
        loaded = models_cache.load(path=isolated_cache)
        assert loaded is not None
        assert loaded.models == ["api-1", "api-2"]

    def test_force_refresh_bypasses_cache(self, isolated_cache):
        models_cache.save(["old-1"], path=isolated_cache, now=time.time())
        with patch("hve.models_api.fetch_models", return_value=["new-1", "new-2"]):
            result = hve_config.get_model_choices(force_refresh=True)
        assert result == ["new-1", "new-2"]


class TestGetModelChoicesStaleFallback:
    def test_returns_stale_when_api_fails(self, isolated_cache):
        from hve.models_api import ModelsAPIError

        # 30h 前 (TTL 24h 切れ)
        old_time = time.time() - 30 * 3600
        models_cache.save(["stale-1", "stale-2"], path=isolated_cache, now=old_time)
        with patch(
            "hve.models_api.fetch_models", side_effect=ModelsAPIError("no auth")
        ):
            result = hve_config.get_model_choices()
        assert result == ["stale-1", "stale-2"]


class TestGetModelChoicesFinalFallback:
    def test_falls_back_to_constant_when_all_fail(self, isolated_cache):
        from hve.models_api import ModelsAPIError

        # キャッシュなし、API も失敗
        with patch(
            "hve.models_api.fetch_models", side_effect=ModelsAPIError("offline")
        ):
            result = hve_config.get_model_choices()
        assert result == list(hve_config.FALLBACK_MODEL_CHOICES)
        assert "claude-opus-4.7" in result


class TestIncludeAuto:
    def test_include_auto_prepends(self, isolated_cache):
        models_cache.save(["m1", "m2"], path=isolated_cache, now=time.time())
        result = hve_config.get_model_choices(include_auto=True)
        assert result == [hve_config.MODEL_AUTO_VALUE, "m1", "m2"]

    def test_include_auto_with_fallback(self, isolated_cache):
        from hve.models_api import ModelsAPIError

        with patch(
            "hve.models_api.fetch_models", side_effect=ModelsAPIError("x")
        ):
            result = hve_config.get_model_choices(include_auto=True)
        assert result[0] == hve_config.MODEL_AUTO_VALUE
        assert result[1:] == list(hve_config.FALLBACK_MODEL_CHOICES)


class TestFallbackAlias:
    def test_fallback_choices_equals_model_choices(self):
        assert hve_config.FALLBACK_MODEL_CHOICES == hve_config.MODEL_CHOICES


class TestEmptyAPIResult:
    def test_empty_api_result_uses_fallback(self, isolated_cache):
        # 空リスト返却時はフォールバックへ
        with patch("hve.models_api.fetch_models", return_value=[]):
            result = hve_config.get_model_choices()
        assert result == list(hve_config.FALLBACK_MODEL_CHOICES)
