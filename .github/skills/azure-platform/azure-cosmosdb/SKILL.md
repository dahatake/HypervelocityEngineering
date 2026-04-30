---
name: azure-cosmosdb
description: "Azure Cosmos DB for NoSQL へのドキュメント登録・クエリ・検証の共通パターン。DefaultAzureCredential を使用した azure-cosmos Python SDK によるデータプレーン操作（CRUD・COUNT）、Shell スクリプトからの呼び出しパターン（quoted heredoc + 環境変数渡し）、結果ファイル書き出し、verify スクリプトとの連携方法を提供する。WHEN: Cosmos DB にサンプルデータを登録する、Cosmos DB 接続スクリプトを書く、DefaultAzureCredential で Cosmos DB に接続する、azure-cosmos SDK を使う、data-registration-script.sh を実装する。"
---

# azure-cosmosdb

## 目的

Azure Cosmos DB for NoSQL へのデータプレーン操作（ドキュメント登録・クエリ・件数検証）を
Shell スクリプトから安全に行うための **共通パターン** を一元管理する。

本 Skill は以下のパターンを提供する:

- **§1 なぜ curl / Bearer token が使えないか（必読）**
- **§2 SDK セットアップ（pip install バージョン指定）**
- **§3 Shell から Python SDK を呼び出すパターン（quoted heredoc）**
- **§4 ドキュメント登録パターン（upsert + 件数検証 + 結果ファイル書き出し）**
- **§5 件数クエリパターン（COUNT(1) — verify スクリプト用フォールバック）**
- **§6 verify スクリプトとの連携パターン（結果ファイル参照 → 直接クエリ）**

---

## §1 なぜ curl / Bearer token が使えないか（必読）

**Cosmos DB data plane は Bearer token（`az account get-access-token` で取得できる OAuth2 トークン）を受け付けない。**

Cosmos DB REST API の `Authorization` ヘッダーには **HMAC-SHA256 署名**（`type=master` または `type=resource`）が必要であり、Bearer token を渡すと必ず **HTTP 401** になる。

