"""GitHub 書き込みを伴うローカル実行の設定整合性 preflight。

FR-CLI-82 の単一実装。Prompt 自由記述は入力として受け取らず、モデルや
GitHub API を起動しない。remote 検証は読み取り専用 Git コマンドだけを使う。
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
_INVALID_BRANCH_CHARS = frozenset(" ~^:?*[\\")


@dataclass(frozen=True)
class StartupPreflightIssue:
    category: str
    field_name: str
    message: str
    remediation_hint: str


@dataclass(frozen=True)
class StartupPreflightResult:
    issues: tuple[StartupPreflightIssue, ...] = ()

    def is_ok(self) -> bool:
        return not self.issues


def github_write_required(
    *,
    workflow: Any | None,
    active_steps: Iterable[str],
    create_issues: bool,
    create_pr: bool,
    enable_auto_merge: bool,
) -> bool:
    """この実行が GitHub branch / Issue / PR 書き込みを必要とするか返す。"""
    if create_issues or create_pr:
        return True
    if not enable_auto_merge or workflow is None:
        return False
    if getattr(workflow, "id", "") == "adfdv":
        return True

    active_base_ids = {str(step_id).split("/", 1)[0] for step_id in active_steps}
    return any(
        not bool(getattr(step, "is_container", False))
        and bool(getattr(step, "requires_remote_cicd", False))
        and str(getattr(step, "id", "")) in active_base_ids
        for step in getattr(workflow, "steps", ())
    )


def _valid_branch_name(value: Any) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if value == "@" or value.startswith(("-", "/")):
        return False
    if value.endswith(("/", ".")) or "//" in value or ".." in value or "@{" in value:
        return False
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        return False
    if any(char in _INVALID_BRANCH_CHARS for char in value):
        return False
    return all(
        part and not part.startswith(".") and not part.endswith(".lock")
        for part in value.split("/")
    )


def _issue(
    category: str,
    field_name: str,
    message: str,
    remediation_hint: str,
) -> StartupPreflightIssue:
    return StartupPreflightIssue(
        category=category,
        field_name=field_name,
        message=message,
        remediation_hint=remediation_hint,
    )


def _git_run(command: list[str], *, repo_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        command,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=env,
        shell=False,
        check=False,
    )


def validate_startup_configuration(
    *,
    workflow: Any | None,
    active_steps: Iterable[str],
    create_issues: bool,
    create_pr: bool,
    enable_auto_merge: bool,
    repo: Any,
    token: Any,
    base_branch: Any,
    check_remote: bool,
    repo_root: Path,
) -> StartupPreflightResult:
    """GitHub 連携設定を検査し、判定可能な不整合を一括で返す。"""
    if not github_write_required(
        workflow=workflow,
        active_steps=active_steps,
        create_issues=create_issues,
        create_pr=create_pr,
        enable_auto_merge=enable_auto_merge,
    ):
        return StartupPreflightResult()

    issues: list[StartupPreflightIssue] = []
    repo_is_valid = isinstance(repo, str) and bool(_REPO_PATTERN.fullmatch(repo))
    if repo_is_valid:
        owner, repository = repo.split("/", 1)
        repo_is_valid = owner not in {".", ".."} and repository not in {".", ".."}
    if not repo_is_valid:
        issues.append(_issue(
            "setting",
            "repo",
            "GitHub リポジトリが owner/repo 形式ではありません。",
            "--repo または REPO に owner/repo 形式の値を設定してください。",
        ))
    if (
        not isinstance(token, str)
        or not token
        or any(char.isspace() for char in token)
    ):
        issues.append(_issue(
            "auth",
            "token",
            "GitHub token を解決できません。",
            "GH_TOKEN または GITHUB_TOKEN を設定してください。",
        ))

    branch_is_valid = _valid_branch_name(base_branch)
    if not branch_is_valid:
        issues.append(_issue(
            "setting",
            "base_branch",
            "ベースブランチ名が Git branch 名として不正です。",
            "空白や禁止文字を含まない既存の remote branch 名を設定してください。",
        ))

    if not check_remote:
        return StartupPreflightResult(tuple(issues))

    root = Path(repo_root)
    try:
        origin = _git_run(["git", "remote", "get-url", "origin"], repo_root=root)
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        issues.append(_issue(
            "setting",
            "origin",
            "Git remote origin を確認できません。",
            "Git が利用可能で、対象リポジトリに origin が設定されていることを確認してください。",
        ))
        return StartupPreflightResult(tuple(issues))

    if origin.returncode != 0 or not origin.stdout.strip():
        issues.append(_issue(
            "setting",
            "origin",
            "Git remote origin が設定されていません。",
            "対象リポジトリの remote origin を設定してください。",
        ))
        return StartupPreflightResult(tuple(issues))

    if not branch_is_valid:
        return StartupPreflightResult(tuple(issues))

    branch = str(base_branch)
    try:
        remote_branch = _git_run(
            [
                "git",
                "ls-remote",
                "--exit-code",
                "--heads",
                "origin",
                f"refs/heads/{branch}",
            ],
            repo_root=root,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        issues.append(_issue(
            "auth",
            "remote",
            "remote branch の実在を確認できません。",
            "Git の認証、ネットワーク接続、および remote origin を確認してください。",
        ))
        return StartupPreflightResult(tuple(issues))

    if remote_branch.returncode == 2:
        issues.append(_issue(
            "setting",
            "base_branch",
            f"remote branch 'origin/{branch}' は存在しません。",
            "origin に存在するベースブランチを選択してください。",
        ))
    elif remote_branch.returncode != 0:
        issues.append(_issue(
            "auth",
            "remote",
            "remote branch の実在を確認できません。",
            "Git の認証とネットワーク接続を確認してください。",
        ))

    return StartupPreflightResult(tuple(issues))


def format_startup_preflight_errors(result: StartupPreflightResult) -> str:
    """token 値を含めず、preflight の全不整合を人間向けに整形する。"""
    lines = ["起動前の設定整合性チェックに失敗しました:"]
    for item in result.issues:
        lines.append(f"  - {item.field_name}: {item.message}")
        if item.remediation_hint:
            lines.append(f"    対処: {item.remediation_hint}")
    return "\n".join(lines)


__all__ = [
    "StartupPreflightIssue",
    "StartupPreflightResult",
    "format_startup_preflight_errors",
    "github_write_required",
    "validate_startup_configuration",
]
