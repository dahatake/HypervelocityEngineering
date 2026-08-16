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
| `adi` | Auto Design-doc Ingestion | **✗（dispatcher 未対応）** | ✓ | `purpose`, `target_scope`, `depth`, `focus_areas` |
| `adoc` | Source Code → Documentation | ✓ | ✓ | `target_dirs`, `exclude_patterns`, `doc_purpose`, `max_file_lines` |
| `ard` | Auto Requirement Definition | **✗（dispatcher 未対応）** | ✓ | `company_name`, `target_business`, `survey_base_date`, `survey_period_years`, `target_region`, `analysis_purpose`, `attached_docs`, `include_kpi_okr` |

\*¹ `enable_review` は Issue Template 入力には存在するが、`WorkflowDef.params` 宣言ではなく内部処理で扱われる。
\*² `workiq_akm_ingest_dxx` も同様に `WorkflowDef.params` には宣言されないが、`_collect_params_non_interactive` で `params` 経由に伝搬される。

旧独立の原本質問票処理は ADI に統合し、独立した Workflow ID・Cloud reusable workflow・CLI / GUI 選択肢として再公開してはならない。後方互換 alias も提供しない。

### 3.3 DAG 実行エンジン

- **FR-DAG-01**: Step の依存関係は AND join、並列 fork、スキップフォールバック（`skip_fallback_deps`）、ブロック（`block_unless`）の 4 パターンをサポートする（[hve/workflow_registry.py](hve/workflow_registry.py)）。
- **FR-DAG-02**: **計画段階**（[hve/dag_planner.py](hve/dag_planner.py)）で Wave 単位の論理プランを生成し、**実行段階**（[hve/dag_executor.py](hve/dag_executor.py)）で `asyncio.Semaphore(max_parallel)` により並列上限を制御する。
- **FR-DAG-03**: 並列上限の階層関係:
  - `WorkflowDef.max_parallel` 未指定 → DAGExecutor 既定値 **15**
  - 明示指定: `akm` = 21、`adi` = 21、`ard` = 15
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

### 3.4 状態ラベルとライフサイクル

- **FR-STATE-01**: 各 Workflow は `{prefix}:initialized` / `{prefix}:ready` / `{prefix}:running` / `{prefix}:done` / `{prefix}:blocked` の状態ラベルを保持する（`_make_state_labels`、[hve/workflow_registry.py](hve/workflow_registry.py)）。
- **FR-STATE-02**: `qa-ready` ラベルは Copilot アサインを保留する状態として明示的にスキップされ、質問票作成を担当する Copilot がアサインされた場合は `qa-drafting`（回答下書き中）へ遷移する。`auto-issue-qa-ready-transition.yml` は回答受領後に `qa-ready` または `qa-drafting` から `ready` への遷移を担当する。
  - 対象セット: `aas:qa-ready` / `aad:qa-ready` / `asdw:qa-ready` / `abd:qa-ready` / `abdv:qa-ready` / `aag:qa-ready` / `aagd:qa-ready` / `akm:qa-ready` / `adoc:qa-ready` / `aad-web:qa-ready` / `asdw-web:qa-ready`
  - **対象外**: `ard:qa-ready` は `qa_ready_labels` セットに含まれない
- **FR-STATE-03**: 完了ラベル `{prefix}:done` 付与時、Cloud Orchestrator は次の推奨 Workflow を Issue コメントで提示する。
  - チェーン定義: `AAS` → `AAD-WEB` / `ABD` / `AAG` の 3 候補（全提示・1 つ選択は利用者判断）、`AAD-WEB` → `ASDW-WEB`、`ABD` → `ABDV`、`AAG` → `AAGD`
  - **終端 Workflow（`ASDW-WEB` / `ABDV` / `AAGD` / `ADOC` / `AKM` / `ARD`）完了時は次候補が提示されない**

### 3.5 モデルと SDK

- **FR-MODEL-01**: 既定モデルは `claude-opus-4.7`。
  - `MODEL_CHOICES` は 4 値: `claude-opus-4.7`、`claude-opus-4.6`、`gpt-5.5`、`gpt-5.4`
  - 別途 `MODEL_AUTO_VALUE='Auto'` が許容される（[hve/config.py](hve/config.py)）
- **FR-MODEL-02**: `Auto` 指定時は SDK へ `model="auto"` (wire 値) を渡し、サーバ側 Auto Model Selection（GitHub Copilot の動的モデルルーティング）に委譲する。`reasoning_effort` はクライアント側で設定しない（サーバ側がモデル毎に適切な effort を選ぶ）。内部センチネル `MODEL_AUTO_VALUE='Auto'` → wire 値 `MODEL_AUTO_WIRE_VALUE='auto'` の変換は [hve/config.py](hve/config.py) の `to_wire_model()` 関数で集中管理。ユーザーが `reasoning_effort` を明示指定した場合は経路を問わず尊重する。SDK が `reasoning_effort` 引数を未サポートの場合は `TypeError` を捕捉し引数除外で再試行する（[hve/orchestrator.py](hve/orchestrator.py) `_create_session_with_auto_reasoning_fallback`）。
- **FR-MODEL-03**: 未サポート / 廃止モデルが渡された場合、ヘルパー `_normalize_model_with_warning` は警告を発出し `Auto` を返す（実際の呼び出し経路は要確認）。
- **FR-MODEL-04**: HVE は GitHub Copilot SDK の `create_session(tool_search=...)`（ツール定義の遅延ロード）を CLI / GUI から設定可能とする。有効時は SDK へ `tool_search={"enabled": True}` を渡し、無効時は当該引数を渡さない。**既定は有効**とする。設定値は Step 実行経路のメインセッション、サブセッション（Pre-QA / Review）、Self-Improve セッションへ同一値を伝搬しなければならない。Fleet mode 親セッション（[hve/orchestrator.py](hve/orchestrator.py)）は意図的にツール公開を狭めた別系統であり、当該経路の実測根拠がないため本要件の対象外とする。`defer_threshold` は SDK 既定に委ね、設定として公開しない。本要件の `SDKConfig.tool_search` は、AAGD ワークフローのパラメータ `enable_tool_search`（生成する AI Agent の Foundry Toolbox 設定）とは別ドメインであり、HVE 自身の SDK セッションにだけ作用する。本要件はツール定義がコンテキストの大きな割合を占める実態（実測: 登録 171 ツール / 54,865 tokens のうち実使用は 10 種 / 9,108 tokens）を背景とするが、**削減効果は本要件の受入対象外**とし、受入は設定の伝搬だけとする（[hve/config.py](hve/config.py)、[hve/runner.py](hve/runner.py)、[hve/self_improve.py](hve/self_improve.py)）。既定を無効から有効へ変更した根拠は利用者の適用方針決定であり、削減率の実測を根拠としてはならない。**2026-08-13 の実測（Copilot CLI 1.0.79 / SDK 1.0.7、`session.metadata.contextInfo`）では、`tool_search` の有効 / 無効 / `defer_threshold=1` の 3 条件で `toolDefinitionsTokens` が 52,756 で完全に一致し、全ツールの `defer_loading` が `null`、`tool_search_tool` もツール一覧に現れなかった。すなわち当該環境では遅延公開が一切発火しておらず、削減効果は 0 である。**この実測は既定有効を否定しない（コンテキストを増やさないため）が、本設定を削減手段として期待してはならない。
- **FR-MODEL-06**: FR-MODEL-04 の既定有効化は、利用者による明示的な無効化を上書きしてはならない。`--no-tool-search` と `HVE_TOOL_SEARCH` の falsy 値は無効として扱い、当該実行では SDK へ引数を渡さない。GUI では新規プロファイルの初期値だけを有効とし、**保存済み設定の値は移行・上書きしない**（保存済みの `false` が利用者の明示指定か旧既定かを区別できないため）。ランキング実装の既定（FR-TS-01 の `tool_search_ranking`）は本変更の対象外であり `sdk` のままとする。
- **FR-MODEL-05**: SDK が `tool_search` 引数を未サポートの場合、Step 実行経路のセッション生成（[hve/runner.py](hve/runner.py) `_create_session_with_auto_reasoning_fallback`）は `TypeError` を捕捉して当該引数を除外し再試行しなければならない。未サポートを理由に実行を停止してはならない（既存の `reasoning_effort` 縮退規則に従う）。
- **FR-MODEL-07**: 開発環境セットアップ（[hve/setup-hve.sh](hve/setup-hve.sh) / [hve/setup-hve.ps1](hve/setup-hve.ps1)）は、`github-copilot-sdk` の導入版を単一の宣言ファイル [hve/copilot-sdk.lock](hve/copilot-sdk.lock) で固定しなければならない。最新版への更新は明示フラグ（`--upgrade-sdk` / `-UpgradeSdk`）を指定したときにだけ行い、その際に当該ファイルの pin 行と Copilot CLI ランタイム版の記録行を書き換えなければならない。既定経路で `--upgrade` してはならない。あわせてセットアップは、SDK が pin する Copilot CLI ランタイム（`copilot/_cli_version.py` の `CLI_VERSION`）を先読みし、実際に解決されるランタイムの埋め込み版と突合して不一致を警告しなければならない。埋め込み版の取得には `--no-auto-update` を付与しなければならない（`--version` 単体はオンライン更新チェックの結果である「最新利用可能版」を返すため pin との突合に使えない。実測: 埋め込み 1.0.69 のバイナリが `--version` では 1.0.78 を返す）。pin を無効化する環境変数 `COPILOT_CLI_PATH` / `COPILOT_CLI_EXTRACT_DIR` / `COPILOT_SKIP_CLI_DOWNLOAD` が設定されている場合は警告しなければならない。本要件は、SDK の生成イベントパーサ（`copilot/generated/session_events.py`）がイベントのエンベロープ（`id` / `timestamp` / `type`）を assert で固めており、pin と異なるランタイムを掴むと `session.event` の解析が `AssertionError` となって当該イベントが黙って捨てられる（終端イベントを取り逃すと `send_and_wait` がタイムアウトまで返らない）ことへの予防である。`pyproject.toml` の下限指定は API 互換の床であり、導入版の情報源としてはならない。

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
- **FR-TS-11**: Step 実行セッションのコンテキスト内訳を実測する CLI を提供しなければならない。`hve toolsearch context` は、[hve/runner.py](hve/runner.py) `_create_session_with_auto_reasoning_fallback` と同じ経路でセッションを生成し、`session.metadata.contextInfo` と `session.metadata.getContextAttribution` から、システムプロンプト / 組み込みツール定義 / MCP サーバー別の実トークン量とツール数を取得してテキストまたは JSON（`--json`）で出力する。`session.send` を行ってはならず、モデル推論を発生させてはならない。`hve/toolsearch/eval.py` のトークン推定で代替してはならない。測定に用いたモデル名（`contextInfo.modelName`）を出力に含めなければならない。`.github/.mcp.json` が宣言する MCP サーバーの接続完了を待ってから測定し、待っても接続しなかったサーバーは未接続として報告しなければならない（実測: stdio の `azure` は接続に 3.7〜5.1 秒）。測定に失敗した場合は非 0 の終了コードと失敗理由を返し、推定値や前回値で埋めてはならない。取得と整形の実装は単一とし、GUI（FR-GUI-07）は本 CLI を呼び出すか同じ実装を共有しなければならない（FR-MAINT-07）。

