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

    def test_missing_use_case_catalog_next_workflow_is_ard(self) -> None:
        """use_case_catalog は ARD Step 4.3 で生成 → next_workflow='ard'。"""
        step = _make_step(consumed_artifacts=["use_case_catalog"])
        result = check_step_input_artifacts(step, existing_artifacts={})
        item = result["missing"][0]
        self.assertEqual(item["next_workflow"], "ard")


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
    "persona_catalog",
    "dataflow_catalog", "batch_service_catalog", "batch_data_model", "batch_domain_analytics",
    "service_specs", "screen_specs", "test_specs",
    "src_files", "test_files", "knowledge",
    "agent_specs", "dataflow_specs", "doc_generated",
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


# ---------------------------------------------------------------------------
# テスト: T-H1H2b — strict モード時の blocked / blocked_step_ids フィールド
# ---------------------------------------------------------------------------


class TestCheckWorkflowInputArtifactsBlockedFields(unittest.TestCase):
    """_check_workflow_input_artifacts が新 status ``blocked`` の入口を返すこと。

    新 status ``blocked`` (T-H1H2a) と連動し、artifact 不足を検出した時に
    上位レイヤーが「failed と区別された停止」として扱える情報を提供する。
    """

    def _make_wf(self, consumed_artifacts):
        step = _make_step("1", consumed_artifacts=consumed_artifacts)
        wf = MagicMock()
        wf.steps = [step]
        return wf

    def test_strict_mode_returns_blocked_true_on_missing(self) -> None:
        """strict + missing → blocked=True, blocked_step_ids にステップ ID。"""
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
        self.assertTrue(result["blocked"])
        self.assertEqual(result["blocked_step_ids"], ["1"])

    def test_strict_mode_no_missing_returns_blocked_false(self) -> None:
        """strict + 全て揃っている → blocked=False, blocked_step_ids=[]。"""
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
        self.assertFalse(result["blocked"])
        self.assertEqual(result["blocked_step_ids"], [])

    def test_warning_mode_does_not_set_blocked_even_on_missing(self) -> None:
        """warning モードでは missing があっても blocked=False (続行が前提)。"""
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
        self.assertFalse(result["blocked"])
        self.assertEqual(result["blocked_step_ids"], [])

    def test_blocked_step_ids_dedup_when_same_step_multiple_missing(self) -> None:
        """同一 step に複数 missing がある場合、blocked_step_ids は dedup される。"""
        step = _make_step("1", consumed_artifacts=["app_catalog", "service_catalog"])
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
        self.assertTrue(result["blocked"])
        # step "1" は missing が 2 件あっても 1 件のみ
        self.assertEqual(result["blocked_step_ids"], ["1"])

    def test_blocked_step_ids_preserve_order_across_steps(self) -> None:
        """複数 step が missing の場合、検出順を保持する。"""
        step_a = _make_step("A", consumed_artifacts=["app_catalog"])
        step_b = _make_step("B", consumed_artifacts=["service_catalog"])
        wf = MagicMock()
        wf.steps = [step_a, step_b]
        config = SDKConfig(require_input_artifacts=True)
        console = _make_console()
        result = _check_workflow_input_artifacts(
            wf=wf,
            active_steps={"A", "B"},
            existing_artifacts={},
            config=config,
            console=console,
        )
        self.assertTrue(result["blocked"])
        self.assertEqual(result["blocked_step_ids"], ["A", "B"])


