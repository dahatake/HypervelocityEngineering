"""Real SQLite concurrency contracts for durable resume.

Traceability: NFR-CONC-02, FR-CLI-90.

These tests use local temporary databases and the multiprocessing ``spawn``
context.  They do not create SDK sessions or make network, Azure, or GitHub
calls.
"""

from __future__ import annotations

from multiprocessing.process import BaseProcess
import multiprocessing
import os
from pathlib import Path
from queue import Empty
from threading import BrokenBarrierError
import time
from typing import Any, Callable

import pytest


_EXECUTION_ID = "execution-concurrency"
_INSTANCE_ID = "aas-1"
_WORKFLOW_ID = "aas"
_SYNC_TIMEOUT_SECONDS = 15.0
_PROCESS_JOIN_TIMEOUT_SECONDS = 5.0


def _acquire_same_cas_worker(
    database_path: str,
    execution_id: str,
    instance_id: str,
    expected_state_version: int,
    owner: str,
    start_barrier: Any,
    ready_queue: Any,
    result_queue: Any,
) -> None:
    """Open one process-owned connection and race one fenced CAS acquire."""

    ready = False
    process_id = os.getpid()
    try:
        from hve.run_state_store import DurableStateError, RunStateStore

        with RunStateStore(database_path) as store:
            ready_queue.put(
                {
                    "status": "ready",
                    "owner": owner,
                    "process_id": process_id,
                }
            )
            ready = True
            start_barrier.wait(timeout=_SYNC_TIMEOUT_SECONDS)
            try:
                token = store.acquire_lease(
                    execution_id,
                    instance_id,
                    expected_state_version,
                    owner,
                    now=100.0,
                )
            except DurableStateError as exc:
                result_queue.put(
                    {
                        "outcome": "loser",
                        "owner": owner,
                        "process_id": process_id,
                        "exception_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
            else:
                # Deliberately leave the committed lease in place. Closing a
                # SQLite connection must not make the competing CAS acquirable.
                result_queue.put(
                    {
                        "outcome": "winner",
                        "owner": owner,
                        "process_id": process_id,
                        "generation": token.generation,
                        "state_version": token.state_version,
                    }
                )
    except BaseException as exc:
        target_queue = result_queue if ready else ready_queue
        target_queue.put(
            {
                "status": "worker_error" if not ready else None,
                "outcome": "worker_error" if ready else None,
                "owner": owner,
                "process_id": process_id,
                "exception_type": type(exc).__name__,
                "message": str(exc),
            }
        )


def _collect_messages(queue: Any, count: int, label: str) -> list[dict[str, Any]]:
    """Collect a fixed message count against one monotonic deadline."""

    deadline = time.monotonic() + _SYNC_TIMEOUT_SECONDS
    messages: list[dict[str, Any]] = []
    while len(messages) < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            pytest.fail(
                f"timed out waiting for {label}: received {messages!r}",
                pytrace=False,
            )
        try:
            message = queue.get(timeout=remaining)
        except Empty:
            pytest.fail(
                f"timed out waiting for {label}: received {messages!r}",
                pytrace=False,
            )
        if not isinstance(message, dict):
            pytest.fail(f"invalid {label} message: {message!r}", pytrace=False)
        messages.append(message)
    return messages


def _cleanup_processes(
    processes: list[BaseProcess],
    start_barrier: Any,
    queues: tuple[Any, ...],
) -> None:
    """Bound process cleanup and unblock any worker left at the barrier."""

    try:
        start_barrier.abort()
    except (BrokenBarrierError, OSError, ValueError):
        pass

    deadline = time.monotonic() + _PROCESS_JOIN_TIMEOUT_SECONDS
    for process in processes:
        process.join(timeout=max(0.0, deadline - time.monotonic()))
    for process in processes:
        if process.is_alive():
            process.terminate()
    for process in processes:
        if process.is_alive():
            process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)

    for queue in queues:
        queue.close()
    for queue in queues:
        queue.join_thread()


def _register_execution(
    store: Any,
    repo_root: Path,
    *,
    execution_id: str = _EXECUTION_ID,
) -> tuple[Any, int]:
    """Register one canonical real-store execution and return its service/version."""

    from hve.resume_service import ResumeService, WorkflowDescriptor

    repo_root.mkdir(parents=True, exist_ok=True)
    service = ResumeService(store, repo_root)
    registered_id = service.register_execution(
        "cli",
        (
            WorkflowDescriptor(
                instance_id=_INSTANCE_ID,
                workflow_id=_WORKFLOW_ID,
                ordinal=0,
                mode="standard",
                argv=("orchestrate", "--workflow", _WORKFLOW_ID),
                missing_replay_keys=(),
            ),
        ),
        execution_id=execution_id,
        checkpoint_head="head-at-launch",
    )
    assert registered_id == execution_id
    instance = store.get_instance(execution_id, _INSTANCE_ID)
    assert instance is not None
    return service, int(instance["state_version"])


def _durable_snapshot(store: Any, execution_id: str) -> dict[str, Any]:
    """Capture rows that stale fenced operations are forbidden to mutate."""

    execution = store.get_execution(execution_id)
    instance = store.get_instance(execution_id, _INSTANCE_ID)
    assert execution is not None
    assert instance is not None
    instance_fields = (
        "status",
        "state_version",
        "heartbeat_at",
        "checkpoint_head",
        "current_run_id",
        "attempt_no",
        "lease_owner",
        "lease_generation",
        "lease_expires_at",
    )
    return {
        "execution_updated_at": execution["updated_at"],
        "instance": tuple(instance[name] for name in instance_fields),
        "steps": tuple(
            tuple(row)
            for row in store.list_steps(execution_id, _INSTANCE_ID)
        ),
    }


class TestConcurrentResumeAcquire:
    """NFR-CONC-02: process-level CAS and fenced takeover are serialized."""

    def test_two_spawned_processes_racing_same_cas_have_one_winner(
        self, tmp_path: Path
    ) -> None:
        from hve.run_state_store import RunStateStore

        database_path = tmp_path / "state.sqlite3"
        repo_root = tmp_path / "repo"
        with RunStateStore(database_path) as setup_store:
            _, expected_state_version = _register_execution(
                setup_store,
                repo_root,
            )

        context = multiprocessing.get_context("spawn")
        start_barrier = context.Barrier(2, timeout=_SYNC_TIMEOUT_SECONDS)
        ready_queue = context.Queue()
        result_queue = context.Queue()
        owners = ("resume-owner-a", "resume-owner-b")
        processes = [
            context.Process(
                target=_acquire_same_cas_worker,
                name=f"t33-cas-{index}",
                args=(
                    os.fspath(database_path),
                    _EXECUTION_ID,
                    _INSTANCE_ID,
                    expected_state_version,
                    owner,
                    start_barrier,
                    ready_queue,
                    result_queue,
                ),
            )
            for index, owner in enumerate(owners)
        ]
        started: list[BaseProcess] = []
        readiness: list[dict[str, Any]] = []
        outcomes: list[dict[str, Any]] = []
        try:
            for process in processes:
                process.start()
                started.append(process)

            readiness = _collect_messages(ready_queue, 2, "worker readiness")
            assert {message.get("status") for message in readiness} == {"ready"}, readiness
            assert {message.get("owner") for message in readiness} == set(owners)
            assert len({message.get("process_id") for message in readiness}) == 2

            outcomes = _collect_messages(result_queue, 2, "CAS outcomes")
        finally:
            _cleanup_processes(
                started,
                start_barrier,
                (ready_queue, result_queue),
            )

        assert all(process.exitcode == 0 for process in started), [
            (process.name, process.exitcode) for process in started
        ]
        winners = [item for item in outcomes if item.get("outcome") == "winner"]
        losers = [item for item in outcomes if item.get("outcome") == "loser"]
        assert len(winners) == 1, outcomes
        assert len(losers) == 1, outcomes
        assert losers[0]["exception_type"] == "DurableStateError"
        assert winners[0]["state_version"] == expected_state_version
        assert winners[0]["generation"] == 1

        with RunStateStore(database_path) as verification_store:
            instance = verification_store.get_instance(
                _EXECUTION_ID,
                _INSTANCE_ID,
            )
            assert instance is not None
            assert instance["lease_owner"] == winners[0]["owner"]
            assert instance["lease_generation"] == winners[0]["generation"]
            assert instance["attempt_no"] == 1

    def test_expired_lease_requires_explicit_takeover_and_fences_old_token(
        self, tmp_path: Path
    ) -> None:
        from hve.run_state_store import DurableStateError, RunStateStore

        database_path = tmp_path / "state.sqlite3"
        repo_root = tmp_path / "repo"
        with RunStateStore(database_path) as old_owner_store:
            _, expected_state_version = _register_execution(
                old_owner_store,
                repo_root,
            )
            old_token = old_owner_store.acquire_lease(
                _EXECUTION_ID,
                _INSTANCE_ID,
                expected_state_version,
                "expired-owner",
                now=0.0,
            )

            with RunStateStore(database_path) as takeover_store:
                from hve.resume_service import ResumeService

                service = ResumeService(takeover_store, repo_root)
                preview = service.build_plan(
                    _EXECUTION_ID,
                    current_head="head-at-launch",
                )
                assert "non_terminal" in preview.risk_reasons
                with pytest.raises(
                    DurableStateError,
                    match="explicit recovery action",
                ):
                    service.acquire(preview, "takeover-owner")

                approved = service.build_plan(
                    _EXECUTION_ID,
                    action="restart-step",
                    current_head="head-at-launch",
                )
                current_token = service.acquire(approved, "takeover-owner")
                try:
                    assert current_token.generation == old_token.generation + 1
                    assert current_token.generation > old_token.generation
                    before = _durable_snapshot(takeover_store, _EXECUTION_ID)

                    stale_operations: tuple[tuple[str, Callable[[], Any]], ...] = (
                        (
                            "heartbeat",
                            lambda: old_owner_store.heartbeat(old_token, now=1.0),
                        ),
                        (
                            "transition",
                            lambda: old_owner_store.transition_workflow(
                                old_token,
                                "running",
                            ),
                        ),
                        (
                            "release",
                            lambda: old_owner_store.release_lease(old_token),
                        ),
                    )
                    for operation_name, operation in stale_operations:
                        with pytest.raises(
                            DurableStateError,
                            match="fenced",
                        ):
                            operation()
                        assert _durable_snapshot(
                            takeover_store,
                            _EXECUTION_ID,
                        ) == before, operation_name
                finally:
                    try:
                        takeover_store.release_lease(current_token)
                    except DurableStateError:
                        # Preserve the primary fencing assertion if production
                        # code incorrectly let an old token mutate the lease.
                        pass


class TestResumePlanStaleness:
    """FR-CLI-90: approval snapshots cannot survive durable state changes."""

    def test_state_change_after_plan_presentation_makes_acquire_stale(
        self, tmp_path: Path
    ) -> None:
        from hve.run_state_store import DurableStateError, RunStateStore

        database_path = tmp_path / "state.sqlite3"
        repo_root = tmp_path / "repo"
        with RunStateStore(database_path) as planning_store:
            service, expected_state_version = _register_execution(
                planning_store,
                repo_root,
            )
            presented_plan = service.build_plan(
                _EXECUTION_ID,
                current_head="head-at-launch",
            )
            assert presented_plan.expected_state_version == expected_state_version

            with RunStateStore(database_path) as changing_store:
                changing_token = changing_store.acquire_lease(
                    _EXECUTION_ID,
                    _INSTANCE_ID,
                    expected_state_version,
                    "state-changing-owner",
                    now=time.time(),
                )
                changed_token = changing_store.transition_workflow(
                    changing_token,
                    "running",
                    run_id="state-changing-run",
                )
                changing_store.release_lease(changed_token)

            before_rejected_acquire = _durable_snapshot(
                planning_store,
                _EXECUTION_ID,
            )
            with pytest.raises(DurableStateError, match="stale"):
                service.acquire(presented_plan, "stale-plan-owner")

            assert changed_token.state_version == expected_state_version + 1
            assert _durable_snapshot(
                planning_store,
                _EXECUTION_ID,
            ) == before_rejected_acquire
