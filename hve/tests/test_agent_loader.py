"""Tests for hve/agent_loader.py (Phase B / Critical No.1)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from hve.agent_loader import (
    load_agent_definitions,
    merge_with_explicit,
    parse_agent_file,
)


_VALID_AGENT_MD = textwrap.dedent(
    """\
    ---
    name: TestAgent
    description: テスト用エージェント。when used for unit testing only.
    tools: ['read', 'edit']
    metadata:
      version: "1.0.0"
    ---

    ## 1) 目的
    - テスト

    ## 4) Prompt 本文（LLM へ渡す本体）
    ```text
    You are TestAgent.
    Do exactly as instructed.
    ```

    ## 5) その他
    無視されるべき本文。
    """
)


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


class TestParseAgentFile:
    def test_parses_valid_agent(self, tmp_path: Path):
        f = _write(tmp_path / "TestAgent.agent.md", _VALID_AGENT_MD)
        agent = parse_agent_file(f)
        assert agent is not None
        assert agent["name"] == "TestAgent"
        assert agent["display_name"] == "TestAgent"
        assert "テスト用エージェント" in agent["description"]
        assert agent["tools"] == ["read", "edit"]
        assert agent["prompt"].startswith("You are TestAgent.")
        assert "Do exactly as instructed." in agent["prompt"]
        # section 5 の本文が prompt に混入しないこと
        assert "無視されるべき本文" not in agent["prompt"]

    def test_returns_none_when_no_frontmatter(self, tmp_path: Path):
        f = _write(tmp_path / "no_fm.agent.md", "## 4) Prompt 本文\n```text\nx\n```\n")
        assert parse_agent_file(f) is None

    def test_returns_none_when_name_missing(self, tmp_path: Path):
        body = textwrap.dedent(
            """\
            ---
            description: name 欠落のテスト
            ---

            ## 4) Prompt 本文
            ```text
            x
            ```
            """
        )
        f = _write(tmp_path / "no_name.agent.md", body)
        assert parse_agent_file(f) is None

    def test_falls_back_to_full_body_when_no_prompt_section(self, tmp_path: Path):
        body = textwrap.dedent(
            """\
            ---
            name: NoPromptSection
            description: prompt section が無い場合のフォールバック検証用ファイル。
            ---

            ## 1) 目的
            本文全体を prompt として扱う。
            """
        )
        f = _write(tmp_path / "nps.agent.md", body)
        agent = parse_agent_file(f)
        assert agent is not None
        assert "本文全体を prompt として扱う" in agent["prompt"]


class TestLoadAgentDefinitions:
    def test_loads_all_agents_in_dir(self, tmp_path: Path):
        _write(tmp_path / "A.agent.md", _VALID_AGENT_MD.replace("TestAgent", "AgentA"))
        _write(tmp_path / "B.agent.md", _VALID_AGENT_MD.replace("TestAgent", "AgentB"))
        agents = load_agent_definitions(tmp_path)
        names = sorted(a["name"] for a in agents)
        assert names == ["AgentA", "AgentB"]

    def test_returns_empty_when_dir_missing(self, tmp_path: Path):
        assert load_agent_definitions(tmp_path / "nonexistent") == []

    def test_skips_invalid_files_silently(self, tmp_path: Path):
        _write(tmp_path / "good.agent.md", _VALID_AGENT_MD)
        _write(tmp_path / "broken.agent.md", "no frontmatter here\n")
        agents = load_agent_definitions(tmp_path)
        assert [a["name"] for a in agents] == ["TestAgent"]

    def test_first_wins_on_duplicate_names(self, tmp_path: Path):
        _write(tmp_path / "a_first.agent.md", _VALID_AGENT_MD)
        _write(tmp_path / "z_second.agent.md", _VALID_AGENT_MD)
        agents = load_agent_definitions(tmp_path)
        assert len(agents) == 1


class TestMergeWithExplicit:
    def test_explicit_takes_priority(self):
        explicit = [
            {"name": "Foo", "prompt": "explicit prompt", "tools": ["*"]},
        ]
        file_based = [
            {"name": "Foo", "prompt": "file prompt", "tools": ["read"]},
            {"name": "Bar", "prompt": "bar prompt", "tools": ["read"]},
        ]
        merged = merge_with_explicit(explicit, file_based)
        assert len(merged) == 2
        foo = next(a for a in merged if a["name"] == "Foo")
        assert foo["prompt"] == "explicit prompt"
        assert {a["name"] for a in merged} == {"Foo", "Bar"}

    def test_empty_explicit(self):
        file_based = [{"name": "Bar", "prompt": "p", "tools": ["read"]}]
        merged = merge_with_explicit([], file_based)
        assert merged == file_based


class TestRepoAgents:
    """リポジトリ実体の `.github/agents/` を読み込めることを保証する統合テスト。"""

    def test_repo_agents_dir_loads_untargeted_agent(self):
        repo_root = Path(__file__).resolve().parents[2]
        agents_dir = repo_root / ".github" / "agents"
        if not agents_dir.is_dir():
            pytest.skip(".github/agents directory not present in test env")

        agents = load_agent_definitions(agents_dir)
        names = {a["name"] for a in agents}
        assert "Arch-ARD-BusinessAnalysis-Untargeted" in names

        untargeted = next(
            a for a in agents if a["name"] == "Arch-ARD-BusinessAnalysis-Untargeted"
        )
        # Phase A で Prompt 本文末尾に追加した「最終出力」セクションが取り込まれていること
        assert "docs/company-business-requirement.md" in untargeted["prompt"]
        # Phase A で削除された tools (execute/todo) が含まれないこと
        assert "execute" not in untargeted["tools"]
        assert "todo" not in untargeted["tools"]
