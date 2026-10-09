"""Tests for EABK Studio: the data-layer parser and the local server. Run: python -m pytest EABK-Studio/tests -q"""
import json
import hashlib
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import eabk_model as m  # noqa: E402
import studio  # noqa: E402

RD = """# 要求定義書

## 1. 概要

### 1.2 目的

| ID | 目的 | 成功指標 | 測定方法 |
|---|---|---|---|
| G-001 | 申請を受け付ける | 合格 | 受入基準 |

## 3. 前提

### 3.2 パラメータ（PARAM）

| ID | 名前 | 値 | 単位 | 根拠 | 決定状態 |
|---|---|---|---|---|---|
| PARAM-001 | 保持期間 | 30 | 日 | 依頼 | 承認済み |

### 3.3 用語

| 用語 | 定義 | 禁止同義語 |
|---|---|---|
| 申請 | 利用者が出す書類 | 申込 |

### 3.4 状態

| 対象エンティティ | 状態 | 遷移の条件 |
|---|---|---|
| 申請 | 下書き | 入力開始 |
| 申請 | 提出済み | 提出 |

## 4. ペルソナ

### 4.1 ペルソナ

| ペルソナ | 業務 | 主要な判断 | 使うデータ | 判断の頻度と緊急度 | 役割 | 出典 |
|---|---|---|---|---|---|---|
| 申請者 | 申請する | 提出時期 | 申請 | 随時 | 一般 | SRC-001 |

## 6. 要求

#### FR-001 申請の下書き保存
- 要求: 申請者は、入力を中断したときに、下書きを保存できる。
- 決定状態: 承認済み（依頼 2026-10-08）　出自: 依頼原文　優先度: MUST（離脱防止）
- 上位: G-001　出典: SRC-001
- 対象エンティティ: 申請　関係する状態: 下書き　参照パラメータ: PARAM-001
- 関連する既存資産: 共通部品「下書き保存」
- 受入基準 AC-001: 保存した下書きが再表示される。
  - 検証レベル: system
- 受入基準 AC-002: 保持期間を過ぎると消える。
  - 検証レベル: integration
  - BLOCKED: Q-001（起点が未定）

#### NFR-SEC-001 通信の暗号化
- 要求: システムは、通信するときに、TLS を使う。FR-001 と同じ経路。
- 決定状態: AI提案／承認待ち　出自: AI提案　優先度: SHOULD（常識）
- 上位: G-001
- 対象エンティティ: なし　関係する状態: なし　参照パラメータ: なし
- 関連する既存資産: なし

## 8. 外部連携

| 連携先 | 方式 | 情報の意味・方向・頻度 | 正本のシステムと識別子 | 自システムの採番 |
|---|---|---|---|---|
| 決済サービス | HTTPS | 決済の依頼 | 決済 | なし |

### 10.1 質問票

| ID | 重要度 | 質問 | 選択肢 | 推奨 | 状態 | 回答 |
|---|---|---|---|---|---|---|
| Q-001 | 高 | 起点はいつか | A / B | A | 未回答 | |
"""

CATALOG = """# カタログ

## 機能

| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |
|---|---|---|---|---|---|
| FR-001 | 申請の下書き保存 | 承認済み | src/app.core/Drafts/Service.cs, src/app.web/Drafts.tsx | tests/unit/DraftsTests.cs | 下書き保存 |
| NFR-SEC-001 | 通信の暗号化 | AI提案／承認待ち | 未実装 | 未実装 | なし |

## API・イベント

| 名前 | 定義ファイル | 関連する要求 ID |
|---|---|---|
| POST /drafts | src/app.core/Api/Drafts.cs | FR-001 |

## テーブル

| テーブル名 | 定義ファイル | 正本のシステム | 関連する要求 ID |
|---|---|---|---|
| drafts | db/schema.sql | 自システム | FR-001 |

## 共通部品

| 部品名 | ファイル | 用途 | 使っている要求 ID |
|---|---|---|---|
| 下書き保存 | src/app.core/Drafts/Store.cs | 下書きを保存する | FR-001 |
"""

