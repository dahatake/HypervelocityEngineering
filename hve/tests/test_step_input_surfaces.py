"""FR-INPUT-04/06 — CLI・Prompt・Cloud が共通 Step 入力契約を使う。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock

import pytest
import yaml

from hve import __main__ as hve_main
from hve.gui.orchestrate_args import OrchestrateArgs
from hve.resume_service import standard_execution_is_registerable
from hve.step_inputs import (
    CloudStepInputResult,
    StepInputError,
    build_cloud_step_input_section,
    materialize_cloud_step_inputs,
)
from hve.workflow_registry import get_workflow


ROOT = Path(__file__).resolve().parents[2]
FORMS = sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))
CLOUD_FORMS = [path for path in FORMS if path.name != "setup-labels.yml"]
REUSABLES = sorted((ROOT / ".github" / "workflows").glob("auto-*-reusable.yml"))
TARGET_REUSABLES = [
    path for path in REUSABLES
    if path.name not in {
        "check-app-requirements-reusable.yml",
        "check-auto-qa-skip-reusable.yml",
    }
]


def test_step_inputs_supports_legacy_flat_import() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from pathlib import Path; "
                f"sys.path.insert(0, {str(ROOT / 'hve')!r}); "
                "import step_inputs; "
                f"root = Path({str(ROOT)!r}); "
                "assert step_inputs.bundle_for_step({}, '1') is None; "
                "assert step_inputs.load_step_input_slots(root, 'aas', '1'); "
                "body = '### Step Input Files\\ninput.md\\n\\n' "
                "+ '### Step Input Bindings\\n{}'; "
                "section = step_inputs.build_cloud_step_input_section(body, 'aas'); "
                "assert 'python3 -m hve.step_inputs cloud-manifest' in section"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_noninteractive_cli_accepts_ordered_step_inputs(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "extra.md"
    source.write_text("extra", encoding="utf-8")
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("HVE_WORK_ROOT", str(ROOT / "work" / "run" / "test-step-input"))
    parser = hve_main._build_parser()
    args = parser.parse_args([
        "orchestrate", "--workflow", "aas", "--steps", "1",
        "--step-input", "1", "additional", "-", str(source),
    ])

    params = hve_main._build_params(args)
    bundle = params["step_input_bundles"]["1"]
    assert len(bundle.entries) == 1
    assert bundle.entries[0].role == "additional"


def test_gui_args_emit_the_same_repeatable_cli_shape(tmp_path: Path) -> None:
    args = OrchestrateArgs(
        workflow="aas",
        step_inputs=[("1", "additional", None, str(tmp_path / "a.md"))],
    )

    argv = args.to_argv()
    index = argv.index("--step-input")
    assert argv[index + 1:index + 5] == [
        "1", "additional", "-", str(tmp_path / "a.md")
    ]


def test_cli_parser_enables_step_input_wizard_by_default() -> None:
    parser = hve_main._build_parser()

    assert parser.parse_args(["cli"]).step_input_wizard is True
    assert parser.parse_args(["cli", "--no-step-input-wizard"]).step_input_wizard is False


def test_cli_wizard_preserves_multiple_candidate_and_explicit_files(
    tmp_path: Path,
) -> None:
    candidate_a = tmp_path / "docs-original" / "a.md"
    candidate_b = tmp_path / "docs-original" / "b.md"
    explicit = tmp_path / "outside.md"
    candidate_a.parent.mkdir(parents=True)
    candidate_a.write_text("a", encoding="utf-8")
    candidate_b.write_text("b", encoding="utf-8")
    explicit.write_text("outside", encoding="utf-8")
    workflow = get_workflow("aas")
    assert workflow is not None

    console = MagicMock()
    console.prompt_yes_no.side_effect = [True, True, False]
    console.menu_select.side_effect = [0, 0]
    console.prompt_input.side_effect = ["candidate", str(explicit)]
    console.prompt_multi_select.return_value = [0, 1]

    specs = hve_main._collect_step_input_specs_wizard(
        console,
        workflow,
        ["1"],
        repo_root=tmp_path,
    )

    assert [Path(spec.source) for spec in specs] == [
        candidate_a.relative_to(tmp_path),
        candidate_b.relative_to(tmp_path),
        explicit,
    ]
    assert all(spec.step_id == "1" for spec in specs)
    assert all(spec.role == "additional" for spec in specs)


def test_step_input_run_is_not_registered_for_durable_resume() -> None:
    class Config:
        dry_run = False
        fleet_mode_enabled = False
        cloud_session_enabled = False
        create_issues = False
        assign_copilot_agent = False

    assert standard_execution_is_registerable(
        Config(),
        {"step_input_bundles": {"1": object()}},
        existing_execution_id=None,
    ) is False


def test_all_current_cloud_forms_offer_files_and_bindings_textareas() -> None:
    # FR-INPUT-04 は「現行12面だけ」を対象とし、将来追加されたFormを暗黙に
    # 対応済みにしない。件数変化時は要件と明示的に同期するdrift gateである。
    assert len(CLOUD_FORMS) == 12
    for path in CLOUD_FORMS:
        body = yaml.safe_load(path.read_text(encoding="utf-8"))["body"]
        by_id = {item.get("id"): item for item in body if isinstance(item, dict)}
        assert "step_input_files" in by_id, path.name
        assert "step_input_bindings" in by_id, path.name
        assert by_id["step_input_files"]["type"] == "textarea", path.name
        assert by_id["step_input_bindings"]["type"] == "textarea", path.name
        assert by_id["step_input_files"]["validations"]["required"] is False
        assert by_id["step_input_bindings"]["validations"]["required"] is False
        description = by_id["step_input_files"]["attributes"]["description"]
        assert "branch-relative path" in description, path.name
        assert "Cloud upload unavailable" in description, path.name
        assert "ドラッグ＆ドロップしてください" not in description, path.name


def test_all_current_cloud_reusables_delegate_to_shared_helper() -> None:
    # Issue Formと同じく、対象を現行12 reusableから無言で拡張しない。
    assert len(TARGET_REUSABLES) == 12
    for path in TARGET_REUSABLES:
        text = path.read_text(encoding="utf-8")
        assert "python3 -m hve.step_inputs cloud-manifest" in text, path.name
        assert "step-input-manifest" in text, path.name
        assert "Cloud upload unavailable" in text, path.name


def test_cloud_section_does_not_recursively_expand_user_placeholders() -> None:
    body = """### Step Input Files

