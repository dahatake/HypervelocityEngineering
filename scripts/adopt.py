#!/usr/bin/env python3
"""adopt.py - bring an existing application (code, design documents, tests) under EABK.

Three layers, each with a different trust level (see users-guide/10-adopting-existing-apps.md):
  1. Facts       `scan`    deterministic inventory of the repository (no LLM). docs/baseline/inventory.{json,md}
  2. Hypotheses  `anchor`  evidence anchors for requirements recovered from code (rd-author writes them as
                           出自: 逆生成 / 決定状態: 承認待ち). Each anchor pins a file range by hash.
  3. Pinned      `golden`  characterization (golden master) cases: record today's observable behaviour, replay later.
`check` reports evidence drift, recovery coverage and unsafe approvals.

Usage:
  python scripts/adopt.py scan [--since-days 365] [--json]
  python scripts/adopt.py request [--clusters 6] [--cluster NAME] [--implement] [--stdout]   # /build request draft
  python scripts/adopt.py anchor SRC-003 src/orders.py:10-48 [src/db.py] [--note "..."]
  python scripts/adopt.py check [--strict] [--json]
  python scripts/adopt.py golden add NAME [--stdin TEXT] [--cwd DIR] [--env K=V] -- CMD ARG...
  python scripts/adopt.py golden record [NAME...] [--update]
  python scripts/adopt.py golden check [NAME...]
  python scripts/adopt.py golden list

Never edits docs/requirements-definition.md (G-1) and never assigns toolkit IDs (G-3).
Writes only under docs/baseline/ (facts, evidence), tests/system/golden/ (pinned behaviour) and work/import/ (request drafts).
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402

BASELINE = "docs/baseline"
INVENTORY = f"{BASELINE}/inventory.json"
INVENTORY_MD = f"{BASELINE}/inventory.md"
EVIDENCE = f"{BASELINE}/evidence.json"
GOLDEN_SPEC = "tests/system/golden/golden.json"
GOLDEN_DIR = "tests/system/golden/snapshots"

LANGS = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".java": "java", ".kt": "kotlin", ".cs": "csharp", ".go": "go",
    ".rb": "ruby", ".php": "php", ".rs": "rust", ".swift": "swift", ".scala": "scala", ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp", ".vb": "vb", ".sql": "sql", ".sh": "shell", ".ps1": "powershell",
    ".cbl": "cobol", ".cob": "cobol", ".html": "html", ".css": "css", ".vue": "vue", ".svelte": "svelte",
}
DOC_EXT = {".md", ".rst", ".txt", ".adoc", ".docx", ".xlsx", ".pptx", ".pdf", ".drawio", ".puml", ".plantuml", ".mmd"}
CONFIG_EXT = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".properties", ".env", ".conf"}
MANIFEST_NAMES = {"package.json", "pyproject.toml", "requirements.txt", "pom.xml", "build.gradle", "go.mod", "Cargo.toml",
                  "Gemfile", "composer.json", "setup.py", "Pipfile", "build.gradle.kts"}
ENTRY_NAMES = {"main.py", "__main__.py", "app.py", "wsgi.py", "asgi.py", "manage.py", "index.js", "server.js", "app.js",
               "main.ts", "index.ts", "Program.cs", "Startup.cs", "main.go", "Main.java", "Application.java", "main.rs",
               "main.c", "main.cpp", "index.php"}
SKIP_DIRS = {"node_modules", "vendor", "dist", "build", "target", "bin", "obj", "__pycache__", ".venv", "venv",
             ".git", "site-packages", ".idea", ".vscode", "coverage"}
GENERIC_DIRS = {"src", "lib", "app", "apps", "main", "java", "source", "pkg", "internal", "cmd", "packages", "services"}
TOOLKIT_PREFIXES = ("scripts/hooks/", "tools/templates/", ".github/agents/", ".github/skills/", ".github/hooks/", ".github/workflows/ebak-", "EABK-Studio/",
                    "tests/system/", "tests/toolkit/", "work/", f"{BASELINE}/")
TOOLKIT_FILES = {"AGENTS.md", ".github/copilot-instructions.md", ".github/ebak-toolkit.json", "docs/catalog.md",
                 "docs/id-registry.md", "docs/run-history.md", "docs/requirements-definition.md"}
DESIGN_HINT = re.compile(r"design|設計|architecture|アーキ|spec|仕様|requirement|要件|要求|adr|decision|openapi|swagger|"
                         r"erd|er-|データモデル|schema|interface|api|画面|基本設計|詳細設計", re.I)
ROUTE_PATTERNS = [
    (re.compile(r"""@(?:\w+\.)?(get|post|put|delete|patch|route)\(\s*['"]([^'"]+)['"]""", re.I), "decorator"),
    (re.compile(r"""\b(?:app|router|server)\.(get|post|put|delete|patch)\(\s*['"`]([^'"`]+)['"`]""", re.I), "express"),
    (re.compile(r"""@(Get|Post|Put|Delete|Patch|Request)Mapping\(\s*(?:value\s*=\s*)?\{?\s*"([^"]*)"""), "spring"),
    (re.compile(r"""\[Http(Get|Post|Put|Delete|Patch)(?:\(\s*"([^"]*)"\s*\))?\]"""), "aspnet"),
    (re.compile(r"""\bpath\(\s*['"]([^'"]+)['"]\s*,"""), "django"),
    (re.compile(r"""\bhttp\.HandleFunc\(\s*"([^"]+)\""""), "go"),
]
TABLE_PATTERNS = [
    re.compile(r"""create\s+table\s+(?:if\s+not\s+exists\s+)?[`"\[]?([\w.]+)[`"\]]?""", re.I),
    re.compile(r"""__tablename__\s*=\s*['"](\w+)['"]"""),
    re.compile(r"""\bclass\s+(\w+)\s*\(\s*(?:models\.Model|db\.Model|Base)\s*\)"""),
    re.compile(r"""^\s*model\s+(\w+)\s*\{""", re.M),
    re.compile(r"""\bDbSet<(\w+)>"""),
    re.compile(r"""@Table\(\s*name\s*=\s*"(\w+)\""""),
]
REF_RE = re.compile(r"\b([A-Z]{2,6}-\d{1,5})\b")
RANGE_RE = re.compile(r"^(?P<path>.+?)(?::(?P<a>\d+)(?:-(?P<b>\d+))?)?$")


