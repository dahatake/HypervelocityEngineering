"""FR-CLI-76 (v2.41): 事前 QA サブセッションの MCP 自動探索を停止する契約。

Work IQ を有効化した QA サブセッションは `mcp_servers` に `_hve_workiq` だけを明示するため、
FR-CLI-76 の縮約条件（`mcp_servers` / `enable_config_discovery` いずれも未指定）を満たさず
自動探索が残っていた。その結果、利用者グローバル設定のプラグインが登録する Work IQ サーバー
（`workiq`）が `tools: ["*"]` で同一セッションへ併存し、HVE が `_hve_workiq` へ課す
最小権限 allowlist（`ask` のみ）が及ばなかった。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner
from hve.workiq import WORKIQ_MCP_SERVER_NAME

_DECLARED_SERVERS = {
    "azure": {"command": "npx", "args": ["-y", "@azure/mcp@latest", "server", "start"], "tools": ["*"]},
    "microsoft-learn": {"type": "http", "url": "https://learn.microsoft.com/api/mcp", "tools": ["*"]},
}


def _write_mcp_config(root: Path, payload: str | None) -> None:
    github_dir = root / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)
    if payload is not None:
        (github_dir / ".mcp.json").write_text(payload, encoding="utf-8")


def _build_pre_qa_opts(*, workflow_id: str | None = None) -> dict:
    config = SDKConfig(workiq_enabled=True)
    runner = StepRunner(config=config, console=Console(verbose=False, quiet=True))
    with patch.object(
        runner, "_build_step_permission_handler", return_value="permission-handler"
    ), patch("hve.runner.is_workiq_available", return_value=True):
        return runner._build_sub_session_opts(
            config.model,
            include_workiq=True,
            step_id="1",
            suffix="pre-qa",
            workflow_id=workflow_id,
        )


@pytest.fixture
def declared_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _write_mcp_config(tmp_path, json.dumps({"mcpServers": _DECLARED_SERVERS}))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_pre_qa_sub_session_disables_config_discovery(declared_repo: Path) -> None:
    """自動探索を止め、プラグイン由来 `workiq` の併存を防ぐ。"""
    opts = _build_pre_qa_opts()

    assert opts["enable_config_discovery"] is False


def test_pre_qa_sub_session_merges_declared_mcp_servers(declared_repo: Path) -> None:
    """自動探索を止めても、リポジトリ宣言分は明示併合して失わない。"""
    opts = _build_pre_qa_opts()

    assert set(opts["mcp_servers"]) == {WORKIQ_MCP_SERVER_NAME, "azure", "microsoft-learn"}


def test_pre_qa_sub_session_keeps_workiq_least_privilege(declared_repo: Path) -> None:
    """併合しても `_hve_workiq` のツール allowlist は `ask` のみのまま。"""
    opts = _build_pre_qa_opts()

    assert opts["mcp_servers"][WORKIQ_MCP_SERVER_NAME]["tools"] == ["ask"]


def test_pre_qa_sub_session_drops_declared_workiq_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """宣言側に Work IQ 別名があっても併合せず、`_hve_workiq` だけを残す。"""
    _write_mcp_config(
        tmp_path,
        json.dumps(
            {
                "mcpServers": {
                    **_DECLARED_SERVERS,
                    "workiq": {"command": "npx", "args": ["-y", "@microsoft/workiq@latest"], "tools": ["*"]},
                }
            }
        ),
    )
    monkeypatch.chdir(tmp_path)

    opts = _build_pre_qa_opts()

    assert "workiq" not in opts["mcp_servers"]
    assert WORKIQ_MCP_SERVER_NAME in opts["mcp_servers"]


def test_pre_qa_sub_session_applies_azure_free_workflow_filter(declared_repo: Path) -> None:
    """FR-CLI-79: Azure を利用しない Workflow では `azure` を併合しない。"""
    opts = _build_pre_qa_opts(workflow_id="akm")

    assert "azure" not in opts["mcp_servers"]
    assert "microsoft-learn" in opts["mcp_servers"]


@pytest.mark.parametrize(
    "payload",
    [None, json.dumps({"mcpServers": {}}), json.dumps({"servers": _DECLARED_SERVERS}), "{ not json"],
)
def test_pre_qa_sub_session_keeps_discovery_when_nothing_is_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str | None
) -> None:
    """宣言が無い/壊れている場合は従来どおり自動探索を残す（回帰回避のフォールバック）。"""
    _write_mcp_config(tmp_path, payload)
    monkeypatch.chdir(tmp_path)

    opts = _build_pre_qa_opts()

    assert "enable_config_discovery" not in opts
    assert set(opts["mcp_servers"]) == {WORKIQ_MCP_SERVER_NAME}


def test_review_sub_session_is_left_to_the_generic_frcli76_path(declared_repo: Path) -> None:
    """Work IQ 無しの Review サブセッションは `mcp_servers` を持たず、共通経路に委ねる。"""
    config = SDKConfig()
    runner = StepRunner(config=config, console=Console(verbose=False, quiet=True))
    with patch.object(
        runner, "_build_step_permission_handler", return_value="permission-handler"
    ):
        opts = runner._build_sub_session_opts(config.model, step_id="1", suffix="review")

    assert "mcp_servers" not in opts
    assert "enable_config_discovery" not in opts
