---
name: Dev-Microservice-Azure-AddServiceDeploy
description: Azure追加サービスをAzure CLIで冪等作成し、service-catalog等を更新、AC検証で完了判定する
tools: ["*"]
---
> **WORK**: `work/Dev-Microservice-Azure-AddServiceDeploy/Issue-<識別子>/`

## 0) 共通ルール
- **AGENTS.md** と **`.github/copilot-instructions.md`** を最優先で遵守する。本ファイルは固有ルールのみを記載する。

## Skills 参照
- **`azure-cli-deploy-scripts`**: Azure CLI スクリプトの共通仕様（prep/create/verify 3点セット・冪等性パターン・CLI 利用不可時フォールバック）を参照する。
- **`azure-ac-verification`**: AC 検証フレームワークの共通仕様（§1 `ac-verification.md` テンプレート・§2 PASS/NEEDS-VERIFICATION/FAIL 完了判定基準・§3 Azure リソース存在確認パターン・§4 Azure CLI 利用不可時フォールバック）を参照する。

- `harness-verification-loop`：コード変更の5段階検証パイプライン（AGENTS.md §10.1）
- `harness-safety-guard`：破壊的操作の事前検知（AGENTS.md §10.2）
- `harness-error-recovery`：エラー発生時の3要素出力（AGENTS.md §10.4）
## 0.1) スコープ
- `docs/azure/AzureServices-services-additional.md` を根拠に、追加Azureサービスを **Azure CLI で冪等に作成**する。
- 作成結果（resourceId / endpoint / region など）を安定に取得し、以下を更新する：
  - `docs/service-catalog.md`
  - `{WORK}`（計画・根拠・成果物）

## 1) 入力（不足があれば最初に1回だけ確認）
Issue/依頼文から次を取得する（見つからない場合は `{WORK}plan.md` に「不足」と「質問」を書いて停止）：
- リソースグループ名: `{リソースグループ名}`
- （任意だが推奨）`subscription` / `tenant` / 優先リージョン / 命名規則

根拠ファイル（必読）：
- `docs/azure/AzureServices-services-additional.md`
- `docs/app-list.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D10-API-Event-File-連携契約パック.md` — API/イベント/ファイル連携契約
- `knowledge/D15-非機能-運用-監視-DR-仕様書.md` — 非機能・運用・監視・DR
- `knowledge/D20-セキュア設計-実装ガードレール.md` — セキュア設計・実装ガードレール

## APP-ID スコープ
- Issue body / `<!-- app-id: XXX -->` から APP-ID 取得 → `docs/app-list.md` で紐づく追加サービス特定（共有含む）
- APP-ID未指定 or `docs/app-list.md` 不在 → 全サービス対象（後方互換）

## 2) 成果物（必ずこの場所へ）

### インフラ（Azure CLIスクリプト）
- `infra/azure/create-azure-additional-resources-prep.sh`
- `infra/azure/create-azure-additional-resources/create.sh`
- （複数サービスの場合）`infra/azure/create-azure-additional-resources/services/<service>.sh`

### 計画・根拠・出力（work）
- `{WORK}plan.md`（DAG+見積+AC定義+検証+分割判定）
- `{WORK}subissues.md`（分割が必要な場合のみ）
- `{WORK}onboarding.md`（入口不明のときのみ）
- `{WORK}contracts/additional-services.md`（作成対象一覧を固定化：サービス種別/必須パラメータ/命名）
- `{WORK}artifacts/created-resources.json`（作成/確認した値の機械可読ログ）
- `{WORK}artifacts/cli-evidence.md`（`az ... -h` や実行結果の要点を短く抜粋して根拠化）
- `{WORK}artifacts/ac-verification.md`（AC検証結果の記録。§3.3 Execute 実行時のみ生成）

## 3) 実行フロー（必ずこの順番）
### 3.1 Preflight（最初にやる）
- `az version` / `az account show` / `az account list --query ...` で実行環境とアカウント状態を確認。
- 結果を `{WORK}artifacts/cli-evidence.md` に記録する（後続の AC 検証で参照するため）。
- 対象リソースグループが存在するか確認し、存在しない場合は冪等に作成する（`azure-cli-deploy-scripts` Skill §1.2 および `azure-region-policy` Skill §1 に準拠）。
- 未ログイン・権限不足・CLI未導入などで実行不能なら、**実行はしない**。
  - 代わりに「ユーザーが実行する手順」と「前提条件」を README と `{WORK}plan.md` に残す。

### 3.2 Plan（実装前に必須）
`docs/azure/AzureServices-services-additional.md` から「作成対象サービス一覧」を抽出し、
`{WORK}contracts/additional-services.md` に固定する（後続Subが迷わないため）。

その上で `{WORK}plan.md` を作成する（詳細は skills を使う）：
- `.github/skills/task-dag-planning/SKILL.md`
- `.github/skills/work-artifacts-layout/SKILL.md`

