#!/usr/bin/env python3
"""run 監視: 残留プロセスの表示・回収と、queue の doing 時間超過の検出（標準ライブラリのみ）。

  python scripts/watch.py scan
  python scripts/watch.py reap [--under PATH]
  python scripts/watch.py stuck [--item-minutes N]

終了コード: 0 正常 / 1 stuck で超過あり / 2 引数・安全上の拒否。
FR-1064 / NFR-OPS-008。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

GRACE_MINUTES = 10          # PARAM-044
ITEM_MINUTES = 60           # PARAM-045
STALE_MINUTES = 120         # PARAM-046
WATCHED_NAMES = ("node", "chrome", "msedge", "chromium", "firefox", "headless_shell",
                 "chrome-headless-shell", "playwright")

ROOT = Path(__file__).resolve().parents[1]


# ----------------------------------------------------------------- pure logic
def norm_path(s: str) -> str:
    return (s or "").replace("\\", "/").rstrip("/").lower()


def is_watched_name(name: str) -> bool:
    n = (name or "").lower()
    n = re.sub(r"\.exe$", "", n)
    return n in WATCHED_NAMES


def is_root_path(path: str) -> bool:
    p = norm_path(path)
    return p == "" or re.fullmatch(r"[a-z]:", p) is not None


def under_matches(under: str, cmd: str) -> bool:
    """AC-359: True if `under` appears in `cmd` ending at a path boundary
    (separator, quote, whitespace or end of string). Case and \\ vs / are ignored."""
    u = norm_path(under)
    if not u:
        return False
    c = (cmd or "").replace("\\", "/").lower()
    pos = c.find(u)
    while pos != -1:
        end = pos + len(u)
        if end == len(c) or c[end] in "/\"' \t\r\n":
            return True
        pos = c.find(u, pos + 1)
    return False


def ancestors(pid: int, parent_of: Dict[int, int]) -> Set[int]:
    out = {pid}
    cur = pid
    while cur in parent_of and parent_of[cur] not in out and parent_of[cur] > 0:
        cur = parent_of[cur]
        out.add(cur)
    return out


def classify(proc: dict, repo_paths: Iterable[str], protected: Set[int], all_pids: Set[int],
             grace: float = GRACE_MINUTES, stale: float = STALE_MINUTES,
             under: Optional[str] = None) -> Tuple[bool, str, str]:
    """Return (kill, reason, kind). kind is 孤児/古い/'' ."""
    if proc["pid"] in protected:
        return False, "自分または祖先", ""
    if not is_watched_name(proc.get("name", "")):
        return False, "監視対象の名前でない", ""
    cmd = norm_path(proc.get("cmd", ""))
    if under is not None:
        if is_root_path(under):
            return False, "--under が空またはルート", ""
        if not under_matches(under, cmd):
            return False, "--under のパスを含まない", ""
        if proc.get("age_min", 0) <= grace:
            return False, f"起動から {grace:g} 分以内", ""
        return True, "--under 配下", "配下"
    if not any(norm_path(r) and norm_path(r) in cmd for r in repo_paths):
        return False, "リポジトリのパスを含まない", ""
    if proc.get("age_min", 0) <= grace:
        return False, f"起動から {grace:g} 分以内", ""
    if proc.get("ppid", 0) not in all_pids:
        return True, "親が存在しない", "孤児"
    if proc.get("age_min", 0) > stale:
        return True, f"起動から {stale:g} 分超", "古い"
    return False, "孤児でも古くもない", ""


def stuck_items(queue: dict, now: dt.datetime, item_minutes: float = ITEM_MINUTES) -> List[Tuple[str, int]]:
    out = []
    for it in (queue or {}).get("items", []):
        if it.get("status") != "doing" or not it.get("started_at"):
            continue
        try:
            st = dt.datetime.fromisoformat(str(it["started_at"]))
        except ValueError:
            continue
        if st.tzinfo is None and now.tzinfo is not None:
            st = st.replace(tzinfo=now.tzinfo)
        mins = (now - st).total_seconds() / 60
        if mins > item_minutes:
            out.append((str(it.get("id") or it.get("item") or "?"), int(mins)))
    return out


def stuck_exit_code(rows: List[Tuple[str, int]]) -> int:
    return 1 if rows else 0


# ----------------------------------------------------------------- system access
def list_processes() -> List[dict]:
    if os.name == "nt":
        ps = ("Get-CimInstance Win32_Process | ForEach-Object { [pscustomobject]@{ pid=[int]$_.ProcessId; "
              "ppid=[int]$_.ParentProcessId; name=$_.Name; cmd=$_.CommandLine; "
              "age_min=$(if($_.CreationDate){((Get-Date)-$_.CreationDate).TotalMinutes}else{0}) } } "
              "| ConvertTo-Json -Compress")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        data = json.loads(r.stdout or "[]")
        if isinstance(data, dict):
            data = [data]
        return [{"pid": d["pid"], "ppid": d["ppid"], "name": d.get("name") or "",
                 "cmd": d.get("cmd") or "", "age_min": float(d.get("age_min") or 0)} for d in data]
    r = subprocess.run(["ps", "-eo", "pid=,ppid=,etimes=,comm=,args="], capture_output=True, text=True)
    procs = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        procs.append({"pid": int(parts[0]), "ppid": int(parts[1]), "age_min": int(parts[2]) / 60,
                      "name": os.path.basename(parts[3]), "cmd": parts[4] if len(parts) > 4 else parts[3]})
    return procs


def kill_pid(pid: int) -> bool:
    try:
        if os.name == "nt":
            return subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True).returncode == 0
        os.kill(pid, 9)
        return True
    except OSError:
        return False


def repo_paths() -> List[str]:
    paths = {str(ROOT)}
    parts = ROOT.parts
    for i in range(len(parts) - 2, 0, -1):          # worktree -> conductor tree
        if parts[i] == "work" and parts[i + 1] == "worktrees":
            paths.add(str(Path(*parts[:i])))
            break
    return sorted(paths)


def conductor_root() -> Path:
    return Path(min(repo_paths(), key=len))


def load_current_queue() -> Optional[dict]:
    work = conductor_root() / "work"
    cur = work / "current-run.txt"
    if not cur.exists():
        return None
    rid = cur.read_text(encoding="utf-8").strip()
    q = work / "runs" / rid / "queue.json"
    if not rid or not q.exists():
        return None
    try:
        return json.loads(q.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ----------------------------------------------------------------- commands
def _evaluate(under: Optional[str], grace: float = GRACE_MINUTES, stale: float = STALE_MINUTES):
    procs = list_processes()
    parent_of = {p["pid"]: p["ppid"] for p in procs}
    protected = ancestors(os.getpid(), parent_of)
    pids = set(parent_of)
    return [(p, *classify(p, repo_paths(), protected, pids, grace, stale, under)) for p in procs
            if is_watched_name(p["name"])]


def cmd_scan(args) -> int:
    rows = [r for r in _evaluate(None) if r[1]]
    if not rows:
        print("疑わしいプロセス: なし")
        return 0
    for p, _, reason, kind in rows:
        print(f"SUSPECT pid={p['pid']} name={p['name']} age={int(p['age_min'])}分 理由={kind}（{reason}）")
    return 0


def cmd_reap(args) -> int:
    under = args.under
    if under is not None and is_root_path(under):
        print("エラー: --under が空またはファイルシステムのルートです。何も終了しません。")
        return 2
    killed = 0
    for p, kill, reason, kind in _evaluate(under):
        if not kill:
            if kind == "" and reason in ("リポジトリのパスを含まない", "監視対象の名前でない"):
                continue
            print(f"KEEP  pid={p['pid']} name={p['name']} 理由={reason}")
            continue
        ok = kill_pid(p["pid"])
        killed += ok
        print(f"{'KILL' if ok else 'FAIL'}  pid={p['pid']} name={p['name']} 理由={kind}（{reason}）")
    print(f"終了したプロセス: {killed}")
    return 0


def cmd_stuck(args) -> int:
    q = load_current_queue()
    if q is None:
        return 0
    rows = stuck_items(q, dt.datetime.now().astimezone(), args.item_minutes)
    for iid, mins in rows:
        print(f"STUCK {iid} {mins}")
    return stuck_exit_code(rows)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="run 監視（scan / reap / stuck）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan").set_defaults(fn=cmd_scan)
    r = sub.add_parser("reap")
    r.add_argument("--under", default=None)
    r.set_defaults(fn=cmd_reap)
    s = sub.add_parser("stuck")
    s.add_argument("--item-minutes", type=float, default=ITEM_MINUTES)
    s.set_defaults(fn=cmd_stuck)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
