"""FR-TS-05: 検索品質（Recall@k / MRR）とトークン削減率の評価。"""

from __future__ import annotations

import unittest
from pathlib import Path

from hve.toolsearch.eval import (
    EvalReport,
    GoldenQuery,
    QueryResult,
    TokenReport,
    entry_definition_text,
    estimate_tokens,
    evaluate,
    format_report,
    load_golden,
    token_report,
)
from hve.toolsearch.policy import ToolSearchPolicy, apply_policy
from hve.toolsearch.skill_catalog import build_skill_entries, discover_skills
from hve.toolsearch.types import ToolEntry

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPO_SKILLS = _REPO_ROOT / ".github" / "skills"

# hve/repository_query_tools.py が define_tool で登録する 4 ツールの description。
_NATIVE_TOOLS = (
    ("search_markdown", "Search local repository Markdown with fixed caps."),
    ("search_code", "Search local repository source code with fixed caps."),
    ("open_evidence", "Open only evidence refs registered by this query."),
    ("find_code_references", "Find local code references for one symbol."),
)


def _eval_catalog(policy: ToolSearchPolicy) -> tuple[ToolEntry, ...]:
    """静的に列挙できるカタログ（Skill + native ツール）を作る。"""
    skills = build_skill_entries(
        discover_skills([_REPO_SKILLS]),
        pin_for=policy.pin_for,
        search_text_for=policy.search_text_for,
    )
    natives = tuple(
        ToolEntry(
            id=ToolEntry.make_id("native", "hve", name),
            kind="native",
            server="hve",
            name=name,
            description=description,
            additional_search_text=policy.search_text_for(ToolEntry.make_id("native", "hve", name)),
            pin=policy.pin_for(ToolEntry.make_id("native", "hve", name)),
        )
        for name, description in _NATIVE_TOOLS
    )
    return skills + natives


