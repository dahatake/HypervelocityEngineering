#!/usr/bin/env python3
"""gate.py - quality gates for Copilot hooks (plan §7.4 G-1..G-6, §8.3, R-23, R-25).

Configured in .github/hooks/quality-gates.json (Copilot CLI format; also loaded by the VS Code Copilot harness
and the GitHub Copilot app, which runs sessions on the Copilot CLI runtime).
Events (first argument):
  session-start   inject the active run-id so a new context resumes from state files
  pre-tool        deny forbidden edits / shell commands / external changes by MCP or plugin tools (G-1, G-2, G-3, G-5, G-6)
  subagent-start  remember which custom agent is running (preToolUse has no agent name)
  subagent-stop   G-4: run scripts/verify before implementer / test-designer / rd-author may finish
  agent-stop      do not let the conductor end its turn before the completion conditions hold
  user-prompt     detect `/build template`: deny tools other than reads and let the turn end after printing it
Also in pre-tool: while a run is active, every `task` call is logged to work/runs/<run-id>/models.jsonl (never denied).
Speed: pre-tool for built-in read-only tools (view, grep, glob, ...) answers before importing anything else,
because it runs thousands of times per run and none of the gates applies to them.
Reads the hook payload (camelCase or snake_case) from stdin; writes one JSON decision to stdout.
Fail-safe: unexpected internal errors allow the tool call (exit 0) and are logged to work/.ebak/gate.log,
except that a malformed payload for pre-tool is allowed as well, so a broken gate never bricks a session.
"""
from __future__ import annotations

import hashlib
import json
import sys

# Built-in tools that only read. Every gate allows them (they also match READ_TOOL_RX below, so `/build template`
# allows them too), so pre-tool answers without loading the configuration or calling git.
FAST_READ_TOOLS = {
    "view", "read", "grep", "glob", "read_file", "list_dir", "grep_search", "list_code_usages", "read_bash",
    "read_powershell", "list_bash", "list_powershell", "read_agent", "list_agents", "web_fetch", "web_search",
    "fetch", "fetch_webpage", "search", "web",
    # 状態を持たない・ローカルの記録だけのツール（どの gate も拒否しない）
    "report_intent", "sql", "session_store_sql", "store_memory", "update_todo", "todo", "manage_todo_list",
    "tool_search_tool", "ask_user", "show_file", "get_errors", "semantic_search", "file_search",
    "list_code_usages", "get_terminal_output", "get_task_output", "memory",
}
_RAW: "bytes | None" = None
if __name__ == "__main__" and sys.argv[1:2] == ["pre-tool"]:
    _RAW = sys.stdin.buffer.read() if not sys.stdin.isatty() else b""
    try:
        _d = json.loads(_RAW.decode("utf-8", "replace") or "{}")
        _t = str(_d.get("toolName") or _d.get("tool_name") or "") if isinstance(_d, dict) else ""
    except ValueError:
        _t = ""
    if _t.lower() in FAST_READ_TOOLS:
        sys.stdout.write("{}")
        sys.exit(0)

import os  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Iterable, List, Optional, Tuple  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ebaklib as h  # noqa: E402

WRITE_TOOL_RX = re.compile(r"edit|create|write|replace|patch|insert|delete|rename|move|notebook", re.I)
READ_TOOL_RX = re.compile(r"^(view|read|grep|glob|search|list|fetch|web)", re.I)
SHELL_TOOL_RX = re.compile(r"^(bash|powershell|shell|execute|run_in_terminal|terminal|runcommand|run_command)", re.I)
PATH_KEYS = ("path", "file_path", "filePath", "filepath", "target_file", "file", "uri", "paths", "files", "newPath", "oldPath")
STATE_TTL_SEC = 12 * 3600
# Built-in tools of Copilot CLI / VS Code (and Claude-style aliases). Every other tool comes from an MCP server,
# a plugin or an extension that the user configured, and may change an external system (check_external).
BUILTIN_TOOLS = {
    "view", "read", "create", "edit", "write", "multiedit", "notebookedit", "str_replace", "str_replace_editor",
    "insert", "apply_patch", "grep", "glob", "rg", "search", "ls", "bash", "powershell", "shell", "execute",
    "read_bash", "write_bash", "stop_bash", "list_bash", "read_powershell", "write_powershell", "stop_powershell",
    "list_powershell", "task", "agent", "read_agent", "write_agent", "list_agents", "skill", "web", "web_fetch",
    "web_search", "fetch", "ask_user", "report_intent", "sql", "session_store_sql", "store_memory", "update_todo",
    "todo", "task_complete", "exit_plan_mode", "tool_search_tool", "fetch_copilot_cli_documentation", "show_file",
    "create_file", "create_directory", "replace_string_in_file", "multi_replace_string_in_file",
    "insert_edit_into_file", "edit_files", "editfiles", "edit_notebook_file", "create_new_jupyter_notebook",
    "create_new_workspace", "read_file", "list_dir", "file_search", "grep_search", "semantic_search",
    "list_code_usages", "get_errors", "get_changed_files", "run_in_terminal", "get_terminal_output",
    "kill_terminal", "create_and_run_task", "run_task", "get_task_output", "run_vscode_command",
    "manage_todo_list", "runsubagent", "run_subagent", "runtests", "run_tests", "test_failure", "fetch_webpage",
    "open_simple_browser", "memory", "vscode_ask_questions", "ask_questions", "write_file", "edit_file",
    "delete_file", "move_file", "rename_file",
    # GitHub Copilot app (desktop): session tools that only change the local app state
    "rename_session", "send_session_message",
}
# `/build template` only prints the request template (skill build, step 0). While that turn runs, every tool except
# reads and these is denied, and agentStop lets the turn end even if a run is active.
TEMPLATE_PROMPT_RX = re.compile(r"^\s*/build(?:\s+|-)template\s*$", re.I)
TEMPLATE_ALLOWED_TOOLS = {"skill", "report_intent", "task_complete"}
TEMPLATE_TTL_SEC = 30 * 60
# GitHub Copilot app: renames the session's git branch. During a run it would orphan meta.json's integration_branch.
BRANCH_RENAME_TOOLS = {"rename_branch"}


