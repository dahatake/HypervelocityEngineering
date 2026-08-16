"""Tests for Step 2 page workflow-specific field visibility refactor."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QLabel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _visible_field_titles(page) -> list[str]:
    """OptionsPage 上の現在見えている _LabeledField タイトル一覧を返す。"""
    from hve.gui.page_options import _LabeledField

    titles: list[str] = []
    for lf in page.findChildren(_LabeledField):
        if not lf.isVisible():
            continue
        lbl = lf.findChild(QLabel)
        if lbl is None:
            continue
        head = lbl.text().split("  *")[0].strip()
        titles.append(head)
    return titles


def test_aas_shows_only_notice(qapp):
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.show()
    page.set_workflows(["aas"], {"aas": "AAS"})

    # Notice should be visible
    assert page._aas_notice is not None
    assert page._aas_notice.isVisible()
    # 他のカテゴリ枠は全て非表示
    for cat_key in ("C4", "C10", "C11", "C13", "C14", "C17"):
        g = page._category_groups.get(cat_key)
        if g is not None:
            assert not g.isVisible(), f"{cat_key} should be hidden for aas"


def test_workiq_draft_does_not_override_existing_true(qapp):
    """非 ard/akm でも c4.workiq=True なら True のまま（妨害しない）。"""
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.set_workflows(["adoc"], {"adoc": "ADOC"})
    page.c4.workiq.setChecked(True)
    page.c4.workiq_draft.setChecked(False)

    args = page.build_args(repo_root=Path.cwd())
    assert args.workiq is True


def test_adi_depth_choices_are_japanese(qapp):
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    depth = page.c17.analysis_depth
    items = [depth.itemText(i) for i in range(depth.count())]
    assert any("標準" in t and "standard" in t for t in items)
    assert any("軽量" in t and "lightweight" in t for t in items)


def test_workiq_draft_session_override_for_ard(qapp):
    """ard 選択時に QA 回答ドラフト生成 ON → args.workiq=True（セッション限定）。"""
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.set_workflows(["ard"], {"ard": "ARD"})
    page.c4.workiq.setChecked(False)
    page.c4.workiq_draft.setChecked(True)

    args = page.build_args(repo_root=Path.cwd())
    assert args.workiq is True


def test_workiq_draft_no_override_for_other_workflows(qapp):
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.set_workflows(["adoc"], {"adoc": "ADOC"})
    page.c4.workiq.setChecked(False)
    page.c4.workiq_draft.setChecked(True)

    args = page.build_args(repo_root=Path.cwd())
    # adoc では強制 ON されない
    assert args.workiq is False


def test_common_additional_prompt_visible_for_all(qapp):
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.show()
    for wf in ("ard", "akm", "adi", "adoc", "aad-web", "asdw-web", "adfd", "adfdv"):
        page.set_workflows([wf], {wf: wf})
        titles = _visible_field_titles(page)
        assert "追加プロンプト" in titles, f"missing in {wf}"


def test_cxx_prefix_removed_from_groups(qapp):
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    for key, group in page._category_groups.items():
        title = group.title()
        # `C1:` のようなプレフィックスは含まれない
        assert not title.startswith("C1:"), title
        assert not title.startswith(f"{key}:"), title


def test_additional_prompt_pinned_top_for_all_workflows(qapp):
    """C3（共通設定）が `_groups_layout` の先頭に常時固定されることを検証する。

    全ワークフロー（`aas` を含む）に対して:
      - C3 カテゴリ枠が可視
      - `_groups_layout` の index 0 が C3
      - C3 内の `_LabeledField` のうち FR-GUI-20 が規定する 6 項目のみが
        規定順で可視
    """
    from hve.gui.page_options import OptionsPage, _LabeledField

    page = OptionsPage()
    page.show()
    workflows = (
        "ard", "aas", "aad-web", "asdw-web", "adfd", "adfdv",
        "aag", "aagd", "akm", "adi", "adoc",
    )
    for wf in workflows:
        page.set_workflows([wf], {wf: wf})
        c3 = page._category_groups["C3"]
        assert c3.isVisible(), f"C3 hidden in {wf}"
        assert page._groups_layout.indexOf(c3) == 0, (
            f"C3 not at top in {wf} (index={page._groups_layout.indexOf(c3)})"
        )
        visible_c3_titles = []
        for lf in page.c3.findChildren(_LabeledField):
            if not lf.isVisible():
                continue
            lbl = lf.findChild(QLabel)
            if lbl is None:
                continue
            visible_c3_titles.append(lbl.text().split("  *")[0].strip())
        assert visible_c3_titles == [
            "QA (質問票) 自動投入", "QA (質問票) 回答モード",
            "QA (質問票) を Knowledge Management へバックグラウンドでマージする",
            "Knowledge Management 用モデル", "Knowledge Management 用コンテキスト階層",
            "追加プロンプト",
        ], (
            f"unexpected visible fields in C3 for {wf}: {visible_c3_titles}"
        )
