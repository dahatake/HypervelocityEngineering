"""FR-WF-ARD-01: ARD を CLI / GUI Orchestrator 専用と確定する契約テスト。

§12 TBD-06 の設計判断を固定する。ARD の Cloud 対応を追加するには専用の
Issue Template・state-transition・`auto-ard-reusable.yml` の新規作成（30+ ファイル
規模）が必要である一方、FR-CLOUD-06 では ASDW-WEB を Cloud dispatch から
**削除** しており、Cloud 対象ワークフローを増やす方向とは逆行する。
本テストは「ARD が Cloud 起動経路へ紛れ込まないこと」を CI で固定する。
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_DISPATCHER = _WORKFLOWS_DIR / "auto-orchestrator-dispatcher.yml"
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"


def _dispatcher_text() -> str:
    return _DISPATCHER.read_text(encoding="utf-8")


def _mapping_block(text: str, name: str, opener: str, closer: str) -> str:
    start = text.index(f"{name} = {opener}")
    return text[start : text.index(closer, start) + 1]


def test_dispatcher_trigger_map_does_not_register_ard() -> None:
    """`trigger_map` に ARD を登録しない。"""
    block = _mapping_block(_dispatcher_text(), "trigger_map", "[", "]")

    assert not re.search(r"'ARD'", block), (
        "ARD は CLI / GUI 専用（FR-WF-ARD-01）。dispatcher の trigger_map へ"
        f" 登録してはならない:\n{block}"
    )


def test_dispatcher_done_map_does_not_register_ard() -> None:
    """`done_map` に ARD を登録しない。"""
    block = _mapping_block(_dispatcher_text(), "done_map", "{", "}")

    assert "ard:done" not in block and "'ARD'" not in block, (
        f"ARD は CLI / GUI 専用（FR-WF-ARD-01）:\n{block}"
    )


def test_no_ard_reusable_workflow_exists() -> None:
    """ARD 専用の reusable workflow を新設しない。"""
    candidates = sorted(
        p.name
        for p in _WORKFLOWS_DIR.glob("*.yml")
        if re.search(r"(^|[-_])ard([-_]|\.)", p.name, re.IGNORECASE)
    )

    assert candidates == [], (
        "ARD 専用 reusable workflow は FR-WF-ARD-01 により作成しない: "
        f"{candidates}"
    )


def test_dispatcher_does_not_reference_ard_workflow() -> None:
    """dispatcher が ARD の reusable workflow を `uses` しない。"""
    uses = re.findall(r"uses:\s*(\S+)", _dispatcher_text())

    offenders = [u for u in uses if re.search(r"ard", u, re.IGNORECASE)]

    assert offenders == [], f"ARD の Cloud 起動経路が存在する: {offenders}"


def test_requirement_definition_declares_ard_as_cli_gui_only() -> None:
    """要件定義が ARD を CLI / GUI 専用と明記し、TBD-06 を解消済みとする。"""
    text = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8")

    assert "FR-WF-ARD-01" in text
    assert "CLI / GUI Orchestrator 専用" in text
    assert re.search(r"\|\s*TBD-06\s*\|\s*~~", text), (
        "TBD-06 が解消済み（打ち消し線）として記載されていない"
    )


@pytest.mark.parametrize("target", ("AAS", "AAD-WEB", "ADFD", "ADFDV", "AAG", "AAGD", "ADOC", "AKM"))
def test_other_cloud_targets_are_unchanged(target: str) -> None:
    """ARD 除外が他の Cloud 対象ワークフローに影響しないこと。"""
    block = _mapping_block(_dispatcher_text(), "trigger_map", "[", "]")

    assert f"'{target}'" in block, f"{target} の Cloud 起動経路が失われている"
