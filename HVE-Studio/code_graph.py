"""FR-1091: function / class level relationships of the source (read only, nothing is executed).

Nodes are functions, methods, classes and (when they call something) module bodies. Edges are call / ref / inherit.
Python is read with `ast`; JS/TS with a comment- and string-masked text. Only what can be resolved is drawn:
- conf "exact": resolved through scope, imports or self/cls.
- conf "name":  `obj.method()` whose method name is unique in the repository (a guess, shown as such).
Dynamic calls (getattr, eval, computed members) are not guessed; they are counted in stats.unresolved.
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import repo_scan

MAX_FILE_BYTES = 512_000  # PARAM-066: a larger source file is listed but not parsed
COMMON_NAMES = {"click", "close", "open", "read", "write", "get", "set", "add", "append", "run", "start", "stop", "update",
                "remove", "push", "find", "items", "keys", "values", "copy", "clear", "send", "load", "save", "join", "split",
                "format", "strip", "wait", "fill", "text", "then", "catch", "call", "bind", "apply", "map", "filter", "test"}
MAX_NODES = 20_000        # PARAM-067: more symbols than this are cut (stats.truncated)
JS_EXTS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*\.py$|\.(test|spec)\.[jt]sx?$", re.I)
REQ_RE = re.compile(r"(?<![A-Za-z0-9\-])((?:NFR-[A-Z0-9]+-\d{2,}|FR-\d{1,5}|NFR-\d{1,5}))(?![0-9A-Za-z])")
VENDOR_RE = re.compile(r"(^|/)(vendor|third_party|site-packages)/|\.min\.(js|css)$", re.I)
JS_KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "return", "typeof", "new", "await", "super",
               "import", "else", "do", "try", "with", "constructor", "delete", "void", "yield", "in", "of"}


def _sym(file: str, qual: str, name: str, kind: str, line: int, end: int, lang: str, parent: str | None = None) -> dict:
    return {"id": f"{file}::{qual}", "name": name, "qual": qual, "kind": kind, "file": file, "line": line,
            "end": end, "lang": lang, "parent": parent}


# ------------------------------------------------------------------ Python
def _py_module_target(files: set[str], rel: str, name: str, level: int) -> str | None:
    base = Path(rel).parent
    for _ in range(max(0, level - 1)):
        base = base.parent
    name = name.replace(".", "/")
    candidates = [base / name] if level else [Path(name), base / name, Path("src") / name]
    for cand in candidates:
        for p in (cand.with_suffix(".py"), cand / "__init__.py"):
            if p.as_posix() in files and p.as_posix() != rel:
                return p.as_posix()
    return None


def _py_extract(rel: str, text: str, files: set[str], out: dict) -> None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        out["stats"]["parseErrors"] += 1
        return
    syms: dict[str, dict] = {}
    scope: dict[str, str] = {}     # top-level name -> symbol id
    methods: dict[str, dict[str, str]] = {}  # class qual -> {method name -> id}
    bases: dict[str, list[ast.expr]] = {}
    imports: dict[str, tuple] = {}  # alias -> ("mod", file) | ("sym", file, name)

    def add(node, qual: str, kind: str, parent: str | None) -> dict:
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        s = _sym(rel, qual, qual.rsplit(".", 1)[-1], kind, node.lineno, end, "py", parent)
        doc = ast.get_docstring(node) or ""
        s["doc"] = doc.strip().split("\n", 1)[0][:140]
        syms[s["id"]] = s
        return s

    def declare(body, prefix: str, parent: str | None, top: bool) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = prefix + node.name
                kind = "method" if parent and syms[parent]["kind"] == "class" else "function"
                s = add(node, qual, kind, parent)
                if top:
                    scope[node.name] = s["id"]
                elif kind == "method":
                    methods.setdefault(prefix[:-1], {})[node.name] = s["id"]
                declare(node.body, qual + ".", s["id"], False)
            elif isinstance(node, ast.ClassDef):
                qual = prefix + node.name
                s = add(node, qual, "class", parent)
                bases[s["id"]] = list(node.bases)
                if top:
                    scope[node.name] = s["id"]
                declare(node.body, qual + ".", s["id"], False)
            elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                for field in ("body", "orelse", "finalbody", "handlers"):
                    inner = getattr(node, field, None)
                    if not inner:
                        continue
                    declare([h for part in inner for h in (part.body if isinstance(part, ast.ExceptHandler) else [part])],
                            prefix, parent, top)

    declare(tree.body, "", None, True)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                target = _py_module_target(files, rel, a.name, 0)
                if target:
                    imports[(a.asname or a.name).split(".")[0]] = ("mod", target)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            target = _py_module_target(files, rel, module, node.level) if (module or node.level) else None
            for a in node.names:
                alias = a.asname or a.name
                sub = _py_module_target(files, rel, ".".join(filter(None, (module, a.name))), node.level)
                if sub:
                    imports[alias] = ("mod", sub)
                elif target:
                    imports[alias] = ("sym", target, a.name)
    out["imports"][rel] = sorted({v[1] for v in imports.values()})

    out["raw"].append({"file": rel, "lang": "py", "syms": syms, "scope": scope, "methods": methods,
                       "bases": bases, "imports": imports, "tree": tree})


def _py_locals(fn) -> frozenset:
    """Names bound inside a function (parameters and assignments): they shadow module-level functions of the same name."""
    names = {a.arg for a in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs, fn.args.vararg, fn.args.kwarg) if a}
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        stack.extend(ast.iter_child_nodes(node))
    return frozenset(names)


def _py_resolve_edges(entry: dict, table: dict, add_edge, uniq: dict) -> None:
    rel, syms, scope, methods, imports, tree = (entry[k] for k in ("file", "syms", "scope", "methods", "imports", "tree"))

    def lookup_top(name: str, file_entry: dict | None = None) -> str | None:
        return (file_entry or entry)["scope"].get(name)

    def class_methods(cid: str, name: str, seen=None) -> str | None:
        seen = seen or set()
        if cid in seen:
            return None
        seen.add(cid)
        owner = table[cid]
        entry_of = table["__entry__"][owner["file"]]
        hit = entry_of["methods"].get(owner["qual"], {}).get(name)
        if hit:
            return hit
        for base in entry_of["bases"].get(cid, []):
            bid = resolve_expr(base, entry_of)
            if bid and bid in table and table[bid]["kind"] == "class":
                found = class_methods(bid, name, seen)
                if found:
                    return found
        return None

    def resolve_name(name: str, file_entry: dict, chain: list[str]) -> str | None:
        for sid in reversed(chain):       # nested defs of the enclosing functions
            cand = f"{file_entry['file']}::{table[sid]['qual']}.{name}"
            if cand in table and table[cand]["kind"] == "function":
                return cand
        top = file_entry["scope"].get(name)
        if top:
            return top
        imp = file_entry["imports"].get(name)
        if imp and imp[0] == "sym":
            other = table["__entry__"].get(imp[1])
            return other["scope"].get(imp[2]) if other else None
        return None

    def resolve_expr(node, file_entry: dict) -> str | None:
        if isinstance(node, ast.Name):
            return resolve_name(node.id, file_entry, [])
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            imp = file_entry["imports"].get(node.value.id)
            if imp and imp[0] == "mod":
                other = table["__entry__"].get(imp[1])
                return other["scope"].get(node.attr) if other else None
        return None

    for sid, s in list(syms.items()):
        if s["kind"] == "class":
            for base in entry["bases"].get(sid, []):
                bid = resolve_expr(base, entry)
                if bid and bid in table:
                    add_edge(sid, bid, "inherit", "exact")

    module_id = f"{rel}::<module>"

    def visit(node, chain: list[str], cls: str | None, shadow: frozenset = frozenset()) -> None:
        cur = chain[-1] if chain else None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node is not tree:
            qual = None
            # find our symbol: match by line (decorators/body are walked under it)
            for sym in syms.values():
                if sym["line"] == node.lineno and sym["name"] == node.name:
                    qual = sym["id"]
                    break
            if qual:
                for dec in getattr(node, "decorator_list", []):
                    visit(dec, chain, cls, shadow)
                new_cls = qual if isinstance(node, ast.ClassDef) else cls
                inner = shadow if isinstance(node, ast.ClassDef) else shadow | _py_locals(node)
                for child in node.body:
                    visit(child, chain + [qual], new_cls, inner)
                return
        if isinstance(node, ast.Call):
            src = cur or module_id
            tgt, conf = None, "exact"
            f = node.func
            if isinstance(f, ast.Name):
                tgt = None if f.id in shadow else resolve_name(f.id, entry, chain)
            elif isinstance(f, ast.Attribute):
                v = f.value
                if isinstance(v, ast.Name) and v.id in ("self", "cls") and cls:
                    tgt = class_methods(cls, f.attr)
                elif isinstance(v, ast.Name):
                    tgt = resolve_expr(f, entry)
                    if not tgt:
                        cid = None if v.id in shadow else resolve_name(v.id, entry, chain)
                        if cid and table.get(cid, {}).get("kind") == "class":
                            tgt = class_methods(cid, f.attr)
                if not tgt and f.attr in uniq:
                    tgt, conf = uniq[f.attr], "name"
            else:
                out_unresolved[0] += 1
            if tgt and tgt != src:
                if src == module_id:
                    table.setdefault(module_id, _sym(rel, "<module>", "<module>", "module", 1, 1, "py"))
                add_edge(src, tgt, "call", conf)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            tgt = None if node.id in shadow else resolve_name(node.id, entry, chain)
            src = cur or module_id
            if tgt and tgt != src and table.get(tgt, {}).get("kind") in ("function", "method") and id(node) not in call_names:
                if src == module_id:
                    table.setdefault(module_id, _sym(rel, "<module>", "<module>", "module", 1, 1, "py"))
                add_edge(src, tgt, "ref", "exact")
        for child in ast.iter_child_nodes(node):
            visit(child, chain, cls, shadow)

    call_names = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    out_unresolved = [0]
    visit(tree, [], None)
    entry["unresolved"] = out_unresolved[0]


# ------------------------------------------------------------------ JS / TS
def _mask(text: str) -> str:
    """Blank out comments and string contents (newlines and length are kept, so offsets still match)."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        two = text[i:i + 2]
        if two == "//":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out[i:j] = " " * (j - i)
            i = j
        elif two == "/*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if text[k] != "\n":
                    out[k] = " "
            i = j
        elif c in "'\"`":
            j = i + 1
            while j < n and text[j] != c:
                if text[j] == "\\":
                    j += 1
                elif c != "`" and text[j] == "\n":
                    break
                j += 1
            for k in range(i + 1, min(j, n)):
                if text[k] != "\n":
                    out[k] = " "
            i = j + 1
        else:
            i += 1
    return "".join(out)


