---
name: Dev-Microservice-Azure-AgenticRetrievalDeploy
description: Agentic Retrieval Azure 実装設計を入力に、Azure CLI / az rest で冪等デプロイする実行骨子と受け入れ条件を定義する（IaC スクリプト本体は実行時生成）。
tools: ["*"]
metadata:
  version: "1.0.0"

---
<!-- markdownlint-disable MD013 MD022 MD031 MD032 MD041 MD058 MD060 -->
> **WORK**: `work/Dev-Microservice-Azure-AgenticRetrievalDeploy/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。
- 本 PR では IaC スクリプト本体を固定生成しない。Agent 実行時に
  `azure-prepare` / `azure-deploy` を使って生成する。

## Agent 固有の Skills 依存
- `.github/skills/agent-common-preamble/SKILL.md`
- `.github/skills/task-dag-planning/SKILL.md`
- `.github/skills/work-artifacts-layout/SKILL.md`
- `.github/skills/app-scope-resolution/SKILL.md`
- `.github/skills/output/large-output-chunking/SKILL.md`
- `.github/skills/harness/harness-verification-loop/SKILL.md`
- `.github/skills/azure-skills/azure-ai/SKILL.md`
- `.github/skills/azure-skills/microsoft-foundry/SKILL.md`
- `.github/skills/azure-skills/microsoft-foundry/references/standard-agent-setup.md`
- `.github/skills/azure-skills/microsoft-foundry/project/connections.md`
- `.github/skills/azure-skills/microsoft-foundry/rbac/rbac.md`
- `.github/skills/azure-skills/microsoft-foundry/foundry-agent/create/references/tool-mcp.md`
- `.github/skills/azure-skills/microsoft-foundry/foundry-agent/create/references/tool-azure-ai-search.md`
- `.github/skills/azure-skills/microsoft-foundry/models/`
- `.github/skills/azure-skills/microsoft-foundry/quota/`
- `.github/skills/azure-skills/microsoft-foundry/resource/`
- `.github/skills/azure-skills/azure-deploy/SKILL.md`
- `.github/skills/azure-skills/azure-prepare/SKILL.md`
- `.github/skills/azure-skills/azure-validate/SKILL.md`
- `.github/skills/azure-skills/azure-resource-lookup/SKILL.md`
- `.github/skills/azure-skills/azure-rbac/SKILL.md`
- `.github/skills/azure-skills/azure-diagnostics/SKILL.md`

## 1) スコープ
4-A の `docs/azure/agentic-retrieval/{serviceId}-design.md` を入力に、Azure CLI / `az rest` で Agentic Retrieval リソースを冪等作成するための実行骨子を定義する。

## 2) 入力（必読）
- リソースグループ名
- `docs/azure/agentic-retrieval/{serviceId}-design.md`
- ワークフロー入力フラグ（Q1〜Q6 全て）
- `docs/catalog/app-catalog.md`

## APP-ID スコープ → Skill `app-scope-resolution` を参照

## 3) 出力（必須）
### インフラ（Agent 実行時に生成）
- `infra/azure/create-azure-agentic-retrieval/prep.sh`
- `infra/azure/create-azure-agentic-retrieval/create.sh`
- `infra/azure/create-azure-agentic-retrieval/services/{serviceId}.sh`

### 計画・根拠・出力（work）
- `{WORK}plan.md`（DAG + 見積 + AC + 検証 + 分割判定）
- `{WORK}contracts/agentic-retrieval-resources.md`
- `{WORK}artifacts/created-resources.json`
- `{WORK}artifacts/cli-evidence.md`
- `{WORK}artifacts/ac-verification.md`（Execute 時のみ）

## 4) 実行フロー

### 4.1 Preflight
- `az version` / `az account show` / `az account list-locations` を確認
- 対象 RG の存在確認。不在時は冪等作成
  （`azure-prepare` / `azure-resource-lookup` の実在 Skill を参照）
- 結果を `cli-evidence.md` に記録
- 実行不可時は Execute せず、手動手順を `infra/README.md` と `{WORK}plan.md` に残す

### 4.2 Plan

- `task-dag-planning` に従い `{WORK}plan.md` を作成
- plan.md の先頭に、以下メタデータをこの順で必須記載:
  ```html
  <!-- task_scope: single|multi -->
  <!-- context_size: small|medium|large -->
  <!-- split_decision: PROCEED or SPLIT_REQUIRED -->
  <!-- subissues_count: N -->
  <!-- implementation_files: true -->
  ```
- `bash .github/scripts/bash/validate-plan.sh --path {WORK}plan.md` で PASS を確認

#### 4.2.1 デフォルト受け入れ条件（AC）
| # | AC 項目 | 重要度 |
| --- | --- | --- |
| AC4B-1 | スクリプト実行後、Azure 上に作成すべき全 Agentic Retrieval リソースが作成され `provisioningState: Succeeded` | 必須 |
| AC4B-2 | `{serviceId}-design.md` 記載の全リソース（Search, Index, Data Source, Skillset, Indexer, Knowledge Source/Base, [Foundry, Model, MCP 接続]）に対応するスクリプトが存在 | 必須 |
| AC4B-3 | 各スクリプトが冪等パターン（存在確認 → 作成/更新 → 結果取得） | 必須 |
| AC4B-4 | `created-resources.json` に全作成リソースの `resourceId` / `region`（必須）と `endpoint`（提供される場合） | 必須 |
| AC4B-5 | `docs/catalog/service-catalog-matrix.md` が更新され、重複行がない | 必須 |
| AC4B-6 | `infra/README.md` に実行手順と前提条件が記載 | 必須 |
| AC4B-7 | 秘密情報（鍵/トークン/パスワード）が成果物・スクリプトログに含まれない | 必須 |
| AC4B-8 | 破壊的変更（削除/置換）が行われていない | 必須 |
| AC4B-9 | Q3=`しない` のとき Foundry 関連リソースを作成しない | 必須 |
| AC4B-10 | prep.sh で Search SKU の Semantic Ranker 対応をチェックし、非対応時は停止 | 必須 |
| AC4B-11 | Q6 フォールバック方針に従って Global / Standard SKU を選択し、選択結果と理由を `cli-evidence.md` に記録 | 必須 |
| AC4B-12 | MS Learn MCP 障害時は `要確認（要：Microsoft Learn 確認）` を記録し、停止せず暫定値（直近 `cli-evidence` があれば）で継続 | 必須 |
| AC4B-13 | SKU / モデル名 / API バージョンをスクリプトにハードコードせず、MS Learn MCP 取得値を変数として利用 | 必須 |

AC 定義後の変更は禁止（追加・修正は Issue 本文更新時のみ）。

### 4.3 Execute（PROCEED 判定時のみ）
`azure-deploy` / `azure-validate` の実在 Skill を参照し、
以下順序で実行する。
1. Search サービス作成（SKU は MS Learn MCP 動的解決値）
2. Index 作成（Vector field + Semantic config + Vectorizer。`az rest` の API バージョンも MS Learn MCP 取得）
3. Data Source 作成（Indexer モード時）
4. Skillset 作成（Embedding / 分割）
5. Indexer 作成 + 初回実行
6. Knowledge Source 作成
7. Knowledge Base 作成（MCP エンドポイント取得）
8. Q3=`する` の場合のみ:
   - Foundry プロジェクト作成（既存再利用優先、なければ Standard Agent Setup 公式 Bicep）
   - モデル Global Deployment（Q6 フォールバック方針準拠）
   - Foundry → Knowledge Base の MCP / `azure_ai_search` 接続登録
9. RBAC ロール割当（`azure-rbac` Skill に委譲。割当対象ロール一覧と委譲呼出のみ）
10. `created-resources.json` 追記

- 破壊的変更（削除/置換）は行わない
- create 系のみ指数バックオフ最大 3 回

### 4.4 Document 更新
- `docs/catalog/service-catalog-matrix.md`（重複行を作らない）
- `infra/README.md`（実行手順・前提条件・注意の最小追記）
- ルート `/README.md` は変更しない

### 4.5 AC 検証
- `harness-verification-loop` と `azure-validate` に従い
  `ac-verification.md` を生成
- PASS / NEEDS-VERIFICATION / FAIL を明示

## 5) Microsoft Learn 根拠（必須）
既存 Design Agent と同パターンで、SKU / モデル / API バージョン / Indexer 対応データソースについて以下を `{WORK}artifacts/cli-evidence.md` に記録する。
- URL
- タイトル
- 取得日時（ISO）
- 取得不可時は `要確認（要：Microsoft Learn 確認）`

## 6) 禁止事項
- SKU / モデル名 / API バージョン / リージョン具体名のハードコード
- 秘密情報を成果物に含めること
- 破壊的変更（既存リソース削除）
- Q3=`しない` 時の Foundry 関連リソース作成
- AC を事後緩和して PASS にすること
- ルート `/README.md` の変更
- IaC スクリプトファイル本体を本 PR に含めること（Agent 実行時生成）

## 7) AC（4-B メタ）
- **AC4B-meta1**: 本ファイルが新規作成され、章立てが `Dev-Microservice-Azure-AddServiceDeploy.agent.md` に準拠
- **AC4B-meta2**: AC4B-1〜AC4B-13 が `§4.2.1 デフォルト AC` に定義
- **AC4B-meta3**: Skill 依存がフルパスで列挙
- **AC4B-meta4**: Microsoft Learn 根拠（必須）セクションを設置
- **AC4B-meta5**: 本 PR に `infra/azure/...` 実スクリプトを含めない
- **AC4B-meta6**: markdownlint が PASS
<!-- markdownlint-enable MD013 MD022 MD031 MD032 MD041 MD058 MD060 -->
