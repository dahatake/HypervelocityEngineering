"""Real-process crash acceptance for HVE durable control state.

Traceability: FR-STATE-04, FR-STATE-05, NFR-REL-03.

The tests use a local temporary SQLite database, the multiprocessing ``spawn``
context, and explicit Barrier/Event/Pipe synchronization.  They never create an
SDK session or make network, Azure, or GitHub calls.
"""

from __future__ import annotations

from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
import ctypes
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
from threading import BrokenBarrierError
import sys
import time
from typing import Any

import pytest


_EXECUTION_ID = "execution-crash-injection"
_INSTANCE_ID = "aas-1"
_WORKFLOW_ID = "aas"
_STEP_ID = "1"
_SYNC_TIMEOUT_SECONDS = 20.0
_PROCESS_JOIN_TIMEOUT_SECONDS = 5.0
_GRACEFUL_LIMIT_SECONDS = 3.0
_WORKER_STOP_TIMEOUT_SECONDS = 2.0


def _registration_payload() -> tuple[dict[str, Any], str, str]:
    """Return one deterministic workflow descriptor and its canonical plan."""

    descriptor = {
        "instance_id": _INSTANCE_ID,
        "workflow_id": _WORKFLOW_ID,
        "ordinal": 0,
        "mode": "standard",
        "argv": ["orchestrate", "--workflow", _WORKFLOW_ID],
        "missing_replay_keys": [],
    }
    plan_json = json.dumps(
        {
            "instances": [descriptor],
            "checkpoint_head": "head-at-launch",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    launch_plan_hash = hashlib.sha256(plan_json.encode("utf-8")).hexdigest()
    return descriptor, plan_json, launch_plan_hash


def _register_execution(store: Any, repo_root: str) -> None:
    """Register the real-store fixture before any lease-protected transition."""

    from hve.run_state_store import compute_repo_key

    descriptor, plan_json, launch_plan_hash = _registration_payload()
    store.register_execution(
        _EXECUTION_ID,
        compute_repo_key(repo_root),
        "cli",
        launch_plan_hash,
        plan_json,
        [descriptor],
    )


def _send_child_error(connection: Connection, exc: BaseException) -> None:
    """Best-effort structured child failure reporting without hiding cleanup."""

    try:
        connection.send(
            {
                "phase": "error",
                "exception_type": type(exc).__name__,
                "message": str(exc),
            }
        )
    except (BrokenPipeError, EOFError, OSError):
        pass


def _hard_kill_child(
    database_path: str,
    repo_root: str,
    start_barrier: Any,
    heartbeat_committed: Any,
    cleanup_requested: Any,
    result_connection: Connection,
) -> None:
    """Commit state, acknowledge a real worker heartbeat, then await hard kill."""

    from hve.run_state_store import HeartbeatWorker, RunStateStore

    store: Any = None
    token: Any = None
    worker: Any = None
    original_heartbeat: Any = None
    lease_released = False
    try:
        store = RunStateStore(database_path)
        _register_execution(store, repo_root)
        token = store.acquire_lease(
            _EXECUTION_ID,
            _INSTANCE_ID,
            0,
            "hard-kill-owner",
        )
        token = store.transition_workflow(
            token,
            "running",
            run_id="hard-kill-run",
        )
        token = store.transition_step(
            token,
            _STEP_ID,
            "running",
            phase="main",
            phase_state="running",
            session_id="hard-kill-session",
        )
        instance = store.get_instance(_EXECUTION_ID, _INSTANCE_ID)
        steps = store.list_steps(_EXECUTION_ID, _INSTANCE_ID)
        if instance is None or len(steps) != 1:
            raise AssertionError("committed transition rows are unavailable")
        result_connection.send(
            {
                "phase": "transition_committed",
                "process_id": os.getpid(),
                "state_version": int(instance["state_version"]),
                "workflow_status": str(instance["status"]),
                "step_state_version": int(steps[0]["state_version"]),
                "step_status": str(steps[0]["status"]),
            }
        )

        start_barrier.wait(timeout=_SYNC_TIMEOUT_SECONDS)

        # Instrument only this spawned process.  The Event is set strictly after
        # the real SQLite heartbeat transaction has returned from COMMIT.
        original_heartbeat = RunStateStore.heartbeat

        def observed_heartbeat(
            current_store: Any,
            heartbeat_token: Any,
            *,
            now: float | None = None,
        ) -> None:
            original_heartbeat(current_store, heartbeat_token, now=now)
            heartbeat_committed.set()

        RunStateStore.heartbeat = observed_heartbeat
        worker = HeartbeatWorker(database_path, token)
        worker.start()
        if not heartbeat_committed.wait(timeout=_SYNC_TIMEOUT_SECONDS):
            raise TimeoutError("real heartbeat worker did not commit before deadline")
        worker.raise_if_failed()

        instance = store.get_instance(_EXECUTION_ID, _INSTANCE_ID)
        if instance is None:
            raise AssertionError("workflow instance disappeared after heartbeat")
        worker_thread = getattr(worker, "_thread", None)
        result_connection.send(
            {
                "phase": "kill_ready",
                "state_version": int(instance["state_version"]),
                "workflow_status": str(instance["status"]),
                "heartbeat_at": float(instance["heartbeat_at"]),
                "worker_alive": bool(
                    worker_thread is not None and worker_thread.is_alive()
                ),
            }
        )

        # Normal success never returns from this wait: the parent hard-kills the
        # process only after receiving kill_ready.  The Event exists solely for
        # bounded cleanup when a parent-side assertion fails.
        if not cleanup_requested.wait(timeout=_SYNC_TIMEOUT_SECONDS):
            raise TimeoutError("parent did not hard-kill or release the child")
    except BaseException as exc:
        _send_child_error(result_connection, exc)
    finally:
        if worker is not None:
            try:
                worker.stop(timeout=_WORKER_STOP_TIMEOUT_SECONDS)
            except BaseException:
                pass
        if original_heartbeat is not None:
            RunStateStore.heartbeat = original_heartbeat
        if store is not None and token is not None and not lease_released:
            try:
                store.release_lease(token)
                lease_released = True
            except BaseException:
                pass
        if store is not None:
            try:
                store.close()
            except BaseException:
                pass
        result_connection.close()


def _graceful_cancel_child(
    database_path: str,
    repo_root: str,
    start_barrier: Any,
    cancel_requested: Any,
    result_connection: Connection,
) -> None:
    """Model GUI phase-one cancellation and durably suspend before exit."""

    from hve.run_state_store import HeartbeatWorker, RunStateStore

    store: Any = None
    token: Any = None
    worker: Any = None
    lease_released = False
    worker_stopped = False
    try:
        store = RunStateStore(database_path)
        _register_execution(store, repo_root)
        token = store.acquire_lease(
            _EXECUTION_ID,
            _INSTANCE_ID,
            0,
            "graceful-owner",
        )
        token = store.transition_workflow(
            token,
            "running",
            run_id="graceful-run",
        )
        worker = HeartbeatWorker(database_path, token)
        worker.start()
        instance = store.get_instance(_EXECUTION_ID, _INSTANCE_ID)
        if instance is None:
            raise AssertionError("running workflow instance is unavailable")
        result_connection.send(
            {
                "phase": "running",
                "process_id": os.getpid(),
                "state_version": int(instance["state_version"]),
                "workflow_status": str(instance["status"]),
            }
        )

        start_barrier.wait(timeout=_SYNC_TIMEOUT_SECONDS)
        if not cancel_requested.wait(timeout=_SYNC_TIMEOUT_SECONDS):
            raise TimeoutError("graceful cancellation was not requested")
        cancellation_observed = time.monotonic()

        token = store.transition_workflow(token, "suspended")
        worker.stop(timeout=_WORKER_STOP_TIMEOUT_SECONDS)
        worker.raise_if_failed()
        worker_thread = getattr(worker, "_thread", None)
        worker_stopped = bool(
            worker_thread is not None and not worker_thread.is_alive()
        )
        if not worker_stopped:
            raise AssertionError("heartbeat worker remained alive after stop")
        store.release_lease(token)
        lease_released = True
        instance = store.get_instance(_EXECUTION_ID, _INSTANCE_ID)
        if instance is None:
            raise AssertionError("suspended workflow instance is unavailable")
        final_result = {
            "phase": "finalized",
            "state_version": int(instance["state_version"]),
            "workflow_status": str(instance["status"]),
            "lease_owner": instance["lease_owner"],
            "worker_stopped": worker_stopped,
            "child_finalize_seconds": time.monotonic() - cancellation_observed,
        }
        store.close()
        store = None
        result_connection.send(final_result)
    except BaseException as exc:
        _send_child_error(result_connection, exc)
    finally:
        if worker is not None and not worker_stopped:
            try:
                worker.stop(timeout=_WORKER_STOP_TIMEOUT_SECONDS)
            except BaseException:
                pass
        if store is not None and token is not None and not lease_released:
            try:
                store.release_lease(token)
            except BaseException:
                pass
        if store is not None:
            try:
                store.close()
            except BaseException:
                pass
        result_connection.close()


def _receive_phase(
    connection: Connection,
    expected_phase: str,
    *,
    timeout: float,
) -> dict[str, Any]:
    """Receive one child message against a bounded monotonic wait."""

    if not connection.poll(timeout):
        pytest.fail(
            f"timed out waiting for child phase {expected_phase!r}",
            pytrace=False,
        )
    try:
        message = connection.recv()
    except EOFError:
        pytest.fail(
            f"child pipe closed before phase {expected_phase!r}",
            pytrace=False,
        )
    if not isinstance(message, dict):
        pytest.fail(f"invalid child message: {message!r}", pytrace=False)
    if message.get("phase") == "error":
        pytest.fail(
            "child failed before "
            f"{expected_phase}: {message.get('exception_type')}: "
            f"{message.get('message')}",
            pytrace=False,
        )
    assert message.get("phase") == expected_phase, message
    return message


def _abort_barrier(barrier: Any) -> None:
    try:
        barrier.abort()
    except (BrokenBarrierError, OSError, ValueError):
        pass


def _bounded_process_cleanup(
    process: BaseProcess,
    *,
    started: bool,
    release_event: Any | None = None,
    barrier: Any | None = None,
) -> None:
    """Release cooperative waits, then hard-stop any remaining real process."""

    if release_event is not None:
        release_event.set()
    if barrier is not None:
        _abort_barrier(barrier)
    if not started:
        return
    process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)
    if process.is_alive():
        process.kill()
        process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)
    if process.is_alive():
        process.terminate()
        process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)


