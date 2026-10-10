"""Unit-level contract checks for safe run cleanup."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "clean-work.py"
SPEC = importlib.util.spec_from_file_location("clean_work", SCRIPT)
assert SPEC and SPEC.loader
clean_work = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = clean_work
SPEC.loader.exec_module(clean_work)


# FR-1009 AC-057
def test_report_authorization_requires_every_success_gate():
    report = """- result: 全件完了
    - main_integration: pass
    - cleanup_authorization: pass
    - main_commit: abc
- complete_check: pass
- final_verify: pass
- target_tests: pass
- post_integration_verify: pass
- cleanup_candidates:
- protected_assets:
- candidate_results: pending
"""
    assert clean_work.report_authorizes(report)
    assert not clean_work.report_authorizes(report.replace("final_verify: pass", "final_verify: fail"))


# FR-1009 AC-057 / FR-1010 AC-062
def test_structured_milestones_are_ordered_and_exact():
    milestones = [
        {"name": "complete-check", "exit_code": 0},
        {"name": "final-verify", "exit_code": 0},
        {"name": "target-system-tests", "exit_code": 0},
        {"name": "main-integration", "status": "success"},
        {"name": "post-integration-verify", "exit_code": 0},
        {"name": "pre-cleanup-report", "status": "finalized"},
    ]
    assert clean_work.milestones_authorize({"completion_milestones": milestones})
    assert not clean_work.milestones_authorize({"completion_milestones": milestones[:-1]})
    assert not clean_work.milestones_authorize({})


# FR-1009 AC-057 / FR-1010 AC-060
def test_current_run_marker_protects_active_but_not_finished_run():
    assert clean_work.protects_current_run("20261010", "20261010", {"status": "active"})
    assert not clean_work.protects_current_run("20261010", "20261010", {"status": "finished"})
    assert not clean_work.protects_current_run("20261010", "other", {"status": "active"})


# NFR-COMPAT-001 AC-066
def test_canonical_key_collapses_path_spelling_aliases(tmp_path):
    spaced = tmp_path / "path with spaces"
    spaced.mkdir()
    assert clean_work.key(spaced) == clean_work.key(spaced / ".")


# FR-1009 AC-059 / NFR-OPS-005 AC-063
def test_plan_requires_all_ownership_evidence_and_never_uses_prefix_alone(tmp_path, monkeypatch):
    root = tmp_path
    worktree = root / "work" / "worktrees" / "209901010101-w1"
    worktree.mkdir(parents=True)
    monkeypatch.setattr(clean_work, "worktree_map", lambda _root: {})
    queue = {
        "run_id": "different-run",
        "items": [{
            "branch": "work/209901010101/I-01",
            "worktree": str(worktree),
        }],
    }
    candidates = clean_work.plan(
        root, {"work": {"dir": "work"}}, "209901010101",
        {"integration_branch": ""}, queue,
    )
    branch = next(c for c in candidates if c.kind == "work-branch")
    assert branch.result == "未実行"
    assert "worktree" in branch.reason


# FR-1010 AC-061
def test_protected_candidate_is_distinct_from_failed_deletion(tmp_path):
    protected = clean_work.Candidate("pool-worktree", "owned", reason="dirty")
    ok, had_protected = clean_work.execute(
        tmp_path, {"work_dir": "work"}, "209901010101",
        {}, {"run_id": "209901010101", "items": []}, "", [protected],
    )
    assert ok and had_protected
    assert protected.result == "保持"


# FR-1010 AC-061
def test_deletion_error_stops_later_candidates_and_is_not_protection(tmp_path, monkeypatch):
    path = tmp_path / "work" / "worktrees" / "209901010101-w1"
    path.mkdir(parents=True)
    worktree = clean_work.Candidate(
        "pool-worktree", str(path), path, "work/209901010101/I-01"
    )
    later = clean_work.Candidate("integration-branch", "run/209901010101")
    monkeypatch.setattr(
        clean_work, "plan",
        lambda *_args, **_kwargs: [worktree, later],
    )
    monkeypatch.setattr(
        clean_work, "git_output",
        lambda *_args, **_kwargs: (1, "simulated delete failure"),
    )
    ok, had_protected = clean_work.execute(
        tmp_path, {}, "209901010101", {}, {}, "", [worktree, later],
    )
    assert not ok and not had_protected
    assert worktree.result == "失敗"
    assert later.result == "未実行"


# FR-1010 AC-062
def test_retry_accepts_missing_asset_only_with_matching_success_record(tmp_path, monkeypatch):
    root = tmp_path
    path = root / "work" / "worktrees" / "209901010101-w1"
    monkeypatch.setattr(clean_work, "worktree_map", lambda _root: {})
    queue = {
        "run_id": "209901010101",
        "items": [{"branch": "work/209901010101/I-01", "worktree": str(path)}],
    }
    without = clean_work.plan(root, {"work": {"dir": "work"}}, "209901010101",
                              {"integration_branch": ""}, queue)
    assert next(c for c in without if c.kind == "pool-worktree").reason
    previous = {("pool-worktree", str(path)): "削除済み"}
    with_record = clean_work.plan(root, {"work": {"dir": "work"}}, "209901010101",
                                 {"integration_branch": ""}, queue, previous)
    assert not next(c for c in with_record if c.kind == "pool-worktree").reason


# NFR-OPS-005 AC-065
def test_execute_rechecks_each_candidate_immediately_before_delete(tmp_path, monkeypatch):
    calls = []
    candidate = clean_work.Candidate("temporary-assets", str(tmp_path / "gone"))

    def changed(*_args, **_kwargs):
        calls.append(True)
        return [clean_work.Candidate(
            candidate.kind, candidate.value, reason="state changed"
        )]

    monkeypatch.setattr(clean_work, "plan", changed)
    ok, protected = clean_work.execute(
        tmp_path, {}, "209901010101", {}, {}, "", [candidate],
    )
    assert calls and ok and protected
    assert candidate.result == "保持" and candidate.reason == "state changed"
