"""FR-1057 AC-315/316/317, FR-1058 AC-318/319/320, FR-1059 AC-321/322, NFR-UX-014 AC-323/324, FR-1060 AC-326 の
単体・結合テスト（階層化・メタデータ定義・関係の索引・情報デザイン）。"""
import json
import re
import sys
from pathlib import Path

from conftest import SOURCE

RD = "docs/requirements-definition.md"
CAT = "docs/catalog.md"
sys.path.insert(0, str(SOURCE / "scripts"))
import ebaklib as h  # noqa: E402


def lines(proc, level):
    return [l for l in proc.stdout.splitlines() if l.startswith(level)]


def check(sample):
    return sample.py("rdcheck.py", "check", "--base", "none")


def set_area(sample, rid, area):
    s = sample.read(RD)
    i = s.index(f"#### {rid} ")
    j = s.index("\n- 受入基準", i)
    sample.write(RD, s[:j] + f"\n- 領域: {area}" + s[j:])


def add_area_table(sample, rows):
    s = sample.read(RD)
    tbl = "### 領域一覧\n\n| 領域名 | 上位 G-ID | 含む要求数 |\n|---|---|---|\n" + "".join(
        f"| {a} | G-001 | {n} |\n" for a, n in rows) + "\n"
    sample.write(RD, s.replace("### 6.1 機能要求\n", tbl + "### 6.1 機能要求\n", 1))


def add_assignment(sample, rows):
    s = sample.read(RD)
    tbl = "\n### 領域の割り当て（決定記録）\n\n| 要求 ID | 領域 |\n|---|---|\n" + "".join(f"| {r} | {a} |\n" for r, a in rows)
    sample.write(RD, s.rstrip("\n") + "\n" + tbl)


# FR-1057 AC-315: 移行期（割り当て表なし）は未所属が違反にも警告にもならず、件数だけ情報で出る
def test_ac315_transition_unassigned_is_info_only(sample):
    proc = check(sample)
    assert proc.returncode == 0, proc.stdout
    assert not [l for l in lines(proc, "ERROR") + lines(proc, "WARN") if "領域" in l]
    assert any(l.startswith("INFO") and "領域未所属" in l for l in proc.stdout.splitlines())


# FR-1057 AC-315 / FR-1060 AC-326: 割り当て表の後は領域が必須で、表と欄の食い違いを位置つきで列挙する
def test_ac315_ac326_after_assignment_missing_and_mismatch_are_errors(sample):
    add_area_table(sample, [("受付", 1)])
    add_assignment(sample, [("FR-001", "照会")])
    proc = check(sample)
    errs = [l for l in lines(proc, "ERROR") if "CHK-30" in l]
    assert proc.returncode == 1 and any("FR-001" in l and "領域の欄がありません" in l for l in errs), proc.stdout
    set_area(sample, "FR-001", "受付")
    proc = check(sample)
    assert any("一致しません" in l and re.search(r"requirements-definition\.md:\d+", l) for l in lines(proc, "ERROR")), proc.stdout
    s = sample.read(RD).replace("| FR-001 | 照会 |", "| FR-001 | 受付 |")
    sample.write(RD, s)
    assert not [l for l in lines(check(sample), "ERROR") if "CHK-30" in l]


# FR-1057 AC-315: 領域の一覧表にない領域は違反。含む要求数の不一致は警告
def test_ac315_undefined_area_and_count_mismatch(sample):
    add_area_table(sample, [("受付", 3)])
    set_area(sample, "FR-001", "受付")
    proc = check(sample)
    assert any("含む要求数 3" in l for l in lines(proc, "WARN")), proc.stdout
    sample.write(RD, sample.read(RD).replace("- 領域: 受付", "- 領域: 未知"))
    proc = check(sample)
    assert any("未知" in l and "領域の一覧表にありません" in l for l in lines(proc, "ERROR")), proc.stdout


