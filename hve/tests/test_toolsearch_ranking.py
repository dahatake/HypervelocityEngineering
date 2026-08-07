"""FR-TS-04: ランキング（日本語 BM25F / 識別子分割 / 適応的打ち切り / フォールバック）。"""

from __future__ import annotations

import unittest

from hve.toolsearch.policy import ToolSearchPolicy
from hve.toolsearch.ranking import (
    FIELD_ORDER,
    ToolRanker,
    rank_tools,
    resolve_bm25_engine,
    split_identifier,
    tokenize,
)
from hve.toolsearch.types import ToolEntry

_WEIGHTS = {"name": 3.0, "additional_search_text": 2.5, "description": 2.0, "arg_terms": 1.0}


def _entry(name: str, description: str = "", *, search_text: str = "", args=()) -> ToolEntry:
    return ToolEntry(
        id=ToolEntry.make_id("mcp", "azure", name),
        kind="mcp",
        server="azure",
        name=name,
        description=description,
        arg_terms=tuple(args),
        additional_search_text=search_text,
    )


class TestSplitIdentifier(unittest.TestCase):
    def test_splits_snake_case(self) -> None:
        self.assertEqual(split_identifier("search_markdown"), ["search", "markdown"])

    def test_splits_double_underscore_namespaces(self) -> None:
        self.assertEqual(split_identifier("mcp__azure__group_list"), ["mcp", "azure", "group", "list"])

    def test_splits_camel_case(self) -> None:
        self.assertEqual(split_identifier("azmcpGroupList"), ["azmcp", "group", "list"])

    def test_deduplicates_repeated_parts(self) -> None:
        self.assertEqual(split_identifier("list_list"), ["list"])


class TestTokenize(unittest.TestCase):
    def test_empty_text_yields_no_tokens(self) -> None:
        self.assertEqual(tokenize(""), [])

    def test_japanese_is_split_into_adjacent_bigrams(self) -> None:
        tokens = tokenize("敵対的レビュー")
        self.assertIn("敵対", tokens)
        self.assertIn("対的", tokens)

    def test_identifier_parts_are_added_alongside_the_whole_token(self) -> None:
        tokens = tokenize("search_markdown")
        self.assertIn("search_markdown", tokens)
        self.assertIn("markdown", tokens)


class TestEngineFallback(unittest.TestCase):
    def test_default_engine_is_the_non_degenerate_one(self) -> None:
        name, factory = resolve_bm25_engine()
        self.assertEqual(name, "mini_bm25")
        index = factory([["a", "b"], ["b", "c"]], b=0.2)
        self.assertEqual(len(index.get_scores(["b"])), 2)

    def test_ranker_reports_which_engine_it_uses(self) -> None:
        ranker = ToolRanker([_entry("x", "desc")], _WEIGHTS)
        self.assertEqual(ranker.engine_name, "mini_bm25")

    def test_rank_bm25_degenerates_to_zero_idf_on_small_catalogs(self) -> None:
        """既定を _MiniBM25 にした根拠を固定する（実測されたエンジン差）。"""
        try:
            from rank_bm25 import BM25Okapi  # noqa: F401
        except ImportError:
            self.skipTest("rank_bm25 is not installed")
        entries = [_entry("hit", "サブスクリプション"), _entry("miss", "無関係")]
        okapi = rank_tools(entries, "サブスクリプション", field_weights=_WEIGHTS, engine="rank_bm25")
        mini = rank_tools(entries, "サブスクリプション", field_weights=_WEIGHTS)
        self.assertEqual(okapi, ())
        self.assertEqual(mini[0].entry.name, "hit")


class TestJapaneseRanking(unittest.TestCase):
    """FR-TS-04: 日本語クエリで正解ツールが上位に入ること。"""

    def setUp(self) -> None:
        self.entries = [
            _entry("skill_adversarial-review", "明示的に要求された敵対的レビューを実行するスキル"),
            _entry("azmcp_group_list", "List Azure resource groups in a subscription"),
            _entry("skill_work-artifacts-layout", "work/ 配下の作業ディレクトリ構造を整備するスキル"),
            _entry("execute_query", "設定済みのデータベースに対してクエリを実行します"),
        ]

    def test_japanese_query_finds_the_right_skill(self) -> None:
        results = rank_tools(self.entries, "敵対的レビューをしたい", field_weights=_WEIGHTS)
        self.assertEqual(results[0].entry.name, "skill_adversarial-review")

    def test_japanese_query_finds_the_work_directory_skill(self) -> None:
        results = rank_tools(self.entries, "作業ディレクトリの構造", field_weights=_WEIGHTS)
        self.assertEqual(results[0].entry.name, "skill_work-artifacts-layout")

    def test_english_identifier_query_still_works(self) -> None:
        results = rank_tools(self.entries, "list resource groups", field_weights=_WEIGHTS)
        self.assertEqual(results[0].entry.name, "azmcp_group_list")


