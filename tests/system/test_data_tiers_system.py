"""System Tests for FR-1062 (各データの上位層の定義: 種類→区分→領域→項目). AC-343, AC-344.

Expected values come from the acceptance criteria only.  The implementation is NOT the oracle: the expected
requirement areas / divisions are computed here directly from the repository documents (the `領域` field and
the ID prefix), never from the tool's own output.

Every test works on a disposable Git repository (datalayer_repo.py); the source checkout is never written.

PROVISIONAL CONTRACT (仮置き。要求は振る舞いのみを定めるため、綴りは実装者が確認し、食い違えば CONFLICT として返す):
  derivation command : python scripts/rdcheck.py hierarchy --json
  output             : {"items": [{"kind","division","area","id"}, ...],
                        "tiers": [{"path": [kind, division, area], "count": n}, ...]}
    kind     : 種類（AC-225 の種別。目的・要求・受入基準・試験ケース・カタログ・エンティティ・users-guide・scripts 等）
    division : 区分（要求は 機能 / 非機能。ほかの種類は既存の節・区分）
    area     : 領域（要求は `- 領域: <名>` の欄。なければ既存の分類名、なければ「未分類」）
  catalog sections   : `#### 領域: <名>` 見出し（test_data_hierarchy_system.py と同じ）
"""
from __future__ import annotations

import json
import re
from collections import Counter

import pytest

import datalayer_repo as d

RDC = ["scripts/rdcheck.py"]
REQ_BLOCK = re.compile(r"^#### ((?:FR|NFR-[A-Z0-9]+)-\d+) ", re.M)


@pytest.fixture
def repo(tmp_path):
    return d.make_clean_installed(tmp_path / "EABK tiers with spaces")


def txt(root, rel):
    return (root / rel).read_text(encoding="utf-8")


def put(root, rel, s):
    (root / rel).write_text(s, encoding="utf-8", newline="\n")


def derive(root):
    r = d.py(root, *RDC, "hierarchy", "--json")
    assert d.no_traceback(r), r.stdout + r.stderr
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def requirement_blocks(root):
    """独立の期待値: ID -> (区分, 領域 or None)。ID 接頭辞と各要求の領域の欄だけから決める。"""
    s = txt(root, d.RD)
    ms = list(REQ_BLOCK.finditer(s))
    out = {}
    for i, m in enumerate(ms):
        body = s[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(s)]
        a = re.search(r"領域: ([^\s　]+)", body)
        out[m.group(1)] = ("機能" if m.group(1).startswith("FR-") else "非機能", a.group(1) if a else None)
    return out


def req_items(h):
    return [i for i in h["items"] if re.fullmatch(r"(?:FR|NFR-[A-Z0-9]+)-\d+", i["id"])]


def set_area(root, rid, area):
    s = txt(root, d.RD)
    i = s.index(f"#### {rid} ")
    j = s.index("\n- 関連する既存資産", i)
    put(root, d.RD, s[:j] + f"\n- 領域: {area}" + s[j:])


def add_req(root, rid, area):
    s = txt(root, d.RD)
    sep = "\u3000"
    blk = (f"\n#### {rid} 上位層テスト用\n- 要求: 試験用。\n- 決定状態: 承認済み（依頼 2026-10-18）{sep}出自: 依頼原文{sep}優先度: MUST（試験）\n"
           f"- 上位: G-001{sep}出典: 依頼原文{sep}対象エンティティ: なし{sep}関係する状態: なし{sep}参照パラメータ: なし\n")
    if area:
        blk += f"- 領域: {area}\n"
    blk += "- 関連する既存資産: なし\n- 受入基準 AC-" + "9" * 4 + ": 試験用。\n  - 検証レベル: integration\n"
    put(root, d.RD, s.replace("### 6.1 機能要求\n", "### 6.1 機能要求\n" + blk, 1) if rid.startswith("FR-")
        else s.rstrip("\n") + "\n" + blk)


# ============================================================================ AC-343
# FR-1062 AC-343: 各データが 種類・区分・領域・項目 の 4 層で並ぶ
def test_ac343_every_data_item_has_four_tiers(repo):
    h = derive(repo)
    assert h["items"], "導出結果が空"
    for it in h["items"]:
        for k in ("kind", "division", "area", "id"):
            assert it.get(k), f"4 層のうち {k} が欠けている: {it}"
    kinds = {i["kind"] for i in h["items"]}
    assert len(kinds) >= 4, f"種類が少なすぎる（要求・カタログ・台帳・users-guide・scripts 等が並ぶはず）: {kinds}"


# FR-1062 AC-343: 要求の区分は ID 接頭辞（FR=機能、NFR-=非機能）と一致する
def test_ac343_requirement_division_matches_id_prefix(repo):
    h = derive(repo)
    reqs = req_items(h)
    assert reqs
    for it in reqs:
        want = "機能" if it["id"].startswith("FR-") else "非機能"
        assert it["division"] == want, f"{it['id']}: 区分 {it['division']!r} != {want!r}"


