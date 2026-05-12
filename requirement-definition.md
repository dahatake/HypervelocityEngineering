# 要求定義・機能要件書 — HVE Cloud Agent Orchestrator / HVE CLI Orchestrator

本書は、リポジトリ `RoyalytyService2ndGen`（Hypervelocity Engineering = HVE）における **HVE Cloud Agent Orchestrator** および **HVE CLI Orchestrator** のソースコード実装から逆抽出した、要求定義と機能要件をまとめたものである。

---

## 1. 文書の位置付け

### 1.1 背景

HVE は、要求整理〜実装までを Workflow / Custom Agent / DAG として運用するためのフレームワークである。Orchestrator は Workflow を起動・進行管理する中核機能であり、Cloud（GitHub Actions）と CLI（Python パッケージ）の 2 系統が並存する。両系統の機能仕様を 1 つの基準で扱うため、本書を要求定義書兼機能要件書として位置付ける。

### 1.2 目的

- 既存実装から逆抽出した機能要件を一元化する
- Cloud / CLI 間の機能差を明示し、二重実装リスクを可視化する
- 受入基準を伴う仕様として、テスト / レビュー時の根拠を提供する

### 1.3 対象範囲

- 対象: Cloud Agent Orchestrator dispatcher と CLI Orchestrator のオーケストレーション機能
- 対象外: Custom Agent 個別のプロンプト仕様、Issue Template の UI 仕様、MCP Server 個別の挙動

### 1.4 対象バージョン

- リポジトリ: `dahatake/RoyalytyService2ndGen`
- ブランチ: `main`
- 確認日: 2026-05-12
- commit SHA: TBD（確定時に追記）

### 1.5 利害関係者

| 役割 | 関心事 |
|---|---|
| 利用者（開発者） | Workflow を確実に起動・完走させたい |
| 運用者 | 失敗の検知、リソース消費の予測、復旧手順 |
| 監査者 | トレーサビリティ（誰が・いつ・何を実行したか） |
| 実装担当者 | 仕様変更時の影響範囲 |

### 1.6 メタ受入基準（本書自身の品質基準）

- 全機能要件に検証方法を紐づけることを次版の到達目標とする
- Cloud / CLI それぞれの未対応機能が表で識別できること
- 未確定事項（TBD）が一覧化されていること（§12 参照）

### 1.7 用語

| 用語 | 定義 |
|---|---|
| Workflow | [hve/workflow_registry.py](hve/workflow_registry.py) の `WorkflowDef` で定義されるオーケストレーション単位。Step DAG・ラベル・固有パラメータを含む |
| Step | `WorkflowDef.steps` に含まれる `StepDef`。実行最小単位。コンテナ Step は実行対象から除外され、Sub-Issue 束ね / 論理グループ化に使用される |
| Custom Agent | `.github/agents/` 配下の Agent 定義ファイル。Step に紐づけて呼び出される |
| Fan-out | Step を静的キー（例 `D01〜D21`）または動的パーサ（`fanout_parser`）で N 子ステップへ展開する仕組み |
| Wave | DAG を BFS で並列実行する 1 段。同 Wave 内は並列、Wave 間は AND join |
| Run ID | 実行単位の一意識別子。`generate_run_id()`（[hve/config.py](hve/config.py)）が **UTC タイムスタンプ** + UUID 短縮 6 文字で発番（例: `20260413T143022-a1b2c3`） |

---

## 2. 全体ユースケース

### 2.1 アクター

| アクター | 説明 |
|---|---|
| 利用者（人） | Issue Template から Cloud Orchestrator を起動、または手元で CLI Orchestrator を起動 |
| GitHub Copilot Cloud Agent | Cloud 経路で Custom Agent をホストし、Issue/PR を介して Workflow を進める主体 |

### 2.2 依存コンポーネント（システム）

- Copilot CLI / SDK（CLI 経路でローカルセッションを生成・実行）
- MCP Server 群（Workflow 内で参照される外部ツール: Work IQ、Foundry 等）

### 2.3 主ユースケース

- UC-01: 利用者が Issue Template から Issue を作成し、Cloud Orchestrator（方式 2）が対応する Workflow を起動する。**方式 1（個別 Issue への手動アサイン）は dispatcher を経由しない別経路である**。
- UC-02: 利用者が `python -m hve orchestrate --workflow <id>` で CLI Orchestrator を起動する
- UC-03: 利用者が `python -m hve` で対話 wizard により Workflow とパラメータを選択する
- UC-04: 1 Workflow 完了時に、Cloud Orchestrator が次の推奨 Workflow を Issue コメントで提示する（state_transition）
- UC-05: 利用者が CLI で `resume` サブコマンドにより中断セッションを再開する
- UC-06: 利用者が `--create-issues` / `--create-pr` で CLI 経由でも GitHub Issue / PR を作成する

---

## 3. 共通機能要件

### 3.1 Workflow レジストリ参照

- **FR-COMMON-01（訂正版）**: **CLI Orchestrator** は [hve/workflow_registry.py](hve/workflow_registry.py) の `WorkflowDef` を単一情報源として Workflow を解決する。**Cloud Orchestrator** ([.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)) は `workflow_registry.py` を直接参照せず、dispatcher 内の `trigger_map` / `done_map` / `closed_prefix_map` で Workflow ID を判定する。
  - **リスク**: Workflow ID 定義が二重管理になっており、片方の追加（例: `ard`）が他方に伝播していない。
  - **検証方法**: `auto-orchestrator-dispatcher.yml` の `trigger_map` キーと `list_workflows()` の戻り値が完全一致することをテストで確認する。
- **FR-COMMON-02**: 後方互換エイリアスの解決は以下の 3 局面で行われる:
  - ラベル解決: `auto-app-detail-design` → `AAD-WEB`、`auto-app-dev-microservice` → `ASDW-WEB`、`aad:done` → `AAD-WEB`、`asdw:done` → `ASDW-WEB`
  - タイトルプレフィックス解決: `[AAD]` → `AAD-WEB`、`[ASDW]` → `ASDW-WEB`
  - CLI Workflow ID 解決: `aad` → `aad-web`、`asdw` → `asdw-web`

### 3.2 サポートする Workflow（Cloud / CLI 対応マップ）

| Workflow ID | 名称 | Cloud Orch | CLI Orch | 固有パラメータ |
|---|---|:---:|:---:|---|
| `aas` | App Architecture Design | ✓ | ✓ | （なし） |
| `aad-web` | App Detail Design (Web) | ✓ | ✓ | `app_ids` 等 |
| `asdw-web` | App Dev (Web / Microservice on Azure) | ✓ | ✓ | `app_ids`, `resource_group`, `usecase_id` 等 |
| `abd` | Batch Design | ✓ | ✓ | `app_ids` |
| `abdv` | Batch Dev | ✓ | ✓ | `app_ids`, `batch_job_id`, `resource_group` |
| `aag` | AI Agent Design | ✓ | ✓ | `app_ids`, `usecase_id` |
| `aagd` | AI Agent Dev | ✓ | ✓ | `app_ids`, `usecase_id`, `resource_group` |
| `akm` | Knowledge Management | ✓ | ✓ | `sources`, `target_files`, `force_refresh`, `custom_source_dir`, `enable_auto_merge`, `enable_review`*¹, `workiq_akm_ingest_dxx`*² |
| `aqod` | Original Docs Review | ✓ | ✓ | `target_scope`, `depth`, `focus_areas`, `enable_review`*¹ |
| `adoc` | Source Code → Documentation | ✓ | ✓ | `target_dirs`, `exclude_patterns`, `doc_purpose`, `max_file_lines` |
| `ard` | Auto Requirement Definition | **✗（dispatcher 未対応）** | ✓ | `company_name`, `target_business`, `survey_base_date`, `survey_period_years`, `target_region`, `analysis_purpose`, `attached_docs` |

