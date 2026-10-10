import json
import os
import time

from conftest import git


def start_run(repo, options="max_hours: 24\ngit_push: しない\ndeploy: しない"):
    out = repo.py("run-state.py", "start", "--options", options, check=True).stdout
    rid = out.split()[1]
    return rid


def test_run_state_lifecycle(sample):
    rid = start_run(sample)
    assert git(sample.path, "branch", "--show-current") == f"run/{rid}"
    assert sample.py("run-state.py", "start", check=True).stdout.startswith(f"RESUME {rid}")
    sample.py("run-state.py", "queue", "add", "--id", "I-01", "--req", "FR-001", "--ac", "AC-001", "--boundary", "申請", check=True)
    sample.py("run-state.py", "queue", "add", "--id", "I-02", "--req", "FR-001", "--boundary", "申請", check=True)
    sample.py("run-state.py", "queue", "add", "--id", "I-03", "--req", "FR-001", "--depends", "I-01", check=True)
    assert sample.py("run-state.py", "queue", "add", "--id", "I-04", "--req", "FR-1,FR-2,FR-3,FR-4,FR-5,FR-6").returncode != 0
    ready = sample.py("run-state.py", "queue", "ready", "--parallel", "3", check=True).stdout
    assert "I-01" in ready and "I-02" not in ready and "I-03" not in ready  # same boundary / dependency
    sample.py("run-state.py", "queue", "set", "I-01", "--status", "done", "--attempts", "+1", check=True)
    ready = sample.py("run-state.py", "queue", "ready", check=True).stdout
    assert "I-02" in ready and "I-03" in ready
    assert sample.py("run-state.py", "complete-check").returncode == 1
    for item in ("I-02", "I-03"):
        sample.py("run-state.py", "queue", "set", item, "--status", "blocked", check=True)
    sample.py("run-state.py", "stage", "6", "--done", check=True)
    sample.write(f"work/runs/{rid}/run-report.md", "結果: blocked あり\n")
    assert sample.py("run-state.py", "complete-check").returncode == 0
    out = sample.py("run-state.py", "finish", "--credits", "12.5", check=True).stdout
    assert "blocked あり" in out
    hist = sample.read("docs/run-history.md")
    assert f"| {rid} |" in hist and "| FR-001 |" in hist and "| 1/1 |" in hist
    assert not (sample.path / "work" / "current-run.txt").exists()
    assert sample.py("rdcheck.py", "check", "--base", "none").returncode == 0


def test_status_follows_renamed_integration_branch(sample):
    # e.g. a GitHub Copilot app worktree session whose branch was renamed after the run started
    git(sample.path, "switch", "-q", "-c", "copilot-session")
    rid = start_run(sample)
    assert git(sample.path, "branch", "--show-current") == "copilot-session"
    git(sample.path, "branch", "-m", "copilot-session", "renamed-session")
    out = sample.py("run-state.py", "status", check=True).stdout
    assert "integration: renamed-session" in out and "WARN" in out
    meta = json.loads((sample.path / "work" / "runs" / rid / "meta.json").read_text(encoding="utf-8"))
    assert meta["integration_branch"] == "renamed-session"
    assert meta["integration_branch_renamed_from"] == "copilot-session"
    out = sample.py("run-state.py", "status", check=True).stdout
    assert "WARN" not in out


def test_stage4_makes_ledger_strict(sample):
    start_run(sample)
    assert sample.py("verify.py", "--docs-only").returncode == 0
    sample.py("run-state.py", "stage", "4", "--done", check=True)
    proc = sample.py("verify.py", "--docs-only")
    assert proc.returncode == 1 and "CHK-10" in proc.stdout


def test_time_budget(sample):
    rid = start_run(sample, "max_hours: 1")
    meta_p = sample.path / "work" / "runs" / rid / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    meta["started_at"] = "2000-01-01T00:00:00+00:00"
    meta_p.write_text(json.dumps(meta), encoding="utf-8")
    assert sample.py("run-state.py", "time").returncode == 3


def test_verify_runs_configured_commands(sample):
    cfg = json.loads(sample.read("scripts/ebak.config.json"))
    cfg["verify"]["commands"] = [
        {"name": "ok", "run": "python -c \"print('fine')\""},
        {"name": "slow", "run": "python -c \"raise SystemExit(1)\"", "slow": True},
    ]
    sample.write("scripts/ebak.config.json", json.dumps(cfg))
    assert sample.py("verify.py", "--quick").returncode == 0
    proc = sample.py("verify.py")
    assert proc.returncode == 1 and "FAIL slow" in proc.stdout


def test_verify_accepts_string_commands_and_reports_bad_entries(sample):
    cfg = json.loads(sample.read("scripts/ebak.config.json"))
    cfg["verify"]["commands"] = ["python -c \"print('one')\"", "python -c \"print('two')\""]
    sample.write("scripts/ebak.config.json", json.dumps(cfg))
    proc = sample.py("verify.py")
    assert proc.returncode == 0, proc.stdout
    assert "PASS python " in proc.stdout and "PASS python-2 " in proc.stdout

    cfg["verify"]["commands"] = "python -c \"print('only')\""
    sample.write("scripts/ebak.config.json", json.dumps(cfg))
    assert sample.py("verify.py").returncode == 0

    cfg["verify"]["commands"] = [{"name": "unit"}, 3]
    sample.write("scripts/ebak.config.json", json.dumps(cfg))
    proc = sample.py("verify.py")
    assert proc.returncode == 1
    assert "FAIL config" in proc.stdout and '"run"' in proc.stdout and "Traceback" not in proc.stdout + proc.stderr
    assert sample.py("verify.py", "--docs-only").returncode == 0


def test_clean_work_retains_unverifiable_run_without_expiry(sample):
    # FR-1009 AC-058 / NFR-OPS-005 AC-063
    old = sample.path / "work" / "runs" / "200001010000"
    old.mkdir(parents=True)
    (old / "progress.md").write_text("x", encoding="utf-8")
    past = time.time() - 30 * 86400
    os.utime(old / "progress.md", (past, past))
    os.utime(old, (past, past))
    rid = start_run(sample)
    out = sample.py("clean-work.py", check=True).stdout
    assert "KEEP   work/runs/200001010000" in out and f"KEEP   work/runs/{rid}" in out
    assert old.exists()


def test_lane_fast_and_full(sample):
    start_run(sample)
    out = sample.py("run-state.py", "lane", "decide", "--changed", "2", check=True).stdout
    assert "LANE: fast" in out and "独立監査" in out
    # a security conflict forces the full lane, and confirm never goes back to fast
    out = sample.py("run-state.py", "lane", "decide", "--changed", "1", "--flags", "security", check=True).stdout
    assert "LANE: full" in out and "skipped: なし" in out
    assert sample.py("run-state.py", "lane", "confirm", check=True).stdout.startswith("LANE: full")
    assert "lane: full" in sample.py("run-state.py", "status", check=True).stdout


def test_lane_confirm_uses_queue_size(sample):
    start_run(sample)
    sample.py("run-state.py", "lane", "decide", "--changed", "3", check=True)
    for i in range(3):
        sample.py("run-state.py", "queue", "add", "--id", f"I-0{i}", "--req", "FR-001", "--boundary", f"b{i}", check=True)
    assert "LANE: full" in sample.py("run-state.py", "lane", "confirm", check=True).stdout
    assert sample.py("run-state.py", "lane", "decide", "--changed", "4").stdout.count("LANE: full") == 1
    assert sample.py("run-state.py", "lane", "decide", "--flags", "bogus").returncode != 0
