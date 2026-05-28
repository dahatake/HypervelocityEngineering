# Hypervelocity Engineering

> **開発中のテンプレートリポジトリです。** 実装は随時更新されるため、README は「概要 + 導線」に絞り、実体確認できる内容だけを記載しています。

Hypervelocity Engineering（HVE）は、GitHub Copilot cloud agent と `hve` CLI を使って、要求定義・設計・実装・ドキュメント生成を段階実行する Vibe Coding フレームワークです。現在のテンプレート実装は Azure を前提にしています。

## 目次

- [はじめての方へ（3 つの始め方）](#はじめての方へ-3-つの始め方)
- [目的](#目的)
- [全体像](#全体像)
- [技術アーキテクチャ](#技術アーキテクチャ)
- [用語](#用語)
- [方式比較表（4 つの使い方）](#方式比較表4-つの使い方)
- [Issue Template 一覧](#issue-template-一覧)
- [GitHub Actions workflows](#github-actions-workflows)
- [`hve` CLI](#hve-cli)
- [users-guide への導線](#users-guide-への導線)
- [リポジトリ構造](#リポジトリ構造)
- [ライセンス](#ライセンス)

## はじめての方へ (3 つの始め方)

利用したい Orchestrator を選んで、対応する Getting Started を開いてください。いずれもチュートリアル形式で、セットアップからサンプルの起動までをカバーしています。

| Orchestrator | 入口 | Getting Started |
|---|---|---|
| HVE Cloud Agent Orchestrator | GitHub Actions（Issue Template） | [hve-cloud-getting-started.md](users-guide/hve-cloud-getting-started.md) |
| HVE CLI Orchestrator | ローカル端末 `python -m hve cli` | [hve-cli-getting-started.md](users-guide/hve-cli-getting-started.md) |
| HVE GUI Orchestrator | ローカル端末 `python -m hve`（GUI） | [hve-gui-getting-started.md](users-guide/hve-gui-getting-started.md) |

## 目的

このリポジトリの目的は、**業務要件の整理から設計・実装・検証までを、再現可能なワークフローとして運用すること**です。

- GitHub Issues / Issue Template を起点に Web 上で実行する
- `python -m hve` からローカルで同じ Workflow / Prompt を実行する
- `knowledge/` を中核ストアとして、`original-docs/`・`qa/`・既存コードの情報を再利用する

## 全体像

HVE は「タスク定義書（Issue Template / CLI 起動メタデータ）」を入口とし、`hve` Orchestrator が `.github/prompts/` の Prompt を DAG に沿って逐次起動し、`docs/` / `knowledge/` / `src/` / `test/` などの成果物を生成します。

![README 用アーキテクチャ概要図](users-guide/images/readme-architecture-overview.svg)

### 3 段構造

各ワークフローは **(1) 入力ドキュメント → (2) Prompt チェーン → (3) 成果物ファイル** の 3 段で表現されます。上流の成果物が下流ワークフローの入力になるため、「ARD → AAS → AAD-WEB/ADFD/AAG → ASDW-WEB/ADFDV/AAGD」の順で進めるのが標準です。

![README 用 3 段構造フロー図](users-guide/images/readme-3-tier-flow.svg)

### `knowledge/` と `qa/` と `original-docs/` の関係

- `original-docs/`—社内ドキュメント等の **取り込み元（読み取り専用）**。全 Prompt は記述を変更しません。
- `qa/`—`AQOD` や Prompt が生成した **質問票 / 回答** ファイル。
- `knowledge/`—`AKM`（`KnowledgeManager`）が `qa/` / `original-docs/` を読み込んで生成・更新する **確定済みドキュメント（D01〜D21）**。以降の設計・実装ワークフローが業務コンテキストとして参照します。

詳細は [km-guide.md](users-guide/km-guide.md) を参照してください。

## 技術アーキテクチャ

3 つの Orchestrator（Cloud Agent / CLI / GUI）、メッセージフロー、4 ゾーン疎結合境界（HVE Python 制御コード / Copilot CLI SDK / Copilot CLI が管理する MCP・Plugin・Skill・認証 / HVE が管理する Prompt・Workflow・Skill）、認証と資格情報の取扱いを 7 枚の SVG 図と共に詳述したドキュメントを用意しています。

- [users-guide/hve-technical-architecture.md](users-guide/hve-technical-architecture.md)

開発者・運用者で内部構造を把握したい方は最初にこのドキュメントを参照してください。

### 中核となる Workflow ID

`hve/workflow_registry.py` で定義されているオーケストレーション Workflow ID は次の 11 個です。**正の一覧は `workflow_registry.py` を参照**し、`python -m hve orchestrate --help` の例示や後方互換エイリアスよりこちらを優先してください。

| Workflow ID | 役割 | 主な成果物 | 対応ガイド |
|---|---|---|---|
| `ard` | 企業・業務分析からユースケース候補を整理する（ADR-0003 で 7 ステップ。+ 本リリースで任意 Step 2.5「KPI/OKR 定義」を追加） | `docs/catalog/use-case-catalog.md`, `docs/company-business-requirement.md`, `docs/business-requirement.md`, `docs/recommended-kpi-okr.md`（Step 2.5 を `--include-kpi-okr` で有効化時） | [01-business-requirement.md（ARD セクション）](users-guide/01-business-requirement.md#要求定義の自動化ard-auto-requirement-definition) |
| `aas` | アプリケーションアーキテクチャ設計 | `docs/catalog/app-catalog.md` など | [02-app-architecture-design.md](users-guide/02-app-architecture-design.md) |
| `aad-web` | Web / Microservice 設計 | `docs/catalog/screen-catalog.md`, `docs/catalog/service-catalog-matrix.md`, `docs/screen/`, `docs/services/`, `docs/test-specs/` | [03-app-design-microservice-azure.md](users-guide/03-app-design-microservice-azure.md) |
| `asdw-web` | Web / Microservice 実装・デプロイ | `src/`, `src/test/`, Azure リソース関連成果物 | [05-app-dev-microservice-azure.md](users-guide/05-app-dev-microservice-azure.md) |
| `adfd` | Dataflow 設計 | `docs/dataflow/*.md` | [04-app-design-dataflow.md](users-guide/04-app-design-dataflow.md) |
| `adfdv` | Dataflow 実装・デプロイ | `src/`, `src/test/`, `src/infra/azure/dataflow/` など | [06-app-dev-dataflow-azure.md](users-guide/06-app-dev-dataflow-azure.md) |
| `aag` | AI Agent 設計（アプリケーション定義・粒度設計・詳細設計） | `docs/agent/` 配下の Agent 詳細設計書群 | [07-ai-agent-simple.md](users-guide/07-ai-agent-simple.md) |
| `aagd` | AI Agent 詳細設計・実装 | `docs/agent/`, `src/test/agent/`, Azure Agent 関連成果物 | [08-ai-agent.md](users-guide/08-ai-agent.md) |
| `akm` | `qa/` と `original-docs/` から `knowledge/` を生成・更新 | `knowledge/D01〜D21-*.md` | [km-guide.md](users-guide/km-guide.md) |
| `aqod` | `original-docs/` を横断分析して質問票を生成 | `qa/D01〜D21-original-docs-questionnaire.md`, `qa/original-docs-cross-questionnaire.md` | [original-docs-review.md](users-guide/original-docs-review.md) |
| `adoc` | ソースコードから技術ドキュメントを生成 | `docs-generated/` | [sourcecode-documentation.md](users-guide/sourcecode-documentation.md) |

> [!NOTE]
> `aad` / `asdw` は bash 旧実装との parity 照合で使われる旧 ID です（`hve/dag_parity.py` の `DEFAULT_WORKFLOW_ALIASES` 参照）。`hve/__main__.py` のヘルプ例や使用例には `aad` / `asdw` が残りますが、`workflow_registry.py` の canonical な ID は `aad-web` / `asdw-web` で、README では canonical 表記を採用しています。

## 用語

| 用語 | この README での意味 |
|---|---|
| **Prompt** | `.github/prompts/` 配下の再利用 Prompt 定義ファイル（`*.prompt.md`）。例: `Arch-ApplicationAnalytics`, `Dev-Dataflow-FunctionsDeploy`, `QA-DocConsistency`, `KnowledgeManager`。`workflow_registry.py` の各 Step は `custom_agent` フィールドでこの Prompt 名を指定します（フィールド名は歴史的経緯で残置）。 |
| **Workflow** | `hve/workflow_registry.py` の Workflow ID と、それに対応する GitHub Actions ワークフロー群 |
| **Phase** | `users-guide/01`〜`08` と Knowledge / Documentation 系ガイドで区切った利用フェーズ |
| **Chain** | 複数の Workflow / Step を前後関係で束ねた流れ。README では Phase の進行順として扱います |

### Prompt の見方

README では全 Prompt の列挙は行わず、命名規則と代表例だけを示します。完全一覧は [workflow-reference.md](users-guide/workflow-reference.md) を参照してください。

| 系統 | 役割 | 実在する代表例 |
|---|---|---|
| `Arch-*` | 分析・設計 | `Arch-ApplicationAnalytics`, `Arch-Microservice-DomainAnalytics`, `Arch-Dataflow-AppCatalog` |
| `Dev-*` | 実装・デプロイ | `Dev-Microservice-Azure-ServiceCoding-AzureFunctions`, `Dev-Dataflow-DataDeploy`, `Dev-Dataflow-FunctionsDeploy` |
| `Doc-*` | ソースコード由来の技術文書生成 | `Doc-APISpec`, `Doc-ComponentDesign`, `Doc-TechDebt` |
| `QA-*` | 品質確認・レビュー | `QA-CodeQualityScan`, `QA-DocConsistency`, `QA-PostImproveVerify` |
| 固有名 | 例外的な単独 Prompt | `KnowledgeManager`, `E2ETesting-Playwright` |

## 方式比較表（4 つの使い方）

| 方式 | 入口 | 実行場所 | 向いているケース | 参照先 |
|---|---|---|---|---|
| 方式 1 | 個別 Issue に Prompt を手動アサイン | GitHub Actions | 単一タスクの試行、特定 Step のデバッグ | [web-ui-guide.md#方式1-copilot-cloud-agent-手動実行](users-guide/web-ui-guide.md#方式1-copilot-cloud-agent-手動実行) |
| 方式 2 | Issue Template から親 Issue を作成 | GitHub Actions | Sub Issue 自動生成を含むフルオーケストレーション | [web-ui-guide.md#方式2-ワークフローオーケストレーションweb](users-guide/web-ui-guide.md#方式2-ワークフローオーケストレーションweb) |
| 方式 3 | `python -m hve cli` / `python -m hve orchestrate` | PC / Mac / 仮想マシン | GitHub Actions を使わずに同じ DAG をターミナルで実行したい場合 | [hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md) |
| 方式 4 | `python -m hve`（既定）/ `python -m hve gui` | PC / Mac / 仮想マシン | GUI ウィザードでオプションを選択して実行したい場合 | [hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md) |

方式 2 では、Issue 作成後に [`auto-orchestrator-dispatcher.yml`](.github/workflows/auto-orchestrator-dispatcher.yml)（`name: HVE Cloud Agent Orchestrator Dispatcher`）がラベルを見て対象 Workflow を判定し、対応する reusable workflow を起動します。

## Issue Template 一覧

`.github/ISSUE_TEMPLATE/*.yml` に存在する 11 個のテンプレートです。README では「どのフォームを選ぶか」を判断できる粒度だけを記載し、詳細な手順は users-guide に委譲します。

> 自己改善（Self-Improve）は独立の Issue Template を持たず、上記の設計・実装テンプレートの `enable_self_improve` チェックボックスで起動します。

| ファイル | UI 名 (`name`) | 使うとき | 主な入力 |
|---|---|---|---|
| `setup-labels.yml` | `Setup Labels: ラベル初期セットアップ` | リポジトリ作成直後にラベル群を投入・更新したい | `confirm` |
| `app-architecture-design.yml` | `Architecture Design（アーキテクチャ設計）` | ユースケースからアプリ構成を設計したい | `branch`, `runner_type`, `steps`, `model`, `review_model`, `qa_model` |
| `web-app-design.yml` | `Web App Design` | 対象 APP-ID の Web / Microservice 設計を進めたい | `branch`, `runner_type`, `app_ids`, `steps`, `model`, `review_model` |
| `web-app-dev.yml` | `Web App Dev & Deploy` | 対象 APP-ID の Web / Microservice 実装・デプロイを進めたい | `app_ids`, `branch`, `runner_type`, `resource_group`, `steps`, `model` |
| `dataflow-design.yml` | `Dataflow Design` | バッチの設計書を作りたい | `app_ids`, `branch`, `runner_type`, `steps`, `model`, `review_model` |
| `dataflow-dev.yml` | `Dataflow Dev` | バッチを実装・デプロイしたい | `app_ids`, `branch`, `runner_type`, `resource_group`, `app_ids`, `steps` |
| `ai-agent-design.yml` | `AI Agent Design` | AI Agent の設計を開始したい | `app_ids`, `usecase_id`, `branch`, `runner_type`, `steps`, `model` |
| `ai-agent-dev.yml` | `AI Agent Dev & Deploy` | AI Agent の実装・デプロイを進めたい | `app_ids`, `branch`, `runner_type`, `resource_group`, `usecase_id`, `steps` |
| `knowledge-management.yml` | `knowledge/ ドキュメント生成・管理` | `qa/` / `original-docs/` / 追加ソースから `knowledge/` を再構成したい | `branch`, `runner_type`, `sources`, `target_files`, `force_refresh`, `enable_review` |
| `original-docs-review.yml` | `Original Docs Review` | `original-docs/` を分析して質問票を作りたい | `branch`, `runner_type`, `target_scope`, `depth`, `focus_areas`, `enable_review` |
| `sourcecode-to-documentation.yml` | `Source Codeからのドキュメント作成` | 既存コードから技術文書を自動生成したい | `branch`, `runner_type`, `target_dirs`, `exclude_patterns`, `doc_purpose`, `max_file_lines` |

## GitHub Actions workflows

ワークフロー棚卸し結果をもとに、用途別に整理します。

### Orchestrators / dispatchers

このリポジトリのオーケストレーションは以下 3 系統に正式名称を統一しています。

| 正式名称 | 実行場所 | 起動点 | 代表エントリ |
|---|---|---|---|
| **HVE Cloud Agent Orchestrator** | GitHub Actions | Issue Template から作成された Issue の label / state | `.github/workflows/auto-orchestrator-dispatcher.yml`（`name: HVE Cloud Agent Orchestrator Dispatcher`）から各 `auto-*-reusable.yml` を `workflow_call` で起動 |
| **HVE CLI Orchestrator** | PC / Mac / 仮想マシン | ローカル端末での `python -m hve cli` / `python -m hve orchestrate --workflow <id>` | `hve/__main__.py` / `hve/orchestrator.py`。詳細は [hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md) |
| **HVE GUI Orchestrator** | PC / Mac / 仮想マシン | ローカル端末での `python -m hve`（既定）/ `python -m hve gui` | `hve/gui/main_window.py`（PySide6 QWizard）。詳細は [hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md)。多言語対応（日本語 / English）— [hve/gui/i18n/README.md](hve/gui/i18n/README.md) |

- `.github/workflows/auto-orchestrator-dispatcher.yml` — issue-label-driven dispatcher。Issue Template 向け reusable orchestrator を呼び出します。
- `.github/workflows/auto-pr-transition-dispatcher.yml` — PR transition dispatcher。QA/review/create-subissues の transition workflow を呼び出します。

### Reusable issue-template orchestrators
`auto-orchestrator-dispatcher.yml` から呼び出され、Issue Template ラベルと紐づく orchestrator 群です。
- `.github/workflows/auto-app-selection-reusable.yml`
- `.github/workflows/auto-app-detail-design-web-reusable.yml`
- `.github/workflows/auto-app-dev-microservice-web-reusable.yml`
- `.github/workflows/auto-dataflow-design-reusable.yml`
- `.github/workflows/auto-dataflow-dev-reusable.yml`
- `.github/workflows/auto-ai-agent-design-reusable.yml`
- `.github/workflows/auto-ai-agent-dev-reusable.yml`
- `.github/workflows/auto-app-documentation-reusable.yml`
- `.github/workflows/auto-knowledge-management-reusable.yml`
- `.github/workflows/auto-aqod.yml`
- `.github/workflows/setup-labels.yml`

### PR / Issue automation workflows
- `.github/workflows/auto-qa-to-review-transition.yml`
- `.github/workflows/auto-review-to-approve-transition.yml`
- `.github/workflows/auto-create-subissues-transition.yml`
- `.github/workflows/create-subissues-from-pr.yml`
- `.github/workflows/sync-issue-labels-to-pr.yml`
- `.github/workflows/auto-draft-to-ready.yml`
- `.github/workflows/auto-approve-and-merge.yml`
- `.github/workflows/copilot-auto-feedback.yml`
- `.github/workflows/post-qa-to-pr-comment.yml`
- `.github/workflows/auto-qa-default-answer.yml`
- `.github/workflows/restore-auto-qa-label.yml`
- `.github/workflows/auto-issue-qa-ready-transition.yml`
- `.github/workflows/auto-human-resolved-to-ready.yml`
- `.github/workflows/auto-blocked-to-human-required.yml`
- `.github/workflows/advance-subissues.yml`
- `.github/workflows/link-copilot-pr-to-issue.yml`
- `.github/workflows/auto-self-improve-close.yml`

### Validation and test workflows
- `.github/workflows/protect-readonly-paths.yml`
- `.github/workflows/plan-validation-and-labeling.yml`
- `.github/workflows/validate-subissues.yml`
- `.github/workflows/validate-agents.yml`
- `.github/workflows/validate-skills.yml`
- `.github/workflows/validate-knowledge.yml`
- `.github/workflows/test-hve-python.yml`
- `.github/workflows/test-cli-scripts.yml`
- `.github/workflows/bats-tests.yml`

### Scheduled operational workflows
- `.github/workflows/aas-timeout-monitor.yml`
- `.github/workflows/audit-plans.yml`
- `.github/workflows/tdd-retry-metrics.yml`
- `.github/workflows/scheduled-drift-detection.yml`
- `.github/workflows/scheduled-health-check.yml`
- `.github/workflows/sync-azure-skills.yml`

### Manual workflows
以下は棚卸し時点で `workflow_dispatch` が確認された manual / confirmation-required workflow です（未使用とは断定しない）。
- `.github/workflows/copilot-setup-steps.yml`
- `.github/workflows/rollback-drill.yml` — 意図的に保持する手動 `workflow_dispatch` 運用 workflow です。rollback drill / rollback verification で使用し、`uses:` 呼び出し元がないことは未使用の根拠になりません（手動実行が意図された経路です）。
- `.github/workflows/self-hosted-runner-smoke-test.yml`

### Reusable E2E workflow intentionally retained
- `.github/workflows/e2e-playwright-reusable.yml` — reusable な E2E Playwright workflow として意図的に保持します。workflow ファイル内で確定した `uses:` 呼び出しは見つかっておらず、現在は複数のテキスト参照（例: `.github/workflows/auto-app-dev-microservice-web-reusable.yml` の Sub Issue 向け生成指示、`.github/prompts/E2ETesting-Playwright.prompt.md`、`users-guide/workflow-reference.md`）で運用上参照されています。削除/改名時は、これらの参照と依存する生成指示を合わせて更新してください。

### Removed / removal-candidate workflows
- `.github/workflows/integration-tests-sample.yml` — 過去の棚卸しで PR1 の削除候補として整理された optional sample workflow（棚卸し事実: `workflow_dispatch` のみ確認、Issue Template 連携と `uses:` caller は未確認）。現時点では `.github/workflows/` 配下に当該ファイルは存在しません。

## `hve` CLI

`hve` は `python -m hve` で起動する Python パッケージです。エントリポイントは [`hve/__main__.py`](hve/__main__.py) です。

### サブコマンド

| サブコマンド | 役割 | 主なオプション |
|---|---|---|
| （引数なし） | GUI ウィザードを起動（PySide6 未導入時は `cli` に自動フォールバック） | — |
| `gui` | GUI ウィザードを明示起動 | — |
| `run` | インタラクティブモードでワークフローを選んで実行（中身は対話型 wizard） | wizard で対話入力 |
| `cli` | `run` のエイリアス（引数なし起動が GUI に変わったため導入した明示起動用コマンド） | 同上 |
| `orchestrate` | Workflow ID を指定して DAG を実行 | `--workflow/-w`, `--model`, `--review-model`, `--qa-model`, `--max-parallel`, `--auto-qa`, `--auto-contents-review`, `--auto-coding-agent-review`, `--create-issues`, `--mcp-config`, `--branch`, `--steps`, `--app-id`, `--app-ids`, `--resource-group`, `--target-scope`, `--depth`, `--target-dirs`, `--exclude-patterns`, `--doc-purpose`, `--max-file-lines`, `--dry-run` |
| `qa-merge` | 回答済みの質問票をマージし、統合 QA ドキュメントを生成 | `qa/` 配下の回答ファイル指定 |
| `workiq-doctor` | Work IQ 連携の診断 | `--json`, `--skip-mcp-probe`, `--tenant-id`, `--timeout`, `--sdk-probe`, `--sdk-tool-probe`, `--sdk-event-trace`, `--sdk-tool-probe-tools-all` |
| `emit-prompt` | プロンプトテンプレートの出力（ワークフロー内部用途・テスト用途） | `--comment-body` 等 |
| `resume` | 保存済み実行セッションの管理と再開 | `list`, `show`, `rename`, `delete`, `continue` |
| `login` | Copilot SDK のログイン補助 | — |

### 実行例

```bash
# インタラクティブ実行
python -m hve

# Web / Microservice 設計を CLI から実行
python -m hve orchestrate --workflow aad-web --dry-run

# original-docs から質問票を生成
python -m hve orchestrate --workflow aqod --target-scope original-docs/ --depth lightweight

# knowledge/ を再生成
python -m hve orchestrate --workflow akm --sources both

# 保存済みセッションを確認
python -m hve resume list
```

### ランチャースクリプトでの起動

環境セットアップ（[hve-cli-getting-started.md](users-guide/hve-cli-getting-started.md) / [hve-gui-getting-started.md](users-guide/hve-gui-getting-started.md)）完了後、`.venv` を activate せずにリポジトリ直下のランチャーから直接起動できます。リポジトリ直下での実行を想定しており、シンボリックリンク経由の起動は非サポートです。

| OS | ランチャー | 実行例 |
|---|---|---|
| Windows (cmd) | `hve.cmd` | `hve.cmd --help` |
| Linux / macOS (sh) | `hve.sh` | `./hve.sh --help` |

いずれもリポジトリ直下の `.venv` の Python から `python -m hve` を呼び出します。`.venv` 未作成時はエラー終了するため、先に以下のいずれかでセットアップしてください。

- Windows: `hve\setup-hve.cmd` または `powershell -ExecutionPolicy Bypass -File hve\setup-hve.ps1`
- Linux / macOS: `./hve/setup-hve.sh`

#### Linux / macOS で実行権限が落ちている場合

clone 直後やファイルシステムの都合で `hve.sh` に実行権限が無い場合は、以下のいずれかで付与します。

```bash
# 利用者側で一時的に付与
chmod +x hve.sh

# リポジトリにコミットされた実行ビットを修正する場合（Windows 環境からの貢献者向け）
git add hve.sh
git update-index --chmod=+x hve.sh
git commit -m "chore: mark hve.sh as executable"
```

> [!NOTE]
> Work IQ を使う場合は、セットアップと利用条件を [hve-cli-orchestrator-guide.md#work-iq-mcp-連携オプション](users-guide/hve-cli-orchestrator-guide.md#work-iq-mcp-連携オプション) で確認してください。

## users-guide への導線

### まず読むガイド

| ドキュメント | 用途 |
|---|---|
| [hve-cloud-getting-started.md](users-guide/hve-cloud-getting-started.md) | HVE Cloud Agent Orchestrator はじめかた（GitHub Actions） |
| [hve-cli-getting-started.md](users-guide/hve-cli-getting-started.md) | HVE CLI Orchestrator はじめかた（ローカル CLI） |
| [hve-gui-getting-started.md](users-guide/hve-gui-getting-started.md) | HVE GUI Orchestrator はじめかた（ローカル GUI） |
| [web-ui-guide.md](users-guide/web-ui-guide.md) | 方式 1 / 方式 2（GitHub Web 実行） |
| [hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md) | 方式 3（ローカル CLI 実行） |
| [hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md) | 方式 4（GUI ウィザード実行） |
| [hve-technical-architecture.md](users-guide/hve-technical-architecture.md) | 技術アーキテクチャ詳細（3 Orchestrator / メッセージフロー / 4 ゾーン疎結合 / 認証） |
| [workflow-reference.md](users-guide/workflow-reference.md) | Workflow / ラベル / Prompt の一覧 |
| [troubleshooting.md](users-guide/troubleshooting.md) | トラブル対応 |

### フェーズ別ガイド

| フェーズ | ドキュメント |
|---|---|
| ARD（要求定義の自動化） | [01-business-requirement.md（ARD セクション）](users-guide/01-business-requirement.md#要求定義の自動化ard-auto-requirement-definition) |
| 要求定義 | [01-business-requirement.md](users-guide/01-business-requirement.md) |
| アプリケーションアーキテクチャ設計 | [02-app-architecture-design.md](users-guide/02-app-architecture-design.md) |
| Web / Microservice 設計 | [03-app-design-microservice-azure.md](users-guide/03-app-design-microservice-azure.md) |
| Dataflow 設計 | [04-app-design-dataflow.md](users-guide/04-app-design-dataflow.md) |
| Web / Microservice 実装 | [05-app-dev-microservice-azure.md](users-guide/05-app-dev-microservice-azure.md) |
| Dataflow 実装 | [06-app-dev-dataflow-azure.md](users-guide/06-app-dev-dataflow-azure.md) |
| AI Agent（簡易） | [07-ai-agent-simple.md](users-guide/07-ai-agent-simple.md) |
| AI Agent（本格） | [08-ai-agent.md](users-guide/08-ai-agent.md) |
| Knowledge Management | [km-guide.md](users-guide/km-guide.md) |
| Original Docs Review | [original-docs-review.md](users-guide/original-docs-review.md) |
| Source Code からの Documentation | [sourcecode-documentation.md](users-guide/sourcecode-documentation.md) |
| プロンプト例 | [prompt-examples.md](users-guide/prompt-examples.md) |

### Skill: `markdown-query` 独立 GUI

`tools/skills/markdown_query/` は **フォルダごと他リポジトリへコピー** すれば
そのリポジトリでも GUI 設定画面（言語 / Strategy / 対象フォルダ / 索引統計 /
利用統計）を独立して起動できる。HVE GUI 本体はこの同じクラス（`MdqIndexSection`）
を import 経由で参照しているため、両者の機能は常に同期する。

- セットアップ・概要: [tools/skills/markdown_query/README.md](tools/skills/markdown_query/README.md)
- 画面の使い方: [tools/skills/markdown_query/USAGE.md](tools/skills/markdown_query/USAGE.md)
- 仕様: [users-guide/skills-markdown-query.md](users-guide/skills-markdown-query.md)

## リポジトリ構造

README では、実在確認できた主要ディレクトリだけを掲載します。

| パス | 内容 |
|---|---|
| `.github/ISSUE_TEMPLATE/` | Issue Template 定義 |
| `.github/workflows/` | GitHub Actions ワークフロー |
| `.github/prompts/` | 再利用 Prompt 定義（`*.prompt.md`）|
| `hve/` | ローカル実行用 CLI / オーケストレーター |
| `users-guide/` | ユーザー向けガイド |
| `src/data/` | サンプルデータ生成先（AAS Step 4.2 出力） |
| `knowledge/` | 業務要件ドキュメント（D01〜D21）— AKM 実行時に生成 |
| `original-docs/` | 原本ドキュメント（読み取り専用、手動配置） |
| `qa/` | 質問票（AQOD / Prompt が生成） |
| `template/` | テンプレート類 |
| `sample/` | サンプル成果物 |
| `work/` | 実行ログ・作業成果物 |
| `infra/` | インフラ関連資産（ASDW-WEB / ADFDV 実行時に生成） |
| `tools/` | 補助ツール |
| `docs/` | 設計ドキュメント出力先（AAS / AAD-WEB / ADFD 等で生成） |
| `docs-generated/` | ADOC で生成される技術文書 |
| `src/` | 実装コード出力先（ASDW-WEB / ADFDV / AAGD 実行時に生成） |

> [!NOTE]
> `knowledge/` / `original-docs/` / `qa/` / `infra/` / `docs/` / `docs-generated/` / `src/` / `work/` は `.gitignore` や `template/` の敗見れ上未トラックのことがあり、ワークフロー実行時に生成・更新されるディレクトリです。クローン直後に存在しないことがあります。

## ライセンス

[MIT License](LICENSE)
