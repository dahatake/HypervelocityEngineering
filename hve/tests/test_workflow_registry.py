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
    "ard": 7,
    "aas": 9,
    "aad-web": 5,
    "asdw-web": 20,  # 4 containers + 16 real steps
    "abd": 9,
    "abdv": 7,
    "aag": 3,
    "aagd": 5,
    "akm": 2,  # ADR-0002: fan-out base + cross-cutting review join
    "aqod": 2,  # ADR-0002 T4H: fan-out base + cross-cutting review join
    "adoc": 23,  # 4 containers + 19 real steps
}

EXPECTED_NON_CONTAINER_COUNTS = {
    "ard": 7,
    "aas": 9,
    "aad-web": 5,
    "asdw-web": 16,
    "abd": 9,
    "abdv": 7,
    "aag": 3,
    "aagd": 5,
    "akm": 2,  # ADR-0002: fan-out base + cross-cutting review join
    "aqod": 2,  # ADR-0002 T4H: fan-out base + cross-cutting review join
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
            # aad_web / asdw_web (snake_case) は Phase 9 で削除済み。
            # .github/ 配下から呼ばれる経路がないことを確認して削除。
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

    def test_params_asdw_web_includes_create_remote_mcp_server(self):
        """ASDW-WEB の params に create_remote_mcp_server が含まれること。"""
        wf = get_workflow("asdw-web")
        assert "create_remote_mcp_server" in wf.params

    def test_params_aad_web(self):
        wf = get_workflow("aad-web")
        assert wf.params == ["app_ids", "app_id", "create_remote_mcp_server"]

    def test_params_aag(self):
        wf = get_workflow("aag")
        assert wf.params == ["app_ids", "app_id", "usecase_id"]

    def test_params_aagd(self):
        wf = get_workflow("aagd")
        assert wf.params == ["app_ids", "app_id", "resource_group", "usecase_id", "tdd_max_retries"]

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

    def test_ard_steps_require_knowledge_management(self):
        wf = get_workflow("ard")
        assert wf is not None
        for step_id in ["1", "1.1", "1.2", "2", "3.1", "3.2", "3.3"]:
            step = wf.get_step(step_id)
            assert step is not None
            assert "knowledge-management" in step.required_skills


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
        # Sub-4 (B-1): Step 4 → 4.1 / 4.2 に分割
        assert [s.id for s in get_next_steps("aas", completed_step_ids=[])] == ["1"]
        assert [s.id for s in get_next_steps("aas", completed_step_ids=["1"])] == ["2"]
        assert [s.id for s in get_next_steps("aas", completed_step_ids=["1", "2"])] == ["3.1"]
        assert [s.id for s in get_next_steps("aas", completed_step_ids=["1", "2", "3.1"])] == ["3.2"]
        assert [s.id for s in get_next_steps("aas", completed_step_ids=["1", "2", "3.1", "3.2"])] == ["4.1"]
        # Step 4.1 完了後は 4.2 と 5 が並列起動可能（5 は depends_on=["4.1"]）
        nexts = sorted(s.id for s in get_next_steps(
            "aas", completed_step_ids=["1", "2", "3.1", "3.2", "4.1"]
        ))
        assert nexts == ["4.2", "5"]
        # 4.2 と 5 が完了したら 6 が走り、その後 7
        assert [s.id for s in get_next_steps(
            "aas", completed_step_ids=["1", "2", "3.1", "3.2", "4.1", "4.2", "5"]
        )] == ["6"]
        assert [s.id for s in get_next_steps(
            "aas", completed_step_ids=["1", "2", "3.1", "3.2", "4.1", "4.2", "5", "6"]
        )] == ["7"]

    def test_aas_step42_and_step5_are_parallel(self):
        """Sub-5 (C-1 部分): Step 4.2 (サンプルデータ) と Step 5 (データカタログ) が
        Step 4.1 完了後に並列起動可能であることを保証する。

        Sub-4 で導入された並列性が将来の DAG 変更で失われないことを回帰防止する。
        """
        step_42 = get_step("aas", "4.2")
        step_5 = get_step("aas", "5")
        # 両方とも 4.1 のみに依存（互いに依存しない）
        assert step_42.depends_on == ["4.1"]
        assert step_5.depends_on == ["4.1"]
        # get_next_steps 経由でも並列に取得できる
        nexts = sorted(
            s.id for s in get_next_steps(
                "aas", completed_step_ids=["1", "2", "3.1", "3.2", "4.1"]
            )
        )
        assert "4.2" in nexts and "5" in nexts

    def test_abd_step61_and_step62_are_parallel(self):
        """Sub-6 (C-3 確認): ABD の Step 6.1 (ジョブ詳細仕様) と Step 6.2 (監視・運用設計) が
        Step 5 完了後に並列起動可能であることを保証する（既存挙動の回帰防止）。

        Sub-6 当初プランでは Step 6.3 も並列化する案だったが、Step 6.3 は consumed_artifacts に
        ``batch_job_specs`` (= Step 6.1 fan-out 子の出力) を含むため、現状の AND 結合
        (depends_on=["6.1", "6.2"]) を維持する。
        """
        step_61 = get_step("abd", "6.1")
        step_62 = get_step("abd", "6.2")
        step_63 = get_step("abd", "6.3")
        assert step_61.depends_on == ["5"]
        assert step_62.depends_on == ["5"]
        # 6.3 は 6.1 と 6.2 の両方に依存（batch_job_specs が必須）
        assert sorted(step_63.depends_on) == ["6.1", "6.2"]
        # 6.1 / 6.2 は同 wave で並列起動可能
        nexts = sorted(
            s.id for s in get_next_steps(
                "abd", completed_step_ids=["1.1", "1.2", "2", "3", "4", "5"]
            )
        )
        assert "6.1" in nexts and "6.2" in nexts

    def test_aad_web_dag_walk(self):
        assert [s.id for s in get_next_steps("aad-web", completed_step_ids=[])] == ["1"]

        nexts = get_next_steps("aad-web", completed_step_ids=["1"])
        assert sorted(s.id for s in nexts) == ["2.1", "2.2"]

        nexts = get_next_steps("aad-web", completed_step_ids=["1", "2.1"])
        assert [s.id for s in nexts] == ["2.2"]

        nexts = get_next_steps("aad-web", completed_step_ids=["1", "2.1", "2.2"])
        assert [s.id for s in nexts] == ["2.3"]

        # Sub-7 (C-4): 2.1/2.2/2.3 完了後に Step 3（整合性レビュー join）が起動可能
        nexts = get_next_steps("aad-web", completed_step_ids=["1", "2.1", "2.2", "2.3"])
        assert [s.id for s in nexts] == ["3"]

    def test_aad_web_step3_is_consistency_review_join(self):
        """Sub-7 (C-4): AAD-WEB Step 3 が screen ↔ service 整合性レビュー join step として
        正しく定義されていること。"""
        step = get_step("aad-web", "3")
        assert step is not None
        assert step.custom_agent == "QA-DocConsistency"
        # AND join: 2.1, 2.2, 2.3 が全て完了して初めて起動
        assert sorted(step.depends_on) == ["2.1", "2.2", "2.3"]
        assert step.output_paths == ["docs/catalog/screen-service-consistency-report.md"]
        # 整合性レビューは fan-out しない（join step）
        assert step.fanout_static_keys is None
        assert step.fanout_parser is None

    def test_asdw_web_dag_walk_and_bypass_agent_chain(self):
        step_30t = get_step("asdw-web", "3.0T")
        assert step_30t is not None
        assert step_30t.depends_on == ["2.5"]
        assert step_30t.skip_fallback_deps == ["2.5"]
        step_33 = get_step("asdw-web", "3.3")
        assert step_33 is not None
        assert step_33.depends_on == ["3.2"]
        assert get_step("asdw-web", "4.1").depends_on == ["3.3"]
        assert get_step("asdw-web", "4.2").depends_on == ["3.3"]

        assert get_step("asdw-web", "2.6") is None
        assert get_step("asdw-web", "2.7") is None
        assert get_step("asdw-web", "2.8") is None

        completed = ["1.1", "1.2", "2.1", "2.2", "2.3", "2.3T", "2.3TC", "2.4", "2.5"]
        nexts = get_next_steps("asdw-web", completed_step_ids=completed)
        assert [s.id for s in nexts] == ["3.0T"]

        completed_ui = completed + ["3.0T", "3.0TC", "3.1", "3.2"]
        nexts = get_next_steps("asdw-web", completed_step_ids=completed_ui)
        assert [s.id for s in nexts] == ["3.3"]

        completed_e2e = completed_ui + ["3.3"]
        nexts = get_next_steps("asdw-web", completed_step_ids=completed_e2e)
        assert sorted(s.id for s in nexts) == ["4.1", "4.2"]

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
        assert get_step("aagd", "1").custom_agent == "Arch-AIAgentDesign-Step1"
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
        # ADR-0002: AKM は fan-out base (Step 1) + 横断レビュー (Step 2) の 2 ステップ構成
        wf = get_workflow("akm")
        assert wf is not None
        assert len(wf.steps) == 2
        assert wf.steps[0].id == "1"
        assert wf.steps[1].id == "2"
        # fan-out 設定
        assert wf.steps[0].fanout_static_keys is not None
        assert len(wf.steps[0].fanout_static_keys) == 21
        assert wf.max_parallel == 21


class TestAQODWorkflow:
    """AQOD ワークフロー固有テスト。"""

    def test_aqod_params(self):
        wf = get_workflow("aqod")
        assert wf is not None
        assert wf.params == ["target_scope", "depth", "focus_areas"]

    def test_aqod_single_step(self):
        # ADR-0002 T4H: AQOD は fan-out base (Step 1) + 横断レビュー (Step 2) の 2 ステップ構成
        wf = get_workflow("aqod")
        assert wf is not None
        assert len(wf.steps) == 2
        assert wf.steps[0].id == "1"
        assert wf.steps[1].id == "2"
        assert wf.steps[0].fanout_static_keys is not None
        assert len(wf.steps[0].fanout_static_keys) == 21
        assert wf.max_parallel == 21


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
        # Sub-4 (B-1): Step 5 の skip_fallback_deps は 4 → 4.1 に更新
        step = get_step("aas", "5")
        assert step.skip_fallback_deps == ["4.1"]

    def test_block_unless_empty(self):
        step = get_step("aas", "1")
        assert step.block_unless == []


class TestAAGAgentNames:
    """AAG ワークフローの各 Step が新しい Agent 名を使用していること（P3-1）。"""

    def test_aag_step1_uses_new_agent(self):
        assert get_step("aag", "1").custom_agent == "Arch-AIAgentDesign-Step1"

    def test_aag_step2_uses_new_agent(self):
        assert get_step("aag", "2").custom_agent == "Arch-AIAgentDesign-Step2"

    def test_aag_step3_uses_new_agent(self):
        assert get_step("aag", "3").custom_agent == "Arch-AIAgentDesign-Step3"


class TestABDVAgentNames:
    """ABDV ワークフローの各 Step が新しい Agent 名を使用していること（P3-2）。"""

    def test_abdv_step11_uses_new_agent(self):
        assert get_step("abdv", "1.1").custom_agent == "Dev-Batch-DataServiceSelect"

    def test_abdv_step12_uses_new_agent(self):
        assert get_step("abdv", "1.2").custom_agent == "Dev-Batch-DataDeploy"

    def test_abdv_step3_uses_new_agent(self):
        assert get_step("abdv", "3").custom_agent == "Dev-Batch-FunctionsDeploy"


# ---------------------------------------------------------------------------
# Sub-3 (Q3=b): output_paths / output_paths_template CI assertion
# ---------------------------------------------------------------------------

# Sub-3 時点で output_paths も output_paths_template も未設定の Step を allowlist 管理。
# 移行期間中の暫定措置。後続 Sub で 1 件ずつ allowlist から外す方針。
# キー = workflow id、値 = step id のリスト。
ALLOWED_EMPTY_OUTPUT_PATHS_STEPS: dict[str, list[str]] = {
    "aad-web": ["1", "2.1", "2.2", "2.3"],
    "asdw-web": [
        "1.1", "1.2", "2.1", "2.2", "2.3", "2.3T", "2.3TC", "2.4", "2.5",
        "3.0T", "3.0TC", "3.1", "3.2", "3.3", "4.1", "4.2",
    ],
    "abd": ["1.1", "1.2", "2", "3", "4", "5", "6.1", "6.2", "6.3"],
    "abdv": ["1.1", "1.2", "2.1", "2.2", "3", "4.1", "4.2"],
    "aag": ["1", "2", "3"],
    "aagd": ["1", "2.1", "2.2", "2.3", "3"],
    "akm": ["1", "2"],
    "aqod": ["1", "2"],
    "adoc": [
        "1", "2.1", "2.2", "2.3", "2.4", "2.5",
        "3.1", "3.2", "3.3", "3.4", "3.5",
        "4", "5.1", "5.2", "5.3", "5.4", "6.1", "6.2", "6.3",
    ],
}


class TestOutputPathsExplicit:
    """全 Step が output_paths または output_paths_template を明示しているか検証する。

    Sub-3 時点では ALLOWED_EMPTY_OUTPUT_PATHS_STEPS の allowlist で移行期間を吸収。
    後続 Sub で allowlist の Step を 1 件ずつ実値設定 → 除外する。
    """

    @pytest.mark.parametrize("wf", list_workflows(), ids=lambda w: w.id)
    def test_all_non_container_steps_have_output_paths_or_template(self, wf):
        allowed = set(ALLOWED_EMPTY_OUTPUT_PATHS_STEPS.get(wf.id, []))
        empty_steps = [
            s.id for s in wf.steps
            if not s.is_container
            and not s.output_paths
            and not s.output_paths_template
            and s.id not in allowed
        ]
        assert empty_steps == [], (
            f"Workflow '{wf.id}': 以下の Step に output_paths も output_paths_template も "
            f"設定されていません: {empty_steps}. "
            f"明示するか、移行期間中は ALLOWED_EMPTY_OUTPUT_PATHS_STEPS に追加してください。"
        )

    def test_step_def_has_output_paths_template_field(self):
        """StepDef に output_paths_template フィールドが存在し、デフォルトが None であること。"""
        step = StepDef(id="x", title="t", custom_agent=None, consumed_artifacts=[])
        assert hasattr(step, "output_paths_template")
        assert step.output_paths_template is None

    def test_output_paths_template_default_factory_safe(self):
        """output_paths_template を指定して StepDef を作成できること。"""
        step = StepDef(
            id="x", title="t", custom_agent=None,
            consumed_artifacts=[],
            output_paths_template=["docs/{key}.md"],
        )
        assert step.output_paths_template == ["docs/{key}.md"]
