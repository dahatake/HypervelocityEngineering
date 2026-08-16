"""hve.job_interaction_ipc — 実行中ジョブ対話用のファイル IPC（FR-GUI-12）。

GUI（送信側）と `hve/runner.py`（実行側）が共有する唯一の実装。要求の書き込み・
列挙・原子的 claim・取消・順序変更と、本文を含まない ACK を提供する。

ファイル名は既存 Steering の規約（``steering-<safe_step_id>-<sequence>.request.json``）
をそのまま維持し、実行側の glob と後方互換を保つ。処理中の要求は同名 + ``.processing``
へ原子的に改名して pending から外すことで、重複送信と順序変更のレースを防ぐ。
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "ACTION_QUEUE",
    "ACTION_STEER",
    "ACTION_STOP_AND_SEND",
    "JOB_INTERACTION_SCHEMA_VERSION",
    "VALID_ACTIONS",
    "VALID_STATUSES",
    "JobInteractionRequest",
    "cancel_request",
    "claim_request",
    "list_acks",
    "list_pending_requests",
    "list_request_paths",
    "read_request",
    "release_request",
    "reorder_pending",
    "safe_step_token",
    "write_ack",
    "write_request",
]

JOB_INTERACTION_SCHEMA_VERSION = 1

ACTION_QUEUE = "queue"
ACTION_STEER = "steer"
ACTION_STOP_AND_SEND = "stop_and_send"
VALID_ACTIONS = frozenset({ACTION_QUEUE, ACTION_STEER, ACTION_STOP_AND_SEND})

VALID_STATUSES = frozenset({"accepted", "failed", "cancelled"})

_REQUEST_SUFFIX = ".request.json"
_CLAIM_SUFFIX = ".processing"
_REQUEST_NAME_RE = re.compile(
    r"^steering-(?P<token>.+)-(?P<sequence>\d+)\.request\.json$"
)
_UNSAFE_RE = re.compile(r"[^A-Za-z0-9_.-]")


@dataclass(frozen=True)
class JobInteractionRequest:
    """1 件の対話送信要求。"""

    request_id: str
    step_token: str
    action: str
    text: str
    sequence: int
    path: Path


def safe_step_token(step_id: str) -> str:
    """実行側の glob と一致するファイル名安全な step トークンを返す。"""
    return _UNSAFE_RE.sub("-", str(step_id))


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _parse_request_name(name: str) -> Optional[Dict[str, str]]:
    if name.endswith(_CLAIM_SUFFIX):
        name = name[: -len(_CLAIM_SUFFIX)]
    match = _REQUEST_NAME_RE.match(name)
    if match is None:
        return None
    return {"token": match.group("token"), "sequence": match.group("sequence")}


def _next_sequence(ipc_dir: Path, token: str) -> int:
    """同一ミリ秒の連続書き込みでも衝突しない単調な sequence を返す。"""
    candidate = int(time.time() * 1000)
    used = set()
    for path in ipc_dir.glob(f"steering-{token}-*{_REQUEST_SUFFIX}"):
        parsed = _parse_request_name(path.name)
        if parsed is not None:
            used.add(int(parsed["sequence"]))
    while candidate in used:
        candidate += 1
    return candidate


def write_request(
    ipc_dir: Path,
    step_id: str,
    text: str,
    *,
    action: str = ACTION_STEER,
    request_id: Optional[str] = None,
) -> Path:
    """対話送信要求をアトミックに書き込み、そのパスを返す。

    Raises:
        ValueError: 未知の action、または本文が空の場合。
        OSError: ディレクトリ作成・書き込みに失敗した場合。
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"unknown job interaction action: {action!r}")
    if not str(text).strip():
        raise ValueError("job interaction text must not be empty")

    ipc_dir = Path(ipc_dir)
    ipc_dir.mkdir(parents=True, exist_ok=True)
    token = safe_step_token(step_id)
    sequence = _next_sequence(ipc_dir, token)
    path = ipc_dir / f"steering-{token}-{sequence}{_REQUEST_SUFFIX}"
    _atomic_write_json(
        path,
        {
            "schema_version": JOB_INTERACTION_SCHEMA_VERSION,
            "request_id": request_id or uuid.uuid4().hex,
            "action": action,
            "text": str(text),
        },
    )
    return path


def read_request(path: Path) -> Optional[JobInteractionRequest]:
    """要求ファイルを読み取る。解釈できない場合は ``None`` を返す。

    ``{"text": ...}`` だけの既存 Steering 形式は ``steer`` として扱う。
    """
    path = Path(path)
    parsed_name = _parse_request_name(path.name)
    if parsed_name is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    action = str(data.get("action") or ACTION_STEER)
    if action not in VALID_ACTIONS:
        return None
    text = str(data.get("text", ""))
    if not text.strip():
        return None

    request_id = str(data.get("request_id") or "").strip()
    if not request_id:
        # 既存形式にはIDが無いため、ファイル名から決定論的に導出する。
        request_id = f"legacy-{parsed_name['token']}-{parsed_name['sequence']}"

    return JobInteractionRequest(
        request_id=request_id,
        step_token=parsed_name["token"],
        action=action,
        text=text,
        sequence=int(parsed_name["sequence"]),
        path=path,
    )