def normalize_tool(name: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def has_verb(norm: str, verbs: Iterable[str]) -> Optional[str]:
    for v in verbs:
        if re.search(rf"(^|_){re.escape(normalize_tool(v))}(_|$)", norm):
            return v
    return None


BUILTIN_NORM = {normalize_tool(t) for t in BUILTIN_TOOLS}


# ---------------------------------------------------------------------- io helpers

def payload() -> dict:
    if _RAW is not None:
        raw = _RAW.decode("utf-8", "replace")
    else:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace") if not sys.stdin.isatty() else ""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def g(data: dict, *keys, default=None):
    for k in keys:
        if k in data and data[k] is not None:
            return data[k]
    return default


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=True))
    sys.stdout.flush()


def deny(reason: str, gate: str) -> None:
    msg = f"[{gate}] {reason}"
    emit({
        "permissionDecision": "deny",
        "permissionDecisionReason": msg,
        "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": msg},
    })


def run_is_fresh(meta: dict, minutes: int = 10) -> bool:
    """An unowned run is claimed only shortly after it started, so a session never takes over a long-running one."""
    try:
        started = datetime.fromisoformat(str(meta.get("started_at")))
        now = datetime.now(started.tzinfo) if started.tzinfo else datetime.now()
        return (now - started).total_seconds() <= minutes * 60
    except (TypeError, ValueError):
        return False


