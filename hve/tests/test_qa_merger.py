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


# ---------------------------------------------------------------------------
# FR-QA-03: 回答済み QA ファイルの read-back 検証 API
# ---------------------------------------------------------------------------

_ANSWERED_ALL_DEFAULTS = """\
# テスト質問票

**状態**: 回答済み
**推論許可**: なし

---

## 質問項目

| No. | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 | ユーザー回答 |
|-----|------|--------|-----------|-----------------|------------|
| 1 | サービス分割方針 | A) 分割 / B) 統合 | A) 分割 | ドメイン分析 | A) 分割 |
| 2 | 通信方式 | A) REST / B) gRPC | A) REST | 習熟度 | B) gRPC |
"""

_NO_ANSWER_NO_DEFAULT = """\
# テスト質問票

**状態**: 回答済み
**推論許可**: なし

---

## 質問項目

| No. | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 | ユーザー回答 |
|-----|------|--------|-----------|-----------------|------------|
| 1 | サービス分割方針 | A) 分割 / B) 統合 | A) 分割 | ドメイン分析 | A) 分割 |
| 2 | 未決定項目 | A) Yes / B) No |  |  |  |
"""


class TestAnsweredQaValidation(unittest.TestCase):
    """FR-QA-03: validate_answered_file — 保存後 read-back 検証。"""

    def test_roundtrip_content_matches(self):
        """保存→再読込で内容・質問数・全回答が一致すれば OK を返す。"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "qa-answered.md"
            QAMerger.save_merged(_ANSWERED_ALL_DEFAULTS, p)
            errors = QAMerger.validate_answered_file(
                p,
                expected_content=_ANSWERED_ALL_DEFAULTS,
                expected_questions=2,
            )
            self.assertEqual(errors, [], f"検証エラーが出るべきではない: {errors}")

    def test_parse_merge_render_save_validate_flow(self):
        """実運用と同じ parse→merge→render→save→validate を通す。"""
        doc = QAMerger.parse_qa_content(_STRUCTURED_CONTENT)
        merged = QAMerger.merge_answers(doc, {}, use_defaults=True)
        rendered = QAMerger.render_merged(merged)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "qa-answered.md"
            self.assertTrue(QAMerger.save_merged(rendered, p))
            errors = QAMerger.validate_answered_file(
                p,
                expected_content=rendered,
                expected_questions=len(doc.questions),
            )
            self.assertEqual(errors, [])

    def test_inference_completed_status_is_valid(self):
        doc = QAMerger.parse_qa_content(_INFERENCE_ALLOWED_CONTENT)
        merged = QAMerger.merge_answers(doc, {}, use_defaults=True)
        rendered = QAMerger.render_merged(merged)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "qa-inferred.md"
            self.assertTrue(QAMerger.save_merged(rendered, p))
            self.assertEqual(QAMerger.validate_answered_file(p), [])

    def test_rejects_empty_user_answer(self):
        """回答が空の質問が含まれていれば拒否する。"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "qa-answered.md"
            QAMerger.save_merged(_NO_ANSWER_NO_DEFAULT, p)
            errors = QAMerger.validate_answered_file(p)
            self.assertTrue(len(errors) > 0, "回答も既定値も無い質問は拒否されるべき")
            self.assertTrue(
                any("2" in e for e in errors),
                f"質問 2 についてのエラーがあるべき: {errors}",
            )

    def test_rejects_tampered_content(self):
        """保存後にファイル内容が改変されていれば拒否する。"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "qa-answered.md"
            QAMerger.save_merged(_ANSWERED_ALL_DEFAULTS, p)
            tampered = p.read_text(encoding="utf-8").replace("A) 分割", "X) 改変")
            p.write_text(tampered, encoding="utf-8")
            original_doc = QAMerger.parse_qa_content(_ANSWERED_ALL_DEFAULTS)
            errors = QAMerger.validate_answered_file(
                p,
                expected_content=_ANSWERED_ALL_DEFAULTS,
                expected_questions=len(original_doc.questions),
            )
            self.assertTrue(len(errors) > 0, "内容改変は検出されるべき")

    def test_question_count_mismatch_rejected(self):
        """再読込した質問数が期待値と異なれば拒否する。"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "qa-answered.md"
            QAMerger.save_merged(_ANSWERED_ALL_DEFAULTS, p)
            errors = QAMerger.validate_answered_file(p, expected_questions=99)
            self.assertTrue(len(errors) > 0, "質問数不一致は検出されるべき")

    def test_rejects_document_without_questions(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "qa-empty.md"
            p.write_text(
                "# QA\n\n**状態**: 回答済み\n\n質問はありません。\n",
                encoding="utf-8",
            )
            errors = QAMerger.validate_answered_file(p)
            self.assertTrue(any("質問が見つかりません" in e for e in errors))


class TestParseQaContent6ColumnsQuestionCount(unittest.TestCase):
    """6列テーブルの質問数テスト（TestParseQaContent6Columns から分離された既存テスト）。"""

    def setUp(self):
        self.doc = QAMerger.parse_qa_content(_6COL_CONTENT)

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


class TestParseAnswersFreeText(unittest.TestCase):
    """`N:: <text>` 形式の自由記述回答パース"""

    def test_freetext_basic(self):
        text = "1:: 自由記述の回答"
        answers = QAMerger.parse_answers(text)
        self.assertEqual(answers, {1: "自由記述の回答"})

    def test_freetext_and_label_mixed(self):
        text = "1: A\n2:: 自由記述コンテンツ\n3: C"
        answers = QAMerger.parse_answers(text)
        self.assertEqual(answers, {1: "A", 2: "自由記述コンテンツ", 3: "C"})

    def test_freetext_with_colons_inside(self):
        text = "1:: foo: bar: baz"
        answers = QAMerger.parse_answers(text)
        self.assertEqual(answers, {1: "foo: bar: baz"})

    def test_freetext_empty_is_ignored(self):
        text = "1::   \n2: A"
        answers = QAMerger.parse_answers(text)
        self.assertEqual(answers, {2: "A"})

    def test_label_format_unaffected_by_freetext_addition(self):
        # 単一英字ラベルは従来通り
        text = "1: A) はい"
        answers = QAMerger.parse_answers(text)
        self.assertEqual(answers, {1: "A"})


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


class TestMergeOtherFreeText(unittest.TestCase):
    """選択肢付き質問の「その他」自由記述を保存する。"""

    @staticmethod
    def _make_doc() -> QADocument:
        return QADocument(
            title="その他回答テスト",
            questions=[
                QAQuestion(
                    no=1,
                    question="方式はどれか",
                    choices=[
                        Choice(label="A", text="標準方式"),
                        Choice(label="B", text="別方式"),
                    ],
                    default_answer="A) 標準方式",
                    reason="既定値",
                ),
            ],
        )

    def test_other_freetext_is_persisted_in_output_file(self):
        answers = QAMerger.parse_answers("1:: その他: 独自の方式")
        merged = QAMerger.merge_answers(self._make_doc(), answers)
        self.assertEqual(merged.questions[0].user_answer, "その他: 独自の方式")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "merged.md"
            self.assertTrue(QAMerger.save_merged(QAMerger.render_merged(merged), path))
            self.assertIn("その他: 独自の方式", path.read_text(encoding="utf-8"))
            persisted = QAMerger.parse_qa_file(path)
            self.assertEqual(persisted.questions[0].user_answer, "その他: 独自の方式")

    def test_empty_other_freetext_falls_back_to_default(self):
        answers = QAMerger.parse_answers("1::   ")
        merged = QAMerger.merge_answers(self._make_doc(), answers)
        self.assertEqual(merged.questions[0].user_answer, "A) 標準方式")


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

    def test_excludes_workiq_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qa_dir = Path(tmpdir)
            (qa_dir / "aaa.md").write_text("content", encoding="utf-8")
            (qa_dir / "run-1-1-workiq-qa.md").write_text("content", encoding="utf-8")
            (qa_dir / "run-1-1-workiq-draft.md").write_text("content", encoding="utf-8")

            files = QAMerger.find_qa_files(qa_dir)
            names = [f.name for f in files]
            self.assertIn("aaa.md", names)
            self.assertNotIn("run-1-1-workiq-qa.md", names)
            self.assertNotIn("run-1-1-workiq-draft.md", names)

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

    def test_parse_5col_v1_legacy_fixture(self):
        """旧形式（v1）のフィクスチャが後方互換でパースできる"""
        path = _FIXTURES_DIR / "sample_qa_5col_v1.md"
        doc = QAMerger.parse_qa_file(path)
        self.assertEqual(len(doc.questions), 3)
        self.assertEqual(doc.status, "回答待ち")
        # 旧形式でも default_answer がパースされる
        self.assertEqual(doc.questions[0].default_answer, "A) 別サービス維持")

    def test_parse_6col_v1_legacy_fixture(self):
        """旧形式マージ済み（v1）のフィクスチャが後方互換でパースできる"""
        path = _FIXTURES_DIR / "sample_qa_6col_v1.md"
        doc = QAMerger.parse_qa_file(path)
        self.assertEqual(len(doc.questions), 3)
        self.assertEqual(doc.status, "回答済み")
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

| No. | 分野 | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 |
|-----|------|------|--------|-----------|----------------|
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

| No. | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 |
|-----|------|--------|-----------|----------------|
| 1 | 方式はどれか | A) 方式X / B) 方式Y | A) 方式X | 実績あり |
"""

_DOUBLE_PIPE_CONTENT = """\
# 二重パイプテスト

