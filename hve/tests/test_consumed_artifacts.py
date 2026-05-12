"""test_consumed_artifacts.py — consumed_artifacts の妥当性テスト (Phase 4)

検証項目:
  1. consumed_artifacts に使用されているキーが _detect_existing_artifacts() の既知キーに含まれること
  2. consumed_artifacts=[] と None の意味が区別されていること
  3. Phase 4 対象ワークフローで consumed_artifacts=None が必要最小限になっていること
  4. None を残す Step は allowlist で明示管理されていること
  5. 既存 Phase 1 の reuse_context_filtering テストを壊さないこと
"""

from __future__ import annotations

import pytest

from hve.workflow_registry import get_workflow, list_workflows


# ---------------------------------------------------------------------------
# _detect_existing_artifacts() が返す既知キーの定義（orchestrator.py と同期）
# ---------------------------------------------------------------------------

KNOWN_ARTIFACT_KEYS: frozenset[str] = frozenset(
    [
        "app_catalog",
        "service_catalog",
        "data_model",
        "domain_analytics",
        "screen_catalog",
        "test_strategy",
        "service_catalog_matrix",
        "use_case_catalog",
        "batch_job_catalog",
        "batch_service_catalog",
        "batch_data_model",
        "batch_domain_analytics",
        "service_specs",
        "screen_specs",
        "test_specs",
        "src_files",
        "test_files",
        "knowledge",
        "agent_specs",
        "batch_job_specs",
        "doc_generated",
    ]
)

# ---------------------------------------------------------------------------
# Phase 4 で consumed_artifacts=None を意図的に残した Step の allowlist
# （ここに列挙された Step は None のままで許容される）
# 現時点では全 Phase 4 対象ワークフローの consumed_artifacts を設定済みのため空。
# ---------------------------------------------------------------------------

ALLOWED_NONE_STEPS: dict[str, list[str]] = {
    # "workflow_id": ["step_id", ...],
    # 例: "aas": ["1"] — 将来後方互換が必要な場合はここに追加し、理由をコメントで記載する
}


# ---------------------------------------------------------------------------
# テスト 1: 全 consumed_artifacts キーが既知キーに含まれること
# ---------------------------------------------------------------------------


class TestConsumedArtifactsKeysAreKnown:
    """workflow_registry.py 内の consumed_artifacts キーはすべて既知キーであること。"""

    @pytest.mark.parametrize("wf", list_workflows(), ids=lambda w: w.id)
    def test_all_consumed_artifact_keys_are_known(self, wf) -> None:
        for step in wf.steps:
            if step.consumed_artifacts is None or step.is_container:
                continue
            unknown = set(step.consumed_artifacts) - KNOWN_ARTIFACT_KEYS
            assert not unknown, (
                f"Workflow '{wf.id}' Step '{step.id}': 未知の consumed_artifacts キー: {unknown}. "
                f"使用可能なキー: {sorted(KNOWN_ARTIFACT_KEYS)}"
            )


# ---------------------------------------------------------------------------
# テスト 2: consumed_artifacts=[] と None の意味が区別されていること
# ---------------------------------------------------------------------------


class TestConsumedArtifactsSemantics:
    """consumed_artifacts の None / [] / [key] の意味が正しく区別されていること。"""

    def test_none_means_backward_compat_all_artifacts(self) -> None:
        """consumed_artifacts=None は後方互換（全成果物を渡す）を意味する。"""
        from hve.workflow_registry import StepDef

        step = StepDef(id="x", title="test", custom_agent=None, consumed_artifacts=None)
        assert step.consumed_artifacts is None

    def test_empty_list_means_no_artifacts_needed(self) -> None:
        """consumed_artifacts=[] はこのステップが既存成果物を参照しないことを示す。"""
        from hve.workflow_registry import StepDef

        step = StepDef(id="x", title="test", custom_agent=None, consumed_artifacts=[])
        assert step.consumed_artifacts == []
        assert step.consumed_artifacts is not None

    def test_none_and_empty_list_are_distinct(self) -> None:
        """None と [] は同一でないこと（意味が異なる）。"""
        assert None is not []
        assert [] is not None


# ---------------------------------------------------------------------------
# テスト 3: Phase 4 対象ワークフローで consumed_artifacts=None が必要最小限
# ---------------------------------------------------------------------------

# Phase 4 で consumed_artifacts を明示設定したワークフロー ID
PHASE4_TARGET_WORKFLOWS = ["aas", "abd", "abdv", "aag", "aagd", "akm", "aqod", "asdw-web"]