class Ctx:
    def __init__(self, data: dict, event: str = ""):
        self.data = data
        self.event = event
        cwd = g(data, "cwd", default=os.getcwd())
        self.cwd = Path(cwd).resolve()
        self.root = h.repo_root(self.cwd)
        cfg0 = h.load_config(self.root)
        self.croot = h.conductor_root(self.root, cfg0)
        self.cfg = h.load_config(self.croot)
        self.state_dir = h.work_dir(self.croot, self.cfg) / ".ebak"
        self.agent_id = ""
        self.parent_sid = ""
        self.resolve_agent_session()
        self.run_id = h.current_run(self.croot, self.cfg)
        self.meta = h.load_meta(self.croot, self.cfg, self.run_id) if self.run_id else {}
        self.run_active = bool(self.run_id and self.meta.get("status") == "active")
        if not self.run_active and (g(data, "toolName", "tool_name", default="") or self.sid or self.is_subagent_event):
            self.bind_sibling_run()
        self.foreign_run = self.run_of_other_session_on_primary()
        if self.foreign_run:
            self.run_active = False  # FR-1076: the run's gates do not apply to a chat that does not own the run
        self.land_pending: Optional[Tuple[Path, str, dict]] = None

    def run_of_other_session_on_primary(self) -> bool:
        """FR-1076: the active run lives in this (primary) tree and its owner session is a different, known session.
        Without a session id, or for the owner, or for an unowned run, the gates stay as they are."""
        if not (self.run_active and self.sid and not (self.croot / ".git").is_file()):
            return False
        owner = self.meta.get("session_id")
        return bool(owner and owner != self.sid)

    @property
    def is_subagent_event(self) -> bool:
        return self.event in ("subagent-start", "subagent-stop")

    @property
    def sid(self) -> str:
        """The owning (parent) session. A custom agent's own tool calls carry the agent id as sessionId; when
        subagentStart recorded that agent id with its real parent session, the parent is used instead."""
        return self.parent_sid or str(g(self.data, "sessionId", "session_id", default=""))

    def resolve_agent_session(self) -> None:
        raw = str(g(self.data, "sessionId", "session_id", default=""))
        if self.is_subagent_event:
            self.agent_id = str(g(self.data, "agentId", "agent_id", default=""))
            return
        if not raw:
            return
        dirs = [h.work_dir(self.root, self.cfg) / ".ebak", self.state_dir]
        try:
            if not (self.root / ".git").is_file():
                dirs += [h.work_dir(p, self.cfg) / ".ebak" for p in
                         sorted(self.root.parent.glob(f"{self.root.name}-run-*")) if (p / ".git").exists()]
        except OSError:
            pass
        now = time.time()
        for d in dirs:
            for a in h.read_json(d / "active-agents.json", default=[]) or []:
                if a.get("agent_id") == raw and a.get("parent") and a["parent"] != raw and now - a.get("t", 0) < STATE_TTL_SEC:
                    self.agent_id, self.parent_sid = raw, str(a["parent"])
                    return

    def pending_land(self) -> Optional[Tuple[Path, str, dict]]:
        """A finished run of this session whose integration branch is not in the base branch yet."""
        base = self.cfg.get("base_branch", "main")
        cands = self.sibling_runs() or ([self.root] if (self.root / ".git").is_file() else [])
        for p in cands:
            rid = h.current_run(p, self.cfg)
            runs = h.work_dir(p, self.cfg) / "runs"
            ids = [rid] if rid else sorted(x.name for x in runs.glob("*") if (x / "meta.json").exists())[-1:]
            for r in ids:
                meta = h.load_meta(p, self.cfg, r)
                owner = meta.get("session_id")
                if meta.get("status") != "finished" or meta.get("result") != "全件完了" or meta.get("landed_commit"):
                    continue
                if (owner and self.sid and owner != self.sid) or (not owner and self.sid and not self.cwd_in(p)):
                    continue
                br = meta.get("integration_branch")
                if br and h.ref_exists(self.root, f"refs/heads/{br}"):
                    rc, _ = h.git(["merge-base", "--is-ancestor", br, base], self.root)
                    if rc != 0:
                        return p, r, meta
        return None

    def cwd_in(self, tree: Path) -> bool:
        return os.path.normcase(str(self.cwd)).startswith(os.path.normcase(str(tree)))

    def sibling_runs(self) -> List[Path]:
        """Run worktrees (<repo>-run-<id>) that run-state.py start created next to the primary checkout."""
        # (also valid after the context was bound to a run worktree: the primary checkout stays self.root)
        if (self.root / ".git").is_file():
            return []
        try:
            return sorted(p for p in self.root.parent.glob(f"{self.root.name}-run-*") if (p / ".git").exists())
        except OSError:
            return []

    def sibling_owned_by_other(self, tree: Path) -> bool:
        """True when `tree` holds an active run owned by a different, known session (never touch it)."""
        rid = h.current_run(tree, self.cfg)
        meta = h.load_meta(tree, self.cfg, rid) if rid else {}
        owner = meta.get("session_id")
        return bool(rid and meta.get("status") == "active" and owner and self.sid and owner != self.sid)

    def sibling_authorized(self, tree: Path) -> bool:
        """Fail-closed: an active run may be written only with evidence this session owns it (session id == run owner);
        inactive/finished run worktrees stay writable."""
        rid = h.current_run(tree, self.cfg)
        meta = h.load_meta(tree, self.cfg, rid) if rid else {}
        if not (rid and meta.get("status") == "active"):
            return True
        return bool(self.sid and meta.get("session_id") == self.sid)

    def bind_to(self, tree: Path) -> bool:
        rid = h.current_run(tree, self.cfg)
        meta = h.load_meta(tree, self.cfg, rid) if rid else {}
        if not (rid and meta.get("status") == "active"):
            return False
        self.croot, self.run_id, self.meta, self.run_active = tree, rid, meta, True
        # agent/verify state belongs to the bound run's tree; sharing the primary's would mix up concurrent sessions
        self.state_dir = h.work_dir(tree, self.cfg) / ".ebak"
        return True

    def rebind_primary(self) -> None:
        self.croot = self.root
        self.state_dir = h.work_dir(self.croot, self.cfg) / ".ebak"
        self.run_id = h.current_run(self.croot, self.cfg)
        self.meta = h.load_meta(self.croot, self.cfg, self.run_id) if self.run_id else {}
        self.run_active = bool(self.run_id and self.meta.get("status") == "active")
        self.foreign_run = self.run_of_other_session_on_primary()
        if self.foreign_run:
            self.run_active = False

    def scan_siblings(self):
        """Active runs in the sibling worktrees, split into (owned by this session, unowned, owned by others)."""
        owned, free, others = [], [], []
        for p in self.sibling_runs():
            rid = h.current_run(p, self.cfg)
            meta = h.load_meta(p, self.cfg, rid) if rid else {}
            if not (rid and meta.get("status") == "active"):
                continue
            owner = meta.get("session_id")
            item = (meta.get("started_at", ""), p)
            if self.sid and owner == self.sid:
                owned.append(item)
            elif not owner:
                free.append(item)
            else:
                others.append(item)
        return owned, free, others

    def starts_a_run(self) -> bool:
        args = g(self.data, "toolArgs", "tool_input", default={})
        text = json.dumps(args, ensure_ascii=False) if not isinstance(args, str) else args
        return bool(START_CMD_RX.search(text.replace("\\\"", '"')))

    def foreign_claims(self) -> List[dict]:
        """Unconsumed start-claims of sessions other than this one (their start may still be about to create a run)."""
        now = time.time()
        f = h.start_claims_file(self.root, self.cfg)
        return [c for c in (h.read_json(f, default=[]) or [])
                if c.get("session") and c["session"] != self.sid and now - c.get("t", 0) < h.CLAIM_TTL_SEC]

    def bind_sibling_run(self) -> None:
        # The session works inside its run worktree while the hook runs in the primary checkout. Pick the run that
        # belongs to this session; never another session's run (several runs may be active at once).
        owned, free, others = self.scan_siblings()
        if owned:
            self.bind_to(max(owned)[1])
            return
        if self.is_subagent_event and not self.sid and not free and len(others) == 1:
            # a subagent hook may carry no session id; with exactly one active run it can only belong to that run
            self.bind_to(others[0][1])
            return
        if not free:
            return
        if self.starts_a_run():
            return  # this call starts its own run: it must not take over a run that is already there
        if not self.sid:
            if self.is_subagent_event and len(free) == 1:
                self.bind_to(free[0][1])  # nothing is recorded in meta; one unowned run can only be meant
            return  # no session evidence: never adopt a run (fail-closed, FR-1075 AC-410)
        # FR-1075 AC-408/409: a run whose owner a start-claim fixed is never rebound. An unowned run is rescued only when
        # it is the single candidate, no other session still has an unconsumed claim, and the meta is written under
        # the same lock that start uses.
        try:
            with h.start_claims_lock(self.root, self.cfg):
                owned, free, others = self.scan_siblings()
                if owned:
                    self.bind_to(max(owned)[1])
                    return
                if len(free) != 1:
                    self.log(f"UNBOUND-RUN session={self.sid} free_runs={len(free)} 候補が一意でないので束縛しません")
                    return
                p = free[0][1]
                rid = h.current_run(p, self.cfg)
                meta = h.load_meta(p, self.cfg, rid) if rid else {}
                if not run_is_fresh(meta):
                    self.log(f"UNBOUND-RUN session={self.sid} free_runs=1 開始から時間が経った所有者なし run は束縛しません")
                    return
                if self.foreign_claims():
                    self.log(f"UNBOUND-RUN session={self.sid} 他の session の未消費の start-claim があるので束縛しません")
                    return
                meta["session_id"] = self.sid
                h.save_meta(p, self.cfg, rid, meta)
                self.bind_to(p)
        except h.LockBusy as e:
            self.log(f"UNBOUND-RUN session={self.sid} {e}")

    def log(self, line: str) -> None:
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            with open(self.state_dir / "gate.log", "a", encoding="utf-8") as fh:
                fh.write(f"{h.now_iso()} {line}\n")
        except OSError:
            pass

    # active custom agents (subagentStart / subagentStop)
    def agents_path(self) -> Path:
        return self.state_dir / "active-agents.json"

    def own_agents(self) -> List[dict]:
        data = h.read_json(self.agents_path(), default=[]) or []
        now = time.time()
        return [a for a in data if now - a.get("t", 0) < STATE_TTL_SEC]

    def other_agent_files(self) -> List[Path]:
        """active-agents.json of the primary checkout and every run worktree except the bound one."""
        roots = [self.root] + ([] if (self.root / ".git").is_file() else self.sibling_runs())
        out: List[Path] = []
        for r in roots:
            f = h.work_dir(r, self.cfg) / ".ebak" / "active-agents.json"
            if f != self.agents_path() and f.exists():
                out.append(f)
        return out

    def foreign_agents(self) -> List[Tuple[Path, dict]]:
        """Agents this session started that subagentStart recorded in another tree (a concurrent run may have been
        bound at that moment). Only entries tagged with this session id count; never another session's agents."""
        if not self.sid:
            return []
        now = time.time()
        return [(f, a) for f in self.other_agent_files() for a in (h.read_json(f, default=[]) or [])
                if a.get("session") == self.sid and now - a.get("t", 0) < STATE_TTL_SEC]

    def active_agents(self) -> List[dict]:
        return self.own_agents() + [a for _, a in self.foreign_agents()]

    def active_names(self) -> List[str]:
        """Roles whose gates apply to this tool call. When the caller is identifiable (agent name in the payload, or
        its agent id recorded by subagentStart) only its own role counts, so a test-designer running next to an
        implementer is not gated as an implementer. Unidentifiable callers stay fail-closed (all active roles)."""
        agents = self.active_agents()
        if self.agent_id:
            mine = [a.get("name", "") for a in agents if a.get("agent_id") == self.agent_id]
            if mine:
                return mine
        known = {a.get("name", "") for a in agents}
        own = agent_name(self)
        if own and own in known and not self.is_subagent_event:
            return [own]
        return [a.get("name", "") for a in agents]

    def save_agents(self, agents: List[dict]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        h.write_json(self.agents_path(), agents)

    def option(self, key: str) -> str:
        return str(self.meta.get("options", {}).get(key, ""))


# ---------------------------------------------------------------------- path helpers

def collect_paths(args) -> List[str]:
    out: List[str] = []

    def walk(v, key=None):
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, k)
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        elif isinstance(v, str):
            if key in PATH_KEYS:
                out.append(v)
            if key in ("input", "patch", "diff") or v.startswith("*** Begin Patch"):
                out.extend(re.findall(r"^\*\*\* (?:Add|Update|Delete) File:\s*(.+?)\s*$", v, re.M))
                out.extend(re.findall(r"^\*\*\* Move to:\s*(.+?)\s*$", v, re.M))
    walk(args)
    return [p for p in out if p]


