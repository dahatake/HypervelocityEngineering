"""System test for FR-011 AC-430 (run 202610271340): header language toggle (JA/EN).

Expected values come only from AC-430 in docs/requirements-definition.md.  The implementation is NOT the oracle.

PROVISIONAL CONTRACT (仮置き。実装者が確認し、食い違えば CONFLICT として返す。この oracle は実装に合わせて直さない):
  - 言語トグル: <header class="top"> 内の #lang。#lang 自身かその子の button が、現在の言語を aria-pressed と語（JA／EN）で示す。
    EN を選ぶ操作は、テキストが "EN" の button（#lang 内、なければ #lang 自身）をクリック／Enter／Space する。
  - 画面: #/map2d ほか。管理データの値（ID・題名など）は検証から除く（ヘッダー帯・ナビ・属性・文書タイトルだけを見る）。
"""
import re

import pytest

from entity_repo import make_zoom
from test_semantic_zoom_system import _serve
from test_studio_system import studio_url  # noqa: F401  (fixture: 実リポジトリ)

JA = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
ROUTES = ["map2d", "entities"]

JS_CHROME = """() => {
  const out = [];
  const add = (v) => { if (v && v.trim()) out.push(v.trim()); };
  const hdr = document.querySelector('header.top');
  add(hdr.innerText);
  for (const e of document.querySelectorAll('header.top *, header.top')) {
    for (const a of ['title', 'aria-label', 'placeholder']) add(e.getAttribute(a));
  }
  for (const e of document.querySelectorAll('[placeholder]')) add(e.getAttribute('placeholder'));
  add(document.title);
  return {texts: out, lang: document.documentElement.lang};
}"""


@pytest.fixture()
def zurl(tmp_path):
    proc, url = _serve(make_zoom(tmp_path / "langtoggle"))
    yield url
    proc.terminate()


def _buttons(page):
    loc = page.locator("header.top #lang button")
    return loc if loc.count() else page.locator("header.top #lang")


def _pick(page, word):
    loc = _buttons(page)
    for i in range(loc.count()):
        if loc.nth(i).inner_text().strip().upper() == word:
            return loc.nth(i)
    raise AssertionError(f"言語トグルに語 {word} のボタンがない")


def _open(browser, url, route="map2d"):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    p = ctx.new_page()
    p.goto(url.split("#")[0] + "#/" + route)
    p.wait_for_load_state("networkidle")
    p.wait_for_selector("header.top #lang")
    return ctx, p


def _chrome(page):
    return page.evaluate(JS_CHROME)


# FR-011 AC-430: 現在の言語が状態と語で分かり、キーボードで操作でき、再読込なしで全文言が切り替わり、
# 他方の言語が残らず、選択は再読込後も保持される。異常系: 切替直後に別画面へ移っても他方の言語が混ざらない。
@pytest.mark.parametrize("route", ROUTES)
def test_ac430_language_toggle_switches_all_text_and_persists(browser, zurl, route):
    ctx, page = _open(browser, zurl, route)
    try:
        # 初期状態: JA と EN の両方の語があり、ちょうど 1 つが押下状態。
        ja, en = _pick(page, "JA"), _pick(page, "EN")
        states = [ja.get_attribute("aria-pressed"), en.get_attribute("aria-pressed")]
        assert sorted(states) == ["false", "true"], f"aria-pressed が現在の言語を示さない: {states}"

        # JA を確定させる（既に JA なら何もしない）。
        if ja.get_attribute("aria-pressed") != "true":
            ja.focus()
            page.keyboard.press("Enter")
        assert _pick(page, "JA").get_attribute("aria-pressed") == "true"
        before = _chrome(page)
        assert before["lang"].lower().startswith("ja")
        assert any(JA.search(t) for t in before["texts"]), "JA なのに日本語の文言がない"

        # キーボードだけで EN に切り替える（再読込なし: ナビゲーション発生を監視する）。
        loads = []
        page.on("load", lambda *_: loads.append(1))
        _pick(page, "EN").focus()
        page.keyboard.press("Enter")
        page.wait_for_function("document.documentElement.lang.toLowerCase().startsWith('en')")
        assert not loads, "切替で再読込が起きた"
        assert _pick(page, "EN").get_attribute("aria-pressed") == "true"
        assert _pick(page, "JA").get_attribute("aria-pressed") == "false"
        after = _chrome(page)
        leftovers = [t for t in after["texts"] if JA.search(t)]
        assert not leftovers, f"EN なのに日本語が残る: {leftovers[:5]}"

        # 異常系: 別の画面へ移っても（動的生成の文言）他方の言語が混ざらない。
        other = [r for r in ROUTES if r != route][0]
        page.evaluate(f"location.hash = '#/{other}'")
        page.wait_for_load_state("networkidle")
        mixed = [t for t in _chrome(page)["texts"] if JA.search(t)]
        assert not mixed, f"画面遷移後に日本語が混ざる: {mixed[:5]}"

        # 再読込後も EN が保持される。
        page.reload()
        page.wait_for_selector("header.top #lang")
        assert _pick(page, "EN").get_attribute("aria-pressed") == "true"
        kept = _chrome(page)
        assert kept["lang"].lower().startswith("en")
        assert not [t for t in kept["texts"] if JA.search(t)]

        # JA に戻すと日本語に戻る（双方向）。
        _pick(page, "JA").click()
        page.wait_for_function("document.documentElement.lang.toLowerCase().startsWith('ja')")
        back = _chrome(page)
        assert any(JA.search(t) for t in back["texts"])
    finally:
        ctx.close()
