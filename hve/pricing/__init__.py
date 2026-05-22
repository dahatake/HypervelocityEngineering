"""hve.pricing — GitHub Copilot 料金表のクロール / キャッシュ / コスト計算。

サブモジュール:
- ``models``     : データクラス ``CopilotPricing`` / ``ModelPricing`` / ``PlanPricing``
- ``crawler``    : docs.github.com + github.com/pricing からの取得
- ``cache``      : ``~/.hve/pricing/copilot-pricing.json`` の永続化と月初判定
- ``calculator`` : ``calc_cost(model, premium_requests, ...) -> (usd, jpy, breakdown)``

捏造禁止: 取得失敗時は例外、未取得値は None。
"""

from hve.pricing.calculator import CostBreakdown, calc_cost
from hve.pricing.cache import (
    PricingCache,
    default_cache_path,
    load_cached_pricing,
    save_cached_pricing,
    should_refresh,
)
from hve.pricing.crawler import PricingFetchError, fetch_copilot_pricing
from hve.pricing.models import CopilotPricing, ModelPricing, PlanPricing

__all__ = [
    "CopilotPricing",
    "ModelPricing",
    "PlanPricing",
    "CostBreakdown",
    "calc_cost",
    "PricingCache",
    "default_cache_path",
    "load_cached_pricing",
    "save_cached_pricing",
    "should_refresh",
    "PricingFetchError",
    "fetch_copilot_pricing",
]
