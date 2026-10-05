"""FR-MODEL-01: 既定モデルは SDK で実在を確認した claude-opus-5.5 とし、選択肢の面を揃える。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from hve.config import DEFAULT_MODEL, FALLBACK_MODEL_CHOICES, MODEL_CHOICES

_ROOT = Path(__file__).resolve().parents[2]
# 2026-09-24 に `hve.models_api.fetch_model_entries()` の実応答で実在を確認した ID
_VERIFIED_OPUS_55 = "claude-opus-5.5"


def test_default_model_matches_verified_id() -> None:
    assert DEFAULT_MODEL == _VERIFIED_OPUS_55
    assert MODEL_CHOICES[0] == _VERIFIED_OPUS_55
    assert FALLBACK_MODEL_CHOICES == MODEL_CHOICES


def test_cloud_model_surfaces_accept_verified_id() -> None:
    labels = {item["name"] for item in json.loads((_ROOT / ".github" / "labels.json").read_text(encoding="utf-8"))}
    for prefix in ("model", "review-model", "qa-model"):
        assert f"{prefix}/{_VERIFIED_OPUS_55}" in labels, prefix

    for name in ("extract-model.py", "extract-review-model.py", "extract-qa-model.py", "extract-akm-model.py"):
        text = (_ROOT / ".github" / "scripts" / "bash" / "lib" / name).read_text(encoding="utf-8")
        assert f'"{_VERIFIED_OPUS_55}"' in text, name

    workflow = (_ROOT / ".github" / "workflows" / "auto-akm-after-qa.yml").read_text(encoding="utf-8")
    assert re.search(rf'"{re.escape(_VERIFIED_OPUS_55)}"\|', workflow)


def test_guide_states_default_model_for_unspecified_model() -> None:
    guide = (_ROOT / "users-guide" / "workflow-reference.md").read_text(encoding="utf-8")
    assert f"`DEFAULT_MODEL`）は `{DEFAULT_MODEL}`" in guide
    assert "`--model` と環境変数 `MODEL` の両方が未指定のとき `Auto` で実行する" not in guide


def test_unspecified_model_uses_default_model_on_local_surfaces(monkeypatch) -> None:
    from hve.config import SDKConfig
    from hve.gui import settings_store

    monkeypatch.delenv("MODEL", raising=False)
    assert SDKConfig.from_env().model == DEFAULT_MODEL
    monkeypatch.setenv("MODEL", "")
    assert SDKConfig.from_env().model == DEFAULT_MODEL
    assert SDKConfig(model="").model == DEFAULT_MODEL
    assert settings_store.defaults()["options"]["model"] == DEFAULT_MODEL

    help_texts = {
        "__main__.py": (_ROOT / "hve" / "__main__.py").read_text(encoding="utf-8"),
        "help_content.py": (_ROOT / "hve" / "gui" / "help_content.py").read_text(encoding="utf-8"),
        "page_options.py": (_ROOT / "hve" / "gui" / "page_options.py").read_text(encoding="utf-8"),
    }
    for text in help_texts.values():
        assert "デフォルト: Auto)" not in text
        assert "既定: Auto）" not in text
    # Qt の翻訳元文字列はリテラルで持つため、DEFAULT_MODEL の変更時に追随しているかを確認する
    assert f"デフォルト: {DEFAULT_MODEL})" in help_texts["help_content.py"]
    assert f"既定: {DEFAULT_MODEL}）" in help_texts["page_options.py"]
