"""MainWindow のステップ選択 → OptionsPage CI/CD トグル連携テスト。

T3 で追加した配線:
  - `steps_selection_changed` → `_on_steps_selection_changed` → `OptionsPage.set_selected_steps`
  - `_on_workflow_selection_changed` でも set_workflows 後に set_selected_steps を呼ぶ

を検証する。MagicMock で fake self を用い、ハンドラの入出力契約を直接単体テストする
(`test_main_window_step_selection_plan.py` と同方針。MainWindow 全体構築を避け
Context Window を小さく保つ)。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.main_window import MainWindow  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


def test_on_steps_selection_changed_forwards_all_enabled_steps() -> None:
    # ステップ選択変更 → all_enabled_steps() の結果を set_selected_steps へ渡す（ステップのチェック変更で即時反映）。
    _ensure_app()
    fake = MagicMock()
    fake._page_workflow.all_enabled_steps.return_value = {"asdw-web": ["3.4", "4.3"]}

    MainWindow._on_steps_selection_changed(fake, "asdw-web", ["3.4", "4.3"])

    fake._page_options.set_selected_steps.assert_called_once_with(
        {"asdw-web": ["3.4", "4.3"]}
    )


def test_on_workflow_selection_changed_also_sets_selected_steps() -> None:
    # ワークフロー選択変更 → set_workflows に加え set_selected_steps も呼ぶ
    # （ワークフロー切替直後の CI/CD トグル表示条件評価のため）。
    _ensure_app()
    fake = MagicMock()
    fake._page_workflow.selected_workflow_ids.return_value = ["asdw-web"]
    fake._page_workflow.selected_workflow_names.return_value = ["ASDW Web"]
    fake._page_workflow.all_enabled_steps.return_value = {"asdw-web": ["3.4"]}
    # attachment_pane を None にして後続の repo_root 伝播分岐をスキップさせる。
    fake._page_options.attachment_pane.return_value = None

    MainWindow._on_workflow_selection_changed(fake, ["asdw-web"])

    fake._page_options.set_workflows.assert_called_once_with(
        ["asdw-web"], {"asdw-web": "ASDW Web"}
    )
    fake._page_options.set_selected_steps.assert_called_once_with({"asdw-web": ["3.4"]})


def test_steps_selection_signal_wired_to_options(tmp_path) -> None:
    # T3 で追加した signal 接続（steps_selection_changed → _on_steps_selection_changed）が
    # 実際に機能し set_selected_steps が呼ばれることを検証する（接続忘れ / スロット名タイポの回帰防止）。
    _ensure_app()
    win = MainWindow(repo_root=tmp_path)
    try:
        win._page_options.set_selected_steps = MagicMock()
        win._page_workflow.steps_selection_changed.emit("asdw-web", ["3.4"])
        win._page_options.set_selected_steps.assert_called_once()
    finally:
        win.deleteLater()


if __name__ == "__main__":
    import unittest

    unittest.main()
