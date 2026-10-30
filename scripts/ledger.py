#!/usr/bin/env python3
"""ledger.py - the only writer of tests/system/ledger.json (plan §7.1, §7.6, CHK-10..12).

Usage:
  python scripts/ledger.py summary
  python scripts/ledger.py add --req FR-012 --ac AC-031 --title "..." --layer e2e --command "npx playwright test ..." [--canary] [--reason "..."]
                               # 同じ AC の有効なケースがあれば拒否（update で拡張する。例外は --new-case-reason "理由"）
  python scripts/ledger.py update ID [--command ...] [--title ...] [--ac ...] [--req ...] [--canary true|false] --reason "..."
  python scripts/ledger.py block ID --reason "..."          # never delete a case; block it with a reason
  python scripts/ledger.py set ID pass|fail|blocked|not_run [--evidence PATH] [--reason ...]
  python scripts/ledger.py digests [--update]               # ac_digests (PARAM expanded AC text)
  python scripts/ledger.py repair [--apply]                 # align with the requirements definition (rdfix.py)
  python scripts/ledger.py preflight [--cases ID,..] [--all]  # pytest 'collect-only': syntax errors / 0 tests selected (test-designer, before implementation)
  python scripts/ledger.py run [--cases E2E-001,IT-002 | --select changed|failed|all] [--base REF]
                               [--canary-first] [--max-minutes N] [--no-record] [--results PATH]

Rules enforced here: cases are never deleted; command/ac_ids changes require --reason (history);
status pass/fail is recorded only from an executed command's exit code.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402

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
    data = h.load_ledger(root, cfg)
    # 似た System Test を増やさない: 同じ AC を保証する有効なケースがあれば、新規に作らず既存を拡張する
    covering = {}
    for c in data["cases"]:
        if c.get("status") == "blocked":
            continue
        for a in acs:
            if a in c.get("ac_ids", []):
                covering.setdefault(a, []).append(c["id"])
    if covering and not args.new_case_reason:
        hits = "、".join(f"{a}: {'、'.join(ids)}" for a, ids in covering.items())
        first = next(iter(covering.values()))[0]
        raise SystemExit(
            f"ERROR ledger: 同じ受入基準を保証する有効なケースがあります（{hits}）。新しいケースを足さず、"
            f"`python scripts/ledger.py update {first} --command ... --ac ... --reason \"...\"` で既存のケースを拡張します。"
            "層（e2e と api など）が違い、別のケースが本当に必要なときだけ --new-case-reason \"理由\" を付けます")
    cid = h.load_script("next-id").allocate(root, cfg, kind, 1, args.title[:40], False)[0]
    case = {
        "id": cid, "requirement_ids": reqs, "ac_ids": acs, "title": args.title, "layer": args.layer,
        "command": args.command, "canary": bool(args.canary), "status": "not_run",
        "last_commit": None, "last_run_at": None, "evidence": None, "history": [],
    }
    history(case, "追加", args.reason or "受入基準からケースを作成", args.by)
    if covering:
        history(case, "同じ AC の既存ケースと別に追加", args.new_case_reason, args.by)
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


CASE_DEFAULTS = {
    "requirement_ids": list, "ac_ids": list, "title": str, "layer": str, "command": str,
    "canary": lambda: False, "status": lambda: "not_run", "last_commit": lambda: None,
    "last_run_at": lambda: None, "evidence": lambda: None, "history": list,
}


def repair(root: Path, cfg: dict, doc, apply: bool, by: str = "rdfix") -> List[dict]:
    """Bring the ledger in line with the requirements definition (used by rdfix.py).

    Fixes only what follows mechanically from the requirements definition: missing fields,
    requirement_ids that no longer match the ACs, missing / orphan ac_digests. Anything that needs
    a test-designer's review (changed AC text, AC out of scope, unknown AC) is returned as MANUAL.
    Returns [{"kind": "FIX"|"MANUAL", "chk", "loc", "msg", "owner"}].
    """
    led = h.mf(cfg, "ledger")
    path = root / led
    out: List[dict] = []

    def add(kind: str, chk: str, msg: str, owner: str = "test-designer") -> None:
        out.append({"kind": kind, "chk": chk, "loc": led, "msg": msg, "owner": owner})

    try:
        raw = h.read_json(path, default=None)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        add("MANUAL", "CHK-10", f"台帳の JSON を読めません（マージの競合の印などを確認します）: {exc}")
        return out
    if raw is not None and not isinstance(raw, dict):
        add("MANUAL", "CHK-10", "台帳の形式が不正です（最上位がオブジェクトではありません）")
        return out
    data = h.load_ledger(root, cfg)
    changed = raw is None
    if raw is None:
        add("FIX", "CHK-10", "台帳がありません。空の台帳を作成します")
    if not isinstance(data.get("cases"), list) or not isinstance(data.get("ac_digests"), dict):
        add("MANUAL", "CHK-10", "台帳の cases（配列）または ac_digests（オブジェクト）の形式が不正です")
        return out
    seen: Dict[str, int] = {}
    referenced: List[str] = []
    sys_ids = {a.id for a in h.system_acs(doc)} if doc.exists else set()
    for i, c in enumerate(data["cases"]):
        if not isinstance(c, dict) or not c.get("id"):
            add("MANUAL", "CHK-10", f"{i + 1} 番目のケースに id がありません")
            continue
        cid = c["id"]
        seen[cid] = seen.get(cid, 0) + 1
        if seen[cid] == 2:
            add("MANUAL", "CHK-10", f"ケース {cid} が重複しています（ケースは削除せず、片方を `ledger.py update` で直します）")
        filled = []
        for key, make in CASE_DEFAULTS.items():
            if key not in c:
                c[key] = make()
                filled.append(key)
        if c.get("status") not in STATUSES:
            filled.append(f"status={c.get('status')!r}→not_run")
            c["status"] = "not_run"
        if filled:
            changed = True
            add("FIX", "CHK-10", f"{cid} の欠けた項目を補います: {', '.join(filled)}")
        acs = [a for a in c.get("ac_ids", []) if isinstance(a, str)]
        referenced += acs
        if not doc.exists:
            continue
        for a in acs:
            if a not in doc.acs:
                add("MANUAL", "CHK-10", f"{cid} が存在しない受入基準 {a} を参照しています（`ledger.py update --ac` か `block`）")
            elif a not in sys_ids and c.get("status") != "blocked":
                add("MANUAL", "CHK-10", f"{cid} の {a} は System Test の対象外になりました（理由つきで `ledger.py block` するか更新します）")
        old = [r for r in c.get("requirement_ids", []) if isinstance(r, str)]
        owners = []
        for a in acs:
            r = doc.acs[a].requirement if a in doc.acs else None
            if r and r in doc.requirements and r not in owners:
                owners.append(r)
        new = [r for r in old if r in doc.requirements]
        new += [r for r in owners if r not in new]
        if new and new != c.get("requirement_ids"):
            changed = True
            history(c, f"requirement_ids: {c.get('requirement_ids')} -> {new}",
                    "rdfix: 受入基準の「対応する要求」と要求定義書に合わせる", by)
            c["requirement_ids"] = new
            add("FIX", "CHK-10", f"{cid} の requirement_ids を {old} → {new} に直します（受入基準の対応する要求に合わせる）")
    digests = data["ac_digests"]
    ref_set = set(referenced)
    if doc.exists:
        for a in sorted(ref_set):
            ac = doc.acs.get(a)
            if ac is None:
                continue
            cur = h.ac_digest(ac, doc.params)
            old_d = digests.get(a)
            if old_d is None:
                digests[a] = cur
                changed = True
                add("FIX", "CHK-11", f"{a} の ac_digests を補います（{cur}）")
            elif old_d != cur:
                add("MANUAL", "CHK-11", f"{a} の本文が台帳の作成時から変わっています。ケースを見直してから `ledger.py digests --update`")
        for a in sorted(k for k in digests if k not in ref_set):
            del digests[a]
            changed = True
            add("FIX", "CHK-11", f"どのケースも参照していない {a} の ac_digests を取り除きます")
    if apply and changed:
        h.save_ledger(root, cfg, data)
    return out


def cmd_repair(args, root, cfg) -> int:
    doc = h.parse_requirements(root, cfg)
    acts = repair(root, cfg, doc, args.apply, args.by)
    for a in acts:
        tail = f"（担当: {a['owner']}）" if a["kind"] == "MANUAL" else ""
        print(f"{a['kind']} {a['chk']} {a['loc']} {a['msg']}{tail}")
    fixes = sum(1 for a in acts if a["kind"] == "FIX")
    print(f"ledger repair: fix={fixes} manual={len(acts) - fixes}{' (applied)' if args.apply else ''}")
    return 1 if fixes and not args.apply else 0


def changed_files(root: Path, base: Optional[str]) -> List[str]:
    if not base:
        return []
    rc, out = h.git(["diff", "--name-only", base], root)
    files = out.splitlines() if rc == 0 else []
    rc2, out2 = h.git(["ls-files", "-o", "--exclude-standard"], root)
    if rc2 == 0:
        files += out2.splitlines()
    return sorted(set(f for f in files if f))


# Shared (execution-base) code: a change here can affect any case, so the selection is widened (AC-451).
# A file that appears in a case's command is not treated as shared (it is matched by command as before).
SHARED_CODE_RE = re.compile(
    r"^(scripts/[^/]+\.(py|ps1|sh|cmd|json)|tools/install\.py|\.github/.+|(.*/)?conftest\.py|"
    r"(.*/)?(package(-lock)?\.json|pyproject\.toml|requirements[^/]*\.txt|pytest\.ini|tox\.ini))$")


def added_lines_by_file(root: Path, base: Optional[str], files: List[str]) -> Optional[Dict[str, str]]:
    """Text of the added/changed lines per file (git diff -U0 vs base; untracked files count fully). None = cannot analyse."""
    res: Dict[str, List[str]] = {}
    if base:
        rc, out = h.git(["diff", "-U0", "--no-color", "--no-renames", base], root)
        if rc != 0:
            return None
        cur = None
        for line in out.splitlines():
            if line.startswith("+++ "):
                cur = line[4:].strip()
                cur = cur[2:] if cur.startswith("b/") else (None if cur == "/dev/null" else cur)
                if cur is not None:
                    res.setdefault(cur, [])
            elif line.startswith("+") and cur is not None:
                res[cur].append(line[1:])
    for f in files:
        if f in res:
            continue
        p = root / f
        if p.is_file() and p.stat().st_size < 2_000_000:
            try:
                tracked = h.git(["ls-files", "--error-unmatch", f], root)[0] == 0
            except Exception:
                return None
            if not tracked:
                res[f] = p.read_text(encoding="utf-8", errors="replace").splitlines()
    return {k: "\n".join(v) for k, v in res.items()}


def select_cases(root: Path, cfg: dict, data: dict, mode: str, base: Optional[str], retry_failed: bool = True,
                 reasons: Optional[Dict[str, str]] = None) -> List[dict]:
    """retry_failed=False: status "fail" cases are picked only by ID / command-file match (not_run is still picked).
    reasons (optional dict) receives {case id: why it was selected}. For `changed`, IDs are taken from the changed lines
    only; when that is not safe (shared code, unparsable diff, a changed file without IDs) the legacy selection is used
    ("広げた"), which always includes the narrow one."""
    legacy = _select_legacy(root, cfg, data, mode, base, retry_failed)
    if mode != "changed":
        if reasons is not None:
            for c in legacy:
                reasons[c["id"]] = f"--select {mode}"
        return legacy
    files = changed_files(root, base)
    if not files:
        if reasons is not None:
            for c in legacy:
                reasons[c["id"]] = "ledger status (not_run/fail)" if c.get("status") in ("not_run", "fail") else "従来の選択"
        return legacy
    cases = data["cases"]
    cmds = [c.get("command") or "" for c in cases]
    in_cmd = {f: any(f in cm for cm in cmds) for f in files}
    shared = [f for f in files if SHARED_CODE_RE.match(f) and not in_cmd[f]]
    added = added_lines_by_file(root, base, files)
    why_wide = ""
    ids_by_file: Dict[str, set] = {}
    if added is not None:
        for f in files:
            ids_by_file[f] = set(h.CODE_ID_RE.findall(added.get(f, "")))
    if shared:
        why_wide = "共通コードの変更: " + ", ".join(shared[:3]) + (" ほか" if len(shared) > 3 else "")
    elif added is None:
        why_wide = "diff を解析できない"
    else:
        bare = [f for f in files if not ids_by_file[f] and not in_cmd[f]]
        if bare:
            why_wide = "変更行に ID がない: " + ", ".join(bare[:3]) + (" ほか" if len(bare) > 3 else "")
    ids = set().union(*ids_by_file.values()) if ids_by_file else set()
    narrow: Dict[str, str] = {}
    for c in cases:
        if c.get("status") == "blocked":
            continue
        hit = sorted(ids & set(c.get("requirement_ids", []) + c.get("ac_ids", [])))
        if c.get("status") == "not_run" or (retry_failed and c.get("status") == "fail"):
            narrow[c["id"]] = f"ledger status {c.get('status')}"
        elif hit:
            narrow[c["id"]] = "変更行の ID: " + ",".join(hit[:5])
        else:
            fm = [f for f in files if f and f in (c.get("command") or "")]
            if fm:
                narrow[c["id"]] = "command に変更ファイル: " + fm[0]
    if not why_wide:
        out = [c for c in cases if c["id"] in narrow]
        if reasons is not None:
            reasons.update(narrow)
        return out
    out = []
    for c in legacy:
        out.append(c)
        if reasons is not None:
            reasons[c["id"]] = narrow.get(c["id"]) or f"広げた（{why_wide}）"
    return out


def _select_legacy(root: Path, cfg: dict, data: dict, mode: str, base: Optional[str], retry_failed: bool = True) -> List[dict]:
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
        if c.get("status") == "not_run" or (retry_failed and c.get("status") == "fail"):
            out.append(c)
            continue
        if ids & set(c.get("requirement_ids", []) + c.get("ac_ids", [])):
            out.append(c)
            continue
        if any(f and f in (c.get("command") or "") for f in files):
            out.append(c)
    return out


def resolve_jobs(arg, cfg: dict) -> int:
    """--jobs N|auto, else system_test.jobs in the config, else 1 (cases may share ports or data; opt in)."""
    v = arg if arg not in (None, "") else (cfg.get("system_test") or {}).get("jobs", 1)
    if str(v).lower() == "auto":
        return max(2, min(6, (os.cpu_count() or 4) // 4))
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return 1


def parse_pytest(cmd: str):
    """`python -m pytest <file>[::node] [-k expr] [-q|-v|-s]` -> (file, node, kexpr). Anything else (other options, shell syntax) -> None."""
    if any(ch in cmd for ch in "\\&|;<>%^`$"):
        return None
    try:
        t = shlex.split(cmd)
    except ValueError:
        return None
    if t[1:3] == ["-m", "pytest"] and t[0] in ("python", "python3", "py"):
        i = 3
    elif t[:1] == ["pytest"]:
        i = 1
    else:
        return None
    target, k = None, None
    while i < len(t):
        a = t[i]
        if a in ("-q", "-v", "-vv", "-s"):
            pass
        elif a == "-k" and i + 1 < len(t) and k is None:
            k = t[i + 1]
            i += 1
        elif not a.startswith("-") and target is None and ".py" in a:
            target = a
        else:
            return None
        i += 1
    if not target:
        return None
    f, _, node = target.partition("::")
    if node and k:
        return None
    if node and not re.fullmatch(r"(\w+::)*\w+(\[[^\]\s\"']*\])?", node):
        return None
    return f, node, k


def _kmatcher(names):
    low = [n.lower() for n in names]
    return lambda ident, **kw: any(ident.lower() in n for n in low)


def plan_batches(reps, groups, is_serial, is_canary, jobs=1, durs=None):
    """Group the System Test commands that run the same pytest file into one process each (>= 2 distinct commands).
    Every case pays for the process start, the imports and the browser tool's start-up once per command; one
    process per file pays it once. Returns (units, batched_reps) where each unit is a virtual case with "_batch" members."""
    try:
        from _pytest.mark.expression import Expression  # the same -k grammar as pytest
    except Exception:
        return [], set()
    members = []
    for c in reps:
        if is_serial(c) or is_canary(c):
            continue
        p = parse_pytest(c["command"])
        if not p:
            continue
        try:
            if p[2]:
                Expression.compile(p[2])
        except Exception:
            continue
        members.append((c, (re.sub(r"^\./", "", p[0]), p[1], p[2])))
    if len(members) < 2:
        return [], set()
    used = {c["command"] for c, _ in members}
    parts = split_members(members, jobs, durs)
    units = [_make_unit(ms, i if len(parts) > 1 else None) for i, ms in enumerate(parts)]
    return units, used


def split_members(members, jobs=1, durs=None):
    """Split compatible members into at most `jobs` balanced parts (jobs <= 1: one part). Known durations (longest
    first) balance the parts, else the case count does; members of one file stay together as far as possible."""
    n = min(max(1, int(jobs or 1)), len(members))
    if n <= 1:
        return [list(members)]
    durs = durs or {}
    known = all(float(durs.get(c["command"], 0) or 0) > 0 for c, _ in members)
    w = (lambda m: float(durs[m[0]["command"]])) if known else (lambda m: 1.0)
    byfile: dict = {}
    for m in members:
        byfile.setdefault(m[1][0], []).append(m)
    items = list(byfile.values())
    while len(items) < n:  # fewer files than processes: split the heaviest multi-case file
        cand = [it for it in items if len(it) > 1]
        if not cand:
            break
        big = max(cand, key=lambda it: sum(w(m) for m in it))
        items.remove(big)
        big = sorted(big, key=lambda m: -w(m))
        half = [big[i] for i in range(0, len(big), 2)], [big[i] for i in range(1, len(big), 2)]
        items += [list(half[0]), list(half[1])]
    items.sort(key=lambda it: -sum(w(m) for m in it))
    bins = [[] for _ in range(min(n, len(items)))]
    load = [0.0] * len(bins)
    for it in items:
        i = load.index(min(load))
        bins[i].extend(it)
        load[i] += sum(w(m) for m in it)
    return [b for b in bins if b]


def _make_unit(members, idx=None):
    # One process for the compatible cases of any test files (no project-specific path is assumed).
    files = list(dict.fromkeys(p[0] for _, p in members))
    if not any(p[2] for _, p in members):
        whole = {p[0] for _, p in members if not p[1]}
        tg = [f for f in files if f in whole]
        tg += list(dict.fromkeys(f"{p[0]}::{p[1]}" for _, p in members if p[1] and p[0] not in whole))
        target, sel = " ".join(f'"{t}"' for t in tg), ""
    else:
        exprs = []
        for _, p in members:
            e = f"({p[2]})" if p[2] else (p[1].split("::")[-1].split("[")[0] if p[1] else Path(p[0]).stem)
            if e not in exprs:
                exprs.append(e)
        target, sel = " ".join(f'"{f}"' for f in files), '-k "' + " or ".join(exprs) + '"'
    label = files[0] if len(files) == 1 else f"{files[0]}+{len(files) - 1}files"
    sfx = "" if idx is None else f"#{idx + 1}"
    return {"id": "BATCH:" + label + sfx, "command": f"BATCH {label}{sfx} {sel}",
            "_batch": {"file": label + sfx, "target": target, "sel": sel, "members": members}}


def kill_tree(proc):
    """Kill a process and every descendant (Popen.kill() alone leaves browser/pytest children behind)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def run_shell(cmd, cwd, timeout):
    """Run a shell command; on timeout, error or interrupt the whole process tree is killed. Returns (rc, output); rc 124 = timeout."""
    kw = {"start_new_session": True} if os.name != "nt" else {}
    proc = subprocess.Popen(cmd, cwd=cwd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", **kw)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out or ""
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        try:
            proc.communicate(timeout=10)
        except Exception:
            pass
        return 124, f"TIMEOUT after {timeout}s"
    except BaseException:
        kill_tree(proc)
        raise


def run_batch(unit, root, logs_dir, timeout, execute_single):
    """Run one merged pytest process and attribute the JUnit result to each member command.
    A member whose tests failed (or that matched no test) is re-run alone, so a failure is always judged and logged
    exactly as before and interference between tests cannot create a false fail. Returns {command: (rc, seconds, log)}."""
    import xml.etree.ElementTree as ET
    from _pytest.mark.expression import Expression
    b = unit["_batch"]
    stamp = h.new_run_id()
    junit = logs_dir / f"BATCH-{re.sub(r'[^A-Za-z0-9]+', '_', b['file'])}-{stamp}.xml"
    cmd = f'python -m pytest {b["target"]} {b["sel"]} -q --junitxml="{junit}"'
    t0 = time.time()
    # the merged run's timeout scales with the number of cases it carries
    _rc, out = run_shell(cmd, str(root), timeout * max(1, len(b["members"])) if timeout else timeout)
    mlog = logs_dir / f"BATCH-{re.sub(r'[^A-Za-z0-9]+', '_', b['file'])}-{stamp}.log"
    mlog.write_text(out, encoding="utf-8")
    tcs = []
    try:
        for tc in ET.parse(junit).getroot().iter("testcase"):
            bad = tc.find("failure") is not None or tc.find("error") is not None
            cls = (tc.get("classname") or "").split(".")
            tcs.append((tc.get("name") or "", cls, float(tc.get("time") or 0), bad))
    except (OSError, ET.ParseError, ValueError):
        tcs = []
    res: dict = {}
    rerun = []
    for c, (f, node, k) in b["members"]:
        if not tcs:
            rerun.append(c)
            continue
        mod = re.sub(r"\.py$", "", f).replace("/", ".")
        ftcs = [t for t in tcs if ".".join(t[1]) == mod or ".".join(t[1]).startswith(mod + ".")]
        if not node and not k:
            hit = ftcs
        elif node:
            parts = node.split("::")
            fn = parts[-1]
            base = fn.split("[")[0]
            hit = [t for t in ftcs if (t[0] == fn if "[" in fn else (t[0] == base or t[0].startswith(base + "[")))
                   and (len(parts) == 1 or parts[-2] in t[1])]
        else:
            ex = Expression.compile(k)
            hit = [t for t in ftcs if ex.evaluate(_kmatcher([t[0], *t[1], Path(f).name, Path(f).stem]))]
        if not hit or any(t[3] for t in hit):
            rerun.append(c)
            continue
        log = logs_dir / f"{c['id']}-{stamp}.log"
        log.write_text(f"BATCH {b['file']}: {len(hit)} tests passed (merged run log: {mlog.name})\n"
                       + "\n".join(f"PASSED {t[0]}" for t in hit), encoding="utf-8")
        res[c["command"]] = (0, round(sum(t[2] for t in hit), 1), log)
    for c in rerun:
        res[c["command"]] = execute_single(c)[1]
    return res


def cmd_run(args, root, cfg) -> int:
    data = h.load_ledger(root, cfg)
    t_start = time.time()
    if args.cases:
        want = split_ids(args.cases)
        sel = [find(data, cid) for cid in want]
    else:
        base = args.base or h.default_base(root, cfg)
        why = {}
        sel = select_cases(root, cfg, data, args.select, base, reasons=why)
        for c in sel:
            print(f"select {c['id']}: {why.get(c['id'], '')}")
        if args.select == "changed":
            print(f"select: {len(sel)}/{len(data['cases'])} cases")
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
    h.apply_resource_env(root, cfg)
    jobs = resolve_jobs(args.jobs, cfg)
    cerr = h.conductor_root(root, cfg)

    def execute(c):
        if deadline and time.time() > deadline:
            return c, None
        t0 = time.time()
        log = logs_dir / f"{c['id']}-{h.new_run_id()}.log"
        rc, out = run_shell(c["command"], str(root), args.case_timeout)
        dur = round(time.time() - t0, 1)
        log.write_text(out, encoding="utf-8")
        return c, (rc, dur, log)

    todo = [c for c in sel if c.get("command")]
    done: dict = {}
    pats = [p for p in ((cfg.get("system_test") or {}).get("serial_patterns") or []) if p]
    dur_path = h.work_dir(cerr, cfg) / ".ebak" / "durations.json"
    try:
        durs = json.loads(dur_path.read_text(encoding="utf-8"))
        if not isinstance(durs, dict):
            durs = {}
    except (OSError, ValueError):
        durs = {}
    # identical commands run once; the result is applied to every case that shares the command
    groups: dict = {}
    for c in todo:
        groups.setdefault(c["command"], []).append(c)
    reps = [g[0] for g in groups.values()]
    omitted = len(todo) - len(reps)

    def is_serial(c):
        return any(x.get("serial") or any(p in x["command"] for p in pats) for x in groups[c["command"]])

    def is_canary(c):
        return args.canary_first and any(x.get("canary") for x in groups[c["command"]])

    cmd_res: dict = {}

    def store(c, r):
        if c.get("_batch"):
            cmd_res.update(r)
        else:
            cmd_res[c["command"]] = r

    def execute_unit(c):
        if not c.get("_batch"):
            return execute(c)
        if deadline and time.time() > deadline:
            return c, {m["command"]: None for m, _ in c["_batch"]["members"]}
        return c, run_batch(c, root, logs_dir, args.case_timeout, execute)

    # canary cases run first and alone, so that a broken canary stops the run before the rest starts
    first = [c for c in reps if is_canary(c)]
    rest = [c for c in reps if c not in first]
    batched = 0
    if not args.no_batch and (cfg.get("system_test") or {}).get("batch_pytest", True):
        units, used = plan_batches(rest, groups, is_serial, is_canary, jobs, durs)
        for u in units:
            groups[u["command"]] = [x for m, _ in u["_batch"]["members"] for x in groups[m["command"]]]
        rest = [c for c in rest if c["command"] not in used] + units
        batched = sum(len(u["_batch"]["members"]) for u in units)

    def dur_key(c):
        if c.get("_batch"):
            return sum(float(durs.get(m["command"], 0) or 0) for m, _ in c["_batch"]["members"])
        return float(durs.get(c["command"], 0) or 0)

    par = [c for c in rest if not is_serial(c)] if jobs > 1 else []
    seq = [c for c in rest if c not in par]
    # longest known duration first (LPT) so the parallel wave finishes sooner
    par.sort(key=lambda c: -dur_key(c))
    # inside the canary stage, non-serial cases run in parallel (jobs) and serial ones alone
    from concurrent.futures import ThreadPoolExecutor
    f_par = [c for c in first if not is_serial(c)] if jobs > 1 else []
    f_seq = [c for c in first if c not in f_par]
    f_par.sort(key=lambda c: -float(durs.get(c["command"], 0) or 0))
    if f_par:
        with ThreadPoolExecutor(jobs) as ex:
            for c, r in ex.map(execute, f_par):
                cmd_res[c["command"]] = r
    for c in f_seq:
        cmd_res[c["command"]] = execute(c)[1]
        r = cmd_res[c["command"]]
        if r and r[0] != 0 and args.stop_on_canary_fail:
            break
    if args.stop_on_canary_fail and any(cmd_res.get(c["command"]) and cmd_res[c["command"]][0] != 0 for c in first):
        stop_reason = "canary 失敗で中止"
    if not stop_reason:
        if par:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(jobs) as ex:
                for c, r in ex.map(execute_unit, par):
                    store(c, r)
        for c in seq:
            store(c, execute_unit(c)[1])
    for c in todo:
        if c["command"] in cmd_res:
            done[c["id"]] = cmd_res[c["command"]]
    try:
        for cmd, r in cmd_res.items():
            if r and r[0] != 124:
                durs[cmd] = r[1]
        dur_path.parent.mkdir(parents=True, exist_ok=True)
        dur_path.write_text(json.dumps(durs), encoding="utf-8")
    except (OSError, ValueError):
        pass
    for c in todo:
        r = done.get(c["id"])
        if r is None:
            summary["skipped"] += 1
            if c["id"] not in done and not stop_reason:
                stop_reason = "時間予算で中止"
            continue
        rc, dur, log = r
        status = "pass" if rc == 0 else "fail"
        summary[status] += 1
        rel_log = log.relative_to(cerr).as_posix() if str(log).startswith(str(cerr)) else str(log)
        lines_out.append(f"{c['id']} {','.join(c.get('requirement_ids', []))} {status} {dur} {rel_log}")
        results["runs"].append({"case": c["id"], "status": status, "exit_code": rc, "seconds": dur, "commit": head, "at": h.now_iso(), "log": rel_log})
        if not args.no_record:
            c["status"] = status
            c["last_commit"] = head
            c["last_run_at"] = h.now_iso()
            c["evidence"] = rel_log
    h.write_json(results_path, results)
    if args.stop_on_canary_fail and not stop_reason and any(c.get("canary") and done.get(c["id"]) and done[c["id"]][0] != 0 for c in todo):
        stop_reason = "canary 失敗で中止"
    if not args.no_record:
        h.save_ledger(root, cfg, data)
    print("\n".join(lines_out))
    result = stop_reason or ("全件 pass" if summary["fail"] == 0 else "fail あり")
    print(f"ledger run: pass={summary['pass']} fail={summary['fail']} skipped={summary['skipped']} results={results_path} 結果: {result}"
          f" unique_commands={len(reps)} dedup_omitted={omitted} batched_commands={batched} jobs={jobs} elapsed={time.time() - t_start:.1f}s")
    return 0 if summary["fail"] == 0 and not stop_reason else 1


def cmd_preflight(args, root, cfg) -> int:
    """Collect-only check of pytest commands: catches syntax errors, bad node ids and -k typos (0 tests selected)
    before an implementer is started, instead of as a failed System Test after the merge (a 30-60 min rework loop)."""
    data = h.load_ledger(root, cfg)
    if args.cases:
        sel = [find(data, cid) for cid in split_ids(args.cases)]
    elif args.all:
        sel = [c for c in data["cases"] if c.get("status") != "blocked"]
    else:
        sel = [c for c in data["cases"] if c.get("status") in ("not_run", "fail")]
    groups: dict = {}
    for c in sel:
        cmd = c.get("command") or ""
        if re.search(r"\bpytest\b", cmd):
            groups.setdefault(cmd, []).append(c["id"])
    h.apply_resource_env(root, cfg)

    def check(cmd):
        try:
            p = subprocess.run(cmd + " --collect-only -q", cwd=str(root), shell=True, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=args.timeout)
        except subprocess.TimeoutExpired:
            return cmd, 124, f"TIMEOUT after {args.timeout}s"
        return cmd, p.returncode, (p.stdout or "") + (p.stderr or "")

    from concurrent.futures import ThreadPoolExecutor
    bad = 0
    with ThreadPoolExecutor(max(1, resolve_jobs(args.jobs, cfg))) as ex:
        for cmd, rc, out in ex.map(check, list(groups)):
            if rc == 0:
                continue
            bad += 1
            why = "選択されたテストが 0 件（-k・node id・パスを確認）" if rc == 5 else "収集に失敗（構文・import・fixture を確認）"
            tail = " | ".join([l.strip() for l in out.splitlines() if l.strip()][-3:])[:240]
            print(f"PREFLIGHT fail {','.join(groups[cmd])} rc={rc} {why}: {cmd} :: {tail}")
    print(f"PREFLIGHT: {'fail' if bad else 'pass'} commands={len(groups)} bad={bad} cases={len(sel)}")
    return 1 if bad else 0


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
    a.add_argument("--new-case-reason", default="",
                   help="同じ AC の有効なケースがあっても別のケースにする理由（既定では拒否し、update での拡張を促す）")
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
    rp = sub.add_parser("repair")
    rp.add_argument("--apply", action="store_true", help="修正を書き込む（既定は確認だけ）")
    pf = sub.add_parser("preflight")
    pf.add_argument("--cases")
    pf.add_argument("--all", action="store_true", help="pass 済みも含める（既定は not_run・fail のケース）")
    pf.add_argument("--jobs", default=None)
    pf.add_argument("--timeout", type=int, default=300)
    r = sub.add_parser("run")
    r.add_argument("--cases")
    r.add_argument("--select", default="changed", choices=("changed", "failed", "all"))
    r.add_argument("--base")
    r.add_argument("--canary-first", action="store_true")
    r.add_argument("--stop-on-canary-fail", action="store_true")
    r.add_argument("--max-minutes", type=float, default=0)
    r.add_argument("--case-timeout", type=int, default=1800)
    r.add_argument("--jobs", default=None, help="同時に実行するケース数（N または auto。既定は system_test.jobs、なければ 1）。\"serial\": true のケースは単独で実行")
    r.add_argument("--no-record", action="store_true", help="台帳を書き換えない（作業役の worktree で使う）")
    r.add_argument("--no-batch", action="store_true", help="同じ pytest ファイルのケースを 1 プロセスにまとめない（既定はまとめる。system_test.batch_pytest: false でも止められる）")
    r.add_argument("--results")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
    fn = {"summary": cmd_summary, "add": cmd_add, "update": cmd_update, "block": cmd_block,
          "set": cmd_set, "digests": cmd_digests, "run": cmd_run, "repair": cmd_repair,
          "preflight": cmd_preflight}[args.cmd]
    if args.cmd in ("add", "update", "block", "set", "digests"):
        with ledger_lock(root, cfg):
            return fn(args, root, cfg)
    return fn(args, root, cfg)


class ledger_lock:
    """Serialises ledger writers (parallel test-designers). Waits up to 120 s; a lock older than 120 s is stale."""

    def __init__(self, root: Path, cfg: dict):
        self.path = h.work_dir(root, cfg) / ".ebak" / "ledger.lock"

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        end = time.time() + 120
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 120:
                        self.path.unlink()
                        continue
                except OSError:
                    continue
                if time.time() > end:
                    raise SystemExit("ERROR ledger: 台帳のロックを取得できません（別の書き込みが続いています）")
                time.sleep(0.2)

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except OSError:
            pass

if __name__ == "__main__":
    sys.exit(main())
