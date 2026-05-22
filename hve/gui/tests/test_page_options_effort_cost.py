"""C1 基本設定: cost ラベル表示と Effort autosave 発火の追加テスト。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui import page_options  # noqa: E402
from hve.gui.page_options import _C1Basic  # noqa: E402
from hve.models_api import ModelEntry  # noqa: E402


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _patch_models(monkeypatch, entries):
    monkeypatch.setattr(
        page_options, "_load_model_choices",
        lambda: ["Auto"] + [e.id for e in entries],
    )
    monkeypatch.setattr(
        page_options, "_load_model_entries_map",
        lambda: {e.id: e for e in entries},
    )


def test_cost_label_shown_on_model_change(monkeypatch):
    _get_app()
    entries = [
        ModelEntry(
            id="claude-opus-4.7", name="Claude Opus 4.7",
            default_reasoning_effort="medium",
            supported_reasoning_efforts=["low", "medium", "high"],
            supports_reasoning_effort=True,
            max_context_window_tokens=200000,
            input_price_usd_per_1m=5.0,
            output_price_usd_per_1m=25.0,
            cache_price_usd_per_1m=0.5,
        ),
    ]
    _patch_models(monkeypatch, entries)

    w = _C1Basic()
    idx = w.model.findData("claude-opus-4.7")
    assert idx >= 0
    w.model.setCurrentIndex(idx)

    assert w.effort.isEnabled()
    items = [w.effort.itemData(i) for i in range(w.effort.count())]
    assert items == ["low", "medium", "high"]
    assert w.effort.currentData() == "medium"
    text = w.cost_label.text()
    assert "In $5.00/1M" in text
    assert "Out $25.00/1M" in text
    assert "Cache $0.50/1M" in text


def test_effort_autosave_fires_on_model_change(monkeypatch):
    _get_app()
    entries = [
        ModelEntry(
            id="claude-opus-4.7", name="Claude Opus 4.7",
            default_reasoning_effort="medium",
            supported_reasoning_efforts=["low", "medium", "high"],
            supports_reasoning_effort=True,
        ),
    ]
    _patch_models(monkeypatch, entries)

    w = _C1Basic()
    fired = []
    w.effort.currentIndexChanged.connect(lambda _i: fired.append(w.effort.currentData()))

    idx = w.model.findData("claude-opus-4.7")
    w.model.setCurrentIndex(idx)
    # autosave 連鎖トリガー: モデル変更 → Effort default 反映後 currentIndexChanged 発火
    assert fired, "effort.currentIndexChanged should fire after model change"
    assert fired[-1] == "medium"


def test_cost_label_empty_when_no_prices(monkeypatch):
    _get_app()
    entries = [
        ModelEntry(
            id="gpt-5.5", name="GPT 5.5",
            default_reasoning_effort="low",
            supported_reasoning_efforts=["low", "high"],
            supports_reasoning_effort=True,
        ),
    ]
    _patch_models(monkeypatch, entries)

    w = _C1Basic()
    idx = w.model.findData("gpt-5.5")
    w.model.setCurrentIndex(idx)
    assert w.cost_label.text() == ""