**状態**: 回答待ち
**推論許可**: なし

---

## 質問項目

|| No. | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 ||
||-----|------|--------|-----------|----------------||
|| 1 | 方式はどれか | A) 方式X / B) 方式Y | A) 方式X | 実績あり ||
"""

_INFERENCE_ALLOWED_CONTENT = """\
# 推論許可テスト

**状態**: 回答待ち
**推論許可**: あり

---

## 質問項目

| No. | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 |
|-----|------|--------|-----------|----------------|
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


# ---------------------------------------------------------------------------
# 新規テストクラス
# ---------------------------------------------------------------------------

_LEGACY_5COL_CONTENT = """\
# 旧形式テスト質問票

**状態**: 回答待ち
**推論許可**: なし

---

## 質問項目

| No. | 質問 | 選択肢 | デフォルトの回答案 | 選択理由 |
|-----|------|--------|-------------------|----------|
| 1 | 方式はどれか | A) 方式X / B) 方式Y | A) 方式X | 実績あり |
| 2 | DB 選定 | A) SQL / B) NoSQL | B) NoSQL | スケーラビリティ優先 |
"""

_STRUCTURED_CONTENT = """\
# 構造化テスト質問票

**状態**: 回答待ち
**推論許可**: なし

---

[Q01]
- 分類項目: アーキテクチャ
- 重要度: 最重要
- 質問文: サービス分割方針はどれか
- 背景と根拠: 出典: domain-analytics.md / 確定: 現行は分割 / 未確定: 統合時の移行コストが未計測
- 判断の観点: 変更容易性: A 有利 / 運用コスト: B 有利
- 選択肢:
  A. 分割維持
  B. 統合
  C. TBD
- 未回答時の既定値候補: A. 分割維持
- 既定値候補の理由: domain-analytics.md に基づく
- 未回答のまま進めた場合の影響: 設計が固まらない

[Q02]
- 分類項目: 通信
- 重要度: 高
- 質問文: 通信方式はどれか
- 背景と根拠: 出典: 未確認 / 確定: 既存は REST / 未確定: gRPC の運用実績
- 判断の観点: 習熟度: A 有利 / スループット: B 有利
- 選択肢:
  A. REST
  B. gRPC
- 未回答時の既定値候補: A. REST
- 既定値候補の理由: チーム習熟度を優先
- 未回答のまま進めた場合の影響: 実装方針が未決
"""

