"""FR-MAINT-10: macOS GUI test の費用承認・手動実行契約。"""

from __future__ import annotations

from pathlib import Path
import tomllib
from typing import cast

import yaml  # type: ignore[import-untyped]


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "test-hve-gui-macos.yml"
_SKILL = (
    _REPO_ROOT
    / ".github"
    / "skills"
    / "hve-requirement-traceability"
    / "SKILL.md"
)
_SMOKE_TEST = _REPO_ROOT / "hve" / "gui" / "tests" / "test_macos_cocoa_smoke.py"
_REQUIREMENTS = _REPO_ROOT / "hve-dev" / "requirement-definition.md"
_MAPPING = _REPO_ROOT / "hve-dev" / "requirement-test-mapping.md"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


def _load_workflow() -> dict[object, object]:
    assert _WORKFLOW.is_file(), f"required workflow is missing: {_WORKFLOW}"
    loaded = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _on_section(workflow: dict[object, object]) -> dict[str, object]:
    section = workflow.get(True, workflow.get("on"))
    assert isinstance(section, dict)
    return cast(dict[str, object], section)


def _jobs(workflow: dict[object, object]) -> dict[str, dict[str, object]]:
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    return cast(dict[str, dict[str, object]], jobs)


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    steps = job.get("steps")
    assert isinstance(steps, list)
    assert all(isinstance(step, dict) for step in steps)
    return steps  # type: ignore[return-value]


def _run_text(job: dict[str, object]) -> str:
    return "\n".join(
        str(step["run"]) for step in _steps(job) if "run" in step
    )


def _unique_step(job: dict[str, object], name: str) -> dict[str, object]:
    matches = [step for step in _steps(job) if step.get("name") == name]
    assert len(matches) == 1, f"expected exactly one step named {name!r}"
    return matches[0]


def test_requirement_and_mapping_register_fr_maint_10() -> None:
    requirements = _REQUIREMENTS.read_text(encoding="utf-8")
    mapping = _MAPPING.read_text(encoding="utf-8")
    assert "**FR-MAINT-10**" in requirements
    assert "#### FR-MAINT-10" in mapping
    assert "hve/tests/test_macos_gui_workflow_contract.py" in mapping


def test_maintenance_skill_defines_the_paid_macos_gate() -> None:
    skill = _SKILL.read_text(encoding="utf-8")
    assert "## macOS GUI test の費用承認ゲート" in skill
    assert "変更影響の判定表" in skill
    assert "runner label / architecture / test scope" in skill
    assert "公式単価とその確認日および出典 URL" in skill
    assert "予測実行時間と予測課金額" in skill
    assert "timeout（分）×単価（USD/分）" in skill
    assert "free minutes 残量を取得できない場合" in skill
    assert "承認は当該見積りに対する特定 workflow run 1 回だけ" in skill
    assert "承認が無い場合は workflow を dispatch しない" in skill
    assert "`github.run_attempt == 1` のときだけ macOS job を開始" in skill
    assert "失敗または workflow run の cancel 後" in skill
    assert "新しい `workflow_dispatch` run を起動" in skill


def test_workflow_is_manual_only_and_requires_cost_approval() -> None:
    workflow = _load_workflow()
    on_section = _on_section(workflow)
    assert set(on_section) == {"workflow_dispatch"}
    dispatch = on_section["workflow_dispatch"]
    assert isinstance(dispatch, dict)
    inputs = dispatch.get("inputs")
    assert isinstance(inputs, dict)
    assert set(inputs) == {"test_scope", "estimated_cost_usd", "cost_approved"}
    scope = inputs["test_scope"]
    assert isinstance(scope, dict)
    assert str(scope.get("description", "")).strip()
    assert scope.get("required") is True
    assert scope.get("default") == "smoke"
    assert scope.get("type") == "choice"
    assert set(scope.get("options", [])) == {"smoke", "full"}
    estimate = inputs["estimated_cost_usd"]
    assert isinstance(estimate, dict)
    assert estimate.get("required") is True
    assert estimate.get("type") == "string"
    approval = inputs["cost_approved"]
    assert isinstance(approval, dict)
    assert approval.get("required") is True
    assert approval.get("type") == "boolean"
    assert approval.get("default") is False


