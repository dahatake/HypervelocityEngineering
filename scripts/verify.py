#!/usr/bin/env python3
"""verify.py - L1 deterministic verification in one command (plan §10). Exit 0 = pass.

Usage:
  python scripts/verify.py                 # management data checks + build/lint/test commands
  python scripts/verify.py --docs-only     # management data checks only (rd-author, test-designer)
  python scripts/verify.py --quick         # skip commands marked "slow": true (implementer gate)
  python scripts/verify.py --run current   # add CHK-21 for the active run's queue.json
  python scripts/verify.py --strict        # final / integration gate: warnings that matter become errors

Project commands come from scripts/hve.config.json -> verify.commands:
  [{"name": "build", "run": "npm run build"}, {"name": "unit", "run": "npm test"},
   {"name": "e2e-smoke", "run": "npx playwright test --grep @canary", "slow": true}]
Full logs go to /work (never to /docs or tests); only a short summary is printed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hvelib as h  # noqa: E402


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
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
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
            print("INFO verify.commands が空です（scripts/hve.config.json にビルド・静的検査・テストのコマンドを登録します）")
        for c in cmds:
            name, cmd = c["name"], c["run"]
            if args.quick and c.get("slow"):
                print(f"SKIP {name} (slow, --quick)")
                continue
            s = time.time()
            rc, out = h.run(cmd, cwd=root, timeout=int(c.get("timeout_sec", cfg["verify"].get("timeout_sec", 1800))), shell=True)
            logf = ldir / f"verify-{stamp}-{name}.log"
            logf.write_text(out, encoding="utf-8")
            dur = time.time() - s
            if rc == 0:
                print(f"PASS {name} ({dur:.0f}s)")
            else:
                failed.append(name)
                print(f"FAIL {name} exit={rc} ({dur:.0f}s) log={logf.as_posix()}")
                for l in summarize(out, 10, 3).splitlines():
                    print("  " + l)
    status = "FAIL" if failed else "PASS"
    print(f"verify: {status} failed={','.join(failed) or '-'} elapsed={time.time() - t0:.0f}s HEAD={h.head_commit(root) or '-'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
