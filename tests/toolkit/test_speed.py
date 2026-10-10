import json
from pathlib import Path

from conftest import git, run


def start_run(repo, options="max_hours: 24\ngit_push: しない\ndeploy: しない"):
    out = repo.py("run-state.py", "start", "--options", options, check=True).stdout
    return out.split()[1]


def worktree_of(out):
    return Path(next(l for l in out.splitlines() if l.startswith("WORKTREE:")).split(":", 1)[1].strip())


def commit_in(wt, rel, text, msg="[FR-001] change"):
    p = wt / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", msg)


def queue(repo, rid):
    return {it["id"]: it for it in json.loads(repo.read(f"work/runs/{rid}/queue.json"))["items"]}


def test_integrate_pool_reuses_worktree_and_merges(sample):
    rid = start_run(sample)
    sample.py("run-state.py", "queue", "add", "--id", "I-01", "--req", "FR-001", check=True)
    sample.py("run-state.py", "queue", "add", "--id", "I-02", "--req", "FR-001", "--depends", "I-01", check=True)
    out = sample.py("integrate.py", "prepare", "I-01", check=True).stdout
    wt = worktree_of(out)
    assert wt.name == f"{rid}-w1" and git(wt, "branch", "--show-current") == f"work/{rid}/I-01"
    it = queue(sample, rid)["I-01"]
    assert it["status"] == "doing" and it["attempts"] == 1 and it["worktree"] == f"work/worktrees/{rid}-w1"
    (wt / "build-cache").mkdir()
    with open(wt / ".gitignore", "a", encoding="utf-8") as fh:
        fh.write("build-cache/\n")
    (wt / "build-cache" / "obj.bin").write_text("x", encoding="utf-8")
    commit_in(wt, "src/app.py", "print('ok')\n")
    out = sample.py("integrate.py", "merge", "I-01", "--summary", "なし", check=True).stdout
    assert out.startswith("INTEGRATE: pass I-01"), out
    assert (sample.path / "src" / "app.py").exists()
    it = queue(sample, rid)["I-01"]
    assert it["status"] == "done" and it["worktree"] is None and it["summary"] == "なし"
    assert it["work_sec"] >= 0 and it["integrate_sec"] >= 0 and it["finished_at"]
    assert git(sample.path, "branch", "--list", f"work/{rid}/I-01") == ""
    # the next item reuses the same slot and keeps ignored build outputs
    wt2 = worktree_of(sample.py("integrate.py", "prepare", "I-02", check=True).stdout)
    assert wt2 == wt and (wt2 / "build-cache" / "obj.bin").exists() and (wt2 / "src" / "app.py").exists()
    assert "BUSY" in sample.py("integrate.py", "pool", check=True).stdout
    sample.py("integrate.py", "abandon", "I-02", "--blocked", "--reason", "test", check=True)
    assert queue(sample, rid)["I-02"]["status"] == "blocked"
    out = sample.py("integrate.py", "pool", "--prune", check=True).stdout
    assert "REMOVED" in out and not wt.exists()


def test_integrate_rolls_back_when_verify_fails(sample):
    cfg = json.loads(sample.read("scripts/ebak.config.json"))
    cfg["verify"]["commands"] = [{"name": "unit", "run": "python -c \"import os,sys; sys.exit(os.path.exists('fail.flag'))\""}]
    sample.write("scripts/ebak.config.json", json.dumps(cfg))
    sample.commit("verify command")
    rid = start_run(sample)
    sample.py("run-state.py", "queue", "add", "--id", "I-01", "--req", "FR-001", check=True)
    wt = worktree_of(sample.py("integrate.py", "prepare", "I-01", check=True).stdout)
    head = git(sample.path, "rev-parse", "HEAD")
    commit_in(wt, "fail.flag", "x")
    proc = sample.py("integrate.py", "merge", "I-01")
    assert proc.returncode == 1 and "INTEGRATE: fail I-01 verify" in proc.stdout and "FAIL unit" in proc.stdout
    assert git(sample.path, "rev-parse", "HEAD") == head and not (sample.path / "fail.flag").exists()
    it = queue(sample, rid)["I-01"]
    assert it["status"] == "todo" and it["worktree"] is None
    # retry: the branch with the previous attempt is checked out again
    wt = worktree_of(sample.py("integrate.py", "prepare", "I-01", check=True).stdout)
    assert (wt / "fail.flag").exists() and queue(sample, rid)["I-01"]["attempts"] == 2
    git(wt, "rm", "-q", "fail.flag")
    git(wt, "commit", "-q", "-m", "[FR-001] fix")
    assert sample.py("integrate.py", "merge", "I-01").returncode == 0


