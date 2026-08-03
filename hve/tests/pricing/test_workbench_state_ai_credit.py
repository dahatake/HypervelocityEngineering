"""Phase A: SDK 直接値 (AI Credit / Quota Snapshot) の WorkbenchState 単体テスト。

`session.disconnect()` が即時ハンドラクリアするため `session.shutdown` 経由の
`totalPremiumRequests` が届かない問題への対応。`assistant.usage` イベントから
`copilot_usage.total_nano_aiu` / `cost` / `quota_snapshots` を毎ターン抽出する
経路の検証。
"""

from __future__ import annotations

import pytest

from hve.gui.workbench_state import WorkbenchState


def _make_state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf", run_id="r1", model="claude-sonnet-4")


# ----------------------------------------------------------------------
# apply_assistant_credit
# ----------------------------------------------------------------------


def test_apply_credit_accumulates_nano_aiu():
    s = _make_state()
    # 1.0 AIU = 1e9 Nano AIU
    result = s.apply_assistant_credit(
        api_call_id="call-1",
        model="claude-sonnet-4",
        nano_aiu=1_000_000_000,
        multiplier_cost=0.25,
    )
    assert result is True
    assert s.sdk_aiu_total_nano == 1_000_000_000
    assert pytest.approx(s.sdk_aiu_total) == 1.0
    assert pytest.approx(s.sdk_multiplier_cost_total) == 0.25


def test_apply_credit_dedup_by_api_call_id():
    """同じ api_call_id は重複排除される (イベント再送対策)。"""
    s = _make_state()
    s.apply_assistant_credit(api_call_id="call-1", nano_aiu=500_000_000)
    s.apply_assistant_credit(api_call_id="call-1", nano_aiu=500_000_000)  # 重複
    assert s.sdk_aiu_total_nano == 500_000_000  # 二重加算されない
    assert len(s.seen_api_call_ids) == 1


def test_apply_credit_multiple_different_ids_accumulate():
    s = _make_state()
    s.apply_assistant_credit(api_call_id="call-1", nano_aiu=300_000_000)
    s.apply_assistant_credit(api_call_id="call-2", nano_aiu=700_000_000)
    assert s.sdk_aiu_total_nano == 1_000_000_000
    assert len(s.seen_api_call_ids) == 2


def test_apply_credit_without_api_call_id_accumulates():
    """api_call_id が無い場合は重複排除されない (補助的フォールバック)。"""
    s = _make_state()
    s.apply_assistant_credit(nano_aiu=100_000_000)
    s.apply_assistant_credit(nano_aiu=200_000_000)
    assert s.sdk_aiu_total_nano == 300_000_000


def test_apply_credit_none_values_are_safe():
    s = _make_state()
    # 全部 None → 何も累積されず、戻り値も False
    result = s.apply_assistant_credit(api_call_id="call-1")
    assert result is False
    assert s.sdk_aiu_total_nano == 0
    assert s.sdk_multiplier_cost_total is None


def test_apply_credit_model_breakdown():
    s = _make_state()
    s.apply_assistant_credit(
        api_call_id="c1", model="claude-sonnet-4", nano_aiu=1_000_000_000
    )
    s.apply_assistant_credit(
        api_call_id="c2", model="gpt-5", nano_aiu=2_000_000_000
    )
    s.apply_assistant_credit(
        api_call_id="c3", model="claude-sonnet-4", nano_aiu=500_000_000
    )
    assert "claude-sonnet-4" in s.sdk_credit_per_model
    assert "gpt-5" in s.sdk_credit_per_model
    assert s.sdk_credit_per_model["claude-sonnet-4"]["nano_aiu"] == 1_500_000_000
    assert s.sdk_credit_per_model["claude-sonnet-4"]["count"] == 2
    assert s.sdk_credit_per_model["gpt-5"]["count"] == 1