_ORIGINAL_DOCS_STRUCTURED_CONTENT = """\
[Q01]
- 対象ドキュメント: docs-original/spec.md
- 該当箇所: 「代表SKUの算出条件が明記されていない」
- 問題種別: 不明瞭
- 重大度: major
- 質問内容: 代表SKUの算出条件はどのドキュメントを正としますか。
- 未回答時の既定値候補: docs-original/spec.md を暫定的な正とする
- 既定値候補の理由: 他に明示された根拠がないため
- 未回答のまま進めた場合の影響: 算出結果の解釈が分岐する
"""

_STRUCTURED_NUMERIC_LABELS = """\
[Q01]
- 質問文: 数字ラベルテスト
- 選択肢:
  1. 選択肢A
  2. 選択肢B
  3. 選択肢C
- 未回答時の既定値候補: 1. 選択肢A
- 既定値候補の理由: テスト
- 未回答のまま進めた場合の影響: なし
"""

_STRUCTURED_MARKDOWN_DECORATED_TEMPLATE = """\
{marker}
- 分類項目: フォーマット
- 重要度: 高
- 質問文: 装飾付きQ見出しがパースできるか
- 選択肢:
  A. はい
  B. いいえ
- 未回答時の既定値候補: A. はい
- 既定値候補の理由: 回帰防止
- 未回答のまま進めた場合の影響: パース失敗でフォールバック
"""


