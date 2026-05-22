"""T2.2: mdq.usage_stats.aggregate_usage_stats の単体テスト。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from mdq import usage_stats


def _make_search(*, q: str = "x", paths: List[str] | None = None,
                  hit_count: int = 1, snippet_chars: int = 100,
                  source_file_chars: int = 1000,
                  elapsed_ms: int = 10, top_k: int = 5, max_tokens: int = 800,
                  snippet_radius: int = 2, include_parent: bool = False,
                  expand_neighbors: int = 0, merge_parts: bool = False,
                  workflow_id: str | None = None, step_id: str | None = None,
                  ts: str = "2026-05-14T00:00:00+00:00") -> Dict[str, Any]:
    rec: Dict[str, Any] = {
        "ts": ts,
        "command": "search",
        "args": {
            "q": q, "paths": paths or [], "top_k": top_k,
            "max_tokens": max_tokens, "snippet_radius": snippet_radius,
            "include_parent": include_parent,
            "expand_neighbors": expand_neighbors,
            "merge_parts": merge_parts,
        },
        "elapsed_ms": elapsed_ms,
        "result": {"hit_count": hit_count, "snippet_chars": snippet_chars,
                   "source_file_chars": source_file_chars},
        "exit_code": 0,
    }
    if workflow_id or step_id:
        rec["context"] = {}
        if workflow_id:
            rec["context"]["workflow_id"] = workflow_id
        if step_id:
            rec["context"]["step_id"] = step_id
    return rec


def test_empty_records_returns_safe_nones(tmp_path: Path) -> None:
    r = usage_stats.aggregate_usage_stats(tmp_path, records=[])
    assert r["record_count"] == 0
    assert r["B1_context_reduction_ratio"]["value"] is None
    assert r["B3_get_search_ratio"]["value"] is None
    assert r["C1_zero_hit_rate"]["value"] is None
    assert r["F1_search_elapsed_ms"]["p50"] is None
    assert r["F2_index_delta_update_ratio"]["value"] is None


def test_a1_command_counts(tmp_path: Path) -> None:
    records = [
        _make_search(),
        _make_search(),
        {"ts": "t", "command": "get", "args": {}, "elapsed_ms": 1,
         "result": {"found": True, "body_chars": 100}, "exit_code": 0},
        {"ts": "t", "command": "stats", "args": {}, "elapsed_ms": 1,
         "result": {"files": 1, "chunks": 1}, "exit_code": 0},
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    assert r["A1_command_counts"] == {"search": 2, "get": 1, "stats": 1}


def test_a2_calls_per_step(tmp_path: Path) -> None:
    records = [
        _make_search(workflow_id="aad-web", step_id="s1"),
        _make_search(workflow_id="aad-web", step_id="s1"),
        _make_search(workflow_id="aad-web", step_id="s2"),
        _make_search(workflow_id="adfd", step_id="s9"),  # 別 workflow も対象
        _make_search(workflow_id=None, step_id=None),    # step_id 無しは対象外
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    a2 = r["A2_calls_per_step"]
    assert a2["total_calls"] == 4
    assert a2["distinct_steps"] == 3
    assert a2["value"] == round(4 / 3, 2)


def test_d1_donot_use_for_violation_detection(tmp_path: Path) -> None:
    records = [
        _make_search(paths=["knowledge/D01-*.md"]),       # 違反
        _make_search(paths=["knowledge/D21-*.md"]),       # 違反
        _make_search(paths=["docs/*"]),                    # OK
        _make_search(paths=[]),                            # OK
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    assert r["D1_donot_use_for_violations"] == 2


def test_b1_context_reduction_ratio(tmp_path: Path) -> None:
    records = [
        _make_search(snippet_chars=100, source_file_chars=1000),
        _make_search(snippet_chars=200, source_file_chars=1000),
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    b1 = r["B1_context_reduction_ratio"]
    # 1 - (100+200)/(1000+1000) = 1 - 0.15 = 0.85
    assert b1["value"] == pytest.approx(0.85, abs=1e-4)
    assert b1["snippet_chars"] == 300
    assert b1["source_file_chars"] == 2000


def test_b2_arg_averages(tmp_path: Path) -> None:
    records = [
        _make_search(top_k=3, max_tokens=400, snippet_radius=1),
        _make_search(top_k=7, max_tokens=800, snippet_radius=3),
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    b2 = r["B2_arg_averages"]
    assert b2["top_k_avg"] == 5.0
    assert b2["max_tokens_avg"] == 600.0
    assert b2["snippet_radius_avg"] == 2.0
    assert b2["sample_size"] == 2


def test_b3_get_search_ratio(tmp_path: Path) -> None:
    records = [
        _make_search(), _make_search(), _make_search(), _make_search(),
        {"ts": "t", "command": "get", "args": {}, "elapsed_ms": 1,
         "result": {"found": True, "body_chars": 10}, "exit_code": 0},
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    assert r["B3_get_search_ratio"]["value"] == pytest.approx(0.25)


def test_c1_zero_hit_rate(tmp_path: Path) -> None:
    records = [
        _make_search(hit_count=0),
        _make_search(hit_count=0),
        _make_search(hit_count=5),
        _make_search(hit_count=3),
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    assert r["C1_zero_hit_rate"]["value"] == pytest.approx(0.5)


def test_c3_expansion_flag_usage_rate(tmp_path: Path) -> None:
    records = [
        _make_search(include_parent=True),
        _make_search(expand_neighbors=2),
        _make_search(merge_parts=True),
        _make_search(),  # no flags
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    assert r["C3_expansion_flag_usage_rate"]["value"] == pytest.approx(0.75)


def test_f1_search_percentiles(tmp_path: Path) -> None:
    records = [_make_search(elapsed_ms=v) for v in [1, 2, 3, 4, 100]]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    f1 = r["F1_search_elapsed_ms"]
    assert f1["p50"] == pytest.approx(3.0)
    assert f1["sample_size"] == 5
    assert f1["p95"] is not None and f1["p95"] >= f1["p50"]


def test_f2_index_delta_update_ratio(tmp_path: Path) -> None:
    records = [
        {"ts": "t", "command": "index", "args": {}, "elapsed_ms": 100,
         "result": {"files_indexed": 2, "files_skipped": 8,
                    "chunks_written": 5, "pruned_chunks": 1}, "exit_code": 0},
        {"ts": "t", "command": "index", "args": {}, "elapsed_ms": 50,
         "result": {"files_indexed": 0, "files_skipped": 10,
                    "chunks_written": 0, "pruned_chunks": 0}, "exit_code": 0},
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    # (0.2 + 0.0) / 2 = 0.1
    assert r["F2_index_delta_update_ratio"]["value"] == pytest.approx(0.1)
    assert r["E5_pruned_chunks_total"]["value"] == 1


def test_a4_skill_routing_listed_true(tmp_path: Path) -> None:
    p = tmp_path / ".github" / "skills" / "_routing" / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("references markdown-query here", encoding="utf-8")
    r = usage_stats.aggregate_usage_stats(tmp_path, records=[])
    assert r["A4_skill_routing_listed"]["value"] is True


def test_a4_skill_routing_listed_false_when_file_missing(tmp_path: Path) -> None:
    r = usage_stats.aggregate_usage_stats(tmp_path, records=[])
    assert r["A4_skill_routing_listed"]["value"] is False


def test_g1_run_ids_collected(tmp_path: Path) -> None:
    records = [
        {"ts": "t", "command": "search", "args": {}, "elapsed_ms": 1,
         "result": {"hit_count": 1, "snippet_chars": 10,
                    "source_file_chars": 100}, "exit_code": 0,
         "context": {"run_id": "r1"}},
        {"ts": "t", "command": "search", "args": {}, "elapsed_ms": 1,
         "result": {"hit_count": 1, "snippet_chars": 10,
                    "source_file_chars": 100}, "exit_code": 0,
         "context": {"run_id": "r2"}},
        {"ts": "t", "command": "search", "args": {}, "elapsed_ms": 1,
         "result": {"hit_count": 1, "snippet_chars": 10,
                    "source_file_chars": 100}, "exit_code": 0,
         "context": {"run_id": "r1"}},
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    assert r["G1_step_completion_rate_diff"]["run_ids_with_mdq_count"] == 2


# ---------------------------------------------------------------------------
# v2 追加指標
# ---------------------------------------------------------------------------

def _make_state_json(path: Path, statuses: list[str]) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    steps = {f"s{i}": {"step_id": f"s{i}", "status": st}
             for i, st in enumerate(statuses)}
    path.write_text(json.dumps({"schema_version": "x", "step_states": steps}),
                    encoding="utf-8")


def test_c2_score_gap_avg(tmp_path: Path) -> None:
    records = [
        _make_search(),  # score 無し → サンプル外
    ]
    # 手動で score_top / score_2nd を入れる
    records[0]["result"]["score_top"] = 10.0
    records[0]["result"]["score_2nd"] = 4.0
    second = _make_search()
    second["result"]["score_top"] = 5.0
    second["result"]["score_2nd"] = 3.0
    records.append(second)
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    c2 = r["C2_score_gap_avg"]
    # (6.0 + 2.0) / 2 = 4.0
    assert c2["value"] == pytest.approx(4.0)
    assert c2["sample_size"] == 2


def test_c2_score_gap_none_when_no_second(tmp_path: Path) -> None:
    rec = _make_search()
    rec["result"]["score_top"] = 5.0
    # score_2nd 無し → C2 算出不能
    r = usage_stats.aggregate_usage_stats(tmp_path, records=[rec])
    assert r["C2_score_gap_avg"]["value"] is None


def test_g1_diff_computed_from_state_json(tmp_path: Path) -> None:
    runs = tmp_path / "session-state" / "runs"
    _make_state_json(runs / "r-used" / "state.json",
                     ["completed", "completed", "completed", "failed"])  # 0.75
    _make_state_json(runs / "r-unused" / "state.json",
                     ["completed", "failed", "failed", "failed"])  # 0.25
    records = [
        {"ts": "t", "command": "search", "args": {}, "elapsed_ms": 1,
         "result": {"hit_count": 1, "snippet_chars": 10,
                    "source_file_chars": 100}, "exit_code": 0,
         "context": {"run_id": "r-used"}},
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    g1 = r["G1_step_completion_rate_diff"]
    assert g1["used_avg"] == pytest.approx(0.75)
    assert g1["unused_avg"] == pytest.approx(0.25)
    assert g1["value"] == pytest.approx(0.5)
    assert g1["used_run_count"] == 1
    assert g1["unused_run_count"] == 1


def test_g1_returns_none_when_no_state_files(tmp_path: Path) -> None:
    records = [
        {"ts": "t", "command": "search", "args": {}, "elapsed_ms": 1,
         "result": {"hit_count": 1, "snippet_chars": 10,
                    "source_file_chars": 100}, "exit_code": 0,
         "context": {"run_id": "r1"}},
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    g1 = r["G1_step_completion_rate_diff"]
    assert g1["value"] is None
    assert g1["note"]


# ---------------------------------------------------------------------------
# D3 / G4 (Wave 11)
# ---------------------------------------------------------------------------

def _make_state_with_retry(path: Path,
                            steps: list[tuple[str, int]]) -> None:
    """状態 + retry_count を含む state.json を書き出す。"""
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": "x",
        "step_states": {
            f"s{i}": {"step_id": f"s{i}", "status": status,
                       "retry_count": rc}
            for i, (status, rc) in enumerate(steps)
        },
    }
    path.write_text(json.dumps(body), encoding="utf-8")


def _seed_typical_queries(tmp_path: Path) -> None:
    """tmp_path に template/typical-queries.json を作る。"""
    import json
    p = tmp_path / "template" / "typical-queries.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": 1,
        "workflows": {
            "aad-web": [
                {"id": "screen_def", "label": "画面定義",
                 "patterns": ["画面定義", "screen[-_ ]?def"]},
                {"id": "service_def", "label": "サービス定義",
                 "patterns": ["service[-_ ]?def"]},
            ]
        }
    }), encoding="utf-8")


def test_d3_aggregates_across_multiple_workflows(tmp_path: Path) -> None:
    """patterns 定義済み workflow が複数あるとき、合算 micro-average が
    正しく計算されることを検証する（レビュー No.9 対応）。"""
    import json
    p = tmp_path / "template" / "typical-queries.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": 1,
        "workflows": {
            "aad-web": [
                {"id": "screen", "label": "画面", "patterns": ["画面"]},
            ],
            "asdw-web": [
                {"id": "infra", "label": "infra",
                 "patterns": ["infra", "インフラ"]},
            ],
        }
    }), encoding="utf-8")
    records = [
        # aad-web: 4 件中 2 件マッチ
        _make_search(q="画面定義", workflow_id="aad-web", step_id="s1"),
        _make_search(q="画面遷移", workflow_id="aad-web", step_id="s2"),
        _make_search(q="apikey", workflow_id="aad-web", step_id="s3"),
        _make_search(q="無関係", workflow_id="aad-web", step_id="s4"),
        # asdw-web: 2 件中 2 件マッチ
        _make_search(q="infra 設計", workflow_id="asdw-web", step_id="s5"),
        _make_search(q="インフラ運用", workflow_id="asdw-web", step_id="s6"),
        # adfd: patterns 未定義 → 合算に含まれない
        _make_search(q="batch", workflow_id="adfd", step_id="s7"),
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    d3 = r["D3_typical_query_rate"]
    # micro-average: (2+2)/(4+2) = 4/6
    assert d3["matched_count"] == 4
    assert d3["total_search"] == 6
    assert d3["value"] == pytest.approx(4 / 6, abs=1e-4)
    assert d3["per_workflow"]["aad-web"]["value"] == pytest.approx(0.5, abs=1e-4)
    assert d3["per_workflow"]["asdw-web"]["value"] == pytest.approx(1.0, abs=1e-4)
    # patterns 未定義 workflow の total_search は 0（集計対象外を明示）
    assert d3["per_workflow"]["adfd"]["total_search"] == 0
    assert d3["per_workflow"]["adfd"]["value"] is None


def test_d3_target_workflows_match_orchestrator_constant() -> None:
    """_D3_TARGET_WORKFLOWS が hve/orchestrator.py の _ARCH_FILTER_WORKFLOWS と
    集合として一致することを検証する（レビュー No.12 対応: 手動同期チェック）。

    `_ARCH_FILTER_WORKFLOWS` は orchestrator.py の関数内ローカル変数のため
    import 不可。ソースをテキスト走査して定義行から集合を抽出する。
    """
    import re
    from mdq.usage_stats import _D3_TARGET_WORKFLOWS  # type: ignore[attr-defined]
    orch = Path(__file__).resolve().parents[1] / "orchestrator.py"
    src = orch.read_text(encoding="utf-8")
    m = re.search(r"_ARCH_FILTER_WORKFLOWS\s*=\s*\{([^}]+)\}", src)
    assert m, "hve/orchestrator.py:_ARCH_FILTER_WORKFLOWS の定義が見つからない"
    arch_filter = set(re.findall(r'"([^"]+)"', m.group(1)))
    assert set(_D3_TARGET_WORKFLOWS) == arch_filter, (
        "mdq/usage_stats.py:_D3_TARGET_WORKFLOWS と "
        "hve/orchestrator.py:_ARCH_FILTER_WORKFLOWS の同期が崩れています"
    )


def test_d3_typical_query_rate(tmp_path: Path) -> None:
    _seed_typical_queries(tmp_path)
    records = [
        _make_search(q="画面定義書を探す", workflow_id="aad-web", step_id="s1"),
        _make_search(q="service-def の場所", workflow_id="aad-web", step_id="s2"),
        _make_search(q="全く関係ない言葉", workflow_id="aad-web", step_id="s3"),
        _make_search(q="screen-def", workflow_id="adfd"),  # patterns 未定義 workflow
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    d3 = r["D3_typical_query_rate"]
    # aad-web の 3 件中 2 件マッチ → 合算 2/3（adfd は patterns 未定義のため分母除外）
    assert d3["total_search"] == 3
    assert d3["matched_count"] == 2
    assert d3["value"] == pytest.approx(2 / 3, abs=1e-4)
    aad = d3["per_workflow"]["aad-web"]
    assert aad["total_search"] == 3
    assert aad["matched_count"] == 2
    assert aad["value"] == pytest.approx(2 / 3, abs=1e-4)
    labels = {p["id"] for p in aad["per_pattern"]}
    assert labels == {"screen_def", "service_def"}
    # adfd は patterns 未定義 → value=None + note
    adfd = d3["per_workflow"]["adfd"]
    assert adfd["value"] is None
    assert "未定義" in (adfd["note"] or "")
    # 4 つの workflow すべてが per_workflow に出現
    assert set(d3["per_workflow"].keys()) == {"aad-web", "asdw-web", "adfd", "adfdv"}


def test_d3_returns_none_when_no_dictionary(tmp_path: Path) -> None:
    # template/typical-queries.json を作らない
    r = usage_stats.aggregate_usage_stats(tmp_path, records=[
        _make_search(q="x", workflow_id="aad-web"),
    ])
    d3 = r["D3_typical_query_rate"]
    assert d3["value"] is None
    assert d3["note"]
    # 全 workflow が per_workflow に出現する（patterns 未定義扱い）
    for wf in ("aad-web", "asdw-web", "adfd", "adfdv"):
        assert d3["per_workflow"][wf]["value"] is None


def test_d3_rejects_schema_version_mismatch(tmp_path: Path) -> None:
    """schema_version が 1 でない辞書は読み込まない。"""
    import json
    p = tmp_path / "template" / "typical-queries.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": 2,  # 未対応
        "workflows": {"aad-web": [
            {"id": "x", "label": "x", "patterns": ["x"]},
        ]},
    }), encoding="utf-8")
    r = usage_stats.aggregate_usage_stats(tmp_path, records=[
        _make_search(q="x", workflow_id="aad-web"),
    ])
    assert r["D3_typical_query_rate"]["value"] is None


def test_d1_strict_pattern_for_knowledge_dnn(tmp_path: Path) -> None:
    """D1 は ``knowledge/D\\d{2}`` 形式のみを違反扱いとする。"""
    records = [
        _make_search(paths=["knowledge/D01-foo.md"]),         # 違反
        _make_search(paths=["knowledge/D21/bar.md"]),         # 違反
        _make_search(paths=["knowledge/Definitions/x.md"]),   # 違反でない
        _make_search(paths=["knowledge/Data-foo.md"]),        # 違反でない
        _make_search(paths=["docs/business-requirement.md"]),
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    assert r["D1_donot_use_for_violations"] == 2


def test_g1_excludes_pending_running_steps(tmp_path: Path) -> None:
    """G1 母数は completed/failed/skipped のみ。pending/running は除外。"""
    runs = tmp_path / "session-state" / "runs"
    # 利用 run: 完了 2 / 失敗 1 / running 5（除外） → 2/3 = 0.667
    _make_state_json(runs / "r-used" / "state.json",
                     ["completed", "completed", "failed",
                      "running", "running", "running", "running", "running"])
    # 未利用 run: 完了 1 / 失敗 1 → 0.5
    _make_state_json(runs / "r-unused" / "state.json",
                     ["completed", "failed"])
    records = [
        {"ts": "t", "command": "search", "args": {}, "elapsed_ms": 1,
         "result": {"hit_count": 1, "snippet_chars": 10,
                    "source_file_chars": 100}, "exit_code": 0,
         "context": {"run_id": "r-used"}},
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    g1 = r["G1_step_completion_rate_diff"]
    assert g1["used_avg"] == pytest.approx(2 / 3, abs=1e-4)
    assert g1["unused_avg"] == pytest.approx(0.5)


def test_d3_returns_none_when_no_aad_searches(tmp_path: Path) -> None:
    _seed_typical_queries(tmp_path)
    r = usage_stats.aggregate_usage_stats(tmp_path, records=[
        _make_search(q="x", workflow_id="adfd"),  # patterns 未定義 workflow のみ
    ])
    d3 = r["D3_typical_query_rate"]
    # patterns 定義済み workflow（aad-web）の search が 0 件のため合算 value=None
    assert d3["value"] is None
    assert d3["total_search"] == 0
    assert d3["per_workflow"]["aad-web"]["total_search"] == 0


def test_g4_retry_count_diff_computed(tmp_path: Path) -> None:
    runs = tmp_path / "session-state" / "runs"
    # 利用 run: 平均 retry = 1.5
    _make_state_with_retry(runs / "r-used" / "state.json",
                            [("completed", 1), ("completed", 2)])
    # 未利用 run: 平均 retry = 0.5
    _make_state_with_retry(runs / "r-unused" / "state.json",
                            [("completed", 0), ("completed", 1)])
    records = [
        {"ts": "t", "command": "search", "args": {}, "elapsed_ms": 1,
         "result": {"hit_count": 1, "snippet_chars": 10,
                    "source_file_chars": 100}, "exit_code": 0,
         "context": {"run_id": "r-used"}},
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    g4 = r["G4_step_retry_count_diff"]
    assert g4["used_avg"] == pytest.approx(1.5)
    assert g4["unused_avg"] == pytest.approx(0.5)
    assert g4["value"] == pytest.approx(1.0)


def test_g4_none_when_only_one_group(tmp_path: Path) -> None:
    runs = tmp_path / "session-state" / "runs"
    _make_state_with_retry(runs / "r-used" / "state.json",
                            [("completed", 1)])
    records = [
        {"ts": "t", "command": "search", "args": {}, "elapsed_ms": 1,
         "result": {"hit_count": 1, "snippet_chars": 10,
                    "source_file_chars": 100}, "exit_code": 0,
         "context": {"run_id": "r-used"}},
    ]
    r = usage_stats.aggregate_usage_stats(tmp_path, records=records)
    g4 = r["G4_step_retry_count_diff"]
    assert g4["value"] is None
    assert g4["note"]
