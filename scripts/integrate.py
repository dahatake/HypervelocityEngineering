#!/usr/bin/env python3
"""integrate.py - worker worktree pool and one-command integration for the conductor (implementation loop).

Usage:
  python scripts/integrate.py prepare I-01            # take a pooled worktree, check out work/<run-id>/I-01, mark doing
  python scripts/integrate.py merge I-01 [--full] [--summary "..."]
                                                      # merge -> verify -> scoped System Test -> commit -> release
  python scripts/integrate.py abandon I-01 [--blocked] [--reason "..."]
                                                      # give the item back (todo / blocked) and release its worktree
  python scripts/integrate.py pool [--prune]          # list the pool; --prune removes idle pooled worktrees

Why (speed): the per-item cost of the loop used to be a fresh `git worktree add` (cold build every time) and
6-8 separate conductor tool calls for merge / verify / ledger / commit / cleanup. Here a fixed pool of worktrees
(work/worktrees/<run-id>-w<N>) is reused, so ignored build outputs (node_modules, bin/obj, .venv ...) survive,
and `merge` does the whole serial integration in one call and prints at most a few lines.

merge:
  * verify runs with --quick (slow commands skipped); every FULL_EVERY-th integration and with --full it runs
    every command. The final gate (stage 6) still runs `verify.py --strict` and the whole System Test.
  * System Test cases are selected against the commit before the merge (only this item's changes), keeping
    the canary and dropping cases whose requirements are not integrated yet (they cannot pass yet).
  * On a merge conflict, a verify failure or a System Test failure the merge is undone (`git reset --hard`),
    the item goes back to todo and the exit code is non-zero, so the integration branch stays green.
Exit codes: 0 pass, 1 gate failed (item back to todo), 2 conflict / usage error.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hvelib as h  # noqa: E402

FULL_EVERY = 5
LOCK_STALE_SEC = 3600


class Ctx:
    def __init__(self, root_arg: Optional[str]):
        root = Path(root_arg).resolve() if root_arg else h.repo_root()
        self.root = h.conductor_root(root, h.load_config(root))
        self.cfg = h.load_config(self.root)
        self.rid = h.current_run(self.root, self.cfg)
        if not self.rid or not (h.run_dir(self.root, self.cfg, self.rid) / "meta.json").exists():
            raise SystemExit("ERROR integrate: 実行中の run がありません（run-state.py start）")
        self.meta = h.load_meta(self.root, self.cfg, self.rid)
        self.integration = self.meta.get("integration_branch") or h.current_branch(self.root)
        self.rs = h.load_script("run-state")

    def queue(self) -> dict:
        return h.load_queue(self.root, self.cfg, self.rid)

    def save(self, q: dict) -> None:
        h.write_json(h.run_dir(self.root, self.cfg, self.rid) / "queue.json", q)

    def item(self, q: dict, item_id: str) -> dict:
        for it in q.get("items", []):
            if it["id"] == item_id:
                return it
        raise SystemExit(f"ERROR integrate: {item_id} が queue にありません")

    def pool_dir(self) -> Path:
        return h.work_dir(self.root, self.cfg) / "worktrees"

    def rel(self, p: Path) -> str:
        try:
            return p.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return p.as_posix()

    def progress(self, text: str) -> None:
        self.rs.append_progress(self.root, self.cfg, self.rid, h.load_meta(self.root, self.cfg, self.rid), text)


def git_ok(args: List[str], cwd: Path) -> str:
    rc, out = h.git(args, cwd)
    if rc != 0:
        raise SystemExit(f"ERROR integrate: git {' '.join(args)} が失敗しました: {out.strip()[:300]}")
    return out


def branch_exists(root: Path, branch: str) -> bool:
    return h.ref_exists(root, f"refs/heads/{branch}")


def registered_worktrees(root: Path) -> Set[str]:
    rc, out = h.git(["worktree", "list", "--porcelain"], root)
    if rc != 0:
        return set()
    return {os.path.normcase(str(Path(l.split(" ", 1)[1]).resolve())) for l in out.splitlines() if l.startswith("worktree ")}


def detach(wt: Path) -> None:
    if wt.exists():
        h.git(["checkout", "-q", "--detach", "-f"], wt)


# ---------------------------------------------------------------------- prepare

def pick_slot(c: Ctx, q: dict, current: Optional[str]) -> Path:
    busy = {os.path.normcase(str((c.root / it["worktree"]).resolve())) for it in q.get("items", [])
            if it.get("status") == "doing" and it.get("worktree")}
    live = registered_worktrees(c.root)
    if current:
        p = (c.root / current).resolve()
        if os.path.normcase(str(p)) in live:
            return p
    n = 1
    while True:
        p = (c.pool_dir() / f"{c.rid}-w{n}").resolve()
        key = os.path.normcase(str(p))
        if key not in busy:
            if key in live:
                return p
            if p.exists():
                h.git(["worktree", "prune"], c.root)
                if p.exists() and any(p.iterdir()):
                    n += 1
                    continue
            p.parent.mkdir(parents=True, exist_ok=True)
            git_ok(["worktree", "add", "-q", "--detach", str(p), c.integration], c.root)
            return p
        n += 1


def cmd_prepare(c: Ctx, args) -> int:
    q = c.queue()
    it = c.item(q, args.item)
    if it.get("status") in ("done", "blocked"):
        raise SystemExit(f"ERROR integrate: {args.item} は {it['status']} です")
    branch = it.get("branch") or f"work/{c.rid}/{args.item}"
    wt = pick_slot(c, q, it.get("worktree") if it.get("status") == "doing" else None)
    note = ""
    if branch_exists(c.root, branch):
        git_ok(["checkout", "-q", "-f", branch], wt)
        rc, out = h.git(["merge", "-q", "--no-edit", c.integration], wt)
        if rc != 0:
            h.git(["merge", "--abort"], wt)
            note = f"NOTE: 統合ブランチ {c.integration} との競合があります。最初に `git merge {c.integration}` で解消します"
    else:
        git_ok(["checkout", "-q", "-f", "-B", branch, c.integration], wt)
    h.git(["clean", "-q", "-fd"], wt)  # untracked leftovers only; ignored build outputs are kept on purpose
    if it.get("status") != "doing":
        c.rs.mark_status(it, "doing")
        it["attempts"] = it.get("attempts", 0) + 1
    it["branch"] = branch
    it["worktree"] = c.rel(wt)
    c.save(q)
    print(f"WORKTREE: {wt}")
    print(f"BRANCH: {branch}  BASE: {c.integration}@{h.head_commit(c.root)}  attempts={it['attempts']}")
    if note:
        print(note)
    return 0


# ---------------------------------------------------------------------- merge

class Lock:
    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and time.time() - self.path.stat().st_mtime > LOCK_STALE_SEC:
            self.path.unlink()
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise SystemExit("ERROR integrate: 別の統合が実行中です（統合は 1 本ずつ直列に行います）")
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return self

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except OSError:
            pass


def select_cases(c: Ctx, q: dict, it: dict, base: str) -> List[dict]:
    ledger = h.load_script("ledger")
    data = h.load_ledger(c.root, c.cfg)
    integrated: Set[str] = {r for x in q.get("items", []) if x.get("status") == "done" for r in x.get("requirement_ids", [])}
    integrated |= set(it.get("requirement_ids", []))
    picked = ledger.select_cases(c.root, c.cfg, data, "changed", base)
    picked += [x for x in data.get("cases", []) if x.get("canary") and x.get("status") != "blocked"]
    out, seen = [], set()
    for x in picked:
        if x["id"] in seen or not x.get("command"):
            continue
        reqs = set(x.get("requirement_ids", []))
        if x.get("canary") or reqs <= integrated:
            out.append(x)
            seen.add(x["id"])
    return out


def give_back(c: Ctx, item_id: str, status: str = "todo") -> None:
    q = c.queue()
    it = c.item(q, item_id)
    c.rs.mark_status(it, status)
    if it.get("worktree"):
        detach((c.root / it["worktree"]).resolve())
        it["worktree"] = None
    c.save(q)


def tail(out: str, n: int = 8) -> str:
    lines = [l for l in out.splitlines() if l.startswith(("FAIL", "  ", "verify:", "ledger run:")) or " fail " in l]
    return "\n".join(lines[:n])


def cmd_merge(c: Ctx, args) -> int:
    t0 = time.time()
    with Lock(h.work_dir(c.root, c.cfg) / ".hve" / "integrate.lock"):
        cur = h.current_branch(c.root)
        if cur != c.integration:
            raise SystemExit(f"ERROR integrate: 統合ブランチ {c.integration} の上で実行します（現在: {cur}）")
        rc, dirty = h.git(["status", "--porcelain", "--untracked-files=no"], c.root)
        if dirty.strip():
            raise SystemExit("ERROR integrate: 統合ブランチに commit していない変更があります:\n" + dirty[:500])
        q = c.queue()
        it = c.item(q, args.item)
        branch = it.get("branch") or f"work/{c.rid}/{args.item}"
        if not branch_exists(c.root, branch):
            raise SystemExit(f"ERROR integrate: ブランチ {branch} がありません")
        ahead = git_ok(["rev-list", "--count", f"{c.integration}..{branch}"], c.root).strip()
        if ahead == "0":
            raise SystemExit(f"ERROR integrate: {branch} に統合する commit がありません")
        pre = git_ok(["rev-parse", "HEAD"], c.root).strip()
        reqs = ",".join(it.get("requirement_ids", []))
        rc, out = h.git(["merge", "--no-ff", "--no-edit", "-m", f"Merge {args.item} [{reqs}]", branch], c.root)
        if rc != 0:
            h.git(["merge", "--abort"], c.root)
            give_back(c, args.item)
            print(f"INTEGRATE: conflict {args.item} -> todo（次の prepare で統合ブランチを取り込み、implementer が競合を解消します）")
            print("\n".join(out.splitlines()[:6]))
            c.progress(f"{args.item} 統合: 競合のため todo に戻した")
            return 2
        n_done = sum(1 for x in q.get("items", []) if x.get("status") == "done") + 1
        full = args.full or n_done % FULL_EVERY == 0
        vargs = [sys.executable, str(c.root / "scripts" / "verify.py"), "--run", "current"] + ([] if full else ["--quick"])
        rc, vout = h.run(vargs, cwd=c.root, timeout=int(c.cfg["verify"].get("timeout_sec", 1800)) + 120)
        if rc != 0:
            git_ok(["reset", "-q", "--hard", pre], c.root)
            give_back(c, args.item)
            print(f"INTEGRATE: fail {args.item} verify -> todo（統合を取り消しました）")
            print(tail(vout))
            c.progress(f"{args.item} 統合: verify が失敗したため取り消して todo に戻した")
            return 1
        cases = select_cases(c, q, it, pre)
        st = "-"
        if cases:
            largs = [sys.executable, str(c.root / "scripts" / "ledger.py"), "--by", "conductor", "run",
                     "--cases", ",".join(x["id"] for x in cases), "--canary-first", "--stop-on-canary-fail"]
            rc, lout = h.run(largs, cwd=c.root, timeout=None)
            m = re.search(r"ledger run: pass=(\d+) fail=(\d+)", lout)
            st = f"{m.group(1)}/{int(m.group(1)) + int(m.group(2))}" if m else "?"
            if rc != 0:
                git_ok(["reset", "-q", "--hard", pre], c.root)
                give_back(c, args.item)
                print(f"INTEGRATE: fail {args.item} System Test {st} -> todo（統合を取り消しました）")
                print(tail(lout))
                c.progress(f"{args.item} 統合: System Test が失敗したため取り消して todo に戻した")
                return 1
            ledger_rel = h.mf(c.cfg, "ledger")
            rc, changed = h.git(["status", "--porcelain", "--", ledger_rel], c.root)
            if changed.strip():
                git_ok(["add", "--", ledger_rel], c.root)
                git_ok(["commit", "-q", "-m", f"ledger: {args.item} System Test {st} [{reqs}]"], c.root)
        q = c.queue()
        it = c.item(q, args.item)
        if it.get("worktree"):
            detach((c.root / it["worktree"]).resolve())
            it["worktree"] = None
        h.git(["branch", "-q", "-d", branch], c.root)
        c.rs.mark_status(it, "done")
        if args.summary is not None:
            it["summary"] = args.summary
        it["integrate_sec"] = round(time.time() - t0, 1)
        c.save(q)
    head = h.head_commit(c.root)
    print(f"INTEGRATE: pass {args.item} HEAD={head} verify={'full' if full else 'quick'} system-test={st} ({time.time() - t0:.0f}s)")
    c.progress(f"{args.item} 統合 {head}（verify {'full' if full else 'quick'}、System Test {st}）")
    return 0


# ---------------------------------------------------------------------- abandon / pool

def cmd_abandon(c: Ctx, args) -> int:
    give_back(c, args.item, "blocked" if args.blocked else "todo")
    status = "blocked" if args.blocked else "todo"
    if args.reason:
        c.progress(f"{args.item} -> {status}: {args.reason}")
    print(f"{args.item}: {status}（worktree を解放。ブランチは残します）")
    return 0


def cmd_pool(c: Ctx, args) -> int:
    q = c.queue()
    busy = {it["worktree"]: it["id"] for it in q.get("items", []) if it.get("status") == "doing" and it.get("worktree")}
    live = registered_worktrees(c.root)
    pool = sorted(p for p in c.pool_dir().glob(f"{c.rid}-w*") if p.is_dir()) if c.pool_dir().is_dir() else []
    removed = 0
    for p in pool:
        rel = c.rel(p)
        owner = busy.get(rel)
        if args.prune and not owner and os.path.normcase(str(p.resolve())) in live:
            rc, out = h.git(["worktree", "remove", "--force", str(p)], c.root)
            removed += rc == 0
            print(f"{'REMOVED' if rc == 0 else 'KEEP   '} {rel}{'' if rc == 0 else ' ' + out.strip()[:120]}")
        else:
            print(f"{'BUSY   ' if owner else 'IDLE   '} {rel}{' ' + owner if owner else ''}")
    if args.prune:
        h.git(["worktree", "prune"], c.root)
    print(f"pool: {len(pool)} worktrees, busy={len(busy)}{f', removed={removed}' if args.prune else ''}")
    return 0


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("item")
    m = sub.add_parser("merge")
    m.add_argument("item")
    m.add_argument("--full", action="store_true", help="verify の slow なコマンドも実行する")
    m.add_argument("--summary", default=None, help="変えた共通部品・契約と影響する要求 ID（次の implementer に渡す）")
    a = sub.add_parser("abandon")
    a.add_argument("item")
    a.add_argument("--blocked", action="store_true")
    a.add_argument("--reason", default="")
    pl = sub.add_parser("pool")
    pl.add_argument("--prune", action="store_true")
    args = ap.parse_args(argv)
    c = Ctx(args.root)
    return {"prepare": cmd_prepare, "merge": cmd_merge, "abandon": cmd_abandon, "pool": cmd_pool}[args.cmd](c, args)


if __name__ == "__main__":
    sys.exit(main())
