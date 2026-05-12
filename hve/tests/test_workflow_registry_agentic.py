"""test_workflow_registry_agentic.py — Agentic Retrieval 関連 Step の整合性検証テスト（Phase 7）

workflow_registry.py の AAD-WEB / ASDW-WEB ワークフロー定義に対して、
Agentic Retrieval 関連 Step の存在・依存整合性・スキップ条件を検証する。

NOTE:
  現時点で Agentic Retrieval は専用の独立 Step ではなく、以下のステップ内で処理される：
  - AAD-WEB Step.2.2: Arch-Microservice-ServiceDetail
      → Arch-AgenticRetrieval-Detail Custom Agent に委譲（Arch-AgenticRetrieval-Detail 相当）
  - ASDW-WEB Step.2.2: Dev-Microservice-Azure-AddServiceDesign（AgenticRetrievalDesign 相当）
  - ASDW-WEB Step.2.3: Dev-Microservice-Azure-AddServiceDeploy（AgenticRetrievalDeploy 相当）
  スキップ判定は registry 単体では完結せず normalize_agentic_retrieval_answers によって
  orchestrator レベルで処理される（本ファイルの TestAgenticRetrievalSkipCondition を参照）。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml  # PyYAML は CI (test-hve-python.yml) で必須インストール済み

from hve.workflow_registry import get_step

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"

# ---------------------------------------------------------------------------
# AAD-WEB: Arch-AgenticRetrieval-Detail 相当の Step 検証
# ---------------------------------------------------------------------------


class TestAadWebAgenticRetrievalStep:
    """AAD-WEB の Agentic Retrieval 関連 Step の存在・整合性を検証する。"""

    def test_aad_web_step_2_2_exists(self):
        """AAD-WEB の Step.2.2 が存在すること。"""
        step = get_step("aad-web", "2.2")
        assert step is not None

    def test_aad_web_step_2_2_uses_service_detail_agent(self):
        """AAD-WEB の Step.2.2 が Arch-Microservice-ServiceDetail を使用すること。

        Arch-Microservice-ServiceDetail は Arch-AgenticRetrieval-Detail に委譲するため、
        この Step が Agentic Retrieval 相当の処理を担う。
        """
        step = get_step("aad-web", "2.2")
        assert step is not None
        assert step.custom_agent == "Arch-Microservice-ServiceDetail"

    def test_aad_web_step_2_2_depends_on_step_1(self):
        """AAD-WEB の Step.2.2 が Step.1 に依存すること。"""
        step = get_step("aad-web", "2.2")
        assert step is not None
        assert "1" in step.depends_on

    def test_aad_web_step_2_2_is_not_container(self):
        """AAD-WEB の Step.2.2 がコンテナでないこと。"""
        step = get_step("aad-web", "2.2")
        assert step is not None
        assert step.is_container is False

    def test_aad_web_all_four_steps_exist(self):
        """AAD-WEB の全 4 Step（1 / 2.1 / 2.2 / 2.3）が存在すること。"""
        for step_id in ["1", "2.1", "2.2", "2.3"]:
            step = get_step("aad-web", step_id)
            assert step is not None, f"AAD-WEB に Step.{step_id} が存在しません"


# ---------------------------------------------------------------------------
# ASDW-WEB: AgenticRetrievalDesign / AgenticRetrievalDeploy 相当の Step 検証
# ---------------------------------------------------------------------------


class TestAsdwWebAgenticRetrievalSteps:
    """ASDW-WEB の AgenticRetrievalDesign / AgenticRetrievalDeploy 相当 Step を検証する。"""

    def test_asdw_web_step_2_2_exists(self):
        """ASDW-WEB の Step.2.2（AgenticRetrievalDesign 相当）が存在すること。"""
        step = get_step("asdw-web", "2.2")
        assert step is not None

    def test_asdw_web_step_2_2_uses_add_service_design_agent(self):
        """ASDW-WEB の Step.2.2 が Dev-Microservice-Azure-AddServiceDesign を使用すること。

        このステップは Agentic Retrieval の設計 (AgenticRetrievalDesign 相当) を担う。
        """
        step = get_step("asdw-web", "2.2")
        assert step is not None
        assert step.custom_agent == "Dev-Microservice-Azure-AddServiceDesign"

    def test_asdw_web_step_2_3_exists(self):
        """ASDW-WEB の Step.2.3（AgenticRetrievalDeploy 相当）が存在すること。"""
        step = get_step("asdw-web", "2.3")
        assert step is not None

    def test_asdw_web_step_2_3_uses_add_service_deploy_agent(self):
        """ASDW-WEB の Step.2.3 が Dev-Microservice-Azure-AddServiceDeploy を使用すること。

        このステップは Agentic Retrieval のデプロイ (AgenticRetrievalDeploy 相当) を担う。
        """
        step = get_step("asdw-web", "2.3")
        assert step is not None
        assert step.custom_agent == "Dev-Microservice-Azure-AddServiceDeploy"

    def test_asdw_web_step_2_3_depends_on_step_2_2(self):
        """ASDW-WEB の Step.2.3 が Step.2.2 に依存すること（Deploy は Design 後）。"""
        step = get_step("asdw-web", "2.3")
        assert step is not None
        assert "2.2" in step.depends_on

    def test_asdw_web_step_2_2_depends_on_step_2_1(self):
        """ASDW-WEB の Step.2.2 が Step.2.1 に依存すること。"""
        step = get_step("asdw-web", "2.2")
        assert step is not None
        assert "2.1" in step.depends_on


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

    def test_step_2_3_depends_on_step_2_1_and_2_2(self):
        """AAD-WEB の Step.2.3 が Step.2.1 AND Step.2.2 に依存すること（AND join）。"""
        step = get_step("aad-web", "2.3")
        assert step is not None
        assert "2.1" in step.depends_on
        assert "2.2" in step.depends_on

    def test_step_2_1_and_2_2_parallel_after_step_1(self):
        """Step.2.1 と Step.2.2 が Step.1 完了後に並列起動可能であること。"""
        from hve.workflow_registry import get_next_steps

        nexts = get_next_steps("aad-web", completed_step_ids=["1"])
        next_ids = sorted(s.id for s in nexts)
        assert "2.1" in next_ids
        assert "2.2" in next_ids

    def test_step_2_3_requires_both_2_1_and_2_2(self):
        """Step.2.1 だけ完了でも Step.2.3 は起動されないこと（AND join）。"""
        from hve.workflow_registry import get_next_steps

        nexts = get_next_steps("aad-web", completed_step_ids=["1", "2.1"])
        next_ids = [s.id for s in nexts]
        assert "2.3" not in next_ids

    def test_step_2_3_available_after_both_2_1_and_2_2(self):
        """Step.2.1 AND Step.2.2 完了後に Step.2.3 が起動可能になること。"""
        from hve.workflow_registry import get_next_steps

        nexts = get_next_steps("aad-web", completed_step_ids=["1", "2.1", "2.2"])
        next_ids = [s.id for s in nexts]
        assert "2.3" in next_ids


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

    def test_step_2_1_depends_on_step_1_2(self):
        """ASDW-WEB の Step.2.1 が Step.1.2 に依存すること。"""
        step = get_step("asdw-web", "2.1")
        assert step is not None
        assert "1.2" in step.depends_on

    def test_step_2_5_depends_on_step_2_4(self):
        """ASDW-WEB の Step.2.5 が Step.2.4 に依存すること。"""
        step = get_step("asdw-web", "2.5")
        assert step is not None
        assert "2.4" in step.depends_on


# ---------------------------------------------------------------------------
# Agentic Retrieval スキップ条件の検証
# ---------------------------------------------------------------------------


class TestAgenticRetrievalSkipCondition:
    """enable_agentic_retrieval=no 条件での正規化動作を検証する。

    NOTE: workflow_registry.py は enable_agentic_retrieval によるスキップ判定を直接持たない。
          スキップ/無効化は normalize_agentic_retrieval_answers が担い、
          orchestrator / reusable workflow レベルで処理される。
          本クラスはその正規化ロジックを直接テストする。
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

    def test_dispatcher_propagates_all_agentic_inputs_to_asdw_web(self):
        """Dispatcher の asdw-web ジョブ `with:` セクションに Q1〜Q6 が存在すること。

        jobs.asdw-web.with の keys を YAML パースで構造的に確認する。
        ファイル全体の文字列検索ではなく、ジョブスコープに限定して検証する。
        """
        with_keys = _get_dispatcher_job_with_keys("asdw-web")
        expected_inputs = [
            "enable_agentic_retrieval",
            "agentic_data_source_modes",
            "foundry_mcp_integration",
            "agentic_data_sources_hint",
            "agentic_existing_design_diff_only",
            "foundry_sku_fallback_policy",
        ]
        for input_name in expected_inputs:
            assert input_name in with_keys, \
                f"dispatcher の asdw-web ジョブ with に '{input_name}' が見つかりません"


