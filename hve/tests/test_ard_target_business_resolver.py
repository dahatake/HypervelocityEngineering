from __future__ import annotations

from pathlib import Path

import pytest

from hve.ard_target_business_resolver import (
    is_path_like,
    resolve,
    to_context_text,
)


# ---------------------------------------------------------------------------
# is_path_like
# ---------------------------------------------------------------------------

def test_is_path_like_japanese_sentence_returns_false():
    assert is_path_like("ロイヤルティプログラム事業の中長期成長戦略") is False


def test_is_path_like_long_text_returns_false():
    long_text = "A" * 201
    assert is_path_like(long_text) is False


def test_is_path_like_with_newlines_returns_false():
    assert is_path_like("docs/sample.md\ndocs/other.md") is False


def test_is_path_like_empty_returns_false():
    assert is_path_like("") is False
    assert is_path_like("   ") is False


def test_is_path_like_single_md_path_returns_true():
    assert is_path_like("docs/sample.md") is True


def test_is_path_like_existing_dir_returns_true(tmp_path: Path):
    subdir = tmp_path / "my_dir"
    subdir.mkdir()
    assert is_path_like(str(subdir)) is True


def test_is_path_like_csv_paths_returns_true():
    assert is_path_like("docs/a.md, docs/b.md") is True


def test_is_path_like_windows_separator_returns_true():
    assert is_path_like(r"C:\docs\a.md") is True


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------

def test_resolve_text_returns_raw_text():
    text = "ロイヤルティプログラム事業の中長期成長戦略"
    result = resolve(text)
    assert result.is_path is False
    assert result.raw_text == text
    assert result.files == []


def test_resolve_single_file(tmp_path: Path):
    md_file = tmp_path / "sample.md"
    # Windows \u3067 write_text \u306f \\n \u3092 \\r\\n \u306b\u5909\u63db\u3059\u308b\u305f\u3081 write_bytes \u3092\u4f7f\u7528\u3057\u308b\u3002
    md_file.write_bytes(b"# Hello\n\nContent")

    result = resolve(str(md_file))

    assert result.is_path is True
    assert len(result.files) == 1
    assert result.files[0].content == "# Hello\n\nContent"
    assert result.files[0].skip_reason is None
    assert result.files[0].truncated is False


def test_resolve_directory_recursive(tmp_path: Path):
    (tmp_path / "a.md").write_text("A", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.md").write_text("B", encoding="utf-8")

    result = resolve(str(tmp_path))

    readable = [f for f in result.files if f.skip_reason is None]
    assert len(readable) == 2
    contents = {f.content for f in readable}
    assert "A" in contents
    assert "B" in contents


def test_resolve_multiple_paths_csv(tmp_path: Path, monkeypatch):
    # Windows の tmp_path は長いため、is_path_like の 200 文字上限を超えて
    # is_path=False と誤判定される。cwd を tmp_path に移して相対パスで検証する。
    monkeypatch.chdir(tmp_path)
    f1 = tmp_path / "a.md"
    f1.write_text("content_a", encoding="utf-8")
    f2 = tmp_path / "b.md"
    f2.write_text("content_b", encoding="utf-8")

    result = resolve("a.md, b.md")

    # デバッグ用: 失敗時の原因把握のため diagnostics を assertion メッセージに含める
    diag = (
        f"is_path={result.is_path} files_count={len(result.files)} "
        f"errors={result.errors} skipped={result.skipped} "
        f"raw_text={result.raw_text!r}"
    )
    readable = [f for f in result.files if f.skip_reason is None]
    assert len(readable) == 2, diag
    contents = {f.content for f in readable}
    assert "content_a" in contents
    assert "content_b" in contents


def test_resolve_skips_binary_extension(tmp_path: Path):
    pdf_file = tmp_path / "doc.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 binary")

    result = resolve(str(pdf_file))

    # バイナリファイルは skip_reason 付きで result.files に入り、skipped にも追加される
    assert len(result.files) == 1
    assert result.files[0].content == ""
    assert result.files[0].skip_reason is not None
    assert len(result.skipped) == 1
    assert ".pdf" in result.skipped[0] or "doc.pdf" in result.skipped[0]


def test_resolve_truncates_large_file(tmp_path: Path):
    large_file = tmp_path / "large.md"
    large_file.write_text("x" * 100, encoding="utf-8")

    result = resolve(str(large_file), max_file_bytes=50)

    assert len(result.files) == 1
    rf = result.files[0]
    assert rf.truncated is True
    assert "truncated" in rf.content
    assert rf.skip_reason is None