def test_integrate_requires_integration_branch(sample):
    rid = start_run(sample)
    sample.py("run-state.py", "queue", "add", "--id", "I-01", "--req", "FR-001", check=True)
    wt = worktree_of(sample.py("integrate.py", "prepare", "I-01", check=True).stdout)
    commit_in(wt, "a.txt", "a")
    git(sample.path, "switch", "-q", "main")
    proc = sample.py("integrate.py", "merge", "I-01")
    assert proc.returncode != 0 and f"run/{rid}" in proc.stdout + proc.stderr


def test_queue_items_take_up_to_five_requirements(sample):
    start_run(sample)
    assert sample.py("run-state.py", "queue", "add", "--id", "I-01", "--req", "FR-1,FR-2,FR-3,FR-4,FR-5").returncode == 0
    assert sample.py("run-state.py", "queue", "add", "--id", "I-02", "--req", "FR-1,FR-2,FR-3,FR-4,FR-5,FR-6").returncode != 0


def test_verify_cache_reuses_pass_on_clean_commit(sample):
    first = sample.py("verify.py", "--docs-only", check=True).stdout
    assert "cached" not in first
    second = sample.py("verify.py", "--docs-only", check=True).stdout
    assert "PASS (cached" in second and "cached=1" in second
    assert "cached" not in sample.py("verify.py", "--docs-only", "--no-cache", check=True).stdout
    assert "cached" not in sample.py("verify.py", check=True).stdout  # other arguments, other key
    sample.write("docs/note.md", "x\n")  # dirty tree: never cached
    assert "cached" not in sample.py("verify.py", "--docs-only", check=True).stdout


def test_verify_cache_never_stores_fail(sample):
    cfg = json.loads(sample.read("scripts/ebak.config.json"))
    cfg["verify"]["commands"] = [{"name": "bad", "run": "python -c \"raise SystemExit(1)\""}]
    sample.write("scripts/ebak.config.json", json.dumps(cfg))
    sample.commit("bad command")
    assert sample.py("verify.py").returncode == 1
    proc = sample.py("verify.py")
    assert proc.returncode == 1 and "cached" not in proc.stdout


def test_verify_retries_flaky_failure_once(sample):
    sample.write("flaky.py", "import os,sys\nif not os.path.exists('m.flag'):\n    open('m.flag','w').close()\n    print('Timeout calling onTaskUpdate'); sys.exit(1)\n")
    cfg = json.loads(sample.read("scripts/ebak.config.json"))
    cfg["verify"]["commands"] = [{"name": "flaky", "run": "python flaky.py"}]
    sample.write("scripts/ebak.config.json", json.dumps(cfg))
    proc = sample.py("verify.py", "--no-cache")
    assert proc.returncode == 0 and "retried" in proc.stdout


def test_verify_step_skipped_when_cache_files_unchanged(sample):
    sample.write("lock.txt", "a\n")
    cfg = json.loads(sample.read("scripts/ebak.config.json"))
    cfg["verify"]["commands"] = [{"name": "setup", "run": "python -c \"print(1)\"", "cache_files": ["lock.txt"]}]
    sample.write("scripts/ebak.config.json", json.dumps(cfg))
    assert "skipped" not in sample.py("verify.py", "--show-warnings", check=True).stdout
    assert "skipped" in sample.py("verify.py", "--show-warnings", check=True).stdout
    sample.write("lock.txt", "b\n")
    assert "skipped" not in sample.py("verify.py", "--show-warnings", check=True).stdout


