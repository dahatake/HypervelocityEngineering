"""EABK Studio: reads the EABK data layer of any repository and builds one model.

Only the data layer is read (requirements definition, catalog, system-test ledger,
ID registry, run history). Source code is never opened; it is only *named* by the
paths that the catalog already holds.
"""
from __future__ import annotations

import json
import hashlib
import re
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path

STUDIO_VERSION = "1.0.0"

DEFAULT_FILES = {
    "requirements": "docs/requirements-definition.md",
    "requirements_dir": "docs/requirements",
    "catalog": "docs/catalog.md",
    "id_registry": "docs/id-registry.md",
    "run_history": "docs/run-history.md",
    "ledger": "tests/system/ledger.json",
    "manual_tests": "docs/manual-tests.md",
}
CONFIG_CANDIDATES = ("scripts/ebak.config.json", "scripts/hve.config.json")

REQ_ID = r"(?:FR-\d{3,}|FR-[A-Z][A-Z0-9_-]*|NFR-[A-Z0-9]+-\d{3,})"
REQ_ID_RE = re.compile(r"(?<![A-Za-z0-9\-])(" + REQ_ID + r")(?![0-9])")
ANY_ID_RE = re.compile(r"(?<![A-Za-z0-9\-])((?:FR|AC|G|Q|PARAM|SRC|E2E|IT|AUD|NFR-[A-Z0-9]+)-\d{3,})(?![0-9])")
REQ_HEADING_RE = re.compile(r"^(#{2,6})\s+\**(" + REQ_ID + r")\**\s*(.*)$")
AC_HEADING_RE = re.compile(r"^(#{2,6})\s+\**(AC-(?:\d{3,}|[A-Z][A-Z0-9_-]*))\**\s*(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
RANGE_RE = re.compile(
    r"(?<![A-Za-z0-9\-])((?:FR|NFR-[A-Z0-9]+)-)(\d{3,})\s*[〜~～]\s*(?:(?:FR|NFR-[A-Z0-9]+)-)?(\d{3,})")
LIST_RE = re.compile(
    r"(?<![A-Za-z0-9\-])((?:FR|NFR-[A-Z0-9]+)-)(\d{3,})((?:\s*[・,、，]\s*\d{3,}(?![0-9\-]))+)")
KEYS = ("決定状態", "出自", "優先度", "上位", "出典", "対象エンティティ", "関係する状態", "参照パラメータ", "関連する既存資産")
KEY_RE = re.compile(r"(?:(?<=^)|(?<=[\s　]))(" + "|".join(KEYS) + r")\s*[:：]")
TOP_KEY_RE = re.compile(
    r"^[-*]\s+(要求|" + "|".join(KEYS) + r"|受入基準(?:\s+(?:AC-(?:\d{3,}|[A-Z][A-Z0-9_-]*)))?)\s*[:：]\s*(.*)$")
AC_BULLET_RE = re.compile(r"^[-*]\s+(?:受入基準\s*)?\**(AC-(?:\d{3,}|[A-Z][A-Z0-9_-]*))\**\s*[:：]\s*(.*)$")
SUB_RE = re.compile(r"^\s{2,}[-*]\s+(検証レベル|BLOCKED)\s*[:：]\s*(.*)$")
NONE_WORDS = {"", "なし", "無し", "-", "—", "–", "n/a", "N/A", "未実装", "未設定", "tbd", "TBD"}

STATUS_KINDS = (
    ("承認済み", "approved"), ("AI提案", "proposed"), ("保留", "hold"),
    ("却下", "rejected"), ("廃止", "retired"),
)
TOP_DIRS = {"src", "app", "apps", "packages", "services", "lib", "libs", "modules", "internal", "cmd", "pkg", "projects"}
TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs"}


def norm(s: str) -> str:
    return re.sub(r"[\s　]+", "", s or "")


def strip_md(s: str) -> str:
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s or "")
    return s.replace("**", "").replace("`", "").strip()


def status_kind(s: str) -> str:
    for head, kind in STATUS_KINDS:
        if (s or "").startswith(head):
            return kind
    return "unknown"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells, cur, tick = [], [], False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            cur.append("|")
            i += 2
            continue
        if ch == "`":
            tick = not tick
        if ch == "|" and not tick:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    cells.append("".join(cur).strip())
    return cells


def parse_document(path: Path, rel: str) -> dict:
    """Headings, tables and raw lines of one markdown file (code fences skipped)."""
    lines = read_text(path).splitlines()
    headings, tables = [], []
    fence = False
    i = 0
    h_stack: list[tuple[int, str]] = []
    while i < len(lines):
        ln = lines[i]
        if ln.lstrip().startswith("```"):
            fence = not fence
            i += 1
            continue
        if fence:
            i += 1
            continue
        m = HEADING_RE.match(ln)
        if m:
            lvl = len(m.group(1))
            h_stack = [h for h in h_stack if h[0] < lvl] + [(lvl, strip_md(m.group(2)))]
            headings.append((i + 1, lvl, strip_md(m.group(2))))
            i += 1
            continue
        if ln.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", lines[i + 1]) and "-" in lines[i + 1]:
            header = [strip_md(c) for c in split_row(ln)]
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                cells = split_row(lines[j])
                rows.append({"cells": cells, "line": j + 1})
                j += 1
            tables.append({"file": rel, "line": i + 1, "header": header,
                           "key": [norm(h) for h in header],
                           "section": " / ".join(h[1] for h in h_stack), "rows": rows})
            i = j
            continue
        i += 1
    return {"rel": rel, "lines": lines, "headings": headings, "tables": tables}


def expand_ids(text: str, known: set[str] | None = None) -> list[str]:
    """Requirement IDs in text, expanding 'FR-102〜104' and 'FR-105・131・132'."""
    out: OrderedDict[str, None] = OrderedDict()
    for m in RANGE_RE.finditer(text or ""):
        pre, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        width = len(m.group(2))
        if 0 <= b - a <= 400:
            for n in range(a, b + 1):
                rid = f"{pre}{n:0{width}d}"
                if known is None or rid in known:
                    out[rid] = None
    for m in LIST_RE.finditer(text or ""):
        pre, first, rest = m.group(1), m.group(2), m.group(3)
        for n in [first] + re.findall(r"\d{3,}", rest):
            rid = f"{pre}{n}"
            if known is None or rid in known:
                out[rid] = None
    for m in REQ_ID_RE.finditer(text or ""):
        rid = m.group(1)
        if known is None or rid in known:
            out[rid] = None
    return list(out)


def split_items(cell: str, seps: str = ",、，;；") -> list[str]:
    """Split a cell by , 、 ， ; outside of parentheses/backticks."""
    items, cur, depth, tick = [], [], 0, False
    for ch in cell or "":
        if ch == "`":
            tick = not tick
        if not tick and ch in "（(":
            depth += 1
        elif not tick and ch in "）)":
            depth = max(0, depth - 1)
        if ch in seps and depth == 0 and not tick:
            items.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    items.append("".join(cur).strip())
    return [strip_md(x) for x in items if strip_md(x)]