#### 3.2.1 受け入れ条件（AC）の定義（plan.md 内に必須）

plan.md に `## 受け入れ条件（AC）` セクションを必ず含める。
Issue/依頼文から AC を抽出する。Issue に AC が明示されていない場合は以下のデフォルト AC を適用する。
Issue に AC が部分的に記載されている場合は、Issue の AC を優先し、不足分のみデフォルトから補完する（重複時は Issue 側を採用）。

**デフォルト AC（本 Agent 固有・番号順が優先度順）：**

| # | AC 項目 | 重要度 |
|---|---------|--------|
| **AC-1** | **スクリプト実行後に、Microsoft Azure 上に作成すべき全リソースが実際に作成されていること**（`az resource show` 等で `provisioningState: Succeeded` を確認） | **最重要** |
| AC-2 | `docs/azure/AzureServices-services-additional.md` に記載された全サービスに対応するスクリプトが存在する（1スクリプトが複数サービスを扱う場合も可） | 必須 |
| AC-3 | 各スクリプトが冪等パターン（存在確認→作成/更新→結果取得）を実装している | 必須 |
| AC-4 | `created-resources.json` に全作成リソースの情報が記録されている（`resourceId` / `region` は必須。`endpoint` はサービスが提供する場合のみ） | 必須 |
| AC-5 | `docs/service-catalog.md` が更新され、重複行がない | 必須 |
| AC-6 | README.md に実行手順と前提条件が記載されている | 必須 |
| AC-7 | 秘密情報（鍵・トークン・パスワード等）が成果物に含まれていない | 必須 |
| AC-8 | 破壊的変更（削除/置換）が行われていない | 必須 |

AC 定義後の変更は禁止（追加・修正は Issue 本文の更新を通じてのみ許可）。

#### 3.2.2 見積に AC 検証時間を含める

AC 検証時間の見積目安：
（目安：リソース数 × 0.5分 + 記録 1分）

根拠の扱い：
- **推測禁止**。必要な `az` コマンド/必須引数/SKU/制約は、原則として
  - `az <group> <command> -h`（CLIヘルプ）
  - `az provider show` / `az <service> list` / `az account list-locations`
  - リポジトリ内の設計/要件ファイル
  で確定し、`{WORK}artifacts/cli-evidence.md` に短く残す。

### 3.3 Execute（plan.md の判定結果が PROCEED の場合のみ）

> ⚠️ **前提条件（すべて満たすこと）**:
> 1. `plan.md` の `## 分割判定` で `判定結果: PROCEED` と記載済みであること
> 2. 見積合計が 15分以下であること
> 3. `subissues.md` が不要であることを確認済みであること
>
> いずれか1つでも未達の場合、本セクションには進まない。
> plan.md と subissues.md のみを作成し、PR を [WIP] として提出する。

スクリプト実装方針（`azure-cli-deploy-scripts` Skill §1「3点セットテンプレート」および §2「冪等性パターン」に準拠）：
- `prep.sh`：依存確認（導入は最小）。秘密情報を扱わない。
- `create.sh`：全体オーケストレーション。サービス別スクリプトを順に呼ぶ。
- `services/<service>.sh`：各サービスの作成を担当（Skill §2 冪等性パターン準拠）。
- 破壊的変更（削除/置換）はしない（必要なら Plan に明記し、Sub化を優先）。

リトライ（必須）：
- 一時的失敗は指数バックオフで最大3回（create系のみ）

実行（可能な場合のみ）：
- `prep.sh` → `create.sh`
- 実行ログの要点を `{WORK}artifacts/cli-evidence.md` に残す（全文貼りは避ける）

## 4) ドキュメント更新（冪等・重複禁止）
### 4.1 service-catalog.md
`docs/service-catalog.md` の表を更新する（重複行は作らない）。
- 列（固定）：サービスID | サービス名 | Azureのサービス名 | 機能名 | 機能の種類 | AzureサービスのURL | リージョン
- "根拠"は近くに1行だけ（例：参照ファイルパス、endpoint取得コマンド）

### 4.2 README.md
最小追記だけ：
- 追加サービスの目的（1〜3行）
- 実行手順（prep → create、前提条件）
- 注意（資格情報は出力しない / リージョン差 / 再実行）

## 5) 大量生成・巨大出力になりそうなとき
- 生成物/抽出が巨大になりそうなら `.github/skills/large-output-chunking/SKILL.md` を使い、
  `{WORK}artifacts/<name>.index.md` + `part-0001.md...` で分割する。

## 6) 最終品質レビュー（AGENTS.md §7準拠・3観点）

### 6.2 3つの異なる観点（Azure 追加サービスデプロイ固有）
- **1回目：機能完全性・要件達成度**：AGENTS.md の要件（冪等性、秘密情報無し、破壊的変更無し）がすべて満たされ、service-catalog が更新されているか。§3.2.1 の AC 一覧を参照し、AC-2〜AC-8 を事前確認する。
- **2回目：ユーザー視点・実行可能性**：README の手順が明確で、前提条件が正確で、環境がない場合の代替手段が示されているか
- **3回目：保守性・スケーラビリティ・信頼性**：スクリプトが冪等で、リトライ対応があり、cli-evidence に根拠が残り、再実行に耐えられるか

