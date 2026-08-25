"""test_workflow_required_input_fields.py — FR-GUI-06（表示）のテスト。

Step 1 右ペインは、選択中ワークフローが必要とする必須入力キーの入力欄を、
当該ワークフローの枠内に表示しなければならない。

検証項目:
  1. 必須入力キーごとの入力欄が、当該ワークフロー枠の中に配置されること
  2. `_STEP2_FIELDS_BY_WORKFLOW` の全エントリが実在する入力欄へ解決できること
  3. 固有入力欄を他に持たないワークフローでも、必須入力キーがあれば枠が生成されること

必須キーの正本は FR-GUI-02 に従いレジストリ側（`REQUIREMENT_TABLE` /
`StepDef.required_params`）であり、本テストは表示対応表側にキー定義を持たない。

根拠: hve-dev/requirement-definition.md §6.4 FR-GUI-06
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from hve.gui.page_options import (  # noqa: E402
    OptionsPage,
    _LabeledField,
    _STEP2_FIELDS_BY_WORKFLOW,
)
from hve.gui.workflow_step_requirements import (  # noqa: E402
    REQUIREMENT_TABLE,
    gui_visible_required_params,
)
from hve.workflow_registry import get_workflow, list_workflows  # noqa: E402


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _required_keys_by_workflow() -> Dict[str, Set[str]]:
    """レジストリ宣言から (workflow_id -> 必須入力キー集合) を組み立てる。

    FR-GUI-01 が評価する 2 系統（`REQUIREMENT_TABLE` の `required_info_keys` と
    `StepDef.required_params`）の和集合。`required_params` 側は FR-GUI-02 に従い
    `default_params` を持たないキーに限る（既定値付きキーは入力欄を持たない）。
    registry に存在しない仮想ワークフロー（autopilot）は GUI のワークフロー選択対象外の
    ため除外する。
    """
    out: Dict[str, Set[str]] = {}
    for (wf_id, _step_id), req in REQUIREMENT_TABLE.items():
        if get_workflow(wf_id) is None:
            continue
        if req.required_info_keys:
            out.setdefault(wf_id, set()).update(req.required_info_keys)
    for wf in list_workflows():
        for step in wf.steps:
            for key in gui_visible_required_params(step):
                out.setdefault(wf.id, set()).add(key)
    return out


def _owning_labeled_field(widget: QWidget) -> Optional[_LabeledField]:
    """入力ウィジェットを内包する `_LabeledField` を親方向へ辿って返す。"""
    current: Optional[QWidget] = widget
    while current is not None:
        if isinstance(current, _LabeledField):
            return current
        current = current.parentWidget()
    return None


class TestRequiredInputFieldsInWorkflowBox(unittest.TestCase):
    """必須入力キーの入力欄が当該ワークフローの枠内に表示されること。"""

    @classmethod
    def setUpClass(cls) -> None:
        _get_app()
        cls.page = OptionsPage()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.page.deleteLater()

    def test_each_workflow_shows_its_required_input_fields(self) -> None:
        page = self.page
        widgets = page._banner_input_widgets()
        missing: List[Tuple[str, str]] = []
        for wf_id, keys in sorted(_required_keys_by_workflow().items()):
            page.set_workflows([wf_id], {wf_id: wf_id})
            box = page._workflow_group_boxes.get(wf_id)
            if box is None:
                missing.extend((wf_id, key) for key in sorted(keys))
                continue
            shown = {id(lf) for lf in box.findChildren(_LabeledField)}
            for key in sorted(keys):
                widget = widgets.get(key)
                self.assertIsNotNone(
                    widget, f"必須キー {key} に対応する入力ウィジェットが無い"
                )
                lf = _owning_labeled_field(widget)
                self.assertIsNotNone(
                    lf, f"必須キー {key} の入力欄が _LabeledField に属していない"
                )
                if id(lf) not in shown:
                    missing.append((wf_id, key))
        self.assertEqual(
            missing, [], f"ワークフロー枠に必須入力欄が無い: {missing}"
        )

    def test_no_unresolvable_field_entries(self) -> None:
        page = self.page
        page._ensure_lf_registry()
        unresolved = [
            (wf_id, cat, title)
            for wf_id, entries in sorted(_STEP2_FIELDS_BY_WORKFLOW.items())
            for cat, title in entries
            if page._lf_registry.get((cat, title.strip())) is None
        ]
        self.assertEqual(
            unresolved, [], f"実在しない入力欄を指すエントリ: {unresolved}"
        )

    def test_workflow_without_other_specific_fields_still_gets_box(self) -> None:
        """`aagd` は resource_group 以外の固有入力欄を持たないが枠を生成する。"""
        page = self.page
        page.set_workflows(["aagd"], {"aagd": "AAGD"})
        self.assertIn("aagd", page._workflow_group_boxes)

    def test_ard_recommendation_id_is_visible_in_workflow_box(self) -> None:
        """ARDの任意SR-ID入力を内部保持だけでなく右ペインへ公開する。"""
        page = self.page
        page.set_workflows(["ard"], {"ard": "ARD"})
        box = page._workflow_group_boxes.get("ard")
        self.assertIsNotNone(box)
        recommendation_field = _owning_labeled_field(
            page.c14.target_recommendation_id
        )
        self.assertIsNotNone(recommendation_field)
        self.assertIn(
            id(recommendation_field),
            {id(field) for field in box.findChildren(_LabeledField)},
        )

    def test_ard_recommendation_id_reaches_cli_argv(self) -> None:
        """右ペインのSR-IDをOrchestrateArgsとCLI argvへ欠落なく伝搬する。"""
        page = self.page
        page.set_workflows(["ard"], {"ard": "ARD"})
        page.c14.target_recommendation_id.setText("sr-3")

        args = page.build_args_for_workflow("ard")
        self.assertEqual(args.target_recommendation_id, "sr-3")
        argv = args.to_argv()
        option_index = argv.index("--target-recommendation-id")
        self.assertEqual(argv[option_index + 1], "sr-3")

    def test_defaulted_params_have_no_input_field(self) -> None:
        """既定値を持つ ASDW-WEB Step 1.3 の 5 件に入力欄を設けない（FR-WF-ASDW-02）。"""
        step = get_workflow("asdw-web").get_step("1.3")
        defaulted = [k for k in step.required_params if k in step.default_params]
        self.assertTrue(defaulted)

        page = self.page
        widgets = page._banner_input_widgets()
        for key in defaulted:
            self.assertNotIn(key, widgets, f"{key} の入力欄が残っている")
            self.assertIsNone(getattr(page.c_azure, key, None), f"{key} ウィジェットが残っている")
