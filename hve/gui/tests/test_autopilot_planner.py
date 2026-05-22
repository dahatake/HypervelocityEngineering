from __future__ import annotations

from pathlib import Path

from hve.gui.autopilot.plan_model import AutopilotSelection
from hve.gui.autopilot.planner import build_plan


def _write_catalog(path: Path, rows: list[tuple[str, str]]) -> None:
    lines = [
        "# Application Architecture Catalog",
        "",
        "## A) サマリ表（全APP横断）",
        "",
        "| APP-ID | APP名 | 推薦アーキテクチャ |",
        "|---|---|---|",
    ]
    for app_id, arch in rows:
        lines.append(f"| {app_id} | sample | {arch} |")
    path.write_text("\n".join(lines), encoding="utf-8")


def test_build_plan_selection_web_only_first_stage(tmp_path: Path) -> None:
    p = tmp_path / "catalog.md"
    _write_catalog(
        p,
        [
            ("APP-001", "Webフロントエンド + クラウド"),
            ("APP-002", "データデータフロー処理"),
        ],
    )
    selection = AutopilotSelection(
        run_ard=False,
        run_aas=False,
        run_aad_web=True,
        run_asdw_web=False,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.pre_phases == []
    assert plan.requires_aas is False
    assert [c.workflows for c in plan.app_chains] == [["aad-web"]]


def test_build_plan_selection_with_ard_and_aas_prephases(tmp_path: Path) -> None:
    p = tmp_path / "catalog.md"
    _write_catalog(p, [("APP-001", "Webフロントエンド + クラウド")])
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=True,
        run_aad_web=True,
        run_asdw_web=True,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.pre_phases == ["ard", "aas"]
    assert plan.main_workflows == []
    assert plan.requires_aas is False


def test_build_plan_missing_catalog_no_downstream_does_not_require_aas(tmp_path: Path) -> None:
    p = tmp_path / "missing.md"
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=False,
        run_aad_web=False,
        run_asdw_web=False,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.catalog_exists is False
    # downstream 不在のため ARD は main_workflows へ分類される（事前位相ではない）
    assert plan.pre_phases == []
    assert plan.main_workflows == ["ard"]
    assert plan.has_main_workflows() is True
    assert plan.requires_aas is False


def test_build_plan_missing_catalog_ard_aas_only_routed_to_main_workflows(tmp_path: Path) -> None:
    """ARD/AAS のみ選択（downstream 不在）時は main_workflows に分類される。"""
    p = tmp_path / "missing.md"
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=True,
        run_aad_web=False,
        run_asdw_web=False,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.pre_phases == []
    assert plan.main_workflows == ["ard", "aas"]
    assert plan.has_main_workflows() is True
    assert plan.requires_aas is False


def test_build_plan_missing_catalog_downstream_with_selected_aas_no_extra_requirement(tmp_path: Path) -> None:
    p = tmp_path / "missing.md"
    selection = AutopilotSelection(
        run_ard=False,
        run_aas=True,
        run_aad_web=True,
        run_asdw_web=True,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.catalog_exists is False
    assert plan.pre_phases == ["aas"]
    assert plan.requires_aas is False


# ---------------------------------------------------------------------------
# T1: pre_phase_only モード（catalog 不在/空＋downstream選択時の事前位相先行実行）
# ---------------------------------------------------------------------------


def test_pre_phase_only_when_catalog_missing_with_downstream(tmp_path: Path) -> None:
    """catalog 不在 ＋ ARD/AAS と downstream を同時選択 → pre_phase_only=True。"""
    p = tmp_path / "missing.md"
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=True,
        run_aad_web=True,
        run_asdw_web=True,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.catalog_exists is False
    assert plan.app_chains == []
    assert plan.pre_phases == ["ard", "aas"]
    assert plan.pre_phase_only is True
    assert plan.is_pre_phase_only() is True


def test_pre_phase_only_false_when_no_downstream(tmp_path: Path) -> None:
    """downstream 未選択時は pre_phase_only にはならない（ARD/AAS が main_workflows へ）。"""
    p = tmp_path / "missing.md"
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=True,
        run_aad_web=False,
        run_asdw_web=False,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.pre_phase_only is False
    assert plan.is_pre_phase_only() is False
    assert plan.main_workflows == ["ard", "aas"]


def test_pre_phase_only_when_catalog_empty_with_downstream(tmp_path: Path) -> None:
    """catalog 存在するがサマリ表が空 ＋ downstream 選択 → pre_phase_only=True。"""
    p = tmp_path / "empty.md"
    p.write_text("# empty catalog\n", encoding="utf-8")
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=True,
        run_aad_web=True,
        run_asdw_web=True,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.catalog_exists is True
    assert plan.app_chains == []
    assert plan.pre_phase_only is True
    assert plan.is_pre_phase_only() is True


def test_pre_phase_only_false_when_app_chains_resolved(tmp_path: Path) -> None:
    """catalog から APP が解決されれば pre_phase_only=False。

    注: app_chains 解決時に pre_phases が無視されることは意味しない。
    pre_phases が同時に非空の場合は `needs_chain_continuation()` 経由で
    連結実行される（GUI フロー側の責務、test_needs_chain_continuation_* 参照）。
    """
    p = tmp_path / "catalog.md"
    _write_catalog(p, [("APP-001", "Webフロントエンド + クラウド")])
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=True,
        run_aad_web=True,
        run_asdw_web=True,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert len(plan.app_chains) >= 1
    assert plan.pre_phase_only is False
    assert plan.is_pre_phase_only() is False


def test_pre_phase_only_when_all_apps_filtered_out(tmp_path: Path) -> None:
    """catalog に batch APP のみ／選択は web downstream のみ → 全 APP フィルタ落ち → pre_phase_only=True。"""
    p = tmp_path / "catalog.md"
    _write_catalog(p, [("APP-001", "データデータフロー処理")])
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=True,
        run_aad_web=True,
        run_asdw_web=True,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.app_chains == []
    assert plan.pre_phases == ["ard", "aas"]
    assert plan.pre_phase_only is True
    assert plan.is_pre_phase_only() is True


# ---------------------------------------------------------------------------
# T_chain: pre_phases + app_chains 同時非空時の連結経路（直列実行 DAG バグ修正）
# ---------------------------------------------------------------------------


def test_needs_chain_continuation_when_pre_phases_and_app_chains_coexist(
    tmp_path: Path,
) -> None:
    """ARD+AAS+AAD-WEB+ASDW-WEB 選択 ＋ catalog 解決済み →
    pre_phases と app_chains が同時に非空となり needs_chain_continuation()=True。

    バグ修正前: この状態でも GUI は AutopilotController に直接遷移し
    pre_phases（ARD/AAS）が無視されていた。
    """
    p = tmp_path / "catalog.md"
    _write_catalog(p, [("APP-001", "Webフロントエンド + クラウド")])
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=True,
        run_aad_web=True,
        run_asdw_web=True,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.pre_phases == ["ard", "aas"]
    assert len(plan.app_chains) >= 1
    assert plan.is_pre_phase_only() is False
    assert plan.has_main_workflows() is False
    assert plan.is_empty() is False
    assert plan.needs_chain_continuation() is True


def test_needs_chain_continuation_false_when_only_app_chains(
    tmp_path: Path,
) -> None:
    """downstream のみ選択（ARD/AAS 未選択）→ needs_chain_continuation()=False。"""
    p = tmp_path / "catalog.md"
    _write_catalog(p, [("APP-001", "Webフロントエンド + クラウド")])
    selection = AutopilotSelection(
        run_ard=False,
        run_aas=False,
        run_aad_web=True,
        run_asdw_web=True,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.pre_phases == []
    assert len(plan.app_chains) >= 1
    assert plan.needs_chain_continuation() is False


def test_needs_chain_continuation_false_when_pre_phase_only(
    tmp_path: Path,
) -> None:
    """catalog 不在 → pre_phase_only=True、needs_chain_continuation()=False（排他）。"""
    p = tmp_path / "missing.md"
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=True,
        run_aad_web=True,
        run_asdw_web=True,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.is_pre_phase_only() is True
    assert plan.needs_chain_continuation() is False


def test_needs_chain_continuation_false_when_main_workflows(
    tmp_path: Path,
) -> None:
    """downstream 未選択で ARD/AAS のみ → main_workflows、needs_chain_continuation()=False。"""
    p = tmp_path / "catalog.md"
    _write_catalog(p, [("APP-001", "Webフロントエンド + クラウド")])
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=True,
        run_aad_web=False,
        run_asdw_web=False,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.has_main_workflows() is True
    assert plan.needs_chain_continuation() is False


def test_execution_order_pre_phases_then_app_chains(tmp_path: Path) -> None:
    """連結経路: ARD+AAS+AAD-WEB+ASDW-WEB 選択時、execution_order が
    [ard, aas, aad-web, asdw-web] の順で返る。"""
    p = tmp_path / "catalog.md"
    _write_catalog(p, [("APP-001", "Webフロントエンド + クラウド")])
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=True,
        run_aad_web=True,
        run_asdw_web=True,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.execution_order() == ["ard", "aas", "aad-web", "asdw-web"]


def test_execution_order_app_chains_only(tmp_path: Path) -> None:
    """downstream のみ選択時、execution_order は app_chains 順のみ。"""
    p = tmp_path / "catalog.md"
    _write_catalog(p, [("APP-001", "Webフロントエンド + クラウド")])
    selection = AutopilotSelection(
        run_ard=False,
        run_aas=False,
        run_aad_web=True,
        run_asdw_web=True,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.execution_order() == ["aad-web", "asdw-web"]


def test_execution_order_main_workflows_only(tmp_path: Path) -> None:
    """downstream 未選択 ＋ ARD/AAS のみ → main_workflows 順。"""
    p = tmp_path / "catalog.md"
    _write_catalog(p, [("APP-001", "Webフロントエンド + クラウド")])
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=True,
        run_aad_web=False,
        run_asdw_web=False,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    assert plan.execution_order() == ["ard", "aas"]


def test_execution_order_dedup_across_apps(tmp_path: Path) -> None:
    """複数 APP で同じ workflow が登場する場合は execution_order で重複除去される。"""
    p = tmp_path / "catalog.md"
    _write_catalog(
        p,
        [
            ("APP-001", "Webフロントエンド + クラウド"),
            ("APP-002", "Webフロントエンド + クラウド"),
        ],
    )
    selection = AutopilotSelection(
        run_ard=True,
        run_aas=True,
        run_aad_web=True,
        run_asdw_web=True,
        run_abd=False,
        run_abdv=False,
    )
    plan = build_plan(p, selection=selection)

    order = plan.execution_order()
    assert order == ["ard", "aas", "aad-web", "asdw-web"]
    assert len(order) == len(set(order))