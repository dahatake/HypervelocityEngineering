"""ModelEntry の token_prices フィールド往復テスト（cache I/O）。"""

from __future__ import annotations

import os
import tempfile

import pytest

from hve import models_cache
from hve.models_api import ModelEntry


@pytest.fixture
def tmp_cache(monkeypatch):
    path = os.path.join(tempfile.gettempdir(), "hve-test-cache-billing.json")
    monkeypatch.setenv("HVE_MODELS_CACHE_PATH", path)
    if os.path.exists(path):
        os.unlink(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_save_and_load_token_prices(tmp_cache):
    entries = [
        ModelEntry(
            id="claude-opus-4.7",
            name="Claude Opus 4.7",
            default_reasoning_effort="medium",
            supported_reasoning_efforts=["low", "medium", "high"],
            supports_reasoning_effort=True,
            max_context_window_tokens=200000,
            input_price_usd_per_1m=5.0,
            output_price_usd_per_1m=25.0,
            cache_price_usd_per_1m=0.5,
        ),
        ModelEntry(
            id="gpt-5.5",
            name="GPT 5.5",
            input_price_usd_per_1m=None,
            output_price_usd_per_1m=None,
            cache_price_usd_per_1m=None,
        ),
    ]
    models_cache.save_entries(entries)

    loaded = models_cache.load(allow_stale=True)
    assert loaded is not None
    by_id = {e.id: e for e in loaded.entries}
    assert by_id["claude-opus-4.7"].input_price_usd_per_1m == 5.0
    assert by_id["claude-opus-4.7"].output_price_usd_per_1m == 25.0
    assert by_id["claude-opus-4.7"].cache_price_usd_per_1m == 0.5
    assert by_id["gpt-5.5"].input_price_usd_per_1m is None
    assert by_id["gpt-5.5"].output_price_usd_per_1m is None
