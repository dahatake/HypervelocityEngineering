"""test_qa_merger.py — QAMerger のユニットテスト"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qa_merger import Choice, QADocument, QAMerger, QAQuestion

_FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# フィクスチャ文字列
# ---------------------------------------------------------------------------

_5COL_CONTENT = """\
# テスト質問票

**状態**: 回答待ち
**推論許可**: なし
**対象PR**: テスト用
**作成日**: 2026-04-01

---

## 質問項目

| No. | 質問 | 選択肢 | デフォルトの回答案 | 選択理由 |
|-----|------|--------|-------------------|----------|
| 1 | SVC-02とSVC-03を別サービスとして分割する方針は正しいか | A) 別サービス維持 / B) 統合 | A) 別サービス維持 | domain-analytics.md §BC-02 に基づく |
| 2 | サービス間の通信方式はどれか | A) REST/HTTP / B) gRPC / C) 混在 | A) REST/HTTP | チーム習熟度を優先 |
| 3 | データストアの選定はどれか | A) Azure SQL / B) Cosmos DB / C) TBD | C) TBD | アーキテクチャ決定待ち |

---

## 回答方法

以下のいずれかを選択してください：
"""

_6COL_CONTENT = """\
# テスト質問票（マージ済み）

**状態**: 回答済み
**推論許可**: なし

---

## 質問項目