def test_jobs_are_read_only_cost_gated_and_have_scope_specific_timeouts() -> None:
    workflow = _load_workflow()
    assert workflow.get("permissions") == {"contents": "read"}
    jobs = _jobs(workflow)
    assert set(jobs) == {"smoke", "full"}
    for scope, timeout in (("smoke", 15), ("full", 120)):
        job = jobs[scope]
        assert job.get("runs-on") == "macos-15"
        assert job.get("timeout-minutes") == timeout
        assert "strategy" not in job
        condition = str(job.get("if", ""))
        assert "inputs.cost_approved" in condition
        assert "inputs.estimated_cost_usd != ''" in condition
        assert f"inputs.test_scope == '{scope}'" in condition
        assert "github.run_attempt == 1" in condition
        assert job.get("continue-on-error") is not True


def test_smoke_uses_cocoa_and_fails_when_the_test_is_skipped() -> None:
    jobs = _jobs(_load_workflow())
    smoke = jobs["smoke"]
    run_text = _run_text(smoke)

    smoke_step = _unique_step(smoke, "Run Cocoa smoke")
    assert smoke_step.get("env") == {
        "QT_QPA_PLATFORM": "cocoa",
        "HVE_MACOS_GUI_ARTIFACT_DIR": "work/run/macos-gui/artifacts",
    }
    assert "hve/gui/tests/test_macos_cocoa_smoke.py" in str(smoke_step.get("run", ""))
    assert "--junitxml=work/run/macos-gui/artifacts/cocoa-smoke.xml" in run_text
    assert "skipped == 0" in run_text
    assert "QApplication.platformName()" not in run_text


def test_full_runs_offscreen_suite_and_cocoa_smoke_in_separate_processes() -> None:
    jobs = _jobs(_load_workflow())
    full = jobs["full"]
    offscreen = _unique_step(full, "Run full GUI suite offscreen")
    cocoa = _unique_step(full, "Run Cocoa smoke")
    assert offscreen.get("env") == {"QT_QPA_PLATFORM": "offscreen"}
    offscreen_run = str(offscreen.get("run", ""))
    assert "python -m pytest hve/gui/tests" in offscreen_run
    assert "--ignore=hve/gui/tests/test_macos_cocoa_smoke.py" in offscreen_run
    assert cocoa.get("env") == {
        "QT_QPA_PLATFORM": "cocoa",
        "HVE_MACOS_GUI_ARTIFACT_DIR": "work/run/macos-gui/artifacts",
    }
    assert "hve/gui/tests/test_macos_cocoa_smoke.py" in str(cocoa.get("run", ""))


def test_workflow_uploads_small_diagnostic_artifacts_for_seven_days() -> None:
    jobs = _jobs(_load_workflow())

    for job in jobs.values():
        upload = next(
            step
            for step in _steps(job)
            if str(step.get("uses", "")).startswith("actions/upload-artifact@")
        )
        assert "always()" in str(upload.get("if", ""))
        with_values = upload.get("with")
        assert isinstance(with_values, dict)
        assert with_values.get("path") == "work/run/macos-gui/artifacts/"
        assert with_values.get("retention-days") == 7
        assert with_values.get("if-no-files-found") == "error"


def test_runtime_smoke_exists_and_no_new_test_framework_is_added() -> None:
    assert _SMOKE_TEST.is_file(), f"required Cocoa smoke is missing: {_SMOKE_TEST}"
    extras = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]
    test_requirements = "\n".join(extras["test"]).lower()

    assert "pytest-qt" not in test_requirements
    assert "pytest-xdist" not in test_requirements
    assert "pytest-timeout" not in test_requirements
    assert "appium" not in test_requirements
