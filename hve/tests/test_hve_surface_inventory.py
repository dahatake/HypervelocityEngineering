"""Contracts for the shared HVE scope decision used by the surface inventory (FR-MAINT-05).

The scope boundary is defined by `hve-dev/requirement-definition.md` §3.7 and must be
decided by a single implementation. These tests fix that the decision lives in one
module and that no consumer re-declares the boundary tables. The version-bump boundary
(FR-MAINT-08) is a subset of the same decision and is therefore contracted here too.
"""

from __future__ import annotations

import ast
import csv
import importlib.util
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / ".github" / "scripts"
SHARED_SCOPE_MODULE = SCRIPTS_DIR / "hve_scope.py"
VALIDATOR = SCRIPTS_DIR / "validate-hve-requirement-traceability.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"

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
    "docs-original/spec.md",
    "sample/demo.md",
    "users-guide/hve-cli-orchestrator-guide.md",
    "work/run/x/Issue-1/plan.md",
    "tests/run/x/tdd-test-report.md",
    "hve.egg-info/PKG-INFO",
    "tools/hve-app-cash/app.py",
    "package.json",
    "jest.config.js",
    "babel.config.js",
    "playwright.config.js",
    "CHANGELOG.md",
    ".github/workflows/deploy-app009.yml",
    ".github/workflows/azure-static-web-apps-app009.yml",
    ".github/workflows/app009-ci.yml",
)

# FR-MAINT-08: 対象境界のうち、HVE パッケージ版の更新を要求するパス。
VERSION_BUMP_REQUIRED_SAMPLES = (
    "hve/orchestrator.py",
    "hve/gui/main_window.py",
    "hve/tests/test_dag_validation.py",
    "hve-dev/requirement-definition.md",
    "template/sample.md",
    ".github/copilot-instructions.md",
    ".github/instructions/hve-maintenance.instructions.md",
    ".github/skills/harness/adversarial-review/SKILL.md",
    ".github/prompts/Arch-DataModeling.prompt.md",
    ".github/io-contracts/Arch-ImprovementPlanner.yaml",
    ".github/scripts/hve_scope.py",
    ".github/workflows/auto-approve-and-merge.yml",
    "tools/runner/entry.py",
    "tools/gen_something.py",
    "tests/bats/smoke.bats",
    "hve.cmd",
    "hve.sh",
    ".vscode/tasks.json",
    # engine 本体ではなくリポジトリ側の設定のため、独立ライフサイクルの除外に含めない。
    "mdq.toml",
    "cq.toml",
)

# FR-MAINT-08: 同期先ファイル自身と、独立ライフサイクルで版管理するパス。
VERSION_BUMP_EXEMPT_SAMPLES = (
    "pyproject.toml",
    "hve/__init__.py",
    "CHANGELOG.md",
    "mdq/cli.py",
    "mdq/gui/__main__.py",
    "mdq/tests/test_store.py",
    "cq/store.py",
    "cq/tests/test_store.py",
    "tools/skills/markdown_query/vendor/mdq/store.py",
    "tools/skills/code_query/pyproject.toml",
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


class TestVersionBumpScope:
    """FR-MAINT-08: 版更新を要求するパス判定が対象境界と同一モジュールの単一実装であること。"""

    def test_predicate_is_part_of_the_shared_scope_api(self) -> None:
        assert hasattr(_load_shared_scope(), "requires_version_bump")

    @pytest.mark.parametrize("path", VERSION_BUMP_REQUIRED_SAMPLES)
    def test_in_scope_paths_require_a_bump(self, path: str) -> None:
        assert _load_shared_scope().requires_version_bump(path) is True

    @pytest.mark.parametrize("path", VERSION_BUMP_EXEMPT_SAMPLES)
    def test_sync_targets_and_independent_lifecycles_are_exempt(self, path: str) -> None:
        assert _load_shared_scope().requires_version_bump(path) is False

    @pytest.mark.parametrize("path", OUT_OF_SCOPE_SAMPLES)
    def test_out_of_scope_paths_never_require_a_bump(self, path: str) -> None:
        assert _load_shared_scope().requires_version_bump(path) is False

    def test_decision_is_a_subset_of_the_scope_boundary(self) -> None:
        module = _load_shared_scope()
        samples = (
            IN_SCOPE_SAMPLES
            + OUT_OF_SCOPE_SAMPLES
            + VERSION_BUMP_REQUIRED_SAMPLES
            + VERSION_BUMP_EXEMPT_SAMPLES
        )
        for path in samples:
            if module.requires_version_bump(path):
                assert module.is_in_scope(path), path

    def test_sync_targets_come_from_the_bumpversion_config(self) -> None:
        """同期先の列挙が `[tool.bumpversion]` からドリフトすると除外が欠ける。"""
        config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["bumpversion"]
        # pyproject.toml 自身は bump-my-version が暗黙の対象に含めるため files に現れない。
        declared = {"pyproject.toml", *(entry["filename"] for entry in config["files"])}
        assert set(_load_shared_scope().VERSION_BUMP_FILES) == declared


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
    def test_git_files_excludes_deleted_cached_paths(
        self,
        generator: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        existing = tmp_path / "hve" / "tests" / "existing.py"
        existing.parent.mkdir(parents=True)
        existing.write_text("def test_existing(): pass\n", encoding="utf-8")
        monkeypatch.setattr(generator, "ROOT", tmp_path)
        monkeypatch.setattr(
            generator.subprocess,
            "check_output",
            lambda *_args, **_kwargs: (
                "hve/tests/existing.py\nhve/tests/deleted.py\n"
            ),
        )

        assert generator.git_files() == ["hve/tests/existing.py"]

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
