"""Phase A: workbench_logger の usage_credit / quota_snapshot パースのテスト。

runner.py の `assistant.usage` ハンドラが発火する `[hve:stats] {...}` 行を
WorkbenchState に反映する経路の検証。
"""

from __future__ import annotations

import json

from hve.gui.workbench_logger import _try_consume_stats_event, parse_stats_event
from hve.gui.workbench_state import WorkbenchState


def _make_state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf", run_id="r1", model="claude-sonnet-4")


def _stats_line(payload: dict) -> str:
    return f"[hve:stats] {json.dumps(payload, ensure_ascii=False)}"


def test_parse_stats_event_returns_payload_dict():
    line = _stats_line({"kind": "usage_credit", "step_id": "1.1", "nano_aiu": 1000})
    payload = parse_stats_event(line)
    assert payload is not None
    assert payload["kind"] == "usage_credit"
    assert payload["nano_aiu"] == 1000


def test_parse_stats_event_returns_none_for_non_stats_lines():
    assert parse_stats_event("plain log line") is None
    assert parse_stats_event("[other] {}") is None


def test_consume_usage_credit_event_accumulates_aiu():
    state = _make_state()
    line = _stats_line(
        {
            "kind": "usage_credit",
            "step_id": "1.1",
            "model": "claude-sonnet-4",
            "api_call_id": "call-1",
            "multiplier_cost": 0.5,
            "nano_aiu": 1_500_000_000,
        }
    )
    result = _try_consume_stats_event(state, line)
    assert result is True
    assert state.sdk_aiu_total_nano == 1_500_000_000
    assert state.sdk_multiplier_cost_total == 0.5
    assert "call-1" in state.seen_api_call_ids


def test_consume_usage_credit_event_dedup():
    """同 api_call_id の重複イベントは二重加算されない。"""
    state = _make_state()
    line = _stats_line(
        {
            "kind": "usage_credit",
            "step_id": "1.1",
            "api_call_id": "dup-call",
            "nano_aiu": 1_000_000_000,
        }
    )
    _try_consume_stats_event(state, line)
    _try_consume_stats_event(state, line)
    assert state.sdk_aiu_total_nano == 1_000_000_000  # 1 回分のみ


def test_consume_quota_snapshot_event_sets_baseline_and_latest():
    state = _make_state()
    line1 = _stats_line(
        {
            "kind": "quota_snapshot",
            "step_id": "1.1",
            "quota_id": "premium_interactions",
            "used_requests": 100,
            "entitlement_requests": 1000,
            "remaining_percentage": 90.0,
            "overage": 0,
            "is_unlimited_entitlement": False,
        }
    )
    line2 = _stats_line(
        {
            "kind": "quota_snapshot",
            "step_id": "1.2",
            "quota_id": "premium_interactions",
            "used_requests": 110,
            "entitlement_requests": 1000,
            "remaining_percentage": 89.0,
            "overage": 0,
        }
    )
    _try_consume_stats_event(state, line1)
    _try_consume_stats_event(state, line2)
    assert state.quota_snapshots_baseline["premium_interactions"]["used_requests"] == 100
    assert state.quota_snapshots_latest["premium_interactions"]["used_requests"] == 110
    assert state.quota_used_delta("premium_interactions") == 10


def test_consume_quota_snapshot_event_with_reset_date_iso():
    state = _make_state()
    line = _stats_line(
        {
            "kind": "quota_snapshot",
            "step_id": "1.1",
            "quota_id": "q1",
            "used_requests": 50,
            "entitlement_requests": 100,
            "reset_date_iso": "2026-07-01T00:00:00+00:00",
        }
    )
    _try_consume_stats_event(state, line)
    assert state.quota_snapshots_latest["q1"]["reset_date_iso"] == "2026-07-01T00:00:00+00:00"


def test_consume_event_consumes_unknown_kind_silently():
    """未知 kind でも True を返す (body に流出させない設計)。state は変更なし。"""
    state = _make_state()
    line = _stats_line({"kind": "some_unknown_event", "value": 42})
    result = _try_consume_stats_event(state, line)
    # body に流出させないため未知 kind でも True (consumed)
    assert result is True
    # state は何も変更されない
    assert state.sdk_aiu_total_nano == 0
    assert len(state.quota_snapshots_latest) == 0


def test_consume_quota_snapshot_missing_quota_id_is_safe():
    state = _make_state()
    line = _stats_line(
        {"kind": "quota_snapshot", "step_id": "1.1", "used_requests": 100}
    )
    # quota_id が無くても True (kind は処理対象) で、state には反映されない
    result = _try_consume_stats_event(state, line)
    assert result is True
    assert len(state.quota_snapshots_latest) == 0


