"""cloud_session.py — GitHub Copilot SDK Cloud Sessions helpers.

This module keeps Cloud Session option construction and small policy helpers out of
runner/orchestrator code. It intentionally avoids broad abstraction layers; callers
still own session lifecycle and fallback behavior.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional, Tuple

CLOUD_SESSION_EVENT_PREFIX: str = "[hve:cloud-session]"
_LIMITERS: Dict[int, "CloudSessionLimiter"] = {}


def resolve_cloud_repository(config: Any) -> Tuple[str, str, Optional[str]]:
    """Resolve Cloud Session repository parameters from config.

    Explicit Cloud Session owner/name/branch values win. Empty owner/name values
    are completed from ``config.repo`` when it is in ``owner/repo`` form. Branch
    falls back to ``config.base_branch``.
    """
    owner = _clean(getattr(config, "cloud_session_repository_owner", None))
    name = _clean(getattr(config, "cloud_session_repository_name", None))
    repo = _clean(getattr(config, "repo", None))
    if (not owner or not name) and repo:
        parts = [part.strip() for part in repo.split("/")]
        if len(parts) == 2 and all(parts):
            repo_owner, repo_name = parts
            owner = owner or repo_owner
            name = name or repo_name

    branch = _clean(getattr(config, "cloud_session_repository_branch", None))
    if not branch:
        branch = _clean(getattr(config, "base_branch", None))
    return owner or "", name or "", branch


def should_use_cloud_session(
    config: Any,
    *,
    step_id: Optional[str] = None,
    subtask_kind: Optional[str] = None,
) -> bool:
    """Return whether a session should be created as a Cloud Session.

    Precedence is workflow default -> runtime auto routing -> step override -> subtask-kind override.
    """
    enabled = bool(getattr(config, "cloud_session_enabled", False))
    step_key = _clean(step_id)
    if step_key:
        runtime_overrides = getattr(config, "cloud_session_runtime_step_overrides", {}) or {}
        if isinstance(runtime_overrides, dict) and step_key in runtime_overrides:
            enabled = bool(runtime_overrides[step_key])

        step_overrides = getattr(config, "cloud_session_step_overrides", {}) or {}
        if isinstance(step_overrides, dict) and step_key in step_overrides:
            enabled = bool(step_overrides[step_key])

    subtask_key = _clean(subtask_kind)
    if subtask_key:
        subtask_overrides = getattr(config, "cloud_session_subtask_overrides", {}) or {}
        if isinstance(subtask_overrides, dict) and subtask_key in subtask_overrides:
            enabled = bool(subtask_overrides[subtask_key])
    return enabled


def compute_cloud_session_routing(
    config: Any,
    steps: list[Any],
    *,
    workflow_id: Optional[str] = None,
    wave_index: Optional[int] = None,
    parallel_limit: Optional[int] = None,
    local_min: int = 1,
) -> Dict[str, bool]:
    """Compute local/cloud routing for one executable DAG wave.

    Rules:
    - Cloud Session 全体が OFF の場合は自動割当しない（手動 step override は別途有効）。
    - 1 wave に 1 task だけなら runtime では local を割り当てる。
    - 複数 task の wave では local を最低 ``local_min`` 件残し、残りから最大で約半数を Cloud にする。
    - ``cloud_session_max_concurrency`` を超えて Cloud に割り当てない。
    - 明示的な step override は最終判定で優先されるため、ここでも manual 値として扱う。
    """
    step_ids = [_step_id(step) for step in steps]
    step_ids = [sid for sid in step_ids if sid]
    if not step_ids or not bool(getattr(config, "cloud_session_enabled", False)):
        return {}

    manual = getattr(config, "cloud_session_step_overrides", {}) or {}
    manual_true = {sid for sid in step_ids if isinstance(manual, dict) and manual.get(sid) is True}
    manual_false = {sid for sid in step_ids if isinstance(manual, dict) and manual.get(sid) is False}
    auto_ids = [sid for sid in step_ids if sid not in manual_true and sid not in manual_false]
    auto_id_set = set(auto_ids)

    try:
        effective_parallel = (
            min(len(step_ids), max(1, int(parallel_limit)))
            if parallel_limit is not None
            else len(step_ids)
        )
    except (TypeError, ValueError):
        effective_parallel = len(step_ids)

    # 1 度に 1 task しか走らない場合は原則 local。
    # 手動 override があれば should_use_cloud_session 側で上書きされる。
    if effective_parallel <= 1:
        return {sid: False for sid in auto_ids}

    try:
        local_floor = max(1, int(local_min))
    except (TypeError, ValueError):
        local_floor = 1
    try:
        cloud_cap = max(1, int(getattr(config, "cloud_session_max_concurrency", 5) or 5))
    except (TypeError, ValueError):
        cloud_cap = 5

    cloud_ids: set[str] = set()
    for batch_start in range(0, len(step_ids), effective_parallel):
        batch_ids = step_ids[batch_start:batch_start + effective_parallel]
        batch_auto_ids = [sid for sid in batch_ids if sid in auto_id_set]
        if not batch_auto_ids:
            continue
        batch_manual_true = sum(1 for sid in batch_ids if sid in manual_true)
        batch_manual_false = sum(1 for sid in batch_ids if sid in manual_false)
        batch_target_total = max(1, len(batch_ids) // 2)
        batch_cloud_capacity = max(0, min(cloud_cap, batch_target_total) - batch_manual_true)
        batch_local_needed_from_auto = max(0, local_floor - batch_manual_false)
        batch_auto_cloud_limit = max(0, len(batch_auto_ids) - batch_local_needed_from_auto)
        batch_auto_cloud_count = min(
            batch_cloud_capacity,
            batch_auto_cloud_limit,
        )
        if (
            batch_auto_cloud_count <= 0
            and batch_manual_true == 0
            and batch_cloud_capacity > 0
            and batch_auto_cloud_limit > 0
        ):
            batch_auto_cloud_count = 1
        if batch_auto_cloud_count <= 0:
            continue
        ranked_batch_auto_ids = sorted(
            batch_auto_ids,
            key=lambda sid: _routing_score(workflow_id, wave_index, sid),
        )
        cloud_ids.update(ranked_batch_auto_ids[:batch_auto_cloud_count])
    return {sid: sid in cloud_ids for sid in auto_ids}


def apply_cloud_session_auto_routing(
    config: Any,
    steps: list[Any],
    *,
    workflow_id: Optional[str] = None,
    wave_index: Optional[int] = None,
    parallel_limit: Optional[int] = None,
    local_min: int = 1,
) -> Dict[str, bool]:
    """Apply auto routing for one DAG wave to ``config`` runtime overrides."""
    routing = compute_cloud_session_routing(
        config,
        steps,
        workflow_id=workflow_id,
        wave_index=wave_index,
        parallel_limit=parallel_limit,
        local_min=local_min,
    )
    if not routing:
        return {}
    runtime = getattr(config, "cloud_session_runtime_step_overrides", None)
    if not isinstance(runtime, dict):
        runtime = {}
        try:
            setattr(config, "cloud_session_runtime_step_overrides", runtime)
        except Exception:
            return routing
    runtime.update(routing)
    return routing


def build_cloud_session_options(
    config: Any,
    *,
    step_id: Optional[str] = None,
    subtask_kind: Optional[str] = None,
) -> Optional[Any]:
    """Build SDK CloudSessionOptions, or return None when Cloud Session is disabled.

    Missing repository owner/name also returns None so the caller can use the
    local session fallback path without treating this as a hard failure.
    """
    if not should_use_cloud_session(config, step_id=step_id, subtask_kind=subtask_kind):
        return None

    owner, name, branch = resolve_cloud_repository(config)
    if not owner or not name:
        return None

    try:
        copilot_module = importlib.import_module("copilot")
    except ImportError:
        return None
    CloudSessionOptions = getattr(copilot_module, "CloudSessionOptions", None)
    CloudSessionRepository = getattr(copilot_module, "CloudSessionRepository", None)
    if CloudSessionOptions is None or CloudSessionRepository is None:
        return None

    repository_kwargs = {"owner": owner, "name": name}
    if branch:
        repository_kwargs["branch"] = branch
    repository = CloudSessionRepository(**repository_kwargs)
    return CloudSessionOptions(repository=repository)


def is_policy_blocked_error(exc: BaseException) -> bool:
    """Best-effort detection for Cloud Session policy-blocked errors."""
    for attr in ("reason", "code", "error_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, str) and value.strip().lower() == "policy_blocked":
            return True
    return "policy_blocked" in str(exc).lower()


def format_cloud_session_event_line(
    *,
    step_id: Optional[str],
    subtask_kind: Optional[str],
    url: str,
) -> str:
    """Return a single structured stdout line for GUI Workbench consumption."""
    payload = {
        "step_id": step_id or "",
        "subtask_kind": subtask_kind or "",
        "url": url,
    }
    return f"{CLOUD_SESSION_EVENT_PREFIX} {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def extract_mission_control_url(event: Any) -> str:
    """Extract Mission Control URL from SDK ``session.info`` remote events."""
    event_type = getattr(getattr(event, "type", None), "value", None)
    if event_type is None:
        event_type = getattr(event, "type", "")
    if str(event_type) != "session.info":
        return ""
    data = getattr(event, "data", None)
    info_type = _get_attr(data, "info_type", "infoType")
    if str(info_type) != "remote":
        return ""
    for attr in ("url", "href", "link", "remote_url", "remoteUrl", "value"):
        value = _get_attr(data, attr)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("url") or value.get("href")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return ""


def attach_cloud_session_event_logger(
    session: Any,
    *,
    step_id: Optional[str],
    subtask_kind: Optional[str],
) -> None:
    """Subscribe to remote session.info events and print Workbench-readable lines."""
    on = getattr(session, "on", None)
    if not callable(on):
        return

    def _handler(event: Any) -> None:
        url = extract_mission_control_url(event)
        if not url:
            return
        print(
            format_cloud_session_event_line(
                step_id=step_id,
                subtask_kind=subtask_kind,
                url=url,
            ),
            file=sys.stdout,
            flush=True,
        )

    try:
        on(_handler)
    except Exception:
        return


def get_cloud_session_limiter(config: Any) -> "CloudSessionLimiter":
    """Return a per-config CloudSessionLimiter for this process."""
    key = id(config)
    limiter = _LIMITERS.get(key)
    max_concurrency = getattr(config, "cloud_session_max_concurrency", 5)
    if limiter is None or limiter.max_concurrency != max(1, int(max_concurrency or 5)):
        limiter = CloudSessionLimiter(max_concurrency)
        _LIMITERS[key] = limiter
    return limiter


async def acquire_cloud_session_slot(config: Any) -> "CloudSessionLimiter":
    limiter = get_cloud_session_limiter(config)
    await limiter.acquire_slot()
    return limiter


def attach_cloud_session_limiter_release(session: Any, limiter: "CloudSessionLimiter") -> None:
    """Release the limiter slot when ``session.disconnect()`` is called."""
    if getattr(session, "_hve_cloud_limiter_release_attached", False):
        return
    disconnect = getattr(session, "disconnect", None)
    if not callable(disconnect):
        limiter.release_slot()
        return

    released = False

    async def _disconnect(*args: Any, **kwargs: Any) -> Any:
        nonlocal released
        try:
            return await disconnect(*args, **kwargs)
        finally:
            if not released:
                released = True
                limiter.release_slot()

    try:
        setattr(session, "disconnect", _disconnect)
        setattr(session, "_hve_cloud_limiter_release_attached", True)
    except Exception:
        limiter.release_slot()


class CloudSessionLimiter:
    """Limit active Cloud Sessions for one shared instance on one event loop."""

    def __init__(self, max_concurrency: int) -> None:
        try:
            normalized = int(max_concurrency)
        except (TypeError, ValueError):
            normalized = 5
        self.max_concurrency = max(1, normalized)
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        self._active_count = 0

    @property
    def active_count(self) -> int:
        return self._active_count

    async def acquire_slot(self) -> None:
        await self._semaphore.acquire()
        self._active_count += 1

    def release_slot(self) -> None:
        if self._active_count <= 0:
            return
        self._active_count -= 1
        self._semaphore.release()

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        await self.acquire_slot()
        try:
            yield
        finally:
            self.release_slot()


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _get_attr(data: Any, *names: str) -> Any:
    if data is None:
        return None
    for name in names:
        value = getattr(data, name, None)
        if value is not None:
            return value
        if isinstance(data, dict) and name in data:
            return data[name]
    return None


def _step_id(step: Any) -> str:
    if isinstance(step, str):
        return step.strip()
    return str(getattr(step, "id", "") or "").strip()


def _routing_score(workflow_id: Optional[str], wave_index: Optional[int], step_id: str) -> int:
    seed = f"{workflow_id or ''}:{wave_index or 0}:{step_id}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)
