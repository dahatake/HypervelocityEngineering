"""ARD ワークフロー登録の単体テスト (PR-1 範囲)。"""
from __future__ import annotations

import unittest

try:
    from hve.workflow_registry import (
        get_workflow,
        get_root_steps,
        get_next_steps,
        list_workflows,
    )
except ImportError:  # flat import fallback
    from workflow_registry import (  # type: ignore[no-redef]
        get_workflow,
        get_root_steps,
        get_next_steps,
        list_workflows,
    )

try:
    from hve.template_engine import _WORKFLOW_DISPLAY_NAMES, _WORKFLOW_PREFIX
except ImportError:
    from template_engine import _WORKFLOW_DISPLAY_NAMES, _WORKFLOW_PREFIX  # type: ignore[no-redef]


class TestARDWorkflowRegistration(unittest.TestCase):
    def test_workflow_is_registered(self):
        wf = get_workflow("ard")
        self.assertIsNotNone(wf)
        self.assertEqual(wf.id, "ard")
        self.assertEqual(wf.name, "Auto Requirement Definition")
        self.assertEqual(wf.label_prefix, "ard")

    def test_state_labels(self):
        wf = get_workflow("ard")
        self.assertEqual(wf.state_labels, {
            "initialized": "ard:initialized",
            "ready": "ard:ready",
            "running": "ard:running",
            "done": "ard:done",
            "blocked": "ard:blocked",
        })

    def test_params_list(self):
        wf = get_workflow("ard")
        self.assertEqual(wf.params, [
            "company_name",
            "target_business",
            "survey_base_date",
            "survey_period_years",
            "target_region",
            "analysis_purpose",
            "attached_docs",
        ])

    def test_steps_ids(self):
        # Sub-10 (ADR-0003): ARD は 7 step に再設計
        wf = get_workflow("ard")
        ids = [s.id for s in wf.steps]
        self.assertEqual(ids, ["1", "1.1", "1.2", "2", "3.1", "3.2", "3.3"])

    def test_step_1_definition(self):
        # Sub-10: Step 1 は「事業分野候補列挙」
        wf = get_workflow("ard")
        s = wf.get_step("1")
        self.assertIsNotNone(s)
        self.assertEqual(s.custom_agent, "Arch-ARD-BusinessAnalysis-Untargeted")
        self.assertEqual(s.depends_on, [])
        self.assertEqual(s.output_paths, ["docs/company-business-recommendation.md"])

    def test_step_1_1_definition_is_fanout(self):
        # Sub-10: Step 1.1 は事業分野別深掘り分析の fan-out 起点
        wf = get_workflow("ard")
        s = wf.get_step("1.1")
        self.assertIsNotNone(s)
        self.assertEqual(s.depends_on, ["1"])
        self.assertEqual(s.fanout_parser, "business_candidate")
        self.assertEqual(s.output_paths_template, ["docs/business/{key}-analysis.md"])

    def test_step_1_2_definition_is_join(self):
        # Sub-10: Step 1.2 は事業分析統合 (join)
        wf = get_workflow("ard")
        s = wf.get_step("1.2")
        self.assertIsNotNone(s)
        self.assertEqual(s.depends_on, ["1.1"])
        self.assertEqual(s.output_paths, ["docs/company-business-requirement.md"])
        # 統合 step なので fan-out しない
        self.assertIsNone(s.fanout_parser)
        self.assertIsNone(s.fanout_static_keys)

    def test_step_2_definition(self):
        # Sub-10: Step 2 は対象業務深掘り分析 (target_business 指定時)
        wf = get_workflow("ard")
        s = wf.get_step("2")
        self.assertIsNotNone(s)
        self.assertEqual(s.custom_agent, "Arch-ARD-BusinessAnalysis-Targeted")
        self.assertEqual(s.depends_on, [])
        self.assertEqual(s.skip_fallback_deps, ["1.2"])
        self.assertEqual(s.output_paths, ["docs/business-requirement.md"])

    def test_step_3_1_skeleton_extraction(self):
        # Sub-10: Step 3.1 はユースケース骨格抽出
        wf = get_workflow("ard")
        s = wf.get_step("3.1")
        self.assertIsNotNone(s)
        self.assertEqual(s.custom_agent, "Arch-ARD-UseCaseCatalog")
        self.assertEqual(s.depends_on, ["2"])
        self.assertEqual(s.skip_fallback_deps, ["1.2"])
        self.assertEqual(s.output_paths, ["docs/catalog/use-case-skeleton.md"])
        self.assertEqual(
            s.required_input_paths,
            [
                "docs/business-requirement.md",
                "docs/company-business-requirement.md",
            ],
        )

    def test_step_3_2_is_fanout(self):
        # Sub-10: Step 3.2 はユースケース詳細生成の fan-out
        wf = get_workflow("ard")
        s = wf.get_step("3.2")
        self.assertIsNotNone(s)
        self.assertEqual(s.depends_on, ["3.1"])
        self.assertEqual(s.fanout_parser, "use_case_skeleton")
        self.assertEqual(s.output_paths_template, ["docs/use-cases/{key}-detail.md"])

    def test_step_3_3_is_join(self):
        # Sub-10: Step 3.3 はカタログ統合 (join)
        wf = get_workflow("ard")
        s = wf.get_step("3.3")
        self.assertIsNotNone(s)
        self.assertEqual(s.depends_on, ["3.2"])
        self.assertEqual(s.output_paths, ["docs/catalog/use-case-catalog.md"])
        self.assertIsNone(s.fanout_parser)

    def test_root_steps_are_1_and_2(self):
        # Sub-10: ルートは Step 1（事業候補列挙）と Step 2（対象業務分析）
        roots = get_root_steps("ard")
        ids = sorted(s.id for s in roots)
        self.assertEqual(ids, ["1", "2"])

    def test_max_parallel_explicit(self):
        # Sub-10 (ADR-0003): ARD は max_parallel=15 を明示する
        wf = get_workflow("ard")
        self.assertEqual(wf.max_parallel, 15)

    def test_next_steps_after_completing_1_2(self):
        """1.2 完了 → 2 が skipped 扱いなら Step 3.1 が起動可能になること（事業未定経路）。"""
        nexts = get_next_steps(
            "ard",
            completed_step_ids=["1", "1.1", "1.2"],
            skipped_step_ids=["2"],
        )
        ids = [s.id for s in nexts]
        self.assertIn("3.1", ids)

    def test_next_steps_after_completing_2(self):
        """2 完了 → 1/1.1/1.2 が skip 扱いなら Step 3.1 が起動可能になること（target_business 指定経路）。"""
        nexts = get_next_steps(
            "ard",
            completed_step_ids=["2"],
            skipped_step_ids=["1", "1.1", "1.2"],
        )
        ids = [s.id for s in nexts]
        self.assertIn("3.1", ids)


