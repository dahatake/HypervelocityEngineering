"""Integration tests (browser) for FR-1094 AC-515 AC-516, FR-1095 AC-519, FR-1096 AC-520..AC-522, FR-1097 AC-523 AC-524,
FR-1098 AC-525..AC-527, NFR-UX-019 AC-531..AC-533 and FR-1099 AC-537.

The AI endpoints of the local server are answered by page.route here (the provider calls themselves are covered by
test_ai.py against a fake Azure OpenAI), so these tests check what the screen does with the answers.
"""
import json
import re

import pytest

from test_links_wrap_status_ui import ROOT, REPO, studio, _open, sync_api  # noqa: F401

STEP_ROUTES = {1: "#/dashboard", 2: "#/tables?tab=reqs", 3: "#/map", 4: "#/implstatus", 5: "#/release", 6: "#/maintenance"}


def _step(page, n):
    page.locator(f'[data-testid="step"][data-step="{n}"]').click()
    page.wait_for_selector(f'[data-testid="step"][data-step="{n}"][aria-current="step"]')


def _name(page, n):
    return page.locator(f'[data-step="{n}"] .step-name').evaluate("e => e.lastChild.textContent")


def _current(page):
    return int(page.locator('[data-testid="step"][aria-current="step"]').get_attribute("data-step"))


