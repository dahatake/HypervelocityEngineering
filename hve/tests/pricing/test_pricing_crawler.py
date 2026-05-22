"""hve.pricing.crawler のテスト (固定 HTML、ネットワーク不要)。"""

from __future__ import annotations

import pytest

from hve.pricing.crawler import (
    PricingFetchError,
    fetch_copilot_pricing,
    parse_docs_multipliers,
    parse_pricing_plans,
)


_DOCS_HTML = """
<html><body>
<h1>About billing</h1>
<table>
  <thead><tr><th>Model</th><th>Multiplier</th></tr></thead>
  <tbody>
    <tr><td>Claude Sonnet 4</td><td>1x</td></tr>
    <tr><td>GPT-5</td><td>1x</td></tr>
    <tr><td>Claude Opus 4</td><td>10x</td></tr>
  </tbody>
</table>
</body></html>
"""

_PRICING_HTML = """
<html><body>
<section>Copilot Pro $10 per month
  300 premium requests per month
  Additional premium requests cost $0.04 per additional premium request</section>
<section>Copilot Business $19 per user / month
  300 premium requests
  $0.04 per additional premium request</section>
</body></html>
"""


def test_parse_docs_multipliers_basic() -> None:
    models = parse_docs_multipliers(_DOCS_HTML)
    assert "claude-sonnet-4" in models
    assert models["claude-sonnet-4"].multiplier == 1.0
    assert "claude-opus-4" in models
    assert models["claude-opus-4"].multiplier == 10.0
    assert "gpt-5" in models
    assert models["gpt-5"].multiplier == 1.0


def test_parse_docs_multipliers_no_table() -> None:
    assert parse_docs_multipliers("<html><body><p>no table</p></body></html>") == {}


def test_parse_pricing_plans_basic() -> None:
    plans = parse_pricing_plans(_PRICING_HTML)
    assert "copilot_pro" in plans
    assert plans["copilot_pro"].monthly_usd == 10.0
    assert plans["copilot_pro"].included_premium_requests == 300
    assert plans["copilot_pro"].additional_request_usd == 0.04


def test_fetch_copilot_pricing_both_fail(monkeypatch) -> None:
    from hve.pricing import crawler

    def _raise(*a, **kw):
        raise PricingFetchError("network down")

    monkeypatch.setattr(crawler, "_http_get", _raise)
    with pytest.raises(PricingFetchError):
        fetch_copilot_pricing()


def test_fetch_copilot_pricing_partial(monkeypatch) -> None:
    from hve.pricing import crawler

    def _get(url, timeout=5.0):
        if "docs.github.com" in url:
            return _DOCS_HTML
        raise PricingFetchError("pricing down")

    monkeypatch.setattr(crawler, "_http_get", _get)
    pricing = fetch_copilot_pricing()
    assert pricing.status == "partial"
    assert pricing.models
    assert pricing.plans == {}


def test_fetch_copilot_pricing_ok(monkeypatch) -> None:
    from hve.pricing import crawler

    def _get(url, timeout=5.0):
        return _DOCS_HTML if "docs.github.com" in url else _PRICING_HTML

    monkeypatch.setattr(crawler, "_http_get", _get)
    pricing = fetch_copilot_pricing()
    assert pricing.status == "ok"
    assert pricing.models
    assert pricing.plans
    assert pricing.source_urls.get("docs")
    assert pricing.source_urls.get("pricing")
