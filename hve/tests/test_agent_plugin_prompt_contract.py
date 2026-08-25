"""Agent Plugins 準拠マニフェストの生成指示を Prompt へ固定する。

FR-WF-AAGD-06。
生成 Agent の実装 Prompt が `plugin.json` を成果物として宣言し、
仕様の固定値と命名規則を指示していることを確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

_PROMPTS = Path(__file__).resolve().parents[2] / ".github" / "prompts"
_PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


@pytest.fixture(scope="module")
def coding_prompt() -> str:
    return (_PROMPTS / "Dev-Microservice-Azure-AgentCoding.prompt.md").read_text(
        encoding="utf-8"
    )


class TestManifestOutput:
    def test_declares_plugin_json_as_an_output(self, coding_prompt: str):
        assert "src/agent/{key}/plugin.json" in coding_prompt

    def test_pins_the_canonical_schema_identifier(self, coding_prompt: str):
        assert _PLUGIN_SCHEMA in coding_prompt

    def test_requires_lowercasing_the_fanout_key(self, coding_prompt: str):
        assert "小文字化" in coding_prompt

    @pytest.mark.parametrize("field", ["`$schema`", "`name`", "`description`", "`version`"])
    def test_lists_every_generated_field(self, coding_prompt: str, field: str):
        assert field in coding_prompt


class TestManifestBoundaries:
    def test_forbids_hve_specific_top_level_fields(self, coding_prompt: str):
        assert "agent-config.json" in coding_prompt
        assert "closed schema" in coding_prompt

    def test_declares_mcp_json_as_a_conditional_output(self, coding_prompt: str):
        """AG-CAP-09 が採用したときだけ mcp.json を生成する条件付き成果物とする。"""
        assert "src/agent/{key}/mcp.json" in coding_prompt
        assert "Plugin components" in coding_prompt

    def test_forbids_inlining_mcp_config_into_the_manifest(self, coding_prompt: str):
        """仕様 §7.2.1: mcp.json は plugin root 固定で plugin.json へ書けない。"""
        assert "インライン記述しない" in coding_prompt

    def test_forbids_credentials_in_mcp_headers_and_env(self, coding_prompt: str):
        assert "資格情報の値を書かない" in coding_prompt
        assert "loopback 以外は HTTPS 必須" in coding_prompt
