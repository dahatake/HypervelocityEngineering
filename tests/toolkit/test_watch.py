"""Unit tests for scripts/watch.py (FR-1064, NFR-OPS-008)."""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "watch.py"
SPEC = importlib.util.spec_from_file_location("watch", SCRIPT)
assert SPEC and SPEC.loader
watch = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = watch
SPEC.loader.exec_module(watch)

REPO = "C:/repo/EABK"


def proc(pid=100, ppid=1, name="node.exe", cmd="node C:\\repo\\EABK\\x.js", age=30):
    return {"pid": pid, "ppid": ppid, "name": name, "cmd": cmd, "age_min": age}


def cls(p, protected=frozenset(), pids=frozenset({1, 100}), under=None):
    return watch.classify(p, [REPO], set(protected), set(pids), under=under)


# FR-1064 AC-357 AC-358 / NFR-OPS-008 AC-365: orphan / stale are killed
def test_orphan_killed():
    kill, _, kind = cls(proc(ppid=999))
    assert kill and kind == "孤児"


def test_stale_killed():
    kill, _, kind = cls(proc(age=121))
    assert kill and kind == "古い"


# FR-1064 AC-358 / NFR-OPS-008 AC-365: exclusions
def test_self_and_ancestors_not_killed():
    assert not cls(proc(ppid=999), protected={100})[0]
    parent_of = {10: 5, 5: 2, 2: 0}
    assert watch.ancestors(10, parent_of) == {10, 5, 2}


def test_within_grace_not_killed():
    assert not cls(proc(ppid=999, age=10))[0]
    assert not cls(proc(ppid=999, age=3), under="C:/repo/EABK")[0]


def test_other_repo_not_killed():
    assert not cls(proc(ppid=999, cmd="node D:\\other\\a.js"))[0]


def test_unwatched_name_not_killed():
    assert not cls(proc(ppid=999, name="python.exe"))[0]
    assert not cls(proc(ppid=999, name="python.exe"), under="C:/repo/EABK")[0]


def test_healthy_young_process_not_killed():
    assert not cls(proc(age=30))[0]


# FR-1064 AC-359: --under
def test_under_kills_regardless_of_orphan_or_age():
    assert cls(proc(age=30), under="C:\\repo\\EABK")[0]


def test_under_empty_or_root_kills_nothing():
    for u in ("", "/", "C:\\", "C:"):
        assert not cls(proc(ppid=999, age=500), under=u)[0]
        assert watch.is_root_path(u)


# FR-1064 AC-360 / NFR-OPS-008 AC-365: stuck
def test_stuck_exit_codes():
    now = dt.datetime(2026, 1, 1, 12, 0, 0)
    q = {"items": [
        {"id": "a", "status": "doing", "started_at": "2026-01-01T10:30:00"},
        {"id": "b", "status": "doing", "started_at": "2026-01-01T11:30:00"},
        {"id": "c", "status": "done", "started_at": "2026-01-01T01:00:00"},
    ]}
    rows = watch.stuck_items(q, now, 60)
    assert rows == [("a", 90)]
    assert watch.stuck_exit_code(rows) == 1
    assert watch.stuck_exit_code(watch.stuck_items(q, now, 120)) == 0
    assert watch.stuck_items({"items": []}, now) == []


# NFR-OPS-008 AC-365: standard library only
def test_stdlib_only():
    import re
    src = SCRIPT.read_text(encoding="utf-8")
    mods = set(re.findall(r"^(?:import|from)\s+([a-zA-Z_]+)", src, re.M))
    assert mods <= set(sys.stdlib_module_names) | {"__future__"}


# FR-1064 AC-359 (audit A-01): --under matches only at a path boundary
def test_under_matches_boundary():
    w1 = "C:\\wt\\run-w1"
    assert watch.under_matches(w1, "node C:\\wt\\run-w1\\x.js")
    assert watch.under_matches(w1, 'node "c:/WT/run-w1"')
    assert watch.under_matches(w1, "node C:\\wt\\run-w1")
    assert not watch.under_matches(w1, "node C:\\wt\\run-w10\\x.js")
    assert not watch.under_matches(w1, "node C:\\wt\\run-w10")


def test_classify_under_w1_keeps_w10():
    p = proc(cmd="node C:\\wt\\run-w10\\x.js")
    kill, _, _ = cls(p, under="C:\\wt\\run-w1")
    assert not kill
    kill, _, _ = cls(proc(cmd="node C:\\wt\\run-w1\\x.js"), under="C:\\wt\\run-w1")
    assert kill
