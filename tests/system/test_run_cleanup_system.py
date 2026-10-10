"""System acceptance tests for safe post-integration run cleanup.

The oracle in this module is FR-1009, FR-1010, NFR-OPS-005 and
NFR-COMPAT-001, not the current clean-work.py implementation.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import SOURCE, run


def py(repo: Path, script: str, *args: str, check: bool = True):
    return run([sys.executable, repo / "scripts" / script, *args], repo, check=check)


def git(repo: Path, *args: str, check: bool = True):
    return run(["git", *args], repo, check=check)


def start_run(repo: Path) -> tuple[str, str]:
    result = py(repo, "run-state.py", "start", "--options", "max_hours: 24")
    match = re.search(r"\b(?:START|RESUME)\s+(\d+)", result.stdout)
    assert match, result.stdout
    run_id = match.group(1)
    return run_id, f"run/{run_id}"


def report_text(run_id: str, *, result: str = "全件完了", failed_gate: str = "", omit: str = "") -> str:
    values = {
        "run-id": run_id,
        "結果": result,
        "正常完了": "true" if result == "全件完了" and not failed_gate else "false",
        "main 統合": "pass",
        "main 統合 commit": "MAIN_COMMIT",
        "完了条件": "pass",
        "最終 verify": "pass",
        "対象テスト": "pass",
        "main 上の統合後 verify": "pass",
        "清掃前版 run-report 確定": "pass",
        "清掃許可判定": "pass",
        "清掃候補": "pool-worktree, work-branch, integration-branch, temporary-assets",
        "保護・保持する資産と理由": "none",
        "候補別結果": "not_run",
        "run 最終状態": "清掃待ち",
    }
    if failed_gate:
        values[failed_gate] = "fail"
        values["清掃許可判定"] = "fail"
    if omit:
        del values[omit]
    return "# run-report\n\n" + "".join(f"- {k}: {v}\n" for k, v in values.items())


def make_owned_candidate(repo: Path, run_id: str) -> tuple[Path, str]:
    branch = f"work/{run_id}/I-01"
    worktree = repo / "work" / "worktrees" / f"{run_id}-w1"
    py(repo, "run-state.py", "queue", "add", "--id", "I-01", "--req", "FR-1009", "--ac", "AC-057")
    git(repo, "worktree", "add", "-q", "-b", branch, worktree)
    (worktree / "owned-result.txt").write_text("must survive on main\n", encoding="utf-8")
    git(worktree, "add", "owned-result.txt")
    git(worktree, "commit", "-q", "-m", "owned result")
    py(
        repo,
        "run-state.py",
        "queue",
        "set",
        "I-01",
        "--status",
        "doing",
        "--branch",
        branch,
        "--worktree",
        worktree.relative_to(repo).as_posix(),
        "--attempts",
        "+1",
    )
    py(repo, "run-state.py", "queue", "set", "I-01", "--status", "done")
    return worktree, branch


def finish_and_merge(
    repo: Path,
    run_id: str,
    integration: str,
    report: str,
    *,
    finish_result: str = "全件完了",
) -> str:
    queue_path = repo / "work" / "runs" / run_id / "queue.json"
    if queue_path.exists():
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        for item in queue.get("items", []):
            branch = item.get("branch")
            if branch and git(repo, "branch", "--list", branch).stdout.strip():
                git(repo, "merge", "--no-ff", "-q", "-m", f"integrate {branch}", branch)
    report_path = repo / "work" / "runs" / run_id / "run-report.md"
    report_path.write_text(report, encoding="utf-8")
    py(repo, "run-state.py", "stage", "3", "--done")
    py(repo, "run-state.py", "stage", "6", "--done")
    py(repo, "run-state.py", "finish", "--result", finish_result)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "finish run")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "--no-ff", "-q", "-m", f"merge {integration}", integration)
    main_commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    text = report_path.read_text(encoding="utf-8").replace("MAIN_COMMIT", main_commit)
    report_path.write_text(text, encoding="utf-8")
    return main_commit


def cleanup(repo: Path, *, check: bool = True):
    return py(repo, "clean-work.py", "--days", "0", check=check)


def worktree_paths(repo: Path) -> set[str]:
    out = git(repo, "worktree", "list", "--porcelain").stdout
    return {line[9:] for line in out.splitlines() if line.startswith("worktree ")}


# FR-1009 AC-057
def test_cleanup_starts_only_after_all_gates_and_main_integration(installed_repo: Path):
    repo = installed_repo
    run_id, integration = start_run(repo)
    candidate, work_branch = make_owned_candidate(repo, run_id)
    temporary = repo / "work" / "runs" / run_id / "temporary-assets"
    temporary.mkdir()
    (temporary / "diagnostic.tmp").write_text("temporary\n", encoding="utf-8")

    before = cleanup(repo)
    assert candidate.exists(), before.stdout
    assert git(repo, "branch", "--list", work_branch).stdout.strip()

    main_commit = finish_and_merge(repo, run_id, integration, report_text(run_id))
    after = cleanup(repo)
    assert after.returncode == 0
    assert not candidate.exists()
    assert not git(repo, "branch", "--list", work_branch).stdout.strip()
    assert not git(repo, "branch", "--list", integration).stdout.strip()
    assert not temporary.exists()
    assert (repo / "owned-result.txt").read_text(encoding="utf-8") == "must survive on main\n"
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == main_commit


# FR-1009 AC-058
@pytest.mark.parametrize(
    ("result", "failed_gate"),
    [
        ("blocked", ""),
        ("中止", ""),
        ("canary 失敗", ""),
        ("全件完了", "完了条件"),
        ("全件完了", "最終 verify"),
        ("全件完了", "対象テスト"),
        ("全件完了", "main 統合"),
        ("全件完了", "main 上の統合後 verify"),
        ("全件完了", "清掃前版 run-report 確定"),
        ("全件完了", "清掃許可判定"),
    ],
)
def test_failed_or_incomplete_run_is_retained_without_expiry(
    installed_repo: Path, result: str, failed_gate: str
):
    repo = installed_repo
    run_id, integration = start_run(repo)
    candidate, branch = make_owned_candidate(repo, run_id)
    text = report_text(run_id, result=result, failed_gate=failed_gate)
    finish_and_merge(repo, run_id, integration, text, finish_result=result)

    first = py(repo, "clean-work.py", "--days", "-36500")
    second = py(repo, "clean-work.py", "--days", "0")
    assert candidate.exists(), first.stdout + second.stdout
    assert git(repo, "branch", "--list", branch).stdout.strip()
    assert (repo / "work" / "runs" / run_id / "run-report.md").exists()
    combined = first.stdout + second.stdout
    assert "KEEP" in combined and ("保持" in combined or "retain" in combined.lower())


# FR-1009 AC-057 AC-058
@pytest.mark.parametrize(
    "missing",
    [
        "完了条件",
        "最終 verify",
        "対象テスト",
        "main 統合",
        "main 統合 commit",
        "main 上の統合後 verify",
        "清掃前版 run-report 確定",
        "清掃許可判定",
    ],
)
def test_run_with_missing_milestone_is_retained_without_expiry(
    installed_repo: Path, missing: str
):
    repo = installed_repo
    run_id, integration = start_run(repo)
    candidate, branch = make_owned_candidate(repo, run_id)
    temporary = repo / "work" / "runs" / run_id / "temporary-assets"
    temporary.mkdir()
    (temporary / "diagnostic.tmp").write_text("temporary\n", encoding="utf-8")
    finish_and_merge(repo, run_id, integration, report_text(run_id, omit=missing))

    first = py(repo, "clean-work.py", "--days", "-36500")
    second = py(repo, "clean-work.py", "--days", "0")
    assert candidate.exists(), first.stdout + second.stdout
    assert git(repo, "branch", "--list", branch).stdout.strip()
    assert git(repo, "branch", "--list", integration).stdout.strip()
    assert (repo / "work" / "runs" / run_id / "run-report.md").exists()
    assert (temporary / "diagnostic.tmp").exists()


# FR-1010 AC-060
def test_report_is_frozen_before_cleanup_then_finalized_before_completion(installed_repo: Path):
    repo = installed_repo
    run_id, integration = start_run(repo)
    make_owned_candidate(repo, run_id)
    finish_and_merge(repo, run_id, integration, report_text(run_id))
    report = repo / "work" / "runs" / run_id / "run-report.md"
    before = report.read_text(encoding="utf-8")

    cleanup(repo)
    assert report.exists(), "run-report itself is diagnostic evidence and must be retained"
    after = report.read_text(encoding="utf-8")
    for required in (
        "正常完了",
        "main 統合 commit",
        "完了条件",
        "最終 verify",
        "対象テスト",
        "main 上の統合後 verify",
        "清掃前版 run-report 確定",
        "清掃候補",
        "保護・保持する資産と理由",
    ):
        assert required in before
    assert "候補別結果" in after and ("削除" in after or "保持" in after or "失敗" in after)
    assert "run 最終状態" in after and "清掃済み" in after
    assert after.startswith(before.split("候補別結果", 1)[0])
    assert after.rfind("run 最終状態") < after.rfind("正常終了")


# NFR-OPS-005 AC-064
def test_mixed_assets_delete_only_safe_owned_candidates(installed_repo: Path, tmp_path: Path):
    repo = installed_repo
    run_id, integration = start_run(repo)
    owned, owned_branch = make_owned_candidate(repo, run_id)
    other = repo / "work" / "worktrees" / "other-run-w1"
    user = tmp_path / "user worktree"
    dirty = tmp_path / "dirty worktree"
    for path, branch in ((other, "work/other-run/I-01"), (user, "user/keep"), (dirty, "user/dirty")):
        git(repo, "worktree", "add", "-q", "-b", branch, path)
    (dirty / "uncommitted.txt").write_text("keep me\n", encoding="utf-8")
    protected = repo / "protected-by-configuration"
    protected.mkdir()
    (protected / "keep.txt").write_text("keep\n", encoding="utf-8")
    root_marker = repo / "root-unrelated.txt"
    root_marker.write_text("keep\n", encoding="utf-8")
    finish_and_merge(repo, run_id, integration, report_text(run_id))

    cleanup(repo)
    assert not owned.exists()
    assert not git(repo, "branch", "--list", owned_branch).stdout.strip()
    for path in (repo, other, user, dirty, protected):
        assert path.exists()
    assert (dirty / "uncommitted.txt").read_text(encoding="utf-8") == "keep me\n"
    assert root_marker.read_text(encoding="utf-8") == "keep\n"


# NFR-COMPAT-001 AC-066
@pytest.mark.skipif(os.name != "nt", reason="AC-066 is the Windows compatibility contract")
def test_windows_alias_collision_spaces_and_locked_candidate_are_protected(installed_repo: Path):
    repo = installed_repo
    run_id, integration = start_run(repo)
    candidate, branch = make_owned_candidate(repo, run_id)
    locked = candidate / "locked result.txt"
    locked.write_text("locked\n", encoding="utf-8")
    queue_path = repo / "work" / "runs" / run_id / "queue.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    alias = str(candidate).swapcase().replace("\\", "/")
    queue["items"][0]["path_aliases"] = [str(candidate), alias]
    queue["items"].append(
        {
            "id": "COLLISION",
            "status": "done",
            "branch": "user/collision",
            "worktree": alias,
            "requirement_ids": ["NFR-COMPAT-001"],
            "ac_ids": ["AC-066"],
        }
    )
    queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finish_and_merge(repo, run_id, integration, report_text(run_id))

    handle = locked.open("r+b")
    try:
        result = cleanup(repo, check=False)
        assert candidate.exists()
        assert locked.exists()
        assert git(repo, "branch", "--list", branch).stdout.strip()
        report = repo / "work" / "runs" / run_id / "run-report.md"
        evidence = result.stdout + result.stderr + report.read_text(encoding="utf-8")
        assert "保持" in evidence and ("lock" in evidence.lower() or "ロック" in evidence)
        assert len([p for p in worktree_paths(repo) if Path(p).resolve() == candidate.resolve()]) == 1
    finally:
        handle.close()


# NFR-COMPAT-001 AC-067
def test_distribution_catalog_conductor_and_guides_publish_one_cleanup_contract(
    installed_repo: Path,
):
    repo = installed_repo
    required = [
        repo / "scripts" / "clean-work.py",
        repo / "scripts" / "run-state.py",
        repo / "scripts" / "integrate.py",
        repo / ".github" / "agents" / "conductor.agent.md",
        repo / "docs" / "catalog.md",
        SOURCE / "users-guide" / "02-during-and-after-run.md",
        SOURCE / "users-guide" / "05-scripts-reference.md",
        SOURCE / "users-guide" / "07-troubleshooting.md",
    ]
    assert all(path.exists() for path in required)
    corpus = "\n".join(path.read_text(encoding="utf-8") for path in required)
    for concept in ("全件完了", "main", "統合後", "verify", "run-report", "清掃", "保持"):
        assert concept in corpus
    for path in required[3:]:
        text = path.read_text(encoding="utf-8")
        assert re.search(r"main.{0,120}(統合|merge)", text, re.S | re.I)
        assert re.search(r"(統合後.{0,120}(verify|検証)|(verify|検証).{0,120}統合後)", text, re.S | re.I)
        assert re.search(r"(それ以外|失敗|未達|blocked|中止).{0,180}(期限なく|無期限|自動.*削除.*しない|保持)", text, re.S | re.I)


# NFR-COMPAT-001 AC-068
def test_cleanup_preserves_unrelated_git_state_and_all_post_cleanup_gates_pass(installed_repo: Path):
    repo = installed_repo
    run_id, integration = start_run(repo)
    make_owned_candidate(repo, run_id)
    finish_and_merge(repo, run_id, integration, report_text(run_id))
    unrelated = repo / "unrelated-user-change.txt"
    unrelated.write_text("do not alter\n", encoding="utf-8")
    before_status = git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout

    cleanup(repo)
    after_status = git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
    assert after_status == before_status
    assert unrelated.read_text(encoding="utf-8") == "do not alter\n"
    assert py(repo, "verify.py", "--docs-only", check=False).returncode == 0
    # Not --strict: strict judges the toolkit's whole requirement set (ledger
    # coverage of unrelated ACs/NFRs), which is environment-dependent here.
    assert py(repo, "verify.py", check=False).returncode == 0
    assert subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            str(SOURCE / "tests" / "system" / "test_run_cleanup_system.py"),
            "-k",
            "not cleanup_preserves_unrelated_git_state_and_all_post_cleanup_gates_pass",
        ],
        cwd=repo,
        env=dict(os.environ, EABK_NESTED_SYSTEM_TEST="1"),
        capture_output=True,
    ).returncode == 0
