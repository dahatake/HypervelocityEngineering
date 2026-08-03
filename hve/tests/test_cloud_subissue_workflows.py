"""Cloud Agent Orchestrator Sub-Issue workflow contract tests.

These tests protect the Cloud version path:
Issue Template / PR -> GitHub Actions -> GitHub Sub-Issue -> Copilot Cloud Agent.
They intentionally avoid executing GitHub APIs and assert only stable workflow
contract markers.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_workflow(name: str) -> str:
    return (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def _assert_in_order(text: str, *markers: str) -> None:
    positions = [text.index(marker) for marker in markers]
    assert positions == sorted(positions), f"markers are out of order: {markers!r}"


def test_create_subissues_from_pr_preserves_cloud_split_required_contract() -> None:
    text = _read_workflow("create-subissues-from-pr.yml")

    assert "pull_request:" in text
    assert "types: [labeled]" in text
    assert "github.event.label.name == 'create-subissues'" in text
    assert "create-subissues-${{ github.event.pull_request.number }}" in text
    assert "permissions:" in text
    assert "issues: write" in text
    assert "contents: write" in text
    assert "pull-requests: write" in text

    # Cloud split handoff must continue to discover only PR-changed work/**/subissues.md.
    assert 'test("^work/.*subissues\\\\.md$")' in text
    assert 'find work -type f -name \'subissues.md\'' in text

    # Parent issue metadata in subissues.md has priority before PR body fallback.
    assert "Method 0: Explicit metadata in changed subissues.md files" in text
    assert "parent[-_]issue" in text
    assert "gh pr view \"$PR_NUMBER\"" in text
    assert "closingIssuesReferences" in text

    # The workflow must create GitHub issues, link them as Sub-Issues, and assign Copilot.
    assert "gh issue create" in text
    assert '"/repos/${REPO}/issues/${PARENT_ISSUE}/sub_issues"' in text
    assert 'source "${GITHUB_WORKSPACE}/.github/scripts/bash/lib/assign-copilot.sh"' in text
    assert 'assign_copilot "$issue_num" "$agent" "$FILE_BASE_BRANCH" "" "$PARENT_MODEL"' in text

    # Idempotency and audit marker are required for safe re-runs.
    assert "<!-- subissues-created -->" in text
    assert "Sub issues already created" in text
    _assert_in_order(
        text,
        "Check idempotency",
        "Find subissues.md files",
        "Parse and create sub issues",
    )
    _assert_in_order(
        text,
        "Method 0: Explicit metadata in changed subissues.md files",
        "Method 1: closing issues references via gh pr view",
        "Method 2: Closing reference in PR body",
        "Method 3: Legacy HTML comment in PR body",
    )
    _assert_in_order(
        text,
        'contains("<!-- subissues-created -->")',
        "gh issue create",
    )


def test_advance_subissues_preserves_dependency_and_copilot_assignment_contract() -> None:
    text = _read_workflow("advance-subissues.yml")

    assert "pull_request:" in text
    assert "types: [closed]" in text
    assert "issues:" in text
    assert "types: [labeled]" in text
    assert "github.event.pull_request.merged == true" in text
    assert "permissions:" in text
    assert "issues: write" in text
    assert "contents: read" in text
    assert "pull-requests: write" in text

    # Parent resolution must support newly-created subissues, native Sub-Issues, and marker fallback.
    assert "find_parent_issue()" in text
    assert "parent-issue" in text
    assert "pr-number" in text
    assert "trackedInIssues" in text
    assert "subissues-created" in text

    # Dependency extraction and advancement must remain issue-number based.
    assert "## ⏳ 前提条件（Dependencies）" in text
    assert "<!-- depends_on: 213,216 -->" in text
    assert "DEP_NUMS" in text
    assert "ALL_DEPS_CLOSED" in text

    # Resolved dependent Sub-Issues are assigned to Copilot Cloud Agent on the merged PR head branch.
    assert 'source "${GITHUB_WORKSPACE}/.github/scripts/bash/lib/assign-copilot.sh"' in text
    assert 'assign_copilot "${sub_num}" "${AGENT}" "${PR_HEAD_BRANCH}" ""' in text
    assert "Sub Issue 自動アサイン" in text
    _assert_in_order(
        text,
        "Method 1: Sub Issue body の <!-- parent-issue: #NNN -->",
        "Method 2: Sub Issue body の <!-- pr-number: NNN -->",
        "Method 3a: GraphQL trackedInIssues",
        "Method 3b: <!-- subissues-created --> PR コメント経由",
    )
    _assert_in_order(
        text,
        "DEP_NUMS=",
        "ALL_DEPS_CLOSED=true",
        'if [ "${ALL_DEPS_CLOSED}" = "true" ]; then',
        'assign_copilot "${sub_num}"',
    )
