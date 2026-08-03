"""Contracts for the shared HVE scope decision used by the surface inventory (FR-MAINT-05).

The scope boundary is defined by `hve-dev/requirement-definition.md` §3.7 and must be
decided by a single implementation. These tests fix that the decision lives in one
module and that no consumer re-declares the boundary tables.
"""

from __future__ import annotations

import ast
import csv
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / ".github" / "scripts"
SHARED_SCOPE_MODULE = SCRIPTS_DIR / "hve_scope.py"
VALIDATOR = SCRIPTS_DIR / "validate-hve-requirement-traceability.py"

SCOPE_TABLE_NAMES = frozenset(
    {
        "IN_SCOPE_PREFIXES",
        "IN_SCOPE_EXACT",
        "OUT_OF_SCOPE_PREFIXES",
        "OUT_OF_SCOPE_EXACT",
    }
)

IN_SCOPE_SAMPLES = (
    "hve/orchestrator.py",
    "hve/gui/main_window.py",
    "hve/tests/test_dag_validation.py",
    "mdq/cli.py",
    "cq/store.py",
    "cq/tests/test_store.py",
    "cq.toml",
    "hve-dev/requirement-definition.md",
    "template/sample.md",
    "tools/skills/markdown_query/vendor/mdq/store.py",
    "users-guide/hve-cli-orchestrator-guide.md",
    ".github/copilot-instructions.md",
    ".github/instructions/hve-maintenance.instructions.md",
    ".github/skills/harness/adversarial-review/SKILL.md",
    ".github/prompts/Arch-DataModeling.prompt.md",
    ".github/io-contracts/Arch-ImprovementPlanner.yaml",
    ".github/scripts/bash/validate-plan.sh",
    ".github/workflows/auto-approve-and-merge.yml",
    "tests/bats/smoke.bats",
    "pyproject.toml",
    "mdq.toml",
    "hve.cmd",
    "hve.sh",
    ".vscode/tasks.json",
    "tools/gen_something.py",
)

OUT_OF_SCOPE_SAMPLES = (
    "src/app/main.ts",
    "docs/catalog/app-catalog.md",
    "docs-generated/architecture/overview.md",
    "knowledge/D01-glossary.md",
    "qa/Arch-DataModeling-Issue-58.md",
    "original-docs/spec.md",
    "sample/demo.md",
    "work/run/x/Issue-1/plan.md",
    "tests/run/x/tdd-test-report.md",
    "hve.egg-info/PKG-INFO",
    "tools/hve-app-cash/app.py",
    "tools/gen_app04_test_specs.py",
    "package.json",
    "jest.config.js",
    "babel.config.js",
    "playwright.config.js",
    "CHANGELOG.md",
    ".github/workflows/deploy-app009.yml",
    ".github/workflows/azure-static-web-apps-app009.yml",
    ".github/workflows/app009-ci.yml",
)


def _load_shared_scope() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hve_scope", SHARED_SCOPE_MODULE)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load shared scope module: {SHARED_SCOPE_MODULE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module_level_assigned_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


class TestSharedScopeModule:
    def test_module_exists(self) -> None:
        assert SHARED_SCOPE_MODULE.is_file()

    def test_public_api(self) -> None:
        module = _load_shared_scope()
        for name in ("is_in_scope", "is_out_of_scope", "normalise_relative", "ScopeError"):
            assert hasattr(module, name), name

    @pytest.mark.parametrize("path", IN_SCOPE_SAMPLES)
    def test_in_scope_samples(self, path: str) -> None:
        module = _load_shared_scope()
        assert module.is_in_scope(path) is True
        assert module.is_out_of_scope(path) is False

    @pytest.mark.parametrize("path", OUT_OF_SCOPE_SAMPLES)
    def test_out_of_scope_samples(self, path: str) -> None:
        module = _load_shared_scope()
        assert module.is_out_of_scope(path) is True
        assert module.is_in_scope(path) is False

    def test_normalise_relative_rejects_unsafe_paths(self) -> None:
        module = _load_shared_scope()
        for value in ("/abs/path", "./rel", "a//b", "a\\b", "..", "a/../b"):
            with pytest.raises(module.ScopeError):
                module.normalise_relative(value)

    def test_normalise_relative_accepts_repository_relative(self) -> None:
        module = _load_shared_scope()
        assert module.normalise_relative("hve/orchestrator.py") == "hve/orchestrator.py"


class TestSingleScopeDeclaration:
    def test_validator_imports_shared_module(self) -> None:
        assert "hve_scope" in _imported_module_names(VALIDATOR)

    def test_validator_does_not_redeclare_scope_tables(self) -> None:
        redeclared = SCOPE_TABLE_NAMES & _module_level_assigned_names(VALIDATOR)
        assert not redeclared, f"scope tables must live only in hve_scope.py: {sorted(redeclared)}"

    def test_scope_tables_are_declared_in_shared_module(self) -> None:
        assert SCOPE_TABLE_NAMES <= _module_level_assigned_names(SHARED_SCOPE_MODULE)


GENERATOR = REPO_ROOT / "hve-dev" / "generate_tdd_inventory.py"
SURFACE_CSV = REPO_ROOT / "hve-dev" / "hve-surface-inventory.csv"

EXPECTED_SURFACE_FIELDNAMES = [
    "surface",
    "kind",
    "symbol",
    "file",
    "line",
    "behavior_summary",
    "rule_tokens",
    "callers_count",
]

