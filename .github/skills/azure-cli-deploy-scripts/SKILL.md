---
name: azure-cli-deploy-scripts
description: "Azure CLI デプロイスクリプトの共通仕様。prep/create/verify 3点セットテンプレート、冪等性パターン、CLI 利用不可時フォールバック手順を提供する。Deploy Agent が Azure リソース作成スクリプトを生成する際に参照する。"
---

# azure-cli-deploy-scripts

## 目的

Azure リソース作成スクリプトの **共通仕様** を一元管理する。
各 Deploy Agent は本 Skill を参照し、固有のリソース定義のみを Agent 側に記載する。

本 Skill は以下の3パターンを統合して提供する:
- **P-02**: prep / create / verify 3点セットテンプレート
- **P-03**: 冪等性パターン（存在確認→作成→skip）
- **P-13**: Azure CLI 利用不可時フォールバック手順

---

## 1. prep / create / verify 3点セットテンプレート

Azure リソース作成は、以下の3スクリプト構成で実装する。

| スクリプト | 役割 | 命名例 |
|-----------|------|--------|
| `*-prep.sh` | 前提チェック（認証・権限・リソースグループ存在確認） | `create-azure-*-prep.sh` |
| `*-create.sh` または `create-*.sh` | リソースの冪等作成（§2 のパターンに従う） | `create-azure-*.sh` |
| `*-verify.sh` または `verify-*.sh` | 全リソースの存在検証 | `verify-*-resources.sh` |

> **例外**: Agent 固有の事情で prep を省略する場合（例: prep 相当の処理を create 冒頭で実施）は、Agent 側にその旨を明記する。

### 1.1 共通仕様（全スクリプト共通）

以下の仕様は **全スクリプト** に適用する:

1. **`set -euo pipefail`** をスクリプト先頭に記載する
2. 全ての `az` コマンドで **`--output` を明示** し、コマンド種別に応じて `json` / `tsv` / `none` を使い分ける（例: 作成系は `--output none`、値取得・検証系は `--query ... --output tsv`、複雑な出力加工が必要な場合は `--output json`）
3. **パラメータ** はスクリプト引数または環境変数で受け取る（ハードコード禁止）
4. **KEY=VALUE 出力**: 作成・取得した値（URL / Resource ID / リージョン等）は標準出力に `KEY=VALUE` 形式で出力する
   ```
   FUNCTION_APP_URL=https://example.azurewebsites.net
   RESOURCE_ID=/subscriptions/.../resourceGroups/.../providers/...
   REGION=japaneast
   ```
5. **シークレット禁止**: 接続文字列・API キー・パスワード等はスクリプト内にハードコードしない。Key Vault または GitHub Secrets に格納する

### 1.2 prep スクリプトテンプレート

```bash
#!/usr/bin/env bash
set -euo pipefail

# --------------- パラメータ ---------------
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-<デフォルト値>}"
LOCATION="${AZURE_LOCATION:-japaneast}"  # azure-region-policy §1 準拠
MAX_RETRIES=3

# --------------- ヘルパー ---------------
log_info()  { echo "[INFO]  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_error() { echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }

# --------------- チェック ---------------
# 1. Azure CLI インストール確認
command -v az >/dev/null 2>&1 || { log_error "az CLI not found"; exit 1; }

# 2. 認証確認（リトライ付き）
for i in $(seq 1 "$MAX_RETRIES"); do
  if az account show --output json >/dev/null 2>&1; then
    log_info "Azure 認証 OK"
    break
  fi
  [ "$i" -eq "$MAX_RETRIES" ] && { log_error "Azure 認証失敗（${MAX_RETRIES}回リトライ済み）"; exit 1; }
  sleep 2
done

# 3. リソースグループ存在確認 → 存在しない場合は冪等に作成
#    az group exists は true/false を返す。認可エラー等では非ゼロ終了するため区別可能
rg_exists=$(az group exists --name "$RESOURCE_GROUP" 2>/dev/null) || {
  log_error "リソースグループ存在確認に失敗しました（認可エラー/ネットワーク障害の可能性）"
  exit 1
}
if [ "$rg_exists" = "true" ]; then
  log_info "リソースグループ '$RESOURCE_GROUP' 確認 OK（既存）"
else
  log_info "リソースグループ '$RESOURCE_GROUP' が存在しません。作成します（場所: $LOCATION）"
  az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none \
    || { log_error "リソースグループ '$RESOURCE_GROUP' の作成に失敗しました"; exit 1; }
  log_info "リソースグループ '$RESOURCE_GROUP' を作成しました"
fi

log_info "前提チェック完了"
```

### 1.3 create スクリプトテンプレート

```bash
#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-<デフォルト値>}"
LOCATION="${AZURE_LOCATION:-japaneast}"

# --- 冪等作成（§2 参照） ---
# リソースごとに §2 の冪等性パターンを適用する

# --- 出力（作成したリソースの値を後続ステップで利用可能にする） ---
# 例: 以下の変数は冪等作成パターン（§2）の中で取得・設定する
# echo "RESOURCE_NAME=<作成したリソース名>"
# echo "RESOURCE_ID=<取得した Resource ID>"
echo "REGION=${LOCATION}"
```