def list_request_paths(ipc_dir: Path, step_id: str) -> List[Path]:
    """当該 step 宛の未処理要求ファイルを作成順に返す（解釈不能なものを含む）。"""
    ipc_dir = Path(ipc_dir)
    if not ipc_dir.is_dir():
        return []
    token = safe_step_token(step_id)
    paths = list(ipc_dir.glob(f"steering-{token}-*{_REQUEST_SUFFIX}"))

    def _sequence_of(path: Path) -> int:
        parsed = _parse_request_name(path.name)
        return int(parsed["sequence"]) if parsed else 0

    return sorted(paths, key=_sequence_of)


def list_pending_requests(ipc_dir: Path, step_id: str) -> List[JobInteractionRequest]:
    """当該 step 宛の未処理要求を作成順に返す。"""
    requests = []
    for path in list_request_paths(ipc_dir, step_id):
        request = read_request(path)
        if request is not None:
            requests.append(request)
    return requests


def claim_request(path: Path) -> Optional[Path]:
    """要求を原子的に claim する。既に消費済みなら ``None`` を返す。"""
    path = Path(path)
    claim_path = path.with_name(path.name + _CLAIM_SUFFIX)
    try:
        os.replace(path, claim_path)
    except OSError:
        return None
    return claim_path


def release_request(path: Path) -> None:
    """claim 済み要求ファイルを削除する（失敗は無視する）。"""
    try:
        Path(path).unlink()
    except OSError:
        pass


def cancel_request(ipc_dir: Path, request_id: str) -> bool:
    """未処理の要求だけを取り消す。処理中・不存在なら ``False`` を返す。"""
    ipc_dir = Path(ipc_dir)
    if not ipc_dir.is_dir():
        return False
    for path in sorted(ipc_dir.glob(f"steering-*{_REQUEST_SUFFIX}")):
        request = read_request(path)
        if request is not None and request.request_id == request_id:
            try:
                path.unlink()
            except OSError:
                return False
            return True
    return False


def reorder_pending(ipc_dir: Path, step_id: str, request_ids: List[str]) -> bool:
    """未処理要求の処理順を ``request_ids`` の順へ変更する。

    ``request_ids`` に含まれない未処理要求は、指定分の後ろへ元の順序で残す。
    実在しない ID は無視する。
    """
    ipc_dir = Path(ipc_dir)
    pending = list_pending_requests(ipc_dir, step_id)
    if not pending:
        return False

    by_id = {request.request_id: request for request in pending}
    ordered: List[JobInteractionRequest] = []
    seen = set()
    for request_id in request_ids:
        request = by_id.get(request_id)
        if request is not None and request.request_id not in seen:
            ordered.append(request)
            seen.add(request.request_id)
    ordered.extend(r for r in pending if r.request_id not in seen)

    # 新しい sequence は既存の最大値より必ず大きいため、既存ファイルとは衝突しない。
    base = max(int(time.time() * 1000), max(r.sequence for r in pending) + 1)
    for offset, request in enumerate(ordered):
        final_path = ipc_dir / (
            f"steering-{request.step_token}-{base + offset}{_REQUEST_SUFFIX}"
        )
        try:
            os.replace(request.path, final_path)
        except OSError:
            # 直前に消費・取消された要求は並べ替え対象から外れるだけで、他へ影響しない。
            continue
    return True


def write_ack(
    ipc_dir: Path,
    request_id: str,
    action: str,
    status: str,
    *,
    detail: str = "",
) -> Path:
    """処理結果を ACK として書き出す。要求本文は決して含めない。

    Raises:
        ValueError: 未知の status の場合。
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown job interaction ack status: {status!r}")
    ipc_dir = Path(ipc_dir)
    ipc_dir.mkdir(parents=True, exist_ok=True)
    path = ipc_dir / f"ack-{_UNSAFE_RE.sub('-', str(request_id))}.json"
    _atomic_write_json(
        path,
        {
            "schema_version": JOB_INTERACTION_SCHEMA_VERSION,
            "request_id": str(request_id),
            "action": str(action),
            "status": status,
            "detail": str(detail),
        },
    )
    return path


def list_acks(ipc_dir: Path) -> List[Dict[str, Any]]:
    """書き出された ACK を列挙する。"""
    ipc_dir = Path(ipc_dir)
    if not ipc_dir.is_dir():
        return []
    acks: List[Dict[str, Any]] = []
    for path in sorted(ipc_dir.glob("ack-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            acks.append(data)
    return acks
