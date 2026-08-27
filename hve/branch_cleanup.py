"""hve.branch_cleanup — マージ済みローカル作業 branch 削除の単一 core（FR-CLI-34 / FR-GUI-37）。

適格性判定と `git checkout <base>` → `git branch -D <branch>` の実行を 1 箇所へ集約する
（FR-MAINT-07）。Orchestrator と GUI monitor はいずれも本 core へ委譲し、同等の判定や
削除コマンドを再実装してはならない。remote branch の削除は行わない。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

__all__ = [
    "LocalBranchCleanupTarget",
    "LocalBranchCleanupResult",
    "is_cleanup_eligible",
    "delete_local_branch",
    "cleanup_local_branch",
]

# git コマンドの実行タイムアウト（秒）。ハングで GUI を止めない。
_GIT_TIMEOUT = 30.0


@dataclass(frozen=True)
class LocalBranchCleanupTarget:
    """ローカル cleanup の対象。"""

    repo: str
    pr_number: Any
    branch: str
    base_branch: str
    created_by_hve: bool


@dataclass(frozen=True)
class LocalBranchCleanupResult:
    """cleanup の結果。``deleted`` が True のときだけ削除が完了している。"""

    deleted: bool
    reason: str = ""


def _positive_int(value: Any) -> Optional[int]:
    """`bool` を除く正の整数だけを返す。"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _same_repo(left: Any, right: Any) -> bool:
    """`owner/repo` を大文字小文字を無視して比較する。"""
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    if not left or not right:
        return False
    return left.casefold() == right.casefold()


def _ref_repo(section: Any) -> tuple[Optional[str], Optional[str]]:
    """PR の head / base から `(ref, repo_full_name)` を取り出す。"""
    if not isinstance(section, Mapping):
        return None, None
    ref = section.get("ref")
    repo = section.get("repo")
    full_name = repo.get("full_name") if isinstance(repo, Mapping) else None
    return (
        ref if isinstance(ref, str) and ref else None,
        full_name if isinstance(full_name, str) and full_name else None,
    )


def is_cleanup_eligible(
    target: LocalBranchCleanupTarget,
    pull_request: Any,
) -> LocalBranchCleanupResult:
    """削除してよい条件をすべて満たすかを fail-closed で判定する。

    条件（FR-CLI-34）:
      - 当該 run が branch を新規作成した（`created_by_hve=True`）
      - PR 番号が `bool` でない正の整数で、取得結果の `number` と一致する
      - PR の `merged` が厳密に `True`
      - PR の `head.ref` が対象 branch と一致し、`head.repo.full_name` が対象 repo と一致する
      - PR の `base.ref` が base branch と一致し、`base.repo.full_name` が対象 repo と一致する
      - 対象 branch が base branch と異なる
    """
    if not target.created_by_hve:
        return LocalBranchCleanupResult(False, "HVE が作成した branch ではありません。")

    branch = target.branch if isinstance(target.branch, str) else ""
    base = target.base_branch if isinstance(target.base_branch, str) else ""
    if not branch or not base:
        return LocalBranchCleanupResult(False, "branch または base branch が未確定です。")
    if branch == base:
        return LocalBranchCleanupResult(False, "base branch は削除できません。")

    number = _positive_int(target.pr_number)
    if number is None:
        return LocalBranchCleanupResult(False, "PR 番号が正の整数ではありません。")

    if not isinstance(pull_request, Mapping):
        return LocalBranchCleanupResult(False, "PR の取得結果が不正です。")
    if _positive_int(pull_request.get("number")) != number:
        return LocalBranchCleanupResult(False, "PR 番号が取得結果と一致しません。")
    if pull_request.get("merged") is not True:
        return LocalBranchCleanupResult(False, "PR がマージされていません。")

    head_ref, head_repo = _ref_repo(pull_request.get("head"))
    if head_ref != branch:
        return LocalBranchCleanupResult(False, "PR の head branch が一致しません。")
    if not _same_repo(head_repo, target.repo):
        return LocalBranchCleanupResult(False, "PR の head が別リポジトリです。")

    base_ref, base_repo = _ref_repo(pull_request.get("base"))
    if base_ref != base:
        return LocalBranchCleanupResult(False, "PR の base branch が一致しません。")
    if not _same_repo(base_repo, target.repo):
        return LocalBranchCleanupResult(False, "PR の base が別リポジトリです。")

    return LocalBranchCleanupResult(True, "")


def delete_local_branch(
    branch: str,
    base_branch: str,
    *,
    runner: Optional[Callable[..., Any]] = None,
) -> LocalBranchCleanupResult:
    """`git checkout <base>` → `git branch -D <branch>` の単一実装（FR-MAINT-07）。

    squash マージではローカルが「マージ済み」と判定されないため `-D` を使う。
    remote branch の削除は行わない。
    """
    run = runner if runner is not None else subprocess.run

    checkout = _run_git(run, ["git", "checkout", base_branch])
    if checkout is None:
        return LocalBranchCleanupResult(False, "git checkout を実行できませんでした。")
    if getattr(checkout, "returncode", 1) != 0:
        return LocalBranchCleanupResult(
            False, "base branch への checkout に失敗しました。"
        )

    delete = _run_git(run, ["git", "branch", "-D", "--", branch])
    if delete is None:
        return LocalBranchCleanupResult(False, "git branch -D を実行できませんでした。")
    if getattr(delete, "returncode", 1) != 0:
        return LocalBranchCleanupResult(False, "ローカル branch の削除に失敗しました。")

    return LocalBranchCleanupResult(True, "")


def cleanup_local_branch(
    target: LocalBranchCleanupTarget,
    pull_request: Any,
    *,
    runner: Optional[Callable[..., Any]] = None,
) -> LocalBranchCleanupResult:
    """適格な場合だけローカル branch を削除する。

    remote branch の削除 API / `git push origin --delete` は呼ばない（FR-GUI-37）。
    """
    eligibility = is_cleanup_eligible(target, pull_request)
    if not eligibility.deleted:
        return eligibility
    return delete_local_branch(target.branch, target.base_branch, runner=runner)


def _run_git(run: Callable[..., Any], command: list) -> Optional[Any]:
    """git を shell を介さずに実行する。起動失敗・タイムアウトは ``None``。"""
    try:
        return run(command, capture_output=True, text=True, timeout=_GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
