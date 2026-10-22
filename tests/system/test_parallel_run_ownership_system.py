"""System acceptance tests for parallel /build runs (FR-1074, FR-1076).

The oracle is the acceptance criteria AC-407 and AC-413 of the requirements
definition, not the current hook / run-state implementation.  Each "chat" is
a separate set of processes: the hook (gate.py pre-tool) and run-state.py start.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from conftest import run

CHATS = 3


def _env(allow_primary: bool) -> dict:
    env = dict(os.environ, PYTHONUTF8="1")
    env.pop("EABK_ALLOW_PRIMARY", None)
    if allow_primary:
        env["EABK_ALLOW_PRIMARY"] = "1"
    return env


def gate(repo: Path, payload: dict) -> dict:
    payload = dict(payload, cwd=str(repo))
    proc = subprocess.run(
        [sys.executable, str(repo / "scripts" / "hooks" / "gate.py"), "pre-tool"],
        cwd=repo, input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=_env(False),
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def denied(result: dict) -> bool:
    text = json.dumps(result, ensure_ascii=False)
    return "deny" in text or result.get("decision") == "block"


def shell_payload(session: str, command: str) -> dict:
    return {"sessionId": session, "toolName": "powershell", "toolArgs": {"command": command}}


def edit_payload(session: str, path: Path) -> dict:
    return {"sessionId": session, "toolName": "create", "toolArgs": {"path": str(path), "file_text": "x\n"}}


def meta_of(worktree: Path) -> dict:
    runs = sorted((worktree / "work" / "runs").iterdir())
    return json.loads((runs[-1] / "meta.json").read_text(encoding="utf-8"))


# FR-1074 AC-407
def test_concurrent_chats_each_own_the_run_they_started_ac407(installed_repo: Path):
    repo = installed_repo
    barrier = threading.Barrier(CHATS)
    out: dict[int, dict] = {}

    def chat(k: int) -> None:
        session = f"chat-{k}"
        cmd = f'python scripts/run-state.py start --options "max_hours: {20 + k}"'
        barrier.wait()
        claim = gate(repo, shell_payload(session, cmd))
        proc = subprocess.run(
            [sys.executable, str(repo / "scripts" / "run-state.py"), "start", "--options", f"max_hours: {20 + k}"],
            cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace", env=_env(False),
        )
        out[k] = {"session": session, "claim": claim, "proc": proc}

    threads = [threading.Thread(target=chat, args=(k,)) for k in range(CHATS)]
    [t.start() for t in threads]
    [t.join(180) for t in threads]
    assert len(out) == CHATS

    worktrees = {}
    for k, r in out.items():
        assert r["proc"].returncode == 0, r["proc"].stdout + r["proc"].stderr
        assert not denied(r["claim"]), r["claim"]
        worktrees[k] = Path(r["proc"].stdout.split("WORKTREE ", 1)[1].split("\n")[0].strip())
    assert len(set(worktrees.values())) == CHATS

    for k, wt in worktrees.items():
        assert meta_of(wt).get("session_id") == out[k]["session"], f"chat {k} does not own the run it started"
    for k, wt in worktrees.items():
        res = gate(repo, edit_payload(out[k]["session"], wt / "work" / f"note-{k}.txt"))
        assert not denied(res), f"owner chat {k} was refused in its own run: {res}"


# FR-1074 AC-407 (abnormal: a chat that did not start the run must not take it over)
def test_other_chat_does_not_take_over_a_started_run_ac407(installed_repo: Path):
    repo = installed_repo
    cmd = 'python scripts/run-state.py start --options "max_hours: 21"'
    assert not denied(gate(repo, shell_payload("owner", cmd)))
    proc = subprocess.run(
        [sys.executable, str(repo / "scripts" / "run-state.py"), "start", "--options", "max_hours: 21"],
        cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace", env=_env(False),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    wt = Path(proc.stdout.split("WORKTREE ", 1)[1].split("\n")[0].strip())
    gate(repo, edit_payload("intruder", wt / "work" / "x.txt"))
    assert meta_of(wt).get("session_id") == "owner"
    assert not denied(gate(repo, edit_payload("owner", wt / "work" / "x.txt")))


# FR-1076 AC-413
def test_primary_tree_run_does_not_gate_other_chat_edits_ac413(installed_repo: Path):
    repo = installed_repo
    cmd = 'python scripts/run-state.py start --allow-primary --options "max_hours: 24"'
    assert not denied(gate(repo, shell_payload("owner", cmd)))
    proc = subprocess.run(
        [sys.executable, str(repo / "scripts" / "run-state.py"), "start", "--allow-primary", "--options", "max_hours: 24"],
        cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace", env=_env(True),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert meta_of(repo).get("session_id") == "owner"

    unrelated = repo / "src" / "unrelated_feature.py"
    for other in ("other-1", "other-2"):
        res = gate(repo, edit_payload(other, unrelated))
        assert not denied(res), f"unrelated chat {other} was refused: {res}"
    # the owner chat keeps the usual scope: editing outside the run's range is still refused
    res = gate(repo, edit_payload("owner", unrelated))
    assert denied(res), f"owner edited outside the run scope: {res}"
    assert meta_of(repo).get("session_id") == "owner"