def path_tokens(cell: str) -> list[str]:
    out = []
    for item in split_items(cell):
        base = re.sub(r"[（(].*$", "", item).strip()
        base = base.replace("\\", "/")
        base = re.sub(r"^\./", "", base)
        base = re.sub(r":\d+(-\d+)?$", "", base)
        if " " in base or base in NONE_WORDS:
            continue
        if "/" in base or re.search(r"\.[A-Za-z0-9]{1,6}$", base):
            out.append(base)
    return out


def is_test_path(p: str) -> bool:
    parts = p.lower().split("/")
    name = parts[-1]
    return (parts[0] in TEST_DIRS or any(x in TEST_DIRS for x in parts[:-1])
            or bool(re.search(r"(tests?|spec)\.[a-z0-9]+$|^test_|_test\.", name)))


def component_of(p: str) -> tuple[str, str]:
    """(component, module) of a repository path."""
    parts = [x for x in p.split("/") if x]
    dirs = parts[:-1] if len(parts) > 1 else []
    if not dirs:
        return "(root)", "(root)"
    if dirs[0] in TOP_DIRS and len(dirs) >= 2:
        comp = f"{dirs[0]}/{dirs[1]}"
        rest = dirs[2:]
    elif dirs[0] in TEST_DIRS and len(dirs) >= 2:
        comp = f"{dirs[0]}/{dirs[1]}"
        rest = dirs[2:]
    else:
        comp = dirs[0]
        rest = dirs[1:]
    mod = comp + ("/" + rest[0] if rest else "")
    return comp, mod


def alias_set(name: str) -> set[str]:
    base = re.sub(r"[（(].*?[）)]", "", name).strip()
    al = {norm(name).lower(), norm(base).lower()}
    for piece in re.split(r"\s*/\s*", base):
        if piece.strip():
            al.add(norm(piece).lower())
    return {a for a in al if a}


def load_config(root: Path) -> dict:
    files = dict(DEFAULT_FILES)
    for cand in CONFIG_CANDIDATES:
        p = root / cand
        if p.is_file():
            try:
                data = json.loads(read_text(p))
                files.update({k: v for k, v in (data.get("management_files") or {}).items() if isinstance(v, str)})
            except ValueError:
                pass
            break
    return files


def find_root(start: Path) -> Path:
    start = start.resolve()
    for cand in [start, *start.parents]:
        if (cand / "docs" / "requirements-definition.md").is_file() or (cand / "docs" / "catalog.md").is_file():
            return cand
    return start


def has_data_layer(root: Path) -> bool:
    files = load_config(root)
    return any((root / files[k]).exists() for k in ("requirements", "catalog", "ledger"))


def data_layer_report(root: Path) -> dict:
    """Which data-layer files exist under root and how many records were parsed (used by --check)."""
    root = Path(root).resolve()
    files = load_config(root)
    rdir = root / files["requirements_dir"]
    entries = [{"key": k, "path": v, "exists": (root / v).exists()} for k, v in files.items()]
    model = build_model(root)
    return {
        "root": str(root),
        "ok": has_data_layer(root),
        "files": entries,
        "boundaryFiles": len(list(rdir.glob("*.md"))) if rdir.is_dir() else 0,
        "counts": {
            "requirements": len(model["reqs"]),
            "acceptanceCriteria": sum(len(r["acs"]) for r in model["reqs"]),
            "catalogFeatures": len(model["catalog"]["features"]),
            "ledgerCases": len(model["cases"]),
            "runs": len(model["runs"]),
        },
        "warnings": list(model["warnings"]),
    }


