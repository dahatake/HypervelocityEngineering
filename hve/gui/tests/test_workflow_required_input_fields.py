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
from hve.gui.workflow_step_requirements import REQUIREMENT_TABLE  # noqa: E402
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
    `StepDef.required_params`）の和集合。registry に存在しない仮想ワークフロー
    （autopilot）は GUI のワークフロー選択対象外のため除外する。
    """
    out: Dict[str, Set[str]] = {}
    for (wf_id, _step_id), req in REQUIREMENT_TABLE.items():
        if get_workflow(wf_id) is None:
            continue
        if req.required_info_keys:
            out.setdefault(wf_id, set()).update(req.required_info_keys)
    for wf in list_workflows():
        for step in wf.steps:
            for key in getattr(step, "required_params", ()) or ():
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