# FR-1094 AC-515: a screen opened directly keeps the step it belongs to, else the step whose default it is;
# selection and search survive; names exist in JA and EN
def test_ac515_direct_links_choose_the_step_and_keep_state(studio):
    page = _open(studio, "dashboard")
    _step(page, 4)
    page.evaluate("() => { location.hash = '#/tables?tab=cases'; }")    # tables belongs to step 4 -> stays
    page.wait_for_selector('#nav a[data-nav="tables"].on')
    assert _current(page) == 4
    page.evaluate("() => { location.hash = '#/diagrams'; }")            # not in step 4 -> its only step (3)
    page.wait_for_selector('#nav a[data-nav="diagrams"].on')
    assert _current(page) == 3
    page.evaluate("() => { location.hash = '#/implstatus'; }")          # default screen of step 4
    page.wait_for_selector('#nav a[data-nav="implstatus"].on')
    assert _current(page) == 4
    page.locator("#q").fill("FR-001")
    page.goto(page.url.split("#")[0] + "#/map2d?select=FR-001")
    page.wait_for_selector("#drawer:not([hidden])")
    _step(page, 1)
    _step(page, 3)
    assert page.locator("#q").input_value() == "FR-001"
    assert "FR-001" in page.locator("#drawer").inner_text()
    ja = [page.locator(f'[data-step="{n}"] .step-name').inner_text() for n in range(1, 7)]
    page.locator('#lang [data-lang="en"]').click()
    en = [page.locator(f'[data-step="{n}"] .step-name').inner_text() for n in range(1, 7)]
    assert all(ja) and all(en) and ja != en and not any(re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", x) for x in en)
    page.context.close()


# FR-1094 AC-516: every step shows what to decide, what the screen shows and the next step; no role-by-role text
@pytest.mark.parametrize("lang", [None, "en"])
def test_ac516_each_step_says_what_to_decide_and_the_next_step(studio, lang):
    page = _open(studio, "dashboard", lang=lang)
    judges = []
    for n in range(1, 7):
        _step(page, n)
        judge = page.get_by_test_id("step-judge").inner_text()
        assert judge and page.locator("#navDesc").inner_text().strip()
        nxt = page.get_by_test_id("step-next").inner_text()
        if n < 6:
            assert _name(page, n + 1) in nxt
        else:
            assert re.search(r"最初|first", nxt)
        judges.append(judge)
        assert page.locator(".analysis, #personaBar").count() == 0
        assert not re.search(r"Software Engineer|Architect", page.locator("body").inner_text())
    assert len(set(judges)) == 6
    page.context.close()


# FR-1095 AC-519: the release state is visible next to step 5 on every step; items are links; empty -> stated
def test_ac519_release_badge_everywhere_and_items(studio):
    page = _open(studio, "dashboard")
    for n in range(1, 7):
        _step(page, n)
        badge = page.locator('[data-step="5"] [data-testid="release-badge"]')
        assert badge.count() == 1 and badge.get_attribute("data-state") in ("action", "ok", "unknown")
        assert badge.locator("svg").count() == 1   # an icon besides the word and the colour
    _step(page, 5)
    rel = page.evaluate("async () => (await (await fetch('/api/model')).json()).release")
    shown = page.locator('[data-testid="release-items"] li').evaluate_all("els => els.map(e => [e.dataset.kind, e.dataset.id])")
    assert shown == [[i["kind"], i["id"]] for i in rel["items"]]
    if not rel["items"]:
        assert page.get_by_test_id("release-items-empty").is_visible()
    else:
        assert page.locator('[data-testid="release-items"] li a.xref').count() >= 1
    assert page.get_by_test_id("release-state").get_attribute("data-state") == rel["state"]
    page.context.close()


FIELDS = {
    ("azure", "key"): {"endpoint", "deployment", "key"},
    ("azure", "entra"): {"signin"},
    ("copilot", "gh"): {"signin", "model"},
    ("copilot", "byok"): {"byokType", "endpoint", "key", "model"},
}


def _settings(page):
    page.get_by_test_id("ai-settings-btn").click()
    page.wait_for_selector('[data-testid="ai-settings"]')


def _mock_signin(page):
    page.route("**/api/ai/signin", lambda r: r.fulfill(status=200, content_type="application/json",
                                                       body=json.dumps({"provider": "x", "account": "pm@example.com", "tokenSource": "gh"})))


# FR-1096 AC-520 AC-521: only the fields of the chosen combination; a typed key is discarded on switching and never shown
def test_ac520_ac521_minimal_fields_and_key_is_discarded(studio):
    page = _open(studio, "dashboard")
    _mock_signin(page)
    page.route("**/api/ai/resources", lambda r: r.fulfill(status=200, content_type="application/json", body='{"items": []}'))
    posted = []
    page.on("request", lambda r: posted.append(r.post_data or "") if "/api/" in r.url and r.method == "POST" else None)
    _settings(page)
    assert page.locator('[data-testid="ai-settings"] [data-field]').count() == 0     # "do not use AI"
    for (provider, auth), want in FIELDS.items():
        page.get_by_test_id(f"ai-provider-{provider}").check()
        page.get_by_test_id(f"ai-auth-{auth}").check()
        page.wait_for_timeout(150)
        got = set(page.locator('[data-testid="ai-settings"] [data-field]').evaluate_all("els => els.map(e => e.dataset.field)"))
        assert got == want, (provider, auth, got)
        if "key" in want:
            box = page.get_by_test_id("ai-field-key")
            assert box.get_attribute("type") == "password"
            box.fill("typed-but-not-saved-123")
    page.get_by_test_id("ai-provider-azure").check()
    page.get_by_test_id("ai-auth-key").check()
    assert page.get_by_test_id("ai-field-key").input_value() == ""
    assert not any("typed-but-not-saved-123" in p for p in posted)
    page.context.close()


# FR-1096 AC-522: non-secret settings are kept per browser and restored; the key is never in the browser's storage
def test_ac522_settings_survive_reload_without_the_key(studio):
    page = _open(studio, "dashboard")
    _settings(page)
    page.get_by_test_id("ai-provider-azure").check()
    page.get_by_test_id("ai-field-endpoint").fill("https://contoso.openai.azure.com")
    page.get_by_test_id("ai-field-endpoint").press("Tab")
    page.get_by_test_id("ai-field-deployment").fill("gpt-dep")
    page.get_by_test_id("ai-field-deployment").press("Tab")
    page.get_by_test_id("ai-field-key").fill("never-stored-in-browser")
    page.reload()
    page.wait_for_load_state("networkidle")
    saved = page.evaluate("() => localStorage.getItem('eabk-studio.ai')")
    assert json.loads(saved) == {"provider": "azure", "auth": "key", "endpoint": "https://contoso.openai.azure.com", "deployment": "gpt-dep"}
    assert "never-stored-in-browser" not in json.dumps(page.evaluate("() => ({...localStorage})"))
    _settings(page)
    assert page.get_by_test_id("ai-field-endpoint").input_value() == "https://contoso.openai.azure.com"
    page.context.close()


# FR-1097 AC-523 AC-524: subscription -> resource -> deployment from the lists; no typing; no password field; 0 items stated
def test_ac523_ac524_entra_lists(studio):
    page = _open(studio, "dashboard")
    _mock_signin(page)
    lists = {
        "subscriptions": [{"id": "00000000-0000-0000-0000-000000000001", "name": "Prod"}],
        "accounts": [{"id": "/subscriptions/0/providers/Microsoft.CognitiveServices/accounts/aoai", "name": "aoai", "location": "japaneast",
                      "endpoint": "https://aoai.openai.azure.com/"}],
        "deployments": [],
    }
    page.route("**/api/ai/resources", lambda r: r.fulfill(status=200, content_type="application/json",
                                                          body=json.dumps({"items": lists[json.loads(r.request.post_data)["level"]]})))
    _settings(page)
    page.get_by_test_id("ai-provider-azure").check()
    page.get_by_test_id("ai-auth-entra").check()
    page.wait_for_selector('[data-testid="ai-list-subscriptions"]')
    assert "pm@example.com" in page.get_by_test_id("ai-signin").inner_text()
    page.get_by_test_id("ai-list-subscriptions").select_option("00000000-0000-0000-0000-000000000001")
    page.wait_for_selector('[data-testid="ai-list-accounts"]')
    assert "aoai · japaneast" in page.get_by_test_id("ai-list-accounts").inner_text()
    page.get_by_test_id("ai-list-accounts").select_option(lists["accounts"][0]["id"])
    page.wait_for_selector('[data-testid="ai-list-empty"]')
    assert page.locator('[data-testid="ai-settings"] input[type=password], [data-testid="ai-field-endpoint"]').count() == 0
    cfg = json.loads(page.evaluate("() => localStorage.getItem('eabk-studio.ai')"))
    assert cfg["endpoint"] == "https://aoai.openai.azure.com/" and cfg["account"] == lists["accounts"][0]["id"]
    page.context.close()


def _configure(page):
    page.evaluate("() => localStorage.setItem('eabk-studio.ai', JSON.stringify({provider:'azure',auth:'key',endpoint:'https://x.openai.azure.com',deployment:'d',priceIn:'100',priceOut:'400'}))")


def _answer(text):
    return {"answer": text, "provider": "azure", "auth": "key", "model": "gpt-x", "at": "2026-11-20T10:00:00+09:00", "step": 2,
            "sentKinds": ["id", "title"], "sent": [{"repository": "r"}],
            "usage": {"inputTokens": 1000, "outputTokens": 500, "estimated": False},
            "ids": [{"id": "FR-001", "known": True}, {"id": "FR-999", "known": False}],
            "recommendations": [{"question": "Q-001", "option": None, "valid": False}]}


# FR-1098 AC-525 AC-526 / NFR-UX-019 AC-531 AC-533: consent, derived label, links, unknown IDs, evidence from the model
def test_ac525_ac526_ac531_ac533_answer_is_marked_linked_and_explained(studio):
    page = _open(studio, "dashboard")
    _configure(page)
    page.reload()
    page.wait_for_load_state("networkidle")
    consents = []
    page.route("**/api/ai/consent", lambda r: (consents.append(json.loads(r.request.post_data)), r.fulfill(status=200, content_type="application/json", body='{"consented": []}')))
    page.route("**/api/ai/ask", lambda r: r.fulfill(status=200, content_type="application/json",
                                                    body=json.dumps(_answer("FR-001 is late and FR-999 too.\nRECOMMEND Q-001: Z"))))
    _step(page, 2)
    page.get_by_test_id("ai-ask").click()
    intro = page.get_by_test_id("ai-intro").inner_text()
    assert all(w in intro for w in ("できること", "できないこと", "誤りうること"))
    assert page.get_by_test_id("ai-example").count() == 3
    page.get_by_test_id("ai-question").fill("what is late?")
    page.get_by_test_id("ai-send").click()
    page.wait_for_selector('[data-testid="ai-consent"]')
    assert "コードファイルの内容" in page.get_by_test_id("ai-consent").inner_text()
    page.get_by_test_id("ai-consent-agree").click()
    page.wait_for_selector('[data-testid="ai-answer"]')
    assert consents and consents[0]["repos"]
    ans = page.get_by_test_id("ai-answer")
    assert "派生物" in page.get_by_test_id("ai-derived").inner_text() and "gpt-x" in page.get_by_test_id("ai-meta").inner_text()
    assert ans.locator(":scope > p a.xref", has_text="FR-001").count() == 1
    assert ans.get_by_test_id("ai-unknown-id").inner_text().startswith("FR-999")
    assert "RECOMMEND" not in ans.inner_text() and page.get_by_test_id("ai-rec").get_attribute("data-valid") == "false"
    page.get_by_test_id("ai-evidence").locator("summary").first.click()
    ev = page.get_by_test_id("ai-evidence").inner_text()
    title = page.evaluate("async () => (await (await fetch('/api/model')).json()).reqs.find(r => r.id === 'FR-001').title")
    assert title in ev and "ステップ 2" in ev
    page.context.close()


# NFR-UX-019 AC-532 AC-533: keyboard cancel / retry / close; errors keep the question; the rest of the page still works
def test_ac532_ac533_keyboard_cancel_and_error_keeps_question(studio):
    page = _open(studio, "dashboard")
    _configure(page)
    page.reload()
    page.wait_for_load_state("networkidle")
    page.route("**/api/ai/consent", lambda r: r.fulfill(status=200, content_type="application/json", body='{"consented": []}'))
    page.route("**/api/ai/ask", lambda r: r.fulfill(status=502, content_type="application/json",
                                                    body=json.dumps({"error": "timeout", "detail": "no answer in 60 s", "action": "try again"})))
    page.locator("#q").fill(">AI")
    assert page.get_by_test_id("command-item").filter(has_text=re.compile("AI に聞く")).count() == 1
    page.locator("#q").press("Enter")
    page.wait_for_selector('[data-testid="ai-panel"]')
    page.get_by_test_id("ai-question").fill("keep me")
    page.get_by_test_id("ai-question").press("Control+Enter")
    page.get_by_test_id("ai-consent-agree").click()
    page.wait_for_selector('[data-testid="ai-error"]')
    assert "時間切れ" in page.get_by_test_id("ai-error").inner_text()
    assert page.get_by_test_id("ai-question").input_value() == "keep me"
    assert page.get_by_test_id("ai-live").inner_text()
    _step(page, 4)    # other screens keep working
    page.get_by_test_id("ai-question").focus()
    page.keyboard.press("Escape")
    page.wait_for_selector('[data-testid="ai-panel"]', state="detached")
    page.context.close()


# FR-1098 AC-527 (screen side): the answer can be closed and does not come back
def test_ac527_closed_answer_does_not_return(studio):
    page = _open(studio, "dashboard")
    _configure(page)
    page.reload()
    page.wait_for_load_state("networkidle")
    page.route("**/api/ai/consent", lambda r: r.fulfill(status=200, content_type="application/json", body='{"consented": []}'))
    page.route("**/api/ai/ask", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(_answer("FR-001"))))
    page.get_by_test_id("ai-ask").click()
    page.get_by_test_id("ai-example").first.click()
    page.get_by_test_id("ai-consent-agree").click()
    page.wait_for_selector('[data-testid="ai-answer"]')
    page.get_by_test_id("ai-dismiss").click()
    assert page.get_by_test_id("ai-answer").count() == 0
    page.get_by_test_id("ai-close").click()
    page.get_by_test_id("ai-ask").click()
    assert page.get_by_test_id("ai-answer").count() == 0
    page.context.close()

