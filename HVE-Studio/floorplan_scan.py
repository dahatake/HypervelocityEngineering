"""FR-1092: the "floorplan" map of a repository — parts, files, endpoints and the lines between them (read only, no AI, nothing executed).

Compatible with Floorplan's `floorplan/architecture.json` (parts, `paths` globs, `exclude`, `packages`, `hosts`, `edges`, `annotations`,
`flows`, `tour`, `ignore`, `editor`): when the repository has that file, its parts are used and files go to the deepest part that claims them.
Without it, parts are derived from the folders. Everything else (files, imports, endpoints, web requests, screens, health, recent work) is scanned.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import code_graph
import floorplan_health
import floorplan_routes
import repo_scan

CODE_EXTS = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".html", ".css", ".sh", ".ps1", ".cmd"}
LANG = {".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript",
        ".html": "html", ".css": "css", ".sh": "shell", ".ps1": "shell", ".cmd": "shell"}
MAX_TEXT = 1_000_000
SCRIPT_DIRS = {"scripts", "script", "tools", "bin", "tool"}
INFRA_DIRS = {".github", ".vscode", "infra", "deploy", "docker", ".devcontainer", ".azure", "ci", ".circleci", ".gitlab"}
KNOWN_PACKAGES = {  # package -> (label, summary)
    "stripe": ("Stripe", "Takes card payments."), "openai": ("OpenAI", "Language-model service."), "anthropic": ("Anthropic", "Language-model service."),
    "boto3": ("Amazon Web Services", "Cloud services."), "azure": ("Microsoft Azure", "Cloud services."), "psycopg2": ("Postgres", "The database."),
    "sqlalchemy": ("Database", "Where the data is kept."), "pymongo": ("MongoDB", "The database."), "mongoose": ("MongoDB", "The database."),
    "redis": ("Redis", "Fast shared memory and queues."), "supabase": ("Supabase", "Database and sign-in service."), "firebase": ("Firebase", "Database and sign-in service."),
    "sendgrid": ("SendGrid", "Sends emails."), "twilio": ("Twilio", "Sends text messages."), "playwright": ("Playwright", "Drives a real browser."),
    "three": ("three.js", "Draws 3D scenes."), "pg": ("Postgres", "The database."), "mysql": ("MySQL", "The database."), "prisma": ("Database", "Where the data is kept."),
}
SKIP_HOSTS = re.compile(r"(?i)^(localhost|127\.|0\.0\.0\.0|example\.|.*\.example$|www\.w3\.org|json-schema\.org|schemas\.|.*\.local$|github\.com$|raw\.githubusercontent\.com$|opensource\.org|creativecommons\.org)")
STDLIB = set(getattr(sys, "stdlib_module_names", ()))


# ------------------------------------------------------------------ small helpers
def humanize(name: str) -> str:
    w = re.sub(r"\.[A-Za-z]+$", "", name).lstrip("_")
    w = re.sub(r"[_\-.]+", " ", w)
    w = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", w).strip()
    words = [x if (len(x) > 1 and x.isupper()) else x.lower() for x in w.split()]
    s = " ".join(words)
    return s[:1].upper() + s[1:]


def clean_doc(s: str) -> str:
    return re.sub(r"^(?:(?:NFR|FR|AC)-[\w-]+[\s,、]*)+[:：]\s*", "", (s or "").strip(), flags=re.I).strip()


def glob_to_re(pat: str) -> tuple[re.Pattern, int]:
    """Floorplan glob syntax: ** any directories, * within a segment, ? one char, {a,b}, a whole `[id]` folder is literal; a pattern with no wildcard is a directory."""
    pat = pat.strip().strip("/")
    literal = len(re.split(r"[*?{\[]", pat, 1)[0])
    out, i, brace = [], 0, 0
    segs = pat.split("/")
    has_wild = any(c in pat for c in "*?{") or any(("[" in s and not (s.startswith("[") and s.endswith("]") and "[" not in s.strip("[]"))) for s in segs)
    for si, seg in enumerate(segs):
        if seg == "**":
            out.append("(?:.*/)?" if si < len(segs) - 1 else ".*")
            continue
        if seg.startswith("[") and seg.endswith("]") and re.fullmatch(r"\[+\.*[\w-]+\]+", seg):
            piece = re.escape(seg)
        else:
            piece = ""
            j = 0
            while j < len(seg):
                c = seg[j]
                if c == "*":
                    piece += "[^/]*"
                elif c == "?":
                    piece += "[^/]"
                elif c == "{":
                    brace += 1
                    piece += "(?:"
                elif c == "}" and brace:
                    brace -= 1
                    piece += ")"
                elif c == "," and brace:
                    piece += "|"
                elif c == "[":
                    k = seg.find("]", j)
                    if k < 0:
                        piece += re.escape(c)
                    else:
                        piece += "[" + seg[j + 1:k].replace("\\", "\\\\") + "]"
                        j = k
                else:
                    piece += re.escape(c)
                j += 1
        out.append(piece + ("/" if si < len(segs) - 1 and seg != "**" else ""))
    body = "".join(out)
    rx = re.compile("^" + body + (r"(?:/.*)?" if not has_wild else "") + "$")
    return rx, literal


# ------------------------------------------------------------------ architecture.json
def load_config(root: Path) -> tuple[dict | None, list[str]]:
    path = root / "floorplan" / "architecture.json"
    if not path.is_file():
        return None, []
    try:
        cfg = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return None, [f"floorplan/architecture.json: {exc}"]
    problems = []
    if not isinstance(cfg, dict) or not isinstance(cfg.get("nodes"), list):
        return None, ["floorplan/architecture.json: `nodes` must be an array"]
    ids = set()
    for i, n in enumerate(cfg["nodes"]):
        if not isinstance(n, dict) or not re.fullmatch(r"[\w.\-]+", str(n.get("id", ""))):
            problems.append(f"nodes[{i}]: `id` must use letters, digits, _ - .")
            continue
        if n["id"] in ids:
            problems.append(f"nodes[{i}] ({n['id']}): duplicate id")
        ids.add(n["id"])
    cfg["nodes"] = [n for n in cfg["nodes"] if isinstance(n, dict) and re.fullmatch(r"[\w.\-]+", str(n.get("id", "")))]
    for n in cfg["nodes"]:
        if n.get("parent") and n["parent"] not in ids:
            problems.append(f"{n['id']}: parent {n['parent']} does not exist")
            n["parent"] = None
        for key in ("paths", "exclude"):
            for pat in n.get(key, []) or []:
                if not isinstance(pat, str) or len(pat) > 300 or pat.count("[") != pat.count("]") or pat.count("{") != pat.count("}"):
                    problems.append(f"{n['id']}.{key}: `{pat}` is not a valid pattern")
    return cfg, problems


# ------------------------------------------------------------------ git: recent work
def _git(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=30, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def recent_work(root: Path, known: set[str], days: int = 30) -> dict:
    tasks = []
    status = _git(root, "status", "--porcelain", "-z")
    items = []
    for entry in status.split("\0"):
        if len(entry) > 3:
            code, p = entry[:2], entry[3:]
            if p in known:
                items.append({"ref": p, "change": "new" if "?" in code or "A" in code else "changed", "note": ""})
    if items:
        tasks.append({"title": "", "kind": "uncommitted", "request": "", "summary": "", "items": items[:60], "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    log = _git(root, "log", f"--since={days}.days", "-n", "10", "--no-merges", "--name-status", "--format=%x01%H%x02%cI%x02%s")
    for block in log.split("\x01")[1:]:
        head, *rest = block.strip().split("\n")
        parts = head.split("\x02")
        if len(parts) < 3:
            continue
        its = []
        for line in rest:
            bits = line.split("\t")
            if len(bits) >= 2 and bits[-1] in known:
                its.append({"ref": bits[-1], "change": "new" if bits[0].startswith("A") else "changed", "note": ""})
        if its:
            tasks.append({"title": parts[2][:90], "kind": "commit", "commit": parts[0][:8], "request": "", "summary": "", "items": its[:60], "at": parts[1]})
    seen: set[str] = set()
    for t in tasks:            # a card belongs to the newest task that touched it
        t["items"] = [i for i in t["items"] if not (i["ref"] in seen or seen.add(i["ref"]))]
    tasks = [t for t in tasks if t["items"]]
    return {"updatedAt": tasks[0]["at"] if tasks else "", "tasks": tasks[:8]}


# ------------------------------------------------------------------ build
def build(root: Path, inv: repo_scan.Inventory | None = None) -> dict:
    paths = repo_scan.list_files(root, inv)
    empty = {"schema": "hve-floorplan@1", "meta": {"repo": str(root), "authored": False, "problems": [], "editor": "vscode", "empty": True}, "project": {"name": root.name, "summary": "", "entrypoints": []},
             "nodes": [], "files": [], "routes": [], "links": [], "flows": [], "tour": [], "recent": {"updatedAt": "", "tasks": []}, "health": {"summary": {"high": 0, "medium": 0, "low": 0}, "issues": [], "checked": {}},
             "screens": [], "annotations": []}
    if paths is None:
        return empty
    cfg, problems = load_config(root)
    ignore = [glob_to_re(p)[0] for p in (cfg or {}).get("ignore", []) if isinstance(p, str)]
    cand = [p for p in paths if Path(p).suffix.lower() in CODE_EXTS and not repo_scan.excluded(p) and not code_graph.VENDOR_RE.search(p)
            and not repo_scan.SECRET_NAME.search(Path(p).name) and not any(rx.match(p) for rx in ignore) and p.split("/")[0] != "floorplan"]
    texts: dict[str, str] = {}
    symlinks: dict[Path, bool] = {}
    for rel in cand:
        try:
            if repo_scan.safe_file(root, rel, symlinks) and (root / rel).stat().st_size <= MAX_TEXT:
                texts[rel] = repo_scan.read_text(root / rel, MAX_TEXT)[0]
        except (OSError, UnicodeDecodeError):
            pass
    cg = code_graph.build(root, inv)
    cgfile = {f["path"]: f for f in cg["files"]}
    syms_by_file: dict[str, list[dict]] = defaultdict(list)
    for n in cg["nodes"]:
        syms_by_file[n["file"]].append(n)

    files: dict[str, dict] = {}
    for rel, text in texts.items():
        ext = Path(rel).suffix.lower()
        info = cgfile.get(rel, {})
        top = sorted((n for n in syms_by_file.get(rel, []) if n["kind"] != "module" and "." not in n["qual"]), key=lambda n: -n["deg"])[:10]
        doc = info.get("doc", "")
        if not doc and ext == ".html":
            m = re.search(r"<title>([^<]{3,120})</title>", text)
            doc = m.group(1).strip() if m else ""
        files[rel] = {"p": rel, "l": LANG[ext], "loc": text.count("\n") + 1, "name": humanize(rel.split("/")[-1]), "d": clean_doc(doc), "test": bool(info.get("test", code_graph.TEST_RE.search(rel))),
                      "s": [[n["name"], n["kind"], n["line"], n["deg"]] for n in top],
                      "entry": bool(re.search(r"__name__\s*==\s*['\"]__main__['\"]|^#!/", text, re.M)) or ext in (".html", ".sh", ".ps1", ".cmd") or Path(rel).name in ("conftest.py", "__init__.py", "index.js", "index.ts", "main.py", "app.py", "setup.py")}

    routes = floorplan_routes.extract(texts)
    for i, r in enumerate(routes):
        r["id"] = f"r:{i}"
        r["name"] = humanize(r["h"]) if r["h"] else humanize([s for s in re.split(r"[/:{}<>*]+", r["p"]) if s and s[0].isalpha()][-1] if re.search(r"[A-Za-z]", r["p"]) else "root")
        r["d"] = clean_doc(r["d"])
    # ---- parts
    nodes, assign = (_config_nodes(cfg, files, routes) if cfg and cfg["nodes"] else _auto_nodes(files, routes, texts))
    node_by_id = {n["id"]: n for n in nodes}
    for rel, f in files.items():
        f["n"] = assign.get(rel, "_unassigned")
    if any(f["n"] == "_unassigned" for f in files.values()) and "_unassigned" not in node_by_id:
        nodes.append({"id": "_unassigned", "parent": None, "label": "Unassigned", "kind": "library", "summary": "Files no part claims.", "details": "", "tags": [], "paths": [], "packages": [], "hosts": []})
        node_by_id["_unassigned"] = nodes[-1]
    # ---- external parts (packages and hosts)
    ext_nodes = _externals(nodes, files, texts, cfg)
    node_by_id.update({n["id"]: n for n in ext_nodes})
    nodes += ext_nodes
    # ---- lines
    links = []
    importers: Counter = Counter()
    sym_w: Counter = Counter()
    for e in cg["edges"]:
        a, b = e["s"].split("::")[0], e["t"].split("::")[0]
        if a != b and e["conf"] != "name":
            sym_w[(a, b)] += e.get("n", 1)
    for rel, info in cgfile.items():
        if rel not in files:
            continue
        for tgt in info["imports"]:
            if tgt in files and tgt != rel:
                importers[tgt] += 1
                links.append({"a": "f:" + rel, "b": "f:" + tgt, "k": "import", "w": max(1, sym_w.get((rel, tgt), 0)), "names": []})
    pkg_links, host_links = _external_links(files, texts, [n for n in nodes if n["kind"] == "external"])
    for rel, text in texts.items():       # a page loads its scripts and styles
        if rel.endswith(".html"):
            for m in re.finditer(r"""<(?:script|link)\b[^>]*?(?:src|href)=["']([^"':#?]+)["']""", text):
                target = os.path.normpath(str(Path(rel).parent / m.group(1))).replace("\\", "/")
                if target in files and target != rel:
                    importers[target] += 1
                    links.append({"a": "f:" + rel, "b": "f:" + target, "k": "import", "w": 1, "names": []})
    links += pkg_links + host_links
    calls = floorplan_routes.http_calls(texts)
    by_route = [(r, r["m"], r["p"]) for r in routes]
    seen_http: Counter = Counter()
    for rel, m, p, _line in calls:
        for r, rm, rp in by_route:
            if (rm == m or rm == "ANY") and floorplan_routes.match(rp, p) and r["f"] != rel:
                seen_http[(rel, r["id"])] += 1
                break
    for (rel, rid), w in seen_http.items():
        links.append({"a": "f:" + rel, "b": rid, "k": "http", "w": w, "names": []})
    for e in (cfg or {}).get("edges", []) or []:
        a, b = _ref(e.get("from", ""), node_by_id, files), _ref(e.get("to", ""), node_by_id, files)
        if a and b:
            links.append({"a": a, "b": b, "k": e.get("kind", "import") if e.get("kind") in ("import", "call", "http", "rpc", "event", "queue", "data", "config") else "import",
                          "w": 1, "names": [], "label": e.get("label", ""), "description": e.get("description", "")})
    # ---- node stats
    for n in nodes:
        n.setdefault("stats", {"files": 0, "loc": 0, "langs": {}, "endpoints": 0})
    child_of: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        if n.get("parent"):
            child_of[n["parent"]].append(n["id"])

    def chain(nid: str):
        while nid:
            yield nid
            nid = node_by_id.get(nid, {}).get("parent")
    for rel, f in files.items():
        for nid in chain(f["n"]):
            st = node_by_id[nid]["stats"]
            st["files"] += 1
            st["loc"] += f["loc"]
            st["langs"][f["l"]] = st["langs"].get(f["l"], 0) + f["loc"]
    for r in routes:
        f = files.get(r["f"])
        if f:
            for nid in chain(f["n"]):
                node_by_id[nid]["stats"]["endpoints"] += 1
    # ---- screens, health, recent, tour, flows
    screens = _screens(files, texts, cgfile, routes, links, node_by_id)
    health = floorplan_health.run(list(files.values()), texts, routes, importers, screens, {"index.js", "index.ts", "main.py", "app.py", "conftest.py"})
    known = set(files)
    recent = recent_work(root, known)
    project = _project(root, cfg, files, nodes)
    def norm(items, key):
        out = []
        for it in items:
            ref = _ref(str(it.get(key, "")), node_by_id, files) or (it.get(key) if str(it.get(key, "")).startswith(("n:", "f:", "r:")) else None)
            if ref:
                out.append({**it, key: ref})
        return out
    flows = []
    for f in (cfg or {}).get("flows") or []:
        if isinstance(f, dict):
            steps = norm([s for s in f.get("steps", []) if isinstance(s, dict)], "node")
            if len(steps) >= 2:
                flows.append({**f, "steps": steps})
    flows = flows or _auto_flows(screens)
    tour = norm([t for t in ((cfg or {}).get("tour") or []) if isinstance(t, dict)], "node") or _auto_tour(nodes, node_by_id)
    first = flows[0] if flows else None
    if cfg and first and first.get("steps") and cfg.get("tour"):
        pass
    return {"schema": "hve-floorplan@1",
            "meta": {"repo": str(root), "authored": bool(cfg), "problems": problems, "editor": (cfg or {}).get("editor", "vscode"), "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "audience": (cfg or {}).get("audience", "everyone"), "counts": {"files": len(files), "routes": len(routes), "links": len(links)}},
            "project": project, "nodes": nodes, "files": list(files.values()), "routes": routes, "links": links, "flows": flows, "tour": tour,
            "recent": recent, "health": health, "screens": screens, "annotations": (cfg or {}).get("annotations", []) or []}


def _ref(x: str, node_by_id: dict, files: dict) -> str | None:
    if x in node_by_id:
        return "n:" + x
    if x in files:
        return "f:" + x
    return None


# ------------------------------------------------------------------ parts
def _config_nodes(cfg: dict, files: dict, routes: list[dict]):
    nodes = []
    compiled = []
    for n in cfg["nodes"]:
        node = {"id": n["id"], "parent": n.get("parent"), "label": n.get("label") or humanize(n["id"]), "kind": n.get("kind", "library"), "summary": n.get("summary", ""),
                "details": n.get("details", ""), "tags": n.get("tags", []) or [], "paths": n.get("paths", []) or [], "packages": n.get("packages", []) or [], "hosts": n.get("hosts", []) or []}
        nodes.append(node)
        if node["kind"] != "external":
            compiled.append((node, [glob_to_re(p) for p in node["paths"] if isinstance(p, str)], [glob_to_re(p)[0] for p in n.get("exclude", []) or [] if isinstance(p, str)]))
    depth: dict[str, int] = {}
    by_id = {n["id"]: n for n in nodes}

    def d(nid: str) -> int:
        if nid not in depth:
            depth[nid] = 0 if not by_id[nid]["parent"] else 1 + d(by_id[nid]["parent"])
        return depth[nid]
    assign: dict[str, str] = {}
    for rel in files:
        best = None
        for node, pats, excl in compiled:
            exclude_here = list(excl)
            p = node
            while p.get("parent"):          # exclude is inherited by descendants
                p = by_id[p["parent"]]
                exclude_here += next((e for nn, _pp, e in compiled if nn is p), [])
            if any(x.match(rel) for x in exclude_here):
                continue
            lit = max((ln for rx, ln in pats if rx.match(rel)), default=-1)
            if lit >= 0:
                key = (d(node["id"]), lit)
                if best is None or key > best[0]:
                    best = (key, node["id"])
        if best:
            assign[rel] = best[1]
    return nodes, assign


def _slug(s: str) -> str:
    return re.sub(r"[^\w.\-]+", "-", s).strip("-") or "root"


def _auto_nodes(files: dict, routes: list[dict], texts: dict):
    nodes: list[dict] = []
    assign: dict[str, str] = {}
    route_files = {r["f"] for r in routes}

    def add(nid, parent, label, kind, summary, paths):
        nodes.append({"id": nid, "parent": parent, "label": label, "kind": kind, "summary": summary, "details": "", "tags": [], "paths": paths, "packages": [], "hosts": []})

    def summary_of(rels: list[str]) -> str:
        docs = [(files[r]["loc"], files[r]["d"]) for r in rels if files[r]["d"] and not files[r]["test"]]
        return max(docs)[1] if docs else ""

    def split(parent: str, rels: list[str], prefix: str, depth: int):
        """Files directly in `prefix` stay on the part; sub-folders with 3+ files become children when the part is big."""
        if len(rels) <= 24 or depth >= 3:
            for r in rels:
                assign[r] = parent
            return
        groups: dict[str, list[str]] = defaultdict(list)
        for r in rels:
            rest = r[len(prefix):].lstrip("/") if prefix else r
            groups[rest.split("/")[0] if "/" in rest else ""].append(r)
        for key, members in sorted(groups.items()):
            if key and len(members) >= 3:
                nid = f"{parent}.{_slug(key)}"
                add(nid, parent, humanize(key), "feature" if depth else "library", summary_of(members), [f"{prefix}/{key}".lstrip("/")])
                split(nid, members, f"{prefix}/{key}".lstrip("/"), depth + 1)
            else:
                for r in members:
                    assign[r] = parent

    tests = [r for r, f in files.items() if f["test"]]
    rest = [r for r in files if r not in set(tests)]
    tops: dict[str, list[str]] = defaultdict(list)
    for r in rest:
        tops[r.split("/")[0] if "/" in r else "."].append(r)
    for top, rels in sorted(tops.items()):
        if top == ".":
            kind, label = "config", "Project files"
        else:
            label = humanize(top)
            low = top.lower()
            langs = Counter(files[r]["l"] for r in rels)
            kind = ("script" if low in SCRIPT_DIRS else "infra" if low in INFRA_DIRS else "service" if any(r in route_files for r in rels)
                    else "ui" if langs.get("html") or (langs.get("javascript", 0) + langs.get("typescript", 0)) > len(rels) / 2 else "library")
        nid = _slug(top)
        add(nid, None, label, kind, summary_of(rels), [] if top == "." else [top])
        split(nid, rels, "" if top == "." else top, 0)
    if tests:
        add("tests", None, "Tests", "test", "The tests that check the rest.", [])
        areas: dict[str, list[str]] = defaultdict(list)
        for r in tests:
            segs = r.split("/")
            areas["/".join(segs[:2]) if segs[0].lower() in ("tests", "test", "__tests__", "spec") and len(segs) > 2 else segs[0] if len(segs) > 1 else "."].append(r)
        for area, rels in sorted(areas.items()):
            if len(areas) == 1 or len(rels) < 2:
                for r in rels:
                    assign[r] = "tests"
                continue
            nid = "tests." + _slug(area)
            label = humanize(area.split("/")[-1] if area.lower().startswith(("tests/", "test/")) else area)
            add(nid, "tests", label + " tests", "test", f"Tests of {label}.", [area])
            for r in rels:
                assign[r] = nid
    return nodes, assign


# ------------------------------------------------------------------ outside parts
def _bare_imports(rel: str, text: str) -> set[str]:
    out = set()
    if rel.endswith(".py"):
        for m in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_]\w*)", text, re.M):
            out.add(m.group(1))
    elif rel.endswith((".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")):
        for m in re.finditer(r"""(?:from\s*|require\(\s*|import\(\s*|import\s+)['"]((?:@[\w.-]+/)?[A-Za-z][\w.-]*)(?:/[^'"]*)?['"]""", text):
            out.add(m.group(1))
    return out


def _externals(nodes: list[dict], files: dict, texts: dict, cfg: dict | None) -> list[dict]:
    if cfg:
        return []
    local_tops = {r.split("/")[0].split(".")[0] for r in files} | {Path(r).stem for r in files}
    count: Counter = Counter()
    for rel, text in texts.items():
        for pkg in _bare_imports(rel, text):
            base = pkg.split("/")[0]
            if base not in STDLIB and base not in local_tops and base in KNOWN_PACKAGES:
                count[base] += 1
    hosts: Counter = Counter()
    for rel, text in texts.items():
        if files[rel]["test"] or not rel.endswith((".py", ".js", ".jsx", ".mjs", ".ts", ".tsx")):
            continue
        for m in re.finditer(r"https?://([A-Za-z0-9][\w.-]+\.[a-z]{2,})(?::\d+)?/", text):
            h = m.group(1).lower()
            if not SKIP_HOSTS.match(h) and "xxx" not in h and not re.search(r"(?i)python\.org|nodejs\.org|npmjs|pypi\.org|codeload\.github", h):
                hosts[h] += 1
    out, used = [], set()
    for base, n in count.most_common(6):
        label, summary = KNOWN_PACKAGES[base]
        if label in used:
            continue
        used.add(label)
        out.append({"id": "ext." + _slug(base), "parent": None, "label": label, "kind": "external", "summary": summary, "details": "", "tags": [], "paths": [], "packages": [base], "hosts": []})
    for h, n in hosts.most_common(4):
        out.append({"id": "ext." + _slug(h), "parent": None, "label": h, "kind": "external", "summary": f"A web service the code calls ({h}).", "details": "", "tags": [], "paths": [], "packages": [], "hosts": [h]})
    return out


def _external_links(files: dict, texts: dict, ext_nodes: list[dict]):
    pkg_links, host_links = [], []
    by_pkg = {p.split(":")[-1]: n["id"] for n in ext_nodes for p in n["packages"]}
    by_host = {h: n["id"] for n in ext_nodes for h in n["hosts"]}
    for rel, text in texts.items():
        for pkg in _bare_imports(rel, text):
            nid = by_pkg.get(pkg) or by_pkg.get(pkg.split("/")[0])
            if nid:
                pkg_links.append({"a": "f:" + rel, "b": "n:" + nid, "k": "import", "w": 1, "names": []})
        for h, nid in by_host.items():
            if h in text and not files[rel]["test"]:
                host_links.append({"a": "f:" + rel, "b": "n:" + nid, "k": "http", "w": 1, "names": []})
    return pkg_links, host_links


# ------------------------------------------------------------------ screens, tour, flows, project
def _screens(files: dict, texts: dict, cgfile: dict, routes: list[dict], links: list[dict], node_by_id: dict) -> list[dict]:
    found: dict[str, dict] = {}

    def add(sid, url, file, name, fw):
        if file in files and sid not in found:
            found[sid] = {"id": sid, "url": url, "file": file, "app": files[file]["n"], "fw": fw, "name": name, "description": files[file]["d"]}
    for rel, text in texts.items():
        if rel.endswith(".html") and not files[rel]["test"]:
            add("screen:" + rel, "/" + rel, rel, files[rel]["d"].split(":")[0] if files[rel]["d"] else humanize(rel.split("/")[-1]), "html")
        m = re.search(r"(?:^|/)app/(.*?)/?page\.(?:tsx|jsx|ts|js)$", rel)
        if m is not None and "/api/" not in rel:
            add("screen:" + rel, "/" + m.group(1), rel, humanize(m.group(1).split("/")[-1] or "home"), "next")
        # a table of screens loaded on demand:  name: { ..., load: () => import('./name.js') }
        for mm in re.finditer(r"""([A-Za-z_$][\w$]*)\s*:\s*\{[^{}]*?import\(\s*['"](\.[^'"]+)['"]\s*\)""", text):
            target = code_graph._js_target(set(files), rel, mm.group(2))
            if target and not files[target]["test"]:
                add(f"screen:{rel}:{mm.group(1)}", "#/" + mm.group(1), target, humanize(mm.group(1)), "hash-router")
        # react-router: <Route path="/x" element={<Comp />}/>
        for mm in re.finditer(r"""<Route[^>]*path=['"]([^'"]*)['"][^>]*(?:element=\{<([A-Z]\w*)|component=\{([A-Z]\w*))""", text):
            comp = mm.group(2) or mm.group(3)
            im = re.search(r"import\s+(?:\{[^}]*\b" + comp + r"\b[^}]*\}|" + comp + r")\s+from\s+['\"](\.[^'\"]+)['\"]", text)
            target = code_graph._js_target(set(files), rel, im.group(1)) if im else None
            if target:
                add(f"screen:{rel}:{mm.group(1)}", mm.group(1) or "/", target, humanize(comp), "react-router")
    # what is behind each screen
    out_links: dict[str, list[dict]] = defaultdict(list)
    for l in links:
        out_links[l["a"]].append(l)
    route_by_id = {r["id"]: r for r in routes}
    dataish = re.compile(r"(?i)(^|/)(db|database|models?|schema|repositor(?:y|ies)|migrations?|store|storage|dao)([/._]|$)")
    screens = []
    for s in found.values():
        behind, seen = [{"id": "f:" + s["file"], "kind": "screen"}], {"f:" + s["file"]}
        queue = deque([("f:" + s["file"], 0)])
        reached_files = [s["file"]]
        while queue and len(behind) < 40:
            cur, d = queue.popleft()
            for l in out_links.get(cur, []):
                if l["k"] == "import" and l["b"].startswith("f:") and l["b"] not in seen and d < 3:
                    seen.add(l["b"])
                    behind.append({"id": l["b"], "kind": "part"})
                    reached_files.append(l["b"][2:])
                    queue.append((l["b"], d + 1))
        servers = []
        for rf in reached_files:
            for l in out_links.get("f:" + rf, []):
                if l["k"] == "http" and l["b"].startswith("r:") and l["b"] not in seen:
                    seen.add(l["b"])
                    behind.append({"id": l["b"], "kind": "request"})
                    srv = "f:" + route_by_id[l["b"]]["f"]
                    if srv not in seen:
                        seen.add(srv)
                        behind.append({"id": srv, "kind": "server"})
                        servers.append(srv)
        for srv in servers:                      # data and outside services the server code uses
            q = deque([(srv, 0)])
            while q:
                cur, d = q.popleft()
                for l in out_links.get(cur, []):
                    b = l["b"]
                    if b in seen:
                        continue
                    if b.startswith("n:"):
                        seen.add(b)
                        behind.append({"id": b, "kind": "outside"})
                    elif l["k"] == "import" and d < 2:
                        seen.add(b)
                        behind.append({"id": b, "kind": "data" if dataish.search(b[2:]) else "part"})
                        q.append((b, d + 1))
        screens.append({**s, "behind": behind})
    screens.sort(key=lambda s: (s["app"], s["url"]))
    return screens[:80]


def _auto_flows(screens: list[dict]) -> list[dict]:
    best = sorted((s for s in screens if any(b["kind"] == "request" for b in s["behind"])), key=lambda s: -len(s["behind"]))[:3]
    flows = []
    for s in best:
        steps = [{"node": b["id"], "kind": b["kind"]} for b in s["behind"] if b["kind"] in ("screen", "request", "server", "data", "outside")]
        order = {"screen": 0, "request": 1, "server": 2, "data": 3, "outside": 4}
        steps.sort(key=lambda x: order[x["kind"]])
        if len(steps) >= 2:
            flows.append({"id": "auto:" + s["id"], "title": s["name"], "auto": True, "steps": steps[:7]})
    return flows


def _auto_tour(nodes: list[dict], node_by_id: dict) -> list[dict]:
    top = [n for n in nodes if not n.get("parent") and n["kind"] != "test"]
    top.sort(key=lambda n: -(n.get("stats", {}).get("loc", 0)))
    return [{"node": "n:" + n["id"], "title": n["label"], "note": n["summary"]} for n in top[:5]]


def _project(root: Path, cfg: dict | None, files: dict, nodes: list[dict]) -> dict:
    proj = (cfg or {}).get("project") or {}
    summary = proj.get("summary", "")
    if not summary:
        for name in ("README.md", "readme.md", "README.rst"):
            p = root / name
            if p.is_file():
                try:
                    body = p.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    break
                paras = [re.sub(r"[#>*`_\[\]]+|\(http[^)]*\)", "", b).strip() for b in re.split(r"\n\s*\n", body)]
                paras = [b for b in paras if len(b) > 40 and not b.startswith("|")]
                summary = " ".join(paras[0].split())[:400] if paras else ""
                break
    entries = proj.get("entrypoints") or [p for p, f in files.items() if f["entry"] and not f["test"] and re.search(r"(^|/)(studio|main|app|index|server|cli)\.(py|js|ts)$", p)][:4]
    return {"name": proj.get("name") or root.name, "summary": summary, "entrypoints": entries}