### 3.6 セキュリティ

- **NFR-SEC-01**: `GH_TOKEN`・`COPILOT_PAT` 等の秘密情報を Issue body / 標準出力に出力してはならない。Resume 用 `state.json` と `config_snapshot` 復元は §5.6 のとおり廃止済みであり、現行要件ではない。
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

- **FR-MAINT-01**: Coding Agent は HVE 対象ファイルを変更する前に、`hve-dev/hve-feature-inventory.csv` を索引として適用候補を絞り込み、`hve-dev/requirement-definition.md` の関連箇所と `hve-dev/requirement-test-mapping.md` の対応箇所を確認しなければならない。適用できる要件 ID は、要求定義書を source とし、索引上 `active-or-described` であるものに限る。未知、競合、`deprecated-or-removed`、`partial-or-not-supported` の ID を現行要件として適用してはならない。新規 ID を追加する bootstrap 中は要求定義書の定義行を一次情報とし、要求テストマッピングと RED テストを追加後、実装前に索引を再生成して当該 ID・source・status・テストパスを照合する。既存 ID では索引と要求定義書が矛盾した場合、推測せず不整合を解消してから実装へ進む。
- **FR-MAINT-02**: Coding Agent は要求書全文を既定の入力にせず、Issue 本文、対象パス、対象 symbol、失敗テスト、Workflow / Step ID を検索キーとして関連チャンクを取得する。初回取得で不足する場合に限り、親見出し、隣接チャンク、関連章の順に一段ずつ拡張する。0 件または矛盾時は検索語を変えて最大 2 回再試行し、それでも解消できなければ理由を記録して確認を求める。索引欠損・stale・検索 CLI 障害時は、既に特定した要求 ID または見出しの限定範囲を read / grep で取得し、要求書全文へ自動 fallback しない。本規則は HVE 要件検索において汎用 Markdown 検索 fallback より優先する。全文取得は、ユーザーの明示要求、要求定義書自体の横断改訂、または章単位でも解消できない複数章の矛盾がある場合に限る。
- **FR-MAINT-03**: `feature` 変更は、要求定義への active 要件追加または改訂 → 要求テストマッピングへの受入テスト追加（未実装時は `要追加`）→ 失敗するテストの作成と RED 確認 → 機能・テスト索引の再生成と新規 ID / test path の照合 → 実装 → 同じ対象テストの GREEN 確認 → 要求テストマッピングへの実結果反映、の順で行う。`feature` では要件 ID、実在テストパス、RED / GREEN 証跡の省略を認めない。`bugfix` / `maintenance` で要件またはテストを `N/A` とする場合は、前項のブロックへ具体的理由と人間レビュー必須を記録する。`hve-dev/hve-tdd-change-policy.md` と生成元が本節と矛盾する場合は本節を正とし、同一変更で同期する。本要件の初回導入では、下記「本要件の導入ゲート」を FR-MAINT-03 の従属規範として適用する。
- **FR-MAINT-04**: HVE 対象変更を含む PR は、前項のトレーサビリティブロックを記録しなければならない。CI は変更パス取得失敗、ブロックの欠落・重複・未置換値、組合せ違反、未知または索引statusが `active-or-described` 以外の ID、存在しない・リポジトリ外・許可テストルート外のパス、要件 ID と要求テストマッピング上の test path 不一致を拒否する。`feature` では要求定義、要求テストマッピング、機能索引の更新と RED / GREEN 証跡を追加で要求する。N/A と変更種別の意味的妥当性は CI が推測せず、既存 branch protection の承認レビューで確認する。HVE 対象外の変更のみである場合は本ゲートを適用しない。validator の正規entrypointは `.github/scripts/validate-hve-requirement-traceability.py` とし、リポジトリroot、PR本文ファイル、変更パス一覧ファイルを明示入力として受け取る。PR workflow は `pull_request` イベントだけで当該 validator を必須ゲートとして実行し、PR本文を shell の `run` へ直接展開せず、最小読取権限で実行する。既定ブランチで実行するtrusted workflowは `pull_request_target` を使用し、base側validatorとPR内容を別ディレクトリへcheckoutし、PR内容はデータとして検証するだけで実行してはならない。branch protection の required status check は両workflow名とvalidator job名から構成されるcheck contextを含み、既存の承認レビュー要求を維持する。
- **NFR-CTX-01**: repository-wide instructions のうち **HVE 要求トレーサビリティに関する記述**は検索ルーターだけを保持し、要求定義書本文を埋め込んではならない。当該ルーターは、(1) HVE 対象変更で `hve-requirement-traceability` Skill を使用する、(2) HVE コアパスでは path-specific instructions も適用する、(3) 要求定義書全文を既定の入力にしない、の 3 箇条だけで構成する。CI はルーターの見出し・3 箇条・Skill 参照・要求書パス・既知の要件 ID / schema key /取得オプションの重複を決定論的に検査する。Coding Agent は customization の raw source を入力として受け取るため、既知識別子の重複検査は HTML comment、code span、fenced / indented code を含むルーター外の raw source 全体を対象とする。言い換えによる意味的な分散・矛盾は捏造して判定せず人間レビューへ委ねる。他のリポジトリ共通ルールは本要件の対象外とする。初回の関連要件取得は最大 5 チャンクかつ最大 800 tokens を上限とし、追加コンテキストは FR-MAINT-02 の段階的拡張でのみ取得する。

#### 本要件の導入ゲート

FR-MAINT-01〜04 / NFR-CTX-01 の追加後、要求テストマッピング、RED 契約テスト、TDD policy の生成元、機能・テスト索引、PR validator / workflow を同一変更セットで同期し、全契約テストを GREEN にするまで、HVE 保守機能の実装完了を宣言してはならない。途中状態では新規 ID が索引に無いことを理由に既存要件へ偽装せず、bootstrap 中であることを明記する。

#### 実行面横断の重複実装防止

HVE は Cloud Agent Orchestrator / CLI Orchestrator / GUI Orchestrator の 3 実行面と、それらが共有する中核モジュールから構成される。同一の規範ルールが複数の実行面へ個別に実装されると、受理集合や検査項目が面ごとに乖離する。本項はその乖離を機械的に検出可能にする。

本項で **規範リテラル** とは、`.github/copilot-instructions.md` または Skill が規定するルールを機械判定するために実装が直接参照する固定文字列またはキー名を指す。

