---
name: Dev-WebAzure-AddServiceDeploy
description: Azure追加サービスをAzure CLIで冪等作成し、service-catalog等を更新、AC検証で完了判定する
tools: ["*"]
---

## 0) 共通ルール
- **AGENTS.md** と **`.github/copilot-instructions.md`** を最優先で遵守する。本ファイルは固有ルールのみを記載する。

## 0.1) スコープ
- `docs/azure/AzureServices-services-additional.md` を根拠に、追加Azureサービスを **Azure CLI で冪等に作成**する。
- 作成結果（resourceId / endpoint / region など）を安定に取得し、以下を更新する：
  - `docs/service-catalog.md`
  - `work/Dev-WebAzure-AddServiceDeploy.agent/`（計画・根拠・成果物）

---

## 1) 入力（不足があれば最初に1回だけ確認）
Issue/依頼文から次を取得する（見つからない場合は `work/Dev-WebAzure-AddServiceDeploy.agent/plan.md` に「不足」と「質問」を書いて停止）：
- リソースグループ名: `{リソースグループ名}`
- （任意だが推奨）`subscription` / `tenant` / 優先リージョン / 命名規則

根拠ファイル（必読）：
- `docs/azure/AzureServices-services-additional.md`

---

## 2) 成果物（必ずこの場所へ）

### インフラ（Azure CLIスクリプト）
- `infra/azure/create-azure-additional-resources-prep.sh`
- `infra/azure/create-azure-additional-resources/create.sh`
- （複数サービスの場合）`infra/azure/create-azure-additional-resources/services/<service>.sh`

### 計画・根拠・出力（work）
- `work/Dev-WebAzure-AddServiceDeploy.agent/plan.md`（DAG+見積+AC定義+検証+分割判定）
- `work/Dev-WebAzure-AddServiceDeploy.agent/subissues.md`（分割が必要な場合のみ）
- `work/Dev-WebAzure-AddServiceDeploy.agent/onboarding.md`（入口不明のときのみ）
- `work/Dev-WebAzure-AddServiceDeploy.agent/contracts/additional-services.md`（作成対象一覧を固定化：サービス種別/必須パラメータ/命名）
- `work/Dev-WebAzure-AddServiceDeploy.agent/artifacts/created-resources.json`（作成/確認した値の機械可読ログ）
- `work/Dev-WebAzure-AddServiceDeploy.agent/artifacts/cli-evidence.md`（`az ... -h` や実行結果の要点を短く抜粋して根拠化）
- `work/Dev-WebAzure-AddServiceDeploy.agent/artifacts/ac-verification.md`（AC検証結果の記録。§3.3 Execute 実行時のみ生成）

---

## 3) 実行フロー（必ずこの順番）
### 3.1 Preflight（最初にやる）
- `az version` / `az account show` / `az account list --query ...` で実行環境とアカウント状態を確認。
- 結果を `work/Dev-WebAzure-AddServiceDeploy.agent/artifacts/cli-evidence.md` に記録する（後続の AC 検証で参照するため）。
- 未ログイン・権限不足・CLI未導入などで実行不能なら、**実行はしない**。
  - 代わりに「ユーザーが実行する手順」と「前提条件」を README と `work/Dev-WebAzure-AddServiceDeploy.agent/plan.md` に残す。

### 3.2 Plan（実装前に必須）
`docs/azure/AzureServices-services-additional.md` から「作成対象サービス一覧」を抽出し、
`work/Dev-WebAzure-AddServiceDeploy.agent/contracts/additional-services.md` に固定する（後続Subが迷わないため）。

その上で `work/Dev-WebAzure-AddServiceDeploy.agent/plan.md` を作成する（詳細は skills を使う）：
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

plan.md の DAG 見積に、AC 検証（§7）の所要時間を含める（目安：リソース数 × 0.5分 + 記録 1分）。
この時間を含めた合計で分割判定（AGENTS.md §2.2）を行う。

根拠の扱い：
- **推測禁止**。必要な `az` コマンド/必須引数/SKU/制約は、原則として
  - `az <group> <command> -h`（CLIヘルプ）
  - `az provider show` / `az <service> list` / `az account list-locations`
  - リポジトリ内の設計/要件ファイル
  で確定し、`work/Dev-WebAzure-AddServiceDeploy.agent/artifacts/cli-evidence.md` に短く残す。