def test_resolve_max_files_limit(tmp_path: Path):
    for i in range(5):
        (tmp_path / f"file{i}.md").write_text(f"content{i}", encoding="utf-8")

    result = resolve(str(tmp_path), max_files=2)

    readable = [f for f in result.files if f.skip_reason is None]
    assert len(readable) == 2
    assert len(result.skipped) == 3


def test_resolve_max_total_bytes_limit(tmp_path: Path):
    (tmp_path / "a.md").write_text("x" * 100, encoding="utf-8")
    (tmp_path / "b.md").write_text("y" * 100, encoding="utf-8")

    result = resolve(str(tmp_path), max_total_bytes=150)

    readable = [f for f in result.files if f.skip_reason is None]
    assert len(readable) == 1
    assert len(result.skipped) >= 1


def test_resolve_nonexistent_path_records_error():
    result = resolve("/nonexistent/path/that/does/not/exist/file.md")

    assert result.is_path is True
    assert result.files == []
    assert len(result.errors) >= 1


def test_resolve_symlink_traversal_skipped(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.md"
    secret.write_text("secret content", encoding="utf-8")

    base_dir = tmp_path / "project"
    base_dir.mkdir()

    try:
        link = base_dir / "link.md"
        link.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported on this platform")

    result = resolve(str(link), base_dir=base_dir)

    # シンボリックリンクは skipped に追加され、秘密ファイルの内容は読まれない
    assert len(result.skipped) >= 1
    readable = [f for f in result.files if f.skip_reason is None]
    assert len(readable) == 0
    assert "secret content" not in to_context_text(result)


# ---------------------------------------------------------------------------
# to_context_text
# ---------------------------------------------------------------------------

def test_to_context_text_for_path_includes_files(tmp_path: Path):
    md_file = tmp_path / "sample.md"
    md_file.write_text("# Sample\n\nSome content.", encoding="utf-8")

    result = resolve(str(md_file))
    context = to_context_text(result)

    assert "sample.md" in context
    assert "target_business" in context


# FR-WF-ARD-02 (v2.57): 展開結果はファイル本文ではなくパス参照とする


def test_to_context_text_excludes_file_body(tmp_path: Path):
    """ファイル本文を Prompt へ埋め込まない。"""
    md_file = tmp_path / "sample.md"
    md_file.write_text("# Sample\n\nUNIQUE-BODY-MARKER-12345", encoding="utf-8")

    context = to_context_text(resolve(str(md_file), base_dir=tmp_path))

    assert "UNIQUE-BODY-MARKER-12345" not in context
    assert "```" not in context


def test_to_context_text_lists_relative_paths(tmp_path: Path):
    """読み取り可能ファイルのリポジトリ相対パス一覧を含める。"""
    (tmp_path / "a.md").write_text("aaa", encoding="utf-8")
    (tmp_path / "b.md").write_text("bbb", encoding="utf-8")

    context = to_context_text(resolve(str(tmp_path), base_dir=tmp_path))

    assert "a.md" in context
    assert "b.md" in context


def test_to_context_text_includes_count_and_total_bytes(tmp_path: Path):
    """件数と合計バイト数を含める。"""
    (tmp_path / "a.md").write_text("12345", encoding="utf-8")

    resolved = resolve(str(tmp_path), base_dir=tmp_path)
    context = to_context_text(resolved)

    assert "展開ファイル数: 1" in context
    assert f"合計サイズ: {resolved.total_size_bytes}" in context


def test_to_context_text_size_is_bounded_by_path_count(tmp_path: Path):
    """本文が大きくても出力サイズはパス件数に比例する（予算超過を招かない）。"""
    big = tmp_path / "big.md"
    big.write_text("x" * 200_000, encoding="utf-8")

    context = to_context_text(resolve(str(big), base_dir=tmp_path))

    assert len(context.encode("utf-8")) < 2_000


def test_to_context_text_for_text_returns_raw():
    text = "ロイヤルティプログラム事業の中長期成長戦略"
    result = resolve(text)
    context = to_context_text(result)

    assert context == text


def test_to_context_text_includes_skipped_section(tmp_path: Path):
    pdf_file = tmp_path / "doc.pdf"
    pdf_file.write_bytes(b"%PDF-1.4")
    md_file = tmp_path / "readme.md"
    md_file.write_text("Hello", encoding="utf-8")

    result = resolve(str(tmp_path))
    context = to_context_text(result)

    assert "スキップ" in context


def test_to_context_text_uses_repo_relative_source_path(tmp_path: Path):
    source = tmp_path / "docs" / "business.md"
    source.parent.mkdir()
    source.write_text("business facts", encoding="utf-8")

    result = resolve(str(source), base_dir=tmp_path)
    context = to_context_text(result)

    assert str(tmp_path) not in context
    assert "docs/business.md" in context.replace("\\", "/")


def test_to_context_text_reports_resolution_errors_without_absolute_path(tmp_path: Path):
    result = resolve("missing/business.md", base_dir=tmp_path)
    context = to_context_text(result)

    assert result.errors
    assert "エラー" in context
    assert "missing/business.md" in context.replace("\\", "/")
    assert str(tmp_path) not in context


def test_to_context_text_redacts_outside_repo_absolute_path(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside-secret.md"
    outside.write_text("secret content", encoding="utf-8")

    result = resolve(str(outside), base_dir=repo)
    context = to_context_text(result)

    assert "secret content" not in context
    assert str(tmp_path) not in context
    assert "outside-base:(redacted)" in context
    assert "outside-secret.md" not in context


def test_resolve_outside_directory_does_not_enumerate_descendants(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "USER-MARKER-123"
    outside.mkdir()
    (outside / "LEAK-MARKER-123.md").write_text("secret", encoding="utf-8")

    result = resolve(str(outside), base_dir=repo)
    context = to_context_text(result)

    assert result.files == []
    assert len(result.skipped) == 1
    assert "USER-MARKER-123" not in context
    assert "LEAK-MARKER-123.md" not in context
    assert "outside-base:(redacted)" in context


def test_directory_resolution_does_not_use_rglob(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "input.md").write_text("facts", encoding="utf-8")

    def reject_rglob(*_args, **_kwargs):
        raise AssertionError("rglob must not cross a symlink boundary before validation")

    monkeypatch.setattr(Path, "rglob", reject_rglob)
    result = resolve(str(repo), base_dir=repo)

    assert [item.relative_path for item in result.files] == ["input.md"]


def test_resolution_diagnostics_are_bounded(tmp_path: Path):
    for index in range(80):
        (tmp_path / f"unsupported-{index:03d}.tmp").write_text(
            "x", encoding="utf-8"
        )

    result = resolve(str(tmp_path), base_dir=tmp_path)
    context = to_context_text(result)

    assert len(result.skipped) <= 51
    assert "追加の診断項目は省略" in context


def test_resolve_symlink_loop_runtime_error_is_recorded(tmp_path: Path, monkeypatch):
    original_resolve = Path.resolve

    def raise_for_loop(path: Path, *args, **kwargs):
        if path.name == "loop.md":
            raise RuntimeError("symlink loop with secret path")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", raise_for_loop)
    result = resolve("loop.md", base_dir=tmp_path)
    context = to_context_text(result)

    assert result.skipped
    assert "symlink loop with secret path" not in context
    assert "outside-base:(redacted)" in context


def test_resolve_multiple_paths_mixed_separators(tmp_path: Path):
    """カンマと空白が混在する入力でもすべてのパスが正しく解決される。"""
    (tmp_path / "a.md").write_text("content_a", encoding="utf-8")
    (tmp_path / "b.md").write_text("content_b", encoding="utf-8")
    (tmp_path / "c.md").write_text("content_c", encoding="utf-8")

    # "a.md, b.md c.md" のようにカンマと空白が混在するケース（相対パス + base_dir）
    result = resolve("a.md, b.md c.md", base_dir=tmp_path)

    readable = [f for f in result.files if f.skip_reason is None]
    assert len(readable) == 3
    contents = {f.content for f in readable}
    assert "content_a" in contents
    assert "content_b" in contents
    assert "content_c" in contents


def test_resolve_symlink_dir_traversal_skipped(tmp_path: Path):
    """base_dir 内の symlink ディレクトリ経由でのトラバーサルもスキップされる。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("secret content", encoding="utf-8")

    base_dir = tmp_path / "project"
    base_dir.mkdir()

    try:
        link_dir = base_dir / "linkdir"
        link_dir.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported on this platform")

    result = resolve(str(base_dir), base_dir=base_dir)

    # symlink dir 経由で発見されるファイルは skipped、内容は読まれない
    readable = [f for f in result.files if f.skip_reason is None]
    assert len(readable) == 0
    assert "secret content" not in to_context_text(result)
    assert "secret.md" not in to_context_text(result)
    assert len(result.skipped) == 1

