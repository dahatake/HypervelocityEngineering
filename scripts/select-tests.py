#!/usr/bin/env python3
"""select-tests.py - choose the tests to run from changed files and requirement IDs (plan §7.3, T-7).

Usage:
  python scripts/select-tests.py [--base REF] [--req FR-012,AC-031] [--json]

Output (text):
  REQ   <requirement / AC IDs touched by the change>
  CASE  <ledger case id>  <reason>        (system tests: canary, not_run/fail, ID or file match)
  TEST  <test file>                         (unit / integration test files mentioning the IDs or changed together)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hvelib as h  # noqa: E402


def changed(root: Path, base) -> List[str]:
    files: List[str] = []
    if base:
        rc, out = h.git(["diff", "--name-only", base], root)
        if rc == 0:
            files += out.splitlines()
    rc, out = h.git(["diff", "--name-only", "HEAD"], root)
    if rc == 0:
        files += out.splitlines()
    rc, out = h.git(["ls-files", "-o", "--exclude-standard"], root)
    if rc == 0:
        files += out.splitlines()
    return sorted(set(f for f in files if f and not f.startswith(h.DEFAULT_CONFIG["work"]["dir"] + "/")))


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=None)
    ap.add_argument("--req", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
    base = args.base or h.default_base(root, cfg)
    files = changed(root, base)
    doc = h.parse_requirements(root, cfg)

    ids: Set[str] = set(x for x in re.split(r"[,\s]+", args.req) if x)
    for f in files:
        p = root / f
        if h.glob_match(f, h.SPECKIT_PATHS):
            continue
        if p.is_file() and p.stat().st_size < 2_000_000:
            ids.update(h.CODE_ID_RE.findall(p.read_bytes().decode("utf-8", "replace")))
    # expand: requirement -> its ACs, AC -> its requirement
    for i in list(ids):
        r = doc.requirements.get(i)
        if r:
            ids.update(r.acs)
        a = doc.acs.get(i)
        if a and a.requirement:
            ids.add(a.requirement)

    ledger = h.load_ledger(root, cfg)
    cases: Dict[str, str] = {}
    for c in ledger.get("cases", []):
        if c.get("status") == "blocked":
            continue
        cid = c.get("id")
        if c.get("canary"):
            cases[cid] = "canary"
        elif c.get("status") in ("not_run", "fail"):
            cases[cid] = c.get("status")
        elif ids & set(c.get("requirement_ids", []) + c.get("ac_ids", [])):
            cases[cid] = "id-match"
        elif any(f in (c.get("command") or "") for f in files):
            cases[cid] = "file-match"

    rx = re.compile(cfg["checks"]["test_path_pattern"])
    tests: List[str] = []
    for f in h.tracked_files(root):
        if not rx.search(f) or f.startswith("tests/system/") or h.glob_match(f, cfg["checks"]["id_scan_exclude"]):
            continue
        if f in files:
            tests.append(f)
            continue
        p = root / f
        try:
            if p.stat().st_size > 2_000_000:
                continue
            found = set(h.CODE_ID_RE.findall(p.read_bytes().decode("utf-8", "replace")))
        except OSError:
            continue
        if found & ids:
            tests.append(f)

    if args.json:
        print(json.dumps({"base": base, "changed_files": files, "ids": sorted(ids), "cases": cases, "tests": tests}, ensure_ascii=False, indent=2))
        return 0
    print(f"BASE  {base or '-'}  changed_files={len(files)}")
    print("REQ   " + (" ".join(sorted(ids)) or "-"))
    for cid, why in cases.items():
        print(f"CASE  {cid}  {why}")
    for t in tests:
        print(f"TEST  {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
