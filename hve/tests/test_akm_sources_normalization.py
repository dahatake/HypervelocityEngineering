"""test_akm_sources_normalization.py — Sub-F-1: _normalize_akm_sources / _default_akm_target_files テスト

Sub-B-1 で導入された AKM 入力ソース正規化ヘルパの動作を検証する。
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orchestrator import _normalize_akm_sources, _default_akm_target_files  # type: ignore[import-untyped]


class TestNormalizeAkmSources(unittest.TestCase):
    """`_normalize_akm_sources` の挙動を検証する。"""

    def test_empty_string_returns_default(self) -> None:
        """空文字は既定 ``[qa, original-docs]`` を返す。"""
        self.assertEqual(_normalize_akm_sources(""), ["qa", "original-docs"])

    def test_none_returns_default(self) -> None:
        """None は既定を返す。"""
        self.assertEqual(_normalize_akm_sources(None), ["qa", "original-docs"])

    def test_single_qa(self) -> None:
        """単一値 ``qa`` はそのまま。"""
        self.assertEqual(_normalize_akm_sources("qa"), ["qa"])

    def test_single_original_docs(self) -> None:
        self.assertEqual(_normalize_akm_sources("original-docs"), ["original-docs"])

    def test_single_workiq(self) -> None:
        """新規 ``workiq`` 単独運用も許可。"""
        self.assertEqual(_normalize_akm_sources("workiq"), ["workiq"])

    def test_both_backward_compat(self) -> None:
        """後方互換: ``both`` は ``[qa, original-docs]`` に正規化される。"""
        self.assertEqual(_normalize_akm_sources("both"), ["qa", "original-docs"])

    def test_comma_separated_multi(self) -> None:
        """カンマ区切り組合せ。"""
        self.assertEqual(
            _normalize_akm_sources("qa,original-docs,workiq"),
            ["workiq", "qa", "original-docs"],
        )

    def test_order_is_fixed(self) -> None:
        """順序は ``workiq, qa, original-docs`` 固定（入力順に依存しない）。"""
        self.assertEqual(
            _normalize_akm_sources("original-docs,qa,workiq"),
            ["workiq", "qa", "original-docs"],
        )

    def test_whitespace_separated(self) -> None:
        """空白区切りも受理する。"""
        self.assertEqual(
            _normalize_akm_sources("qa workiq"),
            ["workiq", "qa"],
        )

    def test_mixed_separators(self) -> None:
        """カンマと空白の混在も受理する。"""
        self.assertEqual(
            _normalize_akm_sources("qa, workiq , original-docs"),
            ["workiq", "qa", "original-docs"],
        )

    def test_list_input(self) -> None:
        """list 入力も受理する。"""
        self.assertEqual(
            _normalize_akm_sources(["workiq", "qa"]),
            ["workiq", "qa"],
        )

    def test_duplicate_tokens_deduped(self) -> None:
        """重複は除去される。"""
        self.assertEqual(_normalize_akm_sources("qa,qa,workiq,qa"), ["workiq", "qa"])

    def test_unknown_tokens_ignored(self) -> None:
        """不明トークンは無視されるが、有効なトークンは保持される。"""
        self.assertEqual(_normalize_akm_sources("qa,foo,bar"), ["qa"])

    def test_unknown_only_falls_back_to_default(self) -> None:
        """全て不明トークンの場合は既定値を返す（捏造ではなく安全側）。"""
        self.assertEqual(_normalize_akm_sources("foo,bar"), ["qa", "original-docs"])

    def test_case_insensitive(self) -> None:
        """大文字小文字を区別しない。"""
        self.assertEqual(_normalize_akm_sources("QA,WorkIQ"), ["workiq", "qa"])


class TestDefaultAkmTargetFiles(unittest.TestCase):
    """`_default_akm_target_files` の挙動を検証する。"""

    def test_qa_only(self) -> None:
        self.assertEqual(_default_akm_target_files("qa"), "qa/*.md")

    def test_original_docs_only(self) -> None:
        self.assertEqual(_default_akm_target_files("original-docs"), "original-docs/*")

    def test_workiq_only_returns_empty(self) -> None:
        """``workiq`` のみは単一パターン既定なし。"""
        self.assertEqual(_default_akm_target_files("workiq"), "")

    def test_both_returns_empty(self) -> None:
        """後方互換 ``both`` は複数 non-workiq → 既定なし。"""
        self.assertEqual(_default_akm_target_files("both"), "")

    def test_multi_qa_original_docs_returns_empty(self) -> None:
        """``qa,original-docs`` は複数 non-workiq → 既定なし。"""
        self.assertEqual(_default_akm_target_files("qa,original-docs"), "")

    def test_workiq_plus_qa(self) -> None:
        """``qa,workiq`` は単一 non-workiq=qa → ``qa/*.md``。"""
        self.assertEqual(_default_akm_target_files("qa,workiq"), "qa/*.md")

    def test_workiq_plus_original_docs(self) -> None:
        self.assertEqual(_default_akm_target_files("workiq,original-docs"), "original-docs/*")

    def test_list_input(self) -> None:
        """list 入力も受理する。"""
        self.assertEqual(_default_akm_target_files(["qa", "workiq"]), "qa/*.md")

    def test_empty_returns_default_pattern(self) -> None:
        """空入力は既定 ``[qa, original-docs]`` 経由で空文字（複数 non-workiq）。"""
        self.assertEqual(_default_akm_target_files(""), "")


if __name__ == "__main__":
    unittest.main()
