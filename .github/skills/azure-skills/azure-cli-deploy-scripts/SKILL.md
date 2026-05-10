---
name: azure-cli-deploy-scripts
description: >
  Azure CLI を用いた追加リソースのデプロイスクリプト雛形と共通規約を提供する。USE FOR: azure cli deploy scripts, addservice deployment, idempotent resource creation. DO NOT USE FOR: direct production incident response. WHEN: AddServiceDeploy や他 Deploy Agent で Azure CLI スクリプトを新規作成・更新するとき。
metadata:
  version: 1.0.0
---

# azure-cli-deploy-scripts

## 目的
- AddServiceDeploy を含む Deploy 系 Agent が、Azure CLI スクリプトを安全かつ冪等に作成できるようにする。
- 本 Skill は AddServiceDeploy 専用ではなく、ComputeDeploy / UIDeploy / AgentDeploy / DataDeploy でも参照可能。

## Non-goals（このスキルの範囲外）
- Azure リソースの実運用監視・障害解析
- AC 判定そのもの（`azure-ac-verification` を参照）

## 1. 前提条件（認証・サブスクリプション）
```bash
az login
az account set --subscription "<subscription-id-or-name>"
az account show --output table
```
- 非対話環境では OIDC / Service Principal を利用する。
- 実行前に `az version` と対象 subscription を記録する。

## 2. リソースグループ・リージョン・タグ規約
- スクリプト冒頭で `set -euo pipefail` を必須化する。
- 変数例: `RESOURCE_GROUP`, `LOCATION`, `TAGS`（配列）。
- 最低限のタグ例: `environment`, `project`, `owner`。

```bash
set -euo pipefail
RESOURCE_GROUP="${RESOURCE_GROUP:?RESOURCE_GROUP is required}"
LOCATION="${LOCATION:-japaneast}"
TAGS=("environment=dev" "project=royalyty")
```

## 3. 冪等性パターン（show || create）
- 作成系コマンドは「存在確認 → 無ければ作成」を徹底する。

```bash
az resource show --ids "$RESOURCE_ID" >/dev/null 2>&1 \
  || az <service> create --resource-group "$RESOURCE_GROUP" --location "$LOCATION" --tags "${TAGS[@]}"
```

- サービス固有で `show` 非対応の場合は `list --query` で存在確認する。

## 4. service-catalog 更新手順（AC-5 整合）
- `docs/catalog/service-catalog-matrix.md` を更新する場合、同一サービスID/サービス名の重複追加を禁止する。
- 追記前に既存行を検索し、重複時は更新に切り替える。

## 5. セキュリティ規約（AC-7 整合）
- 鍵・トークン・接続文字列をハードコードしない。
- シークレットは GitHub Secrets / Key Vault / 環境変数から受け取り、ログへ出力しない。

## 6. verify スクリプト連携
- deploy スクリプトと対になる verify スクリプトを同時に用意する。
- verify では `provisioningState` と endpoint の到達性を確認する。
- AC 判定テンプレート・終了コード規約は `azure-ac-verification` を参照する。

## Related Skills
- `azure-ac-verification`: AC 判定と verify 終了コード規約
- `azure-prepare`: デプロイ前の IaC/前提整理
- `azure-validate`: デプロイ前バリデーション
