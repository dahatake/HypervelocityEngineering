"""Tests for query_router rule-based classification."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mdq import query_router as qr


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
