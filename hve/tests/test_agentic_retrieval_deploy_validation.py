"""Agentic Retrieval の Deploy 成果物ゲート。

FR-WF-AAGD-05。
Toolbox の採否に関わらず、設計の AR-CAP-01 `Knowledge base name` と
AR-CAP-02 の各 `KS name` が `src/infra/azure/` 配下から追跡できることを静的に照合する。
Azure へは接続しない。
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hve.artifact_validation import validate_ai_agent_deploy_artifacts

from hve.tests.test_agentic_retrieval_contract_validation import (
    _ROUTING_WITHOUT_FOUNDRY_IQ,
    _design,
)

_CREATE_SCRIPT = """#!/usr/bin/env bash
set -euo pipefail

KNOWLEDGE_BASE_NAME="policy-kb"
KNOWLEDGE_SOURCES=("policy-docs" "public-news")

az cognitiveservices account project show --name "${ACCOUNT}" --resource-group "${RG}" --project-name "${PROJECT}"
"""

_CREATE_SCRIPT_WITHOUT_KB = """#!/usr/bin/env bash
set -euo pipefail

az cognitiveservices account project show --name "${ACCOUNT}" --resource-group "${RG}" --project-name "${PROJECT}"
"""

_CREATE_SCRIPT_WITHOUT_ONE_SOURCE = """#!/usr/bin/env bash
set -euo pipefail

KNOWLEDGE_BASE_NAME="policy-kb"
KNOWLEDGE_SOURCES=("policy-docs")
"""


def _validate(
    *,
    design_text: str | None = None,
    create_script: str | None = _CREATE_SCRIPT,
) -> list:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        detail = root / "docs" / "agent" / "agent-detail-AG-01.md"
        detail.parent.mkdir(parents=True, exist_ok=True)
        detail.write_text(design_text if design_text is not None else _design(), encoding="utf-8")

        infra = root / "src" / "infra" / "azure"
        infra.mkdir(parents=True, exist_ok=True)
        if create_script is not None:
            (infra / "create-azure-agent-resources.sh").write_text(
                create_script, encoding="utf-8"
            )
        return validate_ai_agent_deploy_artifacts(detail, infra)


def _deploy_ar_errors(errors: list) -> list:
    """設計側の AR-CAP エラーを除き、Deploy ゲート固有の指摘だけを取り出す。"""
    return [
        error
        for error in errors
        if "AR-CAP" in error and not error.startswith("AAGD design prerequisite")
    ]


class TestAgenticRetrievalDeployGate(unittest.TestCase):
    def test_gate_runs_without_a_toolbox_contract(self) -> None:
        """Toolbox 未採用でも AR-CAP 照合が走る（early return による素通りの回帰防止）。"""
        errors = _deploy_ar_errors(_validate(create_script=_CREATE_SCRIPT_WITHOUT_KB))
        self.assertTrue(errors, "AR-CAP 照合が実行されていない")

    def test_matching_scripts_pass(self) -> None:
        errors = _deploy_ar_errors(_validate())
        self.assertEqual(errors, [], errors)

    def test_missing_knowledge_base_name_fails(self) -> None:
        errors = _deploy_ar_errors(_validate(create_script=_CREATE_SCRIPT_WITHOUT_KB))
        self.assertTrue(
            any("AR-CAP-01" in error and "policy-kb" in error for error in errors),
            errors,
        )

    def test_missing_knowledge_source_fails(self) -> None:
        errors = _deploy_ar_errors(
            _validate(create_script=_CREATE_SCRIPT_WITHOUT_ONE_SOURCE)
        )
        self.assertTrue(
            any("AR-CAP-02" in error and "public-news" in error for error in errors),
            errors,
        )

    def test_missing_infra_directory_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            detail = root / "docs" / "agent" / "agent-detail-AG-01.md"
            detail.parent.mkdir(parents=True, exist_ok=True)
            detail.write_text(_design(), encoding="utf-8")
            errors = validate_ai_agent_deploy_artifacts(detail, root / "missing")
        self.assertTrue(_deploy_ar_errors(errors), errors)

    def test_non_agentic_design_is_unaffected(self) -> None:
        """Foundry IQ 経路を選んでいない設計へ AR-CAP 照合を課さない。"""
        design = _design(routing=_ROUTING_WITHOUT_FOUNDRY_IQ, ar_blocks="")
        errors = _deploy_ar_errors(
            _validate(design_text=design, create_script=_CREATE_SCRIPT_WITHOUT_KB)
        )
        self.assertEqual(errors, [], errors)


if __name__ == "__main__":
    unittest.main()
