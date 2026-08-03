"""Unit tests for the ASDW Step 1.3 byte-pinned launcher boundary."""
from __future__ import annotations

import os
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from hve import asdw_data_script_launcher as launcher


_SAMPLE_TEXT = (
    '{"entities":{"AuditRecord":[{"auditEventId":"audit-1",'
    '"result":"sample-success"}]}}\n'
)
_IDENTITY_CLIENT_ID = "00000000-0000-0000-0000-000000000000"
# Captured before the autouse fixture replaces it, for the fail-closed test.
_REAL_IDENTITY_READ_BACK = launcher._resolve_deploy_identity_client_id


@pytest.fixture(autouse=True)
def _stub_identity_read_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the post-prep client ID read-back from shelling out to Azure CLI."""
    monkeypatch.setattr(
        launcher,
        "_resolve_deploy_identity_client_id",
        lambda _environment: _IDENTITY_CLIENT_ID,
    )


def _write_stage_inputs(root: Path) -> dict[str, Path]:
    files = {
        launcher._PREP: "#!/usr/bin/env bash\necho prep\n",
        launcher._CREATE: "#!/usr/bin/env bash\necho create\n",
        launcher._REGISTRATION: "#!/usr/bin/env bash\necho registration\n",
        launcher._VERIFY: "#!/usr/bin/env bash\necho verify\n",
        launcher._SAMPLE: _SAMPLE_TEXT,
        launcher._DESIGN: "# design\n",
    }
    result: dict[str, Path] = {}
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        result[relative] = path
    return result


_COMPLETE_VERIFY_ENVIRONMENT = {
    "DATA_NETWORK_MODE": "private",
    "DATA_VNET_NAME": "vnet-example",
    "DATA_PRIVATE_ENDPOINT_SUBNET_ID": "/subs/x/pe-subnet",
    "DATA_ACI_SUBNET_ID": "/subs/x/aci-subnet",
    "DATA_NAT_GATEWAY_NAME": "nat-example",
    "DATA_DEPLOY_IDENTITY_ID": "/subs/x/identity",
    "DATA_DEPLOY_IDENTITY_CLIENT_ID": "00000000-0000-0000-0000-000000000000",
    "SQL_PRIVATE_ENDPOINT_NAME": "sql-pe",
    "COSMOS_PRIVATE_ENDPOINT_NAME": "cosmos-pe",
    "SQL_PRIVATE_DNS_ZONE": "privatelink.database.windows.net",
    "COSMOS_PRIVATE_DNS_ZONE": "privatelink.documents.azure.com",
    "DATA_VERIFY_ACI_IMAGE": "example.azurecr.io/verify:latest",
    "SQL_SERVER": "sql-example",
}


def _stage_markers(root: Path, environment: dict[str, str]) -> dict[str, Path]:
    markers = launcher._stage_success_marker_paths(root, environment)
    assert markers is not None
    return markers


def test_launcher_rejects_unknown_stage(tmp_path: Path) -> None:
    with pytest.raises(launcher.ScriptLauncherError, match="unsupported"):
        launcher.execute_stage("other", repo_root=tmp_path)


def test_launcher_blocks_execution_when_validator_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    called = False
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: ["invalid"])

    def run(*_args, **_kwargs):
        nonlocal called
        called = True
        return subprocess.CompletedProcess([], 0)

    with pytest.raises(launcher.ScriptLauncherError, match="contract failed"):
        launcher.execute_stage("prep", repo_root=tmp_path, process_runner=run)

    assert called is False


def test_launcher_executes_the_snapshot_not_reopened_script_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_stage_inputs(tmp_path)
    captured: dict[str, object] = {}
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")

    def validate_then_replace(_stage, _root, _snapshots):
        paths[launcher._PREP].write_text(
            "#!/usr/bin/env bash\necho replaced\n",
            encoding="utf-8",
            newline="\n",
        )
        return []

    def run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 7)

    monkeypatch.setattr(launcher, "_validate_stage", validate_then_replace)

    result = launcher.execute_stage("prep", repo_root=tmp_path, process_runner=run)

    assert result == 7
    assert captured["argv"] == ["trusted-bash", "--noprofile", "--norc", "-s"]
    assert captured["input"] == b"#!/usr/bin/env bash\necho prep\n"
    assert captured["text"] is False
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["HVE_ASDW_SCRIPT_DIR"] == str(paths[launcher._PREP].parent)
    assert environment["HVE_ASDW_SCRIPT_STAGE"] == "prep"
    assert paths[launcher._PREP].read_text(encoding="utf-8").endswith("replaced\n")


def test_create_stage_supplies_a_stable_sample_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_stage_inputs(tmp_path)
    captured: dict[str, object] = {}
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")

    def validate_then_replace_sample(_stage, _root, snapshots):
        assert snapshots[launcher._SAMPLE].text == _SAMPLE_TEXT
        paths[launcher._SAMPLE].write_text(
            '{"entities": {"changed": []}}\n',
            encoding="utf-8",
            newline="\n",
        )
        return []

    monkeypatch.setattr(launcher, "_validate_stage", validate_then_replace_sample)

    def run(argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0)

    assert launcher.execute_stage(
        "create",
        repo_root=tmp_path,
        environment={"DATA_CREATE_RUN_ID": "a" * 32},
        process_runner=run,
    ) == 0
    assert captured["input"] == paths[launcher._CREATE].read_bytes()
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["HVE_ASDW_SAMPLE_DATA_JSON"] == _SAMPLE_TEXT
    assert paths[launcher._SAMPLE].read_text(encoding="utf-8") != environment[
        "HVE_ASDW_SAMPLE_DATA_JSON"
    ]


def test_registration_supplies_audit_payload_from_stable_sample_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_stage_inputs(tmp_path)
    captured: dict[str, object] = {}
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")

    def validate_then_replace_sample(_stage, _root, snapshots):
        assert snapshots[launcher._SAMPLE].text == _SAMPLE_TEXT
        paths[launcher._SAMPLE].write_text(
            '{"entities":{"AuditRecord":[{"auditEventId":"changed"}]}}\n',
            encoding="utf-8",
            newline="\n",
        )
        return []

    monkeypatch.setattr(launcher, "_validate_stage", validate_then_replace_sample)

    def run(argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0)

    assert launcher.execute_stage(
        "registration",
        repo_root=tmp_path,
        environment={
            "DATA_REGISTER_RUN_ID": "b" * 32,
            "AUDIT_RECORD_JSON": '{"auditEventId":"stale"}',
        },
        process_runner=run,
    ) == 0
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert json.loads(environment["AUDIT_RECORD_JSON"]) == {
        "auditEventId": "audit-1",
        "result": "sample-success",
    }


def test_hve_stages_require_successful_predecessors_in_the_same_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    run_id = "pytest-prep-order"
    work_root = tmp_path / "work" / "run" / run_id
    work_root.mkdir(parents=True)
    environment = {
        **_COMPLETE_VERIFY_ENVIRONMENT,
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(work_root),
        "DATA_CREATE_RUN_ID": "a" * 32,
        "DATA_REGISTER_RUN_ID": "b" * 32,
        "DATA_VERIFY_RUN_ID": "c" * 32,
    }
    process_calls: list[str] = []
    captured_contract_values: list[tuple[str, str, str]] = []

    def run(argv, **kwargs):
        child_environment = kwargs["env"]
        process_calls.append(str(child_environment["HVE_ASDW_SCRIPT_STAGE"]))
        captured_contract_values.append(
            (
                child_environment["DATA_VNET_NAME"],
                child_environment["DATA_VERIFY_ACI_IMAGE"],
                child_environment["SQL_SERVER"],
            )
        )
        return subprocess.CompletedProcess(argv, 0)

    for stage, predecessor in (
        ("create", "prep"),
        ("registration", "create"),
        ("verify", "registration"),
    ):
        with pytest.raises(launcher.ScriptLauncherError, match=f"successful {predecessor}"):
            launcher.execute_stage(
                stage,
                repo_root=tmp_path,
                environment=environment,
                process_runner=run,
            )
    assert process_calls == []

    assert launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        environment=environment,
        process_runner=run,
    ) == 0
    markers = _stage_markers(tmp_path, environment)
    assert markers["prep"].read_text(
        encoding="utf-8"
    ) == f"{run_id}\n"
    with pytest.raises(launcher.ScriptLauncherError, match="successful create"):
        launcher.execute_stage(
            "registration",
            repo_root=tmp_path,
            environment=environment,
            process_runner=run,
        )
    assert launcher.execute_stage(
        "create",
        repo_root=tmp_path,
        environment=environment,
        process_runner=run,
    ) == 0
    assert markers["create"].read_text(
        encoding="utf-8"
    ) == f"{run_id}\n"
    with pytest.raises(launcher.ScriptLauncherError, match="successful registration"):
        launcher.execute_stage(
            "verify",
            repo_root=tmp_path,
            environment=environment,
            process_runner=run,
        )
    assert launcher.execute_stage(
        "registration",
        repo_root=tmp_path,
        environment=environment,
        process_runner=run,
    ) == 0
    assert markers["registration"].read_text(
        encoding="utf-8"
    ) == f"{run_id}\n"
    assert launcher.execute_stage(
        "verify",
        repo_root=tmp_path,
        environment=environment,
        process_runner=run,
    ) == 0
    assert process_calls == ["prep", "create", "registration", "verify"]
    assert captured_contract_values == [
        ("vnet-example", "example.azurecr.io/verify:latest", "sql-example")
    ] * 4


def test_failed_hve_prep_invalidates_its_previous_success_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    run_id = "pytest-prep-failure"
    work_root = tmp_path / "work" / "run" / run_id
    work_root.mkdir(parents=True)
    environment = {
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(work_root),
        "DATA_CREATE_RUN_ID": "a" * 32,
        "DATA_REGISTER_RUN_ID": "b" * 32,
        "DATA_VERIFY_RUN_ID": "c" * 32,
    }

    def successful_run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0)

    def failed_run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 1)

    assert launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        environment=environment,
        process_runner=successful_run,
    ) == 0
    assert launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        environment=environment,
        process_runner=failed_run,
    ) == 1
    markers = _stage_markers(tmp_path, environment)
    assert not markers["prep"].exists()
    assert not markers["create"].exists()
    assert not markers["registration"].exists()
    with pytest.raises(launcher.ScriptLauncherError, match="successful prep"):
        launcher.execute_stage(
            "create",
            repo_root=tmp_path,
            environment=environment,
            process_runner=successful_run,
        )


@pytest.mark.parametrize(
    ("failed_stage", "downstream_stage", "required_marker"),
    (
        ("create", "registration", launcher._CREATE_SUCCESS_MARKER),
        ("registration", "verify", launcher._REGISTRATION_SUCCESS_MARKER),
    ),
)
def test_failed_hve_intermediate_stage_invalidates_its_downstream_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_stage: str,
    downstream_stage: str,
    required_marker: str,
) -> None:
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    run_id = f"pytest-{failed_stage}-failure"
    work_root = tmp_path / "work" / "run" / run_id
    work_root.mkdir(parents=True)
    environment = {
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(work_root),
        "DATA_CREATE_RUN_ID": "a" * 32,
        "DATA_REGISTER_RUN_ID": "b" * 32,
        "DATA_VERIFY_RUN_ID": "c" * 32,
    }

    def successful_run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0)

    def failed_run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 1)

    assert launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        environment=environment,
        process_runner=successful_run,
    ) == 0
    assert launcher.execute_stage(
        "create",
        repo_root=tmp_path,
        environment=environment,
        process_runner=successful_run,
    ) == 0
    if failed_stage == "registration":
        assert launcher.execute_stage(
            "registration",
            repo_root=tmp_path,
            environment=environment,
            process_runner=successful_run,
        ) == 0

    assert launcher.execute_stage(
        failed_stage,
        repo_root=tmp_path,
        environment=environment,
        process_runner=failed_run,
    ) == 1
    markers = _stage_markers(tmp_path, environment)
    required_stage = {
        launcher._CREATE_SUCCESS_MARKER: "create",
        launcher._REGISTRATION_SUCCESS_MARKER: "registration",
    }[required_marker]
    assert not markers[required_stage].exists()
    with pytest.raises(launcher.ScriptLauncherError, match=f"successful {failed_stage}"):
        launcher.execute_stage(
            downstream_stage,
            repo_root=tmp_path,
            environment=environment,
            process_runner=successful_run,
        )


def test_missing_prep_marker_invalidates_stale_create_marker_before_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    run_id = "pytest-missing-prep-marker"
    work_root = tmp_path / "work" / "run" / run_id
    work_root.mkdir(parents=True)
    environment = {
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(work_root),
        "DATA_CREATE_RUN_ID": "a" * 32,
        "DATA_REGISTER_RUN_ID": "b" * 32,
        "DATA_VERIFY_RUN_ID": "c" * 32,
    }

    def successful_run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0)

    assert launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        environment=environment,
        process_runner=successful_run,
    ) == 0
    assert launcher.execute_stage(
        "create",
        repo_root=tmp_path,
        environment=environment,
        process_runner=successful_run,
    ) == 0
    markers = _stage_markers(tmp_path, environment)
    markers["prep"].unlink()

    with pytest.raises(launcher.ScriptLauncherError, match="successful prep"):
        launcher.execute_stage(
            "create",
            repo_root=tmp_path,
            environment=environment,
            process_runner=successful_run,
        )
    assert not markers["create"].exists()
    with pytest.raises(launcher.ScriptLauncherError, match="successful create"):
        launcher.execute_stage(
            "registration",
            repo_root=tmp_path,
            environment=environment,
            process_runner=successful_run,
        )


@pytest.mark.parametrize("create_exit_code", (0, 1))
def test_hve_stage_lock_prevents_concurrent_create_from_racing_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    create_exit_code: int,
) -> None:
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    run_id = f"pytest-create-lock-{create_exit_code}"
    work_root = tmp_path / "work" / "run" / run_id
    work_root.mkdir(parents=True)
    environment = {
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(work_root),
        "DATA_CREATE_RUN_ID": "a" * 32,
        "DATA_REGISTER_RUN_ID": "b" * 32,
        "DATA_VERIFY_RUN_ID": "c" * 32,
    }
    entered = threading.Event()
    release = threading.Event()
    create_result: list[int] = []
    create_error: list[BaseException] = []
    blocked_process_called = False

    def successful_run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0)

    assert launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        environment=environment,
        process_runner=successful_run,
    ) == 0

    def blocked_create_run(argv, **_kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return subprocess.CompletedProcess(argv, create_exit_code)

    def run_create() -> None:
        try:
            create_result.append(
                launcher.execute_stage(
                    "create",
                    repo_root=tmp_path,
                    environment=environment,
                    process_runner=blocked_create_run,
                )
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            create_error.append(exc)

    worker = threading.Thread(target=run_create)
    worker.start()
    assert entered.wait(timeout=5)

    def must_not_run(*_args, **_kwargs):
        nonlocal blocked_process_called
        blocked_process_called = True
        return subprocess.CompletedProcess([], 0)

    with pytest.raises(launcher.ScriptLauncherError, match="already running"):
        launcher.execute_stage(
            "create",
            repo_root=tmp_path,
            environment=environment,
            process_runner=must_not_run,
        )
    with pytest.raises(launcher.ScriptLauncherError, match="already running"):
        launcher.execute_stage(
            "registration",
            repo_root=tmp_path,
            environment=environment,
            process_runner=must_not_run,
        )
    assert blocked_process_called is False

    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert create_error == []
    assert create_result == [create_exit_code]
    if create_exit_code == 0:
        assert launcher.execute_stage(
            "registration",
            repo_root=tmp_path,
            environment=environment,
            process_runner=successful_run,
        ) == 0
    else:
        with pytest.raises(launcher.ScriptLauncherError, match="successful create"):
            launcher.execute_stage(
                "registration",
                repo_root=tmp_path,
                environment=environment,
                process_runner=successful_run,
            )


def test_hve_stage_lock_is_released_when_lock_owner_process_exits(
    tmp_path: Path,
) -> None:
    run_id = "pytest-lock-owner-exit"
    work_root = tmp_path / "work" / "run" / run_id
    work_root.mkdir(parents=True)
    environment = {
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(work_root),
    }
    lock_path = launcher._stage_execution_lock_path(
        _stage_markers(tmp_path, environment)
    )
    script = (
        "from pathlib import Path\n"
        "import os\n"
        "from hve.asdw_data_script_launcher import _acquire_stage_execution_lock\n"
        "lock = _acquire_stage_execution_lock(Path(__import__('sys').argv[1]))\n"
        "os._exit(0)\n"
    )
    child = subprocess.run(
        [sys.executable, "-c", script, str(lock_path)],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
    )
    assert child.returncode == 0

    lock = launcher._acquire_stage_execution_lock(lock_path)
    launcher._release_stage_execution_lock(lock)


def test_hve_stage_lock_rejects_run_root_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    run_id = "pytest-run-root-link"
    expected_root = tmp_path / "work" / "run" / run_id
    expected_root.parent.mkdir(parents=True)
    outside = tmp_path / "outside-run-root"
    outside.mkdir()
    try:
        expected_root.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    environment = {
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(expected_root),
    }

    with pytest.raises(launcher.ScriptLauncherError, match="symlink or reparse"):
        launcher.execute_stage(
            "prep",
            repo_root=tmp_path,
            environment=environment,
            process_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0),
        )


def test_hve_stage_metadata_remains_outside_replaced_run_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    run_id = "pytest-run-root-recheck"
    work_root = tmp_path / "work" / "run" / run_id
    work_root.mkdir(parents=True)
    environment = {
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(work_root),
    }
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    markers = _stage_markers(tmp_path, environment)
    moved_root = tmp_path / "moved-run-root"
    process_calls: list[str] = []

    def rename_run_root(argv, **kwargs):
        work_root.rename(moved_root)
        process_calls.append(str(kwargs["env"]["HVE_ASDW_SCRIPT_STAGE"]))
        return subprocess.CompletedProcess(argv, 0)

    assert launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        environment=environment,
        process_runner=rename_run_root,
    ) == 0
    assert markers["prep"].read_text(encoding="utf-8") == f"{run_id}\n"
    work_root.write_text("replaced", encoding="utf-8")
    process_called = False

    def must_not_run(*_args, **_kwargs):
        nonlocal process_called
        process_called = True
        return subprocess.CompletedProcess([], 0)

    with pytest.raises(launcher.ScriptLauncherError, match="must not contain"):
        launcher.execute_stage(
            "create",
            repo_root=tmp_path,
            environment=environment,
            process_runner=must_not_run,
        )
    assert process_calls == ["prep"]
    assert process_called is False


def test_hve_stage_lock_rejects_existing_hard_link(
    tmp_path: Path,
) -> None:
    run_id = "pytest-lock-hard-link"
    work_root = tmp_path / "work" / "run" / run_id
    work_root.mkdir(parents=True)
    source = tmp_path / "outside-lock-source"
    source.write_bytes(b"\0")
    environment = {
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(work_root),
    }
    lock_path = launcher._stage_execution_lock_path(
        _stage_markers(tmp_path, environment)
    )
    try:
        os.link(source, lock_path)
    except OSError as exc:
        pytest.skip(f"hard link unavailable: {exc}")

    with pytest.raises(launcher.ScriptLauncherError, match="not a regular file"):
        launcher._acquire_stage_execution_lock(lock_path)


def test_hve_stage_lock_cleanup_preserves_contract_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    run_id = "pytest-lock-cleanup"
    work_root = tmp_path / "work" / "run" / run_id
    work_root.mkdir(parents=True)
    environment = {
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(work_root),
    }
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: ["contract invalid"])
    monkeypatch.setattr(
        launcher,
        "_release_stage_execution_lock",
        lambda _lock: (_ for _ in ()).throw(launcher.ScriptLauncherError("release failed")),
    )

    with pytest.raises(launcher.ScriptLauncherError, match="contract failed"):
        launcher.execute_stage(
            "prep",
            repo_root=tmp_path,
            environment=environment,
            process_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0),
        )


def test_hve_stage_lock_cleanup_failure_fails_a_successful_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    run_id = "pytest-lock-cleanup-success"
    work_root = tmp_path / "work" / "run" / run_id
    work_root.mkdir(parents=True)
    environment = {
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(work_root),
    }
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")

    def release_then_fail(lock: launcher._StageExecutionLock) -> None:
        os.close(lock.descriptor)
        raise launcher.ScriptLauncherError("release failed")

    monkeypatch.setattr(launcher, "_release_stage_execution_lock", release_then_fail)

    with pytest.raises(launcher.ScriptLauncherError, match="release failed"):
        launcher.execute_stage(
            "prep",
            repo_root=tmp_path,
            environment=environment,
            process_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0),
        )
    markers = _stage_markers(tmp_path, environment)
    assert not markers["prep"].exists()
    with pytest.raises(launcher.ScriptLauncherError, match="successful prep"):
        launcher.execute_stage(
            "create",
            repo_root=tmp_path,
            environment=environment,
            process_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0),
        )


def test_hve_stage_lock_cleanup_failure_preserves_nonzero_stage_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_stage_inputs(tmp_path)
    run_id = "pytest-lock-cleanup-nonzero"
    work_root = tmp_path / "work" / "run" / run_id
    work_root.mkdir(parents=True)
    environment = {
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(work_root),
    }
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")

    def release_then_fail(lock: launcher._StageExecutionLock) -> None:
        os.close(lock.descriptor)
        raise launcher.ScriptLauncherError("release failed")

    monkeypatch.setattr(launcher, "_release_stage_execution_lock", release_then_fail)

    assert launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        environment=environment,
        process_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1),
    ) == 1
    assert "lock cleanup failed after stage exit 1" in capsys.readouterr().err


def test_hve_stage_lock_rejects_contender_in_another_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    run_id = "pytest-process-lock"
    work_root = tmp_path / "work" / "run" / run_id
    work_root.mkdir(parents=True)
    environment = {
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(work_root),
        "DATA_CREATE_RUN_ID": "a" * 32,
    }

    def successful_run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0)

    assert launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        environment=environment,
        process_runner=successful_run,
    ) == 0
    lock_path = launcher._stage_execution_lock_path(
        _stage_markers(tmp_path, environment)
    )
    holder = (
        "from pathlib import Path\n"
        "import sys\n"
        "from hve.asdw_data_script_launcher import _acquire_stage_execution_lock\n"
        "lock = _acquire_stage_execution_lock(Path(sys.argv[1]))\n"
        "print('READY', flush=True)\n"
        "sys.stdin.readline()\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", holder, str(lock_path)],
        cwd=Path(__file__).resolve().parents[2],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    assert child.stdin is not None
    try:
        assert child.stdout.readline().strip() == "READY"
        process_called = False

        def must_not_run(*_args, **_kwargs):
            nonlocal process_called
            process_called = True
            return subprocess.CompletedProcess([], 0)

        with pytest.raises(launcher.ScriptLauncherError, match="already running"):
            launcher.execute_stage(
                "create",
                repo_root=tmp_path,
                environment=environment,
                process_runner=must_not_run,
            )
        assert process_called is False
    finally:
        child.stdin.write("\n")
        child.stdin.flush()
        assert child.wait(timeout=5) == 0

    assert launcher.execute_stage(
        "create",
        repo_root=tmp_path,
        environment=environment,
        process_runner=successful_run,
    ) == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows case-insensitive namespace")
def test_hve_stage_rejects_case_only_run_id_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    canonical_run_id = "Run-Case-Alias"
    work_root = tmp_path / "work" / "run" / canonical_run_id
    work_root.mkdir(parents=True)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    alias_environment = {
        "HVE_RUN_ID": canonical_run_id.lower(),
        "HVE_WORK_ROOT": str(work_root),
    }
    process_called = False

    def must_not_run(*_args, **_kwargs):
        nonlocal process_called
        process_called = True
        return subprocess.CompletedProcess([], 0)

    with pytest.raises(launcher.ScriptLauncherError, match="directory case"):
        launcher.execute_stage(
            "prep",
            repo_root=tmp_path,
            environment=alias_environment,
            process_runner=must_not_run,
        )
    assert process_called is False


@pytest.mark.parametrize(
    ("stage", "run_id_key"),
    (("create", "DATA_CREATE_RUN_ID"), ("registration", "DATA_REGISTER_RUN_ID")),
)
def test_launcher_generates_stage_run_id_when_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    run_id_key: str,
) -> None:
    """RC-1: launcher は verify 契約の caller として、run-id 未設定時に 32hex を生成し child env へ渡す。"""
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    captured: dict[str, object] = {}

    def run(_argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess([], 0)

    assert launcher.execute_stage(stage, repo_root=tmp_path, process_runner=run) == 0
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert launcher._RUN_ID_PATTERN.fullmatch(environment[run_id_key])


def test_launcher_uses_a_valid_external_stage_run_id_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既に有効な run-id が env にある場合は生成せずそのまま使う。"""
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    external = "a" * 32
    captured: dict[str, object] = {}

    def run(_argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess([], 0)

    assert launcher.execute_stage(
        "create",
        repo_root=tmp_path,
        environment={"DATA_CREATE_RUN_ID": external},
        process_runner=run,
    ) == 0
    child_environment = captured["env"]
    assert isinstance(child_environment, dict)
    assert child_environment["DATA_CREATE_RUN_ID"] == external


def test_verify_stage_supplies_sanitized_parent_environment_to_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify receives the same validated parent environment as prior stages."""
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    captured: dict[str, object] = {}

    def run(_argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess([], 0)

    assert launcher.execute_stage(
        "verify",
        repo_root=tmp_path,
        environment=_COMPLETE_VERIFY_ENVIRONMENT,
        process_runner=run,
    ) == 0
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["DATA_NETWORK_MODE"] == "private"
    assert environment["SQL_SERVER"] == "sql-example"
    assert launcher._RUN_ID_PATTERN.fullmatch(environment["DATA_VERIFY_RUN_ID"])


def test_verify_stage_parent_environment_cannot_override_launcher_owned_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parent input cannot override launcher-owned HVE stage keys."""
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    captured: dict[str, object] = {}

    def run(_argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess([], 0)

    assert launcher.execute_stage(
        "verify",
        repo_root=tmp_path,
        environment={
            **_COMPLETE_VERIFY_ENVIRONMENT,
            "HVE_ASDW_SCRIPT_STAGE": "spoofed",
        },
        process_runner=run,
    ) == 0
    child_environment = captured["env"]
    assert isinstance(child_environment, dict)
    assert child_environment["HVE_ASDW_SCRIPT_STAGE"] == "verify"


def test_verify_environment_requires_network_mode() -> None:
    """Missing mode is a launcher environment contract defect."""
    with pytest.raises(launcher.ScriptLauncherError, match="must define DATA_NETWORK_MODE"):
        launcher._require_verify_environment({"SQL_SERVER": "sql-example"})


def test_verify_environment_rejects_missing_private_keys() -> None:
    """Private verify fails closed before the child when launcher inputs are incomplete."""
    with pytest.raises(
        launcher.ScriptLauncherError,
        match="missing required private-mode verifier keys",
    ):
        launcher._require_verify_environment(
            {"DATA_NETWORK_MODE": "private", "SQL_SERVER": "sql-example"}
        )


def test_verify_environment_lists_all_missing_keys() -> None:
    """Missing launcher inputs are consolidated and not blamed on the verifier."""
    with pytest.raises(launcher.ScriptLauncherError) as exc:
        launcher._require_verify_environment(
            {"DATA_NETWORK_MODE": "private", "DATA_VNET_NAME": "vnet"}
        )
    message = str(exc.value)
    assert "DATA_VERIFY_ACI_IMAGE" in message
    assert "DATA_NAT_GATEWAY_NAME" in message
    assert "not a verify-script" in message
    assert "DATA_VERIFY_RUN_ID" not in message


def test_verify_environment_skips_private_keys_for_public_mode() -> None:
    """public mode では verify が早期 exit するため network キーを要求しない。"""
    launcher._require_verify_environment({"DATA_NETWORK_MODE": "public"})


def test_verify_environment_accepts_complete_private_inputs() -> None:
    """Complete private launcher inputs pass without an intermediate file."""
    launcher._require_verify_environment(_COMPLETE_VERIFY_ENVIRONMENT)
    for key in launcher._ASDW_DATA_DEPLOY_NETWORK_KEYS:
        assert _COMPLETE_VERIFY_ENVIRONMENT.get(key)


def test_verify_stage_ignores_stale_data_deploy_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A previous-run env file is not a launcher input or source of truth."""
    _write_stage_inputs(tmp_path)
    stale = tmp_path / "src" / "infra" / "azure" / "data-deploy.env"
    stale.write_text("DATA_NETWORK_MODE=blocked\n", encoding="utf-8", newline="\n")
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    captured: dict[str, object] = {}

    def run(_argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess([], 0)

    assert launcher.execute_stage(
        "verify",
        repo_root=tmp_path,
        environment=_COMPLETE_VERIFY_ENVIRONMENT,
        process_runner=run,
    ) == 0
    child_environment = captured["env"]
    assert isinstance(child_environment, dict)
    assert child_environment["DATA_NETWORK_MODE"] == "private"


def test_launcher_preserves_utf8_script_bytes_and_removes_bash_startup_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_stage_inputs(tmp_path)
    raw = "#!/usr/bin/env bash\nprintf '%s\\n' '監査'\n".encode("utf-8")
    paths[launcher._PREP].write_bytes(raw)
    captured: dict[str, object] = {}
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")

    def run(_argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess([], 0)

    assert launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        environment={
            "bash_env": "untrusted-startup.sh",
            "Env": "untrusted-env.sh",
            "Path": "untrusted-path",
            "Bash_Func_untrusted%%": "() { echo unsafe; }",
            "ld_preload": "untrusted-loader.so",
        },
        process_runner=run,
    ) == 0

    environment = captured["env"]
    assert isinstance(environment, dict)
    assert captured["input"] == raw
    assert environment.get("BASH_ENV") is None
    assert environment.get("bash_env") is None
    assert environment.get("ENV") is None
    assert environment.get("Env") is None
    assert environment.get("Path") is None
    assert environment["PATH"] != "untrusted-path"
    assert not any(key.casefold().startswith(("bash_func_", "ld_")) for key in environment)


def test_child_environment_uses_an_explicit_data_deploy_allowlist() -> None:
    child = launcher._build_child_environment(
        {
            "RESOURCE_GROUP": "example-rg",
            "DATA_NETWORK_MODE": "private",
            "UNRELATED_SECRET": "must-not-reach-child",
            "DATA_DEPLOY_ENV": "src/infra/azure/data-deploy.env",
        },
        "prep",
    )

    assert child["RESOURCE_GROUP"] == "example-rg"
    assert child["DATA_NETWORK_MODE"] == "private"
    assert child["HVE_ASDW_SCRIPT_STAGE"] == "prep"
    assert "UNRELATED_SECRET" not in child
    assert "DATA_DEPLOY_ENV" not in child


@pytest.mark.parametrize("stage", ("create", "registration", "verify"))
def test_registry_build_keys_reach_prep_only(stage: str) -> None:
    """prep だけが registry を作成するため、後続 stage へ未使用キーを配らない。"""
    parent = {
        "RESOURCE_GROUP": "example-rg",
        "DATA_NETWORK_MODE": "private",
        "DATA_VERIFY_ACR_NAME": "hveasdwapp009deadbeef",
        "DATA_VERIFY_IMAGE_NAME": "hve-asdw-data-verify:app009",
        "DATA_VERIFY_ACI_IMAGE": (
            "hveasdwapp009deadbeef.azurecr.io/hve-asdw-data-verify:app009"
        ),
    }

    prep_child = launcher._build_child_environment(parent, "prep")
    later_child = launcher._build_child_environment(parent, stage)

    assert prep_child["DATA_VERIFY_ACR_NAME"] == "hveasdwapp009deadbeef"
    assert prep_child["DATA_VERIFY_IMAGE_NAME"] == "hve-asdw-data-verify:app009"
    assert "DATA_VERIFY_ACR_NAME" not in later_child
    assert "DATA_VERIFY_IMAGE_NAME" not in later_child
    assert later_child["DATA_VERIFY_ACI_IMAGE"] == parent["DATA_VERIFY_ACI_IMAGE"]
    assert prep_child["DATA_VERIFY_ACI_IMAGE"] == parent["DATA_VERIFY_ACI_IMAGE"]


@pytest.mark.parametrize("stage", ("create", "registration", "verify"))
def test_identity_client_id_is_read_back_after_prep_only(stage: str) -> None:
    """Azure が採番する clientId は prep 後の読み戻しでのみ供給する。"""
    parent = {
        "RESOURCE_GROUP": "example-rg",
        "DATA_NETWORK_MODE": "private",
        "DATA_DEPLOY_IDENTITY_ID": (
            "/subscriptions/00000000-0000-0000-0000-000000000001"
            "/resourceGroups/example-rg/providers/Microsoft.ManagedIdentity"
            "/userAssignedIdentities/data-deploy-identity"
        ),
    }

    prep_child = launcher._build_child_environment(parent, "prep")
    later_child = launcher._build_child_environment(parent, stage)

    # prep がまだ ID を作成していない時点では読み戻さない。
    assert "DATA_DEPLOY_IDENTITY_CLIENT_ID" not in prep_child
    assert later_child["DATA_DEPLOY_IDENTITY_CLIENT_ID"] == _IDENTITY_CLIENT_ID


def test_identity_client_id_read_back_fails_closed_without_the_identity_id() -> None:
    with pytest.raises(launcher.ScriptLauncherError, match="DATA_DEPLOY_IDENTITY_ID"):
        _REAL_IDENTITY_READ_BACK({"RESOURCE_GROUP": "example-rg"})


def test_execute_stage_does_not_forward_ambient_secret_to_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    monkeypatch.setenv("UNRELATED_AMBIENT_SECRET", "must-not-reach-child")
    monkeypatch.setenv("SUBSCRIPTION_ID", "ambient-subscription")
    monkeypatch.setenv("DATA_VNET_NAME", "ambient-vnet")
    monkeypatch.setenv("HVE_RUN_ID", "ambient-run")
    monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path / "ambient-work-root"))
    monkeypatch.setenv("data_deploy_env", "must-not-reach-child")
    captured: dict[str, object] = {}

    def run(_argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess([], 0)

    assert launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        environment={
            "RESOURCE_GROUP": "example-rg",
            "DATA_NETWORK_MODE": "private",
        },
        process_runner=run,
    ) == 0
    child = captured["env"]
    assert isinstance(child, dict)
    assert child["RESOURCE_GROUP"] == "example-rg"
    assert "UNRELATED_AMBIENT_SECRET" not in child
    assert "SUBSCRIPTION_ID" not in child
    assert "DATA_VNET_NAME" not in child
    assert "HVE_RUN_ID" not in child
    assert "HVE_WORK_ROOT" not in child
    assert "data_deploy_env" not in child


def _pipeline_environment(tmp_path: Path) -> dict[str, str]:
    run_id = "pytest-owned-pipeline"
    work_root = tmp_path / "work" / "run" / run_id
    work_root.mkdir(parents=True)
    return {
        **_COMPLETE_VERIFY_ENVIRONMENT,
        "HVE_RUN_ID": run_id,
        "HVE_WORK_ROOT": str(work_root),
    }


def test_pipeline_runs_the_hve_owned_two_pass_stage_order_and_returns_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    environment = _pipeline_environment(tmp_path)
    markers = _stage_markers(tmp_path, environment)
    observed_stages: list[str] = []
    marker_states: list[tuple[str, dict[str, bool]]] = []

    def run(_argv, **kwargs):
        stage = kwargs["env"]["HVE_ASDW_SCRIPT_STAGE"]
        observed_stages.append(stage)
        marker_states.append(
            (stage, {name: path.exists() for name, path in markers.items()})
        )
        return subprocess.CompletedProcess([], 0)

    results = launcher.execute_pipeline(
        repo_root=tmp_path,
        environment=environment,
        process_runner=run,
    )

    assert observed_stages == [
        "prep",
        "create",
        "registration",
        "verify",
        "create",
        "registration",
        "verify",
    ]
    assert [
        (result.stage, result.attempt, result.exit_code, result.reached)
        for result in results
    ] == [
        ("prep", 1, 0, True),
        ("create", 1, 0, True),
        ("registration", 1, 0, True),
        ("verify", 1, 0, True),
        ("create", 2, 0, True),
        ("registration", 2, 0, True),
        ("verify", 2, 0, True),
    ]
    assert all(result.evidence == "process-exit=0" for result in results)
    assert marker_states == [
        ("prep", {"prep": False, "create": False, "registration": False, "verify": False}),
        ("create", {"prep": True, "create": False, "registration": False, "verify": False}),
        ("registration", {"prep": True, "create": True, "registration": False, "verify": False}),
        ("verify", {"prep": True, "create": True, "registration": True, "verify": False}),
        ("create", {"prep": True, "create": False, "registration": False, "verify": False}),
        ("registration", {"prep": True, "create": True, "registration": False, "verify": False}),
        ("verify", {"prep": True, "create": True, "registration": True, "verify": False}),
    ]


def test_pipeline_generates_distinct_run_ids_for_each_stage_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    generated_ids = iter(f"{index:032x}" for index in range(1, 7))
    monkeypatch.setattr(launcher.secrets, "token_hex", lambda _count: next(generated_ids))
    observed_ids: list[tuple[str, str]] = []

    def run(_argv, **kwargs):
        child = kwargs["env"]
        stage = child["HVE_ASDW_SCRIPT_STAGE"]
        run_id_key = launcher._STAGE_RUN_ID_KEYS.get(stage)
        if run_id_key is not None:
            observed_ids.append((stage, child[run_id_key]))
        return subprocess.CompletedProcess([], 0)

    launcher.execute_pipeline(
        repo_root=tmp_path,
        environment=_pipeline_environment(tmp_path),
        process_runner=run,
    )

    assert observed_ids == [
        ("create", f"{1:032x}"),
        ("registration", f"{2:032x}"),
        ("verify", f"{3:032x}"),
        ("create", f"{4:032x}"),
        ("registration", f"{5:032x}"),
        ("verify", f"{6:032x}"),
    ]


def test_pipeline_stops_after_first_nonzero_result_and_releases_its_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    environment = _pipeline_environment(tmp_path)
    observed_stages: list[str] = []

    def run(_argv, **kwargs):
        stage = kwargs["env"]["HVE_ASDW_SCRIPT_STAGE"]
        observed_stages.append(stage)
        return subprocess.CompletedProcess([], 23 if stage == "registration" else 0)

    results = launcher.execute_pipeline(
        repo_root=tmp_path,
        environment=environment,
        process_runner=run,
    )

    assert observed_stages == ["prep", "create", "registration"]
    assert [result.exit_code for result in results] == [0, 0, 23]
    assert all(result.reached for result in results)
    assert results[-1].evidence == "process-exit=23"
    assert launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        environment=environment,
        process_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0),
    ) == 0


def test_direct_stage_is_rejected_while_pipeline_holds_the_stage_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    environment = _pipeline_environment(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    pipeline_errors: list[BaseException] = []

    def run(_argv, **kwargs):
        if kwargs["env"]["HVE_ASDW_SCRIPT_STAGE"] == "prep":
            entered.set()
            assert release.wait(timeout=5)
        return subprocess.CompletedProcess([], 0)

    def run_pipeline() -> None:
        try:
            launcher.execute_pipeline(
                repo_root=tmp_path,
                environment=environment,
                process_runner=run,
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            pipeline_errors.append(exc)

    worker = threading.Thread(target=run_pipeline)
    worker.start()
    assert entered.wait(timeout=5)
    with pytest.raises(launcher.ScriptLauncherError, match="already running"):
        launcher.execute_stage(
            "create",
            repo_root=tmp_path,
            environment=environment,
            process_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0),
        )
    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert pipeline_errors == []


def test_pipeline_cancellation_does_not_start_later_stages_and_releases_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    environment = _pipeline_environment(tmp_path)
    observed_stages: list[str] = []

    def cancel_during_create(_argv, **kwargs):
        stage = kwargs["env"]["HVE_ASDW_SCRIPT_STAGE"]
        observed_stages.append(stage)
        if stage == "create":
            raise KeyboardInterrupt("pipeline cancellation")
        return subprocess.CompletedProcess([], 0)

    with pytest.raises(KeyboardInterrupt, match="pipeline cancellation"):
        launcher.execute_pipeline(
            repo_root=tmp_path,
            environment=environment,
            process_runner=cancel_during_create,
        )

    assert observed_stages == ["prep", "create"]
    assert launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        environment=environment,
        process_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0),
    ) == 0


def test_verify_success_marker_is_written_only_after_a_successful_verify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")
    environment = _pipeline_environment(tmp_path)
    markers = _stage_markers(tmp_path, environment)

    def run_with_exit(exit_code: int):
        return lambda *_args, **_kwargs: subprocess.CompletedProcess([], exit_code)

    for stage in ("prep", "create", "registration"):
        assert launcher.execute_stage(
            stage,
            repo_root=tmp_path,
            environment=environment,
            process_runner=run_with_exit(0),
        ) == 0
    assert launcher.execute_stage(
        "verify",
        repo_root=tmp_path,
        environment=environment,
        process_runner=run_with_exit(9),
    ) == 9
    assert not markers["verify"].exists()
    assert launcher.execute_stage(
        "verify",
        repo_root=tmp_path,
        environment=environment,
        process_runner=run_with_exit(0),
    ) == 0
    assert markers["verify"].read_text(encoding="utf-8") == (
        f"{environment['HVE_RUN_ID']}\n"
    )


def test_stable_reader_rejects_symlink_and_parent_escape(tmp_path: Path) -> None:
    _write_stage_inputs(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.sh"
    outside.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    alias = tmp_path / "src" / "infra" / "azure" / "alias.sh"
    try:
        alias.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises(launcher.ScriptLauncherError, match="symlink|repository root"):
        launcher._read_stable_utf8_file(alias, tmp_path, "alias")
    with pytest.raises(launcher.ScriptLauncherError, match="escapes"):
        launcher._read_stable_utf8_file(outside, tmp_path, "outside")


def test_stable_reader_rejects_hard_link(tmp_path: Path) -> None:
    target = tmp_path / "target.sh"
    target.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    alias = tmp_path / "alias.sh"
    try:
        os.link(target, alias)
    except OSError as exc:
        pytest.skip(f"hard link unavailable: {exc}")

    with pytest.raises(launcher.ScriptLauncherError, match="hard-linked"):
        launcher._read_stable_utf8_file(alias, tmp_path, "alias")


@pytest.mark.parametrize("payload", ("\ufeff#!/usr/bin/env bash\n", "#!/usr/bin/env bash\r\n"))
def test_stable_reader_rejects_bom_and_crlf(tmp_path: Path, payload: str) -> None:
    target = tmp_path / "script.sh"
    target.write_bytes(payload.encode("utf-8"))

    with pytest.raises(launcher.ScriptLauncherError, match="UTF-8 without BOM"):
        launcher._read_stable_utf8_file(target, tmp_path, "script")
