"""並列開始の統合試験（NFR-OPS-009 AC-417・AC-418、FR-1074・FR-1076）。

複数のプロセスから、hook の start-claim の記録と `run-state.py start`、主ツリー運用の hook 呼び出しを同時に行う。
同時プロセス数と反復回数は docs の PARAM-051・PARAM-052 から読む。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE / "scripts"))
import ebaklib as h  # noqa: E402


def param(pid: str, default: int) -> int:
    text = (SOURCE / "docs" / "requirements-definition.md").read_text(encoding="utf-8")
    m = re.search(rf"\|\s*{pid}\s*\|[^|]*\|\s*(\d+)\s*\|", text)
    return int(m.group(1)) if m else default


PROCS = param("PARAM-051", 3)
ROUNDS = param("PARAM-052", 20)


def _run(cmd, cwd, input_text=None):
    env = dict(os.environ, PYTHONUTF8="1")
    env.pop("EABK_ALLOW_PRIMARY", None)
    return subprocess.run(cmd, cwd=str(cwd), input=input_text, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)


class Repo:
    def __init__(self, path: Path):
        self.path = path

    def gate(self, event: str, payload: dict) -> dict:
        payload = dict(payload, cwd=str(self.path))
        proc = _run([sys.executable, str(self.path / "scripts" / "hooks" / "gate.py"), event], self.path, json.dumps(payload))
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout) if proc.stdout.strip() else {}


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"],
                 ["config", "commit.gpgsign", "false"]):
        assert _run(["git", *args], root).returncode == 0
    inst = _run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(root), "--skip-verify"], root)
    assert inst.returncode == 0, inst.stdout + inst.stderr
    assert _run(["git", "add", "-A"], root).returncode == 0
    assert _run(["git", "commit", "-q", "-m", "install toolkit"], root).returncode == 0
    return Repo(root)


def denied(res: dict) -> bool:
    return res.get("permissionDecision") == "deny"


def shell(repo, sid, command):
    return repo.gate("pre-tool", {"sessionId": sid, "toolName": "powershell", "toolArgs": {"command": command}})


def create(repo, sid, path):
    return repo.gate("pre-tool", {"sessionId": sid, "toolName": "create", "toolArgs": {"path": str(path), "file_text": "x\n"}})


def start_proc(repo, *args, allow_primary=False):
    env = dict(os.environ, PYTHONUTF8="1")
    env.pop("EABK_ALLOW_PRIMARY", None)
    if allow_primary:
        env["EABK_ALLOW_PRIMARY"] = "1"
    return subprocess.run([sys.executable, str(repo.path / "scripts" / "run-state.py"), "start", *args], cwd=str(repo.path),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


def meta_in(tree: Path) -> dict:
    runs = sorted((tree / "work" / "runs").iterdir())
    return json.loads((runs[-1] / "meta.json").read_text(encoding="utf-8"))


def run_threads(fns):
    errs = []

    def wrap(fn):
        try:
            fn()
        except BaseException as e:  # noqa: BLE001
            errs.append(e)

    ts = [threading.Thread(target=wrap, args=(f,)) for f in fns]
    [t.start() for t in ts]
    [t.join(300) for t in ts]
    assert not errs, errs


# NFR-OPS-009 AC-417: PARAM-051 processes × PARAM-052 rounds of (hook start-claim + run-state.py start)
def test_concurrent_claim_and_start_keep_owners_ac417(repo):
    for rnd in range(ROUNDS):
        out = {}
        barrier = threading.Barrier(PROCS)

        def chat(k):
            sid = f"s{rnd}-{k}"
            opts = f"max_hours: {10 + rnd * PROCS + k}"
            barrier.wait()
            claim = shell(repo, sid, f'python scripts/run-state.py start --options "{opts}"')
            proc = start_proc(repo, "--options", opts)
            out[k] = (sid, claim, proc)

        run_threads([lambda k=k: chat(k) for k in range(PROCS)])
        trees = {}
        for k, (sid, claim, proc) in out.items():
            assert proc.returncode == 0, proc.stdout + proc.stderr
            assert not denied(claim), claim
            trees[k] = Path(proc.stdout.split("WORKTREE ", 1)[1].split("\n")[0].strip())
        assert len(set(trees.values())) == PROCS
        for k, tree in trees.items():
            assert meta_in(tree).get("session_id") == out[k][0], (rnd, k, out[k][2].stdout, out[k][2].stderr)
            assert not denied(create(repo, out[k][0], tree / "work" / f"n{k}.txt")), (rnd, k)
        claims = h.read_json(h.start_claims_file(repo.path, h.load_config(repo.path)), default=[]) or []
        assert not claims, "every claim was consumed exactly once"


# NFR-OPS-009 AC-418: simultaneous hook calls of other sessions all pass, the owner's out-of-scope edits are all denied
def test_concurrent_primary_tree_calls_ac418(repo):
    cmd = 'python scripts/run-state.py start --allow-primary --options "max_hours: 24"'
    assert not denied(shell(repo, "owner", cmd))
    proc = start_proc(repo, "--allow-primary", "--options", "max_hours: 24", allow_primary=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert meta_in(repo.path).get("session_id") == "owner"
    n = PROCS * 4
    res = {}

    def call(i):
        if i % PROCS == 0:
            res[i] = ("owner", create(repo, "owner", repo.path / "src" / f"o{i}.py"))
        else:
            res[i] = ("other", create(repo, f"other-{i}", repo.path / "src" / f"x{i}.py"))

    run_threads([lambda i=i: call(i) for i in range(n)])
    assert len(res) == n
    for who, r in res.values():
        assert denied(r) == (who == "owner"), (who, r)
    assert meta_in(repo.path).get("session_id") == "owner"
