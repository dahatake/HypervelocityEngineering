"""FR-PROMPT-06 — 複数 Workflow の依存順安定ソートを GUI と共有する契約テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.workflow_order import sort_workflows_by_dependencies
from hve.workflow_registry import get_meta_dependencies, list_workflows


class TestBasicOrdering:
    def test_empty_and_single(self):
        assert sort_workflows_by_dependencies([]) == []
        assert sort_workflows_by_dependencies(["ard"]) == ["ard"]

    def test_drops_empty_entries(self):
        assert sort_workflows_by_dependencies(["", "ard", ""]) == ["ard"]

    def test_dependency_comes_first(self):
        """`aad-web` は `aas` に依存するため、逆順で渡しても `aas` が先になる。"""
        deps = {d.workflow_id for d in get_meta_dependencies("aad-web")}
        assert "aas" in deps, "前提: aad-web は aas に依存する"
        assert sort_workflows_by_dependencies(["aad-web", "aas"]) == ["aas", "aad-web"]

    def test_is_stable_for_independent_workflows(self):
        selected = ["adoc", "akm"]
        assert sort_workflows_by_dependencies(selected) == selected
        assert sort_workflows_by_dependencies(list(reversed(selected))) == list(
            reversed(selected)
        )

    def test_does_not_add_unselected_dependencies(self):
        assert sort_workflows_by_dependencies(["aad-web"]) == ["aad-web"]

    def test_all_registry_workflows_are_orderable(self):
        ids = [w.id for w in list_workflows()]
        ordered = sort_workflows_by_dependencies(ids)
        assert sorted(ordered) == sorted(ids)


class TestCycleDetection:
    def test_raises_value_error_on_cycle(self, monkeypatch: pytest.MonkeyPatch):
        from types import SimpleNamespace

        import hve.workflow_order as mod

        cycle = {
            "a": [SimpleNamespace(workflow_id="b")],
            "b": [SimpleNamespace(workflow_id="a")],
        }
        monkeypatch.setattr(mod, "get_meta_dependencies", lambda wf: cycle.get(wf, []))
        with pytest.raises(ValueError):
            mod.sort_workflows_by_dependencies(["a", "b"])


class TestGuiParity:
    def test_gui_delegates_to_the_shared_core(self):
        """GUI 側は複製実装を持たず共通 core へ委譲する（FR-MAINT-07）。"""
        source = Path("hve/gui/main_window.py").read_text(encoding="utf-8")
        assert "from ..workflow_order import" in source or "workflow_order" in source
        assert "循環依存があります" not in source, "循環検出は共通 core が所有する"

    def test_gui_function_returns_the_same_order(self):
        pytest.importorskip("PySide6")
        from hve.gui.main_window import _sort_workflows_by_dependencies

        ids = [w.id for w in list_workflows()]
        assert _sort_workflows_by_dependencies(ids) == sort_workflows_by_dependencies(ids)


class TestRequirementIsDeclared:
    def test_fr_prompt_06_is_declared(self):
        text = Path("hve-dev/requirement-definition.md").read_text(encoding="utf-8")
        assert "**FR-PROMPT-06**" in text
