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
from typing import Dict, List, Optional

__all__ = [
    "ModelEntry",
    "ModelsAPIError",
    "fetch_models",
    "fetch_model_entries",
]


# ---------------------------------------------------------------------------
# SDK 互換パッチ
# ---------------------------------------------------------------------------
# github-copilot-sdk 0.3.0 の `ModelBilling.from_dict` は `multiplier` フィールド
# を必須としているが、現行の GitHub Copilot API の `models.list` レスポンスでは
# `billing` から `multiplier` が削除されており、代わりに `token_prices` /
# `restricted_to` を返す。このため `client.list_models()` が全モデルで
# ValueError("Missing required field 'multiplier' in ModelBilling") を投げる。
#
# 本パッチは `multiplier` が無い場合に 0.0 を補って解析を継続する。`hve` 用途では
# billing 値（multiplier）を表示・利用していないため実害は無い。SDK 側で修正版が
# 出たら本パッチは削除可能。
_SDK_PATCH_APPLIED = False


def _apply_sdk_billing_patch() -> None:
    global _SDK_PATCH_APPLIED
    if _SDK_PATCH_APPLIED:
        return
    try:
        from copilot import client as _copilot_client  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover
        return

    ModelBilling = getattr(_copilot_client, "ModelBilling", None)
    if ModelBilling is None:  # pragma: no cover
        return

    original_from_dict = ModelBilling.from_dict

    def _patched_from_dict(obj):  # type: ignore[no-untyped-def]
        if isinstance(obj, dict) and obj.get("multiplier") is None:
            patched = dict(obj)
            patched["multiplier"] = 0.0
            return original_from_dict(patched)
        return original_from_dict(obj)

    ModelBilling.from_dict = staticmethod(_patched_from_dict)  # type: ignore[assignment]
    _SDK_PATCH_APPLIED = True


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
        cache_price_usd_per_1m: キャッシュ 1M トークンあたりの USD 単価 (None = 不明)

    NOTE: token_prices の単位変換式 (GitHub Copilot models.list API 実測):
        usd_per_1m_tokens = raw_price / (batch_size * 1e5)
        例: input_price=300000000000, batch_size=1000000 → $3.00/1M (Claude Sonnet)
    SDK 0.3.0 では `ModelBilling.multiplier` が常に欠落 (=0.0 パッチ) のため
    Premium Request 倍率は提供しない。
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

    # SDK 0.3.0 互換パッチ（multiplier 必須化バグの回避）。冪等。
    _apply_sdk_billing_patch()

    client = CopilotClient()
    raw_billing_by_id: Dict[str, dict] = {}
    # GitHub Copilot サーバの models.list レスポンスは reasoning effort 候補を 2 箇所に持つ:
    #   1. トップレベル `supportedReasoningEfforts` (SDK が読む)
    #   2. `capabilities.supports.reasoning_effort` (snake_case, list)
    # claude-opus-4.7 系では (1) が ["medium"] に縮退する不具合があり、正しい一覧は (2) のみ。
    # SDK は (2) を bool 型として誤マップし list を捨てるため、ここで raw から拾って優先採用する。
    raw_supported_efforts_by_id: Dict[str, List[str]] = {}
    try:
        await client.start()
        # token_prices は SDK dataclass で破棄されるため、低レベル RPC で raw 取得して
        # billing を id でマップする。失敗しても致命ではないため握り潰し。
        try:
            low = getattr(client, "_client", None)
            if low is not None:
                raw = await low.request("models.list", {})
                raw_models = raw.get("models") if isinstance(raw, dict) else raw
                if isinstance(raw_models, list):
                    for rm in raw_models:
                        if isinstance(rm, dict):
                            rid = rm.get("id")
                            b = rm.get("billing")
                            if isinstance(rid, str) and isinstance(b, dict):
                                raw_billing_by_id[rid] = b
                            # capabilities.supports.reasoning_effort (list) を捕捉
                            if isinstance(rid, str):
                                caps = rm.get("capabilities")
                                sup = caps.get("supports") if isinstance(caps, dict) else None
                                re_list = sup.get("reasoning_effort") if isinstance(sup, dict) else None
                                if isinstance(re_list, list):
                                    cleaned = [str(x) for x in re_list if isinstance(x, str) and x]
                                    if cleaned:
                                        raw_supported_efforts_by_id[rid] = cleaned
        except Exception:
            pass
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
        # raw `capabilities.supports.reasoning_effort` を優先採用（SDK 経路がサーバ側の
        # トップレベル supportedReasoningEfforts 縮退バグ (claude-opus-4.7 系等) で
        # ["medium"] のみになるケースを救済）。
        raw_sre = raw_supported_efforts_by_id.get(str(mid))
        if raw_sre and (sre is None or len(raw_sre) > len(sre)):
            sre = raw_sre
            # raw list が存在＝サーバが reasoning effort 機能を提供している証拠
            supports_re = True

        # token_prices: raw RPC からモデル ID で引いて USD/1M tokens に変換
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
        b = raw_billing_by_id.get(str(mid))
        if isinstance(b, dict):
            tp = b.get("token_prices")
            if isinstance(tp, dict):
                batch = tp.get("batch_size")
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
                    in_price = _conv(tp.get("input_price"))
                    out_price = _conv(tp.get("output_price"))
                    cache_price = _conv(tp.get("cache_price"))

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