# NFR-UX-020 AC-534: the step bar, the release view, the AI settings and an AI answer follow the Fluent checks — reflow at
# 320 CSS px without horizontal scrolling, targets of 24px at least, a visible focus indicator, tokens only in their rules,
# a forced-colours rule
def test_ac534_new_screens_reflow_targets_focus_and_tokens(studio):
    page = _open(studio, "release", width=320)
    _configure(page)
    page.reload()
    page.wait_for_load_state("networkidle")
    page.route("**/api/ai/consent", lambda r: r.fulfill(status=200, content_type="application/json", body='{"consented": []}'))
    page.route("**/api/ai/ask", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(_answer("FR-001"))))
    small = """() => [...document.querySelectorAll('#steps button, #stepBand button, #stepBand a, [data-testid=ai-panel] button, [data-testid=ai-settings] button, [data-testid=ai-settings] input, [data-testid=release-state] a')]
        .filter(e => e.offsetParent).map(e => [e, e.getBoundingClientRect()]).filter(([e, r]) => r.width < 24 || r.height < 24).map(([e]) => e.outerHTML.slice(0, 60))"""
    wide = "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    assert page.evaluate(wide) and page.evaluate(small) == []
    page.get_by_test_id("ai-ask").click()
    page.get_by_test_id("ai-example").first.click()
    page.get_by_test_id("ai-consent-agree").click()
    page.wait_for_selector('[data-testid="ai-answer"]')
    assert page.evaluate(wide) and page.evaluate(small) == []
    page.get_by_test_id("ai-settings-open").click()
    page.get_by_test_id("ai-provider-copilot").check()
    page.get_by_test_id("ai-auth-byok").check()
    assert page.evaluate(wide) and page.evaluate(small) == []
    page.keyboard.press("Escape")
    page.locator('[data-testid="step"][aria-current="step"]').focus()
    page.keyboard.press("ArrowRight")
    outline = page.evaluate("() => { const s = getComputedStyle(document.activeElement); return [s.outlineStyle, parseFloat(s.outlineWidth)]; }")
    assert outline[0] != "none" and outline[1] >= 2
    css = (ROOT / "web" / "app.css").read_text(encoding="utf-8")
    new_rules = css[css.index("/* FR-1094: work steps"):]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", new_rules.split("@media (forced-colors")[0])   # colours from tokens only
    assert "@media (forced-colors: active){.step.on" in new_rules
    page.context.close()


# NFR-UX-020 AC-535: README and the user guide map each design principle to the acceptance criteria that judge it
def test_ac535_principles_table_points_to_existing_criteria():
    doc = (REPO / "docs" / "requirements-definition.md").read_text(encoding="utf-8")
    for path in (ROOT / "README.md", REPO / "users-guide" / "studio" / "02-screens.md"):
        text = path.read_text(encoding="utf-8")
        for principle in ("Natural on every platform", "Built for focus", "One for all, all for one", "Unmistakably Microsoft"):
            row = re.search(rf"^\|\s*{re.escape(principle)}\s*\|(.*)$", text, re.M)
            assert row, (path.name, principle)
            ids = re.findall(r"AC-\d{3}", row.group(1))
            assert ids, (path.name, principle)
            for i in ids:
                assert re.search(rf"受入基準 {i}:", doc), i



def _ask_once(page, answer="FR-001"):
    page.get_by_test_id("ai-ask").click()
    if page.get_by_test_id("ai-example").count():
        page.get_by_test_id("ai-example").first.click()
    page.wait_for_selector('[data-testid="ai-answer"], [data-testid="ai-budget-block"], [data-testid="ai-consent"]')
    if page.get_by_test_id("ai-consent-agree").count():
        page.get_by_test_id("ai-consent-agree").click()
        page.wait_for_selector('[data-testid="ai-answer"]')


def _route_ai(page, usage=None):
    page.route("**/api/ai/consent", lambda r: r.fulfill(status=200, content_type="application/json", body='{"consented": []}'))
    body = _answer("FR-001")
    if usage is not None:
        body["usage"] = usage
    page.route("**/api/ai/ask", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))


