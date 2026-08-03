"""Shared pytest fixtures for the hve unit test suite.

Test isolation for the HVE run-context environment variables.

Several production code paths (``hve.orchestrator`` / ``hve.runner`` /
``hve.__main__``) assign ``HVE_RUN_ID`` (and, via the GUI/work-dir resolution,
``HVE_WORK_ROOT``) into ``os.environ`` as an intentional side effect so that
child processes inherit the current run context. When a test exercises one of
those flows it leaks those variables into the shared process environment for
every test that runs afterwards.

The ASDW data-deploy launcher and the deploy-gate/orchestrator tests read the
ambient ``HVE_RUN_ID`` / ``HVE_WORK_ROOT`` (``execute_stage`` starts from
``dict(os.environ)``). A leaked, mismatched run context makes them raise
``HVE data stage work root does not match the current run`` even though they
pass in isolation — an order-dependent, cross-test pollution failure.

This autouse fixture snapshots only those two run-context keys before each test
and restores them afterwards, so no test can leak them to another. It is scoped
to just those keys to avoid disturbing session-level environment (tokens, repo,
CI configuration) that other tests legitimately rely on.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

_HVE_RUN_CONTEXT_ENV_KEYS = ("HVE_RUN_ID", "HVE_WORK_ROOT")

# HVE evidence は `work/run/<run-id>` と `tests/run/<run-id>` の両方へ出力する。
# Step 1.3 の native pipeline を通すテストは repo 直下にこれらを作るため、
# テスト単位で新規に増えた run ディレクトリだけを除去する。
_RUN_ARTIFACT_ROOTS = ("work/run", "tests/run")


@pytest.fixture(autouse=True)
def _restore_hve_run_context_env():
    """Restore HVE run-context env vars after each test to prevent leakage."""
    saved = {key: os.environ.get(key) for key in _HVE_RUN_CONTEXT_ENV_KEYS}
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run_artifact_snapshot(repo_root: Path) -> dict[str, set[str]]:
    snapshot: dict[str, set[str]] = {}
    for relative in _RUN_ARTIFACT_ROOTS:
        base = repo_root / relative
        snapshot[relative] = (
            {entry.name for entry in base.iterdir()} if base.is_dir() else set()
        )
    return snapshot


@pytest.fixture(autouse=True)
def _remove_leaked_run_artifacts():
    """テストが repo 直下へ新規作成した run 成果物だけを除去する。

    既存の run ディレクトリ（過去実行の記録）は削除しない。
    """
    repo_root = Path(__file__).resolve().parents[2]
    before = _run_artifact_snapshot(repo_root)
    try:
        yield
    finally:
        after = _run_artifact_snapshot(repo_root)
        for relative, names in after.items():
            for name in names - before[relative]:
                shutil.rmtree(repo_root / relative / name, ignore_errors=True)