def _windows_filesystem_name(path: Path) -> str:
    """Return the Win32 filesystem name for ``path`` without shelling out."""

    if os.name != "nt":
        raise RuntimeError("Win32 filesystem inspection is Windows-only")

    from ctypes import wintypes

    root = Path(path).resolve().anchor
    filesystem_name = ctypes.create_unicode_buffer(261)
    volume_name = ctypes.create_unicode_buffer(261)
    serial_number = wintypes.DWORD()
    maximum_component_length = wintypes.DWORD()
    filesystem_flags = wintypes.DWORD()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_volume_information = kernel32.GetVolumeInformationW
    get_volume_information.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR,
        wintypes.DWORD,
    )
    get_volume_information.restype = wintypes.BOOL
    succeeded = get_volume_information(
        root,
        volume_name,
        len(volume_name),
        ctypes.byref(serial_number),
        ctypes.byref(maximum_component_length),
        ctypes.byref(filesystem_flags),
        filesystem_name,
        len(filesystem_name),
    )
    if not succeeded:
        error_code = ctypes.get_last_error()
        raise OSError(error_code, "GetVolumeInformationW failed")
    return filesystem_name.value


@pytest.mark.skipif(os.name != "nt", reason="NTFS acceptance applies on Windows")
def test_windows_acceptance_database_is_on_ntfs(tmp_path: Path) -> None:
    filesystem = _windows_filesystem_name(tmp_path)

    print(f"[t32] platform={sys.platform} filesystem={filesystem}")
    assert filesystem.casefold() == "ntfs"


