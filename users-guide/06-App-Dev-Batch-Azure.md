# バッチ処理実装フェーズ チュートリアル

> 初見ユーザーが迷わず **Issue 作成 → Sub Issue 自動生成 → Custom Agent 実行 → PR マージ → デプロイ** の全ステップを進められるよう設計したガイドです。

---

## 対象読者

| 対象 | 前提スキル |
|---|---|
| バッチ処理設計・実装を担当するエンジニア | GitHub Issues / Actions の基本操作 |
| このリポジトリで初めて Copilot Coding Agent を使う開発者 | Markdown / YAML の読み書き |

---

## 前提条件

本チュートリアルを開始する前に、以下の条件が満たされていることを確認してください。

### リポジトリ設定

| 項目 | 確認方法 | 設定値 |
|---|---|---|
| Workflow permissions | Settings → Actions → General → Workflow permissions | **Read and write permissions** |
| GitHub Copilot | Settings → GitHub Copilot（Organization or Repository level） | **有効** |
| GITHUB_TOKEN 権限 | `.github/workflows/*.yml` の `permissions` ブロック | `issues: write`, `contents: write` |

### 必須ドキュメント（設計フェーズの成果物）

バッチ実装フェーズを開始するには、**設計フェーズ**（ABD ワークフロー）の成果物が事前に必要です。

| ファイル | 作成元ワークフロー | 用途 |
|---|---|---|
| `docs/usecase-list.md` | 手動作成（PM / 要件定義） | Step.1.1 / Step.1.2 の入力 |
| `docs/batch/batch-domain-analytics.md` | Step.1.1: `Arch-Batch-DomainAnalytics` | Step.2 以降の入力 |
| `docs/batch/batch-data-source-analysis.md` | Step.1.2: `Arch-Batch-DataSourceAnalysis` | Step.2 以降の入力 |
| `docs/batch/batch-data-model.md` | Step.2: `Arch-Batch-DataModel` | Step.3 以降の入力 |
| `docs/batch/batch-job-catalog.md` | Step.3: `Arch-Batch-JobCatalog` | Step.4 以降の入力 |
| `docs/batch/batch-service-catalog.md` | Step.4: `Arch-Batch-ServiceCatalog` | Step.4.5・Step.5.1/5.2 の入力 |
| `docs/batch/batch-test-strategy.md` | Step.4.5: `Arch-Batch-TestStrategy` | Step.5.3 の入力 |

> ❗ 上記ファイルがまだ存在しない場合は、先に「設計フェーズ」チュートリアルを完了してください。  
> → 参照: [`users-guide/04-AppDesign-Batch.md`](./04-AppDesign-Batch.md)

---

## 全体フロー概観

```
[Step 1]  Issue を作成（Issue Template 使用）
     │  label: auto-batch-design
     ▼
[Step 2]  ABD Bootstrap が Sub Issue を自動生成
     │  step-1.1 と step-1.2 が並列開始
     ▼
[Step 3]  各 Sub Issue に Copilot (Custom Agent) が自動アサイン
     │  Agent が設計ドキュメントを生成して PR を作成
     ▼
[Step 4]  PR をレビュー → マージ
     │  Sub Issue が close → 次の Sub Issue が自動起動
     ▼
[Step 5]  全設計 Step 完了 → 実装 Step に移行（手動 or 別ワークフロー）
     ▼
[Step 6]  実装コード / テストコード / インフラ を Deploy
```

### 依存グラフ（ABD ワークフロー）

```
step-1.1 ──┐
            ├──► step-2 ──► step-3 ──► step-4 ──► step-4.5 ──► step-5.1 ──┐
step-1.2 ──┘                                                    └──► step-5.2 ──┤
                                                                                ▼
                                                                            step-5.3
```

