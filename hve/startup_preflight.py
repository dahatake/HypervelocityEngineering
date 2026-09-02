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

from hve.git_ref import is_valid_branch_name

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def is_github_repository_slug(value: Any) -> bool:
    """Return whether *value* is a strict ``owner/repo`` identifier."""
    if not isinstance(value, str) or not _REPO_PATTERN.fullmatch(value):
        return False
    owner, repository = value.split("/", 1)
    return owner not in {".", ".."} and repository not in {".", ".."}


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
    return is_valid_branch_name(value)


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


def _exact_remote_ref_sha(stdout: str, expected_ref: str) -> str:
    """``git ls-remote`` の単一exact-ref応答からSHAを返す。"""
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        return ""
    fields = lines[0].split()
    if len(fields) != 2 or fields[1] != expected_ref:
        return ""
    return fields[0]


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
    create_working_branch: bool,
    check_remote: bool,
    repo_root: Path,
) -> StartupPreflightResult:
    """GitHub 連携設定を検査し、判定可能な不整合を一括で返す。

    ``create_working_branch=False`` のときは current branch の local 安全検査を
    ``check_remote`` にかかわらず行い、remote ref の照合だけを
    ``check_remote=True`` に限定する（FR-CLI-83）。
    """
    if not github_write_required(
        workflow=workflow,
        active_steps=active_steps,
        create_issues=create_issues,
        create_pr=create_pr,
        enable_auto_merge=enable_auto_merge,
    ):
        return StartupPreflightResult()

    issues: list[StartupPreflightIssue] = []
    repo_is_valid = is_github_repository_slug(repo)
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

    current_branch = ""
    if not create_working_branch:
        try:
            current = _git_run(
                ["git", "branch", "--show-current"], repo_root=Path(repo_root)
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            current = None
        if current is None or current.returncode != 0:
            issues.append(_issue(
                "setting",
                "current_branch",
                "現在の Git branch を確認できません。",
                "Git が利用可能な作業ツリーで非ベースブランチを checkout してください。",
            ))
        else:
            current_branch = current.stdout.strip()
            if not current_branch:
                issues.append(_issue(
                    "setting",
                    "current_branch",
                    "detached HEAD では現在のブランチを PR head に使用できません。",
                    "安全な非ベースブランチを checkout してください。",
                ))
            elif not _valid_branch_name(current_branch):
                issues.append(_issue(
                    "setting",
                    "current_branch",
                    "現在の Git branch 名が不正です。",
                    "有効な非ベースブランチを checkout してください。",
                ))
            elif branch_is_valid and current_branch == str(base_branch):
                issues.append(_issue(
                    "setting",
                    "current_branch",
                    "現在のブランチがベースブランチと同一です。",
                    "ベースブランチへ直接 commit せず、別の作業ブランチを checkout してください。",
                ))

        try:
            status = _git_run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                repo_root=Path(repo_root),
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            status = None
        if status is None or status.returncode != 0:
            issues.append(_issue(
                "setting",
                "worktree",
                "Git worktree / index の状態を確認できません。",
                "Git status を実行できる作業ツリーで再実行してください。",
            ))
        elif status.stdout.strip():
            issues.append(_issue(
                "setting",
                "worktree",
                "current branch mode は clean な worktree / index を必要とします。",
                "変更を commit または別途保管し、未追跡ファイルを含む差分を解消してください。",
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

    if not create_working_branch and current_branch and _valid_branch_name(current_branch):
        try:
            local_head = _git_run(
                ["git", "rev-parse", "HEAD"], repo_root=root
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            local_head = None
        try:
            remote_head = _git_run(
                [
                    "git",
                    "ls-remote",
                    "--exit-code",
                    "--heads",
                    "origin",
                    f"refs/heads/{current_branch}",
                ],
                repo_root=root,
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            remote_head = None

        local_sha = (
            local_head.stdout.strip()
            if local_head is not None and local_head.returncode == 0
            else ""
        )
        if not local_sha:
            issues.append(_issue(
                "setting",
                "current_branch",
                "current branch の local HEAD を確認できません。",
                "local HEAD が有効な commit を指していることを確認してください。",
            ))
        elif remote_head is None:
            issues.append(_issue(
                "auth",
                "current_branch",
                "origin の current branch を確認できません。",
                "Git の認証、ネットワーク接続、および remote origin を確認してください。",
            ))
        elif remote_head.returncode == 0:
            remote_sha = _exact_remote_ref_sha(
                remote_head.stdout,
                f"refs/heads/{current_branch}",
            )
            if not remote_sha or remote_sha != local_sha:
                issues.append(_issue(
                    "setting",
                    "current_branch",
                    "origin/current branch と local HEAD が一致しません。",
                    "自動 pull / reset / force-push は行いません。remote と一致する branch を使用してください。",
                ))
        elif remote_head.returncode != 2:
            issues.append(_issue(
                "auth",
                "current_branch",
                "origin の current branch を確認できません。",
                "Git の認証、ネットワーク接続、および remote origin を確認してください。",
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