\*¹ `enable_review` は Issue Template 入力には存在するが、`WorkflowDef.params` 宣言ではなく内部処理で扱われる。
\*² `workiq_akm_ingest_dxx` も同様に `WorkflowDef.params` には宣言されないが、`_collect_params_non_interactive` で `params` 経由に伝搬される。

### 3.3 DAG 実行エンジン

- **FR-DAG-01**: Step の依存関係は AND join、並列 fork、スキップフォールバック（`skip_fallback_deps`）、ブロック（`block_unless`）の 4 パターンをサポートする（[hve/workflow_registry.py](hve/workflow_registry.py)）。
- **FR-DAG-02**: **計画段階**（[hve/dag_planner.py](hve/dag_planner.py)）で Wave 単位の論理プランを生成し、**実行段階**（[hve/dag_executor.py](hve/dag_executor.py)）で `asyncio.Semaphore(max_parallel)` により並列上限を制御する。
- **FR-DAG-03**: 並列上限の階層関係:
  - `WorkflowDef.max_parallel` 未指定 → DAGExecutor 既定値 **15**
  - 明示指定: `akm` = 21、`aqod` = 21、`ard` = 15
- **FR-DAG-04**: Step に `fanout_static_keys` または `fanout_parser` が定義されている場合、子ステップへ動的展開する。展開後の `step_id` は `{base_id}/{key}` 形式。`fanout_parser` の取り得る値:
  - `app_catalog` / `screen_catalog` / `service_catalog` / `batch_job_catalog` / `agent_catalog`
  - `business_candidate`（ARD Step 1.1）
  - `use_case_skeleton`（ARD Step 3.2）
- **FR-DAG-05**: Step ごとに `consumed_artifacts`（再利用コンテキスト用キー）と `output_paths` / `required_input_paths` を保持し、注入対象の絞り込みと事前チェックに用いる。
- **FR-DAG-06**: ルート Step（`depends_on=[]` の非コンテナ）に対しては、開始前に前提成果物の存在チェックを行う。
  - `HVE_REQUIRE_INPUT_ARTIFACTS=true` → 不足は中断
  - `HVE_REQUIRE_INPUT_ARTIFACTS=false`（既定）→ 警告のみで続行

### 3.4 状態ラベルとライフサイクル

- **FR-STATE-01**: 各 Workflow は `{prefix}:initialized` / `{prefix}:ready` / `{prefix}:running` / `{prefix}:done` / `{prefix}:blocked` の状態ラベルを保持する（`_make_state_labels`、[hve/workflow_registry.py](hve/workflow_registry.py)）。
- **FR-STATE-02**: `qa-ready` ラベルは Copilot アサインを保留する状態として明示的にスキップされ、`auto-issue-qa-ready-transition.yml` が `ready` への遷移を担当する。
  - 対象セット: `aas:qa-ready` / `aad:qa-ready` / `asdw:qa-ready` / `abd:qa-ready` / `abdv:qa-ready` / `aag:qa-ready` / `aagd:qa-ready` / `akm:qa-ready` / `aqod:qa-ready` / `adoc:qa-ready` / `aad-web:qa-ready` / `asdw-web:qa-ready`
  - **対象外**: `ard:qa-ready` は `qa_ready_labels` セットに含まれない
- **FR-STATE-03**: 完了ラベル `{prefix}:done` 付与時、Cloud Orchestrator は次の推奨 Workflow を Issue コメントで提示する。
  - チェーン定義: `AAS` → `AAD-WEB` / `ABD` / `AAG` の 3 候補（全提示・1 つ選択は利用者判断）、`AAD-WEB` → `ASDW-WEB`、`ABD` → `ABDV`、`AAG` → `AAGD`
  - **終端 Workflow（`ASDW-WEB` / `ABDV` / `AAGD` / `ADOC` / `AKM` / `AQOD` / `ARD`）完了時は次候補が提示されない**

### 3.5 モデルと SDK

- **FR-MODEL-01**: 既定モデルは `claude-opus-4.7`。
  - `MODEL_CHOICES` は 4 値: `claude-opus-4.7`、`claude-opus-4.6`、`gpt-5.5`、`gpt-5.4`
  - 別途 `MODEL_AUTO_VALUE='Auto'` が許容される（[hve/config.py](hve/config.py)）
- **FR-MODEL-02**: `Auto` 指定時は `reasoning_effort='high'` を SDK に渡す。SDK が当該引数を未サポートの場合は `TypeError` を捕捉し引数除外で再試行する（[hve/orchestrator.py](hve/orchestrator.py) `_create_session_with_auto_reasoning_fallback`）。
- **FR-MODEL-03**: 未サポート / 廃止モデルが渡された場合、ヘルパー `_normalize_model_with_warning` は警告を発出し `Auto` を返す（実際の呼び出し経路は要確認）。

### 3.6 セキュリティ

- **NFR-SEC-01**: `GH_TOKEN`・`COPILOT_PAT` 等の秘密情報を Issue body / 標準出力 / `state.json` に出力してはならない。`SDKConfig.config_snapshot` 復元時、`github_token` / `repo` / `cli_path` / `cli_url` / `mcp_servers` は復元対象から除外する（[hve/orchestrator.py](hve/orchestrator.py) `_restore_config_from_state`）。
- **NFR-SEC-02**: `original-docs/` 配下は全 Agent から読み取り専用とする（`.github/copilot-instructions.md` §0）。
- **NFR-SEC-03**: `git add` 時は `:!path` pathspec 除外で機密ファイルを除く。pathspec はリスト引数として渡し、shell インジェクションを防止する（[hve/orchestrator.py](hve/orchestrator.py) `_git_add_commit_push`）。

---

## 4. HVE Cloud Agent Orchestrator 固有要件

### 4.1 トリガー仕様

- **FR-CLOUD-01**: 監視イベントは `issues` の `opened` / `labeled` / `closed` の 3 種（[.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)）。
- **FR-CLOUD-02**: 起動はラベルベース。`trigger_map` に従い、対応する `auto-*-reusable.yml` を `workflow_call` で起動する。
- **FR-CLOUD-03**: `opened` イベントでは `author_association` が `OWNER` / `MEMBER` / `COLLABORATOR` のいずれかである場合のみ起動する。**`labeled` / `closed` イベントには `author_association` ガードは適用されない**。
- **FR-CLOUD-04**: `closed` イベントでは Issue タイトルの `[AAS]` / `[AAD-WEB]` 等プレフィックスから対象 Workflow を判定する。
- **FR-CLOUD-05**: `setup-labels` ラベル付与時は `setup-labels.yml` を、`original-docs-review` ラベル付与時は `auto-aqod.yml` を起動する。

