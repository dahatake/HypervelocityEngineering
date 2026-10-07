#!/usr/bin/env python3
"""run-state.py - run state under /work/runs/<run-id>/ for the conductor (plan §7.5, §7.6, §8.3).

Usage:
  python scripts/run-state.py start [--options-file F | --options "max_hours: 24\\n..."] [--new]
  python scripts/run-state.py status                       # resume summary (read this first in a new context)
  python scripts/run-state.py stage N [--done]             # 0 init,1 RD,2 audit,3 plan,4 ST design,5 impl,6 final
  python scripts/run-state.py progress "text"              # append one entry (<= 3 lines) to progress.md
  python scripts/run-state.py queue add --id I-01 --req FR-001 [--ac AC-001] [--boundary B] [--depends I-00] [--shared X] [--summary S]
  python scripts/run-state.py queue set I-01 [--status todo|doing|done|blocked] [--attempts +1] [--branch B] [--summary S]
  python scripts/run-state.py queue ready [--parallel 3]   # items that can start now (deps done, no shared boundary)
  python scripts/run-state.py queue show
  python scripts/run-state.py time                         # elapsed / max_hours; exit 3 when >= 85 %
  python scripts/run-state.py complete-check               # exit 0 only when the run may end (§8.3)
  python scripts/run-state.py finish [--result "..."] [--credits "..."]   # append docs/run-history.md, close the run
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hvelib as h  # noqa: E402

STAGES = {0: "初期化", 1: "要求定義", 2: "独立監査", 3: "計画", 4: "System Test の設計", 5: "実装ループ", 6: "最終"}
DEFAULT_OPTIONS = {
    "max_hours": "24", "approval_policy": "安全範囲は推奨どおり", "parallel_workers": "3",
    "scope": "承認済みすべて", "git_push": "しない", "deploy": "しない", "paid_services": "使わない",
    "external_exposure": "公開しない",
}
HISTORY_HEADER = (
    "# 実行履歴\n\n"
    "conductor の 1 回の実行を 1 行で記録します（工程 6 で `scripts/run-state.py finish` が追記します）。"
    "`/work` の一時ファイルが消えても、実行の結果と KPI をここで追えます。\n\n"
    "| run-id | 開始 | 終了 | HEAD | 結果 | 実装した要求 ID | BLOCKED | AC pass 率 | 経過時間 | 1 回目のゲート通過率 | AI クレジット |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|\n"
)


def ctx(args):
    root = Path(args.root).resolve() if args.root else h.repo_root()
    root = h.conductor_root(root, h.load_config(root))
    cfg = h.load_config(root)
    return root, cfg


def need_run(root, cfg) -> str:
    rid = h.current_run(root, cfg)
    if not rid or not (h.run_dir(root, cfg, rid) / "meta.json").exists():
        raise SystemExit("ERROR run-state: 実行中の run がありません。`run-state.py start` で始めます")
    return rid


def parse_ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def elapsed_hours(meta: dict) -> float:
    try:
        start = parse_ts(meta["started_at"])
    except Exception:
        return 0.0
    return (dt.datetime.now().astimezone() - start).total_seconds() / 3600


def counts(queue: dict) -> Dict[str, int]:
    c = {"todo": 0, "doing": 0, "done": 0, "blocked": 0}
    for it in queue.get("items", []):
        c[it.get("status", "todo")] = c.get(it.get("status", "todo"), 0) + 1
    return c


def cmd_start(args) -> int:
    root, cfg = ctx(args)
    rid = h.current_run(root, cfg)
    if rid and not args.new and (h.run_dir(root, cfg, rid) / "meta.json").exists():
        meta = h.load_meta(root, cfg, rid)
        if meta.get("status") == "active":
            print(f"RESUME {rid}")
            return cmd_status(args)
    text = ""
    if args.options_file:
        text = h.read_text(Path(args.options_file))
    elif args.options:
        text = args.options.replace("\\n", "\n")
    opts = dict(DEFAULT_OPTIONS)
    opts.update(h.parse_options_text(text))
    rid = h.new_run_id()
    rdir = h.run_dir(root, cfg, rid)
    n = 1
    while rdir.exists():
        rid = f"{h.new_run_id()}-{n}"
        rdir = h.run_dir(root, cfg, rid)
        n += 1
    for sub in ("evidence", "audit", "logs"):
        (rdir / sub).mkdir(parents=True, exist_ok=True)
    branch = start_branch = h.current_branch(root)
    branch_msg = ""
    if branch in (cfg.get("base_branch", "main"), "master") and not args.no_branch:
        rc, out = h.git(["switch", "-c", f"run/{rid}"], root)
        if rc == 0:
            branch_msg = f"integration branch: run/{rid}（{branch} からの作業ブランチ）"
            branch = f"run/{rid}"
        else:
            branch_msg = f"WARN 統合ブランチを作れませんでした: {out.strip()[:200]}"
    meta = {
        "run_id": rid, "status": "active", "started_at": h.now_iso(), "finished_at": None,
        "head_at_start": h.head_commit(root), "branch_at_start": start_branch,
        "integration_branch": branch, "options": opts, "stage": 0,
        "stages_done": [], "ledger_strict": False, "session_id": None, "toolkit": h.TOOLKIT_VERSION,
    }
    h.save_meta(root, cfg, rid, meta)
    h.write_json(rdir / "queue.json", {"run_id": rid, "items": []})
    h.write_text_atomic(rdir / "progress.md", f"# progress {rid}\n\n")
    h.write_text_atomic(h.work_dir(root, cfg) / "current-run.txt", rid + "\n")
    print(f"START {rid}")
    print(f"dir: {rdir.relative_to(root).as_posix()}")
    if branch_msg:
        print(branch_msg)
    print("options: " + ", ".join(f"{k}={v}" for k, v in opts.items()))
    return 0


def cmd_status(args) -> int:
    root, cfg = ctx(args)
    rid = h.current_run(root, cfg)
    if not rid:
        print("run: なし（新しい実行として始めます: run-state.py start）")
        return 0
    meta = h.load_meta(root, cfg, rid)
    q = h.load_queue(root, cfg, rid)
    c = counts(q)
    mh = float(meta.get("options", {}).get("max_hours", 24) or 24)
    el = elapsed_hours(meta)
    print(f"run: {rid} status={meta.get('status')} stage={meta.get('stage')}({STAGES.get(meta.get('stage'), '?')}) done={meta.get('stages_done')}")
    print(f"time: {el:.1f}h / {mh:g}h ({el / mh * 100:.0f}%)  branch={h.current_branch(root)} HEAD={h.head_commit(root)}")
    print(f"queue: todo={c['todo']} doing={c['doing']} done={c['done']} blocked={c['blocked']}")
    for it in q.get("items", []):
        if it.get("status") in ("doing", "todo"):
            print(f"  {it['id']} {it.get('status')} req={','.join(it.get('requirement_ids', []))} deps={','.join(it.get('depends_on', [])) or '-'} attempts={it.get('attempts', 0)} branch={it.get('branch') or '-'}")
    prog = h.run_dir(root, cfg, rid) / "progress.md"
    if prog.exists():
        lines = [l for l in h.read_text(prog).splitlines() if l.strip()][-args.tail:]
        print("progress (tail):")
        for l in lines:
            print("  " + l)
    return 0


def cmd_stage(args) -> int:
    root, cfg = ctx(args)
    rid = need_run(root, cfg)
    meta = h.load_meta(root, cfg, rid)
    n = args.n
    if n not in STAGES:
        raise SystemExit("ERROR run-state: stage は 0〜6 です")
    if args.done:
        if n not in meta["stages_done"]:
            meta["stages_done"].append(n)
        if n == 4:
            meta["ledger_strict"] = True
        msg = f"工程{n} {STAGES[n]} 完了"
    else:
        meta["stage"] = n
        if n == 1:
            meta["ledger_strict"] = False
            meta["stages_done"] = [s for s in meta["stages_done"] if s < 1]
        msg = f"工程{n} {STAGES[n]} 開始"
    h.save_meta(root, cfg, rid, meta)
    append_progress(root, cfg, rid, meta, msg)
    print(msg)
    return 0


def append_progress(root, cfg, rid, meta, text: str) -> None:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()][:3]
    if not lines:
        return
    ts = dt.datetime.now().strftime("%m-%d %H:%M")
    entry = f"- {ts} [工程{meta.get('stage', '?')}] " + lines[0][:300] + "".join("\n  " + l[:300] for l in lines[1:]) + "\n"
    p = h.run_dir(root, cfg, rid) / "progress.md"
    with open(p, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(entry)


def cmd_progress(args) -> int:
    root, cfg = ctx(args)
    rid = need_run(root, cfg)
    append_progress(root, cfg, rid, h.load_meta(root, cfg, rid), args.text)
    return 0


def ids(v) -> List[str]:
    return [x for x in re.split(r"[,\s]+", v or "") if x]


def save_queue(root, cfg, rid, q) -> None:
    h.write_json(h.run_dir(root, cfg, rid) / "queue.json", q)


def cmd_queue(args) -> int:
    root, cfg = ctx(args)
    rid = need_run(root, cfg)
    q = h.load_queue(root, cfg, rid)
    items = q.setdefault("items", [])
    by_id = {it["id"]: it for it in items}
    if args.qcmd == "add":
        if args.id in by_id:
            raise SystemExit(f"ERROR run-state: {args.id} は既にあります")
        reqs = ids(args.req)
        if not 1 <= len(reqs) <= 3:
            raise SystemExit("ERROR run-state: 1 項目の要求 ID は 1〜3 個です（§7.3）")
        for d in ids(args.depends):
            if d not in by_id:
                raise SystemExit(f"ERROR run-state: 依存先 {d} がありません")
        items.append({
            "id": args.id, "requirement_ids": reqs, "ac_ids": ids(args.ac), "boundary": args.boundary or "",
            "shared": ids(args.shared), "depends_on": ids(args.depends), "status": "todo", "attempts": 0,
            "branch": None, "summary": args.summary or "",
        })
        save_queue(root, cfg, rid, q)
        print(f"added {args.id}")
        return 0
    if args.qcmd == "set":
        it = by_id.get(args.id)
        if not it:
            raise SystemExit(f"ERROR run-state: {args.id} がありません")
        if args.status:
            if args.status not in ("todo", "doing", "done", "blocked"):
                raise SystemExit("ERROR run-state: status は todo/doing/done/blocked です")
            it["status"] = args.status
        if args.attempts:
            it["attempts"] = it.get("attempts", 0) + int(args.attempts[1:]) if args.attempts.startswith("+") else int(args.attempts)
        if args.branch is not None:
            it["branch"] = args.branch or None
        if args.summary is not None:
            it["summary"] = args.summary
        save_queue(root, cfg, rid, q)
        print(f"{args.id}: status={it['status']} attempts={it.get('attempts', 0)} branch={it.get('branch') or '-'}")
        return 0
    if args.qcmd == "ready":
        doing = [it for it in items if it.get("status") == "doing"]
        busy = set()
        for it in doing:
            busy |= {it.get("boundary")} | set(it.get("shared", []))
        busy.discard("")
        out = []
        slots = max(args.parallel - len(doing), 0)
        for it in items:
            if len(out) >= slots:
                break
            if it.get("status") != "todo":
                continue
            if any(by_id.get(d, {}).get("status") != "done" for d in it.get("depends_on", [])):
                continue
            keys = ({it.get("boundary")} | set(it.get("shared", []))) - {""}
            if keys & busy:
                continue
            busy |= keys
            out.append(it)
        for it in out:
            print(f"{it['id']}\treq={','.join(it['requirement_ids'])}\tac={','.join(it.get('ac_ids', []))}\tboundary={it.get('boundary') or '-'}")
        if not out:
            print("ready: なし")
        return 0
    for it in items:
        print(f"{it['id']}\t{it.get('status')}\treq={','.join(it.get('requirement_ids', []))}\tdeps={','.join(it.get('depends_on', [])) or '-'}\tattempts={it.get('attempts', 0)}\t{it.get('summary', '')}")
    c = counts(q)
    print(f"queue: todo={c['todo']} doing={c['doing']} done={c['done']} blocked={c['blocked']}")
    return 0


def cmd_time(args) -> int:
    root, cfg = ctx(args)
    rid = need_run(root, cfg)
    meta = h.load_meta(root, cfg, rid)
    mh = float(meta.get("options", {}).get("max_hours", 24) or 24)
    el = elapsed_hours(meta)
    pct = el / mh * 100
    print(f"elapsed={el:.2f}h max_hours={mh:g} used={pct:.0f}%{' -> 新しい項目を始めず工程 6 へ' if pct >= 85 else ''}")
    return 3 if pct >= 85 else 0


def completion(root, cfg, rid) -> List[str]:
    meta = h.load_meta(root, cfg, rid)
    q = h.load_queue(root, cfg, rid)
    c = counts(q)
    reasons = []
    if c["todo"] or c["doing"]:
        reasons.append(f"queue に todo={c['todo']} doing={c['doing']} が残っています")
    if 6 not in meta.get("stages_done", []):
        reasons.append("工程 6（最終）が終わっていません")
    if not (h.run_dir(root, cfg, rid) / "run-report.md").exists():
        reasons.append("run-report.md がありません")
    if not q.get("items") and 3 not in meta.get("stages_done", []):
        reasons.append("工程 3（計画）が終わっていません")
    return reasons


def cmd_complete_check(args) -> int:
    root, cfg = ctx(args)
    rid = h.current_run(root, cfg)
    if not rid:
        print("complete: 実行中の run はありません")
        return 0
    reasons = completion(root, cfg, rid)
    if reasons:
        print("incomplete: " + " / ".join(reasons))
        return 1
    print(f"complete: {rid}")
    return 0


def cmd_finish(args) -> int:
    root, cfg = ctx(args)
    rid = need_run(root, cfg)
    reasons = completion(root, cfg, rid)
    if reasons and not args.force:
        raise SystemExit("ERROR run-state: 完了条件を満たしていません: " + " / ".join(reasons))
    meta = h.load_meta(root, cfg, rid)
    q = h.load_queue(root, cfg, rid)
    done = [it for it in q.get("items", []) if it.get("status") == "done"]
    blocked = [it for it in q.get("items", []) if it.get("status") == "blocked"]
    impl = sorted({r for it in done for r in it.get("requirement_ids", [])})
    first_gate = f"{sum(1 for it in done if it.get('attempts', 0) <= 1)}/{len(done)}" if done else "-"
    doc = h.parse_requirements(root, cfg)
    ledger = h.load_ledger(root, cfg)
    sys_acs = [a.id for a in h.system_acs(doc)]
    passed = {a for c in ledger.get("cases", []) if c.get("status") == "pass" for a in c.get("ac_ids", [])}
    ac_rate = f"{sum(1 for a in sys_acs if a in passed)}/{len(sys_acs)}" if sys_acs else "-"
    el = elapsed_hours(meta)
    result = args.result or ("全件完了" if not blocked else "blocked あり")
    meta.update({"status": "finished", "finished_at": h.now_iso(), "result": result})
    h.save_meta(root, cfg, rid, meta)
    hist = root / h.mf(cfg, "run_history")
    text = h.read_text(hist) if hist.exists() else HISTORY_HEADER
    if re.search(rf"^\|\s*{re.escape(rid)}\s*\|", text, re.M):
        print(f"run-history: {rid} は既に記録されています")
    else:
        row = (f"| {rid} | {meta['started_at'][:16]} | {meta['finished_at'][:16]} | {h.head_commit(root)} | {result} | "
               f"{', '.join(impl) or '-'} | {len(blocked)} | {ac_rate} | {el:.1f}h | {first_gate} | {args.credits or '未取得'} |")
        if not text.endswith("\n"):
            text += "\n"
        h.write_text_atomic(hist, text + row + "\n")
        print("run-history: " + row)
    cur = h.work_dir(root, cfg) / "current-run.txt"
    if cur.exists() and h.read_text(cur).strip() == rid:
        cur.unlink()
    print(f"finished {rid}: {result}")
    return 0


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--options-file")
    s.add_argument("--options")
    s.add_argument("--new", action="store_true")
    s.add_argument("--no-branch", action="store_true", help="main 上でも統合ブランチを作らない")
    s.add_argument("--tail", type=int, default=8)
    st = sub.add_parser("status")
    st.add_argument("--tail", type=int, default=8)
    sg = sub.add_parser("stage")
    sg.add_argument("n", type=int)
    sg.add_argument("--done", action="store_true")
    p = sub.add_parser("progress")
    p.add_argument("text")
    q = sub.add_parser("queue")
    qs = q.add_subparsers(dest="qcmd", required=True)
    qa = qs.add_parser("add")
    qa.add_argument("--id", required=True)
    qa.add_argument("--req", required=True)
    qa.add_argument("--ac", default="")
    qa.add_argument("--boundary", default="")
    qa.add_argument("--shared", default="", help="共通部品・テーブルなど、並行させない対象（カンマ区切り）")
    qa.add_argument("--depends", default="")
    qa.add_argument("--summary", default="")
    qset = qs.add_parser("set")
    qset.add_argument("id")
    qset.add_argument("--status")
    qset.add_argument("--attempts")
    qset.add_argument("--branch")
    qset.add_argument("--summary")
    qr = qs.add_parser("ready")
    qr.add_argument("--parallel", type=int, default=3)
    qs.add_parser("show")
    sub.add_parser("time")
    sub.add_parser("complete-check")
    f = sub.add_parser("finish")
    f.add_argument("--result")
    f.add_argument("--credits")
    f.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    return {"start": cmd_start, "status": cmd_status, "stage": cmd_stage, "progress": cmd_progress,
            "queue": cmd_queue, "time": cmd_time, "complete-check": cmd_complete_check,
            "finish": cmd_finish}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
