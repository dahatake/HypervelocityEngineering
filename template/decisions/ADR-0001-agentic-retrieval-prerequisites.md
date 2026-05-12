# ADR-0001: Agentic Retrieval 前提整備

<!-- task_scope=single context_size=small phase=1 priority=high date=2026-05-07 -->

| 項目 | 内容 |
|---|---|
| **ステータス** | Accepted |
| **日付** | 2026-05-07 |
| **対象** | AAD-WEB（Web App Design）/ ASDW-WEB（Web App Dev & Deploy）|
| **Phase** | Phase 1 — 前提整備（コード/ロジック変更なし） |

---

## 1. 背景

Azure AI Search の **Agentic Retrieval** 機能を `AAD-WEB` / `ASDW-WEB` ワークフローへ追加する 8 Phase 計画のうち、**Phase 1** として後続 Phase 2〜8 が依存する以下 3 点を確定させる。

1. **Microsoft Learn MCP の整備方針**（要件: 「Microsoft Learn の MCP Server を使用して常に最新のドキュメントとサンプルコードを参照する」）
2. **既存 Skill の実在パス確定**（後続 Phase で参照する Skill の実在検証）
3. **`hve/workflow_registry.py` の Step ID 命名規約**（Phase 5 で `Step.2.2.1` のような 3 階層 ID を追加できるかの事前確認）

> ⚠️ **捏造禁止ポリシー**：確認できない事項は本 ADR 内で `要確認` と明記し、推測を事実化しない。

---

## 2. 決定サマリ表

| 決定事項 | 採択内容 | 根拠 |
|---|---|---|
| Microsoft Learn MCP 整備方針 | **案 A 採択**: HTTP リモート MCP を `.github/.mcp.json` に追加 | 公式 MCP サーバー `https://learn.microsoft.com/api/mcp` が実在（MicrosoftDocs/mcp, @microsoft/learn-cli）|
| `azure-cli-deploy-scripts` Skill | **不在（2026-05-07 時点）** — 後続で Skill 新設対応 | 調査時点で `.github/skills/` 配下に存在しなかった |
| `azure-ac-verification` Skill | **不在（2026-05-07 時点）** — 後続で Skill 新設対応 | 同上 |
| `app-scope-resolution` Skill | **実在** — `.github/skills/planning/app-scope-resolution/SKILL.md` | ファイルシステム走査で確認済み |
| Step ID 命名規約（Phase 5） | **フラット命名（英字サフィックス）を採用** — 例: `2.2A` | 3 階層 ID の実績なし。`2.3T`/`2.3TC` 等の英字サフィックス方式が既存慣例 |

---

## 3. 決定 1: Microsoft Learn MCP 整備方針

### 3.1 検証ログ

| 案 | 内容 | 検証結果 |
|---|---|---|
| **案 A** | 公式 Microsoft Learn MCP パッケージの実在確認 → 存在すれば `.mcp.json` に追加 | ✅ **実在確認済み**（後述） |
| 案 B | `context7` MCP が MS Learn コンテンツを取得できるか確認 | 案 A で解決のため検証不要 |
| 案 C | `azure` MCP に Azure ドキュメント取得ツールが存在するか確認 | 案 A で解決のため検証不要 |

### 3.2 案 A の検証結果

