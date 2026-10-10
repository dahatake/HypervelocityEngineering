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


# NFR-COMPAT-001 AC-066
def test_canonical_key_collapses_path_spelling_aliases(tmp_path):
    spaced = tmp_path / "path with spaces"
    spaced.mkdir()
    assert clean_work.key(spaced) == clean_work.key(spaced / ".")
