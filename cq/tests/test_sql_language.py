"""SQL 抽出の契約（FR-CQ-04 / FR-CQ-05 / FR-CQ-07 / FR-CQ-11）。

レジストリ登録前でも成立するよう、モジュールを直接呼び出す。
"""

from __future__ import annotations

from collections import Counter

import pytest

from cq.languages import ExtractionError, sql


@pytest.fixture(autouse=True)
def _clear_analysis_cache():
    """`_analyse` は source をキーにキャッシュするので、差し替え検証の前に消す。"""
    sql._analyse.cache_clear()
    yield
    sql._analyse.cache_clear()

TSQL = """\
-- 会員別ロイヤリティ
CREATE TABLE dbo.member (
    id BIGINT NOT NULL,
    name NVARCHAR(50)
);
GO

CREATE VIEW dbo.v_member_total AS
SELECT m.name, SUM(s.amount) AS total
FROM dbo.member AS m
JOIN dbo.sales AS s ON s.member_id = m.id
GROUP BY m.name;
GO

CREATE PROCEDURE dbo.settle_royalty @member_id BIGINT
AS
BEGIN
    SELECT rate FROM dbo.royalty_rate WHERE member_id = @member_id;
END;
GO
"""

POSTGRES = """\
CREATE TABLE public.member (id bigint);

CREATE FUNCTION public.settle(p bigint) RETURNS numeric LANGUAGE plpgsql AS $fn$
DECLARE
  v_total numeric := 0;
BEGIN
  SELECT SUM(amount) INTO v_total FROM public.sales WHERE member_id = p;
  INSERT INTO public.audit_log(total) VALUES (v_total);
  RETURN v_total;
END;
$fn$;
"""

SPARK = """\
CREATE TABLE silver.sales (id BIGINT, amount DOUBLE) USING DELTA;

MERGE INTO silver.sales AS t
USING bronze.sales_raw AS s
ON t.id = s.id
WHEN MATCHED THEN UPDATE SET t.amount = s.amount;
"""

BIGQUERY = """\
CREATE OR REPLACE TABLE `proj.ds.summary` AS
SELECT id, SUM(amount) AS total FROM `proj.ds.sales` GROUP BY id;
"""

ORACLE_ROUTINE = """\
CREATE OR REPLACE PROCEDURE settle_royalty(p_member_id IN NUMBER, p_total OUT NUMBER) AS
    v_rate NUMBER;
BEGIN
    SELECT rate INTO v_rate FROM royalty_rate WHERE member_id = p_member_id;
    FOR rec IN (SELECT amount FROM sales WHERE member_id = p_member_id) LOOP
        p_total := p_total + rec.amount * v_rate;
    END LOOP;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(-20001, 'rate missing');
END settle_royalty;
"""

BIGQUERY_ROUTINE = """\
CREATE OR REPLACE PROCEDURE `proj.ds.settle`(IN member_id INT64, OUT total FLOAT64)
BEGIN
  DECLARE rate FLOAT64 DEFAULT 0.1;
  SET total = 0;
  FOR row IN (SELECT amount FROM `proj.ds.sales` WHERE id = member_id) DO
    SET total = total + row.amount * rate;
  END FOR;
END;
"""


class TestTsql:
    def test_batch_separators_do_not_hide_later_statements(self) -> None:
        """`GO` を素通しすると tokenizer が以降を丸ごと飲み込む。"""
        got = Counter((s.kind, s.qualname) for s in sql.extract(TSQL))
        assert got == Counter([
            ("struct", "dbo.member"),
            ("struct", "dbo.v_member_total"),
            ("function", "dbo.settle_royalty"),
        ])

    def test_procedure_body_is_not_split_at_its_inner_semicolon(self) -> None:
        procedure = next(s for s in sql.extract(TSQL) if s.kind == "function")
        assert (procedure.start_line, procedure.end_line) == (15, 18)
        assert procedure.signature.startswith("CREATE PROCEDURE dbo.settle_royalty")

    def test_referenced_tables_are_indexed_with_their_line(self) -> None:
        refs, imports = sql.extract_graph(TSQL)
        assert refs == ((10, "member"), (11, "sales"), (18, "royalty_rate"))
        assert imports == ()

    def test_the_created_object_is_not_a_reference_to_itself(self) -> None:
        refs, _ = sql.extract_graph(TSQL)
        assert "v_member_total" not in {name for _, name in refs}
        assert "settle_royalty" not in {name for _, name in refs}


class TestOtherDialects:
    def test_spark_merge_reports_both_sides(self) -> None:
        refs, _ = sql.extract_graph(SPARK)
        assert refs == ((3, "sales"), (4, "sales_raw"))

    def test_bigquery_three_part_name_becomes_the_qualname(self) -> None:
        symbols = sql.extract(BIGQUERY)
        assert [(s.kind, s.qualname, s.name) for s in symbols] == [
            ("struct", "proj.ds.summary", "summary")
        ]

    def test_oracle_routine_body_is_structured_by_the_escalation(self) -> None:
        """sqlglot はどの方言でも PL/SQL 本体を構造化できないので sqlfluff へ回す。"""
        symbols = sql.extract(ORACLE_ROUTINE)
        assert [(s.kind, s.qualname) for s in symbols] == [("function", "settle_royalty")]
        assert (symbols[0].start_line, symbols[0].end_line) == (1, 11)
        assert sql.extract_graph(ORACLE_ROUTINE)[0] == ((4, "royalty_rate"), (5, "sales"))


