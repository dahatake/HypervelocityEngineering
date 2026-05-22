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
    for cat_key in ("C4", "C10", "C11", "C12", "C13", "C14"):
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


def test_ard_shows_business_area_and_workiq_draft(qapp):
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.show()
    page.set_workflows(["ard"], {"ard": "ARD"})

    titles = _visible_field_titles(page)
    assert "業務エリア" in titles
    assert "Work IQ 回答ドラフト作成" in titles
    # 追加プロンプト は共通で表示
    assert "追加プロンプト" in titles


def test_akm_shows_renamed_fields(qapp):
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.show()
    page.set_workflows(["akm"], {"akm": "AKM"})

    titles = _visible_field_titles(page)
    assert "取り込みソース" in titles
    assert "対象ファイル" in titles
    assert "既存Knowledgeファイルの再生成" in titles  # renamed
    assert "追加ファイル" in titles  # renamed
    assert "Work IQ 回答ドラフト作成" in titles
    assert "QA 用プロンプト上書き" in titles
    assert "KM 用プロンプト上書き" in titles


def test_aqod_shows_renamed_fields(qapp):
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.show()
    page.set_workflows(["aqod"], {"aqod": "AQOD"})

    titles = _visible_field_titles(page)
    assert "チェック対象ファイルのフォルダパス" in titles  # renamed
    assert "分析の深さ" in titles
    assert "分析の観点" in titles  # renamed


def test_aqod_depth_choices_are_japanese(qapp):
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    items = [page.c12.depth.itemText(i) for i in range(page.c12.depth.count())]
    assert any("標準" in t and "standard" in t for t in items)
    assert any("軽量" in t and "lightweight" in t for t in items)


def test_adoc_fields(qapp):
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.show()
    page.set_workflows(["adoc"], {"adoc": "ADOC"})

    titles = _visible_field_titles(page)
    assert "ドキュメント生成対象ディレクトリ" in titles
    assert "除外パターン" in titles
    assert "ドキュメントの主目的" in titles


def test_aad_web_resource_group_hidden(qapp):
    """aad-web は APP-ID のみ。Azure RG は表示されない。"""
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.show()
    page.set_workflows(["aad-web"], {"aad-web": "AAD-WEB"})

    titles = _visible_field_titles(page)
    assert "対象アプリケーション (APP-ID)" in titles
    assert "Azure リソースグループ名" not in titles


def test_asdw_web_shows_resource_group(qapp):
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.show()
    page.set_workflows(["asdw-web"], {"asdw-web": "ASDW-WEB"})

    titles = _visible_field_titles(page)
    assert "Azure リソースグループ名" in titles
    assert "対象アプリケーション (APP-ID)" not in titles


def test_abd_shows_app_id(qapp):
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    page.show()
    page.set_workflows(["adfd"], {"adfd": "ADFD"})

    titles = _visible_field_titles(page)
    assert "データフローアプリ ID" in titles


def test_dedup_when_multiple_workflows(qapp):
    """asdw-web + adfdv は両方とも `Azure リソースグループ名` を要求するが 1 つに統合される。"""
    from hve.gui.page_options import OptionsPage
    from hve.gui.page_options import _LabeledField
    from PySide6.QtWidgets import QLabel

    page = OptionsPage()
    page.show()
    page.set_workflows(
        ["asdw-web", "adfdv"],
        {"asdw-web": "ASDW-WEB", "adfdv": "ADFDV"},
    )

    matching = []
    for lf in page.findChildren(_LabeledField):
        if not lf.isVisible():
            continue
        lbl = lf.findChild(QLabel)
        if lbl and lbl.text().split("  *")[0].strip() == "Azure リソースグループ名":
            matching.append(lf)
    # 同一 _LabeledField インスタンス（c10 配下）なので 1 件のみ
    assert len(matching) == 1


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
    for wf in ("ard", "akm", "aqod", "adoc", "aad-web", "asdw-web", "adfd", "adfdv"):
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
    """C3（追加プロンプト）が `_groups_layout` の先頭に常時固定されることを検証する。

    全ワークフロー（`aas` を含む）に対して:
      - C3 カテゴリ枠が可視
      - `_groups_layout` の index 0 が C3
      - C3 内の `_LabeledField` のうち「追加プロンプト」のみが可視
    """
    from hve.gui.page_options import OptionsPage, _LabeledField

    page = OptionsPage()
    page.show()
    workflows = (
        "ard", "aas", "aad-web", "asdw-web", "adfd", "adfdv",
        "aag", "aagd", "akm", "aqod", "adoc",
    )
    for wf in workflows:
        page.set_workflows([wf], {wf: wf})
        c3 = page._category_groups["C3"]
        assert c3.isVisible(), f"C3 hidden in {wf}"
        assert page._groups_layout.indexOf(c3) == 0, (
            f"C3 not at top in {wf} (index={page._groups_layout.indexOf(c3)})"
        )
        # C3 内の可視 LabeledField は「追加プロンプト」のみ
        visible_c3_titles = []
        for lf in page.c3.findChildren(_LabeledField):
            if not lf.isVisible():
                continue
            lbl = lf.findChild(QLabel)
            if lbl is None:
                continue
            visible_c3_titles.append(lbl.text().split("  *")[0].strip())
        assert visible_c3_titles == ["追加プロンプト"], (
            f"unexpected visible fields in C3 for {wf}: {visible_c3_titles}"
        )
