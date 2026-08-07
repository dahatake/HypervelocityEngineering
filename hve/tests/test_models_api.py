"""tests/test_models_api.py — hve.models_api のユニットテスト"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from hve.models_api import (
    ModelEntry,
    ModelsAPIError,
    fetch_model_entries,
    fetch_models,
)


def _make_model(
    id_: str,
    name: str = "",
    default_effort: str | None = None,
    *,
    supported_efforts: list[str] | None = None,
    supports_reasoning_effort: bool = False,
    max_context_window_tokens: int | None = None,
    batch_size: int | None = None,
    input_price: float | None = None,
    output_price: float | None = None,
    cache_read_price: float | None = None,
):
    m = MagicMock()
    m.id = id_
    m.name = name or id_
    m.default_reasoning_effort = default_effort
    m.supported_reasoning_efforts = supported_efforts
    # capabilities.supports.reasoning_effort / capabilities.limits.max_context_window_tokens
    caps = MagicMock()
    caps.supports = MagicMock()
    caps.supports.reasoning_effort = supports_reasoning_effort
    caps.limits = MagicMock()
    caps.limits.max_context_window_tokens = max_context_window_tokens
    m.capabilities = caps
    # billing.token_prices は ModelInfo.billing が Optional なため、指定時のみ組み立てる
    if batch_size is None:
        m.billing = None
    else:
        token_prices = MagicMock()
        token_prices.batch_size = batch_size
        token_prices.input_price = input_price
        token_prices.output_price = output_price
        token_prices.cache_read_price = cache_read_price
        billing = MagicMock()
        billing.token_prices = token_prices
        m.billing = billing
    return m


def _make_fake_client(*, models=None, start_raises=None, list_raises=None):
    client = MagicMock()

    async def _start():
        if start_raises:
            raise start_raises

    async def _stop():
        return None

    async def _list_models():
        if list_raises:
            raise list_raises
        return models or []

    client.start = _start
    client.stop = _stop
    client.list_models = _list_models
    return client


# =====================================================================
# fetch_model_entries
# =====================================================================


class TestFetchModelEntries:
    def test_basic(self):
        fake = _make_fake_client(
            models=[
                _make_model("claude-opus-4.7", "Claude Opus 4.7", "high"),
                _make_model("gpt-5.5", "GPT 5.5"),
            ]
        )
        with patch("copilot.CopilotClient", return_value=fake):
            entries = fetch_model_entries(timeout=5.0)
        assert len(entries) == 2
        assert entries[0].id == "claude-opus-4.7"
        assert entries[0].name == "Claude Opus 4.7"
        assert entries[0].default_reasoning_effort == "high"
        assert entries[1].id == "gpt-5.5"

    def test_extracts_effort_and_context(self):
        """SDK ModelInfo の capabilities / supported_reasoning_efforts を ModelEntry に抽出する。"""
        fake = _make_fake_client(
            models=[
                _make_model(
                    "claude-opus-4.7",
                    "Claude Opus 4.7",
                    "medium",
                    supported_efforts=["low", "medium", "high"],
                    supports_reasoning_effort=True,
                    max_context_window_tokens=200000,
                ),
            ]
        )
        with patch("copilot.CopilotClient", return_value=fake):
            entries = fetch_model_entries(timeout=5.0)
        e = entries[0]
        assert e.supported_reasoning_efforts == ["low", "medium", "high"]
        assert e.supports_reasoning_effort is True
        assert e.max_context_window_tokens == 200000
        assert e.default_reasoning_effort == "medium"

    def test_empty_supported_efforts_becomes_none(self):
        fake = _make_fake_client(
            models=[_make_model("m1", supported_efforts=[])]
        )
        with patch("copilot.CopilotClient", return_value=fake):
            entries = fetch_model_entries(timeout=5.0)
        assert entries[0].supported_reasoning_efforts is None

    def test_empty_list(self):
        fake = _make_fake_client(models=[])
        with patch("copilot.CopilotClient", return_value=fake):
            assert fetch_model_entries(timeout=5.0) == []

    def test_models_without_id_are_skipped(self):
        m_bad = MagicMock()
        m_bad.id = ""
        m_good = _make_model("ok-1")
        fake = _make_fake_client(models=[m_bad, m_good])
        with patch("copilot.CopilotClient", return_value=fake):
            entries = fetch_model_entries(timeout=5.0)
        assert [e.id for e in entries] == ["ok-1"]

    def test_name_fallbacks_to_id(self):
        m = MagicMock()
        m.id = "only-id"
        m.name = ""
        m.default_reasoning_effort = None
        m.supported_reasoning_efforts = None
        m.capabilities = None
        fake = _make_fake_client(models=[m])
        with patch("copilot.CopilotClient", return_value=fake):
            entries = fetch_model_entries(timeout=5.0)
        assert entries[0].name == "only-id"

    def test_extracts_price_from_public_billing_field(self):
        """SDK が公開する ModelInfo.billing.token_prices から USD/1M 価格を算出する。"""
        fake = _make_fake_client(
            models=[
                _make_model(
                    "claude-sonnet-4.6",
                    batch_size=1_000_000,
                    input_price=300_000_000_000.0,
                    output_price=1_500_000_000_000.0,
                    cache_read_price=30_000_000_000.0,
                ),
            ]
        )
        with patch("copilot.CopilotClient", return_value=fake):
            entries = fetch_model_entries(timeout=5.0)
        e = entries[0]
        assert e.input_price_usd_per_1m == pytest.approx(3.00)
        assert e.output_price_usd_per_1m == pytest.approx(15.00)
        assert e.cache_price_usd_per_1m == pytest.approx(0.30)

    def test_billing_none_leaves_prices_none(self):
        """ModelInfo.billing が None のモデルは価格 None のままエラーにならない。"""
        fake = _make_fake_client(models=[_make_model("m1")])
        with patch("copilot.CopilotClient", return_value=fake):
            entries = fetch_model_entries(timeout=5.0)
        assert entries[0].input_price_usd_per_1m is None
        assert entries[0].output_price_usd_per_1m is None
        assert entries[0].cache_price_usd_per_1m is None

    def test_list_models_failure_raises(self):
        fake = _make_fake_client(list_raises=RuntimeError("boom"))
        with patch("copilot.CopilotClient", return_value=fake):
            with pytest.raises(ModelsAPIError) as exc_info:
                fetch_model_entries(timeout=5.0)
        assert "boom" in str(exc_info.value)

    def test_start_failure_raises(self):
        fake = _make_fake_client(start_raises=RuntimeError("no-auth"))
        with patch("copilot.CopilotClient", return_value=fake):
            with pytest.raises(ModelsAPIError):
                fetch_model_entries(timeout=5.0)

    def test_timeout_raises(self):
        async def _hang():
            await asyncio.sleep(10)

        async def _noop():
            return None

        fake = MagicMock()
        fake.start = _hang
        fake.stop = _noop
        fake.list_models = _noop
        with patch("copilot.CopilotClient", return_value=fake):
            with pytest.raises(ModelsAPIError) as exc_info:
                fetch_model_entries(timeout=0.1)
        assert "timeout" in str(exc_info.value).lower()


# =====================================================================
# fetch_models
# =====================================================================


class TestFetchModels:
    def test_returns_only_ids(self):
        fake = _make_fake_client(
            models=[_make_model("a"), _make_model("b"), _make_model("c")]
        )
        with patch("copilot.CopilotClient", return_value=fake):
            assert fetch_models(timeout=5.0) == ["a", "b", "c"]


# =====================================================================
# ModelEntry
# =====================================================================


class TestModelEntry:
    def test_frozen(self):
        e = ModelEntry(id="x", name="X")
        with pytest.raises(Exception):
            e.id = "y"  # type: ignore[misc]


# =====================================================================
# SDK 0.3.0 互換パッチ削除の安全性（回帰ガード）
# =====================================================================


class TestModelBillingCompat:
    """installed SDK の ModelBilling.from_dict が multiplier 欠落を許容することを確認する。

    hve.models_api は SDK 0.3.0 時代の multiplier 必須化バグ回避パッチを持っていたが、
    現行 SDK では multiplier 欠落時も例外を投げないため不要。将来 SDK がこの挙動を
    再び壊した場合に検知できるよう、SDK 自体の振る舞いを直接固定する。
    """

    def test_sdk_model_billing_tolerates_missing_multiplier(self):
        from copilot.client import ModelBilling

        billing = ModelBilling.from_dict(
            {"tokenPrices": {"batchSize": 1_000_000, "inputPrice": 300_000_000_000.0}}
        )
        assert billing.multiplier is None
        assert billing.token_prices is not None
        assert billing.token_prices.input_price == 300_000_000_000.0
