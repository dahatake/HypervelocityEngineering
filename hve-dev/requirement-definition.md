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
- 対象: HVE アプリケーション自体の変更に対する、要求参照・テスト対応・PR トレーサビリティの保守プロセス
- 対象外: Custom Agent 個別のプロンプト仕様、Issue Template の UI 仕様、MCP Server 個別の挙動

本書は次の 3 層を含む。優先順位は 1 → 2 → 3 とする。

1. **規範要件**: `FR-*` / `NFR-*` / `G-*` の定義行のうち、索引で `active-or-described` とされたもの、および当該要件が明示的に参照する従属表・箇条書き・スキーマ。HVE アプリケーション変更時に満たす。新規 ID の bootstrap 中は、同一変更セット内でのみ要求定義書の新規定義行とその明示参照先を暫定的な規範として扱い、索引再生成と照合が完了するまで他の変更から利用してはならない。
2. **説明的基線**: 既存実装から逆抽出した表・構成・確認時点の記述。規範要件を上書きしない。
3. **履歴情報**: 改訂履歴、解消済み TBD、`deprecated-or-removed` の要件。互換性調査以外では現行要件として適用しない。

現行コードと規範要件が矛盾する場合、Coding Agent はコードを暗黙の正解として要件を上書きせず、バグ修正か仕様変更かを明示して解消する。仕様変更の場合は、実装前に規範要件を改訂する。

### 1.4 対象バージョン

- リポジトリ: `dahatake/RoyalytyService2ndGen`
- ブランチ: `main`
- 確認日: 2026-05-12
- commit SHA: `48326f3ea5fa55b65c262a4eb6e0cccea261bd6f`（v1.0.3 ベースライン）

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
| Custom Agent | `.github/prompts/` 配下の Agent 定義ファイル。Step に紐づけて呼び出される |
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
- ~~UC-05: 利用者が CLI で `resume` サブコマンドにより中断セッションを再開する~~ → **廃止（v1.1）**: Session State（Resume）機能を全廃
  - **2026-07-27 再確認**: ASDW-WEB の長時間ラン全損対策として resume の復活が検討されたが、本廃止決定を維持する。代替として FR-DAG-08（実行開始時パラメータ pre-flight）により、長時間実行後に判明していた入力不備を起動直後に検出する。resume を復活させる場合は本項の廃止を先に改訂すること。
- UC-06: 利用者が `--create-issues` / `--create-pr` で CLI 経由でも GitHub Issue / PR を作成する。`--issue-number` を併用した場合は Root Issue を新規作成せず既存 Issue へ連携する（FR-GUI-25）
- UC-07: 利用者が GUI から GitHub Issue / Pull Request を閲覧・編集・作成し、書式支援付きの入力欄でコメントを投稿し、Pull Request をレビュー・マージする（FR-GUI-26 / FR-GUI-27 / FR-GUI-30 / FR-GUI-31 / FR-GUI-41〜49）
- UC-08: 利用者が GUI から実行タスクへ関連付ける Issue / Pull Request を一覧または作成結果から指定し、実行後のコンソール出力を当該 Pull Request へコメントとして残し、作業ブランチの push と head ブランチ削除を行う（FR-GUI-32〜34 / FR-GUI-40）

---

## 3. 共通機能要件

### 3.1 Workflow レジストリ参照

- **FR-COMMON-01（訂正版）**: **CLI Orchestrator** は [hve/workflow_registry.py](hve/workflow_registry.py) の `WorkflowDef` を単一情報源として Workflow を解決する。**Cloud Orchestrator** ([.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)) は `workflow_registry.py` を直接参照せず、dispatcher 内の `trigger_map` / `done_map` / `closed_prefix_map` で Workflow ID を判定する。
  - **リスク**: Workflow ID 定義が二重管理になっており、片方の追加が他方に伝播しない。
  - **検証方法**: Cloud 対応を宣言する §3.2 の Workflow ID 集合と、dispatcher の `trigger_map` / `done_map` / `closed_prefix_map` / reusable job の集合が一致することをテストで確認する。CLI / GUI 専用 Workflow（現行は `adi`）を `list_workflows()` との単純な完全一致で Cloud 対象へ昇格させてはならない。
- **FR-COMMON-02**: 後方互換エイリアスの解決は以下の 3 局面で行われる:
  - ラベル解決: `auto-app-detail-design` → `AAD-WEB`、`auto-app-dev-microservice` → `ASDW-WEB`、`aad:done` → `AAD-WEB`、`asdw:done` → `ASDW-WEB`
  - タイトルプレフィックス解決: `[AAD]` → `AAD-WEB`、`[ASDW]` → `ASDW-WEB`
  - CLI Workflow ID 解決: `aad` → `aad-web`、`asdw` → `asdw-web`

### 3.2 サポートする Workflow（Cloud / CLI 対応マップ）

| Workflow ID | 名称 | Cloud Orch | CLI Orch | 固有パラメータ |
|---|---|:---:|:---:|---|
| `ard` | Auto Requirement Definition | ✓ | ✓ | `company_name`, `target_business`, `survey_base_date`, `survey_period_years`, `target_region`, `analysis_purpose`, `attached_docs`, `include_kpi_okr` |
| `aas` | App Architecture Design | ✓ | ✓ | （なし） |
| `ada` | Agent Data Architecture | ✓ | ✓ | `app_ids`, `app_id` |
| `aad-web` | App Detail Design (Web) | ✓ | ✓ | `app_ids`, `app_id`, `create_remote_mcp_server` |
| `asdw-web` | App Dev (Web / Microservice on Azure) | ✓ | ✓ | `app_ids`, `app_id`, `resource_group`, `usecase_id`, `tdd_max_retries`, `create_remote_mcp_server` |
| `adfd` | Dataflow Design | ✓ | ✓ | `app_ids`, `app_id` |
| `adfdv` | Dataflow Dev | ✓ | ✓ | `app_ids`, `app_id`, `resource_group`, `tdd_max_retries` |
| `aag` | AI Agent Design | ✓ | ✓ | `app_ids`, `app_id`, `usecase_id` |
| `aagd` | AI Agent Dev & Deploy | ✓ | ✓ | `app_ids`, `app_id`, `resource_group`, `usecase_id`, `tdd_max_retries` |
| `aar` | Agentic Retrieval Add-on | ✓ | ✓ | `app_ids`, `app_id`, `resource_group`, `usecase_id` |
| `akm` | Knowledge Management | ✓ | ✓ | `sources`, `target_files`, `force_refresh`, `custom_source_dir`, `enable_auto_merge`, `enable_review`*¹, `workiq_akm_ingest_dxx`*² |
| `adi` | Auto Design-doc Ingestion | **✗（dispatcher 未対応）** | ✓ | `purpose`, `target_scope`, `depth`, `focus_areas` |
| `adoc` | Source Code → Documentation | ✓ | ✓ | `target_dirs`, `exclude_patterns`, `doc_purpose`, `max_file_lines` |

\*¹ `enable_review` は Issue Template 入力には存在するが、`WorkflowDef.params` 宣言ではなく内部処理で扱われる。
\*² `workiq_akm_ingest_dxx` も同様に `WorkflowDef.params` には宣言されないが、`_collect_params_non_interactive` で `params` 経由に伝搬される。

行順は [hve/workflow_registry.py](hve/workflow_registry.py) の登録順に合わせる。Cloud Orch 欄は
[.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml) の
`trigger_map` に当該 Workflow が登録されているかを根拠とする。本表の Workflow ID 集合が registry と
一致することは [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py)
`test_requirement_doc_workflow_table_lists_every_registered_workflow` が固定する。

旧独立の原本質問票処理は ADI に統合し、独立した Workflow ID・Cloud reusable workflow・CLI / GUI 選択肢として再公開してはならない。後方互換 alias も提供しない。

### 3.3 DAG 実行エンジン

- **FR-DAG-01**: Step の依存関係は AND join、並列 fork、スキップフォールバック（`skip_fallback_deps`）、ブロック（`block_unless`）の 4 パターンをサポートする（[hve/workflow_registry.py](hve/workflow_registry.py)）。
- **FR-DAG-02**: **計画段階**（[hve/dag_planner.py](hve/dag_planner.py)）で Wave 単位の論理プランを生成し、**実行段階**（[hve/dag_executor.py](hve/dag_executor.py)）で `asyncio.Semaphore(max_parallel)` により並列上限を制御する。
- **FR-DAG-03**: DAG の並列上限は次の順序で解決し、解決結果を計画段階（[hve/dag_plan.py](hve/dag_plan.py) `DAGPlan.max_parallel`）と実行段階の semaphore の双方における唯一の上限としなければならない。
  1. ARD bridge mode の直列化が成立するとき → **1**
  2. `WorkflowDef.max_parallel` の宣言があるとき → **その宣言値**
  3. いずれでもないとき → `SDKConfig.max_parallel`（CLI `--max-parallel`、既定 **15**）
  - 宣言値は `akm` = 21、`adi` = 21、`ard` = 15、`asdw-web` = 1 とする。他の Workflow は宣言を持たない。
  - 解決は [hve/orchestrator.py](hve/orchestrator.py) の単一実装で行い（FR-MAINT-07）、解決根拠を `DAGPlan.max_parallel_source` へ `ard-serial` / `workflow` / `config` として保持しなければならない。`DAGExecutor` へ `dag_plan` を渡す経路では `DAGPlan.max_parallel` が semaphore を決めるため、実行段階で `WorkflowDef.max_parallel` を再解決してはならない。
  - 宣言を持つ Workflow に対して `SDKConfig.max_parallel` で宣言値を上書きしてはならない。`asdw-web` の宣言は同一 worktree での並列書込みを避ける安全制約であり、`akm` / `adi` の宣言は fan-out が設計上その並列度で動くことを表すため、いずれも利用者設定より優先する。従来 `run_workflow` は `SDKConfig.max_parallel` だけを計画へ渡しており、`dag_plan` を伴う経路では `WorkflowDef.max_parallel` が実行に一切反映されていなかった（実測: `asdw-web` は宣言 1 に対し 2 ステップの wave が 4 箇所とも並列実行され、`akm` / `adi` は宣言 21 に対し semaphore 15 で fan-out が分割されていた）。
- **FR-DAG-04**: Step に `fanout_static_keys` または `fanout_parser` が定義されている場合、子ステップへ動的展開する。展開後の `step_id` は `{base_id}/{key}` 形式。`fanout_parser` の取り得る値:
  - `app_catalog` / `screen_catalog` / `service_catalog` / `dataflow_catalog` / `agent_catalog`
  - `business_candidate`（ARD Step 1.1）
  - `use_case_skeleton`（ARD Step 3.2）
  - 展開キーを解決するカタログの探索基準ルートは、**実行プロセスの作業ディレクトリ（対象リポジトリのルート）**とする。HVE パッケージの設置ディレクトリを基準にしてはならない。基準は、DAG 構築前の事前展開（[hve/orchestrator.py](hve/orchestrator.py) `_expand_workflow_for_dag`）と、上流 Step 完了後の deferred 再展開（[hve/dag_executor.py](hve/dag_executor.py) `_try_dynamic_expand`）の双方で同一でなければならない。基準が対象リポジトリを指さない場合、カタログが実在しても展開キーが 0 件となり当該 Step が `fanout-empty` で無警告 skip される。
- **FR-DAG-05**: Step ごとに `consumed_artifacts`（再利用コンテキスト用キー）と `output_paths` / `required_input_paths` を保持し、注入対象の絞り込みと事前チェックに用いる。
- **FR-DAG-06**: ルート Step（`depends_on=[]` の非コンテナ）に対しては、開始前に前提成果物の存在チェックを行う。
  - `HVE_REQUIRE_INPUT_ARTIFACTS=true` → 不足は中断
  - `HVE_REQUIRE_INPUT_ARTIFACTS=false`（既定）→ 警告のみで続行
- **FR-DAG-07**: `StepDef` は `required_params`（当該 Step の実行に必要な Workflow パラメータ名）と `default_params`（未指定時に適用する既定値）を宣言できる（[hve/workflow_registry.py](hve/workflow_registry.py)）。両者は Workflow パラメータ契約の単一情報源であり、CLI wizard / CLI 非対話 / GUI のどの起動経路でも同一の宣言を参照する。
  - `apply_step_default_params(wf, active_steps, params)` は、active step の `default_params` のうち、`params` に未設定または空白のみの値しか無いキーへ既定値を適用し、適用したキー名を昇順で返す。
  - 既に空白でない値があるキーは上書きしない。
  - active step ID が fan-out 子形式（`{base_id}/{key}`）の場合は base step ID へ正規化して解決する。
  - `default_params` のキーは同じ `StepDef` の `required_params` に含まれていなければならない（`WorkflowDef._validate` で検証する）。
- **FR-DAG-08**: Workflow 実行開始時（**dry-run の計画表示より前**、当然 DAG 実行より前）に、active step が `required_params`（FR-DAG-07）で宣言した全パラメータを検査する（[hve/orchestrator.py](hve/orchestrator.py) `_check_required_workflow_params_for_active_steps`）。
  - 検査対象は下流の単一情報源、すなわち `StepRunner` へ `workflow_params` として渡る `effective_params` とする。CLI 引数由来の生 `params` ではない。
  - FR-DAG-07 の `apply_step_default_params` を本検査の直前に `effective_params` へ適用する。既定値で解消できる欠落を不足として報告しない。
  - 判定結果は `_check_workflow_input_artifacts` / `_check_required_skills_for_active_steps` と同じ `should_abort` / `error` / `blocked` / `blocked_step_ids` 形式で返す。
  - **不足は 1 件ずつではなく全件を一括で報告する**。1 回の実行で全ての不足を利用者へ提示できなければならない。
  - 「不足」とは、値が未設定・`None`・空白のみの文字列・`str` 以外の型のいずれかであること。
  - 既定 strict（`should_abort=True`）とする。前提成果物チェックと異なり、必須パラメータの欠落は同一ワークフロー内の先行 Step では解消され得ないため、警告降格の既定値を持たない。
  - `continue_on_error`（local 実行モード）でも本チェックは降格しない。パラメータ欠落のまま Step を起動すると Azure write 直前まで判定が遅延し、実行時間の全損を招くため。
  - `--dry-run` はパラメータ充足性の事前確認手段として機能しなければならない。
- **FR-DAG-09**: レビュー Step の判定を上流 Step の再実行へ結び付けるフィードバックループは、**DAG の外側**に置かなければならない。`FR-DAG-01` が定める依存パターン 4 種は非巡回であり、レビュー Step から実装 Step へ戻るエッジを DAG 内に表現してはならない。
  - 差戻し先は `StepDef.rework_targets` の静的宣言に限る。レビュー成果物の自由記述から戻り先を推測してはならない。LLM 応答へ制御判断を委ねない方針（FR-CLI-63）と同じ理由による。
  - 引き金は `FR-WF-CONF-03` が定める `Judgement` 列の `FAIL` だけとする。`NOT_MEASURED`（測定できなかった）と `NO_TARGET`（目標値が設計側に無い）は実装の不備を意味しないため引き金にしてはならない。`PASS` も同様とする。
  - 測定表の解析は [hve/artifact_validation.py](hve/artifact_validation.py) の既存実装を再利用し、別の表パーサを新設してはならない（FR-MAINT-07）。
  - 本項が規定するのは差戻し先の**決定**までとする。決定した Step 群の再実行は `--steps`（FR-CLI-02）または `--resume-run`（FR-CLI-86）による再起動で行い、`run_workflow` の DAG 構築を run 内で再入可能へ作り替えてはならない。同関数の DAG 構築部は Issue / PR 作成・branch 操作・fan-out 展開・Workbench 起動を含み、再入化の副作用を実行なしで検証できないためである。
  - `rework_targets` を宣言するのは `asdw-web` Step 5.3（要件適合実測）だけとし、戻り先は実装 Step の `3.3` と `4.2` とする。同 Step は `FR-WF-CONF-03` の測定表を出力する 4 Step のうち、実装 Step が複数ある唯一の Workflow に属する。他 Workflow への宣言は、当該 Workflow で測定実績を得た時点で個別に判断する。どの Step へ戻すかは Workflow ごとの方針判断であり、根拠なく既定を与えてはならない。
  - 決定した差戻し先は DAG 実行の完了後に利用者へ提示しなければならない。提示は `run_workflow` が `console.event` へ 1 回だけ出力するものとし、実行面ごとに別の提示実装を追加してはならない（FR-MAINT-07）。GUI は当該出力を既存のログ経路で受け取る。
  - 提示内容は差戻し先 Step ID と `--steps` による再実行コマンドの提案に限る。HVE が自動で再実行を開始してはならない（前項の再起動委譲と同じ理由）。差戻し先が空のときは何も提示してはならない。提示の失敗で run の成否を変えてはならない。
  - 契約テスト: [hve/tests/test_rework_loop.py](hve/tests/test_rework_loop.py)

### 3.4 状態ラベルとライフサイクル

- **FR-STATE-01**: 各 Workflow は `{prefix}:initialized` / `{prefix}:ready` / `{prefix}:running` / `{prefix}:done` / `{prefix}:blocked` の状態ラベルを保持する（`_make_state_labels`、[hve/workflow_registry.py](hve/workflow_registry.py)）。加えて Cloud Agent Orchestrator の HITL 経路（FR-CLOUD-41）が用いる `{prefix}:human-required` / `{prefix}:human-resolved` を保持する。HITL ラベルは `_make_state_labels` の生成対象ではなく、[.github/labels.json](.github/labels.json) の登録と Cloud の遷移 workflow が唯一の情報源である。
  - HITL ラベルの対象プレフィックス（[.github/labels.json](.github/labels.json) 登録分）: `aas` / `aad` / `aad-web` / `asdw` / `asdw-web` / `adfd` / `adfdv` / `aag` / `aagd` / `akm` / `adoc` の 11 件。`aad` / `asdw` は FR-COMMON-02 の後方互換エイリアスである。
  - `ard` / `aar` / `ada` / `adi` は HITL ラベルを持たない。全 Workflow への拡張は本要件の対象外とする。
  - 契約テスト [hve/tests/test_label_consistency_audit.py](hve/tests/test_label_consistency_audit.py) が本項の宣言と `.github/labels.json` の一致を機械検査する。
- **FR-STATE-02**: `qa-ready` ラベルは Copilot アサインを保留する状態として明示的にスキップされ、質問票作成を担当する Copilot がアサインされた場合は `qa-drafting`（回答下書き中）へ遷移する。`auto-issue-qa-ready-transition.yml` は回答受領後に `qa-ready` または `qa-drafting` から `ready` への遷移を担当する。
  - 対象セット: `ard:qa-ready` / `aas:qa-ready` / `aad:qa-ready` / `asdw:qa-ready` / `abd:qa-ready` / `abdv:qa-ready` / `aag:qa-ready` / `aagd:qa-ready` / `akm:qa-ready` / `adoc:qa-ready` / `aad-web:qa-ready` / `asdw-web:qa-ready`
- **FR-STATE-03**: 完了ラベル `{prefix}:done` 付与時、Cloud Orchestrator は次の推奨 Workflow を Issue コメントで提示する。
  - チェーン定義: `ARD` → `AAS`、`AAS` → `AAD-WEB` / `ADFD` / `AAG` の 3 候補（全提示・1 つ選択は利用者判断）、`AAD-WEB` → `ASDW-WEB`、`ADFD` → `ADFDV`、`AAG` → `AAGD`
  - **終端 Workflow（`ASDW-WEB` / `ADFDV` / `AAGD` / `ADOC` / `AKM`）完了時は次候補が提示されない**
- **FR-STATE-04**: HVE の標準ローカル実行は、process 終了後も残る利用者単位の durable state store へ、execution・Workflow instance・Step/承認の control state を保存しなければならない。
  - 保存先は `platformdirs.user_state_path("hve", appauthor=False) / "state.sqlite3"` の単一 SQLite database とする。リポジトリごとの生 absolute path は保存せず、正規化済み Git root の SHA-256 を `repo_key` として使用する。
  - schema は `executions`、`workflow_instances`、`step_instances` の 3 table だけとする。attempt history table、output content hash、prompt/response/tool payload 用 table を追加してはならない。
  - connection ごとに `journal_mode=DELETE` の実効値を検査し、`synchronous=EXTRA`、`foreign_keys=ON`、`trusted_schema=OFF`、busy timeout 1 秒を設定する。open 時に schema version を検査し、resume candidate 読取時に `quick_check` を実行する。corrupt database または未知 schema は自動削除・自動修復せず fail-closed とする。
  - POSIX では state directory を `0700`、database file を `0600` とする。Windows は user profile ACL の継承を前提とし、ACL 強化済みとは主張しない。
  - `dry_run` と初期対象外 mode は execution を登録してはならない。標準新規実行の state write 失敗は run を継続せず、`continue_on_error` によって成功・skip へ降格してはならない。
  - 永続化直前の store 境界でも registration を再検証し、未知の実行面、0 から連続しない Workflow ordinal、重複 instance、credential / URL / absolute path / JSON payload に該当する descriptor 値を拒否しなければならない。上位の `ResumeService` が sanitize 済みであることだけを信用してはならない。
  - `hve/.run-progress.jsonl` は FR-CLI-86 の明示的な legacy reader 専用とし、標準新規実行から追記・自動列挙・SQLite への自動 import を行ってはならない。
- **FR-STATE-05**: durable state は、execution を跨いで再利用できる公開 `execution_id` と、attempt ごとの既存 `run_id` を分離し、次の lifecycle と canonical state を単一実装で管理しなければならない。
  - parent は sanitized ordered plan と全 Workflow instance を、最初の child・model session・外部 write より前に 1 transaction で登録する。direct single-Workflow entrypoint だけが parent として `execution_id` を生成し、child は生成してはならない。
  - `workflow_instances` は `(execution_id, instance_id)`、`step_instances` は `(execution_id, instance_id, step_id)` を key とする。Workflow status は `pending` / `running` / `suspended` / `succeeded` / `failed` / `skipped` / `blocked`、Step/承認 status は `pending` / `running` / `succeeded` / `failed` / `skipped` / `blocked` とする。`needs_reconciliation` は保存 status にせず、resume plan の risk reason として導出する。
  - StepResult `success` と GUI `done` は `succeeded` へ変換する。承認は `record_kind=approval`、`step_id=approval:<wave_index>` とし、approved を `succeeded`、declined を `failed` として保存する。承認者名・自由記述・prompt 本文を保存してはならない。
  - succeeded Step を skip する前に FR-WF-OUT-01 と同じ必須 output 存在判定を行う。output 不足なら当該 Step と DAG 上の transitive descendants を再実行候補にする。content hash は作成しない。
  - 本項が保存するのは HVE-owned control state だけである。未出力 model state、streaming delta、provider 内部状態、生成途中本文、外部副作用の exactly-once を保存・保証してはならない。
- **NFR-REL-03**: durable resume の 10 秒目標は HVE-owned control state に限定し、次の 2 条件を別々に満たさなければならない。
  - transition durability: store method が commit 成功を返した `state_version` は hard process kill 後も欠落 0 とする。
  - liveness freshness: owner 実行中かつ scheduler/storage が正常な受入環境では、kill 時点の `heartbeat_age` を 10 秒以下とする。heartbeat worker は event loop と独立した thread、thread 専用 connection、`time.monotonic()` による 5 秒間隔で動作し、同じ `state_version` の生存時刻だけを更新する。
  - heartbeat write failure または fencing conflict は main executor を停止させ、成功状態を推測してはならない。worker stop は bounded とし、GUI graceful stop の最初の 3 秒以内に final state commit と worker stop を完了できなければならない。
  - OS/VM power loss、network filesystem、model/output progress の 10 秒復元は初期受入範囲外とする。初期実測は Windows/NTFS の graceful/hard process kill と OS 非依存 unit test に限定する。
- **NFR-CONC-02**: 同一 `(execution_id, instance_id)` の resume は state version CAS と fenced lease で直列化しなければならない。
  - lease acquire/takeover は `BEGIN IMMEDIATE` 内で active lease が無いか期限切れであり、かつ `state_version=expected_state_version` の 1 row だけを更新する。lease TTL は 20 秒とする。
  - acquire/takeover ごとに `lease_generation` を単調増加させ、1 へ reset してはならない。transition と heartbeat は lease owner と generation の一致を条件とし、更新 row が 1 でなければ durable state error とする。
  - 未期限切れownerのheartbeat成功時は`lease_expires_at`を当該heartbeat時刻から20秒後へ更新し、正常実行が20秒を超えてもleaseを維持する。期限切れownerは更新できず、最後に成功したheartbeatから20秒後には明示takeoverが可能でなければならない。
  - workflow / Step transition、heartbeat、release は owner / generation に加えて `lease_expires_at` が現在時刻より後であることを条件とする。期限切れ owner は heartbeat で自身を復活させたり、transition を commit したり、lease 情報を release して明示 takeover 要求を迂回したりしてはならない。
  - heartbeat と release は取得時 token の `state_version` との等値を条件にしてはならない。同じ owner / generation の未期限切れ lease で自身の transition が `state_version` を進めた後も、取得時 token で heartbeat と release を継続できなければならない。transition 自体の state version CAS は維持する。
  - 期限切れ lease の takeover は利用者が recovery action を明示した後だけ許可する。Prompt/GUI の plan 提示後に state が変化した場合は stale として再提示し、自動再試行してはならない。
  - parent processがleaseを取得して別のHVE childを起動する場合、取得済みtokenの`lease_owner`と`lease_generation`をhelp非表示のinternal argsでchildへ渡し、childの全transition/heartbeatを同じfencing条件へ結び付ける。parentはchild終了後にleaseを解放する。tokenを渡さずparentだけがleaseを保持すること、またはchild起動前にleaseを解放して同じCASを再実行させることを禁止する。

### 3.5 モデルと SDK

- **FR-MODEL-01**: 既定モデルは `claude-opus-4.7`。
  - `MODEL_CHOICES` は 4 値: `claude-opus-4.7`、`claude-opus-4.6`、`gpt-5.5`、`gpt-5.4`
  - 別途 `MODEL_AUTO_VALUE='Auto'` が許容される（[hve/config.py](hve/config.py)）
- **FR-MODEL-02**: `Auto` 指定時は SDK へ `model="auto"` (wire 値) を渡し、サーバ側 Auto Model Selection（GitHub Copilot の動的モデルルーティング）に委譲する。`reasoning_effort` はクライアント側で設定しない（サーバ側がモデル毎に適切な effort を選ぶ）。内部センチネル `MODEL_AUTO_VALUE='Auto'` → wire 値 `MODEL_AUTO_WIRE_VALUE='auto'` の変換は [hve/config.py](hve/config.py) の `to_wire_model()` 関数で集中管理。ユーザーが `reasoning_effort` を明示指定した場合は経路を問わず尊重する。SDK が `reasoning_effort` 引数を未サポートの場合は `TypeError` を捕捉し引数除外で再試行する（[hve/orchestrator.py](hve/orchestrator.py) `_create_session_with_auto_reasoning_fallback`）。
- **FR-MODEL-03**: 未サポート / 廃止モデルが渡された場合、ヘルパー `_normalize_model_with_warning` は警告を発出し `Auto` を返す（実際の呼び出し経路は要確認）。
- **FR-MODEL-04**: HVE は GitHub Copilot SDK の `create_session(tool_search=...)`（ツール定義の遅延ロード）を CLI / GUI から設定可能とする。有効時は SDK へ `tool_search={"enabled": True}` を渡し、無効時は当該引数を渡さない。**既定は有効**とする。設定値は Step 実行経路のメインセッション、サブセッション（Pre-QA / Review）、Self-Improve セッションへ同一値を伝搬しなければならない。Fleet mode 親セッション（[hve/orchestrator.py](hve/orchestrator.py)）は意図的にツール公開を狭めた別系統であり、当該経路の実測根拠がないため本要件の対象外とする。`defer_threshold` は SDK 既定に委ね、設定として公開しない。本要件の `SDKConfig.tool_search` は、AAGD ワークフローのパラメータ `enable_tool_search`（生成する AI Agent の Foundry Toolbox 設定）とは別ドメインであり、HVE 自身の SDK セッションにだけ作用する。本要件はツール定義がコンテキストの大きな割合を占める実態（実測: 登録 171 ツール / 54,865 tokens のうち実使用は 10 種 / 9,108 tokens）を背景とするが、**削減効果は本要件の受入対象外**とし、受入は設定の伝搬だけとする（[hve/config.py](hve/config.py)、[hve/runner.py](hve/runner.py)、[hve/self_improve.py](hve/self_improve.py)）。既定を無効から有効へ変更した根拠は利用者の適用方針決定であり、削減率の実測を根拠としてはならない。**2026-08-13 の実測（Copilot CLI 1.0.79 / SDK 1.0.7、`session.metadata.contextInfo`）では、`tool_search` の有効 / 無効 / `defer_threshold=1` の 3 条件で `toolDefinitionsTokens` が 52,756 で完全に一致し、全ツールの `defer_loading` が `null`、`tool_search_tool` もツール一覧に現れなかった。すなわち当該環境では遅延公開が一切発火しておらず、削減効果は 0 である。**この実測は既定有効を否定しない（コンテキストを増やさないため）が、本設定を削減手段として期待してはならない。
- **FR-MODEL-06**: FR-MODEL-04 の既定有効化は、利用者による明示的な無効化を上書きしてはならない。`--no-tool-search` と `HVE_TOOL_SEARCH` の falsy 値は無効として扱い、当該実行では SDK へ引数を渡さない。GUI では新規プロファイルの初期値だけを有効とし、**保存済み設定の値は移行・上書きしない**（保存済みの `false` が利用者の明示指定か旧既定かを区別できないため）。ランキング実装の既定（FR-TS-01 の `tool_search_ranking`）は本変更の対象外であり `sdk` のままとする。
- **FR-MODEL-05**: SDK が `tool_search` 引数を未サポートの場合、Step 実行経路のセッション生成（[hve/runner.py](hve/runner.py) `_create_session_with_auto_reasoning_fallback`）は `TypeError` を捕捉して当該引数を除外し再試行しなければならない。未サポートを理由に実行を停止してはならない（既存の `reasoning_effort` 縮退規則に従う）。
- **FR-MODEL-07**: 開発環境セットアップ（[hve/setup-hve.sh](hve/setup-hve.sh) / [hve/setup-hve.ps1](hve/setup-hve.ps1)）は、**既定で `github-copilot-sdk` を最新版へ更新しなければならない**（`pip install --upgrade --no-deps github-copilot-sdk`）。`--no-deps` は必須とする（付けないと pip resolver が `pydantic-core` を pydantic 本体の pin から乖離させ GUI 起動が例外になる）。再現性のために版を固定する経路は明示フラグ（`--pin-sdk` / `-PinSdk`）に限り、指定時だけ単一の宣言ファイル [hve/copilot-sdk.lock](hve/copilot-sdk.lock) の版を導入しなければならない。`--upgrade-sdk` / `-UpgradeSdk` は最新化に加えて当該ファイルの pin 行と Copilot CLI ランタイム版の記録行を書き換えなければならない（既定経路は宣言ファイルを書き換えてはならない）。既定を最新追従へ変更した根拠は利用者の明示的な方針決定であり、下記のランタイム整合検証は変更後も維持する。あわせてセットアップは、SDK が pin する Copilot CLI ランタイム（`copilot/_cli_version.py` の `CLI_VERSION`）を先読みし、実際に解決されるランタイムの埋め込み版と突合して不一致を警告しなければならない。埋め込み版の取得には `--no-auto-update` を付与しなければならない（`--version` 単体はオンライン更新チェックの結果である「最新利用可能版」を返すため pin との突合に使えない。実測: 埋め込み 1.0.69 のバイナリが `--version` では 1.0.78 を返す）。pin を無効化する環境変数 `COPILOT_CLI_PATH` / `COPILOT_CLI_EXTRACT_DIR` / `COPILOT_SKIP_CLI_DOWNLOAD` が設定されている場合は警告しなければならない。ランタイム整合検証は、SDK の生成イベントパーサ（`copilot/generated/session_events.py`）がイベントのエンベロープ（`id` / `timestamp` / `type`）を assert で固めており、pin と異なるランタイムを掴むと `session.event` の解析が `AssertionError` となって当該イベントが黙って捨てられる（終端イベントを取り逃すと `send_and_wait` がタイムアウトまで返らない）ことへの予防である。`pyproject.toml` の下限指定は API 互換の床であり、導入版の情報源としてはならない。宣言ファイル [hve/copilot-sdk.lock](hve/copilot-sdk.lock) 自体は UTF-8 / LF / BOM なしで保持しなければならない。`--upgrade-sdk` / `-UpgradeSdk` の書き換え処理は当該形式を維持したまま pin 行と CLI ランタイム記録行だけを更新しなければならない。
- **FR-MODEL-08**: 開発環境セットアップは、Windows / macOS / Linux のいずれでも外部 `copilot` コマンド（npm パッケージ `@github/copilot`）を**最新版へ導入・更新**しなければならない。未導入時は `@github/copilot@latest` を導入する（他の OS ツールと同じ確認プロンプトに従い、`-Yes` / `-y` で省略できる）。導入済みかつ npm グローバル管理下の場合は確認なしで `@github/copilot@latest` へ更新しなければならない。`copilot` が解決できるのに npm グローバル管理下でない場合は、二重導入で PATH 解決が分岐するため npm 導入を行わず、警告と更新手順を提示しなければならない。`--no-install-tools` / `-NoInstallTools` と `--check-only` / `-CheckOnly` は導入・更新を抑止し、検出結果の報告だけを行わなければならない。npm が解決できない場合は Node.js の導入手順とともに警告しなければならない。本 CLI は GUI の Copilot チャットパネル（FR-GUI-10）の前提であり、SDK が pin する Step 実行用ランタイム（FR-MODEL-07）とは独立に自己更新するため、`COPILOT_CLI_PATH` 等で Step 実行へ流用してはならない。

### 3.5.1 Tool Search ランキングの HVE 実装（FR-TS）

FR-MODEL-04 が「SDK 組み込みツール検索を有効化する設定」を規定するのに対し、本節は「有効化したときの**ランキングを HVE 実装へ差し替える**」ことを規定する。両者は直交し、FR-MODEL-04 の bool 契約（`--tool-search` / `--no-tool-search`）の意味を変更してはならない。

- **FR-TS-01**: HVE は SDK 組み込みの `tool_search_tool` を、`define_tool(name="tool_search_tool", overrides_built_in_tool=True)` で登録した HVE 実装へ差し替えられなければならない。差し替え実装は `ToolInvocation.available_tools`（SDK が当該ツール呼び出し時にだけ渡すライブカタログ）を唯一のカタログ入力とし、HVE 側から MCP へ `tools/list` 等の RPC を発行してはならない。発見結果は `ToolResult.tool_references`（ツール名の列）で返し、定義展開は SDK に委ねる。差し替え対象名は SDK 側の定数（`copilot.session._TOOL_SEARCH_TOOL_NAME`）と一致していなければならない。
- **FR-TS-02**: 検索対象は `ToolEntry`（`id` / `kind` / `server` / `name` / `description` / `arg_terms` / `additional_search_text` / `pin` / `deferred`）へ正規化する。`arg_terms` は入力スキーマの引数名と引数説明を**ネスト 3 階層まで**平坦化した語彙とする。`additional_search_text` は索引にのみ用い、モデルへ返す `ToolCard` に含めてはならない。カタログのスナップショットが `None` の場合は例外とせず空カタログとして扱う。
- **FR-TS-03**: pin ポリシーは次の優先順位で解決する（高→低）: 既存 fail-closed MCP ガード（`_require_trusted_asdw_data_deploy_mcp_servers` / `_require_trusted_foundry_mcp_servers` / `enable_config_discovery=False`）> `available_tools` / `excluded_tools` > step 別 override > `hve/skill_manifest.json` 由来の pin > `policy.json` の pins > 利用履歴による自動 pin > 検索結果。fail-closed ガードが有効な Step では検索による発見を行わず pin のみを公開しなければならない。**ただしランキング実装が制御できるのは「何を返すか」だけであり、呼び出しの禁止を強制する力は持たない。** 禁止の強制は `excluded_tools` と MCP サーバー設定の `tools` allowlist（`[]` = なし）で行い、ランカーを安全境界として扱ってはならない。
  - **`policy.json` の解決先は、実行時・表示・保存のすべてで同一でなければならない。** 解決規則は単一実装（[hve/toolsearch/policy.py](hve/toolsearch/policy.py) `ToolSearchPolicy.default_path()`）が所有し、呼び出し側がリポジトリルートを明示し、かつその直下に `.toolsearch/policy.json` が存在する場合はそれを、それ以外は同梱の `hve/toolsearch/policy.json` を用いる（FR-MAINT-07）。実行時だけリポジトリルートを渡さずにローカルの上書きを無視してはならない。無視すると、GUI（FR-GUI-07）で表示・保存した内容と実際に効くポリシーが食い違う。読み込みに失敗した場合は差し替えを行わず SDK 既定へフォールバックし、Step を落としてはならない。
- **FR-TS-04**: ランキングはフィールド重み付き BM25 とし、日本語クエリで機能しなければならない（CJK 連続は隣接バイグラムへ分割する。[mdq/tokenize.py](mdq/tokenize.py) `scoring_terms` を再利用する）。返却件数は上限（既定 5、最大 10）に加えて `score >= tau * top_score` の適応的打ち切りを行い、全件が閾値未満のときは空を返す。BM25 実装は利用可能なものから順に選択し、追加依存が無い環境でも動作しなければならない。
- **FR-TS-05**: 検索品質は golden クエリ集合に対する Recall@k で評価可能でなければならない。**あわせて、全ツール定義を前置きした場合の推定トークン量と、pin のみ + 検索返却分の推定トークン量を算出し、削減率を測定可能としなければならない。** FR-MODEL-04 が削減効果を受入対象外としているのは同要件の範囲についてであり、本要件での測定を妨げない。
- **FR-TS-06**: Skill（`.github/skills/**/SKILL.md` および外部 Skill ルート）も検索対象に含めなければならない。Skill は SDK の `available_tools` に現れないため、HVE は各 Skill をツールとして登録し、カタログへ合流させる。Core Skill は常時公開、それ以外は遅延公開とし、**平素使わない Skill でも必要な場面で発見できなければならない**。`disabled_skills` による一括無効化を long-tail Skill の唯一の手段としてはならない（発見不能になるため）。
- **FR-TS-07**: 利用履歴に基づく自動 pin を備えなければならない。ウォームアップ期間の後に頻繁に呼ばれるツールを pin へ昇格させ、使われなくなったエントリは失効させる。昇格の単位は prompt cache の prefix 安定性を優先して **workflow × step 単位の決定論**とし、同一入力に対して常に同一の pin 集合を同一順序で返さなければならない。利用履歴は追記専用の JSONL（既定 `<repo-root>/.toolsearch/usage.jsonl`、`HVE_TOOLSEARCH_USAGE` で差し替え）へ保存する。`<repo-root>` は呼び出し側が明示したリポジトリルートとし、明示が無い場合はカレントワーキングディレクトリとする。
- **FR-TS-08**: 遅延公開が発火していないことを検知できなければならない。SDK の `defer_threshold` の既定値はサーバー側にありクライアントから静的に確認できないため、ツール総数が閾値未満だと差し替えたランカーが一度も呼ばれず機能が不活性になる。`available_tools` に `defer_loading=True` のエントリが 0 件の場合は警告を発出しなければならない。**本検知が動くのは `tool_search_ranking="hve"` のときだけである**（既定の `sdk` では差し替えランカーを登録せず、`available_tools` を受け取る経路自体が存在しない）。既定経路での検知は本要件の対象外とする。なお 2026-08-13 の実測（Copilot CLI 1.0.79 / SDK 1.0.7）では、`defer_threshold=1` を指定しても全 183 ツールの `defer_loading` が `null` のままで、遅延公開は一切発火しなかった。
- **FR-TS-09**: 差し替えたランカーの動作は実行時に観測可能でなければならない。`ToolSearchContext.on_event` が発火する `toolsearch.catalog` / `toolsearch.query` / `toolsearch.miss` を追記専用の JSONL（既定 `<repo-root>/.toolsearch/events.jsonl`、`HVE_TOOLSEARCH_EVENTS` で差し替え）へ逐次追記する。`<repo-root>` は FR-TS-07 と同一の解決規則に従う。各イベントは少なくとも発生時刻・schema バージョン・workflow / step・カタログ構成（総数 / pinned / searchable / kind 別内訳 / deferred 数）・検索レイテンシ・返却ツール名とスコア・推定トークン量（全定義前置き相当と実公開分）・FR-TS-08 警告の有無を含む。検索専用語彙（`additional_search_text`）とクエリ以外の会話内容を記録してはならない。収集は best-effort とし、書き込み失敗・集計失敗で Step を落としてはならない。
- **FR-TS-10**: 収集した統計を人間が確認できるダッシュボードを提供しなければならない。CLI（`hve toolsearch dashboard`）はテキスト / JSON / 自己完結 HTML の各形式で描画でき、`--follow` 指定時は一定間隔で再集計して表示を更新する。指標は収集済みイベントと利用履歴（FR-TS-07）だけから算出し、データが不足する指標は 0 や推定値で埋めず「データ不足」と明示しなければならない。HTML 出力は外部ネットワークへ接続してはならない（CDN・外部フォント・リモート画像を参照しない）。**`token_reduction` は遅延公開が発火していない環境では削減率として成立しない。`deferral_inactive_rate` が 1.0 のときは削減率として表示してはならず、無効である旨とその理由を表示しなければならない。JSON 出力では値を残してよいが、無効であることを示すフィールドを併せて出力しなければならない。**
- **FR-TS-11**: Step 実行セッションのコンテキスト内訳を実測する CLI を提供しなければならない。`hve toolsearch context` は、[hve/runner.py](hve/runner.py) `_create_session_with_auto_reasoning_fallback` と同じ経路でセッションを生成し、`session.metadata.contextInfo` と `session.metadata.getContextAttribution` から、システムプロンプト / 組み込みツール定義 / MCP サーバー別の実トークン量とツール数を取得してテキストまたは JSON（`--json`）で出力する。`session.send` を行ってはならず、モデル推論を発生させてはならない。`hve/toolsearch/eval.py` のトークン推定で代替してはならない。測定に用いたモデル名（`contextInfo.modelName`）を出力に含めなければならない。`.github/.mcp.json` が宣言する MCP サーバーの接続完了を待ってから測定し、待っても接続しなかったサーバーは未接続として報告しなければならない（実測: stdio の `azure` は接続に 3.7〜5.1 秒）。測定に失敗した場合は非 0 の終了コードと失敗理由を返し、推定値や前回値で埋めてはならない。取得と整形の実装は単一とし、GUI（FR-GUI-07）は本 CLI を呼び出すか同じ実装を共有しなければならない（FR-MAINT-07）。**測定セッションは Step 実行と同じ設定モデル（`to_wire_model(SDKConfig.model)`）および `context_tier` で生成しなければならない**。あわせて、出力には `contextInfo.modelName` に加えて**セッションへ渡した設定モデル**を含めなければならない（未指定の場合はその旨を示す）。実測では `contextInfo.modelName` はセッションモデルに関わらず `claude-sonnet-4.5` を返す一方、`session.metadata.getContextAttribution` 由来の層別内訳はセッションモデルに依存して変化する（`MODEL=claude-opus-4.7` 指定時、`modelName` は不変のまま azure MCP の層別内訳が 15,047 → 18,047 tokens へ増加、`contextInfo.mcpToolsTokens` は 17,302 で不変）。両者は異なるトークナイザで計測されているため、`contextInfo.toolDefinitionsTokens` と層別内訳の合計との差分を、欠損・未計上・不整合として提示してはならない。

### 3.6 セキュリティ

- **NFR-SEC-01**: `GH_TOKEN`・`COPILOT_PAT` 等の秘密情報を Issue body / 標準出力に出力してはならない。Resume 用 `state.json` と `config_snapshot` 復元は §5.6 のとおり廃止済みであり、現行要件ではない。
  - FR-STATE-04 の durable store と resume plan は固定 allowlist とし、状態、時刻、数値、model ID、Workflow / Step / APP 識別子、sanitized replay descriptor、hash、例外型名だけを保存できる。prompt/response/reasoning 本文、tool 引数・結果、任意環境変数、token/credential、認証 URL、生 SDK payload、生 repository root を保存してはならない。
  - 保存不可の必須 replay 値は値を保存せず `missing_replay_keys` の key 名だけを保存する。resume 時は対話入力、GUI の current input、または Prompt の自然言語入力から再取得し、non-TTY で不足する場合は実行を開始してはならない。
- **NFR-SEC-02**: `docs-original/` 配下は全 Agent から読み取り専用とする（`.github/copilot-instructions.md` §0）。
- **NFR-SEC-03**: `git add` 時は `:!path` pathspec 除外で機密ファイルを除く。pathspec はリスト引数として渡し、shell インジェクションを防止する（[hve/orchestrator.py](hve/orchestrator.py) `_git_add_commit_push`）。

### 3.7 HVE アプリケーション保守の要求トレーサビリティ

#### 対象境界

本節は HVE アプリケーション自体を保守する変更に適用し、HVE が生成・支援する他アプリケーションの成果物には適用しない。

- パスは `/` 区切りのリポジトリ相対表記へ正規化し、絶対パス、空セグメント、`.` / `..` セグメント、リポジトリ外を拒否する。
- rename は旧・新の両パスを評価し、いずれか一方が対象なら HVE 対象変更とする。変更パスの取得・正規化に失敗した場合は fail-closed とする。
- 下表を上から評価し、対象外に一致したパスを対象へ戻してはならない。どのパターンにも一致しないパスは HVE 対象外とする。fail-closed は変更パスの取得・正規化・matcher 実行に失敗した場合に限る。`CHANGELOG.md` は単独変更ではゲートを起動せず、他の HVE 対象変更と同時に変更された場合だけ PR 全体のゲート対象に含まれる。`users-guide/**` も同じ扱いとする。利用者向けドキュメント本文は実行時に観測できる挙動を持たず、単独変更では要件 ID・テストパスの実質的な申告対象が存在しないためである。コード変更に伴うドキュメント同期は、同一 PR 内の他の対象パスによってゲートが起動するため担保される。

| 判定 | リポジトリ相対パターン |
|---|---|
| 対象外 | `src/**`, `docs/**`, `docs-generated/**`, `knowledge/**`, `qa/**`, `docs-original/**`, `sample/**`, `work/**`, `tests/run/**`, `hve.egg-info/**`, `tools/hve-app-cash/**` |
| 対象外 | `.github/workflows/deploy-*.yml`, `.github/workflows/azure-static-web-apps-*.yml`, `.github/workflows/app[0-9]*.yml` |
| 対象外 | `package.json`, `jest.config.js`, `babel.config.js`, `playwright.config.js`, `CHANGELOG.md`（単独変更時）, `users-guide/**`（単独変更時） |
| 対象 | `hve/**`, `mdq/**`, `cq/**`, `hve-dev/**`, `template/**`, `tools/skills/markdown_query/**`, `tools/skills/code_query/**`, `tools/runner/**`, `tools/*.py` |
| 対象 | `.github/copilot-instructions.md`, `.github/instructions/**`, `.github/skills/**`, `.github/prompts/**`, `.github/io-contracts/**`, `.github/scripts/**`, `.github/ISSUE_TEMPLATE/**`, `.github/workflows/**` |
| 対象 | `hve/tests/**`, `hve/gui/tests/**`, `mdq/tests/**`, `mdq/gui/tests/**`, `cq/tests/**`, `tests/bats/**` |
| 対象 | `pyproject.toml`, `mdq.toml`, `cq.toml`, `hve.cmd`, `hve.sh`, `.vscode/tasks.json` |

- 対象パスの機械判定は単一の validator に集約する。path-specific instructions は自動適用範囲を `hve/**`, `mdq/**`, `cq/**`, `hve-dev/**`, `tools/skills/markdown_query/**`, `tools/skills/code_query/**` に限定し、それ以外の HVE 対象は repository-wide の短いルーターから同じ Skill へ委譲する。CI との境界差は契約テストで固定する。

#### 版管理境界

`.github/copilot-instructions.md` §0「HVE の版管理と変更履歴」は HVE 対象変更を含むジョブへ HVE パッケージ版の更新を要求し、その対象判定の機械正本を対象境界の実装モジュールと定めている。一方で版更新を要求するパスの集合は対象境界と一致せず、対象境界からさらに 2 つの部分集合を除いたものになる。本項はその差分を機械判定可能にする。

- **FR-MAINT-08**: 変更パスが HVE パッケージ版（`pyproject.toml` の `[project].version` と `[tool.bumpversion].current_version`、`hve/__init__.py` の `__version__`）の更新を要求するかどうかの判定は、対象境界を所有するモジュールが持つ単一実装とする。判定は対象境界の判定結果を入力とし、対象境界に一致するパスから (1) 版番号と変更履歴の同期先ファイル自身、(2) `hve-dev/hve-app-tools.md` §7 が独立ライフサイクルと定めるパス（`mdq/**`, `cq/**`, `tools/skills/markdown_query/**`, `tools/skills/code_query/**`）を除いたものだけを、版更新を要求するパスとする。(1) を除かなければ版更新のための変更自体が次の版更新を要求し、規則を充足できる状態が存在しなくなる。(2) を除かなければ独立に版管理する成果物の変更が HVE パッケージ版と連動する。(1) の列挙は `pyproject.toml` の `[tool.bumpversion]` 設定を単一の情報源とし、設定と乖離した独自の列挙を保持してはならない。対象境界の判定表を版管理側で再宣言してはならず、対象境界に一致しないパスを版更新の対象へ戻してはならない。`mdq.toml` / `cq.toml` は (2) の列挙に含めず、版更新を要求するパスとして扱う。両者は engine 本体ではなくリポジトリ側の設定であり、§0 の除外列挙が `mdq/**` / `cq/**` / 配布キットに限られるためである。§0 の列挙と本実装が食い違う場合は本実装を正とする。

#### 変更種別

| 種別 | 判定規則 |
|---|---|
| `feature` | 利用者または外部システムから観測できる能力・動作・公開インタフェース・設定・Workflow / Prompt / I/O 契約を追加または変更する。複数解釈があり分類を確定できない場合も `feature` とする |
| `bugfix` | 既存の規範要件または明示済み受入条件を満たさない挙動を、その既存契約へ戻す。新しい能力や契約は追加しない |
| `maintenance` | 実行時の観測可能な挙動を変えない文書、テスト、内部整理、依存・ビルド保守。HVE 対象変更を `maintenance` と申告する場合は常に人間レビュー必須とする |

CI は記載値・参照整合性を検証し、自然言語上の分類理由やテストの意味的妥当性は捏造せず人間レビューへ委ねる。

#### PR トレーサビリティブロック

HVE 対象変更を含む PR は、次のマーカーと 8 キーを各 1 回だけ、例示順で含める。marker 内の未知キーを認めない。キー名は大文字小文字を区別し、値の未置換プレースホルダー（`REPLACE_ME`）、改行を含む値、キーの重複を認めない。複数の ID / path は `, ` 区切りとする。

```markdown
<!-- hve-traceability:start -->
- Change-Type: feature
- Change-Type-Reason: 変更種別を選んだ具体的理由
- Requirement-IDs: FR-MAINT-01, NFR-CTX-01
- Requirement-N/A-Reason: N/A
- Test-Paths: hve/tests/test_hve_requirement_traceability_contract.py
- Test-N/A-Reason: N/A
- TDD-Evidence: RED=実装前の失敗結果; GREEN=実装後の成功結果
- Manual-Review-Required: no
<!-- hve-traceability:end -->
```

- `Requirement-IDs` が実値の場合は `Requirement-N/A-Reason: N/A`、`Test-Paths` が実値の場合は `Test-N/A-Reason: N/A` とする。この companion field の sentinel `N/A` は全変更種別で使用できる。
- 要件を省略する `Requirement-IDs: N/A` またはテストを省略する `Test-Paths: N/A` を使えるのは `bugfix` / `maintenance` だけで、対応する Reason field の具体的理由と `Manual-Review-Required: yes` を必須とする。`maintenance` は省略の有無にかかわらず `Manual-Review-Required: yes` とする。リポジトリの branch protection が要求する承認レビューを省略してはならない。
- 許可するテストパスは `hve/tests/**`, `hve/gui/tests/**`, `mdq/tests/**`, `mdq/gui/tests/**`, `cq/tests/**`, `.github/scripts/tests/**`, `.github/scripts/python/tests/**`, `.github/scripts/powershell/tests/**`, `tests/bats/**` に限る。
- 要件 ID を記載した場合、各 ID は要求テストマッピングに存在し、各 ID のマッピング節には `Test-Paths` の少なくとも 1 件が記載されていなければならない。
- `feature` の `TDD-Evidence` は同じ対象テストについて実装前 RED と実装後 GREEN の両結果を含める。`bugfix` は再現テストの修正前失敗と修正後成功、`maintenance` は実行した回帰検証、または理由付き `N/A` を記録する。

- **FR-MAINT-01**: Coding Agent は HVE 対象ファイルを変更する前に、`hve-dev/hve-feature-inventory.csv` を索引として適用候補を絞り込み、`hve-dev/requirement-definition.md` の関連箇所と `hve-dev/requirement-test-mapping.md` の対応箇所を確認しなければならない。適用できる要件 ID は、要求定義書を source とし、索引上 `active-or-described` であるものに限る。未知、競合、`deprecated-or-removed`、`partial-or-not-supported` の ID を現行要件として適用してはならない。新規 ID を追加する bootstrap 中は要求定義書の定義行を一次情報とし、要求テストマッピングと RED テストを追加後、実装前に索引を再生成して当該 ID・source・status・テストパスを照合する。既存 ID では索引と要求定義書が矛盾した場合、推測せず不整合を解消してから実装へ進む。`hve-requirement-traceability` Skill は §1.3 の 3 層優先順位と §3.7 の変更種別判定規則を保持し、Coding Agent が要求定義書本文を追加取得せずに適用可否と変更種別を判定できるようにしなければならない。
- **FR-MAINT-02**: Coding Agent は要求書全文を既定の入力にせず、Issue 本文、対象パス、対象 symbol、失敗テスト、Workflow / Step ID を検索キーとして関連チャンクを取得する。要件 ID が既知の場合は検索を行わず、`hve-dev/hve-feature-inventory.csv` の当該行の `line` 列が指す定義行だけを読む。ID が未知の場合に限り検索を行う。初回取得で不足する場合に限り、親見出し、隣接チャンク、関連章の順に一段ずつ拡張する。0 件または矛盾時は検索語を変えて最大 2 回再試行し、それでも解消できなければ理由を記録して確認を求める。索引欠損・stale・検索 CLI 障害時は、既に特定した要求 ID または見出しの限定範囲を read / grep で取得し、要求書全文へ自動 fallback しない。本規則は HVE 要件検索において汎用 Markdown 検索 fallback より優先する。全文取得は、ユーザーの明示要求、要求定義書自体の横断改訂、または章単位でも解消できない複数章の矛盾がある場合に限る。ID 直引きを検索より優先するのは次の実測を根拠とする: 同一の問いに対し BM25 の chunk 返却が 3,613 tokens / 151 ms であるのに対し、索引の `line` 列からの直引きは 501〜687 tokens で検索を伴わない。
- **FR-MAINT-03**: `feature` 変更は、要求定義への active 要件追加または改訂 → 要求テストマッピングへの受入テスト追加（未実装時は `要追加`）→ 失敗するテストの作成と RED 確認 → 機能・テスト索引の再生成と新規 ID / test path の照合 → 実装 → 同じ対象テストの GREEN 確認 → 要求テストマッピングへの実結果反映、の順で行う。`feature` では要件 ID、実在テストパス、RED / GREEN 証跡の省略を認めない。`bugfix` / `maintenance` で要件またはテストを `N/A` とする場合は、前項のブロックへ具体的理由と人間レビュー必須を記録する。`hve-dev/hve-tdd-change-policy.md` と生成元が本節と矛盾する場合は本節を正とし、同一変更で同期する。本要件の初回導入では、下記「本要件の導入ゲート」を FR-MAINT-03 の従属規範として適用する。
- **FR-MAINT-04**: HVE 対象変更を含む PR は、前項のトレーサビリティブロックを記録しなければならない。CI は変更パス取得失敗、ブロックの欠落・重複・未置換値、組合せ違反、未知または索引statusが `active-or-described` 以外の ID、存在しない・リポジトリ外・許可テストルート外のパス、要件 ID と要求テストマッピング上の test path 不一致を拒否する。`feature` では要求定義、要求テストマッピング、機能索引の更新と RED / GREEN 証跡を追加で要求する。N/A と変更種別の意味的妥当性は CI が推測せず、既存 branch protection の承認レビューで確認する。HVE 対象外の変更のみである場合は本ゲートを適用しない。validator の正規entrypointは `.github/scripts/validate-hve-requirement-traceability.py` とし、リポジトリroot、PR本文ファイル、変更パス一覧ファイルを明示入力として受け取る。PR workflow は `pull_request` イベントだけで当該 validator を必須ゲートとして実行し、PR本文を shell の `run` へ直接展開せず、最小読取権限で実行する。既定ブランチで実行するtrusted workflowは `pull_request_target` を使用し、base側validatorとPR内容を別ディレクトリへcheckoutし、PR内容はデータとして検証するだけで実行してはならない。branch protection の required status check は両workflow名とvalidator job名から構成されるcheck contextを含み、承認レビューを1件以上要求しなければならない。管理者による直接 push を許容するため、`.github/CODEOWNERS` に一致する変更でも Code Owner 承認を追加要件とせず、管理者には branch protection を強制しない（`require_code_owner_reviews=false`、`enforce_admins=false`）。
- **NFR-CTX-01**: repository-wide instructions のうち **HVE 要求トレーサビリティに関する記述**は検索ルーターだけを保持し、要求定義書本文を埋め込んではならない。当該ルーターは、(1) HVE 対象変更または HVE 対象パスの不具合調査で `hve-requirement-traceability` Skill を使用する、(2) HVE コアパスでは path-specific instructions も適用する、(3) 要求定義書全文を既定の入力にしない、の 3 箇条だけで構成する。CI はルーターの見出し・3 箇条・Skill 参照・要求書パス・既知の要件 ID / schema key /取得オプションの重複を決定論的に検査する。Coding Agent は customization の raw source を入力として受け取るため、既知識別子の重複検査は HTML comment、code span、fenced / indented code を含むルーター外の raw source 全体を対象とする。言い換えによる意味的な分散・矛盾は捏造して判定せず人間レビューへ委ねる。他のリポジトリ共通ルールは本要件の対象外とする。初回の関連要件取得は最大 5 チャンクかつ最大 800 tokens を上限とし、追加コンテキストは FR-MAINT-02 の段階的拡張でのみ取得する。

#### 本要件の導入ゲート

FR-MAINT-01〜04 / NFR-CTX-01 の追加後、要求テストマッピング、RED 契約テスト、TDD policy の生成元、機能・テスト索引、PR validator / workflow を同一変更セットで同期し、全契約テストを GREEN にするまで、HVE 保守機能の実装完了を宣言してはならない。途中状態では新規 ID が索引に無いことを理由に既存要件へ偽装せず、bootstrap 中であることを明記する。

#### 実行面横断の重複実装防止

HVE は Cloud Agent Orchestrator / CLI Orchestrator / GUI Orchestrator の 3 実行面と、それらが共有する中核モジュールから構成される。同一の規範ルールが複数の実行面へ個別に実装されると、受理集合や検査項目が面ごとに乖離する。本項はその乖離を機械的に検出可能にする。

本項で **規範リテラル** とは、`.github/copilot-instructions.md` または Skill が規定するルールを機械判定するために実装が直接参照する固定文字列またはキー名を指す。

- **FR-MAINT-05**: HVE 対象の実装シンボル索引を `hve-dev/hve-surface-inventory.csv` として機械生成する。生成の正規 entrypoint は `hve-dev/generate_tdd_inventory.py` とする。索引対象は §3.7 対象境界の判定に一致するパスだけとし、当該判定は「対象パスの機械判定は単一の validator に集約する」原則に従って既存判定を再利用し、別の範囲定義を作ってはならない。索引は同一入力に対して決定的に生成し、対象外パスに由来する行を含めてはならない。索引の各行は、実行面（`cloud` / `cli` / `gui` / `core`）、シンボル種別、定義ファイルと行、振る舞い要約、当該シンボルが参照する規範リテラルの集合を保持する。CI は、生成スクリプトの出力と索引が不一致の場合、または対象外パスの行を含む場合に失敗させる。不一致の索引は stale として扱い、再生成するまで FR-MAINT-06 / FR-MAINT-07 の判断根拠に使ってはならない。参照数を表す列は静的解析による値であり、CI から `pytest <path>` や `python -m <module>` で起動される経路を数えない。当該列だけを根拠に未使用と判断してはならない。本索引は HVE アプリケーション自体だけを対象とし、HVE が生成・支援する他アプリケーションの成果物を含めてはならない。後者のスコープ解決は `app-scope-resolution` Skill と生成物側のカタログが担う。
- **FR-MAINT-06**: 規範リテラルを判定する実装は、リテラルごとに単一とする。同一の規範リテラル（例: タスク完了報告の検証マーカー、`plan.md` の分割判定メタデータ）を判定する実装が複数の実行面に併存してはならず、他面は単一の実装を呼び出す。CI は FR-MAINT-05 の索引を用いて、規範リテラルごとの判定実装数を決定論的に検査し、許可された単一実装以外を検出した場合は失敗させる。検査対象の規範リテラルと許可実装は明示リストで固定し、リストに無いリテラルを推測して判定してはならない。規範リテラルを**生成する**側の文言複製は本要件の対象外とする。複製の維持を意図する根拠文書がリポジトリ内に存在する箇所（vendoring 等）も対象外とし、その根拠を許可リストに明記する。
- **FR-MAINT-07**: Coding Agent は、HVE 対象パスへ新規の判定・生成・検証ロジックを追加する前に、FR-MAINT-05 の索引を用いて既存実装の有無を確認しなければならない。確認は規範リテラル一致 → 振る舞い要約 → シンボル名の順に行う。この順序は、名前や構文の類似だけでは識別子の異なる同一手続きへ到達できないために定める。シンボル名の不一致だけを根拠に既存実装が無いと判断してはならない。複数の実行面に同一ルールの実装が存在する場合は新規実装を追加せず、単一実装へ寄せる。索引に一致が無い場合に限り新規実装を許可し、どの実行面を単一実装とするかをタスク完了報告へ記録する。本手順は `hve-requirement-traceability` Skill に置き、NFR-CTX-01 を維持するため repository-wide instructions へ手順本文を追加してはならない。本手順は HVE 対象変更にだけ適用し、HVE が生成・支援する他アプリケーションの成果物には適用しない。
- **FR-MAINT-09**: §13 の各 Workflow 節が持つ Step 表と [hve/workflow_registry.py](hve/workflow_registry.py) の StepDef 集合は一致しなければならない。検査は次を満たす単一の実装（[hve/tests/test_requirement_section13_parity.py](hve/tests/test_requirement_section13_parity.py)）が担い、Workflow ごとの個別テストで同じ検査を重複実装してはならない（FR-MAINT-07）。
  - Workflow ごとの検査モード（全 Step 一致 / 要約表としての部分集合）と、§13 に節を持たない Workflow の除外を明示リストで固定し、除外には理由を記載する。除外を理由なく追加してはならない（FR-WF-OUT-09 の allowlist と同じ方式）。
  - registry へ登録済みの Workflow が検査モードにも除外リストにも無い場合は失敗させる。新規 Workflow を追加した変更で §13 の同期を忘れることを防ぐためである。
  - Step ID 列には ID として解釈できるトークンだけを置く。要約表では範囲表記（`2.1〜2.5`）に限り許容する。実装に存在しない ID（過去の `2.3T` / `3.0T` 等）を残してはならない。
  - 表の Step タイトルは registry の同一 Step を指していなければならない。表記揺れで検査が壊れないよう、記号・空白・連体助詞「の」を除去した正規化後の包含で判定する。
  - 依存・Fan-out・生成ファイルの一致は本要件の対象外とする。これらは列構成が節ごとに異なり、機械検査を成立させるには §13 全体の表形式統一が前提になるためである。表を編集する変更では、当該行の値を registry と照合して同時に正す。
  - 本要件は、同種の乖離が §13.5（ADFDV: 旧称 ABDV と実在しない fan-out parser の残存）と §13.12（ARD: 旧 7-Step 表記）で個別に発生し、そのつど当該 Workflow だけのテストで塞いだ結果、§13.2（AAD-WEB: Step 2.4 / 2.5 / 2.6 の欠落）と §13.3（ASDW-WEB: Step ID 体系が実装と系統的に不一致）へ同じ乖離が残存していたことを根拠とする。
- **FR-MAINT-10**: HVE GUI に影響する保守変更で macOS 検証が必要な場合、Coding Agent は `hve-requirement-traceability` Skill が定める変更影響の判定表に基づいて検証要否と `smoke` / `full` の範囲を判定し、判定不能なら利用者へ確認しなければならない。課金されうる GitHub-hosted macOS runner を起動する前に、(a) 必要性と対象変更、(b) runner label / architecture / test scope、(c) 公式単価とその確認日および出典 URL、(d) 予測実行時間と予測課金額、(e) timeout（分）×単価（USD/分）で算出した最大額、(f) free minutes 残量を取得できない場合は実請求額が 0 から最大額までになりうることを提示し、利用者の明示承認を得なければならない。承認は当該見積りに対する特定 workflow run 1 回だけに有効とし、失敗、workflow run の cancel、または rerun には新しい見積りと承認を要求する。承認が無い場合は workflow を dispatch してはならない。
  - macOS GUI test workflow は `workflow_dispatch` だけを trigger とし、`push` / `pull_request` / `schedule` で自動起動してはならない。`cost_approved` は既定 `false` とし、`estimated_cost_usd` が空の場合も macOS job を開始してはならない。
  - `smoke` は Qt platform plugin が `cocoa` であることを検査する。macOS run での Python 例外、ウィンドウ生成失敗、または test skip は job failure とする。Qt Warning / Critical / Fatal の許可リストは初期状態を空とし、実測で無害と確認したメッセージだけを根拠とともに追加でき、それ以外は job failure とする。`offscreen` の成功を `cocoa` の成功として扱ってはならない。
  - `full` は利用者が当該 scope を別途選択した場合にだけ、既存 `hve/gui/tests` の offscreen 全量と同じ `cocoa` smoke を別プロセスで実行する。初期実装では新しい GUI automation framework、TCC 権限変更、OS / architecture matrix、新規 test dependency を追加しない。
- **FR-MAINT-11**: branch protection の required context である `Test HVE Python / HVE Python Tests` と `Test HVE Python / mdq index smoke test` は、`main` を対象とする全 Pull Request の最新 SHA へ結果を報告しなければならない。`.github/workflows/test-hve-python.yml` の `pull_request` trigger に `paths` / `paths-ignore` を置いて Workflow 全体を未起動にしてはならない。既存の重いテスト範囲は単一の変更パス検出 job で判定し、対象外 PR でも required 名の 2 job 自体は起動して成功を報告する。変更パスの取得に失敗した場合は両 required job を失敗させ、成功として扱ってはならない。本要件のために外部 Action、別 Workflow、利用者向け無効化 flag を追加してはならない。

### 3.8 markdown-query（mdq）検索品質の回帰計測

`mdq` は HVE 本体の要件検索（FR-MAINT-02）と、HVE が生成する成果物カタログの参照に共用される。検索品質の劣化は両者へ同時に波及するため、変更の効果と回帰を機械計測可能にする。

- **FR-MDQ-01**: `mdq` 検索の回帰計測として、ゴールデンクエリ集に対する top-1 正解率と top-k 正解率を機械算出する。ゴールデンクエリの各項目はクエリ文字列と 1 件以上の期待着地点を持ち、期待着地点はリポジトリ相対パスと行番号の対で表す。正解判定は、ヒットのパスが期待パスと一致し、かつヒットの行範囲（開始行と終了行の閉区間）が期待行番号を含むことをもって行う。パス一致のみを根拠に正解と判定してはならない。行範囲情報を持たないヒットは不正解として扱う。判定実装は単一とし、`tools/skills/markdown_query/benchmark.py` は当該実装を呼び出して独自の正解判定を実装してはならない。ゴールデンクエリ集に実在しないパスまたは対象ファイルの行数を超える行番号が含まれる場合は fail-closed とし、計測を実行してはならない。機械生成される索引（`hve-dev/*.csv` 等）を期待着地点にする項目は、当該行に含まれる部分文字列を必須とし、再生成による行番号のずれを fail-closed で検出しなければならない。計測に使用した索引 DB のパスをレポートへ記録し、どの索引に対する計測かを監査可能にしなければならない。
- **FR-MDQ-02**: `mdq` は、設定で宣言された表形式ファイル（CSV / TSV）を索引対象に含める。宣言が無い場合は表形式ファイルを索引してはならない（他リポジトリへの移植性を保つため既定は空とする）。索引単位は 1 データ行 = 1 チャンクとし、ヘッダ行はチャンクにしない。チャンクの開始行・終了行は当該レコードの物理行番号とし、引用符内改行を含むレコードでは開始行と終了行が異なる値になる。チャンク本文は空でない全列を「列名: 値」形式で改行連結する。文脈ヘッダは、拡張子を除いたファイル名に続けて先頭 3 列の「列名=値」を連結した機械生成値とし、LLM を使用してはならない。先頭 3 列の「列名=値」をタグとして保持し、列値によるフィルタを可能にする。表形式ファイルの行チャンクは chunking strategy に依存せず、どの strategy の索引でも同一内容を生成する。増分更新・prune は Markdown と同一の既存判定を再利用し、表形式ファイル専用の更新判定を新設してはならない。
- **FR-MDQ-03**: `mdq` の検索応答は、ヒットの抜粋をどの単位で返すかを呼び出し側が選択できなければならない。選択肢は、ヒット行を中心とする行範囲と、ヒットを含むチャンクの本文全体の 2 つとする（本文を含めない第 3 の選択肢は FR-MDQ-10 が追加する）。既定は前者とし、指定が無い場合に後者へ切り替えてはならない（Context Window 消費の最小化を既定の振る舞いとして維持するため）。応答トークン予算の算定は単位によらず同一の実装で行い、単位ごとに別の予算計算を実装してはならない。予算超過時は先頭 1 件を必ず返したうえで打ち切る。返却単位の違いによって、strategy 選定、ヒット対象チャンクの決定規則、およびヒットの順位を変えてはならない。同一予算のもとでは抜粋が長い分だけ応答件数が減るが、これは予算規則の帰結であり本規定に反しない。
- **FR-MDQ-04**: `mdq` 検索の回帰計測は、top-1 正解率・top-k 正解率に加えて MRR@k を機械算出する。MRR@k は、先頭 k 件のうち最初の正解ヒットの順位の逆数をクエリごとに求め、その平均とする。k 件内に正解が無いクエリの寄与は 0 とする。順位の判定は FR-MDQ-01 の正解判定実装を用い、別の正解判定を実装してはならない。計測は、ゴールデンクエリ集が宣言する対象パス絞り込みを適用する条件と、当該絞り込みを適用せずリポジトリ全体を候補とする条件の双方で実行できなければならず、両条件の結果はレポート上で区別可能でなければならない。ヒットの順位付けに影響する既定値を変更する場合は、当該既定値の決定に用いたゴールデンクエリ集と、決定に用いていない別のゴールデンクエリ集の双方で計測し、双方の結果を変更の根拠として記録しなければならない。
- **FR-MDQ-05**: `mdq` の既定検索経路は、チャンク本文に加えて当該チャンクの見出し経路を語彙照合の対象に含める。見出し経路にだけ現れる語であっても、当該チャンクへ到達できなければならない。見出し経路の連結はスコアリングのためだけに用い、応答の抜粋および抜粋が指す行範囲へ影響させてはならない。完全一致検索（grep モード）は本規定の対象外とし、本文だけを照合する。見出し経路を保持しない全文検索索引の経路には本規定を適用しない。
- **FR-MDQ-06**: `mdq` のランキングに用いる文書長正規化の係数は、実装内の単一の定数として定義し、検索呼び出しごとに異なる値を組み立ててはならない。当該係数は利用可能な BM25 実装のいずれにも同じ値で適用しなければならない。既定値は FR-MDQ-04 の回帰計測に基づいて決定し、決定に用いた計測結果を根拠として記録しなければならない。
- **FR-MDQ-07**: `mdq` の応答トークン予算は、呼び出し側へ返す機械可読表現（1 ヒット 1 行の JSON）のトークン数で判定しなければならない。抜粋本文だけを対象とする算定や、文字数の固定比率だけによる近似で判定してはならない。トークン計測器が実行環境に存在しない場合は近似へ降格してよいが、どちらを用いたかを実装が公開する関数で識別できなければならない。計測器は検索経路の import 時に読み込まず、必要になった時点で遅延 import しなければならない。予算判定の実装は FR-MDQ-03 と同一のものとし、返却単位ごとに別の算定を持ってはならない。
- **FR-MDQ-08**: `mdq` の既定検索経路における語彙照合の単位と、照合対象へ含める文脈を次のとおり定める。(1) 連続する CJK 文字の並びは、隣接する 2 文字を 1 語として照合する。隣接する CJK 文字を持たない 1 文字については、その 1 文字を語とする。既定では、同一箇所について 2 文字の語と 1 文字の語を同時に照合対象へ含めない。両方を含める構成を採る場合は (6) の計測で変更前を下回らないことを示さなければならない。ASCII 英数字の連なりは分割してはならない。CJK 文字の範囲は実装が単一の定義として公開し、本規定の判定はその定義に従う。(2) 照合対象には、チャンク本文および見出し経路（FR-MDQ-05）に加えて、当該チャンクのリポジトリ相対パスを含める。(3) 見出し経路は本文より高い重みで照合する。当該重みは実装内の単一の定数として定義し、検索呼び出しごとに異なる値を組み立ててはならない。(4) 本規定はスコアリングのためだけに用い、応答の抜粋および抜粋が指す行範囲へ影響させてはならない。(5) 完全一致検索（grep モード）は本規定の対象外とし、従来どおり本文だけを照合する。全文検索索引を用いる経路は、索引時のトークナイズ単位と索引対象列がいずれも本規定と異なるため、本規定の対象外とする。(6) 本規定に基づく既定値の変更は FR-MDQ-04 の計測手続きに従い、開発用ゴールデンクエリ集とホールドアウト集の双方について、対象パス絞り込みを適用する条件と適用しない条件の双方で、変更前の値を下回らないことを確認しなければならない。
- **FR-MDQ-09**: `mdq` の検索は、応答を返す前に索引と作業ツリーの乖離を検知しなければならない。(1) 検知は索引が保持するファイルのサイズと更新時刻の比較だけで行い、内容ハッシュを用いてはならない（検索 1 回あたりの所要時間を支配させないため）。内容による確定判定は索引側の既存判定を用い、鮮度検知のための判定を新設してはならない。当該比較は内容が同一でも更新時刻だけが変わったファイルを乖離として報告しうるが、これは (1) の安価さと引き換えに許容する。(2) 検知の対象は索引済みファイルの乖離とする。索引に存在しないファイルの発見を検知へ含めるか否かは実装が選んでよいが、含める場合は作業ツリーの列挙コストを検索 1 回あたりの所要時間の実測で評価し、既定の可否を根拠とともに記録しなければならない。(3) 乖離を検知した場合は、乖離したファイル数と復旧手順を含む機械可読な情報を呼び出し側へ公開しなければならない。当該情報はヒットの機械可読表現（1 ヒット 1 行の JSON）とは別の経路で公開し、ヒット行の形式を変更してはならない。(4) 実装は、乖離したファイルだけを再索引してから応答してよい。再索引を行う場合、その適用条件は実装内の単一の定数として定義しなければならない。既定で再索引を行うか否かは、検索 1 回あたりの所要時間の実測に基づいて決定し、決定に用いた計測結果を根拠として記録しなければならない。(5) 本規定は常駐の索引更新機構の有無に依存せず成立しなければならない。当該機構が動作している環境では乖離が検知されないだけであり、本規定を無効化する理由にしてはならない。(6) 検知処理そのものの失敗は検索を中断させてはならない。(7) 呼び出し側は本規定の検知を無効化できなければならない。
- **FR-MDQ-10**: `mdq` の検索応答は、抜粋本文を含めない返却単位を選択できなければならない。(1) 当該単位では、ヒットの識別子・リポジトリ相対パス・見出し経路・行範囲・順位付けスコアを返し、本文の抜粋を含めてはならない。(2) 既定は FR-MDQ-03 の既定から変更してはならない。(3) 応答トークン予算の算定は FR-MDQ-03 および FR-MDQ-07 と同一の実装で行い、本単位のために別の算定を持ってはならない。(4) 本単位を選択したことによって、strategy 選定、ヒット対象チャンクの決定規則、およびヒットの順位を変えてはならない。(5) 本単位で返した識別子は、本文取得のための既存の取得手段でそのまま解決できなければならない。(6) 祖先・近傍・分割片の拡張を併用した場合も本文を含めてはならず、拡張対象についても (1) と同じ所在情報だけを返す。

### 3.9 code-query（cq）ソースコード検索

Coding Agent は、HVE 自体と HVE が生成するアプリケーションの双方について、変更前に既存実装を調査する。`mdq` は `.md` と宣言済み表形式ファイルだけを索引対象とし（§3.8）、ソースコードは索引対象外である。本節はソースコードに対する検索面 `cq` を規定する。

#### 責務分離

- **FR-CQ-01**: `cq` はソースコードだけを索引対象とし、`.md` および表形式ファイル（CSV / TSV）を索引してはならない。設計書・要件・カタログの検索は `mdq`（§3.8）が担い、`cq` は同等機能を再実装してはならない。`cq` の索引 DB は `mdq` の索引 DB と物理的に別ファイルとし、同一の全文検索コーパスへ混在させてはならない。索引は profile 単位に分離し、profile ごとに索引ルートと DB ファイルを 1 対 1 で対応させる。既定 profile は、HVE アプリケーション自体を対象とするものと、HVE が生成するアプリケーションを対象とするものの 2 つとし、設定ファイルで宣言する。設定が存在しない場合は fail-closed とし、既定ルートを推測して索引してはならない。

#### 検索品質の回帰計測

- **FR-CQ-02**: `cq` 検索の回帰計測として、ゴールデンクエリ集に対する top-1 正解率、top-k 正解率、1 クエリあたり応答トークン数、および cold / warm レイテンシを機械算出する。ゴールデンクエリの各項目は、クエリ文字列、対象 profile、想定クエリ意図、および 1 件以上の期待着地点を持つ。期待着地点はリポジトリ相対パスと行番号の対で表し、正解判定はヒットのパスが期待パスと一致し、かつヒットの行範囲（開始行と終了行の閉区間）が期待行番号を含むことをもって行う。パス一致のみを根拠に正解と判定してはならない。行範囲情報を持たないヒットは不正解として扱う。計測は同一クエリ集に対する対照群（行指向 grep 相当の全文検索、およびファイル全文取得）の応答トークン数を同時に算出し、改善幅を根拠付きで比較可能にしなければならない。ゴールデンクエリ集に実在しないパス、または対象ファイルの行数を超える行番号が含まれる場合は fail-closed とし、計測を実行してはならない。正解判定の実装は単一とし、ベンチマーク側で独自の正解判定を実装してはならない。

#### 索引ストアと除外規約

- **FR-CQ-03**: `cq` の索引対象ファイル列挙は、リポジトリの ignore 設定に従う既存の追跡ファイル列挙（`git ls-files --cached --others --exclude-standard`）を単一の入力とし、独自のディレクトリ走査で ignore 設定を迂回してはならない。以下は索引してはならない。(1) 複製であることが明示された vendoring 配下、(2) 生成物・ミニファイ済みファイル・ソースマップ、(3) 資格情報を含み得るファイル（環境変数ファイル、秘密鍵、および設定で宣言された秘密情報パターンに一致するファイル）、(4) 設定で宣言した上限サイズを超えるファイル。除外判定は fail-closed とし、判定に失敗したファイルは索引しない。索引スキーマはバージョン番号を保持し、スキーマ変更時は既存索引を検出して再構築を要求しなければならない。索引 DB はリポジトリへコミットしない。
- **NFR-CQ-01**: `cq` の検索応答は、既定設定においてヒットあたりの本文を一致箇所周辺の抜粋に限定し、1 クエリの応答トークン数の既定上限を設定可能にしなければならない。当該上限の消費量は、**応答として実際に返す 1 ヒット分の機械可読表現の全体**（抜粋と同時に返すメタデータを含む）に対して見積もらなければならず、抜粋の長さだけで見積もってはならない。見積りは検索経路の所要時間を支配しない安価な近似でよく、そのために任意依存のトークナイザを検索経路へ導入してはならない。先頭 1 件は上限を超えても返す。検索経路はランキングを索引エンジン内で完結させ、索引全体をプロセスメモリへ読み込んではならない。検索サブコマンドの起動経路は、任意依存（埋め込み・トークナイザ・多言語パーサ）を import 時に読み込んではならず、必要になった時点で遅延 import しなければならない。

#### 索引層

- **FR-CQ-04**: `cq` は、索引対象ファイルから定義シンボルの表を機械生成する。各行は、リポジトリ相対パス、修飾名、名称、シンボル種別、開始行、終了行、シグネチャ、親シンボル、docstring 等の先頭 1 行、修飾子の集合、およびテスト定義か否かを保持する。抽出は同一入力に対して決定的でなければならない。内容が変わらないファイルは再索引時に skip し、ディスクから消えたファイルの行は prune しなければならない。構文解析に失敗したファイルは索引から除外せず、低フィデリティのパーサへ降格して索引し、当該フィデリティを索引に記録しなければならない。
- **FR-CQ-05**: `cq` は、部分文字列一致のための字句索引と、自然文クエリのための構造チャンク索引を保持する。構造チャンクは構文木のノードを単位とし、上限サイズを超えるノードは子ノードへ再帰的に分割し、上限に満たない兄弟ノードは上限内で連結する。行数だけを根拠にチャンク境界を決めてはならない。チャンクは識別子を語境界（大文字境界・アンダースコア）で分割した語列を検索対象の別フィールドとして保持し、`getUserProfile` のような連結識別子が語単位クエリで到達可能でなければならない。部分文字列検索は索引が要求する最小長を満たさないクエリを fail-closed で拒否し、索引を迂回した全走査へ暗黙に降格してはならない。

#### 検索インタフェース

- **FR-CQ-06**: `cq` の検索は、クエリ形式から検索層を機械的に選択する。選択順は、(1) トレース識別子形式、(2) シンボル名の完全一致、(3) 引用符付きまたは記号を含む部分文字列、(4) 明示指定された正規表現、(5) それ以外の自然文、とする。ヒット 0 件の場合は自然文 → 部分文字列 → シンボルの順に fallback し、選択結果と fallback の有無を応答へ含めなければならない。自然文の検索層が 0 件を返した場合は、**語の連言による照合を選言へ 1 回だけ緩和して再試行しなければならない**。緩和は語が 2 つ以上あるときに限り行い、再試行は 1 回までとする。緩和して得たヒットは、緩和によるものだと呼び出し側が機械的に判別できる標識を応答へ含めなければならない。ただし**クエリが CJK 文字を含む場合は緩和を行ってはならない**。これは「日本語の自然文で英語のみのコードを探すクエリに対しては、誤った上位ヒットを返すより 0 件を返す」という既存の方針を維持するためである。当該方針を変更する場合は、ゴールデンクエリ集に対する実測を根拠として記録しなければならない。すべての検索層が 0 件を返した場合に限り、**リポジトリ相対パスの部分一致で引く検索層を最後に試さなければならない**。当該層はファイルごとに 1 件へ畳んで返し、部分文字列検索と同じ最小長を満たさないクエリでは当該層を試行せず、エラーとしてもならない。本段の緩和とパス層は、検索層を自動選択する場合の規定であり、呼び出し側が検索層を明示指定した場合は既存の fallback 規定と同じく適用しない。正規表現検索は、字句索引で候補集合を絞り込んでから確定照合を行い、候補件数の上限を設定可能にしなければならない。上限を超えた場合は打ち切り、打ち切った旨を応答へ含める。応答は 1 ヒット 1 行の構造化形式とし、パス、行範囲、スコア、抜粋、および当該ファイルのパーサフィデリティを含める。抜粋の単位は呼び出し側が選択できなければならない。選択肢は、ヒット行を中心とする行範囲と、ヒットを含む構造チャンクの本文全体の 2 つとし、既定は前者とする。返却単位の違いによって、検索層の選択、fallback の有無、およびヒットの順位を変えてはならない。同一予算のもとでは抜粋が長い分だけ応答件数が減るが、これは予算規則の帰結であり本規定に反しない。
- **FR-CQ-07**: `cq` は、シンボル参照、モジュール依存、およびソースコードから設計文書への出典参照を索引する。出典参照の抽出パターンは単一箇所に定義し、既存の機能 ID 抽出パターン（`hve-dev/generate_tdd_inventory.py`）と重複定義してはならない。トレース識別子からコード位置を引く経路と、コード位置から設計文書のパスとアンカーを引く経路の双方を提供しなければならない。`cq` は設計文書の本文を返さず、参照先の特定に留める。本文取得は `mdq` が担う。

#### 索引の鮮度

- **FR-CQ-08**: `cq` はソースコードの変更を索引へ反映する手段を提供する。ファイルシステム監視による逐次更新を提供し、監視が動作していない実行環境でも、検索実行時に索引済みファイルの更新時刻とサイズだけを突合して stale を検出しなければならない。突合のためにファイル内容のハッシュを再計算してはならない。差分件数が設定上限以下の場合は当該ファイルだけを再索引してから応答する。上限を超える場合は結果を返したうえで stale である旨と差分件数を応答へ含める。索引が存在しない場合は、0 件の検索結果を返してはならず、索引生成を要求するエラーとしなければならない。

#### 俯瞰出力

- **FR-CQ-09**: `cq` は、指定範囲のコードベースについて、ファイルと主要シンボルの定義行だけからなる俯瞰出力を生成する。出力はトークン予算を引数に取り、予算内に収めなければならない。**予算の判定は、掲載する定義行だけでなく、既定の出力形式が付加する装飾（ファイル見出し・折り畳み記号・区切りの空行・除外件数の通知）を含めた、実際に出力する文字列の全体**に対して行わなければならない。掲載順序は参照グラフ上の被参照数に基づいて決定し、予算超過時は下位から除外したうえで除外件数を出力へ含める。俯瞰出力に本文を含めてはならない。

#### 既存実装との統合

- **FR-CQ-10**: HVE 対象の実装シンボル索引（FR-MAINT-05）の抽出処理は単一実装とする。`cq` のシンボル抽出（FR-CQ-04）と `hve-dev/generate_tdd_inventory.py` のシンボル抽出が併存してはならず、生成元は `cq` の抽出結果を利用しなければならない。統合の前後で `hve-dev/hve-surface-inventory.csv` の列構成と内容が変化してはならない。変化する場合は統合を完了と宣言してはならない。
- **FR-CQ-11**: `cq` の言語対応は、拡張子・パーサ・シンボル種別対応の宣言を言語ごとに 1 箇所へ局所化し、言語追加時に索引・検索の中核実装を変更してはならない。高フィデリティのパーサが実行環境に存在しない場合は、正規表現ベースの低フィデリティパーサへ自動降格し、降格したことを索引と検索応答の双方へ記録しなければならない。降格を理由に索引処理全体を失敗させてはならない。多言語パーサは任意依存とし、未導入の実行環境でも標準ライブラリだけで成立する言語の索引と検索が動作しなければならない。
- **FR-CQ-12**: `cq` は Skill として Coding Agent から参照可能でなければならない。Skill 定義はルーティング表へ登録し、`mdq` の Skill 定義と相互に適用範囲を参照して、ソースコード検索と Markdown 検索の選択が一意に決まるようにしなければならない。`cq` の導入前後で `mdq` の検索品質（FR-MDQ-01 のゴールデンクエリ正解率）が低下してはならない。
- **FR-CQ-13**: `cq.search.get_chunk(db_path, chunk_id)` は、既存索引の `chunks.chunk_id`（検索 hit の `chunk_id` と同一 ID 空間）を再利用するため、`chunk_id` / `path` / `lines`（`[start_line, end_line]`）/ `text` / `parser` の 5 フィールドだけを持つ Python 辞書を返す。未知の chunk ID では `None` を返す。`cq get` は同 API の辞書を `cq/cli.py` で既存の `# path:start-end` と本文へ整形し、成功時標準出力、および未知 ID の終了コードとエラーを変更してはならない。custom tool 側の JSON 化は呼び出し側が担う。
- **FR-CQ-14**: `cq` は CLI サブコマンドの実行ごとに利用ログを 1 行 1 レコードの JSONL として `<repo-root>/.cq/usage.jsonl` へ追記しなければならない。`<repo-root>` は `--repo-root` で解決した値とし、`mdq` の利用ログ（`.mdq/usage.jsonl`）と同一ファイルへ混在させてはならない。各レコードは発生時刻（ISO8601 UTC）・サブコマンド名・引数・所要時間（ミリ秒）・サブコマンド固有の結果集計・終了コードを持ち、Orchestrator が伝播した実行文脈（`HVE_RUN_ID` / `HVE_WORKFLOW_ID` / `HVE_STEP_ID` / `HVE_AGENT_ID`）のうち値が設定されている項目だけを `context` へ含める。値が取得不能な項目はキーごと省略し、`null` で埋めてはならない。長時間常駐する `watch` は記録対象外とする。収集は best-effort とし、書き込みに失敗しても CLI の終了コードと標準出力を変えてはならない。
- **FR-CQ-15**: `cq` の索引統計は、集計対象テーブルごとの合計に加えて、索引済みファイルの言語別内訳を報告しなければならない。言語別内訳は、言語ごとに、ファイル数、シンボル数、チャンク数、およびパーサフィデリティ（FR-CQ-11 の降格を含む）別のファイル数を保持する。パーサ別の集計だけを報告してはならない。同一のパーサ名が複数の言語で共有されるため、パーサ別の集計からは特定言語のフィデリティ低下を判別できないからである。言語の値は FR-CQ-04 の索引が保持する言語をそのまま用い、統計側で言語を再判定・再分類してはならない。言語別内訳の集計は索引スキーマを単一の情報源とし、CLI と GUI で二重に実装してはならない（FR-MAINT-07）。索引が存在しない場合、言語別内訳を 0 件として報告してはならない。
- **FR-CQ-16**: `cq` は、意味的類似度による検索層（FR-CQ-17）を含めて検索するときに限り、FR-CQ-06 の全検索層を実行し、結果を 1 本の順位へ統合しなければならない。語彙層だけを統合する手段を提供してはならない。語彙層だけの統合は逐次の層選択と同じ順位を返し、応答量だけが増えるからである。統合は各層内の順位のみを根拠とし、層をまたいでスコアを直接比較してはならない。層ごとにスコアの尺度と符号が異なるためである。ただし問いの文字列そのものを含む場所を返す層（トレース識別子・シンボル完全一致・部分文字列）は統合の対象外とし、自身の順位を保ったまま統合結果の先頭に置かなければならない。これらの層は 1 つしか当該箇所を返さず、順位の逆数和では複数層に現れる付随的な一致に構造的に負けるためである。同一入力に対する統合結果は決定的でなければならない。要求されたときは、実行した層とその件数を実行内訳として応答へ含められなければならない。実行内訳は既定では出力しない。
- **FR-CQ-17**: `cq` は、要求されたときに意味的類似度に基づく検索層を FR-CQ-16 の統合へ加えられなければならない。この層は単独の検索モードとして選択できてはならない。埋め込みの生成と格納は索引時の明示的な要求に限り行い、既定の索引処理を変えてはならない。ベクトルは FR-CQ-04 の索引スキーマを変更しない場所へ格納しなければならない。既存の索引を読めなくする変更は、既定で無効な機能のために全利用者へ再構築を強制するためである。埋め込みの生成に用いたモデルを格納し、異なるモデルで作られたベクトルを用いてはならない。ベクトル生成後に変更されたファイルのベクトルを用いてはならない。任意依存の不在・ベクトルの不在・モデル不一致・ファイル変更のいずれの場合も、意味検索層の候補を 0 件として扱い、検索そのものを失敗させてはならない。また `cq` は、本文を返さずにヒットを囲むシンボルの修飾名・種別・シグネチャを返す返却単位を提供しなければならない。この単位でも、パーサフィデリティ（FR-CQ-11）と、本文を後から取得するためのチャンク識別子（FR-CQ-13）を落としてはならない。囲むシンボルが存在しないヒットを除外してはならず、位置情報だけを返す。

### 3.9.1 Repository Query Agentic Retrieval 計測 PoC

本項は、通常の deterministic 検索を置換せず、複数ソースを横断する複合質問に対する品質・検索回数・Token・所要時間を比較する HVE 内の計測 PoC だけを規定する。

- **FR-RQ-01**: Repository Query PoC の唯一の実行入口は HVE 開発用 evaluator `hve-dev/evaluate_repository_query.py` とし、同 evaluator が `hve.repository_query` の private Python API を明示呼出しした場合だけ起動する。通常の `mdq search` / `cq search`、公開 CLI、canonical Skill、standalone kit、自動 routing を変更または暗黙起動してはならない。リポジトリ断片を Copilot model へ送信する network benchmark は利用者が evaluator を明示実行した場合だけ許可する。PoC の結果を理由に public feature を自動公開せず、Go/No-Go レポートの確認後に別承認を要求する。
- **FR-RQ-02**: Agentic Arm が利用できる tool は `search_markdown` / `search_code` / `open_evidence` / `find_code_references` の read-only custom tool 4 個だけとし、§3.8 の既存 mdq search / chunk、§3.9 の既存 cq search、FR-CQ-13 の chunk API、FR-CQ-07 の references を委譲先として再利用する。前 2 tool は 1 call 最大 3 個の非空 query と repository-relative filter を受け、1 query 最大 3 hits・800 tokens を返す。`open_evidence` は 1 call 最大 3 個の当該 query の ledger ID、`find_code_references` は 1 個の symbol と session 固定 CQ DB を受け最大 3 references を返す。host-side Evidence Ledger は query ごとに新規作成し、`(source, chunk_id)` を同一性キーとして初回登録順に `E1` から参照 ID を付け、重複登録では既存 ID を返す。`open_evidence` は同じ query の ledger に登録済み参照だけを取得できる。任意ファイル read、write、shell、web、MCP、memory、git 操作を許可してはならない。
- **FR-RQ-03**: Model の最終出力は `status` / `grounding` / `evidence_ids` / `unresolved` だけを持つ Grounding JSON とする。`unresolved` は根拠不足または失敗により未解決の短い事項を並べる `list[str]` であり、`answered` では空、`partial` / `insufficient_evidence` では 1 件以上の非空文字列とする。`evidence_ids` は model が最初に引用した順序を保つ重複なしの `list[str]` とし、同一 `(source, chunk_id)` の再参照には query ledger の既存 ID を使用する。host は ledger と runtime 計測値から `schema_version: 1`、`evidence`（`ref_id` / `source` / `path` / `lines` / `chunk_id` / `snippet`）、`usage`、`limits` を付加する。`status` は `answered` / `partial` / `insufficient_evidence` の allowlist とし、`grounding` 内の `[E#]` と `evidence_ids` は一致し、`answered` / `partial` は有効な evidence を 1 件以上必要とする。Model が path / lines を生成した出力、invalid JSON、未知の evidence ID は、修復 LLM へ再送せず fail-closed とする。
- **FR-RQ-04**: 同一の composite golden query set を次の 3 条件で query ごとに比較し、query 間を 1 model call にまとめてはならない。Arm A は local `mdq` / `cq` だけで deterministic evidence を返し LLM を呼ばない。Arm C は当該 query の Arm A と同一の固定 evidence を tool なしの exactly 1 model call で Grounding JSON へ圧縮する。Arm D は当該 query ごとに Model が FR-RQ-02 の 4 tool だけを bounded session で利用する。query / category / overall ごとに required-evidence recall、citation validity、unanswerable abstention、outer interaction / internal search / LLM / tool の各 call 数、input / output / cache Token、所要時間、error / cap rate を出力し、失敗・abort した試行も分母から除外しない。結果の `provenance` object は `model` / `reasoning_effort` / `sdk_version` / `cli_version` / `commit_sha` / `golden_sha256` / `index_paths` を保持し、Arm A の model 固有値は `null` とする。LLM judge と自動 Go/No-Go 判定を実装せず、数値閾値は baseline 後の別承認とする。
- **NFR-RQ-01**: Arm C / D の network benchmark は fixed model、fixed reasoning effort、`max_ai_credits`、timeout を必須入力とし、Auto または無制限で開始してはならない。初回 PoC はインストール済み GitHub Copilot SDK 1.0.6 の `SessionLimitsConfig.max_ai_credits: float` を前提とし、同 field を利用できない SDK では session を開始せず fail-closed とする。Copilot CLI 1.0.77 が session 作成時に受理する最小値は 30 AI credits であるため、30 未満は client 作成前に拒否する。1 query の内部上限は custom tool calls 6、LLM calls 10、1 search call の subqueries 3、1 subquery の hits 3、1 open call の refs 3、1 subquery の返却 800 tokens とする。LLM calls 10 は、tool calls 6 の canary で SDK `assistant.usage` が内部model処理を含め9回発火した実測に1回の余裕を持たせた値である。次の処理で上限超過となる直前に session を abort し、host result の `error` object に `type=cap_exceeded`、`cap_name`、`limit`、`actual` を記録する。これらは受入閾値ではなく暴走防止の初期 safety cap であり、baseline 後の変更には別承認を要する。raw prompt と reasoning は永続化せず、evidence snippet は利用者が明示した benchmark result artifact にだけ保存でき、SDK log、telemetry、stdout / stderr へ出力してはならない。credential / authentication data はいかなる成果物にも保存してはならず、SDK または pydantic の新規依存を追加してはならない。

### 3.10 Skill 配布キットの可搬性

`mdq`（§3.8）と `cq`（§3.9）は、HVE リポジトリ以外でも利用できるよう配布キット（[tools/skills/markdown_query/](tools/skills/markdown_query/) / [tools/skills/code_query/](tools/skills/code_query/)）を持つ。配布キットは、当該フォルダだけを複製した利用者が上流 HVE リポジトリへ一切アクセスできない前提で成立しなければならない。他リポジトリへの同期は [tools/for-other-repo/](tools/for-other-repo/) の宣言と同期スクリプトが担い、Tool Search（§3.11 の実行時 Observability とは別に、SDK セッションのツール定義遅延ロードを担う `hve/toolsearch/`）も同じ経路で配布する。

- **FR-KIT-01**: 配布キットは検索エンジン実体を同梱し、版管理下に置かなければならない。同梱物は上流パッケージを正本とする生成物とし、正本と同梱物のファイル集合および内容の一致を機械検証しなければならない。同梱物を直接編集してはならない。同梱対象からはテストコードおよびリポジトリ固有の評価データを除外し、除外判定はディレクトリ階層の深さに依存してはならない。
- **FR-KIT-02**: Skill 定義の正本は `.github/skills/<skill-name>/` の 1 箇所とする。配布キットが持つ Skill 定義は当該正本からの生成物とし、内容が一致しなければならない。配布用に別文面の Skill 定義を保守してはならない。リポジトリ固有の記述（profile 名や実リポジトリのパス例等）は正本の参照資料へ隔離し、配布物本体が特定リポジトリの構成を前提としてはならない。
- **FR-KIT-03**: 配布キットのセットアップおよび同期の判断ロジックは単一実装とする。OS 別の起動スクリプトは当該実装への委譲に限り、依存解決・パス決定・設定生成・Skill 配置の判断を OS 別に重複実装してはならない（FR-MAINT-07）。
- **FR-KIT-04**: 配布キットのフォルダだけを他リポジトリへ複製した状態で、セットアップ、設定ファイルの生成、Skill 定義の配置、索引の生成、検索の実行、および GUI の起動導線が成立しなければならない。上流リポジトリ固有の名前（profile 名等）を利用者が手動で与えなければ成立しない状態としてはならず、一意に定まる場合は導入先の宣言から解決しなければならない。GUI の任意依存が未導入の場合は導入手順を示して fail-closed とする。当該成立性は、上流リポジトリを import 経路から除外した実行で機械検証しなければならない。検証は版管理下の実配布物を対象とし、正本から検証時に複製した一時ツリーで代替してはならない（同期漏れを検出できなくなるため）。
- **FR-KIT-05**: 配布対象のコードは、上流リポジトリ固有のパッケージ（`hve`）へ依存してはならない。実行時に当該パッケージの有無を判定して振る舞いを切り替える経路を持ってはならない。HVE 組み込み時の差異は、HVE 側から共有実装へ注入する形で表現しなければならない。
- **FR-KIT-06**: 配布パッケージの構成は宣言を単一の出所とし、同期スクリプトが収集対象を再宣言してはならない。エンジン実体・Skill 定義・共通セットアップ実装を宣言側へ複製してはならない。同期はコピー先へ版マニフェストを生成し、配布版・エンジン版・上流 commit・同期時刻・全配布ファイルのハッシュを記録しなければならない。上流と同版または降格となる同期は既定で拒否し、明示指定でのみ上書きできなければならない。前回配布に含まれ今回含まれないファイルは削除し、配布物以外のファイルを削除してはならない。利用者が編集する前提として宣言されたファイルは既存時に上書きせず、改変検出の対象外であることをマニフェストへ明示しなければならない。コピー先だけで版と改変・欠落を確認できなければならない。上流で extras として宣言される任意依存のうち配布先で必要なものは、同期宣言へ列挙してセットアップ時に導入できなければならない。本要件は手動同期を前提とし、自動配布・外部レジストリへの公開を対象としない。

### 3.11 実行時 Observability と Dashboard

本節は、HVE の各実行面（GUI Workbench / GUI Autopilot / 対話 CLI / 直接 `orchestrate` / CUI Workbench / CLI Autopilot、および `--autopilot-child` の互換ウィンドウ）が、実行中の状態と統計を同一の根拠から表示・記録するための契約を規定する。本節は entrypoint の起動仕様（FR-CLI-10）を改訂しない。閾値アラート、外部 telemetry 送信、run を跨いだ履歴検索は本節の対象外とする。

- **FR-RTO-01**: 実行時観測イベントの構築と解析は単一実装とする（FR-MAINT-07）。既存 `[hve:stats]` 行形式および既存の `kind` / `step` キーを維持したうえで、`schema_version` / `ts` / `seq` / `pid` / `run_id` / `workflow_id` / `instance_id` を付加する。`instance_id` は実行プロセス（ジョブ）単位の識別子とし、既定は `workflow_id`、当該プロセスが単一の APP へ専従する経路（Autopilot の APP 別子プロセス、および起動時の APP 指定が 1 件に確定している場合）では `workflow_id#app_id` とする。同一プロセス内で APP キーごとに fan-out した Step の内訳は `step` フィールドで分離し（FR-RTO-07）、`instance_id` を Step 単位で切り替えてはならない。envelope の `pid` と観測ファイル `observability/events-<pid>.jsonl`（FR-RTO-03）がプロセス単位で対応するため、`instance_id` だけを Step 単位にすると同一プロセスの識別子が複数値となり、表示の集計単位（FR-RTO-05）と保存単位が一致しなくなるためである。既存キーの意味を変更してはならない。未知の `kind` は解析可能とし、無言で捨てずに件数を計上する。
- **FR-RTO-02**: 「収集」「保存」「子プロセスへの配信」「人間向け表示」を分離する。`[hve:stats]` 行の stdout 出力は、GUI 子プロセス（`HVE_GUI_SESSION_ID` 設定時）および Dashboard を持つ親プロセスが環境変数 `HVE_STATS_STREAM=1` を付与して起動した子プロセスに限る。当該判定に新規 CLI オプションを用いてはならない（NFR-RTO-02）。通常 CLI、CUI Workbench、非 TTY 実行では stdout へ出力せず、CUI Workbench の本文ペインにも表示しない。`quiet` および `final_only` でも収集・保存・子プロセス配信は継続し、人間向けの追加表示だけを抑止する（NFR-OBS-03 と矛盾させない）。
- **FR-RTO-03**: 観測イベントは実行プロセスが `resolve_work_root()` 配下の `observability/events-<pid>.jsonl` へ追記する。`HVE_WORK_ROOT` 未設定時および dry-run では書き込まない。同一プロセス内の追記は直列化する。形式は UTF-8 / LF / BOM なしの 1 行 1 JSON とする。ファイルサイズが 32 MiB に達した場合は追記を停止し、その事実を 1 回だけ警告する（ローテーションは行わない）。プロセス内の順序は `seq` により厳密とし、プロセス間の時刻順序は近似であることを明示する。
- **FR-RTO-04**: 永続化する項目は allowlist 方式とし、状態、時刻、数値、モデル ID、Step / Workflow / APP 識別子、例外型名、リポジトリルート相対パス、FR-STATE-04/05 の sanitized replay descriptor・hash・lease metadata に限る。prompt 本文、応答本文、reasoning 本文、tool の引数・出力、任意環境変数、認証情報、認証 URL、生 SDK ペイロード、生 repository root を保存してはならない（NFR-SEC-01）。相対化の基準は実行プロセスの作業ディレクトリ（リポジトリルート）とし、当該ルート配下へ相対化できないパスは保存しない。
- **FR-RTO-05**: 各実行面は同一のイベント列から同一の集計値を表示する。表示は instance 単位で分離し、run 単位で合算する。未取得値を推定で補わず、取得できない項目は `-` として表示する。
- **FR-RTO-06**: 観測記録のライフサイクルは実行プロセスが所有し、`run_workflow` の終了時に確実にクローズする。GUI 親プロセスは観測ファイルを書き込まない。GUI セッション作業ディレクトリの後処理（`keep` / `archive` / `purge`）が観測ファイルに起因して失敗してはならない。
- **FR-RTO-07**: 実行履歴の Step 別表示は Step 単位で分離する。Step の Context、AI Credit、モデル、ツール、Skill は当該 Step へ帰属したイベント（`step` フィールドが当該 Step であるもの）だけから算出し、実行面のグローバル現在値、Workflow 累積値、他 Step の値で代替してはならない。Step へ帰属したイベントが 1 件も無い項目は `-` として表示し、隣接 Step の累積値の差分などの推定値で補ってはならない（FR-RTO-05）。実行面が Step 帰属を解決できない経路の消費も、Workflow 単位の累積値へは計上しなければならない。当該累積値が Step 別内訳の合計と一致しない場合は、その理由を表示上明示しなければならない。SDK Fleet mode へ委譲した Wave では、worker と Step の対応が当該 Wave の Step 集合に対して一意に定まる場合にだけ当該 Step へ帰属させ、一意に定まらない場合は Wave 内のいずれの Step へも割り当ててはならない。対応の解決に用いた入力（tool の引数等）を観測イベントへ保存してはならない（FR-RTO-04）。また、実行識別子（`run_id`）が未確定の時点で開始した実行を、識別子の確定後に別実行として二重に計上してはならない。
- **FR-RTO-08**: 実行プロセスは、当該 run が対象とする GitHub の Root Issue 番号・Pull Request 番号・作業 branch を確定した時点で、既存の観測イベント経路を用いて 1 件の lifecycle イベントとして通知しなければならない。GUI が FR-GUI-36 の自動 Post 先および FR-GUI-37 の cleanup 対象を、GitHub API の一覧取得や作業ディレクトリの走査に頼らず決定できるようにするためである。
  - イベントの `kind` は `github_target` の 1 種類とし、同じ目的で複数の `kind` を追加してはならない。payload に含めてよいのは `repo`（`owner/repo` 形式）、`issue_number`、`pr_number`、`branch`、`base_branch`、`created_by_hve`、`delete_local_merged_branch` に限る。値が未確定の項目は当該キーを省略し、推定値で補ってはならない。
  - token、GitHub API の応答本文、Issue / PR の本文、コメント本文、prompt / 応答本文、`git remote` の URL を含めてはならない（FR-RTO-04 / NFR-SEC-01）。永続化の allowlist へ追加してよいのは前項のキーだけとする。
  - `created_by_hve` は当該 run が新規作成した作業 branch のときだけ `True` とし、FR-CLI-83 の current branch mode では `False` としなければならない。`branch` が未確定の場合は `created_by_hve` を送出してはならない。
  - 既存の `kind` / キーの意味を変更してはならず、本イベントを解釈しない既存の消費者が未知 `kind` として計上できる形式を維持しなければならない（FR-RTO-01 / NFR-RTO-02）。本イベントの送出失敗は Workflow 実行を失敗させてはならない（NFR-RTO-03）。

### 3.12 QA 質問票の説明深度

本節は、QA 質問票の各質問が利用者の意思決定に足る説明を伴うことを規定する。対象は [hve/prompts.py](hve/prompts.py) の質問票生成プロンプト（`PRE_EXECUTION_QA_PROMPT_V2` / `QA_PROMPT_V2`）と、その出力を保持・提示するパイプラインとする。質問の件数・重要度分類・既定値候補の採用ロジックは本節の対象外とする。

- **FR-QA-01**: 質問票生成プロンプトは、各質問に「背景と根拠」と「判断の観点」を必須項目として出力させなければならない。「背景と根拠」は、判断材料として確認した対象（出典）、そこから確定した事項と確定していない事項、および当該未確定が質問に値する理由を含めなければならない。確認していない場合は「未確認」と記載させ、出典を推測で記載させてはならない。「判断の観点」は、回答によって結論が変わる評価軸を 2 つ以上挙げ、主要な選択肢が各軸で有利・不利のいずれとなるかを示さなければならない。「既定値候補の理由」は、当該選択を支持する根拠となる事実、優先した評価軸、および他の選択肢を既定値としなかった理由を含めなければならない。各項目の値は 1 行で記述させ、結論のみの記述を許してはならない。本要件は事前 QA（メインタスク実行前）と事後 QA（成果物に対する QA）の双方へ同一の項目定義で適用する。
- **FR-QA-02**: QA 質問票のパイプラインは FR-QA-01 の 2 項目を欠落させてはならない。[hve/qa_merger.py](hve/qa_merger.py) は当該 2 項目を構造化質問票（`[Qxx]` 形式）およびマージ済みテーブル形式の双方で解析し、`render_merged` の出力へ列として保持しなければならない。当該 2 項目を持たない既存の質問票ファイルは空値として扱い、解析を失敗させてはならない。CLI は [hve/console.py](hve/console.py) の質問票表示で当該 2 項目を提示しなければならない。ただし既存の質問票テーブルへ列として追加してはならず、テーブルとは別の形式で提示する（列追加は既存列の可読幅を損なうため）。GUI の QA 回答ダイアログ（[hve/gui/qa_answer_dialog.py](hve/gui/qa_answer_dialog.py)）は当該 2 項目を回答入力前に参照できるよう表示しなければならない。質問票フォーマットを規定する Skill（[.github/skills/task-questionnaire/SKILL.md](.github/skills/task-questionnaire/SKILL.md) および `references/` 配下のテンプレート）は、プロンプトと同一の項目定義を保持しなければならない。経路によって項目定義が異なってはならない。
- **FR-QA-03**: `auto_qa` が有効な Knowledge Management (`akm`) 以外の Workflow は、質問が 1 件以上ある事前 QA について、ユーザー回答または明示された既定値を全質問へ適用した回答済み Markdown を `qa/` 配下へ保存し、最終パスを再読込して内容・質問数・各質問の非空回答を検証した後でなければメインタスクを開始してはならない。回答済み Markdown の表セルは、Work IQ 応答を含め、CR / LF / pipe を含む入力でも 1 質問 1 物理行を維持し、render → 保存 → 再解析の往復で質問数と全回答を失ってはならない。Work IQ 回答案へ統合できるのは、SDK の `tool.execution_start` イベントから Work IQ 用として許可された MCP server/tool の組を確認でき、かつ応答 status が `FOUND` または `PARTIAL` の結果だけとする。tool 名だけの一致を実行確認としてはならない。許可する tool 名は `@microsoft/workiq` が公開する参照系ツールに限り、書き込み系ツール（entity の作成・更新・削除、`do_action`）および EULA 承認・デバッグリンク取得の実行を統合根拠としてはならない。MCP サーバーへ公開する tool の allowlist（最小権限）と、実行確認に用いる tool 名の集合は別の集合として保持しなければならない。前者を後者に合わせて広げると `_hve_workiq` の公開権限が不必要に緩み、後者を前者に合わせて狭めると、自動探索で併存する Work IQ サーバー経由の実行を検出できなくなるためである。事前 QA サブセッションは FR-CLI-76（v2.41）で自動探索を停止したため併存しないが、`workiq-doctor` の tool probe（`probe_workiq_copilot_tool_invocation`）は利用者環境の実態を観測する診断であり自動探索を残したまま実行確認を行うため、実行確認の集合は引き続き別集合として保持しなければならない。ここでいう Work IQ サーバーには、公式 `workiq` サーバーに加え、同一の Work IQ サービスを別サーバー名で登録するプラグイン（`workiq-preview` 等）を含めなければならない。Work IQ とみなす MCP サーバー名は単一の正本として保持し、実行確認とメインセッションからの分離とで別々に定義してはならない（FR-MAINT-07）。`FOUND` / `PARTIAL` は一次情報が少なくとも一部見つかった結果であるため統合対象とする。`NOT_FOUND` は既定回答を変更する一次情報が見つからず、`UNAVAILABLE` / status 不明 / tool 実行未確認は検索または出典を検証できないため、いずれも検証済み回答へ統合せず、調査用 draft にだけ未確認として保持する。質問が 0 件の場合は同期対象なしとしてメインタスクを継続する。FR-QA-05 の `qa_akm_background_merge` が有効な場合に限り、検証済み QA ファイル 1 件ごとに `sources=qa`、`target_files=<当該ファイル>`（登録単位の値。実行時の値は後述のバッチ規則が定める）、`force_refresh=false`、`auto_qa=false` の AKM 差分更新を別のバックグラウンド実行として登録し、登録キューが当該要求を受理した時点で **QA を生成した source Workflow の親 DAG** は AKM 完了を待たず次 Step へ進めなければならない。登録は検証済み QA ファイル 1 件ごとに行うが、実行開始時点でキューに滞留している複数の登録は 1 回の AKM 子実行へまとめてよい。まとめた場合は `target_files` へ当該バッチの全ファイルを与え、実行結果は登録件数分（ファイル単位）で報告しなければならない。CLI / GUI のバックグラウンド AKM と明示実行 AKM は同一リポジトリ内で直列化し、同時に 2 つ以上の AKM 子プロセスを起動してはならない。AKM の出力空間は `target_files` の指定によらず `knowledge/D01`〜`D21` の全体と `knowledge/business-requirement-document-status.md` を含むため、子プロセスを多重起動すると同一ファイルへの同時書込みと差分喪失が生じる。AKM 子実行の fan-out 並列度は FR-DAG-03 の解決順序に従い AKM の宣言値となる。子プロセスの argv で並列度を固定してはならない（FR-MAINT-07: 同一ルールを二重に実装しない）。当該 fan-out 子は各自の `knowledge/D{NN}-*.md` だけを書く契約（[.github/prompts/fanout/akm/_common.prompt.md](.github/prompts/fanout/akm/_common.prompt.md)）であるため、宣言値までの並列化は上記の直列化要件と両立する。親 Workflow の Git 後処理・branch 切替・GUI cleanup より前に未完了の書込みを安全に終了または取消できなければならない。branch / PR を作る親実行では、AKM が出典として使用した検証済み QA ファイルだけを knowledge 変更とともに commit 対象へ含める。ADI も本要件の対象とし、Step 1.1 / 1.2 が生成する原本質問票 main 成果物は事前 QA の回答済み補助ファイルとは別成果物として扱う。`workflow_id=akm` の実行は QA 起点 AKM 登録を行ってはならず、AKM Root Issue から別の QA 起点 AKM を再帰生成してはならない。ファイル単位の起動とリポジトリ単位の直列化は、複数 Step が回答を保存した場合にも各回答を早期反映しつつ、共有する `knowledge/` への同時書込みと差分喪失を防ぐために必要な最小境界である。SDK Fleet mode へ委譲した wave（実行可能 Step が 2 件以上ある wave。[hve/orchestrator.py](hve/orchestrator.py) `_fleet_wave_runner`）は本要件の事前 QA と QA 起点 AKM の対象外とする。Fleet 経路は `StepRunner.run_step` を経由せず、事前 QA（Phase 0）と敵対的レビュー（Phase 3）は `run_step` の内部にあるためである。ただし実行面は、`auto_qa` または `auto_contents_review` が有効なまま Fleet wave を開始する場合、当該 wave では両フェーズが実行されないことを、Fleet の起動成功が確認できた時点で 1 回だけ警告として通知しなければならない。利用者が明示的に有効化した設定が無言で失われてはならない。警告は wave ごとに 1 回とし、Step ごとに繰り返してはならない（並列 Step 数だけ同一警告が出ると信号が失われるため）。Fleet の起動に失敗して通常経路へフォールバックした場合は、当該 wave で両フェーズが実行されるため警告してはならない。警告文の生成は単一のヘルパーに限定する（FR-MAINT-07）。
- **FR-QA-04**: FR-QA-03 の QA 起点 AKM に対して、利用者は AKM 子実行が使うモデル・reasoning effort・context tier を、メインタスクの実行品質設定とは独立に選択できなければならない。設定キーは `akm_model` / `akm_reasoning_effort` / `akm_context_tier` とし、CLI は `--akm-model` / `--akm-reasoning-effort` / `--akm-context-tier` で受け取る。いずれも未指定を既定とし、未指定のキーは対応するメイン設定（`model` / `reasoning_effort` / `context_tier`）を継承しなければならない。`reasoning_effort` / `context_tier` には既存の環境変数経路が存在しないため（[hve/config.py](hve/config.py) `SDKConfig.from_env`）、本設定にも環境変数経路を新設してはならない。継承の解決は QA 起点 AKM 子プロセスの引数生成（[hve/qa_akm_dispatch.py](hve/qa_akm_dispatch.py) `QaAkmCoordinator._build_argv`）だけで行い、メインタスク・敵対的レビュー・QA 質問票生成のセッション生成へ本設定を適用してはならない。`--workflow akm` を明示指定した実行は本設定の適用対象外とし、従来どおり `--model` / `--reasoning-effort` / `--context-tier` に従わなければならない。CLI 対話 wizard は `auto_qa` を有効化した非 AKM Workflow のときにだけ本 3 項目を尋ね、既定は継承としなければならない。モデル値は既存のモデル正規化（[hve/config.py](hve/config.py) `_normalize_model_with_warning`）と同一の規則で検証しなければならない。本設定は AKM が扱う `knowledge/` の更新粒度と、メインタスクの実行品質・コストを独立に決められるようにするために必要であり、既定の継承によって既存実行の挙動を変えてはならない。
- **FR-QA-05**: FR-QA-03 の QA 起点 AKM をバックグラウンドで起動するかどうかは、利用者が明示的に選択できる設定 `qa_akm_background_merge` で制御しなければならない。既定は無効とし、無効のときは QA 起点 AKM を登録・dispatch してはならない。CLI は `--qa-akm-background-merge` で受け取り、CLI 対話 wizard は `auto_qa` を有効化した非 AKM Workflow のときにだけ本設定を尋ね、既定は無効としなければならない。GUI は設定画面と Step 1 右ペインの双方で選択でき（FR-GUI-20）、Cloud は Issue Form の入力で選択できなければならない（FR-CLOUD-26）。本設定が無効のとき、CLI 対話 wizard は FR-QA-04 の 3 項目を尋ねてはならず、GUI は当該 3 項目を非活性とし値を CLI へ渡してはならない（AKM 子実行自体が起きないため）。判定の実装は実行面ごとに 1 箇所へ限定し、CLI / GUI は [hve/orchestrator.py](hve/orchestrator.py) `_should_enable_qa_akm_dispatch`、Cloud は [.github/workflows/auto-issue-qa-ready-transition.yml](.github/workflows/auto-issue-qa-ready-transition.yml) の `save-qa-answer` job が出力する `sync_required` だけが判定してよい。同一面に判定を重複実装してはならない。FR-QA-04 と同様に環境変数経路を新設してはならない。`--workflow akm` を明示指定した実行は従来どおり本設定の対象外とする。本設定は、QA 回答のたびに `knowledge/` が更新されコスト・実行時間・差分レビュー量が増えることを利用者が制御できるようにするために必要であり、既定を無効とするのは、利用者が明示的に選択していない共有資産（`knowledge/`）への自動書込みを行わないためである。
- **FR-QA-06**: Work IQ 応答の status が `FOUND` または `PARTIAL` であるにもかかわらず、FR-QA-03 の許可済み server/tool 組による tool 実行を SDK イベント上で確認できなかった場合、実行面は当該事象を警告として通知しなければならない。成功記号（`✅`）付きの情報メッセージだけで報告してはならない。統合できた質問が 0 件で、かつ Work IQ 応答が 1 件以上ある場合の統合結果サマリーも警告として扱う。警告には (a) tool 実行を確認できなかったこと、(b) 当該区間で実際に観測されたツール名（観測できた場合）、(c) 診断コマンドを含めなければならない。prompt 本文・tool の引数・M365 応答本文を警告へ含めてはならない（FR-RTO-04 / NFR-SEC-01）。status が `NOT_FOUND` / `UNAVAILABLE` / 不明の応答は一次情報が見つからなかった正常な結果であるため、本警告を出してはならない（全質問で警告が出ると検出漏れの信号が失われるため）。警告文の生成は [hve/workiq.py](hve/workiq.py) の単一ヘルパーに限定し、事前 QA 経路（[hve/runner.py](hve/runner.py)）と prefetch 経路（[hve/orchestrator.py](hve/orchestrator.py)）の双方が同一実装を使わなければならない（FR-MAINT-07）。本要件は、許可集合と実際に公開されるツール名の乖離によって統合が恒久的に 0 件となる事象を、実行中に検知可能にするために必要である。
- **FR-QA-07**: FR-QA-03 の QA 起点 AKM 子実行の標準出力・標準エラーは、当該子実行の run ディレクトリ（`work/run/qa-akm-<id>/`）配下の単一ファイルへ保存しなければならない。破棄してはならない。保存は UTF-8 / 復元可能な decode（`errors="replace"`）で行い、子の出力に含まれる非 UTF-8 バイト列によって親実行を失敗させてはならない。実行結果には当該保存先のリポジトリルート相対パスを含め、親実行は失敗時に `returncode` と当該パスを報告しなければならない。子ログの本文を親実行のログへ展開してはならない（親ログの肥大を避けるため）。バッチ実行では 1 実行につき 1 ファイルとし、当該バッチに含まれる全ファイルの結果へ同一のパスを与える。失敗報告には、FR-CLI-74 の HVE ソース未コミット変更による停止（status=blocked）が代表的な原因であることの確認導線を含めなければならない。また、QA 起点 AKM の登録時点で HVE ソースに未コミット変更を検出した場合は、子実行を起動せずに登録をスキップし、その事実を即時に警告しなければならない。スキップは実行失敗とは別の事象として報告し、`returncode` を失敗として集計してはならない。本事前判定は FR-CLI-74 の最終ガードを置き換えてはならず、登録時点で clean でも実行時点で dirty になり得ることを前提とする。判定は FR-CLI-74 と同一の実装を再利用し、対象リポジトリは coordinator が保持するルートへスコープしなければならない（FR-MAINT-07）。本要件は、子実行が失敗したときに親のログへ件数しか残らず、原因究明に手動再現を要していたことを根拠とする。
- **FR-QA-08**: FR-QA-03 の Work IQ 統合可否を、Workflow を丸ごと再実行せずに確認できる診断経路を提供しなければならない。`workiq-doctor` は `--qa-integration-probe` で、本番の事前 QA と同じ Work IQ プロンプトテンプレートを 1 問だけ送信し、(a) 許可済み server/tool 組の実行確認、(b) 応答 status、(c) 両者から導かれる統合可否を単一の診断チェックとして報告しなければならない。統合可否の判定は事前 QA 本体と同一の実装を使わなければならず、診断用に別実装してはならない（FR-MAINT-07）。判定の理由には、実行未確認の場合に限り当該区間で観測されたツール名を含めなければならない。診断出力へ Work IQ 応答本文・prompt 本文・tool 引数を含めてはならない（FR-RTO-04 / NFR-SEC-01）。本要件は、統合 0 件の受入確認が Workflow 全体の再実行（実測 40 分超）を要し、修正の検証コストが過大だったことを根拠とする。

### 3.13 MCP 通信ログ

本節は、Copilot SDK セッションを介した MCP サーバーとの入出力を、利用者が後から全文で読み返せる形でファイルへ保存する契約を規定する。目的は (a) MCP 経由で何を送り何を受け取ったかを実行後に検証できるようにすること、(b) HVE が Work IQ へ送るプロンプトを利用者が Microsoft 365 Copilot Chat で再利用できるようにすることの 2 点である。本節は §3.11 の実行時 Observability（`observability/events-<pid>.jsonl`）とは別チャネルであり、FR-RTO-01〜07 を改訂しない。

- **FR-MCPLOG-01**: HVE は、Copilot SDK セッションで観測した MCP の入出力を run スコープのログファイルへ全文で追記しなければならない。記録対象は (1) `tool.execution_start` のうち MCP サーバー名を持つもの（MCP サーバー名・MCP ツール名・`tool_call_id`・`arguments`）、(2) 対応する `tool.execution_complete`（成否・結果本文・エラー）、(3) `session.mcp_servers_loaded` / `session.mcp_server_status_changed` のサーバー状態、(4) HVE が Work IQ 専用セッションへ送る自然言語プロンプトと、その応答本文とする。(2) は SDK の `ToolExecutionCompleteData` が MCP サーバー名を持たないため、(1) が記録した `tool_call_id` との相関でのみサーバーを特定しなければならず、相関できない完了イベントを記録してはならない（MCP 由来か組み込みツール由来かを判別できないため）。人間向け表示のための切り詰めを本ログへ適用してはならない。MCP サーバープロセスは Copilot CLI ランタイムが起動し HVE はその標準入出力を保持しないため、記録範囲は SDK イベントが公開する上記に限られる。生の JSON-RPC フレームを取得する目的で MCP サーバーの起動コマンドを書き換えてはならない。
- **FR-MCPLOG-02**: 出力先は `resolve_work_root()` 配下とし、MCP サーバー 1 件につき 1 ファイル `mcp-<サーバー名>.log` とする。親プロセスから起動され作業ディレクトリを共有する子プロセスでは `mcp-<サーバー名>-<pid>.log` とし、複数プロセスが同一ファイルへ追記してはならない（1 レコードが複数行にわたるため、追記の交錯がレコードを破壊するため）。子プロセスの判定条件は `HVE_GUI_SESSION_ID` が非空であるか、`HVE_STATS_STREAM` が既存の真値集合（`1` / `true` / `True`）に一致することとし、[hve/console.py](hve/console.py) が `[hve:stats]` の子プロセス配信可否に用いている条件と同一でなければならない（FR-MAINT-07）。GUI Autopilot の APP 別子プロセス（[hve/gui/autopilot/child_launcher.py](hve/gui/autopilot/child_launcher.py)）は `HVE_STATS_STREAM` を付与されず `HVE_GUI_SESSION_ID` だけを継承する一方、CLI Autopilot の子プロセス（[hve/autopilot/cli_runner.py](hve/autopilot/cli_runner.py)）は `HVE_STATS_STREAM=1` を付与されるため、いずれか一方だけを条件にすると他方で追記が交錯する。サーバー名はファイルシステム安全な文字へ正規化してよいが、SDK が報告した名前以外の別名へ写像してはならない。`HVE_WORK_ROOT` 未設定時および dry-run では書き込んではならない。形式は UTF-8 / LF / BOM なしとし、各レコードは時刻・種別・サーバー名を含む 1 行のヘッダで始めなければならない。1 ファイルが 32 MiB に達した場合は追記を停止し、その事実を 1 回だけ警告する（ローテーションは行わない）。書き込み失敗によって Step を失敗させてはならない。本機能のために新規の CLI オプション・設定項目・環境変数を追加してはならない。
- **FR-MCPLOG-03**: 本ログは prompt 本文・tool の引数・応答本文を意図的に保持するため、FR-RTO-04 の allowlist は適用しない。ただし NFR-SEC-01 が対象とする認証情報は、既存のマスク実装（[hve/workiq.py](hve/workiq.py) `_sanitize_diagnostic_text`）を再利用して記録前に伏せなければならず、同等の処理を新規に実装してはならない（FR-MAINT-07）。当該実装は完全なサニタイズを保証しないため、本ログが業務データを平文で含むことと、`.gitignore` の `*.log` によりリポジトリへコミットされないことを、利用者向けドキュメントへ明記しなければならない。人間向け表示の抑止設定（`quiet` / `final_only` / verbosity）によって記録を止めてはならない（FR-RTO-02 と同じ「収集・保存」と「表示」の分離方針）。

### 3.14 Prompt source centralization

本節は、HVE がモデルへ渡す固定 prompt 本文の正本を `.github/prompts/` 配下へ集約し、読み込み経路と許可範囲を固定する契約を規定する。目的は (a) prompt 本文の重複定義を防ぐこと、(b) 実行経路ごとに異なる prompt 本文が混在する状態を防ぐこと、(c) prompt 読み込み時のパス逸脱や欠損を model call 前に fail-closed で検出することの 3 点である。

- **FR-PROMPT-SRC-01**: HVE が管理する固定 model-facing prompt 本文の正本は `.github/prompts/**` 配下の UTF-8 Markdown ファイルだけとし、Python / Workflow / shell / PowerShell は prompt の選択、安全な読込、動的値補間、および補間済み payload の送信だけを担わなければならない。正本は既存の flat Agent prompt に加え、active Step body、fan-out addendum、runtime fragment、Cloud 実行指示、developer / evaluation harness の固定 prompt を含む。Step body は `steps/`、fan-out addendum は `fanout/`、Cloud 実行指示は `cloud/`、developer / evaluation harness を含むその他の HVE 内部固定 prompt は用途別に `runtime/` 配下へ分類しなければならない。Python 定数、Workflow 定義、manifest、環境変数、CLI 引数、評価 harness のコード、Cloud Agent assignment を構築する Workflow 本文へ固定 prompt 本文を重複保持してはならない。ただし実行時にファイルから読み込んで動的値を補間した payload を model / SDK / Copilot assignment へ送信することは重複保持に含めない。利用者入力、動的データ、UI 表示文言、ログ／エラーメッセージ、テスト fixture、生成アプリが所有する生成物としての Markdown／コード、および HVE 管理外の third-party SDK / MCP / model prompt は対象に含めない。
- **FR-PROMPT-SRC-02**: Prompt 読み込みの単一実装は [hve/prompt_loader.py](hve/prompt_loader.py) とし、repo root の `.github/prompts/` を基準として同 directory 配下だけを許可する安全な repository-relative path を解決対象としなければならない。絶対パス、`..` を含む相対パス、`.github/prompts/` 外への escape、symlink / junction を経由した逸脱を許してはならない。必須 prompt が欠損、空文字、無効な UTF-8、または安全でないパス解決結果となった場合は、model call、SDK session 作成、Copilot assignment の前に fail-closed で停止しなければならない。必須 prompt への inline fallback、別経路からの自動生成、二重定義、manifest / flag / 環境変数 / CLI option / 外部依存による迂回、および hot reload は許可してはならず、本機能のために新規 manifest / flag / 環境変数 / CLI option / 外部依存を追加してはならない。編集内容は次回 process / session から反映する。ただし公開 API `load_prompt(agent_name)` は flat Agent prompt を読む互換 facade として呼び出し互換性を維持しなければならない。

---

## 4. HVE Cloud Agent Orchestrator 固有要件

### 4.1 トリガー仕様

- **FR-CLOUD-01**: 監視イベントは `issues` の `opened` / `labeled` / `closed` の 3 種（[.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)）。
- **FR-CLOUD-02**: 起動はラベルベース。`trigger_map` に従い、対応する `auto-*-reusable.yml` を `workflow_call` で起動する。
- **FR-CLOUD-03**: `opened` イベントでは `author_association` が `OWNER` / `MEMBER` / `COLLABORATOR` のいずれかである場合のみ起動する。**`labeled` / `closed` イベントには `author_association` ガードは適用されない**。
- **FR-CLOUD-04**: `closed` イベントでは Issue タイトルの `[AAS]` / `[AAD-WEB]` 等プレフィックスから対象 Workflow を判定する。
- **FR-CLOUD-05**: `setup-labels` ラベル付与時は `setup-labels.yml` を起動する。
- **FR-CLOUD-06**: registry と同期していない Cloud reusable workflow を dispatcher から起動してはならない。同期とは、reusable workflow が生成する Step Issue の Step ID 集合と Custom Agent 集合が、[.github/scripts/bash/lib/workflow-registry.sh](.github/scripts/bash/lib/workflow-registry.sh) と [hve/workflow_registry.py](hve/workflow_registry.py) の当該 Workflow 定義に一致することを指し、判定は [hve/tests/test_cloud_reusable_workflow_parity.py](hve/tests/test_cloud_reusable_workflow_parity.py) が行う。同期が確認できた Workflow は dispatch 対象としてよい。ASDW-WEB は [.github/workflows/auto-app-dev-microservice-web-reusable.yml](.github/workflows/auto-app-dev-microservice-web-reusable.yml) が現行 Step 体系と非同期であったため Cloud 起動を停止していたが、同 workflow を現行体系へ再構築して同期を確立したため、dispatcher の停止対象（`cloud_dispatch_disabled_targets`）と停止通知ジョブを撤去する（[.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)）。将来いずれかの Workflow で同期が崩れた場合は、本要件に基づき対象 ID と根拠を明記したうえで再び dispatch 対象から外す。AKM は [.github/scripts/bash/lib/workflow-registry.sh](.github/scripts/bash/lib/workflow-registry.sh) へ未登録で reusable workflow が Step をハードコードしているため、同期判定は [hve/workflow_registry.py](hve/workflow_registry.py) の AKM 定義（Step.1 `KnowledgeManager` → Step.2 `QA-DocConsistency`）に対してのみ行う。[.github/workflows/auto-knowledge-management-reusable.yml](.github/workflows/auto-knowledge-management-reusable.yml) は Step.1 と Step.2 の Step Issue を生成し、Step.1 完了で Step.2 を起動し、Step.2 完了で Root Issue へ `akm:done` を付与しなければならない。Step.1 の D01〜D21 fan-out を Cloud で Step Issue へ展開してはならない（`knowledge/` の出力空間は `target_files` によらず D01〜D21 全体と `knowledge/business-requirement-document-status.md` を含み、Step Issue 単位の並列化が同一ファイルへの同時書込みを生むため。FR-QA-03 と同一の根拠）。
- **FR-CLOUD-07**: AAR（Agentic Retrieval Add-on）を Cloud Agent Orchestrator の対象とする。`trigger_map` へ `auto-agentic-retrieval` → `AAR`、`done_map` へ `aar:done` → `AAR`、`closed_prefix_map` へ `[AAR]` → `AAR` を登録し、`auto-agentic-retrieval-reusable.yml` を `workflow_call` で起動する。起動トリガーラベル `auto-agentic-retrieval` と状態ラベル `aar:initialized` / `aar:ready` / `aar:running` / `aar:done` / `aar:blocked` は [.github/labels.json](.github/labels.json) へ登録しなければならない。AAR の全 Step は `enable_agentic_retrieval` が `no` のとき実行対象から外れる（[hve/workflow_registry.py](hve/workflow_registry.py) の `disabled_when_config`）ため、Cloud も FR-CLOUD-10 で抽出した同一値を受け取り、`no` のときは Step Issue を生成してはならない。AAR は AAD-WEB / ASDW-WEB を再実行せずに Agentic Retrieval だけを後付けする単独 Workflow であり、Cloud だけ実行経路を持たない状態を解消するために本要件を置く。

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
  - `ARD` → `auto-requirement-definition-reusable.yml`
  - `AAS` → `auto-app-selection-reusable.yml`
  - `AAD-WEB` → `auto-app-detail-design-web-reusable.yml`
  - `ASDW-WEB` → `auto-app-dev-microservice-web-reusable.yml`
  - `ADFD` → `auto-dataflow-design-reusable.yml`
  - `ADFDV` → `auto-dataflow-dev-reusable.yml`
  - `ADA` → `auto-agent-data-architecture-reusable.yml`
  - `AAG` → `auto-ai-agent-design-reusable.yml`
  - `AAGD` → `auto-ai-agent-dev-reusable.yml`
  - `AAR` → `auto-agentic-retrieval-reusable.yml`
  - `ADOC` → `auto-app-documentation-reusable.yml`
  - `AKM` → `auto-knowledge-management-reusable.yml`
- **FR-CLOUD-21**: 通常の AKM Orchestrator と QA 起点 AKM 調整 Workflow は `akm-knowledge-write-${{ github.repository }}` により同一リポジトリ内で直列化し、`knowledge/` 配下への並列書き込み競合を防止する。QA 起点 AKM 調整 Workflow は当該 group を保持して子 AKM の終端を待機するため、`qa-akm-sync` ラベルを持つ Root / Step Issue の reusable AKM job だけは `akm-qa-sync-child-${{ github.repository }}` で直列化し、自己デッドロックを回避する。通常 AKM を child group へ流してはならず、QA 同期 Root の `qa-akm-sync` は Step Issue 作成時のラベルへ伝播しなければならない（[.github/workflows/auto-knowledge-management-reusable.yml](.github/workflows/auto-knowledge-management-reusable.yml) / [.github/workflows/auto-akm-after-qa.yml](.github/workflows/auto-akm-after-qa.yml)）。
- **FR-CLOUD-22**: **AKM Orchestrator では** `check_qa_skip` ジョブが前段で実行され、`auto-qa` のスキップ条件を判定する。他 reusable workflow の同等チェック有無は要確認。
- **FR-CLOUD-23**: AKM Orchestrator のジョブタイムアウトは 360 分。
- **FR-CLOUD-24**: Cloud Agent Orchestrator が現在対応する Knowledge Management (`AKM`) 以外の Workflow で Issue Form の `enable_qa` が有効な場合、`*:qa-ready` / `*:qa-drafting` の回答受領後、イベントの回答コメント ID を一次キーとして当該 Issue への帰属を検証し、回答時刻（同秒時はコメント ID）より前の最新質問票とだけ対応付けて FR-QA-03 の回答済み形式へ正規化する。`^qa/Issue-[0-9]+-questionnaire-answered-[0-9a-f]{8}\.md$` に一致する固定のパスセーフなファイルとして対象 branch へ保存し、Contents API の再取得結果と SHA を照合してからメインタスクをアサインしなければならない。回答コメントが構造化回答として解決できず、かつ未回答項目に既定値が無い場合は `qa-ready` を維持して修正を求める。保存用 GitHub Actions job は固定 `qa/` パスだけを書き込み、job 単位の `contents: write` と `GITHUB_TOKEN` を使い、branch の実在を確認し、branch protection を迂回してはならない。保存成功後は source Issue 番号・QA SHA・対象 branch・対象ファイルを入力として `workflow_dispatch` 対応の QA 起点 AKM 調整 Workflow を非同期 dispatch する。dispatch job だけに `actions: write` を付与し、GitHub API が dispatch 要求を成功として受理した時点で source Workflow は AKM 調整 job の開始・完了を待たず続行する。調整 Workflow は AKM Root Issue body の `<!-- qa-akm-sync: source-issue=<N>; qa-sha=<64hex>; branch=<branch> -->` を冪等キーとし、open / closed の両方から同一キーを検索して重複を拒否する。既存 Root の routing label が部分失敗で欠落している場合はポーリング前に自己修復する。リポジトリ単位の concurrency を取得した job 内で独立 AKM Root Issue を作成・アサインした後、上限 360 分の低頻度ポーリングにより当該 AKM Root Issue が `akm:done` / `akm:blocked` または closed になるまで待機し、その間 concurrency を保持する。タイムアウト判定の直前には終端状態を再取得し、完了済み Root へ `akm:blocked` を誤付与してはならない。ここで直列待機するのは後続の AKM 実行だけであり、source Workflow は待機対象ではない。外部 Copilot Agent は Actions の初期化 job 終了後も `knowledge/` を更新し得るため、既存の job 終了までの concurrency だけでは同時書込みを防げず、この独立した保持 job を必要とする。タイムアウト時は AKM Root Issue を `akm:blocked` として待機を終了し、source Workflow の成否は変更しない。AKM の auto-merge は source の設定を継承し、強制的に有効化してはならない。`*:qa-ready` / `*:qa-drafting` が同時に複数存在する場合は fail-closed とし、ラベル遷移は新状態の追加と read-back を先に行い、旧状態の削除後にも再検証し、不整合時は旧状態を復元する。Copilot の質問票生成 PR が opened になっただけでメインタスクを開始してはならず、PR opened 経路は質問票コメント確認後の `*:qa-drafting` → `*:qa-ready`（回答待ち）までに限定する。Cloud の AKM 成果物契約は現行の単一 Step（knowledge 文書生成・管理）を対象とし、CLI registry の Step 2 横断整合性レビュー追加は本要件の対象外とする。Cloud dispatch が停止・未実装の Workflow を本要件だけを理由に新規対応してはならない。ADI は Cloud dispatcher 非対応であるため、本要件は ADI の Cloud 対応を要求しない。

- **FR-CLOUD-25**: FR-CLOUD-24 が作成する QA 起点 AKM Root Issue は、source Issue Form で選択された AKM 用モデルを継承しなければならない。Issue Form は Knowledge Management 自身を除く各テンプレートへ `akm_model` を追加し、選択肢は既存の `model` / `review_model` / `qa_model` と同一の許可リスト（`Auto` / `claude-opus-4.7` / `claude-opus-4.6` / `gpt-5.5` / `gpt-5.4`）とする。`save-qa-answer` job は source Issue body の `### AKM 用モデル` 節を許可リスト照合付きで抽出し、一致しない値は空文字へ丸めて dispatch 入力へ渡す。調整 Workflow は当該入力を同じ許可リストで再検証し、一致しない場合は自ら `Auto` へフォールバックしたうえで、作成する AKM Root Issue body の `### 使用するモデル` 節へ必ず値を書き込み、`akm` reusable workflow の既存モデル抽出経路（[.github/scripts/bash/lib/extract-model.py](.github/scripts/bash/lib/extract-model.py)）がそのまま解決できる形にしなければならない。未指定・不正値・許可リスト外を理由に dispatch または調整 Workflow を失敗させてはならない。Cloud 面には reasoning effort / context tier に相当する設定が存在しないため、本要件はモデルのみを対象とし、FR-QA-04 の `akm_reasoning_effort` / `akm_context_tier` を Cloud へ持ち込んではならない。本要件は Cloud の QA 起点 AKM が常に既定モデルで実行され、利用者が AKM だけのモデルを選べなかった状態を解消するために必要である。
- **FR-CLOUD-26**: Cloud Agent Orchestrator は FR-QA-05 の `qa_akm_background_merge` に相当する入力を Issue Form で受け取り、無効のときは FR-CLOUD-24 の QA 起点 AKM dispatch を行ってはならない。Issue Form は Knowledge Management 自身を除く各テンプレートへ `enable_qa_akm_merge` を追加し、既定は未チェック（無効）とする。AKM Root Issue から別の QA 起点 AKM を再帰生成しないため、`knowledge-management.yml` へ追加してはならない。`save-qa-answer` job は source Issue body の当該節を抽出し、チェックを確認できない場合・節が存在しない場合・解釈できない場合はいずれも無効として `sync_required=false` を出力しなければならない。抽出不能を理由に job を失敗させてはならない。判定は `sync_required` の 1 箇所へ限定し、`dispatch-akm` や後続 job の条件式へ同じ判定を重複実装してはならない。本要件は、Cloud だけが常に QA 起点 AKM を起動し CLI / GUI と挙動が不一致になることを防ぐために必要である。

### 4.5 次 Workflow 推奨機能

- **FR-CLOUD-30**: `mode == 'state_transition'` のとき、`suggest-next` ジョブは完了 Workflow に対応する後続候補を `gh issue comment` で投稿する（[.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)）。

### 4.6 Runner 選択

- **FR-CLOUD-40**: `runner_type` 入力に応じて、reusable orchestrator は `["self-hosted","linux","x64","aca"]` または `["ubuntu-latest"]` を選択する。

### 4.7 HITL エスカレーション

- **FR-CLOUD-41**: Cloud Agent Orchestrator は、明示的な `workflow_dispatch` 実行時に `{prefix}:blocked` のまま SLA 時間を超えた Open Issue を `{prefix}:human-required` へ昇格し（[.github/workflows/auto-blocked-to-human-required.yml](.github/workflows/auto-blocked-to-human-required.yml)）、人間が `{prefix}:human-resolved` を付与したとき `{prefix}:human-required` / `{prefix}:blocked` / `{prefix}:human-resolved` の 3 つを外して `{prefix}:ready` へ戻さなければならない（[.github/workflows/auto-human-resolved-to-ready.yml](.github/workflows/auto-human-resolved-to-ready.yml)）。SLA 閾値は `vars.HITL_BLOCKED_SLA_HOURS` とし、未設定時は 24 時間とする。
  - 昇格 Workflow は `workflow_dispatch` だけで起動し、`schedule` その他の自動トリガーを持ってはならない。`workflow_dispatch` の `sla_hours` 入力を最優先とする。既に `{prefix}:human-required` を持つ Issue へ重複付与してはならない。昇格処理はラベルの付与とコメント投稿だけを行い、ラベルを削除してはならない。
  - SLA の経過時間は Issue 全体の `updatedAt`（最終更新時刻）を基準とし、`{prefix}:blocked` の付与時刻ではない。コメントや本文変更で `updatedAt` が進むと判定も延びる。
  - 復帰時に `{prefix}:human-resolved` 自身も削除するのは、同一 Issue が再び `blocked` になったときに同じ遷移を再度発火させるためである。残置すると 2 回目の解消宣言が無視される。
  - `{prefix}:blocked` の自動剥離は `{prefix}:human-resolved` の付与を経た場合に限る。人間が解消を宣言していない Issue を `ready` へ戻さないためである。
  - 対象プレフィックスは FR-STATE-01 が宣言する 11 件とし、2 つの workflow で同一集合を用いなければならない。片方だけを拡張すると、昇格したまま復帰経路を持たない Issue が生じる。
  - 本要件は §13.13 が blocked を「Self-Improve または手動介入の対象とする」と述べるにとどまり、手動介入の引き渡し方法・SLA・復帰経路が未定義だった状態を解消する。CLI / GUI に等価の経路は無く、本要件は Cloud Agent Orchestrator に限定する。
  - 契約テスト: [hve/tests/test_hitl_escalation_contract.py](hve/tests/test_hitl_escalation_contract.py)

### 4.8 運用 Workflow の自動起動禁止契約

- **FR-CLOUD-42**: `.github/workflows/` の repository-managed Workflow は有効な `schedule` を持ってはならない。FR-CLOUD-41 の SLA 昇格を担う `auto-blocked-to-human-required.yml` も `workflow_dispatch` 専用とする。
  - `aas-timeout-monitor.yml` と `auto-qa-timeout-watcher.yml` は `workflow_dispatch` 専用とする。`label-consistency-audit.yml` は `workflow_dispatch` と `issues: [labeled, unlabeled, closed]` だけを持ち、ラベル変更契機の自己修復を維持する。
  - Azure Skills は各開発環境のセットアップでローカルに導入し、`.gitignore` 対象を更新する `sync-azure-skills.yml` を保持してはならない。GitHub Actions 上で同等の同期 Workflow を追加してはならない。
  - 手動専用になった `auto-qa-timeout-watcher.yml` は、定期実行の有効・無効を制御していた `ENABLE_QA_TIMEOUT_WATCHER` で手動実行を無言で skip してはならない。
  - 旧週次全件監査 `audit-plans.yml` と旧日次メトリクス集計 `tdd-retry-metrics.yml` は存在してはならない。前者の削除後も `plan-validation-and-labeling.yml` による PR 差分内の `plan.md` 検証は維持するが、リポジトリ全件の定期再監査を代替すると主張してはならない。
  - `aas-timeout-monitor.yml` の手動入力 `timeout_hours` は正の整数だけを受理し、時刻計算および GitHub API の副作用より前に fail-closed で検証する。手動巡回では `aas:running` の Open Issue を最大 1,000 件取得する。
  - 契約テスト: [hve/tests/test_scheduled_workflow_policy.py](hve/tests/test_scheduled_workflow_policy.py)

---

## 5. HVE CLI Orchestrator 固有要件

### 5.1 サブコマンド体系

[hve/__main__.py](hve/__main__.py) は `argparse` ベースで以下のサブコマンドを提供する:

| サブコマンド | 役割 |
|---|---|
| `run` | インタラクティブ wizard を明示起動（引数なし時の既定は `gui`。FR-CLI-10） |
| `orchestrate` | Workflow ID を指定して DAG を実行 |
| `resume` | current repositoryのdurable executionを選択し、再確認したplanとfenced leaseで再開（FR-CLI-90） |
| `qa-merge` | 回答済み質問票をマージ |
| `workiq-doctor` | Work IQ 連携の診断（`--qa-integration-probe` で事前 QA 統合可否を含む、FR-QA-08） |
| `ingest-docs` | `docs-original/` を走査して `docs/original-design-doc-ingest/` へ目録と正規化済み Markdown を出力 |
| `emit-prompt` | Step のプロンプトを表示（デバッグ用） |
| `gui` | PySide6 ベースの GUI Orchestrator を起動（未導入時はセットアップスクリプトを案内） |
| `cli` | 対話型 CLI ウィザードでワークフローを実行（`run` と同一の対話経路） |
| `login` | GitHub Copilot へログインし、利用可能モデル一覧をキャッシュ |
| `pricing` | AI Credit 料金表を取得・表示（下位サブコマンド `show` / `refresh`） |
| `toolsearch` | Tool Search ランキングの統計を表示（下位サブコマンド `dashboard` / `context`、FR-TS-10 / FR-TS-11） |
| `prompt` | Prompt 版 request から実行計画を提示し、承認後に既存 `orchestrate` へ委譲（下位サブコマンド `plan` / `run`、FR-PROMPT-03 / FR-PROMPT-04） |

本表は `_build_parser()` が登録するトップレベルサブコマンドの全件とし、契約テスト [hve/tests/test_requirement_subcommand_parity.py](hve/tests/test_requirement_subcommand_parity.py) が実装との一致を機械検査する。索引の差分更新対象外サブコマンドの列挙は FR-CLI-77 が別に規定する。

### 5.2 `orchestrate` の必須・主要オプション

- **FR-CLI-01**: 必須引数は `--workflow / -w`（Workflow ID）のみ。
- **FR-CLI-02**: 主要オプション一覧:
  - **モデル**: `--model`、`--review-model`、`--qa-model`、`--akm-model`（FR-QA-04）
  - **実行品質**: `--reasoning-effort`、`--review-reasoning-effort`、`--qa-reasoning-effort`、`--akm-reasoning-effort`、`--context-tier`、`--akm-context-tier`（FR-QA-04）
  - **並列制御**: `--max-parallel`（既定 15）
  - **自動レビュー**: `--auto-qa`、`--auto-contents-review`、`--auto-coding-agent-review`、`--auto-coding-agent-review-auto-approval`
  - **対話制御**: `--force-interactive`（QA 回答入力の TTY 判定をバイパスし対話モードを強制）
  - **Work IQ**: `--workiq`、`--workiq-akm-review`、`--workiq-akm-ingest`、`--workiq-dxx`、`--workiq-draft`、`--workiq-tenant-id`、`--workiq-prompt-{qa,km,review}`、`--workiq-per-question-timeout`
  - **Git/PR**: `--create-issues`、`--create-pr`、`--issue-number`（FR-GUI-25）、`--ignore-paths`、`--branch`、`--repo`
  - **出力**: `--verbose`、`--quiet`、`--verbosity`、`--show-stream`、`--log-level`、`--no-color`、`--banner / --no-banner`、`--screen-reader`、`--timestamp-style`、`--final-only`
  - **タイムアウト**: `--timeout`（既定 21600 秒 = 6h）、`--review-timeout`（既定 7200 秒 = 2h）
  - **MCP / CLI 接続**: `--mcp-config`、`--cli-path`、`--cli-url`
  - **SDK セッション**: `--tool-search` / `--no-tool-search`（FR-MODEL-04、既定有効）
  - **共通絞り込み**: `--steps`、`--app-id`（後方互換、複数指定不可。現行推奨は `--app-ids`） / `--app-ids`、`--resource-group`、`--batch-job-id`、`--usecase-id`
  - **AKM 固有**: `--sources`、`--target-files`、`--force-refresh / --no-force-refresh`、`--custom-source-dir`、`--enable-auto-merge`
  - **ADI 固有**: `--purpose`、`--target-scope`、`--depth`、`--focus-areas`
  - **ADOC 固有**: `--target-dirs`、`--exclude-patterns`、`--doc-purpose`、`--max-file-lines`
  - **ARD 固有**: `--company-name`、`--target-business`、`--survey-base-date`、`--survey-period-years`、`--target-region`、`--analysis-purpose`、`--target-recommendation-id`、`--attached-docs`
  - **追加**: `--additional-prompt`、`--additional-comment`、`--context-max-chars`、`--issue-title`
  - **自己改善**: `--self-improve` / `--no-self-improve`
  - **検証**: `--dry-run`

### 5.3 対話 wizard

- **FR-CLI-10**: `python -m hve`（引数なし）は GUI Orchestrator を既定として起動する。PySide6 が未導入で `ImportError` となる場合に限り、導入手順を示す警告を出したうえで CLI 対話 wizard へフォールバックする。`python -m hve run` および `python -m hve cli` は対話 wizard を明示的に起動する。本項は FR-CLI-77 の「引数なし起動（GUI が既定）の経路は FR-GUI-22 が担う」という担当区分と整合しなければならない。契約テスト [hve/tests/test_requirement_entrypoint_parity.py](hve/tests/test_requirement_entrypoint_parity.py) が本項と実装の一致を機械検査する。
- **FR-CLI-11**: wizard は実行モードとして `quick-auto`（画面表示: クイック全自動）、`custom-auto`（画面表示: カスタム全自動）、`manual`（画面表示: 手動）の 3 つを提供する。`quick-auto` は既定値中心、`custom-auto` は全設定を事前入力した後の無人実行、`manual` は実行中も対話可能な経路とし、Workflow 固有パラメータは選択したモードに従って収集する。
- **FR-CLI-12**: ARD wizard は FR-WF-ARD-03 の 5 表示グループ（`1`〜`5`）をマルチ選択させ、既定選択は同要件の `ARD_DEFAULT_GROUP_IDS` に従う。グループ `1` を選択した場合だけ `company_name` を必須とし、グループ `2` を選択してグループ `1` を選択しない場合だけ `target_business` を必須とする。グループ `1` と `2` を同時選択した場合の空の `target_business` は、Step 1.2 完了後に Strategic Recommendation から生成する bridge 経路で解決する。KPI/OKR の実行有無はグループ `3` の選択だけから導出し、同じ状態を表す別の Yes/No 質問を設けてはならない。グループ `5` はアプリケーション一覧と APP 別要求定義書を一体で生成するため、片方だけを選択する別 UI を設けてはならない。
- **FR-CLI-13**: AKM wizard は `sources` をマルチ選択（`qa` / `original-docs` / `workiq`）し、`workiq` を含む場合のみ取り込み対象 Dxx を尋ねる。
- **FR-CLI-14**: ASDW-WEB wizard は Step 1.3 に到達し得る選択のとき、Step 1.3 の `required_params`（FR-DAG-07）が宣言する Workflow パラメータを順次尋ねる。`default_params` に既定値があるキーは既定値を提示し、空入力（Enter のみ）で既定値を採用する。既定値を持たないキーだけを空入力不可とする。

### 5.4 非対話モード

- **FR-CLI-20**: `cli_args` が `None` でない場合は非対話モード扱いとする（[hve/orchestrator.py](hve/orchestrator.py) `_is_non_interactive`）。
- **FR-CLI-21**: 非対話モードでは `_collect_params_non_interactive` が CLI 引数のみからパラメータを構築し、欠落値は Workflow 既定値を採用する。

#### 5.4.1 Step プロンプト構築

- **FR-CLI-70**: CLI / GUI 実行経路（[hve/orchestrator.py](hve/orchestrator.py) `_build_step_prompt`）が組み立てる Step プロンプトに、`subissues.md` のフォーマット例を注入してはならない。CLI / GUI Orchestrator 配下では分割を workflow DAG / fan-out で表現し、`subissues.md` runtime fork は legacy / 明示 opt-in であるため（[.github/copilot-instructions.md](.github/copilot-instructions.md) §0）、常時注入は誤った作業指示になる。分割手順の参照が必要な場合は Skill `task-dag-planning` に委ねる。
- **FR-CLI-71**: `StepDef.body_template_path` が宣言されている Step でテンプレートのレンダリングが失敗した場合、Orchestrator は簡易プロンプトへフォールバックせず、DAG 実行前にエラーとして停止しなければならない。壊れた縮退プロンプトで Agent セッションを開始してはならない。`body_template_path` が宣言されていない Step が簡易プロンプトを使うことは、本要件の対象外であり従来どおり許容する。

#### 5.4.2 Step 実行時の分離境界

- **FR-CLI-72**: HVE は製品 run の実行中に、HVE 自身のテストスイート（`python -m pytest` 等）を子プロセスとして起動してはならない。ASDW-WEB Step 1.2 のローカル検証は、生成物に対する静的検査（`bash -n`、利用可能な場合の ShellCheck、artifact validator、LF/BOM 検査）に限定する。HVE 自身の回帰テストは CI と開発時に実行する（[hve/asdw_step12_verification.py](hve/asdw_step12_verification.py)）。
- **FR-CLI-73**: `StepRunner` が Copilot セッションへ公開する repository Skill ディレクトリは、`.github/skills` root と、当該 active Step が `required_skills` で宣言した Skill、およびインストール済みの optional Skill に限定する。`.github/skills` 直下の全ディレクトリを無条件に公開してはならない。external Skill の fail-closed 解決は維持する（[hve/runner.py](hve/runner.py)）。
- **FR-CLI-76**: Step 実行経路のセッション生成（[hve/runner.py](hve/runner.py) `_create_session_with_auto_reasoning_fallback`）は、呼び出し側が `mcp_servers` を明示していない場合、リポジトリが宣言した `.github/.mcp.json` の `mcpServers` を `mcp_servers` として渡し、あわせて `enable_config_discovery=False` を指定しなければならない。ワークスペース / ユーザースコープ / プラグイン由来の MCP サーバを自動探索で取り込んではならない。この結果、リポジトリが宣言していない MCP サーバ（実測環境では `github-mcp-server` / `workiq` / プラグイン由来の `azure`）は Step 実行セッションから外れる。`.github/.mcp.json` が存在しない・読み取れない・`mcpServers` が dict でない・`mcpServers` が空の場合は `mcp_servers` を渡さず、`enable_config_discovery` は従来どおり `True` とする（リポジトリが MCP を宣言していない作業ディレクトリでの回帰を避けるため）。呼び出し側が `mcp_servers` または `enable_config_discovery` を明示している経路（`_require_trusted_asdw_data_deploy_mcp_servers` / `_require_trusted_foundry_mcp_servers` / `SDKConfig.mcp_servers`）の挙動は変更してはならない。**Work IQ を有効化した QA サブセッションは本要件の受入範囲に含める**（v2.41 で追加）。当該サブセッションは `mcp_servers` に `_hve_workiq` だけを明示するため従来は自動探索が残り、利用者グローバル設定のプラグインが登録する Work IQ サーバー（`workiq` / `workiq-preview`）が同一セッションへ併存していた。併存側は `tools: ["*"]` で登録されるため HVE が `_hve_workiq` へ課す最小権限 allowlist（`ask` のみ）が及ばず、書き込み系ツール（`create_entity` / `update_entity` / `delete_entity` / `do_action`）および `accept_eula` / `call_function` / `get_debug_link` が同一セッションから到達可能だった（実測: `tools: ["*"]` で公開 14 件）。`available_tools` / `excluded_tools` は既定 `None`、権限ハンドラは `PermissionHandler.approve_all` であり、FR-TS-03 が求める安全境界がどちらの手段でも張られていなかった。したがって当該サブセッションでも `.github/.mcp.json` の宣言分を `mcp_servers` へ併合したうえで `enable_config_discovery=False` を指定しなければならない。併合時は Work IQ 別名（`workiq` / `workiq-preview`）を落とし、HVE が最小権限 allowlist を課した `_hve_workiq` だけを Work IQ 経路として残さなければならない。宣言分が存在しない・読み取れない・空の場合は、`_hve_workiq` の注入だけを従来どおり行い `enable_config_discovery` は `True` のままとする（MCP を宣言していない作業ディレクトリでの回帰を避けるため。本要件の他経路と同じフォールバック規則）。FR-CLI-79 の Azure 除外は本サブセッションにも適用する。`_hve_workiq` のツール allowlist と Work IQ 別名の除外規則（FR-QA-03）は変更しない。新規 CLI オプションおよび新規 `SDKConfig` フィールドを追加してはならない。これらを除く経路では自動探索が残るが、Step 実行の主経路（各 Step のメインセッション）と Work IQ を有効化した QA サブセッションを縮約することを本要件の受入範囲とする。SDK が `enable_config_discovery` を未サポートの場合、既存規則どおり当該引数を剥がして再試行せず停止する（自動探索の再有効化を伴う縮退を禁じる既存の分離境界規則が、本要件により全 Step へ適用される）。Skill の公開範囲は FR-CLI-73 が定める `skill_directories` の明示指定で維持する。`.github/.mcp.json` の各サーバ定義は `tools` キー（`["*"]` = 全件 / `[]` = なし）を明示しなければならない。明示指定した MCP サーバ設定に `tools` キーが無いと、当該サーバは起動されずツールが 1 件も公開されない（実測: `azure` を `tools` なしで明示指定すると connected 0 件・ツール 0 件、`"tools": ["*"]` を付けると connected かつ 68 ツール。`type: "stdio"` の付与では解決しない）。同じ制約は `_require_trusted_foundry_mcp_servers` が渡す設定にも適用される。本要件は FR-TS-03 の pin ポリシー判定を変更しない（`pin_only` の判定は `hve/toolsearch/policy.json` の `step_overrides` だけで決まり、`enable_config_discovery` を参照しない）。本要件は次の実測（Copilot CLI 1.0.79 / SDK 1.0.7、`session.metadata.contextInfo`、model=`claude-sonnet-4.5`、会話 0）を根拠とする: 自動探索が有効なとき、リポジトリが宣言していないユーザースコープ設定・プラグイン由来の MCP サーバが全件接続され、ツール定義は 52,756 tokens（うち MCP 41,096）を占めた。重複していた MCP サーバ 2 系統を環境側で除いた後でも 33,384 tokens（うち MCP 21,728）だった。自動探索を無効にすると同環境で 11,403 tokens（MCP 0）になる。本要件の実装後、`.github/.mcp.json` が宣言する 2 サーバ（`azure` 68 ツール / `microsoft-learn` 3 ツール）だけを公開した Step セッションは 28,763 tokens（MCP 17,217）で、同環境の自動探索有効時 33,527 tokens（MCP 21,728）に対し 4,764 tokens 少ない。あわせて、自動探索は `.github/.mcp.json` を探索対象としておらず（探索対象は作業ディレクトリ直下の `.mcp.json` / `.vscode/mcp.json`）、同ファイル固有のサーバは 1 度も起動していない。本要件はこの「宣言が無視されている状態」の是正を兼ねる。
  - **受入範囲の上書き（v2.51）**: 上記本文末尾の「これらを除く経路では自動探索が残るが、Step 実行の主経路と Work IQ を有効化した QA サブセッションを縮約することを本要件の受入範囲とする」という限定は、本項以下で置き換える。v2.51 以降の受入範囲は、当該 2 経路に加えて [hve/orchestrator.py](hve/orchestrator.py) `_create_session_with_auto_reasoning_fallback` が生成する全セッション（Work IQ 専用 4 経路を含む）とする。受入範囲から除外したままとするのは、本文が列挙する 3 経路（`_require_trusted_asdw_data_deploy_mcp_servers` / `_require_trusted_foundry_mcp_servers` / `SDKConfig.mcp_servers`）と `workiq-doctor` の tool probe（FR-QA-03）だけである。
  - **orchestrator のセッション生成へ本要件の縮約を適用しなければならない**。当該ヘルパーは [hve/runner.py](hve/runner.py) の同名関数と別実装で、リポジトリ宣言の読み取りを行わず `enable_config_discovery` を常に `True` としていたため、ARD の `target_business` 生成・Fleet wave 親・Code Review Agent の各セッションが、利用者グローバル設定およびプラグイン由来の MCP サーバ（実測環境では Work IQ プラグインが宣言する `workiq`）を自動探索で取り込んでいた。判定と縮約の実装は [hve/runner.py](hve/runner.py) の単一のヘルパーへ寄せ、orchestrator 側で同等処理を再実装してはならない（FR-MAINT-07）。
  - orchestrator 経路では、宣言分から Work IQ 別名（FR-QA-03 が単一の正本として保持する `WORKIQ_MCP_SERVER_NAMES` の全要素）を落とさなければならない。Work IQ を使うセッションは自前で `_hve_workiq` を明示するため、宣言経由で別名が混入すると HVE の最小権限 allowlist が及ばないサーバへ到達しうる。
  - **Work IQ 専用の 4 セッション**（`_prefetch_workiq_detailed` / `_run_akm_workiq_verification` / `_run_akm_workiq_ingest` / `_run_ard_workiq_usecase`）も本要件の受入範囲に含める。これらは `mcp_servers` に `_hve_workiq` だけを明示するため従来は自動探索が残り、事前 QA サブセッションと同じ併存（`tools: ["*"]` のプラグイン由来 `workiq`）が発生していた。宣言分（Work IQ 別名を除く）を併合したうえで `enable_config_discovery=False` を指定しなければならない。宣言分が存在しない・読み取れない・空の場合は、`_hve_workiq` の注入だけを従来どおり行い `enable_config_discovery` は `True` のままとする（QA サブセッションと同じフォールバック規則）。
  - FR-CLI-79 が定める `azure` 除外規則を orchestrator 経路へも適用しなければならない。FR-CLI-79 本文は Step 実行セッションを対象に記述しているが、除外の根拠（当該 Workflow の全 Step が Azure に言及しない）は同じ Workflow に属する orchestrator セッションにも当てはまるためである。これを可能にするため、当該ヘルパーは Workflow ID を受け取れなければならない。Workflow ID が解決できない経路（Fleet wave 親 / Code Review Agent）では従来どおり全宣言サーバを渡す（FR-CLI-79 の宣言漏れ規則と同じ側へ倒すため）。
  - 宣言が存在しない・読み取れない・空の場合のフォールバック（`enable_config_discovery` を `True` のまま据え置く）は orchestrator 経路でも同一とする。

#### 5.4.3 Phase 1 リクエストのサイズ計画

- **FR-CLI-84**: `StepRunner` は Phase 1 メインタスクを Copilot SDK セッションへ送る前に、送信するプロンプトの UTF-8 バイト数を計測し、HVE 内部のプロンプト予算と照合して Phase 1 のモデル呼び出し回数を決定しなければならない。計測は文字数ではなくバイト数で行う（日本語は 1 文字 3 バイトになり得るため、文字数では超過を検出できない）。判定と計画の実装は [hve/phase1_request_plan.py](hve/phase1_request_plan.py) の単一実装に限定し、[hve/runner.py](hve/runner.py) 側へ同等の判定を再実装してはならない（FR-MAINT-07）。
  - 予算内の場合、プロンプトを改変せず Phase 1 のモデル呼び出しを **ちょうど 1 回** 行わなければならない。予算超過の場合、Phase 1 のモデル呼び出しを **1 回も行わず** Step を失敗として終了しなければならない。同一内容の自動再送、内容を変えた自動再試行、および同一セッションへの複数ターン分割送信を行ってはならない。任意位置での自動切り詰め、および LLM による自動要約で送信可能サイズへ縮めてはならない。要求が欠落したまま実行が続くと、成果物の欠落を検出できないためである。
  - 判定は 3 段階で行う。(1) `run_step()` が受け取ったプロンプト単体が既に予算を超えている場合は、Copilot SDK クライアント・セッションの生成、および Phase 0 事前 QA より前に停止する。(2) fan-out 追加指示・APP 要求コンテキスト・Agent Prompt 本文・Skill Guard・各 policy prefix・実行モード制約 / TDD / レビュー所有権の各 suffix という Phase 0 前に確定する成分を連結し、メインセッション生成と Phase 0 事前 QA より前に再判定する。(3) 事前 QA コンテキストを含む **最終プロンプト**を送信直前に再判定する。(1) だけでは後続の確定成分による超過を、(2) だけでは事前 QA による超過を検出できず、(3) だけでは不要なメインセッション生成と事前 QA のモデル呼び出しを消費するためである。
  - 最終プロンプトは送信する実ブロック列から 1 回だけ構成し、通知に用いる成分別バイト数の合計は最終プロンプトの UTF-8 バイト数と一致しなければならない。区切り・固定見出し・各 suffix を内訳から除外してはならない。通知には、状態・プロンプトの UTF-8 バイト数・予算バイト数・予定した Phase 1 呼び出し回数・成分名ごとのバイト数だけを含め、プロンプト本文、`additional_prompt` の本文、事前 QA 応答の本文、および認証情報を含めてはならない（FR-RTO-04 / NFR-SEC-01）。
  - `step_start` 後の予算超過は `step_end(..., "failed")` を 1 回記録して終了しなければならない。`dry_run=True` はモデル呼び出しを行わない既存経路であるため、本予算によって失敗へ変更してはならない。
  - 予算は HVE 内部の定数とし、CLI オプション・GUI 設定項目・環境変数を新設してはならない。既存の `context_injection_max_chars`（`--context-max-chars`）は Phase 0 / Phase 3 等へ注入する補助コンテキストの文字数上限であり、本要件のバイト予算とは別の設定である。一方を他方へ流用してはならない。
  - 本要件は、Copilot API がリクエスト全体（システムプロンプト・会話履歴・ツール定義を含む）に上限を持つことに対する HVE 側の安全余白として定める。当該上限の具体値は GitHub の公開仕様として確認できていないため、予算値を公開仕様値として記述してはならない。実測として、HVE の Phase 1 送信が `The request is too large to send through CAPI Responses. Try shortening the conversation or prompt. (32.7 MB request; 5.0 MB limit)` で失敗した事例がある。
  - 予算超過は、送信可能サイズへ縮めるのではなく、利用者が入力を分割・ファイル化して再実行するための情報を提示して停止することで解消する。
- **FR-CLI-85**: Phase 1 の最終プロンプトにおいて、`additional_prompt` に由来するブロックと markdown-query 強制ブロックは、それぞれ高々 1 回しか現れてはならない。[hve/orchestrator.py](hve/orchestrator.py) の `_compute_step_additional_prompt()` / `_build_step_prompt()` が Step プロンプト末尾へ既に連結しているため、[hve/runner.py](hve/runner.py) が同じ値を再度前置してはならない。同一の指示を重複して送ることは、モデルへ与える指示を変えないままリクエストサイズだけを増やし、FR-CLI-84 の予算を無駄に消費するためである。本要件は `additional_prompt` の内容・適用範囲・利用者向け設定を変更しない。

### 5.5 Issue / PR 作成（CLI 経路）

- **FR-CLI-30**: `--create-issues` 指定時、CLI は以下のシーケンスを実行する: 新ブランチ作成 → Root Issue 作成 → Sub-Issue 作成（active Step ごと） → DAG 実行 → `git add/commit/push` → PR 作成 → **`--auto-coding-agent-review` フラグ指定時のみ** Code Review Agent レビュー → サマリー出力（[hve/orchestrator.py](hve/orchestrator.py) module docstring および `_create_issues_if_needed`）。
- **FR-CLI-31**: `--create-issues` または `--create-pr` には `--repo` と `GH_TOKEN`（または `GITHUB_TOKEN`）が必須。未設定時は起動前検証エラーとして fail-closed で停止し、Issue / PR 作成だけを暗黙にスキップして Workflow を続行してはならない。
- **FR-CLI-32**: `--create-pr` は PR 作成のみ行い、自動マージは実行しない（Issue Template の `enable_auto_merge` とは別運用）。
- **FR-CLI-33**: `--ignore-paths` で指定されたパスは `git add` の pathspec 除外として扱う（既定値は `SDKConfig` 側）。
- **FR-CLI-34**: `--delete-local-merged-branch`（既定 **有効**、`--no-delete-local-merged-branch` で無効化。config: `delete_local_merged_branch`）が有効で、かつ `enable_auto_merge` が有効・全 Step 成功・今回実行で PR が作成済みの場合に限り、CLI は PR の merged 状態をポーリングし（既定 15 秒間隔・最大 600 秒）、リモートの auto-approve-and-merge フロー完了（PR が merged）を検知後、今回作成した作業ブランチを**ローカルのみ**削除する（`git checkout <base_branch>` の後に `git branch -D <working_branch>`）。squash マージではローカルブランチが「マージ済み」と判定されないため `-D` を用いる。タイムアウト・PR が未マージ（closed 等）・`checkout` 失敗のいずれかの場合は削除せず警告ログを 1 行出力する。実行中断（Ctrl+C 等）時はポーリングが中断され削除処理に到達しないため、削除は行われない。リモートブランチは削除せず、github.com の「Automatically delete head branches」設定に委ねる。過去に作成済みの作業ブランチは対象外（今回実行分のみ）。`enable_auto_merge` が無効な場合や PR 未作成時は何もしない（[hve/orchestrator.py](hve/orchestrator.py)、[hve/github_api.py](hve/github_api.py)、[hve/config.py](hve/config.py)）。
  - ローカル削除の適格性判定と `git checkout <base_branch>` → `git branch -D <working_branch>` は [hve/branch_cleanup.py](hve/branch_cleanup.py) の単一 core に集約し、Orchestrator と FR-GUI-37 の GUI monitor は同じ core へ委譲しなければならない（FR-MAINT-07）。適格性判定は、当該 run が branch を新規作成したことを示す `created_by_hve=True`、target の PR 番号が `bool` ではない正の整数で取得結果の `number` と一致すること、PR の `merged is True`、PR の `head.ref` と対象 branch の一致、`head.repo.full_name` と対象 repository の一致、PR の `base.ref` と対象 base branch の一致、`base.repo.full_name` と対象 repository の一致、および対象 branch と base branch の不一致を全て必須とする。repository 名の比較は GitHub の扱いに合わせて大文字小文字を区別しない。値が欠落・不一致の場合は fail-closed とし、git delete command を実行してはならない。当該 core が実行する `git checkout` / `git branch -D` の subprocess は、`text=True` と共に `encoding="utf-8"` を明示しなければならない（`hve/tests/test_orchestrator_git_encoding.py` の横断 decode 契約と同一の理由。Windows 既定 locale では非 ASCII 出力が `UnicodeDecodeError` になり得る）。

#### 5.5.1 HVE ソース保護ガード

- **FR-CLI-74**: アプリ生成 run の開始時、HVE ソース（`hve/`, `mdq/`, `hve-dev/`, `.github/prompts/`, `.github/skills/`, `.github/scripts/`, `.github/io-contracts/`）に未コミット変更が存在する場合、Orchestrator は branch 作成および Agent セッション開始より前に、検出した全パスを一括報告して停止しなければならない。利用者が明示的に指定した target 出力パスは対象外とする。GUI の利用者ローカル設定ファイル `hve/.settings.txt` と、そのアトミック書き込み用一時ファイル `hve/.settings.txt.tmp` は、HVE ソースではなく GUI が実行時に書き換える利用者ローカル状態であるため、本ガードの対象外としなければならない。この除外は本ガードに限定し、FR-CLI-75 の staged 検査へ波及させてはならない。新しい override フラグを追加してはならない（[hve/orchestrator.py](hve/orchestrator.py)）。
- **FR-CLI-75**: `git add` の実行後・`commit` の実行前に staged path を検査し、HVE ソースパスが含まれる場合は index を reset して停止しなければならない。target アプリの成果物（`src/**`, `docs/**` 等）のみの staging は従来どおり成功する（[hve/orchestrator.py](hve/orchestrator.py)）。

### 5.6 セッション永続化と再開（廃止）

- **廃止（v1.1）**: GitHub Copilot CLI SDK の複数デバイス間セッション管理が不十分なため、CLI / GUI の Session State（Resume）機能を全廃した。以下はすべて削除済み:
  - `resume` サブコマンド（`list` / `show` / `rename` / `delete` / `continue` / `reconcile` / `gc-orphans`）
  - `session-state/` 永続化（`state.json` / `journal.jsonl` / `.lock` / `journal-archive/`）
  - 起動時 recovery（`HVE_DISABLE_STARTUP_RECOVERY`）、Ctrl+R による中断（graceful pause）
  - 旧 FR-CLI-40〜51（v0.5〜v1.0 で導入された Resume / 2 層トランザクション保護 / RunLock / RunJournal / reconciler 関連要件）
- **存続する機能**: SDK セッション ID の決定論的生成（`hve-<run_id>-step-<step_id>[-<suffix>]` 形式、`make_session_id`）は fork-on-retry のフォーク用 ID 再構成のために存続する（[hve/run_state.py](hve/run_state.py)）。
- **優先規則**: Resume 関連の改訂履歴（§11）と解消済み TBD（§12）は履歴情報であり、現行要件として適用しない。Resume の現行状態は本節を正とする。


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
- **FR-CLI-63**: step-level Self-Improve（[hve/runner.py](hve/runner.py) Phase 4d）の検証結果は、`scan_codebase()` の実測値から決定的に導出しなければならない。LLM 応答 JSON によって `after_quality_score` / `degraded` / `verification_phases` を上書きしてはならない。
  - 判定ロジックは [hve/self_improve.py](hve/self_improve.py) `_build_verification_result()` を単一の実装とし、Phase 4 に同等の判定を再実装してはならない（FR-MAINT-07）。LLM 応答は `VerificationResult.notes` の説明としてのみ使用する。
  - 本委譲により step-level の `degraded` は `_build_verification_result()` の定義（`quality_score` の低下、または test phase が `FAIL`）に従う。従来の step-level 固有定義（test 失敗件数の増加）は廃止する。同一の判定規則を 2 箇所に持たないためである。
  - LLM 応答の JSON パース失敗および JSON ブロック不在は、従来どおり警告として可観測化し、`notes` に `[json_parse_error=...]` を前置しなければならない。
  - 根拠: LLM が `degraded=false` を返すと、実測がデグレードでも Phase 4f のループ停止が働かず、劣化した成果物へ追加の改善試行が積まれる。さらに `learning-NNN.md` に実測と異なる値が残り、次イテレーションの判断材料が汚染される。
- **FR-CLI-64**: [hve/self_improve.py](hve/self_improve.py) `scan_codebase()` は、解決済み scope の対象ファイルに対して秘密情報パターン検査を行い、その結果を `ScanResult.security_status`（`"PASS"` / `"FAIL"`）として設定しなければならない。
  - 検査パターンは `_build_verification_result()` が使用するものと同一とし、新しいパターン集を別に定義してはならない（FR-MAINT-07）。
  - 検査対象は解決済み scope 内のファイルに限る。Self-Improve は scope 内しか変更しない契約（`_path_in_scope()`）であり、scope 外の既存差分を停止理由に含めてはならないからである。
  - 1 ファイルあたりの読み取り量に上限を設け、scope に大きな生成物やバイナリが含まれてもメモリ消費を有界に保たなければならない。上限を超える部分は未検査となる。
  - scope が解決できずスキャン自体を行わない場合（`_empty_scan_result()`）、および解決済み scope path が得られない旧仕様経路は `"PASS"` としてはならず、`"SKIP"` を設定しなければならない。未検査を合格として扱うと fail-open になる。
  - 根拠: `_scan_gate_failure()` は `scan.get("security_status")` が `FAIL` のとき Self-Improve を停止する契約を持つが、当該キーの producer が存在せず、本番経路で当該分岐が発火しない。
- **FR-CLI-65**: `success_criteria` に「テストカバレッジ 70% 以上」を宣言するワークフロー（`asdw-web` / `adfdv`）の `TaskGoal` は、同条件を `criterion_definitions` の criterion として持たなければならない。
  - criterion は `scan.summary.coverage_pct` を metric とし、`gte 70` を満たすことを `required_for_done` とする。判定は既存の `_evaluate_criteria()` を用い、新しい判定関数を追加してはならない（FR-MAINT-07）。
  - `scan_codebase()` は `ScanResult.metric_status` へ `coverage_pct` を設定しなければならない。値は test 系ツールの実行状態（`tool_status.test`）をそのまま用いる。カバレッジは pytest の実行結果からのみ抽出されるため、test が実行されていない場合の `coverage_pct` は測定値ではなく初期値 `0.0` であり、これを未達として扱ってはならないからである。
  - 上記により、test が `NO_TESTS` / `SKIP` / `BLOCKED` / `UNAVAILABLE` のときは `_evaluate_criteria()` が当該 criterion を `BLOCKED` とし、`_required_criteria_unverifiable()` により Self-Improve が `blocked` で停止する。`FAIL` として扱ってはならない。「テストが存在しない」ことと「カバレッジが低い」ことを同一視してはならないからである。
  - 根拠: `success_criteria` が宣言する成功条件のうちカバレッジだけが決定的評価の対象外であり、宣言と実装が一致していない。

### 5.9 起動時の索引差分更新

- **FR-CLI-77**: HVE CLI Orchestrator の起動時（`run` / `cli` / `orchestrate`）、実在する `mdq`（§3.8）および `cq`（§3.9）の索引 DB をバックグラウンドで差分更新しなければならない。
  - 対象は**実在する索引 DB に限る**。`mdq` は `.mdq/index-<lang>-<strategy>.sqlite` に一致するファイル、`cq` は設定ファイルが宣言する profile のうち `.cq/index-<profile>.sqlite` が実在するものとする。索引 DB を新規に作成してはならない。差分更新は既存索引を前提とする操作であり、未構築の strategy / profile を起動時に構築すると、利用者が選択していない索引（埋め込みモデルの取得を伴う `semantic_paragraph` 等）を起動のたびに生成することになるからである。SQLite 索引を持たない strategy（`graphrag`）は、この対象規則により自動的に対象外となる。
  - 更新は差分更新とし、完全再ビルドを行ってはならない。
  - 索引 DB のパス規則と `(lang, strategy)` / profile の解決は `mdq` / `cq` 側の実装を単一の情報源とし、HVE 側で再実装してはならない（FR-MAINT-07）。
  - 本処理の完了前に `mdq` / `cq` の watcher を起動してはならない。同一の索引 DB に対して 2 つの書き込み経路が同時に存在してはならず、`mdq` の索引構築は走査の終了時に 1 回だけコミットするため、走査中は書き込みトランザクションを保持しうるからである。
  - 索引更新の失敗、任意依存の欠落、`cq` 設定の不在は、警告の出力に留めなければならない。Workflow の実行を中断させてはならない。
  - 環境変数 `HVE_STARTUP_INDEX_REFRESH` で無効化できなければならない。既定は有効とする。

### 5.10 CLI Autopilot の実行開始確認

- **FR-CLI-78**: `hve orchestrate --autopilot-chain` は、標準入力が対話可能な場合、計画サマリの表示後・APP チェーンの実行開始前に、利用者へ実行の可否を確認しなければならない。
  - 承認されなかった場合は Step を 1 つも実行せずに終了しなければならない。CLI Autopilot は複数 APP のチェーンを無人で連続実行するため、計画を提示しただけで即時に実行を開始してはならない。
  - 標準入力が対話不可能な場合（CI 等）は確認せずに実行する。既存の非対話実行を後方非互換にしてはならない。確認を省略するための新しいオプションを追加してはならない。
  - `--autopilot-dry-run` 指定時は従来どおり計画のみを表示して終了し、確認を求めてはならない。
  - 対話可否の判定は既存の CLI 実装と同一の規則（`sys.stdin.isatty()`）に従う（[hve/__main__.py](hve/__main__.py)）。

### 5.11 Azure を利用しない Workflow の MCP 縮約

- **FR-CLI-79**: FR-CLI-76 がリポジトリ宣言の MCP サーバを Step 実行セッションへ渡す際、当該 Step が属する Workflow が「Azure を利用しない」と宣言されている場合、`azure` MCP サーバを除いて渡さなければならない。
  - 宣言は **Workflow 単位の allowlist** とし、[hve/runner.py](hve/runner.py) の定数 1 つで保持する。**allowlist に載っていない Workflow・`workflow_id` が解決できない場合は、従来どおり全サーバを渡さなければならない**（宣言漏れが機能破壊にならない側へ倒すため）。
  - Step 単位の判定を行ってはならない。Step ごとの Azure 利用有無を機械的に判定する根拠は、Custom Agent プロンプト中の文字列一致しか無く、誤判定時に Azure 系 Step を機能破壊するためである。
  - 呼び出し側が `mcp_servers` を明示している経路のうち、FR-CLI-76 が受入範囲から除外する 3 経路（`_require_trusted_asdw_data_deploy_mcp_servers` / `_require_trusted_foundry_mcp_servers` / `SDKConfig.mcp_servers`）の挙動を変更してはならない。当該 3 経路では `enable_config_discovery=False` の指定も変更してはならない。Work IQ を有効化した QA サブセッションは v2.41 で FR-CLI-76 の受入範囲へ移ったため本条の対象外とする。
  - `microsoft-learn` MCP サーバを除外してはならない。Azure を利用しない Workflow でも公式ドキュメント参照は発生しうる。
  - 新規 CLI オプションおよび新規 `SDKConfig` フィールドを追加してはならない。
  - **allowlist の妥当性は次の 2 点を機械的に検査しなければならない**。(1) allowlist の各 Workflow に属する全 Step の Custom Agent プロンプトが Azure に言及しないこと、(2) `.github/.mcp.json` の `mcpServers` に除外対象のサーバ名が実在すること。前者は allowlist が実装から取り残されて Step を壊すことを防ぎ、後者はサーバ名の改名により縮約が無言で無効化されることを防ぐ。
  - 本要件は次の実測を根拠とする（全 13 Workflow / 131 Step の Custom Agent プロンプト走査）: `ard`（10 Step）/ `akm`（2 Step）/ `adi`（9 Step）/ `adoc`（23 Step）の計 44 Step は 1 件も Azure に言及しない。一方 `aas` は 10 Step 中 1 件、`aad-web` は 8 Step 中 5 件が言及するため、Workflow 単位では除外できない。

### 5.12 CLI Autopilot の lane 経過時間観測

- **FR-CLI-80**: `CliAutopilotRunner` は lane（APP チェーン）ごとの経過時間を計測し、閾値を超えた lane について警告を 1 行出力しなければならない。
  - **lane を停止させてはならない**。本要件は観測のみを規定する。NFR-TIME-01 の CLI タイムアウトは**無入出力時間ベース**であり、出力が継続する限り lane は無制限に伸びうる。一方 NFR-TIME-02 のとおり Cloud 側は経過時間ベースの上限を持つ。この Cloud / CLI の差を可視化することが本要件の目的である。
  - 閾値は **360 分**とし、NFR-TIME-02 の Cloud 側ジョブタイムアウトと同値にする。**ハードコードとし、設定では変更不可**とする（NFR-PERF-02 と同じ扱い）。新規 CLI オプションおよび新規 `SDKConfig` フィールドを追加してはならない。
  - 警告は lane の完了時に 1 回だけ出力する。lane が chain 内で複数の Workflow を順次実行する場合、計測対象は最初の Workflow の起動から lane 完了までとする。
  - 警告の出力に失敗しても実行を中断してはならない（NFR-RTO-03 と同じ扱い）。
  - 警告の有無は `CliRunSummary` の内容および終了コードを変えてはならない。
  - 経過時間の取得は差し替え可能にし、実時間に依存するテストを書かずに検証できなければならない。
  - 索引と無関係なサブコマンド（`login` / `pricing` / `toolsearch` / `qa-merge` / `workiq-doctor` / `emit-prompt` / `ingest-docs`）では起動してはならない。`gui` サブコマンドと引数なし起動（GUI が既定）の経路は FR-GUI-22 が担う。CLI 側は作業ディレクトリをリポジトリルートとして扱うのに対し、GUI は起動位置からルートを遡って解決するため、引数なし起動を CLI 側で担うと誤ったルートを対象にしうる。
  - `--dry-run` でも実行してよい。索引 DB は Workflow の成果物ではないためである。既存の watcher が `dry_run` で起動しない扱いとは異なる点を、利用者向け文書へ明示しなければならない。

### 5.13 Work IQ 利用不可時の自動無効化

- **FR-CLI-81**: Work IQ を要求する設定が有効な実行で、本処理前の Work IQ 認証確認（[hve/__main__.py](hve/__main__.py) `_run_workiq_auth_preflight`）が失敗した場合、非対話環境では実行を停止してはならず、当該実行に限り Work IQ 関連設定を無効化して続行しなければならない。
  - 無効化は既存の `_disable_workiq()` を再利用し、`workiq_enabled` / `workiq_qa_enabled` / `workiq_akm_review_enabled` / `workiq_akm_ingest_enabled` / `workiq_draft_mode` と、`params` の `sources` に含まれる `workiq` トークン・`workiq_akm_ingest_dxx`・`ard_workiq_enabled` を対象とする。同等処理を新規に実装してはならない（FR-MAINT-07）。
  - 無効化した場合は、Work IQ を要求した設定名を 1 行で通知しなければならない。通知は既存の非対話失敗時の出力（`_workiq_request_reasons()` の列挙）を再利用し、新しい UI・新しい出力経路を追加してはならない。
  - 対話可能な端末での挙動（無効化して続行するかを利用者へ確認し、拒否されたら停止する）は変更してはならない。利用者が明示的に中止を選べる経路を維持するためである。
  - `--dry-run` の場合、および Work IQ を要求する設定が 1 つも有効でない場合に認証確認を実行してはならない（従来どおり）。
  - 新規 CLI オプション・新規 `SDKConfig` フィールド・新規環境変数を追加してはならない。
  - 本要件が保証するのは認証確認の実行時点までとする。確認を通過した後に認証が失効した場合は、従来どおり実行中の警告（FR-QA-06）に委ねる。
  - 本要件は次の 2 点を根拠とする。(1) GUI が起動する HVE サブプロセスの標準入力は対話不能であるため（FR-GUI-23）、Work IQ を要求する設定が 1 つでも有効なとき認証失敗が常に実行停止になっていた。(2) `--workiq-draft` は `workiq_enabled` と `workiq_qa_enabled` を同時に有効化するため（[hve/__main__.py](hve/__main__.py) `_build_config`）、利用者が Work IQ を無効にしたつもりでも停止しうる。

### 5.14 ローカル起動時の設定整合性 preflight

- **FR-CLI-82**: HVE のローカル起動面（CLI 非対話、CLI 対話 wizard、GUI Plan、GUI / CLI Autopilot）は、GitHub への書き込みを伴う Workflow を開始する前に、GitHub 連携設定の整合性を単一実装で検査しなければならない。
  - 対象は `--create-issues` / `--create-pr`、ADFDV で `enable_auto_merge` が有効な Workflow 全体、およびその他の Workflow で `enable_auto_merge` が有効かつ active step に `requires_remote_cicd=True` の宣言がある実行とする。この対象判定は `--dry-run` の有無で変えてはならない。GitHub への書き込みを行わない通常のローカル実行へ GitHub token・remote 接続を要求してはならない。
  - 検査項目は、`repo` が非空の `owner/repo` 形式であること、`GH_TOKEN` または `GITHUB_TOKEN` が解決できること、`base_branch` が Git branch 名として有効であること、Git remote `origin` が解決できること、および `origin` に完全一致する `refs/heads/<base_branch>` が実在することとする。
  - remote branch の実在確認は読み取り専用の `git ls-remote --exit-code --heads origin refs/heads/<base_branch>` を Python の引数リストかつ `shell=False` で実行し、status `2`（一致 ref なし）とその他の非 0（remote・認証・通信等により検証不能）を区別して報告する。branch 名は 1 件だけを完全な ref として渡し、glob による複数 ref 検査を行わない。Git の対話認証を起動してはならない。
  - 不整合は判定可能な全件を 1 回で報告し、`main`・ローカル branch・GitHub の既定 branch へ暗黙に補正してはならない。remote branch が存在しない場合も `_git_checkout_new_branch` のローカル branch fallback へ進めず fail-closed とする。
  - active step を解決した直後、dry-run 計画の構築・表示より前に検査し、最初の Copilot Agent session 作成、モデル呼び出し、branch 作成および DAG 実行より前に完了しなければならない。`--dry-run` も設定充足性の確認手段として同じ検査を行う。
  - CLI / GUI は、Workflow と active step から対象を決める処理、および repo / token / branch / remote を検査する処理を 1 つの共通関数へ集約し、各起動面へ条件判定を複製してはならない（FR-MAINT-07）。同関数は呼び出し側が指定する `check_remote` に応じてローカル判定だけ、または remote 判定を含む結果を返す。GUI Step 1 precheck はネットワーク待ちを UI thread へ持ち込まないよう `check_remote=False` の結果を表示し、remote branch の実在確認は GUI が起動する `hve orchestrate` 子プロセスが同じ関数を `check_remote=True` で呼び出して担う。
  - `additional_prompt`、`workiq_prompt_qa`、`workiq_prompt_km`、`workiq_prompt_review` その他の Prompt 自由記述欄は内容検査の対象外とする。既存の型変換・引数伝搬は維持するが、自然言語の妥当性、空欄可否、業務内容を本 preflight で判定してはならない。
  - 既存の argparse / Qt validator による型・列挙値検証、FR-DAG-08 の active step 必須パラメータ検査、および各認証 preflight は維持する。これらを再実装する包括的 validation framework、新規 CLI オプション、新規永続設定、新規依存を追加してはならない。
  - 根拠は、GUI の保存済み `base_branch` に remote / local のいずれにも存在しない値が残り、`git fetch` 失敗後のローカル fallback も失敗して Workflow が停止した実測である。設定不備は Agent session 作成前に判定可能であり、モデル実行後まで遅延させる理由がない。

### 5.15 PR 用作業ブランチの選択

- **FR-CLI-83**: `--create-issues` / `--create-pr` による workflow-wide PR 作成では、利用者は PR 用の新規作業ブランチを作るか、現在 checkout 中のブランチを使うかを `create_working_branch` で選択できなければならない。CLI は `--create-working-branch` / `--no-create-working-branch`、GUI は同じ設定キーを使用し、既定は新規作成（`True`）とする。
  - `True` のときは従来どおり、選択した remote base branch から `copilot-sdk/<prefix>-<8hex>` を 1 本作成して checkout し、当該 run の commit / push / PR にだけ使用する。1 task で複数の workflow-wide branch または PR を作成してはならない。
  - `False` のときは checkout を行わず、現在の branch を head として使用する。開始時に detached HEAD でないこと、base branch と異なること、worktree と index が clean であることを検証する。`origin/<current>` が存在する場合は local HEAD と同じ commit でなければならず、存在しない場合は最終 push で新規作成してよい。不一致を stash / reset / pull / force-push で自動補正してはならない。
  - 上記 current branch 検査は FR-CLI-82 の共通 startup preflight に集約し、dry-run 計画・branch 作成・最初の Agent session より前に fail-closed で全不整合を報告する。GUI thread では remote 照会を行わない。
  - HVE が新規作成した branch だけを FR-CLI-34 の自動 local cleanup 対象とする。利用者が選択した current branch は、PR が merged でも自動削除してはならない。`enable_auto_merge` の既定 OFF と GitHub の review / status check 境界は変更しない。
  - `enable_auto_merge` 単独で Step-scoped branch を作る ASDW-WEB、および既存の workflow-wide branch を必要とする ADFDV の挙動は本設定で無効化してはならない。これらは remote CI/CD の実行契約であり、任意の PR 作成オプションとは別である。

### 5.16 進捗保存による再実行

本節は §5.6 が廃止した HVE 所有の `state.json` / `config_snapshot` 復元を復活させない。標準再開は FR-STATE-04/05 の durable execution を用い、旧 JSONL は明示的な legacy 経路だけで読む。

- **FR-CLI-86**: `orchestrate --resume-run <run-id>` は `hve/.run-progress.jsonl` の既存記録だけを読む legacy 互換入口として維持し、当該 run と Workflow の `succeeded` な Step を実行対象から除外しなければならない。新しい `execution_id` をこの引数へ渡してはならず、SQLite execution の候補列挙・import・意味の多重解釈を行ってはならない。
  - 指定された run-id の記録が 1 件も無い場合は fail-closed で停止する。誤った run-id を無視して全 Step を再実行してはならない。利用者が完了済みと誤認したまま全体を再実行し、既にデプロイ済みの資源へ重複操作を行う事故を防ぐためである。
  - legacy reader は run-id と Workflow ID の両方で絞り込み、別 Workflow の同じ Step ID を成功扱いしてはならない。
  - 除外は active step の絞り込みとして行い、DAG の依存関係（FR-DAG-01）を変更してはならない。
  - fan-out Step は展開後の子 ID（`{base_id}/{key}`）で記録される一方、本項の除外は展開前の active step（base ID）へ適用するため、**fan-out Step は成功済みでも再実行される**。除外を fan-out 展開後へ移すと、完了済み Step の `required_params`（FR-DAG-08）が未指定であるだけで再実行全体が `blocked` となるため、取りこぼしではなく重複実行の側へ倒している。
  - 新規の環境変数を追加してはならない。
  - 契約テスト: [hve/tests/test_run_progress.py](hve/tests/test_run_progress.py)
- **FR-CLI-90**: 標準ローカル再開の公開入口は `hve resume [<execution-id>]` とし、current repository の FR-STATE-04 execution を共通 ResumeService から選択・計画・実行しなければならない。
  - candidate 0 件は非 0、1 件は内容を表示して確認後に開始、複数件は TTY menu で選択する。non-TTY で候補を暗黙選択してはならない。`--latest` または execution ID の明示指定を受理し、両者の同時指定は拒否する。
  - non-terminal/failed/risk ありの instance は `reuse-session` / `restart-step` / cancel の明示 action を要求する。Main phase だけ `reuse-session` または `restart-step` を許可し、Pre-QA/Review/Self-Improve その他の phase は `restart-step` だけを許可する。non-TTY で action 不足の場合は child・SDK・model を開始してはならない。
  - `reuse-session` は保存済み session IDを SDK call 前に commit 済みであることを確認し、`resume_session(..., continue_pending_work=False)` を使用して固定 recovery promptを新しい turn として送る。`continue_pending_work=True` を使用してはならない。`session.resume` が active/in-use を報告した場合は disconnect して停止する。失敗時に `restart-step`へ silent fallbackしてはならない。
  - status だけを更新する DAG callback が `phase` / `phase_state` / `session_id` を省略しても、commit 済みの Main checkpoint metadata を消去してはならない。legacy split-fork が無効な標準経路では `split-fork` phase を checkpoint として記録せず、明示的に有効なときだけ記録する。
  - `restart-step` は新しい run ID/session ID で対象 Step を先頭から実行する。いずれの action も外部副作用の exactly-once を保証すると表示してはならない。
  - `launch_plan_hash` は execution ID を含めない sanitized ordered plan、`resume_plan_hash` は execution ID、instance status/state version、選択 action、current HEAD、再入力値の hash から計算する。後者は保存せず、plan 承認後に同じ入力で再計算し、expected state version の lease CAS と併用する。
  - current HEAD を取得できない場合は、plan 構築・lease 取得・child 起動の前に fail-closed で停止する。承認後かつlease取得前にもHEADを再取得し、承認済みplanの値から変化していればstaleとして停止する。`None` や固定値 `unknown` を hash 入力へ代入して続行してはならない。
  - GUI/Prompt controllerが既に提示したplanを非対話で実行する場合だけ、help非表示の`--expected-resume-hash`と`--replay-value <key>=<value>`をHVE childへ渡してよい。CLIは同じplanを再構築し、hash不一致・未知key・不足値ではlease/childを開始してはならない。これらの値を利用者へ入力させてはならない。
  - ordered multi-Workflow execution は最初の non-succeeded instance から ordinal 順に進み、最初の failed/blocked/suspended で停止する。後続を先行実行せず、成功済み instance を取り消さない。instance 完了後に次の `ResumePlan` を構築した場合、その plan は新しい instance ID・state version・hashを持つ別の承認対象とする。TTY では次のplanを再提示して再確認し、`--expected-resume-hash`を渡した非対話controllerでは最初の承認済みplanだけを実行して停止し、次のhashを再提示・再承認されるまで次のlease/childを開始してはならない。先行planのhashを後続planへ流用してはならない。先行planへ再入力した平文値もinstance完了時に破棄し、後続planへ渡してはならない。後続planが同じkeyを必要とする場合も改めて再入力・再承認する。
  - TTY と `--expected-resume-hash` controller では、先行 instance の recovery action も後続 `ResumePlan` へ流用してはならない。後続 plan に risk があれば action を改めて選択し、plan hash の再計算後に承認する。
  - output再調停の結果、選択済みStepがすべて成功済みで必須outputも存在し、実行すべきStepが0件になった場合は、空のargvでsubcommandなしchildを起動してはならない。承認済みplanのexpected state versionでfenced leaseを取得し、同じResumeService境界でoutputを再確認して当該instanceを`succeeded`へ確定した後、ordered規則に従って次へ進む。
  - direct `orchestrate` と対話 `run` / `cli` は config/params 解決後かつ最初の外部 auth/model session 前に single-instance execution を登録する。`dry_run`、Autopilot、Fleet、Cloud Session、GitHub Cloud Agent は初期版で登録せず、新規実行の既存挙動を変えない。対象外 execution の resume 要求だけを理由付き非 0 とする。
  - HVE 本体・既知 child 間の identity 伝搬は `OrchestratorContext` の `execution_id` / `instance_id` / `expected_state_version` / `recovery_action` / `lease_owner` / `lease_generation` と argparse help 非表示の internal argsだけを用い、新しい global environment variable を追加してはならない。
  - 契約テスト: [hve/tests/test_resume_cli.py](hve/tests/test_resume_cli.py)、[hve/tests/test_resume_service.py](hve/tests/test_resume_service.py)、[hve/tests/test_runner_resume.py](hve/tests/test_runner_resume.py)、[hve/tests/test_run_state_store.py](hve/tests/test_run_state_store.py)

### 5.17 Wave 境界の承認ゲート

- **FR-CLI-87**: `orchestrate` は `--approval-gates` を受け取り、有効なときに限り、`StepDef.approval_gate` を宣言した Step を含む Wave の実行開始前に利用者へ承認を求めなければならない。既定は無効とし、無効時は一切の確認を出してはならない。
  - 承認は同期とする。標準入力が対話可能でない実行（非対話 CLI、GUI が起動する子プロセス〈FR-GUI-23〉、Cloud）では確認を出さず、当該 run を `blocked` として停止しなければならない。無人実行を承認なしで続行させないためである。
  - 拒否および非対話での停止は、`run_workflow` の戻り値へ `blocked` と `error` を設定して返さなければならない。独自のキー集合で返してはならない（終了コード判定が `blocked` / `error` / `failed` を参照するため）。
  - 承認要求は既存の `on_wave_start` フック経由で行い、[hve/dag_executor.py](hve/dag_executor.py) へ新規のフックを追加してはならない（FR-MAINT-07）。同フックの汎用例外握り潰しからは承認拒否の例外だけを除外する。
  - 承認・拒否の記録は FR-STATE-04 の進捗ストアへ `approval:<wave_index>` を step_id として残し、承認者名・自由記述・prompt 本文を保存してはならない（NFR-SEC-01 / FR-RTO-04）。
  - **GUI からの承認は本項の対象外とする**。FR-GUI-23 が GUI の子プロセスの標準入力を対話不能と定めているため、同期の標準入力プロンプトは成立しない。GUI で承認を行うには FR-QA-03 の `qa_answer_mode="gui-file"` と同種の IPC 経路が必要であり、別要件として扱う。
  - 新規の環境変数を追加してはならない。
  - 契約テスト: [hve/tests/test_approval_gate.py](hve/tests/test_approval_gate.py)

### 5.18 PR / Issue の参照経路

- **FR-CLI-88**: Pull Request および Issue（障害記録を含む）を Agent セッションから参照する場合、その経路は [.github/.mcp.json](.github/.mcp.json) への MCP サーバ宣言としなければならない。`mdq` の索引ルート（FR-MDQ-02）と `cq` の索引対象（FR-CQ-01）を拡張してはならない。両者はワークツリー上のファイルだけを索引する契約であり、GitHub API 上のデータは対象外だからである。
  - 宣言が必要なのは、FR-CLI-76 が `enable_config_discovery=False` を指定してワークスペース / ユーザースコープ / **プラグイン由来**の MCP サーバを自動探索から除外しているためである。利用者が GitHub Copilot CLI 側へプラグインとして登録しただけでは Step 実行セッションへ届かない。
  - GitHub の MCP サーバを宣言する場合、`tools` は**参照系だけを列挙**しなければならない。`tools: ["*"]` を用いてはならず、作成・更新・削除・マージ・クローズ・push・ラベル付与等の状態変更ツールを含めてはならない。`FR-QA-03` が Work IQ で問題視した「`tools: ["*"]` により最小権限 allowlist が及ばない」状態を再現しないためである。
  - 具体的なサーバー定義（`command` / `url` / tool 名）は利用者環境と GitHub の提供形態に依存するため本書では確定しない。宣言した時点で上記 allowlist を満たすことを機械検査する。
  - 契約テスト: [hve/tests/test_mcp_declaration_contract.py](hve/tests/test_mcp_declaration_contract.py)

### 5.19 Copilot cloud agent への Issue 割当

- **FR-CLI-89**: `orchestrate` は `--assign-copilot-agent` を受け取り、`--create-issues` で当該 run が新規作成した Root Issue を Copilot cloud agent へ割り当てられなければならない。既定は無効とする。
  - `--create-issues` を伴わない指定は警告して無視し、既存 Issue、Pull Request、または利用者が指定していない Issue を暗黙に割り当ててはならない。
  - 割当は [hve/github_api.py](hve/github_api.py) の FR-GUI-49 と同じ REST 実装へ委譲し、`assignees: ["copilot-swe-agent[bot]"]` と `agent_assignment.target_repo` を送る。`base_branch` が空または未指定のときは `agent_assignment` へ含めてはならない。
  - 割当に失敗した場合は run を継続せず fail-closed とする。Issue 作成済みであることと割当失敗を区別して報告し、同じ Root Issue を再作成してはならない。
  - public preview の Agent Tasks API（`POST /agents/repos/{owner}/{repo}/tasks`）は使用しない。既存の Issue / Sub-Issue / PR ライフサイクルを迂回しないためである。
  - 新規の環境変数を追加してはならない。

### 5.20 Prompt 版（自然言語 Prompt からの計画と実行）

本節は HVE の Cloud 版 / GUI 版 / CLI 版に並ぶ **第 4 の利用面**（Prompt 版）を規定する。Prompt 版は新しい Workflow 実行エンジンではない。自然言語を型付き request へ変換する repository Agent Skill と、request を決定的に検証・計画して既存 `orchestrate` へ委譲する薄い CLI 境界だけで構成する。

- **FR-PROMPT-01**: Prompt 版は既存の実行核（`run_workflow` / `DAGExecutor` / `StepRunner`）を再実装してはならない。実行は `orchestrate` サブコマンドの子プロセス起動だけを経路とし、Workflow / Step / 依存 / 入出力契約の正本は [hve/workflow_registry.py](hve/workflow_registry.py) と [.github/io-contracts/](.github/io-contracts/) のままとする。
  - 対象面は GUI 内の既存 Copilot CLI タブ、standalone GitHub Copilot CLI、VS Code / GitHub Copilot app のローカル 3 面とする。GitHub.com / Cloud Agent Orchestrator からの Prompt request 実行は本版の対象外とし、対応済みと記載してはならない。
  - 新しい GUI タブ・GUI ウィジェット・Prompt エディタを追加してはならない。
  - 契約テスト: [hve/tests/test_prompt_execution.py](hve/tests/test_prompt_execution.py)

- **FR-PROMPT-02**: Prompt 版の入力は UTF-8 JSON の **request v1** とし、HVE Python はその内容を信用せず、schema・registry・allowlist で再検証しなければならない。HVE Python 内へ自然言語を解釈する新しい parser を追加してはならない。
  - `schema_version` は整数 `1` のみ受理する。未知の major、未知の field、重複 key、空の `workflows`、同一 Workflow の重複指定、非文字列 path は fail-closed で拒否する。
  - `workflow_id` は [hve/workflow_registry.py](hve/workflow_registry.py) の canonical ID へ解決できるものだけを受理し、解決結果を計画へ明示する。`steps` は当該 Workflow に実在する Step ID だけを受理する。
  - `params` / `settings_overrides` は本書が固定する allowlist の key だけを受理する。`settings_overrides` の allowlist は FR-LOCAL-SURFACE-01 (a) の shared setting 集合とし、`params` は当該 Workflow の `WorkflowDef.params` が宣言した key に限る。token・password・任意の環境変数・任意のコマンド・任意のファイルパス実行を受理してはならない。
  - `goal` は既存 `--additional-prompt` へ渡す文字列であり、shell として解釈してはならない。
  - `dry_run` / plan hash / 実行順 / `--workbench off` は Prompt CLI が所有し、request から上書きさせてはならない。
  - 契約テスト: [hve/tests/test_prompt_request.py](hve/tests/test_prompt_request.py)

- **FR-PROMPT-03**: `hve prompt plan --request <path>` は、成果物（`docs/` / `src/` / `knowledge/` / `qa/` 等）を一切生成・変更せずに実行計画を提示しなければならない。
  - 検証済み request と保存済み GUI 設定から各 Workflow の argv を構築し、Workflow ごとに `orchestrate --dry-run` を argv 配列で順に実行する。いずれかが非 0 で終了した場合は計画を提示せず、その終了コードを伝播する。
  - `orchestrate --dry-run` 自体の既存の副作用（run ディレクトリ `work/run/<run-id>/` の作成、mdq / cq の索引更新）は本版では変更しない。「一切書き込まない」と記載してはならない。
  - `--dry-run` は実行計画を表示するだけであり、上流成果物の不足を検出して非 0 で終了する契約を持たない。利用者文書でもこれを前提にしてはならない。
  - 提示内容は Workflow の実行順、入力別名の解決結果、各 Workflow の argv、および計画の SHA-256 とする。
  - 計画の提示文と失敗時のメッセージは、利用者へコマンド・request path・SHA-256 の入力を求めてはならない。承認は自然言語で受け取り、`--expected-sha256` への転記は Agent が行う前提で記述する。
  - 契約テスト: [hve/tests/test_prompt_cli.py](hve/tests/test_prompt_cli.py)

- **FR-PROMPT-04**: `hve prompt run --request <path> --expected-sha256 <64 桁 hex>` は、計画を同じ規則で再構築し、SHA-256 が一致した場合だけ実行しなければならない。
  - `--expected-sha256` の欠落・書式不正・不一致では **`orchestrate` 子プロセスを 1 つも起動してはならない**。HEAD 取得のための `git rev-parse` はこの禁止対象ではない。自然言語上の「承認」だけで書き込みを開始してはならない。
  - 実行は `sys.executable -m hve ...` の argv 配列かつ `shell=False` とし、Prompt 本文をコマンド文字列として評価してはならない。
  - 複数 Workflow は fail-fast とする。ある Workflow が非 0 で終了した場合、後続 Workflow を起動してはならない。成功済み Workflow を取り消す振る舞い（rollback）を主張してはならない。
  - child runner の結果は bool ではない整数 `returncode` を必須とする。process 起動例外、結果 object 欠落、不正な returncode を成功へ丸めてはならない。
  - 承認記録の永続化・署名・期限・分散ロックは本版では実装しない。
  - 契約テスト: [hve/tests/test_prompt_cli.py](hve/tests/test_prompt_cli.py)

- **FR-PROMPT-05**: 計画の SHA-256 は、版付き canonical JSON に対して計算しなければならない。対象は schema version、canonical Workflow ID と安定ソート済みの実行順、各 Workflow の最終 argv 配列（表示用 shell 文字列ではない）、正規化済み入力別名、およびリポジトリの HEAD commit とする。
  - canonical JSON は key ソート、compact separator、UTF-8、LF、リポジトリ相対の `/` 区切りパスで正規化する。保存済み設定・request・HEAD のいずれかが計画内容を変えれば hash も変わらなければならない。
  - HEAD commit を取得できない場合は固定値 `unknown` を hash へ代入して続行せず、`orchestrate` 子プロセスを起動する前に fail-closed で停止しなければならない。
  - 承認済みplanを実行する直前とdurable登録後の最初のchild起動直前にHEADを再取得し、planへ含めたcommitから変化していればchildを起動せずstaleとして停止しなければならない。先行child自身が生成したcommitを理由に後続childを拒否してはならないため、この再照合は最初のchildに限定する。
  - 契約テスト: [hve/tests/test_prompt_execution.py](hve/tests/test_prompt_execution.py)

- **FR-PROMPT-06**: 複数 Workflow の実行順は `get_meta_dependencies()`（FR-COMMON-01）に基づく安定ソートで決定しなければならない。選択されていない依存 Workflow を暗黙に追加してはならず、利用者定義の任意 DAG を受理してはならない。循環を検出した場合は実行前に停止する。
  - 順序決定は GUI と Prompt 版で同一実装を共有しなければならない（FR-MAINT-07）。実装を複製して 2 つの実行面へ drift を持ち込んではならない。
  - 契約テスト: [hve/tests/test_workflow_order.py](hve/tests/test_workflow_order.py)

- **FR-PROMPT-07**: Prompt 版は保存済み GUI 設定（[hve/gui/settings_store.py](hve/gui/settings_store.py) `load()`）を基準値として `OrchestrateArgs` を構築しなければならない。構築は Qt ウィジェットを起動しない純粋関数とし、PySide6 未導入環境でも import・実行できなければならない。
  - 3 状態（`""` / `"on"` / `"off"`）、bool、リスト、Workflow 固有値の解釈は現行 GUI と同一でなければならない。
  - FR-LOCAL-SURFACE-01 (a) の shared setting は、GUI が保存したすべての key について本経路で `OrchestrateArgs` へ反映しなければならない。保存 key 名と `OrchestrateArgs` のフィールド名が異なる場合は明示的に対応付け、無言で捨ててはならない。
  - request の `settings_overrides` は allowlist の key だけを上書きできる。
  - 契約テスト: [hve/gui/tests/test_orchestrate_args_from_settings.py](hve/gui/tests/test_orchestrate_args_from_settings.py)

- **FR-PROMPT-08**: 非 canonical なファイル名の入力は、**実行時の入力別名（canonical → actual）** として扱わなければならない。ファイルのコピー、canonical path への複製、per-Step I/O 契約（[.github/io-contracts/](.github/io-contracts/)）や `StepDef.output_paths` の実行時書き換えを行ってはならない。
  - `canonical` は選択された active Step の `required_input_paths` に**リテラルで**含まれるものだけを受理する。v1 では glob、`{key}` 等の placeholder、ディレクトリ入力の別名化を拒否する。
  - `actual` はリポジトリ内に存在する通常ファイルだけを受理する。絶対パス、`..` によるリポジトリ外への脱出、symlink / junction / reparse point を拒否する。
  - 同一 canonical への重複・競合指定を拒否する。選択された上流 Step が生成する canonical output の差し替えを拒否する。
  - v1 が対応しない形式は actionable なエラーで停止し、silent fallback してはならない。
  - 契約テスト: [hve/tests/test_input_aliases.py](hve/tests/test_input_aliases.py)

- **FR-PROMPT-09**: 入力別名は、root Step の前提成果物判定（FR-DAG-06）、meta 依存の artifact pattern 判定、Step Prompt、および Fleet task の必須入力表示へ、**単一の解決器**を通して同じ結果で適用しなければならない。
  - 別名を一部の判定にだけ適用して前提ゲートを迂回させてはならない。未知・不正な別名は Agent セッション開始前に fail-closed で停止する。
  - fail-closed の適用範囲は Prompt 版の経路だけでなく、`orchestrate --input-alias` を直接使う CLI / GUI 経路を含む。検証を省くと repo 外のパスが Step Prompt へ注入される。
  - Agent へ渡すのは解決後の path だけとし、対象ファイルの本文を Prompt へ埋め込んではならない（NFR-CTX-01）。
  - 別名に関係しない Step の Prompt と、全 Step の canonical output は変化してはならない。
  - 契約テスト: [hve/tests/test_prompt_input_alias_integration.py](hve/tests/test_prompt_input_alias_integration.py)、[hve/tests/test_prompt_cli.py](hve/tests/test_prompt_cli.py)

- **FR-PROMPT-10**: 自然言語から request v1 への変換手順は repository Agent Skill として提供し、HVE Python 側へ持ち込んではならない。Skill は不明な Workflow / Step / field を推測で補完せず、曖昧なときは実行せずに質問しなければならない。
  - 利用者文書（[users-guide/hve-prompt-getting-started.md](users-guide/hve-prompt-getting-started.md) と [users-guide/prompts/](users-guide/prompts/)）は、[hve/workflow_registry.py](hve/workflow_registry.py) が定義する全 Workflow について、Product Manager がコピーできる Markdown Prompt 例を最低 1 件ずつ持たなければならない。複数 Workflow 横断の例と、非 canonical 入力名の例を含める。
  - 各例は「plan を先に提示し、明示承認前に run しない」ことを明記しなければならない。
  - 利用者は自然言語だけで計画取得から実行までを完了できなければならない。`hve prompt plan` / `hve prompt run` の起動、request path の受け渡し、plan SHA-256 の転記はすべて Agent が代行し、Skill も利用者文書もこれらの入力を利用者へ求めてはならない。貼り付け用 Prompt 例の本文へ CLI サブコマンド名を含めてはならない。
  - 承認は自然言語で受け取る。Skill は承認語の網羅列挙を持たず、明確な実行意思だけを承認とみなし、曖昧な同意は承認とせず再確認する。ただし FR-PROMPT-04 の `--expected-sha256` 一致ゲートを緩和してはならない。
  - Prompt 版の承認前に提示する実行計画と、承認後に各 Step が必要に応じて作成する `plan.md` は別の計画層として扱う。前者を提示して利用者の明示承認を得るまでは `hve prompt run` を起動してはならない。提示済み計画への明示承認を得た後、Prompt Edition controller は提示された SHA-256 を `--expected-sha256` へ渡して `hve prompt run` を起動する。HVE が現在の request・設定・HEAD から再計算した SHA-256 との一致を確認した場合だけ、既存 `orchestrate` へ委譲する。controller が単独実行モードであっても、`task_scope=multi` または `context_size=large` を理由にこの委譲を禁止してはならない。この例外が許可するのは既存 `orchestrate` への委譲だけであり、controller が対象成果物を直接実装・編集してはならない。
  - 委譲は FR-PROMPT-01 の既存子プロセス経路を用い、直接 `orchestrate` を起動した場合と同じ argv と制約を適用する。FR-DAG-06 / FR-DAG-08 の事前検査、FR-CLI-87 の Wave 承認、および FR-WF-OUT-01 の成果物ゲートを Prompt 版専用の分岐で省略してはならない。各 Step は必要な `plan.md` を作成してよいが、`plan.md` / `subissues.md` だけで終了せず、選択済み Step の宣言 `output_paths` を実行完了時点で存在させなければならない。FR-WF-OUT-01 は存在ゲートであり、実行前から存在した成果物が今回更新されたことまでは証明しない。完全実行の範囲は選択済み Workflow / Step の成功または最初の失敗までとし、未選択 Workflow の暗黙追加、rollback、失敗後の継続を含めてはならない。Prompt 版の承認を、既存の認証・権限・Azure・QA・デプロイ承認ゲートの代替として扱ってはならない。
  - 利用者文書に Prompt 件数などの変動値を固定記述してはならない。正本または確認方法へ誘導する。
  - 契約テスト: [hve/tests/test_prompt_edition_docs_contract.py](hve/tests/test_prompt_edition_docs_contract.py)
- **FR-PROMPT-11**: Prompt 版の durable resume は request v1 を変更せず、repository Agent Skill が FR-CLI-90 の共通 resume plan を取得・提示・承認後実行する controller として提供しなければならない。
  - Skill は利用者の自然言語から execution/action/replay不足値だけを解決し、Python 側へ自然言語 parser を追加してはならない。利用者へ command、request path、execution hash の転記を求めてはならない。
  - 承認前は実行せず、提示済み `resume_plan_hash` と再計算値が一致し、expected state version の lease CAS が成功した場合だけ既存 `orchestrate` child 経路へ委譲する。stale の場合は child を起動せずplanを再提示し、再承認を求める。
  - normal Prompt run は既存 SHA-256 approval 合格後かつ最初の child 前に全 Workflow instance を 1 transaction で登録し、全 childへ同じ execution IDと各instance IDを internal argsで渡す。既存fail-fastとrequest v1 schemaを変更しない。
  - normal Prompt run は child の終了コード 0 だけで成功を推測せず、対応する durable Workflow instance が `succeeded` または `skipped` へ commit 済みであることを確認してから後続 child へ進む。状態欠落・非終端状態・read failure は非 0 で停止する。
  - 契約テスト: [hve/tests/test_prompt_resume_contract.py](hve/tests/test_prompt_resume_contract.py)、[hve/tests/test_prompt_execution.py](hve/tests/test_prompt_execution.py)

### 5.21 ローカル 3 面の設定パリティ

本節は、直接 `orchestrate` CLI・GUI Orchestrator・Prompt 版（§5.20）の 3 つの**ローカル**利用面に対して、利用者が指定できる設定の同一性を規定する。Cloud Agent Orchestrator は Issue Form を入口とする別経路であり、本節の対象に含めない（Cloud との対応は FR-CLOUD-10 / FR-CLOUD-11 と `hve/tests/fixtures/option_parity_matrix.yaml` が扱う）。

- **FR-LOCAL-SURFACE-01**: ローカル 3 面のパリティは「同じ利用者意図が、同じ正規化済み値として `orchestrate` へ到達すること」と定義する。CLI フラグ名の字面一致を求めてはならない。各設定は次の 5 分類のいずれか 1 つに属し、分類ごとに以下の契約を満たさなければならない。
  - **(a) shared setting**: 3 面すべてで指定できる。GUI は [hve/gui/settings_store.py](hve/gui/settings_store.py) `defaults()` へ既定値を持ち、[hve/gui/settings_apply.py](hve/gui/settings_apply.py) `_SECTION_FIELDS` で widget と対応付けて永続化する。Prompt 版は保存値を基準値とし（FR-PROMPT-07）、`ALLOWED_SETTINGS_OVERRIDES` の key として run 単位で上書きできる。CLI は同義のフラグを持つ。対象は次の 26 key とし、`ALLOWED_SETTINGS_OVERRIDES` と過不足なく一致しなければならない（FR-PROMPT-02）。
    - 実行品質: `model` / `review_model` / `qa_model` / `akm_model` / `reasoning_effort` / `review_reasoning_effort` / `qa_reasoning_effort` / `akm_reasoning_effort` / `context_tier` / `akm_context_tier`
    - 実行制御: `max_parallel` / `timeout` / `review_timeout` / `auto_qa` / `auto_contents_review` / `verbosity` / `branch` / `strict`
    - Agentic Retrieval / Toolbox: `enable_agentic_retrieval` / `agentic_data_source_modes` / `foundry_mcp_integration` / `agentic_data_sources_hint` / `agentic_existing_design_diff_only` / `foundry_sku_fallback_policy` / `enable_tool_search`
    - Cloud Session: `cloud_session_branch`（保存 key は `cloud_session_repository_branch`）
  - shared setting の集合は 1 箇所で定義し、面ごとに別集合を持ってはならない。一致は機械検査しなければならない。
  - 同一 Workflow と、両面で表現可能な同一の保存済み設定を入力し、Prompt request の run 単位上書き・Step・goal・入力別名、および GUI セッション固有値（QA / Steering IPC、Hub の Issue 関連付け、Cloud Session の Step 単位上書き、Autopilot の APP lane）を指定しない場合、GUI は `settings_apply.apply_to_widgets()` 後の `OptionsPage.build_args_for_workflow()`、Prompt 版は `args_from_settings()` からそれぞれ `OrchestrateArgs.to_argv()` へ到達し、生成する argv 配列の要素数・順序・値が完全一致しなければならない。GUI 専用の `qa_answer_mode=user` は比較対象外とする。実効値が同じであっても、面ごとに不要な既定値フラグを追加・省略して差分を残してはならない。
  - **(b) workflow param**: [hve/workflow_registry.py](hve/workflow_registry.py) の `WorkflowDef.params` が宣言した Workflow 固有値。CLI フラグ、Prompt request の `workflows[].params`、および当該 Workflow を選択した GUI 画面から指定できなければならない。値は宣言した Workflow にだけ適用し、GUI の全体設定へ永続化してはならない。対象は `create_remote_mcp_server` / `tdd_max_retries` とする。
  - **(c) semantic alias**: 同じ実行状態へ到達する別表現を持つもの。面ごとに入口が異なってよいが、解決後の実行状態は一致しなければならない。`include_kpi_okr` は FR-PARAM-10 に従い Step 選択を唯一の推奨状態とし、CLI `--include-kpi-okr` と Prompt の `params` は後方互換の入口として維持する。GUI へ重複する可視状態を追加してはならない。
  - **(d) derived**: 他の設定から一意に導出する値。重複入力欄を設けてはならない。Cloud Session の repository owner / name は `repo`（`owner/repo`）から導出する。
  - **(e) excluded**: 意図的に面固有とするもの。除外は根拠となる要件または実装上の制約を伴わなければならない。Workbench 表示系（GUI / Prompt は `--workbench off` を強制注入する）、GUI 固有 IPC（`qa_ipc_dir` / `steering_ipc_dir`）、対話専用（`force_interactive`、および FR-CLI-87 の `--approval-gates`）、GUI 入力欄を禁止した ASDW-WEB Step 1.3 の `data_*`（FR-WF-ASDW-02 / FR-GUI-02）、Autopilot チェーン、`_OBSOLETE_KEYS` 登録済みの旧 GUI 設定、およびコンソール出力の表示制御（`--verbose` / `--quiet` / `--show-stream` / `--log-level` / `--no-color` / `--banner` / `--screen-reader` / `--timestamp-style`）を除外とする。入力別名（`input_aliases`）は FR-PROMPT-08 の非 canonical 入力を request で扱う Prompt 版と直接 CLI の実行時機能であり、GUI へ重複する入力欄を追加しない。ただし `OrchestrateArgs` と `to_argv()` の既存受け口は維持する。コンソール出力の表示制御は `OrchestrateArgs` に存在するが GUI 設定ストアへ永続化しておらず、実行結果の意味論を変えないため、本節では面固有のままとする。
  - 優先順位は、shared setting が「Prompt `settings_overrides` > 保存済み GUI 設定 > 既定値」、workflow param が「明示指定 > 既定値」とする。`tdd_max_retries` は既存の環境変数経路を維持し「CLI 明示 > `HVE_TDD_MAX_RETRIES` > 5」とする。本節のために新しい環境変数を追加してはならない。
  - shared setting と workflow param の解決には、新しい設定レジストリ・シリアライザ・抽象レイヤーを導入してはならない。既存の [hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py) `OrchestrateArgs` を CLI argv への唯一の変換器として再利用する（FR-MAINT-07）。
  - 分類の網羅性は機械検査しなければならない。`orchestrate` の全 CLI 引数は `OrchestrateArgs` のフィールド、明示した別名、または理由付きの除外リストのいずれかへ分類されていなければならず、未分類が残ってはならない。
  - 契約テスト: [hve/tests/test_local_surface_option_parity.py](hve/tests/test_local_surface_option_parity.py)
- **FR-LOCAL-SURFACE-02**: CLI / GUI Plan / Prompt の durable resume は、candidate・risk reason・許可 action・missing replay keys・resume plan hash・lease CAS・ordered execution を同じ ResumeService から取得しなければならない。
  - GUI と Prompt は独自の candidate scan、risk判定、output gate、lease判定を実装してはならない。表示・入力・child launchだけを面固有責務とする。
  - GUI Plan は Start 操作ごとに queue 全体を 1 executionとして登録し、全 childへ同じ execution IDを渡す。新しい Resume dialog は execution ID、Workflow、last state、heartbeat、risk、missing replay keysを表示し、safe executionは1回の確認、riskありはaction選択後に開始する。
  - GUIの承認後実行はdialogが選択したplan hashと再入力値を`hve resume` childへ渡し、同childが再計算・CAS・fenced token付き`orchestrate`起動を行う。GUIが承認済み`ResumePlan.argv`を直接`orchestrate`として起動し、hash再検証またはlease取得を迂回してはならない。
  - Prompt は FR-PROMPT-11、CLIは FR-CLI-90 に従う。3面で同じsnapshotを入力したとき、正規化済みplanの意味とhashが一致しなければならない。
  - 契約テスト: [hve/tests/test_resume_surface_parity.py](hve/tests/test_resume_surface_parity.py)

---

## 6. パラメータ仕様（抜粋）

### 6.1 AKM の `sources` 正規化

- **FR-PARAM-01**: 受理形式は文字列（カンマ / 空白区切り）または `list`/`tuple`/`set`。トークンは `qa` / `original-docs` / `workiq` / `both`（後方互換 → `qa,original-docs`）。
- **FR-PARAM-02**: 不明トークンは例外を出さず無視する（[hve/orchestrator.py](hve/orchestrator.py) `_normalize_akm_sources`）。
  - **運用上のリスク**: **警告も発出されないため、誤入力時に利用者が気づきにくい**。
  - 結果順序は固定 `[workiq, qa, original-docs]` のうち含まれるものを並べる。
- **FR-PARAM-03**: 空入力 / `None` の既定値は `["qa", "original-docs"]`。
- **FR-PARAM-04**: `target_files` の既定値は、非 workiq ソースが `qa` 単独なら `qa/*.md`、`original-docs` 単独なら `docs-original/*`、それ以外（複数または workiq のみ）は空文字列。

### 6.2 ARD のステップ選択ロジック

- **FR-PARAM-10**: CLI 非対話モードで `--steps` / `selected_steps` が未指定の場合、`target_business` の有無にかかわらず FR-WF-ARD-03 の `ARD_DEFAULT_GROUP_IDS`（`("2", "3", "4", "5")`）を既定の `selected_steps` とする（[hve/orchestrator.py](hve/orchestrator.py) `_collect_params_non_interactive`）。起動面ごとに別の既定値を持ってはならない。グループ `3` または実 Step `2.1` が明示選択された場合は `include_kpi_okr=True` と同じ実行状態へ正規化し、直接 CLI の `--include-kpi-okr` は後方互換ショートカットとして維持する。
- **FR-PARAM-11**: 既定値:
  - `survey_base_date` = 実行日（`date.today().isoformat()`）
  - `survey_period_years` = `30`
  - `target_region` = `グローバル全体`
  - `analysis_purpose` = `中長期成長戦略の立案`

### 6.3 APP-ID 自動選択

- **FR-PARAM-20**: `aad-web` / `asdw-web` で APP-ID 未指定時、`docs/catalog/app-arch-catalog.md` から「Webフロントエンド + クラウド」アーキテクチャに合致する APP-ID を自動選択する。
- **FR-PARAM-21**: `abd` / `abdv` では「データバッチ処理 / バッチ」アーキテクチャに合致する APP-ID を自動選択する（[hve/app_arch_filter.py](hve/app_arch_filter.py) `resolve_app_arch_scope`）。

### 6.4 GUI Orchestrator の必須入力事前検証（Precheck）

- **FR-GUI-01**: GUI の Step 1 統合 precheck（[hve/autopilot/precheck_runner.py](hve/autopilot/precheck_runner.py) `run_step1_precheck`）は、選択中ワークフローの active step を次の 2 系統で評価する。
  - **ファイル要件**（`REQUIREMENT_TABLE` 由来）: **最優先ワークフローの全選択 Step**。下流ワークフロー（例: ARD+AAS 同時選択時の AAS）の入力は上流が同一セッション内で生成するため検査しない。
  - **パラメータ要件**（`StepDef.required_params`、FR-DAG-07 由来）: **全選択ワークフローの全選択 Step**。パラメータはどの上流ワークフローも生成しないため、判定を遅らせても解消されない。
  - `default_params` を持つキーは実行時に `apply_step_default_params` が補完するため、GUI 未入力でも不足としない。
  - 根拠: 従来は `summarize_requirements_for_selection` が常に 0〜1 件しか返さず、`pick_target_step` が自然順最小 Step のみを選ぶため、同一ワークフロー内の後続 Step が固有に必要とする入力は起動前に一切検査されなかった。
  - バナー（リアルタイム表示）は情報密度を保つため従来どおり代表 1 件のみを表示してよい。
  - `REQUIREMENT_TABLE` と `WORKFLOW_PRIORITY`（[hve/gui/workflow_step_requirements.py](hve/gui/workflow_step_requirements.py)）は、`list_workflows()` が返す全ワークフローを網羅しなければならない。GUI のワークフロー一覧はレジストリから動的に構築される（[hve/gui/page_workflow_select.py](hve/gui/page_workflow_select.py) `_load_workflow_choices`）ため、未登録のワークフローは選択できるにもかかわらず `pick_target_step` が `WORKFLOW_PRIORITY` 順にしか走査せず、ファイル要件が 1 件も評価されないまま precheck が無警告で通過する。
  - FR-CLI-82 の対象となる GitHub 連携設定は、同要件の単一実装によるローカル判定を追加で行い、設定不整合を `SETTING`、token 不足を `AUTH` として表示する。remote branch の実在確認は UI thread で行わず、`hve orchestrate` 子プロセスの共通 preflight に委譲する。
  - Prompt 自由記述欄は FR-CLI-82 に従い内容検査の対象外とし、Prompt の空欄・自然言語・業務内容を理由に precheck を失敗させてはならない。
- **FR-GUI-02**: GUI の必須入力キー集合は `StepDef.required_params`（FR-DAG-07）から導出する。GUI 側で必須キーを二重管理してはならない。
  - 対象は `required_params` のうち **`default_params` を持たないキー**に限る。既定値を持つキーは FR-GUI-01 が不足報告しないため入力欄を設けても利用者が埋める理由が無く、逆に空でない値が保存されると `apply_step_default_params` は補完をスキップするため、誤った値がレジストリ既定値を無言で上書きし続ける。
  - この「GUI が可視化する必須キー」の判定は単一実装とし、FR-GUI-01 の precheck 側と入力欄導出側で別々に書いてはならない（FR-MAINT-07）。
  - `hve/gui/workflow_step_requirements.py` の `INPUT_FIELD_KEYS` は、静的定義に加えてレジストリ宣言由来のキーを含む。
  - `hve/gui/page_options.py` の監視対象ウィジェット表は `INPUT_FIELD_KEYS` を網羅しなければならない。
- **FR-GUI-03**: GUI の Azure 設定のうち FR-GUI-02 の対象キー（`default_params` を持たない `required_params`。ASDW-WEB Step 1.3 では `resource_group` のみ）は設定ストアへ永続化し、次回起動時に復元する（[hve/gui/settings_store.py](hve/gui/settings_store.py) / [hve/gui/settings_apply.py](hve/gui/settings_apply.py)）。毎回の再入力を強いてはならない。
  - 入力欄を廃止したキーは設定ストアの既定値からも外し、`_OBSOLETE_KEYS` へ登録して保存済みの値を除去する。UI から編集できないキーの値が設定ファイルに残り続けると、FR-GUI-02 が挙げた「既定値の無言の上書き」を利用者が発見も修正もできない。
- **FR-GUI-06**: GUI の Step 1 右ペインは、選択中ワークフローが必要とする必須入力キーの入力欄を、当該ワークフローの枠内に表示しなければならない。バナーが「未入力」と警告するキーに対応する入力欄が画面上に存在しない状態を作ってはならない。
  - 対象キーは FR-GUI-01 が評価する 2 系統（`REQUIREMENT_TABLE` の `required_info_keys` と `StepDef.required_params`）の和集合とする。ただし `StepDef.required_params` 側は FR-GUI-02 に従い `default_params` を持たないキーに限る。必須キーの正本は FR-GUI-02 に従いレジストリ側にあり、表示対応表（[hve/gui/page_options.py](hve/gui/page_options.py) の `_STEP2_FIELDS_BY_WORKFLOW`）で必須性を再定義してはならない。
  - ワークフロー固有の入力欄を他に持たないワークフローについても、必須入力キーがある限り枠を生成する。
  - 複数ワークフローを同時選択した場合、同一の入力欄を共有するワークフロー間では先頭のワークフロー枠へ集約してよい（`resource_group` は `asdw-web` / `adfdv` / `aagd` で同一の入力欄を共有する）。求めるのは入力欄が画面上に存在することであり、枠ごとの重複表示は求めない。
  - 表示対応表に、実在しない入力欄を指すエントリを残してはならない。
  - Step 1 右ペインで入力した必須入力キーの値は設定ストアの `[options]` へ永続化し、次回起動時に復元する。FR-GUI-03 の永続化要件は設定画面経路だけでなく Step 1 右ペイン経路にも適用する。

### 6.5 GUI からの mdq / cq 索引運用

- **FR-GUI-04**: GUI の設定画面は `cq`（§3.9）の運用操作を提供する。提供範囲は、profile の選択、索引統計の表示（FR-CQ-15 の言語別内訳を含む）、索引の差分更新、索引の完全再ビルド、索引 DB の削除、およびリアルタイム索引更新の設定とする。
  - `tools/skills/code_query/` は、HVE GUI を起動せずに利用できる独立した Code-Query 管理画面を提供する。管理画面は起動引数で対象リポジトリルートを受け取り、省略時は起動時のカレントディレクトリを対象とし、操作対象の絶対パスをウィンドウ上で識別可能に表示する。
  - 独立版と HVE 組み込み版は、管理セクション、索引操作サービス、およびバックグラウンド処理を単一実装として共有する。HVE 用と独立版用に同じ索引操作・表示ロジックを複製してはならない（FR-MAINT-07）。
  - 独立版は対象リポジトリごとに GUI 設定を分離し、HVE リポジトリでは既存の `hve/.settings.txt`、それ以外では対象リポジトリ直下の `.cq-gui-settings.txt` を使用する。独立版が所有する `[cq]` と CQ watcher 用設定以外の既存セクション・キーを保存時に消去してはならない。
  - 配布キットの可搬性（セットアップ、OS 別ランチャ、同期済み `vendor/cq/` だけでの上流 import path 非依存起動、GUI 任意依存未導入時の fail-closed）は §3.10（FR-KIT-01 / FR-KIT-03 / FR-KIT-04）を適用する。規範の分岐を避けるため、本節で重複して規定しない。
  - GUI は `cq` の設定ファイルを索引対象の単一の情報源とし、索引ルート・除外パターン・最大ファイルサイズを書き換えてはならない。GUI 上では読み取り専用として表示する。設定内容の編集は設定ファイルの直接編集に委ねる。
  - `cq` の設定が存在しない場合、GUI は既定 profile を推測して索引してはならない（FR-CQ-01 の fail-closed を GUI から迂回してはならない）。索引操作を無効化し、設定が不足している旨と `cq` が探索する設定ファイル候補の全パスを表示する。設定不在を理由に GUI を異常終了させてはならない。
  - GUI は索引 DB のパスを `cq` の profile → DB パス解決から取得し、独自のパス規則を実装してはならない。
  - GUI の索引統計は `cq` の索引スキーマを単一の情報源とする。`cq` の CLI と GUI で統計集計の実装が二重化してはならない（FR-MAINT-07）。
  - GUI は FR-CQ-15 の言語別内訳を表示し、言語ごとのファイル数・シンボル数・チャンク数・パーサフィデリティ別ファイル数を識別できるようにする。パーサ別の集計だけを表示してはならない。
  - 索引が未生成の profile について統計を表示する場合、GUI は索引 DB ファイルおよび索引ディレクトリを新規作成してはならない。統計取得を理由に空の索引を生成してはならない。
  - GUI の設定ストアは `mdq` の設定と `cq` の設定を別セクションで保持する。一方のセクションの保存によって他方のセクションの値を消去してはならない。
  - リアルタイム索引更新の有効・無効および debounce 間隔は設定ストアへ永続化し、GUI が起動する `hve orchestrate` の対応する CLI 引数へ伝播しなければならない。GUI 側で当該既定値を二重管理してはならない。
- **FR-GUI-05**: GUI の設定画面は `mdq`（§3.8）の運用操作を提供する。提供範囲は、索引対象フォルダの選択、tokenize 言語・chunking strategy・当該 strategy 固有パラメータ（overlap 段落数等）の選択、索引統計の表示、strategy 別統計の一括取得、索引の差分更新と完全再ビルド、索引 DB の削除、試し検索、利用統計レポートの生成、およびリアルタイム索引更新の設定とする。
  - [tools/skills/markdown_query/](tools/skills/markdown_query/) は、HVE GUI を起動せずに利用できる独立した Markdown-Query 管理画面を提供する。
  - 独立版と HVE 組み込み版は、管理セクション、索引操作サービス、およびバックグラウンド処理を単一実装として共有する。HVE 用と独立版用に同じ索引操作・表示ロジックを複製してはならない（FR-MAINT-07）。
  - 共有実装は `mdq` パッケージが所有し、依存方向を HVE → `mdq` の一方向とする。HVE の GUI が配布キット配下のモジュールを import してはならない。
  - 独立版と HVE 組み込み版の差異は設定ストアの差し替えだけで表現し、共有実装が実行時に上流パッケージの有無を判定して分岐してはならない（FR-KIT-05）。
  - 索引操作サービスは、strategy 別統計の一括取得と strategy 固有オプションの受け渡しを同一実装で提供しなければならない。HVE 版と独立版で提供機能が異なってはならない。
  - 索引が未生成の strategy について統計を表示する場合、GUI と索引操作サービスは索引 DB ファイルおよび索引ディレクトリを新規作成してはならない。統計取得を理由に空の索引を生成してはならない。単一 strategy の統計取得と strategy 別統計の一括取得で、この判定が食い違ってはならない（FR-MAINT-07）。索引 DB の削除後に統計を再取得しても、削除した索引を再生成してはならない。
  - GUI からの索引構築は、各 chunking strategy の索引実体を `mdq` の CLI と同一の構築実装で生成しなければならない。SQLite 索引を持たない strategy（`graphrag`）を SQLite 索引経路へフォールバックさせ、チャンクを持たない索引 DB を生成してはならない。strategy 別の索引実体パス規則は単一実装を情報源とし、CLI と GUI で二重に定義してはならない（FR-MAINT-07）。
  - strategy 別統計の索引存在判定は、当該 strategy の索引実体を対象としなければならない。SQLite 索引を持たない strategy について SQLite ファイルの有無を存在判定に用いてはならない。実体から取得していないファイル数・チャンク数を 0 として表示してはならない。
  - 索引実体がディレクトリである strategy については、ディレクトリの存在だけをもって構築済みと判定してはならない。任意依存の欠落等で構築が失敗した場合も空のディレクトリが残るため、当該索引エンジンが生成する実体の有無で判定しなければならない。この判定規則は単一実装を情報源とし、索引構築側と統計側で二重に定義してはならない（FR-MAINT-07）。
  - 索引構築の結果表示は、索引エンジンが記録した実際の処理結果を反映しなければならない。構築 API の呼び出しが例外を送出しなかったことだけを根拠に成功件数へ計上してはならない。エンジンが文書単位の失敗を記録している場合は、その件数を利用者が識別できる形で提示しなければならない。
  - 索引構築の成否を左右する strategy 固有パラメータは、CLI だけでなく GUI からも調整できなければならない。既定値はコード側を単一の情報源とし、GUI の設定ストアへ既定値を複写して二重管理してはならない（FR-MAINT-07）。
  - 任意依存が未導入で構築できない strategy は、失敗として提示しなければならない。空の索引を生成して成功として提示してはならない。GUI が任意依存を自動導入してはならない。当該 strategy がチャンク生成の代替手段を定義している場合（`semantic_paragraph` の `heading_recursive` フォールバック）は、代替手段で生成した索引を当該 strategy の索引として扱ってよい。
  - 設定ストアのセクション分離と非破壊性は FR-GUI-04 の規定を適用する。
  - 配布キットの可搬性は §3.10（FR-KIT-01 / FR-KIT-03 / FR-KIT-04）を適用する。
- **FR-GUI-07**: GUI の設定画面は Tool Search（§3.5.1）の設定と統計を提供する。提供範囲は、SDK ツール検索の有効化（`tool_search`）、ランキング実装の選択（`tool_search_ranking`）、Skill レイヤー（Core / Extend の分類と `hve/skill_manifest.json` の workflow / step 別宣言）の閲覧、`hve/toolsearch/policy.json` の現在値の表示と編集、収集済み統計（FR-TS-09）の表示と再集計、HTML レポートの書き出し、収集済みイベントの削除、および Step 実行セッションのコンテキスト内訳の実測とする。
  - `tool_search` と `tool_search_ranking` の入力欄は設定画面が単一の所有者とし、Step 1 右ペインと二重に持ってはならない（FR-MAINT-07）。値は設定ストアの `[options]` へ永続化し、GUI が起動する `hve orchestrate` の対応する CLI 引数へ伝播しなければならない。
  - **設定項目の説明は、当該環境で実際に起きる挙動と食い違ってはならない。** SDK のツール定義遅延ロードが発火しない環境では、その旨を実測日と CLI 版つきで明示しなければならない。根拠となる実測（Copilot CLI 1.0.79 / SDK 1.0.7、`session.metadata.contextInfo`）: `tool_search` の設定値を変えても `toolDefinitionsTokens` は変わらず、無効時と `defer_threshold=1` 指定時がともに 52,756 で完全に一致した（有効時に観測した 49,929 との差は MCP 接続タイミングのゆらぎで、有効 / 無効を交互に 5 回測ると同じ設定でもツール数 171 と 183 の両方が観測される）。全ツールの `defer_loading` は `null` で、`tool_search_tool` はツール一覧に現れない。`tool_search_ranking="hve"` はツール定義を 47,115 → 59,275 tokens（+12,160）へ増やす。
  - Skill レイヤーの表示は読み取り専用とする。実行時の必須 Skill 解決は [hve/runner.py](hve/runner.py) / [hve/skill_resolver.py](hve/skill_resolver.py) が担い、GUI は判定を再実装してはならない（FR-MAINT-07）。Core / Extend は `policy.json` 上の分類であり、Extend が実際に遅延公開されるかは CLI 側の実装に依存する旨を併記しなければならない。
  - `policy.json` は Tool Search の pin・検索語彙・重み設定の単一の情報源とする。GUI は当該ファイルを表示し、`limit`・`max_limit`・`tau`・`field_weights`・`pins`・`additional_search_text`・`step_overrides` を編集して同じファイルへ保存できなければならない。`version` はスキーマ版であり編集させてはならない。読み込みに失敗した場合は推測した既定値を表示せず、失敗した旨と対象パスを表示する。あわせて `always` / `auto` / `never`、`limit`、`tau` の意味を示す凡例と参照先を表示しなければならない。
    - 保存先は表示元と同一のパス（[hve/toolsearch/policy.py](hve/toolsearch/policy.py) `ToolSearchPolicy.default_path()` の解決結果）とする。表示したファイルと異なるファイルへ書き込んではならない。
    - 保存は書き込み前に `ToolSearchPolicy.from_dict()` と同一の検証を通さなければならない。検証に失敗した場合はファイルを一切変更せず、失敗理由を表示する（fail-closed）。値を丸めたり既定値で補ったりして保存してはならない。
    - 保存時に、当該ファイルが持つ未知のトップレベルキー（`_comment` 等）を失ってはならない。
    - 読み込みに失敗した状態から保存してはならない。既存の内容を空値や推測値で上書きしてはならない。
    - 保存の失敗（書き込み権限不足等）で GUI を異常終了させてはならない。失敗した旨と理由を表示する。
    - 保存した値が実行時へ反映されるのは次に開始する Step 実行からであることを表示しなければならない。実行中セッションへ即時反映されるかのように表示してはならない。
    - 各編集項目には、初見の利用者が値の意味と増減の影響を判断できる説明を表示しなければならない。説明文は [hve/gui/help_content.py](hve/gui/help_content.py) を単一の情報源とし、GUI の各セクションで二重に持ってはならない（FR-MAINT-07）。
    - 本セクションの表示文字列（上記の説明を含む）は翻訳カタログの抽出対象とし、英語表示で日本語のまま残してはならない。`.ts` だけを更新してコンパイル済み `.qm` を再生成しない状態を残してはならない（実行時に読まれるのは `.qm` のため）。
  - 統計の集計と描画は [hve/toolsearch/stats.py](hve/toolsearch/stats.py) / [hve/toolsearch/dashboard.py](hve/toolsearch/dashboard.py) を単一の情報源とし、GUI 側で集計・整形を再実装してはならない（FR-MAINT-07）。
  - 収集済みイベントが無い指標を 0 や推定値で埋めて表示してはならない（FR-TS-10）。統計の読み込み・削除の失敗で GUI を異常終了させてはならない。
  - **収集済みイベントが 0 件のときは、「データ不足」の表示に加えて未充足の収集条件を表示しなければならない。** 収集には `tool_search` が有効であること、`tool_search_ranking` が `"hve"` であること、および CLI がモデルへ `tool_search_tool` を公開していることのすべてが必要である。設定から判定できる前 2 者は設定値から判定し、3 番目は「設定は満たしているがイベントが 0 件」という観測事実として表示する。観測していない事実を原因として断定してはならない。
  - **コンテキスト内訳の実測**は、`session.metadata.contextInfo` と `session.metadata.getContextAttribution` から層別（システムプロンプト / 組み込みツール定義 / MCP サーバー別）の実トークン量を取得して表示する。[hve/toolsearch/eval.py](hve/toolsearch/eval.py) のトークン推定で代替してはならない。測定は `session.send` を行わずモデル推論を発生させてはならない。実行は利用者の明示操作に限り、タブを開いただけで実行してはならない。集計ロジックは CLI（`hve toolsearch context`）と単一実装を共有し、GUI 側で再実装してはならない（FR-MAINT-07）。トークン量はトークナイザ依存であるため、測定に用いたモデル名を併せて表示しなければならない。stdio MCP は接続に時間を要する（実測: `azure` は 3.7〜5.1 秒）ため、宣言済みサーバーの接続完了を待ってから測定し、待っても接続しなかったサーバーはその事実を表示しなければならない。
  - 実測が失敗した場合（Copilot CLI 不在・認証不足・MCP 接続不能等）は、失敗した旨と理由を表示し、推定値や前回値で埋めてはならない。
- **FR-GUI-22**: HVE GUI の起動時、FR-CLI-77 と同一の対象規則・同一の実装で、実在する `mdq` / `cq` の索引 DB をバックグラウンドで差分更新しなければならない。対象列挙と更新処理を CLI と GUI で二重に実装してはならない（FR-MAINT-07）。
  - 起動は GUI プロセスにつき 1 回とする。複数の MainWindow を開いても、同一の索引 DB へ 2 つの更新経路を同時に生じさせてはならない。
  - 差分更新の実行中は、Workflow 実行の開始操作を受け付けてはならない。GUI が起動する `hve orchestrate` 子プロセスは自身の watcher を起動するため、GUI 側の更新と子プロセス側の書き込みが同一の索引 DB へ同時に到達しうるからである。
  - 実行中であることとその理由を利用者へ表示しなければならない。理由を示さずに操作を無効化してはならない。表示文字列は翻訳カタログの抽出対象とし、`.ts` だけを更新してコンパイル済み `.qm` を再生成しない状態を残してはならない。
  - 更新の失敗で GUI を異常終了させてはならない。
  - 有効・無効の制御は FR-CLI-77 と同一の環境変数による。GUI 専用の設定項目を追加してはならない。

### 6.6 GUI 質問票の「その他」回答

- **FR-GUI-08**: GUI の QA 回答ダイアログは、選択肢を持つ各質問について、既存の選択肢を保持したまま「その他」を選択肢として 1 件表示しなければならない。質問票の選択肢に既に「その他」が含まれる場合も、画面上で重複表示してはならず、その既存選択肢を自由記述入力に用いなければならない。「その他」の選択時は自由記述欄を入力可能にし、空でない入力は既存の GUI ↔ CLI 回答形式 `N:: その他: <text>` で送信する。`QAMerger` は当該自由記述を選択肢ラベルへ変換せず、マージ済み質問票ファイルの「ユーザー回答」へ `その他: <text>` として保存しなければならない。通常の選択肢は既存の `N: <label>` 形式、選択肢を持たない質問は既存の自由記述入力、未入力の「その他」は当該質問の既定値採用、キャンセル、および IPC のファイル形式を維持する。

### 6.7 GUI の GitHub CLI ログイン用セットアップ

- **FR-GUI-09**: Windows の通常セットアップ入口 `hve/setup-hve.cmd` と macOS / Linux の通常セットアップ入口 `./hve/setup-hve.sh` は、オプションなしで実行したとき、HVE GUI の「GitHub CLIでログイン」が必要とする `gh` を OS ツールとして導入・解決し、同一リポジトリの `.venv` に OS 別 PTY backend（Windows: `pywinpty` が提供する `winpty`、macOS / Linux: `ptyprocess`）を導入し、セットアップ完了前に双方の利用可能性を検証しなければならない。
  - 通常 GUI 構成では、`gh` バイナリを解決できない場合、または GUI 共通 PTY 判定（[hve/gui/pty_backend.py](hve/gui/pty_backend.py) `is_pty_available()`）が利用不可を返す場合、セットアップは非ゼロで終了する。
  - `gh auth status` が未認証を返すことは、GUI で初回ログインを行う正常な開始状態であり、セットアップ失敗条件にしてはならない。セットアップ自身は `gh auth login` を実行してはならない。
  - 既存の正常な `.venv` に通常セットアップを再実行した場合も、不足する `gh` / PTY 依存を追加または修復できなければならず、`Force` を要求してはならない。
  - `NoGui` / `Minimal` は明示的な opt-out として維持し、上記 `gh` / PTY の構築・検証を要求しない。
  - `CheckOnly` / `--check-only` は環境を変更しない診断モードとして維持する。通常 GUI 構成では `gh` を解決できない場合、および既存 `.venv` で GUI 共通 PTY 判定が利用不可を返す場合に警告を出力しなければならないが、通常実行の fail-closed 契約とは分離し、非ゼロ終了してはならない。`.venv` の作成・依存導入を行ってはならない。
  - GUI の PTY 不足または GitHub CLI ログイン事前検査失敗からの復旧案内は、Windows では `hve\setup-hve.cmd`、macOS / Linux では `./hve/setup-hve.sh` を主導線としなければならない。手動の依存導入は補助情報に限り、唯一の復旧案内にしてはならない。
  - 復旧案内の setup パスは GUI の作業ディレクトリに依存してはならない。パッケージ配置から解決した実パスを提示し、setup スクリプトが同居しない導入形態では推測した絶対パスを出さず相対表記へ退避しなければならない。
  - GUI 依存未導入時の GUI 起動案内も同じ主導線に従い、`.[gui]` 単独導入を完全構成の推奨復旧経路として提示してはならない。実在する起動入口（`hve.cmd gui` / `./hve.sh gui`）を案内する。

### 6.8 GUI の Copilot 対話と実行ジョブ連携

- **FR-GUI-10**: HVE GUI の Copilot パネルは、送信のたびに `copilot -p`（非対話モード）の使い捨てプロセスを起動してはならない。GitHub Copilot CLI の対話セッションを 1 プロセスとして起動・維持し、複数ターンの会話とストリーミング表示、および CLI 組み込みの対話コマンド（`/model` / `/context` / `/resume` / `/fork` / `/compact` / `/permissions` / `/mcp` / `/plugin` / `/skills` / `/agent` / `/plan` / `/diff` 等）を利用者へそのまま提供しなければならない。
  - 端末面は既存の PTY 抽象（[hve/gui/pty_backend.py](hve/gui/pty_backend.py)）と端末結線（[hve/gui/widgets/terminal_session.py](hve/gui/widgets/terminal_session.py)）を再利用し、PTY 読み取りを GUI スレッドで行ってはならない。
  - HVE は CLI の画面出力を解釈してチャット UI を再構成してはならない。チャットセッション管理・モデル選択・ツール権限・MCP / Plugin / Skill の管理は Copilot CLI を唯一の情報源とし、HVE 側で再実装してはならない（FR-MAINT-07）。
  - CLI バイナリの解決規則は [hve/gui/copilot_cli_bridge.py](hve/gui/copilot_cli_bridge.py) を単一の情報源とする。GUI 側で別の解決規則を実装してはならない。
  - CLI または PTY backend を解決できない場合は fail-closed とし、FR-GUI-09 の OS 別セットアップを主導線として案内しなければならない。使い捨ての非対話モードへ暗黙にフォールバックしてはならない。
- **FR-GUI-11**: 汎用チャット用に起動する Copilot CLI セッションへ、HVE が `--allow-all-tools` / `--allow-all` / `--allow-all-paths` / `--allow-all-urls` / `--yolo` / `--no-ask-user` を暗黙に付与してはならない。ツール実行の承認は CLI の対話承認と `/permissions` に委ね、権限の緩和は利用者の明示操作に限る。
  - 起動時はリポジトリルートを作業ディレクトリとして渡す（`-C`）。利用者の入力文字列をシェルコマンドへ連結して起動してはならない。
  - 本要件は Step 実行セッション（[hve/runner.py](hve/runner.py)）の権限方針を変更しない。Step 実行の承認方針は本要件の対象外とする。
- **FR-GUI-12**: GUI は実行中の HVE ジョブに対して、次の 3 種の対話送信を提供しなければならない。実行側（[hve/runner.py](hve/runner.py)）は各 action を以下のとおり SDK 呼び出しへ写像する。
  - `queue`: `session.send(text, mode="enqueue")`。実行中のターンを中断せず、完了後に処理させる。
  - `steer`: `session.send(text, mode="immediate")`。実行中のターンへ割り込みメッセージとして届ける（既存 Steering と同一挙動）。
  - `stop_and_send`: `session.abort()` で実行中のターンを取り消したうえで、当該テキストを新しいターンとして送信し、**実行側がその応答を待機して当該 Step の主応答として扱わなければならない**。
    - 根拠（SDK 1.0.8 の実装）: `CopilotSession.abort` は「セッションは有効なまま新しいメッセージに使用できる」と規定し、`CopilotSession.send_and_wait` は `session.idle` の受信で復帰する。abort が `session.idle` を生じさせるか否かはサーバー側の挙動であり、本書では確定しない。
    - したがって実装は、abort により主タスクの待機が復帰する場合でも、送信したテキストへの応答が観測されないまま当該 Step が後続ゲートへ進まないことを保証しなければならない。
  - 送信要求はファイルベース IPC で受け渡し、要求本文（プロンプト）を ACK・統計イベント・標準ログへ複製してはならない。
  - 各要求は要求 ID を持ち、実行側は処理結果を要求 ID・action・状態（`accepted` / `failed` / `cancelled`）だけで応答しなければならない。
  - 未消費の要求に限り、順序変更と取り消しを許可する。処理済みの要求を再処理してはならない。
  - 既存の `{"text": ...}` 形式の Steering 要求は `steer` として後方互換で処理しなければならない。
- **FR-GUI-13**: GUI は対話送信の宛先と実行ログを次のとおり扱わなければならない。
  - Plan モードと Autopilot モードの双方で、実行中の workflow instance と step を列挙し、利用者が宛先を明示選択できなければならない。実行中 step が複数ある場合に送信機能を無効化してはならない。
  - 各 workflow instance は固有の IPC チャネルを持たなければならない。複数の instance が同一チャネルを共有してはならない。
  - 宛先の実行ログは [hve/gui/workbench_state.py](hve/gui/workbench_state.py) が保持する instance 別 / step 別バッファと更新シグナルから増分取得しなければならない。ログを再パースしてはならず、帰属が判定できない行を特定の step へ推測で割り当ててはならない。
  - 完了済みジョブは宛先一覧に表示して transcript と結果を参照できるようにするが、対話送信の宛先にしてはならない。
- **FR-GUI-14**: GUI は完了したジョブの結果を Copilot と相談するために、新しい Copilot CLI チャットの初期コンテキストを構成できなければならない。
  - 対象は選択したジョブの run ID・workflow / instance / step・終了コードと、`console-log.txt`・`gui-logs/`・completion report・セッション生成ファイルのうち **実在するパスだけ** とする。
  - ファイル本文をプロンプトへ埋め込んではならない。存在しないパスを列挙してはならない。選択した run のルート外を自動探索してはならない。
  - GUI セッション作業ディレクトリの後処理方針（`keep` / `archive` / `purge`）を本機能のために上書きしてはならない。`purge` を選んだ利用者に対して、削除済みの成果物を参照できると説明してはならない。
- **FR-GUI-15**: 本節の機能境界は次のとおりとする。
  - 本節は §5.6「セッション永続化と再開（廃止）」を復活させない。Copilot CLI の `/resume` は CLI が所有するチャットセッションの再開であり、HVE ワークフローの再開ではない。両者を同一機能として説明してはならない。
  - FR-GUI-50 の HVE execution resume は HVE-owned control state を再利用する別機能であり、Copilot CLI `/resume` や model生成途中のcheckpointとして表示してはならない。
  - VS Code 固有の実行面（エディタ内インライン補完、インラインチャットの差分適用、SCM / デバッガ / ノートブック専用 UI、拡張ホストと拡張提供ツール、統合ブラウザ、Agents Window、チェックポイント UI）は本要件の対象外とし、HVE GUI で再実装してはならない。
- **FR-GUI-16**: GUI の実行前オプション画面（Step 1 右ペイン）は、`auto_qa`（QA (質問票) 自動投入）を全ワークフロー共通の**必須選択項目**として常時表示しなければならない。
  - `auto_qa` は FR-QA-03 の回答済み QA 保存を行うかどうかを決める唯一の入口であるため、既定値による暗黙決定を許さず「未選択 / 有効にする / 無効にする」の 3 状態で明示選択させる。Knowledge Management への差分同期を起動するかどうかは、`auto_qa` に加えて FR-QA-05 の `qa_akm_background_merge` が有効であることを要する。
  - 既定は「未選択」とし、未選択のままでは `validate()` を失敗させて実行を開始してはならない。
  - `qa_answer_mode`（QA (質問票) 回答モード）は Step 1 右ペインでは同じ枠へ併記し、設定画面では「QA (質問票)」ノードへ配置する（FR-GUI-20）。いずれの面でも `auto_qa` が「有効にする」のときだけ活性化する。
  - 永続化表現は 3 状態セレクタ共通の `"" / "on" / "off"` とし、「未選択」を `False` として保存してはならない（[hve/gui/page_options.py](hve/gui/page_options.py) / [hve/gui/settings_store.py](hve/gui/settings_store.py)）。
- **FR-GUI-17**: GUI は FR-QA-04 の `akm_model` / `akm_reasoning_effort` / `akm_context_tier` を、設定画面と実行前オプション画面（Step 1 右ペイン）の双方で選択できるようにしなければならない。
  - Step 1 右ペインでは `auto_qa` と同じ「共通設定」枠へ配置し、設定画面では「Knowledge Management」ノードへ配置する（FR-GUI-20）。`auto_qa` が「有効にする」で、かつ FR-QA-05 の `qa_akm_background_merge` が有効のときだけ活性化する。いずれかを満たさないときはグレーアウトし、値を CLI へ渡してはならない。
  - モデルの選択肢は既定で「継承」（メインの「使用するモデル」を使用）を先頭に持ち、レビュー用モデル / QA 用モデルと同一の副モデル選択規約に従う。context tier も「継承」を既定とする。
  - 永続化表現は空文字を「継承」とし、保存済みの空文字を具体値へ移行してはならない。
  - reasoning effort は選択中の AKM 用モデルが reasoning effort をサポートするときだけ活性化し、サポートしない場合とモデルが「継承」の場合は選択不可としなければならない。
- **FR-GUI-18**: Copilot パネルの「実行ジョブ」タブは、対話面の構成を Visual Studio Code のチャットビューと同等にしなければならない。本要件は FR-GUI-12 / FR-GUI-13 の送信契約とログ取得契約を変更しない。
  - 会話ビューは 1 本の時系列スクロール列とし、利用者の送信メッセージ・その ACK・GUI 自身の通知・宛先の実行ログを同じ列へ順に配置しなければならない。
  - 会話バブルとして役割付けしてよいのは、HVE 自身が発生源であるもの（送信メッセージ・ACK・GUI 通知）だけとする。宛先の実行ログは既存のログ表示と同じ体裁（[hve/gui/fonts.py](hve/gui/fonts.py) `preferred_log_font`）の生ログとして提示し、行を解析して発話者・役割・ターン境界を推定してはならない（FR-GUI-13）。
  - 入力欄は複数行入力とし、`Enter` で送信、`Shift+Enter` で改行しなければならない。入力量に応じて高さを伸ばしてよいが、伸長の上限を定め、上限に達した後は入力欄内でスクロールさせなければならない。
  - 入力欄はコンテキスト添付を持たなければならない。添付は選択したファイルの**パスだけ**を送信本文へ列挙するものとし、ファイル本文を読み取って本文へ埋め込んではならない。添付は個別に取り消せなければならない。添付を含めた送信本文は既存の入力上限（8 KiB）を超えて送信してはならない。
  - 送信方法（`queue` / `steer` / `stop_and_send`）は入力欄のツールバーへ配置しなければならない。実行中ジョブのモデル・reasoning effort を選択する UI を設けてはならない（FR-GUI-10）。
  - FR-GUI-12 が許可する未消費要求の取り消しと順序変更を、送信待ちキューとして画面から操作できなければならない。取り消し・順序変更の対象は未消費要求に限る。
  - 会話ビューの表示リセット（クリア）と全文コピー、および FR-GUI-14 の結果参照は、対話の主導線を圧迫しない補助操作としてまとめて提供しなければならない。表示リセットは画面表示だけを対象とし、送信済み要求・実行中ジョブ・IPC チャネルへ影響を与えてはならない。
  - 会話ビューは、利用者の送信メッセージを「ターン」として、現在位置（`現在番号/総数`）と前後移動を会話ビューの直上から参照・操作できなければならない。
    - ターンとして数えてよいのは利用者の送信メッセージだけとする。GUI 通知・ACK・実行ログをターンに含めてはならない。
    - 現在ターンは、移動操作を行ったときはその移動先とし、利用者が会話ビューをスクロールしたときはスクロール位置から決定しなければならない。いずれの場合も表示中の番号が現在ターンと食い違ってはならない。会話全体がスクロールせずに収まる場合と、移動先を上端へ寄せきれない場合も同様とする。
    - 新しい送信メッセージを追加したときは、そのメッセージを現在ターンとしなければならない。
    - 送信メッセージが 1 件も無いときは、位置表示と前後移動を表示してはならない。
    - 先頭のターンでは前へ、末尾のターンでは次への移動操作を選べないようにしなければならない。移動を循環させてはならない。
    - ここに表示する本文は送信メッセージの本文だけとし、送信方法・ACK 状態を併記してはならない（いずれも当該メッセージ自体が保持しているため）。表示は 1 行とし、改行以降および実装が定める表示長の上限を超える部分は省略しなければならない。
  - 選択中の宛先について、状態・対話チャネルの利用可否・送信待ち件数を常時参照できなければならない。ここに実行ログを再掲してはならない。
  - ジョブ全体の停止操作を「実行中の応答の取り消し」として提示してはならない。両者は作用範囲が異なるため、同一の操作として説明・配置してはならない。
  - 音声入力、実行ジョブのチャットセッション永続化、VS Code 固有の実行面（FR-GUI-15）は本要件の対象外とする。

### 6.9 GUI Workbench の経過時間表示とジョブ終了検知

- **FR-GUI-19**: GUI の Step 2 Workbench は、実行対象のジョブが終了または停止した時点で経過時間の計測を停止しなければならない。
  - 「作業状況」（[hve/gui/widgets/dag_status_widget.py](hve/gui/widgets/dag_status_widget.py)）が表示する経過時間は、サマリー行・Workflow ノード・Step ノード・fan-out 子ノードのすべてを対象とする。ジョブ終了時に一部だけを停止させ、同一画面内で停止と継続が混在する状態を作ってはならない。停止後に表示ノードを再生成する画面更新（`set_plan` / `update_workflow_instances` の再呼び出し）が行われても、停止状態を維持しなければならない。
  - ジョブの終了検知を、サブプロセスの標準出力ストリームの終端だけに依存させてはならない。GUI が当該サブプロセスの終了を確認できる場合は、ストリームが終端していなくても終了として扱わなければならない。終了の根拠は当該プロセスの終了状態に限り、出力が一定時間途切れたことを終了の根拠にしてはならない。プロセスの終了確認後、既存の終端通知経路が反応するための猶予を設けてよいが、猶予は 10 秒を超えてはならない。
  - ストリーム終端を伴わない終了を検知した場合、GUI は実行ログへ警告を 1 行出力し、当該実行を正常完了と区別できる形で異常終了として記録しなければならない。ただし利用者の停止要求に続く終了は利用者の意図によるため、異常終了として記録してはならない（経過時間の停止はいずれの場合も行う）。実際の結果を観測していないため、実行中であった Step の状態表示を完了・失敗のいずれかへ書き換えてはならない。本検知のために新たな観測イベント種別（`[hve:stats]` の `kind`）を追加してはならない。
  - 本検知による終了処理は、既存の終了経路と同じセッション後始末（実行ログ全文の保存等）を伴わなければならない。stream終端を待つreaderが残る場合は読取端を閉じ、thread終了を確認してからQObjectの破棄を予約する。
  - 本検知は parent window へ非 0 return code を 1 回だけ通知して navigation を更新する。ただし通常の「全タスク完了」通知へ流用せず、異常終了として表示しなければならない。Workflow は失敗として記録してよいが、実際の結果を観測していない実行中 Step の状態は `running` のまま保持する。
  - 同一の終了に対する終了処理は 1 回だけ行い、遅れて到着したストリーム終端によって二重に実行してはならない。
  - 新たな実行を開始したときは、直前の実行で記録した終了検知状態を初期化しなければならない。前回の検知状態によって、新しい実行の経過時間が計測開始直後から停止したままになってはならない。
  - 本要件は「作業状況」を持たない `--autopilot-child` 互換面（[hve/gui/workbench_window.py](hve/gui/workbench_window.py)）を対象外とする。

### 6.10 GUI 設定画面のカテゴリ構成と用語表記

- **FR-GUI-20**: GUI の設定画面「一般」カテゴリは、旧「自動プロンプト」ノードを廃止し、`基本設定` / `QA (質問票)` / `レビュー` / `Knowledge Management` / `自己改善 (Self Improve)` を含むノード構成へ再編しなければならない。
  - `追加プロンプト` と `コンテキスト最大文字数` は `基本設定` へ移す。`QA (質問票)` は `auto_qa` / `qa_answer_mode`、`レビュー` は `auto_contents_review` / `auto_coding_agent_review` / `auto_coding_agent_review_auto_approval`、`Knowledge Management` は `qa_akm_background_merge` / `akm_model` / `akm_reasoning_effort` / `akm_context_tier`、`自己改善 (Self Improve)` は `self_improve` / `self_improve_max_iterations` / `self_improve_target_scope` / `self_improve_goal` を持つ。
  - FR-QA-05 の `qa_akm_background_merge` は、設定画面の `Knowledge Management` ノードと Step 1 右ペインの「共通設定」枠の双方へ表示し、既定は無効（チェックなし）としなければならない。設定画面内で同一項目を複数ノードへ重複表示してはならない。
  - Step 1 右ペインの「共通設定」枠は、`QA (質問票) 自動投入` → `QA (質問票) 回答モード` → `qa_akm_background_merge` → `Knowledge Management 用モデル` → `Knowledge Management 用コンテキスト階層` → `追加プロンプト` の順で表示しなければならない。
  - 利用者が略語の意味を判別できるよう、GUI の表示ラベルと説明文では `QA` を `QA (質問票)`、`AKM` を `Knowledge Management` と表記しなければならない。CLI のフラグ名（`--akm-model` 等）と設定キー名は互換性のため改称してはならない。
  - Step 1 右ペインの入力値はセッション限りであり、永続化の唯一の入口は設定画面とする。右ペインへ独自の保存経路を追加してはならない。

### 6.11 ワークフロー一覧のカテゴリー構成

- **FR-GUI-21**: GUI の Step 1 ワークフロー選択（[hve/gui/page_workflow_select.py](hve/gui/page_workflow_select.py)）と CLI 対話ウィザードのワークフロー選択（[hve/__main__.py](hve/__main__.py)）は、同一のカテゴリー表に従ってワークフロー一覧を分類表示しなければならない。
  - カテゴリー表は単一実装（FR-MAINT-07）とし、[hve/workflow_registry.py](hve/workflow_registry.py) の `WORKFLOW_CATEGORIES` を正本とする。GUI 専用モジュールに定義してはならない。CLI は PySide6 に依存する `hve/gui/` 配下を import できず、GUI 側へ正本を置くと CLI が同じ分類を参照できないためである。
  - カテゴリーとその構成員は次の順序で定義する。`Business Engineering (要求定義)`: `ard` / `Architecture Design`: `aas` / `Software Engineering`: `aad-web`, `asdw-web`, `adfd`, `adfdv` / `既存ドキュメントのインポート`: `adi` / `Knowledge Management`: `akm`, `adoc` / `AI Agent`: `ada`, `aag`, `aagd`, `aar`。`ada` は AI Agent 経路専用のデータ設計 Workflow であるため `AI Agent` へ分類する。
  - カテゴリー表は登録済みの全ワークフローを過不足なく分類しなければならない。同一 ID を複数カテゴリーへ重複させてはならず、`workflow_registry` に存在しない ID を含めてはならない。
  - 未分類 ID を「その他」枠へ集約する縮退経路は維持しなければならない。新規ワークフローをレジストリへ追加した時点でカテゴリー表への登録が漏れても、選択肢自体が一覧から消えてはならないためである。
  - CLI 対話ウィザードは選択肢をカテゴリー順に並べ、各選択肢へカテゴリー名を接頭辞として表示しなければならない。`Console.menu_select` は与えられた全行を連番付きの選択肢として描画するため、選択できない見出し行を挿入してはならない。選択肢を並べ替える場合は、表示用リストと選択結果の解決に用いるリストを同一にして索引の整合を維持しなければならない。
  - GUI / Autopilot がワークフローの表示順を列挙する表（[hve/gui/page_options.py](hve/gui/page_options.py) `_WORKFLOW_CANONICAL_ORDER`、[hve/autopilot/plan_review_gap.py](hve/autopilot/plan_review_gap.py) `_WORKFLOW_CANONICAL_ORDER`、[hve/gui/workflow_step_requirements.py](hve/gui/workflow_step_requirements.py) `WORKFLOW_PRIORITY`）は、登録済みの全ワークフローを欠落なく列挙しなければならない。列挙から漏れたワークフローは当該経路の走査対象外となり、表ごとに対象範囲が食い違うためである。
  - GUI のワークフロー説明（[hve/gui/help_content.py](hve/gui/help_content.py) `_WORKFLOW_SHORT` / `WORKFLOW_GUIDE_MAP`）と表示名（[hve/template_engine.py](hve/template_engine.py) `_WORKFLOW_DISPLAY_NAMES`）は、登録済みの全ワークフローを対象としなければならない。`_WORKFLOW_SHORT` に説明を持たないワークフローはヘルプボタン自体が生成されず（`HelpPopupButton.from_key` が `None` を返す）、利用者が当該ワークフローの説明を参照する手段を持たないためである。

### 6.12 GUI が起動するサブプロセスの標準入力

- **FR-GUI-23**: GUI が起動する HVE サブプロセス（[hve/gui/state_bridge.py](hve/gui/state_bridge.py) `launch_orchestrator`、[hve/gui/autopilot/child_launcher.py](hve/gui/autopilot/child_launcher.py) `AutopilotController._default_popen`）は、標準入力を対話不能な状態で起動しなければならない。
  - 根拠: GUI は当該サブプロセスの標準入力をパイプにも PTY にも接続していないため、GUI から入力を送る経路が存在しない。ターミナルから起動した GUI では子プロセスが端末の標準入力を継承するため、CLI 側の対話プロンプト（[hve/__main__.py](hve/__main__.py) の認証 preflight および `--autopilot-chain` の実行確認）へ到達すると応答不能のまま停止する。
  - 本要件は FR-CLI-78 が定める対話可否の判定規則（`sys.stdin.isatty()`）を変更しない。CLI 単体実行の挙動を変えず、GUI 起動経路の標準入力だけを塞ぐことで同じ結果を得る。
  - CLI 側の対話プロンプトごとに GUI 起動を判定する分岐を追加してはならない（FR-MAINT-07）。判定をプロンプトへ分散させると、プロンプトを追加するたびに同じ判定を再実装することになるためである。

### 6.13 GUI の GitHub Issue / Pull Request 連携

- **FR-GUI-24**: HVE GUI は起動時に GitHub 認証状態を解決しなければならない。`GH_TOKEN` / `GITHUB_TOKEN` のいずれも未設定の場合、`gh auth token`（[hve/gui/gh_cli.py](hve/gui/gh_cli.py) `capture_gh_token`）でトークンを取得し、取得できた場合は同モジュールの `inject_token_into_env` で現プロセスの `GH_TOKEN` へ注入する。
  - 取得できなかった場合に限り、`gh auth login` を起動する導線を 1 回だけ利用者へ提示しなければならない。提示は利用者が拒否できるものとし、拒否した場合も GUI は通常どおり起動しなければならない。GitHub 連携を必要としない Workflow が存在するため、認証完了を GUI 起動の前提条件にしてはならない。
  - 起動時の認証解決は `gh auth login` を自動実行してはならない（FR-GUI-09 の「セットアップ自身は `gh auth login` を実行してはならない」と同じ根拠。対話ログインは利用者の明示操作に限る）。
  - ログイン端末とトークン捕捉の実装は既存の [hve/gui/gh_login_dialog.py](hve/gui/gh_login_dialog.py) と [hve/gui/gh_cli.py](hve/gui/gh_cli.py) を再利用しなければならず、起動経路向けに別実装を設けてはならない（FR-MAINT-07）。
  - トークンはセッション限りとし、ディスクへ永続化してはならない（NFR-SEC-01）。

- **FR-GUI-25**: GUI は Workflow 実行時の Root Issue を「新規作成」と「既存 Issue へ連携」から選択できなければならない。既存 Issue へ連携する場合、Orchestrator は Root Issue を新規作成せず、指定された Issue 番号を Root Issue として扱い、Sub-Issue の親および PR body の closing keyword（現行実装は `Closes #N`）に用いなければならない。
  - 選択は CLI オプション `--issue-number <N>` として Orchestrator へ伝達する。GUI 専用の伝達経路を追加してはならない。
  - `--issue-number` は `--create-issues` または `--create-pr` と併用したときに効力を持つ。`--create-issues` との併用では指定 Issue を Root Issue として Sub-Issue の親にも用いる。`--create-pr` だけとの併用では Root / Sub-Issue を作成せず、PR 作成前に指定 Issue を検証し、有効な Issue 番号を `root_issue_num` として返して PR body の `Closes #N` にだけ用いる。どちらも伴わない指定は警告して無視する。
  - 指定された番号の Issue を取得できない場合、取得結果が Pull Request である場合、または `number` を欠く場合は fail-closed とし、Root Issue の新規作成へ暗黙にフォールバックしてはならない。誤った番号のまま Sub-Issue を無関係な Issue へ紐付けることを防ぐためである。

- **FR-GUI-26**: GUI は GitHub Issue を閲覧・編集できる画面を提供しなければならない。提供範囲は、Issue 一覧の取得と絞り込み（`open` / `closed` / `all`）、選択した Issue の詳細（番号・タイトル・状態・作成者・ラベル・担当者・本文・URL）の表示、タイトルと本文の編集、状態の `open` / `closed` 切り替え、コメント一覧の表示、コメントの投稿、および自身が投稿したコメントの編集とする。
  - 選択中 Issue の会話コメント一覧は、詳細取得に伴う 1 回の取得契機で API の `Link: rel="next"` を追跡して全ページを API 順に取得する。周期的な再取得は行わない。
  - 会話コメント一覧の各 page は object 配列でなければならず、途中 page の非配列応答または非 object 要素を「コメント 0 件」や部分結果へ縮退させてはならない。応答 schema を解釈できない場合は fail-closed とする。
  - 一覧および詳細の更新は利用者の明示操作（更新ボタン）と FR-GUI-31 が定める初期取得で行い、自動ポーリングを行ってはならない。GitHub API のレート制限を不要に消費しないためである。ここでいう自動ポーリングとは、利用者の操作を伴わずに繰り返し取得する周期処理を指し、FR-GUI-31 の 1 回限りの初期取得は含まない。
  - GitHub API 呼び出しを GUI スレッドで実行してはならない。既存の QThread ワーカーの型（[cq/gui/threads.py](cq/gui/threads.py) の `succeeded` / `failed` シグナル）に従う。
  - コメント投稿・更新は応答の正の comment ID が要求対象と一致することを確認してから成功表示しなければならない。応答が object でも ID を確認できない場合は fail-closed とし、入力を消去してはならない。
  - 既存 Issue のラベル・担当者・マイルストーンの編集は FR-GUI-44 が規定する。リアクション・Projects・タイムラインイベントの編集は本要件の対象外とする。新規 Issue 作成時のラベル・担当者・マイルストーンは FR-GUI-41 が規定する。

- **FR-GUI-27**: GUI は GitHub Pull Request を閲覧し、コメントを投稿できる画面を提供しなければならない。提供範囲は、PR 一覧の取得と絞り込み（`open` / `closed` / `all`）、選択した PR の詳細（番号・タイトル・状態・作成者・head / base ブランチ・マージ状態・本文・URL）の表示、変更ファイル一覧の表示、コメント一覧の表示、およびコメントの投稿とする。
  - 選択中 Pull Request の会話コメント一覧は、詳細取得に伴う 1 回の取得契機で Issue Comments API の `Link: rel="next"` を追跡して全ページを API 順に取得する。周期的な再取得は行わない。
  - コメントは Issue Comments API による会話コメントとする。Approve / Request changes / Comment のレビュー投稿は FR-GUI-45、差分の行単位レビューコメントは FR-GUI-46 が規定する。
  - GUI からの Pull Request 新規作成は FR-GUI-42、作成後の metadata と reviewer 設定は FR-GUI-43 が規定する。既存の `--create-pr` / `--create-issues` 経路と、その経路が行う作業ブランチ作成・成果物 commit は変更しない。

- **FR-GUI-28**: FR-GUI-25〜27 および FR-GUI-30〜49 が用いる GitHub アクセスは [hve/github_api.py](hve/github_api.py) を単一の情報源としなければならない。GUI 専用の HTTP クライアント、`gh` サブプロセス呼び出し、および別の GitHub SDK を新規に導入してはならない（FR-MAINT-07）。
  - 同モジュールが既に備えるトークン解決（`GH_TOKEN` → `GITHUB_TOKEN`）、リポジトリ解決（`REPO`）、指数バックオフと `Retry-After` 準拠のリトライを再利用しなければならない。
  - `max_retries` は正の整数とし、負の `Retry-After` を待機値として使用してはならない。最終試行の rate-limit 応答後に、実行しない次試行のための待機を行ってはならない。
  - ページングに必要な場合だけ、`api_call()` は成功応答 header を呼び出し元が渡した専用 map へ複製できなければならない。既定の戻り値（JSON object / array）を変更してはならず、認証 header と応答 header を同じ変数へ格納してはならない。同名の `Link` field line が複数ある場合は受信順の comma 結合値を失わずに渡す。
  - `Link` の `rel="next"` は HTTPS かつ `api.github.com` の同一 endpoint path だけを許可する。HTTPS既定port 443の明示と省略は同一originとして正規化し、それ以外のport、userinfo、fragment、別 origin、別 endpoint、循環 cursor は API 呼び出し前または追跡中に fail-closed で拒否する。自動 redirect が別 origin を指しても `Authorization` を転送せず、GitHub token を別 host へ送信してはならない。
  - GUI 側は同モジュールの例外 `GitHubAPIError` を利用者向けメッセージへ変換する層だけを持ち、リトライ・認証・ページングを再実装してはならない。

- **FR-GUI-30**: FR-GUI-26 / FR-GUI-27 が提供する Markdown 入力欄（Issue 本文・Issue コメントの新規投稿と編集・Pull Request コメントの新規投稿）は、書式の挿入操作と描画プレビューを備えなければならない。実装は 1 つの共通ウィジェットとし、入力欄ごとに別実装を持ってはならない（FR-MAINT-07）。
  - 入力欄は Markdown の原文を保持しなければならない。編集結果をリッチテキストから Markdown へ再生成してはならない。`QTextDocument` の Markdown 往復変換は fenced code block の言語指定・タスクリスト等を保持しないため、GitHub 上の既存本文を編集保存する経路で内容を破壊するためである。
  - 書式の挿入操作は、太字・斜体・見出し・引用・インラインコード・リンク・箇条書き・番号付きリスト・タスクリストの 9 種とする。選択範囲がある場合は選択範囲へ、無い場合はキャレット位置へ Markdown 記法を挿入する。
  - プレビューは入力中の Markdown を描画して表示し、入力欄と切り替えられなければならない。Markdown から HTML への変換は [hve/gui/markdown_preview/markdown_html_renderer.py](hve/gui/markdown_preview/markdown_html_renderer.py) `MarkdownHtmlRenderer` を再利用し、GUI 側へ別の変換実装を持ってはならない（FR-MAINT-07）。
  - 画像・ファイルの添付、`@` メンション補完、`#` 参照補完、絵文字補完は本要件の対象外とする。添付に対応する公開 REST エンドポイントが [hve/github_api.py](hve/github_api.py) の単一情報源の範囲に存在せず、補完 3 種は手入力で代替できるためである。
  - プレビューの描画に Mermaid・数式・シンタックスハイライト用の外部アセットを必須としてはならない。コメント入力欄は 1 画面に複数存在しうるため、描画面の起動コストを既存のプレビュー Dock（FR 対象外）と同等に引き上げないためである。

- **FR-GUI-31**: FR-GUI-26 / FR-GUI-27 の画面は、リポジトリが確定した時点で Issue 一覧と Pull Request 一覧をそれぞれ 1 回だけ取得しなければならない。取得は画面表示時とリポジトリ適用時に限り、以後の更新は利用者の明示操作（更新ボタン）による（FR-GUI-26）。
  - FR-GUI-37 が当該 GUI セッションで HVE-created と確認した branch の具体的な PR 番号 1 件を `GET /pulls/{number}` で確認する targeted polling は、本要件が禁じる Issue / Pull Request **一覧**の自動再取得には含めない。cleanup monitor は一覧 API を呼んではならない。
  - 一覧の取得結果が 0 件の場合、絞り込み状態が `open` であることと、`all` へ切り替えて再取得できることを利用者へ提示しなければならない。取得成功と対象不在を区別できず、利用者が「取得できていない」と誤認するためである。
  - 一覧には、取得済みの一覧に対してクライアント側だけで絞り込む入力欄を設けなければならない。当該絞り込みは追加の GitHub API 呼び出しを行ってはならない。
  - 一覧の既定の絞り込み状態は `open` とする。2 ページ目以降の取得（ページング）は FR-GUI-48 が規定する。GitHub Search API による検索は本要件の対象外とする。

- **FR-GUI-32**: GUI は、実行するタスクへ関連付ける Issue と Pull Request を、それぞれ一覧から選択して指定できなければならない。関連付けは GUI session の run ID、Workflow ID、instance ID の組で分離し、別 Workflow / instance の値で上書きしてはならない（FR-GUI-40）。
  - Issue の選択結果は FR-GUI-25 が定める「連携する Issue 番号」へ反映する。FR-GUI-25 の伝達経路（`--issue-number`）を変更してはならない。
  - Pull Request の関連付けは GUI セッション内の指定に限り、Orchestrator へ伝達してはならない。新規の CLI オプション・`SDKConfig` フィールド・Cloud 経路の入力を追加してはならない。現行の Orchestrator は Pull Request を実行結果として作成する側であり、既存 Pull Request を入力として受け取る処理を持たないためである。既存設定 `linked_pr_number` は起動時の既定値として維持するが、run-scoped な関連付けの正本としては扱わない。
  - 選択のための一覧取得は FR-GUI-28 の単一情報源に従う。選択操作を提供しても、利用者が番号を直接入力する既存の経路を廃止してはならない。

- **FR-GUI-33**: GUI は、実行面に表示されているコンソール出力を、選択中の Pull Request へコメントとして投稿できなければならない。投稿は利用者の明示操作に限る。
  - 投稿本文の組み立ては副作用を持たない単独の関数として実装し、GUI から分離して検証できなければならない。
  - 本文には、投稿対象を識別できる見出しと、出力の総行数および掲載した行数を含めなければならない。掲載範囲は末尾から数えて 300 行までとし、省略が発生した場合はその旨を本文へ明記しなければならない。GitHub の Issue コメント作成 API は本文の最大長を公開していないため、全文の投稿を前提にしてはならない。
  - コンソール出力に含まれる ANSI エスケープシーケンスを除去しなければならない。また、出力本文がコードフェンス記号を含む場合でも Markdown のフェンスが閉じるよう、フェンスの長さを本文に応じて決定しなければならない。
  - 掲載行数・本文書式を変更するための CLI オプション・設定項目・環境変数を追加してはならない。全文は既存の `work/run/<run-id>/console-log.txt`（[hve/gui/page_workbench.py](hve/gui/page_workbench.py) `_write_console_log`）に保存済みであり、本要件はその要約を GitHub 上へ残す手段を補完する。
  - 本要件の「明示操作」は手動の「コンソール出力を投稿」操作を指す。FR-GUI-36 の利用者が明示的に有効化した自動進捗 Post は別契約であり、本操作を削除・自動実行へ置換してはならない。

- **FR-GUI-34**: GUI は、Pull Request の画面から現在のローカルブランチの push と、選択中 Pull Request の head ブランチのリモート削除を行えなければならない。いずれも利用者の明示操作に限る。
  - push と削除は別々の操作としなければならない。push 直後に同じブランチを削除する連続実行を既定の振る舞いにしてはならない。
  - head ブランチの削除は、選択中の Pull Request が `merged` または `closed` の場合に限り実行可能としなければならない。実行前に対象ブランチ名を含む確認を利用者へ提示し、承認された場合にだけ実行しなければならない。
  - 本画面が利用者の明示操作で削除する対象はリモート（`origin`）のブランチに限る。本画面へ手動のローカル削除操作を追加してはならない。FR-GUI-37 の自動 cleanup は例外として GUI セッション内から起動できるが、ローカル削除を GUI 側へ再実装せず、FR-CLI-34 の共通 core へ委譲しなければならない（FR-MAINT-07）。
  - リモートブランチの削除は [hve/github_api.py](hve/github_api.py) を経由しなければならない（FR-GUI-28）。push は git の 1 コマンド実行に限定し、[hve/orchestrator.py](hve/orchestrator.py) の add / commit / 保護パス検査を含む一連の処理を GUI から呼び出してはならない。当該処理は CLI 出力器と Orchestrator の実行文脈に依存するためである。
  - Pull Request 作成前の git 安全判定と明示 push は FR-GUI-42 に従う。本画面から `git add` / `git commit` を呼ばない契約は維持する。

- **FR-GUI-35**: HVE GUI は、GitHub 連携設定・Issue 操作・Pull Request 操作を、ヘッダーの `[GitHub]` から開く単一の非モーダル画面（GitHub Hub）へ集約しなければならない。
  - GitHub Hub は `連携設定` / `Issue` / `Pull Request` の 3 面を持つ。`連携設定` は既存 C5 の設定キーと [hve/gui/settings_store.py](hve/gui/settings_store.py) を再利用し、別の永続化スキーマを追加してはならない。設定画面の GitHub node と Hub 上部の重複 repository 入力は撤去し、利用者が GitHub 設定を編集する可視面を 1 箇所にしなければならない。Orchestrator 引数を構築する内部 adapter は利用者入力面ではないため保持してよい。
  - GitHub Hub の Issue 面は、既存の一覧・編集機能に加えて通常 Issue を作成できなければならない。作成項目は FR-GUI-41 に従い、Projects と Issue Form の画面再現は対象外とする。
  - Issue body は FR-GUI-30 の共通 `GitHubCommentEditor` を用い、Markdown 原文と Preview を維持する。作成は FR-GUI-28 の単一 GitHub API 実装へ委譲し、GUI thread で API を呼んではならない。成功時は一覧を更新し、作成した Issue 番号を利用者が識別できなければならない。失敗時は入力内容を消去してはならない。
  - GitHub Hub は Workflow 実行中も操作でき、FR-GUI-26 / 27 / 32 / 33 / 34 の既存機能を失ってはならない。Hub からの直接作成は FR-GUI-42 に従い、Orchestrator の既存 PR 作成経路と責務を混在させてはならない。

- **FR-GUI-36**: HVE GUI は、Workflow 実行中の進捗を関連 Issue / Pull Request へ自動 Post するかを `github_auto_post_target` で利用者が選択できなければならない。値は `off` / `issue` / `pr` / `both` の 4 値、既定は `off` とし、GitHub Hub の `連携設定` だけが可視入力を所有する。GUI セッション内の機能であるため、新規 CLI オプション、`SDKConfig` フィールド、Cloud 入力を追加してはならない。
  - Post 先 1 件につき、run ごとに進捗コメントを 1 件だけ作成し、以降は同じ comment ID を更新する。開始・各 Step の terminal 状態（`done` / `failed` / `skipped` / `blocked`）・Workflow 終了を更新契機とし、生ログ 1 行ごと、tool 呼び出しごと、token chunk ごとに Post してはならない。API request が進行中なら中間状態を queue へ積まず、最新 snapshot 1 件へ畳み込む。
  - コメント本文は副作用のない単一 formatter が構築し、run ID、Workflow / instance / Step ID、状態、既存観測イベントから得た時刻・経過時間だけを Markdown 表で記録する。token、環境変数、prompt / response / reasoning 本文、tool 引数・結果、生 SDK payload を含めてはならない。動的な表セルは pipe / 改行 / HTML 特殊文字 / backtick をエスケープする。最終更新だけ、[hve/workiq.py](hve/workiq.py) `_sanitize_diagnostic_text` で認証情報をマスクした後、FR-GUI-33 の既存 formatter で整形したコンソール末尾 300 行を付加してよい。interim 更新では `console_text` が渡されても無視しなければならない（FR-MAINT-07）。
  - 実行開始時に既存 Issue / PR が指定済みなら直ちに対象とする。Orchestrator が当該 run で新規作成する Root Issue は番号確定後から対象とする。新規 PR は post-DAG で初めて確定するため、当該 PR への自動 Post は最終更新 1 回だけとし、空 commit や早期 draft PR を本要件のために作成してはならない。
  - GitHub API 呼び出しは FR-GUI-28 の単一実装を `GitHubWorker` から使い、GUI thread で実行してはならない。Post 失敗は status へ表示するが Workflow を失敗させず、次の更新で再試行してよい。create 失敗時は comment ID 未確定のまま次回 create を再試行し、update 失敗時は既存 comment ID を保持して次回 update を再試行する。Issue / PR の一方だけが失敗しても他方の状態を変更してはならない。実行中に同種 target の番号を変更した場合、旧 comment ID を新 target へ再利用せず、新 target で新しい comment を作成する。旧 target の comment は削除しない。GUI 終了時は新規 request を停止し、実行中 worker を既存 GitHub worker と同じ上限付き手順で回収する。close 後に in-flight 完了通知が到着しても pending request を生成してはならない。
  - 手動の Issue / PR コメント、FR-GUI-33 の手動コンソール投稿、自動 Post の ON/OFF は実行中も利用できる。自動 Post を OFF にしても、既に投稿済みの GitHub コメントを削除してはならない。

- **FR-GUI-37**: `delete_local_merged_branch=True` の GUI 実行で、当該 run が新規作成したローカル作業 branch と PR 番号が確定した場合、GUI は起動中に限ってその PR 番号の状態を低頻度で確認し、マージを観測したときだけ FR-CLI-34 の共通 core へローカル cleanup を委譲しなければならない。
  - 監視対象は repository、PR 番号、branch、base branch、`created_by_hve` を持つ当該 GUI セッション内の target に限定する。`created_by_hve=False` の current branch mode、base branch と同名の branch、PR の head が別 repository の fork、head branch が不一致または不明な PR、未マージの open PR、closed-unmerged PR は削除対象外とし、git delete command を 1 回も実行してはならない。`delete_local_merged_branch=False` の場合は target を登録してはならない。
  - 状態確認は FR-GUI-28 の `get_pull_request` を `GitHubWorker` から呼び、GUI thread で GitHub API または git command を実行してはならない。同一 target の request が進行中は重複 request を開始せず、open PR と呼び出し側が retryable と分類した一時的な API 失敗だけを次の周期で再確認してよい。恒久的な API 失敗、closed-unmerged、cleanup request 生成済み、および適格性の恒久的不一致は当該 target の監視を終了する。GUI が起動している間は open PR の監視回数に別の上限を設けない。対象 PR 番号を指定した status API だけを使用し、Issue / Pull Request 一覧を周期取得してはならない。
  - 各 status request は target 登録世代を識別できなければならない。同じ PR 番号の target が別 branch へ置換された後に旧 request が完了しても、旧 target の cleanup request を生成してはならない。同一 target の重複登録は進行中requestの状態を初期化せず、cleanup request生成済みのtargetを同じGUIセッションで再登録してはならない。
  - GUI 終了時は timer を停止して新規 request を作らず、状態取得workerとcleanup workerの双方を既存 GitHub worker と同じ上限付き手順で回収する。終了後の daemon、target のディスク永続化、および次回 GUI 起動時の監視再開を追加してはならない。終了後に in-flight 完了通知が到着しても cleanup request を生成してはならない。
  - 本要件が削除するのはローカル branch だけである。remote head branch の削除は FR-GUI-34 の明示操作または GitHub repository の `Automatically delete head branches` 設定へ委ね、自動 local cleanup から remote delete API / `git push origin --delete` を呼んではならない。
  - cleanup の失敗は status として通知するが Workflow の成否を変更してはならない。GUI を merge 前に終了した場合、その後の自動 cleanup は行わない。

### 6.14 GUI 質問票のクリップボードコピー

- **FR-GUI-29**: GUI の QA 回答ダイアログ（[hve/gui/qa_answer_dialog.py](hve/gui/qa_answer_dialog.py)）は、表示中の質問票をクリップボードへ複製する操作を 2 つ提供しなければならない。1 つは質問票そのもの、もう 1 つは Work IQ（Microsoft 365）へ貼り付けるためのプロンプトとする。いずれもクリップボードへの書き込みだけを行い、Work IQ への送信・認証・MCP ツール呼び出しを行ってはならない。
  - 質問票の文字列は [hve/qa_merger.py](hve/qa_merger.py) `QAMerger.render_merged` の出力とする。GUI 側で別の整形実装を持ってはならない（FR-MAINT-07）。当該メソッドは未回答の `user_answer` を空欄として出力するため、ダイアログで入力途中の回答は含まれない。
  - Work IQ 用プロンプトは [hve/workiq.py](hve/workiq.py) `get_workiq_prompt_template("qa")` が返す既定テンプレートの `{target_content}` へ、前項の質問票文字列を埋め込んだものとする。GUI からテンプレート本文を複製してはならない（FR-MAINT-07）。利用者が設定した `--workiq-prompt-qa` の上書き値は、ダイアログが実行時設定を保持しないため適用対象外とする。
  - プロンプト全体を 1 つの Markdown として構成し、質問票をコードフェンスで囲んではならない。貼り付け先で追加の加工を要さないためである。
  - 2 つの操作は視覚的に区別できなければならない。[hve/gui/copy_button.py](hve/gui/copy_button.py) `CopyButton` は `QToolButton` を継承しており、その既定 `toolButtonStyle` が `ToolButtonIconOnly` であるため `setText("📋")` は描画されず、そのまま 2 個並べると同一外観のボタンとなる。ラベルを併記する表示形式へ設定し、支援技術向けの名前を付与しなければならない。`CopyButton` 自体の既定の表示形式を変更してはならない（他の 9 箇所の呼び出しはアイコンのみを意図しているため）。
  - コピー対象の文字列を組み立てる処理は例外を送出してはならない。`CopyButton` はクリック時の例外を捕捉してエラー文字列をクリップボードへ書き込むため、利用者が当該文字列を貼り付け先へ送る経路を作らないためである。
  - `CopyButton` がクリック後に表示する一時的な tooltip は現状ハードコードされた日本語であり、本要件では国際化の対象としない。当該文言を変更すると他の 9 箇所の呼び出しへ同時に影響するため、既知の制約として扱う。
  - 質問が 0 件の場合、両操作を無効化しなければならない。送信対象の質問が存在せず、空の内容を複製する誤操作を防ぐためである。
  - 本要件のために新規の CLI オプション・設定項目・環境変数・IPC スキーマ変更を追加してはならない。既存の回答送信（`Submit`）・キャンセル・既定値採用の各シグナルと、GUI ↔ CLI の回答形式（FR-GUI-08）を変更してはならない。
  - 本要件は FR-QA-03 が定める Work IQ の自動統合経路を置き換えるものではない。自動統合を無効にしている利用者が、同じ質問票を手動で Work IQ へ問い合わせる手段を補完する。
  - 本操作が生成する文字列は、次の点で FR-QA-03 の自動経路が送信する内容と一致しない。差異を利用者向けドキュメントへ明記しなければならない。
    - 自動経路（[hve/runner.py](hve/runner.py)）は質問を 1 件ずつ送り、`- No:` / `- 質問:` / `- 分類:` / `- 重要度:` / `- 既定値候補:` の箇条書きを `target_content` とする。本操作は全問を 1 つの Markdown テーブルとして渡す。
    - 自動経路は `_filter_workiq_questions` により重要度で絞り込み、`workiq_max_draft_questions`（既定 10）で件数を制限する。本操作は表示中の全質問を対象とし、絞り込みを行わない。
    - 既定テンプレートは応答を最大 5 件に制限するため、質問数にかかわらず返る件数は 5 件までとなる。
  - `QAMerger.render_merged` の出力は先頭に質問票のタイトル（`# `）を含み、既定テンプレートでは `### 質問一覧` の配下へ埋め込まれるため、見出しレベルが逆転する。また表セル内の改行を `<br>`、pipe を `&#124;` へ変換する。いずれも Markdown 構文として不正ではないため、専用の整形実装を新設せず既知の制約として扱う。

### 6.15 GUI からの進捗再実行

- **FR-GUI-38**: GUI は `FR-CLI-86` の legacy `--resume-run <run-id>` を指定できなければならない。入力欄は Advanced 領域へ `Legacy run-id` として 1 つ置き、空欄または空白のみのときは当該オプションを子プロセスへ渡してはならない。
  - run-id の実在確認・一覧取得・自動選択を GUI 側で行ってはならない。記録が無い run-id は `FR-CLI-86` が fail-closed で停止する契約であり、GUI が事前判定を持つと同じ規則の実装が 2 箇所になる（FR-MAINT-07）。
  - 入力値は既存の設定ストアで保存・復元しなければならない。保存キーは `resume_run` とする。
  - 本要件は `FR-CLI-86` が読む既存 `hve/.run-progress.jsonl` の Workflow 進捗だけを対象とし、FR-STATE-04 の SQLite execution や §5.6 が全廃した `state.json` / `config_snapshot` 復元と同じ機能として利用者向けドキュメントへ記述してはならない。
  - 新規の CLI オプション・`SDKConfig` フィールド・環境変数を追加してはならない。
  - 契約テスト: [hve/gui/tests/test_orchestrate_args.py](hve/gui/tests/test_orchestrate_args.py)
### 6.16 GitHub Issue / Pull Request タイトルの自動生成

- **FR-GUI-39**: HVE GUI は、GitHub Issue または Pull Request を作成するとき、GitHub Copilot CLI へ本文コンテキストを問い合わせて簡潔なタイトルを自動生成できなければならない。タイトル生成は [hve/github_title_generator.py](hve/github_title_generator.py) の単一実装へ集約し、Issue 面と Orchestrator の PR 作成経路が同じ実装を使わなければならない（FR-MAINT-07）。
  - Issue 面には利用者が明示的に再生成できる操作を置く。title が空で body が空でない状態で **[Issue を作成]** を押した場合は、タイトル生成に成功してから Issue 作成を継続する。利用者が入力済みの空でない title は自動的に上書きせず、そのまま使用する。明示的な再生成操作だけは既存 title を置き換えてよい。body が空または空白のみの場合は Copilot CLI を呼んではならない。
  - GUI から `create_issues=True` で起動した Orchestrator が新規 Root Issue を作成する場合も、Root Issue body から title を生成する。利用者が `issue_title` を明示した場合は生成せず、その値を保持する。Sub-Issue は Step ID / Step title という決定的な識別子を必要とするため、本要件の生成対象外とする。
  - GUI から起動した Orchestrator（既存の `HVE_GUI_SESSION_ID` が非空の子プロセス）が PR を作成する直前にタイトルを生成する既存経路に加え、FR-GUI-42 の直接作成面では利用者の明示操作でタイトルを生成できる。直接作成面で入力済みの title は自動上書きせず、生成失敗時はフォーム入力を保持して PR を作成しない。CLI 単独実行と Cloud 実行の既存タイトルは変更しない。Orchestrator の生成失敗時は従来の決定的タイトルへフォールバックし、draft checkpoint の識別 suffix を保持する。
  - Copilot CLI は空の一時作業ディレクトリから非対話モード（`-p` / `--silent` / `--stream off` / `--no-color` / `--no-custom-instructions` / `--no-ask-user`）で起動する。`--available-tools=ask_user` と `--no-ask-user` を併用して実行可能 tool を 0 件に制限し、shell を介さず、固定 timeout 付きで実行する。モデルは `auto` とし、同モデルと互換性がない `--effort` は指定しない。汎用チャットの対話セッションを規定する FR-GUI-10 / FR-GUI-11 は変更しない。
  - CLI へ渡してよいのは target 種別、既存の fallback title、必須 prefix、および最大 12,000 文字へ制限した Issue / PR 本文だけとする。repository、token、環境変数、prompt / response ログ、tool 入出力を追加してはならない。本文は信頼できないデータとして区切り、本文中の命令を無視するよう生成プロンプトに明記する。
  - 応答は改行・Markdown prefix・引用符を除去した 1 行へ正規化し、最大 120 文字とする。空応答、非 0 終了、timeout、CLI 不在は失敗とする。Issue 面では入力を保持してエラーを表示し、Issue を作成しない。生成中は title / body / 生成 / 作成操作を無効化し、GUI thread で Copilot CLI を実行してはならない。
  - 本要件のために新規設定キー、CLI オプション、`SDKConfig` フィールド、環境変数を追加してはならない。タイトル生成の明示操作または空 title での Issue 作成、および GUI 起動の PR 作成は、GitHub Copilot の token / premium request を消費し得る。
  - 契約テスト: [hve/tests/test_github_title_generator.py](hve/tests/test_github_title_generator.py)、[hve/gui/tests/test_github_issue_title_generation.py](hve/gui/tests/test_github_issue_title_generation.py)、[hve/tests/test_orchestrator_github_title_generation.py](hve/tests/test_orchestrator_github_title_generation.py)

### 6.17 GUI の GitHub task 関連付けと作成操作

- **FR-GUI-40**: GitHub Hub は現在の task に関連付けられた repository、Issue 番号、Pull Request 番号、head / base branch、関連付け元を表示しなければならない。状態は `(GUI session run ID, workflow ID, instance ID)` を key とするメモリ内状態とし、新しい永続化形式を追加してはならない。
  - Hub が表示する current task は、Workflow 未実行時は session default、実行中は直近に `github_target` を通知した Workflow / instance とする。履歴選択 UI は設けず、Hub は `workflow_id` / `instance_id` / Issue / Pull Request / branch / source を 1 組として受け取る。
  - 手動選択、Hub での作成成功、および FR-RTO-08 の `github_target` event を同じ表示へ反映する。`github_target` が同一 Workflow / instance の provisional な手動値を更新しても、別 Workflow / instance の値を変更してはならない。
  - Workflow 実行前に関連付けた Issue は FR-GUI-25 の `--issue-number` へ snapshot する。実行開始後の手動変更は Hub の追跡先と FR-GUI-36 の将来の Post 先だけを変更し、起動済み Orchestrator の Root Issue を変更してはならない。
  - 既存の `linked_pr_number` は GUI 起動時の既定値として読み取るが、Orchestrator へ渡さず、run-scoped 状態の更新を設定へ自動保存してはならない。token、本文、URL、prompt、response を関連付け状態へ保存してはならない。
  - 契約テスト: [hve/gui/tests/test_github_task_context.py](hve/gui/tests/test_github_task_context.py)、[hve/gui/tests/test_main_window_github_task_wiring.py](hve/gui/tests/test_main_window_github_task_wiring.py)

- **FR-GUI-41**: GitHub Hub の Issue 作成面は、空でない title、任意の Markdown body、labels、assignees、milestone を指定して通常 Issue を作成できなければならない。Projects と GitHub Issue Form の field / upload / required validation の再現は対象外とする。
  - labels と assignees は複数指定、milestone は未指定または 1 件とする。候補一覧は [hve/github_api.py](hve/github_api.py) の REST 実装から `GitHubWorker` で先頭 100 件だけを取得し、取得済み候補の絞り込みで追加 API request を行ってはならない。ページング UI と全件取得は対象外とする。
  - title が空で body が空でない場合は FR-GUI-39 の生成を経て作成する。title が空で body も空の場合は作成しない。title が空でなければ body が空でも作成できなければならない。
  - 「作成後、この task に関連付ける」は既定 ON とし、成功した Issue 番号を FR-GUI-40 へ反映する。API 失敗時は全入力を保持し、作成成功後に GitHub が requested metadata を反映しなかった場合は Issue 番号を保持したまま警告し、Issue を再作成してはならない。
  - 契約テスト: [hve/tests/test_github_api_issue_metadata.py](hve/tests/test_github_api_issue_metadata.py)、[hve/gui/tests/test_github_service_issue_metadata.py](hve/gui/tests/test_github_service_issue_metadata.py)、[hve/gui/tests/test_github_issue_creation_parity.py](hve/gui/tests/test_github_issue_creation_parity.py)

- **FR-GUI-42**: GitHub Hub の Pull Request 面は、現在のローカル branch を head とし、選択した base branch に対して normal または draft Pull Request を直接作成できなければならない。title は必須、Markdown body は任意とし、repository root の既定 Pull Request template が存在して body が未編集なら初期値として用いる。
  - 作成前に detached HEAD、head と base の同一、`base...head` の commit 差分 0、dirty worktree、同じ head / base の open Pull Request を検出して fail-closed とする。GUI から `git add` / `git commit` を行ってはならない。
  - head が origin に未公開、または local に未 push commit がある場合は件数と branch を表示し、利用者の明示操作による既存 push 経路を経た後にだけ作成する。自動 push や push なしの作成を行ってはならない。
  - close-on-merge は Pull Request 作成面だけが所有する保存しない checkbox とし、既定 OFF とする。base が repository default branch で利用者が明示的に ON にした場合だけ `Closes #N` を body へ追加する。default branch 以外では plain `#N` reference とし、自動 close を約束してはならない。既存の `enable_auto_merge` とは無関係である。
  - 作成成功時は Pull Request 番号を直ちに FR-GUI-40 へ反映し、一覧更新後に当該 Pull Request を選択する。作成中は再送信を禁止し、timeout 後も無条件に create を再試行してはならない。
  - 契約テスト: [hve/gui/tests/test_git_ops_preflight.py](hve/gui/tests/test_git_ops_preflight.py)、[hve/tests/test_github_api_pr_creation.py](hve/tests/test_github_api_pr_creation.py)、[hve/gui/tests/test_github_pr_creation.py](hve/gui/tests/test_github_pr_creation.py)

- **FR-GUI-43**: FR-GUI-42 の Pull Request 作成面は labels、assignees、milestone、および reviewer users / teams を指定できなければならない。Pull Request 本体の作成と作成後 metadata 操作を別の結果として扱い、本体作成後の metadata / reviewer 失敗を Pull Request 作成失敗として表示してはならない。
  - 本体作成成功時点で Pull Request 番号と URL を保持する。後処理に失敗した場合は失敗項目を警告し、後処理だけを再試行可能とし、Pull Request 本体を再作成してはならない。
  - reviewer users と team slugs は GitHub REST API の別 field として送信する。Projects v2、native Auto-merge、merge queue、fork / cross-repository head は対象外とする。
  - 契約テスト: [hve/tests/test_github_api_review_requests.py](hve/tests/test_github_api_review_requests.py)、[hve/gui/tests/test_github_pr_creation_metadata.py](hve/gui/tests/test_github_pr_creation_metadata.py)

- **FR-GUI-44**: GitHub Hub の Issue 面は、選択中の既存 Issue の labels、assignees、milestone を編集できなければならない。
  - 候補は FR-GUI-41 の Issue 作成面が取得済みの metadata を再利用し、編集面の表示・保存を理由に追加の候補取得 API request を発行してはならない。候補が未取得の場合は取得操作を利用者へ案内し、推測値を表示してはならない。
  - 更新は利用者の明示操作に限る。API 引数が `None` の項目は payload へ含めず、指定した項目だけを置換する。labels / assignees の空配列は全解除として送信し、milestone の「未設定」は GitHub API の `null` へ明示変換する。
  - 更新失敗時は入力と選択を保持する。成功時は返却された Issue の metadata を表示へ反映し、反映されなかった指定項目があれば Issue を再作成せず警告する。
  - 更新応答は要求した Issue 番号と、要求した metadata field の存在・型を確認しなければならない。全解除要求に対して field 自体が欠落した応答を、空配列または `null` が返されたものと推測して成功扱いしてはならない。
  - metadata 保存中は、同じ Issue の title / body / state / comment および新規 Issue 作成の mutation を開始してはならない。
  - 契約テスト: [hve/tests/test_github_api_issue_update_metadata.py](hve/tests/test_github_api_issue_update_metadata.py)、[hve/gui/tests/test_github_service_issue_update_metadata.py](hve/gui/tests/test_github_service_issue_update_metadata.py)、[hve/gui/tests/test_github_issue_metadata_edit.py](hve/gui/tests/test_github_issue_metadata_edit.py)

- **FR-GUI-45**: GitHub Hub の Pull Request 面は、選択中 Pull Request の review 一覧を表示し、`APPROVE` / `REQUEST_CHANGES` / `COMMENT` の review を提出できなければならない。
  - review 一覧は利用者の明示操作または選択した Pull Request の詳細取得に伴う 1 回の取得に限り、自動ポーリングしてはならない。1 回の取得契機で API の `Link: rel="next"` を追跡して全ページを取得し、GitHub API が返す時系列順を維持する。
  - `REQUEST_CHANGES` と `COMMENT` は空でない body を必須とし、`APPROVE` は body を省略できる。3 値以外の event は API 呼び出し前に fail-closed で拒否する。
  - 提出は既存の `GitHubCommentEditor` を再利用し、GUI thread で API を呼ばない。失敗時は入力内容と選択した event を保持する。
  - review 提出中は、同じ Pull Request の会話 comment、console comment、行単位 review comment、push、head branch 削除の mutation を開始してはならない。
  - 契約テスト: [hve/tests/test_github_api_pr_reviews.py](hve/tests/test_github_api_pr_reviews.py)、[hve/gui/tests/test_github_service_pr_reviews.py](hve/gui/tests/test_github_service_pr_reviews.py)、[hve/gui/tests/test_github_pr_reviews_ui.py](hve/gui/tests/test_github_pr_reviews_ui.py)

- **FR-GUI-46**: GitHub Hub の Pull Request 面は、選択中 Pull Request の review comment 一覧を表示し、変更ファイルの diff 行へ review comment を投稿できなければならない。
  - review comment 一覧は、ダイアログを開く利用者の明示操作を取得契機として API の `Link: rel="next"` を追跡して全ページを取得し、API 順序を維持する。周期的な再取得は行わない。
  - [hve/github_api.py](hve/github_api.py) の Pull Request Files API 応答は、既存の G-DIFF 用 `filename` / `status` / `previous_filename` に加えて GitHub が返した `patch` を保持する。`patch` が無いファイルへ行番号を推測してはならない。
  - 投稿対象は取得済み `patch` から利用者が選択した `path` / `line` / `side` と、選択中 Pull Request の `head.sha` を `commit_id` として確定する。`side` は `LEFT` / `RIGHT` の 2 値、`line` は正の整数、body / path / commit_id は空でないことを API 呼び出し前に検証する。廃止予定の `position` は使用しない。
  - 投稿は利用者の明示操作に限り、失敗時は入力と行選択を保持する。diff 全体を汎用ビューアへ拡張せず、本要件に必要な最小表示に留める。
  - 契約テスト: [hve/tests/test_github_api_pr_review_comments.py](hve/tests/test_github_api_pr_review_comments.py)、[hve/gui/tests/test_github_service_pr_review_comments.py](hve/gui/tests/test_github_service_pr_review_comments.py)、[hve/gui/tests/test_github_review_comment_dialog.py](hve/gui/tests/test_github_review_comment_dialog.py)

- **FR-GUI-47**: GitHub Hub の Pull Request 面は、選択中 Pull Request の head commit に対する check-runs を表示し、利用者の明示確認後に Pull Request をマージできなければならない。
  - check-runs 取得は [hve/github_api.py](hve/github_api.py) の既存 `list_check_runs_for_ref()` を再利用し、選択中 Pull Request の `head.sha` を ref とする。自動ポーリングは行わず、利用者の明示的な更新操作だけで取得する。
  - check-run が未完了、または conclusion が `success` / `neutral` / `skipped` 以外のものを 1 件でも含む場合、マージ操作は既定で無効とする。check-runs を取得していない、応答を解釈できない、または head SHA が不明な場合も fail-closed とする。
  - merge method は `merge` / `squash` / `rebase` の 3 値だけを許し、確認ダイアログに Pull Request 番号、head / base branch、merge method を表示する。同期 merge endpoint を用い、native Auto-merge と merge queue は本要件の対象外とする。
  - API の 405 / 409 を利用者が再判断できるメッセージへ変換し、失敗時にマージ済みと表示してはならない。
  - merge API が失敗した場合、または成功を確認できない応答を返した場合は、取得済み check-runs を破棄し、再取得するまでマージ操作を再度有効化してはならない。
  - 契約テスト: [hve/tests/test_github_api_pr_merge.py](hve/tests/test_github_api_pr_merge.py)、[hve/gui/tests/test_github_service_pr_merge.py](hve/gui/tests/test_github_service_pr_merge.py)、[hve/gui/tests/test_github_pr_merge_ui.py](hve/gui/tests/test_github_pr_merge_ui.py)

- **FR-GUI-48**: GitHub Hub の Issue / Pull Request 一覧は、利用者の明示操作で 2 ページ目以降を取得し、取得済み一覧へ追記できなければならない。
  - 初回 request は `sort=created&direction=desc` とし、既存項目の更新が取得済みページの並びを移動させない安定キーを用いる。新規作成物を page 1 に含め、FR-GUI-35 / 42 の作成後選択契約を維持する。同時の新規作成による前方挿入と state 変更・削除による母集合の変化は snapshot API が無いため防げないので、最新状態の確定には page 1 からの明示更新を案内する。
  - GitHub API の `page` は後方互換の直接呼び出し用として 1 以上の整数を引き続き受理する。ただし GUI の「さらに読み込む」と、1 回の取得で全ページを集約する API は手組みした `page=N` ではなく、応答 `Link` の検証済み `rel="next"` URLだけを継続 cursorとして使用する。
  - `Link` parser は quoted-string 内の comma / semicolon をparameter境界として扱わず、quoted-pair を unquote してから relation type を解釈する。RFC 8288 に従い、同一link-valueで2個目以降の`rel`は拒否せず無視して先頭値だけを採用する。pagination application が `anchor` を適用できないlink-valueは丸ごと無視し、複数の`rel="next"` URLは曖昧な応答としてfail-closedで拒否する。HTTP listの空要素は合理的な範囲で無視する。
  - Issue / Pull Request page の各項目は正の整数 `number` を必須とし、非 object、番号欠落、bool、非正数を含む page は取得済み状態へ反映する前に fail-closed で拒否する。
  - UI は「さらに読み込む」操作だけを提供し、無限スクロール、自動先読み、自動ポーリングを実装してはならない。request 中の二重送信を禁止し、成功応答が返した次 cursorだけを保存する。追加取得失敗時は同じ cursorを保持して再試行可能とし、page 1更新・repository変更・state変更時は古い cursorを破棄する。一覧 request と同じ対象の詳細取得・コメント投稿・Issue 更新は互いの正常な応答を失効させてはならず、各 request の対象 context と世代を独立に検証する。
  - 追記後も FR-GUI-31 のクライアント側絞り込みを全取得済み項目へ適用する。同じ番号の重複は初出を保持して除去し、検証済み `rel="next"` が無い場合は取得件数に関係なく「さらに読み込む」を無効化する。
  - 契約テスト: [hve/tests/test_github_api_list_pagination.py](hve/tests/test_github_api_list_pagination.py)、[hve/gui/tests/test_github_service_pagination.py](hve/gui/tests/test_github_service_pagination.py)、[hve/gui/tests/test_github_issue_pagination.py](hve/gui/tests/test_github_issue_pagination.py)、[hve/gui/tests/test_github_pr_pagination.py](hve/gui/tests/test_github_pr_pagination.py)

- **FR-GUI-49**: GitHub Hub の Issue 面は、選択中 Issue を Copilot cloud agent へ割り当てられなければならない。
  - 割当は利用者の明示操作と確認に限る。確認には Issue 番号、対象 repository、base branch を表示し、入力または対象を特定できない場合は fail-closed とする。
  - REST payload は `assignees: ["copilot-swe-agent[bot]"]` と `agent_assignment.target_repo` を持つ。`base_branch` が空または未指定のときは当該 field を送信しない。Agent Tasks API は使用しない。
  - 割当 API は public preview で変更され得る旨と、必要な token 権限を利用者へ表示する。失敗時は Issue 選択と入力を保持し、成功したと推測して表示を変更してはならない。
  - 契約テスト: [hve/tests/test_github_api_copilot_assign.py](hve/tests/test_github_api_copilot_assign.py)、[hve/gui/tests/test_github_service_copilot_assign.py](hve/gui/tests/test_github_service_copilot_assign.py)、[hve/gui/tests/test_github_issue_copilot_assign.py](hve/gui/tests/test_github_issue_copilot_assign.py)

- **FR-GUI-50**: GUI Plan mode は FR-LOCAL-SURFACE-02 の共通 planを用いる明示 Resume dialog と、normal planのdurable登録・resume child launchを提供しなければならない。
  - dialog は利用者が Resume 操作を選んだときだけ開き、常設history pageを追加してはならない。candidate 0件、safe確認、risk action、missing replay values、stale CAS、unsupported modeを共通serviceの結果どおり表示する。
  - normal Startごとにqueue全体を1 transactionで登録し、同じGUI windowの別jobへ同じexecution IDを再利用してはならない。全childは登録済みdescriptorとinternal identityをmodel/session開始前に照合する。
  - normal Start は current HEAD を取得できない場合に登録・child 起動前に停止する。resume processは既存Workbenchのlog/stop/finish経路へ合流し、別のprocess lifecycleを実装してはならない。graceful stopでは NFR-REL-03 のsuspend/final heartbeat規則を守る。
  - GUI subprocess launcher が補完する `--workbench off` は `orchestrate` child だけに適用する。公開 resume controller の引数だけを受理する `hve resume` child へ同 option を注入してはならない。
  - queue 内の argv 構築失敗・process 起動失敗・非 0 child は Workflow を失敗表示にする。queue 全体の return code は先行失敗を後続成功で隠さず、最初の非 0 を parent へ返す。完了した reader / QA manager は停止処理後に Qt object の破棄を予約し、reader thread の終了を確認してから参照を解放する。
  - dialogは選択済み`ResumePlan`と再入力値を別々に返し、Workbenchは`hve resume`を`--expected-resume-hash`付きで起動する。再入力値をdurable storeへ保存してはならない。
  - 再入力平文は child process 起動に必要な期間だけ保持し、起動後に dialog、Workbench の explicit argv queue、および保持している process argv list から破棄する。後続 Workflow や次回 dialog へ流用してはならない。
  - FR-GUI-38のLegacy run-idと新しいexecution IDを同じ入力欄で多重解釈してはならない。
  - 契約テスト: [hve/gui/tests/test_resume_dialog.py](hve/gui/tests/test_resume_dialog.py)、[hve/gui/tests/test_gui_subprocess_stdin.py](hve/gui/tests/test_gui_subprocess_stdin.py)

---

## 7. 非機能要件

| ID | 要件 |
|---|---|
| NFR-PERF-01 | DAG 実行は `asyncio.Semaphore` を使い、FR-DAG-03 の解決順序で得た並列上限（宣言値: AKM / ADI は 21、ARD は 15、ASDW-WEB は 1。宣言のない Workflow は `--max-parallel` の値で既定 15）を超えない |
| NFR-PERF-02 | 既存成果物走査は `src/` 50 件、`test/` 30 件で早期打ち切る。**ハードコード値であり、設定では変更不可** |
| NFR-PERF-03 | 性能の測定方法 / 目標値（KPI、SLA）は未定義（§12 TBD）|
| NFR-OBS-01 | Wave 2 コンテキスト注入計測（`none_steps` / `total_chars` / `max_chars` / `phase_breakdown` / `self_improve_scope`）を Console / stderr に出力する。`GITHUB_STEP_SUMMARY` 環境変数が設定されている場合に限りサマリにも出力。`OSError` 時は警告のみで継続 |
| NFR-OBS-02 | Fork-on-retry が有効な場合のみ `ForkKPILogger` を構築し、無効時は `None` を返してオーバーヘッドを排除する |
| NFR-OBS-03 | `--verbosity` で `quiet` / `compact` / `normal` / `verbose` を切替可能。既定は `compact` |
| NFR-OBS-05 | `Console.error()` / `Console.warning()` の出力行は、`_CURRENT_EMIT_STEP_ID` が設定されている GUI サブプロセス実行時に `[hve:ctx:<step_id>] ` インラインマーカーを付与する。ERROR / WARN だけがマーカーを持たないために GUI が直前の実行中 Step へ誤帰属する事象を防ぐ。`Console.step_end()` は当該 ContextVar を解除し、Step 完了後の行を完了済み Step へ帰属させない |
| NFR-OBS-06 | GUI の「実行中の課題」への指摘検知は、Agent の自由記述に対する部分文字列一致で行わない。`hve/prompts.py` の重大度テーブル（Critical / Major / Minor）に整合する構造化行だけを対象とし、判定前に `[hve:ctx:<step_id>] ` マーカーを除去して正規化する |
| NFR-OBS-07 | 同一 Step・同一ツールの失敗が後続ターンで成功した場合、GUI は当該課題を解決済みへ降格する。回復済みの一時失敗を未解決の ERROR として残置しない |
| NFR-OBS-08 | Step 実行の包括例外ハンドラは、例外メッセージだけでなく例外型名を出力する。原因不明のまま反復する失敗を防ぐ |
| NFR-OBS-09 | GUI のログ 1 行取り込みは UI スレッド上の処理量を最小化する。(1) ローテーションログの永続化は開いたファイルハンドルを保持して追記し、1 行ごとの `open` / `close` を行わない。追記直後に外部から内容を読めるよう 1 行ごとに flush する。(2) 画面非表示の `_LogPane` が持つ `QPlainTextEdit` へは追記しない。画面表示は `LogTabsWidget` が担い、`console-log.txt` は同ウィジェットの全文を正本とする。ログのキーボードスクロール操作も表示中のウィジェットを対象とし、非表示ウィジェットを操作しない。(3) 表示中ログタブの末尾追従は、同一イベントループ内の連続追記を 1 回へ合体させる。(4) 「実行中の課題」ペインは、生成した表示テキストが前回と同一の場合に `setPlainText` を実行しない。NFR-OBS-07 による課題の降格は表示テキストの変化として検出されるため、本条件下でも画面へ反映される。表示行数の上限は設けない（`console-log.txt` の全文性を損なうため） |
| NFR-COMP-01 | ~~旧 step_id（ARD の `1, 2, 3` 等）からの resume は warning + 新規実行扱いとする~~ → **廃止（v1.1）**: Resume 機能全廃に伴い削除 |
| NFR-COMP-02 | SDK バージョン < 0.3.0 互換のため、`reasoning_effort` 未サポート例外をハンドリングして再試行する |
| NFR-TIME-01 | CLI の既定 idle タイムアウトは 21,600 秒（6h）、Code Review Agent レビュー待ちは 7,200 秒（2h）。**CLI は無入出力時間ベース** |
| NFR-TIME-02 | Cloud Orchestrator の AKM ジョブタイムアウトは 360 分、`detect` / `suggest-next` ジョブは 15 分。**Cloud は GitHub Actions の `timeout-minutes`（経過時間ベース）** |
| NFR-A11Y-01 | CLI は `--screen-reader` で絵文字を日本語ラベルに置換、スピナーを無効化、`NO_COLOR` 環境変数（no-color.org 規格）に従う |
| NFR-RTO-01 | 実行時観測イベント 1 件あたりの追加処理は、既存の GUI ログ 1 行取り込み性能（NFR-OBS-09）を悪化させない。計測方法と実測値を変更時に記録する |
| NFR-RTO-02 | GUI / Autopilot が依存する `[hve:stats]` の既存 `kind` と既存キーは後方互換を維持する。実行時 Observability の追加に伴い、新規 CLI オプションおよび新規 `SDKConfig` フィールドを追加してはならない |
| NFR-RTO-03 | 実行時観測の記録および表示の失敗は Workflow 実行を失敗させない。表示は既存の `HVE_NO_STATUSLINE` / `HVE_NO_WORKBENCH` で停止でき、記録は作業ルート未設定時に無効化される |
| ~~NFR-CONC-01（v0.6 新規）~~ | **廃止（v1.1）**: `RunLock` を含む Resume 機能全廃に伴い削除 |
| ~~NFR-PERF-04（v0.6 新規）~~ | **廃止（v1.1）**: `RunLock` を含む Resume 機能全廃に伴い削除 |
| ~~NFR-REL-01（v0.8 新規）~~ | **廃止（v1.1）**: `delete --hard` / 起動時 recovery を含む Resume 機能全廃に伴い削除 |
| ~~NFR-REL-02（v0.9 新規）~~ | **廃止（v1.1）**: Resume 開始時 `reconcile_run` を含む Resume 機能全廃に伴い削除 |
| ~~NFR-OBS-04（v1.0 新規）~~ | **廃止（v1.1）**: checkpoint journal 記録を含む Resume 機能全廃に伴い削除 |

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

`SDKConfig` を介して以下を保持する（[hve/config.py](hve/config.py) `SDKConfig` クラス定義を正とする）。本セクションは主要グルーピングのみを示す（v1.0.4 で TBD-02 を解消）:

- **モデル**: `model` / `review_model` / `qa_model` / `model_override`
- **並列・タイムアウト**: `max_parallel`、`timeout_seconds`、`review_timeout_seconds`、`qa_input_timeout_seconds`
- **認証・リポジトリ**: `github_token` / `repo`（環境変数優先）
- **CLI / MCP**: `cli_path` / `cli_url` / `mcp_servers`
- **Git / PR**: `create_issues` / `create_pr`、`issue_number`（FR-GUI-25）、`base_branch`、`ignore_paths`、`review_base_ref`
- **コンテキスト制御**: `reuse_context_filtering`、`require_input_artifacts`、`context_injection_max_chars`（既定 20,000）、`max_diff_chars`
- **自動レビュー**: `auto_qa` / `auto_contents_review` / `auto_coding_agent_review` / `auto_coding_agent_review_auto_approval`、`qa_answer_mode` / `qa_auto_defaults` / `force_interactive`
- **Self-Improve**: `auto_self_improve` / `self_improve_scope` / `self_improve_target_scope` / `self_improve_goal` / `self_improve_skip` / `self_improve_max_iterations` / `self_improve_quality_threshold` / `self_improve_max_tokens` / `self_improve_max_requests` / `tdd_max_retries`
- **Work IQ**: `workiq_enabled` / `workiq_qa_enabled` / `workiq_akm_review_enabled` / `workiq_akm_ingest_enabled` / `workiq_akm_ingest_dxx` / `workiq_draft_mode` / `workiq_draft_output_dir` / `workiq_per_question_timeout` / `workiq_max_draft_questions` / `workiq_priority_filter`
- **コンソール出力**: `verbose` / `quiet` / `show_stream` / `show_reasoning` / `log_level` / `verbosity` / `no_color` / `show_banner` / `screen_reader` / `timestamp_style` / `final_only`
- **Agentic Retrieval**: `enable_agentic_retrieval` / `agentic_data_source_modes` / `foundry_mcp_integration` / `agentic_data_sources_hint` / `agentic_existing_design_diff_only` / `foundry_sku_fallback_policy`
- **Fork / 実行セッション**: `fork_on_retry`、`run_id`、`session_id_prefix`、`apply_qa_improvements_to_main` / `apply_review_improvements_to_main` / `apply_self_improve_to_main`、`unattended`、`dry_run`、`additional_prompt`

完全なフィールド一覧は [hve/config.py](hve/config.py) `SDKConfig` クラス定義を正とする。Resume 用 snapshot とその復元契約は §5.6 のとおり廃止済みである。

### 8.3 セッション永続化フォーマット（廃止）

- v1.1 で `state.json` / `.lock` / Resume 用 `journal.jsonl` / `session-state/` を含むセッション永続化フォーマットを全廃した。現行の永続化スキーマは存在しない。
- [hve/run_state.py](hve/run_state.py) は SDK セッション ID 生成ヘルパー、[hve/run_journal.py](hve/run_journal.py) は markdown-query 利用ログの読み取りヘルパーとして存続する。いずれも Resume 用 Run State / Intent Journal ではない。
- v0.5〜v1.0 の旧フォーマットは §11 の改訂履歴にのみ記録し、現行要件として適用しない。

---

## 9. 制約・前提

- **C-01**: 本書の説明的基線は `main` ブランチ時点（2026-05-12 確認）のソースから機械的に抽出した内容に限定する。後日追加された規範要件は §1.3 の優先順位に従い、未確認の挙動は §12 TBD に記載する。
- **C-02**: Workflow ID 表記の正は [hve/workflow_registry.py](hve/workflow_registry.py)（`.github/copilot-instructions.md` 準拠）。
- **C-03**: `docs-original/` は読み取り専用。書き込みは想定しない。
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
- [hve/github_api.py](hve/github_api.py)
- [users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md)
- [users-guide/hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md)
- [users-guide/web-ui-guide.md](users-guide/web-ui-guide.md)
- [hve/run_state.py](hve/run_state.py)（SDK セッション ID 生成ヘルパー）、[hve/run_journal.py](hve/run_journal.py)（markdown-query 利用ログ読み取りヘルパー）。旧 Resume 専用の `run_lock.py` / `recovery.py` / `reconciler.py` は v1.1 で削除済み。

---

## 11. 改訂履歴

| バージョン | 日付 | 内容 |
|---|---|---|
| 0.1 | 2026-05-12 | 初版（ソースコードから逆抽出） |
| 0.2 | 2026-05-12 | 敵対的レビュー指摘の Critical / Major 修正反映 |
| 0.3 | 2026-05-12 | §13 ワークフロー別仕様（生成ファイル詳細）を追加 |
| 0.4 | 2026-05-12 | §13 関連 TBD 調査結果を反映（テンプレ実体に基づき生成ファイルパスを訂正）、廃止した旧独立原本質問票処理の Step 1 テンプレを fan-out 構成に整合 |
| 0.5 | 2026-05-12 | Resume 2 層トランザクション保護（Phase 1）を反映。`schema_version` を 1.0 → 2.0 へ bump。FR-CLI-40 / 43 を改訂し、FR-CLI-44 を新規。§8.3 を保存タイミング・新フィールド付きで更新。§12 に TBD-15 追加 |
| 0.6 | 2026-05-12 | Resume 2 層トランザクション保護（Phase 2）を反映。`hve/run_lock.py` による run_id 単位クロスプロセスロックを FR-CLI-45 として新規、NFR-CONC-01 / NFR-PERF-04 を追加。§8.3 に `.lock` ファイル仕様を追加 |
| 0.7 | 2026-05-12 | Resume 2 層トランザクション保護（Phase 3）を反映。`hve/run_journal.py` による Write-Ahead Intent Journal を FR-CLI-46 / 47 として新規。§8.3 に journal kind 一覧と archive / rotate 保持先を追加 |
| 0.8 | 2026-05-12 | Resume 2 層トランザクション保護（Phase 4）を反映。`resume delete --hard` を journal-based crash-safe 化し FR-CLI-42 を再改訂、FR-CLI-48 を新規。起動時 recovery (`hve/recovery.py`) を `__main__` に統合し、`HVE_DISABLE_STARTUP_RECOVERY` を追加。NFR-REL-01 を新規 |
| 0.9 | 2026-05-12 | Resume 2 層トランザクション保護（Phase 5）を反映。`hve/reconciler.py` による整合性チェックを FR-CLI-49 / 50 として新規。`resume reconcile` / `resume gc-orphans` サブコマンドを§5.1 に追加。NFR-REL-02 を新規 |
| 1.0 | 2026-05-12 | **Resume 2 層トランザクション保護（Phase 6）完了とともにメジャー版へ昇格**。`StepRunner._record_checkpoint` を FR-CLI-51 として新規、NFR-OBS-04 を追加。§10 参照に新規モジュール（`run_state.py` / `run_lock.py` / `run_journal.py` / `recovery.py` / `reconciler.py`）を追加。§12 に TBD-17 を追加。`schema_version` は Phase 1 以降 2.0 で不変 |
| 1.0.1 | 2026-05-12 | TBD-17 解消。`runner.py` の 4 phase（事前 QA / メインタスク応答受信 / Review / Self-Improve イテレーション）に `_record_checkpoint(step_id, marker)` を組み込み、`orchestrator.py` で `RunJournal` を build して `StepRunner` に注入。FR-CLI-51 の「現状の呼び出し箇所」の記載を「全 4 phase で稼働中」に更新 |
| 1.0.2 | 2026-05-12 | 敵対的レビューで検出した Critical 4 件 + Major 数件を修正。(1) `cmd_delete` の journal を archive → end → rmtree の順序に整理し crash-safety を担保、(2) `reconcile_run` の SDK 例外時を `sessions_unknown` 新規分類へ、SDK 未接続時も unknown 扱いに変更、(3) `reconcile_all` で `sdk_list_sessions` を伝搬し sdk_only 検出を有効化、(4) `RunJournal._append_record` で `_ROTATE_CHECK_INTERVAL` ごとに rotate 発火、(5) `_run_startup_recovery` で pending スキャン先行による SDK client 構築抑制、(6) `RunLock.acquire(timeout=0)` 表記を `RunLock.acquire()` に訂正。Critical #1〜#4 検証テスト 3 件を追加 |
| 1.0.3 | 2026-05-12 | 敵対的レビュー Major 指摘の残りを修正。(1) Major #11: `RunJournal.record_event` 単発レコード API を追加し `_record_checkpoint` の fsync 回数を半減、(2) Major #12-13: users-guide に `resume reconcile` / `resume gc-orphans` の説明と v1.0 アップグレード時の破壊的変更通知を追記、(3) Major #14: TBD-15 を解消マークし [CHANGELOG.md](CHANGELOG.md) に schema 2.0 移行案内を追記、(4) Major #15-16: `intent_log` / `lock_holder` 同期ヘルパー (`sync_intent_log_from_journal` / `record_lock_holder`) を追加し、`orchestrator.run_workflow` で journal pending intent を `intent_log` に自動同期、(5) Major #17-19: テスト漏れ補充 (`test_orchestrator_resume.py` / `test_main_startup.py` / `test_run_lock_crossproc.py`)。クロスプロセス排他は `subprocess.Popen` で実機検証 |
| 1.0.4 | 2026-05-12 | 旧 TBD 一掃ターン。(1) **TBD-01 / 03 / 04 / 07 / 10 / 15 を解消マーク**（commit SHA 記録、ADR 実在調査、users-guide リンク検証、`check_qa_skip` 6 reusable workflow 確認、`_normalize_model_with_warning` 3 経路特定）、(2) **TBD-02 解消**: §8.2 を SDKConfig 主要グルーピングで再構成、`_SAFE_CONFIG_FIELDS` を正と明示、(3) **TBD-13 解消 + TBD-11 / 14 部分解消**: AAD-WEB Step 1 / 廃止した旧独立原本質問票処理 Step 1-2 / ADOC Step 1, 3.2-3.5, 4, 5.1-5.4, 6.1-6.3 の `output_paths` を `hve/workflow_registry.py` に正式登録、(4) **TBD-05 / 06 / 08 / 09 / 16 / 12 を保留方針付きでクローズ**: 各 TBD に対応方針・優先度・所要見積を追記し、設計判断要・運用継続課題として明示 |
| 1.2 | 2026-07-24 | Resume 全廃後に残っていた現在形の記述を履歴扱いへ整理し、HVE アプリケーション保守の選択的要件参照、TDD 順序、PR トレーサビリティ要件（FR-MAINT-01〜04 / NFR-CTX-01）を追加 |
| 1.3 | 2026-07-28 | E-09（io-contract registry mismatch 解消と CI 必須化）を反映。(1) **FR-WF-OUT-02 改訂**: `output_paths_template` が fan-out parser 別の ID 別名プレースホルダ（`{screenId}` / `{serviceId}` 等）を解決するよう仕様拡張、(2) **FR-WF-OUT-06 / 07 新規**: 確定ファイルパスへ解決できないエントリの fail-closed drop（5 規則）と、非 fan-out Step における契約宣言専用の位置付けを規定、(3) **FR-WF-OUT-05 新規**: StepDef 宣言と io-contract の一致（registry mismatch 0 件）を必須化し CI を hard fail 化、(4) **TBD-11 / 12 / 14 解消**: AAD-WEB / ASDW-WEB / ADOC の未登録 Step を `hve/workflow_registry.py` へ登録し、`ALLOWED_EMPTY_OUTPUT_PATHS_STEPS` の残件を adfdv 1.2 の 1 件へ削減 |
| 1.4 | 2026-07-28 | live canary による ASDW Step 1.3 の実行経路検証と、§13.5 の実態乖離を解消。(1) **§13.5 全面改訂**: 節名を ABDV（Batch Dev）から **ADFDV（Dataflow Dev）** へ改め、Custom Agent 列を追加し、生成先を `batch` から `dataflow` へ、fan-out parser を `batch_job_catalog` から `dataflow_catalog` へ、成果物パスを `hve/workflow_registry.py` の実定義へ合わせた。(2) **FR-WF-ADFDV-01 / 02 新規**: fan-out キー元を ADFD 生成のアプリカタログと規定し、`{jobNameSlug}` が現状解決不可で FR-WF-OUT-06 により drop されることを明記 |
| 1.5 | 2026-07-28 | `output_paths_template` の宣言健全性を強化。(1) **FR-WF-OUT-08 新規**: 名称スラッグが日本語カタログ名の英訳であり決定的復元が不可能であることを根拠付きで規定し、キー別名への登録を禁止、(2) **FR-WF-OUT-09 新規**: fail-closed drop の結果ゲートが無言で空になる Step を明示 allowlist で固定し、allowlist 外の新規発生を CI で検出することを必須化、(3) **宣言修正**: ASDW-WEB 3.2 のテストプロジェクトパスを実在 8 ディレクトリに基づき `{serviceNameSlug}` から `{serviceId}` へ是正し、非 fan-out の ASDW-WEB 3.4 から永久未解決エントリを除去（io-contract 同期済み） |
| 1.6 | 2026-07-28 | 分離済み残件（TBD-06 / TBD-19 / E-2）を処理。(1) **FR-WF-OUT-10 新規**: fail-closed drop されたエントリのうち fan-out キーを含むものを **prefix 存在ゲート** へ降格して検証を回復させ、**TBD-19 を契約変更なしで解消**（allowlist 7 → 3 件）、(2) **FR-WF-ARD-01 新規**: ARD を CLI / GUI Orchestrator 専用と確定して **TBD-06 を解消**し、dispatcher への混入を契約テストで固定、(3) **TBD-20〜23 新規**: mdq watcher 既定 ON は実装済みと確認、APP-009 依存は fail-closed ガード済みの feature 保留、`artifact_validation.py` 分割は実害未観測のため実施しない、到達不能コードは多層防御として保持することを確定 |
| 1.7 | 2026-07-29 | 実行面横断の重複実装防止を §3.7 へ追加。(1) **FR-MAINT-05 新規**: HVE 対象の実装シンボル索引 `hve-dev/hve-surface-inventory.csv` を機械生成し、対象境界判定の再利用・決定的生成・対象外パス非混入を必須化、(2) **FR-MAINT-06 新規**: 規範リテラルごとの判定実装を単一とし、索引を用いた決定論的検査を必須化。生成側の文言複製と意図的 vendoring は対象外、(3) **FR-MAINT-07 新規**: 新規ロジック追加前の面横断再利用確認を規定し、規範リテラル → 振る舞い要約 → シンボル名の探索順と、名前不一致だけを根拠としないことを必須化、(4) **TBD-24 新規**: PR トレーサビリティブロックへの面横断影響フィールド追加を保留とし、判断根拠を記録 |
| 1.8 | 2026-07-30 | **FR-GUI-04 改訂**: Code-Query の索引管理を HVE 設定画面内だけでなく、任意の別リポジトリを明示して操作できる独立 GUI として配布する契約を追加。HVE / standalone 間の管理セクション・サービス・バックグラウンド処理の単一実装共有、対象リポジトリ単位の設定分離、非所有設定の保持、vendored `cq` による上流 import path 非依存の起動を必須化 |
| 1.9 | 2026-07-30 | Skill 配布キットの単一実装化と可搬性を規定。(1) **§3.10 新設（FR-KIT-01〜05）**: 配布キットへのエンジン同梱と正本一致の機械検証、Skill 定義の単一正本化、セットアップ・同期判断ロジックの単一実装化、フォルダ複製だけで成立する可搬性の機械検証、配布物からの `hve` 依存禁止を必須化、(2) **FR-GUI-05 新規**: `mdq` 管理画面についても独立版と HVE 組み込み版の単一実装共有を必須化し、依存方向を HVE → `mdq` の一方向へ固定、(3) **§6.5 節名変更**: 「GUI からの cq 索引運用」→「GUI からの mdq / cq 索引運用」 |
| 2.0 | 2026-07-31 | **§3.9.1 新設（FR-CQ-13 / FR-RQ-01〜04 / NFR-RQ-01）**: HVE 内の明示実行型 Repository Query Agentic Retrieval 計測 PoC、chunk 再利用 API、custom-only tool、Grounding JSON、A/C/D 比較、bounded execution、public / portable 非対象を規定 |
| 2.1 | 2026-08-03 | **FR-GUI-06 新規**: GUI Step 1 右ペインが選択中ワークフローの必須入力キーの入力欄を当該ワークフロー枠内に表示することを必須化。対象キーを FR-GUI-01 の 2 系統の和集合と規定し、固有入力欄を他に持たないワークフローでも枠を生成すること、表示対応表に実在しない入力欄を指すエントリを残さないこと、右ペイン入力値の設定ストア永続化（FR-GUI-03 の右ペイン経路への適用）を追加 |
| 2.2 | 2026-08-04 | **§3.11 新設（FR-RTO-01〜06 / NFR-RTO-01〜03）**: 全実行面（GUI / GUI Autopilot / 対話 CLI / 直接 `orchestrate` / CUI Workbench / CLI Autopilot / `--autopilot-child` 互換面）の実行時 Dashboard と Observability を規定。イベント契約の単一実装と既存 `[hve:stats]` 後方互換、収集 / 保存 / 子配信 / 表示の分離、run-scoped JSONL 永続化と allowlist、instance 単位表示、ライフサイクルとクリーンアップ非干渉、性能・互換・可用性の非機能要件を追加。entrypoint 要件（FR-CLI-10）は改訂対象外と明示 |
| 2.3 | 2026-08-04 | **FR-MODEL-04 / 05 新規**: SDK の `create_session(tool_search=...)`（ツール定義の遅延ロード）を CLI / GUI から設定可能とし、既定無効・全セッション経路への同一値伝搬・未サポート時の `TypeError` 縮退を規定。`defer_threshold` は SDK 既定に委ね設定公開しない。§5.2 FR-CLI-02 のオプション一覧へ `--tool-search` / `--no-tool-search` を追記 |
| 2.4 | 2026-08-05 | **FR-MODEL-04 改訂 / FR-MODEL-06・FR-WF-AAG-01/02・FR-WF-AAGD-01〜04 新規**: HVE 自身の `tool_search` を既定有効へ変更し（利用者の適用方針決定。削減率は未測定のまま受入対象外）、明示的な無効化（`--no-tool-search` / `HVE_TOOL_SEARCH` falsy / GUI 保存済み値）を上書きしないことを規定。生成 AI Agent の Tool Search 方針を `auto` / `yes` / `no` の 3 値に固定し、全起動経路での同一値伝搬と、設計・実装・Deploy・評価・Cloud 完了判定の各成果物ゲートを必須化。§13.7 の Step 表へ Step 4（tool search 実測評価）を追記 |
| 2.5 | 2026-08-05 | **FR-KIT-06 新規 / FR-KIT-04 改訂**: 配布パッケージの宣言単一化、版マニフェスト（配布版・エンジン版・上流 commit・ハッシュ）の生成、同版・降格同期の既定拒否、旧配布ファイルの削除と利用者所有ファイルの温存、コピー先単独での版・改変確認、上流 extras 相当の任意依存の同期宣言を必須化。併せて FR-KIT-04 へ「上流固有の名前（profile 名等）を手動で与えなければ成立しない状態を禁じる」条件を追加 |
| 2.6 | 2026-08-06 | **FR-CQ-15 新規 / FR-GUI-04 改訂**: 索引統計へ言語別内訳（言語ごとのファイル数・シンボル数・チャンク数・パーサフィデリティ別ファイル数）の報告を必須化し、パーサ別集計だけの報告を禁止。同一パーサ名が複数言語で共有されるため言語別のフィデリティ低下を判別できないことを根拠として明記。言語の再判定禁止と CLI / GUI の単一実装（FR-MAINT-07）を規定し、GUI の提供範囲へ言語別内訳の表示を追加 |
| 2.7 | 2026-08-07 | **FR-GUI-08 新規**: GUI 質問票の選択肢付き質問へ「その他」と自由記述入力を追加し、回答を既存の `N:: その他: <text>` 形式でマージ済み質問票ファイルへ保存する契約を追加 |
| 2.8 | 2026-08-07 | **FR-MODEL-07 新規**: `github-copilot-sdk` の導入版を `hve/copilot-sdk.lock` で固定し、最新化を `--upgrade-sdk` / `-UpgradeSdk` 指定時のみに限定。SDK が pin する Copilot CLI ランタイムの先読みと埋め込み版突合（`--no-auto-update` 必須）、pin 無効化環境変数の警告を必須化。生成イベントパーサがエンベロープを assert で固めており、版ドリフト時に `session.event` が `AssertionError` で黙って捨てられることを根拠として明記 |
| 2.9 | 2026-08-07 | **§3.12 新設（FR-QA-01 / 02）**: QA 質問票の各質問へ「背景と根拠」「判断の観点」を必須項目として追加し、「既定値候補の理由」に根拠事実・優先した評価軸・他選択肢を採らない理由の 3 要素を必須化。既定値候補の理由が結論のみの一語で終わり、なぜ不明点なのか・どの観点で判断が分かれるのかを利用者が読み取れなかったことを根拠として明記。プロンプト・`QAMerger`・CLI 表示・GUI ダイアログ・Skill テンプレートの全経路で同一項目定義を保持することを必須化 |
| 2.10 | 2026-08-07 | **FR-DAG-04 改訂 / FR-GUI-01 改訂**: fan-out 展開のカタログ探索基準ルートを実行プロセスの作業ディレクトリ（対象リポジトリのルート）と規定し、事前展開と deferred 再展開の双方で同一基準とすることを必須化。HVE パッケージ設置ディレクトリを基準にすると、カタログが実在しても展開キーが 0 件となり `fanout-empty` で無警告 skip される事象を根拠として明記。併せて FR-DAG-04 の実在しない parser 名 `batch_job_catalog` を `dataflow_catalog` へ、`use_case_skeleton` の対応 Step を現行の ARD Step 3.2 へ是正。FR-GUI-01 へ `REQUIREMENT_TABLE` / `WORKFLOW_PRIORITY` が `list_workflows()` の全ワークフローを網羅する義務を追加。**FR-WF-ARD-02 新規**: ユーザー提供資料（`attached_docs` / パス指定の `target_business`）を一次情報として最優先参照することの Prompt / テンプレートへの明示を必須化（当該資料は `required_input_paths` 未宣言でパラメータ注入のみが到達経路であることを根拠として明記） |
| 2.11 | 2026-08-07 | **§6.7 / FR-GUI-09 新規**: Windows の `hve/setup-hve.cmd` と macOS / Linux の `./hve/setup-hve.sh` の通常実行で、GUI の GitHub CLI ログイン用 `gh` を OS ツールとして導入・解決し、同一リポジトリの `.venv` に OS 別 PTY backend を導入・検証する契約を追加。通常 GUI 構成の依存欠落は非ゼロ終了、未認証の `gh auth status` は許容、`gh auth login` の自動実行は禁止、既存 venv の Force なし修復と `NoGui` / `Minimal` opt-out の維持、OS 別通常セットアップを主復旧導線とすることを規定 |
| 2.12 | 2026-08-07 | **FR-GUI-09 改訂**: `CheckOnly` / `--check-only` を「変更なしのまま `gh` / PTY backend の不足を警告として報告する診断モード」と明文化（通常実行の fail-closed 契約とは分離し、非ゼロ終了・`.venv` 変更を禁止）。復旧案内の setup パスを GUI の作業ディレクトリに依存させず、パッケージ配置から解決した実パスを提示すること（setup スクリプトが同居しない導入形態では相対表記へ退避）を追加。GUI 依存未導入時の起動案内も同じ主導線に従い、`.[gui]` 単独導入を完全構成の推奨復旧経路として提示せず、実在する起動入口 `hve.cmd gui` / `./hve.sh gui` を案内することを追加 |
| 2.13 | 2026-08-07 | **§3.7 対象境界 改訂**: `users-guide/**` を「対象」から「対象外（単独変更時）」へ移し、`CHANGELOG.md` と同じ扱いに統一。利用者向けドキュメント本文は実行時に観測できる挙動を持たず、単独変更では要件 ID・テストパスの実質的な申告対象が存在せず、定型 N/A 申告だけを量産してゲートの監査価値を希薄化していたことを根拠として明記。コード変更に伴うドキュメント同期は同一 PR 内の他の対象パスでゲートが起動するため担保される |
| 2.14 | 2026-08-13 | **FR-GUI-02 / 03 / 06 改訂 / FR-WF-ASDW-02 改訂**: GUI が入力欄・永続化・監視の対象とする必須入力キーを `required_params` のうち `default_params` を持たないものへ限定し、判定の単一実装（FR-MAINT-07）を必須化。既定値を持つキーへ入力欄を設けると、保存された非空値を `apply_step_default_params` が補完せずレジストリ既定値を無言で上書きすることを根拠として明記。ASDW-WEB Step 1.3 では利用者入力を `resource_group` 1 件へ縮約し、`data_*` 5 件の GUI 入力欄を禁止（3 つの CIDR は包含・非重複を fail-closed 検証する相互依存した組であり部分的な利用者編集が整合しない組合せを許すため）。廃止キーは設定ストア既定値から外し `_OBSOLETE_KEYS` で保存済み値を除去することを追加。CLI フラグによる明示上書き経路は維持 |
| 2.15 | 2026-08-13 | **§6.8 / FR-GUI-10〜15 新規**: HVE GUI の Copilot パネルを使い捨て `copilot -p` から GitHub Copilot CLI の対話セッション常駐へ移行する契約を追加。汎用チャットへの権限緩和フラグ暗黙付与の禁止、実行中ジョブへの `queue` / `steer` / `stop_and_send` の SDK 呼び出し写像と `stop_and_send` 後の再待機義務、workflow instance ごとの IPC チャネル分離と並列 step の宛先明示選択、完了ジョブの実在パスのみを用いた結果相談コンテキスト、および §5.6（HVE ワークフロー再開の廃止）と VS Code 固有実行面を対象外とする境界を規定 |
| 2.16 | 2026-08-13 | **FR-QA-03 / FR-CLOUD-24 新規**: `auto_qa` 有効時に回答済み QA ファイルを最終 read-back 検証後、Knowledge Management 以外の Workflow からファイル単位で AKM 差分更新へ非待機連携する契約を追加。CLI / GUI の Git・cleanup 安全境界、明示 AKM を含むリポジトリ単位直列化、原本質問票処理の事前 QA 対象化、Cloud の回答正規化・固定パス保存・最小権限・branch 検証・冪等 dispatch、および AKM PR 完了まで保持する Cloud concurrency を規定 |
| 2.17 | 2026-08-13 | **FR-RTO-07 新規**: 実行履歴の Step 別表示を Step 単位で分離することを必須化。GUI「今回の実行履歴」が Step の Context / AI Credit / モデルを実行面のグローバル現在値から複製していたため、並列 Wave の Step 群が完全同値となり、Workflow 親行の Context / モデルも最後に完了した Step の値の複製となっていたこと、および SDK Fleet mode へ委譲した Wave の消費が Step 別・Workflow 累積のいずれにも計上されていなかったことを根拠として明記。Step 帰属イベントが無い項目の `-` 表示と累積差分による推定の禁止、Step へ帰属できない消費の Workflow 累積への計上義務と不一致理由の表示、SDK Fleet mode 委譲 Wave での Step 割り当て禁止、`run_id` 未確定期間の実行を確定後に二重計上しないことを規定 |
| 2.18 | 2026-08-14 | **§3.7 対象境界 改訂**: 入力カタログ・生成済みテスト仕様が既に存在しない APP-04 専用生成器を削除し、当該ファイルだけを対象外とする専用例外と契約例を撤去。APP-04 の成果物を HVE 本体の保守対象として扱わない境界を、存在しない個別ファイルではなく現行の生成物・対象パス規則で維持する |
| 2.19 | 2026-08-14 | **FR-RTO-07 改訂**: SDK Fleet mode へ委譲した Wave の worker と Step の対応を「解決不能」と固定していた規定を、「当該 Wave の Step 集合に対して一意に定まる場合にだけ帰属させ、一意に定まらない場合はいずれの Step へも割り当てない」へ改める。SDK が worker の作業イベント（`assistant.usage` / `tool.execution_start`）に `parent_tool_call_id` を付与し、それが sub-agent 起動時の `tool_call_id` と一致することを根拠とする。対応の解決に用いた tool の引数を観測イベントへ保存しない義務を明記（FR-RTO-04 の再掲）。`parent_tool_call_id` を持たない `session.usage_info` / `skill.invoked` に由来する Context・Skill は、引き続き帰属不能として `-` 表示となる |
| 2.20 | 2026-08-14 | **FR-QA-04 / FR-GUI-17 / FR-CLOUD-25 新規**: FR-QA-03 の QA 起点 AKM に対して、AKM 子実行のモデル・reasoning effort・context tier をメインタスクと独立に選択できる契約を追加。CLI / GUI では 3 項目すべてを扱い、未指定はメイン設定を継承、解決は `QaAkmCoordinator._build_argv` の単一実装に限定し、`--workflow akm` の明示実行は対象外とする。GUI は設定画面と Step 1 右ペインの双方へ表示し `auto_qa` 連動で活性化する。Cloud は Issue Form の `akm_model` を QA 起点 AKM Root Issue の `### 使用するモデル` 節へ継承させ、reasoning effort / context tier に相当する設定が Cloud 面に存在しないためモデルのみを対象とする。従来 QA 起点 AKM はメイン設定の丸ごと転写（CLI / GUI）または常に既定モデル（Cloud）で実行され、AKM だけの実行品質を選べなかったことを根拠として明記 |
| 2.21 | 2026-08-15 | **§3.7 版管理境界 新設（FR-MAINT-08 新規）**: `.github/copilot-instructions.md` §0 が機械正本と定める版更新の対象判定を、対象境界と同一モジュールの単一実装として規定。対象境界の判定結果から (1) 版番号・変更履歴の同期先ファイル自身、(2) 独立ライフサイクルのパス（`mdq/**` / `cq/**` / 配布キット）を除いたものだけを版更新の対象とすることを必須化。対象境界の述語をそのまま版管理へ流用すると、`pyproject.toml` と `hve/__init__.py` が対象境界に含まれるため版更新のための変更自体が次の版更新を要求し、規則を充足できる状態が存在しなくなることを根拠として明記。(1) の列挙は `[tool.bumpversion]` 設定を単一の情報源とすることと、`mdq.toml` / `cq.toml` を除外列挙に含めない判断も規定 |
| 2.22 | 2026-08-15 | **§6.9 新設（FR-GUI-19 新規）**: GUI Step 2 Workbench の経過時間表示を、ジョブの終了・停止時に停止させることを必須化。「作業状況」の経過時間停止が `DagStatusWidget.freeze_elapsed()` の設定するサマリー行用の終了時刻にしか作用せず、Workflow ノード・Step ノード・fan-out 子ノードが `time.monotonic()` を参照し続けてカウントアップしていたこと、および Plan モードの終了検知が `SubprocessReader` の標準出力終端にのみ接続されており、サブプロセスが終了してもストリームが終端しない場合に `freeze_progress_elapsed()` が一度も呼ばれないことを根拠として明記。停止対象を 4 系統すべてとし `set_plan` / `update_workflow_instances` による表示ノード再生成後も維持すること、終了検知をストリーム終端だけに依存させないこと、終了の根拠をプロセスの終了状態に限り出力の途絶を根拠にしないこと、終端通知の猶予上限を 10 秒とすること、異常終了時に実行ログへ警告を 1 行出力し正常完了と区別して記録する一方で実行中 Step の状態表示を書き換えず新規の観測イベント種別も追加しないこと、遅延到着したストリーム終端で終了処理を二重実行しないこと、新規実行の開始時に検知状態を初期化することを規定。「作業状況」を持たない `--autopilot-child` 互換面は対象外 |
| 2.23 | 2026-08-15 | **FR-CQ-16 / FR-CQ-17 新規**: `cq` へ全検索層の並列実行と順位統合（要求時のみ）と、意味的類似度に基づく検索層（要求時のみ）を追加。統合は層内順位のみを根拠とし層をまたぐスコア比較を禁止、リテラル一致層は統合対象外として順位を保つことを規定（実測: 等価に統合すると `symbol` の top-1 が 1.00 → 0.77、`substr` が 1.00 → 0.57 へ退行）。意味検索は単独モード禁止・索引スキーマ非変更・モデル記録と不一致時の不使用・ファイル変更後の不使用・全失敗経路での 0 件縮退を必須化 |
| 2.24 | 2026-08-15 | **FR-CQ-16 改訂 / FR-CQ-17 改訂**: ベンチマークの実測に基づき、統合を「意味検索層を含むときに限る」へ制限し、語彙層だけを統合する手段の提供を禁止（golden 56 問で逐次の層選択と **56/56 問で順位が完全一致**し、応答トークンだけが 2.2〜2.4 倍になった）。FR-CQ-17 へ、本文を返さず囲むシンボルの修飾名・種別・シグネチャを返す返却単位を追加し、パーサフィデリティとチャンク識別子の保持、囲むシンボル不在時の位置情報返却を規定 |
| 2.25 | 2026-08-16 | **FR-QA-05 / FR-GUI-20 / FR-CLOUD-26 新規、FR-QA-03 / FR-GUI-16 / FR-GUI-17 改訂**: QA 起点 AKM のバックグラウンド起動を、利用者が明示選択する設定 `qa_akm_background_merge`（既定無効）で制御する契約を追加。従来は `auto_qa` を有効にするだけで共有資産 `knowledge/` への自動書込みが常に起動し、利用者がコスト・実行時間・差分レビュー量を制御できなかったことを根拠として明記。判定を CLI / GUI は `_should_enable_qa_akm_dispatch`、Cloud は `save-qa-answer` の `sync_required` の各 1 箇所へ限定し、環境変数経路の新設と `--workflow akm` 明示実行への適用を禁止。GUI は設定画面の「自動プロンプト」ノードを廃止して `QA (質問票)` / `レビュー` / `Knowledge Management` / `自己改善 (Self Improve)` へ再編し、`追加プロンプト` / `コンテキスト最大文字数` を `基本設定` へ移し、略語 `QA` / `AKM` の表示を `QA (質問票)` / `Knowledge Management` へ改称。Cloud は Issue Form へ `enable_qa_akm_merge` を追加し、`knowledge-management.yml` を除外 |
| 2.26 | 2026-08-16 | **FR-WF-ADI-17 / 18 新規、FR-WF-ADI-12 改訂**: 旧独立の原本質問票処理を廃止し、D01〜D21 質問票 fan-out と横断 join を ADI Step 1.1 / 1.2 へ統合。ADI は CLI / GUI 専用のまま維持し、独立 Workflow ID・Cloud reusable workflow・CLI / GUI 選択肢・後方互換 alias を設けない契約を追加 |
| 2.27 | 2026-08-16 | **FR-WF-AAG-03 / 04・FR-WF-AAGD-05 / 06 / 07 新規**: 生成 AI Agent の Agentic Retrieval 方針を `auto` / `yes` / `no` の 3 値に固定し、AAG Step 3 と AAGD Step 2.3 / 3 への同一値注入と、方針別の設計成果物ゲートを必須化。Foundry IQ 経路では Knowledge Source Matrix の行数下限を 2 とし（1 行のみでは複数ソース横断の前提を満たさずクラシック単一クエリ検索と等価になるため）、AR-CAP-01 へ `Index semantic configuration` を必須ラベルとして追加（各サブクエリが semantic rerank を通るため索引側構成が検索品質の上限を決めることを根拠とする）。AAGD Step 2.1 / 2.2 への `agentic-retrieval-contract` 公開と、Toolbox 採否に依存しない Deploy ゲートの AR-CAP-01 / 02 静的照合を追加。併せて Agent Plugins Specification 1.0.0 準拠のマニフェスト `src/agent/{key}/plugin.json` の生成と検証、および `SKILL.md` frontmatter の長さ制約検証を必須化 |
| 2.28 | 2026-08-17 | **FR-MODEL-07 改訂 / FR-MODEL-08 新規**: セットアップの `github-copilot-sdk` 既定経路を lock 版固定から最新追従（`--upgrade --no-deps`）へ変更し、版固定を明示フラグ `--pin-sdk` / `-PinSdk` の opt-in へ移した。`--upgrade-sdk` / `-UpgradeSdk` は最新化に加えて宣言ファイルの pin 行と CLI ランタイム記録行を書き換える役割として維持し、既定経路では宣言ファイルを書き換えない。ランタイム整合検証（pin 先読み・`--no-auto-update` による埋め込み版突合・pin 無効化環境変数の警告）は変更せず維持する。あわせて外部 `copilot` コマンド（npm パッケージ `@github/copilot`）を Windows / macOS / Linux の全セットアップで最新版へ導入・更新することを必須化し、npm グローバル管理下でない `copilot` を検出した場合の二重導入禁止と警告、`--no-install-tools` / `--check-only` での抑止を規定 |
| 2.30 | 2026-08-17 | **§13.14 新設（FR-WF-CONF-01〜06 新規）／ FR-CLOUD-06 改訂・FR-CLOUD-07 新規**: 生成・デプロイ済みの成果物を実際に動かし、機能要件・非機能要件への適合を測定して報告する Step を ASDW-WEB `5.3` / ADFDV `4.3` / AAGD `5` / AAR `7` へ追加し、単一 Custom Agent `QA-RequirementsConformanceEval` を 4 Workflow で共有することを規定。従来は設計文書の照合による WAF レビューと整合性チェックまでで完結し、デプロイした構成が目標値を満たすかを実測で確認する経路が無かったこと、および実行基盤の選択が過剰かどうかは設計文書から判定できないことを根拠として明記。判定語彙を `PASS` / `FAIL` / `NOT_MEASURED` / `NO_TARGET` の 4 値に固定して目標未定義と未測定を区別し、実測値からの目標逆算を禁止。本 Step のための Azure リソース新規作成の必須化を禁止し、マネージド負荷試験サービスの利用は任意とした。あわせて FR-CLOUD-06 を「同期が確認できた reusable workflow は dispatch 対象としてよい」へ改めて ASDW-WEB の Cloud 起動停止を撤去し、FR-CLOUD-07 で AAR を Cloud dispatch 対象へ追加 |
| 2.29 | 2026-08-17 | **§6.11 新設（FR-GUI-21 新規）**: GUI Step 1 と CLI 対話ウィザードのワークフロー一覧を共通のカテゴリー表で分類することを必須化し、`aag` / `aagd` / `aar` を新カテゴリー `AI Agent` へ分類。従来この 3 件はどのカテゴリーにも登録されておらず未分類の縮退枠「その他」に落ちていたこと、およびカテゴリー表が GUI 専用モジュールにあり CLI から参照できなかったことを根拠として明記。正本を `hve/workflow_registry.py` の `WORKFLOW_CATEGORIES` へ集約（FR-MAINT-07）、全ワークフローの過不足ない分類と重複・未登録 ID の禁止、未分類 ID の「その他」縮退経路の維持、CLI での見出し行挿入禁止と索引整合の維持、表示順を列挙する 3 つの表への全ワークフロー列挙、および全ワークフローに対する GUI 説明文・表示名の提供を規定 |
| 2.31 | 2026-08-19 | **FR-QA-03 改訂**: QA 起点 AKM のバックグラウンド実行について、(1) 実行開始時点でキューに滞留している複数の登録を 1 回の AKM 子実行へまとめてよいこと（`target_files` へ全件を与え、結果はファイル単位で報告）、(2) 同時に 2 つ以上の AKM 子プロセスを起動してはならないこと、(3) AKM 子実行へ Workflow 定義の宣言並列上限（`WorkflowDef.max_parallel`）を明示的に渡すことを追加。従来は検証済み QA ファイル 1 件ごとに子実行が逐次起動され、待ち合わせ境界（Git 後処理・branch 切替・GUI cleanup・DAG 完了）で親 Workflow の待ち時間が登録件数に比例していたこと、および子実行が `--max-parallel` を受け取らず `SDKConfig.max_parallel` の既定値で動くため D01〜D21 の 21 fan-out が複数 wave へ分割されていたことを根拠として明記。子プロセスの多重起動を禁じる根拠として、AKM の出力空間が `target_files` によらず `knowledge/D01`〜`D21` 全体と `knowledge/business-requirement-document-status.md` を含むことを明記 |
| 2.32 | 2026-08-19 | **FR-DAG-03 改訂 / NFR-PERF-01 改訂**: DAG の並列上限の解決順序を「ARD bridge mode → `WorkflowDef.max_parallel` の宣言値 → `SDKConfig.max_parallel`」と規定し、解決を `hve/orchestrator.py` の単一実装へ限定（FR-MAINT-07）、解決根拠を `DAGPlan.max_parallel_source` へ `ard-serial` / `workflow` / `config` として保持することを必須化。宣言を持つ Workflow に対して `SDKConfig.max_parallel` で宣言値を上書きすることを禁止し、宣言値へ `asdw-web` = 1 を追加した。従来 `run_workflow` は `SDKConfig.max_parallel` だけを `build_dag_plan()` へ渡しており、`DAGExecutor` は `dag_plan` がある限り `DAGPlan.max_parallel` で semaphore を作るため、`WorkflowDef.max_parallel` が実行へ一切反映されていなかったことを根拠として明記（実測: `asdw-web` は宣言 1 に対して 2 ステップの wave が 4 箇所とも並列実行され、`akm` / `adi` は宣言 21 に対して semaphore 15 で fan-out が分割されていた）。`asdw-web` の宣言は同一 worktree の並列書込みを避ける安全制約であり、利用者設定で緩められてはならない。あわせて v2.31 で FR-QA-03 へ追加した (3)（AKM 子実行へ宣言並列上限を明示的に渡す）を本解決順序へ統合し、子 argv での並列度固定を禁止した（FR-MAINT-07。本改訂後は子へ `--max-parallel` を渡しても宣言値が優先されるため、当該の明示付与は効果を持たない） |
| 2.33 | 2026-08-19 | **FR-QA-06 / FR-QA-07 新規、FR-QA-03 改訂**: (1) Work IQ 応答が `FOUND` / `PARTIAL` でありながら許可済み server/tool 組の実行を確認できない場合の警告通知を必須化し（FR-QA-06）、警告文の生成を `hve/workiq.py` の単一ヘルパーへ限定（FR-MAINT-07）。(2) QA 起点 AKM 子実行の標準出力・標準エラーの保全と、失敗時の `returncode` / 保存先パス報告を必須化（FR-QA-07）。(3) FR-QA-03 へ、MCP 公開 allowlist（最小権限）と実行確認用 tool 名集合を別集合として保持すること、および書き込み系ツールを統合根拠としないことを追加。根拠は 2026-08-19 の実測（`work/2026-08-19-qa_workiq_dryrun.md`）で、事前 QA の Work IQ 応答 6 件中 3 件が `FOUND` であったにもかかわらず統合 0 件となり、実行面には `✅ Work IQ: 0 件の質問に回答案を統合しました` という成功記号付きの情報メッセージしか出なかったこと（実際に呼ばれたツールは `retrieve` 10 回で、当時の許可集合は `ask` のみ）、および QA 起点 AKM 子実行が失敗しても親のログに件数しか残らず、原因究明に手動再現を要したこと。あわせて、許可集合を SDK の `session.rpc.mcp.list()` から動的構築する案は採らなかった（実測で server オブジェクトが tools を公開せず、`session.rpc.tools` にも一覧取得 API が無いため実装不能）ことを記録する |
| 2.34 | 2026-08-19 | **FR-QA-08 新規 / FR-QA-07 改訂**: (1) 事前 QA の Work IQ 統合可否を Workflow 全体を再実行せずに確認する診断経路 `workiq-doctor --qa-integration-probe` を必須化し、統合可否判定を事前 QA 本体と同一実装（`hve/workiq.py` の `is_workiq_result_mergeable()`）へ限定した（FR-MAINT-07）。従来 FR-QA-03 の統合条件は `hve/runner.py` にインライン実装され、受入確認に実測 40 分超の Workflow 再実行を要していたことを根拠として明記。(2) FR-QA-07 へ、QA 起点 AKM の登録時点で HVE ソースの未コミット変更を検出した場合に子実行を起動せず登録をスキップして即時警告すること、スキップを実行失敗と別事象として報告すること、および FR-CLI-74 の最終ガードを置き換えず対象リポジトリを coordinator のルートへスコープすることを追加した。従来は親 run の開始から 40 分以上経過した後の drain 境界でしか失敗を知り得なかったことを根拠とする |
| 2.34 | 2026-08-19 | **FR-CLOUD-06 改訂**: AKM の Cloud 経路を `hve/workflow_registry.py` の AKM 定義（Step.1 `KnowledgeManager` → Step.2 `QA-DocConsistency`）と同期させることを必須化。従来 `auto-knowledge-management-reusable.yml` は `[AKM] Step.1` の Step Issue を 1 件だけ作成し「AKM はステップが 1 つのみ」と明記していたため、Cloud 利用者が横断整合性レビュー（Step.2）を受け取れず、かつ AKM が parity テストの対象外であったため不一致を検出するゲートが存在しなかったことを根拠として明記。AKM は Bash registry へ未登録のため同期判定を hve registry のみに対して行うこと、Step.1 の D01〜D21 fan-out を Cloud で Step Issue へ展開してはならないこと（`knowledge/` の出力空間が `target_files` によらず D01〜D21 全体を含むため。FR-QA-03 と同一の根拠）を規定 |
| 2.35 | 2026-08-19 | **FR-QA-03 改訂**: 実行確認の対象となる Work IQ サーバーに、公式 `workiq` だけでなく同一の Work IQ サービスを別サーバー名で登録するプラグイン（`workiq-preview` 等）を含めることを明記し、Work IQ とみなす MCP サーバー名を単一の正本で保持すること（FR-MAINT-07）を規定。従来の根拠文は公式 `workiq` サーバーだけを例示しており、実装側（[hve/workiq.py](hve/workiq.py) の server 集合と [hve/runner.py](hve/runner.py) の main session 分離集合）が 2 箇所に分かれていたため、`workiq-preview` 経由の参照系ツール実行が確認されず QA への統合が 0 件になり得たことを根拠として明記 |
| 2.36 | 2026-08-19 | **NFR-CTX-01 / FR-MAINT-01 / FR-MAINT-02 改訂**: (1) NFR-CTX-01 のルーター箇条(1) を「HVE 対象変更」から「HVE 対象変更または HVE 対象パスの不具合調査」へ拡張し、実装を伴わない調査でも `hve-requirement-traceability` Skill を起動対象とすることを規定。従来は起動条件が「変更」に限定されていたため、`hve/**` を読むだけの不具合調査では要求定義書への到達経路が存在しなかったことを根拠とする。(2) FR-MAINT-01 へ、Skill が §1.3 の 3 層優先順位と §3.7 の変更種別判定規則を保持する義務を追加。両規則は Skill に不在で、適用可否と変更種別の判定に要求定義書本文の追加取得を要していた。(3) FR-MAINT-02 へ、要件 ID が既知の場合は検索せず `hve-dev/hve-feature-inventory.csv` の `line` 列が指す定義行だけを読む規則を追加。同一の問いに対し BM25 の chunk 返却が 3,613 tokens / 151 ms であるのに対し、索引の `line` 列からの直引きは 501〜687 tokens で検索を伴わないことを実測根拠として明記 |
| 2.37 | 2026-08-19 | **FR-WF-OUT-11 新規 / FR-QA-03 改訂**: (1) FR-WF-OUT-11 を新規追加し、io-contract の `kind: static` 入力のうち変数記法・glob・ディレクトリ参照を含まないパスの実在を CI で必須化。FR-WF-OUT-05 の registry mismatch 検査が `required: true` かつ `kind: agent_artifact` の入力しか照合しないため、実体と一致しない static 宣言 8 件がどの検査にも掛からず残存していたことを根拠とする。(2) FR-QA-03 へ、SDK Fleet mode へ委譲した wave（2 step 以上）は事前 QA と QA 起点 AKM の対象外である旨の但し書きと、当該 wave 開始前の警告義務を追加。Fleet 経路（[hve/orchestrator.py](hve/orchestrator.py) `_fleet_wave_runner`）は `StepRunner.run_step` を経由しないため、利用者が `auto_qa` / `qa_akm_background_merge` を明示的に有効化しても無言で適用されない状態が観測されたことを根拠とする |
| 2.38 | 2026-08-20 | **§5.9 新設（FR-CLI-77 新規）/ FR-GUI-22 新規**: CLI / GUI の起動時に、実在する `mdq` / `cq` 索引 DB をバックグラウンドで差分更新することを必須化。対象を実在 DB に限定し（未構築 strategy / profile の起動時生成を禁止）、watcher 起動を差分更新の完了後に直列化することを規定した。直列化の根拠は、同一索引 DB への並行書き込みが禁止されていること（[users-guide/skills-markdown-query.md](users-guide/skills-markdown-query.md) §4.2 / [users-guide/skills-code-query.md](users-guide/skills-code-query.md) §4.3）と、`mdq` の索引構築が走査終了時に 1 回だけコミットするため走査中に書き込みトランザクションを保持しうること（[mdq/indexer.py](mdq/indexer.py) `build_index`）。GUI では更新中の実行開始操作を禁止し、その理由の表示を必須化した。制御面は環境変数 1 本（`HVE_STARTUP_INDEX_REFRESH`）に限定し、GUI 専用設定項目の追加を禁止した |
| 2.39 | 2026-08-20 | **§5.10 新設（FR-CLI-78 新規）**: `hve orchestrate --autopilot-chain` が計画サマリ表示後に確認なく複数 APP のチェーン実行を開始していたため、標準入力が対話可能な場合に限り実行可否の確認を必須化した。GUI には開始前の確認ダイアログが存在する一方、CLI 経路には無く、経路によって無人実行の扱いが食い違っていたことを根拠とする。非対話（CI 等）では従来どおり確認せず実行し、確認を省略するための新規オプションは追加しない。`--autopilot-dry-run` は確認より前に return するため対象外とした |
| 2.40 | 2026-08-20 | **§3.2 訂正 / §5.11 新設（FR-CLI-79 新規）/ §5.12 新設（FR-CLI-80 新規）/ FR-TS-11 改訂 / TBD-25 追加**: (1) §3.2 の Cloud / CLI 対応マップが registry と 3 件乖離していた（実在しない `abd` / `abdv` が残存し、改称後の `adfd` / `adfdv` と実在する `ada` が欠落）。行順を registry の登録順へ揃え、Cloud 対応欄の根拠を `auto-orchestrator-dispatcher.yml` の `trigger_map` と明示した上で、ID 集合の一致を契約テストで固定した。(2) FR-CLI-79 を新規追加し、Azure を利用しない Workflow（`ard` / `akm` / `adi` / `adoc`。全 131 Step のプロンプト走査で計 42 Step が Azure 非言及）では `azure` MCP サーバを Step 実行セッションへ渡さないことを規定。Step 単位の判定は誤判定時に機能破壊となるため禁止し、allowlist 未登録は従来どおり全サーバを渡す fail-safe とした。allowlist のドリフト検査 2 種を必須化した。(3) FR-CLI-80 を新規追加し、CLI Autopilot の lane 経過時間を観測して閾値超過時に警告のみ出すことを規定。NFR-TIME-01 の CLI タイムアウトが無入出力時間ベースである一方 NFR-TIME-02 の Cloud 側は経過時間ベースの上限を持つという差の可視化を目的とし、停止は行わない。(4) FR-TS-11 へ、測定セッションを Step 実行と同じ設定モデル / `context_tier` で生成すること、出力に設定モデルを併記すること、`contextInfo` と `contextAttribution` の差分を欠損として提示しないことを追加した。(5) TBD-25 を追加し、`_build_step_permission_handler` の未使用引数を現状維持と判断した |
| 2.41 | 2026-08-20 | **FR-CLI-76 改訂 / FR-CLI-79 改訂 / FR-QA-03 改訂**: Work IQ を有効化した QA サブセッションを FR-CLI-76 の受入範囲へ移した。当該サブセッションは `mcp_servers` に `_hve_workiq` だけを明示するため FR-CLI-76 の縮約条件（`mcp_servers` / `enable_config_discovery` いずれも未指定）を満たさず自動探索が残り、利用者グローバル設定のプラグインが登録する Work IQ サーバー（`workiq`）が `tools: ["*"]`（公開 14 件）で同一セッションへ併存していた。`available_tools` / `excluded_tools` は既定 `None`、権限ハンドラは `PermissionHandler.approve_all` であるため、HVE が `_hve_workiq` へ課す最小権限 allowlist（`ask` のみ）が併存側へ及ばず、書き込み系（`create_entity` / `update_entity` / `delete_entity` / `do_action`）と `accept_eula` / `call_function` / `get_debug_link` が到達可能で、FR-TS-03 が求める安全境界がどちらの手段でも張られていなかった。対処として当該サブセッションでも `.github/.mcp.json` の宣言分（Work IQ 別名を除く）を併合したうえで `enable_config_discovery=False` を指定することとし、宣言分が無い場合は従来どおり自動探索を残すフォールバックを維持した。FR-CLI-79 の「挙動を変更してはならない経路」は 4 経路から 3 経路へ改め、Azure 除外は本サブセッションにも適用する。FR-QA-03 の 2 集合分離の根拠を訂正し、併存の実在箇所を事前 QA サブセッションから `workiq-doctor` の tool probe（`probe_workiq_copilot_tool_invocation`。利用者環境の実態を観測する診断のため自動探索を残す）へ移した |
| 2.42 | 2026-08-21 | **FR-RTO-01 改訂 / FR-GUI-21 改訂**: (1) FR-RTO-01 の `instance_id` を「実行プロセス（ジョブ）単位の識別子」と明確化し、`workflow_id#app_id` を適用する経路を当該プロセスが単一 APP へ専従する場合に限定した。同一プロセス内で APP キーごとに fan-out した Step の内訳は `step`（FR-RTO-07）で分離し、`instance_id` を Step 単位で切り替えないことを明記した。envelope の `pid` と `observability/events-<pid>.jsonl`（FR-RTO-03）がプロセス単位で対応し、`instance_id` だけを Step 単位にすると表示の集計単位（FR-RTO-05）と保存単位が食い違うことを根拠とする。従来の「APP 単位で並列実行する経路」という表記はプロセス内 Step fan-out を含むとも読め、システムテストで解釈が分かれたため文言を確定した。(2) FR-GUI-21 のカテゴリー構成員へ `ada` を追加し `AI Agent` を `ada` / `aag` / `aagd` / `aar` とした。`ada` は登録済みでありながら本要件の列挙から漏れており、「登録済みの全ワークフローを過不足なく分類する」規定と矛盾していたことを根拠とする。カテゴリーの定義順（`AI Agent` を末尾とする）は変更しない |
| 2.43 | 2026-08-23 | **FR-CLI-11 / 12、FR-PARAM-10、FR-WF-OUT-01 / 05 / 07 改訂、FR-WF-ARD-03 / FR-WF-DM-01 新規、§13.13 GATE 境界改訂**: ARD を旧 Step 1〜3 / 7-Step 表記から、現行の 4 表示グループ / 8 実 Step へ同期した。wizard の3実行モードを `quick-auto` / `custom-auto` / `manual` として定義し、既定グループ `2` / `3` / `4` を `ARD_DEFAULT_GROUP_IDS` の immutable tuple 1 箇所で所有して全起動面が参照する契約、KPI/OKR をグループ `3` だけで表す単一選択状態、および `target_recommendation_id` を bridge 経路へ欠落なく伝搬してモード別に入力時点を分ける契約を追加した。従来は再設計後も規範要件と §13.12 が旧採番・旧既定値を保持し、実装との一致を検査する受入テストも無かったことを根拠とする。あわせて、完了ゲートを全経路へ一律適用する旧文を改め、G-LBL は Cloud、G-CONS は AKM、G-DIFF は PR 作成経路だけへ適用し、G-OUT は実行時に解決された必須成果物だけを対象とすることを明確化した。Data Model は親を常時必須の索引/統合版とし、50,000文字超の見込み時だけ固定名3 sidecarへ分割し、分割不要へ戻った再実行では stale sidecarを削除するAAS/ADA共通契約を追加した |
| 2.44 | 2026-08-23 | **FR-MAINT-09 新規 / §13.2・§13.3・§13.7 改訂 / TBD-26 追加**: §13 の Step 表と `hve/workflow_registry.py` の StepDef 集合の一致を全 Workflow 横断で機械検査する要件を追加した。従来は §13.5（ADFDV）と §13.12（ARD）で同種の乖離が個別に発生し、そのつど当該 Workflow だけのテストで塞いでいたため、§13.2 には非コンテナ Step `2.4` / `2.5` / `2.6` の欠落が、§13.3 には実装に存在しない ID（`2.3T` / `2.3TC` / `3.0T` / `3.0TC`）と Step ID 体系の系統的な不一致（表の `1.2` が実装の `1.3` を指す等）が残存していた。あわせて §13.2 / §13.3 / §13.7 の Step ID・タイトル・依存・Fan-out・生成物を registry へ同期し、コンテナ Step は FR-WF-OUT-04 に基づき §13.11 と同じ方針で表から省いた。AAGD Step 6 / 7 は registry へ登録済みだが対応する規範要件が本書に無いため、事実を TBD-26 として記録した |
| 2.45 | 2026-08-23 | **FR-WF-AAGD-08 / 09 新規 / TBD-26 解消**: AAGD Step 6（検索経路の適正化実測）と Step 7（Microsoft 365 / Teams 公開）の成果物契約を規範化した。両 Step は [hve/artifact_validation.py](hve/artifact_validation.py) の決定的検証、[hve/runner.py](hve/runner.py) の成果物ゲート、共有 Prompt の固定フォーマットによって実装側では既に契約が確定していた一方、規範文書側には対応する要件がなく、変更時の判断根拠を持てなかったことを根拠とする。測定条件 / 公開条件ラベル各 8 件、比較表 / 公開表の列構成と最小行数（それぞれ 2 行以上 / 1 行以上）、判定語彙 4 値（`KEEP` / `DOWNGRADE` / `INSUFFICIENT` / `NOT_MEASURED`、`PUBLISHED` / `PENDING_APPROVAL` / `NOT_SELECTED` / `FAILED`）、未実測値の記載禁止、公開メタデータへの secret 混入禁止を固定した。新しい制約は追加していない |
| 2.46 | 2026-08-23 | **TBD-27 解消（FR-MAINT-07 適用、振る舞い変更なし）**: CLI 入口（[hve/__main__.py](hve/__main__.py)）と Orchestrator（[hve/orchestrator.py](hve/orchestrator.py)）に重複していた Workflow パラメータ既定値 7 件を [hve/workflow_registry.py](hve/workflow_registry.py) の公開定数へ集約し、両モジュールを alias import へ変えた。値が一致している間は既存テストで検出できないため、リテラルによる再宣言を AST で拒否する契約テストを追加した。ARD の既定ステップ選択で同型の乖離（CLI `["2","3","4"]` / Orchestrator fallback `["1","2","3"]`）が実際に発生していたことを根拠とする |
| 2.47 | 2026-08-24 | **§13.13 G-DIFF 詳細化・実装**: HVE 管理 PR の実変更パスを GitHub Pull Request Files API から全ページ取得し、Workflow registry / fan-out / prefix / optional template / constrained placeholder の閉じた policy と照合する差分ゲートを規範化した。通常 PR と PR 非作成 local run は `N/A`、識別矛盾・未知 marker・不正 path/status・rename/copy旧path欠落・3,000件超・pagination件数不一致・validator/API失敗は `BLOCKED` とする。Cloud は base SHA の trusted validator だけを実行し subject head はデータ専用とする。CLI / GUI PR作成後のlabel付与、Cloud required check、auto-approve/mergeを同じ判定へ接続し、auto-approve側では `G-DIFF` completed/successの欠落、pending check、check-runs API/応答不正もfail-closedとした。利用者向けoverrideは追加していない |
| 2.48 | 2026-08-25 | **§6.12 新設（FR-GUI-23 新規）**: GUI が起動する HVE サブプロセスの標準入力を対話不能にすることを必須化した。[hve/gui/state_bridge.py](hve/gui/state_bridge.py) `launch_orchestrator` と [hve/gui/autopilot/child_launcher.py](hve/gui/autopilot/child_launcher.py) `AutopilotController._default_popen` が `stdin` を指定せず、ターミナルから起動した GUI の端末標準入力を子プロセスへ継承させていたため、Work IQ 認証 preflight の `input()` へ到達した ARD 実行が応答不能のまま停止した実測を根拠とする。GUI 側に入力経路が無く、プロンプト文字列も改行を伴わないため GUI のログペインにも表示されず、利用者からは無反応に見えていた。CLI 単体実行の対話可否判定（FR-CLI-78 の `sys.stdin.isatty()`）は変更しない |
| 2.49 | 2026-08-25 | **§3.13 新設（FR-MCPLOG-01〜03 新規）**: Copilot SDK セッション経由の MCP 入出力を、表示用の切り詰めを行わない全文ログとして `work/run/<run-id>/mcp-<サーバー名>.log` へ保存する契約を追加した。従来、MCP tool の引数・結果は実行面へ要約表示されるだけで永続化されず、Work IQ へ送るプロンプトも [hve/console.py](hve/console.py) `workiq_prompt` が verbosity に応じて 800 / 10,000 文字で切り詰めた表示しか残らないため、利用者が同じプロンプトを Microsoft 365 Copilot Chat で再利用する手段が無かったことを根拠とする。記録範囲を SDK イベントが公開する範囲に限定し（MCP サーバープロセスは Copilot CLI ランタイムが起動するため HVE は生の JSON-RPC フレームを取得できない）、`ToolExecutionCompleteData` が MCP サーバー名を持たないことから完了イベントは `tool_call_id` 相関でのみ帰属させ、相関できない完了の記録を禁止した。作業ディレクトリを共有する子プロセスでのレコード破壊を避けるため、`HVE_GUI_SESSION_ID` 非空または `HVE_STATS_STREAM` 真値時の `-<pid>` 分離を規定し（GUI Autopilot 子は前者だけ、CLI Autopilot 子は後者だけを継承するため両方を条件とする）、新規 CLI オプション・設定項目・環境変数の追加を禁止した。本ログは prompt / 引数 / 応答本文を意図的に保持するため FR-RTO-04 の allowlist を適用しない一方、認証情報のマスクは既存実装の再利用に限定した（FR-MAINT-07） |
| 2.50 | 2026-08-25 | **§6.13 新設（FR-GUI-24〜28 新規）/ §2 UC-06 改訂・UC-07 新規 / §5.2・§8 改訂**: HVE GUI の GitHub Issue / Pull Request 連携を規定した。(1) 起動時に `GH_TOKEN` / `GITHUB_TOKEN` 未設定なら `gh auth token` でトークンを解決し、取得できない場合だけログイン導線を 1 回提示する（拒否可能。認証完了を GUI 起動の前提にしない）。従来 GUI は認証状態を起動時に一切確認せず、設定画面のボタンを押した利用者だけが GitHub 連携を有効化できていたことを根拠とする。(2) Workflow 実行時の Root Issue を「新規作成」と「既存 Issue へ連携」から選べるようにし、`--issue-number` で伝達する。従来 `--create-issues` は常に Root Issue を新規作成しており、既存 Issue へ紐付ける手段が存在しなかった。取得失敗時は fail-closed とし新規作成へ暗黙フォールバックしない。(3)(4) Issue / PR の一覧・詳細・コメントを閲覧し、Issue のタイトル / 本文 / 状態の編集とコメント投稿・自コメント編集、PR への会話コメント投稿を GUI から行えるようにした。自動ポーリング、行単位レビューコメント、Approve / Request changes、ラベル・担当者・Projects の編集、GUI からの PR 新規作成は対象外とする。(5) GitHub アクセスは [hve/github_api.py](hve/github_api.py) を単一の情報源とし、GUI 専用 HTTP クライアント・`gh` サブプロセス・別 SDK の新規導入を禁止した（FR-MAINT-07） |
| 2.51 | 2026-08-25 | **FR-CLI-76 改訂 / §5.13 新設（FR-CLI-81 新規）**: (1) FR-CLI-76 の受入範囲へ [hve/orchestrator.py](hve/orchestrator.py) `_create_session_with_auto_reasoning_fallback` が生成する全セッション（Work IQ 専用 4 経路を含む）を追加した。当該ヘルパーは runner の同名関数と別実装でリポジトリ宣言を読まず `enable_config_discovery` を常に `True` としており、ARD の `target_business` 生成・Fleet wave 親・Code Review Agent の各セッションが、Work IQ 設定の有効・無効に関わらずプラグイン由来の `workiq` サーバを自動探索で取り込みうる状態だったことを根拠とする。あわせて FR-CLI-79 の `azure` 除外を適用するため当該ヘルパーが Workflow ID を受け取れることを必須化し、縮約実装を runner の単一ヘルパーへ限定した（FR-MAINT-07）。(2) FR-CLI-81 を新設し、Work IQ 認証確認が非対話環境で失敗したときに実行を停止せず当該実行に限り Work IQ を無効化して続行することを必須化した。GUI 子プロセスの標準入力が対話不能である（FR-GUI-23）ため常に停止になっていたこと、および `--workiq-draft` が `workiq_enabled` を同時に有効化するため利用者が Work IQ を無効にしたつもりでも停止しうることを根拠とする |
| 2.52 | 2026-08-25 | **FR-CLI-31 / FR-GUI-01 改訂 / §5.14 新設（FR-CLI-82 新規）**: GitHub 書き込みを伴うローカル実行について、repo / token / base branch / origin remote / remote branch の整合性を最初の Agent session・モデル呼び出し・branch 作成より前に単一実装で検査し、不整合を全件報告して fail-closed とする契約を追加した。存在しない remote branch をローカル branch へ暗黙 fallback しないこと、`--dry-run` でも検査すること、通常のローカル実行へ GitHub 接続を要求しないこと、および Prompt 自由記述欄を内容検査から除外することを明記した。GUI Step 1 はローカル判定を `SETTING` / `AUTH` として表示し、remote 照会は UI thread で行わず子プロセスの共通 preflight へ委譲する |
| 2.53 | 2026-08-25 | **§6.14 新設（FR-GUI-29 新規）**: GUI の QA 回答ダイアログへ、質問票全文と Work IQ 用プロンプトをクリップボードへ複製する 2 操作を追加する契約を規定した。質問票の整形は [hve/qa_merger.py](hve/qa_merger.py) `QAMerger.render_merged`、Work IQ テンプレートの取得は [hve/workiq.py](hve/workiq.py) `get_workiq_prompt_template` を単一の情報源として再利用し、GUI 側へ整形実装やテンプレート本文を複製してはならないこととした（FR-MAINT-07）。クリップボードへの書き込みだけを行い Work IQ への送信・認証・MCP 呼び出しを行わないこと、新規の CLI オプション・設定項目・環境変数・IPC スキーマ変更を追加しないこと、既存の回答送信経路（FR-GUI-08）を変更しないことを明記した。[hve/gui/copy_button.py](hve/gui/copy_button.py) `CopyButton` は `QToolButton` を継承し、既定 `toolButtonStyle` が `ToolButtonIconOnly`（PySide6 実測で確認）であるため `setText("📋")` が描画されず、そのまま 2 個並べると利用者が操作を識別できないため、ラベル併記と支援技術向けの名前を必須とした。クリック後 tooltip の文言は他の 9 箇所の呼び出しへ波及するため国際化の対象外とした。あわせて、本操作が FR-QA-03 の自動統合経路と送信内容で一致しない 3 点（1 問単位の箇条書きに対する全問テーブル、重要度フィルタと `workiq_max_draft_questions` の不適用、既定テンプレートの応答上限 5 件）と、`render_merged` の出力に起因する見出しレベルの逆転および表セルのエスケープを、専用整形を新設せず既知の制約として扱うことを規定した |
| 2.54 | 2026-08-25 | **§6.13 改訂（FR-GUI-30〜34 新規 / FR-GUI-26・28 改訂）/ §2 UC-07 改訂・UC-08 新規**: GUI の GitHub 連携へ 5 件の契約を追加した。(1) FR-GUI-30: Issue 本文・コメントの Markdown 入力欄へ書式挿入 9 種とプレビューを備える共通ウィジェットを必須化し、原文保持（リッチテキストからの再生成禁止）と [hve/gui/markdown_preview/markdown_html_renderer.py](hve/gui/markdown_preview/markdown_html_renderer.py) の再利用を規定した。従来の入力欄は素の複数行テキスト入力のみで、Markdown 記法を暗記していない利用者が投稿内容を確認する手段を持たなかったことを根拠とする。(2) FR-GUI-31: リポジトリ確定時の 1 回限りの初期取得、0 件時に絞り込み状態を提示する義務、クライアント側の絞り込み欄を必須化した。実測で、既定の絞り込み `open` と初期取得の不在により、`open` が 0 件・`closed` が 610 件のリポジトリでは画面が常に空となり、利用者からは取得失敗と区別できなかったことを根拠とする。あわせて FR-GUI-26 の「自動ポーリング禁止」が周期処理を指し 1 回限りの初期取得を含まないことを明文化した。(3) FR-GUI-32: 実行タスクへ関連付ける Issue / Pull Request を一覧から選べることを必須化し、Pull Request の関連付けを GUI セッション内に限定して CLI オプション・`SDKConfig` へ波及させないことを規定した。従来は Issue 番号の直接入力だけで、Pull Request を指定する経路が存在しなかった。(4) FR-GUI-33: 実行面のコンソール出力を選択中 Pull Request へコメント投稿する契約を追加し、本文組み立てを副作用のない単独関数へ分離すること、総行数と掲載行数の明記、ANSI エスケープ除去、コードフェンス長の動的決定を規定した。GitHub の Issue コメント作成 API は本文の最大長を公開していないため全文投稿を前提にしないこととした。(5) FR-GUI-34: 現在のローカルブランチの push と、`merged` / `closed` の Pull Request の head ブランチのリモート削除を GUI から行えることを必須化した。push と削除を別操作とし、削除はリモートのみ・確認必須とし、ローカル削除は FR-CLI-34 の単一実装に委ねる。FR-GUI-27 の PR 新規作成禁止は変更しない |
| 2.55 | 2026-08-25 | **§5.8 改訂（FR-CLI-63〜65 新規）**: step-level Self-Improve の判定と `TaskGoal` の宣言・実装齟齬を是正する契約を追加した。(1) FR-CLI-63: [hve/runner.py](hve/runner.py) Phase 4d の `after_quality_score` / `degraded` / `verification_phases` を LLM 応答 JSON で上書きすることを禁じ、判定を [hve/self_improve.py](hve/self_improve.py) `_build_verification_result()` の単一実装へ委譲することを必須化した（FR-MAINT-07）。LLM が `degraded=false` を返すと実測デグレード時に Phase 4f のループ停止が働かず、`learning-NNN.md` に実測と異なる値が残ることを根拠とする。(2) FR-CLI-64: `scan_codebase()` に `ScanResult.security_status` の producer 実装を必須化した。`_scan_gate_failure()` が当該キーの `FAIL` で停止する契約を持つ一方、設定側が存在せず本番経路で当該分岐が発火しないことを根拠とする。検査パターンは `_build_verification_result()` と同一の単一定義とし、対象は解決済み scope 内のファイルに限る。(3) FR-CLI-65: `success_criteria` にカバレッジ 70% 以上を宣言する `asdw-web` / `adfdv` へ `criterion_definitions` の criterion を必須化し、あわせて `metric_status.coverage_pct` の設定を必須化した。カバレッジは pytest 実行結果からのみ抽出されるため、test 未実行時の `0.0` を未達として扱ってはならないことを根拠とする |
| 2.56 | 2026-08-25 | **§5.1 / §3.4 / §4.7 改訂（FR-CLOUD-41 新規）**: 実装済みだが要求定義書に宣言されていなかった機能群を宣言し、`FR-MAINT-01` / `FR-MAINT-04` のトレーサビリティ対象へ戻した。(1) §5.1 のサブコマンド表が 5 件（`run` / `orchestrate` / `qa-merge` / `workiq-doctor` / `emit-prompt`）しか宣言していない一方で `_build_parser()` は 11 件を登録しており、同一文書内の `FR-CLI-77` が `login` / `pricing` / `toolsearch` / `ingest-docs` / `gui` を列挙していて矛盾していたため、表を実装の全件へ揃え、[hve/tests/test_requirement_subcommand_parity.py](hve/tests/test_requirement_subcommand_parity.py) で parity を機械検査するようにした。(2) `FR-STATE-01` が 5 種の状態ラベルしか宣言していない一方で [.github/labels.json](.github/labels.json) は `{prefix}:human-required` / `{prefix}:human-resolved` を 11 プレフィックス分（計 22 件）登録していたため、HITL ラベルと対象プレフィックス、および `_make_state_labels` の生成対象外であることを明記した。(3) 本番 Cloud 経路で稼働する [.github/workflows/auto-blocked-to-human-required.yml](.github/workflows/auto-blocked-to-human-required.yml) / [.github/workflows/auto-human-resolved-to-ready.yml](.github/workflows/auto-human-resolved-to-ready.yml) に要件 ID が無く、§13.13 が blocked を「手動介入の対象とする」と述べるにとどまっていたため、§4.7 に `FR-CLOUD-41` を新設して SLA 閾値・昇格条件・復帰時の 3 ラベル削除・対象プレフィックスの同一性を規定した。実行時の観測可能な挙動は変更していない |
| 2.57 | 2026-08-25 | **§5.4.3 新設（FR-CLI-84 / FR-CLI-85 新規）/ FR-WF-ARD-02 改訂**: Phase 1 メインタスクの送信前にプロンプトの UTF-8 バイト数を計測し、HVE 内部予算と照合して Phase 1 のモデル呼び出し回数を 1 回または 0 回に確定する契約を追加した。根拠は、Copilot API が `The request is too large to send through CAPI Responses. Try shortening the conversation or prompt. (32.7 MB request; 5.0 MB limit)` を返して Step が失敗した実測である。既存の `context_injection_max_chars`（既定 20,000 文字）は Phase 0 事前 QA へ注入する補助コンテキストにしか適用されず（[hve/runner.py](hve/runner.py) `_run_pre_execution_qa`）、Phase 1 の最終プロンプトには一切のサイズ検査が無かったことを根拠として明記した。(1) FR-CLI-84: 計測をバイト単位とすること、判定を受領プロンプト単体と最終プロンプトの 2 箇所で行うこと、予算超過時に Phase 1 のモデル呼び出しを 0 回とすること、自動切り詰め・自動要約・複数ターン分割・自動再試行を禁止すること、通知へ本文と認証情報を含めないこと（FR-RTO-04 / NFR-SEC-01）、新規の CLI / GUI / 環境変数を追加しないこと、および予算値を GitHub の公開仕様値として記述しないことを規定した。(2) FR-CLI-85: `additional_prompt` と markdown-query 強制ブロックが最終プロンプトへ高々 1 回しか現れてはならないことを規定した。従来 [hve/orchestrator.py](hve/orchestrator.py) が Step プロンプト末尾へ連結した同じ値を [hve/runner.py](hve/runner.py) が再度前置し得たため、指示を変えないままリクエストサイズだけが増えていた。(3) FR-WF-ARD-02 へ、パス指定 `target_business` の展開結果をファイル本文ではなくパス参照（相対パス一覧・件数・合計バイト数・スキップ理由）とすること、既存の安全制約と直接テキストの扱いを変えないこと、および Body テンプレートが `{target_business}` を 1 箇所だけ展開することを追加した。従来は最大 5 MiB の本文を Prompt へ埋め込み、かつ同一値を 2 箇所へ展開していた |
| 2.58 | 2026-08-25 | **FR-CLI-10 改訂 / §5.1 `run` 行訂正**: 引数なし起動の既定を実装へ合わせた。旧記述は「引数なしは対話 wizard を起動する」だったが、[hve/__main__.py](hve/__main__.py) `main()` の `args.command is None` 分岐は `run_gui()` を返し、`ImportError` 時にのみ `_cmd_run_interactive` へフォールバックする。同一文書内の `FR-CLI-77` は既に「引数なし起動（GUI が既定）」と記述しており、`users-guide` 5 ファイルと `hve.cmd` / `hve.sh` ランチャーも GUI 既定を前提としていたため、**要件側 2 箇所の記述が実装の変更へ追随していなかった**と判定した。実行時の振る舞いは変更していない |
| 2.59 | 2026-08-25 | **§3.4 FR-STATE-04 新規 / §5.16 新設（FR-CLI-86 新規）**: run をまたぐ状態が保持されないことを根本原因とするギャップ群へ対処するため、Workflow 進捗（どの Step が成功したか）を `hve/.run-progress.jsonl` へ追記保存し、`--resume-run <run-id>` で成功済み Step を除外して再実行できるようにした。**§5.6 が全廃した SDK セッションの復元は復活させない**（廃止理由は SDK のセッション管理であり、本項が扱うのは HVE 自身が所有する進捗だけ）。記録は既存の `on_step_complete` フック経由とし、[hve/dag_executor.py](hve/dag_executor.py) へ新規の記録経路を追加していない（FR-MAINT-07）。進捗記録の無い run-id は fail-closed とする |
| 2.60 | 2026-08-25 | **§5.17 新設（FR-CLI-87 新規）**: 「無人実行 vs 人間の判断点」を根本原因とするギャップ群へ対処するため、`--approval-gates`（既定無効）による Wave 境界の同期承認を追加した。対象は `StepDef.approval_gate` を宣言した Step を含む Wave とし、ASDW-WEB Step 1.3（最初の live Azure write）へ宣言した。非対話実行では確認を出さず `blocked` で停止する。承認要求は既存の `on_wave_start` フック経由とし、同フックの汎用例外握り潰しと `run_workflow` の `except BaseException` のいずれよりも前で承認拒否を扱う（そうしないと拒否が exit 0 へ縮退する）。GUI からの承認は FR-GUI-23（子プロセスの標準入力を対話不能とする）のため本項の対象外とした |
| 2.61 | 2026-08-25 | **§3.3 FR-DAG-09 新規 / §5.18 新設（FR-CLI-88 新規）**: 残存ギャップの根本原因のうち 2 件へ対処した。(1) FR-DAG-09: レビューから実装への差戻しを **DAG の外側**に置くことを規定し、`StepDef.rework_targets` の静的宣言と `FR-WF-CONF-03` の `FAIL` だけを引き金とする決定層を追加した。`FR-DAG-01` の依存パターン 4 種は変更せず、測定表の解析は既存実装を再利用する（FR-MAINT-07）。再実行は再起動に委ね、`run_workflow` の DAG 構築部を再入可能へ作り替えない。(2) FR-CLI-88: PR / Issue（障害記録）の参照経路を `.github/.mcp.json` への宣言と定め、`mdq` / `cq` の索引契約を拡張しないこと、GitHub 系サーバへ `tools: ["*"]` を用いず参照系だけを列挙することを規定した |
| 2.62 | 2026-08-26 | **FR-CLI-84 / FR-WF-ARD-02 敵対的レビュー反映**: Phase 1 予算判定を受領時・Phase 0 前の確定成分・事前 QA 後の最終 Prompt の 3 段階へ改訂し、成分別 UTF-8 バイト数の合計と最終 Prompt の一致、予算超過時の `step_end(failed)`、dry-run 非影響を規範化した。ARD のパス manifest は `base_dir` 外を子孫列挙前に拒否し、外部パス名・例外本文を固定表現へ匿名化し、symlink cycle の `RuntimeError` を診断へ降格すること、および `skipped` / `errors` を各 50 件 + 省略マーカーへ制限することを追加した。従来の実装は外部 symlink 子を `rglob` で列挙後に拒否し、絶対パスや外部 basename を Prompt へ含め得たほか、診断件数が無制限だったことを根拠とする |
| 2.63 | 2026-08-26 | **§3.3 FR-DAG-09 改訂 / §6.15 新設（FR-GUI-38 新規）**: 実装済みでありながら利用者の実行経路から到達できない 2 件へ対処した。(1) FR-DAG-09: `rework_targets` を宣言する Step が 0 件で決定層が一度も発火しない状態だったため、`asdw-web` Step 5.3 へ宣言し、決定結果を DAG 実行後に提示する義務を追加した。自動再実行は導入せず、再起動委譲の方針は変更しない。(2) FR-GUI-38: `FR-CLI-86` の `--resume-run` が CLI だけに公開され GUI から指定できなかったため、オプション入力と設定保存を規定した。run-id の実在判定は CLI 側の fail-closed へ委ね、GUI へ二重実装しない |
| 2.64 | 2026-08-26 | **§12 TBD-36 追加**: Cloud Agent Orchestrator から `FR-CLI-86`（`--resume-run`）を利用できないことを既知の制約として記録した。`FR-STATE-04` の進捗ストアが利用者ローカル領域限定であり Cloud の Issue / PR ベース実行からは到達できないため、Cloud 実行が `FR-CLI-87` の既定挙動または失敗で停止した後は Sub-Issue の再実行以外に引き継ぎ手段が無い。Cloud run とローカル `run_id` の対応付け、または Cloud 専用の進捗永続化はいずれも新規設計を要するため、要件不備ではなく PoC/設計判断待ちの TBD として保留する |
| 2.65 | 2026-08-26 | **§6.16 新設（FR-GUI-39 新規）**: GitHub Hub の Issue 作成と、GUI から起動した Orchestrator の PR 作成で、本文を GitHub Copilot CLI に問い合わせてタイトルを自動生成する機能を追加した。Issue は明示生成または空 title での作成時に生成し、入力済み title は自動上書きしない。PR 直接作成 UI は追加せず、GUI 子プロセスだけが作成直前に生成する。単一 service、tool 無効、空一時ディレクトリ、入力 12,000 文字 / 出力 120 文字、Issue の fail-closed と PR の既存 title fallback、token 消費の明示を規定した |
| 2.66 | 2026-08-26 | **§5.19 / §6.17 改訂（FR-CLI-89 / FR-GUI-44〜49 新規、FR-GUI-26 / 27 / 28 / 31 改訂）**: GitHub Hub に既存 Issue metadata 編集、PR review 表示・提出、行単位 review comment、check-runs 表示と明示マージ、一覧ページング、Copilot cloud agent 割当を追加する契約を定義した。CLI は `--assign-copilot-agent` で新規 Root Issue を割り当てる。Projects v2、native Auto-merge、merge queue、Agent Tasks API は対象外のまま維持した。 |
| 2.67 | 2026-08-26 | **§5.20 新設（FR-PROMPT-01〜10 新規）／§5.1 サブコマンド表へ `prompt` 追加**: Cloud / GUI / CLI に並ぶ第 4 の利用面として Prompt 版を規定した。自然言語 → request v1 の変換は repository Agent Skill が担い、HVE Python は request を再検証して既存 `orchestrate` へ委譲する。`prompt plan` は書き込みなしで dry-run 計画と SHA-256 を提示し、`prompt run` は `--expected-sha256` 一致時だけ argv + `shell=False` で順次実行する。非 canonical な入力名は実行時の入力別名として扱い、コピーと I/O 契約の書き換えを禁止した。Cloud からの Prompt request 実行、任意 DAG、glob / ディレクトリ別名、永続 approval store は本版の対象外とした。 |
| 2.68 | 2026-08-26 | **FR-PROMPT-03 / FR-PROMPT-10 改訂（NL-only 規約）**: Prompt 版の利用者が自然言語だけで計画取得から実行までを完了できることを規定した。根拠は、[hve/prompt_execution.py](hve/prompt_execution.py) の計画提示文が利用者へ `hve prompt run --expected-sha256 <hash>` の手実行を指示し、[users-guide/prompts/](users-guide/prompts/) の貼り付け用依頼文自体に CLI サブコマンド名が埋め込まれていた実測である。(1) FR-PROMPT-03 へ、提示文と失敗メッセージが利用者へコマンド・request path・SHA-256 の入力を求めないことを追加した。(2) FR-PROMPT-10 へ、CLI 起動と hash 転記を Agent が代行すること、貼り付け用 Prompt 例の本文へ CLI サブコマンド名を含めないこと、承認を自然言語で受け取り曖昧な同意は再確認することを追加した。**機構は変更していない**。FR-PROMPT-04 の `--expected-sha256` 一致ゲート、FR-PROMPT-02 の「HVE Python へ自然言語 parser を追加しない」制約はいずれも維持する。 |
| 2.69 | 2026-08-26 | **§4.8 新設（FR-CLOUD-42 新規）**: 定期運用 Workflow の削除方針を規範化した。FR-CLOUD-41 の毎時 HITL エスカレーションだけを `schedule` の例外として許可し、AAS / QA のタイムアウト監視は手動実行、ラベル整合性監査は手動と Issue イベント駆動へ限定した。旧週次 `plan.md` 全件監査と旧日次 TDD メトリクス集計の不在、QA 手動監視の無言 skip 禁止、AAS 手動入力の GitHub API 副作用前の正整数検証と取得上限 1,000 件を固定した。 |
| 2.70 | 2026-08-27 | **FR-GUI-26 / 28 / 44〜47 敵対的レビュー反映**: comment ID と metadata 更新応答の fail-closed 検証、Retry-After / retry 上限境界、review / review comment の全ページ取得、Issue metadata 保存中と Pull Request review 提出中の mutation 直列化、merge 失敗後の check-runs 再取得を規範化した。 |
| 2.71 | 2026-08-27 | **§3.14 新設（FR-PROMPT-SRC-01 / 02 新規）**: HVE が所有する固定 model-facing prompt 本文の正本を `.github/prompts/**` へ一本化した。flat Agent prompt に加え、active Step body を `steps/`、fan-out addendum を `fanout/`、Cloud 実行指示を `cloud/`、その他の内部 prompt を用途別 `runtime/` へ分類する。Python / Workflow / shell / PowerShell は prompt の選択・安全な読込・動的値補間だけを担い、固定本文を重複保持しない。読込の単一実装を [hve/prompt_loader.py](hve/prompt_loader.py) とし、必須 prompt の欠損・空・不正な path 解決は model call / SDK session / Copilot assignment の前に fail-closed で停止させる。`load_prompt(agent_name)` の flat Agent 互換は維持し、新規 manifest / flag / 環境変数 / CLI option / 外部依存 / hot reload は追加しない。 |
| 2.72 | 2026-08-27 | **FR-GUI-26〜28 / 45 / 46 / 48 改訂**: GitHub一覧・会話comment・review・review commentの継続取得を手組みpage番号から検証済み`Link: rel="next"` cursorへ変更し、GUI一覧の初回順序を`created desc`へ安定化した。`api_call`の既定JSON戻り値は維持し、応答headerのopt-in取得、cursorのorigin/path/cycle検証、失敗時cursor保持、context変更時破棄を規定した。同時新規作成・state変更・削除による母集合変化はsnapshot API不在の残存制約として明示更新へ委ねる。 |
| 2.73 | 2026-08-27 | **§5.21 新設（FR-LOCAL-SURFACE-01 新規）／FR-PROMPT-02・FR-PROMPT-07 改訂**: ローカル 3 面（直接 CLI / GUI / Prompt 版）の設定パリティを shared setting・workflow param・semantic alias・derived・excluded の 5 分類として規範化した。根拠は、GUI 設定画面に存在する Agentic Retrieval 6 項目と `enable_tool_search` が `defaults()` / `_SECTION_FIELDS` へ未登録で永続化されず、保存キー `cloud_session_repository_branch` が `OrchestrateArgs.cloud_session_branch` と名前不一致のため Prompt 版で無言に失われ、`create_remote_mcp_server` / `tdd_max_retries` が対話 wizard と Cloud Issue Form からしか指定できなかった実測である。FR-PROMPT-02 の allowlist を本分類へ接続し、FR-PROMPT-07 へ保存 key 名と `OrchestrateArgs` フィールド名の明示対応を追加した。新しい設定レジストリ・環境変数・設定ファイル形式は追加せず、`OrchestrateArgs` を唯一の argv 変換器として再利用する。分類の網羅性は機械検査で担保する。 |
| 2.74 | 2026-08-27 | **FR-GUI-26 / 28 / 48 敵対的レビュー改訂**: RFC 8288 / RFC 9110 と実行時raceの再監査により、cross-origin redirectへの認証転送禁止、複数`Link` field lineの保持、先頭`rel`優先、quoted-pair、`anchor`、空list要素、page必須番号、会話comment schema、一覽と詳細・mutationの独立世代を規範化した。重複していた改訂版2.71を2.72以降へ連番訂正した。 |
| 2.75 | 2026-08-27 | **FR-LOCAL-SURFACE-01 (a) 改訂**: shared setting の列挙を実装の `ALLOWED_SETTINGS_OVERRIDES` と同じ 26 key へ揃え、両者の過不足なき一致を機械検査対象とした。根拠は、FR-PROMPT-02 が「`settings_overrides` の allowlist は FR-LOCAL-SURFACE-01 (a) の shared setting 集合とする」と規定する一方、本節の列挙が 9 key、実装 allowlist が 26 key で乖離していた実測である。追加した 17 key はいずれも既に `defaults()` / `_SECTION_FIELDS` / `OrchestrateArgs` / allowlist の 4 箇所へ登録済みで、[users-guide/hve-prompt-getting-started.md](users-guide/hve-prompt-getting-started.md) と [.github/skills/hve-prompt-edition/SKILL.md](.github/skills/hve-prompt-edition/SKILL.md) も `model` 等を共有設定として説明していたため、実装・利用者文書の変更を伴わない。新しい設定 key・環境変数・レジストリは追加していない。 |
| 2.76 | 2026-08-27 | **FR-LOCAL-SURFACE-01 改訂**: 同一 Workflow・同一保存設定・面固有 runtime 値なしの条件で、GUI と Prompt 版が生成する argv 配列の要素数・順序・値の完全一致を機械検査対象とした。`asdw-web` の GUI argv が AKM 専用の `sources` / `target_files` / `force_refresh` / `custom_source_dir` を含み、Prompt 版が `auto_qa` 無効時にも `qa_answer_mode=autopilot`、自己改善無効時にも `self_improve_max_iterations` / `self_improve_target_scope` / `self_improve_goal`、SDK 既定と同じ `tool_search_ranking=sdk` を明示していた実測を根拠とする。比較入口と GUI セッション固有値・`qa_answer_mode=user` の除外条件を本文に固定した。入力別名は FR-PROMPT-08 の Prompt / 直接 CLI 専用入口として GUI 入力欄の追加対象から除外し、既存の `OrchestrateArgs` 受け口は維持する。新しい設定 key・CLI flag・環境変数・抽象レイヤーは追加しない。 |
| 2.77 | 2026-08-28 | **FR-PROMPT-10 改訂**: Prompt 版の承認前実行計画と承認後の Step 内 `plan.md` を別の計画層として定義し、提示済み計画への明示承認と FR-PROMPT-04 の SHA-256 一致後は、仲介 Agent が単独実行モードでも `task_scope=multi` / `context_size=large` を理由に `hve prompt run` への委譲を禁止しないことを規定した。例外を既存 `orchestrate` への委譲だけに限定し、仲介 Agent の直接実装、未選択 Workflow の暗黙追加、rollback、失敗後の継続、既存の認証・権限・Azure・QA・デプロイ承認ゲートの迂回を禁止した。Python 実行核は既に非 dry-run 委譲と FR-WF-OUT-01 の成果物ゲートを持つため変更対象外とした。 |
| 2.78 | 2026-08-28 | **FR-PROMPT-04 / 05 / 10 敵対的レビュー反映**: 「子プロセス」を実行対象である `orchestrate` 子プロセスへ限定し、HEAD 取得用 `git rev-parse` との矛盾を解消した。HEAD commit を取得できない場合は `unknown` を hash に使わず fail-closed とした。承認後は controller が提示済み SHA-256 を `hve prompt run` へ渡し、HVE が再計算値との一致を確認してから `orchestrate` へ委譲する時系列へ訂正した。FR-WF-OUT-01 は実行完了時の存在ゲートであり、既存成果物が今回更新されたことまでは証明しない境界も明記した。 |
| 2.79 | 2026-08-28 | **FR-CLI-34 改訂 / FR-MODEL-07 改訂**: 実装済みだが未宣言だった 2 点を明文化した。(1) FR-CLI-34 の共通 cleanup core が実行する `git checkout` / `git branch -D` の subprocess に `encoding="utf-8"` の明示を必須化した。Windows 既定 locale（cp932）では非 ASCII 出力の decode が `UnicodeDecodeError` になり得ることを根拠とする。(2) FR-MODEL-07 へ `hve/copilot-sdk.lock` 自体が UTF-8 / LF / BOM なしを維持しなければならないこと、および `--upgrade-sdk` / `-UpgradeSdk` の書き換えが当該形式を保つことを追加した。実行時の観測可能な挙動は変更していない。 |
| 2.80 | 2026-08-30 | **FR-CLOUD-41 / 42 改訂**: GitHub.com 側で毎時起動していた HITL エスカレーションの `schedule` を停止し、`auto-blocked-to-human-required.yml` を明示的な `workflow_dispatch` 専用へ変更した。repository-managed Workflow 全体で有効な `schedule` を禁止し、SLA 閾値・昇格条件・復帰経路は維持した。 |
| 2.81 | 2026-08-31 | **NFR-CONC-02 / FR-CLI-90 / FR-GUI-50 改訂**: durable resume の実機受入で検出した3境界を既存意図の詳細条件として固定した。(1) 同じowner/generationの未期限切れ取得tokenは、自身のtransitionでstate versionが進んだ後もheartbeat/releaseへ使用できる。(2) status-only DAG callbackはcommit済みMain checkpoint metadataを保持し、legacy split-fork phaseは明示有効時だけ記録する。(3) GUI launcherの`--workbench off`補完は`orchestrate` childだけに適用し、`hve resume`へ注入しない。 |

---

## 12. 未確定事項（TBD）

| TBD No. | 内容 | 確認方法 |
|---|---|---|
| TBD-01 | ~~リポジトリの確定 commit SHA~~ → **解消（v1.0.4）**: §1.4 に `48326f3ea5fa55b65c262a4eb6e0cccea261bd6f` を記録済み | `git rev-parse HEAD` |
| TBD-02 | ~~`SDKConfig` dataclass の完全フィールド一覧~~ → **解消（v1.0.4、v1.1 追随）**: §8.2 に主要フィールドを列挙し、完全リストは [hve/config.py](hve/config.py) `SDKConfig` クラス定義を正とする。旧 `_SAFE_CONFIG_FIELDS` と snapshot 復元は Resume 全廃に伴い削除済み | `hve/config.py` 全文確認 |
| TBD-03 | ~~ADR-0002 / ADR-0003 のファイルパス~~ → **解消（v1.0.4）**: `docs/decisions/` 配下を走査した結果 ADR-0001（[docs/decisions/ADR-0001-agentic-retrieval-prerequisites.md](docs/decisions/ADR-0001-agentic-retrieval-prerequisites.md)）のみ存在し、ADR-0002 / ADR-0003 は未作成。本文中の ADR-0002 / ADR-0003 への参照は**計画上の仮名**として扱う（作成者未定） | `docs/decisions/` 配下を検索 |
| TBD-04 | ~~`users-guide/*.md` 各リンクの実在~~ → **解消（v1.0.4）**: `users-guide/hve-cli-orchestrator-guide.md` / `users-guide/web-ui-guide.md` / `users-guide/km-guide.md` を含む§10 参照リンクはすべて実在を確認済み | ファイル存在確認 |
| TBD-05 | 各 FR への個別受入基準の付与 → **保留（v1.0.4 時点でイスケジュー化推奨）**: 現状の FR-CLI-44〜51 は文章記述で、Given/When/Then 展開はテストとのトレーサビリティ表を設ける導入コストが大きい。個別 FR 改訂時に小さく始める方針としたい | 次版で Given/When/Then 形式に展開 |
| TBD-06 | ~~Cloud Orchestrator の ARD 対応有無の確定~~ → **解消（v1.6）**: **ARD を CLI / GUI 専用と確定**した（FR-WF-ARD-01）。根拠は (1) `auto-orchestrator-dispatcher.yml` の `trigger_map` に ARD は未登録で、専用の Issue Template / state-transition / `auto-ard-reusable.yml` も存在しない、(2) Cloud 対応を追加すると 30+ ファイル規模の新規作成が必要、(3) FR-CLOUD-06 で ASDW-WEB を Cloud dispatch から **削除** しており、Cloud 対象ワークフローを増やす方向とは逆。契約テストで dispatcher に ARD が現れないことを固定した。**v2.30 追記**: 根拠 (3) は失効した（FR-CLOUD-06 改訂により ASDW-WEB の Cloud 起動を再開し、FR-CLOUD-07 で AAR を Cloud dispatch 対象へ追加したため）。根拠 (1)(2) は現時点でも成立するため、ARD を CLI / GUI 専用とする FR-WF-ARD-01 の結論は維持する | 完了（追加作業なし） |
| TBD-07 | ~~AKM 以外の reusable workflow における `check_qa_skip` 同等チェックの有無~~ → **解消（v1.0.4、v2.16 改訂）**: `auto-knowledge-management-reusable.yml` / `auto-dataflow-dev-reusable.yml` / `auto-dataflow-design-reusable.yml` / `auto-app-selection-reusable.yml` / `auto-app-documentation-reusable.yml` / `auto-app-dev-microservice-web-reusable.yml` を含む主要 reusable workflow に `check_qa_skip` ジョブが存在する。旧記述では廃止した旧独立原本質問票処理を事前 QA 常時スキップの例外としていたが、FR-QA-03 / FR-CLOUD-24 により当該例外を廃止し、専用 Cloud 経路も同じ回答保存経路へ統合する | 各 `auto-*-reusable.yml` を確認 |
| TBD-08 | 外部 IF 要件 / データ要件 / エラー処理要件セクションの拡充 → **次版の大規模拡張 / 保留**: Resume 2 層トランザクション保護を扱った旧版では「ソース逆抽出で説明できる範囲」だけをカバーしていた。IF / データ / エラー処理を体系的に拡充するには Cloud / CLI 両方での実況検証が必要 | 次版で追加 |
| TBD-09 | 性能 KPI / SLA の数値目標 → **運用データ蓄積後 / 保留**: NFR-PERF-01〜04 は「上限・期待値」の記述に留め、実測で裏付けるのは実運用開始後とする。`work/run/` の実行データと GitHub Actions の `metrics` API をケーススタディとするコスト見積りが必要 | 運用データ蓄積後に設定 |
| TBD-10 | ~~`_normalize_model_with_warning` の実際の呼び出し経路~~ → **解消（v1.0.4）**: [hve/config.py](hve/config.py) `SDKConfig.__post_init__`（`model` / `review_model` / `qa_model` / `model_override` の正規化）、`SDKConfig.from_env`（環境変数 `REVIEW_MODEL` / `QA_MODEL` / `HVE_MODEL_OVERRIDE` の正規化）、[hve/__main__.py](hve/__main__.py) `_normalize_model_with_warning`（wizard モデル選択後の診断・上書き）の 3 経路で呼ばれる。テストは [hve/tests/test_config.py](hve/tests/test_config.py) | orchestrator.py / runner.py の参照点を確認 |
| TBD-15 | ~~`schema_version 2.0` 移行に伴う既存 `session-state/runs/` データの取扱い周知（破壊的変更）~~ → **解消（v1.0.3）**: [users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md) に「v1.0 アップグレード時の注意」セクション、[CHANGELOG.md](CHANGELOG.md) に Breaking 変更項目を追記済み | users-guide / CHANGELOG への案内追記 |
| TBD-16 | SDK 公式 `CopilotClient.list_sessions` / `get_session_metadata` API のバージョン互換性追跡 → **運用継続課題 / 保留**: SDK アップグレード時に regression 検知が主要手段。バージョン 0.x 間はシグネチャ変更リスクが存在し、現 `_get_copilot_sdk_version()` の major 一致チェックと `try/except` でカバーしている | Copilot SDK へのロックダウン / デグレーション検知 |
| TBD-17 | ~~`StepRunner._record_checkpoint` の呼び出しを runner 内の各 phase（main タスク / QA / review / self-improve）の完了タイミングに組み込む~~ → **解消（v1.0.1）**: 事前 QA / メインタスク応答受信 / Review フェーズ / Self-Improve 各イテレーションの 4 ポイントに組み込み済み。orchestrator.py で RunJournal を構築して StepRunner に注入する経路も整備済み | `runner.py` の 4 phase に `_record_checkpoint(step_id, marker)` を 1 行ずつ追加、`orchestrator.py` で `RunJournal(<run_dir>)` を build して `StepRunner(... , journal=...)` に渡す |
| TBD-18 | ~~ASDW-WEB Step 1.2 の template ↔ Prompt 逐語重複（当初 33 行）の解消~~ → **解消（v1.5・追加削減は不要と判断）**: 固定 TDD レポートスキーマの重複は [hve/tests/test_tdd_test_report_contract.py](hve/tests/test_tdd_test_report_contract.py) `_SCHEMA_DELEGATED_TEMPLATES` による Prompt への委譲で解消済み。残る 11 行 / 729 文字は **意図的な契約** であり削減してはならない。内訳は (1) `_STEP_SCOPED_TEMPLATE_TOKENS` が要求する Step 1.2 固有値（`- Workflow: asdw-web` / `- Step: 1.2` / `- Phase: RED` / `- Live-RED-Status: NOT_RUN` 等、generic プレースホルダでは表現不可）、(2) [hve/tests/test_asdw_data_testcoding_network_contract.py](hve/tests/test_asdw_data_testcoding_network_contract.py) が `injected.count(_STEP_1_2_RUNTIME_HEADING) == 2` で **2 箇所への出現を明示的に強制** する実行時必須契約 3 行、(3) 委譲先を指す節見出し。(1)(2) を削ると [hve/tests/test_asdw_data_contract_ssot.py](hve/tests/test_asdw_data_contract_ssot.py) が意図する双方向ドリフト検出が消滅する | 追加作業なし（現状維持が正） |
| TBD-19 | ~~名称スラッグ（`{screenNameSlug}` / `{serviceNameSlug}` / `{jobNameSlug}`）を含む Step の実行時ゲート復旧~~ → **解消（v1.6）**: 当初は「カタログに英名スラッグ列を追加」または「成果物命名を ID のみへ改める」のいずれかの契約変更が必要と見積もっていたが、単一 run（`ed3931b8`）の生成物が 3 形式に分岐する一方で全件が ID 接頭辞で始まるという実地の証拠から、**契約変更を伴わない prefix 存在ゲート**（FR-WF-OUT-10）で回復できることが判明した。AAD-WEB 2.1 / 2.2、ASDW-WEB 3.3、AKM 1 の 4 Step で検証を回復し、残る 3 Step は FR-WF-OUT-09 の allowlist へ理由付きで残す | 完了（追加作業なし） |
| TBD-20 | ~~mdq watcher の既定有効化~~ → **解消済み（実装確認）**: [hve/config.py](hve/config.py) `mdq_watch: bool = True` が既定 ON で、[hve/orchestrator.py](hve/orchestrator.py) `run_workflow` が `dry_run` 以外で `MdqWatcher` を起動し `atexit` で停止する。watchdog 未導入・起動失敗時は警告のみで本体実行を妨げない。Cloud Agent / GitHub Actions では `config.mdq_watch=False` で無効化する | 完了（追加作業なし） |
| TBD-21 | ASDW Step 1.3 の APP-009 依存の汎用化 → **feature として保留（欠陥ではない）**: [hve/workflow_registry.py](hve/workflow_registry.py) `ASDW_DATA_DEPLOY_SUPPORTED_APP_ID` と [hve/runner.py](hve/runner.py) `_has_supported_asdw_data_deploy_app_scope` により、APP-009 以外は **生成前に fail-closed で拒否** されるため誤動作は起きない。汎用化とは「SQL エンティティ・データベース・テーブル・期待件数の対応（`_ASDW_APP009_SQL_COVERAGE` / `_REQUIRED_ENTITIES`）を設計書から導出する」ことであり、Step 1.2 の verifier 契約テスト群が現行マッピングを逐語で固定しているため、対応アプリを増やす需要が生じた時点で独立 feature として実施する | 対応 APP を増やす需要が生じた時点で起票 |
| TBD-22 | `hve/artifact_validation.py`（11,365 行）の分割 → **実施しない（判断確定）**: 機能変更を伴わない大規模リファクタであり、`import` 経路の変更が [hve/runner.py](hve/runner.py) の定数 re-export（`_ASDW_AUDIT_MODE_*` / `_ASDW_DATA_DEPLOY_NETWORK_KEYS`）と契約テスト群に波及する一方、得られる価値は可読性のみ。行数肥大が実害（テスト実行時間・変更衝突）を生んでいる事実が観測されていないため、実害が観測された時点で再評価する | 実害が観測された時点で再評価 |
| TBD-23 | `_run_asdw_data_deploy_preflight_failure_gate` 等の到達不能コード削除 → **保持する（判断確定）**: Step 1.3 は HVE-native pipeline で実行されるため現状 SDK 経路は到達不能だが、経路自体は構造上復活し得る（routing 変更・新 Agent 追加）。削除すると復活時に preflight 失敗の検出が無言で失われるため、**多層防御として保持** する。同様の理由で post-main / final の producer contract gate、`_session_security_violation*` も保持する | 保持（削除しない） |
| TBD-24 | PR トレーサビリティブロックへの面横断影響フィールド（`Surface-Impact` / `Reuse-Check`）追加 → **初期スコープから除外（判断確定）**: FR-MAINT-04 は 8 キーを例示順で厳密に 1 組要求しており、キー追加は PR テンプレート・生成側・契約テストへ波及する破壊的変更となる。一方、面横断の重複検出自体は FR-MAINT-06 の決定論的検査で担保でき、自己申告フィールドは advisory に留まる。FR-MAINT-06 の運用後に、機械検査で捕捉できない重複が観測された時点で再評価する | FR-MAINT-06 の運用実績を確認した時点で再評価 |
| TBD-25 | `StepRunner._build_step_permission_handler` の未使用引数（`step_id` / `custom_agent`）の扱い → **現状維持（判断確定）**: 引数を使って拒否判定を入れる方向は [hve/tests/test_runner_deploy_gate_order.py](hve/tests/test_runner_deploy_gate_order.py) `test_data_deploy_agent_permission_and_mcp_dead_path_stay_removed` が機械的に禁止している（当該テストの根拠は「native pipeline は SDK import より前に return するため到達不能であり、復活は"到達しない安全境界"を増やすだけで実効性が無い」）。残る選択肢である引数削除は可読性のみの価値で、[hve/runner.py](hve/runner.py) の呼び出し 2 箇所・5 つのテストファイルの参照・`run_step` 内での呼び出し位置を検査する契約テストへ波及する。TBD-22 と同型の判断として現状を維持する。Step 種別で権限を変える具体的な要求が発生した時点で、規範要件の新設から再評価する | 権限分岐の具体要求が発生した時点で起票 |
| TBD-26 | ~~AAGD Step 6（検索経路の適正化実測）/ Step 7（Microsoft 365 / Teams 公開）の規範要件が本書に無い~~ → **解消（v2.45）**: 実装側は [hve/artifact_validation.py](hve/artifact_validation.py) の決定的検証、[hve/runner.py](hve/runner.py) の成果物ゲート、共有 Prompt の固定フォーマットで契約が確定していたため、その内容（ラベル 8 件・表の列構成・最小行数・判定語彙 4 値）を FR-WF-AAGD-08 / FR-WF-AAGD-09 として明文化した。新しい制約は追加していない | 完了（追加作業なし） |
| TBD-27 | ~~CLI 入口（[hve/__main__.py](hve/__main__.py)）と Orchestrator（[hve/orchestrator.py](hve/orchestrator.py)）に同名の既定値定数が 7 件重複している~~ → **解消（v2.46）**: `_ADI_DEFAULT_DEPTH` / `_ADI_DEFAULT_TARGET_SCOPE` / `_AKM_DEFAULT_SOURCES` / `_AKM_DEFAULT_TARGET_FILES` / `_ARD_DEFAULT_ANALYSIS_PURPOSE` / `_ARD_DEFAULT_SURVEY_PERIOD_YEARS` / `_ARD_DEFAULT_TARGET_REGION` の 7 件を [hve/workflow_registry.py](hve/workflow_registry.py) の公開定数へ集約し、両モジュールは alias import で参照する（FR-MAINT-07）。値が一致しているうちは通常のテストで検出できないため、再宣言そのものを禁じる契約テスト（[hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) `TestLaunchSurfacesShareParameterDefaults`）を追加した。flat import 時の `getattr` fallback は registry から値を引くため許容し、リテラルを直接束縛する代入だけを拒否する | 完了（追加作業なし） |
| TBD-28 | 工程ゲート（受付・要求確定・設計確認・実装/テスト・独立レビュー・PR 最終確認）の共通契約 → **PoC 結果を待つ（判断確定）**: 各ゲートの ID・入力成果物・判定項目・機械判定と人間判定の境界・停止理由・結果 schema を規範化する案。現行 §13.13 の `G-OUT` / `G-IN` / `G-LBL` / `G-CONS` / `G-DIFF` は「完了してよいか」を判定する完了ゲートであり、「次工程へ進んでよいか」を判定する工程ゲートとは役割が異なる。出典資料（実行計画）は当該ゲートを「品質Gate案。具体的な判定項目と自動化範囲は PoC で検証する」と明記しており、確定仕様ではない。未検証の仮説を恒久契約へ実装すると、判定項目が変わるたびに 3 実行面の契約とテストを作り直すことになる | 実案件 PoC で判定項目と自動化範囲が確定した時点で起票 |
| TBD-29 | 人間承認点の拡張（要求・受入条件 / テスト観点・期待結果 / 高リスク変更 / 最終 PR）と承認監査証跡 → **PoC 結果を待つ（判断確定）**: 現行 `FR-CLI-87` は Wave 境界の同期承認を CLI へ提供し、対象は `asdw-web` Step 1.3 の 1 件、記録は `approval:<wave_index>` に限る。承認主体・対象成果物の digest・理由・再承認条件を保持する schema は持たない。承認者名と自由記述の保存は `NFR-SEC-01` / `FR-RTO-04` が禁じており、監査証跡を足すには保存対象の再定義が要る。GUI からの承認は `FR-GUI-23` により標準入力が使えず、`FR-QA-03` の `qa_answer_mode="gui-file"` と同種の IPC 経路の新設が必要 | 承認点ごとの判定項目が PoC で確定し、保存してよい主体識別子の範囲が決まった時点で起票 |
| TBD-30 | 案件 PoC の開始条件を固定する Run Manifest → **PoC 結果を待つ（判断確定）**: 対象案件・Done 条件・変更範囲・自動判定手段・除外条件・起動方法・知識ソース・承認者・参照/変更/禁止範囲・比較基準を 1 run として固定する schema と開始前検証の案。現行は APP 要求文書・Workflow パラメータ・`sources` 指定・起動時 preflight が個別に存在するだけで、run 単位の凍結と digest は持たない。§3.9.1 の `PoC` は Repository Query 検索計測を指し、本項の案件 PoC とは別ドメインである | 実案件 PoC で固定すべき項目が確定した時点で起票 |
| TBD-31 | PoC KPI の共通イベント schema と比較レポート → **PoC 結果を待つ（判断確定）**: 人間介入時間・ゲート試行回数と理由・手戻り / 再実行 / 人手修正・品質指摘・セキュリティ検出と解消・追跡の完全性・比較基準との差分を観測する案。現行 `FR-RTO-01`〜`07` の `RuntimeMetrics` は token・AI Credit・コスト・Step 状態・tool / model 失敗数を保持しており、AI 実行量とコストは既に取得できる。不足するのは上記の人手・ゲート・品質・比較の各系列で、永続化 allowlist（`_METRIC_KEYS` / `_PERSISTABLE_KEYS`）の拡張を伴う。測定したい指標が確定する前に allowlist を広げると、`FR-RTO-04` の最小化方針と衝突する | 評価指標と比較基準が PoC で確定した時点で起票 |
| TBD-32 | 要求→判断→設計→コード→テスト→レビュー→PR の追跡グラフ → **PoC 結果を待つ（判断確定）**: 現行 `FR-APPREQ-04` の trace block は `APP-IDs` / `Requirement-IDs` / `Requirement-Documents` / `Unresolved-Blockers` の 4 キーを保持し、validator は構造・ID 実在・APP 整合だけを決定的に検証する。判断・設計・コード・テスト結果・レビュー指摘・解消・PR を結ぶノードとエッジ、成果物 digest は持たない。グラフ化には各成果物へ安定 ID を与える必要があり、Prompt・テンプレート・validator へ広く波及する | 追跡したい関係の粒度が PoC で確定した時点で起票 |
| TBD-33 | 全 run へ適用する共通セキュリティゲート → **PoC 結果を待つ（判断確定）**: 現行は `NFR-SEC-01`〜`03` が秘密情報の出力禁止・`docs-original/` 読み取り専用・`git add` の pathspec 除外を規定し、`FR-CLI-64` が Self-Improve の解決済み scope に対する秘密情報パターン検査を規定する。権限・依存脆弱性・禁止操作を含む合否 schema と PR 前 fail-closed ゲートは持たない。検査対象の範囲を決めずにゲートを足すと、既存 run が恒常的に停止する恐れがある | 検査項目と停止条件が PoC で確定した時点で起票 |
| TBD-34 | 案件 PDCA とプロセス PDCA の二重ループ → **PoC 結果を待つ（判断確定）**: PR 後に発見した事象の入力 schema、原因分類（要求 / 知識 / テスト / 実装 / ゲート / 工程引継ぎ）、案件修正とプロセス変更の別 ID、再現テスト先行、元ケース・同種ケースの回帰対象、改善効果の判定、標準化の承認を規定する案。現行 `FR-CLI-60`〜`65` の Self-Improve は scope 内の品質改善を反復する仕組みであり、案件修正と HVE 標準の変更を別々に管理・承認する契約ではない。分類体系を先に固定すると、実際の失敗事例と合わない分類が残る | 実案件 PoC で失敗事例の分類実績が得られた時点で起票 |
| TBD-35 | 実装前の受入条件・テスト baseline の独立確認と凍結 → **PoC 結果を待つ（判断確定）**: 生成アプリケーションの受入条件・期待結果・テスト集合を実装前に承認し、baseline の digest を固定して以後の変更を検出する案。現行は TDD RED / GREEN の Step 分離（`asdw-web` / `adfdv` / `aagd`）と TestCoding / Coding の Agent 分離で順序を担保するが、承認と凍結の工程は持たない。`FR-CLI-30` の Code Review Agent はフラグ指定時のみで全 run の必須ゲートではない。出典資料も「適用粒度は PoC で検証する」と明記している | 適用粒度と凍結対象が PoC で確定した時点で起票 |
| TBD-36 | Cloud Agent Orchestrator からの `--resume-run`（FR-CLI-86）利用不可 → **保留（設計判断が必要）**: `FR-STATE-04` の進捗ストア（`hve/.run-progress.jsonl`）は「run 終了後も残る利用者ローカル領域」であり、Issue / PR ベースで GitHub-hosted 環境上で実行される Cloud Agent Orchestrator には保存されない。`FR-CLI-86` の `--resume-run <run-id>` は `orchestrate` CLI サブコマンドの引数であり、`auto-*-reusable.yml` の Cloud 起動経路からは呼び出されない。したがって Cloud 実行が `FR-CLI-87` の既定挙動（非対話のため確認を出さず `blocked` で停止）や失敗で停止した後、進捗を引き継いで再開する手段が無く、利用者は当該 Sub-Issue を最初から再実行するしかない。対応するには Cloud run（Issue / PR 番号）とローカル `run_id` の対応付け、または Cloud 側専用の進捗永続化（GitHub Actions cache・Issue コメント等）の新設が必要であり、いずれも保存先・保持期間・認可範囲の新規設計を要するため、現時点では要件不備ではなく未設計の既知の制約として記録するに留める | Cloud 実行の再開需要と許容される保存先・保持期間が確定した時点で起票 |
| TBD-37 | ローカル GitHub API mutation の全画面横断直列化 → **保留（別 feature が必要）**: GitHub 公式は secondary rate limit 回避のため request の直列化と、大量の `POST` / `PATCH` / `PUT` / `DELETE` 間で最低 1 秒の待機を推奨する。現行は `add_labels` / Sub-Issue link / comment / Copilot assignment の一部が個別に 1 秒待機し、本改訂で Issue metadata 保存中と Pull Request review / merge 中の同一画面 mutation を相互排他にしたが、Issue panel・Pull Request panel・自動進捗 Post・Orchestrator を跨ぐ単一 queue / pacing は存在しない。個別 endpoint へ sleep を追加するだけでは同時開始を防げず、完了済みと誤認させるため行わない。対応には全 GitHub API consumer が共有する queue の所有者、read request を直列化する範囲、cancel / shutdown、rate-limit retry との待機統合を規範化する別 feature が必要 | 複数 GitHub mutation の並行実行が実測された時点、または全画面共通 request scheduler を設計するタスクで起票 |

---

## 13. ワークフロー別仕様（生成ファイル詳細）

本節は、各 Workflow の目的・Step DAG・生成ファイル（`output_paths` / `output_paths_template`）・必須入力（`required_input_paths`）をゲートとして緻密化する目的で定義する。[hve/workflow_registry.py](hve/workflow_registry.py) は実装状態の技術的な情報源として本節と整合させる。差分が生じた場合、ソース側を理由なく優先せず、規範要件への違反か規範要件の仕様変更かを判定し、後者なら要件を先に改訂してから両者を同期する。

### 13.0 共通約束

- **FR-WF-OUT-01**: 各 Step は `output_paths` で宣言した全ファイルを実行完了時点で存在させなければならない。`output_paths` は実行時に常に必要な成果物だけを宣言し、条件付き・任意の成果物を含めてはならない。1 件でも欠落した場合、当該 Step は `failed` とする（Self-Improve target scope 解決・Wave 入力チェックの前提）。本ゲートの適用範囲は CLI / GUI Orchestrator 配下モード（`OrchestratorContext` が注入された実行）に限る。単独実行モード（`ctx` 未注入）と fleet mode（`split_fork_enabled=true`）ではサブタスクが別スコープで成果物を生成するため、親 Step の完了条件として本ゲートを適用しない。欠落報告には欠落したパスのみを列挙し、存在する宣言パスを含めてはならない（[hve/runner.py](hve/runner.py) `_check_output_paths_gate`）。
- **FR-WF-OUT-02**: `output_paths_template` は fan-out 子ステップに対して、`{key}` および **fan-out parser 別の ID 別名プレースホルダ**（`app_catalog` / `dataflow_catalog` → `{appId}`、`screen_catalog` → `{screenId}`、`service_catalog` → `{serviceId}`、`agent_catalog` → `{agentId}`、`business_candidate` → `{businessId}`、`use_case_skeleton` → `{useCaseId}`）を fan-out キーで置換した実パスを生成する。別名の対応表は [hve/fanout_expander.py](hve/fanout_expander.py) `_KEY_ALIAS_PLACEHOLDERS_BY_PARSER` を単一情報源とし、「fan-out キーそのものを指す名前」以外を登録してはならない（`{screenNameSlug}` 等の catalog parser から復元できない属性を置換してはならない）。確定ファイルパスへ解決できないエントリの扱いは FR-WF-OUT-06 に従う。fan-out キーが空集合の場合、当該 Step はスキップではなく `failed`（fan-out 失敗）とする。
- **FR-WF-OUT-03**: `required_input_paths` に列挙された全ファイルが存在しない場合の挙動は `HVE_REQUIRE_INPUT_ARTIFACTS` に従う（`true`: 中断 / 既定 `false`: 警告継続、§3.3 FR-DAG-06）。
- **FR-WF-OUT-04**: 表中「生成ファイル」列の `{key}` は fan-out キーを表す。Container Step（`is_container=true`）は生成ファイルを持たず、Sub-Issue 束ね用途に限定する。
- **FR-WF-OUT-05**: [hve/workflow_registry.py](hve/workflow_registry.py) の StepDef 宣言（`output_paths` + `output_paths_template` / `required_input_paths`）と `.github/io-contracts/<Agent>--<workflow>--<stepId>.yaml` の宣言は一致しなければならない。同一 Step でも閾値等の実行時条件により生成有無そのものが分岐する条件付き成果物（FR-WF-DM-01 の sidecar 等）は、非 fan-out Step の `output_paths_template` と io-contract の双方へ同じパスを宣言し、io-contract 側では `required: false` としなければならない。既存成果物を更新し得る当該条件付き成果物は `mode: upsert` とし、`mode: create` で再実行を阻害してはならない。入力ごとに出力パスだけが動的に変わる成果物（ADOC の `{relative-path}` 等）は本追加規定の対象外とし、既存の `required` / `mode` 契約を変更しない。`.github/scripts/validate-io-contract.py`（引数なし）の registry mismatch を 0 件に保ち、[.github/workflows/validate-io-contract.yml](.github/workflows/validate-io-contract.yml) は当該チェックを hard fail として実行する。registry mismatch は `.github/io-contract-exceptions.yaml` では抑止できない（`check_registry_mismatch()` は例外ファイルを参照しない）ため、解消は StepDef 側または io-contract 側の修正で行うこと。
- **FR-WF-OUT-06**: `output_paths_template` の各エントリのうち、次のいずれかに該当するものは **確定ファイルパスへ解決できない**ものとして fan-out 子の `output_paths` に載せてはならない（FR-WF-OUT-01 のゲートを誤 fail させないための fail-closed 規則、[hve/fanout_expander.py](hve/fanout_expander.py) `_resolve_output_path_template`）。載せない場合も、`output_paths_template` の宣言自体は io-contract との契約整合（FR-WF-OUT-05）のために保持する。
  1. キー別名プレースホルダを 1 つも含まない（全 fan-out 子で同一パスになり per-key 成果物ではない）
  2. 置換後もプレースホルダ（`{...}` / `<...>`）が残る
  3. glob（`*` / `?`）を含む
  4. ディレクトリ参照（末尾 `/`）
  5. 同一 `output_paths_template` 内で宣言されたディレクトリ成果物の配下にある（配下のファイル構成は Agent の裁量であり、個別ファイル単位でゲートすると同一成果物でも構成差で誤 fail する）
- **FR-WF-OUT-07**: fan-out 対象でない StepDef の `output_paths_template` は展開されないため、`_check_output_paths_gate` および `collect_workflow_output_paths` の対象にならない。動的パス（`docs-generated/files/{relative-path}.md` 等）や条件付き生成物を io-contract と整合させるための**契約宣言専用の宣言面**として用いてよい。この面に宣言した条件付き成果物は実行時 G-OUT と Self-Improve target scope の対象外であり、生成条件・親成果物からの参照・非生成時の stale cleanup は個別の成果物契約と専用テストで担保する。実行時ゲートの対象としたい確定成果物は `output_paths` に宣言すること。
- **FR-WF-OUT-08**: 名称スラッグ（`{screenNameSlug}` / `{serviceNameSlug}` / `{jobNameSlug}`）は **日本語カタログ名の英訳** であり（`docs/catalog/service-catalog.md` の `SVC-01 | 会員・同意管理サービス` に対し実在ファイルは `docs/services/SVC-01-member-consent-service-description.md`）、訳語は Agent が生成するため [hve/catalog_parsers.py](hve/catalog_parsers.py) を拡張しても決定的には復元できない。したがって名称スラッグを `_KEY_ALIAS_PLACEHOLDERS_BY_PARSER` へ登録してはならず、これを含むエントリは FR-WF-OUT-06 規則 2 により恒久的に drop される。
- **FR-WF-OUT-09**: FR-WF-OUT-06 の結果、fan-out する Step の `output_paths_template` が**どの fan-out キーでも 1 件も解決されない**場合、当該 Step の実行時ゲート（FR-WF-OUT-01）は無言で空になる。この状態は誤 fail を起こさない代わりに検証の消失を招くため、対象 Step を明示 allowlist として固定し、allowlist 外の Step がゲート空になった場合は CI で検出しなければならない（[hve/tests/test_output_paths_template_resolvability.py](hve/tests/test_output_paths_template_resolvability.py) `_EMPTY_GATE_ALLOWLIST`）。allowlist の各項目には空になる理由を記載すること。FR-WF-OUT-10 の prefix ゲートで検証を回復した Step は allowlist から除くこと。
- **FR-WF-OUT-10**: FR-WF-OUT-06 で drop されたエントリのうち、**fan-out キーを実際に含む**ものは、キー出現位置の直後までを接頭辞とする **prefix 存在ゲート**へ降格して検証を回復する（[hve/fanout_expander.py](hve/fanout_expander.py) `resolve_output_path_prefix_gates`、[hve/runner.py](hve/runner.py) `_check_output_paths_gate`）。
  - 判定は「接頭辞に前方一致するファイルまたはディレクトリが 1 件以上存在するか」であり、`output_paths` の内容は変更しない（他の消費者への影響を持たない）。
  - **根拠**: 名称スラッグは FR-WF-OUT-08 のとおり決定的に復元できないうえ、単一 run（`ed3931b8`）の生成物が `docs/services/` だけで `{serviceId}-{serviceNameSlug}-description.md` / `{serviceId}-description.md` / `{serviceId}.md` の 3 形式に分岐しており、完全パス一致でも glob 一致でも誤 fail する。一方で全生成物が **ID 接頭辞で始まる**点は一貫しているため、接頭辞一致だけが誤 fail なしに「当該キーの成果物が存在するか」を検証できる。
  - キー別名を 1 つも含まないエントリ（全 fan-out 子で同一の固定パス）と、キーがそもそも代入されないエントリ（ADFDV の `{jobId}` 等、FR-WF-ADFDV-01）は prefix 化の対象外とし、FR-WF-OUT-09 の allowlist に残す。
  - ID 体系は `SVC-NN` / `APP-NNN-SNNN` / `DNN` のように桁数固定であり、接頭辞が別キーの成果物へ誤って一致しないこと。
- **FR-WF-OUT-11**: `.github/io-contracts/*.yaml` の `inputs[]` のうち `kind: static` であり、かつ変数記法（`{...}` / `<...>`）・glob（`*` / `?`）・ディレクトリ参照（末尾 `/`）のいずれも含まないパスは、リポジトリに実在しなければならない。[.github/scripts/validate-io-contract.py](.github/scripts/validate-io-contract.py)（引数なし）が本検査を行い、違反を integrity error として報告する。除外は [.github/io-contract-exceptions.yaml](.github/io-contract-exceptions.yaml) の `static_paths` に列挙されたパスだけとし、本検査専用の除外機構を新設してはならない（FR-MAINT-07）。FR-WF-OUT-05 の registry mismatch 検査は `required: true` かつ `kind: agent_artifact` の入力しか照合せず、`kind: static` の実在はどの検査も対象にしていなかった。その結果、実体と一致しない static 宣言が 8 件残存していた（`knowledge/D05` と `knowledge/D09` の区切り文字ゆれ 6 件、`knowledge/D15` のファイル名断片 1 件、未生成の生成対象ファイル 1 件）ことを根拠とする。

- **FR-WF-DM-01**: AAS Step 3.1 と ADA Step 4.1 が共有する `Arch-DataModeling` の主成果物は `docs/catalog/data-model.md` とし、分割の有無にかかわらず `output_paths` および io-contract で `required: true` のまま維持する。単一ファイル版が 50,000 文字を超える見込みの場合だけ、次の canonical sidecar 3 件を**全て**作成または更新し、親を索引/統合版として各 sidecar へのリンクと全体要約を保持する。親は分割時も固定見出し `1`〜`6` を維持し、見出し `3`〜`5` には主キー・主要制約・代表インデックス・整合性判断・主要イベント・図の要旨を含む統合ビューを残して、下流 Step が親単独で必要情報を取得できなければならない。sidecar は詳細を補足する任意成果物とし、下流の必須入力へ追加しない。各 sidecar は親への戻りリンクを持つこと。
  - `docs/catalog/data-model-service-stores.md` — Service Data Stores
  - `docs/catalog/data-model-consistency-events.md` — Consistency & Events
  - `docs/catalog/data-model-diagrams.md` — Diagrams
  canonical 3 件以外の章別・APP-ID別 Data Model sidecar を生成してはならない。registry では AAS / ADA の非 fan-out Step 4.1 の `output_paths_template` へ3件を宣言し、io-contract では各々を `required: false`, `mode: upsert` とする（FR-WF-OUT-05 / 07）。分割不要の再実行では、親から sidecar リンクを除去して固定章を親へ統合し、canonical sidecar 3 件の既存ファイルを削除して stale 成果物を残してはならない。分割条件・相互リンク・stale cleanup は共有 Prompt、AAS / ADA Body template、および専用契約テストで同一に保つ。

### 13.1 AAS — Architecture Design

- **目的**: ARD が確定したアプリ群と APP 別要求定義書から、アーキテクチャ推薦／ドメイン／サービス／データ／テスト戦略までの上流アーキテクチャ資産を生成する。AAD-WEB / ADFD / AAG の上流に位置する。
- **必須入力（ルート）**: `docs/catalog/app-catalog.md`、対象 APP 全件の `docs/architectural-requirements-app-NNN.md`
- **Step DAG と生成ファイル**:

| Step | タイトル | Custom Agent | 依存 | 生成ファイル |
|---|---|---|---|---|
| 1 | ソフトウェアアーキテクチャの推薦（APP 毎 fan-out） | Arch-ArchitectureCandidateAnalyzer | — | `docs/catalog/app-arch-catalog.md`（fan-out 結果統合） |
| 2.1 | ドメイン分析 | Arch-Microservice-DomainAnalytics | 1 | `docs/catalog/domain-analytics.md` |
| 2.2 | サービス一覧抽出 | Arch-Microservice-ServiceIdentify | 2.1 | `docs/catalog/service-catalog.md` |
| 3.1 | データモデル設計 | Arch-DataModeling | 2.2 | `docs/catalog/data-model.md`（常時必須）＋ FR-WF-DM-01 の条件付き sidecar 3件 |
| 3.2 | サンプルデータ生成 | Arch-DataModeling | 3.1 | `src/data/sample-data.json` |
| 4 | データカタログ作成 | Arch-DataCatalog | 3.1 | `docs/catalog/data-catalog.md` |
| 5 | サービスカタログ | Arch-Microservice-ServiceCatalog | 4 | `docs/catalog/service-catalog-matrix.md` |
| 6 | テスト戦略書 | Arch-TDD-TestStrategy | 5 | `docs/catalog/test-strategy.md` |
| 7 | ペルソナカタログ | Arch-PersonaCatalog | 6 | `docs/catalog/persona-catalog.md` |
| 8 | ペルソナ別共通画面カタログ | Arch-UI-PersonaScreenList | 7 | `docs/catalog/persona-screen-catalog.md` |

- **FR-WF-AAS-01**: AAS 末尾 2 Step の Step ID は成果物依存と同じ昇順に採番しなければならない。Step 7 を `Arch-PersonaCatalog`（`depends_on=["6"]`、`docs/catalog/persona-catalog.md` を生成）、Step 8 を `Arch-UI-PersonaScreenList`（`depends_on=["7"]`、`docs/catalog/persona-screen-catalog.md` を生成）とする。Step 8 は Step 7 の出力を `required_input_paths` に持つため、依存と逆順の採番（Step 8 → Step 7）へ戻してはならない。
  - 本契約は [hve/workflow_registry.py](hve/workflow_registry.py) を正本とし、[.github/scripts/bash/lib/workflow-registry.sh](.github/scripts/bash/lib/workflow-registry.sh)・[.github/scripts/powershell/lib/workflow-registry.ps1](.github/scripts/powershell/lib/workflow-registry.ps1)・[.github/workflows/auto-app-selection-reusable.yml](.github/workflows/auto-app-selection-reusable.yml)・[.github/ISSUE_TEMPLATE/app-architecture-design.yml](.github/ISSUE_TEMPLATE/app-architecture-design.yml)・`.github/prompts/`・`.github/prompts/steps/aas/`・`.github/io-contracts/` が同一の意味と順序を宣言すること。
  - Cloud のスキップ伝播は Step 7 のスキップが Step 8 を強制スキップする方向のみとする（逆方向は Step 8 の入力欠落を招くため禁止）。
  - Step ID は SDK セッション ID（`run_id × step_id`）の構成要素であり、同じ ID の意味が入れ替わる。透過的な旧 ID 変換は実装せず、再採番をまたぐ実行中 run は完了させるか、新しい run-id / Issue で再起動すること。

- **FR-WF-AAS-02**: AAS の旧 Step 1（`Arch-ApplicationAnalytics`）と `docs/catalog/app-catalog.md` の所有権は ARD Step 4.1 へ移管済みである。AAS Step 1（`Arch-ArchitectureCandidateAnalyzer`）は APP 単位に fan-out せず 1 Agent で全 APP 横断の `docs/catalog/app-arch-catalog.md` を生成する。`docs/catalog/app-catalog.md` と、カタログに列挙された全 APP の `docs/architectural-requirements-app-NNN.md` を必須入力とし、1 件でも欠落・構造不正・未解決 Blocker がある場合はデフォルト推薦へ降格せず対象 APP を fail-closed で停止する。既存の「入力ファイルなしなら Web/データフローをデフォルト推薦する」経路を残してはならない。

- **FR-WF-AAS-03**: AAS の Step ID は本節時点で、旧 Step "2"（`Arch-ArchitectureCandidateAnalyzer`、root）を新 Step "1" へ昇格させ、以降の全 Step ID を 1 つ繰り上げる例外的な再採番を実施した（旧 3.1→2.1 / 3.2→2.2 / 4.1→3.1 / 4.2→3.2 / 5→4 / 6→5 / 7→6 / 8→7 / 9→8）。旧 Step 1（`Arch-ApplicationAnalytics`）が ARD Step 4.1 へ移管された結果、AAS の Step ID が "2" から始まる歯抜け状態になっていたことの解消を目的とする一度限りの措置であり、以後の新規 Step 追加は既存 ID を維持したまま追加する原則（既存ステップの再採番禁止）に復帰する。本措置は FR-WF-AAS-01 の「末尾 2 Step の依存順採番」とは独立しており、影響は AAS 全体（`hve/workflow_registry.py` 正本、bash/PowerShell registry ミラー、Cloud workflow、Issue Form、Prompt、Template、I/O contract、`users-guide/`）に及ぶ。旧 ID を参照する run-id / Issue は、FR-WF-AAS-01 と同様に新しい run-id / Issue で再起動すること。

#### 13.1.1 ADA — Agent Data Architecture の Data Model共有契約

ADA は画面を持たないデータ中心の AI Agent 向けに AAS と並走し、Step 4.1 で同じ `Arch-DataModeling` と同じ主成果物 `docs/catalog/data-model.md` を使用する。ADA Step 4.1 の親成果物と条件付き sidecar 3件にも FR-WF-DM-01 を同一に適用し、AAS と異なるファイル名・分割閾値・cleanup規則を持ってはならない。

### 13.2 AAD-WEB — Web App Design

- **目的**: AAS 完了後、Web 系 APP に対し画面・サービス・テスト仕様（TDD RED 仕様書）を fan-out 生成し、横断整合性レビューで締める。
- **入力**: AAS 一式（`app-catalog` / `service-catalog` / `service-catalog-matrix` / `data-model` / `domain-analytics` / `test-strategy`）。
- **Step DAG と生成ファイル**:

| Step | タイトル | Custom Agent | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|---|
| 1 | 画面一覧と遷移図 | Arch-UI-List | — | `app_catalog` | `docs/catalog/screen-catalog-{key}.md` |
| 2.1 | 画面定義書 | Arch-UI-Detail | 1 | `screen_catalog` | `docs/screen/{screenId}-{screenNameSlug}-description.md` |
| 2.2 | マイクロサービス定義書 | Arch-Microservice-ServiceDetail | 1 | `service_catalog` | `docs/services/{serviceId}-{serviceNameSlug}-description.md` |
| 2.3 | サービス別 TDD テスト仕様書 | Arch-TDD-TestSpec | 2.2 | `service_catalog` | `docs/test-specs/{serviceId}-test-spec.md` |
| 2.4 | 画面別 TDD テスト仕様書 | Arch-TDD-TestSpec | 2.1 | `screen_catalog` | `docs/test-specs/{screenId}-test-spec.md` |
| 2.5 | 追加 Azure サービス選定 | Dev-Microservice-Azure-AddServiceDesign | 2.2 | — | `docs/azure/azure-services-additional.md` |
| 2.6 | Agentic Retrieval 機能要件詳細 | Arch-AgenticRetrieval-Detail | 2.2 | `service_catalog` | `docs/services/{serviceId}-agentic-retrieval-spec.md` |
| 3 | 画面 ↔ サービス整合性レビュー | QA-DocConsistency | 2.1, 2.2, 2.3, 2.4 | — | `docs/catalog/screen-service-consistency-report.md` |

> 注: 上記の Step ID・タイトル・依存・Fan-out・生成ファイルは `hve/workflow_registry.py` の StepDef を一次根拠とし、テンプレート（`.github/prompts/steps/aad-web/step-*.prompt.md` の「## 出力」）とも整合する。Step 1 / 2.1 / 2.2 / 2.3 / 2.4 / 2.6 は `output_paths_template`、Step 2.5 / 3 は `output_paths` へ登録済み（**TBD-11 解消**、§13.0 FR-WF-OUT-02 / 06）。Step 2.6 は `enable_agentic_retrieval` が `no` のとき `disabled_when_config` により実行対象から外れる。

### 13.3 ASDW-WEB — Web App Dev & Deploy

- **目的**: AAD-WEB を入力に、Azure データ層／コンピュート／追加サービス／UI を TDD（RED → GREEN）でデプロイし、WAF レビューまで完了させる。
- **Step DAG（コンテナ Step を除く）と生成物カテゴリ**:

| Step | タイトル | Fan-out | 生成カテゴリ |
|---|---|---|---|
| 1.1 | Azure データストア選定 | — | `docs/azure/azure-services-data.md` |
| 1.2 | データストア検証テスト生成（TDD RED） | — | `src/infra/azure/verify-data-resources.sh` |
| 1.3 | Azure データサービス Deploy（TDD GREEN） | — | `src/infra/azure/create-azure-data-resources-prep.sh`、`src/infra/azure/create-azure-data-resources.sh`、`src/data/azure/data-registration-script.sh`、`docs/azure/service-catalog.md` 更新 |
| 2.1 | 追加 Azure サービス選定 | — | `docs/azure/azure-services-additional.md` |
| 2.2 | 追加 Azure サービス Deploy | — | `src/infra/azure/create-azure-additional-resources-prep.sh`、`src/infra/azure/create-azure-additional-resources/create.sh` |
| 2.3 | 追加サービスのテストコード生成（TDD RED） | — | `src/test/integration/add-service/` |
| 2.4 | 追加サービスのテスト実施（TDD GREEN） | — | `src/test/integration/add-service/` |
| 2.5 | Agentic Retrieval Azure 実装設計 | `service_catalog` | `docs/azure/agentic-retrieval/{serviceId}-design.md` |
| 2.6 | Agentic Retrieval Deploy | — | `src/infra/azure/create-azure-agentic-retrieval/prep.sh`、`src/infra/azure/create-azure-agentic-retrieval/create.sh` |
| 3.1 | Azure コンピュート選定 | — | `docs/azure/azure-services-compute.md` |
| 3.2 | サービス テストコード生成（TDD RED） | `service_catalog` | `src/test/api/{serviceId}.Tests/` |
| 3.3 | サービスコード実装（TDD GREEN） | `service_catalog` | `src/api/{serviceId}-{serviceNameSlug}/` |
| 3.4 | Azure Compute Deploy | — | `src/infra/azure/create-azure-api-resources-prep.sh`、`src/infra/azure/create-azure-api-resources.sh`、`src/infra/azure/verify-azure-resources.sh`、`.github/workflows/*`（CI/CD）、`docs/catalog/service-catalog-matrix.md` 更新 |
| 3.5 | Deploy 後 再テスト | — | `src/test/post-deploy/` |
| 4.1 | UI テストコード生成（TDD RED） | `screen_catalog` | `src/test/ui/{screenId}/` |
| 4.2 | UI 実装（TDD GREEN） | `screen_catalog` | `src/app/` |
| 4.3 | Web アプリ Deploy（Azure SWA） | — | `src/infra/azure/create-azure-webui-resources.sh`、`src/app/staticwebapp.config.json`、`src/infra/azure/verify-webui-resources.sh`、`docs/catalog/service-catalog-matrix.md` 更新 |
| 4.4 | UI E2E テスト（Playwright） | — | `src/test/e2e/playwright/` |
| 5.1 | WAF アーキテクチャレビュー | — | `docs/azure/azure-architecture-review-report.md` |
| 5.2 | 整合性チェック | — | `docs/azure/dependency-review-report.md` |
| 5.3 | 要件適合実測 | — | `docs/azure/requirements-conformance-report.md`（§13.14 FR-WF-CONF-01） |

> 注: 上記の Step ID・タイトル・Fan-out・生成物は `hve/workflow_registry.py` の StepDef を一次根拠とし、テンプレート（`.github/prompts/steps/asdw-web/step-*.prompt.md` の「## 出力」）とも整合する。コンテナ Step `1` / `2` / `3` / `4` / `5` は §13.0 FR-WF-OUT-04 のとおり生成ファイルを持たない Sub-Issue 束ね用途のため本表から省く。ASDW-WEB の全非コンテナ Step は `hve/workflow_registry.py` へ登録済み（**TBD-12 解消**）。実行時ゲートの対象は `output_paths` のみで、ディレクトリ参照・glob・未解決スラッグを含む成果物は `output_paths_template` で契約宣言のみ行う（§13.0 FR-WF-OUT-06 / 07）。Step `2.5` / `2.6` は `enable_agentic_retrieval` が `no` のとき `disabled_when_config` により実行対象から外れる。

#### 13.3.1 Step 1.3（Azure データサービス Deploy）のパラメータ契約

- **FR-WF-ASDW-01**: Step 1.3 の `required_params` は次の 6 件とする。値は [hve/asdw_data_runtime_context.py](hve/asdw_data_runtime_context.py) `build_asdw_data_deploy_bootstrap_context` が Azure write 前に fail-closed 検証する。

| Workflow パラメータ | bootstrap キー | 既定値 | 既定値の根拠 |
|---|---|---|---|
| `resource_group` | `RESOURCE_GROUP` | なし（必須） | 環境固有。既存 Resource Group 名は推測できない |
| `data_location` | `LOCATION` | `japaneast` | [.github/skills/azure-skills/azure-region-policy/SKILL.md](.github/skills/azure-skills/azure-region-policy/SKILL.md) §1 標準リージョン優先順位の第 1 位 |
| `data_resource_suffix` | `RESOURCE_SUFFIX` | `app009` | Step 1.3 は APP-009 単一スコープ固定であり、既定値は APP-ID 定数から導出する（[hve/workflow_registry.py](hve/workflow_registry.py) `asdw_data_deploy_resource_suffix`） |
| `data_vnet_cidr` | `DATA_VNET_CIDR` | `10.40.0.0/16` | RFC 1918 私用アドレス。新規 VNet を作成するため既存環境と競合しない範囲を選択 |
| `data_private_endpoint_subnet_cidr` | `DATA_PRIVATE_ENDPOINT_SUBNET_CIDR` | `10.40.1.0/24` | 上記 VNet の部分集合かつ ACI サブネットと非重複 |
| `data_aci_subnet_cidr` | `DATA_ACI_SUBNET_CIDR` | `10.40.2.0/24` | 同上 |

> 注: 検証イメージ参照は利用者入力ではなく **HVE が導出する**。[hve/asdw_data_runtime_context.py](hve/asdw_data_runtime_context.py) `build_asdw_data_deploy_bootstrap_context` が `RESOURCE_GROUP` と `RESOURCE_SUFFIX` から `DATA_VERIFY_ACR_NAME` / `DATA_VERIFY_IMAGE_NAME` / `DATA_VERIFY_ACI_IMAGE` を決定論的に生成するため、`bootstrap_inputs` に当該キーを渡すと `undeclared` として拒否される。イメージ実体は同一 run 内の prep stage が作成し、[hve/asdw_data_script_generator.py](hve/asdw_data_script_generator.py) が `az acr create` / `az acr build` / `az role assignment create ... acrpull`（AcrPull ロール割当）を生成する。ビルド元 Dockerfile は [src/infra/azure/data-verify/Dockerfile](src/infra/azure/data-verify/Dockerfile)。したがって Workflow パラメータ `data_verify_aci_image`、CLI フラグ `--data-verify-aci-image`、GUI 入力欄はいずれも削除済みで、再導入してはならない。

- **FR-WF-ASDW-02**: 既定値を持たない必須パラメータは `resource_group` のみである。`resource_group` が未指定の場合、FR-DAG-08 の pre-flight が DAG 実行前に `blocked` を返す。Step 1.3 の実行時検証まで判定を遅らせてはならない。
  - したがって利用者へ入力を求めるのは `resource_group` だけとし、既定値を持つ 5 件（`data_location` / `data_resource_suffix` / `data_vnet_cidr` / `data_private_endpoint_subnet_cidr` / `data_aci_subnet_cidr`）に GUI 入力欄を設けてはならない（FR-GUI-02 / FR-GUI-06）。
  - 3 つの CIDR は `build_asdw_data_deploy_bootstrap_context` が「サブネットが VNet の内側にあること」「サブネット同士が重ならないこと」を fail-closed 検証する相互依存した組である。一部だけを利用者編集可能にすると、整合しない組合せを入力できてしまい Step 1.3 が実行時に停止する。
  - 既定値を持つ 5 件は `--data-location` などの CLI フラグ（[hve/__main__.py](hve/__main__.py)）で明示上書きできる。GUI 入力欄の廃止は非対話 CLI の上書き経路を閉じるものではない。

- **FR-WF-ASDW-03**: Azure リソース名・リソース ID・エンドポイントと検証イメージ参照は入力項目とせず、`RESOURCE_GROUP` / `RESOURCE_SUFFIX` / `SUBSCRIPTION_ID` から `build_asdw_data_deploy_bootstrap_context` が決定論的に導出する。`SUBSCRIPTION_ID` は `az account show` から取得し、Azure が採番する `DATA_DEPLOY_IDENTITY_CLIENT_ID` のみ prep 成功後に [hve/asdw_data_script_launcher.py](hve/asdw_data_script_launcher.py) が読み戻す。

#### 13.3.2 Step 4.3（Azure Static Web Apps Deploy）のrepository-managed Workflow契約

- **FR-WF-ASDW-04**: APP-009のrepository-managed SWA deploy Workflow [`.github/workflows/azure-static-web-apps-app009.yml`](.github/workflows/azure-static-web-apps-app009.yml) は `workflow_dispatch` だけで起動し、`resource_group`と`static_web_app_name`を既定値なしの必須文字列入力として受け取らなければならない。Workflow権限は`id-token: write`と`contents: read`だけとし、`environment: copilot`でOIDC認証した後、入力したexact targetを`az staticwebapp show`で確認してからdeployment tokenを動的取得し、値をmaskして`Azure/static-web-apps-deploy`へ渡す。`azure/login`と`Azure/static-web-apps-deploy`は公式repositoryのrelease tagが指す40桁commit SHAへ固定し、review可能なtag名を同じ行のコメントへ残す。hard-coded target、`push` / `pull_request` trigger、PR close job、`repo_token`、手動登録したdeployment token secretを追加してはならない。Step 4.3のPromptは同じ2入力を`gh workflow run`へ明示し、Workflowを生成・編集せずdefault branch上の既存Workflowを起動する。
- **FR-WF-ASDW-05**: APP-009のrollback drillを実行するrepository-managed Workflowを、実行対象scriptが存在しない状態で公開してはならない。現行repositoryには`.github/workflows/rollback-drill.yml`が参照する`src/infra/azure/rollback/run-rollback.sh`、`src/infra/azure/verify-webui-resources.sh`、`src/infra/azure/rollback/ui-staticwebapps-rollback.md`が存在しないため、当該Workflowと現役Workflow一覧からの参照を除去する。将来rollback drillを再導入する場合は、対象環境、実行script、検証script、復旧手順、Azure権限、production承認、受入テストを同一featureで先に定義し、本要件を改訂しなければならない。

### 13.4 ADFD — Dataflow Design

- **目的**: AAS 完了後、データフロー処理（旧称 Batch）のデータモデル・アプリ（ジョブ）カタログ・サービスカタログ・テスト戦略を確定し、ジョブ詳細仕様書・監視運用設計書・TDD テスト仕様書まで生成する。ADFDV（§13.5）の全 Step の上流に位置する。
- **必須入力（ルート）**: `docs/catalog/app-catalog.md`、`docs/catalog/data-model.md`
- **Step ID 体系**: Step 4 / 5 は旧 ABD 採番（データモデル 2 / ジョブ設計 3 / サービスカタログ 4 / テスト戦略 5）をそのまま引き継ぐ。旧 ABD の 2 / 3 は既存 Step 2（監視・運用設計書）/ 3（TDD テスト仕様書）と ID が衝突するため、データモデル / アプリカタログには「既存 Step ブロックの上流」を表す `0.1` / `0.2` を新規採番する。既存 Step 1 / 2 / 3 の ID・Custom Agent・生成ファイルは ADFDV および既存テストが依存するため不変とする。
- **Step DAG と生成ファイル**:

| Step | タイトル | Custom Agent | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|---|
| 0.1 | データフローデータモデル定義書 | Arch-Dataflow-DataModel | — | — | `docs/dataflow/dataflow-data-model.md` |
| 0.2 | データフローアプリカタログ | Arch-Dataflow-AppCatalog | 0.1 | — | `docs/dataflow/dataflow-app-catalog.md` |
| 4 | データフローサービスカタログ | Arch-Dataflow-ServiceCatalog | 0.2 | — | `docs/dataflow/dataflow-service-catalog.md` |
| 5 | データフローテスト戦略書 | Arch-Dataflow-TestStrategy | 4 | — | `docs/dataflow/dataflow-test-strategy.md` |
| 1 | ジョブ詳細仕様書 | Arch-Dataflow-AppSpec | 5 | `dataflow_catalog` | `docs/dataflow/apps/{key}-spec.md` |
| 2 | 監視・運用設計書 | Arch-Dataflow-MonitoringDesign | 5 | — | `docs/dataflow/dataflow-monitoring-design.md` |
| 3 | TDD テスト仕様書 | Arch-Dataflow-TDD-TestSpec | 1, 2 | `dataflow_catalog` | `docs/test-specs/{key}-test-spec.md` |

- **FR-WF-ADFD-01**: ADFD は ADFDV の各 Step が `required_input_paths` として要求する 4 ドキュメント（`docs/dataflow/dataflow-data-model.md` / `dataflow-app-catalog.md` / `dataflow-service-catalog.md` / `dataflow-test-strategy.md`）の producer を workflow 内に持たなければならない。producer 不在を `.github/io-contract-exceptions.yaml` の `external_paths` で迂回してはならない。
- **FR-WF-ADFD-02**: 上記 4 Step は既存 Step 1 / 2 / 3 の上流に配置し、DAG 根は `0.1` の単一ノードとする。既存 Step 1 / 2 / 3 の ID・Custom Agent・`output_paths` / `output_paths_template` は変更しない（ADFDV の fan-out キーとファイル名規約が依存するため）。
- **FR-WF-ADFD-03**: 4 Step の `output_paths` は確定ファイル名 1 件ずつを宣言し、DAG 根が成果物を寄与する状態を維持する。これにより Self-Improve の target scope は `SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS["adfd"]`（`docs/`）へフォールバックせず、具体パス直指定（`scope=""`）を維持する。
- **FR-WF-ADFD-04**: 消費側 Agent が文字列一致で検査する見出しは変更してはならない。`dataflow-app-catalog.md` は `## 1. ジョブ一覧表`、`dataflow-service-catalog.md` は `## 2. ジョブ → Azure サービスマッピング表` を含むこと（`.github/prompts/Dev-Dataflow-*.prompt.md` の依存確認テーブルの停止条件）。`dataflow-test-strategy.md` は「テストダブル戦略」節に Azurite / Testcontainers の利用有無を断定形で記載すること（`Dev-Dataflow-TestCoding` が参照）。

### 13.5 ADFDV — Dataflow Dev

> 旧称は **ABDV（Batch Dev）**。データフロー処理へのリネームに伴い workflow ID は `adfdv`、
> 生成先は `batch` から `dataflow` へ移行している。本節は
> [hve/workflow_registry.py](hve/workflow_registry.py) の実定義を正として記述する。

| Step | タイトル | Custom Agent | 依存 | Fan-out | 生成カテゴリ |
|---|---|---|---|---|---|
| 1.1 | データサービス選定 | Dev-Dataflow-DataServiceSelect | — | — | `src/infra/azure/dataflow/create-batch-resources.sh`、`src/infra/azure/dataflow/verify-batch-resources.sh` |
| 1.2 | Azure データリソース Deploy | Dev-Dataflow-DataDeploy | 1.1 | — | Azure データリソース実体（リポジトリ内成果物なし。FR-WF-OUT-05 の allowlist 唯一の残件） |
| 2.1 | TDD RED — テストコード作成 | Dev-Dataflow-TestCoding | 1.2 | `dataflow_catalog` | `src/test/dataflow/{jobId}-{jobNameSlug}.Tests/` |
| 2.2 | TDD GREEN — データフローアプリ本実装 | Dev-Dataflow-ServiceCoding | 2.1 | `dataflow_catalog` | `src/dataflow/{jobId}-{jobNameSlug}/` |
| 3 | Azure Functions/コンテナ Deploy | Dev-Dataflow-FunctionsDeploy | 2.2 | — | `.github/workflows/deploy-batch-functions.yml`、`src/infra/azure/dataflow/README.md` |
| 4.1 | WAF レビュー | QA-AzureArchitectureReview | 3 | — | `docs/azure/waf-review.md` |
| 4.2 | 整合性チェック | QA-AzureDependencyReview | 3 | — | `docs/azure/dependency-review.md` |
| 4.3 | 要件適合実測 | QA-RequirementsConformanceEval | 4.1, 4.2 | — | `docs/azure/dataflow-requirements-conformance-report.md` |

- **FR-WF-ADFDV-01**: Step 2.1 / 2.2 の fan-out parser は `dataflow_catalog` であり、上流の ADFD（§13.4）が生成する `docs/dataflow/dataflow-app-catalog.md` をキー元とする。
- **FR-WF-ADFDV-02**: `output_paths_template` の `{jobNameSlug}` は、[hve/catalog_parsers.py](hve/catalog_parsers.py) が ID のみを返すため現状解決できず、FR-WF-OUT-06 の fail-closed drop 規則により実行時ゲートから除外される。契約宣言としては保持する。
- **FR-WF-ADFDV-03**: データフロー実装の既定プログラミング言語は **Python**、テストフレームワークは **pytest** とする。選定理由は、実行基盤として Apache Spark / Microsoft Fabric / Databricks を選択できることである。分散処理が不要な規模では標準ライブラリ / pandas、必要な規模では PySpark を選択し、どちらを選んだかと根拠を README へ記録する。対象は `Dev-Dataflow-ServiceCoding` / `Dev-Dataflow-TestCoding` / `Dev-Dataflow-FunctionsDeploy` の各 Prompt と `.github/prompts/steps/adfdv/step-2.1.prompt.md` / `step-2.2.prompt.md`、および Cloud reusable workflow `auto-dataflow-dev-reusable.yml` の inline Issue body とし、.NET 固有の記述（`dotnet` / `xUnit` / `.csproj` / `C#` / `NuGet`）を残してはならない。

### 13.6 AAG — AI Agent Design

| Step | タイトル | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|
| 1 | AI Agent アプリケーション定義 | — | — | `docs/agent/agent-application-definition.md` |
| 2 | AI Agent 粒度設計 | 1 | `agent_catalog` | `docs/agent/agent-architecture.md`（および Agent 別補助ファイル） |
| 3 | AI Agent 詳細設計 | 2 | `agent_catalog` | `docs/agent/agent-detail-{key}.md`、`docs/ai-agent-catalog.md` |

#### 生成 AI Agent の Tool Search 方針（FR-WF-AAG）

本節は「生成する AI Agent が Microsoft Foundry Toolbox の tool search を使うか」を規定する。HVE 自身の SDK セッション設定（§3.5 FR-MODEL-04）とは別ドメインであり、互いの既定値・契約を混同してはならない。

- **FR-WF-AAG-01**: 生成 AI Agent の Tool Search 方針は `SDKConfig.enable_tool_search` の `auto` / `yes` / `no` の 3 値だけとする。第 4 の状態、追加の設定キー、Agent 側の自己判断による上書きを設けてはならない。方針値は CLI / GUI / Cloud のどの起動経路でも同一の 3 値として解決し、AAG Step 3 と AAGD Step 2.3 / 3 / 4 へ同じ値を渡さなければならない。未指定は `auto` とし、3 値以外は fail-closed で拒否する（既定値へ黙って丸めてはならない）。各値の意味は次のとおり固定する。
  - `auto`（既定）: 設計時の Tool 総数が閾値（[hve/artifact_validation.py](hve/artifact_validation.py) `_TOOLBOX_TOOL_COUNT_THRESHOLD`）を超える場合にだけ Toolbox / tool search を採用する。
  - `yes`: Tool 総数に関係なく Toolbox / tool search を採用する。
  - `no`: Tool 総数に関係なく Toolbox / tool search を採用しない。
- **FR-WF-AAG-02**: AAG Step 3 の `docs/agent/agent-detail-{key}.md` は方針に応じて次を満たさなければならず、[hve/artifact_validation.py](hve/artifact_validation.py) が決定的に検証する。
  - `auto` かつ閾値超、または `yes`: Skill `foundry-toolbox-contract` の TB-CAP-01〜05 を持ち、TB-CAP-02 の `Tool search` は `enabled`。
  - `auto` かつ閾値以下: TB-CAP を要求しない。
  - `no`: TB-CAP-01 / TB-CAP-02 を持ち `Tool search` は `disabled`。TB-CAP-03〜05 は理由・根拠・再判定条件付きの N/A とする。
  - 方針に関わらず、TB-CAP-04 の Tool 表は AG-CAP-03 / 04 / 05 から導出される Tool 集合を**過不足なく 1 行 1 件**で列挙し、`Pinned` 列は TB-CAP-03 の pin 一覧と一致しなければならない。欠落・余剰・重複は FAIL とする。

#### 生成 AI Agent の Agentic Retrieval 方針と検索契約（FR-WF-AAG）

本節は「生成する AI Agent が Foundry IQ / Azure AI Search Agentic Retrieval を採用するか」と、採用した場合の検索契約の下限を規定する。§3.9.1 の Repository Query 計測 PoC（HVE 自身の検索）とは別ドメインであり、互いの既定値・契約を混同してはならない。

- **FR-WF-AAG-03**: 生成 AI Agent の Agentic Retrieval 方針は `SDKConfig.enable_agentic_retrieval` の `auto` / `yes` / `no` の 3 値だけとする。方針値は AAG Step 3 と AAGD Step 2.3 / 3 の Prompt へ同一値で注入しなければならず、未指定は `auto`、3 値以外は fail-closed で拒否する（既定値へ黙って丸めてはならない）。各値の意味は次のとおり固定し、**成果物側の検証は FR-WF-AAG-04 が担う**。
  - `auto`（既定）: 経路選択を AG-CAP-03 の決定表（Skill `ai-agent-capability-contract` の `references/search-routing.md` §4）へ委ねる。
  - `yes`: `enterprise-unstructured` の Request class を持つ Agent は、Preferred route に Foundry IQ / Azure AI Search Agentic Retrieval を選ぶ。
  - `no`: Foundry IQ / Azure AI Search Agentic Retrieval を採用せず、AR-CAP-01〜05 を生成しない。
  - 本方針は Agentic Retrieval **Step の実行可否**を制御する既存の `disabled_when_config`（AAD-WEB Step 2.6 / ASDW-WEB Step 2.5・2.6 / AAR 全 Step）とは作用点が異なる。AAG / AAGD には Agentic Retrieval 専用 Step が存在せず、方針は Prompt 注入としてのみ作用する。AAGD Step 4 は tool search 専用の評価であるため注入対象に含めない。
- **FR-WF-AAG-04**: `docs/agent/agent-detail-{key}.md` は次を満たさなければならず、[hve/artifact_validation.py](hve/artifact_validation.py) が方針値を受け取って決定的に検証する。
  - 方針が `yes` かつ AG-CAP-03 に `enterprise-unstructured` の Request class 行がある場合、Preferred または Fallback に Foundry IQ / Azure AI Search Agentic Retrieval が選択され、AR-CAP-01〜05 が揃っていなければならない。
  - 方針が `no` の場合、AG-CAP-03 に Foundry IQ / Azure AI Search Agentic Retrieval の経路を選択してはならない。
  - Foundry IQ 経路を選んだ場合、AR-CAP-02 `Knowledge Source Matrix` の行数は **2 以上 10 以下**とする。1 行のみの Knowledge Base は、1 リクエストで複数 Knowledge Source を横断するという Agentic Retrieval の前提を満たさず、クラシックな単一クエリ検索と等価になるため FAIL とする。上限 10 は tier 依存のため実行時に再確認する。
  - Foundry IQ 経路を選んだ場合、AR-CAP-01 `Knowledge Base Contract` は `Index semantic configuration` を必須ラベルとして持つ。Agentic Retrieval の各サブクエリは semantic rerank を通るため、索引側の semantic configuration が検索品質の上限を決める。どの構成を用いるかを設計時に確定できない場合も、確認予定と確認手段を記載した有意な値を必須とし、空欄・単語だけの `TBD` を認めない。

### 13.7 AAGD — AI Agent Dev & Deploy

| Step | タイトル | 依存 | Fan-out | 生成カテゴリ |
|---|---|---|---|---|
| 1 | AI Agent 構成設計 | — | — | `docs/agent/agent-application-definition.md` |
| 2.1 | AI Agent テスト仕様書（TDD RED） | 1 | `agent_catalog` | `docs/test-specs/{key}-test-spec.md` |
| 2.2 | AI Agent テストコード生成（TDD RED） | 2.1 | `agent_catalog` | `src/test/agent/{key}.Tests/` |
| 2.3 | AI Agent 実装（TDD GREEN） | 2.2 | `agent_catalog` | `src/agent/{key}/`、`src/agent/{key}/plugin.json`（FR-WF-AAGD-06） |
| 3 | AI Agent Deploy | 2.3 | `agent_catalog` | `.github/workflows/deploy-agent-{key}.yml`、`src/infra/azure/create-azure-agent-resources.sh`、`src/infra/azure/verify-agent-resources.sh` |
| 4 | tool search 実測評価 | 3 | `agent_catalog` | `docs/agent/tool-search-eval/{key}-eval-report.md` |
| 5 | 要件適合実測 | 3 | — | `docs/agent/requirements-conformance-report.md` |
| 6 | 検索経路の適正化実測 | 3 | — | `docs/agent/route-rightsizing-report.md` |
| 7 | Microsoft 365 / Teams 公開 | 3 | — | `docs/agent/m365-publish-report.md` |

> 注: 上記の Step ID・タイトル・依存・Fan-out・生成物は `hve/workflow_registry.py` の StepDef を一次根拠とする。Step 4 は `enable_tool_search` が `no` のとき `disabled_when_config` により実行対象から外れる（FR-WF-AAGD-03）。Step 5 の要件は §13.14 FR-WF-CONF-01〜06、Step 6 は FR-WF-AAGD-08、Step 7 は FR-WF-AAGD-09 が規定する。

#### 生成 AI Agent の Tool Search 実装・デプロイ・評価ゲート（FR-WF-AAGD）

- **FR-WF-AAGD-01**: AAGD Step 2.3 の実装成果物は、設計（FR-WF-AAG-02）の TB-CAP と一致しなければならない。Agent 設定ファイル（`agent-config.json` または `appsettings.json`）が tool search の有効/無効・接続トポロジ・`limit`・pin 対象・検索専用語彙を保持し、System Prompt は「能力が存在しないと結論する前に tool search を呼ぶ」旨を含むこと。方針が `no`（または設計に TB-CAP が無い）場合、Toolbox 関連の設定・実装を生成してはならない。検証は Prompt の自己申告ではなく成果物の照合で行う。
- **FR-WF-AAGD-02**: AAGD Step 3 の Deploy 成果物は、Agent 登録より前に Toolbox version を作成し、`{"type": "toolbox_search"}`・pin・検索専用語彙・プレビューヘッダー・トークンスコープ・version 指定エンドポイントを扱わなければならない。検証スクリプトは `tools/list` の内容、pin 集合の一致、検索による発見と実行、`limit`、既定 version を fail-closed で検証すること。方針が `no` の場合は Toolbox の作成・検証を含めてはならない。設計値は Agent 設定を正本とし、スクリプトへ二重にハードコードしてはならない。
- **FR-WF-AAGD-03**: AAGD Step 4 は `docs/agent/tool-search-eval/{key}-eval-report.md` を必ず生成しなければならない。tool search を採用した Agent では、10 件以上の評価クエリ（うち 3 件以上は複数 Tool の組み合わせを要する）・期待 Tool 集合・on / off 両条件・指標一覧・TB-CAP-02 判定への結論を含めること。対象外の Agent では理由付きの N/A レポートを生成する。測定していない指標は「未測定」と理由を明記し、公開ベンチマークの値を自社の実測値として記載してはならない。方針が `no` の場合は本 Step を実行対象から外す。
- **FR-WF-AAGD-04**: Cloud（Issue Template + GitHub Actions）でも FR-WF-AAG-01 の 3 値を選択でき、Root Issue のメタデータと各 Step Issue 本文へ同一値を伝搬しなければならない。Post-DAG Self-Improve へ進む前の完了判定は、Issue のラベル状態だけでなく、checkout 済みブランチ上の設計・実装・Deploy・評価成果物を FR-WF-AAG-02 / FR-WF-AAGD-01〜03 と同じ検証で再確認し、不整合があれば fail-closed で停止しなければならない。

#### 生成 AI Agent の Agentic Retrieval 実装・デプロイゲート（FR-WF-AAGD）

- **FR-WF-AAGD-05**: AAGD Step 2.1 / 2.2 は Skill `agentic-retrieval-contract` を公開しなければならない。AG-CAP-03 で Foundry IQ 経路を選んだ Agent のテスト仕様・テストコードは、AR-CAP-03 の予算超過時の縮退と AR-CAP-04 の引用必須項目を検証対象に含める必要があり、当該 Skill が公開されていない Step では検証観点の正本へ到達できない。AAGD Step 3 の Deploy 成果物ゲート [hve/artifact_validation.py](hve/artifact_validation.py) `validate_ai_agent_deploy_artifacts` は、Toolbox の採否に関わらず、設計の AR-CAP-01 `Knowledge base name` と AR-CAP-02 の各 `KS name` が `src/infra/azure/` 配下のいずれかのファイルから追跡できることを静的に検証しなければならない。AR-CAP-05 の Tool allowlist は Step 2.3 の実装ゲートが既に設定とソースで検証しているため、Deploy ゲートで重複検証しない。Azure 実リソースへは接続せず、実リソースとの照合は Prompt 側の AC 検証の責務とする。

#### 生成 AI Agent の Agent Plugin パッケージング（FR-WF-AAGD）

本節は、生成した AI Agent の拡張点（Agent Skill）を可搬なパッケージとして配布できる形に固定する。準拠先は Agent Plugins Specification 1.0.0（<https://github.com/agentplugins/agent-plugins-spec>、2026-08-16 確認）と、そこから参照される Agent Skills 仕様（<https://agentskills.io/specification>、同日確認）である。

- **FR-WF-AAGD-06**: AAGD Step 2.3 は `src/agent/{key}/plugin.json` を必ず生成しなければならない。`src/agent/{key}/` を Agent Plugins の plugin root とみなし、既存の `src/agent/{key}/skills/{skill-name}/` を仕様の固定位置 `skills/` として扱う。マニフェストは次を満たし、[hve/artifact_validation.py](hve/artifact_validation.py) が決定的に検証する。
  - `$schema` は `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json` に一致する。
  - `name` は `{key}` を小文字化した値とし、1〜64 文字・`a-z` `0-9` `-` `.` のみ・先頭末尾は英数・`--` と `..` を含まない。現行の fan-out キー（`AG-01` 等）は大文字を含み仕様の制約を満たさないため、小文字化を経由しない値を使ってはならない。
  - 生成時に書き込むフィールドは `$schema` / `name` / `description` / `version` の 4 つとする。`description` は複数プラグインを並べたときの識別に、`version` は client の更新判定とキャッシュ鮮度判定に使われるため、仕様上は optional だが生成対象に含める。`author` / `homepage` / `repository` / `license` / `keywords` は推測で埋めることになるため生成しない。
  - validator は、仕様 §5.2 が許容する 10 種（`$schema` / `name` / `version` / `description` / `author` / `homepage` / `repository` / `license` / `keywords` / `extensions`）以外の top-level フィールドが存在する場合を FAIL とする。HVE 固有のランタイム設定を top-level へ追加してはならず、従来どおり `agent-config.json` または `appsettings.json` に置いて二重管理を作らない。
  - `mcp.json` は生成しない。仕様の `mcp.json` はプラグインが接続する MCP server の設定であるのに対し、AG-CAP-05 は生成 Agent を MCP client と定め、Agent 自身の Remote MCP Server 化を既定で禁じている。加えて AG-CAP-05 の Tool allowlist・承認条件・timeout・retry・入力信頼性は仕様 1.0.0 に対応フィールドが無く、認証も同版に OAuth / 資格情報参照フィールドが定義されていない。
- **FR-WF-AAGD-07**: AG-CAP-06 が `required` のとき、`src/agent/{key}/skills/{skill-name}/SKILL.md` の frontmatter は Agent Skills 仕様の長さ制約を満たさなければならない。`name` は 1〜64 文字、`description` は 1〜1024 文字とする。既存の検証は `name` の kebab-case 形状と `description` の有意性のみを見ており、長さ超過を検出できない。

#### 生成 AI Agent の検索経路適正化と Microsoft 365 公開（FR-WF-AAGD）

- **FR-WF-AAGD-08**: AAGD Step 6 は `docs/agent/route-rightsizing-report.md` を必ず生成しなければならない。成果物は次のラベルと表を持ち、[hve/artifact_validation.py](hve/artifact_validation.py) が決定的に検証する。ラベル名・列名は機械検証の固定値であり変更してはならない。
  - 測定条件ラベル（各 1 行）: `Schema-Version` / `Workflow` / `Step` / `Agent` / `Measured-At` / `Dataset` / `Dataset-Size` / `Secret-Redaction`
  - 比較表: `| Rung | Route | Accuracy | Tokens | Latency | Judgement | Evidence |`（**2 行以上**）
  - 結論: `- Conclusion:` と `- Rationale:`、および推奨経路 `- Recommended-Route:`
  - `Judgement` の語彙は `KEEP` / `DOWNGRADE` / `INSUFFICIENT` / `NOT_MEASURED` の 4 値だけとし、他の値を許してはならない。実行できなかった段は `NOT_MEASURED` の行として比較表に残し、理由を `Evidence` へ記す。行を省いて 1 段だけの比較表としてはならない。安い経路で要件を満たせるかを比較しない限り、採用経路が過剰かどうかを判定できないためである。
  - 実測していない段の数値を記載してはならない。段ごとに異なる評価データセットを用いてはならない。測定のために Agent 実装・設定・デプロイ済みリソースを恒久的に変更してはならない。
- **FR-WF-AAGD-09**: AAGD Step 7 は `docs/agent/m365-publish-report.md` を必ず生成しなければならない。成果物は次のラベルと表を持ち、[hve/artifact_validation.py](hve/artifact_validation.py) が決定的に検証する。ラベル名・列名は機械検証の固定値であり変更してはならない。
  - 公開条件ラベル（各 1 行）: `Schema-Version` / `Workflow` / `Step` / `Agent` / `Published-At` / `Publish-Scope` / `Auth-Scheme` / `Secret-Redaction`
  - 公開表: `| Agent Key | Channel | Publish Scope | App Version | Judgement | Approval | Evidence |`（**1 行以上**）
  - 結論: `- Conclusion:` と `- Rationale:`、および利用者向け接続手順 `- Consumer-Setup:`
  - `Judgement` の語彙は `PUBLISHED` / `PENDING_APPROVAL` / `NOT_SELECTED` / `FAILED` の 4 値だけとし、他の値を許してはならない。公開が完了していない状態を `PUBLISHED` としてはならない。
  - 公開メタデータへ secret・API キー・接続文字列・内部 URL を含めてはならない（NFR-SEC-01）。利用者から参照できる面へ出るためである。既に公開した版と同じ版を再利用してはならず、更新時は版を上げる。既存の認可スキーム・プロトコル設定を削除・置換してはならない。

### 13.8 AKM — Knowledge Management

- **fan-out キー**: 固定 `D01`〜`D21`（21 並列）。`max_parallel=21`。
- **同時更新防止**: `concurrency: akm-knowledge-write-${{ github.repository }}`（§4.4 FR-CLOUD-21）。

| Step | タイトル | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|
| 1 | knowledge ドキュメント生成・管理 | — | 静的 `D01〜D21` | `knowledge/{Dxx}-*.md` および `knowledge/{Dxx}-*-ChangeLog.md`（各 Dxx ごと） |
| 2 | knowledge 横断整合性レビュー | 1 | — | `knowledge/business-requirement-document-status.md` 更新（および整合性レポート） |

> `knowledge/` 書き込みは「削除 → 新規作成」ルール（`.github/copilot-instructions.md` §0）に従い、本体ファイルへの LOCK 情報埋め込みは禁止。

- **FR-WF-AKM-01**: [`.github/scripts/validate-knowledge-files.py`](.github/scripts/validate-knowledge-files.py) は`knowledge/D??-*.md`を、要求定義書本文と`*-ChangeLog.md`の2 schemaへファイル名で分けて検証しなければならない。本文は`knowledge-management-guide.md`のmetadata 6項目と§1〜§8、および20,000文字上限を検証し、付録AやChangeLog専用metadataを要求してはならない。ChangeLogは冒頭の`sources` / `generated_at` / `generator`コメント、metadata 5項目、全体更新履歴、要求項目別ログ、付録Aを検証し、本文の§1〜§8や20,000文字上限を要求してはならない。本体と同名prefixのChangeLogは対で存在し、片方だけを成功としてはならない。検証は既存script内の2分岐に限定し、新しいschema frameworkや外部依存を追加してはならない。

### 13.9 原本質問票の ADI 統合

- **fan-out キー**: 固定 `D01`〜`D21`（21 並列）。`max_parallel=21`。
- **位置付け**: 旧独立の原本質問票処理は ADI Step 1.1 / 1.2 に統合し、`qa/{key}-original-docs-questionnaire.md` および `qa/original-docs-cross-questionnaire.md` は ADI の main 成果物として扱う。
- **入力**: ADI Step 1 が生成する `docs/original-design-doc-ingest/index.json` と正規化済み `content.md` 群、および D01〜D21 の分類基準。`docs-original/` は Step 1 の入力として読み取り専用とし、Step 1.1 / 1.2 は直接走査しない。

| Step | タイトル | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|
| 1.1 | 原本質問票生成 | 1 | 静的 `D01〜D21` | `qa/{key}-original-docs-questionnaire.md`（`{key}` は `D01`〜`D21`） |
| 1.2 | 原本質問票 join | 1.1 | — | `qa/original-docs-cross-questionnaire.md` |

### 13.10 ADI — Auto Design-doc Ingestion

- **入力**: `docs-original/`（読み取り専用・任意形式）。
- **生成ルートディレクトリ**: `docs/original-design-doc-ingest/` および `docs/catalog/`。Step 5.x は加えて `docs/dataflow/` へも追記する。
- **実行経路**: CLI / GUI のみ（Cloud dispatcher 未対応。`ard` と同じ扱い）。
- **固有パラメータ**: `purpose`、`target_scope`、`depth`、`focus_areas`。
- **並列上限**: `max_parallel=21`。

| Step | タイトル | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|
| 1 | 原本インベントリ | — | — | `docs/catalog/design-doc-inventory.md`、`docs/original-design-doc-ingest/index.json`、`docs/original-design-doc-ingest/*/content.md` |
| 1.1 | 原本質問票生成 | 1 | 静的 `D01〜D21` | `qa/{key}-original-docs-questionnaire.md` |
| 1.2 | 原本質問票 join | 1.1 | — | `qa/original-docs-cross-questionnaire.md` |
| 2 | Doc Card 生成 | 1.2 | `design_doc_inventory`（`DOC-NNNN`） | `docs/original-design-doc-ingest/*/card.md` |
| 3 | 関連性トリアージ・カタログ統合 | 2 | — | `docs/catalog/design-doc-catalog.md` |
| 4 | 下流ルーティング表 | 3 | — | `docs/catalog/design-doc-routing.md` |
| 5.1 | ARD 成果物への設計書由来候補の反映 | 4 | — | `docs/catalog/use-case-skeleton.md` |
| 5.2 | AAS 成果物への設計書由来候補の反映 | 4 | — | `docs/catalog/app-catalog.md`、`docs/catalog/domain-analytics.md`、`docs/catalog/data-model.md` |
| 5.3 | ADFD 成果物への設計書由来候補の反映 | 4 | — | `docs/dataflow/dataflow-app-catalog.md` |

**要件**

- **FR-WF-ADI-01**: ADI は `docs-original/` を再帰走査し、決定的な `docs/original-design-doc-ingest/index.json` を生成する。同一入力に対し `docs` / `excluded` は常に同一でなければならない（[hve/doc_ingest.py](hve/doc_ingest.py)）。
- **FR-WF-ADI-02**: ADI は `docs-original/` へ書き込みを行ってはならない。CI ジョブ `check-docs-original`（`.github/workflows/protect-readonly-paths.yml`）が強制する。
- **FR-WF-ADI-03**: ADI は `.md` 以外の形式（PDF / Office / HTML / CSV）を Markdown へ変換して `content.md` に格納する。変換不能な形式は `excluded` として理由付きで記録する。
- **FR-WF-ADI-04**: ADI は変換来歴（`source_path` / `sha256` / `converter`）を `provenance.json` に記録する。`converter` は実際の変換経路（`passthrough` / `stdlib` / `markitdown`）と一致させる。
- **FR-WF-ADI-05**: ADI は文書数が上限（`hve.doc_ingest.MAX_DOCS` = 200）を超える場合、fail-closed で停止し `index.json` を書かない。
- **FR-WF-ADI-06**: ADI は `sha256` が前回と一致する文書の派生ファイルを再書き込みしない。
- **FR-WF-ADI-07**: ADI は同一内容の文書を `duplicate_of` として検出する。
- **FR-WF-ADI-08**: Step 1 の出力 `docs/catalog/design-doc-inventory.md` は第 1 列を `doc_id` とする。`hve/catalog_parsers.py` の `parse_design_doc_inventory` が第 1 列から `DOC-NNNN` を抽出するため、列順を変更してはならない。
- **FR-WF-ADI-09**: Step 2 が生成する Doc Card は front matter に `doc_id` / `source_path` / `source_sha256` / `d_classes` / `confidence` を必須で含み、`confidence` は `high` / `medium` / `low` のいずれかとする（`hve/artifact_validation.py::validate_design_doc_card`）。
- **FR-WF-ADI-10**: Step 3 が生成するカタログは、`out` 判定の全行に除外理由を持たなければならない（`hve/artifact_validation.py::validate_design_doc_catalog`）。
- **FR-WF-ADI-11**: `purpose` が空の場合、Step 3 は `must` を付与してはならない（`should` / `may` / `out` の 3 値に限定する）。
- **FR-WF-ADI-12**: AKM は `docs/catalog/design-doc-routing.md` が存在する場合それを優先し、存在しない場合は従来どおり `docs-original/` を走査する（後方互換）。ADI Step 1.1 / 1.2 は同一 Workflow の後段である Step 4 の成果物を参照せず、Step 1 の正規化済み出力を入力とする。
- **FR-WF-ADI-13**: Step 5.1 / 5.2 / 5.3 は下流ワークフロー（ARD / AAS / ADFD）の最上流 Step の成果物に `## 設計書由来の候補（ADI）` セクションを追記する。対象ファイルが存在する場合は全文を読んだ上で、候補セクション以外の既存記述を変更してはならない。
- **FR-WF-ADI-14**: 候補行は出典 `doc_id`（`DOC-NNNN`）を必須で持つ（`hve/artifact_validation.py::validate_downstream_seed_section`）。候補 0 件の場合もセクションを省略せず `なし` と明記する。
- **FR-WF-ADI-15**: ADI は下流ワークフローが採番する識別子（`APP-` / `UC-` / `SVC-` / `SCR-` / `JOB-`）を候補列に含めてはならない。採番は下流の責務であり、ADI が先に振ると衝突する。
- **FR-WF-ADI-16**: ADI は下流ワークフローを自動起動しない。`FULL_PIPELINE` に `adi` を登録せず、依存先としても宣言しない。
- **FR-WF-ADI-17**: ADI Step 1.1 は `QA-DocConsistency` により D01〜D21 へ静的 fan-out し、Step 1 が生成した `docs/original-design-doc-ingest/index.json` と各文書の正規化済み `content.md` を入力とする。`target_scope` は `/` 区切りのリポジトリ相対パスへ正規化し、`docs-original/` 配下だけを許可したうえで、index の `source_path` に対する前方一致で対象文書を絞り込む。省略時は `docs-original/` 全体を対象とする。各 fan-out 子の main 成果物は `qa/{key}-original-docs-questionnaire.md` とし、質問が 0 件でも summary 件数を `0` とし、本文に明示的な「質問なし」を含めた有効な成果物として扱わなければならない。
- **FR-WF-ADI-18**: ADI Step 1.2 は D01〜D21 の 21 質問票を join して `qa/original-docs-cross-questionnaire.md` を生成し、Step 2 は Step 1.2 に `depends_on` しなければならない。Step 2 の単独実行は既存の `qa/original-docs-cross-questionnaire.md` が存在する場合に限り許可する。Step 1.2 も質問 0 件を有効入力として扱い、summary 件数 `0` と明示的な「質問なし」を保持したまま join を完了しなければならない。
- **NFR-SEC-ADI-01**: 変換処理は `convert_local()` 相当のローカル入力限定 API のみを使用する（`hve/gui/doc_convert.py`）。
- **NFR-SEC-ADI-02**: `docs-original/` 外を指すシンボリックリンクは走査対象から除外する。

### 13.11 ADOC — Source Code → Documentation

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

> 上記パスはテンプレート（`.github/prompts/steps/adoc/step-*.prompt.md` の「## 出力」）の実体に基づく。ADOC の全非コンテナ Step は `hve/workflow_registry.py` へ登録済み（**TBD-14 解消**）。Step 2.1〜2.5 / 3.1 の動的パスは `output_paths_template` による契約宣言専用であり、実行時のファイル存在ゲートは適用されない（§13.0 FR-WF-OUT-07）。

### 13.12 ARD — Auto Requirement Definition

- **目的**: 企業全体／対象事業の事業分析から KPI/OKR、ユースケース、アプリケーション一覧、APP 別要求定義書までを自動生成する Workflow。5 表示グループ / 10 実 Step で構成する。
- **Cloud Orchestrator 対応**: **対応**。CLI / GUI と同じ 5 グループ・10 Step 契約を使用する。
- **FR-WF-ARD-01**: ARD は CLI / GUI / Cloud Orchestrator の 3 面で利用できなければならない。Cloud は専用 Issue Form、`auto-requirement-definition-reusable.yml`、dispatcher の trigger / done / closed routing、`ard:initialized` / `ready` / `running` / `done` / `blocked` / `qa-ready` / `qa-drafting` を持つ。Cloud の未選択時は `ARD_DEFAULT_GROUP_IDS` と同じグループ `2`〜`5` を実行し、グループ `1` は明示 opt-in とする。Cloud reusable workflow の Step ID / Custom Agent / 依存は Python と Bash の registry に一致しなければならない（FR-CLOUD-06）。
- **FR-WF-ARD-02**: ARD がユーザー提供資料（`attached_docs` およびパス指定の `target_business`）を受け取る Step では、当該資料を **一次情報として最優先で参照する**ことを Prompt および Body テンプレートに明示しなければならない。根拠: ユーザー提供資料は ARD のどの Step の `required_input_paths` にも宣言されず、`{attached_docs}` / `{target_business}` のパラメータ注入だけが到達経路であるため、優先度の明示が無い Step では固定パスの既定入力に埋没する。対象は Step 1（[.github/prompts/Arch-ARD-BusinessAnalysis-Untargeted.prompt.md](.github/prompts/Arch-ARD-BusinessAnalysis-Untargeted.prompt.md) / [.github/prompts/steps/ard/step-1.prompt.md](.github/prompts/steps/ard/step-1.prompt.md)）と Step 2（[.github/prompts/Arch-ARD-BusinessAnalysis-Targeted.prompt.md](.github/prompts/Arch-ARD-BusinessAnalysis-Targeted.prompt.md) / [.github/prompts/steps/ard/step-2.prompt.md](.github/prompts/steps/ard/step-2.prompt.md)）とし、Step 2 は既に本規定を満たす。
  - **パス指定 `target_business` の展開結果（v2.57 / v2.62 改訂）**: [hve/ard_target_business_resolver.py](hve/ard_target_business_resolver.py) `to_context_text()` が Step 2 へ渡す文字列には、対象ファイルの **本文を埋め込んではならない**。渡してよいのは、匿名化済みの指定パス、読み取り可能なファイルのリポジトリ相対パス一覧、件数、合計バイト数、スキップ理由、および解決エラーの種別に限る。Agent は読み取り可能な相対パスを自らの読み取りツールで参照する。従来は最大 5 MiB のファイル本文をそのまま Prompt へ埋め込んでいたため、Step 2 の Phase 1 リクエストが FR-CLI-84 の予算を単独で超え得た。パスだけを渡してもファイル自体は失われないため、要求の欠落は生じない。
  - 既存の安全制約（`base_dir` 外へ解決されるシンボリックリンク・`..` の除外、バイナリ拡張子・拡張子 allowlist・`max_files` / `max_total_bytes` / `max_file_bytes` の各上限、例外を送出せず `skipped` / `errors` へ記録して継続すること）を緩めてはならない。`base_dir` 外のファイル・ディレクトリ・symlink は子孫を列挙する前に拒否し、絶対パス・外部 basename・例外本文を Prompt へ含めず固定の匿名化表現を用いる。symlink cycle による `Path.resolve()` の `RuntimeError` も外へ送出してはならない。
  - `skipped` / `errors` はそれぞれ最大 50 件と省略マーカー 1 件までとし、診断メタデータ自体によって Prompt を無制限に肥大化させてはならない。除外されたリポジトリ内パスは相対パスと理由を提示し、`base_dir` 外は匿名化済み識別子と理由だけを提示する。
  - パス指定でない直接テキストの `target_business` は、従来どおりそのまま渡す。本項は展開結果の形式だけを変更するものであり、`is_path_like()` の判定規則を変更しない。
  - Body テンプレート [.github/prompts/steps/ard/step-2.prompt.md](.github/prompts/steps/ard/step-2.prompt.md) は `{target_business}` を **1 箇所だけ** 展開しなければならない。同一の値を複数箇所へ展開すると、Prompt サイズが展開箇所数に比例して増える一方で、Agent へ与える情報は増えないためである。
- **FR-WF-ARD-03**: ARD の利用者向け選択単位は次表の 5 表示グループ、実行単位は同表から展開される 10 実 Step とする。グループ対応の単一情報源は [hve/workflow_registry.py](hve/workflow_registry.py) の `_WORKFLOW_GROUP_MAPS["ard"]`、既定選択の単一情報源は同ファイルの immutable tuple `ARD_DEFAULT_GROUP_IDS = ("2", "3", "4", "5")` とし、CLI 直接実行・CLI wizard・GUI・Cloud、およびこれらが値を与えない場合の Orchestrator 側の安全網である fallback は同じ tuple を参照しなければならない。グループ `3` は KPI/OKR 実行有無を表す唯一の wizard / GUI 選択状態とし、別の真偽入力で上書きしてはならない。ARD 固有の任意パラメータ `target_recommendation_id` は CLI / GUI / Cloud から実効パラメータまで欠落させず伝搬し、`target_business` が空でグループ `1` と `2` を同一 run で実行する bridge 経路の Strategic Recommendation 選択にだけ用いる。CLI wizard の custom-auto はこの条件を満たす場合だけ事前入力を許可し、quick-auto は事前入力を尋ねず先頭候補を採用し、manual は事前入力を尋ねず Step 1.2 完了後の既存選択メニューを維持する。明示 ID が候補に存在しない場合は警告して先頭候補へ縮退する。

| 表示グループ | 利用者向け名称 | 展開する実 Step |
|---|---|---|
| `1` | 企業の事業分析 | `1`, `1.1`, `1.2` |
| `2` | 要求定義書作成 | `2` |
| `3` | KPI/OKR 定義 | `2.1` |
| `4` | ユースケース作成 | `3.1`, `3.2`, `3.3` |
| `5` | アプリケーション要求定義 | `4.1`, `4.2` |

- **Step DAG と生成ファイル**:

| Step | タイトル | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|
| 1 | 事業分野候補列挙 | — | — | `docs/company-business-recommendation.md` |
| 1.1 | 事業分野別深掘り分析 | 1 | `business_candidate` | `docs/business/{key}-analysis.md` |
| 1.2 | 事業分析統合 | 1.1 | — | `docs/company-business-requirement.md` |
| 2 | 対象業務深掘り分析 | —（bridge 時は動的に 1.2） | — | `docs/business-requirement.md` |
| 2.1 | KPI/OKR 定義（任意） | 2（skip_fallback `1.2`） | — | `docs/recommended-kpi-okr.md` |
| 3.1 | ユースケース骨格抽出 | 2（skip_fallback `1.2`） | — | `docs/catalog/use-case-skeleton.md` |
| 3.2 | ユースケース詳細生成 | 3.1 | `use_case_skeleton` | `docs/usecase/{key}-detail.md` |
| 3.3 | ユースケースカタログ統合 | 3.2 | — | `docs/catalog/use-case-catalog.md` |
| 4.1 | アプリケーションリスト作成 | 3.3 | — | `docs/catalog/app-catalog.md` |
| 4.2 | APP 別要求定義書作成 | 4.1 | — | `docs/architectural-requirements-app-NNN.md`（APP 全件、単一 Agent が順次 upsert） |

- **FR-WF-ARD-04**: ARD Step 4.1 は従来 AAS Step 1 が所有した `Arch-ApplicationAnalytics` と `docs/catalog/app-catalog.md` を同じ Prompt 契約で引き継ぐ。Step 4.2 は `app-catalog.md` に列挙された APP を出現順に 1 Agent で処理し、各 APP の canonical path `docs/architectural-requirements-app-NNN.md` を upsert する。Step 4.2 は fan-out してはならず、APP 間で共有する既存ファイルへの並列書込みを発生させない。非 fan-out Step は fan-out キー別名を代入できないため、registry と io-contract の `output_paths_template` へは glob `docs/architectural-requirements-app-*.md` を宣言し、`{appId}` のような fan-out プレースホルダを宣言してはならない。専用の完了ゲートは `app-catalog.md` の APP-ID 集合に対応する canonical file が全件実在して FR-APPREQ-01 を満たすことを検証する。カタログに無い orphan 文書は削除せず、警告として列挙する。AAS / ADA の既存 Step ID は再採番せず、ADA Step 1（`Arch-ApplicationAnalytics` による `app-catalog.md` 生成）も AAS Step 1 と同じ理由で ARD Step 4.1 へ移管して廃止した。ADA は Step 2（ドメイン分析）から開始する 9 実 Step となり、ADA 単独での `app-catalog.md` 生成はサポートしない。

#### 13.12.1 生成アプリケーションの要求トレーサビリティ

- **FR-APPREQ-01**: APP 別要求定義書の canonical path は APP-ID `APP-NNN` に対して `docs/architectural-requirements-app-NNN.md` とする。各文書は `APP-ID` / `APP名` / `Schema-Version` / `Document-Status`、および固定列 `Requirement ID | Status | Requirement | Source | Acceptance Criteria | Blocker` の要求表を持つ。Requirement ID は `APP-NNN-FR-NNN` / `APP-NNN-NFR-NNN` / `APP-NNN-C-NNN` のいずれかで文書内一意とし、末尾番号は kind ごとに `001`〜`999` を使用する。次番号が `999` を超える場合は桁を暗黙拡張せず fail-closed とする。`Status` は `confirmed` / `source-backed` / `TBD`、`Blocker` は `yes` / `no` に限定する。
- **FR-APPREQ-02**: 再実行は upsert とし、既存 `confirmed` 行の ID と内容、既存 `source-backed` 行の ID、人手追記、およびカタログから削除された APP の文書を自動削除してはならない。新規 ID は同じ APP・kind 内の最大番号の次を割り当て、既存 ID を再番号付けしない。根拠の優先順位は既存 confirmed > 明示添付 / 回答済み QA > ARD 成果物 > staleness 合格済み knowledge > 推論 TBD とし、上位根拠と競合する場合は上書きせず Blocker として停止する。
- **FR-APPREQ-03**: AAS / ADA / AAD-WEB / ASDW-WEB / ADFD / ADFDV / AAG / AAGD / AAR は、対象 APP-ID を `app-scope-resolution` で確定し、対応する APP 別要求定義書だけを必須参照する。APP-ID fan-out 子は自身の fan-out key、画面・サービス・エンティティ等の fan-out 子は `app-catalog.md` の対応関係、非 fan-out Step は実効 `app_ids` を使用する。実効 `app_ids` が空の横断 Step だけは当該 Workflow の対象分類に含まれる全 APP を参照対象とする。全文を全 Step へ常時注入せず、canonical path と対象 ID をプロンプトへ注入し、詳細は `markdown-query` で選択取得する。対象文書の欠落、構造不正、対象 APP と異なる ID、または `TBD` かつ `Blocker=yes` が 1 件でもあれば、警告降格やデフォルト推薦を行わず対象 APP を fail-closed で停止する。
- **FR-APPREQ-04**: 対象 Workflow の Step 完了報告は、`<!-- app-requirements:start -->` / `<!-- app-requirements:end -->` 間に `APP-IDs` / `Requirement-IDs` / `Requirement-Documents` / `Unresolved-Blockers` の 4 キーを各 1 回だけ記録する。`Requirement-IDs` は対象文書に存在する `confirmed` / `source-backed` ID だけを引用し、`TBD` を実装根拠として引用してはならない。validator はファイル存在、ID 実在、APP-ID整合、ブロック形式だけを決定的に検証し、要求の意味的妥当性は既存の contents review または人間レビューへ委ねる。
- **FR-APPREQ-05**: `application-requirement-traceability` Skill は `app-scope-resolution` と `markdown-query` を再利用し、新規設定・新規外部依存・要求書全文の常時注入を追加してはならない。CLI / GUI は `hve/skill_manifest.json` の workflow default と Runner の単一 preflight / completion gateを、Cloud は全 Custom Agent が継承する `agent-common-preamble` の短いルーターと reusable workflow の前提成果物チェックを使用する。同じパス解決・ID検証を実行面ごとに再実装してはならない（FR-MAINT-07）。

- **必須入力**:
  - Step 1.1: `docs/company-business-recommendation.md`
  - Step 1.2: `docs/business/{key}-analysis.md`
  - Step 3.2: `docs/catalog/use-case-skeleton.md`
  - Step 3.3: `docs/usecase/{key}-detail.md`
- **旧後方互換（廃止）**: 旧 step_id（`1` / `2` / `3`）からの resume 互換は、Resume 機能全廃に伴い NFR-COMP-01 とともに廃止済み。

### 13.13 ゲート条件（受入基準）

各 Workflow の完了判定は、実行経路と Workflow に対して**適用可能なゲートだけ**を評価し、その全てを満たすこと。適用条件を満たさないゲートは `N/A` とし、未達または `NOT_RUN` として扱ってはならない。

1. **G-OUT**: HVE が実行時の存在ゲートへ解決した必須成果物が全て存在すること。対象は固定 `output_paths`、fan-out 子について確定パスへ解決された `output_paths_template`、および FR-WF-OUT-10 の prefix 存在ゲートとする。非 fan-out Step の `output_paths_template` は FR-WF-OUT-07 の契約宣言専用であり、任意出力を含めて本ゲートの対象外とする。
2. **G-IN**: 後続 Workflow が要求する `required_input_paths`（§13 表中の必須入力）が満たされている。
3. **G-LBL**: Cloud Agent Orchestrator の完了判定に限り、`{prefix}:done` ラベルが付与され、`{prefix}:running` / `{prefix}:blocked` が外れていること（§3.4 FR-STATE-01）。CLI `--create-issues` が完了済み Step Issue へ done ラベルを付与する既存挙動は補助的な状態通知であり、本ゲートではない。Cloud Agent Orchestrator 以外の実行では、Issue 作成の有無にかかわらず `N/A` とする。
4. **G-CONS**: AKM Workflow に限り、`knowledge/business-requirement-document-status.md` 上で全 21 ドキュメントのステータスが一貫していること。AKM 以外では `N/A` とする。
5. **G-DIFF**: 当該 run で PR が実際に作成された場合に限り、GitHub Pull Request Files API が返す base...head の全変更パスが当該 Workflow の生成パス契約に収まること（[.github/copilot-instructions.md](.github/copilot-instructions.md) §9「差分品質評価」）。適用可否は起動フラグ名ではなく PR 作成結果で判定し、CLI / GUI の `--create-pr`、`--create-issues` により PR 作成も有効になる経路、ASDW-WEB / ADFDV の `--enable-auto-merge` による PR 作成経路、および Cloud を含む。PR が作成されない local CLI / GUI 実行では `N/A` とする。HVE Workflow の識別根拠を一切持たない通常 PR も `N/A` とし、通常の保守 PR を本ゲートで拒否してはならない。
  - HVE 管理 PR の Workflow ID は、PR body の `<!-- hve-workflow-id: <id> -->`、closing / parent Issue の Workflow タイトルプレフィックスまたは状態ラベル、PR title の既知プレフィックスの順に解決する。marker の値が registry に存在しない場合、または複数の根拠が異なる Workflow を指す場合は `N/A` へ縮退せず `BLOCKED` とする。canonical title の `[AAD-WEB]` / `[ASDW-WEB]` に加え、`[AAD]` → `aad-web`、`[ASDW]` → `asdw-web` の後方互換を維持し、解決結果は常に registry の canonical Workflow ID とする。PR 本文の任意文字列から許可パスを追加してはならない。
  - 許可パスは [hve/workflow_registry.py](hve/workflow_registry.py) の全 Step 宣言と [hve/fanout_expander.py](hve/fanout_expander.py) の既存展開規則を単一の情報源として、固定ファイル、ディレクトリ、segment 境界を越えない glob、subject 側カタログで解決した fan-out 出力、FR-WF-OUT-10 の prefix、非 fan-out の条件付き concrete template、および既知 placeholder の閉じた matcher へ分類する。非 fan-out の条件付き concrete template は G-OUT の必須存在ゲートからは除外されるが、G-DIFF では正当な作成・更新・削除の全てを許可する。ディレクトリ宣言は当該ディレクトリ自身と任意の深さの配下を許可する。`{relative-path}` は `.` / `..` / 空 segment を含まない 1 つ以上の安全な相対 segment、`{module-name}` は `/` を含まない安全な単一 segment とする。fan-out key alias は `_KEY_ALIAS_PLACEHOLDERS_BY_PARSER` を再利用し、未知 placeholder は許可範囲を推測せず policy 解決失敗とする。共通補助出力として許可できるのは `qa/**/*.md` だけとし、任意の `qa/` ファイル、JSONL、`work/` 成果物を許可してはならない。さらに §3.7 の HVE 対象境界を所有する [.github/scripts/hve_scope.py](.github/scripts/hve_scope.py) を再利用し、同モジュールが HVE 対象と判定する path は Workflow の広い directory / glob 宣言に一致しても許可してはならない。同モジュールが対象外とする生成アプリ向け `deploy-*` / `azure-static-web-apps-*` / `app<数字>*` workflow は、Workflow policy にも一致する場合に限り許可する。
  - Git path は case-sensitive な POSIX `/` 区切りの repository-relative path とし、空、absolute、backslash、NUL、CR / LF、`.` / `..` segment を拒否する。duplicate は初出順で除去する。GitHub REST API が列挙する status `added` / `removed` / `modified` / `renamed` / `copied` / `changed` / `unchanged` だけを受理し、`removed` は削除前 path、`renamed` / `copied` は旧・新 path の双方を検査して、いずれか一方でも許可範囲外なら `BLOCKED` とする。これ以外の status、必須 filename の欠落、`renamed` / `copied` の旧 path 欠落、非 JSON、pagination 途中失敗は fail-closed とする。Pull Request Files API は 1 PR につき最大 3,000 files しか返さないため、PR metadata の `changed_files` と取得件数を照合し、3,000 件超または件数不一致を部分一覧のまま `PASS` にしてはならない（[GitHub REST API — List pull requests files](https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files)、2026-08-24 確認）。
  - 判定結果は `PASS` / `BLOCKED` / `N/A` の 3 値とする。管理 PR で 1 件でも宣言外 path がある場合、Workflow ID 解決に矛盾がある場合、GitHub API / pagination / JSON / catalog parser / policy 構築に失敗した場合は `BLOCKED` とする。`BLOCKED` は check failure として違反 path と安全な解決失敗理由だけを報告し、token、PR 本文全文、patch、catalog 本文を出力してはならない。
  - Cloud の authoritative check は `pull_request_target` で base SHA の validator を `trusted/` へ、PR head SHA をデータ専用の `subject/` へ別 checkout し、実行・import・source するコードを `trusted/` だけに固定する。subject 側の Python / shell / PowerShell を実行せず、subject を `PYTHONPATH` へ追加せず、PR body を shell の `run:` へ直接展開してはならない。`opened` / `synchronize` / `reopened` / `edited` / `ready_for_review` の各更新で再検証する。
  - G-DIFF が `PASS` になる前に `auto-approve-ready` を付与してはならず、`BLOCKED`、判定エラー、missing / pending check を Approve / merge / `{prefix}:done` へ進めてはならない。branch protection の required context と `auto-approve-and-merge.yml` 内の共有 validator の直接実行を併用し、remote branch protection の再適用前も fail-closed を維持する。利用者向けの無効化・override フラグを追加してはならない。

適用可能なゲートのいずれか 1 件でも未達のとき、Workflow は `done` ではなく `blocked` 扱いとし、Self-Improve または手動介入の対象とする。`N/A` のゲートだけを理由に `blocked` としてはならない。

### 13.14 CONF — 生成物の要件適合実測（ASDW-WEB / ADFDV / AAGD / AAR 共通）

本節は「生成・デプロイした成果物を実際に動かし、機能要件・非機能要件への適合を測定して報告する」Step を規定する。設計妥当性を文書照合で評価する既存のレビュー Step（`QA-AzureArchitectureReview` / `QA-AzureDependencyReview`）とは異なり、**実行して得た測定値**だけを判定根拠とする。

- **FR-WF-CONF-01**: 次の 4 Workflow へ要件適合実測 Step を 1 件ずつ追加し、いずれも単一の Custom Agent `QA-RequirementsConformanceEval` を共有する。Step ID・依存・成果物は下表で固定し、既存 Step の ID・依存・成果物を変更してはならない。

| Workflow | Step ID | 依存 | 成果物 |
|---|---|---|---|
| `asdw-web` | `5.3` | `5.1`, `5.2` | `docs/azure/requirements-conformance-report.md` |
| `adfdv` | `4.3` | `4.1`, `4.2` | `docs/dataflow/requirements-conformance-report.md` |
| `aagd` | `5` | `3` | `docs/agent/requirements-conformance-report.md` |
| `aar` | `7` | `6` | `docs/azure/agentic-retrieval/requirements-conformance-report.md` |

  - `aagd` の依存を `4` ではなく `3` とするのは、Step 4 が `enable_tool_search=no` のとき実行対象から外れるためである。Deploy 完了（Step 3）だけを前提にすることで、tool search 方針に依存せず実測 Step が到達可能になる。
  - `asdw-web` の `5.3` は既存のコンテナ Step `5`（レビュー）配下に置き、`5.1` / `5.2` と同じ階層とする。Cloud の Sub-Issue はコンテナ配下として生成する。他の 3 Workflow はコンテナ Step を持たないため階層を持たない。
  - `aar` の Step 7 にも他の AAR Step と同じ `disabled_when_config`（`enable_agentic_retrieval` が `no`）を適用する。AAR は Agentic Retrieval 専用 Workflow であり、方針が `no` のとき Workflow 全体が実行対象外となるため。
  - 本 Step は fan-out してはならない。非機能要件はアプリケーション単位で判定する対象であり、要素単位へ分割すると同一の負荷条件を要素数分だけ再測定することになり、測定コストが要件の粒度と一致しない。

- **FR-WF-CONF-02**: 成果物は次のラベルと表を持たなければならず、[hve/artifact_validation.py](hve/artifact_validation.py) が決定的に検証する。ラベル名・列名は機械検証の固定値であり変更してはならない。
  - 測定条件ラベル（各 1 行）: `Schema-Version` / `Workflow` / `Step` / `Agent` / `Measured-At` / `Target-Environment` / `Measurement-Tool` / `Secret-Redaction`
  - 測定表: `| Req ID | Kind | Target | Threshold | Measured | Judgement | Headroom | Evidence |`（`Kind` は `FR` または `NFR`）
  - 結論: `- Conclusion:` と `- Rationale:`
  - 簡素化候補: `- Simplification-Candidate:`（該当なしのときは `none`）
  - 測定表は 1 行以上を持たなければならない。空表を PASS としてはならない。

- **FR-WF-CONF-03**: `Judgement` 列の語彙は `PASS` / `FAIL` / `NOT_MEASURED` / `NO_TARGET` の 4 値だけとし、他の値を許してはならない。
  - `NO_TARGET` は、対象要件に数値目標（`Target` / `Threshold`）が設計成果物側に存在しない場合に用いる。このとき `Measured` は実測値で埋め、Step を失敗させてはならない。目標が無いことと測っていないことを同一視すると、次サイクルで目標を決める材料が失われるため、両者を別語彙で区別する。
  - `NOT_MEASURED` は測定を実行できなかった場合に用い、`Evidence` 列へ理由を記載しなければならない。空欄にしてはならない。
  - `Measured` 列を空にしたまま `PASS` としてはならない。測定していない値を根拠に合格判定を出してはならない。
  - 測定値から目標値を逆算して `Target` / `Threshold` を生成してはならない。現状の性能をそのまま目標にすると改善余地の判定基準を失うため（[Google SRE Book, Chapter 4: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/) の "Don't pick a target based on current performance"、2026-08-17 確認）。

- **FR-WF-CONF-04**: 測定は、当該 Workflow が既にデプロイした資産と既存のテスト資産を用いて実施する。本 Step のために Azure リソースを新規作成することを必須にしてはならない。Azure Load Testing 等のマネージド負荷試験サービスの利用は任意とし、利用した場合は `Measurement-Tool` へ記録する。
  - 根拠: [Azure Well-Architected Framework PE:06 Architecture strategies for performance testing](https://learn.microsoft.com/azure/well-architected/performance-efficiency/performance-test)（2026-08-17 確認）は、性能テストのための専用インフラと専門知識が運用コストを増やすことをトレードオフとして明記し、後から問題を発見するコストと比較して投資を判断するよう求めている。
  - 応答時間を集約する場合は平均ではなくパーセンタイル（p50 / p95 等）を用い、どのパーセンタイルかを `Req ID` または `Target` 列で明示する。平均はロングテールを隠すため（同 SRE Book Chapter 4）。

- **FR-WF-CONF-05**: `Headroom` 列には目標値に対する余裕度を記録する。余裕が過大で構成を簡素化できる可能性がある項目は `- Simplification-Candidate:` へ列挙する。本 Step は測定と報告までを責務とし、簡素化の実施・構成変更・再デプロイを行ってはならない。
  - 根拠: 実運用 FaaS ワークロードの呼び出し頻度は 8 桁のレンジに広がり、大半の関数はごく低頻度でしか呼ばれない（Shahrad ほか, "Serverless in the Wild: Characterizing and Optimizing the Serverless Workload at a Large Cloud Provider", USENIX ATC 2020, <https://www.usenix.org/conference/atc20/presentation/shahrad>、2026-08-17 確認）。したがって選択した実行基盤が過剰かどうかは設計文書からは判定できず、実測値と目標値の差でしか評価できない。

- **FR-WF-CONF-06**: 本 Step は CLI / GUI / Cloud の 3 経路すべてから実行できなければならない。CLI / GUI は [hve/workflow_registry.py](hve/workflow_registry.py) への登録により反映される。Cloud は FR-CLOUD-06 の同期要件に従い、4 Workflow の reusable workflow と [.github/scripts/bash/lib/workflow-registry.sh](.github/scripts/bash/lib/workflow-registry.sh) の双方へ本 Step を登録しなければならない。

---

## 14. §13 関連 TBD 追補

| TBD No. | 内容 | 確認方法 |
|---|---|---|
| TBD-11 | ~~AAD-WEB Step 1 / 2.1 / 2.2 / 2.3 の `output_paths` / `output_paths_template` を `hve/workflow_registry.py` に正式登録~~ → **解消（E-09）**: FR-WF-OUT-02 / 06 により `output_paths_template` が多重プレースホルダを受け入れ、確定ファイルパスへ解決できないエントリを fail-closed で落とすようになった。Step 2.1 = `docs/screen/{screenId}-{screenNameSlug}-description.md`、Step 2.2 = `docs/services/{serviceId}-{serviceNameSlug}-description.md`、Step 2.3 = `docs/test-specs/{serviceId}-test-spec.md`、Step 2.4 = `docs/test-specs/{screenId}-test-spec.md` を登録済み。`{screenNameSlug}` / `{serviceNameSlug}` は catalog parser から復元できないため展開時に落ちる（契約宣言としては保持） | `.github/scripts/validate-io-contract.py` の registry mismatch 0 件 |
| TBD-12 | ~~ASDW-WEB 全 Step の `output_paths` / `output_paths_template` を `hve/workflow_registry.py` に正式登録~~ → **解消（E-09）**: Phase 3 E-01 で未登録だった 2.3 / 2.4 / 3.2 / 3.3 / 3.5 / 4.1 / 4.2 / 4.4 を含め、ASDW-WEB の全非コンテナ Step が `output_paths` または `output_paths_template` を宣言する。`hve/tests/test_workflow_registry.py` の `ALLOWED_EMPTY_OUTPUT_PATHS_STEPS` から asdw-web エントリを全削除済み | 同上 |
| TBD-13 | ~~廃止した旧独立原本質問票処理 Step 1 / 2 の `output_paths` / `output_paths_template` を `hve/workflow_registry.py` に正式登録~~ → **解消（v1.0.4）**: Step 1 は `output_paths_template=["qa/{key}-original-docs-questionnaire.md"]`、Step 2 は `output_paths=["qa/original-docs-cross-questionnaire.md"]` を登録済み。現行要件では ADI Step 1.1 / 1.2 の main 成果物として扱う | 同上 |
| TBD-14 | ~~ADOC 全 Step の `output_paths` / `output_paths_template` を `hve/workflow_registry.py` に正式登録~~ → **解消（E-09）**: Step 2.1〜2.5 は `docs-generated/files/{relative-path}.md`、Step 3.1 は `docs-generated/components/{module-name}.md` を `output_paths_template` へ登録した。いずれも fan-out 非対象 Step のため FR-WF-OUT-07 のとおり契約宣言専用であり、`{relative-path}` / `{module-name}` の実行時解決は行わない（ファイル単位の存在ゲートは適用外） | 同上 |

---

以上。
