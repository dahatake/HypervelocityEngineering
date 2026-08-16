"""hve.gui.tests.test_job_interaction_ipc

FR-GUI-12 の IPC 契約テスト。

GUI と `hve/runner.py` が共有する実行中ジョブ対話用ファイル IPC の
スキーマ・原子性・順序・未消費要求限定の順序変更/取消・ACK の
安全性（本文非複製）を固定する。Qt もネットワークも使わない。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from hve.job_interaction_ipc import (
    ACTION_QUEUE,
    ACTION_STEER,
    ACTION_STOP_AND_SEND,
    JOB_INTERACTION_SCHEMA_VERSION,
    VALID_ACTIONS,
    JobInteractionRequest,
    cancel_request,
    claim_request,
    list_acks,
    list_pending_requests,
    read_request,
    reorder_pending,
    safe_step_token,
    write_ack,
    write_request,
)


_SECRET = "Actually, stop using Synapse. token=ghp_ThisMustNeverBeCopied"


# ---------------------------------------------------------------------------
# スキーマと書き込み
# ---------------------------------------------------------------------------


def test_actions_are_the_three_vs_code_style_actions() -> None:
    assert VALID_ACTIONS == frozenset({ACTION_QUEUE, ACTION_STEER, ACTION_STOP_AND_SEND})


def test_write_request_matches_runner_polling_glob(tmp_path: Path) -> None:
    path = write_request(tmp_path, "2.3", "hi", action=ACTION_QUEUE)
    token = safe_step_token("2.3")
    assert path in list(tmp_path.glob(f"steering-{token}-*.request.json"))
    assert re.match(r"^steering-2\.3-\d+\.request\.json$", path.name)


def test_write_request_records_schema_action_and_request_id(tmp_path: Path) -> None:
    path = write_request(tmp_path, "1.1", "hello", action=ACTION_STOP_AND_SEND)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == JOB_INTERACTION_SCHEMA_VERSION
    assert data["action"] == ACTION_STOP_AND_SEND
    assert data["text"] == "hello"
    assert isinstance(data["request_id"], str) and data["request_id"]


def test_write_request_defaults_to_steer(tmp_path: Path) -> None:
    path = write_request(tmp_path, "1.1", "hello")
    assert json.loads(path.read_text(encoding="utf-8"))["action"] == ACTION_STEER


def test_write_request_rejects_unknown_action(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_request(tmp_path, "1.1", "hello", action="broadcast")


def test_write_request_rejects_empty_text(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_request(tmp_path, "1.1", "   ")


def test_write_request_creates_missing_directory(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    path = write_request(nested, "1.1", "hi")
    assert nested.is_dir() and path.exists()


def test_write_request_leaves_no_temp_file(tmp_path: Path) -> None:
    write_request(tmp_path, "1.1", "hi")
    assert list(tmp_path.glob("*.tmp")) == []


def test_write_request_sanitizes_fanout_step_id(tmp_path: Path) -> None:
    path = write_request(tmp_path, "1.2/D01", "hi")
    assert "/" not in path.name
    assert path.exists()


def test_consecutive_requests_get_unique_files(tmp_path: Path) -> None:
    """同一ミリ秒でもファイル名が衝突せず、全要求が保持される。"""
    paths = [write_request(tmp_path, "1.1", f"m{i}") for i in range(20)]
    assert len({p.name for p in paths}) == 20
    assert len(list_pending_requests(tmp_path, "1.1")) == 20


# ---------------------------------------------------------------------------
# 読み取りと後方互換
# ---------------------------------------------------------------------------


def test_read_request_parses_written_request(tmp_path: Path) -> None:
    path = write_request(tmp_path, "1.1", "hello", action=ACTION_QUEUE)
    request = read_request(path)
    assert isinstance(request, JobInteractionRequest)
    assert request.action == ACTION_QUEUE
    assert request.text == "hello"
    assert request.step_token == safe_step_token("1.1")


def test_legacy_text_only_request_is_treated_as_steer(tmp_path: Path) -> None:
    """既存 Steering 形式 `{"text": ...}` を後方互換で steer として解釈する。"""
    legacy = tmp_path / "steering-1.1-1000.request.json"
    legacy.write_text(json.dumps({"text": "legacy"}), encoding="utf-8")
    request = read_request(legacy)
    assert request is not None
    assert request.action == ACTION_STEER
    assert request.text == "legacy"
    assert request.request_id


def test_malformed_request_returns_none(tmp_path: Path) -> None:
    broken = tmp_path / "steering-1.1-1000.request.json"
    broken.write_text("{not json", encoding="utf-8")
    assert read_request(broken) is None


def test_request_with_unknown_action_returns_none(tmp_path: Path) -> None:
    bad = tmp_path / "steering-1.1-1000.request.json"
    bad.write_text(json.dumps({"action": "broadcast", "text": "x"}), encoding="utf-8")
    assert read_request(bad) is None


def test_pending_requests_are_returned_in_creation_order(tmp_path: Path) -> None:
    for i in range(5):
        write_request(tmp_path, "1.1", f"m{i}")
    texts = [r.text for r in list_pending_requests(tmp_path, "1.1")]
    assert texts == ["m0", "m1", "m2", "m3", "m4"]


def test_pending_requests_are_scoped_to_the_step(tmp_path: Path) -> None:
    write_request(tmp_path, "1.1", "mine")
    write_request(tmp_path, "2.1", "theirs")
    assert [r.text for r in list_pending_requests(tmp_path, "1.1")] == ["mine"]


# ---------------------------------------------------------------------------
# 未消費要求だけの取消・順序変更
# ---------------------------------------------------------------------------


def test_cancel_removes_only_the_target_request(tmp_path: Path) -> None:
    a = write_request(tmp_path, "1.1", "a")
    write_request(tmp_path, "1.1", "b")
    request_a = read_request(a)
    assert request_a is not None
    assert cancel_request(tmp_path, request_a.request_id) is True
    assert [r.text for r in list_pending_requests(tmp_path, "1.1")] == ["b"]


def test_cancel_unknown_request_returns_false(tmp_path: Path) -> None:
    assert cancel_request(tmp_path, "does-not-exist") is False


def test_cancel_of_claimed_request_is_rejected(tmp_path: Path) -> None:
    """処理中（claim 済み）の要求は取り消せない。"""
    path = write_request(tmp_path, "1.1", "a")
    request = read_request(path)
    assert request is not None
    assert claim_request(path) is not None
    assert cancel_request(tmp_path, request.request_id) is False


def test_reorder_changes_pending_order(tmp_path: Path) -> None:
    write_request(tmp_path, "1.1", "a")
    write_request(tmp_path, "1.1", "b")
    write_request(tmp_path, "1.1", "c")
    pending = list_pending_requests(tmp_path, "1.1")
    desired = [pending[2].request_id, pending[0].request_id, pending[1].request_id]
    assert reorder_pending(tmp_path, "1.1", desired) is True
    assert [r.text for r in list_pending_requests(tmp_path, "1.1")] == ["c", "a", "b"]


def test_reorder_ignores_unknown_ids(tmp_path: Path) -> None:
    write_request(tmp_path, "1.1", "a")
    pending = list_pending_requests(tmp_path, "1.1")
    assert reorder_pending(tmp_path, "1.1", ["ghost", pending[0].request_id]) is True
    assert [r.text for r in list_pending_requests(tmp_path, "1.1")] == ["a"]


def test_reorder_does_not_duplicate_or_drop_requests(tmp_path: Path) -> None:
    for name in ("a", "b", "c"):
        write_request(tmp_path, "1.1", name)
    pending = list_pending_requests(tmp_path, "1.1")
    reorder_pending(tmp_path, "1.1", [pending[1].request_id])
    texts = sorted(r.text for r in list_pending_requests(tmp_path, "1.1"))
    assert texts == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# 原子的 claim（重複処理の防止）
# ---------------------------------------------------------------------------


def test_claim_removes_request_from_pending(tmp_path: Path) -> None:
    path = write_request(tmp_path, "1.1", "a")
    claimed = claim_request(path)
    assert claimed is not None and claimed.exists()
    assert list_pending_requests(tmp_path, "1.1") == []


def test_second_claim_of_the_same_request_fails(tmp_path: Path) -> None:
    path = write_request(tmp_path, "1.1", "a")
    assert claim_request(path) is not None
    assert claim_request(path) is None


# ---------------------------------------------------------------------------
# ACK（本文を複製しない）
# ---------------------------------------------------------------------------


def test_ack_records_only_request_id_action_and_status(tmp_path: Path) -> None:
    ack_path = write_ack(tmp_path, "req-1", ACTION_STEER, "accepted")
    data = json.loads(ack_path.read_text(encoding="utf-8"))
    assert data["request_id"] == "req-1"
    assert data["action"] == ACTION_STEER
    assert data["status"] == "accepted"
    assert data["schema_version"] == JOB_INTERACTION_SCHEMA_VERSION
    assert "text" not in data


def test_ack_never_contains_the_prompt_text(tmp_path: Path) -> None:
    path = write_request(tmp_path, "1.1", _SECRET)
    request = read_request(path)
    assert request is not None
    ack_path = write_ack(tmp_path, request.request_id, request.action, "accepted")
    assert _SECRET not in ack_path.read_text(encoding="utf-8")


def test_ack_rejects_unknown_status(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_ack(tmp_path, "req-1", ACTION_STEER, "maybe")


def test_ack_files_are_not_picked_up_as_requests(tmp_path: Path) -> None:
    write_ack(tmp_path, "req-1", ACTION_STEER, "accepted")
    assert list_pending_requests(tmp_path, "1.1") == []


def test_list_acks_returns_written_acks(tmp_path: Path) -> None:
    write_ack(tmp_path, "req-1", ACTION_STEER, "accepted")
    write_ack(tmp_path, "req-2", ACTION_QUEUE, "failed", detail="session closed")
    acks = {a["request_id"]: a for a in list_acks(tmp_path)}
    assert set(acks) == {"req-1", "req-2"}
    assert acks["req-2"]["status"] == "failed"
    assert acks["req-2"]["detail"] == "session closed"


def test_ack_leaves_no_temp_file(tmp_path: Path) -> None:
    write_ack(tmp_path, "req-1", ACTION_STEER, "accepted")
    assert list(tmp_path.glob("*.tmp")) == []


def test_missing_directory_yields_empty_listings(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    assert list_pending_requests(missing, "1.1") == []
    assert list_acks(missing) == []
