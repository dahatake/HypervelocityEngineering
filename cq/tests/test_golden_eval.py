"""Contracts for the cq golden-query evaluator (FR-CQ-02)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cq import golden_eval

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_SET = REPO_ROOT / "cq" / "golden-queries.json"


def _expect(path: str = "a.py", line: int = 3, anchor: str | None = None):
    return golden_eval.Expectation(path=path, line=line, anchor=anchor)


def _write_golden(tmp_path: Path, entries: list[dict]) -> Path:
    target = tmp_path / "golden.json"
    target.write_text(json.dumps(entries), encoding="utf-8")
    return target


def _seed_source(tmp_path: Path, name: str = "a.py", lines: int = 10) -> None:
    (tmp_path / name).write_text(
        "\n".join(f"line{n}" for n in range(1, lines + 1)), encoding="utf-8"
    )


class TestCorrectness:
    def test_path_and_line_range_must_both_match(self) -> None:
        hit = {"path": "a.py", "lines": [2, 5]}
        assert golden_eval.is_correct(hit, [_expect(line=3)]) is True

    def test_path_only_match_is_not_correct(self) -> None:
        hit = {"path": "a.py", "lines": [10, 20]}
        assert golden_eval.is_correct(hit, [_expect(line=3)]) is False

    def test_line_match_in_another_file_is_not_correct(self) -> None:
        hit = {"path": "b.py", "lines": [2, 5]}
        assert golden_eval.is_correct(hit, [_expect(line=3)]) is False

    def test_hit_without_line_range_is_incorrect(self) -> None:
        assert golden_eval.is_correct({"path": "a.py"}, [_expect(line=3)]) is False
        assert golden_eval.is_correct({"path": "a.py", "lines": [1]}, [_expect(line=3)]) is False
        assert golden_eval.is_correct(
            {"path": "a.py", "lines": ["1", "5"]}, [_expect(line=3)]
        ) is False

    def test_start_and_end_line_fields_are_accepted(self) -> None:
        hit = {"path": "a.py", "start_line": 2, "end_line": 5}
        assert golden_eval.is_correct(hit, [_expect(line=3)]) is True

    def test_boundaries_are_inclusive(self) -> None:
        hit = {"path": "a.py", "lines": [3, 5]}
        assert golden_eval.is_correct(hit, [_expect(line=3)]) is True
        assert golden_eval.is_correct({"path": "a.py", "lines": [1, 3]}, [_expect(line=3)]) is True

    def test_any_expectation_may_match(self) -> None:
        hit = {"path": "b.py", "lines": [7, 9]}
        assert golden_eval.is_correct(hit, [_expect(), _expect("b.py", 8)]) is True


class TestGoldenSetValidation:
    def test_rejects_missing_path(self, tmp_path: Path) -> None:
        path = _write_golden(tmp_path, [{
            "query": "q", "profile": "hve", "intent": "symbol",
            "expected": [{"path": "missing.py", "line": 1}],
        }])
        with pytest.raises(golden_eval.GoldenSetError, match="does not exist"):
            golden_eval.load_golden(path, tmp_path)

    def test_rejects_line_beyond_end_of_file(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        path = _write_golden(tmp_path, [{
            "query": "q", "profile": "hve", "intent": "symbol",
            "expected": [{"path": "a.py", "line": 999}],
        }])
        with pytest.raises(golden_eval.GoldenSetError, match="exceeds"):
            golden_eval.load_golden(path, tmp_path)

    def test_rejects_unknown_profile(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        path = _write_golden(tmp_path, [{
            "query": "q", "profile": "nope", "intent": "symbol",
            "expected": [{"path": "a.py", "line": 1}],
        }])
        with pytest.raises(golden_eval.GoldenSetError, match="profile"):
            golden_eval.load_golden(path, tmp_path)

    def test_rejects_unknown_intent(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        path = _write_golden(tmp_path, [{
            "query": "q", "profile": "hve", "intent": "nope",
            "expected": [{"path": "a.py", "line": 1}],
        }])
        with pytest.raises(golden_eval.GoldenSetError, match="intent"):
            golden_eval.load_golden(path, tmp_path)

    def test_rejects_empty_expectations(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        path = _write_golden(tmp_path, [{
            "query": "q", "profile": "hve", "intent": "symbol", "expected": [],
        }])
        with pytest.raises(golden_eval.GoldenSetError, match="expected"):
            golden_eval.load_golden(path, tmp_path)

    def test_anchor_mismatch_reports_actual_lines(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        path = _write_golden(tmp_path, [{
            "query": "q", "profile": "hve", "intent": "symbol",
            "expected": [{"path": "a.py", "line": 1, "anchor": "line7"}],
        }])
        with pytest.raises(golden_eval.GoldenSetError, match=r"found at \[7\]"):
            golden_eval.load_golden(path, tmp_path)

    def test_accepts_matching_anchor(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        path = _write_golden(tmp_path, [{
            "query": "q", "profile": "hve", "intent": "symbol",
            "expected": [{"path": "a.py", "line": 7, "anchor": "line7"}],
        }])
        queries = golden_eval.load_golden(path, tmp_path)
        assert queries[0].expectations[0].anchor == "line7"

    def test_anchor_without_line_resolves_the_line(self, tmp_path: Path) -> None:
        """行番号のドリフトで崩れない形式。"""
        _seed_source(tmp_path)
        path = _write_golden(tmp_path, [{
            "query": "q", "profile": "hve", "intent": "symbol",
            "expected": [{"path": "a.py", "anchor": "line7"}],
        }])
        assert golden_eval.load_golden(path, tmp_path)[0].expectations[0].line == 7

    def test_ambiguous_anchor_is_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("dup\nother\ndup\n", encoding="utf-8")
        path = _write_golden(tmp_path, [{
            "query": "q", "profile": "hve", "intent": "symbol",
            "expected": [{"path": "a.py", "anchor": "dup"}],
        }])
        with pytest.raises(golden_eval.GoldenSetError, match="ambiguous"):
            golden_eval.load_golden(path, tmp_path)

    def test_absent_anchor_is_rejected(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        path = _write_golden(tmp_path, [{
            "query": "q", "profile": "hve", "intent": "symbol",
            "expected": [{"path": "a.py", "anchor": "nowhere"}],
        }])
        with pytest.raises(golden_eval.GoldenSetError, match="does not occur"):
            golden_eval.load_golden(path, tmp_path)

    def test_entry_without_line_or_anchor_is_rejected(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        path = _write_golden(tmp_path, [{
            "query": "q", "profile": "hve", "intent": "symbol",
            "expected": [{"path": "a.py"}],
        }])
        with pytest.raises(golden_eval.GoldenSetError, match="either 'line' or 'anchor'"):
            golden_eval.load_golden(path, tmp_path)


class TestEvaluate:
    def _queries(self) -> tuple[golden_eval.GoldenQuery, ...]:
        return (
            golden_eval.GoldenQuery("q1", "hve", "symbol", (_expect(line=3),)),
            golden_eval.GoldenQuery("q2", "hve", "natural", (_expect("b.py", 8),)),
        )

    def test_top1_and_topk_are_counted_separately(self) -> None:
        def run(query, k):
            if query.query == "q1":
                return [{"path": "a.py", "lines": [1, 5]}], 100
            return (
                [{"path": "z.py", "lines": [1, 2]}, {"path": "b.py", "lines": [7, 9]}],
                200,
            )

        result = golden_eval.evaluate(self._queries(), run, k=5)
        assert (result.total, result.top1, result.topk) == (2, 1, 2)
        assert result.top1_rate == 0.5
        assert result.topk_rate == 1.0
        assert result.avg_tokens == 150.0

    def test_hits_beyond_k_are_ignored(self) -> None:
        def run(query, k):
            return [{"path": "z.py", "lines": [1, 2]}, {"path": "a.py", "lines": [1, 5]}], 10

        queries = (golden_eval.GoldenQuery("q1", "hve", "symbol", (_expect(line=3),)),)
        assert golden_eval.evaluate(queries, run, k=1).topk == 0
        assert golden_eval.evaluate(queries, run, k=2).topk == 1

    def test_latency_is_recorded_per_query(self) -> None:
        def run(query, k):
            return [], 0

        result = golden_eval.evaluate(self._queries(), run)
        assert len(result.latencies_ms) == 2
        assert result.avg_latency_ms >= 0.0
        assert result.max_latency_ms >= result.avg_latency_ms

    def test_report_dict_is_serialisable(self) -> None:
        def run(query, k):
            return [], 0

        report = golden_eval.evaluate(self._queries(), run).to_dict()
        assert json.loads(json.dumps(report))["total"] == 2
        assert {"avg_latency_ms", "max_latency_ms"} <= set(report)


class TestRepositoryGoldenSet:
    def test_golden_set_exists_and_validates(self) -> None:
        queries = golden_eval.load_golden(GOLDEN_SET, REPO_ROOT)
        assert len(queries) >= 40
        per_profile = {p: sum(1 for q in queries if q.profile == p) for p in golden_eval.PROFILES}
        assert per_profile["hve"] >= 20
        assert per_profile["app"] >= 20

    def test_golden_set_covers_every_intent(self) -> None:
        queries = golden_eval.load_golden(GOLDEN_SET, REPO_ROOT)
        assert {q.intent for q in queries} == set(golden_eval.INTENTS)

    def test_generated_inventory_expectations_require_an_anchor(self) -> None:
        """再生成で行がずれる生成物は anchor 必須（fail-closed 検出のため）。"""
        for query in golden_eval.load_golden(GOLDEN_SET, REPO_ROOT):
            for expectation in query.expectations:
                if expectation.path.endswith(".csv"):
                    assert expectation.anchor, f"{query.query}: {expectation.path} needs an anchor"
