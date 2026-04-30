"""test_runner_qa_phase.py — QA フェーズ判定ロジック（run_step 内の判定ロジック相当）の単体テスト

AKM/AQOD/通常ワークフローに対する _run_pre_qa / _run_post_qa の組み合わせを網羅的に検証する。
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig


def _compute_qa_flags(
    *,
    auto_qa: bool,
    qa_phase: str,
    aqod_post_qa_enabled: bool,
    workflow_id: str | None,
    custom_agent: str | None = None,
    prompt: str = "テストプロンプト",
) -> tuple[bool, bool]:
    """runner.run_step() の QA フェーズ判定ロジックを抽出した参照実装。

    Returns:
        (run_pre_qa, run_post_qa)
    """
    _is_aqod_workflow = (
        workflow_id == "aqod"
        or (
            custom_agent == "QA-DocConsistency"
            and "original-docs-questionnaire" in (prompt or "")
        )
    )
    _is_akm_workflow = workflow_id == "akm"

    _skip_pre_qa = _is_aqod_workflow

    run_pre_qa = (
        auto_qa
        and qa_phase in ("pre", "both")
        and not _skip_pre_qa
    )

    if _is_akm_workflow:
        run_post_qa = False
    elif _is_aqod_workflow:
        run_post_qa = auto_qa and aqod_post_qa_enabled
    else:
        run_post_qa = auto_qa and qa_phase in ("post", "both")

    return run_pre_qa, run_post_qa


class TestQaPhaseAkm(unittest.TestCase):
    """AKM ワークフローの QA フェーズ判定テスト。"""

    def test_akm_pre_qa_phase_runs_pre_not_post(self) -> None:
        """auto_qa=True, qa_phase='pre' → pre=True, post=False"""
        pre, post = _compute_qa_flags(
            auto_qa=True, qa_phase="pre", aqod_post_qa_enabled=False, workflow_id="akm"
        )
        self.assertTrue(pre, "AKM + pre → 事前 QA が実行されるべき")
        self.assertFalse(post, "AKM では事後 QA は常に False")

    def test_akm_both_qa_phase_runs_pre_not_post(self) -> None:
        """auto_qa=True, qa_phase='both' → pre=True, post=False（事後は常に廃止）"""
        pre, post = _compute_qa_flags(
            auto_qa=True, qa_phase="both", aqod_post_qa_enabled=False, workflow_id="akm"
        )
        self.assertTrue(pre)
        self.assertFalse(post, "AKM では事後 QA は常に False")

    def test_akm_post_qa_phase_runs_neither(self) -> None:
        """auto_qa=True, qa_phase='post' → pre=False, post=False"""
        pre, post = _compute_qa_flags(
            auto_qa=True, qa_phase="post", aqod_post_qa_enabled=False, workflow_id="akm"
        )
        self.assertFalse(pre, "AKM + post 指定 → 事前 QA もスキップ（qa_phase='post' のため）")
        self.assertFalse(post, "AKM では事後 QA は常に False")

    def test_akm_auto_qa_false_runs_neither(self) -> None:
        """auto_qa=False → どちらも False"""
        pre, post = _compute_qa_flags(
            auto_qa=False, qa_phase="both", aqod_post_qa_enabled=False, workflow_id="akm"
        )
        self.assertFalse(pre)
        self.assertFalse(post)


class TestQaPhaseAqod(unittest.TestCase):
    """AQOD ワークフローの QA フェーズ判定テスト。"""

    def test_aqod_pre_phase_disabled_by_default(self) -> None:
        """AQOD は事前 QA を常にスキップ。"""
        pre, post = _compute_qa_flags(
            auto_qa=True, qa_phase="pre", aqod_post_qa_enabled=False, workflow_id="aqod"
        )
        self.assertFalse(pre, "AQOD では事前 QA は常にスキップ")
        self.assertFalse(post, "aqod_post_qa_enabled=False → 事後 QA も実行しない")

    def test_aqod_post_qa_opt_in(self) -> None:
        """aqod_post_qa_enabled=True → 事後 QA が実行される。"""
        pre, post = _compute_qa_flags(
            auto_qa=True, qa_phase="pre", aqod_post_qa_enabled=True, workflow_id="aqod"
        )
        self.assertFalse(pre, "AQOD では事前 QA は常にスキップ")
        self.assertTrue(post, "aqod_post_qa_enabled=True → 事後 QA が実行される")

    def test_aqod_auto_qa_false_ignores_opt_in(self) -> None:
        """auto_qa=False の場合、aqod_post_qa_enabled=True でも事後 QA は実行しない。"""
        pre, post = _compute_qa_flags(
            auto_qa=False, qa_phase="both", aqod_post_qa_enabled=True, workflow_id="aqod"
        )
        self.assertFalse(pre)
        self.assertFalse(post, "auto_qa=False では無効")

    def test_aqod_doc_consistency_with_questionnaire_uses_opt_in(self) -> None:
        """QA-DocConsistency + original-docs-questionnaire も aqod_post_qa_enabled で制御される。"""
        pre, post = _compute_qa_flags(
            auto_qa=True,
            qa_phase="both",
            aqod_post_qa_enabled=True,
            workflow_id=None,
            custom_agent="QA-DocConsistency",
            prompt="モード: original-docs-questionnaire",
        )
        self.assertFalse(pre, "AQOD 相当 → 事前 QA はスキップ")
        self.assertTrue(post, "aqod_post_qa_enabled=True → 事後 QA が実行される")

    def test_aqod_doc_consistency_without_opt_in_no_post_qa(self) -> None:
        """QA-DocConsistency + original-docs-questionnaire で aqod_post_qa_enabled=False → 事後 QA なし。"""
        pre, post = _compute_qa_flags(
            auto_qa=True,
            qa_phase="both",
            aqod_post_qa_enabled=False,
            workflow_id=None,
            custom_agent="QA-DocConsistency",
            prompt="モード: original-docs-questionnaire",
        )
        self.assertFalse(pre)
        self.assertFalse(post)


class TestQaPhaseNormal(unittest.TestCase):
    """通常ワークフロー（AAD 等）の QA フェーズ判定テスト。"""

    def test_normal_pre_phase(self) -> None:
        """qa_phase='pre' → pre=True, post=False"""
        pre, post = _compute_qa_flags(
            auto_qa=True, qa_phase="pre", aqod_post_qa_enabled=False, workflow_id="aad"
        )
        self.assertTrue(pre)
        self.assertFalse(post)

    def test_normal_both_phase(self) -> None:
        """qa_phase='both' → pre=True, post=True"""
        pre, post = _compute_qa_flags(
            auto_qa=True, qa_phase="both", aqod_post_qa_enabled=False, workflow_id="aad"
        )
        self.assertTrue(pre)
        self.assertTrue(post)

    def test_normal_post_phase(self) -> None:
        """qa_phase='post' → pre=False, post=True"""
        pre, post = _compute_qa_flags(
            auto_qa=True, qa_phase="post", aqod_post_qa_enabled=False, workflow_id="aad"
        )
        self.assertFalse(pre)
        self.assertTrue(post)

    def test_normal_workflow_id_none(self) -> None:
        """workflow_id=None（通常）でも同様に動作する。"""
        pre, post = _compute_qa_flags(
            auto_qa=True, qa_phase="both", aqod_post_qa_enabled=False, workflow_id=None
        )
        self.assertTrue(pre)
        self.assertTrue(post)

    def test_normal_auto_qa_false(self) -> None:
        """auto_qa=False → どちらも False。"""
        pre, post = _compute_qa_flags(
            auto_qa=False, qa_phase="both", aqod_post_qa_enabled=False, workflow_id="aad"
        )
        self.assertFalse(pre)
        self.assertFalse(post)


class TestQaPhaseLogicMatchesRunnerSource(unittest.TestCase):
    """_compute_qa_flags() を通じて runner の QA フェーズ判定仕様を確認する。

    Note: _compute_qa_flags() は runner.run_step() 内の判定ロジックを複製した
    参照実装であり、runner.py の実装変更には追従しない。このクラスのテストは
    仕様の記録として機能する（回帰検知には test_aqod_qa_prompt.py の
    TestRunStepAqodPromptSelectionRuntime を参照）。
    """

    def test_akm_post_qa_always_false(self) -> None:
        """AKM では _run_post_qa が常に False になること（qa_phase='both' でも）。"""
        pre, post = _compute_qa_flags(
            auto_qa=True, qa_phase="both", aqod_post_qa_enabled=False, workflow_id="akm"
        )
        self.assertFalse(post, "AKM では事後 QA は qa_phase に関わらず常に False")

    def test_aqod_skip_pre_qa_always(self) -> None:
        """AQOD では _run_pre_qa が常に False になること。"""
        for qa_phase in ("pre", "both", "post"):
            with self.subTest(qa_phase=qa_phase):
                pre, _ = _compute_qa_flags(
                    auto_qa=True, qa_phase=qa_phase, aqod_post_qa_enabled=False, workflow_id="aqod"
                )
                self.assertFalse(pre, f"AQOD では事前 QA は qa_phase='{qa_phase}' でも常に False")

    def test_aqod_post_qa_uses_aqod_post_qa_enabled(self) -> None:
        """AQOD の事後 QA が aqod_post_qa_enabled で制御される。"""
        _, post_disabled = _compute_qa_flags(
            auto_qa=True, qa_phase="both", aqod_post_qa_enabled=False, workflow_id="aqod"
        )
        _, post_enabled = _compute_qa_flags(
            auto_qa=True, qa_phase="both", aqod_post_qa_enabled=True, workflow_id="aqod"
        )
        self.assertFalse(post_disabled)
        self.assertTrue(post_enabled)


if __name__ == "__main__":
    unittest.main()
