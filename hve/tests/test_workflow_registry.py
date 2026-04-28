"""test_workflow_registry.py — hve/workflow_registry.py のテスト"""

import pytest

from hve.workflow_registry import (
    MetaWorkflowDef,
    StepDef,
    WorkflowDef,
    WorkflowDependency,
    get_meta_dependencies,
    get_next_steps,
    get_root_steps,
    get_step,
    get_workflow,
    list_workflows,
)


# ---------------------------------------------------------------------------
# ステップ数定義
# ---------------------------------------------------------------------------

EXPECTED_STEP_COUNTS = {
    "aas": 8,
    "aad-web": 4,
    "asdw-web": 19,  # 4 containers + 15 real steps
    "abd": 9,
    "abdv": 7,
    "aag": 3,
    "aagd": 5,
    "akm": 1,
    "aqod": 1,
    "adoc": 23,  # 4 containers + 19 real steps
}

EXPECTED_NON_CONTAINER_COUNTS = {
    "aas": 8,
    "aad-web": 4,
    "asdw-web": 15,
    "abd": 9,
    "abdv": 7,
    "aag": 3,
    "aagd": 5,
    "akm": 1,
    "aqod": 1,
    "adoc": 19,
}

CANONICAL_WORKFLOW_IDS = list(EXPECTED_STEP_COUNTS.keys())


class TestGetWorkflow:
    """get_workflow() のテスト。"""

    @pytest.mark.parametrize("wf_id", CANONICAL_WORKFLOW_IDS)
    def test_get_all_workflows(self, wf_id: str):
        wf = get_workflow(wf_id)
        assert wf is not None
        assert wf.id == wf_id

    def test_get_workflow_case_insensitive(self):
        wf = get_workflow("AAS")
        assert wf is not None
        assert wf.id == "aas"

    @pytest.mark.parametrize(
        "alias,expected",
        [
            ("aad", "aad-web"),
            ("asdw", "asdw-web"),
            ("aad_web", "aad-web"),
            ("asdw_web", "asdw-web"),
        ],
    )
    def test_get_workflow_aliases(self, alias: str, expected: str):
        wf = get_workflow(alias)
        assert wf is not None
        assert wf.id == expected

    def test_get_workflow_unknown(self):
        assert get_workflow("unknown") is None

    @pytest.mark.parametrize("wf_id", CANONICAL_WORKFLOW_IDS)
    def test_step_count_matches_expected(self, wf_id: str):
        wf = get_workflow(wf_id)
        assert wf is not None
        assert len(wf.steps) == EXPECTED_STEP_COUNTS[wf_id]

    @pytest.mark.parametrize("wf_id", CANONICAL_WORKFLOW_IDS)
    def test_non_container_count(self, wf_id: str):
        wf = get_workflow(wf_id)
        assert wf is not None
        actual = len([s for s in wf.steps if not s.is_container])
        assert actual == EXPECTED_NON_CONTAINER_COUNTS[wf_id]


class TestWorkflowDef:
    """WorkflowDef のメソッドテスト。"""

    def test_get_step_existing(self):
        wf = get_workflow("aas")
        step = wf.get_step("1")
        assert step is not None
        assert step.title == "アプリケーションリストの作成"

    def test_get_step_nonexistent(self):
        wf = get_workflow("aas")
        assert wf.get_step("999") is None

    def test_duplicate_step_id_raises(self):
        with pytest.raises(ValueError, match="duplicate step id"):
            WorkflowDef(
                id="test",
                name="Test",
                label_prefix="test",
                state_labels={},
                params=[],
                steps=[
                    StepDef(id="1", title="A", custom_agent=None),
                    StepDef(id="1", title="B", custom_agent=None),
                ],
            )

    def test_state_labels(self):
        wf = get_workflow("aas")
        assert wf.state_labels["initialized"] == "aas:initialized"
        assert wf.state_labels["done"] == "aas:done"

    def test_params_asdw_web(self):
        wf = get_workflow("asdw-web")
        assert "app_ids" in wf.params
        assert "app_id" in wf.params
        assert "resource_group" in wf.params
        assert "usecase_id" in wf.params

    def test_params_aad_web(self):
        wf = get_workflow("aad-web")
        assert wf.params == ["app_ids", "app_id"]

    def test_params_aag(self):
        wf = get_workflow("aag")
        assert wf.params == ["app_ids", "app_id", "usecase_id"]

    def test_params_aagd(self):
        wf = get_workflow("aagd")
        assert wf.params == ["app_ids", "app_id", "resource_group", "usecase_id"]

    def test_params_abdv(self):
        wf = get_workflow("abdv")
        assert "app_ids" in wf.params
        assert "app_id" in wf.params
        assert "resource_group" in wf.params
        assert "batch_job_id" in wf.params

    def test_params_abd(self):
        wf = get_workflow("abd")
        assert "app_ids" in wf.params
        assert "app_id" in wf.params


