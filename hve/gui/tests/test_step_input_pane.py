"""FR-INPUT-04 — Step 1 右ペインの文書入力表示・複数選択。"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from hve.gui.step_input_pane import StepInputPane
from hve.gui.page_options import OptionsPage
from hve.step_inputs import StepInputError


_application: QApplication | None = None


def _get_app() -> QApplication:
    global _application
    _application = QApplication.instance() or QApplication([])
    return _application


def test_pane_displays_contract_metadata_and_existing_name(tmp_path: Path) -> None:
    _get_app()
    repo = tmp_path / "repo"
    canonical = repo / "docs" / "catalog" / "app-catalog.md"
    canonical.parent.mkdir(parents=True)
    canonical.write_text("# catalog", encoding="utf-8")
    contract_dir = repo / ".github" / "io-contracts"
    contract_dir.mkdir(parents=True)
    contract_dir.joinpath("Arch-ArchitectureCandidateAnalyzer--aas--1.yaml").write_text(
        "inputs:\n- path: docs/catalog/app-catalog.md\n  required: true\n  kind: agent_artifact\n  producer: Upstream\noutputs: []\n",
        encoding="utf-8",
    )

    pane = StepInputPane(repo_root=repo)
    pane.set_selected_steps({"aas": ["1"]})
    row = pane.rows()[0]

    assert row.required_text == "required"
    assert row.canonical == "docs/catalog/app-catalog.md"
    assert row.kind == "agent_artifact"
    assert row.exists is True
    assert row.existing_names == ("app-catalog.md",)
    assert row.substitute_enabled is False
    pane.deleteLater()


def test_pane_preserves_multiple_selection_and_previews_markdown_names(tmp_path: Path) -> None:
    _get_app()
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.docx"
    first.write_bytes(b"pdf")
    second.write_bytes(b"docx")
    pane = StepInputPane(repo_root=Path.cwd())
    pane.set_selected_steps({"aas": ["1"]})

    pane.set_files("aas", "1", None, "additional", [first, second])
    selections = pane.selections_for_workflow("aas")

    assert [item.source for item in selections] == [first, second]
    assert pane.conversion_previews() == ("first.md", "second.md")
    assert "step_inputs" not in pane.persistent_values()
    pane.deleteLater()


def test_container_selection_expands_to_all_executable_children() -> None:
    _get_app()
    pane = StepInputPane(repo_root=Path.cwd())

    pane.set_selected_steps({"asdw-web": ["1"]})

    assert {row.step_id for row in pane.rows()} == {"1.1", "1.2", "1.3"}
    pane.deleteLater()


def test_switching_workflow_discards_inactive_selections(tmp_path: Path) -> None:
    _get_app()
    source = tmp_path / "extra.md"
    source.write_text("extra", encoding="utf-8")
    pane = StepInputPane(repo_root=Path.cwd())
    pane.set_selected_steps({"aas": ["1"]})
    pane.set_files("aas", "1", None, "additional", [source])

    pane.set_selected_steps({"ada": ["2"]})

    assert pane.selections_for_workflow("aas") == ()
    pane.deleteLater()


def test_unsupported_document_is_rejected_before_runtime(tmp_path: Path) -> None:
    _get_app()
    source = tmp_path / "payload.bin"
    source.write_bytes(b"not a document")
    pane = StepInputPane(repo_root=Path.cwd())
    pane.set_selected_steps({"aas": ["1"]})

    try:
        pane.set_files("aas", "1", None, "additional", [source])
    except StepInputError as exc:
        assert "対応文書形式" in str(exc)
    else:
        raise AssertionError("unsupported document was accepted")
    assert pane.selections_for_workflow("aas") == ()
    pane.deleteLater()


def test_options_page_passes_runtime_selection_and_explicit_consent(tmp_path: Path) -> None:
    _get_app()
    source = tmp_path / "extra.md"
    source.write_text("extra", encoding="utf-8")
    page = OptionsPage(repo_root=Path.cwd())
    page.set_workflows(["aas"], {"aas": "Architecture Design"})
    page.set_selected_steps({"aas": ["1"]})
    page.step_input_pane.set_files("aas", "1", None, "additional", [source])
    page.step_input_pane._mcp_consent.setChecked(True)

    args = page.build_args_for_workflow("aas", repo_root=Path.cwd())
    argv = args.to_argv()

    index = argv.index("--step-input")
    assert argv[index + 1:index + 5] == ["1", "additional", "-", str(source)]
    assert "--step-input-mcp-consent" in argv
    page.deleteLater()
