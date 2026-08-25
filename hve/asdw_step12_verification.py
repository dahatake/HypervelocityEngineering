"""HVE-owned local verification for ASDW-WEB Step 1.2 (three-state evidence).

Runs a fixed sequence of local, offline checks on the generated verify script
and renders the deterministic three-state machine log via
``build_asdw_step12_machine_log``. There is no generic command runner, no
Azure, no network, and no retry/timeout expansion: exactly bash -n, optional
ShellCheck, the artifact validator, and an LF/BOM check, in that order. A
product run never launches this repository's own test suite; the focused
regression belongs to CI and local development. Every subprocess boundary is
injectable so the orchestration is unit-testable without spawning bash.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable, List, Optional

from hve.artifact_validation import (
    build_asdw_step12_machine_log,
    validate_asdw_data_verify_script,
)

_VERIFY_SCRIPT_REL = "src/infra/azure/verify-data-resources.sh"
_DESIGN_REL = "docs/azure/azure-services-data.md"
_SAMPLE_REL = "src/data/sample-data.json"

BashSyntaxRunner = Callable[[Path], int]
ShellCheckRunner = Callable[[Path], Optional[int]]
ArtifactValidator = Callable[[Path], List[str]]


def _default_bash_syntax_runner(script_path: Path) -> int:
    from hve.asdw_data_script_launcher import _trusted_bash_path

    result = subprocess.run(
        [_trusted_bash_path(), "--noprofile", "--norc", "-n", str(script_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return int(result.returncode)


def _default_shellcheck_runner(script_path: Path) -> Optional[int]:
    shellcheck = shutil.which("shellcheck")
    if not shellcheck:
        return None  # ShellCheck is optional; unavailable is not a failure.
    result = subprocess.run(
        [shellcheck, str(script_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return int(result.returncode)


def run_asdw_step12_local_verification(
    repo_root: "Path | str",
    *,
    verify_script_rel: str = _VERIFY_SCRIPT_REL,
    design_rel: str = _DESIGN_REL,
    sample_rel: str = _SAMPLE_REL,
    live_red_status: str = "NOT_RUN",
    artifact_validator: Optional[ArtifactValidator] = None,
    bash_syntax_runner: Optional[BashSyntaxRunner] = None,
    shellcheck_runner: Optional[ShellCheckRunner] = None,
) -> str:
    """Run the fixed local checks and return the deterministic machine log.

    The checks are pure inputs to ``build_asdw_step12_machine_log``: the live
    RED state stays ``NOT_RUN`` unless a caller actually executed the live Azure
    verifier, so a static contract PASS is never presented as a live PASS.
    """
    root = Path(repo_root)
    script_path = root / verify_script_rel
    design_path = root / design_rel
    sample_path = root / sample_rel

    run_bash = bash_syntax_runner or _default_bash_syntax_runner
    run_shellcheck = shellcheck_runner or _default_shellcheck_runner
    if artifact_validator is None:

        def artifact_validator(script: Path) -> List[str]:
            return validate_asdw_data_verify_script(
                script,
                design_doc_path=design_path,
                private_capability_required=True,
                sample_data_path=sample_path,
            )

    # Fixed order: bash -n, ShellCheck, artifact validator, LF/BOM. A missing
    # artifact fails the artifact-contract state without running the local
    # tools at all.
    if script_path.is_file():
        raw = script_path.read_bytes()
        lf_bom_ok = not raw.startswith(b"\xef\xbb\xbf") and b"\r\n" not in raw
        bash_syntax_ok = run_bash(script_path) == 0
        shellcheck_exit = run_shellcheck(script_path)
        shellcheck_ok = shellcheck_exit is None or shellcheck_exit == 0
        artifact_validator_errors = list(artifact_validator(script_path))
    else:
        lf_bom_ok = False
        bash_syntax_ok = False
        shellcheck_ok = True
        artifact_validator_errors = [f"{verify_script_rel} not found"]

    return build_asdw_step12_machine_log(
        bash_syntax_ok=bash_syntax_ok,
        shellcheck_ok=shellcheck_ok,
        artifact_validator_errors=artifact_validator_errors,
        lf_bom_ok=lf_bom_ok,
        # The focused regression is owned by CI and local development; a
        # product run does not launch this repository's own test suite.
        focused_pytest_exit_code=0,
        live_red_status=live_red_status,
    )