class TestLegacyFormatBackwardCompatibility(unittest.TestCase):
    """旧形式（デフォルトの回答案 / 選択理由）テーブルの後方互換テスト"""

    def setUp(self):
        self.doc = QAMerger.parse_qa_content(_LEGACY_5COL_CONTENT)

    def test_question_count(self):
        """旧形式でも正しくパースできる"""
        self.assertEqual(len(self.doc.questions), 2)

    def test_default_answer_parsed(self):
        """旧形式の「デフォルトの回答案」列が default_answer にマップされる"""
        self.assertEqual(self.doc.questions[0].default_answer, "A) 方式X")

    def test_reason_parsed(self):
        """旧形式の「選択理由」列が reason にマップされる"""
        self.assertIn("実績", self.doc.questions[0].reason)

    def test_new_fields_are_empty(self):
        """旧形式では新フィールド（priority, category, impact_if_unanswered）が空文字列"""
        for q in self.doc.questions:
            self.assertEqual(q.priority, "")
            self.assertEqual(q.category, "")
            self.assertEqual(q.impact_if_unanswered, "")


class TestStructuredQuestionParsing(unittest.TestCase):
    """新形式（[Q01]構造化テキスト）パーステスト"""

    def setUp(self):
        self.doc = QAMerger.parse_qa_content(_STRUCTURED_CONTENT)

    def test_question_count(self):
        """[Q01] [Q02] の2問がパースされる"""
        self.assertEqual(len(self.doc.questions), 2)

    def test_q1_number(self):
        self.assertEqual(self.doc.questions[0].no, 1)

    def test_q1_question(self):
        self.assertIn("サービス分割", self.doc.questions[0].question)

    def test_q1_priority(self):
        self.assertEqual(self.doc.questions[0].priority, "最重要")

    def test_q1_category(self):
        self.assertEqual(self.doc.questions[0].category, "アーキテクチャ")

    def test_q1_default_answer(self):
        self.assertIn("分割維持", self.doc.questions[0].default_answer)

    def test_q1_reason(self):
        self.assertIn("domain-analytics", self.doc.questions[0].reason)

    def test_q1_impact_if_unanswered(self):
        self.assertIn("設計が固まらない", self.doc.questions[0].impact_if_unanswered)

    def test_q1_background(self):
        """FR-QA-02: 背景と根拠がパースされる。"""
        self.assertIn("統合時の移行コストが未計測", self.doc.questions[0].background)

    def test_q1_viewpoints(self):
        """FR-QA-02: 判断の観点がパースされる。"""
        self.assertIn("変更容易性: A 有利", self.doc.questions[0].viewpoints)

    def test_q1_choices_alpha_labels(self):
        """英字ラベル選択肢が正しくパースされる"""
        choices = self.doc.questions[0].choices
        self.assertEqual(len(choices), 3)
        self.assertEqual(choices[0].label, "A")
        self.assertEqual(choices[0].text, "分割維持")
        self.assertEqual(choices[1].label, "B")
        self.assertEqual(choices[2].label, "C")

    def test_q2_number(self):
        self.assertEqual(self.doc.questions[1].no, 2)

    def test_q2_priority(self):
        self.assertEqual(self.doc.questions[1].priority, "高")


class TestOriginalDocsStructuredQuestionParsing(unittest.TestCase):
    """原本質問票フィールド名（質問内容/問題種別/重大度）のパーステスト。"""

    def setUp(self):
        self.doc = QAMerger.parse_qa_content(_ORIGINAL_DOCS_STRUCTURED_CONTENT)

    def test_question_content_alias_parsed(self):
        self.assertEqual(len(self.doc.questions), 1)
        self.assertIn("代表SKU", self.doc.questions[0].question)

    def test_issue_type_maps_to_category(self):
        self.assertEqual(self.doc.questions[0].category, "不明瞭")

    def test_severity_maps_to_priority(self):
        self.assertEqual(self.doc.questions[0].priority, "major")

    def test_default_reason_and_impact_parsed(self):
        q = self.doc.questions[0]
        self.assertIn("暫定的な正", q.default_answer)
        self.assertIn("根拠", q.reason)
        self.assertIn("解釈", q.impact_if_unanswered)


