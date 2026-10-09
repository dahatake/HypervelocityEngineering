"""EABK Studio: reads the EABK data layer of any repository and builds one model.

Only the data layer is read (requirements definition, catalog, system-test ledger,
ID registry, run history). Source code is never opened; it is only *named* by the
paths that the catalog already holds.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter, OrderedDict
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

REQ_ID = r"(?:FR|NFR-[A-Z0-9]+)-\d{3,}"
REQ_ID_RE = re.compile(r"(?<![A-Za-z0-9\-])(" + REQ_ID + r")(?![0-9])")
ANY_ID_RE = re.compile(r"(?<![A-Za-z0-9\-])((?:FR|AC|G|Q|PARAM|SRC|E2E|IT|AUD|NFR-[A-Z0-9]+)-\d{3,})(?![0-9])")
REQ_HEADING_RE = re.compile(r"^(#{2,6})\s+\**(" + REQ_ID + r")\**\s*(.*)$")
AC_HEADING_RE = re.compile(r"^(#{2,6})\s+\**(AC-\d{3,})\**\s*(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
RANGE_RE = re.compile(
    r"(?<![A-Za-z0-9\-])((?:FR|NFR-[A-Z0-9]+)-)(\d{3,})\s*[〜~～]\s*(?:(?:FR|NFR-[A-Z0-9]+)-)?(\d{3,})")
LIST_RE = re.compile(
    r"(?<![A-Za-z0-9\-])((?:FR|NFR-[A-Z0-9]+)-)(\d{3,})((?:\s*[・,、，]\s*\d{3,}(?![0-9\-]))+)")
KEYS = ("決定状態", "出自", "優先度", "上位", "出典", "対象エンティティ", "関係する状態", "参照パラメータ", "関連する既存資産")
KEY_RE = re.compile(r"(?:(?<=^)|(?<=[\s　]))(" + "|".join(KEYS) + r")\s*[:：]")
TOP_KEY_RE = re.compile(
    r"^[-*]\s+(要求|" + "|".join(KEYS) + r"|受入基準(?:\s+(?:AC-\d{3,}))?)\s*[:：]\s*(.*)$")
AC_BULLET_RE = re.compile(r"^[-*]\s+(?:受入基準\s*)?\**(AC-\d{3,})\**\s*[:：]\s*(.*)$")
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
         "params": [], "assets": "", "acs": [], "blocked": [], "file": rel, "line": line, "body": ""}
    cur_key, cur_ac, texts = None, None, []
    body = []
    for ln_no, raw in block:
        body.append(raw)
        line_s = raw.rstrip()
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
                 "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "files": {}, "fingerprint": fingerprint(root)},
        "goals": [], "reqs": [], "params": [], "terms": [], "stateMachines": [], "personas": [], "integrations": [],
        "questions": [], "decisions": [], "audits": [], "sources": [], "scenarios": [], "catalog": {"features": [], "apis": [], "tables": [], "parts": []},
        "cases": [], "runs": [], "registry": {}, "graph": {"nodes": [], "edges": []}, "warnings": warnings,
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
                                 "assets": "", "acs": [], "blocked": [], "file": t["file"], "line": row["line"], "body": ""}

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
            data = json.loads(read_text(lp))
            for c in data.get("cases", []):
                model["cases"].append({k: c.get(k) for k in ("id", "requirement_ids", "ac_ids", "title", "layer", "command",
                                                              "canary", "status", "last_commit", "last_run_at", "evidence")})
        except ValueError:
            warnings.append("ledger is not valid JSON")
    rp = root / files["id_registry"]
    if rp.is_file():
        reg = parse_document(rp, files["id_registry"])
        cnt: Counter = Counter()
        for t in reg["tables"]:
            if t["key"][:3] == ["ID", "種別", "状態"]:
                for row in t["rows"]:
                    if len(row["cells"]) > 2:
                        cnt[(strip_md(row["cells"][1]), strip_md(row["cells"][2]))] += 1
        model["registry"] = [{"kind": k, "state": s, "count": n} for (k, s), n in sorted(cnt.items())]
    hp = root / files["run_history"]
    if hp.is_file():
        rh = parse_document(hp, files["run_history"])
        for t in rh["tables"]:
            if t["key"] and t["key"][0] == "run-id":
                for row in t["rows"]:
                    c = row["cells"] + [""] * len(t["header"])
                    model["runs"].append({t["header"][k]: strip_md(c[k]) for k in range(len(t["header"]))})

    model["reqs"] = list(reqs.values())
    # The integrity summary is deliberately derived from the management data
    # only.  It gives the UI both the current state and an explicit ideal
    # target without treating proposed requirements as implementation work.
    features_by_req = {f["req"]: f for f in model["catalog"]["features"]}
    cases_by_req: dict[str, list[dict]] = {}
    for case in model["cases"]:
        for rid in case.get("requirement_ids") or []:
            cases_by_req.setdefault(rid, []).append(case)
    approved = [r for r in model["reqs"] if r["statusKind"] == "approved"]
    cataloged = [r for r in approved if r["id"] in features_by_req]
    implemented = [r for r in cataloged if features_by_req[r["id"]]["impl"]]
    tested = [r for r in cataloged if features_by_req[r["id"]]["tests"]]
    blocked_acs = [a for r in model["reqs"] for a in r["acs"] if a.get("blocked")]
    open_questions = [q for q in model["questions"]
                      if not re.search(r"回答済み|解決済み|取り下げ|クローズ", q.get("state", ""))]
    issues = []
    for r in approved:
        f = features_by_req.get(r["id"])
        if f is None:
            issues.append({"id": r["id"], "kind": "catalog", "message": "approved requirement is not cataloged"})
        elif not f["impl"]:
            issues.append({"id": r["id"], "kind": "implementation", "message": "catalog entry has no implementation file"})
        if f is not None and not f["tests"]:
            issues.append({"id": r["id"], "kind": "test", "message": "catalog entry has no test file"})
        if r["acs"] and not cases_by_req.get(r["id"]):
            issues.append({"id": r["id"], "kind": "ledger", "message": "acceptance criteria have no ledger case"})
    model["integrity"] = {
        "current": {
            "requirements": len(model["reqs"]), "approved": len(approved),
            "cataloged": len(cataloged), "implemented": len(implemented),
            "tested": len(tested), "acceptanceCriteria": sum(len(r["acs"]) for r in model["reqs"]),
            "cases": len(model["cases"]), "passingCases": sum(c.get("status") == "pass" for c in model["cases"]),
            "openQuestions": len(open_questions), "blockedAcceptanceCriteria": len(blocked_acs),
            "historyRuns": len(model["runs"]), "decisions": len(model["decisions"]),
        },
        "ideal": {
            "catalogedApproved": len(approved), "implementedApproved": len(approved),
            "testedApproved": len(approved),
            "ledgerCoverage": sum(1 for r in approved if r["acs"] and cases_by_req.get(r["id"])),
        },
        "issues": issues,
    }
    build_graph(model, reqs, parts)
    return model


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
