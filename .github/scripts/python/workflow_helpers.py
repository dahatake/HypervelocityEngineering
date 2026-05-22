#!/usr/bin/env python3
import json
import os
import re
import sys
from typing import Any

DEFAULT_MARKER = "<!-- auto-close-done -->"


def _stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _load_json_stdin(default: Any) -> Any:
    raw = sys.stdin.read()
    if not raw.strip():
        return default
    try:
        return json.loads(raw)
    except Exception as exc:
        _stderr(f"Failed to parse JSON from stdin: {exc}")
        return default


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe_keep_order(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def cmd_has_marker(argv: list[str]) -> int:
    marker = argv[2] if len(argv) > 2 else DEFAULT_MARKER
    comments = _as_list(_load_json_stdin([]))
    found = any(
        marker in ((c.get("body") or "") if isinstance(c, dict) else "")
        for c in comments
    )
    print("true" if found else "false")
    return 0


def cmd_count_items(_: list[str]) -> int:
    data = _load_json_stdin([])
    print(len(data) if isinstance(data, list) else 0)
    return 0


def cmd_all_closed(_: list[str]) -> int:
    issues = _as_list(_load_json_stdin([]))
    all_closed = all(((i.get("state") if isinstance(i, dict) else None) == "closed") for i in issues)
    print("true" if all_closed else "false")
    return 0


def cmd_has_label(argv: list[str]) -> int:
    label = argv[2] if len(argv) > 2 else ""
    issue = _as_dict(_load_json_stdin({}))
    labels = [l.get("name", "") for l in _as_list(issue.get("labels")) if isinstance(l, dict)]
    print("true" if label and label in labels else "false")
    return 0


def cmd_check_auto_merge(_: list[str]) -> int:
    issue = _as_dict(_load_json_stdin({}))
    labels = [l.get("name", "") for l in _as_list(issue.get("labels")) if isinstance(l, dict)]
    body = issue.get("body") or ""
    section = re.search(r"###\s*PR完全自動化設定\s*\n(.*?)(?=\n###|\Z)", body, flags=re.DOTALL)
    enabled = (
        "auto-approve-ready" in labels
        or bool(re.search(r"<!--\s*auto-merge:\s*true\s*-->", body))
        or bool(
            section
            and re.search(
                r"-\s*\[[xX]\]\s*PR の自動 Approve & Auto-merge を有効にする",
                section.group(1),
            )
        )
    )
    print("true" if enabled else "false")
    return 0


def cmd_parse_closing_issues(_: list[str]) -> int:
    body = sys.stdin.read()
    nums = re.findall(
        r"(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+(?:[\w\-\.]+/[\w\-\.]+)?#(\d+)",
        body,
        flags=re.IGNORECASE,
    )
    for number in _dedupe_keep_order(nums):
        print(number)
    return 0


def cmd_check_assignees(_: list[str]) -> int:
    issue = _as_dict(_load_json_stdin({}))
    logins = {
        (a.get("login", "").casefold())
        for a in _as_list(issue.get("assignees"))
        if isinstance(a, dict)
    }
    assigned = "copilot-swe-agent" in logins or "copilot" in logins
    print("true" if assigned else "false")
    return 0


def cmd_check_open_prs(_: list[str]) -> int:
    timeline = _as_list(_load_json_stdin([]))
    for event in timeline:
        if not isinstance(event, dict) or event.get("event") != "cross-referenced":
            continue
        source = _as_dict(event.get("source"))
        issue = _as_dict(source.get("issue"))
        if issue.get("pull_request") is not None and issue.get("state") == "open":
            print("true")
            return 0
    print("false")
    return 0


def cmd_parse_graphql_ids(_: list[str]) -> int:
    data = _as_dict(_load_json_stdin({}))
    repo = _as_dict(_as_dict(data.get("data")).get("repository"))
    issue = _as_dict(repo.get("issue"))
    suggested = _as_dict(issue.get("suggestedActors"))
    nodes = _as_list(suggested.get("nodes"))

    bot_id = ""
    for node in nodes:
        if not isinstance(node, dict):
            continue
        login = (node.get("login") or "").casefold()
        if login in {"copilot-swe-agent", "copilot"}:
            bot_id = node.get("id") or ""
            break

    issue_node_id = issue.get("id") or ""
    repo_node_id = repo.get("id") or ""
    print(f"{bot_id}\t{issue_node_id}\t{repo_node_id}")
    return 0


def cmd_check_mutation_errors(_: list[str]) -> int:
    data = _as_dict(_load_json_stdin({}))
    errors = data.get("errors")
    has_errors = isinstance(errors, list) and len(errors) > 0
    print("true" if has_errors else "false")
    return 0


def _read_nested(root: Any, path: list[str]) -> Any:
    node = root
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def cmd_check_assigned(_: list[str]) -> int:
    data = _as_dict(_load_json_stdin({}))
    candidate_paths = [
        ["data", "addAssigneesToAssignable", "assignable", "assignees", "nodes"],
        ["data", "updateIssue", "issue", "assignees", "nodes"],
    ]
    for path in candidate_paths:
        nodes = _read_nested(data, path)
        if not isinstance(nodes, list):
            continue
        logins = {
            (n.get("login", "").casefold())
            for n in nodes
            if isinstance(n, dict)
        }
        if "copilot-swe-agent" in logins or "copilot" in logins:
            print("true")
            return 0
    print("false")
    return 0


def cmd_extract_deps(_: list[str]) -> int:
    body = sys.stdin.read()
    deps: list[str] = []

    section = re.search(
        r"##\s*⏳?\s*前提条件(?:（Dependencies）|\(Dependencies\))?\s*\n(.*?)(?=\n##|\Z)",
        body,
        flags=re.DOTALL,
    )
    if section:
        deps.extend(re.findall(r"(?:^|\s)-\s*#(\d+)\b", section.group(1), flags=re.MULTILINE))

    for match in re.findall(r"<!--\s*depends_on\s*:\s*([0-9,\s]+)\s*-->", body, flags=re.IGNORECASE):
        deps.extend(re.findall(r"\d+", match))

    print(" ".join(_dedupe_keep_order(deps)))
    return 0


def cmd_extract_agent(_: list[str]) -> int:
    body = sys.stdin.read()

    match = re.search(r"##\s*Custom Agent\s*\n+`([^`]+)`", body)
    if match:
        print(match.group(1).strip())
        return 0

    match = re.search(r">\s*\*\*Custom agent used:\s*([^*]+)\*\*", body, flags=re.IGNORECASE)
    if match:
        print(match.group(1).strip())
        return 0

    print("")
    return 0


def cmd_parse_sub_issues(_: list[str]) -> int:
    issues = _as_list(_load_json_stdin([]))
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        number = issue.get("number")
        if number in (None, ""):
            continue
        state = issue.get("state", "")
        title = (issue.get("title") or "").replace("\t", " ").replace("\n", " ").replace("\r", " ")
        print(f"{number}\t{state}\t{title}")
    return 0


def cmd_extract_model(_: list[str]) -> int:
    body = sys.stdin.read()
    match = re.search(r"###\s*使用するモデル\s*\n+([^\n#]+)", body)
    if not match:
        print("")
        return 0

    value = match.group(1).strip()
    if value == "GPT-5.5":
        value = "gpt-5.5"

    allowed = {
        "Auto",
        "gpt-5.5",
        "claude-opus-4.7",
        "claude-opus-4.6",
        "gpt-5.4",
    }
    print(value if value in allowed else "")
    return 0


def cmd_char_count(_: list[str]) -> int:
    print(len(os.environ.get("QA_CONTENT", "")))
    return 0


def cmd_truncate(_: list[str]) -> int:
    content = os.environ.get("QA_CONTENT", "")
    raw = os.environ.get("CONTENT_TRUNCATE_AT", "")
    try:
        limit = int(raw)
    except Exception as exc:
        _stderr(f"Invalid CONTENT_TRUNCATE_AT value: {exc}")
        limit = len(content)
    if limit < 0:
        limit = 0
    print(content[:limit], end="")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        _stderr("Usage: workflow_helpers.py <subcommand> [args...]")
        return 1

    command = argv[1]
    handlers = {
        "has_marker": cmd_has_marker,
        "count_items": cmd_count_items,
        "all_closed": cmd_all_closed,
        "has_label": cmd_has_label,
        "check_auto_merge": cmd_check_auto_merge,
        "parse_closing_issues": cmd_parse_closing_issues,
        "check_assignees": cmd_check_assignees,
        "check_open_prs": cmd_check_open_prs,
        "parse_graphql_ids": cmd_parse_graphql_ids,
        "check_mutation_errors": cmd_check_mutation_errors,
        "check_assigned": cmd_check_assigned,
        "extract_deps": cmd_extract_deps,
        "extract_agent": cmd_extract_agent,
        "parse_sub_issues": cmd_parse_sub_issues,
        "extract_model": cmd_extract_model,
        "char_count": cmd_char_count,
        "truncate": cmd_truncate,
    }

    handler = handlers.get(command)
    if handler is None:
        _stderr(f"Unknown subcommand: {command}")
        return 1

    try:
        return handler(argv)
    except Exception as exc:
        _stderr(f"Subcommand '{command}' failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
