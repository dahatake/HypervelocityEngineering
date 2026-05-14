---
name: _routing
description: >-
  Skills 参照先のルーティング表。USE FOR: どのフェーズでどの Skill を参照するか判断するとき。
  DO NOT USE FOR: 実装手順や詳細仕様の代替。
  WHEN: C[...]
metadata:
  version: 1.0.0
---

# Skills ルーティングテーブル

以下は `.github/copilot-instructions.md` から分離したルーティング一覧。

**【共通 / planning】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| Agent 作業開始（共通） | `agent-common-preamble` | `.github/skills/agent-common-preamble/SKILL.md` | 全 Agent 共通ルール・Skills 参照リスト一元管理 |
| 入力ファイル確認 | `input-file-validation` | `.github/skills/input-file-validation/SKILL.md` | 必読ファイル確認・欠損時処理ルール |
| APP-ID スコープ解決 | `app-scope-resolution` | `.github/skills/app-scope-resolution/SKILL.md` | APP-ID からサービス/画面/エンティティ特定 |
| タスク開始 / 不明点あり | `task-questionnaire` | `.github/skills/task-questionnaire/SKILL.md` | 選択式質問票で要件を明確化 |
| 計画 / DAG / 見積 | `task-dag-planning` | `.github/skills/task-dag-planning/SKILL.md` | 依存関係分解・粒度/コンテキスト分割判定 |
| work/ 配下の構造設計 | `work-artifacts-layout` | `.github/skills/work-artifacts-layout/SKILL.md` | 入口 README + contracts/artifacts |
| リポジトリ初見 | `repo-onboarding-fast` | `.github/skills/repo-onboarding-fast/SKILL.md` | 高速オンボーディング（構造把握・規約確認） |
| Karpathy ガイドライン参照 | `karpathy-guidelines` | `.github/skills/karpathy-guidelines/SKILL.md` | Karpathy の実装原則（最小変更・仮説明示・検証重視） |

**【ドメイン設計 / planning】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| アーキテクチャ候補選定 | `architecture-questionnaire` | `.github/skills/architecture-questionnaire/SKILL.md` | Q1-Q26 質問票・適合度評価 |
| knowledge/ 管理 | `knowledge-management` | `.github/skills/knowledge-management/SKILL.md` | D01〜D21 分類・状態判定・ステータス管理 |
| タスク実行中に業務要件が不明瞭 | `knowledge-lookup` | `.github/skills/knowledge-lookup/SKILL.md` | knowledge/ D01〜D21 の条件付き参照ルール |
| MCP Server 設計 | `mcp-server-design` | `.github/skills/mcp-server-design/SKILL.md` | Skills と MCP Server の責務分離・API設計 |
| バッチ処理設計 | `batch-design-guide` | `.github/skills/batch-design-guide/SKILL.md` | バッチ要件定義〜テスト仕様の統合ガイド |
| マイクロサービス設計 | `microservice-design-guide` | `.github/skills/microservice-design-guide/SKILL.md` | サービス定義書テンプレート |
| original-docs/ 取り込み | `knowledge-management` | `.github/skills/knowledge-management/SKILL.md` | original-docs/ → D01〜D21 分類・矛盾検出 |
| Markdown 横断クエリ（ローカル） | `markdown-query` | `.github/skills/markdown-query/SKILL.md` | ローカル完結の Markdown 検索・該当チャンクのみ返却で Context 最小化。HVE CLI Orchestrator 実行中はリアルタイム索引更新が並走する（既定 ON、`--no-mdq-watch` で無効化、Cloud Agent では非対応） |

**Workflow 一覧（Issue Template / hve）**
- `aas`, `aad`, `asdw`, `abd`, `abdv`, `aag`, `aagd`, `akm`, `aqod`, `adoc`

**【出力 / output】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| 大量出力 / 50k超 | `large-output-chunking` | `.github/skills/output/large-output-chunking/SKILL.md` | index + part 分割 |
| docs/ 成果物フォーマット | `docs-output-format` | `.github/skills/output/docs-output-format/SKILL.md` | 固定章立て・出典必須・Mermaid erDiagram |
| SVG ダイアグラム生成 | `svg-renderer` | `.github/skills/output/svg-renderer/SKILL.md` | SVGコード生成・画面レンダリング |

**【ハーネス / harness】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| レビュー（ユーザー指定時） | `adversarial-review` | `.github/skills/harness/adversarial-review/SKILL.md` | 5軸 敵対的レビュー |
| ハーネス: 検証ループ | `harness-verification-loop` | `.github/skills/harness/harness-verification-loop/SKILL.md` | Build/Lint/Test/Security/Diff |
| ハーネス: 安全ガード | `harness-safety-guard` | `.github/skills/harness/harness-safety-guard/SKILL.md` | 破壊的操作検出・停止 |
| ハーネス: エラーリカバリ | `harness-error-recovery` | `.github/skills/harness/harness-error-recovery/SKILL.md` | 原因推定・再試行・停止宣言 |