# FR-1101 AC-546: cap and unit prices are settings kept in the browser; without a unit price nothing is sent
def test_ac546_cap_and_prices_are_saved_and_missing_price_blocks_sending(studio):
    page = _open(studio, "dashboard")
    page.evaluate("() => localStorage.setItem('eabk-studio.ai', JSON.stringify({provider:'azure',auth:'key',endpoint:'https://x.openai.azure.com',deployment:'d'}))")
    page.reload()
    page.wait_for_load_state("networkidle")
    asked = []
    page.on("request", lambda r: asked.append(r.url) if r.url.endswith("/api/ai/ask") else None)
    page.get_by_test_id("ai-ask").click()
    page.get_by_test_id("ai-example").first.click()
    block = page.get_by_test_id("ai-budget-block")
    block.wait_for()
    assert "単価" in block.inner_text() and asked == []
    page.get_by_test_id("ai-settings-open").click()
    assert page.get_by_test_id("ai-budgetYen").get_attribute("placeholder") == "100000"     # PARAM-070 is the default
    page.get_by_test_id("ai-budgetYen").fill("50000")
    page.get_by_test_id("ai-budgetYen").press("Tab")
    page.get_by_test_id("ai-priceIn").fill("120")
    page.get_by_test_id("ai-priceIn").press("Tab")
    page.get_by_test_id("ai-priceOut").fill("480")
    page.get_by_test_id("ai-priceOut").press("Tab")
    page.reload()
    page.wait_for_load_state("networkidle")
    cfg = json.loads(page.evaluate("() => localStorage.getItem('eabk-studio.ai')"))
    assert (cfg["budgetYen"], cfg["priceIn"], cfg["priceOut"]) == ("50000", "120", "480")
    page.get_by_test_id("ai-settings-btn").click()
    assert page.get_by_test_id("ai-budgetYen").input_value() == "50000"
    page.context.close()


