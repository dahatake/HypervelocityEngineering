"""Contracts for identifier splitting and cAST chunking (FR-CQ-05)."""

from __future__ import annotations

import pytest

from cq import chunking

PY_SOURCE = '''\
import os


def alpha():
    return 1


class Widget:
    def resolveUserProfile(self):
        return 2

    def close(self):
        return 3
'''


class TestIdentifierSplitting:
    @pytest.mark.parametrize(("text", "expected"), [
        ("getUserProfile", ["get", "user", "profile"]),
        ("resolve_run_id", ["resolve", "run", "id"]),
        ("HTTPResponseData", ["http", "response", "data"]),
        ("MemberConsentApplication", ["member", "consent", "application"]),
        ("db_path_for", ["db", "path", "for"]),
        ("v2Endpoint", ["v2", "endpoint"]),
    ])
    def test_identifiers_are_split_into_words(self, text: str, expected: list[str]) -> None:
        assert chunking.split_identifier(text) == expected

    def test_source_is_expanded_into_a_word_stream(self) -> None:
        words = chunking.identifier_text("def resolveUserProfile(self, db_path):")
        assert {"resolve", "user", "profile", "db", "path"} <= set(words.split())

    def test_original_identifier_is_kept_alongside_the_split_words(self) -> None:
        words = chunking.identifier_text("resolveUserProfile").split()
        assert "resolveUserProfile" in words

    def test_single_word_identifiers_are_not_duplicated(self) -> None:
        """`text` 列で既に検索できるため、索引を膞らませない。"""
        assert chunking.identifier_text("import os") == ""

    def test_non_identifier_noise_is_dropped(self) -> None:
        assert chunking.identifier_text("### ---- ***") == ""


class TestChunking:
    def test_each_definition_becomes_a_chunk(self) -> None:
        chunks = chunking.chunk_source(PY_SOURCE, "python", max_chars=4000)
        assert [c.name for c in chunks if c.name] == ["alpha", "Widget"]

    def test_chunk_lines_map_back_to_the_source(self) -> None:
        chunks = chunking.chunk_source(PY_SOURCE, "python", max_chars=4000)
        lines = PY_SOURCE.splitlines()
        for chunk in chunks:
            assert 1 <= chunk.start_line <= chunk.end_line <= len(lines)
            assert chunk.text == "\n".join(lines[chunk.start_line - 1:chunk.end_line])

    def test_large_nodes_are_split_into_children(self) -> None:
        """上限を超えるノードは子ノードへ再帰分割する（cAST）。"""
        big = "class Big:\n" + "".join(
            f"    def m{i}(self):\n        return {i}\n" for i in range(40)
        )
        chunks = chunking.chunk_source(big, "python", max_chars=200)
        assert len(chunks) > 1
        assert all(len(c.text) <= 200 or c.end_line == c.start_line for c in chunks)

    def test_small_siblings_are_merged_within_the_limit(self) -> None:
        """上限に満たない兄弟ノードは連結して細切れを防ぐ（cAST）。"""
        statements = "".join(f"x{i} = {i}\n" for i in range(20))
        merged = chunking.chunk_source(statements, "python", max_chars=4000)
        unmerged = chunking.chunk_source(statements, "python", max_chars=10)
        assert len(merged) == 1
        assert len(unmerged) > len(merged)

    def test_boundaries_are_not_decided_by_line_count_alone(self) -> None:
        """行数だけを根拠にチャンク境界を決めない: 定義の先頭が必ず境界になる。"""
        chunks = chunking.chunk_source(PY_SOURCE, "python", max_chars=4000)
        starts = {c.start_line for c in chunks}
        assert {4, 8} <= starts  # `def alpha` と `class Widget` の行

    def test_identifier_text_is_attached_to_every_chunk(self) -> None:
        chunks = chunking.chunk_source(PY_SOURCE, "python", max_chars=4000)
        target = [c for c in chunks if "resolveUserProfile" in c.text]
        assert target
        assert "profile" in target[0].ident_text.split()

    def test_unparsable_source_falls_back_to_windows(self) -> None:
        chunks = chunking.chunk_source("def broken(:\n    x = 1\n", "python", max_chars=4000)
        assert chunks
        assert chunks[0].start_line == 1

    def test_unknown_language_falls_back_to_windows(self) -> None:
        text = "\n".join(f"line {n}" for n in range(1, 101))
        chunks = chunking.chunk_source(text, "csharp", max_chars=200)
        assert len(chunks) > 1
        assert chunks[0].start_line == 1
        assert chunks[-1].end_line == 100

    def test_empty_source_yields_nothing(self) -> None:
        assert chunking.chunk_source("", "python", max_chars=4000) == ()

    def test_chunking_is_deterministic(self) -> None:
        first = chunking.chunk_source(PY_SOURCE, "python", max_chars=200)
        second = chunking.chunk_source(PY_SOURCE, "python", max_chars=200)
        assert first == second

    def test_every_line_is_covered_exactly_once(self) -> None:
        chunks = chunking.chunk_source(PY_SOURCE, "python", max_chars=200)
        covered: list[int] = []
        for chunk in chunks:
            covered.extend(range(chunk.start_line, chunk.end_line + 1))
        assert covered == sorted(covered)
        assert len(covered) == len(set(covered))

    def test_split_definitions_do_not_overlap(self) -> None:
        """分割時に親ヘッダと子ノードの行範囲が重複しないこと。"""
        big = "class Big:\n" + "".join(
            f"    def m{i}(self):\n        return {i}\n" for i in range(40)
        )
        chunks = chunking.chunk_source(big, "python", max_chars=200)
        covered: list[int] = []
        for chunk in chunks:
            covered.extend(range(chunk.start_line, chunk.end_line + 1))
        assert covered == sorted(covered)
        assert len(covered) == len(set(covered))
        assert covered[0] == 1
        assert covered[-1] == len(big.splitlines())
