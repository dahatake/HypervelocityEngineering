import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2]
BENCH_PY = SOURCE / "bench" / "bench.py"

spec = importlib.util.spec_from_file_location("hve_bench", BENCH_PY)
bench = importlib.util.module_from_spec(spec)
sys.modules["hve_bench"] = bench
spec.loader.exec_module(bench)


def run(*args):
    return subprocess.run([sys.executable, str(BENCH_PY), *args], capture_output=True,
                          text=True, encoding="utf-8")


def test_prepare_refuses_nonempty_and_inside_repo(tmp_path):
    (tmp_path / "x.txt").write_text("x")
    assert run("prepare", "--task", "T1", "--dest", str(tmp_path)).returncode != 0
    assert run("prepare", "--task", "T1", "--dest", str(SOURCE / "work" / "bench-inside")).returncode != 0


def test_prepare_t3_contains_only_task_and_seed(tmp_path):
    dest = tmp_path / "r"
    assert run("prepare", "--task", "T3", "--dest", str(dest)).returncode == 0
    assert (dest / "TASK.md").exists()
    assert (dest / "docstore" / "store.py").exists()
    assert (dest / ".git").exists()
    assert not (dest / "hidden").exists() and not (dest / "reference").exists()


def test_score_reference_all_pass():
    s = bench.run_score("T2", SOURCE / "bench" / "tasks" / "T2" / "reference")
    assert s["hidden_total"] >= 8
    assert s["hidden_pass"] == s["hidden_total"]
    assert s["verified_requirements"] == s["total_requirements"]


def test_score_seed_only_t3_features_fail_regression_pass():
    s = bench.run_score("T3", SOURCE / "bench" / "tasks" / "T3" / "seed")
    assert s["requirements"]["R1"]["passed"] is True
    for t in ("test_legacy_create_read_update_delete", "test_legacy_errors_unchanged",
              "test_legacy_list_ids_sorted"):
        assert s["tests"][t] is True
    assert s["tests"]["test_viewer_can_read_and_list_only"] is False
    assert 0 < s["hidden_pass"] < s["hidden_total"]


def test_selfcheck_exit_code_t1_reference():
    s = bench.run_score("T1", SOURCE / "bench" / "tasks" / "T1" / "reference")
    assert s["hidden_pass"] == s["hidden_total"] == 15


def rec(tool, task, interventions, verified, passed=10, total=10, credits=None, minutes=None, run=1):
    return {"tool": tool, "task": task, "run": run, "interventions": interventions,
            "hidden_pass": passed, "hidden_total": total, "verified_requirements": verified,
            "nsm": verified / interventions, "lead_time_min": 30.0, "human_minutes": minutes,
            "credits": credits, "completed_without_correction": True}


def test_empty_aggregate_says_unmeasured(tmp_path):
    out = tmp_path / "R.md"
    assert run("aggregate", "--out", str(out), "--results-dir", str(tmp_path / "none")).returncode == 0
    text = out.read_text(encoding="utf-8")
    assert "未計測" in text
    assert text.count("未検証") == 4
    assert "| T3 | Spec Kit | 0 | - |" in text


def test_aggregate_nsm_and_hypotheses(tmp_path):
    d = tmp_path / "results"
    d.mkdir()
    rs = [
        rec("conductor", "T1", 2, 6, credits=12, minutes=5),
        rec("conductor", "T3", 2, 6, credits=12, minutes=5),
        rec("speckit", "T1", 6, 6, credits=10, minutes=20),
        rec("speckit", "T3", 12, 3, passed=6, credits=10, minutes=20),
    ]
    for i, r in enumerate(rs):
        (d / f"{i}.json").write_text(json.dumps(r), encoding="utf-8")
    text = bench.render(bench.load_results(d))
    assert "記録がまだありません" not in text
    h = {x[0]: x[2] for x in bench.hypotheses(bench.load_results(d))}
    assert h == {"H1": "支持", "H2": "支持", "H3": "支持", "H4": "支持"}
    assert bench.nsm(6, 2) == 3
    assert abs(bench._nsm_mean([r for r in rs if r["tool"] == "speckit"]) - (1 + 0.25) / 2) < 1e-9
    assert abs(bench.credits_per_verified([r for r in rs if r["tool"] == "speckit"]) - 20 / 9) < 1e-9


def test_hypotheses_reject_and_partial():
    rs = [rec("conductor", "T1", 8, 6, passed=5, credits=30), rec("speckit", "T1", 2, 6, credits=10)]
    h = {x[0]: x[2] for x in bench.hypotheses(rs)}
    assert h["H1"] == "不支持" and h["H2"] == "不支持" and h["H3"] == "不支持"
    assert h["H4"] == "未検証"
    assert {x[2] for x in bench.hypotheses(rs[:1])} == {"未検証"}


def test_record_writes_json(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "RESULTS", tmp_path)
    args = bench.build_parser().parse_args([
        "record", "--tool", "conductor", "--task", "T1", "--run", "1",
        "--repo", str(SOURCE / "bench" / "tasks" / "T1" / "reference"),
        "--interventions", "3", "--lead-time-min", "20", "--completed-without-correction", "yes"])
    assert bench.cmd_record(args) == 0
    data = json.loads((tmp_path / "conductor-T1-r1.json").read_text(encoding="utf-8"))
    assert data["verified_requirements"] == 6
    assert data["nsm"] == 2.0
    assert data["toolkit_version"] == bench.toolkit_version()
    assert data["credits"] is None and data["completed_without_correction"] is True