class TestGetRootSteps:
    """get_root_steps() のテスト。"""

    def test_aas_roots(self):
        roots = get_root_steps("aas")
        assert [s.id for s in roots] == ["1"]

    def test_aad_web_roots(self):
        roots = get_root_steps("aad-web")
        assert [s.id for s in roots] == ["1"]

    def test_aag_roots(self):
        roots = get_root_steps("aag")
        assert [s.id for s in roots] == ["1"]

    def test_aagd_roots(self):
        roots = get_root_steps("aagd")
        assert [s.id for s in roots] == ["1"]

    def test_abd_roots(self):
        roots = get_root_steps("abd")
        root_ids = sorted(s.id for s in roots)
        assert root_ids == ["1.1", "1.2"]

    def test_unknown_workflow(self):
        assert get_root_steps("nonexistent") == []


class TestGetNextSteps:
    """get_next_steps() のテスト — DAG 走査ロジック。"""

    def test_aas_expanded_dag_walk(self):
        assert [s.id for s in get_next_steps("aas", completed_step_ids=[])] == ["1"]
        assert [s.id for s in get_next_steps("aas", completed_step_ids=["1"])] == ["2"]
        assert [s.id for s in get_next_steps("aas", completed_step_ids=["1", "2"])] == ["3.1"]
        assert [s.id for s in get_next_steps("aas", completed_step_ids=["1", "2", "3.1"])] == ["3.2"]
        assert [s.id for s in get_next_steps("aas", completed_step_ids=["1", "2", "3.1", "3.2"])] == ["4"]
        assert [s.id for s in get_next_steps("aas", completed_step_ids=["1", "2", "3.1", "3.2", "4"])] == ["5"]
        assert [s.id for s in get_next_steps("aas", completed_step_ids=["1", "2", "3.1", "3.2", "4", "5"])] == ["6"]
        assert [s.id for s in get_next_steps("aas", completed_step_ids=["1", "2", "3.1", "3.2", "4", "5", "6"])] == ["7"]

    def test_aad_web_dag_walk(self):
        assert [s.id for s in get_next_steps("aad-web", completed_step_ids=[])] == ["1"]

        nexts = get_next_steps("aad-web", completed_step_ids=["1"])
        assert sorted(s.id for s in nexts) == ["2.1", "2.2"]

        nexts = get_next_steps("aad-web", completed_step_ids=["1", "2.1"])
        assert [s.id for s in nexts] == ["2.2"]

        nexts = get_next_steps("aad-web", completed_step_ids=["1", "2.1", "2.2"])
        assert [s.id for s in nexts] == ["2.3"]

    def test_asdw_web_dag_walk_and_bypass_agent_chain(self):
        step_30t = get_step("asdw-web", "3.0T")
        assert step_30t is not None
        assert step_30t.depends_on == ["2.5"]
        assert step_30t.skip_fallback_deps == ["2.5"]

        assert get_step("asdw-web", "2.6") is None
        assert get_step("asdw-web", "2.7") is None
        assert get_step("asdw-web", "2.8") is None

        completed = ["1.1", "1.2", "2.1", "2.2", "2.3", "2.3T", "2.3TC", "2.4", "2.5"]
        nexts = get_next_steps("asdw-web", completed_step_ids=completed)
        assert [s.id for s in nexts] == ["3.0T"]

    def test_aag_dag_walk(self):
        assert [s.id for s in get_next_steps("aag", completed_step_ids=[])] == ["1"]
        assert [s.id for s in get_next_steps("aag", completed_step_ids=["1"])] == ["2"]
        assert [s.id for s in get_next_steps("aag", completed_step_ids=["1", "2"])] == ["3"]

    def test_aagd_dag_walk(self):
        assert [s.id for s in get_next_steps("aagd", completed_step_ids=[])] == ["1"]
        assert [s.id for s in get_next_steps("aagd", completed_step_ids=["1"])] == ["2.1"]
        assert [s.id for s in get_next_steps("aagd", completed_step_ids=["1", "2.1"])] == ["2.2"]
        assert [s.id for s in get_next_steps("aagd", completed_step_ids=["1", "2.1", "2.2"])] == ["2.3"]
        assert [s.id for s in get_next_steps("aagd", completed_step_ids=["1", "2.1", "2.2", "2.3"])] == ["3"]

    def test_aagd_agent_steps_present(self):
        assert get_step("aagd", "1").custom_agent == "Arch-AIAgentDesign"
        assert get_step("aagd", "2.3").custom_agent == "Dev-Microservice-Azure-AgentCoding"
        assert get_step("aagd", "3").custom_agent == "Dev-Microservice-Azure-AgentDeploy"

    def test_and_join(self):
        nexts = get_next_steps("abd", completed_step_ids=["1.1"])
        next_ids = [s.id for s in nexts]
        assert "2" not in next_ids
        assert "1.2" in next_ids

        nexts = get_next_steps("abd", completed_step_ids=["1.1", "1.2"])
        next_ids = [s.id for s in nexts]
        assert "2" in next_ids

    def test_skipped_resolves_dependency(self):
        nexts = get_next_steps(
            "abd",
            completed_step_ids=["1.1"],
            skipped_step_ids=["1.2"],
        )
        next_ids = [s.id for s in nexts]
        assert "2" in next_ids

    def test_nonexistent_dep_auto_resolves(self):
        wf = WorkflowDef(
            id="test",
            name="Test",
            label_prefix="test",
            state_labels={},
            params=[],
            steps=[
                StepDef(id="A", title="A", custom_agent=None, depends_on=["GHOST"]),
            ],
        )
        nexts = wf.get_next_steps(completed_step_ids=[])
        assert [s.id for s in nexts] == ["A"]

    def test_containers_excluded(self):
        nexts = get_next_steps("asdw-web", completed_step_ids=[])
        next_ids = [s.id for s in nexts]
        assert "1" not in next_ids
        assert "2" not in next_ids
        assert "3" not in next_ids
        assert "4" not in next_ids

    def test_unknown_workflow(self):
        assert get_next_steps("nonexistent", completed_step_ids=[]) == []