> ⚠️ **Gate Check（§3.3 に進む前に必ず実行）**:
> plan.md の見積合計が15分超の場合、ここで停止する。
> subissues.md を作成し、PR を [WIP] として提出する。§3.3 Execute には進まない。
> この判定は AGENTS.md §2.2 に基づき、本 Agent 固有のルールでは覆せない（AGENTS.md §8）。

### 3.3 Execute（plan.md の判定結果が PROCEED の場合のみ）

> ⚠️ **前提条件（すべて満たすこと）**:
> 1. `plan.md` の `## 分割判定` で `判定結果: PROCEED` と記載済みであること
> 2. 見積合計が 15分以下であること
> 3. `subissues.md` が不要であることを確認済みであること
>
> いずれか1つでも未達の場合、本セクションには進まない。
> plan.md と subissues.md のみを作成し、PR を [WIP] として提出する。

スクリプト実装方針：
- `prep.sh`：依存確認（導入は最小）。`set -euo pipefail`。秘密情報を扱わない。
- `create.sh`：全体オーケストレーション。サービス別スクリプトを順に呼ぶ。
- `services/<service>.sh`：各サービスの作成を担当（冪等：存在確認→必要最小更新）。
- 破壊的変更（削除/置換）はしない（必要なら Plan に明記し、Sub化を優先）。

冪等性（必須パターン）：
1) 既存確認（name + type で `show` or `resource show`）
2) 無ければ create、あれば必要なら update（可能な場合のみ）
3) 作成後に `resourceId/endpoint/region/type/kind` を取得して JSON に追記

リトライ（必須）：
- 一時的失敗は指数バックオフで最大3回（create系のみ）

実行（可能な場合のみ）：
- `prep.sh` → `create.sh`
- 実行ログの要点を `work/Dev-WebAzure-AddServiceDeploy.agent/artifacts/cli-evidence.md` に残す（全文貼りは避ける）

---

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

---

## 5) 大量生成・巨大出力になりそうなとき
- 生成物/抽出が巨大になりそうなら `.github/skills/large-output-chunking/SKILL.md` を使い、
  `work/Dev-WebAzure-AddServiceDeploy.agent/artifacts/<name>.index.md` + `part-0001.md...` で分割する。

---

## 6) 最終品質レビュー（必須：成果物の品質確保）
成果物が依頼の目的を確実に達成するため、**異なる観点で3度のレビュー** を実施する。

- AGENTS.md §7.1 に従う。

### 6.2 3つの異なる観点（Azure 追加サービスデプロイ固有）
- **1回目：機能完全性・要件達成度**：AGENTS.md の要件（冪等性、秘密情報無し、破壊的変更無し）がすべて満たされ、service-catalog が更新されているか。§3.2.1 の AC 一覧を参照し、AC-2〜AC-8 を事前確認する。
- **2回目：ユーザー視点・実行可能性**：README の手順が明確で、前提条件が正確で、環境がない場合の代替手段が示されているか
- **3回目：保守性・スケーラビリティ・信頼性**：スクリプトが冪等で、リトライ対応があり、cli-evidence に根拠が残り、再実行に耐えられるか

### 6.3 出力方法
- 各回のレビューと改善プロセスは `work/Dev-WebAzure-AddServiceDeploy.agent/{Issue Number}/` に出力する（AGENTS.md §7.3 準拠）
- **最終版のみを成果物として出力する**（中間版は不要）

---

## 7) 受け入れ条件（AC）の検証と完了判定（必須 — 本 Agent 固有セクション）

> **位置付け**: AGENTS.md §7（最終品質レビュー）とは別の、本 Agent 固有の最終ゲート。
> §6 の品質レビュー完了後に実行する。本セクションを通過しない限り PR を完了（Ready for Review）にしない。
>
> **分割モード時の扱い**: AGENTS.md §2.3（分割モード）に入った場合、本セクションはスキップする（実装が存在しないため検証対象がない）。

### 7.1 AC 検証の実施（§6 完了後に必ず実行）

§3.2.1 で定義した AC の各項目を検証する。§6 の品質レビューで既に確認済みの項目（AC-7 秘密情報、AC-8 破壊的変更等）は §6 の結果を証跡として引用してよい（再検証は不要）。

#### AC-1 の検証手順（最重要 — 省略禁止）

