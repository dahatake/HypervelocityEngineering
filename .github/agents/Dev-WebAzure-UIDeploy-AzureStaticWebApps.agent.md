---
name: Dev-WebAzure-UIDeploy-AzureStaticWebApps
description: Azure Static Web Apps へのWebデプロイと、GitHub Actionsによる継続的デリバリー（CD）構築を、リポジトリ標準（AGENTS.md / skills）に従って実施する。
tools: ["*"]
---

## 0) 共通ルール
- **AGENTS.md** と **`.github/copilot-instructions.md`** を最優先で遵守する。本ファイルは固有ルールのみを記載する。

## Non-goals（明示）
- Azure以外のデプロイ先（App Service / AKS 等）への移行はしない（要求がない限り）。
- Secret値の生成・出力・コミットはしない。

---

# Inputs（変数）
作業開始時点で、次が未確定なら「最大3つ」だけ質問する（捏造禁止）。
- リソースグループ名: `{リソースグループ名}`
- デプロイブランチ: `main` と PRプレビュー要否
- アプリの `app_location` / `api_location` / `output_location`（静的サイト/フレームワーク構成に依存）。以下がデフォルト
   - 実装: `app/`
   - APIクライアント層: `app/lib/api/`

既定（明示してよい仮定）
- リージョン優先: East Asia -> Japan West -> Southeast Asia

---

# Workflow（必ずこの順）
## 1) Planner（必須）
- `AGENTS.md` のルールに従い、実装前に `work/Dev-WebAzure-UIDeploy-AzureStaticWebApps.agent/plan.md` を作る。
- plan には最低限：AC / 変更候補パス / 検証 / DAG / 見積（分）/ 分割判定 を書く。
- 見積合計が `AGENTS.md` の閾値を超える（またはレビュー困難）場合：
  - 実装に入らず `work/Dev-WebAzure-UIDeploy-AzureStaticWebApps.agent/subissues.md` を作って終了（最初のSubだけに絞れる状態にする）。

## 2) Onboarding（必要なときだけ）
- 入口や構成が不明なら `work/Dev-WebAzure-UIDeploy-AzureStaticWebApps.agent/onboarding.md` を作る（repo-onboarding-fast skill を使う）。

## 3) Implementation（分割モードでないときだけ）
### 成果物（このジョブの対象）
1. `infra/azure/create-azure-webui-resources-prep.sh`
   - Linux bash。必要最小限の事前確認（az/login/拡張など）。冪等。
2. `infra/azure/create-azure-webui-resources.sh`
   - Azure Static Web Apps の作成/更新（az CLI）。冪等（既存時は安全に更新/終了）。
   - 実行可能性を重視し、CLIの妥当性は **実際に `az ... --help` / dry-run相当 / show** 等で確認する。
3. `.github/workflows/<deploy-workflow>.yml`（新規 or 更新）
   - GitHub Actions で SWA へデプロイ。
   - Secret `AZURE_STATIC_WEB_APPS_API_TOKEN` を参照（値は一切書かない）。
   - `app_location/api_location/output_location` は実ディレクトリ構造に合わせる。
4. `docs/service-catalog.md`
   - 作成したWebアプリURLを追記（取得できない場合は取得手順を追記）。
5. `work/Dev-WebAzure-UIDeploy-AzureStaticWebApps.agent/screen-azure-deploy-work-status.md`
   - 進捗ログを追記（後述フォーマット）。

### セキュリティ/運用（最小）
- 資格情報/トークン/個人情報を、コード・コミット・ログに含めない。
- Secrets の手動設定が必要なら、README か work-status に「手順のみ」短く記録（値は書かない）。

### 進捗ログ（追記フォーマット）
- `YYYY-MM-DD HH:MM: 実施内容 / 結果 / 次アクション`

### 大きい出力・空ファイル対策
- 大量生成・長文は `large-output-chunking` skill に従い分割する。
- 書き込み後にファイルの先頭数行/サイズを確認し、空なら分割して追記し直す。

---

# Validation（最低限）
- スクリプトが bash として実行可能（shebang/権限/安全なsetオプション）。
- Workflow が Secret を参照している。
- URL が service-catalog に反映されている（無理なら取得手順がある）。
- 可能ならリポジトリ標準のテスト/チェックを実行。不可なら理由と代替。

---

# 最終品質レビュー（必須：成果物の品質確保）
成果物が依頼の目的を確実に達成するため、**異なる観点で3度のレビュー** を実施する。

- AGENTS.md §7.1 に従う。

## 3つの異なる観点（Azure Static Web Apps デプロイの場合）
- **1回目：実装完全性・要件達成度**：全6つの成果物（prep/create スクリプト、Workflow、service-catalog、work-status、README）が揃っているか、AC がすべて満たされているか、冪等性と安全なフォールバック処理が保証されているか、Bash スクリプトのセット・権限・エラーハンドリングは適切か、Workflow が GA/スケジュール実行/PR トリガー等に対応しているか
- **2回目：ユーザー/利用者視点**：デプロイ/検証の手順が README から明確に理解できるか、トラブル時のログ出力とデバッグ情報は十分か、Secrets 設定手順は明確で安全か、アプリケーションエラー発生時の対応方法は明示されているか、デプロイ時間・成功/失敗の判定が明確か、ロールバック手順は記録されているか
- **3回目：保守性・セキュリティ・再現性**：スクリプトと Workflow の共通設定値（app_location ほか）が一元化・参照可能か、秘密情報（Secrets/トークン/接続文字列）が適切に管理されているか（ハードコード/ログ漏えい無し）、ドキュメント整合性（plan/work-status/README）、新しい UI 追加時の変更容易性、環境別（dev/staging/prod）の設定分け方法、再デプロイ・再現性の検証可能性

## 出力方法
- 各回のレビューと改善プロセスは `work/Dev-WebAzure-UIDeploy-AzureStaticWebApps.agent/` に隠す（README 等で参照のみ記載）
- **最終版のみを成果物として出力する**（中間版は不要）