- **FR-MAINT-05**: HVE 対象の実装シンボル索引を `hve-dev/hve-surface-inventory.csv` として機械生成する。生成の正規 entrypoint は `hve-dev/generate_tdd_inventory.py` とする。索引対象は §3.7 対象境界の判定に一致するパスだけとし、当該判定は「対象パスの機械判定は単一の validator に集約する」原則に従って既存判定を再利用し、別の範囲定義を作ってはならない。索引は同一入力に対して決定的に生成し、対象外パスに由来する行を含めてはならない。索引の各行は、実行面（`cloud` / `cli` / `gui` / `core`）、シンボル種別、定義ファイルと行、振る舞い要約、当該シンボルが参照する規範リテラルの集合を保持する。CI は、生成スクリプトの出力と索引が不一致の場合、または対象外パスの行を含む場合に失敗させる。不一致の索引は stale として扱い、再生成するまで FR-MAINT-06 / FR-MAINT-07 の判断根拠に使ってはならない。参照数を表す列は静的解析による値であり、CI から `pytest <path>` や `python -m <module>` で起動される経路を数えない。当該列だけを根拠に未使用と判断してはならない。本索引は HVE アプリケーション自体だけを対象とし、HVE が生成・支援する他アプリケーションの成果物を含めてはならない。後者のスコープ解決は `app-scope-resolution` Skill と生成物側のカタログが担う。
- **FR-MAINT-06**: 規範リテラルを判定する実装は、リテラルごとに単一とする。同一の規範リテラル（例: タスク完了報告の検証マーカー、`plan.md` の分割判定メタデータ）を判定する実装が複数の実行面に併存してはならず、他面は単一の実装を呼び出す。CI は FR-MAINT-05 の索引を用いて、規範リテラルごとの判定実装数を決定論的に検査し、許可された単一実装以外を検出した場合は失敗させる。検査対象の規範リテラルと許可実装は明示リストで固定し、リストに無いリテラルを推測して判定してはならない。規範リテラルを**生成する**側の文言複製は本要件の対象外とする。複製の維持を意図する根拠文書がリポジトリ内に存在する箇所（vendoring 等）も対象外とし、その根拠を許可リストに明記する。
- **FR-MAINT-07**: Coding Agent は、HVE 対象パスへ新規の判定・生成・検証ロジックを追加する前に、FR-MAINT-05 の索引を用いて既存実装の有無を確認しなければならない。確認は規範リテラル一致 → 振る舞い要約 → シンボル名の順に行う。この順序は、名前や構文の類似だけでは識別子の異なる同一手続きへ到達できないために定める。シンボル名の不一致だけを根拠に既存実装が無いと判断してはならない。複数の実行面に同一ルールの実装が存在する場合は新規実装を追加せず、単一実装へ寄せる。索引に一致が無い場合に限り新規実装を許可し、どの実行面を単一実装とするかをタスク完了報告へ記録する。本手順は `hve-requirement-traceability` Skill に置き、NFR-CTX-01 を維持するため repository-wide instructions へ手順本文を追加してはならない。本手順は HVE 対象変更にだけ適用し、HVE が生成・支援する他アプリケーションの成果物には適用しない。

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

- **FR-RTO-01**: 実行時観測イベントの構築と解析は単一実装とする（FR-MAINT-07）。既存 `[hve:stats]` 行形式および既存の `kind` / `step` キーを維持したうえで、`schema_version` / `ts` / `seq` / `pid` / `run_id` / `workflow_id` / `instance_id` を付加する。`instance_id` は `workflow_id` とし、APP 単位で並列実行する経路では `workflow_id#app_id` とする。既存キーの意味を変更してはならない。未知の `kind` は解析可能とし、無言で捨てずに件数を計上する。
- **FR-RTO-02**: 「収集」「保存」「子プロセスへの配信」「人間向け表示」を分離する。`[hve:stats]` 行の stdout 出力は、GUI 子プロセス（`HVE_GUI_SESSION_ID` 設定時）および Dashboard を持つ親プロセスが環境変数 `HVE_STATS_STREAM=1` を付与して起動した子プロセスに限る。当該判定に新規 CLI オプションを用いてはならない（NFR-RTO-02）。通常 CLI、CUI Workbench、非 TTY 実行では stdout へ出力せず、CUI Workbench の本文ペインにも表示しない。`quiet` および `final_only` でも収集・保存・子プロセス配信は継続し、人間向けの追加表示だけを抑止する（NFR-OBS-03 と矛盾させない）。
- **FR-RTO-03**: 観測イベントは実行プロセスが `resolve_work_root()` 配下の `observability/events-<pid>.jsonl` へ追記する。`HVE_WORK_ROOT` 未設定時および dry-run では書き込まない。同一プロセス内の追記は直列化する。形式は UTF-8 / LF / BOM なしの 1 行 1 JSON とする。ファイルサイズが 32 MiB に達した場合は追記を停止し、その事実を 1 回だけ警告する（ローテーションは行わない）。プロセス内の順序は `seq` により厳密とし、プロセス間の時刻順序は近似であることを明示する。
- **FR-RTO-04**: 永続化する項目は allowlist 方式とし、状態、時刻、数値、モデル ID、Step / Workflow / APP 識別子、例外型名、リポジトリルート相対パスに限る。prompt 本文、応答本文、reasoning 本文、tool の引数・出力、環境変数、認証情報、認証 URL、生 SDK ペイロードを保存してはならない（NFR-SEC-01）。相対化の基準は実行プロセスの作業ディレクトリ（リポジトリルート）とし、当該ルート配下へ相対化できないパスは保存しない。
- **FR-RTO-05**: 各実行面は同一のイベント列から同一の集計値を表示する。表示は instance 単位で分離し、run 単位で合算する。未取得値を推定で補わず、取得できない項目は `-` として表示する。
- **FR-RTO-06**: 観測記録のライフサイクルは実行プロセスが所有し、`run_workflow` の終了時に確実にクローズする。GUI 親プロセスは観測ファイルを書き込まない。GUI セッション作業ディレクトリの後処理（`keep` / `archive` / `purge`）が観測ファイルに起因して失敗してはならない。
- **FR-RTO-07**: 実行履歴の Step 別表示は Step 単位で分離する。Step の Context、AI Credit、モデル、ツール、Skill は当該 Step へ帰属したイベント（`step` フィールドが当該 Step であるもの）だけから算出し、実行面のグローバル現在値、Workflow 累積値、他 Step の値で代替してはならない。Step へ帰属したイベントが 1 件も無い項目は `-` として表示し、隣接 Step の累積値の差分などの推定値で補ってはならない（FR-RTO-05）。実行面が Step 帰属を解決できない経路の消費も、Workflow 単位の累積値へは計上しなければならない。当該累積値が Step 別内訳の合計と一致しない場合は、その理由を表示上明示しなければならない。SDK Fleet mode へ委譲した Wave では、worker と Step の対応が当該 Wave の Step 集合に対して一意に定まる場合にだけ当該 Step へ帰属させ、一意に定まらない場合は Wave 内のいずれの Step へも割り当ててはならない。対応の解決に用いた入力（tool の引数等）を観測イベントへ保存してはならない（FR-RTO-04）。また、実行識別子（`run_id`）が未確定の時点で開始した実行を、識別子の確定後に別実行として二重に計上してはならない。

### 3.12 QA 質問票の説明深度

本節は、QA 質問票の各質問が利用者の意思決定に足る説明を伴うことを規定する。対象は [hve/prompts.py](hve/prompts.py) の質問票生成プロンプト（`PRE_EXECUTION_QA_PROMPT_V2` / `QA_PROMPT_V2`）と、その出力を保持・提示するパイプラインとする。質問の件数・重要度分類・既定値候補の採用ロジックは本節の対象外とする。