def classify(ctx: Ctx, p: str) -> Tuple[Optional[str], bool, Path]:
    """Return (repo-relative path inside the conductor tree or worker worktree, in_worker, absolute path)."""
    if p.startswith("file://"):
        p = re.sub(r"^file:///?", "", p)
        if re.match(r"^[A-Za-z]%3A", p):
            p = p.replace("%3A", ":", 1)
    ap = Path(p)
    if not ap.is_absolute():
        ap = ctx.cwd / ap
    ap = Path(os.path.normpath(str(ap)))
    nap = os.path.normcase(str(ap))
    in_sibling = False
    for sib in ctx.sibling_runs():
        if nap.startswith(os.path.normcase(str(sib)) + os.sep):
            in_sibling = True
            if sib != ctx.croot:
                if ctx.sibling_owned_by_other(sib) or not ctx.sibling_authorized(sib):
                    return None, False, ap  # another session's (or an unproven) run is outside this session's scope (G-5)
                if not ctx.bind_to(sib):
                    ctx.croot = sib  # an inactive run worktree of this repository is still not "outside"
            break
    if not in_sibling and ctx.croot != ctx.root and nap.startswith(os.path.normcase(str(ctx.root)) + os.sep):
        # a sibling run was auto-bound, but this write targets the primary tree the session is in
        ctx.rebind_primary()
    try:
        rel = ap.resolve().relative_to(ctx.croot.resolve()).as_posix() if ap.exists() else ap.relative_to(ctx.croot).as_posix()
    except ValueError:
        try:
            rel = Path(os.path.normcase(str(ap))).relative_to(Path(os.path.normcase(str(ctx.croot)))).as_posix()
        except ValueError:
            return None, False, ap
    wd = ctx.cfg["work"]["dir"]
    m = re.match(rf"^{re.escape(wd)}/worktrees/[^/]+/(.*)$", rel)
    if m:
        return m.group(1), True, ap
    return rel, False, ap


def allowed_outside(ap: Path) -> bool:
    s = os.path.normcase(str(ap))
    homes = [Path.home() / ".copilot", Path.home() / ".vscode", Path(tempfile.gettempdir())]
    if os.environ.get("COPILOT_HOME"):
        homes.append(Path(os.environ["COPILOT_HOME"]))
    return any(s.startswith(os.path.normcase(str(x))) for x in homes)


def is_work_branch(ctx: Ctx) -> bool:
    return bool(re.match(r"^work/[^/]+/[^/]+$", h.current_branch(ctx.root)))


def req_paths(ctx: Ctx) -> Tuple[str, str]:
    return h.mf(ctx.cfg, "requirements"), h.mf(ctx.cfg, "requirements_dir").rstrip("/") + "/"


# ---------------------------------------------------------------------- pre-tool

def check_write(ctx: Ctx, rel: Optional[str], in_worker: bool, ap: Path) -> Optional[Tuple[str, str]]:
    wd = ctx.cfg["work"]["dir"]
    if rel is None:
        if allowed_outside(ap):
            return None
        return ("G-5", f"作業ディレクトリ外への書き込みは禁止です: {ap}")
    names = ctx.active_names()
    worker = in_worker or is_work_branch(ctx)
    req_file, req_dir = req_paths(ctx)
    temp_rx = re.compile(ctx.cfg["checks"]["temp_file_pattern"])
    if not rel.startswith(wd + "/") and temp_rx.search(rel):
        return ("G-6", f"ログ・証跡・実行結果などの一時ファイルは /{wd}/runs/<run-id>/ に書きます（{rel}）")
    if rel.startswith(wd + "/") and not in_worker:
        return None
    if rel.startswith(".github/hooks/") or rel.startswith("scripts/hooks/"):
        if (ctx.run_active or worker) and not ctx.cfg["gates"].get("allow_hook_edit", False):
            return ("G-5", "実行中はゲート（hooks）を変更できません（hooks 自体を保守するリポジトリーは "
                           "scripts/ebak.config.json の gates.allow_hook_edit を true にします）")
    if rel == h.mf(ctx.cfg, "id_registry"):
        return ("G-3", "ID 台帳は直接編集しません。ID は `python scripts/next-id.py <種別>` で採番します")
    if rel == req_file or rel.startswith(req_dir):
        if worker:
            return ("G-1", "作業役（worktree）は要求定義書を変更できません。要求の誤りや不足は結果の『競合』に書き、conductor が rd-author に回します")
        if ctx.run_active and "rd-author" not in names:
            return ("G-1", "要求定義書を編集できるのは rd-author だけです（conductor は rd-author に依頼します）")
        return None
    if rel == h.mf(ctx.cfg, "ledger"):
        return ("G-2", "台帳は直接編集しません。`python scripts/ledger.py add|update|block|set|run|digests` を使います")
    if rel.startswith("tests/system/"):
        if worker or any(n in ("implementer", "reviewer") for n in names):
            return ("G-2", "System Test（tests/system/）は implementer・reviewer からは変更できません。テストと要求の食い違いは『競合』として報告します")
    if names and not in_worker:
        only = set(names)
        if only <= {"rd-auditor", "reviewer"}:
            return ("G-5", f"{'・'.join(sorted(only))} は読み取り専用の役割です。結果は /{wd}/runs/<run-id>/ に書きます")
        if only == {"test-designer"} and not rel.startswith("tests/system/"):
            return ("G-5", "test-designer が編集できるのは tests/system/ だけです（台帳は scripts/ledger.py で更新します）")
        if only == {"rd-author"} and (not rel.startswith("docs/") or rel == h.mf(ctx.cfg, "run_history")):
            return ("G-5", f"rd-author が編集できるのは docs/ の管理データだけです（{h.mf(ctx.cfg, 'run_history')} を除く）")
    if rel.startswith("tests/system/"):
        return None
    if (ctx.run_active and not names and not worker
            and ctx.cfg["gates"].get("enforce_conductor_edit_scope", True)
            and rel != h.mf(ctx.cfg, "run_history")):
        return ("G-5", f"conductor が編集できるのは /{wd}/ と {h.mf(ctx.cfg, 'run_history')} だけです。作業は作業役に委譲します"
                       "（subagent の検出に問題がある場合は scripts/ebak.config.json の gates.enforce_conductor_edit_scope を false にします）")
    return None