### 4.2 `mode` 値と発火条件

| `mode` 値 | 発火条件 | 下流ワークフローへの影響 |
|---|---|---|
| `initialize` | `opened` で `trigger_map` 該当 / `labeled` で `trigger_map` 該当 | 対応 reusable orchestrator を初期化モードで起動 |
| `state_transition` | `labeled` で `done_map` 該当 | reusable orchestrator + `suggest-next` ジョブ |
| `closed` | `closed` で title プレフィックスまたは label 該当 | reusable orchestrator にクローズ通知 |
| `skip` | 上記いずれにも合致しない / `qa_ready_labels` 該当 | 何も起動しない |

### 4.3 Issue Body からの動的設定抽出

- **FR-CLOUD-10**: `detect` ジョブは Issue body から以下のセクションを正規表現で抽出し、reusable workflow へ受け渡す:
  - `enable_agentic_retrieval`（`auto` / `yes` / `no`）
  - `agentic_data_source_modes`（`indexer` / `push` のカンマ区切り）
  - `foundry_mcp_integration`（`true` / `false`）
  - `agentic_data_sources_hint`（自由記述）
  - `agentic_existing_design_diff_only`（`true` / `false`）
  - `foundry_sku_fallback_policy`（`global_required` / `standard_allowed`）
  - `runner_type`（`github-hosted` / `self-hosted`）
- **FR-CLOUD-11**: `enable_agentic_retrieval == 'no'` のとき、`foundry_mcp_integration` を強制 `false`、`foundry_sku_fallback_policy` を `standard_allowed` に正規化する。

### 4.4 Reusable Workflow ディスパッチ

- **FR-CLOUD-20**: 各 Workflow ID に対して個別の reusable workflow を 1 対 1 で起動する:
  - `AAD-WEB` → `auto-app-detail-design-web-reusable.yml`
  - `ASDW-WEB` → `auto-app-dev-microservice-web-reusable.yml`
  - `AAG` → `auto-ai-agent-design-reusable.yml`
  - `AAGD` → `auto-ai-agent-dev-reusable.yml`
  - `ADOC` → `auto-app-documentation-reusable.yml`
  - `AAS` → `auto-app-selection-reusable.yml`
  - `ABD` → `auto-batch-design-reusable.yml`
  - `ABDV` → `auto-batch-dev-reusable.yml`
  - `AKM` → `auto-knowledge-management-reusable.yml`
  - `AQOD` → `auto-aqod.yml`
- **FR-CLOUD-21**: AKM Orchestrator は `concurrency: akm-knowledge-write-${{ github.repository }}` により同一リポジトリ内で直列化する。コードコメントによれば目的は `knowledge/` 配下への並列書き込み競合防止（[.github/workflows/auto-knowledge-management-reusable.yml](.github/workflows/auto-knowledge-management-reusable.yml)）。
- **FR-CLOUD-22**: **AKM Orchestrator では** `check_qa_skip` ジョブが前段で実行され、`auto-qa` のスキップ条件を判定する。他 reusable workflow の同等チェック有無は要確認。
- **FR-CLOUD-23**: AKM Orchestrator のジョブタイムアウトは 360 分。

### 4.5 次 Workflow 推奨機能

- **FR-CLOUD-30**: `mode == 'state_transition'` のとき、`suggest-next` ジョブは完了 Workflow に対応する後続候補を `gh issue comment` で投稿する（[.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)）。

### 4.6 Runner 選択

- **FR-CLOUD-40**: `runner_type` 入力に応じて、reusable orchestrator は `["self-hosted","linux","x64","aca"]` または `["ubuntu-latest"]` を選択する。

---

## 5. HVE CLI Orchestrator 固有要件

### 5.1 サブコマンド体系

[hve/__main__.py](hve/__main__.py) は `argparse` ベースで以下のサブコマンドを提供する:

| サブコマンド | 役割 |
|---|---|
| `run` | インタラクティブ wizard（引数なし時の既定動作） |
| `orchestrate` | Workflow ID を指定して DAG を実行 |
| `qa-merge` | 回答済み質問票をマージ |
| `workiq-doctor` | Work IQ 連携の診断 |
| `resume` | 保存済み実行セッションの管理と再開 |
| `emit-prompt` | Step のプロンプトを表示（デバッグ用） |

### 5.2 `orchestrate` の必須・主要オプション

- **FR-CLI-01**: 必須引数は `--workflow / -w`（Workflow ID）のみ。
- **FR-CLI-02**: 主要オプション一覧:
  - **モデル**: `--model`、`--review-model`、`--qa-model`
  - **並列制御**: `--max-parallel`（既定 15）
  - **自動レビュー**: `--auto-qa`、`--auto-contents-review`、`--auto-coding-agent-review`、`--auto-coding-agent-review-auto-approval`
  - **対話制御**: `--force-interactive`（QA 回答入力の TTY 判定をバイパスし対話モードを強制）
  - **Work IQ**: `--workiq`、`--workiq-akm-review`、`--workiq-akm-ingest`、`--workiq-dxx`、`--workiq-draft`、`--workiq-tenant-id`、`--workiq-prompt-{qa,km,review}`、`--workiq-per-question-timeout`
  - **Git/PR**: `--create-issues`、`--create-pr`、`--ignore-paths`、`--branch`、`--repo`
  - **出力**: `--verbose`、`--quiet`、`--verbosity`、`--show-stream`、`--log-level`、`--no-color`、`--banner / --no-banner`、`--screen-reader`、`--timestamp-style`、`--final-only`
  - **タイムアウト**: `--timeout`（既定 21600 秒 = 6h）、`--review-timeout`（既定 7200 秒 = 2h）
  - **MCP / CLI 接続**: `--mcp-config`、`--cli-path`、`--cli-url`
  - **共通絞り込み**: `--steps`、`--app-id`（後方互換、複数指定不可。現行推奨は `--app-ids`） / `--app-ids`、`--resource-group`、`--batch-job-id`、`--usecase-id`
  - **AKM 固有**: `--sources`、`--target-files`、`--force-refresh / --no-force-refresh`、`--custom-source-dir`、`--enable-auto-merge`
  - **AQOD 固有**: `--target-scope`、`--depth`、`--focus-areas`
  - **ADOC 固有**: `--target-dirs`、`--exclude-patterns`、`--doc-purpose`、`--max-file-lines`
  - **ARD 固有**: `--company-name`、`--target-business`、`--survey-base-date`、`--survey-period-years`、`--target-region`、`--analysis-purpose`、`--target-recommendation-id`、`--attached-docs`
  - **追加**: `--additional-prompt`、`--additional-comment`、`--context-max-chars`、`--issue-title`
  - **自己改善**: `--self-improve` / `--no-self-improve`
  - **検証**: `--dry-run`

