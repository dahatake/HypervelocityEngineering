"""hve.autopilot.plan_review_gap のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.autopilot.plan_review_collector import collect_planned_inputs
from hve.autopilot.plan_review_gap import (
    _AUTOPILOT_IMPLICIT_REQUIRED_PATHS,
    _ARD_STEP_TO_GROUP,
    _WORKFLOW_CANONICAL_ORDER,
    compute_gaps_and_resolve_inputs,
    implicit_required_paths,
)
from hve.autopilot.plan_review_model import FileStatus, PlannedInput


def test_canonical_order_synced_with_page_options() -> None:
    """`_WORKFLOW_CANONICAL_ORDER` が GUI 側 page_options と同期していることを保証。

    Major #4: 両者は Qt 隔離のため別ファイルに置かれるが、内容は完全一致が必要。
    """
    pytest.importorskip("PySide6")
    from hve.gui.page_options import _WORKFLOW_CANONICAL_ORDER as GUI_ORDER

    assert list(_WORKFLOW_CANONICAL_ORDER) == list(GUI_ORDER), (
        "hve/autopilot/plan_review_gap.py:_WORKFLOW_CANONICAL_ORDER と "
        "hve/gui/page_options.py:_WORKFLOW_CANONICAL_ORDER が一致しません。"
        "両者を同期してください。"
    )


def test_implicit_constants_preserved() -> None:
    # 旧 dependency_resolver から正しく移植されていることを保証
    assert _AUTOPILOT_IMPLICIT_REQUIRED_PATHS["aad-web"] == [
        "docs/catalog/app-arch-catalog.md"
    ]
    assert _AUTOPILOT_IMPLICIT_REQUIRED_PATHS["adfdv"] == [
        "docs/catalog/app-arch-catalog.md"
    ]
    assert _ARD_STEP_TO_GROUP["1.1"] == "1"
    assert _ARD_STEP_TO_GROUP["4.2"] == "4"
    # canonical order に必須 11 workflow が含まれる
    for wf in ["ard", "aas", "aad-web", "asdw-web", "adfd", "adfdv",
               "aag", "aagd", "akm", "aqod", "adoc"]:
        assert wf in _WORKFLOW_CANONICAL_ORDER


def test_implicit_required_paths_for_aad_web() -> None:
    out = implicit_required_paths(["aad-web", "ard"])
    paths = [p for _, p in out]
    assert "docs/catalog/app-arch-catalog.md" in paths


def test_compute_gaps_existing_file_marked_reusable(tmp_path: Path) -> None:
    # 既存ファイルあり → EXISTING_REUSABLE
    rel = "docs/sample.md"
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / rel).write_text("", encoding="utf-8")
    inputs = [
        PlannedInput("aas", "1", rel, FileStatus.EXISTING_REUSABLE, None),
    ]
    resolved, gaps = compute_gaps_and_resolve_inputs(
        inputs, ["aas"], tmp_path, steps_by_workflow={"aas": ["1"]}
    )
    assert any(i.status == FileStatus.EXISTING_REUSABLE for i in resolved)
    assert gaps == []


def test_compute_gaps_missing_with_no_producer(tmp_path: Path) -> None:
    # 生成元なし → MISSING_GAP のまま、提案なし
    inputs = [
        PlannedInput("aas", "1", "this/does/not/exist.md", FileStatus.MISSING_GAP, None),
    ]
    resolved, gaps = compute_gaps_and_resolve_inputs(
        inputs, ["aas"], tmp_path, steps_by_workflow={"aas": ["1"]}
    )
    assert any(
        i.path == "this/does/not/exist.md" and i.status == FileStatus.MISSING_GAP
        for i in resolved
    )
    assert all(g.missing_path != "this/does/not/exist.md" for g in gaps)


def test_compute_gaps_aad_web_implicit_app_catalog(tmp_path: Path) -> None:
    # aad-web 選択時 → implicit に app-arch-catalog.md が要求される。
    # tmp_path には存在しないため MISSING_GAP として現れ、
    # global index で生成元が見つかれば提案、見つからなければ未解決。
    inputs = []
    resolved, gaps = compute_gaps_and_resolve_inputs(
        inputs, ["aad-web"], tmp_path, steps_by_workflow={"aad-web": []}
    )
    catalog_inputs = [
        i for i in resolved if i.path == "docs/catalog/app-arch-catalog.md"
    ]
    assert len(catalog_inputs) == 1
    assert catalog_inputs[0].step_id == "<implicit>"


def test_compute_gaps_producer_already_checked_becomes_produced(tmp_path: Path) -> None:
    # 想定: aas Step 1 が docs/catalog/app-arch-catalog.md を生成し、
    #       aad-web Step (implicit 依存) と aas Step 1 が両方チェック済み
    #       → catalog は MISSING_PRODUCED へ昇格
    from hve.workflow_registry import get_workflow

    aas = get_workflow("aas")
    assert aas is not None
    # aas step 1 の output_paths を確認
    step1 = aas.get_step("1")
    if step1 is None or "docs/catalog/app-arch-catalog.md" not in (step1.output_paths or []):
        pytest.skip("aas step 1 does not output app-arch-catalog.md in current registry")

    resolved, gaps = compute_gaps_and_resolve_inputs(
        [],
        ["aas", "aad-web"],
        tmp_path,
        steps_by_workflow={"aas": ["1"], "aad-web": []},
    )
    catalog = [
        i for i in resolved if i.path == "docs/catalog/app-arch-catalog.md"
    ]
    assert any(i.status == FileStatus.MISSING_PRODUCED for i in catalog)
    # 提案からは外れる
    assert all(g.missing_path != "docs/catalog/app-arch-catalog.md" for g in gaps)


def test_compute_gaps_ard_grouping(tmp_path: Path) -> None:
    # ARD の Step ID を含む提案はグループ ID に変換される
    # （ARD が producer になる入力を仕掛けるには workflow_registry に依存。
    #  ここでは _to_enable_id ロジックを間接確認）
    from hve.autopilot.plan_review_gap import _to_enable_id

    assert _to_enable_id("ard", "1.1") == "1"
    assert _to_enable_id("ard", "4.2") == "4"
    assert _to_enable_id("aas", "1.1") == "1.1"
