"""hve.pricing.crawler のテスト (固定 HTML、ネットワーク不要)。"""

from __future__ import annotations

import pytest

from hve.pricing.crawler import (
    PricingFetchError,
    fetch_copilot_pricing,
    parse_docs_multipliers,
    parse_docs_token_prices,
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


_TOKEN_DOCS_HTML = """
<html><body>
<table>
  <thead><tr><th>Model</th><th>Release status</th><th>Tier</th><th>Input</th><th>Cached input</th><th>Output</th></tr></thead>
  <tbody>
    <tr><td>GPT-5.4</td><td>GA</td><td>Default</td><td style="text-align:right">$2.50</td><td>$0.25</td><td>$15.00</td></tr>
    <tr><td>GPT-5.4</td><td>GA</td><td>Long context</td><td>$5.00</td><td>$0.50</td><td>$22.50</td></tr>
    <tr><td>Gemini 3.6 Flash<sup><a href="#fn">1</a></sup></td><td>GA</td><td>Default</td><td>$0.75</td><td>$0.075</td><td>$3.75</td></tr>
    <tr><td>Claude Opus 5.5</td><td>GA</td><td>Default</td><td>Not applicable</td><td>$0.20</td><td>$20.00</td></tr>
    <tr><td>Unpriced</td><td>GA</td><td>Default</td><td>Not applicable</td><td>Not applicable</td><td>Not applicable</td></tr>
  </tbody>
</table>
</body></html>
"""


def test_parse_docs_token_prices_uses_default_tier_and_drops_footnotes() -> None:
    models = parse_docs_token_prices(_TOKEN_DOCS_HTML)

    assert models["gpt-5-4"].input_price_per_mtoken_usd == 2.5
    assert models["gpt-5-4"].output_price_per_mtoken_usd == 15.0
    assert models["gpt-5-4"].multiplier is None
    assert models["gemini-3-6-flash"].display_name == "Gemini 3.6 Flash"
    assert models["gemini-3-6-flash"].output_price_per_mtoken_usd == 3.75


def test_parse_docs_token_prices_keeps_unparseable_values_as_none() -> None:
    models = parse_docs_token_prices(_TOKEN_DOCS_HTML)

    assert models["claude-opus-5-5"].input_price_per_mtoken_usd is None
    assert models["claude-opus-5-5"].output_price_per_mtoken_usd == 20.0
    assert "unpriced" not in models


def test_parse_docs_token_prices_ignores_tables_without_input_output() -> None:
    assert parse_docs_token_prices(_DOCS_HTML) == {}
    assert parse_docs_token_prices("<p>no table</p>") == {}


def test_fetch_copilot_pricing_token_docs_with_unparseable_plan_page_is_partial(
    monkeypatch,
) -> None:
    from hve.pricing import crawler

    def _get(url, timeout=5.0):
        return _TOKEN_DOCS_HTML if "docs.github.com" in url else "<html></html>"

    monkeypatch.setattr(crawler, "_http_get", _get)
    pricing = fetch_copilot_pricing()

    assert pricing.status == "partial"
    assert pricing.models and pricing.plans == {}
    assert pricing.source_urls["docs"] == crawler.DOCS_URL


def test_docs_url_is_the_current_models_and_pricing_page() -> None:
    from hve.pricing import crawler

    assert crawler.DOCS_URL == (
        "https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing"
    )


def test_get_model_matches_sdk_ids_with_dots() -> None:
    from hve.pricing.models import CopilotPricing

    pricing = CopilotPricing(models=parse_docs_token_prices(_TOKEN_DOCS_HTML))

    assert pricing.get_model("claude-opus-5.5").model_id == "claude-opus-5-5"
    assert pricing.get_model("Gemini-3.6-Flash").model_id == "gemini-3-6-flash"
    assert pricing.get_model("unknown-model") is None


def test_pricing_refresh_command_succeeds_with_models_only(
    monkeypatch, tmp_path, capsys
) -> None:
    import hve.__main__ as hve_main
    import hve.pricing as pricing_pkg
    from hve.pricing import crawler

    def _get(url, timeout=5.0):
        if "docs.github.com" in url:
            return _TOKEN_DOCS_HTML
        raise PricingFetchError("plans down")

    monkeypatch.setattr(crawler, "_http_get", _get)
    monkeypatch.setattr(pricing_pkg, "default_cache_path", lambda: tmp_path / "pricing.json")

    code = hve_main.main(["pricing", "refresh", "--timeout", "1"])

    assert code == 0
    assert "status=partial" in capsys.readouterr().out
    assert (tmp_path / "pricing.json").exists()