incoming/{step_input_bindings}.md

### Step Input Bindings

{"step_id":"1","role":"additional","file":1}
"""

    section = build_cloud_step_input_section(body, "aas")

    assert "incoming/{step_input_bindings}.md" in section
    assert section.count('{"step_id":"1","role":"additional","file":1}') == 1


def test_empty_cloud_input_keeps_the_existing_step_body_unchanged() -> None:
    assert build_cloud_step_input_section("", "aas") == ""


def test_cloud_branch_path_uses_the_same_materializer(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "incoming" / "extra.md"
    source.parent.mkdir(parents=True)
    source.write_text("extra", encoding="utf-8")
    contract = repo / ".github" / "io-contracts" / "Arch-ARD-BusinessAnalysis-Untargeted--ard--1.yaml"
    contract.parent.mkdir(parents=True)
    contract.write_text("inputs: []\noutputs: []\n", encoding="utf-8")

    result = materialize_cloud_step_inputs(
        repo_root=repo,
        work_root=repo / "work" / "run" / "cloud",
        workflow_id="ard",
        files_text="incoming/extra.md",
        bindings_text='{"step_id":"1","role":"additional","file":1}',
    )
    assert isinstance(result, CloudStepInputResult)
    assert result.supported is True
    assert result.manifest_path is not None
    assert len(result.bundles["1"].entries) == 1


def test_cloud_branch_path_rejects_resolved_source_outside_repo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    monkeypatch.setattr("hve.step_inputs._resolve_source", lambda *_args: outside)

    with pytest.raises(StepInputError, match="repository配下"):
        materialize_cloud_step_inputs(
            repo_root=repo,
            work_root=repo / "work" / "run" / "cloud",
            workflow_id="ard",
            files_text="incoming/extra.md",
            bindings_text='{"step_id":"1","role":"additional","file":1}',
        )


def test_cloud_upload_without_downloader_is_reported_as_unsupported(tmp_path: Path) -> None:
    result = materialize_cloud_step_inputs(
        repo_root=tmp_path,
        work_root=tmp_path / "work" / "run" / "cloud",
        workflow_id="ard",
        files_text="[input.pdf](https://github.com/user-attachments/assets/example)",
        bindings_text='{"step_id":"1","role":"additional","file":1}',
        downloader=None,
    )
    assert result.supported is False
    assert result.bundles == {}
    assert "Cloud upload unavailable" in result.warning
    assert "branch-relative" in result.warning


def test_cloud_downloader_rejects_symlink_result(tmp_path: Path) -> None:
    import os

    if not hasattr(os, "symlink"):
        pytest.skip("symlink is unavailable")
    target = tmp_path / "target.pdf"
    link = tmp_path / "link.pdf"
    target.write_bytes(b"pdf")
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is not permitted")

    with pytest.raises(StepInputError, match="安全な通常ファイル"):
        materialize_cloud_step_inputs(
            repo_root=tmp_path,
            work_root=tmp_path / "work" / "run" / "cloud",
            workflow_id="ard",
            files_text="[input.pdf](https://github.com/user-attachments/assets/example)",
            bindings_text='{"step_id":"1","role":"additional","file":1}',
            downloader=lambda _url: link,
        )


def test_cloud_branch_path_rejects_parent_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "extra.md").write_text("extra", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    linked_parent = repo / "incoming"
    try:
        linked_parent.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is not permitted")

    with pytest.raises(StepInputError, match="repository配下"):
        materialize_cloud_step_inputs(
            repo_root=repo,
            work_root=repo / "work" / "run" / "cloud",
            workflow_id="ard",
            files_text="incoming/extra.md",
            bindings_text='{"step_id":"1","role":"additional","file":1}',
        )