### 1.4 verify スクリプトテンプレート

```bash
#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-<デフォルト値>}"
PASS=0; FAIL=0

check_resource() {
  local label="$1"
  shift
  if state=$("$@" --query "provisioningState" --output tsv 2>/dev/null); then
    state="${state:-Unknown}"
    if [ "$state" = "Succeeded" ]; then
      echo "[PASS] ${label}: provisioningState=Succeeded"
      ((PASS++))
    else
      echo "[FAIL] ${label}: provisioningState=${state}"
      ((FAIL++))
    fi
  else
    echo "[FAIL] ${label}: リソースが存在しません"
    ((FAIL++))
  fi
}

# --- 検証対象（Agent 固有のリソースを列挙） ---
# check_resource "Resource Group" az group show --name "$RESOURCE_GROUP"
# check_resource "Function App"   az functionapp show --name "..." --resource-group "$RESOURCE_GROUP"

echo "===== 結果: PASS=${PASS} / FAIL=${FAIL} ====="
[ "$FAIL" -eq 0 ] || exit 1
```

---

## 2. 冪等性パターン（存在確認→作成→skip）

Azure リソース作成は **冪等** に実装する。再実行しても副作用が発生しないこと。

### 2.1 疑似コード

```bash
# 冪等作成パターン（リソースごとに適用）
exists=$(az <service> show \
  --name "$RESOURCE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --output json 2>/dev/null || true)

if [ -z "$exists" ]; then
  # 存在しない → 作成
  az <service> create \
    --name "$RESOURCE_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output json
  echo "[CREATE] $RESOURCE_NAME"
else
  # 既に存在 → skip（または必要なら update）
  echo "[SKIP] $RESOURCE_NAME already exists"
fi
```

### 2.2 冪等性チェックリスト

スクリプト作成後、以下を確認する:

- [ ] 各リソースに `show` による存在確認がある
- [ ] 存在しない場合のみ `create` が実行される
- [ ] 既存リソースは `skip` される（または明示的に `update` する場合はその旨をコメントに記載）
- [ ] 2回目の実行で exit code 0 が返る
- [ ] 2回目の実行で重複リソースが作成されない
- [ ] 一時的な API エラー（429 / 503）に対してリトライ（最大3回・指数バックオフ）が実装されている

---

## 3. Azure CLI 利用不可時フォールバック手順

Azure CLI の利用可否は以下の条件により変動し得る:

- `copilot-setup-steps.yml` が **未設定** の場合: Azure CLI は **利用できない**
- `copilot-setup-steps.yml` が **設定済み** の場合: Azure CLI は **利用可能になり得る**（Secrets 未設定・workflow 未実行・login 失敗等で利用不能なケースもある）

最終的な Azure CLI の利用可否は、Agent §0.1 の判定手順（`az account show` の実行結果）で確定すること。

**フォールバックに進む前に、Agent §0.1 の3ステップ判定（Azure MCP Server / `copilot-setup-steps.yml` 存在確認 / `az account show` 実行）を必ず完了すること。**
いずれか1つでも OK であればフォールバックに進んではならない。
以下の手順は、上記3ステップがすべて NG の場合のみ適用する。

### 3.1 フォールバック手順

1. **構文チェック** のみ実施する
   ```bash
   # シェルスクリプトの構文検証
   bash -n infra/azure/<スクリプト名>.sh
   shellcheck infra/azure/<スクリプト名>.sh  # 利用可能な場合
   ```
2. **work-status に記録**: 「Azure CLI 利用不可のため未実行」と記録する
3. **PR description に明記**: 手動実行が必要であることを以下のテンプレートで記載する
4. **README に手順記載**: `infra/` 配下の README に実行手順・前提条件・期待される出力を記載する

### 3.2 PR description テンプレート

```markdown
## ⚠️ Azure リソース未検証（人間による実行が必要）

Azure CLI が利用できない環境のため、Azure リソースの作成・検証が未実施です。
以下のスクリプトを順に実行してください：

1. `infra/azure/<prep スクリプト>`
2. `infra/azure/<create スクリプト>`
3. `infra/azure/<verify スクリプト>`

### 前提条件
- Azure CLI がインストール済みであること
- `az login` で認証済みであること
- 対象リソースグループが存在すること

### 期待される結果
- 全スクリプトが exit code 0 で終了すること
- verify スクリプトの出力で全リソースが `[PASS]` であること
```

### 3.3 構文チェック完了時の判定

- AC のうち「Azure リソース存在確認」は **❌（未検証 — Azure CLI 利用不可）** とする
- 構文チェック通過のみでは「リソースが作成された」とはみなさない
- PR は `[NEEDS-VERIFICATION]` または `[WIP]` 状態で提出する

---

## 参照元

- `work/Issue-skills-migration-investigation/duplication-patterns.md` — P-02, P-03, P-13 の詳細
- `work/Issue-skills-migration-investigation/extraction-candidates.md` — 抽出判定
- `work/Issue-skills-migration-investigation/migration-matrix.md` — GO-1 評価
