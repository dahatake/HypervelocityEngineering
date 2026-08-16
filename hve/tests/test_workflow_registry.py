"""test_workflow_registry.py — hve/workflow_registry.py のテスト"""

import re
from pathlib import Path

import pytest
import yaml

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
    "ard": 8,  # Step 3 (KPI/OKR 定義・任意) 追加で 7 → 8
    "aas": 11,  # AAS に Step 8 (ペルソナカタログ) と Step 9 (ペルソナ別共通画面カタログ) 追加で 9 → 11
    "aad-web": 8,  # Step 2.5 (追加 Azure サービス選定) で 6 → 7、Step 2.6 (Agentic Retrieval 機能要件詳細) で 7 → 8
    "asdw-web": 25,  # 5 containers + 20 real steps (Agentic Retrieval Step 2.5/2.6 追加で 23 → 25)
    # ADFDV が required_input_paths として要求していた 4 ドキュメントの producer Step
    # (0.1 / 0.2 / 4 / 5) を追加して 3 → 7。
    "adfd": 7,
    "adfdv": 7,
    "aag": 3,
    "aagd": 6,  # Step 4 (tool search 実測評価) 追加で 5 → 6
    "aar": 6,  # Agentic Retrieval Add-on: 6 real steps (コンテナなし)
    "akm": 2,  # ADR-0002: fan-out base + cross-cutting review join
    "adi": 9,  # 目録 / 質問票 fan-out・join / Doc Card / トリアージ / ルーティング / 下流反映 3 件
    "adoc": 23,  # 4 containers + 19 real steps
}

