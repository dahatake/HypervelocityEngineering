"""System tests for FR-1070 AC-381/AC-382, FR-1071 AC-385/AC-386, NFR-UX-015 AC-388 (EABK Studio 3D カメラのプリセット).

Expected values come only from the acceptance criteria in docs/requirements-definition.md.  The
implementation is NOT the oracle.

PROVISIONAL CONTRACT (仮置き。実装者が確認し、食い違えば CONFLICT として返す。この oracle は実装に合わせて直さない):
  - 表示モード切替: [data-testid="dim-toggle"] の中の [data-dim="3d"] を押すと 3D（ルート #/map2d から）。
  - プリセット選択 [data-testid="camera-presets"]、各項目 [data-preset=<id>]（button/option/radio のいずれでも可。クリックで選択）。
    現在値は [data-camera-preset] 属性（camera-presets 自身か 3D 領域のどちらか。ページ内で最初の要素を読む）。
  - 詳細表示 [data-testid="camera-detail"] に data-shot / data-angle / data-movement / data-motion。
  - window.__eabk3d.camera() は {preset, shot, angle, movement, motion} を返す（movement は "Static" 等の語彙）。
  - 自動動作の状態は [data-camera-auto="true|false"]（ページ内で最初の要素）。動きの軽減は [data-reduced-motion="true"]。
  - 「自動に戻す」操作の hook は AC にないため、このファイルでは「同じプリセットを再度選ぶ」だけを使う。
  - 3D の描画先は canvas。手動操作は canvas 上のドラッグ・ホイール、およびキー（矢印）。
"""
import pytest

from entity_repo import make_zoom
from test_studio_links_wrap_status_arch_system import _serve  # noqa: F401

VOCAB = {  # 要求定義書 FR-1070 の適用方式（語彙＋別名表）
    "shot": {"EWS", "WS", "FS", "MS", "MCU", "CU", "ECU", "MW"},
    "angle": {"Eye Level", "Low", "High", "Bird's Eye", "Worm's Eye", "Dutch", "Over-the-Shoulder", "POV"},
    "movement": {"Static", "Pan", "Tilt", "Dolly In", "Dolly Out", "Truck", "Pedestal", "Orbit", "Crane",
                 "Handheld", "Gimbal", "Whip Pan", "Zoom", "Dolly Zoom", "Roll", "FPV Fly-through"},
    "motion": {"Locked", "Slow", "Smooth", "Floating", "Natural", "Energetic", "Snappy", "Aggressive",
               "Hyperdynamic", "Impossible"},
}


@pytest.fixture()
def cam_url(tmp_path):
    proc, url = _serve(make_zoom(tmp_path / "cam"))
    yield url
    proc.terminate()


def _open_3d(browser, url, **ctx_args):
    ctx = browser.new_context(viewport={"width": 1400, "height": 900}, **ctx_args)
    page = ctx.new_page()
    page.goto(f"{url}/#/map2d")
    page.wait_for_selector('[data-testid="dim-toggle"]')
    page.locator('[data-testid="dim-toggle"] [data-dim="3d"]').click()
    page.wait_for_selector('[data-testid="camera-presets"]')
    return page


def _items(page):
    return page.locator('[data-testid="camera-presets"] [data-preset]')


def _preset_ids(page):
    return [e.get_attribute("data-preset") for e in _items(page).element_handles()]


def _current(page):
    return page.locator("[data-camera-preset]").first.get_attribute("data-camera-preset")


def _auto(page):
    return page.locator("[data-camera-auto]").first.get_attribute("data-camera-auto")


def _camera(page):
    return page.evaluate("() => window.__eabk3d.camera()")


def _pick(page, preset):
    page.locator(f'[data-testid="camera-presets"] [data-preset="{preset}"]').first.click()
    page.wait_for_timeout(300)


def _moving_preset(page):
    """先頭以外で自動動作を伴うプリセット（movement が Static でないもの）を選んで返す。"""
    for pid in _preset_ids(page):
        _pick(page, pid)
        if _camera(page)["movement"] != "Static" and _auto(page) == "true":
            return pid
    pytest.fail("自動動作を伴うプリセットが 1 つもない")