# ---------------------------------------------------------------------------
# T-H1H2b: _run_workflow Phase 8 abort 戻り値の統合検証
# ---------------------------------------------------------------------------
class TestRunWorkflowAbortIncludesBlockedField(unittest.TestCase):
    """T-H1H2b: _run_workflow の strict abort path 戻り値に `blocked` キーが
    含まれることを検証する。

    `_run_workflow` 本体は依存が多く直接呼ぶと重いため、
    test_continue_on_error_e2e.py のパターンに準拠して
    Phase 8 abort 戻り値構造を等価ロジックで再現し検証する。
    併せて、orchestrator.py 内に該当の戻り値リテラルが存在する
    ことをソースコード regex で固定し、構造変更時にテストが
    壊れるようにする（最重要統合点の固定）。
    """

    def _build_abort_result(
        self,
        *,
        workflow_id: str,
        artifact_check: dict,
        continue_on_error: bool,
    ) -> dict | None:
        """orchestrator.py:3594-3618 の等価ロジック。

        実装と同一の dict literal を組み立て、戻り値構造の固定に用いる。
        """
        if artifact_check["should_abort"] and not continue_on_error:
            return {
                "workflow_id": workflow_id,
                "completed": [],
                "failed": [],
                "skipped": [],
                "blocked": list(artifact_check.get("blocked_step_ids", [])),
                "elapsed_total": 0.0,
                "error": artifact_check["error"],
            }
        return None

    def test_abort_dict_contains_blocked_step_ids(self) -> None:
        artifact_check = {
            "should_abort": True,
            "error": "missing input artifact for step 'step-a'",
            "blocked": True,
            "blocked_step_ids": ["step-a"],
        }
        result = self._build_abort_result(
            workflow_id="Arch-Sample",
            artifact_check=artifact_check,
            continue_on_error=False,
        )
        self.assertIsNotNone(result)
        assert result is not None  # for type narrowing
        self.assertEqual(result["blocked"], ["step-a"])
        self.assertEqual(result["completed"], [])
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["skipped"], [])
        self.assertEqual(result["workflow_id"], "Arch-Sample")
        self.assertIn("missing input artifact", result["error"])

    def test_abort_dict_blocked_is_empty_list_when_no_ids(self) -> None:
        """blocked_step_ids が空でも blocked キーは空配列で存在する（型安定性）。"""
        artifact_check = {
            "should_abort": True,
            "error": "missing",
            "blocked": False,
            "blocked_step_ids": [],
        }
        result = self._build_abort_result(
            workflow_id="wf-1",
            artifact_check=artifact_check,
            continue_on_error=False,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["blocked"], [])

    def test_no_abort_when_continue_on_error_true(self) -> None:
        """continue_on_error=True なら abort 戻り値が組み立てられない（警告に降格）。"""
        artifact_check = {
            "should_abort": True,
            "error": "missing",
            "blocked": True,
            "blocked_step_ids": ["step-a"],
        }
        result = self._build_abort_result(
            workflow_id="wf-2",
            artifact_check=artifact_check,
            continue_on_error=True,
        )
        self.assertIsNone(result)

    def test_no_abort_when_should_abort_false(self) -> None:
        """should_abort=False なら abort 戻り値が組み立てられない。"""
        artifact_check = {
            "should_abort": False,
            "error": None,
            "blocked": False,
            "blocked_step_ids": [],
        }
        result = self._build_abort_result(
            workflow_id="wf-3",
            artifact_check=artifact_check,
            continue_on_error=False,
        )
        self.assertIsNone(result)

    def test_orchestrator_source_includes_blocked_key_in_abort_literal(self) -> None:
        """orchestrator.py の Phase 8 (artifact) と Phase 9 (skill) abort dict
        literal に `"blocked":` が含まれることをソース regex で固定。
        構造変更時に本テストが壊れる。
        """
        import re
        from pathlib import Path

        source_path = Path(__file__).resolve().parent.parent / "orchestrator.py"
        source = source_path.read_text(encoding="utf-8")
        # artifact check (Phase 8) abort 戻り値
        artifact_pattern = re.compile(
            r'"blocked":\s*list\(_artifact_check\.get\("blocked_step_ids"',
        )
        artifact_matches = artifact_pattern.findall(source)
        self.assertGreaterEqual(
            len(artifact_matches),
            1,
            "Phase 8 abort 戻り値 dict literal に 'blocked' キーが含まれていません。"
            " orchestrator.py の run_workflow の戻り値構造を確認してください。",
        )
        # skill check (Phase 9) abort 戻り値
        skill_pattern = re.compile(
            r'"blocked":\s*list\(_skill_check\.get\("blocked_step_ids"',
        )
        skill_matches = skill_pattern.findall(source)
        self.assertGreaterEqual(
            len(skill_matches),
            1,
            "Phase 9 abort 戻り値 dict literal に 'blocked' キーが含まれていません。"
            " orchestrator.py の Skill 不足 abort path を確認してください。",
        )


