"""hve.pricing.calculator — コスト計算。

``calc_cost(model, premium_requests, input_tokens, output_tokens, pricing, plan_id,
usd_jpy_rate) -> CostBreakdown``

優先順位:
1. ``ModelPricing.input_price_per_mtoken_usd`` / ``output_price_per_mtoken_usd``
   が両方取得できていれば、token ベースで計算する。
2. それ以外（multiplier ベース）は、``premium_requests × multiplier × plan.additional_request_usd``
   で計算する。
3. どちらも揃わなければ ``cost_usd = None``（捏造禁止）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from hve.pricing.models import CopilotPricing


DEFAULT_PLAN_ID = "copilot_pro"
"""``plan_id`` が指定されなかった場合に使うデフォルト。"""


@dataclass
class CostBreakdown:
    """コスト計算の内訳。値は USD 換算。"""

    cost_usd: Optional[float] = None
    cost_jpy: Optional[float] = None
    method: str = "unavailable"  # "token" / "multiplier" / "unavailable"
    multiplier: Optional[float] = None
    plan_id: Optional[str] = None
    additional_request_usd: Optional[float] = None
    usd_jpy_rate: Optional[float] = None
    notes: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "cost_usd": self.cost_usd,
            "cost_jpy": self.cost_jpy,
            "method": self.method,
            "multiplier": self.multiplier,
            "plan_id": self.plan_id,
            "additional_request_usd": self.additional_request_usd,
            "usd_jpy_rate": self.usd_jpy_rate,
            "notes": dict(self.notes),
        }


def _resolve_plan(
    pricing: CopilotPricing, plan_id: Optional[str]
) -> Optional[str]:
    """指定 plan_id がキャッシュにあればそのまま、無ければ既知優先順で fallback。"""
    if plan_id and plan_id in pricing.plans:
        return plan_id
    for candidate in (DEFAULT_PLAN_ID, "copilot_pro_plus", "copilot_business", "copilot_enterprise"):
        if candidate in pricing.plans:
            return candidate
    # 何かしらプラン情報があれば最初のもの
    if pricing.plans:
        return next(iter(pricing.plans.keys()))
    return None


def calc_cost(
    *,
    model: str,
    premium_requests: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    pricing: Optional[CopilotPricing] = None,
    plan_id: Optional[str] = None,
    usd_jpy_rate: Optional[float] = None,
) -> CostBreakdown:
    """コストを計算する。``pricing`` が ``None`` または不足時は ``cost_usd=None``。"""
    out = CostBreakdown(usd_jpy_rate=usd_jpy_rate)
    if pricing is None:
        out.notes["reason"] = "pricing cache unavailable"
        return out

    model_p = pricing.get_model(model) if model else None
    out.multiplier = model_p.multiplier if model_p else None

    # Token 課金（優先）
    if (
        model_p is not None
        and model_p.input_price_per_mtoken_usd is not None
        and model_p.output_price_per_mtoken_usd is not None
    ):
        cost = (
            (input_tokens or 0) / 1_000_000 * model_p.input_price_per_mtoken_usd
            + (output_tokens or 0) / 1_000_000 * model_p.output_price_per_mtoken_usd
        )
        out.cost_usd = round(cost, 6)
        out.method = "token"
    else:
        # Multiplier 課金
        resolved_plan_id = _resolve_plan(pricing, plan_id)
        out.plan_id = resolved_plan_id
        if resolved_plan_id is None:
            out.notes["reason"] = "no plan info in pricing cache"
        else:
            plan_p = pricing.plans[resolved_plan_id]
            out.additional_request_usd = plan_p.additional_request_usd
            mult = model_p.multiplier if model_p else None
            if mult is None:
                # モデル不明の場合 1.0× とみなさず未取得扱い（捏造禁止）
                out.notes["reason"] = f"no multiplier for model={model!r}"
            elif plan_p.additional_request_usd is None:
                out.notes["reason"] = f"no additional_request_usd for plan={resolved_plan_id!r}"
            else:
                out.cost_usd = round(
                    premium_requests * mult * plan_p.additional_request_usd, 6
                )
                out.method = "multiplier"

    if out.cost_usd is not None and usd_jpy_rate is not None and usd_jpy_rate > 0:
        out.cost_jpy = round(out.cost_usd * usd_jpy_rate, 2)
    return out


__all__ = ["CostBreakdown", "calc_cost", "DEFAULT_PLAN_ID"]
