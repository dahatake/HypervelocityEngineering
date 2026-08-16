"""test_doc_ingest.py — ADI 決定的前処理のテスト。

対応要件:
- FR-WF-ADI-01: 同一入力に対し ``index.json`` は常に同一
- FR-WF-ADI-02: 原本ディレクトリへ書き込まない
- FR-WF-ADI-03: 非 Markdown を変換し、変換不能な形式は理由付きで除外
- FR-WF-ADI-10: 文書数上限超過で fail-closed
- FR-WF-ADI-11: sha256 一致時は派生ファイルを再書き込みしない
- NFR-SEC-ADI-02: source_dir 外を指すシンボリックリンクを走査しない
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.abspath(_repo_root))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hve.doc_ingest import (  # noqa: E402
    INDEX_FILENAME,
    MaxDocsExceededError,
    _is_inside,
    _remove_if_empty,
    ingest_docs,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class _TempDirs(unittest.TestCase):
    """source_dir / out_dir を用意する共通基底。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.src = root / "docs-original"
        self.out = root / "original-design-doc-ingest"
        self.src.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _index(self) -> dict:
        return json.loads((self.out / INDEX_FILENAME).read_text(encoding="utf-8"))


class TestDeterminism(_TempDirs):
    def test_index_json_is_deterministic(self) -> None:
        _write(self.src / "b.md", "# B\n")
        _write(self.src / "a.md", "# A\n")

        ingest_docs(self.src, out_dir=self.out)
        first = self._index()
        ingest_docs(self.src, out_dir=self.out)
        second = self._index()

        self.assertEqual(first["docs"], second["docs"])
        self.assertEqual(first["excluded"], second["excluded"])

    def test_doc_ids_are_ordered_by_source_path(self) -> None:
        _write(self.src / "z.md", "# Z\n")
        _write(self.src / "a.md", "# A\n")

        ingest_docs(self.src, out_dir=self.out)
        docs = self._index()["docs"]

        self.assertEqual([d["source_path"] for d in docs], ["a.md", "z.md"])
        self.assertEqual([d["doc_id"] for d in docs], ["DOC-0001", "DOC-0002"])


class TestSha256(_TempDirs):
    def test_sha256_recorded_per_doc(self) -> None:
        _write(self.src / "a.md", "# A\n")

        ingest_docs(self.src, out_dir=self.out)
        doc = self._index()["docs"][0]

        self.assertEqual(len(doc["sha256"]), 64)
        self.assertRegex(doc["sha256"], r"^[0-9a-f]{64}$")

    def test_sha256_changes_when_content_changes(self) -> None:
        p = _write(self.src / "a.md", "# A\n")
        ingest_docs(self.src, out_dir=self.out)
        before = self._index()["docs"][0]["sha256"]

        _write(p, "# A changed\n")
        ingest_docs(self.src, out_dir=self.out)
        after = self._index()["docs"][0]["sha256"]

        self.assertNotEqual(before, after)

    def test_duplicate_content_is_marked(self) -> None:
        _write(self.src / "a.md", "# same\n")
        _write(self.src / "b.md", "# same\n")

        ingest_docs(self.src, out_dir=self.out)
        docs = self._index()["docs"]

        self.assertIsNone(docs[0]["duplicate_of"])
        self.assertEqual(docs[1]["duplicate_of"], docs[0]["doc_id"])


class TestIncrementalRewrite(_TempDirs):
    def test_unchanged_doc_is_not_rewritten(self) -> None:
        _write(self.src / "a.md", "# A\n")
        ingest_docs(self.src, out_dir=self.out)
        content = self.out / self._index()["docs"][0]["slug"] / "content.md"
        stamp = content.stat().st_mtime_ns

        ingest_docs(self.src, out_dir=self.out)

        self.assertEqual(content.stat().st_mtime_ns, stamp)

    def test_changed_doc_is_rewritten(self) -> None:
        p = _write(self.src / "a.md", "# A\n")
        ingest_docs(self.src, out_dir=self.out)
        content = self.out / self._index()["docs"][0]["slug"] / "content.md"

        _write(p, "# A changed\n")
        ingest_docs(self.src, out_dir=self.out)

        self.assertIn("changed", content.read_text(encoding="utf-8"))


