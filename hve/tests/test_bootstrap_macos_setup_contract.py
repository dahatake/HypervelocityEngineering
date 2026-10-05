"""FR-LOCAL-SURFACE-04: distribution-only setup verifier ownership."""
from __future__ import annotations

from pathlib import Path

import pytest

from hve.tests import test_dev_task_environment_contract as setup_contract


@pytest.mark.parametrize(
    "distribution,args,verifier_exit,expected_calls",
    [
        (True, (), 0, 1),
        (True, (), 10, 1),
        (True, (), 11, 1),
        (True, (), 12, 1),
        (True, (), 2, 1),
        (False, (), 12, 0),
        (True, ("--check-only",), 12, 0),
        (True, ("--no-gui",), 12, 0),
        (True, ("--minimal",), 12, 0),
    ],
)
def test_setup_final_verifier_once_only_for_normal_distribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, distribution: bool,
    args: tuple[str, ...], verifier_exit: int, expected_calls: int,
) -> None:
    original_write = setup_contract._write_executable

    def write_fake(path: Path, content: str) -> None:
        if path.name == "python":
            assert content.endswith("exit 0\n")
            content = content[:-len("exit 0\n")] + (
                'if [[ "${1:-}" == -I && "${2:-}" == -m && "${3:-}" == hve.bootstrap_verify ]]; then\n'
                f"  printf '{{\"state\":\"{'ready' if verifier_exit == 0 else 'blocked'}\"}}\\n'\n"
                f"  exit {verifier_exit}\nfi\nexit 0\n"
            )
            if distribution:
                manifest = path.parents[2] / "hve-bootstrap-manifest.json"
                manifest.write_text("{}\n", encoding="utf-8")
        original_write(path, content)

    monkeypatch.setattr(setup_contract, "_write_executable", write_fake)
    run = setup_contract._run_shell_setup(
        tmp_path, args=args, gh_available=True, pty_available=True,
    )
    assert (run.returncode == 0) is (expected_calls == 0 or verifier_exit == 0), setup_contract._run_summary("distribution setup", run)
    calls = [call for call in run.calls if "hve.bootstrap_verify" in call]
    assert len(calls) == expected_calls
    if calls:
        assert calls[0][1:4] == ("-I", "-m", "hve.bootstrap_verify")
        assert calls[0][4] == "--root"
        assert calls[0][5].replace("\\", "/").endswith("/repo")
        assert calls[0][6:] == ("--json",)
        assert setup_contract._has_latest_sdk_upgrade(run.calls)
        assert not setup_contract._touched_sdk_lock(run.calls)
        last_install = max(i for i, call in enumerate(run.calls) if "pip" in call and "install" in call)
        assert run.calls.index(calls[0]) > last_install
    assert not any("auth login" in call for call in run.gh_calls)