def fingerprint(root: Path) -> str:
    files = load_config(root)
    stamps = []
    paths = [root / files[k] for k in ("requirements", "catalog", "ledger", "id_registry", "run_history")]
    rd = root / files["requirements_dir"]
    if rd.is_dir():
        paths += sorted(rd.glob("*.md"))
    for p in paths:
        try:
            st = p.stat()
            stamps.append(f"{p.name}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            stamps.append(f"{p.name}:-")
    return "|".join(stamps)


def generated_at(root: Path) -> str:
    files = load_config(root)
    paths = [root / files[k] for k in ("requirements", "catalog", "ledger", "id_registry", "run_history")]
    rd = root / files["requirements_dir"]
    if rd.is_dir():
        paths += sorted(rd.glob("*.md"))
    stamps = [path.stat().st_mtime for path in paths if path.is_file()]
    value = max(stamps, default=root.stat().st_mtime)
    return datetime.fromtimestamp(value).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- requirements
def parse_requirements(doc: dict) -> list[dict]:
    lines, reqs = doc["lines"], []
    i, n, fence = 0, len(lines), False
    while i < n:
        ln = lines[i]
        if ln.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else REQ_HEADING_RE.match(ln)
        if not m:
            i += 1
            continue
        level, rid, title = len(m.group(1)), m.group(2), strip_md(m.group(3))
        j = i + 1
        block = []
        while j < n:
            h = HEADING_RE.match(lines[j])
            if h and len(h.group(1)) <= level:
                break
            if REQ_HEADING_RE.match(lines[j]):
                break
            block.append((j + 1, lines[j]))
            j += 1
        reqs.append(parse_req_block(rid, title, doc["rel"], i + 1, block))
        i = j
    return reqs


def parse_req_block(rid: str, title: str, rel: str, line: int, block: list[tuple[int, str]]) -> dict:
    kind = "FR" if rid.startswith("FR-") else "NFR"
    cat = "" if kind == "FR" else rid.split("-")[1]
    r = {"id": rid, "kind": kind, "cat": cat, "title": title, "text": "", "status": "", "statusKind": "unknown",
         "origin": "", "priority": "", "priorityNote": "", "goal": "", "sources": "", "entities": [], "states": [],
         "params": [], "assets": "", "relation": "", "acs": [], "blocked": [], "file": rel, "line": line, "body": ""}
    cur_key, cur_ac, texts = None, None, []
    body = []
    for ln_no, raw in block:
        body.append(raw)
        line_s = raw.rstrip()
        relation = re.match(r"^[-*]\s+関係\s*[:：]\s*(.*)$", line_s)
        if relation:
            value = strip_md(relation.group(1))
            r["relation"] = "" if value in NONE_WORDS else value
            continue
        sub = SUB_RE.match(line_s)
        if sub and cur_ac is not None:
            if sub.group(1) == "検証レベル":
                cur_ac["level"] = strip_md(sub.group(2)).split()[0].lower() if strip_md(sub.group(2)) else ""
            else:
                cur_ac["blocked"] = strip_md(sub.group(2))
            continue
        acb = AC_BULLET_RE.match(line_s)
        if acb:
            cur_ac = {"id": acb.group(1), "text": strip_md(acb.group(2)), "level": "", "blocked": "", "line": ln_no}
            r["acs"].append(cur_ac)
            cur_key = "ac"
            continue
        top = TOP_KEY_RE.match(line_s)
        if top:
            key, rest = top.group(1), top.group(2)
            if key == "要求":
                cur_key = "text"
                texts.append(rest)
                cur_ac = None
            elif key.startswith("受入基準"):
                cur_key = "ac"
            else:
                cur_key = "kv"
                cur_ac = None
                first = f"{key}: {rest}"
                apply_kv(r, first)
            continue
        if cur_key == "text":
            texts.append(raw.strip())
        elif cur_key == "ac" and cur_ac is not None and line_s.strip():
            cur_ac["text"] = (cur_ac["text"] + " " + strip_md(line_s.strip())).strip()
        elif cur_key == "kv" and line_s.strip().startswith(("-", "*")) is False and line_s.strip():
            pass
    r["text"] = strip_md(" ".join(t for t in texts if t))
    r["body"] = "\n".join(body).strip()
    r["statusKind"] = status_kind(r["status"])
    for ac in r["acs"]:
        for q in re.findall(r"Q-\d{3,}", ac["blocked"]):
            if q not in r["blocked"]:
                r["blocked"].append(q)
    return r


def apply_kv(r: dict, text: str) -> None:
    marks = list(KEY_RE.finditer(text))
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        key, val = m.group(1), text[m.end():end].strip(" 　")
        val = strip_md(val)
        if key == "決定状態":
            r["status"] = val
        elif key == "出自":
            r["origin"] = val
        elif key == "優先度":
            mm = re.match(r"(MUST|SHOULD|MAY|COULD|WON'T)", val, re.I)
            r["priority"] = mm.group(1).upper() if mm else val.split("（")[0]
            r["priorityNote"] = val
        elif key == "上位":
            gm = re.search(r"G-\d{3,}", val)
            r["goal"] = gm.group(0) if gm else val
        elif key == "出典":
            r["sources"] = val
        elif key == "対象エンティティ":
            r["entities"] = [e for e in split_items(val, ",、，;；・/／") if e not in NONE_WORDS]
        elif key == "関係する状態":
            r["states"] = [] if val in NONE_WORDS else [val]
        elif key == "参照パラメータ":
            r["params"] = re.findall(r"PARAM-\d{3,}", val)
        elif key == "関連する既存資産":
            r["assets"] = "" if val in NONE_WORDS else val


# --------------------------------------------------------------------------- states
def parse_state_machines(tables: list[dict]) -> list[dict]:
    machines: OrderedDict[str, dict] = OrderedDict()
    for t in tables:
        if "対象エンティティ" not in t["key"] or "状態" not in t["key"]:
            continue
        ei, si = t["key"].index("対象エンティティ"), t["key"].index("状態")
        ci = next((k for k, h in enumerate(t["key"]) if h.startswith("遷移")), None)
        prev: dict[str, list[str]] = {}
        for row in t["rows"]:
            c = row["cells"]
            if len(c) <= max(ei, si):
                continue
            ent = strip_md(c[ei])
            cond = strip_md(c[ci]) if ci is not None and ci < len(c) else ""
            m = machines.setdefault(ent, {"entity": ent, "states": [], "transitions": [], "file": t["file"], "line": row["line"]})
            cell = strip_md(c[si])
            segments = [s for s in re.split(r"[。\n]", cell) if s.strip()]
            multi = any(("→" in s or "／" in s) for s in segments)
            if multi:
                for k, seg in enumerate(segments):
                    chain(m, seg, cond if k == 0 else "")
                prev[ent] = []
            else:
                name = cell.split("（")[0].strip()
                add_state(m, name)
                for p in prev.get(ent, []):
                    add_trans(m, p, name, cond)
                prev[ent] = [name]
    return list(machines.values())


def add_state(m: dict, name: str) -> None:
    if name and name not in m["states"]:
        m["states"].append(name)


def add_trans(m: dict, a: str, b: str, label: str) -> None:
    if a and b and a != b and not any(t["from"] == a and t["to"] == b for t in m["transitions"]):
        m["transitions"].append({"from": a, "to": b, "label": label})


def chain(m: dict, seg: str, label: str) -> None:
    groups = [[strip_md(x).split("（")[0].strip() for x in re.split(r"[／/]", g) if x.strip()] for g in seg.split("→")]
    prev: list[str] = []
    for gi, g in enumerate(groups):
        for s in g:
            add_state(m, s)
        for p in prev:
            for s in g:
                add_trans(m, p, s, label if gi == 1 else "")
        prev = g


# --------------------------------------------------------------------------- main build
def build_model(root: Path) -> dict:
    root = Path(root).resolve()
    files = load_config(root)
    warnings: list[str] = []
    model: dict = {
        "meta": {"repo": str(root), "name": root.name, "studio": STUDIO_VERSION,
                 "generatedAt": generated_at(root), "files": {}, "fingerprint": fingerprint(root)},
        "goals": [], "reqs": [], "params": [], "terms": [], "stateMachines": [], "personas": [], "integrations": [],
        "questions": [], "decisions": [], "audits": [], "sources": [], "scenarios": [], "catalog": {"features": [], "apis": [], "tables": [], "parts": []},
        "cases": [], "caseDigests": {}, "runs": [], "registry": [], "registryRecords": [],
        "analysis": {"structure": {"layers": [], "differences": []}, "runtime": {}, "history": []},
        "graph": {"nodes": [], "edges": []}, "warnings": warnings,
    }
    rd_path = root / files["requirements"]
    cat_path = root / files["catalog"]
    docs: list[dict] = []
    if rd_path.is_file():
        docs.append(parse_document(rd_path, files["requirements"]))
    rdir = root / files["requirements_dir"]
    if rdir.is_dir():
        for p in sorted(rdir.glob("*.md")):
            docs.append(parse_document(p, f"{files['requirements_dir']}/{p.name}"))
    cat_doc = parse_document(cat_path, files["catalog"]) if cat_path.is_file() else None
    model["meta"]["files"] = {k: (v if (root / v).exists() else None) for k, v in files.items()}
    if not docs and not cat_doc:
        model["meta"]["error"] = "no-data-layer"
        return model

    # requirements
    reqs: OrderedDict[str, dict] = OrderedDict()
    for d in docs:
        for r in parse_requirements(d):
            if r["id"] in reqs:
                warnings.append(f"duplicate {r['id']} ({d['rel']}:{r['line']})")
                continue
            reqs[r["id"]] = r
    all_tables = [t for d in docs for t in d["tables"]]
    # Compact/synthetic repositories may declare goals and external boundaries as bullets.
    for d in docs:
        for line_no, raw in enumerate(d["lines"], 1):
            goal = re.match(r"^[-*]\s+目的\s+(G-[A-Z0-9_-]+)\s*[:：]\s*(.*)$", raw)
            if goal and not any(g["id"] == goal.group(1) for g in model["goals"]):
                model["goals"].append({"id": goal.group(1), "title": strip_md(goal.group(2)),
                                       "metric": "", "method": "", "file": d["rel"], "line": line_no})
            external = re.match(r"^[-*]\s+外部連携\s+([A-Za-z0-9_-]+)\s*[:：]\s*(.*)$", raw)
            if external:
                model["integrations"].append({"name": external.group(1), "method": strip_md(external.group(2)),
                                              "meaning": strip_md(external.group(2)), "owner": "", "numbering": "",
                                              "file": d["rel"], "line": line_no})
    for t in all_tables:  # index tables supply priority / group when the heading lacks them
        if "要求ID" in t["key"] and "題名" in t["key"] and "所属ファイル" in t["key"]:
            idx = {h: k for k, h in enumerate(t["key"])}
            for row in t["rows"]:
                c = row["cells"]
                rid = strip_md(c[idx["要求ID"]]) if len(c) > idx["要求ID"] else ""
                if rid in reqs:
                    r = reqs[rid]
                    if "優先度" in idx and not r["priority"] and len(c) > idx["優先度"]:
                        r["priority"] = strip_md(c[idx["優先度"]])
                    if "決定状態" in idx and not r["status"] and len(c) > idx["決定状態"]:
                        r["status"] = strip_md(c[idx["決定状態"]])
                        r["statusKind"] = status_kind(r["status"])
    # index-only requirements (table rows without a heading block)
    for t in all_tables:
        if "要求ID" in t["key"] and "題名" in t["key"] and ("所属ファイル" in t["key"] or "優先度" in t["key"]):
            idx = {h: k for k, h in enumerate(t["key"])}
            for row in t["rows"]:
                c = row["cells"]
                rid = strip_md(c[0])
                if REQ_ID_RE.fullmatch(rid) and rid not in reqs and len(c) > idx["題名"]:
                    kind = "FR" if rid.startswith("FR-") else "NFR"
                    st = strip_md(c[idx["決定状態"]]) if "決定状態" in idx and len(c) > idx["決定状態"] else ""
                    reqs[rid] = {"id": rid, "kind": kind, "cat": "" if kind == "FR" else rid.split("-")[1],
                                 "title": strip_md(c[idx["題名"]]), "text": "", "status": st, "statusKind": status_kind(st),
                                 "origin": "", "priority": strip_md(c[idx["優先度"]]) if "優先度" in idx and len(c) > idx["優先度"] else "",
                                 "priorityNote": "", "goal": "", "sources": "", "entities": [], "states": [], "params": [],
                                 "assets": "", "relation": "", "acs": [], "blocked": [], "file": t["file"], "line": row["line"], "body": ""}

    # generic ID tables
    for t in all_tables:
        if not t["rows"]:
            continue
        first = t["key"][0] if t["key"] else ""
        h = t["header"]
        for row in t["rows"]:
            c = row["cells"] + [""] * (len(h) - len(row["cells"]))
            rec = {h[k] or f"c{k}": strip_md(c[k]) for k in range(len(h))}
            rec["_line"], rec["_file"] = row["line"], t["file"]
            cid = strip_md(c[0])
            if first == "ID" and re.fullmatch(r"G-\d{3,}", cid):
                model["goals"].append({"id": cid, "title": c[1] and strip_md(c[1]), "metric": strip_md(c[2]) if len(c) > 2 else "",
                                       "method": strip_md(c[3]) if len(c) > 3 else "", "file": t["file"], "line": row["line"]})
            elif first == "ID" and re.fullmatch(r"PARAM-\d{3,}", cid):
                model["params"].append({"id": cid, "name": rec.get("名前", ""), "value": rec.get("値", ""), "unit": rec.get("単位", ""),
                                        "basis": rec.get("根拠", ""), "status": rec.get("決定状態", ""), "file": t["file"], "line": row["line"]})
            elif first == "ID" and re.fullmatch(r"Q-\d{3,}", cid):
                model["questions"].append({"id": cid, "severity": rec.get("重要度", ""), "question": rec.get("質問", ""),
                                           "options": rec.get("選択肢", ""), "recommend": rec.get("推奨", ""),
                                           "state": rec.get("状態", ""), "answer": rec.get("回答", ""), "file": t["file"], "line": row["line"]})
            elif first == "ID" and re.fullmatch(r"SRC-\d{3,}", cid):
                model["sources"].append({"id": cid, "title": rec.get("資料", ""), "version": rec.get("版・日付", ""),
                                         "kind": rec.get("区分", ""), "file": t["file"], "line": row["line"]})
            elif first == "ID" and re.fullmatch(r"AUD-\d{3,}", cid):
                model["audits"].append({"id": cid, "date": rec.get("日付", ""), "category": rec.get("カテゴリ", ""),
                                        "severity": rec.get("重大度", ""), "where": rec.get("位置", ""),
                                        "summary": rec.get("要約", ""), "state": rec.get("状態", ""), "file": t["file"], "line": row["line"]})
        if first == "用語":
            for row in t["rows"]:
                c = row["cells"] + ["", "", ""]
                model["terms"].append({"term": strip_md(c[0]), "definition": strip_md(c[1]), "forbidden": strip_md(c[2]),
                                       "file": t["file"], "line": row["line"]})
        elif first == "ペルソナ" and "業務" in t["key"] and not any(p["name"] == strip_md(t["rows"][0]["cells"][0]) for p in model["personas"]):
            idx = {k: i for i, k in enumerate(t["key"])}
            for row in t["rows"]:
                c = row["cells"] + [""] * len(t["key"])
                model["personas"].append({"name": strip_md(c[0]), "work": strip_md(c[idx["業務"]]),
                                          "decision": strip_md(c[idx["主要な判断"]]) if "主要な判断" in idx else "",
                                          "data": strip_md(c[idx["使うデータ"]]) if "使うデータ" in idx else "",
                                          "role": strip_md(c[idx["役割"]]) if "役割" in idx else "",
                                          "file": t["file"], "line": row["line"]})
        elif first == "連携先":
            for row in t["rows"]:
                c = row["cells"] + [""] * 5
                model["integrations"].append({"name": strip_md(c[0]), "method": strip_md(c[1]), "meaning": strip_md(c[2]),
                                              "owner": strip_md(c[3]), "numbering": strip_md(c[4]), "file": t["file"], "line": row["line"]})
        elif first == "日付" and any(k.startswith("対象ID") for k in t["key"]):
            for row in t["rows"]:
                c = row["cells"] + [""] * 5
                model["decisions"].append({"date": strip_md(c[0]), "target": strip_md(c[1]), "decision": strip_md(c[2]),
                                           "basis": strip_md(c[3]), "run": strip_md(c[4]), "file": t["file"], "line": row["line"]})
    model["stateMachines"] = parse_state_machines(all_tables)
    for d in docs[:1]:
        for ln, lvl, text in d["headings"]:
            if re.match(r"^(\d+\.\s*)?利用シナリオ", text):
                k = d["lines"][ln:]
                for raw in k:
                    if HEADING_RE.match(raw):
                        break
                    mm = re.match(r"^[-*]\s+(.*?)[:：]\s*(.*)$", raw)
                    if mm:
                        model["scenarios"].append({"name": strip_md(mm.group(1)), "text": strip_md(mm.group(2)), "file": d["rel"], "line": ln})

    # catalog
    parts: list[dict] = []
    if cat_doc:
        for t in cat_doc["tables"]:
            k = t["key"]
            if "要求ID" in k and "実装ファイル" in k:
                idx = {h: i for i, h in enumerate(k)}
                for row in t["rows"]:
                    c = row["cells"] + [""] * len(k)
                    rid = strip_md(c[idx["要求ID"]])
                    if not REQ_ID_RE.fullmatch(rid):
                        continue
                    impl_raw = strip_md(c[idx["実装ファイル"]])
                    model["catalog"]["features"].append({
                        "req": rid, "title": strip_md(c[idx["題名"]]) if "題名" in idx else "",
                        "status": strip_md(c[idx["決定状態"]]) if "決定状態" in idx else "",
                        "impl": path_tokens(c[idx["実装ファイル"]]), "implRaw": impl_raw,
                        "tests": path_tokens(c[idx["テスト"]]) if "テスト" in idx else [],
                        "parts": split_items(c[idx["使っている共通部品"]]) if "使っている共通部品" in idx else [],
                        "line": row["line"]})
            elif "名前" in k and "定義ファイル" in k:
                for row in t["rows"]:
                    c = row["cells"] + ["", "", ""]
                    if strip_md(c[0]):
                        model["catalog"]["apis"].append({"name": strip_md(c[0]), "files": path_tokens(c[1]), "reqRaw": strip_md(c[2]), "line": row["line"]})
            elif "テーブル名" in k and "定義ファイル" in k:
                idx = {h: i for i, h in enumerate(k)}
                for row in t["rows"]:
                    c = row["cells"] + [""] * len(k)
                    if strip_md(c[0]):
                        model["catalog"]["tables"].append({
                            "name": strip_md(c[0]), "files": path_tokens(c[idx["定義ファイル"]]),
                            "owner": strip_md(c[idx["正本のシステム"]]) if "正本のシステム" in idx else "",
                            "reqRaw": strip_md(c[idx["関連する要求ID"]]) if "関連する要求ID" in idx else "", "line": row["line"]})
            elif "部品名" in k:
                idx = {h: i for i, h in enumerate(k)}
                for row in t["rows"]:
                    c = row["cells"] + [""] * len(k)
                    if strip_md(c[0]):
                        parts.append({"name": strip_md(c[0]), "files": path_tokens(c[idx["ファイル"]]) if "ファイル" in idx else [],
                                      "purpose": strip_md(c[idx["用途"]]) if "用途" in idx else "",
                                      "reqRaw": strip_md(c[idx["使っている要求ID"]]) if "使っている要求ID" in idx else "", "line": row["line"]})
    known = set(reqs)
    for p in parts:
        p["reqs"] = expand_ids(p.pop("reqRaw"), known)
    for a in model["catalog"]["apis"]:
        a["reqs"] = expand_ids(a.pop("reqRaw"), known)
    for tb in model["catalog"]["tables"]:
        tb["reqs"] = expand_ids(tb.pop("reqRaw"), known)
    model["catalog"]["parts"] = parts

    # ledger / registry / run history
    lp = root / files["ledger"]
    if lp.is_file():
        try:
            ledger_text = read_text(lp)
            data = json.loads(ledger_text)
            model["caseDigests"] = data.get("ac_digests", {}) if isinstance(data.get("ac_digests", {}), dict) else {}
            search_from = 0
            for c in data.get("cases", []):
                case = {k: c.get(k) for k in ("id", "requirement_ids", "ac_ids", "title", "layer", "command",
                                              "canary", "status", "last_commit", "last_run_at", "evidence")}
                encoded_id = json.dumps(c.get("id"), ensure_ascii=False)
                match = re.search(r'"id"\s*:\s*' + re.escape(encoded_id), ledger_text[search_from:])
                if match:
                    absolute = search_from + match.start()
                    case["line"] = ledger_text.count("\n", 0, absolute) + 1
                    search_from += match.end()
                else:
                    case["line"] = 1
                model["cases"].append(case)
        except ValueError:
            warnings.append("ledger is not valid JSON")
    rp = root / files["id_registry"]
    if rp.is_file():
        reg = parse_document(rp, files["id_registry"])
        cnt: Counter = Counter()
        for t in reg["tables"]:
            if len(t["key"]) >= 3 and t["key"][:2] == ["ID", "種別"] and t["key"][2] in ("状態", "使用状態"):
                for row in t["rows"]:
                    if len(row["cells"]) > 2:
                        rid = strip_md(row["cells"][0])
                        kind, state = strip_md(row["cells"][1]), strip_md(row["cells"][2])
                        cnt[(kind, state)] += 1
                        model["registryRecords"].append(
                            {"id": rid, "kind": kind, "state": state,
                             "file": files["id_registry"], "line": row["line"]}
                        )
        model["registry"] = [{"kind": k, "state": s, "count": n} for (k, s), n in sorted(cnt.items())]
    hp = root / files["run_history"]
    if hp.is_file():
        rh = parse_document(hp, files["run_history"])
        for t in rh["tables"]:
            if t["key"] and t["key"][0] == "run-id":
                for row in t["rows"]:
                    c = row["cells"] + [""] * len(t["header"])
                    record = {t["header"][k]: strip_md(c[k]) for k in range(len(t["header"]))}
                    record.update({"file": files["run_history"], "line": row["line"]})
                    model["runs"].append(record)

    model["reqs"] = list(reqs.values())
    build_management_analysis(model, docs, cat_doc, files, warnings)
    build_graph(model, reqs, parts)
    return model


def build_management_analysis(model: dict, docs: list[dict], cat_doc: dict | None,
                              files: dict[str, str], warnings: list[str]) -> None:
    """Build evidence-bearing views from parsed management records.

    The browser deliberately receives the result instead of inventing rows or
    classifying boundaries from display names.
    """
    structure = model["analysis"]["structure"]
    differences = structure["differences"]

    def source(file: str | None, line: int | None = None) -> str:
        return f"{file}:{line}" if file and line else (file or "未配置")

    def add(layer: str, kind: str, target: str, actual: str, ideal: str,
            rule: str, reason: str, file: str | None, line: int | None = None) -> None:
        differences.append({
            "layer": layer, "kind": kind, "delta": kind, "target": f"ID / 位置: {target}", "actual": actual,
            "ideal": ideal, "rule": rule, "reason": f"理由: {reason}", "source": source(file, line),
        })

    req_file_counts = Counter(r["file"] for r in model["reqs"])
    boundary_docs = [d for d in docs if d["rel"] != files["requirements"]]
    layer_specs = [
        ("要求定義書", len(model["reqs"]), "要求ごとに決定状態・上位目的・受入基準を持つ", files["requirements"]),
        ("境界別要求", sum(req_file_counts.get(d["rel"], 0) for d in boundary_docs),
         "索引された境界ファイルの要求が正本IDで結合する", files["requirements_dir"]),
        ("カタログ", len(model["catalog"]["features"]), "要求ごとに実装・試験・共通部品を登録する", files["catalog"]),
        ("System Test", len(model["cases"]), "system ACをケースから要求へ参照できる", files["ledger"]),
        ("ID 台帳", len(model["registryRecords"]), "管理IDを一意な種別・状態で登録する", files["id_registry"]),
        ("実行履歴", len(model["runs"]), "run-idごとに工程・commit・要求・AC・ケースを記録する", files["run_history"]),
        ("境界間", len(model["integrations"]), "連携先ごとに方式・方向・正本を明示する", files["requirements"]),
    ]
    known_req = {r["id"] for r in model["reqs"]}
    known_goal = {g["id"] for g in model["goals"]}
    known_ac = {a["id"] for r in model["reqs"] for a in r["acs"]}
    known_case = {c.get("id") for c in model["cases"]}

    # Requirements: required elements, parent constraints, and duplicate IDs.
    for r in model["reqs"]:
        req_layer = "境界別要求" if r["file"] != files["requirements"] else "要求定義書"
        missing = []
        if not r["status"]:
            missing.append("決定状態")
        if not r["acs"]:
            missing.append("受入基準")
        if missing:
            add(req_layer, "不足", r["id"], "不足: " + "・".join(missing),
                "決定状態・上位目的・受入基準あり", "必須要素",
                "要求の必須要素が解析結果に存在しない", r["file"], r["line"])
        if not r["goal"] or r["goal"] not in known_goal:
            add(req_layer, "孤立", r["id"], f"上位={r['goal']}（参照先なし）",
                "存在する目的に接続", "親子制約", "上位目的が目的レコードに存在しない",
                r["file"], r["line"])
        if not missing and r["goal"] in known_goal:
            add(req_layer, "妥当", r["id"], "必須要素と上位目的を解析済み",
                "決定状態・上位目的・受入基準あり", "必須要素",
                "必須要素と親レコードを確認できた", r["file"], r["line"])
        for ac in r["acs"]:
            refs = set(re.findall(
                r"(?<![A-Za-z0-9-])(?:FR|AC|G|Q|PARAM|SRC|E2E|IT|NFR-[A-Z0-9]+)-[A-Z0-9_-]+",
                ac["text"] or "",
            ))
            for ref in sorted(refs - known_req - known_goal - known_ac):
                add(req_layer, "参照不整合", ac["id"], f"{ref} を参照",
                    "参照IDが管理データに存在", "参照制約",
                    f"参照先 {ref} が解析済みIDに存在しない", r["file"], ac["line"])
    for warning in warnings:
        match = re.match(r"duplicate\s+(\S+)\s+\((.*):(\d+)\)", warning)
        if match:
            add("要求定義書", "重複", match.group(1), "同じIDを複数回定義",
                "ID定義は一意", "必須要素", "パーサーが重複IDを検出",
                match.group(2), int(match.group(3)))

    # Catalog and registry: records with no canonical requirement are excess;
    # duplicate rows and mismatched status/type are explicit differences.
    feature_counts = Counter(f["req"] for f in model["catalog"]["features"])
    req_status = {r["id"]: r["status"] for r in model["reqs"]}
    for f in model["catalog"]["features"]:
        file, line = files["catalog"], f["line"]
        if f["req"] not in known_req:
            add("カタログ", "余剰", f["req"], "要求正本にない機能行",
                "正本要求に対応する機能行", "参照制約",
                "カタログ要求IDの参照先が存在しない", file, line)
        elif feature_counts[f["req"]] > 1:
            add("カタログ", "重複", f["req"], f"機能行 {feature_counts[f['req']]} 件",
                "要求ごとに機能行1件", "必須要素", "同じ要求IDの機能行が複数ある", file, line)
        elif norm(f["status"]) != norm(req_status[f["req"]]):
            add("カタログ", "参照不整合", f["req"], f"カタログ={f['status']}",
                f"要求正本={req_status[f['req']]}", "参照制約",
                "決定状態が要求正本と一致しない", file, line)
        else:
            add("カタログ", "妥当", f["req"],
                f"実装={len(f['impl'])} / 試験={len(f['tests'])} / 共通部品={len(f['parts'])}",
                "要求ごとに実装・試験・共通部品を登録", "必須要素",
                "機能行の要求参照と決定状態が正本に一致", file, line)

    registry_counts = Counter(r["id"] for r in model["registryRecords"])
    for record in model["registryRecords"]:
        rid = record["id"]
        expected = "FR" if rid.startswith("FR-") else ("AC" if rid.startswith("AC-") else rid.split("-", 1)[0])
        if rid not in known_req | known_ac | known_goal:
            add("ID 台帳", "余剰", rid, "正本にないID登録", "定義済みIDのみ登録",
                "参照制約", "台帳IDの定義元が存在しない", record["file"], record["line"])
        elif record["kind"] != expected:
            add("ID 台帳", "参照不整合", rid, f"種別={record['kind']}",
                f"種別={expected}", "参照制約", "ID接頭辞と登録種別が一致しない",
                record["file"], record["line"])
        if registry_counts[rid] > 1:
            add("ID 台帳", "重複", rid, f"登録 {registry_counts[rid]} 件", "登録1件",
                "必須要素", "同じIDが複数行に登録されている", record["file"], record["line"])
        elif rid in known_req | known_ac | known_goal and record["kind"] == expected:
            add("ID 台帳", "妥当", rid, f"種別={record['kind']} / 状態={record['state']}",
                f"種別={expected} / 一意な登録", "必須要素",
                "ID定義元・接頭辞・登録件数が一致", record["file"], record["line"])

    # System Test: every case is checked as an individual record, including
    # parent requirement/AC links, duplicate IDs, and the AC text digest.
    case_counts = Counter(c.get("id") for c in model["cases"])
    ac_parent = {a["id"]: r["id"] for r in model["reqs"] for a in r["acs"]}
    params = {p["id"]: f"{p['value']}{(' ' + p['unit']) if p['unit'] else ''}" for p in model["params"]}

    def current_digest(aid: str) -> str | None:
        ac = next((a for r in model["reqs"] for a in r["acs"] if a["id"] == aid), None)
        if not ac:
            return None
        text = re.sub(r"\{(PARAM-[A-Z0-9_-]+)\}", lambda m: params.get(m.group(1), m.group(0)), ac["text"])
        return "sha256:" + hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode("utf-8")).hexdigest()[:16]

    for case in model["cases"]:
        cid = case.get("id") or source(files["ledger"])
        req_ids = case.get("requirement_ids") or []
        ac_ids = case.get("ac_ids") or []
        if case_counts[case.get("id")] > 1:
            add("System Test", "重複", cid, f"ケース登録 {case_counts[case.get('id')]} 件",
                "ケースIDは一意", "必須要素", "同じケースIDが複数登録されている", files["ledger"])
        invalid_req = [rid for rid in req_ids if rid not in known_req]
        invalid_ac = [aid for aid in ac_ids if aid not in known_ac]
        wrong_parent = [aid for aid in ac_ids if aid in ac_parent and ac_parent[aid] not in req_ids]
        if invalid_req or invalid_ac or wrong_parent:
            actual = " / ".join(filter(None, [
                invalid_req and f"未定義要求={','.join(invalid_req)}",
                invalid_ac and f"未定義AC={','.join(invalid_ac)}",
                wrong_parent and f"親要求不一致={','.join(wrong_parent)}",
            ]))
            add("System Test", "参照不整合", cid, actual,
                "ケースの要求IDが各ACの親要求と一致", "親子制約",
                "ケースから要求・ACの正しい親子関係を辿れない", files["ledger"])
        for aid in ac_ids:
            expected, recorded = current_digest(aid), model["caseDigests"].get(aid)
            if expected and recorded != expected:
                add("System Test", "参照不整合", f"{cid} / {aid}",
                    f"digest={recorded or 'なし'}", f"digest={expected}", "参照制約",
                    "AC本文digestが台帳の作成時点と一致しない", files["ledger"])
        if (case_counts[case.get("id")] == 1 and not invalid_req and not invalid_ac
                and not wrong_parent and all(model["caseDigests"].get(a) == current_digest(a) for a in ac_ids)):
            add("System Test", "妥当", cid,
                f"親要求={','.join(req_ids)} / AC={','.join(ac_ids)} / status={case.get('status')}",
                "親要求一致・一意なケースID・AC digest一致", "親子制約・参照制約",
                "ケースの親・digest・一意性を確認", files["ledger"])

    run_counts = Counter(run.get("run-id", "") for run in model["runs"])
    for run in model["runs"]:
        run_id = run.get("run-id", "")
        refs = expand_ids(" ".join(str(v) for v in run.values()))
        dangling = [ref for ref in refs if ref not in known_req]
        case_refs = [v for k, v in run.items() if k in ("ケース", "case") and v and v not in known_case]
        if dangling or case_refs:
            add("実行履歴", "参照不整合", run_id or source(run["file"], run["line"]),
                "未定義参照: " + "・".join(dangling + case_refs),
                "要求・ケース参照が存在", "参照制約",
                "履歴から辿る参照先が解析データに存在しない", run["file"], run["line"])
        elif run_counts[run_id] > 1:
            add("実行履歴", "重複", run_id, f"履歴 {run_counts[run_id]} 件",
                "run-idごとに履歴1件", "必須要素", "同じrun-idが複数行に存在", run["file"], run["line"])
        else:
            add("実行履歴", "妥当", run_id or source(run["file"], run["line"]),
                "要求・AC・ケース参照を解析済み", "run-idごとに参照先が存在",
                "参照制約", "履歴の参照先と一意性を確認", run["file"], run["line"])

    # Boundary contracts are records too; no aggregate count is used as the
    # oracle. Method, direction, owner and source are cross-boundary constraints.
    boundary_counts = Counter(x["name"] for x in model["integrations"])
    for item in model["integrations"]:
        missing = [label for label, value in (
            ("方式", item["method"]), ("方向", item["meaning"]), ("正本", item["owner"])
        ) if not value]
        if boundary_counts[item["name"]] > 1:
            add("境界間", "重複", item["name"], f"境界定義 {boundary_counts[item['name']]} 件",
                "連携先ごとに定義1件", "必須要素", "同じ連携先が複数定義されている", item["file"], item["line"])
        elif missing:
            add("境界間", "不足", item["name"], "不足=" + "・".join(missing),
                "方式・方向・正本を明示", "境界間制約",
                "境界を越えるデータ契約の必須要素が不足", item["file"], item["line"])
        else:
            add("境界間", "妥当", item["name"],
                f"方式={item['method']} / 方向={item['meaning']} / 正本={item['owner']}",
                "方式・方向・正本を明示", "境界間制約",
                "境界を越えるデータ契約を個別に確認", item["file"], item["line"])

    # AC-045: each of the seven layer summaries is a complete judgement in
    # its own right, not a heading that relies on the detail table below it.
    for name, count, ideal, file in layer_specs:
        rows = [row for row in differences if row["layer"] == name]
        kinds = Counter(row["delta"] for row in rows)
        rules = list(dict.fromkeys(row["rule"] for row in rows))
        structure["layers"].append({
            "name": name,
            "actual": f"解析済みレコード {count} 件",
            "ideal": ideal,
            "delta": " / ".join(f"{kind} {amount} 件" for kind, amount in kinds.items()) or "判定対象 0 件",
            "rule": " / ".join(rules) or "対象レコードの存在確認",
            "reason": f"個別根拠 {len(rows)} 件を集計",
            "source": source(file),
        })

    # Runtime/data placement is a contract derived from the files actually
    # loaded and catalog paths actually registered.
    management = [v for v in model["meta"]["files"].values() if v]
    implementations = sorted({p for f in model["catalog"]["features"] for p in f["impl"]})
    boundaries = [{
        "name": x["name"], "method": x["method"], "direction": x["meaning"],
        "owner": x["owner"], "source": source(x["file"], x["line"]),
    } for x in model["integrations"]]
    management_nodes = [
        {"name": f"管理データ: {path}", "kind": "management", "runsAt": "対象リポジトリ",
         "data": path, "access": "Studio サーバー → 読取", "source": path}
        for path in management
    ]
    implementation_nodes = [
        {"name": f"実装ファイル: {path}", "kind": "implementation", "runsAt": "対象リポジトリ",
         "data": path, "access": "Studio サーバー → 登録位置のみ読取", "source": files["catalog"]}
        for path in implementations
    ]
    model["analysis"]["runtime"] = {
        "components": [
            {"name": "PC", "runsAt": str(model["meta"]["repo"]), "data": "Studio ローカルプロセス", "source": "起動時実行環境"},
            {"name": "ブラウザー", "runsAt": "PC", "data": "APIから受け取った表示モデル（メモリ）", "source": "/api/model"},
            {"name": "Studio サーバー", "runsAt": "PC / 127.0.0.1", "data": "管理データの解析結果（メモリ）", "source": "EABK-Studio/studio.py"},
            {"name": f"対象リポジトリ: {model['meta']['name']}", "runsAt": model["meta"]["repo"],
             "data": "管理データと実装ファイルの格納境界", "source": str(model["meta"]["repo"])},
            *management_nodes, *implementation_nodes,
        ],
        "flows": [
            *[{"from": node["name"], "to": "Studio サーバー", "direction": "読取",
               "data": node["data"], "source": node["source"]} for node in management_nodes],
            *[{"from": "カタログ", "to": node["name"], "direction": "読取（登録位置）",
               "data": node["data"], "source": node["source"]} for node in implementation_nodes],
            {"from": "対象リポジトリ", "to": "Studio サーバー", "direction": "読取",
             "data": "管理データ・実装ファイルの登録位置", "source": "、".join(management) or "なし"},
            {"from": "Studio サーバー", "to": "ブラウザー", "direction": "読取",
             "data": "解析済み表示モデル", "source": "/api/model"},
            {"from": "Studio", "to": "対象リポジトリ", "direction": "書込",
             "data": "なし（表示機能）", "source": "読取専用契約"},
        ],
        "boundaries": boundaries,
        "externalSend": boundaries,
    }

    # AC-051: normalized, evidence-bearing records for every progress dimension.
    history = model["analysis"]["history"]
    for d in model["decisions"]:
        history.append({"category": "決定記録", "id": d["target"] or d["decision"], "date": d["date"],
                        "status": d["decision"], "file": d["file"], "line": d["line"]})
    for run in model["runs"]:
        history.append({"category": "実行履歴", "id": run.get("run-id", ""),
                        "date": run.get("終了") or run.get("開始", ""),
                        "status": run.get("結果", ""), "file": run["file"], "line": run["line"]})
    for r in model["reqs"]:
        history.append({"category": "要求状態", "id": r["id"], "date": "", "status": r["status"],
                        "file": r["file"], "line": r["line"]})
    for f in model["catalog"]["features"]:
        history.append({"category": "実装登録", "id": f["req"], "date": "", "status": "登録済み" if f["impl"] else "未登録",
                        "file": files["catalog"], "line": f["line"]})
    for c in model["cases"]:
        history.append({"category": "System Test", "id": c.get("id") or "", "date": c.get("last_run_at") or "",
                        "status": c.get("status") or "未設定", "file": files["ledger"], "line": c.get("line")})


