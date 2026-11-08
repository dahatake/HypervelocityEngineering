"""FR-1080 AC-441 / AC-443: Graph の force 風の動き（層レイアウトの座標をアンカーとして収束する）と、上限以下でも使える種類フィルタ。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_links_wrap_status_ui import studio, _open, sync_api  # noqa: E402,F401

GRAPH = '[data-testid="graph-view"]'
NODE = '[data-testid="graph-node"]'


def _settled(page):
    page.wait_for_function("() => document.querySelector('[data-testid=graph-view]')?.dataset.vizTransition === 'settled'", timeout=8000)


# FR-1080 AC-443: 動力学は有効（data-layout=force）でも、収まった後の最終配置は層レイアウト（左から右）のまま、ずれ（translate）が残らない。
def test_ac443_force_dynamics_end_exactly_on_the_layered_layout(studio):
    page = _open(studio, "map2d?dim=graph")
    page.wait_for_selector(GRAPH)
    assert page.locator(GRAPH).get_attribute("data-layout") == "force"
    assert page.locator(GRAPH).get_attribute("data-layout-final") == "layered"
    _settled(page)
    assert float(page.locator(GRAPH).get_attribute("data-viz-alpha")) == 0
    assert page.locator(NODE).evaluate_all("els => els.every(e => !e.style.translate)")
    page.context.close()


# FR-1080 AC-441: 上限以下の Graph でも種類のチップで絞れ、「すべて」で元に戻る。件数が data-viz-count と一致する。
def test_ac441_small_graph_type_filter_and_restore(studio):
    page = _open(studio, "map2d?dim=graph")
    page.wait_for_selector(GRAPH)
    _settled(page)
    n0 = page.locator(NODE).count()
    page.locator('[data-testid="graph-filter"] [data-filter-type]').first.click()
    _settled(page)
    n1 = page.locator(NODE).count()
    assert 0 < n1 < n0 and int(page.locator(GRAPH).get_attribute("data-viz-count")) == n1
    page.locator('[data-filter-type-all]').click()
    _settled(page)
    assert page.locator(NODE).count() == n0
    page.context.close()
