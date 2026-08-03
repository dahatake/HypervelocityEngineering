"""Contracts for the code-query (cq) requirement bootstrap and scope boundary.

`cq` is a new HVE application component (source-code search). Before any `cq/`
file can be committed, the §3.7 scope boundary and the requirement/mapping
documents must recognise it; otherwise FR-MAINT-04 would never gate `cq/` changes
and FR-MAINT-05 would never index its symbols.
"""

from __future__ import annotations

import csv
import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCOPE_MODULE = REPO_ROOT / ".github" / "scripts" / "hve_scope.py"
GENERATOR = REPO_ROOT / "hve-dev" / "generate_tdd_inventory.py"
DEFINITION = REPO_ROOT / "hve-dev" / "requirement-definition.md"
MAPPING = REPO_ROOT / "hve-dev" / "requirement-test-mapping.md"
FEATURE_INVENTORY = REPO_ROOT / "hve-dev" / "hve-feature-inventory.csv"

REQUIREMENT_IDS = tuple(f"FR-CQ-{n:02d}" for n in range(1, 13)) + ("NFR-CQ-01",)

CQ_IN_SCOPE_SAMPLES = (
    "cq/store.py",
    "cq/cli.py",
    "cq/languages/python.py",
    "cq/tests/test_store.py",
    "tools/skills/code_query/launch.py",
    "tools/skills/code_query/gui-placeholder.txt",
    "cq.toml",
)


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scope() -> ModuleType:
    return _load(SCOPE_MODULE, "hve_scope")


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return _load(GENERATOR, "generate_tdd_inventory")


class TestScopeBoundary:
    @pytest.mark.parametrize("path", CQ_IN_SCOPE_SAMPLES)
    def test_cq_paths_are_in_scope(self, scope: ModuleType, path: str) -> None:
        assert scope.is_in_scope(path) is True
        assert scope.is_out_of_scope(path) is False

    def test_cq_tests_belong_to_the_test_inventory(self, generator: ModuleType) -> None:
        assert generator.category_for_test_path("cq/tests/test_store.py") is not None

    def test_cq_implementation_is_a_core_surface(self, generator: ModuleType) -> None:
        assert generator.surface_for_path("cq/store.py") == "core"


class TestRequirementBootstrap:
    @pytest.mark.parametrize("requirement_id", REQUIREMENT_IDS)
    def test_defined_in_requirement_definition(self, requirement_id: str) -> None:
        text = DEFINITION.read_text(encoding="utf-8")
        assert re.search(rf"\*\*{re.escape(requirement_id)}\*\*", text), requirement_id

    @pytest.mark.parametrize("requirement_id", REQUIREMENT_IDS)
    def test_has_a_mapping_section(self, requirement_id: str) -> None:
        text = MAPPING.read_text(encoding="utf-8")
        assert re.search(rf"^#### {re.escape(requirement_id)} — ", text, re.M), requirement_id

    @pytest.mark.parametrize("requirement_id", REQUIREMENT_IDS)
    def test_indexed_as_active(self, requirement_id: str) -> None:
        with FEATURE_INVENTORY.open(encoding="utf-8-sig", newline="") as handle:
            rows = [r for r in csv.DictReader(handle) if r["feature_id"] == requirement_id]
        assert rows, f"{requirement_id} is missing from hve-feature-inventory.csv"
        assert all(r["source"] == "hve-dev/requirement-definition.md" for r in rows)
        assert all(r["active_status"] == "active-or-described" for r in rows)

    def test_scope_separation_from_markdown_query_is_normative(self) -> None:
        """cq が .md / CSV を索引しないこと（mdq との責務分離）を要件本文で固定する。"""
        text = DEFINITION.read_text(encoding="utf-8")
        match = re.search(r"^### 3\.9 .*?(?=^### |\Z)", text, re.M | re.S)
        assert match, "§3.9 code-query section is missing"
        section = match.group(0)
        assert "`.md`" in section
        assert "mdq" in section