class TestStructuredNumericLabelConversion(unittest.TestCase):
    """数字ラベル（1./2./3.）→ 英字変換テスト"""

    def setUp(self):
        questions = QAMerger._parse_structured_questions(_STRUCTURED_NUMERIC_LABELS)
        self.q = questions[0] if questions else None

    def test_question_parsed(self):
        self.assertIsNotNone(self.q)

    def test_numeric_labels_converted_to_alpha(self):
        """数字ラベルが英字に変換される"""
        self.assertIsNotNone(self.q)
        self.assertEqual(len(self.q.choices), 3)
        self.assertEqual(self.q.choices[0].label, "A")
        self.assertEqual(self.q.choices[1].label, "B")
        self.assertEqual(self.q.choices[2].label, "C")

    def test_numeric_label_text_preserved(self):
        """数字ラベル→英字変換時に選択肢テキストが保持される"""
        self.assertIsNotNone(self.q)
        self.assertEqual(self.q.choices[0].text, "選択肢A")
        self.assertEqual(self.q.choices[1].text, "選択肢B")
        self.assertEqual(self.q.choices[2].text, "選択肢C")


class TestStructuredQuestionMarkerDecoration(unittest.TestCase):
    """[Q01] 見出しの Markdown 装飾ゆらぎを許容する。"""

    def _assert_single_question_parsed(self, marker: str) -> None:
        content = _STRUCTURED_MARKDOWN_DECORATED_TEMPLATE.format(marker=marker)
        doc = QAMerger.parse_qa_content(content)
        self.assertEqual(len(doc.questions), 1)
        self.assertEqual(doc.questions[0].no, 1)
        self.assertIn("装飾付きQ見出し", doc.questions[0].question)

    def test_marker_without_decoration(self):
        self._assert_single_question_parsed("[Q01]")

    def test_marker_with_bold(self):
        self._assert_single_question_parsed("**[Q01]**")

    def test_marker_with_bold_italic(self):
        self._assert_single_question_parsed("***[Q01]***")

    def test_marker_with_italic(self):
        self._assert_single_question_parsed("*[Q01]*")


class TestQAQuestionNewFields(unittest.TestCase):
    """QAQuestion の新フィールドのデフォルト値テスト"""

    def test_priority_defaults_empty(self):
        q = QAQuestion(no=1, question="テスト")
        self.assertEqual(q.priority, "")

    def test_category_defaults_empty(self):
        q = QAQuestion(no=1, question="テスト")
        self.assertEqual(q.category, "")

    def test_impact_if_unanswered_defaults_empty(self):
        q = QAQuestion(no=1, question="テスト")
        self.assertEqual(q.impact_if_unanswered, "")

    def test_background_defaults_empty(self):
        q = QAQuestion(no=1, question="テスト")
        self.assertEqual(q.background, "")

    def test_viewpoints_defaults_empty(self):
        q = QAQuestion(no=1, question="テスト")
        self.assertEqual(q.viewpoints, "")

    def test_new_fields_can_be_set(self):
        q = QAQuestion(no=1, question="テスト", priority="最重要", category="設計", impact_if_unanswered="影響大")
        self.assertEqual(q.priority, "最重要")
        self.assertEqual(q.category, "設計")
        self.assertEqual(q.impact_if_unanswered, "影響大")


