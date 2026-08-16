"""GUI テスト共通の環境セットアップ。

`page_options` 等が import 時に `platformdirs` を要求するため、
未導入環境でも `HVE_MODELS_CACHE_PATH` を事前設定してキャッシュパス解決を回避する。
"""

from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "HVE_MODELS_CACHE_PATH",
    os.path.join(tempfile.gettempdir(), "hve-test-models-cache.json"),
)


@pytest.fixture(autouse=True)
def _isolated_settings_store(tmp_path, monkeypatch):
    """設定ストアの実ファイルをテストから隔離する。

    `OptionsPage` は監視対象入力欄の `textChanged` で `settings_store.save()` を
    呼ぶため、ウィジェットへ値を入れるだけで利用者の `hve/.settings.txt` が
    書き換わる。
    """
    from hve.gui import settings_store

    monkeypatch.setattr(
        settings_store, "settings_path", lambda: tmp_path / ".settings.txt"
    )
