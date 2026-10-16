"""データ層の確認・修復のコマンド（rdfix.py --full）の結合テストの入口
（FR-1046 AC-242/243、NFR-REL-002 AC-244/245/246/247、NFR-REL-003 AC-248/249/250、
NFR-REL-004 AC-251/252/253、NFR-PERF-005 AC-254/255）。

本体は tests/toolkit/test_rdfix_full.py と tests/toolkit/test_rdfix_robust.py（導入先を模した使い捨てのリポジトリで、
rdfix・verify・install を実際に実行し、故障と壊れた入力はテストの側から注入する）。tests/toolkit は要求 ID の走査の
対象外なので、要求 ID と受入基準 ID をこのファイルに書いて、要求からテストをたどれるようにする。
本体の実行は `python -m pytest -q tests/toolkit/test_rdfix_full.py tests/toolkit/test_rdfix_robust.py`（数分かかるため verify.commands には
入れない。導入先に配る設定にもなるため）。ここでは pytest を入れ子で起動せず、本体のテストが受入基準ごとに存在することを数ミリ秒で確かめる。
"""
import ast
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parents[1] / "toolkit"

# FR-1046 AC-242 AC-243 / NFR-REL-002 AC-244 AC-245 AC-246 AC-247 / NFR-REL-003 AC-248 AC-249 AC-250
# NFR-REL-004 AC-251 AC-252 AC-253 / NFR-PERF-005 AC-254 AC-255
EXPECTED = {
    "test_rdfix_full.py": 15,
    "test_rdfix_robust.py": 7,
}
AC_TESTS = {
    "AC-251": "test_broken_input_is_manual_and_untouched",
    "AC-252": "test_bom_and_line_endings_are_kept",
    "AC-253": "test_directory_that_is_not_a_git_repository",
    "AC-254": "test_clean_data_layer_one_inspection_zero_writes",
    "AC-255": "test_repair_inspection_count_within_rounds_plus_one",
}


def _tests(name: str):
    tree = ast.parse((TOOLKIT / name).read_text(encoding="utf-8"))
    return [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]


def test_data_layer_repair_suite_is_present():
    for name, minimum in EXPECTED.items():
        found = _tests(name)
        assert len(found) >= minimum, f"{name}: テストが {len(found)} 件しかありません（{minimum} 件以上が必要）"
    robust = _tests("test_rdfix_robust.py")
    for ac, test in AC_TESTS.items():
        assert test in robust, f"{ac} のテスト {test} が tests/toolkit/test_rdfix_robust.py にありません"
