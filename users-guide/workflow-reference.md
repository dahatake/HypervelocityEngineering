# ワークフロー・ラベル・Custom Agent リファレンス

← [Users Guide](./README.md)

---

## 目次

- [ワークフロー一覧](#ワークフロー一覧)
- [ワークフロートリガー系ラベル](#ワークフロートリガー系ラベル)
- [Custom Agent 一覧](#custom-agent-一覧)
- [Issue テンプレート一覧](#issue-テンプレート一覧)

---

## ワークフロー一覧

`.github/workflows/` 配下の全ワークフローです。

| ファイル名 | 用途 | トリガー |
|-----------|------|---------|
| `auto-app-selection.yml` | アプリケーション選定（AAS）オーケストレーター | `auto-app-selection` ラベル付き Issue |
| `auto-app-design.yml` | アプリケーション設計（AAD）オーケストレーター | `auto-app-design` ラベル付き Issue |
| `auto-app-dev-microservice-azure.yml` | マイクロサービス実装（ASDW）オーケストレーター | `auto-app-dev-microservice` ラベル付き Issue |
| `auto-batch-design.yml` | バッチ設計（ABD）オーケストレーター | `auto-batch-design` ラベル付き Issue |
| `auto-batch-dev.yml` | バッチ実装（ABDV）オーケストレーター | `auto-batch-dev` ラベル付き Issue |
| `auto-iot-design.yml` | IoT 設計（AID）オーケストレーター | `auto-iot-design` ラベル付き Issue |
| `create-subissues-from-pr.yml` | `subissues.md` から Sub Issue を自動作成 | `create-subissues` ラベル付き PR |
| `advance-subissues.yml` | Sub Issue の完了後に次の Sub Issue を Copilot に自動アサイン | PR クローズ |
| `link-copilot-pr-to-issue.yml` | Copilot が作成した PR を親 Issue にリンク | PR オープン |
| `copilot-auto-review.yml` | Copilot に敵対的レビューを自動依頼 | `auto-context-review` ラベル付き PR |
| `copilot-auto-qa.yml` | Copilot に質問票作成を自動依頼 | `auto-qa` ラベル付き PR |
| `auto-qa-to-review-transition.yml` | `auto-qa` 完了後に `auto-context-review` へ自動遷移 | PR コメント |
| `sync-issue-labels-to-pr.yml` | 親 Issue のラベルを PR に同期 | Issue ラベル変更 |
| `label-split-mode.yml` | `[WIP]` タイトルの PR に `split-mode` ラベルを付与 | PR オープン / 編集 |
| `check-split-mode.yml` | `split-mode` PR での実装ファイル変更を検知・警告 | PR プッシュ |
| `validate-plan.yml` | `plan.md` のフォーマット・分割判定を検証 | PR プッシュ |
| `sync-azure-skills.yml` | microsoft/skills から Azure Skills を定期同期 | 毎週月曜 9:00 UTC / 手動 |
| `copilot-setup-steps.yml` | Copilot Coding Agent の実行前セットアップ | Copilot Agent 起動時 |
| `test-cli-scripts.yml` | `.github/scripts/` の CLI スクリプトをテスト | PR プッシュ |

### SDK 版ワークフロー ID（逆引き）

| ワークフロー ID | 対応ワークフロー | GitHub ワークフローファイル |
|--------------|--------------|--------------------------|
| `aas` | Auto App Selection | `auto-app-selection.yml` |
| `aad` | Auto App Design | `auto-app-design.yml` |
| `asdw` | Auto App Dev Azure Web | `auto-app-dev-microservice-azure.yml` |
| `abd` | Auto Batch Design | `auto-batch-design.yml` |
| `abdv` | Auto Batch Dev | `auto-batch-dev.yml` |
| `aid` | Auto IoT Design | `auto-iot-design.yml` |

> **注意**: SDK 版コマンドで `--workflow asd` は無効です。正しいワークフロー ID は上記の `aas` / `aad` / `asdw` / `abd` / `abdv` / `aid` を使用してください。

---

## ワークフロートリガー系ラベル

以下のラベルを GitHub リポジトリに事前に作成してください。

| ラベル名 | 役割 |
|---------|------|
| `auto-app-selection` | **アプリケーション選定ワークフロー（AAS）の起動トリガー**。Issue にこのラベルが付与されると、AAS オーケストレーターが起動し、Sub Issue を自動生成して Copilot にアサインする |
| `auto-app-design` | **アプリケーション設計ワークフロー（AAD）の起動トリガー**。Issue にこのラベルが付与されると、AAD オーケストレーターが起動し、Step.1〜7.3 の Sub Issue を自動生成して Copilot にアサインする |
| `auto-software-design` | **[過去互換/未使用] 設計ワークフロー用ラベル**。現在、このラベルに対応する ASD ワークフローや Issue テンプレートは `.github/workflows/` / `.github/ISSUE_TEMPLATE/` に存在しないため、付与してもオーケストレーターは起動しません |
| `auto-app-dev-microservice` | **マイクロサービス開発ワークフローの起動トリガー**。Issue にこのラベルが付与されると、ASDW オーケストレーターが起動し、Step.1〜4 の Sub Issue を自動生成して Copilot にアサインする |
| `auto-batch-design` | **バッチ設計ワークフロー（ABD）の起動トリガー**。Issue にこのラベルが付与されると、ABD オーケストレーターが起動し、Step.1.1〜6.3 の Sub Issue を自動生成して Copilot にアサインする |
| `auto-iot-design` | **IoT 設計ワークフロー（AID）の起動トリガー**。Issue にこのラベルが付与されると、AID オーケストレーターが起動し、Step.1〜7 の Sub Issue を自動生成して Copilot にアサインする |
| `auto-batch-dev` | **バッチ実装ワークフロー（ABDV）の起動トリガー**。Issue にこのラベルが付与されると、ABDV オーケストレーターが起動し、Step.1〜4 の Sub Issue を自動生成して Copilot にアサインする |
| `create-subissues` | **Sub Issue 自動作成のトリガー**。人間が PR にこのラベルを手動付与すると、PR 内の `work/**/subissues.md` をパースして Sub Issue を自動作成する |
| `auto-context-review` | **Copilot 敵対的レビューのトリガー**。PR にこのラベルが付いた状態で PR が ready（非 draft）になると、Copilot に敵対的レビュー指示コメントを自動投稿する |
| `auto-qa` | **Copilot 質問票作成のトリガー**。PR にこのラベルが付いた状態で PR が ready（非 draft）になると、Copilot に選択式の質問票作成指示コメントを自動投稿する |

> [!IMPORTANT]
> GitHub の Issue Template の `labels:` フィールドは、**リポジトリに既に存在するラベルのみ**を Issue に自動付与します。ラベルが存在しない場合、Issue 作成時にラベルの自動付与はサイレントにスキップされます。各ワークフローを使用する前に必ずラベルを事前に作成してください。
> 特に、`.github/workflows/label-split-mode.yml` で使用する `split-mode` / `plan-only` ラベルも同様に事前作成が必要です。リポジトリ設定画面の **Settings → Labels** からこれらのラベルを手動作成してからワークフローを利用してください。

---

## Custom Agent 一覧

`.github/agents/` 配下の全 44 Custom Agent を以下に列挙します。

### ビジネス分析・要求定義

| Agent 名 | 用途 |
|---------|------|
| `Arch-ApplicationAnalytics` | ユースケースから実装手段を仕分け・アプリリスト・MVP 選出 |
| `Arch-ArchitectureCandidateAnalyzer` | 各アプリの非機能要件に基づき最良のアーキテクチャを選定 |

### アーキテクチャ設計 — 共通

| Agent 名 | 用途 |
|---------|------|
| `Arch-DataModeling` | ユースケースから全エンティティ・サービス境界・データモデルを生成 |
| `Arch-DataCatalog` | 概念データモデルと物理テーブルのマッピングを記録するデータカタログ生成 |

### アーキテクチャ設計 — Microservice

| Agent 名 | 用途 |
|---------|------|
| `Arch-Microservice-DomainAnalytics` | DDD 観点でドメイン分析（Bounded Context / ユビキタス言語 / 集約 / ドメインイベント）を実施 |
| `Arch-Microservice-ServiceIdentify` | ドメイン分析からマイクロサービス候補を抽出し service-list.md を作成 |
| `Arch-Microservice-ServiceCatalog` | 画面→機能→API→SoT データのマッピングを service-catalog.md に作成 |
| `Arch-Microservice-ServiceDetail` | 全サービスのマイクロサービス詳細仕様（API / イベント / データ / セキュリティ）を作成 |

### アーキテクチャ設計 — UI

| Agent 名 | 用途 |
|---------|------|
| `Arch-UI-List` | 画面一覧（表）と画面遷移図（Mermaid）を設計し screen-list.md を作成 |
| `Arch-UI-Detail` | 全画面の実装用画面定義書（UX / A11y / セキュリティ含む）を docs/screen/ に生成 |

### アーキテクチャ設計 — Batch

| Agent 名 | 用途 |
|---------|------|
| `Arch-Batch-DomainAnalytics` | バッチ DDD 観点ドメイン分析（BC / 冪等性 / チェックポイント）を作成 |
| `Arch-Batch-DataSourceAnalysis` | バッチデータソース / デスティネーション分析（スキーマ / 変換 / SLA）を作成 |
| `Arch-Batch-DataModel` | バッチ 4 層データモデル・冪等性キー・パーティション・ER 図を設計 |
| `Arch-Batch-JobCatalog` | バッチジョブ設計（一覧 / 依存 DAG / スケジュール / リトライ）を作成 |
| `Arch-Batch-JobSpec` | バッチジョブ詳細仕様書を docs/batch/jobs/{jobId}-{jobNameSlug}-spec.md に作成 |
| `Arch-Batch-ServiceCatalog` | バッチジョブサービスカタログを docs/batch/batch-service-catalog.md に作成 |
| `Arch-Batch-MonitoringDesign` | バッチ処理監視・運用設計書を docs/batch/batch-monitoring-design.md に作成 |

### アーキテクチャ設計 — IoT

| Agent 名 | 用途 |
|---------|------|
| `Arch-IoT-DomainAnalytics` | ユースケース文書を根拠に IoT / Physical AI の 3 層境界（Device / Edge / Cloud）を明示してドメイン分析 |
| `Arch-IoT-DeviceConnectivity` | デバイスの HW プロファイル・センサー仕様・接続性・オフライン分類・消費電力・AI 推論要件・状態遷移・フェイルセーフ設計を整理 |

### アーキテクチャ設計 — AI Agent

| Agent 名 | 用途 |
|---------|------|
| `Arch-AIAgentDesign` | AI Agent のアプリケーション定義・粒度設計・詳細設計を実施し、docs/AI-Agents-list.md に出力 |

### アーキテクチャ設計 — テスト

| Agent 名 | 用途 |
|---------|------|
| `Arch-TDD-TestStrategy` | サービスカタログ・データモデルから TDD テスト戦略書を docs/test-strategy.md に生成 |
| `Arch-TDD-TestSpec` | テスト戦略書・画面/サービス定義書から TDD テスト仕様書を docs/test-specs/ に生成 |
| `Arch-Batch-TestStrategy` | バッチ処理テスト戦略書（冪等性 / データ品質 / 障害注入）を docs/batch/batch-test-strategy.md に作成 |
| `Arch-Batch-TDD-TestSpec` | バッチ TDD テスト仕様書をジョブごとに docs/test-specs/{jobId}-test-spec.md に生成 |

### 実装 — Microservice（Azure）

| Agent 名 | 用途 |
|---------|------|
| `Dev-Microservice-Azure-ComputeDesign` | ユースケース内の全マイクロサービスについて最適な Azure コンピュート（ホスティング）を選定 |
| `Dev-Microservice-Azure-DataDesign` | Polyglot Persistence に基づき全エンティティに対する最適 Azure データストアを選定し文書化 |
| `Dev-Microservice-Azure-DataDeploy` | Azure CLI でデータ系サービスを作成し、サンプルデータを変換・一括登録して検証 |
| `Dev-Microservice-Azure-AddServiceDesign` | サービス定義書の外部依存・統合要件から追加で必要な Azure サービスを選定 |
| `Dev-Microservice-Azure-AddServiceDeploy` | Azure 追加サービスを Azure CLI で冪等作成し、AC 検証で完了判定 |
| `Dev-Microservice-Azure-ServiceTestCoding` | TDD RED フェーズのテストコード（失敗するテスト）を test/api/{サービス名}.Tests/ に生成 |
| `Dev-Microservice-Azure-ServiceCoding-AzureFunctions` | マイクロサービス定義書から全サービスの Azure Functions を実装 |
| `Dev-Microservice-Azure-UITestCoding` | 画面別テスト仕様書から TDD RED フェーズの UI テストコードを test/ui/ に生成 |
| `Dev-Microservice-Azure-UICoding` | 画面定義書に基づき全画面の UI を実装し、API クライアント層を整備 |
| `Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps` | Azure Static Web Apps へのデプロイと GitHub Actions による CD 構築 |
| `Dev-Microservice-Azure-ComputeDeploy-AzureFunctions` | 全サービスを Azure Functions 用に作成・デプロイし、GitHub Actions で CI/CD 構築 |

### 実装 — AI Agent（Azure）

| Agent 名 | 用途 |
|---------|------|
| `Dev-Microservice-Azure-AgentTestCoding` | テスト仕様書から TDD RED フェーズのテストコードを test/agent/{AgentName}.Tests/ に生成 |
| `Dev-Microservice-Azure-AgentCoding` | AI Agent 詳細設計書から Azure AI Foundry Agent Service を使用して Agent を実装 |
| `Dev-Microservice-Azure-AgentDeploy` | AI Agent を Azure AI Foundry Agent Service へデプロイし、GitHub Actions で CI/CD 構築 |

### 実装 — Batch（Azure）

| Agent 名 | 用途 |
|---------|------|
| `Dev-Batch-TestCoding` | バッチ TDD テスト仕様書から TDD RED フェーズのテストコードを test/batch/{jobId}-{jobNameSlug}.Tests/ に生成 |
| `Dev-Batch-ServiceCoding` | バッチジョブ詳細仕様書と TDD テスト仕様書に基づき Azure Functions 実装で TDD GREEN を完了 |
| `Dev-Batch-Deploy` | バッチサービスを Azure にデプロイし GitHub Actions CI/CD を構築、AC 検証まで実施 |

### QA / レビュー

| Agent 名 | 用途 |
|---------|------|
| `QA-AzureArchitectureReview` | デプロイ済み Azure リソースを棚卸しし、Azure WAF（5 本柱）と Azure Security Benchmark v3 を根拠にアーキテクチャ / セキュリティをレビュー |
| `QA-AzureDependencyReview` | サービスカタログ準拠で Azure 依存（参照 / 設定 / IaC）を証跡付きで点検 |
| `QA-RequirementClassifier` | `qa/` フォルダーの質問ファイルを読み取り、docs/business-requirement-document-master-list.md の D01〜D21 に分類し、work/business-requirement-document-status.md を生成 |

---

## Issue テンプレート一覧

`.github/ISSUE_TEMPLATE/` 配下の全テンプレートです。

| ファイル名 | 用途 | トリガーラベル |
|-----------|------|-------------|
| `auto-app-selection.yml` | アプリケーション選定ワークフロー起動 | `auto-app-selection` |
| `auto-app-design.yml` | アプリケーション設計ワークフロー起動 | `auto-app-design` |
| `auto-app-dev-microservice.yml` | マイクロサービス実装ワークフロー起動 | `auto-app-dev-microservice` |
| `auto-batch-design.yml` | バッチ設計ワークフロー起動 | `auto-batch-design` |
| `auto-batch-dev.yml` | バッチ実装ワークフロー起動 | `auto-batch-dev` |
| `auto-iot-design.yml` | IoT 設計ワークフロー起動 | `auto-iot-design` |
| `qa-requirement-classification.yml` | 要求定義文書の QA 分類 | — |
