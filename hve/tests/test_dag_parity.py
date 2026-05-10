"""DAG parity helper tests."""

from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from hve.dag_parity import (
    compare_step_definitions,
    compare_step_metadata,
    compare_workflow_id_sets,
    extract_bash_workflow_ids,
    extract_bash_workflow_steps,
    extract_reusable_workflow_ids,
)

# Shared path used by both unit and integration test classes.
# Resolved relative to this file so it is independent of the pytest working directory.
_BASH_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / ".github/scripts/bash/lib/workflow-registry.sh"
)


class TestDAGParity(unittest.TestCase):
    def test_extract_bash_workflow_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workflow-registry.sh"
            path.write_text(
                "_WORKFLOW_REGISTRY[aas]=x\n_WORKFLOW_REGISTRY[aad]=x\n",
                encoding="utf-8",
            )

            self.assertEqual(extract_bash_workflow_ids(path), ("aad", "aas"))

    def test_extract_reusable_workflow_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workflow.yml"
            path.write_text(
                "python -m hve --workflow aad-web --foo bar\n"
                "python -m hve --workflow aqod\n",
                encoding="utf-8",
            )

            self.assertEqual(extract_reusable_workflow_ids([path]), ("aad-web", "aqod"))

    def test_compare_workflow_id_sets_classifies_alias_and_missing_registry(self) -> None:
        report = compare_workflow_id_sets(
            hve_ids=["aas", "aad-web", "aqod"],
            cloud_bash_ids=["aas", "aad"],
            reusable_workflow_ids=["aas", "aad-web", "aqod"],
        )

        self.assertEqual(report.by_classification("same")[0].workflow_id, "aas")
        self.assertEqual(report.by_classification("legacy-alias")[0].hve_id, "aad-web")
        self.assertEqual(report.by_classification("legacy-alias")[0].cloud_bash_id, "aad")
        self.assertEqual(report.by_classification("missing-bash-registry")[0].workflow_id, "aqod")


# ---------------------------------------------------------------------------
# Step-level parity tests (P2-1)
# ---------------------------------------------------------------------------

def _make_bash_registry(workflow_id: str, steps: list[dict]) -> str:
    """Build a minimal workflow-registry.sh snippet for testing."""
    wf_json = json.dumps({"id": workflow_id, "steps": steps})
    return (
        f"_WORKFLOW_REGISTRY[{workflow_id}]=$(cat <<'JSONEOF'\n"
        f"{wf_json}\n"
        "JSONEOF\n"
        ")\n"
    )


