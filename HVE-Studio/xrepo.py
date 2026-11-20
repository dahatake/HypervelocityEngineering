"""FR-1100: relations between the repositories of one application, read deterministically from their code.

Confirmed (確定):
  package   a dependency declaration whose name equals a package another repository declares
  function  a call of a function/class imported from another repository's package (resolved through the import)
  api       a literal HTTP request whose method and path match exactly one other repository's endpoint
Candidate (候補):
  api       the same request when several repositories provide a matching endpoint (destination not unique)
  data      a table defined (CREATE TABLE) in one repository and referenced by name in another;
            a message topic / queue name, or a data-file path, that appears in two repositories (name match only)

The code is only read (never run) and nothing is contacted.  PARAM-066 / PARAM-067 apply per repository.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import floorplan_routes
import repo_scan

MAX_FILE = 512_000      # PARAM-066
MAX_FUNCTIONS = 20_000  # PARAM-067
CODE = (".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
READ = CODE + (".sql",)
MANIFESTS = ("package.json", "pyproject.toml", "setup.cfg", "setup.py", "go.mod")
KINDS = ("package", "function", "api", "data")


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _norm_pkg(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _is_manifest(rel: str) -> bool:
    base = rel.rsplit("/", 1)[-1]
    return base in MANIFESTS or base.endswith(".csproj") or re.fullmatch(r"requirements[\w.-]*\.txt", base) is not None


def read_repo(root: Path) -> dict:
    files = repo_scan.list_files(root)
    if files is None:
        files = sorted(str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*")
                       if p.is_file() and ".git" not in p.parts)
    texts: dict[str, str] = {}
    unparsed = skipped_large = 0
    symlinks: dict = {}
    for rel in files:
        if repo_scan.excluded(rel) or not repo_scan.safe_file(root, rel, symlinks):
            continue
        ext = Path(rel).suffix.lower()
        wanted = ext in READ or _is_manifest(rel)
        if not wanted:
            if ext in repo_scan.SOURCE_EXTS:
                unparsed += 1
            continue
        path = root / rel
        try:
            if path.stat().st_size > MAX_FILE:
                skipped_large += 1
                continue
            texts[rel] = repo_scan.read_text(path)[0]
        except (OSError, UnicodeDecodeError, repo_scan.ScanError):
            unparsed += 1
    return {"texts": texts, "files": len(files), "unparsed": unparsed, "tooLarge": skipped_large}


# ---------------------------------------------------------------- packages
def declared_packages(texts: dict[str, str]) -> dict[str, dict]:
    out: dict[str, dict] = {}

    def add(name, rel, text, pos, modules=()):
        if name:
            out.setdefault(_norm_pkg(name), {"name": name, "file": rel, "line": _line(text, pos), "modules": set()})["modules"].update(modules)

    for rel, text in texts.items():
        base = rel.rsplit("/", 1)[-1]
        if base == "package.json":
            try:
                name = json.loads(text).get("name")
            except ValueError:
                continue
            if isinstance(name, str):
                add(name, rel, text, text.find('"name"'), [name])
        elif base == "pyproject.toml":
            m = re.search(r"^\[(?:project|tool\.poetry)\][^\[]*?^name\s*=\s*['\"]([^'\"]+)['\"]", text, re.M | re.S)
            if m:
                add(m.group(1), rel, text, m.start(1), [m.group(1).replace("-", "_").lower()])
        elif base == "setup.cfg":
            m = re.search(r"^\[metadata\][^\[]*?^name\s*=\s*(\S+)", text, re.M | re.S)
            if m:
                add(m.group(1), rel, text, m.start(1), [m.group(1).replace("-", "_").lower()])
        elif base == "setup.py":
            m = re.search(r"\bname\s*=\s*['\"]([^'\"]+)['\"]", text)
            if m:
                add(m.group(1), rel, text, m.start(1), [m.group(1).replace("-", "_").lower()])
        elif base == "go.mod":
            m = re.search(r"^module\s+(\S+)", text, re.M)
            if m:
                add(m.group(1), rel, text, m.start(1), [m.group(1)])
        elif base.endswith(".csproj"):
            m = re.search(r"<PackageId>([^<]+)</PackageId>", text)
            add(m.group(1) if m else base[:-7], rel, text, m.start(1) if m else 0)
    # Python: top-level packages (folders with __init__.py at the root or under src/) also name importable modules
    for rel in texts:
        parts = rel.split("/")
        if parts[-1] == "__init__.py" and (len(parts) == 2 or (len(parts) == 3 and parts[0] == "src")):
            for info in out.values():
                if info["file"].endswith(("pyproject.toml", "setup.cfg", "setup.py")):
                    info["modules"].add(parts[-2])
    return out


def dependencies(texts: dict[str, str]) -> list[tuple[str, str, int]]:
    deps: list[tuple[str, str, int]] = []
    for rel, text in texts.items():
        base = rel.rsplit("/", 1)[-1]
        if base == "package.json":
            try:
                data = json.loads(text)
            except ValueError:
                continue
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                for name in (data.get(key) or {}):
                    deps.append((name, rel, _line(text, max(0, text.find(f'"{name}"')))))
        elif base == "pyproject.toml":
            block = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.M | re.S)
            if block:
                for m in re.finditer(r"['\"]([A-Za-z0-9][A-Za-z0-9._-]*)", block.group(1)):
                    deps.append((m.group(1), rel, _line(text, block.start(1) + m.start())))
            poetry = re.search(r"^\[tool\.poetry\.dependencies\](.*?)(?=^\[|\Z)", text, re.M | re.S)
            if poetry:
                for m in re.finditer(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*=", poetry.group(1), re.M):
                    if m.group(1).lower() != "python":
                        deps.append((m.group(1), rel, _line(text, poetry.start(1) + m.start())))
        elif re.fullmatch(r"requirements[\w.-]*\.txt", base):
            for m in re.finditer(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", text, re.M):
                deps.append((m.group(1), rel, _line(text, m.start())))
        elif base == "go.mod":
            for m in re.finditer(r"^\s*(?:require\s+)?([a-zA-Z0-9.\-]+\.[a-z]{2,}/\S+)\s+v\S+", text, re.M):
                deps.append((m.group(1), rel, _line(text, m.start(1))))
        elif base.endswith(".csproj"):
            for m in re.finditer(r"<PackageReference\s+Include=\"([^\"]+)\"", text):
                deps.append((m.group(1), rel, _line(text, m.start())))
            for m in re.finditer(r"<ProjectReference\s+Include=\"([^\"]+)\"", text):
                deps.append((re.split(r"[\\/]", m.group(1))[-1].removesuffix(".csproj"), rel, _line(text, m.start())))
    return deps


# ---------------------------------------------------------------- functions
PY_DEF = re.compile(r"^(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)", re.M)
JS_DEF = re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function\*?|class|const|let|var)\s+([A-Za-z_$][\w$]*)", re.M)
PY_FROM = re.compile(r"^\s*from\s+([A-Za-z_][\w.]*)\s+import\s+\(?([^)\n]+(?:\n[^)\n]+)*?)\)?\s*$", re.M)
JS_IMPORT = re.compile(r"""import\s+(?:[A-Za-z_$][\w$]*\s*,\s*)?\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]""")
JS_REQUIRE = re.compile(r"""(?:const|let|var)\s*\{([^}]*)\}\s*=\s*require\(\s*['"]([^'"]+)['"]\s*\)""")


def definitions(texts: dict[str, str]) -> tuple[dict[str, dict], bool]:
    defs: dict[str, dict] = {}
    count, truncated = 0, False
    for rel, text in texts.items():
        pattern = PY_DEF if rel.endswith(".py") else JS_DEF if rel.endswith(CODE) else None
        if pattern is None:
            continue
        for m in pattern.finditer(text):
            count += 1
            if count > MAX_FUNCTIONS:
                truncated = True
                break
            defs.setdefault(m.group(1), {"file": rel, "line": _line(text, m.start(1))})
        if truncated:
            break
    return defs, truncated


def _imported_names(spec: str) -> list[tuple[str, str]]:
    out = []
    for part in spec.split(","):
        part = part.strip().strip("()").strip()
        if not part or part == "*":
            continue
        m = re.match(r"([A-Za-z_$][\w$]*)(?:\s+as\s+|\s*:\s*)([A-Za-z_$][\w$]*)$", part)
        out.append((m.group(1), m.group(2)) if m else (part, part))
    return [(a, b) for a, b in out if re.fullmatch(r"[A-Za-z_$][\w$]*", a)]


def imports(texts: dict[str, str]) -> list[dict]:
    """(file, module, name, local alias, line) of named imports."""
    out = []
    for rel, text in texts.items():
        if rel.endswith(".py"):
            for m in PY_FROM.finditer(text):
                for name, alias in _imported_names(m.group(2).replace("\n", " ")):
                    out.append({"file": rel, "module": m.group(1), "name": name, "alias": alias, "line": _line(text, m.start())})
        elif rel.endswith(CODE):
            for rx in (JS_IMPORT, JS_REQUIRE):
                for m in rx.finditer(text):
                    for name, alias in _imported_names(m.group(1)):
                        out.append({"file": rel, "module": m.group(2), "name": name, "alias": alias, "line": _line(text, m.start())})
    return out


# ---------------------------------------------------------------- data
CREATE_TABLE = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[`\"\[]?\w+[`\"\]]?\.)?[`\"\[]?(\w+)", re.I)
TABLE_REF = re.compile(r"""\b(?:FROM|JOIN|INTO|UPDATE)\s+[`"\[]?(\w+)|__tablename__\s*=\s*['"](\w+)['"]|@Table\(\s*name\s*=\s*"(\w+)"|\.(?:table|from)\(\s*['"](\w+)['"]""", re.I)
TOPIC = re.compile(r"""\b(?:topic|queue|channel|subject|stream)[A-Za-z_]*\s*[=:]\s*['"]([\w.\-/:]{3,})['"]|\.(?:publish|subscribe|send_message|consume|emit)\(\s*['"]([\w.\-/:]{3,})['"]""", re.I)
DATA_FILE = re.compile(r"""['"]((?:[\w.\-]+/)*[\w.\-]+\.(?:csv|parquet|jsonl|ndjson|xlsx|tsv))['"]""")
SQL_WORDS = {"select", "where", "set", "values", "the", "a", "an", "and", "or", "table", "dual", "information_schema"}


def data_names(texts: dict[str, str]) -> dict[str, list[dict]]:
    out = {"define": [], "use": [], "topic": [], "file": []}
    for rel, text in texts.items():
        if rel.endswith(".sql") or rel.endswith(CODE):
            for m in CREATE_TABLE.finditer(text):
                out["define"].append({"name": m.group(1).lower(), "file": rel, "line": _line(text, m.start())})
        if rel.endswith(CODE) or rel.endswith(".sql"):
            for m in TABLE_REF.finditer(text):
                name = next(g for g in m.groups() if g)
                if name.lower() not in SQL_WORDS:
                    out["use"].append({"name": name.lower(), "file": rel, "line": _line(text, m.start())})
        if rel.endswith(CODE):
            for m in TOPIC.finditer(text):
                out["topic"].append({"name": m.group(1) or m.group(2), "file": rel, "line": _line(text, m.start())})
            for m in DATA_FILE.finditer(text):
                out["file"].append({"name": m.group(1).lstrip("./"), "file": rel, "line": _line(text, m.start())})
    return out


# ---------------------------------------------------------------- the relations
def _rel(kind, certainty, label, a, afile, aline, b, bfile, bline):
    return {"kind": kind, "certainty": certainty, "label": label,
            "from": {"repo": a, "file": afile, "line": aline}, "to": {"repo": b, "file": bfile, "line": bline}}


def build(repos: list[dict]) -> dict:
    """repos: [{"name", "path"}].  Returns {"repos": [...stats], "relations": [...], "kinds": KINDS}."""
    info = []
    for r in repos:
        data = read_repo(Path(r["path"]))
        texts = data["texts"]
        code = {k: v for k, v in texts.items() if k.endswith(CODE)}
        defs, truncated = definitions(texts)
        info.append({**r, **data, "packages": declared_packages(texts), "deps": dependencies(texts), "defs": defs,
                     "truncated": truncated, "imports": imports(texts), "routes": floorplan_routes.extract(code),
                     "calls": floorplan_routes.http_calls(code), "data": data_names(texts)})
    relations: list[dict] = []
    owner_pkg = {pkg: (i, meta) for i in info for pkg, meta in i["packages"].items()}

    for a in info:
        # (a) package dependencies
        for name, rel, line in a["deps"]:
            hit = owner_pkg.get(_norm_pkg(name))
            if hit and hit[0] is not a:
                b, meta = hit
                relations.append(_rel("package", "confirmed", meta["name"], a["name"], rel, line, b["name"], meta["file"], meta["line"]))
        # (b) functions through imports of another repository's package / module
        for imp in a["imports"]:
            module = imp["module"]
            if module.startswith("."):
                continue
            if imp["file"].endswith(".py"):
                root_mod = module.split(".")[0]
            else:
                parts = module.split("/")
                root_mod = "/".join(parts[:2]) if module.startswith("@") else parts[0]
            for b in info:
                if b is a:
                    continue
                provides = _norm_pkg(root_mod) in b["packages"] or any(root_mod in meta["modules"] for meta in b["packages"].values())
                target = b["defs"].get(imp["name"]) if provides else None
                if not target:
                    continue
                text = a["texts"][imp["file"]]
                lines = text.splitlines()
                call = re.compile(r"(?<![\w$.])" + re.escape(imp["alias"]) + r"\s*\(")
                for no, ln in enumerate(lines, 1):
                    if no != imp["line"] and call.search(ln) and not re.match(r"\s*(?:def|class|function|import|from)\b", ln):
                        relations.append(_rel("function", "confirmed", imp["name"], a["name"], imp["file"], no,
                                              b["name"], target["file"], target["line"]))
        # (c) HTTP requests
        for rel, method, path, line in a["calls"]:
            if any(floorplan_routes.match(rt["p"], path) and rt["m"] in (method, "ANY") for rt in a["routes"]):
                continue  # served by the calling repository itself
            providers = []
            for b in info:
                if b is a:
                    continue
                for rt in b["routes"]:
                    if rt["m"] in (method, "ANY") and floorplan_routes.match(rt["p"], path):
                        providers.append((b, rt))
                        break
            certainty = "confirmed" if len(providers) == 1 else "candidate"
            for b, rt in providers:
                relations.append(_rel("api", certainty, f"{method} {rt['p']}", a["name"], rel, line, b["name"], rt["f"], rt["l"]))
        # (d) data by name: tables
        for use in a["data"]["use"]:
            for b in info:
                if b is a:
                    continue
                d = next((x for x in b["data"]["define"] if x["name"] == use["name"]), None)
                if d and not any(x["name"] == use["name"] for x in a["data"]["define"]):
                    relations.append(_rel("data", "candidate", "table " + use["name"], a["name"], use["file"], use["line"],
                                          b["name"], d["file"], d["line"]))
    # (d) topics / queues and data files shared by name (one candidate per pair and name)
    for key, word in (("topic", "message "), ("file", "file ")):
        for i, a in enumerate(info):
            for b in info[i + 1:]:
                for x in a["data"][key]:
                    y = next((y for y in b["data"][key] if y["name"] == x["name"]), None)
                    if y and not any(r["label"] == word + x["name"] and r["from"]["repo"] == a["name"] and r["to"]["repo"] == b["name"] for r in relations):
                        relations.append(_rel("data", "candidate", word + x["name"], a["name"], x["file"], x["line"],
                                              b["name"], y["file"], y["line"]))
    seen, unique = set(), []
    for r in relations:
        key = (r["kind"], r["label"], r["from"]["repo"], r["from"]["file"], r["from"]["line"], r["to"]["repo"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    unique.sort(key=lambda r: (KINDS.index(r["kind"]), r["certainty"] != "confirmed", r["from"]["repo"], r["from"]["file"], r["from"]["line"]))
    stats = [{"name": i["name"], "path": i["path"], "files": i["files"], "read": len(i["texts"]), "unparsed": i["unparsed"],
              "tooLarge": i["tooLarge"], "functionsTruncated": i["truncated"], "functions": len(i["defs"]),
              "endpoints": len(i["routes"])} for i in info]
    return {"repos": stats, "relations": unique, "kinds": list(KINDS),
            "limits": {"maxFileBytes": MAX_FILE, "maxFunctions": MAX_FUNCTIONS}}
