import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import git


def start_in_worktree(repo):
    env = {k: v for k, v in os.environ.items() if k != "EABK_ALLOW_PRIMARY"}
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run([sys.executable, str(repo.path / "scripts" / "run-state.py"), "start"], cwd=str(repo.path),
                          capture_output=True, text=True, encoding="utf-8", env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return Path(proc.stdout.split("WORKTREE ", 1)[1].split("\n")[0].strip())


def meta_path(wt):
    rid = (wt / "work" / "current-run.txt").read_text(encoding="utf-8").strip() if (wt / "work" / "current-run.txt").exists() \
        else sorted(p.name for p in (wt / "work" / "runs").iterdir())[-1]
    return rid, wt / "work" / "runs" / rid / "meta.json"


def patch_meta(wt, **kw):
    rid, p = meta_path(wt)
    m = json.loads(p.read_text(encoding="utf-8"))
    m.update(kw)
    p.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return rid, m


def py(wt, script, *args):
    env = dict(os.environ, PYTHONUTF8="1")
    env.pop("EABK_ALLOW_PRIMARY", None)
    return subprocess.run([sys.executable, str(wt / "scripts" / script), *args], cwd=str(wt), capture_output=True,
                          text=True, encoding="utf-8", env=env)


def test_runs_started_together_get_distinct_ids(repo):
    a, b = start_in_worktree(repo), start_in_worktree(repo)
    assert a != b and a.is_dir() and b.is_dir()
    branches = git(repo.path, "branch", "--list", "run/*")
    assert branches.count("run/") == 2


def test_land_merges_finished_run_into_main(sample):
    wt = start_in_worktree(sample)
    (wt / "landed.txt").write_text("x\n", encoding="utf-8")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "work")
    patch_meta(wt, status="finished", result="全件完了")
    proc = py(wt, "run-state.py", "land", "--wait", "5")
    assert proc.returncode == 0 and "LANDED" in proc.stdout, proc.stdout + proc.stderr
    assert (sample.path / "landed.txt").exists()
    assert "LANDED" in py(wt, "run-state.py", "land", "--wait", "5").stdout


def test_land_refuses_unfinished_or_blocked_run(sample):
    wt = start_in_worktree(sample)
    assert py(wt, "run-state.py", "land", "--wait", "1").returncode == 1
    patch_meta(wt, status="finished", result="blocked あり")
    assert "LAND-SKIP" in py(wt, "run-state.py", "land", "--wait", "1").stdout


def commit_in(wt, name="work.txt"):
    (wt / name).write_text("x\n", encoding="utf-8")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "work")


def test_land_works_with_a_dirty_primary_tree(sample):
    wt = start_in_worktree(sample)
    commit_in(wt)
    patch_meta(wt, status="finished", result="全件完了")
    (sample.path / "README.md").write_text("dirty\n", encoding="utf-8")
    proc = py(wt, "run-state.py", "land", "--wait", "5")
    assert proc.returncode == 0 and "LANDED" in proc.stdout, proc.stdout + proc.stderr
    assert (sample.path / "work.txt").exists()
    assert (sample.path / "README.md").read_text(encoding="utf-8") == "dirty\n"


def test_land_waits_when_dirty_change_overlaps(sample):
    wt = start_in_worktree(sample)
    (wt / "README.md").write_text("from run\n", encoding="utf-8")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "run change")
    patch_meta(wt, status="finished", result="全件完了")
    (sample.path / "README.md").write_text("dirty\n", encoding="utf-8")
    proc = py(wt, "run-state.py", "land", "--wait", "1")
    assert proc.returncode == 3 and "LAND-WAIT" in proc.stdout


def test_land_when_primary_is_on_another_branch(sample):
    wt = start_in_worktree(sample)
    commit_in(wt)
    patch_meta(wt, status="finished", result="全件完了")
    git(sample.path, "switch", "-q", "-c", "other")
    proc = py(wt, "run-state.py", "land", "--wait", "5")
    assert proc.returncode == 0 and "LANDED" in proc.stdout, proc.stdout + proc.stderr
    assert "work.txt" in git(sample.path, "ls-tree", "-r", "--name-only", "main")
    assert not (sample.path / "work.txt").exists()


def test_start_run_id_matches_worktree_name(repo):
    wt = start_in_worktree(repo)
    rid, _ = meta_path(wt)
    assert wt.name == f"{repo.path.name}-run-{rid}"


def test_merge_ledgers_three_way():
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_state", Path(__file__).resolve().parents[2] / "scripts" / "run-state.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    c = lambda i, s="not_run": {"id": i, "status": s}
    anc = {"version": 1, "ac_digests": {"AC-1": "a"}, "cases": [c("E-1")]}
    ours = {"version": 1, "ac_digests": {"AC-1": "a", "AC-2": "b"}, "cases": [c("E-1", "pass"), c("E-2")]}
    theirs = {"version": 1, "ac_digests": {"AC-1": "a", "AC-3": "c"}, "cases": [c("E-1"), c("E-3")]}
    out = mod.merge_ledgers(anc, ours, theirs)
    assert [x["id"] for x in out["cases"]] == ["E-1", "E-3", "E-2"]
    assert out["cases"][0]["status"] == "pass"
    assert set(out["ac_digests"]) == {"AC-1", "AC-2", "AC-3"}