class TestRenderMergedDynamicColumns(unittest.TestCase):
    """render_merged() の動的列数テスト"""

    def _make_doc_no_new_fields(self) -> "QADocument":
        """新フィールドなしのドキュメントを生成"""
        doc = QAMerger.parse_qa_content(_LEGACY_5COL_CONTENT)
        return QAMerger.merge_answers(doc, {1: "A", 2: "B"})

    def _make_doc_with_new_fields(self) -> "QADocument":
        """新フィールドありのドキュメントを生成"""
        doc = QAMerger.parse_qa_content(_STRUCTURED_CONTENT)
        return QAMerger.merge_answers(doc, {}, use_defaults=True)

    def test_6col_without_new_fields(self):
        """新フィールドなしで6列テーブル"""
        rendered = QAMerger.render_merged(self._make_doc_no_new_fields())
        self.assertIn("ユーザー回答", rendered)
        self.assertNotIn("重要度", rendered)
        self.assertNotIn("分類項目", rendered)

    def test_9col_with_new_fields(self):
        """新フィールドありで9列テーブル（未回答のまま進めた場合の影響を含む）"""
        rendered = QAMerger.render_merged(self._make_doc_with_new_fields())
        self.assertIn("重要度", rendered)
        self.assertIn("分類項目", rendered)
        self.assertIn("未回答のまま進めた場合の影響", rendered)
        self.assertIn("ユーザー回答", rendered)

    def test_new_term_default_candidate(self):
        """新用語「既定値候補」が使われる"""
        rendered = QAMerger.render_merged(self._make_doc_no_new_fields())
        self.assertIn("既定値候補", rendered)
        self.assertNotIn("デフォルトの回答案", rendered)

    def test_new_term_reason(self):
        """新用語「既定値候補の理由」が使われる"""
        rendered = QAMerger.render_merged(self._make_doc_no_new_fields())
        self.assertIn("既定値候補の理由", rendered)
        self.assertNotIn("選択理由", rendered)


class TestRenderMergedDepthColumns(unittest.TestCase):
    """FR-QA-02: 背景と根拠 / 判断の観点 の列出力と往復保持テスト。"""

    def _make_doc(self) -> QADocument:
        doc = QAMerger.parse_qa_content(_STRUCTURED_CONTENT)
        return QAMerger.merge_answers(doc, {}, use_defaults=True)

    @staticmethod
    def _table_lines(rendered: str) -> list:
        """テーブル行だけを返す。preamble には元の [Qxx] 全文が残るため除外する。"""
        return [line for line in rendered.splitlines() if line.startswith("|")]

    def _table_header(self, rendered: str) -> str:
        return next(line for line in self._table_lines(rendered) if "No." in line)

    def test_extended_header_includes_depth_columns(self):
        header = self._table_header(QAMerger.render_merged(self._make_doc()))
        self.assertIn("背景と根拠", header)
        self.assertIn("判断の観点", header)

    def test_depth_values_are_rendered(self):
        rendered = QAMerger.render_merged(self._make_doc())
        rows = [line for line in self._table_lines(rendered) if "サービス分割方針" in line]
        self.assertTrue(rows, "質問行がテーブルに見つからない")
        self.assertIn("統合時の移行コストが未計測", rows[0])
        self.assertIn("変更容易性: A 有利", rows[0])

    def test_depth_only_document_uses_extended_table(self):
        """重要度・分類項目が無くても、深さ項目だけで拡張テーブルになる。"""
        doc = QADocument(questions=[
            QAQuestion(
                no=1, question="テスト",
                background="出典: 未確認", viewpoints="保守性: A 有利",
            ),
        ])
        rendered = QAMerger.render_merged(doc)
        self.assertIn("背景と根拠", rendered)
        self.assertIn("判断の観点", rendered)

    def test_rendered_table_round_trips_depth_columns(self):
        """GUI の IPC 往復（render → parse）で深さ項目が欠落しない。"""
        rendered = QAMerger.render_merged(self._make_doc())
        reparsed = QAMerger.parse_qa_content(rendered)
        self.assertEqual(len(reparsed.questions), 2)
        self.assertIn("統合時の移行コストが未計測", reparsed.questions[0].background)
        self.assertIn("変更容易性: A 有利", reparsed.questions[0].viewpoints)

    def test_legacy_document_leaves_depth_fields_empty(self):
        """深さ項目を持たない旧形式は空文字列となり、解析は失敗しない。"""
        doc = QAMerger.parse_qa_content(_LEGACY_5COL_CONTENT)
        for q in doc.questions:
            self.assertEqual(q.background, "")
            self.assertEqual(q.viewpoints, "")