class TestARDWizardOrder(unittest.TestCase):
    def test_ard_is_first_in_list_workflows(self):
        wfs = list_workflows()
        self.assertGreater(len(wfs), 0)
        self.assertEqual(wfs[0].id, "ard",
                         "ARD must be the first workflow so that wizard shows it as #1")

    def test_existing_workflows_still_present(self):
        ids = {wf.id for wf in list_workflows()}
        for expected in ("aas", "aad-web", "asdw-web", "abd", "abdv",
                         "aag", "aagd", "akm", "aqod", "adoc"):
            self.assertIn(expected, ids)


class TestARDDisplayNames(unittest.TestCase):
    def test_display_name_registered(self):
        self.assertEqual(_WORKFLOW_DISPLAY_NAMES["ard"], "Auto Requirement Definition")

    def test_prefix_registered(self):
        self.assertEqual(_WORKFLOW_PREFIX["ard"], "ARD")


class TestBusinessCandidateParser(unittest.TestCase):
    """Sub-9 (D-2 / ADR-0003): business_candidate パーサのユニットテスト。"""

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path
        self._tmpdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _write(self, content: str) -> None:
        path = self.repo_root / "docs" / "company-business-recommendation.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_extracts_biz_ids_from_table(self) -> None:
        from hve.catalog_parsers import parse_business_candidate
        self._write(
            "# 事業候補一覧\n\n"
            "| ID | 名称 |\n"
            "|----|------|\n"
            "| BIZ-01 | ロイヤルティ事業 |\n"
            "| BIZ-02 | EC 事業 |\n"
        )
        assert parse_business_candidate(self.repo_root) == ["BIZ-01", "BIZ-02"]

    def test_extracts_biz_ids_from_headings(self) -> None:
        from hve.catalog_parsers import parse_business_candidate
        self._write(
            "# 事業候補\n\n"
            "## BIZ-03 — 新規 SaaS 事業\n\n"
            "詳細...\n\n"
            "## BIZ-04 — 物流事業\n"
        )
        assert parse_business_candidate(self.repo_root) == ["BIZ-03", "BIZ-04"]

    def test_returns_empty_when_file_missing(self) -> None:
        from hve.catalog_parsers import parse_business_candidate
        assert parse_business_candidate(self.repo_root) == []


class TestUseCaseSkeletonParser(unittest.TestCase):
    """Sub-9 (D-2 / ADR-0003): use_case_skeleton パーサのユニットテスト。"""

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path
        self._tmpdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _write(self, content: str) -> None:
        path = self.repo_root / "docs" / "catalog" / "use-case-skeleton.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_extracts_uc_ids_from_table(self) -> None:
        from hve.catalog_parsers import parse_use_case_skeleton
        self._write(
            "| ID | 名称 |\n|----|------|\n"
            "| UC-01 | サインアップ |\n"
            "| UC-02 | 会員登録 |\n"
        )
        assert parse_use_case_skeleton(self.repo_root) == ["UC-01", "UC-02"]

    def test_extracts_uc_ids_from_headings_with_suffix(self) -> None:
        from hve.catalog_parsers import parse_use_case_skeleton
        self._write(
            "## UC-Signup — サインアップ\n\n"
            "詳細...\n\n"
            "## UC-Member-Register — 会員登録\n"
        )
        assert parse_use_case_skeleton(self.repo_root) == ["UC-Signup", "UC-Member-Register"]

    def test_returns_empty_when_file_missing(self) -> None:
        from hve.catalog_parsers import parse_use_case_skeleton
        assert parse_use_case_skeleton(self.repo_root) == []


class TestNewParsersRegistered(unittest.TestCase):
    """Sub-9: 新パーサが KNOWN_PARSERS に登録され parse_catalog 経由で呼べること。"""

    def test_business_candidate_registered(self) -> None:
        from hve.catalog_parsers import KNOWN_PARSERS, parse_catalog
        from pathlib import Path
        assert "business_candidate" in KNOWN_PARSERS
        # ファイル不在時は空リストが返ること（例外を投げない）
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            assert parse_catalog("business_candidate", Path(td)) == []

    def test_use_case_skeleton_registered(self) -> None:
        from hve.catalog_parsers import KNOWN_PARSERS, parse_catalog
        from pathlib import Path
        assert "use_case_skeleton" in KNOWN_PARSERS
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            assert parse_catalog("use_case_skeleton", Path(td)) == []


if __name__ == "__main__":
    unittest.main()
