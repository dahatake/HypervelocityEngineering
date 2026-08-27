"""ARD orchestrator ブリッジ処理の単体テスト。"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import orchestrator as orchestrator_module
from config import SDKConfig
from orchestrator import (
    _collect_params_non_interactive,
    _generate_target_business_from_sr,
    _on_ard_step1_completed,
    _resolve_target_business_paths,
    _select_recommendation,
    run_workflow,
)
from hve.workflow_registry import get_workflow


def _run(coro):
    return asyncio.run(coro)


def _make_recommendations():
    return [
        types.SimpleNamespace(id="SR-1", title="施策1"),
        types.SimpleNamespace(id="SR-2", title="施策2"),
    ]


class TestOrchestratorARD(unittest.TestCase):
    def test_select_recommendation_picks_first_when_unattended(self):
        recs = _make_recommendations()
        config = SDKConfig()
        config.unattended = True
        selected = _select_recommendation(recs, config, {}, mock.MagicMock())
        self.assertEqual(selected.id, "SR-1")

    def test_select_recommendation_uses_explicit_id(self):
        recs = _make_recommendations()
        config = SDKConfig()
        selected = _select_recommendation(
            recs, config, {"target_recommendation_id": "SR-2"}, mock.MagicMock()
        )
        self.assertEqual(selected.id, "SR-2")

    def test_select_recommendation_falls_back_when_id_not_found(self):
        recs = _make_recommendations()
        config = SDKConfig()
        console = mock.MagicMock()
        selected = _select_recommendation(
            recs, config, {"target_recommendation_id": "SR-99"}, console
        )
        self.assertEqual(selected.id, "SR-1")
        console.warning.assert_called()

    def test_select_recommendation_uses_console_menu_in_interactive(self):
        recs = _make_recommendations()
        config = SDKConfig()
        config.unattended = False
        console = mock.MagicMock()
        console.menu_select.return_value = 1
        selected = _select_recommendation(recs, config, {}, console)
        self.assertEqual(selected.id, "SR-2")
        console.menu_select.assert_called_once()

    def test_generate_target_business_dry_run(self):
        config = SDKConfig(dry_run=True)
        selected = types.SimpleNamespace(id="SR-1", title="重点業務")
        result = _run(
            _generate_target_business_from_sr(
                selected_sr=selected,
                md_path=Path("docs/company-business-requirement.md"),
                config=config,
                params={"company_name": "テスト"},
                console=mock.MagicMock(),
            )
        )
        self.assertIn("[dry-run]", result)
        self.assertIn("SR-1", result)

    def test_run_workflow_dry_run_empty_target_business_is_serial(self):
        # ARD は現行8 stepに再設計され、Step 1.1 / 3.2 は fan-out 子持ち。
        # dry-run / fixture 不在の環境では fan-out 子の展開が 0 件 (fanout-empty) で skip され、
        # グループIDを渡し、現行registryの展開とbridge modeを検証する。
        cfg = SDKConfig(dry_run=True, quiet=True)
        result = _run(
            run_workflow(
                workflow_id="ard",
                params={
                    "branch": "main",
                    "selected_steps": ["1", "2", "4"],
                    "target_business": "",
                },
                config=cfg,
            )
        )
        self.assertGreaterEqual(result.get("dag_plan_waves", 0), 3)

    def test_include_kpi_okr_false_excludes_step_2_1(self):
        """include_kpi_okr=False（既定）の場合、Step 2.1 (KPI/OKR) は含まれない。"""
        cfg = SDKConfig(dry_run=True, quiet=True)
        result = _run(
            run_workflow(
                workflow_id="ard",
                params={
                    "branch": "main",
                    "selected_steps": ["2", "4"],
                    "target_business": "事業X",
                    "include_kpi_okr": False,
                },
                config=cfg,
            )
        )
        self.assertNotIn("2.1", result.get("skipped", []))

    def test_include_kpi_okr_true_includes_step_2_1(self):
        """include_kpi_okr=True の場合、Step 2.1 (KPI/OKR) がactive_stepsに含まれる。"""
        cfg = SDKConfig(dry_run=True, quiet=True)
        result = _run(
            run_workflow(
                workflow_id="ard",
                params={
                    "branch": "main",
                    "selected_steps": ["2", "4"],
                    "target_business": "事業X",
                    "include_kpi_okr": True,
                },
                config=cfg,
            )
        )
        # dry-run の skipped には active_steps が出力される
        self.assertIn("2.1", result.get("skipped", []))

    def test_resolve_target_business_paths_text_unchanged(self):
        params = {"target_business": "ロイヤルティ事業の会員運用業務"}
        _run(_resolve_target_business_paths(params, mock.MagicMock()))
        self.assertEqual(params["target_business"], "ロイヤルティ事業の会員運用業務")

    def test_resolve_target_business_paths_replaces_path(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path.cwd()
            os.chdir(td)
            try:
                p = Path("biz.md")
                p.write_text("対象業務の詳細", encoding="utf-8")
                params = {"target_business": "biz.md"}
                _run(_resolve_target_business_paths(params, mock.MagicMock()))
            finally:
                os.chdir(cwd)
        self.assertIn("## target_business: ファイル展開結果", params["target_business"])
        # FR-WF-ARD-02 (v2.57): 本文ではなくパス参照を渡す
        self.assertIn("biz.md", params["target_business"])
        self.assertNotIn("対象業務の詳細", params["target_business"])

    def test_no_recommendations_continues_without_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path.cwd()
            os.chdir(td)
            try:
                Path("docs").mkdir(parents=True, exist_ok=True)
                Path("docs/company-business-requirement.md").write_text(
                    "# sample", encoding="utf-8"
                )
                params = {"target_business": ""}
                config = SDKConfig(dry_run=True)
                with mock.patch(
                    "ard_recommendations.parse_recommendations", return_value=[]
                ), mock.patch(
                    "ard_recommendations.annotate_with_ids", return_value=[]
                ):
                    _run(
                        _on_ard_step1_completed(
                            config=config,
                            params=params,
                            console=mock.MagicMock(),
                        )
                    )
            finally:
                os.chdir(cwd)
        self.assertEqual(params["target_business"], "")

    def test_on_step1_completed_does_not_overwrite_when_target_business_exists(self):
        params = {"target_business": "既存の対象業務"}
        config = SDKConfig(dry_run=True)
        console = mock.MagicMock()
        with mock.patch("orchestrator.Path.exists", return_value=True), mock.patch(
            "ard_recommendations.parse_recommendations"
        ) as parse_mock, mock.patch(
            "ard_recommendations.annotate_with_ids"
        ) as annotate_mock:
            _run(
                _on_ard_step1_completed(
                    config=config,
                    params=params,
                    console=console,
                )
            )
        self.assertEqual(params["target_business"], "既存の対象業務")
        parse_mock.assert_not_called()
        annotate_mock.assert_not_called()


class TestArdRecommendationIdPropagation(unittest.TestCase):
    """FR-WF-ARD-03: build由来IDをeffective paramsへ保持する。"""

    def test_target_recommendation_id_survives_effective_param_normalization(self):
        workflow = get_workflow("ard")
        self.assertIsNotNone(workflow)
        effective = _collect_params_non_interactive(
            workflow, {"target_recommendation_id": "SR-2"}
        )
        self.assertEqual(effective.get("target_recommendation_id"), "SR-2")

    def test_unattended_bridge_selects_the_propagated_explicit_id(self):
        """B2がcustom-autoだけへ供給するIDを、共通unattended選択層が採用する。"""
        workflow = get_workflow("ard")
        self.assertIsNotNone(workflow)
        effective = _collect_params_non_interactive(
            workflow, {"target_recommendation_id": "sr-2"}
        )
        config = SDKConfig()
        config.unattended = True
        selected = _select_recommendation(
            _make_recommendations(), config, effective, mock.MagicMock()
        )
        self.assertEqual(selected.id, "SR-2")

    def test_manual_bridge_without_explicit_id_keeps_console_menu(self):
        workflow = get_workflow("ard")
        self.assertIsNotNone(workflow)
        effective = _collect_params_non_interactive(workflow, {})
        config = SDKConfig()
        config.unattended = False
        console = mock.MagicMock()
        console.menu_select.return_value = 1

        selected = _select_recommendation(
            _make_recommendations(), config, effective, console
        )

        self.assertEqual(selected.id, "SR-2")
        console.menu_select.assert_called_once()

    def test_explicit_id_is_ignored_outside_group_1_2_bridge(self):
        params = {
            "selected_steps": ["1", "4"],
            "target_business": "",
            "target_recommendation_id": "SR-2",
        }
        config = SDKConfig(dry_run=True)
        config.unattended = True
        recommendations = _make_recommendations()
        with tempfile.TemporaryDirectory() as td:
            cwd = Path.cwd()
            os.chdir(td)
            try:
                Path("docs").mkdir(parents=True, exist_ok=True)
                Path("docs/company-business-requirement.md").write_text(
                    "# sample", encoding="utf-8"
                )
                with mock.patch(
                    "ard_recommendations.parse_recommendations",
                    return_value=recommendations,
                ), mock.patch(
                    "ard_recommendations.annotate_with_ids",
                    return_value=recommendations,
                ), mock.patch.object(
                    orchestrator_module,
                    "_generate_target_business_from_sr",
                    new=mock.AsyncMock(return_value="generated"),
                ) as generate_mock:
                    _run(
                        _on_ard_step1_completed(
                            config=config,
                            params=params,
                            console=mock.MagicMock(),
                        )
                    )
            finally:
                os.chdir(cwd)

        selected_sr = generate_mock.await_args.kwargs["selected_sr"]
        self.assertEqual(selected_sr.id, "SR-1")


class TestArdNonInteractiveDefaults(unittest.TestCase):
    def test_missing_steps_use_registry_default_regardless_of_target_business(self):
        workflow = get_workflow("ard")
        self.assertIsNotNone(workflow)
        with mock.patch.object(
            orchestrator_module,
            "ARD_DEFAULT_GROUP_IDS",
            ("2", "4"),
        ):
            without_target = _collect_params_non_interactive(workflow, {})
            with_target = _collect_params_non_interactive(
                workflow,
                {"target_business": "事業A"},
            )
        self.assertEqual(without_target["selected_steps"], ["2", "4"])
        self.assertEqual(with_target["selected_steps"], ["2", "4"])

    def test_explicit_steps_are_not_overridden_by_the_default(self):
        workflow = get_workflow("ard")
        self.assertIsNotNone(workflow)
        with mock.patch.object(
            orchestrator_module,
            "ARD_DEFAULT_GROUP_IDS",
            ("2", "4"),
        ):
            effective = _collect_params_non_interactive(
                workflow,
                {"selected_steps": ["1", "3"]},
            )
        self.assertEqual(effective["selected_steps"], ["1", "3"])

    def test_blank_recommendation_id_is_treated_as_unspecified(self):
        workflow = get_workflow("ard")
        self.assertIsNotNone(workflow)
        effective = _collect_params_non_interactive(
            workflow,
            {"target_recommendation_id": "   "},
        )
        self.assertNotIn("target_recommendation_id", effective)


class TestArdBridgeBindsToStep12(unittest.TestCase):
    """SR 抽出ブリッジは Step 1.2 完了後に成立する契約。

    SR の抽出元 `docs/company-business-requirement.md` の producer は Step 1.2 で
    あり、Step 1 完了時点では存在しない。フックと DAG 依存の両方を 1.2 に
    合わせないと、Step 2 が `target_business` 空のまま実行される。
    """

    @staticmethod
    def _orchestrator_source() -> str:
        path = Path(__file__).resolve().parents[1] / "orchestrator.py"
        return path.read_text(encoding="utf-8")

    def test_hook_fires_after_step_1_2(self):
        src = self._orchestrator_source()
        self.assertIn('workflow_id == "ard" and step_id == "1.2" and success', src)
        self.assertNotIn('workflow_id == "ard" and step_id == "1" and success', src)

    def test_bridge_serializes_step_2_after_step_1_2(self):
        cfg = SDKConfig(dry_run=True, quiet=True)
        result = _run(
            run_workflow(
                workflow_id="ard",
                params={
                    "branch": "main",
                    "selected_steps": ["1", "2"],
                    "target_business": "",
                },
                config=cfg,
            )
        )
        self.assertGreaterEqual(result.get("dag_plan_waves", 0), 4)


if __name__ == "__main__":
    unittest.main()
