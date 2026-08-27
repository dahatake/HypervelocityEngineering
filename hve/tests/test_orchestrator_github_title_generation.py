"""FR-GUI-39: GUI-launched PR title generation contract."""

from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock

import pytest

from hve.config import SDKConfig


def _console() -> Any:
    console = MagicMock()
    console.events = []
    console.warnings = []
    console.event.side_effect = console.events.append
    console.warning.side_effect = console.warnings.append
    return console


def _config() -> SDKConfig:
    return SDKConfig(
        quiet=True,
        github_token="test-token",
        repo="owner/repo",
        cli_path="C:/configured/copilot.exe",
    )


class TestGuiPrTitleHelper:
    def test_gui_child_queries_copilot_cli(self, monkeypatch) -> None:
        from hve import orchestrator

        calls: List[Any] = []

        def _generate(kind: str, source: str, **kwargs: Any) -> str:
            calls.append((kind, source, kwargs))
            return "[AAS] Improve application boundaries"

        monkeypatch.setenv("HVE_GUI_SESSION_ID", "gui-run-1")
        monkeypatch.setattr(orchestrator, "generate_github_title", _generate, raising=False)
        console = _console()

        title = orchestrator._generate_gui_pr_title(
            fallback_title="[AAS] Application Architecture Selection",
            pr_body="PR body",
            required_prefix="[AAS] ",
            config=_config(),
            console=console,
        )

        assert title == "[AAS] Improve application boundaries"
        assert calls == [
            (
                "pull_request",
                "PR body",
                {
                    "fallback_title": "[AAS] Application Architecture Selection",
                    "required_prefix": "[AAS] ",
                    "cli_path": "C:/configured/copilot.exe",
                },
            )
        ]
        assert any("タイトルを生成" in message for message in console.events)

    def test_non_gui_run_keeps_deterministic_title(self, monkeypatch) -> None:
        from hve import orchestrator

        monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
        generator = MagicMock(return_value="Generated")
        monkeypatch.setattr(orchestrator, "generate_github_title", generator, raising=False)

        title = orchestrator._generate_gui_pr_title(
            fallback_title="[AAS] Default",
            pr_body="Body",
            required_prefix="[AAS] ",
            config=_config(),
            console=_console(),
        )

        assert title == "[AAS] Default"
        generator.assert_not_called()

    def test_generation_failure_falls_back_without_failing_pr(
        self, monkeypatch
    ) -> None:
        from hve import github_title_generator, orchestrator

        monkeypatch.setenv("HVE_GUI_SESSION_ID", "gui-run-1")

        def _fail(*_args: Any, **_kwargs: Any) -> str:
            raise github_title_generator.GitHubTitleGenerationError("safe failure")

        monkeypatch.setattr(orchestrator, "generate_github_title", _fail, raising=False)
        console = _console()

        title = orchestrator._generate_gui_pr_title(
            fallback_title="[AAS] Default",
            pr_body="Body",
            required_prefix="[AAS] ",
            config=_config(),
            console=console,
        )

        assert title == "[AAS] Default"
        assert any("既定タイトル" in message for message in console.warnings)
        assert all("Body" not in message for message in console.warnings)


class TestPrCreationWiring:
    def test_create_pr_uses_generated_title_for_gui_run(self, monkeypatch) -> None:
        from hve import orchestrator

        captured: dict[str, Any] = {}
        monkeypatch.setenv("HVE_GUI_SESSION_ID", "gui-run-1")
        monkeypatch.setattr(
            orchestrator,
            "_generate_gui_pr_title",
            lambda **kwargs: "[AAS] Generated title",
            raising=False,
        )
        monkeypatch.setattr(
            orchestrator,
            "create_pull_request",
            lambda **kwargs: captured.update(kwargs) or 42,
        )
        wf = MagicMock()
        wf.id = "aas"

        result = orchestrator._create_pr_if_needed(
            wf=wf,
            head_branch="copilot-sdk/aas-1234abcd",
            base_branch="main",
            config=_config(),
            console=_console(),
        )

        assert result == 42
        assert captured["title"] == "[AAS] Generated title"

    def test_draft_suffix_is_preserved(self, monkeypatch) -> None:
        from hve import orchestrator

        captured: dict[str, Any] = {}
        monkeypatch.setenv("HVE_GUI_SESSION_ID", "gui-run-1")
        monkeypatch.setattr(
            orchestrator,
            "_generate_gui_pr_title",
            lambda **kwargs: "[AAS] Generated title",
            raising=False,
        )
        monkeypatch.setattr(
            orchestrator,
            "create_pull_request",
            lambda **kwargs: captured.update(kwargs) or 43,
        )
        wf = MagicMock()
        wf.id = "aas"

        result = orchestrator._create_pr_if_needed(
            wf=wf,
            head_branch="copilot-sdk/aas-1234abcd",
            base_branch="main",
            config=_config(),
            console=_console(),
            all_steps_succeeded=False,
            local_checkpoint_only=True,
        )

        assert result == 43
        assert captured["title"] == "[AAS] Generated title — local checkpoint (draft)"
        assert captured["draft"] is True


class TestRootIssueTitleWiring:
    def _create_root(self, monkeypatch, *, params: dict[str, Any]) -> dict[str, Any]:
        from hve import orchestrator

        captured: dict[str, Any] = {}
        cfg = _config()
        cfg.create_issues = True
        wf = MagicMock()
        wf.id = "aas"
        wf.steps = []
        monkeypatch.setenv("HVE_GUI_SESSION_ID", "gui-run-1")
        monkeypatch.setattr(
            orchestrator,
            "create_issue",
            lambda **kwargs: captured.update(kwargs) or (81, 8100),
        )

        root, step_map = orchestrator._create_issues_if_needed(
            wf=wf,
            params=params,
            active_steps=set(),
            config=cfg,
            console=_console(),
            render_template_fn=MagicMock(),
            build_root_issue_body_fn=lambda _wf, _params: "Root issue body",
        )

        assert root == 81
        assert step_map == {}
        return captured

    def test_gui_root_issue_uses_generated_title(self, monkeypatch) -> None:
        from hve import orchestrator

        monkeypatch.setattr(
            orchestrator,
            "_generate_gui_issue_title",
            lambda **kwargs: "[AAS] Generated root issue title",
            raising=False,
        )

        captured = self._create_root(monkeypatch, params={})

        assert captured["title"] == "[AAS] Generated root issue title"
        assert captured["body"] == "Root issue body"

    def test_explicit_issue_title_is_not_overwritten(self, monkeypatch) -> None:
        from hve import orchestrator

        generator = MagicMock(return_value="Generated")
        monkeypatch.setattr(
            orchestrator,
            "_generate_gui_issue_title",
            generator,
            raising=False,
        )

        captured = self._create_root(
            monkeypatch,
            params={"issue_title": "User supplied root title"},
        )

        assert captured["title"] == "User supplied root title"
        generator.assert_not_called()
