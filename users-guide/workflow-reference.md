# ワークフロー・ラベル・Custom Agent リファレンス

← [README](../README.md)

---

## 目次

- [ワークフロー一覧](#ワークフロー一覧)
- [ワークフロートリガー系ラベル](#ワークフロートリガー系ラベル)
- [モデル選択ルール](#モデル選択ルール)
- [Custom Agent 一覧](#custom-agent-一覧)
- [Issue テンプレート一覧](#issue-テンプレート一覧)

---

## ワークフロー一覧

`.github/workflows/` 配下の全ワークフローです。

| ファイル名 | 用途 | トリガー |
|-----------|------|---------|
| `auto-app-selection.yml` | アプリケーションアーキテクチャ設計（AAS）オーケストレーター | `auto-app-selection` ラベル付き Issue |
| `auto-app-design.yml` | アプリケーション設計（AAD）オーケストレーター | `auto-app-design` ラベル付き Issue |
| `auto-app-dev-microservice-azure.yml` | マイクロサービス実装（ASDW）オーケストレーター | `auto-app-dev-microservice` ラベル付き Issue |
| `auto-batch-design.yml` | バッチ設計（ABD）オーケストレーター | `auto-batch-design` ラベル付き Issue |
| `auto-batch-dev.yml` | バッチ実装（ABDV）オーケストレーター | `auto-batch-dev` ラベル付き Issue |
| `auto-app-documentation.yml` | Source Codeからのドキュメント作成（ADOC）オーケストレーター | `auto-app-documentation` ラベル付き Issue |
| `auto-knowledge-management.yml` | Knowledge Management（AKM）オーケストレーター（qa / original-docs / both） | `knowledge-management` ラベル付き Issue |
| `auto-aqod.yml` | AQOD 原本ドキュメント質問票生成（AQOD）オーケストレーター | `qa-original-docs` ラベル付き Issue |
| `create-subissues-from-pr.yml` | `subissues.md` から Sub Issue を自動作成 | `create-subissues` ラベル付き PR |
| `advance-subissues.yml` | Sub Issue の完了後に次の Sub Issue を Copilot に自動アサイン | PR クローズ |
| `link-copilot-pr-to-issue.yml` | Copilot が作成した PR を親 Issue にリンク | PR オープン |
| `copilot-auto-review.yml` | Copilot に敵対的レビューを自動依頼 | `auto-context-review` ラベル付き PR |
| `copilot-auto-qa.yml` | Copilot に質問票作成を自動依頼 | `auto-qa` ラベル付き PR |
| `auto-qa-default-answer.yml` | QA 質問票への既定値回答を自動投稿 | Copilot 質問票コメント作成後（`issue_comment.created`） |
| `post-qa-to-pr-comment.yml` | QA 結果を PR コメントに投稿 | PR プッシュ（`pull_request_target.synchronize`）かつ `auto-qa` ラベル付き PR 等の条件 |
| `auto-qa-to-review-transition.yml` | `auto-qa` 完了後に `auto-context-review` へ自動遷移 | PR コメント |
| `auto-review-to-approve-transition.yml` | レビュー完了検知 → `auto-approve-ready` 自動付与 | PR 更新（synchronize）/ PR コメント（Copilot レビュー回答検知） |
| `auto-draft-to-ready.yml` | Copilot PR の Draft → Ready 自動遷移 | `auto-approve-ready` ラベル付き draft PR でデバウンス完了時 |
| `auto-approve-and-merge.yml` | PR 自動 Approve & Auto-merge | `auto-approve-ready` ラベル付き PR（非 draft, 非 split-mode） |
| `sync-issue-labels-to-pr.yml` | 親 Issue のラベルを PR に同期 | Issue ラベル変更 |
| `label-split-mode.yml` | `[WIP]` タイトルの PR に `split-mode` ラベルを付与 | PR オープン / 編集 |
| `check-split-mode.yml` | `split-mode` PR での実装ファイル変更を検知・警告 | PR プッシュ |
| `validate-plan.yml` | `plan.md` のフォーマット・分割判定を検証 | PR プッシュ |
| `audit-plans.yml` | plan.md の監査（全 plan.md のメタデータ違反スキャン／Skill `task-dag-planning` 準拠チェック） | 毎週月曜 3:00 UTC / 手動 |
| `validate-knowledge.yml` | knowledge ドキュメントの検証 | `knowledge/D??-*.md` の PR / push / 手動 |
| `setup-labels.yml` | ラベル初期セットアップ（`.github/labels.json` から一括作成・更新） | `setup-labels` ラベル付き Issue / `workflow_dispatch` |
| `auto-self-improve-close.yml` | Self-Improve Issue 自動クローズ（PR マージ時に `self-improve` ラベル付き Issue を対象に、`auto-merge` 有効かつ Sub Issue 全完了チェックなどの条件を満たす場合にクローズ） | PR マージ |
| `sync-azure-skills.yml` | microsoft/skills から Azure Skills を定期同期 | 毎週月曜 9:00 UTC / 手動 |
| `copilot-setup-steps.yml` | Copilot cloud agent の実行前セットアップ | Copilot cloud agent 起動時 |
| `test-cli-scripts.yml` | `.github/scripts/` の CLI スクリプトをテスト | PR プッシュ |
| `validate-agents.yml` | Agent ファイルの検証 | `push` / `pull_request` |
| `validate-skills.yml` | Skills ファイルの検証 | `pull_request` |

### SDK 版ワークフロー ID（逆引き）

| ワークフロー ID | 対応ワークフロー | GitHub ワークフローファイル |
|--------------|--------------|--------------------------|
| `aas` | App Architecture Design | `auto-app-selection.yml` |
| `aad` | App Design | `auto-app-design.yml` |
| `asdw` | App Dev Microservice Azure | `auto-app-dev-microservice-azure.yml` |
| `abd` | Batch Design | `auto-batch-design.yml` |
| `abdv` | Batch Dev | `auto-batch-dev.yml` |
| `akm` | Knowledge Management（QA + original-docs） | `auto-knowledge-management.yml` |
| `adoc` | Source Codeからのドキュメント作成 | `auto-app-documentation.yml` |
| `aqod` | QA Original Docs | `auto-aqod.yml` |

> **注意**: SDK 版コマンドで `--workflow asd` は無効です。正しいワークフロー ID は上記の `aas` / `aad` / `asdw` / `abd` / `abdv` / `akm` / `adoc` / `aqod` を使用してください。
>
> `akm` / `aqod` / `adoc` は本リポジトリの中核的特徴（`knowledge/` を介した要求定義一元管理）を担うワークフローです。

---

## ワークフロートリガー系ラベル

以下のラベルを GitHub リポジトリに事前に作成してください。

| ラベル名 | 役割 |
|---------|------|
| `auto-app-selection` | **アプリケーションアーキテクチャ設計ワークフロー（AAS）の起動トリガー**。Issue にこのラベルが付与されると、AAS オーケストレーターが起動し、Sub Issue を自動生成して Copilot にアサインする |
| `auto-app-design` | **アプリケーション設計ワークフロー（AAD）の起動トリガー**。Issue にこのラベルが付与されると、AAD オーケストレーターが起動し、Step.1〜7.3 の Sub Issue を自動生成して Copilot にアサインする |
| `auto-app-dev-microservice` | **マイクロサービス開発ワークフローの起動トリガー**。Issue にこのラベルが付与されると、ASDW オーケストレーターが起動し、Step.1〜4 の Sub Issue を自動生成して Copilot にアサインする |
| `auto-batch-design` | **バッチ設計ワークフロー（ABD）の起動トリガー**。Issue にこのラベルが付与されると、ABD オーケストレーターが起動し、Step.1.1〜6.3 の Sub Issue を自動生成して Copilot にアサインする |
| `auto-batch-dev` | **バッチ実装ワークフロー（ABDV）の起動トリガー**。Issue にこのラベルが付与されると、ABDV オーケストレーターが起動し、Step.1〜4 の Sub Issue を自動生成して Copilot にアサインする |
| `auto-app-documentation` | **Source Codeからのドキュメント作成ワークフロー（ADOC）の起動トリガー**。Issue にこのラベルが付与されると、ADOC オーケストレーターが起動し、Step.1〜6 の Sub Issue を自動生成して Copilot にアサインする |
| `knowledge-management` | **Knowledge Management ワークフロー（AKM）の起動トリガー**。Issue にこのラベルが付与されると、AKM オーケストレーターが起動し、`[AKM] Step.1: knowledge/ ドキュメント生成・管理` Sub Issue を自動生成して `KnowledgeManager` Agent で Copilot にアサインする。sources（qa/original-docs/both）は Issue Template で選択する。 |
| `create-subissues` | **Sub Issue 自動作成のトリガー**。人間が PR にこのラベルを手動付与すると、PR 内の `work/**/subissues.md` をパースして Sub Issue を自動作成する |
| `setup-labels` | **ラベル初期セットアップのトリガー**。Issue にこのラベルが付与されると `.github/labels.json` に定義された全ラベルがリポジトリに自動作成・更新される。リポジトリ作成後に1度実行する想定だが、ラベル定義変更時は再実行可能（冪等設計）。Actions タブの `workflow_dispatch` からも手動実行可能。 |
| `split-mode` | **分割モード PR の識別ラベル**。`label-split-mode.yml` が `work/**/plan.md` に `SPLIT_REQUIRED` を検知した場合に PR に自動付与する。`check-split-mode.yml` がこのラベル付き PR の実装ファイル混入を検知・警告する。 |
| `plan-only` | **plan.md のみの PR 識別ラベル**。`label-split-mode.yml` が `split-mode` と同時に付与する。plan.md + subissues.md のみを含む PR であることを示す。 |
| `auto-context-review` | **Copilot 敵対的レビューのトリガー**。PR にこのラベルが付いた状態で PR が ready（非 draft）になると、Copilot に敵対的レビュー指示コメントを自動投稿する |
| `auto-qa` | **Copilot 質問票作成のトリガー**。PR にこのラベルが付いた状態で PR が ready（非 draft）になると、Copilot に選択式の質問票作成指示コメントを自動投稿する |
| `auto-approve-ready` | **PR 自動 Approve & Auto-merge のトリガー**。PR にこのラベルが付いた状態で PR が ready（非 draft, 非 split-mode）になると、`auto-approve-and-merge.yml` が自動発火し、PR の Approve と squash merge を実行する。各オーケストレーターが `auto-merge: true` 設定時に自動付与する |
| `qa-original-docs` | **AQOD ワークフロー（原本ドキュメント質問票生成）の起動トリガー**。Issue にこのラベルが付与されると、AQOD オーケストレーターが起動し、`original-docs/` の原本ドキュメントに対する質問票を自動生成します。 |
| `self-improve` | **自己改善ループの識別ラベル**。Issue テンプレートから Copilot を直接アサインして使用します。`auto-self-improve-close.yml` は、PR マージ時にこのラベルを持つ Issue を検知し、auto-merge 有効判定や Sub Issue 完了確認などの条件を満たした場合に自動クローズします（条件未達時はスキップされることがあります）。 |

> [!IMPORTANT]
> GitHub の Issue Template の `labels:` フィールドは、**リポジトリに既に存在するラベルのみ**を Issue に自動付与します。ラベルが存在しない場合、Issue 作成時にラベルの自動付与はサイレントにスキップされます。各ワークフローを使用する前に、必要なラベルを事前に作成してください。
> 特に、`.github/workflows/label-split-mode.yml` で使用する `split-mode` / `plan-only` ラベルも事前に存在している必要があります。**Setup Labels ワークフロー**（Actions タブ → Setup Labels → Run workflow）を実行すると、これらを含む上記の全ラベルを自動作成できます。必要に応じて、リポジトリ設定画面の **Settings → Labels** から手動作成することも可能です。
>
> **⚠️ 初回セットアップ時の注意（鶏と卵問題）:** 新規リポジトリには `setup-labels` ラベル自体がまだ存在しないため、Issue テンプレートからではなく **Actions タブから `Setup Labels` ワークフローを手動実行**する必要があります（Actions タブ → 左サイドバーの「Setup Labels」→「Run workflow」）。手動実行の前に **Settings → Actions → General → Workflow permissions** を「**Read and write permissions**」に設定してください。
>
> 詳細な手順は [getting-started.md の Step.5](./getting-started.md#step5-ラベル設定) を参照してください。

---

### ステートラベル（各オーケストレーターが自動管理）

以下のラベルは各オーケストレーターワークフローが自己 bootstrap（初回自動作成）し、状態遷移を管理します。
`labels.json`（Setup Labels）の管理対象外です。

| プレフィックス | ワークフロー | bootstrap 箇所 |
|-------------|------------|---------------|
| `aas:*` | `auto-app-selection.yml` | ワークフロー内 bootstrap ステップ |
| `aad:*` | `auto-app-design.yml` | ワークフロー内 bootstrap ステップ |
| `asdw:*` | `auto-app-dev-microservice-azure.yml` | ワークフロー内 bootstrap ステップ |
| `abd:*` | `auto-batch-design.yml` | ワークフロー内 bootstrap ステップ |
| `abdv:*` | `auto-batch-dev.yml` | ワークフロー内 bootstrap ステップ |
| `adoc:*` | `auto-app-documentation.yml` | ワークフロー内 bootstrap ステップ |
| `akm:*` | `auto-knowledge-management.yml` | ワークフロー内 bootstrap ステップ |
| `aqod:*` | `auto-aqod.yml` | ワークフロー内 bootstrap ステップ |

各プレフィックスには以下の 5 状態があります:

| サフィックス | 意味 |
|------------|------|
| `:initialized` | 初期化開始済み（重複実行防止。Sub Issue 生成前に付与される場合あり） |
| `:ready` | 実行待ち（依存解決済み、Copilot アサイン前） |
| `:running` | Copilot 実行中 |
| `:done` | Step 完了（次 Step の起動トリガー） |
| `:blocked` | 依存先未完了でブロック中 |

---

## モデル選択ルール

- 選択肢: `Auto` / `claude-opus-4.7` / `claude-opus-4.6` / `claude-sonnet-4.6` / `gpt-5.4` / `gpt-5.3-codex` / `gemini-2.5-pro`
- `Auto` または空文字は `claude-opus-4.7` として解決
- 指定モデルが API 未対応の場合は `Auto`（既定）に戻して再実行
- Sub-Issue には `model/*` ラベルでモデル指定を伝播
- モデル ID は Copilot CLI の `/model` 表示に合わせてドット区切りを使用（例: `claude-opus-4.7`, `claude-opus-4.6`）

---

## Custom Agent 一覧

`.github/agents/` 配下の **65** Custom Agent を、以下にカテゴリ別で整理します。

### 全体俯瞰図

![全Custom Agentと8ワークフローおよびSelf-Improveループの関係俯瞰図](./images/agent-ecosystem-overview.svg)

### ワークフロー別チェーン図

- AAS: [chain-aas.svg](./images/chain-aas.svg)
- AAD: [chain-aad.svg](./images/chain-aad.svg)
- ASDW: [chain-asdw.svg](./images/chain-asdw.svg)
- ABD: [chain-abd.svg](./images/chain-abd.svg)
- ABDV: [chain-abdv.svg](./images/chain-abdv.svg)
- AKM: [chain-akm.svg](./images/chain-akm.svg)
- AQOD: [chain-aqod.svg](./images/chain-aqod.svg)
- ADOC: [chain-adoc.svg](./images/chain-adoc.svg)
- Self-Improve: [chain-self-improve.svg](./images/chain-self-improve.svg)
- Workflow interconnection: [workflow-interconnection.svg](./images/workflow-interconnection.svg)




### Custom Agent 入出力クイックマップ（定義ファイル抽出）

| Agent 名 | 区分 | 主入力 | 主出力 | knowledge/ 参照 |
|---|---|---|---|---|
| `Arch-AIAgentDesign` | Arch | `docs/catalog/use-case-catalog.md、docs/catalog/domain-analytics.md` | `docs/agent/agent-application-definition.md、docs/agent/agent-architecture.md` | `knowledge/D05-ユースケース-シナリオカタログ.md、knowledge/D06-業務ルール-判定表仕様書.md` |
| `Arch-ApplicationAnalytics` | Arch | `docs/catalog/use-case-catalog.md、knowledge/D01-事業意図-成功条件定義書.md` | `docs/catalog/app-catalog.md` | `knowledge/D01-事業意図-成功条件定義書.md、knowledge/D02-スコープ-対象境界定義書.md` |
| `Arch-ArchitectureCandidateAnalyzer` | Arch | `docs/catalog/app-catalog.md、docs/architectural-requirements-app-xx.md` | `docs/catalog/app-arch-catalog.md、{WORK}plan.md` | `knowledge/D01-事業意図-成功条件定義書.md、knowledge/D02-スコープ-対象境界定義書.md` |
| `Arch-Batch-DataModel` | Arch | `docs/batch/batch-domain-analytics.md、docs/batch/batch-data-source-analysis.md` | `docs/batch/batch-domain-analytics.md、docs/batch/batch-data-source-analysis.md` | `knowledge/D07-用語集-ドメインモデル定義書.md、knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` |
| `Arch-Batch-DataSourceAnalysis` | Arch | `docs/catalog/use-case-catalog.md、docs/catalog/data-model.md` | `docs/catalog/use-case-catalog.md、docs/catalog/data-model.md` | `knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md、knowledge/D10-API-Event-File-連携契約パック.md` |
| `Arch-Batch-DomainAnalytics` | Arch | `docs/catalog/use-case-catalog.md、docs/usecase/` | `docs/catalog/use-case-catalog.md、docs/usecase/` | `knowledge/D04-業務プロセス仕様書.md、knowledge/D05-ユースケース-シナリオカタログ.md` |
| `Arch-Batch-JobCatalog` | Arch | `docs/batch/batch-domain-analytics.md、docs/batch/batch-data-source-analysis.md` | `docs/batch/batch-domain-analytics.md、docs/batch/batch-data-source-analysis.md` | `knowledge/D04-業務プロセス仕様書.md、knowledge/D05-ユースケース-シナリオカタログ.md` |
| `Arch-Batch-JobSpec` | Arch | `docs/batch/batch-service-catalog.md、docs/batch/batch-job-catalog.md` | `docs/batch/batch-service-catalog.md、docs/batch/batch-job-catalog.md` | `knowledge/D04-業務プロセス仕様書.md、knowledge/D05-ユースケース-シナリオカタログ.md` |
| `Arch-Batch-MonitoringDesign` | Arch | `docs/batch/batch-service-catalog.md、docs/batch/batch-job-catalog.md` | `docs/batch/batch-service-catalog.md、docs/batch/batch-job-catalog.md` | `knowledge/D15-非機能-運用-監視-DR-仕様書.md` |
| `Arch-Batch-ServiceCatalog` | Arch | `docs/batch/batch-job-catalog.md、docs/batch/batch-data-model.md` | `docs/batch/batch-job-catalog.md、docs/batch/batch-data-model.md` | `knowledge/D05-ユースケース-シナリオカタログ.md、knowledge/D09-システムコンテキスト-責任境界-再利用方針書.md` |
| `Arch-Batch-TDD-TestSpec` | Arch | `docs/batch/batch-test-strategy.md、docs/batch/batch-service-catalog.md` | `docs/batch/batch-test-strategy.md、docs/batch/batch-service-catalog.md` | `knowledge/D05-ユースケース-シナリオカタログ.md、knowledge/D06-業務ルール-判定表仕様書.md` |
| `Arch-Batch-TestStrategy` | Arch | `docs/batch/batch-service-catalog.md、docs/batch/batch-data-model.md` | `docs/batch/batch-service-catalog.md、docs/batch/batch-data-model.md` | `knowledge/D05-ユースケース-シナリオカタログ.md、knowledge/D06-業務ルール-判定表仕様書.md` |
| `Arch-DataCatalog` | Arch | `docs/catalog/data-model.md、docs/catalog/domain-analytics.md` | `docs/catalog/data-catalog.md、{WORK}work-status.md` | `knowledge/D07-用語集-ドメインモデル定義書.md、knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` |
| `Arch-DataModeling` | Arch | `docs/catalog/domain-analytics.md、docs/catalog/service-catalog.md` | `docs/catalog/data-model.md、data/sample-data.json` | `knowledge/D07-用語集-ドメインモデル定義書.md、knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` |
| `Arch-ImprovementPlanner` | Arch | `{WORK}../QA-CodeQualityScan/artifacts/scan-result.json、knowledge/D15-非機能-運用-監視-DR-仕様書.md` | `{WORK}plan.md、.github/skills/planning/task-dag-planning/references/plan-template.md` | `knowledge/D15-非機能-運用-監視-DR-仕様書.md、knowledge/D17-品質保証-UAT-受入パッケージ.md` |
| `Arch-Microservice-DomainAnalytics` | Arch | `docs/catalog/use-case-catalog.md、docs/catalog/domain-analytics.md` | `docs/catalog/use-case-catalog.md、docs/catalog/domain-analytics.md` | `knowledge/D04-業務プロセス仕様書.md、knowledge/D05-ユースケース-シナリオカタログ.md` |
| `Arch-Microservice-ServiceCatalog` | Arch | `docs/catalog/service-catalog.md、docs/catalog/use-case-catalog.md、docs/catalog/domain-analytics.md` | `docs/catalog/service-catalog-matrix.md、docs/service-catalog-app-01.md、{WORK}plan.md（分割時のみ）、{WORK}subissues.md（分割時のみ）` | `knowledge/D05-ユースケース-シナリオカタログ.md、knowledge/D07-用語集-ドメインモデル定義書.md` |
| `Arch-Microservice-ServiceDetail` | Arch | `docs/catalog/service-catalog*.md` | `docs/services/{serviceId}-description.md、{WORK}work-status.md` | `knowledge/D05-ユースケース-シナリオカタログ.md、knowledge/D06-業務ルール-判定表仕様書.md` |
| `Arch-Microservice-ServiceIdentify` | Arch | `docs/catalog/use-case-catalog.md、docs/catalog/domain-analytics.md` | `docs/catalog/service-catalog.md、{WORK}microservice-modeling-work-status.md` | `knowledge/D04-業務プロセス仕様書.md、knowledge/D05-ユースケース-シナリオカタログ.md` |
| `Arch-TDD-TestSpec` | Arch | `—` | `docs/test-specs/` | `knowledge/D05-ユースケース-シナリオカタログ.md、knowledge/D06-業務ルール-判定表仕様書.md` |
| `Arch-TDD-TestStrategy` | Arch | `—` | `docs/catalog/test-strategy.md、knowledge/D05-ユースケース-シナリオカタログ.md` | `knowledge/D05-ユースケース-シナリオカタログ.md、knowledge/D06-業務ルール-判定表仕様書.md` |
| `Arch-UI-Detail` | Arch | `docs/catalog/screen-catalog.md、docs/catalog/app-catalog.md` | `—` | `knowledge/D05-ユースケース-シナリオカタログ.md、knowledge/D06-業務ルール-判定表仕様書.md` |
| `Arch-UI-List` | Arch | `docs/catalog/domain-analytics.md、docs/catalog/service-catalog.md` | `docs/catalog/screen-catalog.md、{WORK}screen-modeling-work-status.md` | `knowledge/D05-ユースケース-シナリオカタログ.md、knowledge/D11-画面-UX-操作意味仕様書.md` |
| `Dev-Batch-Deploy` | Dev | `docs/batch/batch-service-catalog.md、docs/batch/batch-job-catalog.md` | `docs/batch/batch-service-catalog.md、docs/batch/batch-job-catalog.md` | `knowledge/D15-非機能-運用-監視-DR-仕様書.md、knowledge/D20-セキュア設計-実装ガードレール.md` |
| `Dev-Batch-ServiceCoding` | Dev | `docs/batch/jobs/{jobId}-{jobNameSlug}-spec.md、docs/test-specs/{jobId}-test-spec.md` | `docs/batch/jobs/{jobId}-{jobNameSlug}-spec.md、docs/test-specs/{jobId}-test-spec.md` | `knowledge/D04-業務プロセス仕様書.md、knowledge/D06-業務ルール-判定表仕様書.md` |
| `Dev-Batch-TestCoding` | Dev | `docs/test-specs/{jobId}-test-spec.md、docs/batch/batch-test-strategy.md` | `docs/test-specs/{jobId}-test-spec.md、docs/batch/batch-test-strategy.md` | `knowledge/D06-業務ルール-判定表仕様書.md、knowledge/D17-品質保証-UAT-受入パッケージ.md` |
| `Dev-Microservice-Azure-AddServiceDeploy` | Dev | `{WORK}plan.md、docs/azure/azure-services-additional.md` | `infra/azure/create-azure-additional-resources-prep.sh、infra/azure/create-azure-additional-resources/create.sh` | `knowledge/D10-API-Event-File-連携契約パック.md、knowledge/D15-非機能-運用-監視-DR-仕様書.md` |
| `Dev-Microservice-Azure-AddServiceDesign` | Dev | `—` | `docs/azure/azure-services-additional.md` | `knowledge/D09-システムコンテキスト-責任境界-再利用方針書.md、knowledge/D10-API-Event-File-連携契約パック.md` |
| `Dev-Microservice-Azure-AgentCoding` | Dev | `—` | `knowledge/D06-業務ルール-判定表仕様書.md、knowledge/D10-API-Event-File-連携契約パック.md` | `knowledge/D06-業務ルール-判定表仕様書.md、knowledge/D10-API-Event-File-連携契約パック.md` |
| `Dev-Microservice-Azure-AgentDeploy` | Dev | `—` | `knowledge/D15-非機能-運用-監視-DR-仕様書.md、knowledge/D18-Prompt-ガバナンス-入力統制パック.md` | `knowledge/D15-非機能-運用-監視-DR-仕様書.md、knowledge/D18-Prompt-ガバナンス-入力統制パック.md` |
| `Dev-Microservice-Azure-AgentTestCoding` | Dev | `—` | `knowledge/D06-業務ルール-判定表仕様書.md、knowledge/D17-品質保証-UAT-受入パッケージ.md` | `knowledge/D06-業務ルール-判定表仕様書.md、knowledge/D17-品質保証-UAT-受入パッケージ.md` |
| `Dev-Microservice-Azure-ComputeDeploy-AzureFunctions` | Dev | `—` | `knowledge/D15-非機能-運用-監視-DR-仕様書.md、knowledge/D19-ソフトウェアアーキテクチャ-ADR-パック.md` | `knowledge/D15-非機能-運用-監視-DR-仕様書.md、knowledge/D19-ソフトウェアアーキテクチャ-ADR-パック.md` |
| `Dev-Microservice-Azure-ComputeDesign` | Dev | `—` | `{WORK}artifacts/` | `knowledge/D09-システムコンテキスト-責任境界-再利用方針書.md、knowledge/D15-非機能-運用-監視-DR-仕様書.md` |
| `Dev-Microservice-Azure-DataDeploy` | Dev | `.github/workflows/copilot-setup-steps.yml、{WORK}work-status.md` | `—` | `knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md、knowledge/D13-セキュリティ-プライバシー-監査-法規マトリクス.md` |
| `Dev-Microservice-Azure-DataDesign` | Dev | `docs/catalog/data-model.md、docs/catalog/service-catalog.md` | `docs/azure/azure-services-data.md、{WORK}data-azure-design-work-status.md` | `knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md、knowledge/D13-セキュリティ-プライバシー-監査-法規マトリクス.md` |
| `Dev-Microservice-Azure-ServiceCoding-AzureFunctions` | Dev | `—` | `knowledge/D06-業務ルール-判定表仕様書.md、knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` | `knowledge/D06-業務ルール-判定表仕様書.md、knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` |
| `Dev-Microservice-Azure-ServiceTestCoding` | Dev | `—` | `knowledge/D06-業務ルール-判定表仕様書.md、knowledge/D17-品質保証-UAT-受入パッケージ.md` | `knowledge/D06-業務ルール-判定表仕様書.md、knowledge/D17-品質保証-UAT-受入パッケージ.md` |
| `Dev-Microservice-Azure-UICoding` | Dev | `—` | `—` | `knowledge/D06-業務ルール-判定表仕様書.md、knowledge/D11-画面-UX-操作意味仕様書.md` |
| `Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps` | Dev | `—` | `knowledge/D15-非機能-運用-監視-DR-仕様書.md、knowledge/D20-セキュア設計-実装ガードレール.md` | `knowledge/D15-非機能-運用-監視-DR-仕様書.md、knowledge/D20-セキュア設計-実装ガードレール.md` |
| `Dev-Microservice-Azure-UITestCoding` | Dev | `—` | `knowledge/D06-業務ルール-判定表仕様書.md、knowledge/D11-画面-UX-操作意味仕様書.md` | `knowledge/D06-業務ルール-判定表仕様書.md、knowledge/D11-画面-UX-操作意味仕様書.md` |
| `Doc-APISpec` | Doc | `—` | `docs-generated/components/api-spec.md` | `—` |
| `Doc-ArchOverview` | Doc | `—` | `docs-generated/architecture/overview.md` | `—` |
| `Doc-CICDSummary` | Doc | `.github/workflows/*.yml` | `docs-generated/files/{relative-path}.md` | `—` |
| `Doc-ComponentDesign` | Doc | `docs-generated/files/*.md` | `docs-generated/components/{component}.md` | `—` |
| `Doc-ComponentIndex` | Doc | `docs-generated/components/*.md` | `docs-generated/component-index.md` | `—` |
| `Doc-ConfigSummary` | Doc | `—` | `docs-generated/files/{relative-path}.md` | `—` |
| `Doc-DataModel` | Doc | `—` | `docs-generated/components/data-model.md` | `—` |
| `Doc-DependencyMap` | Doc | `—` | `docs-generated/architecture/dependency-map.md` | `—` |
| `Doc-FileInventory` | Doc | `—` | `docs-generated/inventory.md` | `—` |
| `Doc-FileSummary` | Doc | `docs-generated/inventory.md` | `docs-generated/files/{relative-path}.md` | `—` |
| `Doc-InfraDeps` | Doc | `—` | `docs-generated/architecture/infra-deps.md` | `—` |
| `Doc-LargeFileSummary` | Doc | `—` | `docs-generated/files/{relative-path}.md` | `—` |
| `Doc-Migration` | Doc | `—` | `docs-generated/guides/migration-assessment.md` | `—` |
| `Doc-NFRAnalysis` | Doc | `—` | `docs-generated/architecture/nfr-analysis.md` | `—` |
| `Doc-Onboarding` | Doc | `—` | `docs-generated/guides/onboarding.md` | `—` |
| `Doc-Refactoring` | Doc | `—` | `docs-generated/guides/refactoring.md` | `—` |
| `Doc-TechDebt` | Doc | `—` | `docs-generated/components/tech-debt.md` | `—` |
| `Doc-TestSpecSummary` | Doc | `—` | `docs-generated/components/test-spec-summary.md` | `—` |
| `Doc-TestSummary` | Doc | `—` | `docs-generated/files/{relative-path}.md` | `—` |
| `KnowledgeManager` | Knowledge | `qa/*.md、original-docs/*` | `knowledge/business-requirement-document-status.md、knowledge/D{NN}-*.md` | `knowledge/business-requirement-document-status.md、knowledge/D{NN}-*.md` |
| `QA-AzureArchitectureReview` | QA | `docs/usecase-detail.md、docs/catalog/service-catalog-matrix.md` | `docs/azure/azure-architecture-review-report.md` | `knowledge/D09-システムコンテキスト-責任境界-再利用方針書.md、knowledge/D13-セキュリティ-プライバシー-監査-法規マトリクス.md` |
| `QA-AzureDependencyReview` | QA | `docs/catalog/service-catalog-matrix.md、docs/catalog/app-catalog.md` | `docs/azure/dependency-review-report.md` | `knowledge/D09-システムコンテキスト-責任境界-再利用方針書.md、knowledge/D10-API-Event-File-連携契約パック.md` |
| `QA-CodeQualityScan` | QA | `knowledge/D17-品質保証-UAT-受入パッケージ.md、knowledge/D20-セキュア設計-実装ガードレール.md` | `{WORK}artifacts/scan-result.json、{WORK}artifacts/scan-summary.md` | `knowledge/D17-品質保証-UAT-受入パッケージ.md、knowledge/D20-セキュア設計-実装ガードレール.md` |
| `QA-DocConsistency` | QA | `knowledge/D07-用語集-ドメインモデル定義書.md` | `{WORK}artifacts/doc-consistency-report.md` | `knowledge/D07-用語集-ドメインモデル定義書.md` |
| `QA-PostImproveVerify` | QA | `knowledge/D17-品質保証-UAT-受入パッケージ.md、knowledge/D20-セキュア設計-実装ガードレール.md` | `{WORK}verification-report.md` | `knowledge/D17-品質保証-UAT-受入パッケージ.md、knowledge/D20-セキュア設計-実装ガードレール.md` |
### ビジネス分析・要求定義（2）

| Agent 名 | 用途 |
|---------|------|
| `Arch-ApplicationAnalytics` | ユースケースから実装手段を仕分け・アプリリスト・MVP 選出 |
| `Arch-ArchitectureCandidateAnalyzer` | 各アプリの非機能要件に基づき最良のアーキテクチャを選定 |

### アーキテクチャ設計 — 共通（2）

| Agent 名 | 用途 |
|---------|------|
| `Arch-DataModeling` | ユースケースから全エンティティ・サービス境界・データモデルを生成 |
| `Arch-DataCatalog` | 概念データモデルと物理テーブルのマッピングを記録するデータカタログ生成 |

### アーキテクチャ設計 — Microservice（4）

| Agent 名 | 用途 |
|---------|------|
| `Arch-Microservice-DomainAnalytics` | DDD 観点でドメイン分析（Bounded Context / ユビキタス言語 / 集約 / ドメインイベント）を実施 |
| `Arch-Microservice-ServiceIdentify` | ドメイン分析からマイクロサービス候補を抽出し service-list.md を作成 |
| `Arch-Microservice-ServiceCatalog` | 画面→機能→API→SoT データのマッピングを service-catalog.md に作成 |
| `Arch-Microservice-ServiceDetail` | 全サービスのマイクロサービス詳細仕様（API / イベント / データ / セキュリティ）を作成 |

### アーキテクチャ設計 — UI（2）

| Agent 名 | 用途 |
|---------|------|
| `Arch-UI-List` | 画面一覧（表）と画面遷移図（Mermaid）を設計し screen-list.md を作成 |
| `Arch-UI-Detail` | 全画面の実装用画面定義書（UX / A11y / セキュリティ含む）を docs/screen/ に生成 |

### アーキテクチャ設計 — Batch（7）

| Agent 名 | 用途 |
|---------|------|
| `Arch-Batch-DomainAnalytics` | バッチ DDD 観点ドメイン分析（BC / 冪等性 / チェックポイント）を作成 |
| `Arch-Batch-DataSourceAnalysis` | バッチデータソース / デスティネーション分析（スキーマ / 変換 / SLA）を作成 |
| `Arch-Batch-DataModel` | バッチ 4 層データモデル・冪等性キー・パーティション・ER 図を設計 |
| `Arch-Batch-JobCatalog` | バッチジョブ設計（一覧 / 依存 DAG / スケジュール / リトライ）を作成 |
| `Arch-Batch-JobSpec` | バッチジョブ詳細仕様書を docs/batch/jobs/{jobId}-{jobNameSlug}-spec.md に作成 |
| `Arch-Batch-ServiceCatalog` | バッチジョブサービスカタログを docs/batch/batch-service-catalog.md に作成 |
| `Arch-Batch-MonitoringDesign` | バッチ処理監視・運用設計書を docs/batch/batch-monitoring-design.md に作成 |

### アーキテクチャ設計 — AI Agent（1）

| Agent 名 | 用途 |
|---------|------|
| `Arch-AIAgentDesign` | AI Agent のアプリケーション定義・粒度設計・詳細設計を実施し、docs/ai-agent-catalog.md に出力 |

### アーキテクチャ設計 — 改善（1）

| Agent 名 | 用途 |
|---------|------|
| `Arch-ImprovementPlanner` | コード品質スキャン結果を受け取り、改善計画（DAG + 見積）を策定する[^improvement-planner-phase4b] |

### アーキテクチャ設計 — テスト（4）

| Agent 名 | 用途 |
|---------|------|
| `Arch-TDD-TestStrategy` | サービスカタログ・データモデルから TDD テスト戦略書を docs/catalog/test-strategy.md に生成 |
| `Arch-TDD-TestSpec` | テスト戦略書・画面/サービス定義書から TDD テスト仕様書を docs/test-specs/ に生成 |
| `Arch-Batch-TestStrategy` | バッチ処理テスト戦略書（冪等性 / データ品質 / 障害注入）を docs/batch/batch-test-strategy.md に作成 |
| `Arch-Batch-TDD-TestSpec` | バッチ TDD テスト仕様書をジョブごとに docs/test-specs/{jobId}-test-spec.md に生成 |

### 実装 — Microservice（Azure）（11）

| Agent 名 | 用途 |
|---------|------|
| `Dev-Microservice-Azure-ComputeDesign` | ユースケース内の全マイクロサービスについて最適な Azure コンピュート（ホスティング）を選定 |
| `Dev-Microservice-Azure-DataDesign` | Polyglot Persistence に基づき全エンティティに対する最適 Azure データストアを選定し文書化 |
| `Dev-Microservice-Azure-DataDeploy` | Azure CLI でデータ系サービスを作成し、サンプルデータを変換・一括登録して検証 |
| `Dev-Microservice-Azure-AddServiceDesign` | サービス定義書の外部依存・統合要件から追加で必要な Azure サービスを選定 |
| `Dev-Microservice-Azure-AddServiceDeploy` | Azure 追加サービスを Azure CLI で冪等作成し、AC 検証で完了判定 |
| `Dev-Microservice-Azure-ServiceTestCoding` | TDD RED フェーズのテストコード（失敗するテスト）を test/api/{サービス名}.Tests/ に生成 |
| `Dev-Microservice-Azure-ServiceCoding-AzureFunctions` | マイクロサービス定義書から全サービスの Azure Functions を実装 |
| `Dev-Microservice-Azure-UITestCoding` | 画面別テスト仕様書から TDD RED フェーズの UI テストコードを test/ui/ に生成 |
| `Dev-Microservice-Azure-UICoding` | 画面定義書に基づき全画面の UI を実装し、API クライアント層を整備 |
| `Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps` | Azure Static Web Apps へのデプロイと GitHub Actions による CD 構築 |
| `Dev-Microservice-Azure-ComputeDeploy-AzureFunctions` | 全サービスを Azure Functions 用に作成・デプロイし、GitHub Actions で CI/CD 構築 |

### 実装 — AI Agent（Azure）（3）

| Agent 名 | 用途 |
|---------|------|
| `Dev-Microservice-Azure-AgentTestCoding` | テスト仕様書から TDD RED フェーズのテストコードを test/agent/{AgentName}.Tests/ に生成 |
| `Dev-Microservice-Azure-AgentCoding` | AI Agent 詳細設計書から Azure AI Foundry Agent Service を使用して Agent を実装 |
| `Dev-Microservice-Azure-AgentDeploy` | AI Agent を Azure AI Foundry Agent Service へデプロイし、GitHub Actions で CI/CD 構築 |

### 実装 — Batch（Azure）（3）

| Agent 名 | 用途 |
|---------|------|
| `Dev-Batch-TestCoding` | バッチ TDD テスト仕様書から TDD RED フェーズのテストコードを test/batch/{jobId}-{jobNameSlug}.Tests/ に生成 |
| `Dev-Batch-ServiceCoding` | バッチジョブ詳細仕様書と TDD テスト仕様書に基づき Azure Functions 実装で TDD GREEN を完了 |
| `Dev-Batch-Deploy` | バッチサービスを Azure にデプロイし GitHub Actions CI/CD を構築、AC 検証まで実施 |

### ドキュメント生成（Doc-*）（19）

| Agent 名 | 用途 |
|---------|------|
| `Doc-APISpec` | API 仕様書を生成 |
| `Doc-ArchOverview` | アーキテクチャ概要図を生成 |
| `Doc-CICDSummary` | CI/CD ワークフロー定義ファイルを要約 |
| `Doc-ComponentDesign` | モジュール単位のコンポーネント設計書を作成 |
| `Doc-ComponentIndex` | レイヤー2成果物の要約インデックスを生成 |
| `Doc-ConfigSummary` | 設定・IaC ファイルの構成と依存を要約 |
| `Doc-DataModel` | データモデル定義書を生成 |
| `Doc-DependencyMap` | 依存関係マップを作成し循環依存を検出 |
| `Doc-FileInventory` | 対象ファイルの列挙・言語判定・分割計画を作成 |
| `Doc-FileSummary` | プロダクションコード1ファイルの責務・公開API・依存を要約 |
| `Doc-InfraDeps` | インフラ依存とベンダーロックイン度を分析 |
| `Doc-LargeFileSummary` | 大規模ファイルを分割要約し統合サマリーを作成 |
| `Doc-Migration` | 移行アセスメントを生成 |
| `Doc-NFRAnalysis` | 非機能要件の現状分析を作成 |
| `Doc-Onboarding` | 新規参画者向けオンボーディングガイドを生成 |
| `Doc-Refactoring` | リファクタリングガイドを生成 |
| `Doc-TechDebt` | 技術的負債を集約・分類・優先度付け |
| `Doc-TestSpecSummary` | テスト仕様サマリーを集約 |
| `Doc-TestSummary` | テストコード1ファイルの対象・ケース・モックを要約 |

### QA / レビュー（5）

| Agent 名 | 用途 |
|---------|------|
| `QA-AzureArchitectureReview` | デプロイ済み Azure リソースを棚卸しし、Azure WAF（5 本柱）と Azure Security Benchmark v3 を根拠にアーキテクチャ / セキュリティをレビュー |
| `QA-AzureDependencyReview` | サービスカタログ準拠で Azure 依存（参照 / 設定 / IaC）を証跡付きで点検 |
| `QA-CodeQualityScan` | コードベースの品質スキャンを実行。ruff / pytest --cov / markdownlint の結果を収集しコード品質スコアと改善候補リストを生成。自己改善ループの Phase 4a として使用 |
| `QA-DocConsistency` | docs/ 配下の Markdown ファイルと既存コード・設計文書との整合性を検証し、矛盾・欠落・捏造を検出。自己改善ループの Phase 4a（ドキュメント整合性）として使用 |
| `QA-PostImproveVerify` | 自己改善実行後の品質検証を行う。Skill: harness-verification-loop Verification Loop（5 段階）を実行し、デグレード検知とスコア比較を行う。自己改善ループの Phase 4d として使用 |

### Knowledge Management（1）

| Agent 名 | 用途 |
|---------|------|
| `KnowledgeManager` | AKM ワークフロー（`akm`）で参照される Agent。`qa/` / `original-docs/` / `custom_source_dir` を D01〜D21 に分類し、status/knowledge 更新を行う（`.github/agents/KnowledgeManager.agent.md`）。 |

---


## knowledge/ ディレクトリとの関係

![original-docs/ や qa/ からワークフローを通じて knowledge/ や docs-generated/ に情報が生成・更新される関係図](./images/knowledge-interface-flow.svg)

`knowledge/` フォルダーには業務要件ドキュメント（D01〜D21 の文書クラスのうち、マッピングが存在するもの）が格納されます。これらは `KnowledgeManager` Agent（`knowledge-management` ワークフロー）によって生成・更新されます。

| 情報源 | ワークフロー | 生成先 |
|---|---|---|
| `original-docs/` | `akm` | `knowledge/D01〜D21` |
| `qa/` | `akm` | `knowledge/D01〜D21` |
| `original-docs/` | `aqod` | `qa/`（質問票） |
| `src/` | `adoc` | `docs-generated/` |

設計・開発の全 Custom Agent（`Arch-*`, `Dev-*`, `QA-*`）は、`knowledge/` ファイルが存在する場合に業務コンテキストとして自動参照します。

| knowledge ファイル | 主な参照 Custom Agent |
|------------------|---------------------|
| `knowledge/D01-事業意図-成功条件定義書.md` | `Arch-ApplicationAnalytics`, `Arch-ArchitectureCandidateAnalyzer` |
| `knowledge/D05-ユースケース-シナリオカタログ.md` | `Arch-*` 全般, `Dev-*-ServiceCoding`, `Dev-*-TestCoding` |
| `knowledge/D06-業務ルール-判定表仕様書.md` | `Arch-*`, `Dev-*-ServiceCoding`, `Dev-*-TestCoding`, `Dev-*-UICoding` |
| `knowledge/D07-用語集-ドメインモデル定義書.md` | `Arch-Microservice-DomainAnalytics`, `Arch-DataModeling`, `Arch-DataCatalog` |
| `knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` | `Arch-DataModeling`, `Dev-*-DataDesign`, `Dev-*-DataDeploy` |
| `knowledge/D15-非機能-運用-監視-DR-仕様書.md` | `Dev-*-ComputeDesign`, `Dev-*-ComputeDeploy`, `QA-*` |
| `knowledge/D19-ソフトウェアアーキテクチャ-ADR-パック.md` | `Arch-ArchitectureCandidateAnalyzer`, `Dev-*-ComputeDesign`, `QA-AzureArchitectureReview` |
| `knowledge/D20-セキュア設計-実装ガードレール.md` | `Dev-*-ServiceCoding`, `Dev-*-DataDeploy`, `Dev-*-Deploy`, `QA-*` |

詳細な参照マッピングは各 Custom Agent ファイル（`.github/agents/*.agent.md`）の `knowledge/ 参照（任意・存在する場合のみ）` セクションを参照してください。

## Issue テンプレート一覧

`.github/ISSUE_TEMPLATE/` 配下の全テンプレートです。

| ファイル名 | 用途 | トリガーラベル |
|-----------|------|-------------|
| `app-architecture-design.yml` | アプリケーションアーキテクチャ設計ワークフロー起動 | `auto-app-selection` |
| `app-design.yml` | アプリケーション設計ワークフロー起動 | `auto-app-design` |
| `app-dev-microservice.yml` | マイクロサービス実装ワークフロー起動 | `auto-app-dev-microservice` |
| `batch-design.yml` | バッチ設計ワークフロー起動 | `auto-batch-design` |
| `batch-dev.yml` | バッチ実装ワークフロー起動 | `auto-batch-dev` |
| `sourcecode-to-documentation.yml` | Source Codeからのドキュメント作成ワークフロー起動 | `auto-app-documentation` |
| `knowledge-management.yml` | knowledge ドキュメント管理（qa/original-docs/both） | `knowledge-management` |
| `qa-original-docs.yml` | AQOD 原本質問票生成ワークフロー起動 | `qa-original-docs` |
| `self-improve.yml` | セルフ改善ループの起動 | `self-improve` |
| `setup-labels.yml` | ラベル初期セットアップ | `setup-labels` |

---

## Skills 一覧と Agent-Skills 対応

`.github/skills/` 配下の全 Skills と、主な利用 Agent の対応表です。

### 共通 Skills（全 Agent）

| Skill 名 | パス | 説明 |
|---------|------|------|
| `agent-common-preamble` | `.github/skills/planning/agent-common-preamble/` | 全 Agent 共通ルール・Skills 参照リスト |
| `input-file-validation` | `.github/skills/planning/input-file-validation/` | 必読ファイル確認・欠損時処理 |
| `app-scope-resolution` | `.github/skills/planning/app-scope-resolution/` | APP-ID スコープ解決 |
| `task-questionnaire` | `.github/skills/planning/task-questionnaire/` | 質問票作成 |
| `task-dag-planning` | `.github/skills/planning/task-dag-planning/` | DAG計画・分割判定 |
| `work-artifacts-layout` | `.github/skills/planning/work-artifacts-layout/` | work/ 構造設計 |

### ドメイン Skills

| Skill 名 | パス | 主な利用 Agent |
|---------|------|-------------|
| `architecture-questionnaire` | `.github/skills/planning/architecture-questionnaire/` | `Arch-ArchitectureCandidateAnalyzer` |
| `knowledge-management` | `.github/skills/planning/knowledge-management/` | `KnowledgeManager` |
| `mcp-server-design` | `.github/skills/planning/mcp-server-design/` | MCP Server 設計時 |
| `batch-design-guide` | `.github/skills/planning/batch-design-guide/` | `Arch-Batch-*`, `Dev-Batch-*` |
| `microservice-design-guide` | `.github/skills/planning/microservice-design-guide/` | `Arch-Microservice-*`, `Dev-Microservice-*` |

## APP-ID 指定方法

Issue body または PR body に以下の HTML コメントを含めることで、特定の APP-ID にスコープを絞り込めます：

```html
<!-- app-id: APP-01 -->
```

複数の APP-ID を指定する場合：

```html
<!-- app-id: APP-01, APP-03 -->
```

APP-ID 未指定の場合は全サービス/全画面が対象となります（後方互換）。

[^improvement-planner-phase4b]: QA 自己改善ループ（Self-Improve）の Phase 4b で使用。
