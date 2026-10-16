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


def test_land_waits_for_a_clean_primary_tree(sample):
    wt = start_in_worktree(sample)
    commit_in(wt)
    patch_meta(wt, status="finished", result="全件完了")
    (sample.path / "README.md").write_text("dirty\n", encoding="utf-8")
    proc = py(wt, "run-state.py", "land", "--wait", "1")
    assert proc.returncode == 3 and "LAND-WAIT" in proc.stdout


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
