# HVE Orchestrator 要求定義 ↔ テストコード マッピング

本文書は [hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) の現行機能要件（FR / NFR / G-*）について、対応するテストコードを洗い出したものである。`deprecated-or-removed` の要件は履歴として識別し、現行カバレッジには算入しない。

## 凡例

- **判定**:
  - `✓` 直接対応するテストあり（テスト関数で FR の振る舞いを検証）
  - `△` 間接対応のみ（隣接ロジックや YAML 静的検証など）
  - `✗` 該当テストなし（要追加）
  - `要追加` 契約の既存部分には対応テストがあるが、新規・改訂部分の RED テストが未作成。該当テストが全く無い `✗` とは区別する
- **対応テスト**: `テストファイル :: テスト関数 or テストクラス` 形式。クラス記載時は当該クラス配下の全テストを含意。
- **根拠**: 検証ポイントの短いコメント。捏造を避けるため、テスト名に明示されている動作のみを記述。

## サマリー（カバレッジ概観）

> **注記**: 以下の件数は本マッピング作成時点での **概算** であり、本文の判定マークを機械的に集計したものではない。正確な集計が必要な場合は本文の各表をスクリプトで再集計すること。判定基準も部分的に主観を含む（特に「✓ vs △」の境界）。

| カテゴリ | 直接 ✓（概算） | 間接 △（概算） | なし ✗（概算） |
|---|---:|---:|---:|
| 共通機能（§3） | 多 | 少 | 23 前後（うち FR-CQ / NFR-CQ 系 12 件は bootstrap 中の要追加、FR-MDQ-04 〜 FR-MDQ-10 は本変更で追加、FR-RTO-01〜06 は bootstrap 中の要追加） |
| Cloud Orchestrator（§4） | 数件 | 多 | 数件 |
| CLI 基本（§5.1〜5.5） | 多 | 少 | 少 |
| Resume 2 層保護（§5.6、廃止） | 現行評価対象外 | 現行評価対象外 | 現行評価対象外 |
| パラメータ（§5.7〜6） | 多 | 0 | 1〜2 |
| 非機能（§7） | 多 | 数件 | 数件 |
| IF（§8） | 多 | 0 | 1 |
| ワークフロー別（§13） Step 粒度 | AKM/ADI/ARD/ADOC/AAS 中心 | AAD-WEB/ASDW-WEB/ABDV/AAGD 中心 | ABDV 一部 |
| ゲート条件（§13.13） | 1 | 多 | 0 |

**カバレッジ強度（カテゴリ別、定性評価）**:
- 強: CLI 基本、AKM/ADI、ARD の既存ワークフロー挙動、共通 DAG/Fanout
- 中: パラメータ、非機能、AAS/ADOC（テンプレ整合性レベル）、ARD v2.43 改訂契約（B1〜B3のRED待ち）
- 弱: Cloud Orchestrator dispatcher 周辺、ABDV/AAGD、ゲート完了判定（G-OUT/G-LBL/G-DIFF）

---

## §A 共通機能（§3）

### FR-COMMON-01 — CLI/Cloud の Workflow 解決 SSOT
- 概要: CLI は `WorkflowDef` を SSOT に解決。Cloud は `trigger_map` を持つ二重管理。
- 判定: ✓（RED: ARD Cloud surface 追加前は新規契約が失敗 → GREEN: `test_ard_cloud_surface.py` を含む FR-APPREQ-03/04/05 グループ **27 passed**、既存 SSOT 側 `test_workflow_registry.py` **216 passed / 1 skipped**）
- 直接対応テスト:
  - [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestListWorkflows` / `TestGetWorkflow` — workflow_registry が SSOT として全 Workflow ID を返す
  - [hve/tests/test_ard_cloud_surface.py](hve/tests/test_ard_cloud_surface.py) — §3.2 の Cloud 対応集合と dispatcher trigger / done / closed / reusable job の一致、およびCLI/GUI専用 `adi` の非混入を固定
- 間接対応テスト:
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestWorkflowYamlAgenticInputs` — dispatcher YAML の入力配線を静的検証

### FR-COMMON-02 — 後方互換エイリアス（ラベル/タイトル/CLI ID）
- 判定: △
- 間接対応テスト:
  - [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestListWorkflows`、`TestGetWorkflow`
- 根拠: `aad-web` / `asdw-web` が registry に登録されていることは検証されているが、`aad`→`aad-web` などのエイリアス解決ロジック単体のテストは未確認。

### FR-DAG-01 — 4 依存パターン（AND/並列/skip_fallback/block_unless）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_dag_planner.py](hve/tests/test_dag_planner.py) :: `TestDAGPlanner`
  - [hve/tests/test_dag_executor.py](hve/tests/test_dag_executor.py) :: `TestDAGExecutorAAS`、`TestDAGExecutorABD`、`TestDAGExecutorComputeWaves`
  - [hve/tests/test_dag_validation.py](hve/tests/test_dag_validation.py) :: `TestDAGValidation`

### FR-DAG-02 — 計画段階と実行段階の分離 + Semaphore
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_dag_planner.py](hve/tests/test_dag_planner.py) :: `TestDAGPlanner`
  - [hve/tests/test_dag_executor.py](hve/tests/test_dag_executor.py) :: `TestDAGExecutorPlanPrompts`、`TestDAGExecutorMaxParallel`

### FR-DAG-03 — 並列上限の解決順序
- 判定: 実装済み
- 直接対応テスト:
  - [hve/tests/test_dag_executor.py](hve/tests/test_dag_executor.py) :: `TestDAGExecutorMaxParallel`
  - [hve/tests/test_fanout.py](hve/tests/test_fanout.py) :: `test_akm_max_parallel_is_21`
  - [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestADIQuestionnaireWorkflow.test_adi_questionnaire_steps` — ADI の `max_parallel=21` と Step 1.1 / 1.2 の構成を固定
  - [hve/tests/test_fanout.py](hve/tests/test_fanout.py) :: `test_adi_questionnaire_fanout_produces_21_children` — ADI Step 1.1 の D01〜D21 静的 fan-out を固定
  - （v2.32 追加）[hve/tests/test_workflow_max_parallel_resolution.py](hve/tests/test_workflow_max_parallel_resolution.py) :: `TestResolveMaxParallel` / `TestRunWorkflowWiring` / `TestPlanCarriesResolution` / `TestExecutorDoesNotReResolve`
- 受入ケース:
  - （v2.32 追加）`asdw-web` は `--max-parallel` の値によらず 1 で計画される。→ ✓ (`TestResolveMaxParallel.test_declared_value_wins_over_config` / `TestPlanCarriesResolution`)
  - （v2.32 追加）`akm` / `adi` は `--max-parallel` の値によらず 21 で計画される。→ ✓ (同上)
  - （v2.32 追加）宣言を持たない Workflow は `SDKConfig.max_parallel` で計画される。→ ✓ (`TestResolveMaxParallel.test_config_is_used_when_not_declared`)
  - （v2.32 追加）ARD bridge mode は宣言値 15 より優先され 1 となり、根拠は `ard-serial` となる。→ ✓ (`TestResolveMaxParallel.test_ard_serial_wins_over_declaration`)
  - （v2.32 追加）解決は `hve/orchestrator.py` の 1 実装だけで行い、`dag_executor` 側で再解決しない。→ ✓ (`TestRunWorkflowWiring` / `TestExecutorDoesNotReResolve`)
- 実装後の判断:
  - （v2.32）`--max-parallel` は宣言を持つ 4 Workflow（ard / akm / adi / asdw-web）へは効かなくなる。`asdw-web` の `1` は同一 worktree の並列書込みを避ける安全制約で利用者が緩めてよい値ではなく、`akm` / `adi` の `21` は fan-out が設計上その並列度で動くことを表すため、宣言優先を採った。宣言を持たない 9 Workflow では `--max-parallel` は従来どおり有効。
  - （v2.32）argparse の `--max-parallel` を `default=None` にして「明示指定のときだけ宣言値を上書き」とする案は採らなかった。CLI 対話ウィザードは常に整数を `SDKConfig` へ設定するため明示・既定を区別できず、`SDKConfig.max_parallel` を `Optional[int]` へ変えると GUI 設定ストア・オプションパリティ・既存テストへ波及する。FR-DAG-03 と NFR-PERF-01 のいずれも宣言値の上書きを認めていない。

### FR-DAG-04 — 静的/動的 fan-out 展開
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_fanout.py](hve/tests/test_fanout.py) :: `test_akm_has_fanout_21_keys`、`test_all_known_fanout_parsers_registered`、`test_all_workflows_fanout_parsers_are_known`、`test_akm_fanout_expander_produces_21_children`、`test_fanout_child_carries_fanout_meta`、`test_fanout_empty_parser_marks_skip`、`test_output_paths_template_resolves_with_key`、`test_output_paths_inherited_when_template_absent`、`test_dag_executor_expands_akm_to_21_parallel`、`test_dag_executor_runs_all_children`
  - [hve/tests/test_workflow_registry_ard.py](hve/tests/test_workflow_registry_ard.py) :: `TestBusinessCandidateParser`、`TestUseCaseSkeletonParser`、`TestNewParsersRegistered`
  - [hve/tests/test_orchestrator_fanout_repo_root.py](hve/tests/test_orchestrator_fanout_repo_root.py) :: `TestFanoutRepoRootIsWorkingRepo` — 展開の基準ルートが作業ディレクトリであること。`monkeypatch.chdir` で作業ディレクトリとパッケージ設置ディレクトリを分離し、dry-run の fan-out 子が作業ディレクトリ側の skeleton だけから展開されることを固定。併せて事前展開・deferred 再展開・Fleet wave prompt の 3 経路へ `__file__` 由来のルートを渡していないことを AST で固定（RED: 4 failed → GREEN: 4 passed）

### FR-DAG-05 — `consumed_artifacts` / `output_paths` / `required_input_paths` 保持
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_consumed_artifacts.py](hve/tests/test_consumed_artifacts.py) :: `TestConsumedArtifactsKeysAreKnown`、`TestConsumedArtifactsSemantics`、`TestPhase4ConsumedArtifactsMinimized`、`TestAllWorkflowsConsumedArtifactsExplicit`、`TestPhase4ConsumedArtifactsValues`
  - [hve/tests/test_collect_workflow_output_paths.py](hve/tests/test_collect_workflow_output_paths.py) :: `TestCollectWorkflowOutputPaths`

### FR-DAG-06 — ルート前提成果物チェック + `HVE_REQUIRE_INPUT_ARTIFACTS`
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_input_artifact_check.py](hve/tests/test_input_artifact_check.py) :: `TestCheckStepInputArtifactsSemantics`、`TestCheckStepInputArtifactsPresent`、`TestCheckStepInputArtifactsMissing`、`TestCheckWorkflowInputArtifactsStrict`、`TestCheckStepInputArtifactsUnknownKey`、`TestArtifactKeyMappingConsistency`、`TestSDKConfigRequireInputArtifacts`

### FR-DAG-07 — `StepDef.required_params` / `default_params` 宣言と既定値適用
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_workflow_step_params.py](hve/tests/test_workflow_step_params.py) :: `TestStepParamDeclaration` — ASDW-WEB Step 1.3 の `required_params` 6 件と `default_params` 5 件を検証し、`data_verify_aci_image` が入力項目でないことと `data_resource_suffix` の既定値が APP-ID 由来であることを固定
  - [hve/tests/test_workflow_step_params.py](hve/tests/test_workflow_step_params.py) :: `TestApplyStepDefaultParams` — 欠落・空白のみ補完、既存値非上書き、fan-out 子 ID 正規化、非 active step の既定値非適用
  - [hve/tests/test_workflow_step_params.py](hve/tests/test_workflow_step_params.py) :: `TestDefaultParamsValidity` — `default_params` キーが `required_params` の部分集合であることを `WorkflowDef._validate` が強制

### FR-DAG-08 — active step 必須パラメータの実行開始時 pre-flight
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_workflow_param_precheck.py](hve/tests/test_workflow_param_precheck.py) :: `TestCheckRequiredWorkflowParams` — 不足キーの全件一括報告、未設定/空白/型不正の判定、fan-out 子 ID 正規化、宣言なし Workflow の素通り
  - [hve/tests/test_workflow_param_precheck.py](hve/tests/test_workflow_param_precheck.py) :: `TestRunWorkflowParamPrecheckWiring` — `run_workflow` が DAG 実行前に abort し、`blocked` に該当 step ID を載せること。`continue_on_error` でも降格しないこと

### FR-STATE-01 — 状態ラベル `{prefix}:initialized/ready/running/done/blocked`
- 判定: △
- 間接対応テスト:
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestIssueQaReadyTransitionWorkflow`、`TestQaReadyLabelTokenFallback`
  - [hve/tests/test_workflow_restore_auto_qa_label.py](hve/tests/test_workflow_restore_auto_qa_label.py) :: `TestRestoreAutoQaLabelWorkflow`

### FR-STATE-02 — `qa-ready` スキップと遷移ワークフロー
- 判定: △
- 直接対応テスト:
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestIssueQaReadyTransitionWorkflow`
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestQaReadyLabelTokenFallback`
- 除去契約: [hve/tests/test_label_consistency_audit.py](hve/tests/test_label_consistency_audit.py) / [hve/tests/test_issue_template_qa_parity.py](hve/tests/test_issue_template_qa_parity.py) — 現存Cloudラベル・Issue Form・reusable workflowの集合を検証し、旧専用経路を対象集合へ含めない

### FR-STATE-03 — `{prefix}:done` 付与時の次推奨 Workflow 提示
- 判定: ✗（要追加（RED予定））
- 対応テスト（RED予定）:
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: 終端 Workflow 集合から廃止した旧独立原本質問票経路が除去され、ADI が終端として扱われることを固定するテスト
- 注記: `test_input_artifact_check.py` の `next_workflow` フィールド検証は「**不足成果物を次に生成すべき Workflow**」のメタ情報であり、`suggest-next` Issue コメントとは別概念。混同しないこと。

### FR-MODEL-01 — 既定モデル `claude-opus-4.7`、MODEL_CHOICES 4 値
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_config.py](hve/tests/test_config.py) :: `TestSDKConfigDefaults.test_model_choices_contains_both_46_and_47`、`test_model_choices_contains_gpt_5_5`、`test_model_choices_gpt_5_5_before_claude`
  - [hve/tests/test_config.py](hve/tests/test_config.py) :: `TestSDKConfigModelResolution`、`TestSDKConfigModelOverride`
  - [hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) :: `TestModelDropdown.test_model_choices_parity_with_templates`

### FR-MODEL-02 — Auto 時は `model="auto"` を SDK へ送り Auto Model Selection に委譲（reasoning_effort は付与しない）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_runner.py](hve/tests/test_runner.py) :: `TestSubSessionOptsReasoningEffort.test_auto_model_sends_wire_auto_no_reasoning`、`test_explicit_model_omits_reasoning_effort`、`test_empty_string_omits_model_and_reasoning`
  - [hve/tests/test_config.py](hve/tests/test_config.py) :: `TestToWireModel`（"Auto" → "auto" wire 変換、空文字/None → None 等の契約）
  - [hve/tests/test_orchestrator_effort.py](hve/tests/test_orchestrator_effort.py) :: `TestApplyReasoningEffortMain.test_no_user_value_auto_model_leaves_unset` 等（ユーザー指定 reasoning_effort のみ伝播）
  - [hve/tests/test_runner.py](hve/tests/test_runner.py) :: `TestCreateSessionAutoReasoningFallback.test_strips_reasoning_effort_on_typeerror`

### FR-MODEL-03 — `_normalize_model_with_warning` で Auto 返却
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_config.py](hve/tests/test_config.py) :: `TestNormalizeModelWithWarning`

### FR-MODEL-04 — SDK `tool_search` を CLI / GUI から設定可能にし、全セッション経路へ同一値を伝搬
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_config.py](hve/tests/test_config.py) :: `TestSDKConfigToolSearch` — 既定 `True`、env 未指定時 `True`、`HVE_TOOL_SEARCH` の truthy / falsy 読み取り
  - [hve/tests/test_runner.py](hve/tests/test_runner.py) :: `TestAvailableExcludedToolsPropagation.test_main_session_includes_tool_search_when_enabled` — メインセッションへの伝搬
  - [hve/tests/test_runner.py](hve/tests/test_runner.py) :: `TestAvailableExcludedToolsPropagation.test_sub_session_opts_includes_tool_search` — サブセッションへの伝搬
  - [hve/tests/test_self_improve.py](hve/tests/test_self_improve.py) :: `TestRunImprovementLoopRedContracts.test_mutation_session_includes_tool_search_when_enabled` — Self-Improve セッションへの伝搬
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestBuildParams.test_tool_search_cli_enabled` / `test_tool_search_cli_disabled` — `--tool-search` / `--no-tool-search` のパースと `SDKConfig` 反映
  - [hve/gui/tests/test_orchestrate_args.py](hve/gui/tests/test_orchestrate_args.py) :: `TestToolSearchToArgv` — GUI → CLI argv へのフラグ出力
- 根拠: 削減効果そのものは本要件の受入対象外（FR-MODEL-04 本文）。受入は設定の伝搬に限定するため、テストも伝搬の検証に限定する。Fleet mode 親セッションは FR-MODEL-04 の対象外のためテストを設けない。GUI の設定保存・画面登録（`settings_store.py` / `settings_window.py` / `settings_apply.py`）は既存 `auto_compaction` と同型の登録のみで判定ロジックを持たないため、argv 変換テストでカバーする。

### FR-MODEL-06 — 既定有効化が明示的な無効化を上書きしない
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_config.py](hve/tests/test_config.py) :: `HVE_TOOL_SEARCH` falsy で `False` — `TestSDKConfigToolSearch`
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `--no-tool-search` で `False` — `TestBuildParams.test_tool_search_cli_disabled`
  - [hve/tests/test_runner.py](hve/tests/test_runner.py) / [hve/tests/test_self_improve.py](hve/tests/test_self_improve.py) :: `tool_search=False` の 3 経路で引数を渡さない
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: 新規プロファイル既定 `True` / 保存済み `false` の保持
  - [hve/tests/test_toolsearch_wiring.py](hve/tests/test_toolsearch_wiring.py) :: `tool_search_ranking` 既定が `sdk` のまま — `TestConfigField.test_default_is_sdk`
- 根拠: 保存済み `false` が利用者の明示指定か旧既定かを実行時に区別できないため、移行処理を持たず新規プロファイルの初期値だけを変更する。


### FR-MODEL-05 — SDK 未サポート時は `tool_search` を除外して再試行
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_runner.py](hve/tests/test_runner.py) :: `TestCreateSessionAutoReasoningFallback.test_strips_tool_search_on_typeerror` — `TypeError` 時に `tool_search` を剥がして 2 回目で成功すること
- 根拠: 既存の `test_strips_reasoning_effort_on_typeerror`（FR-MODEL-02）と同じ縮退規則を対象とする。orchestrator 側の同名関数は Fleet mode 専用で `tool_search` を受け取らないため対象外。

### FR-TS-01 — SDK 組み込み `tool_search_tool` を HVE 実装へ差し替える
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolsearch_contract.py](hve/tests/test_toolsearch_contract.py) :: `TestSdkContract`（差し替え対象名が SDK 定数と一致 / `overrides_built_in_tool` `defer` `tool_references` `available_tools` の実在）
  - [hve/tests/test_toolsearch_metatool.py](hve/tests/test_toolsearch_metatool.py) :: `TestToolFactory`（`overrides_built_in_tool=True` / handler が `tool_references` を返す）
  - [hve/tests/test_toolsearch_metatool.py](hve/tests/test_toolsearch_metatool.py) :: `TestSearchCatalog`（`available_tools` のみを入力とし、`None` でも例外にしない）
  - [hve/tests/test_toolsearch_wiring.py](hve/tests/test_toolsearch_wiring.py) :: `TestConfigField` / `TestCliFlag` / `TestCliOverrideReachesConfig`（`--tool-search-ranking` が FR-MODEL-04 の bool と直交すること）
  - [hve/tests/test_toolsearch_wiring.py](hve/tests/test_toolsearch_wiring.py) :: `TestGuiArgs` / `TestGuiWidget`（GUI → CLI argv の往復、Foundry 側設定との取り違え防止）
  - [hve/tests/test_toolsearch_wiring.py](hve/tests/test_toolsearch_wiring.py) :: `TestEnablement` / `TestBuildSessionToolset`（`tool_search` が OFF なら差し替えない、Core Skill は `defer="never"`）
  - [hve/tests/test_toolsearch_wiring.py](hve/tests/test_toolsearch_wiring.py) :: `TestRunnerWiring` / `TestCloudIsGatedUntilMeasured`（runner がヘルパー経由で注入し、Cloud 経路では差し替えない）
- 根拠: HVE 側から MCP へ RPC を発行しないことは、ハンドラの入力が `invocation.available_tools` だけであることをテストで固定して担保する。配線は `tool_search_ranking="hve"`（既定 `"sdk"`）のときだけ有効。G4（Cloud でのカスタム tools 可否）が未実測のため Cloud 経路はゲートしている。

### FR-TS-02 — `ToolEntry` 正規化と `additional_search_text` の非公開
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolsearch_contract.py](hve/tests/test_toolsearch_contract.py) :: `TestFlattenSchemaTerms`（ネスト 3 階層打ち切り・重複排除）
  - [hve/tests/test_toolsearch_contract.py](hve/tests/test_toolsearch_contract.py) :: `TestToolEntry`（mcp / native の判別、不正 pin と空 name の拒否）
  - [hve/tests/test_toolsearch_contract.py](hve/tests/test_toolsearch_contract.py) :: `TestToolCard`（`additional_search_text` を返さない）
  - [hve/tests/test_toolsearch_contract.py](hve/tests/test_toolsearch_contract.py) :: `TestBuildCatalog`（`None` スナップショット、pin と検索語彙の適用、id 重複排除）
- 根拠: RED 証跡 = `hve.toolsearch` の import を遮断した状態で 15 件が collection error。GREEN 証跡 = 実装後 15 件 pass。

### FR-TS-03 — pin ポリシーの優先順位と fail-closed Step での pin-only
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolsearch_policy.py](hve/tests/test_toolsearch_policy.py) :: `TestPolicyValidation`（ツール名のみのキーをロード時に拒否 / pin 値・重み・上限・tau・step mode の検証）
  - [hve/tests/test_toolsearch_policy.py](hve/tests/test_toolsearch_policy.py) :: `TestApplyPolicy`（pin / 検索の振り分け、`excluded_tools` の索引除外、manifest pin の優先、サーバーワイルドカードの非漏洩）
  - [hve/tests/test_toolsearch_policy.py](hve/tests/test_toolsearch_policy.py) :: `TestShippedPolicy`（同梱 policy.json の Core / Long-tail 振り分けと fail-closed Step）
  - [hve/tests/test_toolsearch_policy.py](hve/tests/test_toolsearch_policy.py) :: `TestEnforcementBoundary`（ランカーが安全境界ではないこと）
  - [hve/tests/test_toolsearch_skillcatalog.py](hve/tests/test_toolsearch_skillcatalog.py) :: `TestSkillManifestPins`（`workflow_defaults` / `required_skills` を pin へ、`optional_skills` は pin しない）
  - [hve/tests/test_toolsearch_metatool.py](hve/tests/test_toolsearch_metatool.py) :: `TestDecideCatalog.test_fail_closed_step_returns_no_searchable_entries`
  - [hve/tests/test_toolsearch_wiring.py](hve/tests/test_toolsearch_wiring.py) :: `TestBuildSessionToolset.test_repo_local_policy_override_is_used_at_runtime` / `test_packaged_policy_is_used_when_the_repo_has_no_override` — `policy.json` の解決先が実行時と表示・保存（FR-GUI-07）で一致すること
- 根拠: 強制力は `excluded_tools` / MCP `tools` allowlist が担うことを `TestEnforcementBoundary` で明示的に固定する。
- 実装後の判断（敵対的レビュー反映）:
  - 実行時は `ToolSearchPolicy.load()` を `repo_root` 無しで呼んでおり、GUI の表示・保存先だけが `.toolsearch/policy.json` へ切り替わる乖離があった（RED: `limit` が 2 ではなく 5 のまま）。`load(repo_root=repo_root)` へ揃えて解消した。
  - リポジトリローカルの上書きが実行時ポリシーになるが、安全境界は変わらない。pin の増減は「何を返すか」だけを変え、呼び出しの禁止は `excluded_tools` と MCP `tools` allowlist が引き続き担う。

### FR-TS-04 — 日本語対応のフィールド重み付き BM25 と適応的打ち切り
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolsearch_ranking.py](hve/tests/test_toolsearch_ranking.py) :: `TestJapaneseRanking`（日本語クエリで正解ツールが 1 位）
  - [hve/tests/test_toolsearch_ranking.py](hve/tests/test_toolsearch_ranking.py) :: `TestSplitIdentifier` / `TestTokenize`（snake_case / camelCase / `mcp__azure__` 分割、CJK バイグラム）
  - [hve/tests/test_toolsearch_ranking.py](hve/tests/test_toolsearch_ranking.py) :: `TestAdaptiveCutoff`（tau 未満で空返却、limit 遵守、空カタログ）
  - [hve/tests/test_toolsearch_ranking.py](hve/tests/test_toolsearch_ranking.py) :: `TestEngineFallback`（既定エンジンと rank_bm25 の idf 退化の実測）
  - [hve/tests/test_toolsearch_ranking.py](hve/tests/test_toolsearch_ranking.py) :: `TestAdditionalSearchTextEffect`（検索専用語彙がスコアと順位を改善し、モデルへは返らない）
  - [hve/tests/test_toolsearch_ranking.py](hve/tests/test_toolsearch_ranking.py) :: `TestDeterminism`（同点時の順序が決定論）
- 根拠: `rank_bm25.BM25Okapi` は idf が `log(N-n+0.5) - log(n+0.5)` のため、語が全文書の半数に現れると idf が 0 になる（実測）。小規模カタログで退化するため、常に正の idf を返す `mdq.search._MiniBM25` を既定とした。

### FR-TS-05 — golden クエリによる Recall@k 評価とトークン削減率の測定
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolsearch_eval.py](hve/tests/test_toolsearch_eval.py) :: `TestRetrievalQuality`（Recall@10 >= 0.85 を受入基準とし、評価が決定論であること）
  - [hve/tests/test_toolsearch_eval.py](hve/tests/test_toolsearch_eval.py) :: `TestTokenReduction`（baseline > optimized、削減率 >= 60%）
  - [hve/tests/test_toolsearch_eval.py](hve/tests/test_toolsearch_eval.py) :: `TestMetrics` / `TestTokenEstimation` / `TestGoldenSet`
- 実測値（2026-08-04、対象カタログ = `.github/skills` の Skill + native 4 ツール = 39 件、golden 42 クエリ）:
  Recall@5 = 0.940 / **Recall@10 = 0.964** / MRR = 0.907 / miss = 0 /
  トークン 5,072 → 1,084（**削減 78.6%**、pin 7 件 + 検索返却 5 件相当）
- 根拠: MCP ツールは接続しないと列挙できないため golden の対象外。実運用では FR-MODEL-04 が引用する実測（登録 171 ツール / 54,865 tokens）の規模が加わるため、削減率は本測定値を下限として扱う。

### FR-TS-06 — Skill も検索対象に含める（long-tail Skill の発見可能性）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolsearch_skillcatalog.py](hve/tests/test_toolsearch_skillcatalog.py) :: `TestDiscoverSkills`（実リポジトリの Skill を列挙し、全件に description があること）
  - [hve/tests/test_toolsearch_skillcatalog.py](hve/tests/test_toolsearch_skillcatalog.py) :: `TestBuildSkillEntries` / `TestBuildSkillTools`（Core は `defer="never"`、それ以外は `defer="auto"`）
  - [hve/tests/test_toolsearch_skillcatalog.py](hve/tests/test_toolsearch_skillcatalog.py) :: `TestDisabledSkillsIsNotTheOnlyLever`（long-tail Skill が検索対象に残ること）
  - [hve/tests/test_toolsearch_policy.py](hve/tests/test_toolsearch_policy.py) :: `TestSkillKindRouting`（`skill_` 接頭辞が skill 種別へ分類される）
  - [hve/tests/test_toolsearch_metatool.py](hve/tests/test_toolsearch_metatool.py) :: `TestDecideCatalog.test_merges_live_catalog_with_skill_entries`
- 根拠: Skill は SDK の `available_tools` に現れない（SDK 実測）。`define_tool` でツール登録してカタログへ合流させることで、一括無効化に頼らず発見可能にする。

### FR-TS-07 — 利用履歴に基づく自動 pin（workflow × step 単位の決定論）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolsearch_autopin.py](hve/tests/test_toolsearch_autopin.py) :: `TestWarmup`（ウォームアップ未満では昇格しない）
  - [hve/tests/test_toolsearch_autopin.py](hve/tests/test_toolsearch_autopin.py) :: `TestPromotionRanking`（上位 N 件、同点時の順序が決定論、反復呼び出しで安定）
  - [hve/tests/test_toolsearch_autopin.py](hve/tests/test_toolsearch_autopin.py) :: `TestExpiry`（古い session が window から外れる）
  - [hve/tests/test_toolsearch_autopin.py](hve/tests/test_toolsearch_autopin.py) :: `TestAutoPinPrecedence`（`never` / manifest pin を上書きしない）
  - [hve/tests/test_toolsearch_autopin.py](hve/tests/test_toolsearch_autopin.py) :: `TestRecordAndLoad`（記録は best-effort、壊れた行を捨てる、`ts` を付与しつつ `ts` 無しの旧レコードも読む、既定保存先が `<repo-root>/.toolsearch/usage.jsonl`）
  - [hve/tests/test_toolsearch_wiring.py](hve/tests/test_toolsearch_wiring.py) :: `TestResolveCalledToolIds`（呼ばれたツール名を id へ解決し、未知名は推測せず落とす）
  - [hve/tests/test_toolsearch_wiring.py](hve/tests/test_toolsearch_wiring.py) :: `TestRunnerUsageRecording`（Step 終了時の記録経路と、session_id が Step 単位で決定論にならないこと）
- 根拠: Foundry の auto-pin は per-user だが、HVE は prompt cache の prefix 安定性を優先して workflow × step 単位の決定論とする。session_id に run_id を混ぜないと session 数が増えず、ウォームアップに到達しない。`ts` は FR-TS-10 の期間絞り込みのために後から追加した任意フィールドで、自動 pin の判定には使わない（旧履歴を失効させないため）。保存先は `~/.hve/toolsearch/` からリポジトリ配下の `.toolsearch/` へ移した（`.mdq/` / `.cq/` と同じ流儀に揃え、リポジトリをまたぐ混在を防ぐため。RED 2 件 → GREEN 13 passed）。

### FR-TS-08 — 遅延公開が発火していないことの検知
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolsearch_metatool.py](hve/tests/test_toolsearch_metatool.py) :: `TestDecideCatalog.test_warns_when_nothing_is_deferred`
  - [hve/tests/test_toolsearch_metatool.py](hve/tests/test_toolsearch_metatool.py) :: `TestDecideCatalog.test_does_not_warn_when_deferral_is_active`
  - [hve/tests/test_toolsearch_metatool.py](hve/tests/test_toolsearch_metatool.py) :: `TestDecideCatalog.test_warns_when_the_snapshot_is_unavailable`
- 根拠: `defer_threshold` の既定値はサーバー側にあり、クライアントから静的に確認できない（`copilot/client.py:267-268` は wire へ転送するのみ）。閾値未満だと差し替えたランカーが一度も呼ばれず、失敗として現れない。

### FR-TS-09 — 実行時統計の収集
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolsearch_stats.py](hve/tests/test_toolsearch_stats.py) :: `TestStatsCollector`（`on_event` 互換シンク、JSONL 追記、書き込み失敗を握り潰す）
  - [hve/tests/test_toolsearch_stats.py](hve/tests/test_toolsearch_stats.py) :: `TestEventSchema`（必須フィールド、カタログ内訳、レイテンシ、トークン推定、`additional_search_text` 非記録）
  - [hve/tests/test_toolsearch_stats.py](hve/tests/test_toolsearch_stats.py) :: `TestEventsPath` / `TestLoadEvents`（既定保存先が `<repo-root>/.toolsearch/events.jsonl`、`HVE_TOOLSEARCH_EVENTS` での差し替え、壊れた行を捨てる）
  - [hve/tests/test_toolsearch_stats.py](hve/tests/test_toolsearch_stats.py) :: `TestAggregate` / `TestLiveBuffer`（イベントのみからの算出、不活性判定は FR-TS-08 警告限定、メモリ上限）
  - [hve/tests/test_toolsearch_wiring.py](hve/tests/test_toolsearch_wiring.py) :: `TestRunnerStatsWiring`（runner が `on_event` へ `StatsCollector` を配線する）
- 根拠: 差し替えたランカーは失敗として現れない（呼ばれないだけ）ため、実行時の起動状況を記録しないと不活性を検知できない。収集は best-effort とし、Step を落とさない。保存先は FR-TS-07 と同じく `.toolsearch/` へ移し、GUI は保持している `repo_root` を渡して cwd 依存の誤表示を防ぐ。

### FR-TS-10 — ダッシュボード
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolsearch_dashboard.py](hve/tests/test_toolsearch_dashboard.py) :: `TestRenderText` / `TestRenderJson` / `TestRenderHtml`
  - [hve/tests/test_toolsearch_dashboard.py](hve/tests/test_toolsearch_dashboard.py) :: `TestNoFabrication`（データ不足を 0 や推定値で埋めない）
  - [hve/tests/test_toolsearch_dashboard.py](hve/tests/test_toolsearch_dashboard.py) :: `TestHtmlIsSelfContained`（`http(s)://` / `<script` / CDN を含まない、図はインライン SVG）
  - [hve/tests/test_toolsearch_dashboard.py](hve/tests/test_toolsearch_dashboard.py) :: `TestBuildDashboard` / `TestCli`（両ストアの読み込み、不在容認、`--json` / `--html` / `--follow` と `--once` の排他）
  - [hve/tests/test_toolsearch_dashboard.py](hve/tests/test_toolsearch_dashboard.py) :: `TestDocumentation`（users-guide に全指標キーと収集パスの説明がある）
  - [hve/tests/test_toolsearch_stats.py](hve/tests/test_toolsearch_stats.py) :: `TestAggregate.test_since_also_filters_the_usage_side_of_adoption` / `test_undated_usage_is_excluded_when_a_window_is_given`（`--since` は検索イベントと利用履歴の両側にかかる。時刻を持たない旧レコードは窓の内側だと証明できないので数えない）
- 根拠: 端末は全角を 2 桁で描くため、描画は `unicodedata.east_asian_width` 基準で揃える（コードポイント数だと日本語ラベルの桁が崩れることを目視で確認）。HTML は閉じたネットワークでも開けることを優先し、外部参照を持たない。`adoption_rate` の期間絞り込みのため FR-TS-07 の利用履歴へ任意フィールド `ts` を追加した（旧レコードは `ts` 無しのまま読み、自動 pin の判定は従来どおり）。
- 直接対応テスト（計画・要追加）:
  - [hve/tests/test_toolsearch_dashboard.py](hve/tests/test_toolsearch_dashboard.py) :: `TestTokenReductionValidity` — `deferral_inactive_rate` が 1.0 のとき、テキスト / HTML で `token_reduction` を削減率として表示せず無効理由を出すこと、JSON は値を残しつつ無効フラグを併記すること、クエリ 0 件（`deferral_inactive_rate` が None）を無効判定にしないことを固定

### FR-TS-11 — コンテキスト内訳の実測 CLI
- 判定: ✓
- 直接対応テスト（計画）:
  - [hve/tests/test_toolsearch_context_report.py](hve/tests/test_toolsearch_context_report.py) :: `test_renders_layers_from_the_runtime_snapshot` — システムプロンプト / 組み込み / MCP サーバー別の実トークン量とツール数を描画する
  - [hve/tests/test_toolsearch_context_report.py](hve/tests/test_toolsearch_context_report.py) :: `test_groups_tool_definitions_by_server` / `test_counts_builtin_tools_separately` — ツール定義を `mcp_server_name` で層へ束ね、組み込みを別枠で数える
  - [hve/tests/test_toolsearch_context_report.py](hve/tests/test_toolsearch_context_report.py) :: `test_includes_the_model_name_used_for_tokenization` — `contextInfo.modelName` を必ず含める
  - [hve/tests/test_toolsearch_context_report.py](hve/tests/test_toolsearch_context_report.py) :: `test_reports_declared_but_unconnected_servers` / `test_unconnected_server_is_not_reported_as_zero_tokens` — 宣言済みだが接続しなかった MCP サーバーを 0 と混同せず未接続として示す
  - [hve/tests/test_toolsearch_context_report.py](hve/tests/test_toolsearch_context_report.py) :: `test_tool_definitions_missing_from_metadata_are_not_dropped` — `getCurrentMetadata` に現れないツール（実測: `web_search`）を層別集計から欠落させない
  - [hve/tests/test_toolsearch_context_report.py](hve/tests/test_toolsearch_context_report.py) :: `test_json_exposes_the_runtime_totals` — 合計値はランタイムの `contextInfo` を正とし、attribution 集計で上書きしない
  - [hve/tests/test_toolsearch_context_report.py](hve/tests/test_toolsearch_context_report.py) :: `test_does_not_use_estimated_tokens` — `hve/toolsearch/eval.py` の推定を使わない
  - [hve/tests/test_toolsearch_context_report.py](hve/tests/test_toolsearch_context_report.py) :: `test_collect_never_sends_a_prompt` — 収集経路が `session.send` を呼ばない
  - [hve/tests/test_toolsearch_context_cli.py](hve/tests/test_toolsearch_context_cli.py) :: `test_context_subcommand_is_registered` / `test_context_accepts_the_json_flag` / `test_json_flag_outputs_machine_readable_payload` — `hve toolsearch context` の登録と `--json`
  - [hve/tests/test_toolsearch_context_cli.py](hve/tests/test_toolsearch_context_cli.py) :: `test_text_output_renders_the_report` — 既定はテキスト描画で、CLI 側で再集計しない
  - [hve/tests/test_toolsearch_context_cli.py](hve/tests/test_toolsearch_context_cli.py) :: `test_measurement_failure_exits_non_zero_with_a_reason` — 測定失敗時に非 0 終了と理由を返し、推定値で埋めない
  - [hve/tests/test_toolsearch_context_report.py](hve/tests/test_toolsearch_context_report.py) :: `TestSessionOptions` — 測定セッションを Step 実行と同じ設定モデル / `context_tier` で生成する
  - [hve/tests/test_toolsearch_context_report.py](hve/tests/test_toolsearch_context_report.py) :: `test_collect_builds_its_session_from_session_options` — `collect()` が当該 options を使う配線を固定する
  - [hve/tests/test_toolsearch_context_report.py](hve/tests/test_toolsearch_context_report.py) :: `test_reports_the_model_that_was_requested_for_the_session` / `test_requested_model_is_explicit_when_not_configured` — セッションへ渡した設定モデルを併記する
- 実測に基づく注記（v2.40）:
  - `contextInfo.modelName` はセッションモデルを反映せず、3 条件の実測すべてで `claude-sonnet-4.5` を返した。一方 `contextAttribution` 由来の層別内訳はセッションモデルに依存して変化した（`MODEL=claude-opus-4.7` で azure 15,047 → 18,047 tokens、`contextInfo.mcpToolsTokens` は 17,302 で不変）。両者は異なるトークナイザで計測されているため、差分を欠損として提示しない。
  - `system_prompt_tokens` は 3 条件すべてで `null`。repository instructions が `systemTokens` に含まれるかは未確定。

### NFR-SEC-01 — 秘密情報を Issue body / 標準出力に含めない
- 判定: △
- 間接対応テスト:
  - [hve/tests/test_runner.py](hve/tests/test_runner.py) :: `TestStepRunnerStreamEvents.test_tool_call_id_correlation_does_not_add_shell_or_query_secrets_to_failure_error_msg`
  - [hve/tests/test_runner.py](hve/tests/test_runner.py) :: `TestSubSessionsCreatedCounter.test_log_sub_session_reason_does_not_leak_secrets` / `test_log_sub_session_reason_does_not_include_actual_token_value`
- 根拠: 現行の代表的な標準出力経路は検証されるが、Issue body を含む全出力経路の横断検証ではないため間接対応とする。旧 `state.json` / `config_snapshot` テストは Resume 全廃に伴い削除済み。

### NFR-SEC-02 — `docs-original/` 読み取り専用
- 判定: △
- 直接対応テスト:
  - [hve/tests/test_doc_ingest.py](hve/tests/test_doc_ingest.py) :: `TestSafety.test_source_dir_is_not_modified` — ADI 前処理が `docs-original/` を変更しないこと（FR-WF-ADI-02 と同一根拠）
  - [hve/tests/test_docs_original_readonly_workflow.py](hve/tests/test_docs_original_readonly_workflow.py) :: `test_docs_original_changes_remain_fail_closed` / `test_only_same_path_legacy_rename_is_exempted` — CI が通常の変更を拒否し、`original-docs/` から `docs-original/` への同一相対パスの rename だけを移行例外として許可すること
- 根拠: ADI 経路の非改変は検証されるが、全 Agent が書き込みを行わないことの横断契約テストは未確認。CI ジョブ `check-docs-original`（`.github/workflows/protect-readonly-paths.yml`）が実運用上のガードとなる。

### FR-WF-ADI-01〜18 / NFR-SEC-ADI-01・02 — ADI（Auto Design-doc Ingestion）
- 判定: ○
- 直接対応テスト:
  - FR-WF-ADI-01（決定性）: [hve/tests/test_doc_ingest.py](hve/tests/test_doc_ingest.py) :: `TestDeterminism.test_index_json_is_deterministic` / `test_doc_ids_are_ordered_by_source_path`
  - FR-WF-ADI-02（原本不変）: 同 :: `TestSafety.test_source_dir_is_not_modified`
  - FR-WF-ADI-03（変換と除外）: 同 :: `TestConversion.test_markdown_passthrough` / `test_unsupported_extension_is_excluded_with_reason` / `test_txt_records_stdlib_converter` / `test_csv_records_stdlib_converter` / `test_excluded_doc_leaves_no_directory`
  - FR-WF-ADI-04（変換来歴）: 同 :: `TestConversion.test_provenance_is_written`
  - FR-WF-ADI-05（fail-closed）: 同 :: `TestSafety.test_max_docs_exceeded_fails_closed` / `test_max_docs_failure_leaves_no_index`
  - FR-WF-ADI-06（差分スキップ）: 同 :: `TestIncrementalRewrite.test_unchanged_doc_is_not_rewritten` / `test_changed_doc_is_rewritten`
  - FR-WF-ADI-07（重複検出）: 同 :: `TestSha256.test_duplicate_content_is_marked` / `test_sha256_recorded_per_doc` / `test_sha256_changes_when_content_changes`
  - FR-WF-ADI-08（目録の第 1 列規約）: [hve/tests/test_catalog_parsers_design_doc.py](hve/tests/test_catalog_parsers_design_doc.py) :: `test_extracts_ids_from_table` / `test_falls_back_to_headings` / `test_duplicates_are_removed_in_order` / `test_registered_in_parse_catalog`
  - NFR-SEC-ADI-02（パストラバーサル防止）: [hve/tests/test_doc_ingest.py](hve/tests/test_doc_ingest.py) :: `TestSafety.test_symlink_outside_base_dir_is_skipped`（symlink 非対応環境では skip）、`TestInternalHelpers.test_is_inside_*`（境界判定の単体検証）
  - FR-WF-ADI-09（Doc Card の必須キー）: [hve/tests/test_adi_validation.py](hve/tests/test_adi_validation.py) :: `test_valid_card_has_no_errors` / `test_missing_front_matter_is_reported` / `test_missing_required_key_is_reported` / `test_invalid_confidence_is_reported` / `test_missing_context_section_is_reported` / `test_missing_file_is_reported`
  - FR-WF-ADI-10（`out` の理由必須）: 同 :: `test_valid_catalog_has_no_errors` / `test_out_row_without_reason_is_reported` / `test_missing_out_section_is_reported` / `test_catalog_missing_file_is_reported`
  - FR-WF-ADI-11（`purpose` 空時の `must` 禁止）: 同 :: `test_must_without_purpose_is_reported` / `test_empty_purpose_without_must_is_allowed` / `test_must_section_is_not_confused_with_should`
  - FR-WF-ADI-12（AKM の後方互換フォールバック）: [hve/tests/test_adi_downstream_contract.py](hve/tests/test_adi_downstream_contract.py) :: AKM の fan-out 共通指示が routing 表を優先し、無い場合は原本へフォールバックする契約を検証。ADI の per-document 共通指示は FR-WF-ADI-17 の正規化済み入力契約として分離する
  - FR-WF-ADI-13（下流成果物への候補反映）: [hve/tests/test_adi.py](hve/tests/test_adi.py) :: `test_adi_seed_steps_share_one_agent` / `test_adi_seed_steps_run_in_parallel_after_step4` / `test_adi_seed_step_output_paths` / `test_adi_seed_steps_read_routing_and_cards` / `test_adi_seed_steps_have_body_templates` / `test_adi_seed_targets_do_not_overlap`
  - FR-WF-ADI-14（出典 `doc_id` 必須）: [hve/tests/test_adi_validation.py](hve/tests/test_adi_validation.py) :: `test_valid_seed_section_has_no_errors` / `test_row_without_doc_id_is_reported` / `test_invalid_doc_id_format_is_reported` / `test_seed_section_with_no_rows_is_allowed` / `test_file_without_seed_section_is_allowed`
  - FR-WF-ADI-15（ID 採番禁止）: 同 :: `test_numbered_id_in_candidate_column_is_reported`
  - FR-WF-ADI-16（自動起動しない）: [hve/tests/test_adi.py](hve/tests/test_adi.py) :: `test_adi_is_not_registered_as_meta_dependency`
  - FR-WF-ADI-17（Step 1.1 の入出力・21 fan-out・0件質問）: [hve/tests/test_adi.py](hve/tests/test_adi.py) :: `test_adi_questionnaire_steps_contract` / [hve/tests/test_fanout.py](hve/tests/test_fanout.py) :: `test_adi_questionnaire_fanout_produces_21_children` / [hve/tests/test_adi_validation.py](hve/tests/test_adi_validation.py) :: `test_explicit_zero_questionnaire_is_valid` / `test_silent_zero_questionnaire_is_invalid` / `test_questionnaire_run_detects_step_outputs` / [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestNormalizeAdiTargetScope`
  - FR-WF-ADI-18（Step 1.2 join・Step 2順序・main成果物検証）: [hve/tests/test_adi.py](hve/tests/test_adi.py) :: `test_adi_questionnaire_steps_contract` / `test_adi_step_dependencies_are_serial` / [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestADIQuestionnaireWorkflow.test_adi_questionnaire_steps` / [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestAdiQuestionnairePostDag`
- ワークフロー定義の契約: [hve/tests/test_adi.py](hve/tests/test_adi.py) :: `test_adi_workflow_registered` / `test_adi_params_are_minimal` / `test_adi_max_parallel_matches_existing_convention` / `test_adi_has_expected_steps` / `test_adi_questionnaire_steps_contract` / `test_adi_step1_contract` / `test_adi_fanout_uses_inventory_parser` / `test_adi_step_dependencies_are_serial` / `test_adi_self_improve_scope` / `test_adi_owns_integrated_questionnaire_self_improve_context` / `test_adi_registered_in_skill_manifest` / `test_adi_display_name_registered` / `test_adi_cli_purpose_defaults_to_empty` / `test_adi_cli_questionnaire_params_default` / `test_adi_cli_purpose_is_passed_through` / `test_adi_non_interactive_defaults`
- 補足: NFR-SEC-ADI-01（`convert_local()` 限定）は [hve/gui/doc_convert.py](hve/gui/doc_convert.py) の実装制約であり、[hve/tests/test_gui_doc_convert.py](hve/tests/test_gui_doc_convert.py) が既存の変換経路を検証する。ADI 側からの追加検証は未実施のため判定は間接。

### FR-WF-ADFDV-03 — データフロー実装の既定言語（Python / pytest）
- 判定: ○
- 直接対応テスト: [hve/tests/test_adfdv_deploy_contract.py](hve/tests/test_adfdv_deploy_contract.py) :: `test_dataflow_default_language_is_python` / `test_dataflow_test_coding_uses_pytest` / `test_dataflow_language_rationale_names_target_platforms` / `test_no_dotnet_tokens_remain_in_dataflow_contracts`
- 検証範囲: Prompt 3 件（`Dev-Dataflow-ServiceCoding` / `Dev-Dataflow-TestCoding` / `Dev-Dataflow-FunctionsDeploy`）、body テンプレート 2 件（`templates/adfdv/step-2.1.md` / `step-2.2.md`）、Cloud reusable workflow 1 件（`auto-dataflow-dev-reusable.yml`）。`.NET` 固有トークン（`dotnet` / `xUnit` / `.csproj` / `C#` / `NuGet`）の残存 0 件を機械検証する。
- 補足: 実行プラットフォーム（Spark / Microsoft Fabric / Databricks）の記載は Prompt 本文で検証する。デプロイ先は Azure Functions（Python ランタイム）のまま変更していない。

### NFR-SEC-03 — `git add` の pathspec 除外（shell インジェクション対策）
- 判定: △
- 間接対応テスト:
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `test_ignore_paths_default_in_config`、`test_ignore_paths_cli_override`、`test_ignore_paths_auto_remove_qa_when_workiq_draft_and_create_pr`
- 根拠: `_git_add_commit_push` の pathspec リスト渡しを直接検証するテストは未確認。
- 訂正（2026-07-28）: 旧記述は [hve/tests/test_security.py](hve/tests/test_security.py) を本要件の間接根拠としていたが、同テストが検証する `hve/security.py::sanitize_user_input` はプロンプトへ埋め込む自由記述入力のサニタイズであり、`git add` の pathspec 除外とは無関係のため削除した。

### （未対応要件）`hve/security.py` プロンプトインジェクション対策
- 判定: ✗（**実装は存在するが本体から呼ばれていない**）
- 実装: [hve/security.py](hve/security.py) :: `sanitize_user_input` / `is_sanitization_enabled`
- テスト: [hve/tests/test_security.py](hve/tests/test_security.py) :: `TestSanitizeUserInput`、`TestSanitizeControlChars`、`TestSanitizeDelimiterTokens`、`TestSanitizeMaxLength`、`TestSanitizationFeatureFlag`
- 根拠: `sanitize_user_input` の呼び出しはリポジトリ全体でテストのみ（本体参照 0 件、2026-07-28 実測）。モジュール docstring は「Issue Template の free-text 入力を LLM プロンプトへ埋め込む前にサニタイズする」とするが、その呼び出し経路が実装されていない。
- 残タスク: 対応する active 要件を `requirement-definition.md` へ追加して配線するか、実装とテストを削除するかを決定する。

### HVE アプリケーション保守の要求トレーサビリティ（§3.7）

> **導入中**: T03 の Customization 契約は GREEN（12 passed）で、Skill / instructions / router を現行カバレッジに反映済みである。T04 は GREEN（76 passed、Windowsでsymlink作成不可の2件skip）で、PR側 `pull_request` validatorに加え、既定ブランチ文脈でbase側validatorだけを実行するtrusted workflowを実装済みである。初回導入PRではtrusted workflowがまだ既定ブランチに存在しないため、人間承認後にマージし、更新済みbranch protectionテンプレートをリモートへ再適用してtrusted checkを必須化する。

#### FR-MAINT-01 — 編集前の索引・要求・マッピング確認と active ID 制約
- 判定: ✓（T03 / T04 GREEN）
- 対応テスト:
  - [hve/tests/test_hve_requirement_traceability_contract.py](hve/tests/test_hve_requirement_traceability_contract.py) — GREEN（12 passed）。Coding Agent 向け Skill / instructions が索引 → 要求定義 → テストマッピングの順で確認させる静的契約。改訂 2.36 の 3 層優先順位・変更種別判定の Skill 保持は RED: 5 failed / 7 passed → GREEN: 12 passed
- 対応テスト:
  - [.github/scripts/tests/test_validate_hve_requirement_traceability.py](.github/scripts/tests/test_validate_hve_requirement_traceability.py) — GREEN（76 passed、2 skipped）。要求定義を source とする `active-or-described` のみを許可する validator 契約
- 受入ケース:
  - HVE 対象変更では編集前の 3 段確認を要求する。
  - 未知・競合・`deprecated-or-removed`・`partial-or-not-supported` の ID を拒否する。
  - 新規 ID の bootstrap は同一変更内の要求定義・マッピング・RED テストを根拠にし、索引再生成前の他変更から適用しない。
  - bootstrap では要求定義・マッピング・RED テストの追加後、実装前に索引を再生成し、新規 ID の `source=hve-dev/requirement-definition.md`、`status=active-or-described`、マッピング上の test path を照合する。
  - 既存 ID で索引と要求定義が矛盾する場合は、推測せず不整合を解消するまで実装へ進まない。
  - `hve-requirement-traceability` Skill が §1.3 の 3 層優先順位（規範要件 / 説明的基線 / 履歴情報）と §3.7 の変更種別判定規則（`feature` / `bugfix` / `maintenance`）を保持し、要求定義書本文を追加取得せずに適用可否と変更種別を判定できる。

#### FR-MAINT-02 — 関連チャンクの選択取得と段階的 fallback
- 判定: ✓（T03 GREEN）
- 対応テスト:
  - [hve/tests/test_hve_requirement_traceability_contract.py](hve/tests/test_hve_requirement_traceability_contract.py) — GREEN（12 passed）。検索キー、初回上限、段階的拡張、再試行、限定 read fallback の静的契約。改訂 2.36 の ID 直引き優先は RED: 5 failed / 7 passed → GREEN: 12 passed
- 受入ケース:
  - Issue 本文、対象パス、対象 symbol、失敗テスト、Workflow / Step ID を検索キーとして使用する。
  - 要件 ID が既知の場合は検索を行わず、`hve-dev/hve-feature-inventory.csv` の当該行の `line` 列が指す定義行だけを読む。ID が未知の場合に限り検索へ進む。
  - 初回取得を最大 5 チャンクかつ 800 tokens に制限する。
  - 不足時のみ親見出し → 隣接チャンク → 関連章の順に一段ずつ拡張する。
  - 0 件・矛盾時は検索語を変えて最大 2 回再試行し、それでも解消しなければ理由を記録して確認を求める。
  - 索引欠損・stale・検索 CLI 障害時は、特定済みの要件 ID または見出しの限定範囲だけを read / grep で取得し、要求書全文へ自動 fallback しない。
  - HVE 要件検索では本規則を汎用 Markdown 検索 fallback より優先し、汎用 fallback が先に全文を取得する経路を認めない。
  - 全文取得はユーザーの明示要求、要求定義書自体の横断改訂、または章単位で解消できない複数章の矛盾に限定する。

#### FR-MAINT-03 — feature の要求 → mapping → RED → 索引 → 実装 → GREEN 順序
- 判定: △（T03 / T04 GREEN。initial bootstrap PRのマージとtrusted check有効化が残作業）
- 対応テスト:
  - [hve/tests/test_hve_requirement_traceability_contract.py](hve/tests/test_hve_requirement_traceability_contract.py) — GREEN（12 passed）。Skill / instructions が feature の必須順序と N/A 禁止を保持する静的契約
- 対応テスト:
  - [.github/scripts/tests/test_validate_hve_requirement_traceability.py](.github/scripts/tests/test_validate_hve_requirement_traceability.py) — GREEN（76 passed、2 skipped）。feature の必須差分、要件 ID、テストパス、RED / GREEN 証跡と導入ゲートを検証する validator / workflow 契約
- 受入ケース:
  - feature では要求定義 → テストマッピング → 同じ対象の失敗するテストと RED 確認 → 索引再生成と照合 → 実装 → 同じ対象テストの GREEN 確認 → マッピングへの実結果反映、の順に進める。
  - feature の要件 ID、実在テストパス、RED / GREEN 証跡を省略できない。
  - bugfix / maintenance の N/A は具体的理由と人間レビュー必須の記録がある場合だけ許可する。
  - `hve-dev/hve-tdd-change-policy.md` またはその生成元が §3.7 と矛盾する場合は §3.7 を正とし、同一変更で同期する。
  - 初回導入では要求テストマッピング、RED 契約テスト、TDD policy の生成元、機能・テスト索引、PR validator / workflow を同一変更セットで同期し、全契約テストが GREEN になるまで完了を宣言しない。
  - bootstrap 中の新規 ID が索引にないことを理由に、既存要件へ偽装しない。

#### FR-MAINT-04 — PR トレーサビリティの決定論的検証
- 判定: △（リポジトリ内T04はGREEN。initial bootstrap PRのマージ後にtrusted checkを必須化する残作業）
- 対応テスト:
  - [.github/scripts/tests/test_validate_hve_requirement_traceability.py](.github/scripts/tests/test_validate_hve_requirement_traceability.py) — GREEN（76 passed、2 skipped）。対象パス、8 キー schema、ID / test path / mapping、変更種別ごとの組合せ、workflow / branch protection を検証する契約
  - [hve/tests/test_hve_surface_inventory.py](hve/tests/test_hve_surface_inventory.py) — GREEN。共有スコープ判定モジュールの対象 / 対象外サンプルと、対象外パスが surface 索引に混入しないことを検証する契約
- 受入ケース:
  - §3.7 の対象境界表を parameterized contract として固定し、対象判定を単一 validator に集約する。パスは `/` 区切りのリポジトリ相対形式へ正規化し、絶対パス、空・`.`・`..` セグメント、リポジトリ外を拒否する。
  - 対象外パターンを優先し、未一致パスは対象外とする。`CHANGELOG.md` と `users-guide/**` は単独変更なら非適用、他の HVE 対象変更と同時ならゲート対象とする。rename は旧・新パスを評価し、変更パス取得・正規化・matcher 失敗時は fail-closed とする。
  - HVE 対象外変更だけならゲートを適用せず、対象変更では `<!-- hve-traceability:start -->` / `<!-- hve-traceability:end -->` と、例示順・大小文字を区別した `Change-Type`、`Change-Type-Reason`、`Requirement-IDs`、`Requirement-N/A-Reason`、`Test-Paths`、`Test-N/A-Reason`、`TDD-Evidence`、`Manual-Review-Required` の 8 キーを厳密に 1 組要求する。複数値は `, ` 区切りとし、値内改行を認めない。
  - `Change-Type` は `feature` / `bugfix` / `maintenance` の 3 値だけを許可する。複数解釈があり分類を確定できない場合は `feature` とし、分類理由の意味的妥当性は人間レビューで確認する。
  - `Requirement-IDs` が実値なら `Requirement-N/A-Reason: N/A`、`Test-Paths` が実値なら `Test-N/A-Reason: N/A` を全変更種別で要求する。ID または path を省略する `N/A` は `bugfix` / `maintenance` だけに許可し、対応する具体的理由と `Manual-Review-Required: yes` を要求する。
  - 欠落・重複・未知キー・未置換値・不正な N/A 組合せを拒否する。`maintenance` は N/A の使用有無にかかわらず `Manual-Review-Required: yes` を要求する。
  - 要求 ID の source / status / 要求定義、テストパスの安全性 / 許可ルート / 実在、要求 ID とマッピング上の test path 対応を検証する。
  - `feature` では要求定義・マッピング・索引の更新と、同じ対象テストの実装前 RED / 実装後 GREEN 証跡を追加で要求する。`bugfix` は再現テストの修正前失敗 / 修正後成功、`maintenance` は実行した回帰検証または具体的理由付き `N/A` を `TDD-Evidence` に要求する。
  - PR workflow は validator を必須ゲートとして実行し、branch protection の既存承認レビューを省略・迂回しない。trusted workflowは既定ブランチ文脈でbase側validatorだけを実行し、PR内容はデータとして検証して実行しない。初回導入PRのマージ後、GitHub管理者は更新済みbranch protectionテンプレートをリモートへ再適用してtrusted checkをrequiredにする。N/A と変更種別の意味的妥当性は CI が推測せず、人間レビューへ委ねる。
  - validator のentrypoint、root / PR本文ファイル / 変更パス一覧ファイルの入力、`pull_request`限定・PR本文のshell非直接展開・最小読取権限、workflow / validator job由来のrequired check contextを契約テストで確認する。

#### NFR-CTX-01 — always-on ルーターの最小化と取得上限
- 判定: ✓（T03 GREEN）
- 対応テスト:
  - [hve/tests/test_hve_requirement_traceability_contract.py](hve/tests/test_hve_requirement_traceability_contract.py) — GREEN（12 passed）。repository-wide instructions が 3 箇条の検索ルーターに留まり、要求本文を埋め込まず、初回取得上限を委譲先へ保持する静的契約。改訂 2.36 の不具合調査への適用拡張は RED: 5 failed / 7 passed → GREEN: 12 passed
- 受入ケース:
  - repository-wide instructions の HVE トレーサビリティ記述は、HVE 対象変更または HVE 対象パスの不具合調査で `hve-requirement-traceability` Skill を使用する、HVE コアパスでは path-specific instructions も適用する、要求定義書全文を既定の入力にしない、の 3 箇条だけで構成する。
  - path-specific instructions の本文も変更と不具合調査の双方を適用契機として宣言する。
  - CI はルーターの見出し・3 箇条・Skill 参照・要求書パス・既知の要件 ID / schema key / 取得オプションの重複を検査する。Coding Agent が読む raw source を契約対象とし、HTML comment、code span、fenced / indented code 内の既知識別子もルーター外重複として拒否する。言い換えによる意味的な分散・矛盾は人間レビューへ委ねる。
  - path-specific instructions の自動適用は `hve/**`, `mdq/**`, `cq/**`, `hve-dev/**`, `tools/skills/markdown_query/**`, `tools/skills/code_query/**` に限定し、それ以外の HVE 対象は repository-wide ルーターから同じ Skill へ委譲する。
  - 要求定義書本文を repository-wide instructions へ複製しない。
  - 初回最大 5 チャンク / 800 tokens と、FR-MAINT-02 の段階的拡張を維持する。

#### FR-MAINT-05 — HVE 実装シンボル索引の生成と純度
- 判定: ✓（GREEN。87 passed）
- 対応テスト:
  - [hve/tests/test_hve_surface_inventory.py](hve/tests/test_hve_surface_inventory.py) — GREEN。87 passed。共有スコープ判定の単一宣言、境界表代表パス 42 件、面判定、決定性、対象外パス非混入、テスト非混入、CSV の stale 検知
- 受入ケース:
  - 索引 `hve-dev/hve-surface-inventory.csv` を生成スクリプトから機械生成し、同一入力に対して 2 回実行した出力が一致する。
  - 索引対象は §3.7 対象境界の判定に一致するパスだけとし、対象判定は既存の単一 validator の実装を再利用する。索引生成側に対象境界判定を二重実装しない。
  - 索引の `file` 列に §3.7 で対象外とされたパス（`src/**`, `docs/**`, `work/**` 等）を 1 行も含まない。
  - 対象外パス配下にファイルを追加・削除しても索引の行数が変化しない。
  - 索引の列に、実行面（`cloud` / `cli` / `gui` / `core`）、シンボル種別、定義ファイルと行、振る舞い要約、規範リテラル集合を含む。
  - 生成スクリプトの出力と committed な索引が不一致の場合に CI が失敗する。
  - 不一致時は stale として扱い、再生成するまで FR-MAINT-06 / FR-MAINT-07 の判断根拠に使わない。
  - 参照数列は静的解析値であり、CI から `pytest <path>` / `python -m <module>` で起動される経路を含まないことを明示する。当該列単独で未使用判定を行わない。
  - テストファイルは本索引に含めない。テストの棚卸しは `hve-dev/hve-test-inventory.csv` が正本であり、二重索引を作らない。

#### FR-MAINT-06 — 規範リテラル判定実装の単一性
- 判定: △（検証マーカーは GREEN。`plan.md` 分割判定メタデータの統合は未実施）
- 対応テスト:
  - [hve/tests/test_norm_literal_single_implementation.py](hve/tests/test_norm_literal_single_implementation.py) — GREEN、17 passed。検証マーカー 3 形式の単一判定、`artifact_validation` の委譲、cloud 2 workflow の委譲と独自正規表現不在、entrypoint の終了コード
- 受入ケース:
  - 明示リストで固定した規範リテラルごとに、判定実装が索引上で 1 件だけであることを検査する。
  - 許可された単一実装以外の判定実装を検出した場合に失敗する。
  - リストに無い規範リテラルを推測して判定対象に加えない。
  - 規範リテラルを生成する側の文言複製、および意図的な vendoring を検査対象から除外する。
  - 検査は索引（FR-MAINT-05）を入力とし、ソースの再走査を行わない。

#### FR-MAINT-07 — 新規ロジック追加前の面横断再利用確認
- 判定: ✓（GREEN、12 passed）
- 対応テスト:
  - [hve/tests/test_hve_requirement_traceability_contract.py](hve/tests/test_hve_requirement_traceability_contract.py) — GREEN、12 passed。Skill の「面横断の再利用確認」セクション全行と Non-goals を固定
  - [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestLaunchSurfacesShareParameterDefaults` — GREEN、3 件。CLI 入口と Orchestrator が Workflow パラメータ既定値 7 件を registry から alias import し、リテラルで再宣言しないこと（TBD-27 解消）。`getattr` による flat import fallback は registry から値を引くため許容し、リテラル束縛だけを拒否する
- 受入ケース:
  - `hve-requirement-traceability` Skill が、新規の判定・生成・検証ロジック追加時に索引を確認する手順を保持する。
  - 探索順が規範リテラル一致 → 振る舞い要約 → シンボル名であることを固定する。
  - シンボル名の不一致だけを根拠に既存実装が無いと判断しない旨を保持する。
  - 複数の実行面に同一ルールの実装がある場合に新規実装を禁止する旨を保持する。
  - 本手順を HVE 対象変更に限定し、生成物側へ適用しない旨を保持する。

#### FR-MAINT-08 — 版更新を要求するパスの単一判定
- 判定: ✓（RED：実装前 53 failed。GREEN：実装後 146 passed（新規 53 件を含む））
- 対応テスト:
  - [hve/tests/test_hve_surface_inventory.py](hve/tests/test_hve_surface_inventory.py) :: `TestVersionBumpScope` — GREEN、53 件。公開 API、対象境界内の要 bump パス 20 件、除外パス 10 件、対象外パス 20 件、対象境界への部分集合性、`[tool.bumpversion]` との列挙一致
- 受入ケース:
  - 版更新を要求するかどうかの判定を、対象境界を所有するモジュール（`.github/scripts/hve_scope.py`）の公開 API として単一実装で提供する。
  - 版更新を要求するパスの集合は対象境界の部分集合とし、対象境界に一致しないパスを版更新の対象へ戻さない。
  - 版番号・変更履歴の同期先ファイル自身（`pyproject.toml`, `hve/__init__.py`, `CHANGELOG.md`）は版更新を要求しない。除外しないと版更新のための変更自体が次の版更新を要求する。
  - 同期先ファイルの列挙は `pyproject.toml` の `[tool.bumpversion]` 設定と一致し、設定と乖離した独自の列挙を保持しない。
  - 独立ライフサイクルのパス（`mdq/**`, `cq/**`, `tools/skills/markdown_query/**`, `tools/skills/code_query/**`）は版更新を要求しない。
  - `mdq.toml` / `cq.toml` は独立ライフサイクルの除外に含めず、版更新を要求するパスとして扱う。
  - 対象境界の判定表を版管理側で再宣言しない。

#### FR-MAINT-09 — §13 Step 表と registry の横断 parity
- 判定: ✓（RED：是正前 5 failed / 32 passed。GREEN：§13.2 / §13.3 / §13.7 を registry へ同期後 37 passed）
- 対応テスト:
  - [hve/tests/test_requirement_section13_parity.py](hve/tests/test_requirement_section13_parity.py) — GREEN、37 passed。検査モード表・除外理由・ID 集合・不正トークン・タイトル対応
- 受入ケース:
  - registry へ登録済みの Workflow が検査モード表にも除外 allowlist にも無い場合に失敗する。
  - 除外 allowlist の各項目が理由文字列を持つ。
  - `strict` の節では表の Step ID 集合が registry の全 Step ID 集合と一致する。
  - `subset` の節では表の Step ID が registry に実在する（要約表としての部分集合を許す）。
  - Step ID 列に ID として解釈できないトークンを置かない。要約表では範囲表記に限り許容する。
  - 表の Step タイトルが registry の同一 Step を指す（記号・空白・連体助詞「の」を除去した正規化後の包含で判定）。
- 既存責務境界:
  - Step 集合の一致検査は本テストが単一実装として担う（FR-MAINT-07）。[hve/tests/test_requirement_definition_adfdv_section.py](hve/tests/test_requirement_definition_adfdv_section.py) と [hve/tests/test_ard_requirement_parity.py](hve/tests/test_ard_requirement_parity.py) は当該 Workflow 固有の検査（fan-out parser 名・旧パス不在・見出し名・4 表示グループ対応・既定 tuple）だけを保持する。

### markdown-query 検索品質の回帰計測（§3.8）

#### FR-MDQ-01 — ゴールデンクエリによる top-1 / top-k 正解率の機械算出
- 判定: ✓（RED：evaluator は collection error、benchmark 契約は 2 failed / 2 passed。GREEN：evaluator / benchmark / vendor parity の全 focused test が成功）
- 対応テスト:
  - [mdq/tests/test_golden_eval.py](mdq/tests/test_golden_eval.py) — GREEN。行範囲包含、path-only / 行範囲欠落の不正解、top-1 / top-k、空集合を `None` とする集計、schema / duplicate / path / line / anchor の fail-closed、repository 外 path 拒否、20 問の一意 anchor
  - [mdq/tests/test_benchmark_golden_contract.py](mdq/tests/test_benchmark_golden_contract.py) — GREEN。正解判定を再実装せず shared `score_query` を実呼び出しすること、明示 repo root、実 DB path、engine / config / golden / dependency provenance
  - [hve/tests/test_mdq_vendor_sync.py](hve/tests/test_mdq_vendor_sync.py) — GREEN。`mdq/golden_eval.py` と `mdq/search.py` を含む配布対象の全ファイルについて vendor 複製が byte-for-byte 一致し、欠落・余剰・リポジトリ固有物の混入が無いこと
- 受入ケース:
  - ヒットのパスが期待パスと一致し、かつヒットの行範囲（閉区間）が期待行番号を含む場合にだけ正解と判定する。
  - パスが一致しても期待行番号が行範囲外なら不正解と判定する。
  - `start_line` / `end_line` が欠落したヒットは不正解として扱う。
  - 1 クエリに複数の期待着地点がある場合、いずれか 1 件に着地すれば正解とする。
  - top-1 正解率は 1 位ヒットのみ、top-k 正解率は上位 k 件のいずれかで判定する。
  - ゴールデンクエリ集に実在しないパス、または対象ファイルの行数を超える行番号が含まれる場合は検証エラーを返し、計測を実行しない。
  - 生成物（inventory CSV 等）を期待着地点にするエントリは `anchor`（当該行に含まれる部分文字列）を必須とし、再生成による行ずれを fail-closed で検出する。検出時は修正先行番号をエラーに含める。
  - `tools/skills/markdown_query/benchmark.py` は当該判定実装を呼び出し、独自の正解判定を持たない。
- 非退行実測（2026-07-30 / FTS5 `detail=none` 化と返却単位追加の際）:
  - 計測条件を揃えるため、ベースラインは `git worktree add --detach <tmp> HEAD` の独立ツリーで測定し、両方とも索引を完全再構築して `--db .mdq/index-ja-jp-heading.sqlite` を明示した。
  - ベースラインコード + ベースライン文書: top-1 **0.45** / top-k **0.75**
  - 候補コード + ベースライン文書: top-1 **0.45** / top-k **0.75** → **既定エンジン（in-memory BM25）経路では**検索実装の変更が正解率に影響しない。`--engine fts5` の結果は設計上変わる（日本語クエリが 0 件 → ヒット）ため、本比較の対象外である。
  - 候補コード + 候補文書: top-1 **0.40** / top-k **0.75**。差分は REQ-01 の 1 問のみで、原因は本変更で `FR-MDQ-03` を §3.8 へ追記しチャンクが伸び、BM25 の文書長正規化で隔の §3.9 に 1 位を譲ったこと（§3.8 の score 15.89 → 13.74）。期待着地点は引き続き top-5 内にある。
  - コーパスの変化によるもので検索実装の退行ではないため、**ゴールデンクエリ集は変更していない**。

#### FR-MDQ-02 — 表形式ファイル（CSV / TSV）の行単位索引
- 判定: ✓（RED：実装前は `TypeError: build_index() got an unexpected keyword argument 'tabular_globs'` 他で 25 failed。GREEN：25 passed）
- 対応テスト:
  - [mdq/tests/test_tabular_index.py](mdq/tests/test_tabular_index.py) — GREEN、25 passed。設定未宣言時の非索引、1 データ行 = 1 チャンク、ヘッダ行除外、物理行番号、引用符内改行、文脈ヘッダ生成、`列名: 値` 本文、タグ生成と絞り込み、strategy 非依存、増分更新と prune、空 / ヘッダのみ / 列数不足の頑健性
- 受入ケース:
  - `[index].tabular` が未宣言なら CSV / TSV を 1 行も索引しない。
  - 宣言すると、対象ファイルのデータ行数と同数のチャンクが生成される（ヘッダ行はチャンクにしない）。
  - チャンクの `start_line` / `end_line` はレコードの物理行番号であり、引用符内改行を含むレコードでは `start_line < end_line` となる。
  - `heading_path` は `<拡張子を除いたファイル名> > <列名>=<値>` を先頭 3 列ぶん連結した値である。
  - `text` は空でない全列を `列名: 値` 形式で改行連結した値である。
  - `tags` は先頭 3 列の `列名=値` であり、`--tags` による絞り込みが機能する。
  - `--strategy` を変えても表形式ファイルの行チャンクは同一内容になる。
  - 内容が変わらないファイルは再索引時に skip され、ディスクから消えたファイルは prune で除去される。
  - 空ファイル・ヘッダのみのファイルはチャンク 0 件として扱い、索引を壊さない。

#### FR-MDQ-03 — 検索応答の返却単位の選択
- 判定: ✓（RED：実装前は `TypeError: search() got an unexpected keyword argument 'return_unit'` 他で 6 failed / 1 passed。GREEN：7 passed）
- 対応テスト:
  - [mdq/tests/test_search_return_unit.py](mdq/tests/test_search_return_unit.py) — GREEN、7 passed。既定の行窓、チャンク全文、単位間の順位一致、微小予算での先頭 1 件保証、同一予算での件数単調性、FTS5 経路での適用、CLI 引数と既定値
- 受入ケース:
  - 無指定時はヒット行を中心とする行範囲を返す（既定の変更禁止）。
  - チャンク単位を指定すると、ヒットを含むチャンクの `text` 全体をそのまま返す（400 字の切り詰めを適用しない）。
  - 単位を切り替えても、十分な予算のもとではヒットの `chunk_id` 列と順位が一致する。
  - 予算を小さくしても先頭 1 件は必ず返る。
  - 同一予算ではチャンク単位の応答件数が行単位以下になる（実測: 行単位 2 件 / チャンク単位 1 件）。
  - CLI は単位を選択する引数を公開し、既定値は行単位である。
  - FTS5 経路と in-memory BM25 経路のどちらでも同じ単位制御が効く。

#### FR-MDQ-04 — MRR@k / 絞り込み有無の 2 条件 / ホールドアウトによる既定値変更の裏付け
- 判定: ✓（RED：MRR は `KeyError: 'mrr_at_k'` で 5 failed、broad 条件は `unrecognized arguments: --ignore-golden-paths` で 2 failed。GREEN：両ファイル合計 44 passed）
- 対応テスト:
  - [mdq/tests/test_golden_eval.py](mdq/tests/test_golden_eval.py) :: `TestMeanReciprocalRank` — GREEN。5 tests。順位の逆数の平均、k 件内に正解が無いクエリの寄与 0、順位 k 超過の寄与 0、空入力と順位未付与時の非捏造
  - [mdq/tests/test_benchmark_golden_contract.py](mdq/tests/test_benchmark_golden_contract.py) :: `test_golden_summary_carries_mrr` / `test_markdown_report_renders_mrr` — GREEN。集計とレポート出力
  - [mdq/tests/test_benchmark_golden_contract.py](mdq/tests/test_benchmark_golden_contract.py) :: `test_default_condition_applies_the_golden_path_filter` / `test_broad_condition_ignores_the_golden_path_filter` / `test_report_params_distinguish_the_two_conditions` — GREEN。絞り込み有無の 2 条件とレポート上の区別
- 受入ケース:
  - MRR@k は、先頭 k 件のうち最初の正解ヒットの順位の逆数をクエリごとに求めた平均である。
  - 先頭 k 件内に正解が無いクエリの寄与は 0 である。
  - 順位判定は FR-MDQ-01 の正解判定実装（`mdq.golden_eval`）を用い、別実装を持たない。
  - ゴールデンクエリ集の対象パス絞り込みを適用する条件と、適用せずリポジトリ全体を候補とする条件の双方で計測でき、レポート上で区別できる。
  - 順位付けに影響する既定値の変更は、決定に用いたクエリ集と、決定に用いていない別のクエリ集の双方の計測結果を根拠として記録する。

#### FR-MDQ-05 — 見出し経路を語彙照合へ含める
- 判定: ✓（RED：見出しにだけある語でヒットせず 2 failed。GREEN：3 passed）
- 対応テスト:
  - [mdq/tests/test_search_ranking.py](mdq/tests/test_search_ranking.py) :: `test_term_present_only_in_the_heading_reaches_the_chunk` / `test_heading_text_does_not_leak_into_the_excerpt` / `test_grep_mode_matches_the_body_only` — GREEN
- 受入ケース:
  - 見出し経路にだけ現れる語で当該チャンクがヒットする。
  - 応答の抜粋に見出し経路の文字列が混入しない。
  - ヒットの行範囲は本文の位置を指し、見出し連結によって変化しない。
  - grep モードは本文だけを照合し、見出し経路にだけ一致するチャンクを返さない。

#### FR-MDQ-06 — 文書長正規化係数の単一定数化
- 判定: ✓（RED：`AttributeError: module 'mdq.search' has no attribute 'LENGTH_NORM_B'` で 3 failed。GREEN：3 passed）
- 対応テスト:
  - [mdq/tests/test_search_ranking.py](mdq/tests/test_search_ranking.py) :: `test_length_normalisation_is_declared_as_a_single_constant` / `test_rank_bm25_receives_the_shared_constant` / `test_builtin_bm25_receives_the_shared_constant` — GREEN
- 既定値の根拠: 開発用 40 問とホールドアウト 20 問の filtered / broad 全 4 スライスで、`b=0.2` のみが従来値 `0.75` を一つも下回らなかった（holdout broad MRR 0.3500 → 0.5175）。`b=0.0` は holdout filtered を 0.8625 → 0.8375 へ下げるため却下。
- 受入ケース:
  - 文書長正規化係数が実装内の単一の定数として定義されている。
  - `rank_bm25` 利用時と内蔵 BM25 利用時の双方へ同じ係数が渡る。
  - 既定値の変更は FR-MDQ-04 の 2 つのクエリ集による計測結果を根拠として記録される。

#### FR-MDQ-07 — 応答トークン予算の実表現基準化
- 判定: ✓（RED：`ImportError: cannot import name 'tokens' from 'mdq'`、および予算 400 に対し実 618 tokens が通過し 2 failed。GREEN：7 passed）
- 対応テスト:
  - [mdq/tests/test_tokens.py](mdq/tests/test_tokens.py) — GREEN。4 tests。空文字列、計測器名の公開、日本語の過小評価回避、検索モジュールの非即時 import
  - [mdq/tests/test_search_budget.py](mdq/tests/test_search_budget.py) — GREEN。3 tests。JSON 表現基準の予算、先頭 1 件保証、metadata 分の件数削減
- 実測: 実索引 40 問で「`--max-tokens 800` を実応答が超過した割合」が 90% → **0%**（実トークン最大 1,957 → 790）。代償として平均件数は 5 → 2.23 件となり、broad の Top-5 は予算に依存する。
- 受入ケース:
  - 予算判定は、各ヒットを 1 行 1 JSON で表現したときのトークン数を用いる（抜粋本文だけではない）。
  - 同じ抜粋でも metadata を含む分だけ予算を多く消費し、従来の文字数近似より小さい件数で打ち切られ得る。
  - 予算を超えても先頭 1 件は必ず返る（FR-MDQ-03 と同一の実装）。
  - 計測器の有無を `counter_name()` で識別できる。
  - 検索モジュールの import 時点で tokenizer を読み込まない。

#### FR-MDQ-08 — CJK bigram 照合と path / 見出し重みの文脈付与
- 判定: ✓（RED：`AttributeError: module 'mdq.tokenize' has no attribute 'scoring_terms'` / `... no attribute 'CJK_CHAR_RANGES'` で 8 failed（当時 8 件）および 5 failed, 2 passed。GREEN：9 passed / 7 passed）
- 対応テスト:
  - [mdq/tests/test_tokenize_bigram.py](mdq/tests/test_tokenize_bigram.py) — GREEN。9 tests。トークナイズ単位（RED 後のレビュー反映で `_TOKEN_RE` との範囲突合を検知する 1 件を追加）
  - [mdq/tests/test_search_bigram_context.py](mdq/tests/test_search_bigram_context.py) — GREEN。7 tests。照合対象と抜粋非汚染
- 実装位置: `mdq/tokenize.py::scoring_terms` / `CJK_CHAR_RANGES`、`mdq/search.py::_scoring_text` / `HEADING_WEIGHT`
- 受入ケース:
  - 連続する CJK 文字列は隣接 2 文字の語に分解される（例: 4 文字の語から 3 個の 2 文字語が得られる）。
  - 隣接する CJK 文字を持たない 1 文字は、その 1 文字が語になる。
  - 既定では、同一箇所について 2 文字の語と 1 文字の語が同時に照合対象へ含まれない。
  - ASCII 英数字の連なりは分割されない。
  - CJK 文字の範囲が実装内の単一の定義として公開されている。
  - リポジトリ相対パスにだけ現れる語で当該チャンクへ到達できる。
  - 本文長と出現回数を揃えた制御コーパスにおいて、見出し経路にだけ現れる語のスコアが、同一語が本文にだけ現れる場合より高い。
  - 応答の抜粋にパスおよび見出し経路の文字列が混入しない。
  - ヒットの行範囲が本文の位置を指し、文脈付与によって変化しない。
  - grep モードは本規定の影響を受けず、本文だけを照合する。
  - 全文検索索引を用いる経路は本規定の影響を受けない。
- 既定値変更の裏付け: FR-MDQ-04 の手続きに従い、開発用 40 問とホールドアウト 20 問について filtered / broad の 4 スライスすべてで変更前を下回らないことを確認した（P7）。

| スライス | 変更前 top-1 / top-k / MRR@5 | 変更後 | 差 | 判定 |
|---|---|---|---|---|
| dev / filtered | 0.675 / 0.85 / 0.7583 | 0.675 / 0.85 / 0.7583 | ±0 / ±0 / ±0 | PASS |
| dev / broad | 0.225 / 0.25 / 0.2313 | 0.225 / 0.35 / 0.2792 | ±0 / +0.10 / +0.048 | PASS |
| holdout / filtered | 0.85 / 0.95 / 0.900 | 0.95 / 1.00 / 0.975 | +0.10 / +0.05 / +0.075 | PASS |
| holdout / broad | 0.40 / 0.50 / 0.450 | 0.55 / 0.85 / 0.675 | +0.15 / +0.35 / +0.225 | PASS |

- コストの実測（同一プロセス内の A/B、3 回の最小値）: クエリ毎のコーパス構築が 1,078.3 ms → 1,552.8 ms（**+474.5 ms / クエリ、+44.0%**）。同じ holdout broad の改善幅を得るために A2 で評価した `bge-reranker-base` は +60,849 ms / クエリを要した。本コストに対する事前の合格基準は置いていない（P7 の Critical 指摘として記録済み）。

#### FR-MDQ-09 — 索引と作業ツリーの乖離検知
- 判定: ✓（RED：`ImportError: cannot import name 'freshness' from 'mdq'` による collection error 1 件。GREEN：9 passed）
- 対応テスト:
  - [mdq/tests/test_freshness_guard.py](mdq/tests/test_freshness_guard.py) — GREEN。9 tests
- 実装位置: `mdq/freshness.py`（`check` / `FreshnessReport` / `emit_warning` / `RECOVERY_HINT`）、`mdq/cli.py::--no-freshness-check`
- 受入ケース:
  - 検知はファイルのサイズと更新時刻の比較だけで行い、内容ハッシュを読まない。
  - 内容が同一で更新時刻だけが変わったファイルも乖離として報告されうる（安価さとの引き換えとして許容する）。
  - 索引済みファイルの乖離を検知する。索引に無いファイルの発見を含める場合は、その可否の根拠として所要時間の計測結果を記録する。
  - 乖離時は、乖離ファイル数と復旧手順を含む情報を、ヒット行とは別の経路で取得できる。
  - 当該情報を CLI が出力する場合も、ヒットの JSONL を出力するストリームへ混入させない。
  - 乖離時もヒットの機械可読表現（1 ヒット 1 行の JSON）の形式は変わらない。
  - 再索引を行う実装では、その適用条件が実装内の単一の定数として定義されている。
  - 検知処理が例外で失敗しても検索結果は返る。
  - 呼び出し側が検知を無効化できる。
  - 常駐の索引更新機構が動作していない環境でも検知が成立する。
- 実測（要件の根拠）: 索引済み 162 ファイルに対し、サイズ+更新時刻の比較は最小 4.7 ms / 中央値 5.0 ms、内容 SHA-1 は最小 239.1 ms / 中央値 259.6 ms。前者を採る。出荷実装の `mdq.freshness.check` 経由でも最小 6.7 ms / 中央値 8.7 ms であり、絞り込みありの検索 1 回（実測 546 ms）の 1.2〜1.6% にとどまる。

#### FR-MDQ-10 — 本文を含めない返却単位
- 判定: ✓（RED：`argument --return-unit: invalid choice: 'locations'` で 5 failed, 3 passed。GREEN：8 passed）
- 対応テスト:
  - [mdq/tests/test_return_unit_locations.py](mdq/tests/test_return_unit_locations.py) — GREEN。8 tests
- 実装位置: `mdq/search.py::_excerpt` / `_strip_bodies` / `Hit.snippet: str | None`、`mdq/cli.py::--return-unit locations`
- 実測（出荷実装、同一プロセス・同一索引スナップショット）: 指標は「返却されたヒットに期待箇所が含まれた割合（到達率）」。`locations` を `-k 20 --max-tokens 800` で使うと 0.875 / 0.675 / 1.00 / 0.95（dev filtered / dev broad / holdout filtered / holdout broad）で、平均 6.72〜7.05 件 / 714〜756 tokens。同じ到達率帯を行単位で得るには `-k 5 --max-tokens 1600`（0.850 / 0.600 / 1.00 / 0.95、1,234〜1,316 tokens）を要し、予算を上げるより安い。top-1 正解率は返却単位では変わらない。
- 受入ケース:
  - 当該単位の応答は識別子・パス・見出し経路・行範囲・スコアを含み、本文の抜粋を含まない。
  - 既定は FR-MDQ-03 の既定から変わらない。
  - 予算算定は FR-MDQ-03 / FR-MDQ-07 と同一実装であり、本単位専用の算定を持たない。
  - 十分な予算のもとでは、本単位とほかの単位でヒットの順位と `chunk_id` 列が一致する。
  - 同一予算のもとでは、本単位の応答件数が行単位以上になる（抜粋を含めない分だけ安いためであり、FR-MDQ-03 の予算規則の帰結）。
  - 本単位で返した識別子が既存の本文取得手段でそのまま解決できる。
  - 祖先・近傍・分割片の拡張を併用しても本文が含まれない。

### code-query ソースコード検索（§3.9）

> **bootstrap 状態**: FR-CQ-01 / FR-CQ-02 / FR-CQ-03 は実装済み。他は要件のみ確定しており、実装とテストは後続タスクで追加する。`要追加` の節を現行カバレッジに算入しない。

#### FR-CQ-01 — mdq との責務分離と profile 単位の索引分離
- 判定: ✓（RED：実装前は `ImportError: cannot import name 'config' from 'cq'` で collection error。GREEN：108 passed）
- 対応テスト:
  - [hve/tests/test_code_query_scope_contract.py](hve/tests/test_code_query_scope_contract.py) — GREEN。`cq/**` / `cq/tests/**` / `cq.toml` が §3.7 対象境界に含まれること、`cq/tests/` がテスト索引カテゴリを持つこと、FR-CQ-* が要求定義・マッピング・機能索引の 3 者で整合すること
  - [cq/tests/test_store.py](cq/tests/test_store.py) — GREEN。profile 別 DB パス、profile 間で DB を共有しないこと、`.cq/` 配下であり mdq 索引と別ファイルであること、profile 名の検証
  - [cq/tests/test_config.py](cq/tests/test_config.py) — GREEN。設定不在時の fail-closed、profile / roots の解決、不正な root の拒否
  - [cq/tests/test_discovery.py](cq/tests/test_discovery.py) — GREEN。`.md` / CSV / TSV を一切索引しないこと
- 受入ケース:
  - `cq` は `.md` と CSV / TSV を索引しない。
  - `cq` の索引 DB は `mdq` の索引 DB と別ファイルであり、同一コーパスへ混在しない。
  - profile ごとに索引ルートと DB ファイルが 1 対 1 で対応する。
  - 設定ファイルが存在しない場合は fail-closed とし、既定ルートを推測しない。

#### FR-CQ-02 — ゴールデンクエリによる正解率・トークン・レイテンシの機械算出
- 判定: ✓（RED：実装前は `ImportError: cannot import name 'golden_eval' from 'cq'` で collection error。GREEN：39 passed）
- 対応テスト:
  - [cq/tests/test_golden_eval.py](cq/tests/test_golden_eval.py) — GREEN。行範囲包含による正解判定、パス一致のみの不採用、行範囲欠落ヒットの不正解扱い、top-1 / top-k 集計、クエリごとのレイテンシ記録、ゴールデンクエリ集の fail-closed 検証（実在パス・行数超過・profile / intent 妥当性・anchor ズレ）
  - [cq/tests/test_benchmark.py](cq/tests/test_benchmark.py) — GREEN。対照群 2 種の同時計測、regex 意図クエリの正規表現照合、cold / warm レイテンシ、使用トークン計数器の明示、未知対照群と不正 `--paths` の拒否、独自正解判定を持たないこと
  - [cq/tests/test_tokens.py](cq/tests/test_tokens.py) — GREEN。計数器名と実挙動の一致、`tiktoken` の遅延 import
- 受入ケース:
  - ヒットのパスが期待パスと一致し、かつ行範囲（閉区間）が期待行番号を含む場合にだけ正解と判定する。
  - パス一致のみ、または行範囲欠落のヒットは不正解と判定する。
  - top-1 / top-k 正解率、1 クエリあたり応答トークン数、cold / warm レイテンシを算出する。
  - 対照群（grep 相当の行単位走査、ファイル全文取得）の応答トークン数を同時に算出する。
  - 実在しないパス、行数超過の行番号、未知の profile / intent、ずれた anchor を含むゴールデンクエリ集は fail-closed で拒否する。
  - ベンチマークは単一の正解判定実装を呼び出し、独自判定を持たない。
- **ゴールデン集を 42 → 56 問へ拡張した（2026-08-15）**: `natural` intent が 6 問（日本語 2 / 英語 4）しかなく、1 問の増減が 17〜50% 動くため意味検索の可否を判定できなかった。日本語 10 / 英語 10 の計 20 問へ増やし、1 問 = 5% の分解能にした。日本語の文体は実利用ログの分布に合わせ「〜する実装／処理」型 4 / 疑問形 2 / 単語羅列 2 とし、6 問は同じ着地点へ日英ペアを張って「日本語の問い → 英語のコード」の橋渡しだけを切り出せるようにした。着地点は `.cq` 索引から選び、anchor がリポジトリ全体で一意であることを追加前に検証している（`cq/languages/treesitter.py::chunk_spans` は 14 ファイルに同名があり正解が一意にならないため、`mdq/usage_stats.py::aggregate_usage_stats` へ差し替えた）。

#### FR-CQ-03 — 索引ストアと除外規約
- 判定: ✓（RED：実装前は `ImportError: cannot import name 'config' from 'cq'` で collection error。GREEN：108 passed）
- 対応テスト:
  - [cq/tests/test_discovery.py](cq/tests/test_discovery.py) — GREEN。追跡ファイル列挙コマンドの固定、profile root 絞り込み、拡張子 allowlist、vendoring / ミニファイ、資格情報パターン、上限サイズ、宣言除外、stat 失敗時の skip、不正パスの skip、大文字小文字を区別する照合、死んだ除外パターンを持たないこと、決定性
  - [cq/tests/test_store.py](cq/tests/test_store.py) — GREEN。全テーブルと FTS5 ミラー 2 種の生成、trigram + `detail=none`、`unicode61` 列構成、スキーマバージョンの記録と不一致時の再構築要求、索引不在時のエラー、cascade 削除、`.cq/` の gitignore
  - [cq/tests/test_config.py](cq/tests/test_config.py) — GREEN。`max_file_bytes` の既定と上書き、組込除外の常時適用、宣言除外の追加
- 受入ケース:
  - ファイル列挙は追跡ファイル列挙を単一入力とし、ignore 設定を迂回しない。
  - vendoring 配下・生成物・ミニファイ済み・ソースマップを索引しない。
  - 秘密情報を含み得るファイル（環境変数ファイル、秘密鍵、宣言済みパターン一致）を索引しない。
  - 上限サイズ超過ファイルを索引しない。
  - 除外判定に失敗したファイルは索引しない（fail-closed）。
  - スキーマバージョン変更時に既存索引を検出して再構築を要求する。
- 実リポジトリでの結果: profile=hve 699 ファイル / 9.15 MB、profile=app 154 ファイル / 0.75 MB。`vendor/` と `hve/gui/i18n/` の漏れ 0 件。

#### FR-CQ-04 — 定義シンボル索引
- 判定: ✓（RED：実装前は `ImportError: cannot import name 'indexer' from 'cq'` で collection error。GREEN：135 passed）
- 対応テスト:
  - [cq/tests/test_python_symbols.py](cq/tests/test_python_symbols.py) — GREEN。qualname / kind / signature / parent / docstring 先頭行 / 修飾子 / テスト判定、入れ子定義、async 定義、構文エラー時の `ExtractionError`、決定性、位置順
  - [cq/tests/test_indexer.py](cq/tests/test_indexer.py) — GREEN。初回索引、ファイル同一性（SHA-1 / parser / サイズ）、未変更 skip、変更時の再索引、古いシンボルの置換、削除時の prune、rebuild、BOM 付きファイルを降格させないこと、構文エラー時の lite 降格と索引継続、symbol_id の安定性と一意性
  - [cq/tests/test_treesitter_languages.py](cq/tests/test_treesitter_languages.py) — GREEN。Java / Go / Rust / C / C++ の期待シンボルを多重集合で照合、行範囲がファイル内に収まること、抽出の決定性、callable の signature 必須、doc / annotation / test 判定、`.h` の内容による言語判定、文法未導入時の `ExtractionError` 降格、および temp corpus を `build_index` で通す統合検証（`files.parser='tree-sitter'` の記録、symbols / chunks / refs / imports の永続化、chunk→symbol linkage）
  - [cq/tests/test_language_registry_contract.py](cq/tests/test_language_registry_contract.py) — GREEN。専用 regex 抽出器を `ast` と誤表示しないこと、登録済み全言語が parser を宣言すること、`chunks.symbol_id` が実在する symbol を指すこと、同一開始行の最小包含 owner 解決
- 受入ケース:
  - 各行がパス・修飾名・名称・種別・開始行・終了行・シグネチャ・親・docstring 先頭行・修飾子・テスト判定を保持する。
  - 同一入力に対して抽出結果が決定的である。
  - 内容が変わらないファイルは skip され、消えたファイルの行は prune される。
  - 構文解析に失敗したファイルは除外されず、低フィデリティで索引され、フィデリティが記録される。
  - BOM 付き UTF-8 の正当なソースを構文エラー扱いしない。
- 実測: profile=hve でフル索引 3.82 秒 / 705 ファイル / 12,465 シンボル（`python/ast` 650、残り 55 は言語未対応の `lite`）、増分 1.07 秒。profile=app は 0.52 秒 / 154 ファイル / 627 シンボル。
- 再実測（2026-07-30、tree-sitter 5 言語導入後にスキーマ v3 で全再構築。CLI 起動・チャンク生成・FTS 書き込みを含む壁時計）: profile=hve 770 ファイル / 13,523 シンボル / 11.6〜12.8 秒（3 回）、パーサ内訳 `ast` 705 / `lite` 64 / `regex` 1。profile=app 154 ファイル / 1,404 シンボル / 0.9 秒、`regex` 150 / `lite` 4。旧 DB（v2）は `cq stats` が fail-closed で拒否し再構築を要求することを実機で確認。
- **テストブロックを定義単位へ追加した（2026-08-15）**: JavaScript の `describe` / `it` / `test`、PowerShell の Pester `Describe` / `Context` / `It` を、ラベルを名前とする `is_test` シンボルとして抽出する。実測で zero-symbol ファイルが app:javascript 46/76、60.5%、hve:powershell 17/29、58.6%あり、その内訳を調べると JavaScript は 42 ファイルに 120 個、PowerShell は 6 ファイルに 118 個のテストブロックが存在した（宣言構文ではないため 1 件も拾えていなかった）。
  - 実装: `cq/languages/javascript.py` は `expression_statement`、`cq/languages/powershell.py` は `pipeline` を `Grammar.kinds` へ登録し、内側の call / command を見てラベルを返す。**内側のノード型を鍵にするとチャンク命名が効かない**: `treesitter.chunk_spans` は `Grammar.kinds` にあるノード型だけを命名し、予算に収まった時点で下位へ降りないため。
  - 対応テスト: [cq/tests/test_languages.py](cq/tests/test_languages.py) `TestJavaScriptTestBlocks`（RED 5 failed → GREEN）、[cq/tests/test_powershell_language.py](cq/tests/test_powershell_language.py) `TestPesterBlocks`（RED 6 failed → GREEN、同ファイル計 30 passed）。
  - 実測（before → after）: app:javascript zero-symbol 46 → **4**、symbols 196 → **353**、is_test 0 → **157**。hve:powershell zero-symbol 17 → **11**、symbols 77 → **195**、is_test 0 → **118**。named_chunks は app:javascript 279/377、hve:powershell 133/229。
  - 対象外と判定した残りの zero-symbol: shell 15 件 / batch 7 件 は 39 ファイルを目視し全件が宣言を持たないことを確認（パーサの欠陥ではない）。app:csharp 8 件はすべて top-level statements の `Program.cs`。
  - 誤検出の確認: `Describe -Name 'Foo'` 形式と、ラベルに `{` / `$` を含むものを全 PowerShell ファイルで検査し、いずれも 0 件。リポジトリに存在しない形への防御は過剰実装として見送った。

#### FR-CQ-05 — 字句索引と構造チャンク索引
- 判定: ✓（RED：実装前は `ImportError: cannot import name 'chunking' from 'cq'` で collection error。GREEN：167 passed）
- 対応テスト:
  - [cq/tests/test_chunking.py](cq/tests/test_chunking.py) — GREEN。camelCase / PascalCase / snake_case / 連続大文字の分割、単語 1 個の識別子を重複させないこと、定義単位のチャンク化、上限超過ノードの再帰分割、無名スパンのマージ、行数のみで境界を決めないこと、分割時の行範囲非重複と全行被覆、解析不能時と言語未対応時の窓分割、決定性
  - [cq/tests/test_fts_layers.py](cq/tests/test_fts_layers.py) — GREEN。チャンクの投入と prune、chunk_id の一意性、trigram 経由の索引化 `LIKE` 部分一致と再索引時の更新、分割語による語単位到達、アンダースコアのトークン内包、SQLite 内での `bm25()` ランキング、`detail=column` によるフレーズ非対応の明示
- 受入ケース:
  - 上限超過ノードは子ノードへ再帰分割され、上限未満の無名スパンは上限内で連結される。
  - 行数だけを根拠にチャンク境界を決めない（名前付き定義は必ず境界になる）。
  - 分割時に親ヘッダと子ノードの行範囲が重複せず、全行が過不足なく 1 回だけ被覆される。
  - 識別子を語境界で分割した語列が別フィールドとして検索可能である。
  - ランキングは SQLite 内（`bm25()` / `ORDER BY rank`）で完結する。
- 実測（profile=hve、原本 9.18 MB）: チャンク 12,652、フル索引 12.63 秒、索引 DB 34.19 MB（trigram 索引の増分は原本比 64%）、`LIKE` warm 2.3 ms、BM25 warm 2.4 ms。
- 再実測（2026-07-30）: profile=hve チャンク 13,348 / DB 40.42 MB、profile=app チャンク 512 / DB 4.18 MB。Java / Go / Rust / C / C++ は言語モジュールが構造チャンカを登録し、上限 1,600 / 200 文字の両方で全行被覆・非重複・決定性を検証済み。C# / JavaScript / TypeScript はチャンカ未登録のため行ウィンドウ分割のまま。
- 既知の制約: `chunks_fts` は `detail=column` のためフレーズクエリが実行時エラーになる。FR-CQ-06 の検索層でサニタイズまたは trigram 層への振り分けが必須。

#### FR-CQ-06 — 検索インタフェースとクエリルーティング
- 判定: ✓（RED：実装前は `ImportError: cannot import name 'cli' from 'cq'` で collection error。GREEN：200 passed。返却単位は RED 6 failed / 1 passed → GREEN 7 passed。**0 件時の緩和とパス層（2026-08-04）は RED 4 failed / 7 passed → GREEN 15 passed、および RED 5 failed / 3 passed → GREEN 9 passed**）
- 対応テスト:
  - [cq/tests/test_search.py](cq/tests/test_search.py) — GREEN。5 経路のルーティング、経路の応答への明示、明示モードによる上書き、0 件時の fallback、FTS5 メタ文字とフレーズのサニタイズ、3 文字未満の fail-closed、不正正規表現の拒否と候補上限の通知、パーサフィデリティ・snippet 幅・`--top-k` / `--max-tokens` の反映、索引不在時のエラー、CLI（search / def / get / stats）、起動時の任意依存 import 禁止、SQLite 内ランキング
  - [cq/tests/test_search_recall.py](cq/tests/test_search_recall.py) — GREEN（15 passed）。連言 0 件時の選言再試行、`match: or-fallback` の付与、連言で引けるときの非再試行、1 語時の非再試行、CJK（漢字 / ひらがな / カタカナ / ハングル）の除外、**全文検索クエリの発行回数そのもの**による再試行 1 回上限の検証
  - [cq/tests/test_search_path_route.py](cq/tests/test_search_path_route.py) — GREEN（9 passed）。パスにしか現れない語への到達、`route=path`、応答フィールド、ファイル先頭チャンクの返却、ファイルごと 1 件への畳み込みと順序、他層優先、最小長未満での非実行、`--paths` フィルタ、`--mode path` が存在しないこと
- 受入ケース:
  - トレース識別子 → シンボル完全一致 → 部分文字列 → 正規表現 → 自然文 の順で検索層を選択する。
  - 0 件時に経路別の連鎖で fallback し、選択結果を応答へ含める。
  - 正規表現検索は候補集合を絞り込んでから確定照合し、候補上限超過時は打ち切りを応答へ含める。
  - 応答は 1 ヒット 1 行の構造化形式で、パス・行範囲・スコア・抜粋・パーサフィデリティを含む。
  - 抜粋の単位を呼び出し側が選択でき、無指定時は行範囲を返す。チャンク単位を指定すると構造チャンクの本文全体を返す。単位を変えても `route` ・`score` ・順位は変わらない。対応テストは [cq/tests/test_search_return_unit.py](cq/tests/test_search_return_unit.py)。
  - 自然文の検索層が 0 件を返したとき、語の連言を選言へ 1 回だけ緩和して再試行する。緩和して得たヒットは判別可能な標識を持つ。語が 1 つのとき、および CJK を含むクエリでは緩和しない。連言でヒットする場合は再試行しない。対応テストは [cq/tests/test_search_recall.py](cq/tests/test_search_recall.py)。
  - すべての検索層が 0 件を返したときに限り、リポジトリ相対パスの部分一致で引く層を最後に試す。ファイルごとに 1 件へ畳む。最小長未満のクエリでは試行せず、エラーにもしない。他層がヒットする場合は到達しない。対応テストは [cq/tests/test_search_path_route.py](cq/tests/test_search_path_route.py)。
- 効果測定（golden 42 問 / top-k=5）:
  - profile=hve: top-1 **95.2%**（grep 相当 9.5% / ファイル全文 14.3%）、平均応答トークン **84.8**（同 1,083.0 / 187,854.4）、1 問 **9.6 ms**（同 2,196 ms / 769 ms）
  - profile=app: top-1 **95.2%**（同 71.4% / 76.2%）、平均応答トークン **70.6**（同 148.8 / 2,808.4）、1 問 **5.2 ms**
  - プロセス起動込みの cold latency: 平均 **298 ms**（5 回実測、278〜328 ms）
- 既知の限界: 日本語の自然文で英語のみのコードを探すクエリ（各 profile 1 件）は 0 件を返す。字句検索の原理的限界であり、誤った上位ヒットを返さない設計としている。
- 非退行実測（2026-07-30 / 返却単位追加の際、`--with-cq --baseline ""`）:
  - profile=hve: ベースライン（HEAD worktree）top-1 **0.9524** / top-k **0.9524** / 平均トークン **97.5** / **135.2 ms**
  - profile=hve: 候補 top-1 **0.9524** / top-k **0.9524** / 平均トークン **97.5** / **134.2 ms** → 正解率・トークンとも完全に不変
  - profile=app: 候補 top-1 **0.9524** / top-k **0.9524** / 平均トークン **73.5** / **18.7 ms**
  - 上の「効果測定」行の 84.8 トークン / 9.6 ms は当時のコーパスと計測条件での値。本変更の非退行判定は、同時期に取り直したベースラインとの一致をもって行っている。
- 非退行実測（2026-08-04 / 0 件時の緩和・パス層・予算のペイロード基準化の際、`--with-cq --baseline ""`）:
  - 索引を最新化した直後のベースライン: profile=hve top-1 **0.9524** / top-k **0.9524** / 平均トークン **280.8**、profile=app top-1 **0.9524** / top-k **0.9524** / 平均トークン **236.0**
  - 変更後: profile=hve top-1 **0.9524** / top-k **0.9524** / 平均トークン **280.9**、profile=app top-1 **0.9524** / top-k **0.9524** / 平均トークン **236.0** → **正解率は完全に一致**
  - 平均トークンの +0.1 は、新規テスト 4 ファイル（46 チャンク）が索引へ加わったことによる BM25 スコアの桁数変化。ゴールデン全 21 問について、変更した実装ファイルと新規テストが top-5 に現れないこと（0 / 21）、および経路の内訳に `path` と `or-fallback` が **0 件**であることを実測で確認しており、**コーパスの変化であり検索実装の退行ではない**。
  - `cq/tests` 全体は **587 passed**。配布キット同期・Skill 配線は **106 passed**、`.github/scripts/validate-skill-routing.py` は exit 0。
  - レイテンシは非退行判定に使用していない。本環境では同一コマンドの所要時間が 6 倍以上ばらつく（`pytest cq/tests` が 431.83 s と 69.85 s）。
- FR-CQ-12（`mdq` の非退行）は**実測していない**。本変更セットは `mdq` 配下のファイルを 1 つも編集しておらず、`mdq → cq` / `cq → mdq` の import はいずれも 0 件、索引 DB は FR-CQ-01 により物理分離されているため影響経路が存在しない。加えて本作業と並行して別セッションが `mdq/search.py` / `mdq/cli.py` / `mdq/tokenize.py` を編集中であり、測定値を本変更へ帰属できない。並行作業のコミット後に改めて実測すること。

#### NFR-CQ-01 — 応答トークンと起動コストの上限
- 判定: ✓（GREEN：200 passed。**予算のペイロード基準化（2026-08-04）は RED 2 failed / 3 passed → GREEN 5 passed**）
- 対応テスト:
  - [cq/tests/test_search.py](cq/tests/test_search.py) — GREEN。`cq/__main__.py` / `cq/cli.py` が任意依存（tiktoken / rank_bm25 / tree_sitter / watchdog / numpy / fastembed）を import 時に読み込まないこと、`cq/search.py` が `ORDER BY rank` を用い索引全体をロードしないこと、snippet が小窓であること、`--max-tokens` が応答を打ち切ること
  - [cq/tests/test_search_budget.py](cq/tests/test_search_budget.py) — GREEN（5 passed）。返却ペイロード全体（`ensure_ascii=True` の JSON）基準での予算遵守、chunk 単位でも同一の会計、先頭 1 件の無条件採用、予算と件数の単調性、`cq/search.py` がトークナイザ（`tiktoken` / `cq.tokens`）を import しないこと
  - [cq/tests/test_tokens.py](cq/tests/test_tokens.py) — GREEN。`tiktoken` の遅延 import
- 受入ケース:
  - 既定設定でヒットあたりの本文が一致箇所周辺の抜粋に限定される。
  - 1 クエリの応答トークン数の既定上限が設定可能である。
  - 上限の消費量を、抜粋の長さだけではなく、返却する 1 ヒット分の機械可読表現の全体（メタデータを含む）で見積もる。先頭 1 件は上限を超えても返す。見積りのために任意依存のトークナイザを検索経路へ導入しない。対応テストは [cq/tests/test_search_budget.py](cq/tests/test_search_budget.py)。
  - ランキングが索引エンジン内で完結し、索引全体をプロセスメモリへ読み込まない。
  - 検索サブコマンドの起動経路が任意依存を import 時に読み込まない。
- 実測: 平均応答トークン 84.8（hve）/ 70.6（app）、cold latency 平均 298 ms。

#### FR-CQ-07 — 参照グラフと出典トレース
- 判定: ✓（RED：実装前は `ImportError: cannot import name 'traces' from 'cq'` で collection error。GREEN：230 passed）
- 対応テスト:
  - [cq/tests/test_traces.py](cq/tests/test_traces.py) — GREEN。生成元が `FEATURE_ID_RE` を再宣言せず `cq.traces` から import し実行時に同値であること、`出典:` 参照からの ID / doc パス / アンカー抽出、規範 ID の直接抽出、行番号記録、決定性、`imports` / `refs` / `traces` の索引と prune、トレース ID からのコード位置解決、コード位置からの設計文書逆引き、設計文書本文を返さないこと、`cq refs` / `cq trace --id` / `cq trace --by-path`
- 受入ケース:
  - シンボル参照・モジュール依存・出典参照を索引する。
  - 出典参照の抽出パターンが単一箇所（`cq/traces.py`）に定義され、`hve-dev/generate_tdd_inventory.py` と重複定義されない。
  - トレース識別子 → コード位置、コード位置 → 設計文書パスとアンカー、の双方向で引ける。
  - 設計文書の本文を返さない。
- 実測: profile=hve で refs 67,820 / imports 5,667 / traces 810、profile=app で traces 923（うち出典参照 475）。`cq trace --id TEST-SVC-02-001` が `src/test/api/SVC-02.Tests/Svc02RedTests.cs:8` を返すことを実データで確認。
- 既知の制約: なし（profile=app の refs / imports が 0 だった件は FR-CQ-11 の C# / JS 参照抽出で解消。refs 5,811 / imports 279）。

#### FR-CQ-08 — 索引の鮮度と stale 検出
- 判定: ✓（RED：実装前は `ImportError: cannot import name 'freshness' from 'cq'` で collection error。GREEN：246 passed）
- 対応テスト:
  - [cq/tests/test_freshness.py](cq/tests/test_freshness.py) — GREEN。未変更時の fresh 判定、変更／削除の検出、新規検出のオプトイン、内容ハッシュを再計算しないこと、上限以下の自動再索引、上限超過時の stale 通知、既定 ON と明示無効化、単一ファイル再索引の所要時間、CLI の stale 行が最終行であること、watchdog による反映、`stop()` の冪等性、対象外ファイルの無視
- 受入ケース:
  - ファイルシステム監視で変更が索引へ反映される（`python -m cq watch`）。
  - 監視不在でも更新時刻とサイズだけの突合で stale を検出する（内容ハッシュを再計算しない）。
  - 差分件数が上限以下なら当該ファイルだけ再索引してから応答する。
  - 上限超過時は結果を返しつつ stale と差分件数を応答へ含める。
  - 索引不在時は 0 件を返さず、索引生成を要求するエラーとする。
- 実測（profile=hve、716 ファイル）: 鮮度チェック 26 ms、単一ファイル再索引 36 ms、鮮度ガード ON での `cq search` cold latency 247 ms。
- HVE Orchestrator からの watcher 自動起動（現状）: **実装済み**。[hve/orchestrator.py](hve/orchestrator.py) が `cq.watcher.CqWatcher` を構築・起動し、`cq_watch` / `cq_watch_debounce_ms` を [hve/tests/fixtures/option_parity_matrix.yaml](hve/tests/fixtures/option_parity_matrix.yaml) へ登録している。監視対象は設定ファイルで最初に宣言された profile のみで、当該仕様は [users-guide/skills-code-query.md](users-guide/skills-code-query.md) §11.4 に記載している。（本行は従前「非実装（意図的）：HVE Orchestrator からの watcher 自動起動は行わない」と記載していたが、実装と矛盾していたため 2026-08-04 に修正した）

#### FR-CQ-09 — トークン予算付き俯瞰出力
- 判定: ✓（RED：実装前は `ImportError: cannot import name 'repomap' from 'cq'` で collection error。GREEN：263 passed。**描画後基準への予算変更（2026-08-04）は RED 3 failed / 5 passed → GREEN 8 passed**）
- 対応テスト:
  - [cq/tests/test_repomap.py](cq/tests/test_repomap.py) — GREEN。被参照数による順位付け、自ファイル内参照の除外、同名定義数による減衰、テストコードの除外、パスフィルタ、予算内への収容、除外件数の報告と下位からの除外、本文非掲載、定義行の掲載、決定性、CLI（text / json）、非 ASCII 出力のリダイレクト耐性
  - [cq/tests/test_repomap_budget.py](cq/tests/test_repomap_budget.py) — GREEN（8 passed）。`render()` の出力を `tokens.count_tokens()` で測った値が予算以下であること（予算 200 / 400 / 1200）、除外件数の通知行を含めても超えないこと、掲載 0 件にしないこと、自己申告値が予算以下であること、予算と掲載件数の単調性、本文非掲載
- 受入ケース:
  - 出力がトークン予算内に収まる。予算の判定は、定義行だけでなく既定出力形式が付加する装飾（ファイル見出し・折り畳み記号・区切りの空行・除外件数の通知）を含めた実際の出力文字列全体に対して行う。予算を守った上で掲載 0 件にしない。対応テストは [cq/tests/test_repomap_budget.py](cq/tests/test_repomap_budget.py)。
  - 掲載順序が参照グラフ上の被参照数に基づき、名前衝突（同名定義）で歪まない。
  - 予算超過時は下位から除外し、除外件数を出力へ含める。
  - 本文を含めない。
- 実測（profile=hve、`--paths "hve/*" --max-tokens 400`）: 出力 397 tokens / 掲載 22 件 / 除外 1,378 件、所要 491 ms。

#### FR-CQ-10 — シンボル抽出の単一実装化
- 判定: ✓（RED：実装前は `ImportError: cannot import name 'surface_export' from 'cq'` で collection error。GREEN：373 passed）
- 対応テスト:
  - [cq/tests/test_surface_export.py](cq/tests/test_surface_export.py) — GREEN。列定義の単一化と生成元からの import、移設 5 関数が生成元に本体として残らないこと、`collect_surface_symbols` の委譲、`cq` 側に HVE 固有ポリシーが入らないこと、entrypoint を増やさないこと、再生成が committed CSV とバイト等価であること、決定性、対象外パスの不在、shell / workflow 面の維持
- 受入ケース:
  - `hve-dev/generate_tdd_inventory.py` が `cq.surface_export` の抽出結果を利用し、独自のシンボル抽出を保持しない。
  - 統合の前後で `hve-dev/hve-surface-inventory.csv` の列構成と内容が変化しない。
  - FR-MAINT-05 の「生成の正規 entrypoint は `hve-dev/generate_tdd_inventory.py`」を維持し、`cq` 側に第 2 の entrypoint を作らない。
  - HVE 固有ポリシー（実行面判定・テストパス判定・規範リテラル）は `SurfacePolicy` として呼び出し側から注入し、`cq` へ埋め込まない。
- 挙動保存の検証: 本 Sub で変更した 2 ファイルを除外した全ファイルについて、surface inventory の全行・全列が完全一致（`callers_count` を含む）。

#### FR-CQ-11 — 言語レジストリとパーサ降格
- 判定: ✓（RED：実装前は `ImportError: cannot import name 'csharp' from 'cq.languages'` で collection error。GREEN：324 passed。2026-07-30 の Java / Go / Rust / C / C++ 追加後は 436 passed。2026-08-03 の shell / PowerShell / batch / Scala / SQL 追加後は 541 passed。2026-08-06/07 の C#/JS/TS/tsx tree-sitter 昇格 + Python tree-sitter fallback + Scala val/var/given + SQL 9 方言化後は 633 passed, 0 deselected）
- 対応テスト:
  - [cq/tests/test_languages.py](cq/tests/test_languages.py) — GREEN。拡張子→言語の宣言が `cq/languages/__init__.py` 単一箇所であること、言語追加で `indexer` / `search` / `store` が変更不要であること、C# の型・メソッド・コンストラクタ・入れ子 qualname、宣言キーワードがシンボル種別を決めること（`interface` / `struct` / `enum` を `class` へ崩さない。`record` は最小 kind 語彙に無いため `class`）、class 以外の型のメンバが親を保つこと、宣言行と別行の `{` に追随すること、JS の class / function / メソッド / 代入関数、抽出失敗時の `lite` 降格と `files.parser` への記録、降格しても索引処理が失敗しないこと、**未登録言語の `lite` 抽出**、宣言行を参照として拾わないこと
  - [cq/tests/test_discovery.py](cq/tests/test_discovery.py) — GREEN。テストパス判定の単一定義（`discovery.test_path_sql`）を `search` / `repomap` が共有すること、`src/test/**` を含む判定
  - [cq/tests/test_language_registry_contract.py](cq/tests/test_language_registry_contract.py) — GREEN。専用 regex 抽出器を `ast` と誤表示しないこと、**discoverable な全言語が専用抽出器と parser を宣言すること**、言語モジュールが構造チャンカを登録できること、チャンカ未登録言語（合成 registry エントリ。C# は Phase 2 でチャンカを得たため代替できない）が窓分割へ fallback すること、言語側が重複・ファイル外の span を返しても core が行の分割へ正規化すること、parser の load 失敗を `ExtractionError` へ正規化して `lite` 降格すること、**graph 抽出器の失敗もシンボル抽出と同様に降格すること（2026-08-05 追加。RED：`.ps1` を 1 つ含むだけで `cq index` が `ExtractionError` で異常終了。GREEN：`degraded` 計上で正常終了）**、**`TestNewLanguageIndexIntegration`（temp corpus で `.sh` / `.ps1` / `.cmd` / `.scala` / `.sql` の discovery → `files.parser` → symbols / chunks / refs の永続化）**、**CLI import 時に `sqlglot` / `sqlfluff` を読み込まないこと**
  - [cq/tests/test_treesitter_languages.py](cq/tests/test_treesitter_languages.py) — GREEN。66 件。Java / Go / Rust / C / C++ の symbol / chunk / graph 契約、`.h` を C++ 固有ノード型で判定すること（parse error 数の多数決では判別できないことを固定する回帰テストを含む）、文法未導入時の降格、temp corpus を用いた `build_index` 統合検証
  - [cq/tests/test_shell_language.py](cq/tests/test_shell_language.py) — GREEN。12 件。Bash の 2 つの関数形式、本体を除いたシグネチャ、`#` コメントの doc_head、`command` の参照化と変数宣言を参照にしないこと、`source` が import ではなく参照になること
  - [cq/tests/test_powershell_language.py](cq/tests/test_powershell_language.py) — GREEN。14 件。function / filter / class / enum / メソッド、**`script:BuildSection` のようなスコープ付き名を切り詰めないこと**、プロパティが対象外であること、`body` フィールドを持たない文法でもシグネチャが本体を含まないこと
  - [cq/tests/test_batch_language.py](cq/tests/test_batch_language.py) — GREEN。10 件。`label` だけが定義単位であること、`::` コメントをラベルと誤認しないこと、`call :label` と `call other.cmd` の両形式を参照化すること
  - [cq/tests/test_scala_language.py](cq/tests/test_scala_language.py) — GREEN。16 件。Scala 2 / 3 の object / class / trait / enum / type / def、object メンバが `method` になること、Scaladoc、選択子節を保つ import、**型エイリアスを他言語と同じく `type` で索引すること**、`val` と匿名 `given` が最小 kind 語彙の対象外であること
  - [cq/tests/test_sql_language.py](cq/tests/test_sql_language.py) — GREEN。27 件。`GO` バッチ区切り、**プロシージャ本体が内部の `;` で分断されないこと**、定義対象を自己参照にしないこと、Spark の MERGE、BigQuery の 3 パート名、**エスカレーション条件（sqlglot で本体まで取れる T-SQL では sqlfluff を起動しない）**、sqlfluff 未導入時の fallback、非 SQL 入力の `ExtractionError` 降格、決定性
  - [cq/tests/test_regex_language_improvements.py](cq/tests/test_regex_language_improvements.py) — GREEN。文字列・コメント内の `{` を brace 追跡が数えないこと、エスケープされた引用符で文字列が終了しないこと、C# / JavaScript のスコープ復帰
- 受入ケース:
  - 拡張子・パーサ・シンボル種別対応の宣言が言語ごとに 1 箇所へ局所化される。
  - 言語追加で索引・検索の中核実装が変更されない。
  - 高フィデリティパーサ不在時に低フィデリティへ自動降格し、索引と応答の双方へ記録する。
  - 降格を理由に索引処理全体が失敗しない。（2026-08-05 に graph 抽出経路の未対応を修正。`cq/indexer.py::_extract` にはあった降格が `cq/graph.py::extract` に無く、文法未導入環境では `.ps1` / `.sh` を含むだけで索引全体が落ちていた。他リポジトリへの配布キット導入で顕在化）
  - 任意依存が未導入でも標準ライブラリだけで成立する言語の索引と検索が動作する。
- 実測（profile=app、154 ファイル）: symbols 627 → **1,404**、refs 0 → 5,811 → **6,090**、imports 0 → **279**。ゴールデン評価は top-1 95.24% / top-k 95.24% で劣化なし。
- 実測（2026-08-03、両 profile の再構築）: **`lite` フィデリティのファイルが hve 64 → 0、app 4 → 0**。hve の `tree-sitter` は 72 件（shell 40 / powershell 26 / batch 6）、refs は 70,461 → 77,179。
  **ただし profile=app の symbols は 1,404 のまま変わらない**。実コーパスの `.sh` 45 件で lite と tree-sitter のシンボル名集合が完全一致するためで、昇格の利得は定義数ではなく **終了行（0 → 158）・doc（0 → 76）・参照（0 → 3,130）・構造チャンク** に現れる。
- 採用したパーサ backend（2026-07-30）: **公式の言語別 tree-sitter 文法**（`tree-sitter-java` / `-go` / `-rust` / `-c` / `-cpp`）を `pyproject.toml` の `code` extra へ任意依存として宣言した。文法は wheel に同梱されており実行時ダウンロードが不要なため、ローカル完結の前提（NFR-CQ-01）を破らない。
- 不採用（意図的）: `tree-sitter-language-pack` 1.13.5。文法を初回利用時にネットワーク取得する（`DownloadError: Language 'c_sharp' not available for download` を実測）ため、ローカル完結の前提を破る。
- 追加したパーサ backend（2026-08-03）:
  - **tree-sitter**: `tree-sitter-bash` / `-powershell` / `-batch` / `-scala` を `code` extra へ追加した。いずれも abi3 wheel に文法を同梱しており実行時取得なし。
  - **SQL**: `sqlglot`（`code` extra）を主とし、ルーチン本体を構造化できないときだけ `sqlfluff`（`code-sql` extra）へエスカレーションする。**`sqlfluff` を別 extra に分離したのは、`click<8.4.0` の pin が既定 extras の `semantic`（fastembed → huggingface-hub は `click>=8.4.0`）と衝突し `pip check` が exit 1 になることを実測したため**。
  - `Grammar` へ `callee_of` と `signature_of` の 2 フックを追加した。PowerShell と batch の call ノードが `function` / `name` フィールドを持たず、PowerShell の宣言ノードが `body` フィールドを持たないことを実測したため。既存 5 言語の振る舞いは不変。
  - **PL/pgSQL 本体の再パース**: `tree-sitter-sql`（MIT）を `code` extra へ追加し、`$tag$ ... $tag$` の中だけを再パースしてテーブル参照を拾う。sqlfluff / sqlglot / Oracle ラッパー方式 / tree-sitter-postgres はいずれも本体を構造化できないことを実測した上での選定。`object_reference` の親が `relation` / `from` / `insert` / `update` のものだけを採り、関数名・別名・列修飾子を除外する。
  - **PowerShell の公式パーサエスカレーション**: 文法の回復ノードが残ったファイルに限り `pwsh -NoLogo -NoProfile -NonInteractive` で `Parser.ParseInput` を呼び、定義と呼び出しを JSON で受け取る。ソースは stdin からデータとして渡すだけでスクリプトを実行しない。
- 制限（2026-08-03 の実測）:
  - **PostgreSQL の `$tag$` 本体（PL/pgSQL）は sqlglot / sqlfluff のいずれも 1 トークンとして扱う**。tree-sitter の SQL 文法で本体だけを再パースしてテーブル参照を拾うことで解消したが、手続き構文（`IF` / `LOOP` / `PERFORM`）自体は依然として構造化されない。
  - **tree-sitter-powershell は文法の偽陽性で 5 / 27 ファイルに ERROR ノードを生じる**。回復ノードが残ったファイルだけ `pwsh` 公式パーサへエスカレーションすることで取りこぼしは 0 件になったが、**`pwsh` が無い環境では tree-sitter の結果のままなので同じファイルでも環境によって定義数が変わる**。`parser` 値はどちらの経路でも `tree-sitter` のままで区別されない。
  - Windows batch 文法に関数の概念は無く、取れるのはラベル定義と呼び出しだけ。実コーパス 7 件はラベルを持たないため symbols 0 / refs 26。
  - `.scala` と `.sql` は両 profile に実ファイルが 0 件。`build_index` 経路は temp corpus の統合テストでのみ検証している。
- 不採用（意図的、2026-08-03）: `pglast`（GPL-3.0-or-later）、`bashlex`（GPL-3.0）、`sqloxide`（ストアド本体非対応）、`tree-sitter-sql-bigquery` 0.8.0（cp38-abi3 wheel が tree-sitter 0.26 と ABI 不整合で `OverflowError`）、`Microsoft.SqlServer.TransactSql.ScriptDom`（.NET ランタイム必須）。
- C# / JavaScript / TypeScript の扱い（2026-08-03 時点、移行前）: 標準ライブラリだけの brace 追跡パーサを維持していた。採用 backend での再評価は実 corpus（profile=app）で実施済みで、C# recall 89.1%（ボディ無し宣言 148 件が未検出、誤検出 0）、JavaScript recall 96.4%（オブジェクトリテラルのショートハンドメソッド 7 件が未検出）、TypeScript は実ファイル 0 件で測定不能だった。当時は tree-sitter への移行を言語モジュール 3 本と宣言依存の追加を伴うため本件の対象外とし、未実施の残作業として記録していた。
- **C# / JavaScript / TypeScript を tree-sitter 主へ昇格した（2026-08-06/07、上記の残作業を解消）**: `tree-sitter-c-sharp` / `tree-sitter-javascript` / `tree-sitter-typescript`（`language_typescript()` / `language_tsx()` の2文法）を `code` extra へ任意依存として追加した。`.tsx` は独立言語 `tsx` として registry 分離した。brace 追跡パーサは `extract_regex` / `extract_graph_regex` として維持し、文法未導入環境またはハンドル不能な構文（`ExtractionError`）でのみ自動降格する（FR-CQ-11 の降格要件を満たす）。降格を呼び出し元へ動的報告するため `LanguageSupport.extract_ex` フィールドを新設し、既存 12 言語は無変更（後方互換）。Python は `ast` を主のまま維持し、`tree-sitter-python` を新規フォールバック段として追加した（docstring は fallback 時に非回復、既知の制約として記録）。Scala は `val` / `var` / `given` / `class_parameter`（class/trait/object 直下のみ、`def` 本体内のローカル変数は索引雑音として除外）を追加。SQL は方言を 5 → 9（`mysql` / `sqlite` / `snowflake` / `duckdb` 追加）に拡張し、全方言で構造化できない場合は方言無指定の最終フォールバックを 1 回試す。
  - 実測（2026-08-07、profile=app 再構築）: symbols **1,404 → 1,559**（tree-sitter がレコードプロパティ・ジェネリックメソッド・インターフェースメンバ等を追加回収）、`by_parser` の `regex` は **150 → 0**（C# 74 + JavaScript 76 が tree-sitter へ昇格）。profile=hve は `by_parser` に `tree-sitter-partial`（ERROR ノード回復、2件）が新設された。
  - 既知の制約: tree-sitter 層は ES `import` のみ認識し、CommonJS `require(...)` は regex 層のみが認識する（軽微な既知差異、regression ではない）。
  - 検証: 対象 focused pytest 群（`test_treesitter.py` / `test_csharp_language.py` / `test_javascript_language.py` / `test_typescript_language.py` / `test_python_language.py` / `test_sql_language.py` / `test_scala_language.py` 等）と `cq/tests/` 全体で **633 passed, 0 deselected**。`hve/tests/test_cq_vendor_sync.py` と合わせて **685 passed**。
- 未解決: Universal Ctags / native parser との定量比較、外部 OSS corpus でのベンチマーク（U5）、macOS での install 実行検証（U6 の残り）。Linux は `.github/workflows/test-hve-python.yml` の `cq-python-tests` job で CI 化した。
- **任意依存を言語粒度へ分解した（2026-08-15）**: `code` extra は全言語の文法を一括で入れるため、使わない言語の wheel まで入る。`code-python` / `code-csharp` / `code-javascript` / `code-typescript` / `code-java` / `code-go` / `code-rust` / `code-c` / `code-cpp` / `code-scala` / `code-shell` / `code-powershell` / `code-batch` / `code-sqlglot` の 14 extra を `pyproject.toml` へ追加し、`hve/setup-hve.ps1 -CodeLanguages` / `hve/setup-hve.sh --code-languages` から選択できるようにした。未知の言語名は fail-closed で拒否する。`code` （全言語）と `code-sql`（sqlfluff）は従来のまま。
  - `.h` の内容判定には C / C++ の両文法が要るため、`code-c` / `code-cpp` はどちらも 2 つを入れる。
  - **`cq` が `mdq` の extra を借りていたのを修正した**: `watchdog`（`cq watch`）と `tiktoken`（トークン計上）を `code-watch` / `code-tokenizer` として `cq` 側へ宣言し、users-guide の導入手順から `.[mdq-watch]` / `.[mdq]` の案内を除いた。CI（`test-hve-python.yml`）も `pip install pytest tiktoken` の回避策をやめ extra 指定へ戻した。
  - 対応テスト: [hve/tests/test_dev_task_environment_contract.py](hve/tests/test_dev_task_environment_contract.py) — `code` extra が言語別 extra の和集合であること、`cq` の任意依存が `mdq` の extra を借りないこと、setup スクリプト（ps1 / sh 両方）が提供する言語名が extra 一覧と一致することを固定する。

#### FR-CQ-16 — 全検索層の並列実行と順位統合
- 判定: ✓（新規時 RED 9 failed → GREEN 18 passed。**改訂時**は `--fuse` 削除の RED 10 failed → GREEN 43 passed）
- 対応テスト:
  - [cq/tests/test_search_fusion.py](cq/tests/test_search_fusion.py) — GREEN。**語彙層だけを統合する手段が存在しないこと**、通常検索が実行内訳を残さないこと、`--semantic` で統合が起きること、逐次 fallback が到達しない候補への到達、全層の 1 本化、同一箇所の重複排除、決定性、`top_k` 上限、スコアの降順、`--mode` 明示時に単一層のままであること、**リテラル一致層が統合後も先頭に残ること**、その順序が単独実行時と一致すること、**cosine に閾値が無いため意味検索が 0 件を返さないこと**、`regex` を他層と統合しないこと
  - [cq/tests/test_search_activity.py](cq/tests/test_search_activity.py) — GREEN。非統合時に実行内訳を残さないこと、統合時に実行した層とその順序（symbol → substr → bm25 → path → semantic）を記録すること、`literal` と `merged` の内訳が返却件数を下回らないこと、`--explain` 指定時のみ最終行へ 1 行 JSON を出すこと、**`--fuse` が存在しないこと**
- 受入ケース:
  - **意味的類似度による検索層を含めるときに限り統合する**。語彙層だけを統合する手段を提供しない。
  - 統合は各層内の順位のみを根拠とし、層をまたいでスコアを直接比較しない。
  - トレース識別子・シンボル完全一致・部分文字列の各層は統合対象外とし、自身の順位を保って先頭に置く。
  - 同一入力に対して決定的である。
  - 実行した層とその件数を要求時のみ応答へ含める。
- 実測（golden 56 問 / top-k=5 / 同一プロセス・同一索引スナップショット、2026-08-15）:
  - **リテラル層を等価に統合すると退行する**: `symbol` intent の top-1 が 1.00 → 0.77、`substr` が 1.00 → 0.57、全体で 0.73 → 0.59。原因は、問いの文字列そのものを含む場所を返すのは 1 層だけで、順位の逆数和では複数層に現れる付随的な一致に構造的に負けること。リテラル層を統合対象外にして順位を保つ実装へ変えたところ、**rank 変化 0 件**。
  - **語彙層だけの統合は逐次 fallback と 56/56 問で順位が完全に一致した**（`analyse_saturation.py`：順位が異なるクエリ 0 件）。応答トークンだけが k=3 で 2.2〜2.4 倍になる。**この実測に基づき公開フラグ `--fuse` を削除し、統合を `--semantic` の内部動作へ限定した**。
  - 飽和点はアームと profile で異なる: `chain` は hve で k=1 / app で k=5、`fuse+semantic` は両方とも k=3。**`top_k` の既定値は 5 のままにした**（3 へ下げると app で `natural/en` を 1 問失うため）。
  - `symbol` / `substr` / `trace` / `regex` は k=1 で飽和し、k=1 に絞っても損失は 36 問中 0 問。ただし `_cap_tokens` が既にトークン予算で切っているため、intent 別の自動調整は実装していない。

#### FR-CQ-17 — 意味的類似度に基づく検索層
- 判定: ✓（RED: `cannot import name 'embeddings'` / `'vectors'` / `'semantic_index'` の collection error と `search() got an unexpected keyword argument 'semantic'` で 7 + 11 + 6 + 7 failed → GREEN: 31 passed）
- 対応テスト:
  - [cq/tests/test_embeddings.py](cq/tests/test_embeddings.py) — GREEN。`mdq` を import しないこと（部分文字列ではなく import 文の形で判定）、任意依存不在時に専用例外を出すこと、`(provider, model)` 単位のキャッシュ、既定モデルが fastembed の対応一覧に実在すること、L2 正規化、決定性、バイト列との往復
  - [cq/tests/test_vectors.py](cq/tests/test_vectors.py) — GREEN。本体索引と別パスであること、往復、**ファイルが変わった行を使わないこと**、再構築時の prune、モデルの記録、ストア不在時の空、別モデルのストアを無視すること、cosine 順、`top_k` 上限、同点時の決定的順序
  - [cq/tests/test_semantic_index.py](cq/tests/test_semantic_index.py) — GREEN。docstring が埋め込み対象になること、名前とシグネチャを含むこと、docstring が無いチャンクは本文へ落ちること、全チャンクにベクトルが付くこと、編集後の再構築で更新されること
  - [cq/tests/test_search_semantic.py](cq/tests/test_search_semantic.py) — GREEN。**日本語クエリが docstring 経由で英語コードへ到達すること**、実行内訳に現れること、融合なしでは動かないこと、ベクトル不在・別モデル・backend 不在・ファイル変更後のいずれでも検索が失敗しないこと
- 受入ケース:
  - 単独の検索モードとして選択できない（`--mode` の選択肢に加えない）。
  - 埋め込みの生成は索引時の明示的な要求（`cq index --embed`）に限る。
  - ベクトルは `.cq/vectors-<profile>.sqlite` に置き、`store.SCHEMA_VERSION` を変えない。
  - モデル名を記録し、異なるモデルのベクトルを使わない。
  - ベクトル生成後に変更されたファイルのベクトルを使わない。
  - 任意依存不在・ベクトル不在・モデル不一致・ファイル変更のいずれでも検索を失敗させない。
- 実測（golden 56 問 / top-k=5 / 同一プロセス・同一索引スナップショット、2026-08-15、モデル `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`）:

  | 群 | n | baseline | `--fuse` | `--semantic` |
  |---|---|---|---|---|
  | 全体 | 56 | 0.73 / 0.77 / 0.75 | 0.73 / 0.77 / 0.75 | **0.75 / 0.82 / 0.77** |
  | natural（日本語） | 10 | 0.00 / 0.00 / 0.00 | 0.00 / 0.00 / 0.00 | **0.10 / 0.20 / 0.13** |
  | natural（英語） | 10 | 0.50 / 0.70 / 0.57 | 0.50 / 0.70 / 0.57 | 0.50 / **0.80** / 0.60 |
  | symbol / substr / regex / trace | 36 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |

  値は top-1 / top-5 / MRR。**2026-08-04 の NO-GO 判定（日本語 natural 2/2 が密ベクトルでも圏外）を部分的に覆した**。差は埋め込み対象テキストで、前回は `name + signature + text[:512]`（コード本体）だったのに対し、今回は `name + signature + doc_head`（docstring、無ければ本文先頭）にした。本リポジトリの `doc_head` は hve profile で 6,273 件中 5,432 件（86.6%）が日本語で、日本語の問いと同一言語で照合できる経路ができる。
- コスト（同日実測）: ベクトル構築が hve 16,821 本 / 983.3 秒 / 33.82 MiB、app 1,552 本 / 75.1 秒 / 3.14 MiB。検索の median 応答が 159 ms → 589 ms（約 3.7 倍）。CLI は 1 プロセス 1 クエリなので毎回全ベクトルを読んで総当たりの cosine を取るため。
- **既定 OFF を維持した**。改善はあるがコストが 3.7 倍で、意味検索の候補が語彙層の正解を押し出す悪化も出る（natural 20 問で改善 5 件 / 悪化 2 件）。既定 OFF なら既存経路は 1 ms も遅くならず、退行リスクが構造的にゼロになる。
- 既知の制約: (1) 日本語 natural は 10 問中 2 問の到達にとどまり、「日本語の問い → 英語のコード」の橋渡しは大半が未解決のまま。(2) `--fuse` / `--semantic` を使うと `score` の意味が層固有のスコアから順位の逆数和へ変わる。(3) fastembed 0.8 はこのモデルで mean pooling を使う（警告が出る）ため、モデルや fastembed の版を変えると上表は再現しない。(4) 計測はローカル Windows のみ。
- 不採用（意図的）: LLM によるサブクエリ生成（`hve/repository_query*` の Agentic PoC が NO-GO 済みで、再実験には threshold の事前承認が必要。加えて同期 CLI のレイテンシ前提を壊す）、cross-encoder リランカ（追加モデルと数百 ms の推論を要し「任意依存ゼロで動く」前提を壊す。統合だけで足りるかを先に測る方針）、Azure AI Search 連携（ローカル完結の前提を壊し、`agentic-retrieval-contract` Skill の責務と重複する）、近似最近傍索引（16,821 件は総当たりで足り、問題になった実測が無い）。

- **返却単位 `symbol` を追加した（2026-08-15）**: 本文を返さず、ヒットを囲むシンボルの `qualname` / `kind` / `signature` を返す。`signature` に引数名が含まれるため「どこに何があるか」を知る用途はこれで足りる。
  - 対応テスト: [cq/tests/test_search_return_unit.py](cq/tests/test_search_return_unit.py) の `TestSymbolUnit` — CLI が選択肢を提供すること、本文を返さないこと、名前・種別・シグネチャが付くこと、囲むシンボルが無いヒットも位置情報だけ返すこと、順位が単位によって変わらないこと、`line` 単位よりトークンが少ないこと
  - 実測（golden 56 問 / top-3 / 既定経路）: 応答トークンの中央値が **159 → 110（比 0.69）**、名前の付いたヒットが **31/80 → 62/80**。
  - **`parser` と `chunk_id` は残す**。前者は FR-CQ-11 のフィデリティ通知、後者は `cq get` で本文を取得する導線であり、落とすと契約違反になる。両方を落とせば比 0.45 まで下がるが採らない。
  - 計画時の見積り（比 0.42）は `parser` / `chunk_id` / `route` / `score` を落とした形で試算していたため、実装値 0.69 と乖離した。**実装値が正しい**。
#### FR-CQ-12 — Skill 配線と mdq 品質の非退行
- 判定: ✓（Skill 配線、検索回帰再現、fail-closed A/B gate、最終非退行計測が GREEN）
- 対応テスト:
  - [hve/tests/test_code_query_skill_wiring.py](hve/tests/test_code_query_skill_wiring.py) — GREEN。SKILL.md の存在、frontmatter の USE FOR / PREFER OVER / DO NOT USE FOR / WHEN、`references/` の実在、最短呼び出し例が実 CLI 引数（`def` / `refs` は `--symbol`）と一致すること、ルーティング表への登録、`copilot-instructions.md` のソースコード検索既定手段の宣言、`markdown-query` との相互参照、`cq` が `.md` を索引しないこと、DB パスが `.cq/` に固定され `.mdq` と分離していること、`cq` ↔ `mdq` が相互に import しないこと
    - **独立性ガードの取りこぼしを修正した（2026-08-15）**: `cq` → `mdq` 側の検査だけが `"import mdq" in source` の部分文字列判定で、`from mdq import ...` を検出できなかった（`mdq` → `cq` 側は正規表現で全形式を見ており非対称だった）。両方向を `^[ \t]*(?:import|from)[ \t]+<package>\b` の正規表現へ揃え、`import mdq` / `import mdq.tokens` / `from mdq import tokens` / `from mdq.search import x` の 4 形式を parametrized テストで固定した。RED 2 failed → GREEN 21 passed。
  - [mdq/tests/test_search_tag_ranking.py](mdq/tests/test_search_tag_ranking.py) — GREEN。CQ inventory 行追加で圏外化した `INV-01` を最小再現し、query 内の exact machine-tag identifier が本文中の反復参照を上回ることを BM25 / FTS5 / grep で固定。generic / malformed tag、case、identifier 境界、underscore、同点時の決定的順序も検証
  - [hve/tests/test_mdq_vendor_sync.py](hve/tests/test_mdq_vendor_sync.py) — GREEN。ranking remediation を含む `mdq/search.py` を含め、配布対象の全ファイルについて upstream / vendor byte parity
  - `.github/scripts/validate-skill-routing.py` — 終了コード 0（ルーティング表の全参照が実在）
- 機械ゲート:
  - `validate_corpus_delta.py` — CQ-only inverse operation、生成行数、19 件の work Markdown allowlist を fail-closed 検証
  - `run_ab_measurement.py` — 隔離 snapshot、fresh DB、common engine/config/golden hash、入力実内容 freeze、反復 fingerprint、query-level regression、回帰時 exit 1 を検証
- 受入ケース:
  - Skill 定義がルーティング表へ登録される。→ ✓
  - `mdq` / `cq` の Skill 定義が相互に適用範囲を参照し、選択が一意に決まる。→ ✓（`mdq` の DO NOT USE FOR に「use code-query instead」、`cq` の Non-goals に「`markdown-query` を使う」）
  - `cq` 導入の前後で FR-MDQ-01 のゴールデンクエリ正解率が低下しない。→ ✓（20 queries、`auto`、k=5。baseline / candidate とも top-1 **0.45**、top-k **0.75**、query-level regressions **0**）
- 実測:

| profile | 手法 | top-1 | 平均トークン | 平均レイテンシ |
|---|---|---|---|---|
| hve | `grep` 対照群 | 9.5% | 1,285.8 | 9,634.8 ms |
| hve | 全文読み込み対照群 | 14.3% | 71,550.5 | 1,010.6 ms |
| hve | **`cq search`** | **95.2%** | **99.1** | **32.4 ms** |
| app | `grep` 対照群（範囲指定なし） | 0.0% | 809.4 | 2,861.2 ms |
| app | `grep` 対照群（`--paths "^src/"` を人手で付与） | 71.4% | 148.8 | 132.5 ms |
| app | **`cq search`** | **95.2%** | **73.5** | **12.0 ms** |

- 計測証跡（2026-07-29）: 生成した計測ログは `measurement_status=NON_REGRESSION_CONFIRMED`、CQ corpus 差分 25 paths、`allowed_but_equal_paths=[]`、baseline / candidate の 2 回反復 fingerprint 一致を記録している。正規 `mdq/golden_eval.py` と `mdq/golden-queries.json`（20 問、5 group）はランキング実行前に TDD で復旧し、全 anchor を fail-closed 検証した。初回計測で `INV-01` の top-k 回帰を検出したため、ゴールデンを変更せず exact machine-tag identifier の一般規則を追加し、同じ query set で解消した。

#### FR-CQ-13 — Chunk の再利用可能取得 API
- 判定: ✓（RED: 4 failed。GREEN: 4 passed。既存CQ検索回帰を含むfocused suite: 848 passed / 1 skipped）
- 対応テスト:
  - [cq/tests/test_search_get_chunk.py](cq/tests/test_search_get_chunk.py) :: `test_get_chunk_returns_exact_public_shape` / `test_get_chunk_returns_none_for_an_unknown_id` / `test_cli_get_delegates_to_shared_api_and_preserves_output` / `test_cli_get_preserves_unknown_id_error_contract` — `get_chunk` の5フィールド、`files.parser` JOIN、未知ID、CLI委譲、既存stdout/stderr/exit契約を検証
  - [cq/tests/test_search.py](cq/tests/test_search.py) :: `TestCli` — 既存search/def/get/stats経路の非退行
- 受入ケース:
  - `chunk_id` / `path` / `lines` / `text` / `parser` だけを返し、未知 ID では `None` を返す。
  - Python辞書の CLI 整形責任は `cq/cli.py`、custom tool の JSON 化責任は呼び出し側に置き、`cq get` の成功時標準出力と未知 ID のエラー契約を変更しない。

#### FR-CQ-14 — `cq` 利用ログ（`.cq/usage.jsonl`）
- 判定: ✓（RED: `cq.usage_log` 不在による collection error 1 件。GREEN: 9 passed。cq / Tool Search の focused suite: 962 passed）
- 対応テスト:
  - `hve/tests/test_cq_usage_log.py` :: `test_append_record_writes_jsonl` / `test_append_record_appends_multiple` — `.cq/usage.jsonl` へ 1 行 1 レコードで追記される
  - `hve/tests/test_cq_usage_log.py` :: `test_context_env_vars_captured` / `test_context_omitted_when_no_env_vars` — 実行文脈は設定済みの項目だけを含め、`null` で埋めない
  - `hve/tests/test_cq_usage_log.py` :: `test_append_record_swallows_write_errors` — 書き込み失敗を呼び出し元へ伝搬しない
  - `hve/tests/test_cq_usage_log.py` :: `test_cmd_stats_writes_usage_log` / `test_cmd_search_writes_usage_log` — CLI 経由でレコードが書かれる
  - `hve/tests/test_cq_usage_log.py` :: `test_failed_command_is_recorded_with_its_exit_code` — 失敗経路も終了コード付きで記録される
  - `hve/tests/test_cq_usage_log.py` :: `test_usage_log_path_is_separate_from_mdq` — `.mdq/usage.jsonl` と同一ファイルへ混在させない
- 受入ケース:
  - 保存先は `--repo-root` で解決した `<repo-root>/.cq/usage.jsonl` とし、`.mdq/usage.jsonl` と分離されている。
  - 長時間常駐する `watch` は記録対象外。自動テストは置かず、`cq/cli.py` の `watch` 分岐に記録呼び出しを配置しないことで担保する（`watch` はブロッキングのため CLI 経由テストが成立しない）。
  - 書き込み失敗時も CLI の終了コードと標準出力が変わらない。

#### FR-CQ-15 — 索引統計の言語別内訳
- 判定: ✓（RED: `KeyError: 'by_lang'` で 4 failed。GREEN: 9 passed。cq / GUI の focused suite: 115 passed）
- 対応テスト:
  - [cq/tests/test_index_stats.py](cq/tests/test_index_stats.py) :: `TestLanguageBreakdown::test_reports_a_language_breakdown` — GREEN。言語ごとにファイル数・シンボル数・チャンク数・パーサ別ファイル数を返す
  - [cq/tests/test_index_stats.py](cq/tests/test_index_stats.py) :: `TestLanguageBreakdown::test_separates_languages_that_share_a_parser` — GREEN。同一パーサを共有する複数言語が合算されず分離される
  - [cq/tests/test_index_stats.py](cq/tests/test_index_stats.py) :: `TestLanguageBreakdown::test_language_totals_match_the_overall_totals` — GREEN。言語別の合計が全体合計と一致し、集計が行を重複・欠落させていない
  - [cq/tests/test_index_stats.py](cq/tests/test_index_stats.py) :: `TestLanguageBreakdown::test_uses_the_indexed_language_without_reclassifying` — GREEN。統計側で言語を再判定せず `files.lang` をそのまま用いる
  - [cq/tests/test_index_stats.py](cq/tests/test_index_stats.py) :: `TestIndexStats::test_missing_index_raises_instead_of_reporting_zero` — GREEN（既存）。索引不在時に 0 件の内訳を返さない
  - [cq/tests/test_index_stats.py](cq/tests/test_index_stats.py) :: `TestCliDelegates::test_cli_output_equals_the_single_implementation` — GREEN（既存）。CLI 出力が単一実装の戻り値と一致する（FR-MAINT-07）
- 受入ケース:
  - 統計は集計対象テーブルごとの合計に加えて、言語別内訳を返す。→ ✓
  - 言語別内訳は言語ごとにファイル数・シンボル数・チャンク数と、パーサフィデリティ別のファイル数を保持する。→ ✓
  - 同一のパーサ名を共有する複数言語が、パーサ別集計では合算される一方で言語別内訳では分離される。→ ✓
  - 言語の値は索引が保持する値をそのまま用い、統計側で再判定・再分類しない。→ ✓
  - 索引が存在しない場合に 0 件の言語別内訳を返さない。→ ✓
  - 集計は `cq.store.index_stats` の単一実装であり、CLI 出力と一致する。→ ✓
- 実測（2026-08-06、本リポジトリの索引）: 集計時間は profile=hve で 82〜98 ms（files 866 / symbols 15,437 / chunks 14,792）、profile=app で 22〜31 ms。言語別合計と全体合計の一致を両 profile で確認。profile=app で `by_parser` が `regex=150` と 1 つに合算する 2 言語を、`by_lang` は csharp 74 / javascript 76 へ分離する。
- 既知の制約:
  - 本リポジトリに `.sql` ファイルが存在しないため、SQL は言語行としては表示されない。SQL 方言は索引に保存されないため、方言別の内訳は本要件の対象外。

### Repository Query Agentic Retrieval 計測 PoC（§3.9.1）

> **bootstrap 状態**: 以下は active 要件と予定テストだけを確定した状態であり、Sub-001時点では実装・RED / GREEN結果・network benchmarkは未実施だった。後続担当はcomposite golden（Sub-002）→ RED（Sub-003〜006）→ inventory照合（Sub-007）→ 実装（Sub-008〜012）→ local GREENとmapping / inventory確定（Sub-013〜014）の順とした。この段落はGolden証拠anchorを固定するための履歴であり、現在状態は次段落を正とする。

> **実装済み**: active要件 → mapping → RED → inventory照合 → 実装 →同一テストGREENの順を完了した。REDはSub-003〜006、実装はSub-008〜012、local GREENと通常検索非退行はSub-013で確認した。network benchmarkとGo/No-Go判定は後続Sub-015〜016であり、本節のlocal実装済み判定には含めない。

#### FR-RQ-01 — Measurement-only PoC の隔離
- 判定: ✓（RED: evaluator script不在でcollection error。GREEN: evaluator 43 passed。通常検索: CQ精度0.9524維持、MDQ 4slice基線delta=0）
- 対応テスト:
  - [hve/tests/test_repository_query_evaluation.py](hve/tests/test_repository_query_evaluation.py) :: `test_cli_rejects_missing_network_opt_in_before_writing_outputs` / `test_network_flag_is_required_before_any_runner_call` / `test_default_arm_a_uses_only_local_mdq_and_cq` / `test_runs_arms_in_rotated_order_with_comparable_conditions` — evaluator明示入口、network opt-in、Arm A local-only、runnerへのgolden label隔離を検証
  - [cq/tests/test_search.py](cq/tests/test_search.py) / [cq/tests/test_search_return_unit.py](cq/tests/test_search_return_unit.py) / [mdq/tests/test_search_return_unit.py](mdq/tests/test_search_return_unit.py) / [mdq/tests/test_search_budget.py](mdq/tests/test_search_budget.py) — evaluator非起動時の通常検索 invariant gate
- 受入ケース:
  - HVE 内 evaluator の明示実行時だけ起動し、通常検索、公開 CLI、canonical Skill、standalone kit、自動 routing を変更しない。
  - repository snippet の外部送信は明示 network benchmark に限定し、Go/No-Go レポート後も別承認なしに公開しない。
  - 既存 mdq / cq suites は evaluator 非起動時の invariant gate、新規 evaluator test は明示起動時の隔離契約として役割を分離する。

#### FR-RQ-02 — Custom-only read-only tools と Evidence Ledger
- 判定: ✓（RED: runtime module不在でcollection error。GREEN: 42 passed / 1 symlink-permission skip）
- 対応テスト:
  - [hve/tests/test_repository_query_tools.py](hve/tests/test_repository_query_tools.py) :: `TestEvidenceLedger` / `TestSearchTools` / `TestOpenEvidence` / `TestReferencesAndLimits` — exact 4 tools、SDK `skip_permission`、query-scoped ledger、root/symlink confinement、query/hit/token/ref/global tool cap、backend fail-closedを検証
- 受入ケース:
  - 4 custom tools だけを公開し、`open_evidence` は current ledger ref だけを取得する。
  - 既存 mdq / cq search、FR-CQ-13、FR-CQ-07 を再実装せず委譲する。
  - query-scoped ledger は `(source, chunk_id)` で重複排除し、初回登録順の ID を再利用する。search / open / refs の入力件数・hit・Token 上限を強制する。
  - 任意 read、write、shell、web、MCP、memory、git 操作を拒否する。

#### FR-RQ-03 — Grounding JSON と host-side evidence validation
- 判定: ✓（RED: runtime module不在でcollection error。GREEN: runtime 41 passed）
- 対応テスト:
  - [hve/tests/test_repository_query.py](hve/tests/test_repository_query.py) :: `test_aggregates_usage_and_host_owned_evidence` / `test_invalid_model_output_fails_without_a_repair_call` / `test_insufficient_evidence_can_abstain_without_citations` / `test_partial_answer_requires_evidence_and_unresolved_items` / `test_invalid_ledger_rows_fail_closed` — exact schema、status/unresolved関係、citation順・重複・未知ID、ledger検証、invalid JSONのno-repair fail-closedを検証
- 受入ケース:
  - Model は 4 フィールドの Grounding JSON だけを返し、path / lines / snippet / usage / limits は host が付加する。
  - `unresolved` は `list[str]` とし、answered では空、partial / insufficient_evidence では非空とする。
  - `evidence_ids` は最初の引用順を保つ一意な ID 列とし、host result は `schema_version: 1` を持つ。
  - invalid JSON と未知 evidence ID を修復 LLM へ再送しない。

#### FR-RQ-04 — A/C/D 比較と機械計測
- 判定: ✓（RED: evaluator script不在、および敵対的レビュー追加契約のcollection error / preparation例外漏洩。GREEN: evaluator 43 passed）
- 対応テスト:
  - [hve/tests/test_repository_query_evaluation.py](hve/tests/test_repository_query_evaluation.py) :: `test_loads_the_real_composite_golden` / `test_golden_validation_is_fail_closed` / `test_default_arm_a_uses_only_local_mdq_and_cq` / `test_arm_c_requires_exactly_one_llm_call_and_no_tools` / `test_runs_arms_in_rotated_order_with_comparable_conditions` / `test_repeat_two_keeps_every_run_and_rotates_the_starting_arm` / `test_runner_failures_are_measured_not_dropped` / `test_abstention_accuracy_is_calculated_across_all_unanswerable_queries` / `test_cap_abort_is_counted_and_sanitized` — Golden fail-closed、Arm Aの毎回実検索、default runner＋evaluator統合でのArm C frozen evidence計測外準備と準備失敗時のC error/A・D継続、exactly-one/no-tool、D bounded tools、rotation/repeat、query/category/overall品質・usage・error/cap・Arm別provenance、no GO/judgeを検証
- 受入ケース:
  - golden query ごとに、Arm A は local-only / no-LLM、Arm C は当該 query の A evidence を exactly one-shot / no-tool、Arm D は 4 tool の bounded session とし、query 間を batch call にまとめない。
  - query / category / overall の品質・call・Token・duration・failure と構造化 provenance を分離集計し、失敗・abort も分母へ含める。
  - LLM judge と自動 Go/No-Go 判定を実装せず、数値閾値は baseline 後に別承認する。

#### NFR-RQ-01 — Bounded execution と情報非保存
- 判定: ✓（RED: runtime module不在、SDK capability追加契約、およびAuto入力拒否契約の失敗。GREEN: runtime/tools 83 passed / 1 symlink-permission skip）
- 対応テスト:
  - [hve/tests/test_repository_query.py](hve/tests/test_repository_query.py) :: `test_creates_a_custom_only_fail_closed_session` / `test_eleventh_usage_event_aborts_and_fails_closed` / `test_abort_failure_does_not_mask_the_limit_error` / `test_cleanup_runs_when_send_fails` / `test_cleanup_failures_do_not_mask_an_output_error` / `test_invalid_limits_fail_before_client_creation` / `test_missing_sdk_ai_credit_capability_fails_before_client_creation` / `test_raw_prompt_and_model_output_are_not_logged` — Copilot SDK 1.0.6 `SessionLimitsConfig.max_ai_credits`のclient作成前capability検証、model/effortの空白・大小文字を正規化したAuto拒否、fixed inputs、custom-only allowlist+builtin/MCP denylist、全cap、abort、usage、sanitized SDK/cleanup error、raw content非ログを検証
  - [hve/tests/test_repository_query_tools.py](hve/tests/test_repository_query_tools.py) :: `TestSearchTools` / `TestOpenEvidence` / `TestReferencesAndLimits` — tool側のquery/hit/token/open/ref/global call capとledger非汚染を検証
- 受入ケース:
  - fixed model / effort / max AI credits / timeout を必須化し、Copilot CLI 1.0.77 の最小受理値 30 未満の AI credits と定義済み cap 超過を実行前に拒否または abort する。
  - cap 超過は構造化 error に記録し、初期 cap を受入閾値として扱わない。
  - raw prompt / reasoning は永続化せず、snippet は明示 result artifact だけに限定し、authentication data を保存しない。SDK / pydantic の依存を追加しない。

### Skill 配布キットの可搬性（§3.10）

> 本節の 5 件は事前に策定した実装計画に基づき実装された。

#### FR-KIT-01 — 配布キットのエンジン同梱と正本一致
- 判定: ✓（RED：`vendor/cq` が `.gitignore` 対象で 15 欠落 + 10 内容不一致の 29 failed。GREEN：45 passed）
- 対応テスト:
  - [hve/tests/test_cq_vendor_sync.py](hve/tests/test_cq_vendor_sync.py) — GREEN。`cq` の upstream / vendor byte parity、余剰ファイル検出、任意階層 `tests` の非同梱、`git check-ignore` で非 ignore であること、`git ls-files` で追跡済みであること、時刻入り `UPSTREAM.txt` を生成しないこと
  - [hve/tests/test_mdq_vendor_sync.py](hve/tests/test_mdq_vendor_sync.py) — GREEN。同等の byte parity。除外規則を任意階層の `tests` へ拡張し、`mdq/gui/tests` の非同梱を検証
- 受入ケース:
  - 両キットの同梱物が `git ls-files` で追跡されている。→ ✓（cq 38 ファイル / mdq 33 ファイル）
  - 正本と同梱物のファイル集合および内容が一致する。→ ✓
  - 任意階層の `tests` ディレクトリが同梱物へ混入しない。→ ✓

#### FR-KIT-02 — Skill 定義の単一正本化
- 判定: ✓（RED：`skill/` 不在と `skill-template` 二重管理で 10 failed。GREEN：13 passed）
- 対応テスト:
  - [hve/tests/test_skill_bundle_sync.py](hve/tests/test_skill_bundle_sync.py) — GREEN。両 Skill の正本と配布コピーの byte 一致、余剰ファイル不在、`references/repo-specific/` 非同梱、正本側にリポジトリ固有付録が隔離されていること、`skill-template` の削除、Skill 配置判断が共有実装 1 箇所にあること
  - [hve/tests/test_code_query_skill_wiring.py](hve/tests/test_code_query_skill_wiring.py) — GREEN。汎用化後も frontmatter マーカー、参照資料の実在、`def` / `refs` の `--symbol` 引数、掲載識別子の実在が保たれること
- 受入ケース:
  - `SKILL.md` の編集箇所が `.github/skills/<name>/` の 1 つだけになる。→ ✓
  - 配布コピーが正本と一致する。→ ✓（cq 3 ファイル / mdq 9 ファイル）
  - `markdown-query` にも Skill 定義の配布経路が存在する。→ ✓
- 既知の制約:
  - `references/cli-reference.md` にはリポジトリ固有の呼び出し例が残る。`test_code_query_skill_wiring.py::test_documented_symbols_actually_exist` が捧造防止のために実在識別子の掲載を要求しており、完全な汎用化と両立しない。契約変更を伴うため本件では未解消。

#### FR-KIT-03 — セットアップ・同期判断ロジックの単一化
- 判定: ✓（GREEN：10 passed）
- 対応テスト:
  - [hve/tests/test_kit_bundle_sync.py](hve/tests/test_kit_bundle_sync.py) — GREEN。`tools/skills/_kit/` の存在、`kit.toml` の必須キー宣言、各キット `kit/` との byte 一致と余剰不在、OS 別スクリプトが `pip install` / `-m venv` / `.github/skills` / `golden-queries.json` の判断を持たないこと
  - [hve/gui/tests/test_cq_standalone_gui.py](hve/gui/tests/test_cq_standalone_gui.py) — GREEN。除外規約の正本が `tools/skills/_kit/kit_sync.py` であり、fixture と一致すること
- 受入ケース:
  - OS 別スクリプトに依存解決・パス決定・設定生成・Skill 配置の分岐が残らない。→ ✓
  - 両キットが同一のセットアップ実装を共有する。→ ✓（`kit_setup.py` / `kit_sync.py`）

#### FR-KIT-04 — コピー後の可搬性
- 判定: ✓（GREEN：8 passed。実装前は `python tools/skills/code_query/launch.py --version` が exit 2）
- 対応テスト:
  - [hve/tests/test_portable_kit_e2e.py](hve/tests/test_portable_kit_e2e.py) — GREEN。8 件（2 キット × 4 観点）。**版管理下の実配布物**を一時 git リポジトリへ `copytree` し、`PYTHONPATH` から上流を外した subprocess で setup / 設定生成 / Skill 配置 / 索引 / 検索 / GUI 起動導線 / 同梱エンジンの解決先を検証。**2026-08-05 に `CQ_PROFILE=main` の注入を削除**し、上流固有 profile 名を与えずに検索が成立することを検証対象へ含めた
  - [cq/tests/test_config.py](cq/tests/test_config.py) :: `TestDefaultProfile` — GREEN。5 件。宣言された profile が 1 つだけならそれを既定にすること、複数宣言時は推測せず上流 fallback のままであること、設定不在時の fallback、環境変数の優先、明示 `--profile` を上書きしないこと
  - [hve/tests/test_markdown_query_kit_contract.py](hve/tests/test_markdown_query_kit_contract.py) — GREEN。ランチャの vendored エンジン参照、fail-closed 分岐、パッケージ宣言、CLI ランチャと設定生成の存在
- 受入ケース（契約文書 §4 P1〜P7）:
  - P1 上流非依存で CLI が動く / P2 エンジン実体が同梱（解決された `__file__` が vendor 配下）/ P3 Skill 定義が配置され同梱コピーと byte 一致 / P4 設定ファイルが生成 / P5 GUI 起動導線 / P6 `hve` を import しない / P7 OS 別ランチャ 8 種の同梱。→ すべて ✓
  - 上流固有の名前を手動で与えなくても成立する。→ ✓（2026-08-05 追加。`cq` の profile 既定は `cq.toml` の宣言が 1 つのときそれを採る）
- 既知の制約:
  - E2E は `--no-venv` で実行するため、venv 作成と `pip install` の経路は未検証（ネットワークと実行時間への依存を避ける意図的な限定）。
  - GUI 任意依存未導入時の fail-closed 経路は静的検査のみ（実行環境を壊さずに再現できないため）。

#### FR-KIT-05 — 配布物からの上流依存禁止
- 判定: ✓（RED：実行時 `sys.modules` に `hve*` が 21 モジュール。GREEN：`[]`）
- 対応テスト:
  - [hve/tests/test_distributed_tree_has_no_upstream_dependency.py](hve/tests/test_distributed_tree_has_no_upstream_dependency.py) — GREEN。配布対象 7 ツリーの AST 静的検査と、別プロセスで `mdq.usage_stats.aggregate_usage_stats()` を実行した後の `sys.modules` 検査
  - [hve/tests/test_mdq_gui_single_implementation.py](hve/tests/test_mdq_gui_single_implementation.py) — GREEN。共有 GUI に `hve` import がないこと、設定ストアに実行時の上流探索がないこと
- 受入ケース:
  - 配布対象に `hve` への import が存在しない。→ ✓（`mdq/usage_stats.py` の `from hve import run_journal` を除去し、読み取りを `mdq.usage_log.read_records` へ単一化。`hve.run_journal` は委譲）
  - 上流パッケージの有無を実行時に判定して分岐する経路が存在しない。→ ✓（`_try_hve_settings_store()` を除去し、`SettingsBackend` 注入へ置換）

#### FR-KIT-06 — 配布同期の宣言単一化と版管理
- 判定: ✓（GREEN：57 passed）
- RED / GREEN 証跡（正確に記録する）:
  - **RED を確認した受入ケース1**: 「利用者が編集する前提のファイルを改変検出の対象外とする」。テスト追加時点の実装は `preserve` 対象（`tool-search` の `policy.json`）を改変として報告し、`test_preserved_files_are_not_reported_as_drift` が FAIL した。マニフェストへ `preserved` を追加して GREEN。
  - **RED を確認した受入ケース2**: 「上流パッケージへ依存しない」（FR-KIT-05 との連携）。配布先を cwd として `python -m toolsearch eval` を実行し、`ModuleNotFoundError: No module named 'mdq.search'` を実測した。`toolsearch/ranking.py` の既定 BM25 実装が `mdq.search._MiniBM25` であり、`mdq/tokenize.py` しか同梱していなかった。`mdq/search.py` を同梱対象へ追加して GREEN。
    - **偽 green の原因**: 当初の可搬性テストは `cwd=上流リポジトリ` で subprocess を起動しており、`-m` 実行で cwd が `sys.path` へ入るため `mdq` が上流側へ解決されていた。テストの cwd を配布先へ固定し、遅延 import を静的に拾って同梱漏れを検出する回帰テストを追加した。
  - **RED を確認した受入ケース3（実 Linux）**: Ubuntu 24.04 / WSL2 で 3 パッケージとも `subprocess.CalledProcessError: ... '-m', 'venv' ... returned non-zero exit status 1` で導入不能だった。`install.sh` が Python インタプリタの有無しか見ておらず、Debian 系の `python3-venv`（ensurepip）不在を検知できていなかった。ensurepip の個別確認と自動導入を入れて GREEN。
  - **RED を確認した受入ケース4（素の Windows）**: Windows Sandbox（pwsh / python / py / git / winget / choco が一つも無い素の Windows 11 + PowerShell 5.1）で `install.ps1` が **実行前に構文エラー**となった。5.1 は `.ps1` を ANSI として読むため、UTF-8（BOM 無し）の非 ASCII を含むスクリプトはパースできない。配布される `.ps1` を ASCII のみへ揃えて GREEN（全 `.ps1` が 5.1 で parse-errors=0、パッケージマネージャ不在を検知して exit 3）。同じ欠陥が `tools/skills/*/{setup,sync-vendor,mdq,cq}.ps1` にもあったため併せて修正した。
  - **RED を確認していない受入ケース**: 上記以外。配布機構の実装が先行し、本要件はその契約を事後に規定したものであるため、RED 証跡は存在しない。**bugfix / maintenance ではなく feature の追加であり、TDD 順序を満たしていない**。この逸脱は意図的に記録するものであり、以後の FR-KIT-06 改訂では RED を先行させる。
- 対応テスト:
  - [hve/tests/test_for_other_repo_sync.py](hve/tests/test_for_other_repo_sync.py) — GREEN。48 件。`copy_to_repo.py` が**実際に生成した成果物**を対象に、宣言の健全性（必須キー・参照先実在・エンジン実体を宣言側へ複製していないこと）、配布物へのビルド生成物混入なし、リポジトリ固有データの除外、ドキュメントと画像の同梱、版マニフェストの記録内容、版判定 4 値、同版・降格の既定拒否と `--force`、`preserve` の温存と改変検出除外、旧配布ファイルの削除、配布外ファイル（venv）の生存、コピー先単独での `--version` / `--verify`、**配布先を cwd とした** `python -m toolsearch` の `policy` / `skills` / `eval`、配布エンジンに `hve` import が無いこと、**配布エンジンが参照する `mdq.*` モジュールがすべて同梱されていること**、`kit.toml` の必須キーを検証
- 受入ケース:
  - 宣言が単一の出所であり、同期スクリプトが収集対象を再宣言しない。→ ✓
  - エンジン実体・Skill 定義・共通セットアップ実装を宣言側へ複製しない。→ ✓（`tools/for-other-repo/<package>/vendor/` が存在しないことを検証）
  - 版マニフェストが配布版・エンジン版・上流 commit・同期時刻・全ファイルのハッシュを記録する。→ ✓
  - 同版・降格は既定で拒否し、明示指定でのみ上書きする。→ ✓
  - 旧配布ファイルを削除し、配布物以外を削除しない。→ ✓
  - 利用者が編集する前提のファイルを温存し、改変検出の対象外とする。→ ✓（唯一の RED → GREEN）
  - コピー先だけで版と改変・欠落を確認できる。→ ✓（`install.py --version` / `--verify`）
  - 上流 extras 相当の任意依存を同期宣言から導入できる。→ ✓（`install-extras.json`）
- 実測（2026-08-05）: 配布ファイル数は markdown-query 81 / code-query 72 / tool-search 29。**3 つの実環境**で導入を確認した: (1) Windows 11 / Python 3.14 — 3 パッケージとも exit 0、`mdq` 39 ファイル 402 chunk、`cq` 32 ファイル 0 errors（`.ps1` は tree-sitter）。(2) Ubuntu 24.04 / Python 3.12（WSL2）— 3 パッケージとも exit 0、`CQ_PROFILE` 未設定で検索成立。(3) Windows Sandbox（前提ソフトウェアゼロ + PowerShell 5.1）— 全 `.ps1` が parse-errors=0、パッケージマネージャ不在を検知して exit 3 と導入先 URL。配布先を cwd とした `toolsearch eval` は 73 entries / 42 queries で recall@5 0.869 / MRR 0.807 / トークン削減 91.3%。
- 既知の制約:
  - macOS の Homebrew 経路は実機が無く未検証（分岐ロジックのみ stub で確認）。
  - winget が存在しない素の Windows では fail-closed とし、App Installer の自動導入は行わない。
  - 配布キットの GUI 起動導線（`launch-gui.*`）は本要件の検証対象に含めていない（FR-KIT-04 側で確認）。

### §3.11 実行時 Observability と Dashboard（FR-RTO / NFR-RTO）

#### FR-RTO-01 — 観測イベント契約の単一実装と後方互換
- 判定: ✓（RED: `ImportError: cannot import name 'runtime_observability'` → GREEN: 22 passed）
- 直接対応テスト:
  - [hve/tests/test_runtime_observability.py](hve/tests/test_runtime_observability.py) :: `TestEnvelope` — `schema_version` / `ts`(UTC ISO8601) / `seq` / `pid` / `run_id` / `workflow_id` / `instance_id` の付与、既存 `kind` / `step` の保持、`step` 未指定時の空文字維持
  - [hve/tests/test_runtime_observability.py](hve/tests/test_runtime_observability.py) :: `TestInstanceId` — `workflow_id` / `workflow_id#app_id` の命名規約
  - （v2.42 追加）[hve/tests/test_runtime_observability.py](hve/tests/test_runtime_observability.py) :: `TestInstanceScope` — `instance_id` がプロセス単位であり、プロセス内 Step fan-out（`2/APP-001` 等）で切り替わらず `step` で分離されること、および run 合算の Context が単一プロセス実行で保持されること。本改訂は文言確定であり実装挙動を変えないため、導入時点で GREEN（RED なし。`test_runtime_observability.py` 32 passed）。システムテストが期待した `aas#APP-nnn` への分離は、本要件の確定文言により非採用とした
  - [hve/tests/test_runtime_observability.py](hve/tests/test_runtime_observability.py) :: `TestWireFormat` — `[hve:stats]` 行形式の維持、legacy 行とタイムスタンプ付き行の解析
  - [hve/tests/test_runtime_observability.py](hve/tests/test_runtime_observability.py) :: `TestReducerUnknownKind` — 未知 kind を破棄せず件数計上
  - [hve/gui/tests/test_runtime_dashboard_state.py](hve/gui/tests/test_runtime_dashboard_state.py) :: `TestParserUsesCoreImplementation` — GUI の解析が core 実装へ単一化されていること（FR-MAINT-07）

#### FR-RTO-02 — 収集 / 保存 / 子配信 / 表示の分離
- 判定: ✓（RED: 10 failed → GREEN: 12 passed）
- 直接対応テスト:
  - [hve/tests/test_console_runtime_observability.py](hve/tests/test_console_runtime_observability.py) :: `TestChildDelivery` — 通常 CLI で stdout へ出さず、GUI 子（`HVE_GUI_SESSION_ID`）と明示子（`HVE_STATS_STREAM`）でのみ配信
  - [hve/tests/test_console_runtime_observability.py](hve/tests/test_console_runtime_observability.py) :: `TestWorkbenchBodyIsolation` — CUI Workbench 本文への非混入
  - [hve/tests/test_console_runtime_observability.py](hve/tests/test_console_runtime_observability.py) :: `TestCollectionAlwaysOn` — `quiet` / `final_only` でも収集継続（step ライフサイクル / skill を含む）
  - [hve/tests/test_orchestrator_runtime_dashboard.py](hve/tests/test_orchestrator_runtime_dashboard.py) :: `TestStatusLineDecision`、`TestFinalSummary` — 表示抑止条件と非 TTY 時の 1 回限りサマリー
  - [hve/tests/test_autopilot_cli_observability.py](hve/tests/test_autopilot_cli_observability.py) :: `TestChildEnvironment` — CLI Autopilot 親が子へ配信マーカーを付与
- 契約変更に伴う既存テスト更新:
  - [hve/tests/test_console.py](hve/tests/test_console.py) :: `TestFileIO::test_emits_stats_event_file_io` — 「常時 stdout へ出力」から「子プロセス実行時のみ配信」へ改訂

#### FR-RTO-03 — run-scoped JSONL 永続化
- 判定: ✓（RED: 16 failed → GREEN: 18 passed）
- 直接対応テスト:
  - [hve/tests/test_runtime_observability_store.py](hve/tests/test_runtime_observability_store.py) :: `TestOutputLocation` — `observability/events-<pid>.jsonl`、`HVE_WORK_ROOT` 未設定・dry-run での無効化
  - [hve/tests/test_runtime_observability_store.py](hve/tests/test_runtime_observability_store.py) :: `TestFileFormat` — UTF-8 / LF / BOM なし / 1 行 1 JSON、壊れた行の skip
  - [hve/tests/test_runtime_observability_store.py](hve/tests/test_runtime_observability_store.py) :: `TestConcurrency` — 4 スレッド 200 行の追記で行破損なし
  - [hve/tests/test_runtime_observability_store.py](hve/tests/test_runtime_observability_store.py) :: `TestSizeCap` — 上限到達で停止し警告は 1 回
  - [hve/tests/test_orchestrator_runtime_observability.py](hve/tests/test_orchestrator_runtime_observability.py) :: `TestAttachRuntimeObservability` — 生成条件と identity 付与

#### FR-RTO-04 — 保存 allowlist と秘密情報の非永続化
- 判定: ✓（RED: 2 failed（相対パス正規化）→ GREEN）
- 直接対応テスト:
  - [hve/tests/test_runtime_observability_store.py](hve/tests/test_runtime_observability_store.py) :: `TestSanitization` — 禁止キーの除去、診断 kind の非保存、リポジトリ相対化、リポジトリ外パスと相対トラバーサルの破棄
  - （v2.42 追加・実装済み）[hve/tests/test_runtime_observability_store.py](hve/tests/test_runtime_observability_store.py) :: `TestSanitization::test_shell_expression_tokens_are_dropped` — シェルの変数・式トークン・末尾コード断片（`$p` / `` `$p)) `` / `$p))` / `...md')`）を `path` として保存しないこと（RED: 4 params 失敗 → GREEN）
  - （v2.42 追加・実装済み）[hve/tests/test_runner_file_tracking.py](hve/tests/test_runner_file_tracking.py) :: `TestTrackPowershellFiles::test_variable_and_expression_tokens_not_captured_as_path` / `test_quoted_literal_path_is_still_captured` — 同等のトークンを `track_file` / `file_io` へ発火せず、引用付きの実パスは従来どおり追跡すること（RED: 1 件失敗 → GREEN。実装後は 3 ファイル 72 passed）
  - [hve/tests/test_runtime_observability_parity.py](hve/tests/test_runtime_observability_parity.py) :: `TestSecurityAcrossSurfaces` — Console 経由でも秘密情報が JSONL に出ない

#### FR-RTO-05 — 実行面横断で同一の集計値
- 判定: ✓（RED: registry 5 failed / GUI 7 failed / CUI 5 failed → GREEN）
- 直接対応テスト:
  - [hve/tests/test_runtime_observability_parity.py](hve/tests/test_runtime_observability_parity.py) :: `TestSurfaceParity` — CLI / CUI / GUI / GUI child / CLI Autopilot が同一イベント列で同一集計
  - [hve/tests/test_runtime_observability_registry.py](hve/tests/test_runtime_observability_registry.py) :: `TestRegistryInstanceIsolation`、`TestReducerAggregation` — instance 分離と run 合算、集計の受入ケース
  - [hve/tests/test_workbench_observability.py](hve/tests/test_workbench_observability.py) :: `TestFooterRendering`、`TestStatsCommand` — CUI Footer と `/stats`、未取得値の `-`
  - [hve/gui/tests/test_runtime_dashboard_state.py](hve/gui/tests/test_runtime_dashboard_state.py) :: `TestInstanceScopedMetrics`、`TestLogPipelineFeedsRegistry` — GUI の instance 別集計と既存集計の併存
  - [hve/gui/tests/test_workbench_window_observability.py](hve/gui/tests/test_workbench_window_observability.py) :: `TestRuntimeMetricsIntake` — `--autopilot-child` 互換ウィンドウの取り込みと表示
  - [hve/tests/test_autopilot_cli_observability.py](hve/tests/test_autopilot_cli_observability.py) :: `TestChildLineConsumption`、`TestSummary` — CLI Autopilot の instance 別集約と再出力

#### FR-RTO-06 — 記録ライフサイクルとクリーンアップ非干渉
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_runtime_observability_store.py](hve/tests/test_runtime_observability_store.py) :: `TestFailureIsolation` — クローズの冪等性、context manager 終了後にハンドルを保持しないこと
  - [hve/tests/test_orchestrator_runtime_observability.py](hve/tests/test_orchestrator_runtime_observability.py) :: `TestLifecycleWiring` — `run_workflow` が記録器を生成し終了時に閉じる配線

#### FR-RTO-07 — 実行履歴の Step 単位分離
- 判定: ✓（RED: 46 failed / 88 passed → GREEN: 対象 5 ファイル 110 passed。改訂 2.19 の Fleet worker 帰属は RED: 10 failed → GREEN: 58 passed）
- 直接対応テスト:
  - [hve/gui/tests/test_stats_history_state.py](hve/gui/tests/test_stats_history_state.py) :: `test_step_snapshot_uses_per_step_context` — Step スナップショットの Context が当該 Step 帰属イベントの値であり、他 Step 完了後もグローバル現在値で上書きされないこと
  - [hve/gui/tests/test_stats_history_state.py](hve/gui/tests/test_stats_history_state.py) :: `test_step_snapshot_context_ignores_global_current_value` — グローバル現在値（`set_context`）を Step の Context へ代用しないこと
  - [hve/gui/tests/test_stats_history_state.py](hve/gui/tests/test_stats_history_state.py) :: `test_step_snapshot_uses_per_step_credit` — Step スナップショットの AI Credit が当該 Step 帰属の `usage_credit` 合計であり、Workflow 累積値ではないこと
  - [hve/gui/tests/test_stats_history_state.py](hve/gui/tests/test_stats_history_state.py) :: `test_step_credit_dedupes_by_api_call_id` — 同一 `api_call_id` の再送を Step 別集計でも二重計上しないこと
  - [hve/gui/tests/test_stats_history_state.py](hve/gui/tests/test_stats_history_state.py) :: `test_step_snapshot_records_per_step_model_counts` — Step スナップショットがモデル別呼び出し回数を保持すること
  - [hve/gui/tests/test_stats_history_state.py](hve/gui/tests/test_stats_history_state.py) :: `test_step_snapshot_is_none_when_no_step_event` — Step 帰属イベントが 0 件の Step で Context / AI Credit / モデルが未取得（`None` / 空）となること
  - [hve/gui/tests/test_stats_history_state.py](hve/gui/tests/test_stats_history_state.py) :: `test_workflow_credit_keeps_unattributed_total` — Step へ帰属できない消費も Workflow 累積へ計上されること
  - [hve/gui/tests/test_stats_history_state.py](hve/gui/tests/test_stats_history_state.py) :: `test_placeholder_run_id_snapshot_is_updated_in_place` — `run_id` 未確定で開始した実行が確定後も 1 件のスナップショットに留まること
  - [hve/gui/tests/test_stats_history_state.py](hve/gui/tests/test_stats_history_state.py) :: `test_real_run_id_change_still_appends_snapshot` — プレースホルダでない `run_id` の変更は従来どおり別実行として追加すること（回帰ガード）
  - [hve/gui/tests/test_stats_history_view.py](hve/gui/tests/test_stats_history_view.py) :: `test_step_row_shows_own_aiu` — Step 行の AI Credit 列が Step 実測値を表示し、隣接 Step の累積差分を用いないこと
  - [hve/gui/tests/test_stats_history_view.py](hve/gui/tests/test_stats_history_view.py) :: `test_step_row_shows_dash_when_own_aiu_unknown` — Step 実測値が無い場合に `-` を表示すること
  - [hve/gui/tests/test_stats_history_view.py](hve/gui/tests/test_stats_history_view.py) :: `test_step_row_shows_model_counts` — Step 行のモデル列がモデル別呼び出し回数を表示すること
  - [hve/gui/tests/test_stats_history_view.py](hve/gui/tests/test_stats_history_view.py) :: `test_step_row_model_shows_dash_when_unknown` — モデル帰属イベントが無い Step でグローバルのモデル名を代用せず `-` を表示すること
  - [hve/gui/tests/test_stats_history_view.py](hve/gui/tests/test_stats_history_view.py) :: `test_workflow_row_aggregates_model_counts` — Workflow 親行のモデル列が子 Step の合計であること
  - [hve/gui/tests/test_stats_history_view.py](hve/gui/tests/test_stats_history_view.py) :: `test_view_dclick_opens_popup_for_model_column` — Top-N 表記のモデル列を D-click で全件表示できること
  - [hve/gui/tests/test_stats_history_view.py](hve/gui/tests/test_stats_history_view.py) :: `test_build_csv_has_aiu_own_column` — CSV が `AiuOwn` 列を持ち `AiuDeltaSincePrev` を持たないこと
  - [hve/gui/tests/test_stats_per_step_attribution.py](hve/gui/tests/test_stats_per_step_attribution.py) :: `test_session_usage_detail_records_step_context` — `session_usage_detail` の `step` で Context が Step 別に記録されること
  - [hve/gui/tests/test_stats_per_step_attribution.py](hve/gui/tests/test_stats_per_step_attribution.py) :: `test_session_usage_detail_keeps_latest_value_per_step` — 同一 Step の再送で最新値へ更新されること
  - [hve/gui/tests/test_stats_per_step_attribution.py](hve/gui/tests/test_stats_per_step_attribution.py) :: `test_usage_credit_records_step_credit` — `usage_credit` の `step` で AI Credit が Step 別に記録されること
  - [hve/gui/tests/test_stats_per_step_attribution.py](hve/gui/tests/test_stats_per_step_attribution.py) :: `test_usage_credit_dedupe_is_shared_with_step_bucket` — 重複排除が Step 別バケットにも適用されること
  - [hve/gui/tests/test_stats_per_step_attribution.py](hve/gui/tests/test_stats_per_step_attribution.py) :: `test_step_less_events_do_not_attribute_to_running_step` — `step` が空のイベントを実行中 Step へ誤帰属させず、Workflow 累積へは計上すること
  - [hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py) :: `test_collector_emits_usage_credit_from_assistant_usage` — Fleet セッションの `assistant.usage` から `usage_credit` を発火すること
  - [hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py) :: `test_collector_usage_credit_uses_empty_step_id` — Step を解決できない Fleet worker の `usage_credit` が `step_id=""` であり Wave 内 Step へ割り当てられないこと
  - [hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py) :: `test_collector_does_not_emit_tool_invoked_for_unresolved_worker` — Step を解決できない Fleet worker の tool を誤帰属させないこと
  - [hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py) :: `test_collector_usage_credit_reports_unavailable_reason` — `copilotUsage` 欠落時に取得不能理由を併送すること
  - [hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py) :: `test_collector_usage_credit_without_console_is_noop` — console 未配線時に作業イベントを無視すること（後方互換）
  - [hve/tests/test_runtime_observability.py](hve/tests/test_runtime_observability.py) :: `TestUsageCreditExtraction` — `extract_usage_credit_fields` が `copilotUsage.totalNanoAiu` / `apiCallId` / `cost` を抽出し、`copilotUsage` 欠落時に `unavailable_reason` を返し、本文系フィールドを返さないこと（FR-MAINT-07 / FR-RTO-04）
- Fleet worker → Step 帰属（改訂 2.19、RED: 10 failed → GREEN: 58 passed）:
  - [hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py) :: `test_collector_resolves_step_from_subagent_spawn_arguments` — sub-agent 起動 tool の引数から Wave の Step を一意に解決し、worker の `usage_credit` を当該 Step へ帰属させること
  - [hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py) :: `test_collector_emits_tool_invoked_for_resolved_worker` — 解決済み worker の `tool.execution_start` を `tool_invoked` として当該 Step へ帰属させること
  - [hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py) :: `test_collector_does_not_attribute_when_multiple_steps_match` — 引数が複数の Step に一致する場合はいずれへも割り当てないこと
  - [hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py) :: `test_collector_does_not_attribute_when_no_step_matches` — 一致が 0 件の場合はいずれへも割り当てないこと
  - [hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py) :: `test_collector_step_match_requires_boundary` — `Step.2` が `Step.2/APP-001` へ誤一致しないこと
  - [hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py) :: `test_collector_does_not_persist_tool_arguments` — 解決に用いた tool 引数を観測イベントへ含めないこと（FR-RTO-04）
  - [hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py) :: `test_collector_resolves_step_when_spawn_arrives_after_subagent_started` — 起動 tool と `subagent.started` の到着順が逆でも解決できること
  - [hve/tests/test_orchestrator_fanout_repo_root.py](hve/tests/test_orchestrator_fanout_repo_root.py) :: `test_fleet_collector_receives_wave_step_ids` — `_build_fleet_wave_runner` が Wave の Step 集合を `FleetEventCollector` へ注入すること
  - [hve/gui/tests/test_stats_per_step_attribution.py](hve/gui/tests/test_stats_per_step_attribution.py) :: `test_usage_credit_records_step_model` — モデル別回数を `usage_credit` の `step` / `model` から記録すること（Fleet 経路でも Model 列が埋まる）
- 契約変更に伴う既存テスト更新:
  - [hve/gui/tests/test_stats_history_state.py](hve/gui/tests/test_stats_history_state.py) :: `test_step_done_pushes_snapshot` — グローバル `set_context` 依存から Step 別 API（`record_step_context` / `record_step_model`）へ改訂
  - [hve/gui/tests/test_stats_history_view.py](hve/gui/tests/test_stats_history_view.py) — 累積差分方式のテスト 12 件（`_step_aiu_delta_nano` / `_compute_step_prev_map` 系および差分前提の View / CSV テスト）を削除し、Step 実測方式のテストへ置換
  - [hve/gui/tests/test_stats_per_step_attribution.py](hve/gui/tests/test_stats_per_step_attribution.py) :: `test_assistant_usage_does_not_double_count_step_model` — モデル別回数の記録元を `assistant_usage` から `usage_credit` へ移したことに伴い、`assistant_usage` 単独では記録せず二重計上しないことを検証する契約へ改訂


#### NFR-RTO-01 — 観測イベントの追加処理コスト
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_runtime_observability_parity.py](hve/tests/test_runtime_observability_parity.py) :: `TestPerformanceBudget::test_in_memory_pipeline_matches_gui_intake_budget` — 解析と集計（NFR-OBS-09 と同じ経路）を 2,000 件実行し 1 件あたり 0.2 ms 未満
  - [hve/tests/test_runtime_observability_parity.py](hve/tests/test_runtime_observability_parity.py) :: `TestPerformanceBudget::test_recorder_append_cost_is_bounded` — 1 行ごとの flush を伴う JSONL 追記を別枠で計測し、病的劣化のみを検出する上限（10 ms/件）で固定

#### NFR-RTO-02 — 既存 `[hve:stats]` 互換とオプション非追加
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_runtime_observability.py](hve/tests/test_runtime_observability.py) :: `TestBackwardCompatibleKinds` — 既存 producer の 15 kind を維持
  - [hve/tests/test_runtime_observability.py](hve/tests/test_runtime_observability.py) :: `TestNoNewConfigSurface` — `SDKConfig` に観測用フィールドを増やさないこと、配信マーカーが単一 env であること

#### NFR-RTO-03 — 観測失敗の非致命性と停止手段
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_runtime_observability_store.py](hve/tests/test_runtime_observability_store.py) :: `TestFailureIsolation::test_write_error_is_swallowed_and_disables_recorder` — 書込失敗を握り潰し以後無効化
  - [hve/tests/test_workbench_observability.py](hve/tests/test_workbench_observability.py) :: `TestStateHoldsMetrics::test_snapshot_survives_broken_registry` — 集計取得失敗時も表示側が落ちない

---

## §B Cloud Orchestrator（§4）

### FR-CLOUD-01 — `issues` の opened/labeled/closed 監視
- 判定: △
- 間接対応テスト:
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestWorkflowYamlAgenticInputs`（dispatcher YAML 静的検証）

### FR-CLOUD-02 — `trigger_map` に基づき reusable workflow を `workflow_call`
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) :: `TestRunnerTypeOptionParity.test_dispatcher_forwards_runner_type_for_ten_targets_only`
  - [hve/tests/test_cloud_dispatcher_asdw_dispatch.py](hve/tests/test_cloud_dispatcher_asdw_dispatch.py) :: `TestAsdwWebCloudDispatchEnabled`、`TestOtherCloudWorkflowsUnchanged`

### FR-CLOUD-03 — `opened` のみ `author_association` ガード
- 判定: △
- 間接対応テスト:
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestIssueQaReadyTransitionWorkflow`（`auto-issue-qa-ready-transition.yml` 側の OWNER/MEMBER/COLLABORATOR チェック）
- 根拠: dispatcher 自体の opened 限定ガードを直接検証するテストは未確認。

### FR-CLOUD-04 — `closed` でタイトルプレフィックス判定（`[AAS]` 等）
- 判定: ✗

### FR-CLOUD-05 — `setup-labels` 特例ルーティング
- 判定: △
- 間接対応テスト:
  - [hve/tests/test_label_consistency_audit.py](hve/tests/test_label_consistency_audit.py) — 現存トリガーラベル集合の整合を固定
  - [hve/tests/test_cloud_dispatcher_asdw_dispatch.py](hve/tests/test_cloud_dispatcher_asdw_dispatch.py) :: `TestOtherCloudWorkflowsUnchanged` — 現存Cloud Workflowのルーティング非退行を固定

### FR-CLOUD-06 — registry と同期済みの Cloud reusable workflow だけを dispatcher から起動する
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_cloud_reusable_workflow_parity.py](hve/tests/test_cloud_reusable_workflow_parity.py) :: `TestUnifiedWorkflows` — ASDW-WEB の生成 Step ID / Custom Agent を bash / Python registry と照合
  - [hve/tests/test_cloud_reusable_workflow_parity.py](hve/tests/test_cloud_reusable_workflow_parity.py) :: `test_asdw_web_state_transition_dependencies_match_registry` — Cloud 状態遷移依存を registry と照合
  - [hve/tests/test_cloud_reusable_workflow_parity.py](hve/tests/test_cloud_reusable_workflow_parity.py) :: `TestAkmCloudParity` — AKM の生成 Step ID / Custom Agent を hve registry と照合し、Step.1 完了→Step.2 起動 / Step.2 完了のみ Root `akm:done` を固定
  - [hve/tests/test_cloud_dispatcher_asdw_dispatch.py](hve/tests/test_cloud_dispatcher_asdw_dispatch.py) :: `TestAsdwWebCloudDispatchEnabled` — opened / labeled / done / closed の dispatch と reusable job を固定

### FR-CLOUD-07 — AAR の Cloud 対応
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_cloud_reusable_workflow_parity.py](hve/tests/test_cloud_reusable_workflow_parity.py) :: `TestUnifiedWorkflows`（`auto-agentic-retrieval-reusable.yml`）
  - [hve/tests/test_cloud_dispatcher_asdw_dispatch.py](hve/tests/test_cloud_dispatcher_asdw_dispatch.py) :: `TestOtherCloudWorkflowsUnchanged` — AAR の trigger / done / closed routing と reusable job を固定

### FR-CLOUD-10 — Issue body からの動的設定抽出（agentic_retrieval 等）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) :: `TestAgenticRetrievalWorkflowWiring.test_dispatcher_has_agentic_outputs_and_safety_valve`、`test_dispatcher_passes_agentic_inputs_to_aad_and_asdw`
  - [hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) :: `TestRunnerTypeOptionParity.test_dispatcher_detect_extracts_and_outputs_runner_type`

### FR-CLOUD-11 — `enable_agentic_retrieval=no` 時の正規化
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) :: `TestAgenticRetrievalWorkflowWiring.test_dispatcher_has_agentic_outputs_and_safety_valve`（`if enable_agentic_retrieval == 'no'` / `foundry_mcp_integration='false'` / `foundry_sku_fallback_policy='standard_allowed'`）
  - [hve/tests/test_template_engine.py](hve/tests/test_template_engine.py) :: `TestAgenticRetrievalConstants`（`normalize_agentic_retrieval_answers` の no/しない 正規化）
  - [hve/tests/test_template_engine_agentic.py](hve/tests/test_template_engine_agentic.py) :: `TestNormalizeAgenticRetrievalAnswers`

### FR-CLOUD-20 — Workflow ID と reusable workflow の 1:1 ディスパッチ
- 判定: △
- 直接対応テスト:
  - [hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) :: `TestRunnerTypeOptionParity.test_dispatcher_forwards_runner_type_for_ten_targets_only`、`test_pr4_reusable_workflows_accept_runner_type_and_switch_all_jobs`
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestPlaywrightE2EReusableWorkflow`
  - [hve/tests/test_issue_template_qa_parity.py](hve/tests/test_issue_template_qa_parity.py) / [hve/tests/test_label_consistency_audit.py](hve/tests/test_label_consistency_audit.py) — 現存Issue Form・reusable workflow・トリガーラベル集合の整合を固定し、ADIをCloud対象へ含めない

### FR-CLOUD-21 — AKM の `concurrency` キーで直列化
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestQaAnsweredAkmCloudWorkflow.test_has_repository_level_concurrency` — QA 起点 coordinator がリポジトリ単位の `akm-knowledge-write-*` を保持すること
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestQaAkmChildConcurrencyRouting` — 通常 AKM は大域 group、`qa-akm-sync` Root / Step は自己デッドロックを避ける child groupを使用し、routing label を Step へ伝播すること

### FR-CLOUD-22 — AKM の `check_qa_skip` 前段ジョブ
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_issue_template_qa_parity.py](hve/tests/test_issue_template_qa_parity.py) :: `TestWorkflowAutoQaParity`

### FR-CLOUD-23 — AKM ジョブタイムアウト 360 分
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestQaAnsweredAkmCloudWorkflow.test_job_timeout_is_360_minutes` / `test_timeout_marks_issue_as_blocked` / `test_timeout_rechecks_terminal_state_before_marking_blocked`

### FR-CLOUD-24 — Cloud QA 回答保存後の非待機 AKM 直列調整
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestIssueQaReadyTransitionWorkflow` / `TestQaReadyTransitionSaveAndDispatchPermissions` / `TestQaAnsweredAkmCloudWorkflow` / `TestQaAkmChildConcurrencyRouting`
  - [.github/scripts/python/tests/test_materialize_answered_qa.py](.github/scripts/python/tests/test_materialize_answered_qa.py) — 回答済み QA の正規化、固定パス、SHA、再パース、未解決回答の fail-closed
  - [hve/tests/test_prompts.py](hve/tests/test_prompts.py) :: `TestYamlWorkflowPromptDriftPhase5`
  - [hve/tests/test_issue_template_qa_parity.py](hve/tests/test_issue_template_qa_parity.py) — 現存Cloud Issue FormだけをQA回答保存契約の対象とし、ADIをCloud起動対象へ含めない

### FR-CLOUD-25 — QA 起点 AKM Root Issue への AKM 用モデル継承
- 判定: 実装済み
- 直接対応テスト:
  - [hve/tests/test_issue_template_qa_parity.py](hve/tests/test_issue_template_qa_parity.py) :: `TestAkmModelCloudParity`
- 受入ケース:
  - Knowledge Management を除く Cloud 対応テンプレートに `akm_model` dropdown があり、選択肢が `model` / `qa_model` と同一の許可リストである。→ ✓
  - `knowledge-management.yml` には `akm_model` を追加しない（再帰禁止）。→ ✓
  - `save-qa-answer` job が `### AKM 用モデル` を抽出し output へ公開し、`dispatch-akm` job が `akm_model` を `gh workflow run` へ渡す。→ ✓
  - `auto-akm-after-qa.yml` が `akm_model` 入力を受け取り、許可リスト外を `Auto` へ丸めて Root Issue body の `### 使用するモデル` 節へ必ず書き込む。→ ✓
  - 不正値で dispatch / 調整 Workflow を失敗させない。→ ✓
  - `.github/scripts/bash/lib/extract-akm-model.py` が抽出する節見出しと許可リストが `extract-qa-model.py` と同一規約である。→ ✓
  - `save-qa-answer` が `copilot-assign.sh` を source し `extract_akm_model` 経由で抽出する（python3 直呼びによる wrapper のデッドコード化を禁じる）。→ ✓（`test_transition_workflow_calls_extract_akm_model_wrapper` が source パターンを強制し、python3 直呼びの残存を `assertNotIn` で検出）
- 実装後の判断（敵対的レビュー反映）:
  - 当初 `save-qa-answer` は `extract-akm-model.py` を python3 で直接呼んでおり、`copilot-assign.sh` の `extract_akm_model()` がどこからも呼ばれないデッドコードだった（FR-MAINT-07 の同一ルール 2 重実装）。既存 4 workflow と同じ `source` パターンへ統一し、回帰テストで固定した。
- 既知の制約:
  - `guard` が同一 `qa-sha` の既存 AKM Root Issue を再利用する場合、`create` step をスキップするため今回の `akm_model` は body へ反映されない。これは `auto_merge` と同一の既存冪等性契約（FR-CLOUD-24）であり、本要件で変更していない。
  - Cloud 面には reasoning effort / context tier に相当する設定が存在しないため、FR-QA-04 の 3 項目のうちモデルのみが Cloud へ反映される。

### FR-CLOUD-26 — Issue Form による QA 起点 AKM の起動可否制御
- 判定: 実装済み
- 受入テスト:
  - [hve/tests/test_issue_template_qa_akm_merge.py](hve/tests/test_issue_template_qa_akm_merge.py) :: `TestQaAkmMergeIssueFormParity`
  - [hve/tests/test_issue_template_qa_akm_merge.py](hve/tests/test_issue_template_qa_akm_merge.py) :: `TestQaAkmMergeExtractor`
  - [hve/tests/test_issue_template_qa_akm_merge.py](hve/tests/test_issue_template_qa_akm_merge.py) :: `TestQaAkmMergeTransitionWorkflow`
- 受入ケース:
  - Knowledge Management を除く Cloud 対応テンプレートに `enable_qa_akm_merge` があり、既定は未チェックである。→ ✓
  - `knowledge-management.yml` には追加しない（再帰禁止）。→ ✓
  - `save-qa-answer` が `copilot-assign.sh` の `extract_qa_akm_merge` 経由で抽出し、未チェック時に `sync_required=false` を出力する。→ ✓
  - 節不在・解釈不能でも job を失敗させず `false` として扱う。→ ✓（抽出スクリプトは常に 0 終了し、失敗時は `|| qa_akm_merge="false"` でフォールバック）
  - `dispatch-akm` / 後続 job の条件式へ同じ判定を重複実装しない。→ ✓（`test_gate_is_not_duplicated_in_downstream_jobs`）
- 実装後の判断:
  - ゲートを `dispatch-akm` の `if` ではなく `save-qa-answer` の `sync_required` へ入れた。既存の `finalize` job が `sync_required != 'true'` を許容する条件式を持つため、下流 job を無改修のまま成立させられる。
  - 抽出スクリプトは `sys.stdin.buffer` から UTF-8 で直接デコードする。locale 依存で見出しが化けると常に `false` へ倒れ、利用者の選択を無視するため。

### FR-CLOUD-30 — `state_transition` 時の次候補 Issue コメント
- 判定: ✗（`suggest-next` ジョブ検証なし）

### FR-CLOUD-40 — `runner_type` 入力による Runner ラベル選択
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) :: `TestRunnerTypeOptionParity.test_target_templates_have_runner_type_dropdown`、`test_out_of_scope_templates_do_not_have_runner_type`、`test_dispatcher_detect_extracts_and_outputs_runner_type`、`test_dispatcher_forwards_runner_type_for_ten_targets_only`、`test_pr4_reusable_workflows_accept_runner_type_and_switch_all_jobs`

### §4.2 mode 値 4 種（initialize/state_transition/closed/skip）
- 判定: △
- 間接対応テスト:
  - [hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) :: `TestRunnerTypeOptionParity.test_dispatcher_detect_extracts_and_outputs_runner_type`（dispatcher detect ジョブの出力配線を検証）
- 根拠: mode 4 値の分岐そのものを直接テストする関数は未確認。

---

## §C CLI Orchestrator 基本（§5.1〜5.5）

### FR-CLI-01 — `--workflow / -w` 必須
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestParserBasic.test_workflow_or_autopilot_chain_required_at_command_runtime`、`test_workflow_short_option`

### FR-CLI-02 — `orchestrate` の主要オプション群
- 判定: ✓（多数）
- 直接対応テスト（モデル）: `TestParserBasic.test_model_option`、`test_model_option_gpt_5_5`、`TestReviewModelCLI`（test_main.py）
- 並列制御: `TestParserBasic.test_max_parallel_option`
- 自動レビュー: `test_auto_qa_flag`、`test_auto_contents_review_flag`、`test_auto_coding_agent_review_flag`、`test_auto_coding_agent_review_auto_approval_flag`
- Work IQ: `test_workiq_flags`、`TestBuildParams.test_build_config_workiq`、`test_build_config_workiq_akm_review_can_be_enabled_without_qa`、`test_build_config_workiq_draft_output_dir_not_overridden_when_cli_omitted`
- Work IQ タイムアウトの伝搬: [hve/tests/test_runner_foundry_mcp_routing.py](hve/tests/test_runner_foundry_mcp_routing.py) :: `test_pre_qa_sub_session_applies_the_configured_workiq_timeout` — `--workiq-request-timeout` / `WORKIQ_REQUEST_TIMEOUT` / GUI C4 で設定した値が、事前 QA サブセッションの Work IQ MCP 設定（`MCPServerConfigLocal.timeout`、ミリ秒）へ届くこと
  - 2026-08-20 の実測: RED は `KeyError: 'timeout'`（1 failed / 12 passed）。[hve/runner.py](hve/runner.py) の `_build_sub_session_opts` が `build_workiq_mcp_config` へ `request_timeout` を渡しておらず、設定値が SDK 既定値に置き換わっていた。[hve/orchestrator.py](hve/orchestrator.py) の Work IQ 経路 4 箇所は渡していたため、runner だけが非対称だった。GREEN は 230 passed / 47 subtests、影響範囲 423 passed / 95 subtests。
- Git/PR: `test_create_issues_flag`、`test_create_pr_flag`、`test_branch_option`、`test_repo_option`、`TestCreateIssuesNewFlow`
- 出力: `test_quiet_flag`、`TestBuildConfigOutputFlags`、`TestBuildConfigLogLevel`、`TestNoColor`、`TestShowBanner`、`TestScreenReader`、`TestTimestampStyle`、`TestFinalOnlyMode`（test_console.py）
- タイムアウト: `test_timeout_option`、`TestBuildConfigReviewTimeout`、`test_review_timeout_default`、`test_review_timeout_option`
- MCP/CLI 接続: `test_cli_url_option`、`TestLoadMCPConfig`
- 共通絞り込み: `test_steps_option`、`test_app_id_option`、`test_app_ids_option`、`test_resource_group_option`、`TestBuildParams.test_app_ids_in_params`、`test_app_ids_single_also_sets_app_id`
- AKM 固有: `test_sources_original_docs_option`、`test_target_files_option`、`test_force_refresh_flag`、`TestBuildParams.test_akm_*`（多数）
- ADI 固有: [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestParserBasic.test_adi_target_scope_option` / `test_adi_depth_option` / `test_adi_focus_areas_option`、`TestBuildParams.test_adi_params_defaults` / `test_adi_params_custom_values`、`TestAdiDepthPrompt` — `--purpose` / `--target-scope` / `--depth` / `--focus-areas` をADIパラメータとして受理する契約
- ADOC 固有: `test_adoc_target_dirs_option`、`test_adoc_exclude_patterns_option`、`test_adoc_doc_purpose_option`、`test_adoc_max_file_lines_option`、`TestBuildParams.test_adoc_params_*`
- ARD 固有: [hve/tests/test_main_ard.py](hve/tests/test_main_ard.py) — ARD CLI 引数を網羅
- 追加: `test_context_max_chars_option`
- 自己改善: `TestSelfImproveCLI`
- 検証: `test_dry_run_flag`、`TestMainDryRun`

### FR-CLI-10 — 引数なし時の対話 wizard 起動
- 判定: △
- 間接対応テスト:
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestInteractiveModeCodeReview`、`TestInteractiveModeAutoExecModes`
- 根拠: `_cmd_run_interactive` の主要経路は検証されるが、引数なし entrypoint からの起動そのものを直接検証するテストとしては確認していない。

### FR-CLI-11 — `quick-auto` / `custom-auto` / `manual` の3実行モード
- 判定: 要追加（v2.43 改訂契約の RED 未作成）
- 直接対応テスト:
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestInteractiveModeAutoExecModes.test_quick_auto_*`、`test_custom_auto_*`
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestInteractiveModeCodeReview`、`TestInteractiveModeQaAutoDefaults`、`TestInteractiveAdocParamsValidation`、`TestInteractiveWorkflowParamPrompts`
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestAdiDepthPrompt` — ADIの`depth`メニュー選択を固定
  - [hve/tests/test_adi.py](hve/tests/test_adi.py) :: `test_adi_params_are_minimal` / `test_adi_non_interactive_defaults` — ADIが4パラメータだけを公開し、独立Workflowへ分散しないことを固定
- 追加予定テスト:
  - [hve/tests/test_main_ard.py](hve/tests/test_main_ard.py) — ARD wizard が3モードの意味を維持し、モード別に recommendation ID の事前入力プロンプトを表示または省略すること（wizard表示層を担当）

### FR-CLI-12 — ARD wizard の4表示グループとKPI/OKR単一選択状態
- 判定: 要追加（v2.43 改訂契約の RED 未作成）
- 直接対応テスト:
  - [hve/tests/test_workflow_registry_ard.py](hve/tests/test_workflow_registry_ard.py) :: `TestARDWizardOrder`、`TestARDDisplayNames`
  - [hve/tests/test_main_ard.py](hve/tests/test_main_ard.py) — ARD CLI 全体
  - [hve/tests/test_orchestrator_ard.py](hve/tests/test_orchestrator_ard.py) :: `TestOrchestratorARD`
- 追加予定テスト:
  - [hve/tests/test_main_ard.py](hve/tests/test_main_ard.py) — `ARD_DEFAULT_GROUP_IDS` 由来の既定選択、グループ3だけからのKPI/OKR導出、別Yes/No質問の不在、quick-autoでグループ3を外した場合の無効化

### FR-CLI-13 — AKM wizard の `sources` マルチ選択 + `workiq_dxx` 取り込み
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_akm_sources_normalization.py](hve/tests/test_akm_sources_normalization.py) :: `TestNormalizeAkmSources`、`TestDefaultAkmTargetFiles`
  - [hve/tests/test_akm_workiq_ingest.py](hve/tests/test_akm_workiq_ingest.py) :: `TestWorkiqAkmIngestDxxFilter`

### FR-CLI-14 — ASDW-WEB wizard の Step 1.3 パラメータ収集と既定値提示
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestAsdwDataDeployWizardParams` — wizard が `required_params` 由来の順で尋ね、`default_params` を既定値として提示し、既定値のないキーだけ `required=True` になることを検証

### FR-CLI-20 — `cli_args is not None` で非対話モード判定
- 判定: ✓
- 間接対応テスト:
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestCollectParamsNonInteractiveAppIds`
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestCollectParamsNonInteractiveAdiDefaults` — ADIの4パラメータが非対話経路で既定化されることを固定

### FR-CLI-21 — 非対話モードでの `_collect_params_non_interactive`
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestCollectParamsNonInteractiveAppIds`
  - [hve/tests/test_orchestrator_ard.py](hve/tests/test_orchestrator_ard.py) :: `TestOrchestratorARD`
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestCollectParamsNonInteractiveAdiDefaults` / `TestAdiQuestionnairePostDag` — ADI非対話既定値と質問票main成果物のpost-DAG検証・明示commit対象を固定

### FR-CLI-70 — `_build_step_prompt` へ `subissues.md` フォーマット例を注入しない
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestBuildStepPromptContract::test_FR_CLI_70_template_prompt_has_no_subissues_format_hint` — テンプレート展開経路のプロンプトに `subissues.md` フォーマット例が含まれないことを固定
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestBuildStepPromptContract::test_FR_CLI_70_fallback_prompt_has_no_subissues_format_hint` — `body_template_path` 未宣言 Step の簡易プロンプトにも含まれないことを固定
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestBuildStepPromptContract::test_FR_CLI_70_no_subissues_hint_symbols_in_orchestrator` — `_SUBISSUES_FORMAT_HINT` / `_subissues_format_hint_for_step` が `hve/orchestrator.py` に残っていないことを固定

### FR-CLI-71 — `body_template_path` 宣言 Step のテンプレート失敗時は fail-closed
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestBuildStepPromptContract::test_FR_CLI_71_template_render_exception_propagates` — レンダリング例外が簡易プロンプトへ縮退せず上位へ伝播することを固定
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestBuildStepPromptContract::test_FR_CLI_71_template_render_empty_is_failure` — レンダリング結果が `""` / `None` の場合も失敗として `ValueError` を送出することを固定（subTest 2 件）
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestBuildStepPromptContract::test_FR_CLI_71_step_without_template_path_uses_fallback_prompt` — `body_template_path` 未宣言 Step は従来どおり簡易プロンプトを使う（本要件の対象外挙動）ことを固定

### FR-CLI-72 — 製品 run 中に HVE 自身のテストスイートを子プロセス起動しない
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_asdw_step12_verification.py](hve/tests/test_asdw_step12_verification.py) :: `test_local_verification_never_spawns_a_pytest_subprocess` — bash / ShellCheck の注入境界を stub した状態で `subprocess.run` が 1 度も呼ばれないことを固定
  - [hve/tests/test_asdw_step12_verification.py](hve/tests/test_asdw_step12_verification.py) :: `test_module_exposes_no_focused_pytest_surface` — `_FOCUSED_PYTEST_TARGETS` / `_default_pytest_runner` / `PytestRunner` が存在せず、`run_asdw_step12_local_verification` の引数にも pytest 系が無いことを固定
  - [hve/tests/test_asdw_step12_verification.py](hve/tests/test_asdw_step12_verification.py) :: `test_checks_run_in_the_fixed_order` — ローカル検証が静的検査（`bash -n` → ShellCheck → artifact validator → LF/BOM）の固定順に限定されることを固定
  - [hve/tests/test_asdw_step12_verification.py](hve/tests/test_asdw_step12_verification.py) :: `test_all_checks_pass_yields_canonical_statuses`、`test_output_round_trips_with_the_validator` — 静的検査のみで machine log の 3 状態が確定し validator を通ることを固定

### FR-CLI-73 — Copilot セッションへ公開する repository Skill ディレクトリの限定
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_runner_external_skill_routing.py](hve/tests/test_runner_external_skill_routing.py) :: `test_repository_skill_directories_default_exposes_root_only` — Step コンテキスト無しでは `.github/skills` root のみを公開することを固定
  - [hve/tests/test_runner_external_skill_routing.py](hve/tests/test_runner_external_skill_routing.py) :: `test_repository_skill_directories_scope_to_declared_skills` — 宣言 Skill の親ディレクトリだけを追加公開し、未宣言の `harness` / `output` / `azure-skills` / `knowledge-management` を公開しないことを固定
  - [hve/tests/test_runner_external_skill_routing.py](hve/tests/test_runner_external_skill_routing.py) :: `test_declared_required_repository_skills_stay_resolvable` — 公開範囲を縮約しても当該 Step の `required_skills` が解決可能であることを固定
  - [hve/tests/test_runner_external_skill_routing.py](hve/tests/test_runner_external_skill_routing.py) :: `test_main_session_skill_directories_exclude_undeclared_repository_skills` — メインセッションへ未宣言 repository Skill ディレクトリを渡さないことを固定
  - [hve/tests/test_runner_external_skill_routing.py](hve/tests/test_runner_external_skill_routing.py) :: `test_required_external_skill_rejects_sdk_skill_directory_fallback`、`test_optional_only_external_skill_allows_sdk_skill_directory_fallback` — external Skill の fail-closed 解決が維持されることを固定

### FR-CLI-76 — Step 実行セッションと QA サブセッションへ公開する MCP サーバをリポジトリ宣言分に限定
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_runner_session_mcp_scope.py](hve/tests/test_runner_session_mcp_scope.py) :: `test_repository_mcp_servers_are_injected_when_caller_omits_them` — `mcp_servers` 未指定のセッション生成で `.github/.mcp.json` の `mcpServers` が渡ることを固定
  - [hve/tests/test_runner_session_mcp_scope.py](hve/tests/test_runner_session_mcp_scope.py) :: `test_config_discovery_is_disabled_when_repository_mcp_is_injected` — 同時に `enable_config_discovery=False` が渡ることを固定
  - [hve/tests/test_runner_session_mcp_scope.py](hve/tests/test_runner_session_mcp_scope.py) :: `test_explicit_mcp_servers_are_not_overridden` — 呼び出し側が `mcp_servers` を明示した場合に上書きしないことを固定
  - [hve/tests/test_runner_session_mcp_scope.py](hve/tests/test_runner_session_mcp_scope.py) :: `test_explicit_config_discovery_is_not_overridden` — 呼び出し側が `enable_config_discovery` を明示した場合に上書きしないことを固定
  - [hve/tests/test_runner_session_mcp_scope.py](hve/tests/test_runner_session_mcp_scope.py) :: `test_missing_repository_mcp_config_keeps_config_discovery_enabled` — `.github/.mcp.json` が無い作業ディレクトリでは `mcp_servers` を渡さず `enable_config_discovery=True` のままとすることを固定
  - [hve/tests/test_runner_session_mcp_scope.py](hve/tests/test_runner_session_mcp_scope.py) :: `test_malformed_repository_mcp_config_keeps_config_discovery_enabled` — `mcpServers` が dict でない・キーが無い・空 dict・JSON として壊れている場合も同様に従来動作へ縮退することを固定
  - [hve/tests/test_runner_session_mcp_scope.py](hve/tests/test_runner_session_mcp_scope.py) :: `test_skill_directories_are_still_injected_when_config_discovery_is_disabled` — `enable_config_discovery=False` は Skill の自動探索も止めるため、FR-CLI-73 が定める `skill_directories` の明示注入が同時に行われることを固定
  - [hve/tests/test_runner_session_mcp_scope.py](hve/tests/test_runner_session_mcp_scope.py) :: `test_declared_mcp_servers_specify_a_tools_allowlist` — `.github/.mcp.json` の全サーバが `tools` キーを持つことを固定（欠落するとそのサーバは起動されずツールが 1 件も公開されない）
  - [hve/tests/test_runner_session_mcp_scope.py](hve/tests/test_runner_session_mcp_scope.py) :: `test_foundry_required_azure_config_specifies_a_tools_allowlist` — Foundry 必須 Step が明示指定する Azure MCP 設定にも同じ制約が適用されることを固定
  - （v2.41 追加。事前 QA サブセッション）[hve/tests/test_runner_pre_qa_mcp_scope.py](hve/tests/test_runner_pre_qa_mcp_scope.py) :: `test_pre_qa_sub_session_disables_config_discovery` — `_hve_workiq` を明示するサブセッションでも `enable_config_discovery=False` を渡し、プラグイン由来 `workiq` の併存を防ぐことを固定
  - [hve/tests/test_runner_pre_qa_mcp_scope.py](hve/tests/test_runner_pre_qa_mcp_scope.py) :: `test_pre_qa_sub_session_merges_declared_mcp_servers` — 自動探索を止める代わりにリポジトリ宣言分を明示併合することを固定
  - [hve/tests/test_runner_pre_qa_mcp_scope.py](hve/tests/test_runner_pre_qa_mcp_scope.py) :: `test_pre_qa_sub_session_keeps_workiq_least_privilege` — 併合後も `_hve_workiq` のツール allowlist が `ask` のみであることを固定
  - [hve/tests/test_runner_pre_qa_mcp_scope.py](hve/tests/test_runner_pre_qa_mcp_scope.py) :: `test_pre_qa_sub_session_drops_declared_workiq_aliases` — 宣言側に Work IQ 別名があっても併合せず `_hve_workiq` だけを残すことを固定
  - [hve/tests/test_runner_pre_qa_mcp_scope.py](hve/tests/test_runner_pre_qa_mcp_scope.py) :: `test_pre_qa_sub_session_applies_azure_free_workflow_filter` — FR-CLI-79 の Azure 除外が本サブセッションにも適用されることを固定
  - [hve/tests/test_runner_pre_qa_mcp_scope.py](hve/tests/test_runner_pre_qa_mcp_scope.py) :: `test_pre_qa_sub_session_keeps_discovery_when_nothing_is_declared` — 宣言が無い / 空 / 壊れている場合は `_hve_workiq` の注入だけを行い自動探索を残す（回帰回避のフォールバック）ことを固定
  - [hve/tests/test_runner_pre_qa_mcp_scope.py](hve/tests/test_runner_pre_qa_mcp_scope.py) :: `test_review_sub_session_is_left_to_the_generic_frcli76_path` — Work IQ を使わない Review サブセッションは `mcp_servers` を持たず共通経路に委ねることを固定

### FR-CLI-74 — run 開始時に HVE ソースの未コミット変更を一括報告して停止
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_orchestrator_branch_mode.py](hve/tests/test_orchestrator_branch_mode.py) :: `TestDirtyHveSourcePreflight::test_dirty_hve_sources_abort_before_branch_creation` — dirty 検出時に branch 作成・Agent セッション開始より前に `blocked` で停止することを固定
  - [hve/tests/test_orchestrator_branch_mode.py](hve/tests/test_orchestrator_branch_mode.py) :: `TestDirtyHveSourcePreflight::test_dirty_hve_sources_are_reported_in_a_single_batch` — 検出した全パスが 1 回のエラー報告にまとまることを固定
  - [hve/tests/test_orchestrator_branch_mode.py](hve/tests/test_orchestrator_branch_mode.py) :: `TestDirtyHveSourcePreflight::test_clean_hve_sources_do_not_block_the_run`、`test_dry_run_does_not_block_on_dirty_hve_sources`、`test_guard_also_applies_without_workflow_branch_mode` — clean 時の通過 / `--dry-run` 除外 / branch を作らない run でも適用されることを固定
  - [hve/tests/test_orchestrator_branch_mode.py](hve/tests/test_orchestrator_branch_mode.py) :: `TestDirtyHveSourceDetection::test_only_hve_source_prefixes_are_reported` — HVE ソース 7 prefix 配下のみを検出し、生成物（`docs/` / `src/` 等）を無視することを固定
  - [hve/tests/test_orchestrator_branch_mode.py](hve/tests/test_orchestrator_branch_mode.py) :: `TestDirtyHveSourceDetection::test_explicit_target_output_paths_are_excluded` — 利用者が明示指定した target 出力パスが対象外になることを固定
  - [hve/tests/test_orchestrator_branch_mode.py](hve/tests/test_orchestrator_branch_mode.py) :: `TestDirtyHveSourceDetection::test_git_failure_is_not_silently_swallowed_into_success`、`test_git_is_invoked_with_list_arguments` — git 失敗時に検出結果を捏造しないこと、および git をリスト引数で起動すること（NFR-SEC-03）を固定

### FR-CLI-75 — `git add` 後 `commit` 前の staged path 検査と index reset
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_orchestrator_branch_mode.py](hve/tests/test_orchestrator_branch_mode.py) :: `TestStagedHveSourceGuard::test_staged_hve_source_blocks_commit_and_push` — staged に HVE ソースが含まれる場合 commit / push を行わず停止することを固定
  - [hve/tests/test_orchestrator_branch_mode.py](hve/tests/test_orchestrator_branch_mode.py) :: `TestStagedHveSourceGuard::test_staged_hve_source_resets_the_index_without_touching_worktree` — index のみ reset し作業ツリーを変更しないことを固定
  - [hve/tests/test_orchestrator_branch_mode.py](hve/tests/test_orchestrator_branch_mode.py) :: `TestStagedHveSourceGuard::test_target_only_staging_commits_and_pushes_as_before` — target アプリ成果物のみの staging は従来どおり commit / push まで進むことを固定
  - [hve/tests/test_orchestrator_branch_mode.py](hve/tests/test_orchestrator_branch_mode.py) :: `TestStagedHveSourceGuard::test_hve_source_excluded_from_staging_does_not_block_commit` — `git add` の pathspec 除外で HVE ソースが staged にならない場合は停止しないことを固定

### FR-CLI-30 — `--create-issues` シーケンス（ブランチ → Issue → DAG → PR …）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestCreateIssuesNewFlow.test_create_issues_implies_create_pr`、`test_create_issues_requires_token_and_repo`、`test_auto_coding_agent_review_and_create_issues_allowed`
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestCreatePrIfNeeded`、`TestRequestCodeReviewSDK`、`TestDoneLabeling`
  - [hve/tests/test_github_api.py](hve/tests/test_github_api.py) :: `TestCreateIssue`、`TestLinkSubIssue`、`TestAddLabels`、`TestCreatePullRequest`、`TestPostComment`

### FR-CLI-31 — `--create-issues` が `--repo` + `GH_TOKEN` 必須
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestCreateIssuesNewFlow.test_create_issues_requires_token_and_repo`
  - [hve/tests/test_github_api.py](hve/tests/test_github_api.py) :: `TestResolveToken`、`TestResolveRepo`

### FR-CLI-32 — `--create-pr` は PR 作成のみ（auto-merge は別運用）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestParserBasic.test_create_pr_flag`
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestCreatePrIfNeeded`

### FR-CLI-33 — `--ignore-paths` を pathspec 除外として扱う
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `test_ignore_paths_default_in_config`、`test_ignore_paths_cli_override`、`test_ignore_paths_auto_remove_qa_when_workiq_draft_and_create_pr`

### FR-CLI-34 — `--delete-local-merged-branch`（既定有効）でマージ済みローカル作業ブランチを削除
- 判定: ✗（要追加 — T3〜T8 で実装予定。下記は計画テスト。全計画テストの実装完了後に判定を ✓ へ更新する）
- 直接対応テスト（予定）:
  - [hve/tests/test_config.py](hve/tests/test_config.py) :: `TestSDKConfigDefaults.test_delete_local_merged_branch_default`（既定 True）
  - [hve/tests/test_github_api.py](hve/tests/test_github_api.py) :: `TestGetPullRequest`（PR の `merged` 状態取得 / 404・異常時の戻り）
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestDeleteLocalMergedBranch`（merged 検知で base へ `checkout` 後 `git branch -D` / 未マージ・タイムアウト・checkout 失敗・中断で削除しない / `enable_auto_merge` 無効・PR 未作成時は何もしない / リモート削除 API を呼ばない / 既定 15 秒間隔・最大 600 秒）
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestParserBasic.test_delete_local_merged_branch_flag`（既定 True / `--no-delete-local-merged-branch` で False / `cfg` 反映）
  - GUI（T7/T8 で対象ファイルを確定）: `OrchestrateArgs.delete_local_merged_branch` の off 時のみ `--no-delete-local-merged-branch` 出力 / C5・C10 の共通コンポーネントと双方向同期

### §5.1 サブコマンド体系（run/orchestrate/qa-merge/workiq-doctor/emit-prompt）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestEmitPromptCommand`、`TestWorkIQDoctorSdkProbeArgs`
  - [hve/tests/test_qa_merger.py](hve/tests/test_qa_merger.py) — qa-merge 全体

---

## §D Resume 2 層トランザクション保護（廃止履歴）

- 判定: 現行評価対象外
- v1.1 で `state.json`、RunLock、RunJournal、recovery、reconcile、`resume` サブコマンド、checkpoint を含む Resume 機能と専用テストを削除した。旧 FR-CLI-40〜51 のカバレッジは現行品質指標へ算入しない。
- 存続する決定論的 SDK セッション ID は Resume ではなく fork-on-retry のために使用する。基礎 ID 生成は [hve/tests/test_session_id.py](hve/tests/test_session_id.py)、SDK への伝播は [hve/tests/test_runner.py](hve/tests/test_runner.py) :: `TestSessionIdPropagation`、fork 連携は [hve/tests/test_fork_session_id.py](hve/tests/test_fork_session_id.py) :: `TestMakeForkSessionId` / `TestSetForkIndexAndMainSessionId` で確認する。

---

## §E パラメータ（§5.7〜6）

### FR-CLI-50（既存成果物検出）

> 旧 §5.6 の同番号 Resume 要件は v1.1 で廃止済み。本節の現行 FR-CLI-50 は既存成果物検出だけを表す。

- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestDetectExistingArtifacts`

### FR-CLI-51（再利用コンテキストの 3 条件 AND）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestReuseContextFiltering`、`TestBuildReuseContext`、`TestBuildReuseContextStepKind`

### FR-CLI-52（Step 種別推定 `_infer_step_kind`、half 切り上げ + 優先順位）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestInferStepKind`

### FR-CLI-60 — `--self-improve` / `HVE_AUTO_SELF_IMPROVE` 有効化、`--no-self-improve` 最優先
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestSelfImproveCLI.test_self_improve_flag_enables`、`test_no_self_improve_flag_sets_skip`、`test_no_self_improve_overrides_self_improve`、`test_env_var_enables_self_improve`、`test_default_self_improve_is_false`
  - [hve/tests/test_self_improve.py](hve/tests/test_self_improve.py) :: `TestSDKConfigSelfImproveDefaults`、`TestRunImprovementLoopAutoFalse`、`TestRunImprovementLoopDisabledScope`

### FR-CLI-61 — Self-Improve スコープ 4 値
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_self_improve.py](hve/tests/test_self_improve.py) :: `TestSelfImproveScopeConfig`、`TestResolveTargetScopePaths`
  - [hve/tests/test_config.py](hve/tests/test_config.py) :: `TestSelfImproveWorkflowSdkConfig`、`TestSDKConfigArtifactImprovementDefaults`、`TestSDKConfigArtifactImprovementFromEnv`

### FR-CLI-62 — ワイルドカード `*` 展開先（`work/` 除外）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_self_improve.py](hve/tests/test_self_improve.py) :: `TestResolveTargetScopePaths`

### FR-CLI-77 — 起動時の索引差分更新と watcher 起動の直列化

- 判定: 実装済み
- 受入テスト:
  - [hve/tests/test_index_refresh.py](hve/tests/test_index_refresh.py) :: `TestEnumerateTargets` — 実在する索引 DB だけを対象化し、未構築 strategy / profile、レガシー `.mdq/index.sqlite`、`graphrag` 作業ディレクトリを含めないこと
  - [hve/tests/test_index_refresh.py](hve/tests/test_index_refresh.py) :: `TestRefreshAll` — `rebuild` を真にしないこと、builder へ解決済み絶対パスを渡すこと、1 件の失敗が他を止めないこと、対象 0 件がエラーにならないこと
  - [hve/tests/test_index_refresh.py](hve/tests/test_index_refresh.py) :: `TestBackgroundLifecycle` — `HVE_STARTUP_INDEX_REFRESH` による無効化、プロセス内 1 回だけの起動、`wait_until_idle` の完了 / タイムアウト、worker 例外時の状態復帰
  - [hve/tests/test_orchestrator_index_refresh.py](hve/tests/test_orchestrator_index_refresh.py) :: `TestWatcherStartIsDeferred` — watcher 生成より前に `wait_until_idle` が完了すること、`dry_run` と watch 全無効時にスレッドを起こさないこと、`run_workflow` が当該経路を使うこと
  - [hve/tests/test_orchestrator_index_refresh.py](hve/tests/test_orchestrator_index_refresh.py) :: `TestEntryCommands` — Orchestrator 系サブコマンドでのみ開始し、`login` 等では開始しないこと
- 受入ケース:
  - `.mdq/index-<lang>-<strategy>.sqlite` に一致する実在ファイルだけが mdq 対象になる。`.mdq/index.sqlite` と `.mdq/graphrag-<lang>/` は対象に含まれない。→ ✓
  - `cq` 設定が宣言する profile のうち DB が実在するものだけが対象になる。設定不在では例外を送出せず対象 0 件になる。→ ✓
  - 更新は差分更新であり、完全再ビルドを行わない。→ ✓
  - `run_workflow` は差分更新の完了を待ってから `MdqWatcher` / `CqWatcher` を生成する。→ ✓
  - `HVE_STARTUP_INDEX_REFRESH=0` で起動しない。→ ✓
  - 引数なし起動（GUI 既定）と `gui` は CLI 側の対象外である。→ ✓
- RED / GREEN 証跡:
  - RED（実装前）: `hve/tests/test_index_refresh.py` は `hve.index_refresh` 不在で 22 error、`hve/tests/test_orchestrator_index_refresh.py` は `_start_index_watchers` / `INDEX_REFRESH_COMMANDS` 不在で 8 failed（実測）。相対パス正規化の RED は `test_builders_receive_an_absolute_repo_root` が `AssertionError: WindowsPath('.')` で 1 failed（実測）。
  - GREEN: `hve/tests/test_index_refresh.py` 17 passed、`hve/tests/test_orchestrator_index_refresh.py` 9 passed。実リポジトリへのスモークで `{'targets': 4, 'refreshed': 4, 'failed': []}`（所要 32.7 秒、warm）。
- 実装後の判断（FR-MAINT-07 面横断の再利用）:
  - `index-<lang>-<strategy>.sqlite` の分解規則は [mdq/store.py](mdq/store.py) `existing_index_dbs()` に単一実装し、同型の実装を持っていた [mdq/query_router.py](mdq/query_router.py) `discover_available_strategies()` を当該関数へ委譲させた。HVE 側（[hve/index_refresh.py](hve/index_refresh.py)）にパス規則を再実装していない。
  - 環境変数の真偽判定は [hve/config.py](hve/config.py) `_env_bool` と同一規約（`true` / `1` / `yes` のみ真）とした。`hve/orchestrator.py` は相対 / 絶対 import の双方で読み込まれうるため、`hve/config.py` への import 依存を作らず規約だけを揃えている。
- 既知の制約:
  - 複数の HVE プロセスを同時に起動した場合、同一索引 DB への書き込みが競合して片方が当該対象をスキップしうる（警告のみ）。プロセス間の排他は本変更の範囲外とした。既存の watcher も同じ性質を持つ。
  - HVE が起動する `CqWatcher` は設定の先頭 profile だけを監視する既存挙動を変えていない。起動時の差分更新は実在する全 profile を対象にする。

### FR-CLI-78 — CLI Autopilot の実行開始確認

- 判定: 実装済み
- 受入テスト:
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestAutopilotChainStartConfirmation` — 非対話 stdin では確認せず続行、対話時は `y` で続行 / `n` と空入力で中止、`_cmd_orchestrate_autopilot_chain` が確認関数を参照すること
  - [hve/tests/test_autopilot_cli.py](hve/tests/test_autopilot_cli.py) :: `test_cli_autopilot_dry_run_exits_zero` — `--autopilot-dry-run` が計画のみで exit 0 になること（既存）
- 受入ケース:
  - 標準入力が対話可能なとき、計画サマリ表示後・`CliAutopilotRunner` 生成前に確認する。→ ✓
  - 承認されない場合は Step を 1 つも実行せず終了コード 0 で終了する。→ ✓
  - 標準入力が対話不可能なとき（CI 等）は確認せず実行する。確認を省略する新規オプションは追加していない。→ ✓
  - `--autopilot-dry-run` は確認より前に return するため確認を求めない。→ ✓
- RED / GREEN 証跡:
  - RED（実装前）: `TestAutopilotChainStartConfirmation` は `_confirm_autopilot_chain_start` 不在で失敗（実測）。
  - GREEN: `hve/tests/test_main.py::TestAutopilotChainStartConfirmation` 5 passed、`hve/tests/test_autopilot_cli.py` 7 passed。
- 既知の制約:
  - 「対話 stdin かつ `--autopilot-dry-run`」の組み合わせは自動テストしていない。Windows で pty を用いた TTY 擬似化が困難なためで、dry-run の `return` が確認呼び出しより前にあることは実装順序で担保している。
  - 当初 `_cmd_orchestrate_autopilot_chain` 全体を対象にした統合テストを書いたが、本テストモジュールは `__main__.py` を importlib で別名ロードするため `hve.autopilot` への patch が届かず、**実際の Autopilot が起動した**。実行は FR-CLI-74（HVE ソース未コミット変更ガード）が全 APP を blocked にして停止し、branch 作成・成果物生成は発生していない。以後、この経路の統合テストは行わず、確認ロジックの単体テストに限定する。

### FR-CLI-79 — Azure を利用しない Workflow の MCP 縮約

- 判定: 実装済み
- 受入テスト:
  - [hve/tests/test_runner.py](hve/tests/test_runner.py) :: `TestAzureFreeWorkflowMcpFilter` — allowlist の Workflow で `azure` を除外し `microsoft-learn` を残すこと、他の Workflow では除外しないこと、`workflow_id` が None / 空 / 未知のとき全サーバを渡すこと、allowlist が registry に実在すること、allowlist の全 Step のプロンプトが Azure に言及しないこと、`.github/.mcp.json` に除外対象名が実在すること、フィルタが FR-CLI-76 の注入経路と `run_step` の呼び出しに配線されていること
  - （v2.41 追加）[hve/tests/test_runner_pre_qa_mcp_scope.py](hve/tests/test_runner_pre_qa_mcp_scope.py) :: `test_pre_qa_sub_session_applies_azure_free_workflow_filter` — FR-CLI-76 の受入範囲へ移った事前 QA サブセッションにも Azure 除外が適用されることを固定
- 受入ケース:
  - `ard` / `akm` / `adi` / `adoc` の Step セッションへ `azure` を渡さない。→ ✓
  - 上記以外の 9 Workflow では従来どおり `azure` を渡す。→ ✓
  - `workflow_id` を解決できない場合は全サーバを渡す（fail-safe）。→ ✓
  - `microsoft-learn` は除外しない。→ ✓
  - 新規 CLI オプション / `SDKConfig` フィールドを追加していない。→ ✓
- RED / GREEN 証跡:
  - RED（実装前）: `ImportError: cannot import name '_AZURE_FREE_WORKFLOWS' from 'runner'`（実測）。
  - GREEN: `hve/tests/test_runner.py` 213 passed（`TestAzureFreeWorkflowMcpFilter` 7 passed / 16 subtests）。関連 5 スイート 262 passed。
- 実装後の判断（FR-MAINT-07 面横断の再利用）:
  - 既存の [hve/runner.py](hve/runner.py) `_filter_mcp_servers_for_session`（Work IQ alias 除外の単一実装、呼び出し 3 箇所）へ除外条件を 1 つ追加した。新しい宣言ファイル・抽象層は追加していない。
  - `StepDef.per_key_mcp_servers` は fan-out キー単位の**追加専用マージ**でサーバを除去できないため、再利用先として採用しなかった。
- 既知の制約:
  - Step 単位の絞り込みは行っていない。`aas`（10 中 1 Step）/ `aad-web`（8 中 5 Step）のような混在 Workflow は対象外。
  - 判定根拠は Custom Agent プロンプト中の文字列一致であり、Workflow 単位へ粒度を上げることで誤判定の影響を避けている。

### FR-CLI-80 — CLI Autopilot の lane 経過時間観測

- 判定: 実装済み
- 受入テスト:
  - [hve/tests/test_autopilot_cli.py](hve/tests/test_autopilot_cli.py) :: `test_lane_over_the_threshold_emits_one_warning` / `test_lane_within_the_threshold_is_silent` / `test_threshold_matches_the_cloud_job_timeout` / `test_warning_failure_does_not_break_the_run`
- 受入ケース:
  - 閾値超過の lane に対して警告を 1 回だけ出す。→ ✓
  - 閾値内では警告を出さない。→ ✓
  - 警告の有無で `CliRunSummary` と成否が変わらない。→ ✓
  - 警告出力が例外を投げても実行を止めない。→ ✓
  - 閾値は 360 分（NFR-TIME-02 と同値）でハードコード。→ ✓
  - 経過時間は `clock` 引数で注入でき、実時間に依存しない。→ ✓
- RED / GREEN 証跡:
  - RED（実装前）: `ImportError: cannot import name 'LANE_WALL_CLOCK_WARN_SECONDS'`（実測）。
  - GREEN: `hve/tests/test_autopilot_cli.py` 11 passed。
- 既知の制約:
  - lane の停止は行わない。停止閾値を決める実測データが無いため（TBD-09 と同型）。
  - GUI Autopilot への警告表示は行わない（`[hve:stats]` の `kind` 追加は NFR-RTO-02 に抵触するため）。

### FR-PARAM-01 / 02 — AKM `sources` 正規化（不明トークン無視、順序固定）

- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_akm_sources_normalization.py](hve/tests/test_akm_sources_normalization.py) :: `TestNormalizeAkmSources`

### FR-PARAM-03 — 空入力 / None の既定値 `["qa","original-docs"]`
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_akm_sources_normalization.py](hve/tests/test_akm_sources_normalization.py) :: `TestNormalizeAkmSources`
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestBuildParams.test_akm_sources_default_when_not_specified`

### FR-PARAM-04 — `target_files` の既定値（sources により分岐）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_akm_sources_normalization.py](hve/tests/test_akm_sources_normalization.py) :: `TestDefaultAkmTargetFiles`
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestBuildParams.test_akm_target_files_default_*`（4 件）

### FR-PARAM-10 — ARD の未指定ステップを単一の既定tupleから解決
- 判定: 要追加（v2.43 改訂契約の RED 未作成）
- 追加予定テスト:
  - [hve/tests/test_ard_requirement_parity.py](hve/tests/test_ard_requirement_parity.py) — 要求表の既定tuple宣言とregistryの一致
  - [hve/tests/test_main_ard.py](hve/tests/test_main_ard.py) — 直接CLI / wizardの既定値と後方互換 `--include-kpi-okr`
  - [hve/tests/test_orchestrator_ard.py](hve/tests/test_orchestrator_ard.py) — 非対話fallbackの既定値とKPI/OKR正規化
- 既存責務境界:
  - グループ `3` / 実 Step `2.1` の明示選択を実効 `include_kpi_okr=True` へ正規化する既存処理は [hve/orchestrator.py](hve/orchestrator.py) `run_workflow` の `_kpi_step_selected_directly` 分岐が担う。C3/C4/C6で同じ正規化を重複実装せず、[hve/tests/test_orchestrator_ard.py](hve/tests/test_orchestrator_ard.py) の Step 2.1 include/excludeテストで維持する

### FR-PARAM-11 — ARD の調査条件既定値
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_orchestrator_ard.py](hve/tests/test_orchestrator_ard.py) :: `TestOrchestratorARD`
  - [hve/tests/test_main_ard.py](hve/tests/test_main_ard.py) — ARD 全体
  - [hve/tests/test_ard_target_business_resolver.py](hve/tests/test_ard_target_business_resolver.py) — `target_business` パス/テキスト解決全関数

### FR-PARAM-20 / 21 — APP-ID 自動選択（app-arch-catalog ベース）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_app_arch_filter.py](hve/tests/test_app_arch_filter.py) :: `TestResolveAppArchScope`
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestAppArchFilterInOrchestrator`
  - [hve/tests/test_workflow_app_arch_error_handling.py](hve/tests/test_workflow_app_arch_error_handling.py) :: `TestAppArchFilterErrorClassification`

### FR-GUI-01 — GUI Precheck の全 active step 評価
- 判定: ✓
- 直接対応テスト:
  - [hve/gui/tests/test_workflow_requirements_all_steps.py](hve/gui/tests/test_workflow_requirements_all_steps.py) :: `TestSummarizeAllRequirements` — 全 active step 評価、fan-out 子 ID 正規化、既定値ありキーの非報告、autopilot 時のファイル要件非復活、重複排除
  - [hve/gui/tests/test_workflow_requirements_all_steps.py](hve/gui/tests/test_workflow_requirements_all_steps.py) :: `TestPrecheckRunnerUsesAllSteps` — `run_step1_precheck` が Step 1.3 のパラメータ不足を検出
  - [hve/gui/tests/test_workflow_requirements_all_steps.py](hve/gui/tests/test_workflow_requirements_all_steps.py) :: `TestRequirementTableCoversRegistry` — `list_workflows()` の全ワークフローが `REQUIREMENT_TABLE` / `WORKFLOW_PRIORITY` に登録され、単独選択でも要件サマリーが 1 件以上返ること（RED: `aar` 欠落で 2 failed → GREEN: 22 passed / 12 subtests）
  - [hve/gui/tests/test_workflow_requirements_all_steps.py](hve/gui/tests/test_workflow_requirements_all_steps.py) :: `TestRequirementTableCoversRegistry.test_requirement_table_step_ids_exist_in_registry` — `REQUIREMENT_TABLE` の各エントリが `list_workflows()` 上に**実在する step ID** を指すこと（`ard` は GUI のグループ ID 方式、`autopilot` は疑似 ID のため除外）。ワークフロー単位の網羅性検査だけでは、登録済みでも実在しない step ID を指すエントリを検出できない（2026-08-20 の実測で `adfd` の `6.1` / `6.2` が該当し、当該ワークフローのバナーが 0 件だった）。RED: 新規テストが `[('adfd','6.1'), ('adfd','6.2')]` で失敗し、既存の `test_requirement_table_covers_every_registered_workflow` が `ada` 未登録で失敗（合計 2 failed / 7 passed）→ GREEN: 設定系を含む 9 ファイルで 130 passed / 13 subtests。修正後の実測では孤児エントリ 0 件・未登録ワークフロー 0 件・13 ワークフロー全てのバナー件数が 1

### FR-GUI-02 — 必須入力キーのレジストリ導出
- 判定: ✓
- 直接対応テスト:
  - [hve/gui/tests/test_workflow_requirements_all_steps.py](hve/gui/tests/test_workflow_requirements_all_steps.py) :: `TestRegistryRequiredParamKeys` — `INPUT_FIELD_KEYS` が静的キーとレジストリ宣言キーの和集合であること
  - [hve/gui/tests/test_workflow_requirements_all_steps.py](hve/gui/tests/test_workflow_requirements_all_steps.py) :: `TestBannerInputWidgetCoverage` — 監視対象ウィジェット表が `INPUT_FIELD_KEYS` を網羅
  - [hve/gui/tests/test_workflow_requirements_all_steps.py](hve/gui/tests/test_workflow_requirements_all_steps.py) :: `TestRegistryRequiredParamKeys::test_defaulted_params_are_excluded` — `default_params` を持つキー（ASDW-WEB Step 1.3 の `data_*` 5 件）が `registry_required_param_keys()` にも `INPUT_FIELD_KEYS` にも含まれないこと
  - [hve/gui/tests/test_workflow_requirements_all_steps.py](hve/gui/tests/test_workflow_requirements_all_steps.py) :: `TestRegistryRequiredParamKeys::test_precheck_and_field_derivation_share_one_helper` — 「GUI が可視化する必須キー」判定が単一実装であり、precheck 側（`_summarize_step_required_params`）と入力欄導出側（`registry_required_param_keys`）が同一の [hve/gui/workflow_step_requirements.py](hve/gui/workflow_step_requirements.py) `gui_visible_required_params()` を使うこと（FR-MAINT-07）
- 2026-08-20 の実測: 判定を「要確認（v2.14 改訂の対象キー縮約分は未検証）」から ✓ へ更新。当該 2 件は既に実装済みで、FR-GUI-03 / FR-GUI-06 / FR-WF-ASDW-02 の対応テストを含む 4 ファイル合計で 55 passed / 13 subtests。

### FR-GUI-03 — Azure 設定の永続化
- 判定: ✓
- 直接対応テスト:
  - [hve/gui/tests/test_settings_azure_persistence.py](hve/gui/tests/test_settings_azure_persistence.py) :: `TestAzureSettingsKeys` — 既定値・AZURE セクション表が対象キーを網羅
  - [hve/gui/tests/test_settings_azure_persistence.py](hve/gui/tests/test_settings_azure_persistence.py) :: `TestAzureSettingsRoundTrip` — 保存 → 復元で値が保持される
  - [hve/gui/tests/test_settings_azure_persistence.py](hve/gui/tests/test_settings_azure_persistence.py) :: `TestAzureSettingsKeys::test_defaulted_params_are_not_persisted` — 永続化対象が `default_params` を持たない `required_params`（= `resource_group`）だけであり、`data_*` 5 件が既定値・AZURE セクション表のいずれにも残らないこと
  - [hve/gui/tests/test_settings_azure_persistence.py](hve/gui/tests/test_settings_azure_persistence.py) :: `TestAzureSettingsKeys::test_defaulted_params_are_registered_as_obsolete` および `TestObsoleteAzureKeyMigration::test_saved_values_are_removed_on_load` — 廃止キー 5 件が `settings_store._OBSOLETE_KEYS["options"]` へ登録され、保存済みの値が load 時にファイルから除去されること
  - [hve/gui/tests/test_settings_azure_persistence.py](hve/gui/tests/test_settings_azure_persistence.py) :: `TestAzureSettingsRoundTrip::test_settings_path_is_isolated_from_the_real_store` — `setUp` で `settings_store.settings_path` を tmp へ差し替え、本テストが実ファイル [hve/.settings.txt](hve/.settings.txt) へ書き込まないこと
- 2026-08-20 の実測: 判定を「要確認（v2.14 改訂の対象キー縮約分は未検証）」から ✓ へ更新。当該 3 件は既に実装済みで、[hve/gui/settings_store.py](hve/gui/settings_store.py) の `_OBSOLETE_KEYS["options"]` に `data_location` / `data_resource_suffix` / `data_vnet_cidr` / `data_private_endpoint_subnet_cidr` / `data_aci_subnet_cidr` の 5 件が登録されていることを実測した。
- 2026-08-20 の追加対応（参照元の無いキーの除去）:
  - `settings_store.defaults()` に存在しながら GUI ・CLI のどちらからも設定できないキー（`app_id` / `tdd_max_retries` / `workbench_layout_state`）と、保存・復元の配線を持たない出力制御 9 キー（`log_level` / `timestamp_style` / `verbose` / `quiet` / `show_stream` / `no_color` / `banner` / `screen_reader` / `final_only`）を既定値から外し、`_OBSOLETE_KEYS` へ登録した。本要件の第 2 箇条（「UI から編集できないキーの値が設定ファイルに残り続ける」の禁止）の準用。
  - 検証: [hve/gui/tests/test_settings_store_migration.py](hve/gui/tests/test_settings_store_migration.py) / [hve/gui/tests/test_section_fields_defaults_consistency.py](hve/gui/tests/test_section_fields_defaults_consistency.py) / [hve/gui/tests/test_settings_output_controls_relayout.py](hve/gui/tests/test_settings_output_controls_relayout.py) を含む 9 ファイルで 130 passed / 13 subtests。出力制御の値は Step 1 右ペインまたは CLI フラグで都度指定する（実行時の argv 変換は変更していない）。

### FR-GUI-04 — GUI からの cq 索引運用

- 判定: ✓（独立 GUI 拡張の RED：`ModuleNotFoundError: No module named 'cq.gui'` / 配布ランチャー欠落で 9 failed。GREEN：standalone / HVE 互換 / スコープ / 翻訳 / `cq` コアの関連契約 458 passed）。FR-CQ-15 連動の言語別統計表示は追加済み（RED: `AttributeError: '_language_stats_table'` で 4 failed → GREEN: 4 passed）
- 対応テスト:
  - [hve/gui/tests/test_cq_standalone_gui.py](hve/gui/tests/test_cq_standalone_gui.py) — GREEN（9 件）。対象リポジトリ単位の設定パスと非所有セクション保持、standalone watcher 設定の永続化、対象パスを表示する独立ウィンドウ、HVE 互換 adapter が共有実装を継承すること、配布キットを上流 import path なしで起動できること
  - [hve/gui/tests/test_cq_index_service.py](hve/gui/tests/test_cq_index_service.py) — GREEN（15 件）。profile 一覧が設定ファイルの**宣言順**であること、索引未生成・設定不在・未知 profile のいずれでも `.cq/` を作成しないこと、設定不在で例外を送出せずエラー情報を返すこと、索引構築 → 統計取得の往復、差分ビルドの skip、DB パスが `cq.store.db_path_for` 由来であること、DB 削除、検索プレビューが `cq.search.Hit.to_dict()` の形をそのまま返すこと
  - [hve/gui/tests/test_cq_settings_section.py](hve/gui/tests/test_cq_settings_section.py) — GREEN（16 件）。3 タブ構成、`cq_watch` / `cq_watch_debounce_ms` の公開、debounce 既定値が `cq.watcher.DEFAULT_DEBOUNCE_MS` から実行時に導出されること（monkeypatch で検証）、profile コンボが宣言順であること、roots / exclude が読み取り専用であること、profile 選択の永続化、保存済み profile が未知・空のときの先頭 profile へのフォールバック、一括ビルドの全 uncheck 時に何もビルドしないこと、設定不在時の操作無効化と候補パス表示、skills レジストリ登録と `settings_apply` 経由の往復
  - [hve/gui/tests/test_settings_window_cq_persistence.py](hve/gui/tests/test_settings_window_cq_persistence.py) — GREEN（9 件）。`[cq]` 既定キー、watch キーが `[options]` 側にあること、`[options]` 保存で `[cq]` が消えないこと（更新順序 2 通り + ディスク上既存値）、`[mdq]` と `[cq]` の相互非破壊、`;` 区切りリストの単一実装
  - [hve/gui/tests/test_cq_watch_cli_bridge.py](hve/gui/tests/test_cq_watch_cli_bridge.py) — GREEN（11 件）。`--cq-watch` / `--no-cq-watch` / `--cq-watch-debounce-ms` の CLI 宣言と既定、`SDKConfig` 既定が `cq.watcher.DEFAULT_DEBOUNCE_MS` と一致すること、環境変数上書き、設定ストア値の CLI 引数への伝播、3 状態文字列の bool 正規化（mdq / cq 双方）、debounce 0 の未指定扱い、help エントリの存在
  - [cq/tests/test_index_stats.py](cq/tests/test_index_stats.py) — GREEN（5 件）。統計集計が `cq.store.index_stats` の単一実装であること、索引不在で 0 件を返さず送出すること、集計対象テーブルが実スキーマに存在すること、CLI 出力が単一実装の戻り値と一致すること、`cq/cli.py` に第 2 実装が残っていないこと（FR-MAINT-07）
  - [hve/gui/tests/test_i18n.py](hve/gui/tests/test_i18n.py) — GREEN。`translations.pro` への登録と `CqIndexSection` コンテキストの存在
  - [hve/gui/tests/test_cq_settings_section.py](hve/gui/tests/test_cq_settings_section.py) :: `TestLanguageStats` — GREEN（4 件、FR-CQ-15 連動）。言語別統計テーブルの列構成、索引済み言語がパーサ別に合算されず行として並ぶこと、同一パーサを共有する言語が分離されること、索引未生成時に表が空のまま `.cq/` を作らないこと
- 受入ケース:
  - 独立 GUI は明示された別リポジトリを対象に起動でき、操作対象の絶対パスを表示する。
  - HVE 組み込み版と独立版は同一の管理セクション・索引操作サービス・バックグラウンド処理を使用する。
  - 独立版設定は対象リポジトリごとに分離され、保存時に非所有セクション・キーを消去しない。
  - 配布キットは同期済み `vendor/cq/` から上流 HVE import path なしで管理機能をロードできる。
  - GUI は profile 選択・索引統計・差分更新・完全再ビルド・索引 DB 削除・リアルタイム更新設定を提供する。
  - GUI は索引ルート・除外パターン・最大ファイルサイズを読み取り専用で表示し、書き換えない。
  - 設定ファイルが存在しない場合、GUI は既定 profile を推測せず、索引操作を無効化して設定ファイル候補を表示し、異常終了しない。
  - GUI は索引 DB のパスを `cq` の profile → DB パス解決から取得し、独自のパス規則を持たない。
  - 索引未生成 profile の統計表示で、索引ディレクトリと索引 DB を新規作成しない。
  - `[options]` セクションの保存で `[cq]` セクションの値が消えない。
  - リアルタイム索引更新の有効・無効と debounce 間隔が CLI 引数へ伝播する。
  - GUI は FR-CQ-15 の言語別内訳を表示し、言語・ファイル数・シンボル数・チャンク数・パーサ別ファイル数を識別できる。パーサ別集計だけを表示しない。→ ✓
- 実測: 実リポジトリでのセクション構築 215 ms、profile=hve の統計 `files=727 / symbols=13,072 / chunks=12,939 / refs=68,588 / imports=5,759 / traces=843 / ast=673, lite=54 / schema v2`。英語ロケールでタブが `Basic / Index management / Search quality` と表示されることを実測。
- 既知の制約:
  - CLI orchestrator の `CqWatcher` は設定ファイルで**最初に宣言された profile** のみを監視する。GUI で選択中の profile は CLI へ伝播しない。
  - 配布用 `vendor/cq/` は生成物だが版管理下に置き、コピーだけで起動できるようにする（FR-KIT-01）。上流との byte 一致は [hve/tests/test_cq_vendor_sync.py](hve/tests/test_cq_vendor_sync.py) が検証する。
  - 外部リポジトリには HVE 用 `cq/golden-queries.json` が存在せず、任意 profile を現行評価器が受理しないため、独立 GUI の検索品質ベンチマークは利用不可として明示的に無効化する。索引管理と試し検索には影響しない。

### FR-GUI-05 — GUI からの mdq 索引運用（単一実装共有）

- 判定: ✓（単一実装共有の初版は RED：`ModuleNotFoundError: No module named 'mdq.gui'` 等で 11 failed → GREEN：100 passed。v2 で追加した「統計取得の非作成」「strategy 別索引実体の構築」条項は RED：18 failed → GREEN：`mdq/gui/tests/` 52 passed + mdq 関連 HVE 側 60 passed）
- 対応テスト:
  - [hve/tests/test_mdq_gui_single_implementation.py](hve/tests/test_mdq_gui_single_implementation.py) — GREEN（12 件）。共有サービスの統合 API、`rebuild_index` が `pageindex_options` と `semantic_options` の両方を受けること、`resolve_effective_roots` の第一引数が `repo_root` であること、HVE 側が再エクスポートのみで第 2 実装を持たないこと、`hve/gui/settings_window.py` が配布キットを import しないこと、`SettingsBackend` 注入、HVE adapter が共有セクションを継承すること
  - [hve/gui/tests/test_mdq_strategy_features.py](hve/gui/tests/test_mdq_strategy_features.py) — GREEN
  - [hve/gui/tests/test_settings_window_mdq_tabs.py](hve/gui/tests/test_settings_window_mdq_tabs.py) — GREEN
  - [mdq/gui/tests/test_mdq_index_service_ops.py](mdq/gui/tests/test_mdq_index_service_ops.py) / [test_settings_section_phase3.py](mdq/gui/tests/test_settings_section_phase3.py) / [test_search_preview_panel.py](mdq/gui/tests/test_search_preview_panel.py) / [test_semantic_options.py](mdq/gui/tests/test_semantic_options.py) / [test_settings_store_semantic.py](mdq/gui/tests/test_settings_store_semantic.py) / [test_extras_status.py](mdq/gui/tests/test_extras_status.py) — GREEN
  - [mdq/gui/tests/test_mdq_index_service_ops.py](mdq/gui/tests/test_mdq_index_service_ops.py) — GREEN（11 件）。`get_index_stats` が索引 DB 未存在時にファイルを新規作成せず `db_exists=False` を返すこと、`.mdq/` ディレクトリ自体も作らないこと、`delete_index_db` 直後の統計取得が索引を再生成しないこと、単一統計と strategy 別統計の未生成表現が一致すること
  - [mdq/gui/tests/test_mdq_index_service_graphrag.py](mdq/gui/tests/test_mdq_index_service_graphrag.py) — GREEN（19 件）。`rebuild_index(strategy="graphrag")` が `mdq.indexer.build_graphrag_index` を呼び `build_index` を呼ばず SQLite 索引を生成しないこと、`force` が LightRAG の `rebuild` へ伝播すること、進捗コールバックが転送されること、CLI と GUI が `mdq.store.graphrag_dir_for` を単一情報源とすること、`ALL_STRATEGIES` 全 6 件で当該 strategy の索引実体が生成されること、graphrag 行が LightRAG 作業ディレクトリを存在判定に用いファイル数・チャンク数を 0 と表示しないこと、空の作業ディレクトリや失敗したビルドの残存ディレクトリを構築済みと判定しないこと、LightRAG 索引の判定規則が `mdq.indexer.has_lightrag_index` の単一実装であること、任意依存未導入時に失敗が伝搬され空の索引を残さないこと
  - [mdq/tests/test_search_graphrag.py](mdq/tests/test_search_graphrag.py) — GREEN（13 件、`[graphrag]` extra 導入時のみ実行）。索引の存在判定に使うマーカーが LightRAG の実生成物と一致すること、同一プロセスでの完全再ビルドが索引ファイルを失わないこと、`kv_store_doc_status.json` の状態集計が失敗文書を成功として数えないこと、索引が無い作業ディレクトリでも例外にせず空を返すこと、ビルド要約が `documents_processed` / `documents_failed` を持つこと、CLI 既定タイムアウトが `GraphRAGConfig` 既定値と乖離しないこと
  - [mdq/tests/test_strategies_graphrag.py](mdq/tests/test_strategies_graphrag.py) — GREEN（23 件、`[graphrag]` extra 導入時のみ実行）。セッション開始時に LLM を 1 度呼びモデル読み込みを前倒しすること、LLM 呼び出しと文書処理の同時実行数を Ollama の直列処理へ揃えること（`llm_model_max_async=1` / `max_parallel_insert=1`）、mdq のタイムアウト設定が LightRAG の実行タイムアウト（`default_llm_timeout` / `default_embedding_timeout`）へ伝播すること
  - [mdq/gui/tests/test_graphrag_options.py](mdq/gui/tests/test_graphrag_options.py) — GREEN（7 件）。GUI 既定値がコード側の単一情報源と乖離しないこと、設定値 0 がコード既定を上書きしないこと、明示値がそのまま実行設定へ渡ること、`rebuild_index` が GUI の設定を graphrag の実行設定へ届けること、ウィジェットの往復変換、graphrag 選択時のみ設定が表示されること
- 受入ケース:
  - 独立版と HVE 組み込み版が同一の管理セクション・索引操作サービス・バックグラウンド処理を使用する。→ ✓
  - 依存方向が HVE → `mdq` の一方向である。→ ✓
  - HVE 版と独立版で提供機能に差がない。→ ✓（`get_index_stats_all_strategies` と `pageindex_options` の双方を共有実装へ統合）
  - 索引未生成の strategy の統計取得が索引 DB / 索引ディレクトリを新規作成しない。→ ✓
  - GUI からの索引構築が全 chunking strategy について CLI と同一の構築実装を用い、`graphrag` を SQLite 索引経路へフォールバックさせない。→ ✓
  - strategy 別統計の索引存在判定が当該 strategy の索引実体を対象とする。→ ✓
  - ディレクトリを索引実体とする strategy で、空のディレクトリを構築済みと判定しない。→ ✓
  - 索引構築の結果表示が索引エンジンの記録した実結果を反映し、文書単位の失敗件数を識別できる。→ ✓（実測 2026-08-14: `template/` 5 ファイルのビルドで、旧指標は `files_ok=5 / files_error=0` を示す一方、`documents_processed=1 / documents_failed=4` が実態を提示した）
  - 索引構築の成否を左右する strategy 固有パラメータを GUI から調整でき、既定値をコード側と二重管理しない。→ ✓
- 解消した制約（実装前の実測）:
  - `hve/gui/mdq_index_service.py` と `tools/skills/markdown_query/gui/mdq_index_service.py` が並存し、`git diff --no-index` で 157 行の差分があった。前者のみ `get_index_stats_all_strategies`、後者のみ `pageindex_options` を持っていた。
  - （v2、2026-08-13 実測、リポジトリ `.mdq/`）`mdq.indexer.build_graphrag_index` の呼び出し元が `mdq/cli.py` の 1 箇所のみで、GUI 経路は SQLite 索引パイプラインへフォールバックしていた。結果 `index-ja-jp-graphrag.sqlite` に 110 files / 0 chunks の SQLite が生成され、本来の `.mdq/graphrag-ja-jp/` は存在しなかった。
  - （v2、2026-08-13 実測）`get_index_stats` が無条件に `mdq.store.open_store` を呼ぶため、GUI 起動・Strategy 切替・DB 削除直後の統計再描画で空の DB ファイルが生成された。`index-ja-jp-heading_recursive.sqlite`（64 KB / 0 files / 0 chunks）がこの経路で作られ、strategy 別統計表に「DB 有り 0/0」と表示されていた。

### FR-GUI-06 — Step 1 右ペインの必須入力欄表示と永続化

- 判定: ✓（初版の RED: 表示 3 failed / 永続化 3 failed、GREEN: 対象 7 passed、影響範囲 44 ファイル 370 passed）
- 直接対応テスト:
  - [hve/gui/tests/test_workflow_required_input_fields.py](hve/gui/tests/test_workflow_required_input_fields.py) — GREEN（3 件）。必須入力キーごとの入力欄が当該ワークフロー枠の中に配置されること、`_STEP2_FIELDS_BY_WORKFLOW` の全エントリが実在する入力欄へ解決できること、固有入力欄を他に持たない `aagd` でも枠が生成されること
  - [hve/gui/tests/test_options_page_required_input_persistence.py](hve/gui/tests/test_options_page_required_input_persistence.py) — GREEN（4 件）。全必須入力キーが `_SECTION_FIELDS` に保存先を持つこと、右ペインの入力が設定ストアの `[options]` へ保存されること、`[mdq]` / `[cq]` セクションを破壊しないこと、保存済みの値が `MainWindow` の起動時経路で右ペインへ復元されること
  - [hve/gui/tests/test_workflow_required_input_fields.py](hve/gui/tests/test_workflow_required_input_fields.py) :: `TestRequiredInputFieldsInWorkflowBox::test_defaulted_params_have_no_input_field` — 対象キー導出が `default_params` を持つキーを除外し、ASDW-WEB 枠に `resource_group` の入力欄のみが要求されること。同テストが `getattr(page.c_azure, key, None) is None` で `_CAzure` に `data_*` ウィジェットが残っていないことも固定する
  - [hve/gui/tests/test_orchestrate_args.py](hve/gui/tests/test_orchestrate_args.py) :: `TestDataDeployBootstrapToArgv::test_gui_does_not_emit_bootstrap_flags` / `::test_bootstrap_fields_are_not_declared` — `to_argv()` に `--data-*` が現れず、`OrchestrateArgs` に当該 5 フィールドが宣言されないこと
- 受入ケース:
  - `REQUIREMENT_TABLE` の `required_info_keys` と `StepDef.required_params`（`default_params` を持たないものに限る）の和集合に含まれる全キーについて、対応する入力欄が当該ワークフローの枠へ移設される。→ ✓（`TestRequiredInputFieldsInWorkflowBox::test_each_workflow_shows_its_required_input_fields`）
  - 表示対応表に、実在する入力欄へ解決できないエントリが 0 件である。→ ✓（`TestRequiredInputFieldsInWorkflowBox::test_no_unresolvable_field_entries`）
  - 右ペインで入力した必須入力キーの値が設定ストアへ保存され、次回起動時に復元される。→ ✓
- 2026-08-20 の実測: 判定を「要確認（v2.14 改訂の対象キー縮約分は未検証）」から ✓ へ更新。当該 2 件は既に実装済みで、うち `_CAzure` の `data_*` ウィジェット非存在と `--data-*` 非出力は当初想定した `test_page_options_github_cicd.py` ではなく上記 2 ファイルが固定していた。重複テストは追加しない（FR-MAINT-07）。
- 2026-08-20 の追加対応（実在しないウィジェットを指すエントリの除去）:
  - `settings_apply._SECTION_FIELDS["C10"]["app_id"]` は `page_options._C10AppId` に存在しない属性を指しており（実測: `hasattr(_C10AppId(), "app_id") == False` / `app_ids` のみ実在）、`getattr(..., None)` で読み飛ばされる死参照だった。本要件の「表示対応表に、実在しない入力欄を指すエントリを残してはならない」と同旨の整理として当該エントリを削除した。
  - 対となるテストは [hve/gui/tests/test_settings_apply_sources_persistence.py](hve/gui/tests/test_settings_apply_sources_persistence.py) :: `test_c10_section_has_no_app_id_entry`（旧 `test_c10_section_has_no_duplicate_app_id_entries` は `count("app_id") == 1` を固定していたため、重複混入防止の意図を保ちつつ `"app_id" not in fields` へ改訂）。
- 解消した制約（実装前の実測、2026-08-03、`OptionsPage` を offscreen で生成して確認）:
  - 未表示 3 件: `ard` step 1 の `company_name`（表示対応表に未登録）、`adfdv` step 1.1 の `resource_group`（`c10` と誤登録され解決不能）、`aagd` step 1 の `resource_group`（表示対応表に `aagd` エントリ自体が無く枠が生成されない）。
  - 解決不能エントリ 2 件: `('c_azure','DataDeploy verify ACI image')` と `('c10','Azure リソースグループ名')`。
  - [hve/gui/page_options.py](hve/gui/page_options.py) に `settings_store.save` / `set_option` の呼び出しが 0 件で、右ペイン入力は設定ストアへ保存されなかった。
- 残存する制約（実装後の実測）:
  - 設定ウィンドウを開いたまま Step 1 右ペインの必須入力を編集し、その後に設定ウィンドウ側で autosave が発火すると、右ペインの編集が設定ウィンドウを開いた時点の値へ巻き戻る。設定ウィンドウは非表示のたびに再生成される（[hve/gui/main_window.py](hve/gui/main_window.py) `_open_settings_window`）ため、通常の開閉フローでは発生しない。

### FR-GUI-07 — GUI 設定画面の Tool-Search セクション

- 判定: ✓（`policy.json` の GUI 編集分は RED: 保存 API 7 failed / GUI 16 failed の計 23 failed。GREEN: 対象 2 ファイル 99 passed、Tool Search 全体 354 passed）
- 直接対応テスト:
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) — タブ構成、`settings_apply` が束ねる `tool_search` / `tool_search_ranking` の公開、skills レジストリへの登録
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_autopilot_section_no_longer_owns_tool_search` / `test_step1_pane_has_no_duplicate_input` — 入力欄の単独所有（FR-MAINT-07）
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_unreadable_policy_does_not_fabricate_defaults` — `policy.json` を読めないときに既定値を推測しないこと
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_gui_does_not_reimplement_aggregation` — 集計・整形を GUI 側で再実装しないこと（FR-MAINT-07）
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_empty_store_shows_no_data_rather_than_zero` / `test_reload_tolerates_a_broken_store` / `test_clear_events_tolerates_a_missing_store` — データ不足の明示と失敗の握り潰し
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_skill_layer_view_shows_manifest_summary` / `test_extend_lists_discovered_skills_not_just_explicit_pins` — Skill レイヤーの閲覧専用表示
  - [hve/tests/test_toolsearch_wiring.py](hve/tests/test_toolsearch_wiring.py) :: `TestGuiWidget` — 設定画面が入力欄の単独所有者であり、Step 1 右ペインは保存値をブリッジするだけであること
  - [hve/tests/test_toolsearch_policy.py](hve/tests/test_toolsearch_policy.py) :: `TestSave.test_to_dict_round_trips_through_from_dict` / `test_round_trip_preserves_every_field` / `test_preserves_unknown_top_level_keys` / `test_writes_lf_without_bom` / `test_keeps_non_ascii_readable` / `test_invalid_payload_raises_and_leaves_the_file_untouched` / `test_invalid_key_is_rejected_before_writing` / `test_broken_existing_file_is_not_silently_overwritten` — `policy.json` 保存 API の往復一致、`_comment` 保持、改行・BOM、検証失敗時と既存ファイル破損時の fail-closed
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_policy_tab_exposes_editable_scalars` / `test_policy_tab_exposes_editable_field_weights` / `test_policy_tab_exposes_editable_tables` — `limit` / `max_limit` / `tau` / `field_weights` / `pins` / `additional_search_text` / `step_overrides` を編集できること
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_version_is_displayed_but_not_editable` — `version` を編集させないこと
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_save_writes_the_displayed_path` / `test_save_preserves_unknown_top_level_keys` / `test_table_edits_are_saved` — 表示元と同一パスへ保存し、未知キーを失わず、表の編集が書き戻されること
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_invalid_key_is_not_saved_and_reports_why` / `test_limit_above_max_limit_is_not_saved` / `test_save_is_blocked_while_the_policy_is_unreadable` / `test_save_failure_does_not_crash_the_gui` — 検証失敗・読み込み失敗・書き込み失敗時にファイルを壊さず GUI を落とさないこと
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_save_result_states_when_it_takes_effect` — 反映タイミング（次の Step 実行から）を表示すること
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_untouched_decimals_are_not_rounded_on_save` — 入力欄の桁数で既存の `tau` / `field_weights` を丸めて保存しないこと
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_reload_discards_unsaved_edits` — 再読み込みで未保存の編集を破棄すること
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_every_policy_field_has_a_hint` / `test_policy_hints_come_from_help_content` — 全編集項目に説明ヒントがあり、文言の単一の情報源が `help_content` であること（FR-MAINT-07）
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_editor_choices_match_the_validator` — GUI の選択肢集合（`field_weights` の 4 項目・pin の 3 値・Step の 2 値）が [hve/toolsearch/policy.py](hve/toolsearch/policy.py) の検証集合と乖離しないこと（FR-MAINT-07）
  - [hve/gui/tests/test_i18n.py](hve/gui/tests/test_i18n.py) :: `TestAssets.test_toolsearch_settings_section_is_translated` / `test_toolsearch_policy_hints_are_translated` / `test_compiled_catalog_is_not_stale` — セクションとポリシー説明が翻訳カタログに登録され、`.qm` が stale でないこと
- 直接対応テスト（計画・要追加）:
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_basic_tab_states_that_deferral_does_not_fire` — 基本タブが遅延公開の非発火を実測日・CLI 版つきで明示する
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_basic_tab_warns_hve_ranking_increases_context` — `hve` ランキングがコンテキストを増やすことを明示する
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_empty_stats_reports_disabled_tool_search_as_unmet` / `test_empty_stats_reports_sdk_ranking_as_unmet` — イベント 0 件時に、設定値から判定できる未充足条件を表示する
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_empty_stats_does_not_assert_an_unobserved_cause` — 設定条件が揃っているときは観測していない原因を断定しない
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_stats_diagnosis_is_silent_when_events_exist` — イベントがあるときは診断を出さない
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_policy_tab_shows_a_legend_for_pin_modes_and_thresholds` — `always` / `auto` / `never`・`limit`・`tau` の凡例と参照先
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_has_five_tabs` / `test_tab_labels` — コンテキスト内訳タブを含む 5 タブ構成
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_context_tab_does_not_measure_until_requested` — タブを開いただけでは実測しない
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_context_tab_renders_the_cli_payload_without_reaggregating` — CLI 出力を GUI で再集計しない（FR-MAINT-07）
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_context_tab_reports_failure_without_fabricating` — 実測失敗時に推定値や前回値で埋めない
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_context_measurement_uses_the_cli` — ボタンからの実経路（ワーカー）で CLI を呼ぶ
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_opening_the_context_tab_does_not_load_stats` — 統計の遅延読み込みがタブ位置に依存しない
  - [hve/gui/tests/test_toolsearch_settings_section.py](hve/gui/tests/test_toolsearch_settings_section.py) :: `test_skill_layer_tab_states_that_extend_depends_on_the_cli` — Extend が実際に遅延公開されるかは CLI 側実装に依存する旨を併記する
- 受入ケース:
  - `tool_search` / `tool_search_ranking` の入力欄が設定画面にのみ存在し、設定ストアの `[options]` へ永続化されて CLI 引数へ伝播する。→ ✓
  - `policy.json` を読み込み失敗時に推測既定値で表示しない。→ ✓
  - `policy.json` を GUI から編集し、表示元と同一パスへ検証済みの値だけを保存する。検証失敗時はファイルを変更しない。→ ✓
  - 各編集項目に初見の利用者向け説明を表示し、文言を `help_content` で一元管理する。→ ✓
  - 本セクションの表示文字列とポリシー説明が翻訳カタログへ登録され、`.qm` が stale でない。→ ✓
  - 統計の集計・整形は `hve/toolsearch/stats.py` / `dashboard.py` のみが所有する。→ ✓
  - 収集済みイベントが無い指標を 0 で埋めない。統計の読み込み・削除の失敗で異常終了しない。→ ✓
  - 設定項目の説明が当該環境の実挙動と食い違わない。→ 要追加
  - イベント 0 件時に未充足の収集条件を表示し、観測していない原因を断定しない。→ 要追加
  - コンテキスト内訳を実測で表示し、推定値で代替せず、明示操作時にのみ実行する。→ 要追加
- 実装後の判断（敵対的レビュー反映）:
  - 統計はタブを開いたときにだけ読み込む。イベントログは無制限に伸びるため、設定画面を開くだけで全件読むと待たされる。
  - 「収集済みイベントを削除」は不可逆なので確認ダイアログを挟む。テスト用 API `clear_events()` はダイアログを持たない。
  - `policy.json` の保存は明示ボタンとし、設定画面の他項目と同じ autosave にしない。`from_dict()` が `limit <= max_limit`・キー書式・pin 値を全件検証するため、表の編集途中の中間状態を自動保存すると毎操作で検証エラーになる。
  - `limit` と `max_limit` の入力欄を相互に連動させない。連動させると `limit > max_limit` の入力が黙って丸められ、検証の fail-closed を観測できなくなる。
  - `save()` は既存ファイルを読んでトップレベルの既知キーだけを差し替える。既存ファイルが JSON として壊れている場合は未知キーの保持を保証できないため、書き込まず `PolicyError` を送出する。
  - GUI の選択肢集合と `policy.py` の検証集合の一致をテストで固定する。片方だけ変更すると、GUI の入力が保存時に必ず失敗するか、検証側が受け付ける値を GUI から選べなくなる。
  - 小数入力欄の桁数を固定しない。`QDoubleSpinBox` は `decimals` で値を量子化するため、2 桁固定だと `tau: 0.456` を編集せずに保存しただけで `0.46` へ黙って書き換えてしまう（実測で確認）。読み込んだ値を丸めずに表示できる桁数へ広げてから入れる。
  - 翻訳は `.ts` だけでは完結しない。実行時に読まれるのは `.qm` のため、`pyside6-lupdate` の後に `pyside6-lrelease` を必ず実行する。検査は mtime 比較ではなく、`.qm` を実際にロードして翻訳結果を見る（clone 直後は mtime が保存されず偽陽性になるため）。
- 既知の制約:
  - GUI から保存すると `policy.json` 内の空行が失われる。JSON に空行を表現する構文が無いためで、値と未知キーは保持される。空行を含む整形を保ちたい場合はファイルを直接編集する。
  - `hve/gui/tests/test_settings_window_mdq_tabs.py` は本変更以前から単独実行でもプロセスが異常終了する（`MdqIndexSection` 単体構築で `QThread: Destroyed while thread '' is still running` を実測）。本要件の範囲外のため未修正。GUI 全体の実行結果は当該ファイルを除外して計測した。

### FR-GUI-08 — GUI 質問票の「その他」回答

- 判定: ✓（RED: `QAAnswerDialog` に「その他」がなく 5 failed。GREEN: ダイアログ、IPC、マージの対象 suite 27 passed）
- 直接対応テスト:
  - [hve/gui/tests/test_qa_answer_dialog.py](hve/gui/tests/test_qa_answer_dialog.py) :: `TestQAAnswerDialog.test_choice_question_appends_other_option`、`test_selecting_other_enables_freetext_and_serializes_it`、`test_answer_column_reserves_freetext_width`、`test_structured_other_default_is_editable`、`test_other_text_default_is_editable`、`test_switching_from_other_back_to_choice_uses_label_serialization`、`test_existing_other_choice_is_not_duplicated_and_serializes_freetext`、`test_choice_starting_with_other_remains_a_regular_choice`、`test_empty_other_freetext_is_omitted`
  - [hve/gui/tests/test_qa_ipc_flow.py](hve/gui/tests/test_qa_ipc_flow.py) :: `TestQAIpcFlow.test_other_freetext_round_trip`
  - [hve/tests/test_qa_merger.py](hve/tests/test_qa_merger.py) :: `TestMergeOtherFreeText.test_other_freetext_is_persisted_in_output_file`、`test_empty_other_freetext_falls_back_to_default`

### FR-GUI-09 — 通常セットアップによる `gh` / OS 別 PTY backend 構築

- 判定: 実装済み
- 受入テスト:
  - [hve/tests/test_dev_task_environment_contract.py](hve/tests/test_dev_task_environment_contract.py) :: `test_normal_gui_setup_installs_gh_and_platform_pty_backend`、`test_normal_gui_setup_fails_closed_when_gh_or_pty_is_missing`、`test_normal_gui_setup_repairs_existing_venv_without_force`、`test_no_gui_and_minimal_remain_explicit_opt_outs`、`test_check_only_audits_gui_prerequisites_without_changing_anything`、`test_setup_does_not_run_gh_auth_login_or_reject_unauthenticated_status`、`test_posix_setup_script_is_executable`、`test_ci_verifies_the_pty_backend_on_every_supported_os`
  - [hve/tests/test_pty_backend.py](hve/tests/test_pty_backend.py) :: `test_missing_dependency_hint_recommends_platform_setup`、`test_setup_command_resolves_the_real_script_from_any_cwd`、`test_setup_command_falls_back_to_relative_path_when_script_is_absent`、`test_platform_backend_is_available_for_normal_gui_setup`
  - [hve/tests/test_gui_imports.py](hve/tests/test_gui_imports.py) :: `TestGuiDependencyGuidance.test_missing_gui_extra_recommends_setup_and_real_launcher`
  - [hve/gui/tests/test_gh_login_dialog.py](hve/gui/tests/test_gh_login_dialog.py) :: `test_gh_missing_shows_guidance_and_no_spawn`、`test_pty_unavailable_guidance_recommends_platform_setup`、`test_available_path_spawns_gh_login`
  - [hve/gui/tests/test_i18n.py](hve/gui/tests/test_i18n.py) :: `TestAssets.test_gh_login_dialog_is_translated`
- 受入ケース:
  - 隔離ハーネス上で `hve/setup-hve.sh` / `hve/setup-hve.ps1` をオプションなし実行すると、`gh` を解決したうえで共有 `is_pty_available()` を実行し、`gui-pty` を含む editable install が走る。→ ✓（実測: 上記 4 シナリオとも exit 0）
  - 通常 GUI 構成で `gh` を解決できない場合、または PTY 判定が利用不可の場合は非ゼロ終了する。→ ✓
  - `--no-gui` / `--minimal`（`-NoGui` / `-Minimal`）では `gui-pty` 導入も PTY 判定も実行しない。→ ✓
  - `--check-only` / `-CheckOnly` は `.venv` 作成も pip install も行わず、`gh` 不在と PTY 利用不可を警告として報告し exit 0 を維持する。→ ✓
  - 未認証の `gh auth status` でセットアップは失敗せず、`gh auth login` を実行しない。→ ✓
  - 復旧案内はリポジトリ外の CWD からでも実行できる絶対パスを返し、setup スクリプトが同居しない配置では相対表記へ退避する。→ ✓
  - GUI 依存未導入時の起動案内は OS 別 setup を `pip install` より先に提示し、実在ランチャー（`hve.cmd gui` / `./hve.sh gui`）を案内する。→ ✓
  - `git ls-files --stage hve/setup-hve.sh` が `100755` である。→ ✓
  - `.github/workflows/test-hve-python.yml` の `gui-pty-tests` job が windows / macos / ubuntu の 3 OS で `gui-pty` を導入し、`is_pty_available()` を fail-closed で確認したうえで `hve/tests/test_pty_backend.py` を skip 0 件で実行する。→ ✓（YAML 構文と job 定義をローカル検証。実 runner 実行は CI 側で確認）
- 既知の制約:
  - PowerShell 側のハーネスは `pwsh` 7+ が無い環境では実行されない（`_run_powershell_setup` が `None` を返す）。Linux CI では shell 版のみ検証される。
  - Git for Windows の Bash は NTFS 上に作成したテスト用 shebang スクリプトを `[[ -x ]]` と認識しないため、Windows ホストでは shell ハーネスの「既存 venv」判定が成立しない。当該観点は Linux CI の同一ハーネスと PowerShell ハーネスで担保する。
  - shell ハーネスは `uname` を `Darwin` に固定しているため、Linux 固有分岐（Qt system libs 導入）は本要件のテスト対象外。

### FR-GUI-10 — 埋め込み Copilot CLI 対話セッション

- 判定: 実装済み
- 受入テスト:
  - [hve/gui/tests/test_copilot_interactive_session.py](hve/gui/tests/test_copilot_interactive_session.py) :: `test_start_spawns_one_interactive_process`、`test_start_while_running_does_not_spawn_again`、`test_user_input_is_forwarded_to_the_same_process`、`test_resize_is_forwarded_to_the_same_process`、`test_restart_after_stop_spawns_a_new_process`、`test_missing_binary_fails_closed_with_setup_guidance`、`test_missing_pty_backend_fails_closed_with_setup_guidance`、`test_reader_does_not_poll_on_the_gui_thread`
  - [hve/gui/tests/test_copilot_chat_panel.py](hve/gui/tests/test_copilot_chat_panel.py) :: `test_panel_does_not_spawn_a_one_shot_prompt_process`、`test_starting_the_cli_session_uses_the_persistent_session`、`test_primary_controls_are_reachable_and_named_for_assistive_tech`
  - [hve/tests/test_copilot_cli_pty_smoke.py](hve/tests/test_copilot_cli_pty_smoke.py) :: `test_resolved_copilot_binary_reports_version_through_a_real_pty`、`test_arguments_are_passed_as_a_list_without_shell_interpretation`
  - [hve/tests/test_dev_task_environment_contract.py](hve/tests/test_dev_task_environment_contract.py) :: `test_ci_smoke_tests_the_interactive_copilot_cli_on_every_supported_os`
- 受入ケース:
  - 複数ターン送信で対話プロセスが 1 個のまま維持される。→ ✓
  - CLI 出力を HVE が解釈してチャット UI を再構成しない。→ ✓（端末ビューへ透過し、`QProcess` 経路を持たない）
  - CLI バイナリ解決が `hve/gui/copilot_cli_bridge.py` の規則だけを使う。→ ✓
  - CLI / PTY backend 不在時に fail-closed で OS 別セットアップを案内し、非対話モードへフォールバックしない。→ ✓
  - 3 OS の実 PTY で解決済み CLI が起動・終了する。→ ✓（Windows で実測。macOS / Linux は CI の `gui-pty-tests` job で確認）
- 既知の制約:
  - `copilot` が解決できない開発環境では smoke が skip する。CI はランタイム先読みと
    skip 0 件の検査で fail-closed にする（`test_pty_backend.py` と同じ方式）。

### FR-GUI-11 — 汎用チャットの権限と起動安全性

- 判定: 実装済み
- 受入テスト:
  - [hve/gui/tests/test_copilot_interactive_session.py](hve/gui/tests/test_copilot_interactive_session.py) :: `test_build_argv_never_grants_blanket_permissions`、`test_build_argv_runs_in_repo_root_and_pins_runtime`、`test_build_argv_uses_interactive_prompt_flag_not_oneshot`、`test_build_argv_keeps_prompt_as_single_argument`、`test_build_argv_omits_prompt_flag_when_prompt_is_blank`
  - [hve/gui/tests/test_copilot_chat_panel.py](hve/gui/tests/test_copilot_chat_panel.py) :: `test_panel_does_not_spawn_a_one_shot_prompt_process`
  - [hve/tests/test_copilot_cli_pty_smoke.py](hve/tests/test_copilot_cli_pty_smoke.py) :: `test_arguments_are_passed_as_a_list_without_shell_interpretation`
- 受入ケース:
  - 汎用チャットの argv に権限緩和フラグが含まれない。→ ✓
  - 作業ディレクトリとしてリポジトリルートが渡る。→ ✓
  - 利用者入力がシェルコマンドへ連結されない。→ ✓（実 PTY でメタ文字が解釈されないことを実測）
  - Step 実行セッションの権限方針が変更されない。→ ✓（`hve/runner.py` の permission handler は未変更）

### FR-GUI-12 — 実行中ジョブへの queue / steer / stop_and_send

- 判定: 実装済み
- 受入テスト:
  - [hve/gui/tests/test_job_interaction_ipc.py](hve/gui/tests/test_job_interaction_ipc.py) :: `test_actions_are_the_three_vs_code_style_actions`、`test_write_request_matches_runner_polling_glob`、`test_write_request_leaves_no_temp_file`、`test_consecutive_requests_get_unique_files`、`test_cancel_of_claimed_request_is_rejected`、`test_reorder_does_not_duplicate_or_drop_requests`、`test_second_claim_of_the_same_request_fails`、`test_ack_never_contains_the_prompt_text`、`test_legacy_text_only_request_is_treated_as_steer`
  - [hve/tests/test_runner_job_interaction_ipc.py](hve/tests/test_runner_job_interaction_ipc.py) :: `test_queue_is_sent_as_enqueue`、`test_steer_is_sent_as_immediate`、`test_stop_and_send_aborts_and_defers_the_text_to_a_new_turn`、`test_stop_and_send_becomes_the_main_response`、`test_stop_and_send_is_acknowledged_only_after_the_new_turn_is_sent`、`test_dropped_stop_and_send_is_acknowledged_as_failed`、`test_model_call_failure_during_the_redirect_turn_fails_fast`、`test_accepted_ack_is_written_without_the_prompt`、`test_each_request_is_consumed_exactly_once`
  - [hve/tests/test_runner_steering_ipc.py](hve/tests/test_runner_steering_ipc.py) :: `TestPollSteeringIpcEnabled`、`TestSendAndWaitGuardWithSteering`
  - [hve/gui/tests/test_copilot_chat_panel.py](hve/gui/tests/test_copilot_chat_panel.py) :: `test_send_writes_the_selected_action`、`test_ack_is_surfaced_to_the_operator`、`test_oversized_input_is_rejected`
- 受入ケース:
  - `queue` が `mode="enqueue"`、`steer` が `mode="immediate"` へ写像される。→ ✓
  - `stop_and_send` が `abort()` 実行後に新ターンを送信し、実行側がその応答を待機して Step の主応答とする。→ ✓
  - 送信前に Step が例外復帰した場合、`accepted` を残さず `failed` を ACK する。→ ✓
  - 再待機ターンでも `model.call_failure` の閾値超過で即失敗する。→ ✓
  - 要求本文が ACK・統計イベント・標準ログへ複製されない。→ ✓
  - 未消費要求のみ順序変更・取消でき、処理済み要求は再処理されない。→ ✓

### FR-GUI-13 — 宛先選択と実行ログの参照

- 判定: 実装済み
- 受入テスト:
  - [hve/gui/tests/test_page_workbench_job_interaction.py](hve/gui/tests/test_page_workbench_job_interaction.py) :: `TestJobTargets`、`TestJobChannelRegistry`、`TestJobLogAccess`、`TestPostRunAccess`、`TestPlanModeChannelRegistration`
  - [hve/gui/tests/test_start_autopilot_chain_branch.py](hve/gui/tests/test_start_autopilot_chain_branch.py) :: `test_app_chains_argv_factory_allocates_a_distinct_channel_per_lane`、`test_app_chains_relaunch_updates_the_channel_for_the_same_lane`、`test_prephase_window_allocates_a_channel_for_the_workflow`
  - [hve/gui/tests/test_main_window_dock_integration.py](hve/gui/tests/test_main_window_dock_integration.py) :: `test_copilot_dock_can_reach_the_job_interaction_api`、`test_main_window_allocates_isolated_job_channels`
  - [hve/gui/tests/test_copilot_chat_panel.py](hve/gui/tests/test_copilot_chat_panel.py) :: `test_job_targets_are_listed_from_the_workbench_page`、`test_selecting_a_target_loads_its_log_snapshot`、`test_incremental_log_is_appended_only_for_the_selected_target`、`test_send_is_rejected_for_a_finished_job`
- 受入ケース:
  - 並列 step 実行中でも宛先を明示選択でき、送信機能が無効化されない。→ ✓
  - workflow instance ごとに IPC チャネルが分離される。→ ✓
  - ログは既存バッファ / シグナルから増分取得し、帰属不明行を推測で割り当てない。→ ✓
  - 完了ジョブは参照専用で、対話送信の宛先にならない。→ ✓

### FR-GUI-14 — 完了ジョブの結果相談コンテキスト

- 判定: 実装済み
- 受入テスト:
  - [hve/gui/tests/test_copilot_job_context.py](hve/gui/tests/test_copilot_job_context.py) :: `test_includes_existing_run_paths`、`test_omits_paths_that_do_not_exist`、`test_does_not_search_outside_the_selected_run_root`、`test_does_not_embed_file_contents`、`test_paths_are_deduplicated_and_ordered`、`test_missing_work_root_yields_empty_paths`
  - [hve/gui/tests/test_copilot_chat_panel.py](hve/gui/tests/test_copilot_chat_panel.py) :: `test_open_result_starts_a_new_session_with_path_context`、`test_open_result_without_a_work_root_is_reported`、`test_open_result_does_not_kill_a_running_session_without_consent`
- 受入ケース:
  - 実在するパスだけが初期コンテキストに含まれる。→ ✓
  - ファイル本文がプロンプトへ埋め込まれない。→ ✓
  - 選択した run のルート外を自動探索しない。→ ✓
  - cleanup ポリシーを本機能のために上書きしない。→ ✓（`GuiSessionWorkdir` は未変更）
- 既知の制約:
  - cleanup ポリシーが `purge` の場合、GUI 終了後には参照先パスが残らない。

### FR-GUI-15 — Copilot チャットと HVE ワークフロー再開の境界

- 判定: 実装済み
- 受入テスト:
  - [hve/gui/tests/test_copilot_chat_panel.py](hve/gui/tests/test_copilot_chat_panel.py) :: `test_panel_has_no_workflow_resume_api`
- 受入ケース:
  - §5.6 の廃止済み Resume 機能を復活させない。→ ✓（`resume_session` 参照をパネルが持たない）
  - CLI の `/resume` を HVE ワークフロー再開として説明しない。→ ✓（users-guide で別概念として記載）
  - VS Code 固有の実行面を HVE GUI で再実装しない。→ ✓

### FR-GUI-16 — QA 自動投入を右ペインの必須選択にする

- 判定: 実装済み
- 受入テスト:
  - [hve/gui/tests/test_page_options_auto_qa_required.py](hve/gui/tests/test_page_options_auto_qa_required.py) :: `TestAutoQaVisibleInRightPane` — 全ワークフローで「QA 自動投入」「QA 回答モード」が Step 1 右ペインに可視、かつ `*必須` 表示を持つこと
  - [hve/gui/tests/test_page_options_auto_qa_required.py](hve/gui/tests/test_page_options_auto_qa_required.py) :: `TestAutoQaRequiredValidation` — 未選択で `validate()` が失敗し、有効 / 無効の明示選択で成功すること
  - [hve/gui/tests/test_page_options_auto_qa_required.py](hve/gui/tests/test_page_options_auto_qa_required.py) :: `TestAutoQaSelectionPropagation` — 選択値が `OrchestrateArgs.auto_qa` と QA 回答モードの活性へ伝播すること
  - [hve/gui/tests/test_page_options_auto_qa_required.py](hve/gui/tests/test_page_options_auto_qa_required.py) :: `TestAutoQaSettingsDefault` — 既定値が未選択（`""`）であること
  - [hve/tests/test_gui_step2_refactor.py](hve/tests/test_gui_step2_refactor.py) :: `test_additional_prompt_pinned_top_for_all_workflows` — 共通枠の可視フィールドが FR-GUI-20 規定の 6 項目とその順序であること
- 受入ケース:
  - 未選択のままでは実行を開始できない。→ ✓
  - 「無効にする」を選べば QA / AKM 同期なしで実行できる。→ ✓
  - 「未選択」を `False` として保存しない。→ ✓（`"" / "on" / "off"` で永続化）
  - （v2.25 改訂）表示ラベルが `QA (質問票) 自動投入` / `QA (質問票) 回答モード` であり、設定画面では `QA (質問票)` ノードへ属する。→ ✓ （[hve/gui/tests/test_settings_group_split.py](hve/gui/tests/test_settings_group_split.py) :: `TestSectionFieldsSplit`）

### FR-GUI-17 — AKM 用モデル / effort / context tier の GUI 選択

- 判定: 実装済み
- 受入テスト:
  - [hve/gui/tests/test_page_options_akm_model.py](hve/gui/tests/test_page_options_akm_model.py) :: `TestAkmModelWidgetsExist`
  - [hve/gui/tests/test_page_options_akm_model.py](hve/gui/tests/test_page_options_akm_model.py) :: `TestAkmModelVisibleInRightPane`
  - [hve/gui/tests/test_page_options_akm_model.py](hve/gui/tests/test_page_options_akm_model.py) :: `TestAkmModelAutoQaGating`
  - [hve/gui/tests/test_page_options_akm_model.py](hve/gui/tests/test_page_options_akm_model.py) :: `TestAkmModelArgsPropagation`
  - [hve/gui/tests/test_page_options_akm_model.py](hve/gui/tests/test_page_options_akm_model.py) :: `TestAkmModelSettingsDefaults`
- 受入ケース:
  - 3 項目が全ワークフローで Step 1 右ペインの共通枠へ可視である（effort は「AKM 用モデル」行の内部ウィジェットのため `isVisible()` で直接検証）。→ ✓
  - 設定画面の「Knowledge Management」セクションからも同じ 3 項目を編集できる。→ ✓（v2.25 で旧「自動プロンプト」から移設）
  - `auto_qa` が「有効にする」以外のとき 3 項目が非活性で、`OrchestrateArgs` へ値を渡さない。→ ✓
  - モデル既定は「継承」（`userData=None`）、context tier 既定も「継承」である。→ ✓
  - AKM 用モデルが「継承」または reasoning effort 非対応のとき effort コンボが disable である。→ ✓
  - 設定ストアの既定値が空文字（継承）である。→ ✓
  - （v2.25 改訂）設定画面では `Knowledge Management` ノードへ属し、`qa_akm_background_merge` が無効のとき 3 項目が非活性で `OrchestrateArgs` へ値を渡さない。→ ✓ （[hve/gui/tests/test_page_options_km_background_merge.py](hve/gui/tests/test_page_options_km_background_merge.py) :: `TestKmMergeGating`）
- 実装後の判断（FR-MAINT-07 面横断の再利用）:
  - モデル + Effort + Context size + Cost の行構築と Effort 再評価は `_C1Basic` のメソッドだった。`_C3AutoPrompt` からも使うためモジュール関数（`_build_model_effort_row` / `_populate_main_combo` / `_populate_secondary_combo` / `_refresh_effort_row`）へ単一実装として抽出し、`_C1Basic` は委譲に変えた（ロジックの 2 重実装を作らない）。
  - モデルキャッシュ更新時の再投入漏れを防ぐため、`MainWindow` は `c1.reload_models()` と同時に `c3.reload_models()` も呼ぶ。
  - 新規 `tr()` 文字列は既存の「レビュー用モデル」「QA 用モデル」と同じく `hve/gui/i18n/hve_gui_en_US.ts` へ登録し、`lrelease` で `.qm` を再生成した（英語ロケールで日本語のまま残らないことを実機確認）。
- 既知の制約:
  - `akm_effort` の選択肢は SDK の `ModelEntry.supported_reasoning_efforts` に依存するため、オフラインでモデルキャッシュが空の場合は disable のままとなる（`review_effort` / `qa_effort` と同じ振る舞い）。

### FR-GUI-18 — 実行ジョブタブの VS Code チャット同等 UI

- 判定: 実装済み
- 受入テスト:
  - [hve/gui/tests/test_chat_transcript.py](hve/gui/tests/test_chat_transcript.py) :: `TestUserBubble`、`TestAckBadge`、`TestLogBlock`、`TestTranscriptReset`
  - [hve/gui/tests/test_chat_transcript.py](hve/gui/tests/test_chat_transcript.py) :: `TestUserTurns`、`TestTurnScrollTracking`
  - [hve/gui/tests/test_chat_input_box.py](hve/gui/tests/test_chat_input_box.py) :: `TestMultilineSubmit`、`TestAttachments`、`TestComposeText`、`TestActionSelector`、`TestSendableGating`、`TestHeightGrowth`
  - [hve/gui/tests/test_copilot_chat_panel_chat_ui.py](hve/gui/tests/test_copilot_chat_panel_chat_ui.py) :: `TestJobTabComposition`、`TestPendingQueue`、`TestStatusFooter`、`TestOverflowMenu`
  - [hve/gui/tests/test_copilot_chat_panel_chat_ui.py](hve/gui/tests/test_copilot_chat_panel_chat_ui.py) :: `TestTurnNavigation`
  - [hve/gui/tests/test_copilot_chat_panel.py](hve/gui/tests/test_copilot_chat_panel.py) :: `test_primary_controls_are_reachable_and_named_for_assistive_tech`
  - [hve/gui/tests/test_i18n.py](hve/gui/tests/test_i18n.py) :: `test_job_chat_widgets_are_translated`、`test_copilot_chat_panel_is_translated`
- 受入ケース:
  - 送信メッセージ・ACK・GUI 通知・実行ログが 1 本の時系列列へ順に並ぶ。→ ✓（`TestUserBubble::test_entries_keep_their_chronological_order`、`TestLogBlock::test_a_message_splits_the_log_block`）
  - 実行ログ行を解析して発話者・役割・ターン境界を推定しない。→ ✓（`TestLogBlock::test_log_lines_are_not_parsed_for_roles`）
  - `Enter` で送信、`Shift+Enter` で改行する。入力欄の伸長に上限がある。→ ✓（`TestMultilineSubmit`、`TestHeightGrowth`）
  - 添付はパスだけを本文へ列挙し、ファイル本文を埋め込まない。個別に取り消せる。→ ✓（`TestComposeText::test_file_contents_are_never_embedded`、`TestAttachments::test_attachment_can_be_removed_individually`）
  - 添付を含む本文が 8 KiB を超える場合は送信しない。→ ✓（`TestJobTabComposition::test_composed_text_over_the_input_limit_is_not_sent`）
  - 実行中ジョブのモデル / reasoning effort を選択する UI を持たない。→ ✓（`TestActionSelector::test_no_model_or_effort_selector_is_offered`）
  - 未消費要求だけを送信待ちキューから取り消し・並べ替えできる。→ ✓（`TestPendingQueue::test_cancelling_removes_the_request_from_the_channel`、`::test_moving_a_request_changes_the_processing_order`、`::test_claimed_requests_leave_the_queue`）
  - 表示リセットが送信済み要求・IPC チャネルへ影響しない。→ ✓（`TestOverflowMenu::test_clearing_the_transcript_does_not_touch_pending_requests`）
  - 状態行が宛先の状態・チャネル可否・送信待ち件数を示し、実行ログを再掲しない。→ ✓（`TestStatusFooter`）
  - ジョブ全体の停止操作を「実行中の応答の取り消し」として提示しない。→ ✓（`TestOverflowMenu::test_no_stop_action_is_offered_for_the_running_turn`）
  - 送信メッセージだけをターンとして数え、GUI 通知・ACK・実行ログを含めない。→ ✓（`TestUserTurns::test_only_user_messages_are_counted_as_turns`）
  - 移動操作を行ったときは移動先が現在ターンになり、表示番号と一致する。→ ✓（`TestTurnNavigation::test_moving_to_the_previous_turn_updates_the_position`、`::test_moving_to_the_next_turn_updates_the_position`）
  - 会話全体がスクロールせずに収まる場合でも、移動操作が表示番号へ反映される。→ ✓（`TestTurnNavigation` の移動テストはスクロール範囲が 0（`maximum()==0`）の条件で走るため、スクロール連動が働かない状態でも番号が移動先を示すことを固定する）
  - 利用者がスクロールしたときはスクロール位置から現在ターンを決定する。→ ✓（`TestTurnScrollTracking`、`TestTurnNavigation::test_scrolling_the_conversation_updates_the_position`）
  - 末尾がスクロール範囲の上限に達し上端へ寄せきれない場合も、表示番号が移動先と一致する。→ ✓（`TestTurnScrollTracking::test_last_turn_is_current_even_when_it_cannot_reach_the_top`）
  - 新しい送信メッセージを追加したときはそのメッセージが現在ターンになる。→ ✓（`TestTurnNavigation::test_a_new_message_becomes_the_current_turn`）
  - 送信メッセージが 1 件も無いときは位置表示と前後移動を表示しない。→ ✓（`TestTurnNavigation::test_navigation_is_hidden_without_any_sent_message`、`::test_switching_the_target_resets_the_navigation`、`::test_clearing_the_transcript_hides_the_navigation`）
  - 先頭で前へ、末尾で次への移動を選べず、移動が循環しない。→ ✓（`TestTurnNavigation::test_previous_is_unavailable_on_the_first_turn`、`::test_next_is_unavailable_on_the_last_turn`）
  - ナビ表示は送信本文だけを 1 行で示し、送信方法・ACK を併記しない。→ ✓（`TestTurnNavigation::test_label_shows_only_the_message_body`）
  - 改行以降および表示長の上限を超える部分を省略する。→ ✓（`TestTurnNavigation::test_label_keeps_a_single_line`、`::test_label_elides_a_long_body`）
- 実装メモ:
  - 会話列は [hve/gui/widgets/chat_transcript.py](hve/gui/widgets/chat_transcript.py)、入力面は [hve/gui/widgets/chat_input_box.py](hve/gui/widgets/chat_input_box.py) へ分離し、[hve/gui/copilot_chat_panel.py](hve/gui/copilot_chat_panel.py) は宛先解決・IPC 送受信・状態表示に専念する。
  - 送信待ちキューは既存の [hve/job_interaction_ipc.py](hve/job_interaction_ipc.py) `list_pending_requests` / `cancel_request` / `reorder_pending` を配線しただけで、判定ロジックを GUI 側へ再実装していない（FR-MAINT-07）。
  - `job_log_text()` / `send_job_message()` / `select_action()` / `on_job_log_line()` の公開 API は据え置き、FR-GUI-12〜15 の既存受入テストを改変せずに GREEN を維持した。
  - ターンナビゲーションの現在位置はパネル側の `_turn_index` 1 つで保持し、移動操作で確定値を入れ、スクロール時は `ChatTranscriptView.current_user_turn_index()` の値で上書きする。同メソッドは各ターンの `y` をスクロール上限で clamp して比較するため、上端へ寄せきれない末尾ターンでも番号が一致する。
  - ターンナビの実装中に、実行ログの 1 行追記でログブロックの高さが伸びない既存欠陥を検出し、`document().contentsChanged` を接続して修正した（`TestLogBlock::test_appended_lines_grow_the_block`、`::test_snapshot_and_appended_lines_reach_the_same_height`）。
- 既知の制約:
  - 添付は本文へパスを列挙するだけであり、宛先セッションがそのパスを読めるかは Copilot CLI 側のツール承認に依存する。
  - 会話列は表示専用で永続化しない。宛先を切り替えると、その宛先のログスナップショットで再構成される。

### FR-GUI-19 — Workbench 経過時間の停止とジョブ終了検知

- 判定: 実装済み
- 受入テスト:
  - [hve/gui/tests/test_dag_status_widget.py](hve/gui/tests/test_dag_status_widget.py) :: `test_freeze_elapsed_keeps_summary_at_job_end_time` — 停止後にサマリー行の経過時間が進まない — 既存（本要件のサマリー行部分を満たす）
  - [hve/gui/tests/test_dag_status_widget.py](hve/gui/tests/test_dag_status_widget.py) :: `test_freeze_elapsed_stops_workflow_header_elapsed` — 停止後に Workflow ノードの経過時間が進まない
  - [hve/gui/tests/test_dag_status_widget.py](hve/gui/tests/test_dag_status_widget.py) :: `test_freeze_elapsed_stops_step_node_elapsed` — 停止後に Step ノードの経過時間が進まない
  - [hve/gui/tests/test_dag_status_widget.py](hve/gui/tests/test_dag_status_widget.py) :: `test_freeze_elapsed_stops_fanout_child_elapsed` — 停止後に fan-out 子ノードの経過時間が進まない
  - [hve/gui/tests/test_dag_status_widget.py](hve/gui/tests/test_dag_status_widget.py) :: `test_freeze_elapsed_survives_instances_mode_refresh` — `update_workflow_instances` による表示ノード再生成後も停止が維持される
  - [hve/gui/tests/test_page_workbench_process_exit.py](hve/gui/tests/test_page_workbench_process_exit.py) :: `TestGracePeriod::test_no_freeze_while_process_alive_despite_long_silence` — プロセスが生存している限り、出力が猶予を超えて途絶しても停止しない
  - [hve/gui/tests/test_page_workbench_process_exit.py](hve/gui/tests/test_page_workbench_process_exit.py) :: `TestGracePeriod::test_no_freeze_within_grace_period` — 終了確認から猶予内は停止しない
  - [hve/gui/tests/test_page_workbench_process_exit.py](hve/gui/tests/test_page_workbench_process_exit.py) :: `TestGracePeriod::test_grace_is_measured_from_exit_detection` — 猶予の起点が監視開始時刻ではなく終了確認時刻である
  - [hve/gui/tests/test_page_workbench_process_exit.py](hve/gui/tests/test_page_workbench_process_exit.py) :: `TestGracePeriod::test_grace_period_is_within_requirement_upper_bound` — 猶予と死活チェック 1 周期の合計が上限 10 秒を超えない
  - [hve/gui/tests/test_page_workbench_process_exit.py](hve/gui/tests/test_page_workbench_process_exit.py) :: `TestOrphanedExitDetection::test_freeze_after_grace_period_when_stream_never_ends` — ストリーム終端が来なくても猶予経過で停止し、警告 1 行と異常終了記録を伴う
  - [hve/gui/tests/test_page_workbench_process_exit.py](hve/gui/tests/test_page_workbench_process_exit.py) :: `TestOrphanedExitDetection::test_late_process_finished_is_ignored_after_orphaned_exit` — 遅延到着したストリーム終端で終了処理を二重実行しない
  - [hve/gui/tests/test_page_workbench_process_exit.py](hve/gui/tests/test_page_workbench_process_exit.py) :: `TestOrphanedExitDetection::test_orphaned_exit_finalizes_session_like_other_exit_paths` — 既存の終了経路と同じセッション後始末（実行ログ全文の保存）を伴う
  - [hve/gui/tests/test_page_workbench_process_exit.py](hve/gui/tests/test_page_workbench_process_exit.py) :: `TestOrphanedExitDetection::test_user_requested_stop_is_not_recorded_as_abnormal` — 停止要求後の終了を異常終了として記録しない
  - [hve/gui/tests/test_page_workbench_process_exit.py](hve/gui/tests/test_page_workbench_process_exit.py) :: `TestOrphanedExitDetection::test_mid_queue_completion_does_not_freeze` — キューに未実行が残る通常完了では停止しない
  - [hve/gui/tests/test_page_workbench_process_exit.py](hve/gui/tests/test_page_workbench_process_exit.py) :: `TestOrphanedExitDetection::test_orphaned_exit_does_not_rewrite_running_step_status` — 実行中 Step の状態表示を書き換えない
  - [hve/gui/tests/test_page_workbench_process_exit.py](hve/gui/tests/test_page_workbench_process_exit.py) :: `TestOrphanedExitStateReset::test_start_orchestrators_resets_orphaned_exit_state` — 新規実行の開始時に検知状態が初期化される
- 受入ケース:
  - 停止後にサマリー行・Workflow ノード・Step ノード・fan-out 子ノードの 4 系統すべてで経過時間が進まない。→ ✓（`test_freeze_elapsed_keeps_summary_at_job_end_time` / `test_freeze_elapsed_stops_workflow_header_elapsed` / `test_freeze_elapsed_stops_step_node_elapsed` / `test_freeze_elapsed_stops_fanout_child_elapsed`）
  - `set_plan` / `update_workflow_instances` による表示ノード再生成後も停止状態が維持される。→ ✓（`test_freeze_elapsed_survives_instances_mode_refresh`）
  - サブプロセスが終了しているのに標準出力ストリームが終端しない場合でも、経過時間が停止する。→ ✓（`test_freeze_after_grace_period_when_stream_never_ends`）
  - プロセスが生存している限り、出力が猶予を超えて途絶しても停止しない（終了の判定根拠がプロセスの終了状態のみである）。→ ✓（`test_no_freeze_while_process_alive_despite_long_silence`）
  - 猶予の起点が監視開始時刻ではなく終了確認時刻である。→ ✓（`test_grace_is_measured_from_exit_detection`）
  - 終端通知を待つ猶予が 10 秒を超えない。→ ✓（`test_grace_period_is_within_requirement_upper_bound`。検知は 500ms 周期の `_update_timer` でしか走らないため、定数単体ではなく「猶予 + チェック 1 周期」で検証する。`_ORPHANED_EXIT_GRACE_SEC = 5.0` なので最大 5.5 秒）
  - 異常終了の検知時に実行ログへ警告が 1 行出力され、正常完了と区別して記録される。→ ✓（`test_freeze_after_grace_period_when_stream_never_ends`。`[WARN]` 1 行と `state.aborted` を検証）
  - 停止要求後の終了は経過時間を停止するが、異常終了としては記録されない。→ ✓（`test_user_requested_stop_is_not_recorded_as_abnormal`）
  - 異常終了の検知が既存の終了経路と同じセッション後始末（実行ログ全文の保存）を伴う。→ ✓（`test_orphaned_exit_finalizes_session_like_other_exit_paths`）
  - キューに未実行のワークフローが残る通常完了では経過時間を停止しない。→ ✓（`test_mid_queue_completion_does_not_freeze`）
  - 異常終了の検知が実行中 Step の状態表示を完了・失敗へ書き換えない。→ ✓（`test_orphaned_exit_does_not_rewrite_running_step_status`）
  - 新たな `[hve:stats]` の `kind` を追加していない。→ ✓（静的確認: `git diff -- hve/gui/page_workbench.py hve/gui/widgets/dag_status_widget.py` の追加行に `kind` / `hve:stats` を含む行が 0 件）
  - 遅れて到着したストリーム終端で終了処理が二重実行されない。→ ✓（`test_late_process_finished_is_ignored_after_orphaned_exit`）
  - 新規実行の開始時に前回の終了検知状態が初期化される。→ ✓（`test_start_orchestrators_resets_orphaned_exit_state`）
- 実装メモ:
  - 4 系統の停止は [hve/gui/widgets/dag_status_widget.py](hve/gui/widgets/dag_status_widget.py) `DagStatusWidget._now()` に集約した。経過時間の終端値を求める 4 箱所（`_StepNodeItem.update_text` / `_FanoutChildNodeItem._elapsed_text` / `_WorkflowHeaderItem.update_text` / `_update_summary_label`）が `time.monotonic()` を直接参照せず同メソッドを経由する（FR-MAINT-07）。停止時刻をノード側へ保存しないため、表示ノードを再生成しても停止が維持される。
  - 終了検知は [hve/gui/page_workbench.py](hve/gui/page_workbench.py) `WorkbenchPage._check_subprocess_liveness()` で行い、新規タイマーを追加せず既存の 500ms `_on_update_timer` から呼ぶ。停止自体は既存 API `freeze_progress_elapsed()` / `WorkbenchState.mark_aborted()` を経由し、新規の停止経路を作っていない。
  - `mark_aborted()` は本変更以前はテストからしか呼ばれておらず、本要件で初めて本番経路へ配線された。Footer の Elapsed も同経路で停止する。
  - `qa_answer_mode="gui-file"` 時だけ起動する [hve/gui/qa_ipc_manager.py](hve/gui/qa_ipc_manager.py) `QAIpcManager._check_subprocess` は停止経路へ配線していない。常時動作する本検知で覆えるため、同一ルールを 2 重に実装しない（FR-MAINT-07）。
- 既知の制約:
  - 本検知は `_is_running` を `False` へ戻すが、`process_finished` を emit しない。このため [hve/gui/main_window.py](hve/gui/main_window.py) のナビゲーション（[戻る] / [停止]）は検知時点では更新されない。emit すると `_on_process_finished` が「全てのタスクが終わりました」のモーダルを出す経路を持ち、完了していないジョブへの虚偽通知になるため採用していない。
  - プロセスが生存したまま応答を返さない（ハング）ケースは本要件の対象外。プロセスが生存している間は「実行中」表示が事実に一致するため。
  - 検知後も実行中だった Step のステータスは `running` のまま残る。実際の結果を観測していないため完了・失敗へ書き換えない（捧造防止）。
- 既存テストとの境界:
  - [hve/gui/tests/test_page_workbench_fatal.py](hve/gui/tests/test_page_workbench_fatal.py) :: `TestWorkbenchElapsedFreeze` はキュー枯渇（正常終了）を契機とする停止を検証する。本要件が扱うのはストリーム終端を伴わない終了であり、契機が異なるため重複しない。
  - [hve/gui/tests/test_footer_elapsed_freeze.py](hve/gui/tests/test_footer_elapsed_freeze.py) は Footer の Elapsed が `mark_all_done` / `mark_aborted` で停止することを検証する。本要件の対象は「作業状況」の 4 系統であり対象ウィジェットが異なる。ただし異常終了検知は `mark_aborted` を経由するため、同ファイルは回帰対象に含める。

### FR-GUI-20 — 設定画面のカテゴリ再編と表記改称

- 判定: 実装済み
- 受入テスト:
  - [hve/gui/tests/test_settings_group_split.py](hve/gui/tests/test_settings_group_split.py) :: `TestGeneralCategoryTree`
  - [hve/gui/tests/test_settings_group_split.py](hve/gui/tests/test_settings_group_split.py) :: `TestSectionFieldsSplit`
  - [hve/gui/tests/test_settings_group_split.py](hve/gui/tests/test_settings_group_split.py) :: `TestBasicSectionOwnsAdditionalPrompt`
  - [hve/gui/tests/test_settings_group_split.py](hve/gui/tests/test_settings_group_split.py) :: `TestSettingsWindowReloadModels`
  - [hve/gui/tests/test_page_options_km_background_merge.py](hve/gui/tests/test_page_options_km_background_merge.py) :: `TestKmMergeVisibleInRightPane`
  - [hve/tests/test_gui_step2_refactor.py](hve/tests/test_gui_step2_refactor.py) :: `test_additional_prompt_pinned_top_for_all_workflows`
- 受入ケース:
  - 「一般」カテゴリに「自動プロンプト」ノードが存在せず、`QA (質問票)` / `レビュー` / `Knowledge Management` / `自己改善 (Self Improve)` が存在する。→ ✓
  - `追加プロンプト` / `コンテキスト最大文字数` が `基本設定`（`C1`）へ属する。→ ✓
  - `qa_akm_background_merge` が設定画面の `KM` ノードと Step 1 右ペインの共通枠の双方にあり、既定が未チェックである。→ ✓
  - 共通枠の可視項目が FR-GUI-20 規定の 6 項目・規定順である。→ ✓
  - 表示ラベルが `QA (質問票)` / `Knowledge Management` 表記である。→ ✓
- 実装後の判断（FR-MAINT-07 面横断の再利用）:
  - `_C3AutoPrompt` を `_CQaPrompt` / `_CReviewPrompt` / `_CKnowledgeManagement` / `_CSelfImprove` へ分割し、`_C3AutoPrompt` は 4 セクションを合成して属性を再公開するだけにした。ウィジェット構築コードを設定画面と右ペインで 2 重に持たないため。
  - `auto_qa` は `_CQaPrompt` が所有し、Knowledge Management の活性判定は `_CKnowledgeManagement._refresh_enabled()` の 1 箇所だけに置いた。両面は `wire_auto_qa_to_knowledge_management()` で同じ配線を共有する。
  - 設定画面はカテゴリヘルプボタンを描画しないため、新ノードに `_CATEGORY_HELP` エントリを追加しない（不要な定義を増やさない）。
- 既知の制約:
  - Step 1 右ペインの入力値はセッション限りであり、永続化の入口は設定画面だけである（既存の `auto_qa` / `akm_model` と同じ振る舞い）。

### FR-GUI-21 — ワークフロー一覧のカテゴリー構成

- 判定: 実装済み
- 受入テスト:
  - [hve/tests/test_workflow_categories.py](hve/tests/test_workflow_categories.py) :: `TestWorkflowCategories` — `WORKFLOW_CATEGORIES` の定義一致・網羅性・重複禁止・`AI Agent` の末尾配置
  - （v2.42 追加・実装済み）[hve/tests/test_workflow_categories.py](hve/tests/test_workflow_categories.py) :: `TestWorkflowCategories::test_ai_agent_category_is_last` / `test_ai_agent_category_contains_ada` — `AI Agent` の構成員が `ada` / `aag` / `aagd` / `aar` であり、カテゴリー定義順の末尾であること（RED: 3 failed / 14 passed → GREEN: 245 passed / 1 skipped。旧 `test_ai_agent_category_is_before_legacy_import_and_km` は規範順と矛盾するため本契約へ置換）
  - [hve/tests/test_workflow_categories.py](hve/tests/test_workflow_categories.py) :: `TestWorkflowEnumerationTables` — 表示順 3 表と `_WORKFLOW_DISPLAY_NAMES` が登録済み全ワークフローを含むこと
  - [hve/gui/tests/test_page_workflow_select_categories.py](hve/gui/tests/test_page_workflow_select_categories.py) :: `TestAiAgentCategory` — GUI 左ペインの `AI Agent` 見出し・「その他」非表示・見出し直下の並び・ヘルプボタン生成
  - [hve/tests/test_main_wizard_workflow_menu.py](hve/tests/test_main_wizard_workflow_menu.py) :: `TestWizardWorkflowMenuCategories` — CLI 選択肢のカテゴリー順・接頭辞・索引整合・未分類 ID の「その他」縮退
  - （v2.42 更新）[hve/tests/test_main_wizard_workflow_menu.py](hve/tests/test_main_wizard_workflow_menu.py) :: `test_ai_agent_workflows_are_grouped_together` — 末尾 4 件が `ada` / `aag` / `aagd` / `aar` であること。本改訂前は registry の順序が規範と不一致で実際に失敗していた（実測: 末尾 3 件が `adi` / `akm` / `adoc`）
  - [hve/tests/test_gui_help_content.py](hve/tests/test_gui_help_content.py) :: `test_ai_agent_workflows_have_help_entries` — AAG / AAGD / AAR の説明文と実在するガイド
  - [hve/tests/test_gui_help_content.py](hve/tests/test_gui_help_content.py) :: `test_every_registered_workflow_has_help_entry` — 登録済み全ワークフローの説明文とガイド
- 受入ケース:
  - `WORKFLOW_CATEGORIES` が [hve/workflow_registry.py](hve/workflow_registry.py) にあり、`list_workflows()` の全 ID を重複なく分類し、未登録 ID を含まない。→ ✓
  - `AI Agent` カテゴリーが `aag` / `aagd` / `aar` をこの順で持ち、カテゴリー定義順の末尾に位置する。→ ✓
  - 既存 5 カテゴリーの名称・構成員・順序が変化しない。→ ✓
  - GUI Step 1 左ペインに `AI Agent` 見出しが現れ、`その他` 見出しが現れない。AAG / AAGD / AAR のチェックボックスが当該見出しの直下に定義順で並ぶ。→ ✓
  - AAG / AAGD / AAR のヘルプボタンが生成される（`HelpPopupButton.from_key` が `None` を返さない）。→ ✓
  - CLI 対話ウィザードのワークフロー選択肢がカテゴリー順に並び、各選択肢がカテゴリー名の接頭辞を持つ。選択した索引が同一順序のワークフロー定義へ解決される。→ ✓
  - [hve/gui/page_options.py](hve/gui/page_options.py) / [hve/autopilot/plan_review_gap.py](hve/autopilot/plan_review_gap.py) の `_WORKFLOW_CANONICAL_ORDER` と [hve/gui/workflow_step_requirements.py](hve/gui/workflow_step_requirements.py) の `WORKFLOW_PRIORITY` が登録済み全ワークフローを列挙する。→ ✓
  - [hve/template_engine.py](hve/template_engine.py) の `_WORKFLOW_DISPLAY_NAMES` が `aar` を含む。→ ✓
- RED / GREEN 証跡:
  - RED（実装前）: `TestWorkflowCategories` は `ImportError: cannot import name 'WORKFLOW_CATEGORIES'`、`TestWizardWorkflowMenuCategories` は `AttributeError: _workflow_options_with_categories` が無い、`TestAiAgentCategory` は `AI Agent` 見出し不在で 4 件失敗、`test_every_registered_workflow_has_help_entry` は `['aag', 'aagd', 'aar']` が説明文を持たず失敗（実測）。
  - RED（`TestWorkflowEnumerationTables`）: 3 つの列挙表から `aar` を一時的に取り除いた状態で実行し、`test_page_options_canonical_order_covers_all` / `test_plan_review_gap_canonical_order_covers_all` / `test_display_names_cover_all` が `assert {'aar'} == set()` で失敗、`test_workflow_priority_covers_all` のみ成功することを実測（`WORKFLOW_PRIORITY` は変更前から `aar` を含むため）。
  - GREEN: 上記 6 系統すべて成功（`hve/tests/test_workflow_categories.py` 10 件、`hve/gui/tests/test_page_workflow_select_categories.py` 5 件、`hve/tests/test_main_wizard_workflow_menu.py` 6 件、`hve/tests/test_gui_help_content.py` 15 件）。
- 実装後の判断（FR-MAINT-07 面横断の再利用）:
  - カテゴリー表は [hve/workflow_registry.py](hve/workflow_registry.py) の `WORKFLOW_CATEGORIES` 1 箇所だけに置き、GUI は `_load_workflow_categories()`、CLI は `_workflow_options_with_categories()` から同じ表を読む。GUI 側に旧 `_WORKFLOW_CATEGORIES` リテラルは残していない。
  - CLI の選択肢生成は表示名辞書を引数で受け取り、`hve/template_engine.py` を直接 import しない。`template_engine` は相対 import を持ち、パッケージ外ロード時に単体 import できないため。
  - `Console.menu_select` は改修していない。全行が連番付き選択肢として描画される既存仕様のまま、カテゴリー名を接頭辞として埋め込む方式（既存 `_step_options_with_groups` と同型）を採った。
- 既知の制約:
  - 3 つの表示順列挙表（`_WORKFLOW_CANONICAL_ORDER` × 2 と `WORKFLOW_PRIORITY`）は本変更でも 3 箇所のまま維持した。統合はカテゴリー分類の要件範囲外で、Autopilot のプランレビュー経路まで影響が及ぶため。
  - `aar` の追加は現時点で表示・挙動を変えない。[hve/gui/page_options.py](hve/gui/page_options.py) は `_STEP2_FIELDS_BY_WORKFLOW` に `aar` キーが無いため枠を生成せず、[hve/autopilot/plan_review_gap.py](hve/autopilot/plan_review_gap.py) は `step.output_paths` のみを索引化するが AAR の全 Step は `output_paths_template` しか持たないため。

### FR-GUI-22 — GUI 起動時の索引差分更新と実行開始操作のガード

- 判定: 実装済み
- 受入テスト:
  - [hve/gui/tests/test_gui_index_refresh.py](hve/gui/tests/test_gui_index_refresh.py) :: `TestStartupTrigger` — GUI 起動が共有実装へ委譲すること、開始されなかった場合にポーリングしないこと
  - [hve/gui/tests/test_gui_index_refresh.py](hve/gui/tests/test_gui_index_refresh.py) :: `TestRunGuard` — 差分更新中は実行開始ボタンが無効になり、完了後に再評価されること、理由がステータスへ表示されること
  - [hve/gui/tests/test_gui_index_refresh.py](hve/gui/tests/test_gui_index_refresh.py) :: `TestSharedImplementation` — GUI 側で対象列挙・更新処理を再実装していないこと（FR-MAINT-07）
  - [hve/gui/tests/test_i18n.py](hve/gui/tests/test_i18n.py) :: `TestAssets` — 翻訳カタログの存在と抽出対象
- 受入ケース:
  - GUI 起動時に差分更新が共有実装（[hve/index_refresh.py](hve/index_refresh.py)）へ委譲される。プロセス内 1 回の制約は共有実装側が保証する。→ ✓
  - 差分更新の実行中、実行開始操作が無効になる。→ ✓
  - 無効化の理由が画面に表示される。→ ✓
  - 表示文字列が翻訳カタログ（`hve/gui/i18n/hve_gui_en_US.ts`）に載り、`.qm` が再生成されている。→ ✓（lrelease: 819 finished）
  - GUI 専用の設定項目を追加していない。→ ✓（`hve/gui/settings_store.py` の既定値は未変更）
- RED / GREEN 証跡:
  - RED（実装前）: `hve/gui/tests/test_gui_index_refresh.py` は `hve.index_refresh` 不在で 6 error（実測）。
  - GREEN: `hve/gui/tests/test_gui_index_refresh.py` 6 passed、`hve/gui/tests/test_i18n.py` 23 passed。
- 実装後の判断（FR-MAINT-07 面横断の再利用）:
  - GUI は `hve.index_refresh` を呼ぶだけで、索引 DB のパス規則や更新処理を保持しない。完了検知は [hve/gui/app.py](hve/gui/app.py) の `QTimer` ポーリング 1 本で行い、ウィンドウごとのタイマーを作らない。
- 既知の制約:
  - Autopilot の子 GUI（`--autopilot-child`）では差分更新を開始しない。親 GUI と同時に複数の子プロセスが同一索引 DB へ書き込むのを避けるため。

### FR-MODEL-07 — Copilot SDK の最新追従と明示 pin、ランタイム整合検証

- 判定: 実装済み
- 受入テスト:
  - [hve/tests/test_dev_task_environment_contract.py](hve/tests/test_dev_task_environment_contract.py) :: `test_copilot_sdk_lock_pins_an_exact_version` — `hve/copilot-sdk.lock` が厳密版と CLI ランタイム記録行を持ち、LF / BOM なしであること
  - [hve/tests/test_dev_task_environment_contract.py](hve/tests/test_dev_task_environment_contract.py) :: `test_setup_installs_the_latest_copilot_sdk_unless_pinned` — 既定経路が `--upgrade --no-deps` で最新化し、lock 版の導入が `--pin-sdk` / `-PinSdk` の内側にだけ置かれ、lock 書き換えが `--upgrade-sdk` / `-UpgradeSdk` の内側にだけ置かれていること
  - [hve/tests/test_dev_task_environment_contract.py](hve/tests/test_dev_task_environment_contract.py) :: `test_setup_scripts_verify_copilot_runtime_pin_consistency` — pin 版の先読みと、pin 無効化環境変数 3 種の検出
  - [hve/tests/test_dev_task_environment_contract.py](hve/tests/test_dev_task_environment_contract.py) :: `test_setup_scripts_read_copilot_version_only_with_no_auto_update` — 版突合が `--no-auto-update` を伴うこと
- 受入ケース:
  - 改訂前の HEAD では `test_setup_installs_the_latest_copilot_sdk_unless_pinned` が失敗する（既定経路が lock 導入で `--pin-sdk` / `-PinSdk` が存在しないため。RED 確認済み）。→ ✓
  - 既定実行（フラグなし）で `pip install --upgrade --no-deps github-copilot-sdk` が呼ばれ、`hve/copilot-sdk.lock` は書き換わらない。→ ✓
  - `--pin-sdk` / `-PinSdk` 指定時は `pip install --no-deps -r hve/copilot-sdk.lock` が呼ばれる。→ ✓
  - lock 更新ロジックを一時コピーへ適用すると pin 行と CLI ランタイム記録行の双方が書き換わり、LF / BOM なしが維持される（実測）。→ ✓
- 既知の制約:
  - 既定を最新追従へ変更したため、公開直後の SDK リリースにパーサ不整合がある場合は同時期にセットアップした全員が被弾しうる。再現性が必要な場面では `--pin-sdk` / `-PinSdk` を使う運用とし、実行時のフェイルソフト（`AssertionError` をイベント欠落警告へ変換する asyncio 例外ハンドラ）は本要件の範囲外。
  - `--check-only` / `-CheckOnly` は `.venv` 構築前に終了するため、これらの検証ステップは実行されない。
  - `pip install -e .[extras]` が先に走るため、`--pin-sdk` 指定時の新規環境では一度最新版を取得してから lock 版へ入れ替わる（最終状態は lock 版で正しいが、wheel の二重取得が発生する）。

### FR-MODEL-08 — 外部 Copilot CLI の最新版導入・更新

- 判定: 実装済み
- 受入テスト:
  - [hve/tests/test_dev_task_environment_contract.py](hve/tests/test_dev_task_environment_contract.py) :: `test_setup_scripts_install_the_latest_copilot_cli` — 3 OS 共通のセットアップが導入・更新の双方で `@github/copilot@latest` を指定し、npm グローバル管理下でない `copilot` を検出した場合に二重導入せず警告すること
- 受入ケース:
  - 実装前の HEAD では失敗する（新規導入経路が `@github/copilot`（`@latest` なし）で、npm グローバル管理下でない場合の分岐が存在しないため。RED 確認済み）。→ ✓
  - 導入済みかつ npm グローバル管理下では確認プロンプトなしで `npm install -g @github/copilot@latest` が呼ばれる。→ ✓
  - `--no-install-tools` / `-NoInstallTools` では導入・更新が呼ばれず、検出結果と手動導入手順だけが出力される（既存の setup ハーネスは全実行でこのフラグを付けており、`npm` 呼び出しが発生しないことを併せて担保する）。→ ✓
- 既知の制約:
  - npm グローバル管理下でない `copilot`（スタンドアロン導入版等）は、PATH 解決の分岐を避けるため自動更新しない。警告と手動更新手順の提示に留める。
  - 更新後の版が実際に npm registry の最新であるかは npm の解決に委ねており、セットアップ側で registry へ版問い合わせは行わない。

### FR-QA-01 — QA 質問票プロンプトの必須説明項目

- 判定: 実装済み
- 受入テスト:
  - [hve/tests/test_prompts.py](hve/tests/test_prompts.py) :: `TestQaPromptV2.test_qa_prompt_v2_requires_background_field`、`test_qa_prompt_v2_requires_viewpoints_field`、`test_qa_prompt_v2_requires_depth_rules`
  - [hve/tests/test_prompts.py](hve/tests/test_prompts.py) :: `TestPreExecutionQaPromptV2.test_requires_background_field`、`test_requires_viewpoints_field`、`test_requires_depth_rules`
- 受入ケース:
  - 両プロンプトの `[Qxx]` 出力テンプレートが `- 背景と根拠:` と `- 判断の観点:` を含む。→ ✓
  - 両プロンプトが「記述の深さ」の必須語（出典 / 未確認 / 評価軸 / 他の選択肢 / 1 行で記述）を指示する。→ ✓
  - 実装前は上記 6 件が全件失敗する（RED 確認済み）。→ ✓
- 実装後の判断:
  - 深さルールの文面は [hve/prompts.py](hve/prompts.py) `QUESTIONNAIRE_DEPTH_RULES_TEXT` を単一定義とし、事前 QA / 事後 QA の両プロンプトから連結する（同一文面の 2 重管理を避けるため）。
- 既知の制約:
  - 各フィールドの値を 1 行に限定しているのは、[hve/qa_merger.py](hve/qa_merger.py) の行単位フィールド解析が継続行を取り込まないためである。複数行で出力された場合は 2 行目以降が無視される。プロンプト側の指示で担保しており、解析側の強制は行っていない。
  - LLM が実際に十分な深さを出力するかはプロンプト遵守に依存する。本テストはプロンプトの指示内容を固定するものであり、生成結果の品質を検証するものではない。

### FR-QA-02 — QA 質問票パイプラインでの説明項目の保持と提示

- 判定: 実装済み
- 受入テスト:
  - [hve/tests/test_qa_merger.py](hve/tests/test_qa_merger.py) :: `TestStructuredQuestionParsing.test_q1_background`、`test_q1_viewpoints`
  - [hve/tests/test_qa_merger.py](hve/tests/test_qa_merger.py) :: `TestQAQuestionNewFields.test_background_defaults_empty`、`test_viewpoints_defaults_empty`
  - [hve/tests/test_qa_merger.py](hve/tests/test_qa_merger.py) :: `TestRenderMergedDepthColumns.test_extended_header_includes_depth_columns`、`test_depth_values_are_rendered`、`test_depth_only_document_uses_extended_table`、`test_rendered_table_round_trips_depth_columns`、`test_legacy_document_leaves_depth_fields_empty`
  - [hve/tests/test_questionnaire_ui.py](hve/tests/test_questionnaire_ui.py) :: `TestQuestionnaireDepthDetail.test_detail_block_is_printed_after_table`、`test_detail_block_omitted_when_no_depth_values`、`test_table_header_does_not_gain_depth_columns`
  - [hve/gui/tests/test_qa_answer_dialog.py](hve/gui/tests/test_qa_answer_dialog.py) :: `TestQAAnswerDialogDepthColumns.test_table_has_background_and_viewpoints_columns`、`test_depth_values_are_displayed`
  - [hve/tests/test_prompts.py](hve/tests/test_prompts.py) :: `TestQuestionnaireSkillFieldParity.test_skill_templates_declare_same_depth_fields_as_prompts`
- 受入ケース:
  - 構造化質問票（`[Qxx]` 形式）から `背景と根拠` / `判断の観点` が `QAQuestion` へ取り込まれる。→ ✓
  - `render_merged` の拡張テーブルが当該 2 列を出力し、その出力を再パースすると同じ値が復元される（GUI の IPC 往復で欠落しない）。→ ✓
  - 当該 2 項目を持たない旧形式の質問票は空文字列としてパースされ、例外にならない。→ ✓
  - CLI は既存テーブルの列を増やさず、テーブルの後に当該 2 項目の詳細ブロックを出力する。値が全問空の場合は詳細ブロックを出力しない。→ ✓
  - GUI の回答ダイアログが当該 2 項目の列を持ち、値を表示する。→ ✓
  - `.github/skills/task-questionnaire/` の SKILL.md および `references/` 配下の質問票テンプレートが、プロンプトと同一のフィールド名を宣言する。→ ✓
  - 実装前は上記 14 件が全件失敗する（RED 確認済み。非 GUI 12 件は assert 失敗、GUI 2 件は `_COL_BACKGROUND` 未定義による collection error）。→ ✓
- 実装後の判断（敵対的レビュー反映）:
  - `render_merged` の出力全体に対する `assertIn` は、プレアンブルに元の `[Qxx]` 本文が保持されるため実装前でも PASS する（偽陰性）。テーブル行（`|` で始まる行）に限定して検証すること。
  - CLI はテーブル列を増やさない。8 列の拡張表はすでに `_shrink_to_available` による幅圧縮が働く状態であり、長文 2 列を足すと既存列が読めなくなる。
- 既知の制約:
  - 拡張テーブルは最大 13 列（Work IQ 併用時）となる。Markdown の生テキストでは横に長い。Cloud 経路の利用者は、プロンプトが指示する Issue コメントの `[Qxx]` ブロック形式で参照することを想定している。
  - CLI の詳細ブロックはセル内折り返しを行わず、長文は端末のソフトラップに任せる。NFR の表幅制約（`TestQuestionnaireTableWidth`）はテーブル行に対するものであり、詳細ブロックには適用されない。
  - [hve/workiq.py](hve/workiq.py) の Work IQ 問い合わせメタには当該 2 項目を渡していない（本要件の範囲外）。

### FR-QA-03 — 回答済み QA 保存後の非待機 AKM 差分同期

- 判定: 実装済み
- 直接対応テスト:
  - [hve/tests/test_qa_merger.py](hve/tests/test_qa_merger.py) :: `TestAnsweredQaValidation` — 最終パスの再読込、内容・質問数・全回答の検証、回答も既定値も無い質問の拒否
  - [hve/tests/test_qa_merger.py](hve/tests/test_qa_merger.py) :: `TestRenderMergedMultilineCells` — Work IQ の複数行・CRLF・pipe を含む表セルの render / save / parse round-trip
  - [hve/tests/test_workiq.py](hve/tests/test_workiq.py) :: `TestWorkIQOfficialToolIdentity` — official / internal の厳密な server-tool 組と status allowlist
  - （v2.33 追加）[hve/tests/test_workiq.py](hve/tests/test_workiq.py) :: `TestWorkIQQueryToolDetection` — 参照系ツールの実行確認、書き込み系・管理系の除外、公開 allowlist と実行確認集合の分離
  - （v2.35 追加）[hve/tests/test_workiq.py](hve/tests/test_workiq.py) :: `TestWorkIQQueryToolDetection.test_query_tools_are_detected_on_preview_server` / `test_preview_server_write_and_admin_tools_are_not_execution_evidence` / `test_server_names_constant_is_the_single_source_of_truth` — `workiq-preview` 経由の参照系ツールを実行確認し、書き込み系を除外し、server 名を単一の正本で保持すること
  - （v2.35 追加）[hve/tests/test_runner.py](hve/tests/test_runner.py) :: `TestMcpServerFiltering.test_excludes_preview_plugin_alias` — `workiq-preview` をメインコーディングセッションから除外し、Work IQ 専用フェーズでは保持すること
  - [hve/tests/test_runner_pre_qa.py](hve/tests/test_runner_pre_qa.py) :: `TestPreQaAkmDispatch` — 保存検証成功後のファイル単位 dispatch、0 問スキップ、AKM 再帰防止、原本質問票処理を含む対象 workflow への適用
  - [hve/tests/test_runner_pre_qa.py](hve/tests/test_runner_pre_qa.py) :: `TestPreQaWorkiqRoundTrip` — verified `FOUND` / `PARTIAL` だけを統合し、未確認応答は draft のみに保持
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestQaAkmBackgroundCoordinator` — 親 DAG 非待機、FIFO 順序と同時起動 1 件の維持、明示 AKM との repository lock 排他、Git 境界 drain、検証済み QA だけの stage、cross-process lock
  - （v2.31 追加・v2.32 改訂）[hve/tests/test_qa_akm_child_parallelism.py](hve/tests/test_qa_akm_child_parallelism.py) :: `TestChildFanoutParallelism` — 子 argv が並列度を固定せず、AKM の宣言値を FR-DAG-03 の解決順序が適用すること
  - （v2.31 追加）[hve/tests/test_qa_akm_batching.py](hve/tests/test_qa_akm_batching.py) :: `TestQaAkmBatching` — 滞留登録のバッチ化、`target_files` への FIFO 順展開、ファイル単位の結果報告、同時 Popen ≦ 1、バッチ失敗の全ファイルへの伝搬、単一登録時の非バッチ化
  - [hve/tests/test_adi.py](hve/tests/test_adi.py) :: `test_adi_is_not_excluded_from_pre_qa` / `test_adi_answered_qa_is_dispatched_like_other_workflows` / `test_adi_questionnaire_main_outputs_are_separate_from_pre_qa_file` — ADI に事前 QA・dispatch の例外が無く、Step 1.1 / 1.2 の main 成果物が回答済み補助ファイルと別物であること
  - [hve/tests/test_adi_validation.py](hve/tests/test_adi_validation.py) :: `test_explicit_zero_questionnaire_is_valid` / `test_silent_zero_questionnaire_is_invalid` — 質問 0 件は「総質問数: 0」と「質問なし」の明示があるときだけ有効
  - [hve/gui/tests/test_qa_ipc_flow.py](hve/gui/tests/test_qa_ipc_flow.py) — GUI ユーザー回答 IPC が同じ保存検証・dispatch 経路へ到達し、GUI cleanup 前に worker が cancel / join されること
  - [hve/tests/test_runner_atomic_write.py](hve/tests/test_runner_atomic_write.py) :: `TestAtomicWriteText` / `TestIpcWriterUsesTheHelper` — IPC 書き込みが宛先ロック由来の `PermissionError` を再試行し、他の `OSError` は再試行しないこと
  - （v2.37 追加）[hve/tests/test_qa_merger.py](hve/tests/test_qa_merger.py) :: `TestMergeWorkiqResultsStatusSkip.test_partial_with_unperformed_search_note_is_merged` — `PARTIAL` 応答の本文に「未実施」が非エラー文脈で含まれても統合されること
  - （v2.37 追加）[hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py) :: `test_skipped_phases_warning_*` / `test_orchestrator_emits_skipped_phases_warning_after_fleet_start` — Fleet wave で実行されないフェーズの警告文と発火位置
- 受入ケース:
  - `auto_qa=false` と `workflow_id=akm` では dispatch しない。→ ✓
  - （v2.25 改訂）FR-QA-05 の `qa_akm_background_merge` が無効のときも dispatch しない。→ ✓ （[hve/tests/test_qa_akm_background_merge.py](hve/tests/test_qa_akm_background_merge.py) :: `TestShouldEnableQaAkmDispatchGate`）
  - 質問 0 件は QA ファイルと AKM dispatch を作らずメインタスクへ進む。→ ✓
  - 一部手動回答は既定値で補完し、回答も既定値も無い質問があればメインタスク開始前に失敗する。→ ✓
  - 検証済み QA 1 ファイルにつき `sources=qa` / 当該 `target_files` 1 件 / `force_refresh=false` / `auto_qa=false` で 1 回登録する。→ ✓
  - （v2.31 追加）実行開始時点で滞留している複数登録は 1 回の子実行へまとまり、`target_files` へ FIFO 順で全件が並ぶ。→ ✓ (`TestQaAkmBatching.test_pending_submits_are_batched_into_single_child` / `test_batch_argv_lists_all_target_files_in_fifo_order`)
  - （v2.31 追加）バッチ実行の結果は登録件数分（ファイル単位）で `drain()` から返り、失敗はバッチ全ファイルへ伝搬する。→ ✓ (`TestQaAkmBatching.test_drain_returns_one_result_per_registration` / `test_batch_failure_is_reported_for_every_file`)
  - （v2.31 追加）バッチ化しても同時に起動する AKM 子プロセスは 1 つを超えない。→ ✓ (`TestQaAkmBatching.test_no_concurrent_child_processes` / `TestQaAkmBackgroundCoordinator.test_multiple_submits_fifo_no_concurrent_popen`)
  - （v2.31 追加・v2.32 改訂）子 argv は並列度を固定せず、AKM の宣言値は FR-DAG-03 の解決順序が適用する。→ ✓ (`TestChildFanoutParallelism`)
  - source Workflow の次 Step は AKM 完了を待たないが、Git / branch / GUI cleanup 境界では未完了書込みを残さない。→ ✓
  - branch / PR 経路は AKM が参照した QA ファイルだけを knowledge 変更とともに commit 対象へ含める。→ ✓
  - 複数行・CRLF・pipe を含む Work IQ 回答案でも、回答済み Markdown の再解析で質問数と全回答を保持する。→ ✓ (`TestRenderMergedMultilineCells`)
  - Work IQ tool 実行を server/tool の組で確認でき、status が `FOUND` / `PARTIAL` の応答だけを QA へ統合する。→ ✓ (`TestWorkIQOfficialToolIdentity` / `TestPreQaWorkiqRoundTrip`)
  - `NOT_FOUND` / `UNAVAILABLE` / status 不明 / tool 未確認の応答は QA へ統合せず、未確認 draft にだけ保持する。→ ✓ (`TestPreQaWorkiqRoundTrip`)
  - （v2.35 追加）同一の Work IQ サービスを別サーバー名で登録する `workiq-preview` 経由の参照系ツールも実行確認の対象とし、同サーバーの書き込み系・管理系は対象外のままとする。→ ✓ (`test_query_tools_are_detected_on_preview_server` / `test_preview_server_write_and_admin_tools_are_not_execution_evidence`)
  - （v2.35 追加）Work IQ とみなす MCP サーバー名は単一の正本から導出し、実行確認とメインセッション分離で二重定義しない。→ ✓ (`test_server_names_constant_is_the_single_source_of_truth` / `TestMcpServerFiltering.test_excludes_preview_plugin_alias`)
  - （v2.37 追加・bugfix）tool 実行確認済みかつ `PARTIAL` の応答は、本文に「未実施」等の語が非エラー文脈で含まれていても QA へ統合する。→ ✓ (`test_partial_with_unperformed_search_note_is_merged`。修正前 RED: `AssertionError: '' == ''` で 1 failed / 137 passed、修正後 GREEN: `test_qa_merger.py` + `test_workiq.py` + `test_runner_pre_qa.py` で **356 passed / 47 subtests passed**)
  - （v2.37 追加）SDK Fleet mode へ委譲した wave は事前 QA と QA 起点 AKM の対象外とし、Fleet 起動成功を確認した時点で wave ごとに 1 回だけ警告する。起動失敗で通常経路へフォールバックした場合は警告しない。→ ✓ (`test_orchestrator_emits_skipped_phases_warning_after_fleet_start`)
- 実装後の判断:
  - Markdown table の CR / LF は `<br>`、pipe は `&#124;` を canonical な永続表現とし、literal との区別不能な逆変換は行わない。
  - （v2.31）AKM 子プロセスを多重起動する案は採らなかった。AKM の出力空間は `target_files` によらず `knowledge/D01`〜`D21` 全体と `business-requirement-document-status.md` を含み（[.github/scripts/templates/akm/step-1.md](.github/scripts/templates/akm/step-1.md) の `## 出力`）、多重起動は FR-QA-03 が防ごうとしている差分喪失そのものを生む。安全に並列化できるのは (a) 子 1 実行内の D01〜D21 fan-out（各子が自分の D だけを書く契約: [hve/prompt/fanout/akm/_common.md](hve/prompt/fanout/akm/_common.md)）と、(b) 滞留登録を 1 実行へまとめて同 fan-out で同時処理させることの 2 つに限られる。
  - （v2.31）子の並列度は親の `max_parallel` を継承せず AKM の宣言値を用いる。親の値は親 Workflow の Step 並列度で別概念のため。**（v2.32 改訂）** 当初は `_build_argv` で `--max-parallel` を明示付与していたが、FR-DAG-03 の解決順序を導入したことで宣言値が `SDKConfig.max_parallel` より優先され、当該付与は効果を持たないデッドコードとなった。FR-MAINT-07（同一ルールの二重実装禁止）に従い削除し、子 argv が並列度を固定しないことを回帰テストで固定した。
  - （v2.31）バッチ失敗時の 1 件ずつ再実行は実装しなかった。消費側 `_drain_qa_akm` は失敗件数を warning するだけで粒度を要求しておらず、再試行機構の新設は要件に無い。
  - （v2.31）`TestQaAkmBackgroundCoordinator` の 4 テストは「submit 件数 = 子プロセス数」を前提としており、バッチ化後は fake process が即完了する場合にだけ通る状態になっていた（実測: 25 回連続では失敗を観測せず）。契約が保証しない前提のため、1 件目の子を保持する / 1 件ずつ drain する形へ書き換えて決定論化した（15 回連続で安定を確認）。
  - Work IQ 実行確認は `_hve_workiq` / `workiq` / `workiq-preview` の 3 server と、`@microsoft/workiq` が公開する参照系ツール（`ask` / `retrieve` / `fetch` / `fetch_blob` / `get_schema` / `search_paths`）の組で行い、server 名を持たない tool event は Work IQ として扱わない。**（v2.35 改訂）** 対象 server は `hve/workiq.py` の `WORKIQ_MCP_SERVER_NAMES` を単一の正本とし、`hve/runner.py` のメインセッション分離もそこから導出する（FR-MAINT-07）。**（v2.33 改訂）** 従来は両 server とも `ask` だけを許可していたが、自動探索で併存する公式 `workiq` サーバー経由で `retrieve` が呼ばれた場合に実行確認が成立せず、`FOUND` 応答でも統合が 0 件になった（実測: `work/2026-08-19-qa_workiq_dryrun.md`。`retrieve` 10 回に対し Work IQ 判定は 0 件）。公開ツール名は `tools=["*"]` での実測 14 件（`accept_eula` / `ask` / `call_function` / `create_entity` / `delete_entity` / `do_action` / `fetch` / `fetch_blob` / `get_debug_link` / `get_schema` / `list_agents` / `retrieve` / `search_paths` / `update_entity`）を根拠とし、うち書き込み系・EULA・デバッグリンク・`call_function` / `list_agents` は M365 データ参照の証拠にならないため実行確認集合へ入れない。MCP へ公開する allowlist（`WORKIQ_MCP_TOOL_NAMES` = `ask` のみ）は最小権限のため据え置き、実行確認集合（`WORKIQ_MCP_QUERY_TOOL_NAMES`）と分離した。
  - **（v2.33）** 許可集合をセッションの `session.rpc.mcp.list()` から動的構築する案は採らなかった。実測（`work/run/20260818T092911-0ede91/Issue-WorkIQQueryModeExperiment/artifacts/probe_mcp_tools.log`）で server オブジェクトの属性は `error` / `from_dict` / `name` / `source` / `source_plugin` / `source_plugin_version` / `status` / `to_dict` だけで tools を公開せず、`session.rpc.tools` にも一覧取得 API が無いため実装不能である。**（v2.34 再実測）** 2026-08-19 時点の SDK で同じプローブを再実行したが、server 属性は同一で tools は現れず、`session.rpc.tools` は `get_current_metadata` / `handle_pending_tool_call` / `initialize_and_validate` / `update_subagent_settings` のみだった。判定は維持する。SDK が tools を公開するようになった時点で再検討する。
  - focused GREEN は QA / Work IQ / Pre-QA / Runner event tracking の 334 tests + 7 subtests で確認した。
  - ツール名を `ask` へ修正した変更では、`test_workiq.py` / `test_runner.py` / `test_runner_pre_qa.py` / `test_orchestrator.py` の 4 ファイルで **594 passed + 99 subtests** を確認した。同時に失敗した `TestRunWorkflowFanout::test_aad_web_fanout_meta_is_forwarded_to_step_runner` は本変更とは無関係の別事象で、後日テスト側の欠陥として解消した。原因はテストが `service_catalog` を合成キー `SVC-FANOUT-TEST` へ差し替えていた一方、後から入った APP-ID fan-out フィルタが選択 APP に紐づかないキーを除外し、Step 2.2 が `fanout-empty` で skip されていたこと（実測: 合成キーで子 0 件 / 実キーで子 24 件）。実キーを使う形へテストを修正して GREEN 化した。
  - **（v2.37 ・ bugfix）** [hve/qa_merger.py](hve/qa_merger.py) `merge_workiq_results` の `_error_indicators`（部分文字列一致）を削除した。統合可否の正本は [hve/workiq.py](hve/workiq.py) `is_workiq_result_mergeable` であり、呼び出し元 [hve/runner.py](hve/runner.py) は既に絞り込んだ結果だけを渡すため、同メソッド内のエラー語フィルタは二重フィルタで偽陰性しか生まない。STATUS 判定と「関連情報なし」完全一致判定は既存テスト 3 件が依存するため残した。なお [hve/workiq.py](hve/workiq.py) の `_WORKIQ_ERROR_INDICATORS` は STATUS が `FOUND` / `PARTIAL` / `NOT_FOUND` のとき早期返却するガードを持つ別実装であり、本修正の対象外である。
  - **（v2.37）** Fleet wave で事前 QA を実行させる案は採らなかった。事前 QA は Step ごとに session を分けて QA サブセッションを作る設計で、Fleet（1 セッションで複数 worker を起動）と構造的に噂み合わないため。利用者の明示設定が無言で失われる問題は警告 1 行で可視化する。また Fleet 使用時に `auto_qa` が有効なら Fleet を無言で無効化する案も採らなかった（別の無言の設定無効化を作るため）。

### FR-QA-04 — QA 起点 AKM のモデル / effort / context tier 選択

- 判定: 実装済み
- 直接対応テスト:
  - [hve/tests/test_qa_akm_model_selection.py](hve/tests/test_qa_akm_model_selection.py) :: `TestAkmExecutionQualityConfigDefaults`
  - [hve/tests/test_qa_akm_model_selection.py](hve/tests/test_qa_akm_model_selection.py) :: `TestBuildArgvAkmOverrides`
  - [hve/tests/test_qa_akm_model_selection.py](hve/tests/test_qa_akm_model_selection.py) :: `TestAkmSettingsDoNotLeakToMainSessions`
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestAkmExecutionQualityCliArgs`
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestAkmExecutionQualityWizard`
- 受入ケース:
  - `akm_model` / `akm_reasoning_effort` / `akm_context_tier` の既定が `None` であり、`get_akm_model()` が `model` を継承する。→ ✓
  - `_build_argv` が AKM 専用値を優先し、未指定項目だけメイン値へフォールバックする。→ ✓
  - 3 項目全て未指定のとき、メイン値がそのまま子 argv へ引き継がれ、`--akm-*` フラグが子へ漏れない（後方互換）。→ ✓
  - `--akm-model` / `--akm-reasoning-effort` / `--akm-context-tier` がパースされ `SDKConfig` へ反映される。→ ✓
  - AKM 専用値をセットしてもメイン / review / QA のセッション生成（`_apply_reasoning_effort` 等）が影響を受けない。→ ✓
  - 環境変数経路を新設しない（`from_env()` が `AKM_*` を読まない）。→ ✓
  - `--workflow akm` を明示指定した実行では本 3 項目を適用せず、`--model` / `--reasoning-effort` / `--context-tier` だけに従う。→ ✓
  - CLI wizard は `auto_qa` を有効化した非 AKM Workflow のときだけ 3 項目を尋ね、AKM 選択時および `auto_qa` 無効時は尋ねない。既定は継承。→ ✓
  - `akm_model` が `_normalize_model_with_warning` と同一規則で検証される（廃止名は警告付きで正規化し、許可リスト外は警告のうえ `Auto` へフォールバック）。→ ✓
  - 3 面のオプション対応表（`hve/tests/fixtures/option_parity_matrix.yaml`）へ登録され、CLI / GUI / Issue Form の対応が検証される。→ ✓
- 追加の受入テスト:
  - [hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) :: `TestOptionParityMatrix.test_coverage_all_sdkconfig_fields_registered`、`test_coverage_all_issue_form_ids_registered` — 新規 3 フィールドと Issue Form `akm_model` の登録漏れ検知
- 実装後の判断:
  - 継承の解決は `QaAkmCoordinator._build_argv` の 1 箇所だけで行う。`SDKConfig` 側に「解決済みの値」を持たせると、メインセッション生成が誤って AKM 値を読む経路が生まれるため、`get_akm_model()` は参照専用に留めた。
  - `akm_reasoning_effort` / `akm_context_tier` に環境変数経路を作らないのは、継承元の `reasoning_effort` / `context_tier` 自体に環境変数経路が無く（`SDKConfig.from_env` は `MODEL` / `REVIEW_MODEL` / `QA_MODEL` のみ）、4 つ目の入口を増やすと優先順位規則が既存 2 項目と食い違うため。
- 既知の制約:
  - CLI wizard の reasoning effort は自由入力である（`--reasoning-effort` が argparse に `choices` を持たない自由文字列であることに合わせた）。モデルがサポートしない値を入力した場合は SDK 側でエラーとなり、wizard は検出しない。
  - 本設定は QA 起点でバックグラウンド起動される AKM 子プロセスのみに効く。GUI / CLI の明示 AKM 実行と Cloud の通常 AKM は対象外。

### FR-QA-05 — QA 起点 AKM バックグラウンドマージの可否選択

- 判定: 実装済み
- 受入テスト:
  - [hve/tests/test_qa_akm_background_merge.py](hve/tests/test_qa_akm_background_merge.py) :: `TestQaAkmBackgroundMergeConfigDefaults`
  - [hve/tests/test_qa_akm_background_merge.py](hve/tests/test_qa_akm_background_merge.py) :: `TestShouldEnableQaAkmDispatchGate`
  - [hve/tests/test_qa_akm_background_merge.py](hve/tests/test_qa_akm_background_merge.py) :: `TestQaAkmBackgroundMergeCliArgs`
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestQaAkmBackgroundMergeWizard`
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestQaAkmRunWorkflowWiring.test_coordinator_enablement_condition`
  - [hve/gui/tests/test_page_options_km_background_merge.py](hve/gui/tests/test_page_options_km_background_merge.py) :: `TestKmMergeArgsPropagation`、`TestKmMergeGating`、`TestKmMergeSettingsDefaults`
  - [hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) :: `TestOptionParityMatrix.test_coverage_all_sdkconfig_fields_registered`、`test_coverage_all_issue_form_ids_registered`
- 受入ケース:
  - `SDKConfig.qa_akm_background_merge` の既定が `False` である。→ ✓
  - `_should_enable_qa_akm_dispatch` が本設定無効時に `False` を返す（`auto_qa=True` でも）。→ ✓
  - `--qa-akm-background-merge` が parse され `SDKConfig` へ反映される。→ ✓
  - CLI wizard は `auto_qa` を有効化した非 AKM Workflow のときだけ尋ね、既定は無効である。→ ✓
  - 本設定が無効のとき、wizard は FR-QA-04 の 3 項目を尋ねない。→ ✓（`TestAkmExecutionQualityWizard.test_does_not_ask_when_background_merge_declined`）
  - 環境変数経路を新設しない（`from_env()` が本キーを読まない）。→ ✓
  - GUI のチェックボックス値が `OrchestrateArgs` と argv へ伝播する。→ ✓
  - GUI で本設定が無効のとき FR-QA-04 の 3 項目を非活性化し値を渡さない。→ ✓
  - 3 面のオプション対応表へ登録される。→ ✓
- 実装後の判断:
  - 判定を `_should_enable_qa_akm_dispatch` の引数へ追加した（既定値を付けず必須キーワードにした）。既定値で黙って通すと、呼び出し側の配線漏れがテストで検出できなくなるため。
  - CLI wizard ではマージ可否を先に尋ね、有効のときだけ FR-QA-04 の 3 項目を尋ねる。GUI の活性制御と同じ前提に揃えるため。
- 既知の制約:
  - 本変更は後方互換を意図的に崩す。`--auto-qa` だけを使っていた既存実行は、本フラグを追加しない限り QA 起点 AKM が起動しなくなる（users-guide に変更の注記を記載）。

### FR-QA-06 — Work IQ tool 実行未確認の警告通知

- 判定: 実装済み
- 直接対応テスト:
  - [hve/tests/test_workiq.py](hve/tests/test_workiq.py) :: `TestWorkIQToolNotInvokedWarning` — 共有ヘルパーの文言（未確認の明示・観測ツール名・診断コマンド）と機微情報の非混入
  - [hve/tests/test_runner_pre_qa.py](hve/tests/test_runner_pre_qa.py) :: `TestPreQaWorkiqDetectionMissWarning` — `FOUND` / `PARTIAL` で tool 未確認のときだけ警告、`NOT_FOUND` では警告しない、統合 0 件サマリーの記号
- 受入ケース:
  - status が `FOUND` / `PARTIAL` で tool 実行を確認できないとき警告する。→ ✓ (`test_warns_when_found_status_without_tool_evidence`)
  - status が `NOT_FOUND` / `UNAVAILABLE` / 不明のときは警告しない。→ ✓ (`test_does_not_warn_for_not_found_status`)
  - 警告に当該区間で観測されたツール名が含まれる。→ ✓ (`test_warning_includes_observed_tool_names`)
  - 警告に診断コマンドが含まれる。→ ✓ (`test_warning_includes_diagnostic_command`)
  - 警告へ prompt 本文・tool 引数・M365 応答本文を含めない。→ ✓ (`test_warning_excludes_response_body`)
  - 応答 status が判明している場合は警告へ status を明示する。→ ✓ (`test_warning_reports_status_when_given`)
  - 統合 0 件かつ Work IQ 応答が 1 件以上のサマリーは `✅` ではなく警告で出す。→ ✓ (`test_zero_merge_summary_is_warning`)
  - 統合 1 件以上のサマリーは従来どおり `✅` の status で出す。→ ✓ (`test_nonzero_merge_summary_stays_status`)
  - 警告文の生成は `hve/workiq.py` の単一ヘルパーだけが行い、prefetch 経路も同一実装を使う。→ ✓ (`TestWorkIQToolNotInvokedWarning.test_prefetch_path_uses_shared_helper`)
- 実装後の判断:
  - 警告文の生成を [hve/workiq.py](hve/workiq.py) `format_workiq_tool_not_invoked_warning()` へ寄せ、`hve/orchestrator.py` の prefetch 経路が持っていた同一文言の直書きを置き換えた（FR-MAINT-07）。新規に 2 面目の実装を追加していない。
  - 観測ツール名は `StepRunner._toolsearch_called_tools` の当該区間差分から取る。`_workiq_called_tools` は Work IQ 判定を通ったものだけを保持するため、検出漏れの診断には使えない。
  - `NOT_FOUND` で警告しないのは、一次情報が見つからない質問が常態であり、全質問で警告を出すと検出漏れの信号が埋もれるため。
- 調査結果（2026-08-20 完了、F-09）:
  - **事象**: 実 run のログに `MCP サーバー 'workiq' 接続失敗 (status=failed): MCP transport host MCP list tools callback failed: McpError: MCP error -32001: Request timed out` が出力される（2026-08-19 / 2026-08-20 の 2 run で各 3 回）。出力元は [hve/runner.py](hve/runner.py) の `session.mcp_servers_loaded` ハンドラで、warning のみで実行は継続する。
  - **根本原因（確定）**: 独立した 2 つのタイムアウトの構造的不整合。Copilot CLI は MCP `tools/list` に **10.00 秒**の制限を課す（制御実験で二分探索: 遅延 8 秒→成功 / 11・12・70 秒→いずれも発行から 10.00〜10.01 秒で `-32001`。CLI 1.0.78 / 1.0.80 で同一）。一方 Work IQ MCP は自前でツールを持たない **MCP Proxy** で、`https://workiq.svc.cloud.microsoft/mcp` からのツール一覧取得に **30 秒**の HTTP タイムアウトを持つ（Work IQ 自身の stderr `[MCP Proxy] ... HttpClient.Timeout of 30 seconds ...` を実測）。リモート取得が `tools/list` の処理へずれ込むと、30 秒の予算を持つ処理を 10 秒で打ち切ることになり `-32001` となる。
  - **`workiq_request_timeout` は無関係（実証）**: 当該値が渡る Copilot SDK `MCPServerConfigLocal.timeout` はツール呼び出し専用で、`tools/list` には適用されない。実 run も `--workiq-request-timeout 600.0` を指定していたが発生した。
  - **失敗していたのは HVE のサーバーではない**: 実 run には 2 つの Work IQ が存在し、HVE の `_hve_workiq`（`tools:["ask"]`）は接続成功、失敗したのは Copilot CLI プラグイン宣言の `workiq`（`~/.copilot/installed-plugins/work-iq/workiq/.mcp.json`、`@microsoft/workiq@latest` / `tools:["*"]`）である。同一セッションに 2 つのプロキシが同居すると接続完了に最大 24.56 秒の差が生じることを実測した。
  - **実験系の妥当性**: 同じ制御実験で `initialize` の制限が 60,000 ms であること、およびそのエラー文言 `failed to initialize MCP client: initialize handshake did not complete within 60000 ms` を再現した。これは実 run で `azure` MCP が出したエラーと完全に一致する。
  - **限界**: 調査時点の環境ではリモート取得が一貫して成功したため（`Registered 10 remote tools`）、実 Work IQ の `tools/list` が 10 秒を超える瞬間は直接観測できなかった（直列 3 回・並列 4/12・二重構成・背景負荷 8/20 のいずれでも 0.10〜0.18 秒）。したがって「実 run で取得が `tools/list` へずれ込んだ」部分は確立した機構からの**推論**である。実 run のメッセージ接頭辞 `MCP transport host MCP list tools callback failed:` の由来も未確定。
  - **対処方針**: 10 秒の閾値は Copilot CLI 内部の固定値で HVE から設定できず、実行の成否にも影響しない（NFR-RTO-03 と整合）。要求定義に MCP 再試行を求める規範要件も無いため、**HVE のコード変更は行わない**。詳細は調査レポート（`work/` 配下、2026-08-20 付 F-09 根本原因調査レポート）に記録した。
  - `_workiq_mcp_connection_failed` は [hve/runner.py](hve/runner.py) に初期化 2 箇所・代入 2 箇所があり読み出しが 0 件の write-only フィールドである。本要件の利用者通知は上記 warning が担っているため、読み出しの追加・削除はいずれも要件根拠を持たない。

### FR-QA-07 — QA 起点 AKM 子実行の出力保全と失敗報告

- 判定: 実装済み
- 直接対応テスト:
  - [hve/tests/test_qa_akm_child_logging.py](hve/tests/test_qa_akm_child_logging.py) :: `TestQaAkmChildStdioLog` — 子 stdout / stderr のファイルリダイレクト、`log_path` の結果登録、バッチ全ファイルへの同一パス付与、非 UTF-8 バイト列の許容
  - [hve/tests/test_qa_akm_child_logging.py](hve/tests/test_qa_akm_child_logging.py) :: `TestDrainQaAkmFailureReport` — `_drain_qa_akm` の警告への `returncode` / `log_path` / blocked 確認導線の付与と、子ログ本文の非展開
- 受入ケース:
  - `_execute` は `stdout` へファイルオブジェクト、`stderr` へ `subprocess.STDOUT` を渡し `DEVNULL` を使わない。→ ✓ (`test_child_stdout_is_redirected_to_file`)
  - 保存先は当該子実行の `work/run/qa-akm-<id>/child-stdio.log` である。→ ✓ (`test_log_file_is_created_under_child_run_dir`)
  - 結果 dict にリポジトリルート相対の `log_path` が入る。→ ✓ (`test_result_contains_repo_relative_log_path`)
  - バッチ実行では全ファイルの結果へ同一の `log_path` が入る。→ ✓ (`test_batch_results_share_one_log_path`)
  - 子が非 UTF-8 バイト列を出力しても親を失敗させない。→ ✓ (`test_non_utf8_child_output_does_not_raise`)
  - `_drain_qa_akm` の警告に `returncode` と `log_path` が含まれる。→ ✓ (`test_warning_includes_returncode_and_log_path`)
  - バッチ失敗の警告は保存先単位で束ね、同じパスを反復しない。→ ✓ (`test_warning_groups_batch_failures_by_log_path`)
  - 警告に子ログの本文を展開しない。→ ✓ (`test_warning_does_not_inline_child_log_body`)
  - 警告に HVE ソース未コミット変更（FR-CLI-74）の確認導線が含まれる。→ ✓ (`test_warning_includes_dirty_source_hint`)
  - 子プロセスを起動できず `log_path` が無い場合でも件数と `returncode` を報告する。→ ✓ (`test_warning_without_log_path_is_still_reported`)
  - （v2.34 追加）登録時点で HVE ソースが dirty なら子を起動せずスキップする。→ ✓ (`TestQaAkmSubmitDirtySourcePrecheck.test_dirty_submit_does_not_start_child`)
  - （v2.34 追加）スキップは登録時点で即時警告する。→ ✓ (`test_dirty_submit_warns_immediately`)
  - （v2.34 追加）clean なら従来どおり子を起動し警告しない。→ ✓ (`test_clean_submit_starts_child`)
  - （v2.34 追加）スキップは実行失敗と別の文面で報告する。→ ✓ (`test_skipped_results_are_reported_apart_from_failures`)
  - （v2.34 追加）dirty 判定は FR-CLI-74 と同一実装を再利用する。→ ✓ (`test_default_probe_is_the_shared_dirty_source_resolver`)
- 実装後の判断:
  - **（v2.34 改訂）** `submit()` 時点の dirty 事前判定（当初は不採用としていた案）を採用した。不採用の根拠だった「時点依存で誤った安心を与える」は、最終ガード（`_check_dirty_hve_sources`）を維持したままスキップを追加することで解消する。実測では親 run 開始から失敗判明まで 41 分を要しており、事前判定が無いと利用者は待ち時間の後にしか気づけない。
  - **（v2.34）** dirty 判定は `_git_dirty_hve_source_paths()` を再利用し、`cwd` を coordinator の `repo_root` へスコープした。プロセスの CWD で判定すると、リポジトリ外の一時ディレクトリを `repo_root` にした呼び出しが本体リポジトリの状態を誤って読む。
  - `child-stdio.log` は `errors="replace"` で開く。子は Windows 日本語環境でロケール既定エンコーディングの出力を混在させ得るため、decode 失敗で親スレッドを落とさない。
  - 失敗報告は `log_path` 単位でまとめる。バッチ実行では複数の QA ファイルが同一の子実行・同一の `returncode` を共有するため、ファイル単位で 1 行ずつ出すと同じ情報が反復するだけになる。

### FR-QA-08 — 事前 QA 統合可否の軽量診断

- 判定: 実装済み
- 直接対応テスト:
  - [hve/tests/test_workiq.py](hve/tests/test_workiq.py) :: `TestWorkIQMergeDecision` — 統合可否判定の単一実装と真理値表、runner からの参照
  - [hve/tests/test_workiq.py](hve/tests/test_workiq.py) :: `TestWorkIQQaIntegrationDecisionCheck` — 診断チェックの PASS / FAIL / WARN と観測ツール名・診断コマンドの付与、応答本文の非混入
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestWorkIQDoctorSdkProbeArgs.test_qa_integration_probe_arg_parsed` / `test_qa_integration_probe_default_false` — CLI フラグの解釈と既定値
- 受入ケース:
  - tool 実行確認あり + `FOUND` / `PARTIAL` は `PASS` を返す。→ ✓
  - tool 実行未確認は `FAIL` を返し、観測ツール名と診断コマンドを含む。→ ✓
  - tool 実行確認あり + `NOT_FOUND` 等は `WARN` を返し、正常な場合があることを明示する。→ ✓
  - 判定は事前 QA 本体と同一の `is_workiq_result_mergeable()` を使う。→ ✓ (`TestWorkIQMergeDecision.test_runner_uses_the_shared_helper`)
  - `--qa-integration-probe` の既定は無効。→ ✓
- 実装後の判断:
  - 診断は既存の `probe_workiq_copilot_tool_invocation()` へ引数で分岐させ、セッション生成・MCP 状態確認・イベント購読を再利用した。新規に 2 つ目の probe 関数を作ると同一手続きが 2 面へ複製される。
  - 問い合わせは `query_workiq_detailed()` を使う。本番の事前 QA と同じ応答抽出・サニタイズ経路を通さないと、statusの抽出結果が本番と一致しない可能性がある。
  - 統合可否判定を `hve/runner.py` のインラインから `hve/workiq.py` へ抽出した。抽出しないと診断側が同じ条件を二重実装することになる（FR-MAINT-07）。
- 既知の制約:
  - 本診断は `workiq-doctor` が構成するセッション上で動く。利用者の MCP 設定に公式 `workiq` サーバーが登録されている場合の併存条件までは再現しない。統合 0 件が本番だけで再現する場合は、本診断が `PASS` でも FR-QA-06 の実行時警告で切り分ける必要がある。

---

## §F 非機能（§7）/ インタフェース（§8）

### NFR-PERF-01 — `max_parallel` 上限遵守
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_dag_executor.py](hve/tests/test_dag_executor.py) :: `TestDAGExecutorMaxParallel`
  - [hve/tests/test_fanout.py](hve/tests/test_fanout.py) :: `test_akm_max_parallel_is_21`
  - [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestADIQuestionnaireWorkflow.test_adi_questionnaire_steps`
  - [hve/tests/test_fanout.py](hve/tests/test_fanout.py) :: `test_adi_questionnaire_fanout_produces_21_children`

### NFR-PERF-02 — 既存成果物走査の早期打ち切り（src 50 / test 30）
- 判定: △
- 間接対応テスト:
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestDetectExistingArtifacts`
- 根拠: 50/30 のハードコード値の境界テストは未確認。

### NFR-PERF-03 — 性能 KPI 未定義（要件側 TBD）
- 判定: ✗

### NFR-OBS-01 — Wave 2 コンテキスト注入計測の Console/stderr 出力
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestContextInjectionMetricsOutput`

### NFR-OBS-02 — Fork-on-retry 有効時のみ `ForkKPILogger` 構築
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_fork_kpi_logger.py](hve/tests/test_fork_kpi_logger.py) :: `TestForkKPILoggerDisabled`、`TestForkKPILoggerEnabled`、`TestForkKPILoggerSanitization`、`TestForkKPILoggerIOFailure`
  - [hve/tests/test_fork_flag_rollback.py](hve/tests/test_fork_flag_rollback.py) :: `TestSDKConfigForkFlagDefault`、`TestDAGExecutorRollback`

### NFR-OBS-05 — ERROR / WARN のステップ帰属
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_console_error_step_attribution.py](hve/tests/test_console_error_step_attribution.py) :: `TestErrorStepAttribution` — GUI サブプロセス時の ctx マーカー付与、非 GUI / 未設定時の非付与
  - [hve/tests/test_console_error_step_attribution.py](hve/tests/test_console_error_step_attribution.py) :: `TestStepEndClearsContext` — `step_end` の ContextVar 解除と並列安全性
  - [hve/tests/test_console_error_step_attribution.py](hve/tests/test_console_error_step_attribution.py) :: `TestGuiParserRecoversStepId` — GUI 側での step_id 復元とマーカー除去

### NFR-OBS-06 — 指摘検知の構造化
- 判定: ✓
- 直接対応テスト:
  - [hve/gui/tests/test_workbench_logger_findings.py](hve/gui/tests/test_workbench_logger_findings.py) :: `TestStructuredFindingDetection` — 重大度テーブル行のみ検知、テンプレート/区切り/ヘッダ行の除外
  - [hve/gui/tests/test_workbench_logger_findings.py](hve/gui/tests/test_workbench_logger_findings.py) :: `TestNoFalsePositivesOnAgentProse` — 2026-07-26 ランの偽陽性 5 行が検知されないこと

### NFR-OBS-07 — 回復済みツール失敗の降格
- 判定: ✓
- 直接対応テスト:
  - [hve/gui/tests/test_workbench_logger_tool_recovery.py](hve/gui/tests/test_workbench_logger_tool_recovery.py) :: `TestToolFailureRecovery` — 同一 (step, tool) 成功での降格、別 step / 別 tool / 失敗イベントでの非降格、失敗履歴の保持
  - [hve/gui/tests/test_workbench_logger_tool_recovery.py](hve/gui/tests/test_workbench_logger_tool_recovery.py) :: `TestRunnerEmitsToolResultEvent` — runner が `tool_result` を発火
  - [hve/gui/tests/test_workbench_logger_tool_recovery.py](hve/gui/tests/test_workbench_logger_tool_recovery.py) :: `TestEditUniquenessGuidance` — `edit` 一意化ガイダンスの存在

### NFR-OBS-08 — 例外の型情報保持
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_step_exception_diagnostics.py](hve/tests/test_step_exception_diagnostics.py) :: `TestFormatExceptionForLog` — 型名保持、空メッセージ時の判別可能性、`KeyError('1.1')` 回帰ケース
  - [hve/tests/test_step_exception_diagnostics.py](hve/tests/test_step_exception_diagnostics.py) :: `TestRunnerUsesFormatter` — runner / orchestrator の包括ハンドラへの配線
  - [hve/tests/test_fork_session_id.py](hve/tests/test_fork_session_id.py) :: `TestMakeForkSessionId`、`TestSetForkIndexAndMainSessionId`

### NFR-OBS-09 — GUI ログ取り込みの UI スレッド処理量削減
- 判定: ✓
- 直接対応テスト:
  - [hve/gui/tests/test_console_log_dump.py](hve/gui/tests/test_console_log_dump.py) :: `TestLogPaneBaseDir::test_append_line_does_not_reopen_file_each_line` — 要件 (1): 50 行追記で `Path.open` 呼び出しが 1 回以内（ハンドル保持）かつ追記内容が読めること（flush）
  - [hve/gui/tests/test_console_log_dump.py](hve/gui/tests/test_console_log_dump.py) :: `TestLogPaneBaseDir::test_rotation_opens_new_file_once` — 要件 (1): ローテーション時のみ次ファイルを開き直す
  - [hve/gui/tests/test_console_log_dump.py](hve/gui/tests/test_console_log_dump.py) :: `TestLogPaneBaseDir::test_set_log_base_dir_none_closes_handle` — 要件 (1): 永続化無効化時のハンドルクローズ
  - [hve/gui/tests/test_console_log_dump.py](hve/gui/tests/test_console_log_dump.py) :: `TestLogPaneBaseDir::test_cleanup_closes_log_file_handle` — 要件 (1): `WorkbenchPage.cleanup()` でのハンドルクローズ
  - [hve/gui/tests/test_page_workbench_append_log.py](hve/gui/tests/test_page_workbench_append_log.py) :: `test_append_line_does_not_write_to_hidden_view` — 要件 (2): 非表示 `_LogPane` の `QPlainTextEdit` へ追記せず、ファイルへは永続化する
  - [hve/gui/tests/test_page_workbench_append_log.py](hve/gui/tests/test_page_workbench_append_log.py) :: `test_scroll_log_does_not_touch_hidden_view`、`test_key_scroll_does_not_touch_hidden_view` — 要件 (2): ↑/↓ および `g` / `G` のスクロール操作が非表示ウィジェットを対象にしない
  - [hve/gui/tests/test_log_tabs.py](hve/gui/tests/test_log_tabs.py) :: `test_append_global_coalesces_tail_follow` — 要件 (3): 5 回の連続追記に対し末尾追従の実行が 1 回であること
  - [hve/gui/tests/test_log_tabs.py](hve/gui/tests/test_log_tabs.py) :: `test_append_global_appends_and_tail_follows` — 要件 (3): イベントループ処理後に末尾追従が成立すること
  - [hve/gui/tests/test_page_workbench_layout.py](hve/gui/tests/test_page_workbench_layout.py) :: `test_user_actions_pane_skips_redundant_set_plain_text` — 要件 (4): 表示テキストが不変のとき `setPlainText` を呼ばない
  - [hve/gui/tests/test_page_workbench_layout.py](hve/gui/tests/test_page_workbench_layout.py) :: `test_user_actions_pane_reflects_downgraded_message` — 要件 (4): NFR-OBS-07 の降格でテキストが変化した場合は反映される
- 間接対応テスト:
  - [hve/gui/tests/test_console_log_dump.py](hve/gui/tests/test_console_log_dump.py) :: `TestWorkbenchPageConsoleLogDump::test_maybe_dump_console_log_writes_global_log_text` — 要件 (2): `console-log.txt` が `LogTabsWidget` の全文を正本とすること
  - [hve/gui/tests/test_autopilot_stats_propagation.py](hve/gui/tests/test_autopilot_stats_propagation.py) :: `test_t2_stats_line_not_mirrored_to_log_tabs` — 要件 (2): 表示・永続化の両経路に stats 行が混入しないこと

### NFR-OBS-03 — `--verbosity` 4 段階切替
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_console.py](hve/tests/test_console.py) :: `TestConsoleVerbose`、`TestConsoleNonVerbose`、`TestConsoleQuiet`、`TestConsoleStreamEnabled`、`TestConsoleStreamDisabled`、`TestConsoleStreamQuiet`、`TestStyleTTY`
  - [hve/tests/test_streaming_token_chunk.py](hve/tests/test_streaming_token_chunk.py) :: `test_token_chunk_not_emitted_below_verbose`、`test_token_chunk_suppressed_in_final_only_even_when_verbose`

### 廃止 NFR（NFR-COMP-01 / NFR-CONC-01 / NFR-PERF-04 / NFR-REL-01 / NFR-REL-02 / NFR-OBS-04）
- 判定: 現行評価対象外
- Resume 全廃に伴う廃止履歴として保持し、現行カバレッジへ算入しない。削除済みの RunLock / recovery / reconcile / checkpoint 専用テストを対応テストとして記載しない。

### NFR-COMP-02 — SDK < 0.3.0 互換（reasoning_effort TypeError ハンドリング）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_runner.py](hve/tests/test_runner.py) :: `TestCreateSessionAutoReasoningFallback.test_strips_reasoning_effort_on_typeerror`、`test_passthrough_for_value_validation_typeerror`

### NFR-TIME-01 — CLI idle 21600s / レビュー 7200s
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_main.py](hve/tests/test_main.py) :: `TestParserBasic.test_timeout_option`、`test_review_timeout_default`、`test_review_timeout_option`、`TestBuildConfigReviewTimeout`

### NFR-TIME-02 — Cloud AKM 360 分 / detect・suggest-next 15 分
- 判定: ✗

### NFR-A11Y-01 — `--screen-reader` / `NO_COLOR` / スピナー無効化
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_console.py](hve/tests/test_console.py) :: `TestScreenReader`、`TestNoColor`、`TestConsoleSpinner`、`TestStyleTTY`、`TestTimestampStyle`

### §8.1 Cloud → Reusable Workflow 入力（動的設定 / `runner_type` 配線）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) :: `TestAgenticRetrievalWorkflowWiring`、`TestRunnerTypeOptionParity`
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestWorkflowYamlAgenticInputs`

### §8.2 CLI → SDK（SDKConfig）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_config.py](hve/tests/test_config.py) :: `TestSDKConfigDefaults`、`TestSDKConfigFromEnv`、`TestSDKConfigResolveToken`、`TestSDKConfigToolListFromEnv`、`TestSDKConfigArtifactImprovementDefaults`、`TestSDKConfigArtifactImprovementFromEnv`

### §8.3 セッション永続化フォーマット
- 判定: 現行評価対象外（v1.1 で廃止）
- `state.json` / `.lock` / Resume 用 `journal.jsonl` と専用テストは削除済み。

### Run ID（`generate_run_id`）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_self_improve.py](hve/tests/test_self_improve.py) :: `TestGenerateRunId`、`TestRunImprovementLoopRunId`
- 間接対応テスト:
  - [hve/tests/test_session_id.py](hve/tests/test_session_id.py) :: `TestSafeRunIdComponent`

### §8.1 Cloud → Reusable Workflow 基本入力（`mode` / `event_action` / `label_name` 等）
- 判定: ✗

---

## §G ワークフロー別仕様（§13、Step 粒度）

### §13.0 共通約束

#### FR-WF-OUT-01 — `output_paths` 全件存在を完了条件
- 判定: ✓（v2.43追加分は RED: `test_data_model_split_contract.py` 内11件失敗 → GREEN: 25 passed。既存固定ゲートと合わせて runtime required 出力だけを検査）
- 直接対応テスト:
  - [hve/tests/test_runner_split_required_guard.py](hve/tests/test_runner_split_required_guard.py) :: `TestCheckOutputPathsGate::test_fail_when_one_declared_output_is_missing` — 1 件でも欠落すれば `_check_output_paths_gate` が欠落パスを返す（Step を failed 化する）ことを固定
  - [hve/tests/test_runner_split_required_guard.py](hve/tests/test_runner_split_required_guard.py) :: `TestCheckOutputPathsGate::test_fail_reports_only_missing_paths` — 宣言 3 件のうち一部欠落時、報告対象を欠落パスのみに限定することを固定
  - [hve/tests/test_runner_split_required_guard.py](hve/tests/test_runner_split_required_guard.py) :: `TestCheckOutputPathsGate::test_fail_when_all_outputs_missing`、`test_pass_when_all_declared_outputs_exist` — 全欠落 / 全存在の境界を固定
  - [hve/tests/test_runner_split_required_guard.py](hve/tests/test_runner_split_required_guard.py) :: `TestCheckOutputPathsGate::test_pass_when_ctx_is_none`、`test_pass_when_fleet_mode_enabled`、`test_pass_when_no_output_paths_declared`、`test_pass_when_unknown_step_id`、`test_pass_when_workflow_is_none` — 単独実行モード / fleet mode / 宣言なし Step / 未解決 step_id / workflow=None を適用外とする適用範囲を固定
- 注記: 旧 `hve/tests/test_runner_output_paths_gate.py` は上記クラスと同一対象・同一ケースの重複だったため 2026-07-28 に削除し、固有だった 3 宣言の部分欠落ケースのみ `test_fail_reports_only_missing_paths` として統合先へ移設した。
- 間接対応テスト:
  - [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestOutputPathsExplicit`
  - [hve/tests/test_collect_workflow_output_paths.py](hve/tests/test_collect_workflow_output_paths.py) :: `TestCollectWorkflowOutputPaths`
- v2.43直接対応テスト:
  - [hve/tests/test_data_model_split_contract.py](hve/tests/test_data_model_split_contract.py) — Data Model親だけが固定`output_paths`、条件付きsidecarが実行時G-OUTへ混入しないこと

#### FR-WF-OUT-02 — `output_paths_template` のキー別名プレースホルダ置換、空集合時 failed
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_fanout.py](hve/tests/test_fanout.py) :: `test_output_paths_template_resolves_with_key`、`test_output_paths_inherited_when_template_absent`、`test_fanout_empty_parser_marks_skip`
  - [hve/tests/test_fanout_output_template_resolution.py](hve/tests/test_fanout_output_template_resolution.py) :: `TestKeyAliasPlaceholder`（`{screenId}` / `{serviceId}` の fan-out キー解決、parser 違いの別名を置換しないこと、重複排除）
  - [hve/tests/test_fanout_output_template_resolution.py](hve/tests/test_fanout_output_template_resolution.py) :: `TestBackwardCompatibility`（`{key}` 単独置換と template 未指定時の継承を固定）

#### FR-WF-OUT-06 — 確定ファイルパスへ解決できないエントリの fail-closed drop
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_fanout_output_template_resolution.py](hve/tests/test_fanout_output_template_resolution.py) :: `TestFailClosedDrop`（キー別名なし / 未解決プレースホルダ / glob / ディレクトリ参照の 4 規則と部分採用）
  - [hve/tests/test_fanout_output_template_resolution.py](hve/tests/test_fanout_output_template_resolution.py) :: `TestDirectoryArtifactCoversDescendants`（規則 5: 宣言済みディレクトリ配下のファイルを個別に載せない、境界誤判定防止）
  - [hve/tests/test_fanout_output_template_resolution.py](hve/tests/test_fanout_output_template_resolution.py) :: `TestRegistryContractsAreSafe::test_no_unresolved_output_paths_in_registry`（レジストリ実データで展開後にプレースホルダ / glob が残らないこと）

#### FR-WF-OUT-07 — 非 fan-out Step の `output_paths_template` は契約宣言専用
- 判定: ✓（v2.43追加分は RED: `test_data_model_split_contract.py` 内11件失敗 → GREEN: 25 passed）
- 直接対応テスト:
  - [hve/tests/test_fanout_output_template_resolution.py](hve/tests/test_fanout_output_template_resolution.py) :: `TestRegistryContractsAreSafe::test_no_unresolved_output_paths_in_registry`
- 間接対応テスト:
  - [hve/tests/test_runner_split_required_guard.py](hve/tests/test_runner_split_required_guard.py) :: `TestCheckOutputPathsGate::test_pass_when_no_output_paths_declared`（`output_paths` 未宣言 Step はゲート対象外）
  - [hve/tests/test_collect_workflow_output_paths.py](hve/tests/test_collect_workflow_output_paths.py) :: `TestCollectWorkflowOutputPaths`
- v2.43直接対応テスト:
  - [hve/tests/test_data_model_split_contract.py](hve/tests/test_data_model_split_contract.py) — AAS/ADAの非fan-out sidecar宣言がG-OUT / Self-Improve scope外であること

#### FR-WF-OUT-03 — `required_input_paths` 不足時の挙動
- 判定: ✓ — §3.3 FR-DAG-06 と同等
- 直接対応テスト: [hve/tests/test_input_artifact_check.py](hve/tests/test_input_artifact_check.py) 全クラス

#### FR-WF-OUT-04 — `is_container=true` Step は生成ファイル無し
- 判定: △
- 間接対応テスト:
  - [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestStepDefFields`

#### FR-WF-OUT-05 — StepDef 宣言と io-contract の一致（registry mismatch 0 件 / CI hard fail）
- 判定: ✓（v2.43追加分は RED: `test_data_model_split_contract.py` 内11件失敗 → GREEN: 25 passed。validator実測: Agents 149 / Schema 0 / Integrity 0 / Registry mismatch 0）
- 直接対応テスト:
  - [.github/scripts/validate-io-contract.py](.github/scripts/validate-io-contract.py)（引数なし実行）— `Registry mismatch errors: 0` / exit 0 を CI 必須ステップとして実行（[.github/workflows/validate-io-contract.yml](.github/workflows/validate-io-contract.yml) `Validate io-contracts (registry-check, hard fail)`）
- 間接対応テスト:
  - [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestOutputPathsExplicit::test_all_non_container_steps_have_output_paths_or_template`（`ALLOWED_EMPTY_OUTPUT_PATHS_STEPS` の残存件数を固定）
- v2.43直接対応テスト:
  - [hve/tests/test_data_model_split_contract.py](hve/tests/test_data_model_split_contract.py) — AAS/ADAの親requiredとcanonical sidecar 3件のoptional/upsert宣言を固定
- 補足: registry mismatch は `check_registry_mismatch()` が例外ファイルを参照しないため `.github/io-contract-exceptions.yaml` では抑止できない。pytest ではなく CI ステップが一次検査を担う。

#### FR-WF-OUT-08 — 名称スラッグはキー別名へ登録しない（決定的復元が不可能）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_output_paths_template_resolvability.py](hve/tests/test_output_paths_template_resolvability.py) :: `test_name_slug_placeholders_are_not_registered_as_key_aliases`（`_KEY_ALIAS_PLACEHOLDERS_BY_PARSER` に `*NameSlug` が登録されていないこと）
  - [hve/tests/test_output_paths_template_resolvability.py](hve/tests/test_output_paths_template_resolvability.py) :: `test_service_test_project_paths_use_the_service_id`、`test_service_test_project_paths_do_not_use_the_name_slug`（ASDW-WEB 3.2 の宣言を実在 8 ディレクトリの命名規約へ固定）
  - [hve/tests/test_output_paths_template_resolvability.py](hve/tests/test_output_paths_template_resolvability.py) :: `test_non_fanout_steps_do_not_declare_fanout_placeholders`（非 fan-out Step が永久未解決エントリを宣言しないこと）
- 間接対応テスト:
  - [hve/tests/test_fanout_output_template_resolution.py](hve/tests/test_fanout_output_template_resolution.py) :: `TestKeyAliasPlaceholder`（parser 違いの別名を置換しないこと）

#### FR-WF-OUT-09 — ゲートが無言で空になる Step の明示 allowlist 化
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_output_paths_template_resolvability.py](hve/tests/test_output_paths_template_resolvability.py) :: `test_empty_output_gate_steps_match_the_documented_allowlist`（allowlist 外の Step がゲート空になった場合と、解決可能になったのに allowlist に残っている場合の双方を検出）
  - [hve/tests/test_output_paths_template_resolvability.py](hve/tests/test_output_paths_template_resolvability.py) :: `test_empty_gate_allowlist_entries_are_real_steps`（allowlist が実在 Step のみを指し理由が記載されていること）
- 間接対応テスト:
  - [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestOutputPathsExplicit::test_allowlist_has_no_stale_entries`、`test_allowlisted_step_template_declares_no_repository_artifact`

#### FR-WF-OUT-10 — drop エントリの prefix 存在ゲートへの降格
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_output_paths_prefix_gate.py](hve/tests/test_output_paths_prefix_gate.py) :: `test_name_slug_entry_is_demoted_to_a_key_prefix_gate`、`test_directory_entry_is_demoted_to_a_key_prefix_gate`、`test_glob_entry_is_demoted_to_a_key_prefix_gate`（規則 2 / 4 / 3 で drop されたエントリの降格）
  - [hve/tests/test_output_paths_prefix_gate.py](hve/tests/test_output_paths_prefix_gate.py) :: `test_entry_without_a_key_alias_is_not_demoted`、`test_entry_whose_key_is_never_substituted_is_not_demoted`、`test_fully_resolved_entry_is_not_demoted`、`test_non_fanout_step_has_no_prefix_gate`、`test_prefix_gates_are_deduplicated`（降格してはならない境界）
  - [hve/tests/test_output_paths_prefix_gate.py](hve/tests/test_output_paths_prefix_gate.py) :: `test_prefix_gate_matches_every_observed_naming_variant`、`test_registry_steps_recover_their_gate_via_prefix`（実地データでの誤 fail 非発生とレジストリ実定義での回復）
  - [hve/tests/test_runner_output_paths_prefix_gate.py](hve/tests/test_runner_output_paths_prefix_gate.py) :: `test_gate_passes_for_every_observed_naming_variant`、`test_gate_passes_when_a_directory_matches_the_prefix`、`test_gate_fails_when_no_artifact_matches_the_prefix`、`test_gate_fails_when_the_parent_directory_is_absent`、`test_concrete_and_prefix_gates_are_both_enforced`
  - [hve/tests/test_runner_output_paths_prefix_gate.py](hve/tests/test_runner_output_paths_prefix_gate.py) :: `test_prefix_gate_does_not_alter_output_paths`（`output_paths` を書き換えず他の消費者へ影響しない）
  - [hve/tests/test_runner_output_paths_prefix_gate.py](hve/tests/test_runner_output_paths_prefix_gate.py) :: `test_gate_is_skipped_in_fleet_mode`、`test_gate_is_skipped_in_standalone_mode`、`test_non_fanout_step_keeps_the_plain_gate`（FR-WF-OUT-01 と同一の適用範囲）
- 間接対応テスト:
  - [hve/tests/test_output_paths_template_resolvability.py](hve/tests/test_output_paths_template_resolvability.py) :: `test_empty_output_gate_steps_match_the_documented_allowlist`（prefix で回復した Step が allowlist に残っていないこと）

#### FR-WF-OUT-11 — io-contract の `kind: static` 確定パスの実在検査
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_phase8_s4_reinforcement.py](hve/tests/test_phase8_s4_reinforcement.py) :: `TestStaticInputPathExistence::test_existing_path_passes`、`test_missing_path_is_error`（実在 / 不在の基本判定）
  - [hve/tests/test_phase8_s4_reinforcement.py](hve/tests/test_phase8_s4_reinforcement.py) :: `test_non_static_kind_is_ignored`、`test_brace_placeholder_is_ignored`、`test_angle_placeholder_is_ignored`、`test_glob_is_ignored`、`test_trailing_slash_directory_is_ignored`（確定パスでないものを対象外とする規則）
  - [hve/tests/test_phase8_s4_reinforcement.py](hve/tests/test_phase8_s4_reinforcement.py) :: `test_exception_list_suppresses_error`（除外は `.github/io-contract-exceptions.yaml` の `static_paths` のみ）
  - [hve/tests/test_phase8_s4_reinforcement.py](hve/tests/test_phase8_s4_reinforcement.py) :: `test_repository_contracts_have_no_missing_static_paths`（リポジトリ実体に対する回帰ガード）
- 間接対応テスト:
  - [.github/scripts/validate-io-contract.py](.github/scripts/validate-io-contract.py)（引数なし実行）— `Integrity errors: 0` / exit 0
- 実測: 検査導入時点で 8 件を検出（`knowledge/D05` / `knowledge/D09` の区切り文字ゆれ 6 件、`knowledge/D15` のファイル名断片 1 件、未生成の生成対象 workflow 1 件）。前 7 件は宣言側を実体へ修正し、最後の 1 件は生成タイミング依存のため `static_paths` へ除外登録した。GREEN 後は `21 passed`（`test_phase8_s4_reinforcement.py`）/ validator `Integrity errors: 0`。
- 補足: FR-WF-OUT-05 の `check_registry_mismatch()` は `required: true` かつ `kind: agent_artifact` の入力しか照合しないため、`kind: static` は本検査だけが対象にする。

#### FR-WF-DM-01 — AAS/ADA Data Modelの親required + canonical 3 sidecar契約
- 判定: ✓（RED: 11 failed → GREEN: 25 passed）
- 直接対応テスト:
  - [hve/tests/test_data_model_split_contract.py](hve/tests/test_data_model_split_contract.py) — 50,000文字境界、親/sidecar相互リンク、canonical名限定、AAS/ADA registry・template・io-contractの一致、非分割再実行時のstale cleanup

#### FR-WF-ARD-01 — ARD の CLI / GUI / Cloud 3面対応
- 判定: ✓（RED: 旧CLI/GUI専用契約を本改訂で廃止し、Cloud対応契約が未実装 → GREEN: 2ファイルとも実装済で `test_ard_cli_only_contract.py` **15 passed**、`test_ard_cloud_surface.py` は FR-APPREQ-03/04/05 グループ **27 passed** に含まれる）
- 直接対応テスト:
  - [hve/tests/test_ard_cli_only_contract.py](hve/tests/test_ard_cli_only_contract.py) — 旧Cloud禁止assertionを削除し、dispatcher trigger_map への ARD 登録を含む Cloud 対応契約へ置換済
  - [hve/tests/test_ard_cloud_surface.py](hve/tests/test_ard_cloud_surface.py) — Issue Form、dispatcher、reusable workflow、状態ラベル、Python/Bash registry parity、Step Issue body への `<!-- app-ids: ... -->` 埋め込みを固定
- （2026-08-25 追記・bugfix）Windows PowerShell CLI 経路が未実装のまま残っていた（`.github/scripts/powershell/lib/workflow-registry.ps1` に `ard` ブロック不在）。Python 正本と同一の 10 Step を追加し、GREEN: [hve/tests/test_powershell_workflow_registry_parity.py](hve/tests/test_powershell_workflow_registry_parity.py) `test_powershell_registry_matches_python_ssot[ard]` **4 passed**（aas/adfd/adfdv/ard 全件）、Pester `workflow-registry.Tests.ps1` の `retrieves ARD workflow`（既存の先行宣言テスト）を含む **25 passed**、`commands.Tests.ps1` の AAS dry-run 表示件数（旧11→現10、Step.1 表示アサーション削除）を含む PowerShell Pester 全体 **83 passed / 0 failed**、PSScriptAnalyzer **0 件**。

---

### §13.1 AAS — Architecture Design

> **判定の意味**: AAS 各 Step の `✓` は「`output_paths` の **宣言**（registry / テンプレレベル）が一致」までを意味する。実 Step 実行後にファイルが生成されたかの完了検証は別途必要。

| Step | テンプレ/出力検証 | 判定 | 主な対応テスト |
|---|---|---|---|
| 1 アーキテクチャ推薦（root） | ✓ | ✓（旧 AAS Step 1 は ARD 4.1 へ移管済。旧 Step 2 を Step 1 へ昇格。RED 9 failed → GREEN 10 passed） | [test_application_requirement_workflow.py](hve/tests/test_application_requirement_workflow.py) + 既存 [test_aas_template_parity.py](hve/tests/test_aas_template_parity.py) の移管追随 |
| 2.1 ドメイン分析 | ✓ | ✓ | 同上 |
| 2.2 サービス一覧抽出 | ✓ | ✓ | 同上 |
| 3.1 データモデル | ✓ | ✓ | 同上 |
| 3.2 サンプルデータ | ✓ | ✓ | 同上 |
| 4 データカタログ | ✓ | ✓ | 同上 |
| 5 サービスカタログ統合 | ✓ | ✓ | 同上 |
| 6 テスト戦略書 | ✓ | ✓ | 同上 |
| 7 ペルソナカタログ | ✓ | ✓ | 同上 + [test_aas_persona_step_numbering_contract.py](hve/tests/test_aas_persona_step_numbering_contract.py) |
| 8 ペルソナ別共通画面カタログ | ✓ | ✓ | 同上 + [test_aas_persona_step_numbering_contract.py](hve/tests/test_aas_persona_step_numbering_contract.py) |

補助:
- [hve/tests/test_dag_executor.py](hve/tests/test_dag_executor.py) :: `TestDAGExecutorAAS`（DAG 実行整合性）
- [hve/tests/test_dag_parity.py](hve/tests/test_dag_parity.py) :: 全クラス（YAML ↔ registry parity）

#### FR-WF-AAS-01 — Step 7/8 を成果物依存と同じ昇順で採番
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_aas_persona_step_numbering_contract.py](hve/tests/test_aas_persona_step_numbering_contract.py) :: `TestRegistryContract`（Step 7=ペルソナカタログ / Step 8=ペルソナ別共通画面、宣言順・DAG wave・GUI rank の昇順）
  - [hve/tests/test_aas_persona_step_numbering_contract.py](hve/tests/test_aas_persona_step_numbering_contract.py) :: `TestIoContractFiles`（scoped contract のファイル名と producer、旧ファイル名の不在）
  - [hve/tests/test_aas_persona_step_numbering_contract.py](hve/tests/test_aas_persona_step_numbering_contract.py) :: `TestTemplatesAndPrompts`（Template の Custom Agent、Prompt と下流 consumer の Step 番号）
  - [hve/tests/test_aas_persona_step_numbering_contract.py](hve/tests/test_aas_persona_step_numbering_contract.py) :: `TestBashRegistryParity` / `TestPowerShellRegistryParity`（Bash / PowerShell registry の同期）
  - [hve/tests/test_aas_persona_step_numbering_contract.py](hve/tests/test_aas_persona_step_numbering_contract.py) :: `TestCloudWorkflow`（スキップ伝播方向、Issue タイトル、起動時の前提入力）
  - [hve/tests/test_aas_persona_step_numbering_contract.py](hve/tests/test_aas_persona_step_numbering_contract.py) :: `TestIssueForm` / `TestUsersGuide`（Issue Form の依存表記とガイドの現行構成）
- 間接対応テスト:
  - [hve/tests/test_aas_template_parity.py](hve/tests/test_aas_template_parity.py) :: `TestAasTemplateDependencyStepNumbers`（Step 7/8 を含む `## 依存` の番号整合）
- （追記・AAS Step.1 起点化）旧 Step "2"（root）を新 Step "1" へ昇格させ、以降の全 Step ID を 1 つ繰り上げた（詳細は `hve-dev/requirement-definition.md` §13.1 FR-WF-AAS-03）。本表の Step 番号・テスト内の Step ID 期待値は全て新番号へ更新済み。

### §13.2 AAD-WEB — Web App Design

> **判定の意味**: AAD-WEB 各 Step の `△` は「`TestAadWebStepOrderIntegrity` が Step **順序整合性のみ**検証する」を意味し、Step 個別の出力ファイル/完了条件の検証ではない。TBD-11 解消（registry への `output_paths` 登録）後に再評価が必要。

| Step | 判定 | 主な対応テスト |
|---|---|---|
| 1 画面一覧と遷移図 | △ | [test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestAadWebStepOrderIntegrity`（Step 順序のみ） |
| 2.1 画面定義書 (fan-out) | △ | 同上 |
| 2.2 マイクロサービス定義書 (fan-out) | △ | 同上 |
| 2.3 TDD テスト仕様書 (fan-out) | △ | 同上 |
| 3 整合性レビュー | △ | 同上 |
| Agentic Retrieval Step（横断） | ✓ | [test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestAadWebAgenticRetrievalStep`、`TestAgenticRetrievalSkipCondition` |

根拠: TBD-11 のとおり Step 別 `output_paths` は registry 未登録のため、テンプレ整合性レベルの検証に留まる。

### §13.3 ASDW-WEB — Web App Dev & Deploy

> **判定の意味**: §13.2 と同様。`TestAsdwWebStepOrderIntegrity` は Step 順序整合性のみで、各 Step の出力ファイル / 完了条件の検証ではない。TBD-12 解消後に再評価が必要。

| Step | 判定 | 主な対応テスト |
|---|---|---|
| 1.1 データストア選定 | △ | [test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestAsdwWebStepOrderIntegrity` |
| 1.2 データサービス Deploy | △ | 同上 |
| 2.1 コンピュート選定 | △ | 同上 |
| 2.2 追加サービス選定 | △ | 同上 |
| 2.3 追加サービス Deploy | △ | 同上 |
| 2.3T サービステスト仕様（RED） | △ | 同上 |
| 2.3TC サービステストコード（RED） | △ | 同上 |
| 2.4 サービス実装（GREEN） | △ | 同上 |
| 2.5 Azure Compute Deploy | △ | 同上 |
| 3.0T UI テスト仕様（RED） | △ | 同上 |
| 3.0TC UI テストコード（RED） | △ | 同上 |
| 3.1 UI 実装（GREEN） | △ | 同上 |
| 3.2 Web アプリ Deploy（SWA） | △ | 同上 |
| 3.3 UI E2E（Playwright） | ✓ | [test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestPlaywrightE2EReusableWorkflow` |
| 4.1 WAF レビュー | △ | `TestAsdwWebStepOrderIntegrity` |
| 4.2 整合性チェック | △ | 同上 |
| Agentic Retrieval Step（横断） | ✓ | `TestAsdwWebAgenticRetrievalSteps`、`TestAgenticRetrievalSkipCondition` |

根拠: TBD-12 のとおり大半の Step が registry 未登録のため △ 中心。

#### FR-WF-ASDW-01 — Step 1.3 の `required_params` 6 件と既定値契約
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_workflow_step_params.py](hve/tests/test_workflow_step_params.py) :: `TestStepParamDeclaration::test_required_params_match_contract` — Step 1.3 の `required_params` が契約の 6 件と完全一致することを固定
  - [hve/tests/test_workflow_step_params.py](hve/tests/test_workflow_step_params.py) :: `TestStepParamDeclaration::test_default_params_match_contract`、`test_resource_suffix_default_is_derived_from_the_supported_app_id`、`test_runner_reuses_the_registry_app_id_constant` — 既定値集合と `data_resource_suffix` の APP-ID 由来導出を固定
  - [hve/tests/test_workflow_step_params.py](hve/tests/test_workflow_step_params.py) :: `TestStepParamDeclaration::test_verify_aci_image_is_not_a_workflow_parameter` — `data_verify_aci_image` を入力項目として再導入しないことを固定
  - [hve/tests/test_workflow_step_params.py](hve/tests/test_workflow_step_params.py) :: `TestDefaultParamsValidity::test_declared_defaults_pass_runtime_validator`、`test_declared_defaults_reject_an_undeclared_bootstrap_input` — 宣言既定値が `build_asdw_data_deploy_bootstrap_context` の fail-closed 検証を通り、未宣言キーを `undeclared` として拒否することを固定
  - [hve/tests/test_asdw_data_runtime_context.py](hve/tests/test_asdw_data_runtime_context.py) — `build_asdw_data_deploy_bootstrap_context` の検証・導出挙動

#### FR-WF-ASDW-02 — 既定値を持たない必須パラメータは `resource_group` のみ（pre-flight で `blocked`）
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_workflow_step_params.py](hve/tests/test_workflow_step_params.py) :: `TestStepParamDeclaration::test_resource_group_has_no_default` — `resource_group` だけが `default_params` を持たないことを固定
  - [hve/tests/test_workflow_param_precheck.py](hve/tests/test_workflow_param_precheck.py) :: `TestRunWorkflowParamPrecheckWiring::test_missing_resource_group_is_reported` — `resource_group` 未指定が pre-flight で報告されることを固定
  - [hve/tests/test_workflow_param_precheck.py](hve/tests/test_workflow_param_precheck.py) :: `TestRunWorkflowParamPrecheckWiring::test_missing_required_param_blocks_before_execution`、`test_defaults_are_applied_before_precheck`、`test_precheck_is_not_downgraded_by_continue_on_error` — DAG 実行前に `blocked` を返し、既定値適用後に判定し、`continue_on_error` でも降格しないことを固定
  - [hve/tests/test_workflow_param_precheck.py](hve/tests/test_workflow_param_precheck.py) :: `TestRunWorkflowParamPrecheckWiring::test_step_1_3_not_selected_does_not_require_params` — Step 1.3 非選択時は必須化しないことを固定
  - [hve/gui/tests/test_workflow_required_input_fields.py](hve/gui/tests/test_workflow_required_input_fields.py) :: `TestRequiredInputFieldsInWorkflowBox::test_defaulted_params_have_no_input_field` — 既定値を持つ 5 件（`data_*`）に GUI 入力欄が存在しないこと
  - [hve/gui/tests/test_orchestrate_args.py](hve/gui/tests/test_orchestrate_args.py) :: `TestDataDeployBootstrapToArgv` — GUI が `--data-*` 5 フラグを argv へ出力しないこと（CLI 側のフラグ宣言は [hve/tests/test_main.py](hve/tests/test_main.py) が引き続き固定）
- 2026-08-20 の実測: 判定を「要確認」から ✓ へ更新。上記 2 件は既に実装済みで、FR-GUI-06 の対応テストと同一実体である。
- 補足: 時系列の先行性（Step 1.3 の実行時検証まで判定を遅らせない）は `TestRunWorkflowParamPrecheckWiring` が DAG 実行前 abort を固定することで担保される。

#### FR-WF-ASDW-03 — `SUBSCRIPTION_ID` は `az account show`、`DATA_DEPLOY_IDENTITY_CLIENT_ID` は prep 後に読み戻す
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_asdw_azure_cli_resolution.py](hve/tests/test_asdw_azure_cli_resolution.py) :: `TestSubscriptionIdUsesResolvedExecutable::test_invokes_resolved_executable` — `az account show --query id --output tsv` を **解決済み実行ファイルパス**で起動することを固定
  - [hve/tests/test_asdw_azure_cli_resolution.py](hve/tests/test_asdw_azure_cli_resolution.py) :: `TestIdentityReadBackUsesResolvedExecutable::test_invokes_resolved_executable` — `az identity show` による client ID 読み戻しを同様に固定
  - [hve/tests/test_asdw_azure_cli_resolution.py](hve/tests/test_asdw_azure_cli_resolution.py) :: `TestResolveAzureCliExecutable` 4 件 — 信頼ルート優先 → 継承 PATH フォールバック → fail-closed、および実機解決結果が実在パスであることを固定
  - [hve/tests/test_asdw_azure_cli_resolution.py](hve/tests/test_asdw_azure_cli_resolution.py) :: `TestNoBareAzureCliInvocation::test_asdw_sources_never_spawn_bare_az` — 素の `"az"` を argv[0] に渡す退行をソースレベルで禁止
  - [hve/tests/test_asdw_launcher_windows_runtime.py](hve/tests/test_asdw_launcher_windows_runtime.py) :: `test_child_environment_supplies_azure_config_dir_from_parent`、`test_child_environment_derives_azure_config_dir_from_userprofile` — 子 stage の `az` が親のログイン状態を引き継ぐことを固定
  - [hve/tests/test_asdw_data_stage_guard_contract.py](hve/tests/test_asdw_data_stage_guard_contract.py) :: `test_stage_guards_are_satisfied_by_the_launcher_environment`（4 stage）、`test_prep_does_not_require_the_post_prep_read_back_key`、`test_later_stages_still_require_the_read_back_key` — 「各 stage のスクリプトが要求する変数は launcher がその stage へ供給できるキーの部分集合である」という不変条件で、prep が読み戻し前の値を要求する鶏と卵型の欠陥を禁止
- 補足: 2026-07-28 の live canary（run `20260728T034239-836daa`、Wave 9）で Step 1.3 が `could not run the Azure CLI to resolve SUBSCRIPTION_ID` により失敗した退行に対する回帰テスト。既存テストは対象関数を全てモックしていたため実経路が未検証だった。canary の継続実行では、同じ経路でさらに Policy スコープ形式・MSYS 引数変換・宣言済み CIDR の無視・`subnet create --ids`・`az acr build` のソース指定・AAD 専用認証の外部管理者・Confidential Ledger のリージョン非対応が判明し、いずれも以下のテストで固定した。
  - [hve/tests/test_asdw_data_azure_cli_scope_contract.py](hve/tests/test_asdw_data_azure_cli_scope_contract.py) — ARM スコープ形式、`az acr build` のソース指定形式、AAD 専用認証時の外部管理者 3 引数
  - [hve/tests/test_asdw_data_network_provisioning_contract.py](hve/tests/test_asdw_data_network_provisioning_contract.py) — 「宣言済みワークフローパラメータは生成スクリプトへ到達する」不変条件、`create` での `--ids` 禁止、各サブネットの CIDR 適用、台帳 location の fallback
  - [hve/tests/test_asdw_launcher_windows_runtime.py](hve/tests/test_asdw_launcher_windows_runtime.py) :: `test_child_environment_disables_msys_argument_path_conversion`、`test_windows_script_dir_survives_disabled_path_conversion`

### §13.4 ADFD — Dataflow Design

| Step | 判定 | 主な対応テスト |
|---|---|---|
| 0.1 データフローデータモデル定義書 | ✓ | [test_adfd_dataflow_design_agents.py](hve/tests/test_adfd_dataflow_design_agents.py) :: `TestAdfdRegistryNewSteps::test_new_steps_exist_with_expected_agent_and_outputs`、`TestAdfdIoContracts` |
| 0.2 データフローアプリカタログ | ✓ | 同上 |
| 4 データフローサービスカタログ | ✓ | 同上 |
| 5 データフローテスト戦略書 | ✓ | 同上 |
| 1 ジョブ詳細仕様書 (fan-out) | ✓ | [test_fanout.py](hve/tests/test_fanout.py) :: `test_output_paths_template_resolves_with_key`（テンプレ展開）+ [test_adfd_dataflow_design_agents.py](hve/tests/test_adfd_dataflow_design_agents.py) :: `TestAdfdRegistryNewSteps::test_existing_steps_are_unchanged` |
| 2 監視・運用設計書 | △ | [test_adfd_dataflow_design_agents.py](hve/tests/test_adfd_dataflow_design_agents.py) :: `TestAdfdRegistryNewSteps::test_existing_steps_are_unchanged`（宣言不変のみ） |
| 3 TDD テスト仕様書 (fan-out) | ✓ | 同 fan-out テスト群 + `test_existing_steps_are_unchanged` |

#### FR-WF-ADFD-01 — ADFDV 上流 4 ドキュメントの producer を ADFD 内に持つ
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_adfd_dataflow_design_agents.py](hve/tests/test_adfd_dataflow_design_agents.py) :: `TestAdfdIoContractExceptionsRemoved::test_target_paths_not_in_exceptions` — `external_paths` / `static_paths` に 4 パスが残っていないことを固定
  - [hve/tests/test_adfd_dataflow_design_agents.py](hve/tests/test_adfd_dataflow_design_agents.py) :: `TestAdfdIoContractExceptionsRemoved::test_target_paths_have_producer_in_inventory` — 4 パスを出力する io-contract が inventory に存在することを固定

#### FR-WF-ADFD-02 — 4 Step は既存 Step の上流、DAG 根は `0.1` 単一、既存 Step 宣言は不変
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_adfd_dataflow_design_agents.py](hve/tests/test_adfd_dataflow_design_agents.py) :: `TestAdfdRegistryNewSteps::test_new_steps_are_upstream_of_existing_steps`
  - [hve/tests/test_adfd_dataflow_design_agents.py](hve/tests/test_adfd_dataflow_design_agents.py) :: `TestAdfdRegistryNewSteps::test_existing_steps_are_unchanged`
  - [.github/scripts/powershell/tests/workflow-registry.Tests.ps1](.github/scripts/powershell/tests/workflow-registry.Tests.ps1) — PowerShell面の7 Step、単一root `0.1`、依存解決、skip解決、厳密paramsを固定（Pester更新後のRED: 9 failed / 71 passed → GREEN: 82 passed / 0 failed）
  - [.github/scripts/powershell/tests/commands.Tests.ps1](.github/scripts/powershell/tests/commands.Tests.ps1) — ADFD dry-runがStep `0.1` / `0.2`と正確な7 Step件数を表示することを固定
  - [hve/tests/test_powershell_workflow_registry_parity.py](hve/tests/test_powershell_workflow_registry_parity.py) — AAS / ADFD / ADFDV のparams、Step順、title、Custom Agent、依存、fallback、templateをPython正本と完全比較（3 passed）
- 補足: [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) の `EXPECTED_STEP_COUNTS["adfd"]` / `test_abd_roots` / `test_abd_step61_and_step62_are_parallel` / `test_and_join` は 7 Step 新構造（根 = `0.1`、Step 1 / 2 は `depends_on=["5"]`）へ更新済み。並列性と AND join の意図は、共通上流 Step 5 完了時点を起点として検証する形で維持している。

#### FR-WF-ADFD-03 — 4 Step の `output_paths` 宣言により Self-Improve scope の path 直指定を維持
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestRunWorkflowSelfImprove::test_self_improve_default_scope_per_workflow`（`adfd` の期待 scope = `""`）
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestRunWorkflowSelfImprove::test_declared_workflows_keep_path_directed_scope`（`adfd` が covered=True）

#### FR-WF-ADFD-04 — 消費側が文字列一致で検査する見出しの固定
- 判定: △
- 直接対応テスト:
  - [hve/tests/test_adfd_dataflow_design_agents.py](hve/tests/test_adfd_dataflow_design_agents.py) :: `TestAdfdDataflowDesignPrompts::test_prompt_declares_single_output_path_in_output_contract` — Prompt 側 `<output_contract>` の出力パス固定のみ
- 補足: 生成後ドキュメントの見出し実体検査（`## 1. ジョブ一覧表` 等）は未実装。ADFD 実行後の成果物検証で担保する必要がある。

### §13.5 ABDV — Batch Dev

| Step | 判定 | 主な対応テスト |
|---|---|---|
| 1.1 データサービス選定 | ✗ | — |
| 1.2 データリソース Deploy | ✗ | — |
| 2.1 TDD RED テストコード (fan-out) | △ | [test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestABDVAgentNames` |
| 2.2 TDD GREEN 本実装 (fan-out) | △ | 同上 |
| 3 Functions/コンテナ Deploy | ✗ | — |
| 4.1 WAF レビュー | ✗ | — |
| 4.2 整合性チェック | ✗ | — |

### §13.6 AAG — AI Agent Design

| Step | 判定 | 主な対応テスト |
|---|---|---|
| 1 Agent アプリ定義 | △ | [test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestAAGAgentNames` |
| 2 Agent 粒度設計 (fan-out `agent_catalog`) | △ | 同上 + [test_fanout.py](hve/tests/test_fanout.py) :: `test_all_workflows_fanout_parsers_are_known` |
| 3 Agent 詳細設計 (fan-out) | △ | 同上 |

#### FR-WF-AAG-01 — 生成 AI Agent の Tool Search 方針は `auto` / `yes` / `no` の 3 値
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_tool_search_option_parity.py](hve/tests/test_tool_search_option_parity.py) :: 既定 `auto` と CLI 3 値の受理 — `TestConfigDefault` / `TestCliFlag`
  - [hve/tests/test_generated_agent_tool_search_policy_wiring.py](hve/tests/test_generated_agent_tool_search_policy_wiring.py) :: AAG 3 / AAGD 2.3 / 3 / 4 への同一値注入と非対象 Step 非影響 — `TestPolicyPrefixTargets`
  - [hve/tests/test_generated_agent_tool_search_policy_wiring.py](hve/tests/test_generated_agent_tool_search_policy_wiring.py) :: 3 値以外の fail-closed 拒否 — `test_unknown_policy_is_fail_closed` / `TestCapabilityGateForwardsPolicy`
  - [hve/tests/test_validate_agent_contract_cli.py](hve/tests/test_validate_agent_contract_cli.py) :: CLI wrapper の `--tool-search-policy` 伝搬
- 根拠: 方針値の解決を 1 箇所に集約し、Agent の自己判断や追加設定キーによる分岐を作らない。

#### FR-WF-AAG-02 — 設計成果物の方針別 TB-CAP 契約と Tool 集合の完全一致
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolbox_contract_validation.py](hve/tests/test_toolbox_contract_validation.py) :: 閾値ゲートと整合ルール R1〜R10
  - [hve/tests/test_toolbox_policy_validation.py](hve/tests/test_toolbox_policy_validation.py) :: `auto` 境界（閾値±1）/ `yes` 少数 Tool / `no` 多数・少数 Tool / 不正値 — `TestPolicyAuto` / `TestPolicyYes` / `TestPolicyNo` / `TestUnknownPolicy`
  - [hve/tests/test_toolbox_policy_validation.py](hve/tests/test_toolbox_policy_validation.py) :: TB-CAP-04 の欠落・余剰・重複 ID、`Pinned` 列と TB-CAP-03 の不一致 — `TestSearchMetadataCompleteness`
  - [hve/tests/test_validate_agent_contract_cli.py](hve/tests/test_validate_agent_contract_cli.py) :: CLI wrapper の方針引数が validator へ届く
  - [hve/tests/test_toolbox_prompt_contract.py](hve/tests/test_toolbox_prompt_contract.py) :: 設計 Prompt が 3 方針を指示する — `TestDesignPromptPolicy`
- 根拠: Tool 総数の一致だけでは、行数が合っていて中身が欠落した表を検出できない。

#### FR-WF-AAG-03 — 生成 AI Agent の Agentic Retrieval 方針を AAG 3 / AAGD 2.3 ・ 3 へ注入
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_generated_agent_agentic_retrieval_policy_wiring.py](hve/tests/test_generated_agent_agentic_retrieval_policy_wiring.py) :: 対象 Step への注入と非対象 Step（AAG 1 / 2、AAGD 1 / 2.1 / 2.2 / 4、他 workflow）の非影響 — `TestPolicyPrefixTargets`
  - [hve/tests/test_generated_agent_agentic_retrieval_policy_wiring.py](hve/tests/test_generated_agent_agentic_retrieval_policy_wiring.py) :: 3 値以外の fail-closed 拒否と Tool Search 方針との見出し衝突回避 — `test_unknown_policy_is_fail_closed` / `test_prefix_is_distinct_from_the_tool_search_prefix`
  - [hve/tests/test_generated_agent_agentic_retrieval_policy_wiring.py](hve/tests/test_generated_agent_agentic_retrieval_policy_wiring.py) :: capability gate への方針伝搬 — `TestCapabilityGateForwardsPolicy`
  - [hve/tests/test_agentic_retrieval_prompt_contract.py](hve/tests/test_agentic_retrieval_prompt_contract.py) :: 設計 / Deploy Prompt が 3 値と blocked を指示する — `TestDesignPromptPolicy` / `TestDeployPromptPolicy`
- 根拠: 方針値の解決を 1 箇所へ集約し、Agent の自己判断による経路選択の揺れを作らない。

#### FR-WF-AAG-04 — 方針別の AR-CAP 契約と Knowledge Source の下限・索引契約
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_agentic_retrieval_contract_validation.py](hve/tests/test_agentic_retrieval_contract_validation.py) :: Knowledge Source Matrix 1 行で FAIL / 2 行で PASS — `TestKnowledgeSourceLowerBound`
  - [hve/tests/test_agentic_retrieval_contract_validation.py](hve/tests/test_agentic_retrieval_contract_validation.py) :: `Index semantic configuration` の欠落と単語のみ `TBD` を FAIL — `TestIndexSemanticConfiguration`
  - [hve/tests/test_agentic_retrieval_contract_validation.py](hve/tests/test_agentic_retrieval_contract_validation.py) :: 方針 `auto` / `yes` / `no` 別の経路ゲートと 3 値以外の fail-closed — `TestAgenticRetrievalPolicyGating`
  - [hve/tests/test_agentic_retrieval_prompt_contract.py](hve/tests/test_agentic_retrieval_prompt_contract.py) :: 設計 Prompt が KS 2 件以上と索引契約を指示する — `TestDesignPromptSearchContract`
- 根拠: 1 行の Knowledge Base はクラシックな単一クエリ検索と等価であり、契約見出しの存在だけでは横断検索の前提を担保できない。

### §13.7 AAGD — AI Agent Dev & Deploy

| Step | 判定 | 主な対応テスト |
|---|---|---|
| 1 構成設計 | ✗ | — |
| 2.1 テスト仕様（RED）(fan-out) | △ | fan-out parser 登録テスト（[test_fanout.py](hve/tests/test_fanout.py)） |
| 2.2 テストコード（RED）(fan-out) | △ | 同上 |
| 2.3 実装（GREEN）(fan-out) | △ | 同上 |
| 3 Agent Deploy (fan-out) | △ | 同上 |
| 4 tool search 実測評価 (fan-out) | △ | [test_tool_search_eval_step.py](hve/tests/test_tool_search_eval_step.py)（registry 配線・Prompt 契約） |

#### FR-WF-AAGD-01 — 実装成果物と設計 TB-CAP の一致
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolbox_implementation_validation.py](hve/tests/test_toolbox_implementation_validation.py) :: Agent 設定の tool search 有効/無効・topology・`limit`・pin・検索語彙が設計と一致 — `TestToolboxImplementationGate`
  - [hve/tests/test_toolbox_implementation_validation.py](hve/tests/test_toolbox_implementation_validation.py) :: System Prompt の tool search 指示の存在
  - [hve/tests/test_toolbox_implementation_validation.py](hve/tests/test_toolbox_implementation_validation.py) :: 方針 `no` で Toolbox 設定が混入した場合の FAIL
  - [hve/tests/test_toolbox_tdd_contract.py](hve/tests/test_toolbox_tdd_contract.py) :: テスト仕様の TB-CAP トレース要求 — `TestTestSpecPrompt` / `TestAgentTestCodingPrompt`
- 根拠: SDK シンボル名は preview で変動するため固定値検証はせず、設定契約の一致だけを検証する。

#### FR-WF-AAGD-02 — Deploy 成果物の Toolbox 作成・検証契約
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolbox_deploy_validation.py](hve/tests/test_toolbox_deploy_validation.py) :: Agent 登録前の Toolbox 作成順序 — `test_toolbox_created_after_agent_registration_fails`
  - [hve/tests/test_toolbox_deploy_validation.py](hve/tests/test_toolbox_deploy_validation.py) :: `toolbox_search` / プレビューヘッダー / トークンスコープ / version 指定エンドポイント — `TestEnabledDeployArtifacts`
  - [hve/tests/test_toolbox_deploy_validation.py](hve/tests/test_toolbox_deploy_validation.py) :: 検証スクリプトの `tools/list` / pin 一致 / 発見→実行 / `limit` / 既定 version / fail-closed — `TestVerifyScriptContract`
  - [hve/tests/test_toolbox_deploy_validation.py](hve/tests/test_toolbox_deploy_validation.py) :: 方針 `no` で Toolbox 作成を含む場合の FAIL — `TestDisabledToolSearch`
  - [hve/tests/test_runner_ai_agent_capability_gate.py](hve/tests/test_runner_ai_agent_capability_gate.py) :: AAGD Step 3 の gate 接続 — `test_runner_gate_resolves_aagd_deploy_target`
- 根拠: Toolbox は managed resource で Agent コードと独立に変更できるため、設計値との乖離を静的に検出する。

#### FR-WF-AAGD-03 — 評価レポートの必須生成と測定構造
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_toolbox_eval_report_validation.py](hve/tests/test_toolbox_eval_report_validation.py) :: 評価クエリ 10 件以上・複数 Tool 3 件以上・期待 Tool 集合 — `TestEnabledReport`
  - [hve/tests/test_toolbox_eval_report_validation.py](hve/tests/test_toolbox_eval_report_validation.py) :: on / off 両条件・指標一覧・未測定理由・TB-CAP-02 結論
  - [hve/tests/test_toolbox_eval_report_validation.py](hve/tests/test_toolbox_eval_report_validation.py) :: 公開ベンチマーク値の実測欄流用を FAIL — `TestBenchmarkSubstitution`
  - [hve/tests/test_toolbox_eval_report_validation.py](hve/tests/test_toolbox_eval_report_validation.py) :: 対象外 Agent の理由付き N/A レポート — `TestReasonedNaReport` / `TestDisabledDesign`
  - [hve/tests/test_tool_search_eval_step.py](hve/tests/test_tool_search_eval_step.py) :: 方針 `no` での Step skip と固定ラベル契約 — `TestSkipResolutionActuallyWorks` / `TestPromptJudgement`
  - [hve/tests/test_runner_ai_agent_capability_gate.py](hve/tests/test_runner_ai_agent_capability_gate.py) :: AAGD Step 4 の gate 接続 — `test_runner_gate_resolves_aagd_eval_target`
- 根拠: 公開ベンチマーク値の流用を防ぐため、測定条件と未測定理由の存在を成果物側で検証する。

#### FR-WF-AAGD-04 — Cloud の方針パリティと完了時の成果物再検証
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_cloud_aag_tool_search_policy.py](hve/tests/test_cloud_aag_tool_search_policy.py) :: AAG Issue Form → Root メタデータ → Step 3 本文の一致と Post-DAG design gate
  - [hve/tests/test_cloud_aagd_tool_search_step.py](hve/tests/test_cloud_aagd_tool_search_step.py) :: AAGD の方針伝搬と `no` での Step 4 非生成 — `TestToolSearchPolicyPropagation`
  - [hve/tests/test_tool_search_option_parity.py](hve/tests/test_tool_search_option_parity.py) :: 3 面パリティ（Cloud 欠落の解消）— `TestParityMatrix`
  - [hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) :: `common` エントリの Issue Form フィールド実在検証
  - [hve/tests/test_cloud_aagd_gate.py](hve/tests/test_cloud_aagd_gate.py) :: ラベル GREEN でも成果物不正なら FAIL — `TestArtifactRevalidation`
- 根拠: Issue ラベルは Agent の自己申告に依存するため、ブランチ上の成果物で再確認しなければ偽 GREEN を防げない。

#### FR-WF-AAGD-05 — AAGD 2.1 / 2.2 への Skill 公開と Deploy ゲートの AR-CAP 照合
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: AAGD 2.1 / 2.2 の Skill 公開と 2.3 / 3 の非回帰、Step 4 非対象 — `TestAagdAgenticRetrievalSkillPublication`
  - [hve/tests/test_agentic_retrieval_deploy_validation.py](hve/tests/test_agentic_retrieval_deploy_validation.py) :: Toolbox 未選択でも AR-CAP 照合が走る — `test_gate_runs_without_a_toolbox_contract`
  - [hve/tests/test_agentic_retrieval_deploy_validation.py](hve/tests/test_agentic_retrieval_deploy_validation.py) :: KB 名 / KS 名の未参照と infra ディレクトリ不在で FAIL、非 Foundry IQ 設計は無影響 — `TestAgenticRetrievalDeployGate`
- 根拠: Toolbox 未採用の Agent では既存ゲートが先頭で return しており、AR-CAP 設計値と Deploy スクリプトの乖離を検出できない。

#### FR-WF-AAGD-06 — Agent Plugins 1.0.0 準拠の `plugin.json` 生成と検証
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_agent_plugin_manifest_validation.py](hve/tests/test_agent_plugin_manifest_validation.py) :: ファイル不在 / JSON 不正 / 非オブジェクト root — `TestManifestPresence`
  - [hve/tests/test_agent_plugin_manifest_validation.py](hve/tests/test_agent_plugin_manifest_validation.py) :: `$schema` の固定値検証 — `TestSchemaIdentifier`
  - [hve/tests/test_agent_plugin_manifest_validation.py](hve/tests/test_agent_plugin_manifest_validation.py) :: `name` 制約（大文字 / 先頭末尾 / `--` / `..` / 64 境界 / 空 / period 許容）と `{key}` 小文字化一致 — `TestNameConstraints`
  - [hve/tests/test_agent_plugin_manifest_validation.py](hve/tests/test_agent_plugin_manifest_validation.py) :: closed schema 違反の FAIL と仕様 optional フィールドの受容 — `TestClosedSchema`
  - [hve/tests/test_agent_plugin_manifest_validation.py](hve/tests/test_agent_plugin_manifest_validation.py) :: 実装ゲートへの組み込み — `TestImplementationGateIntegration`
  - [hve/tests/test_agent_plugin_prompt_contract.py](hve/tests/test_agent_plugin_prompt_contract.py) :: AgentCoding Prompt の生成指示と MCP 設定非生成境界 — `TestManifestOutput` / `TestManifestBoundaries`
- 根拠: 仕様 §5.1 により `plugin.json` が無いと適合 client はコンポーネントを一切 discover できない。

#### FR-WF-AAGD-07 — `SKILL.md` frontmatter の長さ制約
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_ai_agent_capability_validation.py](hve/tests/test_ai_agent_capability_validation.py) :: `name` 65 文字 / `description` 1025 文字で FAIL、境界値 64 / 1024 で PASS — `test_skill_name_longer_than_64_characters_fails` / `test_skill_description_longer_than_1024_characters_fails` / `test_skill_name_at_the_length_limit_passes` / `test_skill_description_at_the_length_limit_passes`
- 根拠: 既存検証は kebab-case 形状と有意性のみで、Agent Skills 仕様の長さ上限を検出できない。

#### FR-WF-AAGD-08 — Step 6 検索経路適正化レポートの固定フォーマット
- 判定: ✓（既存実装の明文化。GREEN：37 passed / 21 subtests passed）
- 直接対応テスト:
  - [hve/tests/test_agent_capability_steps.py](hve/tests/test_agent_capability_steps.py) :: `TestRouteRightsizingReport` — 測定条件ラベル 8 件、比較表 7 列、2 行未満の拒否、判定語彙 4 値
  - [hve/tests/test_agent_capability_steps.py](hve/tests/test_agent_capability_steps.py) :: `TestRunnerGateWiring` — `docs/agent/route-rightsizing-report.md` への成果物ゲート結線
- 受入ケース:
  - `Schema-Version` / `Workflow` / `Step` / `Agent` / `Measured-At` / `Dataset` / `Dataset-Size` / `Secret-Redaction` を各 1 行で持つ。
  - 比較表 `| Rung | Route | Accuracy | Tokens | Latency | Judgement | Evidence |` が 2 行以上を持つ。1 行の比較表を受理しない。
  - `Judgement` は `KEEP` / `DOWNGRADE` / `INSUFFICIENT` / `NOT_MEASURED` の 4 値だけを許す。
  - `- Conclusion:` / `- Rationale:` / `- Recommended-Route:` を持つ。
- 根拠: 実装側（`artifact_validation.py` / `runner.py` / 共有 Prompt）で契約が確定していた一方、規範文書に対応要件がなく変更時の判断根拠を持てなかった（TBD-26）。

#### FR-WF-AAGD-09 — Step 7 Microsoft 365 公開レポートの固定フォーマット
- 判定: ✓（既存実装の明文化。GREEN：37 passed / 21 subtests passed）
- 直接対応テスト:
  - [hve/tests/test_agent_capability_steps.py](hve/tests/test_agent_capability_steps.py) :: `TestM365PublishReport` — 公開条件ラベル 8 件、公開表 7 列、判定語彙 4 値
  - [hve/tests/test_agent_capability_steps.py](hve/tests/test_agent_capability_steps.py) :: `TestRunnerGateWiring` — `docs/agent/m365-publish-report.md` への成果物ゲート結線
- 受入ケース:
  - `Schema-Version` / `Workflow` / `Step` / `Agent` / `Published-At` / `Publish-Scope` / `Auth-Scheme` / `Secret-Redaction` を各 1 行で持つ。
  - 公開表 `| Agent Key | Channel | Publish Scope | App Version | Judgement | Approval | Evidence |` が 1 行以上を持つ。
  - `Judgement` は `PUBLISHED` / `PENDING_APPROVAL` / `NOT_SELECTED` / `FAILED` の 4 値だけを許す。
  - `- Conclusion:` / `- Rationale:` / `- Consumer-Setup:` を持つ。
  - 公開メタデータへ secret・API キー・接続文字列・内部 URL を含めない（NFR-SEC-01）。
- 根拠: FR-WF-AAGD-08 と同じ（TBD-26）。


### §13.8 AKM — Knowledge Management

| Step | 判定 | 主な対応テスト |
|---|---|---|
| 1 knowledge ドキュメント生成 (D01〜D21 fan-out) | ✓ | [test_fanout.py](hve/tests/test_fanout.py) :: `test_akm_has_fanout_21_keys`、`test_akm_max_parallel_is_21`、`test_akm_fanout_expander_produces_21_children`、`test_dag_executor_expands_akm_to_21_parallel`、`test_dag_executor_runs_all_children`<br>[test_e2e_akm_fanout_dryrun.py](hve/tests/test_e2e_akm_fanout_dryrun.py) :: `test_akm_dryrun_invokes_21_children`、`test_akm_dryrun_stderr_emits_21_step_starts`<br>[test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestAKMWorkflow` |
| 2 横断整合性レビュー (join) | ✓ | [test_fanout.py](hve/tests/test_fanout.py) :: `test_akm_has_review_join_step` |

横断（AKM 全体）:
- WorkIQ 連携: [test_akm_workiq_phase.py](hve/tests/test_akm_workiq_phase.py)（全関数）、[test_akm_workiq_ingest.py](hve/tests/test_akm_workiq_ingest.py)（全クラス）、[test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) :: `TestAkmWorkflowEnableReview`、`TestEnableAutoMerge`

### §13.9 ADI に統合した原本質問票処理

| Step | 判定 | 主な対応テスト |
|---|---|---|
| 1.1 質問票生成（D01〜D21 fan-out） | ✓ | [hve/tests/test_adi.py](hve/tests/test_adi.py) :: `test_adi_questionnaire_steps_contract`<br>[hve/tests/test_fanout.py](hve/tests/test_fanout.py) :: `test_adi_questionnaire_fanout_produces_21_children`<br>[hve/tests/test_adi_validation.py](hve/tests/test_adi_validation.py) :: `test_explicit_zero_questionnaire_is_valid` / `test_silent_zero_questionnaire_is_invalid` / `test_questionnaire_run_detects_step_outputs`<br>[hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestNormalizeAdiTargetScope` |
| 1.2 横断質問票 join | ✓ | [hve/tests/test_adi.py](hve/tests/test_adi.py) :: `test_adi_questionnaire_steps_contract` / `test_adi_step_dependencies_are_serial`<br>[hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestADIQuestionnaireWorkflow.test_adi_questionnaire_steps`<br>[hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestAdiQuestionnairePostDag` |

### §13.10 ADI — Auto Design-doc Ingestion（統合後）

| 要件 | 判定 | 主な対応テスト |
|---|---|---|
| FR-WF-ADI-12 — AKM が routing を優先し、ADI 1.1 / 1.2 は正規化済み入力を使う | ✓ | [hve/tests/test_adi_downstream_contract.py](hve/tests/test_adi_downstream_contract.py) :: `test_fanout_common_references_routing_table` / `test_fanout_common_declares_backward_compatible_fallback` / `test_adi_questionnaire_fanout_reads_normalized_content_without_routing` |
| FR-WF-ADI-17 — Step 1.1 の入出力・scope・0件質問 | ✓ | [hve/tests/test_adi.py](hve/tests/test_adi.py) :: `test_adi_questionnaire_steps_contract`<br>[hve/tests/test_fanout.py](hve/tests/test_fanout.py) :: `test_adi_questionnaire_fanout_produces_21_children`<br>[hve/tests/test_adi_validation.py](hve/tests/test_adi_validation.py) :: `test_explicit_zero_questionnaire_is_valid` / `test_silent_zero_questionnaire_is_invalid`<br>[hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestNormalizeAdiTargetScope` |
| FR-WF-ADI-18 — Step 1.2 join・Step 2 順序・main成果物検証 | ✓ | [hve/tests/test_adi.py](hve/tests/test_adi.py) :: `test_adi_questionnaire_steps_contract` / `test_adi_step_dependencies_are_serial`<br>[hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestAdiQuestionnairePostDag`<br>[hve/tests/test_main.py](hve/tests/test_main.py) :: `TestBuildParams.test_adi_params_defaults` / `test_adi_params_custom_values` |

### §13.11 ADOC — Source Code → Documentation

> **判定の意味**: ADOC 各 Step の `✓` は「**テンプレ存在性 + プレースホルダ + Step 数 registry 一致**」までであり、Step ごとの個別出力検証ではない。TBD-14 解消後に再評価が必要。

| Step | 判定 | 主な対応テスト |
|---|---|---|
| 1 ファイルインベントリ | ✓（テンプレ整合性レベル） | [test_adoc_template_parity.py](hve/tests/test_adoc_template_parity.py) :: `TestAdocTemplateFilesExist`、`TestAdocTemplatePlaceholders`、`TestAdocTemplateRendering`、`TestAdocStepCountMatchesRegistry`<br>[test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestADOCWorkflow` |
| 2.1〜2.5 ファイルサマリー | ✓ | 同上（テンプレ存在性） |
| 3.1 コンポーネント設計書 | ✓ | 同上 |
| 3.2 API 仕様書 | ✓ | 同上 |
| 3.3 データモデル定義書 | ✓ | 同上 |
| 3.4 テスト仕様サマリー | ✓ | 同上 |
| 3.5 技術的負債一覧 | ✓ | 同上 |
| 4 コンポーネントインデックス | ✓ | 同上 |
| 5.1 アーキテクチャ概要 | ✓ | 同上 |
| 5.2 依存関係マップ | ✓ | 同上 |
| 5.3 インフラ依存分析 | ✓ | 同上 |
| 5.4 非機能要件分析 | ✓ | 同上 |
| 6.1 オンボーディングガイド | ✓ | 同上 |
| 6.2 リファクタリングガイド | ✓ | 同上 |
| 6.3 移行アセスメント | ✓ | 同上 |

根拠: テンプレ整合性とステップ数が登録ワークフローと一致することを `TestAdocStepCountMatchesRegistry` が検証。Step 単体の出力ファイル検証は TBD-14 のとおり未登録。

### §13.12 ARD — Auto Requirement Definition

> **判定の意味**: fan-out 系 Step の `✓` は「**parser 動作 + registry 登録**」を意味し、個別子ステップの出力ファイル生成検証ではない。

| Step | 判定 | 主な対応テスト |
|---|---|---|
| 1 事業分野候補列挙 | ✓ | [test_workflow_registry_ard.py](hve/tests/test_workflow_registry_ard.py) :: `TestARDWorkflowRegistration`、`TestARDDisplayNames` |
| 1.1 事業分野別深掘り (fan-out `business_candidate`) | ✓（parser レベル） | [test_workflow_registry_ard.py](hve/tests/test_workflow_registry_ard.py) :: `TestBusinessCandidateParser`、`TestNewParsersRegistered` |
| 1.2 事業分析統合 | ✓ | `TestARDWorkflowRegistration` |
| 2 対象業務深掘り | ✓ | [test_orchestrator_ard.py](hve/tests/test_orchestrator_ard.py) :: `TestOrchestratorARD`<br>[test_ard_target_business_resolver.py](hve/tests/test_ard_target_business_resolver.py)（全 22 関数）<br>[test_ard_target_business_prompt.py](hve/tests/test_ard_target_business_prompt.py) :: `TestARDTargetBusinessPrompt` |
| 2.1 KPI/OKR 定義（任意） | ✓ | [test_orchestrator_ard.py](hve/tests/test_orchestrator_ard.py) :: `TestOrchestratorARD.test_include_kpi_okr_false_excludes_step_2_1` / `test_include_kpi_okr_true_includes_step_2_1`（直接flag互換）、[test_main_ard.py](hve/tests/test_main_ard.py)（グループ3を唯一のwizard状態として固定。RED: B2 13 failed → GREEN: 49 passed） |
| 3.1 ユースケース骨格抽出 | ✓ | `TestARDWorkflowRegistration` |
| 3.2 ユースケース詳細生成 (fan-out `use_case_skeleton`) | ✓（parser レベル） | [test_workflow_registry_ard.py](hve/tests/test_workflow_registry_ard.py) :: `TestUseCaseSkeletonParser`、`TestNewParsersRegistered` |
| 3.3 ユースケースカタログ統合 | ✓ | `TestARDWorkflowRegistration` |

横断:
- [test_ard_recommendations.py](hve/tests/test_ard_recommendations.py)（全 11 関数） — `target_recommendation_id` 注釈ロジック
- [test_main_ard.py](hve/tests/test_main_ard.py) — ARD CLI 引数全体

#### FR-WF-ARD-02 — ユーザー提供資料の一次情報優先明示
- 判定: ✓
- 直接対応テスト:
  - [hve/tests/test_ard_attached_docs_priority.py](hve/tests/test_ard_attached_docs_priority.py) :: `TestArdAttachedDocsPriority` — Untargeted Prompt の `## 2) 入力（必ず参照）` 節と `templates/ard/step-1.md` の `## 入力` 節に最優先参照規定があること、Untargeted 本文の `{添付資料}` プレースホルダが保持されていること、Targeted 側の既存規定と `templates/ard/step-2.md` の `{attached_docs}` / `{target_business}` が保たれていること（RED: 2 failed → GREEN: 5 passed）

#### FR-WF-ARD-03 — ARDの5表示グループ・10実Step・既定tuple・recommendation伝搬
- 判定: ✓（RED: 既存4グループ / 8 Step契約はGREEN、新規5グループ / 10 Step契約は失敗 → GREEN: 3ファイル合計 **75 passed**）
- 直接対応テスト:
  - [hve/tests/test_ard_requirement_parity.py](hve/tests/test_ard_requirement_parity.py) — §13.12の実Step集合・グループ対応・既定tupleをregistryと照合
  - [hve/tests/test_main_ard.py](hve/tests/test_main_ard.py) — 直接CLI / wizardの既定tuple、wizard KPI単一状態、およびモード別recommendation事前入力プロンプトの有無（wizard表示層）
  - [hve/tests/test_orchestrator_ard.py](hve/tests/test_orchestrator_ard.py) — `target_recommendation_id`のeffective params伝搬、custom-auto明示選択、manual実行時メニュー保持（値伝搬・選択層）
- 関連GUI契約:
  - [hve/gui/tests/test_page_workflow_select_ard_defaults.py](hve/gui/tests/test_page_workflow_select_ard_defaults.py) — GUI既定値が同じtuple由来であること
  - [hve/gui/tests/test_workflow_required_input_fields.py](hve/gui/tests/test_workflow_required_input_fields.py)、[hve/gui/tests/test_options_page_required_input_persistence.py](hve/gui/tests/test_options_page_required_input_persistence.py) — SR-IDの表示・保存・CLI argv伝搬

#### FR-WF-ARD-04 / FR-WF-AAS-02 — ARD 4.1/4.2 と AAS Step 1 root
- 判定: ✓（RED: 2ファイル合計 9 failed / 1 passed → GREEN: **10 passed**）
- 補足: 非 fan-out Step は fan-out キー別名を代入できないため、Step 4.2 の `output_paths_template` は glob `docs/architectural-requirements-app-*.md` を宣言する（`{appId}` 宣言は `test_output_paths_template_resolvability.py` と `workflow_diff_gate` の不変条件に反する）。
- 直接対応テスト:
  - [hve/tests/test_application_requirement_workflow.py](hve/tests/test_application_requirement_workflow.py) — ARD 5グループ / 10 Step、4.1/4.2 の依存・Agent・出力、Step 4.2 のAPP全件coverageとorphan非削除、旧 AAS Step 1 不在と旧 Step 2 root（AAS Step.1 起点化により現在は Step 1 root へ再昇格。`test_aas_starts_at_step_1_after_renumbering` で固定）、ADA Step 1 も ARD Step 4.1 へ移管し廃止したことを固定
  - [hve/tests/test_application_requirement_io_contracts.py](hve/tests/test_application_requirement_io_contracts.py) — ARD 4.1/4.2 の scoped contract、AAS 1（旧 2）の必須 producer、旧 AAS 1 producer 参照 0 件、registry mismatch 0 件を固定
- （2026-08-25 追記・仕様変更）ADA Step 1（`Arch-ApplicationAnalytics` による `app-catalog.md` 生成）は AAS Step 1 と同一理由で ARD Step 4.1 へ移管し廃止した。`hve-dev/requirement-definition.md` の FR-WF-ARD-04 を「ADA Step 1 は初版では維持する」から「ADA Step 1 も ARD Step 4.1 へ移管して廃止した」へ改訂した上で実装した（仕様変更を実装前に規範要件へ反映）。RED: `test_ada_step_1_is_intentionally_preserved` 等 6 failed（registry / io-contract producer / reusable workflow / テスト定数の不整合）→ GREEN: `hve/workflow_registry.py`（ADA Step 1 削除、Step 2 を root 化）、9 件の io-contract の `producer` を `Arch-ApplicationAnalytics--ard--4.1` へ更新、`.github/io-contracts/Arch-ApplicationAnalytics--ada--1.yaml` と `.github/scripts/templates/ada/step-1.md` を削除、Bash registry (`workflow-registry.sh`) と Cloud reusable workflow (`auto-agent-data-architecture-reusable.yml`) を同期。`test_application_requirement_workflow.py` / `test_ada_workflow.py` / `test_ada_cloud_surface.py` / `test_workflow_registry.py` 合計 **266 passed, 1 skipped**。`validate-io-contract.py` は Agents checked 149 / Schema errors 0 / Integrity errors 0 / Registry mismatch errors 0。PowerShell registry (`workflow-registry.ps1`) には ADA 定義が存在しないため対象外（既存ギャップ、本変更のスコープ外）。
- （追記・AAS Step.1 起点化）AAS 自身の旧 Step "2"（root、`Arch-ArchitectureCandidateAnalyzer`）を新 Step "1" へ昇格し、以降の全 Step ID を 1 つ繰り上げた（詳細は `hve-dev/requirement-definition.md` §13.1 FR-WF-AAS-03）。`test_aas_starts_at_existing_step_2_without_renumbering` は `test_aas_starts_at_step_1_after_renumbering` へ改名し、期待値を新 Step ID 集合へ更新。`test_aas_step_2_requires_the_app_requirement_producer` は `test_aas_step_1_requires_the_app_requirement_producer` へ改名し、参照 io-contract を `Arch-ArchitectureCandidateAnalyzer--aas--1.yaml` へ更新。

<!-- validation-confirmed -->



#### FR-APPREQ-01 / 02 — APP要求文書 schema・stable ID・upsert
- 判定: ✓（RED: 2ファイル合計 16 failed → GREEN: **28 passed**）
- 直接対応テスト:
  - [hve/tests/test_application_requirements.py](hve/tests/test_application_requirements.py) — canonical path、APP-ID / requirement ID、001〜999境界、固定表 schema、status / blocker allowlist、重複拒否、未解決 Blocker、confirmed/source-backed ID保持、confirmed 内容保持、orphan非削除を固定
  - [hve/tests/test_application_requirement_prompt_contract.py](hve/tests/test_application_requirement_prompt_contract.py) — Prompt が出典優先順位・upsert・再番号禁止・単一Agent順次処理を指示することを固定
- （2026-08-25 追記・実データ投入）`docs/architectural-requirements-app-*.md` が0件のため fail-closed ゲートで AAS/ADA/AAR 等の下流 9 Workflow が起動不能だった状態を解消した。`docs/catalog/app-catalog.md` §4（APP一覧）を根拠に APP-001〜014 の14件を新規生成（ARD Step 4.2 契約に準拠、Requirement は Primary UC × FR、キーNFR列 × NFR、留意点/TBD列 × C（Status=TBD, Blocker=no）で構成、Source は `use-case-catalog.md#UC-NN` / `app-catalog.md#APP-NNN` を引用）。検証: `validate_requirement_document` 14/14 エラー0、`validate_requirement_coverage` で app_ids 14件一致・errors 0・orphan 0、TBDかつBlocker=yes の行0件、APP名がapp-catalog.md §4と14件全一致。`get_meta_dependencies` ベースのgate再現で aas/ada/aar いずれも前提成果物欠落なし（下流起動可能）を確認。副作用として `test_application_requirement_io_contracts.py::test_all_63_scoped_app_catalog_references_move_to_ard` が T-C（ADA Step 1移管）分の producer 参照9件増加により63→72件が正となり、テスト名と期待値を `test_all_72_scoped_app_catalog_references_move_to_ard` へ更新した。`hve/tests/test_application_requirement*.py` 5ファイル合計 **51 passed**。

<!-- validation-confirmed -->


#### FR-APPREQ-03 / 04 / 05 — 下流選択参照・fail-closed・trace block・3面配線
- 判定: ✓（RED: 3ファイル合計 19 failed → GREEN: **27 passed**）
- 補足: Cloud は fan-out key ごとの子 Issue を作らず固定 Step Issue だけを作るため、共有 preflight / completion gate は `fanout_meta=None` で呼ぶ。実効 APP スコープは Step Issue body の `<!-- app-ids: ... -->` から復元し、catalog 生成側の AAS / ADFD だけが分類内全 APP への fallback を使う。
- 直接対応テスト:
  - [hve/tests/test_application_requirement_traceability.py](hve/tests/test_application_requirement_traceability.py) — 対象9 Workflow、APP / 画面 / サービス fan-out と非fan-outのAPP scope、欠損 / 構造不正 / Blocker の strict停止、canonical pathのみのprompt注入、trace blockの4キーと実在ID検証を固定
  - [hve/tests/test_application_requirement_skill_wiring.py](hve/tests/test_application_requirement_skill_wiring.py) — Skill、workflow default、agent-common-preambleルーター、既存Skill再利用、新規依存不在を固定
  - [hve/tests/test_ard_cloud_surface.py](hve/tests/test_ard_cloud_surface.py) — Issue Form、dispatcher trigger/done/closed、qa-ready、reusable workflow、Bash registry parity、Cloud未選択時group 2〜5を固定
- （2026-08-25 追記・bugfix）対象9 Workflowのうち `ada` / `aar` だけ `get_meta_dependencies()` がメタ依存を宣言しておらず、前提成果物（`app-catalog.md` 等）が無くても起動時に即停止しない抜け穴だった（他7 Workflowは `aas` 等への既存メタ依存経由で間接的にゲートされていたため顕在化していなかった）。RED: `test_get_meta_dependencies_for_app_requirement_consumers[ada]` / `[aar]` 2 failed → GREEN: `hve/workflow_registry.py` の `FULL_PIPELINE.dependencies` へ `ada` / `aar` それぞれに `ard`（`soft=False`）への依存と `docs/catalog/app-catalog.md` / `docs/catalog/use-case-catalog.md` / `docs/architectural-requirements-app-*.md` の `required_artifacts` を追加。[hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) :: `TestMetaWorkflow` 6 passed。

<!-- validation-confirmed -->

### §13.13 ゲート条件

| ゲート | 判定 | 主な対応テスト |
|---|---|---|
| G-OUT（実行時解決済み必須成果物だけの存在） | ✓ | [test_workflow_gate_scope_contract.py](hve/tests/test_workflow_gate_scope_contract.py)（non-fanout宣言専用面の除外）、[test_data_model_split_contract.py](hve/tests/test_data_model_split_contract.py)（optional sidecar宣言と実行時除外。REDは同ファイル内11 failed → GREEN 25 passed）、[test_runner_split_required_guard.py](hve/tests/test_runner_split_required_guard.py) :: `TestCheckOutputPathsGate`（固定output_pathsゲート） |
| G-IN（required_input_paths 充足） | ✓ | [test_input_artifact_check.py](hve/tests/test_input_artifact_check.py) 全クラス |
| G-LBL（Cloud完了判定だけのdone/running/blocked状態） | ✓ | [test_workflow_gate_scope_contract.py](hve/tests/test_workflow_gate_scope_contract.py)（Cloudのcleanup-before-done、API/JSON/競合時fail-closed、close前後の再検証、全prefix。B4 RED 1 failed → 同ファイル GREEN 14 passed）、[test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) :: `TestLabelStateMachineFixWorkflows`（既存状態機械の非回帰）、[test_template_engine.py](hve/tests/test_template_engine.py)（local done指示なし）。[test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestDoneLabeling` はCLI `--create-issues`の補助通知を検証するだけで、本ゲートの根拠には用いない |
| G-CONS（AKMだけの21ドキュメント一貫性） | △ | [test_workflow_gate_scope_contract.py](hve/tests/test_workflow_gate_scope_contract.py)（固定/テンプレート両宣言面のAKM限定characterization）、[test_akm_workiq_phase.py](hve/tests/test_akm_workiq_phase.py) 全関数（既存の間接的整合性レビュー） |
| G-DIFF（実際にPRが作成されたrunだけの差分品質） | ✓ | [test_workflow_diff_gate.py](hve/tests/test_workflow_diff_gate.py)（exact / directory / segment-aware glob / fan-out / prefix / optional template / constrained placeholder、全13 Workflow policy、HVE scope遮断、path/status/rename/copy、identity、決定性・provenance）、[test_github_api.py](hve/tests/test_github_api.py) :: `TestListPullRequestFiles`（全ページ、3,000 files上限、metadata件数照合、途中失敗、非list、rename/copy、patch破棄）、[test_validate_workflow_diff.py](.github/scripts/tests/test_validate_workflow_diff.py)（PASS / BLOCKED / N/A、UTF-8/BOM、malformed JSON、root/symlink confinement、trusted import）、[test_workflow_diff_gate_cloud.py](hve/tests/test_workflow_diff_gate_cloud.py)（trusted二重checkout、subject code非実行、Cloud synthetic fixture、auto-approve直接gate、required context）、[test_orchestrator.py](hve/tests/test_orchestrator.py) :: `TestCreatePrIfNeeded` / `TestDeleteLocalMergedBranch`（marker、実PR差分、label順序、BLOCKED伝播）。実測: core統合145 passed、CLI/validator 138 passed・2 symlink tests skipped（Windows権限制約）、Cloud/auto-approve 80 passed、local PR回帰56 passed |

### §13.14 要件適合実測（FR-WF-CONF）

| 要件 | 判定 | 主な対応テスト |
|---|---|---|
| FR-WF-CONF-01 — 4 workflow の実測 Step と依存 | ✓ | [test_requirements_conformance_step.py](hve/tests/test_requirements_conformance_step.py) — registry / template / Prompt / Skill 配線。加えて [.github/scripts/powershell/tests/workflow-registry.Tests.ps1](.github/scripts/powershell/tests/workflow-registry.Tests.ps1) がPowerShell面のADFDV Step `4.3`と依存を固定し、[test_powershell_workflow_registry_parity.py](hve/tests/test_powershell_workflow_registry_parity.py) がPython正本との一致を固定 |
| FR-WF-CONF-02 — 固定レポート形式 | ✓ | [test_requirements_conformance_validation.py](hve/tests/test_requirements_conformance_validation.py) — 必須ラベル・測定表・結論・簡素化候補 |
| FR-WF-CONF-03 — 4 値判定語彙 | ✓ | [test_requirements_conformance_validation.py](hve/tests/test_requirements_conformance_validation.py) — `PASS` / `FAIL` / `NOT_MEASURED` / `NO_TARGET` |
| FR-WF-CONF-04 — 測定用 Azure リソース作成の非必須化 | ✓ | [test_requirements_conformance_step.py](hve/tests/test_requirements_conformance_step.py) — Prompt / Skill の禁止契約 |
| FR-WF-CONF-05 — Headroom と簡素化候補 | ✓ | [test_requirements_conformance_validation.py](hve/tests/test_requirements_conformance_validation.py) — `Headroom` / `Simplification-Candidate` 検証 |
| FR-WF-CONF-06 — CLI / GUI / Cloud の 3 面対応 | ✓ | [test_workflow_registry.py](hve/tests/test_workflow_registry.py) / [test_cloud_reusable_workflow_parity.py](hve/tests/test_cloud_reusable_workflow_parity.py) / [test_cloud_dispatcher_asdw_dispatch.py](hve/tests/test_cloud_dispatcher_asdw_dispatch.py) |

### §13.15 ADA（Agent Data Architecture）

画面を持たないデータ中心 AI Agent 向けのアーキテクチャ設計ワークフロー。
`ARD → ADA → AAG → AAGD` のチェーンで AAS を置き換える。

| 要件 | 判定 | 主な対応テスト |
|---|---|---|
| ADA-1 — ADA を registry へ登録し 10 Step を固定 | ✓ | [test_ada_workflow.py](hve/tests/test_ada_workflow.py) / [test_workflow_registry.py](hve/tests/test_workflow_registry.py)（`EXPECTED_STEP_COUNTS["ada"] == 10`） |
| ADA-2 — AAS の画面系 3 系統 Step を除外 | ✓ | [test_ada_workflow.py](hve/tests/test_ada_workflow.py) — 画面カタログ / 画面設計 / サービスカタログマトリクス / Azure サービス選定を持たないこと |
| ADA-3 — 非構造化データ資産カタログ（Step 8）と検索経路候補 | ✓ | [test_ada_workflow.py](hve/tests/test_ada_workflow.py) — `Arch-AgentDataAsset` の `output_paths` と `required_skills` |
| ADA-4 — Step 7 のサービス fan-out | ✓ | [test_ada_workflow.py](hve/tests/test_ada_workflow.py) / [test_output_paths_template_resolvability.py](hve/tests/test_output_paths_template_resolvability.py) |
| ADA-5 — AAG / AAGD 入力の付け替え（画面系を任意化、ADA 成果物を必須化） | ✓ | [test_ada_workflow.py](hve/tests/test_ada_workflow.py) / [test_ai_agent_capability_contract.py](hve/tests/test_ai_agent_capability_contract.py) :: `test_scoped_io_registry_and_runner_paths_are_identical` |
| ADA-6 — CLI / GUI / Cloud の 3 面対応 | ✓ | [test_ada_cloud_surface.py](hve/tests/test_ada_cloud_surface.py) / [test_cloud_dispatcher_asdw_dispatch.py](hve/tests/test_cloud_dispatcher_asdw_dispatch.py) / [test_workflow_categories.py](hve/tests/test_workflow_categories.py) / [test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) |
| ADA-7 — 小数 Step ID を壊さない Cloud 状態遷移 | ✓ | [test_ada_cloud_surface.py](hve/tests/test_ada_cloud_surface.py) :: `test_state_transition_handles_decimal_step_ids` |

### §13.16 AI Agent 共通能力契約の拡張（AG-CAP-07〜10）

| 要件 | 判定 | 主な対応テスト |
|---|---|---|
| AG-CAP-07 — Agent Identity & Authorization | ✓ | [test_ai_agent_capability_contract.py](hve/tests/test_ai_agent_capability_contract.py) / [test_ai_agent_capability_validation.py](hve/tests/test_ai_agent_capability_validation.py) |
| AG-CAP-08 — Observability Contract | ✓ | 同上 |
| AG-CAP-09 — Distribution & Packaging（理由付き N/A 可） | ✓ | 同上 |
| AG-CAP-10 — Evaluation & Route Right-sizing | ✓ | 同上 |
| 契約 ID の runtime gate 反映 | ✓ | [test_ai_agent_capability_validation.py](hve/tests/test_ai_agent_capability_validation.py) — `_AI_AGENT_CONTRACT_HEADINGS` の 10 契約すべてでセクション欠落を検出 |
| 検索経路コスト階段（過剰設計の抑止） | ✓ | [test_ai_agent_capability_contract.py](hve/tests/test_ai_agent_capability_contract.py) — `search-routing.md` §4.1〜4.3 の参照契約 |

### §13.17 AAGD Step.6 / Step.7（AG-CAP-10 実測 / AG-CAP-09 公開）

| 要件 | 判定 | 主な対応テスト |
|---|---|---|
| AAGD Step.6 の registry / template / Prompt / io-contract 配線 | ✓ | [test_agent_capability_steps.py](hve/tests/test_agent_capability_steps.py) :: `TestRegistryWiring` / `TestPromptAndTemplate` |
| 2 段以上の比較実測を強制（1 段は `INSUFFICIENT`） | ✓ | [test_agent_capability_steps.py](hve/tests/test_agent_capability_steps.py) :: `test_single_rung_is_rejected` |
| 判定 4 値と未実測理由の強制 | ✓ | [test_agent_capability_steps.py](hve/tests/test_agent_capability_steps.py) :: `TestRouteRightsizingReport` |
| AAGD Step.7 の公開レポート固定形式 | ✓ | [test_agent_capability_steps.py](hve/tests/test_agent_capability_steps.py) :: `TestM365PublishReport` |
| 公開していないのに `PUBLISHED` と書けない | ✓ | [test_agent_capability_steps.py](hve/tests/test_agent_capability_steps.py) :: `test_published_without_app_version_is_rejected` |
| runner gate の発火条件（Agent × workflow × step） | ✓ | [test_agent_capability_steps.py](hve/tests/test_agent_capability_steps.py) :: `TestRunnerGateWiring` |
| Cloud 面（bash registry / reusable workflow の Step 生成と連鎖） | ✓ | [test_agent_capability_steps.py](hve/tests/test_agent_capability_steps.py) :: `TestCloudSurface` / [test_workflow_registry.py](hve/tests/test_workflow_registry.py)（`aagd == 9`） |

### §13.18 Agent Plugin `mcp.json`（AG-CAP-09）

| 要件 | 判定 | 主な対応テスト |
|---|---|---|
| 設計が採用したときだけ生成し、未採用の同梱を拒否 | ✓ | [test_agent_plugin_mcp_config_validation.py](hve/tests/test_agent_plugin_mcp_config_validation.py) :: `TestPresenceContract` |
| closed schema と `$schema` の版一致 | ✓ | 同上 :: `TestSchemaContract` |
| transport 3 値と stdio / remote のフィールド排他 | ✓ | 同上 :: `TestTransportBoundary` |
| 非 loopback の HTTPS 必須・user-info / fragment 禁止 | ✓ | 同上 :: `TestUrlContract` |
| `headers` / `env` への資格情報埋め込み禁止・予約変数の再定義禁止 | ✓ | 同上 :: `TestCredentialContract` |
| 実装 Prompt の条件付き生成契約 | ✓ | [test_agent_plugin_prompt_contract.py](hve/tests/test_agent_plugin_prompt_contract.py) :: `TestManifestBoundaries` |


---

## §H 補助テストファイル（FR への直接寄与は薄いが品質保証に寄与）

| テストファイル | 主な役割 | 関連 FR |
|---|---|---|
| [test_prompt_loader.py](hve/tests/test_prompt_loader.py) | Prompt 定義ファイル読込（旧 `test_agent_loader.py`。Agent → Prompt / io-contracts 移行で置換） | FR-COMMON-01 周辺 |
| [test_console.py](hve/tests/test_console.py) | Console 出力全般（44 クラス） | NFR-OBS-03 / NFR-A11Y-01 |
| [test_prompts.py](hve/tests/test_prompts.py) | プロンプト雛形整合性 | FR-CLOUD-10〜11 周辺 |
| [test_questionnaire_ui.py](hve/tests/test_questionnaire_ui.py) | 質問票 UI/非 TTY | FR-CLI-11、FR-CLI-13 |
| [test_runner.py](hve/tests/test_runner.py) | StepRunner 詳細 | FR-MODEL-02 / NFR-SEC-01 |
| [test_runner_file_tracking.py](hve/tests/test_runner_file_tracking.py) | 生成ファイルトラッキング | FR-WF-OUT-01 周辺 |
| [test_runner_pre_qa.py](hve/tests/test_runner_pre_qa.py) | Pre-QA フェーズ | FR-CLI-02（--auto-qa） |
| [test_runner_qa_phase.py](hve/tests/test_runner_qa_phase.py) | QA フェーズ（AKM/ADI関連/通常） | AKM/ADI 系 |
| [test_startup_token_tools.py](hve/tests/test_startup_token_tools.py) | 起動時トークン計測 | NFR-OBS 周辺 |
| [test_streaming_token_chunk.py](hve/tests/test_streaming_token_chunk.py) | ストリーミング出力 | NFR-OBS-03 |
| [test_template_engine.py](hve/tests/test_template_engine.py) | Issue 本文テンプレ生成（29 クラス） | FR-CLOUD-10、FR-CLI-30 |
| [test_template_engine_agentic.py](hve/tests/test_template_engine_agentic.py) | Issue Form の Agentic Retrieval | FR-CLOUD-10〜11 |
| [test_issue_template_qa_parity.py](hve/tests/test_issue_template_qa_parity.py) | Issue Template ↔ Workflow QA 整合性 | FR-CLOUD-10 周辺 |
| [test_self_improve_completeness.py](hve/tests/test_self_improve_completeness.py) | Self-Improve 設定の Issue Template/Reusable 整合性 | FR-CLI-60 |
| [test_workflow_detect_qa_questionnaire_pr.py](hve/tests/test_workflow_detect_qa_questionnaire_pr.py) | QA 質問票 PR 検出 workflow | FR-STATE-02 周辺 |
| [test_workflow_restore_auto_qa_label.py](hve/tests/test_workflow_restore_auto_qa_label.py) | auto-qa ラベル復元 workflow | FR-STATE-02 周辺 |
| [test_workiq.py](hve/tests/test_workiq.py) | WorkIQ MCP / Copilot Session（30+ クラス） | AKM/ADI 関連の WorkIQ 連携 |
| [test_qa_merger.py](hve/tests/test_qa_merger.py) | qa-merge サブコマンド（30+ クラス） | §5.1 サブコマンド |

### Bash / PowerShell スクリプト系

- [.github/scripts/tests/test-bash.sh](.github/scripts/tests/test-bash.sh) — `validate-plan.sh` ほか CLI スクリプト dry-run（36 passed / 0 failed、FR-CLOUD 全般の支援）
- [.github/scripts/tests/test-assign-copilot.sh](.github/scripts/tests/test-assign-copilot.sh) — Copilot アサインヘルパー（25 passed / 0 failed）
- [.github/scripts/tests/test-prereq-file-check.sh](.github/scripts/tests/test-prereq-file-check.sh) — 前提ファイルチェック（FR-DAG-06 補助）
- [.github/scripts/tests/test-workflow-prereq-checks.sh](.github/scripts/tests/test-workflow-prereq-checks.sh) — Workflow 前提チェック
- [.github/scripts/tests/test-powershell.ps1](.github/scripts/tests/test-powershell.ps1) — PowerShell スクリプト dry-run（Pester 6.1.0で9 passed / 0 failed）
- [.github/scripts/powershell/tests/](.github/scripts/powershell/tests/) — PowerShell registry / command / GitHub API / Issue parser / Copilot assign（Pester 6.1.0で82 passed / 0 failed）
- [.github/workflows/test-cli-scripts.yml](.github/workflows/test-cli-scripts.yml) — Windows / Ubuntuの双方でPester 5+とPSScriptAnalyzer 1.20+を導入し、PowerShell registry群とdry-runを実行。PowerShell 7+専用のためBOM規則だけを除外し、その他のWarning / Errorはテストファイルを含めて検査する（ローカルPSScriptAnalyzer 1.25.0: 0件）
- [.github/scripts/tests/test-validate-agents.py](.github/scripts/tests/test-validate-agents.py) — Agent 定義検証
- [.github/scripts/tests/test_validate_skill_routing.py](.github/scripts/tests/test_validate_skill_routing.py) — Skill ルーティング検証

---

## §I 未カバー要件（要追加テスト候補）

導入中:

- **FR-MAINT-01〜03 / NFR-CTX-01**: [hve/tests/test_hve_requirement_traceability_contract.py](hve/tests/test_hve_requirement_traceability_contract.py)（T03 GREEN、12 passed）
- **FR-MAINT-03 / 04**: initial bootstrap PRのマージ後に、trusted workflow checkを含む`.github/branch-protection-main.json`をリモートmainへ再適用

優先度高（運用影響大）:

1. **FR-COMMON-01**: `auto-orchestrator-dispatcher.yml` の `trigger_map` キーと `list_workflows()` の完全一致テスト
2. **FR-CLOUD-03**: dispatcher の `opened` 限定 `author_association` ガード
3. **FR-CLOUD-04**: `closed` イベントでのタイトルプレフィックス判定
4. **FR-CLOUD-05**: `setup-labels` 特例ルーティングと旧独立原本質問票ラベル経路の削除
5. **FR-CLOUD-21**: AKM の `concurrency: akm-knowledge-write-...` キー存在検証
6. **FR-CLOUD-22**: 各 reusable workflow の `check_qa_skip` 同等チェック有無
7. **FR-CLOUD-23 / NFR-TIME-02**: ジョブタイムアウト値（AKM 360 分 / detect・suggest-next 15 分）
8. **FR-CLOUD-30**: `suggest-next` ジョブの次候補コメント投稿
9. **FR-STATE-03**: 完了時の次推奨 Workflow 提示（チェーン定義含む）
10. **§4.2 mode**: 4 値分岐（initialize/state_transition/closed/skip）の単体テスト

優先度中:

11. **NFR-PERF-02**: src 50 / test 30 のハードコード境界

優先度低（仕様未確定 TBD と紐づく）:

12. **NFR-SEC-02**: `docs-original/` 書き込み拒否の契約テスト
13. **NFR-SEC-03**: `_git_add_commit_push` の pathspec リスト渡し
14. **NFR-PERF-03**: 性能 KPI / SLA 数値目標（要件側 TBD-09）
15. **§13 各 Workflow Step 別 output_paths**: TBD-11〜14 解消後にゲート判定テストを追加

---

## §J 参照

- 要求定義書: [hve-dev/requirement-definition.md](hve-dev/requirement-definition.md)（現行版）
- テストディレクトリ:
  - [hve/tests/](hve/tests/) — Python 単体/統合テスト（73 ファイル）
  - [.github/scripts/tests/](.github/scripts/tests/) — Bash/PowerShell/検証スクリプトテスト
- CI 実行定義:
  - [.github/workflows/test-hve-python.yml](.github/workflows/test-hve-python.yml)
  - [.github/workflows/test-cli-scripts.yml](.github/workflows/test-cli-scripts.yml)
