"""test_gui_pages.py — MainWindow / OptionsPage / WorkflowSelectPage の遷移と引数生成テスト。

`QT_QPA_PLATFORM=offscreen` を必要とする GUI テスト。
PySide6 未インストール時は全テスト skip。
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _setup_offscreen() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _GuiTestBase(unittest.TestCase):
    """QApplication 初期化を行う共通基底。"""

    _qapp = None

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import PySide6  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("PySide6 not installed")
        _setup_offscreen()
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is None:
            cls._qapp = QApplication([])
        else:
            cls._qapp = QApplication.instance()


class TestHeaderBar(_GuiTestBase):
    def test_initial_step_is_zero(self) -> None:
        from hve.gui.header_bar import HeaderBar, STEP_LABELS

        bar = HeaderBar()
        self.assertEqual(bar.current_step(), 0)
        self.assertEqual(bar.step_count(), len(STEP_LABELS))

    def test_set_current_step(self) -> None:
        from hve.gui.header_bar import HeaderBar

        bar = HeaderBar()
        bar.set_current_step(2)
        self.assertEqual(bar.current_step(), 2)

    def test_step_out_of_range_clamped(self) -> None:
        from hve.gui.header_bar import HeaderBar

        bar = HeaderBar()
        bar.set_current_step(99)
        self.assertEqual(bar.current_step(), bar.step_count() - 1)
        bar.set_current_step(-5)
        self.assertEqual(bar.current_step(), 0)


class TestWorkflowSelectPage(_GuiTestBase):
    def test_initial_selection_none(self) -> None:
        from hve.gui.page_workflow_select import WorkflowSelectPage

        page = WorkflowSelectPage()
        self.assertIsNone(page.selected_workflow_id())

    def test_emits_signal_on_selection(self) -> None:
        from hve.gui.page_workflow_select import WorkflowSelectPage

        page = WorkflowSelectPage()
        received: list = []
        page.selection_changed.connect(lambda wf_id: received.append(wf_id))

        # 最初のラジオを選択する
        btns = page._group.buttons()
        if not btns:
            self.skipTest("No workflow buttons found")
        btns[0].setChecked(True)
        self.assertIsNotNone(page.selected_workflow_id())
        self.assertEqual(len(received), 1)

    def test_multiple_selection_supported(self) -> None:
        from hve.gui.page_workflow_select import WorkflowSelectPage

        page = WorkflowSelectPage()
        btns = page._group.buttons()
        if len(btns) < 2:
            self.skipTest("Need at least 2 workflow buttons")

        btns[0].setChecked(True)
        btns[1].setChecked(True)
        selected_ids = page.selected_workflow_ids()
        self.assertEqual(len(selected_ids), 2)


class TestOptionsPage(_GuiTestBase):
    def test_set_workflow_updates_title(self) -> None:
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        page.set_workflow("akm", "Knowledge Management")
        self.assertIn("akm", page._title_label.text())
        self.assertIn("Knowledge Management", page._title_label.text())

    def test_build_args_workflow_propagated(self) -> None:
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        page.set_workflow("akm", "Knowledge Management")
        args = page.build_args()
        self.assertEqual(args.workflow, "akm")

    def test_ard_specific_categories_visible(self) -> None:
        """ARD 選択時に C14 が有効化される。"""
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        page.set_workflow("ard", "Auto Requirement Definition")
        self.assertFalse(page._category_groups["C14"].isHidden())

    def test_akm_specific_categories_only(self) -> None:
        """AKM 選択時は C11 のみ有効、C14 は無効。"""
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        page.set_workflow("akm", "Knowledge Management")
        self.assertFalse(page._category_groups["C11"].isHidden())
        self.assertTrue(page._category_groups["C14"].isHidden())

    def test_ard_attachment_pane_created(self) -> None:
        """ARD 選択時に AttachmentPane が動的追加される。"""
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        page.set_workflow("ard", "Auto Requirement Definition")
        self.assertIsNotNone(page.attachment_pane())


class TestMainWindow(_GuiTestBase):
    def test_initial_step_is_workflow(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        self.assertEqual(w._stack.currentIndex(), 0)
        # 戻るボタンは無効
        self.assertFalse(w._btn_back.isEnabled())
        # 次へボタンは未選択時に無効
        self.assertFalse(w._btn_next.isEnabled())

    def test_navigation_step1_to_step2(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        # Step 1 でワークフロー選択
        btns = w._page_workflow._group.buttons()
        if not btns:
            self.skipTest("No workflow buttons")
        btns[0].setChecked(True)
        # 次へ
        self.assertTrue(w._btn_next.isEnabled())
        w._btn_next.click()
        self.assertEqual(w._stack.currentIndex(), 1)
        # ヘッダー進捗も更新
        self.assertEqual(w._header.current_step(), 1)

    def test_navigation_step2_back_to_step1(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        btns = w._page_workflow._group.buttons()
        if not btns:
            self.skipTest("No workflow buttons")
        btns[0].setChecked(True)
        w._btn_next.click()
        self.assertEqual(w._stack.currentIndex(), 1)
        # 戻る
        self.assertTrue(w._btn_back.isEnabled())
        w._btn_back.click()
        self.assertEqual(w._stack.currentIndex(), 0)
        self.assertEqual(w._header.current_step(), 0)

    def test_window_title_includes_session_index(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=42)
        self.assertIn("Session #42", w.windowTitle())
        # 名称が「HVE GUI Orchestrator」になっている
        self.assertIn("HVE GUI Orchestrator", w.windowTitle())

    def test_settings_button_exists(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        self.assertTrue(hasattr(w, "_btn_settings"))
        self.assertEqual(w._btn_settings.toolTip(), "設定")

    def test_settings_button_opens_popup(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        with patch("hve.gui.main_window.SettingsWindow") as win_cls:
            win = win_cls.return_value
            w._btn_settings.click()
            win_cls.assert_called_once()
            win.show.assert_called_once()


class TestSettingsWindow(_GuiTestBase):
    def test_window_has_tree_and_stack(self) -> None:
        from hve.gui.settings_window import SettingsWindow

        with tempfile.TemporaryDirectory() as d:
            w = SettingsWindow(repo_root=Path(d))
            self.assertGreater(w._tree.topLevelItemCount(), 0)
            self.assertGreater(w._stack.count(), 0)

    def test_dependency_sort_stable_without_cycle(self) -> None:
        from hve.gui.main_window import _sort_workflows_by_dependencies

        selected = ["asdw-web", "aad-web", "aas"]
        ordered = _sort_workflows_by_dependencies(selected)
        self.assertLess(ordered.index("aas"), ordered.index("aad-web"))
        self.assertLess(ordered.index("aad-web"), ordered.index("asdw-web"))

    def test_collect_unselected_dependencies(self) -> None:
        from hve.gui.main_window import _collect_unselected_dependencies

        missing = _collect_unselected_dependencies(["asdw-web"])
        self.assertIn("asdw-web", missing)
        dep_ids = {d.workflow_id for d in missing["asdw-web"]}
        self.assertIn("aad-web", dep_ids)

    def test_format_missing_dependencies_message(self) -> None:
        from hve.gui.main_window import (
            _collect_unselected_dependencies,
            _format_missing_dependencies_message,
        )

        missing = _collect_unselected_dependencies(["asdw-web"])
        msg = _format_missing_dependencies_message(missing)
        self.assertIn("asdw-web", msg)
        self.assertIn("aad-web", msg)
        self.assertIn("required_artifacts", msg)
        self.assertIn("docs/screen/*.md", msg)

    def test_on_process_finished_non_zero_updates_status(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        w._on_process_finished(1)
        self.assertIn("一部失敗あり", w._status_label.text())

    def test_on_process_finished_success_marks_header_completed(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        w._on_process_finished(0)
        self.assertTrue(w._header.is_all_completed())
        self.assertFalse(w._btn_stop.isVisible())

    def test_on_process_finished_failure_marks_header_completed(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        w._on_process_finished(1)
        self.assertTrue(w._header.is_all_completed())
        self.assertFalse(w._btn_stop.isVisible())

    def test_on_process_finished_stopped_skips_completion(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        # ユーザー停止をシミュレート
        w._page_workbench._stop_requested = True
        w._on_process_finished(0)
        self.assertFalse(w._header.is_all_completed())
        self.assertIn("停止", w._status_label.text())

    def test_on_stop_all_clicked_disables_stop_button_immediately(self) -> None:
        """[停止] クリック直後に [停止] ボタンが即無効化されることを検証する。

        多重押下防止のため、process_finished を待たずに setEnabled(False) する。
        """
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        # Step 2 へ遷移し、実行中状態をシミュレート
        btns = w._page_workflow._group.buttons()
        if not btns:
            self.skipTest("No workflow buttons")
        btns[0].setChecked(True)
        w._btn_next.click()
        w._page_workbench._is_running = True
        w._refresh_navigation()
        # 前提: 実行中は [停止] 有効・[戻る] 無効
        self.assertTrue(w._btn_stop.isEnabled())
        self.assertFalse(w._btn_back.isEnabled())

        # stop_orchestrator が実プロセスを触らないようにパッチして発火させる
        with patch.object(w._page_workbench, "stop_orchestrator"):
            w._on_stop_all_clicked()

        # クリック直後: [停止] は即無効化される（[戻る] は process_finished 待ち）
        self.assertFalse(w._btn_stop.isEnabled())


class TestHeaderBarCompleted(_GuiTestBase):
    def test_mark_completed_sets_flag(self) -> None:
        from hve.gui.header_bar import HeaderBar

        bar = HeaderBar()
        bar.set_current_step(2)
        self.assertFalse(bar.is_all_completed())
        bar.mark_completed(True)
        self.assertTrue(bar.is_all_completed())

    def test_set_current_step_resets_completed(self) -> None:
        from hve.gui.header_bar import HeaderBar

        bar = HeaderBar()
        bar.set_current_step(2)
        bar.mark_completed(True)
        # 同 index 再設定でもリセットされる
        bar.set_current_step(2)
        self.assertFalse(bar.is_all_completed())
        # 別 index でもリセットされる
        bar.mark_completed(True)
        bar.set_current_step(0)
        self.assertFalse(bar.is_all_completed())


class TestOptionsPageMultiWorkflow(_GuiTestBase):
    def test_set_workflows_and_build_args_list(self) -> None:
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        page.set_workflows(
            ["akm", "aqod"],
            {"akm": "Knowledge Management", "aqod": "Original Docs Review"},
        )
        args_list = page.build_args_list()
        self.assertEqual([a.workflow for a in args_list], ["akm", "aqod"])


class TestTriStateCombo(_GuiTestBase):
    def test_default_is_inherit(self) -> None:
        from hve.gui.page_options import TriStateCombo

        c = TriStateCombo()
        self.assertIsNone(c.get_tristate())

    def test_set_on(self) -> None:
        from hve.gui.page_options import TriStateCombo

        c = TriStateCombo()
        c.set_tristate(True)
        self.assertTrue(c.get_tristate())

    def test_set_off(self) -> None:
        from hve.gui.page_options import TriStateCombo

        c = TriStateCombo()
        c.set_tristate(False)
        self.assertFalse(c.get_tristate())


class TestOptionsPageDefaults(_GuiTestBase):
    """Step 2 リファクタ後の規定値・選択肢回帰テスト。"""

    def test_model_dropdown_choices_and_default_auto(self) -> None:
        """C1: --model ドロップダウンに Auto + hve.config.MODEL_CHOICES が並び、デフォルトは Auto。"""
        from hve.gui.page_options import MODEL_CHOICES, OptionsPage
        from hve.config import MODEL_CHOICES as CONFIG_MODEL_CHOICES

        page = OptionsPage()
        # config.MODEL_CHOICES が SoT。GUI 側は先頭に "Auto" を付加した一覧。
        self.assertEqual(MODEL_CHOICES, ["Auto", *CONFIG_MODEL_CHOICES])
        combo = page.c1.model
        self.assertEqual(combo.count(), len(MODEL_CHOICES))
        self.assertEqual(combo.currentData(), "Auto")
        self.assertFalse(combo.isEditable())

    def test_review_and_qa_model_default_inherit(self) -> None:
        """C1: --review-model / --qa-model のデフォルトは「継承」(None)。"""
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        self.assertIsNone(page.c1.review_model.currentData())
        self.assertIsNone(page.c1.qa_model.currentData())
        self.assertFalse(page.c1.review_model.isEditable())
        self.assertFalse(page.c1.qa_model.isEditable())

    def test_c11_sources_default_qa_and_original_docs(self) -> None:
        """C11: --sources のチェックボックス群、デフォルトは qa + original-docs。"""
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        self.assertTrue(page.c11.sources_qa.isChecked())
        self.assertTrue(page.c11.sources_original_docs.isChecked())
        self.assertFalse(page.c11.sources_workiq.isChecked())

    def test_c11_sources_to_args_csv_join(self) -> None:
        """C11: --sources は to_args() で CSV 結合される。"""
        from hve.gui.orchestrate_args import OrchestrateArgs
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        page.set_workflow("akm", "Knowledge Management")

        # デフォルト: qa + original-docs
        args = OrchestrateArgs(workflow="akm")
        page.c11.to_args(args)
        self.assertEqual(args.sources, "qa,original-docs")

        # workiq のみ
        page.c11.sources_qa.setChecked(False)
        page.c11.sources_original_docs.setChecked(False)
        page.c11.sources_workiq.setChecked(True)
        args2 = OrchestrateArgs(workflow="akm")
        page.c11.to_args(args2)
        self.assertEqual(args2.sources, "workiq")

        # 全部 OFF → None
        page.c11.sources_workiq.setChecked(False)
        args3 = OrchestrateArgs(workflow="akm")
        page.c11.to_args(args3)
        self.assertIsNone(args3.sources)

    def test_c12_depth_default_standard(self) -> None:
        """C12: --depth のデフォルトは standard。"""
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        self.assertEqual(page.c12.depth.currentData(), "standard")

    def test_c13_doc_purpose_default_all(self) -> None:
        """C13: --doc-purpose のデフォルトは all。"""
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        self.assertEqual(page.c13.doc_purpose.currentData(), "all")

    def test_labels_do_not_expose_cli_flag_names(self) -> None:
        """主要ウィジェットのラベルテキストに `--xxx` パラメーター名が含まれないこと。

        各カテゴリの QCheckBox / QLabel のテキストに CLI フラグ名が露出していないかを確認する。
        """
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        # チェックボックスのテキストに -- が含まれないこと
        checkboxes = page.findChildren(__import__("PySide6.QtWidgets", fromlist=["QCheckBox"]).QCheckBox)
        offenders = [cb.text() for cb in checkboxes if "--" in cb.text()]
        self.assertEqual(
            offenders, [], f"CLI フラグ名が含まれる QCheckBox があります: {offenders}"
        )

    def test_c1_model_round_trip_to_args(self) -> None:
        """C1: モデル選択肢の選択値が OrchestrateArgs に正しく渡る。"""
        from hve.gui.orchestrate_args import OrchestrateArgs
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        # Auto を選択（デフォルト）
        args = OrchestrateArgs(workflow="akm")
        page.c1.to_args(args)
        self.assertEqual(args.model, "Auto")

        # claude-opus-4.7 を選択
        idx = page.c1.model.findData("claude-opus-4.7")
        self.assertGreaterEqual(idx, 0)
        page.c1.model.setCurrentIndex(idx)
        args2 = OrchestrateArgs(workflow="akm")
        page.c1.to_args(args2)
        self.assertEqual(args2.model, "claude-opus-4.7")


class TestLabeledField(_GuiTestBase):
    """共通ウィジェット _LabeledField の挙動を確認。"""

    def test_renders_title_and_description(self) -> None:
        from PySide6.QtWidgets import QCheckBox, QLabel

        from hve.gui.page_options import _LabeledField

        cb = QCheckBox("有効化")
        field = _LabeledField(
            title="QA 自動投入",
            description="QA 質問票を自動的に投入します（既定: 無効）。",
            input_widget=cb,
        )
        labels = field.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        self.assertIn("QA 自動投入", texts)
        self.assertIn("QA 質問票を自動的に投入します（既定: 無効）。", texts)
        self.assertIs(field.input_widget(), cb)

    def test_required_mark(self) -> None:
        from PySide6.QtWidgets import QLineEdit

        from hve.gui.page_options import _LabeledField

        edit = QLineEdit()
        field = _LabeledField(
            title="必須項目テスト",
            description="必須項目の説明",
            input_widget=edit,
            required=True,
        )
        all_text = " ".join(
            lbl.text()
            for lbl in field.findChildren(
                __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel
            )
        )
        self.assertIn("*必須", all_text)


if __name__ == "__main__":
    unittest.main()