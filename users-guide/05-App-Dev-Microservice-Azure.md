# Web Application の作成（ASDW-WEB）

← [03-app-design-microservice-azure.md](./03-app-design-microservice-azure.md) | [06-app-dev-batch-azure.md](./06-app-dev-batch-azure.md) →

---

## 目次

- [対象読者](#対象読者)
- [前提](#前提)
- [次のステップ](#次のステップ)
- [概要](#概要)
- [Agent チェーン図 ASDW-WEB](#agent-チェーン図-asdw-web)
- [ツール](#ツール)
- [ステップ概要](#ステップ概要)
- [TDD 原則](#tdd-原則)
- [手動実行ガイド](#手動実行ガイド)
- [自動実行ガイド ワークフロー](#自動実行ガイド-ワークフロー)
- [動作確認手順](#動作確認手順)

---

## 対象読者

- AAS + AAD-WEB 完了後に Web アプリ実装〜デプロイを自動化したい人
- `web-app-dev.yml` と `auto-app-dev-microservice-web-reusable.yml` を運用する人

## 前提

- 設計成果物が存在すること（`docs/catalog/service-catalog-matrix.md`、`docs/services/`、`docs/screen/` など）
- `COPILOT_PAT`、`AZURE_CLIENT_ID`、`AZURE_TENANT_ID`、`AZURE_SUBSCRIPTION_ID` が設定済みであること
- `AZURE_STATIC_WEB_APPS_API_TOKEN` は手動設定不要（OIDC + `az staticwebapp secrets list` で deploy token を動的取得する運用）
- セットアップ手順は [getting-started.md](./getting-started.md) を参照

## 次のステップ

- AI Agent 実装が必要な場合は [08-ai-agent.md](./08-ai-agent.md)（AAG / AAGD）へ進む

---

## 概要

ASDW-WEB（Web App Dev & Deploy）は、AAS + AAD-WEB で作成した設計成果物を入力として、
Step.1〜Step.4 を Sub-issue 化して順次（Step.4 のみ並列）実行するワークフローです。

- トリガー: `web-app-dev.yml`（Issue Template）
- 実行: `auto-app-dev-microservice-web-reusable.yml`（GitHub Actions）
- `knowledge/` の活用方法は [km-guide.md](./km-guide.md) を参照

## Agent チェーン図 ASDW-WEB

![ASDW-WEB: Dev-Microservice-Azure-DataDesign から QA-AzureDependencyReview までの実行チェーン](./images/chain-asdw.svg)

### アーキテクチャ図

![ASDW-WEB アーキテクチャ: 入力ファイル → auto-app-dev-microservice-web Workflow → Custom Agent チェーン → 成果物](./images/infographic-asdw.svg)

### データフロー図（ASDW-WEB）

![ASDW-WEB データフロー: 入力ファイル → Custom Agent（タスク）→ 出力ファイル](./images/orchestration-task-data-flow-asdw.svg)

---

## ツール

- GitHub Copilot cloud agent / GitHub Copilot for Azure
- GitHub Actions（`auto-app-dev-microservice-web-reusable.yml`）
- MCP Server（Microsoft Learn / Azure）

---

## ステップ概要

### 依存グラフ

```text
Step.1.1 → Step.1.2 → Step.2.1 → Step.2.2 → Step.2.3 → Step.2.3T → Step.2.3TC → Step.2.4 → Step.2.5
                                                                     ↓
                                                                 Step.3.0T → Step.3.0TC → Step.3.1 → Step.3.2 → Step.3.3
                                                                                                      ├─► Step.4.1
                                                                                                      └─► Step.4.2
```

### 各ステップの入出力

| Step ID | タイトル | Custom Agent | 入力 | 出力 | 依存 |
|---|---|---|---|---|---|
| step-1.1 | Azure データストア選定 | `Dev-Microservice-Azure-DataDesign` | `docs/catalog/data-model.md`, `docs/catalog/service-catalog.md`, `docs/catalog/domain-analytics.md`, `docs/catalog/app-catalog.md` | `docs/azure/azure-services-data.md` | なし |
| step-1.2 | Azure データサービス Deploy | `Dev-Microservice-Azure-DataDeploy` | `docs/azure/azure-services-data.md`, `docs/catalog/service-catalog-matrix.md`, `src/data/sample-data.json`, `docs/catalog/app-catalog.md` | `infra/azure/create-azure-data-resources-prep.sh`, `infra/azure/create-azure-data-resources.sh`, `src/data/azure/data-registration-script.sh`, `infra/azure/verify-data-resources.sh`, `docs/test-specs/deploy-step1-data-test-spec.md`, `docs/azure/service-catalog.md` 更新 | step-1.1 |
| step-2.1 | Azure コンピュート選定 | `Dev-Microservice-Azure-ComputeDesign` | `docs/catalog/service-catalog.md`, `docs/catalog/use-case-catalog.md`, `docs/catalog/data-model.md`, `docs/catalog/service-catalog-matrix.md`, `docs/catalog/app-catalog.md` | `docs/azure/azure-services-compute.md` | step-1.2 |
| step-2.2 | 追加 Azure サービス選定 | `Dev-Microservice-Azure-AddServiceDesign` | `docs/catalog/use-case-catalog.md`, `docs/catalog/service-catalog.md`, `docs/services/`, `docs/azure/azure-services-compute.md`, `docs/catalog/app-catalog.md` | `docs/azure/azure-services-additional.md` | step-2.1 |
| step-2.3 | 追加 Azure サービス Deploy | `Dev-Microservice-Azure-AddServiceDeploy` | `docs/azure/azure-services-additional.md`, `docs/catalog/app-catalog.md` | `infra/azure/create-azure-additional-resources*`, `infra/azure/verify-additional-resources.sh` | step-2.2 |
| step-2.3T | サービス テスト仕様書 (TDD RED) | `Arch-TDD-TestSpec` | `docs/catalog/test-strategy.md`, `docs/catalog/service-catalog-matrix.md`, `docs/services/`, `docs/catalog/data-model.md`, `docs/catalog/domain-analytics.md`, `docs/catalog/app-catalog.md` | `docs/test-specs/{serviceId}-test-spec.md` | step-2.3 |
| step-2.3TC | サービス テストコード生成 (TDD RED) | `Dev-Microservice-Azure-ServiceTestCoding` | `docs/test-specs/{serviceId}-test-spec.md`, `docs/services/`, `docs/catalog/service-catalog-matrix.md`, `docs/catalog/app-catalog.md` | `test/api/{ServiceName}.Tests/` | step-2.3T |
| step-2.4 | サービスコード実装 (TDD GREEN) | `Dev-Microservice-Azure-ServiceCoding-AzureFunctions` | サービス定義書, RED テストコード, テスト仕様書, `docs/catalog/app-catalog.md` | `src/api/{serviceId}-{serviceName}/` | step-2.3TC |
| step-2.5 | Azure Compute Deploy | `Dev-Microservice-Azure-ComputeDeploy-AzureFunctions` | `docs/catalog/service-catalog.md`, `docs/catalog/service-catalog-matrix.md`, `src/api/`, `docs/catalog/app-catalog.md` | `infra/azure/create-azure-api-resources-prep.sh`, `infra/azure/verify-api-resources.sh`, `.github/workflows/` | step-2.4 |
| step-3.0T | UI テスト仕様書 (TDD RED) | `Arch-TDD-TestSpec` | `docs/catalog/test-strategy.md`, `docs/catalog/service-catalog-matrix.md`, `docs/screen/`, `docs/catalog/data-model.md`, `docs/catalog/domain-analytics.md`, `docs/catalog/app-catalog.md` | `docs/test-specs/{screenId}-test-spec.md` | step-2.5 |
| step-3.0TC | UI テストコード生成 (TDD RED) | `Dev-Microservice-Azure-UITestCoding` | `docs/test-specs/{screenId}-test-spec.md`, `docs/screen/`, `docs/catalog/service-catalog-matrix.md`, `docs/catalog/app-catalog.md` | `test/ui/` | step-3.0T |
| step-3.1 | UI 実装 (TDD GREEN) | `Dev-Microservice-Azure-UICoding` | 画面定義書, サービスカタログ, RED テストコード, テスト仕様書, `docs/catalog/app-catalog.md` | `src/app/` | step-3.0TC |
| step-3.2 | Web アプリ Deploy (Azure SWA) | `Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps` | `src/app/`, リソースグループ名, `docs/catalog/app-catalog.md` | `infra/azure/create-azure-webui-resources-prep.sh`, `infra/azure/create-azure-webui-resources.sh`, `infra/azure/verify-webui-resources.sh`, `docs/test-specs/deploy-step3-swa-test-spec.md`, `docs/catalog/service-catalog-matrix.md` 更新, `.github/workflows/azure-static-web-apps-*.yml`（`AZURE_STATIC_WEB_APPS_API_TOKEN` 参照） | step-3.1 |
| step-3.3 | UI E2E テスト (Playwright) | `E2ETesting-Playwright` | `src/app/`, `docs/catalog/service-catalog-matrix.md`, `docs/test-specs/`, `docs/catalog/app-catalog.md` | E2E 実行結果（artifact） | step-3.2 |
| step-4.1 | WAF アーキテクチャレビュー | `QA-AzureArchitectureReview` | `docs/catalog/use-case-catalog.md`, `docs/catalog/service-catalog-matrix.md`, `docs/catalog/app-catalog.md`, リソースグループ名 | `docs/azure/azure-architecture-review-report.md` | step-3.3 |
| step-4.2 | 整合性チェック | `QA-AzureDependencyReview` | `docs/catalog/service-catalog-matrix.md`, `src/`, `infra/`, `docs/catalog/app-catalog.md` | `docs/azure/dependency-review-report.md` | step-3.3 |

---

## TDD 原則

ASDW-WEB は TDD を前提とし、次を順守します。

1. テスト仕様書生成（`*T`）
2. テストコード生成（`*TC`）
3. RED 確認
4. GREEN まで実装反復

`web-app-dev.yml` の `tdd_max_retries` で GREEN の最大再試行回数を設定できます。

---

## 手動実行ガイド

### Step.1 データ

- Step.1.1: `Dev-Microservice-Azure-DataDesign`
- Step.1.2: `Dev-Microservice-Azure-DataDeploy`

### Step.2 マイクロサービス

- Step.2.1: `Dev-Microservice-Azure-ComputeDesign`
- Step.2.2: `Dev-Microservice-Azure-AddServiceDesign`
- Step.2.3: `Dev-Microservice-Azure-AddServiceDeploy`
- Step.2.3T: `Arch-TDD-TestSpec`
- Step.2.3TC: `Dev-Microservice-Azure-ServiceTestCoding`
- Step.2.4: `Dev-Microservice-Azure-ServiceCoding-AzureFunctions`
- Step.2.5: `Dev-Microservice-Azure-ComputeDeploy-AzureFunctions`

### Step.3 UI

- Step.3.0T: `Arch-TDD-TestSpec`
- Step.3.0TC: `Dev-Microservice-Azure-UITestCoding`
- Step.3.1: `Dev-Microservice-Azure-UICoding`
- Step.3.2: `Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps`
- Step.3.3: `E2ETesting-Playwright`

### Step.4 レビュー（並列）

- Step.4.1: `QA-AzureArchitectureReview`
- Step.4.2: `QA-AzureDependencyReview`

---

## 自動実行ガイド ワークフロー

### 関連ファイル

- Issue Template: `.github/ISSUE_TEMPLATE/web-app-dev.yml`
- Workflow: `.github/workflows/auto-app-dev-microservice-web-reusable.yml`

### 状態ラベル

| ラベル | 説明 |
|---|---|
| `auto-app-dev-microservice-web` | トリガーラベル（Issue Template で自動付与） |
| `asdw-web:initialized` | Bootstrap 完了 |
| `asdw-web:ready` | 実行可能 |
| `asdw-web:running` | 実行中 |
| `asdw-web:done` | 完了 |
| `asdw-web:blocked` | ブロック |

### フォーム入力（主要）

`web-app-dev.yml` の主要入力:

- `app_ids`
- `branch`
- `runner_type`
- `resource_group`
- `steps`
- `tdd_max_retries`
- `model` / `review_model` / `qa_model`

### 実行手順

1. Issues → New Issue → **Web App Dev & Deploy** を選択
2. 必要項目を入力して Submit
3. `auto-app-dev-microservice-web` が付与され、`ASDW-WEB: Web App Dev & Deploy (Reusable)` が起動

### HITL エスカレーション

`asdw-web:blocked` が付与された場合は以下を使用します。

- `.github/workflows/auto-blocked-to-human-required.yml`
- `.github/workflows/auto-human-resolved-to-ready.yml`

詳細: [`docs/hitl/escalation-sla.md`](../docs/hitl/escalation-sla.md)

---

## 動作確認手順

1. `.github/ISSUE_TEMPLATE/web-app-dev.yml` が存在することを確認
2. `.github/workflows/auto-app-dev-microservice-web-reusable.yml` が存在することを確認
3. Issues で **Web App Dev & Deploy** テンプレートが表示されることを確認
4. Issue 作成後に親 Issue に `asdw-web:initialized` が付与されることを確認
5. Step が `1.1 → 1.2 → 2.1 → 2.2 → 2.3 → 2.3T → 2.3TC → 2.4 → 2.5 → 3.0T → 3.0TC → 3.1 → 3.2 → 3.3` と進むことを確認
6. `step-4.1` と `step-4.2` が並列起動することを確認
7. 最終的に Root Issue に `asdw-web:done` が付与されることを確認
