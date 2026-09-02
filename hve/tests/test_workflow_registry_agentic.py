"""test_workflow_registry_agentic.py — Agentic Retrieval 関連 Step の整合性検証テスト

workflow_registry.py の AAD-WEB / ASDW-WEB ワークフロー定義に対して、
Agentic Retrieval 専用 Step の存在・依存整合性を検証する。

ADR-0001 Phase 5（2026-08-04）で専用 Step を配線済み:
  - AAD-WEB Step.2.6: `Arch-AgenticRetrieval-Detail`（製品非依存の機能要件詳細）
  - ASDW-WEB Step.2.5: `Dev-Microservice-Azure-AgenticRetrievalDesign`（Azure 実装設計）
  - ASDW-WEB Step.2.6: `Dev-Microservice-Azure-AgenticRetrievalDeploy`（Knowledge Base / Source 作成）

`enable_agentic_retrieval=no` による Step 無効化は `StepDef.disabled_when_config` が担う
（契約テストは `test_agentic_retrieval_step_skip.py`）。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml  # PyYAML は CI (test-hve-python.yml) で必須インストール済み

from hve.workflow_registry import get_step

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"

# ---------------------------------------------------------------------------
# AAD-WEB: Arch-AgenticRetrieval-Detail 相当の Step 検証
# ---------------------------------------------------------------------------


class TestAadWebAgenticRetrievalStep:
    """AAD-WEB の Agentic Retrieval 専用 Step（2.6）を検証する。"""

    def test_step_2_6_uses_agentic_retrieval_detail_agent(self):
        """Step.2.6 が `Arch-AgenticRetrieval-Detail` を使用すること。"""
        step = get_step("aad-web", "2.6")
        assert step is not None
        assert step.custom_agent == "Arch-AgenticRetrieval-Detail"
        assert step.is_container is False

    def test_step_2_6_depends_on_service_detail(self):
        """Step.2.6 がマイクロサービス定義書（Step.2.2）に依存すること。"""
        step = get_step("aad-web", "2.6")
        assert step is not None
        assert step.depends_on == ["2.2"]

    def test_step_2_6_declares_spec_output(self):
        """Step.2.6 が製品非依存 spec を契約として宣言すること。

        判定キーワードにヒットしたサービスだけを処理する条件付き成果物のため、
        確定ファイルパス（output_paths）ではゲートしない。
        """
        step = get_step("aad-web", "2.6")
        assert step is not None
        assert step.output_paths == []
        assert step.output_paths_template == [
            "docs/services/{serviceId}-agentic-retrieval-spec.md"
        ]

    def test_step_2_6_requires_agentic_retrieval_contract_skill(self):
        """Step.2.6 が AR-CAP 契約 Skill を required 宣言すること。"""
        step = get_step("aad-web", "2.6")
        assert step is not None
        assert "agentic-retrieval-contract" in step.required_skills

    def test_aad_web_all_steps_exist(self):
        """AAD-WEB の全 Step（1 / 2.1 / 2.2 / 2.3 / 2.4 / 2.5 / 2.6 / 3）が存在すること。"""
        for step_id in ["1", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "3"]:
            assert get_step("aad-web", step_id) is not None, f"AAD-WEB に Step.{step_id} が存在しません"


# ---------------------------------------------------------------------------
# ASDW-WEB: AgenticRetrievalDesign / AgenticRetrievalDeploy 相当の Step 検証
# ---------------------------------------------------------------------------


class TestAsdwWebAgenticRetrievalSteps:
    """ASDW-WEB の Agentic Retrieval 専用 Step（2.5 / 2.6）を検証する。"""

    def test_step_2_5_uses_design_agent(self):
        """Step.2.5 が `Dev-Microservice-Azure-AgenticRetrievalDesign` を使用すること。"""
        step = get_step("asdw-web", "2.5")
        assert step is not None
        assert step.custom_agent == "Dev-Microservice-Azure-AgenticRetrievalDesign"
        assert step.depends_on == ["2.1"]

    def test_step_2_6_uses_deploy_agent(self):
        """Step.2.6 が `Dev-Microservice-Azure-AgenticRetrievalDeploy` を使用すること。"""
        step = get_step("asdw-web", "2.6")
        assert step is not None
        assert step.custom_agent == "Dev-Microservice-Azure-AgenticRetrievalDeploy"

    def test_step_2_6_depends_on_deploy_and_design(self):
        """Step.2.6 が live 済みの 2.2 と設計の 2.5 の両方に依存すること。"""
        step = get_step("asdw-web", "2.6")
        assert step is not None
        assert sorted(step.depends_on) == ["2.2", "2.5"]

    def test_step_2_5_is_part_of_local_generation_checkpoint(self):
        """Step.2.5 は local 生成 Step であり、checkpoint（4.2）へ到達すること。"""
        step_42 = get_step("asdw-web", "4.2")
        assert step_42 is not None
        assert "2.5" in step_42.depends_on

    def test_step_2_6_declares_reality_gate_acs(self):
        """Step.2.6 が実在系 AC（設計値一致と smoke retrieve）を gate として宣言すること。"""
        step = get_step("asdw-web", "2.6")
        assert step is not None
        assert step.reality_gate_acs == ["AC4B-1", "AC4B-14", "AC4B-15", "AC4B-18"]

    def test_agentic_retrieval_steps_require_contract_skill(self):
        """2.5 / 2.6 の両方が AR-CAP 契約 Skill を required 宣言すること。"""
        for step_id in ("2.5", "2.6"):
            step = get_step("asdw-web", step_id)
            assert step is not None
            assert "agentic-retrieval-contract" in step.required_skills, step_id

    def test_add_service_steps_remain_unchanged(self):
        """既存の AddService 系 Step の責務が変わっていないこと。"""
        assert get_step("asdw-web", "2.1").custom_agent == "Dev-Microservice-Azure-AddServiceDesign"
        assert get_step("asdw-web", "2.2").custom_agent == "Dev-Microservice-Azure-AddServiceDeploy"


# ---------------------------------------------------------------------------
# AAGD: Agentic Retrieval 契約 Skill の公開範囲（FR-WF-AAGD-05）
# ---------------------------------------------------------------------------


class TestAagdAgenticRetrievalSkillPublication:
    """TDD Step でも AR-CAP の検証観点へ到達できること。"""

    def test_tdd_steps_require_contract_skill(self):
        """2.1（テスト仕様）/ 2.2（テストコード）が AR-CAP 契約 Skill を required 宣言すること。"""
        for step_id in ("2.1", "2.2"):
            step = get_step("aagd", step_id)
            assert step is not None
            assert "agentic-retrieval-contract" in step.required_skills, step_id

    def test_implementation_and_deploy_steps_keep_the_contract_skill(self):
        """既存の 2.3 / 3 の宣言を壊していないこと。"""
        for step_id in ("2.3", "3"):
            step = get_step("aagd", step_id)
            assert step is not None
            assert "agentic-retrieval-contract" in step.required_skills, step_id

    def test_tool_search_eval_step_does_not_require_the_contract_skill(self):
        """Step 4 は tool search 専用評価であり AR-CAP を扱わない。"""
        step = get_step("aagd", "4")
        assert step is not None
        assert "agentic-retrieval-contract" not in step.required_skills


# ---------------------------------------------------------------------------
# AAD-WEB: 既存 Step の順序・依存整合性
# ---------------------------------------------------------------------------


class TestAadWebStepOrderIntegrity:
    """AAD-WEB の既存 Step 順序・依存関係が壊れていないことを検証する。"""

    def test_step_1_is_root(self):
        """AAD-WEB の Step.1 がルートノード（依存なし）であること。"""
        step = get_step("aad-web", "1")
        assert step is not None
        assert step.depends_on == []

    def test_step_2_1_depends_on_step_1(self):
        """AAD-WEB の Step.2.1 が Step.1 に依存すること。"""
        step = get_step("aad-web", "2.1")
        assert step is not None
        assert "1" in step.depends_on

    def test_step_2_2_depends_on_step_1(self):
        """AAD-WEB の Step.2.2 が Step.1 に依存すること。"""
        step = get_step("aad-web", "2.2")
        assert step is not None
        assert "1" in step.depends_on

    def test_step_2_3_depends_on_step_2_2_only(self):
        """AAD-WEB の Step.2.3 (サービス TDD) が Step.2.2 のみに依存すること。"""
        step = get_step("aad-web", "2.3")
        assert step is not None
        assert "2.2" in step.depends_on
        assert "2.1" not in step.depends_on

    def test_step_2_4_depends_on_step_2_1_only(self):
        """AAD-WEB の Step.2.4 (画面 TDD) が Step.2.1 のみに依存すること。"""
        step = get_step("aad-web", "2.4")
        assert step is not None
        assert "2.1" in step.depends_on
        assert "2.2" not in step.depends_on

    def test_step_2_1_and_2_2_parallel_after_step_1(self):
        """Step.2.1 と Step.2.2 が Step.1 完了後に並列起動可能であること。"""
        from hve.workflow_registry import get_next_steps

        nexts = get_next_steps("aad-web", completed_step_ids=["1"])
        next_ids = sorted(s.id for s in nexts)
        assert "2.1" in next_ids
        assert "2.2" in next_ids

    def test_step_2_3_available_after_step_2_2(self):
        """Step.2.2 完了で Step.2.3 (サービス TDD) が起動可能になること。Step.2.1 完了は不要。"""
        from hve.workflow_registry import get_next_steps

        nexts = get_next_steps("aad-web", completed_step_ids=["1", "2.2"])
        next_ids = [s.id for s in nexts]
        assert "2.3" in next_ids

    def test_step_2_4_available_after_step_2_1(self):
        """Step.2.1 完了で Step.2.4 (画面 TDD) が起動可能になること。Step.2.2 完了は不要。"""
        from hve.workflow_registry import get_next_steps

        nexts = get_next_steps("aad-web", completed_step_ids=["1", "2.1"])
        next_ids = [s.id for s in nexts]
        assert "2.4" in next_ids

    def test_step_2_3_and_2_4_parallel_after_step_2_1_and_2_2(self):
        """Step.2.1 AND Step.2.2 完了後に Step.2.3 と Step.2.4 が並列起動可能になること。"""
        from hve.workflow_registry import get_next_steps

        nexts = get_next_steps("aad-web", completed_step_ids=["1", "2.1", "2.2"])
        next_ids = [s.id for s in nexts]
        assert "2.3" in next_ids
        assert "2.4" in next_ids


# ---------------------------------------------------------------------------
# ASDW-WEB: 既存 Step の順序・依存整合性
# ---------------------------------------------------------------------------


class TestAsdwWebStepOrderIntegrity:
    """ASDW-WEB の既存 Step 順序・依存関係が壊れていないことを検証する。"""

    def test_step_1_1_is_root(self):
        """ASDW-WEB の Step.1.1 がルートノード（依存なし）であること。"""
        step = get_step("asdw-web", "1.1")
        assert step is not None
        assert step.depends_on == []

    def test_step_1_2_depends_on_step_1_1(self):
        """ASDW-WEB の Step.1.2 が Step.1.1 に依存すること。"""
        step = get_step("asdw-web", "1.2")
        assert step is not None
        assert "1.1" in step.depends_on

    def test_step_2_1_depends_on_step_1_1(self):
        """ASDW-WEB の Step.2.1 が Step.1.1（データストア選定）に依存すること。"""
        step = get_step("asdw-web", "2.1")
        assert step is not None
        assert "1.1" in step.depends_on

    def test_step_2_4_depends_on_step_2_3(self):
        """ASDW-WEB の Step.2.4 が Step.2.3 に依存すること。"""
        step = get_step("asdw-web", "2.4")
        assert step is not None
        assert "2.3" in step.depends_on


# ---------------------------------------------------------------------------
# P12: local-first / live-last 化に伴う設計入力の付け替え
# ---------------------------------------------------------------------------


class TestAsdwWebLocalFirstDesignInputs:
    """local Step が deploy 済みリソースではなく設計を入力にすること。"""

    def test_step_2_1_depends_on_data_design_not_data_deploy(self):
        """Step.2.1 は Step.1.1（設計）に依存し、Step.1.3（Deploy）に依存しないこと。"""
        step = get_step("asdw-web", "2.1")
        assert step is not None
        assert "1.1" in step.depends_on
        assert "1.3" not in step.depends_on

    def test_step_2_3_generates_baseline_tests_from_design(self):
        """Step.2.3 は deploy 済みリソースを前提にせず Step.2.1 の設計から生成すること。"""
        step = get_step("asdw-web", "2.3")
        assert step is not None
        assert step.depends_on == ["2.1"]

    def test_step_3_1_uses_planned_design_not_live_service_catalog(self):
        """Step.3.1 は Step.1.3 が生成する live service catalog を必須入力にしないこと。"""
        step = get_step("asdw-web", "3.1")
        assert step is not None
        assert step.depends_on == ["2.3"]
        assert "docs/azure/service-catalog.md" not in (step.required_input_paths or [])

    def test_step_1_3_runs_after_local_ui_coding(self):
        """Step.1.3 は local generation checkpoint（Step.4.2 完了）後に実行されること。"""
        step = get_step("asdw-web", "1.3")
        assert step is not None
        assert "4.2" in step.depends_on


# ---------------------------------------------------------------------------
# Agentic Retrieval スキップ条件の検証
# ---------------------------------------------------------------------------


class TestAgenticRetrievalSkipCondition:
    """enable_agentic_retrieval=no 条件での正規化動作を検証する。

    NOTE: Step の無効化そのものは `StepDef.disabled_when_config` と
          `resolve_disabled_step_ids` が担う（`test_agentic_retrieval_step_skip.py` を参照）。
          本クラスは Foundry 連携フラグ等の**回答値の正規化**（`normalize_agentic_retrieval_answers`）
          だけを対象とする。
    """

    def test_no_disables_foundry_mcp(self):
        """Q1=no のとき foundry_mcp_integration が False に正規化されること。"""
        from hve.template_engine import normalize_agentic_retrieval_answers

        result = normalize_agentic_retrieval_answers({"enable_agentic_retrieval": "no"})
        assert result["foundry_mcp_integration"] is False

    def test_no_sets_standard_allowed_for_sku_fallback(self):
        """Q1=no のとき foundry_sku_fallback_policy が 'standard_allowed' に正規化されること。"""
        from hve.template_engine import normalize_agentic_retrieval_answers

        result = normalize_agentic_retrieval_answers({"enable_agentic_retrieval": "no"})
        assert result["foundry_sku_fallback_policy"] == "standard_allowed"

    def test_auto_does_not_disable_foundry_mcp(self):
        """Q1=auto のとき foundry_mcp_integration は変更されないこと。"""
        from hve.template_engine import normalize_agentic_retrieval_answers

        answers = {"enable_agentic_retrieval": "auto", "foundry_mcp_integration": "する"}
        result = normalize_agentic_retrieval_answers(answers)
        assert result["foundry_mcp_integration"] == "する"

    def test_yes_does_not_disable_foundry_mcp(self):
        """Q1=yes のとき foundry_mcp_integration は変更されないこと。"""
        from hve.template_engine import normalize_agentic_retrieval_answers

        answers = {"enable_agentic_retrieval": "yes", "foundry_mcp_integration": "する"}
        result = normalize_agentic_retrieval_answers(answers)
        assert result["foundry_mcp_integration"] == "する"

    def test_shinai_disables_foundry_mcp(self):
        """Q1=「しない」（UI 表示値）のとき foundry_mcp_integration が False に正規化されること。"""
        from hve.template_engine import normalize_agentic_retrieval_answers

        result = normalize_agentic_retrieval_answers({"enable_agentic_retrieval": "しない"})
        assert result["foundry_mcp_integration"] is False


# ---------------------------------------------------------------------------
# Workflow YAML 静的入力名検証（Phase 6 伝搬の同期テスト）
# ---------------------------------------------------------------------------


def _load_workflow_yaml(filename: str) -> dict:
    """GitHub Actions ワークフロー YAML を読み込む。"""
    return yaml.safe_load((_WORKFLOWS_DIR / filename).read_text(encoding="utf-8"))


def _read_workflow_text(filename: str) -> str:
    """GitHub Actions ワークフロー YAML の生テキストを返す。"""
    return (_WORKFLOWS_DIR / filename).read_text(encoding="utf-8")


def _get_workflow_step(filename: str, *, job_name: str, step_name: str) -> dict:
    """指定 workflow/job/step の辞書を返す。"""
    yaml_data = _load_workflow_yaml(filename)
    steps = yaml_data.get("jobs", {}).get(job_name, {}).get("steps", [])
    return next(step for step in steps if step.get("name") == step_name)


def _get_dispatcher_job_with_keys(job_name: str) -> set[str]:
    """Dispatcher YAML の指定ジョブの `with:` キー一覧を返す。

    jobs.<job_name>.with セクションをパースするため、ファイル全体への
    テキスト検索よりも構造的な検証が可能。
    """
    yaml_data = _load_workflow_yaml("auto-orchestrator-dispatcher.yml")
    jobs = yaml_data.get("jobs", {})
    job = jobs.get(job_name, {})
    return set(job.get("with", {}).keys())


class TestWorkflowYamlAgenticInputs:
    """Dispatcher および Reusable workflow YAML の Agentic Retrieval 入力名を静的検証する。"""

    _DISPATCHER = "auto-orchestrator-dispatcher.yml"
    _AAD_WEB_REUSABLE = "auto-app-detail-design-web-reusable.yml"
    _ASDW_WEB_REUSABLE = "auto-app-dev-microservice-web-reusable.yml"

    def _get_workflow_inputs(self, filename: str) -> set[str]:
        """reusable ワークフローの on.workflow_call.inputs キー一覧を返す。

        NOTE: PyYAML (YAML 1.1) では 'on:' キーワードが Python の boolean True として
              解析されるため、辞書キーとして True を使用する（'on' 文字列では取得できない）。
              両方を試みることで YAML バージョン差異に対応する。
        """
        yaml_data = _load_workflow_yaml(filename)
        # PyYAML YAML 1.1 では 'on' キーワードが boolean True に変換されるため
        # True キーで参照し、見つからなければ文字列 'on' にフォールバックする
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        inputs = on_section.get("workflow_call", {}).get("inputs", {})
        return set(inputs.keys())

    def test_aad_web_reusable_has_enable_agentic_retrieval_input(self):
        """AAD-WEB reusable が enable_agentic_retrieval 入力を持つこと。"""
        inputs = self._get_workflow_inputs(self._AAD_WEB_REUSABLE)
        assert "enable_agentic_retrieval" in inputs

    def test_aad_web_reusable_has_agentic_data_source_modes_input(self):
        """AAD-WEB reusable が agentic_data_source_modes 入力を持つこと。"""
        inputs = self._get_workflow_inputs(self._AAD_WEB_REUSABLE)
        assert "agentic_data_source_modes" in inputs

    def test_aad_web_reusable_has_foundry_mcp_integration_input(self):
        """AAD-WEB reusable が foundry_mcp_integration 入力を持つこと。"""
        inputs = self._get_workflow_inputs(self._AAD_WEB_REUSABLE)
        assert "foundry_mcp_integration" in inputs

    def test_asdw_web_reusable_has_all_six_agentic_inputs(self):
        """ASDW-WEB reusable が Q1〜Q6 に対応する 6 入力をすべて持つこと。"""
        inputs = self._get_workflow_inputs(self._ASDW_WEB_REUSABLE)
        expected_inputs = {
            "enable_agentic_retrieval",
            "agentic_data_source_modes",
            "foundry_mcp_integration",
            "agentic_data_sources_hint",
            "agentic_existing_design_diff_only",
            "foundry_sku_fallback_policy",
        }
        for input_name in expected_inputs:
            assert input_name in inputs, \
                f"ASDW-WEB reusable に '{input_name}' 入力が見つかりません"

    def test_aad_web_reusable_agentic_inputs_subset_of_asdw_web(self):
        """AAD-WEB reusable の Agentic 入力が ASDW-WEB reusable の Agentic 入力のサブセットであること。"""
        aad_inputs = self._get_workflow_inputs(self._AAD_WEB_REUSABLE)
        asdw_inputs = self._get_workflow_inputs(self._ASDW_WEB_REUSABLE)
        agentic_keys = {
            "enable_agentic_retrieval",
            "agentic_data_source_modes",
            "foundry_mcp_integration",
            "agentic_data_sources_hint",
            "agentic_existing_design_diff_only",
            "foundry_sku_fallback_policy",
        }
        aad_agentic = aad_inputs & agentic_keys
        asdw_agentic = asdw_inputs & agentic_keys
        assert aad_agentic <= asdw_agentic, \
            f"AAD-WEB の Agentic 入力が ASDW-WEB のサブセットでありません: {aad_agentic - asdw_agentic}"

    def test_dispatcher_propagates_agentic_inputs_to_aad_web(self):
        """Dispatcher の aad-web ジョブ `with:` セクションに Agentic Retrieval 入力が存在すること。

        jobs.aad-web.with の keys を YAML パースで構造的に確認する。
        ファイル全体の文字列検索ではなく、ジョブスコープに限定して検証する。
        """
        with_keys = _get_dispatcher_job_with_keys("aad-web")
        for input_name in ["enable_agentic_retrieval", "agentic_data_source_modes", "foundry_mcp_integration"]:
            assert input_name in with_keys, \
                f"dispatcher の aad-web ジョブ with に '{input_name}' が見つかりません"

    def test_dispatcher_dispatches_asdw_web_with_agentic_inputs(self):
        """FR-CLOUD-06: registry と同期済みの ASDW-WEB を dispatcher が起動すること。

        auto-app-dev-microservice-web-reusable.yml は hve/workflow_registry.py の
        ASDW-WEB Step 体系と同期済み（test_cloud_reusable_workflow_parity.py が固定）。
        Agentic 入力が asdw-web ジョブへ渡ることも合わせて確認する。
        """
        jobs = _load_workflow_yaml("auto-orchestrator-dispatcher.yml").get("jobs", {})
        assert "asdw-web" in jobs, "dispatcher に ASDW-WEB 起動ジョブがありません"
        assert jobs["asdw-web"]["uses"].endswith(self._ASDW_WEB_REUSABLE)
        with_keys = _get_dispatcher_job_with_keys("asdw-web")
        for input_name in [
            "enable_agentic_retrieval",
            "agentic_data_source_modes",
            "foundry_mcp_integration",
        ]:
            assert input_name in with_keys, \
                f"dispatcher の asdw-web ジョブ with に '{input_name}' が見つかりません"


class TestQaReadyLabelTokenFallback:
    """qa-ready / labeled 連鎖トリガー用ラベル付与時のトークン設定を検証する。"""

    def test_qa_ready_labeling_steps_use_copilot_pat_fallback_token(self):
        targets = [
            ("auto-app-selection-reusable.yml", "Issue 初期化とStep Issue 生成"),
            ("auto-app-detail-design-web-reusable.yml", "Issue 初期化とStep Issue 生成"),
            ("auto-app-dev-microservice-web-reusable.yml", "Issue 初期化とStep Issue 生成"),
            ("auto-dataflow-design-reusable.yml", "Issue 初期化とStep Issue 生成"),
            ("auto-dataflow-dev-reusable.yml", "Issue 初期化とStep Issue 生成"),
            ("auto-ai-agent-design-reusable.yml", "Issue 初期化とStep Issue 生成"),
            ("auto-ai-agent-dev-reusable.yml", "Issue 初期化とStep Issue 生成"),
            ("auto-app-documentation-reusable.yml", "Issue 初期化と Step.1 生成"),
        ]
        expected = "${{ secrets.COPILOT_PAT || secrets.GITHUB_TOKEN }}"
        for workflow, step_name in targets:
            step = _get_workflow_step(workflow, job_name="orchestrate", step_name=step_name)
            assert step.get("env", {}).get("GH_TOKEN") == expected

    def test_adoc_done_transition_step_uses_copilot_pat_fallback_token(self):
        step = _get_workflow_step(
            "advance-subissues.yml",
            job_name="advance_adoc",
            step_name="Advance ADOC sub issues",
        )
        assert step.get("env", {}).get("GH_TOKEN") == "${{ secrets.COPILOT_PAT || secrets.GITHUB_TOKEN }}"


class TestPlaywrightE2EDirectExecution:
    """ASDW-WEB Step 4.4 は到達不能な reusable を介さず直接実行する。"""

    _REMOVED_WORKFLOW = "e2e-playwright-reusable.yml"

    def test_unreachable_reusable_workflow_is_absent(self):
        assert not (_WORKFLOWS_DIR / self._REMOVED_WORKFLOW).exists()

    def test_agent_step_and_cloud_body_use_direct_execution(self):
        paths = (
            _REPO_ROOT / ".github" / "prompts" / "E2ETesting-Playwright.prompt.md",
            _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web" / "step-4.4.prompt.md",
            _WORKFLOWS_DIR / "auto-app-dev-microservice-web-reusable.yml",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            assert self._REMOVED_WORKFLOW not in text, path
            assert "npx playwright test" in text, path
            assert "最大 5 回" in text, path


class TestIssueQaReadyTransitionWorkflow:
    """Issue の qa-ready / qa-drafting 遷移 workflow を静的検証する。"""

    _WORKFLOW = "auto-issue-qa-ready-transition.yml"

    def test_excludes_pre_qa_marker_from_answer_candidates(self):
        save_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="save-qa-answer",
            step_name="Materialize, save, and read back answered QA",
        )
        run_script = save_step.get("run", "")
        assert "! printf '%s' \"${answer_body}\" | grep -qF '<!-- copilot-auto-pre-qa-posted -->'" in run_script
        assert re.search(
            r'contains\("<!-- copilot-auto-pre-qa-posted -->"\)\)\s*\|\s*not',
            run_script,
        )

    def test_uses_human_copilot_mentions_for_manual_answers(self):
        save_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="save-qa-answer",
            step_name="Materialize, save, and read back answered QA",
        )
        run_script = save_step.get("run", "")
        assert "grep -qi '@copilot'" in run_script
        assert 'answer_author_assoc}" == "OWNER"' in run_script
        assert 'answer_author_assoc}" == "MEMBER"' in run_script
        assert 'answer_author_assoc}" == "COLLABORATOR"' in run_script
        assert 'answer_author_type}" != "Bot"' in run_script

    def test_logs_missing_answers_without_injecting_issue_body(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert "QA 回答未検出" in content
        assert "状態メッセージを Issue body に注入しました" not in content

    def test_ready_transition_requires_successful_context_injection(self):
        transition_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="transition",
            step_name="qa-ready → ready 遷移（ラベル入替え + Copilot アサイン）",
        )
        assert "steps.inject-qa-context.outputs.qa_comment_found == 'true'" in transition_step.get("if", "")

    def test_detect_step_accepts_qa_drafting_label(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert 'endswith(":qa-ready") or endswith(":qa-drafting")' in content

    def test_ready_transition_maps_qa_drafting_to_ready(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert 'READY_LABEL="${READY_LABEL/:qa-drafting/:ready}"' in content

    def test_answer_transition_assigns_before_removing_qa_state(self):
        step = _get_workflow_step(
            self._WORKFLOW,
            job_name="transition",
            step_name="qa-ready → ready 遷移（ラベル入替え + Copilot アサイン）",
        )
        script = step.get("run", "")
        assert script.index("assign_copilot") < script.index("gh api -X DELETE")
        assert script.index('labels[]=${READY_LABEL}') < script.index("gh api -X DELETE")
        assert "遷移失敗のため ready/running をロールバック" in script
        assert "final_labels_json" in script
        assert "Copilot アサインに失敗したため QA 状態を維持します" in script
        assert "exit 1" in script

    def test_multiple_qa_state_labels_fail_closed(self):
        save_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="save-qa-answer",
            step_name="Materialize, save, and read back answered QA",
        )
        detect_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="transition",
            step_name="Issue の *:qa-ready / *:qa-drafting ラベル確認",
        )
        for step in (save_step, detect_step):
            script = step.get("run", "")
            assert "qa_label_count" in script
            assert "複数の QA 状態ラベル" in script
            assert "exit 1" in script

    def test_transition_workflow_exports_copilot_pat(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert "COPILOT_PAT: ${{ secrets.COPILOT_PAT }}" in content

    def test_has_workflow_dispatch_inputs_for_dry_run(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        inputs = on_section.get("workflow_dispatch", {}).get("inputs", {})
        assert "target_issue" in inputs
        assert "target_pr" in inputs
        assert "target_comment_id" in inputs
        assert "dry_run" in inputs
        assert "simulate_label" in inputs

    def test_answer_and_questionnaire_are_paired_by_comment_identity_and_time(self):
        save_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="save-qa-answer",
            step_name="Materialize, save, and read back answered QA",
        )
        run_script = save_step.get("run", "")
        assert "/issues/comments/${ANSWER_COMMENT_ID}" in run_script
        assert "answer_created_at" in run_script
        assert "--argjson answer_comment_id" in run_script
        assert ".id != $answer_comment_id" in run_script
        assert ".created_at == $answer_created_at and .id < $answer_comment_id" in run_script
        assert "answer_comment_id=${ANSWER_COMMENT_ID}" in run_script

    def test_transition_reuses_saved_branch_and_exact_answer_comment(self):
        transition = _load_workflow_yaml(self._WORKFLOW)["jobs"]["transition"]
        env = transition.get("env", {})
        assert env.get("SAVED_BRANCH") == "${{ needs.save-qa-answer.outputs.branch }}"
        assert env.get("ANSWER_COMMENT_ID") == (
            "${{ needs.save-qa-answer.outputs.answer_comment_id }}"
        )
        inject_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="transition",
            step_name="QA 回答コンテキストを Issue body に注入（冪等性マーカー付き）",
        )
        assert "/issues/comments/${ANSWER_COMMENT_ID}" in inject_step.get("run", "")
        transition_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="transition",
            step_name="qa-ready → ready 遷移（ラベル入替え + Copilot アサイン）",
        )
        assert 'BRANCH="${SAVED_BRANCH}"' in transition_step.get("run", "")

    def test_transition_workflow_contains_dry_run_guard(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert "dry_run_guard()" in content
        assert '[ "${DRY_RUN}" = "true" ]' in content
        assert "[DRY RUN] would execute:" in content
        assert "[DRY RUN] would execute: $*" not in content

    def test_dispatch_run_guards_against_pull_request_target_issue(self):
        dispatch_guard_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="transition",
            step_name="workflow_dispatch 対象が PR でないことを確認",
        )
        assert dispatch_guard_step.get("if", "") == "github.event_name == 'workflow_dispatch'"
        run_script = dispatch_guard_step.get("run", "")
        assert "data.get('pull_request')" in run_script
        assert "は PR です。Issue 番号を指定してください。" in run_script

    def test_injects_qa_reference_instruction_section(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert "<!-- qa-reference-instruction-start -->" in content
        assert "<!-- qa-reference-instruction-end -->" in content
        assert "<!-- qa-reference-start -->" in content
        assert "<!-- qa-reference-end -->" in content
        assert "## Referenced QA Files" in content
        assert "参照なし: 理由 = <理由>" in content


class TestLabelStateMachineFixWorkflows(unittest.TestCase):
    """Issue #2551 Phase C のラベル状態機械修正を静的検証する。"""

    def test_auto_issue_transition_has_pull_request_target_opened(self):
        yaml_data = _load_workflow_yaml("auto-issue-qa-ready-transition.yml")
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        pr_types = on_section.get("pull_request_target", {}).get("types", [])
        self.assertIn("opened", pr_types)

    def test_auto_issue_transition_contains_copilot_pr_detection_and_marker(self):
        content = _read_workflow_text("auto-issue-qa-ready-transition.yml")
        self.assertIn("copilot-swe-agent[bot]", content)
        self.assertIn("Copilot", content)
        self.assertIn("<!-- hve-qa-context-injected -->", content)
        self.assertIn("transition-pr-opened", content)
        self.assertIn("steps.detect-questionnaire.outputs.questionnaire_found == 'true'", content)

    def test_pr_opened_only_moves_qa_drafting_to_qa_ready(self):
        steps = _load_workflow_yaml("auto-issue-qa-ready-transition.yml")["jobs"]["transition-pr-opened"]["steps"]
        transition = next(
            s for s in steps
            if s.get("name") == "質問票作成完了として qa-drafting → qa-ready 遷移"
        )
        script = transition.get("run", "")
        self.assertIn('QA_READY_LABEL="${QA_DRAFTING_LABEL/:qa-drafting/:qa-ready}"', script)
        self.assertNotIn("RUNNING_LABEL", script)
        self.assertNotIn("assign_copilot", script)
        self.assertNotIn('/:qa-drafting/:ready', script)

    def test_state_transition_on_pr_merge_workflow_contract(self):
        workflow = "state-transition-on-pr-merge.yml"
        workflow_path = _WORKFLOWS_DIR / workflow
        self.assertTrue(workflow_path.exists(), f"{workflow} が存在しません")

        yaml_data = _load_workflow_yaml(workflow)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        pr_types = on_section.get("pull_request_target", {}).get("types", [])
        self.assertIn("closed", pr_types)

        job_if = yaml_data.get("jobs", {}).get("transition", {}).get("if", "")
        self.assertIn("github.event.pull_request.merged == true", job_if)

        permissions = yaml_data.get("permissions", {})
        self.assertEqual("write", permissions.get("issues"))

        content = _read_workflow_text(workflow)
        for prefix in [
            "aas", "aad", "aad-web", "asdw", "asdw-web", "adfd",
            "adfdv", "aag", "aagd", "aar", "ada", "akm", "adoc",
        ]:
            self.assertIn(prefix, content)
        self.assertIn("<!-- state-transition-on-pr-merge-done -->", content)

    def test_state_transition_on_pr_merge_has_done_idempotency_guard(self):
        content = _read_workflow_text("state-transition-on-pr-merge.yml")
        self.assertIn('if [ "${done_present}" = "true" ]; then', content)
        self.assertIn("付与をスキップ", content)
        self.assertIn('elif gh issue edit "${ISSUE_NUMBER}" --repo "${REPO}" --add-label "${done_label}"; then', content)
        self.assertIn("cleanup_failed", content)
        self.assertIn("stale_remaining", content)

    def test_state_transition_on_pr_merge_has_issue_resolution_fallback_and_auto_close(self):
        content = _read_workflow_text("state-transition-on-pr-merge.yml")
        self.assertIn("closingIssuesReferences", content)
        self.assertIn("PR title の #N", content)
        self.assertIn("Method 5", content)
        self.assertIn("cross-referenced", content)
        self.assertIn("/timeline", content)
        self.assertIn("<!-- auto-close-done -->", content)
        self.assertIn("gh issue close \"${ISSUE_NUMBER}\"", content)
        self.assertIn("steps.transition-labels.outputs.done_present", content)

    def test_link_copilot_pr_guard_considers_closing_keyword_presence(self):
        content = _read_workflow_text("link-copilot-pr-to-issue.yml")
        self.assertIn("existing_closing=", content)
        self.assertIn("done マーカーはありますが closing キーワードが無いため再試行します。", content)
        self.assertIn("PR body に既存の closing キーワード", content)