def sha16(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()[:16]


def classify(rel: str) -> Tuple[str, str]:
    p = Path(rel)
    ext, name, low = p.suffix.lower(), p.name, rel.lower()
    lang = LANGS.get(ext, "")
    parts = {x.lower() for x in p.parts[:-1]}
    if parts & {"test", "tests", "__tests__", "spec", "specs", "e2e"} or re.search(r"(^|[._-])(test|spec)s?([._-]|$)", name.lower()):
        return "test", lang
    if name in MANIFEST_NAMES:
        return "manifest", lang
    if ext == ".sql" or "migration" in low or ext == ".prisma":
        return "schema", lang
    if low.startswith(".github/workflows/") or name in {"Dockerfile", "docker-compose.yml", "Jenkinsfile", ".gitlab-ci.yml"}:
        return "ci", lang
    if ext in DOC_EXT:
        return ("design" if DESIGN_HINT.search(rel) else "doc"), lang
    if ext in {".yaml", ".yml", ".json"} and re.search(r"openapi|swagger", low):
        return "design", lang
    if lang and lang not in {"html", "css"}:
        return "source", lang
    if lang in {"html", "css"}:
        return "asset", lang
    if ext in CONFIG_EXT:
        return "config", lang
    return "other", lang


def read_bytes(root: Path, rel: str) -> Optional[bytes]:
    try:
        return (root / rel).read_bytes()
    except OSError:
        return None


def candidate_files(root: Path) -> List[str]:
    out = []
    managed = set((h.read_json(root / ".github/ebak-toolkit.json", {}) or {}).get("files", {}))
    for rel in h.tracked_files(root, include_untracked=True):
        if rel in TOOLKIT_FILES or rel in managed or rel.startswith(TOOLKIT_PREFIXES):
            continue
        if rel.startswith("scripts/") and Path(rel).name in _toolkit_scripts():
            continue
        if SKIP_DIRS & set(rel.split("/")[:-1]):
            continue
        out.append(rel)
    return sorted(set(out))


_TK: Optional[set] = None


def _toolkit_scripts() -> set:
    global _TK
    if _TK is None:
        _TK = {n for n in ("ebaklib.py", "rdcheck.py", "rdfix.py", "verify.py", "verify.ps1", "verify.sh", "next-id.py",
                           "ledger.py", "select-tests.py", "summarize.py", "clean-work.py", "run-state.py", "integrate.py",
                           "kpi.py", "import-speckit.py", "adopt.py", "ebak.config.json")}
    return _TK


def churn(root: Path, since_days: int) -> Counter:
    code, out = h.git(["log", f"--since={since_days}.days", "--name-only", "--pretty=format:", "--no-renames"], root)
    c: Counter = Counter()
    if code == 0:
        for line in out.splitlines():
            if line.strip():
                c[line.strip()] += 1
    return c


def cluster_key(rel: str) -> str:
    parts = rel.split("/")[:-1]
    while parts and parts[0].lower() in GENERIC_DIRS and len(parts) > 1:
        parts = parts[1:]
    return "/".join(parts[:2]) if parts else "(root)"


def scan(root: Path, since_days: int) -> dict:
    cfg = h.load_config(root)
    files, routes, tables, refs = [], [], [], Counter()
    entry_points: List[str] = []
    ch = churn(root, since_days)
    for rel in candidate_files(root):
        data = read_bytes(root, rel)
        if data is None:
            continue
        role, lang = classify(rel)
        binary = b"\0" in data[:4096]
        text = "" if binary or len(data) > 1_500_000 else data.decode("utf-8", "replace")
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        files.append({"path": rel, "role": role, "lang": lang, "lines": lines, "bytes": len(data), "hash": sha16(data),
                      "churn": ch.get(rel, 0)})
        if Path(rel).name in ENTRY_NAMES and role == "source":
            entry_points.append(rel)
        if role in ("source", "schema") and text:
            for i, line in enumerate(text.splitlines(), 1):
                for pat, kind in ROUTE_PATTERNS:
                    m = pat.search(line)
                    if m and role == "source":
                        g = m.groups()
                        method, path = (g[0].upper(), g[1] or "") if len(g) > 1 else ("ANY", g[0])
                        if method in ("ROUTE", "REQUEST"):
                            mm = re.search(r"methods\s*=\s*[\[(]([^\])]+)", line)
                            method = re.sub(r"['\"\s]", "", mm.group(1)).upper() if mm else "ANY"
                        if path.startswith("/") or kind in ("spring", "aspnet", "django"):
                            routes.append({"method": method, "path": path, "file": rel, "line": i, "kind": kind})
            for pat in TABLE_PATTERNS:
                for m in pat.finditer(text):
                    tables.append({"name": m.group(1), "file": rel, "line": text.count("\n", 0, m.start()) + 1})
        if role in ("doc", "design") and text:
            refs.update(REF_RE.findall(text))
    src = [f for f in files if f["role"] == "source"]
    clusters: Dict[str, dict] = {}
    for f in files:
        if f["role"] not in ("source", "test", "schema"):
            continue
        k = cluster_key(f["path"])
        c = clusters.setdefault(k, {"name": k, "source": [], "tests": [], "schema": [], "lines": 0, "churn": 0,
                                    "routes": 0, "tables": []})
        c["source" if f["role"] == "source" else "tests" if f["role"] == "test" else "schema"].append(f["path"])
        if f["role"] == "source":
            c["lines"] += f["lines"]
            c["churn"] += f["churn"]
    for r in routes:
        k = cluster_key(r["file"])
        if k in clusters:
            clusters[k]["routes"] += 1
    for t in tables:
        k = cluster_key(t["file"])
        if k in clusters:
            clusters[k]["tables"].append(t["name"])
    for c in clusters.values():
        c["tables"] = sorted(set(c["tables"]))
        c["hotspot"] = round(c["churn"] * (c["lines"] ** 0.5), 1)
        # tested == has a test file that shares a path component with a source file
        c["has_tests"] = bool(c["tests"])
    ordered = sorted((c for c in clusters.values() if c["source"]), key=lambda c: (-c["hotspot"], -c["lines"], c["name"]))
    return {
        "version": 1,
        "toolkit": h.TOOLKIT_VERSION,
        "commit": h.head_commit(root),
        "generated": h.now_iso(),
        "since_days": since_days,
        "summary": {
            "files": len(files),
            "by_role": dict(Counter(f["role"] for f in files)),
            "by_lang": dict(Counter(f["lang"] for f in src).most_common()),
            "source_lines": sum(f["lines"] for f in src),
            "test_files": sum(1 for f in files if f["role"] == "test"),
            "design_docs": sum(1 for f in files if f["role"] in ("design", "doc")),
            "routes": len(routes),
            "tables": len({t["name"] for t in tables}),
        },
        "entry_points": entry_points,
        "routes": routes,
        "tables": tables,
        "doc_reference_prefixes": dict(Counter(k.split("-")[0] for k in refs).most_common(10)),
        "clusters": ordered,
        "files": files,
    }


def render_md(inv: dict) -> str:
    s = inv["summary"]
    L = ["# 既存アプリの棚卸し（adopt.py scan の出力）", "",
         "> 決定的な事実だけを集めたものです（LLM は使っていません）。要求ではありません。要求の仮説は rd-author が、",
         "> 出典（SRC）と証跡の固定（`adopt.py anchor`）を付けて、「承認待ち」で書きます。", "",
         f"- 基準の commit: `{inv['commit'][:12]}`　生成: {inv['generated']}　churn の集計期間: {inv['since_days']} 日",
         f"- ファイル {s['files']} 件（{', '.join(f'{k} {v}' for k, v in sorted(s['by_role'].items()))}）",
         f"- 言語（ソース行数 {s['source_lines']}）: {', '.join(f'{k} {v}' for k, v in s['by_lang'].items()) or '-'}",
         f"- テストファイル {s['test_files']} 件 / 設計・文書 {s['design_docs']} 件 / ルート {s['routes']} 件 / テーブル {s['tables']} 件", ""]
    if inv["entry_points"]:
        L += ["## 入口の候補", ""] + [f"- `{p}`" for p in inv["entry_points"][:20]] + [""]
    L += ["## 機能のまとまりの候補（変更の多さ × 規模の順）", "",
          "回収（要求の仮説づくり）はこの順に、1 まとまりずつ行います。churn の多いところは変更が集まる所で、挙動を固定する価値が最も高い所です。", "",
          "| まとまり | ソース | 行数 | churn | ルート | テーブル | テスト |", "|---|---|---|---|---|---|---|"]
    for c in inv["clusters"][:40]:
        L.append(f"| `{c['name']}` | {len(c['source'])} | {c['lines']} | {c['churn']} | {c['routes']} | "
                 f"{', '.join(c['tables'][:4]) or '-'} | {len(c['tests'])} |")
    if inv["doc_reference_prefixes"]:
        L += ["", "## 既存の設計書にある ID の接頭辞（既存の要求・設計番号の手がかり）", "",
              ", ".join(f"`{k}-`×{v}" for k, v in inv["doc_reference_prefixes"].items()), ""]
    docs = [f for f in inv["files"] if f["role"] == "design"][:30]
    if docs:
        L += ["", "## 設計書の候補", ""] + [f"- `{f['path']}`" for f in docs]
    return "\n".join(L).rstrip() + "\n"


def cmd_scan(root: Path, a) -> int:
    inv = scan(root, a.since_days)
    h.write_json(root / INVENTORY, inv)
    h.write_text_atomic(root / INVENTORY_MD, render_md(inv))
    s = inv["summary"]
    print(f"SCAN files={s['files']} source_lines={s['source_lines']} clusters={len(inv['clusters'])} "
          f"routes={s['routes']} tables={s['tables']} tests={s['test_files']}")
    print(f"WROTE {INVENTORY} / {INVENTORY_MD}")
    if a.json:
        print(json.dumps(inv["summary"], ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- anchors
def range_hash(root: Path, path: str, a: Optional[int], b: Optional[int]) -> Optional[str]:
    data = read_bytes(root, path)
    if data is None:
        return None
    if a is None:
        return sha16(data)
    lines = data.decode("utf-8", "replace").splitlines()
    seg = lines[a - 1:(b or a)]
    if not seg:
        return None
    # whitespace-insensitive so that reformatting alone does not count as drift
    return sha16("\n".join(re.sub(r"\s+", " ", x).strip() for x in seg).encode("utf-8"))


def cmd_anchor(root: Path, a) -> int:
    if not re.fullmatch(r"SRC-\d{3,}", a.src):
        print("ERROR anchor: 最初の引数は SRC-xxx（出典台帳の ID。採番は next-id.py）です")
        return 2
    ev = h.read_json(root / EVIDENCE, {"version": 1, "anchors": {}}) or {"version": 1, "anchors": {}}
    items, bad = [], 0
    for spec in a.targets:
        m = RANGE_RE.match(spec.replace("\\", "/"))
        path, s, e = m.group("path"), m.group("a"), m.group("b")
        s_i, e_i = (int(s) if s else None), (int(e) if e else (int(s) if s else None))
        digest = range_hash(root, path, s_i, e_i)
        if digest is None:
            print(f"ERROR anchor: {spec} が読めません（ファイルがない、または範囲が空）")
            bad += 1
            continue
        items.append({"path": path, "start": s_i, "end": e_i, "hash": digest, "note": a.note or ""})
    if bad:
        return 2
    ev.setdefault("anchors", {}).setdefault(a.src, [])
    known = {(x["path"], x["start"], x["end"]): x for x in ev["anchors"][a.src]}
    for it in items:
        known[(it["path"], it["start"], it["end"])] = it
    ev["anchors"][a.src] = list(known.values())
    h.write_json(root / EVIDENCE, ev)
    print(f"ANCHOR {a.src} {len(items)} 件を固定（{EVIDENCE}）")
    return 0


# ---------------------------------------------------------------- check
def cmd_check(root: Path, a) -> int:
    cfg = h.load_config(root)
    errors: List[str] = []
    warns: List[str] = []
    inv = h.read_json(root / INVENTORY)
    ev = (h.read_json(root / EVIDENCE) or {}).get("anchors", {})
    if not inv:
        errors.append(f"棚卸しがありません。`python scripts/adopt.py scan` を実行します（{INVENTORY}）")
    # drift: anchored evidence changed or vanished
    drift = []
    for src, items in ev.items():
        for it in items:
            now = range_hash(root, it["path"], it.get("start"), it.get("end"))
            loc = it["path"] + (f":{it['start']}-{it['end']}" if it.get("start") else "")
            if now is None:
                drift.append(f"{src} {loc} が見つかりません（削除・移動・行範囲の変化）")
            elif now != it["hash"]:
                drift.append(f"{src} {loc} の内容が変わっています（証跡の再確認が必要）")
    for d in drift:
        warns.append("DRIFT " + d)
    doc = h.parse_requirements(root, cfg)
    reverse = [r for r in doc.requirements.values() if r.active and "逆生成" in r.fields.get("出自", "")]
    src_ids = set(doc.kind_ids("SRC"))
    for r in reverse:
        cited = set(re.findall(r"SRC-\d{3,}", r.fields.get("出典", "")))
        anchored = [s for s in cited if s in ev]
        if not cited:
            errors.append(f"{r.id}: 出自が逆生成なのに出典（SRC-ID）がありません（根拠のない仮説は書きません）")
        elif not anchored:
            msg = f"{r.id}: 出典 {', '.join(sorted(cited))} に証跡の固定がありません（`adopt.py anchor`）"
            (errors if r.state == "承認済み" else warns).append(msg)
        for s in cited - src_ids:
            errors.append(f"{r.id}: 出典 {s} が出典台帳（§11）にありません")
        if r.state == "承認済み" and "包括承認" in r.state_raw:
            errors.append(f"{r.id}: 逆生成の要求は包括承認できません（現状が意図どおりかは利用者だけが判断できます）")
    # coverage: how much of the source is claimed by the catalog, requirements or anchors
    cov = None
    if inv:
        src_files = [f for f in inv["files"] if f["role"] == "source"]
        text = h.read_text(root / h.mf(cfg, "catalog")) if (root / h.mf(cfg, "catalog")).exists() else ""
        text += "\n" + "\n".join(doc.text.values())
        claimed = {f["path"] for f in src_files if f["path"] in text}
        claimed |= {it["path"] for items in ev.values() for it in items}
        lines_all = sum(f["lines"] for f in src_files) or 1
        lines_claimed = sum(f["lines"] for f in src_files if f["path"] in claimed)
        cov = {"files": f"{len(claimed & {f['path'] for f in src_files})}/{len(src_files)}",
               "lines_pct": round(100 * lines_claimed / lines_all, 1)}
        gaps = [c for c in inv["clusters"][:10] if not any(p in claimed for p in c["source"])]
        for c in gaps[:5]:
            warns.append(f"GAP {c['name']}（hotspot {c['hotspot']}）はまだ要求・カタログに回収されていません")
        if inv.get("commit") and inv["commit"] != h.head_commit(root):
            warns.append("STALE 棚卸しの基準の commit が HEAD と違います（`adopt.py scan` で更新）")
    gold = golden_status(root)
    summary = {"reverse_requirements": len(reverse), "anchors": sum(len(v) for v in ev.values()), "drift": len(drift),
               "coverage": cov, "golden_cases": gold["cases"], "golden_unrecorded": gold["unrecorded"]}
    if a.json:
        print(json.dumps({"errors": errors, "warnings": warns, "summary": summary}, ensure_ascii=False, indent=2))
    else:
        for e in errors:
            print("ERROR " + e)
        for w in warns:
            print("WARN " + w)
        print(f"ADOPT reverse_requirements={len(reverse)} anchors={summary['anchors']} drift={len(drift)} "
              f"coverage={cov['lines_pct'] if cov else '-'}% golden={gold['cases']}(未記録 {gold['unrecorded']})")
    return 1 if errors or (a.strict and warns) else 0


# ---------------------------------------------------------------- golden master
NORMALIZERS = [
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<TIMESTAMP>"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<UUID>"),
    (re.compile(r"0x[0-9a-fA-F]{6,}"), "<ADDR>"),
]


def normalize(text: str, root: Path, extra: List[dict]) -> str:
    text = text.replace("\r\n", "\n").replace(str(root), "<ROOT>").replace(root.as_posix(), "<ROOT>")
    for pat, rep in NORMALIZERS:
        text = pat.sub(rep, text)
    for n in extra or []:
        text = re.sub(n["regex"], n.get("replace", "<X>"), text)
    return text


def load_spec(root: Path) -> dict:
    return h.read_json(root / GOLDEN_SPEC, {"version": 1, "cases": []}) or {"version": 1, "cases": []}


def snap_path(root: Path, name: str) -> Path:
    return root / GOLDEN_DIR / f"{name}.json"


def run_case(root: Path, case: dict) -> dict:
    env = {**os.environ, "PYTHONHASHSEED": "0", "TZ": "UTC", "LC_ALL": "C.UTF-8", **(case.get("env") or {})}
    try:
        p = subprocess.run(case["argv"], cwd=str(root / case.get("cwd", ".")), input=case.get("stdin"), env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=case.get("timeout", 60))
        res = {"exit": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except subprocess.TimeoutExpired:
        res = {"exit": "timeout", "stdout": "", "stderr": ""}
    except OSError as e:
        res = {"exit": "error", "stdout": "", "stderr": str(e)}
    extra = case.get("normalize")
    return {"exit": res["exit"], "stdout": normalize(res["stdout"], root, extra), "stderr": normalize(res["stderr"], root, extra)}


def golden_status(root: Path) -> dict:
    spec = load_spec(root)
    cases = spec.get("cases", [])
    return {"cases": len(cases), "unrecorded": sum(1 for c in cases if not snap_path(root, c["name"]).exists())}


def pick(spec: dict, names: List[str]) -> List[dict]:
    cases = spec.get("cases", [])
    return [c for c in cases if not names or c["name"] in names]


def cmd_golden(root: Path, a) -> int:
    spec = load_spec(root)
    if a.action == "list":
        for c in spec["cases"]:
            print(f"{c['name']}  {'recorded' if snap_path(root, c['name']).exists() else 'unrecorded'}  {' '.join(c['argv'])}")
        return 0
    if a.action == "add":
        if not a.name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", a.name) or not a.cmd:
            print("ERROR golden add: NAME（英数字と _ . -）と `-- コマンド` が必要です")
            return 2
        case = {"name": a.name, "argv": a.cmd}
        for k, v in (("stdin", a.stdin), ("cwd", a.cwd)):
            if v:
                case[k] = v
        if a.env:
            case["env"] = dict(x.split("=", 1) for x in a.env)
        spec["cases"] = [c for c in spec["cases"] if c["name"] != a.name] + [case]
        h.write_json(root / GOLDEN_SPEC, spec)
        print(f"ADDED {a.name}（次に `golden record {a.name}`）")
        return 0
    names = ([a.name] if a.name else []) + (a.more or [])
    cases = pick(spec, names)
    if not cases:
        print("ERROR golden: 対象のケースがありません（`golden add`）")
        return 2
    fails = 0
    for c in cases:
        first = run_case(root, c)
        sp = snap_path(root, c["name"])
        if a.action == "record":
            second = run_case(root, c)
            if first != second:
                print(f"NONDETERMINISTIC {c['name']}: 同じ入力で出力が変わります。`normalize`（regex の置換）を spec に足すか、入力を固定してください")
                fails += 1
                continue
            if sp.exists() and not a.update:
                print(f"SKIP {c['name']}: 記録済み（挙動の変更を承認して取り込むときだけ --update）")
                continue
            h.write_json(sp, first)
            print(f"RECORDED {c['name']} exit={first['exit']}")
        else:
            if not sp.exists():
                print(f"FAIL {c['name']}: 未記録です（`golden record`）")
                fails += 1
                continue
            want = h.read_json(sp)
            if want == first:
                print(f"PASS {c['name']}")
                continue
            fails += 1
            print(f"FAIL {c['name']}: 記録した挙動と違います")
            for key in ("exit", "stdout", "stderr"):
                if want.get(key) != first.get(key):
                    d = list(difflib.unified_diff(str(want.get(key)).splitlines(), str(first.get(key)).splitlines(),
                                                  f"recorded.{key}", f"actual.{key}", lineterm="", n=1))
                    print("\n".join(d[:20]))
    return 1 if fails else 0


def cmd_request(root: Path, a) -> int:
    inv = h.read_json(root / INVENTORY)
    if not inv:
        print("ERROR request: 先に `python scripts/adopt.py scan` を実行します")
        return 2
    ev = (h.read_json(root / EVIDENCE) or {}).get("anchors", {})
    done = {it["path"] for items in ev.values() for it in items}
    todo = [c for c in inv["clusters"] if not (set(c["source"]) & done)]
    if a.cluster:
        todo = [c for c in inv["clusters"] if c["name"] in a.cluster]
    todo = todo[:a.clusters]
    if not todo:
        print("NOTHING 回収していないまとまりがありません")
        return 0
    design = [f["path"] for f in inv["files"] if f["role"] == "design"][:30]
    L = ["<request>", "skill `adopt-existing` に従い、既存のアプリを EABK の管理下に入れてください（逆生成の要求の仮説・出典と証跡・現状の挙動の固定）。",
         "新機能・変更・リファクタリングはしません。コードを変更せず、要求の決定状態は必ず「承認待ち」（出自: 逆生成）にします。",
         "今回回収するまとまり（変更の多さ × 規模の順。`docs/baseline/inventory.md` に根拠があります）:"]
    for c in todo:
        L.append(f"- `{c['name']}`: ソース {len(c['source'])} 件 / {c['lines']} 行 / churn {c['churn']} / ルート {c['routes']} / "
                 f"テーブル {', '.join(c['tables'][:5]) or '-'} / テスト {len(c['tests'])} 件")
    L += ["</request>", "<references>", f"{INVENTORY_MD}", *design, "</references>", "<run_options>",
          "max_hours: 8", "approval_policy: 厳格", "parallel_workers: auto",
          "scope: 承認済みすべて" if a.implement else "scope: なし",
          "git_push: しない", "deploy: しない", "external_write: しない", "paid_services: 使わない",
          "external_exposure: 公開しない", "</run_options>"]
    text = "\n".join(L) + "\n"
    if a.stdout:
        print(text)
        return 0
    out = root / "work" / "import" / f"adopt-{time.strftime('%Y%m%d%H%M')}.md"
    h.write_text_atomic(out, "# 既存アプリの導入: /build の依頼文（conductor に貼り付ける）\n\n```text\n" + text + "```\n")
    print(f"WROTE {out.relative_to(root).as_posix()}（{len(todo)} まとまり）。内容を /build の後に貼り付けます（Agent は conductor）")
    return 0


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--since-days", type=int, default=365)
    s.add_argument("--json", action="store_true")
    rq = sub.add_parser("request")
    rq.add_argument("--clusters", type=int, default=6)
    rq.add_argument("--cluster", action="append")
    rq.add_argument("--implement", action="store_true")
    rq.add_argument("--stdout", action="store_true")
    an = sub.add_parser("anchor")
    an.add_argument("src")
    an.add_argument("targets", nargs="+")
    an.add_argument("--note", default="")
    c = sub.add_parser("check")
    c.add_argument("--strict", action="store_true")
    c.add_argument("--json", action="store_true")
    g = sub.add_parser("golden")
    g.add_argument("action", choices=["add", "record", "check", "list"])
    g.add_argument("name", nargs="?")
    g.add_argument("more", nargs="*")
    g.add_argument("--update", action="store_true")
    g.add_argument("--stdin", default=None)
    g.add_argument("--cwd", default=None)
    g.add_argument("--env", action="append")
    args, rest = ap.parse_known_args(argv)
    root = h.repo_root(Path(args.root) if args.root else None)
    if args.cmd == "golden":
        args.cmd_list = None
        raw = list(argv if argv is not None else sys.argv[1:])
        args.cmd = raw[raw.index("--") + 1:] if "--" in raw else []
        if args.action == "add":
            # NAME is the only positional before `--`; strip extras that argparse swallowed from the command
            args.more = []
        return cmd_golden(root, args)
    return {"scan": cmd_scan, "anchor": cmd_anchor, "check": cmd_check, "request": cmd_request}[args.cmd](root, args)


if __name__ == "__main__":
    raise SystemExit(main())