### 5.3 対話 wizard

- **FR-CLI-10**: `python -m hve`（引数なし）または `python -m hve run` は対話 wizard を起動する。
- **FR-CLI-11**: wizard はクイック全自動モードと詳細モードを提供し、Workflow 固有パラメータを順次収集する。
- **FR-CLI-12**: ARD wizard は Step 1〜3 をマルチ選択させ、Step 1 選択時のみ `company_name` を必須、Step 2 単独実行時のみ `target_business` を必須とする。
- **FR-CLI-13**: AKM wizard は `sources` をマルチ選択（`qa` / `original-docs` / `workiq`）し、`workiq` を含む場合のみ取り込み対象 Dxx を尋ねる。

### 5.4 非対話モード

- **FR-CLI-20**: `cli_args` が `None` でない場合は非対話モード扱いとする（[hve/orchestrator.py](hve/orchestrator.py) `_is_non_interactive`）。
- **FR-CLI-21**: 非対話モードでは `_collect_params_non_interactive` が CLI 引数のみからパラメータを構築し、欠落値は Workflow 既定値を採用する。

### 5.5 Issue / PR 作成（CLI 経路）

- **FR-CLI-30**: `--create-issues` 指定時、CLI は以下のシーケンスを実行する: 新ブランチ作成 → Root Issue 作成 → Sub-Issue 作成（active Step ごと） → DAG 実行 → `git add/commit/push` → PR 作成 → **`--auto-coding-agent-review` フラグ指定時のみ** Code Review Agent レビュー → サマリー出力（[hve/orchestrator.py](hve/orchestrator.py) module docstring および `_create_issues_if_needed`）。
- **FR-CLI-31**: `--create-issues` には `--repo` と `GH_TOKEN` が必須。未設定時は警告を出して Issue 作成をスキップする。
- **FR-CLI-32**: `--create-pr` は PR 作成のみ行い、自動マージは実行しない（Issue Template の `enable_auto_merge` とは別運用）。
- **FR-CLI-33**: `--ignore-paths` で指定されたパスは `git add` の pathspec 除外として扱う（既定値は `SDKConfig` 側）。

### 5.6 セッション永続化と再開

- **FR-CLI-40**: 各 Step 完了時に `state.json` を更新し、以下のフィールドを保存する（[hve/orchestrator.py](hve/orchestrator.py) `_build_step_complete_callback`）:
  - `status`（`completed` / `failed` / `skipped` / `blocked`）
  - `completed_at`、`elapsed_seconds`
  - `error_summary`、`skip_reason`
  - `retry_count`、`forked_session_id`
- **FR-CLI-41**: SDK セッション ID は決定論的に生成し、`hve-<run_id>-step-<step_id>[-<suffix>]` 形式とする（`_orchestrator_session_id` および `runner.py` の `_make_step_session_id`）。
- **FR-CLI-42**: `resume` サブコマンドは `list` / `show` / `rename` / `delete` / `continue` を提供する。
- **FR-CLI-43**: Resume 時は `state.config_snapshot` から `SDKConfig` のフィールドを復元する。ただし機密 / 環境固有フィールド（`github_token` / `repo` / `cli_path` / `cli_url` / `mcp_servers`）は復元対象外。

### 5.7 既存成果物検出と再利用コンテキスト

- **FR-CLI-50**: 実行前に `docs/catalog/*.md`、`docs/services/*.md`、`docs/screen/*.md`、`docs/test-specs/*.md`、`docs/agent/*.md`、`docs/batch/jobs/*.md`、`knowledge/*.md`、`docs-generated/**/*.md`、および `src/`（最大 50）、`test/`（最大 30）を走査して既存成果物を検出する（[hve/orchestrator.py](hve/orchestrator.py) `_detect_existing_artifacts`）。
- **FR-CLI-51**: 再利用コンテキストのフィルタリングは、以下の **全て** の条件を満たす場合に行う:
  - `HVE_REUSE_CONTEXT_FILTERING=true`
  - Step に `consumed_artifacts` が `None` 以外で定義されている
  - 既存成果物が 1 件以上検出されている
- **FR-CLI-52**: Step 種別の推定ルール（`_infer_step_kind`）:
  - 判定式: `half = (total + 1) // 2`（半数切り上げ）。対応キー集合の長さが `half` 以上のとき該当種別とする
  - 優先順位:
    1. `test_files` / `test_specs` / `test_strategy` → `tests`
    2. `src_files` → `code`
    3. `knowledge` / `doc_generated` → `docs`
    4. `*_catalog` / `*_specs` / `*_matrix` → `catalog`
    5. それ以外（混在含む） → `default`

### 5.8 Self-Improve（自己改善ループ）

- **FR-CLI-60**: `--self-improve` または `HVE_AUTO_SELF_IMPROVE=true` で自己改善ループを有効化する。`--no-self-improve` は最優先で無効化する。
- **FR-CLI-61**: スコープは `""`（既定 = step + workflow）、`"disabled"`、`"step"`、`"workflow"` の 4 値（[hve/config.py](hve/config.py) `VALID_SELF_IMPROVE_SCOPES`）。
- **FR-CLI-62**: ワイルドカード `*` 展開先は `data`、`docs`、`docs-generated`、`knowledge`、`src` で、`work/` は常時除外する。

---

## 6. パラメータ仕様（抜粋）

### 6.1 AKM の `sources` 正規化

- **FR-PARAM-01**: 受理形式は文字列（カンマ / 空白区切り）または `list`/`tuple`/`set`。トークンは `qa` / `original-docs` / `workiq` / `both`（後方互換 → `qa,original-docs`）。
- **FR-PARAM-02**: 不明トークンは例外を出さず無視する（[hve/orchestrator.py](hve/orchestrator.py) `_normalize_akm_sources`）。
  - **運用上のリスク**: **警告も発出されないため、誤入力時に利用者が気づきにくい**。
  - 結果順序は固定 `[workiq, qa, original-docs]` のうち含まれるものを並べる。
- **FR-PARAM-03**: 空入力 / `None` の既定値は `["qa", "original-docs"]`。
- **FR-PARAM-04**: `target_files` の既定値は、非 workiq ソースが `qa` 単独なら `qa/*.md`、`original-docs` 単独なら `original-docs/*`、それ以外（複数または workiq のみ）は空文字列。

### 6.2 ARD のステップ選択ロジック

- **FR-PARAM-10**: CLI 非対話モードで `--target-business` が空の場合 `[1, 2, 3]`、指定時は `[2, 3]` を既定の `selected_steps` とする（[hve/orchestrator.py](hve/orchestrator.py) `_collect_params_non_interactive`）。
- **FR-PARAM-11**: 既定値:
  - `survey_base_date` = 実行日（`date.today().isoformat()`）
  - `survey_period_years` = `30`
  - `target_region` = `グローバル全体`
  - `analysis_purpose` = `中長期成長戦略の立案`

### 6.3 APP-ID 自動選択

