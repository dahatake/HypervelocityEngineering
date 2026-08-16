"""materialize_answered_qa.py の TDD RED テスト。

FR-QA-03 / FR-CLOUD-24: 構造化質問票＋手動回答 → 回答済み Markdown を
固定ファイル名で生成するモジュールの契約テスト。

想定する最小公開 API:
    materialize_answered_qa.materialize(
        questionnaire_md: str,   # 構造化 [Q01] 質問票 Markdown
        answer_text: str,        # ユーザー回答テキスト ("1: A\\n2: B")
        issue_number: int,       # Issue 番号
        *,
        use_defaults: bool = False,  # True → 全質問に既定値を採用
    ) -> MaterializeResult

    @dataclass
    MaterializeResult:
        filename: str        # Issue-N-questionnaire-answered-sha8.md
        content: str         # 回答済み Markdown 本文
        appendix: str        # 付録 (原質問票 + 回答コメント)

hve.qa_merger を再利用する前提。ネットワーク不要。
"""

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# production module が未実装でも import エラーでテストが RED になることを確認
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from materialize_answered_qa import MaterializeResult, materialize  # type: ignore[import-not-found]

# ---------------------------------------------------------------------------
# テスト用フィクスチャ
# ---------------------------------------------------------------------------

SAMPLE_QUESTIONNAIRE = """\
# APP-001 事前 QA 質問票

**状態**: 回答待ち
**推論許可**: なし

---

[Q01]
- 分類項目: アーキテクチャ
- 重要度: 最重要
- 質問内容: マイクロサービス分割はどうしますか？
- 選択肢:
  A) サービス分割
  B) モノリス維持
- 既定値候補: A
- 既定値候補の理由: スケーラビリティ優先
- 背景と根拠: 現行はモノリス構成
- 判断の観点: スケーラビリティ vs 運用コスト

[Q02]
- 分類項目: データ
- 重要度: 高
- 質問内容: データベースエンジンは何を使いますか？
- 選択肢:
  A) Cosmos DB
  B) Azure SQL
  C) PostgreSQL
- 既定値候補: A
- 既定値候補の理由: グローバル分散が必要
- 背景と根拠: リージョン横断要件あり
- 判断の観点: 分散 vs コスト vs SQL 互換性

[Q03]
- 分類項目: 認証
- 重要度: 中
- 質問内容: 認証方式は？
- 選択肢:
  A) Entra ID
  B) カスタム認証
- 既定値候補: A
- 既定値候補の理由: 標準準拠
- 背景と根拠: 社内 SSO 統合が前提
- 判断の観点: セキュリティ vs カスタマイズ性
"""

SAMPLE_ANSWERS = """\
1: B
2: A
3:: Entra ID + カスタムクレーム拡張
"""

# 既定値を持たない質問を含む質問票
QUESTIONNAIRE_NO_DEFAULT = """\
# QA 質問票

**状態**: 回答待ち
**推論許可**: なし

---

[Q01]
- 分類項目: セキュリティ
- 重要度: 最重要
- 質問内容: 暗号化方式は？
- 選択肢:
  A) AES-256
  B) RSA
- 既定値候補:
- 既定値候補の理由:
- 背景と根拠: 規制要件による
- 判断の観点: パフォーマンス vs 安全性
"""

QUESTIONNAIRE_ZERO_QUESTIONS = """\
# QA 質問票

**状態**: 回答待ち
**推論許可**: なし

---

質問はありません。
"""


def _sha8(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# テストケース
# ---------------------------------------------------------------------------


class TestMaterializeBasic(unittest.TestCase):
    """構造化質問票＋手動回答 → 回答済み Markdown 変換。"""

    def test_basic_merge(self):
        result = materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=42)
        self.assertIsInstance(result, MaterializeResult)
        self.assertIn("回答済み", result.content)
        from hve.qa_merger import QAMerger
        reparsed = QAMerger.parse_qa_content(result.content)
        self.assertEqual(len(reparsed.questions), 3)
        self.assertTrue(all(q.user_answer for q in reparsed.questions))

    def test_all_answers_present_in_content(self):
        result = materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=42)
        # Q01 は "B) モノリス維持" が回答
        self.assertIn("モノリス維持", result.content)
        # Q02 は "A) Cosmos DB"
        self.assertIn("Cosmos DB", result.content)
        # Q03 は自由記述
        self.assertIn("Entra ID + カスタムクレーム拡張", result.content)


class TestFilenameContract(unittest.TestCase):
    """FR-CLOUD-24: 固定ファイル名 Issue-N-questionnaire-answered-sha8.md。"""

    def test_filename_format(self):
        result = materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=42)
        pattern = r"^Issue-42-questionnaire-answered-[0-9a-f]{8}\.md$"
        self.assertRegex(result.filename, pattern)

    def test_sha8_matches_content(self):
        result = materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=42)
        expected_sha8 = _sha8(result.content)
        actual_sha8 = result.filename.split("-")[-1].replace(".md", "")
        self.assertEqual(expected_sha8, actual_sha8)

    def test_deterministic_filename(self):
        r1 = materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=7)
        r2 = materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=7)
        self.assertEqual(r1.filename, r2.filename)
        self.assertEqual(r1.content, r2.content)

    def test_different_issue_different_filename(self):
        r1 = materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=10)
        r2 = materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=20)
        self.assertNotEqual(r1.filename, r2.filename)


class TestDefaultCompletion(unittest.TestCase):
    """未回答は既定値で補完。"""

    def test_unanswered_filled_with_default(self):
        # Q03 だけ回答なし → 既定値 "A" で補完
        partial_answers = "1: B\n2: A\n"
        result = materialize(SAMPLE_QUESTIONNAIRE, partial_answers, issue_number=1)
        from hve.qa_merger import QAMerger
        reparsed = QAMerger.parse_qa_content(result.content)
        self.assertEqual(reparsed.questions[2].user_answer, "A) Entra ID")


