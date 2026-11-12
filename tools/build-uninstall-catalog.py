#!/usr/bin/env python3
"""build-uninstall-catalog.py - build tools/uninstall-catalog.json from the git history of this repository.

The catalog is what tools/uninstall.py knows about every toolkit version, including the ones without a manifest:
  * every file any version of tools/install.py shipped, at the path it was installed to in that version
    (e.g. users-guide/* was installed as users-guide/ before EABK-docs/ existed), with the content hash of every
    version of that file ever committed (CRLF normalised, like install.py's sha());
  * the management-data templates, manifests, config files, AGENTS.md block markers, .gitignore / .gitattributes
    headers and lines, backup suffixes and data-file defaults that any version used.

The raw material is each committed tools/install.py (parsed with ast, never executed) and every blob of each shipped
file (git log --raw + git cat-file --batch). Run it after changing what the toolkit ships or before a release:

  python tools/build-uninstall-catalog.py           # rewrite tools/uninstall-catalog.json
  python tools/build-uninstall-catalog.py --check   # exit 1 when the catalog is out of date (no write)
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tools" / "uninstall-catalog.json"
INSTALLER = "tools/install.py"
TEMPLATE_DIR = "tools/templates/"


def git(*args: str, data: Optional[bytes] = None) -> bytes:
    proc = subprocess.run(["git", *args], cwd=str(ROOT), input=data, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(f"ERROR build-uninstall-catalog: git {' '.join(args[:3])} failed: "
                         f"{proc.stderr.decode('utf-8', 'replace')[:300]}")
    return proc.stdout


def norm_sha(data: bytes) -> str:
    if b"\0" not in data:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def constants(src: str) -> Dict[str, object]:
    """Module-level UPPER_CASE literals of one installer version (tuples assignments included)."""
    out: Dict[str, object] = {}
    for node in ast.parse(src).body:
        targets = []
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    targets.append((t, node.value))
                elif isinstance(t, ast.Tuple) and isinstance(node.value, ast.Tuple):
                    targets.extend(zip(t.elts, node.value.elts))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            targets.append((node.target, node.value))
        for t, v in targets:
            if isinstance(t, ast.Name) and t.id.isupper():
                try:
                    out[t.id] = ast.literal_eval(v)
                except (ValueError, SyntaxError):
                    pass
    return out


def calls(src: str, name: str, consts: Dict[str, object]) -> List[tuple]:
    """Literal arguments of every `<x>.<name>(...)` call (names resolved through the module constants)."""
    found = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == name:
            vals = []
            for a in node.args:
                if isinstance(a, ast.Constant):
                    vals.append(a.value)
                elif isinstance(a, ast.Name) and a.id in consts:
                    vals.append(consts[a.id])
                else:
                    vals.append(None)
            found.append(tuple(vals))
    return found


def blob_hashes(paths: Set[str]) -> Dict[str, Set[str]]:
    """Every content any commit reachable from HEAD held at each path, plus the working tree. --full-history -m: also
    the contents that only entered through a merge or lived on a merged side branch (default history simplification
    and merge-less --raw would miss them; the verification matrix found such files)."""
    blobs: Dict[str, Set[str]] = {p: set() for p in paths}
    ordered = sorted(paths)
    for i in range(0, len(ordered), 200):
        raw = git("log", "--raw", "--no-abbrev", "--no-renames", "--full-history", "-m", "--format=", "--",
                  *ordered[i:i + 200])
        for line in raw.decode("utf-8", "replace").splitlines():
            if not line.startswith(":") or "\t" not in line:
                continue
            meta, path = line.split("\t", 1)
            new = meta.split()[3]
            if path in blobs and set(new) != {"0"}:
                blobs[path].add(new)
    ids = sorted({b for s in blobs.values() for b in s})
    sha_of: Dict[str, str] = {}
    if ids:
        out = git("cat-file", "--batch", data=("\n".join(ids) + "\n").encode())
        pos = 0
        while pos < len(out):
            nl = out.index(b"\n", pos)
            oid, _type, size = out[pos:nl].decode().split()
            body = out[nl + 1:nl + 1 + int(size)]
            sha_of[oid] = norm_sha(body)
            pos = nl + 1 + int(size) + 1
    hashes = {p: {sha_of[b] for b in s if b in sha_of} for p, s in blobs.items()}
    for p in paths:
        f = ROOT / p
        if f.is_file():
            hashes[p].add(norm_sha(f.read_bytes()))
    return hashes


def build() -> dict:
    commits = git("log", "--reverse", "--full-history", "--format=%H", "--", INSTALLER).decode().split()
    if not commits:
        raise SystemExit("ERROR build-uninstall-catalog: tools/install.py に履歴がありません（浅い clone なら git fetch --unshallow）")
    sources_of: Dict[str, Set[str]] = {}       # installed path -> source paths in this repository
    template_sources: Dict[str, Set[str]] = {}
    sets: Dict[str, Set] = {k: set() for k in ("manifests", "configs", "markers", "blocks", "data", "infixes")}
    ignore: Dict[str, Dict[str, Set[str]]] = {}
    versions = 0
    for c in [*commits, None]:
        src = ((ROOT / INSTALLER).read_text(encoding="utf-8") if c is None
               else git("show", f"{c}:{INSTALLER}").decode("utf-8", "replace"))
        try:
            k = constants(src)
        except SyntaxError:
            continue
        versions += int(c is not None)
        gsrc, gdest = k.get("GUIDE_SRC"), k.get("GUIDE_DEST")

        def dest(rel: str) -> str:
            if isinstance(gsrc, str) and isinstance(gdest, str) and rel.startswith(gsrc):
                return gdest + rel[len(gsrc):]
            return rel
        for rel in list(k.get("MANAGED") or []) + list(k.get("OBSOLETE") or []):
            sources_of.setdefault(dest(rel), set()).add(rel)
        for rel in k.get("TEMPLATES") or []:
            template_sources.setdefault(rel, set()).add(TEMPLATE_DIR + rel)
        for key, bucket in (("MANIFEST", "manifests"), ("CONFIG", "configs")):
            if isinstance(k.get(key), str):
                sets[bucket].add(k[key])
        if isinstance(k.get("BEGIN"), str) and isinstance(k.get("END"), str):
            sets["markers"].add((k["BEGIN"], k["END"]))
        for files in (k.get("DEFAULT_FILES") or {}).values() if isinstance(k.get("DEFAULT_FILES"), dict) else []:
            sets["data"].add(files)
        for args in calls(src, "ensure_block", k):
            if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
                sets["blocks"].add((args[0], args[1].strip()))
        for args in calls(src, "ensure_lines", k):
            if len(args) >= 3 and isinstance(args[0], str) and isinstance(args[1], list) and isinstance(args[2], str):
                entry = ignore.setdefault(args[0], {"headers": set(), "lines": set()})
                entry["headers"].add(args[2])
                entry["lines"].update(args[1])
        for lit in (n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)):
            if lit.startswith(".") and lit.endswith("-backup-"):
                sets["infixes"].add(lit)
    head = commits[-1]
    current = constants((ROOT / INSTALLER).read_text(encoding="utf-8"))
    gsrc, gdest = current.get("GUIDE_SRC", ""), current.get("GUIDE_DEST", "")
    hashes = blob_hashes({s for v in sources_of.values() for s in v} | {s for v in template_sources.values() for s in v})

    def merged(mapping: Dict[str, Set[str]]) -> Dict[str, List[str]]:
        return {d: sorted(set().union(*(hashes.get(s, set()) for s in srcs))) for d, srcs in sorted(mapping.items())}
    shipped = {(gdest + r[len(gsrc):]) if gsrc and r.startswith(gsrc) else r: r for r in current.get("MANAGED", [])}
    lib = (ROOT / "scripts" / "ebaklib.py").read_text(encoding="utf-8")
    version = next((l.split("=", 1)[1].strip().strip('"') for l in lib.splitlines() if l.startswith("TOOLKIT_VERSION")), "unknown")
    return {
        "schema": 1,
        "toolkit_version": version,
        "installer_versions": versions,
        "note": "generated by tools/build-uninstall-catalog.py from the git history; do not edit",
        "files": merged(sources_of),
        "current": dict(sorted(shipped.items())),
        "templates": merged(template_sources),
        "manifests": sorted(sets["manifests"]),
        "configs": sorted(sets["configs"]),
        "markers": sorted([list(m) for m in sets["markers"]]),
        "blocks": sorted([list(b) for b in sets["blocks"]]),
        "ignore": {f: {"headers": sorted(v["headers"]), "lines": sorted(v["lines"])} for f, v in sorted(ignore.items())},
        "backup_infixes": sorted(sets["infixes"]),
        "data": sorted(sets["data"] | set(template_sources)),
        "work_dirs": ["work"],
        "runs": {"branch_prefix": "run/", "worktree_infix": "-run-", "pool_dir": "worktrees"},
        "_head": head[:12],
    }


def render(cat: dict) -> str:
    body = {k: v for k, v in cat.items() if k != "_head"}
    return json.dumps(body, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="書き込まずに、カタログが最新かを確かめる（古ければ exit 1）")
    args = ap.parse_args(argv)
    cat = build()
    text = render(cat)
    old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    n_hash = sum(len(v) for v in cat["files"].values())
    summary = (f"{len(cat['files'])} files / {n_hash} hashes / {cat['installer_versions']} installer versions "
               f"(toolkit {cat['toolkit_version']}, HEAD {cat['_head']})")
    if args.check:
        if old == text:
            print(f"uninstall-catalog: up to date: {summary}")
            return 0
        print("uninstall-catalog: out of date. Run: python tools/build-uninstall-catalog.py", file=sys.stderr)
        return 1
    if old != text:
        OUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"uninstall-catalog: written {OUT.relative_to(ROOT).as_posix()}: {summary}")
    else:
        print(f"uninstall-catalog: unchanged: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
