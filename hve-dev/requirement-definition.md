# 要求定義・機能要件書 — HVE Cloud Agent Orchestrator / HVE CLI Orchestrator

本書は、本 HVE 実装（Hypervelocity Engineering = HVE）における **HVE Cloud Agent Orchestrator** および **HVE CLI Orchestrator** のソースコード実装から逆抽出した、要求定義と機能要件をまとめたものである。

---

## 1. 文書の位置付け

### 1.1 背景

HVE は、要求整理〜実装までを Workflow / Custom Agent / DAG として運用するためのフレームワークである。Orchestrator は Workflow を起動・進行管理する中核機能であり、Cloud（GitHub Actions）と CLI（Python パッケージ）の 2 系統が並存する。両系統の機能仕様を 1 つの基準で扱うため、本書を要求定義書兼機能要件書として位置付ける。

### 1.2 目的

- 既存実装から逆抽出した機能要件を一元化する
- Cloud / CLI 間の機能差を明示し、二重実装リスクを可視化する
- 受入基準を伴う仕様として、テスト / レビュー時の根拠を提供する

#### 1.2.1 規範目標

- **FR-E2E-01**: **優先度 MUST。** HVE は、利用者の依頼 1 回（対象業務・前提・デプロイ先 `resource_group`・事前承認の範囲の宣言）を入力として、選択された Workflow を `get_meta_dependencies()`（FR-COMMON-01）が定める `full-pipeline` の順に最後まで実行できなければならない。実行中に利用者の判断を待って停止してよいのは、(1) 資格情報など利用者しか持たない情報が不足する場合と、(2) 宣言された範囲の外にある破壊的・不可逆・課金・外部公開の操作を行う場合だけとする。それ以外の不明点は安全な既定値を選び、理由と影響を成果物へ記録して続行する。選択されていない Workflow を暗黙に追加してはならない（FR-PROMPT-06 を維持する）。完了の判定は §13.0.1 AC-003 とする。出典: 利用者依頼（2026-09-30）で指定された `work/202609301045-DAGReviewPlan.md` N1-1 と、HVE Orchestrator review report §2.3。

### 1.3 対象範囲

- 対象: Cloud Agent Orchestrator dispatcher と CLI Orchestrator のオーケストレーション機能
- 対象: HVE アプリケーション自体の変更に対する、要求参照・テスト対応・PR トレーサビリティの保守プロセス
- 対象外: Custom Agent 個別のプロンプト仕様、Issue Template の UI 仕様、MCP Server 個別の挙動

本書は次の 3 層を含む。優先順位は 1 → 2 → 3 とする。

1. **規範要件**: `FR-*` / `NFR-*` / `G-*` の定義行のうち、索引で `active-or-described` とされたもの、および当該要件が明示的に参照する従属表・箇条書き・スキーマ。HVE アプリケーション変更時に満たす。新規 ID の bootstrap 中は、同一変更セット内でのみ要求定義書の新規定義行とその明示参照先を暫定的な規範として扱い、索引再生成と照合が完了するまで他の変更から利用してはならない。
2. **説明的基線**: 既存実装から逆抽出した表・構成・確認時点の記述。規範要件を上書きしない。
3. **履歴情報**: 改訂履歴、解消済み TBD、`deprecated-or-removed` の要件。互換性調査以外では現行要件として適用しない。改訂履歴は [hve-dev/requirement-definition-history.md](hve-dev/requirement-definition-history.md) に置く。

現行コードと規範要件が矛盾する場合、Coding Agent はコードを暗黙の正解として要件を上書きせず、バグ修正か仕様変更かを明示して解消する。仕様変更の場合は、実装前に規範要件を改訂する。

### 1.4 初期逆抽出ベースライン

- リポジトリ: 監査対象 repository
- ブランチ: `main`
- 確認日: 2026-05-12
- commit SHA: `48326f3ea5fa55b65c262a4eb6e0cccea261bd6f`
- 位置付け: 初期逆抽出ベースラインであり、現在のスナップショットを示すものではない。

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
- UC-03: 利用者が `python -m hve` を引数なしで実行すると GUI Orchestrator を既定として起動し、PySide6 が未導入の場合に限り CLI 対話 wizard へフォールバックする
- UC-04: 1 Workflow 完了時に、Cloud Orchestrator が次の推奨 Workflow を Issue コメントで提示する（state_transition）
- ~~UC-05: 利用者が CLI で `resume` サブコマンドにより中断セッションを再開する~~ → **廃止（v1.1）**: 旧 JSON `state.json` / `config_snapshot` による Session State Resume（SDK セッション復元）を廃止した。FR-STATE-04 / FR-STATE-05 および FR-CLI-90 の durable resume は本廃止の対象外とする。
  - **2026-07-27 再確認（履歴）**: ASDW-WEB の長時間ラン全損対策として旧 JSON Session State Resume の復活が検討されたが、本廃止決定を維持した。当時の代替として FR-DAG-08（実行開始時パラメータ pre-flight）により、長時間実行後に判明していた入力不備を起動直後に検出する方針とした。この記録は現行 durable resume を対象としない。
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
| `ard` | Auto Requirement Definition | ✓ | ✓ | `company_name`, `target_business`, `survey_base_date`, `survey_period_years`, `target_region`, `analysis_purpose`, `target_recommendation_id`, `attached_docs`, `include_kpi_okr` |
| `aas` | App Architecture Design | ✓ | ✓ | （なし） |
| `ada` | Agent Data Architecture | ✓ | ✓ | `app_ids`, `app_id` |
| `aad-web` | App Detail Design (Web) | ✓ | ✓ | `app_ids`, `app_id`, `create_remote_mcp_server` |
| `asdw-web` | App Dev (Web / Microservice on Azure) | ✓ | ✓ | `app_ids`, `app_id`, `resource_group`, `usecase_id`, `tdd_max_retries`, `create_remote_mcp_server` |
| `adfd` | Dataflow Design | ✓ | ✓ | `app_ids`, `app_id` |
| `adfdv` | Dataflow Dev | ✓ | ✓ | `app_ids`, `app_id`, `resource_group`, `tdd_max_retries` |
| `aag` | AI Agent Design | ✓ | ✓ | `app_ids`, `app_id`, `usecase_id` |
| `aagd` | AI Agent Dev & Deploy | ✓ | ✓ | `app_ids`, `app_id`, `resource_group`, `usecase_id`, `tdd_max_retries` |
| `aar` | Agentic Retrieval Add-on | ✓ | ✓ | `app_ids`, `app_id`, `resource_group`, `usecase_id` |
| `akm` | Knowledge Management | ✓ | ✓ | `sources`, `target_files`, `force_refresh`, `custom_source_dir`, `enable_auto_merge`, `enable_review`*¹ |
| `adi` | Auto Design-doc Ingestion | **✗（dispatcher 未対応）** | ✓ | `purpose`, `target_scope`, `depth`, `focus_areas` |
| `adoc` | Source Code → Documentation | ✓ | ✓ | `target_dirs`, `exclude_patterns`, `doc_purpose`, `max_file_lines` |

\*¹ `enable_review` は Issue Template 入力には存在するが、`WorkflowDef.params` 宣言ではなく内部処理で扱われる。
\*² （v3.38 削除）`workiq_akm_ingest_dxx` は FR-KD-10 で廃止した。

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
  - 宣言値は `akm` = 21、`adi` = 21、`ard` = 15、`asdw-web` = 1 とする。他の Workflow は宣言を持たない。 `asdw-web` の宣言 1 は、FR-IDL-02 の所有範囲が重ならない fan-out の子にだけ `ownership_parallel` まで緩める（v3.32）。
  - 解決は [hve/orchestrator.py](hve/orchestrator.py) の単一実装で行い（FR-MAINT-07）、解決根拠を `DAGPlan.max_parallel_source` へ `ard-serial` / `workflow` / `config` として保持しなければならない。`DAGExecutor` へ `dag_plan` を渡す経路では `DAGPlan.max_parallel` が semaphore を決めるため、実行段階で `WorkflowDef.max_parallel` を再解決してはならない。
  - 宣言を持つ Workflow に対して `SDKConfig.max_parallel` で宣言値を上書きしてはならない。`asdw-web` の宣言は同一 worktree での並列書込みを避ける安全制約であり、`akm` / `adi` の宣言は fan-out が設計上その並列度で動くことを表すため、いずれも利用者設定より優先する。従来 `run_workflow` は `SDKConfig.max_parallel` だけを計画へ渡しており、`dag_plan` を伴う経路では `WorkflowDef.max_parallel` が実行に一切反映されていなかった（実測: `asdw-web` は宣言 1 に対し 2 ステップの wave が 4 箇所とも並列実行され、`akm` / `adi` は宣言 21 に対し semaphore 15 で fan-out が分割されていた）。
- **FR-DAG-04**: Step に `fanout_static_keys` または `fanout_parser` が定義されている場合、子ステップへ動的展開する。展開後の `step_id` は `{base_id}/{key}` 形式。`fanout_parser` の取り得る値:
  - `app_catalog` / `screen_catalog` / `service_catalog` / `dataflow_catalog` / `agent_catalog`
  - `business_candidate`（ARD Step 1.1）
  - `use_case_skeleton`（ARD Step 3.2）
  - `design_doc_inventory`（ADI Step 2）
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
- **FR-DAG-10**: Step の起動可能判定（依存がすべて解決済みで、未完了かつ除外対象でない Step を起動候補にする規則。コンテナの扱いは HVE 固有の差として下記で扱う）は、[hve/dag_readiness.py](hve/dag_readiness.py) の `select_ready_ids` を単一の実装としなければならない。対象は計画段階の Wave 計算（FR-DAG-02）が使う `WorkflowDef.get_next_steps`、実行段階の `DAGExecutor._get_next_steps` と `DAGExecutor._get_next_steps_from_expanded` の 3 つとする。
  - HVE 固有の差（skipped の依存を解決済みとする、既知でない依存を解決済みとする、`block_unless`、failed / blocked と実行中の動的な子の除外、コンテナの除外、入力の順序）は `select_ready_ids` の引数で渡す。
  - 観測できる起動候補とその順序、blocked の理由、計画の Wave を変えてはならない。並列上限（FR-DAG-03）、書込み衝突、優先順位は本判定に使わない。循環のあるグラフでも例外を出さず、循環するノードを起動候補にしない。
  - 遅延 fan-out の展開判定（`DAGExecutor._try_dynamic_expand`）と Cloud の判定（`.github/scripts/bash/lib/workflow-registry.sh`）は本要件の対象外とする。
  - 契約テスト: [hve/tests/test_dag_readiness_parity.py](hve/tests/test_dag_readiness_parity.py)

### 3.4 状態ラベルとライフサイクル

- **FR-STATE-01**: 各 Workflow は `{prefix}:initialized` / `{prefix}:ready` / `{prefix}:running` / `{prefix}:done` / `{prefix}:blocked` の状態ラベルを保持する（`_make_state_labels`、[hve/workflow_registry.py](hve/workflow_registry.py)）。加えて Cloud Agent Orchestrator の HITL 経路（FR-CLOUD-41）が用いる `{prefix}:human-required` / `{prefix}:human-resolved` を保持する。HITL ラベルは `_make_state_labels` の生成対象ではなく、[.github/labels.json](.github/labels.json) の登録と Cloud の遷移 workflow が唯一の情報源である。
  - HITL ラベルの対象プレフィックス（[.github/labels.json](.github/labels.json) 登録分）: `aas` / `aad` / `aad-web` / `asdw` / `asdw-web` / `adfd` / `adfdv` / `aag` / `aagd` / `akm` / `adoc` の 11 件。`aad` / `asdw` は FR-COMMON-02 の後方互換エイリアスである。
  - `ard` / `aar` / `ada` / `adi` は HITL ラベルを持たない。全 Workflow への拡張は本要件の対象外とする。
  - 契約テスト [hve/tests/test_label_consistency_audit.py](hve/tests/test_label_consistency_audit.py) が本項の宣言と `.github/labels.json` の一致を機械検査する。
- **FR-STATE-02**: `qa-ready` ラベルは Copilot アサインを保留する状態として明示的にスキップされ、質問票作成を担当する Copilot がアサインされた場合は `qa-drafting`（回答下書き中）へ遷移する。`auto-issue-qa-ready-transition.yml` は回答受領後に `qa-ready` または `qa-drafting` から `ready` への遷移を担当する。
  - 対象セット: `ard:qa-ready` / `aas:qa-ready` / `aad:qa-ready` / `asdw:qa-ready` / `adfd:qa-ready` / `adfdv:qa-ready` / `aag:qa-ready` / `aagd:qa-ready` / `akm:qa-ready` / `adoc:qa-ready` / `aad-web:qa-ready` / `asdw-web:qa-ready`
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
  - StepResult `success` と GUI `done` は `succeeded` へ変換する。承認は `record_kind=approval`、`step_id=approval-<wave_index>` とし、approved を `succeeded`、declined を `failed` として保存する。承認者名・自由記述・prompt 本文を保存してはならない。
  - succeeded Step を skip する前に FR-WF-OUT-01 と同じ必須 output 存在判定を行う。output 不足なら当該 Step と DAG 上の transitive descendants を再実行候補にする。content hash は作成しない。
  - 本項が保存するのは HVE-owned control state だけである。未出力 model state、streaming delta、provider 内部状態、生成途中本文、外部副作用の exactly-once を保存・保証してはならない。
- **NFR-REL-03**: durable resume の 10 秒目標は HVE-owned control state に限定し、次の 2 条件を別々に満たさなければならない。
  - transition durability: store method が commit 成功を返した `state_version` は hard process kill 後も欠落 0 とする。
  - liveness freshness: owner 実行中かつ scheduler/storage が正常な受入環境では、kill 時点の `heartbeat_age` を 10 秒以下とする。heartbeat worker は event loop と独立した thread、thread 専用 connection、`time.monotonic()` による 5 秒間隔で動作し、同じ `state_version` の生存時刻だけを更新する。
  - heartbeat write failure または fencing conflict は main executor を停止させ、成功状態を推測してはならない。worker stop は bounded とし、GUI graceful stop の最初の 3 秒以内に final state commit と worker stop を完了できなければならない。
  - OS/VM power loss、network filesystem、model/output progress の 10 秒復元は初期受入範囲外とする。初期実測は Windows/NTFS の graceful/hard process kill と OS 非依存 unit test に限定する。
  - **v3.41 明確化（GUI graceful stop の受信側）**: Windows の graceful stop が送る `CTRL_BREAK_EVENT`（SIGBREAK）は、`orchestrate` が SIGINT（Ctrl+C）と同じ中断経路へ変換して受け取らなければならない。Python の既定では SIGBREAK は `finally` を実行せずプロセスを終了させ、durable state が `running`・lease が残ったままになるため（システムテスト N-03）。`orchestrate` は `KeyboardInterrupt` を捕捉して、状態を `suspended` へ遷移させた後に `中断されました。` を stderr へ 1 行出力し、traceback を出さず exit code 1 で終了する（N-06）。`resume` 親プロセスはこの変換の対象に含めない（child が自身の `suspended` 遷移を完了するまで、親が先に終了して child を kill してはならないため）。出典: `tests/system-test/20261001-2235-CLI-Prompt-interrupt-resume-subcommands-skill-e2e-result.md` N-03 / N-06（2026-10-02）。受入テスト: `hve/tests/test_systemtest_20261002_fixes.py::test_ctrl_break_runs_finally_blocks_and_exits_with_one`、`hve/tests/test_resume_cli.py::TestExecutionRegistration::test_keyboard_interrupt_in_orchestrate_exits_one_with_a_message`。
- **NFR-CONC-02**: 同一 `(execution_id, instance_id)` の resume は state version CAS と fenced lease で直列化しなければならない。
  - lease acquire/takeover は `BEGIN IMMEDIATE` 内で active lease が無いか期限切れであり、かつ `state_version=expected_state_version` の 1 row だけを更新する。lease TTL は 20 秒とする。
  - acquire/takeover ごとに `lease_generation` を単調増加させ、1 へ reset してはならない。transition と heartbeat は lease owner と generation の一致を条件とし、更新 row が 1 でなければ durable state error とする。
  - 未期限切れownerのheartbeat成功時は`lease_expires_at`を当該heartbeat時刻から20秒後へ更新し、正常実行が20秒を超えてもleaseを維持する。期限切れownerは更新できず、最後に成功したheartbeatから20秒後には明示takeoverが可能でなければならない。
  - workflow / Step transition、heartbeat、release は owner / generation に加えて `lease_expires_at` が現在時刻より後であることを条件とする。期限切れ owner は heartbeat で自身を復活させたり、transition を commit したり、lease 情報を release して明示 takeover 要求を迂回したりしてはならない。
  - heartbeat と release は取得時 token の `state_version` との等値を条件にしてはならない。同じ owner / generation の未期限切れ lease で自身の transition が `state_version` を進めた後も、取得時 token で heartbeat と release を継続できなければならない。transition 自体の state version CAS は維持する。
  - 期限切れ lease の takeover は利用者が recovery action を明示した後だけ許可する。Prompt/GUI の plan 提示後に state が変化した場合は stale として再提示し、自動再試行してはならない。
  - parent processがleaseを取得して別のHVE childを起動する場合、取得済みtokenの`lease_owner`と`lease_generation`をhelp非表示のinternal argsでchildへ渡し、childの全transition/heartbeatを同じfencing条件へ結び付ける。parentはchild終了後にleaseを解放する。tokenを渡さずparentだけがleaseを保持すること、またはchild起動前にleaseを解放して同じCASを再実行させることを禁止する。
  - **v3.41 明確化（resume 親の heartbeat）**: `hve resume` の親プロセスは、lease 取得後 child の終了まで、`HeartbeatWorker`（`HEARTBEAT_INTERVAL_SECONDS` 間隔）で取得済み token の lease を更新し続け、child 終了後（異常終了を含む）に heartbeat を停止してから lease を解放しなければならない。child の起動から最初の durable 遷移までが lease TTL（20 秒）を超えると、child の transition が `durable workflow transition was fenced` で失敗し、親の release も fenced になって stale lease が残るため（システムテスト N-01）。state store の path を持たない場合だけ heartbeat を省略してよい。出典: 同結果 N-01（2026-10-02）。受入テスト: `hve/tests/test_resume_cli.py::TestResumeIntegrityAndConcurrency` と同ファイルの `test_parent_lease_heartbeat_spans_the_child_run`。

### 3.5 モデルと SDK

- **FR-MODEL-01**: 既定モデルは `claude-opus-5.5`（2026-09-24 に SDK `list_models()` の実応答で実在を確認。改訂前は `claude-opus-4.7`）。
  - `MODEL_CHOICES` は 5 値: `claude-opus-5.5`、`claude-opus-4.7`、`claude-opus-4.6`、`gpt-5.5`、`gpt-5.4`
  - 別途 `MODEL_AUTO_VALUE='Auto'` が許容される（[hve/config.py](hve/config.py)）
  - Issue Template の `model` / `review_model` / `qa_model` / `akm_model` の選択肢、`.github/labels.json` のモデルラベル、Cloud のモデル抽出スクリプトの許可リストは、`Auto` と `MODEL_CHOICES` に一致しなければならない。
  - 利用者がモデルを指定しない場合のメインモデルは、ローカル実行の全ての面で `DEFAULT_MODEL` としなければならない。対象は `hve orchestrate`（`--model` と環境変数 `MODEL` の両方が未指定または空）、`SDKConfig`（`from_env()` と空文字の直接指定）、CLI ウィザードの初期選択、GUI の新規設定の既定値である（ウィザードと GUI は、選択肢に `DEFAULT_MODEL` が無い場合だけ先頭の選択肢を初期選択とする）。`Auto` は利用者が明示的に選んだときだけ使う（FR-MODEL-02）。GUI の保存済み設定値は移行・上書きしない。Cloud の Issue Template の先頭選択肢（`Auto`）は本規定の対象外とする（Cloud で `DEFAULT_MODEL` を選べるかを確認していないため）。
- **FR-MODEL-02**: `Auto` 指定時は SDK へ `model="auto"` (wire 値) を渡し、サーバ側 Auto Model Selection（GitHub Copilot の動的モデルルーティング）に委譲する。`reasoning_effort` はクライアント側で設定しない（サーバ側がモデル毎に適切な effort を選ぶ）。内部センチネル `MODEL_AUTO_VALUE='Auto'` → wire 値 `MODEL_AUTO_WIRE_VALUE='auto'` の変換は [hve/config.py](hve/config.py) の `to_wire_model()` 関数で集中管理。ユーザーが `reasoning_effort` を明示指定した場合は経路を問わず尊重する。SDK が `reasoning_effort` 引数を未サポートの場合は `TypeError` を捕捉し引数除外で再試行する（[hve/orchestrator.py](hve/orchestrator.py) `_create_session_with_auto_reasoning_fallback`）。
- **FR-MODEL-03**: 未サポート / 廃止モデルが渡された場合、ヘルパー `_normalize_model_with_warning` は警告を発出し `Auto` を返す（実際の呼び出し経路は要確認）。v3.30 で、`MODEL_CHOICES` と `Auto` に加え、SDK `list_models()` の結果を保存したキャッシュ（[hve/models_cache.py](hve/models_cache.py)、TTL 切れを含む）にあるモデル ID も未サポートとして扱わず、そのまま通さなければならない。利用者がローカル実行で明示したモデル（例: 費用を抑えるための軽量モデル）が、無言で `Auto`（サーバ側の選択）へ置き換わり、想定外の費用になることを防ぐためである。判定のためにネットワークへ出てはならない。Cloud の Issue Template の選択肢（FR-MODEL-01）は変えない。出典: 利用者依頼（2026-09-30、比較実測 N5-4 のモデル指定「最低のコストのもの」）。
- **FR-MODEL-04**: HVE は GitHub Copilot SDK の `create_session(tool_search=...)`（ツール定義の遅延ロード）を CLI / GUI から設定可能とする。有効時は SDK へ `tool_search={"enabled": True}` を渡し、無効時は当該引数を渡さない。**既定は有効**とする。利用者が `tool_search_defer_threshold` を正の整数で指定した場合は `defer_threshold` として同じ dict へ渡し、未指定時はキー自体を送らず SDK 既定へ委譲する。設定値は Step 実行経路のメインセッション、サブセッション（Pre-QA / Review）、およびローカル orchestrator の ARD 補助・Fleet 親・Code Review セッションへ同一値を伝搬しなければならない。Cloud Session はローカルに登録された Plugin / MCP / Skill を継承する保証を確認できないため対象外とし、対応済みと表示してはならない。本要件の `SDKConfig.tool_search` は、AAGD ワークフローのパラメータ `enable_tool_search`（生成する AI Agent の Foundry Toolbox 設定）とは別ドメインであり、HVE 自身の SDK セッションにだけ作用する。本要件はツール定義がコンテキストの大きな割合を占める実態（実測: 登録 171 ツール / 54,865 tokens のうち実使用は 10 種 / 9,108 tokens）を背景とする。設定伝搬に加え、FR-TS-11 の同一条件比較で削減効果を実測可能にする。**2026-08-13 の実測（Copilot CLI 1.0.79 / SDK 1.0.7、`session.metadata.contextInfo`）では、`tool_search` の有効 / 無効 / `defer_threshold=1` の 3 条件で `toolDefinitionsTokens` が 52,756 で完全に一致し、全ツールの `defer_loading` が `null`、`tool_search_tool` もツール一覧に現れなかった。**この過去実測を現在の SDK / runtime の結果として流用してはならない。
- **FR-MODEL-06**: FR-MODEL-04 の既定有効化は、利用者による明示的な無効化を上書きしてはならない。`--no-tool-search` と `HVE_TOOL_SEARCH` の falsy 値は無効として扱い、当該実行では SDK へ引数を渡さない。GUI では新規プロファイルの初期値だけを有効とし、**保存済み設定の値は移行・上書きしない**（保存済みの `false` が利用者の明示指定か旧既定かを区別できないため）。ランキング実装の既定（FR-TS-01 の `tool_search_ranking`）は本変更の対象外であり `sdk` のままとする。
- **FR-MODEL-05**: SDK が `tool_search` 引数を未サポートの場合、Step 実行経路のセッション生成（[hve/runner.py](hve/runner.py) `_create_session_with_auto_reasoning_fallback`）は `TypeError` を捕捉して当該引数を除外し再試行しなければならない。未サポートを理由に実行を停止してはならない（既存の `reasoning_effort` 縮退規則に従う）。
- **FR-MODEL-07**: 開発環境セットアップ（[hve/setup-hve.sh](hve/setup-hve.sh) / [hve/setup-hve.ps1](hve/setup-hve.ps1)）は、**既定で `github-copilot-sdk` を最新版へ更新しなければならない**（`pip install --upgrade --no-deps github-copilot-sdk`）。`--no-deps` は必須とする（付けないと pip resolver が `pydantic-core` を pydantic 本体の pin から乖離させ GUI 起動が例外になる）。再現性のために版を固定する経路は明示フラグ（`--pin-sdk` / `-PinSdk`）に限り、指定時だけ単一の宣言ファイル [hve/copilot-sdk.lock](hve/copilot-sdk.lock) の版を導入しなければならない。`--upgrade-sdk` / `-UpgradeSdk` は最新化に加えて当該ファイルの pin 行と Copilot CLI ランタイム版の記録行を書き換えなければならない（既定経路は宣言ファイルを書き換えてはならない）。既定を最新追従へ変更した根拠は利用者の明示的な方針決定であり、下記のランタイム整合検証は変更後も維持する。あわせてセットアップは、SDK が pin する Copilot CLI ランタイム（`copilot/_cli_version.py` の `CLI_VERSION`）を先読みし、実際に解決されるランタイムの埋め込み版と突合して不一致を警告しなければならない。埋め込み版の取得には `--no-auto-update` を付与しなければならない（`--version` 単体はオンライン更新チェックの結果である「最新利用可能版」を返すため pin との突合に使えない。実測: 埋め込み 1.0.69 のバイナリが `--version` では 1.0.78 を返す）。pin を無効化する環境変数 `COPILOT_CLI_PATH` / `COPILOT_CLI_EXTRACT_DIR` / `COPILOT_SKIP_CLI_DOWNLOAD` が設定されている場合は警告しなければならない。ランタイム整合検証は、SDK の生成イベントパーサ（`copilot/generated/session_events.py`）がイベントのエンベロープ（`id` / `timestamp` / `type`）を assert で固めており、pin と異なるランタイムを掴むと `session.event` の解析が `AssertionError` となって当該イベントが黙って捨てられる（終端イベントを取り逃すと `send_and_wait` がタイムアウトまで返らない）ことへの予防である。`pyproject.toml` の下限指定は API 互換の床であり、導入版の情報源としてはならない。宣言ファイル [hve/copilot-sdk.lock](hve/copilot-sdk.lock) 自体は UTF-8 / LF / BOM なしで保持しなければならない。`--upgrade-sdk` / `-UpgradeSdk` の書き換え処理は当該形式を維持したまま pin 行と CLI ランタイム記録行だけを更新しなければならない。
- **FR-MODEL-08**: 開発環境セットアップは、Windows / macOS / Linux のいずれでも外部 `copilot` コマンド（npm パッケージ `@github/copilot`）を**最新版へ導入・更新**しなければならない。未導入時は `@github/copilot@latest` を導入する（他の OS ツールと同じ確認プロンプトに従い、`-Yes` / `-y` で省略できる）。導入済みかつ npm グローバル管理下の場合は確認なしで `@github/copilot@latest` へ更新しなければならない。`copilot` が解決できるのに npm グローバル管理下でない場合は、二重導入で PATH 解決が分岐するため npm 導入を行わず、警告と更新手順を提示しなければならない。`--no-install-tools` / `-NoInstallTools` と `--check-only` / `-CheckOnly` は導入・更新を抑止し、検出結果の報告だけを行わなければならない。npm が解決できない場合は Node.js の導入手順とともに警告しなければならない。本 CLI は GUI の Copilot チャットパネル（FR-GUI-10）の前提であり、SDK が pin する Step 実行用ランタイム（FR-MODEL-07）とは独立に自己更新するため、`COPILOT_CLI_PATH` 等で Step 実行へ流用してはならない。

- **FR-MODEL-09**: 既定モデル（FR-MODEL-01）を変更する変更は、[hve-dev/model-upgrade-checklist.md](hve-dev/model-upgrade-checklist.md) に列挙したハーネス部品（事前 QA、Phase 3 敵対的レビュー、言語指示、大型 Prompt の固定手順、計画の分割閾値）について、新しい既定モデルで外して比べる対象を確認し、確認結果（実測値または未実測の理由）を変更記録に残さなければならない。本要件は確認と記録の手順だけを定め、自動の比較実行・新しい設定項目を追加してはならない。
- **FR-MODEL-10**: HVE がローカル session を作成・再開するときは、SDK に `request_extensions=False` を渡さなければならない。呼び出し側が明示した値は上書きしない。Cloud Session は対象外とする。SDK が引数を未サポートの場合は FR-MODEL-05 と同じく `TypeError` を捕捉し、引数を除外して再試行する。本要件は、利用者環境に `~/.copilot/extensions` があると `extensionSdkPath is required when standalone extensions are requested` で session を作れない不具合（2026-09-24、SDK 1.0.13 / CLI ランタイム 1.0.83 で再現）を防ぐためのものであり、HVE は standalone extension を使わない。対象は Step 実行経路と orchestrator の `_create_session_with_auto_reasoning_fallback`（Cloud Session から local session へのフォールバックを含む）、routed session の `build_routed_session_options`、resume で引き継ぐ session 引数、FR-TS-12 の inventory probe session である。`enable_config_discovery=False` で作成する session（`repository_query`）は同じ環境で不具合が再現しないため対象外とする（2026-09-24 実機確認）。

### 3.5.1 Tool Search ランキングの HVE 実装（FR-TS）

FR-MODEL-04 が「SDK 組み込みツール検索を有効化する設定」を規定するのに対し、本節は「有効化したときの**ランキングを HVE 実装へ差し替える**」ことを規定する。両者は直交し、FR-MODEL-04 の bool 契約（`--tool-search` / `--no-tool-search`）の意味を変更してはならない。

- **FR-TS-01**: HVE は SDK 組み込みの `tool_search_tool` を、`define_tool(name="tool_search_tool", overrides_built_in_tool=True)` で登録した HVE 実装へ差し替えられなければならない。差し替え実装は、SDK ライブツールについては `ToolInvocation.available_tools`（SDK が当該ツール呼び出し時にだけ渡すライブカタログ）を唯一のカタログ入力とし（`available_tools` に現れない Skill は FR-TS-06 が定める登録経路でカタログへ合流させる）、HVE 側から MCP へ `tools/list` 等の RPC を発行してはならない。発見結果は `ToolResult.tool_references`（ツール名の列）で返し、定義展開は SDK に委ねる。差し替え対象名は SDK 側の定数（`copilot.session._TOOL_SEARCH_TOOL_NAME`）と一致していなければならない。
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
  - **SDK resource routing による上書き**: 宣言済み MCP の情報源を `.github/.mcp.json` とする記述は FR-TS-12 の SDK resource snapshot に置き換える。明示比較では、同じ snapshot・model・`context_tier`・分類 policy・MCP / Skill 選択を用いた Tool Search OFF / ON の 2 セッションをプロンプト送信なしで測定する。両セッションの接続済み MCP 名または有効 Skill 名が一致しなければ削減率を算出せず「比較不能」とし、片側の値や過去値で補ってはならない。比較は CLI / GUI の明示操作時だけ実行し、通常 Workflow のために追加セッションを作成してはならない。`hve toolsearch context --step <Step-ID>` を指定した場合は、registry の base Step と Skill manifest から同じ required / optional Skill を解決し、FR-TS-13 の `required_mcp_servers_by_skill` で導出した required MCP を同じ route へ含めなければならない。fan-out 子 ID は `/` より前の base Step ID で解決する。`--step` を省略した従来の Workflow 単位測定は維持する。未知の Step はセッション作成前に理由付きで拒否する。
- **FR-TS-12**: HVE は GitHub Copilot SDK が認識する Plugin / MCP Server / Skill の安全な read-only resource snapshot を単一実装で取得しなければならない。
  - 既存の [hve/copilot_client_factory.py](hve/copilot_client_factory.py) で client を開始し、対象 repository を working directory として server-scoped `client.rpc.mcp.discover(...)` / `client.rpc.plugins.list()` / `client.rpc.skills.discover(...)` を呼ぶ。Plugin提供Skillの所有元は server-scoped `skills.discover` 応答に含まれないため、全 discovered MCP serverを `disabled_mcp_servers` に指定した no-prompt inventory sessionを1つだけ作り、`session.rpc.plugins.list()` / `session.rpc.skills.list()` から補完してよい。inventory sessionでは `send`、MCP接続・tool呼出し、auth handlerを使用してはならず、sessionとclientを成功・失敗を問わず停止する。
  - process snapshotとして保持または GUI へ渡してよい値は、resource kind、exact name、enabled、SDK source kind、Plugin marketplace、提供元 Plugin 名・version、Skill description に限定する。snapshot自体をdiskへ永続化してはならない。path、direct source ID、raw config、transport command、URL、args、env、header、credential、生 SDK payload、例外本文を保持または表示してはならない。
  - Plugin / MCP / Skill はそれぞれ `ready` / `unverified` を独立に持つ。取得失敗を 0 件と表示せず、取得できた kind を別 kind の失敗で捨ててはならない。全RPC、inventory session作成、cleanupは内部の共有45秒deadline内で完了させ、APIごとに45秒を再付与して総待ち時間を伸ばしてはならない（v3.41: 実 SDK の探索は単独でも約 10〜12 秒、3 process 並列で 14〜17 秒かかり、従来の 15 秒では並列起動した `resume` が MCP / Skill の unverified で失敗したため 15 秒から改めた）。共有 deadline の期限切れで欠けた snapshot は process cache へ保持してはならない（後続 caller が再探索できるようにする）。snapshot は process 内だけで runtime path・working directory 単位に再利用し、disk cache・daemon・watcher・定期再取得を追加してはならない。GUI の利用者による明示的な再列挙だけは同じ単一実装を `force_refresh` で再実行してよい。
  - SDK が提供元 Plugin 名を返す MCP / Skill は Plugin 分類を既定値として継承できる。同名Pluginが複数marketplaceに存在して所有元を一意に対応付けられない場合、または提供元を SDK 応答から確認できない場合は、名前・path・descriptionから推測せず、個別resource分類がなければ `unclassified` とする。no-prompt inventory sessionが失敗してもserver-scoped取得済みresourceは保持し、確認できなかったSkill所有元だけを未設定とする。
- **FR-TS-13**: FR-TS-12 の resource を `knowledge` / `software-engineering` / `both` / `unclassified` の 4 値へ分類し、ローカル HVE session の公開範囲を決定しなければならない。
  - 単一の metadata 正本は FR-TS-03 と同じ `policy.json` とし、`resource_classifications.plugins` / `resource_classifications.mcp_servers` / `resource_classifications.skills`、`knowledge_tool_allowlists`、`software_engineering_tool_allowlists`、任意の `required_mcp_servers_by_skill` を保持する。`required_mcp_servers_by_skill` は required Skill の exact 名をキー、当該 Skill が要求する MCP server の bare exact 名リストを値とし、空リスト・wildcard・重複・非文字列を拒否する。exact MCP / Skill 分類 > 提供元 Plugin 分類 > `unclassified` の順で解決する。分類値・表構造・exact name を検証し、不正 policy は SDK resource routing を開始せず理由を返す。
  - `knowledge` は registry 上の全 13 Workflow で補助利用候補とする。`software-engineering` は生成アプリケーションの 9 Workflow（`aas` / `ada` / `aad-web` / `asdw-web` / `adfd` / `adfdv` / `aag` / `aagd` / `aar`）と source code document Workflow `adoc` で利用候補とする。`both` はいずれかの対象なら候補、`unclassified` は既定で除外する。Workflow集合は単一定数とし、registry にない値を許可してはならない。
  - enabledでないresourceは分類にかかわらず有効化してはならない。Step の required Skill と、Step契約または required Skill の `required_mcp_servers_by_skill` が要求する exact MCP 名は分類による候補除外より優先して候補へ残す。ただし required は権限昇格ではなく、対象 Workflow で許可される category と exact tool allowlist を迂回してはならない。required resource の未設定・disabled・allowlist空・対象 Workflow で許可される tool が 0 件・session runtime不在は fail-closed とする。optional resource の不在・disabled・allowlist空は Step を失敗させず除外する。呼び出し側が明示した required MCP 名と Skill 依存から導出した名前は順序を維持して重複除去する。
  - MCPまたはSkill snapshotが`unverified`の場合、未発見resourceがambient discoveryから漏れるため、resource-routed sessionを作成せずfail-closedとする。Plugin snapshotまたはSkill所有元補完だけが`unverified`の場合はPlugin分類の継承を行わず、exact MCP / Skill分類だけで続行してよい。
  - session 作成前に `enable_config_discovery=True`、`enable_skills=True`、未選択 MCP の `disabled_mcp_servers`、未選択 Skill の `disabled_skills` を渡す。Skill directory は required repository / external Skill の既存 exact 解決を維持し、個人 directory や Plugin cache path を HVE が探索してはならない。
  - MCP toolはcategoryを問わず、対象categoryの`*_tool_allowlists.<server>`に列挙した、`session.rpc.mcp.list_tools(...)`が返すbare exact tool名だけを許可する。`both` resourceは、Knowledgeだけが対象のWorkflowではKnowledge allowlist、Software Engineeringも対象のWorkflowでは両allowlistの和集合を使う。allowlistが空のoptional serverはsession作成時からdisabledにし、required serverはsession作成前に失敗させる。runtime discovery で得た tool 名を HVE が policy へ自動保存・自動許可してはならない。利用者が実在を確認した bare exact tool 名だけを永続 allowlist とする。
  - session 作成後かつ最初の `send` より前に実toolを照合し、許可外toolをsource-qualified `mcp:<server>-<tool>`として既存`excluded_tools`へ追加したうえで`session.rpc.options.update(...)`を適用する。allowlist toolの欠落、server未接続、tools/list失敗、options更新失敗では、optional serverを`session.rpc.mcp.disable(...)`でsession内だけ無効化し、required serverではsessionを破棄して失敗させる。HVEはtool名からread/writeを推測して許可してはならない。利用者が明示した `available_tools` / `excluded_tools` を分類 routing が拡張してはならず、分類による制限と積集合になるよう維持する。
  - Tool Search は上記で許可された resource の定義だけを遅延公開する。Tool Search を discovery、認証、権限境界の代替として扱ってはならない。Plugin 分類は MCP / Skill の継承 metadata であり、SDK に session-scoped Plugin disable API が無い環境で Plugin が持つ hook / agent / instruction 全体を無効化できたと主張してはならない。
  - Plugin / MCP / Skill の導入・更新・永続構成・有効化・認証は GitHub Copilot CLI / SDK の責務とする。HVE は `.github/.mcp.json`、`--mcp-config`、MCP config writer、OAuth/browser flow、provider別 discovery adapterを持ってはならない。FR-CLI-91のWork IQ互換adapterは共通snapshotから値を射影するだけとし、独自 discovery / config / authを行ってはならない。Cloud Session は本要件の対象外とし、local snapshot を remote session の証拠として流用してはならない。
  - **session resource readiness 改訂（2026-09-06）**: 以下は本要件の create / resume 前の除外と send 前の runtime 検証を具体化し、初期化・接続待ち・失敗時 cleanup に関する従来記述に優先する。分類、対象 Workflow、exact allowlist、Work IQ 専用の問い合わせ結果 schema と既存例外は変更しない。
    - **実効除外集合**: caller の `disabled_mcp_servers` / `disabled_skills` と route の除外を、それぞれ exact 名の順序維持・重複除去した和集合にする。required MCP / Skill との exact 衝突は `create_session` / `resume_session` より前に fail-closed とする。同じ実効集合を `apply_resource_route` の MCP / Skill 選択・検証対象にも反映し、kwargs だけを変更して元 route の有効 server を列挙し続けてはならない。caller が除外した optional resource を再初期化・再公開してはならない。
    - **検証順序**: session 取得後、required Skill を `session.rpc.skills.list()` で runtime 検証し、実効選択 MCP がある場合は `session.rpc.tools.initialize_and_validate()` → `session.rpc.mcp.list()` による bounded な接続待ち → connected な各 exact server の `session.rpc.mcp.list_tools(...)` → 全 server 分を集約した `session.rpc.options.update(...)` の ACK 確認、の順に進む。この gate の成功または後述の許可された optional 無効化が確定する前に `send` / query を開始しない。初期化 API 不在・未サポートは検証失敗とし、API の正常復帰や no-op を readiness の証拠として接続・tool 検証を省略してはならない。
    - **runtime 応答**: Skill / MCP / tool の応答 schema と exact identity を検証する。不正 schema、同一 resource kind / server の応答内で重複した exact 名、未知の status を、正常・connected・有効な空集合に読み替えてはならない。required Skill の runtime 不在・disabled は失敗とする。MCP の `pending` は connected ではなく、共有 deadline 内だけ再確認できる。`needs-auth` は、HVE が認証を開始しないため再確認せず、`failed` / `disabled` / `stopped` / 不在と同じく required / optional の失敗分岐へ直ちに送る（2026-09-24 改訂。待っても無人実行では結果が変わらず、optional でも共有 deadline の枯渇で停止していたため）。`failed` / `disabled` / `stopped` / 不在も接続成功とは扱わず、required / optional の失敗分岐へ送る。HVE は待機中も認証を開始しない。 2026-09-30 bugfix: 実効選択 MCP がすべて optional で caller filter が無い場合、最初の `initialize_and_validate()` は共有 deadline のうち最大 20 秒（`_OPTIONAL_INIT_BUDGET_SECONDS`）で打ち切る。打ち切った後、`mcp.list()` を共有 deadline 内で poll し（`pending` の server があれば状態が確定するまで待つ）、`needs-auth` / `failed` の server が見つかった場合に限り、その server を上記の optional 分岐で session 内 disable し、残りの server について `initialize_and_validate()` からやり直す。原因となる server が見えない場合（全 server が connected）は、初期化が遅いだけの可能性があるため、残りの共有 deadline で `initialize_and_validate()` を待ち直し、その deadline で確定しなければ従来どおり失敗とする（初期化の停止を readiness の証拠にしない）。`needs-auth` の optional server（例: 未認証の Work IQ Plugin）が初期化を止め、共有 deadline を使い切ってすべての Step が失敗していたため（実測: 2026-09-30 の比較実測 P0）。
    - **共有時間予算**: セッション取得後の `apply_resource_route` の入口から出口までを monotonic clock による共有 60 秒 deadline で制限する。required Skill 検証、初期化、接続状態取得、tools/list、options ACK、optional disable の全 RPC と poll 待機を含み、API / server ごとに予算を再付与しない。既存 caller がより短い deadline を持つ場合は早い方を優先し、必要なら optional な内部 keyword 引数で伝播する。公開 flag・設定は追加しない。poll 間隔は 0.5 秒とし、残時間が短い場合だけその残時間までに制限する。
    - **期限・失敗・cancel**: routing 内の各 RPC / 待機の開始前と完了後に正の残時間を確認する。期限内の optional 検証失敗は、残時間内に当該 server の session-scoped disable が成功した場合だけ除外して続行できる。required resource の検証失敗、caller filter の適用を保証できない失敗、disable 失敗は fail-closed とする。共有 deadline 枯渇後は新たな disable 予算や RPC を追加せず、optional でも続行しない。 v3.34 改訂: optional な MCP server が `pending` のまま、共有 deadline の残りが予約分（`min(10 秒, 共有予算の 20%)`、`_OPTIONAL_DISABLE_RESERVE_SECONDS`）になった場合は、その時点で optional の検証失敗として扱い、残りの予約分の中で session 内 disable して続行する（予算を新たに足すのではなく、同じ deadline の中で無効化を終えるための予約である）。required の `pending` は従来どおり deadline まで待ち、確定しなければ失敗とする。並行セッションが多いと Azure MCP などの起動が 60 秒を超え、optional の MCP だけのために Step が失敗していたため（実測: 2026-09-30 の比較実測 P0 で `resource routing deadline exceeded` が 1 run あたり最大 9 Step）。`CancelledError` は cleanup 後に再送出し、通常の optional 失敗へ降格しない。期限後の RPC 復帰を成功や cancel 完了の証拠とみなしてはならない。
    - **集約 ACK**: options 更新が必要な場合は server ごとでなく全体で 1 回だけ行い、応答の `success is True` だけを適用確認とする。`success=False`、応答 decode / schema 例外、RPC 例外は options 更新失敗として既存の required / optional 分岐へ送る。required MCP または caller 明示の `available_tools` / `excluded_tools` を含む更新の失敗は fail-closed とする。選択 MCP がすべて optional かつ caller filter がない場合は、残存する選択 MCP をすべて session 内で disable でき、共有 deadline の残時間が正の場合だけ継続してよい。MCP に依存しない検証済み required Skill だけでは、この optional MCP 継続を拒否しない。ACK 非成功を無条件の session failure にせず、2 回目の options 更新で救済してもならない。
    - **filter 後 metadata 再構築**: 集約 ACK の成功後に実効選択 MCP が残る場合、`session.rpc.tools.get_current_metadata()` が返す MCP identity を、route の exact tool allowlist と caller の `available_tools` / `excluded_tools` の積集合を適用した最終 tool 集合へ照合する。caller filter で正当に除外された allowlist tool を不足または選択外としてはならない。SDK が定義する source-wide filter `mcp:*` は全 MCP identity への allow / exclude として適用するが、HVE 独自の wildcard 構文は追加しない。built-in tool は照合対象外とし、`defer_loading` の真偽にかかわらず exact MCP identity が存在すれば選択済み tool として数える。schema 不正、片側だけの server/tool identity、重複 identity、最終集合外の MCP identity を正常応答へ読み替えてはならない。最終集合外の MCP identity で停止する場合は、違反した exact server / tool identity を決定的な順序でエラーへ含め、tool の説明・引数・応答本文は含めない。SDK が discovery に公開せず session へ暗黙追加する既知の built-in MCP は、検証済み enabled route に含まれる場合を除き、create / resume 前の共通除外へ明示的に含める。応答が未初期化、最終集合の identity が不足する場合、または最終集合外の MCP identity を含む場合だけ、同じ共有 deadline 内で `initialize_and_validate()` を追加で最大 1 回実行し、metadata を 1 回再取得する（最終集合外の identity を条件に含めたのは 2026-09-24 改訂。session-scoped の `mcp.disable` の後も、`get_current_metadata()` は再初期化まで無効化した server の tool を返すため）。再取得後も最終集合外 identity、schema 不正、required/caller-filter 対象の欠落が残る場合は fail-closed とする。最終集合の identity の欠落だけが残り、全 server が optional かつ caller filter がない場合に限り、既存の session-scoped disable 分岐で全選択 server を無効化して継続できる。2 回目の options 更新、追加の initialize retry、公開 flag・設定は追加しない。この metadata 照合は model-visible 定義の準備を確認するもので、tool の実呼び出し成功を証明しない。
    - **cleanup**: 本要件の「session を破棄」は disk 上の再開状態を保持する disconnect を意味し、routing apply の外側で別の上限 5 秒を適用する。client の所有者だけが既存の stop 上限 5 秒・force stop 上限 2 秒で停止し、借用 client を停止しない。session delete、永続構成変更、認証、SDK 改造による回復を行わない。
    - **0 MCP と非実行境界**: 実効選択 MCP が 0 件なら MCP 初期化・接続 poll・tools/list を追加しないが、required Skill の runtime 検証と caller filter が必要な場合の集約 ACK は省略しない。FR-TS-12 の no-prompt inventory は既存の全体 15 秒予算と MCP 非接続を維持する。Prompt plan に runtime 初期化・MCP 接続を追加してはならない。

### 3.6 セキュリティ

- **NFR-SEC-01**: `GH_TOKEN`・`COPILOT_PAT` 等の秘密情報を Issue body / 標準出力に出力してはならない。Resume 用 `state.json` と `config_snapshot` 復元は §5.6 のとおり廃止済みであり、現行要件ではない。
  - FR-STATE-04 の durable store と resume plan は固定 allowlist とし、状態、時刻、数値、model ID、Workflow / Step / APP 識別子、sanitized replay descriptor、hash、例外型名だけを保存できる。prompt/response/reasoning 本文、tool 引数・結果、任意環境変数、token/credential、認証 URL、生 SDK payload、生 repository root を保存してはならない。
  - 保存不可の必須 replay 値は値を保存せず `missing_replay_keys` の key 名だけを保存する。resume 時は対話入力、GUI の current input、または Prompt の自然言語入力から再取得し、non-TTY で不足する場合は実行を開始してはならない。
  - **v3.40 明確化（利用者入力ではない既定値）**: `--ignore-paths` の値が `hve.config.DEFAULT_IGNORE_PATHS`（`docs` `images` `qa` `src` `work`、この順・完全一致）と同一のときは、利用者が指定した自由入力ではないため durable replay argv にそのまま保存し、`missing_replay_keys` に `ignore_paths` を含めない。これにより既定設定の CLI run は non-TTY の `hve resume --latest --action restart-step` で再入力なしに再開できる。1 件でも異なる値・順序（例: `tmp build`、既定から `qa` を除いたもの）は従来どおり key 名だけを保存し、再入力を要求する。出典: システムテスト結果 [tests/system-test/20261001-2125-CLI-Prompt-real-run-resume-snippet-result.md](tests/system-test/20261001-2125-CLI-Prompt-real-run-resume-snippet-result.md) F-02。
- **NFR-SEC-02**: `docs-original/` 配下は全 Agent から読み取り専用とする（`.github/copilot-instructions.md` §0）。
- **NFR-SEC-03**: `git add` 時は `:!path` pathspec 除外で機密ファイルを除く。pathspec はリスト引数として渡し、shell インジェクションを防止する（[hve/orchestrator.py](hve/orchestrator.py) `_git_add_commit_push`）。
- **NFR-SEC-04**: Step セッションの権限コールバック（[hve/permission_handler.py](hve/permission_handler.py)）は、シェル実行の権限要求が Skill `harness-safety-guard` の CRITICAL パターン（[.github/skills/harness-safety-guard/references/danger-patterns.md](.github/skills/harness-safety-guard/references/danger-patterns.md)）に一致する場合、実行前に拒否し、拒否した事実を記録しなければならない。CRITICAL 以外のパターンを本層で拒否してはならない（誤検知による停止で長時間ジョブの所要時間を延ばさないため）。本要件のために新しい設定項目・環境変数を追加してはならない。

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
  - 要求テストマッピングの generator は単一共有 mapping authoring parser を使用し、既存の compact 見出し（明示 ID、同一 prefix の `/` 省略、昇順数値範囲 `〜` / `～` / `~`、数値の `・` 省略）と表行を同じ受理集合として解釈し、各 ID へ判定と test path を対応付けなければならない。新しい authoring 構文を追加してはならない。
  - **session resource readiness 改訂（2026-09-06）**: FR-TS-13 / FR-CLI-76 / FR-CLI-90 / FR-CLI-91 に追加する共有待機・deadline・初期化 / 接続待ち / timeout の観測契約は `feature` として上記順序を適用する。既存 ID の従属契約改訂として扱い、新規 FR-ID は追加しない。要求・mapping だけを改訂した段階では追加予定テストを `要追加` とし、既存テストの成功を本改訂の RED / GREEN 証跡へ流用しない。実装前の索引同期と同じ対象テストによる RED / GREEN 確認は後続工程で必須とする。
- **FR-MAINT-04**: HVE 対象変更を含む PR は、前項のトレーサビリティブロックを記録しなければならない。CI は変更パス取得失敗、ブロックの欠落・重複・未置換値、組合せ違反、未知または索引statusが `active-or-described` 以外の ID、存在しない・リポジトリ外・許可テストルート外のパス、要件 ID と要求テストマッピング上の test path 不一致を拒否する。`feature` では要求定義、要求テストマッピング、機能索引の更新と RED / GREEN 証跡を追加で要求する。N/A と変更種別の意味的妥当性は CI が推測せず、既存 branch protection の承認レビューで確認する。HVE 対象外の変更のみである場合は本ゲートを適用しない。validator の正規entrypointは `.github/scripts/validate-hve-requirement-traceability.py` とし、リポジトリroot、PR本文ファイル、変更パス一覧ファイルを明示入力として受け取る。PR workflow は `pull_request` イベントだけで当該 validator を必須ゲートとして実行し、PR本文を shell の `run` へ直接展開せず、最小読取権限で実行する。既定ブランチで実行するtrusted workflowは `pull_request_target` を使用し、base側validatorとPR内容を別ディレクトリへcheckoutし、PR内容はデータとして検証するだけで実行してはならない。branch protection の required status check は両workflow名とvalidator job名から構成されるcheck contextを含み、承認レビューを1件以上要求しなければならない。管理者による直接 push を許容するため、`.github/CODEOWNERS` に一致する変更でも Code Owner 承認を追加要件とせず、管理者には branch protection を強制しない（`require_code_owner_reviews=false`、`enforce_admins=false`）。
  - PR validator は generator と同じ単一共有 mapping authoring parser を使用し、既存 compact 見出しと表行を同じ受理集合で解釈しなければならない。別の requirement ID / test link parser を保持せず、新しい authoring 構文を追加してはならない。
- **NFR-CTX-01**: repository-wide instructions のうち **HVE 要求トレーサビリティに関する記述**は検索ルーターだけを保持し、要求定義書本文を埋め込んではならない。当該ルーターは、(1) HVE 対象変更または HVE 対象パスの不具合調査で `hve-requirement-traceability` Skill を使用する、(2) HVE コアパスでは path-specific instructions も適用する、(3) 要求定義書全文を既定の入力にしない、の 3 箇条だけで構成する。CI はルーターの見出し・3 箇条・Skill 参照・要求書パス・既知の要件 ID / schema key /取得オプションの重複を決定論的に検査する。Coding Agent は customization の raw source を入力として受け取るため、既知識別子の重複検査は HTML comment、code span、fenced / indented code を含むルーター外の raw source 全体を対象とする。言い換えによる意味的な分散・矛盾は捏造して判定せず人間レビューへ委ねる。他のリポジトリ共通ルールは本要件の対象外とする。初回の関連要件取得は最大 5 チャンクかつ最大 800 tokens を上限とし、追加コンテキストは FR-MAINT-02 の段階的拡張でのみ取得する。

#### 本要件の導入ゲート

FR-MAINT-01〜04 / NFR-CTX-01 の追加後、要求テストマッピング、RED 契約テスト、TDD policy の生成元、機能・テスト索引、PR validator / workflow を同一変更セットで同期し、全契約テストを GREEN にするまで、HVE 保守機能の実装完了を宣言してはならない。途中状態では新規 ID が索引に無いことを理由に既存要件へ偽装せず、bootstrap 中であることを明記する。

#### 実行面横断の重複実装防止

HVE は Cloud Agent Orchestrator / CLI Orchestrator / GUI Orchestrator の 3 実行面と、それらが共有する中核モジュールから構成される。同一の規範ルールが複数の実行面へ個別に実装されると、受理集合や検査項目が面ごとに乖離する。本項はその乖離を機械的に検出可能にする。

本項で **規範リテラル** とは、`.github/copilot-instructions.md` または Skill が規定するルールを機械判定するために実装が直接参照する固定文字列またはキー名を指す。

- **FR-MAINT-05**: HVE 対象の実装シンボル索引を `hve-dev/hve-surface-inventory.csv` として機械生成する。生成の正規 entrypoint は `hve-dev/generate_tdd_inventory.py` とする。索引対象は §3.7 対象境界の判定に一致するパスだけとし、当該判定は「対象パスの機械判定は単一の validator に集約する」原則に従って既存判定を再利用し、別の範囲定義を作ってはならない。索引は同一入力に対して決定的に生成し、対象外パスに由来する行を含めてはならない。索引の各行は、実行面（`cloud` / `cli` / `gui` / `core`）、シンボル種別、定義ファイルと行、振る舞い要約、当該シンボルが参照する規範リテラルの集合を保持する。CI は、生成スクリプトの出力と索引が不一致の場合、または対象外パスの行を含む場合に失敗させる。不一致の索引は stale として扱い、再生成するまで FR-MAINT-06 / FR-MAINT-07 の判断根拠に使ってはならない。参照数を表す列は静的解析による値であり、CI から `pytest <path>` や `python -m <module>` で起動される経路を数えない。当該列だけを根拠に未使用と判断してはならない。本索引は HVE アプリケーション自体だけを対象とし、HVE が生成・支援する他アプリケーションの成果物を含めてはならない。後者のスコープ解決は `app-scope-resolution` Skill と生成物側のカタログが担う。
- **FR-MAINT-06**: 規範リテラルを判定する実装は、リテラルごとに単一とする。同一の規範リテラル（例: タスク完了報告の検証マーカー、`plan.md` の `## 完了条件` セクション）を判定する実装が複数の実行面に併存してはならず、他面は単一の実装を呼び出す。CI は FR-MAINT-05 の索引を用いて、規範リテラルごとの判定実装数を決定論的に検査し、許可された単一実装以外を検出した場合は失敗させる。検査対象の規範リテラルと許可実装は明示リストで固定し、リストに無いリテラルを推測して判定してはならない。規範リテラルを**生成する**側の文言複製は本要件の対象外とする。複製の維持を意図する根拠文書がリポジトリ内に存在する箇所（vendoring 等）も対象外とし、その根拠を許可リストに明記する。
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
  - `full` は、Coding Agent が判定表で `full` と判定し、かつ利用者が test scope = `full` を含む見積りを本要件の手順で承認した場合にだけ、既存 `hve/gui/tests` の offscreen 全量と同じ `cocoa` smoke を別プロセスで実行する。初期実装では新しい GUI automation framework、TCC 権限変更、OS / architecture matrix、新規 test dependency を追加しない。
- **FR-MAINT-11**: branch protection の required context である `Test HVE Python / HVE Python Tests` と `Test HVE Python / mdq index smoke test` は、`main` を対象とする全 Pull Request の最新 SHA へ結果を報告しなければならない。`.github/workflows/test-hve-python.yml` の `pull_request` trigger に `paths` / `paths-ignore` を置いて Workflow 全体を未起動にしてはならない。既存の重いテスト範囲は単一の変更パス検出 job で判定し、対象外 PR でも required 名の 2 job 自体は起動して成功を報告する。変更パスの取得に失敗した場合は両 required job を失敗させ、成功として扱ってはならない。本要件のために外部 Action、別 Workflow、利用者向け無効化 flag を追加してはならない。
- **FR-MAINT-15**: HVE の CI は、FR-MAINT-11 の重いテスト範囲に入る変更で検索の golden 評価を実行し、top-k の正解数が下限を下回ったら、その job を失敗させなければならない。対象の Workflow は `.github/workflows/test-hve-python.yml` とする。
  - mdq: `mdq index smoke test` job で、`mdq/golden-queries.json` を `tools/skills/markdown_query/benchmark.py` の `mdq_auto` シナリオで評価する。下限は **40 問中 30 問**。
  - cq: `cq Python Tests` job で、`cq/golden-queries.json` を `python -m cq.benchmark --with-cq --baseline ""` で profile ごとに評価する。下限は **hve 31 問中 20 問**、**app 25 問中 21 問**。この job は required context ではないため、失敗してもマージは止まらない。
  - 下限は、2026-09-25 の実測値（mdq 31、cq hve 21、cq app 22。記録: `work/20260925-0205-B0-GoldenRebaseline.md`）から 1 問を引いた値とする。下限を変えるとき、または golden の問数が変わるときは、同じ PR で本要件の数値と改訂履歴を直し、理由を書く。
  - 正解の判定には FR-MDQ-01 / FR-CQ-02 の単一の実装（benchmark の出力）を使い、CI の側に別の判定を実装してはならない。CI は出力 JSON の正解数を下限と比べ、結果を Step Summary に書くだけとする。benchmark に本要件のためのフラグを追加してはならない。
  - 重いテスト範囲の変更パスに `mdq/`、`tools/skills/markdown_query/`、`mdq.toml`、`cq.toml` を含める（`on.push.paths` と変更パス検出の両方）。golden の期待パスのうち、この範囲外の文書だけの変更ではゲートは動かない。そのような変更で期待する行が消えたり、重複したり、順位が下がったりすると、次に重いテスト範囲に入る PR で `mdq index smoke test` が失敗する。その PR で golden か下限を直す（下限を変える場合は、上の規則に従う）。
  - FR-MAINT-11 の報告規則（required の 2 job の起動と成功の報告、変更パス検出の失敗時の fail-closed）を変えてはならない。

#### HVE 自己テストの品質証跡

- **FR-MAINT-12**: HVE 自己テスト（`tests/prompt-version/` の統合テスト、CLI / GUI Full SystemTest とその直接依存の回帰検証）の controller が作成する全ファイルは、**元リポジトリ**の `tests/run/<run-id>/<task>/` を保存ルートとし、次の配置・保持契約を満たさなければならない。これは通常の一時作業 `work/` 規約に対する自己テスト限定の例外である。
  - 対象は request、plan、case 定義、status / checkpoint（shard / aggregate）、review、stdout / stderr・終了コード・実行ログ、画像・manifest、測定値・検証結果・report、安全な設定 snapshot、controller の実行補助ファイルを含む。暗黙の `artifacts/`、リダイレクト、子 Agent の出力先と相対リンクも同じ保存ルートへ束縛し、最終 report だけの移動で充足としてはならない。
  - テスト用 checkout / lane も同じ保存ルートの配下へ物理的に隔離し、`lanes/` と保持する品質証跡ディレクトリを兄弟として分離する。元リポジトリの `work/` へ新しい自己テスト証跡を出してはならない。lane 内の通常の `work/`、生成アプリの canonical `docs/` / `src/` / `knowledge/` / `qa/` は許容し、それらの出力契約や通常 HVE の work defaults、GUI セッション隔離・cleanup 実装を変更しない。
  - 親の品質証跡 run は pytest 等の起動前に確保し、fixture が作る新規 run と区別する。CLI / Prompt の既存 `HVE_WORK_ROOT` / `HVE_RUN_ID` を使う場合は子プロセス単位で整合させる。GUI は既存の環境変数 override だけで出力先を固定できると仮定せず、tests 配下の lane 内で通常の作業ルートを使う。
  - 完了した品質証跡は使い捨てにせず、完了を理由とする削除や自動期限削除を行わない。failed / blocked / interrupted も保存する。稼働中 checkpoint は既存の完全 JSON 更新・case-local shard・単一 writer の方式を維持し、確定証跡と区別する。再実行は新しい run / attempt に分離して旧証跡を上書きせず、過去履歴は移動・改変・削除しない。
  - cleanup は専用 lane / fixture に限定する。必要な安全な内部ログと生成物の検証証拠を lane 外の同じ保存ルートへ退避し、証跡一覧との対応、存在、必要な非空条件、相対リンク、既存契約で要求する hash を検証してから行う。正常な空 stderr 等は空である事実を記録し、内容を捏造しない。欠損・検証不能なら cleanup を止め、理由を記録して PASS としない。共有領域・並行 run・既存履歴を削除対象に含めない。
  - cleanup の有無にかかわらず、完了報告前に report / manifest が参照する全 run-scoped 証跡について、参照先の存在、必要な非空条件、相対リンク、既存契約で要求する hash を検証する。欠損・検証不能な参照を完了根拠へ含めず、状態と理由を記録して PASS としない。
  - 秘密値・credential・token・接続文字列・個人情報等の機微情報を、request・plan・ログ・画像・manifest・report 等のいずれの controller 生成物にも保存しない。取得前の非表示化・マスキング等で安全な証跡にし、加工済み証跡を無加工の原本と呼ばず、安全に取得できなければ理由を記録する。設定原本・復元専用データ・MCP 生ログを無条件に品質証跡へコピーしない。OS 資格情報ストア・SDK 管理キャッシュ・既存 `.venv` は証跡収集対象外とする。
  - 安全性を確認した report / JSON / 画像 / ログ等だけを Git 管理対象として選別可能にする。保存と commit は別であり、自動 commit や `tests/**` の無制限な ignore 解除は行わず、lane・fixture・秘密・設定原本・キャッシュは除外する。
  - CI 選別は既存の単一変更パス検出を再利用し、`tests/prompt-version/README.md` と 01〜09、CLI / GUI Full の能動指示12文書および `tests/README.md` の変更を push / PR の既存 HVE 検証へ接続する。`tests/run/**` の証跡追加だけでは重いテストを選択せず、FR-MAINT-11 の required check 報告と検出失敗時の fail-closed は維持する。CI 全体のログ移行・新しい upload / 保管基盤は対象外とする。
  - 新しい設定・CLI flag・環境変数・request / checkpoint schema・実行エンジンを追加しない。既存の承認・認証・権限・入力別名・canonical output・observability の非出力条件を証跡収集の都合で変更せず、本契約の承認をモデル利用・Azure 操作・実システムテストの実行承認へ流用しない。
  - 根拠: 2026-09-15 の利用者依頼で、自己テスト全生成物と lane の tests 集約（lane 内 canonical 構造は維持）、今後の作成先だけの変更、安全な証跡の Git 選別、能動 Prompt と直接依存に限る CI 接続、既存 checkpoint 更新方式の維持が承認された。これを新しい規範の根拠とする。既存の `tests/prompt-version/01-request-contract.md`〜`09-full-system-test.md`、`tests/[cli]SystemTest - Full.txt`、`tests/[gui]SystemTest - Full.txt` の保存指定と `tests/prompt-version/README.md` の隔離・cleanup 手順、`hve/tests/conftest.py` の新規 run 除去、`hve/gui/session_workdir.py` の GUI override は配置・保持設計の説明的根拠であり、従来から tests 保存が義務だったことや本改訂の実装・検証完了を意味しない。

- **FR-MAINT-13**: repository-wide の Coding Agent カスタマイズは、長時間タスクを有界に実行するため次を満たさなければならない。
  - repository Skill は Agent Skills の discovery surface である `.github/skills/<name>/SKILL.md` に配置し、frontmatter の `name` と親ディレクトリ名を一致させる。HVE が同名 Skill を再帰探索できることだけを根拠に、カテゴリ中間層へ必須 Skill を置いてはならない。
  - 長い terminal 出力は会話へ全文注入せず、静かな出力、ファイル保存後の限定抽出、または実行専用 subagent の要約を使用する。秘密値を含む原本を保存してはならず、正常な空出力を埋め草で非空にしてはならない。
  - 承認済みの計画は利用者の要求定義とする。Agent は要求定義から完了条件（exit code で判定できるコマンド）を導き、要求定義の抜け漏れ・矛盾・曖昧さは目的に最も適う合理的な判断で補い、判断と理由を記録して続行する。停止してよいのは、破壊的・不可逆・外部公開の操作（削除、force push、push、デプロイ、課金、権限変更）に既存の明示承認が必要な場合と、資格情報など利用者しか持たない情報が無いと進められない場合だけとし、その場合も依存しない作業を先に終える。セッションの時間・成果物数・tool 実行回数・同じ質問の回数を理由に停止してはならず、着手前に完了条件・時間上限・スコープ外の承認を求めてはならない。根拠: Claude Opus 5.5 の公式プロンプトガイド「Unattended agentic runs」（止まってほしい場面だけを名指しする）と、2026-09-26 の利用者依頼（停止規則の削除、承認済みの計画＝要求定義）。
  - 合否はコマンドの実出力と exit code を根拠とし、要求定義から導いた受入基準と根拠を完了報告へ記録する。既存の安全・承認・要求トレーサビリティ・偽 PASS 禁止を短縮のために緩和してはならない。
  - 2026-09-26 改訂: 1 セッション 1 成果物・90 分・同じ質問 2 回目での停止と、200 回超の tool 実行が見込まれる依頼での着手前 3 項目の承認ゲートを削除した。
  - v3.25 改訂（FR-E2E-01 / FR-PROMPT-13）: 依頼で宣言された範囲（デプロイ先 `resource_group`・外部公開の可否・予算の注記）の操作は承認済みとして扱う。ただし予算の注記は、FR-MAINT-10 の macOS runner のように特定の見積りに対する run 単位の明示承認を要求する操作の承認を代替しない。作業が残っているのに、(1) 済んだことのまとめと次の手順の予告だけで終える、(2) 「希望が無ければ続けます」と申し出て返事を待つ、(3) 残りの作業を止めない判断事項の一覧を渡す、(4) ターンの長さや区切りを理由に報告へ切り替える、の 4 つの形でターンを終えてはならない（危険な操作・破壊的な操作の確認は変えない）。曖昧な HVE 実行依頼では、依頼文と registry から一意に決まる値は理由を記録して使い、inline で確認するのは資格情報と宣言されていないデプロイ先・課金・外部公開に関わる値だけとする（FR-PROMPT-10 の「一意に決まらない値を推測で補完しない」は維持する）。根拠: HVE Orchestrator review report §7.4 W1 / W2 と §7.5。

- **FR-MAINT-14**: repository-wide の Coding Agent カスタマイズは、長時間タスクの推論待ち・context 蓄積・承認待ちを削減するため次を満たさなければならない。
  - モデル選択は routine implementation、lightweight investigation、deep reasoning の3段階で判断し、deep reasoning は限定された難所にだけ使用する。利用者へのモデルの提案は、利用者がモデル選択を尋ねたとき、または作業を deep reasoning と判断したときだけ行い、それ以外のタスクで提案文を出力してはならない（作業に関係しない出力が毎タスク増えるため。根拠: Claude Opus 5.5 の公式プロンプトガイド）。Agent は VS Code の model picker を自動変更できると主張せず、利用可能なモデル名を推測しない。
  - context の蓄積はモデルの context window と harness の自動 compaction に任せる。1 model request の token 数、model request 数、経過時間を理由に session を分割・停止してはならない。workspace の `chat.agent.maxRequests` は長時間の自律実行を途中で止めない値（200 以上）に設定する。2026-09-26 改訂: 100,000 tokens 目標・30 request 上限・新しい session への引継ぎ義務を削除した（利用者依頼。Claude Opus 5 系は 1M context 全域で一貫し、Opus 5.5 は長時間の自律作業を公式に想定している）。
  - 多ファイルのread-only調査は `Explore`、長いone-shot commandは実行専用subagentへ委譲し、親sessionへは要約だけを返す。中間推論を親へ残す必要がない重いSkillは `context: fork` とし、forkを使用可能にするworkspace設定を有効化する。密結合な実装を速度だけのために分割してはならない。
  - terminal auto-approvalはread-only commandの明示allowlistに限定し、built-in deny ruleを維持する。file write、Git状態変更、外部サービス・cloud・deployment command、および任意コードを実行するtest commandは自動承認してはならない。auto-approvalはsecurity boundaryとして扱わず、workspace外write検出を維持する。

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

本節は、QA 質問票の各質問が利用者の意思決定に足る説明を伴うことを規定する。対象は [hve/prompts.py](hve/prompts.py) の質問票生成プロンプト（`PRE_EXECUTION_QA_PROMPT_V2` / `QA_PROMPT_V2`）と、その出力を保持・提示するパイプラインとする。質問の件数・重要度分類・既定値候補の採用ロジックは、FR-QA-09（人へ尋ねる不明点の絞り込み）と FR-QA-10（既定値の較正）を除き、本節の対象外とする。

- **FR-QA-01**: 質問票生成プロンプトは、各質問に「背景と根拠」と「判断の観点」を必須項目として出力させなければならない。「背景と根拠」は、判断材料として確認した対象（出典）、そこから確定した事項と確定していない事項、および当該未確定が質問に値する理由を含めなければならない。確認していない場合は「未確認」と記載させ、出典を推測で記載させてはならない。「判断の観点」は、回答によって結論が変わる評価軸を 2 つ以上挙げ、主要な選択肢が各軸で有利・不利のいずれとなるかを示さなければならない。「既定値候補の理由」は、当該選択を支持する根拠となる事実、優先した評価軸、および他の選択肢を既定値としなかった理由を含めなければならない。各項目の値は 1 行で記述させ、結論のみの記述を許してはならない。本要件は事前 QA（メインタスク実行前）と事後 QA（成果物に対する QA）の双方へ同一の項目定義で適用する。
- **FR-QA-02**: QA 質問票のパイプラインは FR-QA-01 の 2 項目を欠落させてはならない。[hve/qa_merger.py](hve/qa_merger.py) は当該 2 項目を構造化質問票（`[Qxx]` 形式）およびマージ済みテーブル形式の双方で解析し、`render_merged` の出力へ列として保持しなければならない。当該 2 項目を持たない既存の質問票ファイルは空値として扱い、解析を失敗させてはならない。CLI は [hve/console.py](hve/console.py) の質問票表示で当該 2 項目を提示しなければならない。ただし既存の質問票テーブルへ列として追加してはならず、テーブルとは別の形式で提示する（列追加は既存列の可読幅を損なうため）。GUI の QA 回答ダイアログ（[hve/gui/qa_answer_dialog.py](hve/gui/qa_answer_dialog.py)）は当該 2 項目を回答入力前に参照できるよう表示しなければならない。質問票フォーマットを規定する Skill（[.github/skills/task-questionnaire/SKILL.md](.github/skills/task-questionnaire/SKILL.md) および `references/` 配下のテンプレート）は、プロンプトと同一の項目定義を保持しなければならない。経路によって項目定義が異なってはならない。
- **FR-QA-03**: `auto_qa` が有効な Knowledge Management (`akm`) 以外の Workflow は、質問が 1 件以上ある事前 QA について、ユーザー回答または明示された既定値を全質問へ適用した回答済み Markdown を `qa/` 配下へ保存し、最終パスを再読込して内容・質問数・各質問の非空回答を検証した後でなければメインタスクを開始してはならない。回答済み Markdown の表セルは、Work IQ 応答を含め、CR / LF / pipe を含む入力でも 1 質問 1 物理行を維持し、render → 保存 → 再解析の往復で質問数と全回答を失ってはならない。Work IQ 回答案へ統合できるのは、SDK の `tool.execution_start` イベントから Work IQ 用として許可された MCP server/tool の組を確認でき、かつ応答 status が `FOUND` または `PARTIAL` の結果だけとする。tool 名だけの一致を実行確認としてはならない。許可する tool 名は `@microsoft/workiq` が公開する参照系ツールに限り、書き込み系ツール（entity の作成・更新・削除、`do_action`）および EULA 承認・デバッグリンク取得の実行を統合根拠としてはならない。MCP サーバーへ公開する tool の allowlist（最小権限）と、実行確認に用いる tool 名の集合は別の集合として保持しなければならない。前者を後者に合わせて広げると `_hve_workiq` の公開権限が不必要に緩み、後者を前者に合わせて狭めると、自動探索で併存する Work IQ サーバー経由の実行を検出できなくなるためである。事前 QA サブセッションは FR-CLI-76（v2.41）で自動探索を停止したため併存しないが、`workiq-doctor` の tool probe（`probe_workiq_copilot_tool_invocation`）は利用者環境の実態を観測する診断であり自動探索を残したまま実行確認を行うため、実行確認の集合は引き続き別集合として保持しなければならない。ここでいう Work IQ サーバーには、公式 `workiq` サーバーに加え、同一の Work IQ サービスを別サーバー名で登録するプラグイン（`workiq-preview` 等）を含めなければならない。Work IQ とみなす MCP サーバー名は単一の正本として保持し、実行確認とメインセッションからの分離とで別々に定義してはならない（FR-MAINT-07）。`FOUND` / `PARTIAL` は一次情報が少なくとも一部見つかった結果であるため統合対象とする。`NOT_FOUND` は既定回答を変更する一次情報が見つからず、`UNAVAILABLE` / status 不明 / tool 実行未確認は検索または出典を検証できないため、いずれも検証済み回答へ統合せず、調査用 draft にだけ未確認として保持する。質問が 0 件の場合は同期対象なしとしてメインタスクを継続する。FR-QA-05 の `qa_akm_background_merge` が有効な場合に限り、検証済み QA ファイル 1 件ごとに `sources=qa`、`target_files=<当該ファイル>`（登録単位の値。実行時の値は後述のバッチ規則が定める）、`force_refresh=false`、`auto_qa=false` の AKM 差分更新を別のバックグラウンド実行として登録し、登録キューが当該要求を受理した時点で **QA を生成した source Workflow の親 DAG** は AKM 完了を待たず次 Step へ進めなければならない。登録は検証済み QA ファイル 1 件ごとに行うが、実行開始時点でキューに滞留している複数の登録は 1 回の AKM 子実行へまとめてよい。まとめた場合は `target_files` へ当該バッチの全ファイルを与え、実行結果は登録件数分（ファイル単位）で報告しなければならない。CLI / GUI のバックグラウンド AKM と明示実行 AKM は同一リポジトリ内で直列化し、同時に 2 つ以上の AKM 子プロセスを起動してはならない。AKM の出力空間は `target_files` の指定によらず `knowledge/D01`〜`D21` の全体と `knowledge/business-requirement-document-status.md` を含むため、子プロセスを多重起動すると同一ファイルへの同時書込みと差分喪失が生じる。AKM 子実行の fan-out 並列度は FR-DAG-03 の解決順序に従い AKM の宣言値となる。子プロセスの argv で並列度を固定してはならない（FR-MAINT-07: 同一ルールを二重に実装しない）。当該 fan-out 子は各自の `knowledge/D{NN}-*.md` だけを書く契約（[.github/prompts/fanout/akm/_common.prompt.md](.github/prompts/fanout/akm/_common.prompt.md)）であるため、宣言値までの並列化は上記の直列化要件と両立する。親 Workflow の Git 後処理・branch 切替・GUI cleanup より前に未完了の書込みを安全に終了または取消できなければならない。branch / PR を作る親実行では、AKM が出典として使用した検証済み QA ファイルだけを knowledge 変更とともに commit 対象へ含める。ADI も本要件の対象とし、Step 1.1 / 1.2 が生成する原本質問票 main 成果物は事前 QA の回答済み補助ファイルとは別成果物として扱う。`workflow_id=akm` の実行は QA 起点 AKM 登録を行ってはならず、AKM Root Issue から別の QA 起点 AKM を再帰生成してはならない。ファイル単位の起動とリポジトリ単位の直列化は、複数 Step が回答を保存した場合にも各回答を早期反映しつつ、共有する `knowledge/` への同時書込みと差分喪失を防ぐために必要な最小境界である。SDK Fleet mode へ委譲した wave（実行可能 Step が 2 件以上ある wave。[hve/orchestrator.py](hve/orchestrator.py) `_fleet_wave_runner`）は本要件の事前 QA と QA 起点 AKM の対象外とする。Fleet 経路は `StepRunner.run_step` を経由せず、事前 QA（Phase 0）と敵対的レビュー（Phase 3）は `run_step` の内部にあるためである。ただし実行面は、`auto_qa` または `auto_contents_review` が有効なまま Fleet wave を開始する場合、当該 wave では両フェーズが実行されないことを、Fleet の起動成功が確認できた時点で 1 回だけ警告として通知しなければならない。利用者が明示的に有効化した設定が無言で失われてはならない。警告は wave ごとに 1 回とし、Step ごとに繰り返してはならない（並列 Step 数だけ同一警告が出ると信号が失われるため）。Fleet の起動に失敗して通常経路へフォールバックした場合は、当該 wave で両フェーズが実行されるため警告してはならない。警告文の生成は単一のヘルパーに限定する（FR-MAINT-07）。
  - **Work IQ SDK 委譲による上書き（v2.88）**: 本段落は本要件内の Work IQ 固有 clauses（canonical Plugin / remote 構成の複製、`_hve_workiq`、`workiq-preview`、doctor probe、公開用と実行確認用の別 tool 集合）を全面的に置き換える。Work IQ 回答案へ統合できるのは、GitHub Copilot SDK の自動探索で選ばれた exact MCP server `workiq` の exact tool `ask` を `tool.execution_start` で確認でき、応答 status が `FOUND` または `PARTIAL` の結果だけとする。HVE は Work IQ の transport、command、URL、header、OAuth client、token store を取得・複製・検証せず、Plugin / MCP の導入・有効化・構成・認証・EULA 承認も行わない。`workiq-preview` その他の alias を実行証拠として受理してはならない。`NOT_FOUND` / `UNAVAILABLE` / status 不明 / exact tool 実行未確認の扱い、QA 保存・再解析・AKM 差分同期の契約は変更しない。
  - **successful completion の証拠条件（v2.97）**: exact tool 実行確認は、canonical な非空 `tool_call_id` を持つ `tool.execution_start` だけでは成立しない。同じ query 区間で同じ ID を持つ `tool.execution_complete` を確認し、その `success` が厳密に `True` の場合にだけ成立する。開始 identity は MCP 専用の `mcp_server_name` / `mcp_tool_name` から取得し、legacy `tool_name` で欠落を補完してはならない。完了欠落、空・非文字列・前後空白付き ID、異なる ID の完了、pending ID 衝突、`success=False`、または真偽値以外の `success` は実行未確認として fail closed する。同じ query 区間で衝突した ID は完了受信後も当該区間の終了まで曖昧なまま拒否し、次の query checkpoint で相関状態を破棄した後だけ再利用を許可する。MCP 通信ログの有効化状態・書込み成否をこの判定条件にしてはならない。
  - **事前 QA の責務分離（既存契約の明確化）**: 質問票生成は Step の required Skills と通常の resource route を維持する。Work IQ 問い合わせは質問・対象件数・必要な Step 入力同意が成立した後だけ別 session で行い、利用不可・runtime 検証失敗では Work IQ だけを警告付きでスキップして回答済み QA とメイン処理を維持する。query checkpoint、exact 成功完了、content schema の統合条件は緩和しない。
  - **知識探索による上書き（v3.38）**: 本要件の Work IQ 固有 clauses（Work IQ 回答案への統合条件、exact `workiq` / `ask` の `tool.execution_start` 確認、`FOUND` / `PARTIAL` の扱い、調査用 draft、上記 v2.88 / v2.97 の段落、事前 QA の責務分離のうち Work IQ 問い合わせの部分）は FR-KD-04 / FR-KD-06 で置き換える。回答済み QA の保存・最終パスの再読込検証・1 質問 1 物理行・質問 0 件時の継続・QA 起点 AKM の登録と直列化の契約は変更しない。回答済み Markdown の保存は FR-KD-05 のロックと原子的置換を使う。
- **FR-QA-04**: FR-QA-03 の QA 起点 AKM に対して、利用者は AKM 子実行が使うモデル・reasoning effort・context tier を、メインタスクの実行品質設定とは独立に選択できなければならない。設定キーは `akm_model` / `akm_reasoning_effort` / `akm_context_tier` とし、CLI は `--akm-model` / `--akm-reasoning-effort` / `--akm-context-tier` で受け取る。いずれも未指定を既定とし、未指定のキーは対応するメイン設定（`model` / `reasoning_effort` / `context_tier`）を継承しなければならない。`reasoning_effort` / `context_tier` には既存の環境変数経路が存在しないため（[hve/config.py](hve/config.py) `SDKConfig.from_env`）、本設定にも環境変数経路を新設してはならない。継承の解決は QA 起点 AKM 子プロセスの引数生成（[hve/qa_akm_dispatch.py](hve/qa_akm_dispatch.py) `QaAkmCoordinator._build_argv`）だけで行い、メインタスク・敵対的レビュー・QA 質問票生成のセッション生成へ本設定を適用してはならない。`--workflow akm` を明示指定した実行は本設定の適用対象外とし、従来どおり `--model` / `--reasoning-effort` / `--context-tier` に従わなければならない。CLI 対話 wizard は `auto_qa` を有効化した非 AKM Workflow のときにだけ本 3 項目を尋ね、既定は継承としなければならない。モデル値は既存のモデル正規化（[hve/config.py](hve/config.py) `_normalize_model_with_warning`）と同一の規則で検証しなければならない。本設定は AKM が扱う `knowledge/` の更新粒度と、メインタスクの実行品質・コストを独立に決められるようにするために必要であり、既定の継承によって既存実行の挙動を変えてはならない。
- **FR-QA-05**: FR-QA-03 の QA 起点 AKM をバックグラウンドで起動するかどうかは、利用者が明示的に選択できる設定 `qa_akm_background_merge` で制御しなければならない。既定は無効とし、無効のときは QA 起点 AKM を登録・dispatch してはならない。CLI は `--qa-akm-background-merge` で受け取り、CLI 対話 wizard は `auto_qa` を有効化した非 AKM Workflow のときにだけ本設定を尋ね、既定は無効としなければならない。GUI は設定画面と Step 1 右ペインの双方で選択でき（FR-GUI-20）、Cloud は Issue Form の入力で選択できなければならない（FR-CLOUD-26）。本設定が無効のとき、CLI 対話 wizard は FR-QA-04 の 3 項目を尋ねてはならず、GUI は当該 3 項目を非活性とし値を CLI へ渡してはならない（AKM 子実行自体が起きないため）。判定の実装は実行面ごとに 1 箇所へ限定し、CLI / GUI は [hve/orchestrator.py](hve/orchestrator.py) `_should_enable_qa_akm_dispatch`、Cloud は [.github/workflows/auto-issue-qa-ready-transition.yml](.github/workflows/auto-issue-qa-ready-transition.yml) の `save-qa-answer` job が出力する `sync_required` だけが判定してよい。同一面に判定を重複実装してはならない。FR-QA-04 と同様に環境変数経路を新設してはならない。`--workflow akm` を明示指定した実行は従来どおり本設定の対象外とする。本設定は、QA 回答のたびに `knowledge/` が更新されコスト・実行時間・差分レビュー量が増えることを利用者が制御できるようにするために必要であり、既定を無効とするのは、利用者が明示的に選択していない共有資産（`knowledge/`）への自動書込みを行わないためである。
- ~~**FR-QA-06**: Work IQ 応答が `FOUND` / `PARTIAL` なのに exact `workiq` / `ask` の実行を確認できない場合に警告する。~~ → **廃止（v3.38）**: 質問単位の Work IQ 問い合わせを FR-KD-10 で廃止した。出典を確認できない回答は FR-KD-04 で tool の失敗としてモデルへ返し、ファイルへ書かない。
- **FR-QA-07**: FR-QA-03 の QA 起点 AKM 子実行の標準出力・標準エラーは、当該子実行の run ディレクトリ（`work/run/qa-akm-<id>/`）配下の単一ファイルへ保存しなければならない。破棄してはならない。保存は UTF-8 / 復元可能な decode（`errors="replace"`）で行い、子の出力に含まれる非 UTF-8 バイト列によって親実行を失敗させてはならない。実行結果には当該保存先のリポジトリルート相対パスを含め、親実行は失敗時に `returncode` と当該パスを報告しなければならない。子ログの本文を親実行のログへ展開してはならない（親ログの肥大を避けるため）。バッチ実行では 1 実行につき 1 ファイルとし、当該バッチに含まれる全ファイルの結果へ同一のパスを与える。失敗報告には、FR-CLI-74 の HVE ソース未コミット変更による停止（status=blocked）が代表的な原因であることの確認導線を含めなければならない。また、QA 起点 AKM の登録時点で HVE ソースに未コミット変更を検出した場合は、子実行を起動せずに登録をスキップし、その事実を即時に警告しなければならない。スキップは実行失敗とは別の事象として報告し、`returncode` を失敗として集計してはならない。本事前判定は FR-CLI-74 の最終ガードを置き換えてはならず、登録時点で clean でも実行時点で dirty になり得ることを前提とする。判定は FR-CLI-74 と同一の実装を再利用し、対象リポジトリは coordinator が保持するルートへスコープしなければならない（FR-MAINT-07）。本要件は、子実行が失敗したときに親のログへ件数しか残らず、原因究明に手動再現を要していたことを根拠とする。
- ~~**FR-QA-08**: HVE 専用 `workiq-doctor --qa-integration-probe` により Work IQ 統合可否を診断する。~~ → **廃止（v2.88）**: Work IQ の設定・認証・診断を GitHub Copilot CLI / SDK へ一元化し、診断のためにモデル問い合わせや Work IQ query を実行する HVE 独自経路を削除する。HVE の自動検証は FR-CLI-91 の SDK discovery と、実働セッションの status / `list_tools`、exact `workiq` / `ask` のイベント確認で行う。
- **FR-QA-09**: 事前 QA と計画（Skill `task-dag-planning`）は、不明点ごとに解決梯子を安い段から順に試し、解けた段で止めなければならない。段は L0（決定的な解決: 契約スキーマの既定値、registry の宣言、既存の I/O 契約）、L1（リポジトリ内の検索: `knowledge/`、`docs/`、既存の `qa/` の回答済みの質問。候補が 1 つに絞れた場合だけ解決とし、出典のパスを必須とする）、L2（Work IQ。FR-QA-03 の統合条件を満たす結果だけを根拠にする）、L3（公開情報。製品・API の仕様の確認に限り、社内の業務判断を公開情報で決めない）、L4（人）とする。人へ尋ねる（L4）のは次の 3 条件をすべて満たす不明点だけとする: (1) L0〜L3 の後も候補が 2 件以上残る、(2) 影響が受入条件・不可逆な操作・費用・セキュリティのいずれかに及ぶ、(3) 後で安く戻せる既定値が無い。それ以外は既定値を `assumed` として採用し、採用した値と出典を記録して進む。L4 の質問は計画承認と同じ 1 往復にまとめ、FR-QA-01 の形式で既定値を付ける。規則の正本は Skill `task-questionnaire`（[.github/skills/task-questionnaire/SKILL.md](.github/skills/task-questionnaire/SKILL.md)）とする。事前 QA の Prompt（[.github/prompts/runtime/qa/pre-execution.prompt.md](.github/prompts/runtime/qa/pre-execution.prompt.md)）は質問の生成より前に L1 の検索を指示し、L1 で解決した不明点を質問票に載せてはならない。L2 以降の段の実行経路（Work IQ の問い合わせ、FR-QA-03）は変更しない。（v3.38 改訂）L2 は FR-KD の知識源（Work IQ を含む任意の MCP server）とし、回答へ採用できる条件は FR-KD-04 / FR-KD-06 とする。
- **FR-QA-10**: 回答済みの事前 QA を保存・検証した後（FR-QA-03）、HVE は利用者が明示的に回答した質問ごとに 1 行の JSON（`category`（分類項目）、`priority`（重要度）、`default`（既定値候補）、`final`（最終の回答）、`matched`（両者の一致））を較正ログ `work/learning/qa-calibration.jsonl` へ追記しなければならない。利用者が回答せず既定値を自動で適用した質問は、的中の根拠にならないため記録してはならない。Work IQ の応答本文と秘密値を書いてはならない。ログの使い方は Skill `task-questionnaire` の規則とし、HVE のコードは記録だけを行う: 同じ `category` の直近 20 件で不一致が 0 件なら、次回から L4 へ上げずに `assumed` とし、不一致が 1 件でも見つかったら L4 に戻す。`security`（セキュリティ）と `irreversible`（不可逆な操作）に影響する不明点（Skill の不明点台帳の `impact` で判定する）は的中率によらず自動化しない。自動化した種類の不一致は受入・品質ゲートの失敗や後の修正でしか見つからず、検出の漏れがあり得ることを Skill に明記する。`work/learning/` は実行をまたいで使うため `work/run/<run-id>/` の外に置く（artifacts 配置の例外。`work/learning/README.md` に明記する）。
- **FR-QA-11**: 質問票を作る Prompt（[.github/prompts/runtime/qa/pre-execution.prompt.md](.github/prompts/runtime/qa/pre-execution.prompt.md)、[.github/prompts/cloud/copilot-auto-feedback-auto-qa.prompt.md](.github/prompts/cloud/copilot-auto-feedback-auto-qa.prompt.md)）は、`qa/` 配下の質問票ファイルを正本とし、Issue / PR のコメントにはそのファイルへのリンクと質問数・未回答数の要約だけを投稿させなければならない。質問票の全文をコメントへ二重に書かせてはならない（同じ内容の二重記述は食い違いの原因になり、PR では `post-qa-to-pr-comment.yml` が必要に応じて全文を投稿するため）。FR-QA-01〜03 の質問票の項目と回答の保存は変えない。出典: 利用者依頼（2026-09-30）で指定された `work/202609301045-DAGReviewPlan.md` N4-4（HVE Orchestrator review report D11）。
- ~~**FR-WIQ-01**: 既定の QA / KM query の Work IQ 応答に `## 取得内容` / `## 情報源` の構造契約を課す。~~ → **廃止（v3.38）**: Work IQ 専用の固定 Prompt と応答書式の検証を FR-KD-10 で廃止した。出典は FR-KD-04 で検証する。
- ~~**FR-WIQ-02**: exact SDK event・`FOUND` / `PARTIAL`・FR-WIQ-01 構造の 3 条件を満たす Work IQ 応答だけを trusted とする。~~ → **廃止（v3.38）**: FR-KD-04 の出典検証と FR-KD-05 の書込み制御へ置き換えた。

### 3.13 MCP 通信ログ

本節は、Copilot SDK セッションを介した MCP サーバーとの入出力を、利用者が後から全文で読み返せる形でファイルへ保存する契約を規定する。目的は (a) MCP 経由で何を送り何を受け取ったかを実行後に検証できるようにすること、(b) HVE が Work IQ へ送るプロンプトを利用者が Microsoft 365 Copilot Chat で再利用できるようにすることの 2 点である。本節は §3.11 の実行時 Observability（`observability/events-<pid>.jsonl`）とは別チャネルであり、FR-RTO-01〜07 を改訂しない。

- **FR-MCPLOG-01**: HVE は、Copilot SDK セッションで観測した MCP の入出力を run スコープのログファイルへ全文で追記しなければならない。記録対象は (1) `tool.execution_start` のうち MCP サーバー名を持つもの（MCP サーバー名・MCP ツール名・`tool_call_id`・`arguments`）、(2) 対応する `tool.execution_complete`（成否・結果本文・エラー）、(3) `session.mcp_servers_loaded` / `session.mcp_server_status_changed` のサーバー状態、(4) HVE が Work IQ 専用セッションへ送る自然言語プロンプトと、その応答本文とする。(2) は SDK の `ToolExecutionCompleteData` が MCP サーバー名を持たないため、(1) が記録した canonical `tool_call_id` との相関でのみサーバーを特定しなければならず、相関できない完了イベントを記録してはならない（MCP 由来か組み込みツール由来かを判別できないため）。同じ scope で未完了の MCP start と組み込み tool start が同じ ID を使った場合は帰属が曖昧なため、当該 ID の完了を MCP response として記録してはならない。衝突検出のため組み込み tool start も相関器へ通知するが、その request / response 本文を MCP ログへ書き込んではならない。真偽値以外の `success` を成功として記録してはならない。人間向け表示のための切り詰めを本ログへ適用してはならない。MCP サーバープロセスは Copilot CLI ランタイムが起動し HVE はその標準入出力を保持しないため、記録範囲は SDK イベントが公開する上記に限られる。生の JSON-RPC フレームを取得する目的で MCP サーバーの起動コマンドを書き換えてはならない。（v3.38）(4) の Work IQ 専用セッションは FR-KD-10 で廃止したため、(4) に該当する記録は発生しない。知識探索セッション（FR-KD-03）の MCP 入出力は (1)〜(3) として記録する。
- **FR-MCPLOG-02**: 出力先は `resolve_work_root()` 配下とし、MCP サーバー 1 件につき 1 ファイル `mcp-<サーバー名>.log` とする。親プロセスから起動され作業ディレクトリを共有する子プロセスでは `mcp-<サーバー名>-<pid>.log` とし、複数プロセスが同一ファイルへ追記してはならない（1 レコードが複数行にわたるため、追記の交錯がレコードを破壊するため）。子プロセスの判定条件は `HVE_GUI_SESSION_ID` が非空であるか、`HVE_STATS_STREAM` が既存の真値集合（`1` / `true` / `True`）に一致することとし、[hve/console.py](hve/console.py) が `[hve:stats]` の子プロセス配信可否に用いている条件と同一でなければならない（FR-MAINT-07）。GUI Autopilot の APP 別子プロセス（[hve/gui/autopilot/child_launcher.py](hve/gui/autopilot/child_launcher.py)）は `HVE_STATS_STREAM` を付与されず `HVE_GUI_SESSION_ID` だけを継承する一方、CLI Autopilot の子プロセス（[hve/autopilot/cli_runner.py](hve/autopilot/cli_runner.py)）は `HVE_STATS_STREAM=1` を付与されるため、いずれか一方だけを条件にすると他方で追記が交錯する。サーバー名はファイルシステム安全な文字へ正規化してよいが、SDK が報告した名前以外の別名へ写像してはならない。`HVE_WORK_ROOT` 未設定時および dry-run では書き込んではならない。形式は UTF-8 / LF / BOM なしとし、各レコードは時刻・種別・サーバー名を含む 1 行のヘッダで始めなければならない。1 ファイルが 32 MiB に達した場合は追記を停止し、その事実を 1 回だけ警告する（ローテーションは行わない）。書き込み失敗によって Step を失敗させてはならない。本機能のために新規の CLI オプション・設定項目・環境変数を追加してはならない。
- **FR-MCPLOG-03**: 本ログは prompt 本文・tool の引数・応答本文を意図的に保持するため、FR-RTO-04 の allowlist は適用しない。ただし NFR-SEC-01 が対象とする認証情報は、Work IQ に依存しない既存の単一マスク実装（[hve/security.py](hve/security.py) `sanitize_diagnostic_text`）を再利用して記録前に伏せなければならず、同等の処理を新規に実装してはならない（FR-MAINT-07）。当該実装は完全なサニタイズを保証しないため、本ログが業務データを平文で含むことと、`.gitignore` の `*.log` によりリポジトリへコミットされないことを、利用者向けドキュメントへ明記しなければならない。人間向け表示の抑止設定（`quiet` / `final_only` / verbosity）によって記録を止めてはならない（FR-RTO-02 と同じ「収集・保存」と「表示」の分離方針）。

### 3.14 Prompt source centralization

本節は、HVE がモデルへ渡す固定 prompt 本文の正本を `.github/prompts/` 配下へ集約し、読み込み経路と許可範囲を固定する契約を規定する。目的は (a) prompt 本文の重複定義を防ぐこと、(b) 実行経路ごとに異なる prompt 本文が混在する状態を防ぐこと、(c) prompt 読み込み時のパス逸脱や欠損を model call 前に fail-closed で検出すること、(d) HVE が使用する固定 prompt 本文を同じ文字列で手動デバッグできることの 4 点である。

- **FR-PROMPT-SRC-01**: HVE が管理する固定 model-facing prompt 本文の正本は `.github/prompts/**` 配下の UTF-8 Markdown ファイルだけとし、Python / Workflow / shell / PowerShell は prompt の選択、安全な読込、動的値補間、および補間済み payload の送信だけを担わなければならない。正本は既存の flat Agent prompt に加え、active Step body、fan-out addendum、runtime fragment、Cloud 実行指示、developer / evaluation harness の固定 prompt を含む。Step body は `steps/`、fan-out addendum は `fanout/`、Cloud 実行指示は `cloud/`、developer / evaluation harness を含むその他の HVE 内部固定 prompt は用途別に `runtime/` 配下へ分類しなければならない。Python 定数、Workflow 定義、manifest、環境変数、CLI 引数、評価 harness のコード、Cloud Agent assignment を構築する Workflow 本文へ固定 prompt 本文を重複保持してはならない。ただし実行時にファイルから読み込んで動的値を補間した payload を model / SDK / Copilot assignment へ送信することは重複保持に含めない。利用者入力、動的データ、UI 表示文言、ログ／エラーメッセージ、テスト fixture、生成アプリが所有する生成物としての Markdown／コード、および HVE 管理外の third-party SDK / MCP / model prompt は対象に含めない。
  - legacy runtime split-fork の撤去（v3.21）に伴い、production caller を失った `runtime/fleet/subtask.prompt.md`・`runtime/fleet/split-fleet.prompt.md`・`runtime/fleet/split-fleet-todo.prompt.md` を保持してはならない。DAG Wave の fleet 実行が使う `runtime/fleet/dag-wave.prompt.md`・`runtime/fleet/dag-wave-task.prompt.md` は維持する。
  - ~~Work IQ の runtime prompt 正本は実働する QA / Knowledge Management / AKM ingest / AKM verification / ARD use-case 経路に限定する。~~ → **廃止（v3.38）**: `.github/prompts/runtime/workiq/` は FR-KD-10 で削除した。知識探索の runtime prompt 正本は `.github/prompts/runtime/knowledge-discovery/` の 4 件（FR-KD-03）とする。
  - flat Agent prompt の計画の案内は、「計画を書く場合は Skill `task-dag-planning` に従う」の 1 文で Skill へ委譲し、計画の規約や `plan.md` の形式を各 Prompt 本文へ複写してはならない（v3.22、FR-PLAN-01）。固定 TDD レポート schema、意図的重複、flat plain Markdown としての読込契約は保持し、runtime include / resolver / 共通 prompt ファイルを新設してはならない。
- **FR-PROMPT-SRC-02**: Prompt 読み込みの単一実装は [hve/prompt_loader.py](hve/prompt_loader.py) とし、repo root の `.github/prompts/` を基準として同 directory 配下だけを許可する安全な repository-relative path を解決対象としなければならない。絶対パス、`..` を含む相対パス、`.github/prompts/` 外への escape、symlink / junction を経由した逸脱を許してはならない。必須 prompt が欠損、空文字、無効な UTF-8、または安全でないパス解決結果となった場合は、model call、SDK session 作成、Copilot assignment の前に fail-closed で停止しなければならない。必須 prompt への inline fallback、別経路からの自動生成、二重定義、manifest / flag / 環境変数 / CLI option / 外部依存による迂回、および hot reload は許可してはならず、本機能のために新規 manifest / flag / 環境変数 / CLI option / 外部依存を追加してはならない。編集内容は次回 process / session から反映する。ただし公開 API `load_prompt(agent_name)` は flat Agent prompt を読む互換 facade として呼び出し互換性を維持しなければならない。
- **FR-PROMPT-SRC-03**: HVE は、固定 prompt 本文を GitHub Copilot、Microsoft 365 Copilot Chat、または Work IQ を利用できるセッションへ手動入力して、当該 prompt に該当する入力ファイル・MCP・検索結果の参照、Tool 実行、出典、および出力契約を Autopilot 実行とは独立に確認できる非規範リファレンスを [users-guide/prompt-reference/](users-guide/prompt-reference/) に提供しなければならない。`catalog.md` は `.github/prompts/**/*.prompt.md` の全正本について結線済み・module load のみ・未結線を区別し、結線済みまたは module load 対象の本文だけを `copies/**` へ生成する。production 結線前に固定本文を確認する必要がある明示的な移行例外はコピーしてよいが、状態は未結線のまま表示し、production 送信中と表示してはならない。各コピーの本文は [hve/prompt_loader.py](hve/prompt_loader.py) `load_prompt_file()` が返す UTF-8 text と一致しなければならず、working tree の CRLF / LF 差を runtime 文字列の不一致として扱ってはならない。Work IQ の QA / KM 用合成済みテンプレートは、`config_override` を指定しない [hve/workiq.py](hve/workiq.py) `get_workiq_prompt_template()` の各戻り値と一致しなければならない。ルート [README.md](README.md) は固定 prompt の正本・非規範コピー・手動デバッグという位置付けを説明し、本リファレンスへ説明付きでリンクする。利用者文書は placeholder、固定コピーへ動的要素が追加される最終 payload、対象セッションごとの利用範囲、および応答本文だけでなく Tool 実行と出典を照合する手順を説明し、固定コピーだけで最終 payload 全体を再現したと扱わず、Microsoft 365 の実データ・個人情報・秘密情報を検証記録へ保存しないよう警告する。本要件は HVE runtime の Autopilot 判定、CLI / GUI / API / 設定、prompt の自動送信、外部応答の自動評価または保存を追加・変更しない。（v3.38）Work IQ の QA / KM 用合成済みテンプレートは FR-KD-10 で削除したため、合成リファレンスの対象から外す。

### 3.15 Step 入力 bundle

本節は、既存の Workflow / Step / 入出力契約を変更せず、途中工程から実行する利用者が任意の文書を実行 Step の追加資料または代替資料として渡す共通契約を規定する。

- **FR-INPUT-01**: 対象は [hve/workflow_registry.py](hve/workflow_registry.py) に登録された 13 local Workflow の全 non-container Step とする。container Step は実行主体ではないため独自入力を持たず、子 Step の入力を集約表示することで全 Step を画面上で確認可能にする。Cloud は FR-CLOUD-20 の現行 12 Workflow だけを対象とし、`adi` を Cloud 対応へ昇格させない。Step ごとの入力表示は `.github/io-contracts/<Agent>--<workflow>--<step>.yaml` の `inputs[].required` / `kind` / `path` を正本とし、実行時必須入力は `StepDef.required_input_paths` を正本とする。利用者が代替できるのは Markdown または既存 [hve/gui/doc_convert.py](hve/gui/doc_convert.py) が Markdown 化できる文書入力に限る。`static` / `runtime_param`、directory、JSON、script、native pipeline input、system instruction、および Skill は代替対象にしない。各 non-container Step は、文書入力の有無にかかわらず追加資料を 0 件以上受け取れる。`StepDef` または io-contract に新しい field を追加してはならない。
- **FR-INPUT-02**: run-scoped な入力は `workflow_id` / `step_id` / 順序付き `entries` を持つ bundle とする。各 entry は `role`（`additional` / `substitute`）、`canonical`（`substitute` では必須）、materialize 後の repository-relative `actual`、および `actual` bytes の SHA-256 を持つ。複数選択の順序と全件を維持し、暗黙の 1 件選択、LLM による自動要約・統合、canonical path の生成・上書きを行わない。source は変更せず、非 Markdown 文書は既存 `doc_convert.convert_file()` が委譲する Microsoft MarkItDown のローカル変換経路で Markdown 化し、既存 work root 配下へ run-scoped に保存する。新しい変換依存を追加しない。
- **FR-INPUT-03**: `docs-original/` の候補は既存 `mdq` を `docs-original/**` に限定して検索し、ファイル名の一致を優先して最大 10 件を決定的な順序で提示する。同順位は repository-relative POSIX path の辞書順とする。mdq 索引が無い・stale・検索失敗の場合は、その事実を示して実在ファイルの同じ path 順へ縮退する。候補または検索語が 0 件でも正常結果とし、候補を捏造・自動選択しない。利用者は候補外のファイルも明示指定できる。local 面では OS-local path を materializer まで受け取ってよく、Cloud 面では対象 branch の repository-relative path または Issue Form で upload されたファイルだけを受け取る。
- **FR-INPUT-04**: GUI の Step 1 右ペインは、選択中の Workflow / Step ごとに文書入力の required / optional、canonical path、kind、存在状態、実在ファイル名を表示する。既存 canonical がある場合は追加だけ、欠損した文書入力では追加または代替を選択でき、いずれも複数ファイルと変換結果を表示する。CLI（wizard / non-interactive）/ Prompt controller / Cloud は同じ候補を提示し、複数選択または明示指定を受け取る。選択値を永続設定へ追加しない。Cloud は現行 12 Issue Form の upload / textarea と共通 helper を使用し、対象 branch へ Markdown 化した資料と manifest を保存してから、その manifest path を既存 Step body へ渡す。Issue Form upload が利用できない場合は branch 上のファイル指定へ縮退し、対応済みと表示しない。
- **FR-INPUT-05**: custom input を 1 件以上持つ Step は、保存設定を変更せず既存の事前 QA を実効有効化する。質問が 0 件ならそのまま main task へ進む。質問が 1 件以上あり、安全な補填 adapter が ready の場合だけ、query より前に exact `MCP経由で情報を補填しますか?` を利用者へ確認し、明示同意後に問い合わせる。初期 adapter は既存の exact MCP server/tool `workiq` / `ask` に限定し、FR-WIQ-01 / 02 を満たす情報だけを回答済み QA へ統合する。取得不能・未検証・schema 不合格は未充足のまま残し、情報源や内容を推測しない。Cloud で安全な Work IQ 対話が成立しない場合は手動 QA へ戻し、Cloud 対応済みと主張しない。（v3.38）同意後の MCP 補填は FR-KD-06 の知識探索で行う。
- **FR-INPUT-06**: GUI / CLI / Prompt / Cloud は、入力契約の読込、候補解決、materialize、bundle 検証、Prompt 追加文の構築に同じ core 実装を使う。Prompt request v1 は後方互換な任意 field `workflows[].step_inputs` を受理し、省略時は従来動作を維持する。Prompt plan の SHA-256 は正規化済み bundle 全体を含み、内容・順序・role・canonical / actual 対応・digest のいずれかが変われば再 plan と再承認を要求する。既存 `input_aliases` は維持し、同じ canonical との競合を拒否する。本機能のために新しい永続設定、環境変数、外部依存、Strategy / Factory、検索エンジン、top-level Workflow、HVE Workflow / Step、または io-contract field を追加しない。ルート [README.md](README.md) と `users-guide/` は 4 面の利用方法、複数選択、変換、QA / MCP 同意、Cloud の制約を説明する。

### 3.16 計画成果物のタスク完了条件（DoD）

本節は、計画成果物（`plan.md` / `subissues.md`）が既にテンプレート上で要求している完了条件記述を、既存の validator / parser で構造として検査する契約を規定する。本節は**構造検査**のみを対象とし、記述内容の妥当性・十分性の判定は対象外とする。内容品質は既存の敵対的レビュー（要件充足性軸）と FR-WF-OUT-01 の成果物存在ゲートが扱う。実装前の受入条件 baseline の独立確認と凍結は §12 TBD-35 のとおり保留であり、本節をその代替として扱ってはならない。

- **FR-PLAN-01**: **優先度 MUST。** 計画を分割するかどうかはモデルが作業内容から判断しなければならない。`.github/skills/**`・`.github/prompts/**`・[.github/copilot-instructions.md](.github/copilot-instructions.md) に、`task_scope` / `context_size` などの作業量の指標から分割を機械的に強制する規則（`SPLIT_REQUIRED` 判定、判定を覆すことの禁止、`plan.md` 冒頭の分割メタデータと `## 分割判定` セクションの必須化）を置いてはならない。計画の規約は Skill `task-dag-planning` の 3 点（受入条件と非対象を書く、完了条件を exit code またはファイル状態で判定できる形にする、分割するなら独立して検証できる単位で分ける）とし、見積は任意とする。分割を選んだ場合の手段（Cloud の `subissues.md` → `create-subissues-from-pr.yml` による Sub-Issue 作成、`validate-subissues`）は維持し、[.github/workflows/plan-validation-and-labeling.yml](.github/workflows/plan-validation-and-labeling.yml) は `split_decision` ではなく PR に `work/**/subissues.md` が含まれるかで `create-subissues` 系のラベルを付けなければならない。v3.36 で、HVE GUI の表示文言・翻訳ソース・コメント（`hve/gui/**` の `.py` と `.ts`。`hve/gui/tests/**` を除く）も、撤去済みの `SPLIT_REQUIRED` に言及してはならないとした（修正プランの DP-6 で保留していた項目。利用者依頼 2026-10-01）。根拠: ATG 実測（`work/202609271600-ATG-BusinessImpactAnalytics.md`）で計画用 DAG の強制は完成率を上げず、時間・費用を 1.7〜3.5 倍にした。出典: 利用者依頼（2026-09-30）で指定された `work/202609301045-DAGReviewPlan.md` N2-3。
- **FR-DOD-01**: `subissues.md` の各 `<!-- subissue -->` ブロックは `## 完了条件` セクションを持ち、その配下に少なくとも 1 行の非空の記述を含まなければならない。空行、空白のみの行（NO-BREAK SPACE U+00A0 と全角空白 U+3000 を含む）、Markdown 水平線のみの行（ハイフン 3 個以上）、および `REPLACE_ME`（大文字小文字不問）を含む記述は、記述として数えない。`REPLACE_ME` の placeholder 判定は既存の `<!-- title: ... -->` の placeholder 判定（部分一致・大文字小文字不問）と同一としなければならない。検査は既存の `<!-- title: ... -->` 検査と同じ経路（[.github/scripts/bash/validate-subissues.sh](.github/scripts/bash/validate-subissues.sh)、[.github/scripts/powershell/validate-subissues.ps1](.github/scripts/powershell/validate-subissues.ps1)）で行い、bash 版と PowerShell 版は同一の判定条件としなければならない。v3.21 で CLI / GUI の runtime split-fork（旧 `hve/split_fork.py` の `subissues.md` パーサ）を撤去したため、HVE Python 側の検査経路は持たない。bash 実装は `[[:space:]]` のロケール差により NO-BREAK SPACE の扱いが .NET / Python と割れるため、空白クラスへ当該文字を明示的に加えなければならない。本要件のために新しい CLI option、環境変数、設定項目、または別の実行経路を追加してはならない。既存の `<!-- title: ... -->` 欠落時のエラーメッセージ先頭文言を変更してはならず、`## 完了条件` の検査は全ブロックの解析が成功した後にだけ行い、既存の title 空値・placeholder・`depends_on` 前方参照の診断を優先しなければならない。
- **FR-DOD-02**: `plan.md` は `## 完了条件` セクションを持ち、その配下に少なくとも 1 行の非空の記述を含まなければならない。記述として数えない行の定義は FR-DOD-01 と同一とする。[.github/scripts/bash/validate-plan.sh](.github/scripts/bash/validate-plan.sh) と [.github/scripts/powershell/validate-plan.ps1](.github/scripts/powershell/validate-plan.ps1) は本セクションの存在と非空を検査し、違反を `::error::` 形式で報告しなければならない。v3.22 で FR-PLAN-01 により、両 validator の冒頭メタデータと `## 分割判定` セクションの検査は廃止した。本セクションが `plan.md` の唯一の必須セクションである。Skill `task-dag-planning` の計画規約と、[.github/skills/_hve-plan-artifacts/](.github/skills/_hve-plan-artifacts/) が保持する `plan.md` / `subissues.md` のテンプレート正本は、本要件と FR-DOD-01 が求めるセクションを含まなければならない。Skill `agent-common-preamble` から参照するコミット前バリデーション手順（`references/agent-playbook.md`）も同じセクションを要求しなければならない。適用範囲は当該 validator が検査対象として渡されたファイルに限る。Cloud では [.github/workflows/plan-validation-and-labeling.yml](.github/workflows/plan-validation-and-labeling.yml) が Pull Request で変更された `work/**/plan.md` だけを渡すため、本要件は既存の履歴証跡を遡及的に改変する理由にしてはならない（FR-MAINT-12 の履歴保持と両立させる）。
- **FR-DOD-03**: Prompt 版の実行計画提示（[hve/prompt_execution.py](hve/prompt_execution.py) `format_plan`）は、選択済み Workflow / Step が宣言する `output_paths` を完了条件として列挙しなければならない。Step が明示選択されていない（既定の選択）場合は当該 Workflow の全 Step を対象とする。列挙の対象は `output_paths` の宣言だけとし、fan-out 展開後にはじめて確定する `output_paths_template` を含めてはならない。本表示は plan hash の入力（同ファイル `canonical_plan_json`）に含めてはならず、FR-PROMPT-04 の SHA-256 一致判定を変更してはならない。宣言が 0 件の Step についてはその事実を表示し、値を推測または補完してはならない。本要件のために request v1 へ field を追加してはならない。

### 3.17 Phase 3 敵対的レビューの評価分離

本節は CLI / GUI / Prompt 版が共有する Step 実行（[hve/runner.py](hve/runner.py) `run_step`）の Phase 3（`auto_contents_review=True` のときだけ実行する敵対的レビュー）を対象とする。Phase 3 の既定（無効）は変更しない。本節のために新しい CLI option、環境変数、設定項目を追加してはならない。

- **FR-CLI-92**: Phase 3 の評価は、`review_model` がメインモデルと一致するか否かに依らず、メイン Step セッションとは別の新しいセッションで行わなければならない。メイン Step セッションで評価してはならない。`review_model` は評価セッションのモデル選択だけを表し、セッションを分離するかどうかの条件として扱ってはならない。
- **FR-CLI-93**: Phase 3 の評価セッションへの入力は、当該 Step の ID・タイトルと、宣言された `output_paths`（FR-DOD-03 が完了条件として扱う宣言）の一覧としなければならない。`output_paths` が 1 件以上宣言された Step では、メインセッションの最終応答を切り詰めて注入してはならない。宣言が 0 件の Step に限り、従来どおりメインセッションの最終応答を切り詰めて注入する。宣言の解決は既存の `_resolve_step_output_paths` を再利用し、別の解決経路を新設してはならない（FR-MAINT-07）。
- **FR-CLI-94**: Phase 3 の評価 Prompt（[.github/prompts/runtime/review/adversarial-review.prompt.md](.github/prompts/runtime/review/adversarial-review.prompt.md)）と再レビュー Prompt（[.github/prompts/runtime/review/adversarial-recheck.prompt.md](.github/prompts/runtime/review/adversarial-recheck.prompt.md)）は、評価者へ成果物の修正を指示してはならない。指摘の反映は、メイン Step セッションで行う既存の経路（`_apply_main_artifact_improvements`、`apply_review_improvements_to_main=True` のとき）に限る。`apply_review_improvements_to_main=False` のときは成果物が変わらないため、再レビューを行わず初回の判定を確定させる。評価 Prompt は、評価者が発見した問題を軽微・範囲外と自己判断して承認へ回してはならないこと、スタブや表示だけで機能しない実装を要件充足性の Critical 候補として確認すること、および良い判定例と悪い判定例を各 1 件以上含まなければならない。v3.26 で、評価 Prompt は、見つけた問題を重大度に関係なくすべて根拠付きで報告し、合否の絞り込みは HVE が行う（6 軸と Critical 件数による PASS / FAIL は維持する）ことを含めなければならない。
- **FR-CLI-95**: 再レビューでは、前回指摘した未修正の Critical が残る場合、作成者の反論の有無に依らず FAIL を維持しなければならない。新しい根拠を示さずに前回の指摘の重大度を下げて PASS としてはならない。合否基準（Critical = 0 なら PASS）は変更しない。

### 3.17.1 生成物の品質基準と報告形式

本項は Step 実行で使う Prompt と共通指示の文面を対象とする。Workflow・Step の構成と実行制御は変更しない。

- **FR-CLI-96**: UI を設計・生成する Prompt（[.github/prompts/Arch-UI-Detail.prompt.md](.github/prompts/Arch-UI-Detail.prompt.md) と [.github/prompts/Dev-Microservice-Azure-UICoding.prompt.md](.github/prompts/Dev-Microservice-Azure-UICoding.prompt.md)）は、業務 UI の視覚デザイン基準（一貫性・可読性・情報の階層・コントラスト）と、除外するスタイルの具体的な一覧を持たなければならない。「汎用的な見た目を避ける」のような抽象的な指示だけで済ませてはならない。
- **FR-CLI-97**: ローカル実行の完了報告テンプレート（[.github/prompts/runtime/template/completion-local.prompt.md](.github/prompts/runtime/template/completion-local.prompt.md)）は、利用者の判断待ちを報告の先頭に置く章立てを持たなければならない。Code Review Prompt（[.github/prompts/runtime/review/code-review-cli.prompt.md](.github/prompts/runtime/review/code-review-cli.prompt.md)）は、発見した問題を重大度（Blocker / Major / Minor）付きで全件、ファイル・行・理由・失敗の示し方とともに報告させなければならない。重大度で報告を絞る指示（「マージを止める問題だけを報告」等）を置いてはならない（報告の段階で絞ると見落としが増えるため）。マージを止める問題は Blocker とし（要件にない汎用化・不要な抽象化は Blocker として扱う）、合格判定は Blocker 件数だけで決める。絞り込みは別の段階で行い、合格判定行は harness の既存の判定（`_is_review_fail`）が解釈し、修正 Prompt（[.github/prompts/runtime/review/code-review-agent-fix.prompt.md](.github/prompts/runtime/review/code-review-agent-fix.prompt.md)）は Blocker だけを修正対象とする。根拠: Claude Opus 5 の公式プロンプトガイド「Code review and bug-finding」（重大度で絞る指示は報告を文字どおり減らす。全件を報告させ、絞り込みは別パスで行う）。[.github/copilot-instructions.md](.github/copilot-instructions.md) は続行規則を 2 行以内で持たなければならない（指示の肥大化を避けるため、3 行以上に増やしてはならない）。
- **FR-CLI-98**: 全 Step の先頭へ注入する言語指示（[.github/prompts/runtime/orchestrator/language-directive-ja.prompt.md](.github/prompts/runtime/orchestrator/language-directive-ja.prompt.md)）と Skill `agent-common-preamble` の言語規則は、最終出力・成果物・計画・ツール委譲の説明の言語だけを指定しなければならない。内部推論（思考過程・推論の途中経過）の言語を指定してはならない。根拠: 2026-09-24 の同一 Step 比較（`aas` Step 1、`claude-opus-5.5`、各 2 回）で、内部推論の日本語指定があっても表示された推論は英語が大半（日本語比率 0.01〜0.02）で守られず、指定を外しても成果物の日本語比率は同等（0.27〜0.29）だった（`work/run/20260923-2130-longtime-improvement/p3/artifacts/language-directive-ab.md`）。
- **FR-CLI-99**: `.github/prompts/`（Step・fan-out・cloud・runtime の各 Prompt）と、それらが参照する Skill（`adversarial-review`・`task-questionnaire`）は、オーバーエンジニアリングの禁止と捏造の禁止を、理由のない絶対表現（「オーバーエンジニアリングは絶対に禁止」「捏造は絶対に禁止」）で書いてはならない。オーバーエンジニアリングは「要求にない汎用化・抽象化は加えない」と、その理由（後続のレビューと保守の費用が増えるため）を併記して指示する。捏造は、根拠（ファイルパス・行、ツールの実行結果）を示せる内容だけを書くという肯定形と、その理由（根拠のない内容は確認と修正の手間を増やし、結果の信頼を損なうため）で指示する。HVE の定数（`OVERENGINEERING_BAN_TEXT` / `OVERENGINEERING_BAN_TEXT_QA`）と、それを含む QA・レビュー Prompt、fan-out の `_common.prompt.md`、Workflow YAML が参照する cloud Prompt は本要件の文言を持たなければならない。禁止の対象（オーバーエンジニアリングとみなす一覧、捏造の対象）と、禁止事項の優先順位は変更しない。根拠: Claude の公式プロンプトガイド（Prompting best practices「Add context to improve performance」「Tell Claude what to do instead of what not to do」）。HVE の自己テスト手順書（`tests/prompt-version/`・`tests/[cli]SystemTest - Full.txt`・`tests/[gui]SystemTest - Full.txt`）は本要件の対象外とする。
- **FR-CLI-100**: `.github/prompts/` 配下の Prompt は、見出し（コードフェンス外の `#` 行）に強調の接尾辞「（必須）」を付けてはならない。見出しでの強調は本文の規範と重複し、どの節も必須に見えて優先度の手掛かりにならないため。本文の規範的な記述（「〜しなければならない」、理由）は変更しない。コードフェンス内の見出しと、HVE・検証スクリプトが文字列で照合する出力契約の見出し（例: plan テンプレート由来の見出し）は本要件の対象外とする。Skill の見出しと見出し正規化ツール（`tools/normalize-agent-headings.py`。対象は `.github/agents/*.agent.md` で、置換先に「（必須）」を含まない）は変更しない。根拠: Claude の公式プロンプトガイド（Prompting best practices「Add context to improve performance」）。
- **FR-CLI-101**: `.github/prompts/` 配下の Prompt は、出力前に行う独立した検証ステップ（見出し「セルフチェック（出力前に必ず確認）」「最終品質レビュー（単回インライン・セルフチェック）」「最終セルフチェック・品質レビュー」等）を持ってはならない。チェック項目は成果物の受入条件として 1 か所にだけ書く。(1) 「セルフチェック（出力前に必ず確認）」の項目は同じ Prompt の「完了条件」節へ統合し、完了条件節が無い場合はその節を「完了条件」とする。(2) Prompt 固有のドメイン観点は「受入観点（完了条件の補足）」節に置き、節の冒頭に正規文「以下のドメイン固有観点は成果物の受入条件であり、出力前に行う別の検証ステップでも、敵対的レビューの発動条件でもない。」を持つ。観点を満たさない箇所は作業中に主成果物で直し、独立したレビュー成果物を作らない。観点の内容、敵対的レビューの発動規則（Skill `adversarial-review`、HVE Phase 3）、`KnowledgeManager.prompt.md` の任意レビュー契約は変更しない。v3.26 で、HVE が実行時に付与するレビュー所有権の指示文（`auto_contents_review=False` のとき、[.github/prompts/runtime/runner/review-ownership-main-task.prompt.md](.github/prompts/runtime/runner/review-ownership-main-task.prompt.md)）も本要件の対象とし、出力前の自己確認（単回インライン・セルフチェック）を指示せず、メインタスクで Review Sub-agent と敵対的レビューを起動しないことだけを伝える。根拠: Claude Opus 5 の公式プロンプトガイド「Task scope and over-verification」（明示的な検証ステップは過剰検証を招く。モデルは指示なしで自己検証する）。
- **FR-CLI-102**: **優先度 MUST。** [hve/runner.py](hve/runner.py) が全 Step の Phase 1 Prompt へ付加する共通実行指示は、(1) 1 回のツール呼び出しで書き込む内容を 300 行以内とし、大きなファイルは複数回に分けること、(2) 着手前に関係しうる入力を広く確認すること、(3) 文書は必要な内容に応じた長さとし埋め草を追加しないこと、を含まなければならない。v3.24 で、既存の `SDKConfig.step_timeout_seconds` が有効（正の値）な場合に限り「この Step の上限時間は約 N 分」（N は分へ丸めた値、最小 1）の 1 行を同じ共通指示へ加える。無効（`None`）なら何も加えない。このために新しい設定項目を追加してはならない（FR-MAINT-07）。`SDKConfig.unattended=True` の場合だけ、進捗報告・回答可能な質問・任意判断を理由にターンを終了せず、安全な既定値を選んで理由を記録して続行し、停止を資格情報不足または宣言範囲外の破壊的・不可逆・課金・外部公開操作に限定する指示を追加しなければならない。`unattended=False` ではこの停止境界を注入してはならない。共通指示は `_compose_phase1_prompt` の独立した構成要素として UTF-8 byte 予算へ算入し、個別 Agent Prompt へ複製してはならない（FR-MAINT-07）。出典: 利用者依頼（2026-09-30）および同依頼で指定された HVE Orchestrator review report §8.2 / §8.3。
- **FR-CLI-103**: **優先度 MUST。** `.github/prompts/` 配下の Prompt と、それが参照する Skill は、(a) 資格情報など利用者しか持たない情報の不足と、(b) 宣言範囲外の破壊的・不可逆・課金・外部公開の操作を除き、利用者への質問や回答待ちのための停止を指示してはならない。不明点は安全な既定値を選び、理由と影響を成果物へ記録して続ける。質問票を作る経路（FR-QA-* の事前 QA、Cloud の QA、ADI 1.1 / 1.2 の原本質問票、Skill `task-questionnaire` を利用者が明示的に求めた場合）と、Prompt 版の request 作成前ゲート（FR-PROMPT-10）は対象外とする。検査は [hve/tests/test_prompt_no_user_stop_contract.py](hve/tests/test_prompt_no_user_stop_contract.py) の検出パターンと、例外を列挙した allowlist で行い、allowlist の各理由は本要件の例外のいずれかを名指ししなければならない。出典: 利用者依頼（2026-09-30）で指定された `work/202609301045-DAGReviewPlan.md` N4-3（HVE Orchestrator review report D12 / D18 / W6 / W9 / W10）。
- **FR-CLI-104**: **優先度 MUST。** 自己改善（Self-Improve）機能は Cloud / GUI / CLI / Prompt の全版から削除する。(a) CLI の `orchestrate` は `--self-improve` / `--no-self-improve` / `--self-improve-max-iterations` / `--self-improve-target-scope` / `--self-improve-goal` を持たず、指定すると argparse の未知引数エラー（exit code 2）で終了する。(b) `SDKConfig` は `auto_self_improve` / `self_improve_*` / `apply_self_improve_to_main` を持たず、環境変数 `HVE_AUTO_SELF_IMPROVE` / `HVE_SELF_IMPROVE_SCOPE` / `HVE_APPLY_SELF_IMPROVE_TO_MAIN` を読まない。(c) `hve/self_improve.py` と専用 Prompt（`.github/prompts/runtime/self-improve/`、`QA-CodeQualityScan` / `Arch-ImprovementPlanner` / `QA-PostImproveVerify`）を持たず、`StepRunner` は Phase 4、`run_workflow` は Post-DAG 自己改善フェーズを持たない。メイン成果物改善 Prompt（`MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT`）は QA / レビュー用として `runtime/review/main-artifact-apply.prompt.md` へ移して維持する。(d) GUI は自己改善の設定ノード・入力欄・`OrchestrateArgs` フィールドを持たず、保存済み設定の `self_improve*` キーは読み込み時に廃止キーとして削除する。(e) Cloud の Issue Template と reusable workflow は自己改善の入力欄・ジョブ・ラベル（`self-improve` / `aag:self-improve-ready` / `aagd:self-improve-ready`）・Root タグを持たず、AAG / AAGD の Root は最終 Step 完了後に他 Workflow と同じく `done` へ遷移する。(f) 既存の利用者データ（`work/run/*/self-improve/` 等）は削除しない。出典: 利用者依頼（2026-10-03「`hve`の全ての版(`Cloud`/`gui`/`cli`/`prompt`)の`self-improvement`の全機能を削除してください。ドキュメントからも削除してください。」）。削除した要求: FR-CLI-60〜FR-CLI-65（ID は再利用しない）。検査は [hve/tests/test_self_improve_removed.py](hve/tests/test_self_improve_removed.py) と [hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) `TestSelfImproveRemoved`、[hve/gui/tests/test_settings_store_migration.py](hve/gui/tests/test_settings_store_migration.py) `TestSelfImproveSettingsRemoval` で行う。

### 3.18 Autonomous Task Graph（ATG）Skill とエンジン（廃止）

**廃止（v3.18）**: ATG は不要になったため、Skill `atg`（`.github/skills/atg/`）、判定エンジン（`tools/skills/atg/`）、配布キット（`tools/for-other-repo/atg/`）、実行台帳（`tools/atg-ledger/`）、Stop フック（`.github/hooks/atg.json`）、利用者ガイド（`users-guide/skills-atg.md`）と対応テストを削除した。計画の分割判定・粒度・見積・完了条件の規約は Skill `task-dag-planning`（[.github/skills/task-dag-planning/SKILL.md](.github/skills/task-dag-planning/SKILL.md)）へ戻し、HVE の起動可能判定（FR-DAG-10）は [hve/dag_readiness.py](hve/dag_readiness.py) を単一実装とした。以下は現行要件として適用しない。

- ~~**FR-ATG-01**: Skill `atg` の文書は、検証証跡が自己申告であること・分割閾値・受入ノードの分離・実行ループを明記する。~~ → **廃止（v3.18）**: ATG の削除に伴い廃止した。
- ~~**FR-ATG-02**: `node finish` は実在しない `evidence_path` を拒否する。~~ → **廃止（v3.18）**: ATG の削除に伴い廃止した。
- ~~**FR-ATG-03**: `report` は先頭に利用者の判断が必要な事項を列挙する。~~ → **廃止（v3.18）**: ATG の削除に伴い廃止した。
- ~~**FR-ATG-04**: 失敗クラス `environment`・状態 `waiting`・`node resume` を持つ。~~ → **廃止（v3.18）**: ATG の削除に伴い廃止した。
- ~~**FR-ATG-05**: ルート契約 `escalation_limits`・ノード契約 `capabilities` を受け付ける。~~ → **廃止（v3.18）**: ATG の削除に伴い廃止した。
- ~~**FR-ATG-06**: `capsule check` はエスカレーション・カプセルを決定的に検査する。~~ → **廃止（v3.18）**: ATG の削除に伴い廃止した。
- ~~**FR-ATG-07**: カプセルの手順を参照文書 `escalation-capsule.md` に持つ。~~ → **廃止（v3.18）**: ATG の削除に伴い廃止した。
- ~~**FR-ATG-08**: 要求定義を承認済みの計画として 1 セッションで完了させる自律実行モードを持つ。~~ → **廃止（v3.18）**: ATG の削除に伴い廃止した。
- ~~**FR-ATG-09**: `run begin --autonomous` と Stop フック `hook stop` を持つ。~~ → **廃止（v3.18）**: ATG の削除に伴い廃止した。

### 3.19 ID 台帳と相互参照の決定的検査

生成されるアプリの `docs/catalog` の ID（APP・画面・サービス）を 1 つの台帳で管理し、ID の相互参照をモデルの QA Step ではなくコードで決定的に検査する。調査レポート §5.5 と修正プラン N6-1 / N6-2 に基づく。

- **FR-IDL-01**: **優先度 MUST。** ID 台帳 `docs/catalog/id-ledger.md` は、列 `ID` / `種別` / `名前` / `親 ID` / `状態` / `詳細文書` / `書込みパス接頭辞` を持つ Markdown 表とする。`種別` は `APP`（`APP-NN`）/ `SCR`（`APP-NN-S###`）/ `SVC`（`SVC-*`）、`状態` は `active` / `planned` / `deprecated` とし、`書込みパス接頭辞` は `;` 区切りのリポジトリ相対パスとする。台帳の読込は [hve/catalog_parsers.py](hve/catalog_parsers.py) の `parse_id_ledger` を単一実装とし、検査は [hve/id_ledger.py](hve/id_ledger.py) の `check_id_ledger` を単一実装として、CLI [.github/scripts/check-id-ledger.py](.github/scripts/check-id-ledger.py) と CI から呼ぶ（FR-MAINT-07）。検査規則は次のとおりとする。(1) ID の重複、(2) 種別と ID 形式の不一致、(3) `親 ID` が台帳に無い（`SCR` の親は同じ接頭辞の `APP`）、(4) `active` の `詳細文書` が存在しない、(5) カタログ（`app-catalog.md` / `screen-catalog-APP-*.md` / `service-catalog.md`）の ID が台帳に無い、(6) `service-catalog-matrix.md` の画面 ID 列が `TBD` または台帳に無い画面を指す、(7) `docs/test-specs/{ID}-test-spec.md` のテスト ID が `TEST-{ID}-` で始まらない、(8) 同じ種別の `active` 行どうしで `書込みパス接頭辞` が重なる、(9) `状態` が既定値以外。台帳が無い場合は検査を行わず成功とする。CLI は既定で違反があれば非 0 で終了し、`--warn-only` のときは違反を表示して 0 で終了する。`--bootstrap` は既存のカタログと詳細文書から台帳を生成する（詳細文書が無い行は `planned`）。 CI（[.github/workflows/check-id-ledger.yml](.github/workflows/check-id-ledger.yml)）は `docs/catalog/**` / `docs/test-specs/**` を変更した PR で検査を実行する。生成済みのアプリ文書に既存の違反（テスト ID の命名）が残る間は `--warn-only` で違反を注記として表示し、既存の違反が解消した時点で非 0 終了の強制へ切り替える（TBD-39）。カタログを出力する Prompt（ARD のアプリ一覧、AAS のサービスカタログ、AAD-WEB の画面一覧）は、カタログを書き終えた後に `--bootstrap` で台帳をカタログから作り直し（並列の fan-out 子が同じ結果を得るよう、台帳を手で編集させない）、AAD-WEB のテスト仕様の Prompt はテスト ID を `TEST-{ID}-{種別}-{NNN}` とする。出典: 利用者依頼（2026-09-30「N6-1, N6-2: この計画で行ってください」）と `work/202609301045-DAGReviewPlan.md` N6-1。

- **FR-IDL-02**: **優先度 MUST。** `WorkflowDef.ownership_parallel`（既定 0 = 無効）が正の Workflow では、[hve/dag_executor.py](hve/dag_executor.py) は FR-DAG-03 の並列上限（`asdw-web` = 1）を維持したまま、**所有範囲が重ならない fan-out の子**に限り、最大 `ownership_parallel` 個を同時に実行できる。子の所有範囲は、(a) 展開後の `output_paths` と FR-WF-OUT-10 の接頭辞ゲートのうち fan-out キーを含むもの、(b) FR-IDL-01 の台帳で fan-out キーと同じ ID を持つ `active` 行の `書込みパス接頭辞`、の和とする。fan-out キーを含まない宣言のうち、末尾が `/` のディレクトリは共有の置き場所として所有範囲の判定から除き、ファイル（例: `src/app/package.json`）を 1 つでも宣言する子は共有ファイルを書くため排他実行とする。所有範囲を持たない Step（fan-out でない Step、所有範囲が空の子）は、実行中の Step が無いときだけ単独で実行する。同時に実行する子どうしは、所有範囲のどの接頭辞も互いに前方一致しないことを条件とする。排他実行を待つ Step があるときは新しい子を開始しない（待ち続けて実行されない Step を作らないため）。`asdw-web` は `ownership_parallel=4` とし、所有範囲が重ならない RED の子（3.2 サービスのテストコード、4.1 UI のテストコード）だけが並列になる。同じ worktree で実行し、Step ごとの git 操作は行わない。出典: 利用者依頼（2026-09-30「N6-1, N6-2: この計画で行ってください」）と `work/202609301045-DAGReviewPlan.md` N6-2。

### 3.20 知識探索エージェント（FR-KD）

本節は、Work IQ 専用に HVE が組み立てていた問い合わせ処理（固定 Prompt、質問ごとの 1 回問い合わせ、応答書式の検証、D クラス単位の分割、取り込みと検証の二重問い合わせ）を、目的だけを与えた 1 つの SDK セッション（知識探索エージェント）と、出典・書込み先を決定的に確かめる小さな事後検証へ置き換える契約を規定する。知識源は Work IQ に限らず、Copilot CLI に設定済みの任意の MCP server とする。`qa/` と `knowledge/` へのファイル作成・更新は、複数のジョブが同時に動いても差分を失わない単一実装（FR-KD-05）を経由する。Cloud Agent Orchestrator の経路は対象外とする（TBD-KD-01）。出典: 利用者依頼（2026-10-01「WorkIQ 専用の処理をやめて、知識探索エージェント 1 セッション＋小さな事後検証に置き換えます を実装してください。複数のジョブが同時に実行される可能性を考慮して、QA作成 /qa、QA回答 /qa の更新、/knowledge へ qa や docs-original からの作成 などのファイル作成機能は実装してください」）、`work/2026100108115_WorkIQ-RemovelResearch.md` §5〜§6、[GitHub Copilot SDK — Using MCP servers](https://github.com/github/copilot-sdk/blob/main/docs/features/mcp.md)（確認日 2026-10-01）、[microsoft/work-iq workiq-preview](https://github.com/microsoft/work-iq/tree/main/plugins/workiq-preview)（確認日 2026-10-01）。

用語: **知識源** は MCP server 名、**usable** は FR-KD-02 の判定を通過した知識源、**QA ファイル** は [hve/qa_merger.py](hve/qa_merger.py) `QAMerger.parse_qa_content` が解析できる `qa/` 配下の Markdown、**調査列** は QA 表の `調査回答` / `調査状態` / `調査出典` の 3 列、**探索モード** は `qa`（事前 QA）/ `knowledge`（AKM）/ `research`（ARD）の 3 値とする。

- **FR-KD-01**: **優先度 MUST。** 知識源の指定。
  - `SDKConfig.knowledge_sources: List[str]`（既定 `[]`）を設ける。CLI は `--knowledge-source NAME` で受け取り、複数回の指定と 1 値内のカンマ区切りを許す。環境変数は `HVE_KNOWLEDGE_SOURCES`（カンマ区切り）とする。GUI は C4 セクションの「知識源 MCP サーバー」欄（カンマ区切り文字列）を `--knowledge-source <欄の値>` として子プロセスへ渡す。
  - 知識源名は正規表現 `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$` に一致しなければならない。CLI で不一致の名前を受けた場合は argparse エラー（exit code 2、メッセージに当該名を含む）とする。環境変数の不一致トークンと空トークンは無視する。
  - `workiq_enabled`（`--workiq` / `--no-workiq` / `WORKIQ_ENABLED` / GUI「Work IQ を有効化」）は `workiq` を知識源へ加える。既定値と環境変数の解釈は FR-KD-11 に従う（v3.42 でローカル実行面の既定を有効へ変更）。
  - 実効知識源は `SDKConfig.effective_knowledge_sources()` が返す。順序は `workiq`（`workiq_enabled` のとき）、続いて `knowledge_sources` の指定順とし、完全一致の重複は最初の 1 件だけ残す。
  - AKM の `sources` に `workiq` を含む実行（FR-PARAM-01）、および ARD の `ard_workiq_enabled=true` の実行では、当該 Workflow 実行に限り `workiq` を実効知識源へ加える。保存設定は変更しない。
  - 例: `--workiq --knowledge-source confluence,workiq` → `["workiq", "confluence"]`。`HVE_KNOWLEDGE_SOURCES=" jira , ,bad name"` → `["jira"]`。`--knowledge-source "bad name"` → exit 2。
- **FR-KD-02**: **優先度 MUST。** 知識源の利用可否と読み取り専用 tool の許可リスト。
  - 探索の開始前に、FR-TS-12 の共有 resource snapshot から各実効知識源を判定する。snapshot の MCP 状態が `ready` でなければ `unverified`、名前が完全一致し `enabled=True` の MCP server が無ければ `not-configured`、[hve/toolsearch/policy.json](hve/toolsearch/policy.json) `knowledge_tool_allowlists` の当該 server の値が空または未定義なら `no-readonly-allowlist`、いずれにも当たらなければ `usable` とする。許可リストの正本は `ToolSearchPolicy.tool_allowlist_for("knowledge", server)` だけとし、別の許可リストを実装してはならない（FR-MAINT-07）。
  - `usable` でない知識源は当該実行だけ除外し、`知識源 <名前> を除外します（<理由コード>）` を 1 知識源 1 行で警告する。保存設定は変更しない。`usable` が 0 件なら探索を実行しない。
  - 既定の `workiq` 許可リストは `retrieve`、`ask`、`fetch`、`search_paths`、`get_schema`、`list_agents` の 6 件とする。`create_entity`、`update_entity`、`delete_entity`、`do_action`、`call_function`、`fetch_blob` を含めてはならない。
  - v3.42 で、既定の許可リストに `microsoft-learn`（`microsoft_docs_search`、`microsoft_docs_fetch`、`microsoft_code_sample_search` の 3 件）を加える（出典: 利用者依頼 2026-10-02 の原因 3「知識源にできるのは WorkIQ だけ」）。いずれも読み取り専用であり、FR-CLI-88 の禁止（`*` と状態変更 tool）に当たらない。`resource_classifications` は変更しない（`software-engineering` のまま）。知識源として使うには `--knowledge-source microsoft-learn` などで実効知識源へ加える必要がある（実効知識源の既定に加えない）。`workiq-preview` は既定の許可リストに加えない（FR-CLI-91 が `workiq-preview` を `workiq` の代替として扱うことを禁じ、利用者文書の契約〈`hve/tests/test_workiq_sdk_only_docs.py`〉も `workiq-preview` への言及を禁じているため。競合の記録は KD-A9）。
  - セッション作成後、まず `session.rpc.tools.initialize_and_validate()` で MCP host を初期化する（SDK は初期化前の `session.mcp.list` で host の状態を空で返すため）。続いて `session.rpc.mcp.list()` を、対象の知識源に `pending` が残る間は 0.5 秒間隔で再取得し、全体で 30 秒（`RUNTIME_INSPECT_TIMEOUT_SECONDS`）を上限とする。`connected` であり、かつ `session.rpc.mcp.list_tools(server_name=<名前>)` が返す tool と許可リストの積集合が空でない知識源だけを `usable` として残す。残りは理由コード `server-<status>`（上限に達しても `pending` のものは `server-pending`）または `no-allowlisted-tool-exposed` で除外し警告する。0 件になった場合はセッションを閉じて探索を終える。初期化または RPC が失敗・timeout した場合は `unverified` として除外する。
- **FR-KD-03**: **優先度 MUST。** 探索セッションの構成。
  - 1 回の探索につき SDK セッションを 1 つだけ作る。質問ごと・D クラスごとにセッションや問い合わせを分けてはならない。
  - セッションの options は次のとおりとする。`enable_config_discovery=True`。`disabled_mcp_servers` は snapshot で `enabled=True` の server から `usable` を除いた集合（昇順）。`available_tools` は `builtin:view`、`builtin:grep`、`builtin:glob`、`builtin:skill`、`custom:hve_read_file`、`custom:hve_qa_create`、`custom:hve_qa_answer`、探索モードが `knowledge` のときだけ `custom:hve_knowledge_write`、および `usable` の各 server について許可リストの各 tool の `mcp:<server>-<tool>`。`infinite_sessions={"enabled": True}`、`streaming=True`。モデルは探索モード `qa` で `SDKConfig.get_qa_model()`、それ以外で `SDKConfig.model` とする。reasoning effort は、探索モード `qa` では既存の事前 QA サブセッションと同じく指定せず、`knowledge` / `research` では既存の orchestrator セッションと同じ `_apply_reasoning_effort(kind="main")` で設定する。FR-TS-13 の resource routing と Cloud Session 注入を適用してはならない。`on_user_input_request` を渡してはならない（`ask_user` を公開しない）。
  - permission handler は次だけを許可し、それ以外（`write`、`shell`、`url`、未知の kind、`managed_approval_required=True`、`request_sandbox_bypass=True`）を拒否する。`read` は、パスがリポジトリ内で、`.git/`・`.hve/` 配下でなく、ファイル名が `.env` で始まらない場合。`mcp` は、`server_name` が `usable` で `tool_name` がその許可リストにある場合。`custom-tool` は、本節の `hve_*` tool の場合。ファイルの作成・更新は FR-KD-05 の custom tool だけで行わせる。
  - 指示文は [.github/prompts/runtime/knowledge-discovery/](.github/prompts/runtime/knowledge-discovery/) の `common.prompt.md` と探索モード別の `qa.prompt.md` / `knowledge.prompt.md` / `research.prompt.md` を `load_prompt_file` で読み、`{goal}`、`{sources}`、`{qa_path}`、`{run_id}` を置換して作る。FR-KD-09 の修復の指示は `repair.prompt.md` の `{missing}` を置換して作る。指示文は目的・出典の規則・停止条件だけを与え、問い合わせの回数・件数上限・応答の書式（`STATUS:` 行など）を課してはならない。
- **FR-KD-04**: **優先度 MUST。** 出典の検証。
  - HVE は探索セッションの `tool.execution_start`（`mcp_server_name` / `mcp_tool_name` / `tool_call_id`）と、同じ `tool_call_id` の `tool.execution_complete`（`success=True`、`result.content` と `result.detailed_content`）を相関し、成功した MCP 呼出しの server・tool・本文をプロセスのメモリ上だけに保持する。1 呼出しにつき先頭 1,000,000 文字まで、1 セッションにつき最初の 500 呼出しまでとし、超過分は保持しない。
  - 出典は `{id, kind, server, tool, locator, summary}` とし、次の規則で検証する。`kind="repo"` は `locator` がリポジトリ相対パスで、リポジトリ内に実在する通常ファイルであり、`.git/`・`.hve/` 配下でないこと。`kind="mcp"` は、`server` が `usable`、`tool` がその許可リストにあり、当該セッションで同じ server・tool の成功完了が 1 件以上あり、かつ前後空白を除いた `locator` が 3 文字以上で、正規化した `locator` が同じ server の成功完了本文のいずれかを正規化した文字列に含まれること。正規化は `\/` を `/` へ置換し、連続する空白を 1 つの空白へまとめ、`casefold()` する。
  - 回答の状態は `Confirmed` / `Tentative` / `Unknown` の 3 値とする。`Confirmed` は検証済みの出典を 1 件以上必要とする。`Tentative` は 0 件でもよいが、引用した出典はすべて検証済みでなければならない。`Unknown` は出典を要さないが、引用した出典は検証する。
  - 違反がある場合、tool は `result_type="failure"` を返し、本文に出典 ID と理由コード（`unknown-source-kind` / `repo-path-invalid` / `repo-path-missing` / `server-not-usable` / `tool-not-allowlisted` / `no-successful-call` / `locator-too-short` / `locator-not-found` / `confirmed-without-source` / `unknown-source-id`）を列挙し、ファイルを変更してはならない。
  - 例: `workiq` の `retrieve` の成功応答本文に `https://contoso.sharepoint.com/sites/p/Plan.docx` が含まれる場合、`{"id":"S1","kind":"mcp","server":"workiq","tool":"retrieve","locator":"https://contoso.sharepoint.com/sites/p/Plan.docx"}` は検証済みとなる。本文に無い URL は `locator-not-found`、同じセッションで `retrieve` を呼んでいなければ `no-successful-call` となる。
- **FR-KD-05**: **優先度 MUST。** 並行実行に安全なファイル操作。`qa/` と `knowledge/` への作成・更新は [hve/knowledge_files.py](hve/knowledge_files.py) を単一実装とし（FR-MAINT-07）、探索の custom tool と事前 QA の保存（FR-QA-03）はこれを経由する。
  - 対象パス。QA は `qa/` 配下（入れ子可）の `.md`。knowledge は `knowledge/D<2 桁>-<名前>.md`（`-ChangeLog.md` で終わるものを除く）と `knowledge/business-requirement-document-status.md`。`hve_read_file` は QA と knowledge の対象パスに限る。絶対パス、ドライブ指定、`..` を含むパス、パス上のいずれかの要素が symlink のもの、`.md` 以外は理由コード `path-denied` で拒否する。`\` は `/` に読み替えて判定する。
  - ロック。対象ごとに `.hve/locks/<正規化した相対パスの SHA-256 16 進の先頭 40 文字>.lock` を開き、先頭 1 byte に OS の排他ロック（Windows: `msvcrt.locking(LK_NBLCK)`、POSIX: `fcntl.flock(LOCK_EX | LOCK_NB)`）を掛ける。取得できない間は 0.05 秒から始めて毎回 2 倍（上限 0.5 秒）の間隔で再試行し、30 秒で `lock-timeout` とする。取得後、ファイルの内容を JSON `{"pid", "host", "token", "created_at"}` に置き換える（診断用）。解放はロックを外してファイルを閉じるだけとし、ロックファイルは削除しない。ロックを持つプロセスが異常終了した場合は OS がロックを解放する。同じプロセス内のスレッド間は、同じロックファイルごとの `threading.Lock` で直列化する。（v3.38 実装中の修正）当初の `O_CREAT | O_EXCL` と stale 判定（300 秒経過または pid 消滅で削除）は、stale と判定してから削除するまでの間に別プロセスが作り直した有効なロックを削除し得る（Windows ではウイルス対策ソフトによる削除の遅延でこの間隔が広がる）。8 プロセスの同時更新テストで差分の喪失を確認したため、OS のロックへ改めた。
  - 楽観的な同時実行制御。既存ファイルの更新は、ロック取得後に読んだファイルの bytes の SHA-256（小文字 16 進）が呼出し側の `base_sha256` と一致する場合だけ行い、不一致は `conflict`（現在の SHA-256 を返す）とする。新規作成は `base_sha256` が `null` で、かつファイルが存在しない場合だけ行い、存在する場合は `conflict` とする。
  - 書込みは同じディレクトリの一時ファイルへ書いて flush・fsync した後に `os.replace` で置き換える。Windows の `PermissionError` は 0.1 秒間隔で最大 5 回再試行する。失敗時は一時ファイルを削除し、元のファイルを変更しない。文字コードは UTF-8、改行は入力のまま保存する。
  - QA の作成（`hve_qa_create`）。パスは `qa/<run_id>-<label>-knowledge-discovery-qa.md` とする（`run_id` は共通の run_id 無害化規則 `hve/run_state.py` `_safe_run_id_component` で `[A-Za-z0-9_-]` 以外を除去し、結果が空なら `unknown`。`label` は `[A-Za-z0-9._-]` 以外を `-` に置換し、先頭 40 文字）。既存なら `-2`〜`-99` を付けた最初の未使用名を排他的に作成し、99 まで埋まっていれば `exists` とする。1 セッションで作成できる QA は 5 件までとし、超過は `limit-exceeded` とする。内容は QA 表（`## 質問項目`）と `## 調査出典` 節とする。
  - QA の回答更新（`hve_qa_answer`）。更新できるのは、探索モード `qa` で指定された QA ファイルと、当該セッションが作成した QA ファイルだけとし、それ以外は `path-denied` とする。表に無い質問番号は `invalid-question` とする。調査列を指定された質問だけ更新し、他の列と他の質問を変更しない。出典 ID はファイル内で `S1` からの連番へ振り直し、`## 調査出典` 表（`| 出典ID | 種別 | サーバー | ツール | 場所 | 要約 |`）へ追記する。
  - knowledge の書込み（`hve_knowledge_write`、探索モード `knowledge` のみ）。D 文書は最初の空でない行が `# D<NN>:` で始まり、`NN` がファイル名の番号と一致し、かつ FR-WF-AKM-01 の検証器（[.github/scripts/validate-knowledge-files.py](.github/scripts/validate-knowledge-files.py) の本文 schema 判定。メタデータ 6 項目、§1〜§8 の順序、20,000 文字以下）で違反が 0 件でなければならない。違反は `invalid-content` とし、検証器の違反文を返す。検証器を読めない場合も `invalid-content` とする（検証を省略しない）。status ファイルは空白だけでないことだけを検査する。いずれも検証済みの出典を 1 件以上必要とする。D 文書の書込みが成功したら、`knowledge/D<NN>-<名前>-ChangeLog.md` の `## 知識探索による更新履歴` 節の表へ `| <UTC の YYYY-MM-DDTHH:MM:SSZ> | <run_id> | <summary> | <出典 locator を <br> で連結> |` を 1 行追記する。節が無ければファイル末尾に見出しと表ヘッダー `| 日時 (UTC) | 実行 ID | 変更内容の要約 | 出典 |` を追加する。ChangeLog が無ければ、FR-WF-AKM-01 の ChangeLog schema（冒頭の `sources` / `generated_at` / `generator` コメント、メタデータ 5 項目、`## 全体更新履歴` / `## 要求項目別ログ` / `## 付録 A: マッピング詳細`）を満たす雛形（`generator` は `hve-knowledge-discovery`）を作成してから追記する。status ファイルには ChangeLog を追記しない。表のセルでは `|` を `&#124;`、改行を `<br>` に置換する。
  - tool の戻り値は JSON 文字列とし、成功時は `{"ok": true, "path", "sha256", ...}`、失敗時は `{"ok": false, "code", "message"}`（`conflict` は `current_sha256` を含む）とする。
- **FR-KD-06**: **優先度 MUST。** 事前 QA（FR-QA-03）への適用。
  - 条件は、質問が 1 件以上、`dry_run` でない、FR-INPUT-05 の同意が成立している（custom input を持たない Step では常に成立）、`usable` が 1 件以上、の全部とする。
  - 手順は次のとおりとする。(1) 未回答の質問票を `qa/{run_id}-{step_id}-pre-execution-qa.md` へ FR-KD-05 で書く（無ければ新規作成、あれば現在の SHA-256 で置換）。(2) 探索モード `qa` で探索する。(3) ファイルを再読込し、`調査状態` が `Confirmed` または `Tentative` で `調査回答` が空でない質問は `ユーザー回答` に `調査回答` を採用し、それ以外の質問は `既定値候補` を採用する。(4) 既存の保存・再読込検証・QA 起点 AKM の登録（FR-QA-03）を行う。
  - 探索を行う場合、人への回答待ち（CLI の標準入力、GUI のダイアログ、IPC）を行ってはならない。較正ログ（FR-QA-10）へは記録しない（利用者の明示回答ではないため）。
  - 質問票を作る Pre-QA sub-session（`qa_model` がメインと異なる、知識探索を行う、または custom input を持つ場合に作る）では、呼出し元の `disabled_mcp_servers` を変更せず、その和集合に `workiq` と実効知識源の全 MCP server 名を加える。質問票の生成中に知識源へ問い合わせないため、また Work IQ 無効時も利用者設定の `workiq` を FR-INPUT-05 の同意前に呼ばせないためである。Step の required Skill / MCP は維持する（required MCP に `workiq` を含む場合は既存の routing 規則どおり fail-closed）。
  - 条件が成立しない場合は、従来の回答収集（`_collect_qa_answers`）を行う。探索が失敗した場合（セッション作成の失敗、例外、timeout）は警告し、その時点でファイルへ記録済みの調査回答だけを (3) の規則で採用し、残りは既定値候補とする。この場合も人への回答待ちを行わない。
  - 例: 3 問のうち Q1 が `Confirmed`（調査回答 `A) 差分マージ`）、Q2 が `Unknown`、Q3 が未記録の場合、ユーザー回答は Q1=`A) 差分マージ`、Q2=Q2 の既定値候補、Q3=Q3 の既定値候補となる。
- **FR-KD-07**: **優先度 MUST。** AKM への適用。AKM の実行で `dry_run` でなく `usable` が 1 件以上の場合、Issue 作成後・DAG 実行前に「AKM 知識探索」phase を 1 回だけ実行する（探索モード `knowledge`）。目標は、`knowledge/business-requirement-document-status.md` の Unknown / Tentative を優先し、AKM の `sources` に含まれる入力（`qa` → `qa/`、`original-docs` → `docs-original/`）と知識源から事実を特定して `hve_knowledge_write` で D 文書を更新し、調べた不明点と結論を QA へ記録することとする。phase の失敗は警告だけとし、DAG を継続する。旧「AKM Work IQ 取り込み」と「AKM Work IQ 検証」の phase は実行してはならない。
- **FR-KD-08**: **優先度 MUST。** ARD への適用。ARD Step 2 が実行対象で、`dry_run` でなく、`usable` が 1 件以上の場合、Step 2 の Issue 作成後・DAG 実行前に「ARD 知識探索」phase を実行する（探索モード `research`）。目標には `company_name`（未指定なら `未指定`）と、`docs/company-business-requirement.md` が存在すればそのパスを含める。探索で作成された QA に `Confirmed` / `Tentative` の回答が 1 件以上あり、Step 2 の Issue 番号・repo・token が揃う場合に限り、Step 2 の Issue へコメントを 1 件投稿する。コメントは見出し `## ARD 知識探索: ユースケース参照情報`、QA ファイルのパス、表 `| No. | 質問 | 調査状態 | 調査回答 | 調査出典 |`、`## 調査出典` 表の写しで構成し、セルの `|` を `&#124;`、改行を `<br>`、`<` / `>` を `&lt;` / `&gt;` に置換する。回答が 0 件、または Issue 番号が無い場合は投稿せず、その旨を 1 行で通知する。phase の失敗は警告だけとし、DAG を継続する。
- **FR-KD-09**: **優先度 MUST。** 事後検証と修復。
  - 最初の `send_and_wait` の完了後、探索モード `qa` では対象 QA の全質問に `調査状態` があるか、探索モード `knowledge` / `research` では当該セッションが QA を 1 件以上作成し、その全質問に `調査状態` があるかを確かめる。不足があれば、同じセッションへ不足項目（質問番号、または `QA 未作成`）だけを列挙した修復の指示を送る。修復は最大 2 回とする。
  - 2 回の修復後も `調査状態` が無い質問は、探索モードによらず HVE が FR-KD-05 経由で `調査状態=Unknown`、`調査回答` 空で記録する。
  - 探索モード `knowledge` / `research` で作成された QA は、続けて `状態` を `調査済み` とし、`調査状態` が `Confirmed` / `Tentative` で `調査回答` が空でない質問の `ユーザー回答` に `調査回答` を写す（後続の AKM が回答として読むため）。どちらの書込みも FR-KD-05 の SHA-256 照合を使い、`conflict` は読み直して最大 5 回再試行する。
  - 完了時にコンソールへ `知識探索 [<label>]: Confirmed=<n> Tentative=<n> Unknown=<n> 修復=<n> tool失敗=<n>` を 1 行出力する。
- **FR-KD-10**: **優先度 MUST。** Work IQ 専用処理の廃止。
  - 削除するもの: `.github/prompts/runtime/workiq/` 配下の全 Prompt、事前 QA の質問単位の Work IQ 問い合わせと `*-workiq-pre-qa-draft.md` の生成、Work IQ 応答の `STATUS:` と内容書式の検証、AKM の D クラス単位の Work IQ 問い合わせ（取り込み・検証）、ARD の Work IQ 問い合わせ、GUI QA 回答ダイアログの「Work IQ 用プロンプトをコピー」、Step 実行中の Work IQ tool 呼出しの追跡と通知（`🔍 Work IQ ツール '<名前>' が呼び出されました`）。MCP server の接続失敗（`failed` / `needs-auth`）を非致命とする警告（「知識源は補助的な情報源のため実行は継続します」）は、`workiq` と実効知識源のすべてへ一般化して維持する。
  - 削除する CLI option: `--workiq-akm-review` / `--no-workiq-akm-review`、`--workiq-akm-ingest` / `--no-workiq-akm-ingest`、`--workiq-dxx`、`--workiq-draft`、`--workiq-draft-output-dir`、`--workiq-prompt-qa`、`--workiq-prompt-km`、`--workiq-per-question-timeout`。これらを指定した起動は argparse エラー（exit code 2）とする。
  - 削除する `SDKConfig` field: `workiq_qa_enabled`、`workiq_akm_review_enabled`、`workiq_akm_ingest_enabled`、`workiq_akm_ingest_dxx`、`workiq_prompt_qa`、`workiq_prompt_km`、`workiq_draft_mode`、`workiq_draft_output_dir`、`workiq_per_question_timeout`、`workiq_max_draft_questions`、`workiq_priority_filter`。削除する環境変数: `WORKIQ_QA_ENABLED`、`WORKIQ_AKM_REVIEW_ENABLED`、`WORKIQ_AKM_INGEST_ENABLED`、`WORKIQ_AKM_INGEST_DXX`、`WORKIQ_PROMPT_QA`、`WORKIQ_PROMPT_KM`、`WORKIQ_DRAFT_MODE`、`WORKIQ_DRAFT_OUTPUT_DIR`、`WORKIQ_PER_QUESTION_TIMEOUT`、`WORKIQ_MAX_DRAFT_QUESTIONS`、`WORKIQ_PRIORITY_FILTER`（設定されていても読まない）。
  - GUI の保存設定ファイルに削除したキー（`workiq_draft`、`workiq_akm_review`、`workiq_akm_ingest`、`workiq_dxx`、`workiq_draft_output_dir`、`workiq_prompt_qa`、`workiq_prompt_km`、`workiq_per_question_timeout`）が残っていても、読込で無視し、次回保存で書かない。
  - 維持するもの: `--workiq`、`WORKIQ_ENABLED`、`workiq_enabled`、AKM `sources` の `workiq` トークン、ARD の `ard_workiq_enabled`、FR-CLI-91 の capability 判定、FR-CLI-81 / FR-CLI-91 の実行単位の無効化。
  - 既存の `qa/` ファイルの `Work IQ 回答案` / `Work IQ 理由` 列は、それぞれ `調査回答` / `調査出典` として読む。書き出しは新しい列名だけを使う。
- **FR-KD-11**: **優先度 MUST。** ローカル実行面での事前 QA と Work IQ の既定有効化（v3.42）。出典: 利用者依頼（2026-10-02「`**期待どおりに動かない原因**`を修正してください。」の原因 1「既定で無効」）、[202610020340-UnknownIssueBehaviorAnalytics.md](../work/202610020340-UnknownIssueBehaviorAnalytics.md) §8-1。
  - 直接 CLI `orchestrate` は `--auto-qa` / `--no-auto-qa` と `--workiq` / `--no-workiq` を受け取る（argparse `BooleanOptionalAction`、未指定は `None`）。`SDKConfig.auto_qa` は、`--no-auto-qa` なら `False`、それ以外（`--auto-qa` または未指定）なら `True` とする。`SDKConfig.workiq_enabled` は、`--workiq` なら `True`、`--no-workiq` なら `False`、未指定なら環境変数 `WORKIQ_ENABLED` で決める。`WORKIQ_ENABLED` の前後空白を除いて小文字化した値が `false` / `0` / `no` なら `False`、それ以外（未設定・空文字を含む）なら `True` とする。`SDKConfig()` の dataclass 既定値（`auto_qa=False` / `workiq_enabled=False`）は、プログラムから直接生成する場合の値として変更しない。`SDKConfig.from_env()` の `workiq_enabled` は前記の環境変数規則に従う。
  - 対話 wizard（`orchestrate` を `--workflow` なしで起動）は、AKM 以外の Workflow で「QA 自動投入を有効にする？」の既定を `y` とし、知識源の質問「知識探索で Work IQ を使う？」の既定を `y` とする。クイック全自動は、AKM 以外かつ ARD 以外の Workflow で `auto_qa=True`、`workiq_enabled` を Work IQ capability が `ready` かどうかに一致させる。AKM と ARD の wizard の質問と既定（AKM の `sources`、ARD の `ard_workiq_enabled`）は変更しない。
  - GUI の `auto_qa` は FR-GUI-16 の必須選択（未選択では実行しない）を維持する。GUI 設定の `workiq` の既定値は `True` とする。保存済みの値は変更しない。GUI の起動ウィザード（[hve/gui/wizard.py](hve/gui/wizard.py) `WizardResult`）の `--auto-qa` チェックボックスは、チェック時に `--auto-qa`、未チェック時に `--no-auto-qa` を出す（利用者の明示選択として扱う）。同ウィザードの Work IQ ページ（[hve/gui/page_workiq.py](hve/gui/page_workiq.py) `to_workiq_argv`）は `--no-workiq` も抽出する。
  - [hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py) `OrchestrateArgs` の `auto_qa` / `workiq` の既定値は `True` とする。`to_argv()` は `auto_qa` が `True` なら `--auto-qa`、`False` なら `--no-auto-qa` を、`workiq` が `True` なら `--workiq`、`False` なら `--no-workiq` を必ず 1 つ出力する（CLI の既定値に依存しないため）。Prompt 版の `args_from_settings()` は、保存値 `auto_qa` が `"on"` / `True` なら `True`、`"off"` / `False` なら `False`、それ以外（未選択 `""`・キーなし）なら `True` とする。GUI の `OptionsPage.build_args_for_workflow()` も未選択を同じ規則（`auto_qa=True`、`qa_answer_mode` は保存値が `autopilot` のときだけ `autopilot`）で組み立て、FR-LOCAL-SURFACE-01 の argv 一致を保つ（GUI は FR-GUI-16 により未選択のまま実行しない）。
  - HVE が自ら起動する子 `orchestrate` のうち、FR-QA-03 の QA 起点 AKM 子実行（[hve/qa_akm_dispatch.py](hve/qa_akm_dispatch.py) `_build_argv`）は `--no-auto-qa` と `--no-workiq` を必ず含める（AKM 子では事前 QA と Work IQ を使わない従来の動作を保つため）。`hve resume` の replay argv（[hve/resume_service.py](hve/resume_service.py)）は、元の実行の `auto_qa` と `workiq_enabled` を `--auto-qa` / `--no-auto-qa`、`--workiq` / `--no-workiq` で必ず明示する。Autopilot チェーンの子（`--app-ids` と `--workbench off` だけを渡す）は CLI の既定（両方有効）に従う。
  - `--dry-run` は既存どおり Work IQ の capability 確認と知識探索を行わない。`ready` でない Work IQ は FR-CLI-91 のとおり当該実行だけ無効化する。
  - 例: `python -m hve orchestrate -w aas`（`WORKIQ_ENABLED` 未設定）→ `auto_qa=True`、`workiq_enabled=True`。`-w aas --no-auto-qa --no-workiq` → 両方 `False`。`WORKIQ_ENABLED=No -w aas` → `workiq_enabled=False`。`WORKIQ_ENABLED=false -w aas --workiq` → `workiq_enabled=True`。
- **FR-KD-12**: **優先度 MUST。** 知識源を使えなかった理由の記録と認証の案内（v3.42）。出典: 同依頼の原因 2「この環境では WorkIQ が使えない」、同レポート §6。
  - FR-KD-02 の除外警告は、理由コードが `server-needs-auth` のとき `知識源 <名前> を除外します（server-needs-auth）。GitHub Copilot CLI で /mcp auth <名前> を実行して認証し、HVE を再起動してください。` とする。ほかの理由コードの文面は FR-KD-02 のままとする。HVE は認証を試みない。
  - `run_knowledge_discovery` の戻り値 `DiscoveryResult` は `usable`（最終的に使った知識源名の列）と `excluded`（`(知識源名, 理由コード)` の列。snapshot 判定の除外、続いてセッション内判定の除外の順）を持つ。
  - 事前 QA（FR-KD-06）と実行後の不明点調査（FR-KD-13）で、実効知識源が 1 件以上あり（`dry_run` でない、`asdw-data` の deploy Step でない）、質問が 1 件以上ある場合、保存する QA ファイルに `## 知識探索の状況` 節を置く。節は表 `| 知識源 | 状態 | 理由コード |` とし、実効知識源 1 件につき 1 行を実効知識源の順に書く。状態と理由コードは次のとおりとする。`usable` に含まれる → `利用` / `-`。`excluded` に含まれる → `除外` / その理由コード。FR-INPUT-05 の同意が得られず探索しなかった → `未実行` / `consent-not-granted`。探索の開始時に例外が発生し戻り値が無い → `不明` / `discovery-error`。前記以外（探索の途中で終わった等）→ `不明` / `not-reported`。セルの `|` は `&#124;`、改行は `<br>` に置換する。
  - 例: `workiq` が `needs-auth` の場合、QA ファイルに `| workiq | 除外 | server-needs-auth |` の行が残り、各質問の `ユーザー回答` は従来どおり回答収集または既定値候補で決まる。
- **FR-KD-13**: **優先度 MUST。** 実行後の不明点調査（v3.42）。出典: 同依頼の原因 4「メインタスクの前だけ」。
  - 条件は、`auto_qa=True`、`dry_run` でない、durable recovery の `reuse-session` 対象 Step でない、メインタスク（Phase 1）と直後の成果物継続（FR-WF-OUT-12）・`asdw-data` の契約ゲートがすべて `failed` を返さずに終わった、の全部とする。条件を満たす Step では、メインタスクの後・敵対的レビュー（Phase 3）の前に「実行後の不明点調査」phase を 1 回だけ実行し、Step の phase 総数に数える。
  - 手順は次のとおりとする。(1) メインタスクと同じセッションへ、実行中に不明・曖昧なため仮定を置いて進めた点と確認できなかった前提だけを対象とし、対象が無ければ質問票を作らず `質問なし` とだけ答えるよう求める前置きに続けて `QA_PROMPT_V2`（[.github/prompts/runtime/qa/post-execution.prompt.md](.github/prompts/runtime/qa/post-execution.prompt.md)）を送る。(2) 応答を事前 QA と同じ解析（`_parse_qa_content_with_artifact_fallback`）で読み、質問が 0 件なら QA ファイルを作らずに phase を終える。(3) 質問票を `qa/{run_id}-{step_id}-post-execution-qa.md` へ FR-KD-05 で書く。(4) 実効知識源が 1 件以上あり、`asdw-data` の deploy Step でなく、custom Step 入力を持つ Step では事前 QA で FR-INPUT-05 の同意が成立している場合に、探索モード `qa` で知識探索を 1 回実行する（目標は「直前に完了したタスクの実行中に生じた不明点への答えを、知識源とリポジトリ内の資料から調べる」）。(5) FR-KD-12 の `## 知識探索の状況` 節を加え、FR-KD-06 (3) の規則（`Confirmed` / `Tentative` の調査回答、それ以外は既定値候補）で `ユーザー回答` を決め、FR-QA-03 の保存・再読込検証・QA 起点 AKM の登録を行う。
  - 本 phase は人への回答待ち（標準入力・GUI ダイアログ・IPC）を行わず、較正ログ（FR-QA-10）へ記録しない。結果を同じ Step の後続 phase や後続 Step のプロンプトへ注入しない。
  - (1)〜(5) のどこで失敗しても（SDK 例外、timeout、解析・保存・検証の失敗）、`実行後の不明点調査 [<step_id>] を完了できませんでした（<例外の型名>）。` を警告し、Step の成否を変えずに後続 phase へ進む。
  - 例: メインタスクの応答に [Q01]〜[Q02] の質問票が返り、知識探索が Q01 を `Confirmed`（`A) 差分マージ`）、Q02 を `Unknown` と記録した場合、`qa/r1-1-post-execution-qa.md` の `ユーザー回答` は Q01=`A) 差分マージ`、Q02=Q02 の既定値候補となる。
- **FR-KD-14**: **優先度 MUST。** Prompt 版での知識源の run 単位指定（v3.42）。出典: 同依頼の原因 5「Prompt 版の制約」。
  - request v1 の `settings_overrides` は `workiq`（JSON の真偽値）と `knowledge_sources`（文字列。カンマ区切りの知識源名。空文字は「追加の知識源なし」）を受け付ける。`workiq` が真偽値でない場合、`knowledge_sources` が文字列でない場合、または `knowledge_sources` を FR-KD-01 の規則で分解したトークンに名前規則違反がある場合は `PromptRequestError` とし、計画を作らない（fail-closed）。
  - 受け付けた値は FR-LOCAL-SURFACE-01 の優先順位（`settings_overrides` > 保存済み GUI 設定 > 既定値）で `OrchestrateArgs.workiq` / `OrchestrateArgs.knowledge_sources` へ適用し、FR-CLI-91 の capability 確認（`_args_request_workiq`）にも同じ値を使う。
  - 例: `"settings_overrides": {"workiq": false}` → 子 argv に `--no-workiq`。`{"knowledge_sources": "microsoft-learn"}` → `--knowledge-source microsoft-learn`。`{"knowledge_sources": "bad name"}` → `PromptRequestError`。
- **NFR-KD-01**: **優先度 MUST。** 秘密情報と業務データの扱い。MCP の応答本文は HVE のプロセスのメモリ上だけに保持し、FR-MCPLOG の既存ログ以外のファイル・コンソール・tool の失敗メッセージ・QA・ChangeLog へ書いてはならない。QA と ChangeLog へ書くのは、モデルが tool に渡した回答・要約・出典の locator だけとする。ロックファイルには pid・host・token・作成時刻だけを書く。

## 4. HVE Cloud Agent Orchestrator 固有要件

### 4.1 トリガー仕様

- **FR-CLOUD-01**: 監視イベントは `issues` の `opened` / `labeled` / `closed` の 3 種（[.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)）。
- **FR-CLOUD-02**: 起動はラベルベース。`trigger_map` に従い、対応する `auto-*-reusable.yml` を `workflow_call` で起動する。
- **FR-CLOUD-03**: `opened` イベントでは `author_association` が `OWNER` / `MEMBER` / `COLLABORATOR` のいずれかである場合のみ起動する。**`labeled` / `closed` イベントには `author_association` ガードは適用されない**。
- **FR-CLOUD-04**: `closed` イベントでは Issue タイトルの `[AAS]` / `[AAD-WEB]` 等プレフィックスから対象 Workflow を判定する。プレフィックスに一致しない場合に限り、Issue に付いた trigger label から対象 Workflow を判定する（§4.2 の `closed` 行、[.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)）。
- **FR-CLOUD-05**: `setup-labels` ラベル付与時は `setup-labels.yml` を起動する。
- **FR-CLOUD-06**: registry と同期していない Cloud reusable workflow を dispatcher から起動してはならない。同期とは、reusable workflow が生成する Step Issue の Step ID 集合と Custom Agent 集合が、[.github/scripts/bash/lib/workflow-registry.sh](.github/scripts/bash/lib/workflow-registry.sh) と [hve/workflow_registry.py](hve/workflow_registry.py) の当該 Workflow 定義に一致することを指し、判定は [hve/tests/test_cloud_reusable_workflow_parity.py](hve/tests/test_cloud_reusable_workflow_parity.py) が行う。同期が確認できた Workflow は dispatch 対象としてよい。ASDW-WEB は [.github/workflows/auto-app-dev-microservice-web-reusable.yml](.github/workflows/auto-app-dev-microservice-web-reusable.yml) が現行 Step 体系と非同期であったため Cloud 起動を停止していたが、同 workflow を現行体系へ再構築して同期を確立したため、dispatcher の停止対象（`cloud_dispatch_disabled_targets`）と停止通知ジョブを撤去する（[.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)）。将来いずれかの Workflow で同期が崩れた場合は、本要件に基づき対象 ID と根拠を明記したうえで再び dispatch 対象から外す。AKM は [.github/scripts/bash/lib/workflow-registry.sh](.github/scripts/bash/lib/workflow-registry.sh) へ未登録で reusable workflow が Step をハードコードしているため、同期判定は [hve/workflow_registry.py](hve/workflow_registry.py) の AKM 定義（Step.1 `KnowledgeManager` → Step.2 `QA-DocConsistency`）に対してのみ行う。[.github/workflows/auto-knowledge-management-reusable.yml](.github/workflows/auto-knowledge-management-reusable.yml) は Step.1 と Step.2 の Step Issue を生成し、Step.1 完了で Step.2 を起動し、Step.2 完了で Root Issue へ `akm:done` を付与しなければならない。Step.1 の D01〜D21 fan-out を Cloud で Step Issue へ展開してはならない（`knowledge/` の出力空間は `target_files` によらず D01〜D21 全体と `knowledge/business-requirement-document-status.md` を含み、Step Issue 単位の並列化が同一ファイルへの同時書込みを生むため。FR-QA-03 と同一の根拠）。[.github/scripts/bash/lib/workflow-registry.sh](.github/scripts/bash/lib/workflow-registry.sh) に登録済みの各 Workflow の heredoc JSON は、[hve-dev/generate_workflow_registry_sh.py](hve-dev/generate_workflow_registry_sh.py) が [hve/workflow_registry.py](hve/workflow_registry.py) の当該 Workflow 定義から生成し、直接編集してはならない。表示名 `name` だけは Cloud の面が持つ既存の値を保持する（CLI / GUI の表示名と Cloud の表示名は面ごとに持つため）。生成物との一致の判定は [hve/tests/test_workflow_registry_sh_generated.py](hve/tests/test_workflow_registry_sh_generated.py) が行う。
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
- **FR-CLOUD-22**: **AKM Orchestrator では** `check_qa_skip` ジョブが前段で実行され、`auto-qa` のスキップ条件を判定する。主要 reusable workflow の同等チェックも確認済み。
- **FR-CLOUD-23**: AKM Orchestrator のジョブタイムアウトは 360 分。
- **FR-CLOUD-24**: Cloud Agent Orchestrator が現在対応する Knowledge Management (`AKM`) 以外の Workflow で Issue Form の `enable_qa` が有効な場合、`*:qa-ready` / `*:qa-drafting` の回答受領後、イベントの回答コメント ID を一次キーとして当該 Issue への帰属を検証し、回答時刻（同秒時はコメント ID）より前の最新質問票とだけ対応付けて FR-QA-03 の回答済み形式へ正規化する。`^qa/Issue-[0-9]+-questionnaire-answered-[0-9a-f]{8}\.md$` に一致する固定のパスセーフなファイルとして対象 branch へ保存し、Contents API の再取得結果と SHA を照合してからメインタスクをアサインしなければならない。回答コメントが構造化回答として解決できず、かつ未回答項目に既定値が無い場合は `qa-ready` を維持して修正を求める。保存用 GitHub Actions job は固定 `qa/` パスだけを書き込み、job 単位の `contents: write` と `GITHUB_TOKEN` を使い、branch の実在を確認し、branch protection を迂回してはならない。保存成功後は source Issue 番号・QA SHA・対象 branch・対象ファイルを入力として `workflow_dispatch` 対応の QA 起点 AKM 調整 Workflow を非同期 dispatch する。dispatch job だけに `actions: write` を付与し、GitHub API が dispatch 要求を成功として受理した時点で source Workflow は AKM 調整 job の開始・完了を待たず続行する。調整 Workflow は AKM Root Issue body の `<!-- qa-akm-sync: source-issue=<N>; qa-sha=<64hex>; branch=<branch> -->` を冪等キーとし、open / closed の両方から同一キーを検索して重複を拒否する。既存 Root の routing label が部分失敗で欠落している場合はポーリング前に自己修復する。リポジトリ単位の concurrency を取得した job 内で独立 AKM Root Issue を作成・アサインした後、上限 360 分の低頻度ポーリングにより当該 AKM Root Issue が `akm:done` / `akm:blocked` または closed になるまで待機し、その間 concurrency を保持する。タイムアウト判定の直前には終端状態を再取得し、完了済み Root へ `akm:blocked` を誤付与してはならない。ここで直列待機するのは後続の AKM 実行だけであり、source Workflow は待機対象ではない。外部 Copilot Agent は Actions の初期化 job 終了後も `knowledge/` を更新し得るため、既存の job 終了までの concurrency だけでは同時書込みを防げず、この独立した保持 job を必要とする。タイムアウト時は AKM Root Issue を `akm:blocked` として待機を終了し、source Workflow の成否は変更しない。AKM の auto-merge は source の設定を継承し、強制的に有効化してはならない。`*:qa-ready` / `*:qa-drafting` が同時に複数存在する場合は fail-closed とし、ラベル遷移は新状態の追加と read-back を先に行い、旧状態の削除後にも再検証し、不整合時は旧状態を復元する。Copilot の質問票生成 PR が opened になっただけでメインタスクを開始してはならず、PR opened 経路は質問票コメント確認後の `*:qa-drafting` → `*:qa-ready`（回答待ち）までに限定する。Cloud の AKM Step 構成は FR-CLOUD-06 の 2 Step 契約に従う。Cloud dispatch が停止・未実装の Workflow を本要件だけを理由に新規対応してはならない。ADI は Cloud dispatcher 非対応であるため、本要件は ADI の Cloud 対応を要求しない。

- **FR-CLOUD-25**: FR-CLOUD-24 が作成する QA 起点 AKM Root Issue は、source Issue Form で選択された AKM 用モデルを継承しなければならない。Issue Form は Knowledge Management 自身を除く各テンプレートへ `akm_model` を追加し、選択肢は既存の `model` / `review_model` / `qa_model` と同一の許可リスト（`Auto` / `claude-opus-5.5` / `claude-opus-4.7` / `claude-opus-4.6` / `gpt-5.5` / `gpt-5.4`）とする。`save-qa-answer` job は source Issue body の `### AKM 用モデル` 節を許可リスト照合付きで抽出し、一致しない値は空文字へ丸めて dispatch 入力へ渡す。調整 Workflow は当該入力を同じ許可リストで再検証し、一致しない場合は自ら `Auto` へフォールバックしたうえで、作成する AKM Root Issue body の `### 使用するモデル` 節へ必ず値を書き込み、`akm` reusable workflow の既存モデル抽出経路（[.github/scripts/bash/lib/extract-model.py](.github/scripts/bash/lib/extract-model.py)）がそのまま解決できる形にしなければならない。未指定・不正値・許可リスト外を理由に dispatch または調整 Workflow を失敗させてはならない。Cloud 面には reasoning effort / context tier に相当する設定が存在しないため、本要件はモデルのみを対象とし、FR-QA-04 の `akm_reasoning_effort` / `akm_context_tier` を Cloud へ持ち込んではならない。本要件は Cloud の QA 起点 AKM が常に既定モデルで実行され、利用者が AKM だけのモデルを選べなかった状態を解消するために必要である。
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
  - 本要件は §13.13 が blocked を「手動介入の対象とする」と述べるにとどまり、手動介入の引き渡し方法・SLA・復帰経路が未定義だった状態を解消する。CLI / GUI に等価の経路は無く、本要件は Cloud Agent Orchestrator に限定する。
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
| `ingest-docs` | `docs-original/` を走査して `docs/original-design-doc-ingest/` へ目録と正規化済み Markdown を出力 |
| `emit-prompt` | Step のプロンプトを表示（デバッグ用） |
| `gui` | PySide6 ベースの GUI Orchestrator を起動（未導入時はセットアップスクリプトを案内） |
| `cli` | 対話型 CLI ウィザードでワークフローを実行（`run` と同一の対話経路） |
| `login` | GitHub Copilot へログインし、利用可能モデル一覧をキャッシュ |
| `pricing` | AI Credit 料金表を取得・表示（下位サブコマンド `show` / `refresh`） |
| `toolsearch` | Tool Search ランキングの統計を表示（下位サブコマンド `dashboard` / `context`、FR-TS-10 / FR-TS-11） |
| `prompt` | Prompt 版 request から実行計画を提示し、承認後に既存 `orchestrate` へ委譲（下位サブコマンド `plan` / `run`、FR-PROMPT-03 / FR-PROMPT-04） |

本表は `_build_parser()` が登録するトップレベルサブコマンドの全件とし、契約テスト [hve/tests/test_requirement_subcommand_parity.py](hve/tests/test_requirement_subcommand_parity.py) が実装との一致を機械検査する。索引の差分更新対象外サブコマンドの列挙は FR-CLI-77 が別に規定する。

- **v3.41 明確化（`qa-merge` の統合ドキュメント生成）**: `--skip-consistency` を指定しない `qa-merge` は、SDK セッション（`client.create_session`、`on_permission_request` はツール許可要求を常に拒否、`Auto` 以外は `model` を指定）で統合ドキュメントを生成する。生成・保存に失敗した場合（モデル呼び出しの例外、空の応答、保存失敗）は、client / session を閉じたうえで stderr へ `統合ドキュメント生成に失敗` 等を出力し exit code 1 とする（マージ済みの質問票は保存済みのまま残す）。Copilot SDK 自体が無い場合だけ、警告のうえ統合をスキップして exit code 0 とする（システムテスト N-05）。
- **v3.41 明確化（`pricing` の取得元）**: モデル別料金の取得元は `https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing`（2026-10-02 確認。旧 `about-billing-for-github-copilot` は 404）とし、`Model` / `Input` / `Output` 列を持つ表から 100 万 token あたり USD の単価を `input_price_per_mtoken_usd` / `output_price_per_mtoken_usd` へ保存する。同一モデルが Tier 違いで複数行ある場合は先頭行（Default）だけを採用し、`$` 付きの数値でないセル（`Not applicable` 等）と脚注番号は値として扱わず `None` とする。旧 `Model` / `Multiplier` 表も後方互換で `multiplier` へ取り込む。プラン定義（`https://github.com/pricing`）が解析できなくても、モデル別料金が取得できれば `status=partial` として保存し exit code 0 とする。両ソースとも取得できないときだけ exit code 1 とする。取得できない値は推定で補完しない（システムテスト N-07）。SDK のモデル ID（`claude-opus-5.5`）は記号を `-` へ正規化して保存キー（`claude-opus-5-5`）と照合する。

### 5.2 `orchestrate` の必須・主要オプション

- **FR-CLI-01**: 必須引数は `--workflow / -w`（Workflow ID）のみ。ただし `--autopilot-chain`（FR-CLI-78）を指定する場合は `--workflow` を省略し、両者を同時に指定してはならない（同時指定と両方の未指定はエラー終了とする。[hve/__main__.py](hve/__main__.py)）。
- **FR-CLI-02**: 主要オプション一覧:
  - **モデル**: `--model`、`--review-model`、`--qa-model`、`--akm-model`（FR-QA-04）
  - **実行品質**: `--reasoning-effort`、`--review-reasoning-effort`、`--qa-reasoning-effort`、`--akm-reasoning-effort`、`--context-tier`、`--akm-context-tier`（FR-QA-04）
  - **並列制御**: `--max-parallel`（既定 15）
  - **自動レビュー**: `--auto-qa` / `--no-auto-qa`（未指定は有効。FR-KD-11）、`--auto-contents-review`、`--auto-coding-agent-review`、`--auto-coding-agent-review-auto-approval`
  - **対話制御**: `--force-interactive`（QA 回答入力の TTY 判定をバイパスし対話モードを強制）
  - **知識源**: `--workiq` / `--no-workiq`（未指定は `WORKIQ_ENABLED` に従い既定は有効。FR-KD-11）、`--knowledge-source`（FR-KD-01）。v3.38 で削除した Work IQ 専用 option の一覧は FR-KD-10 を正とする
  - **Git/PR**: `--create-issues`、`--create-pr`、`--issue-number`（FR-GUI-25）、`--ignore-paths`、`--branch`、`--repo`
  - **出力**: `--verbose`、`--quiet`、`--verbosity`、`--show-stream`、`--log-level`、`--no-color`、`--banner / --no-banner`、`--screen-reader`、`--timestamp-style`、`--final-only`
  - **タイムアウト**: `--timeout`（既定 21600 秒 = 6h）、`--review-timeout`（既定 7200 秒 = 2h）
  - **MCP / CLI 接続**: `--cli-path`、`--cli-url`
  - **SDK セッション**: `--tool-search` / `--no-tool-search`（FR-MODEL-04、既定有効）、`--tool-search-defer-threshold N`（FR-MODEL-04、正の整数のみ。省略時は SDK 既定へ委譲）
  - **共通絞り込み**: `--steps`、`--app-id`（後方互換、複数指定不可。現行推奨は `--app-ids`） / `--app-ids`、`--resource-group`、`--usecase-id`
  - **AKM 固有**: `--sources`、`--target-files`、`--force-refresh / --no-force-refresh`、`--custom-source-dir`、`--enable-auto-merge`
  - **ADI 固有**: `--purpose`、`--target-scope`、`--depth`、`--focus-areas`
  - **ADOC 固有**: `--target-dirs`、`--exclude-patterns`、`--doc-purpose`、`--max-file-lines`
  - **ARD 固有**: `--company-name`、`--target-business`、`--survey-base-date`、`--survey-period-years`、`--target-region`、`--analysis-purpose`、`--target-recommendation-id`、`--attached-docs`
  - **追加**: `--additional-prompt`、`--context-max-chars`、`--issue-title`
  - **検証**: `--dry-run`

### 5.3 対話 wizard

- **FR-CLI-10**: `python -m hve`（引数なし）は GUI Orchestrator を既定として起動する。PySide6 が未導入で `ImportError` となる場合に限り、導入手順を示す警告を出したうえで CLI 対話 wizard へフォールバックする。`python -m hve run` および `python -m hve cli` は対話 wizard を明示的に起動する。本項は FR-CLI-77 の「引数なし起動（GUI が既定）の経路は FR-GUI-22 が担う」という担当区分と整合しなければならない。契約テスト [hve/tests/test_requirement_entrypoint_parity.py](hve/tests/test_requirement_entrypoint_parity.py) が本項と実装の一致を機械検査する。
- **FR-CLI-11**: wizard は実行モードとして `quick-auto`（画面表示: クイック全自動）、`custom-auto`（画面表示: カスタム全自動）、`manual`（画面表示: 手動）の 3 つを提供する。`quick-auto` は既定値中心、`custom-auto` は全設定を事前入力した後の無人実行、`manual` は実行中も対話可能な経路とし、Workflow 固有パラメータは選択したモードに従って収集する。
  - **v3.41 明確化（stdin が EOF のとき）**: wizard の入力が EOF（`input()` の `EOFError`）で閉じられた場合、`Console` は `input_eof` を記録し、wizard は最終確認（`この設定で実行しますか？`）の前に、既定値を自動受理せず `標準入力が閉じているため、対話設定を既定値で確定できません` を stderr へ出力して exit code 1 で終了する。durable 登録・preflight・モデル実行を開始してはならない（必須の対象業務名が空のまま、実モデル実行と AI Credit 消費が始まるため。システムテスト N-04）。`KeyboardInterrupt` は EOF として記録しない。出典: 同結果 N-04（2026-10-02）。受入テスト: `hve/tests/test_resume_cli.py::TestExecutionRegistration::test_closed_stdin_stops_the_wizard_before_any_execution`、`hve/tests/test_systemtest_20261002_fixes.py::test_console_records_stdin_eof`。
- **FR-CLI-12**: ARD wizard は FR-WF-ARD-03 の 5 表示グループ（`1`〜`5`）をマルチ選択させ、既定選択は同要件の `ARD_DEFAULT_GROUP_IDS` に従う。グループ `1` を選択した場合だけ `company_name` を必須とし、グループ `2` を選択してグループ `1` を選択しない場合だけ `target_business` を必須とする。グループ `1` と `2` を同時選択した場合の空の `target_business` は、Step 1.2 完了後に Strategic Recommendation から生成する bridge 経路で解決する。KPI/OKR の実行有無はグループ `3` の選択だけから導出し、同じ状態を表す別の Yes/No 質問を設けてはならない。グループ `5` はアプリケーション一覧と APP 別要求定義書を一体で生成するため、片方だけを選択する別 UI を設けてはならない。
- **FR-CLI-13**: AKM wizard は `sources` をマルチ選択（`qa` / `original-docs` / `workiq`）する。（v3.38）`workiq` を含む場合に取り込み対象 Dxx を尋ねる規則は、Dxx 指定を FR-KD-10 で削除したため廃止した。
  - FR-CLI-91 の process-wide SDK discovery snapshot が `ready` でない場合は `workiq` を選択肢から除外する。選択可能な source が 0 件になる指定を既定の `qa,original-docs` へ暗黙補正せず、実行を開始しない。wizard は Work IQ の Plugin / MCP を導入・有効化・構成・認証してはならない。
- **FR-CLI-14**: ASDW-WEB wizard は Step 1.3 に到達し得る選択のとき、Step 1.3 の `required_params`（FR-DAG-07）が宣言する Workflow パラメータを順次尋ねる。`default_params` に既定値があるキーは既定値を提示し、空入力（Enter のみ）で既定値を採用する。既定値を持たないキーだけを空入力不可とする。

### 5.4 非対話モード

- **FR-CLI-20**: `cli_args` が `None` でない場合は非対話モード扱いとする（[hve/orchestrator.py](hve/orchestrator.py) `_is_non_interactive`）。
- **FR-CLI-21**: 非対話モードでは `_collect_params_non_interactive` が CLI 引数のみからパラメータを構築し、欠落値は Workflow 既定値を採用する。

#### 5.4.1 Step プロンプト構築

- **FR-CLI-70**: CLI / GUI 実行経路（[hve/orchestrator.py](hve/orchestrator.py) `_build_step_prompt`）が組み立てる Step プロンプトに、`subissues.md` のフォーマット例を注入してはならない。CLI / GUI Orchestrator 配下では分割を workflow DAG / fan-out で表現し、`subissues.md` を実行時に fork する経路を持たないため（v3.21 で legacy runtime split-fork を撤去）、常時注入は誤った作業指示になる。分割手順の参照が必要な場合は Skill `task-dag-planning` と [.github/skills/_hve-plan-artifacts/hve-binding.md](.github/skills/_hve-plan-artifacts/hve-binding.md) に委ねる。
- **FR-CLI-71**: `StepDef.body_template_path` が宣言されている Step でテンプレートのレンダリングが失敗した場合、Orchestrator は簡易プロンプトへフォールバックせず、DAG 実行前にエラーとして停止しなければならない。壊れた縮退プロンプトで Agent セッションを開始してはならない。`body_template_path` が宣言されていない Step が簡易プロンプトを使うことは、本要件の対象外であり従来どおり許容する。

#### 5.4.2 Step 実行時の分離境界

- **FR-CLI-72**: HVE は製品 run の実行中に、HVE 自身のテストスイート（`python -m pytest` 等）を子プロセスとして起動してはならない。ASDW-WEB Step 1.2 のローカル検証は、生成物に対する静的検査（`bash -n`、利用可能な場合の ShellCheck、artifact validator、LF/BOM 検査）に限定する。HVE 自身の回帰テストは CI と開発時に実行する（[hve/asdw_step12_verification.py](hve/asdw_step12_verification.py)）。
- **FR-CLI-73**: `StepRunner` が Copilot セッションへ公開する repository Skill ディレクトリは、`.github/skills` root と、当該 active Step が `required_skills` で宣言した Skill、およびインストール済みの optional Skill に限定する。`.github/skills` 直下の全ディレクトリを無条件に公開してはならない。external Skill の fail-closed 解決は維持する（[hve/runner.py](hve/runner.py)）。
  - **同梱 Skills の整理**: 以下を FR-CLI-73 の従属規範として適用する。同梱 Skill は HVE の実行・生成・検証に必要な固有契約だけを保持し、汎用の説明・教材・架空例は除く。混在 Skill は同じ既存パスで縮約し、全ての HVE 固有契約（成果物形式・必須項目・判定語彙・適用範囲・安全境界・参照先）と採択済みの数値・安全ポリシーを維持する。`code-query` / `markdown-query` を含む core Skill と FR-KIT-02 の正本は保持する。
    - Skill 入口を縮約する場合でも、既存 path、`name`、frontmatter の `metadata.version` フィールドを維持し、description は既存の用途・除外条件を識別できる簡潔な説明にする。版値の更新は既存の版管理境界に従う。詳細は既存または同じ Skill 内に既存本文を移設した `references/` へ条件付きで委譲し、全参照資料を常時必読にしてはならない。
    - 縮約時も HVE 固有契約（schema、数値、retry、permission / 承認、安全境界、no-load 拒否条件）を削除・一般化してはならない。Skill 自体を読み込まずに拒否すべき条件は description に残し、読込後・書込前に適用する承認・資格情報のゲートは root 先頭に保持する。
    - HVE 同梱の active 入口 `karpathy-guidelines` / `appinsights-instrumentation` / `test-strategy-template` / `mcp-server-design` / `svg-renderer` と、それらへの active 依存を廃止する。履歴・過去の測定条件・合成テスト fixture における旧名の記載は禁止せず、現在値へ書き換えてはならない。
    - `hve/skill_manifest.json` の `adfdv` / `aagd` の Workflow defaults にある `test-strategy-template` だけを、同じ default 位置の既存 `tdd-red-green-reality` へ置換する。両 Workflow の required 適用範囲を維持し、他 Workflow の defaults、既存の required / optional external Skill、alias policy、repository 優先・external exact 解決および fail-closed を変更しない。新しい alias や欠損時の代替解決を追加しない。
    - `test-strategy-template` の削除前に、採択済みのテスト方針を既存 `.github/skills/tdd-red-green-reality/SKILL.md` へ移管する。Unit / Integration / E2E の推奨比率 70–80% / 15–20% / 5–10%、Unit（ビジネスロジック / 変換ロジック）のカバレッジ 80% 以上（変換ロジックは 100% 目標）、Integration の主要パス・E2E のクリティカルパス網羅、I/O 層の Unit 対象除外と Integration 検証、条件付きのテストダブル優先順位（Azure Storage は Azurite を最優先、コンテナ化可能なら Testcontainers、適用不能または Unit で十分なら Mock / Stub）を、普遍的な推奨ではなく既存の HVE 生成方針として保持する。
    - 同じ削除前移管で、同 TDD Skill §1.6 に Unit / Component、実装コード向け TDD RED / GREEN、Integration、Post-deploy / E2E の実行環境分類と、層別の実行場所・外部サービス条件・設定注入を保持する。`*_BASE_URL` / `E2E_BASE_URL`、必須 URL / Endpoint / Resource 名 / 認証経路の欠落を環境ブロッカーとして扱い PASS にしない規則、および秘密情報の非ハードコード・非記録を失ってはならない。同 Skill の TDD report schema・RED/GREEN 証跡・reality gate と Step 固有契約は変更しない。
    - 本整理のために新しい flag・loader・resolver・包括 Skill を追加せず、同梱件数を恒久的な固定値にしない。Workflow / Prompt / Skill の観測可能な契約変更であるため、FR-MAINT-03 の `feature` 手順を適用する。
  - **SDK resource routing による上書き**: active Step の required Skill は従来の exact directory 解決を維持する。required 以外の SDK-discovered Skill は FR-TS-13 の分類対象である場合だけ `disabled_skills` から除外する。`enable_config_discovery=False` による Skill 全停止で directory 指定を無効化してはならず、Skillを利用するローカル sessionは `enable_skills=True` を明示する。
- **FR-CLI-76**: Step 実行経路のセッション生成（[hve/runner.py](hve/runner.py) `_create_session_with_auto_reasoning_fallback`）は、呼び出し側が `mcp_servers` を明示していない場合、リポジトリが宣言した `.github/.mcp.json` の `mcpServers` を `mcp_servers` として渡し、あわせて `enable_config_discovery=False` を指定しなければならない。ワークスペース / ユーザースコープ / プラグイン由来の MCP サーバを自動探索で取り込んではならない。この結果、リポジトリが宣言していない MCP サーバ（実測環境では `github-mcp-server` / `workiq` / プラグイン由来の `azure`）は Step 実行セッションから外れる。`.github/.mcp.json` が存在しない・読み取れない・`mcpServers` が dict でない・`mcpServers` が空の場合は `mcp_servers` を渡さず、`enable_config_discovery` は従来どおり `True` とする（リポジトリが MCP を宣言していない作業ディレクトリでの回帰を避けるため）。呼び出し側が `mcp_servers` または `enable_config_discovery` を明示している経路（`_require_trusted_asdw_data_deploy_mcp_servers` / `_require_trusted_foundry_mcp_servers` / `SDKConfig.mcp_servers`）の挙動は変更してはならない。**Work IQ を有効化した QA サブセッションは本要件の受入範囲に含める**（v2.41 で追加）。当該サブセッションは `mcp_servers` に `_hve_workiq` だけを明示するため従来は自動探索が残り、利用者グローバル設定のプラグインが登録する Work IQ サーバー（`workiq` / `workiq-preview`）が同一セッションへ併存していた。併存側は `tools: ["*"]` で登録されるため HVE が `_hve_workiq` へ課す最小権限 allowlist（`ask` のみ）が及ばず、書き込み系ツール（`create_entity` / `update_entity` / `delete_entity` / `do_action`）および `accept_eula` / `call_function` / `get_debug_link` が同一セッションから到達可能だった（実測: `tools: ["*"]` で公開 14 件）。`available_tools` / `excluded_tools` は既定 `None`、権限ハンドラは `PermissionHandler.approve_all` であり、FR-TS-03 が求める安全境界がどちらの手段でも張られていなかった。したがって当該サブセッションでも `.github/.mcp.json` の宣言分を `mcp_servers` へ併合したうえで `enable_config_discovery=False` を指定しなければならない。併合時は Work IQ 別名（`workiq` / `workiq-preview`）を落とし、HVE が最小権限 allowlist を課した `_hve_workiq` だけを Work IQ 経路として残さなければならない。宣言分が存在しない・読み取れない・空の場合は、`_hve_workiq` の注入だけを従来どおり行い `enable_config_discovery` は `True` のままとする（MCP を宣言していない作業ディレクトリでの回帰を避けるため。本要件の他経路と同じフォールバック規則）。FR-CLI-79 の Azure 除外は本サブセッションにも適用する。`_hve_workiq` のツール allowlist と Work IQ 別名の除外規則（FR-QA-03）は変更しない。新規 CLI オプションおよび新規 `SDKConfig` フィールドを追加してはならない。これらを除く経路では自動探索が残るが、Step 実行の主経路（各 Step のメインセッション）と Work IQ を有効化した QA サブセッションを縮約することを本要件の受入範囲とする。SDK が `enable_config_discovery` を未サポートの場合、既存規則どおり当該引数を剥がして再試行せず停止する（自動探索の再有効化を伴う縮退を禁じる既存の分離境界規則が、本要件により全 Step へ適用される）。Skill の公開範囲は FR-CLI-73 が定める `skill_directories` の明示指定で維持する。`.github/.mcp.json` の各サーバ定義は `tools` キー（`["*"]` = 全件 / `[]` = なし）を明示しなければならない。明示指定した MCP サーバ設定に `tools` キーが無いと、当該サーバは起動されずツールが 1 件も公開されない（実測: `azure` を `tools` なしで明示指定すると connected 0 件・ツール 0 件、`"tools": ["*"]` を付けると connected かつ 68 ツール。`type: "stdio"` の付与では解決しない）。同じ制約は `_require_trusted_foundry_mcp_servers` が渡す設定にも適用される。本要件は FR-TS-03 の pin ポリシー判定を変更しない（`pin_only` の判定は `hve/toolsearch/policy.json` の `step_overrides` だけで決まり、`enable_config_discovery` を参照しない）。本要件は次の実測（Copilot CLI 1.0.79 / SDK 1.0.7、`session.metadata.contextInfo`、model=`claude-sonnet-4.5`、会話 0）を根拠とする: 自動探索が有効なとき、リポジトリが宣言していないユーザースコープ設定・プラグイン由来の MCP サーバが全件接続され、ツール定義は 52,756 tokens（うち MCP 41,096）を占めた。重複していた MCP サーバ 2 系統を環境側で除いた後でも 33,384 tokens（うち MCP 21,728）だった。自動探索を無効にすると同環境で 11,403 tokens（MCP 0）になる。本要件の実装後、`.github/.mcp.json` が宣言する 2 サーバ（`azure` 68 ツール / `microsoft-learn` 3 ツール）だけを公開した Step セッションは 28,763 tokens（MCP 17,217）で、同環境の自動探索有効時 33,527 tokens（MCP 21,728）に対し 4,764 tokens 少ない。あわせて、自動探索は `.github/.mcp.json` を探索対象としておらず（探索対象は作業ディレクトリ直下の `.mcp.json` / `.vscode/mcp.json`）、同ファイル固有のサーバは 1 度も起動していない。本要件はこの「宣言が無視されている状態」の是正を兼ねる。
  - **受入範囲の上書き（v2.51）**: 上記本文末尾の「これらを除く経路では自動探索が残るが、Step 実行の主経路と Work IQ を有効化した QA サブセッションを縮約することを本要件の受入範囲とする」という限定は、本項以下で置き換える。v2.51 以降の受入範囲は、当該 2 経路に加えて [hve/orchestrator.py](hve/orchestrator.py) `_create_session_with_auto_reasoning_fallback` が生成する全セッション（Work IQ 専用 4 経路を含む）とする。受入範囲から除外したままとするのは、本文が列挙する 3 経路（`_require_trusted_asdw_data_deploy_mcp_servers` / `_require_trusted_foundry_mcp_servers` / `SDKConfig.mcp_servers`）だけである。旧記述が同じく除外していた `workiq-doctor` の tool probe は、FR-QA-03 の v2.88 上書きで `workiq-doctor` 自体を削除したため現行の経路ではない。
  - **orchestrator のセッション生成へ本要件の縮約を適用しなければならない**。当該ヘルパーは [hve/runner.py](hve/runner.py) の同名関数と別実装で、リポジトリ宣言の読み取りを行わず `enable_config_discovery` を常に `True` としていたため、ARD の `target_business` 生成・Fleet wave 親・Code Review Agent の各セッションが、利用者グローバル設定およびプラグイン由来の MCP サーバ（実測環境では Work IQ プラグインが宣言する `workiq`）を自動探索で取り込んでいた。判定と縮約の実装は [hve/runner.py](hve/runner.py) の単一のヘルパーへ寄せ、orchestrator 側で同等処理を再実装してはならない（FR-MAINT-07）。
  - orchestrator 経路では、宣言分から Work IQ 別名（FR-QA-03 が単一の正本として保持する `WORKIQ_MCP_SERVER_NAMES` の全要素）を落とさなければならない。Work IQ を使うセッションは自前で `_hve_workiq` を明示するため、宣言経由で別名が混入すると HVE の最小権限 allowlist が及ばないサーバへ到達しうる。
  - **Work IQ 専用の 4 セッション**（`_prefetch_workiq_detailed` / `_run_akm_workiq_verification` / `_run_akm_workiq_ingest` / `_run_ard_workiq_usecase`）も本要件の受入範囲に含める。これらは `mcp_servers` に `_hve_workiq` だけを明示するため従来は自動探索が残り、事前 QA サブセッションと同じ併存（`tools: ["*"]` のプラグイン由来 `workiq`）が発生していた。宣言分（Work IQ 別名を除く）を併合したうえで `enable_config_discovery=False` を指定しなければならない。宣言分が存在しない・読み取れない・空の場合は、`_hve_workiq` の注入だけを従来どおり行い `enable_config_discovery` は `True` のままとする（QA サブセッションと同じフォールバック規則）。
  - FR-CLI-79 が定める `azure` 除外規則を orchestrator 経路へも適用しなければならない。FR-CLI-79 本文は Step 実行セッションを対象に記述しているが、除外の根拠（当該 Workflow の全 Step が Azure に言及しない）は同じ Workflow に属する orchestrator セッションにも当てはまるためである。これを可能にするため、当該ヘルパーは Workflow ID を受け取れなければならない。Workflow ID が解決できない経路（Fleet wave 親 / Code Review Agent）では従来どおり全宣言サーバを渡す（FR-CLI-79 の宣言漏れ規則と同じ側へ倒すため）。
  - 宣言が存在しない・読み取れない・空の場合のフォールバック（`enable_config_discovery` を `True` のまま据え置く）は orchestrator 経路でも同一とする。
  - **知識探索による上書き（v3.38）**: Work IQ 専用の 4 セッション（事前 QA 問い合わせ、AKM 取り込み、AKM 検証、ARD use-case）と、AKM 問い合わせ・更新 session の分離（v2.97）は FR-KD-10 で廃止した。知識源を使うセッションは FR-KD-03 の知識探索セッションだけとする。事前 QA の質問票 session から知識源の MCP を外す規則は維持する。

  - **Work IQ SDK 委譲による上書き（v2.88）**: 本段落は本要件のうち Work IQ 専用 QA / orchestrator session に関する全 clauses（v2.41 / v2.51 / v2.83 の explicit `mcp_servers`、repository MCP merge、alias 除外、canonical remote 構成）を全面的に置き換える。一般 main / review / orchestrator session のリポジトリ MCP 縮約と、3つの明示 trusted MCP 経路は変更しない。Work IQ 専用 session は `mcp_servers` を渡さず、SDK の設定探索を有効にし、事前の `client.rpc.mcp.discover` で得た enabled server 名のうち exact `workiq` 以外を `disabled_mcp_servers` に指定し、`available_tools=["mcp:workiq-ask"]` だけをモデルへ公開する。旧 `_hve_workiq` と `workiq-preview` を作成・受理してはならない。session 作成後は `session.rpc.mcp.list()` と `session.rpc.mcp.list_tools(MCPListToolsRequest(server_name="workiq"))` で exact `workiq` が `connected` かつ `ask` を公開することを確認した場合だけ問い合わせ、`pending` / `needs-auth` / `failed` / `disabled` / `stopped` / `not_configured` / `ask` 欠落 / SDK API不在では OAuth や構成変更を行わず当該 Work IQ phase を警告付きでスキップする。
  - **SDK resource classification routing による上書き**: 本段落は一般 main / review / orchestrator session のリポジトリ MCP 縮約、3つの明示 trusted MCP 経路、および `.github/.mcp.json` 欠落時 fallback を置き換える。ローカル session は FR-TS-12 の snapshot と FR-TS-13 の分類から `disabled_mcp_servers` / `disabled_skills` を決定し、SDK の設定探索を有効にする。HVE が `mcp_servers` の raw設定を sessionへ複製してはならない。required Skill が MCP を必要とする場合、その Skill と exact MCP server 名の対応は `policy.json` の `required_mcp_servers_by_skill` だけから解決し、runner / orchestrator に server 名を複製してはならない。リポジトリ固有の `.toolsearch/policy.json` が存在する場合は同じ schema で bundled policy を上書きできる。Work IQ専用sessionの exact `workiq` / `ask` 検査は後方互換として維持するが、その capability は FR-TS-12 snapshot から導出する。
  - **AKM 問い合わせ・更新 session の分離（v2.97）**: AKM ingest / verification は、`available_tools=["mcp:workiq-ask"]` の問い合わせ session へ成果物更新 prompt を送ってはならない。FR-WIQ-02 を満たした後に限り、enabled MCP をすべて `disabled_mcp_servers` へ指定し、`excluded_tools=["mcp:*"]` で MCP を非公開にし、source-qualified な `builtin:view` / `builtin:edit` だけを公開する別の更新 session を使う。更新 session は resource routing と Cloud 注入を再適用して MCP を復活させてはならない。permission handler は送信中の現在 Dxx 1 件に属する `knowledge/` 直下 Markdown の read/write だけを許可し、shell、URL、MCP、別 Dxx、入れ子 path、拡張子違い、Windows alternate data stream 形式、管理対象の権限昇格、sandbox bypass、`knowledge/` root または Dxx の symlink / junction、および既存 Dxx の hard link を拒否する。scope は `send_and_wait` の直前に選択し、正常・例外を問わず直後に空へ戻し、SDK permission callback との並行実行に耐えるよう同期する。更新 session を作成できない場合も、次の Dxx 問い合わせ前の既定 interval を省略してはならない。
  - 更新・取り込み成功件数はモデル応答ではなく対象 Dxx 本文の更新前後 byte snapshot で判定する。既存集合を削除せず 1 件以上の非空 UTF-8 本文が実変更された場合、または空集合から非空 UTF-8 本文をちょうど 1 件新規作成した場合だけ成功とする。ChangeLog は問い合わせ本文・snapshot・成功判定から除外し、安全でない既存本文を読んだり更新 prompt へ含めてはならない。
  - **session resource readiness 改訂（2026-09-06）**: resource-routed な main / pre-QA / review / orchestrator session は FR-TS-13 の実効除外、初期化・接続待ち・集約 ACK、deadline / cleanup を共有し、最初の send 前に完了させる。既存の安全な event / log callback を create / resume 前に渡し、初期化・接続待ち・timeout の段階と経過時間を観測可能にする。返却後の二重 callback 登録や別の初期化を追加しない。一般 main の category / exact allowlist を Work IQ 専用 policy へ置換・拡張せず、上記 AKM 更新 session の MCP 非公開・権限・本文更新判定も維持する。
  - **事前 QA session の分離（既存契約の明確化）**: 質問票用に生成する session は `include_workiq=False` に加え、`disabled_mcp_servers` の既存除外との和集合で exact `WORKIQ_MCP_SERVER_NAME` だけを追加し、generic knowledge allowlist 経由でも同意前の Work IQ 問い合わせを許してはならない。Step の required Skills とその MCP 依存は保持し、Work IQ 専用の除外設定へ重ねてはならない。custom input を持つ Step は QA と main のモデルが同じで Work IQ が利用不可でも専用の質問票 session を使う。custom input なし・同一モデル・Work IQ 利用不可では既存の main reuse を維持し、main / review の policy、保存設定、共有 resource snapshot を変更しない。問い合わせ session は質問生成・FR-INPUT-05 の同意境界を通過した後だけ作成し、既存 SDK builder の exact Work IQ options、`required_mcp_servers=["workiq"]`、`required_skills=[]` を使い、Step Skill を継承しない。exact `workiq` が connected かつ `ask` を公開する検証後だけ問い合わせる。共有 client は借用し停止せず、所有する両 session は既存の時間制限付き cleanup で各 1 回 disconnect する。required/disabled 衝突拒否と通常 Step の必須資源検証は維持する。

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

### 5.6 旧 Session State Resume（廃止）

- **廃止（v1.1）**: GitHub Copilot CLI SDK の複数デバイス間セッション管理が不十分なため、旧 JSON `state.json` / `config_snapshot` により SDK セッションを復元する CLI / GUI の Session State Resume 機能を廃止した。以下は旧機構として削除済み:
  - 旧 `resume` サブコマンド群（`list` / `show` / `rename` / `delete` / `continue` / `reconcile` / `gc-orphans`）
  - `session-state/` 永続化（`state.json` / `config_snapshot` / `journal.jsonl` / `.lock` / `journal-archive/`）
  - 起動時 recovery（`HVE_DISABLE_STARTUP_RECOVERY`）、Ctrl+R による中断（graceful pause）
  - 旧 FR-CLI-40〜51（v0.5〜v1.0 で導入された Resume / 2 層トランザクション保護 / RunLock / RunJournal / reconciler 関連要件）
- **現行 durable resume との境界**: FR-STATE-04 / FR-STATE-05 および FR-CLI-90 が規定する SQLite durable state と公開 `hve resume` 入口は、本節の廃止対象外とする。
- **存続する機能**: SDK セッション ID の決定論的生成（`hve-<run_id>-step-<step_id>[-<suffix>]` 形式、`make_session_id`）は fork-on-retry のフォーク用 ID 再構成のために存続する（[hve/run_state.py](hve/run_state.py)）。
- **優先規則**: 旧 Session State Resume に関する改訂履歴（§11）と解消済み TBD（§12）は履歴情報であり、現行要件として適用しない。本節は廃止済み JSON 機構の境界だけを記録し、現行 durable resume は FR-STATE-04 / FR-STATE-05 および FR-CLI-90 を正とする。


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

### 5.9 起動時の索引差分更新

- **FR-CLI-77**: HVE CLI Orchestrator の起動時（`run` / `cli` / `orchestrate`）、実在する `mdq`（§3.8）および `cq`（§3.9）の索引 DB をバックグラウンドで差分更新しなければならない。
  - 対象は**実在する索引 DB に限る**。`mdq` は `.mdq/index-<lang>-<strategy>.sqlite` に一致するファイル、`cq` は設定ファイルが宣言する profile のうち `.cq/index-<profile>.sqlite` が実在するものとする。索引 DB を新規に作成してはならない。差分更新は既存索引を前提とする操作であり、未構築の strategy / profile を起動時に構築すると、利用者が選択していない索引（埋め込みモデルの取得を伴う `semantic_paragraph` 等）を起動のたびに生成することになるからである。SQLite 索引を持たない strategy（`graphrag`）は、この対象規則により自動的に対象外となる。
  - 更新は差分更新とし、完全再ビルドを行ってはならない。
  - 索引 DB のパス規則と `(lang, strategy)` / profile の解決は `mdq` / `cq` 側の実装を単一の情報源とし、HVE 側で再実装してはならない（FR-MAINT-07）。
  - 本処理の完了前に `mdq` / `cq` の watcher を起動してはならない。同一の索引 DB に対して 2 つの書き込み経路が同時に存在してはならず、`mdq` の索引構築は走査の終了時に 1 回だけコミットするため、走査中は書き込みトランザクションを保持しうるからである。
  - 索引更新の失敗、任意依存の欠落、`cq` 設定の不在は、警告の出力に留めなければならない。Workflow の実行を中断させてはならない。
  - 環境変数 `HVE_STARTUP_INDEX_REFRESH` で無効化できなければならない。既定は有効とする。
  - 索引と無関係なサブコマンド（`login` / `pricing` / `toolsearch` / `qa-merge` / `emit-prompt` / `ingest-docs`）では、起動時の索引差分更新を起動してはならない。`gui` サブコマンドと引数なし起動（GUI が既定）の経路は FR-GUI-22 が担う。CLI 側は作業ディレクトリをリポジトリルートとして扱うのに対し、GUI は起動位置からルートを遡って解決するため、引数なし起動を CLI 側で担うと誤ったルートを対象にしうる。
  - 起動時の索引差分更新は `--dry-run` でも実行してよい。索引 DB は Workflow の成果物ではないためである。既存の watcher が `dry_run` で起動しない扱いとは異なる点を、利用者向け文書へ明示しなければならない。

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
  - **SDK resource classification routing による上書き**: 固定 `azure` server 名と Azure-free allowlist による縮約は FR-TS-13 の `software-engineering` Workflow集合へ置き換える。`microsoft-learn` を特例で残す規則も同じ分類判定へ統合する。required exact MCP は分類にかかわらず残す。

### 5.12 CLI Autopilot の lane 経過時間観測

- **FR-CLI-80**: `CliAutopilotRunner` は lane（APP チェーン）ごとの経過時間を計測し、閾値を超えた lane について警告を 1 行出力しなければならない。
  - **lane を停止させてはならない**。本要件は観測のみを規定する。NFR-TIME-01 の CLI タイムアウトは**無入出力時間ベース**であり、出力が継続する限り lane は無制限に伸びうる。一方 NFR-TIME-02 のとおり Cloud 側は経過時間ベースの上限を持つ。この Cloud / CLI の差を可視化することが本要件の目的である。
  - 閾値は **360 分**とし、NFR-TIME-02 の Cloud 側ジョブタイムアウトと同値にする。**ハードコードとし、設定では変更不可**とする（NFR-PERF-02 と同じ扱い）。新規 CLI オプションおよび新規 `SDKConfig` フィールドを追加してはならない。
  - 警告は lane の完了時に 1 回だけ出力する。lane が chain 内で複数の Workflow を順次実行する場合、計測対象は最初の Workflow の起動から lane 完了までとする。
  - 警告の出力に失敗しても実行を中断してはならない（NFR-RTO-03 と同じ扱い）。
  - 警告の有無は `CliRunSummary` の内容および終了コードを変えてはならない。
  - 経過時間の取得は差し替え可能にし、実時間に依存するテストを書かずに検証できなければならない。

### 5.13 Work IQ 利用不可時の自動無効化

- **FR-CLI-81**: Work IQ を要求する設定が有効な実行で、本処理前の Work IQ 認証確認（[hve/__main__.py](hve/__main__.py) `_run_workiq_auth_preflight`）が失敗した場合、非対話環境では実行を停止してはならず、当該実行に限り Work IQ 関連設定を無効化して続行しなければならない。
  - 無効化は既存の `_disable_workiq()`（実体は [hve/workiq.py](hve/workiq.py) `disable_workiq_for_run`）を再利用し、`workiq` / `workiq_enabled`、`knowledge_sources` 中の `workiq`、`params` の `sources` に含まれる `workiq` トークン・`ard_workiq_enabled` を対象とする（v3.38: 削除した `workiq_qa_enabled` / `workiq_akm_review_enabled` / `workiq_akm_ingest_enabled` / `workiq_draft_mode` / `workiq_akm_ingest_dxx` は対象から外した。FR-KD-10）。同等処理を新規に実装してはならない（FR-MAINT-07）。
  - 無効化した場合は、Work IQ を要求した設定名を 1 行で通知しなければならない。通知は既存の非対話失敗時の出力（`_workiq_request_reasons()` の列挙）を再利用し、新しい UI・新しい出力経路を追加してはならない。
  - **v2.83以降**は対話可否にかかわらず無効化確認の質問を追加せず、非Work IQ処理を続行する。旧版の「対話端末では無効化可否を質問する」挙動は、GUI子processと直接CLIで結果が分かれるため廃止した。
  - `--dry-run` の場合、および Work IQ を要求する設定が 1 つも有効でない場合に認証確認を実行してはならない（従来どおり）。
  - 新規 CLI オプション・新規 `SDKConfig` フィールド・新規環境変数を追加してはならない。
  - 本要件が保証するのは認証確認の実行時点までとする。確認を通過した後に認証が失効した場合は、従来どおり実行中の警告（FR-QA-06）に委ねる。
  - 本要件は次の 2 点を根拠とする。(1) GUI が起動する HVE サブプロセスの標準入力は対話不能であるため（FR-GUI-23）、Work IQ を要求する設定が 1 つでも有効なとき認証失敗が常に実行停止になっていた。(2) `--workiq-draft` は `workiq_enabled` と `workiq_qa_enabled` を同時に有効化するため（[hve/__main__.py](hve/__main__.py) `_build_config`）、利用者が Work IQ を無効にしたつもりでも停止しうる。
  - **SDK discovery による上書き（v2.88）**: 本段落は上記の「認証確認」「live auth」「auth-failed」に関する clauses を置き換える。Work IQ が実効要求され、`dry_run` でない場合に限り、実行前に FR-CLI-91 の SDK discovery snapshot を取得する。`not-configured` / `unverified` の場合は対話可否にかかわらず質問を追加せず、共通 normalizer で当該実行の Work IQ 値だけを無効化して非 Work IQ 処理を続行する。AKM の実効 source が 0 件になる場合は FR-CLI-13 に従い開始しない。保存済み設定を OFF へ書き換えてはならない。discovery が `ready` になった後の接続・認証・tool 公開の失敗は設定値を再正規化せず、各 Work IQ phase が FR-CLI-76 に従って警告付きでスキップする。
  - **知識探索による上書き（v3.38）**: 実行単位の無効化の対象は、`workiq_enabled`、`knowledge_sources` 中の `workiq`、`params` の `sources` 中の `workiq`、`ard_workiq_enabled` とする（FR-KD-10 で削除した field は対象から外す）。`workiq` 以外の知識源の利用不可は FR-KD-02 の除外で扱う。

### 5.14 ローカル起動時の設定整合性 preflight

- **FR-CLI-82**: HVE のローカル起動面（CLI 非対話、CLI 対話 wizard、GUI Plan、GUI / CLI Autopilot）は、GitHub への書き込みを伴う Workflow を開始する前に、GitHub 連携設定の整合性を単一実装で検査しなければならない。
  - 対象は `--create-issues` / `--create-pr`、ADFDV で `enable_auto_merge` が有効な Workflow 全体、およびその他の Workflow で `enable_auto_merge` が有効かつ active step に `requires_remote_cicd=True` の宣言がある実行とする。この対象判定は `--dry-run` の有無で変えてはならない。GitHub への書き込みを行わない通常のローカル実行へ GitHub token・remote 接続を要求してはならない。
  - 検査項目は、`repo` が非空の `owner/repo` 形式であること、`GH_TOKEN` または `GITHUB_TOKEN` が解決できること、`base_branch` が Git branch 名として有効であること、Git remote `origin` が解決できること、および `origin` に完全一致する `refs/heads/<base_branch>` が実在することとする。
  - remote branch の実在確認は読み取り専用の `git ls-remote --exit-code --heads origin refs/heads/<base_branch>` を Python の引数リストかつ `shell=False` で実行し、status `2`（一致 ref なし）とその他の非 0（remote・認証・通信等により検証不能）を区別して報告する。branch 名は 1 件だけを完全な ref として渡し、glob による複数 ref 検査を行わない。Git の対話認証を起動してはならない。
  - 不整合は判定可能な全件を 1 回で報告し、`main`・ローカル branch・GitHub の既定 branch へ暗黙に補正してはならない。remote branch が存在しない場合も `_git_checkout_new_branch` のローカル branch fallback へ進めず fail-closed とする。
  - active step を解決した直後、dry-run 計画の構築・表示より前に検査し、最初の Copilot Agent session 作成、モデル呼び出し、branch 作成および DAG 実行より前に完了しなければならない。`--dry-run` も設定充足性の確認手段として同じ検査を行う。
  - CLI / GUI は、Workflow と active step から対象を決める処理、および repo / token / branch / remote を検査する処理を 1 つの共通関数へ集約し、各起動面へ条件判定を複製してはならない（FR-MAINT-07）。同関数は呼び出し側が指定する `check_remote` に応じてローカル判定だけ、または remote 判定を含む結果を返す。GUI Step 1 precheck はネットワーク待ちを UI thread へ持ち込まないよう `check_remote=False` の結果を表示し、remote branch の実在確認は GUI が起動する `hve orchestrate` 子プロセスが同じ関数を `check_remote=True` で呼び出して担う。
  - `additional_prompt` その他の Prompt 自由記述欄は内容検査の対象外とする（`workiq_prompt_qa` / `workiq_prompt_km` は v3.38 で削除した。FR-KD-10）。既存の型変換・引数伝搬は維持するが、自然言語の妥当性、空欄可否、業務内容を本 preflight で判定してはならない。
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
  - non-terminal/failed/risk ありの instance は `reuse-session` / `restart-step` / cancel の明示 action を要求する。Main phase だけ `reuse-session` または `restart-step` を許可し、Pre-QA/Review その他の phase は `restart-step` だけを許可する。non-TTY で action 不足の場合は child・SDK・model を開始してはならない。
  - `reuse-session` は保存済み session IDを SDK call 前に commit 済みであることを確認し、`resume_session(..., continue_pending_work=False)` を使用して固定 recovery promptを新しい turn として送る。`continue_pending_work=True` を使用してはならない。`session.resume` が active/in-use を報告した場合は disconnect して停止する。失敗時に `restart-step`へ silent fallbackしてはならない。
  - **v3.41 明確化（reuse-session の control deadline）**: `reuse-session` の `_RUNNER_RESUME_EVENT_TIMEOUT_SECONDS`（60 秒。FR-TS-13 の resource route 適用の共有 60 秒と揃える）の deadline は、SDK resource 探索（`discover_sdk_resources`、MCP 接続を含む）の完了後、`resume_session` RPC を発行する直前に開始しなければならない。探索で期限を使い切ると RPC の発行前に `TimeoutError` となり `reuse-session` が成立しない（システムテスト N-02）。deadline の残り時間は、RPC coroutine を生成する前に判定しなければならない（期限切れで未 await の coroutine を残さない）。deadline の残りは `session.resume` event の待機と resource route 適用で共有する従来の規則を維持する。deadline の長さは、実 SDK（Copilot CLI 同梱 runtime）の `resume_session` RPC が単体で約 5.2 秒かかり（2026-10-02 実測、`session.resume` event は同時刻）、HVE が resource policy の option を付けるとさらに長くなるため、従来の 5 秒を 60 秒へ改めた。出典: 同結果 N-02（2026-10-02）。受入テスト: `hve/tests/test_runner_resume.py::test_resume_deadline_starts_after_slow_resource_discovery`、`::test_resume_expired_deadline_never_creates_an_unawaited_rpc_coroutine`。
  - status だけを更新する DAG callback が `phase` / `phase_state` / `session_id` を省略しても、commit 済みの Main checkpoint metadata を消去してはならない。v3.21 で legacy runtime split-fork を撤去したため、`split-fork` phase を checkpoint として記録してはならない。
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
  - **session resource readiness 改訂（2026-09-06）**: `reuse-session` でも `resume_session` より前に FR-TS-13 の caller / route 除外の和集合と required 衝突を解決し、新規作成と同じ discovery / Skill / tool filter 設定を渡す。取得後は同じ実効集合による runtime 検証と集約 ACK を recovery prompt より前に完了する。SDK が `disabled_skills=[]` を resume wire payload から省略する既知の挙動を踏まえ、kwargs に空リストを渡しただけで保存済み無効化を解除できたと主張してはならない。実 wire と required Skill の runtime 有効性を確認し、成立しなければ disk 状態を保持して停止する。raw RPC / SDK 改造や silent restart で回避せず、既存 resident MCP の起動済み副作用を取り消せたとも主張しない。

### 5.17 Wave 境界の承認ゲート

- **FR-CLI-87**: `orchestrate` は `--approval-gates` を受け取り、有効なときに限り、`StepDef.approval_gate` を宣言した Step を含む Wave の実行開始前に利用者へ承認を求めなければならない。既定は無効とし、無効時は一切の確認を出してはならない。
  - 承認は同期とする。標準入力が対話可能でない実行（非対話 CLI、GUI が起動する子プロセス〈FR-GUI-23〉、Cloud）では確認を出さず、当該 run を `blocked` として停止しなければならない。無人実行を承認なしで続行させないためである。
  - 拒否および非対話での停止は、`run_workflow` の戻り値へ `blocked` と `error` を設定して返さなければならない。独自のキー集合で返してはならない（終了コード判定が `blocked` / `error` / `failed` を参照するため）。
  - 承認要求は既存の `on_wave_start` フック経由で行い、[hve/dag_executor.py](hve/dag_executor.py) へ新規のフックを追加してはならない（FR-MAINT-07）。同フックの汎用例外握り潰しからは承認拒否の例外だけを除外する。
  - 承認・拒否の記録は FR-STATE-04 の進捗ストアへ `approval-<wave_index>` を step_id として残し、承認者名・自由記述・prompt 本文を保存してはならない（NFR-SEC-01 / FR-RTO-04）。
  - **GUI からの承認は本項の対象外とする**。FR-GUI-23 が GUI の子プロセスの標準入力を対話不能と定めているため、同期の標準入力プロンプトは成立しない。GUI で承認を行うには FR-QA-03 の `qa_answer_mode="gui-file"` と同種の IPC 経路が必要であり、別要件として扱う。
  - 新規の環境変数を追加してはならない。
  - 契約テスト: [hve/tests/test_approval_gate.py](hve/tests/test_approval_gate.py)

### 5.18 PR / Issue の参照経路

- **FR-CLI-88**: Pull Request および Issue（障害記録を含む）を Agent セッションから参照する場合、その経路は、GitHub Copilot CLI / SDK に登録済みで FR-TS-12 が発見し、FR-TS-13 が対象 Workflow の exact allowlistへ許可した MCP tool に限らなければならない。HVE は `.github/.mcp.json` または raw MCP configを保持してはならない。
  - GitHub API 上のデータを `mdq` の索引ルート（FR-MDQ-02）または `cq` の索引対象（FR-CQ-01）へ追加してはならない。両者はワークツリー上のファイルだけを索引する契約である。
  - `knowledge_tool_allowlists` へ `*`、または作成・更新・削除・マージ・クローズ・push・ラベル付与等の状態変更toolを含めてはならない。HVEはtool名から参照可否を実行時に推測せず、policyへ明示されたbare exact tool名だけをFR-TS-13のruntime照合へ渡す。
  - 具体的なサーバー名・tool名は利用者環境とGitHubの提供形態に依存するため本書では確定しない。Step の required Skill が要求する server 名も runner の定数にはせず、FR-TS-13 の `required_mcp_servers_by_skill` で環境ごとに宣言する。optional resourceが未登録・未分類・allowlist空の場合は公開せず、required resourceとして宣言された場合はFR-TS-13に従いfail-closedとする。
  - 契約テスト: [hve/tests/test_mcp_declaration_contract.py](hve/tests/test_mcp_declaration_contract.py)、[hve/tests/test_mcp_config_removal.py](hve/tests/test_mcp_config_removal.py)、[hve/tests/test_sdk_resource_routing.py](hve/tests/test_sdk_resource_routing.py)

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
  - **v3.39 明確化**: `goal` は任意 field とする。省略時は空文字列 `""` として扱い、値は前後の空白・改行を含めて変更しない。`goal` が空文字列のとき、子 `orchestrate` の argv に `--additional-prompt` を付けない（Workflow 既定の指示だけで実行する）。文字列以外（配列・数値・`null` など）は fail-closed で拒否する。例: `{"schema_version":1,"workflows":[{"workflow_id":"aas"}]}` → 受理し、計画の `goal` は `""`、argv に `--additional-prompt` は無い。`{"schema_version":1,"goal":null,"workflows":[{"workflow_id":"aas"}]}` → 非 0 で拒否。出典: システムテスト結果 [tests/system-test/20261001-2111-Prompt-offline-plan-gate-result.md](tests/system-test/20261001-2111-Prompt-offline-plan-gate-result.md) O-01 と既存契約テスト `test_goal_is_optional`。
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
  - **v3.41 明確化（値の選択を任された場合）**: 利用者が「適当な APP-ID」のように値の選択を任せても、APP-ID を指定したことにはならない。Skill は `hve/workflow_registry.py` の定数（例: ASDW-WEB Step 1.3 だけに固定された `ASDW_DATA_DEPLOY_SUPPORTED_APP_ID`）や過去の例示の APP-ID を、確認なしに採用・使用可能な値として提示してはならず、利用者に APP-ID を選んでもらう質問を返す（request / plan / run は作らない。システムテスト N-08）。受入テスト: `hve/tests/test_systemtest_20261002_fixes.py::test_prompt_edition_skill_forbids_adopting_registry_constant_as_app_id`。
  - 利用者文書（[users-guide/hve-prompt-getting-started.md](users-guide/hve-prompt-getting-started.md) と [users-guide/prompts/](users-guide/prompts/)）は、[hve/workflow_registry.py](hve/workflow_registry.py) が定義する全 Workflow について、Product Manager がコピーできる Markdown Prompt 例を最低 1 件ずつ持たなければならない。複数 Workflow 横断の例と、非 canonical 入力名の例を含める。
  - 各例は「plan を先に提示し、明示承認前に run しない」ことを明記しなければならない。
  - 利用者は自然言語だけで計画取得から実行までを完了できなければならない。`hve prompt plan` / `hve prompt run` の起動、request path の受け渡し、plan SHA-256 の転記はすべて Agent が代行し、Skill も利用者文書もこれらの入力を利用者へ求めてはならない。貼り付け用 Prompt 例の本文へ CLI サブコマンド名を含めてはならない。
  - 承認は自然言語で受け取る。Skill は承認語の網羅列挙を持たず、明確な実行意思だけを承認とみなし、曖昧な同意は承認とせず再確認する。ただし FR-PROMPT-04 の `--expected-sha256` 一致ゲートを緩和してはならない。
  - Prompt 版の承認前に提示する実行計画と、承認後に各 Step が必要に応じて作成する `plan.md` は別の計画層として扱う。前者を提示して利用者の明示承認を得るまでは `hve prompt run` を起動してはならない。提示済み計画への明示承認を得た後、Prompt Edition controller は提示された SHA-256 を `--expected-sha256` へ渡して `hve prompt run` を起動する。HVE が現在の request・設定・HEAD から再計算した SHA-256 との一致を確認した場合だけ、既存 `orchestrate` へ委譲する。controller が単独実行モードであっても、計画の規模や分割の有無を理由にこの委譲を禁止してはならない（FR-PLAN-01）。この例外が許可するのは既存 `orchestrate` への委譲だけであり、controller が対象成果物を直接実装・編集してはならない。
  - 委譲は FR-PROMPT-01 の既存子プロセス経路を用い、直接 `orchestrate` を起動した場合と同じ argv と制約を適用する。FR-DAG-06 / FR-DAG-08 の事前検査、FR-CLI-87 の Wave 承認、および FR-WF-OUT-01 の成果物ゲートを Prompt 版専用の分岐で省略してはならない。各 Step は必要な `plan.md` を作成してよいが、`plan.md` / `subissues.md` だけで終了せず、選択済み Step の宣言 `output_paths` を実行完了時点で存在させなければならない。FR-WF-OUT-01 は存在ゲートであり、実行前から存在した成果物が今回更新されたことまでは証明しない。完全実行の範囲は選択済み Workflow / Step の成功または最初の失敗までとし、未選択 Workflow の暗黙追加、rollback、失敗後の継続を含めてはならない。Prompt 版の承認を、既存の認証・権限・Azure・QA・デプロイ承認ゲートの代替として扱ってはならない。
  - 利用者文書に Prompt 件数などの変動値を固定記述してはならない。正本または確認方法へ誘導する。
  - 契約テスト: [hve/tests/test_prompt_edition_docs_contract.py](hve/tests/test_prompt_edition_docs_contract.py)
- **FR-PROMPT-11**: Prompt 版の durable resume は request v1 を変更せず、repository Agent Skill が FR-CLI-90 の共通 resume plan を取得・提示・承認後実行する controller として提供しなければならない。
  - **v3.39 明確化**: 「request v1 を変更しない」とは、resume の制御値（`execution_id`、`resume_plan_hash`、instance ID、state version、recovery action など）を request v1 の field として受理しないことを指す。これらを含む request は未知 field として非 0 で拒否する（FR-PROMPT-02）。resume 以外の要件で追加された field は本要件の違反ではない。v3.39 時点の request v1 の top-level field は `schema_version` / `goal` / `workflows` / `settings_overrides` / `execution_policy`（FR-PROMPT-13、省略時は `None`）の 5 件とし、parse 結果の field もこの 5 件・この順とする。
  - Skill は利用者の自然言語から execution/action/replay不足値だけを解決し、Python 側へ自然言語 parser を追加してはならない。利用者へ command、request path、execution hash の転記を求めてはならない。
  - 承認前は実行せず、提示済み `resume_plan_hash` と再計算値が一致し、expected state version の lease CAS が成功した場合だけ既存 `orchestrate` child 経路へ委譲する。stale の場合は child を起動せずplanを再提示し、再承認を求める。
  - normal Prompt run は既存 SHA-256 approval 合格後かつ最初の child 前に全 Workflow instance を 1 transaction で登録し、全 childへ同じ execution IDと各instance IDを internal argsで渡す。既存fail-fastとrequest v1 schemaを変更しない。
  - normal Prompt run は child の終了コード 0 だけで成功を推測せず、対応する durable Workflow instance が `succeeded` または `skipped` へ commit 済みであることを確認してから後続 child へ進む。状態欠落・非終端状態・read failure は非 0 で停止する。
  - 契約テスト: [hve/tests/test_prompt_resume_contract.py](hve/tests/test_prompt_resume_contract.py)、[hve/tests/test_prompt_execution.py](hve/tests/test_prompt_execution.py)

- **FR-PROMPT-12**: Prompt 版は、保存済み設定または request の Workflow parameter が Work IQ を要求する場合、計画構築時に FR-CLI-91 の SDK discovery capability を適用しなければならない。live auth、OAuth、browser、model問い合わせ、Work IQ queryを計画構築の一部として実行してはならない。
  - **SDK resource snapshot による上書き**: Work IQ capability は Prompt 計画ごとに1回取得する FR-TS-12 snapshot から導出する。Plugin / MCP / Skill kindごとに別probeを追加してはならない。既存のWork IQ無効化・notice・hash再承認契約は維持する。分類 metadata の編集、Plugin / MCP / Skill のinstall / enable / config / auth、session作成、queryを計画構築中に行ってはならない。
  - Work IQ capability は1計画につき1つのauthoritative discovery snapshotとして取得し、Work IQを要求する全 Workflowへ同じ判定を適用する。計画内でWorkflowごとに独立probeを行って異なるreasonを混在させてはならない。
  - capability が `ready` にならない場合、各 Workflow の実効 `OrchestrateArgs` から全ての残存 `--workiq*` 値と `sources` の `workiq` を同じ共通 normalizer で除去し、Work IQ session・Plugin / MCP install / enable / config / auth を実行してはならない。非 Work IQ source が残る Workflow はその source だけで計画してよい。AKM の source が 0 件になる場合は子 `orchestrate` を起動せず停止する。
  - 計画出力は影響を受ける Workflow ID と、authoritative snapshot の `not-configured` / `unverified` の単一reason codeだけを、`<!-- workiq-disabled: workflows=<昇順カンマ区切り>; reason=<reason-code> -->` の HTML comment 1 件として含める。raw SDK payload、stderr、認証情報を含めてはならず、同じ内容の可視 Markdown 警告を追加してはならない。
  - SHA-256 は無効化後の最終 argv を対象とし、warning comment 自体は hash 入力に含めない。`prompt run` は同じ discovery 判定を再実行し、ready → unavailable と unavailable → ready の両方向で最終 argv が変わる場合は既存 FR-PROMPT-04 の hash 不一致として停止し、再 plan・再承認を要求する。runtime の接続・認証状態は plan hash の入力にしない。
  - repository Agent Skill は warning comment を保持して利用者へ提示するだけとし、Plugin / MCP の自動導入・構成変更・認証・別 runtime への fallback を行ってはならない。
  - 契約テスト: [hve/tests/test_prompt_workiq_capability.py](hve/tests/test_prompt_workiq_capability.py)、[hve/tests/test_prompt_execution.py](hve/tests/test_prompt_execution.py)、[hve/tests/test_prompt_cli.py](hve/tests/test_prompt_cli.py)
  - **知識探索による上書き（v3.38）**: 除去する値は `--workiq`、`--knowledge-source` 中の `workiq`、`sources` 中の `workiq`、`ard_workiq_enabled` とする（FR-KD-10 で削除した `--workiq-*` option は計画にも現れない）。
- **FR-PROMPT-13**: **優先度 MUST。** request v1 は任意の top-level field `execution_policy` を受理し、利用者が最初の依頼で宣言した事前承認の範囲を計画・実行へ渡さなければならない（FR-E2E-01）。省略時は従来の request・argv・plan hash を変えてはならない。
  - `execution_policy` の field は `unattended`（bool、既定 false）、`pre_approved_operations`（固定 allowlist `azure_deploy` の配列）、`allow_public_exposure`（bool、既定 false）、`budget_note`（200 文字以内、改行・制御文字を含まない文字列。記録とモデルへの伝達だけに使い、課金の上限として強制しない）に限る。未知 field、型不一致、allowlist 外の操作は FR-PROMPT-02 と同じく fail-closed で拒否する。
  - `pre_approved_operations` に `azure_deploy` を含む場合、選択した Workflow のうち `resource_group` parameter を宣言するものが 1 件以上あり、その全件で `params.resource_group` が空でないことを要求し、満たさなければ計画を提示せず非 0 で終了する。デプロイの事前承認はこの `resource_group` の範囲に限る。
  - 宣言は各 `orchestrate` 子プロセスの argv へ非公開の replay-only 引数（`--unattended`、`--pre-approved-operation`、`--allow-public-exposure`、`--budget-note`）として付加し、argv と canonical plan JSON の `execution_policy` の両方で plan hash（FR-PROMPT-05）の入力にする。`prompt plan` の提示には宣言範囲を表示する（FR-PROMPT-03）。
  - 4 つの replay-only 引数は durable 登録（`ResumeService.sanitize_argv`、FR-STATE-04 / FR-CLI-90）で拒否されてはならない。`--unattended`・`--allow-public-exposure` は真偽値、`--pre-approved-operation` は固定列挙値として保存し、自由記述の `--budget-note` は保存せず `budget_note` の key-only replay gap とする（NFR-SEC-01）。
  - `workflows[].params.resource_group` は、値が空でない限り Azure のリソースグループ名の規則（英数字・`-`・`_`・`.`・`(`・`)`、1〜90 文字。`hve.runner` の `_RESOURCE_GROUP_RE` と同一）に従わなければならず、違反は計画を提示せず非 0 で終了する。計画に表示する承認範囲と、モデルへ渡る宣言範囲を一致させるためである。
  - `unattended=true` の子では、FR-CLI-102 の無人実行の指示へ宣言範囲（事前承認した操作、`resource_group`、外部公開の可否、予算の注記）を差し込む。差し込む値はモデルへ渡す前に長さと文字種を検証し、不正な値は未宣言として扱う。宣言が無いときは従来の指示のままとする。
  - SHA-256 の一致検査（FR-PROMPT-04 / 05）と「自然言語の承認だけで書き込みを始めない」は変えない。利用者の最初の依頼が `execution_policy.unattended=true` を明示し、計画の提示後に確認を待たずに実行することを求めている場合に限り、repository Agent Skill はその宣言を当該計画への明示承認として扱い、提示した SHA-256 で `hve prompt run` へ進んでよい。計画が stale になった場合は再計画・再提示し、事前承認として扱わない。宣言範囲外の破壊的・不可逆・課金・外部公開の操作は無人実行でも停止の対象とする（FR-E2E-01）。
  - 出典: 利用者依頼（2026-09-30）で指定された `work/202609301045-DAGReviewPlan.md` N3-1。計画で仮称とした「FR-PROMPT-07」は既存 ID と衝突するため本 ID とした。
  - 契約テスト: [hve/tests/test_prompt_request.py](hve/tests/test_prompt_request.py)、[hve/tests/test_prompt_execution.py](hve/tests/test_prompt_execution.py)、[hve/tests/test_runner_output_continuation.py](hve/tests/test_runner_output_continuation.py)、[hve/tests/test_main.py](hve/tests/test_main.py)

### 5.21 ローカル 3 面の設定パリティ

本節は、直接 `orchestrate` CLI・GUI Orchestrator・Prompt 版（§5.20）の 3 つの**ローカル**利用面に対して、利用者が指定できる設定の同一性を規定する。Cloud Agent Orchestrator は Issue Form を入口とする別経路であり、本節の対象に含めない（Cloud との対応は FR-CLOUD-10 / FR-CLOUD-11 と `hve/tests/fixtures/option_parity_matrix.yaml` が扱う）。

- **FR-LOCAL-SURFACE-01**: ローカル 3 面のパリティは「同じ利用者意図が、同じ正規化済み値として `orchestrate` へ到達すること」と定義する。CLI フラグ名の字面一致を求めてはならない。各設定は次の 5 分類のいずれか 1 つに属し、分類ごとに以下の契約を満たさなければならない。
  - **(a) shared setting**: 3 面すべてで指定できる。GUI は [hve/gui/settings_store.py](hve/gui/settings_store.py) `defaults()` へ既定値を持ち、[hve/gui/settings_apply.py](hve/gui/settings_apply.py) `_SECTION_FIELDS` で widget と対応付けて永続化する。  Prompt 版は保存値を基準値とし（FR-PROMPT-07）、`ALLOWED_SETTINGS_OVERRIDES` の key として run 単位で上書きできる。CLI は同義のフラグを持つ。対象は次の 29 key とし、`ALLOWED_SETTINGS_OVERRIDES` と過不足なく一致しなければならない（FR-PROMPT-02）。
    - 実行品質: `model` / `review_model` / `qa_model` / `akm_model` / `reasoning_effort` / `review_reasoning_effort` / `qa_reasoning_effort` / `akm_reasoning_effort` / `context_tier` / `akm_context_tier`
    - 実行制御: `max_parallel` / `timeout` / `review_timeout` / `auto_qa` / `auto_contents_review` / `verbosity` / `branch` / `strict`
      - 知識源（v3.42、FR-KD-14）: `workiq` / `knowledge_sources`
    - Agentic Retrieval / Toolbox: `enable_agentic_retrieval` / `agentic_data_source_modes` / `foundry_mcp_integration` / `agentic_data_sources_hint` / `agentic_existing_design_diff_only` / `foundry_sku_fallback_policy` / `enable_tool_search`
    - SDK Tool Search: `tool_search_defer_threshold`（FR-MODEL-04。保存値 `0` は「未指定」として CLI へ渡さず SDK 既定へ委譲する）
    - Cloud Session: `cloud_session_branch`（保存 key は `cloud_session_repository_branch`）
  - shared setting の集合は 1 箇所で定義し、面ごとに別集合を持ってはならない。一致は機械検査しなければならない。
  - 同一 Workflow と、両面で表現可能な同一の保存済み設定を入力し、Prompt request の run 単位上書き・Step・goal・入力別名、および GUI セッション固有値（QA / Steering IPC、Hub の Issue 関連付け、Cloud Session の Step 単位上書き、Autopilot の APP lane）を指定しない場合、GUI は `settings_apply.apply_to_widgets()` 後の `OptionsPage.build_args_for_workflow()`、Prompt 版は `args_from_settings()` からそれぞれ `OrchestrateArgs.to_argv()` へ到達し、生成する argv 配列の要素数・順序・値が完全一致しなければならない。GUI 専用の `qa_answer_mode=user` は比較対象外とする。実効値が同じであっても、面ごとに不要な既定値フラグを追加・省略して差分を残してはならない。
  - **(b) workflow param**: [hve/workflow_registry.py](hve/workflow_registry.py) の `WorkflowDef.params` が宣言した Workflow 固有値。CLI フラグ、Prompt request の `workflows[].params`、および当該 Workflow を選択した GUI 画面から指定できなければならない。値は宣言した Workflow にだけ適用し、GUI の全体設定へ永続化してはならない。対象は、`WorkflowDef.params` のうち Workflow 固有の入力経路（GUI の必須入力欄〈FR-GUI-02 / FR-GUI-03 / FR-GUI-06〉、対話 wizard の固有入力）が扱わない `create_remote_mcp_server` / `tdd_max_retries` の 2 key とする（[hve/orchestrator.py](hve/orchestrator.py) `_PROJECTED_WORKFLOW_PARAMS`）。それ以外の `WorkflowDef.params`（`resource_group` などの必須入力キー）は既存の固有入力経路に従い、FR-GUI-03 / FR-GUI-06 が定める `[options]` への永続化を妨げない。
  - **(c) semantic alias**: 同じ実行状態へ到達する別表現を持つもの。面ごとに入口が異なってよいが、解決後の実行状態は一致しなければならない。`include_kpi_okr` は FR-PARAM-10 に従い Step 選択を唯一の推奨状態とし、CLI `--include-kpi-okr` と Prompt の `params` は後方互換の入口として維持する。GUI へ重複する可視状態を追加してはならない。
  - **(d) derived**: 他の設定から一意に導出する値。重複入力欄を設けてはならない。Cloud Session の repository owner / name は `repo`（`owner/repo`）から導出する。
  - **(e) excluded**: 意図的に面固有とするもの。除外は根拠となる要件または実装上の制約を伴わなければならない。Workbench 表示系（GUI / Prompt は `--workbench off` を強制注入する）、GUI 固有 IPC（`qa_ipc_dir` / `steering_ipc_dir`）、対話専用（`force_interactive`、および FR-CLI-87 の `--approval-gates`）、GUI 入力欄を禁止した ASDW-WEB Step 1.3 の `data_*`（FR-WF-ASDW-02 / FR-GUI-02）、Autopilot チェーン、`_OBSOLETE_KEYS` 登録済みの旧 GUI 設定、およびコンソール出力の表示制御（`--verbose` / `--quiet` / `--show-stream` / `--log-level` / `--no-color` / `--banner` / `--screen-reader` / `--timestamp-style`）を除外とする。HVE 自身の SDK セッション設定 `tool_search` / `tool_search_ranking`（FR-MODEL-04 / FR-TS-01 / FR-GUI-07）も除外とする。これらは GUI 設定画面が単一の所有者として保存し、GUI は `OptionsPage.build_args_for_workflow()`、Prompt 版は `args_from_settings()` を通じて保存値から同じ CLI 引数へ到達させるが、Prompt request の run 単位上書き（`ALLOWED_SETTINGS_OVERRIDES`）には含めない。入力別名（`input_aliases`）は FR-PROMPT-08 の非 canonical 入力を request で扱う Prompt 版と直接 CLI の実行時機能であり、GUI へ重複する入力欄を追加しない。ただし `OrchestrateArgs` と `to_argv()` の既存受け口は維持する。コンソール出力の表示制御は `OrchestrateArgs` に存在するが GUI 設定ストアへ永続化しておらず、実行結果の意味論を変えないため、本節では面固有のままとする。
  - 優先順位は、shared setting が「Prompt `settings_overrides` > 保存済み GUI 設定 > 既定値」、workflow param が「明示指定 > 既定値」とする。`tdd_max_retries` は既存の環境変数経路を維持し「CLI 明示 > `HVE_TDD_MAX_RETRIES` > 5」とする。本節のために新しい環境変数を追加してはならない。
  - shared setting と workflow param の解決には、新しい設定レジストリ・シリアライザ・抽象レイヤーを導入してはならない。既存の [hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py) `OrchestrateArgs` を CLI argv への唯一の変換器として再利用する（FR-MAINT-07）。
  - 分類の網羅性は機械検査しなければならない。`orchestrate` の全 CLI 引数は `OrchestrateArgs` のフィールド、明示した別名、または理由付きの除外リストのいずれかへ分類されていなければならず、未分類が残ってはならない。
  - controller が child `orchestrate` へ渡す非公開 `dest` は、利用者設定の 5 分類とは別に `orchestrate_cli_internal_dests` へ登録する。FR-CLI-90 の durable identity（`_execution_id` / `_instance_id` / `_expected_state_version` / `_recovery_action` / `_lease_owner` / `_lease_generation` / `_unattended`）はその必須部分集合とし、それ以外の controller-only 内部引数の追加を禁止しない。durable identity のテストは内部分類全体との完全一致を要求してはならない。
  - 契約テスト: [hve/tests/test_local_surface_option_parity.py](hve/tests/test_local_surface_option_parity.py)、[hve/tests/test_resume_cli.py](hve/tests/test_resume_cli.py) `TestHiddenDurableIdentity.test_internal_destinations_are_declared_in_option_parity`
- **FR-LOCAL-SURFACE-02**: CLI / GUI Plan / Prompt の durable resume は、candidate・risk reason・許可 action・missing replay keys・resume plan hash・lease CAS・ordered execution を同じ ResumeService から取得しなければならない。
  - GUI と Prompt は独自の candidate scan、risk判定、output gate、lease判定を実装してはならない。表示・入力・child launchだけを面固有責務とする。
  - GUI Plan は Start 操作ごとに queue 全体を 1 executionとして登録し、全 childへ同じ execution IDを渡す。新しい Resume dialog は execution ID、Workflow、last state、heartbeat、risk、missing replay keysを表示し、safe executionは1回の確認、riskありはaction選択後に開始する。
  - GUIの承認後実行はdialogが選択したplan hashと再入力値を`hve resume` childへ渡し、同childが再計算・CAS・fenced token付き`orchestrate`起動を行う。GUIが承認済み`ResumePlan.argv`を直接`orchestrate`として起動し、hash再検証またはlease取得を迂回してはならない。
  - Prompt は FR-PROMPT-11、CLIは FR-CLI-90 に従う。3面で同じsnapshotを入力したとき、正規化済みplanの意味とhashが一致しなければならない。
  - 契約テスト: [hve/tests/test_resume_surface_parity.py](hve/tests/test_resume_surface_parity.py)

### 5.22 ローカル起動時の HVE バージョン整合性

- **FR-LOCAL-SURFACE-03**: HVE のローカル最上位起動（`hve.cmd` / `hve.sh` が委譲する `python -m hve`、直接の `python -m hve`、および `hve` console script）は、リポジトリ同梱 `.venv` への正規化後かつ通常の CLI / GUI dispatch より前に、Python distribution metadata のインストール済み `hve` 版と、現在 checkout されている [pyproject.toml](pyproject.toml) `[project].version` を比較しなければならない。本リポジトリは PyPI 公開を行わず `git pull` 済み checkout を `pip install -e .` で構成する配布形態であるため、後者を当該起動で利用可能な最新 HVE 版とする。起動時に Git fetch / pull、GitHub API、PyPI、Git tag または Release を問い合わせてはならない。
  - 実プロセスの各最上位入口は、バージョン確認のメッセージを出力する前に標準出力・標準エラーを UTF-8（変換不能文字は置換）へ構成しなければならない。`hve` console script は重い `hve.__main__` の import より前にこの構成を行い、Windows の pipe / redirect でも日本語の警告を cp932 bytes として出力してはならない。stdio 構成は軽量 bootstrap の単一実装とする（FR-MAINT-07）。
  - 両版が有効な `MAJOR.MINOR.PATCH`（各成分は ASCII 10 進数字で、`0` または先頭 `0` なし）で、インストール済み版が checkout 版より古い場合、標準入力が TTY なら「現在インストールされているバージョンは`<installed>`です。最新の`<source>`のバージョンにアップグレードしますか? [y/N]:」と表示する。`y` / `yes` は更新、`n` / `no` / 空入力は更新せず元の起動を継続し、それ以外は同じ質問を再表示する。
  - `yes` の場合だけ、Windows は PowerShell 7+ から [hve/setup-hve.ps1](hve/setup-hve.ps1)、macOS / Linux は [hve/setup-hve.sh](hve/setup-hve.sh) の既存通常セットアップを起動する。Windows の [hve/setup-hve.cmd](hve/setup-hve.cmd) は無引数時に結果表示用の `pause` を行う対話ランチャーであるため、本自動起動では `pwsh.exe` から `.ps1` を直接実行する。`pwsh.exe` を解決できない場合は setup と元コマンドを起動せず、既存 `.cmd` の手動実行を案内して非 0 で終了する。コマンドは引数配列かつ shell を介さず、checkout root を作業ディレクトリとして実行し、セットアップ固有の確認を暗黙承認する `-Yes` / `--yes` を付与してはならない。新しい setup モードを追加してはならない。
  - セットアップが終了コード 0 を返した後に distribution metadata を再取得し、checkout 版との完全一致を確認した場合だけ、元の HVE argv を同じ `.venv` Python で 1 回再起動する。セットアップ失敗、版の再取得失敗、または再取得版の不一致では元のコマンドを開始せず、理由を表示して非 0 で終了する。
  - 標準入力が TTY でない場合は自動更新せず、インストール済み版と checkout 版の両方を含む不一致警告を表示して元の起動を継続する。Windows の `NUL` は C runtime の `isatty()` が真を返す場合でも対話可能な console input とみなさず、同じ非 TTY 分岐を適用する。インストール済み版が checkout 版より新しい場合も両版を表示し、自動 downgrade せず警告して継続する。
  - distribution metadata が存在しない場合、TTY では「HVE のインストール済みバージョンを確認できません。最新の`<source>`のバージョンをセットアップしますか? [y/N]:」と表示する。`y` / `yes` は前項と同じ setup・版再取得・元 argv の 1 回再起動へ進み、`n` / `no` / 空入力は setup を起動せず現在の起動を継続し、それ以外は同じ質問を再表示する。非 TTY では metadata を確認できない旨と checkout 版を警告して継続する。setup 失敗・metadata 再取得失敗・更新後不一致は前項と同じく元コマンドを開始せず非 0 とする。source 版を取得・解釈できない場合は版を捏造せず警告して継続する。
  - 判定・メッセージ・setup argv・再起動制御は PySide6 に依存しない単一実装とし、CLI / GUI / Prompt / launcher ごとに複製してはならない（FR-MAINT-07）。同一 process tree では本機能専用の内部 marker により最上位起動の 1 回だけ確認し、更新後の再起動および HVE が起動する子プロセスで再質問してはならない。既存の `HVE_NO_VENV_REEXEC` の意味と公開済みオプトアウト挙動は変更せず、本機能専用 marker を利用者向け設定として公開してはならない。
  - 本要件のために新しい公開 CLI オプション、GUI 設定、永続設定、外部依存、定期確認、GUI 専用ダイアログを追加してはならない。`main(argv)` をライブラリまたはテストから直接呼ぶ経路では暗黙に setup を起動せず、実プロセスの entrypoint だけを対象とする。
  - 契約テスト: [hve/tests/test_startup_version.py](hve/tests/test_startup_version.py)、[hve/tests/test_venv_reexec.py](hve/tests/test_venv_reexec.py)

### 5.23 ローカル起動時の Work IQ SDK discovery capability

- **FR-CLI-91**: HVE のローカル GUI、CLI wizard、直接 `orchestrate`、Prompt 版は、Work IQ を選択可能にする前または保存済み / request 設定の Work IQ を実行する前に、GitHub Copilot SDK の MCP discovery を唯一の外部状態源として Work IQ capability を確認しなければならない。
  - 判定は既存の Copilot SDK client factoryで client を開始し、対象 repository を `working_directory` とする `client.rpc.mcp.discover(MCPDiscoverRequest(...))` を1回呼ぶ。モデル session、prompt送信、Work IQ query、CLI subprocessによるPlugin / MCP一覧取得を行ってはならない。clientは成功・失敗を問わず停止する。
  - discovery が返す effective resource に exact name `workiq` かつ `enabled=True` の MCP server が存在する場合だけ `ready` とする。source kindは判定条件にせず、利用者がCopilot CLIへ設定したPlugin / user / workspace MCPをそのまま受理する。`workiq-preview`、`_hve_workiq`、部分一致、URL / command / source metadataからの意味推定を代替として受理してはならない。
  - exact `workiq` が不在またはdisabledだけの場合は `not-configured`、SDK import・client start・discover・response schemaの検証に失敗した場合は、不在と捏造せず `unverified` とする。raw SDK payload、transport、command、URL、args、env、header、credentialを capability に保持またはログ出力してはならない。
  - static discovery はGUI / wizardの選択肢制御のためapplication processの起動時に1回実行し、MainWindowの再表示・追加・設定画面の開閉では再実行しない。同じprocess内でCopilot CLI側の設定を変更した場合はprocess再起動後に反映する。直接`orchestrate`とPrompt childは別processとしてauthoritative discoveryを再実行する。disk cache、daemon、watcher、定期再確認を追加してはならない。
  - `ready`は設定の存在だけを表し、認証済み・接続済み・`ask`公開済みを意味しない。Work IQ専用sessionはFR-CLI-76のSDK自動探索隔離を使用し、`session.rpc.mcp.list()`と`session.rpc.mcp.list_tools(MCPListToolsRequest(server_name="workiq"))`でexact `workiq`が`connected`かつ`ask`を公開する場合だけqueryを開始する。それ以外ではHVEがOAuth login、browser起動、token確認、Plugin / MCP構成変更、EULA承認を行わず、Copilot CLIで事前設定・認証するよう警告して当該phaseをskipする。
  - unavailable時の共通normalizerは保存値を変更せず、その実行のWork IQ enable値、Dxx、draft出力先、QA/KM Prompt override、質問単位timeout、AKM `sources`の`workiq`を除去する。除去後に認識可能な非Work IQ sourceが0件なら、不明tokenを既定sourceへ読み替えず開始を拒否する。normalizerはWork IQ session作成前に1回適用し、GUI / CLI / Promptごとに同じ無効化ロジックを複製してはならない（FR-MAINT-07）。
  - HVE-ownedのtenant override、MCP request timeout、Review prompt、`workiq-doctor`、Plugin自動install / enable / configure / authを公開してはならない。新しい公開CLI option、GUI setting、環境変数、外部依存を追加してはならない。
  - 契約テスト: [hve/tests/test_workiq_plugin_capability.py](hve/tests/test_workiq_plugin_capability.py)、[hve/tests/test_workiq_startup_entrypoints.py](hve/tests/test_workiq_startup_entrypoints.py)（`hve/tests/test_workiq_plugin_runtime.py` は v3.38 で削除。runtime 検査は FR-KD-03 の [hve/tests/test_knowledge_discovery.py](hve/tests/test_knowledge_discovery.py) が担う）
  - **汎用 snapshot への互換化**: Work IQ専用の独立 discovery / cache は FR-TS-12 の process snapshot から exact `workiq` の enabled状態を射影する互換adapterへ置き換える。Work IQだけの別client start / `mcp.discover` を行ってはならない。既存の保存値無変更、run単位無効化、exact `workiq` / `ask` runtime検査、問い合わせ結果schemaは1リリース維持する。
  - **session resource readiness 改訂（2026-09-06）**: snapshot の `ready` と runtime の connected は引き続き別の判定とする。Work IQ の実行時検査も FR-TS-13 の初期化後の bounded readiness を共有し、初期化の正常復帰だけでは `ask` の公開・利用可能性を認定しない。期限内の `pending` から connected への遷移は再確認できる（`needs-auth` は FR-TS-13 の 2026-09-24 改訂により再確認せず失敗分岐へ送る）が、schema 不正・exact 名重複・未知 status は成功にしない。失敗は同要件の required / optional / caller filter 分岐へ渡し、deadline 枯渇・cancel を通常の optional 継続へ降格しない。独自の初期化・追加待機予算・auth / config 操作を設けず、既存の exact identity、結果 schema、consumer ごとの既存例外を維持する。FR-TS-12 の 15 秒 inventory と Prompt plan の MCP 初期化・接続禁止は変更しない。
  - **知識探索による上書き（v3.38）**: exact `workiq` の capability 判定と実行単位の無効化は維持する。`ready` 後の runtime 検査（`connected` と tool の公開）は FR-KD-02 の汎用判定で行い、`ask` の公開だけを条件にしない。「新しい公開 CLI option、GUI setting、環境変数を追加してはならない」は、FR-KD-01 の `--knowledge-source`、`HVE_KNOWLEDGE_SOURCES`、GUI の知識源欄に限り適用しない。normalizer が除去する Dxx・draft 出力先・QA / KM Prompt override・質問単位 timeout は FR-KD-10 で削除した。

### 5.24 OS-only 環境からの1操作起動

- **FR-LOCAL-SURFACE-04**: HVE は、private な配布 ZIP を取得して書き込み可能なローカルディレクトリへ展開した利用者が、Windows では ZIP 直下の `Start-HVE.cmd`、macOS では ZIP 直下の `Start-HVE.command` を **1 回起動するだけ**で、HVE GUI を表示できなければならない。本要件の「1操作」は当該トップレベルランチャーの起動を指し、private ZIP の取得・展開、OS が直接表示する UAC / `sudo` / Command Line Tools / Gatekeeper の確認、および GUI 表示後に利用者が明示的に行う GitHub CLI / GitHub Copilot の認証は操作数に含めない。認証を拒否または未完了のままでも FR-GUI-24 に従い GUI の表示を妨げてはならない。
  - トップレベルランチャーの起動を、当該 private ZIP に含まれる HVE と既定の通常 GUI 構成を導入する 1 回の明示同意として扱う。既存 setup の個別 tool 確認は `-Yes` / `--yes` により非対話化し、前項が列挙した OS 自身の確認と GUI 表示後の認証以外に、HVE 独自の追加確認を挟んではならない。この一括同意は初回 bootstrap にだけ適用し、FR-LOCAL-SURFACE-03 の版不一致更新経路へ `-Yes` / `--yes` を付与してはならない。
  - 初期対象は Windows 11 x64、および Apple Silicon 上の macOS 15 / 26 とする。初回セットアップはインターネット接続を前提とする。Intel Mac、Windows ARM64、Windows 10、macOS 14 以下、完全オフライン、proxy / private mirror、公開匿名配布は本要件の対象外とし、対応済みと表示してはならない。
  - private ZIP は HVE の実行に必要な source、`.github/prompts/**`、`.github/skills/**`、`.github/io-contracts/**`、`template/**`、GUI assets、OS 別 setup / launcher、license、および source version / commit を再現する manifest を allowlist で収集する。`.git/**`、`.venv/**`、`.env`、資格情報、利用者設定、索引 DB、`work/**`、ログ、および生成アプリケーションの実データを含めてはならない。配布 ZIP を公開 Release にしてはならず、現 repository の visibility を変更してはならない。
  - 最上位ランチャーは、Python、Git、GitHub CLI、PowerShell 7、Homebrew、Node.js、Azure CLI、ShellCheck、外部 Copilot CLI、および HVE `.venv` が未導入の開始状態を扱う。Windows は `cmd.exe` と OS 標準の native command だけで PowerShell 7+ を解決する段階を完了するまで `.ps1` を起動せず、Windows PowerShell 5.1 へフォールバックしてはならない。macOS は shell profile の事前設定を要求せず、Homebrew / Command Line Tools が未導入の場合は OS が所有する確認を利用者へ表示して同じ起動チェーンを継続する。資格情報・管理者 password を標準出力、ログ、ファイル、または子プロセス引数へ保存してはならない。
  - OS 前提の解決後は既存 [hve/setup-hve.ps1](hve/setup-hve.ps1) / [hve/setup-hve.sh](hve/setup-hve.sh) の通常 GUI setup を再利用し、同等の Python extras、SDK runtime、外部 Copilot CLI、gh、PTY、翻訳、preview asset の導入を別実装へ複製してはならない（FR-MAINT-07）。グローバル Python の既存 HVE は削除せず、setup の既存 `NoGlobalCleanup` 経路を使用する。ZIP 経路では展開 root の [pyproject.toml](pyproject.toml) を FR-LOCAL-SURFACE-03 の source root として扱い、同要件の版比較・再起動制御を維持する一方、`.git` の存在、`git pull`、GitHub API、PyPI、Git tag または Release の問い合わせを要求してはならない。既存の Git checkout 経路の source root と更新規則は変更しない。
  - setup を実行した初回または修復時は、当該 setup の終了コード 0 と、配布先 `.venv` の Python 3.11 以上、`hve` / `mdq` / `cq` の配布先からの import、`pip check`、PySide6 / QtWebEngine、gh、OS 別 PTY、PowerShell 7（Windows）、SDK が pin する Copilot runtime、外部 Copilot CLI、および配布 manifest の必須ファイルを共通の起動前検証で確認した場合だけ、既存 `hve.cmd gui` / `hve.sh gui` と同じ GUI entrypoint を 1 回起動する。setup を実行しない 2 回目以降は、過去の setup 終了コードを保存・参照せず、列挙した起動前検証の現在結果だけで判定する。外部 Copilot CLI の解決は [hve/gui/copilot_cli_bridge.py](hve/gui/copilot_cli_bridge.py) の既存規則を再利用し、認証済みであることは要求しない。`.venv` の存在、`CheckOnly` の終了コード 0、Python import の一部成功、または子プロセス生成だけを GUI 起動可能の根拠としてはならない。必須検証の失敗時は GUI を起動せず、失敗段階と復旧可能な理由を表示して非 0 で終了する。
  - 2 回目以降は同じトップレベルランチャーを使用する。前項の必須検証に合格する構築済み環境では package manager、setup、依存更新を再実行せず GUI を起動する。不完全な初回処理は利用者所有の source・設定・成果物を削除または上書きせず、同じランチャーの再実行で再開可能にする。HVE が所有する `.venv`、一時 download、および生成途中ファイルは、既存 setup の検証付き修復または再生成の範囲で置換してよい。新しい updater、daemon、常駐 service、registry 設定、定期更新、永続設定、公開 CLI option、汎用 validation framework を追加してはならない。
  - setup は Git repository の初期化、remote 設定、fetch / pull、commit / push、Issue / Pull Request / Release の作成、HVE Workflow の実行、Azure resource 操作、MCP / Plugin の認証または構成変更を行ってはならない。GUI 表示後の既存利用者操作へ委ねる。本要件は「GUI が起動すること」と「認証・入力・外部権限を要する Workflow が実行できること」を別の受入条件として扱う。
  - 受入確認は、(1) package manager / download / subprocess を隔離した決定的テスト、(2) 開発 checkout を import path から除外した配布 ZIP 検査、(3) Windows native GUI と GitHub-hosted macOS の Cocoa smoke、(4) 開発ツール未導入の実環境で private ZIP の実取得経路から起動する clean-OS test、の 4 層とする。(4) は `Windows 11 x64`、`macOS 15 arm64`、`macOS 26 arm64` の 3 セルを持つ受入マトリクスとし、各セルへ OS build、architecture、配布 version / SHA-256、および結果を記録する。未実施または失敗したセルは個別に未完了とし、別セルの成功から推測で補ってはならない。GitHub-hosted macOS runner は Python / Homebrew / Xcode 等を事前導入済みであるため (4) の代替としてはならない。実 clean macOS 環境を利用できない場合は該当 macOS セルを未完了と明記する。macOS runner の実行は FR-MAINT-10 の費用見積り・特定 run 1 回の承認を維持する。
  - インストーラー、単体 exe / `.app` bundle、code signing / notarization、Smart App Control / Gatekeeper の無警告保証は将来事項とする。OS の保護を無効化して受入を合格にしてはならない。単体実行ファイルが必要になった場合は、実測に基づく別要件または ADR を先に定義する。

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
- **FR-PARAM-21**: `adfd` / `adfdv` では「データバッチ処理 / バッチ」アーキテクチャに合致する APP-ID を自動選択する（[hve/app_arch_filter.py](hve/app_arch_filter.py) `resolve_app_arch_scope`）。

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
- **FR-GUI-02**: GUI のパラメータ要件（FR-GUI-01 の 2 系統目）の必須入力キー集合は `StepDef.required_params`（FR-DAG-07）から導出する。GUI 側で `required_params` の必須キーを二重管理してはならない。FR-GUI-01 のファイル要件表（`REQUIREMENT_TABLE`）が持つ `required_info_keys` は Step の前提情報を示す別系統であり、FR-GUI-06 が両者の和集合を入力欄の対象とする。
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
  - **SDK resource routing 拡張**: GUI は `tool_search_defer_threshold`（未指定 = SDK既定）を編集でき、FR-TS-11 の OFF / ON 比較を明示操作で実行できなければならない。現在環境の削減率は比較結果だけから表示し、過去実測や推定値で埋めてはならない。Resource分類編集は FR-GUI-53 が担い、同じ表を本タブへ複製してはならない。
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
  - **v3.40 明確化**: SDK の `metadata.context_info` は、セッションが未初期化（最初のターン前でシステムプロンプトとツール情報が未キャッシュ）のとき null を返す（実測: Copilot SDK 同梱の runtime で `aas` Step 1 が再現）。上の「`session.send` を行わない」制約と両立しないため、null のときは非 0 で終了し、原因（未初期化のためモデル呼び出しを送らない）を示す診断を表示する。推定値で埋めたり、課金されるメッセージを送ったりしてはならない。runtime が未初期化でも内訳を返す版へ更新された場合は、そのまま実測値を表示する。出典: システムテスト結果 F-04（同上）。
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

- **FR-GUI-20**: GUI の設定画面「一般」カテゴリは、旧「自動プロンプト」ノードを廃止し、`基本設定` / `QA (質問票)` / `レビュー` / `Knowledge Management` を含むノード構成へ再編しなければならない。
  - `追加プロンプト` と `コンテキスト最大文字数` は `基本設定` へ移す。`QA (質問票)` は `auto_qa` / `qa_answer_mode`、`レビュー` は `auto_contents_review` / `auto_coding_agent_review` / `auto_coding_agent_review_auto_approval`、`Knowledge Management` は `qa_akm_background_merge` / `akm_model` / `akm_reasoning_effort` / `akm_context_tier` を持つ。自己改善（Self-Improve）機能は削除済みであり、保存済み設定の `self_improve*` キーは読み込み時に廃止キーとして削除する。
  - FR-QA-05 の `qa_akm_background_merge` は、設定画面の `Knowledge Management` ノードと Step 1 右ペインの「共通設定」枠の双方へ表示し、既定は無効（チェックなし）としなければならない。設定画面内で同一項目を複数ノードへ重複表示してはならない。
  - Step 1 右ペインの「共通設定」枠は、`QA (質問票) 自動投入` → `QA (質問票) 回答モード` → `qa_akm_background_merge` → `Knowledge Management 用モデル` → `Knowledge Management 用コンテキスト階層` → `追加プロンプト` の順で表示しなければならない。
  - 利用者が略語の意味を判別できるよう、GUI の表示ラベルと説明文では `QA` を `QA (質問票)`、`AKM` を `Knowledge Management` と表記しなければならない。CLI のフラグ名（`--akm-model` 等）と設定キー名は互換性のため改称してはならない。
  - FR-GUI-03 / FR-GUI-06 の対象となる必須入力は設定ストアへ永続化し、次回起動時に復元する。run-scoped Step 入力は永続化しない。右ペインへ独自の保存経路を追加してはならない。

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

- **FR-GUI-29**: GUI の QA 回答ダイアログ（[hve/gui/qa_answer_dialog.py](hve/gui/qa_answer_dialog.py)）は、表示中の質問票をクリップボードへ複製する操作を 1 つ提供しなければならない。クリップボードへの書き込みだけを行い、MCP ツール呼び出し・外部送信を行ってはならない。（v3.38）Work IQ 用プロンプトを複製する 2 つ目の操作は、Work IQ 専用の固定 Prompt を FR-KD-10 で削除したため廃止した。
  - 質問票の文字列は [hve/qa_merger.py](hve/qa_merger.py) `QAMerger.render_merged` の出力とする。GUI 側で別の整形実装を持ってはならない（FR-MAINT-07）。当該メソッドは未回答の `user_answer` を空欄として出力するため、ダイアログで入力途中の回答は含まれない。
  - 操作は [hve/gui/copy_button.py](hve/gui/copy_button.py) `CopyButton` をラベル併記の表示形式で使い、支援技術向けの名前を付与しなければならない。`CopyButton` 自体の既定の表示形式を変更してはならない。
  - コピー対象の文字列を組み立てる処理は例外を送出してはならない。`CopyButton` はクリック時の例外を捕捉してエラー文字列をクリップボードへ書き込むため、利用者が当該文字列を貼り付け先へ送る経路を作らないためである。
  - 質問が 0 件の場合、操作を無効化しなければならない。
  - 本要件のために新規の CLI オプション・設定項目・環境変数・IPC スキーマ変更を追加してはならない。既存の回答送信（`Submit`）・キャンセル・既定値採用の各シグナルと、GUI ↔ CLI の回答形式（FR-GUI-08）を変更してはならない。

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

### 6.18 GUI 起動時の Work IQ SDK discovery capability

- **FR-GUI-51**: HVE GUI は FR-CLI-91 の SDK discovery capability を GUI process につき1回、GUI thread を阻害しない worker で確認し、結果を全 MainWindow と後から開く設定画面へ共有しなければならない。
  - workerはGUI表示直後かつblocking GitHub認証dialogより前に開始する。workerの起動自体が失敗した場合はin-progress flagとthread参照を解除し、`unverified`として完了させる。完了したworkerはglobal参照を解放して`deleteLater()`を予約し、GUI終了時は有界waitで回収する。同じ回収境界へ実行中のC7再列挙workerも含める。
  - 判定中はWorkflow開始操作とWork IQ入力を無効化し、確認中である理由を表示する。判定中に設定画面を開いた場合も、そのWork IQ入力を初期状態から無効にする。判定完了後、C4 Work IQセクション、AKMの`sources_workiq`、QA回答ダイアログの「Work IQ用プロンプトをコピー」は表示したまま、`ready`でない場合は操作不能にする。保存済み値をuncheckまたはOFFとして永続化してはならない。
  - 保存値が有効のまま実効無効化された場合、C4の状態表示は「保存設定: 有効 / この起動: 無効」と`not-configured`または`unverified`を併記し、設定が反映されたように見える無通知状態を作ってはならない。argv構築時はFR-CLI-91の共通normalizerを適用する。
  - HVE-ownedのlive auth worker、認証確認ボタン、認証再試行signal、browser flowを持ってはならない。`ready`は設定有無の表示にだけ用い、認証はCopilot CLI側で事前に完了させる。Copilot CLI側の設定・認証を変更した後はGUI processを再起動してsnapshotを更新する。
  - 追加MainWindow、設定画面の遅延生成、GUIが起動する`orchestrate` childのいずれも判定前のWork IQ値で実行を開始してはならない。childは親のin-memory判定を信用せずFR-CLI-91のauthoritative discoveryを再実行する。
  - C7の一般MCP / Plugin手動再列挙はWork IQ runtime判定とは別機能として維持し、GUI thread外で実行する。取得失敗を「登録0件」と表示してはならない。
  - 契約テスト: [hve/gui/tests/test_app_startup_workiq.py](hve/gui/tests/test_app_startup_workiq.py)、[hve/gui/tests/test_qa_answer_dialog.py](hve/gui/tests/test_qa_answer_dialog.py)
  - **汎用 snapshot への上書き**: worker は FR-TS-12 の Plugin / MCP / Skill snapshot を1回取得して共有し、Work IQ状態は同じsnapshotから導出する。C7のCLI subprocessによるPlugin / MCP再列挙は廃止し、利用者の明示再列挙も同じSDK実装へ委譲する。Plugin / MCP / Skill kindごとの別worker、別cache、CLI subprocess fallbackを追加してはならない。
  - **知識探索による上書き（v3.38）**: C4 セクションの入力は「Work IQ を有効化」と「知識源 MCP サーバー」（FR-KD-01）だけとする。判定中・`ready` でない場合に操作不能にするのは「Work IQ を有効化」と AKM の `sources_workiq` とし、「知識源 MCP サーバー」欄は FR-KD-02 の実行時判定に委ねて常に編集可能とする。QA 回答ダイアログの「Work IQ用プロンプトをコピー」は FR-GUI-29 の改訂で削除した。

- **FR-GUI-53**: GUI の設定画面は FR-TS-12 の resource snapshot と FR-TS-13 の分類 metadata を同じ「Tool-Search」セクション内で管理できなければならない。
  - Resource表は kind、exact name、SDK source kind、Plugin marketplace、提供元Plugin、enabled、effective category、個別分類を表示する。取得失敗kindは「未確認」と表示し0件へ変換しない。path、direct source ID、raw config、URL、command、header、credential、例外本文を表示してはならない。
  - 利用者が編集できるのは個別分類と `knowledge_tool_allowlists` / `software_engineering_tool_allowlists` のexact tool名だけとし、保存先は画面に表示した FR-TS-03 の `policy.json` とする。Plugin / MCP / Skill のinstall / update / enable / disable / config / auth、OAuth、browser、認証手順実行ボタンを提供してはならない。
  - 保存は既存 `ToolSearchPolicy.save()` の検証・未知トップレベルキー保持・LF/BOM契約を再利用する。分類表だけの別設定ファイル、GUI専用schema、provider別widgetを追加してはならない。変更は次に開始するlocal sessionから反映し、実行中sessionを更新したと表示してはならない。
  - Plugin分類は提供元がSDK応答で確認できるMCP / Skillの既定値であり、Pluginのhook / agent / instruction全体をsession単位で無効化する制御ではない旨を表示する。Cloud Sessionは未対応と表示する。

### 6.19 GUI 起動時の利用可能モデル一覧更新

- **FR-GUI-52**: HVE GUI の通常起動は、[hve/gui/app.py](hve/gui/app.py) `_open_first_window()` が初回 `MainWindow` を生成して `win.show()` を呼んだ後、同関数から既存の「利用できるモデルの取得」を実装する [hve/gui/main_window.py](hve/gui/main_window.py) `MainWindow._on_login_clicked()` メソッド全体を、キャッシュの有無や鮮度にかかわらず1回だけ直接呼び出し、利用者が使用できるモデル一覧をバックグラウンドで取得しなければならない。
  - 起動側は `MainWindow._on_login_clicked()` の呼び出しだけを行う。SDK `list_models()`、worker、キャッシュ保存、選択肢更新、失敗通知は、既存の [hve/models_api.py](hve/models_api.py) `fetch_model_entries()`、[hve/models_cache.py](hve/models_cache.py) `save_entries()`、および `MainWindow._on_models_fetched()` へ至る同メソッド内の経路をそのまま再利用し、同等処理を起動側へ再実装してはならない（FR-MAINT-07）。
  - `win.show()` より前に取得を開始してはならず、初回ウィンドウの表示をモデル一覧取得の完了待ちで阻害してはならない。非空の一覧を取得した場合は既存経路でキャッシュとモデル選択欄を更新する。取得失敗または空結果の場合は既存キャッシュと選択欄を維持し、既存処理と同じ警告またはステータス表示を使用して GUI プロセスの起動自体は継続する。`save_entries()` は一時ファイルからの `os.replace()` で既存キャッシュを原子的に置換するため、その呼び出し前に `models_cache.clear()` で既存キャッシュを削除してはならない。
  - worker の `start()` 自体が失敗した場合も取得失敗として処理し、例外を通常 GUI 起動へ伝播させてはならない。worker 参照と取得中表示を解除し、ステータスバーと表示中の設定画面にある同名ボタンを再試行可能な状態へ戻す。
  - 1つの `MainWindow` では同時に1件のモデル取得だけを許可する。取得中はステータスバーと設定画面の両ボタンを無効化し、取得中に設定画面を開いた場合も無効状態を引き継ぐ。直接またはシグナル経由の重複要求は新しいworkerを生成してはならない。
  - 完了したモデル取得workerは保持参照を解除して `deleteLater()` を予約する。取得中にウィンドウを閉じる操作を受けた場合は、実行中 `QThread` を破棄せず完了後にcloseを再実行し、`QThread: Destroyed while thread is still running` によるプロセス異常終了を起こしてはならない。
  - SDK取得timeout後の `CopilotClient.stop()` も既存SDK cleanup境界と同じ5秒で打ち切り、worker完了と延期中closeを無期限に阻害してはならない。
  - close延期中も取得結果のcache／選択欄反映は完了させ、後続の実行中セッション終了確認でcloseが拒否された場合に結果を失ってはならない。close拒否後はwindowを再有効化し、「取得完了後に終了します」の一時statusを残さない。
  - モデル取得の開始・完了・失敗statusは、索引差分更新中、Work IQ起動確認中、またはWorkflow実行中のstatusを上書きしてはならない。警告ダイアログと両取得ボタンの再有効化は維持する。
  - `save_entries()` は同一cacheへ複数writerが到達しても共有一時パスを使わず、writerごとの一時ファイルから原子的に置換する。置換失敗時は既存cacheを維持し、そのwriterの一時ファイルを残置しない。
  - 非空結果のモデル選択欄再読込は各surfaceを独立に試行し、1つのsurfaceの例外で後続surfaceの更新をスキップしてはならない。
  - 自動取得は通常起動の初回 `MainWindow` だけを対象とする。「新規セッション」で追加する `MainWindow` と `--autopilot-child` は `_open_first_window()` を通らないため自動取得してはならない。GUI プロセスを起動しない `python -m hve run` / `python -m hve cli`、直接 `python -m hve orchestrate ...`、Prompt 版も対象外とする。手動の「利用できるモデルの取得」ボタンは再取得手段として維持する。
  - 本要件のために新しい設定、CLI オプション、環境変数、キャッシュ形式、取得 API、抽象レイヤー、外部依存を追加してはならない。
  - 契約テスト: [hve/gui/tests/test_app_startup_models.py](hve/gui/tests/test_app_startup_models.py)、[hve/gui/tests/test_i18n.py](hve/gui/tests/test_i18n.py)、[hve/tests/test_models_api.py](hve/tests/test_models_api.py)、[hve/tests/test_models_cache.py](hve/tests/test_models_cache.py)

---

## 7. 非機能要件

| ID | 要件 |
|---|---|
| NFR-PERF-01 | DAG 実行は `asyncio.Semaphore` を使い、FR-DAG-03 の解決順序で得た並列上限（宣言値: AKM / ADI は 21、ARD は 15、ASDW-WEB は 1。宣言のない Workflow は `--max-parallel` の値で既定 15）を超えない。ただし ASDW-WEB の宣言 1 は、FR-IDL-02 の所有範囲が重ならない fan-out の子に限り `ownership_parallel`（`asdw-web` = 4）まで緩める（FR-DAG-03） |
| NFR-PERF-02 | 既存成果物走査は `src/` 50 件、`test/` 30 件で早期打ち切る。**ハードコード値であり、設定では変更不可** |
| NFR-PERF-03 | 性能の測定方法 / 目標値（KPI、SLA）は未定義（§12 TBD）|
| NFR-OBS-01 | Wave 2 コンテキスト注入計測（`none_steps` / `total_chars` / `max_chars` / `phase_breakdown`）を Console / stderr に出力する。`GITHUB_STEP_SUMMARY` 環境変数が設定されている場合に限りサマリにも出力。`OSError` 時は警告のみで継続 |
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
- **TDD**: `tdd_max_retries`
- **知識源**: `workiq_enabled` / `knowledge_sources`（FR-KD-01）。v3.38 で `workiq_qa_enabled` / `workiq_akm_review_enabled` / `workiq_akm_ingest_enabled` / `workiq_akm_ingest_dxx` / `workiq_draft_mode` / `workiq_draft_output_dir` / `workiq_prompt_qa` / `workiq_prompt_km` / `workiq_per_question_timeout` / `workiq_max_draft_questions` / `workiq_priority_filter` を削除した（FR-KD-10）。tenant override / MCP request timeout / Review prompt は保持しない
- **コンソール出力**: `verbose` / `quiet` / `show_stream` / `show_reasoning` / `log_level` / `verbosity` / `no_color` / `show_banner` / `screen_reader` / `timestamp_style` / `final_only`
- **Agentic Retrieval**: `enable_agentic_retrieval` / `agentic_data_source_modes` / `foundry_mcp_integration` / `agentic_data_sources_hint` / `agentic_existing_design_diff_only` / `foundry_sku_fallback_policy`
- **Fork / 実行セッション**: `fork_on_retry`、`run_id`、`session_id_prefix`、`apply_qa_improvements_to_main` / `apply_review_improvements_to_main`、`unattended`、`dry_run`、`additional_prompt`

完全なフィールド一覧は [hve/config.py](hve/config.py) `SDKConfig` クラス定義を正とする。Resume 用 snapshot とその復元契約は §5.6 のとおり廃止済みである。

### 8.3 セッション永続化フォーマット（廃止）

- v1.1 で `state.json` / `.lock` / Resume 用 `journal.jsonl` / `session-state/` を含むセッション永続化フォーマットを全廃した。これら旧形式の現行スキーマは存在しない。現行の durable state（`state.sqlite3`）は別機構であり、FR-STATE-04 / FR-STATE-05 が定める。
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

改訂履歴は [hve-dev/requirement-definition-history.md](hve-dev/requirement-definition-history.md) に置く（§1.3 の「3. 履歴情報」）。

---

## 12. 未確定事項（TBD）

| TBD No. | 内容 | 確認方法 |
|---|---|---|
| TBD-01 | ~~リポジトリの確定 commit SHA~~ → **解消（v1.0.4）**: §1.4 に `48326f3ea5fa55b65c262a4eb6e0cccea261bd6f` を記録済み | `git rev-parse HEAD` |
| TBD-02 | ~~`SDKConfig` dataclass の完全フィールド一覧~~ → **解消（v1.0.4、v1.1 追随）**: §8.2 に主要フィールドを列挙し、完全リストは [hve/config.py](hve/config.py) `SDKConfig` クラス定義を正とする。旧 `_SAFE_CONFIG_FIELDS` と snapshot 復元は Resume 全廃に伴い削除済み | `hve/config.py` 全文確認 |
| TBD-03 | ~~ADR-0002 / ADR-0003 のファイルパス~~ → **解消（v1.0.4、履歴）**: 2026-05-12 の確認時点では `docs/decisions/` 配下に `docs/decisions/ADR-0001-agentic-retrieval-prerequisites.md` のみ存在し、ADR-0002 / ADR-0003 は未作成だった。2026-09-05 現在、`docs/decisions/` は存在しない | `docs/decisions/` 配下を検索 |
| TBD-04 | ~~`users-guide/*.md` 各リンクの実在~~ → **解消（v1.0.4）**: `users-guide/hve-cli-orchestrator-guide.md` / `users-guide/web-ui-guide.md` / `users-guide/km-guide.md` を含む§10 参照リンクはすべて実在を確認済み | ファイル存在確認 |
| TBD-05 | 各 FR への個別受入基準の付与 → **保留（v1.0.4 時点でイスケジュー化推奨）**: 現状の FR は文章記述で、Given/When/Then 展開はテストとのトレーサビリティ表を設ける導入コストが大きい（当初の例示だった FR-CLI-44〜51 は v1.1 の Resume 全廃で削除済み）。個別 FR 改訂時に小さく始める方針としたい | 次版で Given/When/Then 形式に展開 |
| TBD-06 | ~~Cloud Orchestrator の ARD 対応有無の確定~~ → **解消（v2.96 訂正）**: **ARD は CLI / GUI / Cloud Orchestrator の 3 面対応として確定**している（FR-WF-ARD-01）。v1.6 時点の 2 面限定という結論と根拠は、現行 Cloud 対応により失効した | 完了（追加作業なし） |
| TBD-07 | ~~AKM 以外の reusable workflow における `check_qa_skip` 同等チェックの有無~~ → **解消（v1.0.4、v2.16 改訂）**: `auto-knowledge-management-reusable.yml` / `auto-dataflow-dev-reusable.yml` / `auto-dataflow-design-reusable.yml` / `auto-app-selection-reusable.yml` / `auto-app-documentation-reusable.yml` / `auto-app-dev-microservice-web-reusable.yml` を含む主要 reusable workflow に `check_qa_skip` ジョブが存在する。旧記述では廃止した旧独立原本質問票処理を事前 QA 常時スキップの例外としていたが、FR-QA-03 / FR-CLOUD-24 により当該例外を廃止し、専用 Cloud 経路も同じ回答保存経路へ統合する | 各 `auto-*-reusable.yml` を確認 |
| TBD-08 | 外部 IF 要件 / データ要件 / エラー処理要件セクションの拡充 → **次版の大規模拡張 / 保留**: Resume 2 層トランザクション保護を扱った旧版では「ソース逆抽出で説明できる範囲」だけをカバーしていた。IF / データ / エラー処理を体系的に拡充するには Cloud / CLI 両方での実況検証が必要 | 次版で追加 |
| TBD-09 | 性能 KPI / SLA の数値目標 → **運用データ蓄積後 / 保留**: NFR-PERF-01〜03 は「上限・期待値」の記述に留め（NFR-PERF-04 は v1.1 で廃止済み）、実測で裏付けるのは実運用開始後とする。`work/run/` の実行データと GitHub Actions の `metrics` API をケーススタディとするコスト見積りが必要 | 運用データ蓄積後に設定 |
| TBD-10 | ~~`_normalize_model_with_warning` の実際の呼び出し経路~~ → **解消（v1.0.4）**: [hve/config.py](hve/config.py) `SDKConfig.__post_init__`（`model` / `review_model` / `qa_model` / `model_override` の正規化）、`SDKConfig.from_env`（環境変数 `REVIEW_MODEL` / `QA_MODEL` / `HVE_MODEL_OVERRIDE` の正規化）、[hve/__main__.py](hve/__main__.py) `_normalize_model_with_warning`（wizard モデル選択後の診断・上書き）の 3 経路で呼ばれる。テストは [hve/tests/test_config.py](hve/tests/test_config.py) | orchestrator.py / runner.py の参照点を確認 |
| TBD-15 | ~~`schema_version 2.0` 移行に伴う既存 `session-state/runs/` データの取扱い周知（破壊的変更）~~ → **解消（v1.0.3）**: [users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md) に「v1.0 アップグレード時の注意」セクション、[CHANGELOG.md](CHANGELOG.md) に Breaking 変更項目を追記済み | users-guide / CHANGELOG への案内追記 |
| TBD-16 | SDK 公式 `CopilotClient.list_sessions` / `get_session_metadata` API のバージョン互換性追跡 → **運用継続課題 / 保留**: SDK アップグレード時に regression 検知が主要手段。バージョン 0.x 間はシグネチャ変更リスクが存在し、現 `_get_copilot_sdk_version()` の major 一致チェックと `try/except` でカバーしている | Copilot SDK へのロックダウン / デグレーション検知 |
| TBD-17 | ~~`StepRunner._record_checkpoint` の呼び出しを runner 内の各 phase（main タスク / QA / review）の完了タイミングに組み込む~~ → **解消（v1.0.1）**: 事前 QA / メインタスク応答受信 / Review フェーズの各ポイントに組み込み済み。orchestrator.py で RunJournal を構築して StepRunner に注入する経路も整備済み | `runner.py` の 4 phase に `_record_checkpoint(step_id, marker)` を 1 行ずつ追加、`orchestrator.py` で `RunJournal(<run_dir>)` を build して `StepRunner(... , journal=...)` に渡す |
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
| TBD-29 | 人間承認点の拡張（要求・受入条件 / テスト観点・期待結果 / 高リスク変更 / 最終 PR）と承認監査証跡 → **PoC 結果を待つ（判断確定）**: 現行 `FR-CLI-87` は Wave 境界の同期承認を CLI へ提供し、対象は `asdw-web` Step 1.3 の 1 件、記録は `approval-<wave_index>` に限る。承認主体・対象成果物の digest・理由・再承認条件を保持する schema は持たない。承認者名と自由記述の保存は `NFR-SEC-01` / `FR-RTO-04` が禁じており、監査証跡を足すには保存対象の再定義が要る。GUI からの承認は `FR-GUI-23` により標準入力が使えず、`FR-QA-03` の `qa_answer_mode="gui-file"` と同種の IPC 経路の新設が必要 | 承認点ごとの判定項目が PoC で確定し、保存してよい主体識別子の範囲が決まった時点で起票 |
| TBD-30 | 案件 PoC の開始条件を固定する Run Manifest → **PoC 結果を待つ（判断確定）**: 対象案件・Done 条件・変更範囲・自動判定手段・除外条件・起動方法・知識ソース・承認者・参照/変更/禁止範囲・比較基準を 1 run として固定する schema と開始前検証の案。現行は APP 要求文書・Workflow パラメータ・`sources` 指定・起動時 preflight が個別に存在するだけで、run 単位の凍結と digest は持たない。§3.9.1 の `PoC` は Repository Query 検索計測を指し、本項の案件 PoC とは別ドメインである | 実案件 PoC で固定すべき項目が確定した時点で起票 |
| TBD-31 | PoC KPI の共通イベント schema と比較レポート → **PoC 結果を待つ（判断確定）**: 人間介入時間・ゲート試行回数と理由・手戻り / 再実行 / 人手修正・品質指摘・セキュリティ検出と解消・追跡の完全性・比較基準との差分を観測する案。現行 `FR-RTO-01`〜`07` の `RuntimeMetrics` は token・AI Credit・コスト・Step 状態・tool / model 失敗数を保持しており、AI 実行量とコストは既に取得できる。不足するのは上記の人手・ゲート・品質・比較の各系列で、永続化 allowlist（`_METRIC_KEYS` / `_PERSISTABLE_KEYS`）の拡張を伴う。測定したい指標が確定する前に allowlist を広げると、`FR-RTO-04` の最小化方針と衝突する | 評価指標と比較基準が PoC で確定した時点で起票 |
| TBD-32 | 要求→判断→設計→コード→テスト→レビュー→PR の追跡グラフ → **PoC 結果を待つ（判断確定）**: 現行 `FR-APPREQ-04` の trace block は `APP-IDs` / `Requirement-IDs` / `Requirement-Documents` / `Unresolved-Blockers` の 4 キーを保持し、validator は構造・ID 実在・APP 整合だけを決定的に検証する。判断・設計・コード・テスト結果・レビュー指摘・解消・PR を結ぶノードとエッジ、成果物 digest は持たない。グラフ化には各成果物へ安定 ID を与える必要があり、Prompt・テンプレート・validator へ広く波及する | 追跡したい関係の粒度が PoC で確定した時点で起票 |
| TBD-33 | 全 run へ適用する共通セキュリティゲート → **PoC 結果を待つ（判断確定）**: 現行は `NFR-SEC-01`〜`03` が秘密情報の出力禁止・`docs-original/` 読み取り専用・`git add` の pathspec 除外を規定し。旧 `FR-CLI-64`（Self-Improve の解決済み scope に対する秘密情報パターン検査）は Self-Improve 機能の削除に伴い廃止した。権限・依存脆弱性・禁止操作を含む合否 schema と PR 前 fail-closed ゲートは持たない。検査対象の範囲を決めずにゲートを足すと、既存 run が恒常的に停止する恐れがある | 検査項目と停止条件が PoC で確定した時点で起票 |
| TBD-34 | 案件 PDCA とプロセス PDCA の二重ループ → **PoC 結果を待つ（判断確定）**: PR 後に発見した事象の入力 schema、原因分類（要求 / 知識 / テスト / 実装 / ゲート / 工程引継ぎ）、案件修正とプロセス変更の別 ID、再現テスト先行、元ケース・同種ケースの回帰対象、改善効果の判定、標準化の承認を規定する案。旧 `FR-CLI-60`〜`65` の Self-Improve（削除済み）は scope 内の品質改善を反復する仕組みであり、案件修正と HVE 標準の変更を別々に管理・承認する契約ではない。分類体系を先に固定すると、実際の失敗事例と合わない分類が残る | 実案件 PoC で失敗事例の分類実績が得られた時点で起票 |
| TBD-35 | 実装前の受入条件・テスト baseline の独立確認と凍結 → **PoC 結果を待つ（判断確定）**: 生成アプリケーションの受入条件・期待結果・テスト集合を実装前に承認し、baseline の digest を固定して以後の変更を検出する案。現行は TDD RED / GREEN の Step 分離（`asdw-web` / `adfdv` / `aagd`）と TestCoding / Coding の Agent 分離で順序を担保するが、承認と凍結の工程は持たない。`FR-CLI-30` の Code Review Agent はフラグ指定時のみで全 run の必須ゲートではない。出典資料も「適用粒度は PoC で検証する」と明記している | 適用粒度と凍結対象が PoC で確定した時点で起票 |
| TBD-36 | Cloud Agent Orchestrator からの `--resume-run`（FR-CLI-86）利用不可 → **保留（設計判断が必要）**: `FR-CLI-86` が読む legacy 進捗ファイル（`hve/.run-progress.jsonl`）と `FR-STATE-04` の durable state（利用者単位の `state.sqlite3`）は、いずれも「run 終了後も残る利用者ローカル領域」であり、Issue / PR ベースで GitHub-hosted 環境上で実行される Cloud Agent Orchestrator には保存されない。`FR-CLI-86` の `--resume-run <run-id>` は `orchestrate` CLI サブコマンドの引数であり、`auto-*-reusable.yml` の Cloud 起動経路からは呼び出されない。したがって Cloud 実行が `FR-CLI-87` の承認ゲートを有効にした非対話実行（確認を出さず `blocked` で停止）や失敗で停止した後、進捗を引き継いで再開する手段が無く、利用者は当該 Sub-Issue を最初から再実行するしかない。対応するには Cloud run（Issue / PR 番号）とローカル `run_id` の対応付け、または Cloud 側専用の進捗永続化（GitHub Actions cache・Issue コメント等）の新設が必要であり、いずれも保存先・保持期間・認可範囲の新規設計を要するため、現時点では要件不備ではなく未設計の既知の制約として記録するに留める | Cloud 実行の再開需要と許容される保存先・保持期間が確定した時点で起票 |
| TBD-37 | ローカル GitHub API mutation の全画面横断直列化 → **保留（別 feature が必要）**: GitHub 公式は secondary rate limit 回避のため request の直列化と、大量の `POST` / `PATCH` / `PUT` / `DELETE` 間で最低 1 秒の待機を推奨する。現行は `add_labels` / Sub-Issue link / comment / Copilot assignment の一部が個別に 1 秒待機し、本改訂で Issue metadata 保存中と Pull Request review / merge 中の同一画面 mutation を相互排他にしたが、Issue panel・Pull Request panel・自動進捗 Post・Orchestrator を跨ぐ単一 queue / pacing は存在しない。個別 endpoint へ sleep を追加するだけでは同時開始を防げず、完了済みと誤認させるため行わない。対応には全 GitHub API consumer が共有する queue の所有者、read request を直列化する範囲、cancel / shutdown、rate-limit retry との待機統合を規範化する別 feature が必要 | 複数 GitHub mutation の並行実行が実測された時点、または全画面共通 request scheduler を設計するタスクで起票 |
| ASSUMPTION-01 | **[ASSUMPTION]** 欠落成果物への継続送信は最大 2 回とする。根拠は利用者指定の HVE Orchestrator review report §8.1 が推奨する 2〜3 回の下限であり、追加の AI Credit と待ち時間を小さく保つ安全側の値である。影響は、2 回目でも成果物が揃わない Step が従来どおり `failed` になること。P0 / P1 / P2 実測で 3 回目が同等品質のまま完走率を改善し、追加費用が許容範囲と確認された場合に覆す。 | 比較実測後に再評価 |
| TBD-38 | **解消（v3.36）**: 利用者が 2026-10-01 に、P2 型（Step DAG を使わない 1 セッションの実行）を HVE の実行面として取り込まないと決定した。本項の対象はすべて決着した。Step の縮約（N5-5）と Step ごとの effort（N5-6）は実施せず、fan-out の粒度は現行（画面単位）のまま、ASDW-WEB の `max_parallel` の解除は FR-IDL-02（`ownership_parallel`）で扱った。以下は経緯。 ~~**[BLOCKED]**~~（v3.20 で縮小）Workflow Step の 122 → 約 49 への縮約、fan-out の粒度（画面単位 → APP 単位）、Step ごとの reasoning effort、および ASDW-WEB の `max_parallel=1`（FR-DAG-03）の解除は、P0（現行）/ P1（ステージ化）/ P2（1 セッション）を APP 1 件・各 n=3 で比較し、同一 E2E 合否で時間または AI Credit を 30% 以上削減するという採否基準を満たす構成が未確定のため実装しない。比較は AI Credit と Azure 課金を伴う可能性があり、外部実行・課金は承認されていない。v3.19 で本項に含めていた「計画用 DAG / `SPLIT_REQUIRED` / `split_fork` の削除」は FR-PLAN-01（N2-3）へ、「事前承認 schema の拡張」は FR-PROMPT-13（N3-1）へ移して解除した。解除の根拠: 前者は ATG 実測（`work/202609271600-ATG-BusinessImpactAnalytics.md`。計画用 DAG の有無で完成率は向上せず、時間・費用は 1.7〜3.5 倍）で決まり、後者は安全設計の判断で決まるため、課金を伴う比較実測を待つ理由が当てはまらない。同じ Agent・同じ出力の Step の整理（N5-1）と ADI 1.1 / 1.2 の任意化（N5-2）は Step の順序と実行量の整理であり、本項の対象外とする。 v3.35 追記（比較実測 N5-4 の結果。2026-10-01 に時間枠で打ち切り、`work/run/20260930-dag-review-plan/measurement/artifacts/results.md`）: APP-009・`gpt-6-luna` で、P2 は 3/3 run がデプロイ後テスト exit 0（総実行時間の中央値 7,673 秒、AI Credit の中央値 111.59）。P0 は完了 run が無く（`aad-web` 37/37 成功後、`asdw-web` 8/44 Step で 27,833 秒・429.75 AI Credit）、P1 も完了 run が無い（前半 6/23 ステージで P2 の全工程の時間・AI Credit を超過）。§4.4 の Step 統合（P1）は不採用とし、Step の縮約（N5-5）と Step ごとの effort（N5-6、effort の差を測っていない）は実施しない。P2 型（Step DAG を使わない 1 セッションの実行）は時間・AI Credit の採否基準を満たしたが、盲検レビューは未実施で、実行面の変更は本項の範囲を超えるため、取り込むかどうかは別の計画で決める。`max_parallel` の解除は FR-IDL-02（`ownership_parallel`）で扱った。 | 完了（追加作業なし。v3.36 で利用者が P2 型を取り込まないと決定） |
| TBD-39 | ID 台帳の CI（FR-IDL-01）を `--warn-only` から非 0 終了の強制へ切り替える時期。2026-09-30 の `--bootstrap` 実行で、生成済みのアプリ文書に既存の違反 6 件（`docs/test-specs/` のテスト ID の命名が `TEST-{ID}-` でない: APP-009-S002 / S003 / S004 / S008、SVC-03 / SVC-12）を確認した。これらは HVE ではなく生成されたアプリの成果物であり、AAD-WEB 2.3 / 2.4 の再実行で新しい命名規則へそろう。 | AAD-WEB 2.3 / 2.4 の再実行後に `python .github/scripts/check-id-ledger.py` が exit 0 になった時点 |
| TBD-KD-01 | Cloud Agent Orchestrator 経路での知識探索（FR-KD）。GitHub Copilot cloud agent は OAuth を使う remote MCP server を未サポートと明記しており（[Configure MCP servers for your repository](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/configure-mcp-servers)、確認日 2026-10-01）、Work IQ は Entra ID のユーザー委任認証を要するため、Cloud 経路は本改訂の対象外とする。Cloud の既存 Issue / PR 手順は変更しない。**利用者確認済み（2026-10-01）: 対象外で確定。** | GitHub が cloud agent の OAuth remote MCP 対応を公開した時点で再評価する |

### 12.1 仮定（ASSUMPTION）

本節は、調べても決まらなかった事項について採用した値と、その根拠・影響・覆す条件を記録する。いずれも定数・既定値の変更で後から戻せる。

| ID | 内容 | 根拠 | 影響 | 覆す条件 |
|---|---|---|---|---|
| [ASSUMPTION] KD-A1 | 利用者依頼が要求の正本とした `hve-dev\requirements-definition.md` は、既存の `hve-dev/requirement-definition.md`（本書）を指すものとして本書を更新し、別ファイルを新設しない | `hve-requirement-traceability` Skill、`hve-dev/generate_tdd_inventory.py`、契約テストが本書のパスを正本として参照しており、2 つ目の正本は索引と食い違う | 要求は本書だけに存在する | 利用者が別ファイルの新設を明示した場合 |
| [ASSUMPTION] KD-A2 | 事前 QA で知識探索を実行した場合は、人への回答待ちを行わず、調査回答または既定値候補を採用する（FR-KD-06） | 利用者依頼「なるべくタスクを開始したら私が介在しない方が最良」と FR-E2E-01 の停止境界 | 知識探索を有効にした実行では QA ダイアログ・標準入力の回答待ちが発生しない | 利用者が知識探索と人の回答の併用を求めた場合（知識源を無効にすれば従来の回答収集に戻る） |
| [ASSUMPTION] KD-A3 | MCP 出典の検証は、locator が成功応答本文に含まれるかの部分一致（正規化後）で行う（FR-KD-04） | 応答の構造は MCP server ごとに異なり、全 server に共通する citation の構造化形式が無い。本文中の URL・パス・タイトルは共通に観測できる | 本文に locator を含まない構造化応答だけを返す server では `Confirmed` にできない（安全側） | 誤拒否が運用で多発し、構造化 citation（`result.citable_sources` など）が SDK で安定した場合 |
| [ASSUMPTION] KD-A4 | 修復は最大 2 回、1 セッションの QA 作成は 5 件、ロック待機は 30 秒、応答本文の保持は 1 呼出し 1,000,000 文字・500 呼出しとする（FR-KD-04 / 05 / 09） | 既存の継続上限（FR-WF-OUT-12 の 2 回）と同程度にそろえた。ロックの保持時間は 1 回の書込みで数ミリ秒〜数秒 | 上限を超えた分は処理されない（失敗として扱う） | 実測で上限に達するケースが観測された場合 |
| [ASSUMPTION] KD-A5 | AKM の知識探索は DAG の前に 1 回だけ実行する（FR-KD-07） | 探索の書込みを後続の KnowledgeManager と横断レビュー（AKM Step 2）に通すため。旧取り込み phase と同じ位置 | DAG 後の Work IQ 検証は行わない | DAG 後の検証が必要と判断された場合 |
| [ASSUMPTION] KD-A6 | 既定の `workiq` 許可リストは `retrieve`、`ask`、`fetch`、`search_paths`、`get_schema`、`list_agents` とし、`call_function` と `fetch_blob` を含めない（FR-KD-02） | workiq-preview の README（確認日 2026-10-01）が `retrieve` を先に使う方針を示している。`call_function` は任意の関数を実行し、`fetch_blob` はバイナリを取得するため、読み取り専用の調査に必要ない | `call_function` / `fetch_blob` を使う調査はできない | 利用者が GUI の Tool-Search 設定（FR-GUI-53）で許可リストを変更した場合 |
| [ASSUMPTION] KD-A7 | GUI の「知識源 MCP サーバー」欄の不正な名前は、GUI では検査せず、子プロセスの CLI が exit 2 で拒否する（FR-KD-01） | 名前の検査を CLI の 1 か所に置く（FR-MAINT-07） | 不正名のまま実行するとジョブが起動直後に失敗する | GUI で入力時の検査が必要と判断された場合 |
| [ASSUMPTION] KD-A8 | 既定の有効化（FR-KD-11）は直接 CLI・wizard・Prompt 版の未選択値・GUI の `workiq` 既定だけに適用し、GUI の `auto_qa` は FR-GUI-16 の必須選択を維持する。`SDKConfig()` の dataclass 既定値は変えない | FR-GUI-16 は `auto_qa` を「既定値による暗黙決定を許さない」と定めており、GUI では既に明示選択されている。dataclass 既定値はテスト・プログラムからの直接利用に広く使われ、変更すると無関係な経路の挙動が変わる | 直接 CLI・Autopilot 子・Prompt 版（未選択）では、各 Step に事前 QA と実行後の不明点調査のモデル呼出しが加わる。無効にするには `--no-auto-qa` / `--no-workiq`、`WORKIQ_ENABLED=false`、request の `settings_overrides` を使う | 追加のモデル呼出しの費用・時間が許容できないと利用者が判断した場合 |
| [ASSUMPTION] KD-A9 | 追加する既定の許可リストは `microsoft-learn`（3 tool）だけとし、`workiq-preview`・Context7 などは加えない（FR-KD-02 v3.42） | `microsoft-learn` の tool 名は本端末の Copilot CLI で公開されている tool 一覧（2026-10-02 確認）と既存 `software_engineering_tool_allowlists` で確認できた。**競合**: 本端末には `workiq-preview` プラグイン（`workiq` と同じ MCP URL、`~/.copilot/installed-plugins/work-iq/workiq-preview/.mcp.json`、2026-10-02 確認）もあるが、FR-CLI-91 は `workiq-preview` を `workiq` の代替として受理することを禁じ、利用者文書の契約テストも言及を禁じるため、既存契約を優先した。Context7 などの server 名・tool 名は利用者環境ごとに異なり確定できない | `workiq-preview` などを知識源にするには GUI の Tool-Search 設定（FR-GUI-53）で許可リストを追加する | 利用者が `workiq-preview` などを既定に含めるよう求め、FR-CLI-91 を改訂した場合 |
| [ASSUMPTION] KD-A10 | 実行後の不明点調査（FR-KD-13）は、知識源が 0 件でも質問票を `qa/` に保存し、回答は既定値候補とする。人への回答待ちは行わない | 依頼の原因 4 は「調査も記録もされない」であり、記録は知識源の有無によらず価値がある。メインタスク後に人を待つと無人実行（FR-E2E-01）が止まる | `auto_qa=True` の Step ごとにモデル呼出しが 1 回増える | 実行後の質問票に人の回答を求める要求が出た場合 |
| [ASSUMPTION] KD-A11 | 変更前に記録された durable 実行の replay argv（`--auto-qa` だけを持ち `--no-auto-qa` を持たない）は、`hve resume` で新しい既定（有効）として再実行する | 変更前の argv からは「明示的に無効」と「未指定」を区別できない | 変更前に開始し `auto_qa` 無効で中断した実行を resume すると、事前 QA が有効になる | 変更前の実行の resume で問題が報告された場合 |

---

## 13. ワークフロー別仕様（生成ファイル詳細）

本節は、各 Workflow の目的・Step DAG・生成ファイル（`output_paths` / `output_paths_template`）・必須入力（`required_input_paths`）をゲートとして緻密化する目的で定義する。[hve/workflow_registry.py](hve/workflow_registry.py) は実装状態の技術的な情報源として本節と整合させる。差分が生じた場合、ソース側を理由なく優先せず、規範要件への違反か規範要件の仕様変更かを判定し、後者なら要件を先に改訂してから両者を同期する。

### 13.0 共通約束

- **FR-WF-OUT-01**: 各 Step は `output_paths` で宣言した全ファイルを実行完了時点で存在させなければならない。`output_paths` は実行時に常に必要な成果物だけを宣言し、条件付き・任意の成果物を含めてはならない。1 件でも欠落した場合、当該 Step は `failed` とする（Wave 入力チェックの前提）。本ゲートの適用範囲は CLI / GUI Orchestrator 配下モード（`OrchestratorContext` が注入された実行）に限る。単独実行モード（`ctx` 未注入）では Orchestrator が Step の完了を判定しないため、本ゲートを適用しない。v3.21 で legacy runtime split-fork（`split_fork_enabled=true`）を撤去したため、この経路の適用除外は存在しない。DAG Wave の fleet 実行（`fleet_mode_enabled`）は Wave 単位の完了判定を持ち、本ゲートの適用除外ではない。欠落報告には欠落したパスのみを列挙し、存在する宣言パスを含めてはならない（[hve/runner.py](hve/runner.py) `_check_output_paths_gate`）。
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
- **FR-WF-OUT-07**: fan-out 対象でない StepDef の `output_paths_template` は展開されないため、`_check_output_paths_gate` および `collect_workflow_output_paths` の対象にならない。動的パス（`docs-generated/files/{relative-path}.md` 等）や条件付き生成物を io-contract と整合させるための**契約宣言専用の宣言面**として用いてよい。この面に宣言した条件付き成果物は実行時 G-OUT の対象外であり、生成条件・親成果物からの参照・非生成時の stale cleanup は個別の成果物契約と専用テストで担保する。実行時ゲートの対象としたい確定成果物は `output_paths` に宣言すること。
- **FR-WF-OUT-08**: 名称スラッグ（`{screenNameSlug}` / `{serviceNameSlug}` / `{jobNameSlug}`）は **日本語カタログ名の英訳** であり（`docs/catalog/service-catalog.md` の `SVC-01 | 会員・同意管理サービス` に対し実在ファイルは `docs/services/SVC-01-member-consent-service-description.md`）、訳語は Agent が生成するため [hve/catalog_parsers.py](hve/catalog_parsers.py) を拡張しても決定的には復元できない。したがって名称スラッグを `_KEY_ALIAS_PLACEHOLDERS_BY_PARSER` へ登録してはならず、これを含むエントリは FR-WF-OUT-06 規則 2 により恒久的に drop される。
- **FR-WF-OUT-09**: FR-WF-OUT-06 の結果、fan-out する Step の `output_paths_template` が**どの fan-out キーでも 1 件も解決されない**場合、当該 Step の実行時ゲート（FR-WF-OUT-01）は無言で空になる。この状態は誤 fail を起こさない代わりに検証の消失を招くため、対象 Step を明示 allowlist として固定し、allowlist 外の Step がゲート空になった場合は CI で検出しなければならない（[hve/tests/test_output_paths_template_resolvability.py](hve/tests/test_output_paths_template_resolvability.py) `_EMPTY_GATE_ALLOWLIST`）。allowlist の各項目には空になる理由を記載すること。FR-WF-OUT-10 の prefix ゲートで検証を回復した Step は allowlist から除くこと。
- **FR-WF-OUT-10**: FR-WF-OUT-06 で drop されたエントリのうち、**fan-out キーを実際に含む**ものは、キー出現位置の直後までを接頭辞とする **prefix 存在ゲート**へ降格して検証を回復する（[hve/fanout_expander.py](hve/fanout_expander.py) `resolve_output_path_prefix_gates`、[hve/runner.py](hve/runner.py) `_check_output_paths_gate`）。
  - 判定は「接頭辞に前方一致するファイルまたはディレクトリが 1 件以上存在するか」であり、`output_paths` の内容は変更しない（他の消費者への影響を持たない）。
  - **根拠**: 名称スラッグは FR-WF-OUT-08 のとおり決定的に復元できないうえ、単一 run（`ed3931b8`）の生成物が `docs/services/` だけで `{serviceId}-{serviceNameSlug}-description.md` / `{serviceId}-description.md` / `{serviceId}.md` の 3 形式に分岐しており、完全パス一致でも glob 一致でも誤 fail する。一方で全生成物が **ID 接頭辞で始まる**点は一貫しているため、接頭辞一致だけが誤 fail なしに「当該キーの成果物が存在するか」を検証できる。
  - キー別名を 1 つも含まないエントリ（全 fan-out 子で同一の固定パス）と、キーがそもそも代入されないエントリ（ADFDV の `{jobId}` 等、FR-WF-ADFDV-01）は prefix 化の対象外とし、FR-WF-OUT-09 の allowlist に残す。
  - ID 体系は `SVC-NN` / `APP-NNN-SNNN` / `DNN` のように桁数固定であり、接頭辞が別キーの成果物へ誤って一致しないこと。
- **FR-WF-OUT-11**: `.github/io-contracts/*.yaml` の `inputs[]` のうち `kind: static` であり、かつ変数記法（`{...}` / `<...>`）・glob（`*` / `?`）・ディレクトリ参照（末尾 `/`）のいずれも含まないパスは、リポジトリに実在しなければならない。[.github/scripts/validate-io-contract.py](.github/scripts/validate-io-contract.py)（引数なし）が本検査を行い、違反を integrity error として報告する。除外は [.github/io-contract-exceptions.yaml](.github/io-contract-exceptions.yaml) の `static_paths` に列挙されたパスだけとし、本検査専用の除外機構を新設してはならない（FR-MAINT-07）。FR-WF-OUT-05 の registry mismatch 検査は `required: true` かつ `kind: agent_artifact` の入力しか照合せず、`kind: static` の実在はどの検査も対象にしていなかった。その結果、実体と一致しない static 宣言が 8 件残存していた（`knowledge/D05` と `knowledge/D09` の区切り文字ゆれ 6 件、`knowledge/D15` のファイル名断片 1 件、未生成の生成対象ファイル 1 件）ことを根拠とする。
- **FR-WF-OUT-12**: **優先度 MUST。** CLI / GUI Orchestrator 配下モードで、メイン Step セッションの処理が終了した時点に FR-WF-OUT-01 / 10 の必須成果物が 1 件以上欠落している場合、[hve/runner.py](hve/runner.py) は同じメインセッションへ欠落パスだけを列挙した継続メッセージを送り、各応答後に既存 `_check_output_paths_gate` で再判定しなければならない。最大 2 回のいずれかで全件が存在すれば後続ゲートへ進み、2 回後も欠落する場合は既存の `output-missing` エラーと `failed` 判定を維持する。初回判定で欠落が無い場合は継続メッセージを送ってはならない。単独実行モード、宣言なし Step、未知 Step、未知 Workflow は FR-WF-OUT-01 と同じく対象外とする。継続応答が空でも再判定し、SDK 例外や timeout を成功へ丸めてはならない。v3.24 で、`step_timeout_seconds` が有効な場合に限り、継続メッセージへ Step 開始からの経過分と上限分（「経過 X 分 / 上限 N 分」）を加える。本機能のために新しい CLI option、環境変数、設定項目、別セッション、または別の path 判定実装を追加してはならない（FR-MAINT-07）。出典: 利用者依頼（2026-09-30）および同依頼で指定された HVE Orchestrator review report §8.1。

#### 13.0.1 本改訂の受入基準

| AC | 対応要求 | 事前条件 | 操作 / コマンド | 期待結果 | 証跡 |
|---|---|---|---|---|---|
| AC-001 | FR-WF-OUT-12 | Fake main session、CLI / GUI Orchestrator context、必須成果物 1 件が初回未生成 | `python -m pytest -q hve/tests/test_runner_output_continuation.py` | 初回欠落時だけ継続を送り、1 回目または 2 回目で生成された場合は exit 0。2 回後も欠落するケース、SDK 例外、timeout は非 0。メッセージは欠落パスだけを含み、既存パスを含まない | pytest のケース別 PASS と exit code |
| AC-002 | FR-CLI-102 | `unattended=False` / `True` の両設定 | `python -m pytest -q hve/tests/test_phase1_request_plan.py hve/tests/test_runner_output_continuation.py` | 共通 3 指示は両設定の Prompt に各 1 回だけ含まれ、無人停止境界は `True` だけに含まれる。共通指示の UTF-8 byte 数を含む全構成要素の合計が最終 Prompt byte 数と一致する | pytest の assertion と exit code |
| AC-003 | FR-E2E-01 | 利用者が承認した `full-pipeline` の 1 run（v3.35 までは比較実測 TBD-38 の run を想定。TBD-38 は v3.36 で解消）。依頼 1 回と事前承認の宣言だけを入力にする | 選択した全 Workflow を `full-pipeline` の順に実行し、デプロイ後 E2E（ASDW-WEB 4.4 相当）を実行する | 選択した全 Workflow の G-OUT が合格し、デプロイ後 E2E が exit 0。依頼後の人の入力が資格情報と宣言範囲外の操作の承認だけである | run ログ、G-OUT の判定、E2E の exit code。判定は `要追加`（v3.35: N5-4 の P0 は時間枠内に完了せず、HVE の `full-pipeline` 実行としての合格 run はまだ無い。v3.36: P2 型は取り込まないため、合格の判定には HVE の `full-pipeline` run が必要） |
| AC-004 | FR-KD-01, FR-KD-10 | リポジトリルート。環境変数 `HVE_KNOWLEDGE_SOURCES` / `WORKIQ_ENABLED` を各ケースで設定・解除する | `python -m pytest -q hve/tests/test_knowledge_discovery_config.py` | `--workiq --knowledge-source confluence,workiq` の実効知識源が `["workiq","confluence"]`。`HVE_KNOWLEDGE_SOURCES=" jira , ,bad name"` が `["jira"]`。不正名と削除済み option（`--workiq-dxx` など FR-KD-10 の 8 種）は exit 2。削除済み環境変数を設定しても `SDKConfig` に該当 field が無い。exit 0 | pytest のケース別 PASS と exit code |
| AC-005 | FR-KD-02 | Fake resource snapshot（`ready` / 未 ready）、Fake policy、Fake session RPC | `python -m pytest -q hve/tests/test_knowledge_discovery.py -k "source_resolution or runtime"` | `unverified` / `not-configured` / `no-readonly-allowlist` / `usable` の判定と、除外警告が 1 知識源 1 行。runtime で `connected` でない・許可 tool 非公開の知識源を除外し、0 件で探索しない。既定 policy の `workiq` 許可リストが 6 件で書込み系を含まない。exit 0 | pytest の assertion と exit code |
| AC-006 | FR-KD-03 | Fake client / session | `python -m pytest -q hve/tests/test_knowledge_discovery.py -k "session_options or permission or prompt"` | options の `available_tools` / `disabled_mcp_servers` / `infinite_sessions` / モデルが規定どおりで、`on_user_input_request` を含まない。permission handler が read（`.git/`・`.hve/`・`.env*` を除く）・許可 MCP・`hve_*` だけを許可し、write / shell / url / sandbox bypass を拒否する。指示文に `STATUS:` 書式や件数上限を含まない。1 セッションで 6 件目の QA 作成が `limit-exceeded`。runtime 検査は `initialize_and_validate` の後に一覧を取り、`pending` を期限まで再取得する（`-k runtime` は AC-005 で実行）。exit 0 | pytest の assertion と exit code |
| AC-007 | FR-KD-04, NFR-KD-01 | Fake SDK イベント（start / complete、成功・失敗・ID 不一致） | `python -m pytest -q hve/tests/test_knowledge_discovery.py -k "evidence or source_verification"` | 例の URL が検証済み、本文に無い URL が `locator-not-found`、未呼出しが `no-successful-call`、`Confirmed` の出典 0 件が `confirmed-without-source`。違反時にファイル不変。失敗メッセージ・QA・ChangeLog に MCP 応答本文が含まれない。exit 0 | pytest の assertion と exit code |
| AC-008 | FR-KD-05, NFR-KD-01 | 一時ディレクトリをリポジトリルートとする | `python -m pytest -q hve/tests/test_knowledge_files.py` | 8 プロセスが同じ QA ファイルの別質問を `conflict` 時に再読込して更新し、全 8 件の回答が残る（差分喪失 0）。`base_sha256` 不一致は `conflict` と現在の SHA-256。ロックを持つプロセスの終了による解放、生きているプロセスのロックで `lock-timeout`（テストでは待機上限を短縮）、`path-denied` の各ケース（絶対パス、`..`、symlink、`.md` 以外、ChangeLog）、QA 名の `-2` 採番、D 文書の FR-WF-AKM-01 schema 違反の拒否、ChangeLog 雛形が FR-WF-AKM-01 の ChangeLog schema を満たすこと。ロックファイルの内容が pid / host / token / created_at だけ。exit 0 | pytest の assertion と exit code |
| AC-009 | FR-KD-06, FR-INPUT-05 | Fake Pre-QA session（質問 3 件）、Fake 探索 runner。shipped AAGD Step 2.3 / 3 の実 manifest・policy と fake SDK session | `python -m pytest -q hve/tests/test_runner_pre_qa_knowledge_discovery.py hve/tests/test_runner_pre_qa_mcp_scope.py` | 例の 3 問で Q1 が調査回答、Q2・Q3 が既定値候補になり、`_collect_qa_answers` と IPC を呼ばない。較正ログを書かない。探索が例外の場合も人待ちせず既定値で保存。`usable` が 0 件なら従来の回答収集を呼ぶ。保存後の再読込検証が成功する。質問票 session の `disabled_mcp_servers` は Work IQ の有効・無効によらず `workiq` を含み、呼出し元の list を変更しない。custom input の同意が無ければ知識探索 session を作らない。探索 session の作成・接続・送信の失敗では QA を既定値で確定して main へ進み、切断の失敗・停止は bounded で他方の session の切断を飛ばさない。exit 0 | pytest の assertion と exit code |
| AC-010 | FR-KD-07, FR-KD-08 | Fake 探索 runner、Fake `post_comment` | `python -m pytest -q hve/tests/test_orchestrator_knowledge_discovery.py` | AKM は DAG 前に「AKM 知識探索」を 1 回だけ呼び、旧 Work IQ 取り込み・検証 phase の関数が存在しない。ARD は回答 1 件以上で規定書式のコメントを 1 件投稿し、0 件・Issue 番号なしでは投稿しない。セルの `|`・改行・`<` / `>` を置換する。探索の例外で DAG を止めない。exit 0 | pytest の assertion と exit code |
| AC-011 | FR-KD-09 | Fake session（初回で一部の質問だけ記録） | `python -m pytest -q hve/tests/test_knowledge_discovery.py -k "repair"` | 不足項目だけを列挙した修復の指示を最大 2 回送り、残りを `Unknown` で記録する。knowledge / research モードで QA 未作成なら `QA 未作成` を指示する。サマリ行の書式が規定どおり。exit 0 | pytest の assertion と exit code |
| AC-012 | FR-KD-10 | リポジトリルート | `python -m pytest -q hve/tests/test_knowledge_discovery_removal.py` | `.github/prompts/runtime/workiq/` が存在しない。`hve/` の非テストコードに削除した関数名・option・field・環境変数名が残っていない。GUI 設定の読込が削除済みキーを無視し、保存で書かない。旧列名 `Work IQ 回答案` / `Work IQ 理由` の QA を `調査回答` / `調査出典` として読む。exit 0 | pytest の assertion と exit code |
| AC-013 | FR-KD-01〜10, NFR-KD-01 | 本改訂の変更ファイル | `python -m ruff check --isolated --select F,E9 hve/knowledge_files.py hve/knowledge_discovery.py` と AC-004〜AC-012 の各コマンド。変更した既存 Python ファイルは同じ規則で HEAD より指摘が増えないこと | すべて exit 0（既存ファイルは指摘の増加 0 件） | 各コマンドの exit code。`--isolated` と規則の固定は、リポジトリに ruff 設定が無く、利用者ごとの ruff 設定や ruff の版ごとの既定規則（0.16 は `UP` / `BLE` / `I` などを含み、既存の `typing.Dict` 表記の規約と衝突する）で判定が変わらないようにするため |
| AC-014 | FR-KD-11 | リポジトリルート。`WORKIQ_ENABLED` を各ケースで設定・解除する | `python -m pytest -q hve/tests/test_knowledge_discovery_defaults.py -k "defaults"` | `-w aas` だけで `auto_qa=True`・`workiq_enabled=True`。`--no-auto-qa` / `--no-workiq` で各 `False`。`WORKIQ_ENABLED=No` で `False`、`WORKIQ_ENABLED=false` と `--workiq` の併用で `True`。`OrchestrateArgs.to_argv()` が `True` / `False` で `--auto-qa` / `--no-auto-qa`・`--workiq` / `--no-workiq` を 1 つずつ出す。`args_from_settings` は保存値 `""` で `auto_qa=True`、`"off"` で `False`。QA 起点 AKM 子の argv が `--no-auto-qa` と `--no-workiq` を含む。resume replay argv が `--no-auto-qa` / `--no-workiq` を含み、`sanitize_argv` が受理する。exit 0 | pytest のケース別 PASS と exit code |
| AC-015 | FR-KD-12 | Fake snapshot（`workiq` enabled）、Fake session（`mcp.list` が `needs-auth`）、Fake Pre-QA session | `python -m pytest -q hve/tests/test_knowledge_discovery_defaults.py -k "status or needs_auth"` | 警告に `/mcp auth workiq` を含む。`DiscoveryResult.excluded` が `[("workiq","server-needs-auth")]`。事前 QA の保存ファイルに `## 知識探索の状況` と `\| workiq \| 除外 \| server-needs-auth \|` がある。探索開始時の例外では `\| workiq \| 不明 \| discovery-error \|`。exit 0 | pytest のケース別 PASS と exit code |
| AC-016 | FR-KD-02（v3.42 追補） | 同梱の `hve/toolsearch/policy.json` | `python -m pytest -q hve/tests/test_knowledge_discovery_defaults.py -k "allowlist"` | `tool_allowlist_for("knowledge", "microsoft-learn")` が 3 件、`"workiq-preview"` は空（既定に加えない）。`microsoft-learn` に `*`・`create_entity`・`call_function`・`fetch_blob` を含まない。`microsoft-learn` の分類は `software-engineering` のまま。exit 0 | pytest の assertion と exit code |
| AC-017 | FR-KD-13 | Fake main session（質問票 2 件、`質問なし`、例外の各ケース）、Fake 探索 runner | `python -m pytest -q hve/tests/test_runner_post_execution_discovery.py` | 質問票ありで `qa/r1-1-post-execution-qa.md` を保存し、ユーザー回答が Q01=`A) 差分マージ`・Q02=既定値候補、回答待ちと較正ログが 0 回、AKM 登録 1 件。`質問なし` で QA ファイルを作らない。例外で警告し Step を失敗させない。条件判定は `auto_qa=False`・`dry_run=True`・reuse-session でそれぞれ不実行。exit 0 | pytest のケース別 PASS と exit code |
| AC-018 | FR-KD-14, FR-LOCAL-SURFACE-01 | Fake 保存設定と Fake Work IQ capability（`ready`） | `python -m pytest -q hve/tests/test_knowledge_discovery_defaults.py -k "prompt"` と `python -m pytest -q hve/tests/test_local_surface_option_parity.py` | `{"workiq": false}` で argv が `--no-workiq`、`{"knowledge_sources": "microsoft-learn"}` で `--knowledge-source microsoft-learn`。`{"workiq": "yes"}`・`{"knowledge_sources": "bad name"}` は `PromptRequestError`。shared setting 29 key と `ALLOWED_SETTINGS_OVERRIDES` が一致。exit 0 | pytest のケース別 PASS と exit code |
| AC-019 | FR-KD-11〜14 | 本改訂の変更ファイル | `python -m ruff check --isolated --select F,E9 hve/knowledge_discovery.py hve/runner.py hve/__main__.py hve/config.py hve/prompt_request.py hve/gui/orchestrate_args.py hve/resume_service.py hve/qa_akm_dispatch.py hve/tests/test_knowledge_discovery_defaults.py hve/tests/test_runner_post_execution_discovery.py` と、変更前から存在する関連テスト（AC-004〜AC-012 の各コマンド、`hve/tests/test_main.py`、`hve/tests/test_resume_service.py`、`hve/gui/tests/test_orchestrate_args_from_settings.py`、`hve/tests/test_prompt_cli.py`、`hve/tests/test_prompt_workiq_capability.py`） | 新規テスト 2 ファイルの ruff と関連テストは exit 0。変更した既存 Python ファイルは同じ ruff 規則で HEAD より指摘が増えない（既存の指摘は本改訂の対象外） | 各コマンドの exit code と、HEAD 版との ruff 指摘の差分 |

- **FR-WF-DM-01**: AAS Step 3.1 と ADA Step 4.1 が共有する `Arch-DataModeling` の主成果物は `docs/catalog/data-model.md` とし、分割の有無にかかわらず `output_paths` および io-contract で `required: true` のまま維持する。単一ファイル版が 50,000 文字を超える見込みの場合だけ、次の canonical sidecar 3 件を**全て**作成または更新し、親を索引/統合版として各 sidecar へのリンクと全体要約を保持する。親は分割時も固定見出し `1`〜`6` を維持し、見出し `3`〜`5` には主キー・主要制約・代表インデックス・整合性判断・主要イベント・図の要旨を含む統合ビューを残して、下流 Step が親単独で必要情報を取得できなければならない。sidecar は詳細を補足する任意成果物とし、下流の必須入力へ追加しない。各 sidecar は親への戻りリンクを持つこと。
  - `docs/catalog/data-model-service-stores.md` — Service Data Stores
  - `docs/catalog/data-model-consistency-events.md` — Consistency & Events
  - `docs/catalog/data-model-diagrams.md` — Diagrams
  canonical 3 件以外の章別・APP-ID別 Data Model sidecar を生成してはならない。registry では AAS Step 3.1 / ADA Step 4.1（いずれも非 fan-out）の `output_paths_template` へ3件を宣言し、io-contract では各々を `required: false`, `mode: upsert` とする（FR-WF-OUT-05 / 07）。分割不要の再実行では、親から sidecar リンクを除去して固定章を親へ統合し、canonical sidecar 3 件の既存ファイルを削除して stale 成果物を残してはならない。分割条件・相互リンク・stale cleanup は共有 Prompt、AAS / ADA Body template、および専用契約テストで同一に保つ。

### 13.1 AAS — Architecture Design

- **目的**: ARD が確定したアプリ群と APP 別要求定義書から、アーキテクチャ推薦／ドメイン／サービス／データ／テスト戦略までの上流アーキテクチャ資産を生成する。AAD-WEB / ADFD / AAG の上流に位置する。
- **必須入力（ルート）**: `docs/catalog/app-catalog.md`、対象 APP 全件の `docs/architectural-requirements-app-NNN.md`
- **Step DAG と生成ファイル**:

| Step | タイトル | Custom Agent | 依存 | 生成ファイル |
|---|---|---|---|---|
| 1 | ソフトウェアアーキテクチャの推薦 | Arch-ArchitectureCandidateAnalyzer | — | `docs/catalog/app-arch-catalog.md` |
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
| `data_location` | `LOCATION` | `japaneast` | [.github/skills/azure-region-policy/SKILL.md](.github/skills/azure-region-policy/SKILL.md) §1 標準リージョン優先順位の第 1 位 |
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
- **FR-WF-ASDW-07**: **優先度 MUST。** Step 1.3 の native pipeline は、stage が非 0 で終了したとき、その stage の stderr の末尾を有界な要約として `work-status.md` の `## Failure summary: <stage> (attempt <n>)` 節（`text` fence）へ記録しなければならない。stderr は端末へ実行中に流し続け（tee）、保持するのは末尾 16 KiB までとする。要約は最後の 20 行・各行 300 文字・全体 2,000 文字以内とし、URL、`password` / `token` / `key` / `secret` / `sig` 等の代入、`Bearer` 値、GUID（subscription / tenant / principal ID）、メールアドレス、絶対パス、32 文字以上の不透明な文字列を `<redacted>` へ置換し、制御文字と Markdown fence 文字（`` ` ``）を除く（NFR-SEC-01）。成功した stage は要約を記録しない。要約は Agent の文章ではなく HVE が捕捉した stderr だけから作る。N-14（System Test 20261002-0335）の修正。契約テスト: [hve/tests/test_asdw_data_failure_summary.py](hve/tests/test_asdw_data_failure_summary.py)

#### 13.3.2 Step 4.3（Azure Static Web Apps Deploy）のrepository-managed Workflow契約

- **FR-WF-ASDW-04**: APP-009のrepository-managed SWA deploy Workflow [`.github/workflows/azure-static-web-apps-app009.yml`](.github/workflows/azure-static-web-apps-app009.yml) は `workflow_dispatch` だけで起動し、`resource_group`と`static_web_app_name`を既定値なしの必須文字列入力として受け取らなければならない。Workflow権限は`id-token: write`と`contents: read`だけとし、`environment: copilot`でOIDC認証した後、入力したexact targetを`az staticwebapp show`で確認してからdeployment tokenを動的取得し、値をmaskして`Azure/static-web-apps-deploy`へ渡す。`azure/login`と`Azure/static-web-apps-deploy`は公式repositoryのrelease tagが指す40桁commit SHAへ固定し、review可能なtag名を同じ行のコメントへ残す。hard-coded target、`push` / `pull_request` trigger、PR close job、`repo_token`、手動登録したdeployment token secretを追加してはならない。Step 4.3のPromptは同じ2入力を`gh workflow run`へ明示し、Workflowを生成・編集せずdefault branch上の既存Workflowを起動する。
- **FR-WF-ASDW-05**: APP-009のrollback drillを実行するrepository-managed Workflowを、実行対象scriptが存在しない状態で公開してはならない。現行repositoryには`.github/workflows/rollback-drill.yml`が参照する`src/infra/azure/rollback/run-rollback.sh`、`src/infra/azure/verify-webui-resources.sh`、`src/infra/azure/rollback/ui-staticwebapps-rollback.md`が存在しないため、当該Workflowと現役Workflow一覧からの参照を除去する。将来rollback drillを再導入する場合は、対象環境、実行script、検証script、復旧手順、Azure権限、production承認、受入テストを同一featureで先に定義し、本要件を改訂しなければならない。
- **FR-WF-ASDW-06**: ASDW-WEB Step.2.1 は AAD-WEB Step.2.5 と同じ Custom Agent（`Dev-Microservice-Azure-AddServiceDesign`）で同じ成果物 `docs/azure/azure-services-additional.md` を扱う。ASDW-WEB Step.2.1 の本文は、既存の成果物がある場合はそれを読み、本 Workflow で確定した Azure のデータ層・コンピュートを反映して変わる点の差分だけを追記させ、既存の記述を削除・再生成させてはならない。既存の成果物が無い場合は新規に作成させる。Step は削除しない（AAD-WEB を実行せずに ASDW-WEB を実行する経路と、Azure 設計の反映という更新の役割があるため）。出典: 利用者依頼（2026-09-30）で指定された `work/202609301045-DAGReviewPlan.md` N5-1（review report §4.2）。

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
- **FR-WF-ADFD-03**: 4 Step の `output_paths` は確定ファイル名 1 件ずつを宣言し、DAG 根が成果物を寄与する状態を維持する。これにより `collect_workflow_output_paths` は 4 Step の確定ファイルを具体パスとして返す。
- **FR-WF-ADFD-04**: 消費側 Agent が文字列一致で検査する見出しは変更してはならない。`dataflow-app-catalog.md` は `## 1. ジョブ一覧表`、`dataflow-service-catalog.md` は `## 2. ジョブ → Azure サービスマッピング表` を含むこと（`.github/prompts/Dev-Dataflow-*.prompt.md` の依存確認テーブルの停止条件）。`dataflow-test-strategy.md` は「テストダブル戦略」節に Azurite / Testcontainers の利用有無を断定形で記載すること（`Dev-Dataflow-TestCoding` が参照）。

### 13.5 ADFDV — Dataflow Dev

> 旧称は **ABDV（Batch Dev）**。データフロー処理へのリネームに伴い workflow ID は `adfdv`、
> 生成先は `batch` から `dataflow` へ移行している。本節は
> [hve/workflow_registry.py](hve/workflow_registry.py) の実定義を正として記述する。

| Step | タイトル | Custom Agent | 依存 | Fan-out | 生成カテゴリ |
|---|---|---|---|---|---|
| 1.1 | データサービス選定 | Dev-Dataflow-DataServiceSelect | — | — | `src/infra/azure/dataflow/create-batch-resources.sh`、`src/infra/azure/dataflow/verify-batch-resources.sh` |
| 1.2 | Azure データリソース Deploy | Dev-Dataflow-DataDeploy | 1.1 | — | Azure データリソース実体（リポジトリ内成果物なし。[hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) `ALLOWED_EMPTY_OUTPUT_PATHS_STEPS` の唯一の残件） |
| 2.1 | TDD RED — テストコード作成 | Dev-Dataflow-TestCoding | 1.2 | `dataflow_catalog` | `src/test/dataflow/{jobId}-{jobNameSlug}.Tests/` |
| 2.2 | TDD GREEN — データフローアプリ本実装 | Dev-Dataflow-ServiceCoding | 2.1 | `dataflow_catalog` | `src/dataflow/{jobId}-{jobNameSlug}/` |
| 3 | Azure Functions/コンテナ Deploy | Dev-Dataflow-FunctionsDeploy | 2.2 | — | `.github/workflows/deploy-batch-functions.yml`、`src/infra/azure/dataflow/README.md` |
| 4.1 | WAF レビュー | QA-AzureArchitectureReview | 3 | — | `docs/azure/waf-review.md` |
| 4.2 | 整合性チェック | QA-AzureDependencyReview | 3 | — | `docs/azure/dependency-review.md` |
| 4.3 | 要件適合実測 | QA-RequirementsConformanceEval | 4.1, 4.2 | — | `docs/dataflow/requirements-conformance-report.md` |

- **FR-WF-ADFDV-01**: Step 2.1 / 2.2 の fan-out parser は `dataflow_catalog` とする。キー元は `docs/catalog/app-arch-catalog.md` を優先し、推薦アーキテクチャがデータフロー処理に該当する APP-ID を抽出する。同ファイルが未生成または該当 APP-ID を解決できない場合は `docs/catalog/app-catalog.md` の全 APP-ID へフォールバックする。この primary / fallback は [hve/catalog_parsers.py](hve/catalog_parsers.py) `parse_dataflow_catalog` の実装契約に一致させる。`get_parser_input_path("dataflow_catalog")` は代表入力として fallback 側の `docs/catalog/app-catalog.md` だけを返す。
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
- **FR-WF-AAGD-04**: Cloud（Issue Template + GitHub Actions）でも FR-WF-AAG-01 の 3 値を選択でき、Root Issue のメタデータと各 Step Issue 本文へ同一値を伝搬しなければならない。Root の完了判定は、Issue のラベル状態だけでなく、checkout 済みブランチ上の設計・実装・Deploy・評価成果物を FR-WF-AAG-02 / FR-WF-AAGD-01〜03 と同じ検証で再確認し、不整合があれば fail-closed で停止しなければならない。

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
- **FR-WF-AAGD-10**: AAGD Step.1 は AAG Step.1 と同じ Custom Agent（`Arch-AIAgentDesign-Step1`）で同じ成果物 `docs/agent/agent-application-definition.md` を扱う。AAGD Step.1 の本文は、既存の成果物がある場合はそれを読み、Azure の設計と対象ユースケースを反映して変わる点の差分だけを追記させ、既存の記述を削除・再生成させてはならない。既存の成果物が無い場合は新規に作成させる。Step は削除しない（AAG を実行せずに AAGD を実行する経路と、Azure 設計の反映という更新の役割があるため）。出典: 利用者依頼（2026-09-30）で指定された `work/202609301045-DAGReviewPlan.md` N5-1（review report §4.2）。

### 13.8 AKM — Knowledge Management

- **fan-out キー**: 固定 `D01`〜`D21`（21 並列）。`max_parallel=21`。
- **同時更新防止**: `concurrency: akm-knowledge-write-${{ github.repository }}`（§4.4 FR-CLOUD-21）。
- **知識探索（v3.38）**: 実効知識源が `usable` の場合、DAG 実行前に「AKM 知識探索」phase を 1 回実行する（FR-KD-07）。knowledge の書込みは FR-KD-05 のロック・SHA-256 照合・原子的置換を使う。

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
- **実行経路**: CLI / GUI のみ（Cloud dispatcher 未対応。§3.2 の `adi` 行のとおり。Cloud にも対応する `ard`〈FR-WF-ARD-01〉とは扱いが異なる）。
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
- **FR-WF-ADI-18**: ADI Step 1.2 は D01〜D21 の 21 質問票を join して `qa/original-docs-cross-questionnaire.md` を生成し、Step 2 は Step 1.2 に `depends_on` しなければならない。v3.29（N5-2）で、原本質問票（Step 1.1 / 1.2）は人に質問する工程であり無人実行では答える人がいないため任意とし、Step 2 は `skip_fallback_deps=["1"]` を持ち、`qa/original-docs-cross-questionnaire.md` を必須入力としない（存在すれば参照してよい）。利用者が Step 1.1 / 1.2 を選ばない実行は Step 1 の後に Step 2 へ進む。v3.33 で、`StepDef.selected_by_default`（既定 True）を追加し、ADI Step 1.1 / 1.2 を False とした。Step を明示しない実行（CLI の `--steps` 省略、CLI ウィザードの Enter、GUI の初期チェック、Prompt 版の `steps` 省略とその計画に表示する完了条件）は、registry の `default_step_ids` を単一実装として既定の選択に従い、Step 1.1 / 1.2 を選ばない。全 Step が既定で選ばれる Workflow では `default_step_ids` は空（= 全ステップ）を返し、従来の意味を変えない。利用者が Step 1.1 / 1.2 を明示すれば従来どおり実行する。ADI の Cloud Issue Template は無いため Cloud は対象外である。Step 1.2 も質問 0 件を有効入力として扱い、summary 件数 `0` と明示的な「質問なし」を保持したまま join を完了しなければならない。
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
- **知識探索（v3.38）**: ローカル実行で Step 2 が実行対象かつ実効知識源（`ard_workiq_enabled=true` は `workiq` を加える）が `usable` の場合、DAG 実行前に「ARD 知識探索」phase を実行し、結果を Step 2 の Issue へコメントする（FR-KD-08）。旧 ARD Work IQ ユースケース参照は FR-KD-10 で廃止した。
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
  - **v3.40 明確化（Agent prompt の Skill 公開）**: Custom Agent prompt の「Agent 固有の Skills 依存」に列挙された repository Skill のうち、Step を実行する Workflow の `hve/skill_manifest.json`（`workflow_defaults` または Step 別 `required_skills`）で公開されていないものがあってはならない（未公開だと SDK セッションで `Skill not found` になり、参照が黙って欠落する）。v3.40 で `aas` に `input-file-validation` / `app-scope-resolution` / `knowledge-lookup` / `microservice-design-guide` / `markdown-query`、`ada` に `input-file-validation` / `app-scope-resolution` / `knowledge-lookup` / `markdown-query` を追加した。`hve/tests/test_agent_prompt_skill_manifest_parity.py` が `aas` Step 1 / 2.1 と `ada` Step 2 / 4.1 の Custom Agent についてこの整合を検査する（`tdd-red-green-reality` など他 Step の未公開は本改訂の対象外）。出典: システムテスト結果 F-03（同上）。

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

適用可能なゲートのいずれか 1 件でも未達のとき、Workflow は `done` ではなく `blocked` 扱いとし、手動介入の対象とする。`N/A` のゲートだけを理由に `blocked` としてはならない。

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
