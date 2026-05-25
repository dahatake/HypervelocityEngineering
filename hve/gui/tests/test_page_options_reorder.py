"""test_page_options_reorder.py — Step 1 右ペインのワークフロー単位グループ枠テスト。

Step 1 右ペインは「ワークフロー単位の QGroupBox（タイトル＝ワークフロー名）」で
固有設定を表示する設計に変更された。本テストは以下を検証する:

- 選択ワークフローごとに `_workflow_group_boxes` にエントリが作られること
- 表示順が `_WORKFLOW_CANONICAL_ORDER` (ARD 先頭) に従うこと
- 固有設定を持たないワークフロー (aas / aag / aagd) は枠が作られないこと
- 旧カテゴリ枠 (C4 / C10〜C14) は常時非表示であること
- 「追加プロンプト」(C3) は最上部 (index 0) に固定されること
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import List

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtWidgets import QApplication, QGroupBox  # noqa: E402

from hve.gui.page_options import OptionsPage  # noqa: E402


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _workflow_box_order(page: OptionsPage) -> List[str]:
    """`_groups_layout` 上の workflow group box を出現順に並べた workflow_id リスト。"""
    layout = page._groups_layout  # type: ignore[attr-defined]
    inverse = {id(b): wf_id for wf_id, b in page._workflow_group_boxes.items()}
    ids: List[str] = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        w = item.widget() if item is not None else None
        if isinstance(w, QGroupBox):
            wf_id = inverse.get(id(w))
            if wf_id is not None:
                ids.append(wf_id)
    return ids


class TestWorkflowGroupBoxes(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()
        self.page = OptionsPage()

    def tearDown(self) -> None:
        self.page.deleteLater()

    def test_ard_only_creates_ard_box(self) -> None:
        self.page.set_workflows(["ard"], {"ard": "Auto Requirement Definition"})
        self.assertIn("ard", self.page._workflow_group_boxes)
        self.assertEqual(_workflow_box_order(self.page), ["ard"])

    def test_ard_plus_akm_ordered_canonically(self) -> None:
        # 入力順を逆にしても正準順 (ARD → AKM) で並ぶ
        self.page.set_workflows(
            ["akm", "ard"],
            {"akm": "Knowledge Management", "ard": "Auto Requirement Definition"},
        )
        order = _workflow_box_order(self.page)
        self.assertEqual(order, ["ard", "akm"])

    def test_aas_only_creates_no_box(self) -> None:
        # `aas` は固有設定を持たないため枠を作らない
        self.page.set_workflows(["aas"], {"aas": "Architecture Design"})
        self.assertEqual(self.page._workflow_group_boxes, {})

    def test_category_groups_always_hidden(self) -> None:
        """C4 / C10〜C14 のカテゴリ枠は常時非表示。"""
        self.page.set_workflows(
            ["ard", "akm"],
            {"ard": "Auto Requirement Definition", "akm": "Knowledge Management"},
        )
        for key in ("C4", "C10", "C11", "C12", "C13", "C14"):
            self.assertFalse(
                self.page._category_groups[key].isVisibleTo(self.page),
                f"{key} should be hidden, but is visible",
            )

    def test_additional_prompt_pinned_at_top(self) -> None:
        """C3 (追加プロンプト) は `_groups_layout` の index 0 に固定。"""
        self.page.set_workflows(["ard"], {"ard": "Auto Requirement Definition"})
        layout = self.page._groups_layout
        c3 = self.page._category_groups["C3"]
        self.assertEqual(layout.indexOf(c3), 0)

    def test_switching_workflows_disposes_old_box(self) -> None:
        self.page.set_workflows(["akm"], {"akm": "Knowledge Management"})
        self.assertIn("akm", self.page._workflow_group_boxes)
        self.page.set_workflows(["ard"], {"ard": "Auto Requirement Definition"})
        self.assertNotIn("akm", self.page._workflow_group_boxes)
        self.assertIn("ard", self.page._workflow_group_boxes)

    def test_box_title_contains_workflow_name(self) -> None:
        self.page.set_workflows(
            ["aad-web"], {"aad-web": "Web App Design"}
        )
        box = self.page._workflow_group_boxes["aad-web"]
        title = box.title()
        # `format_workflow_label("aad-web", "Web App Design")` -> "Web App Design (AAD-WEB)"
        self.assertIn("Web App Design", title)
        self.assertIn("AAD-WEB", title)

    def test_ard_attachment_pane_is_inside_workflow_box(self) -> None:
        """ARD 選択時、`AttachmentPane` は ARD ワークフロー枠の配下に置かれて表示可能であること。
        旧実装では c14 (常時非表示) に追加されてしまい表示できなかったため回帰防止。
        """
        self.page.set_workflows(["ard"], {"ard": "Auto Requirement Definition"})
        pane = self.page._attachment_pane
        if pane is None:
            self.skipTest("AttachmentPane could not be imported in this environment")
        box = self.page._workflow_group_boxes.get("ard")
        self.assertIsNotNone(box)
        # AttachmentPane の Qt 親が ARD ワークフロー枠であること
        self.assertIs(pane.parentWidget(), box)

    def test_aad_web_app_id_checklist_attached_to_target_field(self) -> None:
        """aad-web 選択時、`AppIdChecklist` は対象アプリケーション LF の layout 内に追加され、
        Qt 親も同 LF であること。旧実装では `_find_labeled_field(self.c10, ...)` が
        reparent 後の LF を見つけられず checklist が orphan 化していた回帰防止。
        """
        self.page.set_workflows(["aad-web"], {"aad-web": "Web App Design"})
        cl = self.page._app_id_checklist
        if cl is None:
            self.skipTest("AppIdChecklist not created (catalog missing)")
        target_lf = self.page._lf_registry.get(
            ("c10", "対象アプリケーション (APP-ID)")
        )
        self.assertIsNotNone(target_lf)
        self.assertIs(cl.parentWidget(), target_lf)


if __name__ == "__main__":
    unittest.main()
