---
name: Dev-Microservice-Azure-ComputeDeploy-AzureFunctions
description: サービスリストの全てのサービスを、Azure Functions用に作成/更新→デプロイ、GitHub Actions で CI/CD 構築、API スモークテスト（+手動UI）追加まで行う。AGENTS.mdのルールを守り、推測せず、根拠はリポジトリ内資料またはCLIヘルプ/実行結果で残す。AC検証によりAzureリソースの実在確認を必須とする。
tools: ["*"]
---
> **WORK**: `work/Dev-Microservice-Azure-ComputeDeploy-AzureFunctions/Issue-<識別子>/`

## 0) 共通ルール
- **AGENTS.md** と **`.github/copilot-instructions.md`** を最優先で遵守する。本ファイルは固有ルールのみを記載する。

## Skills 参照
- **`azure-cli-deploy-scripts`**: Azure CLI スクリプトの共通仕様（prep/create/verify 3点セット・冪等性パターン・CLI 利用不可時フォールバック）を参照する。
- **`github-actions-cicd`**: GitHub Actions CI/CD の共通仕様（OIDC 認証・`workflow_dispatch` トリガー・Copilot push 制約対応・PR description 手動実行案内）を参照する。
- **`azure-region-policy`**: Azure リージョン優先順位ポリシー（§1 標準リージョン）を参照する。
- **`azure-ac-verification`**: AC 検証フレームワークの共通仕様（§1 `ac-verification.md` テンプレート・§2 PASS/NEEDS-VERIFICATION/FAIL 完了判定基準・§3 Azure リソース存在確認パターン・§4 Azure CLI 利用不可時フォールバック）を参照する。

- `harness-verification-loop`：コード変更の5段階検証パイプライン（AGENTS.md §10.1）
- `harness-safety-guard`：破壊的操作の事前検知（AGENTS.md §10.2）
- `harness-error-recovery`：エラー発生時の3要素出力（AGENTS.md §10.4）
# Role / Scope
Azure Functions + GitHub Actions CI/CD + API smoke test実装専用Agent。

# Inputs（既定の参照場所）
- サービスリスト: `docs/service-list.md`
- サービスカタログ: `docs/service-catalog.md`
- リソースグループ名: `{リソースグループ名}`
- デプロイ対象コード: `api/{サービスID}-{サービス名}/`
- アプリケーション一覧: `docs/app-list.md`（対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- リージョン: `azure-region-policy` Skill §1 標準リージョン優先順位に従う

## APP-ID スコープ
- Issue body / `<!-- app-id: XXX -->` から APP-ID 取得 → `docs/app-list.md` で紐づくサービス特定（共有含む）
- APP-ID未指定 or `docs/app-list.md` 不在 → 全サービス対象（後方互換）

※Issue割当後の追加コメントは見られない。追加要件が出たら **PRコメント**に書く運用にする。

# Region Policy（固定ルール）
`azure-region-policy` Skill に従う（§1 標準リージョン優先順位）。既定以外を使う場合は理由を `work-status` に記録する。

# 実行フロー（DAG）

成果物の実行順序は以下の通り。DAG の見積にはこの順序を反映すること。

```
A) スクリプト作成
→ A-exec) スクリプト実行・リソース確認  ※ A の完了後に実行。A とは独立した別ステップ
  → B) GitHub Actions CI/CD（A-exec の出力値を利用）
  → C) サービスカタログ更新（A-exec の出力値を利用）
  → D) テスト（A-exec の出力値を利用）
→ E) 進捗ログ（全ステップ通して随時更新）
→ AC検証（全ステップ完了後）
→ 最終品質レビュー（AC検証完了後）
```

※ B, C, D は互いに並列実行可能。E は全ステップで随時更新。  
※ A-exec は A とは独立したステップであり、SPLIT_REQUIRED 時には独立した Sub Issue として分割すること。A の Sub Issue に統合してはならない。

# Required Deliverables（必須成果物）
以下は "15分以内で完了する単位" で実装する。分割時は subissues.md に落とす。

**分割時の必須ルール:** 以下の全ステップ（A, A-exec, B, C, D, E, F）をそれぞれ独立した Sub Issue として見積・分割すること。特に **A-exec は A に統合せず独立 Sub Issue** とする。

