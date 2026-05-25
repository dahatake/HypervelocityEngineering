"""MainWindow._offer_session_artifacts_to_attachment_pane の動作テスト。

Step 1 戻り時にセッション成果物を AttachmentPane へ取り込むフローを
ヘッドレスで検証する（実 UI ダイアログは exec をモックする）。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


class TestSessionArtifactPickerDialog(unittest.TestCase):
    """_SessionArtifactPickerDialog 単体テスト。"""

    def setUp(self) -> None:
        _ensure_app()

    def test_initial_all_checked(self) -> None:
        from hve.gui.main_window import _SessionArtifactPickerDialog

        paths = [Path("/tmp/a.md"), Path("/tmp/b.md"), Path("/tmp/c.md")]
        dlg = _SessionArtifactPickerDialog(paths)
        self.assertEqual(dlg.selected_paths(), paths)

    def test_select_all_deselect_all(self) -> None:
        from PySide6.QtCore import Qt
        from hve.gui.main_window import _SessionArtifactPickerDialog

        paths = [Path("/tmp/a.md"), Path("/tmp/b.md")]
        dlg = _SessionArtifactPickerDialog(paths)
        dlg._set_all(Qt.CheckState.Unchecked)
        self.assertEqual(dlg.selected_paths(), [])
        dlg._set_all(Qt.CheckState.Checked)
        self.assertEqual(dlg.selected_paths(), paths)


class TestOfferSessionArtifacts(unittest.TestCase):
    """_offer_session_artifacts_to_attachment_pane のフィルタ / 重複除外 / ダイアログ呼び出しを検証。"""

    def setUp(self) -> None:
        _ensure_app()
        # 実 MainWindow は重い初期化を伴うため、ファクト関数のみ動的に検証する。
        # _offer_session_artifacts_to_attachment_pane は self._page_workbench /
        # self._page_options に依存するだけなので、最小モックで呼び出せる。
        from hve.gui.main_window import MainWindow

        self._cls = MainWindow

    def _make_obj(
        self,
        artifacts,
        attached_src_paths=None,
        dialog_accepted=True,
        dialog_selected=None,
    ):
        """MainWindow インスタンスのモック相当オブジェクトを作る。"""
        obj = MagicMock(spec=self._cls)
        # session_artifacts
        obj._page_workbench = MagicMock()
        obj._page_workbench.session_artifacts.return_value = list(artifacts)
        # attachment_pane
        pane = MagicMock()
        pane._results = [
            MagicMock(src_path=Path(p)) for p in (attached_src_paths or [])
        ]
        pane._on_files_dropped = MagicMock()
        obj._page_options = MagicMock()
        obj._page_options.attachment_pane.return_value = pane
        self._pane = pane
        # ダイアログ exec/selected をパッチ
        self._dialog_accepted = dialog_accepted
        self._dialog_selected = dialog_selected
        # 実メソッドを束縛して呼び出す
        return obj

    def _invoke(self, obj):
        self._cls._offer_session_artifacts_to_attachment_pane(obj)

    def test_empty_artifacts_noop(self) -> None:
        obj = self._make_obj(artifacts=[])
        self._invoke(obj)
        self._pane._on_files_dropped.assert_not_called()

    def test_unsupported_extension_filtered(self, tmp=None) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            unsupported = Path(d) / "script.py"
            unsupported.write_text("x = 1", encoding="utf-8")
            obj = self._make_obj(artifacts=[unsupported])
            # ダイアログが呼ばれないことを確認するため exec をパッチ
            with patch(
                "hve.gui.main_window._SessionArtifactPickerDialog"
            ) as DlgCls:
                self._invoke(obj)
                DlgCls.assert_not_called()
        self._pane._on_files_dropped.assert_not_called()

    def test_nonexistent_path_filtered(self) -> None:
        obj = self._make_obj(artifacts=[Path("/no/such/file.md")])
        with patch("hve.gui.main_window._SessionArtifactPickerDialog") as DlgCls:
            self._invoke(obj)
            DlgCls.assert_not_called()
        self._pane._on_files_dropped.assert_not_called()

    def test_dedup_against_already_attached(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            p1 = Path(d) / "a.md"
            p1.write_text("# a", encoding="utf-8")
            obj = self._make_obj(
                artifacts=[p1], attached_src_paths=[str(p1.resolve())]
            )
            with patch("hve.gui.main_window._SessionArtifactPickerDialog") as DlgCls:
                self._invoke(obj)
                DlgCls.assert_not_called()
        self._pane._on_files_dropped.assert_not_called()

    def test_dialog_canceled_noop(self) -> None:
        import tempfile
        from PySide6.QtWidgets import QDialog

        with tempfile.TemporaryDirectory() as d:
            p1 = Path(d) / "a.md"
            p1.write_text("# a", encoding="utf-8")
            obj = self._make_obj(artifacts=[p1])
            with patch(
                "hve.gui.main_window._SessionArtifactPickerDialog"
            ) as DlgCls:
                dlg_inst = MagicMock()
                dlg_inst.exec.return_value = int(QDialog.DialogCode.Rejected)
                DlgCls.return_value = dlg_inst
                self._invoke(obj)
        self._pane._on_files_dropped.assert_not_called()

    def test_dialog_accepted_zero_selected_noop(self) -> None:
        import tempfile
        from PySide6.QtWidgets import QDialog

        with tempfile.TemporaryDirectory() as d:
            p1 = Path(d) / "a.md"
            p1.write_text("# a", encoding="utf-8")
            obj = self._make_obj(artifacts=[p1])
            with patch(
                "hve.gui.main_window._SessionArtifactPickerDialog"
            ) as DlgCls:
                dlg_inst = MagicMock()
                dlg_inst.exec.return_value = int(QDialog.DialogCode.Accepted)
                dlg_inst.selected_paths.return_value = []
                DlgCls.return_value = dlg_inst
                self._invoke(obj)
        self._pane._on_files_dropped.assert_not_called()

    def test_dialog_accepted_passes_selected_paths(self) -> None:
        import tempfile
        from PySide6.QtWidgets import QDialog

        with tempfile.TemporaryDirectory() as d:
            p1 = Path(d) / "a.md"
            p2 = Path(d) / "b.md"
            p1.write_text("# a", encoding="utf-8")
            p2.write_text("# b", encoding="utf-8")
            obj = self._make_obj(artifacts=[p1, p2])
            with patch(
                "hve.gui.main_window._SessionArtifactPickerDialog"
            ) as DlgCls:
                dlg_inst = MagicMock()
                dlg_inst.exec.return_value = int(QDialog.DialogCode.Accepted)
                dlg_inst.selected_paths.return_value = [p1]
                DlgCls.return_value = dlg_inst
                self._invoke(obj)
        self._pane._on_files_dropped.assert_called_once_with([p1])


if __name__ == "__main__":
    unittest.main()
