"""hve.pricing.crawler — GitHub Copilot 料金表のクロール。

ソース:
- ``docs.github.com`` の "About billing for GitHub Copilot" → モデル別 multiplier 表
- ``github.com/pricing`` → プラン別月額 / premium request 含有数 / 超過単価

両方とも HTML テーブル / 構造化テキストから正規表現で抽出する。失敗時は
``PricingFetchError`` を raise する（呼び出し側で旧キャッシュ継続使用を判断）。

捏造禁止: パース不能な行は ``None`` のまま保持する。
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from urllib import request as urllib_request
from urllib.error import URLError

from hve.pricing.models import (
    CopilotPricing,
    ModelPricing,
    PlanPricing,
    utcnow_iso,
)

logger = logging.getLogger(__name__)

DOCS_URL = (
    "https://docs.github.com/en/copilot/managing-copilot/"
    "managing-copilot-as-an-individual-subscriber/"
    "about-billing-for-github-copilot"
)
PRICING_URL = "https://github.com/pricing"

DEFAULT_TIMEOUT_SEC = 5.0
USER_AGENT = "hve-pricing-crawler/1.0 (+https://github.com/)"


class PricingFetchError(Exception):
    """料金表取得失敗。"""


def _http_get(url: str, timeout: float = DEFAULT_TIMEOUT_SEC) -> str:
    req = urllib_request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:  # nosec: B310 - https only
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except (URLError, TimeoutError, OSError) as e:
        raise PricingFetchError(f"HTTP GET failed: {url}: {e}") from e


# ---------------------------------------------------------------------------
# モデル正規化
# ---------------------------------------------------------------------------

_MODEL_ID_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize_model_id(display_name: str) -> str:
    """``Claude Sonnet 4`` -> ``claude-sonnet-4``。"""
    s = display_name.strip().lower()
    s = _MODEL_ID_NORMALIZE_RE.sub("-", s)
    return s.strip("-")


# ---------------------------------------------------------------------------
# docs.github.com: multiplier 表抽出
# ---------------------------------------------------------------------------

class _MultiplierTableParser(HTMLParser):
    """``<table>`` 内の ``Model`` / ``Multiplier`` 列を抽出する簡易パーサ。

    GitHub docs の料金表は ``<table>`` ベース。``<th>Model</th>`` / ``<th>Multiplier</th>``
    を持つテーブルを検出し、対応する ``<td>`` を抽出する。
    """

    def __init__(self) -> None:
        super().__init__()
        self._in_table = False
        self._in_thead = False
        self._in_row = False
        self._in_cell = False
        self._cell_text: List[str] = []
        self._row_cells: List[str] = []
        self._headers: List[str] = []
        self._has_target_table = False
        self.rows: List[List[str]] = []
        self.header: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag == "table":
            self._in_table = True
            self._headers = []
            self._has_target_table = False
            self.rows_buffer: List[List[str]] = []
        elif self._in_table and tag in ("th", "td"):
            self._in_cell = True
            self._cell_text = []
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._row_cells = []

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag == "table":
            if self._has_target_table:
                # ヘッダと行データを永続化（複数 table がある場合は最初の該当のみ採用）
                if not self.rows:
                    self.header = list(self._headers)
                    self.rows = list(getattr(self, "rows_buffer", []))
            self._in_table = False
            self._headers = []
        elif tag in ("th", "td") and self._in_cell:
            text = "".join(self._cell_text).strip()
            self._row_cells.append(text)
            if tag == "th":
                self._headers.append(text)
            self._in_cell = False
            self._cell_text = []
        elif tag == "tr" and self._in_row:
            # th 専用行はヘッダ確定タイミング
            normalized_headers = [h.lower() for h in self._headers]
            if (
                "model" in normalized_headers
                and any("multiplier" in h for h in normalized_headers)
            ):
                self._has_target_table = True
            if self._has_target_table and self._row_cells and not all(
                c == "" for c in self._row_cells
            ):
                # td 行のみ採用（th 行は同じ row_cells に入っているがヘッダと一致するので除外）
                if self._row_cells != self._headers:
                    self.rows_buffer.append(list(self._row_cells))
            self._in_row = False
            self._row_cells = []

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._in_cell:
            self._cell_text.append(data)


_MULTIPLIER_VALUE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[x×]", re.IGNORECASE)


def parse_docs_multipliers(html: str) -> Dict[str, ModelPricing]:
    """docs.github.com HTML から model_id -> ModelPricing(multiplier) を抽出。"""
    parser = _MultiplierTableParser()
    try:
        parser.feed(html)
    except Exception as e:  # HTMLParser 自体は緩いが念のため
        logger.warning("parse_docs_multipliers: HTMLParser raised: %s", e)
        return {}

    if not parser.header or not parser.rows:
        return {}

    headers_lower = [h.lower() for h in parser.header]
    try:
        model_idx = headers_lower.index("model")
    except ValueError:
        return {}
    multiplier_idx = next(
        (i for i, h in enumerate(headers_lower) if "multiplier" in h), None
    )
    if multiplier_idx is None:
        return {}

    out: Dict[str, ModelPricing] = {}
    for row in parser.rows:
        if len(row) <= max(model_idx, multiplier_idx):
            continue
        display = row[model_idx].strip()
        mult_raw = row[multiplier_idx].strip()
        if not display:
            continue
        m = _MULTIPLIER_VALUE_RE.search(mult_raw)
        multiplier = float(m.group(1)) if m else None
        model_id = _normalize_model_id(display)
        if not model_id:
            continue
        out[model_id] = ModelPricing(
            model_id=model_id,
            display_name=display,
            multiplier=multiplier,
        )
    return out


# ---------------------------------------------------------------------------
# github.com/pricing: プラン情報抽出
# ---------------------------------------------------------------------------

# 注意: github.com/pricing は JS レンダリングを多用しているため、ここで
# 安定して取れるのは「monthly_usd」と「included_premium_requests」の概算。
# 取れなかったフィールドは None のまま残し、calculator 側で fallback する。

_PLAN_BLOCK_RE = re.compile(
    # 「Copilot Pro+」を「Copilot Pro」より優先するため Pro\+ を Pro より先に並べる
    r"(?P<name>Copilot\s+(?:Free|Pro\+|Pro|Business|Enterprise))"
    r"[\s\S]{0,400}?"
    r"\$(?P<price>\d+(?:\.\d+)?)\s*(?:USD\s*)?"
    # "/ month" / "/month" / "per month" / "per user / month" / "per user/month" 全部対応
    r"(?:(?:per\s+user\s*)?(?:/\s*|per\s+)month)",
    re.IGNORECASE,
)

_INCLUDED_REQUESTS_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})*|\d+)\s*premium\s+requests?", re.IGNORECASE
)

_ADDITIONAL_REQUEST_RE = re.compile(
    r"\$(\d+(?:\.\d+)?)\s*(?:USD\s*)?(?:per\s+|/\s*)additional\s+premium\s+request",
    re.IGNORECASE,
)

# fallback: 公開情報として広く知られる "Additional premium requests cost $0.04 each"
_FALLBACK_ADDITIONAL_USD = 0.04


def _normalize_plan_id(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = s.replace("+", "_plus").replace("/", "_")
    s = re.sub(r"[^a-z0-9_]+", "", s)
    return s


def parse_pricing_plans(html: str) -> Dict[str, PlanPricing]:
    """github.com/pricing HTML からプラン情報を抽出。"""
    # HTML タグを大雑把に剥がしてプレーンテキスト化（精密抽出は不要）
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)

    out: Dict[str, PlanPricing] = {}
    for m in _PLAN_BLOCK_RE.finditer(text):
        name = m.group("name")
        price = float(m.group("price"))
        plan_id = _normalize_plan_id(name)
        # 同 plan_id が複数ヒットしたら最初の 1 件のみ採用
        if plan_id in out:
            continue
        # 近傍 800 文字内で included premium requests を探索
        window_start = max(0, m.start() - 200)
        window_end = min(len(text), m.end() + 800)
        window = text[window_start:window_end]
        inc_m = _INCLUDED_REQUESTS_RE.search(window)
        included = (
            int(inc_m.group(1).replace(",", "")) if inc_m else None
        )
        add_m = _ADDITIONAL_REQUEST_RE.search(window)
        additional = float(add_m.group(1)) if add_m else _FALLBACK_ADDITIONAL_USD
        out[plan_id] = PlanPricing(
            plan_id=plan_id,
            display_name=name,
            monthly_usd=price,
            included_premium_requests=included,
            additional_request_usd=additional,
        )
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_copilot_pricing(
    *,
    docs_url: str = DOCS_URL,
    pricing_url: str = PRICING_URL,
    timeout: float = DEFAULT_TIMEOUT_SEC,
) -> CopilotPricing:
    """料金表を取得して ``CopilotPricing`` を返す。

    どちらか一方が失敗してももう一方は採用し、``status="partial"`` とする。
    両方失敗時は ``PricingFetchError`` を raise する。
    """
    models: Dict[str, ModelPricing] = {}
    plans: Dict[str, PlanPricing] = {}
    sources: Dict[str, str] = {}
    errors: List[str] = []

    try:
        docs_html = _http_get(docs_url, timeout=timeout)
        models = parse_docs_multipliers(docs_html)
        sources["docs"] = docs_url
        if not models:
            errors.append("docs: 0 models parsed")
    except PricingFetchError as e:
        errors.append(f"docs: {e}")

    try:
        pricing_html = _http_get(pricing_url, timeout=timeout)
        plans = parse_pricing_plans(pricing_html)
        sources["pricing"] = pricing_url
        if not plans:
            errors.append("pricing: 0 plans parsed")
    except PricingFetchError as e:
        errors.append(f"pricing: {e}")

    if not models and not plans:
        raise PricingFetchError(
            "両ソース取得失敗: " + " / ".join(errors)
        )

    status = "ok" if (models and plans) else "partial"
    return CopilotPricing(
        models=models,
        plans=plans,
        fetched_at=utcnow_iso(),
        source_urls=sources,
        status=status,
    )


__all__ = [
    "PricingFetchError",
    "DOCS_URL",
    "PRICING_URL",
    "fetch_copilot_pricing",
    "parse_docs_multipliers",
    "parse_pricing_plans",
]