| No. | 質問 | 選択肢 | デフォルトの回答案 | 選択理由 | ユーザー回答 |
|-----|------|--------|-------------------|----------|------------|
| 1 | SVC-02とSVC-03を別サービスとして分割する方針は正しいか | A) 別サービス維持 / B) 統合 | A) 別サービス維持 | domain-analytics.md §BC-02 に基づく | A) 別サービス維持 |
| 2 | サービス間の通信方式はどれか | A) REST/HTTP / B) gRPC / C) 混在 | A) REST/HTTP | チーム習熟度を優先 | B) gRPC |
| 3 | データストアの選定はどれか | A) Azure SQL / B) Cosmos DB / C) TBD | C) TBD | アーキテクチャ決定待ち | C) TBD |
"""


# ---------------------------------------------------------------------------
# テストクラス
# ---------------------------------------------------------------------------

class TestParseQaContent5Columns(unittest.TestCase):
    """5列テーブルのパース"""

    def setUp(self):
        self.doc = QAMerger.parse_qa_content(_5COL_CONTENT)

    def test_title_parsed(self):
        self.assertEqual(self.doc.title, "テスト質問票")

    def test_status_parsed(self):
        self.assertEqual(self.doc.status, "回答待ち")

    def test_inference_permission_parsed(self):
        self.assertEqual(self.doc.inference_permission, "なし")

    def test_question_count(self):
        self.assertEqual(len(self.doc.questions), 3)

    def test_question_numbers(self):
        nos = [q.no for q in self.doc.questions]
        self.assertEqual(nos, [1, 2, 3])

    def test_question_text(self):
        self.assertIn("SVC-02", self.doc.questions[0].question)

    def test_user_answer_is_none(self):
        for q in self.doc.questions:
            self.assertIsNone(q.user_answer)

    def test_default_answer_q1(self):
        self.assertEqual(self.doc.questions[0].default_answer, "A) 別サービス維持")

    def test_reason_q2(self):
        self.assertIn("チーム習熟度", self.doc.questions[1].reason)


class TestParseQaContent6Columns(unittest.TestCase):
    """マージ済み6列テーブルのパース"""

    def setUp(self):
        self.doc = QAMerger.parse_qa_content(_6COL_CONTENT)

    def test_status_is_answered(self):
        self.assertEqual(self.doc.status, "回答済み")

    def test_user_answer_q1(self):
        self.assertEqual(self.doc.questions[0].user_answer, "A) 別サービス維持")

    def test_user_answer_q2(self):
        self.assertEqual(self.doc.questions[1].user_answer, "B) gRPC")

    def test_user_answer_q3(self):
        self.assertEqual(self.doc.questions[2].user_answer, "C) TBD")

    def test_question_count(self):
        self.assertEqual(len(self.doc.questions), 3)


class TestParseChoices(unittest.TestCase):
    """選択肢 A) xxx / B) xxx を List[Choice] に変換"""

    def test_two_choices(self):
        choices = QAMerger._parse_choices("A) 別サービス維持 / B) 統合")
        self.assertEqual(len(choices), 2)
        self.assertEqual(choices[0].label, "A")
        self.assertEqual(choices[0].text, "別サービス維持")
        self.assertEqual(choices[1].label, "B")
        self.assertEqual(choices[1].text, "統合")

    def test_three_choices(self):
        choices = QAMerger._parse_choices("A) REST/HTTP / B) gRPC / C) 混在")
        self.assertEqual(len(choices), 3)
        self.assertEqual(choices[2].label, "C")
        self.assertEqual(choices[2].text, "混在")

    def test_empty_string(self):
        choices = QAMerger._parse_choices("")
        self.assertEqual(choices, [])

    def test_choice_with_parentheses(self):
        choices = QAMerger._parse_choices("A) 別サービス維持（現行）/ B) 統合")
        self.assertEqual(len(choices), 2)
        self.assertEqual(choices[0].text, "別サービス維持（現行）")


class TestParseAnswersFull(unittest.TestCase):
    """全問回答ありの回答テキストをパース"""

    def test_full_answers(self):
        text = "1: A\n2: B\n3: C"
        answers = QAMerger.parse_answers(text)
        self.assertEqual(answers, {1: "A", 2: "B", 3: "C"})

    def test_case_insensitive(self):
        answers = QAMerger.parse_answers("1: a\n2: b")
        self.assertEqual(answers[1], "A")
        self.assertEqual(answers[2], "B")


class TestParseAnswersPartial(unittest.TestCase):
    """部分回答のパース"""

    def test_partial_answers(self):
        text = "1: A\n3: C"
        answers = QAMerger.parse_answers(text)
        self.assertEqual(len(answers), 2)
        self.assertIn(1, answers)
        self.assertNotIn(2, answers)
        self.assertIn(3, answers)


class TestParseAnswersWithComments(unittest.TestCase):
    """コメント行・空行を含む回答テキスト"""

    def test_comments_ignored(self):
        text = "# コメント\n1: A\n\n# 別コメント\n2: B"
        answers = QAMerger.parse_answers(text)
        self.assertEqual(answers, {1: "A", 2: "B"})

    def test_empty_text(self):
        answers = QAMerger.parse_answers("")
        self.assertEqual(answers, {})


class TestMergeAllAnswers(unittest.TestCase):
    """全問回答ありでマージ → 6列テーブル + 状態「回答済み」"""

    def setUp(self):
        self.doc = QAMerger.parse_qa_content(_5COL_CONTENT)
        answers = {1: "A", 2: "B", 3: "C"}
        self.merged = QAMerger.merge_answers(self.doc, answers)

    def test_status_updated(self):
        self.assertEqual(self.merged.status, "回答済み")

    def test_q1_user_answer(self):
        self.assertEqual(self.merged.questions[0].user_answer, "A) 別サービス維持")

    def test_q2_user_answer(self):
        self.assertEqual(self.merged.questions[1].user_answer, "B) gRPC")

    def test_q3_user_answer_tbd(self):
        self.assertEqual(self.merged.questions[2].user_answer, "C) TBD")

    def test_original_doc_unchanged(self):
        # マージ元は変更されていないこと（deepcopy で保護）
        self.assertIsNone(self.doc.questions[0].user_answer)


class TestMergeDefaultsOnly(unittest.TestCase):
    """use_defaults=True → デフォルト回答採用"""

    def setUp(self):
        self.doc = QAMerger.parse_qa_content(_5COL_CONTENT)
        self.merged = QAMerger.merge_answers(self.doc, {}, use_defaults=True)

    def test_status_is_answered_without_inference_permission(self):
        """推論許可なし + use_defaults → 「回答済み」（「推論補完済み」ではない）"""
        self.assertEqual(self.merged.status, "回答済み")

    def test_q1_default_applied(self):
        self.assertEqual(self.merged.questions[0].user_answer, "A) 別サービス維持")

    def test_q3_default_applied(self):
        self.assertEqual(self.merged.questions[2].user_answer, "C) TBD")


class TestMergePartialAnswers(unittest.TestCase):
    """部分回答 → 未回答はデフォルト"""

    def setUp(self):
        self.doc = QAMerger.parse_qa_content(_5COL_CONTENT)
        # Q1 のみ回答、Q2 と Q3 は未回答
        answers = {1: "A"}
        self.merged = QAMerger.merge_answers(self.doc, answers)

    def test_q1_answered(self):
        self.assertEqual(self.merged.questions[0].user_answer, "A) 別サービス維持")

    def test_q2_uses_default(self):
        # 未回答はデフォルト回答（A) REST/HTTP）
        self.assertEqual(self.merged.questions[1].user_answer, "A) REST/HTTP")

    def test_q3_uses_default(self):
        self.assertEqual(self.merged.questions[2].user_answer, "C) TBD")

    def test_status_is_answered(self):
        self.assertEqual(self.merged.status, "回答済み")


class TestRenderMerged(unittest.TestCase):
    """マージ済み QADocument → 6列 Markdown"""

    def setUp(self):
        doc = QAMerger.parse_qa_content(_5COL_CONTENT)
        merged = QAMerger.merge_answers(doc, {1: "A", 2: "B", 3: "C"})
        self.rendered = QAMerger.render_merged(merged)

    def test_has_6col_header(self):
        self.assertIn("ユーザー回答", self.rendered)

    def test_has_no_col_header(self):
        self.assertIn("| No. |", self.rendered)

    def test_title_present(self):
        self.assertIn("# テスト質問票", self.rendered)

    def test_status_updated_in_rendered(self):
        self.assertIn("回答済み", self.rendered)

    def test_user_answer_in_row(self):
        self.assertIn("A) 別サービス維持", self.rendered)

    def test_q2_user_answer_in_row(self):
        self.assertIn("B) gRPC", self.rendered)


class TestGenerateConsolidatedPath(unittest.TestCase):
    """qa/foo.md → qa/foo-consolidated.md"""

    def test_basic(self):
        p = Path("qa/foo.md")
        result = QAMerger.generate_consolidated_path(p)
        self.assertEqual(result, Path("qa/foo-consolidated.md"))

    def test_nested(self):
        p = Path("qa/subdir/bar.md")
        result = QAMerger.generate_consolidated_path(p)
        self.assertEqual(result, Path("qa/subdir/bar-consolidated.md"))

    def test_does_not_double_consolidated(self):
        """既に -consolidated で終わるファイルには二重付与しない"""
        p = Path("qa/foo-consolidated.md")
        result = QAMerger.generate_consolidated_path(p)
        self.assertEqual(result, Path("qa/foo-consolidated.md"))


class TestFindQaFilesExcludesConsolidated(unittest.TestCase):
    """-consolidated.md 除外"""

    def test_excludes_consolidated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qa_dir = Path(tmpdir)
            (qa_dir / "aaa.md").write_text("content", encoding="utf-8")
            (qa_dir / "bbb-consolidated.md").write_text("content", encoding="utf-8")
            (qa_dir / "ccc.md").write_text("content", encoding="utf-8")

            files = QAMerger.find_qa_files(qa_dir)
            names = [f.name for f in files]
            self.assertIn("aaa.md", names)
            self.assertIn("ccc.md", names)
            self.assertNotIn("bbb-consolidated.md", names)

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = QAMerger.find_qa_files(Path(tmpdir))
            self.assertEqual(files, [])


class TestSaveMergedWriteReadback(unittest.TestCase):
    """write → read-back 検証"""

    def test_save_and_readback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.md"
            content = "# テスト\n\nコンテンツ\n"
            result = QAMerger.save_merged(content, path)
            self.assertTrue(result)
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subdir" / "out.md"
            result = QAMerger.save_merged("# content\n", path)
            self.assertTrue(result)
            self.assertTrue(path.exists())


class TestParseQaFileNotFound(unittest.TestCase):
    """FileNotFoundError"""

    def test_raises_on_missing(self):
        with self.assertRaises(FileNotFoundError):
            QAMerger.parse_qa_file(Path("/nonexistent/path/qa.md"))


class TestParseAnswersInvalidFormat(unittest.TestCase):
    """不正行は無視"""

    def test_invalid_lines_ignored(self):
        text = "not_a_valid_line\n1: A\nfoo: bar\n2: B"
        answers = QAMerger.parse_answers(text)
        self.assertEqual(answers, {1: "A", 2: "B"})

    def test_only_invalid_lines(self):
        answers = QAMerger.parse_answers("foo\nbar\nbaz")
        self.assertEqual(answers, {})


class TestMergeAlreadyMergedOverwrite(unittest.TestCase):
    """再マージ（上書き）"""

    def test_overwrite_existing_answers(self):
        # 既に6列の doc に再マージ
        doc = QAMerger.parse_qa_content(_6COL_CONTENT)
        # Q2 の回答を B → A に変更
        answers = {1: "A", 2: "A", 3: "C"}
        merged = QAMerger.merge_answers(doc, answers)
        self.assertEqual(merged.questions[1].user_answer, "A) REST/HTTP")

    def test_status_stays_answered(self):
        doc = QAMerger.parse_qa_content(_6COL_CONTENT)
        merged = QAMerger.merge_answers(doc, {1: "A", 2: "A", 3: "C"})
        self.assertEqual(merged.status, "回答済み")


class TestParseQaFileFixtures(unittest.TestCase):
    """fixtures ファイルを使ったパーステスト"""

    def test_parse_5col_fixture(self):
        path = _FIXTURES_DIR / "sample_qa_5col.md"
        doc = QAMerger.parse_qa_file(path)
        self.assertEqual(len(doc.questions), 3)
        self.assertEqual(doc.status, "回答待ち")
        for q in doc.questions:
            self.assertIsNone(q.user_answer)

    def test_parse_6col_fixture(self):
        path = _FIXTURES_DIR / "sample_qa_6col.md"
        doc = QAMerger.parse_qa_file(path)
        self.assertEqual(len(doc.questions), 3)
        self.assertEqual(doc.status, "回答済み")
        # 全問ユーザー回答あり
        for q in doc.questions:
            self.assertIsNotNone(q.user_answer)


# ---------------------------------------------------------------------------
# 追加テスト（review feedback 対応）
# ---------------------------------------------------------------------------

_EXTRA_COL_CONTENT = """\
# 追加列テスト質問票

