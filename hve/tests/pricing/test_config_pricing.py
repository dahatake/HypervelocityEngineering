"""hve.config.SDKConfig.from_env のうち pricing 関連フィールドのテスト。"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def fresh_config(monkeypatch):
    """環境変数を一旦クリアしてから SDKConfig をインポート＆再ロードする。"""
    for key in (
        "HVE_USD_JPY_RATE",
        "HVE_PRICING_CURRENCY",
        "HVE_PRICING_AUTO_REFRESH",
        "HVE_PRICING_STATUSLINE_ENABLED",
        "HVE_NO_STATUSLINE",
        "HVE_PRICING_PLAN_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    import hve.config as cfg

    importlib.reload(cfg)
    return cfg


def test_pricing_defaults(fresh_config) -> None:
    c = fresh_config.SDKConfig.from_env()
    assert c.pricing_usd_jpy_rate == 150.0
    assert c.pricing_currency == "auto"
    assert c.pricing_auto_refresh is True
    assert c.pricing_statusline_enabled is True
    assert c.pricing_plan_id == ""


def test_pricing_env_overrides(monkeypatch, fresh_config) -> None:
    monkeypatch.setenv("HVE_USD_JPY_RATE", "155.5")
    monkeypatch.setenv("HVE_PRICING_CURRENCY", "JPY")
    monkeypatch.setenv("HVE_PRICING_AUTO_REFRESH", "false")
    monkeypatch.setenv("HVE_PRICING_PLAN_ID", "copilot_business")
    c = fresh_config.SDKConfig.from_env()
    assert c.pricing_usd_jpy_rate == 155.5
    assert c.pricing_currency == "jpy"
    assert c.pricing_auto_refresh is False
    assert c.pricing_plan_id == "copilot_business"


def test_no_statusline_env_disables(monkeypatch, fresh_config) -> None:
    monkeypatch.setenv("HVE_NO_STATUSLINE", "1")
    c = fresh_config.SDKConfig.from_env()
    assert c.pricing_statusline_enabled is False


def test_statusline_env_explicit_off(monkeypatch, fresh_config) -> None:
    monkeypatch.setenv("HVE_PRICING_STATUSLINE_ENABLED", "false")
    c = fresh_config.SDKConfig.from_env()
    assert c.pricing_statusline_enabled is False
