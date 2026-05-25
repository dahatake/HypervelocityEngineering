"""hve.autopilot.planner — `app-arch-catalog.md` から実行計画を生成する（Qt 非依存コア）。

後方互換のため `hve.gui.autopilot.planner` 経由でも同じシンボルを参照可能。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from hve.app_arch_filter import classify_architecture, parse_catalog

from .plan_model import (
    AppChain,
    AutopilotPlan,
    AutopilotSelection,
    SkippedApp,
    chain_for_kind,
    default_selection,
)


_DEFAULT_CATALOG_RELPATH = Path("docs") / "catalog" / "app-arch-catalog.md"


def default_catalog_path(repo_root: Path) -> Path:
    return repo_root / _DEFAULT_CATALOG_RELPATH


def _empty_plan(
    catalog_path: Path,
    *,
    exists: bool,
    requires_aas: bool,
    max_parallel: int,
    pre_phases: Optional[List[str]] = None,
    main_workflows: Optional[List[str]] = None,
    ignored_workflows: Optional[List[str]] = None,
    pre_phase_only: bool = False,
) -> AutopilotPlan:
    return AutopilotPlan(
        catalog_path=catalog_path,
        catalog_exists=exists,
        requires_aas=requires_aas,
        app_chains=[],
        skipped=[],
        max_parallel=max_parallel,
        pre_phases=list(pre_phases or []),
        main_workflows=list(main_workflows or []),
        ignored_workflows=list(ignored_workflows or []),
        pre_phase_only=pre_phase_only,
    )


def _filter_chain_by_selection(chain: List[str], selection: AutopilotSelection) -> List[str]:
    allowed = {
        "aad-web": selection.run_aad_web,
        "asdw-web": selection.run_asdw_web,
        "adfd": selection.run_abd,
        "adfdv": selection.run_abdv,
    }
    return [wf for wf in chain if allowed.get(wf, False)]


def _requires_aas(selection: AutopilotSelection, *, catalog_resolved: bool) -> bool:
    if catalog_resolved:
        return False
    return selection.has_downstream_workflows() and not selection.run_aas


def build_plan(
    catalog_path: Path,
    max_parallel: int = 4,
    *,
    selection: Optional[AutopilotSelection] = None,
    requested_app_ids: Optional[List[str]] = None,
) -> AutopilotPlan:
    """カタログから Autopilot 実行計画を生成する。

    - カタログ不在 → requires_aas=True の空計画
    - パース失敗 → requires_aas=True の空計画
    - サマリ表が空 → requires_aas=True の空計画
    - 未マッピング → SkippedApp として記録

    Args:
        requested_app_ids: ユーザーが明示指定した APP-ID のリスト。
            None / 空のとき catalog 全件を対象とする（後方互換）。
            指定時は catalog 内の対象を当該 ID に限定し、catalog に存在しない
            ID は ``SkippedApp(reason="unknown app_id (not in catalog)")`` として
            記録する。architecture / workflow 不一致でフィルタ落ちする ID は
            従来通り ``SkippedApp(reason="unmapped architecture or filtered by
            selection")`` として記録される。

            比較は大文字小文字を正規化（`.upper()`）して行うため、`app-01` と
            `APP-01` は同一視される（catalog 側 APP-ID は大文字想定）。

            ``catalog_path`` 不在 / パース失敗等で `_empty_plan` 早期 return する
            経路では、unknown_ids の skipped 登録は行われない（catalog 解決前は
            検証材料がないため）。
    """
    requested_set: Optional[set] = None
    if requested_app_ids:
        # 大文字正規化して比較（catalog 側 APP-ID は大文字 "APP-NN" 想定）。
        requested_set = {
            aid.strip().upper()
            for aid in requested_app_ids
            if aid and aid.strip()
        }
        if not requested_set:
            requested_set = None
    catalog_path = Path(catalog_path)
    sel = selection or default_selection()
    pre_phases = sel.pre_phases()
    main_workflows = sel.main_workflows()
    capped_parallel = max(1, min(16, int(max_parallel)))

    # T1: catalog 不在 / 空でも pre_phases に ARD/AAS があれば pre_phase_only モード
    # （ARD/AAS の出力で catalog が生成されるため、先行実行可とみなす）。
    pre_phase_only = bool(pre_phases) and sel.has_downstream_workflows()

    if not catalog_path.exists():
        return _empty_plan(
            catalog_path,
            exists=False,
            requires_aas=_requires_aas(sel, catalog_resolved=False),
            max_parallel=capped_parallel,
            pre_phases=pre_phases,
            main_workflows=main_workflows,
            ignored_workflows=sel.ignored_workflows,
            pre_phase_only=pre_phase_only,
        )

    catalog_resolved = False
    try:
        catalog = parse_catalog(str(catalog_path))
        catalog_resolved = len(catalog) > 0
    except (FileNotFoundError, ValueError):
        catalog = {}

    if not catalog:
        return _empty_plan(
            catalog_path,
            exists=True,
            requires_aas=_requires_aas(sel, catalog_resolved=False),
            max_parallel=capped_parallel,
            pre_phases=pre_phases,
            main_workflows=main_workflows,
            ignored_workflows=sel.ignored_workflows,
            pre_phase_only=pre_phase_only,
        )

    chains: List[AppChain] = []
    skipped: List[SkippedApp] = []
    for app_id, arch in catalog.items():
        if requested_set is not None and app_id.upper() not in requested_set:
            # ユーザーが明示指定した APP-ID 以外は計画から除外（skipped にも残さない）。
            continue
        kind = classify_architecture(arch)
        wf_chain = list(chain_for_kind(kind)) if kind else []
        wf_chain = _filter_chain_by_selection(wf_chain, sel)
        if wf_chain:
            chains.append(AppChain(app_id=app_id, architecture=arch,
                                   workflows=wf_chain))
        else:
            skipped.append(SkippedApp(app_id=app_id, architecture=arch,
                                      reason="unmapped architecture or filtered by selection"))

    # catalog に存在しない指定 APP-ID を skipped に追記（タイプミス検出用）。
    if requested_set is not None:
        catalog_ids_upper = {k.upper() for k in catalog.keys()}
        unknown_ids = sorted(requested_set - catalog_ids_upper)
        for aid in unknown_ids:
            skipped.append(SkippedApp(
                app_id=aid,
                architecture="",
                reason="unknown app_id (not in catalog)",
            ))

    # catalog が解決され app_chains が 1 件でもあれば pre_phase_only は不要。
    # app_chains が 0 件（全 APP が selection でフィルタ落ち）かつ pre_phases
    # ありの場合のみ pre_phase_only=True とする。
    final_pre_phase_only = pre_phase_only and not chains
    return AutopilotPlan(
        catalog_path=catalog_path,
        catalog_exists=True,
        requires_aas=_requires_aas(sel, catalog_resolved=catalog_resolved),
        app_chains=chains,
        skipped=skipped,
        max_parallel=capped_parallel,
        pre_phases=pre_phases,
        main_workflows=main_workflows,
        ignored_workflows=list(sel.ignored_workflows),
        pre_phase_only=final_pre_phase_only,
    )
