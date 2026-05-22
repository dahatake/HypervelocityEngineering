"""WorkbenchState の料金累積 (Wave 3) のテスト。"""

from __future__ import annotations

import pytest

from hve.gui.workbench_state import WorkbenchState
from hve.pricing.models import CopilotPricing, ModelPricing, PlanPricing


def _make_state(model: str = "claude-sonnet-4") -> WorkbenchState:
    return WorkbenchState(workflow_id="wf", run_id="r1", model=model)


def _make_pricing() -> CopilotPricing:
    return CopilotPricing(
        models={
            "claude-sonnet-4": ModelPricing(model_id="claude-sonnet-4", multiplier=1.0),
            "claude-opus-4": ModelPricing(model_id="claude-opus-4", multiplier=10.0),
        },
        plans={
            "copilot_pro": PlanPricing(
                plan_id="copilot_pro", monthly_usd=10.0, additional_request_usd=0.04
            )
        },
        status="ok",
    )


def test_apply_premium_requests_without_pricing() -> None:
    s = _make_state()
    s.apply_premium_requests(5)
    assert s.premium_requests_total == 5
    assert s.cost_usd_total is None  # 捏造禁止
    assert s.cost_method_last == "unavailable"
    assert s.cost_unavailable_reason == "pricing_not_loaded"


def test_apply_premium_requests_with_pricing() -> None:
    s = _make_state()
    s.set_pricing(_make_pricing(), usd_jpy_rate=150.0)
    s.apply_premium_requests(10)
    assert s.premium_requests_total == 10
    assert s.cost_usd_total == 0.4
    assert s.cost_jpy_total == 60.0
    assert s.cost_method_last == "multiplier"


def test_apply_premium_requests_accumulates() -> None:
    s = _make_state()
    s.set_pricing(_make_pricing(), usd_jpy_rate=150.0)
    s.apply_premium_requests(10)
    s.apply_premium_requests(5)
    assert s.premium_requests_total == 15
    assert s.cost_usd_total == pytest.approx(0.6, abs=1e-9)  # 0.4 + 0.2
    assert s.cost_jpy_total == pytest.approx(90.0, abs=1e-6)


def test_apply_premium_requests_unknown_model() -> None:
    s = _make_state(model="unknown-model-xyz")
    s.set_pricing(_make_pricing(), usd_jpy_rate=150.0)
    s.apply_premium_requests(10)
    assert s.premium_requests_total == 10
    assert s.cost_usd_total is None  # 不明モデルは累積しない
    assert s.cost_method_last == "unavailable"


def test_apply_premium_requests_per_call_model_override() -> None:
    s = _make_state(model="claude-sonnet-4")
    s.set_pricing(_make_pricing(), usd_jpy_rate=150.0)
    s.apply_premium_requests(2, model="claude-opus-4")
    # 2 * 10 (opus) * 0.04 = 0.8
    assert s.cost_usd_total == 0.8


def test_apply_premium_requests_ignores_non_positive() -> None:
    s = _make_state()
    s.set_pricing(_make_pricing(), usd_jpy_rate=150.0)
    s.apply_premium_requests(0)
    s.apply_premium_requests(-3)
    assert s.premium_requests_total == 0
    assert s.cost_usd_total is None


def test_apply_premium_requests_invalid_count() -> None:
    s = _make_state()
    s.set_pricing(_make_pricing(), usd_jpy_rate=150.0)
    s.apply_premium_requests("not-a-number")  # type: ignore[arg-type]
    assert s.premium_requests_total == 0
