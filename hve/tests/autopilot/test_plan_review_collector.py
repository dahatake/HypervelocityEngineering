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


def test_collect_planned_inputs_lists_midstream_step_without_predecessors(
    tmp_path: Path,
) -> None:
    """T1 回帰防止: 前段ステップ（1.1〜1.3）を選択せず途中ステップ 2.1 のみを
    選択した場合でも、2.1 の required_input_paths が漏れなく列挙されること。

    依存伝播の撤廃後、選択ステップ単位の入力ファイル検証（Phase B プランレビュー）が
    前段ステップの選択に依存せず機能する安全網であることを固定する。
    """
    from hve.workflow_registry import get_workflow

    wf = get_workflow("asdw-web")
    assert wf is not None
    step_21 = wf.get_step("2.1")
    assert step_21 is not None
    declared = list(step_21.required_input_paths or [])
    # 前提（捏造防止）: 2.1 は app-catalog.md を必須入力として宣言している。
    assert "docs/catalog/app-catalog.md" in declared

    inputs = collect_planned_inputs(
        ["asdw-web"], tmp_path, steps_by_workflow={"asdw-web": ["2.1"]}
    )
    # 2.1 の宣言入力が全て列挙される（前段 1.x 非選択でも欠落しない）
    assert {i.path for i in inputs} == set(declared)
    # 代表として app-catalog.md が step 2.1 に紐づき列挙されている
    assert any(
        i.path == "docs/catalog/app-catalog.md" and i.step_id == "2.1"
        for i in inputs
    )
    # 前段ステップ 1.x の入力は混入しない（選択ステップのみが対象）
    assert all(i.step_id == "2.1" for i in inputs)


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