_PATH_ARG = r"""("[^"]+"|'[^']+'|[^\s"';&|]+)"""
CD_RX = re.compile(rf"^\s*(?:cd|chdir|pushd|set-location|sl)\s+(?:/d\s+)?(?:-(?:path|literalpath)\s+)?{_PATH_ARG}\s*$", re.I)
GIT_WRITE_RX = re.compile(rf"\bgit\s+(?:(?:-C\s+{_PATH_ARG}|-c\s+\S+|--no-pager)\s+)*(?:commit|merge|cherry-pick|am)\b")
GIT_C_RX = re.compile(rf"\bgit\b[^;&|]*?\s-C\s+{_PATH_ARG}")


def _resolve_dir(base: Path, raw: str) -> Optional[Path]:
    raw = raw.strip().strip("\"'")
    if not raw or "$" in raw or "`" in raw or "%" in raw:
        return None  # a variable: the target cannot be known from the command line
    p = Path(raw).expanduser()
    return Path(os.path.normpath(str(p if p.is_absolute() else base / p)))


def commit_target_branch(ctx: Ctx, seg: str, shell_cwd: Path) -> str:
    """Branch a `git commit|merge...` segment acts on: the tree named by `git -C <path>`, else the tree the shell is in
    (the hook's cwd, or the directory an earlier `cd <path>` moved to)."""
    m = GIT_C_RX.search(seg)
    tree = _resolve_dir(shell_cwd, m.group(1)) if m else shell_cwd
    if tree is None:
        tree = shell_cwd
    return h.current_branch(h.repo_root(tree))


def check_shell(ctx: Ctx, cmd: str) -> Optional[Tuple[str, str]]:
    c = " ".join(cmd.split())
    base = ctx.cfg.get("base_branch", "main")
    names = ctx.active_names()
    worker = is_work_branch(ctx) or bool(re.search(r"[/\\]worktrees[/\\]", c) and "cd " in c)
    wd = ctx.cfg["work"]["dir"]
    shell_cwd = ctx.cwd
    for seg in re.split(r"&&|\|\||;|\n", cmd):
        s = " ".join(seg.split())
        mcd = CD_RX.match(seg)
        if mcd:
            shell_cwd = _resolve_dir(shell_cwd, mcd.group(1)) or shell_cwd
            continue
        if re.search(r"\bgit\b.*\bpush\b", s):
            if re.search(r"(\s--force\b|\s-f\b|--force-with-lease|--mirror|\s--delete\b|\s-d\b|\s\+\S)", s):
                return ("G-5", "force push・ブランチの削除の push は禁止です")
            if re.search(rf"(\s|:)(refs/heads/)?({re.escape(base)}|master)(\s|$)", s) or (
                    h.current_branch(ctx.root) in (base, "master") and not re.search(r"\bpush\s+\S+\s+\S+", s)):
                return ("G-5", f"{base} への push は禁止です。作業ブランチへ push し、PR で取り込みます")
            if (ctx.run_active or worker) and not h.allows(ctx.option("git_push")):
                return ("G-5", "run_options の git_push が「しない」なので push しません")
        if re.search(r"\bgit\s+(filter-branch|filter-repo)\b", s):
            return ("G-5", "履歴を書き換える git 操作は禁止です")
        if ctx.run_active and GIT_WRITE_RX.search(s) and commit_target_branch(ctx, s, shell_cwd) in (base, "master"):
            return ("G-5", f"実行中は {base} に直接 commit・merge しません。統合ブランチで作業します")
    if ctx.run_active or worker:
        for pat in ctx.cfg["gates"].get("deploy_patterns", []):
            if re.search(pat, c, re.I) and not h.allows(ctx.option("deploy")):
                return ("G-5", "run_options の deploy が「しない」なのでデプロイ・公開の操作はしません")
    if re.search(rf"\b(rm|rmdir|del|erase|Remove-Item)\s[^;&|]*(^|[\s'\"/\\.]){re.escape(wd)}([/\\]|\s|$|['\"])", c, re.I) \
            and "clean-work.py" not in c:
        return ("G-6", f"/{wd} の削除は scripts/clean-work.py と `git worktree remove` だけで行います")
    if worker or any(n in ("implementer", "reviewer") for n in names):
        if re.search(r"(\b(rm|del|Remove-Item|git\s+rm|git\s+mv|mv|move|Move-Item|Set-Content|Add-Content|Out-File|tee|sed\s+-i|perl\s+-pi)\b[^;&|]*|>{1,2}\s*)['\"]?(\./)?tests[/\\]system", c, re.I):
            return ("G-2", "System Test（tests/system/）は implementer・reviewer からは変更できません")
        if re.search(r"\bledger\.py\b.*\b(add|update|block|digests|set)\b", c) or re.search(r"\bledger\.py\b.*\brepair\b.*--apply\b", c):
            return ("G-2", "作業役は台帳を更新しません（`ledger.py run --no-record` で実行だけ行います）")
    if re.search(r"\brdfix\.py\b.*--apply\b", c):
        m = re.search(r"--only[=\s]+['\"]?([A-Za-z,]+)", c)
        only = {x for x in (m.group(1).split(",") if m else []) if x} or {"registry", "catalog", "ledger", "gitignore", "history"}
        if worker or any(n in ("implementer", "reviewer", "rd-auditor") for n in names):
            return ("G-2", "作業役・読み取り専用の役割はデータ層を自動修正しません（`rdfix.py` は確認だけ。--apply は conductor が統合ブランチで実行します）")
        allowed = {"rd-author": {"registry", "catalog"}, "test-designer": {"ledger"}}
        for n in names:
            if n in allowed and not only <= allowed[n]:
                return ("G-5", f"{n} が rdfix.py --apply で直せるのは {','.join(sorted(allowed[n]))} だけです（--only で絞ります）")
    if re.search(r"(\b(Set-Content|Add-Content|Out-File|tee|sed\s+-i|perl\s+-pi)\b[^;&|]*|>{1,2}\s*)['\"]?(\./)?docs[/\\]requirements", c, re.I):
        if worker or (ctx.run_active and "rd-author" not in names):
            return ("G-1", "要求定義書を編集できるのは rd-author だけです")
    if re.search(r"(\b(Set-Content|Add-Content|Out-File|tee|sed\s+-i)\b[^;&|]*|>{1,2}\s*)['\"]?(\./)?docs[/\\]id-registry", c, re.I):
        return ("G-3", "ID 台帳は直接編集しません。scripts/next-id.py を使います")
    return None