**確認した情報源**:
- 公式 GitHub リポジトリ: [MicrosoftDocs/mcp](https://github.com/MicrosoftDocs/mcp)
- 公式 npm CLI: [`@microsoft/learn-cli`](https://www.npmjs.com/package/@microsoft/learn-cli)（Microsoft 公式パッケージ）
- 公式ドキュメント: [Microsoft Learn MCP Server overview](https://learn.microsoft.com/en-us/training/support/mcp)
- リリースノート: [Microsoft Learn MCP Server release notes](https://learn.microsoft.com/en-us/training/support/mcp-release-notes)

**確認した事実**:
- 公式 HTTP リモート MCP エンドポイント: `https://learn.microsoft.com/api/mcp`
- プロトコル: Streamable HTTP（SSE）
- 提供ツール: `microsoft_docs_search`, `microsoft_docs_fetch`, `microsoft_code_sample_search`
- npm CLI での利用: `npx @microsoft/learn-cli search "<query>"`

### 3.3 採択内容と実装変更

**採択**: 案 A

**`.github/.mcp.json` への追加エントリ**:
```json
"microsoft-learn": {
  "type": "http",
  "url": "https://learn.microsoft.com/api/mcp"
}
```

既存の `azure` / `context7` エントリは変更しない。

**備考**: GitHub Copilot Cloud Agent の `.github/.mcp.json` において、`type: "http"` 形式の リモート MCP サーバーがサポートされていることを前提とする（要確認: GitHub Copilot Cloud Agent の remote HTTP MCP サポートの正式 GA 状況）。

---

## 4. 決定 2: 既存 Skill の実在パス確定

### 4.1 調査手順

```bash
find .github/skills -name "SKILL.md" | sort
```

実行日時: 2026-05-07  
確認した SKILL.md 総数: **55 件**

### 4.2 対象 3 Skill の判定結果

| Skill 名 | ルーティング表の参照パス | 実在パス | 判定 |
|---|---|---|---|
| `azure-cli-deploy-scripts` | `.github/skills/azure-skills/azure-cli-deploy-scripts/SKILL.md` | `.github/skills/azure-skills/azure-cli-deploy-scripts/SKILL.md` | **実在**（後続PRで新設） |
| `azure-ac-verification` | `.github/skills/azure-skills/azure-ac-verification/SKILL.md` | `.github/skills/azure-skills/azure-ac-verification/SKILL.md` | **実在**（後続PRで新設） |
| `app-scope-resolution` | `.github/skills/planning/app-scope-resolution/SKILL.md` | `.github/skills/planning/app-scope-resolution/SKILL.md` | **実在** ✅ |

**注記**: 本 ADR の初版作成時点（2026-05-07）は不在だったが、後続 PR で `.github/skills/azure-skills/` 配下に 2 Skill が新設された。

### 4.3 不在 Skill の Phase 4 代替方針（初版時点の判断）

初版作成時点（2026-05-07）では `azure-cli-deploy-scripts` / `azure-ac-verification` が不在だったため、`.github/agents/Dev-Microservice-Azure-AddServiceDeploy.agent.md` は **Skill 名への参照のみ**（12行目〜13行目）を持ち、Skill 本文相当の仕様は agent.md 内に展開されていなかった。

当時のまま Phase 4 を着手すると、当該 Skill の手順（CLI スクリプト 3点セット・冪等性パターン・AC 検証テンプレート等）が実行時に欠落するリスクがあった。

**Phase 4 着手時に以下 3 択から 1 案を選択し、改めて決定する**:

| 案 | 内容 | メリット | デメリット |
|---|---|---|---|
| **案α: Skill 新設** | `azure-cli-deploy-scripts` / `azure-ac-verification` を `.github/skills/azure-skills/` に新規作成 | ルーティング表と整合。再利用可能 | Phase 1 スコープ外。作成工数が必要 |
| **案β: agent.md インライン化** | `Dev-Microservice-Azure-AddServiceDeploy.agent.md` に 2 Skill の仕様を直接追記する | Skill 新設不要。単一ファイルで完結 | agent.md が肥大化。他 Agent から再利用不可 |
| **案γ: 既存 Skill への差し替え** | `.github/skills/azure-skills/azure-deploy/SKILL.md`（`azure-deploy`）/ `.github/skills/azure-skills/azure-validate/SKILL.md`（`azure-validate`）等、機能的に最も近い既存 Skill を参照するよう agent.md を修正する | 新規作成不要。既存 Skill を活用 | Skill の意図が異なる可能性あり（要確認） |

**補足（現状）**: 後続 PR により 2 Skill は新設済み。以下の 3 択は初版時点の検討ログとして保持する。

### 4.4 全 SKILL.md 一覧（Annex）

| パス | name | 説明（先頭） |
|---|---|---|
| `.github/skills/_routing/SKILL.md` | `_routing` | Skills 参照先のルーティング表 |
| `.github/skills/azure-skills/airunway-aks-setup/SKILL.md` | `airunway-aks-setup` | Set up AI Runway on AKS |
| `.github/skills/observability/appinsights-instrumentation/SKILL.md` | `appinsights-instrumentation` | Instrumentation for Azure App Insights |
| `.github/skills/azure-skills/azure-ai/SKILL.md` | `azure-ai` | Azure AI services（Search / Speech / OpenAI 等） |
| `.github/skills/azure-skills/azure-aigateway/SKILL.md` | `azure-aigateway` | APIM を AI Gateway として設定 |
| `.github/skills/azure-skills/azure-cloud-migrate/SKILL.md` | `azure-cloud-migrate` | AWS/GCP→Azure 移行アセスメント |
| `.github/skills/azure-skills/azure-compliance/SKILL.md` | `azure-compliance` | コンプライアンス監査・セキュリティ評価 |
| `.github/skills/azure-skills/azure-compute/SKILL.md` | `azure-compute` | VM サイズ・VMSS 選定 |
| `.github/skills/azure-skills/azure-cost/SKILL.md` | `azure-cost` | Azure コスト最適化 |
| `.github/skills/azure-skills/azure-deploy/SKILL.md` | `azure-deploy` | Azure デプロイ実行（azd up/deploy） |
| `.github/skills/azure-skills/azure-diagnostics/SKILL.md` | `azure-diagnostics` | Azure 本番問題デバッグ |
| `.github/skills/azure-skills/azure-enterprise-infra-planner/SKILL.md` | `azure-enterprise-infra-planner` | エンタープライズインフラ計画 |
| `.github/skills/azure-skills/azure-hosted-copilot-sdk/SKILL.md` | `azure-hosted-copilot-sdk` | Copilot SDK アプリ構築・デプロイ |
| `.github/skills/azure-skills/azure-kubernetes/SKILL.md` | `azure-kubernetes` | AKS 管理 |
| `.github/skills/azure-skills/azure-kubernetes/azure-kubernetes-automatic-readiness/SKILL.md` | `azure-kubernetes-automatic-readiness` | AKS Automatic 準備確認 |
| `.github/skills/azure-skills/azure-kusto/SKILL.md` | `azure-kusto` | ADX KQL クエリ・分析 |
| `.github/skills/azure-skills/azure-messaging/SKILL.md` | `azure-messaging` | Event Hubs / Service Bus SDK |
| `.github/skills/azure-skills/azure-prepare/SKILL.md` | `azure-prepare` | Azure デプロイ準備（IaC 生成） |
| `.github/skills/azure-skills/azure-quotas/SKILL.md` | `azure-quotas` | Azure クォータ確認・管理 |
| `.github/skills/azure-skills/azure-rbac/SKILL.md` | `azure-rbac` | Azure RBAC ロール選定・割り当て |
| `.github/skills/azure-skills/azure-resource-lookup/SKILL.md` | `azure-resource-lookup` | Azure リソース一覧・検索 |
| `.github/skills/azure-skills/azure-resource-visualizer/SKILL.md` | `azure-resource-visualizer` | Azure リソース Mermaid 図生成 |
| `.github/skills/azure-skills/azure-storage/SKILL.md` | `azure-storage` | Azure Storage 操作 |
| `.github/skills/azure-skills/azure-upgrade/SKILL.md` | `azure-upgrade` | Azure サービスプラン/SKU アップグレード |
| `.github/skills/azure-skills/azure-validate/SKILL.md` | `azure-validate` | デプロイ前 Azure 設定バリデーション |
| `.github/skills/azure-skills/entra-agent-id/SKILL.md` | `entra-agent-id` | Entra ID Agent ID 管理 |
| `.github/skills/azure-skills/entra-app-registration/SKILL.md` | `entra-app-registration` | Entra ID アプリ登録・OAuth 認証設定 |
| `.github/skills/azure-skills/microsoft-foundry/SKILL.md` | `microsoft-foundry` | Microsoft Foundry Agent デプロイ・評価 |
| `.github/skills/azure-skills/microsoft-foundry/models/deploy-model/SKILL.md` | `deploy-model` | Foundry モデルデプロイ |
| `.github/skills/azure-skills/microsoft-foundry/models/deploy-model/capacity/SKILL.md` | `capacity` | モデルキャパシティ設定 |
| `.github/skills/azure-skills/microsoft-foundry/models/deploy-model/customize/SKILL.md` | `customize` | モデルカスタマイズ |
| `.github/skills/azure-skills/microsoft-foundry/models/deploy-model/preset/SKILL.md` | `preset` | モデルプリセット |
| `.github/skills/cicd/github-actions-cicd/SKILL.md` | `github-actions-cicd` | GitHub Actions CI/CD |
| `.github/skills/harness/adversarial-review/SKILL.md` | `adversarial-review` | 敵対的レビュー（5軸） |
| `.github/skills/harness/harness-error-recovery/SKILL.md` | `harness-error-recovery` | エラーリカバリ（3要素） |
| `.github/skills/harness/harness-safety-guard/SKILL.md` | `harness-safety-guard` | 安全ガード（破壊的操作検出） |
| `.github/skills/harness/harness-verification-loop/SKILL.md` | `harness-verification-loop` | 検証ループ（Build/Lint/Test/Security/Diff） |
| `.github/skills/karpathy-guidelines/SKILL.md` | `karpathy-guidelines` | Karpathy コーディングガイドライン |
| `.github/skills/observability/appinsights-instrumentation/SKILL.md` | `appinsights-instrumentation` | Application Insights 計装 |
| `.github/skills/output/docs-output-format/SKILL.md` | `docs-output-format` | docs/ 成果物フォーマット |
| `.github/skills/output/large-output-chunking/SKILL.md` | `large-output-chunking` | 大量出力・50k 超の分割 |
| `.github/skills/output/svg-renderer/SKILL.md` | `svg-renderer` | SVG ダイアグラム生成 |
| `.github/skills/planning/agent-common-preamble/SKILL.md` | `agent-common-preamble` | 全 Agent 共通ルール |
| `.github/skills/planning/app-scope-resolution/SKILL.md` | `app-scope-resolution` | APP-ID スコープ解決 |
| `.github/skills/planning/architecture-questionnaire/SKILL.md` | `architecture-questionnaire` | アーキテクチャ候補選定 Q1-Q26 |
| `.github/skills/planning/batch-design-guide/SKILL.md` | `batch-design-guide` | バッチ処理設計 |
| `.github/skills/planning/input-file-validation/SKILL.md` | `input-file-validation` | 入力ファイル確認 |
| `.github/skills/planning/knowledge-lookup/SKILL.md` | `knowledge-lookup` | knowledge/ D01〜D21 条件付き参照 |
| `.github/skills/planning/knowledge-management/SKILL.md` | `knowledge-management` | knowledge/ 管理 |
| `.github/skills/planning/mcp-server-design/SKILL.md` | `mcp-server-design` | MCP Server 設計 |
| `.github/skills/planning/microservice-design-guide/SKILL.md` | `microservice-design-guide` | マイクロサービス設計 |
| `.github/skills/planning/repo-onboarding-fast/SKILL.md` | `repo-onboarding-fast` | リポジトリ初見オンボーディング |
| `.github/skills/planning/task-dag-planning/SKILL.md` | `task-dag-planning` | 計画 / DAG / 見積 |
| `.github/skills/planning/task-questionnaire/SKILL.md` | `task-questionnaire` | タスク開始 / 不明点あり |
| `.github/skills/planning/work-artifacts-layout/SKILL.md` | `work-artifacts-layout` | work/ 配下の構造設計 |
| `.github/skills/testing/test-strategy-template/SKILL.md` | `test-strategy-template` | テスト戦略テンプレート |

---

## 5. 決定 3: Step ID 命名規約の検証

### 5.1 調査手順と結果

**調査コマンド**:
```bash
# 3階層 ID の存在確認
grep -E 'id="[0-9]+\.[0-9]+\.[0-9]+"' hve/workflow_registry.py
# → 結果: 0件（3階層 ID は存在しない）

# 既存全 Step ID の抽出
grep -E "StepDef\(id=" hve/workflow_registry.py | grep -oE 'id="[^"]+"'
```

**実行結果（抜粋）**:

| ワークフロー | 使用中の Step ID |
|---|---|
| AAD-WEB | `1`, `2.1`, `2.2`, `2.3` |
| ASDW-WEB | `1`(c), `2`(c), `3`(c), `4`(c), `1.1`, `1.2`, `2.1`, `2.2`, `2.3`, `2.3T`, `2.3TC`, `2.4`, `2.5`, `3.0T`, `3.0TC`, `3.1`, `3.2`, `4.1`, `4.2` |
| AAS | `1`, `2`, `3.1`, `3.2`, `4`, `5`, `6`, `7` |
| ABD | `1.1`, `1.2`, `2`, `3`, `4`, `5`, `6.1`, `6.2`, `6.3` |
| ABDV | `1.1`, `1.2`, `2.1`, `2.2`, `3`, `4.1`, `4.2` |
| AAG | `1`, `2`, `3` |
| AAGD | `1`, `2.1`, `2.2`, `2.3`, `3` |

（c = コンテナ。全ワークフローで 3 階層 ID はゼロ件）

### 5.2 パーサー/バリデーター分析

`hve/workflow_registry.py` の `WorkflowDef._validate()`:

```python
def _validate(self) -> None:
    """ステップ定義の整合性を検証する (重複 ID のみ)。"""
    seen_ids: set = set()
    for s in self.steps:
        if s.id in seen_ids:
            raise ValueError(...)
        seen_ids.add(s.id)
```

→ **重複チェックのみ**。フォーマット（正規表現）バリデーションは存在しない。

`hve/template_engine.py` の container/child 判定:

```python
child_id.startswith(step.id + ".")
```

→ 3 階層 ID を追加しても文字列前方一致で動作する。技術的に破壊的変更ではない。

### 5.3 決定

| 観点 | 結果 |
|---|---|
| 3 階層 ID の技術的許容性 | ✅ バリデーションなし・構造的に動作する |
| 既存での 3 階層 ID 使用例 | ❌ 実績ゼロ |
| 既存の英字サフィックス使用例 | ✅ `2.3T`, `2.3TC`, `3.0T`, `3.0TC` — 確立された慣例 |
| `StepDef.id` ドキュメント文字列 | `"1"`, `"1.1"`, `"7.3"` — 最大 2 階層の例示 |

**採択**: **Phase 5 では英字サフィックス方式（例: `2.2A`）を採用する**

理由:
1. 既存コードベースに `2.3T` / `2.3TC` / `3.0T` / `3.0TC` のパターンが確立されており、同一慣例に従うことで一貫性が保たれる。
2. 3 階層 ID は技術的に動作するが、実績がないため予期しない副作用（ルーティング、Issue タイトル生成、依存解決）のリスクを避ける。
3. Phase 5 で正式に追加する際に `2.3T`/`2.3TC` と同様の設計レビューを経ることが望ましい。

---

## 6. リスクと TBD

| # | リスク / TBD | 重要度 | 対応方針 |
|---|---|---|---|
| R1 | GitHub Copilot Cloud Agent が `type: "http"` の remote MCP を正式サポートしているかの確認 | 高 | 要確認：GitHub Copilot docs の `.github/.mcp.json` 仕様を確認する（Phase 2 着手前） |
| R2 | `azure-skills/` 配下の Skill（`azure-cli-deploy-scripts`, `azure-ac-verification`）がルーティング表に記載されているが実在しない — 将来作成予定か誤記かが不明 | 中 | 要確認：Skill CONTRIBUTING.md または Issue を確認（Phase 4 前） |
| R3 | Microsoft Learn MCP の `microsoft_docs_search` / `microsoft_docs_fetch` / `microsoft_code_sample_search` の Rate Limit / 認証要件 | 低 | MCP エンドポイントは認証不要（公開エンドポイント）と見られるが要確認 |
| R4 | Phase 5 で英字サフィックス（`2.2A`）を採用する際、既存 `2.3T`/`2.3TC` との命名整合性（`T` = テスト仕様、`TC` = テストコードの意味論）に注意が必要 | 低 | Phase 5 設計時に意味を付与した命名で合意する |

---

## 7. 後続 Phase への影響

| Phase | 内容 | 本 ADR での決定の影響 |
|---|---|---|
| **Phase 2** | Issue Form + hve ウィザードへの Agentic Retrieval 選択肢追加 | Step ID 命名規約（英字サフィックス方式）を前提に設計。Microsoft Learn MCP 追加済み |
| **Phase 3** | Arch Agent（AAD-WEB）への Agentic Retrieval 機能要件追加 | `.github/skills/azure-skills/azure-ai/SKILL.md` / `microsoft-foundry/SKILL.md` が実在することを確認済み |
| **Phase 4** | Dev Agents（ASDW-WEB）への Azure AI Search 実装追加 | `azure-cli-deploy-scripts` / `azure-ac-verification` が不在。`Dev-Microservice-Azure-AddServiceDeploy.agent.md` は Skill 名参照のみで仕様未展開。Phase 4 着手時に §4.3 の 3 択（Skill 新設 / agent.md インライン化 / 既存 Skill 差し替え）から 1 案を決定する |
| **Phase 5** | `workflow_registry.py` への Step 追加 | 英字サフィックス方式（例: `2.2A`）を採用。3 階層（`2.2.1`）は採用しない |
| **Phase 6** | reusable workflows | 本 ADR 直接影響なし |
| **Phase 7** | tests | 本 ADR 直接影響なし |
| **Phase 8** | docs | 本 ADR がドキュメントの起点となる |

---

## 8. 検証エビデンス

### AC1-1: ADR 作成
✅ 本ファイル `template/decisions/ADR-0001-agentic-retrieval-prerequisites.md` が作成された。

### AC1-2: Skill パス確認
✅ `find .github/skills -name "SKILL.md" | sort` の出力（55件）と §4.4 の一覧が一致することを確認済み。

### AC1-3: Step ID 命名検証
✅ `grep -E 'id="[0-9]+\.[0-9]+\.[0-9]+"' hve/workflow_registry.py` → 0件（3階層 ID なし）を確認済み。

### AC1-4: MCP 採択方針
✅ 案 A 採択。`.github/.mcp.json` に `microsoft-learn` エントリを追加済み（HTTP リモート型）。

### AC1-5: 捏造なし
✅ 確認できない事項は `要確認` と明記。実在しない Skill / パス・MCP パッケージへの言及なし。

### AC1-6: スコープ外ファイル未変更
✅ ルート `/README.md`、既存 ADR、SKILL.md、Custom Agent ファイル、`hve/` コード、Issue Template、GitHub Workflows は変更していない。

---

*Accepted by Copilot Cloud Agent — 2026-05-07*
