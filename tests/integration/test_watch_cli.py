"""Integration checks for scripts/watch.py command line (FR-1064, NFR-OPS-008)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "watch.py"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)


# FR-1064 AC-357: scan never fails and changes nothing
def test_scan_exit_zero():
    assert run("scan").returncode == 0


# FR-1064 AC-359: --under empty or root is refused with exit code 2
def test_reap_under_root_refused():
    for u in ("", "/"):
        assert run("reap", "--under", u).returncode == 2


# FR-1064 AC-360: stuck exits 0 when nothing exceeds / no queue
def test_stuck_without_exceeding_items():
    r = run("stuck", "--item-minutes", "100000000")
    assert r.returncode == 0 and "STUCK" not in r.stdout
