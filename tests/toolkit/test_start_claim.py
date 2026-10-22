"""start-claim の排他・結びつけ（FR-1074 AC-405・AC-406）と所有者なし run の救済の安全側（FR-1075 AC-408・AC-410）。"""
import importlib.util
import json
import os
import threading
import time
from pathlib import Path

import pytest

from test_multi_run import hold_lock, meta_path, patch_meta, start_in_worktree

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load_modules():
    import sys
    sys.path.insert(0, str(SCRIPTS))
    import ebaklib as h
    spec = importlib.util.spec_from_file_location("run_state_claim", SCRIPTS / "run-state.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return h, mod


h, rs = load_modules()


def write_claims(root, claims):
    cfg = h.load_config(root)
    f = h.start_claims_file(root, cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    h.write_json(f, claims)
    return cfg, f


def claim(session, ident, age=0):
    return {"session": session, "t": time.time() - age, "ident": ident}


# FR-1074 AC-406: the hook (command line) and start (argv) compute the same identifier
def test_ident_of_command_equals_ident_of_argv_ac406():
    cmd = 'python scripts/run-state.py start --options "max_hours: 21" 2>&1 | tee x.log'
    assert h.start_ident_from_command(cmd) == h.start_ident_from_text(" ".join(["--options", "max_hours: 21"]))
    assert h.start_ident_from_command('python scripts/run-state.py start --options "max_hours: 21"') != \
        h.start_ident_from_command('python scripts/run-state.py start --options "max_hours: 22"')
    assert h.start_ident_from_command("python scripts/run-state.py start --options $OPTS") is None


# FR-1074 AC-406: only the claim with my identifier is consumed; no oldest-first
def test_take_consumes_only_matching_claim_ac406(repo):
    a, b = h.start_ident_from_text("--options a"), h.start_ident_from_text("--options b")
    cfg, f = write_claims(repo.path, [claim("sA", a, age=30), claim("sB", b, age=10)])
    assert rs.take_start_claim(repo.path, cfg, ident=b) == "sB"
    left = json.loads(f.read_text(encoding="utf-8"))
    assert [c["session"] for c in left] == ["sA"]


# FR-1074 AC-406: no matching claim -> take nothing (never the oldest of another start)
def test_take_without_match_takes_nothing_ac406(repo):
    cfg, f = write_claims(repo.path, [claim("sA", "aaaa", age=30), claim("sB", "bbbb", age=10)])
    assert rs.take_start_claim(repo.path, cfg, ident="cccc") is None
    assert len(json.loads(f.read_text(encoding="utf-8"))) == 2


# FR-1074 AC-406: unidentified claim is used only when it is the sole claim
def test_take_unidentified_claim_only_when_sole_ac406(repo):
    cfg, f = write_claims(repo.path, [claim("sA", None)])
    assert rs.take_start_claim(repo.path, cfg, ident="x") == "sA"
    cfg, f = write_claims(repo.path, [claim("sA", None), claim("sB", "bbbb")])
    assert rs.take_start_claim(repo.path, cfg, ident="x") is None
    cfg, f = write_claims(repo.path, [claim("sA", None), claim("sB", None)])
    assert rs.take_start_claim(repo.path, cfg, ident="x") is None


# FR-1074 AC-406: same identifier from different sessions is ambiguous -> nothing taken
def test_take_ambiguous_same_ident_takes_nothing_ac406(repo):
    cfg, f = write_claims(repo.path, [claim("sA", "same"), claim("sB", "same")])
    assert rs.take_start_claim(repo.path, cfg, ident="same") is None


# FR-1074 AC-405: concurrent consumers: each claim is consumed exactly once
def test_concurrent_take_consumes_each_claim_once_ac405(repo):
    n = 8
    cfg, f = write_claims(repo.path, [claim(f"s{k}", f"id{k}") for k in range(n)])
    got, barrier = {}, threading.Barrier(n * 2)

    def worker(tag, k):
        barrier.wait()
        got[(tag, k)] = rs.take_start_claim(repo.path, cfg, ident=f"id{k}")

    ts = [threading.Thread(target=worker, args=(tag, k)) for k in range(n) for tag in "ab"]
    [t.start() for t in ts]
    [t.join(60) for t in ts]
    for k in range(n):
        res = [got[("a", k)], got[("b", k)]]
        assert sorted(r for r in res if r) == [f"s{k}"], (k, res)  # exactly one of the two takers got it
    assert json.loads(f.read_text(encoding="utf-8")) == []


# FR-1074 AC-405: concurrent appends are not lost
def test_concurrent_append_keeps_every_claim_ac405(repo):
    n = 10
    cfg = h.load_config(repo.path)
    f = h.start_claims_file(repo.path, cfg)
    barrier = threading.Barrier(n)

    def append(k):
        barrier.wait()
        with h.start_claims_lock(repo.path, cfg):
            cur = h.read_json(f, default=[]) or []
            time.sleep(0.01)
            cur.append(claim(f"s{k}", f"id{k}"))
            h.write_json(f, cur)

    ts = [threading.Thread(target=append, args=(k,)) for k in range(n)]
    [t.start() for t in ts]
    [t.join(60) for t in ts]
    assert sorted(c["session"] for c in json.loads(f.read_text(encoding="utf-8"))) == sorted(f"s{k}" for k in range(n))


# FR-1074 AC-405: lock wait is bounded (PARAM-053) and a failure writes nothing; orphaned locks are released
def test_lock_busy_fails_without_writing_and_orphan_is_released_ac405(repo):
    assert h.CLAIM_LOCK_WAIT_SEC == 10  # PARAM-053
    cfg, f = write_claims(repo.path, [claim("sA", "x")])
    lock = f.with_name("start-claims.lock")
    holder = hold_lock(lock)  # a live holder in another process
    before = f.read_text(encoding="utf-8")
    try:
        t0 = time.time()
        with pytest.raises(h.LockBusy):
            with h.start_claims_lock(repo.path, cfg, wait=0.3):
                pass
        assert time.time() - t0 < 5
        h.CLAIM_LOCK_WAIT_SEC, saved = 0.3, h.CLAIM_LOCK_WAIT_SEC
        try:
            with pytest.raises(SystemExit) as e:
                rs.take_start_claim(repo.path, cfg, ident="x")
            assert "排他" in str(e.value)
        finally:
            h.CLAIM_LOCK_WAIT_SEC = saved
        assert f.read_text(encoding="utf-8") == before
    finally:
        holder.kill()  # the holder crashes: the OS releases the lock, nothing is left behind
        holder.wait()
    assert rs.take_start_claim(repo.path, cfg, ident="x") == "sA"


# FR-1074 AC-405/406: start records the owner of the claim that matches its own command
def test_start_records_session_of_matching_claim_ac406(sample):
    cfg = h.load_config(sample.path)
    other = h.start_ident_from_text("--options max_hours: 30")
    write_claims(sample.path, [claim("other", other, age=60)])
    # a start whose identifier matches no claim must not take the other start's claim
    wt = start_in_worktree(sample)
    assert not json.loads(meta_path(wt)[1].read_text(encoding="utf-8")).get("session_id")
    assert [c["session"] for c in json.loads(h.start_claims_file(sample.path, cfg).read_text(encoding="utf-8"))] == ["other"]


# FR-1075 AC-408: a run whose owner was fixed by a claim is not rebound to another session by the hook
def test_claimed_run_is_not_rebound_to_other_session_ac408(sample):
    wt = start_in_worktree(sample)
    patch_meta(wt, session_id="owner")
    for sid in ("intruder", "intruder-2"):
        sample.gate("agent-stop", {"sessionId": sid})
        assert json.loads(meta_path(wt)[1].read_text(encoding="utf-8"))["session_id"] == "owner"


# FR-1075 AC-410: no session id on the hook input -> no run is bound
def test_no_session_id_binds_no_run_ac410(sample):
    wt = start_in_worktree(sample)
    sample.gate("agent-stop", {})
    sample.gate("pre-tool", {"toolName": "create", "toolArgs": {"path": str(wt / "work" / "x.txt"), "file_text": "x"}})
    assert not json.loads(meta_path(wt)[1].read_text(encoding="utf-8")).get("session_id")