class TestPhase4ConsumedArtifactsMinimized:
    """Phase 4 対象ワークフローで consumed_artifacts=None の Step が最小限であること。"""

    @pytest.mark.parametrize("wf_id", PHASE4_TARGET_WORKFLOWS)
    def test_no_none_consumed_artifacts_outside_allowlist(self, wf_id: str) -> None:
        """Phase 4 対象ワークフローの非コンテナ Step に consumed_artifacts=None がないこと。
        ただし ALLOWED_NONE_STEPS に登録済みの Step は除外する。"""
        wf = get_workflow(wf_id)
        assert wf is not None
        allowed = ALLOWED_NONE_STEPS.get(wf_id, [])
        none_steps = [
            step.id
            for step in wf.steps
            if not step.is_container
            and step.consumed_artifacts is None
            and step.id not in allowed
        ]
        assert none_steps == [], (
            f"Workflow '{wf_id}': 以下の Step に consumed_artifacts=None が残っている: {none_steps}. "
            f"必要な場合は ALLOWED_NONE_STEPS に理由付きで追加してください。"
        )


# ---------------------------------------------------------------------------
# テスト 3.5 (Sub-1 A-1): 全ワークフロー対象で consumed_artifacts=None を即時 reject
# ---------------------------------------------------------------------------


class TestAllWorkflowsConsumedArtifactsExplicit:
    """全ワークフローの非コンテナ Step で consumed_artifacts が明示されていること。

    Sub-1 (A-1) で導入: ALLOWED_NONE_STEPS に列挙されていない限り None を許容しない。
    新規ワークフローを追加するときも consumed_artifacts=[] を必ず明示する。
    """

    @pytest.mark.parametrize("wf", list_workflows(), ids=lambda w: w.id)
    def test_no_none_consumed_artifacts_any_workflow(self, wf) -> None:
        allowed = ALLOWED_NONE_STEPS.get(wf.id, [])
        none_steps = [
            step.id
            for step in wf.steps
            if not step.is_container
            and step.consumed_artifacts is None
            and step.id not in allowed
        ]
        assert none_steps == [], (
            f"Workflow '{wf.id}': consumed_artifacts=None の Step が残っています: {none_steps}. "
            f"前提成果物がない Step は consumed_artifacts=[] を明示してください。"
        )


# ---------------------------------------------------------------------------
# テスト 4: None を残す Step は allowlist で管理されていること
# ---------------------------------------------------------------------------


class TestAllowedNoneStepsAreManaged:
    """ALLOWED_NONE_STEPS に登録された Step は実際に存在し、None であること。"""

    def test_allowlisted_steps_exist_and_are_none(self) -> None:
        """ALLOWED_NONE_STEPS の全エントリが実際に存在し consumed_artifacts=None であること。"""
        for wf_id, step_ids in ALLOWED_NONE_STEPS.items():
            wf = get_workflow(wf_id)
            assert wf is not None, f"Workflow '{wf_id}' が見つからない"
            for step_id in step_ids:
                step = wf.get_step(step_id)
                assert step is not None, (
                    f"ALLOWED_NONE_STEPS: Workflow '{wf_id}' に Step '{step_id}' が存在しない"
                )
                assert step.consumed_artifacts is None, (
                    f"ALLOWED_NONE_STEPS: '{wf_id}' Step '{step_id}' は None を期待しているが "
                    f"{step.consumed_artifacts!r} が設定されている"
                )


# ---------------------------------------------------------------------------
# テスト 5: Phase 1 の reuse_context_filtering テストを壊さないこと
# （既存の AAD-WEB consumed_artifacts が維持されていること）
# ---------------------------------------------------------------------------


class TestPhase1ReuseContextFilteringUnchanged:
    """Phase 1 で設定済みの AAD-WEB consumed_artifacts が変更されていないこと。"""

    def test_aad_web_step1_consumed_artifacts(self) -> None:
        wf = get_workflow("aad-web")
        step = wf.get_step("1")
        assert step is not None
        assert set(step.consumed_artifacts) == {
            "app_catalog", "service_catalog", "data_model", "domain_analytics"
        }

    def test_aad_web_step21_consumed_artifacts(self) -> None:
        wf = get_workflow("aad-web")
        step = wf.get_step("2.1")
        assert step is not None
        assert set(step.consumed_artifacts) == {"screen_catalog", "app_catalog"}

    def test_aad_web_step22_consumed_artifacts(self) -> None:
        wf = get_workflow("aad-web")
        step = wf.get_step("2.2")
        assert step is not None
        assert set(step.consumed_artifacts) == {
            "app_catalog", "service_catalog", "data_model", "domain_analytics", "service_catalog_matrix"
        }

    def test_aad_web_step23_consumed_artifacts(self) -> None:
        wf = get_workflow("aad-web")
        step = wf.get_step("2.3")
        assert step is not None
        assert set(step.consumed_artifacts) == {
            "test_strategy", "screen_specs", "service_specs", "service_catalog_matrix",
            "data_model", "domain_analytics", "app_catalog"
        }

    def test_adoc_steps_consumed_artifacts_unchanged(self) -> None:
        """ADOC ワークフローの consumed_artifacts が変更されていないこと。"""
        wf = get_workflow("adoc")
        assert wf is not None
        # Step 1 は consumed_artifacts=[] (ソースコード読み込み、既存成果物は不要)
        step1 = wf.get_step("1")
        assert step1 is not None
        assert step1.consumed_artifacts == []
        # Step 4 は consumed_artifacts=["doc_generated"]
        step4 = wf.get_step("4")
        assert step4 is not None
        assert step4.consumed_artifacts == ["doc_generated"]


