"""hve.autopilot.plan_model — Autopilot 実行計画の dataclass 群（Qt 非依存コア）。

後方互換のため `hve.gui.autopilot.plan_model` 経由でも同じシンボルを参照可能。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple


_CHAIN_BY_KIND: dict = {
    "web-cloud": ("aad-web", "asdw-web"),
    "batch": ("adfd", "adfdv"),
}

_AUTOPILOT_SELECTABLE_WORKFLOWS = {
    "ard",
    "aas",
    "aad-web",
    "asdw-web",
    "adfd",
    "adfdv",
}


def chain_for_kind(kind: str) -> Tuple[str, ...]:
    return _CHAIN_BY_KIND.get(kind, tuple())


@dataclass(frozen=True)
class AutopilotSelection:
    """Autopilot 時の Workflow 選択状態。"""

    run_ard: bool = False
    run_aas: bool = False
    run_aad_web: bool = True
    run_asdw_web: bool = True
    run_abd: bool = True
    run_abdv: bool = True
    ignored_workflows: List[str] = field(default_factory=list)

    @classmethod
    def from_workflow_ids(cls, workflow_ids: List[str]) -> "AutopilotSelection":
        normalized = [w.strip().lower() for w in workflow_ids if isinstance(w, str) and w.strip()]
        selected = set(normalized)
        ignored = [w for w in normalized if w not in _AUTOPILOT_SELECTABLE_WORKFLOWS]
        return cls(
            run_ard="ard" in selected,
            run_aas="aas" in selected,
            run_aad_web="aad-web" in selected,
            run_asdw_web="asdw-web" in selected,
            run_abd="adfd" in selected,
            run_abdv="adfdv" in selected,
            ignored_workflows=ignored,
        )

    def has_downstream_workflows(self) -> bool:
        """AAS カタログを消費する後段 workflow が 1 つでも選択されているか。"""
        return any([
            self.run_aad_web,
            self.run_asdw_web,
            self.run_abd,
            self.run_abdv,
        ])

    def downstream_workflow_ids(self) -> List[str]:
        """選択されている downstream workflow_id を実行順で返す。

        フラグと workflow_id の対応関係はクラス内に閉じ込め、外部（GUI 側）が
        ハードコードで重複保持しないようにする
        (gui-workbench-autopilot-display レビュー #3)。
        """
        result: List[str] = []
        if self.run_aad_web:
            result.append("aad-web")
        if self.run_asdw_web:
            result.append("asdw-web")
        if self.run_abd:
            result.append("adfd")
        if self.run_abdv:
            result.append("adfdv")
        return result

    def _ard_aas_sequence(self) -> List[str]:
        """ARD / AAS の選択順（共通ヘルパ）。"""
        phases: List[str] = []
        if self.run_ard:
            phases.append("ard")
        if self.run_aas:
            phases.append("aas")
        return phases

    def pre_phases(self) -> List[str]:
        """事前位相の実行順。

        ARD/AAS は downstream workflow（aad-web/asdw-web/adfd/adfdv）が選択されて
        いる場合に限り「事前位相」となる。downstream 不在時は ARD/AAS 自体が
        メインワークフロー扱いとなるため、ここでは空 list を返す。
        """
        if not self.has_downstream_workflows():
            return []
        return self._ard_aas_sequence()

    def main_workflows(self) -> List[str]:
        """downstream 不在時に主タスクとして実行する ARD/AAS の実行順。

        downstream workflow が選択されている場合は ARD/AAS は pre_phases 側に
        分類されるため、ここでは空 list を返す。
        """
        if self.has_downstream_workflows():
            return []
        return self._ard_aas_sequence()


def default_selection() -> AutopilotSelection:
    """後方互換用の既定選択。"""
    return AutopilotSelection(
        run_ard=False,
        run_aas=False,
        run_aad_web=True,
        run_asdw_web=True,
        run_abd=True,
        run_abdv=True,
        ignored_workflows=[],
    )


@dataclass(frozen=True)
class AppChain:
    app_id: str
    architecture: str
    workflows: List[str]


@dataclass(frozen=True)
class SkippedApp:
    app_id: str
    architecture: str
    reason: str


@dataclass(frozen=True)
class AutopilotPlan:
    catalog_path: Path
    catalog_exists: bool
    requires_aas: bool
    app_chains: List[AppChain] = field(default_factory=list)
    skipped: List[SkippedApp] = field(default_factory=list)
    max_parallel: int = 4
    pre_phases: List[str] = field(default_factory=list)
    main_workflows: List[str] = field(default_factory=list)
    ignored_workflows: List[str] = field(default_factory=list)
    # T1: catalog 不在 / 空かつ ARD/AAS が pre_phases に存在する場合に True。
    # この場合 app_chains は空でも、pre_phases のみ実行 → 完了後に catalog を
    # 再読して downstream を再プランする「半自動継続」モードの対象となる。
    pre_phase_only: bool = False

    def is_empty(self) -> bool:
        return not self.app_chains

    def has_main_workflows(self) -> bool:
        """downstream 不在で ARD/AAS をメインタスクとして実行する計画か。"""
        return bool(self.main_workflows)

    def is_pre_phase_only(self) -> bool:
        """catalog 未生成のため pre_phases のみ先行実行する計画か（T1）。"""
        return self.pre_phase_only and bool(self.pre_phases) and not self.app_chains

    def needs_chain_continuation(self) -> bool:
        """pre_phases と app_chains が同時に非空で「直列連結実行」が必要か。

        ARD/AAS と downstream（aad-web 等）が同時選択され、かつ catalog が既に
        解決済み（app_chains 非空）のケース。pre_phase_only でも main_workflows
        でもない第 4 の経路として、pre_phases → app_chains を直列実行する。
        """
        return bool(self.pre_phases) and bool(self.app_chains) and not self.is_pre_phase_only()

    def execution_order(self) -> List[str]:
        """workflow ID を実行順に並べた list を返す（重複除去済み）。

        順序: pre_phases（ARD → AAS 等）→ app_chains 内の workflow（出現順、
        APP 単位で in-lane 直列。APP 間は並列のため序列の中では括らない）→
        main_workflows（downstream 不在時の ARD/AAS）。

        GUI Step1PlanReviewDialog の表示で「選択した workflow ≠ 実行順」の
        乖離を Step 1 段階で検出するために使用する。
        """
        seen: set = set()
        order: List[str] = []
        for wf in list(self.pre_phases) + list(self.main_workflows):
            if wf and wf not in seen:
                seen.add(wf)
                order.append(wf)
        for chain in self.app_chains:
            for wf in chain.workflows:
                if wf and wf not in seen:
                    seen.add(wf)
                    order.append(wf)
        return order