- **FR-PARAM-20**: `aad-web` / `asdw-web` で APP-ID 未指定時、`docs/catalog/app-arch-catalog.md` から「Webフロントエンド + クラウド」アーキテクチャに合致する APP-ID を自動選択する。
- **FR-PARAM-21**: `abd` / `abdv` では「データバッチ処理 / バッチ」アーキテクチャに合致する APP-ID を自動選択する（[hve/app_arch_filter.py](hve/app_arch_filter.py) `resolve_app_arch_scope`）。

---

## 7. 非機能要件

| ID | 要件 |
|---|---|
| NFR-PERF-01 | DAG 実行は `asyncio.Semaphore` を使い、Workflow ごとの `max_parallel`（AKM/AQOD は 21、その他は 15、ARD は 15）を超えない |
| NFR-PERF-02 | 既存成果物走査は `src/` 50 件、`test/` 30 件で早期打ち切る。**ハードコード値であり、設定では変更不可** |
| NFR-PERF-03 | 性能の測定方法 / 目標値（KPI、SLA）は未定義（§12 TBD）|
| NFR-OBS-01 | Wave 2 コンテキスト注入計測（`none_steps` / `total_chars` / `max_chars` / `phase_breakdown` / `self_improve_scope`）を Console / stderr に出力する。`GITHUB_STEP_SUMMARY` 環境変数が設定されている場合に限りサマリにも出力。`OSError` 時は警告のみで継続 |
| NFR-OBS-02 | Fork-on-retry が有効な場合のみ `ForkKPILogger` を構築し、無効時は `None` を返してオーバーヘッドを排除する |
| NFR-OBS-03 | `--verbosity` で `quiet` / `compact` / `normal` / `verbose` を切替可能。既定は `compact` |
| NFR-COMP-01 | 旧 step_id（ARD の `1, 2, 3` 等）からの resume は warning + 新規実行扱いとする（ADR-0003 §3.4 を参照、パス未確認） |
| NFR-COMP-02 | SDK バージョン < 0.3.0 互換のため、`reasoning_effort` 未サポート例外をハンドリングして再試行する |
| NFR-TIME-01 | CLI の既定 idle タイムアウトは 21,600 秒（6h）、Code Review Agent レビュー待ちは 7,200 秒（2h）。**CLI は無入出力時間ベース** |
| NFR-TIME-02 | Cloud Orchestrator の AKM ジョブタイムアウトは 360 分、`detect` / `suggest-next` ジョブは 15 分。**Cloud は GitHub Actions の `timeout-minutes`（経過時間ベース）** |
| NFR-A11Y-01 | CLI は `--screen-reader` で絵文字を日本語ラベルに置換、スピナーを無効化、`NO_COLOR` 環境変数（no-color.org 規格）に従う |

---

## 8. インタフェース要件

### 8.1 Cloud Orchestrator → Reusable Workflow

`workflow_call` 経由で以下の入力を受け渡す（[.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)）:

- `mode`（`initialize` / `state_transition` / `closed` / `skip`）
- `issue_number`、`event_action`、`label_name`、`issue_labels`
- `enable_agentic_retrieval`、`agentic_data_source_modes`、`foundry_mcp_integration`
- `agentic_data_sources_hint`、`agentic_existing_design_diff_only`、`foundry_sku_fallback_policy`
- `runner_type`

### 8.2 CLI Orchestrator → SDK

`SDKConfig` を介して以下を保持する（[hve/config.py](hve/config.py)）。**SDKConfig dataclass の完全フィールド一覧は要確認（§12 TBD）**:

- `model` / `review_model` / `qa_model`、`max_parallel`
- `github_token` / `repo`（環境変数優先）
- `cli_path` / `cli_url`、`mcp_servers`
- `create_issues` / `create_pr`、`branch`、`ignore_paths`
- `reuse_context_filtering`、`require_input_artifacts`、`context_injection_max_chars`（既定 20,000）
- `auto_self_improve` / `self_improve_scope` / `self_improve_target_scope`
- `fork_on_retry`、`run_id`、`session_id_prefix`

### 8.3 永続化フォーマット

- `state.json` に Run 単位で `run_id` / `workflow_id` / `steps[]` を保持し、各 Step の `status` / `completed_at` / `elapsed_seconds` / `error_summary` / `skip_reason` / `retry_count` / `forked_session_id` を記録する（[hve/run_state.py](hve/run_state.py)）。

---

## 9. 制約・前提

- **C-01**: 本書は `main` ブランチ時点（2026-05-12 確認）のソースから機械的に抽出した内容に限定し、未確認の挙動は §12 TBD に記載する。
- **C-02**: Workflow ID 表記の正は [hve/workflow_registry.py](hve/workflow_registry.py)（`.github/copilot-instructions.md` 準拠）。
- **C-03**: `original-docs/` は読み取り専用。書き込みは想定しない。
- **C-04**: Step ID は Workflow 内でのみ一意。Workflow 横断結合する場合はワークフロー接頭辞が必要。

---

## 10. 参照

> 以下のリンク先の実在は別途検証が必要。

- [.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)
- [.github/workflows/auto-knowledge-management-reusable.yml](.github/workflows/auto-knowledge-management-reusable.yml)
- [hve/__main__.py](hve/__main__.py)
- [hve/orchestrator.py](hve/orchestrator.py)
- [hve/workflow_registry.py](hve/workflow_registry.py)
- [hve/dag_executor.py](hve/dag_executor.py)
- [hve/dag_planner.py](hve/dag_planner.py)
- [hve/config.py](hve/config.py)
- [users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md)
- [users-guide/web-ui-guide.md](users-guide/web-ui-guide.md)

---

## 11. 改訂履歴

| バージョン | 日付 | 内容 |
|---|---|---|
| 0.1 | 2026-05-12 | 初版（ソースコードから逆抽出） |
| 0.2 | 2026-05-12 | 敵対的レビュー指摘の Critical / Major 修正反映 |
| 0.3 | 2026-05-12 | §13 ワークフロー別仕様（生成ファイル詳細）を追加 |
| 0.4 | 2026-05-12 | §13 関連 TBD 調査結果を反映（テンプレ実体に基づき生成ファイルパスを訂正）、AQOD Step 1 テンプレを fan-out 構成に整合 |

---

## 12. 未確定事項（TBD）

| TBD No. | 内容 | 確認方法 |
|---|---|---|
| TBD-01 | リポジトリの確定 commit SHA | `git rev-parse HEAD` |
| TBD-02 | `SDKConfig` dataclass の完全フィールド一覧 | `hve/config.py` 全文確認 |
| TBD-03 | ADR-0002 / ADR-0003 のファイルパス | `docs/decisions/` 配下を検索 |
| TBD-04 | `users-guide/*.md` 各リンクの実在 | ファイル存在確認 |
| TBD-05 | 各 FR への個別受入基準の付与 | 次版で Given/When/Then 形式に展開 |
| TBD-06 | Cloud Orchestrator の ARD 対応有無の確定 | dispatcher への対応エントリ追加可否を判断 |
| TBD-07 | AKM 以外の reusable workflow における `check_qa_skip` 同等チェックの有無 | 各 `auto-*-reusable.yml` を確認 |
| TBD-08 | 外部 IF 要件 / データ要件 / エラー処理要件セクションの拡充 | 次版で追加 |
| TBD-09 | 性能 KPI / SLA の数値目標 | 運用データ蓄積後に設定 |
| TBD-10 | `_normalize_model_with_warning` の実際の呼び出し経路 | orchestrator.py / runner.py の参照点を確認 |