**状態**: 回答待ち
**推論許可**: なし

---

## 質問項目

| No. | 分野 | 質問 | 選択肢 | デフォルトの回答案 | 選択理由 |
|-----|------|------|--------|-------------------|----------|
| 1 | 認証 | SSO 連携するか | A) SSO / B) 独自認証 | A) SSO | 既存 ID 基盤 |
| 2 | DB | データストアはどれか | A) SQL / B) NoSQL | B) NoSQL | スケーラビリティ優先 |
"""

_PREAMBLE_CONTENT = """\
# プレアンブルテスト質問票

**状態**: 回答待ち
**推論許可**: なし

---

以下の質問にご回答ください。
プロジェクトの設計方針を決定するための質問です。

## 質問項目

| No. | 質問 | 選択肢 | デフォルトの回答案 | 選択理由 |
|-----|------|--------|-------------------|----------|
| 1 | 方式はどれか | A) 方式X / B) 方式Y | A) 方式X | 実績あり |
"""

_DOUBLE_PIPE_CONTENT = """\
# 二重パイプテスト

**状態**: 回答待ち
**推論許可**: なし

---

## 質問項目

|| No. | 質問 | 選択肢 | デフォルトの回答案 | 選択理由 ||
||-----|------|--------|-------------------|----------||
|| 1 | 方式はどれか | A) 方式X / B) 方式Y | A) 方式X | 実績あり ||
"""

_INFERENCE_ALLOWED_CONTENT = """\
# 推論許可テスト