# FR-1101 AC-547: usage per answer (provider's tokens, or an estimate marked as such), the month's running total, month reset,
# and nothing of the question or answer is kept in the usage record
def test_ac547_usage_cost_and_monthly_total(studio):
    page = _open(studio, "dashboard")
    _configure(page)
    page.reload()
    page.wait_for_load_state("networkidle")
    _route_ai(page)
    _ask_once(page)
    line = page.get_by_test_id("ai-usage-line").inner_text()
    assert "入力 1000" in line and "出力 500" in line and "概算" in line      # 1000*100/1e6 + 500*400/1e6 = 0.30 yen
    assert "0.30 円" in line and "（概算）" not in line                        # the provider returned the counts
    assert "0.30 円 / 上限 100,000 円（0%）" in page.get_by_test_id("ai-budget-status").inner_text()
    stored = json.loads(page.evaluate("() => localStorage.getItem('eabk-studio.ai-usage')"))
    assert set(stored) == {"month", "inTokens", "outTokens", "yen"} and stored["inTokens"] == 1000
    page.get_by_test_id("ai-dismiss").click()
    page.unroute("**/api/ai/ask")
    _route_ai(page, {"inputTokens": 400, "outputTokens": 100, "estimated": True})
    page.get_by_test_id("ai-example").first.click()
    page.wait_for_selector('[data-testid="ai-answer"]')
    assert "（概算）" in page.get_by_test_id("ai-usage-line").inner_text()
    assert json.loads(page.evaluate("() => localStorage.getItem('eabk-studio.ai-usage')"))["inTokens"] == 1400
    page.evaluate("() => { const u = JSON.parse(localStorage.getItem('eabk-studio.ai-usage')); u.month = '2000-01'; localStorage.setItem('eabk-studio.ai-usage', JSON.stringify(u)); }")
    page.get_by_test_id("ai-close").click()
    page.get_by_test_id("ai-ask").click()
    assert "0.00 円" in page.get_by_test_id("ai-budget-status").inner_text()     # a new month starts from zero
    page.context.close()