def test_land_auto_syncs_ledger_conflict(sample):
    wt = start_in_worktree(sample)
    led = "tests/system/ledger.json"
    base = {"version": 1, "ac_digests": {}, "cases": []}
    (sample.path / "tests" / "system").mkdir(parents=True, exist_ok=True)
    (sample.path / led).write_text(json.dumps(base), encoding="utf-8")
    sample.commit("ledger")
    git(wt, "merge", "-q", "main")
    run = dict(base, cases=[{"id": "E-2", "status": "pass"}])
    (wt / led).write_text(json.dumps(run), encoding="utf-8")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "run ledger")
    patch_meta(wt, status="finished", result="全件完了")
    main = dict(base, cases=[{"id": "E-3", "status": "pass"}])
    (sample.path / led).write_text(json.dumps(main), encoding="utf-8")
    sample.commit("main ledger")
    proc = py(wt, "run-state.py", "land", "--wait", "10")
    assert proc.returncode == 0 and "LANDED" in proc.stdout, proc.stdout + proc.stderr
    merged = json.loads((sample.path / led).read_text(encoding="utf-8"))
    assert {c["id"] for c in merged["cases"]} == {"E-2", "E-3"}


def test_land_conflict_is_aborted(sample):
    wt = start_in_worktree(sample)
    (wt / "README.md").write_text("from run\n", encoding="utf-8")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "run change")
    patch_meta(wt, status="finished", result="全件完了")
    (sample.path / "README.md").write_text("from main\n", encoding="utf-8")
    sample.commit("main change")
    proc = py(wt, "run-state.py", "land", "--wait", "5")
    assert proc.returncode == 2 and "LAND-CONFLICT" in proc.stdout
    assert git(sample.path, "status", "--porcelain", "--untracked-files=no") == ""


def test_land_lock_serialises_runs(sample):
    wt = start_in_worktree(sample)
    commit_in(wt)
    patch_meta(wt, status="finished", result="全件完了")
    lock = Path(git(sample.path, "rev-parse", "--git-common-dir"))
    lock = (lock if lock.is_absolute() else sample.path / lock) / "ebak-land.lock"
    lock.write_text("999", encoding="utf-8")
    try:
        proc = py(wt, "run-state.py", "land", "--wait", "1")
        assert "LAND-BUSY" in proc.stdout + proc.stderr
    finally:
        lock.unlink()


def test_hook_binds_run_by_session(sample):
    a, b = start_in_worktree(sample), start_in_worktree(sample)
    patch_meta(a, session_id="sA")
    patch_meta(b, session_id="sB")
    res = sample.gate("agent-stop", {"sessionId": "sA"})
    assert res.get("decision") == "block"
    assert meta_path(a)[0] in json.dumps(res) or "run-state.py status" in res["reason"]
    assert sample.gate("agent-stop", {"sessionId": "sC"}) == {}


def test_hook_session_claims_newest_free_run(sample):
    a, b = start_in_worktree(sample), start_in_worktree(sample)
    res = sample.gate("agent-stop", {"sessionId": "sX"})
    assert res.get("decision") == "block"
    owners = [json.loads(meta_path(w)[1].read_text(encoding="utf-8")).get("session_id") for w in (a, b)]
    assert owners.count("sX") == 1


def test_agent_stop_blocks_until_finished_run_is_landed(sample):
    wt = start_in_worktree(sample)
    (wt / "x.txt").write_text("x\n", encoding="utf-8")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "work")
    patch_meta(wt, status="finished", result="全件完了", session_id="sA")
    res = sample.gate("agent-stop", {"sessionId": "sA"})
    assert res.get("decision") == "block" and "land" in res["reason"]
    assert sample.gate("agent-stop", {"sessionId": "other"}) == {}
    assert py(wt, "run-state.py", "land", "--wait", "5").returncode == 0
    assert sample.gate("agent-stop", {"sessionId": "sA"}) == {}

def test_subagent_start_without_session_binds_sole_owned_run(sample):
    wt = start_in_worktree(sample)
    patch_meta(wt, session_id="sA")
    sample.gate("subagent-start", {"agentName": "rd-author"})
    log = (wt / "work" / ".ebak" / "gate.log").read_text(encoding="utf-8")
    assert "START rd-author" in log
    assert json.loads((wt / "work" / ".ebak" / "active-agents.json").read_text(encoding="utf-8"))[0]["name"] == "rd-author"
    res = sample.gate("pre-tool", {"sessionId": "sA", "toolName": "edit", "toolArgs": {
        "path": str(wt / "docs" / "requirements-definition.md"), "old_str": "a", "new_str": "b"}})
    assert res == {}
    sample.gate("subagent-stop", {"agentName": "rd-author"})
    assert "STOP rd-author" in (wt / "work" / ".ebak" / "gate.log").read_text(encoding="utf-8")


def test_subagent_start_without_session_does_not_pick_among_several_runs(sample):
    a, b = start_in_worktree(sample), start_in_worktree(sample)
    patch_meta(a, session_id="sA")
    patch_meta(b, session_id="sB")
    sample.gate("subagent-start", {"agentName": "rd-author"})
    for w in (a, b):
        assert not (w / "work" / ".ebak" / "active-agents.json").exists()
