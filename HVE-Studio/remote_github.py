"""Read-only GitHub data (issues, pull requests, Actions runs) of the selected repository.

Uses the GitHub CLI already installed and authenticated on this device. Studio never reads, asks for or stores
a token, never writes to GitHub, and keeps the results in memory only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import repo_scan

DEFAULT_LIMIT = 10000
DEFAULT_TIMEOUT = 600
REMOTE_RE = re.compile(r"^(?:[a-z+]+://)?(?:[^@/]+@)?([^/:]+)(?::\d+)?[:/]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
SECTIONS = {
    "issues": ["issue", "list", "--state", "all",
               "--json", "number,title,state,url,labels,assignees,milestone,author,createdAt,updatedAt,closedAt"],
    "pulls": ["pr", "list", "--state", "all",
              "--json", "number,title,state,isDraft,url,headRefName,baseRefName,author,createdAt,updatedAt,mergedAt,reviewDecision"],
    "runs": ["run", "list",
             "--json", "databaseId,workflowName,displayTitle,status,conclusion,headBranch,event,createdAt,url"],
}


def limit() -> int:
    try:
        value = int(os.environ.get("HVE_STUDIO_REMOTE_LIMIT", DEFAULT_LIMIT))
        if value > 0:
            return value
    except ValueError:
        pass
    raise ValueError("HVE_STUDIO_REMOTE_LIMIT must be a positive integer")


def timeout() -> int:
    try:
        value = int(os.environ.get("HVE_STUDIO_REMOTE_TIMEOUT", DEFAULT_TIMEOUT))
        if value > 0:
            return value
    except ValueError:
        pass
    raise ValueError("HVE_STUDIO_REMOTE_TIMEOUT must be a positive integer (seconds)")


def github_repo(root: Path) -> str | None:
    """host/owner/name of the `origin` remote (or the only remote) when it is a GitHub host."""
    names = repo_scan.git(root, "remote").stdout.decode("utf-8", "replace").split()
    name = "origin" if "origin" in names else (names[0] if len(names) == 1 else None)
    if name is None:
        return None
    url = repo_scan.git(root, "remote", "get-url", name).stdout.decode("utf-8", "replace").strip()
    match = REMOTE_RE.match(url)
    if not match or "github" not in match.group(1).lower():
        return None
    return "/".join(match.groups())


def _names(items, key: str) -> list[str]:
    return [item.get(key, "") for item in items or [] if isinstance(item, dict)]


def _normalize(section: str, item: dict) -> dict:
    out = dict(item)
    if "author" in out:
        out["author"] = (out["author"] or {}).get("login", "")
    if section == "issues":
        out["labels"] = _names(out.get("labels"), "name")
        out["assignees"] = _names(out.get("assignees"), "login")
        out["milestone"] = (out.get("milestone") or {}).get("title", "")
    return out


def fetch(root: Path, run=subprocess.run, progress=None) -> dict:
    """{status: ok|partial|unavailable|error, repo, issues, pulls, runs, errors, truncated, fetchedAt}.

    progress(partial) is called with status "loading" each time one section finishes."""
    result = {"status": "unavailable", "repo": None, "issues": [], "pulls": [], "runs": [], "errors": {},
              "truncated": [], "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        result["limit"] = limit()
    except ValueError as exc:
        return {**result, "status": "error", "reason": str(exc)}
    try:
        result["repo"] = github_repo(root)
    except repo_scan.ScanError as exc:
        return {**result, "status": "error", "reason": str(exc)}
    if result["repo"] is None:
        return {**result, "reason": "no GitHub remote (origin) is configured"}
    try:
        wait = timeout()
    except ValueError as exc:
        return {**result, "status": "error", "reason": str(exc)}
    # Sections run in parallel: Actions runs can take minutes on busy repositories, issues and PRs take seconds.
    with ThreadPoolExecutor(max_workers=len(SECTIONS)) as pool:
        futures = {pool.submit(_section, run, section, result["limit"], result["repo"], wait): section
                   for section in SECTIONS}
        unavailable = None
        pending = list(SECTIONS)
        for future in as_completed(futures):
            section = futures[future]
            pending.remove(section)
            items, error, reason = future.result()
            if reason:
                unavailable = unavailable or reason
            elif error:
                result["errors"][section] = error
            else:
                result[section] = items
                if len(items) >= result["limit"]:
                    result["truncated"].append(section)
            if progress and not unavailable:
                progress({**result, "status": "loading", "errors": dict(result["errors"]),
                          "truncated": list(result["truncated"]), "pending": list(pending)})
    if unavailable:
        return {**result, "issues": [], "pulls": [], "runs": [], "errors": {}, "truncated": [], "reason": unavailable}
    result["truncated"].sort(key=list(SECTIONS).index)
    result["status"] = "error" if len(result["errors"]) == len(SECTIONS) else "partial" if result["errors"] else "ok"
    return result


def _section(run, section: str, max_items: int, repo: str, wait: int):
    """(items, error, unavailable_reason) of one gh list command."""
    try:
        proc = run(["gh", *SECTIONS[section],  "--limit", str(max_items), "-R", repo],
                   capture_output=True, timeout=wait, check=False,
                   env={**os.environ, "GH_PROMPT_DISABLED": "1", "NO_COLOR": "1"})
    except FileNotFoundError:
        return None, None, "GitHub CLI (gh) is not installed"
    except subprocess.TimeoutExpired:
        return None, f"timed out after {wait} s (set HVE_STUDIO_REMOTE_TIMEOUT)", None
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc), None
    if proc.returncode:
        message = proc.stderr.decode("utf-8", "replace").strip() or f"gh exited with {proc.returncode}"
        if "auth login" in message:
            return None, None, "GitHub CLI is not authenticated: run `gh auth login`"
        return None, message, None
    try:
        items = json.loads(proc.stdout.decode("utf-8") or "[]")
    except ValueError as exc:
        return None, f"invalid gh output: {exc}", None
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        return None, "invalid gh output: expected an array of objects", None
    return [_normalize(section, item) for item in items], None, None


def issue_tasks(remote: dict) -> list[dict]:
    return [{"id": f"github:issue:{item['number']}", "title": f"#{item['number']} {item.get('title', '')}",
             "status": "done" if str(item.get("state", "")).upper() == "CLOSED" else "todo",
             "file": "", "line": None, "url": item.get("url", ""), "origin": "github"}
            for item in remote.get("issues", []) if isinstance(item.get("number"), int)]
