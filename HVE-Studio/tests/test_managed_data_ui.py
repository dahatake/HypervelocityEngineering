"""FR-1090 AC-489 AC-490 AC-491 AC-492: real browser data lifecycle."""
import threading

import pytest

from test_managed_data import data_repo, data_server, original_files  # noqa: F401
import managed_data


@pytest.mark.parametrize("language,width", [("ja", 1280), ("en", 320)])
def test_visible_presence_progress_sync_and_immediate_cleanup(data_server, data_repo, shared_browser,
                                                              monkeypatch, language, width):
    state, url = data_server
    before = original_files(data_repo)
    entered, release = threading.Event(), threading.Event()
    sync = managed_data.sync

    def blocked_sync(root, progress):
        def report(event):
            progress(event)
            if event["phase"] == "files" and event["completed"] == 1:
                entered.set()
                if not release.wait(15):
                    raise managed_data.DataError("test progress wait expired")
        return sync(root, report)

    monkeypatch.setattr(managed_data, "sync", blocked_sync)
    context = shared_browser.new_context(viewport={"width": width, "height": 900}, reduced_motion="reduce")
    context.add_init_script(f"localStorage.setItem('eabk-studio.lang', '{language}')")
    page = context.new_page()
    try:
        page.goto(url + "/#/tables")
        page.locator("#splash").wait_for(state="hidden")
        host = page.locator("#generatedData")
        assert host.is_visible() and host.get_attribute("data-state") == "missing"
        assert page.get_by_test_id("data-delete").is_disabled()
        assert str(data_repo / managed_data.RELATIVE_PATH) == page.get_by_test_id("data-path").inner_text()
        page.get_by_test_id("data-sync").click()
        assert entered.wait(5)
        page.wait_for_function("document.querySelector('[data-testid=\"data-progress\"]').value === 1")
        progress = page.get_by_test_id("data-progress")
        assert progress.is_visible() and progress.get_attribute("max") == "3"
        assert page.get_by_test_id("data-sync").is_disabled()
        release.set()
        page.wait_for_function("document.querySelector('#generatedData').dataset.state === 'current'")
        assert (data_repo / managed_data.RELATIVE_PATH).exists()
        page.reload()
        page.locator("#splash").wait_for(state="hidden")
        assert host.get_attribute("data-state") == "current"
        page.goto(url + "/#/dashboard")
        assert host.is_visible() and host.get_attribute("data-state") == "current"
        assert host.evaluate("e => e.scrollWidth <= e.clientWidth")
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.get_by_test_id("data-delete").click()
        assert (data_repo / managed_data.RELATIVE_PATH).exists()
        page.once("dialog", lambda dialog: dialog.accept())
        page.get_by_test_id("data-delete").click()
        page.wait_for_function("document.querySelector('#generatedData').dataset.state === 'missing'")
        assert not (data_repo / managed_data.DIRECTORY).exists()
        assert original_files(data_repo) == before
        page.goto(url + "/#/tables")
        page.wait_for_function("document.querySelector('#view').textContent.includes('FR-ING-01')")
    finally:
        release.set()
        context.close()


def test_failed_operation_displays_reason_and_allows_retry(data_server, shared_browser, monkeypatch):
    _, url = data_server

    def fail(*args, **kwargs):
        raise OSError("test disk full")

    monkeypatch.setattr(managed_data, "sync", fail)
    page = shared_browser.new_page()
    try:
        page.goto(url)
        page.locator("#splash").wait_for(state="hidden")
        page.get_by_test_id("data-sync").click()
        page.get_by_test_id("data-error").wait_for(state="visible")
        assert "test disk full" in page.get_by_test_id("data-error").inner_text()
        assert page.get_by_test_id("data-sync").is_enabled()
        assert page.locator("#generatedData").get_attribute("data-state") == "missing"
    finally:
        page.close()