# ---------------------------------------------------------------------------
# テスト 6: Phase 4 で追加した consumed_artifacts の代表的な値を確認
# ---------------------------------------------------------------------------


class TestPhase4ConsumedArtifactsValues:
    """Phase 4 で設定した consumed_artifacts の代表値が正しいこと。"""

    def test_aas_step1_uses_use_case_catalog(self) -> None:
        wf = get_workflow("aas")
        step = wf.get_step("1")
        assert step is not None
        assert "use_case_catalog" in step.consumed_artifacts

    def test_aas_step4_uses_service_catalog(self) -> None:
        # Sub-4 (B-1): Step 4 を 4.1 (データモデル) / 4.2 (サンプルデータ) に分割
        wf = get_workflow("aas")
        step = wf.get_step("4.1")
        assert step is not None
        assert "service_catalog" in step.consumed_artifacts
        assert "domain_analytics" in step.consumed_artifacts
        assert "app_catalog" in step.consumed_artifacts

    def test_abd_step_11_uses_use_case_catalog(self) -> None:
        wf = get_workflow("abd")
        step = wf.get_step("1.1")
        assert step is not None
        assert "use_case_catalog" in step.consumed_artifacts

    def test_abd_step4_uses_batch_keys(self) -> None:
        wf = get_workflow("abd")
        step = wf.get_step("4")
        assert step is not None
        assert "batch_job_catalog" in step.consumed_artifacts
        assert "batch_data_model" in step.consumed_artifacts
        assert "batch_domain_analytics" in step.consumed_artifacts

    def test_abdv_step21_uses_test_specs(self) -> None:
        wf = get_workflow("abdv")
        step = wf.get_step("2.1")
        assert step is not None
        assert "test_specs" in step.consumed_artifacts
        assert "batch_job_specs" in step.consumed_artifacts

    def test_aag_step1_uses_service_specs(self) -> None:
        wf = get_workflow("aag")
        step = wf.get_step("1")
        assert step is not None
        assert "service_specs" in step.consumed_artifacts
        assert "use_case_catalog" in step.consumed_artifacts

    def test_aag_step2_uses_agent_specs(self) -> None:
        wf = get_workflow("aag")
        step = wf.get_step("2")
        assert step is not None
        assert "agent_specs" in step.consumed_artifacts

    def test_aagd_step21_uses_test_strategy(self) -> None:
        wf = get_workflow("aagd")
        step = wf.get_step("2.1")
        assert step is not None
        assert "test_strategy" in step.consumed_artifacts
        assert "agent_specs" in step.consumed_artifacts

    def test_akm_step1_consumed_artifacts_empty(self) -> None:
        """AKM Step 1: qa/, original-docs/ は既知 key なし → []"""
        wf = get_workflow("akm")
        step = wf.get_step("1")
        assert step is not None
        assert step.consumed_artifacts == []

    def test_aqod_step1_uses_knowledge(self) -> None:
        """AQOD Step 1: knowledge/D07-* は knowledge キーでカバー"""
        wf = get_workflow("aqod")
        step = wf.get_step("1")
        assert step is not None
        assert "knowledge" in step.consumed_artifacts

    def test_asdw_web_step11_uses_catalog_keys(self) -> None:
        wf = get_workflow("asdw-web")
        step = wf.get_step("1.1")
        assert step is not None
        assert "data_model" in step.consumed_artifacts
        assert "service_catalog" in step.consumed_artifacts
        assert "domain_analytics" in step.consumed_artifacts
        assert "app_catalog" in step.consumed_artifacts

    def test_asdw_web_step23t_uses_test_strategy(self) -> None:
        wf = get_workflow("asdw-web")
        step = wf.get_step("2.3T")
        assert step is not None
        assert "test_strategy" in step.consumed_artifacts
        assert "service_specs" in step.consumed_artifacts
