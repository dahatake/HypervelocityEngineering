"""Static wiring of the semantic zoom (FR-1027..FR-1029, NFR-UX-010 AC-187): bilingual words, routes, install list."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "EABK-Studio" / "web"


def js(name: str) -> str:
    return (WEB / "js" / name).read_text(encoding="utf-8")


# NFR-UX-010 AC-187: every sz.* word used by the code exists in both languages
def test_every_sz_key_is_defined_in_ja_and_en():
    text = js("i18n.js")
    ja, en = text.split("  en: {", 1)
    used = set()
    for name in ("semzoom.js", "sz2d.js", "sz3d.js", "map2d.js", "map3d.js", "entities.js"):
        used |= {k for k in re.findall(r"t\('(sz\.[\w.]+)'", js(name)) if not k.endswith(".")}
    used |= {f"sz.level.{k}" for k in ("overview", "mid", "detail")} | {f"sz.lv.{k}" for k in ("overview", "mid", "detail")}
    for key in sorted(used):
        assert f"'{key}'" in ja, f"{key} missing in ja"
        assert f"'{key}'" in en, f"{key} missing in en"


# FR-1027 / FR-1029: the three routes mount the shared shell; 2D and 3D share one view state
def test_routes_mount_the_shared_semantic_zoom_shell():
    assert "mountShell" in js("entities.js") and "create2d" in js("entities.js")
    assert "mountShell" in js("map2d.js") and "create2d" in js("map2d.js")
    assert "mountShell" in js("map3d.js") and "create3d" in js("map3d.js")
    core = js("semzoom.js")
    assert "export const view" in core and 'data-testid\': \'semantic-zoom\'' in core
    assert "window.eabkView" in core and "setScale" in core and "getState" in core
    assert "PARAM-017" in core and "PARAM-018" in core  # 閾値は PARAM


# NFR-UX-010 AC-185/186: keyboard handler, live region and the table alternative exist
def test_keyboard_live_region_and_table_alternative_are_present():
    core = js("semzoom.js")
    for needle in ("keydown", "aria-live", "sz-alt", "data-alt-edge", "aria-label", "role: 'toolbar'"):
        assert needle in core, needle


# the install list carries every new file (a missing one breaks the installed Studio)
def test_install_manages_all_semantic_zoom_files():
    install = (ROOT / "tools" / "install.py").read_text(encoding="utf-8")
    for rel in ("web/js/semzoom.js", "web/js/sz2d.js", "web/js/sz3d.js", "web/js/entities.js", "web/sz.css"):
        assert f"EABK-Studio/{rel}" in install, rel
    assert 'href="sz.css"' in (WEB / "index.html").read_text(encoding="utf-8")
