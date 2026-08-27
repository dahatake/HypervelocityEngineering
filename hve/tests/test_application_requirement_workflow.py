"""FR-WF-ARD-03/04・FR-WF-AAS-02 のWorkflow契約RED。"""

from __future__ import annotations

from pathlib import Path

from hve.orchestrator import (
    _ARTIFACT_KEY_TO_EXPECTED_PATH,
    _ARTIFACT_KEY_TO_GENERATING_WORKFLOW,
    _detect_existing_artifacts,
)
from hve.workflow_registry import (
    ADA,
    AAS,
    ARD,
    ARD_DEFAULT_GROUP_IDS,
    _WORKFLOW_GROUP_MAPS,
)


def test_ard_has_five_groups_and_ten_steps() -> None:
    assert ARD_DEFAULT_GROUP_IDS == ("2", "3", "4", "5")
    assert _WORKFLOW_GROUP_MAPS["ard"]["5"] == ["4.1", "4.2"]
    assert [step.id for step in ARD.steps] == [
        "1", "1.1", "1.2", "2", "2.1", "3.1", "3.2", "3.3", "4.1", "4.2"
    ]


def test_ard_step_41_owns_the_application_catalog() -> None:
    step = ARD.get_step("4.1")
    assert step is not None
    assert step.custom_agent == "Arch-ApplicationAnalytics"
    assert step.depends_on == ["3.3"]
    assert step.output_paths == ["docs/catalog/app-catalog.md"]
    assert step.required_input_paths == ["docs/catalog/use-case-catalog.md"]
    assert step.body_template_path == ".github/prompts/steps/ard/step-4.1.prompt.md"


def test_ard_step_42_is_a_single_sequential_upsert_step() -> None:
    step = ARD.get_step("4.2")
    assert step is not None
    assert step.custom_agent == "Arch-ApplicationRequirementDefinition"
    assert step.depends_on == ["4.1"]
    assert step.fanout_parser is None
    assert step.fanout_static_keys is None
    assert step.output_paths == []
    assert step.output_paths_template == [
        "docs/architectural-requirements-app-*.md"
    ]
    assert step.required_input_paths == [
        "docs/catalog/app-catalog.md",
        "docs/catalog/use-case-catalog.md",
    ]
    assert step.body_template_path == ".github/prompts/steps/ard/step-4.2.prompt.md"


def test_aas_starts_at_step_1_after_renumbering() -> None:
    """AAS Step.1 起点化により、旧 Step 2（root）は新 Step 1 へ昇格した。"""
    ids = [step.id for step in AAS.steps]
    assert ids == ["1", "2.1", "2.2", "3.1", "3.2", "4", "5", "6", "7", "8"]
    step = AAS.get_step("1")
    assert step is not None
    assert step.depends_on == []
    assert step.fanout_parser is None
    assert step.fanout_static_keys is None
    assert "app_requirements" in (step.consumed_artifacts or [])
    assert "docs/architectural-requirements-app-*.md" in step.required_input_paths


def test_ada_step_1_is_migrated_to_ard_and_no_longer_exists() -> None:
    """ADA Step 1 は AAS Step 1 と同じ理由で ARD Step 4.1 へ移管され廃止された。"""
    assert ADA.get_step("1") is None
    step = ADA.get_step("2")
    assert step is not None
    assert step.depends_on == []


def test_application_requirement_artifact_is_detected_and_owned_by_ard(
    tmp_path: Path, monkeypatch
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    requirement = docs / "architectural-requirements-app-001.md"
    requirement.write_text("# placeholder\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    artifacts = _detect_existing_artifacts("aas", {})
    assert artifacts["app_requirements"] == [
        "docs/architectural-requirements-app-001.md"
    ]
    assert _ARTIFACT_KEY_TO_EXPECTED_PATH["app_requirements"] == (
        "docs/architectural-requirements-app-*.md"
    )
    assert _ARTIFACT_KEY_TO_GENERATING_WORKFLOW["app_requirements"] == "ard"