LEDGER = {"version": 1, "cases": [{"id": "E2E-001", "requirement_ids": ["FR-001"], "ac_ids": ["AC-001"], "title": "下書き", "layer": "e2e",
                                   "command": "pytest tests/system/test_drafts.py", "status": "pass", "last_run_at": "2026-10-08T10:00:00+09:00"}]}


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "requirements-definition.md").write_text(RD, encoding="utf-8")
    (tmp_path / "docs" / "catalog.md").write_text(CATALOG, encoding="utf-8")
    (tmp_path / "tests" / "system").mkdir(parents=True)
    (tmp_path / "tests" / "system" / "ledger.json").write_text(json.dumps(LEDGER), encoding="utf-8")
    return tmp_path


def test_requirements_and_acceptance_criteria(repo):
    model = m.build_model(repo)
    reqs = {r["id"]: r for r in model["reqs"]}
    assert set(reqs) == {"FR-001", "NFR-SEC-001"}
    fr = reqs["FR-001"]
    assert fr["statusKind"] == "approved" and fr["priority"] == "MUST" and fr["goal"] == "G-001"
    assert fr["entities"] == ["申請"] and fr["params"] == ["PARAM-001"]
    assert [a["id"] for a in fr["acs"]] == ["AC-001", "AC-002"]
    assert fr["acs"][0]["level"] == "system" and fr["acs"][1]["blocked"].startswith("Q-001")
    assert fr["blocked"] == ["Q-001"]
    assert reqs["NFR-SEC-001"]["statusKind"] == "proposed" and reqs["NFR-SEC-001"]["cat"] == "SEC"


# FR-1006 AC-050: explicit entity relationships are evidence; missing ones remain empty.
def test_entity_relationships_are_explicit_only(repo):
    path = repo / "docs" / "requirements-definition.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "- 関連する既存資産: 共通部品「下書き保存」",
        "- 関連する既存資産: 共通部品「下書き保存」\n- 関係: 申請 1 -- * 明細",
    ), encoding="utf-8")
    model = m.build_model(repo)
    reqs = {r["id"]: r for r in model["reqs"]}
    assert reqs["FR-001"]["relation"] == "申請 1 -- * 明細"
    assert reqs["NFR-SEC-001"]["relation"] == ""


# FR-1002 AC-044 / FR-1003 AC-045 / FR-1005 AC-048 / FR-1006 AC-049 AC-050 AC-051
def test_decision_views_define_personas_and_evidence_renderers():
    source = (ROOT / "web" / "js" / "insights.js").read_text(encoding="utf-8")
    for persona in ("Product Manager", "Architect", "Software Engineer"):
        assert persona in source
    for route in ("dashboard", "map2d", "map3d", "diagrams", "placement", "source", "tables"):
        assert f"{route}:" in source
    for term in (
        "現状", "理想", "適用規則", "判定理由", "根拠",
        "外部／クラウド境界",
        "層一貫性ビューアー", "Entity 向け ER 図", "測定時点",
    ):
        assert term in source
    assert "analysis.layers.map" in source
    assert "analysis.differences.map" in source
    assert "runtime.components.map" in source


# FR-1003 AC-045 / FR-1005 AC-048 / FR-1006 AC-051
def test_management_analysis_is_derived_from_parsed_records(repo):
    model = m.build_model(repo)
    structure = model["analysis"]["structure"]
    assert {layer["name"] for layer in structure["layers"]} == {
        "要求定義書", "境界別要求", "カタログ", "System Test", "ID 台帳", "実行履歴", "境界間",
    }
    assert all(all(layer[key] for key in ("actual", "ideal", "delta", "rule", "reason", "source"))
               for layer in structure["layers"])
    valid = next(d for d in structure["differences"] if d["kind"] == "妥当")
    assert valid["target"] == "ID / 位置: FR-001"
    assert valid["actual"] and valid["ideal"] and valid["rule"] and valid["reason"] and valid["source"]

    runtime = model["analysis"]["runtime"]
    assert any(component["name"] == "ブラウザー" for component in runtime["components"])
    assert any(component["name"] == "Studio サーバー" for component in runtime["components"])
    assert any("docs/requirements-definition.md" in flow["source"] for flow in runtime["flows"])
    assert runtime["boundaries"][0]["name"] == "決済サービス"
    assert runtime["boundaries"][0]["source"].startswith("docs/requirements-definition.md:")
    assert model["cases"][0]["status"] == "pass"
    assert model["meta"]["generatedAt"]


