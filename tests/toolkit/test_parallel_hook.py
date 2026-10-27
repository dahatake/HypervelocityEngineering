"""複数 chat の同時実行（FR-1074〜1077・NFR-OPS-010。NFR-OPS-009 の同時試験は tests/integration/test_parallel_start_it.py）: 主ツリー運用・template 状態の分離・commit 先の判定。"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from conftest import SOURCE

from test_multi_run import hold_lock, meta_path, patch_meta, start_in_worktree

SCRIPTS = SOURCE / "scripts"
sys.path.insert(0, str(SCRIPTS))
import ebaklib as h  # noqa: E402


def denied(res: dict) -> bool:
    return res.get("permissionDecision") == "deny"


def shell(repo, sid, command, cwd=None):
    d = {"toolName": "powershell", "toolArgs": {"command": command}, "cwd": str(cwd or repo.path)}
    if sid:
        d["sessionId"] = sid
    return repo.gate("pre-tool", d)


def create(repo, sid, path, cwd=None):
    d = {"toolName": "create", "toolArgs": {"path": str(path), "file_text": "x\n"}, "cwd": str(cwd or repo.path)}
    if sid:
        d["sessionId"] = sid
    return repo.gate("pre-tool", d)


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


def start_primary_run(sample, owner):
    cmd = 'python scripts/run-state.py start --allow-primary --options "max_hours: 24"'
    assert not denied(shell(sample, owner, cmd))
    proc = start_proc(sample, "--allow-primary", "--options", "max_hours: 24", allow_primary=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert meta_in(sample.path).get("session_id") == owner


# FR-1076 AC-411/412 + users-guide 06 の「外すゲート・残すゲート」
def test_primary_tree_run_gates_only_the_owner_ac411_ac412(sample):
    start_primary_run(sample, "owner")
    src = sample.path / "src" / "feature.py"
    assert denied(create(sample, "owner", src))  # G-5 for the owner
    assert not denied(create(sample, "other", src))  # AC-411
    assert denied(create(sample, "", src))  # AC-412: no session id keeps the gates
    # gates that stay for every session
    assert denied(create(sample, "other", sample.path / "docs" / "id-registry.md"))  # G-3
    assert denied(create(sample, "other", sample.path / "tests" / "system" / "ledger.json"))  # G-2
    assert denied(create(sample, "other", sample.path / "debug.log"))  # G-6
    assert denied(shell(sample, "other", "git push --force origin work/x"))  # G-5 (always)
    # run-dependent gates are not applied to the other session
    assert denied(shell(sample, "owner", "git push origin run/x"))  # git_push is off in the run options
    assert not denied(shell(sample, "other", "git push origin run/x"))
    hooks = sample.path / "scripts" / "hooks" / "gate.py"
    assert denied(create(sample, "owner", hooks))  # G-5 hooks are frozen for the run
    assert not denied(create(sample, "other", hooks))


def test_primary_tree_unowned_run_keeps_gates_ac412(sample):
    start_primary_run(sample, "owner")
    patch_meta(sample.path, session_id=None)
    src = sample.path / "src" / "feature.py"
    assert denied(create(sample, "someone", src))  # unowned run, primary tree: nothing rescues it


# FR-1077 AC-414〜416
def test_template_state_is_per_session(sample):
    prompt = {"prompt": "/build template"}
    sample.gate("user-prompt", dict(prompt, sessionId="s1"))
    sample.gate("user-prompt", dict(prompt, sessionId="s2"))
    state = sample.path / "work" / ".ebak"
    assert len(list(state.glob("template-request-*.json"))) == 2  # AC-414
    assert denied(shell(sample, "s1", "echo hi")) and denied(shell(sample, "s2", "echo hi"))
    sample.gate("user-prompt", {"sessionId": "s1", "prompt": "hello"})  # AC-415: only s1's state goes
    assert not denied(shell(sample, "s1", "echo hi"))
    assert denied(shell(sample, "s2", "echo hi"))
    sample.gate("user-prompt", {"prompt": "hello"})  # AC-416: no session id removes nobody else's state
    assert denied(shell(sample, "s2", "echo hi"))
    sample.gate("user-prompt", {"sessionId": "s2", "prompt": "hello"})
    assert not denied(shell(sample, "s2", "echo hi"))
    assert not list(state.glob("template-request*.json"))


# 不具合修正: run の worktree への commit を cwd の branch（main）で誤拒否しない
def test_commit_in_run_worktree_is_not_judged_by_cwd_branch(sample):
    wt = start_in_worktree(sample)
    patch_meta(wt, session_id="sA")
    sib = lambda cmd, cwd=None: shell(sample, "sA", cmd, cwd)  # noqa: E731
    assert not denied(sib(f'git -C "{wt}" commit -m x'))
    assert not denied(sib(f"cd {wt}; git commit -m x"))
    assert not denied(sib(f"cd '{wt}' && git add -A && git commit -m x"))
    assert not denied(sib("git commit -m x", cwd=wt))
    assert denied(sib("git commit -m x"))  # this really commits on main
    assert denied(sib(f'git -C "{sample.path}" commit -m x'))
    assert denied(sib(f"cd {wt}; cd {sample.path}; git commit -m x"))


# NFR-OPS-010 AC-419: a crashed holder leaves no lock behind; a live lock past PARAM-053 fails without writing
def test_crashed_lock_holder_is_released_and_busy_lock_fails_without_writing_ac419(sample):
    cfg = h.load_config(sample.path)
    f = h.start_claims_file(sample.path, cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    lock = f.with_name("start-claims.lock")
    cmd = 'python scripts/run-state.py start --options "max_hours: 9"'
    holder = hold_lock(lock)
    holder.kill()  # the holder crashed while holding the lock
    holder.wait()
    assert not denied(shell(sample, "sA", cmd))
    claims = json.loads(f.read_text(encoding="utf-8"))
    assert [c["session"] for c in claims] == ["sA"] and claims[0]["ident"]
    before = f.read_text(encoding="utf-8")
    holder = hold_lock(lock)  # a live holder
    try:
        t0 = time.time()
        res = shell(sample, "sB", cmd)
        assert denied(res) and "claim" in res["permissionDecisionReason"]
        assert h.CLAIM_LOCK_WAIT_SEC - 1 <= time.time() - t0 < h.CLAIM_LOCK_WAIT_SEC + 20
        assert f.read_text(encoding="utf-8") == before
    finally:
        holder.kill()
        holder.wait()


# NFR-OPS-010 AC-420: changed hook / run-state are installed (MANAGED) and the guides describe the new behaviour
def test_managed_files_and_guides_match_the_new_behaviour_ac420():
    install = (SOURCE / "tools" / "install.py").read_text(encoding="utf-8")
    for rel in ("scripts/hooks/gate.py", "scripts/run-state.py", "scripts/ebaklib.py"):
        assert f'"{rel}"' in install
    trouble = (SOURCE / "users-guide" / "07-troubleshooting.md").read_text(encoding="utf-8")
    for word in ("start-claims.lock", "識別子", "候補が 1 つ", "を掛けません", "template-request-<session>.json"):
        assert word in trouble, word
    gates = (SOURCE / "users-guide" / "06-quality-gates.md").read_text(encoding="utf-8")
    for gid in ("G-1", "G-2", "G-3", "G-5", "G-6"):
        assert gid in gates.split("### 6.1.1", 1)[1].split("**エージェントの識別方法**", 1)[0], gid
