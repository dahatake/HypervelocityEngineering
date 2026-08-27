"""test_page_options_github_cicd.py — github.com CI/CD トグルの可視性と同期。

メイン画面（C10）の「github.com で CI/CD を実行」トグルは
`_STEP2_FIELDS_BY_WORKFLOW` への登録により asdw-web / adfdv 選択時のみ右ペインの
ワークフロー枠へ移設・表示される。本トグルは設定画面（C5）の
「PR 自動 Approve & Auto-merge」(enable_auto_merge) と双方向同期し、内部設定は
enable_auto_merge に一本化されている。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import List

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtWidgets import QApplication, QLabel, QGroupBox  # noqa: E402

from hve.gui.page_options import (  # noqa: E402
    OptionsPage,
    _C10AppId,
    _DELETE_BRANCH_FIELD_TITLE,
    _LabeledField,
    _STEP2_FIELDS_BY_WORKFLOW,
)


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


class TestGithubCicdToggleVisibility(unittest.TestCase):
    """github_cicd_enabled トグルが asdw-web / adfdv のみで表示されること。"""

    def _titles(self, wf_id: str) -> List[str]:
        return [title for _cat, title in _STEP2_FIELDS_BY_WORKFLOW.get(wf_id, [])]

    def test_registered_for_asdw_web(self) -> None:
        self.assertIn(_C10AppId.GITHUB_CICD_FIELD_TITLE, self._titles("asdw-web"))

    def test_registered_for_adfdv(self) -> None:
        self.assertIn(_C10AppId.GITHUB_CICD_FIELD_TITLE, self._titles("adfdv"))

    def test_not_registered_for_adfd(self) -> None:
        self.assertNotIn(_C10AppId.GITHUB_CICD_FIELD_TITLE, self._titles("adfd"))

    def test_not_registered_for_ard(self) -> None:
        self.assertNotIn(_C10AppId.GITHUB_CICD_FIELD_TITLE, self._titles("ard"))

    def test_not_registered_for_aad_web(self) -> None:
        # aad-web（前段ローカル実行）には github_cicd トグルを出さない
        self.assertNotIn(_C10AppId.GITHUB_CICD_FIELD_TITLE, self._titles("aad-web"))

    def test_toggle_box_created_for_asdw_web(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["asdw-web"], {"asdw-web": "ASDW Web"})
            # asdw-web は固有設定（github_cicd を含む）を持つためワークフロー枠が生成される
            self.assertIn("asdw-web", page._workflow_group_boxes)
        finally:
            page.deleteLater()

    def test_asdw_web_shows_only_the_resource_group_azure_input(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["asdw-web"], {"asdw-web": "ASDW Web"})
            box = page._workflow_group_boxes["asdw-web"]
            titles = [
                field.findChild(QLabel).text().split("  *")[0].strip()
                for field in box.findChildren(_LabeledField)
                if field.findChild(QLabel) is not None
            ]
            self.assertIn("Azure リソースグループ名", titles)
            for title in (
                "DataDeploy location",
                "DataDeploy resource suffix",
                "DataDeploy VNet CIDR",
                "DataDeploy private endpoint subnet CIDR",
                "DataDeploy ACI subnet CIDR",
                "DataDeploy verify ACI image",
            ):
                self.assertNotIn(title, titles)

            page.c_azure.resource_group.setText("rg-app009")

            args = page.build_args_for_workflow("asdw-web")
            argv = args.to_argv()
            self.assertEqual(argv[argv.index("--resource-group") + 1], "rg-app009")
            for flag in (
                "--data-location",
                "--data-resource-suffix",
                "--data-vnet-cidr",
                "--data-private-endpoint-subnet-cidr",
                "--data-aci-subnet-cidr",
            ):
                self.assertNotIn(flag, argv)
        finally:
            page.deleteLater()

    def test_main_toggle_syncs_to_enable_auto_merge(self) -> None:
        # メイン画面トグル ON → 設定画面 enable_auto_merge も ON、
        # build_args は enable_auto_merge=True
        _get_app()
        page = OptionsPage()
        try:
            page.c10.github_cicd_enabled.setChecked(True)
            self.assertTrue(page.c5.enable_auto_merge.isChecked())
            args = page.build_args_for_workflow("asdw-web")
            self.assertTrue(args.enable_auto_merge)
        finally:
            page.deleteLater()

    def test_main_toggle_unchecked_syncs(self) -> None:
        # メイン画面トグル OFF → enable_auto_merge も OFF
        _get_app()
        page = OptionsPage()
        try:
            page.c10.github_cicd_enabled.setChecked(True)
            page.c10.github_cicd_enabled.setChecked(False)
            self.assertFalse(page.c5.enable_auto_merge.isChecked())
            args = page.build_args_for_workflow("asdw-web")
            self.assertFalse(args.enable_auto_merge)
        finally:
            page.deleteLater()

    def test_delete_branch_registered_for_asdw_web(self) -> None:
        # FR-CLI-34: 削除トグルが asdw-web の主画面フィールドに登録されていること。
        self.assertIn(_DELETE_BRANCH_FIELD_TITLE, self._titles("asdw-web"))

    def test_delete_branch_default_true(self) -> None:
        # FR-CLI-34: 削除トグルは既定 ON（C5/C10 両方）、args も True。
        _get_app()
        page = OptionsPage()
        try:
            self.assertTrue(page.c5.delete_local_merged_branch.isChecked())
            self.assertTrue(page.c10.delete_local_merged_branch.isChecked())
            args = page.build_args_for_workflow("asdw-web")
            self.assertTrue(args.delete_local_merged_branch)
        finally:
            page.deleteLater()

    def test_delete_branch_main_toggle_syncs(self) -> None:
        # FR-CLI-34: 主画面（C10）OFF → 設定画面（C5）も OFF、args は False。
        _get_app()
        page = OptionsPage()
        try:
            page.c10.delete_local_merged_branch.setChecked(False)
            self.assertFalse(page.c5.delete_local_merged_branch.isChecked())
            args = page.build_args_for_workflow("asdw-web")
            self.assertFalse(args.delete_local_merged_branch)
        finally:
            page.deleteLater()

    def test_settings_toggle_syncs_to_main(self) -> None:
        # 設定画面トグル ON → メイン画面トグルも ON（双方向同期）
        _get_app()
        page = OptionsPage()
        try:
            page.c5.enable_auto_merge.setChecked(True)
            self.assertTrue(page.c10.github_cicd_enabled.isChecked())
        finally:
            page.deleteLater()

    def test_create_working_branch_default_and_args(self) -> None:
        # FR-CLI-83: C5 の既定は新規作業ブランチを作成する。
        _get_app()
        page = OptionsPage()
        try:
            self.assertTrue(page.c5.create_working_branch.isChecked())
            args = page.build_args_for_workflow("aas")
            self.assertTrue(args.create_working_branch)
        finally:
            page.deleteLater()

    def test_create_working_branch_can_be_disabled(self) -> None:
        # FR-CLI-83: OFF は current branch mode として OrchestrateArgs へ伝搬する。
        _get_app()
        page = OptionsPage()
        try:
            page.c5.create_working_branch.setChecked(False)
            args = page.build_args_for_workflow("aas")
            self.assertFalse(args.create_working_branch)
            self.assertIn("--no-create-working-branch", args.to_argv())
        finally:
            page.deleteLater()

    def test_create_working_branch_uses_existing_settings_store(self) -> None:
        from hve.gui import settings_apply, settings_store

        self.assertTrue(settings_store.defaults()["options"]["create_working_branch"])
        self.assertEqual(
            settings_apply._SECTION_FIELDS["C5"]["create_working_branch"],
            "create_working_branch",
        )

    def test_create_working_branch_settings_round_trip(self) -> None:
        from hve.gui import settings_apply

        _get_app()
        page = OptionsPage()
        try:
            settings_apply.apply_to_widgets(
                {"C5": page.c5},
                {"options": {"create_working_branch": False}},
            )
            self.assertFalse(page.c5.create_working_branch.isChecked())
            collected = settings_apply.collect_from_widgets({"C5": page.c5})
            self.assertIs(collected["create_working_branch"], False)
        finally:
            page.deleteLater()


class TestCicdToggleStepCondition(unittest.TestCase):
    """CI/CD 系2トグルを Deploy ステップ選択時のみ表示する条件（ASDW-WEB Step3.4/4.3・
    ADFDV Step1.2/3）。offscreen + 親非表示では isVisible() が信頼できないため、表示有無は
    ワークフロー枠（QGroupBox）への _LabeledField 所属で判定する。
    """

    def _box_field_titles(self, page: OptionsPage, wf_id: str) -> List[str]:
        """指定ワークフロー枠内の _LabeledField タイトル一覧を返す。"""
        box = page._workflow_group_boxes.get(wf_id)
        if box is None:
            return []
        titles: List[str] = []
        for lf in box.findChildren(_LabeledField):
            lbl = lf.findChild(QLabel)
            if lbl is not None:
                titles.append(lbl.text().split("  *")[0].strip())
        return titles

    def _box_layout_widgets(self, page: OptionsPage, wf_id: str) -> List[object]:
        """指定ワークフロー枠の直下 layout widget を順序付きで返す。"""
        box = page._workflow_group_boxes.get(wf_id)
        if box is None or box.layout() is None:
            return []
        layout = box.layout()
        widgets: List[object] = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widgets.append(widget)
        return widgets

    def _labeled_field_title(self, widget: object) -> str:
        if not isinstance(widget, _LabeledField):
            return ""
        lbl = widget.findChild(QLabel)
        if lbl is None:
            return ""
        return lbl.text().split("  *")[0].strip()

    def test_shown_when_step_3_4_selected_asdw(self) -> None:
        # ASDW-WEB で Step3.4 選択時、CI/CD 系2トグルが asdw-web 枠に表示される。
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["asdw-web"], {"asdw-web": "ASDW Web"})
            page.set_selected_steps({"asdw-web": ["3.4"]})
            titles = self._box_field_titles(page, "asdw-web")
            self.assertIn(_C10AppId.GITHUB_CICD_FIELD_TITLE, titles)
            self.assertIn(_DELETE_BRANCH_FIELD_TITLE, titles)
        finally:
            page.deleteLater()

    def test_auth_group_inserted_immediately_before_cicd_toggle_asdw(self) -> None:
        # Deploy Step 選択時、設定画面と同じ GitHub CLI 認証グループを
        # 「github.com で CI/CD を実行」の直上に表示する。
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["asdw-web"], {"asdw-web": "ASDW Web"})
            page.set_selected_steps({"asdw-web": ["3.4"]})
            widgets = self._box_layout_widgets(page, "asdw-web")
            auth_index = widgets.index(page.c5.gh_auth_group)
            cicd_index = next(
                i for i, widget in enumerate(widgets)
                if self._labeled_field_title(widget) == _C10AppId.GITHUB_CICD_FIELD_TITLE
            )
            self.assertIsInstance(page.c5.gh_auth_group, QGroupBox)
            self.assertEqual(page.c5.gh_auth_group.title(), "認証")
            self.assertEqual(auth_index + 1, cicd_index)
        finally:
            page.deleteLater()

    def test_auth_group_hidden_when_no_deploy_step_asdw(self) -> None:
        # Deploy Step 未選択時は CI/CD トグルと同様に認証グループもワークフロー枠へ出さない。
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["asdw-web"], {"asdw-web": "ASDW Web"})
            page.set_selected_steps({"asdw-web": ["1.1", "2.1"]})
            self.assertNotIn(page.c5.gh_auth_group, self._box_layout_widgets(page, "asdw-web"))
        finally:
            page.deleteLater()

    def test_shown_when_step_4_3_selected_asdw(self) -> None:
        # Step4.3 のみでも表示される。
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["asdw-web"], {"asdw-web": "ASDW Web"})
            page.set_selected_steps({"asdw-web": ["4.3"]})
            self.assertIn(
                _C10AppId.GITHUB_CICD_FIELD_TITLE,
                self._box_field_titles(page, "asdw-web"),
            )
        finally:
            page.deleteLater()

    def test_hidden_when_no_deploy_step_asdw(self) -> None:
        # Deploy ステップ（3.4/4.3）未選択なら CI/CD 系2トグルは非表示。APP-ID は残る（CI/CD トグル以外は常時表示）。
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["asdw-web"], {"asdw-web": "ASDW Web"})
            page.set_selected_steps({"asdw-web": ["1.1", "2.1"]})
            titles = self._box_field_titles(page, "asdw-web")
            self.assertNotIn(_C10AppId.GITHUB_CICD_FIELD_TITLE, titles)
            self.assertNotIn(_DELETE_BRANCH_FIELD_TITLE, titles)
            self.assertIn("対象アプリケーション (APP-ID)", titles)
        finally:
            page.deleteLater()

    def test_shown_when_step_3_selected_adfdv(self) -> None:
        # ADFDV は Step3（Functions Deploy）選択時に表示。
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["adfdv"], {"adfdv": "ADFDV"})
            page.set_selected_steps({"adfdv": ["3"]})
            self.assertIn(
                _C10AppId.GITHUB_CICD_FIELD_TITLE,
                self._box_field_titles(page, "adfdv"),
            )
        finally:
            page.deleteLater()

    def test_shown_when_step_1_2_selected_adfdv(self) -> None:
        # ADFDV は Step1.2（データリソース Deploy）選択時も表示。
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["adfdv"], {"adfdv": "ADFDV"})
            page.set_selected_steps({"adfdv": ["1.2"]})
            self.assertIn(
                _C10AppId.GITHUB_CICD_FIELD_TITLE,
                self._box_field_titles(page, "adfdv"),
            )
        finally:
            page.deleteLater()

    def test_hidden_when_no_deploy_step_adfdv(self) -> None:
        # ADFDV で 1.2/3 未選択なら非表示。
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["adfdv"], {"adfdv": "ADFDV"})
            page.set_selected_steps({"adfdv": ["2.1"]})
            self.assertNotIn(
                _C10AppId.GITHUB_CICD_FIELD_TITLE,
                self._box_field_titles(page, "adfdv"),
            )
        finally:
            page.deleteLater()

    def test_toggles_off_when_hidden(self) -> None:
        # Deploy ステップ未選択で非表示化する際、トグルを OFF にする
        # （C5 enable_auto_merge もミラーで OFF）。
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["asdw-web"], {"asdw-web": "ASDW Web"})
            page.set_selected_steps({"asdw-web": ["3.4"]})
            page.c10.github_cicd_enabled.setChecked(True)
            self.assertTrue(page.c5.enable_auto_merge.isChecked())
            # Deploy ステップを外すと非表示化 + OFF。
            page.set_selected_steps({"asdw-web": ["1.1"]})
            self.assertFalse(page.c10.github_cicd_enabled.isChecked())
            self.assertFalse(page.c5.enable_auto_merge.isChecked())
        finally:
            page.deleteLater()

    def test_visible_multi_workflow_one_deploy(self) -> None:
        # 複数選択 ASDW-WEB(Deploy ON) + ADFDV(Deploy OFF): 表示維持・ON が潰されない（T3 回帰）。
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(
                ["asdw-web", "adfdv"], {"asdw-web": "ASDW Web", "adfdv": "ADFDV"}
            )
            page.c10.github_cicd_enabled.setChecked(True)
            page.set_selected_steps({"asdw-web": ["3.4"], "adfdv": ["2.1"]})
            self.assertTrue(page.c10.github_cicd_enabled.isChecked())
        finally:
            page.deleteLater()

    def test_default_preserved_for_non_cicd_workflow(self) -> None:
        # CI/CD 非対応ワークフロー（ard）選択時は削除トグルのデフォルト True を保持（初期状態回帰）。
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["ard"], {"ard": "ARD"})
            page.set_selected_steps({"ard": ["2"]})
            self.assertTrue(page.c10.delete_local_merged_branch.isChecked())
        finally:
            page.deleteLater()


class TestCicdAuthValidation(unittest.TestCase):
    """github.com CI/CD 実行前の GitHub CLI 認証 validation。"""

    def _without_github_tokens(self):
        old_gh = os.environ.pop("GH_TOKEN", None)
        old_github = os.environ.pop("GITHUB_TOKEN", None)
        return old_gh, old_github

    def _restore_github_tokens(self, old_gh: str | None, old_github: str | None) -> None:
        if old_gh is not None:
            os.environ["GH_TOKEN"] = old_gh
        else:
            os.environ.pop("GH_TOKEN", None)
        if old_github is not None:
            os.environ["GITHUB_TOKEN"] = old_github
        else:
            os.environ.pop("GITHUB_TOKEN", None)

    def test_validate_blocks_cicd_on_without_token(self) -> None:
        _get_app()
        old_gh, old_github = self._without_github_tokens()
        page = OptionsPage()
        try:
            page.set_workflows(["asdw-web"], {"asdw-web": "ASDW Web"})
            page.set_selected_steps({"asdw-web": ["3.4"]})
            page.c3.auto_qa.set_tristate(False)
            page.c10.github_cicd_enabled.setChecked(True)
            ok, msg = page.validate()
            self.assertFalse(ok)
            self.assertIn("GitHub CLI 認証", msg)
        finally:
            page.deleteLater()
            self._restore_github_tokens(old_gh, old_github)

    def test_validate_allows_cicd_on_with_token(self) -> None:
        _get_app()
        old_gh, old_github = self._without_github_tokens()
        os.environ["GH_TOKEN"] = "token-for-test"
        page = OptionsPage()
        try:
            page.set_workflows(["asdw-web"], {"asdw-web": "ASDW Web"})
            page.set_selected_steps({"asdw-web": ["3.4"]})
            page.c3.auto_qa.set_tristate(False)
            page.c10.github_cicd_enabled.setChecked(True)
            ok, msg = page.validate()
            self.assertTrue(ok, msg)
        finally:
            page.deleteLater()
            self._restore_github_tokens(old_gh, old_github)

    def test_validate_allows_deploy_step_when_cicd_off_without_token(self) -> None:
        _get_app()
        old_gh, old_github = self._without_github_tokens()
        page = OptionsPage()
        try:
            page.set_workflows(["asdw-web"], {"asdw-web": "ASDW Web"})
            page.set_selected_steps({"asdw-web": ["3.4"]})
            page.c3.auto_qa.set_tristate(False)
            page.c10.github_cicd_enabled.setChecked(False)
            ok, msg = page.validate()
            self.assertTrue(ok, msg)
        finally:
            page.deleteLater()
            self._restore_github_tokens(old_gh, old_github)


if __name__ == "__main__":
    unittest.main()