# FR-1003 AC-045: individual System Test records enforce parent, digest,
# duplicate, and cross-boundary constraints instead of using aggregate counts.
def test_structure_uses_individual_system_test_and_boundary_constraints(repo):
    ledger_path = repo / "tests" / "system" / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    digest = "sha256:" + hashlib.sha256("保存した下書きが再表示される。".encode("utf-8")).hexdigest()[:16]
    ledger["ac_digests"] = {"AC-001": digest}
    ledger["cases"].append({
        **ledger["cases"][0],
        "requirement_ids": ["NFR-SEC-001"],
    })
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    model = m.build_model(repo)
    rows = model["analysis"]["structure"]["differences"]
    system_rows = [row for row in rows if row["layer"] == "System Test"]
    assert any(row["kind"] == "重複" and "E2E-001" in row["target"] for row in system_rows)
    assert any(row["kind"] == "参照不整合" and row["rule"] == "親子制約" for row in system_rows)
    assert all(all(row[key] for key in ("actual", "ideal", "delta", "rule", "reason", "source"))
               for row in system_rows)
    boundary = next(row for row in rows if row["layer"] == "境界間")
    assert boundary["target"] == "ID / 位置: 決済サービス"
    assert boundary["rule"] == "境界間制約"
    assert "方式=HTTPS" in boundary["actual"] and "正本=決済" in boundary["actual"]


# FR-1005 AC-048: management data and implementation paths are separate
# file-level nodes with location, access direction, and evidence.
def test_runtime_has_file_level_management_and_implementation_nodes(repo):
    runtime = m.build_model(repo)["analysis"]["runtime"]
    management = [node for node in runtime["components"] if node.get("kind") == "management"]
    implementations = [node for node in runtime["components"] if node.get("kind") == "implementation"]
    assert {node["data"] for node in management} >= {
        "docs/requirements-definition.md", "docs/catalog.md", "tests/system/ledger.json",
    }
    assert {node["data"] for node in implementations} >= {
        "src/app.core/Drafts/Service.cs", "src/app.web/Drafts.tsx",
    }
    assert all(node["runsAt"] == "対象リポジトリ" and node["access"] and node["source"]
               for node in management + implementations)
    assert all(any(flow["data"] == node["data"] and flow["direction"] for flow in runtime["flows"])
               for node in management + implementations)


