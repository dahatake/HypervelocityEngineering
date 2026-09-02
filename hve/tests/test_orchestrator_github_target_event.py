"""FR-RTO-08: Orchestrator が GitHub target lifecycle イベントを送出する契約。

RED 先行。`_emit_github_target_event` は本テスト作成時点で未実装。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

from hve import orchestrator
from hve import runtime_observability as rto


class _RecordingConsole:
    def __init__(self) -> None:
        self.events: List[Tuple[str, str, Dict[str, Any]]] = []
        self.warnings: List[str] = []

    def stats_event(self, kind: str, step_id: str = "", **fields: Any) -> None:
        self.events.append((kind, step_id, dict(fields)))

    def warning(self, message: str) -> None:
        self.warnings.append(message)


class _RaisingConsole(_RecordingConsole):
    def stats_event(self, kind: str, step_id: str = "", **fields: Any) -> None:
        raise RuntimeError("stats stream is broken")


def _emit(console: Any, **kwargs: Any) -> None:
    emitter = getattr(orchestrator, "_emit_github_target_event", None)
    if emitter is None:  # pragma: no cover - RED 期間のみ
        pytest.fail("_emit_github_target_event が未実装です（FR-RTO-08）")
    emitter(console, **kwargs)


def _only_event(console: _RecordingConsole) -> Tuple[str, str, Dict[str, Any]]:
    assert len(console.events) == 1
    return console.events[0]


class TestEmission:
    def test_emits_single_github_target_event(self) -> None:
        console = _RecordingConsole()
        _emit(console, repo="owner/repo", issue_number=12)

        kind, step_id, fields = _only_event(console)
        assert kind == rto.GITHUB_TARGET_KIND
        assert step_id == ""
        assert fields == {"repo": "owner/repo", "issue_number": 12}

    def test_emits_full_target_after_pr_is_created(self) -> None:
        console = _RecordingConsole()
        _emit(
            console,
            repo="owner/repo",
            issue_number=12,
            pr_number=34,
            branch="copilot-sdk/asdw-1234abcd",
            base_branch="main",
            created_by_hve=True,
            delete_local_merged_branch=True,
        )

        _, _, fields = _only_event(console)
        assert fields == {
            "repo": "owner/repo",
            "issue_number": 12,
            "pr_number": 34,
            "branch": "copilot-sdk/asdw-1234abcd",
            "base_branch": "main",
            "created_by_hve": True,
            "delete_local_merged_branch": True,
        }

    def test_current_branch_mode_reports_not_created_by_hve(self) -> None:
        console = _RecordingConsole()
        _emit(
            console,
            repo="owner/repo",
            pr_number=34,
            branch="feature/current",
            base_branch="main",
            created_by_hve=False,
        )

        _, _, fields = _only_event(console)
        assert fields["created_by_hve"] is False

    def test_nothing_is_emitted_when_no_field_is_determined(self) -> None:
        console = _RecordingConsole()
        _emit(console, repo=None, issue_number=None, pr_number=None, branch=None)
        assert console.events == []


class TestValidationIsDelegated:
    """FR-MAINT-07: 値検証は `github_target_fields` の単一実装へ委譲する。"""

    def test_invalid_values_are_dropped(self) -> None:
        console = _RecordingConsole()
        _emit(
            console,
            repo="https://github.com/owner/repo.git",
            issue_number=0,
            pr_number=True,
            branch="   ",
            base_branch="main",
        )

        _, _, fields = _only_event(console)
        assert fields == {"base_branch": "main"}

    def test_emitted_fields_match_the_shared_builder(self) -> None:
        console = _RecordingConsole()
        kwargs = {
            "repo": "owner/repo",
            "issue_number": 12,
            "pr_number": 34,
            "branch": "b",
            "base_branch": "main",
            "created_by_hve": True,
            "delete_local_merged_branch": False,
        }
        _emit(console, **kwargs)

        _, _, fields = _only_event(console)
        assert fields == rto.github_target_fields(**kwargs)


class TestSecretExclusion:
    def test_token_argument_is_not_accepted(self) -> None:
        console = _RecordingConsole()
        with pytest.raises(TypeError):
            _emit(console, repo="owner/repo", token="ghp_secret")


class TestFailureIsolation:
    """NFR-RTO-03: 送出失敗は Workflow を止めない。"""

    def test_emit_failure_does_not_raise(self) -> None:
        console = _RaisingConsole()
        _emit(console, repo="owner/repo", issue_number=12)

    def test_emit_failure_warns_with_exception_type_only(self) -> None:
        console = _RaisingConsole()
        _emit(console, repo="owner/repo", issue_number=12)

        assert len(console.warnings) == 1
        message = console.warnings[0]
        assert "RuntimeError" in message
        assert "stats stream is broken" not in message

    def test_console_without_warning_is_tolerated(self) -> None:
        class _EmitOnly:
            def stats_event(self, kind: str, step_id: str = "", **fields: Any) -> None:
                raise RuntimeError("boom")

        _emit(_EmitOnly(), repo="owner/repo", issue_number=12)

    def test_console_without_stats_event_is_tolerated(self) -> None:
        class _Legacy:
            pass

        _emit(_Legacy(), repo="owner/repo", issue_number=12)


class TestProducerWiring:
    """run_workflow が Issue / PR / branch 確定時に producer を呼ぶ。"""

    def test_run_workflow_emits_after_issue_and_branch_are_resolved(self) -> None:
        import inspect

        source = inspect.getsource(orchestrator._run_workflow_body)
        assert source.count("_emit_github_target_event(") >= 2
        assert "created_by_hve=hve_created_branch" in source