**【Azure プラットフォーム / azure-skills】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| Deploy後 AC 検証 | `azure-ac-verification` | `.github/skills/azure-skills/azure-ac-verification/SKILL.md` | PASS/NEEDS-VERIFICATION/FAIL 判定・Azure CLI フォールバック |
| Azure AI サービス利用 | `azure-ai` | `.github/skills/azure-skills/azure-ai/SKILL.md` | Azure AI Search / Speech / OpenAI / Document Intelligence |
| AI Gateway 設定 | `azure-aigateway` | `.github/skills/azure-skills/azure-aigateway/SKILL.md` | APIM を AI Gateway として設定・セマンティックキャッシュ・トークン制御 |
| Azure CLI デプロイスクリプト生成 | `azure-cli-deploy-scripts` | `.github/skills/azure-skills/azure-cli-deploy-scripts/SKILL.md` | prep/create/verify 3点セット・冪等性パターン |
| クラウド間移行アセスメント | `azure-cloud-migrate` | `.github/skills/azure-skills/azure-cloud-migrate/SKILL.md` | AWS/GCP→Azure 移行アセスメント・コード変換 |
| コンプライアンス監査・セキュリティ評価 | `azure-compliance` | `.github/skills/azure-skills/azure-compliance/SKILL.md` | ベストプラクティス評価・Key Vault 有効期限・リソース設定検証 |
| VM サイズ・VMSS 選定 | `azure-compute` | `.github/skills/azure-skills/azure-compute/SKILL.md` | VM サイズ推奨・VMSS 構成・コスト見積 |
| Cosmos DB を含む Azure データサービス準備 | `azure-prepare` | `.github/skills/azure-skills/azure-prepare/SKILL.md` | データサービスを含む IaC 生成・前提条件整理 |
| Azure コスト最適化 | `azure-cost` | `.github/skills/azure-skills/azure-cost/SKILL.md` | コスト削減分析・孤立リソース検出・VM リサイズ推奨 |
| Azure リソースへのデプロイ実行 | `azure-deploy` | `.github/skills/azure-skills/azure-deploy/SKILL.md` | azd up/deploy・terraform apply・エラーリカバリ付きデプロイ |
| Azure 本番問題デバッグ | `azure-diagnostics` | `.github/skills/azure-skills/azure-diagnostics/SKILL.md` | AppLens・Azure Monitor・リソースヘルス・安全トリアージ |
| Copilot SDK アプリ構築・デプロイ | `azure-hosted-copilot-sdk` | `.github/skills/azure-skills/azure-hosted-copilot-sdk/SKILL.md` | GitHub Copilot SDK・BYOM・Azure OpenAI モデル・azd init |
| ADX KQL クエリ・分析 | `azure-kusto` | `.github/skills/azure-skills/azure-kusto/SKILL.md` | Azure Data Explorer・KQL・ログ分析・時系列データ |
| Event Hubs / Service Bus SDK トラブルシューティング | `azure-messaging` | `.github/skills/azure-skills/azure-messaging/SKILL.md` | AMQP エラー・接続障害・SDK 設定問題解決 |
| Azure デプロイ準備（IaC 生成） | `azure-prepare` | `.github/skills/azure-skills/azure-prepare/SKILL.md` | Bicep/Terraform・azure.yaml・Dockerfile 生成・マネージド ID |
| Azure クォータ確認・管理 | `azure-quotas` | `.github/skills/azure-skills/azure-quotas/SKILL.md` | クォータ確認・サービス制限・vCPU 上限・リージョン容量検証 |
| Azure RBAC ロール選定・割り当て | `azure-rbac` | `.github/skills/azure-skills/azure-rbac/SKILL.md` | 最小権限ロール選定・CLI コマンド/Bicep 生成 |
| Azure リージョン選択ポリシー | `azure-deploy` | `.github/skills/azure-skills/azure-deploy/SKILL.md` | デプロイ時のリージョン選定・利用可能性確認（`references/region-availability.md`） |
| Azure リソース一覧・検索・確認 | `azure-resource-lookup` | `.github/skills/azure-skills/azure-resource-lookup/SKILL.md` | 全 Azure リソース検索・Resource Graph |
| Azure リソース Mermaid 図生成 | `azure-resource-visualizer` | `.github/skills/azure-skills/azure-resource-visualizer/SKILL.md` | リソースグループ分析・依存関係可視化・アーキテクチャ図 |
| Azure Storage 操作 | `azure-storage` | `.github/skills/azure-skills/azure-storage/SKILL.md` | Blob/Queue/Table/Data Lake・アクセス層・ライフサイクル管理 |
| Azure サービス プラン/SKU アップグレード | `azure-upgrade` | `.github/skills/azure-skills/azure-upgrade/SKILL.md` | Consumption→Flex Consumption 等プラン移行・アップグレード自動化 |
| デプロイ前 Azure 設定バリデーション | `azure-validate` | `.github/skills/azure-skills/azure-validate/SKILL.md` | Bicep/Terraform・権限・前提条件のプリフライトチェック |
| Entra ID アプリ登録・OAuth 認証設定 | `entra-app-registration` | `.github/skills/azure-skills/entra-app-registration/SKILL.md` | アプリ登録・OAuth 2.0・MSAL 統合・サービスプリンシパル生成 |
| Microsoft Foundry Agent デプロイ・評価・管理 | `microsoft-foundry` | `.github/skills/azure-skills/microsoft-foundry/SKILL.md` | Foundry Agent デプロイ・バッチ評価・プロンプト最適化・モデルデプロイ |

> 💡 各 Azure 系 Skill の詳細は各 SKILL.md を参照。

**【CI/CD / cicd】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| GitHub Actions CI/CD | `github-actions-cicd` | `.github/skills/cicd/github-actions-cicd/SKILL.md` | OIDC 認証・GitHub Actions CI/CD・シークレット管理 |

**【オブザーバビリティ / observability】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| Application Insights 計装 | `appinsights-instrumentation` | `.github/skills/observability/appinsights-instrumentation/SKILL.md` | App Insights SDK・自動/手動計装ガイド |

**【テスト / testing】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| テスト戦略テンプレート | `test-strategy-template` | `.github/skills/testing/test-strategy-template/SKILL.md` | テストピラミッド・テストダブル・データ戦略・カバレッジ方針 |