| 重要な依存関係 | 説明 |
|---|---|
| step-1.1 と step-1.2 は **並列開始** | 設計開始直後に両方同時に Copilot へアサイン |
| step-2 は step-1.1 **AND** step-1.2 の **両方完了後** に起動 | AND 依存 — 片方だけでは次に進まない |
| step-5.1 と step-5.2 は step-4.5 完了後に **並列開始** | 独立しているため同時進行可 |
| step-5.3 は step-5.1 **AND** step-5.2 の **両方完了後** に起動 | AND 依存 |

---

## Step 1: Issue を作成する

### 1-1. Issue テンプレートを開く

1. リポジトリの **Issues** タブ → **New issue** をクリック
2. テンプレート一覧から **"Auto Batch Design Workflow"** を選択して **"Get started"** をクリック

> 📄 テンプレートファイル: [`.github/ISSUE_TEMPLATE/auto-batch-design.yml`](../.github/ISSUE_TEMPLATE/auto-batch-design.yml)

### 1-2. フォームを入力する

| フィールド | 入力内容 | 例 |
|---|---|---|
| 対象ブランチ | 設計ドキュメントをコミットするブランチ | `main` |
| 実行するステップ | 実行したい Step にチェック（未選択 = 全 Step） | （全選択推奨） |
| 追加コメント | データソース・スケジュール・Azure サービス等の補足 | `S3互換ストレージから日次バッチ` |

### 1-3. Issue を Submit する

- Issue を Submit すると、`auto-batch-design` ラベルが自動付与されます
- Actions タブで **"Auto Batch Design - Bootstrap"** ジョブが起動したことを確認してください

> ✅ 確認ポイント: Actions タブに `auto-batch-design.yml` が表示されて実行中になること

---

## Step 2: Sub Issue の自動生成を確認する

Bootstrap ジョブが完了すると、以下が自動で行われます。

1. **Sub Issue が一括生成される** — 各 Step ごとに Issue が作成される
2. **step-1.1 と step-1.2 に `abd:ready` + `abd:running` ラベルが付与される**
3. **Copilot が step-1.1 と step-1.2 に自動アサインされる**
4. **親 Issue にサマリコメントと Sub Issue 一覧が投稿される**

### 確認する内容

```
親 Issue のコメント:
  ✅ Sub Issue 一覧 (step-1.1 〜 step-5.3)
  ✅ step-1.1 / step-1.2 に Copilot アサイン済み

Sub Issue の状態:
  step-1.1: abd:running ラベル付き / Copilot アサイン済み
  step-1.2: abd:running ラベル付き / Copilot アサイン済み
  step-2〜step-5.3: ラベルなし（依存先の完了待ち）
```

