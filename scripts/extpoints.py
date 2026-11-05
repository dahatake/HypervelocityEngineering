#!/usr/bin/env python3
"""extpoints.py - project-specific extension points of the data-layer checks (FR-1082).

A project adds its own checks (e.g. an external-integration catalog check) WITHOUT editing the toolkit's
scripts/*.py or scripts/metadata.json.  Two ways to register (both survive `tools/install.py` updates):

  1. scripts/ebak.config.json  ->  "extensions": {"checks": [{"module": "m", "function": "f", "target": "rdcheck"}]}
     `module` is importable from scripts/ (scripts/m.py, or "ext.m" = scripts/ext/m.py);
     `target` is "rdcheck", "rdfix" or "both" (default "both").
  2. scripts/ext/*.py  ->  auto-loaded.  Every public function defined in the file is a check
     (or, if the file defines CHECKS = [fn, ...], exactly those).  A function attribute `target`
     or a module-level TARGET picks the target (default "both").

A check is `fn(root, cfg)` (root: pathlib.Path of the repository, cfg: the merged ebak.config.json dict; a check
that takes no parameters, or only `root`, is also accepted) and returns a list of findings; an empty list (or None)
means pass.  A finding is a string, a dict {level, chk, loc, msg}, a (level, chk, loc, msg) tuple, or an object with
those attributes (rdcheck.Finding).  Level "ERROR" (default) fails; "WARN" does not.  The same check registered
both ways is called once.  A module that cannot be loaded, a missing function, or an exception is never swallowed:
it is reported as an ERROR that names the extension.
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

TARGETS = ("rdcheck", "rdfix", "both")
Finding4 = Tuple[str, str, str, str]  # level, chk, loc, msg


@dataclass
class Ext:
    module: str
    function: str
    target: str
    source: str  # "config" | "ext"
    fn: Callable = field(repr=False, default=None)  # type: ignore[assignment]

    @property
    def name(self) -> str:
        return f"{self.module}.{self.function}"

    def key(self) -> Tuple[str, str]:
        return (self.module.rsplit(".", 1)[-1], self.function)


@dataclass
class ExtResult:
    ext: Ext
    findings: List[Finding4]

    @property
    def result(self) -> str:
        if any(f[0] == "ERROR" for f in self.findings):
            return "fail"
        return "warn" if self.findings else "pass"

    def line(self, target: str) -> str:
        return f"EXT {self.ext.name} target={target} result={self.result} findings={len(self.findings)} source={self.ext.source}"


def _entries(cfg: dict) -> List[dict]:
    ext = cfg.get("extensions") or {}
    checks = ext.get("checks") if isinstance(ext, dict) else None
    return [c for c in checks] if isinstance(checks, list) else []


def _add_path(root: Path) -> None:
    for p in (root / "scripts", Path(__file__).resolve().parent):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


def _norm(raw, name: str) -> List[Finding4]:
    if raw is None:
        return []
    if isinstance(raw, (str, bytes)) or not hasattr(raw, "__iter__") or isinstance(raw, dict):
        raw = [raw]
    out: List[Finding4] = []
    for it in raw:
        level, chk, loc, msg = "ERROR", f"EXT-{name}", "-", ""
        if isinstance(it, dict):
            level = it.get("level") or it.get("severity") or level
            chk = it.get("chk") or it.get("id") or chk
            loc = it.get("loc") or it.get("location") or loc
            msg = it.get("msg") or it.get("message") or ""
        elif isinstance(it, (tuple, list)) and len(it) == 4:
            level, chk, loc, msg = it
        elif all(hasattr(it, a) for a in ("level", "chk", "loc", "msg")):
            level, chk, loc, msg = it.level, it.chk, it.loc, it.msg
        else:
            msg = str(it)
        level = str(level).upper()
        level = "WARN" if level.startswith("WARN") else "ERROR"
        out.append((level, str(chk), str(loc), f"[{name}] {msg}"))
    return out


def _load_ext_file(path: Path):
    modname = f"ebak_ext_{path.stem}"
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"{path} を読み込めません")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(modname, None)
        raise
    return mod


def discover(root: Path, cfg: dict) -> Tuple[List[Ext], List[Finding4]]:
    """Registered extensions (de-duplicated) and the load errors (ERROR findings naming the extension)."""
    root = Path(root)
    _add_path(root)
    exts: List[Ext] = []
    errors: List[Finding4] = []
    seen = set()

    def add(e: Ext) -> None:
        if e.key() not in seen:
            seen.add(e.key())
            exts.append(e)

    def err(name: str, loc: str, msg: str) -> None:
        errors.append(("ERROR", "EXT-LOAD", loc, f"拡張 {name} を呼べません: {msg}"))

    for i, c in enumerate(_entries(cfg)):
        loc = f"scripts/ebak.config.json:extensions.checks[{i}]"
        if not isinstance(c, dict) or not c.get("module") or not c.get("function"):
            err(str(c), loc, "module と function が必要です")
            continue
        mod, fn_name, target = str(c["module"]), str(c["function"]), str(c.get("target") or "both")
        name = f"{mod}.{fn_name}"
        if target not in TARGETS:
            err(name, loc, f"target は {', '.join(TARGETS)} のどれかです（指定: {target}）")
            continue
        try:
            sys.modules.pop(mod, None)  # always the file on disk (an update or a test may have changed it)
            fn = getattr(importlib.import_module(mod), fn_name, None)
        except BaseException as exc:  # noqa: BLE001 - reported, never swallowed
            err(name, loc, f"{type(exc).__name__}: {exc}")
            continue
        if not callable(fn):
            err(name, loc, f"モジュール {mod} に関数 {fn_name} がありません")
            continue
        add(Ext(mod, fn_name, target, "config", fn))

    ext_dir = root / "scripts" / "ext"
    for p in sorted(ext_dir.glob("*.py")) if ext_dir.is_dir() else []:
        if p.name.startswith("_"):
            continue
        rel = f"scripts/ext/{p.name}"
        try:
            mod = _load_ext_file(p)
        except BaseException as exc:  # noqa: BLE001
            err(p.stem, rel, f"{type(exc).__name__}: {exc}")
            continue
        listed = getattr(mod, "CHECKS", None)
        if listed is not None:
            fns = [f for f in listed if callable(f)]
        else:
            fns = [f for n, f in vars(mod).items()
                   if inspect.isfunction(f) and not n.startswith("_") and f.__module__ == mod.__name__]
        for f in fns:
            target = str(getattr(f, "target", None) or getattr(mod, "TARGET", None) or "both")
            if target not in TARGETS:
                err(f"{p.stem}.{f.__name__}", rel, f"target は {', '.join(TARGETS)} のどれかです（指定: {target}）")
                continue
            add(Ext(p.stem, f.__name__, target, "ext", f))
    return exts, errors


def _call(e: Ext, root: Path, cfg: dict) -> List[Finding4]:
    try:
        n = len([p for p in inspect.signature(e.fn).parameters.values()
                 if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])
        var = any(p.kind == p.VAR_POSITIONAL for p in inspect.signature(e.fn).parameters.values())
    except (TypeError, ValueError):
        n, var = 2, True
    args = (root, cfg) if var or n >= 2 else ((root,) if n == 1 else ())
    try:
        return _norm(e.fn(*args), e.name)
    except BaseException as exc:  # noqa: BLE001 - an extension must never be swallowed (AC-460)
        if isinstance(exc, KeyboardInterrupt):
            raise
        return [("ERROR", "EXT-ERROR", "-", f"拡張 {e.name} が例外で終わりました: {type(exc).__name__}: {exc}")]


def run(root: Path, cfg: dict, target: str) -> Tuple[List[ExtResult], List[Ext], List[Finding4]]:
    """Call the extensions for `target` ("rdcheck" or "rdfix").  Returns (results, not-called extensions, load errors)."""
    root = Path(root)
    exts, errors = discover(root, cfg)
    results: List[ExtResult] = []
    skipped: List[Ext] = []
    for e in exts:
        if e.target in (target, "both"):
            results.append(ExtResult(e, _call(e, root, cfg)))
        else:
            skipped.append(e)
    return results, skipped, errors


def all_findings(results: List[ExtResult], errors: List[Finding4]) -> List[Finding4]:
    return list(errors) + [f for r in results for f in r.findings]


def registered_modules(root: Path, cfg: dict) -> set:
    """Module names registered as extensions (config modules and scripts/ext/*.py stems), for the installer's warning."""
    out = {str(c.get("module")).rsplit(".", 1)[-1] for c in _entries(cfg) if isinstance(c, dict) and c.get("module")}
    ext_dir = Path(root) / "scripts" / "ext"
    if ext_dir.is_dir():
        out |= {p.stem for p in ext_dir.glob("*.py")}
    return out
