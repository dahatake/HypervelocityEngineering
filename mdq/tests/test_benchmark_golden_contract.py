"""FR-MDQ-01 contract between benchmark.py and mdq.golden_eval."""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

from mdq import golden_eval

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = REPO_ROOT / "tools" / "skills" / "markdown_query" / "benchmark.py"


def _tree() -> ast.Module:
    return ast.parse(BENCHMARK.read_text(encoding="utf-8-sig"))


def _module():
    spec = importlib.util.spec_from_file_location("_mdq_benchmark_contract", BENCHMARK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_benchmark_imports_the_shared_evaluator() -> None:
    imports = [node for node in ast.walk(_tree()) if isinstance(node, ast.ImportFrom)]
    assert any(
        node.module == "mdq" and any(alias.name == "golden_eval" for alias in node.names)
        for node in imports
    )


def test_benchmark_does_not_reimplement_correctness_judgement() -> None:
    forbidden = {
        "hit_matches",
        "rank_of_first_correct",
        "score_query",
        "is_correct",
        "validate_golden",
    }
    definitions = {
        node.name
        for node in ast.walk(_tree())
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert definitions.isdisjoint(forbidden)


def test_benchmark_loads_golden_with_an_explicit_repo_root() -> None:
    source = BENCHMARK.read_text(encoding="utf-8-sig")
    assert "golden_eval.load_golden(golden_path, REPO_ROOT)" in source


def test_report_contract_records_all_database_paths_and_provenance() -> None:
    source = BENCHMARK.read_text(encoding="utf-8-sig")
    assert '"database_paths"' in source
    assert '"provenance"' in source
    for key in ("engine_sha256", "config_sha256", "golden_sha256"):
        assert key in source


def test_search_scenario_calls_the_shared_score_query(monkeypatch) -> None:
    benchmark = _module()

    class FakeHit:
        path = "a.md"
        start_line = 2
        end_line = 4

        def to_dict(self):
            return {"path": self.path, "start_line": self.start_line, "end_line": self.end_line}

    monkeypatch.setattr(benchmark.searcher, "search", lambda *args, **kwargs: [FakeHit()])
    calls = []
    original = benchmark.golden_eval.score_query

    def spy(hits, expected, top_k):
        calls.append((hits, expected, top_k))
        return original(hits, expected, top_k)

    monkeypatch.setattr(benchmark.golden_eval, "score_query", spy)
    result = benchmark.run_search_scenario(
        None,
        "bm25",
        [{
            "id": "Q",
            "q": "alpha",
            "group": "unit",
            "expected_hits": [golden_eval.ExpectedHit("a.md", 3)],
        }],
        top_k=5,
        max_tokens=100,
        repeat=1,
        path_globs=None,
        baseline_tokens_total=0,
    )
    assert len(calls) == 1
    assert result["per_query"][0]["top1"] is True


def test_report_path_outside_repository_is_rendered_as_absolute(tmp_path: Path) -> None:
    benchmark = _module()
    report = tmp_path / "outside" / "report.json"
    rendered = benchmark._report_path_for_summary(report)
    assert rendered == str(report.resolve())


def test_report_path_inside_repository_is_rendered_as_relative() -> None:
    benchmark = _module()
    report = REPO_ROOT / "tools" / "skills" / "markdown_query" / "results" / "x.json"
    assert benchmark._report_path_for_summary(report) == (
        "tools/skills/markdown_query/results/x.json"
    )


def _minimal_report(golden: dict) -> dict:
    return {
        "started_at": "2026-01-01T00:00:00Z",
        "env": {"tokenizer": "t", "python": "3.13", "platform": "p", "commit": None},
        "params": {"queries_count": 1, "top_k": 5},
        "index": None,
        "baseline_full": None,
        "scenarios": {
            "mdq_bm25": {
                "queries": 1,
                "total_hits": 1,
                "avg_response_tokens": 10,
                "avg_vs_baseline_savings_pct": None,
                "latency_ms_all": {"mean": 1.0, "p50": 1.0, "p95": None},
                "golden": golden,
                "per_query": [
                    {
                        "query": "alpha",
                        "hits": 1,
                        "response_tokens": 10,
                        "vs_baseline_savings_pct": None,
                        "latency_ms": {"mean": 1.0, "p95": None},
                        "coverage_proxy": None,
                        "rank": 1,
                    }
                ],
            }
        },
    }


def test_golden_summary_carries_mrr(monkeypatch) -> None:
    """FR-MDQ-04: ベンチマークのゴールデン集計が MRR@k を持つこと。"""
    benchmark = _module()

    class FakeHit:
        path = "a.md"
        start_line = 2
        end_line = 4

        def to_dict(self):
            return {"path": self.path, "start_line": self.start_line, "end_line": self.end_line}

    monkeypatch.setattr(benchmark.searcher, "search", lambda *args, **kwargs: [FakeHit()])
    result = benchmark.run_search_scenario(
        None,
        "bm25",
        [{
            "id": "Q",
            "q": "alpha",
            "group": "unit",
            "expected_hits": [golden_eval.ExpectedHit("a.md", 3)],
        }],
        top_k=5,
        max_tokens=100,
        repeat=1,
        path_globs=None,
        baseline_tokens_total=0,
    )
    assert result["golden"]["overall"]["mrr_at_k"] == 1.0


def test_markdown_report_renders_mrr(tmp_path: Path) -> None:
    """FR-MDQ-04: MRR@k がレポートへ出力されること。"""
    benchmark = _module()
    report = _minimal_report(
        {
            "overall": {"queries": 1, "k": 5, "top1_accuracy": 1.0,
                        "topk_accuracy": 1.0, "mrr_at_k": 1.0},
            "per_group": {},
        }
    )
    out = tmp_path / "bench.md"
    benchmark.write_markdown(report, out)
    text = out.read_text(encoding="utf-8")
    assert "MRR@" in text


def _capture_path_globs(benchmark, monkeypatch) -> list:
    seen: list = []

    def fake_search(conn, query, **kwargs):
        seen.append(kwargs.get("path_globs"))
        return []

    monkeypatch.setattr(benchmark.searcher, "search", fake_search)
    return seen


_GOLDEN_ENTRY = {
    "id": "Q",
    "q": "alpha",
    "group": "unit",
    "paths": ["docs/*"],
    "expected_hits": [],
}


def test_default_condition_applies_the_golden_path_filter(monkeypatch) -> None:
    """FR-MDQ-04: 既定はゴールデンの対象パス絞り込みを適用する条件。"""
    benchmark = _module()
    seen = _capture_path_globs(benchmark, monkeypatch)
    benchmark.run_search_scenario(
        None, "bm25", [dict(_GOLDEN_ENTRY)],
        top_k=5, max_tokens=100, repeat=1, path_globs=None,
        baseline_tokens_total=0,
    )
    assert seen and all(globs == ["docs/*"] for globs in seen)


def test_broad_condition_ignores_the_golden_path_filter(monkeypatch) -> None:
    """FR-MDQ-04: 絞り込みを適用せずリポジトリ全体を候補にできること。"""
    benchmark = _module()
    seen = _capture_path_globs(benchmark, monkeypatch)
    benchmark.run_search_scenario(
        None, "bm25", [dict(_GOLDEN_ENTRY)],
        top_k=5, max_tokens=100, repeat=1, path_globs=None,
        baseline_tokens_total=0, ignore_golden_paths=True,
    )
    assert seen and all(globs is None for globs in seen)


def test_report_params_distinguish_the_two_conditions() -> None:
    """FR-MDQ-04: どちらの条件で計測したかがレポート上で区別できること。"""
    benchmark = _module()
    args = benchmark.parse_args(["--q", "alpha", "--ignore-golden-paths"])
    report = benchmark.build_report(args, [], None, {}, None, "s", "f", {})
    assert report["params"]["ignore_golden_paths"] is True