class TestConversion(_TempDirs):
    def test_markdown_passthrough(self) -> None:
        _write(self.src / "a.md", "# Title\n\nbody\n")

        ingest_docs(self.src, out_dir=self.out)
        doc = self._index()["docs"][0]
        content = (self.out / doc["slug"] / "content.md").read_text(encoding="utf-8")

        self.assertEqual(doc["converter"], "passthrough")
        self.assertIn("# Title", content)

    def test_unsupported_extension_is_excluded_with_reason(self) -> None:
        (self.src / "diagram.drawio").write_text("<mxfile/>", encoding="utf-8")

        ingest_docs(self.src, out_dir=self.out)
        excluded = self._index()["excluded"]

        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["source_path"], "diagram.drawio")
        self.assertTrue(excluded[0]["reason"])

    def test_provenance_is_written(self) -> None:
        _write(self.src / "a.md", "# A\n")

        ingest_docs(self.src, out_dir=self.out)
        slug = self._index()["docs"][0]["slug"]
        prov = json.loads((self.out / slug / "provenance.json").read_text(encoding="utf-8"))

        self.assertEqual(prov["source_path"], "a.md")
        self.assertIn("sha256", prov)
        self.assertIn("converter", prov)

    def test_txt_records_stdlib_converter(self) -> None:
        _write(self.src / "a.txt", "plain text\n")

        ingest_docs(self.src, out_dir=self.out)

        self.assertEqual(self._index()["docs"][0]["converter"], "stdlib")

    def test_csv_records_stdlib_converter(self) -> None:
        _write(self.src / "a.csv", "h1,h2\nv1,v2\n")

        ingest_docs(self.src, out_dir=self.out)

        self.assertEqual(self._index()["docs"][0]["converter"], "stdlib")

    def test_excluded_doc_leaves_no_directory(self) -> None:
        (self.src / "diagram.drawio").write_text("<mxfile/>", encoding="utf-8")

        ingest_docs(self.src, out_dir=self.out)

        self.assertEqual([p.name for p in self.out.iterdir()], [INDEX_FILENAME])


class TestSafety(_TempDirs):
    def test_source_dir_is_not_modified(self) -> None:
        p = _write(self.src / "a.md", "# A\n")
        before = (p.read_bytes(), sorted(x.name for x in self.src.iterdir()))

        ingest_docs(self.src, out_dir=self.out)

        after = (p.read_bytes(), sorted(x.name for x in self.src.iterdir()))
        self.assertEqual(before, after)

    def test_symlink_outside_base_dir_is_skipped(self) -> None:
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        _write(outside / "secret.md", "# secret\n")
        link = self.src / "link.md"
        try:
            link.symlink_to(outside / "secret.md")
        except (OSError, NotImplementedError):
            self.skipTest("シンボリックリンクを作成できない環境")

        ingest_docs(self.src, out_dir=self.out)
        index = self._index()

        self.assertEqual(index["docs"], [])
        self.assertEqual([e["source_path"] for e in index["excluded"]], ["link.md"])

    def test_max_docs_exceeded_fails_closed(self) -> None:
        for i in range(3):
            _write(self.src / f"f{i}.md", f"# {i}\n")

        with self.assertRaises(MaxDocsExceededError):
            ingest_docs(self.src, out_dir=self.out, max_docs=2)

    def test_max_docs_failure_leaves_no_index(self) -> None:
        for i in range(3):
            _write(self.src / f"f{i}.md", f"# {i}\n")

        with self.assertRaises(MaxDocsExceededError):
            ingest_docs(self.src, out_dir=self.out, max_docs=2)

        self.assertFalse((self.out / INDEX_FILENAME).exists())


class TestSlug(_TempDirs):
    def test_slug_is_ascii_safe(self) -> None:
        _write(self.src / "倉庫マスタ取り込み処理.md", "# JP\n")

        ingest_docs(self.src, out_dir=self.out)
        slug = self._index()["docs"][0]["slug"]

        self.assertRegex(slug, r"^[a-z0-9._-]+$")
        self.assertTrue((self.out / slug / "content.md").is_file())

    def test_source_path_keeps_original_name(self) -> None:
        _write(self.src / "倉庫マスタ.md", "# JP\n")

        ingest_docs(self.src, out_dir=self.out)

        self.assertEqual(self._index()["docs"][0]["source_path"], "倉庫マスタ.md")


class TestInternalHelpers(unittest.TestCase):
    """symlink を作成できない環境でも境界判定を検証できるようにする。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_is_inside_true_for_regular_file(self) -> None:
        p = _write(self.base / "sub" / "a.md", "# A\n")

        self.assertTrue(_is_inside(p, self.base))

    def test_is_inside_false_for_sibling_dir(self) -> None:
        other = self.base.parent / (self.base.name + "-other")
        other.mkdir()
        try:
            p = _write(other / "a.md", "# A\n")
            self.assertFalse(_is_inside(p, self.base))
        finally:
            for f in other.iterdir():
                f.unlink()
            other.rmdir()

    def test_is_inside_false_for_missing_path(self) -> None:
        self.assertFalse(_is_inside(self.base / "missing.md", self.base))

    def test_remove_if_empty_removes_empty_dir(self) -> None:
        d = self.base / "empty"
        d.mkdir()

        _remove_if_empty(d)

        self.assertFalse(d.exists())

    def test_remove_if_empty_keeps_non_empty_dir(self) -> None:
        d = self.base / "filled"
        _write(d / "a.md", "# A\n")

        _remove_if_empty(d)

        self.assertTrue(d.exists())


class TestContentPath(_TempDirs):
    """``content_path`` は out_dir を丸ごと含み、呼び出し側がそのまま開ける形であること。"""

    def test_content_path_keeps_the_full_out_dir(self) -> None:
        _write(self.src / "a.md", "# A\n")
        nested = self.out.parent / "docs" / "original-design-doc-ingest"

        ingest_docs(self.src, out_dir=nested)

        entry = json.loads((nested / INDEX_FILENAME).read_text(encoding="utf-8"))["docs"][0]
        self.assertTrue(
            (nested.parent.parent / entry["content_path"]).is_file(),
            f"content_path が開けない: {entry['content_path']}",
        )


if __name__ == "__main__":
    unittest.main()
