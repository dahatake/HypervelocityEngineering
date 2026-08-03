"""Contracts for the cq benchmark harness (FR-CQ-02).

The harness must measure the control groups (grep-style line scan and whole-file
reads) in the same run so that improvements are comparable, must report cold and
warm latency, and must delegate correctness to the single oracle in
:mod:`cq.golden_eval`.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from cq import benchmark, golden_eval

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_SOURCE = REPO_ROOT / "cq" / "benchmark.py"


def _query(text: str = "resolve", intent: str = "symbol") -> golden_eval.GoldenQuery:
    return golden_eval.GoldenQuery(
        text, "hve", intent, (golden_eval.Expectation("pkg/mod.py", 2),)
    )


@pytest.fixture()
def corpus(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(
        "import os\ndef resolve(x):\n    return x\n" + "# filler\n" * 50,
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "other.py").write_text("value = 1\n", encoding="utf-8")
    return tmp_path


ALL_PATHS = ("pkg/mod.py", "pkg/other.py")


class TestControlGroups:
    def test_grep_baseline_returns_line_hits(self, corpus: Path) -> None:
        hits, count = benchmark.grep_baseline(_query(), corpus, ALL_PATHS)
        assert hits and hits[0]["path"] == "pkg/mod.py"
        assert hits[0]["lines"] == [2, 2]
        assert count > 0

    def test_grep_baseline_is_scored_by_the_shared_oracle(self, corpus: Path) -> None:
        query = _query()
        hits, _ = benchmark.grep_baseline(query, corpus, ALL_PATHS)
        assert golden_eval.is_correct(hits[0], query.expectations) is True

    def test_regex_intent_is_matched_as_regex(self, corpus: Path) -> None:
        """対照群を不当に弱めない: regex 意図のクエリは正規表現として扱う。"""
        query = _query("^def resolve", intent="regex")
        hits, _ = benchmark.grep_baseline(query, corpus, ALL_PATHS)
        assert [h["lines"] for h in hits] == [[2, 2]]

    def test_invalid_regex_falls_back_to_substring(self, corpus: Path) -> None:
        query = _query("resolve(x", intent="regex")
        hits, _ = benchmark.grep_baseline(query, corpus, ALL_PATHS)
        assert [h["lines"] for h in hits] == [[2, 2]]

    def test_readfile_baseline_returns_whole_files(self, corpus: Path) -> None:
        hits, count = benchmark.readfile_baseline(_query(), corpus, ALL_PATHS)
        assert hits[0]["lines"] == [1, 53]
        assert count > 0

    def test_readfile_baseline_costs_more_tokens_than_grep(self, corpus: Path) -> None:
        _, grep_tokens = benchmark.grep_baseline(_query(), corpus, ("pkg/mod.py",))
        _, read_tokens = benchmark.readfile_baseline(_query(), corpus, ("pkg/mod.py",))
        assert read_tokens > grep_tokens


class TestReport:
    def test_report_includes_every_control_group(self, corpus: Path) -> None:
        report = benchmark.run_baselines((_query(),), corpus, ALL_PATHS, k=5)
        assert set(report) == {"grep", "readfile"}
        for group in report.values():
            assert {"total", "top1_rate", "topk_rate", "avg_tokens"} <= set(group)

    def test_report_includes_cold_and_warm_latency(self, corpus: Path) -> None:
        report = benchmark.run_baselines((_query(),), corpus, ALL_PATHS, k=5)
        for group in report.values():
            assert group["cold_avg_latency_ms"] >= 0.0
            assert group["warm_avg_latency_ms"] >= 0.0

    def test_report_declares_which_token_counter_was_used(self, corpus: Path) -> None:
        report = benchmark.run_baselines((_query(),), corpus, ALL_PATHS, k=5)
        for group in report.values():
            assert group["token_counter"] in {"tiktoken/cl100k_base", "chars/4-approx"}

    def test_unknown_control_group_is_rejected(self, corpus: Path) -> None:
        with pytest.raises(benchmark.BenchmarkError, match="unknown control group"):
            benchmark.run_baselines((_query(),), corpus, ALL_PATHS, names=("nope",))

    def test_report_is_serialisable(self, corpus: Path) -> None:
        report = benchmark.run_baselines((_query(),), corpus, ("pkg/mod.py",), k=5)
        assert json.loads(json.dumps(report))["grep"]["total"] == 1


class TestCli:
    def test_invalid_paths_filter_is_reported(self, corpus: Path) -> None:
        with pytest.raises(benchmark.BenchmarkError, match="not a valid regex"):
            benchmark.main([
                "--golden", str(REPO_ROOT / "cq" / "golden-queries.json"),
                "--repo-root", str(REPO_ROOT), "--paths", "([",
            ])


class TestResponseCost:
    """FR-CQ-02: 応答トークン数は呼び出し側が受け取る応答表現で数える。"""

    def test_cq_runner_counts_the_serialised_response(self, corpus: Path, monkeypatch) -> None:
        from cq import search as cq_search, tokens

        class _Hit:
            path = "pkg/mod.py"
            lines = [2, 3]
            snippet = "def resolve(x):"

            def to_dict(self):
                return {
                    "path": self.path,
                    "lines": self.lines,
                    "route": "symbol",
                    "score": 1.0,
                    "snippet": self.snippet,
                    "qualname": "resolve",
                    "signature": "def resolve(x)",
                }

        monkeypatch.setattr(cq_search, "search", lambda *a, **k: [_Hit()])
        run = benchmark.cq_runner(corpus, "hve")
        hits, counted = run(_query(), 5)
        serialised = json.dumps(hits[0], ensure_ascii=False)
        assert counted >= tokens.count_tokens(serialised)
        assert counted > tokens.count_tokens(_Hit.snippet)


class TestSingleOracle:
    def test_benchmark_does_not_reimplement_correctness(self) -> None:
        """正解判定は cq.golden_eval に単一実装する（独自判定を持たない）。"""
        tree = ast.parse(BENCHMARK_SOURCE.read_text(encoding="utf-8"))
        defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert "is_correct" not in defined
        assert "evaluate" not in defined
        assert "golden_eval" in BENCHMARK_SOURCE.read_text(encoding="utf-8")