class TestExtractBashWorkflowSteps(unittest.TestCase):
    def _write_registry(self, tmpdir: str, content: str) -> Path:
        path = Path(tmpdir) / "workflow-registry.sh"
        path.write_text(content, encoding="utf-8")
        return path

    def test_extracts_non_container_step_ids(self) -> None:
        steps = [
            {"id": "1", "custom_agent": "AgentA", "depends_on": [], "is_container": False},
            {"id": "2", "custom_agent": None, "depends_on": [], "is_container": True},
            {"id": "3", "custom_agent": "AgentB", "depends_on": ["1"], "is_container": False},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_registry(tmpdir, _make_bash_registry("aas", steps))
            result = extract_bash_workflow_steps(path, "aas")
        self.assertEqual(result, ("1", "3"))

    def test_returns_empty_for_unknown_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_registry(tmpdir, _make_bash_registry("aas", []))
            result = extract_bash_workflow_steps(path, "nonexistent")
        self.assertEqual(result, ())

    def test_returns_empty_for_invalid_json(self) -> None:
        content = "_WORKFLOW_REGISTRY[bad]=$(cat <<'JSONEOF'\nnot-json\nJSONEOF\n)\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_registry(tmpdir, content)
            result = extract_bash_workflow_steps(path, "bad")
        self.assertEqual(result, ())

    def test_extracts_steps_for_real_bash_registry(self) -> None:
        """Smoke test against the actual workflow-registry.sh (aas workflow)."""
        if not _BASH_REGISTRY_PATH.exists():
            self.skipTest("workflow-registry.sh not found")
        steps = extract_bash_workflow_steps(_BASH_REGISTRY_PATH, "aas")
        self.assertGreater(len(steps), 0, "Expected at least one step in bash aas workflow")


class TestCompareStepDefinitions(unittest.TestCase):
    def test_in_sync_when_identical(self) -> None:
        result = compare_step_definitions("aas", "aas", ["1", "2", "3"], ["1", "2", "3"])
        self.assertTrue(result["in_sync"])
        self.assertEqual(result["bash_only"], [])
        self.assertEqual(result["hve_only"], [])
        self.assertEqual(result["common"], ["1", "2", "3"])

    def test_bash_only_steps(self) -> None:
        result = compare_step_definitions("aas", "aas", ["1", "2", "extra"], ["1", "2"])
        self.assertFalse(result["in_sync"])
        self.assertEqual(result["bash_only"], ["extra"])
        self.assertEqual(result["hve_only"], [])
        self.assertEqual(result["common"], ["1", "2"])

    def test_hve_only_steps(self) -> None:
        result = compare_step_definitions("aas", "aas", ["1", "2"], ["1", "2", "new"])
        self.assertFalse(result["in_sync"])
        self.assertEqual(result["bash_only"], [])
        self.assertEqual(result["hve_only"], ["new"])
        self.assertEqual(result["common"], ["1", "2"])

    def test_mixed_differences(self) -> None:
        result = compare_step_definitions(
            "wf-bash", "wf-hve",
            ["1", "2", "bash-extra"],
            ["1", "2", "hve-extra"],
        )
        self.assertFalse(result["in_sync"])
        self.assertEqual(result["bash_only"], ["bash-extra"])
        self.assertEqual(result["hve_only"], ["hve-extra"])
        self.assertEqual(result["common"], ["1", "2"])

    def test_workflow_ids_preserved_in_result(self) -> None:
        result = compare_step_definitions("bash-wf", "hve-wf", [], [])
        self.assertEqual(result["bash_workflow_id"], "bash-wf")
        self.assertEqual(result["hve_workflow_id"], "hve-wf")

    def test_empty_inputs_are_in_sync(self) -> None:
        result = compare_step_definitions("aas", "aas", [], [])
        self.assertTrue(result["in_sync"])
        self.assertEqual(result["common"], [])


class TestCompareStepMetadata(unittest.TestCase):
    def test_in_sync_when_metadata_matches(self) -> None:
        bash_steps = [{"id": "1", "custom_agent": "AgentA", "depends_on": []}]
        hve_steps = [{"id": "1", "custom_agent": "AgentA", "depends_on": []}]
        result = compare_step_metadata("aas", "aas", bash_steps, hve_steps)
        self.assertTrue(result["in_sync"])
        self.assertEqual(result["diffs"], [])

    def test_detects_custom_agent_diff(self) -> None:
        bash_steps = [{"id": "1", "custom_agent": "AgentA", "depends_on": []}]
        hve_steps = [{"id": "1", "custom_agent": "AgentB", "depends_on": []}]
        result = compare_step_metadata("aas", "aas", bash_steps, hve_steps)
        self.assertFalse(result["in_sync"])
        self.assertEqual(len(result["diffs"]), 1)
        self.assertEqual(result["diffs"][0]["field"], "custom_agent")
        self.assertEqual(result["diffs"][0]["bash"], "AgentA")
        self.assertEqual(result["diffs"][0]["hve"], "AgentB")

    def test_detects_depends_on_diff(self) -> None:
        bash_steps = [{"id": "2", "custom_agent": "X", "depends_on": ["1"]}]
        hve_steps = [{"id": "2", "custom_agent": "X", "depends_on": []}]
        result = compare_step_metadata("wf", "wf", bash_steps, hve_steps)
        self.assertFalse(result["in_sync"])
        diff = result["diffs"][0]
        self.assertEqual(diff["field"], "depends_on")
        self.assertEqual(diff["bash"], ["1"])
        self.assertEqual(diff["hve"], [])

    def test_depends_on_comparison_is_order_insensitive(self) -> None:
        bash_steps = [{"id": "3", "custom_agent": "A", "depends_on": ["1", "2"]}]
        hve_steps = [{"id": "3", "custom_agent": "A", "depends_on": ["2", "1"]}]
        result = compare_step_metadata("wf", "wf", bash_steps, hve_steps)
        self.assertTrue(result["in_sync"], "Order-insensitive depends_on comparison should be in_sync")

    def test_steps_only_in_one_side_are_not_compared(self) -> None:
        bash_steps = [{"id": "1", "custom_agent": "A", "depends_on": []}]
        hve_steps = [{"id": "2", "custom_agent": "B", "depends_on": []}]
        result = compare_step_metadata("wf", "wf", bash_steps, hve_steps)
        # No common steps → no diffs; in_sync is True (nothing to disagree on)
        self.assertTrue(result["in_sync"])
        self.assertEqual(result["diffs"], [])


class TestStepParityHelperBehavior(unittest.TestCase):
    def test_parse_bash_workflow_raises_on_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workflow-registry.sh"
            path.write_text(
                "_WORKFLOW_REGISTRY[aad]=$(cat <<'JSONEOF'\n"
                "{invalid}\n"
                "JSONEOF\n"
                ")\n",
                encoding="utf-8",
            )
            global _BASH_REGISTRY_PATH
            original_path = _BASH_REGISTRY_PATH
            try:
                _BASH_REGISTRY_PATH = path
                with self.assertRaisesRegex(AssertionError, "JSON parse failed"):
                    TestStepParityWithRealFiles._parse_bash_workflow("aad")
            finally:
                _BASH_REGISTRY_PATH = original_path

    def test_closure_map_raises_on_cycle(self) -> None:
        with self.assertRaisesRegex(AssertionError, "cycle detected in dependency graph"):
            TestStepParityWithRealFiles._closure_map(
                {
                    "1": {"depends_on": ["2"]},
                    "2": {"depends_on": ["1"]},
                }
            )


class TestStepParityWithRealFiles(unittest.TestCase):
    """Integration tests that compare actual bash and hve registries."""

    def setUp(self) -> None:
        if not _BASH_REGISTRY_PATH.exists():
            self.skipTest("workflow-registry.sh not found; skipping real-file parity test")

    def _hve_steps_for(self, workflow_id: str) -> list[str]:
        from hve.workflow_registry import get_workflow
        wf = get_workflow(workflow_id)
        if wf is None:
            return []
        return [s.id for s in wf.steps if not s.is_container]

    def test_aas_step_parity(self) -> None:
        bash_steps = extract_bash_workflow_steps(_BASH_REGISTRY_PATH, "aas")
        hve_steps = self._hve_steps_for("aas")
        missing = []
        if not bash_steps:
            missing.append("bash")
        if not hve_steps:
            missing.append("hve")
        if missing:
            self.fail(
                "aas workflow missing from registry: " + ", ".join(missing)
            )
        result = compare_step_definitions("aas", "aas", list(bash_steps), hve_steps)
        self.assertTrue(
            result["in_sync"],
            f"aas step parity mismatch — bash_only={result['bash_only']}, "
            f"hve_only={result['hve_only']}",
        )

    @staticmethod
    def _parse_bash_workflow(workflow_key: str) -> dict[str, Any] | None:
        text = _BASH_REGISTRY_PATH.read_text(encoding="utf-8")
        pattern = (
            r"_WORKFLOW_REGISTRY\[" + re.escape(workflow_key) + r"\]=\$\(cat <<'JSONEOF'\n"
            r"(.*?)\nJSONEOF"
        )
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"bash workflow '{workflow_key}' JSON parse failed: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise AssertionError(
                f"bash workflow '{workflow_key}' payload must be object: got {type(parsed).__name__}"
            )
        return parsed

    @staticmethod
    def _resolve_bash_workflow(candidates: tuple[str, ...]) -> tuple[str, dict[str, Any]] | None:
        for key in candidates:
            parsed = TestStepParityWithRealFiles._parse_bash_workflow(key)
            if parsed is not None:
                return key, parsed
        return None

    @staticmethod
    def _is_work_iq_step(step_data: Mapping[str, Any]) -> bool:
        haystacks = [
            str(step_data.get("id", "")),
            str(step_data.get("title", "")),
            str(step_data.get("custom_agent", "")),
            str(step_data.get("type", "")),
        ]
        normalized = " ".join(haystacks).lower()
        return "work iq" in normalized or "work_iq" in normalized or "work-iq" in normalized

    @staticmethod
    def _to_filtered_step_map(
        raw_steps: list[Mapping[str, Any]],
        *,
        strip_work_iq: bool,
    ) -> dict[str, dict[str, Any]]:
        filtered: dict[str, dict[str, Any]] = {}
        for step in raw_steps:
            if step.get("is_container", False):
                continue
            step_id = step.get("id")
            if not isinstance(step_id, str):
                continue
            if strip_work_iq and TestStepParityWithRealFiles._is_work_iq_step(step):
                continue
            filtered[step_id] = {
                "id": step_id,
                "depends_on": list(step.get("depends_on", [])),
                "title": step.get("title"),
                "custom_agent": step.get("custom_agent"),
                "body_template_path": step.get("body_template_path"),
                "skip_fallback_deps": sorted(
                    dep for dep in step.get("skip_fallback_deps", [])
                    if isinstance(dep, str)
                ),
                "block_unless": sorted(
                    dep for dep in step.get("block_unless", [])
                    if isinstance(dep, str)
                ),
            }
        return filtered

    @staticmethod
    def _closure_map(step_map: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
        deps_by_id: dict[str, set[str]] = {
            step_id: {
                dep for dep in step_data.get("depends_on", [])
                if isinstance(dep, str) and dep in step_map
            }
            for step_id, step_data in step_map.items()
        }
        cache: dict[str, set[str]] = {}

        def _closure(step_id: str, path: tuple[str, ...]) -> set[str]:
            if step_id in cache:
                return cache[step_id]
            if step_id in path:
                cycle_path = " -> ".join([*path, step_id])
                raise AssertionError(
                    f"cycle detected in dependency graph: {cycle_path}"
                )
            direct = deps_by_id.get(step_id, set())
            all_deps = set(direct)
            next_path = (*path, step_id)
            for dep in direct:
                all_deps.update(_closure(dep, next_path))
            cache[step_id] = all_deps
            return all_deps

        return {
            step_id: sorted(_closure(step_id, tuple()))
            for step_id in sorted(step_map)
        }

    def _xfail(self, reason: str) -> None:
        if "PYTEST_CURRENT_TEST" not in os.environ:
            self.skipTest(f"XFAIL: {reason}")
            return
        import pytest

        pytest.xfail(reason)

    def _compare_dag_parity(
        self,
        *,
        name: str,
        bash_candidates: tuple[str, ...],
        hve_workflow_key: str,
    ) -> None:
        resolved = self._resolve_bash_workflow(bash_candidates)
        if resolved is None:
            self._xfail(
                f"{name}: bash workflow key not found in workflow-registry.sh "
                f"(candidates={bash_candidates})"
            )
            return
        bash_workflow_key, bash_workflow = resolved
        from hve.workflow_registry import get_workflow

        hve_workflow = get_workflow(hve_workflow_key)
        if hve_workflow is None:
            self._xfail(f"{name}: hve workflow '{hve_workflow_key}' not found")
            return

        bash_step_map = self._to_filtered_step_map(
            [s for s in bash_workflow.get("steps", []) if isinstance(s, dict)],
            strip_work_iq=False,
        )
        hve_step_map = self._to_filtered_step_map(
            [
                {
                    "id": s.id,
                    "depends_on": list(s.depends_on),
                    "is_container": s.is_container,
                    "title": s.title,
                    "custom_agent": s.custom_agent,
                    "body_template_path": s.body_template_path,
                    "skip_fallback_deps": sorted(s.skip_fallback_deps),
                    "block_unless": sorted(s.block_unless),
                }
                for s in hve_workflow.steps
            ],
            strip_work_iq=True,
        )

        id_diff = compare_step_definitions(
            bash_workflow_key,
            hve_workflow.id,
            list(bash_step_map.keys()),
            list(hve_step_map.keys()),
        )
        self.assertTrue(
            id_diff["in_sync"],
            f"{name}: step ID mismatch — bash_only={id_diff['bash_only']}, "
            f"hve_only={id_diff['hve_only']}",
        )

        bash_closure = self._closure_map(bash_step_map)
        hve_closure = self._closure_map(hve_step_map)
        closure_diff: dict[str, dict[str, list[str]]] = {}
        for step_id in sorted(set(bash_closure) & set(hve_closure)):
            if bash_closure[step_id] != hve_closure[step_id]:
                closure_diff[step_id] = {
                    "bash": bash_closure[step_id],
                    "hve": hve_closure[step_id],
                }
        self.assertEqual(
            closure_diff,
            {},
            f"{name}: dependency closure mismatch — {closure_diff}",
        )

        attrs_diff: dict[str, dict[str, dict[str, Any]]] = {}
        for step_id in sorted(set(bash_step_map) & set(hve_step_map)):
            step_diff: dict[str, dict[str, Any]] = {}
            for key in (
                "id",
                "title",
                "custom_agent",
                "body_template_path",
                "skip_fallback_deps",
                "block_unless",
            ):
                b = bash_step_map[step_id].get(key)
                h = hve_step_map[step_id].get(key)
                if b != h:
                    step_diff[key] = {"bash": b, "hve": h}
            if step_diff:
                attrs_diff[step_id] = step_diff
        self.assertEqual(
            attrs_diff,
            {},
            f"{name}: shared attribute mismatch — {attrs_diff}",
        )

    def test_dag_parity_aad(self) -> None:
        self._compare_dag_parity(
            name="aad",
            bash_candidates=("aad-web", "aad"),
            hve_workflow_key="aad-web",
        )

    def test_dag_parity_asdw(self) -> None:
        self._compare_dag_parity(
            name="asdw",
            bash_candidates=("asdw-web", "asdw"),
            hve_workflow_key="asdw-web",
        )


if __name__ == "__main__":
    unittest.main()