def check_external(ctx: Ctx, tool: str) -> Optional[Tuple[str, str]]:
    """G-5: changes to external systems through MCP servers / plugins / extensions configured by the user."""
    norm = normalize_tool(tool)
    if norm in BRANCH_RENAME_TOOLS:
        if ctx.run_active or is_work_branch(ctx):
            return ("G-5", "実行中は git のブランチ名を変更しません（統合ブランチは meta.json の integration_branch に記録済みです）。"
                           "ブランチ名を変えたい場合は、run の開始前か終了後に行います")
        return None
    if not norm or norm in BUILTIN_NORM or SHELL_TOOL_RX.match(tool):
        return None
    gates = ctx.cfg["gates"]
    if any(re.search(p, tool, re.I) for p in gates.get("external_tool_allow", [])):
        return None
    deploy_verb = has_verb(norm, gates.get("external_deploy_verbs", []))
    verb = deploy_verb or has_verb(norm, gates.get("external_write_verbs", []))
    if not verb:
        return None
    names = ctx.active_names()
    wd = ctx.cfg["work"]["dir"]
    if names and set(names) <= {"rd-auditor", "reviewer"}:
        return ("G-5", f"{'・'.join(sorted(set(names)))} は読み取り専用の役割なので、外部のツールでの変更（{tool}）はしません。"
                       f"結果は /{wd}/runs/<run-id>/ に書きます")
    if not (ctx.run_active or is_work_branch(ctx)):
        return None
    if deploy_verb and not h.allows(ctx.option("deploy")):
        return ("G-5", f"run_options の deploy が「しない」なので、外部のツールでのデプロイ・公開（{tool}）はしません")
    if not deploy_verb and not h.allows(ctx.option("external_write")):
        return ("G-5", f"run_options の external_write が「しない」なので、外部のツールでの変更（{tool}）はしません。"
                       "参照（検索・取得）だけ行い、変更が必要なら報告に書きます")
    return None


# ---------------------------------------------------------------------- model log (no enforcement)

SUBAGENT_TOOLS = {"task"}
AGENT_KEYS = ("agent_type", "agentType", "subagent_type", "agentName", "agent_name")


def check_model(ctx: Ctx, tool: str, args) -> Optional[Tuple[str, str]]:
    """Log `task` calls to models.jsonl. The model is chosen by the harness (e.g. Copilot Fusion); never denied."""
    if normalize_tool(tool) not in SUBAGENT_TOOLS or not ctx.run_active or not isinstance(args, dict):
        return None
    agent = str(g(args, *AGENT_KEYS, default="")).strip()
    got = str(args.get("model") or "").strip()
    try:
        rdir = h.run_dir(ctx.croot, ctx.cfg, ctx.run_id)
        with open(rdir / "models.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": h.now_iso(), "agent": agent, "model": got or "(既定)"}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return None


# ---------------------------------------------------------------------- /build template

def session_id(ctx: Ctx) -> str:
    return str(g(ctx.data, "sessionId", "session_id", default=""))


def template_path(ctx: Ctx) -> Path:
    """FR-1077: one state file per session (an input without a session id uses the anonymous file)."""
    sid = session_id(ctx)
    if not sid:
        return ctx.state_dir / "template-request.json"
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", sid)[:60]
    return ctx.state_dir / f"template-request-{safe}-{hashlib.sha1(sid.encode('utf-8')).hexdigest()[:8]}.json"


def template_active(ctx: Ctx) -> bool:
    """True while the current turn answers `/build template` (show the request template only)."""
    # an input without a session id cannot tell whose turn it is: it is restricted while any session's turn is active
    files = [template_path(ctx)] if session_id(ctx) else sorted(ctx.state_dir.glob("template-request*.json"))
    for f in files:
        st = h.read_json(f, default=None)
        if isinstance(st, dict) and time.time() - float(st.get("t", 0)) <= TEMPLATE_TTL_SEC:
            return True
    return False


def clear_template(ctx: Ctx) -> None:
    try:
        template_path(ctx).unlink()
    except (FileNotFoundError, OSError):
        pass


def on_user_prompt(ctx: Ctx) -> None:
    prompt = str(g(ctx.data, "prompt", default=""))
    if TEMPLATE_PROMPT_RX.match(prompt):
        ctx.state_dir.mkdir(parents=True, exist_ok=True)
        h.write_json(template_path(ctx), {"session": session_id(ctx), "t": time.time()})
        ctx.log("TEMPLATE requested")
    else:
        clear_template(ctx)
    emit({})


START_CMD_RX = re.compile(r"run-state\.py['\"]?\s+start\b(?!.*--help)")


def record_start_claim(ctx: Ctx, cmd: str) -> Optional[str]:
    """The session that runs `run-state.py start` owns the run it creates. Hooks see the session id only on the
    tool call, so remember it here and let run-state.py read it; otherwise the first other session without a run
    claims the new run (R-2) and the real owner is then refused (G-1/G-5) in its own run."""
    if not (ctx.sid and START_CMD_RX.search(cmd)):
        return None
    ident = h.start_ident_from_command(cmd)
    try:
        f = h.start_claims_file(ctx.root, ctx.cfg)
        with h.start_claims_lock(ctx.root, ctx.cfg):
            now = time.time()
            claims = [c for c in (h.read_json(f, default=[]) or []) if now - c.get("t", 0) < h.CLAIM_TTL_SEC]
            claims.append({"session": ctx.sid, "t": now, "ident": ident})
            f.parent.mkdir(parents=True, exist_ok=True)
            h.write_json(f, claims)
        ctx.log(f"START-CLAIM session={ctx.sid} ident={ident}")
    except h.LockBusy as e:
        ctx.log(f"START-CLAIM-FAILED session={ctx.sid} {e}")
        return f"start-claim を記録できませんでした（claim・meta は書いていません）: {e}。残留ロックでなければ少し待ってもう一度実行します"
    except OSError as e:
        ctx.log(f"START-CLAIM-FAILED session={ctx.sid} {e}")
        return f"start-claim を記録できませんでした（claim・meta は書いていません）: {e}"
    return None


