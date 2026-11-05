import pytest
from playwright import sync_api


@pytest.fixture(scope="session")
def shared_browser(request):
    # sync_playwright() を 2 回開くと asyncio ループが衝突する。プロセスで 1 つの browser を全 UI テストが共有する。
    try:
        yield request.getfixturevalue("browser")
        return
    except pytest.FixtureLookupError:
        pass
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()
