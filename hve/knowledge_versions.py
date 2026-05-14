"""knowledge_versions.py — knowledge/ 参照ファイルの commit SHA 可視化モジュール。

Phase B4: Step 実行時に参照する knowledge ファイル群の commit SHA を収集・可視化する。
収集結果はプロンプトへの埋め込み・コンソールログ・テンプレートプレースホルダ展開に利用する。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 内部ユーティリティ
# ---------------------------------------------------------------------------


def _run_git(repo_root: Path, args: List[str]) -> str:
    """git コマンドを実行してその標準出力を返す。エラー時は空文字列を返す。"""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _latest_commit_for_path(repo_root: Path, path: str, revision: Optional[str] = None) -> str:
    """path に最後に触れた commit SHA を返す。なければ空文字列。"""
    cmd = ["log", "-1", "--format=%H"]
    if revision:
        cmd.append(revision)
    cmd.extend(["--", path])
    return _run_git(repo_root, cmd)


def _is_tracked_in_index(repo_root: Path, path: str) -> bool:
    """path が git index に登録されているか（add 済み）確認する。"""
    out = _run_git(repo_root, ["ls-files", "--", path])
    return bool(out)


def _resolve_previous_revision(repo_root: Path) -> Optional[str]:
    """HEAD~1 の SHA を返す。なければ None。"""
    previous = _run_git(repo_root, ["rev-parse", "--verify", "HEAD~1"])
    return previous or None


# ---------------------------------------------------------------------------
# パブリック API
# ---------------------------------------------------------------------------


def collect_knowledge_file_shas(
    paths: List[str],
    repo_root: Path,
) -> List[Dict[str, str]]:
    """knowledge ファイルのパスリストから commit SHA を収集して返す。

    各エントリは以下のキーを持つ dict:
        path      : ファイルパス（正規化済み、前方スラッシュ）
        sha       : 最新 commit の完全 SHA。コミット未済・未追跡の場合は "-"
        short_sha : SHA の先頭 7 文字。SHA が "-" の場合は "-"
        status    : "tracked" | "staged" | "untracked" | "missing"
        note      : "updated（更新あり）" | "unchanged（更新なし）" |
                    "comparison unavailable（比較対象なし）" | "-"

    Args:
        paths     : 収集対象のファイルパスリスト。
        repo_root : git リポジトリルートへの Path。
    """
    previous_revision = _resolve_previous_revision(repo_root)
    entries: List[Dict[str, str]] = []

    for raw_path in paths:
        path = raw_path.replace("\\", "/")
        abs_path = repo_root / path

        if not abs_path.exists():
            entries.append({
                "path": path,
                "sha": "-",
                "short_sha": "-",
                "status": "missing",
                "note": "-",
            })
            continue

        commit_sha = _latest_commit_for_path(repo_root, path)
        if not commit_sha:
            # ファイルは存在するが git にコミット履歴がない
            is_indexed = _is_tracked_in_index(repo_root, path)
            status = "staged" if is_indexed else "untracked"
            entries.append({
                "path": path,
                "sha": "-",
                "short_sha": "-",
                "status": status,
                "note": "-",
            })
            continue

        short_sha = commit_sha[:7]

        # 更新有無の判定（HEAD~1 との比較）
        if not previous_revision:
            note = "comparison unavailable（比較対象なし）"
        else:
            prev_commit = _latest_commit_for_path(repo_root, path, revision=previous_revision)
            if not prev_commit:
                note = "comparison unavailable（比較対象なし）"
            elif prev_commit == commit_sha:
                note = "unchanged（更新なし）"
            else:
                note = "updated（更新あり）"

        entries.append({
            "path": path,
            "sha": commit_sha,
            "short_sha": short_sha,
            "status": "tracked",
            "note": note,
        })

    return entries


def resolve_knowledge_paths_for_step(
    step: object,
    existing_artifacts: dict,
    repo_root: Path,
) -> List[str]:
    """ステップが参照する knowledge ファイルのパスリストを解決する。

    決定方法（優先順）:
      A. consumed_artifacts に "knowledge" キーが含まれ、existing_artifacts にも
         "knowledge" が存在する場合 → existing_artifacts["knowledge"] を使用
      B. consumed_artifacts が None（後方互換）かつ existing_artifacts に "knowledge" がある場合
         → existing_artifacts["knowledge"] を使用
      C. consumed_artifacts が None かつ existing_artifacts に "knowledge" がない場合
         → repo_root / knowledge/*.md を直接 glob
      D. consumed_artifacts が [] または "knowledge" を含まない場合
         → [] （このステップは knowledge を参照しない）

    Returns:
        knowledge ファイルパスのリスト。参照なしの場合は空リスト。
    """
    consumed = getattr(step, "consumed_artifacts", None)

    if consumed is not None:
        # 明示的にアノテーション済み
        if "knowledge" not in consumed:
            return []
        knowledge_paths = existing_artifacts.get("knowledge", [])
        if isinstance(knowledge_paths, str):
            knowledge_paths = [knowledge_paths]
        else:
            knowledge_paths = list(knowledge_paths)
        # existing_artifacts に knowledge が登録されていない場合は glob にフォールバック
        if not knowledge_paths:
            knowledge_dir = repo_root / "knowledge"
            if knowledge_dir.is_dir():
                return [
                    str(p.relative_to(repo_root)).replace("\\", "/")
                    for p in sorted(knowledge_dir.glob("*.md"))
                ]
        return knowledge_paths

    # consumed_artifacts is None: 後方互換モード
    knowledge_paths = existing_artifacts.get("knowledge")
    if knowledge_paths:
        if isinstance(knowledge_paths, str):
            return [knowledge_paths]
        return list(knowledge_paths)

    # repo_root 直下の knowledge/*.md を直接 glob（fallback）
    knowledge_dir = repo_root / "knowledge"
    if knowledge_dir.is_dir():
        return [
            str(p.relative_to(repo_root)).replace("\\", "/")
            for p in sorted(knowledge_dir.glob("*.md"))
        ]
    return []


def build_knowledge_reference_section(
    entries: List[Dict[str, str]],
    has_knowledge_context: bool = True,
) -> str:
    """knowledge 参照バージョンの Markdown セクション文字列を返す。

    Args:
        entries              : collect_knowledge_file_shas() が返すエントリリスト。
        has_knowledge_context: True = knowledge を参照するステップ。
                               False = knowledge を参照しないステップ（"none" 明示）。

    Returns:
        Markdown 形式のセクション文字列。
    """
    if not has_knowledge_context or not entries:
        return "## 参照 knowledge 版数\n\nknowledge references: none"

    def _esc(value: str) -> str:
        return value.replace("|", "\\|")

    lines = [
        "## 参照 knowledge 版数",
        "",
        "| path | short_sha | status | note |",
        "|---|---|---|---|",
    ]
    for entry in entries:
        lines.append(
            f"| {_esc(entry['path'])} | {_esc(entry['short_sha'])} | {_esc(entry['status'])} | {_esc(entry['note'])} |"
        )

    return "\n".join(lines)


def build_knowledge_reference_log_lines(
    entries: List[Dict[str, str]],
) -> List[str]:
    """コンソール／ログ用の出力行リストを返す。

    Returns:
        文字列リスト。各行はログ出力に適した形式。参照なしの場合は 1 行のみ。
    """
    if not entries:
        return ["knowledge references: none"]

    lines: List[str] = []
    for entry in entries:
        lines.append(
            f"  {entry['path']}: {entry['short_sha']} ({entry['status']}) [{entry['note']}]"
        )
    return lines
