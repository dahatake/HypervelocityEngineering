"""Read-only, offline repository inventory. No repository code is executed."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

TEXT_MAX_BYTES = 1_000_000
SKIP_DIRS = {".git", "node_modules", "bin", "obj", "dist", "build", "out", "target",
             ".venv", "venv", "__pycache__", ".next", ".nuxt", "coverage", "vendor",
             ".idea", ".vs", "work", "TestResults"}
SOURCE_EXTS = {".py", ".cs", ".fs", ".vb", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
               ".vue", ".svelte", ".java", ".kt", ".kts", ".scala", ".go", ".rs", ".rb",
               ".php", ".swift", ".m", ".mm", ".c", ".h", ".cc", ".cpp", ".hpp", ".dart",
               ".lua", ".sql", ".ps1", ".psm1", ".sh", ".bash", ".r", ".jl", ".ex",
               ".exs", ".erl", ".clj", ".hs", ".ml", ".zig", ".nim", ".css", ".scss",
               ".html", ".razor", ".cshtml", ".xaml"}
DOC_EXTS = {".md", ".markdown", ".rst", ".txt"}
CONFIG_EXTS = {".json", ".yaml", ".yml", ".toml", ".xml", ".ini", ".cfg", ".csproj"}
SECRET_NAME = re.compile(r"(^\.env($|\.)|\.pem$|\.key$|^id_(rsa|ed25519)$|credentials|secrets?)", re.I)
CHECKBOX = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s+(.+)$")
TODO = re.compile(r"^\s*(?:#|//|/\*+|\*|--|<!--)\s*(TODO|FIXME)\b[:\s-]*(.+?)(?:\*/|-->)?\s*$")


class ScanError(Exception):
    pass


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=30,
                              env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ScanError(f"git: {exc}") from exc


def _ls(root: Path, *args: str) -> set[str]:
    result = git(root, "ls-files", "-z", *args)
    if result.returncode:
        raise ScanError(result.stderr.decode("utf-8", "replace").strip() or "git ls-files failed")
    return set(result.stdout.decode("utf-8", "strict").split("\0")) - {""}


def list_files(root: Path) -> list[str] | None:
    """Tracked files (including files of initialized submodules) and untracked, not ignored files."""
    if not (root / ".git").exists():
        return None
    return sorted(p for p in _ls(root, "--cached", "--recurse-submodules") | _ls(root, "--others", "--exclude-standard")
                  if p.split("/", 1)[0] != ".hve-studio")


def list_ignored(root: Path) -> list[str]:
    """Ignored paths; a fully ignored directory is one entry ending in '/'. Contents are never read."""
    return sorted(p for p in _ls(root, "--others", "--ignored", "--exclude-standard", "--directory")
                  if p.rstrip("/").split("/", 1)[0] != ".hve-studio")


def list_submodules(root: Path) -> list[dict]:
    if not (root / ".gitmodules").is_file():
        return []
    result = git(root, "submodule", "status", "--recursive")
    if result.returncode:
        raise ScanError(result.stderr.decode("utf-8", "replace").strip() or "git submodule status failed")
    states = {" ": "initialized", "-": "not-initialized", "+": "checked-out-commit-differs", "U": "merge-conflict"}
    items = []
    for raw in result.stdout.decode("utf-8", "replace").splitlines():
        match = re.match(r"^([ +\-U])([0-9a-f]+) (.+?)(?: \((.*)\))?$", raw)
        if match:
            items.append({"path": match.group(3), "commit": match.group(2),
                          "state": states[match.group(1)], "describe": match.group(4) or ""})
    return items


def excluded(rel: str) -> bool:
    return bool(set(Path(rel).parts[:-1]) & SKIP_DIRS)


def safe_file(root: Path, rel: str) -> bool:
    path = root / rel
    return root in path.resolve().parents and not any(p.is_symlink() for p in (path, *path.parents) if p != root)


def fingerprint(root: Path) -> str:
    paths = list_files(root)
    if paths is None:
        return ""
    digest = hashlib.sha256()
    for rel in paths:
        if excluded(rel):
            digest.update(f"{rel}\0".encode("utf-8"))
            continue
        try:
            st = (root / rel).lstat()
            stamp = (st.st_mtime_ns, st.st_size, st.st_mode)
        except OSError:
            stamp = None
        digest.update(f"{rel}\0{stamp}\0".encode("utf-8"))
    head = git(root, "rev-parse", "--verify", "HEAD")
    digest.update(head.stdout)
    refs = git(root, "show-ref", "--head")
    if refs.returncode not in (0, 1) or refs.stderr:
        raise ScanError(refs.stderr.decode("utf-8", "replace").strip() or "git show-ref failed")
    digest.update(refs.stdout)
    digest.update("\0".join(list_ignored(root)).encode("utf-8"))
    digest.update(json.dumps(list_submodules(root)).encode("utf-8"))
    return digest.hexdigest()


def scan(root: Path, is_test, progress=None) -> dict | None:
    if progress:
        progress({"phase": "inventory", "completed": 0, "total": 1})
    paths = list_files(root)
    if paths is None:
        return None
    data = {"files": [], "tasks": [], "dependencies": [], "history": [], "diagnostics": [],
            "texts": {}, "links": [], "limits": {"textBytes": TEXT_MAX_BYTES},
            "submodules": list_submodules(root),
            "scope": "local Git: tracked, untracked and ignored paths, initialized submodule files, all local refs"}
    texts = data["texts"]
    submodules = {s["path"]: s for s in data["submodules"]}
    for rel in list_ignored(root):
        data["files"].append({"path": rel, "kind": "ignored", "bytes": None, "analysis": "inventory-only"})
    if progress:
        progress({"phase": "inventory", "completed": 1, "total": 1})
    for index, rel in enumerate(paths):
        if progress:
            progress({"phase": "files", "completed": index, "total": len(paths), "detail": rel})
        if rel in submodules:
            state = submodules[rel]["state"]
            data["files"].append({"path": rel, "kind": "submodule", "bytes": None, "analysis": "inventory-only"})
            if state == "not-initialized":
                data["diagnostics"].append({"path": rel, "reason": "submodule not initialized: run `git submodule update --init` to analyze its files"})
            continue
        if excluded(rel):
            data["files"].append({"path": rel, "kind": "generated", "bytes": None, "analysis": "inventory-only"})
            data["diagnostics"].append({"path": rel, "reason": "generated/dependency directory: content not analyzed"})
            continue
        path = root / rel
        suffix = path.suffix.lower()
        kind = ("test" if is_test(rel) else "source") if suffix in SOURCE_EXTS else (
            "document" if suffix in DOC_EXTS else "config" if suffix in CONFIG_EXTS else "asset")
        rec = {"path": rel, "kind": kind, "bytes": None, "analysis": "inventory-only"}
        data["files"].append(rec)
        if not safe_file(root, rel):
            rec["analysis"] = "excluded"
            data["diagnostics"].append({"path": rel, "reason": "symlink or path outside repository"})
            continue
        try:
            rec["bytes"] = path.stat().st_size
            if not path.is_file():
                raise OSError("not a regular file (possibly a submodule)")
            if SECRET_NAME.search(path.name):
                rec["analysis"] = "excluded"
                data["diagnostics"].append({"path": rel, "reason": "potential credentials: content not read"})
                continue
            if kind == "asset":
                continue
            if rec["bytes"] > TEXT_MAX_BYTES:
                data["diagnostics"].append({"path": rel, "reason": f"text exceeds {TEXT_MAX_BYTES} bytes"})
                continue
            text = path.read_text(encoding="utf-8-sig")
            if "\0" in text:
                raise ValueError("binary content")
            texts[rel] = text
            rec["analysis"] = "read"
        except (OSError, UnicodeError, ValueError) as exc:
            rec["analysis"] = "unreadable"
            data["diagnostics"].append({"path": rel, "reason": str(exc)})
            continue
        occurrences = Counter()
        fenced = False
        for line, raw in enumerate(text.splitlines(), 1):
            if kind == "document" and raw.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
            if fenced:
                continue
            match = CHECKBOX.match(raw) if kind == "document" else TODO.match(raw) if kind in ("source", "test") else None
            if match:
                title = match.group(2).strip()
                occurrences[title] += 1
                key = hashlib.sha256(f"{rel}\0{title}\0{occurrences[title]}".encode("utf-8")).hexdigest()
                data["tasks"].append({"id": "import:" + key, "title": title,
                                      "status": "done" if match.group(1).lower() == "x" else "todo",
                                      "file": rel, "line": line, "origin": "repository"})
        if path.name == "package.json":
            try:
                package = json.loads(text)
                for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                    for name, version in package.get(section, {}).items():
                        data["dependencies"].append({"name": name, "version": str(version), "kind": section, "file": rel})
            except (ValueError, AttributeError) as exc:
                data["diagnostics"].append({"path": rel, "reason": f"package.json: {exc}"})
        elif re.fullmatch(r"requirements(?:[-.][\w-]+)?\.txt", path.name, re.I):
            for raw in text.splitlines():
                match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)([<>=!~].*?)?\s*(?:#.*)?$", raw)
                if match:
                    data["dependencies"].append({"name": match.group(1), "version": match.group(2) or "",
                                                 "kind": "python", "file": rel})
    if progress:
        progress({"phase": "files", "completed": len(paths), "total": len(paths)})
        progress({"phase": "relationships", "completed": 0, "total": 1})
    # Exact, local module paths only. Dynamic and external imports are not guessed.
    for rel, text in texts.items():
        imports = []
        if rel.endswith(".py"):
            try:
                tree = ast.parse(text)
                for item in ast.walk(tree):
                    if isinstance(item, ast.Import):
                        imports.extend((alias.name.replace(".", "/"), 0) for alias in item.names)
                    elif isinstance(item, ast.ImportFrom):
                        module = (item.module or "").replace(".", "/")
                        imports.append((module, item.level))
                        imports.extend(("/".join(filter(None, (module, alias.name))), item.level) for alias in item.names)
            except SyntaxError as exc:
                data["diagnostics"].append({"path": rel, "reason": f"Python syntax: line {exc.lineno}"})
            for name, level in imports:
                base = Path(rel).parent
                for _ in range(max(0, level - 1)):
                    base = base.parent
                candidates = [base / name] if level else [Path(name), base / name, Path("src") / name]
                for candidate in candidates:
                    target = next((p.as_posix() for p in (candidate.with_suffix(".py"), candidate / "__init__.py")
                                   if p.as_posix() in texts), None)
                    if target and target != rel:
                        data["links"].append({"source": rel, "target": target, "kind": "import"})
                        break
        elif Path(rel).suffix.lower() in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}:
            for match in re.finditer(r"""(?:\bfrom\s*|\bimport\s*|\brequire\s*\(\s*|\bimport\s*\(\s*)['"](\.[^'"]+)['"]""", text):
                base = Path(os.path.normpath(str(Path(rel).parent / match.group(1)))).as_posix()
                target = next((p for p in [base] + [base + ext for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".vue", ".svelte")]
                               + [base + "/index" + ext for ext in (".ts", ".tsx", ".js", ".jsx")] if p in texts), None)
                if target and target != rel:
                    data["links"].append({"source": rel, "target": target, "kind": "import"})
    if progress:
        progress({"phase": "relationships", "completed": 1, "total": 1})
        progress({"phase": "history", "completed": 0, "total": 1})
    head = git(root, "rev-parse", "--verify", "HEAD")
    log = git(root, "log", "--all", *(["HEAD"] if head.returncode == 0 else []),
              "-z", "--format=%H%x00%cI%x00%s")
    if log.returncode:
        raise ScanError(log.stderr.decode("utf-8", "replace"))
    fields = log.stdout.decode("utf-8", "replace").split("\0")
    for i in range(0, len(fields) - 2, 3):
        data["history"].append({"commit": fields[i], "date": fields[i + 1], "subject": fields[i + 2]})
    data["counts"] = dict(Counter(f["kind"] for f in data["files"]))
    data["counts"]["files"] = len(data["files"])
    data["counts"]["read"] = len(texts)
    data["unavailable"] = ["Undeclared goals, acceptance criteria, entities, API contracts and test outcomes are not inferred.",
                           "Ignored and generated paths are listed but their contents are not analyzed; credentials-like files are never read.",
                           "Dependencies: package.json and requirements*.txt; imports: static local Python/JS/TS paths only."]
    if progress:
        progress({"phase": "history", "completed": 1, "total": 1})
    return data
