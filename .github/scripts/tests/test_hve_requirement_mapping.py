"""Contracts for the shared HVE requirement-mapping parser."""

from __future__ import annotations

import ast
import functools
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (REPO_ROOT / ".github/scripts/hve_requirement_mapping.py").resolve()
GENERATOR_PATH = (REPO_ROOT / "hve-dev/generate_tdd_inventory.py").resolve()
MODULE_NAME = "hve_requirement_mapping_under_test"


def _load_module() -> tuple[ModuleType | None, Exception | None]:
    if not MODULE_PATH.is_file():
        return None, FileNotFoundError(MODULE_PATH)

    try:
        spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot create import spec for {MODULE_PATH}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[MODULE_NAME] = module
        spec.loader.exec_module(module)
        return module, None
    except Exception as exc:  # pragma: no cover - exercised by the future implementation
        sys.modules.pop(MODULE_NAME, None)
        return None, exc


MAPPING_MODULE, MODULE_LOAD_ERROR = _load_module()


def IMPLEMENTATION_REQUIRED(function):
    @functools.wraps(function)
    def require_implementation(*args, **kwargs):
        if MAPPING_MODULE is None:
            pytest.fail(
                f"RED: shared mapping module is unavailable: {MODULE_LOAD_ERROR!r}"
            )
        return function(*args, **kwargs)

    return require_implementation


def _module() -> ModuleType:
    assert MAPPING_MODULE is not None
    return MAPPING_MODULE


def _assert_entry(
    mapping: dict[str, dict[str, object]],
    requirement_id: str,
    *,
    judgment: str,
    tests: list[str],
) -> None:
    assert requirement_id in mapping
    entry = mapping[requirement_id]
    assert isinstance(entry, dict)
    assert entry.get("judgment") == judgment
    assert entry.get("tests") == tests


def test_mapping_module_loads_from_absolute_path_with_required_api() -> None:
    assert MODULE_PATH.is_absolute()
    assert MAPPING_MODULE is not None, (
        f"RED: unable to load future module {MODULE_PATH}: {MODULE_LOAD_ERROR!r}"
    )
    assert callable(getattr(MAPPING_MODULE, "mapping_ids_from_text", None))
    assert callable(getattr(MAPPING_MODULE, "parse_requirement_mapping", None))


