#!/usr/bin/env python3
"""ledger.py - the only writer of tests/system/ledger.json (plan §7.1, §7.6, CHK-10..12).

Usage:
  python scripts/ledger.py summary
  python scripts/ledger.py add --req FR-012 --ac AC-031 --title "..." --layer e2e --command "npx playwright test ..." [--canary] [--reason "..."]
  python scripts/ledger.py update ID [--command ...] [--title ...] [--ac ...] [--req ...] [--canary true|false] --reason "..."
  python scripts/ledger.py block ID --reason "..."          # never delete a case; block it with a reason
  python scripts/ledger.py set ID pass|fail|blocked|not_run [--evidence PATH] [--reason ...]
  python scripts/ledger.py digests [--update]               # ac_digests (PARAM expanded AC text)
  python scripts/ledger.py run [--cases E2E-001,IT-002 | --select changed|failed|all] [--base REF]
                               [--canary-first] [--max-minutes N] [--no-record] [--results PATH]

Rules enforced here: cases are never deleted; command/ac_ids changes require --reason (history);
status pass/fail is recorded only from an executed command's exit code.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hvelib as h  # noqa: E402

LAYERS = ("e2e", "api", "contract", "data", "nonfunctional", "ai_eval")
STATUSES = ("not_run", "pass", "fail", "blocked")


def split_ids(v: Optional[str]) -> List[str]:
    return [x.strip() for x in re.split(r"[,\s]+", v or "") if x.strip()]


def history(case: dict, change: str, reason: str, by: str) -> None:
    case.setdefault("history", []).append({"at": h.now_iso(), "by": by, "change": change, "reason": reason})


def find(data: dict, cid: str) -> dict:
    for c in data["cases"]:
        if c.get("id") == cid:
            return c
    raise SystemExit(f"ERROR ledger: ケース {cid} がありません")


def cmd_summary(args, root, cfg) -> int:
    data = h.load_ledger(root, cfg)
    counts = {s: 0 for s in STATUSES}
    for c in data["cases"]:
        counts[c.get("status", "not_run")] = counts.get(c.get("status", "not_run"), 0) + 1
    print(f"HEAD {h.head_commit(root) or '-'} | 台帳 pass={counts['pass']} fail={counts['fail']} blocked={counts['blocked']} not_run={counts['not_run']}")
    if args.verbose:
        for c in data["cases"]:
            print(f"{c['id']}\t{','.join(c.get('requirement_ids', []))}\t{','.join(c.get('ac_ids', []))}\t{c.get('status')}\t{'canary' if c.get('canary') else ''}\t{c.get('title', '')}")
    return 0


def cmd_add(args, root, cfg) -> int:
    if args.layer not in LAYERS:
        raise SystemExit(f"ERROR ledger: layer は {', '.join(LAYERS)} のどれかです")
    doc = h.parse_requirements(root, cfg)
    reqs, acs = split_ids(args.req), split_ids(args.ac)
    if not reqs or not acs:
        raise SystemExit("ERROR ledger: --req と --ac は必須です")
    for a in acs:
        if a not in doc.acs:
            raise SystemExit(f"ERROR ledger: {a} が要求定義書にありません")
    for r in reqs:
        if r not in doc.requirements:
            raise SystemExit(f"ERROR ledger: {r} が要求定義書にありません")
    kind = "E2E" if args.layer == "e2e" else "IT"
    cid = h.load_script("next-id").allocate(root, cfg, kind, 1, args.title[:40], False)[0]
    data = h.load_ledger(root, cfg)
    case = {
        "id": cid, "requirement_ids": reqs, "ac_ids": acs, "title": args.title, "layer": args.layer,
        "command": args.command, "canary": bool(args.canary), "status": "not_run",
        "last_commit": None, "last_run_at": None, "evidence": None, "history": [],
    }
    history(case, "追加", args.reason or "受入基準からケースを作成", args.by)
    data["cases"].append(case)
    for a in acs:
        data["ac_digests"][a] = h.ac_digest(doc.acs[a], doc.params)
    h.save_ledger(root, cfg, data)
    print(cid)
    return 0


def cmd_update(args, root, cfg) -> int:
    if not args.reason:
        raise SystemExit("ERROR ledger: 変更には --reason が必要です（history に残します）")
    data = h.load_ledger(root, cfg)
    c = find(data, args.id)
    changes = []
    for key, val in (("command", args.command), ("title", args.title)):
        if val is not None and c.get(key) != val:
            changes.append(f"{key}: {c.get(key)!r} -> {val!r}")
            c[key] = val
    if args.ac is not None:
        new = split_ids(args.ac)
        if new != c.get("ac_ids"):
            changes.append(f"ac_ids: {c.get('ac_ids')} -> {new}")
            c["ac_ids"] = new
    if args.req is not None:
        new = split_ids(args.req)
        if new != c.get("requirement_ids"):
            changes.append(f"requirement_ids: {c.get('requirement_ids')} -> {new}")
            c["requirement_ids"] = new
    if args.canary is not None:
        val = args.canary.lower() in ("true", "1", "yes")
        if val != c.get("canary"):
            changes.append(f"canary: {c.get('canary')} -> {val}")
            c["canary"] = val
    if not changes:
        print("変更はありません")
        return 0
    c["status"] = "not_run"
    history(c, "; ".join(changes), args.reason, args.by)
    doc = h.parse_requirements(root, cfg)
    for a in c.get("ac_ids", []):
        if a in doc.acs:
            data["ac_digests"][a] = h.ac_digest(doc.acs[a], doc.params)
    h.save_ledger(root, cfg, data)
    print(f"{args.id}: " + "; ".join(changes))
    return 0


def cmd_block(args, root, cfg) -> int:
    if not args.reason:
        raise SystemExit("ERROR ledger: --reason が必要です")
    data = h.load_ledger(root, cfg)
    c = find(data, args.id)
    c["status"] = "blocked"
    history(c, "blocked", args.reason, args.by)
    h.save_ledger(root, cfg, data)
    print(f"{args.id}: blocked")
    return 0


def cmd_set(args, root, cfg) -> int:
    if args.status not in STATUSES:
        raise SystemExit(f"ERROR ledger: status は {', '.join(STATUSES)} のどれかです")
    if args.status in ("pass", "fail") and not args.evidence:
        raise SystemExit("ERROR ledger: pass/fail は実行結果でだけ付けます。`ledger.py run` を使うか、--evidence に実行ログのパスを指定します")
    if args.status == "blocked" and not args.reason:
        raise SystemExit("ERROR ledger: blocked には --reason が必要です")
    data = h.load_ledger(root, cfg)
    c = find(data, args.id)
    c["status"] = args.status
    if args.status in ("pass", "fail"):
        c["last_commit"] = h.head_commit(root)
        c["last_run_at"] = h.now_iso()
        c["evidence"] = args.evidence
    if args.reason:
        history(c, f"status -> {args.status}", args.reason, args.by)
    h.save_ledger(root, cfg, data)
    print(f"{args.id}: {args.status}")
    return 0


def cmd_digests(args, root, cfg) -> int:
    data = h.load_ledger(root, cfg)
    doc = h.parse_requirements(root, cfg)
    referenced = sorted({a for c in data["cases"] for a in c.get("ac_ids", [])})
    diff = 0
    for a in referenced:
        ac = doc.acs.get(a)
        cur = h.ac_digest(ac, doc.params) if ac else None
        old = data["ac_digests"].get(a)
        if cur != old:
            diff += 1
            print(f"{a}\t{old or '-'} -> {cur or 'NOT_FOUND'}")
            if args.update and cur:
                data["ac_digests"][a] = cur
    for a in list(data["ac_digests"]):
        if a not in referenced and args.update:
            del data["ac_digests"][a]
    if args.update:
        h.save_ledger(root, cfg, data)
    print(f"ledger digests: changed={diff}{' (updated)' if args.update else ''}")
    return 0 if (diff == 0 or args.update) else 1


def changed_files(root: Path, base: Optional[str]) -> List[str]:
    if not base:
        return []
    rc, out = h.git(["diff", "--name-only", base], root)
    files = out.splitlines() if rc == 0 else []
    rc2, out2 = h.git(["ls-files", "-o", "--exclude-standard"], root)
    if rc2 == 0:
        files += out2.splitlines()
    return sorted(set(f for f in files if f))


def select_cases(root: Path, cfg: dict, data: dict, mode: str, base: Optional[str]) -> List[dict]:
    cases = data["cases"]
    if mode == "all":
        return [c for c in cases if c.get("status") != "blocked"]
    if mode == "failed":
        return [c for c in cases if c.get("status") in ("fail", "not_run")]
    files = changed_files(root, base)
    ids = set()
    for f in files:
        p = root / f
        if p.is_file() and p.stat().st_size < 2_000_000:
            try:
                ids.update(h.CODE_ID_RE.findall(p.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                pass
    out = []
    for c in cases:
        if c.get("status") == "blocked":
            continue
        if c.get("status") in ("fail", "not_run"):
            out.append(c)
            continue
        if ids & set(c.get("requirement_ids", []) + c.get("ac_ids", [])):
            out.append(c)
            continue
        if any(f and f in (c.get("command") or "") for f in files):
            out.append(c)
    return out


def cmd_run(args, root, cfg) -> int:
    data = h.load_ledger(root, cfg)
    if args.cases:
        want = split_ids(args.cases)
        sel = [find(data, cid) for cid in want]
    else:
        base = args.base or h.default_base(root, cfg)
        sel = select_cases(root, cfg, data, args.select, base)
    sel = [c for c in sel if c.get("status") != "blocked" or args.cases]
    if args.canary_first:
        sel.sort(key=lambda c: not c.get("canary"))
    rid = h.current_run(h.conductor_root(root, cfg), cfg) or ("adhoc-" + h.new_run_id())
    results_path = Path(args.results) if args.results else h.run_dir(h.conductor_root(root, cfg), cfg, rid) / "results.json"
    logs_dir = results_path.parent / "logs" / "system-test"
    logs_dir.mkdir(parents=True, exist_ok=True)
    results = h.read_json(results_path, default={"runs": []}) or {"runs": []}
    deadline = time.time() + args.max_minutes * 60 if args.max_minutes else None
    head = h.head_commit(root)
    summary = {"pass": 0, "fail": 0, "skipped": 0}
    lines_out = []
    stop_reason = ""
    for c in sel:
        if deadline and time.time() > deadline:
            summary["skipped"] += 1
            stop_reason = "時間予算で中止"
            continue
        if not c.get("command"):
            continue
        t0 = time.time()
        log = logs_dir / f"{c['id']}-{h.new_run_id()}.log"
        try:
            proc = subprocess.run(c["command"], cwd=str(root), shell=True, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=args.case_timeout)
            rc, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired:
            rc, out = 124, f"TIMEOUT after {args.case_timeout}s"
        dur = round(time.time() - t0, 1)
        log.write_text(out, encoding="utf-8")
        status = "pass" if rc == 0 else "fail"
        summary[status] += 1
        rel_log = log.relative_to(h.conductor_root(root, cfg)).as_posix() if str(log).startswith(str(h.conductor_root(root, cfg))) else str(log)
        lines_out.append(f"{c['id']} {','.join(c.get('requirement_ids', []))} {status} {dur} {rel_log}")
        results["runs"].append({"case": c["id"], "status": status, "exit_code": rc, "seconds": dur, "commit": head, "at": h.now_iso(), "log": rel_log})
        if not args.no_record:
            c["status"] = status
            c["last_commit"] = head
            c["last_run_at"] = h.now_iso()
            c["evidence"] = rel_log
        if c.get("canary") and status == "fail" and args.stop_on_canary_fail:
            stop_reason = "canary 失敗で中止"
            break
    h.write_json(results_path, results)
    if not args.no_record:
        h.save_ledger(root, cfg, data)
    print("\n".join(lines_out))
    result = stop_reason or ("全件 pass" if summary["fail"] == 0 else "fail あり")
    print(f"ledger run: pass={summary['pass']} fail={summary['fail']} skipped={summary['skipped']} results={results_path} 結果: {result}")
    return 0 if summary["fail"] == 0 and not stop_reason else 1


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    ap.add_argument("--by", default="script", help="history に残す実行者（例: test-designer, conductor）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summary")
    s.add_argument("-v", "--verbose", action="store_true")
    a = sub.add_parser("add")
    a.add_argument("--req", required=True)
    a.add_argument("--ac", required=True)
    a.add_argument("--title", required=True)
    a.add_argument("--layer", required=True)
    a.add_argument("--command", required=True)
    a.add_argument("--canary", action="store_true")
    a.add_argument("--reason", default="")
    u = sub.add_parser("update")
    u.add_argument("id")
    u.add_argument("--command")
    u.add_argument("--title")
    u.add_argument("--ac")
    u.add_argument("--req")
    u.add_argument("--canary")
    u.add_argument("--reason", required=False)
    b = sub.add_parser("block")
    b.add_argument("id")
    b.add_argument("--reason", required=False)
    st = sub.add_parser("set")
    st.add_argument("id")
    st.add_argument("status")
    st.add_argument("--evidence")
    st.add_argument("--reason")
    d = sub.add_parser("digests")
    d.add_argument("--update", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--cases")
    r.add_argument("--select", default="changed", choices=("changed", "failed", "all"))
    r.add_argument("--base")
    r.add_argument("--canary-first", action="store_true")
    r.add_argument("--stop-on-canary-fail", action="store_true")
    r.add_argument("--max-minutes", type=float, default=0)
    r.add_argument("--case-timeout", type=int, default=1800)
    r.add_argument("--no-record", action="store_true", help="台帳を書き換えない（作業役の worktree で使う）")
    r.add_argument("--results")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
    fn = {"summary": cmd_summary, "add": cmd_add, "update": cmd_update, "block": cmd_block,
          "set": cmd_set, "digests": cmd_digests, "run": cmd_run}[args.cmd]
    return fn(args, root, cfg)


if __name__ == "__main__":
    sys.exit(main())