SURFACE_PROBES = (
    ("hve/orchestrator.py", "cli"),
    ("hve/__main__.py", "cli"),
    ("hve/runner.py", "cli"),
    ("hve/gui/main_window.py", "gui"),
    ("hve/artifact_validation.py", "core"),
    ("mdq/cli.py", "core"),
    (".github/scripts/bash/validate-plan.sh", "cloud"),
    (".github/workflows/auto-approve-and-merge.yml", "cloud"),
)


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_tdd_inventory", GENERATOR)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load generator: {GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return _load_generator()


@pytest.fixture(scope="module")
def surface_rows(generator: ModuleType) -> list[dict[str, object]]:
    return generator.collect_surface_symbols(generator.git_files())


class TestSurfaceInventory:
    def test_fieldnames_match_requirement(self, generator: ModuleType) -> None:
        assert generator.SURFACE_FIELDNAMES == EXPECTED_SURFACE_FIELDNAMES

    @pytest.mark.parametrize(("path", "expected"), SURFACE_PROBES)
    def test_surface_for_path(self, generator: ModuleType, path: str, expected: str) -> None:
        assert generator.surface_for_path(path) == expected

    @pytest.mark.parametrize("path", OUT_OF_SCOPE_SAMPLES)
    def test_surface_for_path_rejects_out_of_scope(self, generator: ModuleType, path: str) -> None:
        assert generator.surface_for_path(path) is None

    def test_surface_decision_delegates_to_shared_scope(self, generator: ModuleType) -> None:
        """§3.7 の対象境界判定を索引生成側で二重定義していないこと（FR-MAINT-05）。"""
        module = _load_shared_scope()
        for path in IN_SCOPE_SAMPLES + OUT_OF_SCOPE_SAMPLES:
            assert (generator.surface_for_path(path) is not None) == module.is_in_scope(path), path

    def test_generator_does_not_redeclare_scope_tables(self) -> None:
        redeclared = SCOPE_TABLE_NAMES & _module_level_assigned_names(GENERATOR)
        assert not redeclared, f"scope tables must live only in hve_scope.py: {sorted(redeclared)}"

    def test_collection_is_deterministic(self, generator: ModuleType) -> None:
        files = generator.git_files()
        assert generator.collect_surface_symbols(files) == generator.collect_surface_symbols(files)

    def test_rows_are_well_formed(self, surface_rows: list[dict[str, object]]) -> None:
        assert surface_rows
        for row in surface_rows[:200]:
            assert set(row) == set(EXPECTED_SURFACE_FIELDNAMES)
            assert row["surface"] in {"cloud", "cli", "gui", "core"}
            assert str(row["symbol"])
            assert int(str(row["line"])) > 0

    def test_rows_never_include_out_of_scope_paths(self, surface_rows: list[dict[str, object]]) -> None:
        module = _load_shared_scope()
        offending = sorted({str(r["file"]) for r in surface_rows if module.is_out_of_scope(str(r["file"]))})
        assert not offending, f"generated inventory must exclude HVE-generated artifacts: {offending[:5]}"

    def test_rows_exclude_test_files(
        self, generator: ModuleType, surface_rows: list[dict[str, object]]
    ) -> None:
        """テストは hve-test-inventory.csv が正本。二重索引にしない。"""
        offending = sorted(
            {str(r["file"]) for r in surface_rows if generator.category_for_test_path(str(r["file"]))}
        )
        assert not offending, f"tests belong to the test inventory: {offending[:5]}"

    def test_rule_tokens_expose_cross_surface_duplication(
        self, surface_rows: list[dict[str, object]]
    ) -> None:
        """規範リテラルが面を跨いで引けること（FR-MAINT-06 の検査主キー）。"""

        def surfaces_with(token: str) -> set[str]:
            return {
                str(row["surface"])
                for row in surface_rows
                if token in str(row["rule_tokens"]).split(";")
            }

        assert len(surfaces_with("validation-confirmed")) >= 2
        assert surfaces_with("split_decision")

    def test_csv_exists_with_expected_header(self) -> None:
        assert SURFACE_CSV.is_file()
        with SURFACE_CSV.open(encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream))
        assert header == EXPECTED_SURFACE_FIELDNAMES

    def test_csv_is_not_stale(self, surface_rows: list[dict[str, object]]) -> None:
        """FR-MAINT-05: committed な索引が生成元と一致すること。"""
        with SURFACE_CSV.open(encoding="utf-8-sig", newline="") as stream:
            stored = [tuple(row[name] for name in EXPECTED_SURFACE_FIELDNAMES) for row in csv.DictReader(stream)]
        fresh = [tuple(str(row[name]) for name in EXPECTED_SURFACE_FIELDNAMES) for row in surface_rows]
        assert stored == fresh


class TestSurfaceInventoryCiGate:
    """FR-MAINT-05 の「CI は不一致・対象外混入で失敗させる」を成立させる配線の契約。"""

    WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test-hve-python.yml"

    def _triggers(self) -> dict:
        import yaml

        data = yaml.safe_load(self.WORKFLOW.read_text(encoding="utf-8"))
        # YAML 1.1 では `on:` が真偽値 True としてパースされる。
        return data.get("on") or data[True]

    @pytest.mark.parametrize("event", ("push", "pull_request"))
    @pytest.mark.parametrize("prefix", ("hve-dev/", ".github/scripts/"))
    def test_workflow_runs_when_inventory_sources_change(self, event: str, prefix: str) -> None:
        paths = self._triggers()[event]["paths"]
        assert any(str(entry).startswith(prefix) for entry in paths), (
            f"{event}.paths must include {prefix} so a stale surface inventory is detected"
        )