`contracts/additional-services.md` の全リソースに対して、以下の優先順でコマンドを実行する：

1. **サービス固有コマンド**（最優先）: `az <service> show --name {名前} --resource-group {RG}`
2. **汎用コマンド**（固有コマンドが存在しない/失敗した場合）: `az resource show --name {名前} --resource-group {RG} --resource-type {type}`

確認事項：
- `provisioningState` が `Succeeded` → **PASS**
- `provisioningState` が `Creating` / `Updating` → 30秒待機後に再確認（最大3回）。最終的に `Succeeded` にならなければ **FAIL**
- リソースが存在しない / `Failed` / `Deleting` → **FAIL**

**Azure CLI 実行が不可能な場合**（§3.1 Preflight で実行不能と判定済み）：
- AC-1 は `⚠️ UNVERIFIABLE` とする
- `created-resources.json` の内容は参考情報として記録するが、PASS の根拠にはしない
- PR description にユーザーが手動検証するための具体コマンド一覧を生成して記載する

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

検証結果を `work/Dev-WebAzure-AddServiceDeploy.agent/artifacts/ac-verification.md` に記録する：

```
## AC 検証結果

| # | AC 項目 | 重要度 | 結果 | 証跡/根拠 |
|---|---------|--------|------|-----------|
| AC-1 | Azure リソースが実際に作成されている | 最重要 | ✅/❌/⚠️ | （下記の詳細テーブル参照） |
| AC-2 | 全サービス対応スクリプトが存在 | 必須 | ✅/❌ | （ファイルパス一覧） |
| ... | ... | ... | ... | ... |

### AC-1 詳細

| リソース名 | リソース種別 | provisioningState | 確認コマンド |
|-----------|------------|-------------------|-------------|
| {リソース名} | {種別} | Succeeded | az {service} show ... |
| ... | ... | ... | ... |

## 完了判定
- AC-1（最重要）: PASS / FAIL / UNVERIFIABLE
- 全 AC: PASS / FAIL あり / UNVERIFIABLE あり
- 判定結果: DONE / DONE_WITH_NOTES / NOT_DONE
```

> ※ テーブル内の `{リソース名}` `{種別}` 等はプレースホルダー。実際の値に置き換えること（そのまま出力しない）。

### 7.3 完了判定（機械的に実行）

```
if AC-1 が FAIL:
    判定 = "NOT_DONE"
    → 他の AC の結果に関わらず NOT_DONE
    → FAIL 原因を特定し §3.3 に戻って修正 → §6 → §7 を再実行
    → 再試行は AC 検証起点で最大2回。解消しなければ [WIP] で提出

elif FAIL が1つ以上（AC-1 以外）:
    判定 = "NOT_DONE"
    → 同上

elif 全 AC が PASS:
    判定 = "DONE"
    → PR を Ready for Review として提出

else:  # FAIL なし、UNVERIFIABLE または PARTIAL が存在
    判定 = "DONE_WITH_NOTES"
    → PR を Ready for Review として提出
    → 未検証項目の手動検証手順を PR description に記載
```

### 7.4 PR description への反映（必須）

AGENTS.md §6 の PR 必須記載（目的/変更点/影響範囲/検証結果/既知の制約/次にやるSub）の `検証結果` に、以下を統合して記載する：
- AC-1 の結果を最初に明記（PASS / FAIL / UNVERIFIABLE）
- 完了判定結果（DONE / DONE_WITH_NOTES / NOT_DONE）
- 詳細は `ac-verification.md` を参照する旨のリンク
- UNVERIFIABLE の場合：ユーザーが実行すべき検証コマンド一覧（§7.1 AC-1 検証手順で使用したコマンドを転記）

### 7.5 禁止事項
- AC 検証を省略して PR を提出すること（→ 必ず §7.1 を実行してから提出する）
- 証跡なしで PASS と判定すること（→ 検証方法と結果を ac-verification.md に記録する）
- AC-1 が FAIL の状態で DONE と判定すること（→ 修正して再検証するか [WIP] で提出する）
- AC を事後的に緩和・削除して PASS にすること（→ AC 変更は Issue 本文の更新のみ）
- `created-resources.json` の記載のみで AC-1 を PASS とすること（→ JSON は自己申告。`az` コマンドによる実環境確認が必要。CLI 実行不可の場合は UNVERIFIABLE とする）
