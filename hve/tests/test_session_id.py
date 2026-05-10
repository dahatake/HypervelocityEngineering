"""test_session_id.py — Phase 2 SDK セッション ID 安定化のユニットテスト。

検証範囲:
- `make_session_id()` の決定論性とフォーマット
- パストラバーサル文字の除去
- step_id の "1.1" 形式（ドット表記）保持
- suffix によるサブセッション識別
- prefix のカスタマイズ
- 空入力に対する安全なフォールバック

Phase 2 タスク（resume.md §2）の DoD:
- pytest hve/tests/test_session_id.py 全 PASS
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from run_state import (  # type: ignore[import-not-found]
    DEFAULT_SESSION_ID_PREFIX,
    make_session_id,
    _safe_session_id_token,
)


class TestMakeSessionIdBasic(unittest.TestCase):
    """基本フォーマットの検証。"""

    def test_basic_format(self) -> None:
        sid = make_session_id("20260507T153012-abc123", "1.1")
        self.assertEqual(sid, "hve-20260507T153012-abc123-step-1.1")

    def test_default_prefix(self) -> None:
        sid = make_session_id("run-1", "1.1")
        self.assertTrue(sid.startswith(f"{DEFAULT_SESSION_ID_PREFIX}-"))

    def test_step_id_with_dots_preserved(self) -> None:
        """step_id の "1.1.2" のような階層ドットが保持されること。"""
        sid = make_session_id("run-1", "1.1.2")
        self.assertIn("step-1.1.2", sid)

    def test_step_id_with_underscore(self) -> None:
        sid = make_session_id("run-1", "step_alpha")
        self.assertIn("step-step_alpha", sid)

    def test_suffix_for_subsessions(self) -> None:
        """suffix が末尾に付加されること。"""
        for suffix in ("qa", "review", "pre-qa", "workiq-prefetch"):
            sid = make_session_id("run-1", "1.1", suffix=suffix)
            self.assertTrue(sid.endswith(f"-{suffix}"), f"suffix '{suffix}' が末尾にない: {sid}")

    def test_no_suffix_omits_trailing_dash(self) -> None:
        sid = make_session_id("run-1", "1.1", suffix="")
        self.assertFalse(sid.endswith("-"), f"末尾に余計なダッシュ: {sid}")
        # `-step-1.1` で終了するはず
        self.assertTrue(sid.endswith("-step-1.1"))


class TestMakeSessionIdDeterminism(unittest.TestCase):
    """同じ入力に対して常に同じ出力を返すこと（Resume の前提条件）。"""

    def test_same_inputs_yield_same_id(self) -> None:
        a = make_session_id("run-A", "1.1")
        b = make_session_id("run-A", "1.1")
        self.assertEqual(a, b)

    def test_same_inputs_with_suffix_yield_same_id(self) -> None:
        a = make_session_id("run-A", "1.1", suffix="qa")
        b = make_session_id("run-A", "1.1", suffix="qa")
        self.assertEqual(a, b)

    def test_different_step_ids_yield_different_ids(self) -> None:
        a = make_session_id("run-A", "1.1")
        b = make_session_id("run-A", "1.2")
        self.assertNotEqual(a, b)

    def test_different_suffixes_yield_different_ids(self) -> None:
        main = make_session_id("run-A", "1.1")
        qa = make_session_id("run-A", "1.1", suffix="qa")
        review = make_session_id("run-A", "1.1", suffix="review")
        self.assertNotEqual(main, qa)
        self.assertNotEqual(main, review)
        self.assertNotEqual(qa, review)

    def test_different_run_ids_yield_different_ids(self) -> None:
        a = make_session_id("run-A", "1.1")
        b = make_session_id("run-B", "1.1")
        self.assertNotEqual(a, b)


class TestMakeSessionIdSecurity(unittest.TestCase):
    """パストラバーサル / 不正文字対策。"""

    def test_path_traversal_chars_removed_from_run_id(self) -> None:
        sid = make_session_id("../../etc/passwd", "1.1")
        self.assertNotIn("..", sid)
        self.assertNotIn("/", sid)
        self.assertNotIn("\\", sid)

    def test_path_traversal_chars_removed_from_step_id(self) -> None:
        sid = make_session_id("run-1", "../etc")
        self.assertNotIn("..", sid)
        self.assertNotIn("/", sid)

    def test_path_traversal_chars_removed_from_suffix(self) -> None:
        sid = make_session_id("run-1", "1.1", suffix="../qa")
        self.assertNotIn("..", sid)
        self.assertNotIn("/", sid)

    def test_path_traversal_chars_removed_from_prefix(self) -> None:
        sid = make_session_id("run-1", "1.1", prefix="../malicious")
        self.assertNotIn("..", sid)
        self.assertNotIn("/", sid)

    def test_null_byte_rejected(self) -> None:
        sid = make_session_id("run-1\x00", "1.1\x00", suffix="qa\x00")
        self.assertNotIn("\x00", sid)

    def test_only_ascii_safe_chars(self) -> None:
        """生成された ID は英数字・ハイフン・アンダースコア・ドットのみで構成される。"""
        import re
        sid = make_session_id("run-A_1.0", "1.1.2", suffix="qa-extra")
        self.assertRegex(sid, r"^[A-Za-z0-9\-_.]+$")


class TestMakeSessionIdEdgeCases(unittest.TestCase):
    """空入力・極端な値に対する安全なフォールバック。"""

    def test_empty_run_id_does_not_crash(self) -> None:
        sid = make_session_id("", "1.1")
        # "unknown" にフォールバックすること（空入力で例外を投げない）
        self.assertIn("unknown", sid)
        self.assertTrue(sid.startswith(f"{DEFAULT_SESSION_ID_PREFIX}-"))

    def test_empty_step_id_does_not_crash(self) -> None:
        sid = make_session_id("run-1", "")
        self.assertIn("unknown", sid)

    def test_only_invalid_chars_in_run_id(self) -> None:
        """全文字が不正でも例外を投げず unknown にフォールバックすること。"""
        sid = make_session_id("////", "1.1")
        # _safe_session_id_token は不正文字を "-" に置換し strip する → 空 → "unknown"
        self.assertTrue(sid.startswith(f"{DEFAULT_SESSION_ID_PREFIX}-"))

    def test_long_run_id_truncated(self) -> None:
        """過剰に長い run_id は切り詰められ、生成 ID 全体がファイル名長制限内に収まる。"""
        long_run_id = "a" * 200
        sid = make_session_id(long_run_id, "1.1")
        # OS のファイル名長制限（通常 255 byte）以内であること
        self.assertLess(len(sid), 250)

    def test_long_suffix_truncated(self) -> None:
        long_suffix = "x" * 100
        sid = make_session_id("run-1", "1.1", suffix=long_suffix)
        self.assertLess(len(sid), 250)


class TestMakeSessionIdPrefix(unittest.TestCase):
    """prefix のカスタマイズと正規化。"""

    def test_custom_prefix(self) -> None:
        sid = make_session_id("run-1", "1.1", prefix="custom")
        self.assertTrue(sid.startswith("custom-"))

    def test_empty_prefix_falls_back_to_default(self) -> None:
        sid = make_session_id("run-1", "1.1", prefix="")
        self.assertTrue(sid.startswith(f"{DEFAULT_SESSION_ID_PREFIX}-"))

    def test_invalid_chars_in_prefix_sanitized(self) -> None:
        """prefix の不正文字も正規化されるが、空にならない場合はそのまま使われる。"""
        sid = make_session_id("run-1", "1.1", prefix="my-app_v1")
        # アンダースコアは prefix では許可されないため "-" に置換される
        self.assertTrue(sid.startswith("my-app-v1-"))


class TestSafeSessionIdToken(unittest.TestCase):
    """補助関数 `_safe_session_id_token()` の挙動。"""

    def test_alphanumeric_preserved(self) -> None:
        self.assertEqual(_safe_session_id_token("ABC123"), "ABC123")

    def test_underscore_dot_preserved_when_allowed(self) -> None:
        self.assertEqual(_safe_session_id_token("a_b.c"), "a_b.c")

    def test_underscore_dot_replaced_when_not_allowed(self) -> None:
        result = _safe_session_id_token("a_b.c", allow_underscore_dot=False)
        # アンダースコアとドットが - に置換され、連続 - は 1 個に圧縮される
        self.assertNotIn("_", result)
        self.assertNotIn(".", result)

    def test_consecutive_dashes_compressed(self) -> None:
        self.assertEqual(_safe_session_id_token("a---b"), "a-b")

    def test_leading_trailing_dashes_stripped(self) -> None:
        self.assertEqual(_safe_session_id_token("---abc---"), "abc")

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(_safe_session_id_token(""), "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
