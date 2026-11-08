"""Tests for FR-1042 (external integration catalog browsing in Studio). Run: python -m pytest EABK-Studio/tests -q"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPO / "tests" / "system"))
import eabk_model as m  # noqa: E402
from entity_repo import make_zoom  # noqa: E402

CATALOG = """# 外部連携カタログ

| ID | 名前 | 連携先 | 方向 | 状態 | 関連する要求 |
|---|---|---|---|---|---|
| INT-001 | 受注 API | 取引先 A | 受信 | 運用中 | FR-001 |

#### INT-001 受注 API
- 連携先: 取引先 A
- 方向: 受信
- 方式: REST
- データ分類: 社外秘
- 個人情報: あり
- 認証認可: OAuth 2.0（秘密の保管場所: 鍵保管庫）
- 責任分界: 当社は受信後
- 状態: 運用中
- 関連する要求: FR-001
- 頻度と量: TBD（Q-001）
- レート制限: なし
- 監視: 
- 備考: password: Sup3rSecretValue99

#### INT-002 在庫ファイル
- 連携先: 倉庫システム B
- 方向: 送信
- 方式: ファイル
- データ分類: 公開
- 個人情報: なし
- 認証認可: TBD（Q-002）
- 責任分界: 当社は出力まで
- 状態: 検討中
- 関連する要求: FR-003
"""


def _repo(tmp_path, catalog=CATALOG):
    repo = make_zoom(tmp_path / "r")
    cfg = repo / "scripts" / "ebak.config.json"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    data["management_files"]["integrations"] = "docs/integrations.md"
    cfg.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if catalog is not None:
        (repo / "docs" / "integrations.md").write_text(catalog, encoding="utf-8")
    return repo


# FR-1042 AC-227 AC-228: one item per integration; 16 viewpoints separate filled / none / TBD / missing, with counts and flags.
def test_ac227_ac228_viewpoints_states_counts_and_flags(tmp_path):
    cat = {c["id"]: c for c in m.build_model(_repo(tmp_path))["integrationCatalog"]}
    assert set(cat) == {"INT-001", "INT-002"}
    a = cat["INT-001"]
    assert len(a["viewpoints"]) == 16
    st = {v["label"]: v["state"] for v in a["viewpoints"]}
    assert st["頻度と量"] == "tbd" and st["レート制限"] == "none" and st["監視"] == "missing" and st["連携先"] == "filled"
    assert a["tbd"] == 1 and a["missing"] == 8 and a["flag"] is True
    assert a["reqs"] == ["FR-001"]
    b = cat["INT-002"]
    assert b["flag"] is True and viewpoint_ok(b)  # auth TBD is flagged even though no personal data


def viewpoint_ok(item):
    return {v["label"]: v["state"] for v in item["viewpoints"]}["認証認可"] == "tbd"


# FR-1042 AC-229: INT nodes link to the requirements and appear in the graph under the same ID.
def test_ac229_graph_has_int_nodes_linked_to_requirements(tmp_path):
    g = m.build_model(_repo(tmp_path))["graph"]
    assert any(n["id"] == "INT-001" and n["type"] == "integration" for n in g["nodes"])
    assert {"s": "FR-001", "t": "INT-001", "rel": "req-int"} in g["edges"]


# FR-1042 AC-230: no catalog / zero items -> empty list, no error or warning.
@pytest.mark.parametrize("catalog", [None, "# 外部連携カタログ\n"])
def test_ac230_no_catalog_or_zero_items_is_empty_without_warnings(tmp_path, catalog):
    model = m.build_model(_repo(tmp_path, catalog))
    assert model["integrationCatalog"] == [] and not model["warnings"] and "error" not in model["meta"]


# FR-1042 AC-231: read-only (file untouched), credential-looking values are not shown.
def test_ac231_read_only_and_secret_value_is_masked(tmp_path):
    repo = _repo(tmp_path)
    p = repo / "docs" / "integrations.md"
    before = (p.read_bytes(), p.stat().st_mtime_ns)
    model = m.build_model(repo)
    assert (p.read_bytes(), p.stat().st_mtime_ns) == before
    assert "Sup3rSecretValue99" not in json.dumps(model, ensure_ascii=False)


# FR-1042 AC-231: a section-8 row with the same partner name (case / spaces ignored) merges into the INT item.
def test_ac231_same_partner_row_is_merged_not_duplicated(tmp_path):
    repo = _repo(tmp_path)
    doc = repo / "docs" / "requirements-definition.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\n| 連携先 | 方式 | 意味 | 正本 | 採番 |\n|---|---|---|---|---|\n|  取引先  A | REST | 受注 | 取引先 | なし |\n| 別の相手 | CSV | 他 | 当社 | なし |\n", encoding="utf-8")
    model = m.build_model(repo)
    assert [x["name"] for x in model["integrations"]] == ["別の相手"]
    int1 = next(c for c in model["integrationCatalog"] if c["id"] == "INT-001")
    assert len(int1["merged"]) == 1
