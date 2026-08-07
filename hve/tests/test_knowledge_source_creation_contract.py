"""Knowledge Source の作成手段に関する確定事実を固定する。

Microsoft Learn（2026-08-05 確認）で以下が確定した。
- `az search` に Knowledge Source 作成コマンドは無い（portal / Foundry portal / REST / 各 SDK のみ）
- preview 種別は preview api-version でしか作成できない

Agent が `az search knowledge-source ...` を捏造すると実行時に失敗するため、
Skill と Deploy Prompt の双方に記載があることを検査する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_MATRIX = (
    _REPO
    / ".github"
    / "skills"
    / "agentic-retrieval-contract"
    / "references"
    / "knowledge-source-matrix.md"
)
_DEPLOY_PROMPT = (
    _REPO / ".github" / "prompts" / "Dev-Microservice-Azure-AgenticRetrievalDeploy.prompt.md"
)


@pytest.fixture(scope="module")
def matrix() -> str:
    assert _MATRIX.is_file(), "knowledge-source-matrix.md が存在しない"
    return _MATRIX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def deploy_prompt() -> str:
    assert _DEPLOY_PROMPT.is_file(), "AgenticRetrievalDeploy prompt が存在しない"
    return _DEPLOY_PROMPT.read_text(encoding="utf-8")


class TestAzCliIsNotAnOption:
    """`az search` で作れると誤解させないこと。"""

    def test_matrix_states_az_cli_has_no_command(self, matrix):
        assert "`az search`" in matrix
        assert "作成コマンドは無い" in matrix

    def test_deploy_prompt_states_az_cli_has_no_command(self, deploy_prompt):
        assert "`az search`" in deploy_prompt
        assert "存在しない" in deploy_prompt

    def test_deploy_prompt_names_the_rest_path(self, deploy_prompt):
        """代替手段を書かずに禁止だけすると Agent が止まる。"""
        assert "az rest" in deploy_prompt
        assert "/knowledgesources/" in deploy_prompt


class TestPreviewApiVersionConstraint:
    def test_matrix_states_preview_api_version_requirement(self, matrix):
        assert "preview API version" in matrix or "preview api-version" in matrix

    def test_deploy_prompt_states_preview_api_version_requirement(self, deploy_prompt):
        assert "preview api-version" in deploy_prompt

    @pytest.mark.parametrize("source", ["matrix", "deploy_prompt"])
    def test_api_version_is_not_hardcoded_as_the_rule(self, source, matrix, deploy_prompt):
        """api-version を固定値として書くと陳腐化する。確認日付きの参考値に留める。"""
        text = matrix if source == "matrix" else deploy_prompt
        assert "実行時に確認" in text or "確認した値" in text


class TestPermissions:
    def test_matrix_states_required_roles(self, matrix):
        assert "Search Service Contributor" in matrix
        assert "Search Index Data Contributor" in matrix

    def test_deploy_prompt_states_required_roles(self, deploy_prompt):
        assert "Search Service Contributor" in deploy_prompt


class TestWorkIqRuntimeConstraints:
    """実行時にしか出ない制約を設計段階で拾えるようにする。"""

    def test_timeout_is_documented(self, matrix):
        assert "maxRuntimeInSeconds" in matrix
        assert "120" in matrix

    def test_obo_header_is_documented(self, matrix):
        assert "x-ms-query-source-authorization" in matrix
        assert "https://search.azure.com/.default" in matrix

    def test_action_capability_warning_is_documented(self, matrix):
        """preview の Work IQ は取得だけでなく操作を行う可能性がある。"""
        assert "操作を行う" in matrix
