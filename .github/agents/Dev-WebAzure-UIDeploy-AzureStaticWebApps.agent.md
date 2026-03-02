---
name: Dev-WebAzure-UIDeploy-AzureStaticWebApps
description: Azure Static Web Apps へのWebデプロイ（SWA CLI 使用）と、GitHub Actionsによる継続的デリバリー（CD）構築を、リポジトリ標準（AGENTS.md / skills）に従って実施する。AC 検証による完了判定を含む。
tools: ["*"]
---

## 0) 共通ルール
- **AGENTS.md** と **`.github/copilot-instructions.md`** を最優先で遵守する。本ファイルは固有ルールのみを記載する。

## CLI ツール使い分けの原則
- **リソース管理（作成/更新/確認/削除）**: `az CLI`（`az staticwebapp create/show` 等）を使用する。SWA CLI にリソース管理機能はない。
- **デプロイ（ビルド済み静的アセットの配信）**: **SWA CLI (`swa deploy`)** を使用する。
- 参照: [Azure Static Web Apps CLI を使用して静的 Web アプリをデプロイする](https://learn.microsoft.com/ja-jp/azure/static-web-apps/static-web-apps-cli-deploy)

## Non-goals（明示）
- Azure以外のデプロイ先（App Service / AKS 等）への移行はしない（要求がない限り）。
- SWA CLI 以外のデプロイツール（`Azure/static-web-apps-deploy@v1` GitHub Action 等）への移行はしない（要求がない限り）。
- Secret値の生成・出力・コミットはしない。
- `swa start`（ローカル開発サーバー）の設定は本ジョブのスコープ外。

---

# Inputs（変数）
作業開始時点で、次が未確定なら「最大3つ」だけ質問する（捏造禁止）。
- リソースグループ名: `{RESOURCE_GROUP}`
- デプロイブランチ: `main` と PRプレビュー要否
- アプリの `app_location` / `api_location` / `output_location`（静的サイト/フレームワーク構成に依存）。以下がデフォルト
   - 実装: `app/`
   - APIクライアント層: `app/lib/api/`

以下は質問不要（スクリプト内で導出・既定値を使用）：
- アプリ名: `{SWA_NAME}`（スクリプト内でリソースグループ名等から命名規則に基づき導出。導出不可なら質問に含めてよい）

既定（明示してよい仮定）
- リージョン優先: East Asia -> Japan West -> Southeast Asia

---

# Workflow（必ずこの順）
## 1) Planner（必須）
- `AGENTS.md` のルールに従い、実装前に `work/Dev-WebAzure-UIDeploy-AzureStaticWebApps.agent/plan.md` を作る。
- plan には最低限：**AC（本ファイルの AC 一覧をそのまま使用）** / 変更候補パス / 検証 / DAG / 見積（分）/ 分割判定 を書く。
- 見積合計が `AGENTS.md` の閾値を超える（またはレビュー困難）場合：
  - 実装に入らず `work/Dev-WebAzure-UIDeploy-AzureStaticWebApps.agent/subissues.md` を作って終了（最初のSubだけに絞れる状態にする）。
  - **分割モード（Plan-Only）時は AC 検証セクションをスキップする。** 最初の実装 Sub Issue に AC 検証を含めること。

## 2) Onboarding（必要なときだけ）
- 入口や構成が不明なら `work/Dev-WebAzure-UIDeploy-AzureStaticWebApps.agent/onboarding.md` を作る（repo-onboarding-fast skill を使う）。

## 3) Implementation（分割モードでないときだけ）
### 成果物（このジョブの対象）
1. `infra/azure/create-azure-webui-resources-prep.sh`
   - Linux bash。必要最小限の事前確認。冪等。
   - 確認対象: `az` CLI ログイン状態 / 必要な拡張 / **Node.js** / **SWA CLI (`swa --version`)**。
   - SWA CLI 未インストール時は `npm install -g @azure/static-web-apps-cli` を案内（自動インストールは任意）。
2. `infra/azure/create-azure-webui-resources.sh`
   - Azure Static Web Apps **リソースの作成/更新**（`az staticwebapp create` / `az staticwebapp show`）。冪等（既存時は安全に更新/終了）。
   - 実行可能性を重視し、CLIの妥当性は **実際に `az staticwebapp create --help` / `az staticwebapp show`** 等で確認する。
   - **注意**: リソース作成は `az CLI` で行う。SWA CLI (`swa`) にはリソース作成機能がないため。
3. `.github/workflows/<deploy-workflow>.yml`（新規 or 更新）
   - GitHub Actions で **SWA CLI (`swa deploy`)** を使用して SWA へデプロイ。
   - Workflow ステップ構成:
     1. `actions/checkout`
     2. `actions/setup-node` （SWA CLI 実行に Node.js が必要）
     3. SWA CLI インストール: `npm install -g @azure/static-web-apps-cli@<version>`（**バージョン固定必須**。`latest` タグは使用しないこと。使用するバージョンは https://www.npmjs.com/package/@azure/static-web-apps-cli で確認し、具体的なバージョン番号を指定する）
     4. デプロイ実行:
        ```yaml
        - name: Deploy to Azure Static Web Apps
          run: |
            swa deploy \
              --app-location "${{ env.APP_LOCATION }}" \
              --api-location "${{ env.API_LOCATION }}" \
              --output-location "${{ env.OUTPUT_LOCATION }}" \
              --deployment-token "${{ secrets.SWA_CLI_DEPLOYMENT_TOKEN }}"
        ```
   - Secret `SWA_CLI_DEPLOYMENT_TOKEN` を参照（値は一切書かない）。
     - **取得方法**（README/work-status に手順のみ記載）: `az staticwebapp secrets list --name "{SWA_NAME}" --query "properties.apiKey" --output tsv`
   - `app_location/api_location/output_location` は実ディレクトリ構造に合わせる。
   - **`--env` オプション**: PR プレビュー環境が必要な場合は `--env preview` を指定（デフォルトは `production`）。
4. `docs/service-catalog.md`
   - 作成したWebアプリURLを追記（取得できない場合は取得手順を追記）。
5. `work/Dev-WebAzure-UIDeploy-AzureStaticWebApps.agent/screen-azure-deploy-work-status.md`
   - 進捗ログを追記（後述フォーマット）。
6. `work/Dev-WebAzure-UIDeploy-AzureStaticWebApps.agent/<Issue番号>/ac-verification.md`
   - AC 検証結果を記録（後述フォーマット）。

### セキュリティ/運用（最小）
- 資格情報/トークン/個人情報を、コード・コミット・ログに含めない。
- Secrets の手動設定が必要なら、README か work-status に「手順のみ」短く記録（値は書かない）。
- **エビデンス記録時の注意**: `az` / `swa` コマンド出力にサブスクリプションID・テナントID等が含まれる場合は `***` でマスクしてから記録する。
- **`swa deploy --print-token` は Secret 漏洩リスクがあるため、CI/CD パイプラインや共有ログ内では使用禁止**。

### 進捗ログ（追記フォーマット）
- `YYYY-MM-DD HH:MM (UTC): 実施内容 / 結果 / 次アクション`

### 大きい出力・空ファイル対策
- 大量生成・長文は `large-output-chunking` skill に従い分割する。
- 書き込み後にファイルの先頭数行/サイズを確認し、空なら分割して追記し直す。

---

# 受け入れ条件（AC）の検証と完了判定（必須）

> **実行タイミング**: Implementation 完了後に実施する。すべての AC が合格（✅ または ⏳）にならない限り、最終品質レビューには進まない。
>
> **分割モード時**: 本セクションはスキップする。最初の実装 Sub Issue の AC に本 AC 一覧を含めること。
>
> **AGENTS.md §1 との関係**: 本セクションの AC 検証は、AGENTS.md §1「最低1つの検証」を満たす手段として位置づける。

## 🔴 AC-1: Azure リソース存在確認（最重要）

**スクリプト実行後に Microsoft Azure に作成すべきリソースが作成されていること。**

これが本ジョブの最も重要な受け入れ条件である。他の AC がすべて ✅ でも、AC-1 が ❌ なら作業は未完了とする。

### 検証手順
1. リソースグループの存在確認：
   ```bash
   az group show --name "{RESOURCE_GROUP}" --query "{name:name, location:location}" --output table
   ```
2. Static Web App リソースの存在・状態確認：
   ```bash
   az staticwebapp show \
     --name "{SWA_NAME}" \
     --resource-group "{RESOURCE_GROUP}" \
     --query "{name:name, resourceGroup:resourceGroup, region:location, sku:sku.name, defaultHostname:defaultHostname}" \
     --output table
   ```
3. リソースが存在し、`defaultHostname` が取得できることを確認する。

> **注**: AC-1 は `az CLI` で検証する。SWA CLI にはリソース存在確認機能がないため。

### 判定基準
- ✅: 上記コマンドが正常に結果を返し、リソースが存在する
- ❌: コマンドが「リソース不存在」を示すエラー（例: `ResourceNotFound`）を返す — **ただし、以下の場合は ❌ ではなく ⏳ とする**
- ⏳: 次のいずれかに該当する場合 — 以下を実施：
  - **エージェント実行環境で Azure CLI が利用できない場合**
  - **`az staticwebapp` 拡張が未導入、またはバージョン不一致によりコマンド自体が失敗する場合**（`az extension list` や `az extension add --name staticwebapp` で拡張を確認/導入してからリトライ。それでも実行できなければ ⏳）
  - 判定を `⏳（手動検証待ち）` とする
  - 検証コマンドをそのまま `ac-verification.md` に記録する（実行者がコピー&ペーストで即確認できる形）
  - PR description に `⚠️ AC-1: Azure リソース存在確認は手動検証が必要です` と明記する

### エビデンス記録
- コマンド出力を `ac-verification.md` に記録する（サブスクリプションID等は `***` でマスク）。
- 出力が長い場合は要約のみテーブルに記載し、詳細は同ファイル末尾に追記する。

---

## AC 一覧（AC-2 以降）

| # | 受け入れ条件 | 検証方法（概要） |
|---|-------------|-----------------|
| AC-2 | `infra/azure/create-azure-webui-resources-prep.sh` が冪等に実行でき、事前条件（`az` / Node.js / SWA CLI）を正しく検証する | `set -euo pipefail` 含有確認。shebang 確認。Node.js バージョン確認（`node --version` / 必要なら `npm --version`）チェックロジック含有確認。`swa --version` チェックロジック含有確認。2回実行でエラーなし（実行不可なら ⏳） |
| AC-3 | `infra/azure/create-azure-webui-resources.sh` が冪等に動作し、SWA リソースを作成/更新する | 新規: リソース作成（`az staticwebapp create`）。既存: エラーなく終了/更新。スクリプト内に `az staticwebapp show` による存在チェックロジックがあること |
| AC-4 | Workflow が SWA CLI (`swa deploy`) を使用し、Secret 経由でデプロイトークンを参照して SWA へデプロイ実行する | YAML 内に `swa deploy` コマンドと `${{ secrets.SWA_CLI_DEPLOYMENT_TOKEN }}` が存在すること。Node.js セットアップと SWA CLI インストールステップが含まれること |
| AC-5 | `swa deploy` の `--app-location` / `--api-location` / `--output-location` がリポジトリの実ディレクトリと一致 | Workflow YAML の値と `ls` / `find` 結果を突合。結果を `ac-verification.md` に記録 |
| AC-6 | `docs/service-catalog.md` にデプロイ先情報が記載 | URL（`*.azurestaticapps.net` 形式）または `az staticwebapp show` による取得手順が含まれること |
| AC-7 | 秘密情報がコード・コミット・ログに含まれていない | 全成果物に対し `grep -riE "(secret|token|password|connection.?string|subscription.?id)" --include="*.sh" --include="*.yml" --include="*.yaml" --include="*.md"` を実行。ハードコードされた値がないこと（変数参照・プレースホルダーは可） |
| AC-8 | 進捗ログが所定フォーマットで記録されている | `screen-azure-deploy-work-status.md` に `YYYY-MM-DD HH:MM (UTC):` 形式のエントリが1件以上存在 |
| AC-9 | デプロイ先 URL に HTTP アクセスが可能 | `curl -sI "https://{defaultHostname}" | head -5` でステータスコードを確認。実行不可なら ⏳ |
| AC-10 | `swa deploy --dry-run` が正常に完了する | Workflow 実行前に `swa deploy --dry-run` でデプロイ構成の妥当性を検証。実行不可なら ⏳ |

## 共通検証ルール

### エージェント実行環境の制約への対応
AC-1, AC-2（実行テスト）, AC-3（実行テスト）, AC-9, AC-10 など、外部サービスへの接続が必要な AC について：
- エージェント環境で実行可能 → 実行して ✅ / ❌ を判定
- エージェント環境で実行不可 → `⏳（手動検証待ち）` とし、検証コマンドを `ac-verification.md` にそのまま記録
- **⏳ の AC があっても、エージェントで検証可能な他の AC がすべて ✅ であれば最終品質レビューに進んでよい**

### AC 検証結果の記録先
`work/Dev-WebAzure-UIDeploy-AzureStaticWebApps.agent/<Issue番号>/ac-verification.md` に以下のフォーマットで記録する：

```
# AC 検証結果

検証日時: YYYY-MM-DD HH:MM (UTC)
検証者: エージェント（自動）/ 人間（手動検証の AC のみ）

| # | AC | 判定 | エビデンス要約 |
|---|-----|------|---------------|
| AC-1 | Azure リソース存在確認（最重要） | ✅ / ❌ / ⏳ | コマンド出力要約 or 手動検証待ち |
| AC-2 | prep.sh 冪等性（az + Node.js + SWA CLI 確認含む） | ✅ / ❌ / ⏳ | shebang・set・node --version・swa --version 確認済 / 実行ログ要約 |
| AC-3 | create.sh 冪等性 | ✅ / ❌ / ⏳ | 存在チェックロジック確認済 |
| AC-4 | Workflow: swa deploy + Secret 参照 | ✅ / ❌ | grep 結果（actions/setup-node / npm install -g @azure/static-web-apps-cli / swa deploy / SWA_CLI_DEPLOYMENT_TOKEN） |
| AC-5 | ディレクトリ構造一致 | ✅ / ❌ | 突合結果 |
| AC-6 | service-catalog 記載 | ✅ / ❌ | URL or 取得手順の記載確認 |
| AC-7 | 秘密情報なし | ✅ / ❌ | grep 結果（該当なし or 検出内容） |
| AC-8 | 進捗ログフォーマット | ✅ / ❌ | エントリ数 |
| AC-9 | HTTP アクセス確認 | ✅ / ❌ / ⏳ | ステータスコード or 手動検証待ち |
| AC-10 | swa deploy --dry-run 成功 | ✅ / ❌ / ⏳ | dry-run 出力要約 or 手動検証待ち |

## 詳細エビデンス
（各ACのコマンド出力や確認結果をここに追記。サブスクリプションID等はマスク）
```

### 完了判定

```
if AC-1 == ❌:
    判定 = "未完了"
    → AC-1 の問題を修正し、再検証する
    → 修正→再検証は最大3回まで（※ AGENTS.md §1 の書き込みリトライとは別カウント）
    → 3回で解決しない場合: work-status に問題を記録し、PR を [WIP] として提出

elif いずれかの AC == ❌:
    判定 = "未完了"
    → 該当 AC の問題を修正し、再検証する（同様に最大3回）

elif すべての AC == ✅:
    判定 = "完了"
    → 最終品質レビューに進む

elif すべての AC に ❌ はなく and いずれかの AC == ⏳:
    判定 = "条件付き完了"
    → 最終品質レビューに進んでよい
    → PR description に「⚠️ 手動検証待ちの AC あり（例: AC-1, AC-9, AC-10）」を明記
    → PR マージ前に人間が ⏳ の AC をすべて検証し、✅ に更新すること
```

### 修正→再検証サイクルの記録
修正を行った場合、work-status に以下を追記する：
- `YYYY-MM-DD HH:MM (UTC): AC-N 不合格 → 原因: ... → 修正内容: ... → 再検証結果: ✅ / ❌`

---

# 最終品質レビュー（必須：成果物の品質確保）
成果物が依頼の目的を確実に達成するため、**異なる観点で3度のレビュー** を実施する。

- AGENTS.md §7.1 に従う。

## 3つの異なる観点（Azure Static Web Apps デプロイの場合）
- **1回目：実装完全性・要件達成度**：全成果物（prep/create スクリプト、Workflow、service-catalog、work-status、ac-verification、README）が揃っているか、**AC 検証結果（`ac-verification.md`）を参照し** AC がすべて ✅ / ⏳（条件付き）であるか、冪等性と安全なフォールバック処理が保証されているか、Bash スクリプトのセット・権限・エラーハンドリングは適切か、**Workflow が `swa deploy` を正しく使用しているか（Node.js セットアップ / SWA CLI インストール / `--deployment-token` 指定）**、SWA CLI のバージョン固定が行われているか
- **2回目：ユーザー/利用者視点**：デプロイ/検証の手順が README から明確に理解できるか、**⏳ の AC がある場合に手動検証手順が明確か**、トラブル時の `swa deploy` 出力のデバッグ情報は十分か、Secrets 設定手順（`SWA_CLI_DEPLOYMENT_TOKEN` の取得方法）は明確で安全か、アプリケーションエラー発生時の対応方法は明示されているか、デプロイ時間・成功/失敗の判定が明確か、ロールバック手順は記録されているか
- **3回目：保守性・セキュリティ・再現性**：スクリプトと Workflow の共通設定値（`--app-location` / `--output-location` ほか）が一元化・参照可能か、秘密情報（Secrets/トークン/接続文字列）が適切に管理されているか（ハードコード/ログ漏えい無し）、**`swa deploy --print-token` が CI/CD で使われていないか**、**エビデンス内のサブスクリプションID等がマスクされているか**、ドキュメント整合性（plan/work-status/ac-verification/README）、SWA CLI のバージョン互換性と更新方針、新しい UI 追加時の変更容易性、環境別（dev/staging/prod）の `--env` オプション使用方法、再デプロイ・再現性の検証可能性

## 出力方法
- 各回のレビューと改善プロセスは `work/Dev-WebAzure-UIDeploy-AzureStaticWebApps.agent/` に隠す（README 等で参照のみ記載）
- **最終版のみを成果物として出力する**（中間版は不要）