def test_apply_credit_invalid_values_are_skipped():
    s = _make_state()
    s.apply_assistant_credit(api_call_id="c1", nano_aiu="not-a-number")
    s.apply_assistant_credit(api_call_id="c2", multiplier_cost="invalid")
    assert s.sdk_aiu_total_nano == 0
    assert s.sdk_multiplier_cost_total is None


# ----------------------------------------------------------------------
# apply_quota_snapshot / quota_used_delta
# ----------------------------------------------------------------------


def test_quota_snapshot_baseline_is_set_on_first_observation():
    s = _make_state()
    s.apply_quota_snapshot(
        "premium_interactions",
        {"used_requests": 100, "entitlement_requests": 1000},
    )
    assert "premium_interactions" in s.quota_snapshots_baseline
    assert s.quota_snapshots_baseline["premium_interactions"]["used_requests"] == 100
    # 初回時点では delta = 0
    assert s.quota_used_delta("premium_interactions") == 0


def test_quota_snapshot_delta_increases_with_subsequent_observations():
    s = _make_state()
    s.apply_quota_snapshot(
        "premium_interactions", {"used_requests": 100, "entitlement_requests": 1000}
    )
    s.apply_quota_snapshot(
        "premium_interactions", {"used_requests": 115, "entitlement_requests": 1000}
    )
    s.apply_quota_snapshot(
        "premium_interactions", {"used_requests": 130, "entitlement_requests": 1000}
    )
    assert s.quota_used_delta("premium_interactions") == 30


def test_quota_snapshot_delta_does_not_go_negative():
    """quota window reset 後に used_requests が減少しても delta は 0 以上を返す。"""
    s = _make_state()
    s.apply_quota_snapshot(
        "premium_interactions", {"used_requests": 100, "entitlement_requests": 1000}
    )
    # reset により減少
    s.apply_quota_snapshot(
        "premium_interactions", {"used_requests": 50, "entitlement_requests": 1000}
    )
    assert s.quota_used_delta("premium_interactions") == 0


def test_total_quota_used_delta_sums_all_quotas():
    s = _make_state()
    # quota_a: delta = 10
    s.apply_quota_snapshot("quota_a", {"used_requests": 100})
    s.apply_quota_snapshot("quota_a", {"used_requests": 110})
    # quota_b: delta = 5
    s.apply_quota_snapshot("quota_b", {"used_requests": 50})
    s.apply_quota_snapshot("quota_b", {"used_requests": 55})
    assert s.total_quota_used_delta == 15


def test_display_reqs_prefers_shutdown_total():
    """session.shutdown 経由の premium_requests_total が最優先。"""
    s = _make_state()
    s.premium_requests_total = 42
    s.apply_quota_snapshot("q1", {"used_requests": 100})
    s.apply_quota_snapshot("q1", {"used_requests": 110})
    # shutdown 値が優先される
    assert s.display_reqs == 42


def test_display_reqs_falls_back_to_quota_delta():
    """shutdown 値が無ければ quota delta 合計を表示。"""
    s = _make_state()
    s.apply_quota_snapshot("q1", {"used_requests": 100})
    s.apply_quota_snapshot("q1", {"used_requests": 107})
    assert s.display_reqs == 7


def test_display_reqs_zero_when_nothing_known():
    s = _make_state()
    assert s.display_reqs == 0


def test_quota_snapshot_ignores_empty_quota_id():
    s = _make_state()
    s.apply_quota_snapshot("", {"used_requests": 100})
    assert len(s.quota_snapshots_latest) == 0
    assert len(s.quota_snapshots_baseline) == 0


# ----------------------------------------------------------------------
# unavailable_reason (T5: Unlimited プラン対応)
# ----------------------------------------------------------------------


def test_apply_credit_sets_unavailable_reason_when_provided():
    """SDK が copilot_usage=None を返した場合、unavailable_reason が state に保存される。"""
    s = _make_state()
    assert s.sdk_credit_unavailable_reason == ""
    s.apply_assistant_credit(
        api_call_id="call-1",
        model="gpt-5.5",
        multiplier_cost=1.0,
        nano_aiu=None,
        unavailable_reason="SDK returned copilot_usage=None (Unlimited plan)",
    )
    assert "Unlimited" in s.sdk_credit_unavailable_reason


