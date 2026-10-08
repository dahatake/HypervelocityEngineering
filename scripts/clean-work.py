#!/usr/bin/env python3
"""clean-work.py - delete expired temporary files under /work (plan §7.6, G-6).

Usage:
  python scripts/clean-work.py [--days 14] [--dry-run]

Deletes /work/runs/<run-id>/ whose newest file is older than the retention period, except
  - the run named in /work/current-run.txt, and
  - runs whose integration / work branches are not yet merged into the base branch.
Then runs `git worktree prune` and deletes merged `work/<run-id>/<item>` branches whose worktree is gone.
Only paths under /work are ever deleted.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import List, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402


def newest_mtime(p: Path) -> float:
    m = p.stat().st_mtime
    for f in p.rglob("*"):
        try:
            m = max(m, f.stat().st_mtime)
        except OSError:
            pass
    return m


def branches(root: Path, pattern: str, merged_into: str = "") -> Set[str]:
    args = ["branch", "--format=%(refname:short)", "--list", pattern]
    if merged_into:
        args.insert(1, f"--merged={merged_into}")
    rc, out = h.git(args, root)
    return set(out.split()) if rc == 0 else set()


def run_branches(root: Path, cfg: dict, run_id: str) -> List[str]:
    names = set()
    meta = h.load_meta(root, cfg, run_id)
    if meta.get("integration_branch"):
        names.add(meta["integration_branch"])
    for it in h.load_queue(root, cfg, run_id).get("items", []):
        if it.get("branch"):
            names.add(it["branch"])
    names |= branches(root, f"work/{run_id}/*")
    return sorted(names)


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=float, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
    days = args.days if args.days is not None else cfg["work"]["retention_days"]
    wdir = h.work_dir(root, cfg)
    runs = wdir / "runs"
    keep_current = h.current_run(root, cfg)
    base = cfg.get("base_branch", "main")
    has_base = h.ref_exists(root, base)
    merged = branches(root, "*", base) if has_base else set()
    cutoff = time.time() - days * 86400
    deleted, kept = 0, 0
    if runs.is_dir():
        for rd in sorted(p for p in runs.iterdir() if p.is_dir()):
            rid = rd.name
            reason = ""
            if rid == keep_current:
                reason = "current-run"
            elif newest_mtime(rd) >= cutoff:
                reason = "保持期間内"
            else:
                unmerged = [b for b in run_branches(root, cfg, rid) if h.ref_exists(root, b) and b not in merged]
                if unmerged:
                    reason = "未取り込みのブランチ: " + ", ".join(unmerged[:3])
            if reason:
                kept += 1
                print(f"KEEP   {rd.relative_to(root).as_posix()}  ({reason})")
                continue
            print(f"DELETE {rd.relative_to(root).as_posix()}")
            if not args.dry_run:
                shutil.rmtree(rd, ignore_errors=True)
            deleted += 1
    if not args.dry_run:
        h.git(["worktree", "prune"], root)
        rc, out = h.git(["worktree", "list", "--porcelain"], root)
        live = {l.split(" ", 1)[1] for l in out.splitlines() if l.startswith("branch ")} if rc == 0 else set()
        for b in sorted(branches(root, "work/*/*")):
            if b in merged and f"refs/heads/{b}" not in live:
                rc2, _ = h.git(["branch", "-d", b], root)
                if rc2 == 0:
                    print(f"BRANCH-DELETED {b}")
    print(f"clean-work: deleted={deleted} kept={kept} retention_days={days}{' (dry-run)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
