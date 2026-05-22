"""models_cache.py — モデル一覧の永続キャッシュ

JSON ファイルとして OS 標準キャッシュディレクトリに保存。

  - 保存場所: platformdirs.user_cache_dir("hve") / "models.json"
                  例 (Windows): %LOCALAPPDATA%\\hve\\Cache\\hve\\models.json
                  例 (macOS):   ~/Library/Caches/hve/models.json
                  例 (Linux):   ~/.cache/hve/models.json
  - TTL: デフォルト 24 時間 (引数で変更可)。
  - stale 復元: TTL 切れでも `load(allow_stale=True)` で取得可能。
  - 破損ファイルは欠落と同等扱い (例外を投げず None)。

ファイル形式:
    {
        "version": 1,
        "fetched_at": <epoch seconds, float>,
        "models": ["id1", "id2", ...]
    }
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .models_api import ModelEntry

__all__ = [
    "CACHE_VERSION",
    "DEFAULT_TTL_SECONDS",
    "CachedModels",
    "get_cache_path",
    "load",
    "save",
    "save_entries",
    "clear",
    "is_fresh",
]


CACHE_VERSION: int = 2
DEFAULT_TTL_SECONDS: int = 24 * 60 * 60  # 24h


@dataclass(frozen=True)
class CachedModels:
    """ロード済みキャッシュの不変表現。

    v1 キャッシュを読んだ場合は `entries` は空リスト。
    v2 キャッシュは `entries` と `models` (互換用 ID リスト) の両方を保持。
    """

    models: List[str]
    fetched_at: float
    entries: List[ModelEntry] = field(default_factory=list)

    def age_seconds(self, *, now: Optional[float] = None) -> float:
        return (now if now is not None else time.time()) - self.fetched_at


# ---------------------------------------------------------------------------
# パス解決
# ---------------------------------------------------------------------------


def get_cache_path() -> Path:
    """キャッシュファイルの絶対パスを返す。

    環境変数 HVE_MODELS_CACHE_PATH があれば優先 (テスト・上級ユーザー用)。
    """
    override = os.environ.get("HVE_MODELS_CACHE_PATH")
    if override:
        return Path(override)

    from platformdirs import user_cache_dir

    return Path(user_cache_dir("hve", appauthor=False)) / "models.json"


# ---------------------------------------------------------------------------
# 鮮度判定
# ---------------------------------------------------------------------------


def is_fresh(
    cached: CachedModels,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """キャッシュが TTL 内か判定する。"""
    return cached.age_seconds(now=now) < ttl_seconds


# ---------------------------------------------------------------------------
# ロード
# ---------------------------------------------------------------------------


def load(
    path: Optional[Path] = None,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    allow_stale: bool = False,
    now: Optional[float] = None,
) -> Optional[CachedModels]:
    """キャッシュをロードする。

    Args:
        path: キャッシュファイルパス。None なら get_cache_path()。
        ttl_seconds: 有効期限秒。
        allow_stale: True なら TTL 切れでも返す。
        now: 現在時刻 (テスト用)。

    Returns:
        CachedModels または None (ファイル無し / 破損 / TTL 切れ&allow_stale=False)。
    """
    target = path or get_cache_path()
    if not target.is_file():
        return None

    try:
        raw = target.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        version = data.get("version")
        if version not in (1, 2):
            return None
        fetched_at = data.get("fetched_at")
        if not isinstance(fetched_at, (int, float)):
            return None

        entries: List[ModelEntry] = []
        models_list: List[str] = []

        if version == 2:
            raw_entries = data.get("entries")
            if not isinstance(raw_entries, list):
                return None
            for e in raw_entries:
                if not isinstance(e, dict):
                    continue
                eid = e.get("id")
                if not isinstance(eid, str) or not eid:
                    continue
                name = e.get("name") or eid
                sre = e.get("supported_reasoning_efforts")
                if isinstance(sre, list):
                    sre = [str(x) for x in sre if isinstance(x, str) and x] or None
                else:
                    sre = None
                dre = e.get("default_reasoning_effort")
                dre = str(dre) if isinstance(dre, str) else None
                supports_re = bool(e.get("supports_reasoning_effort", False))
                mctx = e.get("max_context_window_tokens")
                mctx = int(mctx) if isinstance(mctx, int) else None
                def _to_float(v):
                    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None
                ip = _to_float(e.get("input_price_usd_per_1m"))
                op = _to_float(e.get("output_price_usd_per_1m"))
                cp = _to_float(e.get("cache_price_usd_per_1m"))
                entries.append(
                    ModelEntry(
                        id=str(eid),
                        name=str(name),
                        default_reasoning_effort=dre,
                        supported_reasoning_efforts=sre,
                        supports_reasoning_effort=supports_re,
                        max_context_window_tokens=mctx,
                        input_price_usd_per_1m=ip,
                        output_price_usd_per_1m=op,
                        cache_price_usd_per_1m=cp,
                    )
                )
            # entries が空でも `models` フィールドがあれば ID リストとして復元する
            # （save(models) で書かれた v2 互換ファイルの場合）。
            raw_models = data.get("models")
            if isinstance(raw_models, list):
                models_list = [str(m) for m in raw_models if isinstance(m, str) and m]
            else:
                models_list = [e.id for e in entries]
        else:  # version == 1
            raw_models = data.get("models")
            if not isinstance(raw_models, list):
                return None
            models_list = [str(m) for m in raw_models if isinstance(m, str) and m]

        cached = CachedModels(
            models=models_list,
            fetched_at=float(fetched_at),
            entries=entries,
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return None

    if allow_stale:
        return cached
    return cached if is_fresh(cached, ttl_seconds=ttl_seconds, now=now) else None


# ---------------------------------------------------------------------------
# セーブ
# ---------------------------------------------------------------------------


def save(
    models: List[str],
    *,
    path: Optional[Path] = None,
    now: Optional[float] = None,
) -> Path:
    """モデル ID 一覧のみをキャッシュに保存する。親ディレクトリは自動作成。

    v2 フォーマットで entries 空リストとして保存される（互換ラッパー）。
    詳細な entry 情報 (effort/context) も保存したい場合は `save_entries` を使う。

    Returns:
        書き込んだファイルの絶対パス。
    """
    target = path or get_cache_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "fetched_at": float(now if now is not None else time.time()),
        "models": list(models),
        "entries": [],
    }
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return target


def save_entries(
    entries: List[ModelEntry],
    *,
    path: Optional[Path] = None,
    now: Optional[float] = None,
) -> Path:
    """ModelEntry リストを v2 フォーマットでキャッシュに保存する。

    `entries` と互換用の `models` (ID のみ) を両方保存する。
    """
    target = path or get_cache_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized: List[dict] = []
    for e in entries:
        d: dict = {"id": e.id, "name": e.name}
        if e.default_reasoning_effort is not None:
            d["default_reasoning_effort"] = e.default_reasoning_effort
        if e.supported_reasoning_efforts is not None:
            d["supported_reasoning_efforts"] = list(e.supported_reasoning_efforts)
        if e.supports_reasoning_effort:
            d["supports_reasoning_effort"] = True
        if e.max_context_window_tokens is not None:
            d["max_context_window_tokens"] = e.max_context_window_tokens
        if e.input_price_usd_per_1m is not None:
            d["input_price_usd_per_1m"] = e.input_price_usd_per_1m
        if e.output_price_usd_per_1m is not None:
            d["output_price_usd_per_1m"] = e.output_price_usd_per_1m
        if e.cache_price_usd_per_1m is not None:
            d["cache_price_usd_per_1m"] = e.cache_price_usd_per_1m
        serialized.append(d)
    payload = {
        "version": CACHE_VERSION,
        "fetched_at": float(now if now is not None else time.time()),
        "models": [e.id for e in entries],
        "entries": serialized,
    }
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return target


# ---------------------------------------------------------------------------
# クリア
# ---------------------------------------------------------------------------


def clear(path: Optional[Path] = None) -> bool:
    """キャッシュを削除する。

    Returns:
        削除した場合 True, 元々存在しない場合 False。
    """
    target = path or get_cache_path()
    if target.is_file():
        target.unlink()
        return True
    return False