# FR-1057 AC-316: 領域で絞った一覧と、領域別の合計（廃止を除く）
def test_ac316_list_by_area(sample):
    add_area_table(sample, [("受付", 1)])
    set_area(sample, "FR-001", "受付")
    a = sample.py("rdcheck.py", "list", "--area", "受付")
    assert a.returncode == 0 and "FR-001" in a.stdout and "承認済み" in a.stdout
    b = sample.py("rdcheck.py", "list", "--by-area")
    assert "## 受付（1 件）" in b.stdout
    stats = json.loads(sample.py("rdcheck.py", "stats").stdout)["by_state"]
    total = sum(stats.get(k, 0) for k in ("承認済み", "承認待ち", "保留", "却下"))
    assert f"合計 {total} 件" in b.stdout


# FR-1057 AC-317: カタログの領域の区切りと要求定義書の領域が違うと不整合
def test_ac317_catalog_area_section_mismatch(sample):
    set_area(sample, "FR-001", "受付")
    cat = sample.read(CAT)
    sample.write(CAT, cat.replace("## 機能\n", "## 機能\n\n#### 領域: 照会\n", 1))
    errs = [l for l in lines(check(sample), "ERROR") if "CHK-30" in l and "FR-001" in l]
    assert errs and "照会" in errs[0] and "受付" in errs[0]
    sample.write(CAT, cat.replace("## 機能\n", "## 機能\n\n#### 領域: 受付\n", 1))
    assert not [l for l in lines(check(sample), "ERROR") if "CHK-30" in l]


# FR-1058 AC-318: 定義に無い欄・許容値外の値は位置つきで報告し、領域・更新日・版は任意の欄として通る
def test_ac318_unknown_field_and_value_outside(sample):
    s = sample.read(RD)
    j = s.index("\n- 受入基準", s.index("#### FR-001 "))
    sample.write(RD, s[:j] + "\n- 領域: 受付\n- 更新日: 2026-10-17\n- 版: 1" + s[j:])
    assert check(sample).returncode == 0
    sample.write(RD, s[:j] + "\n- 謎の欄: x" + s[j:])
    errs = [l for l in lines(check(sample), "ERROR") if "謎の欄" in l]
    assert errs and re.search(r"requirements-definition\.md:\d+", errs[0])
    sample.write(RD, s.replace("優先度: MUST", "優先度: ほぼ必須", 1))
    assert any("優先度" in l for l in lines(check(sample), "ERROR"))
    sample.write(RD, s[:j] + "\n- 更新日: 昨日" + s[j:])
    assert any("更新日" in l for l in lines(check(sample), "ERROR"))


