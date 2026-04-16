"""test_workflow_registry.py — hve/workflow_registry.py のテスト"""

import pytest

from hve.workflow_registry import (
    StepDef,
    WorkflowDef,
    get_workflow,
    get_step,
    get_next_steps,
    get_root_steps,
    list_workflows,
)


# ---------------------------------------------------------------------------
# bash 版と一致するステップ数定義 (workflow-registry.sh より)
# ---------------------------------------------------------------------------

EXPECTED_STEP_COUNTS = {
    "aas": 2,
    "aad": 16,   # 3 containers + 13 real steps
    "asdw": 24,  # 4 containers + 20 real steps
    "abd": 9,
    "abdv": 7,
    "aqkm": 1,
    "adoc": 23,  # 4 containers + 19 real steps
}

EXPECTED_NON_CONTAINER_COUNTS = {
    "aas": 2,
    "aad": 13,
    "asdw": 20,
    "abd": 9,
    "abdv": 7,
    "aqkm": 1,
    "adoc": 19,
}


class TestGetWorkflow:
    """get_workflow() のテスト。"""

    @pytest.mark.parametrize("wf_id", ["aas", "aad", "asdw", "abd", "abdv", "aqkm", "adoc"])
    def test_get_all_workflows(self, wf_id: str):
        wf = get_workflow(wf_id)
        assert wf is not None
        assert wf.id == wf_id

    def test_get_workflow_case_insensitive(self):
        wf = get_workflow("AAS")
        assert wf is not None
        assert wf.id == "aas"

    def test_get_workflow_unknown(self):
        assert get_workflow("unknown") is None

    @pytest.mark.parametrize("wf_id", ["aas", "aad", "asdw", "abd", "abdv", "aqkm", "adoc"])
    def test_step_count_matches_bash(self, wf_id: str):
        """各ワークフローのステップ数が bash 版と一致すること。"""
        wf = get_workflow(wf_id)
        assert wf is not None
        assert len(wf.steps) == EXPECTED_STEP_COUNTS[wf_id]

    @pytest.mark.parametrize("wf_id", ["aas", "aad", "asdw", "abd", "abdv", "aqkm", "adoc"])
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

    def test_params_asdw(self):
        wf = get_workflow("asdw")
        assert "app_id" in wf.params
        assert "resource_group" in wf.params
        assert "usecase_id" in wf.params

    def test_params_abdv(self):
        wf = get_workflow("abdv")
        assert "resource_group" in wf.params
        assert "batch_job_id" in wf.params


class TestGetRootSteps:
    """get_root_steps() のテスト。"""

    def test_aas_roots(self):
        """AAS: Step.1 のみがルート。"""
        roots = get_root_steps("aas")
        root_ids = [s.id for s in roots]
        assert root_ids == ["1"]

    def test_aad_roots(self):
        """AAD: Step.1.1 のみがルート（コンテナは除外）。"""
        roots = get_root_steps("aad")
        root_ids = [s.id for s in roots]
        assert root_ids == ["1.1"]

    def test_abd_roots(self):
        """ABD: Step.1.1 と Step.1.2 が並列ルート。"""
        roots = get_root_steps("abd")
        root_ids = sorted(s.id for s in roots)
        assert root_ids == ["1.1", "1.2"]

    def test_unknown_workflow(self):
        assert get_root_steps("nonexistent") == []


class TestGetNextSteps:
    """get_next_steps() のテスト — DAG 走査ロジック。"""

    def test_sequential(self):
        """AAS: Step.1 完了 → Step.2 が次。"""
        nexts = get_next_steps("aas", completed_step_ids=["1"])
        assert [s.id for s in nexts] == ["2"]

    def test_initial_state(self):
        """AAS: 何も完了していない → ルートのみ。"""
        nexts = get_next_steps("aas", completed_step_ids=[])
        assert [s.id for s in nexts] == ["1"]

    def test_all_completed(self):
        """AAS: 全て完了 → 空。"""
        nexts = get_next_steps("aas", completed_step_ids=["1", "2"])
        assert nexts == []

    def test_and_join(self):
        """ABD: Step.1.1 AND Step.1.2 → Step.2 (AND join)。"""
        # 片方だけ完了 → Step.2 はまだ
        nexts = get_next_steps("abd", completed_step_ids=["1.1"])
        next_ids = [s.id for s in nexts]
        assert "2" not in next_ids
        assert "1.2" in next_ids

        # 両方完了 → Step.2 が起動可能
        nexts = get_next_steps("abd", completed_step_ids=["1.1", "1.2"])
        next_ids = [s.id for s in nexts]
        assert "2" in next_ids

    def test_parallel_fork(self):
        """AAD: Step.6 完了 → Step.7.1 と Step.7.2 が並列起動。"""
        completed = ["1.1", "1.2", "2", "3", "4", "5", "6"]
        nexts = get_next_steps("aad", completed_step_ids=completed)
        next_ids = sorted(s.id for s in nexts)
        assert "7.1" in next_ids
        assert "7.2" in next_ids

    def test_skipped_resolves_dependency(self):
        """スキップされたステップは依存解決に使える。"""
        # ABD: Step.1.1 完了、Step.1.2 スキップ → Step.2 が起動可能
        nexts = get_next_steps(
            "abd",
            completed_step_ids=["1.1"],
            skipped_step_ids=["1.2"],
        )
        next_ids = [s.id for s in nexts]
        assert "2" in next_ids

    def test_nonexistent_dep_auto_resolves(self):
        """レジストリに存在しない依存先は自動解決される。"""
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
        """コンテナは get_next_steps の結果に含まれない。"""
        nexts = get_next_steps("aad", completed_step_ids=[])
        next_ids = [s.id for s in nexts]
        # コンテナ ID ("1", "7", "8") が含まれないこと
        assert "1" not in next_ids
        assert "7" not in next_ids
        assert "8" not in next_ids

    def test_unknown_workflow(self):
        assert get_next_steps("nonexistent", completed_step_ids=[]) == []


