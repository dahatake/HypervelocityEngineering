"""FR-1089 AC-485 AC-486 AC-487: startup progress and recovery."""
import pytest

from test_links_wrap_status_ui import studio  # noqa: F401


@pytest.mark.parametrize("language,width", [("ja", 1280), ("en", 320)])
def test_startup_tracks_real_model_and_view_loading(studio, language, width):
    browser, url = studio
    context = browser.new_context(viewport={"width": width, "height": 700}, reduced_motion="reduce")
    context.add_init_script(f"localStorage.setItem('eabk-studio.lang', '{language}')")
    context.add_init_script("""
      const originalFetch = window.fetch;
      window.pendingStartup = {};
      window.fetch = async (...args) => {
        const path = String(args[0]);
        if (path === '/api/model' || path === '/api/fingerprint') {
          await new Promise(resolve => { window.pendingStartup[path] = resolve; });
        }
        return originalFetch(...args);
      };
    """)
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_function("Boolean(window.pendingStartup && window.pendingStartup['/api/model'])")
    splash = page.locator("#splash")
    assert splash.is_visible()
    assert page.locator("#splashReload").is_hidden()
    assert page.locator("#splashBar").get_attribute("value") == "1"
    assert page.locator("#splashStatus").inner_text() == (
        "ソースと管理データを解析中…" if language == "ja" else "Analyzing source and project data…"
    )
    assert page.locator("header.top").get_attribute("inert") is not None
    assert page.evaluate("document.querySelector('#splash').scrollWidth <= document.querySelector('#splash').clientWidth")
    page.evaluate("window.pendingStartup['/api/model']()")
    page.wait_for_function("Boolean(window.pendingStartup['/api/fingerprint'])")
    assert page.locator("#splashBar").get_attribute("value") == "1"
    assert page.locator("#splashStatus").inner_text() == (
        "データと関連を準備中…" if language == "ja" else "Preparing data and relationships…"
    )
    page.evaluate("window.pendingStartup['/api/fingerprint']()")
    splash.wait_for(state="hidden")
    assert page.locator("#splashBar").get_attribute("value") == "3"
    assert page.locator("header.top").get_attribute("inert") is None
    assert page.locator("#view").inner_text()
    context.close()


def test_failed_model_load_offers_existing_retry(studio):
    browser, url = studio
    context = browser.new_context()
    page = context.new_page()
    calls = []

    def fail_once(route):
        calls.append(1)
        if len(calls) == 1:
            route.fulfill(status=503, content_type="application/json", body='{"detail":"startup failure"}')
        else:
            route.continue_()

    page.route("**/api/model", fail_once)
    page.goto(url)
    panel = page.locator('[data-testid="state-panel"][data-state="error"]')
    panel.wait_for(state="visible")
    assert "startup failure" in panel.inner_text()
    assert page.locator("#splash").is_hidden()
    panel.locator("button").click()
    page.wait_for_function("document.querySelector('#view [data-testid=\"state-panel\"][data-state=\"error\"]') === null")
    assert len(calls) >= 2
    context.close()


def test_module_load_failure_keeps_splash_with_reload(studio):
    browser, url = studio
    context = browser.new_context(locale="en-US")
    page = context.new_page()
    page.route("**/js/app.js", lambda route: route.abort())
    page.goto(url)
    page.locator("#splashReload").wait_for(state="visible")
    assert "could not be loaded" in page.locator("#splashStatus").inner_text()
    assert page.locator("#splash").is_visible()
    context.close()