def _match_brace(masked: str, open_at: int) -> int:
    depth = 0
    for i in range(open_at, len(masked)):
        ch = masked[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(masked) - 1


JS_FUNC = re.compile(r"(?m)^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(")
JS_ARROW = re.compile(
    r"(?m)^[ \t]*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=\s*(?:async\s*)?"
    r"(?:function\b|\((?:[^()]|\([^()]*\))*\)\s*(?::[^=\n{]+)?=>|[A-Za-z_$][\w$]*\s*=>)")
JS_CLASS = re.compile(r"(?m)^[ \t]*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)(?:\s+extends\s+([A-Za-z_$][\w$.]*))?[^{]*\{")
JS_METHOD = re.compile(r"(?m)^[ \t]*(?:(?:public|private|protected|static|async|get|set|readonly)\s+)*\*?([A-Za-z_$#][\w$]*)\s*\((?:[^()]|\([^()]*\))*\)\s*(?::\s*[^{;=]+)?\{")
JS_REQUIRE = re.compile(r"""(?:const|let|var)\s+(\{[^}]*\}|[A-Za-z_$][\w$]*)\s*=\s*require\(\s*['"](\.[^'"]+)['"]\s*\)""")


def _line_of(starts: list[int], pos: int) -> int:
    lo, hi = 0, len(starts)
    while lo < hi:
        mid = (lo + hi) // 2
        if starts[mid] <= pos:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _js_target(files: set[str], rel: str, spec: str) -> str | None:
    base = Path(os.path.normpath(str(Path(rel).parent / spec))).as_posix()
    for cand in [base] + [base + e for e in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")] + [base + "/index" + e for e in (".ts", ".tsx", ".js", ".jsx")]:
        if cand in files and cand != rel:
            return cand
    return None


def _js_extract(rel: str, text: str, files: set[str], out: dict) -> None:
    masked = _mask(text)
    starts = [0] + [m.end() for m in re.finditer("\n", text)]
    syms: dict[str, dict] = {}
    ranges: list[tuple[int, int, str]] = []  # (start, end, id) offsets for innermost lookup
    scope: dict[str, str] = {}
    methods: dict[str, dict[str, str]] = {}
    bases: dict[str, str] = {}

    def body_end(start: int, arrow_expr_ok: bool) -> int:
        brace = masked.find("{", start)
        nl = masked.find("\n", start)
        arrow = masked.find("=>", start)
        if arrow_expr_ok and arrow >= 0 and (brace < 0 or arrow < brace):
            after = masked[arrow + 2:].lstrip()
            if not after.startswith("{"):
                stop = masked.find("\n", arrow)
                return len(masked) if stop < 0 else stop
            brace = masked.find("{", arrow)
        if brace < 0:
            return nl if nl >= 0 else len(masked)
        return _match_brace(masked, brace)

    def register(name, kind, start, end, parent=None, qual=None, line_pos=None):
        qual = qual or name
        s = _sym(rel, qual, name, kind, _line_of(starts, start if line_pos is None else line_pos),
                 _line_of(starts, end), "js", parent)
        if s["id"] in syms:
            return None
        syms[s["id"]] = s
        ranges.append((start, end, s["id"]))
        return s

    for m in JS_CLASS.finditer(masked):
        brace = m.end() - 1
        end = _match_brace(masked, brace)
        s = register(m.group(1), "class", m.start(), end, line_pos=m.start(1))
        if not s:
            continue
        scope[m.group(1)] = s["id"]
        if m.group(2):
            bases[s["id"]] = m.group(2)
        # methods at class-body depth 1
        depth, i, body_start = 0, brace, brace
        while i < end:
            ch = masked[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif depth == 1 and (i == brace + 1 or masked[i - 1] == "\n"):
                mm = JS_METHOD.match(masked, i)
                if mm and mm.group(1) not in JS_KEYWORDS:
                    mend = _match_brace(masked, mm.end() - 1)
                    qual = f"{m.group(1)}.{mm.group(1)}"
                    ms = register(mm.group(1), "method", mm.start(), mend, s["id"], qual, mm.start(1))
                    if ms:
                        methods.setdefault(m.group(1), {})[mm.group(1)] = ms["id"]
                    i = mend + 1  # the method body belongs to the method
                    depth = 1
                    continue
            i += 1
    class_spans = [(r[0], r[1]) for r in ranges if syms[r[2]]["kind"] == "class"]

    def in_class(pos: int) -> bool:
        return any(a <= pos <= b for a, b in class_spans)

    for rx, arrow in ((JS_FUNC, False), (JS_ARROW, True)):
        for m in rx.finditer(masked):
            if in_class(m.start()):
                continue
            end = body_end(m.end() - 1 if rx is JS_FUNC else m.start(), arrow)
            s = register(m.group(1), "function", m.start(), end, line_pos=m.start(1))
            if s:
                scope.setdefault(m.group(1), s["id"])

    imports: dict[str, tuple] = {}
    out["imports"][rel] = []
    for m in re.finditer(r"""(?:import\s+([^'";]*?)\s+from|export\s+(?:\{[^}]*\}|\*)\s*(?:as\s+\w+\s*)?from)\s*['"](\.[^'"]*)['"]""", text):
        target = _js_target(files, rel, m.group(2))
        if not target:
            continue
        out["imports"][rel].append(target)
        clause = (m.group(1) or "").strip()
        named = re.search(r"\{([^}]*)\}", clause)
        if named:
            for part in named.group(1).split(","):
                bits = re.split(r"\s+as\s+", part.strip())
                if bits[0]:
                    imports[bits[-1].strip()] = ("sym", target, bits[0].strip())
        ns = re.search(r"\*\s+as\s+([\w$]+)", clause)
        if ns:
            imports[ns.group(1)] = ("mod", target)
        default = re.match(r"([A-Za-z_$][\w$]*)\s*(?:,|$)", clause)
        if default:
            imports[default.group(1)] = ("sym", target, "default")
    for m in JS_REQUIRE.finditer(text):
        target = _js_target(files, rel, m.group(2))
        if not target:
            continue
        out["imports"][rel].append(target)
        if m.group(1).startswith("{"):
            for part in m.group(1).strip("{} ").split(","):
                bits = [b.strip() for b in part.split(":")]
                if bits[0]:
                    imports[bits[-1]] = ("sym", target, bits[0])
        else:
            imports[m.group(1)] = ("mod", target)
    out["imports"][rel] = sorted(set(out["imports"][rel]))
    out["raw"].append({"file": rel, "lang": "js", "syms": syms, "scope": scope, "methods": methods, "bases": bases,
                       "imports": imports, "ranges": sorted(ranges), "masked": masked, "starts": starts})


def _js_resolve_edges(entry: dict, table: dict, add_edge, uniq: dict) -> None:
    rel, syms, scope, methods, imports, masked = (entry[k] for k in ("file", "syms", "scope", "methods", "imports", "masked"))
    ranges = entry["ranges"]
    module_id = f"{rel}::<module>"
    decl_pos = {s["line"] for s in syms.values()}

    def owner_of(pos: int) -> tuple[str, str | None]:
        best, cls = None, None
        for a, b, sid in ranges:
            if a <= pos <= b:
                if best is None or a >= best[0]:
                    best = (a, sid)
                if syms[sid]["kind"] == "class":
                    cls = sid
        if best is None:
            return module_id, None
        sid = best[1]
        if syms[sid]["kind"] == "method":
            cls = syms[sid]["parent"]
        return sid, cls

    def default_of(file: str) -> str | None:
        other = table["__entry__"].get(file)
        if not other:
            return None
        for m in re.finditer(r"export\s+default\s+(?:async\s+)?(?:function\s*\*?\s*|class\s+)([A-Za-z_$][\w$]*)", other["masked"]):
            return other["scope"].get(m.group(1))
        m = re.search(r"export\s+default\s+([A-Za-z_$][\w$]*)\s*;?", other["masked"])
        return other["scope"].get(m.group(1)) if m else None

    def resolve_name(name: str) -> str | None:
        if name in scope:
            return scope[name]
        imp = imports.get(name)
        if imp and imp[0] == "sym":
            other = table["__entry__"].get(imp[1])
            if not other:
                return None
            return default_of(imp[1]) if imp[2] == "default" else other["scope"].get(imp[2])
        return None

    def class_method(cid: str, name: str, seen=None) -> str | None:
        seen = seen or set()
        if cid in seen:
            return None
        seen.add(cid)
        owner = table[cid]
        e = table["__entry__"][owner["file"]]
        hit = e["methods"].get(owner["qual"], {}).get(name)
        if hit:
            return hit
        base = e["bases"].get(cid)
        if base:
            bid = e["scope"].get(base) or (resolve_name(base) if e is entry else None)
            if bid and bid in table:
                return class_method(bid, name, seen)
        return None

    for cid, base in entry["bases"].items():
        bid = resolve_name(base)
        if bid:
            add_edge(cid, bid, "inherit", "exact")

    names = set(scope) | {k for k, v in imports.items() if v[0] == "sym"}
    call_spans = set()
    for m in re.finditer(r"(?<![\w$])(this\.)?([A-Za-z_$][\w$]*)(?:\.([A-Za-z_$][\w$]*))?\s*\(", masked):
        start = m.start()
        # a declaration header is not a call
        head = masked[max(0, start - 9):start]
        if re.search(r"(function|class)\s*\*?\s*$", head) or masked[max(0, start - 1):start] == ".":
            continue
        src, cls = owner_of(start)
        if m.group(1):                               # this.foo( ... )
            name = m.group(2)
            tgt = class_method(cls, name) if cls else None
            conf = "exact"
            if not tgt and name in uniq:
                tgt, conf = uniq[name], "name"
            if src in syms and syms[src]["name"] == name and syms[src]["kind"] == "method" and tgt == src:
                continue
        elif m.group(3):                             # a.b( ... )
            a, b = m.group(2), m.group(3)
            tgt, conf = None, "exact"
            imp = imports.get(a)
            if imp and imp[0] == "mod":
                other = table["__entry__"].get(imp[1])
                tgt = other["scope"].get(b) if other else None
            if not tgt:
                cid = resolve_name(a)
                if cid and table.get(cid, {}).get("kind") == "class":
                    tgt = class_method(cid, b)
            if not tgt and b in uniq:
                tgt, conf = uniq[b], "name"
        else:                                        # f( ... )
            name = m.group(2)
            if name in JS_KEYWORDS:
                continue
            tgt, conf = resolve_name(name), "exact"
            call_spans.add(m.start(2))
        if tgt and tgt != src:
            if src == module_id:
                table.setdefault(module_id, _sym(rel, "<module>", "<module>", "module", 1, 1, "js"))
            add_edge(src, tgt, "call", conf)
    if names:
        ref_text = re.sub(r"\b(?:import|export)\b[^;'\"]*?\bfrom\b", lambda m: re.sub(r"[^\n]", " ", m.group(0)), masked)
        for m in re.finditer(r"(?<![\w$.])(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")(?![\w$])(?!\s*\()", ref_text):
            tgt = resolve_name(m.group(1))
            if not tgt or table[tgt]["kind"] not in ("function", "method"):
                continue
            line = _line_of(entry["starts"], m.start())
            before = masked[max(0, m.start() - 12):m.start()]
            if re.search(r"(function|const|let|var|class|import|export|default)\s*\*?\s*$", before) or "{" == masked[m.end():m.end() + 1] and "import" in before:
                continue
            src, _cls = owner_of(m.start())
            if src in syms and (src == tgt or syms[src]["line"] == line and syms[src]["name"] == m.group(1)):
                continue
            if tgt != src:
                if src == module_id:
                    table.setdefault(module_id, _sym(rel, "<module>", "<module>", "module", 1, 1, "js"))
                add_edge(src, tgt, "ref", "exact")


# ------------------------------------------------------------------ entry point
def build(root: Path, inv: repo_scan.Inventory | None = None) -> dict:
    paths = repo_scan.list_files(root, inv)
    if paths is None:
        return {"nodes": [], "edges": [], "files": [], "stats": {"files": 0, "nodes": 0, "edges": 0, "unresolved": 0,
                                                                  "parseErrors": 0, "truncated": False, "skipped": 0}}
    cand = [p for p in paths if Path(p).suffix.lower() in ({".py"} | JS_EXTS)
            and not repo_scan.excluded(p) and not VENDOR_RE.search(p) and not repo_scan.SECRET_NAME.search(Path(p).name)]
    fileset = set(cand)
    out = {"raw": [], "imports": {}, "stats": {"parseErrors": 0}}
    texts: dict[str, str] = {}
    symlinks: dict[Path, bool] = {}
    skipped = 0
    for rel in cand:
        path = root / rel
        try:
            if not repo_scan.safe_file(root, rel, symlinks) or path.stat().st_size > MAX_FILE_BYTES:
                skipped += 1
                continue
            texts[rel], _enc, _cut = repo_scan.read_text(path, MAX_FILE_BYTES)
        except (OSError, UnicodeDecodeError):
            skipped += 1
    for rel, text in texts.items():
        (_py_extract if rel.endswith(".py") else _js_extract)(rel, text, fileset, out)

    table: dict = {"__entry__": {e["file"]: e for e in out["raw"]}}
    for e in out["raw"]:
        table.update(e["syms"])
    # method names that exist exactly once in the repository: the only "name" guesses we allow
    by_name: dict[str, list[str]] = {}
    for sid, s in table.items():
        if sid != "__entry__" and s["kind"] == "method" and len(s["name"]) >= 4 \
                and s["name"] not in COMMON_NAMES and not s["name"].startswith("__"):
            by_name.setdefault(s["name"], []).append(sid)
    uniq = {k: v[0] for k, v in by_name.items() if len(v) == 1}

    edges: dict[tuple, dict] = {}

    def add_edge(s, t, kind, conf):
        key = (s, t, kind)
        cur = edges.get(key)
        if cur:
            cur["n"] += 1
            if conf == "exact":
                cur["conf"] = "exact"
        else:
            edges[key] = {"s": s, "t": t, "kind": kind, "conf": conf, "n": 1}

    unresolved = 0
    for e in out["raw"]:
        (_py_resolve_edges if e["lang"] == "py" else _js_resolve_edges)(e, table, add_edge, uniq)
        unresolved += e.get("unresolved", 0)

    nodes, truncated = [], False
    degree: dict[str, int] = {}
    for e in edges.values():
        degree[e["s"]] = degree.get(e["s"], 0) + 1
        degree[e["t"]] = degree.get(e["t"], 0) + 1
    for sid, s in table.items():
        if sid == "__entry__":
            continue
        if len(nodes) >= MAX_NODES:
            truncated = True
            break
        loc = max(1, s["end"] - s["line"] + 1)
        nodes.append({"id": sid, "name": s["name"], "qual": s["qual"], "kind": s["kind"], "file": s["file"],
                      "line": s["line"], "loc": loc, "lang": s["lang"], "deg": degree.get(sid, 0), "doc": s.get("doc", ""),
                      "test": bool(TEST_RE.search(s["file"]))})
    keep = {n["id"] for n in nodes}
    edge_list = [e for e in edges.values() if e["s"] in keep and e["t"] in keep]
    files = []
    for rel, text in texts.items():
        reqs = sorted(set(REQ_RE.findall(text)))[:12]
        files.append({"path": rel, "lang": "py" if rel.endswith(".py") else "js", "loc": text.count("\n") + 1,
                      "test": bool(TEST_RE.search(rel)), "imports": out["imports"].get(rel, []), "reqs": reqs})
    nodes.sort(key=lambda n: (n["file"], n["line"]))
    return {"nodes": nodes, "edges": edge_list, "files": files,
            "stats": {"files": len(files), "nodes": len(nodes), "edges": len(edge_list), "unresolved": unresolved,
                      "parseErrors": out["stats"]["parseErrors"], "truncated": truncated, "skipped": skipped}}