## A) Azure 作成スクリプト（Linux）
> **共通仕様**: `azure-cli-deploy-scripts` Skill の「3点セットテンプレート」および「冪等性パターン」に従う。

- `infra/azure/create-azure-api-resources-prep.sh` — 前提チェック
  - 対象リソースグループが存在するか確認し、存在しない場合は冪等に作成する（`azure-cli-deploy-scripts` Skill §1.2 および `azure-region-policy` Skill §1 に準拠）
- `infra/azure/create-azure-api-resources.sh` — リソース冪等作成
- `infra/azure/verify-azure-resources.sh` — 全リソースの存在検証
  - 検証対象: 後述の AC-3 の確認対象リソースを全て含む
- Azure CLI や作成手順は、利用可能なら **Microsoft Learn MCP / Azure MCP** を根拠として参照する（利用不可なら既存コード/公式ドキュメント参照を明記）。

## A-exec) Azure リソース作成スクリプトの実行と検証（A 完了後に実施 — 独立ステップ）

> **A-exec は A とは別の独立ステップである。** A で作成したスクリプトの実行と結果確認を行う。
> 
> **分割時の注意（SPLIT_REQUIRED の場合）：** A-exec は A（スクリプト作成）とは独立した Sub Issue として分割すること。A の Sub Issue に吸収・統合してはならない。Azure CLI 利用不可の場合でも、本ステップの「Azure CLI 利用不可の場合」セクションに記載された作業（構文チェック、work-status 記録、PR description 明記、README 記載）を独立 Sub Issue の成果物として含めること。

### 実行手順
1. `infra/azure/create-azure-api-resources-prep.sh` を実行する
   - **成功判定**: exit code 0、かつ Azure CLI バージョン/ログイン状態が出力されること
2. `infra/azure/create-azure-api-resources.sh` を実行する
   - **成功判定**: exit code 0、かつ全リソースの URL/Resource ID/リージョンが出力されること
3. `infra/azure/verify-azure-resources.sh` を実行する（AC-3 の事前検証）
   - **成功判定**: exit code 0、かつ全リソースの `provisioningState` が `Succeeded` であること
4. べき等性検証: ステップ 2 を **もう1回実行** し、exit code 0 で既存リソースが skip されることを確認する（`azure-cli-deploy-scripts` Skill §2.2 チェックリスト参照）

### 出力値の記録
- 取得した値（Function App URL / Resource ID / リージョン等）を `{WORK}api-azure-deploy-work-status.md` に追記する
- この値は後続の B（GitHub Actions）、C（サービスカタログ）、D（テスト）で参照する

### 失敗時の対応
- エラー内容を `{WORK}api-azure-deploy-work-status.md` に記録する
- リージョンフォールバックが必要な場合は `azure-region-policy` Skill §1 に従い、理由を `{WORK}api-azure-deploy-work-status.md` に記録する
- 修正→再実行を **最大3回** まで試行する（1回 = prep + create + verify の1サイクル）
- 3回失敗した場合は PR コメントで報告し、人間の判断を仰ぐ

### Azure CLI 利用不可の場合（デフォルト想定）
`azure-cli-deploy-scripts` Skill §3「Azure CLI 利用不可時フォールバック手順」に従う。
対象スクリプト:
- `infra/azure/create-azure-api-resources-prep.sh`
- `infra/azure/create-azure-api-resources.sh`
- `infra/azure/verify-azure-resources.sh`

## B) GitHub Actions（CI/CD）
> **共通仕様**: `github-actions-cicd` Skill に従う（§1 OIDC 認証・§2 `workflow_dispatch` トリガー・§2.3 PR description 手動実行案内）。

- 配置: `/.github/workflows/`
- Functions デプロイ: Azure Functions 用公式 Action を利用（既存 Function App へデプロイ）

## C) サービスカタログ更新
- `docs/service-catalog.md` の表に追記/更新
  - 列: サービスID / マイクロサービス名 / Azureサービス名 / 種類 / URL / AzureリソースID / リージョン
- **重複防止**：同一（サービスID + 種類）があれば更新、なければ追記
- URL / AzureリソースID / リージョンは A-exec で取得・記録した値を使用する。Azure CLI 未実行の場合は `TBD（要確認）` と記載する

