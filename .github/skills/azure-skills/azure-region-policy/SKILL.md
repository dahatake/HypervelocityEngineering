---
name: azure-region-policy
description: >
  Azure リージョン選択ポリシー。リポジトリ標準の japaneast 優先、サービス非対応時の fallback、対応 location 確認、例外理由の記録要件を定義する。 USE FOR: Azure region selection, location fallback, region availability checks. DO NOT USE FOR: Azure リソース作成スクリプト、リージョンごとの価格・SLA 断定、実デプロイ実行。 WHEN: Azure リソースの location を決める、または fallback 理由を成果物へ記録するとき。
metadata:
  origin: user
  version: 1.0.0
---

# azure-region-policy

## 目的

Azure リソースの location 選択を、リポジトリ内で一貫して扱うためのポリシーを定義する。Agent はリージョンを推測で決めず、既存要件・サービス対応 location・利用者地域・データ所在地・可用性の観点を確認し、fallback した場合は理由を成果物に残す。

## 適用対象

- Azure リソース作成スクリプトの `LOCATION` / `AZURE_LOCATION` / `--location`
- Azure Functions / Static Web Apps / データストア / 追加 Azure サービスの location 選択
- `docs/azure/*`、`docs/catalog/service-catalog-matrix.md`、`ac-verification.md` への location 記録

## Non-goals

- Azure サービスの最新対応リージョン一覧を本 Skill に固定しない。必ず Azure CLI / Microsoft Learn / Azure Portal 等で確認する。
- 価格、可用性ゾーン、SLA、データ所在地を根拠なく断定しない。
- 実際のデプロイ操作は `azure-cli-deploy-scripts` または各 Deploy Agent が担う。

## 公式根拠

本 Skill の確認手段は以下の Microsoft Learn 確認事項に基づく。

| 確認事項 | Microsoft Learn |
|---|---|
| 現在のサブスクリプションでサポートされるリージョン一覧は `az account list-locations` で取得できる。 | [az account list-locations](https://learn.microsoft.com/cli/azure/account?view=azure-cli-latest#az-account-list-locations) |
| Azure Resource Manager は全リージョンでサポートされるが、個別リソース種別は全リージョンでサポートされるとは限らない。対応 location は `az provider show` で確認できる。 | [Azure resource providers and types](https://learn.microsoft.com/azure/azure-resource-manager/management/resource-providers-and-types#azure-cli) |
| Resource Group の location は Resource Group メタデータの格納場所を表し、コンプライアンス上の考慮が必要になる場合がある。 | [Manage Azure resource groups by using Azure CLI](https://learn.microsoft.com/azure/azure-resource-manager/management/manage-resource-groups-cli) |

## リポジトリ内根拠

本リポジトリでは、既存資料に以下のリージョン方針が記録されている。

| 根拠ファイル | 確認事項 |
|---|---|
| `.github/ISSUE_TEMPLATE/dataflow-dev.yml` / `.github/ISSUE_TEMPLATE/web-app-dev.yml` | `Japan East` 優先の記載 |
| `.github/scripts/templates/asdw/step-2.5.md` / `.github/scripts/templates/asdw-web/step-3.4.md` | `Japan East`、利用不可時 `Japan West`、さらに不可時 `Southeast Asia` の fallback 記載 |
| `docs/azure/dependency-review-report.md` | 標準リージョンとして `japaneast` を記録 |
| `docs/azure/azure-services-compute.md` | `japaneast` 既定、SWA は既存レビュー上 `eastasia` 実装確認あり |

---

## §1 標準リージョン優先順位

本リポジトリの Azure リソースは、明示要件がない限り以下を標準優先順位とする。

1. `japaneast`（Japan East）
2. `japanwest`（Japan West）
3. `southeastasia`（Southeast Asia）

ただし、上記は **リポジトリ標準の既定値** であり、全サービス・全サブスクリプションで利用可能であることを保証しない。実作成前に以下を確認する。

- Issue / prompt / 既存設計書が別 location を明示している場合は、その明示指定を優先し、標準優先順位から外れる理由を記録する。
- `az account list-locations` でサブスクリプション上の location を確認する。
- `az provider show --namespace <namespace> --query "resourceTypes[?resourceType=='<type>'].locations | [0]"` で対象 resource type の対応 location を確認する。
- 既存 Resource Group / 既存リソースを再利用する場合は、その location と混在理由を記録する。
- 利用者地域・データ所在地・可用性要件が未確認の場合は、確定表現を避け `TBD（要確認）` と記録する。

---

## §2 fallback ルール

明示要件がなく、標準優先順位に従う場合は、`japaneast` が対象サービス・SKU・サブスクリプションで利用できない場合のみ、`japanwest`、次に `southeastasia` を検討する。Issue / prompt / 既存設計書が `eastasia` など別 location を指定している場合は、fallback ではなく **明示指定の採用** として扱い、根拠を記録する。

fallback した場合の必須記録:

- fallback 前の希望 location
- fallback 後の location
- fallback 理由（例: resource type 非対応、SKU 非対応、既存 Webspace / quota / 容量制約）
- 確認手段（`az provider show`、`az account list-locations`、Azure CLI エラー、Microsoft Learn 等）
- 影響（レイテンシ、データ所在地、運用上の注意）

`eastasia` など標準優先順位外の location を使う場合も、既存実装・サービス制約・利用者地域などの根拠を記録する。

---

## §3 例外記録

以下の場合は、Agent が成果物に例外理由を記録する。

- UI / CDN / Static Web Apps と Backend / Data の location が分かれる。
- 既存 Resource Group の location と新規リソース location が異なる。
- サービス固有制約で標準優先順位外の location を選ぶ。
- 障害対策・DR・レイテンシ要件で複数リージョン構成を選ぶ。

記録先の候補:

- `ac-verification.md`
- `docs/azure/*.md`
- `docs/catalog/service-catalog-matrix.md`
- deploy / rollback 手順書

---

## §4 禁止事項

- `japaneast` が常に利用可能であると断定しない。
- サービス非対応・quota・容量制約を確認せずに fallback しない。
- fallback 理由を記録しないまま完了しない。
- リージョン混在の影響を「問題なし」と根拠なく断定しない。
- 実在確認のない location / Resource ID / URL を成果物に記録しない。

## Related Skills

| Skill | 関係 | 説明 |
|---|---|---|
| `azure-cli-deploy-scripts` | 後続 | location を使った create / verify スクリプトの作成規約 |
| `azure-ac-verification` | 後続 | fallback 結果と location 証跡の AC 記録 |
| `github-actions-cicd` | 関連 | GitHub Actions から Azure CLI を実行する場合の認証・実行規約 |