> 💡 Sub Issue が作成されない場合は [トラブルシューティング](#トラブルシューティング) を参照してください。

---

## Step 3: Custom Agent の実行を待つ

各 Sub Issue にアサインされた Copilot は、対応する **Custom Agent** を使用して設計ドキュメントを生成します。

### 各 Step の Custom Agent と成果物

| Step | Custom Agent | 入力ファイル | 成果物 |
|---|---|---|---|
| step-1.1 | [`Arch-Batch-DomainAnalytics`](../.github/agents/Arch-Batch-DomainAnalytics.agent.md) | `docs/usecase-list.md` | `docs/batch/batch-domain-analytics.md` |
| step-1.2 | [`Arch-Batch-DataSourceAnalysis`](../.github/agents/Arch-Batch-DataSourceAnalysis.agent.md) | `docs/usecase-list.md`, `docs/data-model.md`（任意） | `docs/batch/batch-data-source-analysis.md` |
| step-2 | [`Arch-Batch-DataModel`](../.github/agents/Arch-Batch-DataModel.agent.md) | `batch-domain-analytics.md`, `batch-data-source-analysis.md` | `docs/batch/batch-data-model.md` |
| step-3 | [`Arch-Batch-JobCatalog`](../.github/agents/Arch-Batch-JobCatalog.agent.md) | `batch-domain-analytics.md`, `batch-data-source-analysis.md`, `batch-data-model.md` | `docs/batch/batch-job-catalog.md` |
| step-4 | [`Arch-Batch-ServiceCatalog`](../.github/agents/Arch-Batch-ServiceCatalog.agent.md) | `batch-job-catalog.md`, `batch-data-model.md`, `batch-domain-analytics.md` | `docs/batch/batch-service-catalog.md` |
| step-4.5 | [`Arch-Batch-TestStrategy`](../.github/agents/Arch-Batch-TestStrategy.agent.md) | `batch-service-catalog.md`, `batch-data-model.md` | `docs/batch/batch-test-strategy.md` |
| step-5.1 | [`Arch-Batch-JobSpec`](../.github/agents/Arch-Batch-JobSpec.agent.md) | `batch-service-catalog.md`, `batch-job-catalog.md`, `batch-data-model.md` | `docs/batch/jobs/{jobId}-{jobNameSlug}-spec.md` |
| step-5.2 | [`Arch-Batch-MonitoringDesign`](../.github/agents/Arch-Batch-MonitoringDesign.agent.md) | `batch-service-catalog.md`, `batch-job-catalog.md` | `docs/batch/batch-monitoring-design.md` |
| step-5.3 | [`Arch-Batch-TDDTestSpec`](../.github/agents/Arch-Batch-TDDTestSpec.agent.md) | `batch-test-strategy.md`, `jobs/*-spec.md`, `batch-monitoring-design.md` | `docs/test-specs/{jobId}-test-spec.md` |

### Custom Agent を手動でアサインする場合

Bootstrap が Copilot アサインに失敗した場合は、手動で以下の手順を実施してください。

1. 対象の Sub Issue を開く
2. 右サイドバーの **Assignees** → 歯車アイコン → `copilot` を選択
3. サイドバーの **Copilot** セクション → **Select agent** から対応する Agent を選択
4. Issue を Save/Update

---

## Step 4: PR をレビューしてマージする

Custom Agent が成果物を生成すると、リポジトリに **PR（Pull Request）** が自動作成されます。

### 4-1. PR の確認事項

各 PR をマージする前に以下を確認してください。

```
□ 成果物ファイルが正しいパスに生成されているか
  例: docs/batch/batch-domain-analytics.md

□ ドキュメントの内容がユースケース仕様と整合しているか

□ 前段の設計ドキュメントを正しく参照しているか

□ work/ 配下の plan.md に split_decision が記載されているか
  → SPLIT_REQUIRED の場合、実装ファイルが混入していないか確認
```

### 4-2. PR の自動チェック

PR 作成時に以下のワークフローが自動実行されます。

| Workflow | 確認内容 |
|---|---|
| [`check-split-mode.yml`](../.github/workflows/check-split-mode.yml) | 分割モード違反（実装ファイルの混入）を検知 |
| [`validate-plan.yml`](../.github/workflows/validate-plan.yml) | `plan.md` の見積・分割判定・実装ファイル有無を検証 |

> ⚠️ これらの自動チェックが失敗している PR はマージしないでください。

### 4-3. PR をマージする

PR の確認が完了したら **"Squash and merge"** または **"Merge pull request"** でマージします。

PR がマージされると：

- 対応する Sub Issue が **close** される（または手動 close が必要な場合あり）
- ABD Orchestrator が次の Step の依存関係を確認する
- 依存が解消された次の Step Issue に `abd:ready` + `abd:running` が付与される
- Copilot が次の Step に自動アサインされる

---

## Step 5: 全設計 Step の完了を確認する

全 Step（step-1.1 〜 step-5.3）が完了すると：

1. 親 Issue に **完了通知コメント** が投稿される
2. 以下のファイルが所定のパスに揃っていることを確認してください

```
docs/
├── batch/
│   ├── batch-domain-analytics.md       ← step-1.1 成果物
│   ├── batch-data-source-analysis.md   ← step-1.2 成果物
│   ├── batch-data-model.md             ← step-2 成果物
│   ├── batch-job-catalog.md            ← step-3 成果物
│   ├── batch-service-catalog.md        ← step-4 成果物
│   ├── batch-test-strategy.md          ← step-4.5 成果物
│   ├── batch-monitoring-design.md      ← step-5.2 成果物
│   └── jobs/
│       └── {jobId}-{jobNameSlug}-spec.md   ← step-5.1 成果物
└── test-specs/
    └── {jobId}-test-spec.md             ← step-5.3 成果物
```

> 💡 設計フェーズ完了後に実装フェーズ（コーディング・デプロイ）へ移行する場合は、新たに実装専用の Issue を起票して Custom Agent を使用してください。

---

## Step 6: 実装・デプロイへの移行（設計完了後）

設計ドキュメントが揃ったら、以下の実装ステップに進みます。

### Sub Issue を使った実装フェーズの運営

実装フェーズも設計フェーズと同様に、**Sub Issue → Custom Agent → PR → マージ** のサイクルで進めます。

#### 実装フェーズの新規 Issue 作成

1. **Issues** タブ → **New issue**（またはテンプレートが存在する場合はテンプレートを使用）
2. Issue 本文に実装タスクの仕様・参照ドキュメントを記載
3. `work/Issue-{識別子}/subissues.md` を PR に含めて `create-subissues` ラベルを付与する

#### Sub Issue の自動作成

`create-subissues` ラベルを PR に付与すると、[`create-subissues-from-pr.yml`](../.github/workflows/create-subissues-from-pr.yml) が `subissues.md` を解析して GitHub Issue を自動作成します。

> 📄 参照: [`create-subissues-from-pr.yml`](../.github/workflows/create-subissues-from-pr.yml)

#### Sub Issue の自動アドバンス

親 Sub Issue の PR がマージ（close）されると、[`advance-subissues.yml`](../.github/workflows/advance-subissues.yml) が依存関係を確認して、次の Sub Issue に Copilot を自動アサインします。

> 📄 参照: [`advance-subissues.yml`](../.github/workflows/advance-subissues.yml)

### 利用可能な実装系 Custom Agent

| Agent 名 | ファイル | 主な用途 |
|---|---|---|
| `Dev-Microservice-Azure-ServiceCoding-AzureFunctions` | [`.github/agents/Dev-Microservice-Azure-ServiceCoding-AzureFunctions.agent.md`](../.github/agents/Dev-Microservice-Azure-ServiceCoding-AzureFunctions.agent.md) | Azure Functions サービス実装 |
| `Dev-Microservice-Azure-ServiceTestCoding` | [`.github/agents/Dev-Microservice-Azure-ServiceTestCoding.agent.md`](../.github/agents/Dev-Microservice-Azure-ServiceTestCoding.agent.md) | TDD RED フェーズ — API テストコード生成 |
| `Dev-Microservice-Azure-ComputeDeploy-AzureFunctions` | [`.github/agents/Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.agent.md`](../.github/agents/Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.agent.md) | Azure Functions 実装 + CI/CD 構築 |
| `Dev-Microservice-Azure-DataDeploy` | [`.github/agents/Dev-Microservice-Azure-DataDeploy.agent.md`](../.github/agents/Dev-Microservice-Azure-DataDeploy.agent.md) | Azure CLI でデータ系サービス作成・サンプルデータ登録 |

### デプロイ

| Workflow | トリガー | 用途 |
|---|---|---|
| [`deploy-api-functions.yml`](../.github/workflows/deploy-api-functions.yml) | `workflow_dispatch` + push（main） | Azure Functions サービスのデプロイ |

---

## よくある失敗例と対処法

### ❌ Bootstrap ワークフローが起動しない

**原因の確認**:
1. `auto-batch-design` ラベルが Issue に付与されているか確認
2. Actions タブで当該ワークフローが **enabled** になっているか確認
3. Repository settings → Actions → General → Workflow permissions が **Read and write** になっているか確認

**対処**:
- ラベルが未付与の場合: Issue の右サイドバーから手動でラベルを付与する
- ワークフローが disabled の場合: Actions タブ → 対象ワークフロー → "Enable workflow"

---

### ❌ Sub Issue が作成されない

**原因の確認**:
1. Actions タブで Bootstrap ジョブのログを確認（Sub Issues API エラーが出ていないか）
2. `GITHUB_TOKEN` に `issues: write` 権限があるか確認
3. Sub-issues API が Organization/Repository プランで利用可能か確認

**対処**:
- Sub-issues API が使用できない場合: Actions ログを確認し、Bootstrap が親 Issue にチェックリストコメントとして Step 一覧を投稿しているか確認する（フォールバック動作）
- ログにエラーが出ている場合: `GITHUB_TOKEN` の権限を確認する

---

### ❌ Copilot が Sub Issue に自動アサインされない

**原因の確認**:
1. Actions ログで GraphQL `addAssigneesToAssignable` mutation がエラーになっていないか確認
2. `COPILOT_PAT` シークレットが設定されているか確認（または失効していないか）
3. リポジトリで GitHub Copilot が有効になっているか確認

**対処**:
- 手動でアサインする: Issue 右サイドバー → Assignees → `copilot` を選択し、Copilot セクションで適切な Custom Agent を選択

---

### ❌ step-2 が step-1.1 または step-1.2 完了後に起動しない

**原因**: `step-2` は step-1.1 **AND** step-1.2 の**両方**が完了するまで起動しません（AND 依存）。

**対処**:
1. 両方の Step Issue が close されているか確認
2. `abd:done` ラベルが両方の Issue に付与されているか確認
3. Actions タブで `auto-batch-design.yml` の状態遷移ジョブが起動しているか確認

---

### ❌ Custom Agent が「依存ファイルが見つからない」と報告する

**原因**: 前段の PR がマージされておらず、入力ファイルが `docs/batch/` に存在しない。

**対処**:
1. 前段の PR がマージ済みか確認する
2. `docs/batch/` 配下に対象ファイルが存在するか確認する
3. 存在しない場合は前段の Sub Issue を再確認して PR を作成・マージする

---

### ❌ plan.md の split-mode チェックが失敗する

**原因**: `plan.md` の `split_decision: SPLIT_REQUIRED` と判定されたにもかかわらず、実装ファイルが PR に混入している。

**対処**:
1. PR の差分を確認し、`work/` 配下以外の実装ファイルをコミットから除去する
2. `plan.md` の見積合計が 15 分以内か確認する（AGENTS.md §2.2 参照）
3. 必要であれば作業を Sub Issue に分割して再 PR する

---

### ❌ 状態遷移後も次の Step が起動しない

**原因の確認**:
1. Actions タブで `auto-batch-design.yml` の状態遷移ジョブがエラーで終了していないか確認
2. 前段 Sub Issue が正しく close されているか確認
3. AND 依存の場合、**すべての依存 Step** が close されているか確認

**対処**:
- Actions のジョブログを確認し、エラーメッセージに従い対処する
- 状態遷移が失敗した場合: Issue に `abd:done` ラベルを手動で付与して再トリガーする

---

## 参照ファイル一覧

### Issue テンプレート

| ファイル | 用途 |
|---|---|
| [`.github/ISSUE_TEMPLATE/auto-batch-design.yml`](../.github/ISSUE_TEMPLATE/auto-batch-design.yml) | ABD ワークフロー起動用テンプレート |

### Workflows

| ファイル | 用途 |
|---|---|
| [`.github/workflows/auto-batch-design.yml`](../.github/workflows/auto-batch-design.yml) | ABD Orchestrator（Step.1.1〜5.3 の自動起動・状態遷移） |
| [`.github/workflows/create-subissues-from-pr.yml`](../.github/workflows/create-subissues-from-pr.yml) | `subissues.md` から GitHub Issue を自動作成 |
| [`.github/workflows/advance-subissues.yml`](../.github/workflows/advance-subissues.yml) | Sub Issue 完了後に次 Sub Issue を自動アドバンス |
| [`.github/workflows/check-split-mode.yml`](../.github/workflows/check-split-mode.yml) | 分割モード違反の検知 |
| [`.github/workflows/validate-plan.yml`](../.github/workflows/validate-plan.yml) | `plan.md` 分割判定の検証 |
| [`.github/workflows/deploy-api-functions.yml`](../.github/workflows/deploy-api-functions.yml) | Azure Functions デプロイ |

### Custom Agents（Arch-Batch-* 設計系）

| ファイル | Step | 成果物 |
|---|---|---|
| [`.github/agents/Arch-Batch-DomainAnalytics.agent.md`](../.github/agents/Arch-Batch-DomainAnalytics.agent.md) | step-1.1 | `docs/batch/batch-domain-analytics.md` |
| [`.github/agents/Arch-Batch-DataSourceAnalysis.agent.md`](../.github/agents/Arch-Batch-DataSourceAnalysis.agent.md) | step-1.2 | `docs/batch/batch-data-source-analysis.md` |
| [`.github/agents/Arch-Batch-DataModel.agent.md`](../.github/agents/Arch-Batch-DataModel.agent.md) | step-2 | `docs/batch/batch-data-model.md` |
| [`.github/agents/Arch-Batch-JobCatalog.agent.md`](../.github/agents/Arch-Batch-JobCatalog.agent.md) | step-3 | `docs/batch/batch-job-catalog.md` |
| [`.github/agents/Arch-Batch-ServiceCatalog.agent.md`](../.github/agents/Arch-Batch-ServiceCatalog.agent.md) | step-4 | `docs/batch/batch-service-catalog.md` |
| [`.github/agents/Arch-Batch-TestStrategy.agent.md`](../.github/agents/Arch-Batch-TestStrategy.agent.md) | step-4.5 | `docs/batch/batch-test-strategy.md` |
| [`.github/agents/Arch-Batch-JobSpec.agent.md`](../.github/agents/Arch-Batch-JobSpec.agent.md) | step-5.1 | `docs/batch/jobs/{jobId}-{jobNameSlug}-spec.md` |
| [`.github/agents/Arch-Batch-MonitoringDesign.agent.md`](../.github/agents/Arch-Batch-MonitoringDesign.agent.md) | step-5.2 | `docs/batch/batch-monitoring-design.md` |
| [`.github/agents/Arch-Batch-TDDTestSpec.agent.md`](../.github/agents/Arch-Batch-TDDTestSpec.agent.md) | step-5.3 | `docs/test-specs/{jobId}-test-spec.md` |

### Custom Agents（Dev-Microservice-Azure-* 実装系）

| ファイル | 用途 |
|---|---|
| [`.github/agents/Dev-Microservice-Azure-ServiceCoding-AzureFunctions.agent.md`](../.github/agents/Dev-Microservice-Azure-ServiceCoding-AzureFunctions.agent.md) | Azure Functions サービス実装 |
| [`.github/agents/Dev-Microservice-Azure-ServiceTestCoding.agent.md`](../.github/agents/Dev-Microservice-Azure-ServiceTestCoding.agent.md) | TDD RED フェーズ — API テストコード生成 |
| [`.github/agents/Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.agent.md`](../.github/agents/Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.agent.md) | Azure Functions 実装 + CI/CD 構築 |
| [`.github/agents/Dev-Microservice-Azure-DataDeploy.agent.md`](../.github/agents/Dev-Microservice-Azure-DataDeploy.agent.md) | Azure CLI でデータ系サービス作成 |

### ドキュメント

| ファイル | 説明 |
|---|---|
| [`users-guide/04-AppDesign-Batch.md`](./04-AppDesign-Batch.md) | ABD ワークフロー詳細運用ドキュメント |
| [`docs/batch/batch-agent-common-patterns.md`](../batch/batch-agent-common-patterns.md) | Batch Agent 共通パターン集 |
| [`AGENTS.md`](../AGENTS.md) | リポジトリ全体の Copilot Agent 運用ルール |
| [`work/Issue-20260306-batch-implementation-workflow-plan/contracts/asset-inventory.md`](../work/Issue-20260306-batch-implementation-workflow-plan/contracts/asset-inventory.md) | GitHub 運用資産 棚卸し & 命名規約 |