---

## 13. ワークフロー別仕様（生成ファイル詳細）

本節は、各 Workflow の目的・Step DAG・生成ファイル（`output_paths` / `output_paths_template`）・必須入力（`required_input_paths`）をゲートとして緻密化する目的で定義する。本節と [hve/workflow_registry.py](hve/workflow_registry.py) は単一情報源（SSOT）として整合させ、差分が生じた場合はソース側を正として優先する。

### 13.0 共通約束

- **FR-WF-OUT-01**: 各 Step は `output_paths` で宣言した全ファイルを実行完了時点で存在させなければならない。1 件でも欠落した場合、当該 Step は `failed` とする（Self-Improve target scope 解決・Wave 入力チェックの前提）。
- **FR-WF-OUT-02**: `output_paths_template` は fan-out 子ステップに対して `{key}` を fan-out キー（例 `D01` / `SC-Home` / `SVC-billing` / 業務候補 ID / UC スケルトン ID）で置換した実パスを生成する。fan-out キーが空集合の場合、当該 Step はスキップではなく `failed`（fan-out 失敗）とする。
- **FR-WF-OUT-03**: `required_input_paths` に列挙された全ファイルが存在しない場合の挙動は `HVE_REQUIRE_INPUT_ARTIFACTS` に従う（`true`: 中断 / 既定 `false`: 警告継続、§3.3 FR-DAG-06）。
- **FR-WF-OUT-04**: 表中「生成ファイル」列の `{key}` は fan-out キーを表す。Container Step（`is_container=true`）は生成ファイルを持たず、Sub-Issue 束ね用途に限定する。

### 13.1 AAS — Architecture Design

- **目的**: ユースケースカタログから、アプリ群／ドメイン／サービス／データ／テスト戦略までの上流アーキテクチャ資産を一式生成する。AAD-WEB / ABD / AAG の上流に位置する。
- **必須入力（ルート）**: `docs/catalog/use-case-catalog.md`
- **Step DAG と生成ファイル**:

| Step | タイトル | Custom Agent | 依存 | 生成ファイル |
|---|---|---|---|---|
| 1 | アプリケーションリスト作成 | Arch-ApplicationAnalytics | — | `docs/catalog/app-catalog.md` |
| 2 | ソフトウェアアーキテクチャ推薦（APP 毎 fan-out） | Arch-ArchitectureCandidateAnalyzer | 1 | `docs/catalog/app-arch-catalog.md`（fan-out 結果統合） |
| 3.1 | ドメイン分析 | Arch-Microservice-DomainAnalytics | 2 | `docs/catalog/domain-analytics.md` |
| 3.2 | サービス一覧抽出 | Arch-Microservice-ServiceIdentify | 3.1 | `docs/catalog/service-catalog.md` |
| 4.1 | データモデル設計 | Arch-DataModeling | 3.2 | `docs/catalog/data-model.md` |
| 4.2 | サンプルデータ生成 | Arch-DataModeling | 4.1 | `src/data/sample-data.json` |
| 5 | データカタログ | Arch-DataCatalog | 4.1 | `docs/catalog/data-catalog.md` |
| 6 | サービスカタログ統合 | Arch-Microservice-ServiceCatalog | 5 | `docs/catalog/service-catalog-matrix.md` |
| 7 | テスト戦略書 | Arch-TDD-TestStrategy | 6 | `docs/catalog/test-strategy.md` |

### 13.2 AAD-WEB — Web App Design

- **目的**: AAS 完了後、Web 系 APP に対し画面・サービス・テスト仕様（TDD RED 仕様書）を fan-out 生成し、横断整合性レビューで締める。
- **入力**: AAS 一式（`app-catalog` / `service-catalog` / `service-catalog-matrix` / `data-model` / `domain-analytics` / `test-strategy`）。
- **Step DAG と生成ファイル**:

| Step | タイトル | Custom Agent | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|---|
| 1 | 画面一覧と遷移図 | Arch-UI-List | — | — | `docs/catalog/screen-catalog.md` |
| 2.1 | 画面定義書 | Arch-UI-Detail | 1 | `screen_catalog` | `docs/screen/{screenId}-{screenNameSlug}-description.md` |
| 2.2 | マイクロサービス定義書 | Arch-Microservice-ServiceDetail | 1 | `service_catalog` | `docs/services/{serviceId}-{serviceNameSlug}-description.md` |
| 2.3 | TDD テスト仕様書 | Arch-TDD-TestSpec | 2.1, 2.2 | `service_catalog` | `docs/test-specs/{serviceId}-test-spec.md`（テンプレ上 `docs/test-specs/{screenId}-test-spec.md` も併記の表記揺れあり） |
| 3 | 画面 ↔ サービス整合性レビュー | QA-DocConsistency | 2.1, 2.2, 2.3 | — | `docs/catalog/screen-service-consistency-report.md` |

> 注: 上記パスはテンプレート（`.github/scripts/templates/aad-web/step-*.md` の「## 出力」）の実体に基づく。Step 1 / 2.1 / 2.2 / 2.3 は `hve/workflow_registry.py` の `output_paths` / `output_paths_template` が未登録のため、ゲート判定の自動化には正式登録が必要。**TBD-11（§14）**。

### 13.3 ASDW-WEB — Web App Dev & Deploy

- **目的**: AAD-WEB を入力に、Azure データ層／コンピュート／追加サービス／UI を TDD（RED → GREEN）でデプロイし、WAF レビューまで完了させる。
- **Step DAG（抜粋）と生成物カテゴリ**:

