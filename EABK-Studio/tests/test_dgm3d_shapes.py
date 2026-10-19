"""Static wiring tests: the diagram 3D view (dgm3d.js) draws per-kind shapes, not sprites.
FR-1068 / FR-1069 / FR-1070 / FR-1071. Run: python -m pytest EABK-Studio/tests/test_dgm3d_shapes.py -q"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
SRC = (WEB / "js" / "dgm3d.js").read_text(encoding="utf-8")


# FR-1068 AC-374: nodes are shapes from shapes3d.js; no second kind->shape table and no round sprites
def test_fr1068_ac374_uses_shared_shape_table_not_sprites():
    assert "from './shapes3d.js'" in SRC and "buildNodeObjects" in SRC and "shapeOf" in SRC
    assert "THREE.Sprite(new THREE.SpriteMaterial({ map: dot" not in SRC
    assert not re.search(r"\b(crystal|scroll|gear|gate|database)\b\s*:", SRC), "kind->shape table must live only in shapes3d.js"
    assert "kind: e.type" in SRC  # the node type is the kind


# FR-1068 AC-374: legend and test hook
def test_fr1068_legend_and_hook():
    assert "buildLegend" in SRC and "window.__eabk3d" in SRC and "nodes:" in SRC


# FR-1069: style toggle, Software Engineering default, only the style name is stored (shapes3d.saveStyle)
def test_fr1069_style_toggle():
    assert "buildStyleToggle" in SRC and "loadStyle()" in SRC and "saveStyle(" in SRC and "FX_BY_STYLE" in SRC


# FR-1070 / FR-1071: camera presets, reduced motion handled in camera3d (Static) and in the fx loop here; manual input via rig
def test_fr1070_fr1071_camera_rig_and_reduced_motion():
    assert "createCameraRig" in SRC and "interact: stage" in SRC and "applyDelta" in SRC
    assert "prefers-reduced-motion" in SRC
    assert "rig.destroy()" in SRC and "delete window.__eabk3d" in SRC


# selection, labels and picking are kept
def test_existing_selection_label_pick_behaviour_kept():
    for needle in ("onPick?.(", "setSelected(id)", "labelOf(", "keydown"):
        assert needle in SRC
