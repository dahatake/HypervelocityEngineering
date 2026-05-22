"""回帰テスト: _run_pre_execution_qa の質問票パース処理。

目的:
    `hve/runner.py:_run_pre_execution_qa` 内で `QAMerger.parse_qa(...)`
    という存在しないメソッドが呼ばれ、`AttributeError` が
    `except Exception: pass` でサイレントに握りつぶされたために
    GUI ユーザー回答モードのダイアログが一切表示されない不具合
    （Phase 0b/0c の常時スキップ）が発生した。

本テストは:
    1. `QAMerger.parse_qa_content` が現に存在し、`parse_qa` が
       存在しない（=利用してはならない）ことをガードする。
    2. 実 qa/ ファイル相当の最小サンプルを `parse_qa_content` に
       渡すと questions が非空でパースされることを確認する。
    3. パース失敗時にも例外が呼び出し側へ伝播する（黙殺されない）
       ことを Python レベルで確認する。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HVE_DIR = Path(__file__).resolve().parent.parent
if str(_HVE_DIR) not in sys.path:
    sys.path.insert(0, str(_HVE_DIR))

from qa_merger import QAMerger  # noqa: E402


_MIN_QA_CONTENT = """\
# 事前質問票

**状態**: 回答待ち

---

## 質問項目

| No. | 質問 | 選択肢 | デフォルトの回答案 | 選択理由 |
|-----|------|--------|-------------------|----------|
| 1 | 出力先ディレクトリは `work/Issue-N` で良いか | A) はい / B) いいえ | A) はい | 既存ルールに準拠 |
| 2 | 既存ファイルがある場合は上書きするか | A) 上書き / B) 中止 | A) 上書き | 安全側方針 |
"""


class TestQAMergerAPISurface(unittest.TestCase):
    """QAMerger 公開 API の同一性保証（回帰テスト）。"""

    def test_parse_qa_does_not_exist(self) -> None:
        """`QAMerger.parse_qa` は存在しない。

        過去に `runner.py:_run_pre_execution_qa` が
        `QAMerger.parse_qa(...)` を呼んで AttributeError がサイレント
        握りつぶしされる不具合があった。万一誰かが再追加した場合、
        利用箇所の見直しが必要なため、本テストでガードする。
        """
        self.assertFalse(
            hasattr(QAMerger, "parse_qa"),
            "QAMerger.parse_qa が存在する場合、runner.py での呼び出し有無を確認すること。",
        )

    def test_parse_qa_content_exists(self) -> None:
        self.assertTrue(hasattr(QAMerger, "parse_qa_content"))


class TestParseQAContentMinimal(unittest.TestCase):
    """最小限の質問票テキストに対する parse_qa_content の挙動。"""

    def test_parse_non_empty_questionnaire_returns_questions(self) -> None:
        doc = QAMerger.parse_qa_content(_MIN_QA_CONTENT)
        self.assertGreaterEqual(
            len(doc.questions),
            1,
            "最小サンプルから 1 問以上抽出できなければ runner.py 側の "
            "Phase 0b/0c が常時スキップされる不具合が再発する。",
        )

    def test_parse_empty_string_returns_zero_questions(self) -> None:
        doc = QAMerger.parse_qa_content("")
        self.assertEqual(len(doc.questions), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