# FR-1062 AC-343（異常系）: 非機能の接頭辞（SEC・PERF ほか）で区分の層が増えない
def test_ac343_nonfunctional_prefixes_do_not_add_division_layer(repo):
    add_req(repo, "NFR-SEC-" + "9" * 4, "試験領域")
    add_req(repo, "NFR-PERF-" + "9" * 4, "試験領域")
    h = derive(repo)
    divisions = {i["division"] for i in req_items(h)}
    assert divisions == {"機能", "非機能"}, divisions
    for it in req_items(h):
        if it["id"] in ("NFR-SEC-" + "9" * 4, "NFR-PERF-" + "9" * 4):
            assert (it["division"], it["area"]) == ("非機能", "試験領域"), it


# FR-1062 AC-343: 要求の領域が各要求の領域の欄と一致する（9.2 の写しとも一致する）
def test_ac343_requirement_area_equals_area_field_and_matches_9_2(repo):
    set_area(repo, "FR-001", "試験領域A")
    expected = requirement_blocks(repo)
    got = {i["id"]: i["area"] for i in req_items(derive(repo))}
    assert got["FR-001"] == "試験領域A"
    for rid, (_, area) in expected.items():
        if area:
            assert got.get(rid) == area, f"{rid}: 欄={area!r} 導出={got.get(rid)!r}"
    s = txt(repo, d.RD)
    rows = re.findall(r"^\| ((?:FR|NFR-[A-Z0-9]+)-\d+) \| ([^|]+?) \|\s*$", s, re.M)
    for rid, area in rows:
        if rid in got and rid in expected and expected[rid][1]:
            assert expected[rid][1] == area.strip(), f"9.2 の写しが欄と違う: {rid}"


# FR-1062 AC-343（異常系）: 元データの変更が再導出で反映され、新たな割り当て表・ファイルを作らない
def test_ac343_rederivation_reflects_source_change_without_new_assignment_table(repo):
    set_area(repo, "FR-001", "最初の領域")
    assert {i["id"]: i["area"] for i in req_items(derive(repo))}["FR-001"] == "最初の領域"
    s = txt(repo, d.RD).replace("- 領域: 最初の領域", "- 領域: 変更後の領域", 1)
    put(repo, d.RD, s)
    assert {i["id"]: i["area"] for i in req_items(derive(repo))}["FR-001"] == "変更後の領域"
    st = d.run(["git", "status", "--porcelain"], repo)
    changed = [l[3:] for l in st.stdout.splitlines()]
    assert changed == [d.RD] or changed == [d.RD.replace("\\", "/")], f"導出が余計なファイルを作った/変えた: {changed}"


# ============================================================================ AC-344
# FR-1062 AC-344: 領域の欄がない要求は領域「未分類」に入り、欠けない
def test_ac344_requirement_without_area_goes_to_unclassified(repo):
    add_req(repo, "FR-" + "9" * 4, None)
    got = {i["id"]: i for i in req_items(derive(repo))}
    assert "FR-" + "9" * 4 in got, "領域のない要求が導出から欠けた"
    assert got["FR-" + "9" * 4]["area"] == "未分類"
    assert got["FR-" + "9" * 4]["division"] == "機能"


# FR-1062 AC-344: 領域の欄がないデータは既存の分類（カタログの節名）を領域に使う
def test_ac344_catalog_rows_use_existing_section_name_as_area(repo):
    s = txt(repo, "docs/catalog.md")
    put(repo, "docs/catalog.md", s.rstrip("\n") + "\n\n#### 領域: 試験カタログ節\n\n| 機能 ID | 名称 |\n|---|---|\n| F-9001 | 試験機能 |\n")
    h = derive(repo)
    cat = [i for i in h["items"] if i["id"] == "F-9001"]
    assert len(cat) == 1, f"カタログの行が 1 回ずつ並ばない: {cat}"
    assert cat[0]["area"] == "試験カタログ節"


# FR-1062 AC-344: 全データが 1 つの上位層にちょうど 1 回属し、各上位層の件数の合計が全件数と一致する
def test_ac344_each_item_belongs_exactly_once_and_tier_counts_sum_to_total(repo):
    h = derive(repo)
    keys = [(i["kind"], i["id"]) for i in h["items"]]
    dup = [k for k, n in Counter(keys).items() if n > 1]
    assert not dup, f"重複して属するデータ: {dup[:5]}"
    tiers = h["tiers"]
    assert sum(t["count"] for t in tiers) == len(h["items"]), "上位層の件数の合計が全データ件数と違う"
    per = Counter((i["kind"], i["division"], i["area"]) for i in h["items"])
    for t in tiers:
        assert per[tuple(t["path"])] == t["count"], f"{t['path']}: 件数が項目数と違う"


# FR-1062 AC-344（異常系）: 分類が定まらないデータだけが「未分類」に入り、分類のあるデータは入らない
def test_ac344_unclassified_only_for_items_without_any_classification(repo):
    set_area(repo, "FR-001", "試験領域B")
    add_req(repo, "FR-" + "8" * 4, None)
    got = {i["id"]: i["area"] for i in req_items(derive(repo))}
    assert got["FR-001"] == "試験領域B"
    assert got["FR-" + "8" * 4] == "未分類"
    expected = requirement_blocks(repo)
    for rid, area in got.items():
        if area == "未分類":
            assert expected[rid][1] is None, f"{rid} は領域の欄があるのに未分類にされた"
