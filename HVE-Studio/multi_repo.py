"""FR-1099: one view over the repositories that make up one application.

Each repository's model stays its own (each repository is the source of truth for its data); for display they are
merged without mixing: every record ID gets the repository name as a prefix (`api:FR-001`, AC-537), every graph node
carries `repo`, and the release judgment is made per repository and then combined (AC-538).
"""
from __future__ import annotations

import re
from pathlib import Path

import release

LIMIT = 10  # PARAM-069: repositories in one group
# record IDs (FR-001, NFR-SEC-001, AC-001, G-001, E2E-001, Q-001, PARAM-001, SRC-001, AUD-001, INT-001 ...)
RECORD_ID = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+")


def repo_names(paths: list[str]) -> list[str]:
    """Display names: the folder name, made unique with the parent folder (then a number) when two collide."""
    names = []
    for p in paths:
        path = Path(p)
        name = path.name or str(path)
        if name in names or any(Path(q).name == name for q in paths if q != p):
            name = f"{path.parent.name}/{name}" if path.parent.name else name
        base, k = name, 2
        while name in names:
            name, k = f"{base}-{k}", k + 1
        names.append(name)
    return names


def _ids(model: dict) -> set[str]:
    ids = {n["id"] for n in (model.get("graph") or {}).get("nodes", [])}
    for r in model.get("reqs") or []:
        ids.add(r["id"])
        ids.update(a["id"] for a in r.get("acs", []))
    for key in ("goals", "questions", "params", "sources", "audits", "cases"):
        ids.update(str(x.get("id")) for x in model.get(key) or [] if x.get("id"))
    return {i for i in ids if RECORD_ID.fullmatch(i) or ":" in i}


def _prefix(value, ids: set[str], p: str):
    if isinstance(value, str):
        return p + value if value in ids else value
    if isinstance(value, list):
        return [_prefix(v, ids, p) for v in value]
    if isinstance(value, dict):
        return {(p + k if k in ids else k): _prefix(v, ids, p) for k, v in value.items()}
    return value


def _merge_into(out, add):
    if isinstance(out, list) and isinstance(add, list):
        out.extend(add)
        return out
    if isinstance(out, dict) and isinstance(add, dict):
        for k, v in add.items():
            out[k] = _merge_into(out[k], v) if k in out else v
        return out
    return out


def merge(entries: list[dict]) -> dict:
    """entries: [{"name", "path", "model"}] of the repositories that loaded; the first one is the primary."""
    merged: dict | None = None
    for e in entries:
        model = e["model"]
        p = e["name"] + ":"
        body = {k: v for k, v in model.items() if k not in ("meta", "release")}
        body = _prefix(body, _ids(model), p)
        for n in body.get("graph", {}).get("nodes", []):
            n["repo"] = e["name"]
            if n.get("label") and not str(n["label"]).startswith(p):
                n["label"] = p + str(n["label"])
        for r in body.get("reqs", []):
            r["repo"] = e["name"]
        if merged is None:
            merged = {**body, "meta": dict(model["meta"])}
        else:
            for k, v in body.items():
                merged[k] = _merge_into(merged[k], v) if k in merged else v
    assert merged is not None
    return merged


def group_release(entries: list[dict]) -> dict:
    per = [{"name": e["name"], "path": e["path"], "release": e["model"].get("release") or release.judge(e["model"])}
           for e in entries]
    combined = release.combine(per)
    items, goals, reasons = [], [], []
    for e, r in zip(entries, per):
        p = e["name"] + ":"
        items += [{**i, "id": p + i["id"], "refs": [p + x for x in i["refs"]], "repo": e["name"]} for i in r["release"]["items"]]
        goals += [{**g, "id": p + g["id"], "repo": e["name"]} for g in r["release"]["goals"]]
        reasons += [{**x, "repo": e["name"]} for x in r["release"]["reasons"]]
    items.sort(key=lambda it: (release.KIND_ORDER[it["kind"]],
                               release.SEVERE.index(it["severity"]) if it["kind"] == "question" else 0,
                               release._num_key(it["id"])))
    runs = [r["release"]["ledgerRunAt"] for r in per if r["release"].get("ledgerRunAt")]
    return {**combined, "items": items, "goals": goals, "reasons": reasons,
            "ledgerRunAt": max(runs) if runs else None, "modelAt": entries[0]["model"]["meta"].get("generatedAt"),
            "approvalRequests": sum(r["release"].get("approvalRequests", 0) for r in per)}
