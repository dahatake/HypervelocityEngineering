"""T2.4: tools/skills/markdown_query/generate_usage_report.py のテスト。"""

from __future__ import annotations

import datetime
import importlib.util
import json
import sys
from pathlib import Path

import pytest


_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "tools" / "skills" / "markdown_query" / "generate_usage_report.py"
)


@pytest.fixture()
def gen_module():
    """generate_usage_report.py をモジュールとしてロードする。"""
    spec = importlib.util.spec_from_file_location(
        "generate_usage_report", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_generate_report_creates_four_files(gen_module, tmp_path: Path) -> None:
    out = gen_module.generate_report(tmp_path, window_days=7,
                                      today=datetime.date(2026, 5, 15),
                                      output_dir=tmp_path / "usage-report")
    for key in ("json", "md", "latest_json", "latest_md"):
        assert out[key].exists(), f"{key} not created"
    assert out["json"].name == "2026-05-15.json"
    assert out["md"].name == "2026-05-15.md"
    assert out["latest_json"].name == "latest.json"
    assert out["latest_md"].name == "latest.md"


def test_generated_json_is_valid_schema(gen_module, tmp_path: Path) -> None:
    out = gen_module.generate_report(tmp_path, today=datetime.date(2026, 5, 15),
                                      output_dir=tmp_path / "usage-report")
    data = json.loads(out["json"].read_text(encoding="utf-8"))
    # 必須キー（15 指標）
    for k in (
        "E1_index_size", "E2_index_freshness", "E5_pruned_chunks_total",
        "F2_index_delta_update_ratio",
        "A1_command_counts", "A2_calls_per_step",
        "A4_skill_routing_listed", "D1_donot_use_for_violations",
        "B1_context_reduction_ratio", "B2_arg_averages", "B3_get_search_ratio",
        "C1_zero_hit_rate", "C2_score_gap_avg", "C3_expansion_flag_usage_rate",
        "F1_search_elapsed_ms", "G1_step_completion_rate_diff",
        "G4_step_retry_count_diff", "D3_typical_query_rate",
    ):
        assert k in data, f"missing key: {k}"
    assert data["schema_version"] == 1
    assert "generated_at" in data


def test_generated_markdown_contains_section_headings(gen_module, tmp_path: Path) -> None:
    out = gen_module.generate_report(tmp_path, today=datetime.date(2026, 5, 15),
                                      output_dir=tmp_path / "usage-report")
    md = out["md"].read_text(encoding="utf-8")
    assert "# markdown-query Skill 利用統計レポート" in md
    assert "① 基盤・索引" in md
    assert "② 呼び出し量・選択妥当性" in md
    assert "③ Context 削減" in md
    assert "④ 結果品質" in md
    assert "⑤ パフォーマンス / 成果" in md


def test_latest_files_match_dated_files(gen_module, tmp_path: Path) -> None:
    out = gen_module.generate_report(tmp_path, today=datetime.date(2026, 5, 15),
                                      output_dir=tmp_path / "usage-report")
    assert out["json"].read_bytes() == out["latest_json"].read_bytes()
    assert out["md"].read_bytes() == out["latest_md"].read_bytes()


def test_render_markdown_handles_none_values_gracefully(gen_module) -> None:
    stats = {
        "schema_version": 1, "window_days": 7, "since_iso": "x",
        "record_count": 0,
        "E1_index_size": {"files": None, "chunks": None, "note": "x"},
        "E2_index_freshness": {"age_seconds": None, "db_mtime": None,
                                "note": "x"},
        "E5_pruned_chunks_total": {"value": 0, "window_records": 0,
                                    "note": None},
        "F2_index_delta_update_ratio": {"value": None, "sample_size": 0,
                                          "note": "x"},
        "A1_command_counts": {},
        "A2_calls_per_step": {"value": None, "total_calls": 0,
                                       "distinct_steps": 0, "note": "x"},
        "A4_skill_routing_listed": {"value": False, "note": None},
        "D1_donot_use_for_violations": 0,
        "B1_context_reduction_ratio": {"value": None, "snippet_chars": 0,
                                         "source_file_chars": 0, "note": "x"},
        "B2_arg_averages": {"top_k_avg": None, "max_tokens_avg": None,
                             "snippet_radius_avg": None, "sample_size": 0},
        "B3_get_search_ratio": {"value": None, "get_count": 0,
                                 "search_count": 0, "note": "x"},
        "C1_zero_hit_rate": {"value": None, "note": "x"},
        "C2_score_gap_avg": {"value": None, "sample_size": 0, "note": "x"},
        "C3_expansion_flag_usage_rate": {"value": None, "note": "x"},
        "F1_search_elapsed_ms": {"p50": None, "p95": None,
                                  "sample_size": 0, "note": "x"},
        "G1_step_completion_rate_diff": {"value": None,
                                          "used_avg": None,
                                          "unused_avg": None,
                                          "used_run_count": 0,
                                          "unused_run_count": 0,
                                          "run_ids_with_mdq_count": 0,
                                          "note": "x"},
        "G4_step_retry_count_diff": {"value": None,
                                       "used_avg": None,
                                       "unused_avg": None,
                                       "used_run_count": 0,
                                       "unused_run_count": 0,
                                       "note": "x"},
        "D3_typical_query_rate": {"value": None,
                                    "matched_count": 0,
                                    "total_search": 0,
                                    "per_workflow": {},
                                    "note": "x"},
    }
    md = gen_module.render_markdown(stats)
    # None は「（データ不足）」と置換されていること
    assert "（データ不足）" in md
    # E1 関連ラベルがいずれか出現（テーブル化されても項目名は残る）
    assert "E1 索引サイズ" in md


# ---------------------------------------------------------------------------
# T8.2 retention_days 削除挙動
# ---------------------------------------------------------------------------

def _seed_dated_files(out_dir: Path, dates: list[str]) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for d in dates:
        for ext in ("json", "md"):
            p = out_dir / f"{d}.{ext}"
            p.write_text("dummy", encoding="utf-8")
            paths.append(p)
    return paths


def test_retention_deletes_old_dated_files(gen_module, tmp_path: Path) -> None:
    out_dir = tmp_path / "tools" / "skills" / "markdown_query" / "usage-report"
    today = datetime.date(2026, 5, 15)
    seeded = _seed_dated_files(out_dir, [
        "2026-01-01",  # 134 日前 → 削除
        "2026-02-01",  # 103 日前 → 削除
        "2026-04-01",  # 44 日前 → 残す
        "2026-05-10",  # 5 日前 → 残す
    ])
    result = gen_module.generate_report(tmp_path, today=today,
                                          retention_days=90,
                                          output_dir=out_dir)
    pruned_names = {Path(p).name for p in result["pruned"]}
    assert "2026-01-01.json" in pruned_names
    assert "2026-01-01.md" in pruned_names
    assert "2026-02-01.json" in pruned_names
    assert "2026-04-01.json" not in pruned_names
    assert "2026-05-10.json" not in pruned_names
    # 削除確認
    assert not (out_dir / "2026-01-01.json").exists()
    assert (out_dir / "2026-04-01.json").exists()
    # latest.* は常に保持
    assert (out_dir / "latest.json").exists()
    assert (out_dir / "latest.md").exists()


def test_retention_zero_disables_deletion(gen_module, tmp_path: Path) -> None:
    out_dir = tmp_path / "tools" / "skills" / "markdown_query" / "usage-report"
    today = datetime.date(2026, 5, 15)
    _seed_dated_files(out_dir, ["2020-01-01"])
    result = gen_module.generate_report(tmp_path, today=today,
                                          retention_days=0,
                                          output_dir=out_dir)
    assert result["pruned"] == []
    assert (out_dir / "2020-01-01.json").exists()


def test_retention_preserves_latest_and_unrelated_files(gen_module,
                                                          tmp_path: Path) -> None:
    out_dir = tmp_path / "tools" / "skills" / "markdown_query" / "usage-report"
    out_dir.mkdir(parents=True, exist_ok=True)
    # ``README.md`` のような関係ない既存ファイルが削除されないこと
    (out_dir / "README.md").write_text("readme", encoding="utf-8")
    (out_dir / "notes.txt").write_text("notes", encoding="utf-8")
    _seed_dated_files(out_dir, ["2020-01-01"])
    today = datetime.date(2026, 5, 15)
    gen_module.generate_report(tmp_path, today=today, retention_days=30,
                                output_dir=out_dir)
    assert (out_dir / "README.md").exists()
    assert (out_dir / "notes.txt").exists()
    assert not (out_dir / "2020-01-01.json").exists()
