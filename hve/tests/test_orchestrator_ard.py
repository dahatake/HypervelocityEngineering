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

from config import SDKConfig
from orchestrator import (
    _generate_target_business_from_sr,
    _on_ard_step1_completed,
    _resolve_target_business_paths,
    _select_recommendation,
    run_workflow,
)


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
        cfg = SDKConfig(dry_run=True, quiet=True)
        result = _run(
            run_workflow(
                workflow_id="ard",
                params={"branch": "main", "selected_steps": ["1", "2", "3"], "target_business": ""},
                config=cfg,
            )
        )
        self.assertEqual(result.get("dag_plan_waves"), 3)

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
        self.assertIn("対象業務の詳細", params["target_business"])

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


if __name__ == "__main__":
    unittest.main()
