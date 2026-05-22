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
    assert "Cost" in html
    assert "Reqs" in html
    # 料金表未注入 → -
    assert ">-<" in html


def test_footer_shows_cost_when_pricing_loaded(qapp):
    s = _make_state()
    s.set_pricing(_make_pricing(), usd_jpy_rate=150.0)
    s.apply_premium_requests(10)
    w = FooterWidget(s)
    html = w._label.text()
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
