"""T10: ``MainWindow._run_step1_unified_precheck`` の追加プロンプト配線テスト。

T9 で導入した修正の回帰防止:
  - OptionsPage の ``additional_prompt`` テキスト欄が precheck に **実際に** 渡る
    （旧実装では `additional_prompts: dict = {}` のまま空 dict が渡っていた）
  - 設定 ``precheck_use_llm_judge`` の値が ``run_step1_precheck(use_llm_judge=...)``
    に中継される
  - 追加プロンプトは選択中の全 workflow_id に同一文字列として複製される（Q8=A）
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.autopilot.precheck_model import AutopilotPrecheckResult  # noqa: E402
from hve.gui.main_window import MainWindow  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


def _make_self(tmp_path: Path, *, prompt_text: str) -> MagicMock:
    """`_run_step1_unified_precheck` 実行に必要な属性のみ持つ軽量 self。"""
    fake = MagicMock()
    fake._repo_root = tmp_path
    fake.tr = lambda s: s
    fake._step1_plan_review_iterations = 0
    fake._page_workflow.all_enabled_steps.return_value = {}
    fake._page_workflow.selected_workflow_ids.return_value = ["aas", "aad-web"]
    fake._page_workflow.autopilot_catalog_path.return_value = ""
    fake._collect_ard_attachment_paths.return_value = []
    # OptionsPage の additional_prompt: QPlainTextEdit を MagicMock で模擬。
    fake._page_options.additional_prompt.toPlainText.return_value = prompt_text
    return fake


def _ok() -> AutopilotPrecheckResult:
    return AutopilotPrecheckResult(items=[])


def _empty_plan_review():
    rv = MagicMock()
    rv.gaps = []
    return rv


def test_additional_prompt_forwarded_to_precheck(tmp_path: Path) -> None:
    """OptionsPage の追加プロンプトが run_step1_precheck に渡される。"""
    _ensure_app()
    fake_self = _make_self(
        tmp_path, prompt_text="docs/x.md は docs/y.md に置き換えます"
    )

    with patch(
        "hve.autopilot.precheck_runner.run_step1_precheck",
        return_value=_ok(),
    ) as mock_precheck, patch(
        "hve.autopilot.plan_review_runner.build_step1_plan_review",
        return_value=_empty_plan_review(),
    ), patch(
        "hve.gui.settings_store.get_option",
        return_value=False,
    ):
        MainWindow._run_step1_unified_precheck(
            fake_self, ["aas", "aad-web"], autopilot_mode=False
        )

    mock_precheck.assert_called_once()
    kwargs = mock_precheck.call_args.kwargs
    ap = kwargs.get("additional_prompts")
    assert isinstance(ap, dict)
    # Q8=A: 同一文字列が選択中の全 workflow_id にマップされる
    assert ap.get("aas") == "docs/x.md は docs/y.md に置き換えます"
    assert ap.get("aad-web") == "docs/x.md は docs/y.md に置き換えます"


def test_empty_additional_prompt_passes_empty_dict(tmp_path: Path) -> None:
    """追加プロンプトが空文字列ならば additional_prompts は空 dict（後方互換）。"""
    _ensure_app()
    fake_self = _make_self(tmp_path, prompt_text="")

    with patch(
        "hve.autopilot.precheck_runner.run_step1_precheck",
        return_value=_ok(),
    ) as mock_precheck, patch(
        "hve.autopilot.plan_review_runner.build_step1_plan_review",
        return_value=_empty_plan_review(),
    ), patch(
        "hve.gui.settings_store.get_option",
        return_value=False,
    ):
        MainWindow._run_step1_unified_precheck(
            fake_self, ["aas"], autopilot_mode=False
        )

    kwargs = mock_precheck.call_args.kwargs
    assert kwargs.get("additional_prompts") == {}


def test_whitespace_only_prompt_treated_as_empty(tmp_path: Path) -> None:
    """空白のみの追加プロンプトは空扱い（strip 後判定）。"""
    _ensure_app()
    fake_self = _make_self(tmp_path, prompt_text="   \n\t ")

    with patch(
        "hve.autopilot.precheck_runner.run_step1_precheck",
        return_value=_ok(),
    ) as mock_precheck, patch(
        "hve.autopilot.plan_review_runner.build_step1_plan_review",
        return_value=_empty_plan_review(),
    ), patch(
        "hve.gui.settings_store.get_option",
        return_value=False,
    ):
        MainWindow._run_step1_unified_precheck(
            fake_self, ["aas"], autopilot_mode=False
        )

    kwargs = mock_precheck.call_args.kwargs
    assert kwargs.get("additional_prompts") == {}


def test_use_llm_judge_setting_forwarded_true(tmp_path: Path) -> None:
    """precheck_use_llm_judge=True が run_step1_precheck に中継される。"""
    _ensure_app()
    fake_self = _make_self(tmp_path, prompt_text="dummy")

    def _get_option(key, *args, **kwargs):  # noqa: ANN001
        if key == "precheck_use_llm_judge":
            return True
        # step1_show_plan_review_always 等は False を返す
        return False

    with patch(
        "hve.autopilot.precheck_runner.run_step1_precheck",
        return_value=_ok(),
    ) as mock_precheck, patch(
        "hve.autopilot.plan_review_runner.build_step1_plan_review",
        return_value=_empty_plan_review(),
    ), patch(
        "hve.gui.settings_store.get_option",
        side_effect=_get_option,
    ):
        MainWindow._run_step1_unified_precheck(
            fake_self, ["aas"], autopilot_mode=False
        )

    kwargs = mock_precheck.call_args.kwargs
    assert kwargs.get("use_llm_judge") is True


def test_use_llm_judge_setting_forwarded_false(tmp_path: Path) -> None:
    """precheck_use_llm_judge=False のとき False が中継される。"""
    _ensure_app()
    fake_self = _make_self(tmp_path, prompt_text="dummy")

    with patch(
        "hve.autopilot.precheck_runner.run_step1_precheck",
        return_value=_ok(),
    ) as mock_precheck, patch(
        "hve.autopilot.plan_review_runner.build_step1_plan_review",
        return_value=_empty_plan_review(),
    ), patch(
        "hve.gui.settings_store.get_option",
        return_value=False,
    ):
        MainWindow._run_step1_unified_precheck(
            fake_self, ["aas"], autopilot_mode=False
        )

    kwargs = mock_precheck.call_args.kwargs
    assert kwargs.get("use_llm_judge") is False