# ---------------------------------------------------------------------------
# T-H1H2b: _check_required_skills_for_active_steps の blocked フィールド検証
# ---------------------------------------------------------------------------
class TestCheckRequiredSkillsBlockedFields(unittest.TestCase):
    """T-H1H2b: 必須 Skill 不足 abort path の戻り値に `blocked` /
    `blocked_step_ids` が含まれることを検証する。
    """

    def _make_console(self) -> Any:
        console = MagicMock()
        console.warning = MagicMock()
        console.error = MagicMock()
        return console

    def _make_step(self, step_id: str, required_skills: list[str]) -> Any:
        step = MagicMock()
        step.id = step_id
        step.title = f"step-{step_id}"
        step.is_container = False
        step.required_skills = required_skills
        return step

    def _make_wf(self, steps: list[Any]) -> Any:
        wf = MagicMock()
        wf.steps = steps
        return wf

    def test_no_missing_skills_returns_blocked_false(self) -> None:
        from hve.orchestrator import _check_required_skills_for_active_steps

        wf = self._make_wf([self._make_step("A", [])])
        console = self._make_console()
        result = _check_required_skills_for_active_steps(
            wf=wf,
            workflow_id="test-wf",
            active_steps={"A"},
            console=console,
        )
        self.assertFalse(result["should_abort"])
        self.assertFalse(result["blocked"])
        self.assertEqual(result["blocked_step_ids"], [])

    def test_missing_skill_returns_blocked_true_with_step_ids(self) -> None:
        from hve.orchestrator import _check_required_skills_for_active_steps

        wf = self._make_wf(
            [
                self._make_step("A", ["nonexistent-skill-xyz"]),
                self._make_step("B", ["another-missing-skill"]),
            ]
        )
        console = self._make_console()
        # validate_skill_names が "nonexistent-skill-xyz" / "another-missing-skill"
        # を missing として返すように patch する。
        with unittest.mock.patch(
            "hve.skill_resolver.validate_skill_names",
            return_value=(
                ["nonexistent-skill-xyz", "another-missing-skill"],
                [],
                {},
            ),
        ), unittest.mock.patch(
            "hve.skill_resolver.get_required_skills_for_step",
            side_effect=lambda workflow_id, step_id, step_declared_required: (
                ["nonexistent-skill-xyz"] if step_id == "A" else ["another-missing-skill"]
            ),
        ):
            result = _check_required_skills_for_active_steps(
                wf=wf,
                workflow_id="test-wf",
                active_steps={"A", "B"},
                console=console,
            )
        self.assertTrue(result["should_abort"])
        self.assertTrue(result["blocked"])
        self.assertEqual(result["blocked_step_ids"], ["A", "B"])
        self.assertIn("status=blocked", result["error"])

    def test_skill_resolver_import_failure_returns_blocked_false(self) -> None:
        """Skill resolver 自体が読み込めない場合は warning 経由で skip するため
        blocked=False を維持する（後方互換）。
        """
        from hve.orchestrator import _check_required_skills_for_active_steps

        wf = self._make_wf([self._make_step("A", ["x"])])
        console = self._make_console()
        # skill_resolver 自体の import を失敗させる
        with unittest.mock.patch.dict("sys.modules", {"hve.skill_resolver": None}), \
             unittest.mock.patch.dict("sys.modules", {"skill_resolver": None}):
            result = _check_required_skills_for_active_steps(
                wf=wf,
                workflow_id="test-wf",
                active_steps={"A"},
                console=console,
            )
        # blocked フィールドが存在し False であることを確認
        self.assertIn("blocked", result)
        self.assertFalse(result["blocked"])
        self.assertEqual(result["blocked_step_ids"], [])


# ---------------------------------------------------------------------------
# T-H1H2b: CLI 終了コード判定で blocked を error より先に判定することの検証
# ---------------------------------------------------------------------------
class TestCLIBlockedBranchEvaluatedBeforeError(unittest.TestCase):
    """T-H1H2b: __main__.py の終了コード判定で `blocked` が `error` より
    先に判定されることを検証する（等価ロジックレベル）。

    実 CLI ハンドラ (`_cmd_workflow` / Cloud workflow) は重い
    `asyncio.run` セットアップを含むため、`test_continue_on_error_e2e.py`
    のパターンに準拠して終了コード判定ロジックを等価再現する。
    併せて、`__main__.py` の該当箇所にも `result.get("blocked")` 分岐が
    `result.get("error")` 分岐より前に存在することを regex で確認する。
    """

    def _classify(self, result: dict) -> str:
        """__main__.py の終了コード判定等価ロジック (blocked / error / failed / ok)。"""
        if result.get("blocked"):
            return "blocked"
        if result.get("error"):
            return "error"
        if result.get("failed"):
            return "failed"
        return "ok"

    def test_blocked_takes_precedence_over_error(self) -> None:
        result = {
            "blocked": ["step-a"],
            "error": "missing input artifact for step 'step-a'",
            "failed": [],
        }
        self.assertEqual(self._classify(result), "blocked")

    def test_error_evaluated_when_blocked_is_empty(self) -> None:
        result = {"blocked": [], "error": "some other error", "failed": []}
        self.assertEqual(self._classify(result), "error")

    def test_error_evaluated_when_blocked_key_absent(self) -> None:
        # 後方互換: 古い戻り値 (blocked キーなし) でも従来通り error 経路に流れる。
        result = {"error": "some error", "failed": []}
        self.assertEqual(self._classify(result), "error")

    def test_failed_evaluated_when_no_blocked_or_error(self) -> None:
        result = {"blocked": [], "error": None, "failed": ["step-x"]}
        self.assertEqual(self._classify(result), "failed")

    def test_main_source_includes_blocked_branch_before_error_branch(self) -> None:
        """__main__.py の 2 ハンドラ全てで `result.get("blocked")` が
        `result.get("error")` より先に評価されていることを regex で固定。
        """
        import re
        from pathlib import Path

        source_path = Path(__file__).resolve().parent.parent / "__main__.py"
        source = source_path.read_text(encoding="utf-8")
        # 「result.get("blocked")」が出現してから「result.get("error")」が
        # 出現するパターンが少なくとも 2 箇所 (workflow CLI /
        # cloud workflow CLI) で存在することを確認。
        pattern = re.compile(
            r'result\.get\("blocked"\).*?result\.get\("error"\)',
            re.DOTALL,
        )
        matches = pattern.findall(source)
        self.assertGreaterEqual(
            len(matches),
            2,
            "__main__.py の終了コード判定で `blocked` 分岐が `error` 分岐より"
            "前に評価されていない箇所があります。workflow / cloud "
            "workflow の 2 ハンドラ全てを確認してください。",
        )


if __name__ == "__main__":
    unittest.main()
