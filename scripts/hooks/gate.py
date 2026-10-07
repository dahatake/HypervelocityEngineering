#!/usr/bin/env python3
"""gate.py - quality gates for Copilot hooks (plan §7.4 G-1..G-6, §8.3, R-23, R-25).

Configured in .github/hooks/quality-gates.json (Copilot CLI / VS Code Copilot harness format).
Events (first argument):
  session-start   inject the active run-id so a new context resumes from state files
  pre-tool        deny forbidden edits / shell commands (G-1, G-2, G-3, G-5, G-6)
  subagent-start  remember which custom agent is running (preToolUse has no agent name)
  subagent-stop   G-4: run scripts/verify before implementer / test-designer / rd-author may finish
  agent-stop      do not let the conductor end its turn before the completion conditions hold

Reads the hook payload (camelCase or snake_case) from stdin; writes one JSON decision to stdout.
Fail-safe: unexpected internal errors allow the tool call (exit 0) and are logged to work/.hve/gate.log,
except that a malformed payload for pre-tool is allowed as well, so a broken gate never bricks a session.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import hvelib as h  # noqa: E402

WRITE_TOOL_RX = re.compile(r"edit|create|write|replace|patch|insert|delete|rename|move|notebook", re.I)
READ_TOOL_RX = re.compile(r"^(view|read|grep|glob|search|list|fetch|web)", re.I)
SHELL_TOOL_RX = re.compile(r"^(bash|powershell|shell|execute|run_in_terminal|terminal|runcommand|run_command)", re.I)
PATH_KEYS = ("path", "file_path", "filePath", "filepath", "target_file", "file", "uri", "paths", "files", "newPath", "oldPath")
STATE_TTL_SEC = 12 * 3600


# ---------------------------------------------------------------------- io helpers

def payload() -> dict:
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


class Ctx:
    def __init__(self, data: dict):
        self.data = data
        cwd = g(data, "cwd", default=os.getcwd())
        self.cwd = Path(cwd).resolve()
        self.root = h.repo_root(self.cwd)
        cfg0 = h.load_config(self.root)
        self.croot = h.conductor_root(self.root, cfg0)
        self.cfg = h.load_config(self.croot)
        self.state_dir = h.work_dir(self.croot, self.cfg) / ".hve"
        self.run_id = h.current_run(self.croot, self.cfg)
        self.meta = h.load_meta(self.croot, self.cfg, self.run_id) if self.run_id else {}
        self.run_active = bool(self.run_id and self.meta.get("status") == "active")

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

    def active_agents(self) -> List[dict]:
        data = h.read_json(self.agents_path(), default=[]) or []
        now = time.time()
        return [a for a in data if now - a.get("t", 0) < STATE_TTL_SEC]

    def active_names(self) -> List[str]:
        return [a.get("name", "") for a in self.active_agents()]

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
        if ctx.run_active or worker:
            return ("G-5", "実行中はゲート（hooks）を変更できません")
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
                       "（subagent の検出に問題がある場合は scripts/hve.config.json の gates.enforce_conductor_edit_scope を false にします）")
    return None


def check_shell(ctx: Ctx, cmd: str) -> Optional[Tuple[str, str]]:
    c = " ".join(cmd.split())
    base = ctx.cfg.get("base_branch", "main")
    names = ctx.active_names()
    worker = is_work_branch(ctx) or bool(re.search(r"[/\\]worktrees[/\\]", c) and "cd " in c)
    wd = ctx.cfg["work"]["dir"]
    for seg in re.split(r"&&|\|\||;|\n", cmd):
        s = " ".join(seg.split())
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
        if ctx.run_active and re.search(r"\bgit\s+(commit|merge|cherry-pick|am)\b", s) and h.current_branch(ctx.root) in (base, "master"):
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
        if re.search(r"\bledger\.py\b.*\b(add|update|block|digests|set)\b", c):
            return ("G-2", "作業役は台帳を更新しません（`ledger.py run --no-record` で実行だけ行います）")
    if re.search(r"(\b(Set-Content|Add-Content|Out-File|tee|sed\s+-i|perl\s+-pi)\b[^;&|]*|>{1,2}\s*)['\"]?(\./)?docs[/\\]requirements", c, re.I):
        if worker or (ctx.run_active and "rd-author" not in names):
            return ("G-1", "要求定義書を編集できるのは rd-author だけです")
    if re.search(r"(\b(Set-Content|Add-Content|Out-File|tee|sed\s+-i)\b[^;&|]*|>{1,2}\s*)['\"]?(\./)?docs[/\\]id-registry", c, re.I):
        return ("G-3", "ID 台帳は直接編集しません。scripts/next-id.py を使います")
    return None


def on_pre_tool(ctx: Ctx) -> None:
    tool = str(g(ctx.data, "toolName", "tool_name", default=""))
    args = g(ctx.data, "toolArgs", "tool_input", default={})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {"command": args} if SHELL_TOOL_RX.match(tool) else {"input": args}
    if SHELL_TOOL_RX.match(tool):
        cmd = ""
        if isinstance(args, dict):
            cmd = str(g(args, "command", "script", "cmd", "input", default=""))
        res = check_shell(ctx, cmd)
        if res:
            ctx.log(f"DENY {res[0]} {tool}: {cmd[:200]}")
            deny(res[1], res[0])
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
    agents = ctx.active_agents()
    agents.append({"name": name, "t": time.time()})
    ctx.save_agents(agents)
    ctx.log(f"START {name}")
    emit({})


def release_agent(ctx: Ctx, name: str) -> None:
    agents = ctx.active_agents()
    for i, a in enumerate(agents):
        if a.get("name") == name:
            del agents[i]
            break
    ctx.save_agents(agents)


def on_subagent_stop(ctx: Ctx) -> None:
    name = agent_name(ctx)
    gates = ctx.cfg["gates"]
    verify_map = gates.get("subagent_verify", {})
    if name not in verify_map:
        release_agent(ctx, name)
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
        release_agent(ctx, name)
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
    release_agent(ctx, name)
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


def on_agent_stop(ctx: Ctx) -> None:
    if not ctx.run_active:
        emit({})
        return
    sid = str(g(ctx.data, "sessionId", "session_id", default=""))
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
    mh = float(meta.get("options", {}).get("max_hours", 24) or 24)
    over = rs.elapsed_hours(meta) > mh * 1.25
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
        ctx = Ctx(data)
        if not ctx.cfg["gates"].get("enabled", True):
            emit({})
            return 0
        {"pre-tool": on_pre_tool, "subagent-start": on_subagent_start, "subagent-stop": on_subagent_stop,
         "session-start": on_session_start, "agent-stop": on_agent_stop}.get(event, lambda c: emit({}))(ctx)
    except Exception:  # never brick a session because of a gate bug
        try:
            d = Path(os.getcwd()) / "work" / ".hve"
            d.mkdir(parents=True, exist_ok=True)
            with open(d / "gate.log", "a", encoding="utf-8") as fh:
                fh.write(f"{h.now_iso()} ERROR {event}: {traceback.format_exc()}\n")
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
