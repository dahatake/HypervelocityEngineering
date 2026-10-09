"""Tests for EABK Studio: the data-layer parser and the local server. Run: python -m pytest EABK-Studio/tests -q"""
import json
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


# FR-001 AC-001 / FR-009 AC-009
def test_model_integrity_exposes_current_and_ideal_coverage(repo):
    model = m.build_model(repo)
    integrity = model["integrity"]
    assert integrity["current"]["requirements"] == 2
    assert integrity["current"]["cataloged"] == 1
    assert integrity["current"]["implemented"] == 1
    assert integrity["current"]["tested"] == 1
    assert integrity["current"]["openQuestions"] == 1
    assert integrity["current"]["blockedAcceptanceCriteria"] == 1
    assert integrity["ideal"]["catalogedApproved"] == 1
    assert not any(issue["id"] == "FR-001" and issue["kind"] == "ledger"
                   for issue in integrity["issues"])


# FR-013 AC-013
def test_model_integrity_is_derived_without_reading_source_files(repo):
    (repo / "src").mkdir()
    source = repo / "src" / "should-not-be-read.py"
    source.write_text("FR-999 = 'secret'", encoding="utf-8")
    before = source.stat().st_mtime_ns
    model = m.build_model(repo)
    assert model["integrity"]["current"]["requirements"] == 2
    assert source.stat().st_mtime_ns == before
    assert all(node["id"] != "FR-999" for node in model["graph"]["nodes"])


def test_nothing_outside_the_data_layer_is_read(repo):
    (repo / "src").mkdir()
    (repo / "src" / "secret.py").write_text("FR-999 = 'must not be parsed'", encoding="utf-8")
    model = m.build_model(repo)
    assert all(n["id"] != "FR-999" for n in model["graph"]["nodes"])


def test_repository_without_data_layer(tmp_path):
    model = m.build_model(tmp_path)
    assert model["meta"]["error"] == "no-data-layer" and model["reqs"] == []


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