# FR-1058 AC-318: 現行の要求定義書は初期定義の下で違反にならない
def test_ac318_repository_has_no_metadata_violation():
    from subprocess import run
    p = run([sys.executable, str(SOURCE / "scripts" / "rdcheck.py"), "check", "--base", "none"], cwd=SOURCE,
            capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert not [l for l in p.stdout.splitlines() if l.startswith("ERROR") and "CHK-29" in l]


# FR-1058 AC-320: 欄の定義は metadata.json が唯一の正本で、変更が検査に反映される
def test_ac320_definition_drives_required_fields_and_enum():
    defs = h.requirement_field_defs()
    assert {"領域", "更新日", "版"} <= set(defs) and not defs["領域"]["required"]
    assert h.required_requirement_fields() == [f["name"] for f in h.load_metadata()["requirement_fields"] if f["required"]]
    assert h.VERIFICATION_LEVELS == tuple(h.load_metadata()["ac_fields"][0]["allowed"])


# FR-1058 AC-320: 定義の変更（必須の追加）が検査にそのまま反映される
def test_ac320_definition_change_is_reflected(sample):
    meta = json.loads(sample.read("scripts/metadata.json"))
    for f in meta["requirement_fields"]:
        if f["name"] == "出典":
            f["required"] = True
    # 出典は FR-001 にあるので、必須の追加だけでは違反にならない。許容値の追加で確かめる
    for f in meta["requirement_fields"]:
        if f["name"] == "版":
            f["pattern"] = "^v\\d+$"
    sample.write("scripts/metadata.json", json.dumps(meta, ensure_ascii=False))
    s = sample.read(RD)
    j = s.index("\n- 受入基準", s.index("#### FR-001 "))
    sample.write(RD, s[:j] + "\n- 版: 1" + s[j:])
    assert any("版" in l for l in lines(check(sample), "ERROR"))


# FR-1059 AC-321: 索引は決定的で、保存されず、種類の出所が要求定義書・カタログ・台帳に分かれる
def test_ac321_index_kinds_and_determinism(sample):
    cat = sample.read(CAT)
    sample.write(CAT, cat.replace("| FR-001 | 入力の中断と再開 | 承認済み | 未実装 | 未実装 | なし |",
                                  "| FR-001 | 入力の中断と再開 | 承認済み | `src/a.py` | 未実装 | 入力部品 |"))
    sample.commit("snapshot")
    a = sample.py("rdcheck.py", "index", "--json").stdout
    assert a == sample.py("rdcheck.py", "index", "--json").stdout
    got = {(x["from"], x["kind"], x["to"]) for x in json.loads(a)}
    assert ("FR-001", "上位", "G-001") in got and ("FR-001", "出典", "依頼原文") in got
    assert ("FR-001", "参照", "PARAM-001") in got and ("AC-001", "参照", "PARAM-001") in got
    assert ("FR-001", "実装", "src/a.py") in got and ("FR-001", "使用", "入力部品") in got
    from conftest import run
    status = [l for l in run(["git", "status", "--porcelain"], sample.path).stdout.splitlines() if "__pycache__" not in l]
    assert status == []


# FR-1059 AC-321/322: 台帳の「検証」と逆引き（索引を使わない独立の走査と一致）
def test_ac322_reverse_lookup_matches_independent_scan(sample):
    sample.write("tests/system/ledger.json", json.dumps({"version": 1, "ac_digests": {}, "cases": [
        {"id": "E2E-001", "ac_ids": ["AC-001"], "requirement_ids": ["FR-001"], "status": "not_run"},
        {"id": "IT-001", "ac_ids": ["AC-002"], "requirement_ids": ["FR-001"], "status": "not_run"}]}))
    out = json.loads(sample.py("rdcheck.py", "index", "FR-001", "--kind", "検証", "--json").stdout)
    ledger = json.loads(sample.read("tests/system/ledger.json"))["cases"]
    expected = {c["id"] for c in ledger if "FR-001" in c["requirement_ids"]}
    assert {x["from"] for x in out} == expected
    ac = json.loads(sample.py("rdcheck.py", "index", "AC-001", "--kind", "検証", "--json").stdout)
    assert {x["from"] for x in ac} == {"E2E-001"}


# NFR-UX-014 AC-323: 領域に分けられた節だけが上限（PARAM-043）を超えると警告。領域化の前は警告しない
def test_ac323_section_limit_warns_only_after_assignment(sample):
    rows = "".join(f"| FR-9{i:02d} | x |\n" for i in range(25))
    body = "\n#### 領域: 多い\n\n| 要求 ID | 領域 |\n|---|---|\n" + rows
    cat = sample.read(CAT)
    sample.write(CAT, cat.rstrip("\n") + "\n" + body)
    assert not [l for l in lines(check(sample), "WARN") if "CHK-32" in l]
    set_area(sample, "FR-001", "多い")
    add_assignment(sample, [("FR-001", "多い")])
    warns = [l for l in lines(check(sample), "WARN") if "CHK-32" in l]
    assert warns and "領域: 多い" in warns[0] and "20" in warns[0]


# NFR-UX-014 AC-324: 同じ種類の表の列名・順序が違うと列挙する
def test_ac324_column_mismatch_reported(sample):
    assert not [l for l in lines(check(sample), "WARN") if "CHK-31" in l]
    cat = sample.read(CAT)
    extra = ("\n#### 追加の機能表\n\n| 要求 ID | 決定状態 | 題名 | 実装ファイル | テスト | 使っている共通部品 |\n"
             "|---|---|---|---|---|---|\n| FR-001 | 承認済み | 入力の中断と再開 | 未実装 | 未実装 | なし |\n")
    sample.write(CAT, cat.rstrip("\n") + "\n" + extra)
    warns = [l for l in lines(check(sample), "WARN") if "CHK-31" in l]
    assert warns and "列名" in warns[0]
