"""hve.gui.git_ops — GUI から呼ぶ最小限の git 操作（FR-GUI-34）。

FR-GUI-34 は push を git の 1 コマンド実行に限定する。`hve.orchestrator` の
add / commit / 保護パス検査を含む一連の処理は CLI 出力器と Orchestrator の
実行文脈に依存するため、GUI からは呼び出さない。PySide6 へは依存しない。
"""

from __future__ import annotations

import subprocess
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

__all__ = [
    "GitOpsError",
    "PullRequestPreflight",
    "current_branch",
    "inspect_pull_request",
    "load_pull_request_template",
    "origin_repository",
    "parse_github_remote_url",
    "push_current_branch",
]

_TIMEOUT = 120
_GITHUB_REMOTE_PATTERNS = (
    re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/?$"),
    re.compile(r"^git@github\.com:([^/\s]+)/([^/\s]+)$"),
    re.compile(r"^ssh://git@github\.com/([^/\s]+)/([^/\s]+)/?$"),
)


class GitOpsError(Exception):
    """GUI へ表示するための git 操作エラー。"""


@dataclass(frozen=True)
class PullRequestPreflight:
    head_branch: str
    base_branch: str
    ahead_commits: int
    changed_files: int
    published: bool
    unpushed_commits: int
    origin_repo: str = ""

    @property
    def ready(self) -> bool:
        return self.published and self.unpushed_commits == 0


def _run(
    args: list[str],
    timeout: int = _TIMEOUT,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(cwd) if cwd is not None else None,
        )
    except FileNotFoundError as exc:
        raise GitOpsError("git コマンドが見つかりません。") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitOpsError("git 操作がタイムアウトしました。") from exc


def current_branch(repo_root: Optional[Path] = None) -> Optional[str]:
    """現在のブランチ名を返す。detached HEAD / 取得失敗時は ``None``。"""
    proc = _run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        timeout=30,
        cwd=repo_root,
    )
    if proc.returncode != 0:
        return None
    name = (proc.stdout or "").strip()
    return name if name and name != "HEAD" else None


def push_current_branch(repo_root: Optional[Path] = None) -> str:
    """現在のブランチを ``origin`` へ push する（FR-GUI-34）。

    Returns:
        push したブランチ名。

    Raises:
        GitOpsError: ブランチ名を解決できない場合、または push が失敗した場合。
    """
    branch = current_branch(repo_root)
    if not branch:
        raise GitOpsError(
            "現在のブランチを特定できません（detached HEAD の可能性があります）。"
        )
    proc = _run(["git", "push", "-u", "origin", branch], cwd=repo_root)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise GitOpsError(f"ブランチ '{branch}' の push に失敗しました: {detail}")
    return branch


def _required_output(args: list[str], repo_root: Path, label: str) -> str:
    result = _run(args, timeout=30, cwd=repo_root)
    if result.returncode != 0:
        raise GitOpsError(f"{label}を確認できませんでした。")
    return (result.stdout or "").strip()


def origin_repository(repo_root: Path) -> Optional[str]:
    """origin URL から GitHub の ``owner/repo`` を返す。"""
    result = _run(
        ["git", "remote", "get-url", "origin"],
        timeout=30,
        cwd=Path(repo_root),
    )
    if result.returncode != 0:
        return None
    return parse_github_remote_url((result.stdout or "").strip())


def parse_github_remote_url(url: str) -> Optional[str]:
    """GitHub remote URL から ``owner/repo`` を抽出する。"""
    value = (url or "").strip()
    if not value:
        return None
    for pattern in _GITHUB_REMOTE_PATTERNS:
        match = pattern.match(value)
        if not match:
            continue
        owner, repo = match.group(1), match.group(2)
        if repo.endswith(".git"):
            repo = repo[:-4]
        if owner and repo and "/" not in owner and "/" not in repo:
            return f"{owner}/{repo}"
    return None


def inspect_pull_request(repo_root: Path, base_branch: str) -> PullRequestPreflight:
    """現在 branch の direct PR 作成可否を副作用なしで検査する。"""
    root = Path(repo_root)
    origin_repo = origin_repository(root)
    if not origin_repo:
        raise GitOpsError("origin の GitHub repository を特定できません。")
    head = current_branch(root)
    if not head:
        raise GitOpsError("現在の branch を特定できません（detached HEAD の可能性があります）。")
    base = (base_branch or "").strip()
    if not base:
        raise GitOpsError("base branch が空です。")
    if head == base:
        raise GitOpsError("head branch と base branch が同じです。")

    status = _run(["git", "status", "--porcelain"], timeout=30, cwd=root)
    if status.returncode != 0:
        raise GitOpsError("worktree の状態を確認できませんでした。")
    if (status.stdout or "").strip():
        raise GitOpsError("未コミットの変更があります。commit 後に再実行してください。")

    base_ref = f"refs/remotes/origin/{base}"
    base_check = _run(
        ["git", "show-ref", "--verify", "--quiet", base_ref],
        timeout=30,
        cwd=root,
    )
    if base_check.returncode != 0:
        raise GitOpsError(f"remote base branch 'origin/{base}' が見つかりません。")

    ahead_text = _required_output(
        ["git", "rev-list", "--count", f"origin/{base}..HEAD"],
        root,
        "commit 差分",
    )
    try:
        ahead = int(ahead_text)
    except ValueError as exc:
        raise GitOpsError("commit 差分の件数が不正です。") from exc
    if ahead <= 0:
        raise GitOpsError("base branch に対する新しい commit がありません。")

    files_text = _required_output(
        ["git", "diff", "--name-only", f"origin/{base}...HEAD"],
        root,
        "変更ファイル",
    )
    changed_files = len([line for line in files_text.splitlines() if line.strip()])

    head_ref = f"refs/remotes/origin/{head}"
    published = (
        _run(
            ["git", "show-ref", "--verify", "--quiet", head_ref],
            timeout=30,
            cwd=root,
        ).returncode
        == 0
    )
    unpushed = ahead
    if published:
        unpushed_text = _required_output(
            ["git", "rev-list", "--count", f"origin/{head}..HEAD"],
            root,
            "未 push commit",
        )
        try:
            unpushed = int(unpushed_text)
        except ValueError as exc:
            raise GitOpsError("未 push commit の件数が不正です。") from exc
    return PullRequestPreflight(
        head, base, ahead, changed_files, published, unpushed, origin_repo
    )


def load_pull_request_template(repo_root: Path) -> str:
    """repository root の既定 PR template を読み込む。"""
    path = Path(repo_root) / ".github" / "pull_request_template.md"
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else ""
    except (OSError, UnicodeError):
        return ""