class TestColumnIndexZeroSafety(unittest.TestCase):
    """None チェーンのインデックス0テスト

    既定値候補がテーブルのインデックス0に配置されていてもパースできることを検証する。
    これは or チェーン（`col_map.get("既定値候補") or col_map.get("デフォルトの回答案")`）では
    インデックス0が falsy のためバグになるケースを回避するため。
    """

    def test_index_zero_default_column_parsed(self):
        """既定値候補列がインデックス0でもパース可能"""
        # 既定値候補が最初の列（インデックス0）に来るケース
        content = """\
# テスト

**状態**: 回答待ち
**推論許可**: なし

---

## 質問項目

| 既定値候補 | No. | 質問 | 選択肢 | 既定値候補の理由 |
|-----------|-----|------|--------|----------------|
| A) はい | 1 | テストか | A) はい / B) いいえ | 実績あり |
"""
        doc = QAMerger.parse_qa_content(content)
        self.assertEqual(len(doc.questions), 1)
        # No. と 質問 が正しくパースされることを確認
        self.assertEqual(doc.questions[0].no, 1)
        self.assertIn("テスト", doc.questions[0].question)
        # インデックス0の既定値候補が正しく取得される
        self.assertEqual(doc.questions[0].default_answer, "A) はい")

    def test_index_zero_reason_column_parsed(self):
        """既定値候補の理由列がインデックス0でもパース可能"""
        # 既定値候補の理由が最初の列（インデックス0）に来るケース
        content = """\
# テスト

**状態**: 回答待ち
**推論許可**: なし

---

## 質問項目

| 既定値候補の理由 | No. | 質問 | 選択肢 | 既定値候補 |
|----------------|-----|------|--------|-----------|
| 実績あり | 1 | テストか | A) はい / B) いいえ | A) はい |
"""
        doc = QAMerger.parse_qa_content(content)
        self.assertEqual(len(doc.questions), 1)
        self.assertEqual(doc.questions[0].no, 1)
        # インデックス0の既定値候補の理由が正しく取得される
        self.assertEqual(doc.questions[0].reason, "実績あり")


class TestRenderMergedMultilineCells(unittest.TestCase):
    """FR-QA-03: 複数行セルでも回答済み QA の往復構造を壊さない。"""

    @staticmethod
    def _make_doc(workiq_answer: str) -> QADocument:
        doc = QADocument(
            title="Work IQ 複数行テスト",
            status="回答待ち",
            header_fields=[("状態", "回答待ち")],
            questions=[
                QAQuestion(no=1, question="質問1", default_answer="A. 回答1"),
                QAQuestion(
                    no=2,
                    question="質問2",
                    default_answer="B. 回答2",
                    workiq_answer=workiq_answer,
                    workiq_reason="Work IQ 調査結果",
                ),
                QAQuestion(no=3, question="質問3", default_answer="C. 回答3"),
            ],
        )
        return QAMerger.merge_answers(doc, {}, use_defaults=True)

    @staticmethod
    def _table_body_lines(rendered: str) -> list[str]:
        lines = rendered.splitlines()
        header_index = next(
            index for index, line in enumerate(lines)
            if line.startswith("| No. |")
            and index + 1 < len(lines)
            and lines[index + 1].startswith("|-----|")
        )
        return [line for line in lines[header_index + 2:] if line]

    def test_multiline_workiq_answer_keeps_one_physical_row_per_question(self) -> None:
        doc = self._make_doc(
            "STATUS: FOUND\n| 種別 | 情報ソース |\n|---|---|\n| ファイル | 仕様書 |"
        )

        rendered = QAMerger.render_merged(doc)

        body_lines = self._table_body_lines(rendered)
        self.assertEqual(len(body_lines), 3)
        self.assertEqual(
            [line.split("|", 2)[1].strip() for line in body_lines],
            ["1", "2", "3"],
        )
        self.assertIn("STATUS: FOUND", body_lines[1])

    def test_crlf_cr_lf_and_pipe_are_safe_in_one_table_cell(self) -> None:
        """採用済み D1=A: 改行は `<br>`、pipe は entity へ変換する。"""
        doc = self._make_doc(
            "STATUS: PARTIAL\r\nalpha\rbeta\ngamma | delta"
        )

        rendered = QAMerger.render_merged(doc)
        body_lines = self._table_body_lines(rendered)

        self.assertNotIn("\r", rendered)
        self.assertIn("STATUS: PARTIAL<br>alpha<br>beta<br>gamma &#124; delta", body_lines[1])
        self.assertEqual(len(body_lines), 3)

    def test_render_save_parse_validate_round_trip_preserves_questions_and_answers(self) -> None:
        doc = self._make_doc(
            "STATUS: FOUND\n| 種別 | 情報ソース |\n| ファイル | 要件定義書 |"
        )
        rendered = QAMerger.render_merged(doc)

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "answered.md"
            self.assertTrue(QAMerger.save_merged(rendered, path))
            errors = QAMerger.validate_answered_file(
                path,
                expected_content=rendered,
                expected_questions=3,
            )
            reparsed = QAMerger.parse_qa_file(path)

        self.assertEqual(errors, [])
        self.assertEqual([q.no for q in reparsed.questions], [1, 2, 3])
        self.assertTrue(all((q.user_answer or "").strip() for q in reparsed.questions))
        self.assertIn("STATUS: FOUND", reparsed.questions[1].workiq_answer)
        self.assertIn("<br>", reparsed.questions[1].workiq_answer)
        self.assertIn("&#124;", reparsed.questions[1].workiq_answer)
        self.assertIn("要件定義書", reparsed.questions[1].workiq_answer)

    def test_render_parse_render_is_stable_for_multiline_workiq_answer(self) -> None:
        rendered = QAMerger.render_merged(
            self._make_doc("STATUS: FOUND\nline 1\nline 2 | value")
        )

        reparsed = QAMerger.parse_qa_content(rendered)

        self.assertEqual(QAMerger.render_merged(reparsed), rendered)