- **FR-QA-01**: 質問票生成プロンプトは、各質問に「背景と根拠」と「判断の観点」を必須項目として出力させなければならない。「背景と根拠」は、判断材料として確認した対象（出典）、そこから確定した事項と確定していない事項、および当該未確定が質問に値する理由を含めなければならない。確認していない場合は「未確認」と記載させ、出典を推測で記載させてはならない。「判断の観点」は、回答によって結論が変わる評価軸を 2 つ以上挙げ、主要な選択肢が各軸で有利・不利のいずれとなるかを示さなければならない。「既定値候補の理由」は、当該選択を支持する根拠となる事実、優先した評価軸、および他の選択肢を既定値としなかった理由を含めなければならない。各項目の値は 1 行で記述させ、結論のみの記述を許してはならない。本要件は事前 QA（メインタスク実行前）と事後 QA（成果物に対する QA）の双方へ同一の項目定義で適用する。
- **FR-QA-02**: QA 質問票のパイプラインは FR-QA-01 の 2 項目を欠落させてはならない。[hve/qa_merger.py](hve/qa_merger.py) は当該 2 項目を構造化質問票（`[Qxx]` 形式）およびマージ済みテーブル形式の双方で解析し、`render_merged` の出力へ列として保持しなければならない。当該 2 項目を持たない既存の質問票ファイルは空値として扱い、解析を失敗させてはならない。CLI は [hve/console.py](hve/console.py) の質問票表示で当該 2 項目を提示しなければならない。ただし既存の質問票テーブルへ列として追加してはならず、テーブルとは別の形式で提示する（列追加は既存列の可読幅を損なうため）。GUI の QA 回答ダイアログ（[hve/gui/qa_answer_dialog.py](hve/gui/qa_answer_dialog.py)）は当該 2 項目を回答入力前に参照できるよう表示しなければならない。質問票フォーマットを規定する Skill（[.github/skills/task-questionnaire/SKILL.md](.github/skills/task-questionnaire/SKILL.md) および `references/` 配下のテンプレート）は、プロンプトと同一の項目定義を保持しなければならない。経路によって項目定義が異なってはならない。
- **FR-QA-03**: `auto_qa` が有効な Knowledge Management (`akm`) 以外の Workflow は、質問が 1 件以上ある事前 QA について、ユーザー回答または明示された既定値を全質問へ適用した回答済み Markdown を `qa/` 配下へ保存し、最終パスを再読込して内容・質問数・各質問の非空回答を検証した後でなければメインタスクを開始してはならない。回答済み Markdown の表セルは、Work IQ 応答を含め、CR / LF / pipe を含む入力でも 1 質問 1 物理行を維持し、render → 保存 → 再解析の往復で質問数と全回答を失ってはならない。Work IQ 回答案へ統合できるのは、SDK の `tool.execution_start` イベントから Work IQ 用として許可された MCP server/tool の組を確認でき、かつ応答 status が `FOUND` または `PARTIAL` の結果だけとする。tool 名だけの一致を実行確認としてはならない。`FOUND` / `PARTIAL` は一次情報が少なくとも一部見つかった結果であるため統合対象とする。`NOT_FOUND` は既定回答を変更する一次情報が見つからず、`UNAVAILABLE` / status 不明 / tool 実行未確認は検索または出典を検証できないため、いずれも検証済み回答へ統合せず、調査用 draft にだけ未確認として保持する。質問が 0 件の場合は同期対象なしとしてメインタスクを継続する。FR-QA-05 の `qa_akm_background_merge` が有効な場合に限り、検証済み QA ファイル 1 件ごとに `sources=qa`、`target_files=<当該ファイル>`、`force_refresh=false`、`auto_qa=false` の AKM 差分更新を別のバックグラウンド実行として登録し、登録キューが当該要求を受理した時点で **QA を生成した source Workflow の親 DAG** は AKM 完了を待たず次 Step へ進めなければならない。CLI / GUI のバックグラウンド AKM と明示実行 AKM は同一リポジトリ内で直列化し、親 Workflow の Git 後処理・branch 切替・GUI cleanup より前に未完了の書込みを安全に終了または取消できなければならない。branch / PR を作る親実行では、AKM が出典として使用した検証済み QA ファイルだけを knowledge 変更とともに commit 対象へ含める。ADI も本要件の対象とし、Step 1.1 / 1.2 が生成する原本質問票 main 成果物は事前 QA の回答済み補助ファイルとは別成果物として扱う。`workflow_id=akm` の実行は QA 起点 AKM 登録を行ってはならず、AKM Root Issue から別の QA 起点 AKM を再帰生成してはならない。ファイル単位の起動とリポジトリ単位の直列化は、複数 Step が回答を保存した場合にも各回答を早期反映しつつ、共有する `knowledge/` への同時書込みと差分喪失を防ぐために必要な最小境界である。
- **FR-QA-04**: FR-QA-03 の QA 起点 AKM に対して、利用者は AKM 子実行が使うモデル・reasoning effort・context tier を、メインタスクの実行品質設定とは独立に選択できなければならない。設定キーは `akm_model` / `akm_reasoning_effort` / `akm_context_tier` とし、CLI は `--akm-model` / `--akm-reasoning-effort` / `--akm-context-tier` で受け取る。いずれも未指定を既定とし、未指定のキーは対応するメイン設定（`model` / `reasoning_effort` / `context_tier`）を継承しなければならない。`reasoning_effort` / `context_tier` には既存の環境変数経路が存在しないため（[hve/config.py](hve/config.py) `SDKConfig.from_env`）、本設定にも環境変数経路を新設してはならない。継承の解決は QA 起点 AKM 子プロセスの引数生成（[hve/qa_akm_dispatch.py](hve/qa_akm_dispatch.py) `QaAkmCoordinator._build_argv`）だけで行い、メインタスク・敵対的レビュー・QA 質問票生成のセッション生成へ本設定を適用してはならない。`--workflow akm` を明示指定した実行は本設定の適用対象外とし、従来どおり `--model` / `--reasoning-effort` / `--context-tier` に従わなければならない。CLI 対話 wizard は `auto_qa` を有効化した非 AKM Workflow のときにだけ本 3 項目を尋ね、既定は継承としなければならない。モデル値は既存のモデル正規化（[hve/config.py](hve/config.py) `_normalize_model_with_warning`）と同一の規則で検証しなければならない。本設定は AKM が扱う `knowledge/` の更新粒度と、メインタスクの実行品質・コストを独立に決められるようにするために必要であり、既定の継承によって既存実行の挙動を変えてはならない。
- **FR-QA-05**: FR-QA-03 の QA 起点 AKM をバックグラウンドで起動するかどうかは、利用者が明示的に選択できる設定 `qa_akm_background_merge` で制御しなければならない。既定は無効とし、無効のときは QA 起点 AKM を登録・dispatch してはならない。CLI は `--qa-akm-background-merge` で受け取り、CLI 対話 wizard は `auto_qa` を有効化した非 AKM Workflow のときにだけ本設定を尋ね、既定は無効としなければならない。GUI は設定画面と Step 1 右ペインの双方で選択でき（FR-GUI-20）、Cloud は Issue Form の入力で選択できなければならない（FR-CLOUD-26）。本設定が無効のとき、CLI 対話 wizard は FR-QA-04 の 3 項目を尋ねてはならず、GUI は当該 3 項目を非活性とし値を CLI へ渡してはならない（AKM 子実行自体が起きないため）。判定の実装は実行面ごとに 1 箇所へ限定し、CLI / GUI は [hve/orchestrator.py](hve/orchestrator.py) `_should_enable_qa_akm_dispatch`、Cloud は [.github/workflows/auto-issue-qa-ready-transition.yml](.github/workflows/auto-issue-qa-ready-transition.yml) の `save-qa-answer` job が出力する `sync_required` だけが判定してよい。同一面に判定を重複実装してはならない。FR-QA-04 と同様に環境変数経路を新設してはならない。`--workflow akm` を明示指定した実行は従来どおり本設定の対象外とする。本設定は、QA 回答のたびに `knowledge/` が更新されコスト・実行時間・差分レビュー量が増えることを利用者が制御できるようにするために必要であり、既定を無効とするのは、利用者が明示的に選択していない共有資産（`knowledge/`）への自動書込みを行わないためである。

---

## 4. HVE Cloud Agent Orchestrator 固有要件

### 4.1 トリガー仕様

- **FR-CLOUD-01**: 監視イベントは `issues` の `opened` / `labeled` / `closed` の 3 種（[.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)）。
- **FR-CLOUD-02**: 起動はラベルベース。`trigger_map` に従い、対応する `auto-*-reusable.yml` を `workflow_call` で起動する。
- **FR-CLOUD-03**: `opened` イベントでは `author_association` が `OWNER` / `MEMBER` / `COLLABORATOR` のいずれかである場合のみ起動する。**`labeled` / `closed` イベントには `author_association` ガードは適用されない**。
- **FR-CLOUD-04**: `closed` イベントでは Issue タイトルの `[AAS]` / `[AAD-WEB]` 等プレフィックスから対象 Workflow を判定する。
- **FR-CLOUD-05**: `setup-labels` ラベル付与時は `setup-labels.yml` を起動する。
- **FR-CLOUD-06**: registry と同期していない Cloud reusable workflow を dispatcher から起動してはならない。[.github/workflows/auto-app-dev-microservice-web-reusable.yml](.github/workflows/auto-app-dev-microservice-web-reusable.yml) は [hve/workflow_registry.py](hve/workflow_registry.py) の ASDW-WEB Step 体系と非同期（ファイル冒頭で OUT-OF-SYNC NOTICE を自己申告）であるため、ASDW-WEB の Cloud 起動を停止し、CLI / GUI 経路が supported であることを明示する（[.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml)）。他の Cloud workflow の挙動は変更しない。

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
| `emit-prompt` | Step のプロンプトを表示（デバッグ用） |

### 5.2 `orchestrate` の必須・主要オプション

