"""T6: ``MainWindow._resolve_steps_for_workflow`` の Plan モード経路への配線テスト。

Step 1 のワークフロー別ステップ選択が:
  - ``OrchestrateArgs.steps`` (CLI ``--steps`` 値) に反映される (Q1=C, Q3=B)
  - ``workflow_plan.steps`` (進捗表示) のフィルタに反映される (Q1=C)
  - Step 2 テキスト欄との合成は AND で動作する (Q2=C / Q2-1=A)
  - ARD はグループ ID を CSV に渡しつつ、display は実 Step ID 展開する (Q4=A)
  - ``all_enabled_steps()`` 未登録 wf は全 ON 扱いで後方互換維持

`_resolve_steps_for_workflow` を直接単体テストする方針 (Plan モード経路の
ループ全体を再現するよりも入出力契約が明確で、Context Window も小さい)。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.main_window import MainWindow  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


def _make_fake(enabled_by_wf: dict) -> MagicMock:
    """`_resolve_steps_for_workflow` 実行に必要な属性のみ持つ軽量 self。"""
    fake = MagicMock()
    fake._page_workflow.all_enabled_steps.return_value = enabled_by_wf
    return fake


# ---------------------------------------------------------------------------
# 非 ARD ワークフロー: 実 Step ID がそのまま渡る
# ---------------------------------------------------------------------------


def test_non_ard_partial_selection_no_text() -> None:
    """部分選択 + テキスト欄空 → CSV は選択順、display は集合に一致。"""
    _ensure_app()
    fake = _make_fake({"aas": ["1", "3"]})

    csv, display = MainWindow._resolve_steps_for_workflow(fake, "aas", None)

    # CSV の順序は step1_ids の順序保持 (enabled_by_wf の戻り順) に依存するため、
    # 順序非依存で内容のみ検証。
    assert csv is not None
    assert set(csv.split(",")) == {"1", "3"}
    assert "1" in display and "3" in display
    # 含まれない step は display にも入らない
    assert "2" not in display


def test_non_ard_full_selection_lists_all_explicitly() -> None:
    """Q3=B: 全選択でも全 ID を明示列挙して返す (空フォールバックではない)。"""
    _ensure_app()
    # aas の実 step を取得して全選択にする
    from hve.workflow_registry import get_workflow

    wf = get_workflow("aas")
    assert wf is not None
    all_ids = [s.id for s in wf.steps if not s.is_container]

    fake = _make_fake({"aas": list(all_ids)})
    csv, display = MainWindow._resolve_steps_for_workflow(fake, "aas", None)

    assert csv is not None
    assert set(csv.split(",")) == set(all_ids)
    assert display == set(all_ids)


def test_non_ard_text_override_and_intersect() -> None:
    """Q2-1=A: テキスト欄 ∩ Step 1 選択 が採用される。"""
    _ensure_app()
    fake = _make_fake({"aas": ["1", "2", "3"]})

    csv, display = MainWindow._resolve_steps_for_workflow(fake, "aas", "2,4")

    # "4" は Step 1 で OFF なので AND から除外、"2" のみ残る
    assert csv == "2"
    assert display == {"2"}

def test_non_ard_text_yields_empty_intersection_returns_none() -> None:
    """AND 結果が空集合のとき CSV=None (orchestrator 既定動作にフォールバック)。"""
    _ensure_app()
    fake = _make_fake({"aas": ["1"]})

    csv, display = MainWindow._resolve_steps_for_workflow(fake, "aas", "9.9,8.8")

    assert csv is None
    assert display == set()


def test_unregistered_workflow_returns_none() -> None:
    """`get_workflow` が None を返す未知 wf は (None, empty) を返す。"""
    _ensure_app()
    fake = _make_fake({})
    csv, display = MainWindow._resolve_steps_for_workflow(
        fake, "nonexistent_workflow_xyz", None
    )
    assert csv is None
    assert display == set()


def test_all_enabled_steps_empty_dict_falls_back_to_full() -> None:
    """既存テストモック互換: ``all_enabled_steps()`` が ``{}`` のとき全 ON 扱い。"""
    _ensure_app()
    fake = _make_fake({})  # wf_id 未登録

    from hve.workflow_registry import get_workflow

    wf = get_workflow("aas")
    assert wf is not None
    all_ids = {s.id for s in wf.steps if not s.is_container}

    csv, display = MainWindow._resolve_steps_for_workflow(fake, "aas", None)

    assert csv is not None
    assert set(csv.split(",")) == all_ids
    assert display == all_ids


# ---------------------------------------------------------------------------
# ARD: グループ ID は CSV にそのまま渡し、display は実 Step ID 展開 (Q4=A)
# ---------------------------------------------------------------------------


def test_ard_group_id_csv_and_expanded_display() -> None:
    """ARD: グループ "1","4" を選ぶと CSV は "1,4"、display は実 Step ID 展開。"""
    _ensure_app()
    fake = _make_fake({"ard": ["1", "4"]})

    csv, display = MainWindow._resolve_steps_for_workflow(fake, "ard", None)

    # CSV はグループ ID のまま (orchestrator 側で _WORKFLOW_GROUP_MAPS により再展開)
    assert csv is not None
    assert set(csv.split(",")) == {"1", "4"}
    # display は実 Step ID 展開済 (Q4=A 既定: expand_group_step_ids 利用)
    # _WORKFLOW_GROUP_MAPS["ard"]: "1"→["1","1.1","1.2"], "4"→["4.1","4.2","4.3"]
    expected = {"1", "1.1", "1.2", "4.1", "4.2", "4.3"}
    assert display == expected
    assert "2" not in display  # グループ 2 は未選択


def test_ard_text_override_and_intersect_at_group_level() -> None:
    """ARD: テキスト欄 ∩ Step 1 のグループ ID で AND。"""
    _ensure_app()
    fake = _make_fake({"ard": ["1", "2", "4"]})

    csv, display = MainWindow._resolve_steps_for_workflow(fake, "ard", "2,4")

    # AND 結果: {"2","4"}. 順序は step1_ids の順序保持に依存するため非依存検証。
    assert csv is not None
    assert set(csv.split(",")) == {"2", "4"}
    expected = {"2", "4.1", "4.2", "4.3"}
    assert display == expected


def test_ard_text_override_empty_intersection_returns_none() -> None:
    """ARD: AND 結果空集合のとき CSV=None。"""
    _ensure_app()
    fake = _make_fake({"ard": ["1"]})

    csv, display = MainWindow._resolve_steps_for_workflow(fake, "ard", "2,4")

    assert csv is None
    assert display == set()


# ---------------------------------------------------------------------------
# Step 1 で全 OFF 状態のケース (理論上ありうる: enabled_by_wf に空 list)
# ---------------------------------------------------------------------------


def test_step1_empty_list_returns_none() -> None:
    """Step 1 でそのワークフローのステップを全 OFF にすると CSV=None。"""
    _ensure_app()
    fake = _make_fake({"aas": []})

    csv, display = MainWindow._resolve_steps_for_workflow(fake, "aas", None)

    assert csv is None
    assert display == set()
