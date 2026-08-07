"""T4: Prompt が TB-CAP を正しく指示しているかの契約テスト。

見出しレベルの罠（AR-CAP で偽 GREEN を起こした既知の欠陥）を
Prompt 側でも防いでいることを固定する。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_PROMPTS = Path(__file__).resolve().parents[2] / ".github" / "prompts"


def _text(name: str) -> str:
    path = _PROMPTS / f"{name}.prompt.md"
    assert path.exists(), f"{name}.prompt.md が存在しない"
    return path.read_text(encoding="utf-8")


class TestDesignPrompt:
    """Arch-AIAgentDesign-Step3 が TB-CAP-01〜05 を指示する。"""

    def test_declares_skill_dependency(self):
        assert "foundry-toolbox-contract" in _text("Arch-AIAgentDesign-Step3")

    @pytest.mark.parametrize(
        "heading",
        [
            "7.5.1 Tool Inventory (TB-CAP-01)",
            "7.5.2 Toolbox Decision (TB-CAP-02)",
            "7.5.3 Pinning Policy (TB-CAP-03)",
            "7.5.4 Search Metadata (TB-CAP-04)",
            "7.5.5 Discovery Budget (TB-CAP-05)",
        ],
    )
    def test_lists_all_five_headings(self, heading: str):
        assert heading in _text("Arch-AIAgentDesign-Step3")

    def test_states_the_counting_formula(self):
        """総数の数え方を指示していないと TB-CAP-01 が埋まらない。"""
        text = _text("Arch-AIAgentDesign-Step3")
        assert "Required: yes" in text
        assert "重複排除" in text

    def test_forbids_double_counting_routes(self):
        """同一経路の二重計上を禁止している（R1）。"""
        text = _text("Arch-AIAgentDesign-Step3")
        assert "同じ経路が複数行にあっても 1 と数える" in text

    def test_states_the_threshold(self):
        assert "15 を超える" in _text("Arch-AIAgentDesign-Step3")

    def test_requires_same_heading_level(self):
        """AR-CAP で偽 GREEN を起こした見出しレベルの罠を防ぐ。"""
        text = _text("Arch-AIAgentDesign-Step3")
        assert "見出しレベルは Section 7.0〜7.4 と同じレベルにする" in text
        assert "子レベルにしない" in text

    def test_completion_criteria_include_tb_cap(self):
        text = _text("Arch-AIAgentDesign-Step3")
        assert "TB-CAP-01〜05" in text.split("完了判定")[-1]


class TestDesignPromptPolicy:
    """FR-WF-AAG-01 / 02: 設計 Prompt が `auto` / `yes` / `no` を区別する。"""

    @pytest.mark.parametrize("policy", ["auto", "yes", "no"])
    def test_names_each_policy_value(self, policy: str):
        assert f"`{policy}`" in _text("Arch-AIAgentDesign-Step3")

    def test_yes_requires_tb_cap_regardless_of_tool_count(self):
        assert "Tool 総数に関係なく" in _text("Arch-AIAgentDesign-Step3")

    def test_no_requires_reasoned_na(self):
        """`no` でも判断の記録を残させる（空欄で消さない）。"""
        text = _text("Arch-AIAgentDesign-Step3")
        assert "理由付き N/A" in text or "理由・根拠・再判定条件" in text

    def test_rejects_unknown_policy(self):
        """3 値以外を既定へ丸めると利用者の指定が消える。"""
        assert "3 値以外" in _text("Arch-AIAgentDesign-Step3")

    def test_requires_tool_id_completeness(self):
        """行数だけ合って中身が欠けた TB-CAP-04 を防ぐ。"""
        assert "過不足なく" in _text("Arch-AIAgentDesign-Step3")

    def test_requires_pinned_column_consistency(self):
        assert "TB-CAP-03 の pin 一覧と一致" in _text("Arch-AIAgentDesign-Step3")


class TestCodingPrompt:
    """AgentCoding が TB-CAP の実装境界を持つ。"""

    def test_declares_skill_dependency(self):
        assert "foundry-toolbox-contract" in _text("Dev-Microservice-Azure-AgentCoding")

    def test_has_implementation_boundary_section(self):
        assert "TB-CAP実装境界" in _text("Dev-Microservice-Azure-AgentCoding")

    def test_forbids_hardcoding_toolbox_values(self):
        text = _text("Dev-Microservice-Azure-AgentCoding")
        assert "ハードコードしない" in text

    def test_forbids_wildcard_pin_when_search_enabled(self):
        """全 pin は tool search 無効化と等価（R6）。"""
        assert '`"*"` による全 Tool pin を実装しない' in _text(
            "Dev-Microservice-Azure-AgentCoding"
        )

    def test_requires_sdk_symbol_confirmation(self):
        """SDK シンボル名はブログと Learn で不一致のため実行時確認が必須。"""
        text = _text("Dev-Microservice-Azure-AgentCoding")
        assert "Microsoft Learn MCP" in text
        assert "推測しない" in text

    def test_requires_system_prompt_instruction(self):
        """tool_search を呼ばせる指示が無いとモデルが能力なしと誤判定する。"""
        assert "tool_search` を呼ぶ" in _text("Dev-Microservice-Azure-AgentCoding")


class TestDeployPrompt:
    """AgentDeploy が実 Toolbox と設計値の一致を検証する。"""

    def test_declares_skill_dependency(self):
        assert "foundry-toolbox-contract" in _text("Dev-Microservice-Azure-AgentDeploy")

    def test_has_verification_section(self):
        assert "## Toolbox 検証" in _text("Dev-Microservice-Azure-AgentDeploy")

    @pytest.mark.parametrize(
        "item", ["tool search", "pin", "limit", "version"]
    )
    def test_verifies_each_design_value(self, item: str):
        section = _text("Dev-Microservice-Azure-AgentDeploy").split("## Toolbox 検証")[-1]
        section = section.split("# 5)")[0]
        assert item in section, f"{item} の照合が無い"

    def test_states_drift_risk(self):
        """Toolbox は Agent コードを変えずに変更できるため乖離しやすい。"""
        section = _text("Dev-Microservice-Azure-AgentDeploy").split("## Toolbox 検証")[-1]
        assert "乖離" in section

    def test_states_preview_prerequisites(self):
        section = _text("Dev-Microservice-Azure-AgentDeploy").split("## Toolbox 検証")[-1]
        section = section.split("# 5)")[0]
        assert "Toolboxes=V1Preview" in section
        assert "Foundry User" in section

    def test_reads_values_from_agent_config(self):
        """script へ二重ハードコードすると config 更新が反映されない。"""
        text = _text("Dev-Microservice-Azure-AgentDeploy")
        assert "Agent config（`agent-config.json` / `appsettings.json`）を正本として読み取る" in text
        assert "二重にハードコードしない" in text

    @pytest.mark.parametrize(
        "variable", ["PINNED_TOOLS", "TOOL_SEARCH_LIMIT", "TOOLBOX_VERSION"]
    )
    def test_verify_expectations_are_injected(self, variable: str):
        assert variable in _text("Dev-Microservice-Azure-AgentDeploy")

    def test_verify_script_is_fail_closed(self):
        assert "fail-closed" in _text("Dev-Microservice-Azure-AgentDeploy")


class TestNoContradictionWithAgCap:
    """TB-CAP の追加が既存 AG-CAP の指示を壊していない。"""

    def test_twelve_section_schema_is_preserved(self):
        """12 セクションの番号・順序を変えない指示が残っている。"""
        text = _text("Arch-AIAgentDesign-Step3")
        assert text.count("12セクションの番号・順序は変えない") >= 2

    def test_ar_cap_instructions_remain(self):
        """AR-CAP の指示が消えていない。"""
        text = _text("Arch-AIAgentDesign-Step3")
        for heading in ("7.0.1 Knowledge Base Contract (AR-CAP-01)",):
            assert heading in text

    def test_tool_consolidation_is_still_forbidden(self):
        """Tool 統合禁止（AG-CAP-03）と矛盾していない。"""
        skill = (
            Path(__file__).resolve().parents[2]
            / ".github" / "skills" / "foundry-toolbox-contract" / "SKILL.md"
        )
        text = skill.read_text(encoding="utf-8")
        assert "統合を推奨しない" in text


class TestDeployCreatesToolbox:
    """T5: Toolbox の作成がデプロイスクリプト要件に含まれる。

    別 Step を新設せず既存の Deploy スクリプトへ組み込む方針のため、
    「作成される」ことをここで固定しないと配線が消えても気付けない。
    """

    @property
    def _text(self) -> str:
        return _text("Dev-Microservice-Azure-AgentDeploy")

    def _section(self, heading_prefix: str) -> str:
        """`## <prefix>` 見出しから次の `#` 見出しまでを取り出す。

        単純な split だと同じ文字列の最終出現を拾ってしまうため見出しで区切る。
        """
        pattern = re.compile(
            rf"^##\s+{re.escape(heading_prefix)}.*?$(.*?)(?=^#)",
            re.MULTILINE | re.DOTALL,
        )
        match = pattern.search(self._text)
        assert match, f"見出し '{heading_prefix}' が見つからない"
        return match.group(1)

    def test_creation_is_declared(self):
        assert "Toolbox の作成" in self._text

    def test_created_before_agent_registration(self):
        """Agent は toolbox エンドポイントを参照するため順序が重要。"""
        assert "Agent 登録の**前に**" in self._text

    def test_reflects_design_values_without_change(self):
        assert "設計値を変えない" in self._text

    def test_is_idempotent(self):
        assert "冪等" in self._section("create-azure-agent-resources.sh")

    def test_skipped_when_no_tb_cap(self):
        """TB-CAP が無い設計で toolbox を作らない（不要リソースを作らない）。"""
        assert "TB-CAP が無い設計では toolbox を作成しない" in self._text

    def test_verification_is_wired_into_verify_script(self):
        assert "tools/list" in self._section("verify-agent-resources.sh")


class TestSkillMatchesValidator:
    """Skill が要求するキー名と validator が読むキー名を一致させる。

    片方だけ変えると「Skill どおり書いたのに FAIL」という不可解な状態になる。
    """

    @property
    def _skill(self) -> str:
        return (
            Path(__file__).resolve().parents[2]
            / ".github" / "skills" / "foundry-toolbox-contract" / "SKILL.md"
        ).read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "column", ["Tool ID", "Pinned", "Additional search text"]
    )
    def test_tb_cap_04_required_columns_are_documented(self, column: str):
        """validator は 3 列で表を探す。Skill が列名を明示していないと書けない。"""
        assert f"`{column}`" in self._skill

    @pytest.mark.parametrize(
        "key",
        [
            "Total tools",
            "REST tools",
            "MCP allowlist tools",
            "Distinct search routes",
            "Counting source",
            "Tool search",
            "Connection topology",
            "Pinned tools",
            "Wildcard pin",
            "Expected tool_search calls per turn",
            "Overflow behavior",
        ],
    )
    def test_required_keys_are_documented(self, key: str):
        assert key in self._skill

    def test_validator_reads_the_documented_keys(self):
        """validator 側にも同じキー名が存在する（実装との突き合わせ）。"""
        src = (
            Path(__file__).resolve().parents[1] / "artifact_validation.py"
        ).read_text(encoding="utf-8")
        for key in (
            "Total tools",
            "REST tools",
            "MCP allowlist tools",
            "Distinct search routes",
            "Counting source",
            "Tool search",
            "Connection topology",
            "Pinned tools",
            "Wildcard pin",
            "Overflow behavior",
        ):
            assert f'"{key}"' in src, f"validator が {key} を読んでいない"

