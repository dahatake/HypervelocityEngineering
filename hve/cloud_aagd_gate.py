"""AAGD Cloud workflow completion gate.

The gate is intentionally independent from the GitHub Actions shell script so the
same recursive rules run both when the Root becomes Self-Improve-ready and again
immediately before Post-DAG mutation.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from collections import deque
from typing import Any, Callable, Dict, Iterable, List

_BLOCKING_LABELS = frozenset({"aagd:blocked", "aagd:test-failed"})
_DONE_LABEL = "aagd:done"


def validate_aagd_issue_tree(
    root_issue: int,
    fetch_issue: Callable[[int], Dict[str, Any]],
    fetch_children: Callable[[int], Iterable[Dict[str, Any]]],
    *,
    allow_root_self_improve_blocked: bool = False,
) -> List[str]:
    """Return deterministic violations for an AAGD Root and all descendants.

    Every existing descendant must have ``aagd:done`` and must not carry a
    blocking label. Explicitly skipped steps are not created, so they do not
    appear in the tree. The Root may retain ``aagd:blocked`` only while retrying
    a previously failed Post-DAG Self-Improve run; descendants never receive
    that exception.
    """

    violations: List[str] = []
    queue: deque[tuple[int, bool]] = deque([(int(root_issue), True)])
    seen: set[int] = set()
    descendant_count = 0

    while queue:
        issue_number, is_root = queue.popleft()
        if issue_number in seen:
            continue
        seen.add(issue_number)

        issue = fetch_issue(issue_number)
        labels = {
            str(item.get("name", ""))
            for item in issue.get("labels", [])
            if isinstance(item, dict)
        }
        blocking = set(labels & _BLOCKING_LABELS)
        if is_root and allow_root_self_improve_blocked:
            blocking.discard("aagd:blocked")
        if blocking:
            violations.append(
                f"#{issue_number}:blocking-labels={','.join(sorted(blocking))}"
            )
        if not is_root and _DONE_LABEL not in labels:
            violations.append(f"#{issue_number}:missing-{_DONE_LABEL}")

        children = [
            child
            for child in fetch_children(issue_number)
            if isinstance(child, dict) and child.get("number") is not None
        ]
        for child in children:
            descendant_count += 1
            queue.append((int(child["number"]), False))

    if descendant_count == 0:
        violations.append(f"#{root_issue}:no-descendant-issues")
    return violations


class GitHubIssueReader:
    """Minimal read-only GitHub Issues REST adapter with pagination."""

    def __init__(self, repo: str, token: str) -> None:
        self.repo = repo
        self.token = token
        self.base_url = f"https://api.github.com/repos/{repo}"

    def _get(self, path: str) -> Any:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def fetch_issue(self, issue_number: int) -> Dict[str, Any]:
        payload = self._get(f"/issues/{int(issue_number)}")
        if not isinstance(payload, dict):
            raise ValueError(f"Issue #{issue_number} response is not an object")
        return payload

    def fetch_children(self, issue_number: int) -> Iterable[Dict[str, Any]]:
        page = 1
        while True:
            payload = self._get(
                f"/issues/{int(issue_number)}/sub_issues?per_page=100&page={page}"
            )
            if not isinstance(payload, list):
                raise ValueError(
                    f"Issue #{issue_number} sub-issues response is not an array"
                )
            for child in payload:
                if isinstance(child, dict):
                    yield child
            if len(payload) < 100:
                break
            page += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate AAGD Cloud Issue tree")
    parser.add_argument("--repo", required=True, help="owner/repository")
    parser.add_argument("--root", required=True, type=int, help="Root Issue number")
    parser.add_argument(
        "--allow-root-self-improve-blocked",
        action="store_true",
        help="Allow Root aagd:blocked while retrying Post-DAG Self-Improve",
    )
    args = parser.parse_args(argv)
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        parser.error("GH_TOKEN is required")

    reader = GitHubIssueReader(args.repo, token)
    violations = validate_aagd_issue_tree(
        args.root,
        reader.fetch_issue,
        reader.fetch_children,
        allow_root_self_improve_blocked=args.allow_root_self_improve_blocked,
    )
    if violations:
        print(
            "AAGD TDD/Deploy gate failure prevents Self-Improve: "
            + "; ".join(violations)
        )
        return 1
    print(f"AAGD Cloud Issue tree gate PASS: root=#{args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
