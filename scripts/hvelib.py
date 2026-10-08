"""Shared helpers for the Enterprise App Build Kit scripts (Python 3.9+, standard library only).

The scripts under scripts/ import this module. It parses the management data
(requirements definition, catalog, ID registry, system-test ledger) and manages
the temporary run state under /work.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

TOOLKIT_VERSION = "0.2.0"

SPECKIT_PATHS = [".specify/**", "specs/**/*.md"]

DEFAULT_CONFIG: dict = {
    "management_files": {
        "requirements": "docs/requirements-definition.md",
        "requirements_dir": "docs/requirements",
        "catalog": "docs/catalog.md",
        "id_registry": "docs/id-registry.md",
        "run_history": "docs/run-history.md",
        "ledger": "tests/system/ledger.json",
        "manual_tests": "docs/manual-tests.md",
    },
    "base_branch": "main",
    "work": {"dir": "work", "retention_days": 14},
    "verify": {"commands": [], "timeout_sec": 1800},
    "checks": {
        "ambiguous_words": [
            "適切", "適宜", "なるべく", "できるだけ", "可能な限り", "十分な", "迅速", "高速に", "簡単",
            "容易", "直感的", "柔軟", "使いやすい", "必要に応じて", "モダン", "シームレス",
            "ユーザーフレンドリー", "効率的", "最適",
        ],
        "unit_pattern": r"(?<![A-Za-z0-9\-.])\d+(?:[.,]\d+)?\s*(?:ミリ秒|秒|分|時間|日間|日|週間|週|か月|ヶ月|カ月|年|件|回|%|％|ms|MB|GB|KB|TB|円|人|文字|px|行)",
        "id_scan_exclude": [
            "docs/**", "work/**", ".github/**", "scripts/**", "tools/**", "users-guide/**",
            "tests/toolkit/**", "templates/**", "node_modules/**", "**/node_modules/**", ".git/**",
            "**/*.lock", "**/package-lock.json", "AGENTS.md", "README.md", "**/*.svg",
            # GitHub Spec Kit artifacts use their own FR-/SC- numbering (imported via scripts/import-speckit.py)
            *SPECKIT_PATHS,
        ],
        "test_path_pattern": r"(^|/)(tests?|__tests__|spec|specs|e2e)(/|$)|(^|/)(test_[^/]*|[^/]*_test\.[^/]+|[^/]*\.(test|spec)\.[^/]+|[^/]*Tests?\.[^/]+)$",
        "temp_file_pattern": r"\.(log|har|trace|webm)$|(^|/)(trace[^/]*\.zip|results[^/]*\.json)$|(^|/)(evidence|screenshots|test-results|playwright-report)/",
    },
    "gates": {
        "enabled": True,
        "subagent_verify": {
            "implementer": ["--quick"],
            "test-designer": ["--docs-only"],
            "rd-author": ["--docs-only"],
        },
        "subagent_verify_max_blocks": 3,
        "agent_stop_max_blocks": 40,
        "enforce_conductor_edit_scope": True,
        # G-7: deny `task` calls that do not pass the model fixed in "models" (only while a run is active)
        "enforce_models": True,
        "deploy_patterns": [
            r"\bazd\s+(up|deploy|provision)\b",
            r"\baz\s+deployment\s+\S+\s+create\b",
            r"\baz\s+(webapp|functionapp|containerapp|staticwebapp)\s+(up|deploy|create)\b",
            r"\bterraform\s+(apply|destroy)\b",
            r"\bpulumi\s+(up|destroy)\b",
            r"\bkubectl\s+(apply|delete|create|replace)\b",
            r"\bhelm\s+(install|upgrade|uninstall)\b",
            r"\bfunc\s+azure\s+functionapp\s+publish\b",
            r"\bswa\s+deploy\b",
            r"\b(vercel|netlify)\s+(deploy|--prod)\b",
            r"\bfirebase\s+deploy\b",
            r"\bcdk\s+deploy\b",
            r"\bserverless\s+deploy\b",
            r"\b(npm|pnpm|yarn)\s+publish\b",
            r"\btwine\s+upload\b",
            r"\bdotnet\s+nuget\s+push\b",
            r"\bgh\s+release\s+create\b",
            r"\bdocker\s+push\b",
        ],
        # Tools contributed by MCP servers, plugins and extensions (anything not in gate.py BUILTIN_TOOLS).
        # A tool name whose words contain one of these verbs is treated as a change to an external system.
        "external_write_verbs": [
            "create", "update", "upsert", "delete", "remove", "destroy", "purge", "drop", "write", "insert",
            "add", "put", "patch", "post", "send", "reply", "forward", "comment", "submit", "merge", "close",
            "reopen", "resolve", "approve", "assign", "unassign", "cancel", "start", "stop", "restart", "scale",
            "invoke", "do_action", "apply", "upload", "move", "rename", "archive", "share", "grant", "revoke",
            "enable", "disable", "schedule", "accept", "decline", "transfer", "push", "commit", "trigger",
            "dispatch", "rerun", "edit", "modify",
        ],
        "external_deploy_verbs": ["deploy", "provision", "publish", "release"],
        "external_tool_allow": [],
    },
}

ID_KIND_RE = r"(?:G|FR|AC|Q|PARAM|SRC|NFR-[A-Z0-9]+)"
ID_RE = re.compile(r"(?<![A-Za-z0-9\-])(" + ID_KIND_RE + r")-(\d{3,})(?![0-9])")
REQ_ID_RE = re.compile(r"(?<![A-Za-z0-9\-])((?:FR|NFR-[A-Z0-9]+)-\d{3,})(?![0-9])")
CODE_ID_RE = re.compile(r"(?<![A-Za-z0-9\-])((?:FR|AC|NFR-[A-Z0-9]+)-\d{3,})(?![0-9])")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
REQ_HEADING_RE = re.compile(r"^(#{2,6})\s+\**((?:FR|NFR-[A-Z0-9]+)-\d{3,})\**\s*(.*)$")
AC_HEADING_RE = re.compile(r"^(#{2,6})\s+\**(AC-\d{3,})\**\s*(.*)$")
GENERIC_HEADING_DEF_RE = re.compile(r"^#{2,6}\s+\**((?:G|Q|PARAM|SRC)-\d{3,})\**(?:\s|$)")
TABLE_DEF_RE = re.compile(r"^\|\s*\**(" + ID_KIND_RE + r"-\d{3,})\**\s*\|")
LIST_DEF_RE = re.compile(r"^\s{0,4}[-*]\s+\**((?:G|Q|PARAM|SRC)-\d{3,})\**\s*[:：]")
AC_BULLET_RE = re.compile(r"^\s{0,4}[-*]\s+(?:受入基準\s*)?\**(AC-\d{3,})\**\s*[:：]\s*(.*)$")
SUB_BULLET_RE = re.compile(r"^\s{2,}[-*]\s+(.*)$")
TOP_BULLET_RE = re.compile(r"^\s{0,1}[-*]\s+(.*)$")
PARAM_REF_RE = re.compile(r"\{(PARAM-\d{3,})\}")

STATES = ("承認済み", "承認待ち", "保留", "却下", "廃止")
VERIFICATION_LEVELS = ("system", "integration", "unit", "manual")
AC_META_KEYS = ("検証レベル", "BLOCKED", "対応する要求", "決定状態")
AC_TEXT_KEYS = ("内容", "判定条件", "観察できる結果", "起点", "事前条件", "対象")
ANSWERED_RE = re.compile(r"回答済み|解決済み|取り下げ|クローズ")


# --------------------------------------------------------------------------- io

def setup_io() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def new_run_id() -> str:
    return _dt.datetime.now().strftime("%Y%m%d%H%M")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(read_text(path))


def write_json(path: Path, data) -> None:
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def load_script(name: str):
    """Import a sibling script whose file name contains hyphens (e.g. next-id.py)."""
    import importlib.util
    modname = "hve_" + name.replace("-", "_")
    if modname in sys.modules:
        return sys.modules[modname]
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(modname, str(path))
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# --------------------------------------------------------------------------- git / repo

def run(cmd, cwd: Optional[Path] = None, timeout: Optional[int] = None, shell: bool = False) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, shell=shell,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError:
        return 127, f"command not found: {cmd if isinstance(cmd, str) else cmd[0]}"
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        return 124, f"{out}\nTIMEOUT after {timeout}s"


def git(args: List[str], cwd: Path) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        return proc.returncode, (proc.stdout or "").rstrip("\n")
    except FileNotFoundError:
        return 127, ""


def repo_root(start: Optional[Path] = None) -> Path:
    start = Path(start or os.getcwd()).resolve()
    rc, out = git(["rev-parse", "--show-toplevel"], start)
    if rc == 0 and out.strip():
        return Path(out.strip()).resolve()
    for p in [start, *start.parents]:
        if (p / ".git").exists():
            return p
    return start


def current_branch(root: Path) -> str:
    rc, out = git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    return out.strip() if rc == 0 else ""


def head_commit(root: Path) -> str:
    rc, out = git(["rev-parse", "--short", "HEAD"], root)
    return out.strip() if rc == 0 else ""


def ref_exists(root: Path, ref: str) -> bool:
    rc, _ = git(["rev-parse", "--verify", "--quiet", ref + "^{commit}"], root)
    return rc == 0


def default_base(root: Path, cfg: dict) -> Optional[str]:
    """merge-base of HEAD and the base branch, or None when HEAD is the base itself."""
    base = cfg.get("base_branch", "main")
    for cand in (base, f"origin/{base}"):
        if ref_exists(root, cand):
            rc, out = git(["merge-base", "HEAD", cand], root)
            if rc == 0 and out.strip():
                mb = out.strip()
                rc2, head = git(["rev-parse", "HEAD"], root)
                if rc2 == 0 and head.strip() == mb:
                    return None
                return mb
    return None


def git_show(root: Path, ref: str, rel: str) -> Optional[str]:
    rc, out = git(["show", f"{ref}:{rel}"], root)
    return out + "\n" if rc == 0 else None


def tracked_files(root: Path, include_untracked: bool = True) -> List[str]:
    rc, out = git(["ls-files", "-z"], root)
    files: List[str] = []
    if rc == 0:
        files = [f for f in out.split("\0") if f]
        if include_untracked:
            rc2, out2 = git(["ls-files", "-z", "-o", "--exclude-standard"], root)
            if rc2 == 0:
                files += [f for f in out2.split("\0") if f]
        return sorted(set(f.replace("\\", "/") for f in files if (root / f).is_file()))
    for p in root.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            files.append(p.relative_to(root).as_posix())
    return sorted(files)


_GLOB_CACHE: Dict[str, "re.Pattern[str]"] = {}


def _glob_to_re(pat: str) -> "re.Pattern[str]":
    if pat in _GLOB_CACHE:
        return _GLOB_CACHE[pat]
    i, out = 0, ""
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**/", i):
            out += r"(?:.*/)?"
            i += 3
            continue
        if pat.startswith("**", i):
            out += r".*"
            i += 2
            continue
        if c == "*":
            out += r"[^/]*"
        elif c == "?":
            out += r"[^/]"
        else:
            out += re.escape(c)
        i += 1
    rx = re.compile("^" + out + "$")
    _GLOB_CACHE[pat] = rx
    return rx


def glob_match(rel: str, patterns: Iterable[str]) -> bool:
    return any(_glob_to_re(p).match(rel) for p in patterns)


# --------------------------------------------------------------------------- config

def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(root: Path) -> dict:
    path = root / "scripts" / "hve.config.json"
    cfg = DEFAULT_CONFIG
    if path.exists():
        try:
            cfg = _deep_merge(DEFAULT_CONFIG, json.loads(read_text(path)))
        except json.JSONDecodeError as exc:
            print(f"WARN config: scripts/hve.config.json を読めません: {exc}", file=sys.stderr)
    return cfg


def mf(cfg: dict, key: str) -> str:
    return cfg["management_files"][key]


# --------------------------------------------------------------------------- markdown tables

@dataclass
class Table:
    heading: str
    header_line: int
    header: List[str]
    rows: List[Tuple[int, List[str]]]

    def col(self, *names: str) -> Optional[int]:
        for i, h in enumerate(self.header):
            hn = h.replace(" ", "")
            for n in names:
                if n.replace(" ", "") in hn:
                    return i
        return None


def split_row(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur, esc = [], "", False
    for ch in s:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            cur += ch
            esc = True
        elif ch == "|":
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
    cells.append(cur.strip())
    return cells


def parse_tables(lines: List[str]) -> List[Table]:
    tables: List[Table] = []
    heading = ""
    i = 0
    in_code = False
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_code = not in_code
            i += 1
            continue
        if in_code:
            i += 1
            continue
        m = HEADING_RE.match(line)
        if m:
            heading = m.group(2)
        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            header = split_row(line)
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append((j + 1, split_row(lines[j])))
                j += 1
            tables.append(Table(heading, i + 1, header, rows))
            i = j
            continue
        i += 1
    return tables


def strip_md(s: str) -> str:
    return re.sub(r"[*`]", "", s or "").strip()


# --------------------------------------------------------------------------- requirements

@dataclass
class AC:
    id: str
    file: str
    line: int
    text: str = ""
    sub: List[str] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)
    requirement: Optional[str] = None

    @property
    def level(self) -> str:
        return strip_md(self.meta.get("検証レベル", "")).split()[0].lower() if strip_md(self.meta.get("検証レベル", "")) else ""

    @property
    def blocked(self) -> bool:
        return "BLOCKED" in self.meta or bool(re.search(r"\bBLOCKED\b", self.text))

    @property
    def blocked_ref(self) -> str:
        if "BLOCKED" in self.meta:
            return self.meta["BLOCKED"]
        m = re.search(r"BLOCKED[^\n]*", self.text)
        return m.group(0) if m else ""

    def full_text(self) -> str:
        return "\n".join([self.text, *self.sub]).strip()


@dataclass
class Requirement:
    id: str
    title: str
    file: str
    line: int
    level: int
    fields: Dict[str, str] = field(default_factory=dict)
    acs: List[str] = field(default_factory=list)
    body: List[str] = field(default_factory=list)

    @property
    def state_raw(self) -> str:
        return self.fields.get("決定状態", "")

    @property
    def state(self) -> str:
        return normalize_state(self.state_raw)

    @property
    def basis(self) -> str:
        m = re.search(r"[（(]([^）)]*)[）)]", self.state_raw)
        return m.group(1).strip() if m else ""

    @property
    def priority(self) -> str:
        m = re.match(r"\s*\**(MUST|SHOULD|MAY)\b", self.fields.get("優先度", ""), re.I)
        return m.group(1).upper() if m else ""

    @property
    def statement(self) -> str:
        return self.fields.get("要求", "")

    @property
    def active(self) -> bool:
        return self.state not in ("却下", "廃止")


def normalize_state(raw: str) -> str:
    s = strip_md(raw)
    s = re.sub(r"[（(][^）)]*[）)]", "", s).strip()
    if s.startswith("承認済み"):
        return "承認済み"
    if "承認待ち" in s:
        return "承認待ち"
    for st in ("保留", "却下", "廃止"):
        if st in s:
            return st
    return s


def parse_fields(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in re.split(r"\u3000+", text):
        m = re.match(r"^\s*\**([^:：*（(]{1,20}?)\**\s*[:：]\s*(.*)$", part)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


@dataclass
class Definition:
    id: str
    file: str
    line: int


@dataclass
class RequirementsDoc:
    files: List[str] = field(default_factory=list)
    defs: Dict[str, List[Definition]] = field(default_factory=dict)
    requirements: Dict[str, Requirement] = field(default_factory=dict)
    acs: Dict[str, AC] = field(default_factory=dict)
    params: Dict[str, Dict[str, str]] = field(default_factory=dict)
    questions: Dict[str, Dict[str, object]] = field(default_factory=dict)
    terms: List[Tuple[str, List[str]]] = field(default_factory=list)
    has_ui_policy: bool = False
    no_ui: bool = False
    persona_headers: List[List[str]] = field(default_factory=list)
    text: Dict[str, str] = field(default_factory=dict)
    exists: bool = False

    def kind_ids(self, kind: str) -> List[str]:
        return [i for i in self.defs if id_kind(i) == kind]


def id_kind(id_: str) -> str:
    m = re.match(r"^(" + ID_KIND_RE + r"|E2E|IT)-\d+$", id_)
    return m.group(1) if m else ""


def id_num(id_: str) -> int:
    m = re.search(r"-(\d+)$", id_)
    return int(m.group(1)) if m else 0


def requirement_files(root: Path, cfg: dict) -> List[Path]:
    main = root / mf(cfg, "requirements")
    files = [main] if main.exists() else []
    split_dir = root / mf(cfg, "requirements_dir")
    if split_dir.is_dir():
        files += sorted(p for p in split_dir.rglob("*.md") if p.is_file())
    return files


def parse_requirements(root: Path, cfg: dict) -> RequirementsDoc:
    texts = {p.relative_to(root).as_posix(): read_text(p) for p in requirement_files(root, cfg)}
    return parse_requirements_texts(texts)


def strip_comments(text: str) -> str:
    """Blank out HTML comments while keeping line numbers."""
    return re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)


def parse_requirements_texts(texts: Dict[str, str]) -> RequirementsDoc:
    doc = RequirementsDoc()
    doc.exists = bool(texts)
    for rel, text in texts.items():
        text = strip_comments(text)
        doc.files.append(rel)
        doc.text[rel] = text
        _parse_one(doc, rel, text.splitlines())
    _parse_tables(doc)
    return doc


def _add_def(doc: RequirementsDoc, id_: str, rel: str, line: int) -> None:
    doc.defs.setdefault(id_, []).append(Definition(id_, rel, line))


def _apply_ac_fields(ac: AC, content: str, allow_text: bool) -> None:
    f = parse_fields(content)
    hit = False
    for k, v in f.items():
        if k in AC_META_KEYS:
            ac.meta[k] = v
            hit = True
        elif k in AC_TEXT_KEYS:
            ac.sub.append(f"{k}: {v}")
            hit = True
    if not hit and allow_text:
        ac.sub.append(content)
    if "対応する要求" in ac.meta and not ac.requirement:
        m = REQ_ID_RE.search(ac.meta["対応する要求"])
        if m:
            ac.requirement = m.group(1)


def _parse_one(doc: RequirementsDoc, rel: str, lines: List[str]) -> None:
    cur_req: Optional[Requirement] = None
    cur_ac: Optional[AC] = None
    ac_owned_block = False  # AC defined by its own heading (not nested in a requirement)
    in_code = False
    for idx, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        hm = HEADING_RE.match(line)
        if hm:
            level = len(hm.group(1))
            if re.search(r"既定制約|ui_policy|UI\s*の方針", hm.group(2), re.I):
                doc.has_ui_policy = True
            rm = REQ_HEADING_RE.match(line)
            am = AC_HEADING_RE.match(line)
            if cur_req and level <= cur_req.level:
                cur_req = None
            cur_ac, ac_owned_block = None, False
            if rm:
                rid = rm.group(2)
                cur_req = Requirement(rid, strip_md(rm.group(3)), rel, idx, level)
                _add_def(doc, rid, rel, idx)
                doc.requirements.setdefault(rid, cur_req)
            elif am:
                aid = am.group(2)
                cur_ac = AC(aid, rel, idx, text=strip_md(am.group(3)))
                if cur_req:
                    cur_ac.requirement = cur_req.id
                    cur_req.acs.append(aid)
                ac_owned_block = True
                _add_def(doc, aid, rel, idx)
                doc.acs.setdefault(aid, cur_ac)
            else:
                gm = GENERIC_HEADING_DEF_RE.match(line)
                if gm:
                    _add_def(doc, gm.group(1), rel, idx)
            continue
        if "画面を持たない" in line:
            doc.no_ui = True
        tm = TABLE_DEF_RE.match(line)
        if tm:
            if not REQ_ID_RE.fullmatch(tm.group(1)):
                _add_def(doc, tm.group(1), rel, idx)
            continue
        acm = AC_BULLET_RE.match(line)
        if acm:
            aid = acm.group(1)
            cur_ac = AC(aid, rel, idx, text=acm.group(2).strip())
            ac_owned_block = False
            if cur_req:
                cur_ac.requirement = cur_req.id
                cur_req.acs.append(aid)
            _add_def(doc, aid, rel, idx)
            doc.acs.setdefault(aid, cur_ac)
            continue
        lm = LIST_DEF_RE.match(line)
        if lm:
            _add_def(doc, lm.group(1), rel, idx)
            cur_ac = None
            continue
        sm = SUB_BULLET_RE.match(line)
        if sm and cur_ac is not None:
            _apply_ac_fields(cur_ac, sm.group(1).strip(), allow_text=True)
            continue
        bm = TOP_BULLET_RE.match(line)
        if bm:
            content = bm.group(1).strip()
            if cur_ac is not None and ac_owned_block:
                _apply_ac_fields(cur_ac, content, allow_text=False)
                continue
            if cur_req is not None:
                cur_ac = None
                for k, v in parse_fields(content).items():
                    cur_req.fields.setdefault(k, v)
                cur_req.body.append(content)
            continue
        if cur_req is not None and line.strip():
            cur_req.body.append(line.strip())


def _parse_tables(doc: RequirementsDoc) -> None:
    for rel, text in doc.text.items():
        lines = text.splitlines()
        for t in parse_tables(lines):
            first = [strip_md(r[1][0]) if r[1] else "" for r in t.rows]
            if any(re.fullmatch(r"PARAM-\d{3,}", f) for f in first):
                vcol, ucol = t.col("値"), t.col("単位")
                for (ln, cells), fid in zip(t.rows, first):
                    if re.fullmatch(r"PARAM-\d{3,}", fid):
                        doc.params.setdefault(fid, {
                            "value": cells[vcol] if vcol is not None and vcol < len(cells) else "",
                            "unit": cells[ucol] if ucol is not None and ucol < len(cells) else "",
                            "file": rel, "line": str(ln),
                        })
            if any(re.fullmatch(r"Q-\d{3,}", f) for f in first):
                for (ln, cells), fid in zip(t.rows, first):
                    if re.fullmatch(r"Q-\d{3,}", fid):
                        doc.questions.setdefault(fid, {
                            "answered": bool(ANSWERED_RE.search(" ".join(cells[1:]))),
                            "file": rel, "line": ln,
                        })
            hdr = " ".join(t.header)
            if "用語" in hdr and "禁止" in hdr:
                tcol, fcol = t.col("用語"), t.col("禁止")
                for _, cells in t.rows:
                    if tcol is None or fcol is None or fcol >= len(cells):
                        continue
                    forb = [w.strip() for w in re.split(r"[、,/／]", strip_md(cells[fcol]))
                            if w.strip() and w.strip() not in ("-", "なし", "—")]
                    if forb:
                        doc.terms.append((strip_md(cells[tcol]), forb))
            if any("ペルソナ" in h for h in t.header) or "ペルソナ" in t.heading:
                doc.persona_headers.append(t.header)
        for d_id, defs in doc.defs.items():
            if not d_id.startswith("Q-") or d_id in doc.questions:
                continue
            for d in defs:
                if d.file == rel:
                    block = "\n".join(lines[d.line - 1:d.line + 8])
                    doc.questions[d_id] = {"answered": bool(ANSWERED_RE.search(block)), "file": rel, "line": d.line}


def expand_params(text: str, params: Dict[str, Dict[str, str]]) -> str:
    def rep(m: "re.Match[str]") -> str:
        p = params.get(m.group(1))
        if not p:
            return m.group(0)
        return f"{strip_md(p.get('value', ''))}{strip_md(p.get('unit', ''))}"
    return PARAM_REF_RE.sub(rep, text)


def ac_digest(ac: AC, params: Dict[str, Dict[str, str]]) -> str:
    text = expand_params(ac.full_text(), params)
    norm = re.sub(r"\s+", " ", text).strip()
    return "sha256:" + hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def system_acs(doc: RequirementsDoc) -> List[AC]:
    """Approved, non-BLOCKED ACs with verification level 'system' (the 1:1 scope, A-3)."""
    out = []
    for ac in doc.acs.values():
        req = doc.requirements.get(ac.requirement or "")
        if req and req.state == "承認済み" and not ac.blocked and ac.level == "system":
            out.append(ac)
    return out


# --------------------------------------------------------------------------- catalog

@dataclass
class CatalogRow:
    table: str
    line: int
    cells: Dict[str, str]


def parse_catalog(root: Path, cfg: dict) -> Tuple[bool, List[CatalogRow], List[Tuple[int, str]]]:
    """Returns (exists, function-table rows, [(line, path)] for every file reference)."""
    path = root / mf(cfg, "catalog")
    if not path.exists():
        return False, [], []
    rows: List[CatalogRow] = []
    refs: List[Tuple[int, str]] = []
    for t in parse_tables(strip_comments(read_text(path)).splitlines()):
        is_func = t.col("要求 ID", "要求ID") is not None and t.col("決定状態") is not None
        file_cols = [i for i, h in enumerate(t.header) if re.search(r"ファイル|テスト", h)]
        for ln, cells in t.rows:
            named = {t.header[i]: (cells[i] if i < len(cells) else "") for i in range(len(t.header))}
            if is_func:
                rows.append(CatalogRow(t.heading, ln, named))
            for c in file_cols:
                if c < len(cells):
                    for p in split_paths(cells[c]):
                        refs.append((ln, p))
    return True, rows, refs


def split_paths(cell: str) -> List[str]:
    cell = re.sub(r"<br\s*/?>", ",", cell)
    cell = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", r"\2", cell)
    out = []
    for part in re.split(r"[,、;\s]+", cell):
        p = part.strip().strip("`").strip()
        if not p or p in ("-", "—", "なし", "未実装", "N/A", "n/a"):
            continue
        p = re.sub(r"(#L?\d+(-L?\d+)?|:\d+(-\d+)?)$", "", p)
        if "://" in p:
            continue
        if "/" in p or re.search(r"\.[A-Za-z0-9]{1,6}$", p):
            out.append(p)
    return out


def catalog_req_rows(rows: List[CatalogRow]) -> Dict[str, CatalogRow]:
    out: Dict[str, CatalogRow] = {}
    for r in rows:
        m = REQ_ID_RE.search(catalog_cell(r, "要求ID"))
        if m:
            out.setdefault(m.group(1), r)
    return out


def catalog_cell(row: CatalogRow, *names: str) -> str:
    for k, v in row.cells.items():
        kn = k.replace(" ", "")
        if any(n.replace(" ", "") in kn for n in names):
            return v
    return ""


# --------------------------------------------------------------------------- ledger

def load_ledger(root: Path, cfg: dict) -> dict:
    data = read_json(root / mf(cfg, "ledger"), default=None)
    if data is None:
        data = {}
    data.setdefault("version", 1)
    data.setdefault("ac_digests", {})
    data.setdefault("cases", [])
    return data


def save_ledger(root: Path, cfg: dict, data: dict) -> None:
    write_json(root / mf(cfg, "ledger"), data)


# --------------------------------------------------------------------------- registry

def parse_registry_text(text: str) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for t in parse_tables(text.splitlines()):
        ic, sc = t.col("ID"), t.col("状態")
        if ic is None or sc is None:
            continue
        for ln, cells in t.rows:
            if ic < len(cells):
                rid = strip_md(cells[ic])
                if rid:
                    out[rid] = {"state": strip_md(cells[sc]) if sc < len(cells) else "", "line": str(ln)}
    return out


# --------------------------------------------------------------------------- /work run state

def work_dir(root: Path, cfg: dict) -> Path:
    return root / cfg["work"]["dir"]


def current_run(root: Path, cfg: dict) -> Optional[str]:
    p = work_dir(root, cfg) / "current-run.txt"
    if p.exists():
        rid = read_text(p).strip()
        return rid or None
    return None


def run_dir(root: Path, cfg: dict, run_id: str) -> Path:
    return work_dir(root, cfg) / "runs" / run_id


def load_meta(root: Path, cfg: dict, run_id: str) -> dict:
    return read_json(run_dir(root, cfg, run_id) / "meta.json", default={}) or {}


def save_meta(root: Path, cfg: dict, run_id: str, meta: dict) -> None:
    write_json(run_dir(root, cfg, run_id) / "meta.json", meta)


def load_queue(root: Path, cfg: dict, run_id: str) -> dict:
    q = read_json(run_dir(root, cfg, run_id) / "queue.json", default=None)
    return q or {"run_id": run_id, "items": []}


def conductor_root(root: Path, cfg: dict) -> Path:
    """Inside a worker worktree (<conductor>/work/worktrees/<x>) return the conductor tree."""
    parts = root.resolve().parts
    wd = cfg["work"]["dir"]
    for i in range(len(parts) - 2, 0, -1):
        if parts[i] == wd and i + 1 < len(parts) and parts[i + 1] == "worktrees":
            return Path(*parts[:i])
    return root


def parse_options_text(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*[:：]\s*(.*?)\s*$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def allows(value: Optional[str]) -> bool:
    """Interpret run_options values such as 'する' / '作業ブランチへ push する' / 'しない'."""
    if not value:
        return False
    v = value.strip()
    if re.search(r"しない|使わない|^no$|^false$|^off$|^なし$", v, re.I):
        return False
    return bool(re.search(r"する|使う|^yes$|^true$|^on$", v, re.I))
