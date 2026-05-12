"""test_akm_workiq_ingest.py — Sub-F-3/F-4/F-5: AKM Work IQ 取り込みフェーズの計画組込・ドライ実行・Dxx フィルタテスト

Sub-E-1, E-2 で導入された ``_run_akm_workiq_ingest`` と ``run_workflow`` のフェーズ計画への
組込挙動を検証する。実 Work IQ 呼び出しは行わず、計画ロジックと early-skip 経路を中心に検証する。
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Sub-F-3: フェーズ計画へのフラグ別組込
# ---------------------------------------------------------------------------


class TestAkmWorkiqIngestPhasePlanning(unittest.TestCase):
    """``_phases`` 構築ロジックを再現し、ingest フラグの有無で挿入順序を検証する。"""

    @staticmethod
    def _build_phases(
        *,
        workflow_id: str,
        ingest_enabled: bool,
        review_enabled: bool,
        dry_run: bool,
    ) -> list:
        """``run_workflow`` 内のフェーズ計画ロジックを再現する。"""
        from hve.config import SDKConfig

        cfg = SDKConfig(
            workiq_akm_review_enabled=review_enabled,
            workiq_akm_ingest_enabled=ingest_enabled,
        )
        phases = ["ワークフロー定義取得", "パラメータ収集", "ステップフィルタリング"]
        phases.append("実行計画 → DAG 実行")
        # AKM Work IQ 取り込み（DAG 前）
        if workflow_id == "akm" and cfg.is_workiq_akm_ingest_enabled() and not dry_run:
            idx = next(
                (i for i, ph in enumerate(phases) if "DAG 実行" in ph), len(phases) - 1
            )
            phases.insert(idx, "AKM Work IQ 取り込み")
        if workflow_id == "akm" and cfg.is_workiq_akm_review_enabled() and not dry_run:
            phases.append("AKM Work IQ 検証")
        phases.append("サマリー")
        return phases

    def test_ingest_on_inserts_phase_before_dag(self) -> None:
        """ingest=ON のとき「AKM Work IQ 取り込み」が DAG 実行の **前** に挿入される。"""
        phases = self._build_phases(
            workflow_id="akm", ingest_enabled=True, review_enabled=False, dry_run=False
        )
        self.assertIn("AKM Work IQ 取り込み", phases)
        ingest_idx = phases.index("AKM Work IQ 取り込み")
        dag_idx = phases.index("実行計画 → DAG 実行")
        self.assertLess(ingest_idx, dag_idx)

    def test_ingest_off_excludes_phase(self) -> None:
        """ingest=OFF のときフェーズに含まれない。"""
        phases = self._build_phases(
            workflow_id="akm", ingest_enabled=False, review_enabled=False, dry_run=False
        )
        self.assertNotIn("AKM Work IQ 取り込み", phases)

    def test_ingest_and_review_both_on_order(self) -> None:
        """ingest + review 両 ON のとき、順序は ingest → DAG → review。"""
        phases = self._build_phases(
            workflow_id="akm", ingest_enabled=True, review_enabled=True, dry_run=False
        )
        self.assertIn("AKM Work IQ 取り込み", phases)
        self.assertIn("AKM Work IQ 検証", phases)
        ingest_idx = phases.index("AKM Work IQ 取り込み")
        dag_idx = phases.index("実行計画 → DAG 実行")
        verify_idx = phases.index("AKM Work IQ 検証")
        self.assertLess(ingest_idx, dag_idx)
        self.assertLess(dag_idx, verify_idx)

    def test_ingest_skipped_in_dry_run(self) -> None:
        """dry_run=True のときは ingest フェーズが含まれない。"""
        phases = self._build_phases(
            workflow_id="akm", ingest_enabled=True, review_enabled=False, dry_run=True
        )
        self.assertNotIn("AKM Work IQ 取り込み", phases)

    def test_ingest_only_for_akm(self) -> None:
        """非 AKM ワークフローでは ingest=True でもフェーズに含まれない。"""
        phases = self._build_phases(
            workflow_id="aad-web", ingest_enabled=True, review_enabled=False, dry_run=False
        )
        self.assertNotIn("AKM Work IQ 取り込み", phases)


# ---------------------------------------------------------------------------
# Sub-F-4: _run_akm_workiq_ingest のドライ実行（Work IQ 未利用環境では skip）
# ---------------------------------------------------------------------------


class TestRunAkmWorkiqIngestEarlySkip(unittest.TestCase):
    """``_run_akm_workiq_ingest`` の早期 skip 経路を検証する。

    実 Work IQ 呼び出しは行わず、``is_workiq_available=False`` 時に warning 経由で
    早期 return することを確認する（HVE Cloud Agent 対象外・ローカル CLI 専用機能）。
    """

    def test_skip_when_workiq_unavailable(self) -> None:
        """``is_workiq_available()=False`` のとき warning 出力後に早期 return する。"""
        from hve.config import SDKConfig

        # orchestrator は hve パッケージ経由でロードされる前提（test_akm_workiq_phase と同様）。
        import hve.orchestrator as orch  # type: ignore[import-untyped]

        cfg = SDKConfig(workiq_akm_ingest_enabled=True)
        console = mock.MagicMock()
        report_paths: set = set()

        # `hve.workiq.is_workiq_available` を False に固定し、orchestrator 内の
        # `from .workiq import is_workiq_available` がパッチ後の関数を取得することを期待する。
        with mock.patch("hve.workiq.is_workiq_available", return_value=False):
            asyncio.run(
                orch._run_akm_workiq_ingest(
                    config=cfg, console=console, workiq_report_paths=report_paths
                )
            )
        # warning が呼ばれ、メッセージに「Work IQ」が含まれること。
        self.assertTrue(console.warning.called)
        warning_args = " ".join(str(c.args[0]) for c in console.warning.call_args_list)
        self.assertIn("Work IQ", warning_args)
        # Work IQ が利用不可なら report_paths は変化しない。
        self.assertEqual(report_paths, set())


# ---------------------------------------------------------------------------
# Sub-F-5: Dxx フィルタ動作
# ---------------------------------------------------------------------------


class TestWorkiqAkmIngestDxxFilter(unittest.TestCase):
    """``config.workiq_akm_ingest_dxx`` の正規化と適用範囲を検証する。"""

    def test_parse_workiq_akm_ingest_dxx_empty(self) -> None:
        """空文字 → 空リスト（= 全 Dxx を対象）。"""
        from hve.config import _parse_workiq_akm_ingest_dxx

        self.assertEqual(_parse_workiq_akm_ingest_dxx(""), [])
        self.assertEqual(_parse_workiq_akm_ingest_dxx("   "), [])

    def test_parse_workiq_akm_ingest_dxx_basic(self) -> None:
        """``D01,D04`` → ``["D01","D04"]``。"""
        from hve.config import _parse_workiq_akm_ingest_dxx

        self.assertEqual(_parse_workiq_akm_ingest_dxx("D01,D04"), ["D01", "D04"])

    def test_parse_workiq_akm_ingest_dxx_case_insensitive(self) -> None:
        """大文字小文字混在は正規化される（``D`` は大文字、ゼロパディング付与）。"""
        from hve.config import _parse_workiq_akm_ingest_dxx

        self.assertEqual(_parse_workiq_akm_ingest_dxx("d1,D02"), ["D01", "D02"])

    def test_parse_workiq_akm_ingest_dxx_invalid_skipped(self) -> None:
        """不正パターン（``foo``, ``X01`` 等）は除外される。"""
        from hve.config import _parse_workiq_akm_ingest_dxx

        self.assertEqual(_parse_workiq_akm_ingest_dxx("D01,foo,X01,D04"), ["D01", "D04"])

    def test_parse_workiq_akm_ingest_dxx_whitespace(self) -> None:
        """空白区切りも受理する。"""
        from hve.config import _parse_workiq_akm_ingest_dxx

        self.assertEqual(_parse_workiq_akm_ingest_dxx("D01 D04"), ["D01", "D04"])

    def test_parse_workiq_akm_ingest_dxx_dedup(self) -> None:
        """重複は除去される。"""
        from hve.config import _parse_workiq_akm_ingest_dxx

        self.assertEqual(_parse_workiq_akm_ingest_dxx("D01,D01,D04"), ["D01", "D04"])

    def test_config_workiq_akm_ingest_dxx_default_empty(self) -> None:
        """SDKConfig の既定値は空リスト（= 全件）。"""
        from hve.config import SDKConfig

        cfg = SDKConfig()
        self.assertEqual(cfg.workiq_akm_ingest_dxx, [])

    def test_config_workiq_akm_ingest_enabled_default_false(self) -> None:
        """SDKConfig.workiq_akm_ingest_enabled の既定値は False。"""
        from hve.config import SDKConfig

        cfg = SDKConfig()
        self.assertFalse(cfg.is_workiq_akm_ingest_enabled())

    def test_is_workiq_akm_ingest_enabled_when_true(self) -> None:
        """明示 True で is_workiq_akm_ingest_enabled() が True を返す。"""
        from hve.config import SDKConfig

        cfg = SDKConfig(workiq_akm_ingest_enabled=True)
        self.assertTrue(cfg.is_workiq_akm_ingest_enabled())


if __name__ == "__main__":
    unittest.main()
