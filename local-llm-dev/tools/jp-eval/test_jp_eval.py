"""判定ロジックの回帰テスト。

敵対的レビューで発見した誤判定を再発させないための最小限のテスト。
    python test_jp_eval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jp_eval import (
    check_instruction,
    final_answer,
    jp_metrics,
    strip_code_blocks,
    variant_comparability_errors,
)

FAILURES: list[str] = []


def check(name: str, actual, expected) -> None:
    if actual == expected:
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name}: expected={expected!r} actual={actual!r}")
        FAILURES.append(name)


def test_heading_not_confused_with_python_comment() -> None:
    """コードフェンス内の `# コメント` を Markdown 見出しと誤検出しないこと。"""
    answer = (
        "重複を除去するには set を使います。\n\n"
        "```python\n"
        "# リストの重複を除去する\n"
        "def dedupe(items):\n"
        "    return list(dict.fromkeys(items))\n"
        "```\n"
    )
    check("見出しなし判定（コード内コメントを無視）",
          check_instruction({"expects_code": True}, answer)["r2_no_heading"], True)


def test_real_heading_is_detected() -> None:
    """本物の Markdown 見出しは検出されること（修正が緩すぎないことの確認）。"""
    answer = "## 手順\n\n次のようにします。\n"
    check("見出しあり判定", check_instruction({}, answer)["r2_no_heading"], False)


def test_heading_inside_unclosed_fence_ignored() -> None:
    """閉じられていないフェンス以降も コード扱いされること。"""
    answer = "説明です。\n\n```python\n# 途中で切れた\nprint(1)\n"
    check("未閉じフェンス内を無視", check_instruction({}, answer)["r2_no_heading"], True)


def test_unclosed_think_is_stripped() -> None:
    """`</think>` が欠けた打ち切り出力でも推論トレースを最終回答に含めないこと。"""
    body = {"message": {"content": "<think>Let me think about this in English at length"}}
    check("未閉じ think を除去", final_answer(body), "")


def test_closed_think_is_stripped() -> None:
    body = {"message": {"content": "<think>reasoning</think>\n回答です。"}}
    check("閉じた think を除去", final_answer(body), "回答です。")


def test_japanese_kanji_not_flagged_as_simplified() -> None:
    """「点」「会」「来」は日本語漢字であり簡体字混入と判定しないこと。"""
    m = jp_metrics("このコードの問題点は、会社の来期の計画に関係します。")
    check("日本語漢字を簡体字と誤検出しない", m["has_simplified_chinese"], False)


def test_actual_simplified_is_flagged() -> None:
    """実際の簡体字は検出されること。"""
    m = jp_metrics("这是一个说明です。ひらがなもあります。")
    check("簡体字を検出", m["has_simplified_chinese"], True)


def test_is_japanese_threshold() -> None:
    check("英語のみは日本語でない", jp_metrics("This is an English answer.")["is_japanese"], False)
    check("日本語は日本語と判定", jp_metrics("これは日本語の回答です。")["is_japanese"], True)


def test_strip_code_blocks() -> None:
    check("コードブロック除去", strip_code_blocks("a\n```py\nx=1\n```\nb").strip(), "a\n\nb".strip())


def test_rules_not_applicable_are_none() -> None:
    """適用外のルールは None になり、集計から除外されること。"""
    rules = check_instruction({}, "回答です。")
    check("r3 適用外", rules["r3_unknown"], None)
    check("r4 適用外", rules["r4_python_fence"], None)


def test_variants_are_comparable() -> None:
    """否定形と肯定形が同じ判定条件を指示していること。

    判定が特定の語の出現を見る以上、片方のバリアントだけがその語を指示していると、
    もう片方は構造的に合格できず、否定形 vs 肯定形の比較が無効になる。
    実際に B-2 の初回測定はこの欠陥で「肯定形が優れる」という誤った結論を出した。
    """
    spec = json.loads((Path(__file__).resolve().parent / "prompts.json").read_text("utf-8"))
    check("バリアントの比較可能性", variant_comparability_errors(spec), [])


def test_comparability_check_detects_asymmetry() -> None:
    """検査が緩すぎないこと（判定語を欠いたバリアントを実際に検出できる）。"""
    broken = {"instruction_variants": {
        "negative": "推測で書いてはならない。コードにフェンスを付けよ。",
        "positive": "知らないことは「不明」と書く。コードは python フェンスに入れる。",
    }}
    errs = variant_comparability_errors(broken)
    check("非対称なバリアントを検出する", len(errs), 2)


def main() -> int:
    for fn in sorted(
        (v for k, v in globals().items() if k.startswith("test_") and callable(v)),
        key=lambda f: f.__name__,
    ):
        print(fn.__name__)
        fn()
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} 件 -> {FAILURES}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