> 参考: [Azure Cosmos DB REST API — Authorization](https://learn.microsoft.com/en-us/rest/api/cosmos-db/access-control-on-cosmosdb-resources)

**解決策**: `azure-cosmos` Python SDK を使用する。SDK 内部で `DefaultAzureCredential` をサポートしており、RBAC ロール（`Cosmos DB Built-in Data Contributor` 等）が付与されていれば認証が通る。

```
# NG: curl + Bearer token → 必ず HTTP 401
curl -H "Authorization: Bearer $(az account get-access-token --query accessToken -o tsv)" ...

# OK: azure-cosmos SDK + DefaultAzureCredential
python3 - <<'PYEOF'
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
client = CosmosClient(endpoint, credential=DefaultAzureCredential())
...
PYEOF
```

---

## §2 SDK セットアップ（pip install バージョン指定）

### インストールコマンド

```bash
pip install "azure-cosmos>=4.7,<5" "azure-identity>=1.16,<2" --quiet
```

- バージョン範囲指定を必須とする（無指定では破壊的変更の取り込みリスクがある）
- `--quiet` でログを抑制（CI ログ汚染防止）

### スクリプト先頭での確認パターン

```bash
if ! python3 -c "import azure.cosmos, azure.identity" 2>/dev/null; then
  log_info "azure-cosmos / azure-identity をインストールします..."
  pip install "azure-cosmos>=4.7,<5" "azure-identity>=1.16,<2" --quiet || {
    log_error "pip install が失敗しました"
    exit 1
  }
fi
```

---

## §3 Shell から Python SDK を呼び出すパターン（quoted heredoc）

### ルール

1. **quoted heredoc `<<'PYEOF'` を使用する**（unquoted `<<PYEOF` はシェル変数が展開されインジェクションリスクがある）
2. **シェル変数は `export PY_*` として環境変数でPython に渡す**（heredoc 内への直接埋め込みは禁止）
3. `python3 -` で stdin から読む

### テンプレート

```bash
# シェル変数を PY_ プレフィックスで export
export PY_COSMOS_ENDPOINT="https://${COSMOS_ACCOUNT}.documents.azure.com"
export PY_COSMOS_DB="${COSMOS_DB}"
export PY_COSMOS_CONTAINER="${COSMOS_CONTAINER}"
export PY_RESULT_FILE="${RESULT_FILE}"

python3 - <<'PYEOF'
import os
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

endpoint   = os.environ["PY_COSMOS_ENDPOINT"]
db_name    = os.environ["PY_COSMOS_DB"]
cont_name  = os.environ["PY_COSMOS_CONTAINER"]

cred      = DefaultAzureCredential()
client    = CosmosClient(endpoint, credential=cred)
db        = client.get_database_client(db_name)
container = db.get_container_client(cont_name)

# ... 処理 ...
PYEOF
PYRC=$?
[ "${PYRC}" -eq 0 ] || { log_error "Python SDK 呼び出しが失敗しました (exit ${PYRC})"; exit 1; }
```

---

## §4 ドキュメント登録パターン（upsert + 件数検証 + 結果ファイル書き出し）

### 完全テンプレート

```bash
# パラメータ
COSMOS_ACCOUNT="${COSMOS_ACCOUNT:-<account-name>}"
COSMOS_DB="${COSMOS_DB:-<database-name>}"
COSMOS_CONTAINER="${COSMOS_CONTAINER:-<container-name>}"
DOCS_DIR="/tmp/<service>-samples"
RESULT_FILE="${TMPDIR:-/tmp}/<service>-reg-result.txt"
EXPECTED=3  # 登録期待件数（shell 側のみで管理。Python 結果ファイルには含めない）

# 環境変数として export
export PY_COSMOS_ENDPOINT="https://${COSMOS_ACCOUNT}.documents.azure.com"
export PY_COSMOS_DB="${COSMOS_DB}"
export PY_COSMOS_CONTAINER="${COSMOS_CONTAINER}"
export PY_DOCS_DIR="${DOCS_DIR}"
export PY_RESULT_FILE="${RESULT_FILE}"

python3 - <<'PYEOF'
import json, sys, os, glob, datetime
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

endpoint   = os.environ["PY_COSMOS_ENDPOINT"]
db_name    = os.environ["PY_COSMOS_DB"]
cont_name  = os.environ["PY_COSMOS_CONTAINER"]
docs_dir   = os.environ["PY_DOCS_DIR"]
result_file = os.environ["PY_RESULT_FILE"]

cred      = DefaultAzureCredential()
client    = CosmosClient(endpoint, credential=cred)
container = client.get_database_client(db_name).get_container_client(cont_name)

inserted = 0
failed   = 0

for doc_file in sorted(glob.glob(os.path.join(docs_dir, "*.json"))):
    with open(doc_file, "r", encoding="utf-8") as f:
        doc = json.load(f)
    doc_id    = doc.get("id")
    partition = doc.get("<partition-key-field>")  # フィールド名は実装に合わせる
    if not doc_id:
        print(f"[ERROR] id が空 ({doc_file})", file=sys.stderr)
        failed += 1
        continue
    if not partition:
        print(f"[ERROR] partition key が空 ({doc_file})", file=sys.stderr)
        failed += 1
        continue
    try:
        container.upsert_item(doc)
        print(f"[INFO]  [OK] id={doc_id}")
        inserted += 1
    except exceptions.CosmosHttpResponseError as e:
        print(f"[ERROR] [FAIL] id={doc_id}: {e.status_code} {e.message}", file=sys.stderr)
        failed += 1

# 結果ファイルに書き出す（verify スクリプトが参照）
# EXPECTED は shell 側で管理するため、結果ファイルには書き出さない
ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
with open(result_file, "w", encoding="utf-8") as rf:
    rf.write(f"SERVICE=CosmosDB\n")
    rf.write(f"CONTAINER={cont_name}\n")
    rf.write(f"INSERTED={inserted}\n")
    rf.write(f"FAILED={failed}\n")
    rf.write(f"TIMESTAMP={ts}\n")

print(f"\n登録済み: {inserted}、失敗: {failed}")

if failed > 0:
    # INSERTED < EXPECTED の最終判定は shell 側で行う
    print(f"[WARN]  {failed} 件失敗", file=sys.stderr)
sys.exit(0)
PYEOF
PYRC=$?
[ "${PYRC}" -eq 0 ] || { log_error "Python SDK 登録処理が失敗しました"; exit 1; }

# 結果ファイルから INSERTED を読み取って最終判定
INSERTED=$(grep '^INSERTED=' "${RESULT_FILE}" 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || echo 0)
if [ "${INSERTED}" -ge "${EXPECTED}" ]; then
  log_info "[OK] 登録件数 ${INSERTED}/${EXPECTED} 件"
else
  log_error "[FAIL] 登録件数 ${INSERTED}/${EXPECTED} 件（期待値未達）"
  exit 1  # 部分登録を成功扱いにしない
fi
```

### 重要なルール

| ルール | 理由 |
|-------|------|
| `INSERTED < EXPECTED` の場合は `exit 1` | 部分登録を成功扱いにしない（CI で偽陽性を防ぐ） |
| `EXPECTED` は shell 変数のみで管理 | Python 結果ファイルに `EXPECTED` を書くと二重管理になる |
| `partition key` が空なら即 FAIL | 空の partition key でアップサートすると予期しないパーティションに書き込まれる |

---

## §5 件数クエリパターン（COUNT(1) — verify スクリプト用フォールバック）

```bash
export PY_TC_ENDPOINT="https://${COSMOS_ACCOUNT}.documents.azure.com"
export PY_TC_DB="${COSMOS_DB}"
export PY_TC_CONTAINER="${COSMOS_CONTAINER}"

cosmos_count=$(python3 - <<'PYCOUNT'
import os, sys
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
try:
    client    = CosmosClient(os.environ["PY_TC_ENDPOINT"], credential=DefaultAzureCredential())
    container = client.get_database_client(os.environ["PY_TC_DB"]) \
                      .get_container_client(os.environ["PY_TC_CONTAINER"])
    items = list(container.query_items(
        "SELECT VALUE COUNT(1) FROM c",
        enable_cross_partition_query=True
    ))
    print(items[0] if items else 0)
except Exception as e:
    print(f"[ERROR] {e}", file=sys.stderr)
    sys.exit(1)
PYCOUNT
)
cosmos_rc=$?
if [ "${cosmos_rc}" -ne 0 ] || [ -z "${cosmos_count}" ]; then
  echo "[FAIL] Cosmos DB への COUNT クエリが失敗しました"
  FAIL=$((FAIL+1))
elif [ "${cosmos_count}" -ge "${EXPECTED_INSERTED}" ]; then
  echo "[PASS] Cosmos DB データ確認 OK (COUNT=${cosmos_count})"
  PASS=$((PASS+1))
else
  echo "[FAIL] Cosmos DB 件数不足 (COUNT=${cosmos_count}, 期待>=${EXPECTED_INSERTED})"
  FAIL=$((FAIL+1))
fi
```

---

## §6 verify スクリプトとの連携パターン（結果ファイル参照 → 直接クエリ）

`verify-data-resources.sh` の TC（データ登録確認）では以下の2段階パターンを使用する:

```bash
REG_RESULT_FILE="${TMPDIR:-/tmp}/<service>-reg-result.txt"
EXPECTED_INSERTED=3

if [ -f "${REG_RESULT_FILE}" ]; then
  # 1st: 登録スクリプトの結果ファイルを参照
  actual=$(grep -E "^INSERTED=" "${REG_RESULT_FILE}" | cut -d= -f2 | tr -d '[:space:]')
  if [ -z "${actual}" ]; then
    echo "[FAIL] TC-XX: 結果ファイルに INSERTED 行が見つかりません (${REG_RESULT_FILE})"
    FAIL=$((FAIL+1))
  elif [ "${actual}" -ge "${EXPECTED_INSERTED}" ]; then
    echo "[PASS] TC-XX: データ登録確認 OK (INSERTED=${actual})"
    PASS=$((PASS+1))
  else
    echo "[FAIL] TC-XX: 登録件数不足 (INSERTED=${actual}, 期待=${EXPECTED_INSERTED})"
    FAIL=$((FAIL+1))
  fi
else
  # 2nd: 結果ファイル不在時は Cosmos DB を直接クエリ（フォールバック）
  # ※ CI 再実行時・別セッションで verify のみ実行する場合に必要
  if ! python3 -c "import azure.cosmos, azure.identity" 2>/dev/null; then
    echo "[FAIL] TC-XX: 結果ファイルなし & azure-cosmos SDK 未インストール"
    echo "       先に data-registration-script.sh を実行してください"
    FAIL=$((FAIL+1))
  else
    # §5 の COUNT クエリパターンを使用
    # （上記 §5 のコードブロックをここに配置する）
    ...
  fi
fi
```

### なぜ2段階パターンか

| 状況 | 動作 |
|------|------|
| 登録スクリプトと verify を同一セッションで連続実行 | 結果ファイルを参照（高速・SDK 再認証不要） |
| CI 再実行 / 別セッションで verify のみ実行 | Cosmos DB への直接クエリ（フォールバック）で件数を確認 |
| SDK 未インストール & 結果ファイルなし | FAIL（インストール案内を出す） |

---

## §7 前提条件（RBAC 設定）

- Cosmos DB へのデータプレーン書き込みには **`Cosmos DB Built-in Data Contributor`** ロールが必要
- ロールは Control Plane の RBAC ではなく **Cosmos DB 固有のデータプレーン RBAC** で付与する

```bash
# objectId（GUID）を確実に取得する
# - Service Principal: az account show --query user.name は clientId (GUID) を返すためそのまま使用可能
# - ユーザー / UPN: az ad user show で objectId を取得する
_USER_OR_CLIENT_ID=$(az account show --query user.name -o tsv)
if [[ "${_USER_OR_CLIENT_ID}" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
  # GUID 形式 → Service Principal の clientId としてそのまま使用
  PRINCIPAL_ID="${_USER_OR_CLIENT_ID}"
else
  # UPN / 表示名 → az ad user show で objectId を取得
  PRINCIPAL_ID=$(az ad user show --id "${_USER_OR_CLIENT_ID}" --query id -o tsv 2>/dev/null \
    || az ad signed-in-user show --query id -o tsv 2>/dev/null)
fi

SUBSCRIPTION_ID=$(az account show --query id -o tsv)

az cosmosdb sql role assignment create \
  --account-name "${COSMOS_ACCOUNT}" \
  --resource-group "${RESOURCE_GROUP}" \
  --role-definition-name "Cosmos DB Built-in Data Contributor" \
  --principal-id "${PRINCIPAL_ID}" \
  --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.DocumentDB/databaseAccounts/${COSMOS_ACCOUNT}" \
  --output none
```

> **注意**: RBAC ロール付与後、反映に最大 **15分** かかることがある。付与直後に接続すると 403 / 401 になる場合は数分待ってから再実行すること。

---

## §8 この Skill を参照すべき Agent

| Agent | 参照する Skill §§ |
|-------|-----------------|
| `Dev-Microservice-Azure-DataDeploy` | §1 §2 §3 §4 §6 §7 |
| `Dev-Microservice-Azure-DataDesign` | §1 §7（設計時の認証方式判断） |
| `Dev-Batch-ServiceCoding` | §2 §3 §5（Cosmos DB を読み取るバッチ実装） |
| `Dev-Batch-DataDeploy` | §4 §6（バッチデータ登録・検証） |

新しく Cosmos DB のデータプレーン操作が必要な Agent は本 Skill の §1〜§7 を参照すること。
