"""NFR-UX-002 AC-015 / AC-041: 配置（レイアウト）の保存・復元・既定へ戻す操作の配線（静的確認）。
ブラウザー上の動作は tests/system/e2e/test_studio_layout_authz_system.py（E2E-109/110）が確かめる。"""
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


def test_layout_module_saves_only_layout_id_and_falls_back_to_default():  # NFR-UX-002 AC-015
    js = (WEB / "js" / "layout.js").read_text(encoding="utf-8")
    assert "eabk-studio.layout" in js
    assert "LAYOUTS.includes(v) ? v : DEFAULT_LAYOUT" in js  # 不正値は既定
    assert js.count("localStorage.setItem") == 1 and "setItem(LAYOUT_KEY, id)" in js  # 保存は配置 ID だけ


def test_header_has_change_and_reset_controls_wired_in_app():  # NFR-UX-002 AC-041
    html = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "js" / "app.js").read_text(encoding="utf-8")
    for tid in ("layout-change", "layout-reset"):
        assert f'data-testid="{tid}"' in html and f'[data-testid="{tid}"]' in app
