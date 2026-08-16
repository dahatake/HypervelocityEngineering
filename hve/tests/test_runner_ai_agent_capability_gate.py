"""CLI wrapper and StepRunner AI Agent capability gate tests (Sub-23)."""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner
from hve.tests.test_ai_agent_capability_validation import (
    _write_design,
    _write_implementation,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = (
    _REPO_ROOT
    / ".github"
    / "skills"
    / "ai-agent-capability-contract"
    / "scripts"
    / "validate-agent-contract.py"
)


def _runner() -> StepRunner:
    return StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_wrapper_passes_aag_and_aagd_artifacts(tmp_path: Path) -> None:
    detail = _write_design(tmp_path)
    agent_dir, test_spec = _write_implementation(tmp_path)

    aag = _run_cli(
        "--workflow",
        "aag",
        "--design",
        str(detail),
        "--json",
    )
    assert aag.returncode == 0, aag.stderr or aag.stdout
    assert json.loads(aag.stdout)["passed"] is True

    aagd = _run_cli(
        "--workflow",
        "aagd",
        "--design",
        str(detail),
        "--agent-dir",
        str(agent_dir),
        "--test-spec",
        str(test_spec),
        "--json",
    )
    assert aagd.returncode == 0, aagd.stderr or aagd.stdout
    payload = json.loads(aagd.stdout)
    assert payload == {
        "workflow": "aagd",
        "passed": True,
        "warnings": [],
        "errors": [],
    }


def test_cli_wrapper_returns_one_and_structured_errors(tmp_path: Path) -> None:
    result = _run_cli(
        "--workflow",
        "aag",
        "--design",
        str(tmp_path / "missing.md"),
        "--json",
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert payload["warnings"] == []
    assert payload["errors"]
    assert "not found" in payload["errors"][0].lower()


def test_cli_non_json_errors_use_stderr_only(tmp_path: Path) -> None:
    result = _run_cli(
        "--workflow",
        "aag",
        "--design",
        str(tmp_path / "missing.md"),
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "ERROR:" in result.stderr


def test_runner_gate_resolves_aag_fanout_target(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_validator(
        workflow_id: str,
        design_path: Path,
        *,
        agent_dir: Path | None = None,
        test_spec_path: Path | None = None,
        tool_search_policy: str = "auto",
        agentic_retrieval_policy: str = "auto",
    ) -> list[str]:
        calls.append(
            {
                "workflow": workflow_id,
                "design": design_path,
                "agent_dir": agent_dir,
                "test_spec": test_spec_path,
            }
        )
        return []

    monkeypatch.setattr(
        "hve.artifact_validation.validate_ai_agent_capability_artifacts",
        fake_validator,
    )
    errors = _runner()._run_ai_agent_capability_gate(
        "3/AG-01",
        "Arch-AIAgentDesign-Step3",
        "aag",
    )
    assert errors == []
    assert calls == [
        {
            "workflow": "aag",
            "design": tmp_path / "docs" / "agent" / "agent-detail-AG-01.md",
            "agent_dir": None,
            "test_spec": None,
        }
    ]


def test_runner_gate_resolves_aagd_fanout_target(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[tuple[object, ...]] = []

    def fake_validator(
        workflow_id: str,
        design_path: Path,
        *,
        agent_dir: Path | None = None,
        test_spec_path: Path | None = None,
        tool_search_policy: str = "auto",
        agentic_retrieval_policy: str = "auto",
    ) -> list[str]:
        calls.append((workflow_id, design_path, agent_dir, test_spec_path))
        return []

    monkeypatch.setattr(
        "hve.artifact_validation.validate_ai_agent_capability_artifacts",
        fake_validator,
    )
    errors = _runner()._run_ai_agent_capability_gate(
        "2.3/AG-02",
        "Dev-Microservice-Azure-AgentCoding",
        "aagd",
    )
    assert errors == []
    assert calls == [
        (
            "aagd",
            tmp_path / "docs" / "agent" / "agent-detail-AG-02.md",
            tmp_path / "src" / "agent" / "AG-02",
            tmp_path / "docs" / "test-specs" / "AG-02-test-spec.md",
        )
    ]


def test_runner_gate_resolves_aagd_deploy_target(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[tuple[object, ...]] = []

    def fake_deploy_validator(
        design_path: Path,
        infra_dir: Path,
        tool_search_policy: str = "auto",
        agentic_retrieval_policy: str = "auto",
    ) -> list[str]:
        calls.append(
            (design_path, infra_dir, tool_search_policy, agentic_retrieval_policy)
        )
        return []

    monkeypatch.setattr(
        "hve.artifact_validation.validate_ai_agent_deploy_artifacts",
        fake_deploy_validator,
    )
    errors = _runner()._run_ai_agent_capability_gate(
        "3/AG-03",
        "Dev-Microservice-Azure-AgentDeploy",
        "aagd",
    )
    assert errors == []
    assert calls == [
        (
            tmp_path / "docs" / "agent" / "agent-detail-AG-03.md",
            tmp_path / "src" / "infra" / "azure",
            "auto",
            "auto",
        )
    ]


def test_runner_gate_resolves_aagd_eval_target(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[tuple[object, ...]] = []

    def fake_eval_validator(
        design_path: Path,
        report_path: Path,
        tool_search_policy: str = "auto",
    ) -> list[str]:
        calls.append((design_path, report_path, tool_search_policy))
        return []

    monkeypatch.setattr(
        "hve.artifact_validation.validate_tool_search_eval_report",
        fake_eval_validator,
    )
    errors = _runner()._run_ai_agent_capability_gate(
        "4/AG-04",
        "QA-ToolSearchEval",
        "aagd",
    )
    assert errors == []
    assert calls == [
        (
            tmp_path / "docs" / "agent" / "agent-detail-AG-04.md",
            tmp_path / "docs" / "agent" / "tool-search-eval" / "AG-04-eval-report.md",
            "auto",
        )
    ]


def test_runner_gate_is_exact_allowlist_and_other_workflows_noop(
    monkeypatch: Any,
) -> None:
    called = False

    def fake_validator(*args: object, **kwargs: object) -> list[str]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(
        "hve.artifact_validation.validate_ai_agent_capability_artifacts",
        fake_validator,
    )
    runner = _runner()
    cases = (
        ("3/AG-01", "OtherAgent", "aag"),
        ("2/AG-01", "Arch-AIAgentDesign-Step3", "aag"),
        ("2.3/AG-01", "Dev-Microservice-Azure-AgentCoding", "asdw-web"),
        ("2.2/AG-01", "Dev-Microservice-Azure-AgentTestCoding", "aagd"),
    )
    for step_id, agent, workflow in cases:
        assert runner._run_ai_agent_capability_gate(step_id, agent, workflow) == []
    assert called is False


def test_runner_gate_fails_closed_for_missing_or_unsafe_target_key() -> None:
    runner = _runner()
    missing = runner._run_ai_agent_capability_gate(
        "3",
        "Arch-AIAgentDesign-Step3",
        "aag",
    )
    assert missing and "fan-out target key" in missing[0]

    unsafe = runner._run_ai_agent_capability_gate(
        "2.3/../../outside",
        "Dev-Microservice-Azure-AgentCoding",
        "aagd",
    )
    assert unsafe and "unsafe" in unsafe[0].lower()


def test_runner_gate_accepts_valid_target_key_boundaries(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "hve.artifact_validation.validate_ai_agent_capability_artifacts",
        lambda *args, **kwargs: [],
    )
    runner = _runner()
    for key in ("A", "a1", "AG-01_v2", "x" * 128):
        assert runner._run_ai_agent_capability_gate(
            f"3/{key}",
            "Arch-AIAgentDesign-Step3",
            "aag",
        ) == []


def test_runner_gate_prefixes_validator_errors(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "hve.artifact_validation.validate_ai_agent_capability_artifacts",
        lambda *args, **kwargs: ["[AG-CAP-03] selected route missing"],
    )
    errors = _runner()._run_ai_agent_capability_gate(
        "2.3/AG-01",
        "Dev-Microservice-Azure-AgentCoding",
        "aagd",
    )
    assert errors == [
        "[Dev-Microservice-Azure-AgentCoding] AI Agent capability contract failed: "
        "[AG-CAP-03] selected route missing"
    ]


def test_runner_gate_converts_validator_exception_to_fail_closed_error(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)

    def raise_validator(*args: object, **kwargs: object) -> list[str]:
        raise RuntimeError("validator boom")

    monkeypatch.setattr(
        "hve.artifact_validation.validate_ai_agent_capability_artifacts",
        raise_validator,
    )
    errors = _runner()._run_ai_agent_capability_gate(
        "3/AG-01",
        "Arch-AIAgentDesign-Step3",
        "aag",
    )
    assert len(errors) == 1
    assert "validator raised: RuntimeError: validator boom" in errors[0]


def test_run_step_contains_fail_closed_capability_gate() -> None:
    source = inspect.getsource(StepRunner.run_step)
    assert "_run_ai_agent_capability_gate" in source
    assert '"kind": "ai_agent_capability_gate_failed"' in source
    gate_start = source.index("_run_ai_agent_capability_gate")
    final_success = source.rindex(
        'self.console.step_end(step_id, "success"'
    )
    assert gate_start < final_success
    gate_block = source[gate_start:final_success]
    assert 'self.console.step_end(step_id, "failed"' in gate_block
    assert "return False" in gate_block