class TestPostgres:
    def test_table_and_function_are_indexed(self) -> None:
        got = [(s.kind, s.qualname) for s in sql.extract(POSTGRES)]
        assert got == [("struct", "public.member"), ("function", "public.settle")]

    def test_dollar_quoted_body_is_reparsed_for_its_references(self) -> None:
        """`$fn$ ... $fn$` は sqlglot / sqlfluff とも 1 トークンなので、本体を再パースする。"""
        function = next(s for s in sql.extract(POSTGRES) if s.kind == "function")
        assert (function.start_line, function.end_line) == (3, 11)
        assert sql.extract_graph(POSTGRES)[0] == ((7, "sales"), (8, "audit_log"))

    def test_a_call_inside_the_body_is_not_a_table_reference(self) -> None:
        """`SUM(...)` のような呼び出しをテーブル参照として拾わない。"""
        assert "SUM" not in {name for _, name in sql.extract_graph(POSTGRES)[0]}

    def test_body_references_exclude_aliases_and_column_qualifiers(self) -> None:
        """再パースした本体で、別名 `r` / `m` と列修飾子を関係と取り違えない。"""
        source = """\
CREATE FUNCTION public.f() RETURNS void LANGUAGE plpgsql AS $b$
BEGIN
  WITH recent AS (SELECT id FROM public.sales)
  SELECT r.id, public.helper(r.id) FROM recent AS r JOIN public.member m ON m.id = r.id;
  INSERT INTO public.audit_log(total) VALUES (1);
  UPDATE public.member SET seen = true;
  DELETE FROM public.stale;
END;
$b$;
"""
        assert sql.extract_graph(source)[0] == (
            (3, "sales"),
            (4, "member"),
            (4, "recent"),
            (5, "audit_log"),
            (6, "member"),
            (7, "stale"),
        )


class TestEscalation:
    def test_bigquery_scripting_routine_needs_the_escalation(self) -> None:
        """sqlglot はどの方言でも BigQuery のスクリプトを構造化できない。"""
        with pytest.raises(ExtractionError):
            sql._by_sqlglot(BIGQUERY_ROUTINE)
        symbols = sql.extract(BIGQUERY_ROUTINE)
        assert [(s.kind, s.qualname) for s in symbols] == [("function", "proj.ds.settle")]
        assert sql.extract_graph(BIGQUERY_ROUTINE)[0] == ((5, "sales"),)

    def test_a_routine_sqlglot_already_structured_is_not_escalated(self, monkeypatch) -> None:
        """T-SQL は sqlglot で本体まで取れるので 40 ms 級の sqlfluff を起動しない。"""
        called = []
        monkeypatch.setattr(sql, "_by_sqlfluff", lambda source: called.append(source))
        sql.extract(TSQL)
        assert called == []

    def test_analysis_falls_back_when_sqlfluff_is_absent(self, monkeypatch) -> None:
        """`code-sql` extra 未導入の環境では sqlglot の結果をそのまま使う。"""
        monkeypatch.setattr(sql, "_by_sqlfluff", lambda source: None)
        function = next(s for s in sql.extract(ORACLE_ROUTINE) if s.kind == "function")
        assert (function.qualname, function.end_line) == ("settle_royalty", 10)


class TestDegradation:
    def test_non_sql_input_degrades_instead_of_raising_something_else(self) -> None:
        with pytest.raises(ExtractionError):
            sql.extract("this is not sql at all {{{ >>> ???\n")


class TestDeterminism:
    @pytest.mark.parametrize("source", [TSQL, POSTGRES, SPARK, BIGQUERY])
    def test_extraction_is_deterministic(self, source: str) -> None:
        assert sql.extract(source) == sql.extract(source)

    @pytest.mark.parametrize("source", [TSQL, POSTGRES, SPARK, BIGQUERY])
    def test_graph_is_deterministic(self, source: str) -> None:
        assert sql.extract_graph(source) == sql.extract_graph(source)


class TestChunkContract:
    def test_each_statement_becomes_a_span(self) -> None:
        spans = sql.chunk_spans(TSQL, TSQL.splitlines(), 1600)
        assert [(s.start, s.end, s.name) for s in spans] == [
            (2, 4, "dbo.member"),
            (8, 12, "dbo.v_member_total"),
            (15, 18, "dbo.settle_royalty"),
        ]

    def test_statements_without_a_definition_have_no_name(self) -> None:
        spans = sql.chunk_spans(SPARK, SPARK.splitlines(), 1600)
        assert [(s.start, s.end, s.name) for s in spans] == [
            (1, 1, "silver.sales"),
            (3, 6, ""),
        ]

    @pytest.mark.parametrize("source", [TSQL, POSTGRES, SPARK, BIGQUERY])
    def test_spans_stay_inside_the_file(self, source: str) -> None:
        total = len(source.splitlines())
        for span in sql.chunk_spans(source, source.splitlines(), 1600):
            assert 1 <= span.start <= span.end <= total