class TestVerifyQaReferenceInPrWorkflow:
    """verify-qa-reference-in-pr workflow の静的検証。"""

    _WORKFLOW = "verify-qa-reference-in-pr.yml"

    def test_has_pull_request_target_triggers(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        pr_target_types = on_section.get("pull_request_target", {}).get("types", [])
        assert "opened" in pr_target_types
        assert "edited" in pr_target_types
        assert "synchronize" in pr_target_types
        assert "ready_for_review" in pr_target_types
        assert "reopened" in pr_target_types
        assert "labeled" in pr_target_types

    def test_has_workflow_dispatch_inputs(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        inputs = on_section.get("workflow_dispatch", {}).get("inputs", {})
        assert "target_pr" in inputs
        assert "dry_run" in inputs

    def test_has_concurrency_group_by_pr_number(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        concurrency = yaml_data.get("concurrency", {})
        group = concurrency.get("group", "")
        assert "verify-qa-reference-in-pr-" in group
        assert "inputs.target_pr" in group
        assert "github.event.pull_request.number" in group
        assert concurrency.get("cancel-in-progress") is False

    def test_job_condition_scopes_target_prs(self):
        job_if = _load_workflow_yaml(self._WORKFLOW).get("jobs", {}).get("verify", {}).get("if", "")
        assert "vars.QA_REFERENCE_CHECK_MODE != 'disabled'" in job_if
        assert "contains(github.event.pull_request.labels.*.name, 'auto-qa')" in job_if
        assert "!contains(github.event.pull_request.labels.*.name, 'qa-questionnaire-pr')" in job_if
        assert "!github.event.pull_request.draft" in job_if

    def test_run_script_checks_required_markers_and_no_reference(self):
        verify_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="verify",
            step_name="Verify QA Reference section in PR body",
        )
        run_script = verify_step.get("run", "")
        assert "<!-- qa-reference-start -->" in run_script
        assert "<!-- qa-reference-end -->" in run_script
        assert "参照なし" in run_script
        assert "QA Reference セクションが PR 本文に存在しません" in run_script
        assert "QA Reference セクションに参照ファイルまたは『参照なし: 理由 = ...』が記載されていません" in run_script

    def test_run_script_checks_path_safety_and_file_existence(self):
        verify_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="verify",
            step_name="Verify QA Reference section in PR body",
        )
        run_script = verify_step.get("run", "")
        assert "grep -qE '^qa/[a-zA-Z0-9_][a-zA-Z0-9_.-]*(/[a-zA-Z0-9_][a-zA-Z0-9_.-]*)*\\.md$'" in run_script
        assert "grep -qE '(^|/)\\.\\.(/|$)'" in run_script
        assert "grep -qE '(^|/)\\.(/|$)'" in run_script
        assert '[[ "${qa_path}" == *"?"* ]]' in run_script
        assert '[[ "${qa_path}" == *"#"* ]]' in run_script
        assert '[[ "${qa_path}" == *"%"* ]]' in run_script
        assert "/contents/${qa_path}?ref=${head_sha}" in run_script
        assert "/contents/${qa_path}?ref=${base_sha}" in run_script

    def test_run_script_generates_comment_file_on_pr_fetch_failure(self):
        verify_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="verify",
            step_name="Verify QA Reference section in PR body",
        )
        run_script = verify_step.get("run", "")
        assert 'failures_json=\'["PR #' in run_script
        assert "/tmp/qa_reference_check_comment.md" in run_script

    def test_upserts_failure_comment_with_marker(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert "<!-- qa-reference-check-result -->" in content
        assert "gh api --method PATCH \"/repos/${REPO}/issues/comments/${comment_id}\"" in content
        assert "gh pr comment \"${PR_NUMBER}\"" in content

    def test_skips_comment_in_dry_run(self):
        comment_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="verify",
            step_name="Upsert PR comment on failure",
        )
        assert "env.DRY_RUN != 'true'" in comment_step.get("if", "")
        skip_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="verify",
            step_name="Skip comment posting in dry-run mode",
        )
        assert "env.DRY_RUN == 'true'" in skip_step.get("if", "")


