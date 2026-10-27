"""FR-011 AC-431 / AC-432: the i18n dictionary is complete, and no user-visible text is hard-coded (static checks, no browser).

AC-431: every key used by data-i18n* / t() exists in both ja and en, is non-empty, and has the same {placeholders} in both.
AC-432: index.html and web/js/*.js carry no hard-coded Japanese literal (outside comments, the dictionary itself and
        lines marked `i18n-data` = managed-data keys); index.html has no visible text or title / aria-label / placeholder
        outside the dictionary attributes.
"""
import re

import pytest

import i18n_scan as S

PH = re.compile(r"\{(\w+)\}")


@pytest.fixture(scope="module")
def dicts():
    return S.load_dict()


# FR-011 AC-431: ja と en のキー集合が一致する。
def test_ac431_ja_and_en_have_the_same_keys(dicts):
    ja, en = set(dicts["ja"]), set(dicts["en"])
    assert not (ja - en), f"en にないキー: {sorted(ja - en)[:10]}"
    assert not (en - ja), f"ja にないキー: {sorted(en - ja)[:10]}"


# FR-011 AC-431: 値が空でない。
def test_ac431_values_are_not_empty(dicts):
    empty = [(lg, k) for lg in ("ja", "en") for k, v in dicts[lg].items() if not str(v).strip()]
    assert not empty, f"空の値: {empty[:10]}"


# FR-011 AC-431: プレースホルダー（{n} など）が両言語で一致する。
def test_ac431_placeholders_match(dicts):
    bad = [k for k in dicts["ja"] if k in dicts["en"] and set(PH.findall(dicts["ja"][k])) != set(PH.findall(dicts["en"][k]))]
    assert not bad, f"プレースホルダー不一致: {bad[:10]}"


# FR-011 AC-431: 同じ言語ブロックの中で同じキーを二重に定義しない（後ろが前を黙って上書きするのを防ぐ）。
def test_ac431_no_duplicate_keys_in_a_block():
    src = (S.WEB / "js" / "i18n.js").read_text(encoding="utf-8")
    start = src.index("const D = {")
    end = src.index("\n};", start)
    body = src[start:end]
    cut = body.index("\n  en: {")
    dup = []
    for name, block in (("ja", body[:cut]), ("en", body[cut:])):
        keys = re.findall(r"""['"]([\w.\-]+)['"]\s*:""", block)
        dup += [(name, k) for k in {k for k in keys if keys.count(k) > 1}]
    assert not dup, f"重複キー: {dup[:10]}"


# FR-011 AC-431: t() と data-i18n* が参照するキー（動的に続くものは接頭辞）が、辞書の ja と en の両方にある。
def test_ac431_every_referenced_key_exists_in_both_languages(dicts):
    keys, prefixes = S.used_keys()
    missing = [(k, where) for k, where in keys.items() if k not in dicts["ja"] or k not in dicts["en"]]
    assert not missing, f"辞書にないキー: {missing[:10]}"
    nopref = [(p, where) for p, where in prefixes.items() if not any(k.startswith(p) for k in dicts["ja"]) or not any(k.startswith(p) for k in dicts["en"])]
    assert not nopref, f"辞書にない接頭辞: {nopref[:10]}"


# FR-011 AC-430/AC-432: en の値に日本語が残らない（管理データの語は辞書に入れない）。
def test_ac430_english_values_have_no_japanese(dicts):
    bad = [k for k, v in dicts["en"].items() if S.JP.search(v) and not k.endswith(".keys")]   # *.keys = search keywords, matched in both languages
    assert not bad, f"en に日本語: {bad[:10]}"


# FR-011 AC-432: js に日本語の文字列リテラルの直書きがない（辞書 i18n.js・コメント・正規表現・`i18n-data` の行を除く）。
@pytest.mark.parametrize("path", [f for f in S.JS_FILES if f.name != "i18n.js"], ids=lambda p: p.name)
def test_ac432_no_hardcoded_japanese_in_js(path):
    found = S.hardcoded_js(path)
    assert not found, f"{path.name}: 日本語の直書き {[(l, t[:30]) for l, t in found[:8]]}"


# FR-011 AC-432: index.html に直書きの表示文言・title・aria-label・placeholder がない。
def test_ac432_index_html_has_no_hardcoded_text():
    found = S.html_scan().found
    assert not found, f"index.html の直書き: {found[:10]}"


# FR-011 AC-432: 検査自身の確認（直書きを見つけ、印のある行・コメント・正規表現は見逃す）。
def test_ac432_scanner_detects_hardcoded_text(tmp_path):
    f = tmp_path / "x.js"
    f.write_text("const a = '日本語';\nconst b = `x${y}保存`; // 注釈\nconst c = /日本/;\nconst d = '要求'; // i18n-data\n"
                 "// i18n-data\nconst e = '未分類';\n/* 説明 */ const f = t('k');\n", encoding="utf-8")
    assert [l for l, _ in S.hardcoded_js(f)] == [1, 2]
