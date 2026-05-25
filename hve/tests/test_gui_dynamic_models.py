"""tests/test_gui_dynamic_models.py — GUI モデル選択肢動的化のユニットテスト

Qt 描画には依存しない (page_options モジュールの `_load_model_choices` のみ検証)。
モジュール定数 `MODEL_CHOICES` は GUI 再起動なしで反映するために廃止済みであり、
代わりに `_C1Basic.__init__` と `_C1Basic.reload_models()` の双方が
`_load_model_choices()` を都度呼び出す設計に変更されている。
"""

from __future__ import annotations

import importlib
import time

import pytest


pytest.importorskip("PySide6", reason="GUI extras (PySide6) が未導入")


@pytest.fixture
def isolated_cache_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HVE_MODELS_CACHE_PATH", str(tmp_path / "models.json"))
    yield tmp_path


class TestLoadModelChoices:
    def test_uses_cache_when_present(self, isolated_cache_env):
        from hve import models_cache
        from hve.gui import page_options

        models_cache.save(["custom-1", "custom-2"], now=time.time())
        # _load_model_choices は import 時固定なので関数を再呼び出し
        result = page_options._load_model_choices()
        assert result[0] == "Auto"
        assert result[1:] == ["custom-1", "custom-2"]

    def test_uses_stale_cache(self, isolated_cache_env):
        from hve import models_cache
        from hve.gui import page_options

        # 30h 前 (stale)
        models_cache.save(["stale-1"], now=time.time() - 30 * 3600)
        result = page_options._load_model_choices()
        assert "stale-1" in result

    def test_falls_back_when_no_cache(self, isolated_cache_env):
        from hve.config import FALLBACK_MODEL_CHOICES
        from hve.gui import page_options

        result = page_options._load_model_choices()
        assert result[0] == "Auto"
        assert result[1:] == list(FALLBACK_MODEL_CHOICES)

    def test_module_constant_format(self):
        from hve.gui import page_options

        # MODEL_CHOICES 定数は廃止済み。_load_model_choices() の戻り値で検証する。
        result = page_options._load_model_choices()
        # 先頭は必ず Auto
        assert result[0] == "Auto"
        # 少なくとも 1 つ以上のモデルがある
        assert len(result) >= 2


# NOTE: 旧 TestLoginDialogImport は hve/gui/login_dialog.py 削除に伴い 2026-05 撤去。
# 認証は GitHub Copilot CLI 側で完結する想定。