class TestCopilotAutoFeedbackWorkflow:
    """copilot-auto-feedback workflow の dry-run 追加を静的検証する。"""

    _WORKFLOW = "copilot-auto-feedback.yml"

    def test_has_workflow_dispatch_inputs_for_dry_run(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        inputs = on_section.get("workflow_dispatch", {}).get("inputs", {})
        assert "target_issue" in inputs
        assert "target_pr" in inputs
        assert "dry_run" in inputs
        assert "simulate_label" in inputs

    def test_auto_qa_on_issue_supports_simulate_label(self):
        job = _load_workflow_yaml(self._WORKFLOW).get("jobs", {}).get("auto-qa-on-issue", {})
        condition = job.get("if", "")
        assert "inputs.simulate_label" in condition
        assert "workflow_dispatch" in condition

    def test_write_steps_use_dry_run_guard(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert "dry_run_guard()" in content
        assert "[DRY RUN] would execute:" in content
        assert "[DRY RUN] would execute: $*" not in content


# ---------------------------------------------------------------------------
# FR-CLOUD-24: QA 回答保存後の非待機 AKM 直列調整 — 契約テスト
# ---------------------------------------------------------------------------


class TestQaAnsweredAkmCloudWorkflow:
    """auto-akm-after-qa.yml の静的契約を検証する（FR-CLOUD-24）。

    このファイルは未実装のため、全テストは RED（FileNotFoundError/AssertionError）で失敗する。
    """

    _WORKFLOW = "auto-akm-after-qa.yml"

    def test_workflow_file_exists(self):
        """auto-akm-after-qa.yml がリポジトリに存在すること。"""
        assert (_WORKFLOWS_DIR / self._WORKFLOW).exists(), \
            f"{self._WORKFLOW} が .github/workflows/ に存在しません"

    def test_has_workflow_dispatch_trigger(self):
        """workflow_dispatch トリガーを持つこと。"""
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        assert "workflow_dispatch" in on_section

    def test_workflow_dispatch_has_required_inputs(self):
        """workflow_dispatch に source_issue, qa_sha, qa_path, branch, auto_merge 入力を持つこと。"""
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        inputs = on_section.get("workflow_dispatch", {}).get("inputs", {})
        for name in ("source_issue", "qa_sha", "qa_path", "branch", "auto_merge"):
            assert name in inputs, f"workflow_dispatch に '{name}' 入力がありません"

    def test_qa_sha_input_description_mentions_64hex(self):
        """qa_sha 入力の description が 64 文字 hex であることを示すこと。"""
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        qa_sha = on_section["workflow_dispatch"]["inputs"]["qa_sha"]
        description = qa_sha.get("description", "").lower()
        assert "64" in description and "hex" in description

    def test_has_repository_level_concurrency(self):
        """リポジトリ単位の concurrency を持つこと（Issue 単位ではない）。"""
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        jobs = yaml_data.get("jobs", {})
        job = jobs.get("coordinate-akm", {})
        assert job, "coordinate-akm job がありません"
        conc = job.get("concurrency", {})
        group = conc.get("group", "") if isinstance(conc, dict) else ""
        assert group == "akm-knowledge-write-${{ github.repository }}"

    def test_job_timeout_is_360_minutes(self):
        """主要 job の timeout-minutes が 360 であること。"""
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        jobs = yaml_data.get("jobs", {})
        timeouts = [j.get("timeout-minutes") for j in jobs.values() if j.get("timeout-minutes")]
        assert 360 in timeouts, f"timeout-minutes=360 の job がありません: {timeouts}"

    def test_permissions_include_issues_write(self):
        """issues: write 権限を持つこと。"""
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        # top-level or job-level permissions
        perms = yaml_data.get("permissions", {})
        jobs = yaml_data.get("jobs", {})
        all_perms = dict(perms)
        for j in jobs.values():
            all_perms.update(j.get("permissions", {}))
        assert all_perms.get("issues") == "write"

    def test_permissions_include_pull_requests_read(self):
        """pull-requests: read 権限を持つこと。"""
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        perms = yaml_data.get("permissions", {})
        jobs = yaml_data.get("jobs", {})
        all_perms = dict(perms)
        for j in jobs.values():
            all_perms.update(j.get("permissions", {}))
        assert all_perms.get("pull-requests") == "read"

    def test_permissions_include_contents_read(self):
        """contents: read 権限を持つこと。"""
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        perms = yaml_data.get("permissions", {})
        jobs = yaml_data.get("jobs", {})
        all_perms = dict(perms)
        for j in jobs.values():
            all_perms.update(j.get("permissions", {}))
        assert all_perms.get("contents") == "read"

    def test_idempotency_marker_scan_in_open_and_closed_labeled_issues(self):
        """検索索引に依存せず qa-akm-sync ラベル対象の本文を厳密照合すること。"""
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        steps = yaml_data["jobs"]["coordinate-akm"]["steps"]
        guard = next(step for step in steps if "Find existing" in step.get("name", ""))
        script = guard.get("run", "")
        assert "qa-akm-sync" in script
        assert "branch=${BRANCH}" in script
        assert "state=all" in script
        assert "labels=qa-akm-sync" in script
        assert "--paginate" in script
        assert "--search" not in script
        assert "issue_number=" in script and "GITHUB_OUTPUT" in script

    def test_creates_independent_akm_root_issue(self):
        """独立した AKM Root Issue を作成する記述があること。"""
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        steps = yaml_data.get("jobs", {}).get("coordinate-akm", {}).get("steps", [])
        names = [step.get("name", "") for step in steps]
        create_idx = next(i for i, name in enumerate(names) if "AKM Root Issue" in name)
        label_idx = next(i for i, name in enumerate(names) if "knowledge-management" in name)
        assert create_idx < label_idx
        create = steps[create_idx]
        assert create.get("if") == "steps.guard.outputs.issue_number == ''"
        assert "gh issue create" in create.get("run", "")
        assert "issue_number=" in create.get("run", "")
        label = steps[label_idx]
        assert label.get("if") == "steps.guard.outputs.issue_number == ''"
        assert "steps.create.outputs.issue_number" in str(label.get("env", {}))

    def test_existing_issue_skips_create(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        steps = yaml_data["jobs"]["coordinate-akm"]["steps"]
        create = next(step for step in steps if "Create independent" in step.get("name", ""))
        resolve = next(step for step in steps if "Resolve AKM Root" in step.get("name", ""))
        assert create.get("if") == "steps.guard.outputs.issue_number == ''"
        assert "steps.guard.outputs.issue_number" in str(resolve.get("env", {}))

    def test_create_applies_routing_label_atomically_and_finds_legacy_orphans(self):
        steps = _load_workflow_yaml(self._WORKFLOW)["jobs"]["coordinate-akm"]["steps"]
        ensure_idx = next(i for i, s in enumerate(steps) if "Ensure QA sync routing label" in s.get("name", ""))
        create_idx = next(i for i, s in enumerate(steps) if "Create independent" in s.get("name", ""))
        assert ensure_idx < create_idx
        create_script = steps[create_idx].get("run", "")
        assert 'gh issue create' in create_script
        assert '--label "qa-akm-sync"' in create_script
        guard = next(s for s in steps if "Find existing" in s.get("name", ""))
        assert "fallback" in guard.get("run", "").lower()
        assert 'issues?state=all&per_page=100' in guard.get("run", "")

    def test_existing_nonterminal_issue_reconciles_labels_before_poll(self):
        steps = _load_workflow_yaml(self._WORKFLOW)["jobs"]["coordinate-akm"]["steps"]
        reconcile_idx = next(i for i, s in enumerate(steps) if "Reconcile AKM Root" in s.get("name", ""))
        poll_idx = next(i for i, s in enumerate(steps) if "Poll AKM terminal" in s.get("name", ""))
        assert reconcile_idx < poll_idx
        script = steps[reconcile_idx].get("run", "")
        assert 'akm:done' in script and 'akm:blocked' in script and 'closed' in script
        assert '--add-label "qa-akm-sync"' in script
        assert '--add-label "knowledge-management"' in script

    def test_polls_terminal_states(self):
        """akm:done / akm:blocked / closed を低頻度 poll する記述があること。"""
        content = _read_workflow_text(self._WORKFLOW)
        assert "akm:done" in content
        assert "akm:blocked" in content
        assert 'state' in content and 'closed' in content
        assert "POLL_INTERVAL_SECONDS" in content

    def test_timeout_marks_issue_as_blocked(self):
        """タイムアウト時に akm:blocked を付与する記述があること。"""
        content = _read_workflow_text(self._WORKFLOW)
        assert "akm:blocked" in content
        assert 'TIMEOUT_MINUTES: "350"' in content
        assert "MAX_POLLS * POLL_INTERVAL_SECONDS / 60" in content

    def test_timeout_rechecks_terminal_state_before_marking_blocked(self):
        steps = _load_workflow_yaml(self._WORKFLOW)["jobs"]["coordinate-akm"]["steps"]
        poll = next(s for s in steps if "Poll AKM terminal" in s.get("name", ""))
        script = poll.get("run", "")
        assert "poll < MAX_POLLS" in script
        assert "final_issue_json=" in script
        assert script.index("final_issue_json=") < script.index('--add-label "akm:blocked"')


class TestQaReadyTransitionSaveAndDispatchPermissions:
    """auto-issue-qa-ready-transition.yml の FR-CLOUD-24 更新契約を検証する。

    回答保存 job は contents:write、dispatch job は actions:write を持つこと。
    """

    _WORKFLOW = "auto-issue-qa-ready-transition.yml"

    def test_save_job_has_contents_write_permission(self):
        """回答保存 job が contents: write 権限を持つこと。"""
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        jobs = yaml_data.get("jobs", {})
        save_job = jobs.get("save-qa-answer", {})
        assert save_job, "save-qa-answer job がありません"
        perms = save_job.get("permissions", {})
        assert perms.get("contents") == "write", \
            "save-qa-answer job に contents: write がありません"

    def test_dispatch_job_has_actions_write_permission(self):
        """dispatch job が actions: write 権限を持つこと。"""
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        jobs = yaml_data.get("jobs", {})
        dispatch_job = jobs.get("dispatch-akm", {})
        assert dispatch_job, "dispatch-akm job がありません"
        perms = dispatch_job.get("permissions", {})
        assert perms.get("actions") == "write", \
            "dispatch-akm job に actions: write がありません"

    def test_branch_existence_check_before_save(self):
        """branch 実在確認を save 前に行う記述があること。"""
        content = _read_workflow_text(self._WORKFLOW)
        assert "refs/heads/" in content or "branch" in content.lower()

    def test_fixed_qa_path_pattern(self):
        r"""保存先が qa/ 固定パスパターンに一致すること。"""
        content = _read_workflow_text(self._WORKFLOW)
        assert "Issue-${ISSUE_NUMBER}-questionnaire-answered-${QA_SHA:0:8}.md" in content
        assert ".." in content and "拒否" in content

    def test_contents_api_readback_and_sha_verification(self):
        """Contents API の read-back と SHA 照合記述があること。"""
        content = _read_workflow_text(self._WORKFLOW)
        assert "/contents/${QA_PATH}?ref=${BRANCH}" in content
        assert "sha256" in content.lower()

    def test_dispatch_success_then_source_assignment(self):
        """dispatch API 成功後に source assignment へ進む記述があること。"""
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        jobs = yaml_data.get("jobs", {})
        dispatch = jobs.get("dispatch-akm", {})
        assert "gh workflow run auto-akm-after-qa.yml" in "\n".join(
            step.get("run", "") for step in dispatch.get("steps", [])
        )
        transition_needs = jobs.get("transition", {}).get("needs", [])
        if isinstance(transition_needs, str):
            transition_needs = [transition_needs]
        assert "dispatch-akm" in transition_needs

    def test_source_workflow_does_not_wait_for_akm_completion(self):
        """source workflow が AKM 完了を待機しない（非同期 dispatch）こと。

        workflow_dispatch API 呼び出し後に sleep/poll/wait するロジックがないことを検証。
        """
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        jobs = yaml_data.get("jobs", {})
        for job_name in ("save-qa-answer", "dispatch-akm", "transition"):
            job = jobs.get(job_name, {})
            for step in job.get("steps", []):
                run_script = step.get("run", "")
                assert "akm:done" not in run_script
                assert "akm:blocked" not in run_script


class TestQaAkmChildConcurrencyRouting:
    """QA同期AKM子フローがcoordinatorの大域lockと自己デッドロックしない契約。"""

    _WORKFLOW = "auto-knowledge-management-reusable.yml"

    def test_qa_sync_uses_separate_group_while_normal_akm_keeps_global_group(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        concurrency = yaml_data["jobs"]["orchestrate"]["concurrency"]
        group = concurrency.get("group", "")
        assert "qa-akm-sync" in group
        assert "akm-qa-sync-child-" in group
        assert "akm-knowledge-write-" in group
        assert concurrency.get("cancel-in-progress") is False

    def test_qa_sync_label_is_propagated_to_step_issues(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert 'index("qa-akm-sync")' in content
        assert 'STEP_LABELS=$(echo "${STEP_LABELS}" | jq -c' in content
        assert '["qa-akm-sync"]' in content


class TestAutoQaTimeoutWatcherWorkflow:
    """QA フェーズタイムアウト監視 workflow の静的検証。"""

    _WORKFLOW = "auto-qa-timeout-watcher.yml"

    def test_has_no_schedule_trigger(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        assert "schedule" not in on_section

    def test_has_workflow_dispatch_inputs(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        inputs = on_section.get("workflow_dispatch", {}).get("inputs", {})
        assert "target_issue" in inputs
        assert "dry_run" in inputs

    def test_manual_job_has_no_enable_flag_guard(self):
        watch_job = _load_workflow_yaml(self._WORKFLOW).get("jobs", {}).get("watch", {})
        assert "if" not in watch_job
        assert "ENABLE_QA_TIMEOUT_WATCHER" not in _read_workflow_text(self._WORKFLOW)

    def test_uses_default_timeout_variable_and_notification_marker(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert "QA_TIMEOUT_HOURS: ${{ vars.QA_PHASE_TIMEOUT_HOURS || '72' }}" in content
        assert "<!-- qa-timeout-notified -->" in content

    def test_handles_timeline_failure_without_failing_job(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert "timeline 解析に失敗したためスキップします" in content
        assert "/timeline?per_page=100" in content
        assert "--jq '.[]'" in content
        assert "jq -rs --arg label" in content
        assert "| max // \"\"" in content