def on_pre_tool(ctx: Ctx) -> None:
    if ctx.run_active:
        h.touch_heartbeat(ctx.croot, ctx.cfg, ctx.run_id)
    tool = str(g(ctx.data, "toolName", "tool_name", default=""))
    if template_active(ctx) and not (READ_TOOL_RX.match(tool) or normalize_tool(tool) in TEMPLATE_ALLOWED_TOOLS):
        ctx.log(f"DENY TEMPLATE {tool}")
        deny("`/build template` は雛形を表示するだけです。ファイルの書き込み・コマンド・作業役の呼び出し・conductor の手順は行いません。"
             "skill `build` の「雛形（既定値）」のコードブロックをそのまま出力して、このターンを終えてください", "TEMPLATE")
        return
    args = g(ctx.data, "toolArgs", "tool_input", default={})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {"command": args} if SHELL_TOOL_RX.match(tool) else {"input": args}
    res = check_model(ctx, tool, args) or check_external(ctx, tool)
    if res:
        ctx.log(f"DENY {res[0]} {tool}")
        deny(res[1], res[0])
        return
    if SHELL_TOOL_RX.match(tool):
        cmd = ""
        if isinstance(args, dict):
            cmd = str(g(args, "command", "script", "cmd", "input", default=""))
        res = check_shell(ctx, cmd)
        if res:
            ctx.log(f"DENY {res[0]} {tool}: {cmd[:200]}")
            deny(res[1], res[0])
        else:
            failed = record_start_claim(ctx, cmd)
            if failed:
                deny(failed, "G-5")
        return
    if READ_TOOL_RX.match(tool) or not WRITE_TOOL_RX.search(tool):
        return
    for p in collect_paths(args):
        rel, in_worker, ap = classify(ctx, p)
        res = check_write(ctx, rel, in_worker, ap)
        if res:
            ctx.log(f"DENY {res[0]} {tool}: {p}")
            deny(res[1], res[0])
            return


# ---------------------------------------------------------------------- subagents

def agent_name(ctx: Ctx) -> str:
    return str(g(ctx.data, "agentName", "agent_name", "agent_type", "agentType", default="")).strip()


def on_subagent_start(ctx: Ctx) -> None:
    name = agent_name(ctx)
    if not name:
        return
    agents = ctx.own_agents()
    entry = {"name": name, "t": time.time()}
    if ctx.sid:
        entry["session"] = ctx.sid
    aid = str(g(ctx.data, "agentId", "agent_id", default=""))
    parent = str(g(ctx.data, "parentAgentId", "parent_agent_id", default="")) or ctx.sid
    if aid and parent and aid != parent:
        entry.update({"agent_id": aid, "parent": parent})  # the agent's own tool calls carry sessionId = agent id
    agents.append(entry)
    ctx.save_agents(agents)
    ctx.log(f"START {name}")
    emit({})


