"""System-boundary tests for post-integration cleanup.

The tests deliberately drive only the installed command-line toolkit and inspect
Git, files, and run reports.  Application modules are not imported, so the
acceptance criteria remain the oracle.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[3]
RID = "209901020304"


def run(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run(
        list(args), cwd=cwd, env=env, text=True, encoding="utf-8",
        errors="replace", capture_output=True,
    )
    if check and proc.returncode:
        raise AssertionError(f"{args} -> {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    return proc


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(repo, "git", *args, check=check)


@pytest.fixture()
def installed_repo(tmp_path: Path) -> Path:
    """Install the shipping artifact into a consumer repository."""
    repo = tmp_path / "consumer repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "system-test@example.invalid")
    git(repo, "config", "user.name", "System Test")
    (repo / "README.md").write_text("consumer-owned\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "consumer baseline")
    run(repo, sys.executable, str(SOURCE / "tools" / "install.py"),
        "--target", str(repo), "--skip-verify")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "install EABK")
    return repo


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def seed_run(repo: Path, *, result: str = "全件完了", milestones: int = 6) -> tuple[Path, Path]:
    """Create externally observable run records and one run-owned worktree."""
    run_dir = repo / "work" / "runs" / RID
    run_dir.mkdir(parents=True, exist_ok=True)
    integration = f"run/{RID}"
    worker = f"work/{RID}/I-01"
    git(repo, "branch", integration)
    worktree = repo / "work" / "worktrees" / f"{RID}-w1"
    git(repo, "worktree", "add", "-q", "-b", worker, str(worktree), integration)
    (worktree / "owned.tmp").write_text("run-owned\n", encoding="utf-8")
    git(worktree, "add", "owned.tmp")
    git(worktree, "commit", "-q", "-m", "run work")
    git(repo, "merge", "--no-ff", "-q", "-m", "integrate work", worker)
    meta = {
        "run_id": RID,
        "status": "finished",
        "result": result,
        "integration_branch": integration,
        "stages_done": [1, 2, 3, 4, 5, 6],
        # Ordered, structured results required by AC-057.  A prefix represents
        # interruption at that boundary and must never authorize cleanup.
        "completion_milestones": [
            {"name": "complete-check", "exit_code": 0},
            {"name": "final-verify", "exit_code": 0},
            {"name": "target-system-tests", "exit_code": 0},
            {"name": "main-integration", "status": "success", "commit": git(repo, "rev-parse", "HEAD").stdout.strip()},
            {"name": "post-integration-verify", "exit_code": 0},
            {"name": "pre-cleanup-report", "status": "finalized"},
        ][:milestones],
    }
    write_json(run_dir / "meta.json", meta)
    write_json(run_dir / "queue.json", {
        "run_id": RID,
        "items": [{"id": "I-01", "status": "done", "branch": worker, "worktree": str(worktree)}],
    })
    (run_dir / "run-report.md").write_text(
        "# run-report\n\n"
        f"- result: {result}\n"
        f"- main_commit: {meta['completion_milestones'][3]['commit'] if milestones > 3 else '-'}\n"
        "- complete_check: pass\n- final_verify: pass\n- target_tests: pass\n"
        "- main_integration: pass\n- cleanup_authorization: pass\n"
        "- 清掃前版 run-report 確定: pass\n"
        "- post_integration_verify: pass\n- cleanup_candidates:\n"
        f"  - {worktree}\n- protected_assets: []\n- candidate_results: pending\n",
        encoding="utf-8",
    )
    return run_dir, worktree


def cleanup(repo: Path, *, dry_run: bool = False) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, "scripts/clean-work.py", "--root", str(repo), "--days", "-1"]
    if dry_run:
        args.append("--dry-run")
    return run(repo, *args, check=False)


def report_for(repo: Path) -> str:
    reports = list(repo.glob(f"**/{RID}/run-report.md"))
    assert reports, "cleanup must retain the diagnostic run-report"
    return reports[0].read_text(encoding="utf-8")


# FR-1009 AC-057
def test_cleanup_starts_only_after_ordered_success_and_pre_cleanup_report(installed_repo: Path) -> None:
    _, worktree = seed_run(installed_repo, milestones=5)
    assert cleanup(installed_repo).returncode == 0
    assert worktree.exists(), "missing pre-cleanup report must retain run-owned assets"

    # Reaching the sixth ordered milestone is the first point at which cleanup
    # may start; an arbitrary "finished" value above was not sufficient.
    meta_path = installed_repo / "work" / "runs" / RID / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["completion_milestones"].append({"name": "pre-cleanup-report", "status": "finalized"})
    write_json(meta_path, meta)
    assert cleanup(installed_repo).returncode == 0
    assert not worktree.exists()


# FR-1009 AC-058
@pytest.mark.parametrize("result", [
    "blocked あり", "時間予算で中止", "canary 失敗で中止", "完了条件未達",
    "最終 verify 失敗", "対象テスト失敗", "main 統合競合",
    "main 統合失敗", "main 上 verify 失敗", "清掃前 report 不足", "清掃許可判定失敗",
])
def test_every_unsuccessful_branch_is_retained_without_expiry(installed_repo: Path, result: str) -> None:
    run_dir, worktree = seed_run(installed_repo, result=result)
    assert cleanup(installed_repo).returncode == 0
    assert run_dir.exists() and worktree.exists()
    assert result in report_for(installed_repo)


# FR-1010 AC-060
def test_report_is_finalized_before_cleanup_and_records_every_candidate_result(installed_repo: Path) -> None:
    _, worktree = seed_run(installed_repo)
    assert cleanup(installed_repo).returncode == 0
    report = report_for(installed_repo)
    required = ("全件完了", "main_commit", "complete_check", "final_verify",
                "target_tests", "post_integration_verify", "cleanup_candidates",
                "protected_assets", "candidate_results")
    assert all(term in report for term in required)
    assert str(worktree) in report
    assert re.search(r"(deleted|削除済み)", report, re.I)
    assert re.search(r"(final|最終状態|清掃済み)", report, re.I)


# NFR-OPS-005 AC-064
def test_mixed_foreign_dirty_active_root_main_and_configured_assets_are_untouched(installed_repo: Path) -> None:
    _, owned = seed_run(installed_repo)
    foreign = installed_repo.parent / "foreign-worktree"
    git(installed_repo, "worktree", "add", "-q", "-b", "user/keep", str(foreign), "main")
    (foreign / "dirty.txt").write_text("do not delete\n", encoding="utf-8")
    protected = installed_repo / "work" / "protected-by-user"
    protected.mkdir(parents=True)
    (protected / "keep.txt").write_text("protected\n", encoding="utf-8")
    config = json.loads((installed_repo / "scripts" / "ebak.config.json").read_text(encoding="utf-8"))
    config.setdefault("work", {})["protected_paths"] = [str(protected)]
    write_json(installed_repo / "scripts" / "ebak.config.json", config)
    before = git(installed_repo, "status", "--porcelain=v1", "--untracked-files=all").stdout

    assert cleanup(installed_repo).returncode == 0
    assert not owned.exists()
    assert installed_repo.exists() and foreign.exists() and protected.exists()
    assert (foreign / "dirty.txt").read_text(encoding="utf-8") == "do not delete\n"
    assert (protected / "keep.txt").read_text(encoding="utf-8") == "protected\n"
    assert git(installed_repo, "status", "--porcelain=v1", "--untracked-files=all").stdout == before


# NFR-COMPAT-001 AC-066
def test_windows_aliases_are_one_candidate_but_collisions_and_locks_are_protected(
    installed_repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows path identity is observable only on Windows")
    _, owned = seed_run(installed_repo)
    report_path = installed_repo / "work" / "runs" / RID / "run-report.md"
    aliases = [str(owned), str(owned).upper(), str(owned).replace("\\", "/")]
    with report_path.open("a", encoding="utf-8") as stream:
        stream.write("\n".join(f"- cleanup_candidate: {value}" for value in aliases) + "\n")
    locked = owned / "locked file.txt"
    locked.write_text("locked\n", encoding="utf-8")
    with locked.open("r+b"):
        proc = cleanup(installed_repo)
    assert proc.returncode != 0
    report = report_for(installed_repo)
    assert report.count("candidate") >= 1
    assert re.search(r"(lock|ロック).*(retain|保持)", report, re.I | re.S)
    assert owned.exists(), "a locked or identity-conflicting candidate must not be deleted"


# NFR-COMPAT-001 AC-067
def test_shipping_catalog_agent_and_guides_publish_one_cleanup_contract(installed_repo: Path) -> None:
    required_files = (
        "scripts/clean-work.py", "scripts/run-state.py", "scripts/integrate.py",
        ".github/agents/conductor.agent.md",
    )
    assert all((installed_repo / rel).is_file() for rel in required_files)
    manifest = json.loads((installed_repo / ".github" / "ebak-toolkit.json").read_text(encoding="utf-8"))
    assert all(rel in manifest["files"] for rel in required_files)
    texts = [
        (SOURCE / "docs" / "catalog.md").read_text(encoding="utf-8"),
        (SOURCE / ".github" / "agents" / "conductor.agent.md").read_text(encoding="utf-8"),
        *[p.read_text(encoding="utf-8") for p in (SOURCE / "users-guide").glob("*.md")],
    ]
    combined = "\n".join(texts)
    assert "main" in combined and "全件完了" in combined and "統合後" in combined
    assert "清掃前" in combined and "清掃後" in combined
    assert re.search(r"(期限を設けず|自動期限なく).{0,80}保持", combined, re.S)


# NFR-COMPAT-001 AC-068
def test_cleanup_preserves_unrelated_diff_and_all_final_verifiers_exit_zero(installed_repo: Path) -> None:
    _, _ = seed_run(installed_repo)
    unrelated = installed_repo / "consumer-note.txt"
    unrelated.write_text("unrelated user change\n", encoding="utf-8")
    before = unrelated.read_bytes()
    assert cleanup(installed_repo).returncode == 0
    assert unrelated.read_bytes() == before
    assert run(installed_repo, sys.executable, "scripts/verify.py", "--docs-only", check=False).returncode == 0
    # --strict would also judge the whole toolkit's own requirements (ledger
    # cases for unrelated ACs), which are absent in this minimal consumer repo.
    assert run(installed_repo, sys.executable, "scripts/verify.py", check=False).returncode == 0
    # The final report must name the cleanup-target test command and its zero exit.
    assert re.search(r"(cleanup.*test|清掃対象テスト).*(exit[_ ]?code[:= ]+0|pass)",
                     report_for(installed_repo), re.I | re.S)
