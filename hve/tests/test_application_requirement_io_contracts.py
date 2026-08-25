"""FR-WF-ARD-04 / FR-WF-AAS-02 のscoped I/O producer移管RED。"""

from __future__ import annotations

from pathlib import Path

import yaml


_REPO = Path(__file__).resolve().parents[2]
_CONTRACTS = _REPO / ".github" / "io-contracts"
_OLD_PRODUCER = "Arch-ApplicationAnalytics--aas--1"
_NEW_PRODUCER = "Arch-ApplicationAnalytics--ard--4.1"
_REQUIREMENT_PRODUCER = "Arch-ApplicationRequirementDefinition--ard--4.2"


def _load(name: str) -> dict:
    data = yaml.safe_load((_CONTRACTS / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_ard_scoped_producer_contracts_exist_and_old_aas_contract_is_removed() -> None:
    assert (_CONTRACTS / f"{_NEW_PRODUCER}.yaml").is_file()
    assert (_CONTRACTS / f"{_REQUIREMENT_PRODUCER}.yaml").is_file()
    assert not (_CONTRACTS / f"{_OLD_PRODUCER}.yaml").exists()


def test_all_72_scoped_app_catalog_references_move_to_ard() -> None:
    """AAS 63件 + ADA Step 1 移管で追加された 9件 = 72件が ard--4.1 を producer とする。"""
    texts = [path.read_text(encoding="utf-8") for path in _CONTRACTS.glob("*.yaml")]
    assert sum(text.count(f"producer: {_OLD_PRODUCER}") for text in texts) == 0
    assert sum(text.count(f"producer: {_NEW_PRODUCER}") for text in texts) == 72


def test_requirement_producer_declares_variable_upsert_output() -> None:
    contract = _load(f"{_REQUIREMENT_PRODUCER}.yaml")
    output = next(
        item
        for item in contract["outputs"]
        if item["path"] == "docs/architectural-requirements-app-*.md"
    )
    assert output["required"] is False
    assert output["mode"] == "upsert"


def test_aas_step_1_requires_the_app_requirement_producer() -> None:
    contract = _load("Arch-ArchitectureCandidateAnalyzer--aas--1.yaml")
    requirement = next(
        item
        for item in contract["inputs"]
        if item["path"] == "docs/architectural-requirements-app-*.md"
    )
    assert requirement == {
        "path": "docs/architectural-requirements-app-*.md",
        "required": True,
        "kind": "agent_artifact",
        "producer": _REQUIREMENT_PRODUCER,
    }