class TestGetStep:
    """モジュールレベル get_step() のテスト。"""

    def test_existing(self):
        step = get_step("asdw-web", "2.3T")
        assert step is not None
        assert step.custom_agent == "Arch-TDD-TestSpec"

    def test_nonexistent_step(self):
        assert get_step("aas", "999") is None

    def test_nonexistent_workflow(self):
        assert get_step("nonexistent", "1") is None


class TestListWorkflows:
    """list_workflows() のテスト。"""

    def test_all_ids_are_present(self):
        workflows = list_workflows()
        wf_ids = [wf.id for wf in workflows]

        assert len(workflows) == len(CANONICAL_WORKFLOW_IDS)
        assert len(wf_ids) == len(set(wf_ids))
        assert set(wf_ids) == set(CANONICAL_WORKFLOW_IDS)


class TestMetaWorkflow:
    """MetaWorkflowDef / WorkflowDependency のテスト。"""

    def test_meta_dataclasses_constructible(self):
        dep = WorkflowDependency(workflow_id="aas", required_artifacts=["docs/catalog/*.md"], soft=True)
        mwf = MetaWorkflowDef(
            id="meta",
            workflows=["aas"],
            dependencies={"aas": [dep]},
        )
        assert mwf.dependencies["aas"][0].workflow_id == "aas"
        assert mwf.dependencies["aas"][0].soft is True

    def test_get_meta_dependencies_for_aad_web(self):
        deps = get_meta_dependencies("aad-web")
        assert len(deps) == 1
        assert deps[0].workflow_id == "aas"
        assert "docs/catalog/app-catalog.md" in deps[0].required_artifacts

    def test_get_meta_dependencies_for_alias(self):
        deps = get_meta_dependencies("asdw")
        assert len(deps) == 1
        assert deps[0].workflow_id == "aad-web"

    def test_get_meta_dependencies_unknown(self):
        assert get_meta_dependencies("unknown") == []


class TestAKMWorkflow:
    """AKM ワークフロー固有テスト。"""

    def test_akm_params(self):
        wf = get_workflow("akm")
        assert wf is not None
        assert wf.params == ["sources", "target_files", "force_refresh", "custom_source_dir", "enable_auto_merge"]

    @pytest.mark.parametrize("sources", ["qa", "original-docs", "both"])
    def test_akm_sources_values_documented(self, sources: str):
        assert sources in ["qa", "original-docs", "both"]

    def test_akm_single_step(self):
        wf = get_workflow("akm")
        assert wf is not None
        assert len(wf.steps) == 1
        assert wf.steps[0].id == "1"


class TestAQODWorkflow:
    """AQOD ワークフロー固有テスト。"""

    def test_aqod_params(self):
        wf = get_workflow("aqod")
        assert wf is not None
        assert wf.params == ["target_scope", "depth", "focus_areas"]

    def test_aqod_single_step(self):
        wf = get_workflow("aqod")
        assert wf is not None
        assert len(wf.steps) == 1
        assert wf.steps[0].id == "1"


class TestADOCWorkflow:
    """ADOC ワークフロー固有テスト。"""

    def test_adoc_params(self):
        wf = get_workflow("adoc")
        assert wf is not None
        assert "target_dirs" in wf.params
        assert "exclude_patterns" in wf.params
        assert "doc_purpose" in wf.params
        assert "max_file_lines" in wf.params

    def test_adoc_root_step(self):
        roots = get_root_steps("adoc")
        assert len(roots) == 1
        assert roots[0].id == "1"


class TestStepDefFields:
    """StepDef の各フィールドが正しく設定されていること。"""

    def test_template_path(self):
        step = get_step("aas", "1")
        assert step.body_template_path == "templates/aas/step-1.md"

    def test_skip_fallback_deps(self):
        step = get_step("aas", "5")
        assert step.skip_fallback_deps == ["4"]

    def test_block_unless_empty(self):
        step = get_step("aas", "1")
        assert step.block_unless == []