class TestAutoDefaultMarker(unittest.TestCase):
    """自動デフォルト回答マーカーで全既定値採用。"""

    def test_use_defaults_flag(self):
        result = materialize(
            SAMPLE_QUESTIONNAIRE, "", issue_number=5, use_defaults=True
        )
        from hve.qa_merger import QAMerger
        reparsed = QAMerger.parse_qa_content(result.content)
        self.assertEqual(
            [q.user_answer for q in reparsed.questions],
            ["A) サービス分割", "A) Cosmos DB", "A) Entra ID"],
        )

    def test_use_defaults_with_empty_answers(self):
        result = materialize(
            SAMPLE_QUESTIONNAIRE, "", issue_number=5, use_defaults=True
        )
        self.assertIsInstance(result, MaterializeResult)
        self.assertTrue(result.content.strip())


class TestFailClosed(unittest.TestCase):
    """回答も既定値もない質問は fail-closed。"""

    def test_no_answer_no_default_raises(self):
        with self.assertRaises(ValueError):
            materialize(QUESTIONNAIRE_NO_DEFAULT, "", issue_number=1)

    def test_no_answer_no_default_with_use_defaults_raises(self):
        with self.assertRaises(ValueError):
            materialize(
                QUESTIONNAIRE_NO_DEFAULT, "", issue_number=1, use_defaults=True
            )


class TestZeroQuestions(unittest.TestCase):
    """質問 0 件は同期不要。"""

    def test_zero_questions_returns_none(self):
        result = materialize(QUESTIONNAIRE_ZERO_QUESTIONS, "", issue_number=1)
        self.assertIsNone(result)


class TestInputValidation(unittest.TestCase):
    """Issue 番号不正・パストラバーサル不可。"""

    def test_negative_issue_number(self):
        with self.assertRaises(ValueError):
            materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=-1)

    def test_zero_issue_number(self):
        with self.assertRaises(ValueError):
            materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=0)

    def test_path_traversal_in_issue_number_string(self):
        # issue_number は int だが、生成されたファイル名がパストラバーサルを含まないこと
        result = materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=999999)
        self.assertNotIn("..", result.filename)
        self.assertNotIn("/", result.filename)
        self.assertNotIn("\\", result.filename)

    def test_unknown_question_number_rejected(self):
        with self.assertRaises(ValueError):
            materialize(SAMPLE_QUESTIONNAIRE, "99: A", issue_number=1)

    def test_duplicate_question_number_rejected(self):
        with self.assertRaises(ValueError):
            materialize(SAMPLE_QUESTIONNAIRE, "1: A\n1: B", issue_number=1)


class TestLineEndingNormalization(unittest.TestCase):
    def test_lf_and_crlf_produce_identical_content_and_filename(self):
        lf = materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=42)
        crlf = materialize(
            SAMPLE_QUESTIONNAIRE.replace("\n", "\r\n"),
            SAMPLE_ANSWERS.replace("\n", "\r\n"),
            issue_number=42,
        )
        self.assertEqual(lf.content, crlf.content)
        self.assertEqual(lf.filename, crlf.filename)


class TestReparse(unittest.TestCase):
    """FR-QA-03: 出力を再 parse して全質問の user_answer が非空。"""

    def test_reparse_all_answers_nonempty(self):
        result = materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=42)

        # hve.qa_merger で再パースし、全質問の user_answer が非空であることを検証
        # これは FR-QA-03 の「最終パスを再読込して内容・質問数・各質問の非空回答を検証」に対応
        sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
        from hve.qa_merger import QAMerger

        reparsed = QAMerger.parse_qa_content(result.content)
        self.assertGreater(len(reparsed.questions), 0)
        for q in reparsed.questions:
            with self.subTest(question_no=q.no):
                self.assertTrue(
                    q.user_answer,
                    f"Q{q.no:02d} の user_answer が空です",
                )


class TestAppendix(unittest.TestCase):
    """FR-CLOUD-24: 原質問票と回答コメントを付録へ保存。"""

    def test_appendix_contains_original(self):
        result = materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=42)
        self.assertIn("APP-001 事前 QA 質問票", result.appendix)

    def test_appendix_contains_answers(self):
        result = materialize(SAMPLE_QUESTIONNAIRE, SAMPLE_ANSWERS, issue_number=42)
        self.assertIn("1: B", result.appendix)
        self.assertIn("2: A", result.appendix)
        self.assertIn("3:: Entra ID + カスタムクレーム拡張", result.appendix)
        self.assertIn(result.appendix, result.content)


class TestCliFileOutput(unittest.TestCase):
    def test_cli_writes_valid_utf8_lf_file_and_reports_full_sha(self):
        script = SCRIPTS_DIR / "materialize_answered_qa.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            questionnaire = root / "questionnaire.md"
            answers = root / "answers.md"
            output = root / "qa"
            questionnaire.write_text(
                "\ufeff" + SAMPLE_QUESTIONNAIRE.replace("\n", "\r\n"),
                encoding="utf-8",
            )
            answers.write_text(
                "\ufeff" + SAMPLE_ANSWERS.replace("\n", "\r\n"),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--questionnaire-file", str(questionnaire),
                    "--answer-file", str(answers),
                    "--issue-number", "42",
                    "--output-dir", str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            written = Path(payload["path"]).read_bytes()
            self.assertFalse(written.startswith(b"\xef\xbb\xbf"))
            self.assertNotIn(b"\r\n", written)
            self.assertEqual(hashlib.sha256(written).hexdigest(), payload["sha256"])


if __name__ == "__main__":
    unittest.main()