# FR-1006 AC-051: every required category and state exposes individual records
# carrying state/time and an exact clickable file:line destination.
def test_history_has_individual_evidence_records_for_every_progress_category(repo):
    requirements = repo / "docs" / "requirements-definition.md"
    requirements.write_text(requirements.read_text(encoding="utf-8") + """

## 決定記録
| 日付 | 対象ID | 決定 | 根拠 | run-id |
|---|---|---|---|---|
| 2026-10-08 | FR-001 | 承認 | 依頼 | run-1 |
| 2026-10-09 | FR-001 | 継続 | 再確認 | run-2 |
""", encoding="utf-8")
    (repo / "docs" / "run-history.md").write_text(
        "# 実行履歴\n| run-id | 開始 | 終了 | 結果 |\n|---|---|---|---|\n"
        "| run-1 | 2026-10-08T09:00:00+09:00 | 2026-10-08T10:00:00+09:00 | 完了 |\n"
        "| run-2 | 2026-10-09T09:00:00+09:00 |  | 失敗 |\n",
        encoding="utf-8",
    )
    ledger = json.loads((repo / "tests" / "system" / "ledger.json").read_text(encoding="utf-8"))
    ledger["cases"].append({**ledger["cases"][0], "id": "E2E-002", "status": "not_run",
                            "last_run_at": None})
    (repo / "tests" / "system" / "ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

    model = m.build_model(repo)
    records = model["analysis"]["history"]
    required_states = {
        "決定記録": {"承認", "継続"},
        "実行履歴": {"完了", "失敗"},
        "実装登録": {"登録済み", "未登録"},
        "System Test": {"pass", "not_run"},
    }
    for category, states in required_states.items():
        assert {record["status"] for record in records if record["category"] == category} == states
    run_records = {record["id"]: record for record in records if record["category"] == "実行履歴"}
    assert run_records["run-1"]["date"] == "2026-10-08T10:00:00+09:00"
    assert run_records["run-2"]["date"] == "2026-10-09T09:00:00+09:00"
    assert any(record["category"] == "System Test" and record["status"] == "pass"
               and record["date"] == "2026-10-08T10:00:00+09:00" for record in records)
    required_records = [record for record in records if record["category"] in required_states]
    assert all(record["id"] and record["status"] and record["file"] and record["line"]
               for record in required_records)


# FR-1003 AC-045 / FR-1006 AC-051: summaries render all judgement fields and
# each evidence record uses its own VS Code file:line destination.
def test_summary_and_history_renderers_expose_complete_click_targets():
    source = (ROOT / "web" / "js" / "insights.js").read_text(encoding="utf-8")
    for field in ("layer.actual", "layer.ideal", "layer.delta", "layer.rule",
                  "layer.reason", "layer.source"):
        assert field in source
    assert "category.groups" in source
    helper = re.search(
        r"export function evidenceTarget\(record\) \{.*?^\}", source, re.MULTILINE | re.DOTALL
    ).group(0).replace("export function", "function")
    script = f"""
      const vscodeUrl = (file, line) => `vscode://${{file}}:${{line}}`;
      {helper}
      console.log(JSON.stringify(evidenceTarget({{
        category: "System Test", status: "not_run",
        file: "tests/system/ledger.json", line: 42
      }})));
    """
    target = json.loads(subprocess.check_output(
        ["node", "-e", script],
        text=True,
    ))
    assert target == {
        "label": "tests/system/ledger.json:42",
        "href": "vscode://tests/system/ledger.json:42",
    }


def test_tables_are_classified(repo):
    model = m.build_model(repo)
    assert [g["id"] for g in model["goals"]] == ["G-001"]
    assert model["params"][0]["value"] == "30"
    assert model["questions"][0]["state"] == "未回答"
    assert model["personas"][0]["name"] == "申請者"
    assert model["integrations"][0]["name"] == "決済サービス"
    sm = model["stateMachines"][0]
    assert sm["entity"] == "申請" and sm["states"] == ["下書き", "提出済み"]
    assert sm["transitions"][0]["from"] == "下書き" and sm["transitions"][0]["to"] == "提出済み"


def test_catalog_maps_requirements_to_source(repo):
    model = m.build_model(repo)
    nodes = {n["id"]: n for n in model["graph"]["nodes"]}
    edges = {(e["s"], e["t"], e["rel"]) for e in model["graph"]["edges"]}
    assert nodes["FR-001"]["impl"] == "done" and nodes["NFR-SEC-001"]["impl"] == "none"
    f = "file:src/app.core/Drafts/Service.cs"
    assert ("FR-001", f, "req-file") in edges
    assert nodes[f]["comp"] == "src/app.core" and nodes[f]["module"] == "src/app.core/Drafts"
    assert ("FR-001", "file:tests/unit/DraftsTests.cs", "req-test") in edges
    assert nodes["file:tests/unit/DraftsTests.cs"]["role"] == "test"
    assert ("FR-001", "part:下書き保存", "req-part") in edges
    assert ("part:下書き保存", "file:src/app.core/Drafts/Store.cs", "part-file") in edges
    assert ("api:POST /drafts", "file:src/app.core/Api/Drafts.cs", "def-file") in edges
    assert ("tbl:drafts", "file:db/schema.sql", "def-file") in edges
    assert ("FR-001", "api:POST /drafts", "req-api") in edges
    assert ("FR-001", "E2E-001", "req-case") in edges and ("AC-001", "E2E-001", "ac-case") in edges
    assert ("NFR-SEC-001", "FR-001", "ref") in edges


def test_nothing_outside_the_data_layer_is_read(repo):
    (repo / "src").mkdir()
    (repo / "src" / "secret.py").write_text("FR-999 = 'must not be parsed'", encoding="utf-8")
    model = m.build_model(repo)
    assert all(n["id"] != "FR-999" for n in model["graph"]["nodes"])


def test_repository_without_data_layer(tmp_path):
    model = m.build_model(tmp_path)
    assert model["meta"]["error"] == "no-data-layer" and model["reqs"] == []


# FR-001 AC-001: the model exposes every management-data source for traceability.
def test_model_exposes_management_data_sources(repo):
    model = m.build_model(repo)
    assert model["meta"]["files"]["requirements"] == "docs/requirements-definition.md"
    assert model["meta"]["files"]["catalog"] == "docs/catalog.md"
    assert model["meta"]["files"]["ledger"] == "tests/system/ledger.json"
    assert model["catalog"]["features"][0]["req"] == "FR-001"


# FR-009 AC-009: history, current model data, and integrity records share one model.
def test_model_includes_history_and_integrity_records(repo):
    (repo / "docs" / "run-history.md").write_text(
        "# 実行履歴\n\n| run | 日付 | 状態 |\n|---|---|---|\n| run-1 | 2026-10-09 | 成功 |\n",
        encoding="utf-8",
    )
    model = m.build_model(repo)
    assert model["meta"]["files"]["run_history"] == "docs/run-history.md"
    assert isinstance(model["runs"], list)
    assert model["reqs"][0]["acs"][0]["id"] == "AC-001"


def test_expand_ids_handles_ranges_and_lists():
    known = {f"FR-{n:03d}" for n in range(100, 140)}
    assert m.expand_ids("FR-102〜104、FR-110", known) == ["FR-102", "FR-103", "FR-104", "FR-110"]
    assert m.expand_ids("FR-105・131・132", known) == ["FR-105", "FR-131", "FR-132"]
    assert m.expand_ids("FR-200〜202", known) == []


def test_state_chain_with_alternatives():
    sm = {"entity": "run", "states": [], "transitions": []}
    m.chain(sm, "新規→実行中→完了／取消", "")
    assert sm["states"] == ["新規", "実行中", "完了", "取消"]
    assert {(t["from"], t["to"]) for t in sm["transitions"]} == {("新規", "実行中"), ("実行中", "完了"), ("実行中", "取消")}


def test_config_overrides_file_locations(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "ebak.config.json").write_text(json.dumps({"management_files": {"catalog": "meta/cat.md"}}), encoding="utf-8")
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "cat.md").write_text(CATALOG, encoding="utf-8")
    model = m.build_model(tmp_path)
    assert len(model["catalog"]["features"]) == 2


def test_find_root_walks_up(repo):
    sub = repo / "src" / "deep"
    sub.mkdir(parents=True)
    assert m.find_root(sub) == repo.resolve()


@pytest.fixture()
def server(repo):
    studio.STATE = studio.State(repo)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), studio.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_server_serves_model_and_static_files(server):
    status, body = get(server + "/api/model")
    assert status == 200 and json.loads(body)["reqs"][0]["id"] == "FR-001"
    assert get(server + "/")[0] == 200
    assert get(server + "/js/app.js")[0] == 200


def test_server_blocks_path_traversal_and_foreign_hosts(server):
    assert get(server + "/..%2Fstudio.py")[0] == 404
    assert get(server + "/api/model", {"Host": "evil.example"})[0] == 403


def test_server_switch_repo_needs_header_and_a_data_layer(server, tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp('other')
    def post(payload, headers):
        req = urllib.request.Request(server + "/api/repo", data=json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
    assert post({"path": str(tmp_path)}, {}) == 403
    empty = tmp_path / "empty"
    empty.mkdir()
    assert post({"path": str(empty)}, {"X-EABK-Studio": "1"}) == 422
    assert post({"path": str(tmp_path / "nope")}, {"X-EABK-Studio": "1"}) == 400
