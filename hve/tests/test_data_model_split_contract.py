"""FR-WF-DM-01: AAS/ADA Data Model親 + canonical sidecar契約。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from hve.orchestrator import collect_workflow_output_paths
from hve.orchestrator_context import OrchestratorContext
from hve.runner import _check_output_paths_gate
from hve.workflow_registry import get_step, get_workflow

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPT = _REPO_ROOT / ".github" / "prompts" / "Arch-DataModeling.prompt.md"
_TEMPLATES = _REPO_ROOT / ".github" / "scripts" / "templates"
_IO_CONTRACTS = _REPO_ROOT / ".github" / "io-contracts"
_PARENT = "docs/catalog/data-model.md"
_SIDECARS = (
    "docs/catalog/data-model-service-stores.md",
    "docs/catalog/data-model-consistency-events.md",
    "docs/catalog/data-model-diagrams.md",
)
_WORKFLOW_IDS = ("aas", "ada")
_WORKFLOW_STEP_IDS = (("aas", "3.1"), ("ada", "4.1"))
_THRESHOLD_RE = re.compile(r"(?<![\d,])50,000(?![\d,])\s*文字")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _contract(workflow_id: str, step_id: str) -> dict:
    path = _IO_CONTRACTS / f"Arch-DataModeling--{workflow_id}--{step_id}.yaml"
    return yaml.safe_load(_read(path))


def _section(body: str, heading: str, next_heading_prefix: str) -> str:
    assert body.count(heading) == 1
    start = body.index(heading) + len(heading)
    match = re.search(rf"(?m)^{re.escape(next_heading_prefix)}", body[start:])
    end = start + match.start() if match else len(body)
    return body[start:end]


def _split_contract(body: str) -> str:
    return _section(body, "### 3.3.1 成果物の分割ルール", "### 3.4 ")


class TestPromptDeclaresSplitContract:
    @pytest.fixture
    def body(self) -> str:
        return _read(_PROMPT)

    def test_declares_50000_character_threshold(self, body: str) -> None:
        assert _THRESHOLD_RE.search(_split_contract(body))

    def test_lists_all_canonical_sidecars(self, body: str) -> None:
        section = _split_contract(body)
        assert [path for path in _SIDECARS if path not in section] == []

    def test_forbids_app_id_sidecar_splitting(self, body: str) -> None:
        section = _split_contract(body)
        assert not re.search(
            r"APP-ID.{0,12}(?:単位|ごと).{0,12}(?:分割|切り出)", section
        )
        assert not re.search(r"data-model-app-\d+", section, re.IGNORECASE)

    def test_requires_parent_and_sidecar_cross_links(self, body: str) -> None:
        section = _split_contract(body)
        assert "索引/統合版" in section
        assert _PARENT in section
        assert re.search(
            r"親(?:ファイル|成果物)?.{0,80}(?:各\s*)?sidecar.{0,80}(?:リンク|参照)",
            section,
            re.IGNORECASE | re.DOTALL,
        )
        assert re.search(
            r"(?:各\s*)?sidecar.{0,80}親(?:ファイル|成果物)?.{0,80}(?:リンク|参照)",
            section,
            re.IGNORECASE | re.DOTALL,
        )

    def test_requires_stale_sidecar_cleanup(self, body: str) -> None:
        section = _split_contract(body)
        assert re.search(
            r"(?:分割不要|非分割).{0,200}(?:stale|古い).{0,100}削除",
            section,
            re.IGNORECASE | re.DOTALL,
        )

    def test_parent_remains_self_contained_for_downstream_steps(self, body: str) -> None:
        section = _split_contract(body)
        assert "見出し `1`〜`6`" in section
        assert "下流 Step が親単独" in section
        for token in ("主キー", "主要制約", "代表インデックス", "主要イベント"):
            assert token in section

    def test_declares_data_model_specific_skill_precedence(self, body: str) -> None:
        assert "### Skill 適用境界" in body
        assert "app-scope-resolution" in body
        assert "large-output-chunking" in body
        assert "Data Model の固定3 sidecar契約" in body

    def test_split_contract_is_in_the_early_output_inventory(self, body: str) -> None:
        output = _section(body, "### A) モデリングドキュメント", "### B) ")
        assert "条件付き sidecar" in output
        assert "§3.3.1" in output

    def test_self_check_covers_partial_and_stale_split_artifacts(self, body: str) -> None:
        review = _section(body, "### 3.4.2 ドメイン固有観点", "### 3.4.3 ")
        assert "canonical sidecar 3件がすべて存在" in review
        assert "stale sidecar" in review


class TestRegistryDeclaresConditionalSidecars:
    @pytest.mark.parametrize("workflow_id,step_id", _WORKFLOW_STEP_IDS)
    def test_parent_is_the_only_required_output(self, workflow_id: str, step_id: str) -> None:
        step = get_step(workflow_id, step_id)
        assert step is not None
        assert step.custom_agent == "Arch-DataModeling"
        assert step.fanout_parser is None
        assert step.fanout_static_keys is None
        assert step.output_paths == [_PARENT]

    @pytest.mark.parametrize("workflow_id,step_id", _WORKFLOW_STEP_IDS)
    def test_sidecars_are_declared_on_the_nonfanout_template_surface(
        self, workflow_id: str, step_id: str
    ) -> None:
        step = get_step(workflow_id, step_id)
        assert step is not None
        assert set(step.output_paths_template or ()) == set(_SIDECARS)


class TestIoContractDeclaresConditionalSidecars:
    @pytest.mark.parametrize("workflow_id,step_id", _WORKFLOW_STEP_IDS)
    def test_parent_remains_required(self, workflow_id: str, step_id: str) -> None:
        outputs = {entry["path"]: entry for entry in _contract(workflow_id, step_id)["outputs"]}
        assert outputs[_PARENT]["required"] is True

    @pytest.mark.parametrize("workflow_id,step_id", _WORKFLOW_STEP_IDS)
    def test_sidecars_are_optional_upserts(self, workflow_id: str, step_id: str) -> None:
        outputs = {entry["path"]: entry for entry in _contract(workflow_id, step_id)["outputs"]}
        assert set(outputs) == {_PARENT, *_SIDECARS}
        for path in _SIDECARS:
            assert outputs[path]["required"] is False
            assert outputs[path]["mode"] == "upsert"

    @pytest.mark.parametrize("workflow_id,step_id", _WORKFLOW_STEP_IDS)
    def test_registry_and_io_contract_output_paths_match(self, workflow_id: str, step_id: str) -> None:
        step = get_step(workflow_id, step_id)
        assert step is not None
        registry_paths = set(step.output_paths or []) | set(step.output_paths_template or [])
        contract_paths = {entry["path"] for entry in _contract(workflow_id, step_id)["outputs"]}
        assert registry_paths == contract_paths


class TestTemplateDeclaresConditionalOutputs:
    @pytest.mark.parametrize("workflow_id,step_id", _WORKFLOW_STEP_IDS)
    def test_template_lists_threshold_and_sidecars(self, workflow_id: str, step_id: str) -> None:
        body = _read(_TEMPLATES / workflow_id / f"step-{step_id}.md")
        output = _section(body, "## 出力", "## ")
        assert _THRESHOLD_RE.search(output)
        assert [path for path in _SIDECARS if path not in output] == []
        assert "条件" in output
        assert re.search(
            r"(?:分割不要|非分割).{0,200}(?:stale|古い).{0,100}削除",
            output,
            re.IGNORECASE | re.DOTALL,
        )
        assert "下流 Step が親単独" in output
        assert "親から各 sidecar" in output
        assert "各 sidecar から親" in output

        completion = _section(body, "## 完了条件", "## ")
        assert "分割時は canonical sidecar 3件がすべて" in completion
        assert "分割不要時は canonical sidecar 3件が残っていない" in completion


class TestConditionalSidecarsStayOutOfRuntimeGates:
    """C2/D2/D3の前後でGREENを維持すべき非回帰ガード。"""
    @pytest.mark.parametrize("workflow_id,step_id", _WORKFLOW_STEP_IDS)
    def test_g_out_ignores_missing_optional_sidecars(
        self, workflow_id: str, step_id: str, tmp_path: Path
    ) -> None:
        workflow = get_workflow(workflow_id)
        assert workflow is not None
        parent = tmp_path / _PARENT
        parent.parent.mkdir(parents=True)
        parent.write_text("# Data Model\n", encoding="utf-8")
        assert _check_output_paths_gate(
            OrchestratorContext(), workflow, step_id, tmp_path
        ) == []

    @pytest.mark.parametrize("workflow_id", _WORKFLOW_IDS)
    def test_self_improve_scope_excludes_optional_sidecars(
        self, workflow_id: str, tmp_path: Path
    ) -> None:
        collected = collect_workflow_output_paths(workflow_id, repo_root=tmp_path)
        assert _PARENT in collected
        assert not set(_SIDECARS) & set(collected)