| Step | タイトル | Fan-out | 生成カテゴリ |
|---|---|---|---|
| 1 / 2 / 3 / 4 | 各種コンテナ | — | （Sub-Issue 束ね、ファイル非生成） |
| 1.1 | Azure データストア選定 | — | `docs/azure/azure-services-data.md` |
| 1.2 | Azure データサービス Deploy | — | `infra/azure/create-azure-data-resources-prep.sh`、`infra/azure/create-azure-data-resources.sh`、`src/data/azure/data-registration-script.sh`、`docs/azure/service-catalog.md` 更新 |
| 2.1 | Azure コンピュート選定 | — | `docs/azure/azure-services-compute.md` |
| 2.2 | 追加 Azure サービス選定 | — | `docs/azure/azure-services-additional.md` |
| 2.3 | 追加 Azure サービス Deploy | — | `infra/azure/create-azure-additional-resources-prep.sh`、`infra/azure/create-azure-additional-resources/create.sh`、`docs/catalog/service-catalog-matrix.md` 更新 |
| 2.3T | サービステスト仕様書（TDD RED） | `service_catalog` | `docs/test-specs/{serviceId}-test-spec.md` |
| 2.3TC | サービステストコード生成（TDD RED） | `service_catalog` | `test/api/{サービス名}.Tests/**` |
| 2.4 | サービス実装（TDD GREEN） | `service_catalog` | `src/api/{サービスID}-{サービス名}/**` |
| 2.5 | Azure Compute Deploy | — | `infra/azure/create-azure-api-resources-prep.sh`、`.github/workflows/*.yml`（CI/CD）、`docs/catalog/service-catalog-matrix.md` 更新、`test/{サービスID}-{サービス名}/**`、デプロイ TDD 用 `docs/test-specs/deploy-step2-compute-test-spec.md`、`infra/azure/verify-api-resources.sh` |
| 3.0T | UI テスト仕様書（TDD RED） | `screen_catalog` | `docs/test-specs/{screenId}-test-spec.md` |
| 3.0TC | UI テストコード生成（TDD RED） | `screen_catalog` | `test/ui/**`（Jest + jsdom） |
| 3.1 | UI 実装（TDD GREEN） | `screen_catalog` | `src/app/**` |
| 3.2 | Web アプリ Deploy（Azure SWA） | — | `infra/azure/create-azure-webui-resources-prep.sh`、`infra/azure/create-azure-webui-resources.sh`、`.github/workflows/*.yml`（SWA）、`docs/catalog/service-catalog-matrix.md` 更新、デプロイ TDD 用 `docs/test-specs/deploy-step3-swa-test-spec.md`、`infra/azure/verify-webui-resources.sh` |
| 3.3 | UI E2E テスト（Playwright） | — | Playwright 実行ログ、失敗時 HTML レポート / trace artifact（永続ファイル非生成） |
| 4.1 | WAF アーキテクチャレビュー | — | `docs/azure/azure-architecture-review-report.md` |
| 4.2 | 整合性チェック | — | `docs/azure/dependency-review-report.md` |

> 注: 上記パスはテンプレート（`.github/scripts/templates/asdw-web/step-*.md` の「## 出力」）の実体に基づく。ASDW-WEB の各 Step は `hve/workflow_registry.py` の `output_paths` / `output_paths_template` が未登録のため、ゲート判定の自動化には正式登録が必要。**TBD-12**。

### 13.4 ABD — Batch Design

| Step | タイトル | 依存 | Fan-out | 生成ファイル（規約パス） |
|---|---|---|---|---|
| 1.1 | バッチドメイン分析 | — | — | `docs/batch/batch-domain-analytics.md` |
| 1.2 | データソース／デスティネーション分析 | — | — | `docs/batch/batch-data-source-analysis.md` |
| 2 | バッチデータモデル | 1.1, 1.2 | — | `docs/batch/batch-data-model.md` |
| 3 | ジョブ設計書 | 2 | — | `docs/batch/batch-job-catalog.md` |
| 4 | サービスカタログ | 3 | — | `docs/batch/batch-service-catalog.md` |
| 5 | テスト戦略書 | 4 | — | `docs/batch/batch-test-strategy.md` |
| 6.1 | ジョブ詳細仕様書 | 5 | `batch_job_catalog` | `docs/batch/jobs/{key}-spec.md` |
| 6.2 | 監視・運用設計書 | 5 | — | `docs/batch/batch-monitoring-design.md` |
| 6.3 | TDD テスト仕様書 | 6.1, 6.2 | `batch_job_catalog` | `docs/test-specs/{key}-test-spec.md` |

### 13.5 ABDV — Batch Dev

| Step | タイトル | 依存 | Fan-out | 生成カテゴリ |
|---|---|---|---|---|
| 1.1 | データサービス選定 | — | — | `infra/azure/batch/**`、`docs/azure/azure-services-data.md` |
| 1.2 | Azure データリソース Deploy | 1.1 | — | Azure データリソース実体 |
| 2.1 | TDD RED テストコード作成 | 1.2 | `batch_job_catalog` | `test/batch/{key}.Tests/**` |
| 2.2 | TDD GREEN バッチジョブ本実装 | 2.1 | `batch_job_catalog` | `src/batch/{key}/**` |
| 3 | Azure Functions / コンテナ Deploy | 2.2 | — | `.github/workflows/*.yml`、Azure Functions 実体 |
| 4.1 | WAF レビュー | 3 | — | `docs/azure/waf-review-batch.md` 等 |
| 4.2 | 整合性チェック | 3 | — | `docs/azure/dependency-review-batch.md` 等 |

### 13.6 AAG — AI Agent Design

| Step | タイトル | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|
| 1 | AI Agent アプリケーション定義 | — | — | `docs/agent/agent-application-definition.md` |
| 2 | AI Agent 粒度設計 | 1 | `agent_catalog` | `docs/agent/agent-architecture.md`（および Agent 別補助ファイル） |
| 3 | AI Agent 詳細設計 | 2 | `agent_catalog` | `docs/agent/agent-detail-{key}.md`、`docs/ai-agent-catalog.md` |

### 13.7 AAGD — AI Agent Dev & Deploy

| Step | タイトル | 依存 | Fan-out | 生成カテゴリ |
|---|---|---|---|---|
| 1 | AI Agent 構成設計 | — | — | `docs/azure/azure-services-agent.md` 等 |
| 2.1 | テスト仕様書（TDD RED） | 1 | `agent_catalog` | `docs/test-specs/{key}-test-spec.md` |
| 2.2 | テストコード生成（TDD RED） | 2.1 | `agent_catalog` | `test/agent/{key}.Tests/**` |
| 2.3 | 実装（TDD GREEN） | 2.2 | `agent_catalog` | `src/agent/{key}/**` |
| 3 | AI Agent Deploy | 2.3 | `agent_catalog` | `.github/workflows/*.yml`、Foundry Agent リソース実体 |

### 13.8 AKM — Knowledge Management

- **fan-out キー**: 固定 `D01`〜`D21`（21 並列）。`max_parallel=21`。
- **同時更新防止**: `concurrency: akm-knowledge-write-${{ github.repository }}`（§4.4 FR-CLOUD-21）。

| Step | タイトル | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|
| 1 | knowledge ドキュメント生成・管理 | — | 静的 `D01〜D21` | `knowledge/{Dxx}-*.md` および `knowledge/{Dxx}-*-ChangeLog.md`（各 Dxx ごと） |
| 2 | knowledge 横断整合性レビュー | 1 | — | `knowledge/business-requirement-document-status.md` 更新（および整合性レポート） |

> `knowledge/` 書き込みは「削除 → 新規作成」ルール（`.github/copilot-instructions.md` §0）に従い、本体ファイルへの LOCK 情報埋め込みは禁止。

### 13.9 AQOD — Original Docs Review

- **fan-out キー**: 固定 `D01`〜`D21`（21 並列）。`max_parallel=21`。
- **入力**: `original-docs/`（読み取り専用）、`knowledge/D01〜D21-*.md`。