class TestMergeWorkiqResultsStatusSkip(unittest.TestCase):
    """STATUS: NOT_FOUND / UNAVAILABLE 応答は workiq_answer にセットされないこと。"""

    def _make_doc(self) -> QADocument:
        return QADocument(questions=[
            QAQuestion(no=1, question="質問1"),
            QAQuestion(no=2, question="質問2"),
            QAQuestion(no=3, question="質問3"),
            QAQuestion(no=4, question="質問4"),
        ])

    def test_not_found_skipped(self) -> None:
        doc = self._make_doc()
        results = {1: "STATUS: NOT_FOUND\n関連情報なし"}
        merged = QAMerger.merge_workiq_results(doc, results)
        self.assertEqual(merged.questions[0].workiq_answer, "")

    def test_unavailable_skipped(self) -> None:
        doc = self._make_doc()
        results = {2: "STATUS: UNAVAILABLE\nツール未接続"}
        merged = QAMerger.merge_workiq_results(doc, results)
        self.assertEqual(merged.questions[1].workiq_answer, "")

    def test_found_sets_workiq_answer(self) -> None:
        doc = self._make_doc()
        results = {3: "STATUS: FOUND\n| メール | 件名: 議事録 | 2026-04-20 | Outlook | 関連あり |"}
        merged = QAMerger.merge_workiq_results(doc, results)
        self.assertNotEqual(merged.questions[2].workiq_answer, "")

    def test_partial_sets_workiq_answer(self) -> None:
        doc = self._make_doc()
        results = {4: "STATUS: PARTIAL\n| メール | 件名: 部分的な結果 | 2026-04-21 | Outlook | 一部のみ |"}
        merged = QAMerger.merge_workiq_results(doc, results)
        self.assertNotEqual(merged.questions[3].workiq_answer, "")

    def test_case_insensitive_not_found_skipped(self) -> None:
        doc = self._make_doc()
        results = {1: "status: not_found\n関連情報なし"}
        merged = QAMerger.merge_workiq_results(doc, results)
        self.assertEqual(merged.questions[0].workiq_answer, "")

    def test_partial_with_unperformed_search_note_is_merged(self) -> None:
        """本文に「未実施」を含む PARTIAL 応答も統合される（FR-QA-03）。

        Work IQ が「どの追加検索を行わなかったか」を説明する文脈で「未実施」を
        使うことがあり、これを Work IQ の利用不能と誤判定してはならない。
        呼び出し元 (`hve/runner.py`) は `is_workiq_result_mergeable` で
        tool 実行確認済み + status FOUND/PARTIAL の結果だけを渡している。
        """
        doc = self._make_doc()
        results = {
            4: (
                "STATUS: PARTIAL\n"
                "\n"
                "| 種別 | 情報ソース | 日時 | パス/場所 | 関連観点 |\n"
                "|---|---|---:|---|---|\n"
                "| メール | 件名: 設計レビュー | 2026-07-10 | Outlook | 設計レビューの実施予定 |\n"
                "\n"
                "**補足**:\n"
                "- 「構成図」等のキーワードでのファイル深掘り検索は今回未実施。"
                "追加検索で設計書自体が見つかる可能性は残る。"
            )
        }
        merged = QAMerger.merge_workiq_results(doc, results)
        self.assertNotEqual(merged.questions[3].workiq_answer, "")


if __name__ == "__main__":
    unittest.main()
