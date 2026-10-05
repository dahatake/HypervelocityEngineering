"""FR-CLI-102 / FR-WF-OUT-12 runtime guidance and output continuation."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

import pytest

from hve.orchestrator_context import OrchestratorContext
from hve.runner import (
    StepRunner,
    _build_runtime_guidance_suffix,
    _continue_for_missing_outputs,
)


@dataclass
class _Step:
    id: str
    output_paths: list[str] = field(default_factory=list)


@dataclass
class _Workflow:
    steps: list[_Step]


Send = Callable[[object, str], Awaitable[object]]


def _workflow(*paths: str) -> _Workflow:
    return _Workflow([_Step(id="1", output_paths=list(paths))])


def _run(coro):
    return asyncio.run(coro)


def test_existing_outputs_do_not_send_continuation(tmp_path: Path) -> None:
    output = tmp_path / "docs" / "ready.md"
    output.parent.mkdir()
    output.write_text("ready\n", encoding="utf-8")
    prompts: list[str] = []

    async def send(_session: object, prompt: str) -> object:
        prompts.append(prompt)
        return object()

    missing = _run(
        _continue_for_missing_outputs(
            object(),
            ctx=OrchestratorContext(),
            workflow=_workflow("docs/ready.md"),
            step_id="1",
            repo_root=tmp_path,
            send=send,
        )
    )

    assert missing == []
    assert prompts == []


def test_first_continuation_can_create_missing_output(tmp_path: Path) -> None:
    output = tmp_path / "docs" / "created.md"
    prompts: list[str] = []

    session = object()

    async def send(active_session: object, prompt: str) -> object:
        assert active_session is session
        prompts.append(prompt)
        output.parent.mkdir()
        output.write_text("created\n", encoding="utf-8")
        return object()

    missing = _run(
        _continue_for_missing_outputs(
            session,
            ctx=OrchestratorContext(),
            workflow=_workflow("docs/created.md"),
            step_id="1",
            repo_root=tmp_path,
            send=send,
        )
    )

    assert missing == []
    assert len(prompts) == 1
    assert "docs/created.md" in prompts[0]


def test_second_continuation_can_create_missing_output(tmp_path: Path) -> None:
    output = tmp_path / "docs" / "created.md"
    prompts: list[str] = []

    async def send(_session: object, prompt: str) -> object:
        prompts.append(prompt)
        if len(prompts) == 2:
            output.parent.mkdir()
            output.write_text("created\n", encoding="utf-8")
        return object()

    missing = _run(
        _continue_for_missing_outputs(
            object(),
            ctx=OrchestratorContext(),
            workflow=_workflow("docs/created.md"),
            step_id="1",
            repo_root=tmp_path,
            send=send,
        )
    )

    assert missing == []
    assert len(prompts) == 2


def test_two_continuations_then_returns_only_still_missing_paths(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "docs" / "existing.md"
    existing.parent.mkdir()
    existing.write_text("ready\n", encoding="utf-8")
    prompts: list[str] = []

    async def send(_session: object, prompt: str) -> object:
        prompts.append(prompt)
        return object()

    missing = _run(
        _continue_for_missing_outputs(
            object(),
            ctx=OrchestratorContext(),
            workflow=_workflow("docs/existing.md", "docs/missing.md"),
            step_id="1",
            repo_root=tmp_path,
            send=send,
        )
    )

    assert missing == ["docs/missing.md"]
    assert len(prompts) == 2
    assert all("docs/missing.md" in prompt for prompt in prompts)
    assert all("docs/existing.md" not in prompt for prompt in prompts)


def test_standalone_mode_does_not_send_continuation(tmp_path: Path) -> None:
    prompts: list[str] = []

    async def send(_session: object, prompt: str) -> object:
        prompts.append(prompt)
        return object()

    missing = _run(
        _continue_for_missing_outputs(
            object(),
            ctx=None,
            workflow=_workflow("docs/missing.md"),
            step_id="1",
            repo_root=tmp_path,
            send=send,
        )
    )

    assert missing == []
    assert prompts == []


def test_send_failure_is_not_converted_to_success(tmp_path: Path) -> None:
    async def send(_session: object, _prompt: str) -> object:
        raise TimeoutError("continuation timed out")

    with pytest.raises(TimeoutError, match="continuation timed out"):
        _run(
            _continue_for_missing_outputs(
                object(),
                ctx=OrchestratorContext(),
                workflow=_workflow("docs/missing.md"),
                step_id="1",
                repo_root=tmp_path,
                send=send,
            )
        )


def test_runtime_guidance_is_shared_and_unattended_rule_is_conditional() -> None:
    interactive = _build_runtime_guidance_suffix(unattended=False)
    unattended = _build_runtime_guidance_suffix(unattended=True)

    for guidance in (interactive, unattended):
        assert "300 行以内" in guidance
        assert "関係しうる入力" in guidance
        assert "埋め草" in guidance
    assert "進捗報告" not in interactive
    assert "進捗報告" in unattended
    assert "資格情報" in unattended


def test_run_step_continues_on_the_main_session_before_contract_gates() -> None:
    source = inspect.getsource(StepRunner.run_step)

    main_send = source.index(
        "main_response = await self._send_and_wait_with_model_call_failure_guard"
    )
    continuation = source.index("await _continue_for_missing_outputs(")
    first_contract_gate = source.index("preflight_failure_errors =")

    assert main_send < continuation < first_contract_gate
    assert "session,\n                ctx=self._orchestrator_ctx" in source
    assert source.count(
        '("runtime_guidance_suffix", _runtime_guidance_suffix)'
    ) >= 2


def test_declared_scope_is_interpolated_only_when_unattended() -> None:
    """FR-PROMPT-13: 無人実行の指示へ宣言範囲を差し込む。"""
    from hve.runner import DeclaredScope, _build_runtime_guidance_suffix

    scope = DeclaredScope(
        resource_group="rg-hve-dev",
        pre_approved_operations=("azure_deploy",),
        allow_public_exposure=False,
        budget_note="検証用",
    )
    unattended = _build_runtime_guidance_suffix(True, scope)
    assert "rg-hve-dev" in unattended
    assert "azure_deploy" in unattended
    assert "検証用" in unattended
    assert "外部公開" in unattended
    assert _build_runtime_guidance_suffix(True, None) == _build_runtime_guidance_suffix(True)
    assert "rg-hve-dev" not in _build_runtime_guidance_suffix(False, scope)


def test_declared_scope_rejects_unsafe_values() -> None:
    from hve.runner import DeclaredScope, _build_runtime_guidance_suffix

    scope = DeclaredScope(
        resource_group="rg; rm -rf /",
        pre_approved_operations=("azure_deploy",),
        allow_public_exposure=False,
        budget_note="a\nb",
    )
    text = _build_runtime_guidance_suffix(True, scope)
    assert "rm -rf" not in text
    assert "a\nb" not in text


def test_step_time_limit_is_added_to_common_guidance_when_enabled() -> None:
    """N3-2 / FR-CLI-102: 上限時間が有効なら共通実行指示へ分単位で示す。"""
    with_limit = _build_runtime_guidance_suffix(False, None, 7200.0)
    assert "この Step の上限時間は約 120 分です" in with_limit
    assert _build_runtime_guidance_suffix(False, None, None) == _build_runtime_guidance_suffix(False)
    unattended = _build_runtime_guidance_suffix(True, None, 90.0)
    assert "約 2 分" in unattended
    assert unattended.count("この Step の上限時間") == 1


def test_continuation_message_reports_elapsed_and_limit(tmp_path: Path) -> None:
    """N3-2 / FR-WF-OUT-12: 継続メッセージに経過時間と上限を示す。"""
    prompts: list[str] = []

    async def send(_session: object, prompt: str) -> object:
        prompts.append(prompt)
        return object()

    _run(
        _continue_for_missing_outputs(
            object(),
            ctx=OrchestratorContext(),
            workflow=_workflow("docs/missing.md"),
            step_id="1",
            repo_root=tmp_path,
            send=send,
            started_at=1000.0,
            limit_seconds=3600.0,
            clock=lambda: 1000.0 + 25 * 60,
        )
    )
    assert prompts and "経過 25 分 / 上限 60 分" in prompts[0]
    assert "docs/missing.md" in prompts[0]


def test_continuation_message_omits_time_without_limit(tmp_path: Path) -> None:
    prompts: list[str] = []

    async def send(_session: object, prompt: str) -> object:
        prompts.append(prompt)
        return object()

    _run(
        _continue_for_missing_outputs(
            object(),
            ctx=OrchestratorContext(),
            workflow=_workflow("docs/missing.md"),
            step_id="1",
            repo_root=tmp_path,
            send=send,
        )
    )
    assert prompts and "経過" not in prompts[0]
