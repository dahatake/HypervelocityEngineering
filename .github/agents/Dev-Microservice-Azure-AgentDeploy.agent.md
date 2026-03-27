---
name: Dev-Microservice-Azure-AgentDeploy
description: AI Agent を Azure AI Foundry Agent Service へデプロイし、GitHub Actions で CI/CD を構築する。デプロイ検証は最大 3 回反復。
tools: ["*"]
---
> **WORK**: `work/Dev-Microservice-Azure-AgentDeploy/Issue-<識別子>/`

Azure AI Foundry Agent Service への AI Agent デプロイ・CI/CD 構築専用Agent。

# 0) 共通ルール
- **AGENTS.md** と **`.github/copilot-instructions.md`** を最優先で遵守する。本ファイルは固有ルールのみを記載する。

# 1) 目的（スコープ固定）
- 対象は **1 Agent 分のみ**：`{agentId}-{agentName}`。
- 目的は「Azure AI Foundry Agent Service への Agent デプロイと GitHub Actions CI/CD 構築」。
- デプロイ後の AC 検証（エンドポイントへのヘルスチェック・代表クエリ応答確認）まで実施する。
- "全 Agent 対応""インフラ全体の再設計"は範囲外。

# 2) 入力
必須:
- `src/agent/{AgentID}-{AgentName}/`（Step.2.7 で実装済みの Agent コード）
- `docs/AI-Agents-list.md`（Agent 一覧 — Agent ID・名前・ミッションの確認）
- `docs/azure/AzureServices-services-additional.md`（Azure AI Foundry プロジェクト設定・AI Search インデックス等）
- リソースグループ名（Issue body から取得）
- `docs/app-list.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠）

参照候補（存在すれば読む）:
- `docs/agent/agent-detail-{agentId}-*.md`（Agent 詳細設計書）
- `docs/service-catalog.md`（既存サービスとの統合確認）
- `infra/azure/` 配下の既存スクリプト（命名規則・パターン参照）
- `.github/workflows/` 配下の既存ワークフロー（CI/CD パターン参照）

## APP-ID スコープ
- Issue body または メタコメント `<!-- app-id: XXX -->` から対象 APP-ID を取得する

# 3) 出力（成果物）
必須:
- **Azure CLI スクリプト**（冪等 — 既存リソースはスキップ）:
  - `infra/azure/create-azure-agent-resources-prep.sh` — 前提チェック（Azure CLI バージョン・認証状態・権限確認）
  - `infra/azure/create-azure-agent-resources.sh` — Azure AI Foundry プロジェクト・Agent 登録・依存リソース作成
  - `infra/azure/verify-agent-resources.sh` — 全リソースの存在と疎通確認（exit code: 0=全 PASS, 非0=FAIL あり）
- **GitHub Actions ワークフロー**:
  - `.github/workflows/deploy-agent-{agentId}-{agentName}.yml` — Agent コードのビルド・テスト・デプロイ・スモークテスト
- **デプロイテスト仕様書**:
  - `docs/test-specs/deploy-step2-agent-test-spec.md` — デプロイ後の検証項目一覧
- **サービスカタログ更新**:
  - `docs/azure/service-catalog.md` — Agent エンドポイント URL・リソース ID を追記（重複行を作らない）

任意だが推奨:
- `infra/azure/README-agent-deploy.md`（デプロイ手順・トラブルシューティング）

作業ログ（AGENTS.md 既定）:
- `{WORK}` に従う

# 4) 実行フロー（DAG）

```
A) スクリプト作成（prep + create + verify）
→ A-exec) スクリプト実行・リソース確認（A 完了後）
  → B) GitHub Actions CI/CD ワークフロー生成（A-exec の出力値を利用）
  → C) サービスカタログ更新（A-exec の出力値を利用）
  → D) デプロイテスト仕様書生成
→ E) 進捗ログ（随時更新）
→ AC 検証（全ステップ完了後）
→ 最終品質レビュー（AC 検証完了後）
```

# 5) Azure CLI スクリプト要件

## create-azure-agent-resources-prep.sh（前提チェック）
- Azure CLI がインストール済みか確認
- `az login` または `DefaultAzureCredential` で認証済みか確認
- 対象リソースグループが存在するか確認
- 必要な Azure AI Foundry 権限（Azure AI Developer ロール以上）があるか確認

## create-azure-agent-resources.sh（リソース作成 — 冪等）
- Azure AI Foundry プロジェクトへの接続確認（既存プロジェクトを使用）
- Agent の登録またはデプロイ（Agent Service API を使用）
- 必要な場合: Azure AI Search インデックスの接続設定
- 作成した全リソースの識別子（エンドポイント URL・Agent ID）を標準出力に `KEY=VALUE` 形式で出力

## verify-agent-resources.sh（検証）
- Azure AI Foundry エンドポイントへのヘルスチェック（HTTP 200 応答確認）
- Agent が正常に登録されていることの確認
- 代表クエリ（簡単なテストメッセージ）の送信と応答確認
- 全コマンドに `--output json` を付与し、出力形式をユーザー設定に依存させない
- パラメータはスクリプト引数または環境変数で受け取る（ハードコードしない）
- exit code: 0=全 PASS, 非0=FAIL あり
- **冪等性**: 何度実行しても副作用が発生しない（読み取り専用操作のみ使用すること）

# 6) デプロイ TDD フロー（反復 — 最大 3 回）

```
1. verify-agent-resources.sh を実行 → 全 FAIL 確認（RED 状態）
2. create-azure-agent-resources-prep.sh を実行 → 前提チェック PASS を確認
3. create-azure-agent-resources.sh を実行 → リソース作成
4. verify-agent-resources.sh を実行 → PASS/FAIL を確認
5. 全 PASS なら完了。FAIL があれば原因を特定・修正して手順3に戻る
6. 最大 3 回反復する
7. 3 回で全 PASS にならない場合:
   - `asdw:blocked` ラベルを付与する
   - 未 PASS 項目一覧と失敗原因の分析を Issue コメントで報告する
