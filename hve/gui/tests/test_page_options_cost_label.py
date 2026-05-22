"""_format_cost_label / _format_context_size_label の整形テスト。"""

from __future__ import annotations

from hve.gui.page_options import _format_context_size_label, _format_cost_label
from hve.models_api import ModelEntry


def test_format_cost_label_all_prices():
    e = ModelEntry(
        id="x", name="X",
        input_price_usd_per_1m=3.0,
        output_price_usd_per_1m=15.0,
        cache_price_usd_per_1m=0.3,
    )
    s = _format_cost_label(e)
    assert "In $3.00/1M" in s
    assert "Out $15.00/1M" in s
    assert "Cache $0.30/1M" in s
    assert " · " in s


def test_format_cost_label_partial():
    e = ModelEntry(id="x", name="X", input_price_usd_per_1m=3.0)
    s = _format_cost_label(e)
    assert s == "In $3.00/1M"


def test_format_cost_label_none():
    assert _format_cost_label(None) == ""
    e = ModelEntry(id="x", name="X")
    assert _format_cost_label(e) == ""


def test_format_context_size_label():
    assert _format_context_size_label(200000) == "Context Size: 200K tokens (200,000)"
    assert _format_context_size_label(None) == ""
    assert _format_context_size_label(0) == ""
    assert _format_context_size_label(500) == "Context Size: 500 tokens"
