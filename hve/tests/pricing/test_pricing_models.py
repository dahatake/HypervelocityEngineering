"""hve.pricing.models のテスト。"""

from __future__ import annotations

from hve.pricing.models import CopilotPricing, ModelPricing, PlanPricing


def test_model_pricing_roundtrip() -> None:
    m = ModelPricing(model_id="claude-sonnet-4", display_name="Claude Sonnet 4", multiplier=1.0)
    assert m.to_dict()["multiplier"] == 1.0


def test_copilot_pricing_roundtrip() -> None:
    pricing = CopilotPricing(
        models={"claude-sonnet-4": ModelPricing(model_id="claude-sonnet-4", multiplier=1.0)},
        plans={"copilot_pro": PlanPricing(plan_id="copilot_pro", monthly_usd=10.0, additional_request_usd=0.04)},
        fetched_at="2026-05-01T00:00:00+00:00",
        source_urls={"docs": "https://example.com/docs"},
        status="ok",
    )
    data = pricing.to_dict()
    restored = CopilotPricing.from_dict(data)
    assert restored.status == "ok"
    assert "claude-sonnet-4" in restored.models
    assert restored.plans["copilot_pro"].monthly_usd == 10.0


def test_get_model_prefix_match() -> None:
    pricing = CopilotPricing(
        models={"claude-sonnet-4": ModelPricing(model_id="claude-sonnet-4", multiplier=1.0)}
    )
    # SDK が version suffix 付きで返すケース
    m = pricing.get_model("claude-sonnet-4-20250101")
    assert m is not None
    assert m.multiplier == 1.0


def test_get_model_none_for_unknown() -> None:
    pricing = CopilotPricing()
    assert pricing.get_model("gpt-99") is None
    assert pricing.get_model("") is None
