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
