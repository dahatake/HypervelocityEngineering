"""P7 / C4: Agentic Retrieval 実装ゲートの end-to-end 配線テスト。

背景:
    `test_agentic_retrieval_contract_validation.py::TestAgenticRetrievalImplementationGate`
    は `_validate_agentic_retrieval_implementation()` を**直接**呼ぶ単体テストである。
    そのため、公開エントリポイント `validate_ai_agent_implementation_artifacts()` から
    AR-CAP 検証へ至るフック（`hve/artifact_validation.py` 内の呼び出し）が
    削除・破損しても、既存テストは全て PASS してしまう。

    本モジュールは実ファイル（設計書 + agent ディレクトリ + テスト仕様）を
    tmp_path 上に構築し、公開エントリポイント経由で AR-CAP 違反が検出されることを
    固定する。フックが外れれば `test_hook_is_wired_*` が失敗する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hve.artifact_validation import validate_ai_agent_implementation_artifacts
from hve.tests.test_agentic_retrieval_contract_validation import (
    _ar_cap_01,
    _ar_cap_02,
    _ar_cap_03,
    _ar_cap_04,
    _ar_cap_05,
    _design,
)
from hve.tests.test_ai_agent_capability_validation import (
    _write_design,
    _write_implementation,
)

_KB_NAME = "policy-kb"
_KS_NAMES = ["policy-docs", "public-news"]
_ALLOWED_TOOL = "knowledge_base_retrieve"


def _ar_errors(errors: list[str]) -> list[str]:
    return [e for e in errors if "AR-CAP" in e]


def _build_agentic_design(root: Path) -> Path:
    """AR 経路が選択された設計書を、実装ゲートが探す既定パスへ書き出す。"""
    path = _write_design(root)  # ディレクトリ構造と既定パスを流用
    path.write_text(_design(), encoding="utf-8")
    return path


def _apply_agentic_implementation(
    agent_dir: Path,
    *,
    kb_name: str = _KB_NAME,
    effort: str = "low",
    knowledge_sources: list[str] | None = None,
    tool_allowlist: list[str] | None = None,
    retrieve_source: str | None = None,
) -> None:
    """agent ディレクトリを AR-CAP 契約に整合する内容へ更新する。"""
    config_path = agent_dir / "agent-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["knowledge_base"] = {
        "name": kb_name,
        "retrieval_reasoning_effort": effort,
        "knowledge_sources": list(
            _KS_NAMES if knowledge_sources is None else knowledge_sources
        ),
    }
    config["mcp_servers"] = [
        {
            "server_label": "knowledge-base",
            "tool_allowlist": list(
                [_ALLOWED_TOOL] if tool_allowlist is None else tool_allowlist
            ),
        }
    ]
    config_path.write_text(json.dumps(config), encoding="utf-8")

    source = (
        retrieve_source
        if retrieve_source is not None
        else f"\n\ndef retrieve(query):\n    return call_tool('{_ALLOWED_TOOL}', query)\n"
    )
    agent_py = agent_dir / "agent.py"
    agent_py.write_text(
        agent_py.read_text(encoding="utf-8") + source, encoding="utf-8"
    )


@pytest.fixture
def agentic_project(tmp_path: Path):
    """AR 経路が選択され、実装も整合している状態の一式を返す。"""
    design = _build_agentic_design(tmp_path)
    agent_dir, test_spec = _write_implementation(tmp_path)
    _apply_agentic_implementation(agent_dir)
    return design, agent_dir, test_spec


class TestHookIsWired:
    """公開エントリポイントから AR-CAP 検証へ到達することを固定する。"""

    def test_aligned_implementation_has_no_agentic_errors(self, agentic_project):
        design, agent_dir, test_spec = agentic_project
        errors = validate_ai_agent_implementation_artifacts(design, agent_dir, test_spec)
        assert _ar_errors(errors) == [], (
            "整合した実装が AR-CAP 違反として報告された: " + "; ".join(_ar_errors(errors))
        )

    def test_hook_is_wired_for_knowledge_base_name(self, agentic_project):
        """設定の KB 名が設計と食い違えば、公開エントリポイントが検出する。"""
        design, agent_dir, test_spec = agentic_project
        _apply_agentic_implementation(agent_dir, kb_name="unrelated-kb")
        errors = validate_ai_agent_implementation_artifacts(design, agent_dir, test_spec)
        assert _ar_errors(errors), (
            "AR-CAP-01 の不一致が公開エントリポイント経由で検出されない"
            "（validate_ai_agent_implementation_artifacts のフックが外れている可能性）"
        )

    def test_hook_is_wired_for_reasoning_effort(self, agentic_project):
        design, agent_dir, test_spec = agentic_project
        _apply_agentic_implementation(agent_dir, effort="medium")
        errors = validate_ai_agent_implementation_artifacts(design, agent_dir, test_spec)
        assert _ar_errors(errors), "AR-CAP-01 の reasoning effort 不一致が検出されない"

    def test_hook_is_wired_for_knowledge_sources(self, agentic_project):
        design, agent_dir, test_spec = agentic_project
        _apply_agentic_implementation(agent_dir, knowledge_sources=["policy-docs"])
        errors = validate_ai_agent_implementation_artifacts(design, agent_dir, test_spec)
        assert _ar_errors(errors), "AR-CAP-02 の Knowledge Source 欠落が検出されない"

    def test_hook_is_wired_for_mcp_tool_allowlist(self, agentic_project):
        """Foundry Agent Service で許可されないツールを足すと検出される。"""
        design, agent_dir, test_spec = agentic_project
        _apply_agentic_implementation(
            agent_dir, tool_allowlist=[_ALLOWED_TOOL, "list_indexes"]
        )
        errors = validate_ai_agent_implementation_artifacts(design, agent_dir, test_spec)
        assert _ar_errors(errors), "AR-CAP-05 の許可外ツールが検出されない"


class TestGatingAtEntryPoint:
    """AR 経路が選択されていない設計では AR-CAP 検証を強制しない。"""

    def test_non_agentic_design_is_not_gated(self, tmp_path: Path):
        design = _write_design(tmp_path)  # 既定は Foundry IQ 経路を含まない
        agent_dir, test_spec = _write_implementation(tmp_path)
        errors = validate_ai_agent_implementation_artifacts(design, agent_dir, test_spec)
        assert _ar_errors(errors) == [], (
            "AR 経路を選んでいない設計に AR-CAP 契約が強制されている"
        )

    def test_gating_is_not_tautological(self, tmp_path: Path):
        """AR 経路を選ぶと、KB 設定が無い実装は必ず失敗する（陰性対照）。

        この確認により `test_non_agentic_design_is_not_gated` の PASS が
        「そもそも AR 検証が動いていない」ことに由来しないと言える。
        """
        design = _build_agentic_design(tmp_path)
        agent_dir, test_spec = _write_implementation(tmp_path)
        # knowledge_base を設定しないまま検証する
        errors = validate_ai_agent_implementation_artifacts(design, agent_dir, test_spec)
        assert _ar_errors(errors), (
            "AR 経路選択時に KB 未設定の実装が素通りしている"
        )


class TestDesignPrerequisitePropagates:
    """設計書側の AR-CAP 違反が実装ゲートでも前提エラーとして現れる。"""

    def test_design_violation_surfaces_through_implementation_gate(self, tmp_path: Path):
        # minimal + answerSynthesis は Learn 上両立しない（R2 違反）
        broken = _design(
            ar_blocks=(
                _ar_cap_01(effort="minimal", output_mode="answerSynthesis")
                + "\n" + _ar_cap_02()
                + "\n" + _ar_cap_03()
                + "\n" + _ar_cap_04()
                + "\n" + _ar_cap_05()
            )
        )
        design = _write_design(tmp_path)
        design.write_text(broken, encoding="utf-8")
        agent_dir, test_spec = _write_implementation(tmp_path)
        _apply_agentic_implementation(agent_dir)
        errors = validate_ai_agent_implementation_artifacts(design, agent_dir, test_spec)
        assert any("AAGD design prerequisite" in e for e in errors), (
            "設計書の AR-CAP 違反が実装ゲートの前提エラーとして伝播していない"
        )