class TestGoldenSet(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ToolSearchPolicy.load()
        self.catalog = _eval_catalog(self.policy)
        self.golden = load_golden()

    def test_golden_set_is_large_enough_to_be_meaningful(self) -> None:
        self.assertGreaterEqual(len(self.golden), 40)

    def test_every_expected_tool_exists_in_the_catalog(self) -> None:
        names = {entry.name for entry in self.catalog}
        missing = {
            expected
            for item in self.golden
            for expected in item.expected
            if expected not in names
        }
        self.assertEqual(missing, set(), msg=f"golden references unknown tools: {sorted(missing)}")

    def test_queries_are_unique(self) -> None:
        queries = [item.query for item in self.golden]
        self.assertEqual(len(queries), len(set(queries)))


class TestRetrievalQuality(unittest.TestCase):
    """FR-TS-05 の合否判定: Recall@10 >= 0.85。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = ToolSearchPolicy.load()
        cls.catalog = _eval_catalog(cls.policy)
        cls.report = evaluate(
            cls.catalog,
            load_golden(),
            field_weights=cls.policy.field_weights,
            limit=10,
        )

    def test_recall_at_10_meets_the_acceptance_threshold(self) -> None:
        self.assertGreaterEqual(
            self.report.recall_at(10),
            0.85,
            msg="\n" + format_report(self.report),
        )

    def test_recall_at_5_is_reported(self) -> None:
        self.assertGreater(self.report.recall_at(5), 0.0)

    def test_mrr_is_reported(self) -> None:
        self.assertGreater(self.report.mrr, 0.0)

    def test_evaluation_is_deterministic(self) -> None:
        again = evaluate(
            self.catalog,
            load_golden(),
            field_weights=self.policy.field_weights,
            limit=10,
        )
        self.assertEqual(
            [r.ranked for r in again.results],
            [r.ranked for r in self.report.results],
        )


class TestMetrics(unittest.TestCase):
    def test_recall_counts_only_the_top_k(self) -> None:
        result = QueryResult(query="q", expected=("a",), ranked=("x", "y", "a"))
        self.assertEqual(result.recall_at(2), 0.0)
        self.assertEqual(result.recall_at(3), 1.0)

    def test_hit_rank_is_one_based(self) -> None:
        self.assertEqual(QueryResult(query="q", expected=("a",), ranked=("x", "a")).hit_rank(), 2)
        self.assertIsNone(QueryResult(query="q", expected=("a",), ranked=("x",)).hit_rank())

    def test_mrr_uses_the_reciprocal_of_the_first_hit(self) -> None:
        report = EvalReport(
            results=(
                QueryResult(query="1", expected=("a",), ranked=("a",)),
                QueryResult(query="2", expected=("b",), ranked=("x", "b")),
            )
        )
        self.assertAlmostEqual(report.mrr, (1.0 + 0.5) / 2)

    def test_empty_report_is_zero_not_an_error(self) -> None:
        report = EvalReport(results=())
        self.assertEqual(report.recall_at(10), 0.0)
        self.assertEqual(report.mrr, 0.0)

    def test_misses_are_listed(self) -> None:
        report = EvalReport(results=(QueryResult(query="q", expected=("a",), ranked=("x",)),))
        self.assertEqual(len(report.misses), 1)


class TestTokenEstimation(unittest.TestCase):
    def test_empty_text_costs_nothing(self) -> None:
        self.assertEqual(estimate_tokens(""), 0)

    def test_longer_text_costs_more(self) -> None:
        self.assertGreater(estimate_tokens("a" * 400), estimate_tokens("a" * 40))

    def test_definition_text_excludes_search_only_vocabulary(self) -> None:
        entry = ToolEntry(
            id="mcp:azure:x",
            kind="mcp",
            server="azure",
            name="x",
            description="desc",
            additional_search_text="秘匿すべき検索専用語彙",
        )
        self.assertNotIn("秘匿すべき検索専用語彙", entry_definition_text(entry))

    def test_reduction_ratio_is_zero_for_an_empty_baseline(self) -> None:
        self.assertEqual(TokenReport(baseline_tokens=0, optimized_tokens=0).reduction_ratio, 0.0)


class TestTokenReduction(unittest.TestCase):
    """FR-TS-05: トークン削減率を数値で報告できること。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = ToolSearchPolicy.load()
        cls.catalog = _eval_catalog(cls.policy)
        cls.decision = apply_policy(cls.catalog, cls.policy)
        cls.tokens = token_report(cls.catalog, cls.decision.pinned)

    def test_baseline_counts_every_definition(self) -> None:
        self.assertGreater(self.tokens.baseline_tokens, 0)

    def test_optimized_is_smaller_than_the_baseline(self) -> None:
        self.assertLess(self.tokens.optimized_tokens, self.tokens.baseline_tokens)

    def test_reduction_is_reported_and_substantial(self) -> None:
        self.assertGreaterEqual(
            self.tokens.reduction_ratio,
            0.60,
            msg=format_report(EvalReport(results=()), self.tokens),
        )

    def test_report_formats_both_quality_and_cost(self) -> None:
        report = evaluate(self.catalog, load_golden(), field_weights=self.policy.field_weights, limit=10)
        text = format_report(report, self.tokens)
        self.assertIn("recall@10", text)
        self.assertIn("reduction", text)

    def test_pinned_entries_are_matched_by_id_not_object_identity(self) -> None:
        """apply_policy はフィールドを差し替えた新しい ToolEntry を返す（S2-S8 レビュー Critical）。"""
        import dataclasses

        entry = ToolEntry(id="mcp:azure:x", kind="mcp", server="azure", name="x", description="desc")
        rewritten = dataclasses.replace(entry, pin="always", additional_search_text="vocab")
        self.assertNotEqual(entry, rewritten)
        tokens = token_report([entry], [rewritten])
        self.assertEqual(tokens.optimized_tokens, tokens.baseline_tokens)


if __name__ == "__main__":
    unittest.main()