**状態**: 回答待ち
**推論許可**: あり

---

## 質問項目

| No. | 質問 | 選択肢 | デフォルトの回答案 | 選択理由 |
|-----|------|--------|-------------------|----------|
| 1 | 方式はどれか | A) 方式X / B) 方式Y | A) 方式X | 実績あり |
"""


class TestDynamicColumnParsing(unittest.TestCase):
    """追加列（例: 分野）を含むテーブルのパース"""

    def setUp(self):
        self.doc = QAMerger.parse_qa_content(_EXTRA_COL_CONTENT)

    def test_question_count(self):
        self.assertEqual(len(self.doc.questions), 2)

    def test_question_text_q1(self):
        """追加列があっても 質問 列を正しく取得する"""
        self.assertIn("SSO", self.doc.questions[0].question)

    def test_choices_q1(self):
        """選択肢列を正しく取得する"""
        self.assertEqual(len(self.doc.questions[0].choices), 2)
        self.assertEqual(self.doc.questions[0].choices[0].label, "A")

    def test_default_answer_q2(self):
        self.assertEqual(self.doc.questions[1].default_answer, "B) NoSQL")

    def test_reason_q1(self):
        self.assertIn("ID 基盤", self.doc.questions[0].reason)


class TestPreamblePreservation(unittest.TestCase):
    """プレアンブル（ヘッダーフィールドとセクション間の文章）が保持される"""

    def test_preamble_parsed(self):
        doc = QAMerger.parse_qa_content(_PREAMBLE_CONTENT)
        self.assertIn("以下の質問にご回答ください", doc.preamble)

    def test_preamble_in_rendered_output(self):
        doc = QAMerger.parse_qa_content(_PREAMBLE_CONTENT)
        merged = QAMerger.merge_answers(doc, {1: "A"})
        rendered = QAMerger.render_merged(merged)
        self.assertIn("以下の質問にご回答ください", rendered)

    def test_no_preamble_content_is_empty(self):
        doc = QAMerger.parse_qa_content(_5COL_CONTENT)
        self.assertEqual(doc.preamble, "")


class TestDoublePipeTolerance(unittest.TestCase):
    """LLM 出力の二重パイプ行もパースできる"""

    def test_double_pipe_rows_parsed(self):
        doc = QAMerger.parse_qa_content(_DOUBLE_PIPE_CONTENT)
        self.assertEqual(len(doc.questions), 1)
        self.assertIn("方式", doc.questions[0].question)


class TestMergeStatusWithInferencePermission(unittest.TestCase):
    """推論許可あり + use_defaults=True → 「推論補完済み」"""

    def test_status_is_inference_when_permitted(self):
        doc = QAMerger.parse_qa_content(_INFERENCE_ALLOWED_CONTENT)
        self.assertEqual(doc.inference_permission, "あり")
        merged = QAMerger.merge_answers(doc, {}, use_defaults=True)
        self.assertEqual(merged.status, "推論補完済み")

    def test_status_is_answered_when_no_permission(self):
        """推論許可なし + use_defaults=True → 「回答済み」"""
        doc = QAMerger.parse_qa_content(_5COL_CONTENT)
        self.assertEqual(doc.inference_permission, "なし")
        merged = QAMerger.merge_answers(doc, {}, use_defaults=True)
        self.assertEqual(merged.status, "回答済み")


if __name__ == "__main__":
    unittest.main()