def test_hard_kill_preserves_acknowledged_state_and_fresh_heartbeat(
    tmp_path: Path,
) -> None:
    from hve.run_state_store import RunStateStore

    database_path = tmp_path / "hard-kill-state.sqlite3"
    repo_root = tmp_path / "repo-hard-kill"
    repo_root.mkdir()
    context = multiprocessing.get_context("spawn")
    start_barrier = context.Barrier(2, timeout=_SYNC_TIMEOUT_SECONDS)
    heartbeat_committed = context.Event()
    cleanup_requested = context.Event()
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_hard_kill_child,
        name="t32-hard-kill",
        args=(
            os.fspath(database_path),
            os.fspath(repo_root),
            start_barrier,
            heartbeat_committed,
            cleanup_requested,
            send_connection,
        ),
    )
    started = False
    hard_killed = False
    exitcode: int | None = None
    heartbeat_age_seconds: float | None = None
    transition: dict[str, Any] = {}
    kill_ready: dict[str, Any] = {}
    try:
        process.start()
        started = True
        send_connection.close()

        transition = _receive_phase(
            receive_connection,
            "transition_committed",
            timeout=_SYNC_TIMEOUT_SECONDS,
        )
        assert transition["process_id"] == process.pid
        assert transition["workflow_status"] == "running"
        assert transition["step_status"] == "running"
        assert transition["state_version"] == transition["step_state_version"]

        start_barrier.wait(timeout=_SYNC_TIMEOUT_SECONDS)
        kill_ready = _receive_phase(
            receive_connection,
            "kill_ready",
            timeout=_SYNC_TIMEOUT_SECONDS,
        )
        assert heartbeat_committed.is_set()
        assert kill_ready["worker_alive"] is True
        assert kill_ready["workflow_status"] == "running"
        assert kill_ready["state_version"] == transition["state_version"]

        kill_time = time.time()
        heartbeat_age_seconds = kill_time - float(kill_ready["heartbeat_at"])
        assert 0.0 <= heartbeat_age_seconds <= 10.0, (
            "NFR-REL-03 heartbeat freshness exceeded at hard kill: "
            f"age={heartbeat_age_seconds:.6f}s"
        )

        process.kill()
        hard_killed = True
        process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)
        assert not process.is_alive(), "hard-killed child did not exit before deadline"
        exitcode = process.exitcode
        assert exitcode not in (None, 0), exitcode
    finally:
        _bounded_process_cleanup(
            process,
            started=started,
            release_event=None if hard_killed else cleanup_requested,
            barrier=start_barrier,
        )
        receive_connection.close()
        send_connection.close()

    with RunStateStore(database_path) as verification_store:
        assert verification_store.quick_check() is True
        instance = verification_store.get_instance(_EXECUTION_ID, _INSTANCE_ID)
        steps = verification_store.list_steps(_EXECUTION_ID, _INSTANCE_ID)

    assert instance is not None
    assert instance["status"] == "running"
    assert int(instance["state_version"]) == transition["state_version"]
    assert float(instance["heartbeat_at"]) >= float(kill_ready["heartbeat_at"])
    assert instance["lease_owner"] == "hard-kill-owner"
    assert len(steps) == 1
    assert steps[0]["step_id"] == _STEP_ID
    assert steps[0]["status"] == "running"
    assert int(steps[0]["state_version"]) == transition["step_state_version"]
    assert heartbeat_age_seconds is not None
    print(
        "[t32] hard_kill "
        f"heartbeat_age_seconds={heartbeat_age_seconds:.6f} "
        f"state_version={instance['state_version']} quick_check=ok "
        f"exitcode={exitcode}"
    )