## D) テスト（自動 + 手動UI）
- 保存先: `test/{サービスID}-{サービス名}/`
- 必須:
  1. 自動スモークテスト（HTTPでFunctions API呼び出し、主要レスポンス検証）
  2. 手動UI（最小の Web 画面：入力 → API呼び出し → 結果表示。静的 HTML で外部依存なし）
- リポジトリ既存のテスト方式があればそれに従う。無ければ「依存追加なし」で動く最小構成を選ぶ。

## E) 進捗ログ（必須・随時更新）
- `{WORK}api-azure-deploy-work-status.md` に追記（日本語）
  - 実施内容 / 作成・更新ファイル一覧 / 実行結果（成功/失敗・エラー要約）/ 次アクション
  - A-exec の実行結果（取得した値、リージョン情報）もここに記録する

## F) README 更新（必須）
- `infra/README.md` に以下を記載する：
  - スクリプトの実行手順・前提条件（Azure CLI バージョン、必要な権限等）
  - 期待される出力（各リソースの URL/ID）
  - Azure CLI 利用不可時の代替手順
  - 認証方式（OIDC / publish profile）の選択理由と設定手順

# 受け入れ条件（AC）の検証と完了判定（必須）

> **適用条件**: 実装モード（PROCEED 判定）の場合のみ実施する。分割モード（SPLIT_REQUIRED / Plan-Only）の場合は本セクションを **省略する**。

全成果物の実装完了後、最終品質レビュー（後述）の **前に** 以下の AC 検証を実施する。  
AC 検証の見積は DAG 合計に含めること（目安: 2〜3分）。

## AC チェックリスト

> **最重要 AC**: AC-3（Azure リソース存在確認）は本 Agent の最も重要な受け入れ条件である。AC-3 が ❌ の場合、他の AC が全て ✅ であっても **PR を完了とはみなさない**。

| #  | カテゴリ | 受け入れ条件 | 検証方法 | 判定 |
|----|---------|-------------|---------|------|
| AC-1 | A: スクリプト | 作成スクリプトが存在し構文エラーがない | `bash -n` + `shellcheck`（利用可能なら）で全 `.sh` ファイルを検証 | ✅/❌ |
| AC-2 | A: スクリプト | スクリプトがべき等である | A-exec ステップ4 の2回目実行で exit code 0 かつ skip 動作を確認済み | ✅/❌ |
| **AC-3** | **A-exec: 実行** | **🔴 スクリプト実行後に Microsoft Azure 上に作成すべきリソースが全て存在する（最重要）** | **`verify-azure-resources.sh` を実行し、全リソースの存在と `provisioningState: Succeeded` を確認（詳細は後述）** | **✅/❌** |
| AC-4 | A-exec: 実行 | 必要な値（URL/Resource ID/リージョン）が取得・記録されている | `work-status` に全値が記載されていること | ✅/❌ |
| AC-5 | B: CI/CD | GitHub Actions ワークフローが構文的に正しい | `.github/workflows/` の YAML を `actionlint`（利用可能なら）または `yamllint` で検証 | ✅/❌ |
| AC-6 | B: CI/CD | 認証方式（OIDC または代替）が設定されている | ワークフロー YAML 内に `azure/login` + OIDC 設定があること。代替の場合は `infra/README.md` に採用理由が記載されていること | ✅/❌ |
| AC-7 | C: カタログ | サービスカタログに対象サービスの行が存在する | `docs/service-catalog.md` に行が存在し、全7列が埋まっていること（`grep` / 目視） | ✅/❌ |
| AC-8 | C: カタログ | 重複行がない | 同一（サービスID + 種類）の行が複数存在しないこと（`sort | uniq -d` 等で確認） | ✅/❌ |
| AC-9 | D: テスト | 自動スモークテストが存在する | `test/{サービスID}-{サービス名}/` にテストファイルが存在し、HTTP リクエスト→レスポンス検証のロジックが含まれること | ✅/❌ |
| AC-10 | D: テスト | 手動UI が存在する | `test/{サービスID}-{サービス名}/` に HTML ファイルが存在し、入力フォーム・API呼び出し・結果表示の要素が含まれること | ✅/❌ |
| AC-11 | 安全性 | 秘密情報がハードコードされていない | 全成果物に対し `grep -rn -E "(password|secret|api[_-]?key|token|DefaultEndpointsProtocol|AccountKey)" --include="*.sh" --include="*.yml" --include="*.yaml" --include="*.html" --include="*.md"` を実行し、実際の秘密値が含まれていないこと（コメント・プレースホルダは許容） | ✅/❌ |
| AC-12 | E: ログ | 進捗ログが記録されている | `work-status` に全ステップの実施内容・結果・次アクションが記載されていること | ✅/❌ |
| AC-13 | Region | Region Policy に準拠している | 使用リージョンが Japan East（またはフォールバック先）であること。Japan East 以外の場合は理由が `work-status` に記録されていること（AC-3 の `location` フィールドで併せて確認） | ✅/❌ |