def build_graph(model: dict, reqs: dict, parts: list[dict]) -> None:
    nodes: OrderedDict[str, dict] = OrderedDict()
    edges: dict[tuple[str, str, str], None] = {}

    def node(nid: str, typ: str, label: str, **kw) -> dict:
        n = nodes.get(nid)
        if n is None:
            n = {"id": nid, "type": typ, "label": label}
            nodes[nid] = n
        n.update({k: v for k, v in kw.items() if v not in (None, "")})
        return n

    def edge(a: str, b: str, rel: str) -> None:
        if a in nodes and b in nodes and a != b:
            edges[(a, b, rel)] = None

    feats = {f["req"]: f for f in model["catalog"]["features"]}
    for g in model["goals"]:
        node(g["id"], "goal", g["id"], title=g["title"], file=g["file"], line=g["line"])
    for r in reqs.values():
        f = feats.get(r["id"])
        impl = "unlisted" if f is None else ("done" if f["impl"] else "none")
        node(r["id"], "req", r["id"], title=r["title"], status=r["status"], statusKind=r["statusKind"], priority=r["priority"],
             kind=r["kind"], cat=r["cat"], impl=impl, file=r["file"], line=r["line"], group=r["file"].rsplit("/", 1)[-1])
    for p in model["params"]:
        node(p["id"], "param", p["id"], title=f"{p['name']} = {p['value']}{p['unit'] and ' ' + p['unit']}", file=p["file"], line=p["line"])
    for q in model["questions"]:
        node(q["id"], "question", q["id"], title=q["question"][:120], status=q["state"], file=q["file"], line=q["line"])

    # components & files
    def file_node(path: str, role: str, **kw) -> str:
        comp, mod = component_of(path)
        nid = f"file:{path}"
        n = node(nid, "file", path.rsplit("/", 1)[-1], title=path, path=path, comp=comp, module=mod, role=role)
        if role == "test":
            n["role"] = "test"
        cid = f"comp:{comp}"
        node(cid, "component", comp.rsplit("/", 1)[-1], title=comp, path=comp, kind="test" if comp.split("/")[0] in TEST_DIRS else "app")
        edge(nid, cid, "member")
        return nid

    part_alias: dict[str, str] = {}
    for p in parts:
        pid = f"part:{p['name']}"
        node(pid, "part", re.sub(r"[（(].*$", "", p["name"]).strip() or p["name"], title=p["purpose"][:200], path=p["name"],
             file=model["meta"]["files"].get("catalog"), line=p["line"])
        for al in alias_set(p["name"]):
            part_alias.setdefault(al, pid)
        for fp in p["files"]:
            edge(pid, file_node(fp, "impl"), "part-file")
        for rid in p["reqs"]:
            edge(rid, pid, "req-part")
    for a in model["catalog"]["apis"]:
        aid = f"api:{a['name']}"
        node(aid, "api", a["name"], title=a["name"], file=model["meta"]["files"].get("catalog"), line=a["line"])
        for fp in a["files"]:
            edge(aid, file_node(fp, "impl"), "def-file")
        for rid in a["reqs"]:
            edge(rid, aid, "req-api")
    for tb in model["catalog"]["tables"]:
        tid = f"tbl:{tb['name']}"
        node(tid, "table", tb["name"], title=f"{tb['name']} ({tb['owner']})" if tb["owner"] else tb["name"],
             file=model["meta"]["files"].get("catalog"), line=tb["line"])
        for fp in tb["files"]:
            edge(tid, file_node(fp, "impl"), "def-file")
        for rid in tb["reqs"]:
            edge(rid, tid, "req-table")

    # entities
    ent_alias: dict[str, str] = {}
    for sm in model["stateMachines"]:
        eid = f"ent:{sm['entity']}"
        node(eid, "entity", sm["entity"], title=sm["entity"], states=len(sm["states"]), file=sm["file"], line=sm["line"])
        ent_alias[norm(re.sub(r"[（(].*?[）)]", "", sm["entity"]))] = eid
    for t in model["terms"]:
        base = norm(re.sub(r"[（(].*?[）)]", "", t["term"]))
        eid = ent_alias.get(base)
        if eid is None:
            eid = f"ent:{t['term']}"
            node(eid, "entity", t["term"], title=t["definition"][:200], file=t["file"], line=t["line"])
            ent_alias[base] = eid
        else:
            node(eid, "entity", nodes[eid]["label"], title=t["definition"][:200])
    for r in reqs.values():
        for e in r["entities"]:
            base = norm(re.sub(r"[（(].*?[）)]", "", e))
            eid = ent_alias.get(base)
            if eid is None:
                eid = f"ent:{e}"
                node(eid, "entity", e, title=e)
                ent_alias[base] = eid
            edge(r["id"], eid, "req-entity")

    for r in reqs.values():
        rid = r["id"]
        if r["goal"] in nodes:
            edge(r["goal"], rid, "goal-req")
        for pid in r["params"]:
            edge(rid, pid, "req-param")
        for q in r["blocked"]:
            edge(rid, q, "req-question")
        for ac in r["acs"]:
            node(ac["id"], "ac", ac["id"], title=ac["text"][:160], req=rid, level=ac["level"], blocked=ac["blocked"],
                 file=r["file"], line=ac["line"])
            edge(rid, ac["id"], "req-ac")
        for other in expand_ids(r["text"] + " " + " ".join(a["text"] for a in r["acs"]), set(reqs)):
            if other != rid:
                edge(rid, other, "ref")
        f = feats.get(rid)
        if f:
            for fp in f["impl"]:
                edge(rid, file_node(fp, "impl"), "req-file")
            for fp in f["tests"]:
                edge(rid, file_node(fp, "test"), "req-test")
            for pn in f["parts"]:
                base = re.sub(r"[（(].*$", "", pn).strip()
                pid = part_alias.get(norm(base).lower())
                if pid is None:
                    for piece in re.split(r"\s*/\s*", base):
                        pid = part_alias.get(norm(piece).lower())
                        if pid:
                            break
                if pid:
                    edge(rid, pid, "req-part")

    for c in model["cases"]:
        cid = c["id"]
        node(cid, "case", cid, title=c.get("title") or "", status=c.get("status") or "", layer=c.get("layer") or "",
             file=model["meta"]["files"].get("ledger"))
        for rid in c.get("requirement_ids") or []:
            edge(rid, cid, "req-case")
        for aid in c.get("ac_ids") or []:
            edge(aid, cid, "ac-case")
        for fp in path_tokens(c.get("command") or ""):
            edge(cid, file_node(fp, "test"), "case-file")

    for p in model["personas"]:
        node(f"persona:{p['name']}", "persona", p["name"], title=p["work"], file=p["file"], line=p["line"])
    for it in model["integrations"]:
        node(f"ext:{it['name']}", "external", it["name"], title=it["meaning"][:160], file=it["file"], line=it["line"])

    deg: Counter = Counter()
    for (a, b, _rel) in edges:
        deg[a] += 1
        deg[b] += 1
    for nid, n in nodes.items():
        n["deg"] = deg[nid]
    model["graph"] = {"nodes": list(nodes.values()),
                      "edges": [{"s": a, "t": b, "rel": rel} for (a, b, rel) in edges]}
