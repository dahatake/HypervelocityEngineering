"""hve.pricing.models — 料金データクラス。

捏造禁止: クロールできなかった値は None / 空 dict のまま保持する。
``ModelPricing.multiplier`` が None なら ``calculator.calc_cost`` は ``cost_usd=None`` を返す。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional


SCHEMA_VERSION = 1
"""``copilot-pricing.json`` のスキーマバージョン。後方互換性のため bump 時に
``cache.load_cached_pricing`` で migration を実装すること。"""


@dataclass(frozen=True)
class ModelPricing:
    """1 モデルの料金情報。

    - ``model_id``: SDK が ``assistant.usage.model`` で返す値（例: ``claude-sonnet-4``）
    - ``display_name``: docs.github.com 表示名（例: ``Claude Sonnet 4``）
    - ``multiplier``: 1 premium request あたりの倍率（例: 1.0, 10.0）。None=未取得
    - ``input_price_per_mtoken_usd``: token 課金モデル用。None=未取得
    - ``output_price_per_mtoken_usd``: token 課金モデル用。None=未取得
    """

    model_id: str
    display_name: str = ""
    multiplier: Optional[float] = None
    input_price_per_mtoken_usd: Optional[float] = None
    output_price_per_mtoken_usd: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PlanPricing:
    """1 プランの料金情報。

    - ``plan_id``: ``individual_pro`` / ``business`` / ``enterprise`` 等
    - ``display_name``: 表示名（例: ``Copilot Pro``）
    - ``monthly_usd``: プラン月額 USD
    - ``included_premium_requests``: プラン内に含まれる premium request 数
    - ``additional_request_usd``: 含有数超過後の 1 premium request あたり単価 USD
    """

    plan_id: str
    display_name: str = ""
    monthly_usd: Optional[float] = None
    included_premium_requests: Optional[int] = None
    additional_request_usd: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CopilotPricing:
    """料金表全体。``cache.save_cached_pricing`` で JSON 永続化される。

    ``models``: model_id -> ModelPricing
    ``plans``:  plan_id  -> PlanPricing
    ``fetched_at``: ISO8601 UTC 文字列
    ``source_urls``: 取得元 URL 一覧（``docs`` / ``pricing``）
    ``status``: ``"ok"`` / ``"partial"`` / ``"stale"`` / ``"unavailable"``
    """

    models: Dict[str, ModelPricing] = field(default_factory=dict)
    plans: Dict[str, PlanPricing] = field(default_factory=dict)
    fetched_at: str = ""
    source_urls: Dict[str, str] = field(default_factory=dict)
    status: str = "unavailable"
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "fetched_at": self.fetched_at,
            "source_urls": dict(self.source_urls),
            "status": self.status,
            "models": {k: v.to_dict() for k, v in self.models.items()},
            "plans": {k: v.to_dict() for k, v in self.plans.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CopilotPricing":
        models = {
            k: ModelPricing(**v) for k, v in (data.get("models") or {}).items()
        }
        plans = {
            k: PlanPricing(**v) for k, v in (data.get("plans") or {}).items()
        }
        return cls(
            models=models,
            plans=plans,
            fetched_at=str(data.get("fetched_at") or ""),
            source_urls=dict(data.get("source_urls") or {}),
            status=str(data.get("status") or "unavailable"),
            schema_version=int(data.get("schema_version") or SCHEMA_VERSION),
        )

    def get_model(self, model_id: str) -> Optional[ModelPricing]:
        """モデル ID 解決（大小無視、prefix 部分一致）。

        SDK は ``claude-sonnet-4`` を返すが docs 側は ``Claude Sonnet 4``。
        crawler 側で正規化して ``model_id`` に小文字ハイフン形式を保存する前提。
        """
        if not model_id:
            return None
        norm = model_id.strip().lower()
        if norm in self.models:
            return self.models[norm]
        # prefix 部分一致（例: "claude-sonnet-4-20250101" -> "claude-sonnet-4"）
        for k, v in self.models.items():
            if norm.startswith(k) or k.startswith(norm):
                return v
        return None


def utcnow_iso() -> str:
    """ISO8601 UTC 文字列（``2026-05-21T14:23:11+00:00``）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
