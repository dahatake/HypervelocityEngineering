"""Scala 抽出の契約（FR-CQ-04 / FR-CQ-05 / FR-CQ-07 / FR-CQ-11）。

レジストリ登録前でも成立するよう、モジュールを直接呼び出す。
"""

from __future__ import annotations

from collections import Counter

import pytest

from cq import languages
from cq.languages import scala, treesitter as ts

SCALA2 = """\
package com.example.etl

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions.{col, sum}

type MemberId = Long

/** Loads and aggregates sales. */
object RoyaltyJob {
  def loadSales(spark: SparkSession, path: String): Unit = {
    spark.read.parquet(path)
    logIt("done")
  }
}

case class Royalty(memberId: MemberId, total: Double)

trait Sink {
  def write(): Unit
}

class DeltaSink(table: String) extends Sink {
  override def write(): Unit = println(table)
}
"""

SCALA3 = """\
package com.example.etl

enum Tier:
  case Bronze, Gold

given Ordering[Tier] = Ordering.by(_.ordinal)

extension (t: Tier) def isTop: Boolean = t == Tier.Gold

object RoyaltyJob3:
  def classify(total: Double): Tier =
    if total > 1000 then Tier.Gold else Tier.Bronze
"""


class TestScala2Symbols:
    def test_expected_symbols_are_extracted(self) -> None:
        got = Counter((s.kind, s.qualname) for s in scala.extract(SCALA2))
        assert got == Counter([
            ("type", "MemberId"),
            ("class", "RoyaltyJob"),
            ("method", "RoyaltyJob.loadSales"),
            ("class", "Royalty"),
            ("property", "Royalty.memberId"),
            ("property", "Royalty.total"),
            ("interface", "Sink"),
            ("method", "Sink.write"),
            ("class", "DeltaSink"),
            ("property", "DeltaSink.table"),
            ("method", "DeltaSink.write"),
        ])

    def test_object_members_are_methods_not_functions(self) -> None:
        """`object` は singleton なので `def` は `Name.member` として到達する。"""
        loader = next(s for s in scala.extract(SCALA2) if s.name == "loadSales")
        assert (loader.kind, loader.parent) == ("method", "RoyaltyJob")

    def test_abstract_trait_member_is_indexed(self) -> None:
        write = [s for s in scala.extract(SCALA2) if s.qualname == "Sink.write"]
        assert len(write) == 1 and write[0].kind == "method"

    def test_type_alias_is_indexed_like_the_other_languages(self) -> None:
        """Go / Rust / C / C++ と同じく型エイリアスは `type` で索引する。"""
        alias = next(s for s in scala.extract(SCALA2) if s.name == "MemberId")
        assert (alias.kind, alias.parent) == ("type", None)

    def test_class_level_val_and_var_are_indexed_as_variables(self) -> None:
        """Phase 3 (FR-CQ-11): a class/trait/object member `val`/`var`/`given`
        closes the gap tags.scm identifies (previously out of the vocabulary)."""
        symbols = scala.extract(
            "object A {\n  val total: Int = 1\n  var counter: Int = 0\n}\n"
        )
        by_qualname = {s.qualname: s for s in symbols}
        assert by_qualname["A.total"].kind == "variable"
        assert by_qualname["A.counter"].kind == "variable"

    def test_local_val_inside_a_def_is_still_out_of_scope(self) -> None:
        """A local binding is not a class member; indexing it would flood the
        symbol table with noise unrelated to the file's public surface."""
        symbols = scala.extract(
            "object A {\n  def run(): Unit = {\n    val x = 1\n    println(x)\n  }\n}\n"
        )
        assert [s.qualname for s in symbols] == ["A", "A.run"]

    def test_given_definition_is_indexed_as_a_variable(self) -> None:
        source = "object A {\n  given intOrdering: Ordering[Int] = Ordering.Int\n}\n"
        given = next(s for s in scala.extract(source) if s.name == "intOrdering")
        assert (given.kind, given.qualname) == ("variable", "A.intOrdering")

    def test_scaladoc_becomes_the_doc_head(self) -> None:
        job = next(s for s in scala.extract(SCALA2) if s.name == "RoyaltyJob")
        assert job.doc_head == "Loads and aggregates sales."

    def test_signature_stops_before_the_body(self) -> None:
        job = next(s for s in scala.extract(SCALA2) if s.name == "RoyaltyJob")
        assert job.signature == "object RoyaltyJob"

    def test_line_ranges_stay_inside_the_file(self) -> None:
        total = len(SCALA2.splitlines())
        for symbol in scala.extract(SCALA2):
            assert 1 <= symbol.start_line <= symbol.end_line <= total

    def test_extraction_is_deterministic(self) -> None:
        assert scala.extract(SCALA2) == scala.extract(SCALA2)


class TestScala3Symbols:
    def test_enum_and_indented_object_are_extracted(self) -> None:
        got = Counter((s.kind, s.qualname) for s in scala.extract(SCALA3))
        assert got == Counter([
            ("enum", "Tier"),
            ("function", "isTop"),
            ("class", "RoyaltyJob3"),
            ("method", "RoyaltyJob3.classify"),
        ])

    def test_anonymous_given_is_not_a_symbol(self) -> None:
        """名前を持たない `given` は最小 kind 語彙の対象外。"""
        assert "Ordering" not in {s.name for s in scala.extract(SCALA3)}


class TestGraphContract:
    def test_imports_keep_the_selector_clause(self) -> None:
        _, imports = scala.extract_graph(SCALA2)
        assert imports == (
            (3, "org.apache.spark.sql.SparkSession"),
            (4, "org.apache.spark.sql.functions.{col, sum}"),
        )

    def test_calls_resolve_to_the_trailing_member(self) -> None:
        refs, _ = scala.extract_graph(SCALA2)
        assert (11, "parquet") in refs
        assert (12, "logIt") in refs
        assert (23, "println") in refs


class TestChunkContract:
    def test_each_top_level_definition_gets_a_named_span(self) -> None:
        spans = scala.chunk_spans(SCALA2, SCALA2.splitlines(), 2000)
        named = {(s.name, s.start, s.end) for s in spans if s.name}
        assert named == {
            ("MemberId", 6, 6),
            ("RoyaltyJob", 9, 14),
            ("Royalty", 16, 16),
            ("Sink", 18, 20),
            ("DeltaSink", 22, 24),
        }

    def test_spans_stay_inside_the_file(self) -> None:
        """重複の除去は core の責任。言語側はファイル内に収めることだけを保証する。"""
        total = len(SCALA2.splitlines())
        for span in scala.chunk_spans(SCALA2, SCALA2.splitlines(), 200):
            assert 1 <= span.start <= span.end <= total

    def test_chunking_is_deterministic(self) -> None:
        lines = SCALA2.splitlines()
        assert scala.chunk_spans(SCALA2, lines, 200) == scala.chunk_spans(SCALA2, lines, 200)


class TestDegradation:
    def test_absent_grammar_raises_extraction_error(self, monkeypatch) -> None:
        """文法未導入の環境では indexer が lite へ降格できる形で失敗する。"""
        monkeypatch.setitem(
            ts._PARSERS,
            ts.cache_key(scala.GRAMMAR),
            languages.ExtractionError("simulated missing grammar"),
        )
        with pytest.raises(languages.ExtractionError):
            scala.extract(SCALA2)