@IMPLEMENTATION_REQUIRED
def test_mapping_module_uses_only_stdlib_and_the_canonical_id_grammar() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8-sig"), filename=str(MODULE_PATH))
    imported_roots: set[str] = set()
    relative_imports: list[int] = []
    canonical_imports: set[tuple[str | None, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative_imports.append(node.lineno)
            elif node.module:
                imported_roots.add(node.module.partition(".")[0])
                canonical_imports.update((node.module, alias.name) for alias in node.names)

    third_party = imported_roots - sys.stdlib_module_names - {"__future__", "cq"}
    assert not relative_imports, f"relative imports are not allowed: lines {relative_imports}"
    assert not third_party, f"non-standard-library imports are not allowed: {sorted(third_party)}"
    assert ("cq.traces", "FEATURE_ID_RE") in canonical_imports


@IMPLEMENTATION_REQUIRED
def test_explicit_requirement_and_gate_ids_are_returned_in_source_order() -> None:
    actual = _module().mapping_ids_from_text(
        "FR-MAINT-03 / NFR-CTX-01 / G-OUT — fixture"
    )
    assert actual == ["FR-MAINT-03", "NFR-CTX-01", "G-OUT"]


@IMPLEMENTATION_REQUIRED
def test_heading_references_after_the_title_separator_are_not_mapping_ids() -> None:
    actual = _module().mapping_ids_from_text(
        "FR-MCPLOG-03 — FR-RTO-04 を参照する logging contract"
    )
    assert actual == ["FR-MCPLOG-03"]


@IMPLEMENTATION_REQUIRED
def test_same_prefix_slash_shorthand_expands_every_id() -> None:
    actual = _module().mapping_ids_from_text("FR-APPREQ-03 / 04 / 05")
    assert actual == ["FR-APPREQ-03", "FR-APPREQ-04", "FR-APPREQ-05"]


@IMPLEMENTATION_REQUIRED
@pytest.mark.parametrize("separator", ("〜", "～", "~"))
def test_ascending_range_expands_inclusively_and_preserves_numeric_width(
    separator: str,
) -> None:
    actual = _module().mapping_ids_from_text(f"FR-WF-ADI-08{separator}10")
    assert actual == ["FR-WF-ADI-08", "FR-WF-ADI-09", "FR-WF-ADI-10"]


@IMPLEMENTATION_REQUIRED
def test_middle_dot_shorthand_uses_the_same_prefix() -> None:
    actual = _module().mapping_ids_from_text("NFR-SEC-ADI-01・02")
    assert actual == ["NFR-SEC-ADI-01", "NFR-SEC-ADI-02"]


@IMPLEMENTATION_REQUIRED
@pytest.mark.parametrize(
    "text",
    (
        "FR-WF-ADI-03〜01",
        "FR-WF-ADI-03～01",
        "FR-WF-ADI-03~01",
        "FR-WF-ADI-01〜XX",
        "FR-WF-ADI-01〜",
        "FR-WF-ADI-01~02-EXTRA",
        "FR-WF-ADI-01 / 02.5",
        "FR-WF-ADI-01・02_extra",
        "FR-WF-ADI-01_extra",
        "FR-WF-ADI-01.5",
        "FR-WF-ADI-01 /",
        "FR-WF-ADI-01・XX",
        "FR-WF-ADI-01 // 02",
    ),
)
def test_malformed_or_descending_ranges_fail_closed_without_partial_ids(
    text: str,
) -> None:
    module = _module()
    assert module.mapping_ids_from_text(text) == []
    assert module.parse_requirement_mapping(
        f"### {text} — invalid fixture\n- 判定: ✓\n"
    ) == {}


@IMPLEMENTATION_REQUIRED
@pytest.mark.parametrize(
    "text",
    (
        "FR-WF-ADI-01〜02X",
        "FR-WF-ADI-01~02.5",
        "FR-WF-ADI-01〜1001",
    ),
)
def test_invalid_suffix_or_oversized_ranges_fail_closed(text: str) -> None:
    assert _module().mapping_ids_from_text(text) == []


@IMPLEMENTATION_REQUIRED
def test_range_expansion_limit_accepts_100_items_and_rejects_101() -> None:
    accepted = _module().mapping_ids_from_text("FR-X-01〜100")
    assert len(accepted) == 100
    assert accepted[0] == "FR-X-01"
    assert accepted[-1] == "FR-X-100"
    assert _module().mapping_ids_from_text("FR-X-01〜101") == []


@IMPLEMENTATION_REQUIRED
def test_grouped_heading_applies_judgment_and_links_to_every_id() -> None:
    text = """\
# Fixture mapping

### FR-WF-ADI-01〜03 / NFR-SEC-ADI-01・02 — ADI
- 判定: ○
- 直接対応テスト:
  - [doc ingest](hve/tests/test_doc_ingest.py)
  - [GUI conversion](hve/gui/tests/test_gui_doc_convert.py)

#### FR-PARAM-01 / 02 — AKM sources
- 判定: ✓
- 直接対応テスト:
  - [source normalization](hve/tests/test_akm_sources_normalization.py)
"""
    mapping = _module().parse_requirement_mapping(text)

    first_ids = [
        "FR-WF-ADI-01",
        "FR-WF-ADI-02",
        "FR-WF-ADI-03",
        "NFR-SEC-ADI-01",
        "NFR-SEC-ADI-02",
    ]
    first_tests = [
        "hve/tests/test_doc_ingest.py",
        "hve/gui/tests/test_gui_doc_convert.py",
    ]
    for requirement_id in first_ids:
        _assert_entry(mapping, requirement_id, judgment="○", tests=first_tests)

    second_tests = ["hve/tests/test_akm_sources_normalization.py"]
    for requirement_id in ("FR-PARAM-01", "FR-PARAM-02"):
        _assert_entry(mapping, requirement_id, judgment="✓", tests=second_tests)

    assert set(mapping) == set(first_ids) | {"FR-PARAM-01", "FR-PARAM-02"}


@IMPLEMENTATION_REQUIRED
def test_table_rows_use_first_cell_ids_second_cell_judgment_and_later_links() -> None:
    text = """\
### §13 fixture

| 要件 | 判定 | 主な対応テスト | 補助テスト |
|---|---|---|---|
| FR-WF-CONF-01 — conformance wiring | ✓ | [step contract](hve/tests/test_requirements_conformance_step.py) | [PowerShell parity](.github/scripts/powershell/tests/workflow-registry.Tests.ps1) |
| FR-WF-CONF-02 — report schema | ✓ | [schema contract](hve/tests/test_requirements_conformance_validation.py) | — |
| G-OUT（必須成果物） | △ | [output gate](hve/tests/test_workflow_gate_scope_contract.py) | [Bats smoke](tests/bats/hve.bats) |
"""
    mapping = _module().parse_requirement_mapping(text)

    conformance_tests = [
        "hve/tests/test_requirements_conformance_step.py",
        ".github/scripts/powershell/tests/workflow-registry.Tests.ps1",
    ]
    _assert_entry(mapping, "FR-WF-CONF-01", judgment="✓", tests=conformance_tests)
    _assert_entry(
        mapping,
        "FR-WF-CONF-02",
        judgment="✓",
        tests=["hve/tests/test_requirements_conformance_validation.py"],
    )

    _assert_entry(
        mapping,
        "G-OUT",
        judgment="△",
        tests=["hve/tests/test_workflow_gate_scope_contract.py", "tests/bats/hve.bats"],
    )
    assert set(mapping) == {
        "FR-WF-CONF-01",
        "FR-WF-CONF-02",
        "G-OUT",
    }


@IMPLEMENTATION_REQUIRED
def test_table_row_requires_an_id_led_first_cell_and_ignores_prose_slashes() -> None:
    text = """\
| 要件 | 判定 | 主な対応テスト |
|---|---|---|
| Historical note for FR-TEST-01 | ✓ | [hidden](hve/tests/test_runner.py) |
| G-LBL（done/running/blocked） | ✓ | [labels](hve/tests/test_label_consistency_audit.py) |
    | FR-INDENTED-01 | ✓ | [hidden](hve/tests/test_runner.py) |
"""
    mapping = _module().parse_requirement_mapping(text)
    assert set(mapping) == {"G-LBL"}
    _assert_entry(
        mapping,
        "G-LBL",
        judgment="✓",
        tests=["hve/tests/test_label_consistency_audit.py"],
    )


@IMPLEMENTATION_REQUIRED
def test_heading_collects_links_from_every_allowed_test_root() -> None:
    expected_paths = [
        "hve/tests/test_contract.py",
        "hve/gui/tests/test_contract.py",
        "mdq/tests/test_contract.py",
        "mdq/gui/tests/test_contract.py",
        "cq/tests/test_contract.py",
        ".github/scripts/tests/test_contract.py",
        ".github/scripts/python/tests/test_contract.py",
        ".github/scripts/powershell/tests/test_contract.ps1",
        "tests/bats/test_contract.bats",
    ]
    links = "\n".join(f"  - [{path}]({path})" for path in expected_paths)
    text = (
        "### FR-MAINT-04 — traceability\n"
        "- 判定: ✓\n"
        "- 対応テスト:\n"
        f"{links}\n"
        "  - [not a test](docs/test-notes.md)\n"
        "  - [unsupported nested test root](.github/scripts/custom/deep/tests/test_contract.py)\n"
    )

    mapping = _module().parse_requirement_mapping(text)

    _assert_entry(
        mapping,
        "FR-MAINT-04",
        judgment="✓",
        tests=expected_paths,
    )
    assert set(mapping) == {"FR-MAINT-04"}


@IMPLEMENTATION_REQUIRED
def test_section_family_headings_clear_context_without_creating_fake_ids() -> None:
    text = """\
### FR-MAINT-04 — active mapping
- 判定: ✓

### §3.11 Observability（FR-RTO / NFR-RTO）
- [unowned](hve/tests/test_runtime_observability.py)
"""
    mapping = _module().parse_requirement_mapping(text)
    assert set(mapping) == {"FR-MAINT-04"}
    assert mapping["FR-MAINT-04"]["tests"] == []


@IMPLEMENTATION_REQUIRED
@pytest.mark.parametrize(
    "text",
    (
        "```markdown\n### FR-TEST-01 — hidden\n- 判定: ✓\n```\n",
        "<!--\n### FR-TEST-01 — hidden\n- 判定: ✓\n-->\n",
        "`### FR-TEST-01 — hidden`\n- 判定: ✓\n",
        "````markdown\n```\n### FR-TEST-01 — hidden\n```\n````\n",
        "```markdown\n~~~\n### FR-TEST-01 — hidden\n~~~\n```\n",
    ),
)
def test_hidden_markdown_does_not_create_mapping_entries(text: str) -> None:
    assert _module().parse_requirement_mapping(text) == {}


@IMPLEMENTATION_REQUIRED
def test_duplicate_mapping_declarations_keep_both_source_lines() -> None:
    mapping = _module().parse_requirement_mapping(
        "### FR-MAINT-04 — first\n- 判定: ✓\n"
        "### FR-MAINT-04 — duplicate\n- 判定: ✓\n"
    )
    assert mapping["FR-MAINT-04"]["lines"] == [1, 3]


@IMPLEMENTATION_REQUIRED
def test_duplicate_ids_in_one_declaration_keep_both_occurrences() -> None:
    mapping = _module().parse_requirement_mapping(
        "### FR-MAINT-04 / FR-MAINT-04 — duplicate\n- 判定: ✓\n"
    )
    assert mapping["FR-MAINT-04"]["lines"] == [1, 1]


@IMPLEMENTATION_REQUIRED
def test_generator_integrity_checks_only_links_owned_by_active_mappings() -> None:
    spec = importlib.util.spec_from_file_location("generator_under_test", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    mapping = _module().parse_requirement_mapping(
        "### FR-TEST-01 — active\n"
        "- 判定: ✓\n"
        "- [active](hve/tests/test_requirement_definition_integrity.py)\n"
        "### 廃止 NFR（NFR-OLD-01）\n"
        "- [historical missing](hve/tests/test_missing_old.py)\n"
        "## §H 補助テスト\n"
        "- [supplemental missing](hve/tests/test_missing_supplemental.py)\n"
    )
    rows = [
        {
            "feature_kind": "FR",
            "feature_id": "FR-TEST-01",
            "active_status": "active-or-described",
        }
    ]
    errors = generator.mapping_integrity_errors(rows, mapping, root=REPO_ROOT)
    assert errors == []


@IMPLEMENTATION_REQUIRED
def test_generator_integrity_requires_a_real_test_row_for_each_active_link() -> None:
    spec = importlib.util.spec_from_file_location("generator_test_row_integrity", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    mapping = _module().parse_requirement_mapping(
        "### FR-TEST-01 — active\n"
        "- 判定: RED確認済み\n"
        "- [mapped](hve/tests/test_requirement_definition_integrity.py)\n"
    )
    features = [
        {
            "feature_kind": "FR",
            "feature_id": "FR-TEST-01",
            "active_status": "active-or-described",
        }
    ]
    helper_only = [
        {
            "file": "hve/tests/test_requirement_definition_integrity.py",
            "kind": "helper",
            "function_or_case": "helper_only",
        }
    ]
    errors = generator.mapping_integrity_errors(
        features,
        mapping,
        test_rows=helper_only,
        root=REPO_ROOT,
    )
    assert errors == [
        "active requirement mapping has no test row: FR-TEST-01"
    ]


@IMPLEMENTATION_REQUIRED
def test_generator_integrity_rejects_an_active_mapping_without_test_links() -> None:
    spec = importlib.util.spec_from_file_location("generator_empty_test_mapping", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    mapping = _module().parse_requirement_mapping(
        "### FR-TEST-01 — active\n- 判定: 要追加\n"
    )
    features = [
        {
            "feature_kind": "FR",
            "feature_id": "FR-TEST-01",
            "active_status": "active-or-described",
        }
    ]
    assert generator.mapping_integrity_errors(
        features,
        mapping,
        test_rows=[],
        root=REPO_ROOT,
    ) == ["active requirement mapping has no test row: FR-TEST-01"]


@IMPLEMENTATION_REQUIRED
def test_generator_bats_parser_emits_actual_test_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = importlib.util.spec_from_file_location("generator_bats_parser", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    path = tmp_path / "tests" / "bats" / "launcher.bats"
    path.parent.mkdir(parents=True)
    path.write_text(
        "#!/usr/bin/env bats\n@test \"launcher rejects bad input\" {\n  run false\n}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(generator, "ROOT", tmp_path)

    assert generator.category_for_test_path("tests/bats/launcher.bats") == (
        "bats-shell",
        "hve-shell-launchers",
    )
    rows = generator.parse_bats_test(
        "tests/bats/launcher.bats",
        "bats-shell",
        "hve-shell-launchers",
    )
    assert [(row["kind"], row["function_or_case"]) for row in rows] == [
        ("bats-test", "launcher rejects bad input")
    ]


@IMPLEMENTATION_REQUIRED
def test_generator_integrity_allows_fixture_links_beside_a_real_test() -> None:
    spec = importlib.util.spec_from_file_location("generator_fixture_link", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    mapping = _module().parse_requirement_mapping(
        "### FR-TEST-01 — active\n"
        "- 判定: RED確認済み\n"
        "- [test](hve/tests/test_requirement_definition_integrity.py)\n"
        "- [fixture](hve/tests/fixtures/option_parity_matrix.yaml)\n"
    )
    features = [
        {
            "feature_kind": "FR",
            "feature_id": "FR-TEST-01",
            "active_status": "active-or-described",
        }
    ]
    tests = [
        {
            "file": "hve/tests/test_requirement_definition_integrity.py",
            "kind": "test",
            "function_or_case": "test_mapping_integrity",
        }
    ]
    assert generator.mapping_integrity_errors(
        features,
        mapping,
        test_rows=tests,
        root=REPO_ROOT,
    ) == []


@IMPLEMENTATION_REQUIRED
def test_generator_integrity_accepts_a_mapped_path_with_a_test_row() -> None:
    spec = importlib.util.spec_from_file_location("generator_valid_test_row", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    mapping = _module().parse_requirement_mapping(
        "### FR-TEST-01 — active\n"
        "- 判定: RED確認済み\n"
        "- [mapped](hve/tests/test_requirement_definition_integrity.py)\n"
    )
    features = [
        {
            "feature_kind": "FR",
            "feature_id": "FR-TEST-01",
            "active_status": "active-or-described",
        }
    ]
    tests = [
        {
            "file": "hve/tests/test_requirement_definition_integrity.py",
            "kind": "test",
            "function_or_case": "test_mapping_integrity",
        }
    ]
    assert generator.mapping_integrity_errors(
        features,
        mapping,
        test_rows=tests,
        root=REPO_ROOT,
    ) == []


@IMPLEMENTATION_REQUIRED
def test_generator_main_does_not_write_any_artifact_before_integrity_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location("generator_write_order", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    writes: list[str] = []
    monkeypatch.setattr(generator, "git_files", lambda: [])
    monkeypatch.setattr(generator, "collect_tests", lambda _files: ([], []))
    monkeypatch.setattr(generator, "collect_features", lambda: [])
    monkeypatch.setattr(generator, "collect_surface_symbols", lambda _files: [])
    monkeypatch.setattr(generator, "parse_mapping_ids", lambda: {})
    monkeypatch.setattr(
        generator,
        "mapping_integrity_errors",
        lambda *_args, **_kwargs: ["fixture integrity failure"],
    )
    monkeypatch.setattr(generator, "write_csv", lambda *_args, **_kwargs: writes.append("csv"))
    monkeypatch.setattr(generator, "write_policy", lambda: writes.append("policy"))
    monkeypatch.setattr(generator, "write_crosswalk", lambda *_args: writes.append("crosswalk"))

    assert generator.main() == 1
    assert writes == []


@IMPLEMENTATION_REQUIRED
def test_generator_regeneration_matches_all_committed_inventory_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = importlib.util.spec_from_file_location("generator_full_regeneration", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    targets = {
        "TEST_CSV": REPO_ROOT / "hve-dev/hve-test-inventory.csv",
        "FEATURE_CSV": REPO_ROOT / "hve-dev/hve-feature-inventory.csv",
        "SURFACE_CSV": REPO_ROOT / "hve-dev/hve-surface-inventory.csv",
        "CROSSWALK_MD": REPO_ROOT / "hve-dev/hve-tdd-crosswalk-baseline.md",
        "POLICY_MD": REPO_ROOT / "hve-dev/hve-tdd-change-policy.md",
    }
    expected = {name: path.read_bytes() for name, path in targets.items()}
    for name, path in targets.items():
        monkeypatch.setattr(generator, name, tmp_path / path.name)

    assert generator.main() == 0

    for name, path in targets.items():
        generated = tmp_path / path.name
        assert generated.is_file()
        assert generated.read_bytes() == expected[name], path