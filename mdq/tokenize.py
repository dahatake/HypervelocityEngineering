"""Language-aware tokenization for the markdown-query Skill.

Two tokenization layers exist in mdq:

1. **FTS5 tokenizer** — declared in the ``CREATE VIRTUAL TABLE chunks_fts``
   statement (see :mod:`mdq.store`). SQLite resolves it at query time.
2. **BM25 fallback tokenizer** — pure-Python regex used when ``rank_bm25``
   is unavailable or when callers explicitly request BM25 ranking outside
   FTS5 (see :mod:`mdq.search`).

We support two language codes:

- ``ja-jp`` (default): FTS5 uses the built-in ``trigram`` tokenizer (SQLite
  3.34+, no extra wheel). The Python fallback tokenizer matches CJK 1-char
  runs and ASCII identifiers — already implemented in ``search._TOKEN_RE``.
- ``en-us``: FTS5 uses ``unicode61`` (default). Python fallback identical.

If a SQLite build lacks the ``trigram`` tokenizer (older 3.x), the caller
should fall back to ``unicode61`` and log a warning.
"""
from __future__ import annotations

import sqlite3
from typing import Literal

Lang = Literal["ja-jp", "en-us"]

ALL_LANGS: tuple[Lang, ...] = ("ja-jp", "en-us")
DEFAULT_LANG: Lang = "ja-jp"


def normalize(lang: str | None) -> Lang:
    """Return a validated language code; falls back to default.

    Accepts common variants ``ja_JP`` / ``en_US`` (underscored) by
    lower-casing and replacing underscore with hyphen.
    """
    if not lang:
        return DEFAULT_LANG
    key = lang.lower().replace("_", "-")
    if key in ALL_LANGS:
        return key  # type: ignore[return-value]
    return DEFAULT_LANG


def fts5_tokenizer_for(lang: Lang) -> str:
    """Return the FTS5 ``tokenize=...`` clause body for a language.

    Example return value: ``"trigram"`` or ``"unicode61"``. The caller wraps
    it as ``tokenize='<value>'`` inside the CREATE VIRTUAL TABLE statement.
    """
    if lang == "ja-jp":
        return "trigram"
    return "unicode61"


def has_trigram_tokenizer(conn: sqlite3.Connection) -> bool:
    """Probe whether this SQLite build supports the ``trigram`` tokenizer.

    Returns ``True`` if the probe succeeds; ``False`` otherwise. Caller
    typically falls back to ``unicode61`` when this returns ``False``.
    """
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS _trigram_probe "
            "USING fts5(x, tokenize='trigram')"
        )
        conn.execute("DROP TABLE IF EXISTS _trigram_probe")
        return True
    except sqlite3.OperationalError:
        try:
            conn.execute("DROP TABLE IF EXISTS _trigram_probe")
        except sqlite3.OperationalError:
            pass
        return False


def resolved_fts5_tokenizer(conn: sqlite3.Connection, lang: Lang) -> str:
    """Return the FTS5 tokenizer actually usable on this SQLite build.

    For ``ja-jp`` this returns ``"trigram"`` when supported, otherwise
    ``"unicode61"`` as a graceful fallback. For ``en-us`` always
    ``"unicode61"``.
    """
    requested = fts5_tokenizer_for(lang)
    if requested == "trigram" and not has_trigram_tokenizer(conn):
        return "unicode61"
    return requested