- **FR-CLI-01**: 必須引数は `--workflow / -w`（Workflow ID）のみ。
- **FR-CLI-02**: 主要オプション一覧:
  - **モデル**: `--model`、`--review-model`、`--qa-model`、`--akm-model`（FR-QA-04）
  - **実行品質**: `--reasoning-effort`、`--review-reasoning-effort`、`--qa-reasoning-effort`、`--akm-reasoning-effort`、`--context-tier`、`--akm-context-tier`（FR-QA-04）
  - **並列制御**: `--max-parallel`（既定 15）
  - **自動レビュー**: `--auto-qa`、`--auto-contents-review`、`--auto-coding-agent-review`、`--auto-coding-agent-review-auto-approval`
  - **対話制御**: `--force-interactive`（QA 回答入力の TTY 判定をバイパスし対話モードを強制）
  - **Work IQ**: `--workiq`、`--workiq-akm-review`、`--workiq-akm-ingest`、`--workiq-dxx`、`--workiq-draft`、`--workiq-tenant-id`、`--workiq-prompt-{qa,km,review}`、`--workiq-per-question-timeout`
  - **Git/PR**: `--create-issues`、`--create-pr`、`--ignore-paths`、`--branch`、`--repo`
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

- **FR-CLI-10**: `python -m hve`（引数なし）または `python -m hve run` は対話 wizard を起動する。
- **FR-CLI-11**: wizard はクイック全自動モードと詳細モードを提供し、Workflow 固有パラメータを順次収集する。
- **FR-CLI-12**: ARD wizard は Step 1〜3 をマルチ選択させ、Step 1 選択時のみ `company_name` を必須、Step 2 単独実行時のみ `target_business` を必須とする。
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
- **FR-CLI-76**: Step 実行経路のセッション生成（[hve/runner.py](hve/runner.py) `_create_session_with_auto_reasoning_fallback`）は、呼び出し側が `mcp_servers` を明示していない場合、リポジトリが宣言した `.github/.mcp.json` の `mcpServers` を `mcp_servers` として渡し、あわせて `enable_config_discovery=False` を指定しなければならない。ワークスペース / ユーザースコープ / プラグイン由来の MCP サーバを自動探索で取り込んではならない。この結果、リポジトリが宣言していない MCP サーバ（実測環境では `github-mcp-server` / `workiq` / プラグイン由来の `azure`）は Step 実行セッションから外れる。`.github/.mcp.json` が存在しない・読み取れない・`mcpServers` が dict でない・`mcpServers` が空の場合は `mcp_servers` を渡さず、`enable_config_discovery` は従来どおり `True` とする（リポジトリが MCP を宣言していない作業ディレクトリでの回帰を避けるため）。呼び出し側が `mcp_servers` または `enable_config_discovery` を明示している経路（`_require_trusted_asdw_data_deploy_mcp_servers` / `_require_trusted_foundry_mcp_servers` / `SDKConfig.mcp_servers` / Work IQ を有効化した QA サブセッション）の挙動は変更してはならない。これらの経路では自動探索が残るが、Step 実行の主経路（各 Step のメインセッション）を縮約することを本要件の受入範囲とする。SDK が `enable_config_discovery` を未サポートの場合、既存規則どおり当該引数を剥がして再試行せず停止する（自動探索の再有効化を伴う縮退を禁じる既存の分離境界規則が、本要件により全 Step へ適用される）。Skill の公開範囲は FR-CLI-73 が定める `skill_directories` の明示指定で維持する。`.github/.mcp.json` の各サーバ定義は `tools` キー（`["*"]` = 全件 / `[]` = なし）を明示しなければならない。明示指定した MCP サーバ設定に `tools` キーが無いと、当該サーバは起動されずツールが 1 件も公開されない（実測: `azure` を `tools` なしで明示指定すると connected 0 件・ツール 0 件、`"tools": ["*"]` を付けると connected かつ 68 ツール。`type: "stdio"` の付与では解決しない）。同じ制約は `_require_trusted_foundry_mcp_servers` が渡す設定にも適用される。本要件は FR-TS-03 の pin ポリシー判定を変更しない（`pin_only` の判定は `hve/toolsearch/policy.json` の `step_overrides` だけで決まり、`enable_config_discovery` を参照しない）。本要件は次の実測（Copilot CLI 1.0.79 / SDK 1.0.7、`session.metadata.contextInfo`、model=`claude-sonnet-4.5`、会話 0）を根拠とする: 自動探索が有効なとき、リポジトリが宣言していないユーザースコープ設定・プラグイン由来の MCP サーバが全件接続され、ツール定義は 52,756 tokens（うち MCP 41,096）を占めた。重複していた MCP サーバ 2 系統を環境側で除いた後でも 33,384 tokens（うち MCP 21,728）だった。自動探索を無効にすると同環境で 11,403 tokens（MCP 0）になる。本要件の実装後、`.github/.mcp.json` が宣言する 2 サーバ（`azure` 68 ツール / `microsoft-learn` 3 ツール）だけを公開した Step セッションは 28,763 tokens（MCP 17,217）で、同環境の自動探索有効時 33,527 tokens（MCP 21,728）に対し 4,764 tokens 少ない。あわせて、自動探索は `.github/.mcp.json` を探索対象としておらず（探索対象は作業ディレクトリ直下の `.mcp.json` / `.vscode/mcp.json`）、同ファイル固有のサーバは 1 度も起動していない。本要件はこの「宣言が無視されている状態」の是正を兼ねる。

### 5.5 Issue / PR 作成（CLI 経路）

- **FR-CLI-30**: `--create-issues` 指定時、CLI は以下のシーケンスを実行する: 新ブランチ作成 → Root Issue 作成 → Sub-Issue 作成（active Step ごと） → DAG 実行 → `git add/commit/push` → PR 作成 → **`--auto-coding-agent-review` フラグ指定時のみ** Code Review Agent レビュー → サマリー出力（[hve/orchestrator.py](hve/orchestrator.py) module docstring および `_create_issues_if_needed`）。
- **FR-CLI-31**: `--create-issues` には `--repo` と `GH_TOKEN` が必須。未設定時は警告を出して Issue 作成をスキップする。
- **FR-CLI-32**: `--create-pr` は PR 作成のみ行い、自動マージは実行しない（Issue Template の `enable_auto_merge` とは別運用）。
- **FR-CLI-33**: `--ignore-paths` で指定されたパスは `git add` の pathspec 除外として扱う（既定値は `SDKConfig` 側）。
- **FR-CLI-34**: `--delete-local-merged-branch`（既定 **有効**、`--no-delete-local-merged-branch` で無効化。config: `delete_local_merged_branch`）が有効で、かつ `enable_auto_merge` が有効・全 Step 成功・今回実行で PR が作成済みの場合に限り、CLI は PR の merged 状態をポーリングし（既定 15 秒間隔・最大 600 秒）、リモートの auto-approve-and-merge フロー完了（PR が merged）を検知後、今回作成した作業ブランチを**ローカルのみ**削除する（`git checkout <base_branch>` の後に `git branch -D <working_branch>`）。squash マージではローカルブランチが「マージ済み」と判定されないため `-D` を用いる。タイムアウト・PR が未マージ（closed 等）・`checkout` 失敗のいずれかの場合は削除せず警告ログを 1 行出力する。実行中断（Ctrl+C 等）時はポーリングが中断され削除処理に到達しないため、削除は行われない。リモートブランチは削除せず、github.com の「Automatically delete head branches」設定に委ねる。過去に作成済みの作業ブランチは対象外（今回実行分のみ）。`enable_auto_merge` が無効な場合や PR 未作成時は何もしない（[hve/orchestrator.py](hve/orchestrator.py)、[hve/github_api.py](hve/github_api.py)、[hve/config.py](hve/config.py)）。

#### 5.5.1 HVE ソース保護ガード

- **FR-CLI-74**: アプリ生成 run の開始時、HVE ソース（`hve/`, `mdq/`, `hve-dev/`, `.github/prompts/`, `.github/skills/`, `.github/scripts/`, `.github/io-contracts/`）に未コミット変更が存在する場合、Orchestrator は branch 作成および Agent セッション開始より前に、検出した全パスを一括報告して停止しなければならない。利用者が明示的に指定した target 出力パスは対象外とする。新しい override フラグを追加してはならない（[hve/orchestrator.py](hve/orchestrator.py)）。
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

- **FR-PARAM-10**: CLI 非対話モードで `--target-business` が空の場合 `[1, 2, 3]`、指定時は `[2, 3]` を既定の `selected_steps` とする（[hve/orchestrator.py](hve/orchestrator.py) `_collect_params_non_interactive`）。
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
  - 本検知による終了処理は、既存の終了経路と同じセッション後始末（実行ログ全文の保存等）を伴わなければならない。
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

---

## 7. 非機能要件

| ID | 要件 |
|---|---|
| NFR-PERF-01 | DAG 実行は `asyncio.Semaphore` を使い、Workflow ごとの `max_parallel`（AKM/ADI は 21、その他は 15、ARD は 15）を超えない |
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
- **Git / PR**: `create_issues` / `create_pr`、`base_branch`、`ignore_paths`、`review_base_ref`
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
- [users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md)
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

---

## 12. 未確定事項（TBD）

