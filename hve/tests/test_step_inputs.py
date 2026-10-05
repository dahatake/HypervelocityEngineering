"""FR-INPUT-01/02/06 — Step 入力契約・materialize・prompt addendum の契約テスト。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hve.gui import doc_convert
from hve.step_inputs import (
    StepInputError,
    StepInputBundle,
    StepInputEntry,
    StepInputSpec,
    bundle_for_step,
    build_step_input_addendum,
    load_step_input_slots,
    materialize_step_inputs,
    resolve_step_input_step_ids,
    validate_step_input_bundles,
)
from hve.workflow_registry import list_workflows


def test_step_specific_contract_is_display_source_of_truth() -> None:
    slots = load_step_input_slots(Path.cwd(), "aas", "1")
    by_path = {slot.canonical: slot for slot in slots}

    assert by_path["docs/catalog/app-catalog.md"].required is True
    assert by_path["docs/catalog/app-catalog.md"].runtime_required is True
    assert by_path["docs/catalog/app-catalog.md"].kind == "agent_artifact"
    assert by_path["knowledge/D01-事業意図-成功条件定義書.md"].required is False
    assert by_path["knowledge/D01-事業意図-成功条件定義書.md"].kind == "static"
    assert by_path["knowledge/D01-事業意図-成功条件定義書.md"].substitutable is False


def test_every_non_container_step_has_a_loadable_step_contract() -> None:
    seen: set[tuple[str, str]] = set()
    for workflow in list_workflows():
        for step in workflow.steps:
            if step.is_container:
                continue
            slots = load_step_input_slots(Path.cwd(), workflow.id, step.id)
            assert all(slot.step_id == step.id for slot in slots)
            for slot in slots:
                assert slot.runtime_required is (
                    slot.canonical in (step.required_input_paths or [])
                )
            seen.add((workflow.id, step.id))
    assert len(seen) >= 122


def test_container_aggregates_child_step_slots_without_own_slot() -> None:
    slots = load_step_input_slots(Path.cwd(), "asdw-web", "1")

    assert {slot.step_id for slot in slots} == {"1.1", "1.2", "1.3"}
    assert any(slot.canonical == "docs/azure/azure-services-data.md" for slot in slots)


def test_container_selection_resolves_to_executable_step_input_targets() -> None:
    assert resolve_step_input_step_ids("asdw-web", ("1",)) == (
        "1.1",
        "1.2",
        "1.3",
    )


def test_materialize_preserves_order_source_and_actual_digest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    work_root = repo / "work" / "run" / "test-run"
    source_a = tmp_path / "outside-a.md"
    source_b = tmp_path / "outside-b.txt"
    source_a.write_text("# A\n", encoding="utf-8")
    source_b.write_text("plain text", encoding="utf-8")
    original_a = source_a.read_bytes()
    original_b = source_b.read_bytes()

    bundles, manifest = materialize_step_inputs(
        repo_root=repo,
        work_root=work_root,
        workflow_id="aas",
        specs=(
            StepInputSpec("1", "additional", source_a),
            StepInputSpec("1", "additional", source_b),
        ),
    )

    bundle = bundles["1"]
    assert [entry.role for entry in bundle.entries] == ["additional", "additional"]
    assert manifest.is_file()
    assert source_a.read_bytes() == original_a
    assert source_b.read_bytes() == original_b
    for entry in bundle.entries:
        actual = repo / entry.actual
        assert actual.is_file()
        assert actual.suffix == ".md"
        assert hashlib.sha256(actual.read_bytes()).hexdigest() == entry.sha256


def test_substitute_requires_missing_document_slot(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".github" / "io-contracts").mkdir(parents=True)
    (repo / ".github" / "io-contracts" / "Arch-ArchitectureCandidateAnalyzer--aas--1.yaml").write_text(
        "inputs:\n- path: docs/required.md\n  required: true\n  kind: agent_artifact\n  producer: Upstream\noutputs: []\n",
        encoding="utf-8",
    )
    source = tmp_path / "replacement.md"
    source.write_text("replacement", encoding="utf-8")

    bundles, _ = materialize_step_inputs(
        repo_root=repo,
        work_root=repo / "work" / "run" / "r1",
        workflow_id="aas",
        specs=(StepInputSpec("1", "substitute", source, "docs/required.md"),),
    )
    assert bundles["1"].entries[0].canonical == "docs/required.md"

    (repo / "docs").mkdir()
    (repo / "docs" / "required.md").write_text("canonical", encoding="utf-8")
    with pytest.raises(StepInputError, match="存在"):
        materialize_step_inputs(
            repo_root=repo,
            work_root=repo / "work" / "run" / "r2",
            workflow_id="aas",
            specs=(StepInputSpec("1", "substitute", source, "docs/required.md"),),
        )


def test_non_markdown_materialization_delegates_to_existing_converter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    source = tmp_path / "input.pdf"
    source.write_bytes(b"pdf")
    calls: list[Path] = []

    def fake_convert(src: Path, *, out_dir: Path, out_name: str | None = None):
        calls.append(src)
        target = out_dir / (out_name or "input.md")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("converted", encoding="utf-8")
        return doc_convert.ConversionResult(
            src_path=src, converted_path=target, ok=True
        )

    monkeypatch.setattr(doc_convert, "convert_file", fake_convert)
    bundles, _ = materialize_step_inputs(
        repo_root=repo,
        work_root=repo / "work" / "run" / "r",
        workflow_id="aas",
        specs=(StepInputSpec("1", "additional", source),),
    )
    assert calls == [source]
    assert (repo / bundles["1"].entries[0].actual).read_text(encoding="utf-8") == "converted"


def test_manifest_is_not_published_before_bundle_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    work_root = repo / "work" / "run" / "r"
    source = tmp_path / "extra.md"
    source.write_text("extra", encoding="utf-8")

    def fail_validation(*_args, **_kwargs) -> None:
        raise StepInputError("forced validation failure")

    monkeypatch.setattr(
        "hve.step_inputs.validate_step_input_bundles",
        fail_validation,
    )
    with pytest.raises(StepInputError, match="forced validation failure"):
        materialize_step_inputs(
            repo_root=repo,
            work_root=work_root,
            workflow_id="aas",
            specs=(StepInputSpec("1", "additional", source),),
        )

    assert not (work_root / "step-inputs" / "aas" / "manifest.json").exists()


def test_validation_rejects_digest_tamper_and_input_alias_collision(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = tmp_path / "extra.md"
    source.write_text("extra", encoding="utf-8")
    bundles, _ = materialize_step_inputs(
        repo_root=repo,
        work_root=repo / "work" / "run" / "r",
        workflow_id="aas",
        specs=(StepInputSpec("1", "additional", source, "docs/catalog/app-catalog.md"),),
    )
    entry = bundles["1"].entries[0]
    (repo / entry.actual).write_text("tampered", encoding="utf-8")
    with pytest.raises(StepInputError, match="SHA-256"):
        validate_step_input_bundles(bundles, repo_root=repo)

    source.write_text("extra", encoding="utf-8")
    bundles, _ = materialize_step_inputs(
        repo_root=repo,
        work_root=repo / "work" / "run" / "r2",
        workflow_id="aas",
        specs=(StepInputSpec("1", "additional", source, "docs/catalog/app-catalog.md"),),
    )
    with pytest.raises(StepInputError, match="input_alias"):
        validate_step_input_bundles(
            bundles,
            repo_root=repo,
            input_aliases=(("docs/catalog/app-catalog.md", "other.md"),),
        )


def test_prompt_addendum_lists_paths_without_embedding_file_contents(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = tmp_path / "secret-shaped.md"
    source.write_text("DO-NOT-INLINE-CONTENT", encoding="utf-8")
    bundles, manifest = materialize_step_inputs(
        repo_root=repo,
        work_root=repo / "work" / "run" / "r",
        workflow_id="aas",
        specs=(StepInputSpec("1", "additional", source),),
    )

    text = build_step_input_addendum(bundles["1"], manifest_path=manifest, repo_root=repo)
    assert bundles["1"].entries[0].actual in text
    assert "DO-NOT-INLINE-CONTENT" not in text


def test_fanout_child_inherits_its_base_step_bundle() -> None:
    bundle = StepInputBundle(
        workflow_id="ard",
        step_id="3.2",
        entries=(
            StepInputEntry(
                role="additional",
                canonical=None,
                actual="work/run/r/step-inputs/ard/3.2/001-extra.md",
                sha256="0" * 64,
            ),
        ),
    )
    assert bundle_for_step({"3.2": bundle}, "3.2/UC-001") is bundle