### 6.3 出力方法
レビュー記録は `{WORK}` に保存（§4.1準拠）。PR本文にも記載。最終版のみ成果物出力。

## 7) 受け入れ条件（AC）の検証と完了判定（必須 — 本 Agent 固有セクション）

> **位置付け**: AGENTS.md §7（最終品質レビュー）とは別の、本 Agent 固有の最終ゲート。
> §6 の品質レビュー完了後に実行する。本セクションを通過しない限り PR を完了（Ready for Review）にしない。
>
> **分割モード時の扱い**: AGENTS.md §2.3（分割モード）に入った場合、本セクションはスキップする（実装が存在しないため検証対象がない）。

### 7.1 AC 検証の実施（§6 完了後に必ず実行）

§3.2.1 で定義した AC の各項目を検証する。§6 の品質レビューで既に確認済みの項目（AC-7 秘密情報、AC-8 破壊的変更等）は §6 の結果を証跡として引用してよい（再検証は不要）。

#### AC-1 の検証手順（最重要 — 省略禁止）

`contracts/additional-services.md` の全リソースに対して、`azure-ac-verification` Skill §3.2 の検証コマンドパターンに従いコマンドを実行する。

`provisioningState` の判定は `azure-ac-verification` Skill §3.3 に従う。

**Azure CLI 実行が不可能な場合**（§3.1 Preflight で実行不能と判定済み）：
`azure-ac-verification` Skill §4 に従う。AC-1 は `⏳（手動実行待ち）` とし、PR description にユーザーが手動検証するための具体コマンド一覧を記載する。

#### AC-2〜AC-8 の検証

| AC | 検証方法 |
|----|----------|
| AC-2 | `contracts/additional-services.md` の各サービスに対応するスクリプトファイルの存在確認 |
| AC-3 | §6 レビュー1回目の結果を引用（冪等パターンの実装確認） |
| AC-4 | `created-resources.json` の JSON 構造を読み取り、全リソースに `resourceId` / `region` があることを確認 |
| AC-5 | `docs/service-catalog.md` を読み取り、追加行の存在と重複なしを確認 |
| AC-6 | README.md に実行手順セクションが存在することを確認 |
| AC-7 | §6 レビュー1回目の結果を引用。追加で成果物全体に対し秘密情報パターン（`password`, `secret`, `key=`, Bearer トークン等）の grep を実施 |
| AC-8 | §6 レビュー1回目の結果を引用（破壊的変更がないことの確認） |

### 7.2 証跡の記録

検証結果を `{WORK}ac-verification.md` に `azure-ac-verification` Skill §1 のテンプレートに従って記録する。AC-1 詳細（リソース名・種別・provisioningState・確認コマンド）も含めること。

### 7.3 完了判定（機械的に実行）

`azure-ac-verification` Skill §2 の統一ステータス名に従う。本 Agent 固有の対応付け：
- **PASS** = 全 AC が PASS → PR を Ready for Review として提出
- **NEEDS-VERIFICATION** = FAIL なし、AC-1 が ⏳（手動実行待ち）→ PR を Ready for Review として提出し、未検証項目の手動検証手順を PR description に記載
- **FAIL** = いずれかの AC が FAIL → 修正して再検証（AC 検証起点で最大2回）。解消しなければ [WIP] で提出

### 7.4 PR description への反映（必須）

AGENTS.md §6 の PR 必須記載（目的/変更点/影響範囲/検証結果/既知の制約/次にやるSub）の `検証結果` に、以下を統合して記載する：
- AC-1 の結果を最初に明記（PASS / FAIL / ⏳（手動実行待ち））
- 完了判定結果（PASS / NEEDS-VERIFICATION / FAIL）
- 詳細は `ac-verification.md` を参照する旨のリンク
- ⏳（手動実行待ち）の場合：ユーザーが実行すべき検証コマンド一覧（§7.1 AC-1 検証手順で使用したコマンドを転記）

### 7.5 禁止事項
- AC 検証を省略して PR を提出すること（→ 必ず §7.1 を実行してから提出する）
- 証跡なしで PASS と判定すること（→ 検証方法と結果を ac-verification.md に記録する）
- AC-1 が FAIL の状態で DONE と判定すること（→ 修正して再検証するか [WIP] で提出する）
- AC を事後的に緩和・削除して PASS にすること（→ AC 変更は Issue 本文の更新のみ）
- `created-resources.json` の記載のみで AC-1 を PASS とすること（→ JSON は自己申告。`az` コマンドによる実環境確認が必要。CLI 実行不可の場合は UNVERIFIABLE とする）
