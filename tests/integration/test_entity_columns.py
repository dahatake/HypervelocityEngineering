"""Unit / integration tests for the columns, relations, clusters and the DDL / schema supplement of scripts/entities.py
(FR-1025 AC-169/170, FR-1026 AC-171/172/173, FR-1030 AC-181/182)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE / "tests" / "system"))
from entity_repo import CAT, DOC, make_other, make_standard, make_zoom, run_entities, snapshot  # noqa: E402


def model(repo: Path) -> dict:
    r = run_entities(repo, "list", "--json")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def ents(m: dict) -> dict:
    return {e["name"]: e for e in m["entities"]}


def rdcheck(repo: Path):
    return subprocess.run([sys.executable, "scripts/rdcheck.py", "check"], cwd=repo, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def entity_errors(r) -> list:
    """ERROR lines of the entity checks (CHK-25); the fixtures are not complete requirement documents, so other checks are ignored."""
    return [ln for ln in r.stdout.splitlines() if "ERROR" in ln and "CHK-25" in ln and "の対象エンティティ「" not in ln]  # (the standard fixture leaves 顧客 undefined on purpose)


def patch(repo: Path, rel: str, old: str, new: str) -> None:
    p = repo / rel
    p.write_text(p.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")


# FR-1025 AC-169: columns are derived per entity from the catalog's table sections; changing the data changes the list
def test_ac169_columns_are_derived_per_entity_and_follow_the_data(tmp_path):
    repo = make_zoom(tmp_path / "r")
    e = ents(model(repo))
    cols = {c["name"]: c for c in e["注文"]["columns"]}
    assert (cols["id"]["type"], cols["id"]["key"], cols["id"]["description"]) == ("int", "主キー", "注文番号")
    assert (cols["customer_id"]["key"], cols["customer_id"]["ref"]) == ("外部キー", "顧客.id")
    assert [c["name"] for c in e["顧客"]["columns"]] == ["id", "name"]
    patch(repo, CAT, "| item | text | なし |  | 品目 |", "| item | varchar | なし |  | 品目 |\n| qty | int | なし |  | 数量 |")
    again = {c["name"]: c for c in ents(model(repo))["注文"]["columns"]}
    assert again["item"]["type"] == "varchar" and "qty" in again


def test_ac169_no_new_file_or_table_is_created_by_the_derivation(tmp_path):
    repo = make_zoom(tmp_path / "r")
    before = snapshot(repo)
    model(repo)
    assert snapshot(repo) == before


# FR-1025 AC-170: optional; absent data passes; wrong words / unknown references / unknown tables are located errors
def test_ac170_columns_are_optional_and_unwritten_entities_are_marked(tmp_path):
    repo = make_standard(tmp_path / "r")
    m = model(repo)
    assert all(e["columns"] == [] and e["columnsMissing"] for e in m["entities"])  # 推測した値は出さない
    assert not entity_errors(rdcheck(repo))
    z = ents(model(make_zoom(tmp_path / "z")))
    assert z["商品"]["columnsMissing"] is True and z["注文"]["columnsMissing"] is False


@pytest.mark.parametrize("old,new,needle", [
    ("| 主キー |", "| 主ｷｰ |", "キー"),
    ("| 外部キー | 顧客.id |", "| 外部キー | 未知.id |", "未知"),
    ("| 外部キー | 顧客.id |", "| 外部キー | 顧客.zzz |", "zzz"),
    ("### 列: orders", "### 列: ghost", "ghost"),
])
def test_ac170_invalid_column_definitions_are_errors_with_location_and_reason(tmp_path, old, new, needle):
    repo = make_zoom(tmp_path / "r")
    patch(repo, CAT, old, new)
    r = rdcheck(repo)
    hit = [ln for ln in r.stdout.splitlines() if "ERROR" in ln and needle in ln]
    assert hit and "docs/catalog.md:" in hit[0], r.stdout


def test_ac170_valid_column_definitions_pass_the_docs_check(tmp_path):
    assert not entity_errors(rdcheck(make_zoom(tmp_path / "r")))


# FR-1026 AC-171: relations carry kind, both ends and the position of the source; nothing is invented
def test_ac171_relations_have_kind_ends_and_sources_and_no_invented_ones(tmp_path):
    m = model(make_zoom(tmp_path / "r"))
    rels = {(r["scope"], r["from"], r["to"], r["kind"]): r for r in m["relations"]}
    assert ("entity", "注文", "顧客", "外部キー") in rels and ("entity", "注文", "商品", "参照") in rels
    col = rels[("column", "注文", "顧客", "参照")]
    assert (col["fromColumn"], col["toColumn"]) == ("customer_id", "id")
    assert any(s["file"] == "docs/catalog.md" and s["line"] > 0 for s in col["sources"])
    assert any(s["file"] == "docs/requirements-definition.md" for s in rels[("entity", "注文", "商品", "参照")]["sources"])
    assert any(r["scope"] == "usage" and r["to"] == "orders" for r in m["relations"])
    assert not any("在庫" in (r["from"], r["to"]) and r["scope"] != "usage" for r in m["relations"])
    assert not any(r["scope"] == "entity" for r in model(make_standard(tmp_path / "s"))["relations"])


# FR-1026 AC-172: the optional field may be omitted; unknown entities and kinds are located errors
@pytest.mark.parametrize("old,new,needle", [
    ("注文→商品（参照）", "注文→幽霊（参照）", "幽霊"),
    ("注文→商品（参照）", "注文→商品（継承）", "継承"),
    ("注文→商品（参照）", "注文→商品", "種別"),
])
def test_ac172_invalid_relation_field_is_an_error_with_location(tmp_path, old, new, needle):
    repo = make_zoom(tmp_path / "r")
    patch(repo, DOC, old, new)
    r = rdcheck(repo)
    hit = [ln for ln in r.stdout.splitlines() if "ERROR" in ln and "FR-002" in ln and needle in ln]
    assert hit and "docs/requirements-definition.md:" in hit[0], r.stdout


def test_ac172_relation_field_omitted_is_valid(tmp_path):
    repo = make_standard(tmp_path / "r")
    assert "エンティティの関係" not in rdcheck(repo).stdout


# FR-1026 AC-173: a foreign key makes one entity relation; the same pair written in the field merges into one with both sources
def test_ac173_foreign_key_yields_one_entity_relation_and_merges_with_the_field(tmp_path):
    repo = make_zoom(tmp_path / "r")
    patch(repo, DOC, "注文→商品（参照）", "注文→商品（参照）、注文→顧客（参照）")
    pairs = [r for r in model(repo)["relations"] if r["scope"] == "entity" and (r["from"], r["to"]) == ("注文", "顧客")]
    assert len(pairs) == 1 and pairs[0]["kind"] == "外部キー"
    origins = {s["origin"] for s in pairs[0]["sources"]}
    assert "列の定義" in origins and any(o.startswith("要求") for o in origins)


# FR-1027 AC-176 (data side): every entity belongs to exactly one cluster; isolated entities are single clusters
def test_ac176_clusters_partition_the_entities(tmp_path):
    m = model(make_zoom(tmp_path / "r"))
    names = sorted(n for c in m["clusters"] for n in c["entities"])
    assert names == sorted(e["name"] for e in m["entities"]) and len(names) == len(set(names))
    assert sorted(c["count"] for c in m["clusters"]) == [1, 3]


# FR-1030 AC-181: DDL supplement with source, managed values win and differences are shown; unparseable parts are explained
DDL = """-- orders
CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  customer_id INT REFERENCES customers(id),
  item TEXT NOT NULL,
  note varchar(10)
);
CREATE TABLE customers (id int, name text, PRIMARY KEY (id));
CREATE TABLE broken (id int
"""


def test_ac181_ddl_supplements_columns_with_source_and_flags_differences(tmp_path):
    repo = make_zoom(tmp_path / "r")
    (repo / "db").mkdir()
    (repo / "db" / "orders.sql").write_text(DDL, encoding="utf-8")
    m = model(repo)
    cols = {c["name"]: c for c in ents(m)["注文"]["columns"]}
    assert cols["id"]["type"] == "int" and [x["field"] for x in cols["id"]["mismatch"]] == ["type"]  # 管理データを優先し食い違いを示す
    assert cols["note"]["origin"] == "補完" and cols["note"]["source"] == {"file": "db/orders.sql", "line": 6}
    assert cols["note"]["type"] == "varchar(10)"
    assert any("broken" in d["reason"] or "括弧" in d["reason"] for d in m["supplement"]["diagnostics"])  # 解析不能は理由つき
    assert "broken" not in json.dumps([e["columns"] for e in m["entities"]], ensure_ascii=False)  # 推測しない


def test_ac181_ddl_only_entity_gets_columns_and_foreign_keys_become_relations(tmp_path):
    repo = make_zoom(tmp_path / "r")
    (repo / "db").mkdir()
    (repo / "db" / "stock.sql").write_text("CREATE TABLE 在庫 (id int primary key, item_id int REFERENCES orders(id));\n", encoding="utf-8")
    m = model(repo)
    cols = {c["name"]: c for c in ents(m)["在庫"]["columns"]}
    assert cols["id"]["key"] == "主キー" and cols["item_id"]["ref"] == "注文.id"
    assert any(r["scope"] == "entity" and (r["from"], r["to"], r["kind"]) == ("在庫", "注文", "外部キー") for r in m["relations"])


def test_ac181_json_schema_supplements_columns(tmp_path):
    repo = make_zoom(tmp_path / "r")
    (repo / "schemas").mkdir()
    (repo / "schemas" / "商品.schema.json").write_text(json.dumps({"title": "商品", "properties": {"sku": {"type": "string"}, "price": {"type": ["number", "null"]}}}), encoding="utf-8")
    cols = {c["name"]: c for c in ents(model(repo))["商品"]["columns"]}
    assert cols["sku"]["type"] == "string" and cols["price"]["type"] == "number|null" and cols["sku"]["origin"] == "補完"


# FR-1030 AC-182: read only, no network, and repositories without such files behave as before
def test_ac182_supplement_does_not_write_and_absent_files_change_nothing(tmp_path):
    repo = make_zoom(tmp_path / "r")
    assert model(repo)["supplement"] == {"files": [], "diagnostics": []}
    (repo / "db").mkdir()
    (repo / "db" / "orders.sql").write_text(DDL, encoding="utf-8")
    before = snapshot(repo)
    model(repo)
    assert snapshot(repo) == before
    src = (SOURCE / "scripts" / "entities.py").read_text(encoding="utf-8")
    block = src[src.index("# --- DDL / JSON Schema supplement"):src.index("def column_model")]
    assert "urllib" not in block and "socket" not in block and "open(" not in block.replace("p.read_text", "")  # 外部通信・書き込みなし
    assert not entity_errors(rdcheck(make_other(tmp_path / "o")))


def test_ac182_unreadable_or_huge_files_are_skipped_with_a_reason(tmp_path):
    repo = make_zoom(tmp_path / "r")
    (repo / "db").mkdir()
    (repo / "db" / "bad.schema.json").write_text("{not json", encoding="utf-8")
    d = model(repo)["supplement"]["diagnostics"]
    assert any(x["file"] == "db/bad.schema.json" and "JSON" in x["reason"] for x in d)
