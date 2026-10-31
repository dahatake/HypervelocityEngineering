#!/usr/bin/env python3
"""perf-report.py - where did the time of EABK runs go? (reads work/runs/<run-id>/ of one or more repos)

Usage:
  python scripts/perf-report.py [--root DIR ...] [--glob 'C:/GitHub/*'] [--format md|json] [--out FILE]

Sources per run (all written by the toolkit): meta.json, queue.json, results.json (System Test runs),
subagents.jsonl (task call seconds), logs/verify-<stamp>-<step>.log (verify invocations).
Findings: wall vs. work time, System Test re-runs (same case + same commit, pass repeated), serial
cost of failing cases, verify repeats, retry/blocked items, sub-agent time by agent.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def load(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def jsonl(p: Path):
    out = []
    if p.exists():
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    return out


def ts(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def activity_gaps(rd: Path, meta: dict, min_gap_min: float = 20.0):
    """Stretches with no file written under the run directory (logs, results, evidence). Gaps this long are
    usually the machine asleep / the host app suspended / an agent waiting on a hung process, not work."""
    times = sorted(f.stat().st_mtime for f in rd.rglob("*") if f.is_file())
    a, b = ts(meta.get("started_at")), ts(meta.get("finished_at"))
    if a:
        times.insert(0, a.timestamp())
    if b:
        times.append(b.timestamp())
    out = []
    for x, y in zip(times, times[1:]):
        if (y - x) / 60 >= min_gap_min:
            out.append((datetime.fromtimestamp(x).strftime("%m-%d %H:%M"), datetime.fromtimestamp(y).strftime("%m-%d %H:%M"),
                        round((y - x) / 60, 1)))
    return out


def analyze_run(repo: str, rd: Path) -> dict:
    meta = load(rd / "meta.json", {}) or {}
    queue = (load(rd / "queue.json", {}) or {}).get("items", [])
    res = load(rd / "results.json", {}) or {}
    runs = res.get("runs", []) if isinstance(res, dict) else []
    subs = jsonl(rd / "subagents.jsonl")
    a, b = ts(meta.get("started_at")), ts(meta.get("finished_at"))
    wall = (b - a).total_seconds() if a and b else None

    seen = defaultdict(list)
    for r in runs:
        seen[r.get("case")].append(r)
    total_t = sum(float(r.get("seconds") or 0) for r in runs)
    wasted_pass = 0.0   # a case that already passed at the same commit and was run again
    fail_t = 0.0
    redundant_runs = 0
    for case, lst in seen.items():
        passed_commit = set()
        for r in lst:
            sec = float(r.get("seconds") or 0)
            if r.get("status") != "pass":
                fail_t += sec
            if r.get("status") == "pass":
                if r.get("commit") in passed_commit:
                    wasted_pass += sec
                    redundant_runs += 1
                passed_commit.add(r.get("commit"))
    slow = sorted(runs, key=lambda r: -float(r.get("seconds") or 0))[:5]

    stamps = Counter()
    steps = defaultdict(int)
    last_mtime = {}
    for f in (rd / "logs").glob("verify-*.log") if (rd / "logs").exists() else []:
        m = re.match(r"verify-(\d{8}-\d{6})-(.+)\.log", f.name)
        if m:
            stamps[m.group(1)] += 1
            steps[m.group(2)] += 1
            last_mtime[m.group(1)] = max(last_mtime.get(m.group(1), 0), f.stat().st_mtime)
    # a verify invocation lasts from its stamp (taken at start) to the newest step log it wrote
    verify_sec = 0.0
    for stp, mt in last_mtime.items():
        try:
            verify_sec += max(0.0, mt - datetime.strptime(stp, "%Y%m%d-%H%M%S").timestamp())
        except ValueError:
            pass
    work = [float(i.get("work_sec") or 0) for i in queue]
    gaps = activity_gaps(rd, meta)
    integ = [float(i.get("integrate_sec") or 0) for i in queue]
    by_agent = defaultdict(lambda: [0, 0.0])
    for s in subs:
        by_agent[s.get("agent")][0] += 1
        by_agent[s.get("agent")][1] += float(s.get("seconds") or 0)
    return {
        "repo": repo, "run": rd.name, "wall_h": round(wall / 3600, 2) if wall else None,
        "budget_h": (meta.get("options") or {}).get("max_hours"),
        "items": len(queue), "attempts_gt1": sum(1 for i in queue if (i.get("attempts") or 0) > 1),
        "blocked": sum(1 for i in queue if i.get("status") == "blocked"),
        "work_h": round(sum(work) / 3600, 2), "integrate_min": round(sum(integ) / 60, 1),
        "avg_item_min": round(sum(work) / len(work) / 60, 1) if work else None,
        "st_runs": len(runs), "st_cases": len(seen), "st_total_min": round(total_t / 60, 1),
        "st_fail_min": round(fail_t / 60, 1), "st_wasted_pass_min": round(wasted_pass / 60, 1),
        "st_redundant_runs": redundant_runs,
        "st_max_reruns": max((len(v) for v in seen.values()), default=0),
        "st_slowest": [(r.get("case"), r.get("seconds"), r.get("status")) for r in slow],
        "verify_invocations": len(stamps), "verify_steps": dict(steps), "verify_min": round(verify_sec / 60, 1),
        "item_detail": [{"id": i.get("id"), "attempts": i.get("attempts"), "status": i.get("status"),
                         "work_min": round(float(i.get("work_sec") or 0) / 60, 1),
                         "integrate_min": round(float(i.get("integrate_sec") or 0) / 60, 1)} for i in queue],
        "stage_min": {k: round((ts(v["done"]) - ts(v["start"])).total_seconds() / 60, 1)
                      for k, v in (meta.get("stage_times") or {}).items()
                      if isinstance(v, dict) and ts(v.get("start")) and ts(v.get("done"))},
        "idle_gaps": gaps, "idle_gap_h": round(sum(g[2] for g in gaps) / 60, 2),
        "stop_blocks": meta.get("stop_blocks"), "land_blocks": meta.get("land_blocks"),
        "subagents": {k: {"calls": v[0], "min": round(v[1] / 60, 1)} for k, v in by_agent.items()},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", default=[])
    ap.add_argument("--glob", action="append", default=[])
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    roots = [Path(r) for r in a.root]
    for g in a.glob:
        roots += [Path(x) for x in glob.glob(g)]
    if not roots:
        roots = [Path.cwd()]
    rows = []
    for root in roots:
        base = root / "work" / "runs"
        if base.is_dir():
            for rd in sorted(base.iterdir()):
                if rd.is_dir() and (rd / "meta.json").exists():
                    rows.append(analyze_run(root.name, rd))
    if a.format == "json":
        text = json.dumps(rows, ensure_ascii=False, indent=1)
    else:
        L = ["| repo | run | wall h | budget h | items | retry | work h | st runs/cases | st min | st fail min | st wasted-pass min | verify n |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            L.append(f"| {r['repo']} | {r['run']} | {r['wall_h']} | {r['budget_h']} | {r['items']} | {r['attempts_gt1']} | {r['work_h']} | "
                     f"{r['st_runs']}/{r['st_cases']} | {r['st_total_min']} | {r['st_fail_min']} | {r['st_wasted_pass_min']} | {r['verify_invocations']} |")
        text = "\n".join(L)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
