"""Integration test for FR-1093 (the "New here?" wizard on every screen)."""
import pytest

from test_links_wrap_status_ui import studio, _open, sync_api  # noqa: F401

SCREENS = ["dashboard", "implstatus", "map2d", "diagrams", "entities", "integrations", "source", "tables", "maintenance"]


# FR-1093 AC-513: every screen opens a card wizard that dims the rest, steps with Next, and closes with Esc.
@pytest.mark.parametrize("screen", SCREENS)
def test_ac513_guide_wizard_on_every_screen(studio, screen):
    page = _open(studio, screen)
    page.locator('[data-testid="guide-open"]').click()
    card = page.locator('[data-testid="guide-card"]')
    card.wait_for()
    assert page.locator(".guide-spot").count() == 1
    assert "1 /" in card.inner_text().replace("\n", " ")
    page.locator('[data-testid="guide-next"]').click()
    assert "2 /" in card.inner_text().replace("\n", " ")
    page.keyboard.press("Escape")
    assert page.locator('[data-testid="guide"]').count() == 0
    page.context.close()