def test_graceful_cancel_suspends_and_stops_worker_within_three_seconds(
    tmp_path: Path,
) -> None:
    from hve.run_state_store import RunStateStore

    database_path = tmp_path / "graceful-state.sqlite3"
    repo_root = tmp_path / "repo-graceful"
    repo_root.mkdir()
    context = multiprocessing.get_context("spawn")
    start_barrier = context.Barrier(2, timeout=_SYNC_TIMEOUT_SECONDS)
    cancel_requested = context.Event()
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_graceful_cancel_child,
        name="t32-graceful-cancel",
        args=(
            os.fspath(database_path),
            os.fspath(repo_root),
            start_barrier,
            cancel_requested,
            send_connection,
        ),
    )
    started = False
    finalized: dict[str, Any] = {}
    elapsed_seconds: float | None = None
    try:
        process.start()
        started = True
        send_connection.close()

        running = _receive_phase(
            receive_connection,
            "running",
            timeout=_SYNC_TIMEOUT_SECONDS,
        )
        assert running["process_id"] == process.pid
        assert running["workflow_status"] == "running"

        start_barrier.wait(timeout=_SYNC_TIMEOUT_SECONDS)
        cancellation_started = time.monotonic()
        cancel_requested.set()
        finalized = _receive_phase(
            receive_connection,
            "finalized",
            timeout=_GRACEFUL_LIMIT_SECONDS,
        )
        elapsed_seconds = time.monotonic() - cancellation_started

        assert elapsed_seconds <= _GRACEFUL_LIMIT_SECONDS, (
            "NFR-REL-03 GUI graceful window exceeded: "
            f"elapsed={elapsed_seconds:.6f}s"
        )
        assert finalized["child_finalize_seconds"] <= _GRACEFUL_LIMIT_SECONDS
        assert finalized["workflow_status"] == "suspended"
        assert finalized["worker_stopped"] is True
        assert finalized["lease_owner"] is None

        process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)
        assert not process.is_alive(), "gracefully finalized child did not exit"
        assert process.exitcode == 0
    finally:
        _bounded_process_cleanup(
            process,
            started=started,
            release_event=cancel_requested,
            barrier=start_barrier,
        )
        receive_connection.close()
        send_connection.close()

    with RunStateStore(database_path) as verification_store:
        assert verification_store.quick_check() is True
        instance = verification_store.get_instance(_EXECUTION_ID, _INSTANCE_ID)

    assert instance is not None
    assert instance["status"] == "suspended"
    assert int(instance["state_version"]) == finalized["state_version"]
    assert instance["lease_owner"] is None
    assert instance["lease_expires_at"] is None
    assert elapsed_seconds is not None
    print(
        "[t32] graceful_cancel "
        f"elapsed_seconds={elapsed_seconds:.6f} "
        f"child_finalize_seconds={finalized['child_finalize_seconds']:.6f} "
        f"state_version={instance['state_version']} worker_stopped=true"
    )
