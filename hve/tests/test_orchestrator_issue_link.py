"""tests/test_orchestrator_issue_link.py — FR-GUI-25 の既存 Issue 連携のテスト。

`_create_issues_if_needed` が `SDKConfig.issue_number` 指定時に Root Issue を
新規作成せず、既存 Issue を Root として扱うことを検証する。GitHub API は mock する。
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, cast
from unittest import mock

from hve import orchestrator
from hve.config import SDKConfig
from hve.github_api import GitHubAPIError
from hve.workflow_registry import get_workflow


class _RecordingConsole:
    def __init__(self) -> None:
        self.events: List[str] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def event(self, message: str, *_a, **_kw) -> None:
        self.events.append(message)

    def warning(self, message: str, *_a, **_kw) -> None:
        self.warnings.append(message)

    def error(self, message: str, *_a, **_kw) -> None:
        self.errors.append(message)


def _config(**kwargs: Any) -> SDKConfig:
    cfg = SDKConfig(repo="owner/repo", github_token="tok", **kwargs)
    return cfg


def _call(cfg: SDKConfig, console: _RecordingConsole, active_steps=None):
    wf = get_workflow("aad-web")
    assert wf is not None
    steps = active_steps if active_steps is not None else set()
    return orchestrator._create_issues_if_needed(
        wf=wf,
        params={},
        active_steps=steps,
        config=cfg,
        console=cast(Any, console),
        render_template_fn=lambda **_kw: "body",
        build_root_issue_body_fn=lambda *_a, **_kw: "root body",
    )


class TestExistingRootIssue(unittest.TestCase):
    def test_uses_existing_issue_without_creating_root(self) -> None:
        console = _RecordingConsole()
        with mock.patch.object(
            orchestrator, "get_issue", return_value={"number": 1234}
        ) as get_mock, mock.patch.object(orchestrator, "create_issue") as create_mock:
            root, step_map = _call(_config(create_issues=True, issue_number=1234), console)

        self.assertEqual(root, 1234)
        self.assertEqual(step_map, {})
        get_mock.assert_called_once_with(1234, repo="owner/repo", token="tok")
        create_mock.assert_not_called()
        self.assertTrue(any("1234" in e for e in console.events))

    def test_sub_issues_link_to_existing_root(self) -> None:
        console = _RecordingConsole()
        created: List[Dict[str, Any]] = []
        linked: List[Dict[str, Any]] = []

        def _create_issue(**kwargs):
            created.append(kwargs)
            return (900 + len(created), 8000 + len(created))

        def _link(**kwargs):
            linked.append(kwargs)
            return True

        wf = cast(Any, get_workflow("aad-web"))
        first_step = next(s for s in wf.steps if not s.is_container and s.body_template_path)

        with mock.patch.object(
            orchestrator, "get_issue", return_value={"number": 55}
        ), mock.patch.object(
            orchestrator, "create_issue", side_effect=_create_issue
        ), mock.patch.object(orchestrator, "link_sub_issue", side_effect=_link):
            root, step_map = _call(
                _config(create_issues=True, issue_number=55),
                console,
                active_steps={first_step.id},
            )

        self.assertEqual(root, 55)
        self.assertEqual(step_map, {first_step.id: 901})
        self.assertEqual(len(created), 1, "Root Issue を新規作成してはならない")
        self.assertEqual(linked[0]["parent_num"], 55)

    def test_unresolvable_issue_is_fail_closed(self) -> None:
        console = _RecordingConsole()
        with mock.patch.object(
            orchestrator, "get_issue", side_effect=GitHubAPIError("not found", 404)
        ), mock.patch.object(orchestrator, "create_issue") as create_mock:
            with self.assertRaises(orchestrator.RootIssueResolutionError):
                _call(_config(create_issues=True, issue_number=999), console)

        create_mock.assert_not_called()

    def test_missing_number_field_is_fail_closed(self) -> None:
        console = _RecordingConsole()
        with mock.patch.object(
            orchestrator, "get_issue", return_value={"title": "no number"}
        ), mock.patch.object(orchestrator, "create_issue") as create_mock:
            with self.assertRaises(orchestrator.RootIssueResolutionError):
                _call(_config(create_issues=True, issue_number=999), console)

        create_mock.assert_not_called()

    def test_pull_request_number_is_rejected(self) -> None:
        """PR 番号を Issue 番号として渡した場合は fail-closed とする。"""
        console = _RecordingConsole()
        with mock.patch.object(
            orchestrator,
            "get_issue",
            return_value={"number": 12, "pull_request": {"url": "https://example.invalid/12"}},
        ), mock.patch.object(orchestrator, "create_issue") as create_mock:
            with self.assertRaises(orchestrator.RootIssueResolutionError):
                _call(_config(create_issues=True, issue_number=12), console)

        create_mock.assert_not_called()

    def test_create_pr_only_links_issue_without_sub_issues(self) -> None:
        """PR だけを作る run でも既存 Issue を closing target として返す。"""
        console = _RecordingConsole()
        with mock.patch.object(
            orchestrator, "get_issue", return_value={"number": 88}
        ) as get_mock, mock.patch.object(orchestrator, "create_issue") as create_mock, \
                mock.patch.object(orchestrator, "link_sub_issue") as link_mock:
            root, step_map = _call(
                _config(create_issues=False, create_pr=True, issue_number=88),
                console,
                active_steps={"1"},
            )

        self.assertEqual(root, 88)
        self.assertEqual(step_map, {})
        get_mock.assert_called_once_with(88, repo="owner/repo", token="tok")
        create_mock.assert_not_called()
        link_mock.assert_not_called()

    def test_create_pr_only_invalid_issue_is_fail_closed(self) -> None:
        console = _RecordingConsole()
        with mock.patch.object(
            orchestrator, "get_issue", side_effect=GitHubAPIError("not found", 404)
        ), mock.patch.object(orchestrator, "create_issue") as create_mock:
            with self.assertRaises(orchestrator.RootIssueResolutionError):
                _call(
                    _config(create_issues=False, create_pr=True, issue_number=999),
                    console,
                )

        create_mock.assert_not_called()

    def test_create_pr_only_rejects_pull_request_number(self) -> None:
        console = _RecordingConsole()
        with mock.patch.object(
            orchestrator,
            "get_issue",
            return_value={"number": 12, "pull_request": {"url": "https://example.invalid/12"}},
        ), mock.patch.object(orchestrator, "create_issue") as create_mock:
            with self.assertRaises(orchestrator.RootIssueResolutionError):
                _call(
                    _config(create_issues=False, create_pr=True, issue_number=12),
                    console,
                )

        create_mock.assert_not_called()


class TestUnchangedBehaviour(unittest.TestCase):
    def test_without_issue_number_root_is_created(self) -> None:
        console = _RecordingConsole()
        with mock.patch.object(orchestrator, "get_issue") as get_mock, mock.patch.object(
            orchestrator, "create_issue", return_value=(10, 100)
        ) as create_mock:
            root, _ = _call(_config(create_issues=True), console)

        self.assertEqual(root, 10)
        create_mock.assert_called_once()
        get_mock.assert_not_called()

    def test_create_issues_disabled_short_circuits(self) -> None:
        console = _RecordingConsole()
        with mock.patch.object(orchestrator, "get_issue") as get_mock, mock.patch.object(
            orchestrator, "create_issue"
        ) as create_mock:
            root, step_map = _call(_config(create_issues=False, issue_number=1), console)

        self.assertIsNone(root)
        self.assertEqual(step_map, {})
        get_mock.assert_not_called()
        create_mock.assert_not_called()

    def test_missing_token_skips_without_calling_github(self) -> None:
        console = _RecordingConsole()
        cfg = SDKConfig(repo="owner/repo", create_issues=True, issue_number=5)
        cfg.github_token = ""
        with mock.patch.object(cfg, "resolve_token", return_value=""), mock.patch.object(
            orchestrator, "get_issue"
        ) as get_mock:
            root, step_map = _call(cfg, console)

        self.assertIsNone(root)
        self.assertEqual(step_map, {})
        get_mock.assert_not_called()
        self.assertTrue(console.warnings)


if __name__ == "__main__":
    unittest.main()