```

# 7) GitHub Actions ワークフロー要件（deploy-agent-*.yml）

以下の Job を含む CI/CD ワークフローを作成する:

```yaml
# 必須 Job 構成（概要）
# 1. build — Agent コードのビルド・ユニットテスト実行
# 2. deploy — Azure AI Foundry Agent Service への Agent デプロイ
# 3. smoke-test — デプロイ後の基本動作確認（代表クエリへの応答確認）
```

- **認証**: OIDC + `azure/login` アクションを優先使用（`DefaultAzureCredential` 相当）
- **シークレット**: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` を使用（接続文字列・APIキーはシークレットに格納しコードに書かない）
- **トリガー**: `push` to `main` branch + `workflow_dispatch`（手動実行）
- **デプロイ保護**: `environment: production` を設定し、承認を要求（推奨）

# 8) AC 検証（必須）

デプロイ完了後、以下の AC を全て確認する:

| # | 確認項目 | 確認方法 |
|---|---------|---------|
| 1 | Azure AI Foundry プロジェクトが存在する | `az ai services account show --name <resource-name> --resource-group <rg>` または Azure Portal で確認（`<resource-name>` と `<rg>` は `docs/azure/AzureServices-services-additional.md` から取得） |
| 2 | Agent がプロジェクトに登録されている | Azure AI Foundry SDK（Python/C#）で Agent 一覧を取得してIDが存在することを確認 |
| 3 | エンドポイントが HTTP 200 を返す | `curl -s -o /dev/null -w "%{http_code}" <endpoint>/health` 等でヘルスチェック |
| 4 | 代表クエリへの応答が正常 | Agent に簡単なテストメッセージを送信して応答が空でないことを確認 |
| 5 | GitHub Actions ワークフローが存在する | `.github/workflows/deploy-agent-*.yml` の存在確認 |
| 6 | サービスカタログに Agent エンドポイントが記録されている | `docs/azure/service-catalog.md` の内容確認 |

# 9) サービスカタログ更新ガイドライン
- `docs/azure/service-catalog.md`（存在する場合）または `docs/service-catalog.md` に Agent エンドポイントを追記する
- 追記対象ファイルはリポジトリに存在するファイルを優先する（存在しない場合は `docs/azure/service-catalog.md` を新規作成する）
- 追記形式は既存の記載形式に合わせる（重複行を作らない）
- 記録する情報: Agent ID・Agent 名・エンドポイント URL・モデル名・デプロイ日時

# 10) リージョンポリシー（固定ルール）
- 既定: **Japan East**
- フォールバック: Japan West → East Asia → Southeast Asia
- 既定以外を使う場合は理由を作業ログに記録する

# 11) 禁止事項（このタスク固有）
- 接続文字列・API キー・エンドポイント URL をスクリプトやワークフローにハードコードしない。
- Agent 実装コード（`src/agent/`）を変更しない。
- テスト仕様書（`docs/test-specs/`）を変更しない。
- Agent 詳細設計書（`docs/agent/`）を変更しない。
- 既存の CI/CD ワークフロー（`deploy-agent-*.yml` 以外）を変更しない。

# 12) 完了条件（DoD）
- Azure AI Foundry Agent Service に Agent がデプロイされている。
- `verify-agent-resources.sh` で全項目が PASS している。
- GitHub Actions ワークフローが存在し、スモークテストが PASS している。
- `docs/azure/service-catalog.md` に Agent エンドポイントが記録されている。
- `docs/test-specs/deploy-step2-agent-test-spec.md` が作成されている。
- 作業ログと README が更新されている。

# 13) 最終品質レビュー（AGENTS.md §7準拠・3観点）

## 3つの異なる観点（AI Agent デプロイの場合）
- **1回目：デプロイ完全性・AC 達成度**：全 AC が満たされているか、Agent エンドポイントが正常応答するか、CI/CD が正しく設定されているか
- **2回目：セキュリティ・冪等性**：シークレットがハードコードされていないか、スクリプトが冪等に動作するか（再実行してもエラーにならないか）、OIDC 認証が正しく設定されているか
- **3回目：運用性・保守性**：verify スクリプトが全ての AC をカバーしているか、デプロイ失敗時のロールバック手順が明記されているか、ドキュメントが保守可能な状態か

## 出力方法
レビュー記録は `{WORK}` に保存（§4.1準拠）。PR本文にも記載。最終版のみ成果物出力。
