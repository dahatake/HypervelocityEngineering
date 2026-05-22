"""GUI テスト共通の環境セットアップ。

`page_options` 等が import 時に `platformdirs` を要求するため、
未導入環境でも `HVE_MODELS_CACHE_PATH` を事前設定してキャッシュパス解決を回避する。
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "HVE_MODELS_CACHE_PATH",
    os.path.join(tempfile.gettempdir(), "hve-test-models-cache.json"),
)