class TestQaReadyLabelTokenFallback:
    """qa-ready / labeled 連鎖トリガー用ラベル付与時のトークン設定を検証する。"""

    def test_qa_ready_labeling_steps_use_copilot_pat_fallback_token(self):
        targets = [
            ("auto-app-selection-reusable.yml", "Issue 初期化とStep Issue 生成"),
            ("auto-app-detail-design-web-reusable.yml", "Issue 初期化とStep Issue 生成"),
            ("auto-app-dev-microservice-web-reusable.yml", "Issue 初期化とStep Issue 生成"),
            ("auto-batch-design-reusable.yml", "Issue 初期化とStep Issue 生成"),
            ("auto-batch-dev-reusable.yml", "Issue 初期化とStep Issue 生成"),
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


class TestPlaywrightE2EReusableWorkflow:
    """Playwright E2E reusable workflow の静的構造検証。"""

    _WORKFLOW = "e2e-playwright-reusable.yml"

    def test_has_workflow_call_inputs(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        inputs = on_section.get("workflow_call", {}).get("inputs", {})
        assert "e2e_base_url" in inputs
        assert "service_catalog_path" in inputs
        assert "working_directory" in inputs

    def test_has_failure_artifact_upload_steps(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        jobs = yaml_data.get("jobs", {})
        job = jobs.get("playwright-e2e", {})
        steps = job.get("steps", [])
        upload_names = [step.get("name", "") for step in steps]
        assert "Upload Playwright HTML report (failure only)" in upload_names
        assert "Upload Playwright traces (failure only)" in upload_names


class TestIssueQaReadyTransitionWorkflow:
    """Issue の qa-ready / qa-drafting 遷移 workflow を静的検証する。"""

    _WORKFLOW = "auto-issue-qa-ready-transition.yml"

    def test_excludes_pre_qa_marker_from_answer_candidates(self):
        inject_step = _get_workflow_step(
            self._WORKFLOW,
            job_name="transition",
            step_name="QA 回答コンテキストを Issue body に注入（冪等性マーカー付き）",
        )
        run_script = inject_step.get("run", "")
        assert re.search(
            r'contains\("<!-- copilot-auto-pre-qa-posted -->"\)\)\s*\|\s*not',
            run_script,
        )
        assert not re.search(
            r'or\s*\(?\s*\(\(\.body\s*//\s*""\)\s*\|\s*contains\("<!-- copilot-auto-pre-qa-posted -->"\)\)',
            run_script,
        )

    def test_uses_human_copilot_mentions_for_manual_answers(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert 'contains("@copilot")' in content
        assert '(.author_association // "") == "OWNER"' in content
        assert '(.author_association // "") == "MEMBER"' in content
        assert '(.author_association // "") == "COLLABORATOR"' in content
        assert '(.user.type // "") != "Bot"' in content

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
        assert "l.endswith(':qa-ready') or l.endswith(':qa-drafting')" in content

    def test_ready_transition_maps_qa_drafting_to_ready(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert 'READY_LABEL="${READY_LABEL/:qa-drafting/:ready}"' in content

    def test_transition_workflow_exports_copilot_pat(self):
        content = _read_workflow_text(self._WORKFLOW)
        assert "COPILOT_PAT: ${{ secrets.COPILOT_PAT }}" in content

    def test_has_workflow_dispatch_inputs_for_dry_run(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        inputs = on_section.get("workflow_dispatch", {}).get("inputs", {})
        assert "target_issue" in inputs
        assert "target_pr" in inputs
        assert "dry_run" in inputs
        assert "simulate_label" in inputs

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


class TestAutoQaTimeoutWatcherWorkflow:
    """QA フェーズタイムアウト監視 workflow の静的検証。"""

    _WORKFLOW = "auto-qa-timeout-watcher.yml"

    def test_has_schedule_cron_every_6_hours(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        schedule = on_section.get("schedule", [])
        assert any(item.get("cron") == "0 */6 * * *" for item in schedule)

    def test_has_workflow_dispatch_inputs(self):
        yaml_data = _load_workflow_yaml(self._WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        inputs = on_section.get("workflow_dispatch", {}).get("inputs", {})
        assert "target_issue" in inputs
        assert "dry_run" in inputs

    def test_job_has_enable_flag_guard(self):
        watch_job = _load_workflow_yaml(self._WORKFLOW).get("jobs", {}).get("watch", {})
        assert watch_job.get("if", "") == "${{ vars.ENABLE_QA_TIMEOUT_WATCHER != 'false' }}"

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
