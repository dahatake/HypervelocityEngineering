"""Durable resume service RED contracts.

Traceability: FR-STATE-05, FR-CLI-90, NFR-SEC-01.
The production modules are imported while each test is running so missing
implementations remain named test failures rather than collection errors.
"""

from __future__ import annotations

from contextlib import contextmanager
import importlib
import json
from pathlib import Path
import re
import time
from typing import Any, Iterator, Mapping, Sequence

import pytest


_RESUME_MODULE = "hve.resume_service"
_STATE_MODULE = "hve.run_state_store"


def _api(requirement: str, *required_names: str) -> Any:
    try:
        module = importlib.import_module(_RESUME_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name in {_RESUME_MODULE, _STATE_MODULE}:
            pytest.fail(
                f"{requirement}: missing production module {exc.name}",
                pytrace=False,
            )
        raise

    missing = [name for name in required_names if not hasattr(module, name)]
    if missing:
        pytest.fail(
            f"{requirement}: {_RESUME_MODULE} is missing API: {', '.join(missing)}",
            pytrace=False,
        )
    return module


def _state_api(requirement: str) -> Any:
    try:
        module = importlib.import_module(_STATE_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name == _STATE_MODULE:
            pytest.fail(
                f"{requirement}: missing production module {_STATE_MODULE}",
                pytrace=False,
            )
        raise

    missing = [
        name
        for name in ("DurableStateError", "RunStateStore")
        if not hasattr(module, name)
    ]
    if missing:
        pytest.fail(
            f"{requirement}: {_STATE_MODULE} is missing API: {', '.join(missing)}",
            pytrace=False,
        )
    return module


def _field(record: Any, name: str) -> Any:
    if isinstance(record, Mapping):
        return record[name]
    try:
        return record[name]
    except (IndexError, KeyError, TypeError):
        return getattr(record, name)


def _descriptor(
    api: Any,
    instance_id: str,
    workflow_id: str,
    ordinal: int,
    *,
    argv: Sequence[str] | None = None,
    missing_replay_keys: Sequence[str] = (),
) -> Any:
    return api.WorkflowDescriptor(
        instance_id=instance_id,
        workflow_id=workflow_id,
        ordinal=ordinal,
        mode="standard",
        argv=tuple(
            argv
            or (
                "orchestrate",
                "--workflow",
                workflow_id,
            )
        ),
        missing_replay_keys=tuple(missing_replay_keys),
    )


def _assert_sha256(value: str) -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", value)


def _risk_codes(plan: Any) -> tuple[str, ...]:
    return tuple(
        str(reason).casefold().replace("-", "_").replace(" ", "_")
        for reason in plan.risk_reasons
    )


def _selected_steps(argv: Sequence[str]) -> tuple[str, ...]:
    values = tuple(str(value) for value in argv)
    if "--steps" not in values:
        return ()
    start = values.index("--steps") + 1
    selected: list[str] = []
    for value in values[start:]:
        if value.startswith("--"):
            break
        selected.extend(part for part in re.split(r"[\s,]+", value) if part)
    return tuple(selected)


class _RecordingStore:
    def __init__(self) -> None:
        self.registration_calls: list[dict[str, Any]] = []
        self.candidate_keys: list[str] = []

    def quick_check(self) -> bool:
        return True

    def register_execution(
        self,
        execution_id: str,
        repo_key: str,
        surface: str,
        launch_plan_hash: str,
        plan_json: str,
        instances: Sequence[Any],
    ) -> None:
        self.registration_calls.append(
            {
                "execution_id": execution_id,
                "repo_key": repo_key,
                "surface": surface,
                "launch_plan_hash": launch_plan_hash,
                "plan_json": plan_json,
                "instances": list(instances),
            }
        )

    def list_candidates(self, repo_key: str) -> list[dict[str, str]]:
        self.candidate_keys.append(repo_key)
        return [
            {
                "execution_id": f"execution-{repo_key[-12:]}",
                "repo_key": repo_key,
                "surface": "cli",
                "updated_at": "2026-08-28T00:00:00Z",
            }
        ]

    @staticmethod
    def list_instances(execution_id: str) -> list[dict[str, Any]]:
        return [
            {
                "execution_id": execution_id,
                "instance_id": "aas-1",
                "workflow_id": "aas",
                "ordinal": 0,
                "mode": "standard",
                "status": "pending",
                "state_version": 0,
                "heartbeat_at": None,
            }
        ]


@contextmanager
def _registered_service(
    tmp_path: Path,
    requirement: str,
    descriptors: Sequence[Any],
    *,
    execution_id: str = "execution-test",
    checkpoint_head: str = "head-at-launch",
) -> Iterator[tuple[Any, Any, Any, Any, str, Path]]:
    api = _api(requirement, "ResumeService")
    state_api = _state_api(requirement)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    database_path = tmp_path / "state.sqlite3"

    with state_api.RunStateStore(database_path) as store:
        service = api.ResumeService(store, repo_root)
        registered_id = service.register_execution(
            "cli",
            tuple(descriptors),
            execution_id=execution_id,
            checkpoint_head=checkpoint_head,
        )
        yield api, state_api, store, service, registered_id, repo_root


def _state_version(store: Any, execution_id: str, instance_id: str) -> int:
    instance = store.get_instance(execution_id, instance_id)
    assert instance is not None
    value = _field(instance, "state_version")
    assert isinstance(value, int) and not isinstance(value, bool)
    return value


def _set_workflow_status(
    store: Any,
    execution_id: str,
    instance_id: str,
    status: str,
) -> None:
    token = store.acquire_lease(
        execution_id,
        instance_id,
        _state_version(store, execution_id, instance_id),
        f"test-owner-{instance_id}",
        now=time.time(),
    )
    if status != "running":
        token = store.transition_workflow(token, "running", run_id="attempt-1")
    token = store.transition_workflow(token, status, run_id="attempt-1")
    store.release_lease(token)


def _set_step_progress(
    store: Any,
    execution_id: str,
    instance_id: str,
    succeeded_step_ids: Sequence[str],
    *,
    final_status: str = "suspended",
) -> None:
    token = store.acquire_lease(
        execution_id,
        instance_id,
        _state_version(store, execution_id, instance_id),
        f"test-owner-{instance_id}",
        now=time.time(),
    )
    token = store.transition_workflow(token, "running", run_id="attempt-1")
    for step_id in succeeded_step_ids:
        token = store.transition_step(
            token,
            step_id,
            "succeeded",
            phase="main",
            phase_state="completed",
            session_id=f"session-{step_id.replace('.', '-')}",
        )
    token = store.transition_workflow(token, final_status, run_id="attempt-1")
    store.release_lease(token)


class TestCanonicalHashes:
    """FR-STATE-05 / FR-CLI-90: canonical launch and resume hashes."""

    def test_canonical_json_is_sorted_compact_and_utf8(self) -> None:
        api = _api("FR-STATE-05 canonical JSON", "canonical_json")

        actual = api.canonical_json(
            {
                "zeta": "日本語",
                "alpha": {"second": 2, "first": 1},
            }
        )

        assert actual == '{"alpha":{"first":1,"second":2},"zeta":"日本語"}'
        assert json.loads(actual)["zeta"] == "日本語"

    def test_launch_hash_is_execution_id_independent_and_order_sensitive(
        self, tmp_path: Path
    ) -> None:
        api = _api(
            "FR-CLI-90 launch hash boundary",
            "WorkflowDescriptor",
            "ResumeService",
            "compute_launch_plan_hash",
        )
        descriptors = (
            _descriptor(api, "ard-1", "ard", 0),
            _descriptor(api, "aas-1", "aas", 1),
        )
        stores = (_RecordingStore(), _RecordingStore())
        for index, store in enumerate(stores):
            repo_root = tmp_path / f"repo-{index}"
            repo_root.mkdir()
            api.ResumeService(store, repo_root).register_execution(
                "prompt",
                descriptors,
                execution_id=f"execution-{index}",
                checkpoint_head="abc123",
            )

        first_hash = stores[0].registration_calls[0]["launch_plan_hash"]
        second_hash = stores[1].registration_calls[0]["launch_plan_hash"]
        reordered = (
            _descriptor(api, "ard-1", "ard", 1),
            _descriptor(api, "aas-1", "aas", 0),
        )

        _assert_sha256(first_hash)
        assert first_hash == second_hash
        assert first_hash == api.compute_launch_plan_hash(descriptors)
        assert first_hash != api.compute_launch_plan_hash(reordered)

    def test_resume_hash_has_separate_state_action_head_and_replay_inputs(self) -> None:
        api = _api(
            "FR-CLI-90 resume hash boundary",
            "WorkflowDescriptor",
            "compute_launch_plan_hash",
            "compute_resume_plan_hash",
        )
        descriptor = _descriptor(api, "aas-1", "aas", 0)
        payload = {
            "execution_id": "execution-a",
            "instance_id": "aas-1",
            "status": "failed",
            "state_version": 7,
            "action": "restart-step",
            "current_head": "abc123",
            "replay_values": {"additional_prompt": "re-entered value"},
        }
        variants = {
            "execution_id": {**payload, "execution_id": "execution-b"},
            "status": {**payload, "status": "suspended"},
            "state_version": {**payload, "state_version": 8},
            "action": {**payload, "action": "reuse-session"},
            "current_head": {**payload, "current_head": "def456"},
            "replay_values": {
                **payload,
                "replay_values": {"additional_prompt": "different value"},
            },
        }

        resume_hash = api.compute_resume_plan_hash(payload)

        _assert_sha256(resume_hash)
        assert resume_hash != api.compute_launch_plan_hash((descriptor,))
        for changed_input, variant in variants.items():
            assert api.compute_resume_plan_hash(variant) != resume_hash, changed_input


class TestExecutionRegistration:
    """FR-STATE-05: one parent registration with an ordered descriptor set."""

    def test_registers_all_ordered_descriptors_in_one_bulk_store_call(
        self, tmp_path: Path
    ) -> None:
        api = _api(
            "FR-STATE-05 atomic ordered registration",
            "WorkflowDescriptor",
            "ResumeService",
            "canonical_json",
            "compute_launch_plan_hash",
        )
        store = _RecordingStore()
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        descriptors = (
            _descriptor(api, "ard-1", "ard", 0),
            _descriptor(api, "aas-1", "aas", 1),
            _descriptor(api, "aad-web-1", "aad-web", 2),
        )

        actual_id = api.ResumeService(store, repo_root).register_execution(
            "prompt",
            descriptors,
            execution_id="execution-parent",
            checkpoint_head="abc123",
        )

        assert actual_id == "execution-parent"
        assert len(store.registration_calls) == 1
        call = store.registration_calls[0]
        assert call["execution_id"] == "execution-parent"
        assert call["surface"] == "prompt"
        assert re.fullmatch(r"[0-9a-f]{64}", call["repo_key"])
        assert str(repo_root.resolve()).casefold() not in call["repo_key"].casefold()
        assert [
            (_field(instance, "instance_id"), _field(instance, "ordinal"))
            for instance in call["instances"]
        ] == [("ard-1", 0), ("aas-1", 1), ("aad-web-1", 2)]
        payload = json.loads(call["plan_json"])
        assert [item["instance_id"] for item in payload["instances"]] == [
            "ard-1",
            "aas-1",
            "aad-web-1",
        ]
        assert call["plan_json"] == api.canonical_json(payload)
        assert call["launch_plan_hash"] == api.compute_launch_plan_hash(descriptors)

    def test_explicit_parent_execution_id_is_not_regenerated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _api(
            "FR-STATE-05 parent-owned execution identity",
            "WorkflowDescriptor",
            "ResumeService",
        )
        store = _RecordingStore()
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        service = api.ResumeService(store, repo_root)

        def forbidden_generation() -> str:
            raise AssertionError("a child/existing execution must not mint an execution ID")

        monkeypatch.setattr(service, "new_execution_id", forbidden_generation)

        actual_id = service.register_execution(
            "cli",
            (_descriptor(api, "ard-1", "ard", 0),),
            execution_id="execution-from-parent",
        )

        assert actual_id == "execution-from-parent"
        assert store.registration_calls[0]["execution_id"] == actual_id

    def test_duplicate_ordinals_are_rejected_without_partial_registration(
        self, tmp_path: Path
    ) -> None:
        api = _api(
            "FR-STATE-05 unique ordered descriptors",
            "WorkflowDescriptor",
            "ResumeService",
        )
        state_api = _state_api("FR-STATE-05 unique ordered descriptors")
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        database_path = tmp_path / "state.sqlite3"
        descriptors = (
            _descriptor(api, "ard-1", "ard", 0),
            _descriptor(api, "aas-1", "aas", 0),
        )

        with state_api.RunStateStore(database_path) as store:
            service = api.ResumeService(store, repo_root)
            with pytest.raises((state_api.DurableStateError, ValueError)):
                service.register_execution(
                    "prompt",
                    descriptors,
                    execution_id="execution-duplicate-ordinal",
                )

            assert store.get_execution("execution-duplicate-ordinal") is None


class TestCandidateScope:
    """FR-CLI-90: candidates are selected for the current repository only."""

    def test_repo_key_is_stable_from_a_git_subdirectory(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-04 canonical Git root", "ResumeService")
        state_api = _state_api("FR-STATE-04 canonical Git root")
        repo_root = tmp_path / "repo"
        nested = repo_root / "src" / "nested"
        nested.mkdir(parents=True)
        (repo_root / ".git").mkdir()

        root_service = api.ResumeService(_RecordingStore(), repo_root)
        nested_service = api.ResumeService(_RecordingStore(), nested)

        assert root_service.repo_root == repo_root.resolve()
        assert nested_service.repo_root == repo_root.resolve()
        assert nested_service.repo_key == root_service.repo_key
        assert state_api.compute_repo_key(nested) == state_api.compute_repo_key(
            repo_root
        )

    def test_candidates_are_scoped_by_normalized_repository_key(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-CLI-90 repository-scoped candidates", "ResumeService")
        store = _RecordingStore()
        first_root = tmp_path / "first-repository"
        second_root = tmp_path / "second-repository"
        first_root.mkdir()
        second_root.mkdir()

        first = api.ResumeService(store, first_root).list_candidates()
        second = api.ResumeService(store, second_root).list_candidates()

        assert len(store.candidate_keys) == 2
        first_key, second_key = store.candidate_keys
        _assert_sha256(first_key)
        _assert_sha256(second_key)
        assert first_key != second_key
        assert str(first_root.resolve()).casefold() not in first_key.casefold()
        assert str(second_root.resolve()).casefold() not in second_key.casefold()
        assert _field(first[0], "repo_key") == first_key
        assert _field(second[0], "repo_key") == second_key


class TestReplaySanitization:
    """NFR-SEC-01: replay descriptors use a fixed allowlist and key-only gaps."""

    def test_replay_option_classes_are_pairwise_disjoint(self) -> None:
        api = _api("NFR-SEC-01 unambiguous replay option grammar")
        classes = {
            "replay-value": api._REPLAY_VALUE_FLAGS,
            "replay-multi-value": api._REPLAY_MULTI_VALUE_FLAGS,
            "replay-boolean": api._REPLAY_BOOLEAN_FLAGS,
            "missing-value": api._MISSING_VALUE_FLAGS,
            "missing-multi-value": api._MISSING_MULTI_VALUE_FLAGS,
            "missing-pair": api._MISSING_PAIR_FLAGS,
            "rejected": api._REJECTED_FLAGS,
        }

        names = list(classes)
        for index, first_name in enumerate(names):
            for second_name in names[index + 1 :]:
                overlap = classes[first_name] & classes[second_name]
                assert not overlap, f"{first_name} / {second_name}: {sorted(overlap)}"

    def test_sanitize_argv_keeps_identifiers_but_never_free_text_or_tool_config(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-SEC-01 replay argv allowlist", "ResumeService")
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        service = api.ResumeService(_RecordingStore(), repo_root)
        sentinels = {
            "PROMPT-SENTINEL-7f4d",
            "TITLE-SENTINEL-1e2a",
            "WORKIQ-SENTINEL-98bd",
            "MCP-PATH-SENTINEL-331c",
            "https://credential.example.invalid/SENTINEL",
        }
        raw_argv = (
            "orchestrate",
            "--workflow",
            "aas",
            "--model",
            "claude-opus-4.7",
            "--steps",
            "1,2.1",
            "--app-id",
            "APP-009",
            "--additional-prompt",
            "PROMPT-SENTINEL-7f4d",
            "--issue-title",
            "TITLE-SENTINEL-1e2a",
            "--workiq-prompt-qa",
            "WORKIQ-SENTINEL-98bd",
            "--mcp-config",
            "MCP-PATH-SENTINEL-331c",
            "--cli-url",
            "https://credential.example.invalid/SENTINEL",
        )

        safe_argv, missing_replay_keys = service.sanitize_argv(raw_argv)
        serialized = api.canonical_json(
            {
                "argv": list(safe_argv),
                "missing_replay_keys": list(missing_replay_keys),
            }
        )

        for flag, value in (
            ("--workflow", "aas"),
            ("--model", "claude-opus-4.7"),
            ("--steps", "1,2.1"),
            ("--app-id", "APP-009"),
        ):
            index = tuple(safe_argv).index(flag)
            assert safe_argv[index + 1] == value
        assert "additional_prompt" in missing_replay_keys
        assert all(re.fullmatch(r"[a-z][a-z0-9_]*", key) for key in missing_replay_keys)
        assert not any(sentinel in serialized for sentinel in sentinels)

    def test_registration_persists_missing_key_names_but_not_values(
        self, tmp_path: Path
    ) -> None:
        api = _api(
            "NFR-SEC-01 key-only replay persistence",
            "WorkflowDescriptor",
            "ResumeService",
        )
        store = _RecordingStore()
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        secret_prompt = "DO-NOT-PERSIST-PROMPT-4a43"
        descriptor = _descriptor(
            api,
            "aas-1",
            "aas",
            0,
            argv=(
                "orchestrate",
                "--workflow",
                "aas",
                "--additional-prompt",
                secret_prompt,
            ),
        )

        api.ResumeService(store, repo_root).register_execution(
            "cli",
            (descriptor,),
            execution_id="execution-secure",
        )

        call = store.registration_calls[0]
        instance = call["instances"][0]
        assert secret_prompt not in call["plan_json"]
        assert secret_prompt not in repr(call["instances"])
        assert "additional_prompt" in _field(instance, "missing_replay_keys")
        assert secret_prompt not in _field(instance, "missing_replay_keys")

    def test_malformed_option_without_value_is_rejected(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-SEC-01 malformed replay argv", "ResumeService")
        state_api = _state_api("NFR-SEC-01 malformed replay argv")
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        service = api.ResumeService(_RecordingStore(), repo_root)

        with pytest.raises((state_api.DurableStateError, ValueError)):
            service.sanitize_argv(
                ("orchestrate", "--workflow", "aas", "--additional-prompt")
            )

    def test_repository_url_is_rejected_instead_of_persisted(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-SEC-01 repository slug", "ResumeService")
        state_api = _state_api("NFR-SEC-01 repository slug")
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        service = api.ResumeService(_RecordingStore(), repo_root)

        with pytest.raises(state_api.DurableStateError):
            service.sanitize_argv(
                (
                    "orchestrate",
                    "--workflow",
                    "aas",
                    "--repo",
                    "https://user:credential@example.invalid/owner/repo",
                )
            )

    def test_embedded_data_uri_is_rejected_instead_of_persisted(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-SEC-01 embedded replay URI", "ResumeService")
        state_api = _state_api("NFR-SEC-01 embedded replay URI")
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        service = api.ResumeService(_RecordingStore(), repo_root)

        with pytest.raises(state_api.DurableStateError):
            service.sanitize_argv(
                (
                    "orchestrate",
                    "--workflow",
                    "aas",
                    "--model",
                    "data:text/plain;base64,U0VDUkVU",
                )
            )

    def test_arbitrary_scope_paths_are_key_only_replay_gaps(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-SEC-01 arbitrary replay paths", "ResumeService")
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        service = api.ResumeService(_RecordingStore(), repo_root)
        sentinels = (
            "C:\\private\\repository",
            "/private/self-improve/root",
        )

        safe, missing = service.sanitize_argv(
            (
                "orchestrate",
                "--workflow",
                "adi",
                "--target-scope",
                sentinels[0],
                "--self-improve-target-scope",
                sentinels[1],
            )
        )

        serialized = api.canonical_json(
            {"argv": list(safe), "missing_replay_keys": list(missing)}
        )
        assert "target_scope" in missing
        assert "self_improve_target_scope" in missing
        assert all(sentinel not in serialized for sentinel in sentinels)

    def test_prompt_cloud_and_fleet_options_use_safe_persistence_boundary(
        self, tmp_path: Path
    ) -> None:
        """FR-PROMPT-11 / NFR-SEC-01: mode 設定は安全値と再入力値へ分離する。"""
        api = _api(
            "FR-PROMPT-11 Prompt mode replay boundary",
            "ResumeService",
            "WorkflowDescriptor",
        )
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        store = _RecordingStore()
        service = api.ResumeService(store, repo_root)
        sensitive = {
            "INTEGRATION-ID-SENTINEL-17aa",
            "https://internal.example.invalid/mc",
            '{"1":true}',
            '{"pre_qa":true}',
        }
        raw_argv = (
            "orchestrate",
            "--workflow",
            "ard",
            "--cloud-session",
            "--cloud-session-owner",
            "octocat",
            "--cloud-session-repository-name",
            "repo",
            "--cloud-session-branch",
            "feature/prompt-durable",
            "--cloud-session-max-concurrency",
            "5",
            "--cloud-session-integration-id",
            "INTEGRATION-ID-SENTINEL-17aa",
            "--cloud-session-mc-base-url",
            "https://internal.example.invalid/mc",
            "--cloud-session-step-overrides",
            '{"1":true}',
            "--cloud-session-subtask-overrides",
            '{"pre_qa":true}',
            "--fleet-mode",
        )
        safe, missing = service.sanitize_argv(raw_argv)

        assert safe == (
            "orchestrate",
            "--workflow",
            "ard",
            "--cloud-session",
            "--cloud-session-owner",
            "octocat",
            "--cloud-session-repository-name",
            "repo",
            "--cloud-session-branch",
            "feature/prompt-durable",
            "--cloud-session-max-concurrency",
            "5",
            "--fleet-mode",
        )
        assert missing == (
            "cloud_session_integration_id",
            "cloud_session_mc_base_url",
            "cloud_session_step_overrides",
            "cloud_session_subtask_overrides",
        )
        serialized = api.canonical_json(
            {"argv": list(safe), "missing_replay_keys": list(missing)}
        )
        assert all(value not in serialized for value in sensitive)

        service.register_execution(
            "prompt",
            (_descriptor(api, "ard-1", "ard", 0, argv=raw_argv),),
            execution_id="execution-prompt-mode",
        )
        call = store.registration_calls[0]
        persisted_instance = call["instances"][0]
        assert tuple(_field(persisted_instance, "argv")) == safe
        assert tuple(_field(persisted_instance, "missing_replay_keys")) == missing
        assert all(value not in call["plan_json"] for value in sensitive)
        assert all(value not in repr(call["instances"]) for value in sensitive)


class TestRiskAndAction:
    """FR-CLI-90: risk is observable and recovery action is explicit."""

    def test_failed_instance_exposes_risk_and_selected_action_changes_plan(
        self, tmp_path: Path
    ) -> None:
        api = _api(
            "FR-CLI-90 risk and recovery action",
            "WorkflowDescriptor",
            "ResumePlan",
        )
        descriptors = (_descriptor(api, "aas-1", "aas", 0),)

        with _registered_service(tmp_path, "FR-CLI-90 risk and recovery action", descriptors) as (
            _,
            _,
            store,
            service,
            execution_id,
            _,
        ):
            _set_workflow_status(store, execution_id, "aas-1", "failed")

            preview = service.build_plan(
                execution_id,
                current_head="head-at-launch",
            )
            selected = service.build_plan(
                execution_id,
                action="restart-step",
                current_head="head-at-launch",
            )

        assert preview.instance_id == "aas-1"
        assert preview.action is None
        assert preview.risk_reasons
        assert any("failed" in reason for reason in _risk_codes(preview))
        assert selected.action == "restart-step"
        assert selected.risk_reasons == preview.risk_reasons
        assert selected.resume_plan_hash != preview.resume_plan_hash

    def test_risky_plan_without_action_cannot_acquire_a_lease(
        self, tmp_path: Path
    ) -> None:
        api = _api(
            "FR-CLI-90 explicit action before lease",
            "WorkflowDescriptor",
        )
        descriptors = (_descriptor(api, "aas-1", "aas", 0),)

        with _registered_service(tmp_path, "FR-CLI-90 explicit action before lease", descriptors) as (
            _,
            state_api,
            store,
            service,
            execution_id,
            _,
        ):
            _set_workflow_status(store, execution_id, "aas-1", "failed")
            risky_plan = service.build_plan(
                execution_id,
                current_head="head-at-launch",
            )

            with pytest.raises(state_api.DurableStateError):
                service.acquire(risky_plan, "resume-owner")

    def test_head_drift_is_an_explicit_risk_and_changes_resume_hash(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-CLI-90 checkpoint HEAD drift", "WorkflowDescriptor")
        descriptors = (_descriptor(api, "aas-1", "aas", 0),)

        with _registered_service(
            tmp_path,
            "FR-CLI-90 checkpoint HEAD drift",
            descriptors,
            checkpoint_head="head-at-launch",
        ) as (_, _, _, service, execution_id, _):
            unchanged = service.build_plan(
                execution_id,
                action="restart-step",
                current_head="head-at-launch",
            )
            drifted = service.build_plan(
                execution_id,
                action="restart-step",
                current_head="different-head",
            )

        assert not any("head_drift" in reason for reason in _risk_codes(unchanged))
        assert any("head_drift" in reason for reason in _risk_codes(drifted))
        assert drifted.resume_plan_hash != unchanged.resume_plan_hash

    def test_explicit_action_acquires_expected_fenced_lease(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-CLI-90 explicit action lease", "WorkflowDescriptor")
        descriptors = (_descriptor(api, "aas-1", "aas", 0),)

        with _registered_service(
            tmp_path,
            "FR-CLI-90 explicit action lease",
            descriptors,
        ) as (_, _, store, service, execution_id, _):
            _set_workflow_status(store, execution_id, "aas-1", "failed")
            plan = service.build_plan(
                execution_id,
                action="restart-step",
                current_head="head-at-launch",
            )
            token = service.acquire(plan, "resume-owner")
            store.release_lease(token)

        assert token.execution_id == execution_id
        assert token.instance_id == "aas-1"
        assert token.owner == "resume-owner"
        assert token.state_version == plan.expected_state_version


class TestOrderedResume:
    """FR-CLI-90: resume starts at the earliest non-succeeded ordinal."""

    def test_plan_targets_earliest_non_succeeded_instance_by_ordinal(
        self, tmp_path: Path
    ) -> None:
        api = _api(
            "FR-CLI-90 earliest non-succeeded instance",
            "WorkflowDescriptor",
        )
        descriptors = (
            _descriptor(api, "ard-1", "ard", 0),
            _descriptor(api, "aas-1", "aas", 1),
            _descriptor(api, "aad-web-1", "aad-web", 2),
        )

        with _registered_service(
            tmp_path,
            "FR-CLI-90 earliest non-succeeded instance",
            descriptors,
        ) as (_, _, store, service, execution_id, _):
            _set_workflow_status(store, execution_id, "ard-1", "succeeded")
            _set_workflow_status(store, execution_id, "aas-1", "failed")

            plan = service.build_plan(
                execution_id,
                action="restart-step",
                current_head="head-at-launch",
            )
            instances = store.list_instances(execution_id)

        assert plan.instance_id == "aas-1"
        assert plan.workflow_id == "aas"
        assert tuple(plan.argv)[tuple(plan.argv).index("--workflow") + 1] == "aas"
        assert _field(instances[0], "status") == "succeeded"
        assert _field(instances[2], "status") == "pending"


class TestOutputReconciliation:
    """FR-STATE-05: required-output existence invalidates DAG descendants."""

    @staticmethod
    def _descriptors(api: Any) -> tuple[Any, ...]:
        return (
            _descriptor(
                api,
                "aas-1",
                "aas",
                0,
                argv=(
                    "orchestrate",
                    "--workflow",
                    "aas",
                    "--steps",
                    "1,2.1,2.2",
                ),
            ),
        )

    def test_existing_required_outputs_keep_succeeded_steps_skipped(
        self, tmp_path: Path
    ) -> None:
        api = _api(
            "FR-STATE-05 required output existence",
            "WorkflowDescriptor",
        )

        with _registered_service(
            tmp_path,
            "FR-STATE-05 required output existence",
            self._descriptors(api),
        ) as (_, _, store, service, execution_id, repo_root):
            (repo_root / "docs" / "catalog").mkdir(parents=True)
            (repo_root / "docs" / "catalog" / "app-arch-catalog.md").write_text(
                "architecture",
                encoding="utf-8",
            )
            (repo_root / "docs" / "catalog" / "domain-analytics.md").write_text(
                "domain",
                encoding="utf-8",
            )
            _set_step_progress(store, execution_id, "aas-1", ("1", "2.1"))

            plan = service.build_plan(
                execution_id,
                action="restart-step",
                current_head="head-at-launch",
            )

        assert _selected_steps(plan.argv) == ("2.2",)
        assert not any(
            "missing_output" in reason for reason in _risk_codes(plan)
        )

    def test_missing_output_invalidates_step_and_transitive_descendants(
        self, tmp_path: Path
    ) -> None:
        api = _api(
            "FR-STATE-05 missing output descendant invalidation",
            "WorkflowDescriptor",
        )

        with _registered_service(
            tmp_path,
            "FR-STATE-05 missing output descendant invalidation",
            self._descriptors(api),
        ) as (_, _, store, service, execution_id, repo_root):
            (repo_root / "docs" / "catalog").mkdir(parents=True)
            # Step 1's output is intentionally absent. Both descendants have their
            # own outputs, so their re-selection can only come from DAG invalidation.
            (repo_root / "docs" / "catalog" / "domain-analytics.md").write_text(
                "domain",
                encoding="utf-8",
            )
            (repo_root / "docs" / "catalog" / "service-catalog.md").write_text(
                "services",
                encoding="utf-8",
            )
            _set_step_progress(
                store,
                execution_id,
                "aas-1",
                ("1", "2.1", "2.2"),
            )

            plan = service.build_plan(
                execution_id,
                action="restart-step",
                current_head="head-at-launch",
            )

        assert _selected_steps(plan.argv) == ("1", "2.1", "2.2")
        assert any(
            "missing_output" in reason for reason in _risk_codes(plan)
        )

    def test_output_content_changes_do_not_create_a_content_hash_dependency(
        self, tmp_path: Path
    ) -> None:
        api = _api(
            "FR-STATE-05 no output content hash",
            "WorkflowDescriptor",
        )

        with _registered_service(
            tmp_path,
            "FR-STATE-05 no output content hash",
            self._descriptors(api),
        ) as (_, _, store, service, execution_id, repo_root):
            output_path = repo_root / "docs" / "catalog" / "app-arch-catalog.md"
            output_path.parent.mkdir(parents=True)
            output_path.write_text("first content", encoding="utf-8")
            _set_step_progress(store, execution_id, "aas-1", ("1",))

            first = service.build_plan(
                execution_id,
                action="restart-step",
                current_head="head-at-launch",
            )
            output_path.write_text(
                "completely different content",
                encoding="utf-8",
            )
            second = service.build_plan(
                execution_id,
                action="restart-step",
                current_head="head-at-launch",
            )

        assert second.argv == first.argv
        assert second.risk_reasons == first.risk_reasons
        assert second.resume_plan_hash == first.resume_plan_hash


class TestAdversarialResumeRegressions:
    """Post-GREEN adversarial findings remain fixed at the shared boundary."""

    def test_real_option_arities_and_short_aliases_are_sanitized(self, tmp_path: Path) -> None:
        api = _api("NFR-SEC-01 fixed replay option grammar", "ResumeService")
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        service = api.ResumeService(_RecordingStore(), repo_root)

        safe, missing = service.sanitize_argv(
            (
                "orchestrate",
                "-w",
                "aas",
                "--enable-agentic-retrieval",
                "yes",
                "--foundry-mcp-integration",
                "--create-pr",
                "-q",
            )
        )

        assert safe == (
            "orchestrate",
            "--workflow",
            "aas",
            "--enable-agentic-retrieval",
            "yes",
            "--foundry-mcp-integration",
            "--create-pr",
            "--quiet",
        )
        assert missing == ()

    def test_descriptor_workflow_mismatch_is_rejected_before_registration(
        self, tmp_path: Path
    ) -> None:
        api = _api(
            "FR-STATE-05 descriptor identity",
            "ResumeService",
            "WorkflowDescriptor",
        )
        store = _RecordingStore()
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        descriptor = _descriptor(
            api,
            "aas-1",
            "aas",
            0,
            argv=("orchestrate", "--workflow", "ard"),
        )

        with pytest.raises(Exception, match="does not match"):
            api.ResumeService(store, repo_root).register_execution(
                "cli", (descriptor,)
            )

        assert store.registration_calls == []

    def test_resume_hash_covers_every_ordered_instance_state(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-CLI-90 ordered execution hash", "WorkflowDescriptor")
        descriptors = (
            _descriptor(api, "aas-1", "aas", 0),
            _descriptor(api, "aad-web-1", "aad-web", 1),
        )

        with _registered_service(
            tmp_path,
            "FR-CLI-90 ordered execution hash",
            descriptors,
        ) as (_, _, store, service, execution_id, _):
            before = service.build_plan(
                execution_id,
                current_head="head-at-launch",
            )
            _set_workflow_status(store, execution_id, "aad-web-1", "failed")
            after = service.build_plan(
                execution_id,
                current_head="head-at-launch",
            )

        assert before.instance_id == after.instance_id == "aas-1"
        assert before.expected_state_version == after.expected_state_version
        assert before.resume_plan_hash != after.resume_plan_hash

    def test_plaintext_replay_value_is_not_passed_to_hash_payload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _api("NFR-SEC-01 replay hash input", "WorkflowDescriptor")
        secret = "REENTERED-PROMPT-SENTINEL-f83c"
        descriptors = (
            _descriptor(
                api,
                "aas-1",
                "aas",
                0,
                argv=(
                    "orchestrate",
                    "--workflow",
                    "aas",
                    "--additional-prompt",
                    "launch-only prompt",
                ),
            ),
        )

        with _registered_service(
            tmp_path,
            "NFR-SEC-01 replay hash input",
            descriptors,
        ) as (_, _, _, service, execution_id, _):
            original = api.compute_resume_plan_hash
            captured: list[str] = []

            def capture(payload: Mapping[str, Any]) -> str:
                captured.append(api.canonical_json(payload))
                return original(payload)

            monkeypatch.setattr(api, "compute_resume_plan_hash", capture)
            plan = service.build_plan(
                execution_id,
                action="restart-step",
                replay_values={"additional_prompt": secret},
                current_head="head-at-launch",
            )

        assert captured and secret not in captured[0]
        assert any(secret in value for value in plan.argv)

    def test_multiple_input_aliases_can_be_reentered_from_one_key_only_gap(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-SEC-01 multi-alias replay", "WorkflowDescriptor")
        descriptors = (
            _descriptor(
                api,
                "aas-1",
                "aas",
                0,
                argv=(
                    "orchestrate",
                    "--workflow",
                    "aas",
                    "--input-alias",
                    "docs/a.md",
                    "incoming/a.md",
                    "--input-alias",
                    "docs/b.md",
                    "incoming/b.md",
                ),
            ),
        )

        with _registered_service(
            tmp_path,
            "NFR-SEC-01 multi-alias replay",
            descriptors,
        ) as (_, _, _, service, execution_id, _):
            plan = service.build_plan(
                execution_id,
                action="restart-step",
                replay_values={
                    "input_alias": json.dumps(
                        [
                            ["docs/a.md", "incoming/a.md"],
                            ["docs/b.md", "incoming/b.md"],
                        ]
                    )
                },
                current_head="head-at-launch",
            )

        aliases = [
            tuple(plan.argv[index + 1 : index + 3])
            for index, value in enumerate(plan.argv)
            if value == "--input-alias"
        ]
        assert aliases == [
            ("docs/a.md", "incoming/a.md"),
            ("docs/b.md", "incoming/b.md"),
        ]

    @pytest.mark.parametrize(
        ("key", "stored_flag", "launch_values", "replay_value"),
        [
            (
                "ignore_paths",
                "--ignore-paths",
                ("launch-only",),
                '["--create-pr"]',
            ),
            (
                "input_alias",
                "--input-alias",
                ("docs/a.md", "incoming/a.md"),
                '[["docs/a.md","--strict"]]',
            ),
        ],
        ids=["multi-value", "pair-value"],
    )
    def test_replay_values_cannot_inject_new_cli_options(
        self,
        tmp_path: Path,
        key: str,
        stored_flag: str,
        launch_values: tuple[str, ...],
        replay_value: str,
    ) -> None:
        api = _api("NFR-SEC-01 replay option injection", "WorkflowDescriptor")
        state_api = _state_api("NFR-SEC-01 replay option injection")
        descriptor = _descriptor(
            api,
            "aas-1",
            "aas",
            0,
            argv=(
                "orchestrate",
                "--workflow",
                "aas",
                stored_flag,
                *launch_values,
            ),
        )

        with _registered_service(
            tmp_path,
            "NFR-SEC-01 replay option injection",
            (descriptor,),
        ) as (_, _, _, service, execution_id, _):
            with pytest.raises(state_api.DurableStateError):
                service.build_plan(
                    execution_id,
                    action="restart-step",
                    replay_values={key: replay_value},
                    current_head="head-at-launch",
                )

    def test_expired_pending_owner_is_not_presented_as_safe(
        self, tmp_path: Path
    ) -> None:
        api = _api("NFR-CONC-02 expired lease takeover", "WorkflowDescriptor")
        descriptors = (_descriptor(api, "aas-1", "aas", 0),)

        with _registered_service(
            tmp_path,
            "NFR-CONC-02 expired lease takeover",
            descriptors,
        ) as (_, _, store, service, execution_id, _):
            token = store.acquire_lease(
                execution_id,
                "aas-1",
                0,
                "stale-owner",
                now=100.0,
            )
            plan = service.build_plan(
                execution_id,
                current_head="head-at-launch",
            )
            store.release_lease(token, now=101.0)

        assert "non_terminal" in _risk_codes(plan)
        assert plan.action is None

    def test_removed_stored_step_fails_closed_instead_of_expanding_scope(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-05 stored step drift", "WorkflowDescriptor")
        descriptors = (
            _descriptor(
                api,
                "aas-1",
                "aas",
                0,
                argv=(
                    "orchestrate",
                    "--workflow",
                    "aas",
                    "--steps",
                    "removed-step",
                ),
            ),
        )

        with _registered_service(
            tmp_path,
            "FR-STATE-05 stored step drift",
            descriptors,
        ) as (_, state_api, _, service, execution_id, _):
            with pytest.raises(state_api.DurableStateError, match="unknown step"):
                service.build_plan(
                    execution_id,
                    current_head="head-at-launch",
                )

    def test_service_cannot_acquire_a_plan_from_another_repository(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-CLI-90 repository-scoped lease", "WorkflowDescriptor")
        state_api = _state_api("FR-CLI-90 repository-scoped lease")
        first_root = tmp_path / "first"
        second_root = tmp_path / "second"
        first_root.mkdir()
        second_root.mkdir()

        with state_api.RunStateStore(tmp_path / "state.sqlite3") as store:
            first = api.ResumeService(store, first_root)
            execution_id = first.register_execution(
                "cli",
                (_descriptor(api, "aas-1", "aas", 0),),
            )
            plan = first.build_plan(execution_id, current_head="head-at-launch")

            with pytest.raises(state_api.DurableStateError, match="another repository"):
                api.ResumeService(store, second_root).acquire(plan, "other-owner")

    def test_completed_selected_steps_produce_no_child_argv(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-05 final-state reconciliation", "WorkflowDescriptor")
        descriptors = (
            _descriptor(
                api,
                "aas-1",
                "aas",
                0,
                argv=("orchestrate", "--workflow", "aas", "--steps", "1"),
            ),
        )

        with _registered_service(
            tmp_path,
            "FR-STATE-05 final-state reconciliation",
            descriptors,
        ) as (_, _, store, service, execution_id, repo_root):
            output = repo_root / "docs" / "catalog" / "app-arch-catalog.md"
            output.parent.mkdir(parents=True)
            output.write_text("architecture", encoding="utf-8")
            _set_step_progress(store, execution_id, "aas-1", ("1",))

            plan = service.build_plan(
                execution_id,
                action="restart-step",
                current_head="head-at-launch",
            )

        assert plan.argv == ()

    def test_completed_selected_steps_can_be_fenced_to_succeeded_without_child(
        self, tmp_path: Path
    ) -> None:
        api = _api("FR-STATE-05 reconciled completion", "WorkflowDescriptor")
        descriptors = (
            _descriptor(
                api,
                "aas-1",
                "aas",
                0,
                argv=("orchestrate", "--workflow", "aas", "--steps", "1"),
            ),
        )

        with _registered_service(
            tmp_path,
            "FR-STATE-05 reconciled completion",
            descriptors,
        ) as (_, _, store, service, execution_id, repo_root):
            output = repo_root / "docs" / "catalog" / "app-arch-catalog.md"
            output.parent.mkdir(parents=True)
            output.write_text("architecture", encoding="utf-8")
            _set_step_progress(store, execution_id, "aas-1", ("1",))
            plan = service.build_plan(
                execution_id,
                action="restart-step",
                current_head="head-at-launch",
            )
            token = service.acquire(plan, "resume-owner")
            completed_token = service.complete_reconciled(plan, token)
            store.release_lease(completed_token)
            instance = store.get_instance(execution_id, "aas-1")

        assert plan.argv == ()
        assert _field(instance, "status") == "succeeded"
        assert completed_token.state_version == plan.expected_state_version + 1
