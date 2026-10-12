#!/usr/bin/env python3
"""next-impl.py - analyze which requirements to implement next (FR-1015).

Usage:
  python scripts/next-impl.py [--json] [--root DIR]

Reads the management data (requirements definition, catalog, system-test ledger and the
current run's queue) and prints a ranked table of the next implementation candidates, the
excluded requirements with the reason, and a requirement-ID list that can be passed to `scope`.
The command is read-only: it never writes to the target repository.

Candidate = approved, and either not started, or implemented but with no system test registered /
with a failing system test.  Ranking (deterministic): dependencies first, then priority
(MUST > SHOULD > MAY), then the number of other candidates that depend on it (descending), then
implemented before not-started, then requirement ID ascending.  Dependencies are the other
requirement IDs written in the requirement's 「関連する既存資産」 field ([ASSUMPTION]).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

sys.dont_write_bytecode = True  # read-only: leave no __pycache__ in the target repository
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402

PRIORITY_RANK = {"MUST": 0, "SHOULD": 1, "MAY": 2}
# implementation states (same classification rules as FR-1014)
S_NOT_STARTED = "未着手"
S_NO_TEST = "実装登録済み・試験未登録"
S_TEST_FAIL = "実装登録済み・試験未合格"
S_PASS = "試験 pass 済み"
S_NO_SYSTEM = "実装登録済み・system 試験対象外"
CANDIDATE_STATES = (S_NOT_STARTED, S_NO_TEST, S_TEST_FAIL)


def natural_key(id_: str):
    m = re.match(r"^(.*?)-(\d+)$", id_)
    return (m.group(1), int(m.group(2))) if m else (id_, 0)


def classify(root: Path, req, doc, rows, ledger) -> str:
    """Implementation state of one requirement (rules shared with FR-1014)."""
    row = rows.get(req.id)
    impl = False
    if row is not None:
        impl = any((root / p).exists() for p in h.split_paths(h.catalog_cell(row, "実装ファイル")))
    if not impl:
        return S_NOT_STARTED
    cases = [c for c in ledger.get("cases", []) if req.id in (c.get("requirement_ids") or [])]
    if cases:  # same precedence as FR-1014: ledger cases decide first
        return S_PASS if all((c.get("status") or "not_run") == "pass" for c in cases) else S_TEST_FAIL
    has_system = any(doc.acs[a].level == "system" for a in req.acs if a in doc.acs)
    return S_NO_TEST if has_system else S_NO_SYSTEM


def stopped(req, doc) -> bool:
    """All ACs are stopped (BLOCKED by an open question / TBD / conflict)."""
    acs = [doc.acs[a] for a in req.acs if a in doc.acs]
    return bool(acs) and all(a.blocked for a in acs)


def dependencies(req, doc) -> List[str]:
    deps = []
    for m in h.REQ_ID_RE.finditer(req.fields.get("関連する既存資産", "")):
        d = m.group(1)
        if d != req.id and d in doc.requirements and d not in deps:
            deps.append(d)
    return deps


def run_queue(root: Path, cfg: dict):
    """(doing ids, done ids) from the current run's queue; empty without a current run."""
    croot = h.conductor_root(root, cfg)
    rid = h.current_run(croot, cfg)
    if not rid or not (h.run_dir(croot, cfg, rid) / "meta.json").exists():
        return set(), set()
    doing: Set[str] = set()
    done: Set[str] = set()
    for it in h.load_queue(croot, cfg, rid).get("items", []):
        target = doing if it.get("status") == "doing" else done if it.get("status") == "done" else None
        if target is not None:
            target.update(it.get("requirement_ids") or [])
    return doing, done


def find_cycle_members(nodes: List[str], deps: Dict[str, List[str]]) -> Set[str]:
    members: Set[str] = set()
    for n in nodes:
        seen: Set[str] = set()
        stack = list(deps.get(n, []))
        while stack:
            x = stack.pop()
            if x == n:
                members.add(n)
                break
            if x in seen:
                continue
            seen.add(x)
            stack.extend(deps.get(x, []))
    return members