class TestAdditionalSearchTextEffect(unittest.TestCase):
    """記事の中心的主張: 実装語彙の説明だけではユーザーの語彙で上位に来ない。"""

    QUERY = "ダッシュボード用のデータを取得したい"

    def _entries(self, *, with_vocabulary: bool):
        return [
            _entry(
                "execute_query",
                "設定済みのデータベースに対してクエリを実行します",
                search_text="分析 ダッシュボード SQL レポート ウェアハウス テーブル構造" if with_vocabulary else "",
            ),
            _entry("list_records", "取得したデータの一覧を返します"),
            _entry("send_mail", "メールを送信します"),
        ]

    def _score_of(self, name: str, *, with_vocabulary: bool) -> float:
        results = rank_tools(
            self._entries(with_vocabulary=with_vocabulary),
            self.QUERY,
            field_weights=_WEIGHTS,
            limit=10,
            tau=0.0,
        )
        for item in results:
            if item.entry.name == name:
                return item.score
        return 0.0

    def test_vocabulary_raises_the_score_of_the_target_tool(self) -> None:
        without = self._score_of("execute_query", with_vocabulary=False)
        with_text = self._score_of("execute_query", with_vocabulary=True)
        self.assertGreater(with_text, without)

    def test_vocabulary_improves_the_rank_position(self) -> None:
        def position(with_vocabulary: bool) -> int:
            ranked = [
                r.entry.name
                for r in rank_tools(
                    self._entries(with_vocabulary=with_vocabulary),
                    self.QUERY,
                    field_weights=_WEIGHTS,
                    limit=10,
                    tau=0.0,
                )
            ]
            return ranked.index("execute_query")

        self.assertLess(position(True), position(False))

    def test_search_only_vocabulary_never_reaches_the_model(self) -> None:
        from hve.toolsearch import ToolCard

        results = rank_tools(self._entries(with_vocabulary=True), self.QUERY, field_weights=_WEIGHTS, tau=0.0)
        card = ToolCard.from_entry(results[0].entry, results[0].score)
        self.assertNotIn("ウェアハウス", repr(card))


class TestArgumentTermsAreSearchable(unittest.TestCase):
    def test_argument_vocabulary_contributes_to_the_score(self) -> None:
        entries = [
            _entry("alpha", "generic tool"),
            _entry("beta", "generic tool", args=("subscription", "サブスクリプション ID")),
        ]
        results = rank_tools(entries, "サブスクリプション", field_weights=_WEIGHTS)
        self.assertEqual(results[0].entry.name, "beta")


class TestAdaptiveCutoff(unittest.TestCase):
    def test_returns_empty_when_nothing_matches(self) -> None:
        self.assertEqual(rank_tools([_entry("x", "abc")], "全く無関係な語彙", field_weights=_WEIGHTS), ())

    def test_returns_empty_for_blank_query(self) -> None:
        self.assertEqual(rank_tools([_entry("x", "abc")], "", field_weights=_WEIGHTS), ())

    def test_respects_the_limit(self) -> None:
        entries = [_entry(f"tool_{i}", "共通の説明 検索対象") for i in range(10)]
        self.assertLessEqual(len(rank_tools(entries, "共通の説明", field_weights=_WEIGHTS, limit=3)), 3)

    def test_low_scoring_tail_is_cut_by_tau(self) -> None:
        entries = [
            _entry("strong", "敵対的レビュー 敵対的レビュー 敵対的レビュー"),
            _entry("weak", "レビュー観点をひとつだけ含む長い説明 " + "詰め物 " * 40),
        ]
        loose = rank_tools(entries, "敵対的レビュー", field_weights=_WEIGHTS, tau=0.0, limit=10)
        strict = rank_tools(entries, "敵対的レビュー", field_weights=_WEIGHTS, tau=0.95, limit=10)
        self.assertGreaterEqual(len(loose), len(strict))
        self.assertEqual(strict[0].entry.name, "strong")

    def test_empty_catalog_yields_empty_result(self) -> None:
        self.assertEqual(rank_tools([], "何か", field_weights=_WEIGHTS), ())

    def test_zero_limit_yields_empty_result(self) -> None:
        self.assertEqual(rank_tools([_entry("x", "abc")], "abc", field_weights=_WEIGHTS, limit=0), ())


class TestDeterminism(unittest.TestCase):
    def test_ties_are_broken_deterministically_by_id(self) -> None:
        entries = [_entry("b", "同一の説明"), _entry("a", "同一の説明")]
        first = [r.entry.name for r in rank_tools(entries, "同一の説明", field_weights=_WEIGHTS, limit=5)]
        second = [r.entry.name for r in rank_tools(list(reversed(entries)), "同一の説明", field_weights=_WEIGHTS, limit=5)]
        self.assertEqual(first, second)


class TestFieldWeightContract(unittest.TestCase):
    def test_field_order_matches_the_shipped_policy(self) -> None:
        policy = ToolSearchPolicy.load()
        self.assertEqual(set(FIELD_ORDER), set(policy.field_weights))

    def test_zero_weighted_field_is_not_indexed(self) -> None:
        ranker = ToolRanker([_entry("x", "説明のみ")], {**_WEIGHTS, "description": 0.0})
        self.assertNotIn("description", ranker._indexes)


if __name__ == "__main__":
    unittest.main()
