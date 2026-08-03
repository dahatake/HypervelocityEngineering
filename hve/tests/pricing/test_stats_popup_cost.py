"""Wave 4 GUI: stats_detail_popup の Cost / Elapsed セクションのテスト。"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.stats_detail_popup import build_snapshot  # noqa: E402
from hve.gui.workbench_state import WorkbenchState  # noqa: E402
from hve.pricing.models import CopilotPricing, ModelPricing, PlanPricing  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _make_state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf", run_id="r1", model="claude-sonnet-4")


def _make_pricing() -> CopilotPricing:
    return CopilotPricing(
        models={"claude-sonnet-4": ModelPricing(model_id="claude-sonnet-4", multiplier=1.0)},
        plans={"copilot_pro": PlanPricing(plan_id="copilot_pro", monthly_usd=10.0, additional_request_usd=0.04)},
        status="ok",
    )


def _find_section(sections, title):
    return next((s for s in sections if s.title == title), None)


def test_snapshot_contains_cost_and_elapsed_sections(qapp):
    s = _make_state()
    sections, _ = build_snapshot(s)
    # Phase A: セクション名を "Cost (AI Credit)" → "Cost (pricing 計算)" に変更
    cost = _find_section(sections, "Cost (pricing 計算)")
    elapsed = _find_section(sections, "Elapsed")
    sdk_credit = _find_section(sections, "AI Credit (SDK 直接)")
    quota = _find_section(sections, "Quota Snapshot")
    assert cost is not None
    assert elapsed is not None
    assert sdk_credit is not None
    assert quota is not None
    # 未注入 → 累積コストは "-"
    cost_dict = {it.label: it.value for it in cost.items}
    assert cost_dict["累積コスト (pricing 計算)"] == "-"
    assert cost_dict["Premium Requests (shutdown)"] == "0"
    # Phase A: SDK 直接値も未取得 → "-"
    sdk_dict = {it.label: it.value for it in sdk_credit.items}
    assert sdk_dict["累積 AI Credit (AIU)"] == "-"


def test_snapshot_cost_with_pricing(qapp):
    s = _make_state()
    s.set_pricing(_make_pricing(), usd_jpy_rate=150.0)
    s.apply_premium_requests(10)
    sections, _ = build_snapshot(s)
    cost = _find_section(sections, "Cost (pricing 計算)")
    assert cost is not None
    cost_dict = {it.label: it.value for it in cost.items}
    assert "$" in cost_dict["累積コスト (pricing 計算)"]
    assert "¥" in cost_dict["累積コスト (pricing 計算)"]
    assert cost_dict["Premium Requests (shutdown)"] == "10"
    assert cost_dict["計算方式"] == "multiplier"
    assert cost_dict["料金表 ステータス"] == "ok"


def test_snapshot_cost_unavailable_reason_present(qapp):
    s = _make_state()
    # 不明モデルで apply → reason="model_not_found" 等
    s.set_pricing(_make_pricing(), usd_jpy_rate=150.0)
    s.apply_premium_requests(5, model="unknown-model-xyz")
    sections, _ = build_snapshot(s)
    cost = _find_section(sections, "Cost (pricing 計算)")
    cost_dict = {it.label: it.value for it in cost.items}
    # 累積コストは "-" のまま、Reqs は加算済み
    assert cost_dict["累積コスト (pricing 計算)"] == "-"
    assert cost_dict["Premium Requests (shutdown)"] == "5"
    assert "未計算理由" in cost_dict


def test_snapshot_sdk_aiu_present(qapp):
    """Phase A: SDK 直接値の AIU セクションが表示される。"""
    s = _make_state()
    s.apply_assistant_credit(
        api_call_id="call-1",
        model="claude-sonnet-4",
        nano_aiu=2_500_000_000,  # 2.5 AIU
        multiplier_cost=0.5,
    )
    sections, _ = build_snapshot(s)
    sdk = _find_section(sections, "AI Credit (SDK 直接)")
    assert sdk is not None
    d = {it.label: it.value for it in sdk.items}
    assert "AIU" in d["累積 AI Credit (AIU)"]
    assert "2.500000" in d["累積 AI Credit (AIU)"]
    assert d["累積 Nano AIU"] == "2,500,000,000"
    assert d["API call 件数 (dedup 後)"] == "1"


def test_snapshot_quota_section_with_delta(qapp):
    """Phase A: Quota Snapshot セクションが baseline 差分付きで表示される。"""
    s = _make_state()
    s.apply_quota_snapshot(
        "premium_interactions",
        {"used_requests": 100, "entitlement_requests": 1000, "remaining_percentage": 90.0, "overage": 0, "is_unlimited_entitlement": False},
    )
    s.apply_quota_snapshot(
        "premium_interactions",
        {"used_requests": 115, "entitlement_requests": 1000, "remaining_percentage": 88.5, "overage": 0, "is_unlimited_entitlement": False},
    )
    sections, _ = build_snapshot(s)
    quota = _find_section(sections, "Quota Snapshot")
    assert quota is not None
    d = {it.label: it.value for it in quota.items}
    # quota_id:premium_interactions の行に delta=15 が含まれる
    assert "Δ=15" in d["quota:premium_interactions"]
    assert d["全 quota Δ 合計 (= Reqs)"] == "15"
