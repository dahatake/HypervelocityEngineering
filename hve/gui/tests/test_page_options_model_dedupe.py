"""page_options._load_model_choices の "Auto"/"auto" 重複排除テスト。

GUI ドロップダウンに `Auto`（MODEL_AUTO_VALUE）と API 由来の `auto` が同時に
表示されないことを保証する。
"""

from __future__ import annotations

import os
import tempfile

import pytest

from hve import models_cache
from hve.config import MODEL_AUTO_VALUE
from hve.gui.page_options import _load_model_choices


@pytest.fixture
def tmp_cache_path(monkeypatch):
    path = os.path.join(tempfile.gettempdir(), "hve-test-models-dedupe.json")
    monkeypatch.setenv("HVE_MODELS_CACHE_PATH", path)
    if os.path.exists(path):
        os.unlink(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_lowercase_auto_is_filtered_out(tmp_cache_path):
    models_cache.save(["auto", "claude-opus-4.7", "gpt-5.5"])
    choices = _load_model_choices()
    assert choices[0] == MODEL_AUTO_VALUE
    # "auto" は除去され、"Auto" は 1 件のみ
    assert sum(1 for c in choices if c.lower() == "auto") == 1
    assert "claude-opus-4.7" in choices
    assert "gpt-5.5" in choices


def test_mixed_case_and_duplicate_ids_deduped(tmp_cache_path):
    models_cache.save(["AUTO", "Auto", "claude-opus-4.7", "claude-opus-4.7", "GPT-5.5", "gpt-5.5"])
    choices = _load_model_choices()
    # "Auto" は 1 件のみ
    assert sum(1 for c in choices if c.lower() == "auto") == 1
    # claude-opus-4.7 は 1 件のみ
    assert sum(1 for c in choices if c.lower() == "claude-opus-4.7") == 1
    # gpt-5.5 (大小無視) も 1 件のみ
    assert sum(1 for c in choices if c.lower() == "gpt-5.5") == 1


def test_no_cache_returns_auto_first_only_once(tmp_cache_path):
    # キャッシュ無し → FALLBACK_MODEL_CHOICES のみ。先頭は "Auto" 1 件。
    choices = _load_model_choices()
    assert choices[0] == MODEL_AUTO_VALUE
    assert sum(1 for c in choices if c.lower() == "auto") == 1
