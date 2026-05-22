"""hve.pricing.cache — ``~/.hve/pricing/copilot-pricing.json`` の永続化。

- load/save は atomic（temp → os.replace）
- ``should_refresh(now)`` で「キャッシュ最終更新月が ``now`` の月より前か」を判定
- 失敗時は WARN ログのみで例外を伝搬しない（呼び出し側は ``None`` を受け取る）
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from hve.pricing.models import CopilotPricing, SCHEMA_VERSION

logger = logging.getLogger(__name__)

DEFAULT_DIRNAME = ".hve"
DEFAULT_SUBDIR = "pricing"
DEFAULT_FILENAME = "copilot-pricing.json"


def default_cache_path() -> Path:
    """``~/.hve/pricing/copilot-pricing.json``。

    ``HVE_PRICING_CACHE_PATH`` 環境変数で上書き可能。
    """
    override = os.environ.get("HVE_PRICING_CACHE_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / DEFAULT_DIRNAME / DEFAULT_SUBDIR / DEFAULT_FILENAME


def load_cached_pricing(path: Optional[Path] = None) -> Optional[CopilotPricing]:
    """キャッシュ JSON を読み込む。存在しない / 破損時は ``None``。"""
    p = path or default_cache_path()
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("load_cached_pricing failed: %s: %s", p, e)
        return None
    if int(data.get("schema_version") or 0) > SCHEMA_VERSION:
        logger.warning(
            "load_cached_pricing: schema_version=%s is newer than supported %s",
            data.get("schema_version"),
            SCHEMA_VERSION,
        )
        return None
    try:
        return CopilotPricing.from_dict(data)
    except (TypeError, ValueError) as e:
        logger.warning("load_cached_pricing: parse failed: %s", e)
        return None


def save_cached_pricing(
    pricing: CopilotPricing, path: Optional[Path] = None
) -> bool:
    """キャッシュ JSON を atomic 保存する。成否を bool で返す。"""
    p = path or default_cache_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(p.parent),
            delete=False,
            prefix=".pricing-",
            suffix=".tmp",
        ) as tmp:
            json.dump(pricing.to_dict(), tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = tmp.name
        os.replace(tmp_path, p)
        return True
    except OSError as e:
        logger.warning("save_cached_pricing failed: %s: %s", p, e)
        return False


def should_refresh(
    pricing: Optional[CopilotPricing], now: Optional[datetime] = None
) -> bool:
    """月初自動更新の判定。

    - キャッシュ未取得 (``None``) → True
    - ``fetched_at`` が解釈できない → True
    - ``fetched_at`` の (年, 月) が ``now`` の (年, 月) と異なる → True
    """
    if pricing is None or not pricing.fetched_at:
        return True
    now = now or datetime.now(timezone.utc)
    try:
        fetched = datetime.fromisoformat(pricing.fetched_at)
    except ValueError:
        return True
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return (fetched.year, fetched.month) != (now.year, now.month)


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------


class PricingCache:
    """キャッシュへの読み書きとリフレッシュ判定をまとめた薄いラッパ。"""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or default_cache_path()
        self._cached: Optional[CopilotPricing] = None
        self._loaded = False

    def load(self) -> Optional[CopilotPricing]:
        if not self._loaded:
            self._cached = load_cached_pricing(self.path)
            self._loaded = True
        return self._cached

    def save(self, pricing: CopilotPricing) -> bool:
        ok = save_cached_pricing(pricing, self.path)
        if ok:
            self._cached = pricing
            self._loaded = True
        return ok

    def should_refresh(self, now: Optional[datetime] = None) -> bool:
        return should_refresh(self.load(), now=now)


__all__ = [
    "PricingCache",
    "default_cache_path",
    "load_cached_pricing",
    "save_cached_pricing",
    "should_refresh",
]