def release_agent(ctx: Ctx, name: str, agent_id: str = "") -> None:
    """Remove the stopping agent's own record. Parallel agents share a name (implementer ×N), so the agent id
    decides; releasing "the first one with this name" dropped another running agent's session mapping, which made
    its edits look like writes from an unknown session (spurious G-5)."""
    def mine(a: dict) -> bool:
        if agent_id and any(x.get("agent_id") == agent_id for x in (agents + [y for _, y in ctx.foreign_agents()])):
            return a.get("agent_id") == agent_id
        return a.get("name") == name

    agents = ctx.own_agents()
    found = any(mine(a) for a in agents)
    if not found:
        for f, a in ctx.foreign_agents():
            if mine(a):
                rest = [x for x in (h.read_json(f, default=[]) or []) if x != a]
                h.write_json(f, rest)
                break
    for i, a in enumerate(agents):
        if mine(a):
            if ctx.run_active and a.get("t"):
                try:  # 作業役ごとの所要時間（KPI・時間の内訳用）
                    rdir = h.run_dir(ctx.croot, ctx.cfg, ctx.run_id)
                    with open(rdir / "subagents.jsonl", "a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"at": h.now_iso(), "agent": name, "seconds": round(time.time() - a["t"])}, ensure_ascii=False) + "\n")
                except OSError:
                    pass
            del agents[i]
            break
    ctx.save_agents(agents)


def on_subagent_stop(ctx: Ctx) -> None:
    name = agent_name(ctx)
    gates = ctx.cfg["gates"]
    verify_map = gates.get("subagent_verify", {})
    if name not in verify_map:
        release_agent(ctx, name, ctx.agent_id)
        ctx.log(f"STOP {name}")
        emit({})
        return
    response = str(g(ctx.data, "response", "last_assistant_message", default=""))
    m = re.search(r"^\s*WORKTREE:\s*(.+?)\s*$", response, re.M)
    target = ctx.croot
    if m:
        cand = Path(m.group(1).strip().strip("`"))
        if not cand.is_absolute():
            cand = ctx.croot / cand
        if (cand / "scripts" / "verify.py").exists():
            target = cand
    rc, out = h.run([sys.executable, str(target / "scripts" / "verify.py"), *verify_map[name]], cwd=target, timeout=840)
    tail = "\n".join(l for l in out.splitlines() if l.startswith(("FAIL", "  ", "verify:")))[:3000]
    if rc == 0:
        release_agent(ctx, name, ctx.agent_id)
        ctx.log(f"STOP {name} verify=PASS")
        emit({})
        return
    key = str(g(ctx.data, "agentId", "agent_id", default=name))
    counts = h.read_json(ctx.state_dir / "verify-blocks.json", default={}) or {}
    n = counts.get(key, 0) + 1
    counts[key] = n
    ctx.state_dir.mkdir(parents=True, exist_ok=True)
    h.write_json(ctx.state_dir / "verify-blocks.json", counts)
    limit = int(gates.get("subagent_verify_max_blocks", 3))
    if n <= limit:
        ctx.log(f"BLOCK G-4 {name} ({n}/{limit})")
        emit({"decision": "block", "reason": (
            f"[G-4] 終了前の検証（scripts/verify {' '.join(verify_map[name])}）が失敗しています（{n}/{limit} 回目）。"
            f"原因を直して再実行し、exit 0 にしてから終了してください。テストの削除・弱体化・スキップは禁止です。\n{tail}")})
        return
    release_agent(ctx, name, ctx.agent_id)
    ctx.log(f"GIVEUP G-4 {name}")
    emit({"modifiedResponse": f"GATE G-4: verify が失敗したまま終了しました（{limit} 回差し戻し済み）。conductor はこの結果を統合しません。\n{tail}\n\n{response}"})


# ---------------------------------------------------------------------- session / agent stop

def on_session_start(ctx: Ctx) -> None:
    source = str(g(ctx.data, "source", default=""))
    if source in ("startup", "new"):
        try:
            ctx.agents_path().unlink()
        except (FileNotFoundError, OSError):
            pass
    if ctx.run_active:
        emit({"additionalContext": (
            f"実行中の conductor の run があります: {ctx.run_id}（工程 {ctx.meta.get('stage')}）。"
            "conductor として続ける場合は、最初に `python scripts/run-state.py status` を実行し、未完了の工程から再開します。")})
    else:
        emit({})


def land_fingerprint(ctx: Ctx, tree: Path, meta: dict) -> str:
    """State that decides whether `run-state.py land` can make progress: the base and integration branch commits and
    the dirty files of the primary checkout (read-only git calls; nothing is committed, stashed or changed)."""
    base = ctx.cfg.get("base_branch", "main")
    try:
        primary = h.load_script("run-state").primary_tree(ctx.root)
    except Exception:
        primary = ctx.root
    parts = [h.git(["rev-parse", base], primary)[1].strip(),
             h.git(["rev-parse", str(meta.get("integration_branch") or "HEAD")], tree)[1].strip(),
             h.git(["status", "--porcelain"], primary)[1]]
    return hashlib.sha1("\n".join(parts).encode("utf-8", "replace")).hexdigest()


def on_agent_stop(ctx: Ctx) -> None:
    if template_active(ctx):
        clear_template(ctx)
        ctx.log("AGENT-STOP allowed (template)")
        emit({})
        return
    if not ctx.run_active:
        pend = ctx.pending_land()
        if pend:
            tree, rid, pmeta = pend
            fp = land_fingerprint(ctx, tree, pmeta)
            if pmeta.get("land_fp") == fp:
                # same blocker, nothing changed since the last stop: do not repeat the same push-back (AC-448)
                first = not pmeta.get("land_notified")
                pmeta["land_notified"] = True
                h.save_meta(tree, ctx.cfg, rid, pmeta)
                ctx.log(f"AGENT-STOP allowed (land {rid} waiting, same blocker)")
                if first:
                    emit({"systemMessage": (
                        f"run {rid} は全件完了ですが main への取り込みが止まっています（取り込み待ち）。run・統合ブランチ・worktree は保持しています。"
                        f"主の作業ツリーの未コミット変更を利用者が commit か退避したあと、`{tree}` を cwd にして "
                        "`python scripts/run-state.py land` を実行してください。")})
                else:
                    emit({})
                return
            pmeta["land_fp"], pmeta["land_notified"] = fp, False
            n = int(pmeta.get("land_blocks", 0)) + 1
            pmeta["land_blocks"] = n
            h.save_meta(tree, ctx.cfg, rid, pmeta)
            limit = int(ctx.cfg["gates"].get("agent_stop_max_blocks", 40))
            if n <= limit:
                ctx.log(f"AGENT-STOP blocked (land {rid} {n}/{limit})")
                emit({"decision": "block", "reason": (
                    f"run {rid} は全件完了ですが、main への取り込みが終わっていません。`{tree}` を cwd にして "
                    "`python scripts/run-state.py land` を実行してください（0 で終わり。2 は競合: run の worktree で main を merge して解消し、"
                    "verify の後にもう一度実行。3 は主の作業ツリーが未整備: 待ってから再実行）。利用者は途中で応答しません。")})
                return
        emit({})
        return
    sid = ctx.sid
    meta = ctx.meta
    if not meta.get("session_id") and sid:
        meta["session_id"] = sid
    if sid and meta.get("session_id") and meta["session_id"] != sid:
        emit({})
        return
    rs = h.load_script("run-state")
    reasons = rs.completion(ctx.croot, ctx.cfg, ctx.run_id)
    if not reasons:
        h.save_meta(ctx.croot, ctx.cfg, ctx.run_id, meta)
        emit({})
        return
    mh = h.effective_max_hours(meta.get("options"), ctx.cfg)
    over = rs.elapsed_hours(meta) > mh + 0.25
    n = int(meta.get("stop_blocks", 0)) + 1
    limit = int(ctx.cfg["gates"].get("agent_stop_max_blocks", 40))
    if over or n > limit:
        meta["stop_blocks"] = n
        h.save_meta(ctx.croot, ctx.cfg, ctx.run_id, meta)
        ctx.log(f"AGENT-STOP allowed (over={over} blocks={n})")
        emit({})
        return
    meta["stop_blocks"] = n
    h.save_meta(ctx.croot, ctx.cfg, ctx.run_id, meta)
    ctx.log(f"AGENT-STOP blocked ({n}/{limit}): {' / '.join(reasons)}")
    emit({"decision": "block", "reason": (
        "conductor の完了条件（§8.3）を満たしていません: " + " / ".join(reasons) +
        "。利用者は途中で応答しません。`python scripts/run-state.py status` で状態を確認し、未完了の工程から続けてください。"
        "時間予算の 85% を過ぎていれば、新しい項目を始めずに工程 6（最終）に進みます。")})


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    data = payload()
    try:
        ctx = Ctx(data, event)
        if not ctx.cfg["gates"].get("enabled", True):
            emit({})
            return 0
        {"pre-tool": on_pre_tool, "subagent-start": on_subagent_start, "subagent-stop": on_subagent_stop,
         "session-start": on_session_start, "agent-stop": on_agent_stop,
         "user-prompt": on_user_prompt}.get(event, lambda c: emit({}))(ctx)
    except Exception:  # never brick a session because of a gate bug
        try:
            d = Path(os.getcwd()) / "work" / ".ebak"
            d.mkdir(parents=True, exist_ok=True)
            with open(d / "gate.log", "a", encoding="utf-8") as fh:
                fh.write(f"{h.now_iso()} ERROR {event}: {traceback.format_exc()}\n")
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