def test_apply_credit_preserves_first_unavailable_reason():
    """unavailable_reason は初回のみセットされ、後続呼び出しでは上書きしない。"""
    s = _make_state()
    s.apply_assistant_credit(
        api_call_id="call-1",
        unavailable_reason="first reason",
    )
    s.apply_assistant_credit(
        api_call_id="call-2",
        unavailable_reason="second reason",
    )
    assert s.sdk_credit_unavailable_reason == "first reason"


def test_apply_credit_unavailable_reason_with_nano_aiu_still_set():
    """nano_aiu と unavailable_reason が同時に渡された場合: reason は state に保存される。

    (API 契約: reason は『初回のみ』フィルタが効くだけで、nano_aiu 有無は無関係。
    実運用上は runner.py で `copilot_usage is None` のときのみ reason を送るため、
    両立しないが、関数 API としては独立処理する。)
    """
    s = _make_state()
    s.apply_assistant_credit(
        api_call_id="call-1",
        nano_aiu=1_000_000_000,
        unavailable_reason="should still be recorded as fact",
    )
    assert s.sdk_credit_unavailable_reason == "should still be recorded as fact"
    assert s.sdk_aiu_total_nano == 1_000_000_000


def test_apply_credit_no_reason_when_no_kwarg():
    """unavailable_reason 引数を渡さなければ既存挙動と完全互換。"""
    s = _make_state()
    s.apply_assistant_credit(
        api_call_id="call-1",
        nano_aiu=1_000_000_000,
    )
    assert s.sdk_credit_unavailable_reason == ""
    assert s.sdk_aiu_total_nano == 1_000_000_000


# ----------------------------------------------------------------------
# assistant_usage_count / display_reqs (T4: Unlimited プラン Reqs フォールバック)
# ----------------------------------------------------------------------


def test_display_reqs_zero_when_nothing_received():
    s = _make_state()
    assert s.display_reqs == 0


def test_display_reqs_uses_assistant_usage_count_when_no_quota_delta():
    """T4: Unlimited プランでは quota delta が常に 0 なので assistant_usage_count を返す。"""
    s = _make_state()
    s.assistant_usage_count = 7
    # premium_requests_total / quota delta はゼロ
    assert s.premium_requests_total == 0
    assert s.total_quota_used_delta == 0
    assert s.display_reqs == 7


def test_display_reqs_premium_total_takes_precedence_over_count():
    """premium_requests_total が来ていれば assistant_usage_count より優先。"""
    s = _make_state()
    s.premium_requests_total = 12
    s.assistant_usage_count = 7
    assert s.display_reqs == 12


def test_display_reqs_quota_delta_takes_precedence_over_count():
    """quota baseline 差分が出ていれば assistant_usage_count より優先。"""
    s = _make_state()
    s.apply_quota_snapshot("chat", {
        "used_requests": 100,
        "entitlement_requests": 1000,
        "remaining_percentage": 90.0,
        "overage": 0,
        "is_unlimited_entitlement": False,
        "overage_allowed_with_exhausted_quota": False,
        "usage_allowed_with_exhausted_quota": False,
        "reset_date_iso": None,
        "model": "gpt-5.5",
    })
    s.apply_quota_snapshot("chat", {
        "used_requests": 105,
        "entitlement_requests": 1000,
        "remaining_percentage": 89.5,
        "overage": 0,
        "is_unlimited_entitlement": False,
        "overage_allowed_with_exhausted_quota": False,
        "usage_allowed_with_exhausted_quota": False,
        "reset_date_iso": None,
        "model": "gpt-5.5",
    })
    s.assistant_usage_count = 7
    # delta = 105 - 100 = 5、これが count=7 より優先される
    assert s.display_reqs == 5