# FR-1070 AC-381
def test_ac381_nine_presets_default_corporate_and_selection_drives_camera(browser, cam_url):
    page = _open_3d(browser, cam_url)
    ids = _preset_ids(page)
    assert len(ids) == 9 and len(set(ids)) == 9, ids
    assert ids[0] == "corporate"
    assert _current(page) == "corporate"
    for item in _items(page).element_handles():
        assert item.inner_text().strip(), "平易な名称・説明が空"
        assert item.query_selector("svg, img, canvas, [data-icon], [data-preview]"), "アイコンまたはプレビューがない"
    target = ids[3]
    _pick(page, target)
    assert _current(page) == target
    assert _camera(page)["preset"] == target
    # 異常系: 存在しないプリセットは選べず、現在値は変わらない
    assert _items(page).filter(has=page.locator('[data-preset="__none__"]')).count() == 0
    assert _current(page) == target


# FR-1070 AC-382
def test_ac382_detail_shows_four_elements_in_vocabulary_for_every_preset(browser, cam_url):
    page = _open_3d(browser, cam_url)
    for pid in _preset_ids(page):
        _pick(page, pid)
        detail = page.get_by_test_id("camera-detail")
        if not detail.is_visible():
            detail = page.get_by_test_id("camera-detail").first
        vals = {k: detail.get_attribute(f"data-{k}") for k in ("shot", "angle", "movement", "motion")}
        assert all(vals.values()), (pid, vals)
        cam = _camera(page)
        assert cam["preset"] == pid
        for k, v in vals.items():
            assert cam[k] == v, (pid, k, cam[k], v)
        for k, v in vals.items():
            parts = v.split("→")
            assert 1 <= len(parts) <= 2, (pid, k, v)  # 遷移の複合値は 2 値まで
        for k, v in vals.items():
            for part in v.split("→"):
                assert part.strip() in VOCAB[k], f"語彙にない {k}: {part} ({pid})"


# FR-1071 AC-385
def test_ac385_reduced_motion_forces_static_keeps_info_and_restores_when_unset(browser, cam_url):
    page = _open_3d(browser, cam_url, reduced_motion="reduce")
    assert page.locator('[data-reduced-motion="true"]').count() >= 1
    for pid in _preset_ids(page):
        _pick(page, pid)
        assert _camera(page)["movement"] == "Static", pid
        assert _auto(page) != "true", pid
        item = page.locator(f'[data-testid="camera-presets"] [data-preset="{pid}"]').first
        assert item.inner_text().strip(), "名称・説明が欠けた"
    # 異常系: 設定を戻して再読み込みすると自動動作が有効になる
    page.emulate_media(reduced_motion="no-preference")
    page.reload()
    page.wait_for_selector('[data-testid="camera-presets"]')
    page.locator('[data-testid="dim-toggle"] [data-dim="3d"]').click()
    assert page.locator('[data-reduced-motion="true"]').count() == 0
    assert _moving_preset(page)


# FR-1071 AC-386
@pytest.mark.parametrize("manual", ["drag", "wheel", "key"])
def test_ac386_manual_operation_stops_auto_and_only_reselect_resumes(browser, cam_url, manual):
    page = _open_3d(browser, cam_url)
    pid = _moving_preset(page)
    box = page.locator("canvas").first.bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    if manual == "drag":
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.move(cx + 120, cy + 40, steps=8)
        page.mouse.up()
    elif manual == "wheel":
        page.mouse.move(cx, cy)
        page.mouse.wheel(0, -300)
    else:
        page.locator("canvas").first.focus()
        page.keyboard.press("ArrowLeft")
    page.wait_for_timeout(200)
    assert _auto(page) == "false"
    # 手動操作の後は勝手に再開しない
    page.wait_for_timeout(1500)
    assert _auto(page) == "false"
    # 同じプリセットを再度選ぶと再開する
    _pick(page, pid)
    assert _auto(page) == "true"


# NFR-UX-015 AC-388
def test_ac388_no_external_network_while_3d_camera_presets_active(browser, cam_url):
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    origin = cam_url.rstrip("/")
    seen = []
    page.on("request", lambda r: seen.append(r.url))
    page.goto(f"{cam_url}/#/map2d")
    page.wait_for_selector('[data-testid="dim-toggle"]')
    page.locator('[data-testid="dim-toggle"] [data-dim="3d"]').click()
    page.wait_for_selector('[data-testid="camera-presets"]')
    for pid in _preset_ids(page):
        _pick(page, pid)
    page.wait_for_timeout(1000)
    external = [u for u in seen if not (u.startswith(origin) or u.startswith(("data:", "blob:", "about:")))]
    assert external == [], external
    scripts = [u for u in seen if u.split("?")[0].endswith(".js") and "three" in u.lower()]
    assert scripts and all(u.split("?")[0].endswith("three.module.min.js") for u in scripts), scripts
