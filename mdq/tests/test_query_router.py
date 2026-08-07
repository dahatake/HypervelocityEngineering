"""Tests for query_router rule-based classification."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mdq import query_router as qr
from mdq import strategies as _strategies


def test_id_lookup_single_token() -> None:
    d = qr.classify_query("D03")
    assert d.strategy == "heading"
    assert d.reason == "id_lookup"
    assert d.rule_id == 1


def test_id_lookup_app_pattern() -> None:
    d = qr.classify_query("APP-12")
    assert d.reason == "id_lookup"


def test_exact_match_quoted() -> None:
    d = qr.classify_query('"foo bar"')
    assert d.reason == "exact_match"
    assert d.rule_id == 2
    assert d.strategy == "heading"


def test_grep_mode_forces_exact_match() -> None:
    d = qr.classify_query("anything goes here narrative how", mode="grep")
    assert d.reason == "exact_match"


def test_code_fragment_route_to_fixed_window() -> None:
    d = qr.classify_query("foo => bar()")
    assert d.reason == "code_fragment"
    assert d.strategy == "fixed_window"


def test_short_proper_noun_route() -> None:
    # 3 CJK tokens (認/証/サ -> 3 tokens but サービス は カタカナ; トークナイザは
    # 単一 CJK 文字ごとに 1 トークンを生成するため "認証" だけで 2 トークン
    # = ルール 3 の 要件 <=3 を満たす）
    d = qr.classify_query("認証")
    assert d.reason == "short_proper_noun"
    assert d.strategy == "heading"


def test_concept_overview_route() -> None:
    # concept_overview は pageindex を第一候補にする (新ルート)。
    # available_strategies 未指定時はフォールバックなしで pageindex を返す。
    d = qr.classify_query("システム全体のアーキテクチャ")
    assert d.reason == "concept_overview"
    assert d.strategy == "pageindex"


def test_concept_overview_falls_back_when_pageindex_missing() -> None:
    d = qr.classify_query(
        "システム全体のアーキテクチャ",
        available_strategies={"heading"},
    )
    assert d.reason == "concept_overview"
    assert d.original_strategy == "pageindex"
    assert d.fallback_used is True
    assert d.strategy == "heading"


def test_narrative_query_route() -> None:
    # ルール 4 (concept_overview) に乗らないよう 「設計」等の概念語を選拞しない。
    d = qr.classify_query("どうやって認証フローを実装すべきか教えて")
    assert d.reason == "narrative_query"
    # narrative_query は semantic_paragraph を第一候補にする (新ルート)。
    # 既存 DB が限定されていれば _finalize のフォールバック順で
    # heading_recursive へ降格する。
    assert d.strategy == "semantic_paragraph"


def test_narrative_query_falls_back_to_heading_recursive_when_semantic_missing() -> None:
    d = qr.classify_query(
        "どうやって認証フローを実装すべきか教えて",
        available_strategies={"heading_recursive"},
    )
    assert d.reason == "narrative_query"
    assert d.strategy == "heading_recursive"
    assert d.fallback_used is True
    assert d.original_strategy == "semantic_paragraph"


def test_default_fallback() -> None:
    d = qr.classify_query("foo bar baz qux quux corge")
    # トークン>=8 の長文として narrative_query にマッチする可能性もある。
    # 元戦略は narrative ルールに合致した場合 semantic_paragraph、
    # default ルートなら heading_recursive。
    assert d.reason in ("narrative_query", "default")
    assert d.strategy in ("semantic_paragraph", "heading_recursive")


def test_fallback_when_chosen_unavailable() -> None:
    d = qr.classify_query("D03", available_strategies={"heading_recursive"})
    # rule_id=1 wanted heading, but only heading_recursive is available
    assert d.fallback_used is True
    assert d.strategy == "heading_recursive"
    assert d.original_strategy == "heading"


def test_no_fallback_when_chosen_available() -> None:
    d = qr.classify_query("D03", available_strategies={"heading"})
    assert d.fallback_used is False
    assert d.strategy == "heading"


# --- discover_available_strategies -----------------------------------------
# The function's contract is "the set of strategies whose per-(lang, strategy)
# DB exists". It must therefore recognise every SQLite-backed strategy in
# mdq.strategies.ALL_STRATEGIES, not a hardcoded subset.

# graphrag is excluded on purpose: it does not use the SQLite store at all.
_SQLITE_STRATEGIES = tuple(
    s for s in _strategies.ALL_STRATEGIES if s != "graphrag"
)


def _make_index(root: Path, lang: str, strategy: str) -> None:
    base = root / ".mdq"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"index-{lang}-{strategy}.sqlite").write_bytes(b"")


@pytest.mark.parametrize("strategy", _SQLITE_STRATEGIES)
def test_discover_recognises_every_sqlite_strategy(tmp_path: Path,
                                                   strategy: str) -> None:
    _make_index(tmp_path, "ja-jp", strategy)
    assert qr.discover_available_strategies(tmp_path) == {strategy}


def test_discover_does_not_confuse_heading_with_heading_recursive(
    tmp_path: Path,
) -> None:
    _make_index(tmp_path, "ja-jp", "heading_recursive")
    assert qr.discover_available_strategies(tmp_path) == {"heading_recursive"}


def test_discover_returns_all_present_strategies(tmp_path: Path) -> None:
    for strategy in _SQLITE_STRATEGIES:
        _make_index(tmp_path, "en-us", strategy)
    assert qr.discover_available_strategies(tmp_path) == set(_SQLITE_STRATEGIES)


def test_discover_ignores_graphrag(tmp_path: Path) -> None:
    """graphrag never writes to the SQLite store, so it must not be reported."""
    _make_index(tmp_path, "ja-jp", "graphrag")
    _make_index(tmp_path, "ja-jp", "heading")
    assert qr.discover_available_strategies(tmp_path) == {"heading"}


def test_narrative_query_reaches_semantic_paragraph_when_indexed(
    tmp_path: Path,
) -> None:
    """A built semantic_paragraph index must be reachable via --strategy auto."""
    _make_index(tmp_path, "ja-jp", "semantic_paragraph")
    available = qr.discover_available_strategies(tmp_path)
    # Deliberately free of CONCEPT_TERMS so rule 4 does not pre-empt rule 5.
    d = qr.classify_query("なぜこの挙動になるのか教えてほしい",
                          available_strategies=available)
    assert d.reason == "narrative_query"
    assert d.strategy == "semantic_paragraph"
    assert d.fallback_used is False


def test_concept_overview_reaches_pageindex_when_indexed(tmp_path: Path) -> None:
    _make_index(tmp_path, "ja-jp", "pageindex")
    available = qr.discover_available_strategies(tmp_path)
    d = qr.classify_query("アーキテクチャの概要", available_strategies=available)
    assert d.reason == "concept_overview"
    assert d.strategy == "pageindex"
    assert d.fallback_used is False