### AC-3 詳細検証手順（Azure リソース存在確認 — 最重要）

`infra/azure/verify-azure-resources.sh` の実行により、以下を確認する。

#### 確認対象リソース
スクリプトが作成する **全てのリソース** を対象とする。最低限以下を含む：

| リソース種類 | 検証コマンド例 |
|-------------|--------------|
| リソースグループ | `az group show --name {RG} --output json` |
| Storage Account | `az storage account show --name {SA} --resource-group {RG} --output json` |
| App Service Plan / Consumption Plan | `az appservice plan show --name {PLAN} --resource-group {RG} --output json` |
| Function App | `az functionapp show --name {APP} --resource-group {RG} --output json` |
| Application Insights（構成に含む場合） | `az monitor app-insights component show --app {AI} --resource-group {RG} --output json` |

※ `{RG}`, `{SA}`, `{PLAN}`, `{APP}`, `{AI}` 等のパラメータは `verify-azure-resources.sh` が引数または環境変数から取得する。

#### 検証基準
`azure-ac-verification` Skill §3.1〜§3.3 に従う（provisioningState 判定・非同期ポーリング・検証コマンドパターン）。

#### Azure CLI 利用不可の場合（デフォルト想定）
`azure-ac-verification` Skill §4 に従う。AC-3 の判定は **⏳（手動実行待ち）** とし、`ac-verification.md` に記録する。
`azure-cli-deploy-scripts` Skill §3 にも従う（構文チェック・work-status 記録・PR description テンプレート記載・README 記載）。

#### セキュリティ上の注意
`azure-ac-verification` Skill §3.4 に従う。

## 検証結果の記録

検証結果を `{WORK}ac-verification.md` に `azure-ac-verification` Skill §1 のテンプレートに従って保存する。

## 完了判定

`azure-ac-verification` Skill §2 の統一ステータス名（PASS / NEEDS-VERIFICATION / FAIL）に従う。

# Safety / Output Constraints
- 資格情報をハードコードしない。ログ/生成物に秘密情報を出さない。
- `ac-verification.md` のセキュリティルールは `azure-ac-verification` Skill §3.4 に従う。

# 最終品質レビュー（AGENTS.md §7準拠・3観点）
- **実施タイミング**: AC 検証（上記）の完了後に実施する。AC 検証が NEEDS-VERIFICATION の場合でも、検証済みの範囲でレビューを実施する。

## 3つの異なる観点（Azure Functions デプロイCI/CD 固有）
- **1回目：機能完全性・要件達成度**：Azure Functions デプロイが自動化され、GitHub Actions が正常に動作し、スモークテストが実行可能か。**AC-3（Azure リソース存在確認）が検証済みまたは検証手段が提供されているか**
- **2回目：ユーザー視点・実行可能性**：`infra/README.md` の手順が明確で、認証方式の選択が妥当で、Azure CLI 利用不可時の対応が明記されているか
- **3回目：保守性・セキュリティ・堅牢性**：秘密情報がハードコードされていなく、べき等性が保証され、再実行に耐えられるか。`verify-azure-resources.sh` のパラメータがハードコードされていないか

## 出力方法
レビュー記録は `{WORK}` に保存（§4.1準拠）。PR本文にも記載。最終版のみ成果物出力。

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D15-非機能-運用-監視-DR-仕様書.md` — 非機能・運用・監視・DR
- `knowledge/D19-ソフトウェアアーキテクチャ-ADR-パック.md` — ソフトウェアアーキテクチャ・ADR
- `knowledge/D20-セキュア設計-実装ガードレール.md` — セキュア設計・実装ガードレール
- `knowledge/D21-CI-CD-ビルド-リリース-供給網管理仕様書.md` — CI/CD・ビルド・リリース
