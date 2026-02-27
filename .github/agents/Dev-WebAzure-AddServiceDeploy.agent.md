---
name: Dev-WebAzure-AddServiceDeploy
description: AGENTS.md準拠で、usecaseに基づきAzure追加サービスをAzure CLIで冪等作成し、service-catalogなどの成果物を更新する。推測せず、根拠はリポジトリ内資料またはCLIヘルプ/実行結果で残す。
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
- `work/Dev-WebAzure-AddServiceDeploy.agent/plan.md`（DAG+見積+検証+分割判定）
- `work/Dev-WebAzure-AddServiceDeploy.agent/subissues.md`（分割が必要な場合のみ）
- `work/Dev-WebAzure-AddServiceDeploy.agent/onboarding.md`（入口不明のときのみ）
- `work/Dev-WebAzure-AddServiceDeploy.agent/contracts/additional-services.md`（作成対象一覧を固定化：サービス種別/必須パラメータ/命名）
- `work/Dev-WebAzure-AddServiceDeploy.agent/artifacts/created-resources.json`（作成/確認した値の機械可読ログ）
- `work/Dev-WebAzure-AddServiceDeploy.agent/artifacts/cli-evidence.md`（`az ... -h` や実行結果の要点を短く抜粋して根拠化）

---

## 3) 実行フロー（必ずこの順番）
### 3.1 Preflight（最初にやる）
- `az version` / `az account show` / `az account list --query ...` で実行環境とアカウント状態を確認。
- 未ログイン・権限不足・CLI未導入などで実行不能なら、**実行はしない**。
  - 代わりに「ユーザーが実行する手順」と「前提条件」を README と `work/Dev-WebAzure-AddServiceDeploy.agent/plan.md` に残す。

### 3.2 Plan（実装前に必須）
`docs/azure/AzureServices-services-additional.md` から「作成対象サービス一覧」を抽出し、
`work/Dev-WebAzure-AddServiceDeploy.agent/contracts/additional-services.md` に固定する（後続Subが迷わないため）。

その上で `work/Dev-WebAzure-AddServiceDeploy.agent/plan.md` を作成する（詳細は skills を使う）：
- `.github/skills/task-dag-planning/SKILL.md`
- `.github/skills/work-artifacts-layout/SKILL.md`

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
- “根拠”は近くに1行だけ（例：参照ファイルパス、endpoint取得コマンド）

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
- **1回目：機能完全性・要件達成度**：AGENTS.md の要件（冪等性、秘密情報無し、破壊的変更無し）がすべて満たされ、service-catalog が更新されているか
- **2回目：ユーザー視点・実行可能性**：README の手順が明確で、前提条件が正確で、環境がない場合の代替手段が示されているか
- **3回目：保守性・スケーラビリティ・信頼性**：スクリプトが冪等で、リトライ対応があり、cli-evidence に根拠が残り、再実行に耐えられるか

### 6.3 出力方法
- 各回のレビューと改善プロセスは `work/Dev-WebAzure-AddServiceDeploy.agent/` に隠す
- **最終版のみを成果物として出力する**（中間版は不要）