EXPECTED_NON_CONTAINER_COUNTS = {
    "ard": 8,  # Step 3 (KPI/OKR 定義・任意) 追加で 7 → 8
    "aas": 11,  # 同上
    "aad-web": 8,  # Step 2.5 (追加 Azure サービス選定) で 6 → 7、Step 2.6 (Agentic Retrieval 機能要件詳細) で 7 → 8
    "asdw-web": 20,  # Agentic Retrieval Step 2.5/2.6 追加で 18 → 20
    "adfd": 7,  # 同上（ADFD はコンテナ Step を持たないため総数と一致）
    "adfdv": 7,
    "aag": 3,
    "aagd": 6,  # Step 4 (tool search 実測評価) 追加で 5 → 6
    "aar": 6,
    "akm": 2,  # ADR-0002: fan-out base + cross-cutting review join
    "adi": 9,
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

    def test_asdw_web_remote_cicd_steps_are_limited_to_compute_and_ui_deploy(self):
        """ASDW-WEB の Step 単位 remote CI/CD 対象は GitHub Actions --ref が必要な 2 Step のみ。"""
        wf = get_workflow("asdw-web")
        assert wf is not None
        remote_cicd_steps = {
            s.id for s in wf.steps
            if not s.is_container and s.requires_remote_cicd
        }
        assert remote_cicd_steps == {"3.4", "4.3"}
        assert not get_step("asdw-web", "1.3").requires_remote_cicd
        assert not get_step("asdw-web", "2.2").requires_remote_cicd

    def test_asdw_addservice_deploy_declares_foundry_skills_and_reality_acs(self):
        """Step.2.2 は実在する Azure Skills と Project/Model AC を宣言する。"""
        step = get_step("asdw-web", "2.2")
        assert step is not None
        assert step.required_skills == [
            "azure-cli-deploy-scripts",
            "azure-ac-verification",
            "azure-region-policy",
        ]
        assert step.reality_gate_acs == ["AC-1", "AC-13", "AC-14"]

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
        wf = get_workflow("adfdv")
        assert "app_ids" in wf.params
        assert "app_id" in wf.params
        assert "resource_group" in wf.params
        assert "app_id" in wf.params

    def test_params_abd(self):
        wf = get_workflow("adfd")
        assert "app_ids" in wf.params
        assert "app_id" in wf.params

    def test_ard_steps_require_knowledge_management(self):
        wf = get_workflow("ard")
        assert wf is not None
        for step_id in ["1", "1.1", "1.2", "2", "2.1", "3.1", "3.2", "3.3"]:
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
        roots = get_root_steps("adfd")
        root_ids = sorted(s.id for s in roots)
        # ADFD は ADFDV が要求する 4 ドキュメントの producer Step (0.1 / 0.2 / 4 / 5) を
        # 既存 Step 1/2/3 の上流に追加した。起点は Step 0.1（データフローデータモデル）のみで、
        # 旧 root だった Step 1 / 2 は Step 5 完了後に起動する。
        assert root_ids == ["0.1"]

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
        # Step 7 完了後は Step 8 (ペルソナカタログ) が起動
        assert [s.id for s in get_next_steps(
            "aas", completed_step_ids=["1", "2", "3.1", "3.2", "4.1", "4.2", "5", "6", "7"]
        )] == ["8"]
        # Step 8 完了後は Step 9 (ペルソナ別共通画面カタログ) が起動
        assert [s.id for s in get_next_steps(
            "aas", completed_step_ids=["1", "2", "3.1", "3.2", "4.1", "4.2", "5", "6", "7", "8"]
        )] == ["9"]

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
        """Sub-6 (C-3 確認): ADFD の Step 1 (ジョブ詳細仕様) と Step 2 (監視・運用設計) が
        同一 wave で並列起動可能であることを保証する。

        producer Step (0.1 / 0.2 / 4 / 5) 追加後は「ワークフロー起動直後」ではなく
        「共通の上流 Step 5 完了直後」が並列点になる。守るべき意図（1 と 2 が互いに
        依存せず同 wave で起動できること）は不変。

        Step 3 は consumed_artifacts に ``dataflow_specs`` (= Step 1 fan-out 子の出力) を含むため、
        現状の AND 結合 (depends_on=["1", "2"]) を維持する。
        """
        step_1 = get_step("adfd", "1")
        step_2 = get_step("adfd", "2")
        step_3 = get_step("adfd", "3")
        # 1 / 2 は同一の上流 Step にのみ依存し、互いには依存しない
        assert step_1.depends_on == ["5"]
        assert step_2.depends_on == ["5"]
        # 3 は 1 と 2 の両方に依存（dataflow_specs が必須）
        assert sorted(step_3.depends_on) == ["1", "2"]
        # 1 / 2 は共通上流の完了時点で同 wave に並ぶ
        nexts = sorted(
            s.id for s in get_next_steps(
                "adfd", completed_step_ids=["0.1", "0.2", "4", "5"]
            )
        )
        assert "1" in nexts and "2" in nexts

    def test_aad_web_dag_walk(self):
        assert [s.id for s in get_next_steps("aad-web", completed_step_ids=[])] == ["1"]

        nexts = get_next_steps("aad-web", completed_step_ids=["1"])
        assert sorted(s.id for s in nexts) == ["2.1", "2.2"]

        nexts = get_next_steps("aad-web", completed_step_ids=["1", "2.1"])
        assert sorted(s.id for s in nexts) == ["2.2", "2.4"]

        nexts = get_next_steps("aad-web", completed_step_ids=["1", "2.1", "2.2"])
        assert sorted(s.id for s in nexts) == ["2.3", "2.4", "2.5", "2.6"]

        # Sub-7 (C-4): 2.1/2.2/2.3/2.4 完了後に Step 3（整合性レビュー join）が起動可能。
        # Step 2.5 (追加 Azure サービス選定) と Step 2.6 (Agentic Retrieval 機能要件詳細) は
        # depends_on=["2.2"] のため 2.3/2.4 と並列で 2.2 完了後にも起動可能であり、
        # この段階では未完了として並ぶ。
        nexts = get_next_steps("aad-web", completed_step_ids=["1", "2.1", "2.2", "2.3", "2.4"])
        assert sorted(s.id for s in nexts) == ["2.5", "2.6", "3"]

    def test_aad_web_step3_is_consistency_review_join(self):
        """Sub-7 (C-4): AAD-WEB Step 3 が screen ↔ service 整合性レビュー join step として
        正しく定義されていること。"""
        step = get_step("aad-web", "3")
        assert step is not None
        assert step.custom_agent == "QA-DocConsistency"
        # AND join: 2.1, 2.2, 2.3, 2.4 が全て完了して初めて起動 (Step 2.4 = 画面別 TDD テスト仕様書)
        assert sorted(step.depends_on) == ["2.1", "2.2", "2.3", "2.4"]
        assert step.output_paths == ["docs/catalog/screen-service-consistency-report.md"]
        # 整合性レビューは fan-out しない（join step）
        assert step.fanout_static_keys is None
        assert step.fanout_parser is None

    def test_asdw_web_dag_walk_and_bypass_agent_chain(self):
        # local-first / live-last: local 生成を完了させてから live deploy へ進む
        step_41 = get_step("asdw-web", "4.1")
        assert step_41 is not None
        assert step_41.depends_on == ["3.3"]
        assert step_41.skip_fallback_deps == []
        step_44 = get_step("asdw-web", "4.4")
        assert step_44 is not None
        assert step_44.depends_on == ["4.3"]
        assert get_step("asdw-web", "5.1").depends_on == ["4.4"]
        assert get_step("asdw-web", "5.2").depends_on == ["4.4"]

        # AI Agent step は registry 未採用（reusable YAML 側にのみ存在）
        assert get_step("asdw-web", "2.7") is None
        assert get_step("asdw-web", "2.8") is None
        # Agentic Retrieval step は ADR-0001 Phase 5 で採用済み
        assert get_step("asdw-web", "2.5").custom_agent == "Dev-Microservice-Azure-AgenticRetrievalDesign"
        assert get_step("asdw-web", "2.6").custom_agent == "Dev-Microservice-Azure-AgenticRetrievalDeploy"
        # 旧 step ID も未採用であること
        assert get_step("asdw-web", "2.3TC") is None
        assert get_step("asdw-web", "3.0TC") is None

        # データコンテナ: 1.1 → 1.2 (DataTestCoding TDD RED) → … → 1.3 (DataDeploy TDD GREEN)
        assert get_step("asdw-web", "1.2").custom_agent == "Dev-Microservice-Azure-DataTestCoding"
        assert get_step("asdw-web", "1.3").custom_agent == "Dev-Microservice-Azure-DataDeploy"

        # local フェーズ: 1.1 後にデータ検証テストと追加サービス設計が ready になる
        assert [s.id for s in get_next_steps("asdw-web", completed_step_ids=[])] == ["1.1"]
        assert sorted(
            s.id for s in get_next_steps("asdw-web", completed_step_ids=["1.1"])
        ) == ["1.2", "2.1"]
        assert sorted(
            s.id for s in get_next_steps("asdw-web", completed_step_ids=["1.1", "1.2", "2.1"])
        ) == ["2.3", "2.5"]

        local_completed = ["1.1", "1.2", "2.1", "2.3", "2.5", "3.1", "3.2", "3.3", "4.1"]
        assert [
            s.id for s in get_next_steps("asdw-web", completed_step_ids=local_completed)
        ] == ["4.2"]

        # local generation checkpoint 後に初めて live deploy へ進む
        after_checkpoint = local_completed + ["4.2"]
        assert [
            s.id for s in get_next_steps("asdw-web", completed_step_ids=after_checkpoint)
        ] == ["1.3"]

        live_completed = after_checkpoint + ["1.3", "2.2", "2.4", "3.3"]
        # Step 2.6（Agentic Retrieval Deploy）は depends_on=["2.2", "2.5"] を満たすため
        # 3.4 と並列で ready になる。
        assert sorted(
            s.id for s in get_next_steps("asdw-web", completed_step_ids=live_completed)
        ) == ["2.6", "3.4"]

        completed_ui = live_completed + ["2.6", "3.4", "3.5", "4.3", "4.4"]
        nexts = get_next_steps("asdw-web", completed_step_ids=completed_ui)
        assert sorted(s.id for s in nexts) == ["5.1", "5.2"]

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
        # ADFD Step 3 は Step 1 AND Step 2 の両方完了で起動する AND join。
        # producer Step 追加後は上流 0.1/0.2/4/5 の完了が前提になる。
        upstream = ["0.1", "0.2", "4", "5"]
        nexts = get_next_steps("adfd", completed_step_ids=upstream + ["1"])
        next_ids = [s.id for s in nexts]
        assert "3" not in next_ids
        assert "2" in next_ids

        nexts = get_next_steps("adfd", completed_step_ids=upstream + ["1", "2"])
        next_ids = [s.id for s in nexts]
        assert "3" in next_ids

    def test_skipped_resolves_dependency(self):
        # Step 2 を skip すると、Step 1 完了のみで Step 3 が起動可能。
        nexts = get_next_steps(
            "adfd",
            completed_step_ids=["0.1", "0.2", "4", "5", "1"],
            skipped_step_ids=["2"],
        )
        next_ids = [s.id for s in nexts]
        assert "3" in next_ids

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
        step = get_step("aad-web", "2.3")
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


class TestADIQuestionnaireWorkflow:
    """ADIへ統合した原本質問票StepのRegistry契約。"""

    def test_adi_params(self):
        wf = get_workflow("adi")
        assert wf is not None
        assert wf.params == ["purpose", "target_scope", "depth", "focus_areas"]

    def test_adi_questionnaire_steps(self):
        wf = get_workflow("adi")
        assert wf is not None
        assert wf.get_step("1.1").fanout_static_keys == [
            f"D{n:02d}" for n in range(1, 22)
        ]
        assert wf.get_step("1.2").depends_on == ["1.1"]
        assert wf.get_step("2").depends_on == ["1.2"]
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
    """ADFDV ワークフローの各 Step が新しい Agent 名を使用していること（P3-2）。"""

    def test_abdv_step11_uses_new_agent(self):
        assert get_step("adfdv", "1.1").custom_agent == "Dev-Dataflow-DataServiceSelect"

    def test_abdv_step12_uses_new_agent(self):
        assert get_step("adfdv", "1.2").custom_agent == "Dev-Dataflow-DataDeploy"

    def test_abdv_step3_uses_new_agent(self):
        assert get_step("adfdv", "3").custom_agent == "Dev-Dataflow-FunctionsDeploy"


# ---------------------------------------------------------------------------
# Sub-3 (Q3=b): output_paths / output_paths_template CI assertion
# ---------------------------------------------------------------------------

# output_paths も output_paths_template も未設定の Step を allowlist 管理。
# 移行期間中の暫定措置。後続 Sub で 1 件ずつ allowlist から外す方針。
# キー = workflow id、値 = step id のリスト。
#
# E-01 / E-08 で解消済み（allowlist から除外）:
#   asdw-web: 1.1 / 2.1 / 2.2 / 3.1 / 3.4 / 4.3 / 5.1 / 5.2
#   aagd:     3
#   adoc:     1 / 3.2 / 3.3 / 3.4 / 3.5 / 4 / 5.1〜5.4 / 6.1〜6.3（宣言済みだった分の棚卸し）
#
# E-07 で解消済み（allowlist から除外）:
#   akm:      1 / 2（templates/akm/step-1.md・step-2.md の `## 出力` を registry へ宣言）
#   adfdv:    4.1 / 4.2（templates/adfdv/step-4.1.md・step-4.2.md の `## 出力` と
#             QA-AzureArchitectureReview / QA-AzureDependencyReview prompt の Step 別出力表を registry へ宣言）
#
# E-09 で解消済み（allowlist から除外）:
#   `output_paths_template` が「fan-out キーの別名プレースホルダ / glob / ディレクトリ参照」を
#   fail-closed で落とすようになった（FR-FANOUT-OUT-01）ため、確定ファイルパスへ解決できない
#   成果物も runner の output_paths ゲートを誤 fail させずに契約として宣言できる。
#   これにより次の Step を io-contract の宣言どおり registry へ反映し、allowlist から外した:
#     aad-web:  1 / 2.1 / 2.2 / 2.3（2.1 / 2.2 は `{screenNameSlug}` / `{serviceNameSlug}` を含み展開されない）
#     asdw-web: 2.3 / 2.4 / 3.2 / 3.3 / 3.5 / 4.1 / 4.2 / 4.4
#     adfd:     1 / 2 / 3（もとから宣言済みで allowlist が陳腐化していた）
#     adfdv:    1.1 / 2.1 / 2.2 / 3
#     aag:      1 / 2 / 3（もとから宣言済みで allowlist が陳腐化していた）
#     aagd:     2.2 / 2.3 / 3
#     akm:      1 / 2
#     旧独立原本質問票: 1 / 2（ADI 1.1 / 1.2 へ移設）
#     adoc:     2.1〜2.5 / 3.1（TBD-14 の動的パスを `output_paths_template` で宣言）
#
# 残置理由:
#   adfdv 1.2 : templates/adfdv/step-1.2.md `## 出力` は「Azure リソースの作成・検証完了」と
#               `{WORK}` 配下の実行ログのみで、リポジトリ内の成果物パスが契約上存在しない。
ALLOWED_EMPTY_OUTPUT_PATHS_STEPS: dict[str, list[str]] = {
    "adfdv": ["1.2"],
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

    def test_allowlist_has_no_stale_entries(self):
        """allowlist が陳腐化していないこと。

        宣言済みになった Step が allowlist に残ると、以後その Step の宣言漏れを
        検出できなくなる。allowlist は「実際に宣言が空の Step」だけを含む。
        """
        workflows = {wf.id: wf for wf in list_workflows()}
        stale: list[str] = []
        for workflow_id, step_ids in ALLOWED_EMPTY_OUTPUT_PATHS_STEPS.items():
            workflow = workflows.get(workflow_id)
            assert workflow is not None, f"allowlist が実在しない workflow を参照: {workflow_id}"
            for step_id in step_ids:
                step = next((s for s in workflow.steps if s.id == step_id), None)
                assert step is not None, (
                    f"allowlist が実在しない Step を参照: {workflow_id} {step_id}"
                )
                if step.output_paths or step.output_paths_template:
                    stale.append(f"{workflow_id} {step_id}")
        assert stale == [], (
            f"宣言済みになった Step が allowlist に残っている: {stale}. "
            f"ALLOWED_EMPTY_OUTPUT_PATHS_STEPS から削除してください。"
        )

    @pytest.mark.parametrize(
        ("workflow_id", "step_id"),
        [
            (workflow_id, step_id)
            for workflow_id, step_ids in ALLOWED_EMPTY_OUTPUT_PATHS_STEPS.items()
            for step_id in step_ids
        ],
    )
    def test_allowlisted_step_template_declares_no_repository_artifact(
        self, workflow_id: str, step_id: str
    ):
        """allowlist の残置理由をコメントではなく検証で担保する。

        allowlist を許すのは「template の `## 出力` にリポジトリ内成果物パスが
        契約上存在しない」Step だけである。template に成果物パスが追加されたら
        allowlist を外して宣言すべきなので、その時点で本テストが落ちる。
        """
        template = (
            Path(__file__).resolve().parents[2]
            / ".github"
            / "scripts"
            / "templates"
            / workflow_id
            / f"step-{step_id}.md"
        )
        assert template.is_file(), f"template が見つからない: {template}"

        text = template.read_text(encoding="utf-8")
        match = re.search(r"^##\s*出力\s*$(.*?)^##\s", text, re.M | re.S)
        assert match is not None, f"{template} に `## 出力` 節が無い"

        repository_paths = [
            line.strip()
            for line in match.group(1).splitlines()
            if re.search(r"`(?!\{)[\w./-]+/[\w./-]+`", line)
        ]
        assert repository_paths == [], (
            f"{workflow_id} {step_id} の template がリポジトリ内成果物を宣言している: "
            f"{repository_paths}. ALLOWED_EMPTY_OUTPUT_PATHS_STEPS から外し、"
            f"output_paths に宣言してください。"
        )

    def test_step_def_remote_cicd_default_false(self):
        """StepDef の requires_remote_cicd は明示しない限り False。"""
        step = StepDef(id="x", title="t", custom_agent=None, consumed_artifacts=[])
        assert step.requires_remote_cicd is False

    def test_output_paths_template_default_factory_safe(self):
        """output_paths_template を指定して StepDef を作成できること。"""
        step = StepDef(
            id="x", title="t", custom_agent=None,
            consumed_artifacts=[],
            output_paths_template=["docs/{key}.md"],
        )
        assert step.output_paths_template == ["docs/{key}.md"]


# ---------------------------------------------------------------------------
# P12: ASDW-WEB local-first / live-last DAG
# ---------------------------------------------------------------------------

# local generation checkpoint より前に完了する Step（Azure live 操作を伴わない）。
ASDW_WEB_LOCAL_STEP_IDS = [
    "1.1", "1.2", "2.1", "2.3", "2.5", "3.1", "3.2", "3.3", "4.1", "4.2",
]

# local generation checkpoint より後に実行する Step（Azure live 操作またはその結果に依存）。
ASDW_WEB_LIVE_STEP_IDS = [
    "1.3", "2.2", "2.4", "2.6", "3.4", "3.5", "4.3", "4.4", "5.1", "5.2",
]

ASDW_WEB_EXPECTED_DEPENDS_ON = {
    # --- local ---
    "1.1": [],
    "1.2": ["1.1"],
    "2.1": ["1.1"],
    "2.3": ["2.1"],
    "2.5": ["2.1"],
    "3.1": ["2.3"],
    "3.2": ["3.1"],
    "3.3": ["3.2"],
    "4.1": ["3.3"],
    "4.2": ["1.2", "2.5", "4.1"],
    # --- local generation checkpoint ---
    # --- live ---
    "1.3": ["1.2", "4.2"],
    "2.2": ["1.3", "2.1"],
    "2.4": ["2.2", "2.3"],
    "2.6": ["2.2", "2.5"],
    "3.4": ["2.4", "3.3"],
    "3.5": ["3.4"],
    "4.3": ["3.5", "4.2"],
    "4.4": ["4.3"],
    "5.1": ["4.4"],
    "5.2": ["4.4"],
}


def _asdw_web_transitive_deps(step_id: str) -> set[str]:
    """step_id が推移的に依存する Step ID 集合を返す。"""
    seen: set[str] = set()
    pending = [step_id]
    while pending:
        current = pending.pop()
        step = get_step("asdw-web", current)
        assert step is not None, current
        for dep in step.depends_on:
            if dep not in seen:
                seen.add(dep)
                pending.append(dep)
    return seen


_IO_CONTRACT_DIR = Path(__file__).resolve().parents[2] / ".github" / "io-contracts"
_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[2] / ".github" / "scripts" / "templates" / "asdw-web"
)


def _asdw_web_scoped_io_contract(step_id: str) -> dict:
    """ASDW-WEB Step の scoped I/O contract を読み込む。"""
    matches = sorted(_IO_CONTRACT_DIR.glob(f"*--asdw-web--{step_id}.yaml"))
    assert len(matches) == 1, f"step {step_id} の scoped io-contract が 1 件でない: {matches}"
    return yaml.safe_load(matches[0].read_text(encoding="utf-8")) or {}


class TestAsdwWebLocalFirstDag:
    """ASDW-WEB が local 生成を完了してから live deploy を行う DAG であること。"""

    def test_local_and_live_step_ids_cover_all_non_container_steps(self):
        """local / live の分類が非コンテナ Step を過不足なく覆うこと。"""
        wf = get_workflow("asdw-web")
        actual = sorted(s.id for s in wf.steps if not s.is_container)
        assert sorted(ASDW_WEB_LOCAL_STEP_IDS + ASDW_WEB_LIVE_STEP_IDS) == actual
        assert not set(ASDW_WEB_LOCAL_STEP_IDS) & set(ASDW_WEB_LIVE_STEP_IDS)

    @pytest.mark.parametrize("step_id", list(ASDW_WEB_EXPECTED_DEPENDS_ON))
    def test_step_declares_local_first_dependencies(self, step_id):
        """各 Step の depends_on が local-first / live-last DAG と一致すること。"""
        step = get_step("asdw-web", step_id)
        assert step is not None, step_id
        assert sorted(step.depends_on) == ASDW_WEB_EXPECTED_DEPENDS_ON[step_id], step_id

    @pytest.mark.parametrize("live_step_id", ASDW_WEB_LIVE_STEP_IDS)
    def test_every_live_step_follows_all_local_steps(self, live_step_id):
        """live Step は全 local Step の完了後にしか到達できないこと。"""
        reachable = _asdw_web_transitive_deps(live_step_id) | {live_step_id}
        missing = [s for s in ASDW_WEB_LOCAL_STEP_IDS if s not in reachable]
        assert missing == [], f"{live_step_id} が local Step {missing} より先に実行され得る"

    @pytest.mark.parametrize("local_step_id", ASDW_WEB_LOCAL_STEP_IDS)
    def test_local_step_never_depends_on_live_step(self, local_step_id):
        """local Step が live Step へ依存しないこと。"""
        deps = _asdw_web_transitive_deps(local_step_id)
        assert not deps & set(ASDW_WEB_LIVE_STEP_IDS), local_step_id

    def test_local_steps_do_not_require_live_only_artifacts(self):
        """local Step が live Step の出力を required_input_paths に要求しないこと。"""
        live_outputs: set[str] = set()
        for live_step_id in ASDW_WEB_LIVE_STEP_IDS:
            step = get_step("asdw-web", live_step_id)
            assert step is not None, live_step_id
            live_outputs.update(step.output_paths or [])
        violations = []
        for local_step_id in ASDW_WEB_LOCAL_STEP_IDS:
            step = get_step("asdw-web", local_step_id)
            assert step is not None, local_step_id
            for required in step.required_input_paths or []:
                if required in live_outputs:
                    violations.append((local_step_id, required))
        assert violations == [], f"local Step が live 出力を要求している: {violations}"

    def test_local_step_io_contract_inputs_are_not_produced_by_live_steps(self):
        """local Step の I/O contract 入力が live Step を producer として宣言しないこと。

        registry の `output_paths` は ASDW-WEB ではほぼ未宣言のため、
        成果物の生成元の正本である scoped I/O contract を根拠に検査する。
        """
        live_producer_suffixes = tuple(f"--asdw-web--{sid}" for sid in ASDW_WEB_LIVE_STEP_IDS)
        violations = []
        for local_step_id in ASDW_WEB_LOCAL_STEP_IDS:
            contract = _asdw_web_scoped_io_contract(local_step_id)
            for entry in contract.get("inputs") or []:
                producer = entry.get("producer") or ""
                if producer.endswith(live_producer_suffixes):
                    violations.append((local_step_id, entry.get("path"), producer))
        assert violations == [], f"local Step が live Step の成果物を入力にしている: {violations}"

    def test_dag_walk_reaches_local_checkpoint_before_data_deploy(self):
        """get_next_steps の走査が local 群を先に消化し、最後に live 群へ進むこと。"""
        completed: list[str] = []
        local_remaining = set(ASDW_WEB_LOCAL_STEP_IDS)
        while local_remaining:
            nexts = [s.id for s in get_next_steps("asdw-web", completed_step_ids=completed)]
            assert nexts, f"local 走査が停止した: completed={completed}"
            assert not set(nexts) & set(ASDW_WEB_LIVE_STEP_IDS), (
                f"local 未完了のまま live Step {nexts} が起動可能: completed={completed}"
            )
            completed.extend(nexts)
            local_remaining -= set(nexts)
        assert [s.id for s in get_next_steps("asdw-web", completed_step_ids=completed)] == ["1.3"]

    def test_workflow_limits_parallelism_to_one(self):
        """初期版は同一 worktree の true parallel を避けるため max_parallel=1 とすること。"""
        assert get_workflow("asdw-web").max_parallel == 1

    @pytest.mark.parametrize("step_id", list(ASDW_WEB_EXPECTED_DEPENDS_ON))
    def test_step_template_dependency_section_matches_registry(self, step_id):
        """template の `## 依存` が registry の depends_on を漏れなく宣言すること。

        DAG 変更時に template の記述だけが旧依存のまま残ると、Agent が誤った
        前提で実行するため、両者の drift を機械的に検出する。
        """
        step = get_step("asdw-web", step_id)
        assert step is not None, step_id
        template = _TEMPLATES_DIR / f"step-{step_id}.md"
        assert template.exists(), template
        text = template.read_text(encoding="utf-8")
        if "## 依存" not in text:
            pytest.skip(f"step-{step_id}.md は依存セクションを持たない")
        section = text.split("## 依存", 1)[1].split("\n## ", 1)[0]
        # `Step.X ... asdw-web:done` 形式の前提条件宣言だけを依存記述として扱う
        # （「Step.5.2 と並列実行可能」等の補足記述を誤検出しないため）。
        declared = set(re.findall(r"Step\.(\d+\.\d+)[^\n]*asdw-web:done", section))
        stale = sorted(declared - set(step.depends_on))
        assert stale == [], f"step-{step_id}.md の `## 依存` に旧依存 {stale} が残っている"
        if declared:
            missing = sorted(set(step.depends_on) - declared)
            assert missing == [], f"step-{step_id}.md の `## 依存` に {missing} が無い"


_PROMPTS_DIR = Path(__file__).resolve().parents[2] / ".github" / "prompts"


class TestCustomAgentPromptFilesExist:
    """全ワークフローの custom_agent に対応する Prompt ファイルが実在すること。

    `hve/prompt_loader.py::load_prompt()` はファイル不存在時に例外ではなく空文字を
    返すため、Prompt 未作成のまま Step が実行されても実行時には落ちない
    （Agent 仕様が LLM に一切渡らないまま進行する）。既存の CI は
    `body_template_path` の実在しか検証しておらず Prompt 側は無検査だったので、
    本テストで宣言と実体の 1:1 を強制する。
    """

    @pytest.mark.parametrize("wf", list_workflows(), ids=lambda w: w.id)
    def test_every_custom_agent_has_a_prompt_file(self, wf):
        missing = [
            f"step {s.id}: {s.custom_agent}"
            for s in wf.steps
            if s.custom_agent
            and s.custom_agent != "(none)"
            and not (_PROMPTS_DIR / f"{s.custom_agent}.prompt.md").is_file()
        ]
        assert missing == [], (
            f"Workflow '{wf.id}': 以下の custom_agent に対応する "
            f".github/prompts/<name>.prompt.md がありません: {missing}"
        )

    @pytest.mark.parametrize("wf", list_workflows(), ids=lambda w: w.id)
    def test_every_custom_agent_prompt_is_not_empty(self, wf):
        """0 バイト書き込み事故を検出する（空ファイルは実質未作成と同義）。"""
        empty = [
            f"step {s.id}: {s.custom_agent}"
            for s in wf.steps
            if s.custom_agent
            and s.custom_agent != "(none)"
            and (path := _PROMPTS_DIR / f"{s.custom_agent}.prompt.md").is_file()
            and not path.read_text(encoding="utf-8").strip()
        ]
        assert empty == [], (
            f"Workflow '{wf.id}': 以下の Prompt ファイルが空です: {empty}"
        )