| TBD No. | 内容 | 確認方法 |
|---|---|---|
| TBD-01 | ~~リポジトリの確定 commit SHA~~ → **解消（v1.0.4）**: §1.4 に `48326f3ea5fa55b65c262a4eb6e0cccea261bd6f` を記録済み | `git rev-parse HEAD` |
| TBD-02 | ~~`SDKConfig` dataclass の完全フィールド一覧~~ → **解消（v1.0.4、v1.1 追随）**: §8.2 に主要フィールドを列挙し、完全リストは [hve/config.py](hve/config.py) `SDKConfig` クラス定義を正とする。旧 `_SAFE_CONFIG_FIELDS` と snapshot 復元は Resume 全廃に伴い削除済み | `hve/config.py` 全文確認 |
| TBD-03 | ~~ADR-0002 / ADR-0003 のファイルパス~~ → **解消（v1.0.4）**: `docs/decisions/` 配下を走査した結果 ADR-0001（[docs/decisions/ADR-0001-agentic-retrieval-prerequisites.md](docs/decisions/ADR-0001-agentic-retrieval-prerequisites.md)）のみ存在し、ADR-0002 / ADR-0003 は未作成。本文中の ADR-0002 / ADR-0003 への参照は**計画上の仮名**として扱う（作成者未定） | `docs/decisions/` 配下を検索 |
| TBD-04 | ~~`users-guide/*.md` 各リンクの実在~~ → **解消（v1.0.4）**: `users-guide/hve-cli-orchestrator-guide.md` / `users-guide/web-ui-guide.md` / `users-guide/km-guide.md` を含む§10 参照リンクはすべて実在を確認済み | ファイル存在確認 |
| TBD-05 | 各 FR への個別受入基準の付与 → **保留（v1.0.4 時点でイスケジュー化推奨）**: 現状の FR-CLI-44〜51 は文章記述で、Given/When/Then 展開はテストとのトレーサビリティ表を設ける導入コストが大きい。個別 FR 改訂時に小さく始める方針としたい | 次版で Given/When/Then 形式に展開 |
| TBD-06 | ~~Cloud Orchestrator の ARD 対応有無の確定~~ → **解消（v1.6）**: **ARD を CLI / GUI 専用と確定**した（FR-WF-ARD-01）。根拠は (1) `auto-orchestrator-dispatcher.yml` の `trigger_map` に ARD は未登録で、専用の Issue Template / state-transition / `auto-ard-reusable.yml` も存在しない、(2) Cloud 対応を追加すると 30+ ファイル規模の新規作成が必要、(3) FR-CLOUD-06 で ASDW-WEB を Cloud dispatch から **削除** しており、Cloud 対象ワークフローを増やす方向とは逆。契約テストで dispatcher に ARD が現れないことを固定した | 完了（追加作業なし） |
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

---

## 13. ワークフロー別仕様（生成ファイル詳細）

本節は、各 Workflow の目的・Step DAG・生成ファイル（`output_paths` / `output_paths_template`）・必須入力（`required_input_paths`）をゲートとして緻密化する目的で定義する。[hve/workflow_registry.py](hve/workflow_registry.py) は実装状態の技術的な情報源として本節と整合させる。差分が生じた場合、ソース側を理由なく優先せず、規範要件への違反か規範要件の仕様変更かを判定し、後者なら要件を先に改訂してから両者を同期する。

### 13.0 共通約束

- **FR-WF-OUT-01**: 各 Step は `output_paths` で宣言した全ファイルを実行完了時点で存在させなければならない。1 件でも欠落した場合、当該 Step は `failed` とする（Self-Improve target scope 解決・Wave 入力チェックの前提）。本ゲートの適用範囲は CLI / GUI Orchestrator 配下モード（`OrchestratorContext` が注入された実行）に限る。単独実行モード（`ctx` 未注入）と fleet mode（`split_fork_enabled=true`）ではサブタスクが別スコープで成果物を生成するため、親 Step の完了条件として本ゲートを適用しない。欠落報告には欠落したパスのみを列挙し、存在する宣言パスを含めてはならない（[hve/runner.py](hve/runner.py) `_check_output_paths_gate`）。
- **FR-WF-OUT-02**: `output_paths_template` は fan-out 子ステップに対して、`{key}` および **fan-out parser 別の ID 別名プレースホルダ**（`app_catalog` / `dataflow_catalog` → `{appId}`、`screen_catalog` → `{screenId}`、`service_catalog` → `{serviceId}`、`agent_catalog` → `{agentId}`、`business_candidate` → `{businessId}`、`use_case_skeleton` → `{useCaseId}`）を fan-out キーで置換した実パスを生成する。別名の対応表は [hve/fanout_expander.py](hve/fanout_expander.py) `_KEY_ALIAS_PLACEHOLDERS_BY_PARSER` を単一情報源とし、「fan-out キーそのものを指す名前」以外を登録してはならない（`{screenNameSlug}` 等の catalog parser から復元できない属性を置換してはならない）。確定ファイルパスへ解決できないエントリの扱いは FR-WF-OUT-06 に従う。fan-out キーが空集合の場合、当該 Step はスキップではなく `failed`（fan-out 失敗）とする。
- **FR-WF-OUT-03**: `required_input_paths` に列挙された全ファイルが存在しない場合の挙動は `HVE_REQUIRE_INPUT_ARTIFACTS` に従う（`true`: 中断 / 既定 `false`: 警告継続、§3.3 FR-DAG-06）。
- **FR-WF-OUT-04**: 表中「生成ファイル」列の `{key}` は fan-out キーを表す。Container Step（`is_container=true`）は生成ファイルを持たず、Sub-Issue 束ね用途に限定する。
- **FR-WF-OUT-05**: [hve/workflow_registry.py](hve/workflow_registry.py) の StepDef 宣言（`output_paths` + `output_paths_template` / `required_input_paths`）と `.github/io-contracts/<Agent>--<workflow>--<stepId>.yaml` の宣言は一致しなければならない。`.github/scripts/validate-io-contract.py`（引数なし）の registry mismatch を 0 件に保ち、[.github/workflows/validate-io-contract.yml](.github/workflows/validate-io-contract.yml) は当該チェックを hard fail として実行する。registry mismatch は `.github/io-contract-exceptions.yaml` では抑止できない（`check_registry_mismatch()` は例外ファイルを参照しない）ため、解消は StepDef 側または io-contract 側の修正で行うこと。
- **FR-WF-OUT-06**: `output_paths_template` の各エントリのうち、次のいずれかに該当するものは **確定ファイルパスへ解決できない**ものとして fan-out 子の `output_paths` に載せてはならない（FR-WF-OUT-01 のゲートを誤 fail させないための fail-closed 規則、[hve/fanout_expander.py](hve/fanout_expander.py) `_resolve_output_path_template`）。載せない場合も、`output_paths_template` の宣言自体は io-contract との契約整合（FR-WF-OUT-05）のために保持する。
  1. キー別名プレースホルダを 1 つも含まない（全 fan-out 子で同一パスになり per-key 成果物ではない）
  2. 置換後もプレースホルダ（`{...}` / `<...>`）が残る
  3. glob（`*` / `?`）を含む
  4. ディレクトリ参照（末尾 `/`）
  5. 同一 `output_paths_template` 内で宣言されたディレクトリ成果物の配下にある（配下のファイル構成は Agent の裁量であり、個別ファイル単位でゲートすると同一成果物でも構成差で誤 fail する）
