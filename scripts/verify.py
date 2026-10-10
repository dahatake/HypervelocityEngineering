#!/usr/bin/env python3
"""verify.py - L1 deterministic verification in one command (plan §10). Exit 0 = pass.

Usage:
  python scripts/verify.py                 # management data checks + build/lint/test commands
  python scripts/verify.py --docs-only     # management data checks only (rd-author, test-designer)
  python scripts/verify.py --quick         # skip commands marked "slow": true (implementer gate)
  python scripts/verify.py --run current   # add CHK-21 for the active run's queue.json
  python scripts/verify.py --strict        # final / integration gate: warnings that matter become errors
  python scripts/verify.py --no-cache      # always run (a PASS on the same clean commit is otherwise reused)

Project commands come from scripts/ebak.config.json -> verify.commands:
  [{"name": "build", "run": "npm run build"}, {"name": "unit", "run": "npm test"},
   {"name": "e2e-smoke", "run": "npx playwright test --grep @canary", "slow": true}]
Full logs go to /work (never to /docs or tests); only a short summary is printed.

Cache: when the working tree is clean (no tracked or untracked changes), a PASS is stored in
/work/.ebak/verify-cache.json under a key made of HEAD, the arguments, scripts/ebak.config.json and the run state
that the checks read. The same verify on the same commit (e.g. the implementer's gate, then hook G-4) is then
answered from the cache. FAIL is never cached. Disable with --no-cache or EBAK_VERIFY_NO_CACHE=1.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402

_STEP_LOCK = threading.Lock()


def log_dir(root: Path, cfg: dict) -> Path:
    croot = h.conductor_root(root, cfg)
    rid = h.current_run(croot, cfg)
    d = h.run_dir(croot, cfg, rid) / "logs" if rid else h.work_dir(root, cfg) / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def normalize_commands(raw) -> Tuple[List[dict], List[str]]:
    """verify.commands -> ([{"name", "run", ...}], [problems]). A plain string is accepted as {"run": <string>}."""
    if raw in (None, ""):
        return [], []
    if isinstance(raw, (str, dict)):
        raw = [raw]
    if not isinstance(raw, list):
        return [], [f"verify.commands は配列にします（現在: {type(raw).__name__}）"]
    out: List[dict] = []
    problems: List[str] = []
    used: Dict[str, int] = {}
    for i, c in enumerate(raw, 1):
        if isinstance(c, str):
            c = {"run": c}
        if not isinstance(c, dict):
            problems.append(f"verify.commands の {i} 番目が不正です（{type(c).__name__}）")
            continue
        run = c.get("run") or c.get("command") or c.get("cmd")
        if not isinstance(run, str) or not run.strip():
            problems.append(f"verify.commands の {i} 番目に \"run\"（実行するコマンド）がありません: {json.dumps(c, ensure_ascii=False)[:120]}")
            continue
        base = str(c.get("name") or re.sub(r"[^A-Za-z0-9_.-]+", "-", run.split()[0].split("/")[-1].split("\\")[-1]).strip("-") or "step")
        used[base] = used.get(base, 0) + 1
        name = base if used[base] == 1 else f"{base}-{used[base]}"
        out.append({**c, "name": name, "run": run})
    return out, problems


CACHE_TTL_SEC = 24 * 3600
CACHE_MAX = 200


def cache_key(root: Path, cfg: dict, args) -> str:
    """Key of a verify result, or "" when the result must not be cached (dirty tree, no git)."""
    if args.no_cache or os.environ.get("EBAK_VERIFY_NO_CACHE"):
        return ""
    # tree hash: the same content on another commit/worktree shares the result
    rc, head = h.git(["rev-parse", "HEAD^{tree}"], root)
    if rc != 0 or not head.strip():
        return ""
    rc, dirty = h.git(["status", "--porcelain"], root)
    # the toolkit's own byte-code (scripts/__pycache__) appears as untracked when the target does not ignore it
    dirty = "\n".join(l for l in dirty.splitlines() if "__pycache__/" not in l and not l.endswith(".pyc"))
    if rc != 0 or dirty.strip():
        return ""
    parts = [head.strip(), json.dumps(vars(args), sort_keys=True, default=str),
             json.dumps(cfg, sort_keys=True, ensure_ascii=False), h.TOOLKIT_VERSION]
    croot = h.conductor_root(root, cfg)
    rid = h.current_run(croot, cfg)
    if rid:
        meta = h.load_meta(croot, cfg, rid)
        parts.append(f"{rid}:{meta.get('ledger_strict')}:{meta.get('stages_done')}")
        if args.run:
            parts.append(json.dumps(h.load_queue(croot, cfg, rid), sort_keys=True, ensure_ascii=False))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def cache_path(root: Path, cfg: dict) -> Path:
    return h.work_dir(h.conductor_root(root, cfg), cfg) / ".ebak" / "verify-cache.json"


def cache_get(root: Path, cfg: dict, key: str) -> dict:
    if not key:
        return {}
    data = h.read_json(cache_path(root, cfg), default={}) or {}
    hit = data.get(key) or {}
    if hit and time.time() - float(hit.get("t", 0)) < CACHE_TTL_SEC:
        return hit
    return {}


def cache_put(root: Path, cfg: dict, key: str, summary: str) -> None:
    if not key:
        return
    p = cache_path(root, cfg)
    try:
        data = h.read_json(p, default={}) or {}
    except ValueError:
        data = {}
    data[key] = {"t": time.time(), "at": h.now_iso(), "summary": summary}
    if len(data) > CACHE_MAX:
        data = dict(sorted(data.items(), key=lambda kv: kv[1].get("t", 0))[-CACHE_MAX:])
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        h.write_json(p, data)
    except OSError:
        pass


FLAKY_DEFAULT = r"Timeout calling|ECONNRESET|ETIMEDOUT|EBUSY|EMFILE|worker (?:exited|terminated)|ERR_WORKER_OUT_OF_MEMORY"


def step_key(root: Path, files) -> str:
    """Hash of the files a step depends on (e.g. package-lock.json), or "" when none exist."""
    hs = hashlib.sha256()
    found = False
    for f in files:
        p = root / f
        if p.is_file():
            found = True
            hs.update(f.encode() + b"\0" + p.read_bytes())
    return hs.hexdigest() if found else ""


def step_cache_path(root: Path, cfg: dict) -> Path:
    return h.work_dir(root, cfg) / ".ebak" / "step-cache.json"


def run_step(root: Path, cfg: dict, c: dict, cmd: str, no_cache: bool):
    """Run one verify command. Returns (rc, out, note). Skips when "cache_files" are unchanged since the last success;
    retries once when a failure matches an infrastructure-flaky pattern (config "retry_on", default FLAKY_DEFAULT)."""
    timeout = int(c.get("timeout_sec", cfg["verify"].get("timeout_sec", 1800)))
    files = c.get("cache_files") or []
    skey = "" if no_cache or not files else step_key(root, files)
    sp = step_cache_path(root, cfg)
    if skey:
        try:
            if (h.read_json(sp, default={}) or {}).get(c["name"]) == skey:
                return 0, "", "skipped (unchanged: " + ", ".join(files) + ")"
        except (ValueError, OSError):
            pass
    rc, out = h.run(cmd, cwd=root, timeout=timeout, shell=True)
    note = ""
    pat = cfg["verify"].get("retry_on", FLAKY_DEFAULT)
    if rc != 0 and pat and cfg["verify"].get("retry_flaky", True) and re.search(pat, out):
        rc, out2 = h.run(cmd, cwd=root, timeout=timeout, shell=True)
        out = out + "\n--- retry (flaky infrastructure failure) ---\n" + out2
        note = "retried"
    if rc == 0 and skey:
        try:
            with _STEP_LOCK:
                data = h.read_json(sp, default={}) or {}
                data[c["name"]] = skey
                sp.parent.mkdir(parents=True, exist_ok=True)
                h.write_json(sp, data)
        except (ValueError, OSError):
            pass
    return rc, out, note


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs-only", action="store_true")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--run", default=None)
    ap.add_argument("--base", default=None)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--strict-ledger", action="store_true")
    ap.add_argument("--no-strict-ledger", action="store_true")
    ap.add_argument("--show-warnings", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
    h.apply_resource_env(root, cfg)
    key = "" if args.show_warnings else cache_key(root, cfg, args)
    hit = cache_get(root, cfg, key)
    if hit:
        print(f"PASS (cached {hit.get('at', '')[:19]}: 同じ commit・引数・設定で合格済み。再実行は --no-cache)")
        print(f"verify: PASS failed=- elapsed=0s HEAD={h.head_commit(root) or '-'} cached=1")
        return 0
    summarize = h.load_script("summarize").summarize
    rdcheck = h.load_script("rdcheck")
    ldir = log_dir(root, cfg)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    failed = []
    t0 = time.time()

    rd_args = ["--root", str(root), "check"]
    if args.base:
        rd_args += ["--base", args.base]
    if args.run:
        rd_args += ["--run", args.run]
    if args.strict:
        rd_args.append("--strict")
    if args.strict_ledger:
        rd_args.append("--strict-ledger")
    if args.no_strict_ledger:
        rd_args.append("--no-strict-ledger")
    if not args.show_warnings:
        rd_args.append("--errors-only")
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = rdcheck.main(rd_args)
    out = buf.getvalue()
    (ldir / f"verify-{stamp}-rdcheck.log").write_text(out, encoding="utf-8")
    lines = out.strip().splitlines()
    if rc != 0:
        failed.append("rdcheck")
        print(f"FAIL rdcheck (management data) log={(ldir / f'verify-{stamp}-rdcheck.log').as_posix()}")
        shown = [l for l in lines if l.startswith("ERROR")][:25]
        for l in shown:
            print("  " + l)
        more = sum(1 for l in lines if l.startswith("ERROR")) - len(shown)
        if more > 0:
            print(f"  ... (+{more} errors)")
        try:
            n = h.load_script("rdfix").count_fixable(root, cfg)
        except Exception:  # the hint must never break verify
            n = 0
        if n:
            print(f"HINT rdfix: データ層の不整合のうち {n} 件は `python scripts/rdfix.py --apply` で自動修正できます（要求定義書は変更しません）")
    else:
        print("PASS rdcheck (management data)")
    if args.show_warnings:
        for l in lines:
            if l.startswith("WARN"):
                print("  " + l)
    if lines:
        print("  " + lines[-1])

    if not args.docs_only:
        cmds, problems = normalize_commands(cfg.get("verify", {}).get("commands", []))
        for p in problems:
            failed.append("config")
            print(f"FAIL config {p}")
            print('  書き方: "commands": [{"name": "unit", "run": "python -m pytest -q"}]（users-guide/04-customization.md 4.1）')
        if not cmds and not problems:
            print("INFO verify.commands が空です（scripts/ebak.config.json にビルド・静的検査・テストのコマンドを登録します）")
        runnable = []
        for c in cmds:
            if args.quick and c.get("slow"):
                print(f"SKIP {c['name']} (slow, --quick)")
                continue
            runnable.append(c)
        # consecutive steps marked "parallel": true (e.g. lint, typecheck, unit after a build) run at the same time
        groups: List[List[dict]] = []
        for c in runnable:
            if c.get("parallel") and groups and groups[-1][-1].get("parallel"):
                groups[-1].append(c)
            else:
                groups.append([c])
        nocache = args.no_cache or bool(os.environ.get("EBAK_VERIFY_NO_CACHE"))

        def one(c):
            s = time.time()
            rc, out, note = run_step(root, cfg, c, c["run"], nocache)
            return c, rc, out, note, time.time() - s

        for g in groups:
            if len(g) > 1:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(len(g)) as ex:
                    results = list(ex.map(one, g))
            else:
                results = [one(g[0])]
            for c, rc, out, note, dur in results:
                name = c["name"]
                logf = ldir / f"verify-{stamp}-{name}.log"
                logf.write_text(out, encoding="utf-8")
                if rc == 0:
                    print(f"PASS {name} ({dur:.0f}s){' ' + note if note else ''}")
                else:
                    failed.append(name)
                    print(f"FAIL {name} exit={rc} ({dur:.0f}s) log={logf.as_posix()}")
                    for l in summarize(out, 10, 3).splitlines():
                        print("  " + l)
    status = "FAIL" if failed else "PASS"
    line = f"verify: {status} failed={','.join(failed) or '-'} elapsed={time.time() - t0:.0f}s HEAD={h.head_commit(root) or '-'}"
    print(line)
    if not failed and key and key == cache_key(root, cfg, args):
        cache_put(root, cfg, key, line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