def test_consume_usage_credit_with_null_values():
    """全ペイロード値が None でも例外にならず True を返す。"""
    state = _make_state()
    line = _stats_line(
        {
            "kind": "usage_credit",
            "step_id": "1.1",
            "api_call_id": None,
            "multiplier_cost": None,
            "nano_aiu": None,
        }
    )
    result = _try_consume_stats_event(state, line)
    assert result is True
    assert state.sdk_aiu_total_nano == 0


def test_consume_assistant_usage_raw_appends_to_body():
    """T1: HVE_DEBUG_ASSISTANT_USAGE=1 で発火される診断イベントは body に追記される。"""
    state = _make_state()
    raw_payload_json = json.dumps(
        {"copilot_usage": {"total_nano_aiu": 0, "token_details": []}}
    )
    line = _stats_line(
        {
            "kind": "assistant_usage_raw",
            "step_id": "1.1",
            "payload_json": raw_payload_json,
        }
    )
    result = _try_consume_stats_event(state, line)
    assert result is True
    # body (SimpleRingBuffer.lines) に追記され、prefix が SENSITIVE_DEBUG 警告付きで付くこと
    assert any(
        "[assistant_usage_raw SENSITIVE_DEBUG step=1.1]" in body_line
        and raw_payload_json in body_line
        for body_line in state.body.lines
    )


def test_consume_assistant_usage_raw_without_step_id():
    """step_id が空でも例外にならず prefix [assistant_usage_raw SENSITIVE_DEBUG] が付く。"""
    state = _make_state()
    raw_payload_json = "{\"foo\":1}"
    line = _stats_line(
        {"kind": "assistant_usage_raw", "payload_json": raw_payload_json}
    )
    result = _try_consume_stats_event(state, line)
    assert result is True
    assert any(
        body_line.startswith("[assistant_usage_raw SENSITIVE_DEBUG] ")
        and raw_payload_json in body_line
        for body_line in state.body.lines
    )


def test_consume_assistant_usage_raw_missing_payload_no_body_append():
    """payload_json が無い場合は body に追記せず、ただ True を返す。"""
    state = _make_state()
    body_len_before = len(state.body)
    line = _stats_line({"kind": "assistant_usage_raw", "step_id": "1.1"})
    result = _try_consume_stats_event(state, line)
    assert result is True
    assert len(state.body) == body_len_before


def test_consume_assistant_usage_raw_truncates_huge_payload():
    """巨大 payload (> 20000 文字) は truncate されて GUI 応答性を保護。"""
    state = _make_state()
    big = "x" * 30000
    raw_payload_json = json.dumps({"big_field": big})
    line = _stats_line(
        {
            "kind": "assistant_usage_raw",
            "step_id": "1.1",
            "payload_json": raw_payload_json,
        }
    )
    _try_consume_stats_event(state, line)
    # body の中で truncate マーカーが付いている行が存在
    assert any(
        "[assistant_usage_raw SENSITIVE_DEBUG step=1.1]" in body_line
        and body_line.endswith("... [truncated]")
        for body_line in state.body.lines
    )
    # かつ追記された行は prefix + 20000 + " ... [truncated]" 程度の長さ以下
    target_lines = [
        b for b in state.body.lines if "SENSITIVE_DEBUG" in b and "[truncated]" in b
    ]
    assert len(target_lines) == 1
    # 20000 + prefix + suffix (40 文字程度) 以内
    assert len(target_lines[0]) < 21000


def test_consume_assistant_usage_raw_non_string_payload_is_serialized():
    """payload_json が dict で来ても JSON 化されて str として body に乗る。"""
    state = _make_state()
    line = _stats_line(
        {
            "kind": "assistant_usage_raw",
            "step_id": "1.1",
            "payload_json": {"total_nano_aiu": 12345},
        }
    )
    _try_consume_stats_event(state, line)
    assert any(
        "[assistant_usage_raw SENSITIVE_DEBUG step=1.1]" in body_line
        and "12345" in body_line
        for body_line in state.body.lines
    )


def test_process_log_line_routes_assistant_usage_raw_to_body_once():
    """process_log_line 経由でも body に 1 行のみ追記され、元の [hve:stats] 行は重複混入しない。"""
    from hve.gui.workbench_logger import process_log_line  # 経路網羅のため遅延 import

    state = _make_state()
    raw_payload_json = json.dumps({"total_nano_aiu": 0})
    stats_line = _stats_line(
        {
            "kind": "assistant_usage_raw",
            "step_id": "1.1",
            "payload_json": raw_payload_json,
        }
    )
    process_log_line(state, stats_line)
    matched = [b for b in state.body.lines if "assistant_usage_raw" in b]
    assert len(matched) == 1
    assert matched[0].startswith("[assistant_usage_raw SENSITIVE_DEBUG step=1.1] ")
    # 元の `[hve:stats]` 行は body に流れないこと（_try_consume_stats_event が True 返却で抑制）
    assert not any(b.startswith("[hve:stats]") for b in state.body.lines)


