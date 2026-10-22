import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import git


def start_in_worktree(repo, *args):
    env = {k: v for k, v in os.environ.items() if k != "EABK_ALLOW_PRIMARY"}
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run([sys.executable, str(repo.path / "scripts" / "run-state.py"), "start", *args], cwd=str(repo.path),
                          capture_output=True, text=True, encoding="utf-8", env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return Path(proc.stdout.split("WORKTREE ", 1)[1].split("\n")[0].strip())


def hold_lock(path):
    """A separate process that holds the exclusive lock on `path` (a live holder); kill it to simulate a crash."""
    code = ("import sys, time; sys.path.insert(0, sys.argv[1]); import ebaklib as h; "
            "l = h.FileLock(sys.argv[2], 30); l.__enter__(); print('held', flush=True); time.sleep(300)")
    scripts = str(Path(__file__).resolve().parents[2] / "scripts")
    proc = subprocess.Popen([sys.executable, "-c", code, scripts, str(path)], stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "held"
    return proc


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
    lock.write_text(str(os.getpid()), encoding="utf-8")
    try:
        proc = py(wt, "run-state.py", "land", "--wait", "1")
        assert "LAND-BUSY" in proc.stdout + proc.stderr
    finally:
        lock.unlink()


def test_land_lock_orphaned_is_released(sample):
    wt = start_in_worktree(sample)
    commit_in(wt)
    patch_meta(wt, status="finished", result="全件完了")
    lock = Path(git(sample.path, "rev-parse", "--git-common-dir"))
    lock = (lock if lock.is_absolute() else sample.path / lock) / "ebak-land.lock"
    lock.write_text("999999999", encoding="utf-8")
    proc = py(wt, "run-state.py", "land", "--wait", "1")
    assert "LAND-BUSY" not in proc.stdout + proc.stderr


def test_hook_binds_run_by_session(sample):
    a, b = start_in_worktree(sample), start_in_worktree(sample)
    patch_meta(a, session_id="sA")
    patch_meta(b, session_id="sB")
    res = sample.gate("agent-stop", {"sessionId": "sA"})
    assert res.get("decision") == "block"
    assert meta_path(a)[0] in json.dumps(res) or "run-state.py status" in res["reason"]
    assert sample.gate("agent-stop", {"sessionId": "sC"}) == {}


def test_hook_session_does_not_bind_among_several_free_runs(sample):
    # FR-1075 AC-409: two unowned runs -> no run is bound and no owner is recorded
    a, b = start_in_worktree(sample), start_in_worktree(sample)
    assert sample.gate("agent-stop", {"sessionId": "sX"}) == {}
    owners = [json.loads(meta_path(w)[1].read_text(encoding="utf-8")).get("session_id") for w in (a, b)]
    assert owners == [None, None]


def test_hook_session_rescues_the_single_free_run(sample):
    # FR-1075 AC-409: exactly one unowned run, identifiable session, no other session's claim -> bound
    a = start_in_worktree(sample)
    res = sample.gate("agent-stop", {"sessionId": "sX"})
    assert res.get("decision") == "block"
    assert json.loads(meta_path(a)[1].read_text(encoding="utf-8")).get("session_id") == "sX"


def test_hook_rescue_refused_while_another_session_has_an_unconsumed_claim(sample):
    # FR-1075 AC-409: another session's start is still pending -> the free run may be its run
    a = start_in_worktree(sample)
    sample.gate("pre-tool", {"sessionId": "sY", "toolName": "powershell", "toolArgs": {
        "command": 'python scripts/run-state.py start --options "max_hours: 9"'}})
    assert sample.gate("agent-stop", {"sessionId": "sX"}) == {}
    assert not json.loads(meta_path(a)[1].read_text(encoding="utf-8")).get("session_id")


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


def _real_subagent_start(sample, parent, agent_id, name="rd-author"):
    # shape of the real subagentStart hook input (events.jsonl of a VS Code session): sessionId is the parent session
    return sample.gate("subagent-start", {"sessionId": parent, "agentId": agent_id, "agentType": name, "agentName": name,
                                          "parentAgentId": parent, "cwd": str(sample.path)})


def test_subagent_tool_calls_use_parent_run_not_a_free_run(sample):
    # real incident: the subagent's preToolUse carries sessionId = agent id; it used to claim a fresh unowned run
    a = start_in_worktree(sample)
    patch_meta(a, session_id="sA")
    _real_subagent_start(sample, "sA", "agent-1")
    b = start_in_worktree(sample)  # a fresh run nobody owns yet
    edit = {"sessionId": "agent-1", "cwd": str(sample.path), "toolName": "edit", "toolArgs": {
        "path": str(a / "docs" / "requirements-definition.md"), "old_str": "a", "new_str": "b"}}
    assert sample.gate("pre-tool", edit) == {}
    assert sample.gate("pre-tool", dict(edit, toolName="create", toolArgs={
        "path": str(a / "work" / "peek.py"), "file_text": "x"})) == {}
    assert not json.loads(meta_path(b)[1].read_text(encoding="utf-8")).get("session_id")


def test_other_session_cannot_write_into_owned_run(sample, tmp_path_factory, monkeypatch):
    # the repo lives under the temp dir (which is an allowed outside location); point the hook at a different temp dir
    other = tmp_path_factory.mktemp("elsewhere")
    for k in ("TEMP", "TMP", "TMPDIR"):
        monkeypatch.setenv(k, str(other))
    a, b = start_in_worktree(sample), start_in_worktree(sample)
    patch_meta(a, session_id="sA")
    patch_meta(b, session_id="sB")
    own = {"sessionId": "sA", "cwd": str(sample.path), "toolName": "create", "toolArgs": {
        "path": str(a / "work" / "note.txt"), "file_text": "x"}}
    assert sample.gate("pre-tool", own) == {}
    # sA (bound to its own run) writing into sB's run, and an unrelated agent id doing the same, are both refused
    for sid in ("sA", "unknown-agent"):
        res = sample.gate("pre-tool", dict(own, sessionId=sid, toolArgs={"path": str(b / "work" / "note.txt"), "file_text": "x"}))
        assert res.get("permissionDecision") == "deny" and "G-5" in res["permissionDecisionReason"], (sid, res)


def test_subagent_record_lifecycle_and_nesting(sample, tmp_path_factory, monkeypatch):
    # recorded child of sA: allowed in sA's run, refused in sB's run; nested agent (parent = agent id) is not
    # trusted in sB's run; after subagent-stop the record is gone and writes into sB's run are refused again.
    other = tmp_path_factory.mktemp("elsewhere2")
    for k in ("TEMP", "TMP", "TMPDIR"):
        monkeypatch.setenv(k, str(other))
    a, b = start_in_worktree(sample), start_in_worktree(sample)
    patch_meta(a, session_id="sA")
    patch_meta(b, session_id="sB")

    def create(run, sid):
        return {"sessionId": sid, "cwd": str(sample.path), "toolName": "create", "toolArgs": {
            "path": str(run / "work" / "note.txt"), "file_text": "x"}}

    _real_subagent_start(sample, "sA", "agent-1")
    assert sample.gate("pre-tool", create(a, "agent-1")) == {}
    assert sample.gate("pre-tool", create(b, "agent-1")).get("permissionDecision") == "deny"
    sample.gate("subagent-start", {"sessionId": "agent-1", "agentId": "agent-2", "agentType": "implementer",
                                   "agentName": "implementer", "parentAgentId": "agent-1", "cwd": str(sample.path)})
    assert sample.gate("pre-tool", create(b, "agent-2")).get("permissionDecision") == "deny"
    sample.gate("subagent-stop", {"sessionId": "agent-1", "agentId": "agent-1", "agentName": "rd-author", "cwd": str(sample.path)})
    assert sample.gate("pre-tool", create(b, "agent-1")).get("permissionDecision") == "deny"

def test_unrecorded_agent_cannot_write_into_unowned_or_foreign_run(sample, tmp_path_factory, monkeypatch):
    # fail-open hole: an agent id with no parent record (session bound to no run) must not write into a sibling run
    # unless it owns it; this holds for an owned run with no session id, and for an unowned (stale) run.
    other = tmp_path_factory.mktemp("elsewhere3")
    for k in ("TEMP", "TMP", "TMPDIR"):
        monkeypatch.setenv(k, str(other))
    a, b = start_in_worktree(sample), start_in_worktree(sample)
    patch_meta(a, session_id="sA")
    patch_meta(b, started_at="2000-01-01T00:00:00+00:00")  # unowned and stale: never auto-claimed

    def create(run, sid):
        d = {"cwd": str(sample.path), "toolName": "create", "toolArgs": {"path": str(run / "work" / "note.txt"), "file_text": "x"}}
        return dict(d, sessionId=sid) if sid else d

    assert sample.gate("pre-tool", create(a, "sA")) == {}
    for run in (a, b):
        for sid in ("unrecorded-agent", ""):
            res = sample.gate("pre-tool", create(run, sid))
            assert res.get("permissionDecision") == "deny" and "G-5" in res["permissionDecisionReason"], (run.name, sid, res)


def test_rd_author_recorded_in_another_tree_still_counts_for_its_session(sample):
    # real incident: with concurrent runs, subagentStart was recorded in a tree other than the session's run,
    # so the session's own run saw no rd-author and refused the requirements edit with G-1.
    a, b = start_in_worktree(sample), start_in_worktree(sample)
    patch_meta(a, session_id="sA")
    patch_meta(b, session_id="sB")
    edit = {"sessionId": "sA", "cwd": str(sample.path), "toolName": "edit", "toolArgs": {
        "path": str(a / "docs" / "requirements-definition.md"), "old_str": "a", "new_str": "b"}}
    assert "G-1" in sample.gate("pre-tool", edit).get("permissionDecisionReason", "")
    f = b / "work" / ".ebak" / "active-agents.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    import time
    f.write_text(json.dumps([{"name": "rd-author", "t": time.time(), "session": "sA"}]), encoding="utf-8")
    assert sample.gate("pre-tool", edit) == {}
    # another session's rd-author does not grant anything to sA, and an untagged record never leaks across sessions
    f.write_text(json.dumps([{"name": "rd-author", "t": time.time(), "session": "sB"},
                             {"name": "rd-author", "t": time.time()}]), encoding="utf-8")
    assert "G-1" in sample.gate("pre-tool", edit).get("permissionDecisionReason", "")
    # subagentStop of the same session releases the record where it was written
    f.write_text(json.dumps([{"name": "rd-author", "t": time.time(), "session": "sA"}]), encoding="utf-8")
    sample.gate("subagent-stop", {"sessionId": "sA", "agentName": "rd-author", "cwd": str(sample.path)})
    assert json.loads(f.read_text(encoding="utf-8")) == []


def test_run_is_owned_by_the_session_that_started_it_not_the_first_other_session(sample):
    # real incident: another session's first tool call claimed a freshly started run (R-2); the real owner was then
    # refused in its own run. The hook records who runs `run-state.py start`, and start stores it in meta.
    shell = {"sessionId": "sA", "cwd": str(sample.path), "toolName": "powershell",
             "toolArgs": {"command": "python scripts/run-state.py start --options x"}}
    assert sample.gate("pre-tool", shell) == {}
    wt = start_in_worktree(sample, "--options", "x")  # the same command line the hook saw (FR-1074 AC-406)
    assert patch_meta(wt)[1]["session_id"] == "sA"
    other = {"sessionId": "sB", "cwd": str(sample.path), "toolName": "edit", "toolArgs": {
        "path": str(wt / "docs" / "requirements-definition.md"), "old_str": "a", "new_str": "b"}}
    sample.gate("pre-tool", other)
    assert patch_meta(wt)[1]["session_id"] == "sA"
    # a second concurrent start by another session gets its own run and owner (claims are consumed in order)
    sample.gate("pre-tool", dict(shell, sessionId="sB"))
    wt2 = start_in_worktree(sample, "--options", "x")
    assert patch_meta(wt2)[1]["session_id"] == "sB"
