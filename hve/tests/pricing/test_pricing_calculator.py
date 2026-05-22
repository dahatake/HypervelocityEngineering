"""hve.pricing.calculator のテスト。"""

from __future__ import annotations

from hve.pricing.calculator import calc_cost
from hve.pricing.models import CopilotPricing, ModelPricing, PlanPricing


def _pricing_multiplier_only() -> CopilotPricing:
    return CopilotPricing(
        models={
            "claude-sonnet-4": ModelPricing(model_id="claude-sonnet-4", multiplier=1.0),
            "claude-opus-4": ModelPricing(model_id="claude-opus-4", multiplier=10.0),
        },
        plans={
            "copilot_pro": PlanPricing(
                plan_id="copilot_pro",
                monthly_usd=10.0,
                additional_request_usd=0.04,
            )
        },
        status="ok",
    )


def _pricing_token_based() -> CopilotPricing:
    return CopilotPricing(
        models={
            "fancy-model": ModelPricing(
                model_id="fancy-model",
                multiplier=2.0,
                input_price_per_mtoken_usd=3.0,
                output_price_per_mtoken_usd=15.0,
            )
        },
        plans={},
        status="ok",
    )


def test_calc_cost_multiplier_basic() -> None:
    br = calc_cost(
        model="claude-sonnet-4",
        premium_requests=10,
        pricing=_pricing_multiplier_only(),
        usd_jpy_rate=150.0,
    )
    assert br.method == "multiplier"
    assert br.cost_usd == 0.4  # 10 * 1.0 * 0.04
    assert br.cost_jpy == 60.0
    assert br.multiplier == 1.0


def test_calc_cost_multiplier_opus() -> None:
    br = calc_cost(
        model="claude-opus-4",
        premium_requests=5,
        pricing=_pricing_multiplier_only(),
        usd_jpy_rate=150.0,
    )
    assert br.cost_usd == 2.0  # 5 * 10 * 0.04


def test_calc_cost_token_based_priority() -> None:
    br = calc_cost(
        model="fancy-model",
        input_tokens=1_000_000,
        output_tokens=500_000,
        premium_requests=999,  # 無視されるべき
        pricing=_pricing_token_based(),
        usd_jpy_rate=150.0,
    )
    assert br.method == "token"
    # 1M * $3 + 0.5M * $15 = 3 + 7.5 = 10.5
    assert br.cost_usd == 10.5


def test_calc_cost_no_pricing_returns_none() -> None:
    br = calc_cost(model="x", premium_requests=10, pricing=None)
    assert br.cost_usd is None
    assert br.method == "unavailable"


def test_calc_cost_unknown_model() -> None:
    br = calc_cost(
        model="unknown-model",
        premium_requests=10,
        pricing=_pricing_multiplier_only(),
        usd_jpy_rate=150.0,
    )
    assert br.cost_usd is None
    assert br.method == "unavailable"


def test_calc_cost_no_jpy_rate() -> None:
    br = calc_cost(
        model="claude-sonnet-4",
        premium_requests=10,
        pricing=_pricing_multiplier_only(),
        usd_jpy_rate=None,
    )
    assert br.cost_usd == 0.4
    assert br.cost_jpy is None
