"""Benchmark submission NFRs (NFR-PERF-001/002, NFR-REL-001).

These need a target application's measurement profile and a submission
under test (SUBMISSION_DIR). Neither is defined in the requirements yet,
so the cases are BLOCKED in the ledger; the tests fail closed until then.
"""
import os

import pytest

SUBMISSION = os.environ.get("SUBMISSION_DIR")


def _require_submission():
    if not SUBMISSION:
        pytest.fail("SUBMISSION_DIR and the app measurement profile are undefined (TBD)")


# NFR-PERF-001 AC-074
def test_public_dataset_processed_within_param_008_seconds():
    _require_submission()


# NFR-PERF-002 AC-075
def test_private_perf_case_result_recorded_separately_from_functional_result():
    _require_submission()


# NFR-REL-001 AC-076
def test_fresh_process_verify_exit_code_and_result_file_decide_completion():
    _require_submission()
