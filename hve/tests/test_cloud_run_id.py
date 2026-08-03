"""hve/split_fork.py の `resolve_run_id` / `resolve_work_root` / Cloud 検出のテスト。"""
from __future__ import annotations

import json

import pytest

from hve import split_fork


@pytest.fixture(autouse=True)
def _reset_cache_and_env(monkeypatch):
    monkeypatch.delenv("HVE_WORK_ROOT", raising=False)
    monkeypatch.delenv("HVE_RUN_ID", raising=False)
    monkeypatch.delenv("GITHUB_ISSUE_NUMBER", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    split_fork._reset_run_id_cache()
    yield
    split_fork._reset_run_id_cache()


def test_resolve_run_id_from_env(monkeypatch):
    monkeypatch.setenv("HVE_RUN_ID", "custom-id-1")
    assert split_fork.resolve_run_id() == "custom-id-1"


def test_resolve_run_id_from_cloud_issue_number(monkeypatch):
    monkeypatch.setenv("GITHUB_ISSUE_NUMBER", "42")
    assert split_fork.resolve_run_id() == "issue-42"


def test_resolve_run_id_from_cloud_event_path(monkeypatch, tmp_path):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"issue": {"number": 99}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert split_fork.resolve_run_id() == "issue-99"


def test_resolve_run_id_fallback_generates_and_caches(monkeypatch):
    rid1 = split_fork.resolve_run_id()
    rid2 = split_fork.resolve_run_id()
    assert rid1 == rid2
    # 形式: YYYYMMDDTHHMMSS-xxxxxx
    assert len(rid1) == 22
    assert rid1[8] == "T"
    assert rid1[15] == "-"


def test_resolve_run_id_env_overrides_cache(monkeypatch):
    _ = split_fork.resolve_run_id()  # キャッシュさせる
    monkeypatch.setenv("HVE_RUN_ID", "override-id")
    assert split_fork.resolve_run_id() == "override-id"


def test_resolve_work_root_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path / "custom"))
    assert split_fork.resolve_work_root() == (tmp_path / "custom").resolve()


def test_resolve_work_root_default_uses_run_subdir(monkeypatch):
    monkeypatch.setenv("HVE_RUN_ID", "rid-123")
    root = split_fork.resolve_work_root()
    parts = root.parts
    assert parts[-3:] == ("work", "run", "rid-123")


def test_detect_cloud_run_id_invalid_event_path_returns_none(monkeypatch, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(bad))
    assert split_fork._detect_cloud_run_id() is None


def test_detect_cloud_run_id_missing_issue_number_in_event(monkeypatch, tmp_path):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 5}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert split_fork._detect_cloud_run_id() is None


def test_issue_number_takes_priority_over_event_path(monkeypatch, tmp_path):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"issue": {"number": 99}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_ISSUE_NUMBER", "42")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert split_fork._detect_cloud_run_id() == "issue-42"
