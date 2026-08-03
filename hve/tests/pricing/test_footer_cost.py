"""Wave 4 GUI: FooterWidget の Cost / Reqs 表示および 1Hz QTimer のテスト。"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.workbench_state import WorkbenchState  # noqa: E402
from hve.gui.workbench_widgets import FooterWidget  # noqa: E402
from hve.pricing.models import CopilotPricing, ModelPricing, PlanPricing  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _make_state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf", run_id="r1", model="claude-sonnet-4")


def _make_pricing() -> CopilotPricing:
    return CopilotPricing(
        models={"claude-sonnet-4": ModelPricing(model_id="claude-sonnet-4", multiplier=1.0)},
        plans={
            "copilot_pro": PlanPricing(
                plan_id="copilot_pro", monthly_usd=10.0, additional_request_usd=0.04
            )
        },
        status="ok",
    )


def test_footer_shows_cost_and_reqs_dash_when_unavailable(qapp):
    s = _make_state()
    w = FooterWidget(s)
    html = w._label.text()
    # Phase A: Footer ラベル "Cost" は "AI Credit" に変更された (USD と区別するため)
    assert "AI Credit" in html
    assert "Reqs" in html
    # 料金表未注入 & SDK 値未取得 → -
    assert ">-<" in html


def test_footer_shows_cost_when_pricing_loaded(qapp):
    s = _make_state()
    s.set_pricing(_make_pricing(), usd_jpy_rate=150.0)
    s.apply_premium_requests(10)
    w = FooterWidget(s)
    html = w._label.text()
    # SDK 直接値が無くても pricing 経由の USD/JPY にフォールバックする
    assert "$" in html
    assert "¥" in html  # ja デフォルト → both
    assert "Reqs" in html
    assert "10" in html


def test_footer_currency_usd_only(qapp):
    s = _make_state()
    s.set_pricing(_make_pricing(), usd_jpy_rate=150.0)
    s.apply_premium_requests(10)
    w = FooterWidget(s)
    w.set_display_currency("usd")
    html = w._label.text()
    assert "$" in html
    # USD のみモードでは "¥" は出ない (Cost の括弧表記もない)
    assert "¥" not in html


def test_footer_qtimer_attribute_exists(qapp):
    s = _make_state()
    w = FooterWidget(s)
    # 1Hz タイマが設定されている
    assert getattr(w, "_tick", None) is not None
    assert w._tick.interval() == 1000


def test_footer_shows_sdk_aiu_when_present(qapp):
    """Phase A: SDK 直接値 (Nano AIU) があれば優先表示される。"""
    s = _make_state()
    # 1.5 AIU = 1_500_000_000 Nano AIU
    s.apply_assistant_credit(
        api_call_id="call-1",
        model="claude-sonnet-4",
        nano_aiu=1_500_000_000,
    )
    w = FooterWidget(s)
    html = w._label.text()
    assert "AIU" in html  # AI Credit ラベルで AIU 表記


def test_footer_shows_reqs_from_quota_delta(qapp):
    """Phase A: quota_snapshots の baseline 差分が Reqs として表示される。"""
    s = _make_state()
    # 初回観測 (baseline 設定)
    s.apply_quota_snapshot(
        "premium_interactions",
        {"used_requests": 100, "entitlement_requests": 1000, "remaining_percentage": 90.0, "overage": 0},
    )
    # 後続観測 (delta = 7)
    s.apply_quota_snapshot(
        "premium_interactions",
        {"used_requests": 107, "entitlement_requests": 1000, "remaining_percentage": 89.3, "overage": 0},
    )
    w = FooterWidget(s)
    html = w._label.text()
    assert "Reqs" in html
    assert ">7<" in html  # delta = 7


def test_footer_shows_na_when_sdk_credit_unavailable(qapp):
    """T5: SDK が copilot_usage=None (Unlimited 等) を返し、mc 累計もゼロのとき、
    AI Credit は『-』ではなく『N/A (AIU unavailable)』表示される (未取得と未提供を区別)。"""
    s = _make_state()
    # SDK 側で copilot_usage=None と判明した状態を再現 (multiplier_cost も None)
    s.apply_assistant_credit(
        api_call_id="call-unlimited-1",
        model="gpt-5.5",
        multiplier_cost=None,
        nano_aiu=None,
        unavailable_reason="SDK returned copilot_usage=None (Unlimited plan)",
    )
    w = FooterWidget(s)
    html = w._label.text()
    assert "AI Credit" in html
    assert "N/A (AIU unavailable)" in html
    # ハイフン単独表示ではないこと
    assert ">N/A" in html or "N/A " in html


def test_footer_shows_mc_total_when_aiu_unavailable_but_cost_present(qapp):
    """T6: total_nano_aiu 取得不能でも multiplier_cost 累計 > 0 のときは
    『mc: X.X』を表示する (Unlimited プラン向け案 A フォールバック、捏造禁止)。"""
    s = _make_state()
    # Unlimited プラン: nano_aiu=None だが cost=1.0 が来る
    for i in range(7):
        s.apply_assistant_credit(
            api_call_id=f"call-{i}",
            model="gpt-5.5",
            multiplier_cost=1.0,
            nano_aiu=None,
            unavailable_reason="SDK returned copilot_usage=None (Unlimited plan)",
        )
    assert s.sdk_multiplier_cost_total == 7.0
    w = FooterWidget(s)
    html = w._label.text()
    assert "AI Credit" in html
    # mc: 7.0 が表示され、N/A 表記は出ない (mc 優先)
    assert "mc: 7.0" in html
    assert "N/A" not in html


def test_footer_prefers_aiu_over_mc_when_both_present(qapp):
    """T6: total_nano_aiu と multiplier_cost が両方取れているときは AIU 優先 (Q3 default)。"""
    s = _make_state()
    s.apply_assistant_credit(
        api_call_id="call-1",
        model="claude-sonnet-4",
        multiplier_cost=3.0,
        nano_aiu=1_500_000_000,  # 1.5 AIU
    )
    w = FooterWidget(s)
    html = w._label.text()
    assert "AIU" in html  # AIU 表記が出る
    assert "mc:" not in html  # mc 表記は出ない
