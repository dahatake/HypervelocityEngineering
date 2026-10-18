"""System Tests for FR-1057 (hierarchy), FR-1058 (metadata), FR-1059 (relation index), NFR-UX-014 (information design).

Expected values come from the acceptance criteria only (AC-315..AC-322, AC-324).
AC-323 and AC-326 use the FR-1060 assignment table (decision record 9.2: | 要求 ID | 領域 |), approved.

Every test works on a disposable Git repository (datalayer_repo.py); the source checkout is never written.

[ASSUMPTION] concrete interface (the requirements fix behaviour, not spelling; adjust if the implementation settles otherwise):
  area field        : a line  `- 領域: <名>`  inside the requirement block
  area table        : RD table  | 領域名 | 上位 G-ID | 要求数 |
  area filter       : python scripts/rdcheck.py list --area <名>
  catalog sections  : a heading line  `#### 領域: <名>`  before each group of catalog function rows
  relation index    : python scripts/rdcheck.py index --json   -> list of {"from","kind","to"}
  check output      : lines "<ERROR|WARN> <CHK-ID> <location> <message>"
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import datalayer_repo as d

SOURCE = d.SOURCE
RDC = ["scripts/rdcheck.py"]


@pytest.fixture
def repo(tmp_path):
    return d.make_clean_installed(tmp_path / "EABK hierarchy with spaces")


def txt(root, rel):
    return (root / rel).read_text(encoding="utf-8")


def put(root, rel, s):
    (root / rel).write_text(s, encoding="utf-8", newline="\n")


def check(root):
    r = d.py(root, *RDC, "check")
    assert d.no_traceback(r), r.stdout + r.stderr
    return r


def lines(r, level):
    return [l for l in (r.stdout + "\n" + r.stderr).splitlines() if l.startswith(level)]


def set_area(root, rid, area):
    """Insert `- 領域: area` after the 上位 line of the requirement block."""
    s = txt(root, d.RD)
    i = s.index(f"#### {rid} ")
    j = s.index("\n- 関連する既存資産", i)
    put(root, d.RD, s[:j] + f"\n- 領域: {area}" + s[j:])


def add_area_table(root, areas):
    s = txt(root, d.RD)
    tbl = "\n### 領域一覧\n\n| 領域名 | 上位 G-ID | 要求数 |\n|---|---|---|\n" + "".join(
        f"| {a} | G-001 | {n} |\n" for a, n in areas) + "\n"
    put(root, d.RD, s.replace("### 6.1 機能要求\n", tbl + "### 6.1 機能要求\n", 1))


def count_stats(root):
    r = d.py(root, *RDC, "stats")
    return json.loads(r.stdout)


# ============================================================================ FR-1057
# FR-1057 AC-315: 移行期（割り当て表なし）は領域の欄が無くても違反にも警告にもならない
def test_ac315_transition_unassigned_is_neither_error_nor_warn(repo):
    r = check(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    bad = [l for l in (lines(r, "ERROR") + lines(r, "WARN")) if "領域" in l]
    assert not bad, "移行期の未所属を違反・警告にした:\n" + "\n".join(bad)


# FR-1057 AC-316: 領域で絞った一覧は、その領域の要求だけを ID・題名・決定状態つきで返す。合計は廃止を除く要求数
def test_ac316_list_by_area_and_sum_equals_non_abolished(repo):
    add_area_table(repo, [("受付", 1), ("照会", 1)])
    set_area(repo, "FR-001", "受付")
    set_area(repo, "FR-002", "照会")
    a = d.py(repo, *RDC, "list", "--area", "受付")
    b = d.py(repo, *RDC, "list", "--area", "照会")
    assert a.returncode == 0 and b.returncode == 0, a.stderr + b.stderr
    assert "FR-001" in a.stdout and "注文の登録" in a.stdout and "承認済み" in a.stdout, a.stdout
    assert "FR-002" not in a.stdout, "別の領域の要求が混ざった"
    assert "FR-002" in b.stdout and "FR-001" not in b.stdout, b.stdout
    st = count_stats(repo)["by_state"]
    total = sum(st.get(k, 0) for k in ("承認済み", "承認待ち", "保留", "却下"))
    per_area = sum(len(re.findall(r"^FR-\d+|^NFR-[A-Z0-9]+-\d+", o.stdout, re.M)) for o in (a, b))
    assert per_area == total, f"領域の件数の合計 {per_area} != 廃止を除く要求数 {total}"


# FR-1057 AC-316 (異常系): 廃止の要求は領域の件数に含まれない
def test_ac316_abolished_requirement_not_counted_in_area(repo):
    add_area_table(repo, [("受付", 1)])
    set_area(repo, "FR-001", "受付")
    set_area(repo, "FR-002", "受付")
    s = txt(repo, d.RD)
    i = s.index("#### FR-002 ")
    j = s.index("決定状態: 承認済み", i)
    put(repo, d.RD, s[:j] + "決定状態: 廃止" + s[j + len("決定状態: 承認済み"):])
    a = d.py(repo, *RDC, "list", "--area", "受付")
    assert "FR-001" in a.stdout and "FR-002" not in a.stdout, a.stdout
    st = count_stats(repo)["by_state"]
    assert st.get("廃止", 0) == 1


# FR-1057 AC-317: カタログの領域の区切りと要求定義書の領域が食い違うと不整合になる
def test_ac317_catalog_area_mismatch_reported(repo):
    add_area_table(repo, [("受付", 1), ("照会", 1)])
    set_area(repo, "FR-001", "受付")
    set_area(repo, "FR-002", "照会")
    cat = txt(repo, d.CATALOG)
    hdr = "| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |\n|---|---|---|---|---|---|\n"
    row1 = "| FR-001 | 注文の登録 | 承認済み | 未実装 | 未実装 | なし |\n"
    row2 = "| FR-002 | 注文の照会 | 承認済み | 未実装 | 未実装 | なし |\n"
    ok = cat.replace(hdr + row1 + row2,
                     "#### 領域: 受付\n\n" + hdr + row1 + "\n#### 領域: 照会\n\n" + hdr + row2)
    assert ok != cat, "前提: カタログの表の形が想定と違う（テストの誤り）"
    put(repo, d.CATALOG, ok)
    base = check(repo)
    assert not [l for l in lines(base, "ERROR") if "FR-00" in l], base.stdout
    bad = cat.replace(hdr + row1 + row2,
                      "#### 領域: 受付\n\n" + hdr + row1 + row2)  # FR-002 を受付の区切りに置く（要求定義書は照会）
    put(repo, d.CATALOG, bad)
    r = check(repo)
    assert r.returncode == 1 and [l for l in lines(r, "ERROR") if "FR-002" in l], r.stdout + r.stderr


# ============================================================================ FR-1058
# FR-1058 AC-318: 現行の構造化欄・領域・更新日・版は違反にならない
def test_ac318_current_and_new_optional_fields_are_valid(repo):
    set_area(repo, "FR-001", "受付")
    s = txt(repo, d.RD)
    j = s.index("\n- 関連する既存資産", s.index("#### FR-001 "))
    put(repo, d.RD, s[:j] + "\n- 更新日: 2026-10-17\n- 版: 1" + s[j:])
    r = check(repo)
    bad = [l for l in lines(r, "ERROR") if "FR-001" in l and ("更新日" in l or "版" in l or "領域" in l)]
    assert not bad, "\n".join(bad)


# FR-1058 AC-318 (異常系): 定義に無い欄は位置つきで報告される
def test_ac318_unknown_field_reported_with_location(repo):
    s = txt(repo, d.RD)
    j = s.index("\n- 関連する既存資産", s.index("#### FR-001 "))
    put(repo, d.RD, s[:j] + "\n- 謎の欄: x" + s[j:])
    r = check(repo)
    hit = [l for l in lines(r, "ERROR") if "謎の欄" in l]
    assert r.returncode == 1 and hit, r.stdout + r.stderr
    assert any("FR-001" in l or re.search(r"requirements-definition\.md:\d+", l) for l in hit), hit


# FR-1058 AC-318 (異常系): 許容値外の値は位置つきで報告される
def test_ac318_value_outside_allowed_reported(repo):
    s = txt(repo, d.RD)
    i = s.index("#### FR-001 ")
    put(repo, d.RD, s[:i] + s[i:].replace("優先度: MUST", "優先度: ほぼ必須", 1))
    r = check(repo)
    hit = [l for l in lines(r, "ERROR") if "優先度" in l or "ほぼ必須" in l]
    assert r.returncode == 1 and hit, r.stdout + r.stderr


# FR-1058 AC-318: 現行の全要求は初期定義の下で違反にならない（この checkout で確認。読み取りのみ）
def test_ac318_source_checkout_has_no_metadata_violation():
    r = d.py(SOURCE, *RDC, "check")
    assert d.no_traceback(r), r.stdout + r.stderr
    bad = [l for l in lines(r, "ERROR") if "欄" in l or "許容" in l]
    assert not bad, "\n".join(bad)


# FR-1058 AC-319: 領域・更新日を足しても要求・受入基準の文面と決定状態は変わらない
def test_ac319_adding_optional_fields_changes_only_those_lines(repo):
    before = txt(repo, d.RD)
    show_before = d.py(repo, *RDC, "show", "FR-001").stdout
    set_area(repo, "FR-001", "受付")
    s = txt(repo, d.RD)
    j = s.index("\n- 関連する既存資産", s.index("#### FR-001 "))
    put(repo, d.RD, s[:j] + "\n- 更新日: 2026-10-17" + s[j:])
    after = txt(repo, d.RD)
    removed = [l for l in before.splitlines() if l not in after.splitlines()]
    added = [l for l in after.splitlines() if l not in before.splitlines()]
    assert not removed, removed
    assert sorted(added) == sorted(["- 領域: 受付", "- 更新日: 2026-10-17"]), added
    sh = d.py(repo, *RDC, "show", "FR-001")
    # 本文・決定状態は追加前と同じ（fixture 本文の語には依存しない。追加前の表示行がすべて残る）
    assert "承認済み" in sh.stdout
    missing = [l for l in show_before.splitlines() if l not in sh.stdout.splitlines()]
    assert not missing, missing
    dg = d.py(repo, *RDC, "digest", "AC-001")
    assert dg.returncode == 0, dg.stderr
    assert check(repo).returncode == 0


# FR-1058 AC-320: 欄名の一覧が定義の外に重複して残らない（静的に確認。unit）
def test_ac320_field_name_list_is_not_duplicated_outside_definition():
    names = ["エンティティの使い方", "利用シナリオ", "関係する状態", "参照パラメータ", "関連する既存資産"]
    holders = {}
    for base in (SOURCE / "scripts", SOURCE / "EABK-Studio"):
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if "node_modules" in p.parts or "test" in p.name.lower():
                continue
            t = p.read_text(encoding="utf-8", errors="replace")
            if sum(n in t for n in names) >= 4:  # 欄名を並べた一覧
                holders[str(p.relative_to(SOURCE))] = True
    assert len(holders) <= 1, "欄名の一覧が複数のコードに重複している: " + ", ".join(sorted(holders))


# ============================================================================ FR-1059
def index_pairs(root):
    r = d.py(root, *RDC, "index", "--json")
    assert d.no_traceback(r) and r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


# FR-1059 AC-321: 索引は決定的で、保存されず、本文の参照と一致する
def test_ac321_index_deterministic_not_persisted_and_matches_text(repo):
    d.commit(repo, "snapshot")
    a = index_pairs(repo)
    b = index_pairs(repo)
    assert a == b, "2 回の生成結果が異なる"
    assert d.run(["git", "status", "--porcelain"], repo).stdout.strip() == "", "索引の生成がファイルを作った・変えた（二重管理）"
    got = {(x["from"], x["kind"], x["to"]) for x in a}
    assert ("FR-001", "上位", "G-001") in got and ("FR-002", "上位", "G-001") in got
    assert any(f == "FR-001" and k == "出典" for f, k, t in got) or any(k == "出典" for f, k, t in got)
    # 検証は台帳から: ケースは要求 FR-001 / AC-001 に結びつく
    led = json.loads(txt(repo, d.LEDGER))["cases"]
    for c in led:
        cid = c["id"]
        assert any(cid in (f, t) and k == "検証" for f, k, t in got), f"台帳のケース {cid} の「検証」の関係が索引にない"
    # 実装・使用はカタログから（行は「未実装」でも FR の行が存在すること）
    kinds = {k for _, k, _ in got}
    assert {"上位", "検証"} <= kinds


# FR-1059 AC-321 (異常系): 本文の参照を消すと索引から該当の組が消える（索引だけを根拠にしない）
def test_ac321_index_follows_text_when_reference_removed(repo):
    s = txt(repo, d.RD)
    i = s.index("#### FR-002 ")
    put(repo, d.RD, s[:i] + s[i:].replace("上位: G-001", "上位: G-002", 1))
    got = {(x["from"], x["kind"], x["to"]) for x in index_pairs(repo)}
    assert ("FR-002", "上位", "G-001") not in got, "本文を変えたのに索引が古い"


# FR-1059 AC-322: 逆引きが、索引を使わない独立の計算と同じ集合になる
def test_ac322_reverse_lookup_matches_independent_scan(repo):
    led = json.loads(txt(repo, d.LEDGER))["cases"]
    for rid in ("FR-001", "FR-002"):
        expected = {c["id"] for c in led if rid in c["requirement_ids"]}  # 台帳を直接走査（索引を使わない）
        assert expected, "前提: 台帳にケースがある"
        r = d.py(repo, *RDC, "trace", rid, "--json")
        assert d.no_traceback(r) and r.returncode == 0, r.stdout + r.stderr
        found = set(re.findall(r"\b(?:E2E|IT)-\d+\b", r.stdout))
        assert expected <= found, f"{rid} の逆引きに台帳のケースが欠けている: {expected - found}"
        assert not (found - expected), f"{rid} の逆引きに無関係なケースがある: {found - expected}"


# FR-1059 AC-322 (異常系): 存在しない ID の逆引きは落ちずに空（または未検出）を返す
def test_ac322_reverse_lookup_unknown_id_is_graceful(repo):
    r = d.py(repo, *RDC, "trace", "FR-" + "9999")
    assert d.no_traceback(r), r.stdout + r.stderr
    assert not re.findall(r"\b(?:E2E|IT)-\d+\b", r.stdout)


# ============================================================================ NFR-UX-014
# NFR-UX-014 AC-324: 同じ種類の表の列名・順序が違うと検査が列挙する
def test_ac324_table_column_mismatch_reported_and_clean_passes(repo):
    assert check(repo).returncode == 0
    cat = txt(repo, d.CATALOG)
    hdr = "| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |\n|---|---|---|---|---|---|\n"
    swapped = "| 要求 ID | 決定状態 | 題名 | 実装ファイル | テスト | 使っている共通部品 |\n|---|---|---|---|---|---|\n"
    extra = "\n#### 追加の機能表\n\n" + swapped + "| FR-001 | 承認済み | 注文の登録 | 未実装 | 未実装 | なし |\n"
    put(repo, d.CATALOG, cat.rstrip("\n") + "\n" + extra)
    r = check(repo)
    hit = [l for l in (lines(r, "ERROR") + lines(r, "WARN")) if "列" in l or "欄名" in l or "題名" in l or "決定状態" in l]
    assert hit, r.stdout + r.stderr


# ============================================================================ FR-1060 / NFR-UX-014
def add_assignment(root, pairs):
    """決定記録に領域の割り当て表（要求 ID・領域）を足す。"""
    s = txt(root, d.RD)
    tbl = "\n### 領域の割り当て表\n\n| 要求 ID | 領域 |\n|---|---|\n" + "".join(
        f"| {r} | {a} |\n" for r, a in pairs) + "\n"
    put(root, d.RD, s.replace("### 6.1 機能要求\n", tbl + "### 6.1 機能要求\n", 1))


def area_ready(root, pairs=(("FR-001", "受付"), ("FR-002", "照会"))):
    names = sorted({a for _, a in pairs})
    add_area_table(root, [(a, sum(1 for _, x in pairs if x == a)) for a in names])
    add_assignment(root, pairs)
    for r, a in pairs:
        set_area(root, r, a)


def chk(r, code, level):
    return [l for l in lines(r, level) if code in l]


def area_section(root, n):
    cat = txt(root, d.CATALOG)
    hdr = "| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |\n|---|---|---|---|---|---|\n"
    rows = "".join("| FR-001 | 注文の登録 | 承認済み | 未実装 | 未実装 | なし |\n" for _ in range(n))
    put(root, d.CATALOG, cat.rstrip("\n") + "\n\n#### 領域: 受付\n\n" + hdr + rows)


# NFR-UX-014 AC-323: 領域化済みの節だけ、直下の項目が PARAM-043(20) を超えると警告。20 件は警告なし
def test_ac323_area_section_over_limit_warns_at_boundary(repo):
    area_ready(repo)
    area_section(repo, 20)
    ok = check(repo)
    assert not chk(ok, "CHK-32", "WARN"), "20 件（上限ちょうど）で警告した:\n" + ok.stdout
    area_section_repo = repo  # 21 件へ
    cat = txt(repo, d.CATALOG)
    row = "| FR-001 | 注文の登録 | 承認済み | 未実装 | 未実装 | なし |\n"
    put(repo, d.CATALOG, cat.rstrip("\n") + "\n" + row)
    r = check(area_section_repo)
    hit = chk(r, "CHK-32", "WARN")
    assert hit and "領域: 受付" in hit[0] and "21" in hit[0], r.stdout + r.stderr
    assert not chk(r, "CHK-32", "ERROR"), "警告であって違反ではない"


# NFR-UX-014 AC-323 (異常系): 領域化の前（割り当て表なし）の節は 21 件以上でも警告しない
def test_ac323_before_area_assignment_no_warning(repo):
    area_section(repo, 25)
    r = check(repo)
    assert not chk(r, "CHK-32", "WARN"), r.stdout + r.stderr


# FR-1060 AC-326: 表と欄が一致していれば領域の違反なし
def test_ac326_consistent_table_and_fields_clean(repo):
    area_ready(repo)
    r = check(repo)
    bad = [l for l in lines(r, "ERROR") if "CHK-30" in l]
    assert not bad, "\n".join(bad)


# FR-1060 AC-326 (異常系): 値の不一致を位置つきで列挙する
def test_ac326_value_mismatch_reported_with_location(repo):
    area_ready(repo)
    s = txt(repo, d.RD)
    i = s.index("#### FR-001 ")
    j = s.index("- 領域: 受付", i)
    put(repo, d.RD, s[:j] + "- 領域: 照会" + s[j + len("- 領域: 受付"):])
    r = check(repo)
    hit = [l for l in chk(r, "CHK-30", "ERROR") if "FR-001" in l]
    assert r.returncode == 1 and hit and re.search(r"requirements-definition\.md:\d+", hit[0]), r.stdout + r.stderr


# FR-1060 AC-326 (異常系): 表にない要求・欄にない要求を列挙する
def test_ac326_missing_in_table_and_missing_field_reported(repo):
    area_ready(repo, (("FR-001", "受付"),))  # FR-002 は表にも欄にもない
    r = check(repo)
    hit = [l for l in chk(r, "CHK-30", "ERROR") if "FR-002" in l]
    assert r.returncode == 1 and len(hit) >= 2, r.stdout + r.stderr
    assert any("割り当て表" in l for l in hit) and any("欄" in l for l in hit), hit


# FR-1060 AC-326: 領域の名称を変えても要求・受入基準の ID は変わらない
def test_ac326_renaming_area_keeps_ids(repo):
    area_ready(repo)
    before = d.py(repo, *RDC, "list", "--area", "受付").stdout
    assert "FR-001" in before
    s = txt(repo, d.RD).replace("受付", "窓口")
    put(repo, d.RD, s)
    after = d.py(repo, *RDC, "list", "--area", "窓口").stdout
    assert "FR-001" in after and "FR-002" not in after, after
    r = check(repo)
    assert not [l for l in lines(r, "ERROR") if "CHK-30" in l], r.stdout
    ids = lambda t: sorted(set(re.findall(r"\b(?:FR-\d+|NFR-[A-Z0-9]+-\d+|AC-\d+)\b", t)))
    assert ids(s) == ids(txt(repo, d.RD))
