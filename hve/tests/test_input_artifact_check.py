"""test_input_artifact_check.py — 前提成果物チェックのテスト (Phase 8)

検証するケース:
  1. consumed_artifacts=[]       → 不足なし（前提成果物なし）
  2. consumed_artifacts=None     → 後方互換としてスキップ（fail しない）
  3. 明示キーで artifact が存在する → 不足なし
  4. 明示キーで artifact が存在しない → missing に追加（warning または strict failure）
  5. strict mode: missing artifact で should_abort=True
  6. 未知 artifact key: 捏造パスを出さない（key 名を含む不明メッセージのみ）
  7. _ARTIFACT_KEY_TO_EXPECTED_PATH のキーが KNOWN_ARTIFACT_KEYS と一致
  8. _ARTIFACT_KEY_TO_GENERATING_WORKFLOW のキーが KNOWN_ARTIFACT_KEYS に含まれる
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock
import unittest.mock

from hve.config import SDKConfig
from hve.orchestrator import (
    _ARTIFACT_KEY_TO_EXPECTED_PATH,
    _ARTIFACT_KEY_TO_GENERATING_WORKFLOW,
    _check_workflow_input_artifacts,
    check_step_input_artifacts,
)
from hve.workflow_registry import StepDef


# ---------------------------------------------------------------------------
# ヘルパー: ダミー Console
# ---------------------------------------------------------------------------


def _make_console() -> MagicMock:
    return MagicMock()


def _make_step(
    step_id: str = "1",
    consumed_artifacts=None,
) -> StepDef:
    return StepDef(
        id=step_id,
        title="test step",
        custom_agent=None,
        consumed_artifacts=consumed_artifacts,
    )


# ---------------------------------------------------------------------------
# テスト 1-2: consumed_artifacts=[] と None のセマンティクス
# ---------------------------------------------------------------------------


class TestCheckStepInputArtifactsSemantics(unittest.TestCase):
    """check_step_input_artifacts の基本セマンティクスを検証する。"""

    def test_empty_list_means_no_prereqs(self) -> None:
        """consumed_artifacts=[] は前提成果物なし → missing=[], skipped_none=False。"""
        step = _make_step(consumed_artifacts=[])
        result = check_step_input_artifacts(step, existing_artifacts={})
        self.assertEqual(result["missing"], [])
        self.assertFalse(result["skipped_none"])

    def test_none_means_backward_compat_skip(self) -> None:
        """consumed_artifacts=None は後方互換。チェックをスキップして skipped_none=True。"""
        step = _make_step(consumed_artifacts=None)
        result = check_step_input_artifacts(step, existing_artifacts={})
        self.assertEqual(result["missing"], [])
        self.assertTrue(result["skipped_none"])

    def test_none_never_fails_even_with_empty_existing(self) -> None:
        """consumed_artifacts=None は既存成果物が空でも fail しない。"""
        step = _make_step(consumed_artifacts=None)
        result = check_step_input_artifacts(step, existing_artifacts={})
        self.assertFalse(result.get("should_abort", False))


# ---------------------------------------------------------------------------
# テスト 3: 明示キーで artifact が存在する
# ---------------------------------------------------------------------------


class TestCheckStepInputArtifactsPresent(unittest.TestCase):
    """必要成果物がすべて存在する場合に missing が空であること。"""

    def test_all_keys_present_returns_no_missing(self) -> None:
        step = _make_step(consumed_artifacts=["app_catalog", "data_model"])
        existing = {"app_catalog": "docs/catalog/app-catalog.md", "data_model": "docs/catalog/data-model.md"}
        result = check_step_input_artifacts(step, existing_artifacts=existing)
        self.assertEqual(result["missing"], [])
        self.assertFalse(result["skipped_none"])

    def test_single_key_present(self) -> None:
        step = _make_step(consumed_artifacts=["service_catalog"])
        existing = {"service_catalog": "docs/catalog/service-catalog.md"}
        result = check_step_input_artifacts(step, existing_artifacts=existing)
        self.assertEqual(result["missing"], [])


# ---------------------------------------------------------------------------
# テスト 4: 明示キーで artifact が存在しない
# ---------------------------------------------------------------------------


class TestCheckStepInputArtifactsMissing(unittest.TestCase):
    """必要成果物が不足している場合に missing が正しく返されること。"""

    def test_missing_key_is_reported(self) -> None:
        step = _make_step(consumed_artifacts=["app_catalog"])
        result = check_step_input_artifacts(step, existing_artifacts={})
        self.assertEqual(len(result["missing"]), 1)
        item = result["missing"][0]
        self.assertEqual(item["key"], "app_catalog")
        self.assertIn("docs/catalog/app-catalog.md", item["expected"])

    def test_missing_key_includes_expected_path(self) -> None:
        step = _make_step(consumed_artifacts=["use_case_catalog"])
        result = check_step_input_artifacts(step, existing_artifacts={})
        self.assertEqual(len(result["missing"]), 1)
        item = result["missing"][0]
        self.assertIn("docs/catalog/use-case-catalog.md", item["expected"])

    def test_partial_missing(self) -> None:
        step = _make_step(consumed_artifacts=["app_catalog", "service_catalog"])
        existing = {"app_catalog": "docs/catalog/app-catalog.md"}
        result = check_step_input_artifacts(step, existing_artifacts=existing)
        self.assertEqual(len(result["missing"]), 1)
        self.assertEqual(result["missing"][0]["key"], "service_catalog")

    def test_missing_next_workflow_is_returned(self) -> None:
        """missing item に next_workflow フィールドが含まれること。"""
        step = _make_step(consumed_artifacts=["app_catalog"])
        result = check_step_input_artifacts(step, existing_artifacts={})
        item = result["missing"][0]
        # app_catalog は aas が生成する（確認済み）
        self.assertEqual(item["next_workflow"], "aas")

    def test_missing_knowledge_next_workflow_is_akm(self) -> None:
        step = _make_step(consumed_artifacts=["knowledge"])
        result = check_step_input_artifacts(step, existing_artifacts={})
        item = result["missing"][0]
        self.assertEqual(item["next_workflow"], "akm")

    def test_missing_use_case_catalog_next_workflow_is_none(self) -> None:
        """use_case_catalog は生成ワークフロー未確認 → next_workflow=None（要確認）。"""
        step = _make_step(consumed_artifacts=["use_case_catalog"])
        result = check_step_input_artifacts(step, existing_artifacts={})
        item = result["missing"][0]
        self.assertIsNone(item["next_workflow"])


# ---------------------------------------------------------------------------
# テスト 5: strict mode
# ---------------------------------------------------------------------------


class TestCheckWorkflowInputArtifactsStrict(unittest.TestCase):
    """strict mode (require_input_artifacts=True) で missing があれば should_abort=True になること。"""

    def _make_wf(self, consumed_artifacts):
        """ダミーワークフロー (1ステップ) を返す。"""
        step = _make_step("1", consumed_artifacts=consumed_artifacts)
        wf = MagicMock()
        wf.steps = [step]
        return wf

    def test_strict_mode_aborts_on_missing(self) -> None:
        wf = self._make_wf(consumed_artifacts=["app_catalog"])
        config = SDKConfig(require_input_artifacts=True)
        console = _make_console()
        result = _check_workflow_input_artifacts(
            wf=wf,
            active_steps={"1"},
            existing_artifacts={},
            config=config,
            console=console,
        )
        self.assertTrue(result["should_abort"])
        self.assertIsNotNone(result["error"])
        console.error.assert_called_once()

    def test_strict_mode_no_abort_when_all_present(self) -> None:
        wf = self._make_wf(consumed_artifacts=["app_catalog"])
        config = SDKConfig(require_input_artifacts=True)
        console = _make_console()
        result = _check_workflow_input_artifacts(
            wf=wf,
            active_steps={"1"},
            existing_artifacts={"app_catalog": "docs/catalog/app-catalog.md"},
            config=config,
            console=console,
        )
        self.assertFalse(result["should_abort"])
        console.error.assert_not_called()

    def test_warning_mode_does_not_abort_on_missing(self) -> None:
        """warning モード（デフォルト）では missing があっても should_abort=False。"""
        wf = self._make_wf(consumed_artifacts=["app_catalog"])
        config = SDKConfig(require_input_artifacts=False)
        console = _make_console()
        result = _check_workflow_input_artifacts(
            wf=wf,
            active_steps={"1"},
            existing_artifacts={},
            config=config,
            console=console,
        )
        self.assertFalse(result["should_abort"])
        console.warning.assert_called_once()
        console.error.assert_not_called()

    def test_warning_mode_is_default(self) -> None:
        """SDKConfig のデフォルトは require_input_artifacts=False（warning モード）。"""
        config = SDKConfig()
        self.assertFalse(config.require_input_artifacts)

    def test_none_consumed_artifacts_never_aborts_in_strict(self) -> None:
        """consumed_artifacts=None は strict モードでもスキップ（後方互換）。"""
        wf = self._make_wf(consumed_artifacts=None)
        config = SDKConfig(require_input_artifacts=True)
        console = _make_console()
        result = _check_workflow_input_artifacts(
            wf=wf,
            active_steps={"1"},
            existing_artifacts={},
            config=config,
            console=console,
        )
        self.assertFalse(result["should_abort"])
        console.error.assert_not_called()
        console.warning.assert_not_called()

    def test_empty_consumed_artifacts_never_aborts(self) -> None:
        """consumed_artifacts=[] は前提なし → should_abort=False。"""
        wf = self._make_wf(consumed_artifacts=[])
        config = SDKConfig(require_input_artifacts=True)
        console = _make_console()
        result = _check_workflow_input_artifacts(
            wf=wf,
            active_steps={"1"},
            existing_artifacts={},
            config=config,
            console=console,
        )
        self.assertFalse(result["should_abort"])

    def test_container_steps_are_skipped(self) -> None:
        """コンテナ Step は前提チェック対象外。"""
        step = StepDef(id="1", title="container", custom_agent=None, is_container=True,
                       consumed_artifacts=["app_catalog"])
        wf = MagicMock()
        wf.steps = [step]
        config = SDKConfig(require_input_artifacts=True)
        console = _make_console()
        result = _check_workflow_input_artifacts(
            wf=wf,
            active_steps={"1"},
            existing_artifacts={},
            config=config,
            console=console,
        )
        self.assertFalse(result["should_abort"])

    def test_inactive_steps_are_skipped(self) -> None:
        """active_steps に含まれない Step はチェック対象外。"""
        step = _make_step("2", consumed_artifacts=["app_catalog"])
        wf = MagicMock()
        wf.steps = [step]
        config = SDKConfig(require_input_artifacts=True)
        console = _make_console()
        result = _check_workflow_input_artifacts(
            wf=wf,
            active_steps={"1"},  # step "2" は含まれない
            existing_artifacts={},
            config=config,
            console=console,
        )
        self.assertFalse(result["should_abort"])

    def test_non_root_steps_are_skipped(self) -> None:
        """depends_on が空でない（非ルート）Step は開始前チェック対象外。

        同ワークフロー内の先行ステップが成果物を生成するケースで
        正当な実行が中断されないことを確認する。
        例: AAS Step 2 (depends_on=["1"]) は app_catalog を consumed するが
            Step 1 が app-catalog.md を出力するため、開始前には存在しない。
        """
        root_step = _make_step("1", consumed_artifacts=[])  # ルート: 前提なし
        non_root = StepDef(
            id="2",
            title="depends on step 1",
            custom_agent=None,
            depends_on=["1"],               # 非ルート
            consumed_artifacts=["app_catalog"],  # Step 1 が生成する予定
        )
        wf = MagicMock()
        wf.steps = [root_step, non_root]
        config = SDKConfig(require_input_artifacts=True)
        console = _make_console()
        result = _check_workflow_input_artifacts(
            wf=wf,
            active_steps={"1", "2"},
            existing_artifacts={},  # app_catalog はまだ存在しない
            config=config,
            console=console,
        )
        # 非ルートステップは除外されるため should_abort=False
        self.assertFalse(result["should_abort"])
        console.error.assert_not_called()


# ---------------------------------------------------------------------------
# テスト 6: 未知 artifact key
# ---------------------------------------------------------------------------


class TestCheckStepInputArtifactsUnknownKey(unittest.TestCase):
    """未知 artifact key の扱いを検証する。"""

    def test_unknown_key_is_reported_without_fake_path(self) -> None:
        """未知キーは missing に追加されるが、捏造したパスを返さない。"""
        step = _make_step(consumed_artifacts=["nonexistent_key_xyz"])
        result = check_step_input_artifacts(step, existing_artifacts={})
        self.assertEqual(len(result["missing"]), 1)
        item = result["missing"][0]
        self.assertEqual(item["key"], "nonexistent_key_xyz")
        # 捏造パスではなく「不明」を示す文字列
        self.assertIn("不明", item["expected"])
        self.assertIn("nonexistent_key_xyz", item["expected"])

    def test_unknown_key_next_workflow_is_none(self) -> None:
        """未知キーは next_workflow=None（断定しない）。"""
        step = _make_step(consumed_artifacts=["totally_unknown"])
        result = check_step_input_artifacts(step, existing_artifacts={})
        item = result["missing"][0]
        self.assertIsNone(item["next_workflow"])


# ---------------------------------------------------------------------------
# テスト 7-8: _ARTIFACT_KEY_TO_EXPECTED_PATH / _ARTIFACT_KEY_TO_GENERATING_WORKFLOW の整合性
# ---------------------------------------------------------------------------

_KNOWN_ARTIFACT_KEYS = frozenset([
    "app_catalog", "service_catalog", "data_model", "domain_analytics",
    "screen_catalog", "test_strategy", "service_catalog_matrix", "use_case_catalog",
    "batch_job_catalog", "batch_service_catalog", "batch_data_model", "batch_domain_analytics",
    "service_specs", "screen_specs", "test_specs",
    "src_files", "test_files", "knowledge",
    "agent_specs", "batch_job_specs", "doc_generated",
])


class TestArtifactKeyMappingConsistency(unittest.TestCase):
    """_ARTIFACT_KEY_TO_EXPECTED_PATH と _ARTIFACT_KEY_TO_GENERATING_WORKFLOW の整合性テスト。"""

    def test_expected_path_keys_match_known_keys(self) -> None:
        """_ARTIFACT_KEY_TO_EXPECTED_PATH のキーセットが KNOWN_ARTIFACT_KEYS と一致すること。"""
        path_keys = frozenset(_ARTIFACT_KEY_TO_EXPECTED_PATH.keys())
        self.assertEqual(
            path_keys,
            _KNOWN_ARTIFACT_KEYS,
            f"差分: {path_keys.symmetric_difference(_KNOWN_ARTIFACT_KEYS)}",
        )

    def test_generating_workflow_keys_are_subset_of_known(self) -> None:
        """_ARTIFACT_KEY_TO_GENERATING_WORKFLOW の各キーが既知キーに含まれること（個別エラーメッセージ付き）。"""
        for key in _ARTIFACT_KEY_TO_GENERATING_WORKFLOW:
            self.assertIn(
                key,
                _KNOWN_ARTIFACT_KEYS,
                f"未知キー '{key}' が _ARTIFACT_KEY_TO_GENERATING_WORKFLOW に含まれています",
            )

    def test_generating_workflow_keys_match_known_keys(self) -> None:
        """_ARTIFACT_KEY_TO_GENERATING_WORKFLOW のキーセットが KNOWN_ARTIFACT_KEYS と完全一致すること。"""
        gen_keys = frozenset(_ARTIFACT_KEY_TO_GENERATING_WORKFLOW.keys())
        self.assertEqual(
            gen_keys,
            _KNOWN_ARTIFACT_KEYS,
            f"差分: {gen_keys.symmetric_difference(_KNOWN_ARTIFACT_KEYS)}",
        )

    def test_expected_path_values_are_nonempty_strings(self) -> None:
        """_ARTIFACT_KEY_TO_EXPECTED_PATH の値が空でない文字列であること。"""
        for key, path in _ARTIFACT_KEY_TO_EXPECTED_PATH.items():
            self.assertIsInstance(path, str, f"key={key!r}: str を期待")
            self.assertTrue(path, f"key={key!r}: 空文字列は不正")


# ---------------------------------------------------------------------------
# テスト: SDKConfig.require_input_artifacts の環境変数読み込み
# ---------------------------------------------------------------------------


class TestSDKConfigRequireInputArtifacts(unittest.TestCase):
    """SDKConfig.require_input_artifacts の環境変数サポートを確認する。"""

    def test_default_is_false(self) -> None:
        config = SDKConfig()
        self.assertFalse(config.require_input_artifacts)

    def test_env_true_sets_strict(self) -> None:
        import os
        with unittest.mock.patch.dict(os.environ, {"HVE_REQUIRE_INPUT_ARTIFACTS": "true"}):
            config = SDKConfig.from_env()
        self.assertTrue(config.require_input_artifacts)

    def test_env_false_keeps_warning_mode(self) -> None:
        import os
        with unittest.mock.patch.dict(os.environ, {"HVE_REQUIRE_INPUT_ARTIFACTS": "false"}):
            config = SDKConfig.from_env()
        self.assertFalse(config.require_input_artifacts)

    def test_env_unset_defaults_to_false(self) -> None:
        import os
        env = {k: v for k, v in os.environ.items() if k != "HVE_REQUIRE_INPUT_ARTIFACTS"}
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            config = SDKConfig.from_env()
        self.assertFalse(config.require_input_artifacts)


if __name__ == "__main__":
    unittest.main()