class TestGetStep:
    """モジュールレベル get_step() のテスト。"""

    def test_existing(self):
        step = get_step("asdw", "2.3T")
        assert step is not None
        assert step.custom_agent == "Arch-TDD-TestSpec"

    def test_nonexistent_step(self):
        assert get_step("aas", "999") is None

    def test_nonexistent_workflow(self):
        assert get_step("nonexistent", "1") is None


class TestListWorkflows:
    """list_workflows() のテスト。"""

    def test_list_workflows_returns_seven(self):
        wfs = list_workflows()
        assert len(wfs) == 7

    def test_all_ids(self):
        wf_ids = sorted(wf.id for wf in list_workflows())
        assert wf_ids == ["aad", "aas", "abd", "abdv", "adoc", "aqkm", "asdw"]


class TestAQKMWorkflow:
    """AQKM ワークフロー固有テスト。"""

    def test_aqkm_params(self):
        wf = get_workflow("aqkm")
        assert wf is not None
        assert "scope" in wf.params
        assert "target_files" in wf.params
        assert "force_refresh" in wf.params

    def test_aqkm_single_step(self):
        wf = get_workflow("aqkm")
        assert wf is not None
        assert len(wf.steps) == 1
        assert wf.steps[0].id == "1"

    def test_aqkm_custom_agent(self):
        wf = get_workflow("aqkm")
        assert wf is not None
        assert wf.steps[0].custom_agent == "QA-KnowledgeManager"

    def test_aqkm_template_path(self):
        step = get_step("aqkm", "1")
        assert step is not None
        assert step.body_template_path == "templates/aqkm/step-1.md"

    def test_aqkm_root_step(self):
        roots = get_root_steps("aqkm")
        assert len(roots) == 1
        assert roots[0].id == "1"

    def test_aqkm_template_mentions_knowledge(self):
        """AQKM step-1.md テンプレートが knowledge/ 出力への言及を含むこと。"""
        from hve.template_engine import _load_template
        content = _load_template("templates/aqkm/step-1.md")
        assert "knowledge/" in content

    def test_aqkm_template_uses_correct_master_list_path(self):
        """AQKM step-1.md テンプレートが正しいパス template/ を参照していること（docs/ ではない）。"""
        from hve.template_engine import _load_template
        content = _load_template("templates/aqkm/step-1.md")
        assert "template/business-requirement-document-master-list.md" in content
        assert "docs/business-requirement-document-master-list.md" not in content

    def test_aqkm_template_has_9_steps(self):
        """AQKM step-1.md テンプレートが 9 ステップの処理フローを記述していること。"""
        from hve.template_engine import _load_template
        content = _load_template("templates/aqkm/step-1.md")
        assert "9 ステップ" in content

    def test_aqkm_template_output_lists_knowledge(self):
        """AQKM step-1.md テンプレートの出力セクションに knowledge/ が含まれること。"""
        from hve.template_engine import _load_template
        content = _load_template("templates/aqkm/step-1.md")
        assert "knowledge/D{NN}" in content


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

    def test_adoc_parallel_step_2(self):
        nexts = get_next_steps("adoc", completed_step_ids=["1"])
        next_ids = sorted(s.id for s in nexts)
        assert next_ids == ["2.1", "2.2", "2.3", "2.4", "2.5"]

    def test_adoc_final_parallel_step_6(self):
        completed = [
            "1", "2.1", "2.2", "2.3", "2.4", "2.5",
            "3.1", "3.2", "3.3", "3.4", "3.5",
            "4", "5.1", "5.2", "5.3", "5.4",
        ]
        nexts = get_next_steps("adoc", completed_step_ids=completed)
        next_ids = sorted(s.id for s in nexts)
        assert next_ids == ["6.1", "6.2", "6.3"]


class TestStepDefFields:
    """StepDef の各フィールドが正しく設定されていること。"""

    def test_template_path(self):
        step = get_step("aas", "1")
        assert step.body_template_path == "templates/aas/step-1.md"

    def test_container_no_template(self):
        wf = get_workflow("aad")
        container = wf.get_step("1")
        assert container.is_container is True
        assert container.body_template_path is None
        assert container.custom_agent is None

    def test_skip_fallback_deps(self):
        step = get_step("aad", "3")
        assert step.skip_fallback_deps == ["2"]

    def test_block_unless_empty(self):
        step = get_step("aas", "1")
        assert step.block_unless == []
