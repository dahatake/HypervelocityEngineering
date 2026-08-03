"""io-contract tests for runtime TDD report artifacts."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATE_SCRIPT = _REPO_ROOT / ".github" / "scripts" / "validate-io-contract.py"
_RUNTIME_REPORT_PATH = "tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md"
_RUNTIME_WORK_PATH = (
    "work/run/<run-id>/Dev-Microservice-Azure-DataDeploy/"
    "Issue-<識別子>/ac-verification.md"
)
_RUNTIME_WORK_STATUS_PATH = (
    "work/run/<run-id>/Dev-Microservice-Azure-DataDeploy/"
    "Issue-<識別子>/work-status.md"
)
_DATA_DEPLOY_CONTRACTS = (
    "Dev-Microservice-Azure-DataDeploy.yaml",
    "Dev-Microservice-Azure-DataDeploy--asdw-web--1.3.yaml",
)
_IO_CONTRACTS = [
    "Dev-Microservice-Azure-DataTestCoding--asdw-web--1.2.yaml",
    "Dev-Microservice-Azure-DataDeploy--asdw-web--1.3.yaml",
    "Dev-Microservice-Azure-AddServiceTestCoding--asdw-web--2.3.yaml",
    "Dev-Microservice-Azure-AddServiceTesting--asdw-web--2.4.yaml",
    "Dev-Microservice-Azure-ServiceTestCoding--asdw-web--3.2.yaml",
    "Dev-Microservice-Azure-ServiceCoding-AzureFunctions--asdw-web--3.3.yaml",
    "Dev-Microservice-Azure-UITestCoding--asdw-web--4.1.yaml",
    "Dev-Microservice-Azure-UICoding--asdw-web--4.2.yaml",
    "Dev-Dataflow-TestCoding--adfdv--2.1.yaml",
    "Dev-Dataflow-ServiceCoding--adfdv--2.2.yaml",
    "Dev-Microservice-Azure-AgentTestCoding--aagd--2.2.yaml",
    "Dev-Microservice-Azure-AgentCoding--aagd--2.3.yaml",
]


def _load_validate_module():
    spec = importlib.util.spec_from_file_location("validate_io_contract_tdd", _VALIDATE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_io_contract_tdd"] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_tdd_report_output_is_detected_as_runtime_artifact() -> None:
    mod = _load_validate_module()
    assert mod.is_runtime_output_path(_RUNTIME_REPORT_PATH) is True
    assert mod.is_runtime_output_path(_RUNTIME_WORK_PATH) is True
    assert mod.is_runtime_output_path("docs/catalog/app-catalog.md") is False


def test_runtime_tdd_report_is_ignored_by_registry_mismatch() -> None:
    mod = _load_validate_module()
    agents = {
        "Agent--wf--1": {
            "inputs": [],
            "outputs": [
                {"path": _RUNTIME_REPORT_PATH, "required": True, "mode": "create"},
                {"path": _RUNTIME_WORK_PATH, "required": True, "mode": "create"},
            ],
        }
    }
    assert mod._contract_output_paths(agents["Agent--wf--1"]) == set()


def test_tdd_io_contracts_declare_runtime_report_output() -> None:
    contracts_dir = _REPO_ROOT / ".github" / "io-contracts"
    for name in _IO_CONTRACTS:
        text = (contracts_dir / name).read_text(encoding="utf-8")
        assert _RUNTIME_REPORT_PATH in text, f"{name} missing TDD runtime report output"


def test_asdw_sample_data_requiredness_matches_step_roles() -> None:
    contracts_dir = _REPO_ROOT / ".github" / "io-contracts"
    expected = {
        "Dev-Microservice-Azure-DataTestCoding--asdw-web--1.2.yaml": False,
        "Dev-Microservice-Azure-DataDeploy--asdw-web--1.3.yaml": True,
    }
    for name, required in expected.items():
        contract = yaml.safe_load(
            (contracts_dir / name).read_text(encoding="utf-8")
        )
        sample_input = next(
            item
            for item in contract["inputs"]
            if item["path"] == "src/data/sample-data.json"
        )
        assert sample_input["required"] is required, name


def test_data_deploy_contracts_declare_hve_owned_stage_result_evidence() -> None:
    """P09: pipeline—not Agent prose—owns the three DataDeploy reports."""
    contracts_dir = _REPO_ROOT / ".github" / "io-contracts"
    expected_paths: dict[str, dict[str, object]] = {
        _RUNTIME_WORK_STATUS_PATH: {
            "mode": "create",
            "owner": "hve",
            "evidence_source": "stage_results",
        },
        _RUNTIME_WORK_PATH: {
            "mode": "create",
            "owner": "hve",
            "evidence_source": "stage_results",
            "acceptance_criteria": ["AC-1", "AC-2", "AC-3"],
        },
        _RUNTIME_REPORT_PATH: {
            "mode": "create",
            "owner": "hve",
            "evidence_source": "stage_results",
        },
    }
    for name in _DATA_DEPLOY_CONTRACTS:
        contract = yaml.safe_load(
            (contracts_dir / name).read_text(encoding="utf-8")
        )
        outputs = {
            item["path"]: item
            for item in contract["outputs"]
            if item["path"] in expected_paths
        }
        assert outputs.keys() == expected_paths.keys(), name
        for path, expected in expected_paths.items():
            for field, value in expected.items():
                assert outputs[path].get(field) == value, (name, path, field)


def test_data_deploy_contracts_never_reintroduce_env_file_as_input_or_output() -> None:
    """P09: source-tree data-deploy.env is neither an Agent nor HVE artifact."""
    contracts_dir = _REPO_ROOT / ".github" / "io-contracts"
    for name in _DATA_DEPLOY_CONTRACTS:
        contract = yaml.safe_load(
            (contracts_dir / name).read_text(encoding="utf-8")
        )
        paths = [
            item["path"]
            for role in ("inputs", "outputs")
            for item in contract[role]
        ]
        assert not any("data-deploy.env" in path for path in paths), name


def test_data_deploy_stage_result_evidence_metadata_passes_io_schema() -> None:
    mod = _load_validate_module()
    contracts_dir = _REPO_ROOT / ".github" / "io-contracts"
    for name in _DATA_DEPLOY_CONTRACTS:
        contract = yaml.safe_load(
            (contracts_dir / name).read_text(encoding="utf-8")
        )
        assert mod.validate_io_contract(name, contract) == []
