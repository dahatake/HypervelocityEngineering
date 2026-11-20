"""FR-1095: the release judgment derived only from the loaded model (goals, approved requirements, ledger, questions).

Goal verdict (section 1.2 of the requirements): all linked system cases `pass` -> met; any `fail`/`blocked` -> unmet
(wins over everything else); otherwise any `not_run` (or another status) -> undetermined; no case at all ->
undetermined with nothing to judge.  Overall state: one or more action items -> "action"; otherwise any reason the
judgment cannot be completed -> "unknown"; otherwise "ok".  "ok" is never reported when the judgment is incomplete.
"""
from __future__ import annotations

import re

SEVERE = ("重大", "高")
ANSWERED = ("回答済み", "解消", "取り下げ", "廃止", "不要")
KIND_ORDER = {"fail": 0, "blocked": 1, "stalled": 2, "question": 3, "not_run": 4}
_UPPER = re.compile(r"上位\s*[:：]\s*([^\n　]*)")


def _num_key(s: str):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", s or "")]


def goals_of(req: dict) -> list[str]:
    m = _UPPER.search(req.get("body") or "")
    found = re.findall(r"G-\d{3,}", m.group(1)) if m else []
    if not found and re.fullmatch(r"G-\d{3,}", req.get("goal") or ""):
        found = [req["goal"]]
    return list(dict.fromkeys(found))


def _live(ac: dict) -> bool:
    return not (ac.get("text") or "").lstrip().startswith(("（廃止", "(廃止"))


def _approved(req: dict) -> bool:
    return req.get("statusKind") == "approved"


def _cases_for(cases: list[dict], ac_ids: set[str], req_id: str | None = None) -> list[dict]:
    out = []
    for c in cases:
        acs = set(c.get("ac_ids") or [])
        if acs & ac_ids or (req_id and not acs and req_id in (c.get("requirement_ids") or [])):
            out.append(c)
    return out


def _verdict(statuses: list[str]) -> str:
    if not statuses:
        return "none"
    if any(s in ("fail", "blocked") for s in statuses):
        return "unmet"
    if all(s == "pass" for s in statuses):
        return "met"
    return "undetermined"


def _open_question(q: dict) -> bool:
    state = q.get("state") or ""
    return q.get("severity") in SEVERE and not state.startswith(ANSWERED)


def judge(model: dict) -> dict:
    meta = model.get("meta") or {}
    reasons: list[dict] = []
    if meta.get("error"):
        reasons.append({"code": "load-failed", "detail": str(meta.get("error"))})
    files = meta.get("files") or {}
    if not files.get("ledger"):
        reasons.append({"code": "no-ledger"})
    goals = model.get("goals") or []
    if not goals:
        reasons.append({"code": "no-goals"})
    reqs = [r for r in model.get("reqs") or [] if _approved(r)]
    cases = model.get("cases") or []

    goal_rows = []
    for g in goals:
        linked = [r for r in reqs if g["id"] in goals_of(r)]
        system_acs = {a["id"] for r in linked for a in r.get("acs", []) if _live(a) and (a.get("level") or "") == "system"}
        gcases = _cases_for(cases, system_acs)
        statuses = [c.get("status") or "not_run" for c in gcases]
        verdict = _verdict(statuses)
        if verdict == "none":
            reasons.append({"code": "goal-without-cases", "goal": g["id"]})
        goal_rows.append({"id": g["id"], "title": g.get("title") or "", "verdict": verdict,
                          "requirements": [r["id"] for r in linked], "cases": [c.get("id") for c in gcases],
                          "counts": {s: statuses.count(s) for s in sorted(set(statuses))}})

    items: list[dict] = []
    approved_acs = {a["id"]: r["id"] for r in reqs for a in r.get("acs", []) if _live(a)}
    seen_cases = set()
    for c in cases:
        status = c.get("status") or "not_run"
        linked = [a for a in (c.get("ac_ids") or []) if a in approved_acs]
        if not linked and not (set(c.get("requirement_ids") or []) & {r["id"] for r in reqs}):
            continue
        if status in ("fail", "blocked", "not_run") and c.get("id") not in seen_cases:
            seen_cases.add(c.get("id"))
            items.append({"kind": status, "id": c.get("id"), "title": c.get("title") or "",
                          "refs": linked or list(c.get("requirement_ids") or [])})
    for r in reqs:
        for a in r.get("acs", []):
            note = a.get("blocked") or ""
            if note or re.search(r"\bTBD\b", a.get("text") or ""):
                items.append({"kind": "stalled", "id": a["id"], "title": note or "TBD", "refs": [r["id"]]})
    for q in model.get("questions") or []:
        if _open_question(q):
            items.append({"kind": "question", "id": q["id"], "title": q.get("question") or "", "severity": q.get("severity"),
                          "refs": []})
    items.sort(key=lambda it: (KIND_ORDER[it["kind"]],
                               SEVERE.index(it["severity"]) if it["kind"] == "question" else 0, _num_key(it["id"])))

    if items:
        state = "action"
    elif reasons:
        state = "unknown"
    else:
        state = "ok"
    runs = [c.get("last_run_at") for c in cases if c.get("last_run_at")]
    approvals = sum(1 for r in model.get("reqs") or [] if (r.get("status") or "").startswith("承認待ち"))
    return {"state": state, "reasons": reasons, "goals": goal_rows, "items": items,
            "ledgerRunAt": max(runs) if runs else None, "modelAt": meta.get("generatedAt"),
            "approvalRequests": approvals}


def combine(per_repo: list[dict]) -> dict:
    """AC-538: overall state of a repository group. Any "action" -> action; else any "unknown" -> unknown; else ok."""
    states = [r["release"]["state"] for r in per_repo]
    state = "action" if "action" in states else "unknown" if "unknown" in states or not states else "ok"
    return {"state": state, "repos": [{"name": r["name"], "path": r["path"], "state": r["release"]["state"],
                                       "reasons": r["release"]["reasons"], "items": len(r["release"]["items"])}
                                      for r in per_repo]}
