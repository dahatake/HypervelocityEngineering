"""generate_run_id() タイムゾーン解決のテスト。"""

from __future__ import annotations

import os
import re

import pytest

from hve.config import generate_run_id


_RE = re.compile(r"^(\d{8}T\d{6})-[0-9a-f]{6}$")


def _extract_ts(run_id: str) -> str:
    m = _RE.match(run_id)
    assert m, f"run-id format invalid: {run_id}"
    return m.group(1)


def test_default_is_jst(monkeypatch: pytest.MonkeyPatch) -> None:
    """引数なし・env なしは JST (Asia/Tokyo, UTC+9) で生成される。

    JST と UTC の時刻部分を datetime としてパースし、差が 9 時間 ±数秒であることを検証。
    """
    from datetime import datetime, timedelta

    monkeypatch.delenv("HVE_RUN_ID_TZ", raising=False)
    rid_jst = generate_run_id()
    rid_utc = generate_run_id("UTC")
    ts_jst = datetime.strptime(_extract_ts(rid_jst), "%Y%m%dT%H%M%S")
    ts_utc = datetime.strptime(_extract_ts(rid_utc), "%Y%m%dT%H%M%S")
    diff = ts_jst - ts_utc
    # 連続呼び出しでも数秒以内に完了するため、差は 9 時間 ±10 秒
    assert timedelta(hours=9) - timedelta(seconds=10) <= diff <= timedelta(hours=9) + timedelta(seconds=10), (
        f"JST と UTC の差が 9 時間でない: jst={ts_jst} utc={ts_utc} diff={diff}"
    )


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """HVE_RUN_ID_TZ で UTC を指定できる。"""
    monkeypatch.setenv("HVE_RUN_ID_TZ", "UTC")
    rid = generate_run_id()
    assert _RE.match(rid)


def test_explicit_arg_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """引数は env より優先される。"""
    monkeypatch.setenv("HVE_RUN_ID_TZ", "UTC")
    rid = generate_run_id("Asia/Tokyo")
    assert _RE.match(rid)


def test_invalid_tz_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """不正な tz 名はフォールバックして例外を投げない。"""
    monkeypatch.delenv("HVE_RUN_ID_TZ", raising=False)
    rid = generate_run_id("Not/A_Real_Zone")
    assert _RE.match(rid)


def test_format_stable() -> None:
    """フォーマットは YYYYMMDDTHHMMSS-<hex6> で安定。"""
    rid = generate_run_id("UTC")
    assert _RE.match(rid), rid


def test_uniqueness() -> None:
    """連続呼び出しで UUID 部分により一意性が保たれる。"""
    ids = {generate_run_id("UTC") for _ in range(20)}
    assert len(ids) == 20
