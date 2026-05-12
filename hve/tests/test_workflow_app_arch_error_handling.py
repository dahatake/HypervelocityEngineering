"""4 reusable workflows の app-arch filter エラー分類が正しく実装されているか検証する。"""

import unittest
from pathlib import Path

_WF = Path(__file__).resolve().parents[2] / ".github" / "workflows"

_TARGETS = {
    "auto-app-detail-design-web-reusable.yml": "aad-web",
    "auto-app-dev-microservice-web-reusable.yml": "asdw-web",
    "auto-batch-design-reusable.yml": "abd",
    "auto-batch-dev-reusable.yml": "abdv",
}


class TestAppArchFilterErrorClassification(unittest.TestCase):
    def _read(self, fn: str) -> str:
        return (_WF / fn).read_text(encoding="utf-8")

    def test_helper_function_defined(self):
        for fn in _TARGETS:
            with self.subTest(fn=fn):
                content = self._read(fn)
                self.assertIn(
                    "_post_app_arch_filter_error()",
                    content,
                    f"{fn} に分類関数 _post_app_arch_filter_error の定義がありません",
                )

    def test_classifies_section_not_found(self):
        for fn in _TARGETS:
            with self.subTest(fn=fn):
                content = self._read(fn)
                self.assertIn(
                    "セクションが見つかりません",
                    content,
                    f"{fn} に セクション不在 の case 分岐がありません",
                )
                self.assertIn(
                    "出力契約",
                    content,
                    f"{fn} に 出力契約 への案内文がありません",
                )

    def test_classifies_file_not_found(self):
        for fn in _TARGETS:
            with self.subTest(fn=fn):
                content = self._read(fn)
                self.assertIn(
                    "catalog ファイルが見つかりません",
                    content,
                    f"{fn} に ファイル不在 の case 分岐がありません",
                )

    def test_unknown_error_branch(self):
        for fn in _TARGETS:
            with self.subTest(fn=fn):
                content = self._read(fn)
                self.assertIn(
                    "詳細不明",
                    content,
                    f"{fn} に 詳細不明 のフォールバック文言がありません",
                )

    def test_invokes_helper_in_filter_block(self):
        for fn, wf_id in _TARGETS.items():
            with self.subTest(fn=fn):
                content = self._read(fn)
                self.assertIn(f"--workflow {wf_id}", content)
                self.assertIn(
                    '_post_app_arch_filter_error "${ROOT_ISSUE}" "${FILTER_RESULT}"',
                    content,
                    f"{fn} で フィルタ失敗ブロック内 から関数呼び出しがされていません",
                )

    def test_uses_external_python_error_parser(self):
        for fn in _TARGETS:
            with self.subTest(fn=fn):
                content = self._read(fn)
                self.assertIn(
                    'python3 "${GITHUB_WORKSPACE}/.github/scripts/python/parse_filter_error.py"',
                    content,
                    f"{fn} の _err 抽出が外部スクリプト化されていません",
                )