- **FR-WF-OUT-07**: fan-out 対象でない StepDef の `output_paths_template` は展開されないため、`_check_output_paths_gate` および `collect_workflow_output_paths` の対象にならない。動的パス（`docs-generated/files/{relative-path}.md` 等）や条件付き生成物を io-contract と整合させるための**契約宣言専用の宣言面**として用いてよい。実行時ゲートの対象としたい確定成果物は `output_paths` に宣言すること。
- **FR-WF-OUT-08**: 名称スラッグ（`{screenNameSlug}` / `{serviceNameSlug}` / `{jobNameSlug}`）は **日本語カタログ名の英訳** であり（`docs/catalog/service-catalog.md` の `SVC-01 | 会員・同意管理サービス` に対し実在ファイルは `docs/services/SVC-01-member-consent-service-description.md`）、訳語は Agent が生成するため [hve/catalog_parsers.py](hve/catalog_parsers.py) を拡張しても決定的には復元できない。したがって名称スラッグを `_KEY_ALIAS_PLACEHOLDERS_BY_PARSER` へ登録してはならず、これを含むエントリは FR-WF-OUT-06 規則 2 により恒久的に drop される。
- **FR-WF-OUT-09**: FR-WF-OUT-06 の結果、fan-out する Step の `output_paths_template` が**どの fan-out キーでも 1 件も解決されない**場合、当該 Step の実行時ゲート（FR-WF-OUT-01）は無言で空になる。この状態は誤 fail を起こさない代わりに検証の消失を招くため、対象 Step を明示 allowlist として固定し、allowlist 外の Step がゲート空になった場合は CI で検出しなければならない（[hve/tests/test_output_paths_template_resolvability.py](hve/tests/test_output_paths_template_resolvability.py) `_EMPTY_GATE_ALLOWLIST`）。allowlist の各項目には空になる理由を記載すること。FR-WF-OUT-10 の prefix ゲートで検証を回復した Step は allowlist から除くこと。
- **FR-WF-OUT-10**: FR-WF-OUT-06 で drop されたエントリのうち、**fan-out キーを実際に含む**ものは、キー出現位置の直後までを接頭辞とする **prefix 存在ゲート**へ降格して検証を回復する（[hve/fanout_expander.py](hve/fanout_expander.py) `resolve_output_path_prefix_gates`、[hve/runner.py](hve/runner.py) `_check_output_paths_gate`）。
  - 判定は「接頭辞に前方一致するファイルまたはディレクトリが 1 件以上存在するか」であり、`output_paths` の内容は変更しない（他の消費者への影響を持たない）。
  - **根拠**: 名称スラッグは FR-WF-OUT-08 のとおり決定的に復元できないうえ、単一 run（`ed3931b8`）の生成物が `docs/services/` だけで `{serviceId}-{serviceNameSlug}-description.md` / `{serviceId}-description.md` / `{serviceId}.md` の 3 形式に分岐しており、完全パス一致でも glob 一致でも誤 fail する。一方で全生成物が **ID 接頭辞で始まる**点は一貫しているため、接頭辞一致だけが誤 fail なしに「当該キーの成果物が存在するか」を検証できる。
  - キー別名を 1 つも含まないエントリ（全 fan-out 子で同一の固定パス）と、キーがそもそも代入されないエントリ（ADFDV の `{jobId}` 等、FR-WF-ADFDV-01）は prefix 化の対象外とし、FR-WF-OUT-09 の allowlist に残す。
  - ID 体系は `SVC-NN` / `APP-NNN-SNNN` / `DNN` のように桁数固定であり、接頭辞が別キーの成果物へ誤って一致しないこと。

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
| 8 | ペルソナカタログ | Arch-PersonaCatalog | 7 | `docs/catalog/persona-catalog.md` |
| 9 | ペルソナ別共通画面カタログ | Arch-UI-PersonaScreenList | 8 | `docs/catalog/persona-screen-catalog.md` |

- **FR-WF-AAS-01**: AAS 末尾 2 Step の Step ID は成果物依存と同じ昇順に採番しなければならない。Step 8 を `Arch-PersonaCatalog`（`depends_on=["7"]`、`docs/catalog/persona-catalog.md` を生成）、Step 9 を `Arch-UI-PersonaScreenList`（`depends_on=["8"]`、`docs/catalog/persona-screen-catalog.md` を生成）とする。Step 9 は Step 8 の出力を `required_input_paths` に持つため、依存と逆順の採番（Step 9 → Step 8）へ戻してはならない。
  - 本契約は [hve/workflow_registry.py](hve/workflow_registry.py) を正本とし、[.github/scripts/bash/lib/workflow-registry.sh](.github/scripts/bash/lib/workflow-registry.sh)・[.github/scripts/powershell/lib/workflow-registry.ps1](.github/scripts/powershell/lib/workflow-registry.ps1)・[.github/workflows/auto-app-selection-reusable.yml](.github/workflows/auto-app-selection-reusable.yml)・[.github/ISSUE_TEMPLATE/app-architecture-design.yml](.github/ISSUE_TEMPLATE/app-architecture-design.yml)・`.github/prompts/`・`.github/scripts/templates/aas/`・`.github/io-contracts/` が同一の意味と順序を宣言すること。
  - Cloud のスキップ伝播は Step 8 のスキップが Step 9 を強制スキップする方向のみとする（逆方向は Step 9 の入力欠落を招くため禁止）。
  - Step ID は SDK セッション ID（`run_id × step_id`）の構成要素であり、同じ ID の意味が入れ替わる。透過的な旧 ID 変換は実装せず、再採番をまたぐ実行中 run は完了させるか、新しい run-id / Issue で再起動すること。

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

> 注: 上記パスはテンプレート（`.github/scripts/templates/aad-web/step-*.md` の「## 出力」）の実体に基づく。Step 1 / 2.1 / 2.2 / 2.3 / 2.4 は `hve/workflow_registry.py` の `output_paths_template` へ登録済み（**TBD-11 解消**、§13.0 FR-WF-OUT-02 / 06）。

### 13.3 ASDW-WEB — Web App Dev & Deploy

- **目的**: AAD-WEB を入力に、Azure データ層／コンピュート／追加サービス／UI を TDD（RED → GREEN）でデプロイし、WAF レビューまで完了させる。
- **Step DAG（抜粋）と生成物カテゴリ**:

| Step | タイトル | Fan-out | 生成カテゴリ |
|---|---|---|---|
| 1 / 2 / 3 / 4 | 各種コンテナ | — | （Sub-Issue 束ね、ファイル非生成） |
| 1.1 | Azure データストア選定 | — | `docs/azure/azure-services-data.md` |
| 1.2 | Azure データサービス Deploy | — | `src/infra/azure/create-azure-data-resources-prep.sh`、`src/infra/azure/create-azure-data-resources.sh`、`src/data/azure/data-registration-script.sh`、`docs/azure/service-catalog.md` 更新 |
| 2.1 | Azure コンピュート選定 | — | `docs/azure/azure-services-compute.md` |
| 2.2 | 追加 Azure サービス選定 | — | `docs/azure/azure-services-additional.md` |
| 2.3 | 追加 Azure サービス Deploy | — | `src/infra/azure/create-azure-additional-resources-prep.sh`、`src/infra/azure/create-azure-additional-resources/create.sh`、`docs/catalog/service-catalog-matrix.md` 更新 |
| 2.3T | サービステスト仕様書（TDD RED） | `service_catalog` | `docs/test-specs/{serviceId}-test-spec.md` |
| 2.3TC | サービステストコード生成（TDD RED） | `service_catalog` | `src/test/api/{サービス名}.Tests/**` |
| 2.4 | サービス実装（TDD GREEN） | `service_catalog` | `src/api/{サービスID}-{サービス名}/**` |
| 2.5 | Azure Compute Deploy | — | `src/infra/azure/create-azure-api-resources-prep.sh`、`.github/workflows/*.yml`（CI/CD）、`docs/catalog/service-catalog-matrix.md` 更新、`src/test/{サービスID}-{サービス名}/**`、デプロイ TDD 用 `docs/test-specs/deploy-step2-compute-test-spec.md`、`src/infra/azure/verify-api-resources.sh` |
| 3.0T | UI テスト仕様書（TDD RED） | `screen_catalog` | `docs/test-specs/{screenId}-test-spec.md` |
| 3.0TC | UI テストコード生成（TDD RED） | `screen_catalog` | `src/test/ui/**`（Jest + jsdom） |
| 3.1 | UI 実装（TDD GREEN） | `screen_catalog` | `src/app/**` |
| 3.2 | Web アプリ Deploy（Azure SWA） | — | `src/infra/azure/create-azure-webui-resources-prep.sh`、`src/infra/azure/create-azure-webui-resources.sh`、`.github/workflows/*.yml`（SWA）、`docs/catalog/service-catalog-matrix.md` 更新、デプロイ TDD 用 `docs/test-specs/deploy-step3-swa-test-spec.md`、`src/infra/azure/verify-webui-resources.sh` |
| 3.3 | UI E2E テスト（Playwright） | — | Playwright 実行ログ、失敗時 HTML レポート / trace artifact（永続ファイル非生成） |
| 4.1 | WAF アーキテクチャレビュー | — | `docs/azure/azure-architecture-review-report.md` |
| 4.2 | 整合性チェック | — | `docs/azure/dependency-review-report.md` |

> 注: 上記パスはテンプレート（`.github/scripts/templates/asdw-web/step-*.md` の「## 出力」）の実体に基づく。ASDW-WEB の全非コンテナ Step は `hve/workflow_registry.py` へ登録済み（**TBD-12 解消**）。実行時ゲートの対象は `output_paths` のみで、ディレクトリ参照・glob・未解決スラッグを含む成果物は `output_paths_template` で契約宣言のみ行う（§13.0 FR-WF-OUT-06 / 07）。

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

