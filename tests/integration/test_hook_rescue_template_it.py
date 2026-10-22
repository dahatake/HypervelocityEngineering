"""hook の所有者なし run の救済の厳格化（FR-1075 AC-408・AC-409・AC-410）と template 状態の session 分離（FR-1077 AC-414〜416）の統合試験。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_parallel_start_it import _run, denied, repo, shell, start_proc, SOURCE  # noqa: E402,F401


def _start_worktree(repo) -> Path:
    proc = start_proc(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return Path(proc.stdout.split("WORKTREE ", 1)[1].split("\n")[0].strip())


def _meta(wt: Path):
    p = sorted((wt / "work" / "runs").iterdir())[-1] / "meta.json"
    return p, json.loads(p.read_text(encoding="utf-8"))


def _unowned(wt: Path):
    p, m = _meta(wt)
    m["session_id"] = None
    p.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return p


def _in_run(repo, sid, wt):
    return repo.gate("pre-tool", {"sessionId": sid, "toolName": "create", "cwd": str(wt),
                                  "toolArgs": {"path": str(wt / "docs" / "requirements-definition.md"), "file_text": "x\n"}})


def _owner(p: Path):
    return json.loads(p.read_text(encoding="utf-8")).get("session_id")


# FR-1075 AC-409/AC-408: a single unowned run + identifiable session is rescued; once owned, another session cannot take it
def test_single_unowned_run_rescued_then_owner_fixed_fr1075_ac408_ac409(repo):
    wt = _start_worktree(repo)
    p = _unowned(wt)
    shell(repo, "sA", "echo hi")
    assert _owner(p) == "sA"
    shell(repo, "sB", "echo hi")
    assert _owner(p) == "sA"  # AC-408: owner unchanged


# FR-1075 AC-409: two unowned runs -> nothing is bound
def test_two_unowned_runs_bind_nothing_fr1075_ac409(repo):
    p1 = _unowned(_start_worktree(repo))
    p2 = _unowned(_start_worktree(repo))
    shell(repo, "sA", "echo hi")
    assert _owner(p1) is None and _owner(p2) is None


# FR-1075 AC-410: no session id -> no run is bound
def test_no_session_id_binds_nothing_fr1075_ac410(repo):
    p = _unowned(_start_worktree(repo))
    repo.gate("pre-tool", {"toolName": "powershell", "toolArgs": {"command": "echo hi"}, "cwd": str(repo.path)})
    assert _owner(p) is None


# FR-1077 AC-414/AC-415/AC-416
def test_template_state_per_session_fr1077_ac414_ac415_ac416(repo):
    state = repo.path / "work" / ".ebak"
    for s in ("s1", "s2"):
        repo.gate("user-prompt", {"sessionId": s, "prompt": "/build template"})
    assert len(list(state.glob("template-request-*.json"))) == 2  # AC-414
    repo.gate("user-prompt", {"sessionId": "s1", "prompt": "hello"})  # AC-415
    assert len(list(state.glob("template-request-*.json"))) == 1
    assert denied(shell(repo, "s2", "echo hi"))
    repo.gate("user-prompt", {"prompt": "hello"})  # AC-416: no id removes nobody else's
    assert denied(shell(repo, "s2", "echo hi"))
    repo.gate("user-prompt", {"sessionId": "s2", "prompt": "hello"})
    assert not list(state.glob("template-request*.json"))
