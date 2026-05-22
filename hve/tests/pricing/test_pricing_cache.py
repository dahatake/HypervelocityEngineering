"""hve.pricing.cache のテスト。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from hve.pricing.cache import (
    load_cached_pricing,
    save_cached_pricing,
    should_refresh,
)
from hve.pricing.models import CopilotPricing, ModelPricing


def _make_pricing(fetched_at: str = "2026-05-01T00:00:00+00:00") -> CopilotPricing:
    return CopilotPricing(
        models={"x": ModelPricing(model_id="x", multiplier=1.0)},
        fetched_at=fetched_at,
        status="ok",
    )


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "sub" / "copilot-pricing.json"
    pricing = _make_pricing()
    assert save_cached_pricing(pricing, p) is True
    loaded = load_cached_pricing(p)
    assert loaded is not None
    assert loaded.status == "ok"
    assert "x" in loaded.models


def test_load_missing_returns_none(tmp_path: Path) -> None:
    assert load_cached_pricing(tmp_path / "nope.json") is None


def test_load_broken_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "broken.json"
    p.write_text("{ broken json", encoding="utf-8")
    assert load_cached_pricing(p) is None


def test_should_refresh_when_none() -> None:
    assert should_refresh(None) is True


def test_should_refresh_when_same_month() -> None:
    pricing = _make_pricing("2026-05-15T10:00:00+00:00")
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    assert should_refresh(pricing, now=now) is False


def test_should_refresh_when_prev_month() -> None:
    pricing = _make_pricing("2026-04-30T23:59:59+00:00")
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    assert should_refresh(pricing, now=now) is True


def test_should_refresh_when_fetched_at_broken() -> None:
    pricing = _make_pricing("not-a-date")
    assert should_refresh(pricing) is True