def test_queue_rejects_item_with_too_many_acs(sample):
    start_run(sample)
    acs = ",".join(f"AC-{i:03d}" for i in range(1, 14))
    proc = sample.py("run-state.py", "queue", "add", "--id", "I-big", "--req", "FR-001", "--ac", acs)
    assert proc.returncode != 0 and "AC は 12 個まで" in (proc.stdout + proc.stderr)
    ok = sample.py("run-state.py", "queue", "add", "--id", "I-big", "--req", "FR-001", "--ac", acs, "--allow-large")
    assert ok.returncode == 0


def test_ledger_writers_are_serialised(sample):
    import subprocess, sys
    procs = [subprocess.Popen([sys.executable, str(sample.path / "scripts" / "ledger.py"), "--by", "t", "digests", "--update"],
                              cwd=str(sample.path), stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(4)]
    assert all(p.wait() == 0 for p in procs)
    json.loads(sample.read("tests/system/ledger.json"))
    assert not (sample.path / "work" / ".ebak" / "ledger.lock").exists()


def test_auto_workers_scale_with_machine():
    import importlib.util, sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    h = importlib.import_module("ebaklib")
    assert h.auto_workers(cpus=4, mem_gb=64) == 2
    assert h.auto_workers(cpus=20, mem_gb=64) == 8
    assert h.auto_workers(cpus=20, mem_gb=16) == 2
    assert h.auto_workers(cpus=64, mem_gb=512) == 8
    assert h.cpu_share(8, cpus=20) == 4 and h.cpu_share(5, cpus=20) == 6 and h.cpu_share(32, cpus=20) == 1 and h.cpu_share(1, cpus=20) == 20


def test_run_start_resolves_auto_workers_and_hands_out_cpu_share(sample):
    import importlib, sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    h = importlib.import_module("ebaklib")
    out = sample.py("run-state.py", "start", "--options", "max_hours: 24\ngit_push: しない\ndeploy: しない", check=True).stdout
    assert "parallel_workers: auto ->" in out
    rid = out.split("START")[1].split()[0]
    workers = int(json.loads(sample.read(f"work/runs/{rid}/meta.json"))["options"]["parallel_workers"])
    cfg = json.loads(sample.read("scripts/ebak.config.json"))
    cfg["verify"]["commands"] = [{"name": "env", "run": "python -c \"import os;print('CPUS='+os.environ['HVE_CPUS']+' VT='+os.environ['VITEST_MAX_WORKERS'])\""}]
    sample.write("scripts/ebak.config.json", json.dumps(cfg))
    sample.commit("env probe")
    sample.py("verify.py", "--show-warnings", check=True)
    logs = sorted((sample.path / "work" / "runs" / rid / "logs").glob("verify-*-env.log"))
    share = h.cpu_share(workers)
    assert f"CPUS={share} VT={share}" in logs[-1].read_text(encoding="utf-8")


def test_verify_parallel_group_runs_concurrently(sample):
    sleep = "python -c \"import time;time.sleep(3)\""
    cfg = json.loads(sample.read("scripts/ebak.config.json"))
    cfg["verify"]["commands"] = [{"name": f"s{i}", "run": sleep, "parallel": True} for i in range(3)]
    sample.write("scripts/ebak.config.json", json.dumps(cfg))
    sample.commit("parallel steps")
    import time
    t = time.time()
    out = sample.py("verify.py", "--no-cache", check=True).stdout
    assert out.count("PASS s") == 3 and time.time() - t < 8.5  # 3 x 3 s sequentially would be 9 s+


def test_ledger_run_jobs_runs_cases_concurrently_and_serial_alone(sample):
    sleep = "python -c \"import time;time.sleep(2.5)\""
    for i in range(4):
        sample.py("ledger.py", "--by", "t", "add", "--req", "FR-001", "--ac", "AC-001", "--title", f"c{i}", "--layer", "e2e", "--command", sleep)
    data = json.loads(sample.read("tests/system/ledger.json"))
    data["cases"][-1]["serial"] = True
    sample.write("tests/system/ledger.json", json.dumps(data))
    import time
    t = time.time()
    out = sample.py("ledger.py", "run", "--select", "all", "--jobs", "3", "--no-record").stdout
    el = time.time() - t
    assert out.count(" pass ") >= 4 and "全件 pass" in out
    assert el < 4 * 2.5 + 1 and el >= 2 * 2.5  # 3 parallel + 1 serial: two waves, not four


def test_gate_enforces_model_table(sample):
    cfg = json.loads(sample.read("scripts/ebak.config.json"))
    cfg["models"].update({"implementer": "m-small", "implementer-escalation": "m-big", "reviewer": ""})
    sample.write("scripts/ebak.config.json", json.dumps(cfg))
    sample.commit("models")
    task = lambda **a: sample.gate("pre-tool", {"toolName": "task", "toolArgs": a})  # noqa: E731
    assert task(agent_type="implementer") == {}  # no run: not enforced
    rid = start_run(sample)
    res = task(agent_type="implementer", prompt="x")
    assert "[G-7]" in res.get("permissionDecisionReason", "") and "m-small" in res["permissionDecisionReason"]
    assert task(agent_type="implementer", model="m-small") == {}
    assert task(agent_type="implementer", model="m-big") == {}
    assert task(agent_type="reviewer") == {}  # empty entry: default model
    lines = [json.loads(l) for l in sample.read(f"work/runs/{rid}/models.jsonl").splitlines()]
    assert [(e["agent"], e["model"]) for e in lines] == [
        ("implementer", "(既定)"), ("implementer", "m-small"), ("implementer", "m-big"), ("reviewer", "(既定)")]
    cfg["gates"]["enforce_models"] = False
    sample.write("scripts/ebak.config.json", json.dumps(cfg))
    assert task(agent_type="implementer") == {}


def test_gate_fast_path_for_read_tools(sample):
    start_run(sample)
    sample.gate("user-prompt", {"sessionId": "s1", "prompt": "/build template"})
    for tool in ("view", "grep", "glob", "read_powershell"):
        assert sample.gate("pre-tool", {"toolName": tool, "toolArgs": {"path": "docs/requirements-definition.md"}}) == {}
    proc = run(["python", "-S", str(sample.path / "scripts" / "hooks" / "gate.py"), "pre-tool"], sample.path,
               json.dumps({"toolName": "view", "cwd": str(sample.path)}))
    assert proc.returncode == 0 and proc.stdout == "{}"


def test_kpi_reports_flow_metrics(sample):
    rid = start_run(sample)
    sample.py("run-state.py", "stage", "5", check=True)
    sample.py("run-state.py", "queue", "add", "--id", "I-01", "--req", "FR-001", check=True)
    wt = worktree_of(sample.py("integrate.py", "prepare", "I-01", check=True).stdout)
    commit_in(wt, "src/a.py", "a = 1\n")
    sample.py("integrate.py", "merge", "I-01", check=True)
    sample.py("run-state.py", "stage", "5", "--done", check=True)
    sample.gate("pre-tool", {"toolName": "task", "toolArgs": {"agent_type": "implementer", "model": "m1"}})
    data = json.loads(sample.py("kpi.py", "run", "--format", "json", check=True).stdout)
    f = data["flow"]
    assert "5" in f["stage_minutes"] and f["integrate_minutes"] is not None
    assert f["models"] == {"implementer": {"m1": 1}}
    md = sample.py("kpi.py", "run", check=True).stdout
    assert "実効の並列度" in md and "統合の直列時間" in md and "implementer: m1×1" in md
    assert rid in md