# FR-1101 AC-548: warning at 80% (icon and words), stop at 100% with the reason; everything else keeps working
def test_ac548_warning_at_80_percent_and_stop_at_100_percent(studio):
    page = _open(studio, "dashboard")
    _configure(page)
    page.evaluate("""() => { const d = new Date(), m = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
        localStorage.setItem('eabk-studio.ai', JSON.stringify({provider:'azure',auth:'key',endpoint:'https://x.openai.azure.com',deployment:'d',priceIn:'100',priceOut:'400',budgetYen:'1000'}));
        localStorage.setItem('eabk-studio.ai-usage', JSON.stringify({month: m, inTokens: 0, outTokens: 0, yen: 799}));}""")
    page.reload()
    page.wait_for_load_state("networkidle")
    asked = []
    page.on("request", lambda r: asked.append(r.url) if r.url.endswith("/api/ai/ask") else None)
    page.get_by_test_id("ai-ask").click()
    status = page.get_by_test_id("ai-budget-status")
    assert status.get_attribute("data-level") == "ok"
    page.evaluate("() => { const u = JSON.parse(localStorage.getItem('eabk-studio.ai-usage')); u.yen = 800; localStorage.setItem('eabk-studio.ai-usage', JSON.stringify(u)); }")
    page.get_by_test_id("ai-close").click()
    page.get_by_test_id("ai-ask").click()
    status = page.get_by_test_id("ai-budget-status")
    assert status.get_attribute("data-level") == "warn" and status.locator("svg").count() == 1 and "80%" in status.inner_text()
    page.evaluate("() => { const u = JSON.parse(localStorage.getItem('eabk-studio.ai-usage')); u.yen = 1000; localStorage.setItem('eabk-studio.ai-usage', JSON.stringify(u)); }")
    page.get_by_test_id("ai-close").click()
    page.get_by_test_id("ai-ask").click()
    assert page.get_by_test_id("ai-budget-status").get_attribute("data-level") == "stop"
    page.get_by_test_id("ai-example").first.click()
    block = page.get_by_test_id("ai-budget-block")
    block.wait_for()
    assert "上限" in block.inner_text() and "来月" in block.inner_text() and asked == []
    page.locator('[data-testid="step"][data-step="3"]').click()           # AI is off the path of the other screens
    page.wait_for_function("() => location.hash.startsWith('#/map')")
    page.context.close()
