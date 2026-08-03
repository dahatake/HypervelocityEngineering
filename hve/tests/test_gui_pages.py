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

    def setUp(self) -> None:
        # MainWindow.__init__ は GuiSessionWorkdir.create(repo_root) で
        # work/run/<id>/ を作成する。repo_root 未指定の MainWindow() は
        # Path.cwd()（実リポジトリ）を使うため、テストごとに一時ディレクトリへ
        # 隔離して実リポジトリ直下の work/run/ 汚染を防ぐ。
        #
        # 一時ディレクトリは即時削除しない（pytest の tmp_path と同様に OS の
        # %TEMP% クリーンアップへ委ねる）。MainWindow は gui-logs を
        # QFileSystemWatcher で監視するため、テスト終了時に即時 rmtree すると
        # 監視中ディレクトリ消滅で Qt が stderr 警告を出す。これを避けるため
        # 削除を遅延させる（中身は空の log-0001.log のみで肥大化しない）。
        from hve.gui.session_workdir import GuiSessionWorkdir

        tmp_root = Path(tempfile.mkdtemp(prefix="hve-gui-test-"))

        _orig_create = GuiSessionWorkdir.create

        def _isolated_create(repo_root, *, cleanup_policy="keep"):
            # repo_root を一時ディレクトリへ強制し、実リポジトリ汚染を防ぐ。
            return _orig_create(tmp_root, cleanup_policy=cleanup_policy)

        patcher = patch.object(
            GuiSessionWorkdir, "create", staticmethod(_isolated_create)
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class TestHeaderBar_REMOVED(_GuiTestBase):
    """旧 HeaderBar 削除に伴い、関連クラスは撤去された。

    互換のためクラスシムだけ残し、テスト本体は持たない。
    """

    def test_header_bar_removed(self) -> None:
        # HeaderBar モジュールはアプリから削除済み
        import importlib

        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("hve.gui.header_bar")


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
        # 画面内タイトル (_title_label) は廃止。set_workflow は内部の選択状態を更新する。
        self.assertEqual(page._workflow_id, "akm")
        self.assertEqual(page._workflow_name, "Knowledge Management")

    def test_build_args_workflow_propagated(self) -> None:
        from hve.gui.page_options import OptionsPage

        page = OptionsPage()
        page.set_workflow("akm", "Knowledge Management")
        args = page.build_args()
        self.assertEqual(args.workflow, "akm")

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
        from hve.gui.page_options import OptionsPage
        from hve.gui.page_workbench import WorkbenchPage

        w = MainWindow(session_index=1)
        # Step 1 でワークフロー選択
        btns = w._page_workflow._group.buttons()
        if not btns:
            self.skipTest("No workflow buttons")
        btns[0].setChecked(True)
        # 次へ
        self.assertTrue(w._btn_next.isEnabled())
        # 2 ペイン再設計後、[次へ] は実行起動を兼ねる（_on_run_clicked → Workbench へ遷移）。
        # ナビゲーション（index==_STEP_WORKBENCH）の検証に絞るため、モーダル precheck /
        # 入力検証 / 子プロセス起動を patch で無効化する（いずれも別テストで検証済み）。
        with patch.object(MainWindow, "_run_step1_unified_precheck", return_value=True), \
             patch.object(OptionsPage, "validate", return_value=(True, "")), \
             patch.object(WorkbenchPage, "start_orchestrators"):
            w._btn_next.click()
        self.assertEqual(w._stack.currentIndex(), 1)

    def test_navigation_step2_back_to_step1(self) -> None:
        from hve.gui.main_window import MainWindow
        from hve.gui.page_options import OptionsPage
        from hve.gui.page_workbench import WorkbenchPage

        w = MainWindow(session_index=1)
        btns = w._page_workflow._group.buttons()
        if not btns:
            self.skipTest("No workflow buttons")
        btns[0].setChecked(True)
        with patch.object(MainWindow, "_run_step1_unified_precheck", return_value=True), \
             patch.object(OptionsPage, "validate", return_value=(True, "")), \
             patch.object(WorkbenchPage, "start_orchestrators"):
            w._btn_next.click()
        self.assertEqual(w._stack.currentIndex(), 1)
        # 戻る
        self.assertTrue(w._btn_back.isEnabled())
        w._btn_back.click()
        self.assertEqual(w._stack.currentIndex(), 0)

    def test_window_title_includes_session_index(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=42)
        self.assertIn("Session #42", w.windowTitle())
        # 要件: ウィンドウタイトルは "HVE Workbench" を含む（旧 "HVE GUI Orchestrator" から変更）。
        self.assertIn("HVE Workbench", w.windowTitle())

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
        from mdq import usage_report

        with tempfile.TemporaryDirectory() as d:
            # 利用統計レポート未生成による自動再生成スレッドを抑止する。
            # 起動すると SQLite ハンドルを掘んだまま tmpdir 削除に失敗する。
            report = usage_report.default_output_dir(Path(d)) / "latest.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("# dummy\n", encoding="utf-8")
            w = SettingsWindow(repo_root=Path(d))
            self.assertGreater(w._tree.topLevelItemCount(), 0)
            self.assertGreater(w._stack.count(), 0)

    def test_dependency_sort_stable_without_cycle(self) -> None:
        from hve.gui.main_window import _sort_workflows_by_dependencies

        selected = ["asdw-web", "aad-web", "aas"]
        ordered = _sort_workflows_by_dependencies(selected)
        self.assertLess(ordered.index("aas"), ordered.index("aad-web"))
        self.assertLess(ordered.index("aad-web"), ordered.index("asdw-web"))

    def test_on_process_finished_non_zero_updates_status(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        w._on_process_finished(1)
        self.assertIn("一部失敗あり", w._status_label.text())

    def test_on_process_finished_success_hides_stop_button(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        w._on_process_finished(0)
        self.assertFalse(w._btn_stop.isVisible())

    def test_on_process_finished_failure_hides_stop_button(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        w._on_process_finished(1)
        self.assertFalse(w._btn_stop.isVisible())

    def test_on_process_finished_stopped_skips_completion(self) -> None:
        from hve.gui.main_window import MainWindow

        w = MainWindow(session_index=1)
        # ユーザー停止をシミュレート
        w._page_workbench._stop_requested = True
        w._on_process_finished(0)
        self.assertIn("停止", w._status_label.text())

    def test_on_stop_all_clicked_disables_stop_button_immediately(self) -> None:
        """[停止] クリック直後に [停止] ボタンが即無効化されることを検証する。

        多重押下防止のため、process_finished を待たずに setEnabled(False) する。
        """
        from hve.gui.main_window import MainWindow
        from hve.gui.page_options import OptionsPage
        from hve.gui.page_workbench import WorkbenchPage

        w = MainWindow(session_index=1)
        # Step 2 へ遷移し、実行中状態をシミュレート
        btns = w._page_workflow._group.buttons()
        if not btns:
            self.skipTest("No workflow buttons")
        btns[0].setChecked(True)
        # [次へ]=実行起動のため、モーダル precheck / 入力検証 / 子プロセス起動を
        # patch して Workbench への遷移のみ行わせる（C2 と同根のハング回避）。
        with patch.object(MainWindow, "_run_step1_unified_precheck", return_value=True), \
             patch.object(OptionsPage, "validate", return_value=(True, "")), \
             patch.object(WorkbenchPage, "start_orchestrators"):
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
        # タイトルは行内 QLabel で表示される。
        self.assertIn("QA 自動投入", texts)
        # description は行内 QLabel ではなく入力ウィジェットのツールチップ
        # （およびヘルプポップアップ）へ統合される仕様に変更された。
        self.assertEqual(cb.toolTip(), "QA 質問票を自動的に投入します（既定: 無効）。")
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