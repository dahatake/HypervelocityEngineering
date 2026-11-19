"""FR-1092: web endpoints (routes) found in source, with the prefixes of mounted routers composed (read only, nothing is executed).

Python: http.server handlers (`path == "/x"` inside do_GET / do_POST / _post), Flask (+ blueprints), FastAPI (+ APIRouter / include_router), Django urls.py.
JS/TS: Express / Hono / Fastify / Koa style `x.get('/p', ...)` and `x.use('/prefix', router)` followed through imports, barrels and factories; Next.js route files.
Only literal paths are read; a path built at run time is not guessed.
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import code_graph

METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
JS_EXT = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")


def _join(prefix: str, path: str) -> str:
    out = "/" + "/".join(p for p in (prefix.strip("/"), path.strip("/")) if p)
    return out if out != "/" or not (prefix or path).strip("/") else out


def _route(f: str, m: str, p: str, line: int, handler: str = "", doc: str = "") -> dict:
    return {"f": f, "m": m.upper(), "p": p or "/", "l": line, "h": handler, "d": doc}


# ------------------------------------------------------------------ Python
def _py_str(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _py_methods(call: ast.Call) -> list[str]:
    for kw in call.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
            got = [_py_str(e) for e in kw.value.elts]
            return [g.upper() for g in got if g] or ["GET"]
    return ["GET"]


def _py_collect(rel: str, text: str, fileset: set[str]) -> dict | None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    info = {"rel": rel, "tree": tree, "routers": {}, "routes": [], "mounts": [], "imports": {}, "apps": set()}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            fn = node.value.func
            name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
            if name in ("APIRouter", "Blueprint", "FastAPI", "Flask"):
                pre = ""
                for kw in node.value.keywords:
                    if kw.arg in ("prefix", "url_prefix"):
                        pre = _py_str(kw.value) or ""
                info["routers"][node.targets[0].id] = pre
                if name in ("FastAPI", "Flask"):
                    info["apps"].add(node.targets[0].id)
        elif isinstance(node, ast.Import):
            for a in node.names:
                tf = code_graph._py_module_target(fileset, rel, a.name, 0)
                if tf:
                    info["imports"][(a.asname or a.name).split(".")[0]] = (tf, None)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for a in node.names:
                sub = code_graph._py_module_target(fileset, rel, ".".join(filter(None, (module, a.name))), node.level)
                if sub:
                    info["imports"][a.asname or a.name] = (sub, None)
                else:
                    tf = code_graph._py_module_target(fileset, rel, module, node.level) if (module or node.level) else None
                    if tf:
                        info["imports"][a.asname or a.name] = (tf, a.name)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("include_router", "register_blueprint") and node.args:
            owner = node.func.value.id if isinstance(node.func.value, ast.Name) else ""
            pre = ""
            for kw in node.keywords:
                if kw.arg in ("prefix", "url_prefix"):
                    pre = _py_str(kw.value) or ""
            info["mounts"].append((owner, node.args[0], pre))
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = (ast.get_docstring(fn) or "").strip().split("\n", 1)[0][:140]
            for dec in fn.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.args):
                    continue
                path = _py_str(dec.args[0])
                owner = dec.func.value.id if isinstance(dec.func.value, ast.Name) else ""
                if path is None:
                    continue
                if dec.func.attr == "route":
                    for m in _py_methods(dec):
                        info["routes"].append((owner, m, path, fn.lineno, fn.name, doc))
                elif dec.func.attr in METHODS:
                    info["routes"].append((owner, dec.func.attr.upper(), path, fn.lineno, fn.name, doc))
    return info


def _py_framework(infos: dict[str, dict]) -> list[dict]:
    out, claimed, emitted = [], set(), set()

    def target(info: dict, expr) -> tuple[str, str] | None:
        if isinstance(expr, ast.Name):
            if expr.id in info["routers"]:
                return info["rel"], expr.id
            imp = info["imports"].get(expr.id)
            if imp and imp[1]:
                return imp[0], imp[1]
        elif isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
            imp = info["imports"].get(expr.value.id)
            if imp and imp[1] is None:
                return imp[0], expr.attr
        return None

    def walk(file: str, var: str, prefix: str, depth=0):
        if depth > 8 or file not in infos:
            return
        info = infos[file]
        own = prefix + info["routers"].get(var, "")
        for owner, m, path, line, h, doc in info["routes"]:
            if owner == var:
                key = (file, m, _join(own, path))
                if key not in emitted:
                    emitted.add(key)
                    out.append(_route(file, m, _join(own, path), line, h, doc))
        for owner, expr, pre in info["mounts"]:
            if owner == var:
                hit = target(info, expr)
                if hit:
                    claimed.add(hit)
                    walk(hit[0], hit[1], _join(own, pre), depth + 1)

    for file, info in infos.items():
        for app in info["apps"]:
            walk(file, app, "")
    for file, info in infos.items():
        for var in info["routers"]:
            if (file, var) not in claimed and var not in info["apps"]:
                walk(file, var, "")
        for owner, *_rest in info["routes"]:           # decorators on a name not created here (e.g. imported app)
            if owner not in info["routers"]:
                walk(file, owner, "")
    return out


def _py_routes(rel: str, text: str, info: dict | None) -> list[dict]:
    tree = info["tree"] if info else None
    if tree is None:
        return []
    out: list[dict] = []
    # http.server style: literal comparisons of the request path inside do_GET / do_POST / _post
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        for fn in cls.body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            m = fn.name[3:].upper() if fn.name.startswith("do_") else "POST" if fn.name in ("_post", "post") else ""
            if m not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            seen = set()
            for node in ast.walk(fn):
                if not isinstance(node, ast.Compare) or not isinstance(node.left, ast.Name) or node.left.id not in ("path", "endpoint", "route"):
                    continue
                for op, comp in zip(node.ops, node.comparators):
                    lits = [_py_str(comp)] if isinstance(op, ast.Eq) else [_py_str(e) for e in comp.elts] if isinstance(op, ast.In) and isinstance(comp, (ast.Tuple, ast.List, ast.Set)) else []
                    for lit in lits:
                        if lit and lit.startswith("/") and (m, lit) not in seen:
                            seen.add((m, lit))
                            out.append(_route(rel, m, lit, node.lineno, "", ""))
                if isinstance(node.left, ast.Name):
                    pass
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "startswith" \
                        and isinstance(node.func.value, ast.Name) and node.func.value.id in ("path", "endpoint") and node.args:
                    lit = _py_str(node.args[0])
                    if lit and lit.startswith("/") and (m, lit + "*") not in seen:
                        seen.add((m, lit + "*"))
                        out.append(_route(rel, m, lit + "*", node.lineno, "", ""))
    if rel.endswith("urls.py"):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("path", "re_path") and node.args:
                lit = _py_str(node.args[0])
                if lit is not None:
                    view = node.args[1] if len(node.args) > 1 else None
                    h = view.attr if isinstance(view, ast.Attribute) else view.id if isinstance(view, ast.Name) else ""
                    out.append(_route(rel, "ANY", "/" + lit.lstrip("/"), node.lineno, h, ""))
    return out


# ------------------------------------------------------------------ JS / TS
ROUTER_DEF = re.compile(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=\s*(?:new\s+)?(?:express\s*\.\s*)?(Router|Hono|express|fastify|Fastify|Koa|KoaRouter)\s*\(")
ROUTE_CALL = re.compile(r"""\b([A-Za-z_$][\w$]*)\s*\.\s*(get|post|put|patch|delete|all|head|options)\s*\(\s*(['"`])([^'"`\n]*)\3""")
USE_CALL = re.compile(r"""\b([A-Za-z_$][\w$]*)\s*\.\s*(?:use|route)\s*\(\s*(['"`])([^'"`\n]*)\2\s*,([^;]*?)\)\s*;?\s*$""", re.M | re.S)
IMPORT_RE = re.compile(r"""import\s+(?:([A-Za-z_$][\w$]*)\s*,?\s*)?(?:\{([^}]*)\}\s*)?(?:\*\s+as\s+([A-Za-z_$][\w$]*)\s*)?from\s*['"](\.[^'"]*)['"]""")
REEXPORT = re.compile(r"""export\s+(?:\*|\{([^}]*)\})\s*from\s*['"](\.[^'"]*)['"]""")
REQUIRE = re.compile(r"""(?:const|let|var)\s+([A-Za-z_$][\w$]*|\{[^}]*\})\s*=\s*require\(\s*['"](\.[^'"]+)['"]\s*\)""")


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _js_file(rel: str, text: str, files: dict[str, str]) -> dict:
    fset = set(files)
    masked = code_graph._mask(text)
    # keep the string literals (paths) but not comments: mask only comments
    nocomment = re.sub(r"//[^\n]*|/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
    info = {"rel": rel, "routers": {}, "apps": set(), "imports": {}, "exports": {}, "default": None, "reexports": [], "factories": {}, "mounts": [], "text": nocomment}
    lines = text.split("\n")
    for m in ROUTER_DEF.finditer(nocomment):
        name, kind = m.group(1), m.group(2)
        info["routers"].setdefault(name, [])
        if kind not in ("Router", "KoaRouter"):
            info["apps"].add(name)
    # a factory: function name() { const r = Router(); ...; return r }
    for m in re.finditer(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", nocomment):
        end = code_graph._match_brace(masked, m.end() - 1)
        body = nocomment[m.end():end]
        rv = re.search(r"return\s+([A-Za-z_$][\w$]*)\s*;?\s*$", body.strip())
        if rv and rv.group(1) in info["routers"]:
            info["factories"][m.group(1)] = rv.group(1)
    for m in re.finditer(r"(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{", nocomment):
        end = code_graph._match_brace(masked, m.end() - 1)
        body = nocomment[m.end():end]
        rv = re.search(r"return\s+([A-Za-z_$][\w$]*)\s*;?\s*$", body.strip())
        if rv and rv.group(1) in info["routers"]:
            info["factories"][m.group(1)] = rv.group(1)
    for m in ROUTE_CALL.finditer(nocomment):
        owner, verb, _q, path = m.groups()
        if owner in info["routers"] or owner in info["apps"]:
            line = _line(text, m.start())
            doc = code_graph._js_lead_doc(lines, line)
            info["routers"].setdefault(owner, []).append((verb.upper(), path, line, doc))
    for m in IMPORT_RE.finditer(nocomment):
        default, named, ns, spec = m.groups()
        target = code_graph._js_target(fset, rel, spec)
        if not target:
            continue
        if default:
            info["imports"][default] = (target, "default")
        if ns:
            info["imports"][ns] = (target, "*")
        for part in (named or "").split(","):
            bits = re.split(r"\s+as\s+", part.strip())
            if bits[0]:
                info["imports"][bits[-1].strip()] = (target, bits[0].strip())
    for m in REQUIRE.finditer(nocomment):
        target = code_graph._js_target(fset, rel, m.group(2))
        if target:
            if m.group(1).startswith("{"):
                for part in m.group(1).strip("{} ").split(","):
                    bits = [b.strip() for b in part.split(":")]
                    if bits[0]:
                        info["imports"][bits[-1]] = (target, bits[0])
            else:
                info["imports"][m.group(1)] = (target, "default")
    for m in REEXPORT.finditer(nocomment):
        target = code_graph._js_target(fset, rel, m.group(2))
        if target:
            info["reexports"].append((target, m.group(1)))
    # exports
    dm = re.search(r"export\s+default\s+([A-Za-z_$][\w$]*)\s*;?", nocomment)
    if dm:
        info["default"] = dm.group(1)
    mm = re.search(r"module\.exports\s*=\s*([A-Za-z_$][\w$]*)\s*;?", nocomment)
    if mm:
        info["default"] = mm.group(1)
    for m in re.finditer(r"export\s+(?:const|let|var|function|async function)\s+([A-Za-z_$][\w$]*)", nocomment):
        info["exports"][m.group(1)] = m.group(1)
    for m in re.finditer(r"export\s*\{([^}]*)\}\s*;?", nocomment):
        if "from" in nocomment[m.end():m.end() + 8]:
            continue
        for part in m.group(1).split(","):
            bits = re.split(r"\s+as\s+", part.strip())
            if bits[0]:
                info["exports"][bits[-1].strip()] = bits[0].strip()
    # mounts: x.use('/prefix', a, b, target)
    for m in USE_CALL.finditer(nocomment):
        owner = m.group(1)
        if owner not in info["routers"] and owner not in info["apps"]:
            continue
        args = [a.strip() for a in re.split(r",(?![^()]*\))", m.group(4)) if a.strip()]
        if args:
            info["mounts"].append((owner, m.group(3), args[-1]))
    return info


def _js_routes(files: dict[str, str]) -> list[dict]:
    infos = {rel: _js_file(rel, text, files) for rel, text in files.items() if rel.endswith(JS_EXT)}

    def router_of(file: str, name: str, seen=None):
        """(file, router variable) that `name` exported from `file` stands for."""
        seen = seen or set()
        if (file, name) in seen or file not in infos:
            return None
        seen.add((file, name))
        info = infos[file]
        if name == "default":
            var = info["default"]
        else:
            var = info["exports"].get(name)
        if var:
            if var in info["routers"]:
                return file, var
            if var in info["factories"]:
                return file, info["factories"][var]
            if var in info["imports"]:
                tf, tn = info["imports"][var]
                return router_of(tf, tn, seen)
        for target, names in info["reexports"]:
            if names is None:
                hit = router_of(target, name, seen)
            else:
                hit = None
                for part in names.split(","):
                    bits = re.split(r"\s+as\s+", part.strip())
                    if bits[-1].strip() == name:
                        hit = router_of(target, bits[0].strip(), seen)
            if hit:
                return hit
        return None

    def resolve(file: str, expr: str):
        expr = expr.strip()
        call = re.fullmatch(r"([A-Za-z_$][\w$.]*)\s*\(\s*\)", expr)
        if call:
            expr = call.group(1)
            factory = True
        else:
            factory = False
        info = infos[file]
        if "." in expr:
            ns, member = expr.split(".", 1)
            imp = info["imports"].get(ns)
            return router_of(imp[0], member.split(".")[0]) if imp and imp[1] == "*" else None
        if expr in info["routers"] and not factory:
            return file, expr
        if factory and expr in info["factories"]:
            return file, info["factories"][expr]
        if expr in info["imports"]:
            tf, tn = info["imports"][expr]
            return router_of(tf, tn)
        # `const billingRoutes = createBillingRoutes()` style alias
        am = re.search(r"(?:const|let|var)\s+" + re.escape(expr) + r"\s*=\s*([A-Za-z_$][\w$.]*)\s*\(\s*\)", info["text"])
        if am:
            return resolve(file, am.group(1) + "()")
        return None

    out: list[dict] = []
    emitted: set[tuple] = set()
    claimed: set[tuple] = set()           # routers that some app mounts

    def walk(file: str, var: str, prefix: str, depth=0):
        if depth > 8:
            return
        info = infos[file]
        for verb, path, line, doc in info["routers"].get(var, []):
            key = (file, verb, _join(prefix, path), line)
            if key not in emitted:
                emitted.add(key)
                out.append(_route(file, verb, _join(prefix, path), line, "", doc))
        for owner, pre, expr in info["mounts"]:
            if owner == var:
                hit = resolve(file, expr)
                if hit:
                    walk(hit[0], hit[1], _join(prefix, pre), depth + 1)

    for file, info in infos.items():
        for _owner, _pre, expr in info["mounts"]:
            hit = resolve(file, expr)
            if hit:
                claimed.add(hit)
    for file, info in infos.items():     # roots: apps and routers nobody mounts
        for var in info["routers"]:
            if (file, var) not in claimed:
                walk(file, var, "")
    # Next.js file routes
    for rel, text in files.items():
        m = re.search(r"(?:^|/)app/(.*)/route\.(?:ts|js|tsx|jsx|mjs)$", rel) or re.search(r"(?:^|/)pages/(api/.*)\.(?:ts|js|tsx|jsx)$", rel)
        if m:
            url = "/" + re.sub(r"/index$", "", m.group(1))
            verbs = re.findall(r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b|export\s+const\s+(GET|POST|PUT|PATCH|DELETE)\b", text)
            for v in verbs or [("ANY", "")]:
                out.append(_route(rel, v[0] or v[1], url, 1))
    return out


def extract(files: dict[str, str]) -> list[dict]:
    """files: relative path -> text. Returns routes sorted by file and line."""
    routes: list[dict] = []
    fileset = set(files)
    infos = {}
    for rel, text in files.items():
        if rel.endswith(".py"):
            info = _py_collect(rel, text, fileset)
            if info:
                infos[rel] = info
                routes += _py_routes(rel, text, info)
    routes += _py_framework(infos)
    routes += _js_routes(files)
    seen, out = set(), []
    for r in sorted(routes, key=lambda r: (r["f"], r["l"], r["m"], r["p"])):
        key = (r["f"], r["m"], r["p"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def http_calls(files: dict[str, str]) -> list[tuple[str, str, str, int]]:
    """(file, METHOD, path, line) of literal requests made from JS/TS (fetch / axios / ky / $.ajax style) and Python (requests / httpx)."""
    calls = []
    for rel, text in files.items():
        if rel.endswith(JS_EXT):
            masked = re.sub(r"//[^\n]*|/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
            for m in re.finditer(r"""\bfetch\(\s*(['"`])((?:/|https?://[^/'"`]+/)[^'"`\n$]*)\1\s*(?:,\s*\{(.{0,160}?)\})?""", masked, re.S):
                opts = m.group(3) or ""
                mm = re.search(r"method\s*:\s*['\"](\w+)['\"]", opts)
                calls.append((rel, (mm.group(1) if mm else "GET").upper(), re.sub(r"^https?://[^/]+", "", m.group(2)), _line(text, m.start())))
            for m in re.finditer(r"""\b(?:axios|api|http|client|ky)\s*\.\s*(get|post|put|patch|delete)\(\s*(['"`])((?:/|https?://[^/'"`]+/)[^'"`\n$]*)\2""", masked):
                calls.append((rel, m.group(1).upper(), re.sub(r"^https?://[^/]+", "", m.group(3)), _line(text, m.start())))
        elif rel.endswith(".py"):
            for m in re.finditer(r"""\b(?:requests|httpx|session)\s*\.\s*(get|post|put|patch|delete)\(\s*f?(['"])(https?://[^/'"]+(/[^'"{\n]*)?)\2""", text):
                calls.append((rel, m.group(1).upper(), m.group(4) or "/", _line(text, m.start())))
    return calls


def match(route_path: str, call_path: str) -> bool:
    """A request path matches a route path; `:id` / `{id}` / `<id>` segments match any one segment, `*` any rest."""
    call_path = call_path.split("?")[0]
    if route_path.endswith("*"):
        return call_path.startswith(route_path[:-1])
    a, b = route_path.strip("/").split("/"), call_path.strip("/").split("/")
    if len(a) != len(b):
        return False
    return all(x == y or x.startswith(":") or (x.startswith("{") and x.endswith("}")) or (x.startswith("<") and x.endswith(">")) for x, y in zip(a, b))
