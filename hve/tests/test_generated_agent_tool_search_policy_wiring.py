"""生成する AI Agent の Tool Search 方針が Prompt と gate へ届くことの検証。

FR-WF-AAG-01 / FR-WF-AAGD-04。
`SDKConfig.enable_tool_search`（生成 Agent 用）が対象 Step にだけ注入され、
非対象 Step の Prompt を変えないことを確認する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner, _tool_search_policy_prefix


def _runner(policy: str) -> StepRunner:
    config = SDKConfig()
    config.enable_tool_search = policy
    return StepRunner(config=config, console=Console(verbose=False, quiet=True))


class TestPolicyPrefixTargets:
    @pytest.mark.parametrize(
        ("workflow", "step_id"),
        [
            ("aag", "3/AG-01"),
            ("aagd", "2.3/AG-01"),
            ("aagd", "3/AG-01"),
            ("aagd", "4"),
        ],
    )
    def test_target_steps_receive_the_policy(self, workflow: str, step_id: str):
        text = _tool_search_policy_prefix(workflow, step_id, "yes")
        assert "`yes`" in text

    @pytest.mark.parametrize(
        ("workflow", "step_id"),
        [
            ("aag", "2"),
            ("aag", "4"),
            ("aagd", "2.1/AG-01"),
            ("aad-web", "3"),
            ("", "3"),
            (None, "3"),
        ],
    )
    def test_unrelated_steps_are_untouched(self, workflow: Any, step_id: str):
        assert _tool_search_policy_prefix(workflow, step_id, "yes") == ""

    @pytest.mark.parametrize("policy", ["auto", "yes", "no"])
    def test_each_policy_is_passed_through_verbatim(self, policy: str):
        assert f"`{policy}`" in _tool_search_policy_prefix("aag", "3/AG-01", policy)

    def test_forbids_agent_side_override(self):
        text = _tool_search_policy_prefix("aag", "3/AG-01", "no")
        assert "上書きしない" in text

    def test_unknown_policy_is_fail_closed(self):
        text = _tool_search_policy_prefix("aag", "3/AG-01", "ON")
        assert "`ON`" in text
        assert "blocked" in text


class TestCapabilityGateForwardsPolicy:
    def _capture(self, tmp_path: Path, monkeypatch: Any, policy: str) -> dict:
        monkeypatch.chdir(tmp_path)
        captured: dict = {}

        def fake_validator(workflow_id: str, design_path: Path, **kwargs: Any) -> list:
            captured.update(kwargs)
            return []

        monkeypatch.setattr(
            "hve.artifact_validation.validate_ai_agent_capability_artifacts",
            fake_validator,
        )
        assert _runner(policy)._run_ai_agent_capability_gate(
            "3/AG-01", "Arch-AIAgentDesign-Step3", "aag"
        ) == []
        return captured

    @pytest.mark.parametrize("policy", ["auto", "yes", "no"])
    def test_design_gate_receives_the_configured_policy(
        self, tmp_path: Path, monkeypatch: Any, policy: str
    ):
        assert self._capture(tmp_path, monkeypatch, policy)["tool_search_policy"] == policy

    def test_unknown_policy_reaches_the_validator_unchanged(
        self, tmp_path: Path, monkeypatch: Any
    ):
        """既定へ丸めず validator に fail-closed 判定させる。"""
        assert self._capture(tmp_path, monkeypatch, "ON")["tool_search_policy"] == "ON"
