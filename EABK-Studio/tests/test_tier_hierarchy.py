"""Integration tests for FR-1062 (種類→区分→領域→項目の階層の導出). Run: python -m pytest EABK-Studio/tests/test_hierarchy.py -q"""
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import eabk_model as m  # noqa: E402

SEP = "\u3000"


def _req(rid, area, ac):
    s = (f"#### {rid} 試験要求\n- 要求: 試験。\n- 決定状態: 承認済み（依頼 2026-10-18）{SEP}出自: 依頼原文{SEP}優先度: MUST（試験）\n"
         f"- 上位: G-001{SEP}出典: 依頼原文\n")
    if area:
        s += f"- 領域: {area}\n"
    return s + f"- 受入基準 {ac}: 試験。\n  - 検証レベル: integration\n\n"


def _repo(tmp_path, with_area=True):
    (tmp_path / "docs").mkdir()
    (tmp_path / "users-guide").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "users-guide" / "01-a.md").write_text("# はじめに\n", encoding="utf-8")
    (tmp_path / "scripts" / "x.py").write_text("print(1)\n", encoding="utf-8")
    rd = ("# 要求定義書\n\n### 1.2 目的\n\n| ID | 目的 | 成功指標 | 測定方法 |\n|---|---|---|---|\n| G-001 | 目的 | 合格 | 試験 |\n\n"
          "### 6.1 機能要求\n\n" + _req("FR-001", "領域甲" if with_area else None, "AC-001")
          + _req("NFR-SEC-001", "領域乙", "AC-002") + _req("NFR-PERF-001", "領域乙", "AC-003"))
    (tmp_path / "docs" / "requirements-definition.md").write_text(rd, encoding="utf-8")
    (tmp_path / "docs" / "catalog.md").write_text(
        "# カタログ\n\n#### 領域: 試験節\n\n| 機能 ID | 名称 |\n|---|---|\n| F-1 | 一 |\n\n## 共通部品\n\n| 部品名 | ファイル | 用途 | 使っている要求 ID |\n|---|---|---|---|\n| 部品 | `a.py` | 用 | FR-001 |\n",
        encoding="utf-8")
    return tmp_path


def _hier(root):
    return m.build_model(root)["hierarchy"]


# FR-1062 AC-343: 4 層・区分は ID 接頭辞・非機能の接頭辞で層が増えない・領域は欄
def test_ac343_four_tiers_division_from_prefix_area_from_field(tmp_path):
    h = _hier(_repo(tmp_path))
    for it in h["items"]:
        assert all(it.get(k) for k in ("kind", "division", "area", "id")), it
    reqs = {i["id"]: i for i in h["items"] if i["kind"] == "要求"}
    assert (reqs["FR-001"]["division"], reqs["FR-001"]["area"]) == ("機能", "領域甲")
    for rid in ("NFR-SEC-001", "NFR-PERF-001"):
        assert (reqs[rid]["division"], reqs[rid]["area"]) == ("非機能", "領域乙")
    assert {i["division"] for i in reqs.values()} == {"機能", "非機能"}
    assert {"目的", "要求", "受入基準", "カタログ", "users-guide", "scripts"} <= {i["kind"] for i in h["items"]}


# FR-1062 AC-343: 元データの変更が再導出で反映される（保存した割り当てを持たない）
def test_ac343_rederivation_reflects_change(tmp_path):
    root = _repo(tmp_path)
    p = root / "docs" / "requirements-definition.md"
    p.write_text(p.read_text(encoding="utf-8").replace("領域甲", "領域丙"), encoding="utf-8")
    assert {i["id"]: i["area"] for i in _hier(root)["items"] if i["kind"] == "要求"}["FR-001"] == "領域丙"


# FR-1062 AC-344: 領域の欄のない要求は「未分類」、カタログ・users-guide は既存の分類名
def test_ac344_unclassified_only_without_existing_classification(tmp_path):
    h = _hier(_repo(tmp_path, with_area=False))
    by = {(i["kind"], i["id"]): i for i in h["items"]}
    assert by[("要求", "FR-001")]["area"] == "未分類"
    assert by[("要求", "NFR-SEC-001")]["area"] == "領域乙"
    assert by[("カタログ", "F-1")]["area"] == "試験節"
    assert by[("users-guide", "users-guide/01-a.md")]["area"] == "はじめに"


# FR-1062 AC-344: 全データが 1 回ずつ属し、層ごとの件数の合計が全件数と一致する
def test_ac344_exactly_once_and_counts_sum(tmp_path):
    h = _hier(_repo(tmp_path, with_area=False))
    keys = [(i["kind"], i["id"]) for i in h["items"]]
    assert len(keys) == len(set(keys))
    assert sum(t["count"] for t in h["tiers"]) == len(h["items"])
    per = Counter((i["kind"], i["division"], i["area"]) for i in h["items"])
    assert all(per[tuple(t["path"])] == t["count"] for t in h["tiers"])


# FR-1062: 共通 JS 部品が存在し、開閉・aria・キーボード・JA/EN の名称を持つ
def test_hier_js_component_contract():
    s = (ROOT / "web" / "js" / "hier.js").read_text(encoding="utf-8")
    for needle in ("export function renderTiers", "aria-expanded", "data-tier-path", "ArrowDown", "tier-toggle"):
        assert needle in s
    # FR-011 AC-432: the English tier names live in the dictionary (web/js/i18n.js)
    assert "'tier.n.unclassified': 'Unclassified'" in (ROOT / "web" / "js" / "i18n.js").read_text(encoding="utf-8")
    assert not re.search(r"fetch\(", s)