# ----- T1.5: debug_env / assistant_usage_raw_err -----



def test_consume_debug_env_appends_env_dump_to_body():
    """T1.5 (P1/P2/P4 切り分け用): debug_env stats_event は state に
    数値変化を起こさず、env 値を body に追記して終わる。"""
    state = _make_state()
    payload = {
        "kind": "debug_env",
        "step_id": "1.1",
        "HVE_DEBUG_ASSISTANT_USAGE_raw": "1",
        "HVE_DEBUG_ASSISTANT_USAGE_repr": "'1'",
        "HVE_DEBUG_ASSISTANT_USAGE_len": 1,
        "pid": 12345,
    }
    line = _stats_line(payload)
    consumed = _try_consume_stats_event(state, line)
    assert consumed is True
    matched = [b for b in state.body.lines if "[debug_env step=1.1]" in b]
    assert len(matched) == 1
    # env 名と pid が body 行内に文字列として現れる
    assert "HVE_DEBUG_ASSISTANT_USAGE_raw" in matched[0]
    assert "12345" in matched[0]


def test_consume_debug_env_without_step_id_uses_bare_prefix():
    state = _make_state()
    payload = {
        "kind": "debug_env",
        "HVE_DEBUG_ASSISTANT_USAGE_raw": "<unset>",
        "pid": 999,
    }
    line = _stats_line(payload)
    consumed = _try_consume_stats_event(state, line)
    assert consumed is True
    matched = [b for b in state.body.lines if "[debug_env]" in b]
    assert len(matched) == 1
    assert matched[0].startswith("[debug_env] ")


def test_consume_assistant_usage_raw_err_appends_error_line_to_body():
    """T1.5 (P3 切り分け用): runner.py 側で payload シリアライズに失敗した場合、
    silent fail せず err_type / err が body に追記される。"""
    state = _make_state()
    payload = {
        "kind": "assistant_usage_raw_err",
        "step_id": "2.1",
        "err": "Object of type set is not JSON serializable",
        "err_type": "TypeError",
    }
    line = _stats_line(payload)
    consumed = _try_consume_stats_event(state, line)
    assert consumed is True
    matched = [b for b in state.body.lines if "[assistant_usage_raw_err step=2.1]" in b]
    assert len(matched) == 1
    assert "TypeError" in matched[0]
    assert "Object of type set is not JSON serializable" in matched[0]


# ----------------------------------------------------------------------
# T4: assistant_usage_count フォールバック
# ----------------------------------------------------------------------


def test_usage_credit_does_not_increment_assistant_usage_count():
    """usage_credit イベントは assistant_usage_count を増やさない。
    既存 apply_assistant_usage (assistant_usage イベント) で既に +1 されており、
    runner.py は同じ SDK assistant.usage から両イベントを発火するため、
    二重加算を防ぐ目的で usage_credit 側ではカウントしない。"""
    state = _make_state()
    line = _stats_line(
        {"kind": "usage_credit", "step_id": "1.1", "api_call_id": "call-1", "multiplier_cost": 1.0}
    )
    _try_consume_stats_event(state, line)
    _try_consume_stats_event(state, line)
    assert state.assistant_usage_count == 0


def test_assistant_usage_event_increments_count_only_once_per_api_call():
    """SDK assistant.usage 1 回につき assistant_usage_count が +1 される (既存挙動)。"""
    state = _make_state()
    # 既存 apply_assistant_usage 経路で +1 される
    state.apply_assistant_usage(input_tokens=100, output_tokens=50)
    state.apply_assistant_usage(input_tokens=200, output_tokens=80)
    assert state.assistant_usage_count == 2


def test_paired_assistant_usage_and_usage_credit_no_double_count():
    """runner.py が同 API call で assistant_usage + usage_credit を両方発火しても
    assistant_usage_count は 1 回しか増えない (rubber-duck Blocking #1 対応)。"""
    state = _make_state()
    # assistant_usage 経路
    state.apply_assistant_usage(input_tokens=100)
    # 同じ API call の usage_credit
    credit_line = _stats_line(
        {"kind": "usage_credit", "step_id": "1.1", "api_call_id": "call-X", "multiplier_cost": 1.0}
    )
    _try_consume_stats_event(state, credit_line)
    assert state.assistant_usage_count == 1
