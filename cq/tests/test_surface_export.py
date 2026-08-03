"""Contracts for the single-implementation surface inventory export (FR-CQ-10).

The extraction algorithm must exist exactly once (in :mod:`cq.surface_export`),
while the *entrypoint* stays `hve-dev/generate_tdd_inventory.py` as FR-MAINT-05
requires. Adding a second entrypoint (e.g. a `cq export` subcommand) would
recreate the drift this requirement exists to prevent.
"""

from __future__ import annotations

import ast
import csv
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from cq import surface_export

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "hve-dev" / "generate_tdd_inventory.py"
SURFACE_CSV = REPO_ROOT / "hve-dev" / "hve-surface-inventory.csv"

EXPECTED_FIELDNAMES = [
    "surface", "kind", "symbol", "file", "line",
    "behavior_summary", "rule_tokens", "callers_count",
]
MOVED_FUNCTIONS = {
    "literals_in", "summarize_definition", "python_surface_rows",
    "shell_surface_rows", "workflow_surface_rows",
}


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_tdd_inventory", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return _generator()


@pytest.fixture(scope="module")
def generator_tree() -> ast.Module:
    return ast.parse(GENERATOR.read_text(encoding="utf-8-sig"))


class TestSingleImplementation:
    def test_fieldnames_live_in_the_shared_module(self) -> None:
        assert surface_export.SURFACE_FIELDNAMES == EXPECTED_FIELDNAMES

    def test_generator_imports_the_shared_module(self, generator_tree: ast.Module) -> None:
        imported = {
            (node.module, alias.name)
            for node in ast.walk(generator_tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert ("cq.surface_export", "SURFACE_FIELDNAMES") in imported

    @pytest.mark.parametrize("name", sorted(MOVED_FUNCTIONS))
    def test_generator_no_longer_defines_the_algorithm(
        self, generator_tree: ast.Module, name: str
    ) -> None:
        defined = {
            node.name for node in generator_tree.body if isinstance(node, ast.FunctionDef)
        }
        if name in defined:
            # 残っていてよいのは委譲だけ（本体を持たない）。
            node = next(n for n in generator_tree.body
                        if isinstance(n, ast.FunctionDef) and n.name == name)
            body = [s for s in node.body if not isinstance(s, ast.Expr)]
            assert len(body) == 1 and isinstance(body[0], ast.Return)
            assert "surface_export" in ast.unparse(body[0])

    def test_generator_delegates_collection(self, generator_tree: ast.Module) -> None:
        node = next(n for n in generator_tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "collect_surface_symbols")
        assert "surface_export.collect" in ast.unparse(node)

    def test_shared_module_has_no_hve_specific_imports(self) -> None:
        """cq 側に HVE 固有ポリシーを埋め込まない（境界の維持）。"""
        source = (REPO_ROOT / "cq" / "surface_export.py").read_text(encoding="utf-8")
        assert "hve_scope" not in source
        assert "NORMATIVE_LITERALS" not in source

    def test_no_second_entrypoint_is_added(self) -> None:
        """FR-MAINT-05: 生成の正規 entrypoint は generate_tdd_inventory.py 単一。"""
        source = (REPO_ROOT / "cq" / "surface_export.py").read_text(encoding="utf-8")
        assert "__main__" not in source
        cli_source = (REPO_ROOT / "cq" / "cli.py").read_text(encoding="utf-8")
        assert "surface_export" not in cli_source


class TestOutputIsUnchanged:
    def test_regeneration_matches_the_committed_inventory(
        self, generator: ModuleType, tmp_path: Path
    ) -> None:
        """統合の前後で列構成と内容が変化しない（FR-CQ-10）。"""
        rows = generator.collect_surface_symbols(generator.git_files())
        target = tmp_path / "surface.csv"
        generator.write_csv(target, rows, surface_export.SURFACE_FIELDNAMES)
        assert target.read_bytes() == SURFACE_CSV.read_bytes()

    def test_collection_is_deterministic(self, generator: ModuleType) -> None:
        files = generator.git_files()
        assert generator.collect_surface_symbols(files) == generator.collect_surface_symbols(files)


class TestContent:
    @pytest.fixture(scope="class")
    @classmethod
    def rows(cls) -> list[dict[str, str]]:
        with SURFACE_CSV.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def test_out_of_scope_paths_are_absent(self, rows) -> None:
        assert not [r["file"] for r in rows if r["file"].startswith(("src/", "docs/", "work/"))]

    def test_every_surface_is_known(self, rows) -> None:
        assert {r["surface"] for r in rows} <= {"cloud", "cli", "gui", "core"}

    def test_rule_tokens_are_still_populated(self, rows) -> None:
        """FR-MAINT-06 の検査主キーが失われていないこと。"""
        assert any(r["rule_tokens"] for r in rows)

    def test_shell_and_workflow_surfaces_survive(self, rows) -> None:
        kinds = {r["kind"] for r in rows}
        assert {"shell_function", "ci_rule", "constant", "function", "class"} <= kinds
