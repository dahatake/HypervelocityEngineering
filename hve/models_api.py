"""models_api.py — GitHub Copilot 利用可能モデル一覧取得

`github-copilot-sdk` の `CopilotClient.list_models()` を同期ラップし、モデル ID
のリストを返す。HTTP 直叩きは行わず、SDK 経由で取得する (SDK 内部キャッシュも
自動で機能する)。

詳細仕様 (Phase 0 findings):
    - `client.list_models()` は `list[ModelInfo]` を返す。
    - `ModelInfo.id` がモデル ID (例: "claude-opus-4.7"), `ModelInfo.name` は表示名。
    - 認証必須。未認証時は SDK 側で例外送出。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from dataclasses import dataclass
from typing import List, Optional

__all__ = [
    "ModelEntry",
    "ModelsAPIError",
    "fetch_models",
    "fetch_model_entries",
]


@dataclass(frozen=True)
class ModelEntry:
    """SDK ModelInfo から必要項目を抽出した不変データ。

    Fields:
        id: モデル ID (例: "claude-opus-4.7")
        name: 表示名
        default_reasoning_effort: SDK が返す既定 reasoning effort 値 (例: "medium")
        supported_reasoning_efforts: モデルがサポートする effort 値の選択肢リスト
        supports_reasoning_effort: モデルが reasoning effort 機能をサポートするか
        max_context_window_tokens: コンテキストウィンドウの上限トークン数 (SDK 上限)
        input_price_usd_per_1m: 入力 1M トークンあたりの USD 単価 (None = 不明)
        output_price_usd_per_1m: 出力 1M トークンあたりの USD 単価 (None = 不明)
        cache_price_usd_per_1m: キャッシュ 1M トークンあたりの USD 単価 (None = 不明)。
            SDK 上の非推奨フィールド `cache_price` ではなく `cache_read_price` から算出する。

    NOTE: token_prices の単位変換式 (GitHub Copilot models.list API 実測):
        usd_per_1m_tokens = raw_price / (batch_size * 1e5)
        例: input_price=300000000000, batch_size=1000000 → $3.00/1M (Claude Sonnet)
    """

    id: str
    name: str
    default_reasoning_effort: Optional[str] = None
    supported_reasoning_efforts: Optional[List[str]] = None
    supports_reasoning_effort: bool = False
    max_context_window_tokens: Optional[int] = None
    input_price_usd_per_1m: Optional[float] = None
    output_price_usd_per_1m: Optional[float] = None
    cache_price_usd_per_1m: Optional[float] = None


class ModelsAPIError(Exception):
    """モデル一覧取得失敗時の例外。"""


# ---------------------------------------------------------------------------
# 内部 async 実装
# ---------------------------------------------------------------------------


async def _fetch_model_entries_async() -> List[ModelEntry]:
    try:
        from copilot import CopilotClient  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover
        raise ModelsAPIError(f"github-copilot-sdk が import できません: {e}") from e

    client = CopilotClient()
    try:
        await client.start()
        try:
            models = await client.list_models()
        except Exception as e:
            # SDK 内のパース失敗（例: ModelBilling.multiplier 欠落）等に備え、
            # HVE_DEBUG_MODELS=1 のときのみ低レベル RPC で生レスポンスを取得しダンプする。
            # 既存挙動を変えず、原因特定のためのデバッグ情報のみ追加。
            if os.environ.get("HVE_DEBUG_MODELS"):
                sys.stderr.write(
                    "[HVE_DEBUG_MODELS] list_models 失敗。低レベル RPC で生レスポンス取得を試行します。\n"
                )
                sys.stderr.write(traceback.format_exc())
                try:
                    low = getattr(client, "_client", None)
                    if low is not None:
                        raw = await low.request("models.list", {})
                        sys.stderr.write(
                            "[HVE_DEBUG_MODELS] models.list raw response:\n"
                            + json.dumps(raw, ensure_ascii=False, indent=2, default=str)
                            + "\n"
                        )
                    else:
                        sys.stderr.write(
                            "[HVE_DEBUG_MODELS] client._client が None のため低レベル RPC 不可。\n"
                        )
                except Exception as dbg_e:  # pragma: no cover
                    sys.stderr.write(
                        f"[HVE_DEBUG_MODELS] 低レベル RPC でも失敗: {type(dbg_e).__name__}: {dbg_e}\n"
                    )
            raise ModelsAPIError(f"list_models 失敗: {type(e).__name__}: {e}") from e
    except ModelsAPIError:
        raise
    except Exception as e:
        raise ModelsAPIError(f"list_models 失敗: {type(e).__name__}: {e}") from e
    finally:
        try:
            await client.stop()
        except Exception:
            pass

    entries: List[ModelEntry] = []
    for m in models or []:
        mid = getattr(m, "id", None)
        if not mid:
            continue
        # capabilities.supports.reasoning_effort / capabilities.limits.max_context_window_tokens
        supports_re = False
        max_ctx: Optional[int] = None
        caps = getattr(m, "capabilities", None)
        if caps is not None:
            sup = getattr(caps, "supports", None)
            if sup is not None:
                supports_re = bool(getattr(sup, "reasoning_effort", False))
            lim = getattr(caps, "limits", None)
            if lim is not None:
                _mctx = getattr(lim, "max_context_window_tokens", None)
                if isinstance(_mctx, int):
                    max_ctx = _mctx
        sre_raw = getattr(m, "supported_reasoning_efforts", None)
        sre: Optional[List[str]] = None
        if isinstance(sre_raw, list):
            sre = [str(x) for x in sre_raw if isinstance(x, str) and x]
            if not sre:
                sre = None

        # token_prices: 公開 ModelInfo.billing.token_prices から USD/1M tokens に変換
        # 単位の根拠（実測クロスチェック済み）:
        #   - Claude Sonnet 4.6: input_price=3e11, batch_size=1e6 → $3.00/1M
        #   - Claude Opus 4.7:   input_price=5e11, batch_size=1e6 → $5.00/1M
        #   - Claude Haiku 4.5:  input_price=1e11, batch_size=1e6 → $1.00/1M
        # を公開価格と照合して一致を確認。API の raw 価格単位は 1e-11 USD/トークンと推定されるため
        # 1M tokens あたりドル換算係数 = 1e-11 * 1e6 = 1e-5 → raw / (batch_size * 1e5)
        _GH_PRICE_TO_USD_PER_1M = 1e5  # named constant for clarity
        in_price: Optional[float] = None
        out_price: Optional[float] = None
        cache_price: Optional[float] = None
        billing = getattr(m, "billing", None)
        tp = getattr(billing, "token_prices", None) if billing is not None else None
        if tp is not None:
            batch = getattr(tp, "batch_size", None)
            if isinstance(batch, int) and not isinstance(batch, bool) and batch > 0:
                def _conv(v):
                    # bool は int サブクラスのため明示除外
                    if (
                        isinstance(v, (int, float))
                        and not isinstance(v, bool)
                        and v >= 0
                    ):
                        return float(v) / (float(batch) * _GH_PRICE_TO_USD_PER_1M)
                    return None
                in_price = _conv(getattr(tp, "input_price", None))
                out_price = _conv(getattr(tp, "output_price", None))
                # cache_price は SDK で deprecated（cache_read_price へ移行済み）のため、後者を参照する
                cache_price = _conv(getattr(tp, "cache_read_price", None))

        entries.append(
            ModelEntry(
                id=str(mid),
                name=str(getattr(m, "name", mid) or mid),
                default_reasoning_effort=getattr(m, "default_reasoning_effort", None),
                supported_reasoning_efforts=sre,
                supports_reasoning_effort=supports_re,
                max_context_window_tokens=max_ctx,
                input_price_usd_per_1m=in_price,
                output_price_usd_per_1m=out_price,
                cache_price_usd_per_1m=cache_price,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# 公開同期 API
# ---------------------------------------------------------------------------


def fetch_model_entries(timeout: float = 30.0) -> List[ModelEntry]:
    """モデル一覧を同期取得し、ModelEntry のリストを返す。

    Raises:
        ModelsAPIError: SDK 起動失敗・認証エラー・タイムアウト等。
    """
    try:
        return asyncio.run(
            asyncio.wait_for(_fetch_model_entries_async(), timeout=timeout)
        )
    except asyncio.TimeoutError as e:
        raise ModelsAPIError(f"timeout after {timeout}s") from e
    except ModelsAPIError:
        raise
    except Exception as e:
        raise ModelsAPIError(f"{type(e).__name__}: {e}") from e


def fetch_models(timeout: float = 30.0) -> List[str]:
    """モデル ID のリストのみを返す薄いラッパー。"""
    return [e.id for e in fetch_model_entries(timeout=timeout)]
