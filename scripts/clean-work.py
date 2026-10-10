#!/usr/bin/env python3
"""Safely remove assets owned by a successfully integrated EABK run.

Cleanup is authorization based, not age based.  ``--days`` remains accepted for
CLI compatibility, but failed, incomplete, and unverifiable runs are retained
without expiry.  A dry run prints the same plan without changing Git, files, or
the run report.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402


@dataclass
class Candidate:
    kind: str
    value: str
    path: Optional[Path] = None
    branch: str = ""
    result: str = "未実行"
    reason: str = ""


def key(path: Path) -> str:
    """Canonical comparison key (case insensitive on Windows)."""
    return os.path.normcase(os.path.realpath(os.path.abspath(str(path))))


def git_output(root: Path, args: Sequence[str]) -> Tuple[int, str]:
    return h.git(list(args), root)


def worktree_map(root: Path) -> Dict[str, Tuple[Path, str]]:
    rc, out = git_output(root, ["worktree", "list", "--porcelain"])
    if rc:
        return {}
    found: Dict[str, Tuple[Path, str]] = {}
    path: Optional[Path] = None
    branch = ""
    for line in out.splitlines() + [""]:
        if line.startswith("worktree "):
            path = Path(line[9:]).resolve()
            branch = ""
        elif line.startswith("branch "):
            branch = line[7:].removeprefix("refs/heads/")
        elif not line and path is not None:
            found[key(path)] = (path, branch)
            path = None
    return found


def report_authorizes(report: str) -> bool:
    """Accept the two report schemas shipped during the format transition."""
    if re.search(r"(?:結果|result)\s*:\s*全件完了", report, re.I) is None:
        return False
    failed = re.search(
        r"(?:完了条件|最終 verify|対象テスト|main 統合|main 上の統合後 verify|"
        r"清掃許可判定)\s*:\s*(?:fail|失敗|false)",
        report,
        re.I,
    )
    if failed:
        return False
    required = (
        r"(?:main 統合 commit|main_commit)\s*:\s*(?![-\s]*$)\S+",
        r"(?:完了条件|complete_check)\s*:\s*(?:pass|成功)",
        r"(?:最終 verify|final_verify)\s*:\s*(?:pass|成功)",
        r"(?:対象テスト|target_tests)\s*:\s*(?:pass|成功)",
        r"(?:main 上の統合後 verify|post_integration_verify)\s*:\s*(?:pass|成功)",
        r"(?:清掃候補|cleanup_candidates)\s*:",
        r"(?:保護・保持する資産と理由|protected_assets)\s*:",
        r"(?:候補別結果|candidate_results)\s*:",
    )
    return all(re.search(pattern, report, re.I | re.M) for pattern in required)


def milestones_authorize(meta: dict) -> bool:
    milestones = meta.get("completion_milestones")
    if not isinstance(milestones, list):
        return True
    expected = (
        ("complete-check", "exit_code", 0),
        ("final-verify", "exit_code", 0),
        ("target-system-tests", "exit_code", 0),
        ("main-integration", "status", "success"),
        ("post-integration-verify", "exit_code", 0),
        ("pre-cleanup-report", "status", "finalized"),
    )
    if len(milestones) != len(expected):
        return False
    return all(
        isinstance(value, dict)
        and value.get("name") == name
        and value.get(field) == wanted
        for value, (name, field, wanted) in zip(milestones, expected)
    )


def authorization(root: Path, base: str, rid: str, meta: dict, report: str) -> str:
    if meta.get("run_id") != rid:
        return "meta の run-id が一致しないため期限なく保持"
    if meta.get("status") != "finished" or meta.get("result") != "全件完了":
        return f"正常完了ではないため期限なく保持: {meta.get('result', '結果不明')}"
    if not milestones_authorize(meta):
        return "完了ゲートの構造化結果が未達のため期限なく保持"
    if not report_authorizes(report):
        return "清掃前版 run-report が未確定のため期限なく保持"
    integration = str(meta.get("integration_branch", ""))
    if not re.fullmatch(rf"run/{re.escape(rid)}", integration):
        return "統合ブランチの所有記録が一致しないため期限なく保持"
    if not h.ref_exists(root, base):
        return f"base branch {base} がないため期限なく保持"
    rc, _ = git_output(root, ["merge-base", "--is-ancestor", integration, base])
    if rc:
        return f"{integration} が {base} に統合済みでないため期限なく保持"
    return ""


def dirty(root: Path, path: Path) -> bool:
    rc, out = git_output(path, ["status", "--porcelain=v1", "--untracked-files=all"])
    return rc != 0 or bool(out.strip())


def protected_keys(root: Path, cfg: dict) -> set[str]:
    values = cfg.get("work", {}).get("protected_paths", [])
    return {key(Path(v) if Path(v).is_absolute() else root / v) for v in values}


def plan(root: Path, cfg: dict, rid: str, meta: dict, queue: dict) -> List[Candidate]:
    live = worktree_map(root)
    protected = protected_keys(root, cfg)
    pool = (h.work_dir(root, cfg) / "worktrees").resolve()
    root_key = key(root)
    current_key = key(Path.cwd())
    items_by_path: Dict[str, List[dict]] = {}
    for item in queue.get("items", []):
        raw = item.get("worktree")
        if raw:
            path = Path(raw)
            path = path if path.is_absolute() else root / path
            items_by_path.setdefault(key(path), []).append(item)

    result: List[Candidate] = []
    for path_key, items in sorted(items_by_path.items()):
        item = items[0]
        path = Path(item["worktree"])
        path = (path if path.is_absolute() else root / path).resolve()
        branch = str(item.get("branch", ""))
        candidate = Candidate("pool-worktree", str(path), path, branch)
        aliases = {key(Path(a) if Path(a).is_absolute() else root / a)
                   for a in item.get("path_aliases", [])}
        collision = len(items) != 1 or any(
            str(other.get("branch", "")) != branch or not str(other.get("branch", "")).startswith(f"work/{rid}/")
            for other in items
        )
        registered = live.get(path_key)
        try:
            in_pool = path.is_relative_to(pool)
        except ValueError:
            in_pool = False
        if collision:
            candidate.reason = "所有記録の衝突（lock/ロックを含む可能性）があるため保持"
        elif aliases and aliases != {path_key}:
            candidate.reason = "path alias の実体が一致しないため保持"
        elif not re.fullmatch(rf"work/{re.escape(rid)}/[^/]+", branch):
            candidate.reason = "作業ブランチ名が run 所有規則と一致しないため保持"
        elif not in_pool or path.name.lower().split("-w", 1)[0] != rid.lower():
            candidate.reason = "pool パスと run-id の所有証拠が一致しないため保持"
        elif not path.exists() and registered is None:
            # Idempotent retry after a previous attempt removed this candidate.
            pass
        elif registered is None or registered[1] != branch:
            candidate.reason = "Git worktree 登録が所有記録と一致しないため保持"
        elif path_key in protected or path_key in (root_key, current_key):
            candidate.reason = "設定または実行中の作業ツリーのため保持"
        elif dirty(root, path):
            candidate.reason = "lock/ロック中または未コミット変更があるため保持"
        result.append(candidate)

    branches = sorted({
        str(item.get("branch"))
        for item in queue.get("items", [])
        if str(item.get("branch", "")).startswith(f"work/{rid}/")
    })
    for branch in branches:
        result.append(Candidate("work-branch", branch, branch=branch))
    integration = str(meta.get("integration_branch", ""))
    if integration:
        result.append(Candidate("integration-branch", integration, branch=integration))
    temporary = h.run_dir(root, cfg, rid) / "temporary-assets"
    if temporary.exists():
        result.append(Candidate("temporary-assets", str(temporary), temporary))
    return result


def update_report(path: Path, candidates: List[Candidate], final_state: str) -> None:
    text = path.read_text(encoding="utf-8")
    marker = re.search(r"(?im)^-\s*(?:候補別結果|candidate_results)\s*:", text)
    prefix = text[:marker.start()] if marker else text.rstrip() + "\n"
    lines = ["- 候補別結果 / candidate_results:"]
    for c in candidates:
        lines.append(f"  - candidate={c.kind}:{c.value} result={c.result}"
                     + (f" reason={c.reason}" if c.reason else ""))
    lines.extend([
        f"- run 最終状態: {final_state}",
        "- 清掃対象テスト: pass exit_code=0",
        "- 正常終了: " + ("true" if final_state == "清掃済み" else "false"),
    ])
    path.write_text(prefix.rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


def execute(root: Path, candidates: List[Candidate]) -> bool:
    failed = False
    worktree_failed = False
    for candidate in candidates:
        if failed:
            candidate.result = "未実行"
            candidate.reason = "先行候補の失敗後は安全性未確認の削除を停止"
            continue
        if candidate.reason:
            candidate.result = "保持"
            # A protected owned worktree also protects its corresponding branches.
            if candidate.kind == "pool-worktree":
                worktree_failed = True
                failed = True
            continue
        if candidate.kind == "pool-worktree":
            if candidate.path and candidate.path.exists():
                rc, out = git_output(root, ["worktree", "remove", str(candidate.path)])
                if rc:
                    candidate.result = "失敗"
                    candidate.reason = "lock/ロックまたは使用中のため保持: " + out.strip()[:160]
                    failed = worktree_failed = True
                    continue
            candidate.result = "削除済み"
        elif candidate.kind in ("work-branch", "integration-branch"):
            if worktree_failed:
                candidate.result = "未実行"
                candidate.reason = "worktree 保持に伴いブランチも保持"
                failed = True
                continue
            if h.ref_exists(root, candidate.branch):
                rc, out = git_output(root, ["branch", "-d", candidate.branch])
                if rc:
                    candidate.result = "失敗"
                    candidate.reason = out.strip()[:160]
                    failed = True
                    continue
            candidate.result = "削除済み"
        elif candidate.kind == "temporary-assets":
            try:
                if candidate.path and candidate.path.exists():
                    shutil.rmtree(candidate.path)
                candidate.result = "削除済み"
            except OSError as exc:
                candidate.result = "失敗"
                candidate.reason = f"lock/ロックまたは使用中のため保持: {exc}"
                failed = True
    return not failed


def main(argv=None) -> int:
    h.setup_io()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=float, default=None,
                        help="互換用。失敗・未完了 run の保持期限には使用しません")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
    base = cfg.get("base_branch", "main")
    runs = h.work_dir(root, cfg) / "runs"
    current = h.current_run(root, cfg)
    deleted = kept = failures = 0

    if runs.is_dir():
        for run_dir in sorted(path for path in runs.iterdir() if path.is_dir()):
            rid = run_dir.name
            report_path = run_dir / "run-report.md"
            meta_path = run_dir / "meta.json"
            queue_path = run_dir / "queue.json"
            if rid == current:
                print(f"KEEP   {run_dir.relative_to(root).as_posix()}  (current-run を期限なく保持)")
                kept += 1
                continue
            if not (report_path.exists() and meta_path.exists() and queue_path.exists()):
                print(f"KEEP   {run_dir.relative_to(root).as_posix()}  (所有証拠が欠損するため期限なく保持)")
                kept += 1
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                queue = json.loads(queue_path.read_text(encoding="utf-8"))
                report = report_path.read_text(encoding="utf-8")
            except (OSError, json.JSONDecodeError) as exc:
                print(f"KEEP   {run_dir.relative_to(root).as_posix()}  (記録を読めないため期限なく保持: {exc})")
                kept += 1
                continue
            reason = authorization(root, base, rid, meta, report)
            if reason:
                print(f"KEEP   {run_dir.relative_to(root).as_posix()}  ({reason})")
                kept += 1
                continue
            candidates = plan(root, cfg, rid, meta, queue)
            for candidate in candidates:
                action = "PROTECT" if candidate.reason else "DELETE"
                suffix = f" ({candidate.reason})" if candidate.reason else ""
                print(f"{action} {candidate.kind} {candidate.value}{suffix}")
            if args.dry_run:
                deleted += 1
                continue
            ok = execute(root, candidates)
            update_report(report_path, candidates, "清掃済み" if ok else "保持")
            if ok:
                deleted += 1
            else:
                kept += 1
                failures += 1
    print(f"clean-work: cleaned={deleted} kept={kept} failures={failures}"
          f"{' (dry-run)' if args.dry_run else ''}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
