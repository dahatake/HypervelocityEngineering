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
    cost = _find_section(sections, "Cost (AI Credit)")
    elapsed = _find_section(sections, "Elapsed")
    assert cost is not None
    assert elapsed is not None
    # 未注入 → 累積コストは "-"
    cost_dict = {it.label: it.value for it in cost.items}
    assert cost_dict["累積コスト"] == "-"
    assert cost_dict["Premium Requests 累積"] == "0"


def test_snapshot_cost_with_pricing(qapp):
    s = _make_state()
    s.set_pricing(_make_pricing(), usd_jpy_rate=150.0)
    s.apply_premium_requests(10)
    sections, _ = build_snapshot(s)
    cost = _find_section(sections, "Cost (AI Credit)")
    assert cost is not None
    cost_dict = {it.label: it.value for it in cost.items}
    assert "$" in cost_dict["累積コスト"]
    assert "¥" in cost_dict["累積コスト"]
    assert cost_dict["Premium Requests 累積"] == "10"
    assert cost_dict["計算方式"] == "multiplier"
    assert cost_dict["料金表 ステータス"] == "ok"


def test_snapshot_cost_unavailable_reason_present(qapp):
    s = _make_state()
    # 不明モデルで apply → reason="model_not_found" 等
    s.set_pricing(_make_pricing(), usd_jpy_rate=150.0)
    s.apply_premium_requests(5, model="unknown-model-xyz")
    sections, _ = build_snapshot(s)
    cost = _find_section(sections, "Cost (AI Credit)")
    cost_dict = {it.label: it.value for it in cost.items}
    # 累積コストは "-" のまま、Reqs は加算済み
    assert cost_dict["累積コスト"] == "-"
    assert cost_dict["Premium Requests 累積"] == "5"
    assert "未計算理由" in cost_dict
