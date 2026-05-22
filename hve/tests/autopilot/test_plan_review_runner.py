"""hve.autopilot.plan_review_runner のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

from hve.autopilot.plan_review_model import AutopilotPlanReview, FileStatus
from hve.autopilot.plan_review_runner import build_step1_plan_review


def test_build_returns_review(tmp_path: Path) -> None:
    r = build_step1_plan_review(
        ["aas"], tmp_path, steps_by_workflow={"aas": ["1"]}
    )
    assert isinstance(r, AutopilotPlanReview)
    # inputs / outputs / parameters / gaps は全て list
    assert isinstance(r.inputs, list)
    assert isinstance(r.outputs, list)
    assert isinstance(r.parameters, list)
    assert isinstance(r.gaps, list)


def test_build_empty_when_no_steps_selected(tmp_path: Path) -> None:
    r = build_step1_plan_review(
        ["aas"], tmp_path, steps_by_workflow={"aas": []}
    )
    assert r.inputs == []
    assert r.outputs == []
    # gaps は implicit 依存があれば 0 ではない可能性


def test_has_blocking_gaps_property(tmp_path: Path) -> None:
    r = build_step1_plan_review(
        ["aad-web"], tmp_path, steps_by_workflow={"aad-web": []}
    )
    # aad-web は implicit 依存で app-arch-catalog.md を要求する。
    # tmp_path 上にファイルなしかつ producer 解決済なら gap として現れる。
    assert isinstance(r.has_blocking_gaps, bool)


def test_parameters_collected_when_inputs_given(tmp_path: Path) -> None:
    # 現状 _REQUIRED_BY_WORKFLOW / _REQUIRED_SETTING_KEYS は空のため、結果も空。
    r = build_step1_plan_review(
        ["aas"], tmp_path,
        steps_by_workflow={"aas": ["1"]},
        wizard_inputs_by_workflow={"aas": {}},
        settings_by_workflow={"aas": {}},
    )
    assert r.parameters == []


def test_file_status_enum_values_used() -> None:
    # 列挙値の文字列が安定しており、UI 表示テーブルと整合することを保証
    assert FileStatus.EXISTING_REUSABLE.value == "existing_reusable"
    assert FileStatus.MISSING_PRODUCED.value == "missing_produced"
    assert FileStatus.MISSING_GAP.value == "missing_gap"
    assert FileStatus.UNKNOWN.value == "unknown"


# ----------------------------------------------------------------------
# 回帰テスト: ARD グループ ID → 実 Step ID 展開
# ----------------------------------------------------------------------


def test_ard_group_id_expanded_to_real_step_ids(tmp_path: Path) -> None:
    """ARD グループ ID "4" を渡すと実 Step 4.1 / 4.3 の output が列挙される。

    バグ: 旧実装では plan_review_collector が expand_group_step_ids を呼ばず、
    ARD 実 Step (4.1, 4.3 等) が plan review の outputs から脱落していた。
    """
    r = build_step1_plan_review(
        ["ard"], tmp_path, steps_by_workflow={"ard": ["4"]}
    )
    out_paths = {o.path for o in r.outputs}
    # Step 4.1 と 4.3 の output_paths が含まれる（4.2 は output_paths_template
    # のため fanout 未展開時は outputs に出ない）。
    assert "docs/catalog/use-case-skeleton.md" in out_paths, (
        f"ARD 4.1 の output が脱落: {sorted(out_paths)}"
    )
    assert "docs/catalog/use-case-catalog.md" in out_paths, (
        f"ARD 4.3 の output が脱落: {sorted(out_paths)}"
    )


def test_ard_group_4_resolves_use_case_catalog_gap(tmp_path: Path) -> None:
    """ARD グループ "4" 選択時、aas 側の use-case-catalog.md 要求が
    MISSING_PRODUCED に昇格する（ARD 4.3 が producer として解決される）。
    """
    r = build_step1_plan_review(
        ["ard", "aas"],
        tmp_path,
        steps_by_workflow={"ard": ["4"], "aas": ["1"]},
    )
    # aas Step 1 は use-case-catalog.md を required_input_paths に持つ。
    target = [
        i for i in r.inputs
        if i.workflow_id == "aas" and i.path == "docs/catalog/use-case-catalog.md"
    ]
    assert target, "aas/1 の use-case-catalog.md 入力が見つからない"
    inp = target[0]
    assert inp.status == FileStatus.MISSING_PRODUCED, (
        f"ARD 4.3 が producer として解決されていない: status={inp.status}, "
        f"producer={inp.producer}"
    )
    assert inp.producer == ("ard", "4.3"), (
        f"producer が ARD 4.3 ではない: {inp.producer}"
    )


def test_non_ard_workflow_passthrough_unchanged(tmp_path: Path) -> None:
    """非 ARD workflow は expand_group_step_ids が passthrough のため挙動不変。"""
    r = build_step1_plan_review(
        ["aas"], tmp_path, steps_by_workflow={"aas": ["1"]}
    )
    # aas Step 1 が列挙されている（具体的な output 数までは検証しない）。
    assert any(o.workflow_id == "aas" and o.step_id == "1" for o in r.outputs)