| Step | タイトル | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|
| 1 | original-docs 質問票生成 | — | 静的 `D01〜D21` | `qa/{key}-original-docs-questionnaire.md`（`{key}` は `D01`〜`D21`） |
| 2 | 横断整合性レビュー | 1 | — | `qa/original-docs-cross-questionnaire.md` |

> 上記パスはテンプレート（`.github/scripts/templates/aqod/step-1.md` および `step-2.md` の「## 出力」）の実体に基づく。AQOD の各 Step は `hve/workflow_registry.py` の `output_paths` / `output_paths_template` が未登録のため、ゲート判定の自動化には正式登録が必要。**TBD-13**。

### 13.10 ADOC — Source Code → Documentation

- **入力**: `--target-dirs` で指定されたソースコード階層。
- **生成ルートディレクトリ**: `docs-generated/`。

| Step | タイトル | 依存 | 生成カテゴリ |
|---|---|---|---|
| 1 | ファイルインベントリ | — | `docs-generated/inventory.md` |
| 2.1〜2.5 | ファイルサマリー（5 系統並列） | 1 | `docs-generated/files/{relative-path}.md`（プロダクション / テスト / 設定 / CI/CD / 大規模分割） |
| 3.1 | コンポーネント設計書 | 2.* | `docs-generated/components/{module-name}.md` |
| 3.2 | API 仕様書 | 2.* | `docs-generated/components/api-spec.md` |
| 3.3 | データモデル定義書 | 2.* | `docs-generated/components/data-model.md` |
| 3.4 | テスト仕様サマリー | 2.2 | `docs-generated/components/test-spec-summary.md` |
| 3.5 | 技術的負債一覧 | 2.* | `docs-generated/components/tech-debt.md` |
| 4 | コンポーネントインデックス | 3.* | `docs-generated/component-index.md` |
| 5.1 | アーキテクチャ概要 | 4 | `docs-generated/architecture/overview.md` |
| 5.2 | 依存関係マップ | 4 | `docs-generated/architecture/dependency-map.md` |
| 5.3 | インフラ依存分析 | 4 | `docs-generated/architecture/infra-deps.md` |
| 5.4 | 非機能要件現状分析 | 4, 3.4, 3.5 | `docs-generated/architecture/nfr-analysis.md` |
| 6.1 | オンボーディングガイド | 5.1, 5.2 | `docs-generated/guides/onboarding.md` |
| 6.2 | リファクタリングガイド | 5.2, 5.4, 3.5 | `docs-generated/guides/refactoring.md` |
| 6.3 | 移行アセスメント | 5.1, 5.3, 5.4 | `docs-generated/guides/migration-assessment.md` |

> 上記パスはテンプレート（`.github/scripts/templates/adoc/step-*.md` の「## 出力」）の実体に基づく。ADOC の各 Step は `hve/workflow_registry.py` の `output_paths` / `output_paths_template` が未登録のため、ゲート判定の自動化には正式登録が必要。**TBD-14**。

### 13.11 ARD — Auto Requirement Definition

- **目的**: 企業全体／対象事業の事業分析からユースケースカタログまでを自動生成する Workflow。ADR-0003 で 7 step 構成に再設計。
- **Cloud Orchestrator 対応**: 未対応（§3.2 FR-COMMON-01、§12 TBD-06）。
- **Step DAG と生成ファイル**:

| Step | タイトル | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|
| 1 | 事業分野候補列挙 | — | — | `docs/company-business-recommendation.md` |
| 1.1 | 事業分野別深掘り分析 | 1 | `business_candidate` | `docs/business/{key}-analysis.md` |
| 1.2 | 事業分析統合 | 1.1 | — | `docs/company-business-requirement.md` |
| 2 | 対象業務深掘り分析 | （`target_business` 指定時ルート／未指定時 1.2 経由 skip_fallback） | — | `docs/business-requirement.md` |
| 3.1 | ユースケース骨格抽出 | 2（skip_fallback `1.2`） | — | `docs/catalog/use-case-skeleton.md` |
| 3.2 | ユースケース詳細生成 | 3.1 | `use_case_skeleton` | `docs/use-cases/{key}-detail.md` |
| 3.3 | ユースケースカタログ統合 | 3.2 | — | `docs/catalog/use-case-catalog.md` |

- **必須入力**:
  - Step 3.1: `docs/business-requirement.md`、`docs/company-business-requirement.md`
- **後方互換**: 旧 step_id（`1`/`2`/`3`）からの resume は警告ログ後に新規実行扱い（NFR-COMP-01）。

### 13.12 ゲート条件（受入基準）

各 Workflow の完了判定は以下を全て満たすこと:

1. **G-OUT**: 当該 Workflow の全 Step（コンテナ除く）について `output_paths` / `output_paths_template` 展開後の全ファイルが存在し、サイズ > 0。
2. **G-IN**: 後続 Workflow が要求する `required_input_paths`（§13 表中の必須入力）が満たされている。
3. **G-LBL**: `{prefix}:done` ラベルが付与され、`{prefix}:running` / `{prefix}:blocked` が外れている（§3.4 FR-STATE-01）。
4. **G-CONS**: AKM の場合のみ、`knowledge/business-requirement-document-status.md` 上で全 21 ドキュメントのステータスが一貫していること。
5. **G-DIFF**: PR 作成経路（CLI `--create-pr` / Cloud）では、当該 Workflow の生成パス以外への変更が含まれていないこと（§9 差分品質評価、`.github/copilot-instructions.md` §9）。

上記いずれか 1 件でも未達のとき、Workflow は `done` ではなく `blocked` 扱いとし、Self-Improve または手動介入の対象とする。

---

## 14. §13 関連 TBD 追補

| TBD No. | 内容 | 確認方法 |
|---|---|---|
| TBD-11 | AAD-WEB Step 1 / 2.1 / 2.2 / 2.3 の `output_paths` / `output_paths_template` を `hve/workflow_registry.py` に正式登録（テンプレ規約は §13.2 で判明済み。Step 2.3 のテンプレに `{serviceId}` と `{screenId}` の表記揺れあり、テンプレ統一も合わせて検討） | `hve/workflow_registry.py` に追記し本書と同期 |
| TBD-12 | ASDW-WEB 全 Step の `output_paths` / `output_paths_template` を `hve/workflow_registry.py` に正式登録（テンプレ規約は §13.3 で判明済み。Step 3.3 のように永続ファイルを生成しない Step の扱い方針も併せて確定） | 同上 |
| TBD-13 | AQOD Step 1 / 2 の `output_paths` / `output_paths_template` を `hve/workflow_registry.py` に正式登録（テンプレ規約は §13.9 で判明済み。v0.4 で Step 1 テンプレを fan-out 構成に整合済み） | 同上 |
| TBD-14 | ADOC 全 Step の `output_paths` / `output_paths_template` を `hve/workflow_registry.py` に正式登録（テンプレ規約は §13.10 で判明済み。Step 2.1〜2.5 の `{relative-path}` 規則の最終確定を含む） | `Doc-FileInventory` 仕様確認＋`hve/workflow_registry.py` への追記 |

---

以上。
