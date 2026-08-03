from __future__ import annotations

from pathlib import Path

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner
from hve.workflow_registry import get_workflow

_AGENT = "Dev-Microservice-Azure-AddServiceDeploy"


def _runner() -> StepRunner:
    return StepRunner(config=SDKConfig(), console=Console(verbose=False, quiet=True))


def _write_report(run_root: Path, step_id: str = "2.2") -> None:
    report = run_root / _AGENT / f"Issue-step-{step_id.replace('.', '-')}" / "ac-verification.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        "| AC-1 | resources | ✅ | ok |\n"
        "| AC-13 | model deployment | ✅ | ok |\n"
        "| AC-14 | Foundry Project | ✅ | ok |\n",
        encoding="utf-8",
    )


def _write_design(repo_root: Path, *, foundry: bool) -> None:
    design = repo_root / "docs" / "azure" / "azure-services-additional.md"
    design.parent.mkdir(parents=True, exist_ok=True)
    service = "Microsoft Foundry (Foundry Agent Service)" if foundry else "Azure Key Vault"
    design.write_text(f"| AI/LLM | {service} |\n", encoding="utf-8")


def _write_valid_scripts(repo_root: Path) -> None:
    services = repo_root / "src" / "infra" / "azure" / "create-azure-additional-resources" / "services"
    services.mkdir(parents=True, exist_ok=True)
    (services / "aiservices.sh").write_text(
        "az cognitiveservices account project show --name account -g rg --project-name project\n"
        "az cognitiveservices account project create --name account -g rg --project-name project --location eastus\n"
        "az cognitiveservices account project show --name account -g rg --project-name project\n",
        encoding="utf-8",
    )
    verify = (
        repo_root
        / "src"
        / "infra"
        / "azure"
        / "create-azure-additional-resources"
        / "verify-additional-resources.sh"
    )
    verify.write_text(
        "az cognitiveservices account project show --name account -g rg --project-name project\n",
        encoding="utf-8",
    )


def test_asdw_step_2_2_rejects_missing_foundry_artifacts(tmp_path: Path, monkeypatch) -> None:
    run_root = tmp_path / "work" / "run" / "run-1"
    _write_report(run_root)
    _write_design(tmp_path, foundry=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    errors = _runner()._run_deploy_ac_gate(
        "2.2", _AGENT, get_workflow("asdw-web")
    )

    assert any("Foundry deploy artifact contract failed" in error for error in errors)
    assert any("service scripts not found" in error for error in errors)


def test_asdw_step_2_2_accepts_valid_foundry_artifacts(tmp_path: Path, monkeypatch) -> None:
    run_root = tmp_path / "work" / "run" / "run-1"
    _write_report(run_root)
    _write_design(tmp_path, foundry=True)
    _write_valid_scripts(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    assert _runner()._run_deploy_ac_gate(
        "2.2", _AGENT, get_workflow("asdw-web")
    ) == []


def test_asdw_step_2_2_skips_artifact_contract_when_foundry_not_adopted(
    tmp_path: Path, monkeypatch
) -> None:
    run_root = tmp_path / "work" / "run" / "run-1"
    _write_report(run_root)
    _write_design(tmp_path, foundry=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    assert _runner()._run_deploy_ac_gate(
        "2.2", _AGENT, get_workflow("asdw-web")
    ) == []


def test_foundry_artifact_contract_is_not_applied_to_other_steps(
    tmp_path: Path, monkeypatch
) -> None:
    run_root = tmp_path / "work" / "run" / "run-1"
    _write_report(run_root, step_id="2.3")
    _write_design(tmp_path, foundry=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    assert _runner()._run_deploy_ac_gate(
        "2.3", _AGENT, get_workflow("asdw-web")
    ) == []


def test_asdw_step_2_2_returns_ac_and_artifact_errors_together(
    tmp_path: Path, monkeypatch
) -> None:
    run_root = tmp_path / "work" / "run" / "run-1"
    _write_report(run_root)
    report = run_root / _AGENT / "Issue-step-2-2" / "ac-verification.md"
    report.write_text(
        "| AC-1 | resources | ✅ | ok |\n"
        "| AC-13 | model deployment | ✅ | ok |\n"
        "| AC-14 | Foundry Project | ❌ | missing |\n",
        encoding="utf-8",
    )
    _write_design(tmp_path, foundry=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    errors = _runner()._run_deploy_ac_gate(
        "2.2", _AGENT, get_workflow("asdw-web")
    )

    assert any("AC AC-14 is not GREEN" in error for error in errors)
    assert any("Foundry deploy artifact contract failed" in error for error in errors)


def test_foundry_artifact_contract_is_not_applied_without_workflow(
    tmp_path: Path, monkeypatch
) -> None:
    run_root = tmp_path / "work" / "run" / "run-1"
    _write_report(run_root)
    _write_design(tmp_path, foundry=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    assert _runner()._run_deploy_ac_gate("2.2", _AGENT, None) == []
