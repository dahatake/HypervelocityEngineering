#!/usr/bin/env python3
"""kpi.py - KPIs of a conductor run and of the whole run history (users-guide/08-roadmap.md §8.2).

Usage:
  python scripts/kpi.py run [--run current|<run-id>] [--format md|json|html] [--out FILE]
  python scripts/kpi.py history [--format md|json|html] [--out FILE]

North Star: verified requirements per human intervention
  = (implemented requirements that are verified) / (human prompts recorded with `run-state.py human`).
A requirement is "verified" when it is approved, has a catalog row, none of its ACs is BLOCKED,
and every system-level AC has at least one System Test case and all of them are `pass` in the ledger.
Integration / unit ACs are covered by the implementer gate and verify, so they are not re-checked here.

Flow (speed) metrics come from the timestamps written by run-state.py / integrate.py: stage durations,
effective parallelism of the implementation loop (sum of item work time / wall time of stage 5),
serial integration time, and the models actually used by `task` calls (work/runs/<run-id>/models.jsonl, G-7).
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402

TARGET_FIRST_GATE = 0.70
TARGET_AC_PASS = 1.0
TARGET_TRACE = 1.0


def ratio(num: int, den: int) -> Optional[float]:
    return num / den if den else None


def pct(v: Optional[float]) -> str:
    return "-" if v is None else f"{v * 100:.0f}%"


def judge(v: Optional[float], target: float, higher_is_better: bool = True) -> str:
    if v is None:
        return "-"
    ok = v >= target if higher_is_better else v <= target
    return "達成" if ok else "未達"


def verified_requirements(root: Path, cfg: dict, req_ids: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """Returns (verified ids, {id: reason}) for the requirements that are not verified."""
    doc = h.parse_requirements(root, cfg)
    _, rows, _ = h.parse_catalog(root, cfg)
    catalog = h.catalog_req_rows(rows)
    cases = h.load_ledger(root, cfg).get("cases", [])
    ok, why = [], {}
    for rid in req_ids:
        req = doc.requirements.get(rid)
        if not req:
            why[rid] = "要求定義書にない"
            continue
        if req.state != "承認済み":
            why[rid] = f"決定状態が {req.state or '不明'}"
            continue
        if rid not in catalog:
            why[rid] = "カタログの行がない"
            continue
        acs = [doc.acs[a] for a in req.acs if a in doc.acs]
        blocked = [a.id for a in acs if a.blocked]
        if blocked:
            why[rid] = "BLOCKED の AC: " + ",".join(blocked)
            continue
        bad = []
        for ac in acs:
            if ac.level != "system":
                continue
            mine = [c for c in cases if ac.id in c.get("ac_ids", [])]
            if not mine or any(c.get("status") != "pass" for c in mine):
                bad.append(ac.id)
        if bad:
            why[rid] = "System Test が pass でない AC: " + ",".join(bad)
            continue
        ok.append(rid)
    return ok, why


def traceability(root: Path, cfg: dict) -> Tuple[int, int, int, int]:
    """(approved requirements with catalog row and ledger cases for every system AC, approved requirements,
        system ACs that pass, system ACs)."""
    doc = h.parse_requirements(root, cfg)
    _, rows, _ = h.parse_catalog(root, cfg)
    catalog = h.catalog_req_rows(rows)
    cases = h.load_ledger(root, cfg).get("cases", [])
    covered_acs = {a for c in cases for a in c.get("ac_ids", [])}
    passed = {a for c in cases if c.get("status") == "pass" for a in c.get("ac_ids", [])}
    approved = [r for r in doc.requirements.values() if r.state == "承認済み"]
    sys_acs = h.system_acs(doc)
    traced = 0
    for r in approved:
        need = [a.id for a in sys_acs if a.requirement == r.id]
        if r.id in catalog and all(a in covered_acs for a in need):
            traced += 1
    return traced, len(approved), sum(1 for a in sys_acs if a.id in passed), len(sys_acs)


def open_questions(root: Path, cfg: dict) -> int:
    doc = h.parse_requirements(root, cfg)
    return sum(1 for q in doc.questions.values() if not q.get("answered"))


def resolve_run(root: Path, cfg: dict, name: Optional[str]) -> str:
    if name in (None, "", "current"):
        rid = h.current_run(root, cfg)
        if rid:
            return rid
        runs = h.work_dir(root, cfg) / "runs"
        cands = sorted((p for p in runs.iterdir() if (p / "meta.json").exists()), key=lambda p: p.name) if runs.is_dir() else []
        if not cands:
            raise SystemExit("ERROR kpi: run がありません（work/runs/<run-id>/meta.json）")
        return cands[-1].name
    if not (h.run_dir(root, cfg, name) / "meta.json").exists():
        raise SystemExit(f"ERROR kpi: run {name} がありません")
    return name


def hours_between(meta: dict) -> float:
    import datetime as dt
    try:
        start = dt.datetime.fromisoformat(meta["started_at"])
        end = dt.datetime.fromisoformat(meta["finished_at"]) if meta.get("finished_at") else dt.datetime.now().astimezone()
        return (end - start).total_seconds() / 3600
    except Exception:
        return 0.0


def _ts(s: Optional[str]):
    import datetime as dt
    try:
        return dt.datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


def flow(root: Path, cfg: dict, rid: str, meta: dict, items: List[dict]) -> dict:
    import datetime as dt
    now = dt.datetime.now().astimezone()
    stages = {}
    for n, t in (meta.get("stage_times") or {}).items():
        a, b = _ts(t.get("start")), _ts(t.get("done"))
        if a:
            stages[n] = round(((b or now) - a).total_seconds() / 60, 1)
    work = [float(it.get("work_sec", 0)) for it in items if it.get("work_sec")]
    integ = [float(it.get("integrate_sec", 0)) for it in items if it.get("integrate_sec")]
    loop_min = stages.get("5")
    if loop_min is None:
        starts = [x for x in (_ts(it.get("first_started_at")) for it in items) if x]
        ends = [x for x in (_ts(it.get("finished_at")) for it in items) if x]
        loop_min = round((max(ends) - min(starts)).total_seconds() / 60, 1) if starts and ends else None
    models: Dict[str, Dict[str, int]] = {}
    mp = h.run_dir(root, cfg, rid) / "models.jsonl"
    if mp.exists():
        for line in h.read_text(mp).splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            per = models.setdefault(e.get("agent") or "?", {})
            per[e.get("model") or "?"] = per.get(e.get("model") or "?", 0) + 1
    return {
        "stage_minutes": stages,
        "loop_minutes": loop_min,
        "item_work_minutes_avg": round(sum(work) / len(work) / 60, 1) if work else None,
        "parallelism": round(sum(work) / 60 / loop_min, 2) if work and loop_min else None,
        "integrate_minutes": round(sum(integ) / 60, 1) if integ else None,
        "integrate_share": round(sum(integ) / 60 / loop_min, 2) if integ and loop_min else None,
        "parallel_workers": meta.get("options", {}).get("parallel_workers"),
        "models": models,
    }


def run_kpis(root: Path, cfg: dict, rid: str) -> dict:
    meta = h.load_meta(root, cfg, rid)
    items = h.load_queue(root, cfg, rid).get("items", [])
    done = [it for it in items if it.get("status") == "done"]
    blocked = [it for it in items if it.get("status") == "blocked"]
    impl = sorted({r for it in done for r in it.get("requirement_ids", [])})
    verified, why = verified_requirements(root, cfg, impl)
    human = meta.get("human_interventions")
    n_human = len(human) if isinstance(human, list) else None
    first_ok = sum(1 for it in done if it.get("attempts", 0) <= 1)
    traced, approved, ac_pass, ac_total = traceability(root, cfg)
    hours = hours_between(meta)
    return {
        "run_id": rid, "status": meta.get("status"), "result": meta.get("result"),
        "toolkit": meta.get("toolkit"), "elapsed_hours": round(hours, 2),
        "human_interventions": n_human,
        "human_breakdown": _breakdown(human) if isinstance(human, list) else {},
        "implemented": impl, "verified": verified, "not_verified": why,
        "nsm": round(len(verified) / n_human, 2) if n_human else None,
        "items": {"total": len(items), "done": len(done), "blocked": len(blocked)},
        "first_gate": {"pass": first_ok, "total": len(done), "rate": ratio(first_ok, len(done))},
        "ac_pass": {"pass": ac_pass, "total": ac_total, "rate": ratio(ac_pass, ac_total)},
        "traceability": {"traced": traced, "total": approved, "rate": ratio(traced, approved)},
        "hours_per_requirement": round(hours / len(impl), 2) if impl else None,
        "open_questions": open_questions(root, cfg),
        "flow": flow(root, cfg, rid, meta, items),
    }


def _breakdown(human: List[dict]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for e in human:
        k = e.get("kind", "?")
        out[k] = out.get(k, 0) + 1
    return out


def run_rows(k: dict) -> List[Tuple[str, str, str, str, str]]:
    hb = "、".join(f"{a} {b}" for a, b in k["human_breakdown"].items()) or "-"
    return [
        ("North Star: 人の介入 1 回あたりの検証済み要求", "-" if k["nsm"] is None else f"{k['nsm']:.2f}",
         "前回より増やす", "-", f"検証済み要求 {len(k['verified'])} ÷ 人の介入 {k['human_interventions'] if k['human_interventions'] is not None else '未記録'}"),
        ("人の介入", "未記録" if k["human_interventions"] is None else str(k["human_interventions"]),
         "1（回答があれば 2）", judge(k["human_interventions"], 2, False) if k["human_interventions"] is not None else "-", hb),
        ("検証済み要求 / 実装した要求", f"{len(k['verified'])}/{len(k['implemented'])}", "全件",
         "-" if not k["implemented"] else ("達成" if len(k["verified"]) == len(k["implemented"]) else "未達"),
         "; ".join(f"{a}: {b}" for a, b in k["not_verified"].items()) or "-"),
        ("1 回目のゲート通過率", f"{pct(k['first_gate']['rate'])}（{k['first_gate']['pass']}/{k['first_gate']['total']}）",
         pct(TARGET_FIRST_GATE) + " 以上", judge(k["first_gate"]["rate"], TARGET_FIRST_GATE), "attempts が 1 以下で done になった項目"),
        ("system AC の pass 率", f"{pct(k['ac_pass']['rate'])}（{k['ac_pass']['pass']}/{k['ac_pass']['total']}）",
         pct(TARGET_AC_PASS), judge(k["ac_pass"]["rate"], TARGET_AC_PASS), "承認済み・BLOCKED でない system AC"),
        ("トレーサビリティ網羅率", f"{pct(k['traceability']['rate'])}（{k['traceability']['traced']}/{k['traceability']['total']}）",
         pct(TARGET_TRACE), judge(k["traceability"]["rate"], TARGET_TRACE), "承認済み要求のうち、カタログ行があり system AC がすべて台帳にあるもの"),
        ("要求 1 件あたりの経過時間", "-" if k["hours_per_requirement"] is None else f"{k['hours_per_requirement']}h",
         "Phase 1 の計測値より短く", "-", f"経過 {k['elapsed_hours']}h ÷ 実装 {len(k['implemented'])} 件"),
        ("項目の完了 / BLOCKED", f"{k['items']['done']}/{k['items']['total']}（BLOCKED {k['items']['blocked']}）", "BLOCKED 0", 
         "-" if not k["items"]["total"] else ("達成" if k["items"]["blocked"] == 0 else "未達"), "queue.json"),
        ("未回答の質問票", str(k["open_questions"]), "-", "-", "次の Prompt の <answers> で回答する"),
    ] + flow_rows(k.get("flow") or {})


def flow_rows(f: dict) -> List[Tuple[str, str, str, str, str]]:
    if not f:
        return []
    rs_stages = {"1": "要求定義", "2": "独立監査", "3": "計画", "4": "System Test の設計", "5": "実装ループ", "6": "最終"}
    st = "、".join(f"{rs_stages.get(n, n)} {m} 分" for n, m in sorted(f["stage_minutes"].items())) or "未記録"
    par, pw = f.get("parallelism"), f.get("parallel_workers")
    try:
        pw_n = float(pw) if pw else None
    except ValueError:
        pw_n = None
    models = "; ".join(f"{a}: " + ", ".join(f"{m}×{n}" for m, n in per.items()) for a, per in sorted(f["models"].items())) or "未記録"
    return [
        ("工程ごとの時間", st, "-", "-", "meta.json の stage_times"),
        ("実効の並列度（実装ループ）", "-" if par is None else f"{par}", f"parallel_workers（{pw or '-'}）の 70% 以上",
         "-" if par is None or not pw_n else judge(par / pw_n, 0.7), "項目の作業時間の合計 ÷ 実装ループの経過時間"),
        ("項目 1 件あたりの作業時間", "-" if f["item_work_minutes_avg"] is None else f"{f['item_work_minutes_avg']} 分", "-", "-",
         "queue.json の work_sec（doing の間の時間）"),
        ("統合の直列時間", "-" if f["integrate_minutes"] is None else f"{f['integrate_minutes']} 分（ループの {pct(f['integrate_share'])}）",
         "ループの 20% 以下", "-" if f["integrate_share"] is None else judge(f["integrate_share"], 0.2, False), "integrate.py merge の所要時間の合計"),
        ("実際に使ったモデル", models, "ebak.config.json の models と一致", "-", "models.jsonl（G-7）"),
    ]


def parse_history(root: Path, cfg: dict) -> List[Dict[str, str]]:
    p = root / h.mf(cfg, "run_history")
    if not p.exists():
        return []
    out = []
    for t in h.parse_tables(h.read_text(p).splitlines()):
        if t.col("run-id") is None:
            continue
        for _, cells in t.rows:
            row = {t.header[i]: (cells[i].strip() if i < len(cells) else "") for i in range(len(t.header))}
            if row.get("run-id"):
                out.append(row)
    return out


def _frac(s: str) -> Tuple[int, int]:
    m = re.search(r"(\d+)\s*/\s*(\d+)", s or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _int(s: str) -> Optional[int]:
    m = re.fullmatch(r"\s*(\d+)\s*", s or "")
    return int(m.group(1)) if m else None


def _hours(s: str) -> Optional[float]:
    m = re.search(r"([\d.]+)\s*h", s or "")
    return float(m.group(1)) if m else None


def _reqs(s: str) -> int:
    return len(h.REQ_ID_RE.findall(s or ""))


def history_kpis(rows: List[Dict[str, str]]) -> dict:
    n = len(rows)
    complete = sum(1 for r in rows if r.get("結果", "").startswith("全件完了"))
    fg = [_frac(r.get("1 回目のゲート通過率", "")) for r in rows]
    fg_num, fg_den = sum(a for a, _ in fg), sum(b for _, b in fg)
    humans = [(_int(r.get("人の介入", "")), _frac(r.get("検証済み要求", ""))[0]) for r in rows]
    measured = [(hn, v) for hn, v in humans if hn]
    hours = [(_hours(r.get("経過時間", "")), _reqs(r.get("実装した要求 ID", ""))) for r in rows]
    h_sum = sum(x for x, k in hours if x is not None and k)
    r_sum = sum(k for x, k in hours if x is not None and k)
    last_ac = _frac(rows[-1].get("AC pass 率", "")) if rows else (0, 0)
    return {
        "runs": n,
        "unattended_completion": {"complete": complete, "total": n, "rate": ratio(complete, n)},
        "first_gate": {"pass": fg_num, "total": fg_den, "rate": ratio(fg_num, fg_den)},
        "human": {"runs_measured": len(measured), "total": sum(a for a, _ in measured),
                  "mean": round(sum(a for a, _ in measured) / len(measured), 2) if measured else None},
        "verified_total": sum(v for _, v in measured),
        "nsm": round(sum(v for _, v in measured) / sum(a for a, _ in measured), 2) if measured else None,
        "hours_per_requirement": round(h_sum / r_sum, 2) if r_sum else None,
        "last_ac_pass": {"pass": last_ac[0], "total": last_ac[1], "rate": ratio(*last_ac)},
        "credits_recorded": sum(1 for r in rows if r.get("AI クレジット") not in ("", "未取得", "-", None)),
    }


def history_rows(k: dict) -> List[Tuple[str, str, str, str, str]]:
    return [
        ("North Star: 人の介入 1 回あたりの検証済み要求", "-" if k["nsm"] is None else f"{k['nsm']:.2f}", "増加傾向", "-",
         f"検証済み要求 {k['verified_total']} ÷ 人の介入 {k['human']['total']}（介入を記録した run {k['human']['runs_measured']} 件）"),
        ("無人完走率", f"{pct(k['unattended_completion']['rate'])}（{k['unattended_completion']['complete']}/{k['unattended_completion']['total']}）",
         "80% 以上", judge(k["unattended_completion"]["rate"], 0.8), "結果が「全件完了」の run の割合"),
        ("run あたりの人の介入（平均）", "-" if k["human"]["mean"] is None else str(k["human"]["mean"]), "2 以下",
         judge(k["human"]["mean"], 2, False), "run-state.py human の記録"),
        ("1 回目のゲート通過率", f"{pct(k['first_gate']['rate'])}（{k['first_gate']['pass']}/{k['first_gate']['total']}）",
         pct(TARGET_FIRST_GATE) + " 以上", judge(k["first_gate"]["rate"], TARGET_FIRST_GATE), "全 run の合計"),
        ("要求 1 件あたりの経過時間", "-" if k["hours_per_requirement"] is None else f"{k['hours_per_requirement']}h",
         "短縮傾向", "-", "経過時間の合計 ÷ 実装した要求の数"),
        ("直近の AC pass 率", f"{pct(k['last_ac_pass']['rate'])}（{k['last_ac_pass']['pass']}/{k['last_ac_pass']['total']}）",
         pct(TARGET_AC_PASS), judge(k["last_ac_pass"]["rate"], TARGET_AC_PASS), "最後の run"),
        ("AI クレジットを記録した run", f"{k['credits_recorded']}/{k['runs']}", "全件", 
         "-" if not k["runs"] else ("達成" if k["credits_recorded"] == k["runs"] else "未達"), "run-state.py finish --credits"),
    ]


HEAD = ("指標", "値", "目標", "判定", "根拠・内訳")


def to_md(title: str, rows: List[Tuple[str, ...]]) -> str:
    out = [f"## {title}", "", "| " + " | ".join(HEAD) + " |", "|" + "---|" * len(HEAD)]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "／") for c in r) + " |")
    return "\n".join(out) + "\n"


def to_html(title: str, rows: List[Tuple[str, ...]]) -> str:
    esc = html.escape
    body = "".join("<tr>" + "".join(
        f'<td class="{"ok" if c == "達成" else "ng" if c == "未達" else ""}">{esc(str(c))}</td>' for c in r) + "</tr>\n" for r in rows)
    return (f"<!doctype html>\n<html lang=\"ja\"><head><meta charset=\"utf-8\"><title>{esc(title)}</title>\n"
            "<style>body{font-family:system-ui,sans-serif;margin:2em}table{border-collapse:collapse}"
            "td,th{border:1px solid #ccc;padding:.4em .7em;vertical-align:top}th{background:#f3f3f3}"
            ".ok{color:#116611;font-weight:bold}.ng{color:#b00020;font-weight:bold}</style></head><body>\n"
            f"<h1>{esc(title)}</h1>\n<table><tr>" + "".join(f"<th>{esc(x)}</th>" for x in HEAD) + "</tr>\n"
            f"{body}</table>\n</body></html>\n")


def emit(fmt: str, title: str, data: dict, rows: List[Tuple[str, ...]], out: Optional[str]) -> None:
    if fmt == "json":
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    elif fmt == "html":
        text = to_html(title, rows)
    else:
        text = to_md(title, rows)
    if out:
        h.write_text_atomic(Path(out), text)
        print(f"kpi: {Path(out).as_posix()}")
    else:
        sys.stdout.write(text)


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--run", default="current")
    hi = sub.add_parser("history")
    for p in (r, hi):
        p.add_argument("--format", choices=("md", "json", "html"), default="md")
        p.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    root = h.conductor_root(root, h.load_config(root))
    cfg = h.load_config(root)
    if args.cmd == "run":
        rid = resolve_run(root, cfg, args.run)
        k = run_kpis(root, cfg, rid)
        emit(args.format, f"KPI（run {rid}）", k, run_rows(k), args.out)
    else:
        k = history_kpis(parse_history(root, cfg))
        emit(args.format, f"KPI（実行履歴 {k['runs']} 件）", k, history_rows(k), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
