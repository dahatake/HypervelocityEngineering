"""FR-MDQ-01 contracts for the shared golden-query evaluator."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mdq import golden_eval

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN = REPO_ROOT / "mdq" / "golden-queries.json"


def _expected(path: str = "a.md", line: int = 3, anchor: str = ""):
    return golden_eval.ExpectedHit(path=path, line=line, anchor=anchor)


def _write(tmp_path: Path, queries: list[dict], *, version: int = 1) -> Path:
    target = tmp_path / "golden.json"
    target.write_text(
        json.dumps({"schema_version": version, "queries": queries}), encoding="utf-8"
    )
    return target


def _entry(**overrides) -> dict:
    row = {
        "id": "Q-01",
        "q": "alpha",
        "expected": [{"path": "a.md", "line": 3}],
        "paths": ["docs/*"],
        "group": "unit",
    }
    row.update(overrides)
    return row


def _seed(tmp_path: Path, text: str = "one\ntwo\nunique anchor\nfour\n") -> None:
    (tmp_path / "a.md").write_text(text, encoding="utf-8")


class TestHitCorrectness:
    def test_path_and_inclusive_line_range_must_match(self) -> None:
        assert golden_eval.hit_matches(
            {"path": "a.md", "start_line": 2, "end_line": 4}, _expected()
        )

    def test_path_only_match_is_wrong(self) -> None:
        assert not golden_eval.hit_matches(
            {"path": "a.md", "start_line": 8, "end_line": 9}, _expected()
        )

    def test_missing_line_range_is_wrong(self) -> None:
        assert not golden_eval.hit_matches({"path": "a.md"}, _expected())

    def test_lines_pair_is_accepted(self) -> None:
        assert golden_eval.hit_matches({"path": "a.md", "lines": [3, 3]}, _expected())

    def test_non_numeric_line_range_is_wrong(self) -> None:
        assert not golden_eval.hit_matches(
            {"path": "a.md", "lines": ["2", "4"]}, _expected()
        )

    def test_path_is_normalised_to_posix(self) -> None:
        assert golden_eval.hit_matches(
            {"path": "docs\\a.md", "lines": [1, 1]},
            _expected("docs/a.md", 1),
        )

    def test_first_correct_rank_is_one_based(self) -> None:
        hits = [
            {"path": "wrong.md", "lines": [1, 2]},
            {"path": "a.md", "lines": [2, 4]},
        ]
        assert golden_eval.rank_of_first_correct(hits, [_expected()]) == 2

    def test_top1_and_topk_are_separate(self) -> None:
        hits = [
            {"path": "wrong.md", "lines": [1, 2]},
            {"path": "a.md", "lines": [2, 4]},
        ]
        assert golden_eval.score_query(hits, [_expected()], top_k=5) == {
            "rank": 2,
            "top1": False,
            "topk": True,
        }


class TestAggregate:
    def test_rates_are_aggregated(self) -> None:
        result = golden_eval.aggregate(
            [{"top1": True, "topk": True}, {"top1": False, "topk": True}], 5
        )
        assert result["top1_accuracy"] == 0.5
        assert result["topk_accuracy"] == 1.0

    def test_empty_input_does_not_fabricate_zero_accuracy(self) -> None:
        result = golden_eval.aggregate([], 5)
        assert result["queries"] == 0
        assert result["top1_accuracy"] is None
        assert result["topk_accuracy"] is None


class TestMeanReciprocalRank:
    """FR-MDQ-04: MRR@k は順位の逆数の平均で、k 件内に正解が無ければ寄与 0。"""

    def test_mrr_is_the_mean_of_reciprocal_ranks(self) -> None:
        result = golden_eval.aggregate(
            [
                {"top1": True, "topk": True, "rank": 1},
                {"top1": False, "topk": True, "rank": 4},
            ],
            5,
        )
        assert result["mrr_at_k"] == 0.625

    def test_query_without_a_correct_hit_contributes_zero(self) -> None:
        result = golden_eval.aggregate(
            [
                {"top1": True, "topk": True, "rank": 1},
                {"top1": False, "topk": False, "rank": None},
            ],
            5,
        )
        assert result["mrr_at_k"] == 0.5

    def test_rank_beyond_k_contributes_zero(self) -> None:
        result = golden_eval.aggregate(
            [{"top1": False, "topk": False, "rank": 7}], 5
        )
        assert result["mrr_at_k"] == 0.0

    def test_empty_input_does_not_fabricate_zero_mrr(self) -> None:
        assert golden_eval.aggregate([], 5)["mrr_at_k"] is None

    def test_rows_without_rank_do_not_fabricate_mrr(self) -> None:
        """順位が渡されていないのに 0 を返すと topk と矛盾した数値になる。"""
        result = golden_eval.aggregate([{"top1": True, "topk": True}], 5)
        assert result["mrr_at_k"] is None


class TestGoldenSetValidation:
    def test_rejects_unknown_schema(self, tmp_path: Path) -> None:
        with pytest.raises(golden_eval.GoldenSetError, match="schema_version"):
            golden_eval.load_golden(_write(tmp_path, [], version=999), tmp_path)

    def test_rejects_duplicate_ids(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        path = _write(tmp_path, [_entry(), _entry()])
        with pytest.raises(golden_eval.GoldenSetError, match="duplicate|重複"):
            golden_eval.load_golden(path, tmp_path)

    def test_rejects_empty_expected(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        with pytest.raises(golden_eval.GoldenSetError, match="expected"):
            golden_eval.load_golden(_write(tmp_path, [_entry(expected=[])]), tmp_path)

    def test_rejects_missing_path(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            [_entry(expected=[{"path": "missing.md", "line": 1}])],
        )
        with pytest.raises(golden_eval.GoldenSetError, match="exist|存在"):
            golden_eval.load_golden(path, tmp_path)

    @pytest.mark.parametrize("unsafe", ["../outside.md", "/outside.md", "C:/outside.md"])
    def test_rejects_expected_paths_outside_repository(
        self, tmp_path: Path, unsafe: str
    ) -> None:
        path = _write(
            tmp_path,
            [_entry(expected=[{"path": unsafe, "line": 1}])],
        )
        with pytest.raises(golden_eval.GoldenSetError, match="repository|relative|path"):
            golden_eval.load_golden(path, tmp_path)

    def test_rejects_line_beyond_file(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        path = _write(tmp_path, [_entry(expected=[{"path": "a.md", "line": 99}])])
        with pytest.raises(golden_eval.GoldenSetError, match="99"):
            golden_eval.load_golden(path, tmp_path)

    def test_anchor_only_resolves_snapshot_line(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        path = _write(
            tmp_path,
            [_entry(expected=[{"path": "a.md", "anchor": "unique anchor"}])],
        )
        query = golden_eval.load_golden(path, tmp_path)[0]
        assert query.expected[0].line == 3

    def test_rejects_absent_anchor(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        path = _write(
            tmp_path,
            [_entry(expected=[{"path": "a.md", "anchor": "absent"}])],
        )
        with pytest.raises(golden_eval.GoldenSetError, match="anchor"):
            golden_eval.load_golden(path, tmp_path)

    def test_rejects_ambiguous_anchor(self, tmp_path: Path) -> None:
        _seed(tmp_path, "dup\nother\ndup\n")
        path = _write(
            tmp_path,
            [_entry(expected=[{"path": "a.md", "anchor": "dup"}])],
        )
        with pytest.raises(golden_eval.GoldenSetError, match="ambiguous|複数"):
            golden_eval.load_golden(path, tmp_path)

    def test_pinned_line_anchor_mismatch_reports_actual_line(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        path = _write(
            tmp_path,
            [_entry(expected=[{"path": "a.md", "line": 1, "anchor": "unique anchor"}])],
        )
        with pytest.raises(golden_eval.GoldenSetError, match="3"):
            golden_eval.load_golden(path, tmp_path)

    def test_generated_inventory_requires_anchor(self, tmp_path: Path) -> None:
        generated = tmp_path / "hve-dev" / "hve-feature-inventory.csv"
        generated.parent.mkdir()
        generated.write_text("kind,id\nFR,FR-X\n", encoding="utf-8")
        path = _write(
            tmp_path,
            [_entry(expected=[{"path": "hve-dev/hve-feature-inventory.csv", "line": 2}])],
        )
        with pytest.raises(golden_eval.GoldenSetError, match="anchor"):
            golden_eval.load_golden(path, tmp_path)

    def test_query_metadata_is_preserved(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        query = golden_eval.load_golden(_write(tmp_path, [_entry()]), tmp_path)[0]
        assert query.paths == ("docs/*",)
        assert query.group == "unit"


class TestRepositoryGoldenSet:
    def test_repository_set_is_fixed_before_ranking(self) -> None:
        queries = golden_eval.load_golden(GOLDEN, REPO_ROOT)
        assert len(queries) == 40
        assert {q.group for q in queries} == {
            "requirements",
            "catalog",
            "design-docs",
            "guides",
            "generated-inventory",
        }

    def test_every_expectation_has_a_unique_anchor(self) -> None:
        queries = golden_eval.load_golden(GOLDEN, REPO_ROOT)
        for query in queries:
            for expected in query.expected:
                assert expected.anchor, query.id
                lines = (REPO_ROOT / expected.path).read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                found = [n for n, line in enumerate(lines, 1) if expected.anchor in line]
                assert found == [expected.line], (query.id, found)

    def test_expected_locations_exist_in_the_cq_ablation_baseline(self) -> None:
        queries = golden_eval.load_golden(GOLDEN, REPO_ROOT)
        for query in queries:
            for expected in query.expected:
                assert "FR-CQ-" not in expected.anchor
                assert "code-query" not in expected.path
                assert not expected.path.startswith("work/analysis/2026-07-29-code-query-skill/")
