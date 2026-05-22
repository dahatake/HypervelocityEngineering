"""hve.autopilot.plan_review_collector のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.autopilot.plan_review_collector import (
    _path_exists,
    collect_planned_inputs,
    collect_planned_outputs,
)
from hve.autopilot.plan_review_model import FileStatus


def test_path_exists_empty(tmp_path: Path) -> None:
    assert _path_exists(tmp_path, "") is True


def test_path_exists_file_present(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    assert _path_exists(tmp_path, "a.md") is True


def test_path_exists_missing(tmp_path: Path) -> None:
    assert _path_exists(tmp_path, "missing.md") is False


def test_path_exists_glob_hit(tmp_path: Path) -> None:
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "a.md").write_text("", encoding="utf-8")
    assert _path_exists(tmp_path, "x/*.md") is True


def test_collect_planned_inputs_returns_existing_status(tmp_path: Path) -> None:
    """aas Step 1 の required_input_paths が宣言されていれば、tmp_path 下に
    ファイルがないため全件 MISSING_GAP となることを確認。

    Major #8: 入力 0 件で vacuous true にならないよう、宣言値の数を別途確認。
    """
    from hve.workflow_registry import get_workflow

    aas = get_workflow("aas")
    assert aas is not None
    step1 = aas.get_step("1")
    declared = list((step1.required_input_paths if step1 else []) or [])

    inputs = collect_planned_inputs(
        ["aas"], tmp_path, steps_by_workflow={"aas": ["1"]}
    )
    # 宣言数と列挙数の一致 → vacuous true 防止
    assert len(inputs) == len(declared)
    if declared:
        assert all(i.status == FileStatus.MISSING_GAP for i in inputs)


def test_collect_planned_inputs_skips_unselected_workflow(tmp_path: Path) -> None:
    inputs = collect_planned_inputs(
        ["aas"], tmp_path, steps_by_workflow={}  # キー欠落 → 対象ゼロ
    )
    assert inputs == []


def test_collect_planned_outputs(tmp_path: Path) -> None:
    outputs = collect_planned_outputs(
        ["aas"], tmp_path, steps_by_workflow={"aas": ["1"]}
    )
    # 出力 0 件ではない（aas Step 1 は output_paths を持つ）と仮定。
    # 持たない場合は空リストになり得るためアサートは「型のみ」。
    assert isinstance(outputs, list)
    for o in outputs:
        assert o.already_exists is False  # 全てまだ未作成


def test_collect_planned_outputs_existing_file_meta(tmp_path: Path) -> None:
    outputs = collect_planned_outputs(
        ["aas"], tmp_path, steps_by_workflow={"aas": ["1"]}
    )
    if not outputs:
        pytest.skip("aas/1 has no declared output_paths")
    # ファイル作成して mtime/size が埋まることを確認
    target = outputs[0]
    p = tmp_path / target.path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("hello", encoding="utf-8")
    outputs2 = collect_planned_outputs(
        ["aas"], tmp_path, steps_by_workflow={"aas": ["1"]}
    )
    hit = [o for o in outputs2 if o.path == target.path][0]
    assert hit.already_exists is True
    assert hit.size_bytes == 5
    assert hit.mtime_iso is not None