def analyze(root: Path, cfg: dict) -> dict:
    doc = h.parse_requirements(root, cfg)
    _, cat_rows, _ = h.parse_catalog(root, cfg)
    rows = h.catalog_req_rows(cat_rows)
    ledger = h.load_ledger(root, cfg)
    doing, done = run_queue(root, cfg)
    states = {rid: classify(root, r, doc, rows, ledger) for rid, r in doc.requirements.items()}
    excluded: List[dict] = []
    cands: Dict[str, str] = {}  # id -> state

    def exclude(rid, reason, detail=""):
        r = doc.requirements[rid]
        excluded.append({"id": rid, "title": r.title, "reason": reason, "detail": detail})

    for rid in sorted(doc.requirements, key=natural_key):
        r = doc.requirements[rid]
        st = states[rid]
        if r.state != "承認済み":
            exclude(rid, "未承認", r.state or "決定状態なし")
        elif rid in doing:
            exclude(rid, "実行中", "現在の run の queue で doing")
        elif rid in done:
            exclude(rid, "完了済み", "現在の run の queue で done")
        elif st in (S_PASS, S_NO_SYSTEM):
            exclude(rid, "完了済み", st)
        elif stopped(r, doc):
            exclude(rid, "BLOCKED", "AC がすべて停止中")
        else:
            cands[rid] = st
    # dependency-based exclusion, repeated until nothing changes
    changed = True
    while changed:
        changed = False
        for rid in sorted(cands, key=natural_key):
            for d in dependencies(doc.requirements[rid], doc):
                dr = doc.requirements[d]
                if dr.state != "承認済み":
                    exclude(rid, "依存先が未承認", f"依存先 {d}（{dr.state}）")
                elif d not in cands and d not in done and states[d] not in (S_PASS, S_NO_SYSTEM):
                    exclude(rid, "依存先未完了", f"依存先 {d}（{'実行中' if d in doing else '除外中・未完了'}）")
                else:
                    continue
                del cands[rid]
                changed = True
                break
    ids = sorted(cands, key=natural_key)
    deps = {i: [d for d in dependencies(doc.requirements[i], doc) if d in cands] for i in ids}
    cycle = find_cycle_members(ids, deps)
    warnings: List[str] = []
    ranked: List[str]
    count = {i: sum(1 for j in ids if i in deps[j]) for i in ids}

    def key(i):
        r = doc.requirements[i]
        return (PRIORITY_RANK.get(r.priority, 3), -count[i], 0 if cands[i] != S_NOT_STARTED else 1, natural_key(i))

    if cycle:
        warnings.append("依存が循環しています: " + ", ".join(sorted(cycle, key=natural_key))
                        + "（候補の並びは要求 ID の昇順にしました）")
        ranked = ids
    else:
        ranked, placed = [], set()
        while len(ranked) < len(ids):
            ready = [i for i in ids if i not in placed and all(d in placed for d in deps[i])]
            nxt = min(ready, key=key)
            ranked.append(nxt)
            placed.add(nxt)
    table = []
    for n, i in enumerate(ranked, 1):
        r = doc.requirements[i]
        basis = [f"優先度 {r.priority or '未設定'}", f"依存される数 {count[i]}", f"状態 {cands[i]}"]
        if deps[i]:
            basis.append("依存先 " + "・".join(deps[i]))
        table.append({"rank": n, "id": i, "title": r.title, "priority": r.priority or "-",
                      "state": cands[i], "basis": "、".join(basis)})
    return {"candidates": table, "excluded": excluded, "warnings": warnings,
            "scope": ranked, "states": states}


def rank_table_md(res: dict) -> str:
    lines = ["| 順位 | 要求 ID | 題名 | 優先度 | 実装状態 | 選定の根拠 |", "|---|---|---|---|---|---|"]
    for c in res["candidates"]:
        lines.append(f"| {c['rank']} | {c['id']} | {c['title']} | {c['priority']} | {c['state']} | {c['basis']} |")
    if not res["candidates"]:
        lines.append("| - | （候補なし） | - | - | - | - |")
    return "\n".join(lines)


def excluded_md(res: dict) -> str:
    lines = ["| 要求 ID | 題名 | 除外の理由 | 詳細 |", "|---|---|---|---|"]
    for e in res["excluded"]:
        lines.append(f"| {e['id']} | {e['title']} | {e['reason']} | {e['detail']} |")
    if not res["excluded"]:
        lines.append("| - | （除外なし） | - | - |")
    return "\n".join(lines)


def render(res: dict) -> str:
    out = ["# 次に実装すべき要求（分析）", "", "## 順位表", "", rank_table_md(res), "",
           "## 除外一覧", "", excluded_md(res), ""]
    if res["warnings"]:
        out += ["## 警告", ""] + [f"- WARN {w}" for w in res["warnings"]] + [""]
    out += ["## scope に渡す要求 ID", "", "scope: " + ", ".join(res["scope"]) if res["scope"] else "（候補なし）"]
    return "\n".join(out)


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description="次に実装すべき要求を分析する（読み取り専用）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
    res = analyze(root, cfg)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(render(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
