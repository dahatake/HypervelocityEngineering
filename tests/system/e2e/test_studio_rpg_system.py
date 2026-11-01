"""System tests for the retired RPG display mode (FR-1066 AC-286/AC-295).

Expected behavior comes only from the acceptance criteria. The implementation is
not the oracle; these tests characterize the remaining display-mode controls and
the absence of RPG-only controls and behavior.
"""
import pytest

from entity_repo import make_zoom
from test_studio_links_wrap_status_arch_system import _serve

HDR = '[data-testid="header-dim-toggle"]'
RPG_ONLY = (
    '[data-testid="rpg-view"]',
    '[data-testid="rpg-dialog"]',
    '[data-testid="rpg-menu"]',
)


@pytest.fixture()
def mode_url(tmp_path):
    proc, url = _serve(make_zoom(tmp_path / "map-modes"))
    yield url
    proc.terminate()


def _open_map(browser, url):
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()
    page.add_init_script(
        """() => {
          window.__systemAudioStarts = 0;
          for (const name of ["AudioBufferSourceNode", "OscillatorNode"]) {
            const start = window[name]?.prototype?.start;
            if (start) window[name].prototype.start = function (...args) {
              window.__systemAudioStarts++;
              return start.apply(this, args);
            };
          }
          const play = HTMLMediaElement.prototype.play;
          HTMLMediaElement.prototype.play = function (...args) {
            window.__systemAudioStarts++;
            return play.apply(this, args);
          };
        }"""
    )
    page.goto(f"{url}/#/map2d")
    page.wait_for_selector(HDR)
    return page


def _assert_rpg_absent(page):
    assert page.locator('[data-dim="rpg"]').count() == 0
    for selector in RPG_ONLY:
        assert page.locator(selector).count() == 0, f"RPG 専用 UI が残っている: {selector}"
    header = page.locator(HDR)
    assert header.get_attribute("data-current") != "rpg"
    assert header.get_attribute("data-selected") != "rpg"


# FR-1066 AC-286: RPG を選択できず、旧画面の再読込でも復元されない
def test_ac286_rpg_cannot_be_selected_and_legacy_reload_uses_2d(browser, mode_url):
    page = _open_map(browser, mode_url)
    assert page.locator(HDR).get_attribute("data-current") == "2d"
    _assert_rpg_absent(page)

    # 旧版で使われていたマップ URL を再読込し、RPG 表示が復元されないことを確認する。
    page.goto(f"{mode_url}/#/maprpg")
    page.reload()
    page.wait_for_selector(HDR)
    assert page.locator(HDR).get_attribute("data-current") == "2d"
    _assert_rpg_absent(page)

    # コマンド検索からも RPG を選べない。
    page.keyboard.press("Control+k")
    search = page.get_by_test_id("command-search")
    search.fill("RPG")
    search.press("Enter")
    page.wait_for_timeout(100)
    _assert_rpg_absent(page)
    page.context.close()


# FR-1066 AC-295: RPG 専用キーは起動せず、検索・フォーカス・残るモード操作は使える
def test_ac295_rpg_keys_do_not_start_rpg_and_keep_search_focus_and_mode_keyboard(browser, mode_url):
    page = _open_map(browser, mode_url)
    _assert_rpg_absent(page)

    # RPG 専用操作をマップ上で行っても、移動・会話・メニュー・音の切替は起動しない。
    for key in ("ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
                "w", "a", "s", "d", "Enter", "z", "Escape", "x", "Space", "Shift"):
        page.evaluate("() => document.activeElement?.blur()")
        page.keyboard.press(key)
        _assert_rpg_absent(page)
    assert page.evaluate("() => window.__systemAudioStarts") == 0, "RPG 専用の音楽・効果音が起動した"

    # 検索入力・検索結果とキーボードによるフォーカス移動を維持する。
    search = page.get_by_test_id("command-search")
    search.fill("注文")
    assert search.input_value() == "注文"
    assert "注文" in page.locator("#results").inner_text()
    search.focus()
    page.keyboard.press("Tab")
    assert not page.evaluate(
        "() => document.activeElement === document.querySelector('[data-testid=\"command-search\"]')"
    )
    page.keyboard.press("Shift+Tab")
    assert page.evaluate(
        "() => document.activeElement === document.querySelector('[data-testid=\"command-search\"]')"
    )

    # 残る表示モードのキーボード切替は動作する。
    for dim in ("3d", "2d"):
        page.locator(f'{HDR} [data-dim="{dim}"]').focus()
        page.keyboard.press("Enter")
        page.wait_for_function(
            "(dim) => document.querySelector('[data-testid=\"header-dim-toggle\"]').dataset.selected === dim",
            arg=dim,
        )
        _assert_rpg_absent(page)
    page.context.close()