- **FR-WF-ADFDV-01**: Step 2.1 / 2.2 の fan-out parser は `dataflow_catalog` であり、上流の ADFD（§13.4）が生成する `docs/dataflow/dataflow-app-catalog.md` をキー元とする。
- **FR-WF-ADFDV-02**: `output_paths_template` の `{jobNameSlug}` は、[hve/catalog_parsers.py](hve/catalog_parsers.py) が ID のみを返すため現状解決できず、FR-WF-OUT-06 の fail-closed drop 規則により実行時ゲートから除外される。契約宣言としては保持する。
- **FR-WF-ADFDV-03**: データフロー実装の既定プログラミング言語は **Python**、テストフレームワークは **pytest** とする。選定理由は、実行基盤として Apache Spark / Microsoft Fabric / Databricks を選択できることである。分散処理が不要な規模では標準ライブラリ / pandas、必要な規模では PySpark を選択し、どちらを選んだかと根拠を README へ記録する。対象は `Dev-Dataflow-ServiceCoding` / `Dev-Dataflow-TestCoding` / `Dev-Dataflow-FunctionsDeploy` の各 Prompt と `templates/adfdv/step-2.1.md` / `step-2.2.md`、および Cloud reusable workflow `auto-dataflow-dev-reusable.yml` の inline Issue body とし、.NET 固有の記述（`dotnet` / `xUnit` / `.csproj` / `C#` / `NuGet`）を残してはならない。

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
| 1 | AI Agent 構成設計 | — | — | `docs/azure/azure-services-agent.md` 等 |
| 2.1 | テスト仕様書（TDD RED） | 1 | `agent_catalog` | `docs/test-specs/{key}-test-spec.md` |
| 2.2 | テストコード生成（TDD RED） | 2.1 | `agent_catalog` | `src/test/agent/{key}.Tests/**` |
| 2.3 | 実装（TDD GREEN） | 2.2 | `agent_catalog` | `src/agent/{key}/**` |
| 3 | AI Agent Deploy | 2.3 | `agent_catalog` | `.github/workflows/*.yml`、Foundry Agent リソース実体 |
| 4 | tool search 実測評価 | 3 | `agent_catalog` | `docs/agent/tool-search-eval/{key}-eval-report.md` |

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

### 13.8 AKM — Knowledge Management

- **fan-out キー**: 固定 `D01`〜`D21`（21 並列）。`max_parallel=21`。
- **同時更新防止**: `concurrency: akm-knowledge-write-${{ github.repository }}`（§4.4 FR-CLOUD-21）。

| Step | タイトル | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|
| 1 | knowledge ドキュメント生成・管理 | — | 静的 `D01〜D21` | `knowledge/{Dxx}-*.md` および `knowledge/{Dxx}-*-ChangeLog.md`（各 Dxx ごと） |
| 2 | knowledge 横断整合性レビュー | 1 | — | `knowledge/business-requirement-document-status.md` 更新（および整合性レポート） |

> `knowledge/` 書き込みは「削除 → 新規作成」ルール（`.github/copilot-instructions.md` §0）に従い、本体ファイルへの LOCK 情報埋め込みは禁止。

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

> 上記パスはテンプレート（`.github/scripts/templates/adoc/step-*.md` の「## 出力」）の実体に基づく。ADOC の全非コンテナ Step は `hve/workflow_registry.py` へ登録済み（**TBD-14 解消**）。Step 2.1〜2.5 / 3.1 の動的パスは `output_paths_template` による契約宣言専用であり、実行時のファイル存在ゲートは適用されない（§13.0 FR-WF-OUT-07）。

### 13.12 ARD — Auto Requirement Definition

- **目的**: 企業全体／対象事業の事業分析からユースケースカタログまでを自動生成する Workflow。ADR-0003 で 7 step 構成に再設計。
- **Cloud Orchestrator 対応**: **非対応（確定）**。詳細は FR-WF-ARD-01（§12 TBD-06 解消）。
- **FR-WF-ARD-01**: ARD は **CLI / GUI Orchestrator 専用**とする。[.github/workflows/auto-orchestrator-dispatcher.yml](.github/workflows/auto-orchestrator-dispatcher.yml) の `trigger_map` / `done_map` に ARD を登録してはならず、`auto-ard-reusable.yml` を新設してはならない。Cloud 対応が必要になった場合は、ARD 専用の Issue Template・state-transition・reusable workflow の新規作成（30+ ファイル規模）を伴う独立設計タスクとして起票すること。本制約は FR-CLOUD-06（registry と同期しない Cloud reusable workflow を dispatcher から外す）と同じ方針に立つ。
- **FR-WF-ARD-02**: ARD がユーザー提供資料（`attached_docs` およびパス指定の `target_business`）を受け取る Step では、当該資料を **一次情報として最優先で参照する**ことを Prompt および Body テンプレートに明示しなければならない。根拠: ユーザー提供資料は ARD のどの Step の `required_input_paths` にも宣言されず、`{attached_docs}` / `{target_business}` のパラメータ注入だけが到達経路であるため、優先度の明示が無い Step では固定パスの既定入力に埋没する。対象は Step 1（[.github/prompts/Arch-ARD-BusinessAnalysis-Untargeted.prompt.md](.github/prompts/Arch-ARD-BusinessAnalysis-Untargeted.prompt.md) / [.github/scripts/templates/ard/step-1.md](.github/scripts/templates/ard/step-1.md)）と Step 2（[.github/prompts/Arch-ARD-BusinessAnalysis-Targeted.prompt.md](.github/prompts/Arch-ARD-BusinessAnalysis-Targeted.prompt.md) / [.github/scripts/templates/ard/step-2.md](.github/scripts/templates/ard/step-2.md)）とし、Step 2 は既に本規定を満たす。
- **Step DAG と生成ファイル**:

| Step | タイトル | 依存 | Fan-out | 生成ファイル |
|---|---|---|---|---|
| 1 | 事業分野候補列挙 | — | — | `docs/company-business-recommendation.md` |
| 1.1 | 事業分野別深掘り分析 | 1 | `business_candidate` | `docs/business/{key}-analysis.md` |
| 1.2 | 事業分析統合 | 1.1 | — | `docs/company-business-requirement.md` |
| 2 | 対象業務深掘り分析 | （`target_business` 指定時ルート／未指定時 1.2 経由 skip_fallback） | — | `docs/business-requirement.md` |
| 4.1 | ユースケース骨格抽出 | 2（skip_fallback `1.2`） | — | `docs/catalog/use-case-skeleton.md` |
| 4.2 | ユースケース詳細生成 | 4.1 | `use_case_skeleton` | `docs/usecase/{key}-detail.md` |
| 4.3 | ユースケースカタログ統合 | 4.2 | — | `docs/catalog/use-case-catalog.md` |

- **必須入力**:
  - Step 4.1: `docs/business-requirement.md`、`docs/company-business-requirement.md`
- **旧後方互換（廃止）**: 旧 step_id（`1` / `2` / `3`）からの resume 互換は、Resume 機能全廃に伴い NFR-COMP-01 とともに廃止済み。

### 13.13 ゲート条件（受入基準）

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
| TBD-11 | ~~AAD-WEB Step 1 / 2.1 / 2.2 / 2.3 の `output_paths` / `output_paths_template` を `hve/workflow_registry.py` に正式登録~~ → **解消（E-09）**: FR-WF-OUT-02 / 06 により `output_paths_template` が多重プレースホルダを受け入れ、確定ファイルパスへ解決できないエントリを fail-closed で落とすようになった。Step 2.1 = `docs/screen/{screenId}-{screenNameSlug}-description.md`、Step 2.2 = `docs/services/{serviceId}-{serviceNameSlug}-description.md`、Step 2.3 = `docs/test-specs/{serviceId}-test-spec.md`、Step 2.4 = `docs/test-specs/{screenId}-test-spec.md` を登録済み。`{screenNameSlug}` / `{serviceNameSlug}` は catalog parser から復元できないため展開時に落ちる（契約宣言としては保持） | `.github/scripts/validate-io-contract.py` の registry mismatch 0 件 |
| TBD-12 | ~~ASDW-WEB 全 Step の `output_paths` / `output_paths_template` を `hve/workflow_registry.py` に正式登録~~ → **解消（E-09）**: Phase 3 E-01 で未登録だった 2.3 / 2.4 / 3.2 / 3.3 / 3.5 / 4.1 / 4.2 / 4.4 を含め、ASDW-WEB の全非コンテナ Step が `output_paths` または `output_paths_template` を宣言する。`hve/tests/test_workflow_registry.py` の `ALLOWED_EMPTY_OUTPUT_PATHS_STEPS` から asdw-web エントリを全削除済み | 同上 |
| TBD-13 | ~~廃止した旧独立原本質問票処理 Step 1 / 2 の `output_paths` / `output_paths_template` を `hve/workflow_registry.py` に正式登録~~ → **解消（v1.0.4）**: Step 1 は `output_paths_template=["qa/{key}-original-docs-questionnaire.md"]`、Step 2 は `output_paths=["qa/original-docs-cross-questionnaire.md"]` を登録済み。現行要件では ADI Step 1.1 / 1.2 の main 成果物として扱う | 同上 |
| TBD-14 | ~~ADOC 全 Step の `output_paths` / `output_paths_template` を `hve/workflow_registry.py` に正式登録~~ → **解消（E-09）**: Step 2.1〜2.5 は `docs-generated/files/{relative-path}.md`、Step 3.1 は `docs-generated/components/{module-name}.md` を `output_paths_template` へ登録した。いずれも fan-out 非対象 Step のため FR-WF-OUT-07 のとおり契約宣言専用であり、`{relative-path}` / `{module-name}` の実行時解決は行わない（ファイル単位の存在ゲートは適用外） | 同上 |

---

以上。
