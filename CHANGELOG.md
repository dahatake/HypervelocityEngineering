# CHANGELOG

## [Unreleased]

### Fixed — AAS Step ID を `2` 起点の歯抜け構成から `1` 起点の連番構成へリナンバリングし、users-guide / テストの追随漏れを解消した（FR-WF-AAS-03）

先行の AAS Step 1（`Arch-ApplicationAnalytics`）廃止・ARD Step 4.1 への移管により、AAS は Step `2, 3.1, 3.2, 4.1, 4.2, 5, 6, 7, 8, 9`（root が `2`）という歯抜けの Step ID 体系のまま残っていた。実装本体（`hve/workflow_registry.py`・bash/PowerShell registry・Step template・io-contract・Cloud reusable workflow・Issue Template・`hve-dev/requirement-definition.md` の FR-WF-AAS-03）は新 ID（`1, 2.1, 2.2, 3.1, 3.2, 4, 5, 6, 7, 8`）へ既に更新済みだったが、`users-guide/` の複数ファイルが旧 ID のまま残存し、加えてこのリナンバリングによって 8 件の Python テストと 2 件の PowerShell Pester テストが実際に RED 化していた（実装は正しく更新済みで、テスト側だけが旧 ID を期待していたため）。

- **`users-guide/02-app-architecture-design.md` を全面的に新 ID へ更新した**（最大範囲）。Step 概要表・依存グラフ（ASCII art）・全 10 個の Step 見出しと本文・Cloud/CLI/GUI 実行ガイド・失敗時の確認表・完了チェックリスト・動作確認手順・実装根拠を新 ID へ置換した。あわせて、同一ファイル内に残っていた 2 件の副次的な誤り（`Arch-ApplicationAnalytics` を依然 AAS 自身の Agent として記載していた歴史的注記の文言修正、および `--steps 5,6,7` の古い部分再実行例）も修正した。
- **`users-guide/00-design-doc-ingestion.md` / `01-business-requirement.md` / `hve-cli-orchestrator-guide.md` / `hve-gui-orchestrator-guide.md` / `workflow-reference.md` の旧 AAS Step 参照を修正した**。`00-design-doc-ingestion.md` の ADI 反映先対応表は `app-catalog.md` を ARD Step 4.1（AAS ではない）、`domain-analytics.md` を AAS Step 2.1、`data-model.md` を AAS Step 3.1 に訂正した。`01-business-requirement.md` は「AAS Step 2 の任意入力」を「AAS Step 1」へ、および `Arch-ApplicationAnalytics` を AAS 自身の Agent として記載していた KPI/OKR 参照節の誤りを ARD Step 4.1 へ訂正した。`hve-cli-orchestrator-guide.md` は `--dry-run` サンプル出力の Step 構成・タイトルを実際の新 ID（Step.1 = ソフトウェアアーキテクチャの推薦）に合わせて訂正した。あわせて、`hve-cli-orchestrator-guide.md` / `hve-gui-orchestrator-guide.md` に残っていた「AAS Step が APP-ID へ fan-out する」という実装と矛盾する記述（AAS のどの Step にも `fanout_parser` は設定されていない）を、Step 番号の置換と同時に是正した。`workflow-reference.md` は Fan-out 適用表から実在しない AAS の fan-out 行を削除し、GUI precheck 表の AAS Step 1 必須ファイル記載を実装（`app_requirements` file kind）に合わせて訂正し、`aas` の FULL_PIPELINE 必須成果物（それまで「なし」と誤記載）を ARD 依存の 3 成果物へ訂正し、Prompt 一覧表の AAS Step ID 列を新 ID へ更新した。
- **AAS 専用の SVG 3 枚（`chain-aas.svg` / `infographic-aas.svg` / `orchestration-task-data-flow-aas.svg`）を座標込みで再構築した**。廃止済みの旧 Step 1（`Arch-ApplicationAnalytics`）ボックスを削除し、後続の全ボックス・接続線・ラベルを新 ID へ再配置した。3 枚とも XML として整形式であることを確認した。
- **Step ID リナンバリングにより RED 化していた 8 件の Python テストを修正した**（`test_consumed_artifacts.py`・`test_dag_planner.py`・`test_data_model_split_contract.py`）。`test_data_model_split_contract.py` は AAS（新 `3.1`）と ADA（`4.1` のまま、対象外）で Step ID が分岐したため、ワークフロー別の Step ID をパラメータ化する形に修正した。
- **同じ理由で RED 化していた 2 件の PowerShell Pester テストを修正した**（`workflow-registry.Tests.ps1`・`commands.Tests.ps1`）。AAS のペルソナ系 Step 契約・`Get-NextStep` の DAG 前進・dry-run 出力サンプルを新 ID へ更新した。
- **`hve-dev/` の各種インベントリを再生成した**（`hve-feature-inventory.csv` / `hve-test-inventory.csv` / `hve-tdd-crosswalk-baseline.md`）。上記テストのリネーム・修正を反映した。

**影響範囲**: `users-guide/00-design-doc-ingestion.md`・`01-business-requirement.md`・`02-app-architecture-design.md`・`hve-cli-orchestrator-guide.md`・`hve-gui-orchestrator-guide.md`・`workflow-reference.md`・`users-guide/images/{chain-aas,infographic-aas,orchestration-task-data-flow-aas}.svg`、`hve/tests/{test_consumed_artifacts,test_dag_planner,test_data_model_split_contract}.py`、`hve/gui/tests/test_workflow_step_requirements.py`（コメントのみ）、`.github/scripts/powershell/tests/{workflow-registry,commands}.Tests.ps1`、`hve-dev/{hve-feature-inventory.csv,hve-test-inventory.csv,hve-tdd-crosswalk-baseline.md}`。`hve/workflow_registry.py` 等の実装コード・`.github/prompts/`・`.github/io-contracts/`・`hve-dev/requirement-definition.md` は本セッションでは変更していない（先行コミットで既に新 ID へ更新済みのため）。

**既知の制約**: ADA ワークフロー（`Step 2` から始まる同種の歯抜け構成）のリナンバリングは対象外（要求定義書 FR-WF-ARD-04 の記載どおり、AAS のみを対象とする措置）。

**検証**: `hve/tests` 全体を実行し、修正前は AAS Step ID リナンバリングに起因する **8 failed**（`test_aas_step4_uses_service_catalog` 等）を確認し、修正後は **8389 passed, 17 skipped, 1 xfailed, 697 subtests passed**（実行時間 13分39秒、新規失敗なし）を確認した。PowerShell: `Invoke-Pester` で `.github/scripts/powershell/tests` 全体 **83 passed, 0 failed**（修正前は AAS 関連 2 件が failed）、`Invoke-ScriptAnalyzer`（`PSUseBOMForUnicodeEncodedFile` 除外）で新規警告 0 件（既存 3 件の `PSUseDeclaredVarsMoreThanAssignment` は本セッション以前から存在し無関係であることを HEAD 版との比較で確認済み）を確認した。3 枚の SVG は `xml.etree.ElementTree` で整形式であることを確認した。

<!-- validation-confirmed -->

### Fixed — ARD Step 4.1/4.2 追加と AAS Step 1 廃止に伴う README.md / users-guide のドキュメント未反映・矛盾を解消した（FR-WF-ARD-04 / FR-WF-AAS-02）

先行の ARD Step 4.1/4.2 追加（APP別要求定義書の自動生成）と AAS Step 1 廃止（ARD への移管）は実装・要求定義書側では完了していたが、`users-guide/` の複数ファイルが旧い Step 数・Step 構成のまま残り、特に `02-app-architecture-design.md` は「Step 1 は ARD へ移設済み」という冒頭注記と矛盾する形で、廃止されたはずの AAS Step 1 の完全な手動実行手順と Cloud/GUI 実行ガイドの記述（Sub-Issue 作成・precheck・動作確認手順）がそのまま残存していた。

- **`users-guide/01-business-requirement.md` の ARD セクションを 5 グループ構成に更新した**。旧「4 グループ・8 実Step」の記述を「5 グループ・10 実Step」に修正し、グループ 5（実 Step `4.1`/`4.2`、既定 ON）の対応表行・既定 ON 設定・次のステップ案内を追加した。あわせて、AAS の旧 Step 1（`Arch-ApplicationAnalytics` によるアプリケーションリスト作成）の手動実行手順を、ARD の対応する新設節「ARD Step 4.1 / 4.2 アプリケーション要求定義」へ移設し、目次にも追加した。
- **`users-guide/02-app-architecture-design.md` の AAS Step 1 関連の陳腐化記述を解消した**。重複していた旧 Step 1 の手動実行手順を削除して 01-business-requirement.md への参照ポインタに置き換え、Step 2 の説明・ADI 由来候補の採番元・`chain-aas.svg` の alt テキストにあった「Step 1」参照を修正した。加えて、Cloud/GUI 実行ガイドと動作確認手順（番号付きチェックリスト）が、AAS の root Step が Step 2 に変わった後も旧 Step 1 の Sub-Issue 作成・precheck・完了確認を前提とした記述のまま残っていたことを発見し、Step 2 基準の記述へ全面的に修正した。
- **`users-guide/workflow-reference.md` と `hve-cli-orchestrator-guide.md` の Step 数表記を実装と同期した**。`ard` の Step 数を 8→10 へ、`aas` の Step 数を 11→10 へ修正し（計 5 箇所）、`ard` 行の Prompt 一覧に Step `4.1`/`4.2` を追加した。
- **README.md に直接埋め込まれる `orchestration-dataflow-overview.svg` を実データフローに同期した**。ARD の出力ボックスへ `app-catalog.md` / `architectural-requirements-app-NNN.md` を追加し、AAS の出力ボックスから重複表記の `app-catalog.md` を除いて「ARD 生成・入力として消費」に修正した（既存レイアウトを保つため、当該テキストのみフォントサイズを縮小して2行化し、座標再計算を伴う周辺要素の移動は行っていない）。

**影響範囲**: `users-guide/01-business-requirement.md`、`users-guide/02-app-architecture-design.md`、`users-guide/workflow-reference.md`、`users-guide/hve-cli-orchestrator-guide.md`、`users-guide/images/orchestration-dataflow-overview.svg`。`hve/workflow_registry.py` 等の実装コード、`.github/prompts/`、`hve-dev/requirement-definition.md` は変更していない（いずれも既に正確なため）。

**既知の制約**: AAS 専用の3図（`chain-aas.svg` / `infographic-aas.svg` / `orchestration-task-data-flow-aas.svg`）と ARD 詳細図（`orchestration-task-data-flow-ard.svg`）は、ノード追加・削除に伴う座標再計算が必要な高工数・高リスクな変更であり、本セッションでは対象外とした（テキスト側に正しい情報が既に併記されているため実害は限定的と判断）。詳細は `work/20260825_ARD-AAS-Docs-Update-Plan.md` を参照。

**検証**: 実装前後で `hve/workflow_registry.py`（ARD 10 Step / AAS 10 Step、グループ5=実Step `4.1`/`4.2`、`ARD_DEFAULT_GROUP_IDS` に `"5"` を含む既定ON）との整合を直接照合。編集後、`grep` による横断チェックで旧い Step 数・グループ数表記（`11 実行ステップ`、`8 実行ステップ`、`4 グループ構成` 等）が対象 `.md` ファイルから 0 件になったことを確認。敵対的レビューで `02-app-architecture-design.md` の動作確認手順の項番ずれ（1項目統合により末尾の「15.」が孤立）を検出し「14.」へ修正した。

<!-- validation-confirmed -->

### Fixed — ADA Step 1 の ARD Step 4.1 移管漏れと ada/aar の APP要求前提ゲート抜け穴を解消し、APP別要求定義書14件の初期投入で下流ワークフローの起動不能状態を解消した（FR-WF-ARD-04 / FR-WF-AAS-02 / FR-APPREQ-01〜05）

先行コミット（`0da8f77f`）は AAS Step 1 → ARD Step 4.1/4.2 の移設パイロットを実施したが、同型の重複を持つ ADA Step 1、`ada`/`aar` の APP要求前提ゲート未配線、`docs/architectural-requirements-app-*.md` の実データ0件という3つの後続ギャップが未着手のまま残っていた。加えて無関係な別コミット（`acadd516`）が副作用として APP-009 の Azure Static Web Apps デプロイ workflow を誤って削除していた。

- **ADA Step 1（`Arch-ApplicationAnalytics` による `app-catalog.md` 生成）を AAS Step 1 と同一理由で ARD Step 4.1 へ移管し廃止した**。`hve/workflow_registry.py` から ADA Step 1 を削除して Step 2 を root 化し、9件の io-contract の `producer` を `Arch-ApplicationAnalytics--ard--4.1` へ更新、旧 `Arch-ApplicationAnalytics--ada--1.yaml` と `templates/ada/step-1.md` を削除、Bash registry・Cloud reusable workflow（`auto-agent-data-architecture-reusable.yml`）を同期した。`hve-dev/requirement-definition.md` の FR-WF-ARD-04 を「ADA Step 1 は初版では維持する」から移管・廃止へ改訂した上で実装した。
- **`ada` / `aar` の2 Workflowに欠けていた APP要求前提ゲートを追加した**。`FULL_PIPELINE.dependencies` へ両 Workflow の `ard`（`soft=False`）依存と `docs/catalog/app-catalog.md` / `docs/catalog/use-case-catalog.md` / `docs/architectural-requirements-app-*.md` の `required_artifacts` を追加し、前提成果物が無くても起動時に停止しない抜け穴を解消した。
- **`docs/architectural-requirements-app-001.md` 〜 `-014.md` の14件を新規生成した**。`docs/catalog/app-catalog.md` §4 を根拠に、Primary UC 別の FR 行・キーNFR列別の NFR 行・留意点/TBD列を集約した Constraint 行（Status=TBD, Blocker=no）で構成し、全件が ARD Step 4.2 の schema・coverage 検証を通過することを確認した。これにより AAS/ADA/AAR 等、下流9 Workflow が前提成果物欠落で起動不能だった状態を解消した。
- **APP-009 の Azure Static Web Apps デプロイ workflow（`azure-static-web-apps-app009.yml`）を復元した**。無関係な別コミットが副作用で誤削除していたことを `git log --diff-filter=D` とコミットメッセージ精査で特定し、直前コミット時点の内容をそのまま復元した。
- T-D（`sample-data.json` の部分集合判定）・T-F（entrypoint import フック）・T-G（`launch-gui.sh` の CRLF）は、いずれも実装確認・対応テスト実行の結果、既に解消済みであることを確認し、変更を加えていない。
- Cloud 実 dispatch を伴う E2E 確認（実行プランの追加タスク）は、ライブ GitHub Issue 作成・実 Copilot Cloud Agent 起動という不可逆・共有インフラ操作にあたるため、本セッションでは実施せず明示的にスコープ外とした。

**影響範囲**: `hve/workflow_registry.py`、9件の io-contract の producer 更新（`Arch-ApplicationAnalytics--ada--1.yaml` は削除）、`.github/scripts/bash/lib/workflow-registry.sh`、`.github/workflows/auto-agent-data-architecture-reusable.yml`、`docs/architectural-requirements-app-001.md`〜`-014.md`（新規14件）、`.github/workflows/azure-static-web-apps-app009.yml`（復元）、`hve-dev/requirement-definition.md`、`users-guide/09-agent-data-architecture.md`・`hve-cli-orchestrator-guide.md`・`workflow-reference.md`、`hve-dev/requirement-test-mapping.md`。PowerShell registry（`workflow-registry.ps1`）には ADA 定義が存在せず対象外（既存ギャップ、本変更のスコープ外）。

**既知の制約**: Cloud 実 dispatch E2E 確認は上記の理由により未実施。`docs/architectural-requirements-app-NNN.md` の TBD 行（留意点由来の Constraint）は Blocker=no のまま残存し、値の確定は今後の作業とする。

**検証**: ADA Step 1 移管 **266 passed, 1 skipped**（io-contract validator: Schema errors 0 / Integrity errors 0 / Registry mismatch errors 0）。`ada`/`aar` ゲート追加 `TestMetaWorkflow` **6 passed**。APP要求定義書14件 `test_application_requirement*.py` 5ファイル合計 **51 passed**（`validate_requirement_document` 14/14 エラー0、`validate_requirement_coverage` で app_ids 14件一致・orphan 0、TBD かつ Blocker=yes の行0件）。SWA workflow 復元 **11 passed**。`hve-dev/generate_tdd_inventory.py` でインベントリを再生成後、`hve/tests` 全体を実行し **8387 passed, 1 failed（本変更と無関係な既存の環境依存: `copilot-sdk.lock` の CRLF。セッション開始前から未変更であることを `git status` で確認済み）, 17 skipped, 1 xfailed**（実行時間 19分13秒）を確認した。修正前の既知2失敗（SWA workflow 未生成・`copilot-sdk.lock` の CRLF）のうち、SWA workflow 側は本変更の T-E で解消した。

<!-- validation-confirmed -->

### Fixed — ARD の Windows PowerShell CLI 経路が未実装のまま残っていた最後のギャップを解消した（FR-WF-ARD-01）

前回変更で ARD の Cloud Agent Orchestrator 面・bash registry・`hve/runner.py` 側は同期を完了させたが、Windows PowerShell CLI（`orchestrate.ps1` 等が読む `.github/scripts/powershell/lib/workflow-registry.ps1`）だけ `ard` ブロックが未実装のまま残っていた。既存の Pester テスト（`workflow-registry.Tests.ps1` の `retrieves ARD workflow`）はこのギャップを先行宣言していたが red のままだった。

- **PowerShell registry へ ARD の全 10 Step を追加した**。Python 正本（`hve/workflow_registry.py`）と 1 対 1 で一致する `id`/`title`/`custom_agent`/`depends_on`/`skip_fallback_deps`/`body_template_path` を持つ `NewWorkflowStep` 呼び出し列を追加し、`hve/tests/test_powershell_workflow_registry_parity.py` のパラメータ化対象へ `ard` を追加した。
- **AAS Step 1 廃止に追随できていなかった PowerShell 側 Pester テストを修正した**。`commands.Tests.ps1` の dry-run 実行計画テストが、既に削除済みの旧 Step 1（`アプリケーションリストの作成`）の表示と旧ステップ数「11 個」をなお期待していたため、Step 1 表示アサーションを削除し件数を「10 個」へ更新した。
- **README.md のワークフロー一覧を実装と同期した**。`ard` 行の説明を「ADR-0003 で 7 ステップ + 任意 Step 2.5」から「5 表示グループ・10 実 Step、Step 2.1 が任意の KPI/OKR 定義」へ更新し、`docs/catalog/app-catalog.md` / `docs/architectural-requirements-app-NNN.md` を成果物へ追加した。`aas` 行から、ARD Step 4.1 生成に移管済みの `app-catalog.md` の自己生成扱いの記述を外した。
- **`hve-dev/requirement-test-mapping.md` の FR-WF-ARD-01 に本件の GREEN 実績を追記した**（bugfix 区分。新規要件 ID は起こしていない）。

**影響範囲**: `.github/scripts/powershell/lib/workflow-registry.ps1`、`.github/scripts/powershell/tests/commands.Tests.ps1`、`hve/tests/test_powershell_workflow_registry_parity.py`、`README.md`、`hve-dev/requirement-test-mapping.md`。bash registry・Python registry・Cloud workflow・`hve/runner.py` は変更していない。

**既知の制約**: 他の対象 Custom Agent（ADA / AAD-WEB 等）への APP 要求 preflight gate 展開は、対応する Prompt 更新と一体で行うべき将来作業として引き続き未着手（現時点でこれを要求する失敗テストは無い）。`.github/scripts/README.md` の「サポートするワークフロー」ステップ数表は `ard`/`ada`/`aar` が未掲載で他ワークフローの件数も本セッション以前から不整合だが、根拠となる失敗テストが無く、対象外とした。

**検証**: PowerShell: `test_powershell_registry_matches_python_ssot[ard]` を含む **4 passed**、Pester（`workflow-registry.Tests.ps1` + `commands.Tests.ps1` を含む全5ファイル）**83 passed, 0 failed**（修正前は **81 passed, 2 failed**）、PSScriptAnalyzer **0 件**。Python: `hve/tests` 全体 **8387 passed, 2 failed（本変更と無関係な既知の環境依存: SWA workflow 未生成・`copilot-sdk.lock` の CRLF）, 17 skipped, 1 xfailed**（修正前比 +1 passed、新規失敗なし）。

<!-- validation-confirmed -->

### Fixed — AAS Step 1 の ARD Step 4.1/4.2 移設パイロットで未同期のまま残っていた領域を解消し、生成アプリケーション要求トレーサビリティを配線した（FR-WF-ARD-04 / FR-APPREQ-01〜05）

先行コミットは AAS Step 1（アプリケーションリスト作成）を ARD Step 4.1/4.2 へ移設したが、Python registry とその直近テストだけを更新し、Cloud 側（bash / PowerShell registry、GitHub Actions、io-contracts）・formal requirement-definition・Prompt・Skill・ローカル実行エンジン（`hve/runner.py`）は未同期のままだった。本変更はこの移設を全面で完了させ、新規の `application-requirement-traceability` Skill を関連 9 Workflow へ配線する。

- **AAS Step 1 廃止を全面同期した**。bash / PowerShell registry、Cloud workflow（`auto-app-selection-reusable.yml`）、`orchestrator.py` の成果物キー解決から旧 Step 1 を除去し、`docs/catalog/app-catalog.md` の生成元を ARD Step 4.1 として一貫させた。
- **ARD の Cloud Agent Orchestrator 面を実装した**。bash registry へ ARD の全 10 Step を追加し、`labels.json` へ `ard:*` ラベル一式、dispatcher へ ARD ルーティングと `check_app_requirements` 前提成果物チェックジョブ、`state-transition-on-pr-merge.yml` へ ARD Step 4.2 専用の APP 要求完了ゲート（trusted/subject 分離チェックアウト）を追加した。
- **G-DIFF を `auto-approve-and-merge.yml` の auto-approve 前提条件へ統合した**。PR メタデータ収集・G-DIFF 判定ステップを追加し、check-run 集計を許可リスト方式・自 run 除外・再試行付きへ書き換え、G-DIFF 未達時は auto-approve をブロックする。
- **io-contracts の移行を完了させた**。ARD Step 4.1/4.2 用の新規 producer 契約は既に存在していたため、自己参照が残るだけだった旧 `Arch-ApplicationAnalytics--aas--1.yaml` を削除し、63 件の producer 参照を新契約へ一本化した。
- **`hve-dev/requirement-definition.md` の ARD 節と registry の parity を回復した**。ドキュメント本体は既に 5 表示グループ・10 実 Step へ更新済みだったため、対応する契約テスト側の期待値（8 Step / 4 グループ）を実体に合わせて更新した。
- **FR-APPREQ-03/04 を `hve/runner.py` の `StepRunner.run_step` へ配線した**。SDK 起動前に対象 APP の要求定義書を検証する preflight（`build_application_requirement_context`）と、SDK 完了後に ARD Step 4.2 の catalog 全体 coverage（`validate_requirement_coverage`）・完了報告の trace block（`validate_application_requirement_trace_block`）を検証する completion gate を追加した。既存呼び出し元（47 箇所超）を壊さないよう、新規 class 属性 `_APP_REQUIREMENT_PREFLIGHT_AGENTS` の allowlist（現状は `Arch-ArchitectureCandidateAnalyzer` のみ）でスコープし、対象外の Custom Agent / Workflow は no-op のままとした。
- **`Arch-ArchitectureCandidateAnalyzer.prompt.md` を fail-closed 設計へ書き換えた**。APP 別要求定義書欠損時の「デフォルト推薦」フォールバックを廃止し、`docs/architectural-requirements-app-NNN.md` を必須入力として明記した（Runner の preflight が既に SDK 起動前に停止するため、Prompt 側の欠損時ロジックは不要になった）。
- **`agent-common-preamble` Skill へ `application-requirement-traceability` へのルーティング節を追加した**。対象 9 Workflow（AAS/ADA/AAD-WEB/ASDW-WEB/ADFD/ADFDV/AAG/AAGD/AAR）が要求定義書全文を既定入力にせず、`app-scope-resolution` / `markdown-query` を再利用する方針を明記した。
- **ASDW サンプルデータの検証を coverage/subset 方式へ緩和した**。`src/data/sample-data.json` が APP-009 単体から全 APP 横断の ALL-APPS fixture（44 entities）へ意図的に拡張されたことに合わせ、`_validate_required_sample_records` を厳密な集合一致からカバレッジ検査へ変更した。
- **`users-guide/02-app-architecture-design.md` を要点レベルで同期した**（Step 表・依存グラフ・NOTE・fan-out 節）。詳細な手動実行プロセス散文と関連 SVG 図は本変更の対象外とした（下記既知の制約参照）。

**影響範囲**: `hve/runner.py`（`StepRunner.run_step` の preflight/completion gate 追加のみ、既存フローは変更なし）、`hve/orchestrator.py`、`hve/workflow_registry.py` 関連テスト、bash / PowerShell registry、5 件の GitHub Actions workflow、`labels.json`、io-contracts 1 件削除、`.github/prompts/Arch-ArchitectureCandidateAnalyzer.prompt.md`、`.github/skills/agent-common-preamble/SKILL.md`、`hve-dev/requirement-definition.md` 検証テスト、`users-guide/02-app-architecture-design.md`。Workflow の DAG 構造・既存 Step の入出力契約・CLI 引数は変更していない。

**既知の制約**: `users-guide` の詳細な手動/Cloud 実行ガイド散文（Step.1 言及を含む節）と関連 SVG 図（`chain-aas.svg` 等）は未更新。PowerShell registry への ARD 追加は見送った（既存パリティテストが `aas`/`adfd`/`adfdv` のみを対象とし、無検証のまま追加すると却って検証されないコードになるため）。GitHub-hosted runner 上での実 workflow dispatch・ブランチ保護の適用は本セッションでは実施していない。`hve/runner.py` の APP 要求 preflight/completion gate は `Arch-ArchitectureCandidateAnalyzer` のみを allowlist 登録した段階的展開であり、他の対象 Custom Agent への展開は今後の作業とする。

**検証**: `hve/tests` 全体を実行し、本変更前の RED 17 failed から **8386 passed, 2 failed（いずれも本変更と無関係な既知の環境依存: SWA workflow 未生成・`copilot-sdk.lock` の CRLF）, 17 skipped, 1 xfailed** へ復旧した。加えて `bash -n` / YAML `safe_load` による全 Cloud workflow 構文検証、`hve-dev/generate_tdd_inventory.py` によるインベントリ再生成、5 回の独立した敵対的レビュー（各回 Critical=0 / Major=0）を実施した。

<!-- validation-confirmed -->

### Fixed — Pester 6でPowerShell CLI契約を再検証し、ADFD / ADFDV registryドリフトを解消した（FR-WF-ADFD-02 / FR-WF-CONF-01）

- CurrentUserスコープのPesterを3.4.0から6.1.0へ更新し、PSScriptAnalyzer 1.25.0とともにCI同等条件で検証した。
- PowerShell registryのADFDを旧3 Stepから現行7 Stepへ同期し、単一root `0.1`、上流4 producer、Step `1` / `2`の並列、Step `3`のAND joinを復旧した。ADFDVにはStep `4.3`（要件適合実測）と現行paramsを追加し、7 Stepから8 Stepへ同期した。
- PesterテストをAAS 11 / ADFD 7 / ADFDV 8の正確な件数・DAG・paramsへ更新し、Python正本との全Step metadataパリティテストを追加した。Ubuntu jobでもPowerShell registryテスト群を実行するようにした。
- PowerShell 7+専用契約に基づき、PSScriptAnalyzerでは`PSUseBOMForUnicodeEncodedFile`だけを除外した。Pesterの`BeforeAll`変数に対する既知の誤検知だけをテストファイルで限定除外し、その他のWarning / Errorは全ファイルで検査する。
- 共通plan fixtureへ必須`estimate_total`を追加した。Windows Git Bashではnative PythonのstdinをUTF-8へ固定し、比較境界のCRLFだけを正規化してBash helperテストを移植可能にした。

**影響範囲**: `.github/scripts/powershell`のADFD / ADFDV dry-run DAG、Bash / PowerShellテスト、`Test CLI Scripts` workflow。Python registry、Workflow本体、CLI引数、成果物パスは変更していない。

**既知の制約**: GitHub-hosted runner上のworkflow dispatchは行っていない。代わりにWindows 11のPowerShell 7.6.5と、WSL Ubuntu 24.04へ一時展開した公式PowerShell 7.6.5ポータブル版の双方で、CIと同じAnalyzer・Pester設定を実測した。

**検証**: 正本同期前RED **9 failed / 71 passed**。修正後はWindows / WSL Ubuntuの双方でPester registry群 **82 passed / 0 failed**、PowerShell dry-run **9 passed / 0 failed**、PSScriptAnalyzer **0件**（Pester 6.1.0 / PSScriptAnalyzer 1.25.0）。加えてBash dry-run **36 passed / 0 failed**、assign-copilot helper **25 passed / 0 failed**、Python/Bash/PowerShellパリティ・関連回帰 **249 passed / 1 xfailed / 9 subtests passed**。

<!-- validation-confirmed -->

### Changed — ARD / Data Model / Cloud完了ゲートを現行契約へ同期した（FR-WF-ARD-03 / FR-WF-DM-01 / G-LBL）

- **ARD の選択契約を単一正本化した**。4 表示グループ / 8 実 Step と既定 `ARD_DEFAULT_GROUP_IDS = ("2", "3", "4")` をCLI直接実行・wizard・GUI・Orchestratorへ伝搬し、KPI/OKRの二重状態を廃止した。`target_recommendation_id` はGUIの表示・保存・argvを含めて欠落なく伝搬し、グループ`1`+`2`のbridge経路だけで採用する。quick-autoは先頭候補、manualはStep `1.2`後の選択メニューを維持する。
- **Cloud G-LBLをfail-closed化した**。PR merge後の実Cloud workflowで非終端ラベルを`done`付与前に整理・再検証し、API/JSON失敗、残置、付与失敗、競合時は`done`を可能な限りrollbackしてIssue closeを拒否する。close直前・直後にもG-LBLを再検証し、AAR / ADAを含む全Cloud系列を対象にした。
- **Data Model分割契約と利用者資料を同期した**。親`data-model.md`を常時requiredの統合版とし、50,000 Unicode文字超の場合だけcanonical sidecar 3件をoptional upsertする。分割不要の再実行ではstale sidecarを削除する。AAS / ADAのPrompt・template・registry・io-contract・利用者ガイドを同じ契約へ揃えた。
- **利用者資料8件を実装へ揃えた**。ARDのモード別SR選択、CLI必須条件、GUI C14、KPI/OKR既定、8実StepのSVG、ADR-0003追補を更新した。SVGは偽の直列依存を除き、条件付きbridgeと並列兄弟を区別した。
- **Windows Git BashのBash契約テストを移植可能にした**。日本語JSON fixtureをUnicode escapeへ固定し、native PythonのCRLFだけを比較前に正規化した。製品helperの挙動は変更していない。

**影響範囲**: ARDの既定グループ・KPI/OKR選択・SR-ID伝搬、Cloud PR merge後のラベル終端処理、AAS / ADA Data Modelの条件付き成果物宣言、関連するCLI / GUI / 利用者資料。新規設定・新規依存・汎用G-DIFFエンジンは追加していない。

**既知の制約**: G-DIFFの汎用自動強制は引き続き`△`。ローカルはPester 3.4.0のみで、Pester 5+は既存`Test CLI Scripts` CIで確認する。HVE/GUI全回帰で残る7件は隔離した変更前HEADでも同じ顔ぶれを再現しており、本変更による新規回帰ではない。

**検証**: focused契約 **200 passed**、inventory再生成一致 **163 passed**、Bash **36 passed**、I/O contract **149件（Schema / Integrity / Registry mismatch すべて0）**、Cloud G-LBL run本文の`bash -n` / ShellCheck、ARD SVG XML、相対リンク、Python compileを確認した。B1〜B5の同一テストはRED **28 failed / 69 passed** からGREEN（個別 **3 / 49 / 21 / 14 / 25 passed**）へ移行した。

<!-- validation-confirmed -->

### Added — §13 の Workflow Step 表と registry の乖離を全 Workflow 横断で機械検査するようにした（FR-MAINT-09）

要求定義書 §13 の Step 表が実装から取り残される乖離は、§13.5（ADFDV）と §13.12（ARD）で個別に発生し、そのつど当該 Workflow だけの契約テストで塞いできた。横断検査が無かったため、同じ乖離が §13.2（AAD-WEB）と §13.3（ASDW-WEB）へ残存していた。本変更は横断検査を 1 つ追加し、検出された乖離を実装へ同期する。新しい設定・CLI 引数・環境変数・依存は追加していない。Workflow 定義・DAG・実行時の成果物パスは変更していない。

- **FR-MAINT-09 を新設した**。§13 の Step 表と [hve/workflow_registry.py](hve/workflow_registry.py) の StepDef 集合の一致を必須化し、Workflow ごとの検査モード（全 Step 一致 / 要約表としての部分集合）と、§13 に節を持たない Workflow の除外を明示リストで固定する。除外には理由の記載を必須とした（FR-WF-OUT-09 の allowlist と同じ方式）。依存・Fan-out・生成ファイルの一致は、列構成が節ごとに異なるため対象外と明記した。
- **横断契約テストを追加した**。[hve/tests/test_requirement_section13_parity.py](hve/tests/test_requirement_section13_parity.py) が registry 登録済みの全 13 Workflow を対象に、(a) 検査モード表と除外 allowlist の網羅、(b) Step ID 集合、(c) ID として解釈できないトークンの排除、(d) 表の Step タイトルが registry の同一 Step を指すこと、を検査する。新規 Workflow を追加したときに §13 の同期を忘れると失敗する。
- **重複実装を単一化した（FR-MAINT-07）**。[hve/tests/test_requirement_definition_adfdv_section.py](hve/tests/test_requirement_definition_adfdv_section.py) の Step 集合検査を削除し、当該ファイルは ADFDV 固有の検査（fan-out parser 名・旧パス不在・見出し名・Custom Agent 名）だけを保持する。
- **契約テストが読むファイルを CI トリガへ追加した**。[.github/workflows/test-hve-python.yml](.github/workflows/test-hve-python.yml) の `paths` へ `.github/prompts/**` と `.github/io-contracts/**` を追加した。従来はこの 2 系統だけを変更した PR で Python 契約テストが起動しなかった。
- **起動面ごとに重複していた既定値 7 件を単一化した（FR-MAINT-07、TBD-27 解消）**。CLI 入口（[hve/__main__.py](hve/__main__.py)）と Orchestrator（[hve/orchestrator.py](hve/orchestrator.py)）に同名で定義されていた `_AKM_DEFAULT_SOURCES` / `_AKM_DEFAULT_TARGET_FILES` / `_ADI_DEFAULT_TARGET_SCOPE` / `_ADI_DEFAULT_DEPTH` / `_ARD_DEFAULT_SURVEY_PERIOD_YEARS` / `_ARD_DEFAULT_TARGET_REGION` / `_ARD_DEFAULT_ANALYSIS_PURPOSE` を [hve/workflow_registry.py](hve/workflow_registry.py) の公開定数へ集約し、両モジュールを alias import へ変えた。参照側の 20 箱所は名前が変わらないため未変更で、振る舞いも変わらない。値が一致している間は既存テストで検出できないため、リテラルによる再宣言を AST で拒否する契約テスト（[hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) `TestLaunchSurfacesShareParameterDefaults`）を追加した。flat import 時の `getattr` fallback は registry から値を引くため許容する。

### Added — AAGD Step 6 / 7 の成果物契約を規範化した（FR-WF-AAGD-08 / 09、TBD-26 解消）

Step 6（検索経路の適正化実測）と Step 7（Microsoft 365 / Teams 公開）は、[hve/artifact_validation.py](hve/artifact_validation.py) の決定的検証、[hve/runner.py](hve/runner.py) の成果物ゲート、共有 Prompt の固定フォーマットによって**実装側では契約が確定していた**一方、要求定義書に対応する要件が無く、変更時の判断根拠を持てなかった。既存の実装契約をそのまま明文化したもので、新しい制約は追加していない。

- **FR-WF-AAGD-08**: `docs/agent/route-rightsizing-report.md` の測定条件ラベル 8 件、比較表 `| Rung | Route | Accuracy | Tokens | Latency | Judgement | Evidence |`（2 行以上）、判定語彙 4 値（`KEEP` / `DOWNGRADE` / `INSUFFICIENT` / `NOT_MEASURED`）、`- Recommended-Route:` を固定した。1 行だけの比較表を受理しないのは、安い経路で要件を満たせるかを比較しない限り採用経路が過剰かを判定できないためである。
- **FR-WF-AAGD-09**: `docs/agent/m365-publish-report.md` の公開条件ラベル 8 件、公開表 `| Agent Key | Channel | Publish Scope | App Version | Judgement | Approval | Evidence |`（1 行以上）、判定語彙 4 値（`PUBLISHED` / `PENDING_APPROVAL` / `NOT_SELECTED` / `FAILED`）、`- Consumer-Setup:`、および公開メタデータへの secret 混入禁止（NFR-SEC-01）を固定した。

### Changed — Data Model の分割契約を canonical sidecar 3 件へ固定した（FR-WF-DM-01）

- [.github/prompts/Arch-DataModeling.prompt.md](.github/prompts/Arch-DataModeling.prompt.md) §3.3.1 から APP-ID 単位分割の例示を削除し、単一ファイル版が 50,000 文字を超える見込みのときだけ canonical sidecar 3 件をすべて作成・更新すること、親を索引/統合版として相互リンクを張ること、分割不要へ戻った再実行では stale な sidecar を削除することを規定した。
- AAS / ADA の Step 4.1 テンプレート（[.github/scripts/templates/aas/step-4.1.md](.github/scripts/templates/aas/step-4.1.md) / [.github/scripts/templates/ada/step-4.1.md](.github/scripts/templates/ada/step-4.1.md)）と io-contract（[.github/io-contracts/Arch-DataModeling--aas--4.1.yaml](.github/io-contracts/Arch-DataModeling--aas--4.1.yaml) / [.github/io-contracts/Arch-DataModeling--ada--4.1.yaml](.github/io-contracts/Arch-DataModeling--ada--4.1.yaml)）へ同じ条件付き成果物を宣言した。sidecar は `required: false` / `mode: upsert`、親は `required: true` のまま維持する。

### Fixed — §13.2 / §13.3 / §13.7 の Step 表と `users-guide` の ARD 記述を実装へ同期した

- **§13.2（AAD-WEB）**: 非コンテナ Step `2.4`（画面別 TDD テスト仕様書）/ `2.5`（追加 Azure サービス選定）/ `2.6`（Agentic Retrieval 機能要件詳細）が表に無く、同じ節の注記だけが `2.4` に言及していた。3 件を追加し、あわせて Step 1 の Fan-out（`app_catalog`）と生成パス、Step 2.3 のタイトルと依存（`2.1, 2.2` → `2.2`）、Step 3 の依存（`2.4` を追加）を registry へ揃えた。
- **§13.3（ASDW-WEB）**: 表の Step ID 体系が実装と系統的に食い違っていた（表の `1.2` が実装の `1.3` を、表の `2.1` が実装の `3.1` を指す等）。実装に存在しない ID（`2.3T` / `2.3TC` / `3.0T` / `3.0TC`）と、リポジトリにも registry にも存在しない成果物パス 4 件を除去し、非コンテナ 21 Step を registry へ揃えた。コンテナ Step は FR-WF-OUT-04（生成ファイルを持たない Sub-Issue 束ね）に基づき §13.11 と同じ方針で表から省いた。
- **§13.7（AAGD）**: Step `5`（要件適合実測）/ `6`（検索経路の適正化実測）/ `7`（Microsoft 365 / Teams 公開）が表に無かったため追加し、Step 1 の生成パスを registry の実宣言（`docs/agent/agent-application-definition.md`）へ訂正した。
- **`users-guide`**: [users-guide/workflow-reference.md](users-guide/workflow-reference.md) の ARD 記述で、表示グループ ID が `1 / 2 / 2.1 / 3`（正しくは `1 / 2 / 3 / 4`）、KPI/OKR が「既定 OFF」（実際は既定で選択される）、ユースケース系が「グループ 3」（正しくはグループ 4）と書かれていた。同じ内容を正しく記載している [users-guide/01-business-requirement.md](users-guide/01-business-requirement.md) との食い違いを含めて訂正した。
- **ARD のデータフロー図と ADR-0003**: [users-guide/images/orchestration-task-data-flow-ard.svg](users-guide/images/orchestration-task-data-flow-ard.svg) は 7 ステップ構成のままで KPI/OKR Step が図に存在しなかった。Step 2.1 のブロックを追加して以降を再配置し（viewBox 920 → 1029、Step 見出し 8 件、要素の viewBox 外への溢れ 0 件）、凡例と関連 Prompt 一覧も揃えた。[template/decisions/ADR-0003-ard-fanout-architecture.md](template/decisions/ADR-0003-ard-fanout-architecture.md) には決定内容（7 step の fan-out 構成）を保持したまま、現行が 8 実 Step / 4 表示グループであることの追補を加えた（ステータス `Proposed` は変更していない）。
- **要求↔テスト対応表の重複**: FR-MAINT-08 の受入ケース 7 行が完全に 2 回記載されていたため、2 回目を削除した。
- **契約テストの型エラーと重複検査**: [hve/tests/test_requirement_definition_adfdv_section.py](hve/tests/test_requirement_definition_adfdv_section.py) の `get_workflow("adfdv")` を `None` 安全にし、[hve/tests/test_ard_requirement_parity.py](hve/tests/test_ard_requirement_parity.py) からは横断テストと重複する Step 集合一致の検査を外して ARD 固有の件数・重複検査だけを残した（FR-MAINT-07）。

**影響範囲**: 要求定義書 §3.7 / §12 / §13.2 / §13.3 / §13.7、要求↔テスト対応表、`Arch-DataModeling` の Prompt と AAS / ADA Step 4.1 の宣言面、`users-guide` の該当 3 ファイル、CI のトリガ条件。Workflow 定義・DAG・実行時の成果物パス・GUI の選択肢・CLI 引数は変更していない。

**利用者への影響**: 実行時の挙動は変わらない。`users-guide` の ARD 記述が実装と一致し、KPI/OKR（グループ `3`）が既定で選択されることを正しく読めるようになる。

**既知の制約**: (1) §13 の parity 検査は Step ID とタイトルだけを対象とし、依存・Fan-out・生成ファイルは対象外である（列構成が節ごとに異なるため）。表を編集する変更では当該行を registry と照合して同時に正す運用とする。(2) `aar` / `ada` は §13 に専用節が無いため理由付きで allowlist に載せた。節の新設は別スコープである。(3) 本変更セットの作業中、別セッションが ARD の実装同期（既定値の単一正本化、wizard の KPI 単一状態、`target_recommendation_id` の伝搬、GUI 既定値、`users-guide` 3 ファイル）を並行で実施している。それらの CHANGELOG エントリは当該セッションが記載する。

**検証**: 横断 parity テストの RED を是正前に実測した——**5 failed / 32 passed**（AAD-WEB の Step 3 件欠落、AAGD の Step 3 件欠落、ASDW-WEB の不正トークン 4 件とタイトル不一致 15 件、および AAS のタイトル 2 件）。うち AAS の 2 件は連体助詞「の」の有無だけの表記揺れによる偽陽性であったため、文書ではなく正規化側を修正して除去した（**4 failed / 33 passed**）。§13.2 / §13.3 / §13.7 の同期後は **37 passed**。ADFDV 個別テストとの重複整理後に 3 ファイル合計 **44 passed**。Data Model 契約テストは **21 passed**、[.github/scripts/validate-io-contract.py](.github/scripts/validate-io-contract.py) の registry mismatch は **6 件 → 0 件**（Schema 0 / Integrity 0 / 149 contracts）。回帰は、変更した要求定義書・registry・template・io-contract・`users-guide` を読むテスト 14 ファイルで **465 passed / 1 skipped**。AAGD Step 6 / 7 の契約テスト（[hve/tests/test_agent_capability_steps.py](hve/tests/test_agent_capability_steps.py)）は **37 passed / 21 subtests passed**。ARD 図の SVG は XML 整形式性を `xml.etree.ElementTree` で検証し、全要素が viewBox 内に収まること（溢れ 0 件）と Step 見出し 8 件が registry の 8 実 Step と一致することを実測した。既定値の単一化後は、7 定数が registry と同一値に解決されることを実行時に確認したうえで、ARD / AKM / ADI / registry 系 8 ファイルで **629 passed / 1 skipped / 27 subtests passed**。追加した AST 検査は、リテラル再宣言（トップレベル / `try` 内 / 関数内）を検出し、alias import と `getattr` fallback を誤検出しないことを 5 ケースで確認した。実装シンボル索引を再生成し、[hve/tests/test_hve_surface_inventory.py](hve/tests/test_hve_surface_inventory.py) / [cq/tests/test_surface_export.py](cq/tests/test_surface_export.py) で **163 passed**。

### Fixed — 観測イベントへのシェル式トークン保存とワークフローカテゴリー順の不一致を規範へ揃え、`instance_id` の適用経路を確定した（FR-RTO-01 / FR-RTO-04 / FR-GUI-21）

GUI からの AAS Step 1 / Step 2 システムテストで検出した 3 件に対応した。新しい設定・CLI 引数・環境変数・依存は追加していない。Workflow 定義・DAG・成果物パス・argv 変換は変更していない。

- **シェルの変数・式トークンを観測イベントの `path` として保存しなくなった（FR-RTO-04、bugfix）**。[hve/runner.py](hve/runner.py) `_track_powershell_files` は `-Path` / `-FilePath` / `-Destination` / リダイレクトの直後の raw token を正規表現で抽出し、外側の引用符を落とすだけだったため、`$p` や `` `$p)) `` のような実パスでない値をファイル I/O として発火していた。判定を [hve/runtime_observability.py](hve/runtime_observability.py) `is_plain_repo_path_token` の単一実装（FR-MAINT-07）へ集約し、producer での発火抑止と `sanitize_event` での fail-closed 拒否の両方で防ぐ。実測した 4 値（`$p` / `$p))` / `` `$p)) `` / `docs/architectural-requirements-app-006.md')`）を回帰データとして固定した。
- **ワークフロー一覧のカテゴリー順を規範へ戻した（FR-GUI-21、bugfix）**。[hve/workflow_registry.py](hve/workflow_registry.py) `WORKFLOW_CATEGORIES` で `AI Agent` が 4 番目へ繰り上がっており、要件が定める末尾配置と不一致だった。このため [hve/tests/test_main_wizard_workflow_menu.py](hve/tests/test_main_wizard_workflow_menu.py) `test_ai_agent_workflows_are_grouped_together` は実際に失敗していた。規範順（Business Engineering → Architecture Design → Software Engineering → 既存ドキュメントのインポート → Knowledge Management → AI Agent）へ戻し、並び順を検査する契約テストを追加した。
- **`instance_id` の適用経路を確定した（FR-RTO-01 改訂、挙動変更なし）**。従来の「APP 単位で並列実行する経路」という表記はプロセス内の Step fan-out を含むとも読め、システムテストで解釈が分かれていた。envelope の `pid` と `observability/events-<pid>.jsonl`（FR-RTO-03）がプロセス単位で対応することを根拠に、`instance_id` を実行プロセス（ジョブ）単位と定め、`workflow_id#app_id` を適用するのは当該プロセスが単一 APP へ専従する場合（Autopilot の APP 別子プロセス等）に限定した。プロセス内の APP fan-out は `step`（FR-RTO-07）で分離する。代替案（Step 単位で `instance_id` を切り替える）は、`RuntimeMetricsRegistry.totals()` が instance 1 件のときだけ Context を引き継ぐ実装のため、StatusLine・CUI Workbench・終了サマリーの Context 表示を `-/-` へ退行させることを確認し、採用しなかった。
- **`users-guide` を registry の実出力へ同期した**。GUI ガイドのワークフロー表へ `ada` を追加して 13 件へ、操作フロー図の一覧と件数を 13 へ、CLI ガイドの対話メニュー例を実出力（`ada` 追加、`aagd` の実行ステップ数を 7 → 9 へ訂正）へ揃えた。ADA ガイドには `AI Agent` カテゴリーから選択する旨を明記した。

**影響範囲**: 観測イベントの `path` 保存と PowerShell ファイル追跡、GUI / CLI のワークフロー一覧の並び順、`users-guide` の該当項。集計値・表示項目・保存先パス・MCP 公開範囲・GUI の選択肢自体は変更していない。

**利用者への影響**: GUI Step 1 と CLI 対話ウィザードで `AI Agent` グループが一覧の末尾へ戻り、`ada` を含む 4 件が同グループに並ぶ。実行時統計の表示値は変わらない。

**既知の制約**: (1) パス判定は fail-closed で、`$` / バッククォート / 引用符 / 丸括弧を含む値は保存しない。現リポジトリの追跡ファイルに該当パスは 0 件（`git ls-files` 実測）。(2) `_track_bash_files` は変更していない。同種のトークンが来ても永続化は sanitizer が fail-closed で遮断し、PowerShell 側でのめの実測事例しかないためである。(3) 操作フロー図の右ペイン表記「QToolBox 16 カテゴリ」は設定画面側の別事象であり、本変更では手を付けていない。(4) [users-guide/hve-technical-architecture.md](users-guide/hve-technical-architecture.md) の「2026-08-07 時点で 12 ワークフロー」は日付付きのスナップショット記述のため変更していない。

**検証**: RED を実装前に実測した——パス保存は sanitizer 4 params と producer 1 件の計 **5 failed**、カテゴリー順は **3 failed / 14 passed**。実装後は観測系 3 ファイル **72 passed**、カテゴリー系 4 ファイル **245 passed / 1 skipped** と GUI 左ペイン **5 passed**。回帰は観測・Fleet・Autopilot 系 10 ファイル **183 passed**、GUI 観測・履歴系 5 ファイル **45 passed**、Console 系を含む群で **203 passed**。実装シンボル索引を [hve-dev/generate_tdd_inventory.py](hve-dev/generate_tdd_inventory.py) で再生成し（test 12,240 行 / feature 421 行 / surface 3,335 行）、[hve/tests/test_hve_surface_inventory.py](hve/tests/test_hve_surface_inventory.py) / [cq/tests/test_surface_export.py](cq/tests/test_surface_export.py) で **163 passed**。`is_plain_repo_path_token` の境界は実行で確認し、Windows 絶対パスとバックスラッシュ区切りパスが受理されることを実測した。

**検証手順に関する注記（本変更とは無関係の既存事象）**: [hve/tests/test_gui_help_content.py](hve/tests/test_gui_help_content.py) を先行させて [hve/tests/test_runner.py](hve/tests/test_runner.py) を同一プロセスで実行すると 13 件が失敗する。単独実行では **213 passed** であり、基準 commit `08c3b3b3` の隔離 worktree で同じ組み合わせを実行しても **13 failed / 216 passed** が再現したため、ファイル間の状態汚染による既存事象と帰属した。

<!-- validation-confirmed -->

### Changed — 事前 QA サブセッションの MCP 自動探索を停止し、Work IQ サーバーの併存による最小権限の迂回を塞いだ（FR-CLI-76 / FR-CLI-79 / FR-QA-03）

事前 QA サブセッションでは、HVE が登録する `_hve_workiq` と、利用者環境の Copilot CLI プラグインが登録する `workiq` が同じセッションへ併存していた。`mcp_servers` を明示すると FR-CLI-76 の縮約条件（`mcp_servers` / `enable_config_discovery` いずれも未指定）を満たさず、自動探索が残るためである。併存側は `tools: ["*"]`（公開 14 件）で登録されるため、HVE が `_hve_workiq` に課す最小権限 allowlist（`ask` のみ）が及ばず、書き込み系ツール（`create_entity` / `update_entity` / `delete_entity` / `do_action`）と `accept_eula` / `call_function` / `get_debug_link` が同一セッションから到達可能だった。`available_tools` / `excluded_tools` は既定 `None`、権限ハンドラは `PermissionHandler.approve_all` であり、FR-TS-03 が求める安全境界がどちらの手段でも張られていなかった。要件を先に改訂したうえで実装を合わせた。

- **要件を改訂した**。[hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) v2.41。FR-CLI-76 の除外経路から「Work IQ を有効化した QA サブセッション」を外し、受入範囲へ移した（除外は 3 経路へ）。FR-CLI-79 の「挙動を変更してはならない経路」を 4 経路から 3 経路へ改め、Azure 除外を本サブセッションにも適用することを明記した。FR-QA-03 の 2 集合分離の根拠を訂正し、併存の実在箇所を事前 QA サブセッションから `workiq-doctor` の tool probe へ移した。
- **事前 QA サブセッションの MCP 範囲を縮約した**。[hve/runner.py](hve/runner.py) の `_build_sub_session_opts` が Work IQ 注入時に `.github/.mcp.json` の宣言分を併合し、`enable_config_discovery=False` を渡す。併合時は Work IQ 別名（`workiq` / `workiq-preview`）を落とし、`_hve_workiq` だけを Work IQ 経路として残す。
- **FR-CLI-79 の Azure 除外を配線した**。`_build_sub_session_opts` に `workflow_id` を追加し、`_run_pre_execution_qa` から渡す。`ard` / `akm` / `adi` / `adoc` では `azure` を併合しない。
- **回帰回避のフォールバックは FR-CLI-76 の既存規則に揃えた**。`.github/.mcp.json` が無い / 読み取れない / `mcpServers` が空の場合は `_hve_workiq` の注入だけを行い、`enable_config_discovery` は `True` のまま据え置く。
- **`workiq-doctor --sdk-tool-probe` は対象外とした**。当該 probe は利用者環境の実態を観測する診断であり、自動探索を止めると診断対象そのものが変わるためである。`WORKIQ_MCP_QUERY_TOOL_NAMES`（6 件）はこの経路の実行確認に引き続き必要なので縮小していない。
- **既存テストの過剰な代理 assert を対象限定へ是正した**。[hve/tests/test_runner_deploy_gate_order.py](hve/tests/test_runner_deploy_gate_order.py) の `enable_config_discovery` 不在 assert は、削除済み ASDW DataDeploy 死パス（当該キーを `if is_asdw_data_deploy:` の内側で設定していた）を検出する代理だった。git 履歴で元の実装を確認したうえで、代理をやめ `asdw_data_deploy` シンボルそのものを禁止する assert へ置き換えた（旧 assert より広く、docstring の意図に一致する）。

**影響範囲**: 事前 QA サブセッションが接続する MCP サーバーの集合。Step 実行のメインセッション、Review サブセッション、`SDKConfig.mcp_servers` / Foundry / ASDW DataDeploy の明示経路、`workiq-doctor`、Workflow 定義・DAG・成果物パス・CLI 引数・GUI の選択肢は変更していない。新規 CLI オプションおよび新規 `SDKConfig` フィールドは追加していない。

**利用者への影響**: 事前 QA サブセッションから、リポジトリが宣言していない MCP サーバー（`workiq` / `github-mcp-server` 等）が外れる。Work IQ の問い合わせは `_hve_workiq` の `ask` で従来どおり行われる。`.github/.mcp.json` を持たない作業ディレクトリでは挙動が変わらない。

**既知の制約**: 併存の解消は事前 QA サブセッションに限る。[hve/orchestrator.py](hve/orchestrator.py) の Work IQ 経路（AKM 検証 / AKM 取込 / ARD ユースケース）は FR-CLI-76 が対象とする `hve/runner.py` の共通セッション生成ヘルパーを経由せず、本要件の受入範囲外のため自動探索が残る。`workiq-doctor` の tool probe も上記の理由で対象外とした。

**検証**: RED を実装前に確認した——新規の [hve/tests/test_runner_pre_qa_mcp_scope.py](hve/tests/test_runner_pre_qa_mcp_scope.py) が **9 failed / 1 passed**、実装後は **10 passed**。回帰はグループ単位で実行し（既知のテスト間汚染を避けるため）、[hve/tests/test_runner.py](hve/tests/test_runner.py) **213 passed**、MCP スコープ 5 ファイル **62 passed**、[hve/tests/test_workiq.py](hve/tests/test_workiq.py) **198 passed**、[hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) **208 passed**、要件系 **161 passed**、`users-guide` 系 **33 passed**。実装シンボル索引を [hve-dev/generate_tdd_inventory.py](hve-dev/generate_tdd_inventory.py) で再生成し、[hve/tests/test_hve_surface_inventory.py](hve/tests/test_hve_surface_inventory.py) / [cq/tests/test_surface_export.py](cq/tests/test_surface_export.py) で **163 passed**。敵対的レビューは各タスク完了ごとに機械検証で実施し、要件改訂 **24 項目**・実装 **25 項目**・`users-guide` **17 項目**・要件テストマッピング **14 項目** すべて ALL_CHECKS_PASSED。レビューで是正した点は 3 件——(1) FR-CLI-76 にフォールバック規則（宣言分が無い場合の扱い）が抜けていたため明記、(2) FR-QA-03 の改訂根拠を「orchestrator の AKM/ARD 経路が使うため」と書きかけたが AST 追跡で当該経路が実行確認コードへ到達しないことが判明したため、実際の消費者である `workiq-doctor` の tool probe に差し替え、(3) 改訂履歴の版番号を実体（v2.40 の次）に合わせて v2.42 から v2.41 へ訂正。

<!-- validation-confirmed -->

### Changed — Work IQ MCP の接続失敗警告に非致命であることを明示し、`users-guide` へタイムアウト不整合の説明を追加した（FR-QA-03 / FR-QA-06 / FR-MAINT-07）

F-09 の根本原因調査で「Copilot CLI の `tools/list` 制限（10 秒）と Work IQ MCP Proxy のリモートツール取得（30 秒）の構造的な不整合」と確定した事象について、**HVE 側で対処できる範囲だけ**を修正した。タイムアウト値そのものは両方とも HVE の管理外であり変更していない。実行時の挙動は変えていない（表示文言と死んだフィールドのみ）。

- **Work IQ 系 MCP サーバーの接続失敗警告に、非致命である旨を追記した**。[hve/runner.py](hve/runner.py) の `session.mcp_servers_loaded` / `session.mcp_server_status_changed` の警告へ「Work IQ は補助的な情報源のため実行は継続します」を付す。実際、実 run では本警告が出た後も `ask` が 5 回実行され 3 問すべてで応答を取得している。この文言不足により、システムテストが本事象を欠陥 F-09 として計上していた。
- **注記は Work IQ 系サーバーに限定した**。他の MCP サーバーへ一律に「非致命」と書いてはならない。ASDW DataDeploy / Foundry 経路は fail-closed ガード（FR-TS-03）を持ち、接続失敗が無害とは限らないためである。`session.mcp_servers_loaded` 側の判定は Work IQ 別名の単一正本（`_is_workiq_mcp_server_name()`、FR-MAINT-07）へ揃えた。
- **`users-guide` に本事象の説明を追加した**。[users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md) の Work IQ トラブルシューティング表へ `MCP error -32001: Request timed out` の行を追加し、原因（10 秒 対 30 秒の不整合）・対応不要であること・`--workiq-request-timeout` が本事象に作用しないこと・`workiq-doctor` では PASS になりうることを記載した。付録D「MCP Server が接続できない」からは相互参照 1 行のみを置き、内容を二重管理しない。
- **write-only の死んだフィールドを削除した**。`_workiq_mcp_connection_failed` は [hve/runner.py](hve/runner.py) に初期化 2 箇所・代入 2 箇所があり読み出しが 0 件だった。利用者への通知は上記の warning が担っており、読み出しを追加する要件根拠は無いため削除した。
- **`CHANGELOG` の `[Unreleased]` に残っていた陳腐化記述 3 件へ追記した**。既存の記述は書き換えず、`> **追記（2026-08-20）**` の 1 行を添えて現状を示す。うち `azure` MCP の件は「打ち切りの正体は CLI の `initialize` 制限 60,000 ms と特定済み、ただし起動が 60 秒を超えた寄与因子は未計測」と**部分的な解消**として正確に記載した。

**影響範囲**: MCP サーバー接続失敗時の警告文言、`users-guide` の Work IQ トラブルシューティング。Workflow 定義・DAG・成果物パス・CLI 引数・GUI の選択肢・MCP サーバーの公開範囲は変更していない。

**利用者への影響**: Work IQ 系 MCP サーバーの接続失敗警告に 1 文が追加される。それ以外の MCP サーバーの警告は変わらない。

**既知の制約**: 事前 QA サブセッションに HVE の `_hve_workiq` と Copilot CLI プラグイン由来の `workiq` が併存する状態は解消していない。**FR-CLI-76 が当該経路の挙動変更を明示的に禁止している**ためである（「Work IQ を有効化した QA サブセッション…の挙動は変更してはならない。これらの経路では自動探索が残るが…」）。また `session.mcp_server_status_changed` 側の Work IQ 判定は従来どおり `_hve_workiq` のみを対象とする。ここを別名集合へ広げると、従来 `console.event`（情報）だった `workiq` / `workiq-preview` の状態変化が `console.warning` へ格上げされ、GUI「実行中の課題」へ流れて警告ノイズが増えるためである。

> **追記（2026-08-20）**: 併存の件は解消済み。FR-CLI-76 を v2.41 で改訂し、当該サブセッションを禁止対象から受入範囲へ移したうえで自動探索を停止した（本 `[Unreleased]` の先頭エントリーを参照）。`session.mcp_server_status_changed` の判定範囲は当時の方針のまま変更していない。

**検証**: RED を実装前に確認した——新規の [hve/tests/test_runner_mcp_status_messages.py](hve/tests/test_runner_mcp_status_messages.py) が **5 failed / 1 passed**。修正後は同ファイル 8 件を含め、[hve/tests/test_runner.py](hve/tests/test_runner.py) / [hve/tests/test_workiq.py](hve/tests/test_workiq.py) / [hve/tests/test_runner_pre_qa.py](hve/tests/test_runner_pre_qa.py) / [hve/tests/test_runner_foundry_mcp_routing.py](hve/tests/test_runner_foundry_mcp_routing.py) で **452 passed / 69 subtests**。実装シンボル索引を [hve-dev/generate_tdd_inventory.py](hve-dev/generate_tdd_inventory.py) で再生成し、[hve/tests/test_hve_surface_inventory.py](hve/tests/test_hve_surface_inventory.py) / [cq/tests/test_surface_export.py](cq/tests/test_surface_export.py) で **163 passed**。`users-guide` と `CHANGELOG` に書いた数値（10 秒 / 60,000 ms / 30 秒）は照合スクリプトで調査の証跡 JSON と突き合わせ **ALL_CHECKS_PASSED** を確認した。敵対的レビューにより 2 件を是正した——(1) 単独 `azure` テストを「`workiq` と `azure` が同一イベントに同居する」実 run 相当のテストへ置換し、イベント単位ではなくサーバー単位で判定していることを固定（テスト数は減り被覆は増えた）、(2) `session.mcp_server_status_changed` の判定を別名集合へ広げた変更が警告ノイズを増やす退行になると判断して撤回し、その方針を固定するテストを追加した。

<!-- validation-confirmed -->

### Changed — Work IQ MCP の `-32001` の根本原因を特定し、要件↔テストのマッピングの TBD を確定記録へ置き換えた（FR-QA-06）

実 run で繰り返し観測されていた `MCP サーバー 'workiq' 接続失敗 (status=failed): ... McpError: MCP error -32001: Request timed out` について、制御実験による根本原因調査を実施した。**HVE の実装コードは変更していない**（調査の結果、HVE 側に原因が無いと確定したため）。更新したのは [hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) の記述のみで、従来「根本原因は未確定」としていた TBD を確定した機構の記録へ置き換えた。

- **根本原因は 2 つの独立したタイムアウトの構造的不整合**である。GitHub Copilot CLI は MCP の `tools/list` リクエストに **10.00 秒**の制限を課す。一方 Work IQ MCP サーバーは自前でツールを持たない **MCP Proxy** で、`https://workiq.svc.cloud.microsoft/mcp` からのツール一覧取得に **30 秒**の HTTP タイムアウトを持つ。リモート取得が `tools/list` の処理へずれ込むと、30 秒の予算を持つ処理を 10 秒で打ち切ることになり `-32001` が発生する。いずれの値も HVE の管理外である。
- **`--workiq-request-timeout` はこの事象に作用しないことを実証した**。当該値が渡る Copilot SDK `MCPServerConfigLocal.timeout` はツール呼び出し専用で、`tools/list` には適用されない。実 run も 600 秒を指定していたが発生していた。
- **失敗していたのは HVE が生成する MCP サーバーではなかった**。実 run には 2 つの Work IQ が同居しており、HVE の `_hve_workiq`（`tools: ["ask"]`）は接続成功、失敗していたのは Copilot CLI プラグインが宣言する `workiq`（`~/.copilot/installed-plugins/work-iq/workiq/.mcp.json`、`@microsoft/workiq@latest` / `tools: ["*"]`）だった。この宣言はリポジトリ管理外の利用者グローバル設定である。
- **HVE のコード変更・MCP 再試行機構の追加は行わない**。10 秒の閾値は CLI 内部の固定値で設定できず、事象はワークフローの成否に影響しない（NFR-RTO-03 と整合。実 run では `ask` が 5 回実行され 3 問すべてで応答を取得している）。要求定義に MCP 接続失敗時の再試行を求める規範要件も存在しない。

**影響範囲**: [hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) の FR-QA-06 節のみ。HVE の実装・テスト・設定・利用者向けドキュメントは変更していない。

**利用者への影響**: なし。当該警告は従来どおり出力され、実行は継続する。重複する `workiq` プラグイン宣言を無効化すれば警告は出なくなるが、これはリポジトリ管理外の利用者環境の判断事項である。

**既知の制約**: 調査時点の環境ではリモートツール取得が一貫して成功したため（`[MCP Proxy] Registered 10 remote tools`）、実 Work IQ の `tools/list` が 10 秒を超える瞬間は直接観測できなかった。したがって「実 run で取得が `tools/list` へずれ込んだ」という最後の 1 段は、確立した機構からの**推論**であり直接観測ではない。実 run のメッセージ接頭辞 `MCP transport host MCP list tools callback failed:` の由来も未確定である（CLI バイナリはアプリ本体の JS を平文で格納しておらず、静的探索では特定できない）。

**検証**: 遅延を制御できる MCP stdio サーバーを実 CLI へ接続する制御実験を行った。`tools/list` の遅延を 8 / 11 / 12 / 70 秒と変えたところ、8 秒は `connected`、11・12・70 秒はいずれも**発行から 10.00〜10.01 秒**で `MCP error -32001: Request timed out` となり、閾値が遅延量によらず一定であることを確認した（CLI 1.0.78 / 1.0.80 の双方で同一）。同じ実験系で `initialize` の制限が 60,000 ms であること、およびその文言 `failed to initialize MCP client: initialize handshake did not complete within 60000 ms` を再現し、**これが実 run で `azure` MCP が出したエラーと完全に一致する**ことをもって実験系の妥当性を確認した。`tools/list` の再発行契機が `notifications/tools/list_changed` のみであることは A/B 実験で確定した（通知なしではツール呼び出しを 2 回跨いでも再発行されない）。Work IQ 実機の計測は直列 3 回・並列 4 / 12・二重構成・背景負荷 8 / 20 プロセスで実施し、`initialize` は 6.1〜56.1 秒（12 並列で最大 53.9 秒）、`tools/list` は 0.10〜0.18 秒だった。レポートに記載した全数値は照合スクリプトで証跡 JSON と突き合わせ、**ALL_CHECKS_PASSED** を確認した。

<!-- validation-confirmed -->

### Fixed — 事前 QA サブセッションへ Work IQ のタイムアウト設定が伝搬しない不具合を修正し、要件↔テストのマッピングを実装状態へ揃えた（FR-CLI-02 / FR-GUI-02 / FR-GUI-03 / FR-GUI-06 / FR-WF-ASDW-02）

システムテストで観測した 2 件の未確定事項（Work IQ 回答の QA 統合可否、実 run 中の MCP 接続タイムアウト）を追跡調査し、その過程で見つかった実装欠陥 1 件と説明文の過剰主張 2 件を修正した。あわせて、要件↔テストのマッピング文書が実装より古くなっていた 4 節を実測で更新した。新しい設定・CLI 引数・環境変数は追加していない。Workflow 定義・DAG・成果物パス・argv 変換は変更していない。

- **`--workiq-request-timeout` が事前 QA サブセッションへ届いていなかったのを修正した（FR-CLI-02）**。[hve/runner.py](hve/runner.py) の `_build_sub_session_opts` が `build_workiq_mcp_config` へ `request_timeout` を渡しておらず、利用者が CLI 引数 / 環境変数 `WORKIQ_REQUEST_TIMEOUT` / GUI「Work IQ」枠で指定した値が **Work IQ の主用途である事前 QA に一切適用されず**、Copilot SDK の既定値に置き換わっていた。[hve/orchestrator.py](hve/orchestrator.py) の Work IQ 経路 4 箇所はいずれも渡しており、runner だけが非対称だった。伝搬を固定する回帰テストが存在しなかったため、あわせて追加した。
- **タイムアウト設定の説明が実際の作用範囲より広かったのを是正した**。[hve/gui/help_content.py](hve/gui/help_content.py) と [hve/gui/page_options.py](hve/gui/page_options.py) が当該設定を「Copilot SDK の MCP クライアントが発行する -32001 (Request timed out) を防ぐための設定」と説明していたが、この値が渡る Copilot SDK の `MCPServerConfigLocal.timeout` は導入済み SDK の定義上 **ツール呼び出しにのみ作用する**（`"Timeout in milliseconds for tool calls to this server."`）。実 run で観測した -32001 は接続時の list-tools で発生しており、本設定では防げない。作用範囲を明示する文言へ置き換え、翻訳カタログと `.qm` を再生成した。
- **要件↔テストのマッピングで「要追加」とされていた 8 件が既に実装済みだったのを実測で確認し、判定を更新した（FR-GUI-02 / FR-GUI-03 / FR-GUI-06 / FR-WF-ASDW-02）**。[hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) の 4 節が v2.14 改訂（ASDW-WEB Step 1.3 の `data_*` 5 件を GUI 入力欄から外す変更）について「要追加」「判定: 要確認」を残していたが、対応するテストは実在し全て PASS していた。**コード変更もテスト追加も行わず**、各項目を実在するテストのノード ID へ差し替え、判定を ✓ へ更新した。FR-GUI-06 の 1 項目が指していた `test_page_options_github_cicd.py` には実装が無く、実体は別の 2 ファイルにあることを記録した（同一契約の二重テストは追加しない／FR-MAINT-07）。
- **`users-guide` の C4 フラグ列挙に `--workiq-request-timeout` を追加した**。[users-guide/hve-technical-architecture.md](users-guide/hve-technical-architecture.md) の Work IQ 行は 11 フラグしか挙げていなかったが、`OrchestrateArgs` は Work IQ 関連 12 フィールドを保持し `to_argv()` が当該フラグを出力する（実測）。
- **Work IQ 回答の QA 統合は正常であることを確定させた**。前回の再測定は診断出力を PowerShell の `Tee-Object` で保存した際に `detail` 欄が壊れて判定できなかった。文字コードを UTF-8 に固定して再取得したところ、`workiq_qa_merge_decision` は **PASS**（`tool=ask / status=PARTIAL`）で、要件の「`FOUND` / `PARTIAL` は統合対象」と一致した。**コードの欠陥ではない**。

**影響範囲**: 事前 QA サブセッションの Work IQ MCP 設定、GUI の設定説明文と英語翻訳、要件↔テストのマッピング文書、`users-guide` の技術アーキテクチャ表。QA の統合判定ロジック・Work IQ のツール許可リスト・Workflow 定義・CLI 引数・GUI の選択肢は変更していない。

**利用者への影響**: Work IQ を有効にした実行で、事前 QA のツール呼び出しに設定値（既定 300 秒）が適用されるようになる。従来はこの経路だけ Copilot SDK の既定値が使われていた。`hve/orchestrator.py` の Work IQ 経路は以前から同じ既定値を適用しており、本修正で両者の挙動が揃う。

**既知の制約**: 実 run 中の `MCP error -32001` について、発生機構は特定した（`session.mcp_servers_loaded` の warning であり実行は継続する／失敗点はツール呼び出しではなく接続時の list-tools ／`-32001` は導入済み Python SDK のソースに存在せず CLI ランタイム側で発生）が、**根本原因（npx の `@latest` 解決コスト・node プロセスの並列リソース競合・Work IQ サービス側の応答遅延のいずれか）は未確定**である。本修正の適用前に再観測しても切り分けられないため、確認方法つきの TBD として [hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) の FR-QA-06 へ記録した。要件根拠が無いため MCP の再試行機構は追加していない。

> **追記（2026-08-20）**: ここで未確定とした根本原因は、後続の「Changed — Work IQ MCP の `-32001` の根本原因を特定し…」エントリーで**特定済み**（Copilot CLI の `tools/list` 制限 10 秒と Work IQ プロキシのリモート取得 30 秒の不整合）。

**検証**: RED を実装前に確認した——新規の `test_pre_qa_sub_session_applies_the_configured_workiq_timeout` が `KeyError: 'timeout'` で失敗（**1 failed / 12 passed**）。修正後は [hve/tests/test_runner_foundry_mcp_routing.py](hve/tests/test_runner_foundry_mcp_routing.py) / [hve/tests/test_workiq.py](hve/tests/test_workiq.py) / [hve/tests/test_runner_deploy_gate_order.py](hve/tests/test_runner_deploy_gate_order.py) で **230 passed / 47 subtests**、影響範囲の [hve/tests/test_runner.py](hve/tests/test_runner.py) / [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py) / QA 並列系で **423 passed / 95 subtests**。`hve/runner.py` の差分は 1 行のみであることを `git diff` で確認した。マッピング文書の判定更新は、対象 4 ファイルで **55 passed / 13 subtests** を実測し、`--collect-only` で 11 件のノード ID の実在を照合したうえで行った。文言変更は `.ts` を更新して `pyside6-lrelease` で `.qm` を再生成し（819 訳 / 0 unfinished）、再生成後の `.qm` から是正後の英訳が引けることを実測、GUI / i18n 関連 5 ファイルで **94 passed**。実装シンボル索引を [hve-dev/generate_tdd_inventory.py](hve-dev/generate_tdd_inventory.py) で再生成し、[hve/tests/test_hve_surface_inventory.py](hve/tests/test_hve_surface_inventory.py) / [cq/tests/test_surface_export.py](cq/tests/test_surface_export.py) で **163 passed**。敵対的レビューにより、当初 2 件だった新規テストのうち 0 境界の 1 件が既存の単体テストと契約を二重所有していたため削除し、1 回しか使われないヘルパーをインライン化した。また文言の過剰主張が [hve/gui/page_options.py](hve/gui/page_options.py) にも同一内容で存在することを検出し、あわせて修正した。最終確認は群別に実施し、Work IQ 経路 **644 passed / 138 subtests**、マッピング裏付け **55 passed / 13 subtests**、i18n **23 passed**、索引鮮度 **163 passed**。

**検証手順に関する注記（本変更とは無関係の既存事象）**: 上記 12 ファイルを 1 コマンドでまとめて実行すると、GUI テストを含む特定の組み合わせで [hve/tests/test_runner.py](hve/tests/test_runner.py) の `TestAvailableExcludedToolsPropagation` などがファイル間の状態汚染により失敗する。本変更が原因でないことを 2 通りで確認した——(1) 本変更の 1 行を一時的に戻しても同じ失敗が再現した、(2) `git worktree` で **HEAD（`29baa18b`）の作業ツリーを作成し、本変更も並行作業も一切含まない状態で同じコマンドを実行したところ同じ失敗が再現した**（18 failed / 684 passed）。既存事象のため本変更では対処せず、最終検証は群別に分けて実施した。

<!-- validation-confirmed -->

### Added — HVE の CLI / GUI 起動時に、実在する markdown-query / code-query 索引 DB をバックグラウンドで差分更新する（FR-CLI-77 / FR-GUI-22）

`hve run` / `hve cli` / `hve orchestrate` と HVE GUI の起動時に、`.mdq/` と `.cq/` に**実在する**索引 DB をバックグラウンドで差分更新するようにした。従来はリアルタイム索引更新（watcher）が起動中の変更しか拾わず、HVE を起動していない間にリポジトリが変わっていると、Agent は古い索引に対して検索していた。新しい CLI 引数・GUI 設定項目は追加せず、制御は環境変数 1 本に限定した。Workflow 定義・DAG・成果物パス・argv 変換は変更していない。

- **共有実装 [hve/index_refresh.py](hve/index_refresh.py) を追加した**。対象は「実在する索引 DB」だけとし、`mdq` は `.mdq/index-<lang>-<strategy>.sqlite` に一致するファイル、`cq` は設定が宣言する profile のうち `.cq/index-<profile>.sqlite` が実在するものとする。**未構築の strategy / profile を新規作成しない**（利用者が選択していない索引——埋め込みモデルの取得を伴う `semantic_paragraph` など——を起動のたびに生成しないため）。この対象規則により、SQLite 索引を持たない `graphrag` とレガシーの `.mdq/index.sqlite` は自動的に対象外になる。更新は差分更新のみで、完全再ビルドは行わない。
- **watcher の起動を差分更新の完了後へ直列化した（FR-CLI-77）**。[hve/orchestrator.py](hve/orchestrator.py) の watcher 起動ブロックを `_start_index_watchers()` へ切り出し、`_start_index_watchers_when_idle()` が専用スレッドで待ち合わせてから起動するようにした。同一の索引 DB へ 2 つの書き込み経路を同時に置かないためで、`mdq` の索引構築は走査の終了時に 1 回だけコミットする（[mdq/indexer.py](mdq/indexer.py) `build_index`）ため走査中は書き込みトランザクションを保持しうる。[users-guide/skills-markdown-query.md](users-guide/skills-markdown-query.md) §4.2 と [users-guide/skills-code-query.md](users-guide/skills-code-query.md) §4.3 が並行書き込みを禁じている根拠に対応する。
- **GUI は差分更新中の実行開始操作を無効化する（FR-GUI-22）**。GUI が起動する `hve orchestrate` 子プロセスは自身の watcher を起動するため、GUI 側の更新と子プロセス側の書き込みが同一 DB へ同時に到達しうる。[hve/gui/main_window.py](hve/gui/main_window.py) の `_refresh_navigation()` でボタンを無効化し、理由をステータス欄へ表示する（新規文言は翻訳カタログへ追加し `.qm` を再生成済み）。完了検知は [hve/gui/app.py](hve/gui/app.py) の `QTimer` ポーリング 1 本で行う。Autopilot の子 GUI では開始しない。
- **索引 DB のファイル名分解を単一実装へ寄せた（FR-MAINT-07）**。`index-<lang>-<strategy>.sqlite` の分解は [mdq/store.py](mdq/store.py) `existing_index_dbs()` を正本とし、同型の実装を持っていた [mdq/query_router.py](mdq/query_router.py) `discover_available_strategies()` を当該関数へ委譲させた。HVE 側にパス規則は持たない。あわせて `lang` を既知の言語だけに限定した（従来は未知の言語名でも strategy を報告していたが、その DB は検索経路が開く `db_path_for(lang, strategy)` と一致しない）。
- **制御は環境変数 `HVE_STARTUP_INDEX_REFRESH` のみとした**。真偽の解釈は [hve/config.py](hve/config.py) `_env_bool` と同一規約（`true` / `1` / `yes` のみ真）。索引と無関係なサブコマンド（`login` / `pricing` / `toolsearch` / `qa-merge` / `workiq-doctor` / `emit-prompt` / `ingest-docs`）では開始しない。引数なし起動は GUI 既定起動のため CLI 側では開始せず、GUI が自身の解決したリポジトリルートで開始する。
- **repo_root は解決済み絶対パスへ正規化する**。実リポジトリでのスモーク検証で、相対パスを渡すと `mdq` の全対象が `'...' is not in the subpath of '.'` で失敗することを検出した（[mdq/indexer.py](mdq/indexer.py) の走査は解決済み絶対パスと `relative_to` するため）。回帰テストを追加した。

### Fixed — `mdq index` が front matter の日付でプロセスごと失敗し、索引が一切更新されなくなっていた

`python -m mdq index` が `TypeError: Object of type date is not JSON serializable` で異常終了し、**すべての Markdown 索引が更新できない状態**だった。PyYAML は `freshness: 2025-08-21` のような引用符なしの値を `datetime.date` として読むが、[mdq/indexer.py](mdq/indexer.py) の front matter 保存は素の `json.dumps` を使っていた。1 ファイルの front matter で走査全体が落ちるため、当該ファイル以降が索引されない。

- `json.dumps(fm, ensure_ascii=False, default=str)` として、JSON 化できない値を文字列へ落とすようにした。`datetime.date` は ISO 形式の文字列になる。
- 本リポジトリでは `docs/original-design-doc-ingest/**/card.md` の 29 ファイルが該当していた。修正後に `python -m mdq index` を実行したところ、heading 戦略で 216 ファイル / 19,065 チャンク、fixed_window 戦略で 276 ファイル / 19,574 チャンクが新たに索引された（それまで反映されていなかった分）。
- 回帰テストは既存の [mdq/tests/test_build_index_progress.py](mdq/tests/test_build_index_progress.py) `test_front_matter_with_unquoted_date_is_indexed` を用いた（本変更で追加した重複テストは敵対的レビューで削除した）。
- 配布キットの複製 `tools/skills/markdown_query/vendor/mdq/` へ同期済み。

**影響範囲**: HVE CLI / GUI の起動処理、`mdq` の索引構築と strategy 検出、`cq` の索引更新契機、`users-guide` の索引ドキュメント。検索 API・索引スキーマ・CLI 引数・GUI の選択肢は変更していない。

**利用者への影響**: 起動直後に索引更新が走るため、GUI では実行開始ボタンが一時的に無効になる（理由は画面に表示される）。CLI では watcher の開始が差分更新の完了まで遅れる。本リポジトリの warm 状態では 4 対象合計 **32.7 秒**（2026-08-20 実測、実際の起動経路と同じプロセス内実行）。`HVE_STARTUP_INDEX_REFRESH=0` で従来どおりの挙動に戻せる。`--dry-run` でも索引は更新される（索引は Workflow の成果物ではないため。watcher が `--dry-run` で起動しないのとは扱いが異なる）。

**既知の制約**: (1) 複数の HVE プロセスを同時に起動した場合、同一索引 DB への書き込みが競合して片方が当該対象をスキップしうる（警告のみ）。プロセス間の排他は本変更の範囲外とした。既存の watcher も同じ性質を持つ。(2) [hve/orchestrator.py](hve/orchestrator.py) が `MdqWatcher` へ渡す DB パスはレガシーの `.mdq/index.sqlite` のままで、`mdq search` が開く `.mdq/index-<lang>-<strategy>.sqlite` と一致しない。本変更では触れていない（別の不具合として分離）。(3) HVE が起動する `CqWatcher` は設定の先頭 profile だけを監視する既存挙動のままで、起動時の差分更新だけが全 profile を対象にする。

**検証**: RED を実装前に確認した——`hve/tests/test_index_refresh.py` が `hve.index_refresh` 不在で 22 error、`hve/tests/test_orchestrator_index_refresh.py` が 8 failed、`hve/gui/tests/test_gui_index_refresh.py` が 6 error（実測）。実装後は新規 3 ファイルで **32 passed**（17 / 9 / 6）。実リポジトリへのスモークで 4 対象全件が差分更新されることを確認した（`{'targets': 4, 'refreshed': 4, 'failed': []}`）。このスモークで相対パス不具合を検出し、RED テストを追加してから修正した。`mdq index` の既存バグは、修正を `git stash` で退避して既存テストが同一の `TypeError` で失敗することを確認してから修正した。回帰は `hve/tests/test_orchestrator.py` / `test_main.py` / `test_orchestrator_branch_mode.py` / `mdq/tests` で **762 passed / 3 skipped / 166 subtests**、`mdq/tests/test_query_router.py` 23 passed、`hve/tests/test_mdq_vendor_sync.py` 41 passed、`hve/gui/tests/test_i18n.py` 23 passed。索引 CSV を [hve-dev/generate_tdd_inventory.py](hve-dev/generate_tdd_inventory.py) で再生成し、`FR-CLI-77` / `FR-GUI-22` が `active-or-described` として登録されたことを照合した。`mdq/tests/test_golden_eval.py::TestRepositoryGoldenSet` の 3 件は本変更の前から失敗しており（`docs/catalog/data-model.md` と `mdq/golden-queries.json` はいずれも未変更）、対象外とした。

<!-- validation-confirmed -->

### Fixed — GUI の必須要件バナーが 2 ワークフローで無警告に出ない不具合を修正し、参照先の無い設定キーを整理した（FR-GUI-01 / FR-GUI-03 / FR-GUI-06）

2026-08-20 の GUI システムテストと、その実行プラン・結果レポートを再分析して検出した不具合に対応した。新しい設定・CLI 引数・環境変数は追加していない。Workflow の DAG・成果物パス・argv 変換は変更していない。

- **workflow `ada` を要件テーブルへ登録した（FR-GUI-01）**。[hve/gui/workflow_step_requirements.py](hve/gui/workflow_step_requirements.py) の `REQUIREMENT_TABLE` に `ada` のエントリが無く、選択してもファイル要件が 1 件も評価されなかった。ADA Step 1 の `required_input_paths` が `docs/catalog/use-case-catalog.md` の 1 件で `required_params` を持たないことを実測し、AAS Step 1 と同じ `use_case_catalog` を必須ファイル種別として登録した。
- **workflow `adfd` の要件エントリが実在しない step ID を指していたのを修正した（FR-GUI-01）**。`adfd` は `6.1` / `6.2` で登録されていたが、[hve/workflow_registry.py](hve/workflow_registry.py) の実際の step ID は `0.1 / 0.2 / 4 / 5 / 1 / 2 / 3` であり、`pick_target_step` の候補に一度も一致しなかった。ガイダンス文の内容が registry の入力宣言と一致する step（`6.1` → `0.1` データフローデータモデル定義書、`6.2` → `2` 監視・運用設計書）へ ID を対応付け直した。文言は変更していない。
- **孤児 step ID を検出するガードテストを追加した**。既存の網羅性検査はワークフロー単位でしか見ておらず、`adfd` のように「登録されているが機能しない」状態を検出できなかった。[hve/gui/tests/test_workflow_requirements_all_steps.py](hve/gui/tests/test_workflow_requirements_all_steps.py) へ `test_requirement_table_step_ids_exist_in_registry` を追加した（`ard` は GUI のグループ ID 方式、`autopilot` は疑似 ID のため除外）。
- **実在しないウィジェットを指す設定マッピングを削除した（FR-GUI-06）**。[hve/gui/settings_apply.py](hve/gui/settings_apply.py) の `_SECTION_FIELDS["C10"]["app_id"]` は `page_options._C10AppId` に存在しない属性を指しており（実測: `app_ids` のみ実在）、`getattr(..., None)` で読み飛ばされる死参照だった。同様に [hve/gui/main_window.py](hve/gui/main_window.py) が `apply_to_widgets` へ渡していた `"C6"` セクションも、`_SECTION_FIELDS` 側に対応が無く無効だったため取り除いた。
- **参照先の無い設定キーを既定値から外し、`_OBSOLETE_KEYS` へ登録した（FR-GUI-03 の準用）**。`app_id` / `tdd_max_retries` / `workbench_layout_state` は GUI ウィジェットも CLI フラグも持たず、`hve/.settings.txt` に「編集しても効かない値」として残り続けていた。あわせて出力制御 9 キー（`log_level` / `timestamp_style` / `verbose` / `quiet` / `show_stream` / `no_color` / `banner` / `screen_reader` / `final_only`）も同様に整理した。この 9 キーは設定画面の「出力制御」ノードを撤去した際に `_SECTION_FIELDS` への登録も外れており（既存の契約テストが `"C6" not in _SECTION_FIELDS` を固定済み）、保存も復元もされない状態だった。セッション限りの設定として一貫させ、値は Step 1 右ペインまたは CLI フラグで都度指定する。`OrchestrateArgs` への反映経路（argv 変換）は変更していない。
- **`orchestrate_args.py` の陳腐化した実装状況コメントを実態へ揃えた**。「`_C4WorkIQ` が 12 フィールドすべてのフォームを提供」とあったが、`workiq_tenant_id` の GUI 入力経路は廃止済みで `_OBSOLETE_KEYS` へも登録済みである。コメントのみの変更で、`to_argv()` の挙動は変えていない。
- **`users-guide` の GUI 変更手順へ [hve/gui/settings_apply.py](hve/gui/settings_apply.py) を追加した**。[users-guide/hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md) の「設定・実装の正本」表と「変更手順」は `settings_store.py` → `settings_window.py` → `orchestrate_args.py` の 3 点しか示しておらず、永続化・復元の要である `_SECTION_FIELDS` への登録が抜けていた。あわせて C6（出力制御）の値が保存されない旨をカテゴリ表へ明記した。
- **Work IQ 診断の前回 FAIL は診断コマンドの待ち時間不足に起因していた（コード変更なし）**。システムテストの診断は `--sdk-tool-probe-timeout` を指定せず既定 60 秒で実行され、`copilot_tool_probe_send` がタイムアウトして FAIL していた。`users-guide` が推奨する 300 秒（＋ `--skip-mcp-probe`）で再測定したところ同チェックは PASS となり、終了コードも 1 から 0 へ変わった。

**影響範囲**: GUI Step 1 の必須要件バナー（`ada` / `adfd` で新たに表示される）、設定ストアのキー集合、`users-guide` の GUI ガイド。Workflow 定義・DAG のスケジューリング・成果物パス・CLI 引数・GUI の選択肢は変更していない。

**利用者への影響**: `hve/.settings.txt` に保存済みの `app_id` / `tdd_max_retries` / `workbench_layout_state` と出力制御 9 キーは、次回読み込み時に `_OBSOLETE_KEYS` の移行で除去される。いずれも従来から実行に反映されていなかった値のため、実行時挙動は変わらない。

**既知の制約**: (1) Work IQ 診断の `workiq_qa_merge_decision` は再測定後も WARN のままで、その理由は未確定である。診断出力を PowerShell の `Tee-Object` で保存した際に `detail` 欄の日本語がコンソールの文字コードで壊れたためで、`name` / `status` のみを根拠にしている。`users-guide` は「一次情報が見つからなかっただけなら WARN は正常」と明記しており、本変更では断定しない。(2) 実 run 中の MCP 接続タイムアウト（`MCP error -32001`）は診断の timeout とは経路が異なり、再現条件を特定できていないため本変更の対象外とした。

> **追記（2026-08-20）**: (1) は後日 UTF-8 を固定して再取得し、`workiq_qa_merge_decision` が **PASS**（`tool=ask / status=PARTIAL`）であることを実測して**解消済み**。(2) は後続の「Changed — Work IQ MCP の `-32001` の根本原因を特定し…」エントリーで**特定済み**。

**検証**: RED を実装前に確認した——新規の `test_requirement_table_step_ids_exist_in_registry` が `[('adfd', '6.1'), ('adfd', '6.2')]` で失敗し、既存の `test_requirement_table_covers_every_registered_workflow` が `ada` 未登録で失敗（**2 failed / 7 passed**）。修正後は対象 12 ファイルで **144 passed / 13 subtests**。あわせて全 13 ワークフローについてバナー件数を実測し、孤児エントリ 0 件・未登録ワークフロー 0 件・バナー 0 件のワークフロー 0 件（修正前は `ada` / `adfd` が 0 件）を確認した。実装シンボル索引を [hve-dev/generate_tdd_inventory.py](hve-dev/generate_tdd_inventory.py) で再生成し、`hve/tests/test_hve_surface_inventory.py` / `cq/tests/test_surface_export.py` / `hve/tests/test_mdq_vendor_sync.py` / `hve/tests/test_markdown_query_kit_contract.py` で **219 passed**（うち索引鮮度の 3 件を含む）。独立した敵対的レビューで、設定ウィンドウ系のテスト 3 箇所（[hve/gui/tests/test_settings_window_cq_persistence.py](hve/gui/tests/test_settings_window_cq_persistence.py) 2 箇所 / [hve/gui/tests/test_settings_window_mdq_persistence.py](hve/gui/tests/test_settings_window_mdq_persistence.py) 1 箇所）が「他オプションの変更」を模す値として廃止対象の `verbose` を使っており、うち 2 件が `KeyError: 'verbose'` で失敗することを検出した。生存キー `create_issues` へ置き換え、設定ウィンドウ周辺 9 ファイルで **175 passed / 218 subtests**。あわせて `hve/` / `mdq/` / `cq/` の 274 ファイルを走査し、削除した 12 キーを設定ストア経由で読む本番経路が 0 件であることを機械検査した。Work IQ 診断の再測定は `python -m hve workiq-doctor --skip-mcp-probe --qa-integration-probe --sdk-tool-probe-timeout 300 --json` を 1 回実行し、PASS 15 / SKIP 2 / WARN 1、終了コード 0。

<!-- validation-confirmed -->

### Added — HVE GUI のシステムテストを 5 層（L0〜L4）で実施し、`users-guide` の Step 1 オプション画面の記述を実装へ揃えた

別途合意したシステムテスト実行プランの 27 タスクを実行した。GUI の実配線をヘッドレスで駆動して静的棚卸し・単体回帰・設定駆動・dry-run・実 run を計測し、要件別に合否を判定した。HVE の実行時挙動（Orchestrator / Workflow 定義 / DAG / 成果物パス / CLI 引数 / GUI の選択肢）は変更していない。コード修正は本テストの方針に従い行わず、検出した問題は記録に留めた。

- **`users-guide` の Step 1 オプション画面の記述を実装へ揃えた（唯一の恒久成果物の変更）**。`users-guide/hve-gui-orchestrator-guide.md` は「`QToolBox` アコーディオン形式で 16 カテゴリに分類」と記載し 16 行のカテゴリ表を持っていたが、実装は `QGroupBox` 群へ置き換え済みで（`hve/gui/page_options.py` `_setup_ui` に「QToolBox から置き換え」と明記）、実カテゴリ枠は 13 個だった。実測した 13 カテゴリ（`C1` / `C3` / `C4` / `C5` / `C6` / `C7` / `AZURE` / `AGENTIC` / `C10` / `C11` / `C13` / `C14` / `C17`）と画面上の見出し・主な内容へ表を作り直し、`C2` / `C8` / `C9` / `C12` / `C15` / `C16` が他カテゴリへ統合・廃止された旨の注記を更新した。オプション数の記述も `OrchestrateArgs` の実測フィールド数（114）へ改めた。
- **静的棚卸し（L0）**。`settings_store.defaults()` 130 キー（`[options]` 112 / `[mdq]` 16 / `[cq]` 2）、`settings_apply._SECTION_FIELDS` にマップ済み 97 キー、`OrchestrateArgs` 114 フィールド、`orchestrate` CLI 131 オプション、登録ワークフロー 13 / 総ステップ 131、要求定義書の要件 ID 288 件（うち GUI 関連 55 件）を実コードから機械抽出した。
- **設定駆動検証（L2）**。`[options]` 112 キーを 1 項目ずつ変更して argv 反映を実測し、105 件が反映、2 件は GUI の入力検証がプローブ値を拒否、5 件は活性制御・設計上の非伝搬・計測限界で説明できることを確認した。要件が相互作用を規定する `auto_qa` × `qa_answer_mode` × `qa_akm_background_merge` × `akm_model` / `akm_reasoning_effort` / `akm_context_tier` の 72 通りを網羅し、契約違反 0 件だった。
- **dry-run 検証（L3）**。GUI が確定した argv をそのまま `--dry-run` で実行し、13 ワークフローすべてが `returncode=0` かつ DAG 計画（Wave 構成と `Plan summary`）を出力することを確認した。
- **実 run（L4）**。隔離 git worktree で AAS Step 1（`--auto-qa` / `--qa-akm-background-merge` / Work IQ 有効）と Step 2 を実行し、いずれも `returncode=0`、tool 失敗 0 / model 失敗 0 だった。Step 1 は 1537.2 秒・tool 呼び出し 76 件、Step 2 は Fleet mode で 14 fan-out 子すべてが完了した。バックグラウンド AKM により `knowledge/` の 35 ファイルが更新され、Step 1 が `knowledge/D01, D02, D05, D06, D07, D09` を実際に参照したことを実行ログで確認した。
- **要件別判定**。`FR-GUI-01` / `02` / `03` / `04` / `05` / `06` / `07` / `16` / `17` / `20` / `21`、`FR-QA-04` / `05` / `08`、`FR-MAINT-07` を含む 21 項目すべてが PASS だった。

**影響範囲**: `users-guide/hve-gui-orchestrator-guide.md` の Step 1 オプション画面の節のみ。`hve/**` のコード・設定・CLI 引数は変更していない。実 run の生成物は隔離 worktree 内に残置し、本体リポジトリへは反映していない。

**既知の制約**: 検出した 9 件の問題は記録のみでコード修正していない。うち `users-guide` の乖離 1 件だけがテスト計画で更新作業として定義されていたため本変更で解消済み。`reasoning_effort` はモデル一覧を取得していない環境のため選択肢が 1 つしかなく、代替値を投入した反映確認ができなかった。`[options]` 単一キー掃引はキー間の相互作用を網羅していない。

**検証**: GUI 単体テスト 150 ファイルを隔離 worktree（HEAD 一致・未コミット変更 0 件）でファイル単位実行し **1608 passed / 2 failed / 1 skipped**（2036.2 秒）。失敗 2 件はいずれも `workflow_step_requirements.REQUIREMENT_TABLE` に workflow `ada` が未登録であることに起因し、worktree が HEAD 断面かつ未コミット変更 0 件であることから本作業以前から存在する既存の失敗と帰属判定した。dry-run は 13 ワークフローすべて `returncode=0` かつ DAG 計画出力あり。実 run は Step 1 / Step 2 とも `returncode=0`。`users-guide` 更新後に再計測し、ガイドの記述・カテゴリ表の行数・実カテゴリ枠数がすべて 13 で一致し差分 0 件になることを確認した。

<!-- validation-confirmed -->

### Fixed — Work IQ の `PARTIAL` 応答が語句の部分一致で握り潰される不具合を修正し、io-contract の static 入力実在検査と Fleet wave のフェーズ非実行警告を追加した（FR-QA-03 / FR-WF-OUT-11）

2026-08-19 の GUI 実行（AAS Step 1 → Step 2）で検出した 3 件に対応した。新しい設定・CLI 引数・環境変数は追加していない。

- **`PARTIAL` の Work IQ 応答が QA へ統合されない不具合を修正した（FR-QA-03、bugfix）**。[hve/qa_merger.py](hve/qa_merger.py) `merge_workiq_results` が独自の `_error_indicators`（`"未実施"` 等 8 語の**部分文字列一致**）で応答を破棄していた。統合可否の正本は [hve/workiq.py](hve/workiq.py) `is_workiq_result_mergeable`（tool 実行確認済み + status `FOUND`/`PARTIAL`）であり、呼び出し元 [hve/runner.py](hve/runner.py) は既に絞り込んだ結果だけを渡すため、当該フィルタは偽陰性しか生まない二重実装だった。実測では Work IQ が Outlook のメール 1 件を提示した `STATUS: PARTIAL` の応答が、本文の「深掘り検索は今回**未実施**」（＝どの追加検索を行わなかったかの説明）に一致して破棄され、QA 質問票に Work IQ 由来の記述が 0 件になっていた。`workiq-doctor --qa-integration-probe` は正本だけを見るため `PASS` を返し、利用者が原因を特定できない状態だった。STATUS 判定と「関連情報なし」完全一致判定は既存テスト 3 件が依存するため残している。
- **io-contract の `kind: static` 入力の実在を CI で検査するようにした（FR-WF-OUT-11 新規）**。FR-WF-OUT-05 の registry mismatch 検査は `required: true` かつ `kind: agent_artifact` の入力しか照合せず、`kind: static` はどの検査の対象にもなっていなかった。[.github/scripts/validate-io-contract.py](.github/scripts/validate-io-contract.py) に `check_static_input_paths()` を追加し、変数記法（`{...}` / `<...>`）・glob（`*` / `?`）・ディレクトリ参照（末尾 `/`）を含まない確定パスの実在を integrity error として検査する。除外は既存の [.github/io-contract-exceptions.yaml](.github/io-contract-exceptions.yaml) の `static_paths` のみで、本検査専用の除外機構は追加していない。
- **実体と一致しない static 宣言 8 件を解消した**。`knowledge/D05`（中黒/ハイフン）と `knowledge/D09`（ハイフン/中黒）の区切り文字ゆれ 6 件、`knowledge/D15` のファイル名断片 1 件を実体へ揃え、生成タイミングに依存する `.github/workflows/azure-static-web-apps-app009.yml` 1 件は `static_paths` へ除外登録した。あわせて同じ誤パスを持つ [.github/prompts/](.github/prompts/) 8 ファイルと [.github/skills/architecture-questionnaire/references/question-template.md](.github/skills/architecture-questionnaire/references/question-template.md) の計 10 箇所も修正した（Agent が存在しないパスの読み取りを指示されていた）。
- **Fleet wave で事前 QA / 敵対的レビューが無言で実行されない状態を可視化した（FR-QA-03 改訂）**。[hve/orchestrator.py](hve/orchestrator.py) `_fleet_wave_runner` は実行可能 Step が 2 件以上の wave を単一 Copilot セッションへ委譲し、`StepRunner.run_step` を経由しない。事前 QA（Phase 0）と敵対的レビュー（Phase 3）は `run_step` の内部にあるため、利用者が `--auto-qa` / `--qa-akm-background-merge` / `--auto-contents-review` を明示的に有効化しても発火しなかった。[hve/fleet_mode.py](hve/fleet_mode.py) に `format_fleet_wave_skipped_phases_warning()` を追加し、Fleet 起動成功を確認した時点で wave ごとに 1 回警告する。起動に失敗して通常経路へフォールバックした場合は警告しない。Fleet 経路自体の挙動は変更していない。
- **AAS Step 2 の入力宣言に `knowledge/` を任意補強として明記した**。[.github/scripts/templates/aas/step-2.md](.github/scripts/templates/aas/step-2.md) の `## 入力` に `knowledge/D01, D02, D05, D09, D15, D19` を追加した。Fleet worker へ渡るのは body テンプレート由来の prompt と `required_input_paths` であり、従来はどちらにも `knowledge/` が現れず、実測でも Step 2 の 14 fan-out 子すべてが `knowledge/` を参照していなかった。必須化はしていない。
- **AAS Step 1 の io-contract を実測へ合わせた**。[.github/io-contracts/Arch-ApplicationAnalytics--aas--1.yaml](.github/io-contracts/Arch-ApplicationAnalytics--aas--1.yaml) と `Arch-ApplicationAnalytics.yaml` が `knowledge/D01,D02,D05,D06,D07,D09` を `required: true` と宣言していたが、実行時に読まれず（observability の `file_io` で 0 件、対照の AKM 子は 202 件）、実行時にもCIにも強制されていなかった。同ファイルが既に `knowledge/` ディレクトリを `required: false` で宣言しているため、6 件を `required: false` へ揃えた。実行時挙動は変わらない。

**影響範囲**: Work IQ の QA 統合判定、io-contract の CI 検査、Fleet wave 開始時の警告出力、AAS の入力宣言・テンプレート。Workflow の DAG・成果物パス・CLI 引数・GUI の選択肢は変更していない。

**検証**: `test_qa_merger.py` の再現テストが修正前 RED（`AssertionError: '' == ''`、1 failed / 137 passed）→ 修正後 GREEN。`test_hve_surface_inventory.py` / `test_surface_export.py` / `test_qa_merger.py` / `test_workiq.py` / `test_runner_pre_qa.py` / `test_fleet_mode.py` / `test_phase8_s4_reinforcement.py` / `test_workflow_registry.py` で **803 passed / 1 skipped / 47 subtests passed**。`python .github/scripts/validate-io-contract.py` は `Schema errors: 0` / `Integrity errors: 0` / `Registry mismatch errors: 0`。

### Changed — HVE 保守の要件参照を不具合調査へ拡張し、Skill へ適用判断規則と要件 ID 直引きを追加した（NFR-CTX-01 / FR-MAINT-01 / FR-MAINT-02 改訂）

`hve` 自体の保守で要求定義書を参照させる経路に 3 つの欠落があった。(1) 起動条件が「HVE 対象変更」に限定され、`hve/**` を読むだけの不具合調査では Skill が起動しなかった。(2) Skill に §1.3 の 3 層優先順位（規範要件 / 説明的基線 / 履歴情報）と §3.7 の変更種別判定規則が無く、適用可否と変更種別の判定に要求定義書本文の追加取得を要していた。(3) 要件 ID が既知でも検索経路しか無かった。新しい設定・CLI 引数・環境変数・モジュールは追加していない。

- **不具合調査を Skill の起動対象に加えた（NFR-CTX-01 改訂）**。repository-wide ルーター（[.github/copilot-instructions.md](.github/copilot-instructions.md) §12）と path-specific instructions（[.github/instructions/hve-maintenance.instructions.md](.github/instructions/hve-maintenance.instructions.md)）の適用契機を「変更」から「変更・不具合調査」へ拡張した。ルーターは NFR-CTX-01 が定める 3 箇条構成のままとし、箇条数を増やしていない。
- **適用判断規則を Skill へ保持させた（FR-MAINT-01 改訂）**。[.github/skills/hve-requirement-traceability/SKILL.md](.github/skills/hve-requirement-traceability/SKILL.md) の「編集前確認」へ 3 層優先順位とコードを正解としない規則を、「feature の TDD 順序」へ変更種別 3 値の判定規則を追加した。H2 セクションは 9 個のままで増やしていない。
- **要件 ID の直引きを検索より優先させた（FR-MAINT-02 改訂）**。ID が既知の場合は検索せず、[hve-dev/hve-feature-inventory.csv](hve-dev/hve-feature-inventory.csv) の当該行の `line` 列が指す定義行だけを読む。同一の問いに対し BM25 の chunk 返却が 3,613 tokens / 151 ms であるのに対し、直引きは 501〜687 tokens で検索を伴わない（実測）。既存 CSV の列をそのまま使うため、新しい索引ファイルもヘルパーも追加していない。
- **受入ケースの自動適用範囲の列挙を正した**。[hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) の NFR-CTX-01 受入ケースは path-specific instructions の自動適用範囲を 4 パターンと記載していたが、正本である §3.7 と実 `applyTo` は `cq/**` と `tools/skills/code_query/**` を含む 6 パターンである。契約テストの `_APPLY_TO` は 6 パターンを固定しており振る舞いは正しかったため、文書側だけの不一致を解消した。

**影響範囲**: Coding Agent が `hve` 自体を保守するときの参照手順のみ。HVE の実行時挙動（Orchestrator / Workflow 定義 / DAG / 成果物パス / CLI 引数）は変更していない。SKILL.md は 2,189 → 2,684 tokens（+495、+22.6%、tiktoken cl100k_base 実測）。

**既知の制約**: (1) `python -m mdq index` はリポジトリ全体では失敗する。`docs/original-design-doc-ingest/**/card.md` の frontmatter に非引用の日付があり [mdq/indexer.py](mdq/indexer.py) の `json.dumps` が `TypeError` になるためで、コミット済み・未変更のファイルに起因する既存不具合であり本変更とは無関係である。golden 回帰は `hve-dev` に限定したスクラッチ索引で実施した。(2) [mdq/golden-queries.json](mdq/golden-queries.json) の DOC-01 は `docs/catalog/data-model.md` の分割によりアンカーが解決できない既存 stale 状態で、本変更の対象外である。

**検証**: 契約テストの逐語定数を先に更新して実装前 RED を確認した（[hve/tests/test_hve_requirement_traceability_contract.py](hve/tests/test_hve_requirement_traceability_contract.py) で **5 failed / 7 passed**、失敗内訳は編集前確認・feature TDD 順序・選択取得・path-specific instructions・repository-wide ルーターの 5 件）。実装後は同ファイルで **12 passed**。索引を [hve-dev/generate_tdd_inventory.py](hve-dev/generate_tdd_inventory.py) で再生成し、`test_hve_requirement_traceability_contract.py` / `test_hve_surface_inventory.py` / `.github/scripts/tests/test_validate_hve_requirement_traceability.py` で **240 passed / 2 skipped**（skip 2 件は Windows で symlink を作成できない既知分）。golden 回帰は requirements グループ 16 件を `hve-dev` スクラッチ索引で評価し、`validate_golden` の問題 0 件、改訂した 3 要件（REQ-03 / REQ-12 / REQ-13）はいずれも rank=1、全体で top-1 0.875 / top-5 0.9375 / MRR@5 0.9062。唯一 MISS の REQ-04（FR-DAG-04、本変更の非対象）は編集前の内容を持つ main 索引でも同じく MISS することを対照実行で確認しており、本変更による退行ではない。FR-MAINT-04 の PR トレーサビリティ validator（[.github/scripts/validate-hve-requirement-traceability.py](.github/scripts/validate-hve-requirement-traceability.py)）を実変更 13 ファイルと本変更のトレーサビリティブロックで実行し **exit=0** を確認した（`TDD-Evidence` は `RED=<test-path> failed ...; GREEN=<test-path> passed ...` の形式が必須で、テストパスを含まない記述は拒否される）。

<!-- validation-confirmed -->

### Fixed — セッション終了統計の欠落・fan-out 展開後のステップ総数の過大表示・Work IQ preview サーバーの実行未検出を修正した（FR-QA-03 改訂）

2026-08-19 の GUI 実行ログ調査で検出した 3 件の欠陥を修正した。いずれも既定動作のバグ修正であり、新しい設定・CLI 引数・環境変数は追加していない。

- **`session.shutdown` の `files_modified` を件数として扱うようにした**。Copilot SDK の `ShutdownCodeChanges.files_modified` は `list[str]` だが [hve/runner.py](hve/runner.py) は `int()` に渡しており、1 件以上のファイル変更を伴う `session.shutdown` では必ず `TypeError` になっていた（変更 0 件のときは `[] or 0` が 0 に落ちるため例外にならない）。SDK 側がイベントハンドラの例外を握り潰すため無症状に見えるが、実際には `📈 Stats: ...` 行と直後の `premium_requests` stats_event が同時に失われ、GUI 統計ポップアップの Premium Requests 累積が常に 0 のままだった。`list` / `tuple` なら要素数、数値ならその値を使う（後方互換）。
- **fan-out 展開後のステップ総数表示を実行対象数に合わせた**。[hve/orchestrator.py](hve/orchestrator.py) の `_expand_workflow_for_dag` は deferred fan-out のランタイム再展開に備えて fan-out ベース ID を `active_step_ids` に残すため、`len(active_step_ids)` を「実行計画パネルの合計」と「進捗の分母」に使うと過大になっていた（AKM は 23 と表示されるが実行対象は 22）。[hve/dag_executor.py](hve/dag_executor.py) に `total_display_steps()` を追加し、展開後 step 索引に存在する非コンテナの active step だけを数える単一実装へ寄せた（FR-MAINT-07）。コンテナ step も active に入るが wave には現れないため除外する（実測: ASDW-WEB は 114 → 104、ADOC は 23 → 19）。あわせて Workbench Header#2 のステップ一覧からもコンテナを除外し、リポジトリ内の他のステップ数表示と規則を揃えた。
- **`workiq-preview` MCP サーバーを Work IQ として認識するようにした（FR-QA-03 改訂）**。Work IQ プラグインの preview ビルドは同一サービスを `workiq-preview` という別サーバー名で登録するが、[hve/workiq.py](hve/workiq.py) の実行確認集合にも [hve/runner.py](hve/runner.py) のメインセッション分離集合にも含まれていなかった。前者の欠落は当該サーバー経由の参照系ツール実行が確認されず QA への統合が 0 件になり得る問題、後者の欠落は `--mcp-config` に当該サーバーを含む設定を渡したときメインコーディングセッションへ接続されてしまう問題である。server 名の正本を `WORKIQ_MCP_SERVER_NAMES` に一本化し、両者がそこから導出するようにした（FR-MAINT-07）。MCP サーバーへ公開する allowlist（`ask` のみ）は変更していない。

**影響範囲**: CLI / GUI の実行時表示（`📈 Stats:` 行・実行計画パネルの合計・進捗バーの分母・Workbench Header#2 の一覧）と、事前 QA の Work IQ 実行確認・メインセッションの MCP フィルタ。ワークフロー定義・DAG のスケジューリング・成果物パス・`knowledge/` の出力形式は変更していない。GUI の Premium Requests 累積は本修正で初めて加算されるようになるため、これまで 0 だった表示が実値に変わる。

**既知の制約**: deferred fan-out（依存 step の出力を待って展開する fan-out）は実行計画表示の時点で子が未確定のため、合計がランタイム展開後に増える。従来の `len(active_step_ids)` も同様に増えており回帰ではないが、実行計画時点の合計に展開分は含まれない。また `azure` MCP サーバーが 21 並列のサブセッションで接続失敗した事象は、原因が npx の `@latest` 解決コストか node プロセスの並列リソース競合か切り分けできておらず、証跡ログも削除済みのため本変更では扱っていない。

> **追記（2026-08-20）**: `azure` MCP の件は**部分的に解消**。打ち切りの正体が Copilot CLI の `initialize` 制限 **60,000 ms** であることを制御実験で再現し、エラー文言が実 run と完全一致することを確認した。**ただし起動が 60 秒を超えた寄与因子（`@latest` 解決コストか並列競合か）は依然として未計測**である。

**検証**: 新規 RED を実装前に確認した（[hve/tests/test_runner_shutdown_stats.py](hve/tests/test_runner_shutdown_stats.py) / [hve/tests/test_fanout_step_count_display.py](hve/tests/test_fanout_step_count_display.py) / `test_workiq.py::TestWorkIQQueryToolDetection` で **13 failed / 11 passed**）。実装後は同 3 対象 + `test_runner.py::TestMcpServerFiltering` で **25 passed / 35 subtests**。回帰は 16 ファイル（`test_runner.py` / `test_console.py` / `test_workiq.py` / `test_fanout.py` / `test_dag_executor.py` / `test_dag_planner.py` / `test_deferred_fanout.py` / `test_dag_executor_fanout_deferred.py` / `test_orchestrator.py` / `test_runner_pre_qa.py` / `pricing/test_workbench_state_ai_credit.py` ほか）で **943 passed / 13 failed**。この 13 件は変更前に取得したベースラインと**同一の顔ぶれ・同一件数**（`test_runner.py` の `TestSessionIdPropagation` 5 件 / `TestAvailableExcludedToolsPropagation` 6 件 / `TestStepWorkDirectory` 1 件 / `TestStepRunnerStreamEvents` 1 件）であり、本変更による増加はない。`hve-dev/generate_tdd_inventory.py` を再生成し、索引整合の `test_hve_surface_inventory.py` / `cq/tests/test_surface_export.py` で **163 passed**。独立した敵対的レビューを実施し、指摘 10 件のうち 9 件を反映した（未反映 1 件は現行 SDK の型では発生し得ない入力型への例外処理追加で、不要な防御的実装のため見送った）。

<!-- validation-confirmed -->

### Fixed — Knowledge Management (AKM) の Cloud 経路が registry と非同期だった問題を修正した（FR-CLOUD-06 改訂）

[.github/workflows/auto-knowledge-management-reusable.yml](.github/workflows/auto-knowledge-management-reusable.yml) は `[AKM] Step.1` の Step Issue を 1 件だけ作成し、同ファイル内に「AKM はステップが 1 つのみ」と明記していた。一方 CLI / GUI の正本である [hve/workflow_registry.py](hve/workflow_registry.py) の AKM 定義は Step.1（`KnowledgeManager`）→ Step.2（`QA-DocConsistency` による `knowledge/` 横断整合性レビュー）の 2 ステップである。AKM は Cloud parity テストの対象外だったため不一致を検出するゲートが存在せず、Cloud 利用者だけが横断整合性レビューを受け取れない状態が固定されていた。

- **Cloud へ Step.2 を追加した**。初期化時に `[AKM] Step.2: knowledge/ 横断整合性レビュー` を `akm:blocked` 付きで作成して Root Issue へ紐付け、Step.1 完了（`akm:done`）で `akm:blocked` を外して Copilot をアサインし、Step.2 完了で Root Issue へ `akm:done` と完了コメントを付与する。`labeled` と `closed` の二重発火で同じ Step を 2 回起動しないガードは AAR と同じ方式（`akm:ready` / `akm:running` / `akm:done` のいずれかを持つ場合はスキップ）にした。
- **D01〜D21 の fan-out は Cloud で Step Issue へ展開しない**。`knowledge/` の出力空間は `target_files` の指定によらず D01〜D21 全体と `business-requirement-document-status.md` を含むため、Step Issue 単位の並列化は同一ファイルへの同時書込みを生む（FR-QA-03 と同じ根拠）。Root Issue の concurrency（`akm-knowledge-write-<repo>`、FR-CLOUD-21）とも両立しない。
- **AKM を parity テストの対象へ入れた**。AKM は [.github/scripts/bash/lib/workflow-registry.sh](.github/scripts/bash/lib/workflow-registry.sh) へ未登録で Cloud YAML が Step をハードコードしているため、bash / Python 双方の registry と照合する `TestUnifiedWorkflows` ではなく、`hve/workflow_registry.py` のみと照合する `TestAkmCloudParity` を追加した。
- **[users-guide/km-guide.md](users-guide/km-guide.md) の陳腐化した注記を是正した**。「上図の SVG は Step 2 と fanout を描いていない（図の更新は要確認）」は `chain-akm.svg` の描き直しで、「両者の同期は本ガイドの範囲外の課題として要確認」は本修正で、それぞれ解消済みである。
- **[hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) に残っていた誤った原因記述を更新した**。`TestRunWorkflowFanout::test_aad_web_fanout_meta_is_forwarded_to_step_runner` の失敗を「`hve/workflow_registry.py` に起因する別事象」と記録していたが、実際の原因はテストが `service_catalog` を合成キー `SVC-FANOUT-TEST` へ差し替えていた一方、後から入った APP-ID fan-out フィルタが選択 APP に紐づかないキーを除外し Step 2.2 が `fanout-empty` で skip されていたことだった（実測: 合成キーで子 0 件 / 実キーで子 24 件）。解消済みである旨へ書き換えた。

**影響範囲**: Cloud（Issue Template）経由の AKM 実行のみ。CLI / GUI の AKM 実行経路、`hve/workflow_registry.py` の定義、`knowledge/` の出力形式、Issue Form の入力項目は変更していない。Cloud の AKM は Root Issue が `akm:done` になるまでに作成される Step Issue が 1 件から 2 件へ増える。

**既知の制約**: AKM は `.github/scripts/bash/lib/workflow-registry.sh` へ未登録のままであり、bash registry を用いる `TestUnifiedWorkflows` の照合対象には入らない。bash registry への登録は Bash orchestration 経路の新設を伴うため本変更の範囲外とした。

**検証**: 新規 RED（[hve/tests/test_cloud_reusable_workflow_parity.py](hve/tests/test_cloud_reusable_workflow_parity.py) の `TestAkmCloudParity` 4 件）を実装前 **4 failed**、実装後は同ファイル全体で **46 passed** を確認した。Cloud 契約テスト群（`test_cloud_reusable_workflow_parity.py` / `test_issue_template_qa_parity.py` / `test_workflow_registry_agentic.py` / `test_self_improve_completeness.py` / `test_phase6_option_parity.py` / `test_adversarial_review_policy_contract.py` / `test_cloud_dispatcher_asdw_dispatch.py`）で **357 passed + 263 subtests**。ワークフロー YAML のパースと全 12 run ブロックの `bash -n` を Git for Windows の bash で GREEN 確認（`shutil.which("bash")` は WSL の bash を拾って Windows パスを解決できず全ブロックが偽陽性で落ちるため、既存テストと同じく Git for Windows の bash を明示指定した）。`hve-dev/generate_tdd_inventory.py` を再実行し、索引整合の `test_hve_surface_inventory.py` / `cq/tests/test_surface_export.py` で **163 passed**。

<!-- validation-confirmed -->

### Fixed — `WorkflowDef.max_parallel` の宣言値が実行へ一切反映されていなかった問題を修正した（FR-DAG-03 改訂）

FR-DAG-03 はワークフローごとの並列上限（AKM / ADI = 21、ARD = 15、ASDW-WEB = 1）を規定していたが、`run_workflow` は `SDKConfig.max_parallel`（`--max-parallel`、既定 15）だけを `build_dag_plan()` へ渡しており、`DAGExecutor` は `dag_plan` がある限り `DAGPlan.max_parallel` で semaphore を作るため、宣言値は本番経路で一切使われていなかった。

- **実害（実測）**: ASDW-WEB は宣言 `1`（「同一 worktree の true parallel を避けるため逐次実行に固定する」[hve/workflow_registry.py](hve/workflow_registry.py) のコメント）に対して semaphore が 15 で、wave サイズ `[1,2,2,1,1,1,1,1,1,1,2,1,1,1,1,2,1]` のうち **2 ステップの wave 4 箇所が並列実行されていた**。AKM / ADI は宣言 `21` に対し semaphore 15 で D01〜D21 の fan-out が分割されていた。
- **解決順序を単一実装へ集約した**。[hve/orchestrator.py](hve/orchestrator.py) に `_resolve_max_parallel()` を追加し、(1) ARD bridge mode → `1`、(2) `WorkflowDef.max_parallel` の宣言がある → その宣言値、(3) それ以外 → `SDKConfig.max_parallel` の順で解決する。解決根拠は既存の `DAGPlan.max_parallel_source` へ `ard-serial` / `workflow` / `config` として保持する（新しいフィールドは追加していない）。
- **宣言を持つ 4 ワークフローでは `--max-parallel` が効かなくなる**（ard / akm / adi / asdw-web）。ASDW-WEB の `1` は安全制約で利用者が緩めてよい値ではなく、AKM / ADI の `21` は fan-out が設計上その並列度で動くことを表すため。宣言を持たない 9 ワークフローでは従来どおり有効。
- **argparse の `--max-parallel` を `default=None` へ変えて「明示指定のときだけ宣言値を上書き」とする案は採らなかった**。CLI 対話ウィザードは常に整数を `SDKConfig` へ設定するため明示・既定を区別できず、`SDKConfig.max_parallel` を `Optional[int]` へ変えると GUI 設定ストア・オプションパリティ・既存テストへ波及する。FR-DAG-03 と NFR-PERF-01 のいずれも宣言値の上書きを認めていない。
- **ドキュメントを実測に合わせて修正した**。[users-guide/workflow-reference.md](users-guide/workflow-reference.md) は「`max_parallel` はワークフロー単位で上書きされます」と記載していたが実際には上書きされておらず、本修正によって記載と実装が一致した。解決順序を 3 段階で明示した。

**影響範囲**: CLI / GUI の `orchestrate` 実行における DAG の並列上限のみ。ASDW-WEB は従来より遅く（しかし宣言どおり直列に）、AKM / ADI は fan-out が 1 波で完了するため速くなる。設定キー・CLI 引数・環境変数・出力パスの追加や削除はない。

**検証**: 新規 RED （[hve/tests/test_workflow_max_parallel_resolution.py](hve/tests/test_workflow_max_parallel_resolution.py)）を実装前 **7 failed / 3 passed**、実装後 **10 passed + 32 subtests** で確認した。`test_orchestrator.py` / `test_dag_planner.py` / `test_dag_executor.py` / `test_fanout.py` / `test_workflow_registry.py` / `test_asdw_web_production_path.py` / `test_agentic_retrieval_step_skip.py` で **549 passed + 117 subtests**。`hve/tests` 全体で **7951 passed / 10 failed**。失敗 10 件のうち 9 件は `git worktree` で切り出した HEAD でも同一に再現する既存の失敗で、残り 1 件は本変更後に未再生成だった索引の stale 検出（`test_csv_is_not_stale`）で、再生成で解消した。

<!-- validation-confirmed -->

### Changed — QA 回答から起動する Knowledge Management のバックグラウンド実行を、安全に並列化できる範囲で並列化した（FR-QA-03 改訂）

実行前 QA を有効にし、さらにバックグラウンドマージを明示的に有効化すると、回答済み QA 1 件ごとに Knowledge Management (AKM) の子実行が登録され、これまでは登録件数分だけ逐次に子プロセスが起動していた。親 DAG は完了を待たないが、Git 後処理・branch 切替・GUI cleanup・DAG 完了の各境界では `drain()` で待ち合わせるため、QA 回答が増えるほど親 Workflow の実待ち時間が延びていた。安全に並列化できる 2 つの軸だけを並列化した。

- **実行開始時点でキューに滞留している登録を 1 回の AKM 子実行へまとめるようにした**。`--target-files` へ当該バッチの全ファイルを FIFO 順で渡し、`drain()` の結果は従来どおり登録件数分（ファイル単位）で返す。バッチが失敗した場合は同じ returncode をバッチ内の全ファイルへ記録する。まとめられた QA は AKM 内部の D01〜D21 fan-out で同時に処理されるため、回答件数が増えても子実行の回数は増えない。
- **AKM 子実行が AKM の宣言並列上限（`21`）で走るようにした**。従来は子が `SDKConfig.max_parallel` の既定 `15` で動き、D01〜D21 の 21 fan-out が 15 件 + 6 件へ分割されていた。当初は [hve/qa_akm_dispatch.py](hve/qa_akm_dispatch.py) `QaAkmCoordinator._build_argv` で `--max-parallel 21` を明示付与したが、同じ Unreleased で行った FR-DAG-03 改訂により宣言値が `SDKConfig.max_parallel` より優先されるようになったため、当該付与は効果を持たないデッドコードとなり FR-MAINT-07（同一ルールの二重実装禁止）に従って削除した。子 argv が並列度を固定しないことを回帰テストで固定している。
- **AKM 子プロセスの多重起動は採用しなかった**。AKM の出力空間は `target_files` の指定によらず `knowledge/D01`〜`D21` 全体と `knowledge/business-requirement-document-status.md` を含むため（[.github/scripts/templates/akm/step-1.md](.github/scripts/templates/akm/step-1.md) の `## 出力`）、子プロセスを同時に走らせると FR-QA-03 が防ごうとしている「共有 `knowledge/` への同時書込みと差分喪失」そのものが起きる。同時に起動する子プロセスが 1 つを超えないことを契約テストで固定した。
- **新しい CLI / GUI / Issue Form オプションは追加していない**。`SDKConfig` のフィールドも増えていないため、`hve/tests/fixtures/option_parity_matrix.yaml` への登録は不要である。Cloud（GitHub Actions）経路は `akm-knowledge-write-<repo>` の concurrency で直列化しており（FR-CLOUD-21）、同じ `knowledge/` 競合が理由のため本変更の対象外とした。
- **`users-guide/workflow-reference.md` の `max_parallel` 記述を実測に合わせて是正した**。「ワークフロー単位で上書きされます」と書かれていたが、`run_workflow` は常に `dag_plan` を渡すため `DAGExecutor` の semaphore は `dag_plan.max_parallel`（= `config.max_parallel`）で決まる（実測: AKM の宣言値 21 に対して semaphore は 15）。宣言値と実行時上限の関係、および ARD bridge mode と QA 起点 AKM 子実行という 2 つの例外を明記した。この上書き順序自体は ADI / ASDW-WEB へも波及する全面的な挙動変更になるため、本変更では触れていない。

**影響範囲**: CLI / GUI の QA 起点 Knowledge Management バックグラウンド実行のみ。`--workflow akm` の明示実行、Cloud 経路、`qa/` 生成物、`knowledge/` の出力形式は変更していない。設定キー・CLI 引数・環境変数・出力パスの追加や削除はない。

**敵対的レビューで是正した点**: (1) FR-QA-03 の登録単位 `target_files=<当該ファイル>` とバッチ実行時の `target_files` が直接衝突して読めたため、登録単位の値であることを明記した。(2) `users-guide/workflow-reference.md` に書こうとした「実際の並列上限は `--max-parallel` が決める」を実測で検証し、ARD bridge mode が実行時に `1` へ落とす例外を反映した。(3) `hve-cli-orchestrator-guide.md` の「fan-out が 1 wave に収まります」は元から 1 wave（21 ステップ）であり誤りだったため、「21 件が同時に実行される」へ訂正した。(4) `QaAkmCoordinator` の class docstring がバッチ化を反映しておらず、面横断の再利用探索（`hve-surface-inventory.csv` の `behavior_summary`）で実挙動に到達できなくなるため 1 行追記した。

**検証**: 新規 RED を 2 ファイル（[hve/tests/test_qa_akm_child_parallelism.py](hve/tests/test_qa_akm_child_parallelism.py) / [hve/tests/test_qa_akm_batching.py](hve/tests/test_qa_akm_batching.py)）で作成し、実装前 **9 failed / 5 passed**、実装後 **11 passed + 3 subtests** を確認した。`TestQaAkmBackgroundCoordinator` の既存 4 テストは「submit 件数 = 子プロセス数」を前提としており、バッチ化後は fake process が即完了する場合にだけ通る状態になっていた（実測: 25 回連続では失敗を観測せず）。契約が保証しない前提のため決定論的な形へ書き換え、書き換え後は QA 起点 AKM 関連 51 tests + 9 subtests を **15 回連続で全 GREEN** で確認した。広域では `test_orchestrator.py` / `test_runner_pre_qa.py` / `test_fanout.py` / `test_workflow_registry.py` / `test_qa_akm_*.py` の **520 passed + 94 subtests**、`test_phase6_option_parity.py` / `test_main.py` の **308 passed + 234 subtests**、索引整合の `test_hve_surface_inventory.py` / `cq/tests/test_surface_export.py` の **163 passed** が GREEN。`TestRunWorkflowFanout::test_aad_web_fanout_meta_is_forwarded_to_step_runner` の失敗は `git worktree` で切り出した HEAD でも同一に再現するため既存の失敗であり、本変更とは無関係である。`hve/gui/tests/test_qa_ipc_flow.py` は初回に Windows の `QFileSystemWatcher` がハンドルを保持したことによる `os.replace` の `PermissionError` で 1 件失敗したが、再実行で **3 passed** となる flaky であり、本変更が触れていない `hve/runner.py` の `_atomic_write` 経路である。`hve-dev/generate_tdd_inventory.py` を再実行して 3 つの索引 CSV を更新した。

<!-- validation-confirmed -->

### Fixed — Work IQ MCP のツール名不一致で Work IQ が実質無効だった問題を修正した

HVE が固定していた Work IQ MCP の allowlist は `ask_work_iq` だったが、`@microsoft/workiq`（実測 1.0.0.28144）が実際に公開する問い合わせツール名は `ask` であり、`ask_work_iq` というツールは存在しなかった。このため MCP サーバーは `connected` になる一方で Work IQ のツールが 1 つもモデルへ公開されず、LLM は `STATUS: UNAVAILABLE`（「ツールが公開されていない」）を返していた。さらにイベント判定側も `_hve_workiq` × `ask_work_iq` の組だけを許可していたため、仮にツールが呼ばれても FR-QA-03 の統合条件（tool 実行確認 + `FOUND` / `PARTIAL`）を満たせない二重の不整合になっていた。

- **allowlist を実ツール名 `ask` へ修正した**（`hve/workiq.py` の `WORKIQ_MCP_TOOL_NAMES`）。`build_workiq_mcp_config()` が生成する `tools` もこれに追随する。`@microsoft/workiq` は `ask` 以外に `fetch` / `get_schema` などの参照系と `create_entity` / `update_entity` / `delete_entity` / `do_action` などの書き込み系も公開するが、HVE が使うのは自然言語問い合わせの 1 経路だけのため、最小権限として `ask` のみを許可する方針は維持した。
- **server 名を持たない tool event を Work IQ として扱わないようにした**（`_is_workiq_tool_metadata`）。MCP 由来の tool event は必ず `mcp_server_name` を伴うことを実測で確認しており、従来の legacy フォールバックは実在しないツール名のためのもので一度も成立し得なかった。`ask` は 3 文字の一般語であり、server 名なしで許可すると別 server の同名ツールを誤検知するため、組での判定に一本化した。
- **`_WORKIQ_DATA_INDICATORS` から実在しない `ask_work_iq` を除去した**。応答本文にツール名が現れることを「実データあり」の指標として使う設計だったが、対象の名前が存在しないため指標として機能していなかった。
- **`run_workiq_event_extractor_self_test()` の自己診断ケースを実仕様へ更新した**。`workiq-doctor --event-extractor-self-test` が現行の判定と一致することを検証する。
- **users-guide の 2 つの誤記を訂正した**。(1) 許可ツール一覧と `--sdk-tool-probe` の説明に書かれていた `ask_work_iq` を `ask` へ修正した。(2)「`--workiq-draft` を指定しない場合は一括問い合わせとして `qa/{run_id}-{step_id}-workiq-qa.md` に保存される」という記述は実装に存在しない挙動だった。事前 QA の Work IQ 問い合わせは常に質問ごとに実行され、常に `qa/{run_id}-{step_id}-workiq-pre-qa-draft.md` へ保存される（`hve/runner.py` の保存呼び出しは `pre-qa-draft` 固定で、`workiq_draft_mode` は `runner.py` から参照されていない）。対象質問数の上限は環境変数 `WORKIQ_MAX_DRAFT_QUESTIONS`（既定 10）である。

**影響範囲**: CLI / GUI 共通の Work IQ 連携（事前 QA、AKM 取り込み / 検証、ARD ユースケース参照、`workiq-doctor`）。設定キー・CLI 引数・環境変数・出力パスの追加や削除はない。既存の `qa/` 生成物と生成アプリの成果物は変更していない。

**検証**: 修正前は既定設定の実機実行で MCP ツール呼び出しが **0 回**・`STATUS: UNAVAILABLE` だったが、修正後は同じ既定設定で `_hve_workiq::ask` の呼び出しを観測し、HVE 側の Work IQ 判定も `['ask']` と非空になり `STATUS: FOUND` を取得した。`python -m hve workiq-doctor --sdk-probe --sdk-tool-probe --event-extractor-self-test` は **22 PASS / 0 FAIL / 0 WARN / 1 SKIP** で総合判定「全チェック成功」となった（修正前は `copilot_tool_invocation` が FAIL）。`hve/tests/test_workiq.py` / `test_runner.py` / `test_runner_pre_qa.py` / `test_orchestrator.py` で **594 passed + 99 subtests**。同時に失敗した `TestRunWorkflowFanout::test_aad_web_fanout_meta_is_forwarded_to_step_runner` は AAD-WEB Step 2.2 の fan-out に関するもので、本変更が触れていない `hve/workflow_registry.py` に起因する別事象である。`hve-dev/generate_tdd_inventory.py` を再実行して索引を更新し、2 回連続実行で出力が一致すること（決定性）も確認した。

<!-- validation-confirmed -->

### Fixed — README と users-guide の導線欠落・一覧の陳腐化を解消し、ルート README の変更禁止規定を実態に合わせた

ルート `README.md` から `users-guide/` への到達性を調査したところ、36 件中 10 件がどこからもリンクされておらず、うち 2 件はリポジトリ全体からも参照されていなかった。あわせて README と `users-guide/workflow-reference.md` の一覧・件数記載が実装と食い違っていた。ドキュメントの構造は変えず、リンクと一覧の中身だけを実装照合のうえ修正した。また、CI で既に解除済みだった「ルート README.md 変更禁止」の規範文を実態に合わせた。

- **README から到達できなかった 10 件をすべてリンクした**（26 / 36 → **36 / 36**）。`09-agent-data-architecture.md` / `10-agent-evaluation.md` / `11-agent-m365-publish.md` / `agentic-retrieval-guide.md` はフェーズ別ガイド表へ、`setup-self-hosted-runner.md` / `local-cicd-enablement.md` / `cloud-session.md` / `plugin-mcp-auth.md` / `setup-playwright-mcp.md` / `pricing-guide.md` は新設した「セットアップ・運用オプション」表へ追加した。`tool-search-guide.md` はコードスパンのままリンクになっていなかったため Markdown リンクへ変更した。
- **Workflow ID 表に `ada` を追加し「12 個」→「13 個」に修正した**。`hve/workflow_registry.py` には `WorkflowDef` が 13 個登録されており、`WORKFLOW_CATEGORIES` でも `ada` は "AI Agent" カテゴリに含まれていたが、README の表にだけ載っていなかった。これが `09-agent-data-architecture.md` が到達不能だった直接の原因である。
- **Issue Template 一覧に 2 件を追加し「10 個」→「12 個」に修正した**。`agent-data-architecture.yml` と `agentic-retrieval.yml` が実在するのに未掲載だった。UI 名は各 YAML の `name` と一致することを機械照合した。
- **Reusable orchestrator 一覧に 2 件を追加した**。`auto-agent-data-architecture-reusable.yml` / `auto-agentic-retrieval-reusable.yml` は `auto-orchestrator-dispatcher.yml` から `uses:` で起動されているのに未掲載だった。掲載 12 件が dispatcher の `uses:` 集合と完全一致することを確認した。
- **users-guide 内の孤立と片方向リンクを解消した**。どこからも参照されていなかった `setup-playwright-mcp.md` と `pricing-guide.md` に相互リンクを追加し、孤立ファイルを 0 にした。あわせて `02 → 01`、`04 → 02`、`10 ↔ 11`、`08 → tool-search-guide`、`skills-*-query → tool-search`、`hve-cli-orchestrator-guide → hve-cli-getting-started / web-ui-guide`、`web-ui-guide → hve-gui-orchestrator-guide` の戻りリンクを追加した。
- **`← [README](../README.md)` の戻りリンクを 36 / 36 に統一した**（従来 24 / 36）。`03` / `05` は既存の前後ナビゲーション行の先頭へ追記し、既存表記は壊していない。
- **`users-guide/workflow-reference.md` の 3 つの一覧を実体に追従させた**。「Issue テンプレート一覧」は「全テンプレート」と謳っていながら 10 / 12 件しかなく、`agent-data-architecture.yml` / `agentic-retrieval.yml` が欠けていた。「ワークフロー一覧」には `auto-agent-data-architecture-reusable.yml` が、「Workflow ID × 実行経路」表には `ada` が欠けていた。README がこのページを「全項目の参照先」としてリンクしているため、README 側だけ直すと下流が古いままになる。
- **README の GitHub Actions workflow 一覧を棚卸しした**。実在 57 件のうち 11 件が未掲載だったため、trigger 実測値に基づいて分類して追加した（PR / Issue automation 4 件、Validation 3 件、Scheduled 2 件、新設した Reusable helper 2 件）。逆に `copilot-setup-steps.yml` / `scheduled-drift-detection.yml` / `scheduled-health-check.yml` / `validate-agents.yml` の 4 件は実在しないため一覧から削除した（`integration-tests-sample.yml` は不在であることを README 本文で明記済みのため維持）。
- **「ルート README.md 変更禁止」の規範文を実態に合わせた**。`.github/workflows/protect-readonly-paths.yml` の `check-readme` ジョブは 2026-05-05 に解除済みであり、`README.md` は `ROOT_FILE_ALLOWLIST` にも掲載されているのに、`.github/copilot-instructions.md` §0 だけが禁止を謳い続けていた。「ルート README.md の扱い」へ改め、導線インデックスとして一覧を同期する責任を明記した。Self-Improve ループの改善適用 Prompt（`hve/prompts.py`）が `/README.md` を変更しない制限は意図的に維持し、その旨を規範文と `protect-readonly-paths.yml` のヘッダーコメントに明記した。

**検証**: リンク検証スクリプトで README + `users-guide/*.md` の 37 ファイル、相対リンクとアンカー（`<a id="...">` 含む）の解決失敗 **0 件**。README からの未リンク **0 件**、users-guide 内の孤立・被リンク 0 件のファイルとも **0 件**。`workflow-reference.md` の 3 一覧は実体と完全一致（workflow 57 / 57、Workflow ID 13 / 13、Issue Template 12 / 12 で `name` ・ `labels` も機械照合）。README の workflow 一覧も実在 57 件を全掲載。`check-auto-qa-skip-reusable.yml` の呼び出し元 9 件は `uses:` 行を実測して確認した。`protect-readonly-paths.yml` は YAML としてパースでき、ジョブ構成（`check-readme` / `check-docs-original` / `check-root-temp-files`）は変わらない。pytest は `test_tool_search_guide_contract` / `test_toolsearch_dashboard` / `test_gui_help_content` / `test_aas_persona_step_numbering_contract` / `test_hve_surface_inventory` で **245 passed**、`.github/copilot-instructions.md` を読む契約テスト群で **409 passed**。変更はリンク行・一覧行・件数表記・規範文 1 行に限定し、他の本文の意味を変える編集は行っていない。

<!-- validation-confirmed -->

### Fixed — AG-CAP-09 / AG-CAP-10 配線の敵対的レビュー指摘を修正した

追加した Step と検証器を敵対的レビューにかけ、実測で裏付けた欠陥を修正した。

- **日本語の否定語で `mcp.json` が必須と誤判定される問題を直した**。`_normalize_ai_agent_label` は `[^a-z0-9]+` を除去するため、`Plugin components: mcp.json: 不要` は `mcpjson` へ正規化され、否定語による除外が効かず **採用と誤判定**されていた（実測確認）。判定を **`mcp.json: required` / `mcp.json: yes` という閉じた肯定語彙が明示されたときだけ採用**へ改め、既定を not-required とした。あわせて `capability-contract.md` / 実装 Prompt / users-guide に「英語の定型語で書く」ことを明記した。従来の否定語トークン 4 種のうち 3 種は他のトークンの部分文字列で死にコードだったため、この変更で解消した。
- **未定義の要件 ID 参照を削除した**。`FR-WF-AAGD-07` は既存要件（SKILL.md frontmatter の長さ制約）と衝突し、`FR-WF-AAGD-08` / `09` および `FR-WF-ADA-01〜07` は `hve-dev/requirement-definition.md` に定義が無かった。`CHANGELOG.md` と `hve-dev/requirement-test-mapping.md` から該当 ID を除去し、説明的なラベルへ置き換えた。
- **存在しない成果物パスの参照を削除した**。`Dev-Agent-M365Publish.prompt.md` が推奨入力に挙げていた `docs/agent/agent-deploy-report.md` は AAGD Step 3 の成果物ではない（テストの合成 fixture 値だった）。実在する `src/infra/azure/README-agent-deploy.md` へ差し替えた。
- **`mcp.json` の URL 検証を堅牢化した**。不正な IPv6 URL（`https://[::1/mcp`）で `urlparse` が `ValueError` を送出しゲート外へ伝播していたため捕捉してエラー行へ変換し、ホストが空の URL（`https:///mcp`）を拒否するようにした。いずれも実測で再現を確認している。
- **リモート transport で `env` を拒否するようにした**。Prompt と users-guide は「リモートは `url` / `headers` のみ」と書いていたが検証器は `env` を許しており、記述と実装が乖離していた。
- **`mcp.json` 本文へ既存の secret 検出を適用した**。従来はキー名の一致だけを見ており、`X-Custom` のような無害なキーに値としてトークンを書く経路を単体検証で拾えなかった。
- **到達不能だった分岐とメッセージを整理した**。ヘッダー行だけの表は `_find_ai_agent_table` が `None` を返すため、`validate_m365_publish_report` の「1 行以上必要」分岐は永久に実行されなかった。列と行の両方に言及するメッセージへ統合した。
- **`Conclusion` の語彙を表の判定と揃えた**。検証器は自由文を許す一方、users-guide とテンプレートは 4 値を示唆しており契約が二重だった。検索経路の適正化レポートでは `Conclusion` も 4 値固定として検証する。
- **未使用の共有状態と過剰な間接化を除去した**。`metadata["m365_publish_selected"]` は他のどのコードからも参照されないためローカル変数へ降格し、runner ゲートの「validator 名の文字列 + `getattr`」による 2 分岐の動的解決を直接 import へ単純化した。
- **AAGD Step 6 の ADA 専用成果物依存を緩和した**。`docs/catalog/unstructured-data-catalog.md` を必須にすると AAS→AAG→AAGD 経路では永久に満たせないため、比較候補の参考入力（任意）へ変更した。
- **Cloud の Issue Template を実態に合わせた**。`ai-agent-dev.yml` は説明・チェックボックスとも Step.4 止まりで、Step.5/6/7 を skip 指定できず reusable 側の skip 分岐が到達不能だった。Step.5/6/7 の行を追加し、重複していた Step.3 の行を除去した。
- **users-guide の記述漏れを補った**。`08-ai-agent.md` の AAGD 鎖の説明（Step 4 止まり）を Step 7 まで更新し、新設ガイド 09 / 10 / 11 への相互リンクを追加した（索引はルート `README.md` にあり編集禁止のため）。`workflow-reference.md` の抽出日も更新した。
- **未検証だった経路にテストを追加した**。`_validate_ai_agent_distribution` の非 N/A 経路はテストがゼロで、上記の誤判定を見逃していた。設計文字列から `mcp_config_required` を判定する契約テストと、URL 例外・空ホスト・remote の `env`・値側 secret の回帰テストを追加した。

**検証**: `.github/scripts/validate-io-contract.py` が 149 Agent に対しエラー 0 件。契約系 3 ファイルで 90 passed / 21 subtests passed。`-k "agent or capability or contract or aagd or aag or workflow or cloud or skill or option_parity"` の横断実行で 3040 passed / 496 subtests passed。`ai-agent-dev.yml` の steps 選択肢が 7 件で重複なし、`auto-ai-agent-dev-reusable.yml` の全 8 run ブロックが `bash -n` を通過。指摘 1・11・12 と「ヘッダーのみの表は `None` を返す」ことは、修正前に一時スクリプトで実測して再現を確認した。残存する 5 件の失敗は本変更が触れていないファイルに起因する既存の失敗である。

<!-- validation-confirmed -->

### Added — AG-CAP-09 / AG-CAP-10 を実行する Step と成果物ゲートを追加した

AG-CAP-07〜10 を契約として定義し、設計書の見出しゲートまでは反映していたが、**契約が要求する実行が誰の責務にもなっていなかった**。具体的には次の 3 点が欠けていた。

1. **Agent を MCP として公開する経路が禁止のままだった**。[.github/prompts/Dev-Microservice-Azure-AgentCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-AgentCoding.prompt.md) は「`mcp.json` は作らない」と固定していたため、AG-CAP-09 が `Plugin components` で `mcp.json` を採る設計を選んでも、実装 Step がそれを生成できなかった。
2. **選んだ検索経路が過剰かどうかを実測する Step が無かった**。Step 5（要件適合実測）は「デプロイした構成が目標を満たすか」を測るが、「より安い経路でも足りたのではないか」は比較実測でしか判定できない。AG-CAP-10 が「候補経路を 2 段以上実測しない評価は受理しない」と定めていても、実行する Step が存在しなかった。
3. **Microsoft 365 / Teams へ公開する Step が無かった**。Foundry へデプロイしただけでは利用者のチャットクライアントから呼べず、AG-CAP-09 が防ごうとしている「実装したが呼び出せない」状態がそのまま残っていた。

- **`mcp.json` の条件付き生成と検証を追加した**。実装 Prompt を「作らない」から「詳細設計 Section 7.8 の `Plugin components` が要としたときだけ作る」へ改め、[hve/artifact_validation.py](hve/artifact_validation.py) に `validate_agent_plugin_mcp_config` を追加して `validate_ai_agent_implementation_artifacts` から呼ぶようにした。Agent Plugins Specification 1.0.0 §7.2 に基づき、top-level の closed schema（`$schema` / `mcpServers` のみ）、`$schema` の版一致、transport 3 値（`stdio` / `streamable-http` / `sse`）、stdio と remote のフィールド排他、**非 loopback の HTTPS 必須**、user-info と fragment の禁止、`headers` / `env` への資格情報埋め込み禁止、予約変数 `PLUGIN_ROOT` / `PLUGIN_DATA` の再定義禁止を検証する。**設計が採用していないのにファイルが存在する場合もエラー**にし、意図しない公開設定の同梱を防ぐ。
- **AG-CAP-09 の設計側パースを追加した**。`_validate_ai_agent_distribution` が `Channels` / `Plugin manifest` / `Plugin components` / `Metadata visibility` / `Decision source` の必須ラベルを検証し、`mcp.json` の要否を metadata へ残す。**採用の判定は `mcp.json: required` / `mcp.json: yes` という閉じた肯定語彙のみ**とし、それ以外は採用しないとして扱う。ラベル正規化は非 ASCII を落とすため、日本語の「不要」を否定語として検出できないことを実測で確認したためである。理由付き N/A は既存の `_reasoned_ai_agent_na` を再利用し、新しい N/A 判定器を作っていない。
- **AAGD Step.6「検索経路の適正化実測」を新設した**（`QA-AgentRouteRightsizingEval`）。`references/search-routing.md` §4.1 のコスト階段から**採用段とそれより安い段の計 2 段以上**を、同一の評価データセットで実測する。判定語彙は `KEEP` / `DOWNGRADE` / `INSUFFICIENT` / `NOT_MEASURED` の 4 値固定で、**比較表が 1 行のレポートは gate が拒否**する。1 段だけの測定を「適正」と結論する経路を塞ぐことが本 Step の中核である。`KEEP` / `DOWNGRADE` は正答率・トークン・応答時間の 3 指標が揃った行にしか使えない。
- **AAGD Step.7「Microsoft 365 / Teams 公開」を新設した**（`Dev-Agent-M365Publish`）。判定語彙は `PUBLISHED` / `PENDING_APPROVAL` / `NOT_SELECTED` / `FAILED` の 4 値固定。**設計が当該チャネルを採っていない場合も Step 自体は実行され**、採らなかった理由と再判定条件をレポートへ残す（`NOT_SELECTED`）。「公開しない」という判断を無記録にしないためである。`PUBLISHED` / `PENDING_APPROVAL` には App Version を必須とし、版の再利用を防ぐ。公開メタデータは利用者に見えるため、レポート本文にも既存の secret 検出を適用する。
- **両 Step の依存を Step 4 ではなく Step 3 に置いた**。Step 4（tool search 実測評価）は `enable_tool_search=no` のとき実行対象から外れるため、依存先にすると到達できなくなる。既存 Step 5 と同じ判断である。
- **fan-out しない設計にした**。検索経路の適正化も配布もアプリケーション単位の判定であり、要素単位に割ると同じ比較を要素数分だけ measurement し直すことになる。
- **runner の成果物ゲートを追加した**。[hve/runner.py](hve/runner.py) の `_run_agent_capability_report_gate` が `(Agent, workflow, step)` の 3 つ組で対象を引き、`validate_route_rightsizing_report` / `validate_m365_publish_report` を Step 完了時に呼ぶ。Agent 名を鍵に含めたため、他 workflow へ同名 Step を足しても誤発火しない。
- **AG-CAP-07 / 08 / 10 の実装境界を実装 Prompt へ追加した**。AG-CAP-07 は `attended` を選んだ場合に利用者 identity を下流へ伝播し、伝播できないときに application 権限へ置き換えず blocked にすること。AG-CAP-08 は 4 種の span を出し、**span 属性へ query 本文・response 本文・access token・raw URL を入れない**こと。AG-CAP-10 は本 Step では評価せず、評価に必要な計測点を span へ残すことだけを担う。
- **Cloud 面を同期した**。[.github/scripts/bash/lib/workflow-registry.sh](.github/scripts/bash/lib/workflow-registry.sh) と [.github/workflows/auto-ai-agent-dev-reusable.yml](.github/workflows/auto-ai-agent-dev-reusable.yml) へ Step.6 / Step.7 の Issue 生成・紐付け・状態遷移（Step.5 → 6 → 7）を追加した。
- **users-guide を追加した**。[users-guide/10-agent-evaluation.md](users-guide/10-agent-evaluation.md)（Step.5 との違い・コスト階段・レポートの読み方）と [users-guide/11-agent-m365-publish.md](users-guide/11-agent-m365-publish.md)（2 つの配布チャネル・`mcp.json` の制約・公開時の禁止事項）を新設し、[users-guide/workflow-reference.md](users-guide/workflow-reference.md) の Step 一覧へ ADA と AAGD Step.6 / 7 を反映した。

**既知の境界**: 本変更は Step の配線とレポートの機械検証までを対象とする。実際の Microsoft 365 公開 API 呼び出し・Bot Service リソース定義・評価データセットの自動生成は含まない。`mcp.json` は条件付き成果物のため `StepDef.output_paths_template` と io-contract の `outputs` には宣言していない（宣言すると未採用時に完了ゲートが落ちる）。`skills/` と設定ファイルと同じ扱いで、`src/agent/{key}/` に包含される。Cloud 経路は GitHub Actions 構文と registry parity をローカル検証したのみで、実 Issue を作成する live run は実施していない。

**検証**: `.github/scripts/validate-io-contract.py` が 149 Agent に対し schema / integrity / registry mismatch すべて 0 件。新規 2 ファイルで 54 passed / 18 subtests passed（`mcp.json` 検証 23 件、Step.6 / 7 契約 31 件）。`auto-ai-agent-dev-reusable.yml` の全 8 run ブロックが `bash -n` を通過。`-k "agent or capability or contract or aagd or aag or workflow or cloud or skill"` の横断実行で 2977 passed。実装前の RED を実測確認したのは Step 数 7→9 の期待値不一致と、Prompt 契約テストの旧契約 assertion の 2 件である。残存する 5 件の失敗（`test_asdw_data_azure_cli_scope_contract` 2 件 / `test_asdw_web_step_scoped_cicd_contract` / `test_dev_task_environment_contract` / `test_orchestrator.py::test_aad_web_fanout_meta_is_forwarded_to_step_runner`）は、いずれも本変更が触れていないファイルに起因する既存の失敗である。

<!-- validation-confirmed -->

### Added — 画面を持たないデータ中心 AI Agent 向けの ADA ワークフローを新設し、AG-CAP-07〜10 を消費側へ反映した

チャットアプリや API から呼ばれる AI Agent には画面が無い。それにもかかわらず、AAG / AAGD の前段として使えるアーキテクチャ設計ワークフローは AAS しか無く、AAS は画面カタログ・画面設計・画面×サービスのマトリクスを必須成果物として持つ。結果として、画面を作らない案件でも画面設計 Step を通すか、AAG の必須入力を欠いたまま実行するかの二択になっていた。

- **`ADA`（Agent Data Architecture）ワークフローを新設した**。`ARD → ADA → AAG → AAGD` のチェーンで AAS を置き換える。Step は 10 個（`1` / `2` / `3` / `4.1` / `4.2` / `5` / `6` / `7` / `8` / `9`）で、うち 9 個は AAS と同じ Custom Agent を再利用し、新規 Agent は Step 8 の `Arch-AgentDataAsset` のみとした。
- **AAS から 3 系統の Step を除外した**。画面カタログ・画面設計（画面が存在しない）、サービスカタログマトリクス（画面×サービスの交差が存在しない）、Azure サービス選定（AAGD の Deploy 側で決定する）。除外理由は [hve/workflow_registry.py](hve/workflow_registry.py) の ADA 定義ヘッダーコメントに根拠付きで残した。
- **`Arch-AgentDataAsset`（Step 8）を新設した**。非構造化データ資産を `UDA-NNN` で採番し、形式・所在・件数・更新頻度・機密度・権限モデル・関連エンティティ・利用 APP・出典を記録する。**各資産に対して `ai-agent-capability-contract` の検索経路コスト階段から 2 段以上の候補を挙げ、除外した経路とその理由を残すこと**を必須とした。高い推論量を伴う検索手法が過剰かどうかを、AAG の設計以前に判定できるようにするため。
- **AAG / AAGD の必須入力を付け替えた**。画面カタログ・画面設計・サービスカタログマトリクス・Azure サービス選定書の 5 パスを **任意入力へ緩和**し、代わりに ADA が生成する `docs/catalog/data-catalog.md` / `docs/catalog/persona-catalog.md` / `docs/catalog/unstructured-data-catalog.md` を必須入力へ加えた。これにより AAS 経由・ADA 経由のどちらでも AAG / AAGD が実行できる。対象は AAG 3 Step と AAGD 5 Step の計 8 io-contract。
- **CLI / GUI / Cloud の 3 面へ登録した**。CLI と GUI は `hve/template_engine.py` / `hve/gui/help_content.py` / `hve/gui/page_workflow_select.py` / `hve/gui/page_options.py` / `hve/gui/workflow_step_requirements.py` / `hve/autopilot/plan_review_gap.py` / `hve/skill_manifest.json`、Cloud は新規 `.github/workflows/auto-agent-data-architecture-reusable.yml`・`.github/scripts/bash/lib/workflow-registry.sh`・`auto-orchestrator-dispatcher.yml`・`.github/labels.json`・新規 Issue Template `.github/ISSUE_TEMPLATE/agent-data-architecture.yml`。
- **Cloud の次 Step 解決を順序リスト方式にした**。ADA は `4.1` / `4.2` の小数 Step ID を持つため、既存 workflow が使う `$((STEP + 1))` 方式では `4.1` の次が解決できない。`order = ['1','2','3','4.1','4.2','5','6','7','8','9']` の順序リストで次 Step を引く方式へ変更し、`$((STEP + 1))` を使わないことを契約テストで固定した。
- **AG-CAP-07〜10 を契約の消費側へ反映した**。[hve/artifact_validation.py](hve/artifact_validation.py) の `_AI_AGENT_CONTRACT_HEADINGS` へ 4 契約を追加し、AAG Step 3 の設計書生成契約（`7.6`〜`7.9` の固定見出し・見出しレベル・N/A 不可の指定）、AAGD のテスト仕様 / テストコード / 実装 Prompt、テンプレート、Skill 間の相互参照、users-guide の範囲表記を `AG-CAP-01〜10` へ揃えた。これにより AG-CAP-07 / 08 / 10 のセクション欠落が Step 完了時に検出される。
- **`users-guide/09-agent-data-architecture.md` を新設した**。[hve/gui/help_content.py](hve/gui/help_content.py) が参照するガイドの実体であり、AAS との差分表・Step 一覧・3 面の起動手順・後続ワークフローへの接続を記載した。

**既知の境界**: 本変更は ADA ワークフローの配線と AG-CAP-07〜10 の見出しゲートまでを対象とする。AG-CAP-09 が扱う `mcp.json` の生成と検証、AG-CAP-08 が扱う Observability 実装の成果物検証、AG-CAP-10 の評価 Step 追加、Microsoft 365 / Teams への公開 Step は本変更に含まれない。ADA の Cloud 経路は GitHub Actions 構文・registry parity・dispatcher routing をローカル検証したのみで、実 Issue を作成する live run は実施していない。

**検証**: `.github/scripts/validate-io-contract.py` が 147 Agent に対し schema / integrity / registry mismatch すべて 0 件。`.github/scripts/validate-skill-routing.py` が exit 0。`pytest hve/tests/test_ada_workflow.py hve/tests/test_workflow_registry.py` 245 passed、`test_ada_cloud_surface.py` + `test_cloud_dispatcher_asdw_dispatch.py` 63 passed（reusable workflow の全 run ブロックに対する `bash -n` 構文検査を含む）、`test_phase6_option_parity.py` + `test_ada_cloud_surface.py` 63 passed / 207 subtests passed、契約系 5 ファイル 106 passed。`-k "agent or capability or contract or aagd or aag"` の横断実行で 1996 passed。`hve-dev/generate_tdd_inventory.py` を再実行し inventory 3 種を再生成した。残存する 7 件の失敗（`test_agentic_retrieval_surface_parity.py` 3 件 / `test_asdw_data_azure_cli_scope_contract.py` 2 件 / `test_asdw_web_step_scoped_cicd_contract.py` / `test_dev_task_environment_contract.py`）は、いずれも本変更が触れていないファイルの未コミット差分（並行作業による AAGD Step.5 追加ほか）に起因することを `git diff` で確認した。

<!-- validation-confirmed -->

### Added — 生成物を実行して要件適合を測る Step を 4 ワークフローへ追加した（FR-WF-CONF-01〜06、FR-CLOUD-06 改訂 / FR-CLOUD-07 新規）

ASDW-WEB / ADFDV / AAGD / AAR の最終 Step は、いずれも設計文書と成果物の照合で完結していた。WAF レビューと整合性チェックは「設計が妥当か」を見るが、「デプロイした構成が実際に目標の応答時間・スループット・成功率を満たすか」は誰も測っていなかった。選んだ実行基盤が過剰かどうかも同様で、設計文書からは判定できない。

- **`QA-RequirementsConformanceEval` を新設し、4 ワークフローで共有した**。`QA-AzureArchitectureReview` が ASDW-WEB 5.1 と ADFDV 4.1 で共有されている既存の形をそのまま踏襲し、Agent・Prompt・Skill・validator をいずれも 1 実装に集約した。Step は `asdw-web:5.3`（依存 5.1, 5.2）/ `adfdv:4.3`（依存 4.1, 4.2）/ `aagd:5`（依存 3）/ `aar:7`（依存 6）で、既存 Step の ID・依存・成果物は変更していない。
- **AAGD の依存を Step 4 ではなく Step 3 に置いた**。Step 4（tool search 実測評価）は `enable_tool_search=no` のとき実行対象から外れるため、依存先にすると実測 Step へ到達できなくなる。
- **fan-out しない設計にした**。非機能要件はアプリケーション単位で判定する対象であり、要素単位に分けると同じ負荷条件を要素数分だけ測り直すことになる。
- **判定語彙を `PASS` / `FAIL` / `NOT_MEASURED` / `NO_TARGET` の 4 値へ固定した**。「目標が無い」と「測っていない」を別語彙に分けたのは、次サイクルで取るべき行動が異なるため（前者は目標の制定、後者は測定環境の整備）。実測値から目標値を逆算することは禁止した（Google SRE Book Ch.4 "Don't pick a target based on current performance"）。
- **本 Step のための Azure リソース新規作成の必須化を禁止した**。測定には各ワークフローが既に生成したテスト資産とデプロイ済みエンドポイントを使う。Azure Load Testing 等の利用は任意とした。Azure Well-Architected Framework PE:06 が、性能テスト専用のインフラと専門知識による運用コスト増をトレードオフとして明記し、後から問題を発見するコストと比較して判断するよう求めていることを根拠とした。
- **`Headroom` 列と `Simplification-Candidate` を導入した**。実運用 FaaS ワークロードの呼び出し頻度が 8 桁のレンジに広がるという公開研究（Shahrad ほか, USENIX ATC 2020）を踏まえ、構成が過剰かどうかは目標値と実測値の差でしか評価できないとした。本 Step は測定と報告までを責務とし、構成変更・再デプロイは行わない。
- **成果物ゲートを追加した**。[hve/artifact_validation.py](hve/artifact_validation.py) の `validate_requirements_conformance_report` が、必須ラベル 8 件・測定表・判定語彙・未測定理由・結論を検証し、[hve/runner.py](hve/runner.py) の `_run_requirements_conformance_gate` が Step 完了時に呼ぶ。既存の AI Agent 系ヘルパー（表解析・ラベル抽出）を再利用し、新しい解析器は作っていない。
- **Cloud 側の単一正本を整備した**。[.github/scripts/bash/lib/workflow-registry.sh](.github/scripts/bash/lib/workflow-registry.sh) へ未登録だった `asdw-web` と `aar` を追加し、`adfdv` / `aagd` へ新 Step を追加した。ASDW-WEB reusable を現行 26 Step と依存 DAG へ移行し、AAR 専用 reusable workflow・Issue Template・状態ラベルを追加した。dispatcher は同期済み ASDW-WEB と AAR を起動し、AAR は `enable_agentic_retrieval=no` の場合に Step Issue を生成しない。parity テストは ASDW-WEB / AAR を含む生成 Step ID・Custom Agent・ASDW-WEB 状態遷移依存を registry と照合する。
- **ASDW-WEB Cloud の Step 起動でモデル指定の適用範囲が変わった**。26 Step 化に伴い `start_step` 関数へ集約した結果、従来は Step.1.1 のみへ渡していた `SELECTED_MODEL` を全 Step へ渡すようになった。Issue で選んだモデルがワークフロー全体へ一貫して適用される。
- **users-guide を更新した**。[users-guide/workflow-reference.md](users-guide/workflow-reference.md) の Step 一覧表（4 ワークフロー分の Step 数と Agent 割当）、[users-guide/05-app-dev-microservice-azure.md](users-guide/05-app-dev-microservice-azure.md) の Step 表・依存グラフ・live Step 一覧、[users-guide/06-app-dev-dataflow-azure.md](users-guide/06-app-dev-dataflow-azure.md) の Step 表・DAG 図・並列実行の注記、[users-guide/08-ai-agent.md](users-guide/08-ai-agent.md) の AAGD Step 表、[users-guide/agentic-retrieval-guide.md](users-guide/agentic-retrieval-guide.md) の AAR Step 表へ新 Step を反映した。
- **FR-CLOUD-06 を改訂し、FR-CLOUD-07 を新設した**。従来の「ASDW-WEB の Cloud 起動を停止する」という記述を、「同期が確認できた reusable workflow は dispatch 対象としてよい」という一般規則へ改め、AAR を Cloud dispatch 対象とする要件を追加した。あわせて TBD-06 の根拠 (3)（Cloud 対象を増やす方向とは逆）が失効したことを明記し、ARD を CLI / GUI 専用とする FR-WF-ARD-01 の結論は根拠 (1)(2) により維持されることを記録した。

**既知の境界**: GitHub Actions の構文・registry parity・dispatcher routing はローカル検証済みだが、本変更では実 GitHub Issue を作成する Cloud live run と Azure リソースへの live 測定は実施していない。実測 Step は対象環境・資格情報・数値目標が無い場合に `NOT_MEASURED` / `NO_TARGET` を記録し、値を推測しない。

**検証**: 新規 2 ファイルの契約テストで 71 passed（実装前の RED を実測確認: validator の `ImportError`、registry 配線 33 failed）。Step 数の期待値表を新 Step に合わせて更新し `test_workflow_registry.py` 206 passed。`test_consumed_artifacts.py` / `test_output_paths_template_resolvability.py` / `test_fanout_output_template_resolution.py` / `test_template_engine.py` / `test_work_path_regression.py` を含む走査型テストと、`test_gui_help_content.py` / `test_azure_microsoft_learn_mcp_contract.py` / `test_skill_resolver.py` / `test_workflow_categories.py` / io-contract 検証系で追加の失敗が無いことを確認した。`.github/scripts/validate-io-contract.py` は 137 Agent に対し schema / integrity / registry mismatch すべて 0 件。`test_cloud_reusable_workflow_parity.py` は AAGD の Step 5 欠落を一度 FAIL として検出し、reusable への追加後に回復した。ADFDV を parity の検証対象へ加えたうえで 23 passed、`auto-dataflow-dev-reusable.yml` と `auto-ai-agent-dev-reusable.yml` の YAML 構文解析も成功することを確認した。新 Skill が `.github/skills/testing/requirements-conformance-measurement` として解決されることを実測した。

<!-- validation-confirmed -->

### Added — AI Agent 共通能力契約へ Identity / Observability / 配布 / 評価の 4 契約を追加した（AG-CAP-07〜10）

ARD → データ設計 → AAG → AAGD の順で「画面を持たない、データ中心の AI Agent」を設計・開発する経路を整備するにあたり、`ai-agent-capability-contract` Skill の既存 6 契約（AG-CAP-01〜06）では次の 4 点が契約として存在しなかった。

1. **Agent が「誰として」下流リソースを呼ぶか**が固定見出しで記録されていなかった。`entra-agent-id` は AAG Step 2 / 3 と AAGD Step 2.3 の optional skill として公開されるだけで、実行 identity・委任の有無・権限付与範囲を設計書へ残す契約が無かった。
2. **可観測性が検証されていなかった**。[.github/prompts/Dev-Microservice-Azure-AgentCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-AgentCoding.prompt.md) は Observability コードの生成を指示していたが、[hve/artifact_validation.py](hve/artifact_validation.py) 内に対応する検証は無く、`Observability` の文字列は AR-CAP-04 の見出し 1 件しか存在しなかった。
3. **生成物を配布する契約が無かった**。AAGD は `plugin.json` を生成するが、Agent Plugins Specification 1.0.0 が定義するコンポーネントは skills と MCP servers の 2 種のみであり、どちらを載せるかを決める契約が無かった。
4. **選んだ検索経路が目的に見合うかを判定する契約が無かった**。高い推論量を伴う検索手法を選んでも、より安い経路で足りるかどうかを設計時に問う仕組みが無かった。

- **AG-CAP-07 `Agent Identity & Authorization` を追加した**。`Identity kind` / `Authentication mode` / `Permission scope` / `Identity granularity` / `Accountability` / `Secret handling` を必須ラベルとし、attended（delegated / on-behalf-of）と unattended（application-only）の分類名を Microsoft Foundry の Agent identity 公式定義へ揃えた。**AG-CAP-03 または AG-CAP-04 のいずれかの経路が per-user 権限を要件とする場合、`attended` を含めることを必須**とし、ユーザー identity を伝播できないまま application 権限で代替することを禁止した。検索経路の per-user 判定は AG-CAP-03、Knowledge Base を MCP 公開する際の伝播可否は AR-CAP-05 を正本とし、再定義しない。
- **AG-CAP-08 `Observability Contract` を追加した**。準拠規約の既定を OpenTelemetry の generative AI semantic conventions とし、必須 span をリクエスト全体 / Goal Loop の各 iteration / 各 Tool 呼び出し / 各検索呼び出しの 4 種と定めた。検索・Tool 呼び出しの span 属性へ query 本文・response 本文・access token・raw URL を入れないことを明示し、AR-CAP-04 の「残してはならないもの」と整合させた。
- **AG-CAP-09 `Distribution & Packaging` を追加した**。Agent Plugins チャネルと Microsoft 365 / Teams チャネルの 2 系統を扱い、closed schema・コンポーネント 2 種・`mcp.json` のインライン記述不可・非 loopback の HTTPS 必須・**v1 が OAuth 設定を定義せず認可が client 管理であること**・`headers` / `env` への資格情報埋め込み禁止を仕様条項付きで固定した。M365 側は公開範囲と認可スキームの連動、版の再利用不可、公開メタデータが利用者に見えることを記録項目とした。
- **AG-CAP-10 `Evaluation & Route Right-sizing` を追加した**。**候補経路を 2 段以上実測しない評価は受理しない**とし、未実測を PASS としないことを契約化した。候補の並び順は `references/search-routing.md` を正本とする。
- **AG-CAP-07 / 08 / 10 は N/A にできない**契約とし、§8.1 設計 gate と SKILL.md の契約一覧へ明記した。
- **`references/tool-mcp-skill-packaging.md` に §4.4「Agent自身をMCP Serverとして公開する場合」を新設した**。既存 §4.2 が扱う「既存業務 API を MCP 公開する adapter」と区別し、公開 Tool を AG-CAP-04 で `Required: yes` のものに限定、mutation は REST と同じ認可・HITL・監査・冪等性を通すこと、要件の根拠なく既定で有効にしないことを禁止事項へ入れた。既存 §4.4「allowlist Tool 数の集計」は §4.5 へ繰り下げた（本文は無変更）。
- **`references/search-routing.md` に §4.1〜§4.3 を追加した**。検索経路のコスト階段を 5 段（反復検索あり / 既定 / LLM 非使用の最小構成 / データストア native / 自前実装）で定義し、各段を下げたときに失う機能を明示した。Knowledge Source として提供されないストアや、document-level permission を明示サポートしない Knowledge Source を候補から外す判定条件、および自前実装を選んだ場合に補う 6 機能を表にした。
- **範囲表記を `AG-CAP-01〜10` へ更新した**。`references/capability-contract.md` の §4 / §5.1 / §6 / §7 / §8.1 / §8.4 / §10、[.github/skills/ai-agent-capability-contract/SKILL.md](.github/skills/ai-agent-capability-contract/SKILL.md)、[.github/skills/_evals/ai-agent-capability-contract.eval.yaml](.github/skills/_evals/ai-agent-capability-contract.eval.yaml)、`scripts/validate-agent-contract.py` の argparse description が対象。

**既知の境界**: 本エントリーは Skill（契約の正本）だけを対象とする。契約を消費する側、すなわち AAG / AAGD の Prompt・テンプレート・`hve/artifact_validation.py` の `_AI_AGENT_CONTRACT_HEADINGS`・`hve/tests` のアサーションは **まだ `AG-CAP-01〜06` のまま**であり、後続の変更で揃える。そのため現時点では AG-CAP-07〜10 は設計書生成にも runtime gate にも反映されない。`hve/tests/test_ai_agent_capability_contract.py` の `_CONTRACT_IDS` は `f"AG-CAP-0{index}"` 形式のため、AG-CAP-10 を含める際は `f"AG-CAP-{index:02d}"` へ変更する必要がある。`references/capability-contract.md` に既存の `### 5.3` 重複（「Read、REST mutation、MCPの境界」と「N/Aの条件」）があるが、本変更起因ではないため番号は変更していない。新規参照は番号ではなく節タイトルで行っている。

**検証**: `python .github/scripts/validate-skill-routing.py` が exit 0（唯一の警告 `UNREFERENCED_SKILL` は本変更が触れていない別作業の新規 Skill に対するもの）。`pytest hve/tests/test_ai_agent_capability_contract.py` が 11 passed。`git diff` で `tool-mcp-skill-packaging.md` の §4.5 繰り下げが見出し行のみの移動であり本文が無改変であることを確認した。編集途中に `references/capability-contract.md` §5.3 の本文 1 行を意図せず書き換えたことを自己検出し、元の記述へ復元済み。

<!-- validation-confirmed -->

### Added — ワークフロー一覧に `AI Agent` グループを追加し、分類表を CLI と共有する正本へ集約した（FR-GUI-21）

GUI Step 1 のワークフロー一覧には 5 つのカテゴリー見出しがあったが、`aag` / `aagd` / `aar` はどのカテゴリーにも登録されておらず、未分類 ID の縮退枠である「その他」に落ちていた。3 件はいずれも AI Agent 系ワークフローであり、名称からは同種と分かるのに一覧上は分類不能な残りとして扱われていた。

さらにカテゴリー表は GUI 専用モジュール [hve/gui/page_workflow_select.py](hve/gui/page_workflow_select.py) のリテラルとして定義されていた。CLI は PySide6 に依存する `hve/gui/` を import できないため、同じ分類を参照する手段が無く、HVE CLI Orchestrator の対話メニューはグループ表示を一切持たないフラットな 12 件の一覧だった。

加えて `aag` / `aagd` / `aar` は GUI の説明文辞書に未登録で、`HelpPopupButton.from_key` が説明文の無いキーへ `None` を返すため、この 3 件だけヘルプボタンが表示されなかった。`aar` は表示名辞書にも登録が無かった。

- **カテゴリー表を [hve/workflow_registry.py](hve/workflow_registry.py) の `WORKFLOW_CATEGORIES` へ移し、単一正本にした**（FR-MAINT-07）。GUI は `_load_workflow_categories()`、CLI は `_workflow_options_with_categories()` から同じ表を読む。同ファイルには「GUI / CLI 側で表示するグループを本モジュールへ集約する」という既存の前例（`_WORKFLOW_GROUP_MAPS`）がある。
- **`AI Agent` カテゴリーを追加した**。構成員は `aag` / `aagd` / `aar` で、既存 5 カテゴリーの名称・構成員・順序と画面上の並び順は変えていない。カテゴリー順は GUI の実行ステップパネルの並び順も決めるため、現行順を保つことで既存の表示順契約を維持した。
- **未分類 ID の「その他」縮退経路は残した**。新規ワークフローをレジストリへ追加した時点でカテゴリー登録が漏れても、選択肢が一覧から消えないようにするため。
- **CLI 対話ウィザードをグループ順表示にした**。`Console.menu_select` は与えられた全行を連番付きの選択肢として描画するため見出し行を挿入できない。既存の `_step_options_with_groups`（ステップ選択）と同じく、カテゴリー名を各選択肢の接頭辞へ埋め込む方式を採り、`Console` は改修していない。並べ替えは表示用リストと選択結果の解決に使うリストを同一にして索引整合を保つ。
- **AAG / AAGD / AAR のヘルプと表示名を補完した**。[hve/gui/help_content.py](hve/gui/help_content.py) の `_WORKFLOW_SHORT` / `WORKFLOW_GUIDE_MAP` と [hve/gui/page_workflow_select.py](hve/gui/page_workflow_select.py) の `_WORKFLOW_DESCRIPTIONS`、[hve/template_engine.py](hve/template_engine.py) の `_WORKFLOW_DISPLAY_NAMES` へ登録し、英訳を `hve/gui/i18n/hve_gui_en_US.ts` へ追加して `.qm` を再生成した。AAG / AAGD の英訳は過去に `type="vanished"` として残っていた訳文を再利用した。
- **ワークフロー表示順の列挙表から欠落していた `aar` を補った**。[hve/gui/page_options.py](hve/gui/page_options.py) と [hve/autopilot/plan_review_gap.py](hve/autopilot/plan_review_gap.py) の `_WORKFLOW_CANONICAL_ORDER` に `aar` が無く、[hve/gui/workflow_step_requirements.py](hve/gui/workflow_step_requirements.py) の `WORKFLOW_PRIORITY` とだけ内容が食い違っていた。現時点で表示・挙動は変わらない（前者は `_STEP2_FIELDS_BY_WORKFLOW` に `aar` キーが無いため枠を生成せず、後者は `step.output_paths` のみを索引化するが AAR の全 Step は `output_paths_template` しか持たないため）。
- **users-guide を更新した**。GUI ガイドのワークフロー一覧表へグループ列を追加し（併せて `aas` / `aad-web` / `asdw-web` / `adoc` の正式名称をレジストリ定義へ揃えた）、CLI ガイドの対話メニュー出力例を実際の表示へ差し替え、AI Agent 系 3 ガイドへ GUI のカテゴリー名を追記した。

**既知の境界**: 表示順を列挙する 3 つの表は 3 箇所のまま維持した（統合はカテゴリー分類の要件範囲外で、Autopilot のプランレビュー経路まで影響が及ぶため）。GUI のスクリーンショットと 2 ステップ操作フロー図は更新していない（後者は現状もカテゴリー見出しを描かないフラット一覧の簡略図であり、本変更の影響を受けないため）。

**検証**: 新規 3 ファイル + 既存 1 ファイル追記のテストで 31 passed（実装前の RED を実測確認: `WORKFLOW_CATEGORIES` の `ImportError`、`_workflow_options_with_categories` の `AttributeError`、`AI Agent` 見出し不在による 4 件失敗、説明文欠落による `['aag', 'aagd', 'aar']` の失敗）。列挙表の RED は 3 表から `aar` を一時的に除いた状態で `assert {'aar'} == set()` を実測した。`hve/tests` を 4 バッチに分割して 7692 passed。GUI は Step 1 選択・オプション系で 223 passed。`.qm` は 818 translations を生成し、新規 3 件が英訳へ解決することを実測した。TDD inventory を再生成し、FR-GUI-21 が `active-or-described` として索引へ登録されたことを確認した。残存失敗はいずれも本変更が触れていないファイル（ASDW-WEB / APP-009 のデータ生成・SWA workflow、`markdown-query` 配布キットの CRLF）に起因するか、`main()` 内の既存の相対 import と AAD-WEB fan-out に対する pre-existing な失敗で、変更 7 ファイルの差分位置と未変更ファイルの照合により自変更起因でないことを確認した。

<!-- validation-confirmed -->

### Added — AAG / AAGD へ Agentic Retrieval 方針ゲートと Agent Plugin パッケージングを追加した（FR-WF-AAG-03 / 04、FR-WF-AAGD-05 / 06 / 07）

AAG / AAGD が生成する AI Agent について、2 つの欠落を埋めた。

1 つ目は **Agentic Retrieval の効果が設計・実装で担保されていなかった**こと。`--enable-agentic-retrieval` は `StepDef.disabled_when_config` 経由でしか消費されず、AAD-WEB / ASDW-WEB / AAR の Step 実行可否だけを制御していた。AAG / AAGD には Agentic Retrieval 専用 Step が無いため、利用者が `yes` を指定しても生成 Agent が Foundry IQ を選ぶ保証が無かった（同種のオプションである `--enable-tool-search` は Prompt へ注入されており、扱いが非対称だった）。また AR-CAP-02 の Knowledge Source は上限 10 だけを検証しており、**1 件でも PASS** していた。1 件の Knowledge Base はファンアウト先が 1 つしかなく、クラシックな単一クエリ検索と等価になるため、「1 リクエストで複数ソースを横断する」という Agentic Retrieval 固有の利得が出ない。

2 つ目は **生成物が可搬なプラグインとして配布できる形になっていなかった**こと。AG-CAP-06 が生成する `src/agent/{key}/skills/{skill-name}/` は [Agent Plugins Specification 1.0.0](https://github.com/agentplugins/agent-plugins-spec) の固定位置 `skills/` と構造が一致していたが、plugin root のマニフェスト `plugin.json` が無いため、仕様 §5.1 により適合クライアントはコンポーネントを一切 discover できなかった。

- **Agentic Retrieval 方針を AAG Step 3 / AAGD Step 2.3・3 へ注入した**（FR-WF-AAG-03）。[hve/runner.py](hve/runner.py) に `_agentic_retrieval_policy_prefix` を追加し、`_tool_search_policy_prefix` と同じ 3 値（`auto` / `yes` / `no`）・同じ fail-closed 規則で Prompt へ渡す。同じ Step へ 2 方針が注入されるため見出しを分離した。AAGD Step 4 は tool search 専用評価のため対象外とした。
- **方針別の設計成果物ゲートを追加した**（FR-WF-AAG-04）。[hve/artifact_validation.py](hve/artifact_validation.py) の `_parse_ai_agent_design` 系へ `agentic_retrieval_policy` を通し、`yes` かつ `enterprise-unstructured` の Request class がある場合に Foundry IQ 経路の選択を必須化、`no` の場合に同経路を禁止、3 値以外を fail-closed で拒否する。
- **Knowledge Source の下限 2 と索引契約を必須化した**（FR-WF-AAG-04）。AR-CAP-02 は 2 行以上 10 行以下とし、AR-CAP-01 へ `Index semantic configuration` を必須ラベルとして追加した。各サブクエリが semantic rerank を通るため索引側の構成が検索品質の上限を決めることを根拠とし、Skill `agentic-retrieval-contract` へ整合ルール R14 / R15 として記録した。
- **AAGD Step 2.1 / 2.2 へ `agentic-retrieval-contract` を公開した**（FR-WF-AAGD-05）。従来は Step 2.3 / 3 だけが required 宣言しており、TDD の RED を作る Step から AR-CAP の検証観点（予算超過時の縮退・引用必須項目）の正本へ到達できなかった。
- **Deploy ゲートの early return を解消した**（FR-WF-AAGD-05）。`validate_ai_agent_deploy_artifacts` は Toolbox 未採用時に先頭で return しており、AR-CAP 設計値と Deploy スクリプトの乖離を検出できなかった。Toolbox の採否に依存せず、AR-CAP-01 の `Knowledge base name` と AR-CAP-02 の各 `KS name` が `src/infra/azure/` 配下から追跡できることを静的に照合する。Azure へは接続しない。
- **`src/agent/{key}/plugin.json` の生成と検証を追加した**（FR-WF-AAGD-06）。`validate_agent_plugin_manifest` が `$schema` の固定値、`name` の仕様 §5.5 制約（1〜64 文字・`a-z0-9.-`・先頭末尾英数・`--` / `..` 禁止）と fan-out キーの小文字化一致、closed schema 違反、symlink を検証する。現行キー `AG-01` は大文字を含み仕様を満たさないため、小文字化を必須とした。仕様の任意フィールドは利用者の追記を壊さないよう受容する。`mcp.json` は生成しない（AG-CAP-05 が生成 Agent を MCP client と定めており、Tool allowlist・承認条件・timeout・retry に対応フィールドが仕様 1.0.0 に無いため）。
- **`SKILL.md` frontmatter の長さ制約を検証するようにした**（FR-WF-AAGD-07）。既存検証は kebab-case 形状と有意性だけを見ており、Agent Skills 仕様の `name` 64 文字 / `description` 1024 文字の上限超過を検出できなかった。
- **未追跡の重複 Skill ディレクトリを削除した**。`.github/skills/azure-skills/agentic-retrieval-contract/`（`SKILL.md` を持たず `references/` のみ）は正本の旧版のサブセットで、参照 0 件・Git 未追跡だった。

**既知の境界**: Cloud（`hve/cloud_aagd_gate.py`）の成果物再検証は本方針を伝搬せず `auto` 相当で動作する。retrieval の実測評価（reasoning effort 比較）は引き続き AAR Step 6 のみが担い、AAG / AAGD には追加していない。

**検証**: 新規・改修テスト 8 ファイルで 155 passed（RED → GREEN を確認）。周辺回帰 594 passed / 2 skipped。`validate-io-contract.py` は Registry mismatch 0 件。TDD inventory を再生成し、新規 5 要件が `active-or-described` として索引へ登録されたことを確認した。

<!-- validation-confirmed -->

### Changed — データフロー実装の既定言語を Python / pytest へ戻し、検証範囲を Cloud 経路まで広げた（FR-WF-ADFDV-03）

`3f992af4`「データフロー実装のプログラミング言語を C# に変更し、テストフレームワークを xUnit に更新」が、その直前まで存在した Python 契約を上書きしていた。上書き前の契約は「実行基盤として Apache Spark / Microsoft Fabric / Databricks を選択できる言語である」ことを選定理由として明記しており、`users-guide/02-app-architecture-design.md` の batch 定義（「大量データ一括処理（PySpark / ADF / Airflow / dbt 等）」）とも整合していた。C# 化はこの整合を崩し、あわせて言語契約の機械検証（要件 `FR-WF-ADFDV-03` と対応テスト 4 件）も削除していたため、退行を検出できない状態になっていた。上書き直前の状態へ戻す。

- **既定言語を Python / pytest へ戻した**。対象は [Dev-Dataflow-ServiceCoding](.github/prompts/Dev-Dataflow-ServiceCoding.prompt.md) / [Dev-Dataflow-TestCoding](.github/prompts/Dev-Dataflow-TestCoding.prompt.md) / [Dev-Dataflow-FunctionsDeploy](.github/prompts/Dev-Dataflow-FunctionsDeploy.prompt.md) の各 Prompt と `templates/adfdv/step-2.1.md` / `step-2.2.md`。データ規模に応じて標準ライブラリ / pandas と PySpark を選び分け、根拠を README へ記録する規定も復活させた。
- **言語契約の機械検証を復活させた**。`FR-WF-ADFDV-03` と [hve/tests/test_adfdv_deploy_contract.py](hve/tests/test_adfdv_deploy_contract.py) の 4 テスト（既定言語 / pytest 採用 / 選定理由に実行プラットフォーム名を含むこと / `.NET` 固有トークンの残存 0 件）を戻した。
- **Cloud 経路の不整合を解消した**。[.github/workflows/auto-dataflow-dev-reusable.yml](.github/workflows/auto-dataflow-dev-reusable.yml) の inline Issue body に `xUnit / C#` と `dotnet test` が残っており、`adfdv` は Cloud 起動が有効なため、Cloud で実行すると CLI と異なる言語で生成される状態だった。これは C# 化コミット以前から存在した不整合で、Python 契約の対象範囲が Prompt 3 件と body テンプレート 2 件に限定されていたため検出できていなかった。当該 2 箇所を Python / pytest へ揃え、`FR-WF-ADFDV-03` の検証対象を **6 ファイル**へ拡張した。

**検証**: `test_adfdv_deploy_contract.py` 8 passed。Prompt / テンプレート / TDD 契約系の広域回帰 240 passed。ADFDV 関連 6 ファイルに対する `.NET` 固有トークン（`dotnet ` / `xUnit` / `.csproj` / `C#` / `NuGet`）の残存 0 件を機械検証で確認した。

<!-- validation-confirmed -->

### Added — ADI が下流ワークフロー（ARD / AAS / ADFD）の成果物へ設計書由来の候補を反映するようにした（FR-WF-ADI-13〜16）

ADI は目録・トリアージ・ルーティング表までを生成していたが、その結果は下流ワークフローへ自動では渡らなかった。ルーティング表に `→ ARD` / `→ AAS` / `→ ADFD` の列はあるものの、それを読む配線は AQOD / AKM 側にしか無く、設計ワークフローの利用者は表を人手で読み替える必要があった。Step 5.1 / 5.2 / 5.3 を追加し、下流の**最上流 Step の成果物**へ候補セクションを直接書き込むようにした。

- **Step 5.1 / 5.2 / 5.3 を追加した**。いずれも Step 4 の後に**並列実行**され、書き込み先は重ならない。反映先は `docs/catalog/use-case-skeleton.md`（ARD Step 3.1）、`docs/catalog/app-catalog.md` / `domain-analytics.md` / `data-model.md`（AAS Step 1 / 3.1 / 4.1）、`docs/dataflow/dataflow-app-catalog.md`（ADFD Step 0.2）の 5 件。3 Step は Agent [Doc-OriginalDownstreamSeed](.github/prompts/Doc-OriginalDownstreamSeed.prompt.md) を共有し、対象別の出力仕様だけを body テンプレートに置くことで共通ルールの多重管理を避けた。
- **ID は採番しない契約にした**。`APP-` / `UC-` / `SVC-` などの識別子は下流ワークフローが採番する。ADI が先に振ると採番が衝突するため、候補は名称・根拠・出典だけを持つ。[hve/artifact_validation.py](hve/artifact_validation.py) に `validate_downstream_seed_section` を追加し、採番済み ID の混入と出典 `doc_id` の欠落を機械検証する。
- **既存成果物は熟読してからマージする**。対象ファイルがある場合は全文を読み、候補セクション以外の既存記述を変更しない。既に本表にある実体と重複する候補は追加せず、除外件数を完了報告に記録する。
- **下流ワークフローは自動起動しない**。`FULL_PIPELINE` に `adi` を登録せず、依存先としても宣言しない。この不変条件はテストで固定した。
- **対象を設計フェーズの 3 ワークフローに限定した**。`aad-web` は成果物のファイル名に APP-ID を含むため `app-catalog.md` 確定前は書き出し先が決まらない。`asdw-web` / `adfdv` / `aar` の成果物は `src/` のコード・Azure スクリプトが中心で、TDD RED→GREEN と Azure 公式情報に基づく契約のため、旧設計書からの生成は根拠のない実装・サービス選定になる。
- **前提成果物チェックへの影響を明記した**。HVE は下流 Step の前提成果物を**ファイルの存在有無**だけで判定する（[hve/orchestrator.py](hve/orchestrator.py) の `check_step_input_artifacts`）。ADI が `app-catalog.md` 等を新規作成すると、中身が候補セクションだけでも「成果物あり」と判定されるため、AAS 未実行でも AAD-WEB の前提チェックが通る。挙動を変える除外機構は追加せず、[users-guide/00-design-doc-ingestion.md](users-guide/00-design-doc-ingestion.md) に警告として記載した。
- **ルーティング表に `→ 反映先成果物` 列を追加した**。どの候補がどのファイルへ反映されるかを Step 4 の時点で追跡できるようにした。
- **ADI をマージ規約テストの対象に加えた**。`TestExistingArtifactPolicyIntegration` の対象ディレクトリに `adi` が未登録で、テンプレートは既に規約を満たしていたものの退行を検出できない状態だった。

**検証**: `validate-io-contract.py` が 133 Agent / schema・integrity・registry いずれも 0 error。ADI 系・registry・template・prompt・orchestrator・consumed_artifacts のテスト 692 passed / 2 skipped。実測により、ADI の出力と下流 7 ワークフローの出力の完全一致が**意図した 5 件のみ**（ard 1 / aas 3 / adfd 1）で、`aad-web` / `asdw-web` / `adfdv` / `aar` とは 0 件であることを確認した。変更した Markdown の相対リンクとアンカーを検査し、新規追加分は全て解決することを確認した（検出された 6 件はいずれも対象が元から不在の既存問題で、自分の差分は該当行に触れていない）。`test_orchestrator.py::TestRunWorkflowFanout::test_aad_web_fanout_meta_is_forwarded_to_step_runner` の 1 件は `git worktree` で HEAD を別ツリーへ取り出しても同様に失敗する既存不具合である。

<!-- validation-confirmed -->

### Changed — ADI の派生物を `docs/original-design-doc-ingest/` へ移し、成果物を `docs/` に一本化した

ADI だけが `docs-original-index/` というリポジトリ直下のディレクトリへ派生物を出力しており、他のワークフローが `docs/` 配下へ成果物を集約するのと揃っていなかった。そのため索引・版管理・GUI エクスプローラーの 3 箇所へ個別にディレクトリ登録が必要で、登録漏れが「動くが誤動作する」形で表面化しうる構造だった。派生物の出力先を `docs/` 配下へ移すことで、既存の `docs` 登録がそのまま効くようにした。

- **出力先を移動した**。`docs-original-index/` → `docs/original-design-doc-ingest/`。`index.json` / `content.md` / `provenance.json` / `card.md` の構造と `<slug>/` の階層は変更していない。人間可読なカタログ（`design-doc-inventory.md` / `design-doc-catalog.md` / `design-doc-routing.md`）は、既存の `app-catalog.md` 等と同じ性質のため [docs/catalog/](docs/catalog/) に据え置いた。
- **`index.json` の `content_path` が壊れる不具合を修正した**。[hve/doc_ingest.py](hve/doc_ingest.py) は出力先ディレクトリ名を `Path.name` で組み立てていたため、出力先が入れ子になると親ディレクトリが欠落し、リポジトリルートから解決できないパスを記録していた。出力先を丸ごと含める形へ改め、回帰テストを追加した。従来は出力先が直下 1 階層だったため顕在化していなかった。
- **重複していたディレクトリ登録を 3 箇所から削除した**。`mdq.toml` の `[index].roots`、[.github/scripts/hve_scope.py](.github/scripts/hve_scope.py) の版管理対象外プレフィックス、[.github/copilot-instructions.md](.github/copilot-instructions.md) の対象外列挙。いずれも `docs` / `docs/` を既に含んでおり、移動後は二重宣言になるため。副次的に、索引ルートの記述が 9 件で `.github/skills/markdown-query/` 側の記載と一致するようになった。
- **既知の挙動変化を明記した**。派生物が `docs/` 配下になるため `--self-improve-target-scope "*"` の走査対象に入る（`SELF_IMPROVE_WILDCARD_PATHS` に `docs` が含まれるため）。除外用のフラグは追加せず、[users-guide/00-design-doc-ingestion.md](users-guide/00-design-doc-ingestion.md) の「既知の制約」に記載する方針とした。

**検証**: 対象 31 ファイル・78 参照のうち、生成物 2 ファイルを含め旧パス参照が 0 件であることを確認。`validate-io-contract.py` が 130 Agent / schema・integrity・registry いずれも 0 error。ADI 系および registry / template / prompt / orchestrator / self-improve のテスト 993 passed。`test_orchestrator.py::TestRunWorkflowFanout::test_aad_web_fanout_meta_is_forwarded_to_step_runner` の 1 件が失敗するが、`git worktree` で HEAD を別ツリーへ取り出して同一環境で実行しても同様に失敗する既存不具合で、本変更が触れていない AAD-WEB Step 2.2 の fan-out に起因する。実データで `python -m hve ingest-docs` を実行し、29 件が新パスへ出力され `content_path` がリポジトリルートから解決できること、`docs-original/` が無変更であることを確認した（確認後、生成物は削除）。mdq の索引 DB に旧ルート由来のチャンクは 0 件で、索引再構築は不要だった（旧ディレクトリが未生成のため索引されていなかった）。

<!-- validation-confirmed -->

### Added — 設計書取り込みワークフロー ADI（Auto Design-doc Ingestion）を新設した（FR-WF-ADI-01〜12 / NFR-SEC-ADI-01・02）

これまで `docs-original/` の原本を扱えるのは AQOD（質問票生成）と AKM（knowledge 統合）だけで、どちらも **Markdown を直接読む前提**だった。そのため (1) PDF / Office は CLI 経路で読めず、(2) 何が入っているかの目録が無く、(3) D01〜D21 の 21 並列子がそれぞれ「関連しそうな資料」を毎回自力探索する構造だった。ADI はこの前段を切り出し、「目録化 → 文脈カード生成 → 目的に基づく選別 → 下流ルーティング」の 4 Step として独立させる。

- **ワークフロー `adi` を追加した**。固有パラメータは `purpose`（任意）の 1 つだけとし、変換エンジン選択やトリアージ方針のフラグは定数で開始する（未使用オプションの先回り導入を避ける）。**Cloud（GitHub Actions）は未対応**で、`ard` と同じく CLI / GUI 専用とする。GUI では専用カテゴリ **「既存ドキュメントのインポート」** から選択し、Step 2 の「ADI 固有」枠で目的を入力する。
- **決定的前処理を Python 側に置いた**。[hve/doc_ingest.py](hve/doc_ingest.py) と `python -m hve ingest-docs` サブコマンドを新設し、走査・`sha256` 算出・Markdown 変換・`index.json` 生成を LLM に任せない。同一入力に対し `docs` / `excluded` は常に同一になる。変換は既存の [hve/gui/doc_convert.py](hve/gui/doc_convert.py)（microsoft/markitdown）を CLI からも使う形で再利用し、依存パッケージは追加していない。
- **`sha256` による差分スキップと重複検出を入れた**。内容が変わらない文書は派生物を再書き込みせず、同一内容の文書は `duplicate_of` として記録する。実データでの検証中に `docs-original/original-docs/` という入れ子の二重配置（29 ファイル）を検出できた。
- **選別は「無言で捨てない」契約にした**。`out` 判定の全行に除外理由を必須化し、`purpose` が空のときは `must` を付与しない（目的が無い状態で「必須」とは判定できないため fail-safe 側に倒す）。`must` の依存先は `should` へ自動昇格し、取りこぼしを防ぐ。いずれも [hve/artifact_validation.py](hve/artifact_validation.py) の `validate_design_doc_card` / `validate_design_doc_catalog` で機械検証する。
- **既存ワークフローへの接続は後方互換とした**。AQOD / AKM の fan-out 共通指示に「`docs/catalog/design-doc-routing.md` があれば優先、無ければ従来どおり `docs-original/` を走査」を追記した。ADI を実行していない既存運用は無変更で動く。
- **派生物は `docs/original-design-doc-ingest/` に出力する**。`docs/` 配下に置くことで、BM25 索引（`mdq.toml` の `[index].roots`）・版管理対象外リスト（[.github/scripts/hve_scope.py](.github/scripts/hve_scope.py)）・GUI の `explorer_roots` のいずれも `docs` の登録で足り、個別登録が不要になる。
- **図の取り込みは未実装**。画像・`.drawio` / `.vsdx` は `excluded` として理由付きで記録される。制約は [users-guide/00-design-doc-ingestion.md](users-guide/00-design-doc-ingestion.md) の「既知の制約」に明記した。

### Fixed — `original-docs/` → `docs-original/` 移行の残存参照を解消した

- `users-guide/images/chain-self-improve.svg` の図中ラベルを `docs-original/` へ修正した。全体を実測した結果、残る `original-docs` はすべて識別子（`sources` の値名 / Agent のモード名 / 出力ファイル名 / ラベル名）であり、パス表記としての残存は 0 件であることを確認した。
- `.github/copilot-instructions.md` §0 の版管理対象外列挙と `users-guide/skills-markdown-query.md` の mdq roots 件数を、機械正本の変更に追従させた。

**検証**: `hve/tests/test_doc_ingest.py`（23 passed / 1 skipped）、`test_adi.py`・`test_adi_validation.py`・`test_adi_downstream_contract.py`・`test_catalog_parsers_design_doc.py`（合計 135 passed / 1 skipped）を RED → GREEN で確認した。`validate-io-contract.py` は 130 Agent で schema / integrity / registry とも 0 error。`test_workflow_registry.py`・`test_template_engine.py`・`test_consumed_artifacts.py`・`test_prompts.py`・`test_main.py`・`test_phase6_option_parity.py`（57 passed / 211 subtests）・GUI 系（96 passed）・`.github/scripts/tests`（91 passed）の既存テストに回帰がないことを確認し、`hve-dev/generate_tdd_inventory.py` を再実行して inventory を更新した（162 passed）。`python -m hve ingest-docs` を実データでスモーク実行し、58 件中 29 件の重複検出を確認した。

### Changed — QA 回答の Knowledge Management へのバックグラウンドマージを、GUI / CLI / Cloud 共通の明示選択にした（FR-QA-05 / FR-GUI-20 / FR-CLOUD-26）

これまでは実行前 QA（`--auto-qa`）を有効にするだけで、回答済み QA を `knowledge/` へ取り込む Knowledge Management が常にバックグラウンド起動していた。共有資産である `knowledge/` への自動書込みを利用者が制御できず、コスト・実行時間・差分レビュー量を選べなかった。設定 `qa_akm_background_merge`（既定: 無効）を新設し、3 面すべてで明示的に選ぶ形へ変更した。

- **既定値の変更（後方互換を意図的に崩す）**: `--auto-qa` だけを指定していた既存実行では、QA 起点 Knowledge Management が起動しなくなる。従来と同じ挙動にするには `--qa-akm-background-merge` を追加する。Cloud では Issue Form の「Knowledge Management マージ設定」にチェックを入れる。
- **判定点は実行面ごとに 1 箇所へ限定した**。CLI / GUI は [hve/orchestrator.py](hve/orchestrator.py) `_should_enable_qa_akm_dispatch`、Cloud は [.github/workflows/auto-issue-qa-ready-transition.yml](.github/workflows/auto-issue-qa-ready-transition.yml) の `save-qa-answer` job が出力する `sync_required` だけが判定する。Cloud はゲートを `sync_required` へ入れたため、`dispatch-akm` / 後続 job の条件式は無改修のまま成立する。
- **CLI**: `--qa-akm-background-merge`（`store_true`）を追加し、対話ウィザードでも「QA 自動投入」を有効にした非 AKM ワークフローのときに尋ねる。FR-QA-04 の Knowledge Management 用モデル / effort / context tier は、本設定を有効にしたときだけ尋ねる（無効なら子実行自体が起きないため）。実行サマリーへ `KM マージ` 行を追加した。
- **Cloud**: `knowledge-management.yml` を除く 9 テンプレートへ `enable_qa_akm_merge` チェックボックスを追加し、抽出は [.github/scripts/bash/lib/extract-qa-akm-merge.py](.github/scripts/bash/lib/extract-qa-akm-merge.py) と `copilot-assign.sh` の `extract_qa_akm_merge()` で行う。節が無い・チェックが確認できない・解釈できない場合はいずれも無効として扱い、job を失敗させない。抽出は locale に依存しないよう `stdin.buffer` から UTF-8 で直接デコードする。
- **環境変数経路は新設していない**。FR-QA-04 の 3 項目と同じ方針に揃えた。`--workflow akm` の明示実行は従来どおり対象外。

### Added — GUI 設定画面の「自動プロンプト」を 4 グループへ再編し、略語表記を平易化した（FR-GUI-20）

「QA」「AKM」という略語だけでは初見の利用者が内容を判別できず、また 1 ノードに QA / レビュー / Knowledge Management / 自己改善が混在していた。

- **設定画面「一般」カテゴリを再編した**。「自動プロンプト」ノードを廃止し、`基本設定` / `QA (質問票)` / `レビュー` / `Knowledge Management` / `自己改善 (Self Improve)` へ分割した。`追加プロンプト` と `コンテキスト最大文字数` は `基本設定` へ移した。
- **表示ラベルと説明文の略語を展開した**。`QA 自動投入` → `QA (質問票) 自動投入`、`QA 回答モード` → `QA (質問票) 回答モード`、`QA 用モデル` → `QA (質問票) 用モデル`、`AKM 用モデル` → `Knowledge Management 用モデル`、`AKM 用コンテキスト階層` → `Knowledge Management 用コンテキスト階層`。CLI のフラグ名と設定キー名は互換性のため改称していない。
- **新設のマージ設定を 2 面へ表示する**。設定画面の `Knowledge Management` ノードと、Step 1 右ペインの「共通設定」枠の双方に置き、共通枠の表示順を `QA (質問票) 自動投入` → `QA (質問票) 回答モード` → マージ設定 → `Knowledge Management 用モデル` → `Knowledge Management 用コンテキスト階層` → `追加プロンプト` に固定した。
- **活性制御**: マージ設定は `auto_qa` が「有効にする」のときだけ選択でき、Knowledge Management 用モデル / コンテキスト階層はさらにマージ設定が有効のときだけ活性化する。無効時は値を CLI へ渡さない。
- **内部カテゴリ名の表記も揃えた**。Step 1 右ペインの枠 `C3` は実行時に「共通設定  *必須」へ上書きされるにもかかわらず、初期タイトル・コメント・利用者ガイドの一覧・構成図が旧称「自動プロンプト」のままだったため、いずれも「共通設定」へ統一した（[users-guide/hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md) / [users-guide/hve-technical-architecture.md](users-guide/hve-technical-architecture.md) / [users-guide/images/hve-gui-orchestrator-2step-flow.svg](users-guide/images/hve-gui-orchestrator-2step-flow.svg) / [hve/gui/page_options.py](hve/gui/page_options.py) / [hve/gui/settings_store.py](hve/gui/settings_store.py) / [hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py) / [hve/gui/settings_apply.py](hve/gui/settings_apply.py)）。CLI の概念名「Post-step 自動プロンプト」は存続するため変更していない。

**実装上の判断（FR-MAINT-07 面横断の再利用）**: `_C3AutoPrompt` を `_CQaPrompt` / `_CReviewPrompt` / `_CKnowledgeManagement` / `_CSelfImprove` へ分割し、`_C3AutoPrompt` は 4 セクションを合成して属性を再公開するだけにした。ウィジェット構築コードを設定画面と Step 1 右ペインで 2 重に持たないためである。`auto_qa` は `_CQaPrompt` が所有し、Knowledge Management の活性判定は `_CKnowledgeManagement._refresh_enabled()` の 1 箇所だけに置いた。両面は `wire_auto_qa_to_knowledge_management()` で同じ配線を共有する。設定画面はカテゴリヘルプボタンを描画しないため、新ノードへの `_CATEGORY_HELP` エントリは追加していない。

**敵対的レビューで是正した点**: (1) 当初プランは CLI wizard と Cloud を対象外にしており、3 面の一貫性を欠いていたため両方をスコープへ入れた。(2) `_should_enable_qa_akm_dispatch` の引数追加で必ず壊れる既存テスト 2 箇所（`test_orchestrator.py` / `test_main.py`）の追随を計画に入れていなかったため追加した。(3) 「composite を残せば既存テストがそのまま動く」という断定が誤りで、`_SECTION_FIELDS["C3"]` を直接参照する 2 テストが壊れることを確認し追随させた。(4) 新オプションの `option_parity_matrix.yaml` 登録先を未決のままにしていたため、Cloud 対応を前提に `options:` へ 4 キー揃えて登録した。(5) 不要作業だった新ノードへの `_CATEGORY_HELP` 追加を削除した。(6) 自作テストの options ブロック抽出 regex が `re.DOTALL` 下で行をまたいで貪欲一致していた欠陥を修正した。

**検証**: 新規 RED を 4 ファイル（`hve/tests/test_qa_akm_background_merge.py` / `hve/tests/test_issue_template_qa_akm_merge.py` / `hve/gui/tests/test_settings_group_split.py` / `hve/gui/tests/test_page_options_km_background_merge.py`）で先に確認したうえで実装し、GREEN 化した。コア / CLI / Cloud 系 656 件（`test_main.py` / `test_orchestrator.py` / `test_runner_pre_qa.py` / `test_qa_akm_model_selection.py` / `test_issue_template_qa_parity.py` / `test_workflow_registry_agentic.py` / `test_gui_step2_refactor.py` ほか）、GUI 系 129 件、設定画面ワイヤリング 44 件、索引整合 223 件、3 面パリティ 57 件がいずれも PASS。`hve-dev/generate_tdd_inventory.py` を再実行し、FR-QA-05 / FR-GUI-20 / FR-CLOUD-26 が `active-or-described` として feature 索引へ載ることを確認した。新規・改称した GUI 文字列 46 件を [hve/gui/i18n/hve_gui_en_US.ts](hve/gui/i18n/hve_gui_en_US.ts) へ英訳投入し、`lrelease` で `.qm` を再生成した。

**検証の制約**: `hve/tests/test_orchestrator.py::TestRunWorkflowFanout::test_aad_web_fanout_meta_is_forwarded_to_step_runner` は本変更の前から失敗している。`git worktree` で HEAD を取り出して同一テストを実行し、同じく失敗することを確認済みで、本変更とは無関係である。

<!-- validation-confirmed -->


### Fixed — GUI の英語カタログを全件翻訳済みにし、廃止カテゴリのヘルプ定義を整理した

- **未翻訳だった GUI 文字列 257 件へ英訳を投入した**。`lrelease` の結果が `811 finished / 0 unfinished` となり、英語ロケールで日本語のまま表示される箇所が無くなった（従来は 233 件が未翻訳のまま無視され、23 件が未完了だった）。対象は `MainWindow` / `_C1Basic` / `_C5IssuePR` / `_CAgenticRetrieval` / `_CAutopilotSection` / `_C4WorkIQ` / `_C7Connection` / `AttachmentPane` / `help_content` ほか。`{path}` / `{total}` / `%s` / `%d` などのプレースホルダが原文と一致することを全 811 件について機械的に検証した。
- **廃止済みカテゴリのヘルプ定義を削除した**。[hve/gui/help_content.py](hve/gui/help_content.py) の `_CATEGORY_HELP` に残っていた `C2` / `C8` / `C9` / `C15` / `C16` は、対応するカテゴリ枠（`OptionsPage._setup_ui` の `_add(...)`）が存在せず、`category.<key>` からは決して参照されない死んだ定義だった。併せて回帰テストを「C1〜C16 が全て存在する」から「実在しないカテゴリの説明文が残っていない」へ変更し、カテゴリを減らしたときに検出できる形にした。
- **`基本設定`（C1）のヘルプに移設した 2 項目を反映した**。`追加プロンプト` と `コンテキスト最大文字数` が C1 の所有になったにもかかわらず説明文が旧内容のままだった。
- **`C11` の表示ラベルを FR-GUI-20 の表記規則へ揃えた**。枠タイトルとヘルプ、利用者ガイドの一覧が `AKM 固有` のまま残っており、`Knowledge Management` 表記の徹底が漏れていた。

**検証**: `hve/gui/tests/test_i18n.py`（22 件）/ `hve/tests/test_gui_help_content.py`（12 件）/ `hve/gui/tests/test_settings_group_split.py` / `hve/gui/tests/test_page_options_km_background_merge.py` / `hve/tests/test_gui_step2_refactor.py` の 71 件が PASS。英語ロケールを実際にロードし、代表 8 件が英訳へ解決されることを確認した。索引再生成後の `hve/tests/test_hve_surface_inventory.py` / `cq/tests/test_surface_export.py` の 162 件も PASS。

**既知の制約**: `help_content` の tool-search ポリシー説明は原文が `{種別}:{サーバー}:{ツール名}` というキー書式の例を含むため、プレースホルダ検証で 1 件だけ不一致として検出される。`.format()` を通さない表示専用の文字列であり、原文・訳文とも意図どおりである。

<!-- validation-confirmed -->


### Added — GUI「実行ジョブ」タブに、送信メッセージの位置表示（`n/n`）と前後移動を追加した（FR-GUI-18）

VS Code のチャットビューは、会話の上部に「いま見ている要求の本文」「その位置（`3/3`）」「前後へ移動する矢印」を出す。実行ジョブタブの会話ビューにはこれが無く、送信を重ねると自分がどの指示のところを読んでいるのかを、流れ続けるログの中から数えて把握するしかなかった。同じ並びと操作を会話ビューの直上へ置いた。

- **ターンとして数えるのは利用者の送信メッセージだけとした**。GUI 通知・ACK・実行ログは番号に含めない。VS Code の `n/n` が要求単位であることに合わせ、番号が実際の送信回数と一致するようにした。
- **本文は 1 行で表示し、改行以降と 60 文字を超える分を省略する**。送信方法（キューに追加 / いま割り込む / 中断して送信）と ACK 状態は併記しない。どちらも当該メッセージ自体が表示しており、見出しで重複させる意味が無いため。
- **移動は端で止まる**。先頭では前へ、末尾では次への操作が選べなくなり、反対側へ回り込まない。移動先は会話ビューの上端へ寄せる。
- **現在位置は移動操作とスクロールの両方から決まる**。移動操作ではその移動先を確定値とし、利用者が会話ビューをスクロールしたときはスクロール位置から決め直す。保持する状態は現在位置 1 つだけで、移動の直後にスクロール連動が上書きしないよう順序を固定した。
- **末尾のターンを上端へ寄せきれない場合でも番号が食い違わないようにした**。スクロールバーは上限で頭打ちになるため、素朴に「上端より上にあるターン」で判定すると、末尾へ移動したのに `n-1/n` と表示される。各ターンの位置をスクロール上限で clamp してから比較することで、追加の状態を持たずに一致させている。会話全体がスクロールせずに収まる場合も、移動操作の結果がそのまま番号へ出る。
- **送信メッセージが 1 件も無いときは行ごと隠す**。宛先を切り替えた直後や会話をクリアした直後はログだけの状態が常態で、常に `0/0` を出すと主導線を圧迫するため。送信待ちキュー行と同じ挙動に揃えた。
- **新しく送信したメッセージが現在位置になる**。

**併せて修正した既存の欠陥**: 会話ビューのログブロックが、実行中に 1 行ずつ届くログで高さを伸ばしていなかった。`_LogEntry` は高さ追従を `documentLayout().documentSizeChanged` にだけ接続していたが、このシグナルは `setPlainText`（宛先切替時のスナップショット）と幅変更では発火する一方、`appendPlainText`（実行中の 1 行追記）では発火しない。そのため **実行中にストリーミングされるログが 1 行分の高さに潰れ、2 行目以降が表示されない** 状態だった（実測: 40 行を追記しても高さ 23px のまま。スナップショット経由では 608px）。`document().contentsChanged` を併せて接続して解消し、追記経路とスナップショット経路が同じ高さへ収束することをテストで固定した。幅変更時の折り返し行数の変化は `documentSizeChanged` が担うため、両シグナルを併用している（実測: 幅 586px で 11 行 / 166px で 55 行に追従）。本欠陥は本機能のスクロール検証中に発見した。

**敵対的レビューで是正した点**: (1) 要件へ「現在ターンはスクロール位置から決定する」とだけ書いていたが、会話全体がスクロールせずに収まる場合はスクロール位置に情報が無く、移動操作を表示へ反映できない。移動操作時は移動先を確定値とする条項を追加した。(2) 要件の「表示は 1 行へ収め、収まらない場合は省略する」が検証不能だったため、「改行以降および実装が定める表示長の上限を超える部分を省略する」という観測可能な条件へ直した。(3) 要件の「会話ビューの上部から操作できる」が会話ビュー内部とも読め、配置がトレースできなかったため「会話ビューの直上」と明示した。(4) 受入ケースが要件の省略規則を網羅していなかったため補った。(5) テストが未実装の私有ヘルパー `_user_turn_widgets()` に依存しており、本番クラスへテスト専用 API を強いる設計になっていた。「1 ピクセル戻すと直前のターンが現在になる」等、公開 API と観測可能な条件だけで同じ契約を検証する形へ置き換えた。(6) スクロール連動の配線（パネル ↔ スクロールバー）を検証するテストが無かったため追加した。(7) その配線テストがドックを単独表示したままでスクロール範囲を得られず前提を満たしていなかったため、実運用と同じく `QMainWindow` へドッキングし、レイアウト確定に 2 巡のイベント処理が必要であることを実測して反映した。(8) 同テストがスクロールバーの初期値 0 のまま `setValue(0)` していて `valueChanged` が発火せず、連動を検証できていなかった。上限へ動かしてから 0 へ戻す両方向の検証へ直した。(9) `refresh_turn_nav` を公開名にしていたが内部からしか呼ばれず、タイマーのスロットとして外部接続される `refresh_pending_queue` と可視性の意味が食い違うため `_refresh_turn_nav` へ改名した。(10) 翻訳カタログへ記録した location 行番号が実体とずれていたため実測値へ揃えた。(11) 利用者ガイドの見出しにタイポ（`操作するる`）を混入させたため修正した。

**採用しなかった選択肢**: VS Code と同じくスクロール時だけ出現するオーバーレイ型の sticky ヘッダーは採らなかった。ビューポートの追従・z-order・背景描画の再実装が必要になる一方、得られる差は「スクロールしていない間に隠れるかどうか」だけで、位置把握と前後移動という機能価値は常設行と同一のため。ショートカットキーの割り当ても、既存キーバインドとの衝突検証が必要で要求に無いため見送った。

**検証**: `hve/gui/tests/test_chat_transcript.py`（31 件）/ `hve/gui/tests/test_copilot_chat_panel_chat_ui.py`（40 件）/ `hve/gui/tests/test_chat_input_box.py`（26 件）/ `hve/gui/tests/test_copilot_chat_panel.py`（21 件）/ `hve/gui/tests/test_i18n.py`（22 件）の 140 件が PASS。Copilot パネルとジョブ対話に触れる既存テスト（`test_copilot_job_context.py` / `test_copilot_interactive_session.py` / `test_job_interaction_ipc.py` / `test_page_workbench_job_interaction.py` / `test_main_window_dock_integration.py` / `test_start_autopilot_chain_branch.py`）を加えた 239 件も PASS。実装前に 29 件の RED を確認している。`hve/tests/test_hve_surface_inventory.py`（146 件）も PASS。`hve-dev/generate_tdd_inventory.py` を再実行し、FR-GUI-18 が `active-or-described` として feature 索引に載ることと、新規テスト 27 行がテスト索引へ登録されることを確認した。新規 `tr()` 4 件を [hve/gui/i18n/hve_gui_en_US.ts](hve/gui/i18n/hve_gui_en_US.ts) の `CopilotChatPanel` コンテキストへ登録し、`lrelease` で `.qm` を再生成した。

**検証の制約**: `hve/gui/tests` の全件一括実行は、本変更の有無にかかわらず完走しない既知事象のため、影響範囲に絞った上記 239 件で回帰を確認している。

<!-- validation-confirmed -->


### Fixed — GUI「作業状況」の経過時間が、ジョブ終了後もカウントアップし続ける問題を修正した（FR-GUI-19）

GUI の Step 2 Workbench では、実行対象のタスクが既に終了・停止しているのに画面が「実行中」のまま残り、経過時間だけが増え続けることがあった。原因は独立した 2 つの欠陥で、いずれも実測で確定した。

- **停止処理がサマリー行しか止めていなかった**。[hve/gui/widgets/dag_status_widget.py](hve/gui/widgets/dag_status_widget.py) `freeze_elapsed()` は `_global_finished_at` を設定するだけで、その値を参照していたのは `_update_summary_label` のみだった。Workflow ノード・Step ノード・fan-out 子ノードの 3 系統は `time.monotonic()` を直接参照しており、停止後も進み続けていた。offscreen で実測すると、`freeze_elapsed()` から 3600 秒進めた時点でサマリー行が `00:00:12` に固定される一方、Workflow ノードと Step ノードは `01:00:12` を表示していた。
- **Plan モードの終了検知が標準出力の終端だけに依存していた**。[hve/gui/state_bridge.py](hve/gui/state_bridge.py) `SubprocessReader.run()` は `for raw_line in stdout` が EOF に達してから `proc.wait()` して `finished_with_code` を emit する。[hve/gui/page_workbench.py](hve/gui/page_workbench.py) `_on_process_finished` はこのシグナルにのみ接続されており、停止契機は他に無かった。`launch_orchestrator` は `stdout=PIPE` で起動するため、サブプロセスが終了してもパイプが終端しない状況では `freeze_progress_elapsed()` が一度も呼ばれず、4 系統すべてが進み続ける。GUI 側にアイドル・無応答の監視は存在しない。

- **経過時間の終端値を `DagStatusWidget._now()` に集約した**。停止後は終了時刻を返すこのメソッドを、経過時間の終端値を求める 4 箇所（`_StepNodeItem.update_text` / `_FanoutChildNodeItem._elapsed_text` / `_WorkflowHeaderItem.update_text` / `_update_summary_label`）が共通で参照する（FR-MAINT-07）。停止時刻をノード側へ保存しないため、`set_plan` / `update_workflow_instances` による表示ノードの再生成後も停止が維持される。停止していないときの挙動は変わらない。
- **プロセスの終了状態を根拠とする終了検知を追加した**。`WorkbenchPage._check_subprocess_liveness()` が `Popen.poll()` で終了を確認し、終端通知が届かないまま猶予（5 秒）が過ぎたら経過時間を停止する。新規タイマーは作らず、既存の 500ms `_on_update_timer` から呼ぶ。猶予の起点は監視開始時刻ではなく終了確認時刻とし、プロセスが生存している限りは出力が何秒途絶しても停止しない（入力の途絶を終了の根拠にしない）。
- **停止は既存 API を経由させ、新しい停止経路を作らなかった**。異常終了として検知した場合は `WorkbenchState.mark_aborted()` と `freeze_progress_elapsed()` を呼ぶ。`mark_aborted()` は実装済みでありながら本番コードからは一度も呼ばれておらずテストのみが呼んでいたため、本変更で初めて配線された。これにより Footer の Elapsed（`state.all_done` 依存）も同時に停止する。
- **利用者の停止要求に続く終了は異常終了として記録しない**。`_stop_requested` が立っている場合は `[WARN]` を出さず `mark_all_done()` を使う。停止自体はどちらの経路でも行う。
- **実行中だった Step のステータスは書き換えない**。実際の結果を観測していないため、`running` のまま残す。新たな `[hve:stats]` の `kind` も追加していない。
- **`_on_qa_subprocess_terminated` は停止経路へ配線しなかった**。[hve/gui/qa_ipc_manager.py](hve/gui/qa_ipc_manager.py) `QAIpcManager._check_subprocess` も `Popen.poll()` で終了を検知するが、`qa_answer_mode="gui-file"` のときしか起動しない。常時動作する本検知が上位互換であり、両方に配線すると同一ルールの 2 重実装になるため（FR-MAINT-07）。
- **`process_finished` は emit しない**。emit すると [hve/gui/main_window.py](hve/gui/main_window.py) `_on_process_finished` が「全てのタスクが終わりました」のモーダルを出す経路に載り、完了していないジョブへの虚偽通知になるため。この結果、検知時点では [戻る] / [停止] の状態が更新されないことを既知の制約とした。

**敵対的レビューで是正した点**: (1) 異常終了の検知が `_maybe_dump_console_log()` を呼んでおらず、既存の終了経路（キュー枯渇・fatal・停止要求）だけが実行ログ全文を保存する非対称があった。同じ後始末を行うようにし、回帰テストを追加した。(2) 利用者が [停止] を押した後にプロセスが終了した場合も `mark_aborted()` で「異常終了」と記録していた。停止要求時は `mark_all_done()` へ分岐させた。(3) RED テストが猶予の起点を検証しておらず、監視開始時刻を起点に実装しても通る偽陰性があったため、終了確認時刻が起点であることを直接検証するテストへ差し替えた。(4) テストが Step ノードを位置ではなくノード ID で特定していなかったため、レイアウト変更で別ノードを検証しうる状態だった。(5) 猶予の上限テストが定数単体しか見ておらず、検知が 500ms 周期のタイマーでしか走らないことを反映していなかった。実際の最大待ちである「猶予 + チェック 1 周期」が 10 秒以下であることを検証するよう強化した（実測 5.5 秒）。

**採用しなかったレビュー指摘**: 「猶予を待たず即座に停止すべき」は、プロセス終了後も `SubprocessReader` がバッファ済みの行を排出しており、即時判定が正常終了と競合するため採用していない。「ハングしたプロセスも検知すべき」は、プロセスが生存している間は「実行中」表示が事実に一致するため対象外とした。「早期 return で QA IPC マネージャがリークする」は、[hve/gui/qa_ipc_manager.py](hve/gui/qa_ipc_manager.py) が自身の 1 秒周期 `_check_subprocess` で終了を検知して `subprocess_terminated` を emit し、`_on_qa_subprocess_terminated` が `stop_and_cleanup()` する自己回復経路を持つため採用していない（本検知の 5 秒より先に走る）。「`stop_orchestrator()` で即座に `_is_running=False` にすべき」は、プロセスが実際に終了するまで True を保つのが既存の意図した振る舞いであり、本変更での回帰ではないため採用していない。

**検証**: `hve/gui/tests/test_dag_status_widget.py`（26 件）/ `hve/gui/tests/test_page_workbench_process_exit.py`（11 件）/ `hve/gui/tests/test_page_workbench_fatal.py`（20 件 + subtests 2）/ `hve/gui/tests/test_footer_elapsed_freeze.py`（8 件）/ `hve/tests/test_workbench_state.py`（17 件）が PASS。`hve/gui/tests` 配下の全 147 テストファイルをファイル単位で実行し、失敗 0 を確認した（`test_main_window_*` / `test_page_options_*` の一部は 1 ファイルあたり 70〜130 秒を要する）。`hve-dev/generate_tdd_inventory.py` を再実行し、FR-GUI-19 が `active-or-described` / `source=hve-dev/requirement-definition.md` として索引へ 1 行だけ載ること、新規テストがテスト索引へ 17 行登録されることを照合したうえで、`hve/tests/test_hve_surface_inventory.py` + `cq/tests/test_surface_export.py`（162 件）が PASS することを確認した。静的確認として、実装差分の追加行に `kind` / `hve:stats` を含む行が 0 件であることを確認した。

<!-- validation-confirmed -->


### Changed — GUI「実行ジョブ」タブを Visual Studio Code の [チャット] と同じ構成へ作り替えた（FR-GUI-18）

従来の実行ジョブタブは「対象ジョブの選択」「平坦なログ表示」「単行入力」「結果参照ボタン」の 4 段で、送信したメッセージ・受理結果・GUI の通知が、宛先の実行ログと同じ `QPlainTextEdit` へ区別なく流し込まれていた。自分が何をどの送信方法で送り、それが受理されたのかを、流れ続けるログの中から読み取る必要があった。VS Code のチャットビューは「会話列」「入力ボックス」「状態行」が分かれており、同じ並びへ揃えた。

- **会話ビューを新設した**（[hve/gui/widgets/chat_transcript.py](hve/gui/widgets/chat_transcript.py)）。送信メッセージ・ACK バッジ・GUI 通知・宛先の実行ログを 1 本の時系列列へ並べる。ACK は新しい行を足さず、対応する送信メッセージの右側へ `→ accepted` / `→ failed (詳細)` として付く。連続する実行ログ行は 1 つのブロックへまとめ、送信メッセージが入るとブロックが区切れる。
- **実行ログは加工せずそのまま提示する**（FR-GUI-13）。会話バブルにしてよいのは HVE 自身が発生源である送信メッセージ・ACK・通知だけで、ログ行を解析して発話者・役割・ターン境界を推定しない。`assistant:` のような役割らしい文字列を含む行を入れても、ログとして分類されたまま文字列が一字も変わらないことをテストで固定した。
- **入力ボックスを新設した**（[hve/gui/widgets/chat_input_box.py](hve/gui/widgets/chat_input_box.py)）。単行 `QLineEdit` を複数行入力へ置き換え、`Enter` で送信・`Shift+Enter` で改行する。行数に応じて高さが伸び、上限に達したらそれ以上伸びずにスクロールへ切り替わる。送信方法（キューに追加 / いま割り込む / 中断して送信）のセレクタと送信ボタンを同じ枠へ収めた。
- **コンテキスト添付を追加した**。`[+]` で選んだファイル・フォルダーがチップとして並び、`×` で個別に外せる。送信本文へ **パスだけ** を列挙し、ファイルを開いて中身を読むことはない（FR-GUI-14 と同じ方針）。既存の 8 KiB 入力上限は、添付を含めて組み立てた本文に対して判定する。
- **送信待ちキューを GUI から操作できるようにした**。[hve/job_interaction_ipc.py](hve/job_interaction_ipc.py) の `list_pending_requests` / `cancel_request` / `reorder_pending` は FR-GUI-12 の「未消費の要求に限り順序変更と取り消しを許可する」を実装済みだったが、**GUI から一度も呼ばれておらず、テストからの利用しかなかった**。未処理の要求があるときだけ現れるキュー欄を設け、`↑` / `↓` で処理順を入れ替え、`×` で取り消す。実行側が claim した要求は一覧から外れ、操作対象にならない。判定ロジックは GUI 側へ再実装せず既存 IPC を呼ぶだけとした（FR-MAINT-07）。
- **状態行を新設した**。宛先の状態・対話チャネルの可否・送信待ち件数を示す。実行ログの内容を再掲しない。
- **補助操作を `[⋯]` メニューへ集約した**。「会話をクリア」「会話をコピー」「結果を Copilot で開く」を置いた。会話のクリアは表示だけを消し、送信済みの要求・IPC チャネル・実行中のジョブへ影響しない。
- **モデル / reasoning effort のセレクタは作っていない**。実行中ジョブのモデルは `hve orchestrate` の起動時に決まり、`WorkflowInstance` / `JobTarget` はモデルを保持していないため、表示も切り替えもできる根拠が無い。チャットセッションのモデル選択は Copilot CLI を唯一の情報源とする既存方針（FR-GUI-10 / FR-MAINT-07）とも整合させた。セレクタが増えていないことをテストで固定した。
- **応答の停止ボタンも作っていない**。「実行中の応答だけを取り消す」に相当する送信方法が IPC に無く、`stop_orchestrator()` はジョブ全体の停止という別の操作になる。誤操作を誘発するため、送信ボタンの隣へ置かなかった。音声入力は Copilot CLI / HVE のどちらにも経路が無いため対象外とした。
- **公開 API は据え置いた**。`job_log_text()` / `send_job_message()` / `select_action()` / `on_job_log_line()` / `refresh_job_targets()` / `poll_acks()` の名前と意味を変えていないため、FR-GUI-12〜15 の既存受入テストのうち書き換えが必要になったのは、`_job_input` が単行 `QLineEdit` であることに依存していたアクセシビリティテスト 1 件だけで、残りは無改変で GREEN を維持している。その 1 件も、参照するウィジェットを新構成のもの（`⋯` ボタン・入力ボックスの各要素）へ差し替えただけで、検証している「主要操作がキーボードで到達でき読み上げ名を持つ」「`Enter` だけで送信できる」という内容は変えていない。送信の検証は `returnPressed` シグナルの直接発火から実キーイベントの送出へ変わり、キー処理経路そのものを通るようになった。

**敵対的レビューで是正した点**: (1) 要件へ書いた「等幅フォントで表示する」が既存実装と矛盾していた。[hve/gui/fonts.py](hve/gui/fonts.py) `preferred_log_font()` は Windows で日本語の可読性を優先して意図的に等幅を選ばない設計のため、「共有のログ用フォントを使う」という検証可能な表現へ直した。(2) 状態表示行と `[⋯]` メニューを実装する計画なのに要件へ書いておらず、トレースできない実装になっていたため要件へ追加した。(3) 要件の「入力欄が伸びすぎない」が検証不能だったため、上限に達したらスクロールへ切り替わるという観測可能な条件へ直した。(4) 要件に「実行中ターンの取り消しを提供してはならない」と書いており、将来 IPC 側に対応する action が追加されても禁止し続ける過剰な制約だったため、「ジョブ全体の停止を実行中の応答の取り消しとして提示しない」へ限定した。(5) タブ構成テストが `isVisibleTo(panel)` で可視性を判定しており、非アクティブなタブページでは常に `False` になるため判定が無効化されていた。親子関係とレイアウト順の検証へ置き換えた。(6) 状態行のテストが `"1" in text` という緩い部分一致で、他の数値にも当たり得たため、件数の表記そのものを照合するよう強めた。(7) 会話ビューの遅延スクロールを `QTimer.singleShot` + lambda で行っており、ウィジェット破棄後に発火すると削除済み C++ オブジェクトを触る（PySide でクラッシュする既知パターン）。バインドメソッド経由の呼び出しへ直した。(8) 入力欄の高さ更新が `height() != 目標値` を条件にしており、レイアウト適用前は毎回条件が成立して `setFixedHeight` を反復呼び出ししていた。保持した目標値との比較へ直した。(9) 垂直スクロールバーのポリシーを 2 か所で設定していた重複と、`QLabel.text()` をそのまま返すだけの `_NoticeEntry.text_value()` を削除した。(10) 送信可否ゲートのテスト 2 件が「送信方法の選択」を検証する `TestActionSelector` の配下にあり責務と一致していなかったため、`TestSendableGating` へ分離した。

**採用しなかったレビュー指摘**: 「実行ログも会話バブルにすべき」は、ログ行の解析による発話者・ターン境界の推定を必要とし、FR-GUI-13 が明示的に禁止しているため採用していない。「モデルピッカーを表示だけでも出すべき」は、宛先ジョブのモデルを保持しているデータ構造が無く、表示のために `JobTarget` / `WorkflowInstance` / orchestrate 引数へ新たな配線が必要になるため、本変更の範囲外とした。

**検証**: 新規 `hve/gui/tests/test_chat_transcript.py`（17 件）/ `hve/gui/tests/test_chat_input_box.py`（26 件）/ `hve/gui/tests/test_copilot_chat_panel_chat_ui.py`（25 件）、既存の `hve/gui/tests/test_copilot_chat_panel.py`（21 件）/ `hve/gui/tests/test_i18n.py`（22 件）を合わせた 111 件が PASS。Copilot パネルとジョブ対話に触れる既存テスト（`test_copilot_job_context.py` / `test_copilot_interactive_session.py` / `test_job_interaction_ipc.py` / `test_page_workbench_job_interaction.py` / `test_main_window_dock_integration.py` / `test_start_autopilot_chain_branch.py`）を加えた 210 件も PASS。`hve/tests/test_hve_surface_inventory.py`（146 件）も PASS。`hve-dev/generate_tdd_inventory.py` を再実行し、FR-GUI-18 が `source=hve-dev/requirement-definition.md` かつ `active-or-described` として feature 索引に載ること、新規テスト 3 ファイル（89 行）と新規実装面 2 ファイル（7 行）がテスト索引 / surface 索引へ登録されることを確認した。新規 `tr()` 文字列は `ChatTranscriptView` / `ChatInputBox` / `CopilotChatPanel` の 3 コンテキストとも [hve/gui/i18n/hve_gui_en_US.ts](hve/gui/i18n/hve_gui_en_US.ts) へ登録し、`lrelease` で `.qm` を再生成した（`type="unfinished"` が残らないことをテストで固定）。

**検証の制約**: `hve/gui/tests` の全件一括実行は、本変更の有無にかかわらず完走しなかった（新規テスト 3 ファイルを `--ignore` で除外したベースラインでも 39% で停滞）。本変更に起因する事象ではないため、影響範囲に絞った上記 210 件で回帰を確認している。

<!-- validation-confirmed -->


### Added — QA 起点 AKM に、メインタスクとは別のモデル / reasoning effort / context tier を選べるようにした（FR-QA-04 / FR-GUI-17 / FR-CLOUD-25）

実行前 QA を有効にすると、回答済み QA を `knowledge/` へ取り込む AKM がバックグラウンドで直列起動される（FR-QA-03）。この AKM は `knowledge/` の差分同期という定型作業に近い一方、従来はメインタスクの実行品質設定をそのまま引き継ぐしかなく、利用者が AKM だけを別モデルへ逃がす手段が無かった。CLI / GUI では [hve/qa_akm_dispatch.py](hve/qa_akm_dispatch.py) `QaAkmCoordinator._build_argv` がメインの `model` / `reasoning_effort` / `context_tier` を無条件で子プロセスへ転送しており、Cloud では [.github/workflows/auto-akm-after-qa.yml](.github/workflows/auto-akm-after-qa.yml) が作る AKM Root Issue の body にモデル節が無いため、[.github/scripts/bash/lib/extract-model.py](.github/scripts/bash/lib/extract-model.py) が常に空を返して `Auto` へ落ちていた。

- **CLI に `--akm-model` / `--akm-reasoning-effort` / `--akm-context-tier` を追加した**。いずれも未指定が既定で、未指定の項目だけ対応するメイン設定（`--model` / `--reasoning-effort` / `--context-tier`）を継承する。3 項目とも未指定なら子 argv は従来と同一で、`--akm-*` が子へ漏れることはない。継承の解決は `_build_argv` の 1 箇所だけで行い、メイン・敵対的レビュー・QA 質問票生成のセッション生成へは適用しない。`--workflow akm` を明示指定した実行は対象外で、従来どおり `--model` などに従う。
- **対話ウィザードで 3 項目を尋ねるようにした**。「QA 自動投入」を有効にした非 AKM ワークフローのときにだけ表示し、既定はいずれも継承。reasoning effort は `--reasoning-effort` が argparse に `choices` を持たない自由文字列であることに合わせて自由入力、context tier は `choices` があるためメニュー選択とした。
- **環境変数経路は新設しなかった**。継承元の `reasoning_effort` / `context_tier` 自体に環境変数経路が無く（[hve/config.py](hve/config.py) `SDKConfig.from_env` は `MODEL` / `REVIEW_MODEL` / `QA_MODEL` のみ）、4 つ目の入口を作ると優先順位規則が既存 2 項目と食い違うため。`AKM_MODEL` も 3 項目の指定方法を揃える目的で用意していない。
- **GUI は設定画面と Step 1 右ペインの双方へ表示した**。「一般 > 自動プロンプト」（C3）へ「AKM 用モデル」「AKM 用コンテキスト階層」を追加し、右ペインの「共通設定  *必須」枠にも常時表示する。reasoning effort はモデルと同じ行の **Effort** で選ぶ。「QA 自動投入」が「有効にする」以外のときは 3 項目とも非活性化し、`OrchestrateArgs` へも値を渡さない。
- **GUI のモデル行構築を単一実装へ寄せた**（FR-MAINT-07）。モデル + Effort + Context size + Cost の行構築と Effort 再評価は `_C1Basic` のメソッドだったが、`_C3AutoPrompt` からも使うためモジュール関数（`_build_model_effort_row` / `_populate_main_combo` / `_populate_secondary_combo` / `_refresh_effort_row`）へ抽出し、`_C1Basic` は委譲に変えた。モデルキャッシュ更新時の再投入漏れを防ぐため、`MainWindow` は `c1.reload_models()` と同時に `c3.reload_models()` も呼ぶ。
- **Cloud はモデルのみを継承させた**。Knowledge Management を除く 9 つの Issue Template へ `akm_model` ドロップダウンを追加し、`save-qa-answer` job が `### AKM 用モデル` 節を許可リスト照合付きで抽出、`dispatch-akm` job が dispatch 入力へ渡し、調整 Workflow が同じ許可リストで再検証したうえで Root Issue body の `### 使用するモデル` 節へ必ず書き込む。未指定・不正値でも `Auto` へ丸めて Workflow を失敗させない。**Cloud 面には reasoning effort / context tier に相当する設定が存在しない**（`.github/` 配下で `reasoning_effort` に一致するのは Azure AI Search の `retrievalReasoningEffort` のみで別概念）ため、Cloud はモデルだけを対象とした。
- **`knowledge-management.yml` には `akm_model` を追加していない**。AKM Root Issue から別の QA 起点 AKM を再帰生成しない既存契約（FR-QA-03 / FR-CLOUD-24）に合わせた。

**敵対的レビューで是正した点**: (1) `copilot-assign.sh` に追加した `extract_akm_model()` が、`save-qa-answer` の python3 直呼びによってデッドコードになっていた（同一ルールの 2 重実装）。既存 4 workflow と同じ `source` パターンへ統一し、python3 直呼びの再発を `assertNotIn` で検出する回帰テストを追加した。(2) 新規 `tr()` 文字列が [hve/gui/i18n/hve_gui_en_US.ts](hve/gui/i18n/hve_gui_en_US.ts) へ未登録で、既存の「レビュー用モデル」「QA 用モデル」が翻訳済みなのに AKM 用だけ英語ロケールで日本語のまま残っていた。`_C3AutoPrompt` 6 件と `help_content` 3 件を登録し `lrelease` で `.qm` を再生成、実機で英訳が引けることを確認した。(3) 「3 項目が右ペインへ可視」の受入ケースのうち effort だけ全ワークフロー網羅テストが無かったため追加した。(4) **3 面のオプション対応表 [hve/tests/fixtures/option_parity_matrix.yaml](hve/tests/fixtures/option_parity_matrix.yaml) への登録が漏れており**、`test_phase6_option_parity.py` の 2 件が失敗していた。`akm_model` を `options`（Issue Form ID 対応あり）へ、Cloud に対応概念が無い `akm_reasoning_effort` / `akm_context_tier` を `sdkconfig_internal_fields` へ登録した。(5) 継承規則が `SDKConfig.get_akm_model()` と `_build_argv` の 2 箇所にあったため、`_build_argv` を `get_akm_model()` 経由へ統一した（FR-MAINT-07）。(6) 後方互換テストが `SDKConfig` 既定から自明に真となる比較しか行っていなかったため、`--akm-*` が子 argv へ漏れないことを直接検証するテストへ置き換えた。(7) `extract-akm-model.py` の見出し正規表現が前方一致で `### AKM 用モデル<別語>` にも当たり得たため、Issue Form の label と完全一致させ `extract-model.py` と同じ厳格さへ揃えた。(8) `_C3AutoPrompt` で `auto_qa` のシグナル接続が AKM ウィジェット生成より前にあり、将来の初期値設定追加で `AttributeError` になる順序依存だったため、生成後に接続する順序へ直した。

**採用しなかったレビュー指摘**: 「AKM 欄が Step 1 右ペインに表示されるのは UI 崩れ」は、右ペインへの表示が本変更の要件そのもの（FR-GUI-17）のため採用していない。「既存 AKM Root Issue を再利用すると `akm_model` が無視される」は、同一 `qa-sha` で Root Issue を再作成しない既存の冪等性契約（FR-CLOUD-24）に由来し、`auto_merge` と同じ挙動のため本変更では変えていない。

**検証**: `hve/tests/test_qa_akm_model_selection.py`（16 件）/ `hve/tests/test_main.py`（252 件 1 skip）/ `hve/tests/test_issue_template_qa_parity.py`（30 件 + subtests 64）/ `hve/gui/tests/test_page_options_akm_model.py`（18 件）/ `hve/tests/test_phase6_option_parity.py`（57 件 + subtests 207）/ `hve/gui/tests/test_i18n.py` / `.github/scripts/tests/test_validate_hve_requirement_traceability.py` + `hve/tests/test_hve_surface_inventory.py`（174 件 2 skip）がいずれも PASS。`hve-dev/generate_tdd_inventory.py` を再実行し、FR-QA-04 / FR-GUI-17 / FR-CLOUD-25 が `active-or-described` として索引へ載ることと、新規テストがテスト索引に登録されることを確認した。

<!-- validation-confirmed -->


### Fixed — graphrag 索引を実際に構築・運用できるようにした（FR-GUI-05）

`graphrag` は任意依存として用意されていたが、環境を整えても実データでは索引が構築できなかった。原因は LightRAG がプロセス単位・並列前提で設計されているのに対し、mdq がそれを 1 プロセス・逐次の運用へ組み込んでいたことにある。いずれも実測で切り分けた。

- **同一プロセスでの完全再ビルドが索引を破壊していた**。LightRAG は storage 状態をプロセス単位で保持するため、1 度ビルドしたプロセスで再ビルドすると、初期化済みの storage が新しい作業ディレクトリへ書き戻されず、成功報告のまま索引が 10 ファイルから 1 ファイルへ落ちていた（実測）。GUI は 1 プロセスで「完全再ビルド」を繰り返すため、この経路が実運用のパターンになる。セッション開始時に共有状態を破棄し、新規プロセスと同じ状態から始めるようにした。
- **成功していない文書を成功として数えていた**。`ainsert` は文書単位の抽出失敗を内部で捕捉して送出しないため、呼び出しが返ったことを根拠に成功と見なしていた。実測では LightRAG が `status=failed` と記録した文書を `files_ok` に計上していた。エンジンが記録した実際の状態を読み取り、`documents_processed` / `documents_failed` として要約と GUI へ提示するようにした。
- **モデルの初回読み込みが後続要求のタイムアウトを食い潰していた**。Ollama は初回呼び出しでモデルを読み込む（7B で実測約 2 分）。LightRAG は抽出呼び出しを並列に発行し Ollama は既定で 1 件ずつ処理するため、読み込みが待ち行列の中に入ると後続要求が時間切れになる。セッション開始時に 1 度だけ読み込みを済ませるようにした。あわせて既定タイムアウトを LightRAG 自身の実行タイムアウトと同じ 240 秒へ揃えた（従来 120 秒）。
- **LightRAG の並列度を Ollama の直列処理へ合わせた**。LLM 呼び出し 4 並列・文書 3 並列という既定は、`OLLAMA_NUM_PARALLEL=1` の環境では待ち行列を作るだけで実効スループットを上げない。待ち時間が各要求のタイムアウトに算入されて失敗するため、双方を 1 へ揃えた。
- **タイムアウト設定が LightRAG へ伝わっていなかった**。mdq は HTTP 要求のタイムアウトだけを設定しており、LightRAG が自身の実行タイムアウト（LLM 240 秒 / 埋め込み 30 秒）で先に打ち切るため、`--graphrag-timeout` を延ばしても効果が無かった。LLM・埋め込みの双方について、設定値を LightRAG の実行タイムアウトへ渡すようにした。
- **既定タイムアウトを実測に基づき 1200 秒へ引き上げ、GUI からも調整できるようにした**。240 秒（LightRAG 自身の既定）では本リポジトリの文書で抽出が時間切れになる。CLI には `--graphrag-timeout` がある一方 GUI には調整手段が無く、GUI からは失敗を回避できなかったため、基本タブへ graphrag 専用設定を追加した（semantic_paragraph / pageindex と同じ構造）。設定値 0 は「コード側既定を採用」の意で、GUI 側へ既定値を複写しない。
- **索引の存在判定と結果表示の規範を要求定義へ追加した**。ディレクトリの存在だけで構築済みと判定しないこと、構築 API が例外を送出しなかったことだけを根拠に成功件数へ計上しないことを明文化した。
- **セットアップに opt-in の `-Graphrag` / `--graphrag` を追加した**。`graphrag` は pandas を 2.4 未満へダウングレードし別途 Ollama を要するため既定では導入しないが、指定すれば再現可能に構築できる。`-Minimal` と併用した場合は無視される旨を警告する。あわせて `setup-hve.sh` の `usage()` がヘッダー途中で切れていた行範囲を修正した。

**実測（2026-08-14、Windows 11 / Python 3.14.7 / qwen2.5:7b + nomic-embed-text / CPU）**: `lightrag-hku 1.5.6` は mdq が使う API（`LightRAG` / `EmbeddingFunc` / `QueryParam`、`ainsert(file_paths=)` / `aquery(param=)` / `initialize_storages` / `finalize_storages`）をすべて備え、`import lightrag` は pip を起動しない。埋め込み次元 768。生成スループット 27.8 tokens/sec、プロンプト処理 1233.8 tokens/sec。小規模文書 3 件はウォーム状態で 18.4 秒（6.1 秒/ファイル）。実リポジトリでは `template/atdd-template.md`（2260 文字）が 107.8 秒で 36 node / 30 edge を抽出。検索は `local` 61.0 秒 / `naive` 28.9 秒で出典つきの回答を返す。`pandas` は 3.0.3 から 2.3.3 へ下がるが、`Required-by` は空でリポジトリ内に `import pandas` は無い。同時に入る `configparser` は `backports/` 配下のみで標準ライブラリを隠蔽しない（wheel 実体で確認）。

**タイムアウトの実測（同上の環境）**: `template/business-requirement-document-master-list.md`（17,597 bytes / 5 chunk）で計測した。240 秒では、タイムアウトを延ばしても LightRAG 側が先に打ち切るため必ず失敗した。伝播修正後は、**1200 秒（新しい既定値）でも chunk 2/5 の gleaning 呼び出しが超過して失敗**し（1712.0 秒で `documents_failed=1`）、**1800 秒では成功**した（2931.8 秒 / 148 node / 107 edge / `documents_failed=0`）。すなわち本リポジトリの大きい文書は既定値のままでは通らない。これが GUI へ調整手段を設けた理由であり、`documents_failed` が出た場合はこの値を増やして再実行する運用を前提とする。

**既知の制約**: 抽出速度はローカル LLM の生成性能に律速される。大きな文書ほどチャンク数に比例して時間がかかるため、リポジトリ全体の索引化は相応の実行時間を要する。失敗した文書は `documents_failed` に現れるので、GUI の「LLM タイムアウト」または `--graphrag-timeout` を増やすか、より小さい・速いモデルへ切り替えて再実行する。

<!-- validation-confirmed -->


### Fixed — GUI「今回の実行履歴」の統計を Step 単位で分離した（FR-RTO-07）

統計情報ウィンドウの「今回の実行履歴」で、並列 Wave の Step 群が Context・実行時間まで完全に同値となり、AI Credit・Tools・Skills は全て `-` になっていた。Workflow 親行の Context とモデルも最後に完了した Step の値の複製だった。実行ログ（`observability/events-<pid>.jsonl` 5,713 件）で表示値を再現した結果、原因は 2 つに分かれた。

- **SDK Fleet mode へ委譲した並列 Wave の課金消費を計上するようにした**。`DAGExecutor` は Wave 内の Step が 2 個以上のとき Fleet へ委譲するが、Fleet セッションのイベントを受ける `FleetEventCollector` は表示転送しか行わず、観測イベントを 1 件も発火していなかった。そのため当該 Wave の Step は `step_status` 以外の観測イベントを持たず、AI Credit は Step 別内訳だけでなく **Workflow 累積からも欠落**していた（実測: Step 帰属の総和 4,921.80 AIU に対し 14 並列 Wave と 2 並列 Wave の消費が未計上）。`assistant.usage` から `usage_credit` を発火して計上する。
- **Fleet worker の消費を Step へ帰属させるようにした**。SDK の `SubagentStartedData` は Step 識別子を持たないが、sub-agent を起動した tool call の引数には Fleet prompt が書いた `Step.<step_id>` が含まれ、`AssistantUsageData` / `ToolExecutionStartData` は `parent_tool_call_id` を持つ。`_build_fleet_wave_runner` から Wave の Step 集合を `FleetEventCollector` へ注入し、起動 tool の引数と照合して `tool_call_id` → `step_id` を解決する。一致が当該 Wave の Step 集合に対して一意に定まるときだけ帰属させ、 0 件・複数件一致・集合未注入のいずれでも割り当てない（`Step.2` が `Step.2/APP-001` へ前方一致しないよう境界を見る）。解決できた worker は `usage_credit` と `tool_invoked` を当該 Step へ発火し、解決できなければ `usage_credit` を `step_id=""` で発火して累積にだけ計上する（`tool_invoked` は誤帰属を避けて発火しない）。解決に用いた tool 引数は観測イベントへ含めない（FR-RTO-04）。
- **課金値の抽出を単一実装へ寄せた**（FR-MAINT-07）。`copilotUsage.totalNanoAiu` / `apiCallId` / `cost` の抽出は `runner.py` の `assistant.usage` ハンドラ内にインライン実装されていた。Fleet 経路と重複実装にならないよう `runtime_observability.extract_usage_credit_fields` へ切り出し、両経路が共有する。返却値は課金 5 項目に限定し、本文系フィールドを含めない（FR-RTO-04）。
- **Step の Context・AI Credit・モデルを Step 帰属イベントだけから算出するようにした**。`WorkbenchState` が Step 別に保持していたのは Tools と Skills だけで、Step スナップショットは Context・モデル・AI Credit をグローバル現在値と Workflow 累積からコピーしていた。そのため同時完了する並列 Step は必ず同値になっていた。`session_usage_detail` / `usage_credit` / `assistant_usage` の `step` フィールドで Step 別バケットへ振り分ける。`step` が空のイベントは実行中 Step へ代替帰属させない。
- **AI Credit の Step 表示を累積差分から実測値へ変えた**。従来は完了時刻順で隣接する Step の Workflow 累積の差を表示しており、同時完了する並列 Step は差分 0 で必ず `-` になっていた。当該 Step へ帰属した `usage_credit` の合計を表示する。帰属イベントが無い Step は `-` のままとし、累積差分などの推定値で補わない。CSV の `AiuDeltaSincePrev` 列は `AiuOwn` 列へ置き換えた。
- **モデル列をモデル別呼び出し回数にした**。1 つの Step が事前 QA サブセッションで別モデルを併用するため、単一のグローバル値では実態と乖離していた（実測: Step 4.1 は `claude-opus-5` 68 回 + `gpt-5.6-terra` 27 回）。記録元は `usage_credit` とし、Fleet 経路でもモデル列が埋まるようにした（`assistant_usage` と `usage_credit` は 1 API call につき 1:1 で発火されることを実測で確認した — 451 件 vs 451 件）。Tools / Skills と同じ Top-5 表記で表示し、セルのダブルクリックで全件を表示する。
- **`run_id` 未確定期間の実行が 2 行に分かれる問題を修正した**。GUI は `run_id="unknown"` で状態を初期化し、子プロセスが `[hve] run_id=` を出力した時点で確定させる。確定時に別実行と判定して直前のスナップショットを finalize していたため、Step を 1 件も持たない空の Workflow 行が残っていた。プレースホルダの間に届いた実 `run_id` は同一実行として in-place で更新する。
- **列の意味を凡例とツールチップで明示した**。Workflow 行の AI Credit は Step へ帰属できない Wave の消費を含む累積のため子 Step の合計と一致しないこと、Workflow 行の Context は瞬間値のため最後に完了した Step の値であること、並列 Wave の Step の実行時間は Wave 全体の所要時間であることを示す。

**既知の制約**: Fleet へ委譲した Wave の Step は、Context と Skills の Step 別内訳を引き続き `-` と表示する。SDK の `SessionUsageInfoData` と skill イベントは `parent_tool_call_id` を持たず、worker との対応を解決できないためである。実行時間も Wave 全体の所要時間のままとなる（`SubagentCompletedData.duration` は存在するが、Step 完了時刻は parent 側の Wave 終了で確定するため、スナップショットの経過時間とは基準が異なる）。いずれも推定で補わず、取得不能の事実を凡例とツールチップで示す。

**検証**: RED 46 failed / 88 passed → GREEN。Fleet の Step 帰属（引数照合・境界一致・到着順序・引数非保存・`step_ids` 未注入時の後方互換）を RED 10 failed → GREEN で固定した。影響範囲のテスト（stats 系 3 ファイル / `test_stats_detail.py` / `test_footer_stats.py` / `test_runtime_dashboard_state.py` / `test_fleet_mode.py` / `test_runtime_observability*.py` / `test_workbench_observability.py` / `pricing/` / 索引整合）で 346 passed、[hve/tests/test_runner.py](hve/tests/test_runner.py) で 205 passed、i18n で 21 passed。GUI 全体回帰は **1,436 passed / 1 skipped / 失敗 0**（1:29:52）。前回の全体回帰で失敗していた 4 件（`cq` のパーサ表示 1 件と CI/CD 認証検証 3 件）は、並行作業の完了に伴っていずれも解消していることを確認した。削除した `_step_aiu_delta_nano` / `_compute_step_prev_map` / `AiuDeltaSincePrev` の残存参照は 0 件。要求定義に `FR-RTO-07` を追加・改訂し、要求テストマッピングの 38 件がすべて実在テストと一致することを機械照合し、索引 CSV を再生成して `active-or-described` として登録されていることを確認した。

<!-- validation-confirmed -->

### Fixed — Markdown-Query GUI が全 chunking strategy の索引を作成しない問題を修正した（FR-GUI-05）

GUI の「選択 Strategy を一括ビルド」を実行しても、`graphrag` は空の SQLite が残るだけで本来の索引が作られず、未ビルドの strategy が統計表では「DB 有り 0/0」と表示されていた。原因は索引の**構築経路**と**存在判定**の 2 つが SQLite 前提に固定されていたことにある。

- **GUI の索引構築を CLI と同じ実装へ配線した**。`graphrag` は LightRAG が索引を所有し SQLite を使わないが、GUI 経路は strategy を問わず `mdq.indexer.build_index` を呼んでおり、`mdq.indexer.build_graphrag_index` の呼び出し元は `mdq/cli.py` の 1 箇所しかなかった。その結果、chunk を 1 件も持たない SQLite が生成され、本来の作業ディレクトリは作られなかった（実測 2026-08-13: `index-ja-jp-graphrag.sqlite` に 110 files / 0 chunks、`.mdq/graphrag-ja-jp/` は不在）。GUI からも同じ構築関数へ委譲し、完全再ビルドと進捗通知も伝播するようにした。任意依存 `[graphrag]` が未導入の場合は失敗として提示され、空の索引を残さない。
- **統計取得が索引を作る副作用を止めた**。`get_index_stats` は索引の有無に関わらず `mdq.store.open_store` を呼んでおり、これはファイルを物理生成する。GUI 起動・Strategy 切替・DB 削除直後の再描画だけで空の DB ができ、未ビルドと「ビルド済みだが空」を区別できなくなっていた（実測: `index-ja-jp-heading_recursive.sqlite` が 64 KB / 0 files / 0 chunks で生成）。未生成時は索引へ触れずに報告する。同じ規範は Code-Query 側（FR-GUI-04）では既に明文化されており、Markdown-Query 側の欠落を塞いだ。
- **索引の実体パスを strategy ごとに解決するようにした**。作業ディレクトリのパス規則を `mdq.store.graphrag_dir_for` の単一実装にまとめ、CLI と GUI の双方が参照する。存在判定・削除・統計はいずれも当該 strategy の実体を対象とするため、`graphrag` の索引が SQLite の有無で誤判定されない。
- **計測できない値を 0 と表示しないようにした**。LightRAG は SQLite 索引と同じ粒度のファイル数・チャンク数を持たないため、統計表と統計パネルでは `-` を表示する。あわせて `graphrag` のビルド結果サマリーを LightRAG が返す項目で表示し、説明文の「各 Strategy は別 DB ファイルに保存されます」という記述を実態に合わせた。
- **失敗したビルドが残す空ディレクトリを「索引あり」と誤判定しないようにした**。`build_graphrag_index` は LightRAG を呼ぶ前に作業ディレクトリを作るため、任意依存 `[graphrag]` が未導入の環境ではビルドが失敗しても空のディレクトリだけが残る。ディレクトリの存在だけを見ると、修正対象そのものである「未ビルドなのに有りと表示される」状態が `graphrag` で再現していた。LightRAG が生成するファイルの有無で判定するようにし、その判定規則を `mdq.indexer.has_lightrag_index` の単一実装へまとめて索引構築側の安全確認と共有した。
- **strategy の配線漏れが必ず検出されるようにした**。既存の一括ビルド試験はスレッドをテストダブルへ差し替えており、実際の索引が生成されるかを検証していなかった。`ALL_STRATEGIES` 全件を対象に索引実体の生成を検証する試験を追加したため、今後 strategy を追加して構築経路へ配線し忘れた場合は必ず失敗する。

**影響**: GUI からの索引運用のみに影響する。`mdq` CLI の挙動、索引スキーマ、検索結果は変更していない。既存の `.mdq/index-<lang>-graphrag.sqlite` は参照されなくなるため、手動で削除してよい。

**`graphrag` の利用可否（2026-08-14 実測）**: 本リポジトリの `.venv` では `graphrag` は**利用できない**。`lightrag-hku` が未導入（`pip show` で not found、`import lightrag` が失敗）で、LightRAG の依存 `nano_vectordb` / `networkx` も無い。LLM 実行基盤の Ollama も未導入で（PATH・`%LOCALAPPDATA%\Programs\Ollama` のいずれにも存在せず、プロセスも無い）、既定の `http://127.0.0.1:11434` は接続拒否となる。この状態でビルドすると `GraphRAGUnavailable: LightRAG is not installed` で失敗し、SQLite 索引も統計上の「索引あり」も残らない。利用するには `pip install -e .[graphrag]`（`pandas` が 2.4 未満へダウングレードされる）と Ollama の導入・起動、および既定モデル `qwen2.5:7b` / `nomic-embed-text` の取得が必要である。

**検証**: RED 18 failed → GREEN、追加修正で RED 3 failed → GREEN。`mdq/gui/tests/` 55 passed、`mdq/` エンジンと mdq 関連 HVE テストをまとめて 440 passed、`MdqIndexSection` を構築する HVE GUI テスト 40 passed。既存失敗 4 件は本変更の対象外であることを確認した — `mdq/tests/test_golden_eval.py` の 3 件は並行作業による `docs/catalog/data-model.md` の見出し再構成に起因し（作業ツリーと `HEAD` を突き合わせて確認）、`hve/gui/tests/test_cq_settings_section.py` の 1 件は Code-Query のパーサフィデリティ表示に関するもので `cq/` に未コミット変更が 1 件も無い状態で再現する。要求定義・要求テストマッピングを更新し、索引 CSV を再生成した。

<!-- validation-confirmed -->

### Added — GUI に GitHub Copilot の常設対話と実行ジョブ連携を追加した（FR-GUI-10〜15）

GUI の Copilot パネルは、これまで単発のプロンプト送信しかできなかった。実行中のジョブへ指示を出すことも、終わったジョブの結果を見ながら相談することもできず、利用者は GUI とターミナルを往復していた。Copilot の対話機能そのものを再実装するのではなく、GitHub Copilot CLI の対話セッションを GUI へ埋め込み、HVE 固有のジョブ連携だけを足す方針で解決した。

- **Copilot CLI の対話セッションを常設した（FR-GUI-10）**。既存の PTY backend と xterm ビューの上で `copilot` を 1 プロセスとして起動・維持するため、会話の文脈が失われない。`/model` `/agent` `/plan` `/context` `/compact` `/fork` `/resume` `/diff` `/review` `/mcp` `/plugin` `/skills` `/permissions` など、CLI が提供するコマンドはそのまま使える。HVE は CLI の出力を解釈せず、チャット内容を別途保存しない。
- **権限緩和フラグを付けない設計にした（FR-GUI-11）**。起動 argv は作業ディレクトリ指定と自動更新抑止のみで、`--allow-all-tools` / `--allow-all-paths` / `--yolo` / `--no-ask-user` / `-p` を一切渡さない。ツール実行の可否判断は CLI の対話プロンプトに残り、方針変更は `/permissions` で行う。CLI または OS 別 PTY backend が解決できない場合はセッションを起動せず、OS 別セットアップ導線を案内する（fail-closed）。
- **実行中ジョブへ 3 種類の送信方法を追加した（FR-GUI-12）**。「キューに追加」は現在の応答完了後に順次処理し、「いま割り込む」は実行中ターンへ即時に割り込み、「中断して送信」は実行中ターンを中断して新しいターンとして実行しその応答をステップ結果とする。並列実行時は対象ジョブを一覧から明示選択するため、宛先を取り違えない。
- **送信の受理・失敗を利用者が確認できるようにした**。送信経路はファイル IPC（schema v1）へ一本化し、Runner は要求ファイルを原子的にリネームして取得する。ACK には要求 ID・送信方法・状態・詳細だけを載せ、送信本文を決して含めない。「中断して送信」の ACK は実送信が成立した時点まで遅らせ、送信前にステップが終了した場合は失敗として通知するため、指示が無言で失われない。
- **完了したジョブの結果を Copilot で開けるようにした（FR-GUI-13）**。実行ディレクトリ・コンソールログ・完了レポート・成果物のうち、実在が確認できたものの**パスだけ**を初期メッセージに載せて新しいセッションを開始する。ファイル本文は埋め込まず、実行ルート外は探索しない。セッション作業フォルダーのクリーンアップが `purge` の場合は GUI 終了後に参照先が残らないため、実行後に相談する運用では `keep` または `archive` を選ぶ。
- **GUI の実行インスタンスごとに独立した IPC チャネルを割り当てた（FR-GUI-14）**。通常実行・Autopilot チェーン・事前フェーズのいずれの起動経路でも、他インスタンス宛の指示が混線しない。既存の Steering 経路は共通 IPC へ委譲する後方互換 wrapper とし、要求ファイル名も従来と互換を保った。
- **パネル全体を英語表示に対応させ、主要コントロールに支援技術向けの名前を付けた（FR-GUI-15）**。

**検証**: FR-GUI-10〜15 の各契約を RED → GREEN で確認した。新規・関連スイート 11 ファイルで **173 passed / 1 failed**。失敗 1 件（`test_copilot_sdk_lock_pins_an_exact_version`）は本変更が触れていない SDK lock ファイルの改行コードに起因する既存不具合で、変更前の HEAD を別 worktree に取り出して同一環境で実行しても同じく失敗することを確認済み。3 OS の実 PTY / 実 CLI smoke を CI（`gui-pty-tests`）へ組み込み、CLI 未解決時に skip で無言に消えないよう fail-closed にした。要求定義・要求テストマッピング・索引 CSV を再生成し、FR-GUI-10〜15 が `active-or-described` として登録されていることを照合した（索引整合 123 passed）。

<!-- validation-confirmed -->

### Fixed — Pre-QA の複数行 Work IQ 応答で回答済み QA が壊れる問題を修正した（FR-QA-03）

- Work IQ 応答を含む Markdown table cell を単一物理行へ正規化し、保存後も質問数と全回答を保持するようにした。
- Work IQ tool の実行を server/tool の組で確認し、`FOUND` / `PARTIAL` だけを回答済み QA へ統合するようにした。
- tool 未確認、`NOT_FOUND`、`UNAVAILABLE`、status 不明の応答は検証済み QA へ混ぜず、未確認 draft だけに保持する。

### Changed — Agent の実行入力から `users-guide/` を排除し、Prompt 本文を Single Source of Truth に一本化した

ARD と AAG の Agent は、実行時に `users-guide/01-business-requirement.md` / `users-guide/08-ai-agent.md` を「必ず参照」と指示されていた。`users-guide/` は利用者向けの手動実行ガイドであり、Agent の実行入力に混ぜると出力仕様が二重管理になる。実際 ARD では両者が既に乖離しており（`1.3` 節の見出し名、調査期間が `過去30年間` 固定かパラメータか）、どちらが正かを実行時に判定できない状態だった。Agent が実行入力として参照するドキュメントを `docs/` と Prompt 本文へ限定した。

- **ARD 3 Prompt の `users-guide` 必読指定を削除した**。ARD の Prompt は元々 §4 に本文全文を内包しており、外部参照は冗長かつ矛盾していた。§4 を SoT と明記した。
- **AAG 3 Prompt は自己完結していなかったため、委譲していた規則を本文へ取り込んだ**。Step 1 に固定見出し構成と TIME-BOX / MODE SWITCH 条件、Step 2 に MODE SWITCH 規則、Step 3 に完成判定 15 項目と分割規則を移設した。
- **io-contract 16 件から `kind: static` の必須入力を削除した**（ARD 7 / AAG 7 / DataDeploy 2）。併せて `io-contract-exceptions.yaml` の `static_paths` 2 件を削除した。この 2 件は `check_integrity` が `kind: agent_artifact` だけを対象とするため、そもそも効果の無い設定だった。
- **Body テンプレート 8 件からも参照を削除した**（`aag` 3 / `aad` 3 / `aagd` 1 / `asdw` 1）。テンプレートは実行時プロンプトへ展開されるため、ここを残すと Prompt 側の修正が無効化される。敵対的レビューで検出した。
- **`docs/` 配下の既存成果物 5 ファイル 15 箇所の出典を、実際の SoT である Prompt 本文へ差し替えた**。成果物は後続 Step の入力にもなるため、stale なポインタを残すと Agent が再び `users-guide/` を読みに行く余地が残る。
- `users-guide/01-business-requirement.md` と `users-guide/08-ai-agent.md` の Prompt ブロックに「手動実行用であり ARD / AAG の SoT ではない」旨を明記した。
- **Agent が読み込む残りの面からも参照を除去した**。`templates/aas/step-2.md` の手順参照を「ユーザーが用意する入力ファイル」という意味だけに改め、`code-query` Skill の extras 一覧参照を実際の宣言元である `pyproject.toml` の `[project.optional-dependencies]` へ、`markdown-query` Skill のレポート指標参照を `mdq.usage_stats` / `mdq.usage_report` へ向け直した。`code-query` は配布キット側のコピー（`tools/skills/code_query/skill/SKILL.md`）も byte 一致を保つよう同期した。

### Fixed — ARD の `target_business` 自動生成が機能しない問題を修正した

`target_business` 未指定時に Strategic Recommendation から値を生成するフックが、実 Step `1` の完了時に発火する一方で、読み取り先は Step `1.2` の出力 `docs/company-business-requirement.md` だった。クリーン実行では当該ファイルがまだ存在せず、警告を出したうえで `target_business` が空のまま Step 2 が実行されていた。

- **フックの発火点を Step `1.2` 完了時へ移した**。併せて bridge mode の直列化条件と依存注入先を `1` → `1.2` へ変更し、Step 2 が SR 抽出元より先に走らないようにした。依存先が Step 2 の既存 `skip_fallback_deps=["1.2"]` と一致するようになった。

### Fixed — GUI で ARD グループ 1 と 2 の同時実行が precheck にブロックされる問題を修正した

orchestrator の bridge mode と CLI ウィザードは、グループ 1 を併せて実行する場合に `target_business` を必須としない。一方 GUI の Step 1 precheck はグループ 2 の `target_business` を無条件に必須としていたため、**bridge 経路が GUI からは到達不能** だった。

- グループ 1 が選択されている場合、グループ 2 の `target_business` を precheck 対象から除外した。グループ 2 を単独で選んだ場合の必須判定は従来どおり維持している。
- 「業務エリア」欄の説明が旧 Step 構成（`Step 1 → 2 → 3`）のままだったため、現行の必須条件へ修正し英訳も同期した。

### Fixed — ARD の Step 1 と成果物の責務、および文書の誤記を修正した

- **Untargeted Prompt に Step 別スコープ指示を追加した**。同 Prompt は Step `1` / `1.1` / `1.2` で共用されるが、本文が Step を問わず第 1〜7 章の全社レポートを要求していたため、「候補一覧」であるべき Step 1 の出力が Step 1.2 と重複する構造だった。Step 1 は `BIZ-NN` 候補表に限定し、全社レポートは Step 1.2 専用と明記した。
- `Arch-ARD-UseCaseCatalog` の出力先テーブルが旧 Step 番号 `4.1` / `4.2` / `4.3` のままで、registry の `3.1` / `3.2` / `3.3` と一致していなかったため修正した。Prompt は実行時に注入されるため、Agent が Step 番号を誤認する経路になっていた。
- `templates/ard/step-1.md` が `company_name` を「（任意）」と記載する一方、CLI / GUI / precheck は必須として扱っていたため「（必須）」へ統一した。
- `users-guide/workflow-reference.md` の ARD ステップ表で `3.1`〜`3.3` が「グループ 3」と誤記されていた（正しくはグループ 4）。表示グループの注記も `1 / 2 / 2.1 / 3` から `1 / 2 / 3 / 4` へ修正し、展開規則の正本を併記した。
- 同ファイルの GUI precheck 説明が「代表エントリステップ 1 件のみを評価」となっていたが、実装は最優先ワークフローの全選択 Step のファイル要件と全ワークフローの `required_params` を評価する。実装に合わせて修正した。

**検証**: `validate-io-contract.py` が 126 Agent / schema・integrity・registry いずれも 0 error。ARD 系 94 件、AAG/AAGD 契約系 116 件、GUI 要件系 76 件が PASS。Phase C / D は RED を確認してから実装した。`hve/tests` 全件実行で 7549 passed / 9 failed となったが、`git worktree` で HEAD を別ツリーへ取り出して同一環境で実行しても同じ 9 件が同様に失敗することを確認済みで、いずれも本変更が触れていない領域（生成済み Azure スクリプト、SDK lock の改行コード、AQOD Work IQ、未配置の SWA workflow）に起因する既存不具合である。`hve-dev/generate_tdd_inventory.py` を再実行し索引 CSV を更新した（`test_hve_surface_inventory.py` 146 件 PASS）。

**意図的に変更していない参照**: `markdown-query` Skill が記述する索引対象ルート（`mdq.config.GENERIC_DEFAULT_ROOTS` と `mdq.toml` の宣言内容）と `work-artifacts-layout` Skill の恒久成果物一覧は、いずれも実装・設定の事実記述であり、文面だけを書き換えると誤った記述になる。検索索引の対象範囲を変えるには別ライフサイクルで版管理される `mdq` パッケージ側の判断が必要なため、本変更の範囲外とした。Issue Template の `users-guide/` 参照は `dropdown` / `markdown` の表示専用ブロックにあり Issue body へ入らないため Agent 入力ではなく、`preflight-cloud-setup.sh` のメッセージ、GUI ヘルプ（`help_content.py`）、エクスプローラー既定値も人間向けナビゲーションのため据え置いている。

<!-- validation-confirmed -->

### Changed — 原本ドキュメント格納先を `original-docs/` から `docs-original/` へ改称した

リポジトリ直下の原本ドキュメント格納先が `original-docs/` だけ命名規則から外れており、`docs/` `docs-generated/` と並べたときの一覧性が悪かった。ディレクトリ実体を `git mv` で `docs-original/` へ移動し、リポジトリ全体のパス参照を追随させた。**HVE の入出力契約・ワークフロー挙動・成果物フォーマットに変更はなく、参照先パスだけが変わる**。

- **実体移動**: `docs-original/` 配下 29 ファイル。`git mv` により全件が rename として記録され、履歴と blame を保持している。
- **適用範囲を「パス表記」と「ディレクトリを指す表示文言」に限定した**。`--sources` の受理トークン `original-docs`、GitHub ラベル `original-docs-review`、[.github/ISSUE_TEMPLATE/original-docs-review.yml](.github/ISSUE_TEMPLATE/original-docs-review.yml)、[users-guide/original-docs-review.md](users-guide/original-docs-review.md)、AQOD 出力名 `qa/{key}-original-docs-questionnaire.md` / `qa/original-docs-cross-questionnaire.md`、mode マーカー `original-docs-questionnaire`、Python 識別子 `sources_original_docs` / `original_docs_or_qa`、GUI 設定キー `sources_original_docs` は **意図的に据え置いた**。これらは外部状態（ラベル・既存 `qa/` 成果物・保存済み GUI 設定・io-contract の producer 参照）と結び付いており、同時に改称すると後方互換シムの新設が必要になるためである。トークン値を据え置いた以上、それを列挙・説明する文言（`qa / original-docs / workiq`、`original-docs のみ` 等）も実値と乖離させないため据え置いた。
- **読み取り専用ガードを先に切り替えた**。[.github/workflows/protect-readonly-paths.yml](.github/workflows/protect-readonly-paths.yml) の検出パターンを `^docs-original/` へ、`ROOT_DIR_ALLOWLIST` を `docs-original` へ変更し、ジョブ ID も `check-docs-original` へ揃えた。`main` のブランチ保護必須チェックに本ジョブが含まれていないことを `gh api .../branches/main/protection` で確認済みのため、表示名変更による副作用はない。
- **対象境界の機械正本**: [.github/scripts/hve_scope.py](.github/scripts/hve_scope.py) の `OUT_OF_SCOPE_PREFIXES` と、その契約テスト（[hve/tests/test_hve_surface_inventory.py](hve/tests/test_hve_surface_inventory.py) / `.github/scripts/tests/`）のサンプルパスを同一変更セットで更新した。
- **HVE 実装**: AQOD の既定対象スコープ（`_AQOD_DEFAULT_TARGET_SCOPE`）、AKM の `target_files` 既定 glob（`_default_akm_target_files` の `docs-original/*`）、AQOD 成果物の必須スコープ行（`対象スコープ: docs-original/`）、AQOD Step タイトル、GUI のワークフロー要求ファイル種別と `explorer_roots` 既定値を更新した。GUI 翻訳は [hve/gui/i18n/hve_gui_en_US.ts](hve/gui/i18n/hve_gui_en_US.ts) の該当 4 組を同期し、`pyside6-lrelease` で `.qm` を再生成した（811 件 finished / 0 unfinished）。
- **索引**: [mdq.toml](mdq.toml) の `[index].roots` を `docs-original` へ変更した。ルート構成を変えても prune では旧チャンクが消えないため、`.mdq/index.sqlite` と `.mdq/index-ja-jp-heading.sqlite` を削除して再構築した（後者には旧パスのチャンクが 236 件残っていた）。
- **意図的に変更していない参照**: [mdq/cli.py](mdq/cli.py) と vendor 複製のコメントにある `original-docs/` は、移植可能な汎用エンジンが「豊富な文書構成を持つリポジトリの例」を列挙している箇所であり、本リポジトリのパスを指す参照ではない。`mdq` は独立ライフサイクルで版管理されるため範囲外とした。本ファイルの既存記述、`work/` 配下の実行成果物、`tools/skills/markdown_query/results/bench-*` は過去時点の記録のため書き換えていない。

**影響範囲**: 162 ファイル（`.github/` 88 / `hve/` 39 / `users-guide/` 20 / `hve-dev/` 5 / `docs/` 3 / ルート・設定ほか 7）。`.github/prompts/*.prompt.md` は 61 ファイルで、うち 58 は「書き込み禁止」定型 1 行のみの更新。

**検証**: `pytest hve/tests mdq cq .github/scripts/tests` で **8809 passed / 13 failed**。13 件は `git worktree add --detach <リポジトリ外パス> HEAD` で HEAD を別ツリーへ取り出し同一環境で実行し、**12 件が同じく失敗すること（既存不具合）を確認**した（生成済み Azure スクリプト 3、未配置の SWA workflow 1、SDK lock の改行コード 1、AQOD Work IQ 2、aad-web fan-out meta 1、PySide6 不在フォールバック 1、mdq リポジトリ golden set 3）。残る 1 件 `test_fanout_output_template_resolution[adi]` は、同一ワークツリーで並行作業中の別セッションが未コミットで追加した `ADI` ワークフロー由来であり（HEAD に `id="adi"` は存在せず、本変更の差分にも含まれない）、本変更とは無関係である。`hve/gui/tests` は 147 ファイルの単一プロセス一括実行が非実用のため、本変更が触れた `test_workflow_step_requirements.py` / `test_workflow_requirements_all_steps.py` / `test_explorer_roots.py` / `test_i18n.py` / `test_gui_pages.py` / `test_gui_help_content.py` を個別実行して 141 passed を確認した。`validate-io-contract.py` は 126 Agent / schema・integrity・registry いずれも 0 error。全 SVG の XML パース、全 workflow / Issue Template / io-contract の YAML パース、`mdq index` 後の `docs-original/` チャンク登録、`hve-dev/generate_tdd_inventory.py` 再生成（surface export 契約 162 passed）も確認した。

**既知の制約**: GUI 設定 `explorer_roots` を保存済みの利用者は、旧値 `original-docs` が残るため起動時に空ディレクトリが再作成される（Git 追跡外）。単発の改称に対する設定移行処理は追加していない。

<!-- validation-confirmed -->

### Added — CLI Autopilot が対話実行時に開始を確認する（FR-CLI-78）

`hve orchestrate --autopilot-chain` は計画サマリを表示した後、確認なしでそのまま複数 APP のチェーン実行を開始していた。GUI には開始前の確認ダイアログがあり、経路によって無人実行の扱いが食い違っていた。標準入力が対話可能なときだけ実行可否を確認するようにした。

- **確認は対話時のみとした**。[hve/\_\_main\_\_.py](hve/__main__.py) に `_confirm_autopilot_chain_start()` を追加し、`sys.stdin.isatty()` が偽のとき（CI 等）は従来どおり確認せず実行する。既存の非対話実行を後方非互換にしないため。確認を省略するための新規オプションは追加していない。既定の回答は「実行しない」とし、`y` / `yes` のときだけ開始する。
- **`--autopilot-dry-run` の挙動は変えていない**。dry-run は確認より前に return するため、従来どおり計画のみを表示して終了する。
- 要件 **FR-CLI-78** を [hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) §5.10 へ追加し、[hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) へ受入テストと RED / GREEN 証跡を記録した。要件インベントリを再生成し `active-or-described` として登録されたことを照合した。

### Fixed — `hve toolsearch context` が Step 実行と異なる条件で測定していた（FR-TS-11）

FR-TS-11 は「[hve/runner.py](hve/runner.py) `_create_session_with_auto_reasoning_fallback` と同じ経路でセッションを生成」すると規定しているが、[hve/toolsearch/context_report.py](hve/toolsearch/context_report.py) の `collect()` は `{"streaming": True}` だけを渡しており、設定済みモデルと `context_tier` がセッションへ伝わっていなかった。測定値が実 Step を代表しない状態だった。

- `session_options(config)` を追加し、`to_wire_model(config.model)` と `config.context_tier` を渡すようにした。cloud セッション設定は測定対象外のため注入していない。
- **この修正により、従来は観測できなかった事実が判明した**。`contextInfo.modelName` はセッションモデルに関係なく常に `claude-sonnet-4.5` を返す一方、`contextAttribution` 由来の層別内訳はセッションモデルに依存して変化する（`MODEL=claude-opus-4.7` で azure が 15,047→18,047 tokens）。2 つの API は異なるトークナイザで計測されており、`tool_definitions_tokens` と層別内訳の合計を突き合わせることはできない。`system_prompt_tokens` は 3 条件すべてで `null` だった。

### Fixed — `skill_manifest.json` が実在しない Step を参照し、registry の docstring が実数と食い違っていた

- **到達しない Step 参照を削除した**。`required_skills.ard` が宣言していた `3` / `4.1` / `4.2` / `4.3` は [hve/workflow_registry.py](hve/workflow_registry.py) に存在せず（実在は `1` / `1.1` / `1.2` / `2` / `2.1` / `3.1` / `3.2` / `3.3`）、一度も引かれない死んだエントリだった。実在する各 Step は `StepDef.required_skills` で同じ `knowledge-management` を宣言しているため、削除による解決結果の変化はない。
- **再発防止の検査を追加した**。[hve/tests/test_skill_resolver.py](hve/tests/test_skill_resolver.py) に `TestManifestMatchesRegistry` を追加し、`workflow_defaults` / `required_skills` / `optional_skills` が参照する workflow ID と Step ID が registry に実在することを固定した。この種の不整合は実行時エラーにならず、Skill が黙って適用されないだけなので静的検査でしか検出できない。
- **既存テストの誤りを是正した**。`test_required_skill_from_manifest_for_ard_step` は存在しない Step `"3"` を対象にしていたため、実在する Step `"1"` へ変更した（テストを通すための改変ではなく、registry の実態と乖離していたテストの修正）。
- **registry の docstring を実数に合わせた**。「12 個のオーケストレーションワークフロー」と記載しつつ実際は 13 個で、列挙から `ADA` が漏れていた。
- **`aar` の `workflow_defaults` は追加していない**。AAR の全 7 Step が `StepDef.required_skills` で `agentic-retrieval-contract` を宣言済みで、`workflow_defaults` へ足しても解決結果が変わらないため（使われない設定を増やさない）。

**影響範囲**: `hve/toolsearch/context_report.py`、`hve/skill_manifest.json`、`hve/workflow_registry.py`（docstring）、`hve/__main__.py`、`hve-dev/` の要件・テストマッピング・インベントリ。Workflow の DAG・成果物パス・argv 変換・GUI は変更していない。

**利用者への影響**: 対話端末から `hve orchestrate --autopilot-chain` を実行すると、開始前に `[y/N]` の確認が出る。CI などの非対話実行は変わらない。`hve toolsearch context` の層別内訳は設定モデルに応じた値になる（従来は SDK 既定モデルの値だった）。

**既知の制約**: (1)「対話 stdin かつ `--autopilot-dry-run`」の組み合わせは自動テストしていない。Windows で pty による TTY 擬似化が困難なためで、順序は実装で担保している。(2) `contextInfo` と `contextAttribution` のトークナイザ差は SDK / サーバ側の挙動であり、本変更では解消していない。(3) Autopilot の lane 単位の累積時間・コスト上限、および Azure MCP の Step 別読み込みは実装していない。前者は既定で有効にすると従来完走していた実行を止めるため後方非互換になり、後者は「Custom Agent プロンプトに `Azure` の文字列が現れるか」以上の判定根拠が得られておらず、誤判定時に Azure 系 Step を機能破壊するため。実測では 131 Step 中 58 Step が Azure 非依存だった。

**検証**: RED を実装前に確認した——`session_options` は `ImportError` で collection error、`TestManifestMatchesRegistry` は `{'required_skills.ard': ['3', '4.1', '4.2', '4.3']} != {}` で 1 failed、`TestAutopilotChainStartConfirmation` は `_confirm_autopilot_chain_start` 不在で失敗（いずれも実測）。実装後は `hve/tests/test_main.py` / `test_skill_resolver.py` / `test_toolsearch_context_report.py` / `test_toolsearch_context_cli.py` / `test_autopilot_cli.py` / `test_workflow_registry.py` / `test_toolsearch_skillcatalog.py` / `test_toolsearch_wiring.py` / `test_adi.py` の合計で **633 passed / 0 failed / 2 skipped**（27 subtests）。`hve toolsearch context --json` を 3 条件（model 未指定 / `"Auto"` / `claude-opus-4.7`）で実測し、いずれも EXIT=0 で内訳を取得した。要件インベントリを再生成し `FR-CLI-78` が `active-or-described` として登録されたことを照合した。

**事故と復旧の記録**: Autopilot の開始確認を実装する過程で、当初 `_cmd_orchestrate_autopilot_chain` 全体を対象とする統合テストを書いたところ、当該テストモジュールが `__main__.py` を `importlib` で別名ロードするため `hve.autopilot` への patch が届かず、**実際の Autopilot が起動した**。実行は FR-CLI-74（HVE ソース未コミット変更ガード）が全 APP を `blocked` にして停止させ、branch 作成・`work/run` 配下の新規生成・`docs/` `src/` への出力はいずれも発生していないことを実測で確認した。以後この経路の統合テストは行わず、確認ロジックの単体テストに限定した。

<!-- validation-confirmed -->

### Added — Azure を利用しない Workflow へ Azure MCP を渡さない（FR-CLI-79）

FR-CLI-76 がリポジトリ宣言の MCP サーバを Step 実行セッションへ渡す際、Azure を一切使わない Workflow にも `azure` MCP（68 ツール）が渡っていた。全 13 Workflow / 131 Step の Custom Agent プロンプトを走査したところ、`ard`（8 Step）/ `akm`（2 Step）/ `adi`（9 Step）/ `adoc`（23 Step）の **計 42 Step は 1 件も Azure に言及しない**。この 4 Workflow では `azure` を渡さないようにした。

- **Step 単位ではなく Workflow 単位の allowlist とした**。Step ごとの Azure 利用有無を機械判定する根拠はプロンプト中の文字列一致しかなく、誤判定すると Azure 系 Step を機能破壊する。本リポジトリにはプロンプトへ「Azure Functions」の語を足しただけで無関係な契約テストが誤発火した前例がある。Workflow 単位なら宣言は 4 件で済み、`aas`（11 中 1 Step）や `aad-web`（8 中 5 Step）のような混在 Workflow は対象外として安全側に倒せる。
- **allowlist 未登録は従来どおり全サーバを渡す**。`workflow_id` が解決できない場合も同様で、宣言漏れが機能破壊にならない向きに設計した。逆向き（「Azure が必要な Workflow を宣言する」）は宣言漏れが即障害になるため採らなかった。
- 実装は既存の [hve/runner.py](hve/runner.py) `_filter_mcp_servers_for_session`（Work IQ alias 除外の単一実装、呼び出し 3 箇所）へ除外条件を 1 つ追加しただけで、新しい宣言ファイルや抽象層は追加していない。`StepDef.per_key_mcp_servers` は fan-out キー単位の**追加専用マージ**でサーバを除去できないため再利用先にならなかった。
- **ドリフト検査を 2 種追加した**。(1) allowlist の全 Workflow の全 Step のプロンプトが Azure に言及しないこと、(2) `.github/.mcp.json` に除外対象のサーバ名が実在すること。前者は allowlist が実装から取り残されて Step を壊すことを防ぎ、後者はサーバ名の改名で縮約が無言で無効化されることを防ぐ。
- `microsoft-learn` MCP（3 ツール）は除外していない。Azure を使わない Workflow でも公式ドキュメント参照は発生しうるため。

### Added — CLI Autopilot の lane 経過時間を観測する（FR-CLI-80）

NFR-TIME-01 のとおり CLI の既定タイムアウト（21,600 秒）は**無入出力時間ベース**で、出力が続く限り lane は無制限に伸びうる。一方 NFR-TIME-02 のとおり Cloud 側は経過時間ベースの上限（360 分）を持つ。この Cloud / CLI の差を可視化するため、lane（APP チェーン）ごとの経過時間を計測し、360 分を超えた lane について警告を 1 行出すようにした。

- **lane を停止させない**。停止閾値を決めるには lane の実所要時間の分布が必要だが、そのデータが無い（TBD-09「性能 KPI は運用データ蓄積後」と同型）。まず観測だけを入れて、後続の判断材料を集める。既定で停止させると従来完走していた実行を止めるため後方非互換にもなる。
- 閾値は NFR-TIME-02 と同値の 360 分で**ハードコードとし、設定では変更不可**とした（NFR-PERF-02 と同じ扱い）。NFR-RTO-02 が新規 CLI オプションと `SDKConfig` フィールドの追加を禁じているため、制御面は増やしていない。
- 経過時間の取得は `clock` 引数で差し替え可能にし、実時間に依存するテストを書かずに検証できるようにした。警告の出力が例外を投げても実行は継続する。
- GUI Autopilot への警告表示は行っていない（`[hve:stats]` の `kind` 追加は NFR-RTO-02 に抵触するため）。

### Fixed — 要求定義書 §3.2 の Workflow 対応マップが registry と 3 件乖離していた

- **実在しない `abd` / `abdv`（Batch Design / Batch Dev）が残っていた**。改訂履歴 1.4 で §13.5 を ADFDV（Dataflow Dev）へ改称済みだったが、§3.2 の表だけ追随していなかった。`adfd` / `adfdv` へ置換した。
- **実在する `ada`（Agent Data Architecture、10 Step）が欠落していた**。`auto-orchestrator-dispatcher.yml` の `trigger_map` に `('auto-agent-data-architecture', 'ADA')` が登録され、専用 reusable workflow も実在するため **Cloud 対応済み**として追加した。以前の分析で「要件記載がないため削除候補」としていたのは誤りで、本書側の記載漏れだった。
- 行順を registry の登録順へ揃え、固有パラメータ列を `WorkflowDef.params` の実体に合わせ、Cloud 対応欄の根拠が `trigger_map` であることを明記した。表の Workflow ID 集合が registry と一致することを [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) が固定する。
- あわせて `adfdv` の `WorkflowDef.params` に `app_id` が 2 回宣言されていたのを 1 回に整理した。`params` は全経路で `in` による所属判定にしか使われず、厳密比較するテストも無いため挙動は変わらない。

### Fixed — `hve toolsearch context` の出力が測定条件を誤解させていた（FR-TS-11）

`contextInfo.modelName` は**セッションモデルを反映しない**。3 条件で実測したところ、`MODEL=claude-opus-4.7` を明示しても `modelName` は `claude-sonnet-4.5` のままだった。一方 `contextAttribution` 由来の層別内訳はセッションモデルに依存して変化する（azure 15,047 → 18,047 tokens、`contextInfo.mcpToolsTokens` は 17,302 で不変）。**2 つの API は異なるトークナイザで計測されている**。

- 出力に**セッションへ渡した設定モデル**を併記し、`modelName` と別物であることを明示した。
- 層別内訳の見出しに、上位の集計値とは別のトークナイザで計測されるため合計が一致しない旨を追記した。これまで両者の差分（実測 2,245〜2,273 tokens）は原因不明の欠損に見えていた。
- FR-TS-11 へ、測定セッションを Step 実行と同じ設定モデル / `context_tier` で生成すること、設定モデルを出力に含めること、両 API の差分を欠損として提示しないことを追記した。
- トークナイザを揃えるための独自再計算は行っていない（FR-TS-11 が推定値での代替を禁じているため）。

### Changed — `_build_step_permission_handler` の未使用引数は現状維持とした（TBD-25）

`StepRunner._build_step_permission_handler(step_id, custom_agent)` は両引数を使わないが、これは意図された設計である。引数を使って拒否判定を入れる方向は [hve/tests/test_runner_deploy_gate_order.py](hve/tests/test_runner_deploy_gate_order.py) `test_data_deploy_agent_permission_and_mcp_dead_path_stay_removed` が機械的に禁止しており、その根拠は「native pipeline は SDK import より前に return するため到達不能であり、復活は"到達しない安全境界"を増やすだけで実効性が無い」。残る選択肢の引数削除は可読性のみの価値で、呼び出し 2 箇所・5 テストファイルの参照・呼び出し位置を検査する契約テストへ波及する。TBD-22 と同型の判断として現状を維持し、判断根拠を §12 へ記録した。

**影響範囲**: `hve/runner.py`（MCP フィルタとセッション生成の `workflow_id` 伝播）、`hve/autopilot/cli_runner.py`、`hve/toolsearch/context_report.py`、`hve/workflow_registry.py`（`adfdv` の params）、`hve-dev/` の要求定義・テストマッピング・インベントリ。Workflow の DAG・成果物パス・argv 変換・GUI の選択肢は変更していない。

**利用者への影響**: `ard` / `akm` / `adi` / `adoc` の Step は Azure MCP を読み込まなくなる。CLI Autopilot は 360 分を超えた lane について警告を出す（実行は継続する）。`hve toolsearch context` の出力に「セッションの設定モデル」行が増える。

**既知の制約**: (1) Azure MCP の Step 単位の絞り込みは行っていない。混在 Workflow を扱うにはプロンプト文字列以外の判定根拠が必要。(2) lane の停止・コスト上限は実装していない。(3) `contextInfo` と `contextAttribution` のトークナイザ差は SDK / サーバ側の挙動であり解消していない。`system_prompt_tokens` は 3 条件すべてで `null` のままで、repository instructions の寄与は未確定。

**検証**: 各変更で RED を実装前に確認した——§3.2 の表は `{'abd','abdv'}` 余剰かつ `{'ada','adfd','adfdv'}` 欠落で 1 failed、`session_options` / `requested_model` は `build_report() got an unexpected keyword argument`、`_AZURE_FREE_WORKFLOWS` と `LANE_WALL_CLOCK_WARN_SECONDS` はいずれも `ImportError`（すべて実測）。実装後は `hve/tests/test_workflow_registry.py` ほか 5 スイートで **408 passed / 1 skipped**、`hve/tests/test_runner.py` ほか 5 スイートで **262 passed**、`hve/tests/test_toolsearch_context_report.py` と CLI で **21 passed**、`hve/tests/test_autopilot_cli.py` で **11 passed**。`hve toolsearch context` を実機実行し、EXIT=0 で「セッションの設定モデル: auto」および層別内訳の注記が出力されることを確認した。要件インベントリを再生成し `FR-CLI-79` / `FR-CLI-80` が `active-or-described` として登録されたことを照合した。

<!-- validation-confirmed -->

### Changed — GUI からの AAS Step 1/2 システムテストを再実施し、実行可能 profile の見積りと `users-guide` / `README` の記述を実装へ揃えた

GUI（Workflow=`aas` / Step=`1,2` / モデル=`Auto` / Autopilot=OFF）を対象にシステムテストを再実施した。製品コード（`hve/` `mdq/` `cq/` `src/`）は変更していない。新しい設定・CLI 引数・環境変数・依存は追加していない。Workflow 定義・DAG・成果物パス・argv 変換も変更していない。

- **runtime profile の実行可能部分集合を 147 から 37 へ補正した（測定手法の是正、製品挙動の変更なし）**。339 profile を 1 件ずつ GUI 上で dry-run したところ、110 profile が起動境界へ到達できなかった。原因は [hve/gui/page_options.py](hve/gui/page_options.py) `OptionsPage.validate()` が「QA (質問票) 自動投入」の三値ウィジェット未選択時に実行を拒否することで、`options.auto_qa` を設定しないシナリオは既定値のまま拒否される。これは「回答の AKM 同期有無を左右するため明示的な選択が必要」という設計意図どおりの挙動であり製品欠陥ではない。欠陥は、実行可能 profile の見積りがこの事前検証ゲートを織り込んでいなかった点にあった。観測された阻害理由コードは `auto_qa_tristate_unselected` の 1 種類のみである。
- **profile 分割の順序依存を解消した（測定手法の是正）**。単一の `OptionsPage` を全シナリオで再利用すると、combo 系ウィジェットへ空文字の既定値を戻せず前シナリオの値が持ち越され、profile 分割が処理順序に依存していた。シナリオごとにページを再生成する方式へ改め、逆順実行でも同一結果になることを確認した。profile 数は 543 から 339 へ収束した。
- **設定計測の対象セクションを補完した（測定手法の是正）**。`OptionsPage` の 15 セクションだけを観測しており、`SettingsWindow` 側のみに存在する 6 セクション（`AUTOPILOT` / `CQ` / `EXPLORER` / `LANG` / `MDQ` / `TOOLSEARCH`）を計測していなかった。`SettingsWindow` も生成してウィジェット ID から解決する方式へ改め、宣言済みウィジェットの未解決を 824 から 0 にした。
- **`users-guide` と `README` の記述を実装へ揃えた**。[users-guide/hve-gui-getting-started.md](users-guide/hve-gui-getting-started.md) の dock パネル既定表示（ファイルツリーは表示、Markdown プレビューは非表示）、[users-guide/hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md) の設定画面 16 ノードと Step 1 右ペインの区別・`C3` の例外再表示・legacy プレビュー・`C16` 欠番・Workbench の実行コマンド撤去・モデルウィジェットの同一性・Step 3 表記、[users-guide/cloud-session.md](users-guide/cloud-session.md) の GUI 設定場所、[users-guide/hve-technical-architecture.md](users-guide/hve-technical-architecture.md) のワークフロー数 13・MainWindow の 2 ページ構成・16 カテゴリー表の位置づけ・実行コマンド表示・`C5〜C16` 例示・`C16` 欠番・GUI ステップ表記、`README.md` の通常 GUI クラス表記を修正した。
- **前回キャンペーンの `users-guide` 未修正項目を解消した**。前回の `[Unreleased]` エントリーが「日付付きスナップショット記述のため変更していない」としていた「2026-08-07 時点で 12 ワークフロー」は、`list_workflows()` を実行して 13 件（`ard` / `aas` / `ada` / `aad-web` / `asdw-web` / `adfd` / `adfdv` / `aag` / `aagd` / `aar` / `akm` / `adi` / `adoc`）であることを実測し、ID 列を明記した記述へ改めた。同じく「操作フロー図の右ペイン表記『QToolBox 16 カテゴリ』は別事象」としていた項目も、設定互換用の内部識別子表であると位置づけを明確化して解消した。

**影響範囲**: `users-guide` 4 ファイルと `README.md` line 167 の記述、およびシステムテストの測定手法。製品コード・Workflow 定義・DAG・成果物パス・CLI 引数・GUI の選択肢は変更していない。

**利用者への影響**: ドキュメント上の誤記が解消される。GUI / CLI の挙動は変わらない。

**既知の制約**: (1) actual キャンペーンは 1 件も実行していない。G1 は承認済みだが、生成物が `docs/` の恒久成果物領域へ書き込まれる一方で専用 worktree が存在せず、共有チェックアウト上での相互汚染を機械的に防げないため、承認キャンペーン数を `0` として保留した。解除条件は run 配下の承認契約に記載した。(2) このため active FR 230 件はすべて `BLOCKED` であり、確定問題は 0 件である。製品の `PASS` も `FAIL` も主張していない。(3) 旧キャンペーンの SYS-001〜003 は現行ビルドで再現していないため引用していない。(4) 1 キャンペーンあたりの AI Credit / 所要時間は別キャンペーン由来の実測 1 件からの線形外挿であり、当該記録は commit を持たず source identity を主張できない。見積単位としてのみ用いている。

**検証**: 1,038 シナリオの設定計測で、宣言済みウィジェットの未解決 0 / 自動保存の往復差分 0 / 非伝播違反 0 / AAS 非適用オプションの漏れ出し 0、1-wise・pairwise・クラスターの未被覆いずれも 0 を実測した。339 profile の dry-run では実プロセス起動 0 / model 呼び出し 0 / 外部書き込み 0 / 遮断対象操作の試行 0 / 対象外 Step の選択 0 / argv 署名の不一致 0 を実測し、実 `hve/.settings.txt` が測定前後で不変であることを確認した。要件判定は 230 件で欠落・重複・未解決・不正 status すべて 0。`users-guide` / `README` は統合検証で旧文言の残存 0、更新不要と判定した対象の差分 0、`README.md` の変更行が `167` のみであることを確認した。キャンペーン全体では 40 個の完了マーカーについて 195 件の成果物ハッシュを照合し不一致 0、レビュー未 PASS 0、未解決指摘 0、製品コード差分 0 を確認した。

**検証時の注記**: 検証器の初回実行で 38 件の不一致を検出したが、切り分けの結果すべて検証器側の欠陥であり成果物の破損ではなかった。内訳は (a) `core.autocrlf=true` 下で記録側が raw バイト方式・検証側が LF 正規化方式に固定されていた（実 `hve/.settings.txt` は raw ハッシュが基準値と完全一致し無変更）、(b) `artifacts` 辞書内の `*_sha256` キーをパスとして解決しようとした、(c) キャンペーン内に 4 種ある review 記録形式のうち 3 種しか判別していなかった、(d) リポジトリ相対パスと、内容不変のまま改名された受け渡し文書を解決できなかった、の 4 件である。いずれも検証器を是正して再実行し不一致 0 を確認した。

<!-- validation-confirmed -->

## [0.8.40] - 2026-08-24

Pester 6対応、PowerShell ADFD / ADFDV registry同期、Windows / Ubuntu CIの検証範囲強化を反映した保守リリース。詳細は`[Unreleased]`の同名エントリーを参照。

<!-- validation-confirmed -->

## [0.8.39] - 2026-08-23

ARDの4表示グループ / 8実Step、SR-ID伝搬、Data Modelのcanonical sidecar、Cloud G-LBL fail-closed遷移を同期した保守リリース。検証結果と既知の制約は`[Unreleased]`の同名エントリーを参照。

<!-- validation-confirmed -->

## [0.8.38] - 2026-08-23

§13のWorkflow Step表とregistryの横断同期、AAGD Step 6 / 7の成果物契約規範化、および起動面ごとの既定値単一化を反映した保守リリース。詳細は`[Unreleased]`の該当エントリーを参照。

<!-- validation-confirmed -->

## [0.8.37] - 2026-08-22

GUI からの AAS Step 1/2 システムテスト再実施に伴う保守リリース。製品コードの変更はなく、`users-guide` 4 ファイルと `README.md` の記述を実装へ揃えた。詳細は `[Unreleased]` の該当エントリーを参照。

<!-- validation-confirmed -->

## [0.8.24] - 2026-08-19

### Added — 事前 QA の Work IQ 統合可否を Workflow 再実行なしで確認できるようにした（FR-QA-08 新規 / FR-QA-07 改訂）

v0.8.23 の受入確認は「AAS Step 1 を丸ごと再実行して統合件数を数える」しかなく、実測 40 分超を要していた。修正の検証コストが過大で、同種の不具合が再発しても短時間で切り分けられない。

- **`workiq-doctor --qa-integration-probe` を追加した（FR-QA-08）**。本番の事前 QA と同じ Work IQ プロンプトテンプレートを 1 問だけ送信し、`workiq_qa_merge_decision` チェックとして (a) 許可済み server/tool 組の実行確認、(b) 応答 status、(c) 統合可否を報告する。`FAIL`（実行未確認）のときは当該区間で観測されたツール名と診断コマンドを併記する。応答本文・prompt 本文・tool 引数は出力しない。
- **統合可否の判定を単一実装へ寄せた（FR-MAINT-07）**。[hve/runner.py](hve/runner.py) にインライン実装されていた FR-QA-03 の条件を [hve/workiq.py](hve/workiq.py) の `is_workiq_result_mergeable()` へ抽出し、事前 QA 本体と診断の双方が同一実装を使う。診断は既存の `probe_workiq_copilot_tool_invocation()` へ引数で分岐させ、セッション生成・MCP 状態確認・イベント購読を再利用した（新しい probe 関数は作っていない）。問い合わせも本番と同じ `query_workiq_detailed()` を通す。
- **QA 起点 AKM の登録時点で HVE ソースの dirty を事前判定するようにした（FR-QA-07 改訂）**。dirty のときは子実行を起動せず登録をスキップし、即時に警告する。スキップは実行失敗と別の文面で報告し、`returncode` を失敗として集計しない。FR-CLI-74 の最終ガードは弱めず維持する（登録時 clean でも実行時 dirty になり得るため）。判定は `_git_dirty_hve_source_paths()` を再利用し、`cwd` を coordinator の `repo_root` へスコープした。従来はプロセスの CWD で判定するため、リポジトリ外を `repo_root` にした呼び出しが本体リポジトリの状態を誤って読んでいた。

### Fixed — 子出力を decode する subprocess 呼び出し 8 箇所へ encoding を明示した

v0.8.23 では `hve/workiq.py` だけを修正したが、同じ欠陥（`text=True` のみで `encoding` 未指定 → 日本語 Windows で cp932 decode）が他モジュールに残っていた。

- 修正対象: [hve/asdw_data_script_launcher.py](hve/asdw_data_script_launcher.py)、[hve/asdw_step12_verification.py](hve/asdw_step12_verification.py)（2 箇所）、[hve/copilot_client_factory.py](hve/copilot_client_factory.py)、[hve/runner.py](hve/runner.py)（2 箇所）、[hve/self_improve.py](hve/self_improve.py)（2 箇所）。いずれも子出力を capture するため同一の再現条件を持つ。
- **契約テストをリポジトリ横断へ広げた**。[hve/tests/test_orchestrator_git_encoding.py](hve/tests/test_orchestrator_git_encoding.py) に `hve` / `mdq` / `cq` / `.github/scripts` の非テストコードを AST 走査する `TestHveSubprocessDecodeContract` を追加し、v0.8.23 で `hve/workiq.py` 限定だった AST テストは重複のため撤去した。
- 契約は **`encoding` の明示のみ**を強制し、`errors` の要否は呼び出しごとの判断に委ねる。`cq/benchmark.py` / `cq/discovery.py` の git ファイル列挙は `errors="replace"` を付けると存在しないパスへ化けるため、strict のままが正しい。

**影響範囲**: Work IQ 診断 CLI（新規オプション 1 つ）、QA 起点 AKM の登録経路、上記 8 箇所の subprocess 呼び出し。既定動作は変わらない（`--qa-integration-probe` の既定は無効、dirty でないときの登録挙動は従来どおり）。

**検証**: 新規 RED を実装前に確認（`test_workiq.py` / `test_qa_akm_child_logging.py` / `test_main.py` / `test_orchestrator_git_encoding.py` で 19 failed）。実装後、関連 9 ファイルで **532 passed / 69 subtests**、回帰 6 ファイルで **767 passed / 190 subtests**、いずれも 0 failed。**実機受入 4 件をすべて実行した**: (1) P-1 は `workiq-doctor --qa-integration-probe` が `workiq_qa_merge_decision: PASS`（`tool=ask / status=PARTIAL` → 統合される）を返し、全チェック成功。(2) P-2 は一時 git リポジトリで AKM 子実行を実際に失敗させ、`returncode=1`・`work/run/qa-akm-<id>/child-stdio.log` に blocked 本文（`hve/dirty_probe.py` を含む）・親報告に `returncode` / ログパス / 未コミット変更の導線が出ることを確認。(3) P-4 は `is_workiq_available()` が warm で **53.7 秒**（旧既定 30 秒を超過＝初回 `False` の直接原因）、独立した一時 npm キャッシュによる cold で 20.4 秒、いずれも `True`。(4) P-5 は `workiq-doctor --sdk-probe --sdk-tool-probe --sdk-event-trace` を 3 回連続実行して `UnicodeDecodeError` **0 件**（`copilot_tool_invocation` は 3/3 PASS）。`hve-dev/generate_tdd_inventory.py` を再生成し、`FR-QA-08` が `source=hve-dev/requirement-definition.md` / `active-or-described` で索引へ載ることを確認した。

**既知の制約**: `--qa-integration-probe` は `workiq-doctor` が構成するセッション上で動くため、利用者の MCP 設定に公式 `workiq` サーバーが登録されている場合の併存条件までは再現しない。統合 0 件が本番でだけ再現する場合は、本診断が `PASS` でも FR-QA-06 の実行時警告で切り分ける必要がある。また、許可集合の動的構築（v0.8.23 で実装不能と判定）は本変更時点の SDK でも実測し直したが状況は変わらない。`session.rpc.mcp.list()` の server オブジェクトの属性は `error` / `from_dict` / `name` / `source` / `source_plugin` / `source_plugin_version` / `status` / `to_dict` だけで tools を含まず、`session.rpc.tools` は `get_current_metadata` / `handle_pending_tool_call` / `initialize_and_validate` / `update_subagent_settings` のみで一覧取得 API を持たない。

<!-- validation-confirmed -->

## [0.8.23] - 2026-08-19

### Fixed — Work IQ の調査結果が事前 QA へ 1 件も統合されない問題を修正し、統合失敗を検知可能にした（FR-QA-06 / FR-QA-07 新規、FR-QA-03 改訂）

2026-08-19 の実測（AAS Step.1 を `--auto-qa --workiq --workiq-draft` で実行）で、Work IQ 応答 6 件のうち 3 件が `STATUS: FOUND` であったにもかかわらず、事前 QA への統合が **0 件**になった。実行面には `✅ Work IQ: 0 件の質問に回答案を統合しました` という成功記号付きの情報メッセージしか出ず、利用者は異常に気づけなかった。実際に呼ばれていたツールは `retrieve`（10 回）で、当時の実行確認集合は `ask` のみだった。

- **実行確認集合を公開 allowlist から分離した**（[hve/workiq.py](hve/workiq.py)）。MCP へ公開する allowlist `WORKIQ_MCP_TOOL_NAMES` は最小権限の `ask` のまま据え置き、tool 実行確認には新設の `WORKIQ_MCP_QUERY_TOOL_NAMES`（`ask` / `retrieve` / `fetch` / `fetch_blob` / `get_schema` / `search_paths`）を使う。Work IQ を有効化した QA サブセッションは FR-CLI-76 により MCP 自動探索が残るため、利用者設定の公式 `workiq` サーバーが HVE の allowlist の制限を受けずに参照系ツールを公開する。集合を `ask` だけに揃えると、この経路の実行を恒久的に検出できない。公開ツール名は `tools=["*"]` での実測 14 件を根拠とし、書き込み系（`create_entity` / `update_entity` / `delete_entity` / `do_action`）と `accept_eula` / `get_debug_link` / `call_function` / `list_agents` は M365 データ参照の証拠にならないため実行確認集合へ入れていない。`mcp_server_name` を持たない tool イベントを Work IQ として扱わない判定は維持した。
- **tool 実行未確認を警告として通知するようにした（FR-QA-06）**。応答 status が `FOUND` / `PARTIAL` なのに実行を確認できない場合、当該区間で実際に観測されたツール名と診断コマンドを添えて警告する。統合が 0 件で Work IQ 応答が 1 件以上ある場合の統合結果サマリーも `✅` ではなく警告で出す。`NOT_FOUND` / `UNAVAILABLE` / status 不明は一次情報が見つからなかった正常な結果のため警告しない（全質問で警告が出ると検出漏れの信号が埋もれるため）。警告文の生成は [hve/workiq.py](hve/workiq.py) の `format_workiq_tool_not_invoked_warning()` へ集約し、[hve/orchestrator.py](hve/orchestrator.py) の prefetch 経路が持っていた同一文言の直書きを置き換えた（FR-MAINT-07）。
- **QA 起点 AKM 子実行の出力を保全するようにした（FR-QA-07）**。[hve/qa_akm_dispatch.py](hve/qa_akm_dispatch.py) は子の stdout / stderr を `subprocess.DEVNULL` へ捨てていたため、失敗しても親のログに件数しか残らず、原因究明に手動再現が必要だった。`work/run/qa-akm-<id>/child-stdio.log` へ束ねて保存し、結果へリポジトリルート相対の `log_path` を含め、[hve/orchestrator.py](hve/orchestrator.py) の失敗報告へ `returncode` と保存先パス、および HVE ソース未コミット変更（FR-CLI-74）の確認導線を出す。子ログの本文は親のログへ展開しない。バッチ実行では保存先単位で束ねて報告する。
- **Work IQ CLI の可用性判定を堅牢化した**。`is_workiq_available()` はタイムアウト（旧既定 30 秒）を他の例外と同列に握りつぶし、`False` をモジュールキャッシュへ恒久的に書き込んでいた。初回は `npx -y` が npm レジストリからパッケージを取得するため 30 秒を超え得る（実測: cold で `False`、warm で 7.0 秒の `True`）。既定を 120 秒へ引き上げ、タイムアウトは「判定不能」として結果をキャッシュせず同一プロセス内で最大 2 回まで再試行する。`FileNotFoundError` 等は従来どおり `False` をキャッシュする。
- **Windows のロケール既定 decode による例外を解消した**。[hve/workiq.py](hve/workiq.py) の `subprocess.run` 8 箇所が `text=True` のみを指定しており、日本語 Windows では cp932 で decode するため、Work IQ CLI が UTF-8 の非 ASCII を出力すると `UnicodeDecodeError: 'cp932' codec can't decode byte 0x81` でスレッド例外になった（`workiq-doctor` 実行時に実測）。全 8 箇所へ `encoding="utf-8", errors="replace"` を指定し、AST で回帰を固定した。

**影響範囲**: Work IQ を有効化した事前 QA / prefetch 経路、`workiq-doctor` 診断、QA 起点 AKM 子実行の 3 箇所。既定で Work IQ / QA 起点 AKM を使わない実行には影響しない。統合対象の判定条件（server/tool の組 + status が `FOUND` / `PARTIAL`）は変更していないため、従来統合されていた結果が統合されなくなることはない。MCP へ公開するツールは `ask` のままで、権限は広がらない。

**既知の制約**: 許可集合をセッションの `session.rpc.mcp.list()` から動的構築する案は採らなかった。実測で server オブジェクトが公開する属性は `error` / `from_dict` / `name` / `source` / `source_plugin` / `source_plugin_version` / `status` / `to_dict` だけで tools を含まず、`session.rpc.tools` にも一覧取得 API が無いため実装できない。SDK が tools を公開した時点で再検討する。また、`submit()` 時点で HVE ソースの dirty 判定を先読みして事前警告する案も採らなかった。判定は時点依存で、submit 時 clean でも実行時に dirty になり得るため誤った安心を与える。`retrieve` を発行した tool イベントが `mcp_server_name` を伴っていたかは事後ログから確認できない。伴っていなかった場合は本修正後も実行確認は成立しないが、その場合は FR-QA-06 の警告が観測ツール名付きで出るため、恒久的に無症状のまま統合 0 件になることは無くなる。

**検証**: 新規 RED を実装前に確認（`hve/tests/test_workiq.py` / `hve/tests/test_runner_pre_qa.py` / 新規 `hve/tests/test_qa_akm_child_logging.py` で **36 failed / 191 passed**）。実装後、同 3 ファイル + QA 起点 AKM 関連 4 ファイルで **252 passed / 38 subtests / 0 failed**。回帰確認として `hve/tests/test_runner.py` / `test_orchestrator.py` / `test_qa_merger.py` / `test_adi.py` / `test_main.py` で **834 passed / 118 subtests / 0 failed**。`hve-dev/generate_tdd_inventory.py` を再生成し、`FR-QA-06` / `FR-QA-07` が `source=hve-dev/requirement-definition.md` / `active-or-described` で索引へ載ること、新規テストが `hve-dev/hve-test-inventory.csv` へ登録されること、対象外パスの混入が無いことを確認した。

<!-- validation-confirmed -->

## [0.8.9] - 2026-08-17

### Changed — セットアップが GitHub Copilot CLI と SDK を既定で最新版へ更新するようにした（FR-MODEL-07 改訂 / FR-MODEL-08 新規）

Windows / macOS / Linux のセットアップは、外部 `copilot` CLI について「導入済みか」を見るだけで、npm グローバル管理下と判定できた場合しか更新していなかった。判定に失敗した環境（`npm ls -g` が非ゼロを返す構成など）では何も起こらず、新規導入経路も `@github/copilot`（タグ未指定）だったため、「最新版が入る」ことが保証されていなかった。`github-copilot-sdk` も既定では `hve/copilot-sdk.lock` の固定版で止まっていた。

- **`github-copilot-sdk` の既定を最新追従へ変更した**（FR-MODEL-07）。既定経路は `pip install --upgrade --no-deps github-copilot-sdk` を実行する。`--no-deps` は従来どおり必須で、pip resolver が `pydantic-core` を pydantic 本体の pin から乖離させる問題を避ける。版を固定したい場合は新フラグ `-PinSdk` / `--pin-sdk` を指定すると `hve/copilot-sdk.lock` の版を導入する。`-UpgradeSdk` / `--upgrade-sdk` は「最新化 + lock 書き換え」の役割として維持し、既定経路では lock に触れない。SDK が pin する Copilot ランタイムの先読みと `--no-auto-update` による版突合、pin 無効化環境変数の警告は変更していない。
- **外部 `copilot` CLI を常に最新版へ導入・更新するようにした**（FR-MODEL-08）。導入時・更新時とも `@github/copilot@latest` を指定する。導入済みかつ npm グローバル管理下なら確認プロンプトなしで更新し、npm 管理下でない `copilot` を検出した場合は PATH 上に 2 つの CLI が並ぶことを避けるため更新せず、警告と手動更新手順を提示する。`-NoInstallTools` / `--no-install-tools` と `-CheckOnly` / `--check-only` は従来どおり変更を抑止する。
- **利用者ガイドと `hve/setup-hve.cmd` のヘルプを実挙動へ揃えた**。オプション表へ `-PinSdk` / `--pin-sdk` と `-UpgradeSdk` / `--upgrade-sdk` を追加した。

**既知の制約**: 既定が最新追従になったため、公開直後の SDK リリースにパーサ不整合があると同時期にセットアップした全員が影響を受けうる。切り分けや再現手順の共有が必要な場面では `-PinSdk` / `--pin-sdk` を使う。npm グローバル管理下でない `copilot` は自動更新しない。

**検証**: `hve/tests/test_dev_task_environment_contract.py` 22 passed（改訂 2 件・新規 2 件について RED → GREEN を確認）。setup ハーネスで `setup-hve.sh` / `setup-hve.ps1` を実行し、既定実行が SDK を `--upgrade` し lock に触れないこと、`--pin-sdk` / `-PinSdk` が lock 版のみを導入することを実測した。`bash -n` と ShellCheck は既存の SC2164 1 件のみ（本変更以前からの指摘）。`--help` の表示範囲も実行確認した。TDD inventory を再生成し FR-MODEL-08 が `active-or-described` として索引へ登録されたことを確認した。

<!-- validation-confirmed -->

## [0.8.7] - 2026-08-16

### Removed

- 独立していた原本質問票Workflowを廃止し、Registry、CLI / GUI選択肢、Cloud dispatcher、reusable workflow、Issue Form、ラベル、専用I/O契約・テンプレート・fan-out指示・テスト・利用者ガイド・専用SVGを削除した。後方互換aliasとCloud代替経路は設けていない。

### Changed

- 原本質問票生成をADIのStep 1とStep 2の間へ移し、9 Step DAG（`1 → 1.1 → 1.2 → 2 → 3 → 4 → 5.1/5.2/5.3`）へ統合した。Step 1.1はD01〜D21を21並列fan-outし、Step 1.2は21質問票をjoinして横断質問票を生成する。
- ADIが `purpose` / `target_scope` / `depth` / `focus_areas` の4パラメータを一元所有し、`target_scope` は `docs-original/` 配下だけへfail-closedで正規化するようにした。
- D01〜D21の質問票21件と横断質問票1件をADIのmain成果物として検証・明示commit対象にし、質問0件は件数0と「質問なし」を明記した有効成果物として扱うようにした。
- `QA-DocConsistency`、Self-Improve、I/O契約、GUI設定・英訳、AKM routing soft dependency、利用者ガイド、技術文書、ADR、共有SVGをADI中心の契約へ同期した。
- ルートREADME.mdをADI統合後の構成へ同期した。Workflow一覧を13→12件、Issue Templateを11→10個、task-data-flow SVGを11→10枚へ更新し、ADI行へ質問票成果物を追記、CLI実行例を `--workflow adi` へ差し替え、削除済みガイド・reusable workflow・Issue Formへの参照を除去した。ADIがCLI / GUI専用であることの注記も追加した。

### Validation

- HVEコア全体は **7600 passed / 18 skipped / 7 deselected / 2 xfailed / 571 subtests passed**。除外した7件は隔離したHEAD worktreeでも同じ顔ぶれで失敗することを確認した（ASDW sample-data 3、未配置SWA workflow 1、SDK lock改行1、GUI fallback 1、AAD-WEB fan-out 1）。GUI / i18n focused suiteは **212 passed / 12 subtests passed**、Cloud / Prompt横断契約は **417 passed / 2 xfailed / 296 subtests passed**、inventory整合は **163 passed**。
- I/O契約検証は133 Agent、schema / integrity / registry mismatchすべて0件。文書リンク、全SVG XML、差分品質、版番号 `0.8.7` の4箇所同期、active成果物の廃止識別子残存0件を機械検証した。
- 敵対的レビューを実施し、CloudでADIを起動できるように見える説明、AARの誤接続図、GUIカテゴリ欠番の説明不足、要件マッピングの陳腐化したRED予定を修正した。
- READMEは版管理対象外（[.github/scripts/hve_scope.py](.github/scripts/hve_scope.py) の判定で out-of-scope）のため版は `0.8.7` のままとした。README内の相対リンク全件が実在すること、廃止識別子の残存が0件であること、件数表記が実測値（SVG 10枚 / Issue Template 10個 / Workflow 12個）と一致すること、`git diff --check` がクリーンであることを確認した。

<!-- validation-confirmed -->

## [0.8.2] - 2026-08-16

### Added — Custom Agent の Prompt ファイル実在を CI で強制するようにした

[hve/prompt_loader.py](hve/prompt_loader.py) の `load_prompt()` は `.github/prompts/<Agent>.prompt.md` が存在しないとき例外ではなく空文字を返す。一方で既存の CI は `test_template_engine.py::test_all_body_template_paths_exist` が `body_template_path` の実在を検証するだけで、Prompt 側は無検査だった。そのため Prompt を作り忘れたまま Step を実行しても、Agent 仕様が LLM に一切渡らない状態で完走してしまう（実行時に落ちないので気付けない）。

- [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) に `TestCustomAgentPromptFilesExist` を追加し、全ワークフローの `custom_agent` について (1) 対応する `.prompt.md` が実在すること、(2) それが空でないこと、を検証する。空ファイル検査は「存在するが 0 バイト」という書き込み事故を拾うためのもので、実体が無い点では未作成と同義として扱う。

**検証**: 13 ワークフロー × 2 件 = 26 passed。ADI の Prompt 1 件を一時退避した状態で対象テストが FAILED になることを確認してから復元し、false-green でないことを確かめた。調査時点で全 13 ワークフロー・103 件の `custom_agent` 宣言に対する Prompt 欠落は 0 件。

<!-- validation-confirmed -->

## [0.8.1] - 2026-08-16

### Changed — 原本保存先を `docs-original/` へ移行した

- `original-docs/` の原本 29 ファイルを、内容を変更せず同一相対パスの `docs-original/` へ Git rename した（全件 `R100`）。
- GUI Explorer の既定ルートを `docs-original` に統一し、保存済み設定の完全一致トークン `original-docs` は読込時に自動移行する。`custom/original-docs` のような部分パスは変更しない。
- `check-docs-original` は通常の `docs-original/` 変更を fail-closed で拒否し、GitHub PR ファイルメタデータ上で検出できる `original-docs/` から同一相対パスへの rename だけを初回移行例外として許可する。

### 検証

<!-- validation-confirmed -->

- `check-docs-original` の run script を UTF-8 で抽出し、`bash -n` が成功した。
- `hve-dev/generate_tdd_inventory.py` を連続 2 回実行し、各回でテスト 11,711 行、機能 372 行、実装面 3,285 行を生成した。
- GUI 設定移行、読み取り専用 CI、原本取り込み、トレーサビリティ、生成インベントリを対象にした回帰テストは **293 passed / 3 skipped**。
- `pyproject.toml` の 2 箇所、`hve/__init__.py`、本見出しの HVE 版番号が `0.8.1` で一致することを確認した。

## [0.7.4] - 2026-08-15

### Changed — HVE と code-query Skill の PATCH 版を上げた

- HVE: `0.7.3` → `0.7.4`（`pyproject.toml` の `[project].version` と `[tool.bumpversion].current_version`、`hve/__init__.py` の `__version__`、本ファイルの版見出し）。
- code-query Skill: `0.4.0` → `0.4.1`（[.github/skills/code-query/SKILL.md](.github/skills/code-query/SKILL.md) の `metadata.version`）。配布キット側の写しは `sync-vendor` で同期した。

出荷物の挙動は変えていない。

### 検証

<!-- validation-confirmed -->

- `cq/tests/` + vendor sync + Skill 配線 + Skill バンドル同期で **796 passed**。
- 4 箇所の HVE 版番号が `0.7.4` で一致し、直前の `0.7.3` から 1 つだけ増えていることを確認した。

## [0.7.3] - 2026-08-15

### Changed — code-query の順位統合を `--semantic` の内部動作へ限定し、`--fuse` を削除した（FR-CQ-16 改訂）

`[0.7.2]` で追加した `--fuse` を、ベンチマークで測って外した。golden 56 問で、語彙経路だけを順位の逆数和で統合した結果は逐次 fallback と **56 問すべてで順位が完全に一致**し（順位が異なるクエリ 0 件）、応答トークンだけが k=3 で 2.2〜2.4 倍に増えた。

- 統合の機構そのものは残る。`--semantic` を付けたときにだけ内部で動く（意味検索は語彙経路と統合してこそ効くため）。
- `--explain` は据え置き。統合が起きる `--semantic` 時にだけ実行内訳が出る。
- 何も変えない公開フラグを残すより削る方が正しいと判断した。追加した当日で外部利用者がいないため、非推奨期間は設けていない。

### Added — code-query に「コード情報だけを返す」返却単位を追加した（`--return-unit symbol`、FR-CQ-17 改訂）

本文（snippet）を返さず、ヒットを囲むシンボルの `qualname` / `kind` / `signature` を返す。`signature` に引数名が含まれるので、「どこに何があるか」を知る用途はこれで足りる。

```bash
python -m cq search --profile hve --q "resolve_run_id" --return-unit symbol
```

- 実測（golden 56 問 / top-3 / 既定経路）: 応答トークンの中央値が **159 → 110（比 0.69）**、名前の付いたヒットが **31/80 → 62/80**。
- **`symbols` へ結合する**。結合しないとトークンはさらに小さくなるが、80 件中 49 件がパスと行番号だけになり「関数名・引数名を返す」用途を満たさない。
- **`parser` と `chunk_id` は落とさない**。前者は FR-CQ-11 のフィデリティ通知、後者は `cq get` で本文を取得する導線であり、落とすと契約違反になる。両方を落とせば比 0.45 まで下がるが採らない。

### 実測に基づき「実装しない」と判断したもの

`work/` のベンチマーク（`e1_route_budget.py` 〜 `e7_return_shape.py`）で測った結果、以下は採用しなかった。

| 候補 | 実測 |
|---|---|
| 既定 `top_k` を 5 → 3 へ下げる | `chain` の飽和点は `profile=app` で **k=5**。3 へ下げると `natural/en` を 1 問失う |
| intent 別に `top_k` を自動で絞る | `symbol`/`substr`/`trace`/`regex` は k=1 で損失 0 問（36 問）だが、`_cap_tokens` が既にトークン予算で切っており分岐を足す利得が無い |
| `natural` で意味検索を単独運用する | `hve:natural/en` の @3 で `semantic-only` 0.86 > `fuse+semantic` 0.71。ただし **n=7 で 1 問差**のため判定不能 |
| LLM によるクエリプランニング | ローカル LLM（`phi4-mini` 3.8B / `qwen2.5:7b`）で @3 が 0.40 と `fuse+semantic` の 0.45 を下回る。所要 0.22 → 8.2 秒（37 倍）、検索 5 → 16 回 |
| 自然言語での返却 | トークンは 89% 減るが、正解が top-3 にある 45 件のうち **5 件で正解パスが要約から落ちた**。1 クエリ 2.05 秒とローカル LLM 常駐も要る |
| 意味検索のレイテンシ最適化 | 実 CLI の 3,285 ms のうち **95.5% が埋め込みモデルのロード**（2,957 ms）。ベクトル読み込みは 76 ms で、最適化しても効かない。回避には常駐プロセス化が必要 |

### ベンチマークで判明した運用上の事実（ドキュメントへ反映済み）

- **正解に到達できる問いは、すべて 1 経路で到達できる**。複数経路の統合が必須になった問いは 56 問中 0 問。
- intent ごとに効く経路は 1 つに決まる。日本語の自然文だけは **`--semantic` が唯一の到達手段**（語彙 4 経路がすべて 0 件）。
- **`--semantic` は実 CLI で 3,285 ms**（非 semantic は 338 ms）。語彙経路で届く問いには付けないこと。
- **cosine に閾値が無いため `--semantic` は 0 件を返さない**。ヒットしたことを関連の根拠にしないこと。

### 検証

<!-- validation-confirmed -->

- `cq/tests/` + vendor sync + Skill 配線 + GUI 索引サービスで **797 passed**。
- 変更は RED → GREEN の順序で実施（`--fuse` 削除と `--return-unit symbol` で 10 failed → 43 passed）。
- 実装後に golden 56 問で再計測し、`--semantic` の到達率が計測時と一致することを確認した（hve 0.71/0.74、app 0.80/0.88、chain は hve 0.68 / app 0.80/0.84/0.88）。
- 各タスク後に敵対的レビューを実施し、以下を反映した:
  1. 先のベンチマークレポート 3 本に誤りが 2 件（「k=3 で飽和」は profile とアームで異なる／「semantic が遅いのはベクトル読み込みのため」は誤りで支配項はモデルロード 95.5%）。実測し直して訂正した。
  2. `--return-unit symbol` のトークン比が計画の見積り 0.42 に対し実装値 0.69 と乖離。原因は見積りが落とせないフィールド（`parser` / `chunk_id`）を落として試算していたこと。実装値を正とし、記録を訂正した。
  3. `--return-unit symbol` の追加時に既存テストを分断していたので復元した。
  4. CLI 経由の activity テストが実モデル（240 MiB）をロードしており環境依存だった。provider を差し替えて 2.07 秒・環境非依存にした。

## [0.7.2] - 2026-08-15

### Added — code-query に全検索層の順位統合（Agentic Retrieval 相当）を追加した（FR-CQ-16）

これまでの検索は「最初に非空を返した層で打ち切る」逐次 fallback で、後続層が持つ候補へ到達できなかった。Azure AI Search の Agentic Retrieval が「サブクエリを並列実行し、統合ランキングへまとめる」形をとるのと同じ構造を、**LLM もクラウドも使わずローカルで**実装した。`python -m cq search --q "..." --fuse` で有効になる。

- 統合は**各層内の順位のみ**を根拠とする順位の逆数和で行う。層ごとにスコアの尺度と符号が違う（`bm25` は SQLite の負値、`symbol` は 1.0/0.5 の固定値、`substr` は固定値）ため、スコアを直接混ぜられない。
- **リテラル一致の層（`trace` / `symbol` / `substr`）は統合対象外**とし、自身の順位を保って先頭に置く。問いの文字列そのものを含む場所を返すのは 1 層だけで、順位の逆数和では複数層に現れる付随的な一致に構造的に負けるため。これを等価に統合した最初の実装は、golden 56 問で `symbol` intent の top-1 が 1.00 → 0.77、`substr` が 1.00 → 0.57、全体が 0.73 → 0.59 へ**退行した**。層を分けた実装では rank 変化が 0 件になった。
- `--explain` を付けると、実行した層とその件数（activity log）を最終行へ 1 行 JSON で出す。既定応答は 800 token 予算でメタデータだけで 101 tokens/hit を使うため、常時は出さない。
- **統合単体の利得は実測でゼロ**（全体 0.73 / 0.77 / 0.75 が baseline と同値）。`_fallback_order` が既に意図に最も近い層から試す優先順位を実装しているため。このため**既定は逐次 fallback のまま**にした。統合が効くのは次項の意味検索層を加えたとき。

### Added — code-query に意味検索の層を追加した（FR-CQ-17）

`python -m cq index --embed` でベクトル副索引を作り、`python -m cq search --q "..." --semantic` で上記の統合へ加える。**既定は OFF** で、ベクトルを作らない限り一切のコストがかからない。

- **2026-08-04 の NO-GO 判定を部分的に覆した**。当時は日本語 `natural` golden 2/2 が密ベクトルでも圏外だった。差は埋め込み対象テキストで、前回の `name + signature + text[:512]`（コード本体）に対し、今回は `name + signature + doc_head`（docstring、無ければ本文先頭）にした。本リポジトリの `doc_head` は hve profile で 6,273 件中 5,432 件（86.6%）が日本語なので、日本語の問いと同一言語で照合できる経路ができる。
- 判定に足る分解能を得るため **golden を 42 → 56 問へ拡張**した（`natural` を 6 → 20 問、日本語 10 / 英語 10）。6 問は同じ着地点へ日英ペアを張り、「日本語の問い → 英語のコード」の橋渡しだけを切り出せるようにした。
- 実測（golden 56 問 / top-k=5 / 同一プロセス・同一索引スナップショット、値は top-1 / top-5）:

  | 群 | n | baseline | `--fuse` | `--semantic` |
  |---|---|---|---|---|
  | 全体 | 56 | 0.73 / 0.77 | 0.73 / 0.77 | **0.75 / 0.82** |
  | natural（日本語） | 10 | 0.00 / 0.00 | 0.00 / 0.00 | **0.10 / 0.20** |
  | natural（英語） | 10 | 0.50 / 0.70 | 0.50 / 0.70 | 0.50 / **0.80** |
  | symbol / substr / regex / trace | 36 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |

- ベクトルは本体索引ではなく **`.cq/vectors-<profile>.sqlite`** に置く。`chunks` へ列を足すと `SCHEMA_VERSION` を上げることになり、`store.py` が既存索引を fail-closed で拒否して、**既定 OFF の機能のために全利用者へ全再構築を強制する**ため。
- 分離の代償である同期ずれは、各行にファイルの SHA-1 を持たせて検出する。`chunk_id` はパスと順番から作られるので編集後も同じ id が残り、内容の照合なしでは古いベクトルが誤った場所を指す。
- **すべての失敗経路が無言で縮退する**: 任意依存不在・ベクトル不在・別モデルで作られたストア・ベクトル作成後に変更されたファイル、のいずれも「意味検索の候補が 0 件」になるだけで、検索そのものは失敗しない。
- 任意依存は `code-semantic`（`fastembed` + `numpy`）として `cq` 側に宣言した。`mdq` の `semantic` extra と同じパッケージを使うが、`cq` は `mdq` に依存しない契約（FR-CQ-01 / FR-KIT-05）なので `cq/embeddings.py` を独立に持つ。

### 既知の制約

- 日本語 `natural` は 10 問中 **2 問の到達にとどまる**。「日本語の問い → 英語のコード」の橋渡しは、多言語埋め込みを入れても大半が未解決のまま。
- 意味検索の候補が語彙層の正解を押し出す悪化がある（natural 20 問で改善 5 件 / 悪化 2 件）。
- 検索の median 応答が 159 ms → 589 ms（約 3.7 倍）。CLI は 1 プロセス 1 クエリなので、毎回全ベクトル（hve で 33.82 MiB）を読んで総当たりの cosine を取る。
- ベクトル構築のコストは hve 16,821 本 / 983.3 秒 / 33.82 MiB、app 1,552 本 / 75.1 秒 / 3.14 MiB。
- `--fuse` / `--semantic` を使うと `score` の意味が層固有のスコアから順位の逆数和へ変わる。
- fastembed 0.8 はこのモデルで mean pooling を使う（警告が出る）。モデルや fastembed の版を変えると上表は再現しない。
- 計測はローカル Windows のみ。Cloud Agent（Linux runner）では未実測。

### 意図的に採らなかった選択肢

- **LLM によるサブクエリ生成**: `hve/repository_query*` の Agentic PoC が NO-GO 判定済みで、再実験には品質・failure・cost・latency の threshold 承認が前提。加えて 1 クエリ数十 ms の同期 CLI という前提を壊す。
- **cross-encoder リランカ**（Azure の semantic ranker 相当）: 追加モデルの DL とクエリ毎の推論を要し、「任意依存ゼロで動く」前提を壊す。順位統合だけで足りるかを先に測る方針とした。
- **Azure AI Search との連携**: cq の「必須の外部依存はゼロ・ローカル完結」という前提を壊し、配布キットが成立しなくなる。生成アプリ側の Azure Agentic Retrieval 設計は `agentic-retrieval-contract` Skill が既に担当しており責務が重複する。
- **近似最近傍索引**: 16,821 件は総当たりで足り、問題になった実測が無い。

### 検証

<!-- validation-confirmed -->

- `cq/tests/` + `hve/tests/test_cq_vendor_sync.py` + `hve/tests/test_code_query_skill_wiring.py` で **773 passed**。
- 新規契約テストはすべて RED → GREEN の順序で追加した（融合 9 failed → 18 passed、意味検索 7 + 11 + 6 + 7 failed → 31 passed）。
- 各タスク完了後に敵対的レビューを実施し、指摘を反映した。反映した主なものは以下:
  1. golden の追加問 `chunk_spans` は 14 ファイルに同名があり正解が一意にならないため、リポジトリ全体で一意な `aggregate_usage_stats` へ差し替えた。
  2. 順位統合の初版がリテラル一致層を等価に扱って退行させていた（上記）。契約テストを足して修正し、再計測で rank 変化 0 件を確認した。
  3. ベクトルストアの初版が同期ずれを検査しておらず、編集後も同じ `chunk_id` の古いベクトルを使っていた。ファイル SHA-1 での検査へ直した。
  4. `cq/embeddings.py` の独立性テストが `"mdq" not in source` の部分文字列判定で、docstring 中の言及にも反応していた。import 文の形を見る正規表現へ直した（本日別途修正した同種の欠陥と同じ形）。
  5. `test_an_unavailable_backend_does_not_break_the_search` が、fastembed 導入済みの環境では実モデル（240 MiB）を読み込んでおり名前どおりの経路を検証していなかった。provider の取得を差し替えて環境非依存にした。
  6. 計測スクリプトが `regex` intent のクエリを `--q` として投げており intent 別の数字が意味を失っていた。`cq.benchmark` と同じく `regex=` で投げるよう直した。

## [0.7.1] - 2026-08-15

### Added — code-query が JavaScript / PowerShell のテストブロックを定義単位として索引するようにした（FR-CQ-04）

JavaScript の `describe` / `it` / `test` と PowerShell の Pester `Describe` / `Context` / `It` は、宣言構文ではなく単なる関数・コマンド呼び出しであるため、シンボルとして 1 件も拾えていなかった。テストのラベルを名前とする `is_test` シンボルとして抽出するようにした。

- 実測でシンボルが 1 件も取れないファイルが `app:javascript` 46/76（60.5%）、`hve:powershell` 17/29（58.6%）あり、内訳を調べると JavaScript は 42 ファイルに 120 個、PowerShell は 6 ファイルに 118 個のテストブロックが存在した。
- 改善後: `app:javascript` の該当ファイルは 46 → **4**、シンボル 196 → **353**。`hve:powershell` は 17 → **11**、シンボル 77 → **195**。`is_test` はそれぞれ 157 / 118。
- **チャンクの `name` / `signature` 列が埋まるようになった**。この 2 列は BM25 の重みが最大（10.0 / 5.0）で、テストブロックしか無いファイルは全チャンクが無名のまま索引されていた。改善後の named_chunks は `app:javascript` 279/377、`hve:powershell` 133/229。
- 実装上の要点として、`Grammar.kinds` へ登録するのは **内側の call / command ではなく外側の文ノード**（JavaScript は `expression_statement`、PowerShell は `pipeline`）である必要がある。`treesitter.chunk_spans` は `Grammar.kinds` にあるノード型だけを命名し、かつ予算に収まった時点で下位へ降りないため、内側を鍵にするとシンボルは取れてもチャンク命名が効かない。
- 残る該当ファイル（shell 15 / batch 7 / csharp 8 等）はパーサの欠陥ではないことを確認済み。shell / batch は 39 ファイルを目視して全件が宣言を持たないこと、C# は全件が top-level statements の `Program.cs` であることを実測した。

### Added — code-query の tree-sitter 文法を言語ごとに導入できるようにした（FR-CQ-11）

`code` extra は全言語の文法を一括で入れるため、使わない言語の wheel まで入っていた。

- `code-python` / `code-csharp` / `code-javascript` / `code-typescript` / `code-java` / `code-go` / `code-rust` / `code-c` / `code-cpp` / `code-scala` / `code-shell` / `code-powershell` / `code-batch` / `code-sqlglot` の 14 extra を追加した。`code`（全言語）と `code-sql`（sqlfluff）は従来どおり。
- `hve/setup-hve.ps1 -CodeLanguages python,csharp` / `hve/setup-hve.sh --code-languages python,csharp` で選択できるようにした。未知の言語名はインストールせずに fail-closed で停止する。`-Minimal` / `--minimal` とは併用できず、警告して無視する。
- `.h` の内容判定には C / C++ の両文法が要るため、`code-c` / `code-cpp` はどちらも 2 つを入れる。
- `code` extra が言語別 extra の和集合であること、setup スクリプト（ps1 / sh 両方）が提供する言語名が extra 一覧と一致することをテストで固定した。

### Fixed — code-query が markdown-query の任意依存を借りていたのをやめた

`cq` が必要とする `watchdog`（`cq watch`）と `tiktoken`（トークン計上）は、`mdq-watch` / `mdq` extra の導入を案内していた。`mdq` を使わない利用者に `mdq` の依存が付き、`mdq` 側の変更が `cq` を壊す構造だった。

- `code-watch` / `code-tokenizer` として `cq` 側に宣言し、users-guide の導入手順と失敗時対処表から `.[mdq-watch]` / `.[mdq]` の案内を除いた。
- CI（`test-hve-python.yml`）が `pip install pytest tiktoken` で個別導入していた回避策をやめ、`pip install -e ".[code,code-sql,code-watch,code-tokenizer,test]"` へ戻した。

### Fixed — cq → mdq の独立性ガードが `from mdq import ...` を検出できていなかった（FR-CQ-12）

`cq` が `mdq` を import しないことを検査するテストが `"import mdq" in source` の部分文字列判定で、`from mdq import ...` を見逃していた（逆方向の `mdq` → `cq` は正規表現で全形式を見ており非対称だった）。

- 両方向を `^[ \t]*(?:import|from)[ \t]+<package>\b` の正規表現へ揃え、4 つの import 形式を parametrized テストで固定した。
- 実行時の相互 import は静的・動的の両方で 0 件であることを確認済みで、実害は出ていない。

## [0.7.0] - 2026-08-15

### Notes — MINOR を 1 つ増やした（0.6.4 → 0.7.0）

利用者の明示指示による MINOR の引き上げ。`[Unreleased]` に後方互換のある機能追加（`Added` / `Changed`）が積まれており、[hve-dev/hve-app-tools.md](hve-dev/hve-app-tools.md) §3.3 の「最もインパクトの大きい変更に合わせて bump 種別を決定する」に沿って PATCH ではなく MINOR を選んでいる。

本エントリー自体は機能・振る舞いの変更を含まない。変更は版番号の同期先 3 箇所（[pyproject.toml](pyproject.toml) の `[project].version` と `[tool.bumpversion].current_version`、[hve/\_\_init\_\_.py](hve/__init__.py) の `__version__`）と本ファイルの版見出しだけである。

`[Unreleased]` の既存エントリーは本リリースへ取り込んでいない。並行ジョブの記録を誤って別リリースへ含めないため、`bump-my-version` の見出し自動挿入（`## [Unreleased]` の直後へ挿入する）は使わず、既存内容の後ろへ版見出しを手動配置している（[.github/copilot-instructions.md](.github/copilot-instructions.md) §0 / [hve-dev/hve-app-tools.md](hve-dev/hve-app-tools.md) §2.2）。

FR-MAINT-08 の `requires_version_bump` はこれら 3 ファイルをいずれも除外するため、本変更はさらなる版更新を要求しない。

**検証**: 版番号 4 箇所（`[project].version` / `[tool.bumpversion].current_version` / `__version__` / 本ファイルの版見出し）が `0.7.0` で相互一致することを確認。`hve/tests/test_hve_surface_inventory.py` と `cq/tests/test_surface_export.py` が PASS（`[tool.bumpversion]` 設定との列挙一致テストを含む）。

<!-- validation-confirmed -->

## [0.6.4] - 2026-08-15

### Fixed — Pre-QA と Work IQ の保存契約を fail-closed のまま修復した（FR-QA-03）

AAS Step.1 の事前 QA で、Work IQ の複数行 Markdown 応答を table cell へそのまま埋め込むと、保存後の再解析が最初の質問しか読み取れず、「期待 3 / 実際 1 / 質問 1 の回答が空」で停止していた。保存後 validator は破損を正しく検出しており、原因は validator ではなく Work IQ 応答のシリアライズと採否境界だった。

- **Markdown table cell の CRLF / CR / LF を `<br>`、pipe を `&#124;` へ正規化した**。1 質問 1 物理行を維持し、render → save → read-back → parse で質問番号と全回答を保持する。
- **Work IQ 実行確認を MCP server/tool の厳密な組へ限定した**。内部経路の `_hve_workiq` / `ask_work_iq`、公式経路の `workiq` / `ask` を許可し、server 名のない legacy event は `ask_work_iq` だけを後方互換で許可する。bare `ask` と別 server の `ask` は拒否する。
- **raw draft と QA 統合対象を分離した**。tool event を確認でき、status が `FOUND` / `PARTIAL` の応答だけを回答済み QA へ統合する。`NOT_FOUND` / `UNAVAILABLE` / status 不明 / tool 未確認は未統合理由と原文を draft に残す。
- **保存後 validator は緩和していない**。同じ質問数・全回答非空の検証を通過してからだけ QA 起点 AKM を dispatch する既存契約を維持した。
- 要求定義と要求テストマッピングを更新し、公式 generator で feature / test / surface inventory と crosswalk を同期した。

**影響範囲**: CLI / GUI 共通の HVE 事前 QA 経路。AAS 固有 Prompt、Skill、`docs/**`、`src/**`、既存 `qa/**` 生成物は変更していない。

**検証**: 新規 RED は serializer 4件、tool identity/status 4失敗+4既存互換PASS、Pre-QA合成2件で本番例外を再現し、同じテストを変更せずGREEN化した。Focused **334 passed + 7 subtests**、広範回帰 **747 passed + 13 subtests**、inventory/scope/traceability/surface export **223 passed**。`py_compile`、合成3問round-trip、`git diff --check`、追加行の秘密情報パターン検査がPASS。ruffは環境未導入のためSKIPした。

<!-- validation-confirmed -->

## [0.6.3] - 2026-08-15

### Changed — HVE 対象変更時の PATCH 更新を Copilot の自律実施へ強制した

[.github/copilot-instructions.md](.github/copilot-instructions.md) §0「HVE の版管理と変更履歴」は版更新を 必須 と定めていたが、PATCH の項が「既定では PATCH を 1 ジョブにつき 1 回だけ増やす」という弱い言い回しで始まり、直後に MINOR を対象とした「Copilot が自律的に増やしてはならない」が続いていた。この並びは、指示が無いジョブで版更新を見送る誤読を誘発しやすい。

- **PATCH の更新を「必須・確認不要の自律実施」として明記した**。指示・承認を待たずに 1 ジョブにつき 1 回増やすこと、および「指示が無い」「差分が小さい」「文書だけの変更に見える」「別ジョブと競合しうる」「既存の `[Unreleased]` がある」を省略理由にできないことを列挙した。判断に迷う場合は更新する側へ倒す。MINOR の制限（ユーザーの明示判断のみ）は従来どおり維持し、PATCH との適用範囲を文上で分離した。
- **見出し行へ「ユーザーからの指示・依頼の有無にかかわらず」を追加した**。
- **完了報告前の版更新セルフチェックを必須化した**。変更パス一覧を取得して対象判定の機械正本に照らし、(a) 3 ファイルの揃い、(b) 4 箇所の版番号の相互一致、(c) 直前の版からの増加を確認し、未充足なら完了報告を出さずに版更新を実施する。確認結果は §7.1 の検証結果へ 1 行で記録させる。

変更は `.github/copilot-instructions.md` の §0 のみで、対象境界・版管理境界の機械判定（[.github/scripts/hve_scope.py](.github/scripts/hve_scope.py)）は変更していない。同ファイルは版更新を要求するパスのため、本変更自体も PATCH を 1 回増やしている（0.6.2 → 0.6.3）。

**検証**: `hve/tests/test_hve_requirement_traceability_contract.py` と `.github/scripts/tests/test_validate_hve_requirement_traceability.py`、`hve/tests/test_hve_surface_inventory.py` が PASS（repository-wide instructions のルーター制約と版管理境界の回帰を確認）。版番号 4 箇所が `0.6.3` で相互一致することを確認。

<!-- validation-confirmed -->

## [0.6.2] - 2026-08-15

### Notes — PATCH を 1 つ増やした（0.6.1 → 0.6.2）

利用者の明示指示による PATCH の引き上げであり、機能・振る舞いの変更は含まない。変更は版番号の同期先 3 箇所（[pyproject.toml](pyproject.toml) の `[project].version` と `[tool.bumpversion].current_version`、[hve/\_\_init\_\_.py](hve/__init__.py) の `__version__`）と本ファイルの版見出しだけである。

FR-MAINT-08 の `requires_version_bump` はこれら 3 ファイルをいずれも除外するため、本変更はさらなる版更新を要求しない。

**検証**: 3 箇所が `0.6.2` で相互一致することを確認。`hve/tests/test_hve_surface_inventory.py` と `cq/tests/test_surface_export.py` で 162 passed（`[tool.bumpversion]` 設定との列挙一致テストを含む）。

<!-- validation-confirmed -->

## [0.6.1] - 2026-08-15

### Added — 版更新を要求するパスの判定を対象境界と同一モジュールへ追加した（FR-MAINT-08）

[.github/copilot-instructions.md](.github/copilot-instructions.md) §0「HVE の版管理と変更履歴」は、版更新の対象判定の「単一の機械正本」を [.github/scripts/hve_scope.py](.github/scripts/hve_scope.py) と定めている。しかし同モジュールは要求トレーサビリティ用の対象境界（`is_in_scope` / `is_out_of_scope`）しか持たず、版管理規則が要求する境界を表現していなかった。

**根本原因**: 版更新を要求するパスの集合は対象境界と一致しない。対象境界には `pyproject.toml` と `hve/__init__.py` が含まれるため、`is_in_scope` をそのまま流用すると **版更新のための変更自体が次の版更新を要求し、規則を充足できる状態が存在しなくなる**。また §0 が独立ライフサイクルとして除外する `mdq/**` / `cq/**` / 配布キットも対象境界には含まれる。

**修正内容**:
- `requires_version_bump(path)` を `hve_scope.py` へ追加した。対象境界の判定結果を入力とし、そこから (1) 版番号・変更履歴の同期先ファイル自身（`VERSION_BUMP_FILES`）と (2) 独立ライフサイクルのパス（`INDEPENDENT_VERSION_PREFIXES`）を除いたものだけを True とする。
- (1) の列挙が `pyproject.toml` の `[tool.bumpversion]` からドリフトすると除外が欠けるため、設定と一致することを契約テストで固定した。
- `mdq.toml` / `cq.toml` は engine 本体ではなくリポジトリ側の設定であり、§0 の除外列挙が `mdq/**` / `cq/**` / 配布キットに限られるため、除外に含めず版更新の対象として扱う判断を要求定義へ明記した。
- 要求定義 §3.7 へ「版管理境界」節と FR-MAINT-08 を新設し、要求テストマッピングと索引 CSV を同期した。

**本変更のスコープ外**: 本判定を消費する CI ゲート・不変条件の契約テスト・pre-push hook は含まない。述語の追加までであり、既存の実行経路の振る舞いは変わらない。

**主な変更ファイル**: [.github/scripts/hve_scope.py](.github/scripts/hve_scope.py) / [hve/tests/test_hve_surface_inventory.py](hve/tests/test_hve_surface_inventory.py) / [hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) / [hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md)

**検証**: 実装前 RED = `hve/tests/test_hve_surface_inventory.py::TestVersionBumpScope` が 53 failed。実装後 GREEN = 同ファイル 146 passed（新規 53 件を含む）。回帰確認として `.github/scripts/tests/test_validate_hve_requirement_traceability.py` / `hve/tests/test_hve_requirement_traceability_contract.py` / `hve/tests/test_norm_literal_single_implementation.py` が 110 passed / 2 skipped、`cq/tests/test_surface_export.py` が 16 passed。`hve-dev/generate_tdd_inventory.py` を再実行し、FR-MAINT-08 が `active-or-described` として機能索引へ、新規テスト 6 件がテスト索引へ登録されることを照合した。

<!-- validation-confirmed -->

## [0.6.0] - 2026-08-14

### Changed — HVE と検索関連パッケージのマイナーバージョンを更新

- HVE を `0.5.5` から `0.6.0` へ更新し、project / bumpversion / `hve.__version__` / editable distribution metadata を同期した。
- Code Query を engine / Skill `0.3.0` → `0.4.0`、独立 GUI `0.2.0` → `0.3.0`、移植用キット `1.2.0` → `1.3.0` へ更新した。
- Markdown Query を engine / Skill `0.7.0` → `0.8.0`、独立 GUI `0.2.0` → `0.3.0`、移植用キット `1.2.0` → `1.3.0` へ更新した。
- Tool Search 移植用キットを `1.2.0` から `1.3.0` へ更新した。
- Code Query / Markdown Query の vendor、Skill bundle、共通 kit は正本から再生成し、運用表を同期した。実行時の機能・公開 API は変更していない。

**検証**: vendor byte 一致、Skill bundle、共通 kit、他リポジトリ配布契約の 5 スイートで **180 passed**。全版番号の機械照合、TOML parse、実行時 import、`hve.egg-info/PKG-INFO` の `0.6.0` 反映、および変更ファイルの静的診断 0 件を確認した。

<!-- validation-confirmed -->

## [0.5.5] - 2026-08-14

### Added — QA 回答を保存・検証したうえで Knowledge Management へ都度同期するようにした（FR-QA-03 / FR-CLOUD-21 / FR-CLOUD-24）

実行前 QA で得た回答は、その場のメインタスクに注入されるだけで `knowledge/` へ還元されておらず、`akm` を手動で起動しない限り蓄積されなかった。回答済みファイルの保存すら Cloud 経路には存在せず、Issue コメントとして流れて消えていた。

- **CLI / GUI で、回答済み QA を保存・検証してから AKM をバックグラウンド起動するようにした（FR-QA-03）**。ユーザー回答または明示された既定値を全質問へ適用した Markdown を `qa/` へ保存し、最終パスを再読込して内容・質問数・文書状態（`回答済み` または `推論補完済み`）・各質問の非空回答を検証する。検証を通るまでメインタスクを開始しない。質問が 0 件のときは同期対象なしとしてそのまま続行する。
- **メインの DAG は AKM の完了を待たない**。検証済みファイル 1 件ごとに `--sources qa` / 当該 `--target-files` / `--no-force-refresh` で AKM 子プロセスを登録し、キューが受理した時点で次 Step へ進む。子へは許可した実行品質設定だけを渡し、`--auto-qa` は渡さない（既定の無効のまま）。AKM 同士は FIFO かつリポジトリ単位のロック（`.hve/qa-akm.lock`、Windows は `msvcrt.locking` / POSIX は `fcntl.flock`）で直列化し、明示実行の `akm` とも排他する。Git commit / branch 切替 / GUI cleanup の各境界では未完了の書き込みを残さないよう待ち合わせる。
- **Cloud で回答コメントを回答済み QA として保存するようにした（FR-CLOUD-24）**。イベントの回答コメント ID を一次キーとして当該 Issue への帰属を検証し、回答時刻（同秒時はコメント ID）より前の最新質問票とだけ対応付けて正規化する。`qa/Issue-<N>-questionnaire-answered-<sha8>.md` の固定パスへ保存し、Contents API の再取得結果と SHA を照合する。照合後に QA 回答本文と保存済み QA パスを Issue body へ注入してから Copilot をアサインするため、メインタスクは保存済みファイルを確実に参照できる。保存 job だけに `contents: write`、dispatch job だけに `actions: write` を与える。
- **AKM の起動は非同期にした**。保存成功後に `auto-akm-after-qa.yml` を `workflow_dispatch` し、API が受理した時点で source Workflow は続行する。調整 Workflow 側は `<!-- qa-akm-sync: source-issue=<N>; qa-sha=<64hex>; branch=<branch> -->` を冪等キーとし、`qa-akm-sync` ラベル付き Issue の REST pagination 走査に加えて全 Issue のマーカー走査へフォールバックする。Root Issue はラベル付きで作成し、部分失敗で routing ラベルが欠けた既存 Root はポーリング前に自己修復する。タイムアウト判定の直前に終端状態を再取得し、完了済み Root へ `akm:blocked` を誤付与しない。
- **調整 Workflow と子 AKM の自己デッドロックを避ける concurrency 分離を入れた（FR-CLOUD-21）**。調整 job はリポジトリ単位の `akm-knowledge-write-<repo>` を保持したまま子 AKM の終端を待つため、`qa-akm-sync` ラベルを持つ Root / Step の reusable AKM だけを `akm-qa-sync-child-<repo>` で直列化する。通常 AKM は従来どおり大域 group に残し、QA 同期 Root のラベルは Step Issue 作成時のラベルへ伝播する。
- **再帰を禁止した**。`workflow_id=akm` の実行は QA 起点 AKM を登録せず、AKM Root Issue から別の QA 起点 AKM を再帰生成しない。

**検証**: 回答済み QA の検証・非待機 dispatch・FIFO / ロック排他・Git 境界の drain・Cloud の保存と冪等 dispatch を RED → GREEN で確認した。`test_qa_merger.py` / `test_runner_pre_qa.py` / `test_runner_qa_phase.py` / `test_workflow_registry_agentic.py` / `test_aqod.py` / `test_materialize_answered_qa.py` の **311 passed + 6 subtests**、`test_orchestrator.py` の **201 passed + 77 subtests**、GUI の QA IPC 経路 **3 passed**。`hve/tests` 全体回帰は **7,389 passed / 17 failed / 18 skipped / 2 xfailed / 494 subtests** で、失敗はいずれも本変更に起因しない。内訳は索引 stale 1 件（`test_hve_surface_inventory.py::test_csv_is_not_stale`。再生成で解消し、索引整合 154 件が PASS）、GUI import 2 件（`test_gui_imports.py` の `test_app_importable` / `test_main_window_importable`。単独実行では同ファイル 28 件が PASS するテスト間干渉）、並行作業中の `mdq` vendor ツリー 7 件（`test_mdq_vendor_sync.py` 6 件と `test_distributed_tree_has_no_upstream_dependency.py[mdq]`）、本変更が触れていないファイル 7 件（`test_asdw_data_azure_cli_scope_contract.py` 2 件、`test_asdw_data_create_validation.py`、`test_asdw_web_step_scoped_cicd_contract.py`、`test_dev_task_environment_contract.py`、`test_main_entrypoints.py`、`test_orchestrator.py::TestRunWorkflowFanout::test_aad_web_fanout_meta_is_forwarded_to_step_runner`）。最後の 1 件は clean HEAD を別 worktree に取り出して同一環境で実行しても同じく失敗することを確認した。

<!-- validation-confirmed -->

### Changed — AQOD を共通の事前 QA 経路へ統合し、QA 状態ラベルの遷移を厳格化した（FR-QA-03 / FR-CLOUD-24）

- **AQOD の「事前 QA 常時スキップ」を廃止した**。他ワークフローと同じ `check_qa_skip` と `*:qa-ready` / `*:qa-drafting` 経路を使う。Cloud では質問票設定が有効なとき Step Issue へ `aqod:qa-ready` を付与してメインの Copilot アサインを保留し、回答後の共通遷移でアサインする。既存 QA を検知した場合は従来どおり直接アサインする。
- **Copilot の質問票生成 PR が opened になっただけでメインタスクを開始しないようにした**。従来は PR opened で `*:qa-drafting` / `*:qa-ready` から `*:ready` + `*:running` まで進んでいたため、回答の保存・検証・AKM 同期を経ずにメインタスクが走り得た。質問票コメントを確認したうえで `*:qa-drafting` → `*:qa-ready`（回答待ち）までに限定する。
- **`*:qa-ready` と `*:qa-drafting` が同時に複数存在する状態を全入口で失敗させるようにした**。従来は先頭 1 件を採用していたため、状態機械が壊れたまま遷移が進んでいた。あわせてラベル遷移は新状態の付与と read-back を先に行い、旧状態の削除後にも再検証して不整合なら旧状態へ戻す。

**検証**: AQOD の `check_qa_skip` 接続・QA 有効時のメインアサイン保留・ゲートの状態ラベル判定を RED → GREEN で確認した（`test_aqod.py` 16 件）。PR opened 経路の限定と複数 QA 状態の fail-closed、ラベル遷移の add-first / read-back / rollback は `test_workflow_registry_agentic.py` と `test_prompts.py` の契約テストで固定した。Issue Template・実行オプション・レビュー設定の横断整合は `test_issue_template_qa_parity.py` / `test_phase6_option_parity.py` / `test_adversarial_review_policy_contract.py` の **123 passed + 240 subtests** で確認した。あわせて `auto-aqod.yml` のゲート判定に埋め込んだ Python が YAML パースでは検出できないインデント崩れを起こしていたため修正し、ヒアドキュメント内 Python を `compile()` で構文検証する回帰テストを追加した。

<!-- validation-confirmed -->

### Changed — GUI の「QA 自動投入」を右ペインの必須選択にした（FR-GUI-16）

QA 回答から Knowledge Management への同期を起動するかどうかは `auto_qa` が唯一の入口だが、この項目は Step 1 右ペインに表示されておらず、設定画面を開かない限り既定値 `False` のまま「QA なし＝AKM 同期なし」が暗黙で確定していた。

- **ワークフローを選択すると右ペイン最上部の共通枠に「QA 自動投入」を常時表示するようにした**。全ワークフロー共通の設定であり、`_LabeledField` は単一インスタンスを共有するため、ワークフロー枠ではなく共通枠に置く。枠の見出しは実態に合わせて「共通設定  *必須」とした。
- **チェックボックスを「未選択 / 有効にする / 無効にする」の 3 状態セレクタに変えた**。既定は未選択で、未選択のままでは `validate()` が実行を許可しない。既定値による暗黙決定を残さないための必須化であり、他の必須入力と同じく見出しに `*必須` を付ける。
- **「QA 回答モード」も同じ枠に併記し、「有効にする」を選んだときだけ活性化するようにした**。
- **永続化表現を他の 3 状態項目と同じ `"" / "on" / "off"` に統一した**。「未選択」を `False` として保存しない。旧 `true` / `false` の保存値は未選択として扱う。`auto_qa` は起動時に復元せず、実行ごとの明示選択を求める。
- **設定画面を閉じただけで右ペインの選択が巻き戻る欠陥を塞いだ**。設定画面は独立した `_C3AutoPrompt` を持ち、閉じるだけでも autosave → `settings_changed` → 右ペインへの再適用が走るため、必須項目が未選択へ戻って実行不能になる（あるいは stale な on/off に化ける）経路があった。`C10.app_ids` と同じ `skip_keys` 方式で `C3.auto_qa` を保護する。必須ではない `qa_answer_mode` は保護対象に含めず、起動時に保存値を復元する従来動作を維持する。
- **タイトルを定数化した際に翻訳対象から外れていたのを戻した**。`QT_TRANSLATE_NOOP` で登録し、表示時に翻訳を解決する。新規文言の英訳を追加して `.qm` を再生成した。

**検証**: FR-GUI-16 の契約を RED → GREEN で確認（新規 9 件）。設定画面 close 経路の巻き戻し防止に 4 件を追加。仕様変更で前提が変わった既存テストは、C3 の可視フィールド一覧・設定値の round-trip・CI/CD 認証検証の 3 系統を新契約へ同期した。`test_page_options_auto_qa_required.py` / `test_settings_apply_skip_keys.py` / `test_page_options_github_cicd.py` の 45 件、および i18n を含む 38 件が PASS。`QTranslator` を実ロードして新規 6 文言の英訳解決を確認した。GUI 全体回帰は 1,427 passed / 4 failed で、失敗の内訳は CI/CD 認証検証 3 件（必須化に伴う前提不足。本作業で同期して解消）と、後述の `cq` 言語別内訳 1 件（本作業で解消）である。要求定義・要求テストマッピング・索引 CSV を再生成し、`FR-GUI-16` が `active-or-described` として登録されていることを照合した。

<!-- validation-confirmed -->

### Fixed — `cq` の言語別内訳で C# / JavaScript を regex と説明していた記述を実態へ揃えた

C# と JavaScript は tree-sitter 主・regex フォールバックへ移行済みだが、「パーサを共有する言語を行として分ける」ことを示す例として regex を挙げたままの箇所が残っていた。

- **`cq/store.py` の docstring を tree-sitter へ修正し、vendor コピーも同一内容へ揃えた**。全体再同期ではなく当該箇所だけを手当てし、並行作業中の他ファイルを巻き込まないようにした。
- **GUI 側の回帰テストを実態へ同期した**。`test_languages_sharing_a_parser_stay_separate` は regex を前提にしており実行時に失敗していた。テストの意図（パーサを共有しても言語行は分離される）は変えず、期待するパーサ名だけを tree-sitter へ揃えた。

**検証**: `test_cq_settings_section.py` を含む関連 81 件が PASS。`cq` 本体と vendor コピーの同期検査も PASS し、source と vendor が同一内容であることを確認した。

<!-- validation-confirmed -->

## [0.5.4] - 2026-08-14

### Added — GUI から Tool Search の検索ポリシーを編集できるようにした（FR-GUI-07）

設定画面の Tool-Search「ポリシー」タブは `hve/toolsearch/policy.json` を読み取り専用で表示するだけで、pin や検索語彙を変えるにはファイルを直接開いて JSON を書く必要があった。キー形式（`{種別}:{サーバー}:{ツール名}`）や `limit <= max_limit` の制約はファイルを読み込む時点まで分からず、初めて触る利用者には各項目が何をする値なのかも読み取れなかった。

- **同じタブから編集して保存できるようにした**。`version` を除く全項目（`limit` / `max_limit` / `tau` / `field_weights` / `pins` / `additional_search_text` / `step_overrides`）を数値入力と表形式で編集する。表には「行を追加」「選択行を削除」を付けた。`version` は書式のバージョンであり設定値ではないため表示のみとする。
- **各項目に「?」の説明を付けた**。値の意味・増減したときに何が起きるか・既定値を、初めて触る利用者向けに記述し、`users-guide/tool-search.md` へのリンクを添えた。説明文の実体は [hve/gui/help_content.py](hve/gui/help_content.py) が単一の情報源として持ち、GUI セクション側へ二重に置かない（FR-MAINT-07）。あわせてセクション全体を翻訳カタログの抽出対象へ加え、日本語 61 件・ポリシー説明 8 件を英訳して `.qm` を再生成した（英語表示で日本語が残らないこと、`.qm` が stale でないことを試験で固定）。
- **保存を fail-closed にした**。書き込み前に `ToolSearchPolicy.from_dict()` と同じ検証を通し、キー形式違反や `limit > max_limit` があるとファイルを 1 バイトも変更せずに理由を表示する。`limit` と `max_limit` の入力欄を相互に連動させていないため、矛盾した入力が黙って丸められることはない。読み込みに失敗している状態からは保存できない（既存の内容を空値で上書きしないため）。
- **表示したファイルへそのまま書き戻すようにした**。保存先は画面上部に表示している「参照元 / 保存先」と同一で、`ToolSearchPolicy.default_path()` の解決結果に従う。保存後は「次に開始する Step 実行から反映される」ことを明示し、実行中セッションへ即時反映されるかのような表示をしない。
- **保存 API を `hve/toolsearch/policy.py` に置いた**。`ToolSearchPolicy.to_dict()` / `save()` を追加し、既存ファイルのトップレベルにある未知のキー（`_comment` 等）を保持したまま既知フィールドだけを差し替える。改行は LF 固定・BOM なし・非 ASCII はエスケープしない。既存ファイルが JSON として壊れている場合は未知キーの保持を保証できないため、書き込まずに `PolicyError` を返す。
- **GUI の選択肢と検証側の集合の乖離をテストで塞いだ**。`field_weights` の 4 項目・pin の 3 値・Step の 2 値は GUI と `policy.py` の双方に現れるため、片方だけ変更すると「GUI の入力が必ず保存に失敗する」か「検証側が受け付ける値を GUI から選べない」状態になる。両者の一致を固定する試験を追加した。
- **小数入力欄が既存の値を丸めないようにした**。`QDoubleSpinBox` は `decimals` で値を量子化するため、桁数を固定すると `tau: 0.456` のポリシーを**編集せずに保存しただけで** `0.46` へ書き換わる（実測で確認）。読み込んだ値を丸めずに表示できる桁数まで広げてから入力欄へ入れる。

**影響**: GUI からのポリシー編集のみに影響する。ランキング実装・検索結果・`policy.json` のスキーマは変更していない。保存すると JSON 内の空行は失われる（JSON に空行を表現する構文が無いため）が、値と未知キーは保持される。

### Fixed — 実行時のポリシー解決先が GUI の表示・保存先と食い違う問題を修正した（FR-TS-03）

実行時（[hve/toolsearch/session.py](hve/toolsearch/session.py) `build_session_toolset`）は `ToolSearchPolicy.load()` をリポジトリルート無しで呼んでおり、常に同梱の `hve/toolsearch/policy.json` を読んでいた。一方で GUI の表示・保存先はリポジトリルート直下の `.toolsearch/policy.json` を優先する。上書きファイルを置くと「GUI では変更できたのに実行時には効かない」状態になり、しかも失敗としては現れなかった。

- **解決規則を 1 つに揃えた**。実行時も `ToolSearchPolicy.load(repo_root=...)` を通し、表示・保存・実行時の 3 者が `ToolSearchPolicy.default_path()` の同一結果を使うようにした。読み込みに失敗したときに SDK 既定へフォールバックして Step を落とさない既存の挙動は変えていない。
- **安全境界は変わらない**。pin の増減は「何を返すか」だけを変え、呼び出しの禁止は従来どおり `excluded_tools` と MCP サーバー設定の `tools` allowlist が担う。

**影響**: `.toolsearch/policy.json` を置いている環境でのみ挙動が変わる（本リポジトリには存在しない）。同ファイルが無い環境では同梱ポリシーを読む従来どおりの動作。

### Fixed — Tool Search 周辺の陳腐化した記述と型定義を修正した

- **GUI のタブ一覧を実態に合わせた**。[users-guide/tool-search-dashboard.md](users-guide/tool-search-dashboard.md) は「3 つのタブ」と書いていたが実際は 5 タブで、Skill Layer とコンテキスト内訳が表から欠けていた。[users-guide/tool-search.md](users-guide/tool-search.md) の「ポリシーの確認」も編集可能になった実態と食い違っていた。
- **`policy.json` の解決先をガイドへ明記した**。どのファイルが読まれるか（`.toolsearch/policy.json` → 同梱ファイル）を §6 冒頭に追加した。従来この説明はどこにも無かった。
- **削除済み成果物への参照を外した**。`hve/toolsearch/policy.json` の `_comment` が存在しない `work/hve-tool-search/contracts/core-tool-selection.md` を出典として指していたため、恒久ドキュメントの該当節へ差し替えた。
- **pin の型注釈を実装と一致させた**。`skill_manifest_pins` / `ToolSearchContext.manifest_pins` / `apply_policy` が `str` を渡しており、`ToolEntry.pin`（`Literal["always","auto","never"]`）に対する型エラーが残っていた。いずれも `PinMode` へ揃えた。実行時の検証（`ToolEntry.__post_init__`）は従来どおり。

**検証**: RED 23 failed（保存 API 7 件 / GUI 16 件）→ GREEN。ポリシー編集の対象 2 ファイル 100 passed、Tool Search 関連 356 passed、i18n と設定画面の GUI 関連 80 passed。実行時ポリシー解決は `.toolsearch/policy.json` の上書きが効かないことを RED（`limit` が 2 ではなく 5）で確認してから修正した。翻訳は `.qm` を再生成し、`en_US` を実際にロードして「保存 → Save」等が返ることを確認した。要求定義（FR-GUI-07 / FR-TS-03）と要求テストマッピングを改訂し、索引 CSV を再生成した。

<!-- validation-confirmed -->

## [0.5.3] - 2026-08-14

### Fixed — 版管理規約が HVE の生成するアプリケーションへ波及しうる範囲漏れを閉じた

導入済みの版管理規約は対象を allowlist で列挙しており、`src/**` や `docs/**` など生成アプリの主成果物はもともと対象外だった。しかし `.github/workflows/**` を無条件に対象としていたため、HVE が生成するデプロイ workflow を出力する Step が HVE 本体の版上げを要求され得た。

- **生成アプリのデプロイ workflow を明示的に対象外にした**。`.github/workflows/deploy-*.yml` / `azure-static-web-apps-*.yml` / `app<数字>*.yml` は、ASDW-WEB Step 3.4・ADFDV Step 3・AAGD Step 3 が生成宣言する成果物であり、既存の対象境界でも対象外と定義されている。
- **生成アプリ成果物全般の除外を規約本文へ明記した**。`src/**`、`docs/**`、`docs-generated/**`、`knowledge/**`、`qa/**`、`original-docs/**`、`sample/**`、`tests/run/**`、`package.json` / `jest.config.js` / `babel.config.js` / `playwright.config.js` だけの変更では HVE の版を上げない。
- **境界判定の正本を単一化した**。規約の列挙と機械判定が食い違う場合は `.github/scripts/hve_scope.py` を正とすると定め、列挙のドリフトが規約を壊さないようにした。あわせて `.github/scripts/**` を対象側の列挙へ補った。
- **利用者ガイドにも同じ境界を記載した**。

**影響**: HVE が設計・開発するアプリケーションを生成・変更するジョブは、HVE の版上げと変更履歴記載を要求されない。HVE 自身の保守ジョブの扱いは変わらない。

<!-- validation-confirmed -->

## [0.5.2] - 2026-08-14

### Removed — 廃止済み APP-04 テスト仕様生成器と HVE 保守対象の専用例外

- **入力・出力が既に存在しない APP-04 専用生成器を削除した**。HVE が設計・開発を支援するアプリケーションの旧成果物を、HVE 本体リポジトリのルート `tools/` に残さないようにした。
- **削除済みファイル名だけを対象外とするスコープ例外を撤去した**。§3.7、単一の scope validator、および両方の契約テストから同じ例外を削除し、現行の対象境界とテストの期待値を同期した。

**影響**: 廃止済み生成器を直接実行する経路は提供しない。HVE の対象境界は、現存する対象パス規則だけで判定する。

**検証**: `TestSharedScopeModule` とトレーサビリティ契約テストを実行し、129 passed、2 skipped。公式の `hve-dev/generate_tdd_inventory.py` を連続 2 回実行して索引を再生成した。

<!-- validation-confirmed -->

## [0.5.1] - 2026-08-14

### Added — HVE 関連ジョブの版管理と変更履歴同期を必須化

- **HVE の実装・Prompt・Skill・Workflow・契約を変更するジョブ**では、完了報告前に `CHANGELOG.md` への記録と PATCH 版の更新を必須にした。1 ジョブで増やす PATCH は 1 回だけとし、`pyproject.toml` の 2 か所、`hve.__version__`、変更履歴の版見出しを同じ値へ同期する。
- **MINOR 版の更新はユーザー判断に限定した**。`x.y.0` の `y` を増やすのはユーザーが明示的に判断した場合だけであり、Copilot は自律的に MINOR を上げない。
- **利用者向けの版管理手順を追加した**。HVE をカスタマイズする利用者が、対象範囲、PATCH / MINOR の判断、同期対象、既存の `[Unreleased]` エントリーを誤ってリリースへ含めない方法を確認できるようにした。
- **既存のリリース手順書も整合させた**。`bump-my-version` の見出し自動挿入は、全 `[Unreleased]` エントリーを同一リリースへ含める一括リリースだけに限定し、Copilot ジョブでは既存エントリーを保持して手動同期する。
- **対象外の境界を明示した**。独立ライフサイクルで版管理する `mdq/**` / `cq/**` / 配布キットは本規則の PATCH 対象とせず、従来の独立手順を維持する。

**影響**: 今後の HVE 関連ジョブでは、同一変更セット内での PATCH 版・変更履歴同期が必須になる。MINOR 版を上げる判断権限は引き続きユーザーに残る。

**検証**: トレーサビリティ契約 94 passed / 2 skipped、規約ファイルを参照する契約テスト群 188 passed、ASDW / 開発環境契約 81 passed / 1 failed。失敗 1 件（`test_copilot_sdk_lock_pins_an_exact_version`）は本変更が触れていない SDK lock ファイルの改行コードに起因する既存不具合で、`git show HEAD` の内容が既に CRLF であることを確認済み。あわせて `pyproject.toml` の TOML 構文と 2 か所の版番号、`hve.__version__`、`CHANGELOG.md`、利用者ガイド、リリース手順書の必須記載、変更差分の空白エラーを確認した。

<!-- validation-confirmed -->

## [0.5.0] - 2026-08-13

### Changed — GUI の Tool-Search 設定を実挙動に合わせ、コンテキスト内訳を実測できるようにした（FR-GUI-07 / FR-TS-10 / FR-TS-11）

設定画面が「遅延ロードでトークンを削減する」と説明していた一方、同時期の実測では遅延公開が一度も発火していなかった。説明・統計・ダッシュボードが揃って実態と食い違っていたため、表示を実測に合わせ、実測手段そのものを製品機能として追加した。

- **基本タブの説明から未発火の機能を約束する記述を外した**。GitHub Copilot CLI 1.0.79 では `tool_search` の ON / OFF で `toolDefinitionsTokens` が変わらず（無効・`defer_threshold=1` ともに 52,756）、全ツールの `defer_loading` が `null`、`tool_search_tool` はツール一覧に現れない。ランキングを `hve` にすると Skill がツールとして登録されるだけで 47,115 → 59,275 tokens（**+12,160**）に増える。計測日と CLI バージョンを併記して画面に明示した。
- **統計が 0 件のとき、未充足の収集条件を表示するようにした**。設定値から判定できる条件（遅延ロード OFF / ランキングが SDK のまま）だけを列挙し、画面から確認できない条件（CLI が `tool_search_tool` を公開しているか）は原因と断定せず観察事実として提示する。
- **`token_reduction` を無効表示できるようにした（FR-TS-10）**。`deferral_inactive_rate` が 1.0 のとき削減率は成立しないため、テキスト / HTML では「無効（遅延公開が発火していない）」と表示し、JSON では値を残したうえで `token_reduction_valid` を併せて出力する。
- **`hve toolsearch context` を新設した（FR-TS-11）**。`contextInfo` / `getContextAttribution` / `getCurrentMetadata` から、モデル名・上限・システムプロンプト・ツール定義（うち MCP）・MCP サーバーごとの実トークン数とツール数を取得する。Step 実行と同じセッション生成経路を使い、`send` を呼ばないためモデル推論も quota 消費も発生しない。`hve/toolsearch/eval.py` の推定トークンは参照しない。宣言済み MCP サーバーの接続を最大 60 秒待ち、時間内に接続しなかったものは 0 トークンとして混ぜず「未接続」として列挙する。失敗時は理由を出して非 0 終了し、数値を推定で埋めない。
- **GUI に「コンテキスト内訳」タブを追加した**。ボタンを押したときだけ CLI を呼び、その出力をそのまま描画する（GUI 側で再集計しない）。MCP 接続待ちで数秒ブロックするためワーカースレッドで実行する。あわせて、統計の遅延読み込みが「末尾タブかどうか」で判定されていた箇所をタブ位置非依存に直した（タブ追加で別タブを開いたときに発火する退行を防ぐ）。
- **ポリシータブに `always` / `auto` / `never` / `limit` / `tau` / `field_weights` の凡例を、Skill Layer タブに「Extend 層の実効性は CLI 側に依存する」旨の注記を追加した**。

**検証**: FR-GUI-07 / FR-TS-10 / FR-TS-11 の各契約を RED → GREEN で確認（GUI 44 件、CLI 5 件、context_report 10 件を含む Tool Search 関連 131 件が PASS）。`hve/tests` 全体は 7,275 passed / 4 failed で、失敗 4 件はいずれも本変更が触れていないファイルに起因する既存不具合（`test_aad_web_fanout_meta_is_forwarded_to_step_runner` / `test_no_args_fallback_when_pyside6_missing` / 未生成の `azure-static-web-apps-app009.yml` / SDK lock の CRLF）。要求定義・要求テストマッピング・索引 CSV を再生成し、`FR-TS-11` が `active-or-described` として登録されていることを照合した。

<!-- validation-confirmed -->

### Changed — Step 実行セッションのツール定義トークンを 45.5% 削減した（FR-CLI-76）

GitHub Copilot CLI 1.0.79 / SDK 1.0.7 上で、Step 実行セッションのコンテキストがツール定義で圧迫されている実態を実測し、公開する MCP サーバをリポジトリ宣言分に限定した。計測は `session.send` を行わず、`session.tools.initializeAndValidate` と `session.metadata.contextInfo` / `getContextAttribution` / `mcp.list` だけで行っている（モデル推論なし）。

- **`tool_search` は削減に寄与していないことを実測で確定した**。有効 / 無効 / `defer_threshold=1` の 3 条件で `toolDefinitionsTokens` が 52,756 で完全に一致し、全 183 ツールの `defer_loading` が `null`、`tool_search_tool` もツール一覧に現れなかった。`toolDefinitionsTokens` は SDK 定義上 "excludes deferred tools" であるため、遅延化されたツールは 0 件である。`tool_search_ranking=hve` を有効にすると Skill 73 件がツールとして登録されるだけで deferral が働かず、ツール定義が 47,115 → 59,275 tokens（+12,160）に増えた。既定の `sdk` を維持する。
- **FR-CLI-76 を新設した**。`_create_session_with_auto_reasoning_fallback` は、呼び出し側が `mcp_servers` と `enable_config_discovery` のいずれも指定していない場合に、`.github/.mcp.json` の `mcpServers` を渡し `enable_config_discovery=False` を設定する。ワークスペース / ユーザースコープ / プラグイン由来の MCP 自動探索を止める。宣言が無い・壊れている・空の場合は従来動作（自動探索有効）へ縮退する。`_require_trusted_asdw_data_deploy_mcp_servers` / `_require_trusted_foundry_mcp_servers` / `SDKConfig.mcp_servers` / Work IQ 有効時の QA サブセッションなど、呼び出し側が明示している経路の挙動は変更していない。
- **明示指定した MCP サーバ設定に `tools` キーが無いとサーバが起動されない欠陥を発見し修正した**。`.github/.mcp.json` の `azure` は `tools` を持たず、FR-CLI-76 実装直後の実測で Azure MCP の 68 ツールが全 Step から消えていた。従来は自動探索が同名のプラグイン `azure` を起動していたため表面化していなかった。`.github/.mcp.json` と `hve/runner.py` の `_FOUNDRY_REQUIRED_AZURE_MCP_CONFIG` の双方へ `"tools": ["*"]` を追加し、静的検査テスト 2 件で固定した。
- **1 度も起動していなかった `context7` を `.github/.mcp.json` から削除した**。9 セッション分の計測と CLI ログで一度も出現せず、自動探索の対象は作業ディレクトリ直下の `.mcp.json` / `.vscode/mcp.json` であって `.github/.mcp.json` ではない。`hve/toolsearch/policy.json` の pin と検索語彙、`mcp-server-design` Skill と eval、users-guide 2 件の記述を同期した。
- **重複していた MCP サーバをユーザースコープ設定から除いた**（リポジトリ外の環境設定）。`azure-mcp`（プラグインの `azure` と同一コマンド）と `workiq-preview`（`workiq` と同一 URL・同一 oauthClientId）。プラグインの有効・無効は `settings.json` の `enabledPlugins` だけでは反映されず、`config.json` の `installedPlugins[].enabled` が実効値であることを実測で確認した。
- **Skill カタログの説明つき掲載が文字数予算で 33 件に打ち切られていた**。組み込み `skill` ツールの description に埋め込まれる `<available_skills>` は予算超過分を「Additional skills available (invoke by name):」の名前のみ列挙に降格させており、`work-artifacts-layout` と `test-strategy-template` が説明を失っていた。件数上限ではなく文字数予算であることを spike で確定し、最長 2 件（`code-query` / `markdown-query`）の frontmatter `description` を短縮して repo の 35 件すべてが説明つきで載る状態にした。配布キットは `sync-vendor` で再生成した。
- **削減効果（実測）**: ツール定義トークン 52,756 → 33,384（環境の重複解消）→ **28,763**（FR-CLI-76）。累計 **−23,993 tokens（−45.5%）**、セッション全体では 67,928 → 43,702 tokens。全 Step のメインセッションとサブセッションが毎回この量を積むため、Step 数の多いワークフロー（`asdw-web` は 25 Step）ほど効果が大きい。

**検証**: `hve/tests/test_runner_session_mcp_scope.py`（12 件）を RED → GREEN で確認。MCP / Skill 経路の既存テスト 290 件、tool search 系 376 件、配布キット同期 130 件、索引整合 326 件が PASS。広域回帰は 2,318 passed / 2 failed で、失敗 2 件（`test_aad_web_fanout_meta_is_forwarded_to_step_runner` / `test_no_args_fallback_when_pyside6_missing`）はクリーン HEAD の worktree でも同一に失敗する既存不具合であることを確認済み。要求定義・要求テストマッピング・3 種の索引 CSV を再生成し、`FR-CLI-76` が `active-or-described` として登録されていることを照合した。

<!-- validation-confirmed -->

### Fixed — ASDW-WEB Step 1.2 の検証スクリプトがマージコンフリクトマーカーを含んだまま `main` にコミットされていた

`src/infra/azure/verify-data-resources.sh` は、コミット `1000fe29`（"Fix merge conflicts in verify-data-resources.sh"）がコンフリクトを解決しないままマーカー行を残してコミットしたため、`bash -n` が exit 2 で失敗し、ASDW-WEB Step 1.2 / 1.3 の artifact validator が 18 件のエラーを返す状態だった。Step 1.3 の deploy gate は Azure 操作前に同じ validator を実行するため、この状態ではデータ層のデプロイへ進めない。

- **破損コミットが追加した 17 行だけを差し戻した**。直前の健全なリビジョン `889095c1`（blob `ea34ec3d`）へ戻し、内訳は 6 マーカー行、`public` mode の重複 `printf` 1 行、`DATA_VERIFY_RUN_ID` / `timeout` ガードの重複 9 行、敗北側の単一行 `aci_command` 1 行。追加行は 0 行で、他ファイルは変更していない。
- **検証器・契約テスト・設計書・sample-data は一切変更していない**。壊れた成果物に合わせて検証を緩めるのではなく、成果物側を最後の健全な状態へ戻す方針とした。
- **契約テストは修正前から 686 件すべて成功していた**。これらは fixture / `tmp_path` ベースで、リポジトリ内の実 `verify-data-resources.sh` を検査しない。実成果物を検査する CI ゲートが存在しないことが、構文破壊が `main` に残り続けた直接の原因である。

**検証**: `bash -n` は exit 2 → 0、ShellCheck は exit 1 → 0、artifact validator は 18 件 → 0 件。LF・BOM なしを維持（`.gitattributes` の `*.sh text eol=lf` により `core.autocrlf=true` 環境でも LF）。focused pytest 8 ファイルは修正前後とも 686 passed / 2 skipped で回帰なし。差分は `git diff --cached --numstat` で 0 追加 / 17 削除であることを確認。Azure CLI・Azure REST・対象スクリプトの実行は一切行っていない（`Live-RED-Status: NOT_RUN`）。

**既知の制約**: リポジトリ内の実 `verify-data-resources.sh` を artifact validator へ通す CI ゲートは追加していない（本修正のスコープ外）。差し戻しにより、破損コミットが持ち込んでいた `DATA_VERIFY_RUN_ID` / `timeout` ガードの診断用 `printf` メッセージは失われるが、契約上は必須ではなく重複ガードの解消を優先した。RED 証跡の `static-verification.log` は `.gitignore` の `*.log` 対象のためコミットされない（既存 25 件の `tdd-test-report.md` が tracked、`static-verification.log` は 0 件 tracked という従来の運用と同じ）。

<!-- validation-confirmed -->

### Fixed — GUI の「GitHub CLI でログイン」に必要な `gh` / PTY backend が通常セットアップで揃わなかった（FR-GUI-09）

Windows の `hve\setup-hve.cmd` と macOS / Linux の `./hve/setup-hve.sh` をオプションなしで実行しても、GUI の「GitHub CLI でログイン」が必要とする `gh` と OS 別 PTY backend（`pywinpty` / `ptyprocess`）が揃っているとは限らず、GUI 側の復旧案内も手動 `pip install` とリポジトリ相対パスに依存していた。

- **通常セットアップを fail-closed 化**: 通常 GUI 構成では `gh` を解決できない場合、または GUI 共通判定 `hve.gui.pty_backend.is_pty_available()` が利用不可を返す場合に非ゼロ終了する。`gh auth status` の未認証は正常な開始状態として許容し、セットアップ自身は `gh auth login` を実行しない。`-NoGui` / `--no-gui` / `-Minimal` / `--minimal` は明示的な opt-out として維持する。
- **`-CheckOnly` / `--check-only` を診断モードとして明文化**: `.venv` の作成も pip install も行わないまま、通常 GUI 構成で不足している `gh` / PTY backend を **警告** として報告する。通常実行の fail-closed 契約とは分離し、非ゼロ終了しない。
- **復旧案内を CWD 非依存にした**: `pty_backend.setup_command()` がパッケージ配置から setup スクリプトの実パスを解決するため、リポジトリ外の作業ディレクトリから GUI を起動しても案内をそのまま実行できる。setup スクリプトが同居しない導入形態では推測した絶対パスを出さず相対表記へ退避する。
- **GUI 起動時の依存不足案内を setup 主導線へ統一**: `.[gui]` 単独導入を完全構成の推奨復旧経路として提示せず、OS 別 setup と実在する起動入口（`hve.cmd gui` / `./hve.sh gui`）を案内する。手動 `pip install` は補助情報に降格した。
- **i18n**: `hve/gui/gh_login_dialog.py` を `translations.pro` の抽出対象に追加し、`GhLoginDialog` の 8 文字列を英訳して `.qm` を再生成した。`pyside6-lupdate` が `.pro` の直接受け取りを廃止したため、`hve/gui/i18n/README.md` の手順を実行可能な形へ更新した。
- **CI**: `test-hve-python.yml` に 3 OS matrix（windows / macos / ubuntu）の `gui-pty-tests` job を追加。`gui-pty` 導入 → `is_pty_available()` の fail-closed 確認 → `hve/tests/test_pty_backend.py` を skip 0 件で実行、の順に検証する。
- **ドキュメント**: `users-guide` の GUI 導線を実在ファイルへ是正した。存在しない `hve-gui.bat` / `hve-gui.sh` / `hve-gui.command` の参照を `hve.cmd` / `hve.sh` へ置換し、`troubleshooting.md` に「GUI の『GitHub CLI でログイン』で端末が開かない」症状の復旧手順と成功確認方法を追加した。

**検証**: `hve/tests/test_dev_task_environment_contract.py`（隔離 setup ハーネス、bash / pwsh 両系統）、`hve/tests/test_pty_backend.py`、`hve/tests/test_gui_imports.py`、`hve/gui/tests/test_gh_login_dialog.py`、`hve/gui/tests/test_i18n.py` を実行し 83 passed（唯一の失敗は後述の既知制約）。PowerShell パーサ 0 エラー、`bash -n` OK、workflow YAML parse OK、`pyside6-lrelease` で `.qm` 生成成功、`git diff --check` 指摘なし、`hve-dev/generate_tdd_inventory.py` を 2 回実行して生成日時以外のハッシュ一致を確認。

**既知の制約**: `test_copilot_sdk_lock_pins_an_exact_version` は本変更以前から Windows ホストで失敗する（`core.autocrlf=true` により `hve/copilot-sdk.lock` が CRLF で checkout されるため。リポジトリの blob は LF で、Linux CI では PASS）。本要件の対象外のため未修正。`hve/setup-hve.sh` line 171 の ShellCheck SC2164 も本変更以前からの指摘で、対象外として据え置いた。PowerShell 側の setup ハーネスは `pwsh` 7+ が無い環境では実行されない。

<!-- validation-confirmed -->

### Changed — AAS Step 8/9 を成果物依存と同じ昇順へ再採番（FR-WF-AAS-01）

**破壊的変更**: AAS ワークフロー末尾 2 Step の ID の意味を入れ替えた。従来は Step 9（ペルソナカタログ）の出力を Step 8（ペルソナ別共通画面カタログ）が消費しており、実行順が `Step.7 → Step.9 → Step.8` と番号に逆行していた。成果物依存は変えずに ID だけを入れ替え、実行順を `Step.7 → Step.8 → Step.9` へ揃えた。

- **Step.8** = ペルソナカタログ（`Arch-PersonaCatalog` / `depends_on=["7"]` / `docs/catalog/persona-catalog.md`）
- **Step.9** = ペルソナ別共通画面カタログ（`Arch-UI-PersonaScreenList` / `depends_on=["8"]` / `docs/catalog/persona-screen-catalog.md`）

**移行時の注意**: Step ID は SDK セッション ID（`run_id × step_id`）と Cloud の Step Issue タイトルの構成要素であり、同じ ID の意味が変わる。透過的な旧 ID 変換は実装していないため、実行中の AAS run は本変更の取り込み前に完了させること。完了できない run は新しいコードで再開せず、新しい run-id（CLI / GUI）または新しい Issue（Cloud）で再起動する。旧番号の Step Issue が開いている状態で新しい workflow を有効化しないこと。

**変更内容**:

- **要件**: `hve-dev/requirement-definition.md` §13.1 に Step 8/9 行と FR-WF-AAS-01 を追加。`hve-dev/requirement-test-mapping.md` に対応表を追加。
- **正本**: `hve/workflow_registry.py` の AAS StepDef を入れ替え。`hve/orchestrator.py` の producer コメントを同期。
- **Prompt / Template / I-O 契約**: `templates/aas/step-8.md` と `step-9.md` を入れ替え、`Arch-PersonaCatalog--aas--8.yaml` / `Arch-UI-PersonaScreenList--aas--9.yaml` へリネーム。AAD-WEB 側 consumer（`Arch-UI-List` / `Arch-UI-Detail` の prompt・io-contract・テンプレート）の producer 参照を Step.9 へ更新。
- **Cloud**: `auto-app-selection-reusable.yml` の skip 伝播を「Step.8 スキップ → Step.9 も強制スキップ」へ反転し、Step Issue 生成・紐付け・状態遷移（7→8→9→done）を更新。Step.9 の前提入力を registry 宣言（persona-catalog.md / app-catalog.md）に合わせた。
- **Issue Form**: `app-architecture-design.yml` のステップ表・依存チェーン・チェックボックスを新採番へ更新。
- **Bash / PowerShell**: `workflow-registry.sh` を同期。`workflow-registry.ps1` の AAS を旧 2 Step 定義から現行 11 Step へ同期し、Pester の AAS 期待値を更新。
- **ドキュメント**: `users-guide/02-app-architecture-design.md` を 11 ステップ構成へ更新し、Step 8/9 の入出力と手動実行手順を追加。AAS の SVG 3 点に Step 8/9 を追加。
- **テスト**: `hve/tests/test_aas_persona_step_numbering_contract.py` を新設し、registry・DAG wave・GUI rank・I-O 契約・Template・Prompt・Bash / PowerShell registry・Cloud workflow・Issue Form・ユーザーガイドを 1 ファイルで突き合わせる。`test_aas_template_parity.py` の依存パターンに Step 8/9 を追加。

**検証**: 新規契約テストは実装前に 30 failed（旧採番のみが理由）で RED を確認し、実装後に全 GREEN。`validate-io-contract.py` は Schema / Integrity / Registry mismatch すべて 0。Cloud / Issue Form の YAML parse、Bash 構文チェック、SVG の XML parse、PowerShell registry の直接実行検証（11 Step、7→8→9）を実施。各サブタスクで独立した敵対的レビューを行い、指摘を反映済み。

**既知の制約**: PowerShell の Pester はローカル環境に 3.4.0 のみ導入されており、テストが要求する Pester 5 構文を実行できないため、AAS の assertion はローカルでは未実行（構文解析と registry の直接呼び出しで代替検証）。Pester 5 が利用可能な環境（CI 等）で `workflow-registry.Tests.ps1` の AAS assertion を必ず実行して確認すること。`workflow-registry.Tests.ps1` の ADFD 関連 assertion は本変更以前から実装と乖離しており、本変更では対象外として据え置いた。

<!-- validation-confirmed -->

### Added — GUI 質問票で「その他」を自由記述として回答・保存できるようにした（FR-GUI-08）

選択肢付きの QA 質問へ「その他」を 1 件表示し、選択時に自由記述を入力できるようにした。既に「その他」を含む質問票では選択肢を重複させず、通常選択肢・選択肢なし自由記述・キャンセル・既存 IPC 形式は維持する。

- 自由記述は既存の `N:: その他: <text>` 形式で GUI から CLI へ渡し、マージ済み質問票の「ユーザー回答」へ保存する。
- 構造化質問票の `D. その他`、ラベル自体が「その他」の既定値、空欄時の既定値採用、および「その他」で始まる通常選択肢を回帰テストで保護した。

### Changed — QA 質問票が「なぜ不明点なのか」を説明せず、既定値候補の理由が一語で終わっていた（FR-QA-01 / FR-QA-02）

QA 質問票の各質問は `分類項目` / `重要度` / `質問文` / `選択肢` / `既定値候補` / `既定値候補の理由` / `未回答のまま進めた場合の影響` の 7 項目しか持たず、**「その論点がなぜ不明点として挙がったのか」「どの評価軸で判断が分かれるのか」を出力させるフィールドが存在しなかった**。結果として `既定値候補の理由` が「実績あり」「チーム習熟度を優先」のような結論のみの一語に収束し、回答者は各質問の妥当性を自分で調べ直さなければ判断できなかった。

- **質問テンプレートへ「背景と根拠」「判断の観点」の 2 項目を追加した**（[hve/prompts.py](hve/prompts.py) `PRE_EXECUTION_QA_PROMPT_V2` / `QA_PROMPT_V2`）。「背景と根拠」は確認した対象（出典）・確定した事項と確定していない事項・その未確定が質問に値する理由の 3 点を、「判断の観点」は回答で結論が変わる評価軸 2 つ以上と各選択肢の有利不利を求める。確認していない場合は「未確認」と書かせ、出典の推測を禁止した。
- **「既定値候補の理由」に 3 要素（根拠となる事実 / 優先した評価軸 / 他の選択肢を採らなかった理由）を必須化した**。従来は結論だけを書いても形式上は満たせてしまい、これが説明の浅さの直接原因だった。文面は `QUESTIONNAIRE_DEPTH_RULES_TEXT` を単一定義とし、事前 QA と事後 QA の両プロンプトから連結している（同一文面の二重管理を避けるため）。
- **`QAMerger` を新項目に対応させた**（[hve/qa_merger.py](hve/qa_merger.py)）。構造化質問票（`[Qxx]` 形式）とマージ済みテーブルの双方で解析し、拡張テーブルへ列として出力する。**GUI は `render_merged` の出力を IPC ファイル経由で再パースしてダイアログを組み立てるため、テーブル列として持たないと GUI に一切届かない**。この往復でのデータ保持を回帰テストで固定した。新項目を持たない既存の質問票は空値として扱う。
- **CLI は表の列を増やさず、表の直後に詳細ブロックを出力するようにした**（[hve/console.py](hve/console.py)）。拡張表はすでに 8 列で `_shrink_to_available` による幅圧縮が働く状態にあり、長文 2 列を足すと重要度や選択肢まで数文字に潰れて読めなくなるため。
- **GUI の QA 回答ダイアログへ「背景と根拠」「判断の観点」の 2 列を追加した**（[hve/gui/qa_answer_dialog.py](hve/gui/qa_answer_dialog.py)）。回答を選ぶ画面が唯一の判断材料提示面であるため、ここに無いと目的を達成できない。
- **Skill 側テンプレートを同一項目定義へ揃えた**（`.github/skills/task-questionnaire/` の SKILL.md と `references/` 配下 2 ファイル）。Cloud Agent 経路の質問票は `hve/prompts.py` ではなく Skill テンプレートを見るため、揃えないと「CLI/GUI は深いが Cloud は浅い」という経路依存の品質差が残る。プロンプトと Skill のフィールド名一致を契約テストで固定した。

**検証**: RED は 18 件（プロンプト 6 / `QAMerger` 9 / CLI 表示 2 / Skill 整合 1）＋ GUI 2 件が意図通り失敗することを確認。実装後は関連 8 ファイル（`test_prompts` / `test_qa_merger` / `test_questionnaire_ui` / `test_runner_pre_qa` / `test_main` / `test_console` / GUI 2 ファイル）で 688 passed / 1 skipped。棚卸し索引（[hve-dev/hve-feature-inventory.csv](hve-dev/hve-feature-inventory.csv) 他）を再生成し、FR-QA-01 / FR-QA-02 が `source=hve-dev/requirement-definition.md` / `active-or-described` で登録されること、新規テストクラス 4 種が索引に載ることを照合した。拡張テーブルは 11 列（通常）/ 13 列（Work IQ 併用）の双方について、ヘッダーとセパレータの列数一致および render → parse の往復で値が復元されることを実データで実測した。

**既知の制約**: 各フィールドの値を 1 行に限定しているのは、`QAMerger` の行単位フィールド解析が継続行を取り込まないためで、複数行で出力された場合は 2 行目以降が無視される。プロンプト側の指示で担保しており、解析側での強制は行っていない。LLM が実際に十分な深さを出力するかはプロンプト遵守に依存し、追加した契約テストはプロンプトの指示内容を固定するもので生成結果の品質を検証するものではない。CLI の詳細ブロックはセル内折り返しを行わず、長文は端末のソフトラップに任せている（表の幅制約は適用されない）。既存の `qa/` 配下ファイルは新項目が空欄のまま残る（再生成もマイグレーションも行わない）。[hve/workiq.py](hve/workiq.py) の Work IQ 問い合わせメタには新項目を渡していない。

### Fixed — setup が Copilot ランタイムの版不整合を検出できず、`session.event` 解析の AssertionError を素通ししていた（FR-MODEL-07）

macOS 環境で `hve` CLI 起動時に `CopilotClient._connect_via_stdio.<locals>.handle_notification` 内の `session_event_from_dict` → `from_uuid(obj.get("id"))` → `assert isinstance(x, str)` が AssertionError となる報告を調査した。原因は hve 側のバグではなく、**`github-copilot-sdk` の生成イベントパーサと、実際に spawn される Copilot CLI ランタイムのスキーマドリフト**である。パーサは未知のイベント "種別" にしか前方互換を持たず（`SessionEventType._missing_` → `UNKNOWN` + `RawSessionEventData`）、エンベロープ（`id` / `timestamp` / `type`）は assert で固めてあるため、pin と異なるランタイムを掴むと当該イベントが黙って捨てられる（終端イベントを取り逃すと `send_and_wait` がタイムアウトまで返らない）。トレースバックの行番号を実 wheel と照合し、報告環境の SDK が公開翌日の 1.0.9 であることを特定した。

- **`github-copilot-sdk` の導入版を [hve/copilot-sdk.lock](hve/copilot-sdk.lock) で固定した**。従来は `setup-hve.{sh,ps1}` が毎回 `pip install --upgrade` していたため「セットアップした日」でマシンごとに版が変わり、公開直後のリリースに不整合があると特定の人だけ壊れて再現・切り分けができなかった。既定は lock からの導入とし、最新化は `--upgrade-sdk` / `-UpgradeSdk` 指定時にだけ行って lock の pin 行と Copilot CLI ランタイム記録行を書き換える。更新が意図的な 1 回のコミットになるため、チーム全体が同じ版で動く。
- **`setup-hve.sh` / `setup-hve.ps1` に「Copilot ランタイム整合性」ステップを追加した**。SDK 版と pin 版（`copilot/_cli_version.py` の `CLI_VERSION`）を表示し、`python -m copilot download-runtime` で pin 版ランタイムを先読みしたうえで、キャッシュ済みバイナリの実バージョンと pin を突合して不一致を警告する。
- **pin を無効化する環境変数（`COPILOT_CLI_PATH` / `COPILOT_CLI_EXTRACT_DIR` / `COPILOT_SKIP_CLI_DOWNLOAD`）を検出して警告するようにした**。前者 2 つは SDK のバージョン固定キャッシュを迂回するため、設定されている限り版ドリフトが不可避になる。
- **外部 `copilot` CLI の実バージョンを表示し、npm 管理下にある場合のみ `@github/copilot@latest` へ更新するようにした**。この CLI は GUI チャットパネル専用で SDK の pin とは独立に自己更新するため、`COPILOT_CLI_PATH` へ流用しない旨をスクリプト内コメントと出力の両方に明記した。VS Code 同梱 CLI など npm 管理外のものは更新対象から除外し、競合インストールを避けている。
- **バージョン突合には `--no-auto-update` を必須とした**。`copilot --version` 単体はオンライン更新チェックを走らせ「最新利用可能版」を返すため pin との比較に使えない（実測: `cli/1.0.69/copilot.exe --version` → `1.0.78`、`--no-auto-update --version` → `1.0.69`、バイナリ内文字列は `1.0.69` が 8 件・`1.0.78` は 0 件）。この罠は調査自体を誤診させるため、契約テストで固定した。
- **`pyproject.toml` の下限指定が導入版の情報源ではないことをコメントで明記した**。lock を唯一の情報源とし、二重管理を避けている。

**検証**: `bash -n hve/setup-hve.sh` と PowerShell パーサでの構文検証。SDK 1.0.9rc3 へドリフトさせた `.venv` に対し `pip install --no-deps -r hve/copilot-sdk.lock` を実行し、1.0.9rc3 をアンインストールして 1.0.8 へ戻ることを実測。lock 更新ロジックを一時コピーへ適用し、pin 行と CLI ランタイム記録行の双方が書き換わり LF / BOM なしが維持されることを実測。追加ロジックを実バイナリへ適用したプローブで、SDK 1.0.8 / pin 1.0.73 / 実ランタイム 1.0.73 = 一致、PATH 上の VS Code 同梱 CLI 1.0.78 = 乖離を正しく検出。`hve/tests/test_dev_task_environment_contract.py` に契約テスト 4 件を追加し、トレーサビリティ・索引・scope の関連テストと併せて 242 passed / 2 skipped。追加テストは変更前の HEAD では検出マーカーが 0 件で失敗することを確認済み。棚卸し索引（[hve-dev/hve-feature-inventory.csv](hve-dev/hve-feature-inventory.csv) 他）を再生成し、FR-MODEL-07 の source / status / テストパスの登録を照合した。

**既知の制約**: 本変更は「pin と実ランタイムの不整合」および「マシン間の版ドリフト」を防ぐもので、**SDK の特定リリース自体にパーサ不整合がある場合の解析失敗そのものは防げない**。実行時のフェイルソフト（`AssertionError` をイベント欠落警告へ変換する asyncio 例外ハンドラ）は未実装で、別要件として扱う。`--check-only` / `-CheckOnly` は `.venv` 構築前に終了するため、これらの検証ステップは実行されない。`pip install -e .[extras]` が先に走るため、新規環境では一度最新版を取得してから lock 版へ入れ替わる（最終状態は lock 版で正しいが wheel の二重取得が発生する）。lock の初期値は実測で動作を確認済みの 1.0.8（pin CLI 1.0.73）とし、報告のあった 1.0.9 は採用していない。

### Fixed — fan-out 展開の基準ルートが HVE の設置ディレクトリを指し、対象リポジトリのカタログを読めていなかった（FR-DAG-04）

macOS で HVE を対象リポジトリとは別の場所へ設置して ARD を実行すると、Step 3.1 が `docs/catalog/use-case-skeleton.md` を正しく生成した直後に Step 3.2 が `⏭️ deferred fan-out が依存解決後も 0 件のため skip` で落ちる事象を調査した。原因は [hve/orchestrator.py](hve/orchestrator.py) が fan-out 展開の `repo_root` に `Path(__file__).resolve().parent.parent`（= HVE パッケージの設置ディレクトリ）を渡していたことで、カタログが対象リポジトリに実在しても展開キーが 0 件になり `fanout-empty` で**無警告 skip** されていた。ARD 固有ではなく全ワークフローの全 fan-out Step に波及する。

- **事前展開・deferred 再展開・Fleet wave prompt の 3 箇所を `Path.cwd()` へ是正した**。`DAGExecutor` 自身の既定値は `repo_root=None → Path.cwd()` で元から正しく、orchestrator が明示引数で誤った値に上書きしていた。リポジトリ内の他の作業リポジトリ解決（[hve/runner.py](hve/runner.py) ほか）はすべて `Path.cwd()` 系で統一されている。
- **本リポジトリは HVE 自身を dogfooding するため `Path(__file__).resolve().parent.parent == Path.cwd()` が成立し、素の実行では症状が出ない**。既存テストも `repo_root` を直接注入しており orchestrator の実配線を通っていなかったため、`monkeypatch.chdir` で両者を必ず分離する回帰テストを追加した。
- **Self-Improve の `repo_root` は HVE 自身の prompts / skills を改善対象とするため変更していない**。用途が異なるため一括置換していない。
- **FR-DAG-04 へ「展開の基準ルートは実行プロセスの作業ディレクトリ」を明文化した**。併せて同要件が挙げていた実在しない parser 名 `batch_job_catalog` を `dataflow_catalog` へ、`use_case_skeleton` の対応 Step を現行の ARD Step 3.2 へ是正した。

**検証**: 追加した [hve/tests/test_orchestrator_fanout_repo_root.py](hve/tests/test_orchestrator_fanout_repo_root.py) が変更前は 4 件失敗（作業ディレクトリに UC 2 件しか置いていないのに本リポジトリ側の 26 件へ展開される事象を再現）、変更後は 4 件成功。既存の fan-out / ARD 回帰 79 件、GUI 要件 106 件、ARD 系 213 件が pass。

**既知の制約**: Fleet wave prompt 経路（fleet mode 有効時のみ）は実行証跡が無く、AST による契約テストでのみ固定している。Self-Improve が `collect_workflow_output_paths`（内部で fan-out 展開）と改善対象ルートを同一変数で兼務している点は未分離のまま残している。

### Fixed — `aar` ワークフローが GUI の要件テーブルに未登録で、起動前チェックが無警告で通過していた（FR-GUI-01）

GUI のワークフロー一覧は [hve/gui/page_workflow_select.py](hve/gui/page_workflow_select.py) が `list_workflows()` から動的に構築するため `aar` も選択できるが、`REQUIREMENT_TABLE` / `WORKFLOW_PRIORITY` / `WORKFLOW_TO_SECTION` のいずれにも登録が無く、レジストリ 12 ワークフロー中で唯一の欠落だった。`pick_target_step` は `WORKFLOW_PRIORITY` 順にしか走査しないため、`aar` 単独選択時はファイル要件が 1 件も評価されないまま precheck が通過する。

- **`aar` Step 1 の要件を 3 テーブルへ登録した**（[hve/gui/workflow_step_requirements.py](hve/gui/workflow_step_requirements.py)）。必須ファイルは同構成の AAD-WEB / ASDW-WEB と同じ `app_catalog` を流用し、新しいファイル種別は追加していない。`aar` Step 1〜6 は `required_params` を持たないため必須情報キーは空とした。
- **FR-GUI-01 へ「`REQUIREMENT_TABLE` / `WORKFLOW_PRIORITY` はレジストリの全ワークフローを網羅する」義務を追加した**。`WORKFLOW_TO_SECTION` は既定値 `OPTIONS_TOP` を持ち precheck を壊さないため規範には含めていないが、既存の `WORKFLOW_PRIORITY ⊆ WORKFLOW_TO_SECTION` 不変条件を満たすため登録自体は行った。

**検証**: 追加した `TestRequirementTableCoversRegistry` が変更前は 2 件失敗（`aar` 欠落）、変更後は同ファイル 22 passed / 12 subtests。GUI 要件・バナー・autopilot の関連 106 passed / 1 skipped。

### Added — ARD がユーザー提供資料を一次情報として最優先で参照する契約（FR-WF-ARD-02）

ユーザーが PDF などを Markdown 化して ARD の入力に指定した場合、その資料は ARD の**どの Step の `required_input_paths` にも宣言されず**、`{attached_docs}` / `{target_business}` のパラメータ注入だけが到達経路である。Step 2（Targeted）のプロンプトには「一次情報として最優先で参照する」という規定があったが、Step 1（Untargeted）側には同等の規定が無く、`情報源の優先順位` は公開 IR 資料を筆頭に列挙していたため、ユーザー提供資料が既定入力に埋没しうる非対称があった。

- **Untargeted プロンプトの入力節・参照資料節・情報源の優先順位節に最優先参照規定を追加した**（[.github/prompts/Arch-ARD-BusinessAnalysis-Untargeted.prompt.md](.github/prompts/Arch-ARD-BusinessAnalysis-Untargeted.prompt.md)）。公開情報は「添付資料に記載が無い事項」を補う位置付けに整理し、従来の信頼性評価順は維持した。
- **Step 1 の Body テンプレートにも同じ規定を明記した**（[.github/scripts/templates/ard/step-1.md](.github/scripts/templates/ard/step-1.md)）。Agent が実際に読むのはテンプレートの `## 入力` 節であるため、プロンプト側だけでは到達しない。
- **ファイル名を推測せず与えられたパスをそのまま読むことを明示した**。ユーザー指定ファイル名は固定ではなく、`docs/company-business-recommendation.md` のような既定の出力ファイル名と混同させないため。

**検証**: 追加した [hve/tests/test_ard_attached_docs_priority.py](hve/tests/test_ard_attached_docs_priority.py) が変更前は 2 件失敗、変更後は 5 件成功（Targeted 側の既存規定と `step-2.md` のプレースホルダ保持も回帰として固定）。

**既知の制約**: 本変更は Step 1 / Step 2 のプロンプトとテンプレートに規定を置くもので、Step 2.1 / 3.1 / 3.2 / 3.3 はユーザー提供資料を入力として宣言していない（従来どおり Step 2 が生成した `docs/business-requirement.md` 経由で間接的に伝播する）。生成物の出力ファイル名を可変にする対応は含まない。

## [0.4.0] - 2026-08-07

### Fixed — Cloud Session の初回送信が無言でドロップされ得るレース条件を解消した

`client.create_session(cloud=...)` は Mission Control がタスクを予約した時点で解決するが、実際にリモートの `copilot-agent` ワーカーが接続して `session.start` を発火するまでには数秒のタイムラグがある。GitHub Copilot SDK のドキュメント（Cloud Sessions ガイド）は、このタイムラグ中に送信するとサーバ側がプロンプトを無言で破棄し得ると明記しており、実際にインストール済み SDK（`github-copilot-sdk` 1.0.8）のソースを確認したところ、`CopilotSession.send_and_wait()` にはこのレースに対する保護が一切無いことを確認した。hve は Cloud Session 作成直後に `send_and_wait()` を呼ぶ構成のため、この既知のレースにそのまま曝露していた。

- **`wait_for_cloud_session_ready()` を新設した**（[hve/cloud_session.py](hve/cloud_session.py)）。Cloud Session 作成成功後、最初の送信前に `session.start`（`producer == "copilot-agent"`）を待つ。60 秒でタイムアウトした場合は `TimeoutError` を送出し、既存の Cloud Session 失敗時フォールバック（ローカルセッションへの切り替え）にそのまま委ねる。
- **[hve/orchestrator.py](hve/orchestrator.py) と [hve/runner.py](hve/runner.py) の `_create_session_with_auto_reasoning_fallback` に統合した**。並行利用数制限（`CloudSessionLimiter`）のスロット解放が正しく行われるよう、readiness 待機はスロット解放処理より前に配置した。
- **実装中に発見した第三の該当箇所として、[hve/self_improve.py](hve/self_improve.py) の `discover_task_goal_with_llm` にも同じ脆弱パターンがあったため、同様に修正した**（当初計画では未対象だったが、根本原因が同一のため対応した）。

**検証**: RED は `hve/tests/test_cloud_session.py` / `hve/tests/test_cloud_session_runtime.py` で 5 件、`hve/tests/test_self_improve.py` で 1 件が意図通り失敗。実装後は該当 3 ファイル合計で 210 passed（既存分含む）。関連する `hve/tests/test_orchestrator.py`（181 passed。無関係な pre-existing 失敗 1 件を除く）・`hve/tests/test_runner.py`（205 passed）でも回帰なしを確認した。

**既知の制約**: readiness 待機がタイムアウトした場合、見捨てられた Cloud Session を明示的に `disconnect()` しないため、リモート側タスクが孤立する可能性がある（ローカル側の並行数制限スロットは既存の解放処理で正しく戻る）。この待機（最大60秒）が呼び出し元の `send_and_wait(timeout=...)` を含むステップ全体のタイムアウト予算に与える影響は個別に検証していない。`hve/self_improve.py` の Cloud Session フォールバック経路は本来 console 警告を持たない設計（pre-existing）で、今回追加した readiness timeout もこの経路に該当し無警告でフォールバックし得る。実際の `CopilotSession`（実 SDK）に対する統合テストは行っておらず、全テストは fake ベースの単体テストに留まる。

### Fixed — モデル一覧のトークン単価が常に取得できず、SDK 0.3.0 時代の互換パッチが陳腐化していた

`hve/models_api.py` は SDK 0.3.0 時代の `ModelBilling.multiplier` 必須化バグを避けるモンキーパッチと、`billing.token_prices` / `capabilities.supports.reasoning_effort` を独自の低レベル RPC 直叩きで補う回避コードを持っていた。インストール済み SDK（1.0.8）のソースを直接確認したところ、(1) `ModelBilling.from_dict` は `multiplier` 欠落を今は許容しており当該パッチは不要、(2) 低レベル RPC 側のキー名が snake_case（`token_prices` / `batch_size` / `reasoning_effort` 等）だったのに対し実際の wire フォーマットは camelCase（`tokenPrices` / `batchSize` / `reasoningEffort` 等）のため、このキー不一致により現行 SDK（1.0.8）では両回避コードとも空振りしていた（過去バージョンでの動作有無までは未検証）。

- **`_apply_sdk_billing_patch()` を削除した**。現行 SDK の `ModelBilling.from_dict` が `multiplier` 欠落を素通しすることを回帰テストで固定した。
- **価格抽出を公開 API 経由（`ModelInfo.billing.token_prices.*`）に置き換えた**。既存の USD/1M 換算式は変更していない。非推奨化された `cache_price` の代わりに SDK が案内する `cache_read_price` を参照するようにした。
- **機能していなかった `capabilities.supports.reasoning_effort` の縮退救済ロジックを削除した**。この項目は wire・SDK 双方で単なる bool であり、削除前から一度も「候補一覧」を返せていなかったため、既存の正規経路（トップレベル `supported_reasoning_efforts` および `capabilities.supports.reasoning_effort` の bool 値）には影響しない。

**検証**: RED は `hve/tests/test_models_api.py` で 2 件が意図通り失敗。実装後は同ファイルで 14 passed、関連する `hve/tests/test_cli_login.py` / `hve/tests/test_get_model_choices.py` で 26 passed を確認した。

### Changed — 一時作業ファイルをリポジトリルート直下に作れないよう強制した

リポジトリルート直下に一時デバッグスクリプト・pytest 出力・`MagicMock/` ディレクトリが堆積していた。`.gitignore` 済みのものは気付かれないまま作業ツリーを汚し、うち 1 件（`_tmp_mdq_probe3.py`）は Git 管理下にコミットされていた。ルールは Skill 側に散在しておらず、CI での検出手段も無かった。

- **ルート直下の不要ファイルを削除した**。`_tmp_mdq_probe3.py`（コミット済みの一時プローブスクリプト）、`MagicMock/`（`unittest.mock` の `MagicMock` をパスとして扱った副作用で生成されたディレクトリ）、`artifacts/requested_gui_pytest.out.txt` / `.err.txt`。ビルド／publish 成果物（`.tmp/`、`artifacts/svc13.zip`、`artifacts/svc16.zip`、`artifacts/svc13-publish/`、`artifacts/svc16-publish/`）は再生成コストがあるため残した。
- **`.github/copilot-instructions.md` §0 に絶対ルールを追加した**。一時作業ファイルは `work/run/<run-id>/.../artifacts/` 配下にのみ作成し、ルート直下へは置かない。`.gitignore` 済みかどうかは判断基準にしない。
- **CI で強制するようにした**。`protect-readonly-paths.yml` に `check-root-temp-files` ジョブを追加し、PR で追加（`status=added`）されたパスのトップレベル要素を許可リスト `ROOT_FILE_ALLOWLIST` / `ROOT_DIR_ALLOWLIST` と突合して、載っていなければ fail させる。正当なルート直下ファイルを追加する場合は同じ PR で許可リストも更新する運用にした。
- **Skill 側にも配置先を明記した**。`work-artifacts-layout` に用途別の正しい配置先の対応表、`agent-common-preamble` に全 Custom Agent が継承する 1 行ルールを追加した。

**検証**: 追加ジョブのシェルロジックを 5 ケース（許可済みパスのみ / 追加なし / ルート直下の一時スクリプト / ルート直下の一時ディレクトリ / 許可と違反の混在）で実行し、期待どおりの終了コードと違反パス表示を確認した。`validate-skills.py` は 35 件すべて PASS。

## [0.3.0] - 2026-08-07

### Changed — 全配布パッケージのマイナーバージョンを更新

- HVE: `0.2.0` → `0.3.0`
- Code Query: engine / Skill / GUI `0.1.0` → `0.2.0`、配布キット `1.1.2` → `1.2.0`
- Markdown Query: engine / Skill `0.5.0` → `0.6.0`、GUI `0.1.0` → `0.2.0`、配布キット `1.1.2` → `1.2.0`
- Tool Search: 配布キット `1.1.3` → `1.2.0`

### Added — `code-query` の索引統計を言語別に分解し、GUI で技術ごとに確認できるようにした（FR-CQ-15 新規 / FR-GUI-04 改訂）

統計はパーサ別の内訳しか持たず、**1 つのパーサ名を複数の言語が共有する**ため、どの技術で解析フィデリティが落ちているのかを判別できなかった。実測では profile=app の `regex=150` が C# 74 件と JavaScript 76 件の合算で、GUI 上では両者を区別できない状態だった。

- **`cq.store.index_stats` に `by_lang` を追加した**。言語ごとに `files` / `symbols` / `chunks` / `by_parser` を返す。言語の値は索引の `files.lang` をそのまま用い、統計側で拡張子から再分類しない。
- **集計は単一実装のまま拡張した**（FR-MAINT-07）。CLI の `cq stats` と GUI の両方に同時に反映され、第 2 実装を作らない。
- **GUI の「インデックス管理」タブへ言語別統計表を追加した**。HVE 組込画面と独立 GUI は同じセクション実装を共有するため、両方に反映される。統計取得の呼び出し回数は従来と同じ 1 回のまま。
- **索引未生成時の振る舞いは変えていない**。表は空のままで、統計表示を理由に `.cq/` を新規作成しない。

これにより、従来は見えなかった降格が言語単位で特定できる（2026-08-06 の本リポジトリ実測: profile=hve で PowerShell 26 件中 20 件、Shell 40 件中 33 件が `lite` 降格）。**降格の原因は本変更の調査範囲外であり、未特定**。

既知の制約: 本リポジトリに `.sql` ファイルが存在しないため SQL は言語行として現れない。SQL 方言と DB 製品の内訳は索引が値を保持していないため対象外とした。

**検証**: RED は `KeyError: 'by_lang'` と `AttributeError: '_language_stats_table'` で **8 failed**。実装後は cq / GUI の focused suite で **115 passed**。配布キット同期とインベントリ一致の契約は同期直後に **68 passed**。集計時間は profile=hve で 82〜98 ms、profile=app で 22〜31 ms で、言語別合計と全体合計の一致を両 profile で確認した。

### Added — `code-query` の利用ログを `.cq/usage.jsonl` へ記録するようにした（FR-CQ-14）

`markdown-query` は `.mdq/usage.jsonl` に利用ログを持っていたが、`code-query` には利用ログの仕組みが一切無く、`.cq/` にあるのは索引 DB だけだった。どのクエリがどれだけ使われ、何件ヒットしたかを後から追跡できなかった。

- **`cq/usage_log.py` を追加した**。`mdq/usage_log.py` と同じレコード形式（`ts` / `command` / `args` / `elapsed_ms` / `result` / `exit_code` / `context`）で、`<repo-root>/.cq/usage.jsonl` へ 1 コマンド = 1 行を追記する。保存先は `--repo-root` で解決した値で、`.mdq/usage.jsonl` とは別ファイルにする。
- **`cq/cli.py` から記録するようにした**。`_dispatch` が結果集計を書き込む辞書を受け取り、`main` が 1 箇所で追記する構成にしたため、サブコマンドごとに追記呼び出しを複製していない。`index` / `stats` / `search` / `def` / `get` / `refs` / `trace` / `map` を記録し、例外経路も終了コード付きで記録する。長時間常駐する `watch` は記録しない。
- **記録は best-effort**。書き込みに失敗しても CLI の終了コードと標準出力は変わらない。値が取得できない項目はキーごと省略し、`null` で埋めない。
- `.cq/` は既に `.gitignore` 済みのため、追跡除外の変更は不要。

**検証**: RED は `cq.usage_log` 不在による collection error 1 件。実装後 **9 passed**。cq 既存経路（`test_search` / `test_index_stats` / `test_repomap` / `test_traces`）を含む focused suite は **962 passed**。配布キット同期後の byte 一致検査は **82 passed**。

### Changed — Tool Search の実行時ログをリポジトリ配下 `.toolsearch/` へ移し、VS Code `tool_search` のログ出力先を確定した（FR-TS-07 / FR-TS-09 改訂）

Tool Search のイベントログと利用履歴だけがユーザースコープ（`~/.hve/toolsearch/`）にあり、`markdown-query`（`.mdq/`）・`code-query`（`.cq/`）とログの置き場が揃っていなかった。複数リポジトリで HVE を動かすと 1 ファイルに記録が混在し、リポジトリ単位で切り分けられなかった。

- **既定の保存先を `<repo-root>/.toolsearch/` へ移した**。`default_events_path()` / `default_usage_path()` は任意引数 `repo_root` を取り、省略時はカレントワーキングディレクトリを基準にする。`HVE_TOOLSEARCH_EVENTS` / `HVE_TOOLSEARCH_USAGE` による差し替えは従来どおりで、環境変数は `repo_root` の明示より優先する。
- **GUI が保持する `repo_root` を渡すようにした**。設定画面は cwd がリポジトリルートと一致する保証がなく、従来は誤ったパスを表示しうる状態だった。
- `.gitignore` に `.toolsearch/` を追加した。CLI の help、ユーザーガイド、他リポジトリ配布キットの記述も新既定へ揃えた。
- **既存ログの自動移行は行わない**。旧パスは読まない。

**VS Code `tool_search` のログ出力先（調査結果）**: VS Code 同梱 `GitHub.copilot-chat` 0.60.0 の `package.json` と公式ドキュメントを実測確認した結果、経路は 2 つあり、出力先を選べるのは片方だけだった。

- Chat デバッグファイルログ（`github.copilot.chat.agentDebugLog.fileLogging.enabled`、既定 `false`）は `<拡張ストレージ>/debug-logs/<sessionId>/main.jsonl` へ書き、**出力先を変更する設定は存在しない**（拡張ストレージ URI から導出される）。
- OpenTelemetry ファイルエクスポーター（`github.copilot.chat.otel.enabled` + `github.copilot.chat.otel.outfile`）は **任意のパスへ JSON-lines を出力できる**。3 設定はいずれも `scope: application` でユーザー設定にしか書けず、反映にウィンドウ再読み込みを要する。

後者を `.toolsearch/vscode-otel.jsonl` へ向ける手順を [users-guide/tool-search-dashboard.md](users-guide/tool-search-dashboard.md) §2.4 に追加した。全ワークスペース共通の設定であるため他ワークスペースの記録も混在すること、`otel.captureContent` が既定 `false` で会話内容を含まないことを併記した。**`tool_search` に対して `execute_tool` スパンが発火するかは静的確認だけでは断定できないため未確定事項として明記し、導入時の一度きりの実測を求める形にした**（`tool_search` は拡張の `contributes.languageModelTools` に登録されない内部ツールのため）。ダッシュボードはこのファイルを読まず、保存先を揃えるところまでを対象とする。

**検証**: RED 5 件（`default_*_path` の `repo_root` 引数不在と旧パス）→ 実装後 **13 passed**。Tool Search / GUI 設定画面 / ダッシュボードを含む focused suite は **962 passed**、周辺の配布同期・契約テストは **153 passed**（別途 1 件失敗があるが `tools/skills/markdown_query/launch-gui.sh` の CRLF に起因する既存不具合で、本変更と無関係であることを git 履歴で確認済み）。

### Fixed — ダークテーマで GUI が判読不能になる問題を修正し、色トークン基盤を導入

ダークテーマ選択時に設定画面のラベル・入力欄・チェックボックスが判読不能になる問題を修正した。原因は3つ複合していた: (1) `QApplication` に `setStyle()` を指定していなかったためネイティブスタイルが `QPalette` を無視していた（実測: Windows 11 ネイティブスタイルの `QLineEdit` 背景 `#bcbdbf` はダーク文字色に対しコントラスト比 **1.59:1**、windowsvista スタイルは `#ffffff` で **1.18:1** — いずれも WCAG AA 基準 4.5:1 を大きく下回る）、(2) `QPalette` が 21 ロール中 11 ロールしか設定されておらず残り 10 ロールがシステム配色へフォールバックしていた、(3) light テーマ固定の色リテラルが `hve/gui` 配下 24 ファイルに 111 個・`mdq/gui` に追加 8 個、ハードコードされていた。極端な例では設定画面ラベルの前景/背景がともに `#1f2328` となりコントラスト比 **1.00:1**（実質不可視）だった。

- **`QApplication` に `Fusion` スタイルを固定した**。Fusion は `QPalette` の指定を正しく反映するため、実測コントラスト比は `#0d1117` 系で **16.02:1** まで改善した。
- **`hve/gui/theme.py` を新規作成し、色を単一の出所へ集約した**。VS Code の `registerColor(id, {light, dark})` パターンに倣い、全トークンに light/dark 両値を必須とする辞書（`TOKENS`）を定義し、`token()` / `build_palette()` / `build_stylesheet()` / `set_current_theme()` を通じて `hve/gui` 全体・`mdq/gui`（3 ファイル）・vendor 同期先（`tools/skills/markdown_query/vendor/mdq/gui/`）へ適用した。
- **`hveRole` プロパティによるテーマ即時追従を実装した**。ウィジェットに `setProperty("hveRole", ...)` を設定するだけでテーマ切替時に自動的に配色が追従する仕組みを導入し、再起動不要のテーマ切替を実現した。
- **チェックボックス / ラジオボタンのインジケーターを SVG 化した**（`hve/gui/icons/check.svg` / `radio-dot.svg` 新規）。Qt はサブコントロールを1つでも独自指定するとネイティブのチェックマークが消える仕様のため、checked / disabled 双方の状態を QSS + SVG で明示的に定義した。
- **WCAG AA 到達のためトークンを3件微調整した**（light テーマ）: `disabledForeground` `#6e7781`→`#656d76`、`warningForeground` `#9a6700`→`#8b5f00`、`palette.disabledText` `#8c959f`→`#818b95`。
- **色リテラル再混入防止のガードテストを追加した**（`hve/gui/tests/test_theme_tokens.py` 新規 22 件）。`hve/gui` / `mdq/gui` / `cq/gui` 配下で許可リスト外の色リテラル（`#RRGGBB` / `rgba(...)`）を静的スキャンで検出するテスト、未知の `hveRole` 値・`token()` 名を AST 解析で検出するテストの3種を追加した。

**既知の意図的な見た目の変更**（回帰ではない）: 全プラットフォームでネイティブ外観を喪失（`Fusion` 固定）／チェックボックス・ラジオの✓が同梱 SVG に変更／`FooterWidget` の統計ボタンの枠線が透明化（hover/checked の配色がテーマ追従するよう変更）／`mdq/gui` の警告バナーが赤系前景を失い枠線・背景での注意喚起に変更（文言は不変）。

**非対象**: `markdown_preview/assets/preview.html` / `widgets/xterm_assets/index.html`（Chromium 描画面、別機構が必要なため対象外）、`status_banner.py` / `dag_status_widget.py`（既に light/dark 両対応でトークン統合の必要なし）、高コントラストテーマの追加、OS 外観への自動追従。

**検証**: `hve/gui/tests` 全体（137 ファイル）は単一プロセスでの一括実行では環境要因（Qt offscreen の累積的リソース圧迫による非決定的クラッシュ/激重化、既知事象）により完走しないため、4 バッチに分割し各バッチを独立プロセスで実行して **1257 passed, 1 skipped, 2 subtests passed, 0 failed** を確認した。`hve/tests` 全体（約7,100件）は **7,119 passed, 18 skipped, 2 xfailed, 3 failed, 490 subtests passed**（829秒）で、失敗3件はいずれも静的差分・import参照の両面で本変更と無関係であることを確認済み（本変更はテーマ関連ファイルのみに限定され、失敗テストが参照するモジュールに一切触れていない）。実ウィンドウでの light/dark 目視確認は、検証実施時に端末画面が OS レベルでロックされていた環境要因により実施できず、上記の自動テスト証跡で代替した（レイアウト崩れの検出は本証跡の対象外であり、次回インタラクティブセッションでの目視確認を推奨事項として残す）。

### Changed — GUI 設定の「連携」を「各サービス連携」へ改称し、Agentic Retrieval を独立セクションへ移設

- 設定ツリーの「連携」を「各サービス連携」へ改称し、Azure の直後に **Agentic Retrieval** を追加した。
- 「基本設定」にあった 6 項目（`--enable-agentic-retrieval` ほか）を `_CAgenticRetrieval` へ移設した。`OptionsPage` から CLI 引数へ渡る値は不変である。
- 非対象: これら 6 項目の設定永続化（`settings_apply._SECTION_FIELDS` 未登録の既存挙動）、`Foundry Toolbox: tool search` の移設、i18n `.ts` / `.qm` の再生成。
- **検証**: 移設・設定画面・GUI ページ統合の focused suite は **120 passed**。棚卸し再生成後の `hve/tests/test_hve_surface_inventory.py` は **94 passed**。GUI 全体 suite は clean HEAD でも Qt 側の不安定な停止が発生するため、影響範囲テストで代替確認した。

### Added — `markdown-query` / `code-query` / Tool Search を他リポジトリへ手動同期できるようにした

3 つの機能はいずれも HVE 本体へ依存しないローカル完結の実装だが、他リポジトリへ持ち出す手段は「フォルダを手でコピーする」しかなく、版の追跡も旧ファイルの削除も行われていなかった。`tools/for-other-repo/` に宣言駆動の同期機構を追加し、コピー先パスを引数に取る script 1 本で 3 パッケージを配布できるようにした。

**配布機構（FR-KIT-06 新規）**

- **宣言を単一の出所にした**。`<package>/package.toml` が「どこから何を集めるか」だけを宣言し、コピー script が組み立てる。エンジン実体（`mdq` / `cq` / `toolsearch`）も Skill 定義も共通セットアップ実装も上流の既存の場所が正本のままで、宣言側へ複製しない。
- **版マニフェストを生成するようにした**。コピー先の `KIT-VERSION.json` に配布版・エンジン版・上流 commit・同期時刻・全ファイルの sha256 を記録する。上流と同版または降格となる同期は既定で拒否し、`--force` でのみ上書きする。前回配布に含まれ今回含まれないファイルは削除し、利用者が作った venv や設定は削除しない。
- **利用者が編集する前提のファイルを温存するようにした**。`preserve` に宣言したファイル（Tool Search の `policy.json`）は既存時に上書きせず、マニフェストの `preserved` へ記録して改変検出の対象から外す。
- **OS だけの状態からセットアップできるようにした**。`install.ps1` / `install.sh` は Python 3.11+ と git が無ければ OS のパッケージマネージャ（winget / choco / Homebrew / apt / dnf / yum / zypper / pacman / apk）で導入し、以降の判断は既存の `kit/kit_setup.py` へ委譲する。OS 別スクリプトに判断ロジックを持たせない方針（FR-KIT-03）は維持した。
- **上流の extras 相当を配布先でも入れられるようにした**。`extra_dependencies` の宣言を `install-extras.json` として同梱し、セットアップ時に kit の venv へ導入する。`code-query` の tree-sitter 文法群がこれに当たる。
- **コピー先だけで版と改変を確認できるようにした**。`install.py --version` / `--verify` は上流リポジトリを参照しない。
- Tool Search は Skill ではなくライブラリなので `.github/skills/` へは配置しない。配布用の CLI 入口（`dashboard` / `skills` / `policy` / `eval`）だけを新規に追加した。上流ではこの役目を `hve/__main__.py` の `toolsearch dashboard` が担っている。

**配布検証で見つかった既存不具合の修正**

- **`cq` の graph 抽出が文法未導入時に索引全体を落としていた（FR-CQ-11 違反）**。`cq/indexer.py` の symbol 抽出には「任意文法が無ければ lite へ降格する」処理があるが、`cq/graph.py` の参照・import 抽出には無く、`ExtractionError` がそのまま伝播していた。上流は `[code]` extras で文法が入っているため顕在化せず、配布キットを入れた他リポジトリで `.ps1` を 1 つ置いただけで `cq index` が異常終了する形で表面化した。降格処理を追加した。
- **`cq` の既定 profile 名が上流固有の `hve` で、配布先では必ず不一致になっていた（FR-KIT-04 改訂）**。`cq.toml` に profile が 1 つしか宣言されていなければそれを既定にするようにした。複数宣言時は推測せず従来の fallback のままとする。可搬性 E2E から `CQ_PROFILE=main` の注入を外し、上流固有の名前を与えずに検索が成立することを検証対象へ含めた。
- **Tool Search の配布物が上流の `mdq.search` へ暗黙依存していた（FR-KIT-05 違反）**。`toolsearch/ranking.py` の既定 BM25 実装は `mdq.search._MiniBM25` で、`mdq/tokenize.py` しか同梱していなかった。**検証を上流リポジトリを cwd として実行していたため `mdq` が上流側へ解決され、テストが偽 green になっていた**。配布先を cwd として再実行して `ModuleNotFoundError` を実測し、`mdq/search.py` を同梱対象へ追加した。遅延 import を静的に拾って同梱漏れを検出する回帰テストと、検証の cwd を配布先へ固定する修正を併せて入れた。
- **Debian / Ubuntu でセットアップが必ず失敗していた**。`install.sh` は Python インタプリタの有無しか見ておらず、Ubuntu 24.04 のように `python3` はあるが `python3-venv`（ensurepip）が無い環境では `python3 -m venv` が落ち、3 パッケージとも導入できなかった（実機実測）。ensurepip の有無を個別に確認し、不在なら venv 用パッケージを導入するようにした。導入後も使えなければ `--no-venv` を案内して fail-closed とする。
- **素の Windows では配布した `.ps1` がそもそもパースできなかった**。Windows PowerShell 5.1 は `.ps1` を ANSI として読むため、UTF-8（BOM 無し）で非 ASCII を含むスクリプトは起動前に構文エラーになる。素の Windows には 5.1 しか無いので、これは導入不能を意味する（Windows Sandbox で実測）。配布される `.ps1` を ASCII のみへ揃えた。既存の `tools/skills/*/{setup,sync-vendor,mdq,cq}.ps1` も em dash を含んでいたため同様に修正した（FR-KIT-04 の既存欠陥）。日本語の案内は UTF-8 を扱える `install.py` と `GETTING-STARTED.md` 側に残している。
- **winget が利用者のツールチェーンを更新しうる点を閉じた**。`winget install` へ `--no-upgrade` を付け、既に入っている Python / git を勝手に更新しないようにした。

**方針決定と非対象**: 手動同期を前提とし、自動配布・外部レジストリへの公開は対象としない。macOS の Homebrew 経路は実機が無く未検証（分岐ロジックのみ stub で確認）。winget が無い素の Windows では fail-closed とし、App Installer の自動導入は行わない。

**検証**: 新規 57 件（配布同期契約）を追加し、既存の配布キットテストと合わせて green を確認した。導入は **3 つの実環境**で検証した: Windows 11 / Python 3.14、Ubuntu 24.04 / Python 3.12（WSL2）、および **Windows Sandbox（pwsh / python / py / git / winget / choco が一つも無い素の Windows 11 + PowerShell 5.1）**。Windows では `mdq` 39 ファイル 402 chunk / `cq` 32 ファイル 0 errors（`.ps1` は tree-sitter）、Ubuntu では 3 パッケージとも exit 0 で venv 作成・依存導入・設定生成・Skill 配置・索引・検索まで通った。Sandbox では全 `.ps1` が 5.1 で parse-errors=0 となり、パッケージマネージャ不在を検知して exit 3 と導入先 URL を返した。配布先を cwd とした `toolsearch eval` は 73 entries / 42 queries で recall@5 0.869 / MRR 0.807 / トークン削減 91.3%。RED → GREEN を実機で確認した不具合は 4 件（`cq` graph 降格、`mdq.search` 同梱漏れ、Debian 系 venv 不備、PowerShell 5.1 パース不能）。winget 経路は PATH を削った子プロセスで実際に `winget install` を走らせ、PATH 再取得後に処理が継続することを確認した。GUI 起動導線は PySide6 未導入時の fail-closed（exit 2 と導入手順の提示）と、offscreen での vendored ウィンドウ構築を確認した。`hve/tests` 全体は **7,109 passed / 18 skipped / 2 xfailed / 490 subtests**。同時に失敗した 2 件（ASDW-WEB の Static Web Apps ワークフロー不在、aad-web fan-out メタ伝搬）は分離 worktree の HEAD でも同一に失敗することを確認しており、本変更とは無関係の既存の失敗である。

### Changed — Tool Search を HVE 自身で既定有効化し、生成 AI Agent 側の方針を全経路で強制するようにした

Tool Search が「HVE 自身の SDK セッション設定（`SDKConfig.tool_search`）」と「HVE が設計・開発する AI Agent の Foundry Toolbox 設定（`SDKConfig.enable_tool_search`）」の 2 ドメインに分かれている点を調査した結果、前者は実装済みだが既定無効、後者は Prompt の自己申告に依存し検証されていないことが分かった。前者を既定有効化し、後者を設計から実測評価まで機械検証できるようにした。

**HVE 自身の Tool Search（FR-MODEL-04 / FR-MODEL-06）**

- **既定を有効へ変更した**。`SDKConfig()` / `from_env()` / GUI の新規プロファイル初期値をいずれも有効にした。要件本文にも「既定を無効から有効へ変更した根拠は利用者の適用方針決定であり、削減率の実測を根拠としてはならない」と明記した。
- **明示的な無効化を上書きしない**ことを新要件 FR-MODEL-06 として定義した。`--no-tool-search` / `HVE_TOOL_SEARCH` の falsy / GUI 保存済み `false` は保持される。保存済み `false` が利用者の明示指定か旧既定かを実行時に区別できないため、移行処理は持たず新規プロファイルの初期値だけを変更した。
- `tool_search_ranking` の既定（`sdk`）と、SDK 未サポート時の縮退（FR-MODEL-05）は変更していない。

**生成 AI Agent の Tool Search 方針（FR-WF-AAG-01 / -02、FR-WF-AAGD-01〜04）**

- **方針を `auto` / `yes` / `no` の 3 値に固定した**。`auto` は Tool 総数（15 超）で判定、`yes` は総数に関係なく採用、`no` は Toolbox を作らず TB-CAP-03〜05 を理由付き N/A とする。3 値以外は既定へ丸めず blocked とする。
- **CLI / GUI / Cloud の 3 面で選択肢と意味を一致させた**。Cloud は AAG / AAGD 双方の Issue Form に設問を追加し、Root メタデータタグ経由で Step 本文と validator へ同一値を届ける。方針 `no` のときは AAGD の実測評価 Step を作成しない（実装・デプロイ Step は止めない）。
- **設計 validator を方針対応にし、Tool 集合の完全一致を検証するようにした**。検索メタデータ表が全 Tool を過不足なく 1 行 1 件で持つこと、pin 列が pin ポリシーと一致することを検査する。従来は Tool 総数の一致しか見ておらず、行数が合っていて中身が欠けた表を検出できなかった。
- **実装・デプロイ・実測評価の各成果物を gate した**。Agent 設定・System Prompt・テスト仕様のトレースを設計値と照合し、デプロイスクリプトは Agent 登録前の Toolbox 作成順序・プレビューヘッダー・トークンスコープ・version 指定エンドポイントを、検証スクリプトは初期ツール一覧・pin 集合・発見と実行・上限・version を fail-closed で確認することを静的に検査する。SDK シンボル名や API version は preview で変動するため検証対象にしていない。
- **実測評価レポートを必須成果物にした**。従来は Toolbox を持たない Agent を「成果物なしで完了」としており入出力契約（`required: true`）と矛盾していたため、理由付き N/A レポートの作成を必須に変更した。有効な Agent には評価クエリ 10 件以上・複数 Tool 併用 3 件以上・on/off 両条件・未測定理由・判定への結論を要求し、公開ベンチマーク値を実測欄の出所にすることを FAIL とする。数値の正しさは判定せず、測定構造と証跡の存在だけを検証する。
- **Cloud の完了判定を成果物の内容で再確認するようにした**。全 Issue がラベル上 done でも、チェックアウト済みブランチの成果物が不正なら Post-DAG の自己改善へ進ませない。Azure へは接続せず、既存の成果物 validator と GitHub Issue の読み取りだけを使う。

**方針決定と非対象**: 実 Foundry / Azure への書き込みを伴う live 検証は本変更に含めない（別途承認のうえ実施）。検索ランキングアルゴリズムの変更も対象外。

**検証**: 全 16 タスクを RED → 最小実装 → 個別回帰 → 敵対的レビュー（6 軸）→ 指摘反映の順で実施し、各タスクで Critical 0 を確認した。最終スナップショットで `hve/tests` 全体を実行し **7,061 passed / 18 skipped / 2 xfailed / 490 subtests** を確認した。同時に検出された失敗のうち 2 件（gate 対象の完全一致アサーション、面横断索引の陳腐化）は本変更に起因するため修正し、再実行で解消を確認した。残る 2 件（ASDW-WEB の Static Web Apps ワークフロー不在、aad-web fan-out メタ伝搬）は分離 worktree で HEAD でも同一に失敗することを確認しており、本変更とは無関係な既存の失敗である。Cloud ワークフローは YAML パースと全 run ブロックの `bash -n` を通し、いずれも構文エラー 0 件だった。要件対応表の判定を実測結果に合わせて更新し、TDD 索引を再生成した。

### Changed — 恒久成果物からの `work/` 出典引用を除去し、CHANGELOG の引用ポリシーを明確化した

`work/` はジョブ完了後に削除されてよい使い捨て領域だが、`docs/catalog/app-catalog.md` 等の恒久成果物や本 `CHANGELOG.md` 自身が `work/run/` `work/analysis/` 配下のパスをリンク／コードスパンで出典引用していた。実際に一部（`app-catalog.md` の完全版UC×APP行列、本ファイル旧エントリの検証証跡）は既に消失済みであることを確認し、この引用習慣がリンク切れ・再現不能な事実を生む構造的リスクであると判断した。

- **ルール追加**（[.github/skills/work-artifacts-layout/SKILL.md](.github/skills/work-artifacts-layout/SKILL.md), [.github/copilot-instructions.md](.github/copilot-instructions.md)）: 恒久成果物（`docs/` `knowledge/` `qa/` `src/` 等）から `work/` への出典引用を禁止する規定を追加した。唯一の例外は本 `CHANGELOG.md` で、そこでもパス／リンクは禁止し要約文字列のみ許可する。
- **恒久成果物の是正**（[docs/catalog/app-catalog.md](docs/catalog/app-catalog.md), [docs/catalog/screen-service-consistency-report.md](docs/catalog/screen-service-consistency-report.md), [src/test/ui/APP-009-S005/README.md](src/test/ui/APP-009-S005/README.md), [src/test/ui/APP-009-S006/README.md](src/test/ui/APP-009-S006/README.md), [src/infra/azure/data-verify/Dockerfile](src/infra/azure/data-verify/Dockerfile)）: `work/` への出典引用を除去した。`app-catalog.md` の完全版UC×APP R/S/N行列（旧 `[MATRIX]`）は分離先の作業ファイルが既に失われていたため、内容を復元せず「TBD（要確認）: 未整備」と正直に記録した。`data-verify/Dockerfile` はピン留めパッケージ・バージョンの根拠を `work/analysis/` への参照からコメント内へ直接記載する形に変更した。
- **HVE自身のドキュメントの是正**（[hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md), [users-guide/agentic-retrieval-guide.md](users-guide/agentic-retrieval-guide.md), [users-guide/tool-search-guide.md](users-guide/tool-search-guide.md), [users-guide/tool-search.md](users-guide/tool-search.md)）: `work/` へのパス／リンクを除去した。いずれも既存の周辺プレーンテキストが事実を十分に説明していたため、内容の重複追加はしていない。
- **本 CHANGELOG の是正**（本ファイル）: 過去エントリ 10 箇所の `work/run/` `work/analysis/` へのパス／リンクを除去した。1 件（Final-Validation 検証証跡）はローカル限定で作成されリポジトリに commit されなかったファイルであったため、内容を捏造せず「commit されておらず現存しない」事実を明記した。残りは既存の要約プレーンテキストで内容が十分に説明されていたため削除のみとした。`work/` の構造・ライフサイクルそのものを説明する既存の記述（例: GUI セッション隔離、`resolve_work_root()` の挙動）は出典引用ではないため対象外とした。

**対象外（意図的）**: [hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) の一般的な将来データソース言及、[docs/services/SVC-23.md](docs/services/SVC-23.md) のコンプライアンス宣言（他Stepの `work/run/` 成果物を参照していない旨）は、特定の `work/` ファイルへの出典引用ではないため変更していない。

**検証**: 全対象ファイルを再走査し、恒久成果物・HVE自身のドキュメント・CHANGELOG本体から `work/run/` `work/analysis/` `work/hve-tool-search/` へのMarkdownリンク／コードスパン出典が0件であることを確認した。各修正は敵対的レビュー（6軸）を実施し、指摘（`hve-dev/requirement-test-mapping.md` での編集誤りによるテーブル破損1件、`app-catalog.md` §14の矛盾記述1件、`CHANGELOG.md` 修正漏れ1件）を検出・修正のうえPASSとした。[hve/tests/test_code_query_scope_contract.py](hve/tests/test_code_query_scope_contract.py) と [hve/tests/test_hve_requirement_traceability_contract.py](hve/tests/test_hve_requirement_traceability_contract.py)（計61件）がPASSすることを確認した。本変更はドキュメント／コメントのみでコード動作を変更していないため、それ以外のビルド・実行時テストは対象外。

### Added — SDK のツール定義遅延ロード (`tool_search`) を CLI / GUI から設定できるようにした

1 ラン（`asdw-web` / 866 ラウンドトリップ）の実測ログを解析したところ、**ツール定義がコンテキストの p50 47.9%（最大 72.8%）を占め**、866 ターンで再送された量は **47,599,512 tokens = 全入力の 45.0%**（ブレンド単価換算 **852.93 AIU 相当**）だった。さらにセッションへ登録された **171 ツール / 54,865 tokens** のうち、そのランで実際に呼ばれたのは **10 種 / 9,108 tokens（16.6%）** で、**45,757 tokens（83.4%）が一度も使われずに毎ターン運ばれていた**。内訳は azure MCP が 136 ツール / 37,342 tokens（68%）、単体最大は `skill` の 6,375 tokens。

GitHub Copilot SDK 1.0.7 には `create_session(tool_search=...)`（ツール定義を遅延ロードし、必要時に `tool_search_tool` で発見させる）が存在するが、HVE はこれを一度も渡していなかった。要件は **FR-MODEL-04 / FR-MODEL-05** として [hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) §3.5 に新設した。

- **`SDKConfig.tool_search`（既定 `False`）を追加した**（FR-MODEL-04）。有効時のみ SDK へ `tool_search={"enabled": True}` を渡し、無効時は引数自体を渡さない。環境変数 `HVE_TOOL_SEARCH` からも読む。
- **Step 実行経路の全セッションへ同一値を伝搬する**。メインセッション（[hve/runner.py](hve/runner.py)）、サブセッション（Pre-QA / Review、`_build_sub_session_opts`）、Self-Improve セッション（[hve/self_improve.py](hve/self_improve.py)）の 3 経路。
- **CLI に `--tool-search` / `--no-tool-search` を追加した**（`BooleanOptionalAction`、既定は `SDKConfig` を継承）。GUI は設定画面のチェックボックスと `OrchestrateArgs` → CLI argv 変換を追加し、GUI 実行でも同じ経路を通るようにした。
- **SDK 未サポート時は当該引数を外して再試行する**（FR-MODEL-05）。既存の `reasoning_effort` 縮退と同じ仕組み（`_create_session_with_auto_reasoning_fallback` の除去対象キーワード）へ `tool_search` を加えた。未サポートを理由に実行を止めない。
- **`defer_threshold` は設定として公開していない**。SDK 既定で足りるかを未検証のまま設定項目を作らないため。

**Fleet mode 親セッション（[hve/orchestrator.py](hve/orchestrator.py)）は対象外とした**。当初は「Orchestrator セッション」も伝搬先に含める計画だったが、実体は opt-in（既定 OFF）の Fleet 親セッションで、コード上「意図的にツール公開を狭めている」と明記された別系統であり、実測ログ（通常 Step 経路）に当該経路の根拠がないため要件から外した。

**命名が近い既存フィールドとの区別**: 本変更の `SDKConfig.tool_search` は **HVE 自身の SDK セッション設定**である。並行して存在する `SDKConfig.enable_tool_search`（`"auto"` / `"yes"` / `"no"`）は **AAGD ワークフローが生成する AI Agent の Foundry Toolbox 設定**で、別ドメインの値である。FR-MAINT-07 の面横断確認でこの近接を検出したため、要件本文・[hve/config.py](hve/config.py) のコメント・[hve/tests/fixtures/option_parity_matrix.yaml](hve/tests/fixtures/option_parity_matrix.yaml) の注記に区別を明記した。

**効果の主張は本変更に含めない**。`tool_search` の削減効果は `get_current_metadata()` では観測できず（on/off で登録ツール一覧が 171 tools / 54,865 tokens と完全に同一だった。deferral はプロンプト構築時に効くため）、実プロンプトを送る A/B 実測が必要である。したがって本変更の受入基準は **設定が全経路へ正しく伝搬すること**に限定し、削減率の主張は行わない。

**検証**: RED を各タスクで先行確認した（config 10 failed `AttributeError: no attribute 'tool_search'` / runner メイン 1 failed / runner サブ・縮退 3 failed / CLI 3 failed `unrecognized arguments: --tool-search` / GUI argv 2 failed / self-improve 1 failed `None != {'enabled': True}`）。GREEN は [hve/tests/test_config.py](hve/tests/test_config.py) **112 passed**、[hve/tests/test_runner.py](hve/tests/test_runner.py) **203 passed**、[hve/tests/test_self_improve.py](hve/tests/test_self_improve.py) **164 passed**、[hve/tests/test_main.py](hve/tests/test_main.py) **234 passed / 1 skipped**、GUI 設定系（[hve/gui/tests/test_orchestrate_args.py](hve/gui/tests/test_orchestrate_args.py) / [hve/gui/tests/test_github_section_consolidation.py](hve/gui/tests/test_github_section_consolidation.py) / [hve/gui/tests/test_cq_settings_section.py](hve/gui/tests/test_cq_settings_section.py)）**36 passed**、[hve/tests/test_phase6_option_parity.py](hve/tests/test_phase6_option_parity.py) **57 passed**。TDD 索引を再生成し、FR-MODEL-04 / 05 が `active-or-described` として登録されることを確認した。

**回帰**: `hve/tests`（6,610 件 / 272 ファイル）を分割して全区間実行した（`hve/tests/test_gui_doc_convert.py` は本変更と無関係に応答しなくなるため除外）。前半区間（0〜54%）は失敗 1 件のみで、`-x` 実行によりその 1 件を **1,764 passed / 1 failed / 9 skipped** の時点で特定した。後半区間（44〜100%、143 ファイル）は **3,681 passed / 1 failed / 6 skipped**。両区間は 44〜54% で重なるため全体を網羅している。失敗 2 件はいずれも本変更と無関係であることを確認した。

- `hve/tests/test_asdw_web_step_scoped_cicd_contract.py::test_app009_swa_workflow_exists_and_uses_oidc_dynamic_token` — `FileNotFoundError: .github/workflows/azure-static-web-apps-app009.yml`。ASDW が生成する成果物の不在であり、SDK セッション設定とは無関係。
- `hve/tests/test_orchestrator.py::TestRunWorkflowFanout::test_aad_web_fanout_meta_is_forwarded_to_step_runner` — Step 2.2 の service catalog fan-out が展開されない件。`git worktree` でクリーンな HEAD（`3afd2477`）を切り出して同テストを実行し、**同一の `AssertionError: [] is not true` で失敗すること**を確認した（既存 failure）。

型検査では変更した 9 ファイルのうち GUI 5 ファイルが errors 0 件、残り 4 ファイルの指摘はすべて既存箇所（dual-import の fallback や未変更行）で、**本変更が追加した行に指摘は 1 件もない**。

**併せて修正**: 直前の Unreleased エントリが「`test_coverage_all_sdkconfig_fields_registered` が `tool_search` の fixture 未登録で失敗する」と記録していた件を、[hve/tests/fixtures/option_parity_matrix.yaml](hve/tests/fixtures/option_parity_matrix.yaml) の `sdkconfig_internal_fields` へ `tool_search` を追加して解消した（同テストを含む 57 件が GREEN）。

### Added — GUI / CLI / CUI / Autopilot に共通の実行時 Dashboard と Observability を追加した

HVE には実行面が 6 つ（GUI Workbench / GUI Autopilot / 対話 CLI / 直接 `orchestrate` / CUI Workbench / CLI Autopilot）と互換面が 1 つ（`--autopilot-child`）あるが、実行中の状態と統計を見られるのは実質 GUI Workbench だけだった。CUI Workbench は Context・model・経過時間しか持たず、CLI Autopilot は APP の完了数と終了コードしか集約せず、`--autopilot-child` のウィンドウは `[hve:stats]` 行を破棄していた。要件は **FR-RTO-01〜06 / NFR-RTO-01〜03** として [hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) §3.11 に新設した（entrypoint 要件 `FR-CLI-10` は改訂対象外と明記）。

- **観測イベントの構築と解析を 1 実装へ集約した**（FR-RTO-01 / FR-MAINT-07）。[hve/runtime_observability.py](hve/runtime_observability.py) を新設し、既存の `[hve:stats]` 行形式と `kind` / `step` キーを保ったまま `schema_version` / `ts`(UTC ISO8601) / `seq` / `pid` / `run_id` / `workflow_id` / `instance_id` を付与する。`instance_id` は `workflow_id`、APP 並列時のみ `workflow_id#app_id`。**未知 `kind` は破棄せず件数を計上する**（従来の GUI パーサは未知 kind を「消費済み」として無言で捨てていた）。
- **「収集」「保存」「子プロセスへの配信」「人間向け表示」を分離した**（FR-RTO-02）。`quiet` / `final_only` でも収集・保存・子配信は継続し、抑止するのは人間向けの追加表示だけにした。従来は `Console.step_start` / `step_end` / `skill_invoked` が `quiet` で観測イベント自体を発火せず、GUI から `--quiet` を選ぶと進捗表示が止まる構造だった。
- **run-scoped な JSONL を追加した**（FR-RTO-03 / FR-RTO-06）。`resolve_work_root()` 配下の `observability/events-<pid>.jsonl` へ 1 行 1 JSON（UTF-8 / LF / BOM なし）で追記する。`HVE_WORK_ROOT` 未設定と `--dry-run` では書かない。**同一プロセス内の追記はロックで直列化する**（DAG は 1 プロセス内で複数 Step を並列実行するため、プロセス別ファイルだけでは行破損を防げない）。32 MiB で追記を停止し警告は 1 回だけ出す。書き込みは実行プロセスが所有し `run_workflow` の終了時に必ず閉じるため、GUI セッションの `purge` / `archive` と競合しない。
- **保存項目を allowlist にした**（FR-RTO-04 / NFR-SEC-01）。状態・時刻・数値・モデル ID・識別子・例外型名・リポジトリルート相対パスだけを保存し、prompt 本文・応答本文・reasoning・tool の引数と出力・環境変数・認証情報・生 SDK ペイロードは保存しない。診断専用 kind（`assistant_usage_raw` / `debug_env` / `assistant_usage_raw_err`）はイベントごと保存対象外。パスは相対化できたものだけ残し、`src/../../etc/passwd` のような離脱は正規化して破棄する。
- **CUI Workbench に統計を表示できるようにした**（FR-RTO-05）。Footer へ Context / Model / 経過時間に加えて Token・AI Credit・Reqs・Tools・Skills を出し、`/stats` で詳細スナップショットを表示する。`[hve:stats]` の生 JSON は本文ペインへ流さない。
- **Workbench を使わない CLI に 1 行ステータスを配線した**。実装済みだがどこからも呼ばれていなかった [hve/statusline.py](hve/statusline.py) を `run_workflow` へ接続し、既存の `pricing_statusline_enabled` と `HVE_NO_STATUSLINE` で制御する。非 TTY では再描画せず、終了時に集計を 1 回だけ出す（`quiet` / `final_only` では出さない）。
- **GUI と CLI Autopilot を instance 単位で分離集計するようにした**。GUI は解析を core 実装へ寄せ、`workflow_id#app_id` ごとに統計を保持する。CLI Autopilot は子プロセスの stdout を読み、APP / Workflow 別の集計と全体サマリーを出す。`--autopilot-child` の互換ウィンドウも統計を取り込むようにした。

**新規の CLI オプションと `SDKConfig` フィールドは 1 つも追加していない**（NFR-RTO-02）。追加した環境変数は CLI Autopilot 親が子へ配信を許可する `HVE_STATS_STREAM` の 1 個だけで、本変更は [hve/config.py](hve/config.py) と [hve/tests/fixtures/option_parity_matrix.yaml](hve/tests/fixtures/option_parity_matrix.yaml) を変更していない。外部 telemetry 送信・閾値アラート・run を跨いだ履歴検索は対象外とした。

**既知の制約**: JSONL のプロセス内順序は `seq` により厳密だが、**プロセス間の時刻順序は近似**である（並列実行される子プロセス間で時刻がずれ得るため）。run 単位の合算では Context 使用量を埋めない（instance ごとの現在値であり、合算に意味がないため）。

**検証**: RED は各タスクで先行確認した（core は `ImportError: cannot import name 'runtime_observability'`、以降は registry 5 failed / 永続化 16 failed / Console 10 failed / producer 5 failed / CUI 5 failed / GUI 7 failed / CLI Autopilot 8 failed。内訳は [hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) §3.11 に記録）。GREEN は新規観測系 11 ファイルが **120 passed**、GUI 側の新規と既存統計テスト 8 ファイルが **128 passed**、CUI Workbench 関連 9 ファイルが **101 passed**、Console / dag_executor / autopilot / statusline / entrypoint / option parity の既存テストが **318 passed**。TDD 索引を再生成し、FR-RTO-01〜06 / NFR-RTO-01〜03 の 9 件が `active-or-described` として登録されることを確認した。

**検証の限界**: `hve/tests` 全体実行はゲートに使っていない。作業ツリーに本変更と無関係の進行中作業（Agentic Retrieval / tool search / mdq / cq）が同居しており、全体実行が 45% 地点で進まなくなったため打ち切った。本変更の検証は、変更したモジュールを直接カバーする範囲で行っている。なお `hve/tests/test_phase6_option_parity.py::TestOptionParityMatrix::test_coverage_all_sdkconfig_fields_registered` は失敗するが、原因は並行作業（FR-MODEL-04）が [hve/config.py](hve/config.py) へ追加した `tool_search` フィールドが fixture 未登録であることで、**本変更の差分に `tool_search` は 1 件も含まれない**（`hve/config.py` と fixture は本変更で未編集）。

### Changed — `[hve:stats]` の stdout 出力を子プロセス実行時に限定した

従来は verbosity に関係なく常に stdout へ機械可読 JSON を書いており、通常の CLI 実行でも人間向けログに `[hve:stats] {...}` が混ざっていた。CUI Workbench 有効時は `Console._emit` 経由で本文ペインにも同じ行が入っていた。

`[hve:stats]` を stdout へ流すのは、GUI 子プロセス（`HVE_GUI_SESSION_ID`）と、Dashboard を持つ親が `HVE_STATS_STREAM=1` を付けて起動した子プロセスだけにした。GUI と Autopilot が依存する行形式・`kind`・既存キーは変更していないため、受信側の互換は保たれる。

これに伴い [hve/tests/test_console.py](hve/tests/test_console.py) の `TestFileIO::test_emits_stats_event_file_io` を「常時 stdout へ出力」から「子プロセス実行時のみ配信し、収集は継続する」へ改訂した。

**検証**: `hve/tests/test_console.py` と `hve/tests/test_console_runtime_observability.py` で 184 passed。GUI 受信側の非退行は `hve/gui/tests/test_footer_stats.py` / `test_stats_detail.py` / `test_autopilot_stats_propagation.py` を含む 128 passed で確認した。

### Fixed — `permission_count` の観測イベントが常に失われていた

[hve/runner.py](hve/runner.py) の `permission.requested` ハンドラが `stats_event("permission_count", step_id=..., count=..., kind=kind_str)` を呼んでおり、`Console.stats_event(kind, step_id="", **fields)` の第 1 引数と衝突していた。実測で `TypeError: Console.stats_event() got multiple values for argument 'kind'` を確認しており、呼び出しが `try/except Exception: pass` に包まれているため**例外は握り潰され、イベントは一度も発火していなかった**。フィールド名を `permission_kind` へ改め、権限要求が集計されるようにした。

あわせて、ツール実行の**失敗**が観測イベントとして残っていなかった点も修正した。従来 `tool_result` は成功時にしか発火せず（NFR-OBS-07 の降格判定用）、失敗はテキストログにしか現れなかったため、Dashboard から失敗件数を数えられなかった。失敗時も `tool_result`（`success=false`）を発火し、`RuntimeMetrics.tool_failures` として集計する。

**検証**: 修正前に `Console.stats_event("permission_count", step_id=..., count=..., kind=...)` を実行して `TypeError` を再現確認した。RED は [hve/tests/test_runner_runtime_observability.py](hve/tests/test_runner_runtime_observability.py) 5 failed、GREEN 後は `hve/tests/test_runner.py` を含めて非退行を確認した。

### Fixed — DAG の終端状態の一部が観測イベントに現れていなかった

[hve/dag_executor.py](hve/dag_executor.py) は Fleet 経路（`_apply_fleet_wave_result`）でしか `step_status` を発火しておらず、通常経路の `inactive` skip、`fanout-empty` skip、依存未解決の `blocked` は状態集合には入るのに観測イベントが出ていなかった。GUI のツリーは `[main]` 側のログから状態を復元できるが、CUI と CLI Autopilot は当該 Step が未実行のまま残って見える。これらの終端遷移でも `step_status` を発火するようにした。

**検証**: RED は [hve/tests/test_dag_executor_runtime_observability.py](hve/tests/test_dag_executor_runtime_observability.py)、GREEN 後に既存 `hve/tests/test_dag_executor.py` と合わせて非退行を確認した。`blocked` の発生条件が `dag_plan` 併用経路に限られることを実装で確認し、テストを実経路に合わせて是正した。

### Added — code-query が 0 件のときに連言を緩和し、ファイルパスでも引くようになった

Coding Agent がソースコードを横断検索する用途で、`cq search` が 0 件を返す場面を実測したところ、原因が 2 つに分かれた。要件は **FR-CQ-06** の改訂として [hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) §3.9 に定義した（新規 ID は起こしていない）。

- **BM25 が 0 件のとき、語の連言を選言へ 1 回だけ緩和して再試行するようにした**。FTS5 の既定は暗黙 AND なので、語数が増えるほど 0 件になりやすい。実測では `token budget`（2 語）が 5 ヒットなのに `token budget cap search hits`（5 語）は 0 件、`fan out parent child`（4 語）が 5 ヒットなのに 7 語にすると 0 件だった。緩和で得たヒットは `match` が `or-fallback` になり、呼び出し側が確度の低いヒットとして区別できる（symbol 経路の `name-fallback` と同じ表現方法）。**CJK を含むクエリは緩和しない**。「日本語の自然文で英語のみのコードを探すクエリには、誤った上位ヒットを返すより 0 件を返す」という既存の方針（FR-CQ-06 の既知の限界）を維持するためで、実測でも日本語ゴールデン 1 問は緩和後に 5 件返るが期待着地点は圏外だった。
- **すべての検索層が 0 件のとき、リポジトリ相対パスの部分一致で引く層を最後に追加した**（`route` が `path`）。`chunks_fts` の索引列は `name` / `signature` / `ident_text` / `text` の 4 列だけで**パスを含まない**ため、pytest の失敗出力に必ず現れるテストモジュール名は、索引が最新でも到達不能だった。実測: `test_asdw_data_private_verify_validation` は再索引後も 0 件だったが、本変更で当該ファイルを返す。ファイルごとに先頭チャンク 1 件へ畳み、並びはテストパスを後ろへ回してからパス長昇順。絞り込みは `files`（実測 830 行）側で行う。`chunks`（実測 14,169 行）を走査すると同じ結果に **6〜17 倍**の時間がかかるため（`runner` で 16.60 ms → 0.95 ms）。`--mode path` は用意していない（fallback 連鎖専用）。

**実測（本変更で 0 件から到達できるようになった例、profile=hve）**:

| クエリ | 変更前 | 変更後の top-1 |
|---|---:|---|
| `how does the orchestrator decide fan out` | 0 件 | `hve/orchestrator.py:1682-1693`（`match=or-fallback`） |
| `fan out parent child relationship in orchestrator` | 0 件 | `hve/orchestrator.py:4581-4609` |
| `structure aware chunking cast split then merge` | 0 件 | `cq/chunking.py:1-24` |
| `why does the deploy gate run before the test gate` | 0 件 | `hve/cloud_aagd_gate.py:1-21` |
| `test_search_recall` | 0 件 | `cq/tests/test_search_recall.py:1-20`（`route=path`） |

緩和は 0 件時にしか実行されない。選言の所要時間は実測で 4 語 24.8 ms / 10 語 117.9 ms（連言は 0.16 ms）。

**検証**: RED は `cq/tests/test_search_recall.py` 4 failed / 7 passed、`cq/tests/test_search_path_route.py` 5 failed / 3 passed。GREEN は 15 passed / 9 passed。`cq/tests` 全体 **587 passed**。ゴールデン非退行は profile=hve / app とも top-1 **0.9524** / top-k **0.9524** で変更前と一致（[hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) の FR-CQ-06 節に記録）。

**既知の制約**: CJK だけで構成される自然文クエリ（語が 1 つに潰れるもの）は引き続き 0 件を返す。字句検索の原理的限界であり、形態素解析器を導入しない前提を維持している。

### Changed — code-query のトークン予算を「実際に返すもの」で数えるようにした

`--max-tokens` が守られていなかった。要件は **NFR-CQ-01** と **FR-CQ-09** の改訂として定義した。

- **`cq search` の予算を、抜粋の長さではなく 1 ヒット分の返却 JSON 全体で見積もるようにした**。従来は snippet の文字数 ÷ 4 だけを数えており、メタデータ（`path` / `lines` / `route` / `score` / `parser` / `chunk_id` / `signature`）が会計外だった。実測では `--return-unit line` の 1 ヒットが合計 **160 tokens**、うち **101 tokens（63%）がメタデータ**である（`ensure_ascii=True` の CLI 実出力形式、`tiktoken/cl100k_base`）。見積り誤差は実測で **×2.49〜27.50 → ×1.53〜1.86** に縮んだ。`ensure_ascii=True` で数えるのは CLI の実出力と同じ形にするため。**文字数 ÷ 4 の概算と、先頭 1 件を必ず返す振る舞いは変えていない**（検索経路へトークナイザを持ち込まないため）。
- **`cq map` の予算を、描画後の出力全体で判定するようにした**。従来は掲載する定義行だけを数えており、`render()` が付加するファイル見出し・折り畳み記号・区切りの空行・除外件数の通知行が会計外だった。実測では `--paths "hve/gui/*" --max-tokens 400` の実出力が 657 tokens（予算の **×1.64**）だった。トークナイズは文字列連結に対して加法的でないため、見積りで選んだあとに**実際の描画結果を計測して超過分を落とす**。

**実測（profile=hve）**:

| 対象 | 条件 | 変更前の実出力 | 変更後の実出力 |
|---|---|---:|---:|
| `cq map` | `--paths "hve/gui/*" --max-tokens 400` | 657 tokens（掲載 20 件） | **386 tokens（掲載 11 件）** |
| `cq map` | `--max-tokens 1200`（全体） | — | **1,121 tokens（掲載 26 件）** |

`cq map` は**同じ予算で掲載される件数が減る**（実測で約 45%）。予算を守ることと引き換えの帰結であり、[users-guide/skills-code-query.md](users-guide/skills-code-query.md) と [.github/skills/code-query/references/cli-reference.md](.github/skills/code-query/references/cli-reference.md) へ明記した。

**`cq search` の `--max-tokens` は依然としてハードキャップではない。** (1) 先頭 1 件は上限を超えても返す（実測: `--return-unit chunk` の `run_workflow` は 1 ヒットで見積り 914、予算 800）。(2) 文字数 ÷ 4 の概算はコードに対して `tiktoken` より約 1.5 倍過小に出る（実測: 見積り 694 に対し実測 1,039）。本変更の目的は「メタデータを会計外にしない」ことであり、この 2 点は対象外である（前者は仕様、後者は検索経路へトークナイザを持ち込まないため）。

**検証**: RED は `cq/tests/test_search_budget.py` 2 failed / 3 passed、`cq/tests/test_repomap_budget.py` 3 failed / 5 passed。GREEN は 5 passed / 8 passed。既存の予算テスト 3 件（`test_max_tokens_caps_the_response` / `test_first_hit_survives_a_tiny_budget` / `test_chunk_unit_never_returns_more_hits_than_line_unit`）は変更なしで通る。

### Fixed — code-query の文書に残っていた「動かない実例」と再現しない実測値を訂正した

先行調査で見つかった文書の欠陥を、実行して確認した内容へ差し替えた。

- **0 件を返す実例を削除した**。[.github/skills/code-query/references/cli-reference.md](.github/skills/code-query/references/cli-reference.md) と [users-guide/skills-code-query.md](users-guide/skills-code-query.md) が例示していた `--q "fan-out の親子関係" --mode bm25` は実測 0 件だった。実行して出力を確認した 2 例へ差し替えた。
- **再現しない実測値へ計測条件と計測日を付した**。[.github/skills/code-query/references/repo-specific/hve-integration.md](.github/skills/code-query/references/repo-specific/hve-integration.md) と `users-guide` の「hve 84.8 トークン / 9.6 ms」は当時のコーパスと計測条件での値で、現在は再現しない。2026-08-04 の実測（探索空間・トークン計数器つき）へ差し替え、**レイテンシ列は削除**した（本環境では同一コマンドが 431.83 s と 69.85 s のように 6 倍以上ばらつくため）。あわせて **`app` profile では探索空間を揃えると `grep` の方がトークンが少ない**（148.8 対 236.0）という不利な実測も記載した。
- **`SKILL.md` の「索引は常に最新に保たれる」に注記を追加した**。一度も索引されていない新規ファイルは検索時の差分突合の対象外で、stale 警告にも現れない。`users-guide` §2.2 には記載があったが Skill 定義側に無く、0 ヒットの原因を Agent が判別できなかった。
- **トレーサビリティの矛盾記述を是正した**。[hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) の FR-CQ-08 に「非実装（意図的）: HVE Orchestrator からの watcher 自動起動は行わない」と記載されていたが、[hve/orchestrator.py](hve/orchestrator.py) は実際に `CqWatcher` を起動しており、`cq_watch` は option parity matrix にも登録され `users-guide` §11.4 に挙動が文書化されていた。実装に合わせて書き換えた。

**検証**: 差し替えた実例はすべて実行して出力を確認した。配布キットの同期検証（`test_cq_vendor_sync` / `test_skill_bundle_sync` / `test_kit_bundle_sync` / `test_portable_kit_e2e` / `test_code_query_skill_wiring`）は **106 passed**、`python .github/scripts/validate-skill-routing.py` は exit 0。

**既知の制約**: FR-CQ-12（`mdq` の検索品質の非退行）は実測していない。本変更は `mdq` 配下を 1 ファイルも編集しておらず、`mdq → cq` / `cq → mdq` の import は 0 件、索引 DB は FR-CQ-01 により物理分離されているため影響経路が無い。加えて本作業と並行して別セッションが `mdq/search.py` / `mdq/cli.py` / `mdq/tokenize.py` を編集中であり、測定値を本変更へ帰属できない。並行作業のコミット後に改めて実測すること。

### Added — markdown-query の日本語検索を bigram 照合と文脈付与で強化し、鮮度検知と所在のみ返却を追加した

大量の Markdown を Coding Agent が横断検索する用途で、既定の in-memory BM25 経路が日本語を 1 文字 1 トークンへ分解しており、語の連続性を一切見ていなかった。文字の出現回数だけで順位が決まるため、複合語のクエリで無関係なチャンクが上位に来ていた。要件は **FR-MDQ-08** / **FR-MDQ-09** / **FR-MDQ-10** として [hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) §3.8 に追加した。

- **CJK の連続部を隣接バイグラムへ分解して照合するようにした**（FR-MDQ-08）。`mdq/tokenize.py::scoring_terms` を新設し、CJK 連続部は隣接 2 文字の語へ、隣に CJK が無い 1 文字はそのまま、ASCII 連続部は小文字化するだけで分割しない。同一箇所が 2 文字語と 1 文字語の両方を出すことはない。Lucene の `CJKBigramFilter` / Elasticsearch の `cjk_bigram` と同じ考え方で、形態素解析器は導入していない。
- **リポジトリ相対パスと見出し経路をスコアリング対象へ加えた**（FR-MDQ-08）。`mdq/search.py::_scoring_text` が `path` + `heading_path`（`HEADING_WEIGHT = 3` 回）+ 本文を連結する。抜粋にはパスも見出しも混入せず、ヒットの行範囲も本文の位置を指したままである。重み 3 は後述のゲートを通過した値であり、重みそのものの最適化は行っていない。
- **索引と作業ツリーの乖離を検知して警告するようにした**（FR-MDQ-09）。`mdq/freshness.py` を新設し、索引済みファイルのサイズと更新時刻だけを比較する（内容ハッシュは読まない）。乖離時は `{"warning":"stale","changed":N,"hint":"..."}` を **stderr** へ出す。ヒットの JSONL（stdout）は形式が変わらない。`--no-freshness-check` で無効化できる。検知が例外で失敗しても検索結果は返る。
- **本文を返さない返却単位 `--return-unit locations` を追加した**（FR-MDQ-10）。識別子・パス・見出し経路・行範囲・スコアだけを返し、`--include-parent` / `--expand-neighbors` / `--merge-parts` の拡張からも本文を除く。既定は `line` のまま変えていない。
- **既定の `--top-k` / `--max-tokens` は据え置いた**。4 スライスすべてで「1,000 tokens あたりの到達率」が現行既定で最大であり、予算を倍にするより `--return-unit locations` のほうが安く候補を増やせることを実測で確認したため。
- **Skill 定義と配布キットを実装へ同期した**。[.github/skills/markdown-query/SKILL.md](.github/skills/markdown-query/SKILL.md) と `references/cli-reference.md` / `references/indexing-internals.md` / `references/language-and-strategy.md` が「CJK は 1 文字 1 トークン」と記述したままだったため書き換え、`tools/skills/markdown_query/` の vendored コピーへ反映した。

**実測（精度ゲート）**: 開発用 40 問とホールドアウト 20 問について、filtered / broad の 4 スライスすべてで変更前を下回らないことを条件とし、全スライスで PASS した。

| スライス | 変更前 top-1 / top-k / MRR@5 | 変更後 | 差 |
|---|---|---|---|
| dev / filtered | 0.675 / 0.85 / 0.7583 | 0.675 / 0.85 / 0.7583 | ±0 / ±0 / ±0 |
| dev / broad | 0.225 / 0.25 / 0.2313 | 0.225 / 0.35 / 0.2792 | ±0 / +0.10 / +0.048 |
| holdout / filtered | 0.85 / 0.95 / 0.900 | 0.95 / 1.00 / 0.975 | +0.10 / +0.05 / +0.075 |
| holdout / broad | 0.40 / 0.50 / 0.450 | 0.55 / 0.85 / 0.675 | +0.15 / +0.35 / +0.225 |

**実測（コスト）**: 同一プロセス内 A/B（3 回の最小値）で、クエリ毎のコーパス構築が 1,078.3 ms → 1,552.8 ms（**+474.5 ms / クエリ、+44.0%**）。この増分は「毎クエリでコーパスを組み直す」in-memory BM25 経路に固有であり、FTS5 経路には発生しない。比較対象として、同程度の holdout broad 改善を得るために評価した cross-encoder リランカ `bge-reranker-base` は +60,849 ms / クエリを要したため採用していない。変更前と変更後の BM25 順位を RRF で融合する案も実測したが、変更後単独のほうが良かったため採用していない。鮮度検知は索引済み 162 ファイルに対し最小 4.7 ms（内容 SHA-1 は 239.1 ms）、出荷実装経由でも 6.7 ms で、絞り込みありの検索 1 回（546 ms）の 1.2〜1.6% にとどまる。`locations` は `--top-k 20 --max-tokens 800` で平均 6.72〜7.05 件 / 714〜756 tokens、`line` の `--top-k 5 --max-tokens 1600` は平均 4.47〜4.75 件 / 1,234〜1,316 tokens で、到達率は 4 スライスすべてで `locations` が同等以上だった。

**既知の制約**: `--max-tokens` を引き上げない呼び出しでは dev/broad の到達率が 0.35 にとどまる（既定を据え置く判断の代償。`--return-unit locations` または予算引き上げで回避する）。鮮度検知は乖離を報告するだけで**自動再索引はしない**（乖離 8 ファイルの再索引に 33.4 s を要し、検索レイテンシと桁が違うため）。サイズと更新時刻しか見ないため、内容を元へ戻す編集は見逃す。コーパス構築の +474.5 ms に対する事前の合格基準は設けていなかった。

**検証**: RED は `AttributeError: module 'mdq.tokenize' has no attribute 'scoring_terms'` 等で 8 failed、照合側が 5 failed / 2 passed、`ImportError: cannot import name 'freshness' from 'mdq'` による collection error 1 件、`argument --return-unit: invalid choice: 'locations'` で 5 failed / 3 passed を確認した。GREEN は新規 4 ファイルが 33 passed、`pytest mdq/tests` が 245 passed / 3 skipped、`pytest hve/tests/test_mdq_vendor_sync.py hve/tests/test_skill_bundle_sync.py hve/tests/test_markdown_query_kit_contract.py` が 69 passed、`.github/scripts/validate-skill-routing.py` が exit 0。棚卸し索引（[hve-dev/hve-feature-inventory.csv](hve-dev/hve-feature-inventory.csv) 他）を再生成し、FR-MDQ-08/09/10 と新規テスト 4 ファイルの登録を確認した。

### Fixed — markdown-query 配布キットに残っていた git 追跡外の `gui/` 残骸を削除した

`tools/skills/markdown_query/gui/` は生成物としては削除済みだったが、`__pycache__` の `.pyc` だけが git 追跡外で残っており、`hve/tests/test_markdown_query_kit_contract.py::test_kit_no_longer_owns_a_gui_package` が HEAD で失敗し続けていた。CHANGELOG の「GUI のログ取り込みを 1 行あたり 13.7 倍速くした」の検証節でも、本変更と無関係な残存失敗として記録されていたものである。

**検証**: `pytest hve/tests/test_markdown_query_kit_contract.py` を含む配布キット契約テスト 69 passed。

### Changed — GUI のログ取り込みを 1 行あたり 13.7 倍速くした

GUI がオーケストレータの出力を 1 行取り込むたびに、UI スレッド上でファイルの `open` / `close`、非表示ウィジェットへの追記、スクロールバーの再配置を繰り返していた。長時間実行でログが増えるほど UI が重くなる原因になっていたため、表示結果を変えずに処理量を削減した。要件は **NFR-OBS-09** として [hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) §7 に追加した。

- **ローテーションログの永続化でファイルハンドルを保持するようにした**。従来は 1 行ごとに `open` → `write` → `close` を繰り返していた。開いたハンドルを保持して追記し、追記直後に外部から読めるよう 1 行ごとに `flush` する。ローテーション時・永続化無効化時・`WorkbenchPage.cleanup()` 時にハンドルを閉じる（[hve/gui/page_workbench.py](hve/gui/page_workbench.py) の `_LogPane`）。
- **非表示ウィジェットへの二重追記をやめた**。`_LogPane` は `hide()` 済みでファイル永続化専用であり、その `QPlainTextEdit` は画面表示にも `console-log.txt`（`LogTabsWidget` の全文が正本）にも使われていなかった。同じ 1 行を 2 つの `QPlainTextEdit` へ追記していたのを表示側だけにした。あわせて、非表示ウィジェットのスクロールバーを操作していたキーボード操作（`g` / `G` / ↑ / ↓）を表示中のウィジェットへ向け直した（`LogTabsWidget.global_scroll_bar()` を追加）。
- **末尾追従を 1 回へ合体するようにした**。従来は追記のたびにスクロールバーを最大値へ設定していた。保留フラグと単発タイマーで、同一イベントループ内の連続追記に対する末尾追従を 1 回だけ実行する（[hve/gui/widgets/log_tabs.py](hve/gui/widgets/log_tabs.py)）。タイマーはウィジェットの子とし、破棄後に発火して `RuntimeError: libshiboken: Internal C++ object already deleted` になる経路を塞いだ。
- **「実行中の課題」ペインの無変化な再描画をやめた**。500 ms 周期タイマーと 7 種の状態シグナルの双方から、蓄積済みの課題を毎回すべて文字列化して `setPlainText` で全置換していた。生成した表示テキストが前回と同一なら `setPlainText` を実行しない。NFR-OBS-07 による課題の降格はテキストの変化として検出されるため、降格の反映は維持される。

表示行数の上限は設けていない。`setMaximumBlockCount` による上限は実測で 1 行あたり 0.3469 ms → 0.5032 ms と**遅くなり**（ブロック削除のコスト）、かつ `console-log.txt` の全文性を損なうため採用しなかった。

**実測**（同一プロセス内で改善前の処理を再現して比較、N=20,000 行、Windows / offscreen）: 改善前 0.6073 ms/行 → 改善後 0.0442 ms/行（**13.7 倍**）。

**検証**: RED は永続化 3 failed / 末尾追従 1 failed / 非表示ウィジェット 3 failed / 課題ペイン 1 failed を確認。GREEN は `pytest hve/gui/tests/` が 1178 passed / 1 skipped、`hve/tests` のうち GUI を参照する 30 ファイルが 319 passed / 3 skipped。振る舞い変更に伴い [hve/gui/tests/test_autopilot_stats_propagation.py](hve/gui/tests/test_autopilot_stats_propagation.py) の `test_t2_stats_line_not_mirrored_to_log_tabs` を、非表示ウィジェットの内容ではなく永続化ファイルの内容を検証する形へ更新した。残る 2 件の失敗（`test_settings_window_mdq_tabs.py` の access violation クラッシュ、`test_kit_gui_directory_is_removed` が検出する git 追跡外の `tools/skills/markdown_query/gui/__pycache__` 残骸）はいずれも変更対象モジュールに依存しておらず、本変更とは無関係（`tools/` の変更は 0 件）。

### Fixed — code-query 配布キットの任意依存と既知の制約を実装に合わせた

配布キット [tools/skills/code_query/README.md](tools/skills/code_query/README.md) の §6 / §7 が、SQL・shell・PowerShell・batch・Scala を追加した実装に追随していなかった。

- **任意依存を §6.1 解析フィデリティ / §6.2 ツールへ分けた**。tree-sitter の言語別文法 9 種、`sqlglot`、`tree-sitter-sql`、`sqlfluff` が未記載で、これらが `setup` の `--with-gui` / `--with-watch` / `--with-tokenizer` では導入されないことも書かれていなかった。未導入時に該当言語だけが `lite` へ降格する挙動（[cq/indexer.py](cq/indexer.py) が `ExtractionError` / `ImportError` を捕捉する）を明記し、両 OS 分の導入コマンドを載せた。
- **§7 の対応拡張子を実装と一致させた**。`.java` `.go` `.rs` `.c` `.cc` `.cpp` `.cxx` `.hpp` `.hh` `.h` `.cmd` `.bat` `.scala` `.sql` が抜けていた。構造チャンクの説明も「cAST は Python のみ」から、tree-sitter / SQL 系も構造チャンクを持ち行ウィンドウなのは C# / JS / TS だけである実態へ改めた。PL/pgSQL の手続き構文が構造化されないこと、`pwsh` の有無で PowerShell の定義数が変わること、Windows batch に関数の概念が無いことを既知の制約に追加した。
- **`sqlfluff` の依存衝突を実測値で記述した**。`click<8.4.0` を pin するため、`click<9.0.0,>=8.4.2` を要求する `huggingface-hub 1.22.0` と同居すると `pip check` が失敗する。[pyproject.toml](pyproject.toml) のコメントは未検証の版と制約（`>= 1.18` が `click>=8.4.0` を要求）を書いていたため、実測した値へ置き換えた。導入後も `click` / `huggingface_hub` / `fastembed` / `sqlglot` / `sqlfluff` の import と `pytest mdq/tests` は成功しており、宣言上の不整合であって実行時の破綻は観測していない。
- **廃止済みの `tools/skills/code_query/vendor/UPSTREAM.txt` を削除した**。生成コードは `kit_sync` から除去済みだが、`sync_engine` は `vendor/cq` しか置換しないため残骸が消えず、`test_upstream_stamp_is_not_regenerated` が HEAD で失敗し続けていた。`markdown_query` 側には既に存在しない。

**検証**: `pytest hve/tests/test_cq_vendor_sync.py hve/tests/test_mdq_vendor_sync.py` 90 passed、`pytest mdq/tests` 212 passed / 3 skipped。`pytest cq/tests` は 549 passed / 1 failed で、残る 1 件（`test_surface_export.py`）は進行中の [hve/setup-hve.sh](hve/setup-hve.sh) 変更に伴う surface inventory のドリフトであり（差分 33 行すべてが同ファイル由来であることを再生成して確認）、本変更とは無関係。

### Added — GUI のワークフロー選択で必須入力項目を入力・保存できるようになった

Step 1 の左ペインでワークフローを選択したとき、そのワークフローが実行に必要とする必須入力項目の入力欄を、右ペインのワークフロー枠内に表示するようにした。入力した値は CLI 引数（`hve orchestrate` の対応オプション）と GUI 設定ファイル（`hve/.settings.txt` の `[options]`）の両方へ渡り、次回起動時に復元される。要件は **FR-GUI-06** として [hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) §6.4 に追加した。

- **これまで入力欄が出なかった 3 件を表示するようにした**（実測で確認）。ARD Step 1 の `company_name`（対象企業名）は表示対応表に未登録、ADFDV Step 1.1 の `resource_group` は誤ったカテゴリ（`c10`）で登録され解決できず、AAGD Step 1 の `resource_group` は表示対応表に AAGD のエントリ自体が無く枠が生成されていなかった。バナーが「⚠ 未入力」と警告するのに、その項目を入力する欄が画面上に存在しない状態になっていた。
- **必須キーの正本はレジストリ側に一本化**した。表示対象は `REQUIREMENT_TABLE` の `required_info_keys` と `StepDef.required_params` の和集合であり、表示対応表（[hve/gui/page_options.py](hve/gui/page_options.py) の `_STEP2_FIELDS_BY_WORKFLOW`）側で必須性を再定義しない（FR-GUI-02 と一貫）。
- **解決できない表示エントリを除去**した。`('c_azure', 'DataDeploy verify ACI image')` は対応する入力欄が `_CAzure` にも `OrchestrateArgs` にも存在せず、常に解決失敗する死にエントリだった。
- **右ペインの入力を設定ストアへ永続化**するようにした。従来は [hve/gui/page_options.py](hve/gui/page_options.py) に設定保存の呼び出しが 1 つも無く、設定画面から削除済みの C10〜C14 セクションの入力は保存されなかった。起動時の復元経路（[hve/gui/main_window.py](hve/gui/main_window.py) の `_on_settings_changed`）へ C14 を追加し、`[mdq]` / `[cq]` セクションを壊さないことと合わせて回帰テストで固定した。起動時の設定反映でも `textChanged` が発火するため、現在の保存値と同値なら書き込まない。

**既知の制約**: 設定ウィンドウを開いたまま Step 1 右ペインの必須入力を編集し、その後に設定ウィンドウ側で自動保存が走ると、右ペインの編集が設定ウィンドウを開いた時点の値へ巻き戻る（実測）。設定ウィンドウは非表示のたびに再生成されるため通常の開閉フローでは発生しない。変更前は右ペインの入力自体が保存されず、設定ウィンドウを開くだけで値が失われていた。

**検証**: RED は表示 3 failed / 永続化 3 failed を確認。GREEN は [hve/gui/tests/test_workflow_required_input_fields.py](hve/gui/tests/test_workflow_required_input_fields.py) と [hve/gui/tests/test_options_page_required_input_persistence.py](hve/gui/tests/test_options_page_required_input_persistence.py) の 7 passed、影響範囲 44 ファイル 370 passed。`pytest hve/gui/tests/` の全体実行は `test_settings_window_mdq_tabs.py` / `test_qa_ipc_flow.py` で access violation クラッシュするが、`git stash` した baseline でも再現する pre-existing であり、両ファイルは変更対象モジュールを import しない。

### Added — HVE 内部の Repository Query Agentic Retrieval 計測 PoC（公開化は NO-GO）

通常の `mdq search` / `cq search` を置き換えず、複数ソースを横断する質問について検索回数・Token・品質・所要時間を比較する **HVE 内部の明示実行型 measurement PoC** を追加した。公開 CLI、canonical Skill、standalone kit、自動 routing からは起動できず、利用者が [hve-dev/evaluate_repository_query.py](hve-dev/evaluate_repository_query.py) を network opt-in 付きで明示実行した場合だけ、private Python API [hve/repository_query.py](hve/repository_query.py) を呼び出す。

- **安全境界**: Model に公開するのは `search_markdown` / `search_code` / `open_evidence` / `find_code_references` の read-only custom tool 4 個だけ。任意ファイル read、write、shell、web、MCP、memory、git、builtin tool を遮断し、query-scoped Evidence Ledger と host-side Grounding JSON 検証で未知 ID・捏造 path・不正 JSON を fail-closed にする。上限は custom tool calls 6、1 search call の subquery 3、1 subquery の hit 3 / 800 tokens。LLM calls は 10 を超える usage の観測時に abort するため、SDK から既に配送された usage の actual は 10 を超えて記録され得る。fixed model / reasoning effort / timeout / AI credit cap を必須化した。
- **比較器**: 12 問の composite golden を、A（local deterministic）、C（A と同じ固定 evidence の one-shot compression）、D（bounded Agentic）の 3 条件で query ごとに比較する。設計・開発・保守・障害対応、cross-source / multi-document / unanswerable を含み、required-evidence recall、citation validity、abstention、検索・LLM・tool call、Token、所要時間、error / cap を失敗 run も分母に残して集計する。LLM judge、自動 Go/No-Go、未承認の数値 threshold は追加していない。
- **トレーサビリティ**: FR-RQ-01〜04 / NFR-RQ-01、Golden、runtime / tool / evaluator の契約テストを追加した。既存 `mdq` / `cq` API を委譲利用し、新規依存は追加していない。

#### 実測（12 queries × 3 arms = 36 runs）

固定条件は `gpt-5.6-sol`、reasoning effort `high`、timeout 120 秒、最大 30 AI credits / network session、GitHub Copilot SDK 1.0.6 / CLI 1.0.77。Arm A は LLM を使わない。

| Arm | Errors / runs | Cap aborts | Required evidence recall | Citation validity | Internal searches | Input / output tokens | Duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| A deterministic | 0 / 12 | 0 | 0.0455 | 1.0000 | 24 | 0 / 0 | 18,024 ms |
| C one-shot | 6 / 12 | 0 | 0.0455 | 0.6250 | 24 | 10,029 / 2,875 | 135,613 ms |
| D bounded Agentic | 7 / 12 | 4 | 0.2273 | 0.5000 | 166 | 739,893 / 15,603 | 497,191 ms |

Cap aborts は Errors の内数であり、両者を加算しない。

- **検索回数と Token は減らなかった**。A と C の internal searches は同じ 24 回で、C は recall を改善せず LLM Token・error・latency を追加した。D は recall と unanswerable abstention に改善 signal を示した一方、検索量、Token、latency、error / cap が増え、citation validity が低下した。
- **SDLC 全体での有効性は未証明**。D は設計・開発で限定的な recall signal を示したが error が残り、保守は 3 / 3 runs が error。障害対応は static repository evidence の小標本で live telemetry を評価していないため、成功した abstention を運用全体へ一般化しない。
- **判断**: deterministic A は維持。現形 C/D と public CLI / Skill / standalone / Auto routing は **NO-GO** とし、公開実装を開始しない。HVE 内部の再実験も、品質・failure・cost・latency threshold、診断方法、複数 repeat、実運用 workflow baseline を別途承認した場合だけ Conditional GO とする。

**既知の制約**: repeat は 1。C の duration は frozen A evidence の準備を含まない。実運用 Agent の複数 call 削減と caller-visible context token は未測定。error 詳細は安全のため保存しておらず validation rule 別の原因は不明。単一 model・dirty workspace の結果で、計測対象 6 ソースと Golden の SHA-256 は記録したが、委譲先 mdq/cq を含む clean commit baseline ではない。他モデルや production effectiveness へ一般化しない。

### Added — `code-query` が SQL / Spark 系 ETL / OS シェルを高フィデリティで索引するようになった

`cq` の対応言語に **shell（bash）/ PowerShell / Windows batch / Scala / SQL** を追加した。解析エンジンは自作せず、商用利用可能な OSS から選定している。
- **拡張子の追加**: `.cmd` / `.bat` / `.scala` / `.sql`。`.cmd` はこれまでまったく索引対象外だった。
- **任意依存の追加**: `tree-sitter-bash` / `-powershell` / `-batch` / `-scala` と `sqlglot` を `code` extra へ、`sqlfluff` を新設の **`code-sql` extra** へ。文法はすべて wheel 同梱で実行時ダウンロードしない。
- **SQL は方言対応パーサの 2 段構え**: `sqlglot` を主とし、T-SQL / Oracle / PostgreSQL / BigQuery / Spark を固定順で試して全文を構造化できた最初の方言を採用する（順序が固定なので結果は決定的）。`GO` は T-SQL のバッチ区切りとして扱う。**ルーチン本体を構造化できなかったときだけ** `sqlfluff` へエスカレーションする。これにより Oracle PL/SQL の本体参照が `()` → `royalty_rate` / `sales` に、BigQuery のスクリプトプロシージャが `ExtractionError` → シンボル + 参照を取得できるようになった。非エスカレーション時の解析コストは中央値 0.5〜1.1 ms を維持している。
- **PostgreSQL の `$tag$ ... $tag$` 本体を再パース**: PL/pgSQL 本体は sqlglot / sqlfluff のどちらも 1 トークンとして扱う。`tree-sitter-sql`（MIT）で本体だけを再パースし、`SELECT` / `INSERT` / `UPDATE` / `DELETE` のテーブル参照をファイル行番号付きで拾う。関数名・別名・列修飾子は除外する。
- **PowerShell は回復ノードが残ったファイルだけ `pwsh` 公式パーサへエスカレーション**: `Parser.ParseInput` を stdin 経由で呼び、定義と呼び出しを JSON で受け取る（スクリプトは実行しない）。実コーパス 27 件中 5 件がエスカレーションし、**文法の偽陽性による取りこぼしが 2 件 → 0 件**になった。
- **`Grammar` へフックを 2 つ追加**: `callee_of`（PowerShell の `command` と batch の `cmd` が `function` / `name` フィールドを持たないため）と `signature_of`（PowerShell の宣言ノードが `body` フィールドを持たず、シグネチャに本体が丸ごと入ってしまうため）。既存 5 言語の振る舞いは不変。
- **`.scala` / `.sql` はリポジトリに実ファイルが 0 件**のため、`build_index` 経路を temp corpus の統合テスト（`TestNewLanguageIndexIntegration`）で押さえた。

`sqlfluff` を `code` から分離したのは、`click<8.4.0` の pin が既定 extras の `semantic`（fastembed → huggingface-hub は `click>=8.4.0`）と衝突し **`pip check` が exit 1 になることを実測した**ため。`.[code]` 単独なら `pip check` は通る。

### Changed — shell / PowerShell が `lite` から昇格し、索引に `lite` ファイルが無くなった

`cq/languages/__init__.py` の `LITE_ONLY` は空集合になったため削除した（未登録言語の `lite` 降格機構自体は不変）。両 profile を再構築した結果は次のとおり。

| 指標 | profile=hve | profile=app |
|---|---:|---:|
| `lite` フィデリティのファイル | 64 → **0** | 4 → **0** |
| refs | 70,461 → **77,263** | 5,811 → **6,090** |
| symbols | 13,523 → 14,178 | 1,404 → **1,404** |

**`profile=app` の symbols は 1 件も増えていない。** 実コーパスの `.sh` 45 件で lite と tree-sitter の抽出シンボル名集合が完全に一致したためで、昇格の利得は定義数ではなく **終了行（複数行の行範囲を持つ定義 0 → 158）・doc（0 → 76）・参照（0 → 3,130）・構造チャンク** に現れる。PowerShell は公式パーサへのエスカレーションにより実コーパスで lite と同数の 66 定義を取得し（取りこぼし 0 件）、加えて ERROR ノード周辺で tree-sitter が 314 行離れたコメントを doc として誤付与していた 2 件も修正された。

検索品質は `code-query` ゴールデンが hve / app とも **top-1 0.9524 / top-k 0.9524** で記録値と一致し、`markdown-query` の FR-MDQ-01 は inventory 再生成の前後どちらも **top-1 0.675 / top-k 0.85** で不変だった（FR-CQ-12 の非退行条件）。

**既知の制約**:

- **PL/pgSQL の手続き構文自体（`IF` / `LOOP` / `PERFORM`）は依然として構造化されない。** 本体の再パースで取れるのは埋め込まれた SQL 文のテーブル参照まで。
- **`pwsh` が無い環境では PowerShell のエスカレーションが起きないため、同じファイルでも環境によって定義数が変わる。** `parser` 値はどちらの経路でも `tree-sitter` のままで、エスカレーションの有無は区別されない。
- **Windows batch 文法に関数の概念は無く**、取れるのはラベル定義と `call` / コマンドの参照だけ。実コーパス 7 件はラベルを持たないため symbols 0 / refs 26。

### Added — `markdown-query` の検索品質を測るための評価基盤（MRR@5 / 絞り込みなし条件 / ホールドアウト集合）

直近 30 日の Copilot 利用履歴（CLI ローカル 343 セッション / 1,591 ターン、VS Code 側 52 セッション行のうち本文を伴うもの 8 件）と `mdq` の利用ログ 862 レコード（うち検索 693 件）を分析したところ、**「検索が効いているか」を判定する仕組みそのものが不足していた**ことが分かった。既存のゴールデン評価は 20 問・Top-1/Top-k のみで、しかも全問がゴールデン側の対象パス絞り込み付きで実行されていた。実運用でパス絞り込みが使われるのは **43.4%** に過ぎず、残る 56.6% の呼び出しに相当する「対象パス絞り込みなし」の条件は一度も測られていなかった。既定値のチューニングを始める前に、この測定基盤を先に用意した。

要求定義へ **FR-MDQ-04（順位品質指標と 2 条件計測、ホールドアウト必須）** を新設し（[hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) §3.8）、以下を実装した。

- **MRR@k の追加**: [mdq/golden_eval.py](mdq/golden_eval.py) の `aggregate()` が `mrr_at_k` を返す。ヒット行に `rank` が欠けている場合は **`None` を返して算出しない**（Top-k と矛盾する値を作らないための fail-closed）。[tools/skills/markdown_query/benchmark.py](tools/skills/markdown_query/benchmark.py) のレポートにも `MRR@k` 列を追加した。
- **絞り込みなし（broad）条件の追加**: `run_search_scenario(..., ignore_golden_paths=True)` と CLI の `--ignore-golden-paths` を追加し、ゴールデン各問の `paths` を無視してリポジトリ全体を検索する条件を計測できるようにした。既定（filtered）の挙動は変えていない。
- **評価セットの拡張とホールドアウトの新設**: [mdq/golden-queries.json](mdq/golden-queries.json) を 20 → **40 問**へ拡張し、既定値の決定に一切使わない [mdq/golden-queries-holdout.json](mdq/golden-queries-holdout.json)（**20 問**）を新設した。ID・クエリ・期待着地点のいずれも開発用と重複しない。全 anchor は対象ファイル内で一意であることと、`code-query` 導入（2026-07-29）より前から存在する記述であることを確認済み。
- **配布キットへの非同梱**: ゴールデンは評価用データであり配布物ではないため、[tools/skills/_kit/kit_sync.py](tools/skills/_kit/kit_sync.py) の除外規則へ `golden-queries-holdout.json` を追加した（既存の `golden-queries.json` と同じ扱い）。

### Changed — 実測に基づいて `mdq` の順位付け既定値と索引範囲を変更

上記の基盤で測ったところ、**当初の見立てだったチャンク分割やカバレッジは問題ではなかった**（ゴールデン 20 問の期待着地点はいずれもちょうど 1 チャンクで覆われていた）。実際のボトルネックは順位付けだったため、スコープを絞って以下だけを変更した。

- **見出しパスをスコアリング対象へ含める（FR-MDQ-05）**: [mdq/search.py](mdq/search.py) の BM25 コーパスを `heading_path + 本文` から構築する。見出しにしか現れない語で本文チャンクへ到達できるようになる。**抜粋・行範囲へは一切混入させない**（返却される内容は従来どおり本文のみ）。`grep` モードと FTS5 経路は対象外。
- **文書長正規化係数の明示と変更（FR-MDQ-06）**: 暗黙の既定 `b=0.75` を `LENGTH_NORM_B` として定数化し、**`0.2` へ変更**した。`rank_bm25` の有無で切り替わる 2 実装（`BM25Okapi` / 内蔵 `_MiniBM25`）の**双方へ同じ定数を渡す**ため、経路によって順位が変わらない。値は 4 水準（0.75 / 0.4 / 0.2 / 0.0）× 4 スライス × 3 指標の全数計測で決定した。**b=0.2 は全 12 値で変更前（0.75）を下回らず、かつ broad の伸びが最大**。b=0.0 は dev broad の MRR こそ最良だが holdout filtered が 0.8625 → 0.8375 と変更前を割り込むため却下、b=0.4 は全スライスで改善するものの broad の伸びが小さく次点とした。
- **索引ルートから `work/` を除外**: [mdq.toml](mdq.toml) の `[index].roots` を 10 → 9 へ。作業成果物が正本文書と競合して broad 検索の上位を占めるのに加え、**過去 run のレポートがゴールデンのクエリ文字列と期待パスを含むため、評価そのものが無効化される**問題があった。
- Skill 文書（[.github/skills/markdown-query/SKILL.md](.github/skills/markdown-query/SKILL.md) ほか）を実装へ同期した。

#### 効果（同一索引・同一クエリ集・同一予算で、順位付け変更のみを切り替えた A/B）

| スライス | 変更前 Top-1 | 変更後 Top-1 | 変更前 MRR@5 | 変更後 MRR@5 | MRR 改善 |
|---|---:|---:|---:|---:|---:|
| dev filtered（40 問） | 0.550 | 0.675 | 0.6396 | 0.7583 | +18.6% |
| dev broad（40 問） | 0.075 | 0.225 | 0.1208 | 0.2313 | +91.5% |
| holdout filtered（20 問） | 0.600 | 0.850 | 0.7333 | 0.9000 | +22.7% |
| holdout broad（20 問） | 0.200 | 0.400 | 0.2750 | 0.4500 | +63.6% |

**4 スライスすべてで改善し、劣化したスライスは無い。** さらに既定値の決定に使っていないホールドアウトの改善幅が開発用集合以上であり、開発用集合への過学習ではないことを確認した。

コーパスは 18,801 → **15,305 chunk（-18.6%）**。パス絞り込みありの結果は完全に同一（絞り込みはスコアリング前に適用されるため）で、broad だけがわずかに改善した。`code-query` のゴールデン（profile=hve、21 問）は **0.9524 で変化なし**（FR-CQ-12 の非退行条件）。

**既知の制約**: `[index].roots` からルートを外しても、**既存索引から当該チャンクは自動的に消えない**。prune は「ディスク上に存在しないファイル」だけを削除するため、ファイルが残っていれば索引に残り続ける（`mdq index --rebuild` でも消えなかった）。ルート構成を変えたときは索引 DB を削除してから再構築すること。

### Fixed — `--max-tokens` の宣言値と実応答が 71% 乖離していた欠陥と、利用統計レポートが常に 0 件だった欠陥

**応答トークン予算（FR-MDQ-07）**: [mdq/search.py](mdq/search.py) の予算判定は「抜粋の文字数 ÷ 4」で行われていた。実際に返却されるのは `path` / `heading_path` / `start_line` / `score` 等を含む JSON であり、**メタデータ分が丸ごと勘定から抜けていた**うえに、日本語文書では「文字数 ÷ 4」が実トークン数を大きく下回る。結果として、`--max-tokens 800` を指定した検索の **90%（旧ゴールデン 20 問中 18 問）が予算を超過**し、実応答の平均は 1,368.6 トークン（最大 1,957）に達していた。返却する 1 ヒット 1 行 JSON を `tiktoken` で実測する方式へ変更した。

- 計測器は [mdq/tokens.py](mdq/tokens.py) を新設し、`cq/tokens.py` と同じ実装（`tiktoken/cl100k_base`、未導入時は `chars/4-approx` へフォールバック）を持たせた。`cq` から import すると `markdown-query` 配布キットが `cq` の同梱を強いられ FR-KIT-04（キット単体で成立）を破るため、**2 つの独立配布物であることを理由に重複を意図的に許容**している。`tiktoken` の import は遅延させ、検索経路の起動コストを増やしていない。
- 少なくとも 1 件は必ず返す（先頭ヒットは予算超過でも落とさない）挙動は維持している。

| 指標 | 是正前 | 是正後 |
|---|---:|---:|
| `--max-tokens 800` の超過率 | 90% | **0%** |
| 実応答トークン最大 | 1,957 | 790 |
| 実応答トークン平均 | 1,368.6 | 621.0 |

是正後の平均返却件数は 2.23 件（dev filtered / `--max-tokens 800`）。是正前に `800` 指定で実際に消費していた量（平均 1,368.6 トークン）は、是正後に `--max-tokens 1600` を指定したときの実コスト（平均 1,313〜1,368 トークン、平均 4.5〜4.6 件）とほぼ一致する。つまりこの是正は精度を落としたのではなく、**それまで無自覚に超過していたコストを可視化した**ものである。

**既定 `max_tokens` は 800 のまま変更しない。** 1600 へ引き上げれば宣言と実態は一致するが、それは「既定で消費するコンテキスト量」を追認することになる。実運用ログでは **69.7% の呼び出しが既に 800 超（平均 1,703）を明示指定**しており既定値の影響は限定的なため、代わりに「同じ予算で得られる件数の目安」（日本語文書では 800 トークンで 2〜3 件、5 件必要なら 1,600 前後）と「件数が足りないときは `--top-k` ではなく `--max-tokens` を上げる」ことを Skill 文書へ明記した。

**`cq` ベンチマークのトークン会計**: [cq/benchmark.py](cq/benchmark.py) の応答コストも実際の JSONL ではなく抜粋文字列から概算していたため、同じ方式（1 ヒット 1 行 JSON の直列化結果を計測）へ揃えた。`cq` の検索実装自体は変更していない。

**利用統計レポートが常に 0 件だった欠陥**: [tools/skills/markdown_query/generate_usage_report.py](tools/skills/markdown_query/generate_usage_report.py) は vendor を `sys.path` の先頭へ置くため、vendored 側の repo-root 既定解決が `tools/skills/markdown_query/vendor` を指し、**対象リポジトリの `.mdq/usage.jsonl` を一度も読めていなかった**（実測: 生成済み `latest.json` が record_count=0 / files=0、一方リポジトリルートで直接集計すると 862 records / 521 files）。ラッパー側に `default_repo_root()` を実装し、`mdq.toml` または `.mdq` の存在で検証したうえで `--repo-root` 未指定時に注入する。

### Changed — `markdown-query` / `code-query` を「ソース 1 か所・画面 1 か所・コピーで使える」構成へ統一

2 つの Skill は方向の異なる構成を持っていた。`cq` はエンジンと GUI を `cq/` に置く一方で配布 vendor が `.gitignore` されており（実測: `python tools/skills/code_query/launch.py --version` が **exit 2**）、`mdq` は vendor をコミットしている一方で GUI の実体が配布キット側にあり、HVE の GUI がキットを import する**逆方向依存**になっていた。両者の正しい側へ統一した。

要求定義へ **§3.10「Skill 配布キットの可搬性」（FR-KIT-01〜05）** と **FR-GUI-05** を新設し（[hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) v1.9）、以下を実装した。

- **画面の単一実装化（FR-GUI-05）**: `tools/skills/markdown_query/gui/` を [mdq/gui/](mdq/gui/) へ移設し、`cq/gui/` と同じ位置づけに揃えた。並存していた索引操作サービス 2 実装（`git diff --no-index` で **157 行差**。`get_index_stats_all_strategies` は HVE 側のみ、`pageindex_options` は独立版のみという機能ドリフト）を [mdq/gui/index_service.py](mdq/gui/index_service.py) へ統合。`hve/gui/mdq_index_service.py` は再エクスポートだけに縮退し、[hve/gui/mdq_settings_section.py](hve/gui/mdq_settings_section.py) が HVE の設定ストアを注入する。実行時に上流の有無を判定していた `_try_hve_settings_store()` は `SettingsBackend` Protocol の注入へ置換した。
- **配布エンジンの同梱と一致検証（FR-KIT-01）**: `tools/skills/code_query/vendor/cq/` を `.gitignore` から外してコミットし、[hve/tests/test_cq_vendor_sync.py](hve/tests/test_cq_vendor_sync.py) で byte 一致・非 ignore・追跡済みを検証する（`mdq` 方式へ統一）。毎回差分を生む `vendor/UPSTREAM.txt` は廃止。除外規則は任意階層の `tests` へ拡張した。
- **Skill 定義の単一正本化（FR-KIT-02）**: `tools/skills/code_query/skill-template/`（正本と **104 行相当の差**があった）を削除し、`.github/skills/<name>/` を正本として各キットの `skill/` を生成する。リポジトリ固有の profile 名・実測値・具体例は `references/repo-specific/` へ隔離し、配布物には同梱しない。[hve/tests/test_skill_bundle_sync.py](hve/tests/test_skill_bundle_sync.py) が一致を検証する。
- **セットアップ・同期の単一実装化（FR-KIT-03）**: 判断ロジックを [tools/skills/_kit/](tools/skills/_kit/)（`kit_setup.py` / `kit_sync.py`）へ集約し、キット固有の値は `kit.toml` で宣言する。`setup.{ps1,sh}` / `sync-vendor.{ps1,sh}` は委譲だけの薄いブートストラップになり、**引数は全 OS 共通**（`--repo-root` / `--with-gui` / `--install-skill` 等）になった。
- **コピー可搬性の機械検証（FR-KIT-04）**: [hve/tests/test_portable_kit_e2e.py](hve/tests/test_portable_kit_e2e.py) が**版管理下の実配布物**を一時 git リポジトリへコピーし、上流を import 経路から外した subprocess でセットアップ・設定生成・Skill 配置・索引・検索・GUI 起動導線を検証する。正本から検証時に複製した一時ツリーでは同期漏れを検出できないため代替しない。
- **上流依存の除去（FR-KIT-05）**: `mdq/usage_stats.py` の `from hve import run_journal`（無条件）と `from hve.gui import mdq_index_service`（遅延）を除去。利用ログの読み取りを書き込み側と同じ [mdq/usage_log.py](mdq/usage_log.py) の `read_records()` へ単一化し、`hve.run_journal` は委譲に変更した。実測: `mdq.usage_stats.aggregate_usage_stats()` 実行後の `sys.modules` 内 `hve*` が **21 → 0**。
- **`markdown-query` キットの機能整備**: CLI ランチャ `mdq.{ps1,sh,cmd}`、設定生成 `init_config.py`、Skill 配置（`--install-skill`）を追加し、`code-query` キットと同等にした。GUI ランチャは vendored `mdq.gui` 経由へ切り替え、`pyproject.toml` の配布対象を `vendor` 側へ変更した。
- **`cq` の profile 既定値**: 上流固有の `hve` が固定既定だったため、コピー先ではセットアップ成功直後の `python -m cq search` が失敗していた。`CQ_PROFILE` から解決する `default_profile()` を追加した（[cq/cli.py](cq/cli.py)）。
- **利用統計レポートの出力先**: `tools/skills/markdown_query/usage-report/` から対象リポジトリ配下の `.mdq/usage-report/` へ変更した。配布キットを任意のリポジトリへコピーしても無関係な階層を作らないため。生成処理は [mdq/usage_report.py](mdq/usage_report.py) へ移設し、キット側にはドキュメント済み CLI を維持する薄い wrapper を残した。

### Fixed — 日本語の文分割が全く行われず、範囲外オフセットを返していた

`semantic_paragraph` チャンキングが使う [mdq/sentence_splitter.py](mdq/sentence_splitter.py) は、日本語テキストを **1 文も分割していなかった**。

- **原因**: JA 終止符（`。` `！` `？` `．`）の直後へ `\n` を挿入して「Punkt に英語的な境界を見せる」設計だったが、**Punkt は改行を文境界として扱わない**。実測: `sent_tokenize("これは日本語です。\n次の文があります。\n最後の文！")` は 1 要素を返す。モジュール docstring のこの前提が事実と異なっていた。
- **二次被害**: 挿入した `\n` が戻り値に残るため、`split_with_offsets()` が**入力に存在しない文字列**と**範囲外のオフセット**を返していた。実測: 23 文字の入力に対し `(0, 25, ...)`。docstring の「Offsets are character positions into *text*」という契約に反する。
- **修正**: 文字を挿入せず、JA 終止符の直後を**ゼロ幅で切って**から各断片へ Punkt を適用する。JA 終止符を含まないテキストは従来どおり丸ごと Punkt へ渡るため、**英語の複数行にまたがる文は分割されない**（非退行を実測確認: `"This is a\nlong sentence that wraps. And another one here."` → 2 文のまま）。
- 修正後は `text[start:end] == sentence` が全ての戻り値で成立する。

あわせて `test_mixed_block_with_fence_and_prose` を是正した。`Prose A.` のような**単一大文字＋ピリオドを Punkt は略語/イニシャルとして扱い分割しない**（実測: `sent_tokenize("Prose A. Prose B.")` → 1 要素。`"Prose alpha. Prose beta."` → 2 要素）。このテストが見たいのはフェンスの原子性と前後の散文が分割されることなので、その判定に干渉しない語へ差し替えた。アサーションは弱めていない。

### Fixed — mdq の日本語 FTS5 検索が常に 0 件だった欠陥と、索引の 18 倍肥大

`mdq` の FTS5 経路は、**日本語クエリに対して常に 0 件**を返していた。`ja-jp` 索引の `chunks_fts` は `trigram` トークナイザ（3 文字未満を索引しない）で作られる一方、[mdq/search.py](mdq/search.py) の `_TOKEN_RE` は CJK を 1 文字へ分解し、その 1 文字トークンをそのまま `MATCH` 式に並べていたため、構造的に一致し得なかった。英語クエリは動作していたため顕在化していなかった。

- **実測による確定**: trigram 索引への直接プローブで `検`=0 件 / `検証`=0 件 / `検証マ`=20 件 / `検証マーカー`=17 件。同一クエリ `検証マーカー 書式` で既定経路（in-memory BM25）は 3 件ヒットするのに対し、`MDQ_FTS5=1` は 0 件だった。
- **[.github/skills/markdown-query/references/language-and-strategy.md](.github/skills/markdown-query/references/language-and-strategy.md) の記載が事実と逆だった**: 「FTS5 利用時は `ja-jp` で `trigram` が選択され、日本語の部分一致検索が安定する」。実装へ同期した。
- **修正方式**: `chunks_fts`（trigram のみ）を `detail=none` で作り直したうえで、クエリの各セグメントをトリグラムへ分解して AND 結合し、同一 SQL 内の `LIKE` で確定照合する。`bm25()` によるランキングは維持する。トリグラム AND だけでは 4 つのトリグラムを非連続に含む文書が偽陽性として残ることを実測で確認済み。
- **3 文字未満のクエリ**は trigram 索引で表現できないため、0 件を返さず in-memory BM25 へフォールバックする。長短のセグメントが混在する場合は短い方が条件から落ちる（`検証 マーカー書式` → `マーカー書式` だけが条件）。またセグメントは連続一致を要求するため、BM25 経路より precision は高く recall は低い。いずれも Skill ドキュメントへ明記した。
- **確定照合の `LIKE` で `%` / `_` をエスケープする**。未エスケープだと `_` が任意 1 文字にマッチするため、本来除外すべき偽陽性が通ってしまう。実証: 文書 `ab_ b_d _de and abXde` はクエリ `ab_de` を literal に含まないにもかかわらずヒットしていた。回帰テストを追加して固定している。
- **`en-us`（unicode61）は変更していない**。肥大の実測値を持たない対象へ最適化を広げるのは根拠がないため、`detail=none` も新しいクエリ構築も `trigram` のときだけ適用する。
- **`_migrate()` がスキーマ差を見逃す欠陥も併せて是正**: 再作成の判定がトークナイザ名だけの比較だったため、`detail` を変えても既存 DB が無言で古いまま残る状態だった。仮想表の引数列全体の比較へ変更し、`SCHEMA_VERSION` を 6 → 7 へ引き上げた。バージョン差に救われず欠陥が露見するよう、`user_version` を据え置いたケースの回帰テストも追加した。
- **`cq/golden-queries.json` の anchor 追随**: `SCHEMA_VERSION` の引き上げで anchor `"SCHEMA_VERSION = 6"` が `mdq/store.py` に存在しなくなり、FR-CQ-02 の fail-closed 判定が発動して cq 側 4 件が失敗した。`profile=hve` の索引ルートに `mdq/` が含まれるため、mdq 側の変更が cq のゴールデン集合を壊し得る。anchor を更新して解消（fail-closed 機構が意図どおり働いた例であり、抑止すべき挙動ではない）。

#### 効果（実索引・18,080 chunk / 513 ファイル）

| 指標 | 変更前 | 変更後 |
|---|---:|---:|
| FTS5 データ領域（`chunks_fts_data`） | 139.6 MB | **8.7 MB**（−93.8%） |
| 索引ファイル | 164.9 MB | **30.2 MB** |
| 日本語検索 `検証マーカー`（FTS5） | **0 件** | 5 件 / 11.2 ms |
| 日本語検索 `検証マーカー 書式`（FTS5） | **0 件** | 5 件 / 14.0 ms |
| 2 文字クエリ `検証` | 0 件 | 5 件 / 1,500 ms（BM25 へフォールバック） |
| v6 → v7 マイグレーション所要 | — | 1.3 秒 |

> 測定条件の注記: FTS5 データ領域の行はどちらも `sum(length(block))` で同条件。索引ファイルの行は **変更前は既存ファイルの実サイズ、変更後は `VACUUM` 後の値**であり同条件ではない。マイグレーション直後は解放ページが残るため 164.9 MB のままである。新規に構築した索引は最初から小さい。

2 文字クエリは 0 件回避と引き換えに in-memory BM25 のレイテンシ（約 1.5 秒）を拈う。高速な応答が必要な場合は 3 文字以上の語を使う。

**既知の制約**: マイグレーションは `VACUUM` を行わないため、既存の `.mdq/*.sqlite` はファイルサイズが縮まない（解放ページは以後の索引成長で再利用される）。新規構築される索引は最初から小さい。縮めたい場合は `mdq index --rebuild` か `VACUUM` を 1 度実行する。`open_store()` は毎回走るため、所要時間の読めない `VACUUM` を暗黙に混ぜない判断とした。

### Added — mdq / cq の検索応答に返却単位の選択を追加（FR-MDQ-03 新設 / FR-CQ-06 改訂）

両 Skill は意味的にまとまったチャンク（mdq=見出しセクション、cq=cAST の構造ノード）を構築しながら、応答ではヒット行の **±2 行**しか返していなかった。「関数の単位など、意味のある単位で本文が欲しい」という用途では毎回 `get` の追加呼び出しが必要だった。

- `search` に `--return-unit {line,chunk}` を追加した。**既定は `line` で従来どおり**。`chunk` はヒットを含むチャンクの本文全体を切り詰めずに返す。
- 既定を変えなかったのは、`chunk` を既定にすると全 Agent 呼び出しのトークン消費が増え、Skill の主目的（Context Window 最小化）と C3 指標（`1 - Σsnippet_chars/Σsource_file_chars`）を悪化させるため。
- 単位を変えても **strategy 選定・検索層の選択・ヒット対象・順位は変わらない**。抜粋が長い分だけ同じ `--max-tokens` で返る件数が減るのは予算規則の帰結であり、テストで単調性（`len(chunk) <= len(line)`）として固定した（実測: 行単位 2 件 / チャンク単位 1 件）。
- cq 側は経路判定と順位付けが終わったあとに本文を差し替える実装にした。単位が検索層の選択へ影響し得ない構造にするためで、トークン予算の算定は差し替え後の本文に対して行う。このとき **`lines` もチャンクの行範囲へ広げる**。regex / trace 経路はマッチ行だけを `lines` に入れるため、本文だけを広げると `lines=[17,17]` に対し抜粋 33 行という矛盾が生じ、FR-CQ-06 の「パス、行範囲、スコア、抜粋」に反する。回帰テストを追加して固定している。
- mdq と cq で実装を共有していない。`FR-CQ-01` が両エンジンの索引 DB の物理分離を要求しており、`mdq` は `tools/skills/markdown_query/vendor/mdq/` へ byte 一致で複製されて他リポジトリへ配布されるため、`cq` を import すると配布が破綻する（FR-MAINT-07 の面横断確認の結果として記録）。

#### 検証

<!-- validation-confirmed -->

- `pytest mdq/tests cq/tests hve/tests/test_mdq.py hve/tests/test_mdq_vendor_sync.py hve/tests/test_hve_requirement_traceability_contract.py hve/tests/test_code_query_skill_wiring.py` **733 passed / 0 failed / 3 skipped**。着手時に pre-existing だった `mdq/tests/test_sentence_splitter.py` の 2 件も、本変更セット内で根本原因を特定して解消した。
- 新規テスト: [mdq/tests/test_search_fts5_japanese.py](mdq/tests/test_search_fts5_japanese.py)（8 件、うち LIKE メタ文字 2 件）、[mdq/tests/test_search_return_unit.py](mdq/tests/test_search_return_unit.py)（7 件）、[cq/tests/test_search_return_unit.py](cq/tests/test_search_return_unit.py)（9 件、うち `lines` 整合 2 件）、[mdq/tests/test_store_migration.py](mdq/tests/test_store_migration.py) に 4 件追加。すべて RED を確認してから実装した。
- **FR-MDQ-01 非退行**: 計測条件を揃えるため `git worktree add --detach <tmp> HEAD` の独立ツリーでベースラインを取り、両方とも索引を完全再構築して同一 `--db` を明示した。
  - ベースラインコード + ベースライン文書: top-1 **0.45** / top-k **0.75**
  - **候補コード + ベースライン文書: top-1 0.45 / top-k 0.75** → 検索実装の変更は正解率に影響しない
  - 候補コード + 候補文書: top-1 **0.40** / top-k **0.75**。差分は REQ-01 の 1 問のみで、原因は本変更で `FR-MDQ-03` を §3.8 へ追記してチャンクが伸び、BM25 の文書長正規化で隣の §3.9 に 1 位を譲ったこと（§3.8 の score 15.89 → 13.74）。期待着地点は引き続き top-5 内にある。コーパスの変化であり検索実装の退行ではないため、**ゴールデンクエリ集は変更していない**。
- **FR-CQ-02 非退行**: `profile=hve` でベースライン（HEAD worktree）top-1 **0.9524** / top-k **0.9524** / 平均トークン **97.5** に対し、候補も **0.9524 / 0.9524 / 97.5** で完全に一致。`profile=app` も top-1 / top-k **0.9524**。
- 配布 vendor を `sync-vendor.ps1` で再生成し、`hve/tests/test_mdq_vendor_sync.py` **42 passed** を確認。`vendor/mdq/{cli,search,store}.py` が上流と byte 一致することを個別にも検証した。
- ドキュメントに追記したコマンド（`mdq search --return-unit chunk` / `cq search --return-unit chunk`）は実際に実行して出力を確認した。`.github/scripts/validate-skill-routing.py` exit 0。
- 調査レポートの誤り 2 件を訂正した。`golden_eval` は top-1 だけでなく top-k も計測しており「top-1 のみ」は誤り。`cq/repomap.py` は "Aider's repo map idea" としか述べておらず PageRank 準拠は主張していないため、当該指摘は撤回した。存在しない問題を欠陥として残さないための訂正である。

#### 申し送り

本変更中、別タスク `skill-kit-single-source` が `mdq/gui/**` を実時間で編集していた（`git status` の `AM` とファイル更新時刻で確認）。配布 vendor と棚卸し索引はリポジトリ全体のスナップショットであるため、当該タスクの完了時に `tools/skills/markdown_query/sync-vendor.ps1` と `hve-dev/generate_tdd_inventory.py` の再実行が必要になる。編集途中の状態を vendor へ焼き付けないよう、レース中の再同期は繰り返さず、編集が 8 分停止したことを確認してから最終同期した。

### Fixed — cq 5 言語対応の未検証・未同期の残作業

Java / Go / Rust / C / C++ の tree-sitter 対応は実装済みだったが、**一度も実行されていない**状態だった。実装本体は変更していない（C# の 1 箇所を除く）。

- **任意依存が未導入で言語契約テストが全 skip だった**: [cq/tests/test_treesitter_languages.py](cq/tests/test_treesitter_languages.py) は `pytest.importorskip("tree_sitter")` でモジュールごと skip されており、5 言語の受入条件は一度も評価されていなかった。`pip install -e ".[code]"` で 66 件が GREEN になることを確認した。
- **CI が `cq/tests` を実行していなかった**: [.github/workflows/test-hve-python.yml](.github/workflows/test-hve-python.yml) は `hve/tests/` しか流さず、path filter にも `cq/**` が無かった。`cq-python-tests` job（ubuntu / `[code]` extra）を追加し、文法 import を fail-closed で検証してから `cq/tests` を実行する。silent skip の再発を防ぐと同時に、Linux での wheel install 実行検証も兼ねる。
- **索引パイプライン全体が未検証だった**: 本リポジトリには Java / Go / Rust / C / C++ のソースが 1 件も無いため、既存テストは抽出器を直接呼ぶだけで `build_index` 経路を通っていなかった。temp corpus を索引する `TestIndexIntegration` を追加し、`files.parser='tree-sitter'` の記録、`.h` の内容判定、symbols / chunks / refs / imports の永続化、chunk→symbol linkage を検証する。
- **索引 DB がスキーマ v2 のまま残っていた**: 実装は `SCHEMA_VERSION = 3`。旧 DB が `cq stats` で fail-closed 拒否されることを実機確認し、両 profile を再構築した。`profile=app` の parser 内訳が `ast` 150 → `regex` 150 へ是正され、FR-CQ-11 の「専用 regex 抽出器を `ast` と誤表示しない」が実データで確認できた。
- **[cq/languages/csharp.py](cq/languages/csharp.py) が `interface` / `struct` / `enum` を `class` として記録していた**: `class|record|struct|interface|enum` を単一の正規表現で受けながら kind を固定していた。宣言キーワード由来の kind へ是正した（`record` は最小 kind 語彙に無いため `class` のまま）。再構築後の `profile=app` で interface 74 件 / enum 36 件が正しい種別になった。
- **要件マッピングが実装と正反対だった**: [hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) の FR-CQ-11 に「非実装（意図的）: tree-sitter を採用しない」「`code` extra を追加せず」が残っていた。採用した backend、不採用にした `tree-sitter-language-pack`、C#/JS/TS の再評価結果、未解決項目へ書き換え、FR-CQ-04 / 05 へ再実測を追記した。
- **Skill / 利用者ガイドが旧実装のままだった**: [indexing-internals.md](.github/skills/code-query/references/indexing-internals.md) の「cAST を **Python にだけ** 適用」「parser（`ast` / `lite`）」、[users-guide/skills-code-query.md](users-guide/skills-code-query.md) の「tree-sitter は不採用」「SCHEMA v2」「対応言語表」「実測値」を実装と実測へ同期した。
- **作業成果物のリンクが全て切れていた**: `work/run/20260730-cq-lang-expansion/` の README / plan / subissues が参照する Sub-1 spike 成果物は commit されておらず存在しない。数値の復元は捏造になるため、**存在しない事実を明記**したうえで根拠を再現可能な証跡（テスト / CI / `pyproject.toml`）へ移した。
- **成果物が消えた根本原因は [.gitignore](.gitignore) にあった**: .NET Core 向けテンプレート由来の `artifacts/` がリポジトリ全域に効いており、`work-artifacts-layout` Skill が標準ディレクトリと定める `work/run/**/artifacts/` を丸ごと除外していた。Sub-1 の spike 成果物が commit されなかったのはこのためで、放置すれば今回追加した証跡も同じく失われる。`work/**/artifacts/` だけを除外から外し、トップレベルの `artifacts/`（ビルド出力）は除外のまま維持した。
  - 除外を外した直後、過去 run の `*.env` に Azure サブスクリプション ID と内部エンドポイントが含まれていることを確認したため、`work/**/artifacts/` 配下でも `*.env` / `*.env.d/` / `*.log` / `*.key` / `*.pem` は除外を維持する。調整後に可視化される 69 ファイル（`.md` 59 / `.py` 7 / `.json` 3）へ、サブスクリプション ID・GUID・資格情報らしき文字列が含まれないことを機械走査で確認した。
  - この修正により、過去 run の未追跡成果物 69 ファイル（約 0.3 MB）が `git status` に現れる。内容の commit 可否は本件では判断していない。

#### C# / JavaScript / TypeScript の再評価（移行は未実施）

Sub-7 の必須項目として、実 corpus（`profile=app`）で regex 抽出器と公式 tree-sitter 文法を比較した。文法は測定のためだけに一時導入し、測定後に削除している（`code` extra は不変）。

| 言語 | ファイル | tree-sitter | regex | 欠落 | 誤検出 | recall |
|---|---:|---:|---:|---:|---:|---:|
| C# | 74 | 1,354 | 1,206 | 148 | 0 | 89.1% |
| JavaScript | 76 | 196 | 189 | 7 | 0 | 96.4% |
| TypeScript | 0 | — | — | — | — | 測定不能 |

欠落は C# の interface メンバ等ボディ無し宣言と、JS のオブジェクトリテラル内ショートハンドメソッド。tree-sitter への移行は言語モジュール 3 本と宣言依存 3 件の追加を伴い Sub-3〜6 と同規模になるため、本件の対象外として別タスクへ切り出した。

#### 検証

<!-- validation-confirmed -->

- `pytest cq/tests` **436 passed**（`[code]` extra 導入前は tree-sitter 契約 66 件がモジュール単位 skip、導入後に +75 件が実行対象化）。
- `pytest hve/tests/{test_hve_requirement_traceability_contract,test_code_query_skill_wiring,test_code_query_scope_contract,test_mdq_vendor_sync}.py` **101 passed**。`.github/scripts/validate-skill-routing.py` exit 0。
- RED → GREEN の実証: C# の kind 修正は先に 3 件の失敗テストを作ってから実装した。
- 索引再構築（スキーマ v3）: `profile=hve` 770 files / 13,523 symbols / 13,348 chunks / 70,461 refs / 40.42 MB / 11.6〜12.8 秒、`profile=app` 154 files / 1,404 symbols / 512 chunks / 4.18 MB / 0.9 秒。
- 検索品質の非退行: cq ゴールデン 42 問は hve / app とも **top-1 95.24%**。mdq FR-MDQ-01 は **top-1 0.45 / top-k 0.75** で記録値と一致。
  - 注意: mdq は**索引を完全再構築してから**測定すること。stale 索引（`--ensure-index` では完全更新されない）だと 0.15 / 0.40 に見え、退行と誤認する。
- 棚卸し索引を再生成。`hve-surface-inventory.csv` の差分は編集した `cq/languages/csharp.py` の行に限定。
- ドキュメントの識別子・`SCHEMA_VERSION`・parser 表・chunker 一覧・相対リンクを実装に対して機械照合（欠落 0 / リンク切れ 0）。
- 未解消として残す: C#/JS/TS の tree-sitter 移行判断、外部 OSS corpus と Universal Ctags / native parser の定量比較（U5）、macOS での install 実行検証（U6 の残り）。

### Added — markdown-query 配布 vendor の同期スクリプト

`tools/skills/markdown_query/` に `sync-vendor.ps1` / `sync-vendor.sh` を追加した。上流 `mdq/` を `tools/skills/markdown_query/vendor/mdq/` へ再生成する。これまで再同期手順は [vendor/SYNC.md](tools/skills/markdown_query/vendor/SYNC.md) の手打ちコマンドしか無く、姉妹キットの [code_query](tools/skills/code_query/sync-vendor.ps1) だけがスクリプトを持っていた。

- 除外物は `tests/` / `__pycache__/` / `golden-queries.json` の 3 種で、code_query 側と同一。`golden-queries.json` は期待パスと行番号が本リポジトリ固有のため配布しない。
- code_query 版と異なり `UPSTREAM.txt` は生成しない。`vendor/cq/` は [.gitignore](.gitignore) 済みだが `vendor/mdq/` はコミット対象であり、生成すると絶対パスと生成時刻が毎回差分として混入するため。
- 両スクリプトは実行結果が一致することを確認済み（ともに 20 ファイル、再実行で git 差分 0）。上流が見つからない場合はどちらも exit 2 で停止し、`vendor/` を破壊しない。

### Fixed — 上流と配布 vendor の同一性検査の欠落、および `--fusion-alpha` の既定値誤記

配布キットが「他リポジトリでも同じコードで動く」ことを機械保証できていなかった 4 点を是正した。**実行時の挙動は変更していない。**

- **[hve/tests/test_mdq_vendor_sync.py](hve/tests/test_mdq_vendor_sync.py)**: 検査対象が 20 モジュール中 `watcher.py` / `golden_eval.py` / `search.py` の 3 個だけで、残り 17 個のドリフトは無検出だった。配布対象を「上流の中身 − 除外物」と定義し直し、全ファイルの byte 一致・欠落・余剰・除外物の混入を検査する。定義を再帰走査にしたため、将来 `.py` 以外の実行時アセットやサブパッケージが増えても検知漏れしない。
- **[vendor/SYNC.md](tools/skills/markdown_query/vendor/SYNC.md)**: 記載の手順が `golden-queries.json` を除外しておらず、**手順どおり再同期すると検査に失敗する状態**だった。手順を新しいスクリプト参照へ置き換え、実際の除外規約と、忘れた再同期がテストで落ちることを明記した。
- **[mdq/cli.py](mdq/cli.py)**: `--fusion-alpha` の help が `Default: 0.5.` と表示していたが、argparse の実装は `default=None`（未指定ではベクトル統合を一切行わない）だった。help を実装に一致させ、あわせて FTS5 経路（`--engine fts5`）では fusion が適用されない制約を明記した。同じ誤記が波及していた [cli-reference.md](.github/skills/markdown-query/references/cli-reference.md) の既定列も是正。回帰は [mdq/tests/test_fusion.py](mdq/tests/test_fusion.py) の契約テストで固定した（help が既定値を名指しする場合、argparse が適用する値と一致することを要求）。
- **[hve/gui/tests/test_cq_standalone_gui.py](hve/gui/tests/test_cq_standalone_gui.py)**: cq の portable bundle fixture が除外規約の 3 つ目の複製を持ち、`sync-vendor.{ps1,sh}` から静かにドリフトしうる状態だった。スクリプトの削除対象を抽出して集合比較する検査を追加し、除外物の追加・削除の双方向を検知できるようにした。

#### 検証

<!-- validation-confirmed -->

- 対象テスト: [test_mdq_vendor_sync.py](hve/tests/test_mdq_vendor_sync.py) **23 passed** / [test_cq_standalone_gui.py](hve/gui/tests/test_cq_standalone_gui.py) **11 passed** / [test_fusion.py](mdq/tests/test_fusion.py) **6 passed**。
- 回帰: `mdq/tests` + `cq/tests` + vendor 同期 / GUI / 索引 / Skill 配線 / 要件トレーサビリティの各契約テスト → **703 passed / 3 skipped**。
- RED → GREEN の実証: `--fusion-alpha` の help 修正で vendor が上流から乖離し `test_vendored_file_matches_upstream_byte_for_byte[cli.py]` が失敗、`sync-vendor.ps1` 実行で復帰することを確認した。vendor へ意図的にドリフトを注入した場合の検出も実測済み。
- 同期スクリプトの再現性: `sync-vendor.ps1` と `sync-vendor.sh` の実行後いずれも `vendor/mdq` の git 差分が 0（＝コミット済み状態を正確に再現）。
- 棚卸し索引を再生成（8,696 rows / 435 files）。差分は今回変更したテスト 3 ファイルの行に限定され、`hve-feature-inventory.csv` と `hve-surface-inventory.csv` は無変化（新規 active 要件なし、関数定義を持たないシェルスクリプトは索引対象外で code_query 側と一貫）。

#### 既知の制約（本変更の対象外）

- `mdq/tests/test_sentence_splitter.py` の 2 件（`test_japanese_basic_split` / `test_mixed_block_with_fence_and_prose`）が失敗する。[mdq/sentence_splitter.py](mdq/sentence_splitter.py) と当該テストはいずれも本変更で触れておらず HEAD から未変更のため、**既存の失敗**として切り分けた。
- 変更種別は bugfix / maintenance であり、新規要件 ID は追加していない。`--fusion-alpha` の help 是正は CLI help 文言を直接規定する active 要件が存在しないため要件 ID は N/A とし、既存の FR-MDQ-01 / FR-CQ-12 の配布同一性の範囲で [requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) の記述のみ実態に合わせて更新した。

### Fixed — 実装と食い違っていたドキュメント・要件対応の是正（不要コード棚卸しの副産物）

到達不能コードの棚卸し（下記 `Removed` 項目）の過程で判明した、**実装と記述が食い違っている 3 箇所**を是正した。コードの挙動変更はない。

- **[hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) の NFR-SEC-03**: 間接対応テストから [hve/tests/test_security.py](hve/tests/test_security.py) を削除した。同テストが検証する `hve/security.py::sanitize_user_input` は **プロンプトへ埋め込む自由記述入力のサニタイズ**であり、NFR-SEC-03（`git add` の pathspec 除外 / shell インジェクション対策）とは無関係だったため。あわせて「（未対応要件）`hve/security.py` プロンプトインジェクション対策」の項を新設し、**実装とテストは存在するが本体からの呼び出しが 0 件**である事実と、配線するか削除するかが未決である旨を記録した。
- **[users-guide/pricing-guide.md](users-guide/pricing-guide.md)**: §4.2「GUI 設定タブ」と §6「CUI StatusLine」を **未実装** と明記した。[hve/gui/settings_pricing_tab.py](hve/gui/settings_pricing_tab.py) は [hve/gui/settings_window.py](hve/gui/settings_window.py) から import されておらず、[hve/statusline.py](hve/statusline.py) はどこからも import されていない（本 CHANGELOG に「orchestrator / console への実呼び出し統合は未実施」と記録されたまま）。環境変数 `HVE_PRICING_STATUSLINE_ENABLED` / `HVE_NO_STATUSLINE` が現状では効果を持たないこと、Q2「StatusLine が出ない」が仕様であることも追記。GUI Footer / 統計ポップアップ / `hve pricing` CLI / 料金計算は配線済みで、記述は変更していない。
- **[hve/config.py](hve/config.py)**: `pricing_statusline_enabled` のコメントが抑止手段として挙げていた `--no-statusline` は **CLI に存在しない**（`hve/__main__.py` に定義なし）。当該記述を削除し、本フラグを読む実装が現在存在しない旨に改めた。

#### 検証

<!-- validation-confirmed -->

- 要件トレーサビリティ契約テスト（[hve/tests/test_hve_requirement_traceability_contract.py](hve/tests/test_hve_requirement_traceability_contract.py) / `.github/scripts/tests/test_validate_hve_requirement_traceability.py`）+ `hve/tests/pricing` + `test_config.py` + `test_phase6_option_parity.py` → **370 passed / 2 skipped / 200 subtests passed**。
- `hve-dev` 棚卸し索引を再生成（8,191 rows / 410 files）。

#### 未決（所有者判断が必要なため未実施）

- [hve/security.py](hve/security.py)（96 行）を **配線する**か **削除する**か。配線は機能追加のため `hve-dev/README.md` の TDD 順序（要件追加 → テスト仕様 → RED → 実装 → GREEN）が必要。削除はセキュリティ制御の撤去にあたる。
- [hve/gui/settings_pricing_tab.py](hve/gui/settings_pricing_tab.py) / [hve/statusline.py](hve/statusline.py) を **完成させる**か **削除する**か。削除する場合は `Config.pricing_statusline_enabled` と `HVE_PRICING_STATUSLINE_ENABLED` / `HVE_NO_STATUSLINE` の扱いも同時に決める必要がある。

### Removed — HVE 本体の到達不能コードを削除（孤立モジュール 10 / 孤立シンボル 13 / 廃止済みプロンプト定数 1）

`hve/` + `mdq/` の非テストコード 188 ファイル / 97,837 行を AST 参照グラフとシンボル単位参照解析で棚卸しし、**本体から到達不能** と裏取りできたものだけを削除した。実測 **コード側 −2,692 行**（テストファイル削除を含む全体は −2,905 / +116）。

#### 削除したモジュール（本体からの import 0 件）

| ファイル | 削除根拠 |
|---|---|
| [hve/knowledge_versions.py](hve/knowledge_versions.py) | import 元はテストのみ。`hve-dev/requirement-definition.md` に対応 FR/NFR なし、CHANGELOG 記載もなし |
| [hve/prompt_templates.py](hve/prompt_templates.py) | 9 ビルダ全てが非テスト参照 0。移行元 [hve/prompts.py](hve/prompts.py) の `*_PROMPT` は 14 件が現役で、宣言されていた R3.5 移行は実施されていない |
| [hve/gui/tasktre_widget.py](hve/gui/tasktre_widget.py) | `TaskTreeWidget` / `UserInteractionWidget` ともに定義行以外の参照 0。実表示は [hve/gui/widgets/dag_status_widget.py](hve/gui/widgets/dag_status_widget.py) が担当 |
| [hve/autopilot/precheck_llm_judge.py](hve/autopilot/precheck_llm_judge.py) | precheck v2 で `run_step1_precheck` から `use_llm_judge` が撤去済み（本 CHANGELOG 既存項目）。モジュール本体だけが残存していた |
| [hve/existing_artifact_snapshot.py](hve/existing_artifact_snapshot.py) | 同機能の正規実装は FR-CLI-50 が [hve/orchestrator.py](hve/orchestrator.py) `_detect_existing_artifacts` と明示。重複実装で呼び出し 0 |
| [hve/recreate_existing.py](hve/recreate_existing.py) | 検知対象の `recreate-existing` ラベル / HTML マーカーが Issue Template・`labels.json` のいずれにも存在せず到達不能 |
| [hve/gui/widgets/word_wrap_delegate.py](hve/gui/widgets/word_wrap_delegate.py) | docstring が用途先として挙げる `ActivityStatusWidget` は削除済み（本 CHANGELOG 既存項目） |
| [hve/tools/_inspect_state.py](hve/tools/_inspect_state.py) | 入力の `state.json` 自体が Resume 全廃（v1.1）で削除済み |
| [mdq/contextualizer.py](mdq/contextualizer.py) | import 0・テスト 0。同一テンプレートを [mdq/strategies_semantic.py](mdq/strategies_semantic.py) が `_CTX_TEMPLATE` として保持しており SSOT を一本化 |
| `tools/skills/markdown_query/vendor/mdq/contextualizer.py` | 上記の vendored コピー。[tools/skills/markdown_query/vendor/SYNC.md](tools/skills/markdown_query/vendor/SYNC.md) の同期表からも当該行を削除 |

対応テスト 5 ファイルも同時に削除（`test_knowledge_versions.py` / `test_prompt_templates.py` / `test_existing_output_snapshot.py` / `test_recreate_existing.py` / `autopilot/test_precheck_llm_judge.py`）。

#### 削除したシンボル（定義のみで呼び出し 0）

- [hve/gui/workbench_widgets.py](hve/gui/workbench_widgets.py): `WorkflowProgressWidget`（docstring 自体が `[DEPRECATED]` と `DagStatusWidget` への置換済みを宣言）。未使用化した import `Dict` / `List` / `QPlainTextEdit` / `apply_cjk_wrap` / `format_workflow_label_activity` も除去。
- [hve/orchestrator.py](hve/orchestrator.py): `_append_workiq_prefetch_log`（唯一の `json` 利用箇所だったため `import json` も除去）。
- [hve/runner.py](hve/runner.py): `_read_stdin_async`（実際に使われているのは `_read_stdin_multiline`。共通ヘルパー `_blocking_stdin_read` は存続）。
- [hve/gui/settings_store.py](hve/gui/settings_store.py): `load_mcp_enabled` / `save_mcp_enabled`（対になる `page_options.mcp_enabled_dict()` は「現行 UI は MCP Server の実行時 ON/OFF を扱わない」として空 dict を返すスタブで、永続化経路全体が未配線だった）。
- [hve/artifact_validation.py](hve/artifact_validation.py): `find_aqod_artifacts` と、その唯一の呼び出し先だった `is_aqod_helper_artifact` / `_asdw_data_create_executable_text` / `_asdw_sample_counts`。実際に使われる候補列挙は `_find_aqod_artifact_candidates`。
- [hve/workflow_registry.py](hve/workflow_registry.py): `get_artifact_description`。
- [hve/gui/timezones.py](hve/gui/timezones.py): `iana_names`。
- [hve/gui/workflow_step_requirements.py](hve/gui/workflow_step_requirements.py): `all_defined_keys`。
- [hve/gui/autopilot/log_events.py](hve/gui/autopilot/log_events.py): `format_prefixed_line`。
- [hve/gui/markdown_preview/preview_panel.py](hve/gui/markdown_preview/preview_panel.py): `_ExternalLinkPage`（中身が `pass` のみのプレースホルダで差し替え処理は未実装）。

#### 削除した廃止済みプロンプト定数

- [hve/prompts.py](hve/prompts.py): `AQOD_QA_PROMPT`。コメントは「`runner.py` の Phase 2 QA で使用」と記載していたが、[hve/runner.py](hve/runner.py) は `aqod_post_qa_enabled` 削除済みで、現行は `_skip_pre_qa = _is_aqod_workflow` により AQOD の QA 自体をスキップする。あわせてモジュール docstring の「R3.5 で `*_PROMPT` を `hve.prompt_templates` へ移行」という実態と逆の予告を削除。

#### 参照側の是正

- [hve/gui/i18n/translations.pro](hve/gui/i18n/translations.pro): `SOURCES` から `../tasktre_widget.py` を削除。
- [users-guide/hve-technical-architecture.md](users-guide/hve-technical-architecture.md) / [users-guide/workflow-reference.md](users-guide/workflow-reference.md) / [users-guide/skills-markdown-query.md](users-guide/skills-markdown-query.md): 削除済みモジュールへの参照を実装の実態へ修正。
- [hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md): AQOD 行から削除した `TestAqodQaPrompt` を除去。`hve-dev/hve-test-inventory.csv` / `hve-dev/hve-tdd-crosswalk-baseline.md` を再生成（8,191 rows / 410 files）。

#### 意図的に削除しなかったもの

- **[hve/security.py](hve/security.py)（96 行）**: `sanitize_user_input` の本体呼び出しは 0 件だが、これは死コードではなく **未配線のプロンプトインジェクション対策**である。削除ではなく配線が正解の可能性があるため、方針決定まで維持する。あわせて `hve-dev/requirement-test-mapping.md` L153 が本テストを NFR-SEC-03（`git add` の pathspec 除外）の間接根拠としている点は、`sanitize_user_input` が pathspec と無関係であるため対応が誤っている（別途要是正）。
- **[hve/gui/settings_pricing_tab.py](hve/gui/settings_pricing_tab.py)（239 行）/ [hve/statusline.py](hve/statusline.py)（227 行）**: 本体参照 0 だが `users-guide/pricing-guide.md` に公開仕様として記載があり、本 CHANGELOG にも「次回 orchestrator 改修時に統合予定」と将来計画が明記されている。「不要になったコード」ではなく「未完成の機能」であるため対象外とした。
- **[hve/dag_parity.py](hve/dag_parity.py) / [hve/cloud_aagd_gate.py](hve/cloud_aagd_gate.py) / [hve/gui/markdown_preview/download_assets.py](hve/gui/markdown_preview/download_assets.py)**: Python の import グラフには現れないが、それぞれ `test-hve-python.yml` の独立 pytest ステップ / `auto-ai-agent-dev-reusable.yml` の `python3 -m hve.cloud_aagd_gate` / `setup-hve.{ps1,sh}` から起動される。

#### 検証

<!-- validation-confirmed -->

- **collection**: `hve/tests` + `hve/gui/tests` + `mdq/tests` + `tools/skills/markdown_query/gui/tests` + `.github/scripts/python/tests` で **6,978 tests collected、収集エラー 0**。
- **直接影響スイート**: `test_prompts.py` / `test_aqod_qa_prompt.py` / `test_workflow_registry.py` / `test_qa_merger.py` / `test_questionnaire_ui.py` / `hve/gui/tests` → **1,529 passed / 2 skipped / 2 subtests passed**。
- **残り全スイート**: `hve/tests` + `mdq/tests` + `tools/skills/markdown_query/gui/tests` + `.github/scripts/python/tests` + `test_validate_skill_routing.py` → **5,856 passed / 20 skipped / 2 xfailed / 458 subtests passed、10 failed**。10 件の内訳は以下のとおりで、いずれも本変更に起因しない。
  - 5 件（`test_app009_swa_workflow_exists_and_uses_oidc_dynamic_token` / `test_aad_web_fanout_meta_is_forwarded_to_step_runner` / `mdq` の `test_sentence_splitter` 2 件 / `test_deploy_ac_gate_preserves_legacy_ac1_fallback`）は **pre-existing**。`git stash` で本変更を退避した状態で同一テストを実行し、**同じ 5 件が同じ理由で失敗する**ことを確認済み。
  - 5 件（`test_validate_skill_routing.py` 4 件 / `test_parse_filter_error.py` 1 件）は測定時に設定した `PYTHONIOENCODING=utf-8` が子プロセスへ伝播し、親側 `subprocess` の cp932 デコードと不整合を起こしたもの。当該環境変数を外して再実行すると **14 passed**。
- **静的検査**: 編集した 14 ファイルに対する AST ベースの未使用 import 検出で、本変更が生んだ未使用 import は 0（`hve/runner.py` の `QA_PROMPT_V2` 等は pre-existing のため対象外とした）。

### Removed — HVE 生成 registration script への文法・drift 検出テストを削減（第 2・3 弾）

- [hve/tests/test_asdw_data_registration_audit_mode.py](hve/tests/test_asdw_data_registration_audit_mode.py) を **66 → 33 テスト**へ縮約した。`src/data/azure/data-registration-script.sh` は [hve/asdw_data_script_generator.py](hve/asdw_data_script_generator.py) の `_render_registration_script` が固定テンプレートから決定論的に生成し、生成器自身が `_producer_validation_errors` で同じ validator にかけ、tracked ファイルは byte-identical guard で固定されているため、変形入力は原理的に発生しない。
  - 削除内訳（計 33）: 冪等性ガード drift 3 / 完了ライフサイクル・成功マーカー・marker 外実行 3 / mode wiring 3 / `aci_command` 割当・実行 drift 2 / ACI オプション・環境トークン・import 順 9 / 埋め込み Python の非 canonical 文法・型契約 2 / audit block marker 隠蔽・status mask・host allowlist・インベントリ・marker 外書き込み 6 / create コマンド逸脱・subnet drift・入れ子 Azure CLI 3
  - 未使用となったヘルパー `_unconditional_sql_registration_source` / `_unconditional_direct_registration_source` も削除。
  - **維持**: 生成 Python を `exec` で実行して冪等性・重複行拒否・ロールバック・close 失敗継続を確認する 11 件（実行ベース検証）、design mode 判定の正常系 / 不一致検出、誤検知防止系、共有 Skill 契約の文言固定 5 件（SSOT 集約が前提のため保留）。

#### 検証

- 当該ファイル: **73 passed**
- producer 関連 10 スイート: **472 passed / 5 skipped**
- 第 1 弾の検証として clean tree で full-suite を実行済み: **7,225 passed / 5 failed**（5 件はすべて削除と無関係の pre-existing / 別領域）

### Added — 分離済み残件（TBD-06 / TBD-19 / E-2）の処理

#### Fixed — prefix 存在ゲートによる検証の回復（TBD-19 解消）

FR-WF-OUT-09 で「ゲートが無言で空になる」と記録した 7 Step のうち **4 Step の検証を回復** した。当初は「カタログに英名スラッグ列を追加」または「成果物命名を ID のみへ改める」のいずれかの契約変更が必要と見積もっていたが、実地の証拠がより単純な解を示した。

**決定的な証拠**: 単一 run（`ed3931b8`）の生成物が `docs/services/` だけで 3 形式に分岐していた。

| 実在ファイル | 形式 |
|---|---|
| `SVC-01-member-consent-service-description.md` | `{id}-{slug}-description.md` |
| `SVC-02-description.md` | `{id}-description.md` |
| `SVC-09.md` | `{id}.md` |

完全パス一致でも glob 一致でも誤 fail するが、**全件が ID 接頭辞で始まる**点は一貫している。したがって接頭辞一致だけが誤 fail なしに「当該キーの成果物が存在するか」を検証できる。

- **FR-WF-OUT-10**（新規要件）— FR-WF-OUT-06 で drop されたエントリのうち fan-out キーを実際に含むものを、キー出現位置までの接頭辞による **prefix 存在ゲート**へ降格する。`output_paths` の内容は変更しないため、`collect_workflow_output_paths` / `existing_artifact_snapshot` / io-contract など他の消費者への影響はない。
- 回復した Step: **AAD-WEB 2.1 / 2.2、ASDW-WEB 3.3、AKM 1**。FR-WF-OUT-09 の allowlist は **7 → 3 件**へ縮小した。
- 残る 3 件は prefix 化しても検証できない（ADFDV 2.1 / 2.2 は `{jobId}` が `dataflow_catalog` の返す APP-ID と不一致でキーが代入されない。ASDW-WEB 4.2 は全 fan-out 子で同一の固定パス）。

#### Added — ARD を CLI / GUI Orchestrator 専用と確定（TBD-06 解消）

- **FR-WF-ARD-01**（新規要件）— ARD の Cloud Orchestrator 対応を**行わない**と確定した。根拠は (1) `auto-orchestrator-dispatcher.yml` の `trigger_map` に ARD は未登録で専用の Issue Template / state-transition / reusable workflow も存在しない、(2) Cloud 対応の追加は 30+ ファイル規模、(3) FR-CLOUD-06 で ASDW-WEB を Cloud dispatch から**削除**しており Cloud 対象を増やす方向とは逆行する。
- [hve/tests/test_ard_cli_only_contract.py](hve/tests/test_ard_cli_only_contract.py) — dispatcher の `trigger_map` / `done_map` / `uses` に ARD が現れないこと、ARD 専用 reusable workflow が存在しないこと、要件定義との一致、および他 8 ワークフローの Cloud 起動経路が不変であることを固定。

#### Changed — E-2 残件の判定確定

| 項目 | 判定 | 根拠 |
|---|---|---|
| mdq watcher 既定化（TBD-20） | **解消済み** | `mdq_watch: bool = True` が既定 ON で、`run_workflow` が `dry_run` 以外で起動し `atexit` で停止する。追加作業なし |
| APP-009 汎用化（TBD-21） | **feature 保留** | `ASDW_DATA_DEPLOY_SUPPORTED_APP_ID` と `_has_supported_asdw_data_deploy_app_scope` により APP-009 以外は生成前に fail-closed で拒否されるため**欠陥ではない**。汎用化は SQL エンティティ対応を設計書から導出する feature |
| `artifact_validation.py` 分割（TBD-22） | **実施しない** | 11,365 行だが機能変更を伴わない大規模リファクタで、`import` 経路の変更が runner の定数 re-export と契約テスト群へ波及する。行数肥大が実害を生んでいる事実が未観測 |
| 到達不能コード削除（TBD-23） | **保持する** | `_run_asdw_data_deploy_preflight_failure_gate` 等は現状到達不能だが経路は構造上復活し得る。削除すると復活時に検出が無言で失われるため多層防御として保持 |

#### 検証

- RED: `resolve_output_path_prefix_gates` 未実装で ImportError、ゲート接続前に 3 件失敗。
- GREEN: 新規 3 ファイル 39 テストを含む関連 7 ファイルが全通過。

### Fixed — `output_paths_template` の宣言健全性（永久未解決エントリと無言のゲート消失）

**概要**: live canary 後の棚卸しで、`output_paths_template` の宣言に **実行時ゲートが機能しない 2 系統の欠陥** が見つかった。いずれも「誤 fail」ではなく「宣言があるのに検証が無言で消える」形の欠陥のため、CI でも実行ログでも気付けない状態だった。

#### Fixed

- **非 fan-out Step が fan-out プレースホルダを宣言していた**。`asdw-web` Step 3.4（`fanout_parser=None`）が `src/test/{serviceId}-{serviceNameSlug}/` を宣言していた。fan-out しない Step ではキー別名を代入する機会が無く、当該エントリは永久に解決されない。実際に `src/test/` 直下へ当該ディレクトリが作られたことも無い（実在するのは `api` / `integration` / `ui` の 3 つのみ）。[hve/workflow_registry.py](hve/workflow_registry.py) から除去し、io-contract を同期した。
- **実在しない命名規約を宣言していた**。`asdw-web` Step 3.2 が `src/test/api/{serviceNameSlug}.Tests/` を宣言していたが、ASDW-WEB 実行後に実在するのは `SVC-01.Tests` 〜 `SVC-23.Tests` の 8 ディレクトリで、いずれも **serviceId** による命名だった（`{serviceId}-{serviceNameSlug}` 形式を採る `src/api/SVC-01-member-consent-service/` とは規約が異なる）。`{serviceId}` へ是正し、io-contract を同期した。

#### Added

- **FR-WF-OUT-08**（新規要件）— 名称スラッグ（`{screenNameSlug}` / `{serviceNameSlug}` / `{jobNameSlug}`）は **日本語カタログ名の英訳** であり（`docs/catalog/service-catalog.md` の `SVC-01 | 会員・同意管理サービス` に対し実在ファイルは `docs/services/SVC-01-member-consent-service-description.md`）、訳語は Agent が生成するため [hve/catalog_parsers.py](hve/catalog_parsers.py) を拡張しても決定的には復元できない。キー別名への登録を恒久的に禁止する。
- **FR-WF-OUT-09**（新規要件）— fail-closed drop（FR-WF-OUT-06）の結果、fan-out する Step の宣言が**どのキーでも 1 件も解決されず実行時ゲートが無言で空になる**状態を、理由付きの明示 allowlist として固定する。allowlist 外の Step がゲート空になった場合、および解決可能になったのに allowlist へ残っている場合の双方を CI で検出する。現時点の該当は 7 件で、名称スラッグ由来の 5 件（AAD-WEB 2.1 / 2.2、ADFDV 2.1 / 2.2、ASDW-WEB 3.3）に加え、本テストの導入によって新たに **AKM 1**（`knowledge/{key}-*.md` の glob）と **ASDW-WEB 4.2**（`src/app/` 配下が全 fan-out 子で同一の固定パス）も検証が消えていたことが判明した。
- [hve/tests/test_output_paths_template_resolvability.py](hve/tests/test_output_paths_template_resolvability.py) — 非 fan-out Step のプレースホルダ宣言禁止、静的キー fan-out の誤検知防止、テストプロジェクト命名規約の固定、ゲート空 allowlist の一致検証、名称スラッグのキー別名登録禁止。
- [hve/tests/test_requirement_definition_adfdv_section.py](hve/tests/test_requirement_definition_adfdv_section.py) — 要件定義 §13.5 が `hve/workflow_registry.py` の ADFDV 実定義（Step 集合・Custom Agent・fan-out parser）と一致し、廃止済みの `src/batch/` 系パスを含まないことを固定。
- [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py) — `ALLOWED_EMPTY_OUTPUT_PATHS_STEPS` に陳腐化エントリが残らないこと、および allowlist 対象 Step の template `## 出力` がリポジトリ内成果物を宣言していないことを検証（コメントによる正当化を実行可能なテストへ置換）。

#### Changed

- [hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) を v1.5 へ更新。**§13.5 を全面改訂**し、節名を ABDV（Batch Dev）から **ADFDV（Dataflow Dev）** へ改称、Custom Agent 列を追加、生成先を `batch` から `dataflow` へ、fan-out parser を `batch_job_catalog` から `dataflow_catalog` へ、成果物パスをレジストリ実定義へ一致させた（**FR-WF-ADFDV-01 / 02** を新設）。あわせて **TBD-18**（Step 1.2 の template ↔ Prompt 重複は残り 11 行が意図的な契約であり削減不可）と **TBD-19**（名称スラッグのゲート復旧はカタログ様式または命名規約の変更を要する）を追記した。

#### 検証

- RED: 新規テストが修正前に 4 件失敗（非 fan-out プレースホルダ宣言 1 件、命名規約 3 件）。
- GREEN: 対象 3 ファイル 181 passed / 1 skipped / exit 0。
- io-contract: `.github/scripts/validate-io-contract.py` が Schema 0 / Integrity 0 / **Registry mismatch 0** / exit 0。
- 実行経路: 全 11 ワークフローの dry-run で 10 件 exit 0。`asdw-web` のみ exit 1 だが、これは `resource_group` 未指定による pre-flight ブロック（`status=blocked`）で、`--app-ids` / `--resource-group` を与えると exit 0 になることを確認済み（退行ではない）。

#### 既知の制約

- ゲートが空になる 7 Step（FR-WF-OUT-09 の allowlist）は、成果物の存在検証が実行時に行われない状態が続く。名称スラッグ由来の 5 件の復旧には TBD-19 のとおりカタログ様式または成果物命名規約の変更を伴うため、独立タスクとして分離した。
- `asdw-web` Step 3.3 は固定パス（`src/test/api/smoke-ui/index.html`）も宣言しているが、キー別名を含まないため FR-WF-OUT-06 規則 1 により drop される。fan-out 子で共有される成果物を 1 回だけゲートする仕組みは未実装。

### Fixed — live canary が検出した ASDW Step 1.3 の Windows 実行不能欠陥 4 件を修正

**概要**: 2026-07-28 の live canary（`asdw-web` 全 16 Wave、run `20260728T034239-836daa`）が Wave 9 の Step 1.3 で `ASDW Step 1.3 could not run the Azure CLI to resolve SUBSCRIPTION_ID` により停止した（37 成功 / 1 失敗）。原因は **Windows 実機でのみ発現する 4 件の欠陥**で、いずれも既存テストが対象関数をモックしていたため実経路が未検証だった。Step 1.3 のネイティブ実行経路は Windows 上で **一度も成功したことがない**状態だった。

#### Fixed

- **Azure CLI を素のコマンド名で起動していた**（確定ブロッカー）。[hve/runner.py](hve/runner.py) `_resolve_asdw_data_deploy_subscription_id` と [hve/asdw_data_script_launcher.py](hve/asdw_data_script_launcher.py) `_resolve_deploy_identity_client_id` が `subprocess.run(["az", ...])` を呼んでいた。Windows の `CreateProcess` は拡張子なしコマンドへ `.exe` しか補完しないため、実体 `az.CMD` を起動できず `FileNotFoundError` になる。新設した `resolve_azure_cli_executable()` が **信頼ルート優先 → 継承 PATH フォールバック → fail-closed** の順で解決する。[hve/__main__.py](hve/__main__.py) `_azure_account_available` が既に採用していた `shutil.which` 規約を ASDW 経路へ揃えたもの。
- **設計書・サンプルデータの CRLF を拒否していた**（確定ブロッカー）。[hve/asdw_data_script_launcher.py](hve/asdw_data_script_launcher.py) `_read_stable_utf8_file` が全入力に LF を要求していた。[.gitattributes](.gitattributes) は `*.sh` にしか `eol=lf` を付けておらず、`core.autocrlf=true` の Windows チェックアウトでは `docs/azure/azure-services-data.md`（CR 107 箇所）と `src/data/sample-data.json`（CR 144 箇所）が必ず CRLF になる。[hve/asdw_data_script_generator.py](hve/asdw_data_script_generator.py) は同じ 2 ファイルを `allow_crlf=True` で読み、pre-gate の validator も universal newlines で吸収するため、**generator と gate は通過して launcher だけが落ちる**非対称があった。`allow_crlf` 引数を追加して generator と同一契約に揃え、HVE 生成物である `.sh` は LF 厳格のまま維持した。
- **子プロセス環境から home 変数が消え `az` が未ログイン扱いになっていた**（確定ブロッカー）。`_build_child_environment` は allowlist で環境を完全置換するため `USERPROFILE` / `TEMP` / `TMP` が失われ、bash 内の `az` が設定ディレクトリを相対パス `~/.azure` へ解決してトークンを見失い、さらに **リポジトリルート直下に `~` ディレクトリを生成**していた。prep stage 最初の `az policy assignment list` が exit 1 になる。非機密のホストパス（`USERPROFILE` / `HOMEDRIVE` / `HOMEPATH` / `TEMP` / `TMP`、POSIX では `HOME` / `TMPDIR`）を転送し、`AZURE_CONFIG_DIR` を明示解決して注入するようにした。機密キーの遮断は従来どおり。
- **信頼 Bash が継承 PATH を前置していた**（セキュリティ）。`_trusted_bash_path` が Git ラッパー `Git/bin/bash.exe` を使っていたため、`env` で渡した信頼 PATH より前に `/mingw64/bin:/usr/bin:/c/bin` が前置され、「継承 PATH を探索しない」という設計保証が Windows でのみ崩れていた。書き込み可能な `C:\bin` が信頼ルートを影で上書きし得る。`Git/usr/bin/bash.exe` へ変更し、実測で子 bash の PATH が信頼ルートのみ（`/usr/bin:/bin:/c/Windows/System32:/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin`）になることを確認した。

#### Added

- [hve/tests/test_asdw_azure_cli_resolution.py](hve/tests/test_asdw_azure_cli_resolution.py)（8 テスト）— Azure CLI 解決順序、fail-closed、両呼び出し箇所が解決済みパスを起動すること、および素の `"az"` 復活をソースレベルで禁止する退行ガード。
- [hve/tests/test_asdw_launcher_windows_runtime.py](hve/tests/test_asdw_launcher_windows_runtime.py)（10 テスト）— CRLF 許容範囲（設計書・サンプルは許容、生成物 `.sh` は厳格、単独 CR は常に拒否）、子環境の host runtime 変数と `AZURE_CONFIG_DIR`、機密キー遮断の維持、信頼 Bash の選択。

#### Changed

- [hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) に `FR-WF-ASDW-03` の対応テスト節を追加した。本修正は既存 active 要件 `FR-WF-ASDW-03`（`SUBSCRIPTION_ID` は `az account show` から取得）を Windows 上で復元するバグ修正であり、新規要件 ID は追加していない。

#### 検証

- RED: 新規 18 テストが実装前に 8/8・7/10 失敗（残り 3 件は既存の厳格性を固定する退行ガードのため当初から成功）。
- GREEN: 新規 18 テスト全通過。
- 実機実測: `resolve_azure_cli_executable()` → `C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.CMD`、`_resolve_asdw_data_deploy_subscription_id()` → 実 subscription ID を取得。修正後の子プロセス環境で `bash --noprofile --norc -s` 経由の `az account show` が rc=0、機密キー漏洩 0 件、`~` の誤生成なし。
- 回帰: ASDW 関連 8 ファイル 333 passed / 2 skipped / exit 0。

#### 既知の制約

- `_trusted_runtime_path()` は Azure CLI の既定インストール先 `C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin` を固定列挙しているため、旧 32bit MSI 等で別位置にある環境では子 bash 内の裸 `az` が解決できない。親プロセス側は `shutil.which` フォールバックで動作するため、**親は成功して子だけ失敗する**非対称が残る。
- `os.access(bash_path, os.X_OK)` は Windows では既存ファイルに対し常に True を返すため、実行可否の検証にはなっていない（機能的失敗は生じない）。

### Fixed — live canary が Step 1.3 の実行を進めるたびに検出した契約・引数・リージョンの欠陥 7 件を修正

**概要**: 上記 4 件の修正後、`asdw-web` の残り 9 Step（`1.3,2.2,2.4,3.4,3.5,4.3,4.4,5.1,5.2`）を live 実行するたびに Step 1.3 がより深い地点で停止し、そのつど新しい欠陥が判明した。**Step 1.3 のネイティブ実行経路は一度も Azure リソースを作成できたことがない**状態であり、単体テストは対象関数をモックしていたため 1 件も検出できていなかった。到達点は 0.0 秒 → 2.1 秒 → 3.7 秒 → 3.2 秒 → 43.5 秒 → 178 秒 → 151 秒 → 930 秒と伸び、prep stage 完走と SQL / Cosmos の実作成まで到達した。

#### Fixed

- **prep が自分で作成する identity の clientId を事前要求していた**（鶏と卵）。prep stage は managed identity `data-deploy-identity` を作成する stage であり、その clientId は Azure が採番するため prep 実行前には存在しない。要求定義 `FR-WF-ASDW-03` と [hve/asdw_data_runtime_context.py](hve/asdw_data_runtime_context.py) の docstring はいずれも「prep 成功後に launcher が読み戻す」と明記し、`_build_child_environment` も `stage != "prep"` のときだけ供給していたが、**生成器の prep テンプレートだけがこの決定を反映していなかった**。当該ガード 1 行を削除した。validator は prep と create の private branch を合わせて検査するため、create 側にガードが残る現状で契約は維持される。
- **Policy pre-flight が裸のサブスクリプション GUID をスコープに渡していた**。`az policy assignment list --scope` は ARM スコープパスを期待し、裸の GUID では azure-cli 内部の `ResolveScopeForList` が `IndexError` になる。実測で `--scope <GUID>` → rc=1、`--scope /subscriptions/<GUID>` → rc=0 を確認。同じスクリプト内の `az role assignment create` などは既に `/subscriptions/...` を組み立てており、policy pre-flight の 4 行だけが誤っていた。
- **子 bash で MSYS が ARM スコープ ID を Windows パスへ書き換えていた**。MSYS は POSIX 風の引数をネイティブ実行ファイルへ渡す前に変換するため、`/subscriptions/<id>` が `C:/Program Files/Git/subscriptions/<id>` に化けて Azure CLI が拒否した。回避方法を実測比較（対策なし rc=1 / `MSYS_NO_PATHCONV=1` rc=0 / `MSYS2_ARG_CONV_EXCL=*` rc=0 / 二重スラッシュ rc=1）し、両変数を子環境へ設定した。**生成スクリプトは変更せず、プラットフォーム差分を launcher の環境構築に閉じ込めている。**
- **宣言済み CIDR が沈黙のうちに無視されていた**。`az network vnet create` に `--address-prefixes` が無く、実際に作成された VNet のアドレス空間は宣言値 `10.40.0.0/16` ではなく Azure CLI 既定の `10.0.0.0/16` だった。`DATA_VNET_CIDR` / `DATA_PRIVATE_ENDPOINT_SUBNET_CIDR` / `DATA_ACI_SUBNET_CIDR` の 3 件は `FR-WF-ASDW-01` が既定値の根拠まで定義した宣言入力でありながら、**子環境の allowlist に無く、どの生成スクリプトにも一度も出現していなかった**。allowlist へ追加し、VNet とサブネットの作成へ適用した。
- **`az network vnet subnet create` に `--ids` を渡していた**。`--ids` は既存リソース参照用（show / update / delete）で、`create` では `--name` / `--resource-group` / `--vnet-name` が `[Required]`。`subnet update --ids` は正当なため維持している。
- **`az acr build` が Windows でソースディレクトリを解決できなかった**。ソース指定形式を実測比較したところ、ドライブレター付き絶対パス（区切り文字を問わず）もリポジトリ相対パスも `Unable to find 'Dockerfile'.` で失敗し、**カレントディレクトリを移して `.` を渡す形式だけが成立**した。なお Dockerfile の存在検査はレジストリ解決より後に行われるため、存在しないレジストリを使った安全なプローブでは再現しない。host grammar には当該 `cd` 2 文だけを許可として追加し、他の `cd` は引き続き拒否される。
- **SQL Server が AAD 専用認証で外部管理者を指定していなかった**。`az sql server create --enable-ad-only-auth` は外部管理者 3 引数を必須とし、欠けると Azure が `MissingExternalAdministratorWithAadOnlyAuth` を返す。管理者にはデプロイ用マネージド ID を指定した。`az sql server create --help` で Application の `--external-admin-sid` が Client ID（Object ID ではない）であることを確認しており、検証 ACI が `Authentication=ActiveDirectoryMSI` で接続する identity と一致させることで SQL への接続経路が一貫する。
- **Confidential Ledger が非対応リージョンで作成されていた**。`az provider show --namespace Microsoft.ConfidentialLedger` で `Ledgers` の対応 location を確認し、リポジトリ標準優先順位と突き合わせた結果 `japaneast` NG / `japanwest` NG / `southeastasia` OK。Skill `azure-region-policy` §2 の fallback ルールに従い、**台帳のみ** `southeastasia` へ退避する導出値 `CONFIDENTIAL_LEDGER_LOCATION` を追加した。

#### Added

- [hve/tests/test_asdw_data_stage_guard_contract.py](hve/tests/test_asdw_data_stage_guard_contract.py) — 「各 stage のスクリプトが要求する変数は launcher がその stage へ供給できるキーの部分集合である」という不変条件を 4 stage すべてに適用し、鶏と卵型の欠陥クラス全体を検出する。
- [hve/tests/test_asdw_data_azure_cli_scope_contract.py](hve/tests/test_asdw_data_azure_cli_scope_contract.py) — ARM スコープ形式、`az acr build` のソース指定形式、AAD 専用認証時の外部管理者 3 引数を固定する。
- [hve/tests/test_asdw_data_network_provisioning_contract.py](hve/tests/test_asdw_data_network_provisioning_contract.py) — 「宣言済みワークフローパラメータは生成スクリプトへ到達する」という不変条件、`create` での `--ids` 禁止、各サブネットの CIDR 適用、サブネット名リテラルとリソース ID 導出定数の一致、台帳 location の fallback を固定する。

#### 検証

- 各修正で RED → GREEN を確認（RED 合計 21 失敗）。
- Azure 実環境で作成を確認: リソースグループ、VNet（**宣言どおり `10.40.0.0/16` に是正**）、サブネット 2 件（`10.40.1.0/24` / `10.40.2.0/24`）、NAT Gateway、Managed Identity、Container Registry、検証イメージ `hve-asdw-data-verify:app009`、SQL Server（AAD 専用認証）、SQL Database 7 件、Cosmos DB。
- 各スクリプトの `bash -n` exit 0。

#### 既知の制約

- **監査ダイジェスト（Confidential Ledger）だけが `southeastasia` に置かれ、他のリソースは `LOCATION` のまま**というリージョン混在構成になる。リポジトリのリージョン方針上は正規の fallback だが、監査記録のデータ所在地はコンプライアンス判断を伴うため、要件次第では全体を `southeastasia` へ寄せる選択もあり得る。
- `CONFIDENTIAL_LEDGER_LOCATION` は導出定数であり、利用者が上書きする経路を持たない。
- 生成スクリプト内の全 `az` コマンドを `az ... --help` と突き合わせる一括監査を試みたが、`az --help` の起動が遅く並列化しても収束しなかったため断念した。欠陥クラスごとの `grep` 洗い出しで代替している。
- Step 1.3 より後の Step（2.2 / 2.4 / 3.4 / 3.5 / 4.3 / 4.4 / 5.1 / 5.2）は canary が到達していないため **未検証**。

### Removed — HVE 自身が生成する producer への文法・難読化テストと、完全重複テストを削除

**概要**: テストコード棚卸しの結論のうち、**前提条件なしで実施できる範囲**のみを適用した。削除根拠は「検証対象成果物の作者と決定性」であり、APP-009 固有性ではない。

#### Removed

- `hve/tests/test_asdw_data_create_validation.py` を **21 → 4 テスト**へ縮約した。`create-azure-data-resources{,-prep}.sh` は [hve/asdw_data_script_generator.py](hve/asdw_data_script_generator.py) の `render_asdw_data_producers` が固定テンプレートから決定論的に生成し、生成器自身が `_producer_validation_errors` で同じ validator にかけ、tracked ファイルは byte-identical guard で固定されている。したがって難読化・shell 再構成・隠蔽ブロックといった入力は原理的に発生しない。残したのは `test_accepts_private_design_aware_prep_and_create`（正常系）、`test_current_tracked_producers_pass_the_generator_contract`、`test_current_tracked_producers_are_byte_identical_to_generator_output`、`test_rejects_crlf_or_bom`（validator の退行検出用 negative 1 本）。
- `hve/tests/test_asdw_data_private_verify_validation.py` の `test_registration_aci_owner_gate_rejects_*` を **16 → 1 関数**へ縮約した（`data-registration-script.sh` も同じく generator 出力）。`test_registration_aci_owner_gate_rejects_missing_ownership_control` を negative として、`..._accepts_multiline_create_and_follow_up` を正常系として残した。
- `hve/tests/test_runner_output_paths_gate.py` を削除した（7 テスト）。同一対象 `_check_output_paths_gate` に対する検証が [hve/tests/test_runner_split_required_guard.py](hve/tests/test_runner_split_required_guard.py) の `TestCheckOutputPathsGate` と重複しており、ヘルパー `_FakeStep` / `_FakeWorkflow` も二重定義だった。**固有だった「3 宣言中の部分欠落」ケースのみ `TestCheckOutputPathsGate::test_fail_reports_only_missing_paths` として統合先へ移設**しており、カバレッジは失われていない。
- `hve/tests/test_workflow_registry_agentic.py` の `TestAadWebAgenticRetrievalStep::test_aad_web_step_2_2_depends_on_step_1` を削除した。同ファイル `TestAadWebStepOrderIntegrity::test_step_2_2_depends_on_step_1` と本体コードが完全一致していた。
- `hve/tests/test_config.py` の `test_auto_self_improve_default_false` を削除した。[hve/tests/test_self_improve.py](hve/tests/test_self_improve.py) の同名テストと本体コードが完全一致しており、self_improve 既定値群としてまとまっている後者を正とした。

#### Changed

- [hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) の `FR-WF-OUT-01` 対応テストを、削除した `test_runner_output_paths_gate.py` から統合先 `test_runner_split_required_guard.py::TestCheckOutputPathsGate` へ付け替えた。

#### 実施しなかったもの（前提条件が未充足）

- **文言固定テスト 164 件**（Prompt / template / Skill / io-contract の日本語文言を逐語照合）: RCA 施策 P1-2「契約 SSOT を Skill 1 ファイルへ集約」が未実施のため。集約前に削除すると契約検証が完全に消える。
- **統合判定 255 件**（validator ごとに parametrize 1 本へ集約）: 統合先テストの設計が未確定のため。
- **Agent 生成物への敵対的回避テスト 93 件**: 脅威モデル（Agent を敵対者とみなさない）の明示的合意が未取得のため。
- **未配線モジュール 7 件のテスト 68 件**: 「削除」か「本体への配線漏れ修正」かの要件判断が未了のため。
- `hve-dev/hve-test-inventory.csv` 等の棚卸し索引の再生成: 作業ツリーに他作業の未完了変更が多数あり、索引へ混入するため見送った。**clean な作業ツリーで `hve-dev/generate_tdd_inventory.py` を再実行すること**。

### Changed — io-contract の registry mismatch を 0 にして CI 必須化し、Self-Improve scope と ADFD producer 不在の構造的欠陥を解消

**概要**: 直前の変更で「既知の制約」として持ち越した 4 件を解消した。`output_paths_template` が単一プレースホルダ置換しか対応しないという構造的制約を、fan-out parser 由来の ID 別名解決と fail-closed な drop 規則で解消し、registry mismatch を **126 → 0** にして CI の registry-check を hard fail 化した。あわせて、部分的な `output_paths` 宣言が Self-Improve の対象範囲を無言で縮小させる欠陥、ADFDV が要求する 4 ドキュメントの producer Agent 不在、TDD レポート固定スキーマの Prompt/template 重複を解消した。

#### Added

- ADFD（Dataflow Design）へ Custom Agent 4 種と対応 Step を追加した。ADFDV が `required_input_paths` として要求しながら生成者が存在しなかった 4 ドキュメントの producer である。
  - `Arch-Dataflow-DataModel` → `docs/dataflow/dataflow-data-model.md`
  - `Arch-Dataflow-AppCatalog` → `docs/dataflow/dataflow-app-catalog.md`
  - `Arch-Dataflow-ServiceCatalog` → `docs/dataflow/dataflow-service-catalog.md`
  - `Arch-Dataflow-TestStrategy` → `docs/dataflow/dataflow-test-strategy.md`
  ADFD は 3 Step → **7 Step**（`0.1` → `0.2` → `4` → `5` → `1` ∥ `2` → `3`）。既存 Step 1 / 2 / 3 の ID・Agent 名・出力は不変。設計指針は Skill `dataflow-design-guide` へ委譲し本文を複製していない。
- `hve/orchestrator.py` に `workflow_output_paths_cover_workflow()` を追加した。DAG 根（`get_root_steps()`）が成果物を寄与しない workflow では、`SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS` のディレクトリ既定を維持する。
- 規範要件 `FR-WF-OUT-05`（registry mismatch 0 / CI hard fail）、`FR-WF-OUT-06`（fail-closed drop 規則）、`FR-WF-OUT-07`（非 fan-out Step は契約宣言専用）、および `FR-WF-ADFD-01`〜`04` を追加した。

#### Changed

- `hve/fanout_expander.py` の `output_paths_template` 展開を、fan-out parser ごとの **ID 別名**（`{screenId}` / `{serviceId}` / `{appId}` / `{agentId}` / `{businessId}` / `{useCaseId}`）へ対応させた。**別名として登録してよいのは「fan-out キーそのものを指す名前」だけ**であり、catalog から取得できない `{screenNameSlug}` 等は解決対象にしない。`{key}` は後方互換として維持する。
- 展開後に確定ファイルパスにならないエントリは `output_paths` に載せない **fail-closed な drop 規則 5 件**を導入した（別名を含まない / 置換後もプレースホルダが残る / glob を含む / ディレクトリ参照 / 宣言済みディレクトリ成果物の配下）。これにより「宣言はあるが実在しないパス」で実行時ゲートが誤 fail することを防ぐ。
- io-contract の registry mismatch を **126 → 0** にした。内訳は `knowledge/D*.md` を outputs から inputs（`required: false` / `kind: static`）へ移動 51 件、StepDef への宣言追加 57 件、`{key}` とプレースホルダ表記の統一 15 件など。**すべて template の `## 出力` または prompt の `<output_contract>` を根拠とし、例外登録は 0 件**。
- `.github/workflows/validate-io-contract.yml` の registry-check を warning-only（`exit 0` 固定）から **hard fail** へ変更し、trigger paths に `hve/workflow_registry.py` を追加した。
- `ALLOWED_EMPTY_OUTPUT_PATHS_STEPS` を **33 件 → 1 件**へ削減した。残るのは `adfdv 1.2` のみで、`## 出力` がリポジトリ内成果物パスを持たないことが理由。ASDW-WEB は **18 / 18 Step** が宣言済みになった。
- TDD レポート固定スキーマの検証を Prompt 側へ委譲した。`asdw-web/step-1.2.md` からスキーマの重複コードブロック 33 行を削除し、template には Step 固有値（`- Live-RED-Status: NOT_RUN` / `Raw-Log-Path` 規約等）のみを要求する。**固定スキーマ全 19 トークンの検証は Prompt 契約テスト・委譲分岐・Skill 正本テストの 3 箇所で担保**しており、検証は消滅していない。委譲は明示マップに列挙した 1 件に限定し、他 11 template は従来どおり全トークンを要求する。
- `.github/io-contract-exceptions.yaml` の `external_paths` を空にした（`docs/dataflow/` 4 件の暫定例外を撤去）。

#### Fixed

- **部分的な `output_paths` 宣言が Self-Improve の対象範囲を無言で縮小させる欠陥**を解消した。`run_workflow` は `collect_workflow_output_paths` が非空を返すだけでパス直指定へ切り替わっていたが、同関数は fan-out 展開を AAG / AAGD にしか適用していなかった。全 workflow で展開を試み、かつ **DAG 根の被覆**を満たすときだけパス直指定へ切り替えるようにした。これにより ADFDV / AKM / AAGD へ部分宣言を追加しても scope が縮小しない。
- `aad-web 2.1` の `output_paths_template` が `docs/screen/{key}-description.md` と宣言され、展開結果が実生成ファイル名とも io-contract とも一致しない誤宣言だった問題を修正した（厳格化済みの output gate では実行時 false fail を引き起こす）。
- `hve-dev/requirement-definition.md` の **TBD-11 / TBD-12 / TBD-14**（二重プレースホルダと動的パスの `output_paths` 未登録）を解消済みへ更新した。§13.4 が実在しない ABD を記載していた点を ADFD の実構成へ訂正した。

#### 既知の制約

- `adfdv 1.2` のみ `output_paths` 未宣言で allowlist に残る。`templates/adfdv/step-1.2.md` の `## 出力` が「Azure リソースの作成・検証完了」と `{WORK}` 配下の実行ログのみで、リポジトリ内の成果物パスを契約上持たないため。
- `{screenNameSlug}` / `{serviceNameSlug}` / `{jobNameSlug}` は `hve/catalog_parsers.py` が ID しか返さないため解決できない。該当パスは drop 規則により宣言されず、実行時ゲートの対象外となる。slug を含むファイル名まで検証するには catalog parser の拡張が必要。

### Changed — HVE 実行既定パスから「静かな失敗」と到達不能コードを除去し、成果物ゲートと io-contract を契約準拠へ

**概要**: HVE（GUI / CLI / Cloud）が本来の目的（他アプリのコード生成 → build/test → Azure deploy）を完走できるよう、既定の実行パスを縮約した。プロンプト構築の失敗が簡易プロンプトへ縮退して壊れたまま Agent を起動する経路、製品 run 中に HVE 自身のテストスイートを起動する処理、Step 1.3 の native 化で到達不能になっていた permission / session / MCP コード、registry と非同期のまま起動可能だった Cloud reusable workflow を取り除いた。あわせて成果物ゲートを FR-WF-OUT-01 準拠にし、io-contract の schema / integrity 検証を緑化した。判定基準は完走率・false fail・実 deploy であり、行数削減を目的化していない。

#### Added

- 規範要件 `FR-CLI-70`〜`FR-CLI-75`、`FR-CLOUD-06` を [hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) へ追加し、[hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md) で実在テストへ対応付けた。
- run 開始時の HVE ソース未コミット変更 preflight（`FR-CLI-74`）。branch 作成・Agent セッション開始より前に全パスを一括報告して停止する（[hve/orchestrator.py](hve/orchestrator.py) `_check_dirty_hve_sources`）。
- `git add` 後・`commit` 前の staged path 検査（`FR-CLI-75`）。HVE ソースが混入していれば index を `git reset --mixed` で戻し、commit / push を行わずに停止する。作業ツリーのファイル内容は変更しない（[hve/orchestrator.py](hve/orchestrator.py) `_git_add_commit_push`）。
- ASDW-WEB Step 1.3 の DataDeploy io-contract に、Step 1.3 が HVE native（`execute_pipeline`）であり Agent は成果物を著作しない旨を明記。

#### Changed

- 成果物ゲートを `FR-WF-OUT-01` 準拠へ変更した。従来は宣言した `output_paths` が**全て**欠落した場合のみ失敗としていたが、**1 件でも欠落したら失敗**とし、欠落パスのみを列挙する（[hve/runner.py](hve/runner.py) `_check_output_paths_gate`）。適用範囲（単独実行モードと fleet mode は対象外）を要件本文へ明文化した。
- ASDW-WEB の `output_paths` 宣言を 2 / 18 Step から 10 / 18 Step へ拡大した。残り 8 Step は成果物が可変ディレクトリ・二重プレースホルダ・条件付き生成物のみで、宣言すると誤 fail するため allowlist に残し理由を明記した（[hve/workflow_registry.py](hve/workflow_registry.py) / [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py)）。
- Copilot セッションへ公開する repository Skill ディレクトリを、`.github/skills` root 直下 25 ディレクトリの無条件全公開から、**root ＋ 宣言 Skill のみ**へ縮約した（`FR-CLI-73`、[hve/runner.py](hve/runner.py) `_repository_skill_directories`）。external Skill の fail-closed 解決は維持。
- io-contract の producer 宣言を validator が提示する実 ID（`--<workflow>--<step>` 付き）へ揃え、YAML block mapping のインデント不正 6 件を修正した。`--no-registry-check` の ERROR は **47 → 0**、全体 ERROR は **181 → 126** へ減少。
- Step 1.2 の template から Prompt と重複する記述を除去し、prompt + template の合計文字数を 24,328 → 22,571 文字へ削減した（[.github/scripts/templates/asdw-web/step-1.2.md](.github/scripts/templates/asdw-web/step-1.2.md)）。

#### Removed

- CLI / GUI の Step プロンプトへの `subissues.md` フォーマット例の常時注入（`FR-CLI-70`）。CLI / GUI Orchestrator では分割を workflow DAG / fan-out で表現するため、常時注入は誤った作業指示になっていた。`_SUBISSUES_FORMAT_HINT` と `_subissues_format_hint_for_step` を削除した。
- `body_template_path` 宣言 Step のテンプレートレンダリング失敗を握り潰す `except Exception: pass` と、簡易プロンプトへのフォールバック（`FR-CLI-71`）。レンダリング失敗は例外をそのまま伝播させ、原因テンプレートパスを 1 行表示して停止する。`body_template_path` 未宣言 Step が簡易プロンプトを使う挙動は従来どおり維持。
- 製品 run 中の focused pytest 起動（`FR-CLI-72`）。Step 1.2 のローカル検証は `bash -n` / ShellCheck / artifact validator / LF・BOM の静的検査に限定した（[hve/asdw_step12_verification.py](hve/asdw_step12_verification.py)）。
- ASDW-WEB Step 1.3 の native 化（`execute_pipeline`）により到達不能だった DataDeploy 専用の permission handler / session / MCP 検証コード。`_build_asdw_data_deploy_permission_handler`、`_verify_asdw_data_deploy_session_mcp_servers`、permission ヘルパー 16 個、専用状態辞書 5 種、関連定数 9 種を削除した。[hve/runner.py](hve/runner.py) は 8,129 → 6,925 行（正味 −1,204 行）。一般 Step の permission handler と MCP routing は不変。
- Cloud dispatcher からの ASDW-WEB 起動（`FR-CLOUD-06`）。[.github/workflows/auto-app-dev-microservice-web-reusable.yml](.github/workflows/auto-app-dev-microservice-web-reusable.yml) は自ら `OUT-OF-SYNC NOTICE` を宣言しており registry と Step 体系が一致しないため、dispatcher の該当ジョブを削除し、CLI / GUI（`python -m hve orchestrate --workflow asdw-web`）が supported である旨を Issue コメントで通知する。**他の 9 workflow の dispatch は不変**。reusable YAML 自体は削除していない。

#### Fixed

- io-contract 整合性 CI の hard-fail 経路（`validate-io-contract.py --no-registry-check`）が exit 1 だった問題。YAML parse error 6 件と producer 宣言不整合 41 件を解消し **exit 0** にした。
- ASDW-WEB Step 1.3 の旧 Agent 経路を前提にした "fake production-path" E2E テストを、native pipeline の実境界（generator → `execute_pipeline` → `StageResult` → HVE evidence → return）を検証する内容へ置換した（[hve/tests/test_asdw_data_production_path_e2e.py](hve/tests/test_asdw_data_production_path_e2e.py)）。

#### 既知の制約

- registry mismatch 126 件は warning-only のまま残る。内訳は `knowledge/` 副次成果物、`{key}` と `{screenId}` 等のプレースホルダ命名差、`{serviceId}-{serviceNameSlug}` のような二重プレースホルダ、ディレクトリ参照、条件付き生成物。`output_paths_template` が単一プレースホルダ置換しか対応しないという構造的制約に起因するため、CI の registry-check 必須化は見送った（恒常的に赤くなるため）。
- **`output_paths` の宣言が Self-Improve の target scope を無言で縮小させる問題が判明した**。`run_workflow` は `collect_workflow_output_paths` が非空を返すと `SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS` のディレクトリ既定を使わずパス直指定へ切り替わるが、当該 collector は fan-out 展開を AAG / AAGD にしか適用しない。そのため ADFDV / AKM / AAGD へ部分宣言を追加すると scope が `"."` / `"knowledge/"` から数ファイルへ縮小される。本変更では当該 3 workflow の宣言を見送り、理由を `ALLOWED_EMPTY_OUTPUT_PATHS_STEPS` のコメントへ記録した。collector の fan-out 展開を全 workflow へ拡げるか、scope 解決を部分宣言に対応させるかは別タスクとする。
- `docs/dataflow/` の 4 ドキュメントは producer Agent（`Arch-Dataflow-ServiceCatalog` 等）がリポジトリに存在しないため、[.github/io-contract-exceptions.yaml](.github/io-contract-exceptions.yaml) へ暫定的に例外登録した。当該 Agent 追加時に例外を削除して producer 宣言へ戻すこと。

### Changed — ASDW-WEB の必須入力を「Azure リソースグループ名」1 件へ縮約し、Azure リソース名を APP-ID から導出

**概要**: GUI / CLI で ASDW-WEB を実行する際、`data_verify_aci_image`（検証 ACI イメージ参照）が必須入力になっていた。Azure リソースがまだ 1 つも作成されていない初回実行時には設定できる値が存在せず、矛盾した要求になっていた。Step 1.3 が必要とするその他の Azure リソース名・リソース ID・エンドポイントも HVE 起動プロセスの環境変数に依存しており、利用者が事前に決めて export する必要があった。必須入力を Azure リソースグループ名だけに減らし、残りはすべて APP-ID 由来の suffix から HVE が決定論的に導出するようにした。

#### Added

- 検証／登録 ACI 用イメージの Dockerfile ([src/infra/azure/data-verify/Dockerfile](src/infra/azure/data-verify/Dockerfile))。`mssql-python` / `azure-cosmos` / `azure-identity` / `azure-confidentialledger` をバージョン固定で同梱し、validator の必須パッケージ定義を SSOT として参照する。
- prep stage が Azure Container Registry（Basic SKU）を作成し、`az acr build` で上記イメージをビルドしてデプロイ用マネージド ID に `acrpull` を付与する処理 ([hve/asdw_data_script_generator.py](hve/asdw_data_script_generator.py))。ACI 側は `--acr-identity` でユーザー割り当て ID を用いて pull する。
- `RESOURCE_GROUP` / `RESOURCE_SUFFIX` / `SUBSCRIPTION_ID` から Azure リソース名・サブネット ID・マネージド ID リソース ID・SQL / Cosmos / Confidential Ledger のエンドポイントを導出する処理 ([hve/asdw_data_runtime_context.py](hve/asdw_data_runtime_context.py))。`SUBSCRIPTION_ID` は `az account show` から解決する ([hve/runner.py](hve/runner.py))。
- Azure が採番する `DATA_DEPLOY_IDENTITY_CLIENT_ID` を prep stage 成功後に `az identity show --query clientId` で読み戻し、後続 stage へ注入する処理 ([hve/asdw_data_script_launcher.py](hve/asdw_data_script_launcher.py))。

#### Changed

- ASDW-WEB Step 1.3 の `required_params` を 7 件から 6 件へ削減し、既定値を持たない入力は `resource_group` のみとした ([hve/workflow_registry.py](hve/workflow_registry.py))。
- `data_resource_suffix` の既定値を APP-ID 定数から導出し、リテラルの二重管理を解消した ([hve/workflow_registry.py](hve/workflow_registry.py) `asdw_data_deploy_resource_suffix`)。
- 検証イメージ参照 `DATA_VERIFY_ACI_IMAGE` を入力ではなく導出値に変更した。レジストリ名は Azure のグローバル一意制約に合わせ、デプロイスコープのダイジェストを付与して導出する。
- ネットワーク契約の正本 ([asdw-data-verifier-contract.md](.github/skills/azure-skills/azure-cli-deploy-scripts/references/asdw-data-verifier-contract.md)) に、導出キーの出所・prep stage のレジストリ所有・stage 間読み戻し規定を追記した。
- 要件定義とテストマッピング ([hve-dev/requirement-definition.md](hve-dev/requirement-definition.md) / [hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md)) を新しいパラメータ契約（FR-WF-ASDW-01 〜 03）へ更新し、インベントリ CSV を再生成した。

#### Removed

- GUI の「DataDeploy verify ACI image」入力欄と説明文、設定永続化キー ([hve/gui/page_options.py](hve/gui/page_options.py) / [hve/gui/settings_apply.py](hve/gui/settings_apply.py) / [hve/gui/settings_store.py](hve/gui/settings_store.py) / [hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py))。
- CLI フラグ `--data-verify-aci-image` と対応するパラメータ収集経路 ([hve/\_\_main\_\_.py](hve/__main__.py) / [hve/orchestrator.py](hve/orchestrator.py))。

### Fixed — ASDW-WEB を local-first / live-last 化し、Step.1.3 の実行・証跡・成果物保持を HVE 所有へ恒久修正

**概要（symptom）**: ASDW-WEB は Step.1.3（`Dev-Microservice-Azure-DataDeploy`）が直列 DAG の 3 番目にあり、Azure live deploy が失敗するとその後の API / UI 生成に到達できず、ユーザーのアプリケーション生成が丸ごと停止していた。加えて Step.1.3 の実行と証跡が Agent 著作に依存しており、未到達 stage の PASS 自己申告、launcher stage の個別要求、成果物欠落状態での commit / push を構造的に防げなかった。

**root cause**: (1) DAG が `1.1 → 1.2 → 1.3 → 2.1 → …` の完全直列で、live deploy が local 生成の前段にあった。(2) Step.1.3 の bootstrap 値が ambient env / source-tree `data-deploy.env` に依存し、pipeline 実行順序と証跡が Agent 側に委ねられていた。(3) local 生成物の消失を検出して stage / commit / push を止める仕組みが無く、live 失敗時に checkpoint 成果物を保持する経路も無かった。

- **明示 bootstrap context** ([hve/asdw_data_runtime_context.py](hve/asdw_data_runtime_context.py)): LOCATION / RESOURCE_SUFFIX / 3 CIDR / ACI image / RESOURCE_GROUP を strict 検証（型・CIDR 包含・重複・image credential）付きで CLI / GUI / Runner へ immutable に伝播し、ambient 値より優先する。必須値が欠ける場合は Azure write 前に停止する。
- **resource lifecycle の閉包** ([hve/asdw_data_script_generator.py](hve/asdw_data_script_generator.py)): renderer が後段で参照する SQL DB（SVC01/02/03/07/09、SVC12 は sql-ledger-digest のみ）・Cosmos・Private DNS zone / link・Private Endpoint・DNS zone group を実際に作成する順序で生成する。tracked producer は HVE の lock / snapshot / validate / promote transaction で再生成し、手編集しない。
- **launcher の環境隔離と HVE 所有 pipeline** ([hve/asdw_data_script_launcher.py](hve/asdw_data_script_launcher.py)): child env を denylist から明示 allowlist へ変更し、PATH を固定、`DATA_DEPLOY_ENV` と run-context env の子伝播を遮断。`execute_pipeline()` が prep → create → registration → verify → create → registration → verify の 7 stage を単一 lock 下で固定順に実行し、途中失敗で後段を起動しない `StageResult` を返す。
- **StageResult 正本の HVE 所有証跡** ([hve/runner.py](hve/runner.py)): APP-009 Step.1.3 を SDK セッション起動前に native pipeline へ分岐し、`work-status.md` / `ac-verification.md` / GREEN `tdd-test-report.md` を StageResult のみを根拠に atomic 生成する（AC-1 = 全 7 stage 成功、AC-2 = create/registration の attempt 1・2、AC-3 = verify の attempt 1・2 を個別判定）。未到達 stage・未実行 verify を PASS / ✅ にできない。I/O contract は `owner: hve` / `evidence_source: stage_results` で宣言する。
- **Agent 責務の縮約** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md) / [.github/scripts/templates/asdw-web/step-1.3.md](.github/scripts/templates/asdw-web/step-1.3.md)): generator / launcher / pipeline / evidence / Agent の実行責務を本 Step で 1 回だけ定義し、Agent による launcher stage 要求と証跡の新規作成・上書き・訂正の記述を削除した。
- **local-first / live-last DAG** ([hve/workflow_registry.py](hve/workflow_registry.py)): local 生成（1.1 / 1.2 / 2.1 / 2.3 / 3.1 / 3.2 / 3.3 / 4.1 / 4.2）を完了させてから live deploy（1.3 / 2.2 / 2.4 / 3.4 / 3.5 / 4.3 / 4.4 / 5.x）へ進む DAG へ再構成し、`max_parallel=1` で同一 worktree の true parallel を避ける。Step.2.3 は deploy 済みリソースではなく Step.2.1 の設計から baseline integration test を生成し（Deploy 前の FAIL を正常な RED として扱う）、Step.3.1 は live service catalog ではなく `azure-services-data.md` の planned design を入力にする。
- **protected artifact guard** ([hve/orchestrator.py](hve/orchestrator.py)): local generation checkpoint 時点の `src/api` / `src/app` / `src/test` を manifest 化し、保護ルートの全消失または成功済み local 出力の欠落を検出したら **`git add` より前に** stage / commit / push を拒否する（index を事故状態にしない）。全 commit/push 経路へ接続済み。
- **local checkpoint retention** ([hve/orchestrator.py](hve/orchestrator.py) / [hve/github_api.py](hve/github_api.py)): live フェーズだけが失敗した run は checkpoint 成果物を破棄せず draft PR として残し、検証マーカーと `auto-approve-ready` ラベルを付けない（live 未達を auto-merge しない）。失敗時 PR cleanup は checkpoint PR に適用しない。
- **top-level import 経路の修復** ([hve/asdw_data_script_launcher.py](hve/asdw_data_script_launcher.py)): launcher が無条件の相対 import を持ち、`hve/` を `sys.path` に置く top-level runner 互換経路が `ImportError` で壊れていた（13 テストモジュールが collection error）。`hve/runner.py` と同じ二重 import へ揃えて修復した。
- **real verification**: focused suite（generator / launcher / runtime context / pipeline / evidence / registry / guard / retention / production path）はすべて PASS。broad full-suite は **5869 passed / 12 failed**。この 12 failed は本修正着手前の base（`39fdb788^` = `f66d58b7`）を一時 worktree で実行しても**同一の 12 件が失敗する pre-existing かつ本修正と無関係な別領域**であり、新規 regression は **0 件**。`docs/**` 変更 0、`src/**` の手編集 0（producer は HVE 再生成のみ）、新規依存 0。
- **live not run**: Azure CLI / Azure REST / live Azure 操作および実 GUI での ASDW-WEB end-to-end 完走は未実行（ユーザー起動が必要な外部ゲート）。本修正の検証はすべて static / local（pytest・fake process・byte 検査）に限定し、production path E2E は clean な一時ツリー上で本物の `DAGExecutor` を Agent セッションのみ fake にして駆動している。

### Fixed — ASDW-WEB Step.1.2/1.3 の contract-generation 反復停止を、producer 生成 + Step.1.2 証跡 + reject provenance の3層で恒久修正

**概要（symptom）**: ASDW-WEB の Step.1.2（`Dev-Microservice-Azure-DataTestCoding`）と Step.1.3（`Dev-Microservice-Azure-DataDeploy`）が、（a）committed 済みの stale な data producer スクリプトを agent が手直ししようとして書込境界で拒否され停止、（b）静的契約 PASS を live RED 実行として提示する／nonzero focused pytest を単一 PASS に畳み込む証跡の曖昧化、（c）Copilot SDK が `create` / `edit` 短縮別名で write を通知した際に provenance に write が記録されず、拒否理由の追跡不能で反復停止、という複合要因で繰り返し停止していた。本修正は HVE が制御可能な3層（producer の HVE 所有生成・Step.1.2 の三状態証跡・Step.1.3 reject の構造化 provenance）に絞って恒久対処する。

**root cause**: (1) producer スクリプトが agent 著作・手動 promote 前提で、生成契約から drift しても検出・再生成する HVE 所有経路が無かった。(2) Step.1.2 の TDD レポートに「成果物契約」「live RED」「focused 回帰」を分離する機械検証の source of truth が無く、静的 PASS と live 実行が混同し得た。(3) file-tracking の tool 分類に SDK 短縮別名（`create` / `edit` / `view`）が欠落し、write が read として誤分類され provenance が欠損。加えて Step.1.3 の権限 reject が構造化された起点情報を残さず、反復停止の真因追跡が困難だった。

- **Producer の HVE 所有生成・promote・read-only 化** ([hve/asdw_data_script_generator.py](hve/asdw_data_script_generator.py) 他): data producer（`create-azure-data-resources-prep.sh` / `create-azure-data-resources.sh` / `data-registration-script.sh`）を HVE がセッション開始前に生成・byte-pinned に promote する経路を追加し、tracked producer を生成器出力へ移行（byte-identical）。runtime env は HVE 所有キーとして凍結し、agent の write 越境を fail-closed に拒否する。
- **Step.1.2 三状態証跡** ([hve/artifact_validation.py](hve/artifact_validation.py) / [hve/asdw_step12_verification.py](hve/asdw_step12_verification.py) / [hve/runner.py](hve/runner.py)): `Artifact-Contract-Status` / `Live-RED-Status` / `Focused-Regression-Status` の三状態ラベルを導入。HVE 所有の local verifier（`bash -n` → ShellCheck(任意) → artifact validator → LF/BOM → focused pytest を最後に固定順で実行）が権威的な machine-verification.log を生成し、レポートのラベルがログと不一致なら gate が拒否する。静的契約 PASS を live RED 実行として提示できず、nonzero focused pytest を単一 PASS に畳み込めない。prompt / template / skill も三状態契約へ整合。
- **I/O provenance（SDK 別名分類 + reject origin event）** ([hve/runner.py](hve/runner.py) / [hve/console.py](hve/console.py)): file-tracking の tool 分類に SDK 短縮別名を追加（`create` = write、`edit` = read+write、`view` = read）。既存 `create_file` / `edit_file` / `apply_patch` の挙動は不変。加えて Step.1.3 の権限 reject が、生の command / path / URL / secret を含まない固定スキーマの origin event（origin=hve-policy、decision=reject、canonical reason code、任意の sanitized tool_call_id）を1回だけ発行する（`Console.permission_reject_event`）。event 発行の失敗が権限判定を fail-open させないよう握り潰し、reject 判定・feedback は不変。
- **real verification**: 統合ブランチで producer + evidence を競合なく統合し、統合回帰 **639 passed / 7 skipped**。focused suite（generator / launcher / Runner / permission / contracts / evidence / provenance）**1500 passed / 7 skipped**。3 validator（create / registration / verify）を現行 tracked producer に対し **PASS**、4 producer の `bash -n` / ShellCheck / LF・BOM いずれも OK。broad full-suite は **5678 passed / 4 failed**。この 4 failed はいずれも base（`cc9451bf`、本修正着手前）でも失敗する **pre-existing かつ本 3 層修正と無関係な別領域**（SWA workflow 未生成 `test_app009_swa_workflow_exists...`、network 契約宣言 `test_network_env_contract_declaration_is_exact`、fanout meta 転送 `test_aad_web_fanout...`、Step 1.3 verify 契約順序 `test_asdw_data_deploy_verify_contract_fails_before_sdk_import`）。加えて、full-suite でのみ顕在化していた **順序依存の 15 失敗**（launcher 11・deploy-gate 4：production の run-context env 副作用 `HVE_RUN_ID` / `HVE_WORK_ROOT` が後続テストへリーク）を autouse conftest fixture（[hve/tests/conftest.py](hve/tests/conftest.py)）による run-context env の復元で解消し、producer 生成が Step 1.3 の env snapshot 必須化で崩した外部スキル分離テスト1件（`test_asdw_data_deploy_keeps_external_skill...`、base では PASS）も snapshot スタブで修復した（本 change set 起因の regression）。差分は root README / docs / 依存 / manifest 無変更、実 secret 混入なし、commit 済み blob は LF・BOM なし。
- **live not run**: Azure CLI / Azure REST / live Azure 操作・実 GUI の ASDW-WEB end-to-end 完走はいずれも未実行（ユーザー起動が必要な外部ゲート）。本修正の検証はすべて static / local（pytest・bash -n・ShellCheck・validator・byte 検査）に限定。

### Fixed — ASDW-WEB Step.1.3 の data-deploy.env 生成契約を launcher で検証し RC-1 の end-to-end ギャップを閉じる

**概要**: RC-1 修正で launcher が verify 用に `data-deploy.env` を supply するようにしたが、その `data-deploy.env` が verifier の必要キーを**完備しているか検証する仕組みが無かった**問題を修正した。調査で、(1) create/prep スクリプトは host-boundary grammar（`[ERROR]` printf・`az` コマンド・`: "${KEY:?}"`・固定 ACI ライフサイクルのみ許可、executable 全体を shebang 直後の marker block に限定）により `data-deploy.env` を**構造的に書けない**、(2) `data-deploy.env` は **agent が write tool で著作する** artifact（DataDeploy prompt/template の「data-deploy.env 契約」）、(3) network 契約キーの SSOT は skill `asdw-data-verifier-contract.md` であり prompt/template への複製は既存テスト `test_prompt_and_template_consume_the_shared_network_contract` が禁止、を確認した。前回の RC-1 開示「create script が data-deploy.env を書く」は不正確で、正しくは「agent が著作し、その完全性を検証する仕組みが欠落」だった。

- **Launcher content check** ([hve/asdw_data_script_launcher.py](hve/asdw_data_script_launcher.py)): `_load_data_deploy_environment`（verify stage で `data-deploy.env` を child env へ供給する RC-1 経路）に新設 `_require_data_deploy_verify_keys()` を追加。`DATA_NETWORK_MODE` の存在を必須化し、`private` mode では network 契約11キー（SSOT `_ASDW_DATA_DEPLOY_NETWORK_KEYS` を artifact_validation から import して重複回避）＋承認済み検証イメージ `DATA_VERIFY_ACI_IMAGE` の充足を fail-closed で検証する。欠落時は consolidated な `ScriptLauncherError` を送出し、「Step 1.3 が `data-deploy.env` に書き出すべき env 契約欠陥であり verify-script bug ではない」と明示（cryptic な unbound-variable 失敗が verifier 内部深くで出るのを防ぎ、agent の誤修正＝Step 1.2 責務への越境を抑止）。`DATA_VERIFY_RUN_ID` は launcher が生成するため要求しない。
- **契約 SSOT の明確化（skill）** ([.github/skills/azure-skills/azure-cli-deploy-scripts/references/asdw-data-verifier-contract.md](.github/skills/azure-skills/azure-cli-deploy-scripts/references/asdw-data-verifier-contract.md)): §Step 1.3 DataDeploy network contract に、DataDeploy step が network 契約キー（`private` mode では11キー）＋`DATA_VERIFY_ACI_IMAGE` を `data-deploy.env` に**書き出し**、制御ホスト（launcher）が verify 起動前に export する旨を明記（従来は「consume する」のみで書き手が曖昧だった）。`DATA_VERIFY_RUN_ID` は launcher 生成のため書き出さないことも明記。network キーの SSOT は skill に一元化し prompt/template には複製しない。
- **Tests** ([hve/tests/test_asdw_data_script_launcher.py](hve/tests/test_asdw_data_script_launcher.py)): content check の RED/GREEN（`DATA_NETWORK_MODE` 欠落・private 必須キー欠落・欠落キーの consolidated 列挙＋`DATA_VERIFY_RUN_ID` 非要求・public mode での network キー非要求・完全 private の通過）を追加（5件）。RC-1 で private mode を使う既存3テストを完全 `data-deploy.env` fixture（ヘルパー `_write_complete_data_deploy_env`）へ更新。
- **非対象・開示（意図的にスコープ外）**:
  - **prompt/template への network キー追加は不採用**（初回試行を敵対的レビューで撤回）。既存テスト `test_prompt_and_template_consume_the_shared_network_contract` が network キーの prompt/template 複製を禁止し、SSOT は skill と規定するため。network 契約は skill に既存で、agent は skill 参照で認知する。
  - **create の network キー入力供給**（create が `${DATA_VNET_NAME:?}` 等を入力として要求する値の供給元）は、本タスクの「data-deploy.env 内容の生成契約検証」とは別層の深い設計課題として未解決のまま開示する。verify 側の env 供給（RC-1）と content 検証（本修正）は完了。
- **検証**: `hve/tests/test_asdw_data_script_launcher.py` **35 passed / 2 skipped**（新規5・fixture 更新3含む）、影響範囲回帰（`test_runner_deploy_gate_order` / `test_asdw_data_private_verify_validation` / `test_asdw_data_create_validation` / `test_asdw_data_registration_audit_mode` / `test_asdw_data_contract_ssot` / `test_asdw_data_deploy_policy_contract` / `test_asdw_web_data_deploy_contract`）合算 **811 passed / 2 skipped**。SSOT テストで prompt/template への network キー非複製を再確認。Azure CLI / REST / live Azure 操作は未実行。

### Fixed — ASDW-WEB Step.1.3 の launcher が verify 契約の caller 役割を履行し RC-1（sanctioned launcher 経路の env 供給ギャップ）を解消

**概要**: ASDW-WEB Step.1.3（`Dev-Microservice-Azure-DataDeploy`）の唯一の sanctioned な script 実行経路 `python -m hve.asdw_data_script_launcher <stage>` が、必要な環境変数を取得できず構造的に実行不能だった問題（RC-1）を、launcher が verify 契約の "caller" 役割を履行するよう修正した。調査（前タスク T0）で、(1) launcher の create/registration/verify stage は `DATA_{CREATE,REGISTER,VERIFY}_RUN_ID`（32桁小文字16進）を実行前に必須検証するが、これを生成・export する sanctioned 経路が hve・scripts のいずれにも存在せず launcher が自身の precondition で fail、(2) `verify-data-resources.sh` は `DATA_NETWORK_MODE` / network 11キー / Resource 名キーを環境変数として要求するが `data-deploy.env` を自読込しない（契約通り）一方、launcher も同ファイルを供給しない、という二重の env 供給ギャップを確認していた。verifier 契約（[asdw-data-verifier-contract.md](.github/skills/azure-skills/azure-cli-deploy-scripts/references/asdw-data-verifier-contract.md) §`private` mode）は「呼出し側が `data-deploy.env` を読み込み、network 11キー・`DATA_VERIFY_ACI_IMAGE`・生成した `DATA_VERIFY_RUN_ID`・Resource 名キーを export して verifier を起動する。verifier 自身は `data-deploy.env` を読み込まない」と規定しており、その "呼出し側"＝launcher がこの役割を未履行だったのが RC-1 の本質である。

- **Launcher** ([hve/asdw_data_script_launcher.py](hve/asdw_data_script_launcher.py)):
  - `execute_stage` に stage run-id の**生成**を追加。`DATA_{stage}_RUN_ID` が env に無い／不正な場合、`secrets.token_hex(16)`（32桁小文字16進）を child env に供給する（`^[0-9a-f]{32}$` に一致）。既に有効な値が env にある場合はそのまま使う（外部 override 可）。これにより launcher が自身の caller 役割として run-id を提供し、外部 step の export を不要にする。
  - `verify` stage に限り、新設 `_load_data_deploy_environment()` で `src/infra/azure/data-deploy.env` を**in-process で厳密 `KEY=VALUE` パース**（`shell source` を使わない）して child env へ merge。`_read_stable_utf8_file` による TOCTOU-safe な path 検証（repo 相対・regular file・symlink/reparse/hardlink 拒否・BOM/CRLF 拒否）を経由し、`PATH` / `BASH_ENV` / `LD_*` 等の loader/PATH injection knob を fail-closed で拒否、malformed 行・NUL 値も拒否する。merge は launcher 所有キー（`HVE_ASDW_*`）と run-id 生成の**前**に行い、`data-deploy.env` がそれらや `PATH` を上書きできないようにした。`registration` は自身で `data-deploy.env` を読むため対象外、`create`/`prep` は base 入力に既定値を持つため対象外。
  - module docstring を「env file を source しない」から caller 役割（run-id 生成・verify での `data-deploy.env` in-process 供給・loader knob 拒否）へ更新した。
- **Tests** ([hve/tests/test_asdw_data_script_launcher.py](hve/tests/test_asdw_data_script_launcher.py)): run-id 未設定時の raise を期待していた `test_launcher_requires_a_safe_stage_run_id` を、生成挙動を固定する `test_launcher_generates_stage_run_id_when_absent`（create/registration）＋外部有効 run-id の非上書き・verify の `data-deploy.env` 供給・launcher 所有キー非上書き・loader の forbidden key/malformed 行拒否の各テストへ置換／追加（6件）。verify を完走させる既存 predecessor テストに `data-deploy.env` セットアップを追加した。
- **非対象・開示（意図的にスコープ外）**:
  - 本修正は **launcher（呼出し側）の env 供給ギャップ**を解消する。end-to-end で verify が GREEN になるには、`create-azure-data-resources.sh` が verifier 契約の network 11キー・`DATA_VERIFY_ACI_IMAGE`・Resource 名キーを `data-deploy.env` に**書き出す**ことが追加で必要である。現行 committed の create script（public/legacy 由来）はこれら network 変数を書いていないが、`src/` スクリプトは毎 run agent が再生成する対象であり、private mode で契約準拠に再生成された create script が同ファイルを完備すれば launcher がそれを供給する。create script の生成契約（何を `data-deploy.env` に書くか）は本タスクのスコープ外とし、必要なら別タスクで検証・整備する。
  - run-id を stage 間で共有・永続化しない（各 stage の run-scoped ACI 命名／所有タグは one-shot 用途のため per-invocation 生成で十分）。
- **検証**: `hve/tests/test_asdw_data_script_launcher.py` **30 passed / 2 skipped**（置換1・新規5含む）、影響範囲回帰（`test_runner_deploy_gate_order` / `test_asdw_data_private_verify_validation` / `test_asdw_data_create_validation` / `test_asdw_data_registration_audit_mode` / `test_asdw_data_contract_ssot`）合算 **735 passed / 2 skipped**。security 境界（forbidden key/PATH/symlink/TOCTOU/Bash startup hook 除去）は既存テストで不変を確認。Azure CLI / REST / live Azure 操作は未実行。実 GUI の end-to-end 完走はユーザー起動＋契約準拠 create script の外部ゲート。

### Fixed — ASDW-WEB Step.1.3 が GREEN `tdd-test-report.md` 未生成と launcher 誤認で `tdd-test-report.md not found` 停止する問題を Prompt/template で緩和

**概要**: ASDW-WEB Step.1.3（`Dev-Microservice-Azure-DataDeploy`）が `tdd-test-report.md not found` で workflow を停止した事象（run `20260722T220318-c8d503`）を、HVE 側で制御可能な**生成契約（Prompt/template）**に絞って緩和した。実測の直接原因は、(1) agent が `Get-ChildItem` / `Join-Path` の path-resolution glitch で HVE 所有 launcher を「不在」と誤認し（launcher は実在）、canonical launcher を一度も要求せず `bash` 直接実行（gate が正しく拒否）へ逸れた、(2) その後 "envelope" メタファーの injection 風メタ会話へ約8分脱線し、Step.1.3 全体で `Files: 3 read, 1 written`（実書込1件のみ）のまま `assistant.idle` でターン終了、canonical GREEN `tdd-test-report.md` を生成しなかった、という連鎖である。gate（permission / artifact）の挙動は設計通りで欠陥ではない。model 側の hallucinated write / injection 脱線は Copilot SDK / モデル側要因のため（[CHANGELOG.md](CHANGELOG.md) 既往どおり YAGNI）本修正の対象外とし、唯一の HVE 制御レバーである「必須成果物の前倒し・ターン終了強制」と「launcher 直接呼び出し規律」に絞る。

- **生成契約（Prompt）** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md)):
  - ステップ0.5（必須証跡スタブ）・ステップ0.6（verify 直後の最優先確定）・成果物作成の必須化（ターン終了前）・AC-1 ❌ 即終了、の各規則に GREEN `tdd-test-report.md` を追加。ac-verification.md と同じく早期スタブ→verify outcome 確定直後に最優先で確定させ、**依頼外／メタ的な会話（HVE 内部実装・shell boundary の考察等）への応答より前に** finalize することを明記した。判定値は validator 仕様（GREEN は `TDD-Judgement ∈ {PASS, BLOCKED}`・`Evidence-Status: EXECUTED`、`FAIL` は拒否）に整合させ、GREEN 達成時 `PASS`／未達時 `BLOCKED` と規定。
  - shell 境界・ASDW DataDeploy network contract に「launcher の直接呼び出し（存在 probe 禁止）」規律を追加。launcher モジュール／スクリプトの**ファイル存在を shell で probe しない**（`Get-ChildItem` / `Test-Path` / `ls` / `dir` 等を発行せず直接 `python -m hve.asdw_data_script_launcher <stage>` を要求）、失敗時（モジュール不在・run-id / 環境変数不足・契約エラー等いずれでも）は `bash` / `./` 直接実行や手動 `az` 代替検証へ**フォールバックせず**、環境ブロッカーとして AC-1 `❌` / `tdd-test-report.md` `TDD-Judgement: BLOCKED` で証跡付き fail 終了する、と規定した。
- **生成契約（Template）** ([.github/scripts/templates/asdw-web/step-1.3.md](.github/scripts/templates/asdw-web/step-1.3.md)): TDD GREEN フロー（step 2 の必須スタブ、step 4 の verify 直後確定、step 5 の即終了）・完了条件に GREEN `tdd-test-report.md`（PASS/BLOCKED）を対称化し、step 3 に launcher 存在 probe 禁止・フォールバック禁止のサブバレットを追加した。レポートのフルパス宣言は `## TDD テスト結果レポート（必須）` 節の1回のみに保ち（既存 SSOT 不変条件を維持）、追加箇所はファイル名参照＋節への相互参照とした。
- **Tests** ([hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)): GREEN `tdd-test-report.md` の必須スタブ／verify 直後確定／ターン終了強制（prompt・template）と、launcher 直接呼び出し・存在 probe 禁止・フォールバック禁止（prompt・template）を固定する契約テストを追加（4件）。既存 `test_data_deploy_prompt_finalizes_ac_verification_before_other_work` のアサーションを 0.6 の新文言（`他作業・会話へ進まない` / 依頼外応答より前）へ更新した。
- **非対象（意図的に除外・理由付き）**:
  - **launcher の env 供給修正（RC-1）**: 調査で launcher の verify/registration/create stage が `DATA_{VERIFY,REGISTER,CREATE}_RUN_ID`（32hex）＋ `data-deploy.env` 変数を取得する sanctioned 経路を持たない（launcher が verify 契約の "caller" 役割＝env source・run-id 生成・network context 供給を未履行）ことを確認した。これは launcher を caller として完成させる複数部品の変更で `DATA_NETWORK_MODE` 供給元に未確定部分が残るため、別スコープの保留項目とした。本修正の launcher 直接呼び出し規律は、当該 env ギャップで launcher が失敗しても flailing / hijack ではなく**証跡付き clean 終端**へ変える（完走には RC-1 修正が別途必要）。
  - **model 側 glitch の HVE 検出機構**（hallucinated write / 0-written リトライ / injection 検出）: [CHANGELOG.md](CHANGELOG.md) 既往で YAGNI・機序未確定と disposition 済みのため追加しない。
  - **`_REQUIRED_DIRS` への GREEN dir 追加**: 本 run の致命は dir 不在ではなく無書込であり（write gate は当該パスを既に許可）、予防追加は YAGNI。
  - **permission fixture の実 SDK replay 拡張（RC-3）**: 本 run で「全 shell 一律拒否」は未再現（Step.1.1 shell approved）のため別課題。
- **検証**: `hve/tests/test_asdw_web_data_deploy_contract.py` **54 passed**（新規4件・更新1件含む）、DataDeploy prompt/template を参照する関連回帰（`test_tdd_test_report_contract` / `test_tdd_green_retry_contract` / `test_generated_test_runtime_contract` / `test_asdw_data_deploy_policy_contract` / `r03_prompt_review_inline_contract`）合算 **152 passed**。フルパス1回制限の不変条件（`test_asdw_data_deploy_report_path_override_is_exact_and_limited`）も維持。既存の pre-existing 失敗 `test_asdw_web_step_scoped_cicd_contract.py::test_app009_swa_workflow_exists_and_uses_oidc_dynamic_token` は `.github/workflows/azure-static-web-apps-app009.yml` 不在によるもので本修正と無関係（SWA workflow 未生成・別系統）。Azure CLI / REST / live Azure 操作は未実行。実 GUI の ASDW-WEB Step.1.3 完走確認はユーザー起動が必要な外部ゲートとして未実施。hve アプリケーションコード（`runner.py` / `asdw_data_script_launcher.py` 等）は変更なし（gate / launcher は正常動作。変更は Prompt/template と契約テストのみ）。

### Fixed — ASDW-WEB Step.1.2 が既存 verifier の手読み監査中のターン終了で 0-written 停止する問題を出力前倒しで緩和

**概要**: ASDW-WEB Step.1.2（`Dev-Microservice-Azure-DataTestCoding`）が、既存 `verify-data-resources.sh` を逐次手読みで精査中に、claude-opus-4.8 が `view` ツール呼び出しを**リテラルテキスト**（`<invoke name="view">…`）として最終本文に出力→ SDK が実ツール呼び出しを検出できず `assistant.idle` → `Files: 8 read, 0 written` でターン終了し、TDD report gate が `tdd-test-report.md not found` で停止した事象（run `20260722T153122-1bc283`）を、HVE 側で制御可能な**出力順序**に絞って緩和した。直接原因のリテラルツール呼び出しは SDK/モデル側の機序で、[CHANGELOG.md](CHANGELOG.md) 既往（「literal tool-call 混入のランタイム検出は機序未確定・HVE 検出可否不明・YAGNI」）どおり HVE では扱わない。唯一の HVE 制御レバーである「必須成果物の前倒し生成」を Step.1.2 の生成手順へ追加し、既存 verifier の適合性を逐次手読みでなく機械検証（`bash -n` / artifact validator / LF・BOM）で判定して、追加の手読みレビューより前に `static-verification.log` → `tdd-test-report.md` を確定させる。これにより成果物が存在するまでのターン数を縮小し、監査中のターン終了グリッチが 0-written を招く窓を狭める。

- **生成契約（Prompt）** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md)): §5.3 の先頭に「出力の前倒し（ターン終了グリッチ耐性・最優先）」規則を追加。必須成果物（`static-verification.log` → `tdd-test-report.md`）を早期確定し、既存 verifier の適合性は逐次手読みでの網羅精査ではなく `bash -n` / artifact validator（`hve.artifact_validation.validate_asdw_data_verify_script`）/ LF・BOM で機械判定、その直後にレポート（準拠・未変更なら `Test-Files-Changed: no`）を作成、stale・不適合なら再生成してから同順で確定、手読み監査は必須成果物作成後にのみ実施、と規定した。
- **生成契約（Template）** ([.github/scripts/templates/asdw-web/step-1.2.md](.github/scripts/templates/asdw-web/step-1.2.md)): `## TDD RED フロー（必須）` 見出し直後に「出力前倒し（最優先）」バレットを追加し、prompt と同方針（機械検証→ログ→レポートの早期確定）を対称化した。
- **Tests** ([hve/tests/test_asdw_data_testcoding_network_contract.py](hve/tests/test_asdw_data_testcoding_network_contract.py)): prompt/template の出力前倒し規則（機械検証・手読み監査の後置・早期レポート確定）の固有フレーズを固定する契約テストを追加した（1件）。
- **効果と限界**: 必須成果物が存在するまでのターン数を「手読み監査主体」→「機械検証＋書込み主体」へ短縮し、ターン終了グリッチが 0-written を招く窓を大幅に縮小する（本 run では適合確認からグリッチまでの窓で書けていれば通過できた）。ただしグリッチが書込みターンそのもので起きれば依然失敗する（緩和であり保証ではない）。直接原因は SDK/モデル側で HVE 制御外。
- **非対象（意図的に除外）**: (a) HVE 側のリテラルツール呼び出し検出／ターン継続・0-written リトライは [CHANGELOG.md](CHANGELOG.md) 既往で YAGNI・機序未確定と disposition 済みのため新規機構を追加しない。(b) out=32000 サーキットブレーカ・ツール不安定耐性は前回同様除外（今回は再発せず）。(c) 6 RED プロンプト全展開は観測失敗が Step.1.2 のみのため見送り。
- **検証**: `hve/tests/test_asdw_data_testcoding_network_contract.py` **202 passed**（新規1件含む）、関連回帰 `test_asdw_data_contract_ssot` / `test_generated_test_runtime_contract` / `test_tdd_red_green_reality_contract` / `test_tdd_test_report_contract` / `r03_prompt_review_inline_contract` / `test_asdw_data_private_verify_validation` / `test_prompt_loader` **296 passed**。既存破壊なし。hve コード変更なし（gate は正常動作・前回の診断 hint 済み）。実 GUI の ASDW-WEB Step.1.2 完走確認はユーザー起動が必要な外部ゲートとして未実施。
### Added — HVE 保守向けの選択的要件参照と PR トレーサビリティゲート

- `.github/skills/hve-requirement-traceability/SKILL.md`、HVEコアパス限定instructions、3行のrepository-wide routerを追加し、要求定義書全文の常時注入を避けながら、active要件・mapping・実在テストの選択的確認を固定した。
- `hve-dev` の機能変更順序と生成元を、要求 → mapping → RED → 索引照合 → 実装 → GREEN → 実結果反映へ同期し、要求・テスト索引を再生成した。featureゲートは両索引の更新を要求し、generatorはtrackedおよびnon-ignoredの未追跡テストを棚卸し対象にする。
- PRテンプレートの8キーblock、`.github/scripts/validate-hve-requirement-traceability.py`、read-only `pull_request` workflow、branch-protection check contextを追加した。validatorはパス境界、schema、active ID、mapping、許可テストパス、RED/GREEN証跡をfail-closedで検証し、symlinkをtest pathとして拒否する。さらに既定ブランチ文脈の`pull_request_target` trusted workflowを追加し、base側validatorとPR内容を別ディレクトリへcheckoutして、PRコードを実行せずデータとして検証する。
- **検証**: T03は **11 passed**、T04は **76 passed / 2 skipped**。Windowsでの2件のskipはsymlink作成権限不足による。trusted workflowのpost-merge分離シミュレーションもPASS。初回導入PRのマージ後、trusted checkを含むbranch protectionテンプレートをリモートmainへ再適用する必要がある。Azure CLI / REST / live Azure操作は実行していない。

### Fixed — ASDW-WEB Step.1.2 が RED 成果物を生成せず確認質問で終了し `tdd-test-report.md not found` で停止する問題を抑止

**概要**: ASDW-WEB Step.1.2（`Dev-Microservice-Azure-DataTestCoding`）が、既存 `verify-data-resources.sh` のレビュー中にツール不安定（view/grep/glob の断続失敗）で内容を捏造し、存在しない契約違反を巡る推論ループ（`out=32000` の空応答）に陥った末、非対話 GUI 実行にもかかわらず「進めてよいですか？」と確認質問して `Files: 0 written` のままターンを終え、TDD report gate が `tdd-test-report.md not found` で workflow を停止していた事象（run `20260722T085014-63e41d`）を、HVE 側で抑止可能な**終端挙動**に絞って修正した。deploy 系プロンプト6本が持つ「必須成果物未生成での終了禁止」規則が RED / TestCoding 系プロンプトに欠落していたギャップを埋め、非対話での確認質問終了と、既存 verifier の際限のない適合監査でのターン浪費を禁止する。ツール不安定・`out=32000` ループそのものは Copilot SDK 側要因のため本修正の対象外とし、非対象として記録する。

- **生成契約（Prompt）** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md)): §6 禁止事項の先頭に3規則を追加した。(1) `tdd-test-report.md` / `verify-data-resources.sh` / `static-verification.log` を作成しないままターンを終えない（RED 実行不能でも確認できた情報で verifier を生成し、レポートに `Evidence-Status: BLOCKED` / `TDD-Judgement: FAIL` と理由を記録して必ず作成）。(2) 非対話 Orchestrator 配下では確認質問で停止しない。ただし §4 依存確認による停止（`azure-services-data.md` / `app-catalog.md` 不在・空・解決不能）は正当な hard-stop で対象外とし、依存未達を推測補完しない。(3) 既存 verifier を安定読取できない場合は際限のない適合監査を続けず設計書＋契約から再生成する。
- **生成契約（Template）** ([.github/scripts/templates/asdw-web/step-1.2.md](.github/scripts/templates/asdw-web/step-1.2.md)): `## 完了条件` に未生成終了禁止のミラー行を追加し、`## 出力` に `tdd-test-report.md` と `static-verification.log` を列挙した。これによりローカル実行の `{completion_instruction}`（「上記の出力ファイルが全て正常に生成されていることを確認」）の自己完了チェックが RED レポート/ログを実効カバーする（deploy step-1.3 / step-2.2 の `## 出力` 対称化と同方式）。
- **Runner 診断** ([hve/runner.py](hve/runner.py)): `_run_tdd_report_gate` の `tdd-test-report.md not found` 診断に、無出力ターン終了を疑う actionable hint（ツール不安定による無出力・捏造・非対話での確認質問終了・推論ループへの脱線が無いか console-log を確認）を付した（`_run_deploy_ac_gate` の hint 方式をミラー）。GREEN / 状態判定ロジックは不変。
- **Tests** ([hve/tests/test_asdw_data_testcoding_network_contract.py](hve/tests/test_asdw_data_testcoding_network_contract.py), [hve/tests/test_runner_tdd_report_gate.py](hve/tests/test_runner_tdd_report_gate.py)): プロンプト3規則（§4 依存停止免除を含む）・テンプレートの完了条件ミラー行と `## 出力` 列挙・gate hint 固有フレーズを固定する契約/回帰テストを追加した（3件）。
- **非対象（意図的に除外）**: (a) ツール不安定（view/glob/PowerShell stdout の断続失敗）への hve 側耐性は Copilot SDK / セッションストア側で確実に制御不能なため除外。(b) `out=32000` サーキットブレーカは [CHANGELOG.md](CHANGELOG.md) 既往（run `20260611T001618`）で「初因未確定・修正は投機的」と disposition 済みのため新規機構を追加しない（YAGNI）。(c) 6 TestCoding プロンプト全展開は観測された失敗が Step.1.2 のみのため見送り、再発時に個別対応。(d)「全ストア報告 vs fail-fast」文言はプロンプト §5.1 で既に整合済みのため追記しない（捏造回避）。
- **検証**: `hve/tests/test_asdw_data_testcoding_network_contract.py` **201 passed**（新規2件含む）、`hve/tests/test_runner_tdd_report_gate.py` **60 passed / 2 skipped**（新規1件含む）、関連回帰 `test_asdw_data_private_verify_validation.py` / `test_asdw_data_skill_routing.py` / `test_prompt_loader.py` **230 passed**。Azure CLI / REST / live Azure 操作は未実行。実 GUI の ASDW-WEB Step.1.2 完走確認はユーザー起動が必要な外部ゲートとして未実施。

### Fixed — ASDW-WEB の非 data-deploy Step で `producer_phase_closed` 書き込みが KeyError で停止する回帰を修正

**概要**: ASDW-WEB の非 data-deploy Step（例: Step.1.1 `Dev-Microservice-Azure-DataDesign`）が、メインタスク完了直後に `KeyError: '1.1'` で失敗し workflow が blocked になる回帰を修正した。原因は [hve/runner.py](hve/runner.py) の producer 契約 gate 通過後に無条件実行される `self._asdw_data_deploy_producer_repair_states[str(step_id)]["producer_phase_closed"] = True` で、この辞書エントリは `if _is_data_deploy:` ガード内（entry 生成箇所）でしか作られないため、非 data-deploy Step では `[str(step_id)]` の読み取りが `KeyError` を送出していた（`str(KeyError('1.1'))` がログの `: '1.1'` に一致）。書き込みを `if _is_data_deploy:` でガードし、data-deploy 専用状態への無条件アクセスを解消する。`producer_phase_closed` は data-deploy launcher の permission handler だけが参照する状態のため、data-deploy Step の挙動は不変。

- **Runner** ([hve/runner.py](hve/runner.py)): メインタスク完了後の `producer_phase_closed` 書き込みを `if _is_data_deploy:` でガードした。data-deploy Step はエントリ生成箇所（同一ガード内）が先行実行済みで挙動不変、非 data-deploy Step はスキップして `KeyError` を解消する。
- **Tests** ([hve/tests/test_runner_deploy_gate_order.py](hve/tests/test_runner_deploy_gate_order.py)): `producer_phase_closed` 書き込みの直前が `if _is_data_deploy:` ガードであることをソース検査で固定する回帰テストを追加した（修正前 RED / 修正後 GREEN）。
- **検証**: `hve/tests/test_runner_deploy_gate_order.py` **259 passed**（追加テスト含む）。`hve/tests/test_runner.py` は **197 passed**、既存の pre-existing 失敗 `test_asdw_data_deploy_verify_contract_fails_before_sdk_import` 1 件のみで、本修正を temp-revert（`git stash`）しても同一失敗のため無関係と確認した。Azure CLI / REST / live Azure 操作は実行していない。

### Changed — ASDW-WEB Step.1.3 の producer gate を session 生成物限定にし、実 SDK 形状 permission と契約 SSOT の回帰を固定

**概要**: 恒久対策プラン v2 の確定必須3件を実装した。(1) Step.1.3 の post-main / final producer 契約 gate に `session_start` freshness ガードを追加し、当 step で再生成された producer script だけを検証する。pre-execution permission gate（`session_start=None`）は無条件検証を維持し、Azure 実行前の security 境界は不変。これにより agent が canonical launcher を実行せず終了した run で、stale な commit 済みスクリプトの契約エラーが真因（preflight / 環境ブロッカー）をマスクする問題を解消する。(2) 実 Copilot SDK 形状（full-command identifier / `request_sandbox_bypass=None` / PowerShell envelope）の permission replay テストを inspection 全種・launcher 全 stage・registration・非 canonical へ拡張し、合成 fixture が隠していた実互換バグを回帰検出する。(3) registration marker 定数と `static-verification.log` path の validator↔生成側 契約ドリフトを検出する SSOT テストを追加した。

- **Runner** ([hve/runner.py](hve/runner.py)): `_asdw_producer_script_is_session_output()` を新設し、`_run_asdw_data_producer_contract_gate()` に `session_start` を追加。post-main / final の 2 呼び出しは `session_start=start` を渡し、pre-execution permission 配線は無条件検証（security 境界）を維持する。
- **Tests** ([hve/tests/test_runner_deploy_gate_order.py](hve/tests/test_runner_deploy_gate_order.py), [hve/tests/test_artifact_validation_deploy_gate.py](hve/tests/test_artifact_validation_deploy_gate.py), [hve/tests/test_asdw_data_contract_ssot.py](hve/tests/test_asdw_data_contract_ssot.py)): 実 SDK 形状 permission replay（24件・直接19＋envelope 5）、producer gate freshness（helper / stale skip / fresh validate / 無条件 security / call-site 検査）、契約 SSOT ドリフト検出（4件）を追加した。
- **Producer state machine** ([hve/runner.py](hve/runner.py), [.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md), [.github/scripts/templates/asdw-web/step-1.3.md](.github/scripts/templates/asdw-web/step-1.3.md)): Step.1.3 の prep/create/registration を Azure launcher 前に一括検証し、いずれの launcher も未承認の初回不適合だけを `prep` から一度修復できる状態へ限定した。repair pending 中は prep 以外の create/registration/verify を拒否し、いずれかの launcher 承認後の producer または verifier 不適合は初回でも terminal 化する。terminal は pre-QA・main・subsession 間で共有し、producer write、launcher、split-fork、deploy AC gate を遮断する。post-main/final は当sessionで再生成された producer のみを検査し、stale な prep/create の片方や registration が真因を覆い隠さないようにした。`verify-data-resources.sh` は引き続き Step.1.2 所有であり、Step.1.3 の書込み対象外とする。
- **State-machine tests** ([hve/tests/test_runner_deploy_gate_order.py](hve/tests/test_runner_deploy_gate_order.py), [hve/tests/test_artifact_validation_deploy_gate.py](hve/tests/test_artifact_validation_deploy_gate.py), [hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)): 承認前の一回だけの修復、pending 中の非 prep launcher 拒否、承認後の producer/verifier mismatch terminal、pre-QA から main への fail-fast、producer phase close、post/final freshness、fresh/stale pair 分離、Step.1.2 verifier 所有権を回帰テストで固定した。
- **見送り（記録）**: T-F（view_range の runner 側 clamp）は runner の tool イベントが観測専用で引数を実行前に改変できないため実装不可、既存 Prompt 側衛生で代替。T-β2（Prompt escape hatch）は T-β1 が masking を解消したため YAGNI で見送り。T-E（環境 BLOCKED semantics）は deploy 合否境界の緩和で製品判断が必要なため fail-closed を維持し見送り。
- **検証**: 実装3タスクの focused pytest **395 passed**、関連統合 **649 passed**。T03 state-machine と SSOT を含む最終ローカル統合回帰は **731 passed / 2 skipped**。既存の pre-existing 失敗 `test_asdw_data_deploy_verify_contract_fails_before_sdk_import`（work-root / MCP 前置 gate 由来）は本変更と無関係で、diff を temp-revert しても同一。Azure CLI / REST / live Azure 操作は未実行。実 GUI の ASDW-WEB Step.1.1→1.3 完走確認は、ユーザー起動が必要な外部ゲートとして未実施。

### Fixed — ASDW-WEB Step.1.2 / Step.1.3 の実SDK shell metadata・MCP pin・生成契約の不整合を修正

**概要**: ASDW-WEB Step.1.3 で、実GitHub Copilot SDKが`commands[].identifier`へコマンド全文を返す形式を、Runnerが先頭tokenだけとして判定してcanonical preflightやHVE所有launcherまで拒否していた問題を修正した。固定preflightをPowerShell/Bash共通の`az --version`、`az account show -o tsv`、`gh --version`、`gh auth status`へ統一し、shell制限Stepが`python -m mdq`や複合探索commandを要求しないようPrompt・Template・共通規約を整合した。preflight failure markerをstale registration scriptのpost-main gateより先に評価し、一次原因を19件の既存artifactエラーで覆わない。Microsoft Learn HTTP MCPにはSDKで必要な`tools: ["*"]`をrepo/runtime pinへ明示し、`mcp.list()`の`connected`以外をmain turn前にfail-closedとする。Step.1.2の任意knowledge参照とwildcard検索衛生、Step.1.3のD08任意性・主要script出力・registry出力も同期した。

- **Runner / permission / MCP** ([hve/runner.py](hve/runner.py), [.github/.mcp.json](.github/.mcp.json)): exact allowlistを広げず、full-command identifierをcanonical command形式として限定受理する。想定外MCP serverはstatusにかかわらず拒否し、期待serverは`connected`だけを受理する。更新済みrepo pinを最小SDK sessionへ渡した`mcp.list()`で`microsoft-learn: connected`を確認した。
- **生成契約** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md), [.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md), [.github/scripts/templates/asdw-web/step-1.3.md](.github/scripts/templates/asdw-web/step-1.3.md), [.github/skills/azure-skills/azure-cli-deploy-scripts/references/asdw-data-verifier-contract.md](.github/skills/azure-skills/azure-cli-deploy-scripts/references/asdw-data-verifier-contract.md), [.github/io-contracts/](.github/io-contracts/), [hve/workflow_registry.py](hve/workflow_registry.py)): preflight、shell境界、entrypoint前景実行、任意knowledge、exact-path検索、D08入力、prep/create/registration出力を同期した。
- **Tests** ([hve/tests/test_runner_deploy_gate_order.py](hve/tests/test_runner_deploy_gate_order.py), [hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py), [hve/tests/test_asdw_data_testcoding_network_contract.py](hve/tests/test_asdw_data_testcoding_network_contract.py), [hve/tests/test_runner_foundry_mcp_routing.py](hve/tests/test_runner_foundry_mcp_routing.py), [hve/tests/test_azure_external_skill_integration.py](hve/tests/test_azure_external_skill_integration.py)): 実run metadata replay、full-command identifier、canonical/非canonical command境界、MCP status・pin、preflight fatal優先、Prompt/I/O/registry同期を回帰テストで固定した。
- **検証**: focused統合pytest **417 passed**、MCP pin/routing回帰 **183 passed**、Runner suite **166 passed**、Python構文、YAML/JSON parse、`git diff --check`、secret-like scanをPASS。全I/O validatorの既存負債とは分離し、ASDW Step.1.3の新規output mismatchがないことを確認した。Azure CLI、Azure REST、Azure resource/data-plane write、live Azure受入試験は、明示承認がないため実行していない。

### Fixed — ASDW-WEB Step.1.2 のWindows形式Raw-Log-Pathと並列tool失敗診断を修正

**概要**: ASDW-WEB Step.1.2（`Dev-Microservice-Azure-DataTestCoding`）で、`tdd-test-report.md`の正しいrun-scoped `Raw-Log-Path`がWindowsの`\`区切りで記録されると、TDD report gateがPOSIXの`/`区切りとの文字列不一致としてStepを失敗させ、workflowを停止していた問題を修正した。既存のinline-code単一バッククォート正規化に加え、今回はconsumer側がcanonicalなrepository-relative POSIX表記と、その全区切りをWindows形式へ置き換えた表記の2候補だけを完全一致で受理する。実ファイルは引き続きRunner算出の固定`static-verification.log`だけを開く。producer側のPrompt/templateは新規生成値をcanonicalな`/`区切りへ統一し、focused pytestへ同gate suiteを必須化した。あわせて、同一Stepで並列実行された`view`等のstart/completeを`toolCallId`で相関し、`view_range out of bounds`時に正しいpath/rangeを表示するようにした。ID欠落・重複・未知ID、順不同complete、キャンセルを含むcleanupでは、別callの引数を誤表示せず、保持する引数をread/view系のpath/rangeへ限定する。

- **TDD report gate** ([hve/runner.py](hve/runner.py)): optionalな単一バッククォートを除去後、POSIX表記または完全なWindows区切り表記だけを受理し、mixed separator、別run/target/phase、絶対path、UNC、traversal、重複区切りを拒否する。ラベル値はI/O先に使わず、既存のstable reader・symlink/junction/reparse・TOCTOU・非空検査を維持した。
- **生成契約** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md), [.github/scripts/templates/asdw-web/step-1.2.md](.github/scripts/templates/asdw-web/step-1.2.md)): 生成する`Raw-Log-Path`をrepository-relative `/`区切りへ固定し、`hve/tests/test_runner_tdd_report_gate.py`をfocused pytestへ必須化した。未知の実在行数へ大きいview範囲を指定せず、OOB時は見出し検索または小範囲へ切り替える規則も追加した。
- **並列tool診断** ([hve/runner.py](hve/runner.py)): `tool.execution_start` / `tool.execution_complete`をStep＋call IDで相関し、ID欠落時も並列startを曖昧状態として扱う。重複active IDは全completeまで名前・引数を借用せず、step開始・session/client cleanupの前後で孤児stateを回収する。`disconnect()`取消時も`client.stop()`を実行し、cleanup中の遅延イベントを最終cleanupで破棄する。
- **Tests** ([hve/tests/test_runner_tdd_report_gate.py](hve/tests/test_runner_tdd_report_gate.py), [hve/tests/test_asdw_data_testcoding_network_contract.py](hve/tests/test_asdw_data_testcoding_network_contract.py), [hve/tests/test_runner.py](hve/tests/test_runner.py)): Windows/不正path境界、Prompt/templateの可視トップレベル契約、否定・HTML・Markdown fenceによる形骸化、Step 1.2のAPP-ID/run-id到達、実SDK型・camelCase互換・並列/順不同/unknown/duplicate/legacy call、秘密値非追加、正常/取消cleanupを回帰テストで固定した。
- **検証**: 契約5モジュールとRunner 3クラスのfocused pytestは **345 passed / 2 skipped / 2 subtests passed**。2件のskipはいずれもWindowsのsymlink作成権限不足（WinError 1314）による既存安全性テスト。run `20260720T223353-71bab6`の既存レポートとraw logを変更せずgateを再評価し、修正前1件の不一致から`GATE_ERROR_COUNT=0`になったことを確認した。Python構文と`git diff --check`はPASS。実装・テスト差分6ファイル（本CHANGELOGを含めて計7ファイル）はallowlist一致、事前dirtyと既存run証跡はSHA-256で不変を確認した。Azure CLI、Azure REST、live Azure操作、workflow全体の再実行は行っていない。

### Fixed — ASDW-WEB Step.1.3 の permission gate が unsandboxed 環境で全 shell を拒否する問題を修正

**補足（2026-07-21実測）**: 後続run `20260721T050325-01f241` のshell permission metadataでは`requestSandboxBypass=null`であり、このbypass緩和は当該runの直接原因ではなかった。同runの実SDK identifier形式、cross-platform preflight、MCP pin、fatal優先順位の修正は上記の新規エントリーに記録する。

**概要**: ASDW-WEB Step.1.3（`Dev-Microservice-Azure-DataDeploy`）が GUI / ローカル（unsandboxed）実行時に、preflight・launcher を含む**すべての shell 要求**を permission gate が拒否し（`HVE blocked Step 1.3 shell request with conflicting path, URL, redirection, command, or sandbox metadata`）、agent が deploy スクリプトを再生成・実行できず workflow が Wave 3 で停止していた問題を修正した。根本原因は shell metadata gate（`_permission_shell_metadata_is_safe()`）が `request_sandbox_bypass` を最初の check で一律拒否シグナルとして扱う点にある。OS コマンドサンドボックスを持たない local / GUI host では Copilot SDK が shell 実行のたびに同フラグを立てるため、canonical Step 1.3 コマンド（固定 preflight / script inspection / launcher stage / registration）が exact-match allowlist と contract gate へ到達する前に拒否されていた（実行時メタデータの直接ログは外部 Copilot SDK のため未取得。read 要求のみ承認され shell 要求が一律拒否された事象・gate の評価順序・SDK スキーマ `PermissionRequestShell` から本フラグをブロッカーと**強く推定**したもので、実 GUI での最終確認は次回 Step.1.3 実行時に行う）。この停止は、shell を実行できず stale な committed `src/data/azure/data-registration-script.sh` が再生成されないまま step 終了時の登録契約 gate で失敗する下流症状として顕在化していた。shell metadata gate の `request_sandbox_bypass` 拒否のみを撤去し、canonical コマンドの実セキュリティ境界（exact-match allowlist + contract gate + path-safety / redirection / URL / identifier 検査）は維持する。read / write / url の sandbox bypass 拒否も不変。

- **Runner** ([hve/runner.py](hve/runner.py)): `_permission_shell_metadata_is_safe()` から `request_sandbox_bypass` の拒否分岐を撤去し、その理由（unsandboxed host では全 shell 実行が bypass を伴い、canonical allowlist と contract gate が実境界であること）を docstring に明記した。`has_write_file_redirection` / `possible_urls` 空要求 / `possible_paths` の expected-target 整合（symlink・hardlink・repo 外の拒否）/ `commands` identifier 整合、および `_permission_request_uses_sandbox_bypass()` を用いる read / write / url 経路の bypass 拒否はすべて維持した。
- **Tests** ([hve/tests/test_runner_deploy_gate_order.py](hve/tests/test_runner_deploy_gate_order.py)): canonical Step 1.3 コマンド（preflight 4 / inspection 3 / launcher create・verify 3 / registration 1）が `request_sandbox_bypass=True` でも承認されること、bypass 緩和後も他の shell metadata 防御（redirection / repo 外 path / URL / 追加 identifier）が拒否を維持すること、非 canonical コマンド（任意 az / `rm -rf` / 別 wrapper / 直接スクリプト実行）が bypass=True でも依然拒否されることを回帰テストで固定した。`test_data_deploy_permission_rejects_conflicting_shell_metadata` から `request_sandbox_bypass` param を撤去した。
- **検証**: `python -m pytest hve/tests/test_runner_deploy_gate_order.py -q` → **154 passed**（旧来 bypass で拒否されていた canonical 承認 11 ケースが GREEN 化、防御ガードは保全）。関連スイート `test_runner.py` / `test_asdw_data_registration_audit_mode.py` / `test_asdw_data_private_verify_validation.py` / `test_asdw_data_testcoding_network_contract.py` 合算 → **916 passed**。既存の pre-existing 失敗 `test_asdw_data_deploy_verify_contract_fails_before_sdk_import` 1 件は未コミットの work-root / MCP 前置 gate に起因し本修正と無関係（本修正を temp-revert しても同一失敗を確認）。Azure CLI / REST / live Azure 操作は実行していない。

### Fixed — ASDW-WEB Step.1.3 の MCP ロード確認イベント待機による恒常失敗を修正

**概要**: ASDW-WEB Step.1.3（`Dev-Microservice-Azure-DataDeploy`）が「create-time MCP ロード確認イベントを受信できない (`did not receive its create-time MCP load confirmation event`)」エラーで毎回失敗し、workflow が Wave 3 で停止していた問題を修正した。Step.1.3 は Azure write 境界のため `enable_config_discovery=False` の隔離セッションで作成されるが、この構成では Copilot SDK / runtime が config discovery ライフサイクルイベントである `session.mcp_servers_loaded` を発火しない（イベント payload の `McpServerSource` は user / workspace / plugin / builtin の discovery 由来のみ）。MCP 検証ゲートが同イベントの confirmation を必須待機していたため待機は必ずタイムアウトし（旧 5.0s も延長後の 60.0s も同様に失敗）、`session.rpc.mcp.list()` は pinned サーバー集合を正しく返しているにもかかわらず Step が閉じられていた。ゲートを Foundry ステップと同方式の `session.rpc.mcp.list()` 厳密一致検査のみへ整理し、充足不能なイベント待機を撤去した。MCP 隔離境界（pinned Microsoft Learn のみ・discovery 無効・実行中の想定外サーバー混入を中断する during-task guard）は不変。

- **Runner** ([hve/runner.py](hve/runner.py)): `StepRunner._verify_asdw_data_deploy_session_mcp_servers()` から `session.mcp_servers_loaded` の confirmation 待機（`asyncio.wait_for`）と待機後の violation 再検査を撤去し、`session.rpc.mcp.list()` の pinned 集合厳密一致を MCP 隔離境界の権威検査とした。未参照となった confirmation 機構（`_session_mcp_confirmation_events` 辞書とその生成箇所、確認待ちタイムアウト定数、`session.mcp_servers_loaded` handler の confirmation set 分岐）を撤去した。実行中の動的サーバー混入を検出する `_session_security_violation_events` と handler の violation 検出分岐は保持した（`session.mcp.start` は `session.mcp_servers_loaded` を発火するため during-task guard は有効）。
- **Tests** ([hve/tests/test_runner_deploy_gate_order.py](hve/tests/test_runner_deploy_gate_order.py)): confirmation イベント不在でも `mcp.list()` 一致ならゲートを通過すること（`asyncio.wait_for` 境界で回帰時ハングを fail-fast 化）、ゲートが `session.mcp_servers_loaded` を待機しないこと（source 回帰ガード）、期待どおりの集合では security violation を記録しないことを固定するテストへ置換した。旧 confirmation / timeout 前提テストは撤去した。
- **検証**: `python -m pytest hve/tests/test_runner_deploy_gate_order.py -q` → **136 passed**。confirmation イベントを待たず `session.rpc.mcp.list()` 一致のみでゲートが通過することを回帰テストで固定。Azure CLI / REST / live Azure 操作は実行していない。

### Changed — HVE GUI 事前 QA ダイアログに選択肢列を追加し回答列を記号表示に変更

**概要**: HVE GUI の事前 QA 回答ダイアログで、回答コンボが選択肢の全文を表示していたため列幅内で文字が省略され読めなかった問題を解消した。「質問」列の直後に読み取り専用の「選択肢」列を新設し、各選択肢を「ラベル) 本文」形式で改行区切り表示する。回答列のコンボはラベル記号（A/B/C…）のみを表示するよう変更し、選択肢の全文は新設列で確認できるようにした。Submit 出力形式（`N: ラベル` / `N:: 自由記述`）・`userData`・IPC 契約・シグナルは変更していない。

- **GUI ダイアログ** ([hve/gui/qa_answer_dialog.py](hve/gui/qa_answer_dialog.py)): 列定数に `_COL_CHOICES` を追加して `既定値候補` / `理由` / `回答` を繰り下げ（計8列）、`_COL_HEADERS` に「選択肢」を挿入した。`_build_table` で選択肢セルへ「ラベル) 本文」を改行連結で設定し、選択肢列を `Stretch` にした。`_build_answer_widget` のコンボ項目テキストをラベル記号のみ（`userData` は従来どおり大文字ラベル）に変更した。列増加に伴いダイアログ既定幅を 1100→1250px にした。自由記述質問（選択肢なし）の選択肢セルは空欄とした。
- **Tests** ([hve/gui/tests/test_qa_answer_dialog.py](hve/gui/tests/test_qa_answer_dialog.py)): 選択肢列の改行区切り全文表示、新設列ヘッダ「選択肢」、回答コンボのラベルのみ表示（`selected_label` の不変性を含む）、自由記述質問の選択肢列空欄を回帰テストで固定した。
- **検証**: `python -m py_compile hve/gui/qa_answer_dialog.py` → PASS。`QT_QPA_PLATFORM=offscreen` の focused pytest `hve/gui/tests/test_qa_answer_dialog.py` → **11 passed**。周辺回帰 `test_qa_answer_dialog.py` / `test_qa_ipc_flow.py` / `test_qa_gui_file_mode.py` の合算 → **20 passed**。対象差分の `git diff --check` → PASS。Submit 出力・IPC 契約は不変のため既存テストの回帰なし。

### Added — Azure / Microsoft Foundry Skill の Step 単位 JIT routing

**概要**: HVE が Azure または Microsoft Foundry を扱う active Step で、外部 Skill root 全体を無条件に公開せず、`hve/skill_manifest.json` で宣言された required Skill と、active Step に宣言されインストール済みの optional candidate の**正確な directory**だけを session へ渡すようにした。optional candidate の実際の読込・利用はPrompt/Skill guardで選定済みAzureサービスと操作に一致するものへ限定する。AAGD の Foundry 固定 Step は `microsoft-foundry` meta skill と repository-pinned Azure / Microsoft Learn MCP を fail-closed で要求し、ASDW-WEB Step.1.3 の Microsoft Learn-only 境界は維持する。Azure resource、`.github/.mcp.json`、新規CLIフラグ、`azd` lifecycleは変更していない。

- **Resolver / manifest / Runner** ([hve/skill_resolver.py](hve/skill_resolver.py), [hve/skill_manifest.json](hve/skill_manifest.json), [hve/runner.py](hve/runner.py)): repository Skillを優先し、external Skillはfrontmatter名が一致する `~/.agents/skills/<name>/SKILL.md` のexact directoryだけを解決する。AAGD `2.3` / `3` は `microsoft-foundry` を required にし、欠落またはSDKがrequired external directoryを受け付けない場合は session 作成前に停止する。Foundry-required main sessionではrepository-pinned `azure` / `microsoft-learn`を注入し、両方の`connected`確認をmain turn前に実施する。per-key MCP上書き後もpinned構成を再適用する。
- **JIT policy / Prompt** ([.github/skills/agent-common-preamble/SKILL.md](.github/skills/agent-common-preamble/SKILL.md), [.github/skills/_routing/README.md](.github/skills/_routing/README.md), [.github/prompts/](.github/prompts/)): optional candidateは選定済みAzureサービスと操作に一致するときだけ利用し、未導入時は設計・read-only・reviewをMicrosoft Learn MCPへfallback、対応Skillが必要なAzure writeはblockする規約を追加した。`azure-prepare` / `azure-deploy`はactive candidateに含めず、`azure-validate`は`asdw-web:5.2` / `adfdv:4.2`のread-only readiness reviewに限定する。ASDW AddServiceではFoundry選定時のみmeta skillを使用し、AAGD Coding / Deployではmeta skill → Azure MCP discovery → Microsoft Learn公式sample →用途限定guidanceの順序を固定した。
- **Isolation / regression tests** ([hve/tests/test_azure_external_skill_integration.py](hve/tests/test_azure_external_skill_integration.py) ほか): exact external directory、repository優先、required Skill欠落時のpre-session停止、pinned MCP接続順序、ASDW Step.1.3 Learn-only隔離、active candidate map、DataDeploy test fixtureのrun ID環境隔離を回帰テストで固定した。
- **検証**: Skill routing validator → PASS。最終統合pytestは `33 passed, 1 skipped`、`151 passed`、`67 passed`、`23 passed`。`git diff --check` → PASS。skipはWindowsのsymlink作成権限に依存する既存テスト。Azure CLI / REST / resource操作 / live verificationは実行していない。

### Fixed — Pre-QA が長い成果物サマリーから質問票を回収できず skip する問題を修正

**概要**: Pre-QA Agent が `qa/*.md` に有効な質問票を保存したあと、質問本文ではなく50文字を超える成果物サマリーを返すと、Runner がその要約だけを解析して質問0件と判定し、回答収集を skip していた問題を修正した。応答本文から質問を抽出できない場合は、既存の安全な `qa/*.md` artifact fallback を使って再解析し、質問票をPhase 0b以降へ渡す。

- **Runner** ([hve/runner.py](hve/runner.py)): `_run_pre_execution_qa()` の文字数ベースのartifact読込分岐を廃止し、既存の `_parse_qa_content_with_artifact_fallback()` を使用して、本文に質問がない場合だけ明示された質問票を再解析するようにした。
- **Tests** ([hve/tests/test_runner_pre_qa_artifact_fallback.py](hve/tests/test_runner_pre_qa_artifact_fallback.py)): 50文字超・`[Qxx]`本文なし・`qa/*.md`参照のみの応答から質問票を回収し、回答収集とPre-QAコンテキスト注入へ進む回帰テストを追加した。
- **検証**: `python -m py_compile hve/runner.py hve/tests/test_runner_pre_qa_artifact_fallback.py` → PASS。Pre-QA parser / merger / fallback helperを含むfocused pytest → **129 passed**。対象差分の `git diff --check` → PASS。

### Fixed — ASDW-WEB Step.1.2 の Raw-Log-Path inline-code 表記による誤停止を抑止

**概要**: ASDW-WEB Step.1.2（`Dev-Microservice-Azure-DataTestCoding`）で、`tdd-test-report.md` の正しい `Raw-Log-Path` を Markdown inline-code の単一バッククォートで囲んだ場合に、TDD report gate が文字列不一致として Step を失敗させ workflow を停止していた問題を修正した。比較前に単一対応バッククォートだけを外し、その後も同じ run-scoped `static-verification.log` との完全一致を要求する。`N/A`、別パス、片側または二重バッククォート、複数ラベル、不可視ブロック、symlink/junction/reparse、読取中の変化、空ログの既存 fail-closed 検証は維持する。

- **Runner** ([hve/runner.py](hve/runner.py)): `StepRunner._validate_asdw_data_static_verification_log()` で、`Raw-Log-Path` が単一対応の ASCII バッククォートで囲まれる場合だけ外側の2文字を除去してから、既存の canonical なリポジトリ相対パスとの完全一致判定を行うようにした。
- **Tests** ([hve/tests/test_runner_tdd_report_gate.py](hve/tests/test_runner_tdd_report_gate.py)): 正しい inline-code path の受理、片側・二重バッククォートの拒否、inline-code 内の別パス拒否を回帰テストで固定した。
- **検証**: `python -m py_compile hve/runner.py hve/tests/test_runner_tdd_report_gate.py` → PASS。`python -m pytest hve/tests/test_runner_tdd_report_gate.py -q -p no:cacheprovider` → **48 passed, 2 skipped**。run `20260720T141916-1bbae9` の実際の Step.1.2 TDD report に対する gate 再評価 → PASS。Azure CLI、Azure REST、live Azure 操作は実行していない。

### Changed — HVE GUI の「実行中の課題」をセッション中は無制限に保持・表示

**概要**: HVE GUI の Workbench 下部「実行中の課題」が 50 件を超えると最古の通知を破棄していたため、GUI セッション中の保持上限を撤去した。既存のスクロール表示と見出しの総件数表示を維持し、設定項目・CLI/CUI の挙動・永続化は追加していない。

- **GUI 状態** ([hve/gui/workbench_state.py](hve/gui/workbench_state.py)): `WorkbenchState.add_user_action()` から固定保持上限と最古の通知を削除する処理を除去し、追加された課題通知をセッション中はすべて保持するようにした。
- **Tests** ([hve/gui/tests/test_page_workbench_layout.py](hve/gui/tests/test_page_workbench_layout.py), [hve/tests/test_gui_user_actions_pane_contract.py](hve/tests/test_gui_user_actions_pane_contract.py)): 旧上限を1件超える51件について、状態の保持数、本文の全件表示、見出しの総件数を検証し、Qt非依存の契約テストで保持上限と最古要素削除処理の再導入を防止する。
- **検証**: `python -m py_compile hve/gui/workbench_state.py hve/gui/tests/test_page_workbench_layout.py hve/tests/test_gui_user_actions_pane_contract.py` → PASS。focused pytest → **12 passed**。対象差分の `git diff --check` → PASS。

### Fixed — ASDW-WEB AuditRecord の設計追随と再実行可能な deterministic gate を統合

**概要**: ASDW-WEB Step.1.2 / 1.3 が AuditRecord を Azure Confidential Ledger application entry 固定で扱い、Step.1.1 が選定した Azure SQL append-only ledger + trusted digest store 設計を正しい成果物でも拒否していた問題を修正した。DataDesign の固定表から `sql-ledger-digest` / `acl-direct` の2方式だけを解決し、verifier / registrationの両validatorが同じresolverを使用し、Runnerが同じdesign pathを伝播する。選定方式と生成物の不一致、未知方式、反対方式の混在、host-side data-plane実行、件数・metadata・identity・cleanupの欠落を各artifact gateでfail-closedとし、生成スクリプト内のAzure CLI実行前guardに加えてregistration実行要求ごとの直前再検査を必須化した。

- **共有契約 / 公式情報参照** ([.github/skills/azure-skills/azure-cli-deploy-scripts/references/asdw-data-verifier-contract.md](.github/skills/azure-skills/azure-cli-deploy-scripts/references/asdw-data-verifier-contract.md), [.github/skills/agent-common-preamble/SKILL.md](.github/skills/agent-common-preamble/SKILL.md)): AuditRecordの2 mode、SQL ledger table / current digest metadata、ACL専用collection、UAMI、mode別registrationを1つの生成契約へ集約した。Microsoft Learn Web fallbackは、相対redirectをHTTPS・同一hostの最終URLへ一度だけ再試行し、連鎖時は停止する規律を追加した。
- **Verifier gate / canonical resolver** ([hve/artifact_validation.py](hve/artifact_validation.py)): DataDesignの固定9列・単一AuditRecord行だけを読み、balancedな`**...**` / `` `...` `` / `*...*`装飾spanと末尾句点1個だけを限定除去した後に、公開済みのcase-sensitive canonical 2値と完全一致させるstrict resolverを追加した。APP-009の10 SQL mapping + VocRecord + AuditRecord件数、SQL append-only ledger type / current digest host・block、ACL direct entry列挙、canonical import / call / resource lifecycle、private ACI / environment / ownership、非private fail-closedを限定AST/shell grammarで検査する。
- **Registration gate / 再実行契約 / ACL TLS lifecycle** ([hve/artifact_validation.py](hve/artifact_validation.py)): Step.1.3 registrationは`HVE-AUDIT-REGISTRATION` markerで完全registrationからAudit処理を分離し、marker外のAudit writeやstatus maskingを拒否する。SQL modeは`UPDLOCK, HOLDLOCK`付きconditional INSERTと同一batchの件数・canonical payload read-backを行い、結果が厳密に`(1, 1)`の場合だけcommitする。ACL modeは最大1001件を遅延列挙し、上限超過・不正entry・同一ID重複・異payloadをfail-closed、未登録時だけappendする。両modeとも同一writerの逐次再実行を保証境界とし、同一payloadをno-op、並行実行は保証外とする。resourceは単一`ExitStack`で解放し、ACL TLS certificateは`TemporaryDirectory`配下の`ledger_certificate_path`へ取得する。登録payloadはcanonical AST完全一致だけを受理し、到達不能となった旧semantic validatorと専用helperを削除した。
- **Runner / permission / reality gate** ([hve/runner.py](hve/runner.py), [hve/workflow_registry.py](hve/workflow_registry.py)): Step.1.3のpre（verifierのみ）/ post-main・step-end（verifier + registration）gateへ同じdesign pathを伝播した。registration実行はHVE所有launcherのexact stageだけを許可し、要求ごとに最新artifactを再検査して`ApproveOnce`とする。source / wrapper / alias / glob / 変数 / `BASH_ENV` / 同一要求内書換えを拒否する。Step.1.3の実在系gateをAC-1 / AC-2 / AC-3へ拡張し、HTML comment・fence・indented codeは不可視として除外し、raw HTMLはvisibility boundary errorとして拒否したうえで、各AC-IDに重複のない単一の`✅`状態を要求する。`src/data/sample-data.json`をregistry必須入力とし、Runnerもvalidator呼出前に欠損をfail-closedにする。Agent起動前のrun-scoped `Issue-*`作成、fan-out分離、path traversal / symlink escape、mkdir失敗時のSDK未起動も保証した。
- **TDD raw evidence gate** ([hve/runner.py](hve/runner.py), [hve/artifact_validation.py](hve/artifact_validation.py)): ASDW Step.1.2だけは、generic TDD schemaに加えて`Raw-Log-Path`が同階層の`static-verification.log`と完全一致することを要求する。reportとraw logを単一file descriptorの安定スナップショットとしてUTF-8 strict読取し、leaf/親symlink・junction・reparse、root escape、非regular/空ファイル、読取中のidentity/size/mtime/path変化をfail-closedにした。可視Markdownの単一行ラベルだけを受理し、comment/fence/indented codeを無視、raw HTML・汎用declaration・container内hidden blockを拒否する。
- **Developer environment** ([pyproject.toml](pyproject.toml), [hve/setup-hve.ps1](hve/setup-hve.ps1), [hve/setup-hve.sh](hve/setup-hve.sh), [.vscode/tasks.json](.vscode/tasks.json)): `test` extraに`pytest>=8.0`を定義し、通常setupはtest extraを導入、`-Minimal`はruntime baseのみとする境界を明確化した。PowerShell setupではeditable installの`-e`とtargetを別引数で渡し、VS Code taskは`${workspaceFolder}`相対の標準`.venv`とRunner同等のdesign/private/sample-data引数を使用する。恒久task 8件を明示的な完全集合として固定し、検証用`TEMP *` taskの残存を契約テストで拒否する。利用ガイドのPowerShell 7実行例も`pwsh -NoProfile -File`へ統一した。
- **回帰実行の安定化** ([mdq/watcher.py](mdq/watcher.py), [tools/skills/markdown_query/vendor/mdq/watcher.py](tools/skills/markdown_query/vendor/mdq/watcher.py)): `MdqWatcher`の相対SQLiteパスを起動元`repo_root`へ固定し、process CWDが別テストの一時ディレクトリへ変わった後に`.mdq/index.sqlite`を誤生成・ロックする順序依存を解消した。upstream修正をportable Skillのvendor snapshotへ同期し、watcherのbyte parityを回帰テストで固定した。
- **Controlled regeneration** ([src/infra/azure/verify-data-resources.sh](src/infra/azure/verify-data-resources.sh)): 手編集ではなく更新済み契約を使うcontrolled Step.1.2 runで再生成し、必須selector、最終wildcard、AuditRecordを含む12 entity coverageを反映し、既存のUAMI/private ACI/ownership-safe cleanupを維持した。Bash / ShellCheck / artifact validator / LF・BOM・UTF-8 / TDD report schemaとfocused pytest **515 passed**を確認した。Step.1.3 registration成果物のcontrolled regenerationとlive実行は未実施で、registrationはvalidator / 契約テストまでを検証した。Azure CLI / REST / data-plane / live verificationは実行していない。
- **検証**: 標準`.venv`で変更領域focused core **1365 passed / 2 skipped / 4 subtests passed / RC=0**、一時task削除後のdeveloper environment契約は **3 passed**、verifierのBash / ShellCheck / artifact / LF-BOM / TDD report + raw logはすべてPASS。自己観測するtask環境契約を一時full taskと分離した`hve/tests`全体の合算は **4997 passed / 3 failed / 10 skipped / 2 xfailed / 441 subtests passed / RC=1**で、今回変更に起因する新規失敗0件。2件の追加skipはWindows権限依存のleaf symlink実体テストで、junction/reparse回帰はPASS。3失敗は前回と同一の既知baseline（未存在SWA workflow、親Skillとreferenceのnetwork-key契約drift、AAD-WEB fan-out fixture mapping不足）のため「全回帰green」とは扱わない。実行コマンド・RC・summary outputはrun-scopedの検証証跡として保存したが、当該ファイルは本エントリ作成時点でリポジトリにcommitされておらず現存しない。

- **Critical 3 — byte-pinned launcher** ([hve/asdw_data_script_launcher.py](hve/asdw_data_script_launcher.py), [hve/runner.py](hve/runner.py), [hve/artifact_validation.py](hve/artifact_validation.py)): Step 1.3のprep/create/registration/verifyは、HVE所有の`python -m hve.asdw_data_script_launcher <stage>`だけを正規実行経路とした。launcherはregular file・symlink/junction/reparse・hardlink・読取中のidentity/size/mtime/path変化を検査し、UTF-8/LFのsnapshot bytesをvalidator入力とBash stdinへ同一のまま渡す。`BASH_ENV`、`ENV`、loader/shell-function、Azure CLI構成、継承PATHを大小文字非依存で除去し、固定system Bashとruntime pathを用いる。design/sample-dataもvalidatorへsnapshot注入し、Runnerはdirect `bash`/`./`、child実行、wrapper、合成command、前後空白付きlauncherを拒否する。現行のstale prep/create/registration artifactは安全に実行前blockされ、再生成前にAzure操作へ進まない。

### Added — AAG/AAGD 生成 Agent の共通能力契約（AG-CAP-01〜06）

**概要**: AAG / AAGD が設計・実装するアプリケーション AI Agent に、ユーザー目的から検証可能な完了条件までを結ぶ Goal Contract、有限の Plan / Act / Observe / Evaluate loop、データ種別に応じた検索経路、SELECT-only SQL、REST API 経由の Create / Update / Delete、MCP client / Remote MCP adapter の責務分離、必要時だけ生成する Agent Skill を共通契約として追加した。Prompt 記述だけでなく deterministic validator と Runner gate で欠落・理由なし N/A・未選択 provider の先回り実装を fail にする。

- **共有契約 Skill** ([.github/skills/ai-agent-capability-contract/](.github/skills/ai-agent-capability-contract/)): `AG-CAP-01`〜`AG-CAP-06`、Goal Loop、検索ルーティング、REST/MCP境界、Skill 3回ルール、reasoned N/A、公式情報の確認日・runtime probe・fallbackを定義した。Web IQ は limited access として扱い、利用可否を実行時確認して承認済みfallbackへ切り替える契約とした。
- **AAG設計 / AAGD実装契約** ([users-guide/08-ai-agent.md](users-guide/08-ai-agent.md), [.github/prompts/](.github/prompts/), [.github/scripts/templates/aagd/](.github/scripts/templates/aagd/), [.github/io-contracts/](.github/io-contracts/)): Mission / success criteria / Mutation Intent、`Knowledge & Structured Data Routing`、REST CRUD Matrix、MCP Integration Plan、Skill Packaging Decisionを設計・テスト仕様・RED/GREEN実装・Deploy preflightへ一貫して伝播した。
- **Artifact validator / Runner gate** ([hve/artifact_validation.py](hve/artifact_validation.py), [.github/skills/ai-agent-capability-contract/scripts/validate-agent-contract.py](.github/skills/ai-agent-capability-contract/scripts/validate-agent-contract.py), [hve/runner.py](hve/runner.py)): AAG Step 3とAAGD Step 2.3のfan-out成果物をexact allowlistで検査し、Markdown/code spoofing、理由不足N/A、route/REST/MCP/Skillの設計実装不一致、secret-like値、symlink逃げ、test trace欠落を検出するようにした。
- **AAGD Issue-tree gate** ([hve/cloud_aagd_gate.py](hve/cloud_aagd_gate.py)): Root以下をpagination付きで再帰走査し、全descendantの`aagd:done`、`aagd:blocked` / `aagd:test-failed`不在、空tree拒否、cycle dedupeをSelf-Improve直前までfail-closedで確認するCLIを追加した。

### Changed — AAG/AAGD の Post-DAG Self-Improve を既定必須化

**概要**: HVEのPost-DAG Self-Improveをscan-only処理から、実Copilot mutation、決定的criteria評価、再検証、diff/evidence記録までを行う品質ループへ拡張した。AAG/AAGDはCloudで常時必須、CLI/GUIでは既定ONとし、ローカル障害時の明示的な緊急opt-outだけを維持する。

- **Self-Improve core** ([hve/self_improve.py](hve/self_improve.py)): SCAN → PLAN → MUTATE → VERIFY → DIFF → RECORDを実装し、required criterion全PASS、非空PASS evidence、test/contract/security/verification PASSを成功条件にした。pytest / ruff / dotnet build・testを言語別に判定し、NO_TESTS / tool unavailable / non-zero exitを成功扱いしない。
- **Scope / lifecycle safety** ([hve/self_improve.py](hve/self_improve.py), [hve/orchestrator.py](hve/orchestrator.py)): mutation・scan・verifyをworkflow output ceiling内に限定し、absolute/traversal/`work/`/symlink/Windows junction・reparse point、command/git mutation、scope外patchを拒否する。Copilot session/client cleanup、iteration/timeout/budget、上位workflowへの失敗伝播、PR/merge抑止を追加した。
- **CLI / GUI設定** ([hve/__main__.py](hve/__main__.py), [hve/gui/page_options.py](hve/gui/page_options.py), [hve/gui/settings_store.py](hve/gui/settings_store.py)): Self-Improveを継承 / 明示ON / 明示OFFのtri-stateへ変更し、旧boolean設定を後方互換migrationした。
- **Cloud state machine** ([.github/workflows/auto-ai-agent-design-reusable.yml](.github/workflows/auto-ai-agent-design-reusable.yml), [.github/workflows/auto-ai-agent-dev-reusable.yml](.github/workflows/auto-ai-agent-dev-reusable.yml)): `pending → running → finalizing → completed`、成功/失敗label read-back、失敗時reopen、allowlist staging、clean tree、FF-only push、Root done/closeの成功後限定を実装した。AAG/AAGDは共通のrepository-wide FIFO group `ai-agent-root-state-${{ github.repository }}`でstate mutationと同一branch pushを直列化する。

### Fixed — 無条件Review増殖によるStep timeoutとASDW data network契約の重複を解消

**概要**: ASDW-WEB Step.1.2で成果物とRED証跡の生成後もPromptの無条件レビュー指示がReview Sub-agentを反復起動し、GitHub Copilot SDKの`send_and_wait`がsession idleへ到達しないままHVEの`step_timeout_seconds=7200`で停止した問題を修正した。敵対的レビューの発動条件を既存Skillへ集約し、通常時はPrompt固有観点を1回のインライン・セルフチェックとして扱い、HVE Main PhaseとPhase 3、Cloud producer / consumer / transitionの所有権を分離した。あわせてStep.1.2 / 1.3に重複していたnetwork key・route・ACI lifecycle・passwordless接続契約をSkill-owned referenceへ集約し、Step.1.2の未定義`public` / `nsp` evidence schemaはAzure呼び出し前にfail-closedとした。

- **Review activation SSOT** ([.github/skills/harness/adversarial-review/](.github/skills/harness/adversarial-review/), [.github/skills/agent-common-preamble/SKILL.md](.github/skills/agent-common-preamble/SKILL.md), [.github/copilot-instructions.md](.github/copilot-instructions.md)): 敵対的レビューを明示marker、専用label、ユーザーの明示依頼、または`auto_contents_review=true`のHVE Phase 3だけで発動する契約へ統一した。`auto-context-review`は質問トリガーのまま敵対的レビューには流用せず、Cloudでは引用部を除外し、`false` markerをlabel / `true` markerより優先する。
- **Prompt / Runner所有権** ([.github/prompts/](.github/prompts/), [hve/tests/r03_prompt_review_inline_contract.py](hve/tests/r03_prompt_review_inline_contract.py), [hve/runner.py](hve/runner.py), [hve/orchestrator.py](hve/orchestrator.py)): レビュー記述を持つ43 Promptを動的inventoryとの集合一致で固定し、単回inline self-checkへ移行した。通常時のReview Sub-agent・反復レビュー・独立review artifact要求を除去し、RunnerはMain送信直前の末尾suffixで、Review OFF時は単回self-check後に完了、ON時はMain内レビュー禁止・既存Phase 3へ委譲を明示する。対話経路の`skip_review`も`auto_contents_review`へ同期し、新しい設定flag、SDK tool除外、成果物監視cancel、timeout延長は追加していない。
- **Cloud review chain** ([.github/ISSUE_TEMPLATE/](.github/ISSUE_TEMPLATE/), [.github/workflows/](.github/workflows/), [.github/scripts/](.github/scripts/)): Issue producer、最新PR再取得consumer、review→approve transition、最終consumerの発動判定を同じexplicit-only契約へ揃えた。HVE Python Issue producerは`auto_contents_review`をCloud marker / labelへ複製せず、Main / Phase 3とCloud reviewの二重発動を防止する。
- **ASDW data network SSOT** ([.github/skills/azure-skills/azure-cli-deploy-scripts/references/asdw-data-verifier-contract.md](.github/skills/azure-skills/azure-cli-deploy-scripts/references/asdw-data-verifier-contract.md), [.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md), [.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md), [.github/scripts/templates/asdw-web/step-1.2.md](.github/scripts/templates/asdw-web/step-1.2.md), [.github/scripts/templates/asdw-web/step-1.3.md](.github/scripts/templates/asdw-web/step-1.3.md)): 11 network keys、private topology、run-scoped one-shot ACI、ownership-safe cleanup、bounded log / exit判定、UAMI/passwordless SQL / Cosmosを1つのreferenceへ集約した。Prompt / templateにはStep固有の目的・APP-009対象・Policy pre-flight・TDD / AC / output契約とexact delegationだけを残し、Step.1.3のPolicy許可済み`public` semanticsはStep.1.2のfail-closedへ誤統一していない。
- **Tests / 実モデルsmoke** ([hve/tests/test_adversarial_review_policy_contract.py](hve/tests/test_adversarial_review_policy_contract.py), [hve/tests/r03_prompt_review_inline_contract.py](hve/tests/r03_prompt_review_inline_contract.py), [hve/tests/test_runner_review_activation.py](hve/tests/test_runner_review_activation.py), [hve/tests/test_asdw_data_testcoding_network_contract.py](hve/tests/test_asdw_data_testcoding_network_contract.py), [hve/tests/test_asdw_data_deploy_policy_contract.py](hve/tests/test_asdw_data_deploy_policy_contract.py)): Review契約93件、Runner回帰334件（subtest 7件）、ASDW network契約440件、統合focused suite **867 passed / 7 subtests passed**を同一Python 3.14 processで確認した。C01追記前のV05静的監査時点で、B00基線以降の変更116パスはexact allowlistと完全一致し、Python 14件compile、YAML 33件 / JSON 1件parse、Bash 5件 / PowerShell 6件構文、secret・UTF-8・LF/BOM・`git diff --check`をPASSした。Windows上のdetached一時worktreeで実行したStep.1.2のstep-level実モデルsmoke（Azure live deployなし、2026-07-16）は**15分46秒**で完了し、Review Phase / Review Sub-agent 0、focused pytest **205 passed**、artifact validator / TDD gate / Bash / ShellCheckをPASSした。Azure CLI / REST / SDK data-plane / live deployは実行していない。

### Fixed — ASDW-WEB private data verifier の生成契約と fail-closed gate を強化

**概要**: ASDW-WEB Step.1.2 / 1.3 のデータ検証について、再生成される `docs/` / `src/` や Azure resource instanceを直接修正せず、HVEのSkill・Prompt・Step template・artifact validator・Runner gate・契約テストを強化した。Policyでpublic経路が使えない場合のprivate topology、User-assigned Managed Identity、one-shot ACI、SQL/Cosmos件数検証を決定的に検査し、未確認状態や権限エラーからpublic/data-planeへ進むfail-openを防止する。

- **生成契約** ([.github/skills/azure-skills/azure-cli-deploy-scripts/SKILL.md](.github/skills/azure-skills/azure-cli-deploy-scripts/SKILL.md), [.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md), [.github/scripts/templates/asdw-web/step-1.2.md](.github/scripts/templates/asdw-web/step-1.2.md)): `public` / `private` / `nsp` / `blocked`の固定分岐、private topologyのread-only確認、`DATA_VERIFY_ACI_IMAGE`と32桁run ID、`mssql-python`の`ActiveDirectoryMSI`、`azure-cosmos`のUAMI credential、ACI ownership付きcleanupを統一した。同名ACIはsuccessfulな`az container list`の件数が厳密に0の場合だけ作成し、`container show`の任意の非ゼロを「不存在」と誤認しない。
- **Deterministic validator / Runner** ([hve/artifact_validation.py](hve/artifact_validation.py), [hve/runner.py](hve/runner.py)): multiline `aci_command`をhost-side statementとACI payloadに分離し、前者は許可したAzure CLI文法、後者はSQL/Cosmos/Auditの実行契約として個別に検査する。APP-009のSQL table/database対応、異なるsample期待件数、Cosmos count、実行可能なConfidential Ledger count、全client/cursorの同一`finally`内closeを静的検査する。実在するsample-dataが壊れている場合はfail-closed、Step.1.2の任意sample欠損時だけcoverageを省略する。Step.1.3ではregistration scriptをmain task後・split-fork前に検査し、Deploy AC失敗をoutput不足より先に報告する。
- **TDD / I/O契約** ([hve/tests/test_tdd_test_report_contract.py](hve/tests/test_tdd_test_report_contract.py), [.github/scripts/validate-io-contract.py](.github/scripts/validate-io-contract.py)): DataDeployのcanonical report pathを`asdw-web/step-1-3/.../GREEN`へ固定し、他TDD Stepのgeneric path契約を維持した。`tests/run/<run-id>/`と`work/run/<run-id>/`はruntime-only outputとしてStepDef registry比較から除外し、DataDeploy固有のI/O false positiveを解消した。
- **対象外（意図的）**: live Azure deploy / data registration / smoke testとAzure resource instanceは操作していない。再生成される`docs/` / `src/` / `tests/run/` / `work/run/`成果物そのものは本変更の意図差分に含めず、次回runのAgent再生成に委譲した。今回実行した全I/O validatorは既存負債（schema 6 / integrity 41 / registry mismatch 133）によりexit 1のままだが、出力内の`asdw-web/1.3`一致エラーは0件である。
- **検証**: Step.1.2 focused契約 **223 passed**、Step.1.3 HVE-only契約 **180 passed**、代表回帰 **45 passed**、sample optional/required境界 **7 passed**、変更Python 8ファイルのcompile、最終意図差分11ファイルのsecret scan（0件）、`git diff --check`、`docs/` / `src/`意図差分0件を確認した。ruff / markdownlintは実行環境に未導入のためSKIPした。実Azure操作は未実施。

### Fixed — AI Agent workflow parity・I/O契約・全回帰基線

- AAG/AAGD Issue Templateの任意enable checkboxを削除し、max iterations / quality thresholdとAAGD TDD retryを独立設定として維持した。Cloud mandatoryとCLI emergency opt-outの意図的差をparity fixtureへ明記した。
- AAG/AAGD CloudのRoot完了先取り、late TDD/Deploy failure、Step 4.1/4.2誤完了、label API fail-open、branch競合、scope外staging、generated Python dependency未導入を修正した。
- 変更I/O contractのYAML構文とper-Step producerを現行registryへ同期し、今回変更契約のvalidator errorを0件にした。全repo validatorには既存debt（schema 6 / integrity 41 / registry mismatch 137）が残る。
- SDK不在とlegacy-shaped Copilot SDKのclient生成を分離し、Work IQ / Code Reviewのgraceful fallbackを回復した。ARD KPI/OKRを現行Step 2.1へ同期し、モデル取得テストの実network漏れ、AAD fan-out fixture依存、usage report schema v2テスト、GUI tri-state可視性基線も修正した。
- **検証**: `hve/tests/test_*.py` 169ファイルを8 shardで実行し、**3,841 passed / 12 skipped / 2 xfailed / 427 subtests passed**。変更GUI回帰22件、Skill routing strict、変更YAML parse、Python compileall、secret scan、`git diff --check`もPASS。ruff / markdownlintは選択環境に未導入のためSKIPし、構文・契約・全pytestで代替した。

### Fixed — Microsoft Foundry の Project 未作成と陳腐化した固定モデル選定を抑止

**概要**: ASDW-WEB の追加 AI/LLM サービス配置で、Foundry resource に `--allow-project-management` を指定するだけで Foundry Project 子リソースを作成せず、モデルも Prompt の旧い例示へ固定され得る問題を修正した。Foundry resource と Project の責務を分離し、Project の `show → 未存在時 create → show`、Project 実在 AC、Model Router-first の live 選定、固定モデル fallback、後段 integration test、AAGD の既存 Project 利用までを一貫した契約へ更新した。

- **Design / Microsoft Learn 契約** ([.github/prompts/Dev-Microservice-Azure-AddServiceDesign.prompt.md](.github/prompts/Dev-Microservice-Azure-AddServiceDesign.prompt.md), [.github/scripts/templates/aad-web/step-2.5.md](.github/scripts/templates/aad-web/step-2.5.md), [.github/scripts/templates/asdw-web/step-2.1.md](.github/scripts/templates/asdw-web/step-2.1.md)): Project 名・location・作成方針と `model-router|fixed` を設計成果物の必須キーにし、Project／architecture／model deployment／Model Router／model version の公式ページ全文、live model catalog、SKU、quota を選定根拠として要求した。quickstart のモデル例と特定モデルの静的既定値は選定根拠から除外した。
- **Deploy / AC** ([.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md), [.github/scripts/templates/asdw-web/step-2.2.md](.github/scripts/templates/asdw-web/step-2.2.md), [hve/workflow_registry.py](hve/workflow_registry.py)): Project の冪等作成、account／Project／設計 location の整合、live catalog の `model-router` entry、quota と deployment capacity の区別、Project情報の記録を追加した。モデル実在を AC-13、Project 子リソース `Succeeded` を AC-14 として分離し、Step.2.2 に既存 Azure Skill 3件と両 reality AC を宣言した。
- **Post-deploy / AAGD** ([.github/prompts/Dev-Microservice-Azure-AddServiceTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-AddServiceTestCoding.prompt.md), [.github/prompts/Dev-Microservice-Azure-AddServiceTesting.prompt.md](.github/prompts/Dev-Microservice-Azure-AddServiceTesting.prompt.md), [.github/scripts/templates/asdw-web/step-2.3.md](.github/scripts/templates/asdw-web/step-2.3.md), [.github/scripts/templates/asdw-web/step-2.4.md](.github/scripts/templates/asdw-web/step-2.4.md), [.github/prompts/Dev-Microservice-Azure-AgentDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-AgentDeploy.prompt.md), [.github/scripts/templates/aagd/step-3.md](.github/scripts/templates/aagd/step-3.md)): Project とモデルの read-only 実在テストを分離し、不在時は Step.2.2 へ差し戻すようにした。AAGD は Project を作成せず、Project endpoint を親 account endpoint で代用しない契約へ統一した。
- **Runtime gate** ([hve/artifact_validation.py](hve/artifact_validation.py), [hve/runner.py](hve/runner.py)): Foundry 採用時だけ生成 shell の実行コマンドを検査し、create側の Project `show` 2件以上／`create` 1件以上、verify側の `show` 必須／`create` 禁止、旧 project CLI の不使用を ASDW Step.2.2 専用 gate で強制した。非 Foundry 設計は no-op とし、新規設定フラグや汎用 shell parser は追加していない。
- **Tests** ([hve/tests/test_asdw_web_addservice_deploy_contract.py](hve/tests/test_asdw_web_addservice_deploy_contract.py), [hve/tests/test_azure_microsoft_learn_mcp_contract.py](hve/tests/test_azure_microsoft_learn_mcp_contract.py), [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py), [hve/tests/test_skill_resolver.py](hve/tests/test_skill_resolver.py), [hve/tests/test_artifact_validation_deploy_gate.py](hve/tests/test_artifact_validation_deploy_gate.py), [hve/tests/test_runner_foundry_deploy_gate.py](hve/tests/test_runner_foundry_deploy_gate.py), [hve/tests/test_aagd_foundry_project_contract.py](hve/tests/test_aagd_foundry_project_contract.py)): Project／モデル契約、Learn根拠、Skill解決、N/A、comment-only／legacy CLI／CRLF／複数script、Runner限定適用、AAGD責務を回帰テストで固定した。
- **対象外（意図的）**: 既存 Azure resource の修復・再配置、実 Azure smoke test、Model Router評価基盤、外部 Foundry Skill の vendoring、global Skill resolver拡張、新規外部依存・設定flag・汎用抽象層は追加していない。
- **検証**: 関連テスト **261 passed**。変更 Python の `py_compile`、対象差分の `git diff --check`、全対象ファイルの最終改行／末尾空白検査も PASS。Microsoft Learn MCP で Project／Model Router／モデル配置／version管理の現行資料を再確認した。実 Azure 操作は未実施。

### Fixed — `enable_auto_merge` 単独の作業ブランチ作成対象を ASDW-WEB / ADFDV に限定

**概要**: GUI の共通設定 `enable_auto_merge=True` が選択した全 workflow へ渡され、ARD / AAS など remote CI/CD 対象外の workflow でも実行開始時に `copilot-sdk/<workflow>-<hash>` ブランチを作成していた問題を修正した。`enable_auto_merge` 単独でブランチを作成する対象を、ASDW-WEB の Step 単位 remote CI/CD と ADFDV の workflow 単位 CI/CD に限定した。明示的な `create_issues` / `create_pr` による workflow 単位ブランチ作成は全 workflow で従来どおり維持する。

- **Orchestrator** ([hve/orchestrator.py](hve/orchestrator.py)): `_uses_workflow_branch_mode` の auto-merge 単独経路を ADFDV のみに限定し、ASDW-WEB は既存の Step.3.4 / Step.4.3 専用ブランチ経路を維持した。実際の作業ブランチも Step 専用ブランチも存在しない非対象 workflow では、失敗時に「PR 作成をスキップ」と誤表示しないようサマリー条件を実オブジェクト基準へ変更した。
- **設定契約** ([hve/config.py](hve/config.py)): `enable_auto_merge` のコメントを、ASDW-WEB（Step 単位）/ ADFDV（workflow 単位）と、その他 workflow の明示 `create_issues` / `create_pr` 経路の責務に同期した。
- **Tests** ([hve/tests/test_orchestrator_branch_mode.py](hve/tests/test_orchestrator_branch_mode.py), [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py)): 全 workflow の branch-mode マトリクス、ARD / AAS の checkout・commit・push・PR 非実行、ADFDV の workflow branch、明示 Issue / PR 優先、dry-run、失敗時サマリー、ASDW-WEB Step-scoped lifecycle を回帰テストで固定した。
- **対象外（意図的）**: GUI 保存値や CLI 引数の伝播、ブランチ命名、push / PR / merge / branch cleanup、ASDW-WEB / ADFDV の既存 CI/CD 単位は変更していない。新規設定・抽象レイヤー・外部依存も追加していない。
- **検証**: 関連テスト `51 passed, 48 subtests passed`。変更 Python 4 ファイルの `py_compile`、対象差分の `git diff --check` も PASS。

### Fixed — HVE GUI / Autopilot で非canonical推薦のAPPが対象外になる問題を修正

**概要**: `docs/catalog/app-arch-catalog.md` の推薦アーキテクチャが既知の完全一致語彙にない場合、`classify_architecture()` が `None` を返し、GUI の「対象アプリケーション (APP-ID)」と Autopilot 実行計画から当該 APP が脱落する問題を修正した。既知表記の分類を優先したうえで、DWH・BI・Analytics・分析、バッチ・ETL・集計・データ処理・データパイプラインに関する非空推薦を `batch`、それ以外の非空推薦を `web-cloud` に分類する。空推薦は従来どおり未分類とする。

- **生成契約** ([.github/prompts/Arch-ArchitectureCandidateAnalyzer.prompt.md](.github/prompts/Arch-ArchitectureCandidateAnalyzer.prompt.md), [.github/skills/architecture-questionnaire/assets/output-format.md](.github/skills/architecture-questionnaire/assets/output-format.md), [.github/skills/app-scope-resolution/SKILL.md](.github/skills/app-scope-resolution/SKILL.md)): 詳細な推薦名を保持したまま downstream workflow 用に二分類する規則、欠損時のデータ中心判定、英字大小文字と独立語 `BI` の扱いを統一した。
- **分類実装** ([hve/app_arch_filter.py](hve/app_arch_filter.py)): 空値と既知完全一致を先に処理し、未知の非空推薦を `batch` / `web-cloud` のいずれかへ防御的に分類するフォールバックを追加した。
- **Tests** ([hve/tests/test_app_arch_filter.py](hve/tests/test_app_arch_filter.py), [hve/tests/test_app_arch_routing_contract.py](hve/tests/test_app_arch_routing_contract.py), [hve/gui/tests/test_app_id_checklist.py](hve/gui/tests/test_app_id_checklist.py), [hve/gui/tests/test_autopilot_planner.py](hve/gui/tests/test_autopilot_planner.py), [.github/skills/_evals/app-scope-resolution.eval.yaml](.github/skills/_evals/app-scope-resolution.eval.yaml)): BFF系の `web-cloud`、DWH/BI/Analytics系の `batch`、大小文字、`BI` 部分一致除外、GUI両kind表示、Autopilot chain、Prompt/Skill契約ドリフトを回帰テストで固定した。
- **対象外（意図的）**: 再実行で生成される成果物である `docs/**` と、分類ロジックを利用する側の `src/**` は変更していない。新規設定・外部ライブラリ・抽象レイヤーも追加していない。`pyproject.toml` の依存定義は変更せず、既存の `.[gui]` extras は GUI テスト実行環境の準備にのみ使用した。
- **検証**: 関連テスト `77 passed, 8 subtests passed`。実カタログ12件で `APP-001=web-cloud`、`APP-010=batch`、AAD-WEB / ADFD 対象の和集合が12件であることを確認。`py_compile`、`git diff --check`、`docs/src` 差分なしも確認した。

### Fixed — ASDW-WEB Step.4.2 GREEN gate が正直な BLOCKED 終端を拒否し不要停止する問題を抑止

**概要**: ASDW-WEB Step.4.2 (`Dev-Microservice-Azure-UICoding`) の TDD GREEN gate が `TDD-Judgement: PASS` のみを受理し、テスト側/共有設定側の確定ブロッカー（実装だけでは GREEN 化不能）を正直に `BLOCKED` と記録しても Step を失敗させて workflow を停止させる問題を抑止した。gate を `PASS` に加え `BLOCKED` も受理（実装未達など自ステップ起因の `FAIL` は従来通り拒否）するよう整合し、prompt / template / skill の GREEN 終端判定も `BLOCKED` 許容へ統一した。BLOCKED 時は runner が警告表示（成功扱い・下流続行）する。

- **Gate** ([hve/artifact_validation.py](hve/artifact_validation.py)): `validate_tdd_test_report` の GREEN 分岐を `TDD-Judgement not in ("PASS","BLOCKED")` でエラー化へ変更（`FAIL` 等は従来通り拒否）。
- **Runner** ([hve/runner.py](hve/runner.py)): `_run_tdd_report_gate` で GREEN の `BLOCKED` を検出した場合、Step は成功扱いのまま「要フォロー」警告を表示する。
- **Prompt / Template / Skill** ([.github/prompts/Dev-Microservice-Azure-UICoding.prompt.md](.github/prompts/Dev-Microservice-Azure-UICoding.prompt.md), [.github/scripts/templates/asdw-web/step-4.2.md](.github/scripts/templates/asdw-web/step-4.2.md), [.github/skills/testing/tdd-red-green-reality/SKILL.md](.github/skills/testing/tdd-red-green-reality/SKILL.md), [.github/skills/testing/tdd-green-retry-strategy/SKILL.md](.github/skills/testing/tdd-green-retry-strategy/SKILL.md)): テスト側/共有設定ブロッカー確定時は `TDD-Judgement: BLOCKED`（gate 受理・下流継続）、自ステップ起因の失敗は `FAIL` とする契約へ統一。
- **Tests** ([hve/tests/test_artifact_validation_tdd_report.py](hve/tests/test_artifact_validation_tdd_report.py), [hve/tests/test_runner_tdd_report_gate.py](hve/tests/test_runner_tdd_report_gate.py), [hve/tests/test_asdw_web_ui_fanout_contract.py](hve/tests/test_asdw_web_ui_fanout_contract.py)): gate が GREEN `BLOCKED` を受理する契約テストを追加し、既存の FAIL 前提アサーションを BLOCKED へ更新した。
- **対象外（意図的）**: Step.4.2 ファイルへのツール利用衛生節の展開、`runner.py` の MCP config discovery 変更（S009 の M365 脱線対策・別スコープ）、他ワークフロー（ADFDV/AAGD）への横展開は行わない。
- **検証**: `py -m pytest hve/tests/test_artifact_validation_tdd_report.py hve/tests/test_runner_tdd_report_gate.py hve/tests/test_asdw_web_ui_fanout_contract.py hve/tests/test_tdd_red_green_reality_contract.py hve/tests/test_tdd_test_report_contract.py hve/tests/test_tdd_report_io_contract.py` → 62 passed。

### Fixed — ASDW-WEB Step.4.1 再実行時の「全テスト FAIL」矛盾による不要停止を抑止

**概要**: ASDW-WEB Step.4.1 (`Dev-Microservice-Azure-UITestCoding`) の画面別 fan-out で、再実行時に `src/app/{screenId}/` の実装が既存（前 run の GREEN 成果）だと canonical テストが PASS し「全テスト FAIL（RED）」を機械的に満たせず、fan-out 子が矛盾を解消しようとして凍結（判断待ち）・迷走・脱線し `tdd-test-report.md` を生成できず workflow が `status=blocked` になる事象を抑止した。RED 指示（prompt / template）を再実行認識へ整合させ、初回実行（実装なし）は全 FAIL＝RED、再実行（実装既存）は canonical スイートの PASS を実装先行として許容し、RED を強制する spec 非対応 ad-hoc 失敗テスト（`*.red-gaps` 等）の捏造・累積を禁止、前 run の矛盾テスト累積は canonical スイートへ再整合（置換）する契約に統一した。あわせて fan-out の tool failure（`view_range out of bounds` / 非存在パス read）を減らすツール利用衛生の指針を追加した。

- **Prompt / Template** ([.github/prompts/Dev-Microservice-Azure-UITestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-UITestCoding.prompt.md), [.github/scripts/templates/asdw-web/step-4.1.md](.github/scripts/templates/asdw-web/step-4.1.md)): 目的 / 出力 / RED 確認手順 / 完了条件 / Expected Outcome / §5.3 / §5.5 / DoD / レビュー観点を再実行認識（canonical のみ・実装先行 PASS 許容・失敗テスト捏造禁止・累積は再整合）へ更新し、`## ツール利用衛生（fan-out）` 節（`markdown-query` 優先・`view_range out of bounds` 時の小範囲再取得・`Test-Path` 事前確認）を追加した。
- **Tests** ([hve/tests/test_asdw_web_ui_fanout_contract.py](hve/tests/test_asdw_web_ui_fanout_contract.py)): prompt / template が再実行認識とツール利用衛生を保持することを固定する回帰テストを追加した。
- **対象外（意図的）**: Step.4.2 GREEN gate の `BLOCKED` 受理（root cause A）、`UICoding` / `UIDeploy` prompt・step-4.2 / step-4.3 template へのツール利用衛生展開、fan-out レポート未生成時の gate 挙動（現状 hard fail のまま）、`/src`・`/docs`・`tests/run`・`work/run` の run 生成物は変更しない。
- **検証**: `py -m pytest hve/tests/test_asdw_web_ui_fanout_contract.py` → 14 passed（既存 13 ＋ 新規 1、回帰なし）。

### Fixed — ASDW-WEB Step.4.3 Deploy/AC gate の証跡列 substring 誤検出による不要停止を抑止

**概要**: ASDW-WEB Step.4.3 (`Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps`) で、実デプロイが成功（`ac-verification.md` の AC-1〜AC-12 すべて ✅、GH Actions run success、verify `OK=7 WARN=0 FAIL=0`）しているにもかかわらず、`auto-approve-and-merge.yml` の Deploy/AC gate が PR を停止し、Orchestrator が `<!-- auto-approve-deploy-gate-blocked -->` を検知して Step.4.3 を失敗降格・後続 Step (4.4/5.1/5.2) を blocked にする事象を修正した。原因は gate の naive な部分文字列照合が、コミットされた `ac-verification.md` の**証跡カラム**にあるスクリプト実出力 `FAIL=0`（キーワード `FAIL` に一致）と、post-merge 手動切替 (`switch-swa-to-main.sh`) の設計注記「本 Step では未実行」（キーワード `未実行` に一致）を誤検出していたこと。runner 側 `validate_deploy_ac_verification` は状態カラムのみを検査しており誤検出しないため、gate をこの正しい列認識に整合させた。

- **Workflow** ([.github/workflows/auto-approve-and-merge.yml](.github/workflows/auto-approve-and-merge.yml)): Deploy/AC gate の AC テーブル行 not-green 判定を、whole-row substring 照合から**状態カラム（3列目）限定**（`NEEDS-VERIFICATION|❌|⏳`）へ変更。全体キーワード net の走査対象を `source_text`（`ac-verification.md` 全文＋PR prose）から `combined_text`（PR 本文/コメントのみ）へ限定。必須 AC ✅ 強制ループ・AC-1 / AC-13 フォールバックは維持。
- **Tests** ([hve/tests/test_auto_approve_and_merge_contract.py](hve/tests/test_auto_approve_and_merge_contract.py)): 状態カラム限定判定と `combined_text` 限定 net を固定する契約テストを追加した。
- **対象外（意図的）**: runner 側 `validate_deploy_ac_verification`（既に正しい列認識）、UIDeploy prompt / template、`auto-app-dev-microservice-web-reusable.yml` の類似 gate、agent の `git add -f` 挙動は変更しない。
- **検証**: 実データ（Step.4.3 の committed `ac-verification.md`）で gate コアロジックを実行し、全✅+`FAIL=0`+`未実行`→PASS（誤検出解消）、AC-6=❌ / AC-8=⏳ / PR 本文に「残作業」→ block（真の失敗検出）を確認。`py -m pytest hve/tests/test_auto_approve_and_merge_contract.py hve/tests/test_artifact_validation_deploy_gate.py hve/tests/test_orchestrator.py -q -k "deploy_ac or gate or wait_pr or contract"` → 68 passed。YAML パース・`bash -n` も PASS。

### Fixed — ASDW-WEB Step.4.3 SWA workflow dispatch の default branch 未認識エラーを抑止

**概要**: ASDW-WEB Step.4.3 (`Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps`) が同一 Step 内で新規作成した Azure Static Web Apps workflow を即 `gh workflow run --ref <branch>` し、GitHub 側で `workflow ... not found on the default branch` となって AC-6 / AC-8 が未達になる問題を修正した。SWA workflow は default branch に存在するリポジトリ管理 workflow として扱い、Step.4.3 は既存 workflow の pre-flight 確認・実行・検証を担当する契約へ統一した。

- **Workflow** ([.github/workflows/azure-static-web-apps-app009.yml](.github/workflows/azure-static-web-apps-app009.yml)): APP-009 SWA 用 workflow をリポジトリ管理ファイルとして追加し、`workflow_dispatch`、`environment: copilot`、OIDC `azure/login@v2`、`az staticwebapp secrets list` による deployment token 動的取得、`Azure/static-web-apps-deploy@v1` を固定した。
- **Prompt / Template / Skill / io-contract** ([.github/prompts/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md](.github/prompts/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md), [.github/scripts/templates/asdw-web/step-4.3.md](.github/scripts/templates/asdw-web/step-4.3.md), [.github/skills/cicd/github-actions-cicd/SKILL.md](.github/skills/cicd/github-actions-cicd/SKILL.md), [.github/skills/cicd/github-actions-cicd/references/cicd-common-spec.md](.github/skills/cicd/github-actions-cicd/references/cicd-common-spec.md), [.github/io-contracts/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps--asdw-web--4.3.yaml](.github/io-contracts/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps--asdw-web--4.3.yaml)): Step.4.3 で SWA workflow を新規作成・更新しないこと、default branch に存在する workflow を `gh workflow run --ref <branch>` で実行すること、workflow 未認識時は deploy へ進まないことを明記した。io-contract では SWA workflow を runtime output から static input へ移し、work artifact 出力の YAML インデント崩れも修正した。
- **Runner logging** ([hve/runner.py](hve/runner.py)): `apply_patch` の V4A patch header（`Add` / `Update` / `Delete File`）から更新対象ファイルだけを file I/O tracking に反映し、GUI / console の Files summary が `/dev/null` だけを write として表示する誤認を抑止した。
- **Tests** ([hve/tests/test_asdw_web_step_scoped_cicd_contract.py](hve/tests/test_asdw_web_step_scoped_cicd_contract.py), [hve/tests/test_runner_file_tracking.py](hve/tests/test_runner_file_tracking.py)): Step.4.3 の既存 default-branch workflow 前提、APP-009 SWA workflow の OIDC / 動的 token 契約、io-contract の input/output 境界、`apply_patch` file tracking を固定する回帰テストを追加した。
- **対象外（意図的）**: `/src` / `/docs` / `work/run` / `tests/run` の run 生成物は直接修正しない。AC-6 / AC-8 gate の緩和、Step.4.3 の bootstrap 例外フラグ、Agent による base branch push 許可、Orchestrator の中間 merge 機構は追加しない。
- **検証**: `python -m pytest hve/tests/test_asdw_web_step_scoped_cicd_contract.py hve/tests/test_runner_file_tracking.py hve/tests/test_artifact_validation_deploy_gate.py -q` → 80 passed。`git --no-pager diff --check -- .github hve CHANGELOG.md` → PASS。変更 Python ファイルの診断では既存 import / type 警告が残るが、今回追加箇所に起因する新規診断は検出されていない。

### Fixed — ASDW-WEB Step.4.1 UI RED 生成時の未確定 Contract 検出と tool failure 診断を強化

**概要**: ASDW-WEB Step.4.1 (`Dev-Microservice-Azure-UITestCoding`) の画面別 fan-out 実行で、対象 `src/test/ui/<screenId>/` 配下の helper `.js` に executable な `TBD（要確認）` が残った場合に HVE gate が失敗させる既存契約を、Prompt / template / 回帰テストでより明確化した。あわせて `view_range out of bounds` など read/view 系 tool failure の原因追跡に必要な path / range がログに残らず調査不能になる問題を、失敗時だけ安全な引数サマリーを出す最小実装で改善した。

- **Prompt / Template** ([.github/prompts/Dev-Microservice-Azure-UITestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-UITestCoding.prompt.md), [.github/scripts/templates/asdw-web/step-4.1.md](.github/scripts/templates/asdw-web/step-4.1.md)): UI RED テスト生成完了前に `src/test/ui/{screenId}/` 配下の `.js` を確認し、非コメント行の `TBD（要確認` を実行コードから除去して `{WORK}` の契約確定待ち記録へ分離する指示を追加した。Step.4.1 template の `src/app/` 最小スタブ許可は、UI 実装コード変更禁止と矛盾するため削除した。
- **Runner logging** ([hve/runner.py](hve/runner.py)): `tool.execution_start` の read/view 系安全引数（path / `view_range` / line range）のみを step 単位で一時保持し、`tool.execution_complete` failure 時だけ error message に付与するようにした。shell command や任意 query は秘密情報・ログ肥大化リスクがあるため出力しない。
- **Fan-out common** ([hve/prompt/fanout/asdw-web/_common.md](hve/prompt/fanout/asdw-web/_common.md)): ASDW-WEB fan-out 子の screen key / service doc 参照を実運用の `APP-*-S*`、`docs/screen/{{key}}-description.md`、`docs/services/{{key}}-description.md` 形式へ修正した。io-contract の required outputs は影響範囲が大きく、今回の直接原因ではないため変更しない。
- **Tests** ([hve/tests/test_artifact_validation_tdd_report.py](hve/tests/test_artifact_validation_tdd_report.py), [hve/tests/test_runner.py](hve/tests/test_runner.py), [hve/tests/test_asdw_web_ui_fanout_contract.py](hve/tests/test_asdw_web_ui_fanout_contract.py)): UI RED TBD guard が sibling `.js` と missing path を扱う契約、read/view tool failure に path / range が出る契約、成功 tool 後に stale args が混入しない契約、Prompt / template / fan-out common の契約を追加した。
- **対象外（意図的）**: `/src` / `/docs` / `tests/run` / `work/run` の生成物は run ごとに再生成されるため直接修正しない。`view_range` 失敗を Step failure に昇格する変更、全 tool event の永続 JSONL 化、io-contract schema / producer integrity の広域修正は今回の最小修正を超えるため行わない。
- **検証**: `python -m pytest hve/tests/test_artifact_validation_tdd_report.py hve/tests/test_asdw_web_ui_fanout_contract.py hve/tests/test_runner.py::TestStepRunnerStreamEvents hve/tests/test_tdd_report_io_contract.py -q` → 73 passed, 3 warnings。`python -m py_compile hve/runner.py hve/artifact_validation.py hve/tests/test_runner.py hve/tests/test_artifact_validation_tdd_report.py hve/tests/test_asdw_web_ui_fanout_contract.py` → PASS。対象 io-contract YAML の限定 parse / runtime report output 確認 → PASS。`python .github/scripts/validate-io-contract.py --no-registry-check` は今回未編集の既存 io-contract schema / integrity エラーにより失敗するため、広域検証としては不採用。

### Fixed — ASDW-WEB Step.4.1 の未確定 Contract RED が Step.4.2 GREEN を阻害する問題を抑止

**概要**: ASDW-WEB Step.4.1 (`Dev-Microservice-Azure-UITestCoding`) が、正式 API endpoint / event / schema / enum 値が `TBD（要確認）` の未確定 Contract を Step.4.2 で PASS 必須の実行テストとして生成し、Step.4.2 (`Dev-Microservice-Azure-UICoding`) が UI 実装だけでは GREEN 化できず TDD report gate で失敗する問題を抑止した。未確定契約は実行テストではなく契約確定待ちの blocker / Questions として記録し、GREEN 必達テストは UI 実装・API mock・fixture 接続で PASS 化可能な範囲に限定する。

- **Prompt / Template** ([.github/prompts/Arch-TDD-TestSpec.prompt.md](.github/prompts/Arch-TDD-TestSpec.prompt.md), [.github/prompts/Dev-Microservice-Azure-UITestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-UITestCoding.prompt.md), [.github/prompts/Dev-Microservice-Azure-UICoding.prompt.md](.github/prompts/Dev-Microservice-Azure-UICoding.prompt.md), [.github/scripts/templates/asdw-web/step-4.1.md](.github/scripts/templates/asdw-web/step-4.1.md), [.github/scripts/templates/asdw-web/step-4.2.md](.github/scripts/templates/asdw-web/step-4.2.md)): 未確定契約を後続 GREEN Step の PASS 必須実行テストにしないこと、UI RED テスト生成時は契約確定待ちとして記録すること、GREEN 化不能なテスト側ブロッカーは成功扱いせず `TDD-Judgement: FAIL` とすることを明記した。
- **Runner / gate** ([hve/artifact_validation.py](hve/artifact_validation.py), [hve/runner.py](hve/runner.py)): ASDW-WEB Step.4.1 / `Dev-Microservice-Azure-UITestCoding` の fan-out target に限定し、生成 UI RED テスト内の非コメント `TBD（要確認）` を検出して fail する guard を追加した。汎用 TDD gate の judgement 体系や新規設定フラグは追加していない。
- **Tests** ([hve/tests/test_asdw_web_ui_fanout_contract.py](hve/tests/test_asdw_web_ui_fanout_contract.py), [hve/tests/test_artifact_validation_tdd_report.py](hve/tests/test_artifact_validation_tdd_report.py), [hve/tests/test_runner_tdd_report_gate.py](hve/tests/test_runner_tdd_report_gate.py)): Prompt / Template の未確定 Contract 方針、UI RED guard の検出・コメント除外、fan-out target スコープを固定する回帰テストを追加した。
- **対象外（意図的）**: `/src` / `/docs` / 既存 `tests/run` / `work/run` 成果物は次回実行で再生成されるため直接修正しない。WorkIQ MCP timeout、`view_range out of bounds`、`WebFetchRedirectError`、GUI summary reason の表示ずれは今回の直接原因ではないため別課題とする。
- **検証**: `python -m pytest hve/tests/test_asdw_web_ui_fanout_contract.py hve/tests/test_tdd_test_report_contract.py hve/tests/test_tdd_red_green_reality_contract.py hve/tests/test_tdd_green_retry_contract.py hve/tests/test_runner_tdd_report_gate.py hve/tests/test_artifact_validation_tdd_report.py hve/tests/test_generated_test_runtime_contract.py hve/tests/test_template_engine_generated_test_runtime.py -q` → 76 passed。`python -m py_compile hve/runner.py hve/artifact_validation.py hve/tests/test_runner_tdd_report_gate.py hve/tests/test_artifact_validation_tdd_report.py hve/tests/test_asdw_web_ui_fanout_contract.py` → PASS。

### Fixed — ASDW-WEB Step.4.1 TDD report の workflow path 誤生成を抑止

**概要**: ASDW-WEB Step.4.1 (`Dev-Microservice-Azure-UITestCoding`) の画面別 fan-out TDD RED 実行で、Agent が `tdd-test-report.md` を HVE workflow id の `asdw-web` ではなく Custom Agent 名ディレクトリ配下へ生成し、HVE の TDD report gate が `not found` と判定する問題を修正した。HVE が期待する run-scoped report path をメインタスク Prompt に具体的に注入し、report 内の `Workflow` / `Target-Key` ラベル不一致も gate で検出するようにした。

- **Runner / gate** ([hve/runner.py](hve/runner.py), [hve/artifact_validation.py](hve/artifact_validation.py)): fan-out TDD Step へ `tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md` の具体パスを注入し、`Workflow` と `Target-Key` ラベルの期待値不一致を検出するようにした。
- **Prompt / Template** ([.github/prompts/Dev-Microservice-Azure-UITestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-UITestCoding.prompt.md), [.github/scripts/templates/asdw-web/step-4.1.md](.github/scripts/templates/asdw-web/step-4.1.md)): `<workflow-id>` は HVE workflow id（ASDW-WEB では `asdw-web`）であり、`Dev-Microservice-Azure-UITestCoding` は Agent 名として扱うこと、HVE が提示する具体 report path を優先することを明記した。
- **Tests** ([hve/tests/test_runner_tdd_report_gate.py](hve/tests/test_runner_tdd_report_gate.py), [hve/tests/test_artifact_validation_tdd_report.py](hve/tests/test_artifact_validation_tdd_report.py), [hve/tests/test_asdw_web_ui_fanout_contract.py](hve/tests/test_asdw_web_ui_fanout_contract.py)): Custom Agent 名ディレクトリ配下の report だけでは gate が pass しないこと、`Workflow` / `Target-Key` mismatch を検出すること、Prompt / Template が workflow id と Agent 名を区別することを固定した。
- **対象外（意図的）**: `/src` / `/docs` / 既存 `tests/run` / `work/run` 成果物は修正しない。RED フェーズで `TDD-Judgement: FAIL` をどう扱うか、WorkIQ MCP timeout、`view_range out of bounds` は今回の直接原因ではないため別課題とする。
- **検証**: `python -m pytest hve/tests/test_runner_tdd_report_gate.py hve/tests/test_artifact_validation_tdd_report.py hve/tests/test_asdw_web_ui_fanout_contract.py hve/tests/test_tdd_report_io_contract.py hve/tests/test_tdd_test_report_contract.py hve/tests/test_runner_split_required_guard.py -q` → 48 passed。`python -m py_compile hve/runner.py hve/artifact_validation.py hve/tests/test_runner_tdd_report_gate.py hve/tests/test_artifact_validation_tdd_report.py hve/tests/test_asdw_web_ui_fanout_contract.py` → PASS。

### Fixed — HVE GUI「選択中」ログタブでサブコンポーネント選択時に関連ログを表示するよう修正

**概要**: HVE GUI の Workbench 右ペイン「選択中」タブが、左ツリーで fan-out 子ノード（サブコンポーネント/サブプロセス）を選択しても関連ログをほとんど表示しない問題を修正した。原因は、autopilot 経路では fan-out 子のログ行が行頭インラインマーカー（`[hve:ctx:...]`）を持たず `[main]` プレフィックスへ落ちて `WorkflowInstance.step_log_buffers` に振り分けられないため、選択ハンドラの `step_log_buffers` 完全一致参照では空表示となっていたこと。選択ハンドラを、`log_buffer` 全体から選択 step_id（および fan-out 子孫 `<id>/...`）に一致する本文ラベル/プレフィックスを持つ行を抽出する方式へ変更した。

- **GUI** ([hve/gui/page_workbench.py](hve/gui/page_workbench.py)): `_on_node_selected` の Step ノード分岐を `step_log_buffers[step_id]` 完全一致から `_filter_lines_for_step()` による `log_buffer` フィルタへ変更し、本文ラベル `[<id>]` / `[Step.<id>]` と子孫 `<id>/...` を照合する `_build_step_label_pattern()` を追加した。subagent ノード（`parent::subagent::name`）は親 step_id にフォールバックし、一致 0 行時は従来の `step_log_buffers` 完全一致へフォールバック（Plan/fleet マーカー経路互換）する。
- **GUI** ([hve/gui/widgets/log_tabs.py](hve/gui/widgets/log_tabs.py)): `set_selected_content()` が該当ログ 0 行のとき、未選択時プレースホルダと区別できる「関連ログなし」文言を表示するようにした。
- **Tests** ([hve/gui/tests/test_page_workbench_selected_filter.py](hve/gui/tests/test_page_workbench_selected_filter.py)): fan-out 子抽出・親子孫集約・ラベル無し継続行の除外・subagent 親フォールバック・空時 `step_log_buffers` フォールバック・パターン誤マッチ防止を検証する単体テスト 9 件を追加した。
- **対象外（意図的）**: 本文にサブ ID ラベルを持たない継続行（`skill` 単独行、MCP 接続行等）の推測帰属は誤帰属（捏造）となるため行わない。選択後に追記される行のライブ反映、フィルタ入力 UI、表示行数上限は本修正の範囲外（YAGNI）とする。
- **検証**: `.venv\Scripts\python.exe -m pytest hve/gui/tests/test_page_workbench_selected_filter.py hve/gui/tests/test_log_tabs.py hve/gui/tests/test_page_workbench_layout.py` → JUnit XML 集計で 24 passed / 0 failed / 0 error（新規 9 + 回帰 15）。

### Fixed — HVE GUI の「実行中の課題」ペインで保持中の課題通知を確認可能に修正

**概要**: HVE GUI 下部の「実行中の課題」ペインが `WorkbenchState.user_actions_view()` 経由で最新 5 件だけを表示していたため、TDD report gate などが大量の ERROR を出している状況でも画面上では一部しか見えず、問題量を把握しづらい問題を修正した。GUI では既存の保持上限（最大 50 件）内の課題通知をスクロール可能なテキスト欄へ全件表示し、見出しに件数を表示するようにした。

- **GUI** ([hve/gui/page_workbench.py](hve/gui/page_workbench.py)): `_EnhancedUserActionsPane` が `state.user_actions_view()` ではなく保持中の `state.user_actions` を表示し、通知がある場合は見出しを `実行中の課題 (N)` に更新するようにした。新しい設定フラグや保持上限変更は行わず、既存の `QPlainTextEdit` スクロールをそのまま利用する。
- **Tests** ([hve/gui/tests/test_page_workbench_layout.py](hve/gui/tests/test_page_workbench_layout.py), [hve/tests/test_gui_user_actions_pane_contract.py](hve/tests/test_gui_user_actions_pane_contract.py)): GUI ペインが保持中の課題通知を全件表示すること、件数見出しを更新することを検証する Qt テストを追加した。ローカル環境で PySide6 が無い場合でも今回の GUI 差分を検知できるよう、Qt 非依存の軽量 contract test も追加した。
- **対象外（意図的）**: `work/run/` / `tests/run/` の過去 run 成果物、TDD report validator の緩和、課題通知の重複集約、新規 UI 設定フラグ追加は行わない。
- **検証**: `python -m pytest hve/tests/test_gui_user_actions_pane_contract.py hve/gui/tests/test_page_workbench_layout.py hve/tests/test_runner_tdd_report_gate.py hve/tests/test_artifact_validation_tdd_report.py hve/tests/test_tdd_test_report_contract.py hve/tests/test_tdd_red_green_reality_contract.py hve/tests/test_template_engine_generated_test_runtime.py -q -rs` → 37 passed, 1 skipped（PySide6 未導入環境の GUI module skip）。

### Fixed — TDD report gate の fan-out target 誤検査と固定スキーマ伝達漏れを修正

**概要**: HVE CLI / GUI の TDD RED/GREEN Step で、fan-out 子 Step 完了時に TDD report gate が現在 target ではなく同一 Step 配下の全 target レポートを検査し、兄弟 target の壊れた `tdd-test-report.md` に巻き込まれて正常 target まで fail する問題を修正した。あわせて、ASDW-WEB Step.4.2 を含む TDD gate 対象 Prompt / Step template に固定 Markdown スキーマを明記し、`<!-- validation-confirmed -->`、`- Label: value` 形式の必須ラベル、固定見出しを生成元から伝達できるようにした。

- **Runner** ([hve/runner.py](hve/runner.py)): fan-out child step id（例: `4.2/APP-009-S013`）では `tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md` の現在 target だけを検査し、target suffix のない通常 Step では従来どおり Step 配下の全候補を検査するようにした。
- **Prompt / Template** ([.github/prompts/](.github/prompts/), [.github/scripts/templates/](.github/scripts/templates/)): `_TDD_REPORT_PHASES` 対象の ASDW-WEB / ADFDV / AAGD TDD RED/GREEN Prompt と Step template に、Skill `tdd-red-green-reality` 準拠の固定 `tdd-test-report.md` skeleton、Markdown list label 形式、固定見出し名を追加した。
- **Tests** ([hve/tests/test_runner_tdd_report_gate.py](hve/tests/test_runner_tdd_report_gate.py), [hve/tests/test_tdd_test_report_contract.py](hve/tests/test_tdd_test_report_contract.py)): fan-out child が兄弟 target の不正 report に巻き込まれないこと、現在 target の report 欠落は見逃さないこと、TDD gate 対象 Prompt / template が固定 report schema を含むことを回帰テストで固定した。
- **対象外（意図的）**: `/docs`、`/src`、`tests/run/`、`work/run/` の既存 run 成果物は次回実行で再生成されるため直接修正しない。phase ディレクトリ大小文字の fallback や report 自動補正も、今回の root cause に対する最小修正を超えるため追加しない。
- **検証**: `python -m pytest hve/tests/test_runner_tdd_report_gate.py hve/tests/test_tdd_test_report_contract.py hve/tests/test_artifact_validation_tdd_report.py hve/tests/test_tdd_report_io_contract.py hve/tests/test_tdd_red_green_reality_contract.py hve/tests/test_tdd_green_retry_contract.py hve/tests/test_generated_test_runtime_contract.py -q` → 55 passed。`python -m py_compile hve/runner.py hve/tests/test_runner_tdd_report_gate.py hve/tests/test_tdd_test_report_contract.py` → PASS。

### Fixed — ASDW-WEB Step.4.1 TDD RED レポート固定スキーマの伝達不足を修正

**概要**: ASDW-WEB Step.4.1 (`Dev-Microservice-Azure-UITestCoding`) の画面別 TDD RED 実行で、Agent が生成する `tdd-test-report.md` に必要情報を書いていても、HVE の TDD report gate が要求する固定 Markdown スキーマ（`<!-- validation-confirmed -->`、`- Label: value` 形式の必須ラベル、`## Actual Result` / `## Evidence` / `## Test Protection` などの固定見出し）と一致せず、Step が `missing required label` / `missing required section` で fail する問題を修正した。過去 run の `/docs` / `/src` / `tests/run` 成果物は直接修正せず、次回以降の run で効く生成元 prompt / template / skill と契約テストに限定して是正した。

- **Skill** ([.github/skills/testing/tdd-red-green-reality/SKILL.md](.github/skills/testing/tdd-red-green-reality/SKILL.md)): `tdd-test-report.md` の固定 Markdown テンプレートを追加し、ラベルは `- Label: value` 形式にすること、`## Result` / `## Observed Result` / `## Actual Outcome` / `## Changed Test Files` などの代替見出しを使わないこと、RED フェーズの `TDD-Judgement: PASS` は「テスト成功」ではなく「RED 期待結果どおりの証跡判定」を表すことを明記した。
- **Prompt / Template** ([.github/prompts/Dev-Microservice-Azure-UITestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-UITestCoding.prompt.md), [.github/scripts/templates/asdw-web/step-4.1.md](.github/scripts/templates/asdw-web/step-4.1.md)): UI TestCoding Agent と ASDW-WEB Step.4.1 のレンダリング指示に、validator と一致する固定スキーマ、必須ラベル形式、固定見出し名、代替見出し禁止を追加した。
- **Tests** ([hve/tests/test_tdd_test_report_contract.py](hve/tests/test_tdd_test_report_contract.py), [hve/tests/test_artifact_validation_tdd_report.py](hve/tests/test_artifact_validation_tdd_report.py)): skill / prompt / template が固定スキーマを含むこと、非 bullet ラベルや `## Result` / `## Changed Test Files` などの見出し名ゆれを `validate_tdd_test_report()` が拒否することを固定する回帰テストを追加した。
- **対象外（意図的）**: `hve/artifact_validation.py` の validator ロジックは、固定スキーマ品質を守る既存 gate として正しく機能しているため変更しない。`hve/runner.py` / `hve/template_engine.py` への自動補正・alias 許容・新規設定フラグ追加も、過剰な汎用化を避けるため行わない。
- **検証**: `python -m pytest hve/tests/test_artifact_validation_tdd_report.py hve/tests/test_tdd_test_report_contract.py hve/tests/test_tdd_red_green_reality_contract.py hve/tests/test_template_engine_generated_test_runtime.py hve/tests/test_runner_tdd_report_gate.py -q` → 33 passed。コード / Prompt / Template / Skill の対象 5 ファイルの診断 → 0 件。`docs/` 配下の変更なしを確認。

### Changed — TDD テスト結果レポートの標準出力先を `test/run/` から `tests/run/` にリネーム

**概要**: TDD RED/GREEN テスト結果レポートの標準出力先を、ルート直下 `test/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`（単数 `test`）から `tests/run/<run-id>/.../tdd-test-report.md`（複数形 `tests`）へリネームした。ルート直下の CI テスト資産を集約する `tests/` 配下へ統一し、`src/test/` はテストコード専用のまま維持する。本エントリは上記「生成テストのローカル / 外部サービス実行契約」および「TDD RED/GREEN テスト結果レポートを `test/run/` に標準化」で定義した `test/run/` 出力先を置き換える。

- **Prompt / Template / Skill / io-contract** ([.github/prompts/](.github/prompts/), [.github/scripts/templates/](.github/scripts/templates/), [.github/skills/](.github/skills/), [.github/io-contracts/](.github/io-contracts/)): TDD レポート出力先の記述・宣言を `tests/run/<run-id>/.../tdd-test-report.md` へ更新し、`src/test/` はテストコード専用・`tests/` はテスト結果レポート専用とする解説を統一した。
- **CLI/GUI 共通経路** ([hve/runner.py](hve/runner.py), [.github/scripts/validate-io-contract.py](.github/scripts/validate-io-contract.py)): TDD レポート gate の探索先と registry mismatch 比較から除外する runtime output prefix を `tests/run/` へ更新した。
- **io-contract Schema** ([.github/io-contracts/SCHEMA.md](.github/io-contracts/SCHEMA.md)): テストレポートディレクトリの命名規約を `tests/run/` に更新した。
- **Tests** ([hve/tests/test_runner_tdd_report_gate.py](hve/tests/test_runner_tdd_report_gate.py) 他 TDD 契約テスト群): 標準パス定数・アサーションを `tests/run/` へ更新した。
- **検証**: `python -m pytest hve/tests/test_tdd_test_report_contract.py hve/tests/test_tdd_report_io_contract.py hve/tests/test_tdd_red_green_reality_contract.py hve/tests/test_tdd_green_retry_contract.py hve/tests/test_runner_tdd_report_gate.py hve/tests/test_artifact_validation_tdd_report.py hve/tests/test_generated_test_runtime_contract.py hve/tests/test_template_engine_generated_test_runtime.py -q` → 51 passed。残存 `test/run`（`tests/run` 除く）→ 0 件。

### Changed — 生成テストのローカル / 外部サービス実行契約を Prompt・Skill・CLI/GUI 共通経路へ反映

**概要**: HVE が生成するテストコードについて、Unit / 実装コード向け TDD RED/GREEN はローカル端末・CI で決定的に実行可能にし、Azure など外部サービスを使う Integration / Post-deploy / E2E は構成済みサービスを前提に環境変数またはテスト設定ファイルで接続先を注入する契約へ整理した。未構成の外部サービスを PASS / GREEN 扱いしないこと、秘密情報をコード・README・ログへハードコードしないことも Prompt / Skill / Template / io-contract / CLI/GUI 共通レンダリング経路で明文化した。

- **Skills** ([.github/skills/testing/tdd-red-green-reality/SKILL.md](.github/skills/testing/tdd-red-green-reality/SKILL.md), [.github/skills/testing/test-strategy-template/SKILL.md](.github/skills/testing/test-strategy-template/SKILL.md), [.github/skills/testing/tdd-green-retry-strategy/SKILL.md](.github/skills/testing/tdd-green-retry-strategy/SKILL.md), [.github/skills/harness/harness-verification-loop/references/verification-commands.md](.github/skills/harness/harness-verification-loop/references/verification-commands.md)): 生成テストの実行環境分類、外部サービス未設定時の環境ブロッカー扱い、秘密情報ハードコード禁止、JavaScript/UI テスト実行コマンドを追記した。
- **Prompt / Template** ([.github/prompts/](.github/prompts/), [.github/scripts/templates/](.github/scripts/templates/)): ASDW-WEB / ADFDV / AAGD の TestSpec / TestCoding / GREEN / Integration / Post-deploy / E2E 系 Step に、ローカル実行可能なテストダブル方針、構成済み外部サービス接続、環境変数・設定ファイル注入、`E2E_BASE_URL` / `src/test/agent` / `src/test/e2e` の標準パスを反映した。
- **CLI/GUI 共通レンダリング** ([hve/template_engine.py](hve/template_engine.py)): TDD 専用レポートを要求する Step template に `## 生成テストの実行環境` セクションが無い場合だけ最小契約を補う注入処理を追加し、既存セクションがある場合は重複しないようにした。Azure 公式情報の注入判定も、`Microsoft Learn MCP` の語だけでなく必須文言の有無で判定するよう補正した。
- **io-contract / validation** ([.github/io-contracts/](.github/io-contracts/), [.github/scripts/validate-io-contract.py](.github/scripts/validate-io-contract.py)): TDD ランタイムレポートの出力先を `test/run/<run-id>/.../tdd-test-report.md` に統一し、registry mismatch 比較から除外する runtime output prefix も同じ標準パスへ更新した。
- **Tests** ([hve/tests/test_generated_test_runtime_contract.py](hve/tests/test_generated_test_runtime_contract.py), [hve/tests/test_template_engine_generated_test_runtime.py](hve/tests/test_template_engine_generated_test_runtime.py), 既存 TDD 契約テスト群): 生成テスト実行環境契約、TDD report 標準パス、template render 時の重複なし注入、io-contract runtime output 判定を固定する回帰テストを追加・更新した。
- **検証**: `python -m pytest hve/tests/test_generated_test_runtime_contract.py hve/tests/test_template_engine_generated_test_runtime.py hve/tests/test_tdd_test_report_contract.py hve/tests/test_tdd_report_io_contract.py hve/tests/test_tdd_red_green_reality_contract.py hve/tests/test_tdd_green_retry_contract.py hve/tests/test_azure_microsoft_learn_mcp_contract.py -q` → 49 passed。`tests/run/<run-id>` / `test/agent` / `tests/e2e/playwright` の残存検索 → 0 件。変更 Python ファイルの診断 → 0 件。

### Added — TDD RED/GREEN テスト結果レポートを `test/run/` に標準化

**概要**: HVE CLI / GUI の TDD RED/GREEN Step で、テスト実行結果の証跡が `{WORK}` / Issue コメント / 作業ログに分散していた状態を改め、ルート直下 `test/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md` を標準出力先として定義した。`src/test/` はテストコード専用、`test/` はテスト結果レポート専用とし、RED/GREEN の実行コマンド・期待結果・実結果・秘密情報マスク確認・テスト保護証跡を固定ラベルで記録する。

- **Skills** ([.github/skills/testing/tdd-red-green-reality/SKILL.md](.github/skills/testing/tdd-red-green-reality/SKILL.md), [.github/skills/testing/tdd-green-retry-strategy/SKILL.md](.github/skills/testing/tdd-green-retry-strategy/SKILL.md), [.github/skills/harness/harness-verification-loop/references/verification-commands.md](.github/skills/harness/harness-verification-loop/references/verification-commands.md)): TDD 専用レポートの標準パス、必須ラベル、RED/GREEN 判定、GREEN retry の Root-Cause / 異アプローチ記録、汎用 `verification-report.md` との役割分担を追加した。
- **Prompt / Template** ([.github/prompts/](.github/prompts/), [.github/scripts/templates/](.github/scripts/templates/)): ASDW-WEB / ADFDV / AAGD の TDD RED/GREEN Step に `tdd-test-report.md` の作成を必須化し、実行ログを `docs/` / `src/` に追記しない規律を追加した。
- **Runtime gate** ([hve/artifact_validation.py](hve/artifact_validation.py), [hve/runner.py](hve/runner.py)): `validate_tdd_test_report()` と allowlist ベースの TDD report gate を追加し、対象 Step の report 欠落・固定ラベル欠落・GREEN の `TDD-Judgement` 不一致を検出できるようにした。
- **io-contract** ([.github/scripts/validate-io-contract.py](.github/scripts/validate-io-contract.py), [.github/io-contracts/](.github/io-contracts/)): 対象 per-step io-contract に runtime TDD report output を追加し、`test/run/<run-id>/...` は StepDef 静的 `output_paths` との registry mismatch 比較から除外するようにした。
- **Tests** ([hve/tests/test_tdd_test_report_contract.py](hve/tests/test_tdd_test_report_contract.py), [hve/tests/test_artifact_validation_tdd_report.py](hve/tests/test_artifact_validation_tdd_report.py), [hve/tests/test_runner_tdd_report_gate.py](hve/tests/test_runner_tdd_report_gate.py), [hve/tests/test_tdd_report_io_contract.py](hve/tests/test_tdd_report_io_contract.py), [hve/tests/test_tdd_red_green_reality_contract.py](hve/tests/test_tdd_red_green_reality_contract.py), [hve/tests/test_tdd_green_retry_contract.py](hve/tests/test_tdd_green_retry_contract.py)): TDD report 標準パス、Skill / Prompt / Template / io-contract 契約、validator、runner gate を固定する回帰テストを追加・更新した。
- **検証**: `python -m pytest hve/tests/test_tdd_test_report_contract.py hve/tests/test_artifact_validation_tdd_report.py hve/tests/test_runner_tdd_report_gate.py hve/tests/test_tdd_report_io_contract.py hve/tests/test_tdd_red_green_reality_contract.py hve/tests/test_tdd_green_retry_contract.py hve/tests/test_artifact_validation_deploy_gate.py -q` → 97 passed。`python .github/scripts/validate-io-contract.py` は既存の schema / integrity / registry mismatch が残っているため失敗するが、今回追加した `test/run/<run-id>/.../tdd-test-report.md` はエラーに含まれないことを確認した。

### Fixed — ASDW-WEB Step.4.3 の auto-merge gate と UI fan-out 共有設定衝突を抑止

**概要**: ASDW-WEB Step.4.3 の Azure Static Web Apps deploy が成功しているにもかかわらず、PR auto-merge 側の Deploy / AC gate が UI deploy 契約外の `AC-13` を AI/LLM 文脈だけで要求して停止し、Orchestrator が 600 秒の merge 待機 timeout で workflow を失敗扱いにする問題を修正した。あわせて、Step.4.1 / Step.4.2 の画面別 fan-out 子が root `package.json` / `jest.config.js` を並列作成・更新しない契約へ整理した。

- **Workflow** ([.github/workflows/auto-approve-and-merge.yml](.github/workflows/auto-approve-and-merge.yml)): `AC-13` 必須判定を追加 Azure サービス deploy の変更ファイルに限定し、SWA UI deploy PR が APP 名等の AI 文脈だけで `AC-13` 不足扱いにならないようにした。明示された `AC-13` 行の `✅` / `N/A` 検証は維持した。
- **Orchestrator / GitHub API** ([hve/orchestrator.py](hve/orchestrator.py), [hve/github_api.py](hve/github_api.py)): PR merge 待機中に `<!-- auto-approve-deploy-gate-blocked -->` コメントを検出した場合、timeout まで待たず原因付きで fail-fast するようにした。コメント取得失敗時は従来の待機経路へフォールバックする。
- **Prompt / Template / io-contract** ([.github/prompts/Dev-Microservice-Azure-UITestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-UITestCoding.prompt.md), [.github/prompts/Dev-Microservice-Azure-UICoding.prompt.md](.github/prompts/Dev-Microservice-Azure-UICoding.prompt.md), [.github/scripts/templates/asdw-web/step-4.1.md](.github/scripts/templates/asdw-web/step-4.1.md), [.github/scripts/templates/asdw-web/step-4.2.md](.github/scripts/templates/asdw-web/step-4.2.md), [.github/io-contracts/Dev-Microservice-Azure-UICoding--asdw-web--4.2.yaml](.github/io-contracts/Dev-Microservice-Azure-UICoding--asdw-web--4.2.yaml)): UI fan-out 子では root `package.json` / `jest.config.js` を作成・更新しないこと、Step.4.2 GREEN フェーズでは Step.4.1 の `src/test/ui/` 成果物を input として参照し原則変更しないことを明文化した。
- **Tests** ([hve/tests/test_auto_approve_and_merge_contract.py](hve/tests/test_auto_approve_and_merge_contract.py), [hve/tests/test_asdw_web_ui_fanout_contract.py](hve/tests/test_asdw_web_ui_fanout_contract.py), [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py), [hve/tests/test_github_api.py](hve/tests/test_github_api.py)): auto-approve gate の `AC-13` スコープ、UI fan-out 共有設定保護、PR deploy gate block の fail-fast、Issue / PR コメント取得 API wrapper を固定する回帰テストを追加・更新した。
- **検証**: `python -m pytest hve/tests/test_auto_approve_and_merge_contract.py hve/tests/test_asdw_web_ui_fanout_contract.py hve/tests/test_asdw_web_step_scoped_cicd_contract.py hve/tests/test_artifact_validation_deploy_gate.py hve/tests/test_github_api.py -q` → 121 passed。`python -m pytest hve/tests/test_orchestrator.py -k "wait_pr_merged or merged_triggers_delete or merged_failed_checks_no_delete or unmerged_closed_no_delete or timeout_no_delete or api_error_no_delete or skips_when_repo_missing" -q` → 10 passed, 154 deselected。`python -m pytest hve/tests/test_tdd_red_green_reality_contract.py hve/tests/test_tdd_report_io_contract.py hve/tests/test_tdd_test_report_contract.py hve/tests/test_tdd_green_retry_contract.py -q` → 29 passed。

### Fixed — ASDW-WEB Step scoped CI/CD の merge 後判定と fan-out 実行ログを安定化

**概要**: ASDW-WEB Step.3.4 の Step scoped CI/CD で、Deploy Agent と workflow_dispatch は成功しているのに、PR merge 後の merge commit check-run が存在しないため HVE Orchestrator が失敗扱いにする問題を修正した。あわせて、Step.3.2 / Step.3.3 の fan-out 子が同じ `{WORK}` の `Issue-0` を共有して作業成果物衝突を起こす問題と、並列 session event が別 Step label で表示されるログ誤帰属を修正した。

- **Orchestrator** ([hve/orchestrator.py](hve/orchestrator.py)): 通常 PR 経路は従来どおり merge commit check-run の成功を fail-closed で要求しつつ、Step scoped CI/CD の PR merge 待機では check-run 必須条件を外し、merge 済み判定だけで Step finalize を継続できるようにした。
- **Runner** ([hve/runner.py](hve/runner.py)): fan-out 子 Step の Agent Prompt `{WORK}` 識別子を `Issue-step-<step-id>` 形式へ分離し、非 fan-out Step は既存互換の `Issue-0` を維持した。また Copilot session event handler を Step ID に束縛して登録し、共有 `_current_step_id` の上書きによる並列ログ誤帰属を防止した。
- **Prompt** ([.github/prompts/Dev-Microservice-Azure-ServiceCoding-AzureFunctions.prompt.md](.github/prompts/Dev-Microservice-Azure-ServiceCoding-AzureFunctions.prompt.md)): Azure MCP の Functions template を取得する場合は、MCP が返す利用可能テンプレート一覧の正確な ID を使い、`HttpTrigger` など別ツール文脈の名前を推測で固定指定しないルールを追加した。
- **Tests** ([hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py), [hve/tests/test_runner.py](hve/tests/test_runner.py), [hve/tests/test_azure_microsoft_learn_mcp_contract.py](hve/tests/test_azure_microsoft_learn_mcp_contract.py)): Step scoped CI/CD の check-run スキップ、通常 PR の check-run fail-closed 維持、fan-out WORK 識別子分離、session event の Step ID 束縛、Azure MCP template ID ルールを固定する回帰テストを追加した。
- **検証**: `python -m pytest hve/tests/test_orchestrator.py::TestDeleteLocalMergedBranch hve/tests/test_runner.py::TestWorkIdentifierForStep hve/tests/test_runner.py::TestStepRunnerStreamEvents hve/tests/test_prompt_loader.py hve/tests/test_azure_microsoft_learn_mcp_contract.py hve/tests/test_asdw_web_step_scoped_cicd_contract.py -q` → 80 passed, 3 warnings（既存 `datetime.utcnow()` 非推奨警告）。

### Changed — HVE GUI の github.com CI/CD 実行前に GitHub CLI 認証導線を表示

**概要**: ASDW-WEB / ADFDV の remote CI/CD 対象 Deploy Step 選択時、メイン画面の `github.com で CI/CD を実行` トグル直上に GitHub CLI ログイン用の認証コンポーネントを表示するようにした。`github.com で CI/CD` を ON にして実行する場合は `GH_TOKEN` / `GITHUB_TOKEN` が必須になるため、未認証時は実行前 validation で停止し、同じ画面からログインできる導線を提示する。

- **GUI** ([hve/gui/page_options.py](hve/gui/page_options.py), [hve/gui/main_window.py](hve/gui/main_window.py)): 設定画面 GitHub セクションの認証 UI / `gh auth login` 処理を `_GitHubCliLoginGroup` に切り出し、ASDW-WEB Step.3.4 / Step.4.3 および ADFDV Step.1.2 / Step.3 選択時のみ、既存の CI/CD トグル表示条件に合わせてワークフロー枠へ移設するようにした。CI/CD ON かつ GitHub token 未設定の場合は通常実行・Autopilot 直行経路の両方で validation により停止する。
- **i18n** ([hve/gui/i18n/hve_gui_en_US.ts](hve/gui/i18n/hve_gui_en_US.ts), [hve/gui/i18n/hve_gui_en_US.qm](hve/gui/i18n/hve_gui_en_US.qm)): 新しい認証グループ context と validation メッセージの英訳を追加し、`pyside6-lrelease` による `.qm` 再生成を実施した。
- **Tests** ([hve/gui/tests/test_page_options_github_cicd.py](hve/gui/tests/test_page_options_github_cicd.py), [hve/gui/tests/test_gh_login_button.py](hve/gui/tests/test_gh_login_button.py), [hve/gui/tests/test_main_window_cicd_steps_sync.py](hve/gui/tests/test_main_window_cicd_steps_sync.py), [hve/gui/tests/test_i18n.py](hve/gui/tests/test_i18n.py)): 認証グループが CI/CD トグル直上に表示されること、Deploy Step 未選択時は表示されないこと、CI/CD ON + 未認証を validation でブロックすること、既存のステップ選択同期と i18n ロードが壊れないことを検証する回帰テストを追加・確認した。
- **検証**: `hve/gui/tests/test_page_options_github_cicd.py` → 26 passed。`hve/gui/tests/test_main_window_cicd_steps_sync.py` → 3 passed。`hve/gui/tests/test_i18n.py` → 15 passed。

### Fixed — ASDW-WEB Step scoped CI/CD の stale branch final push を抑止

**概要**: ASDW-WEB の GUI/CLI `github.com で CI/CD` 経路で、Step.3.4 / Step.4.3 の Deploy Agent が remote Step branch を先に進めた後、HVE Orchestrator が stale な local Step branch を final push して `non-fast-forward` で停止する問題を修正した。Agent が誤って `main` / base branch へ push しないよう Prompt / Skill の branch 境界も明確化した。

- **Orchestrator** ([hve/orchestrator.py](hve/orchestrator.py)): Step scoped CI/CD finalization 前に remote Step branch の先行状態を確認し、Agent が remote branch を更新済みの場合は stale local branch の final push をスキップして PR 作成へ進むようにした。current branch が期待する Step branch から drift し、未コミット変更がある場合は final push を中止する guard も追加した。
- **Prompt / Skill** ([.github/prompts/Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.prompt.md](.github/prompts/Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.prompt.md), [.github/prompts/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md](.github/prompts/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md), [.github/skills/cicd/github-actions-cicd/SKILL.md](.github/skills/cicd/github-actions-cicd/SKILL.md), [.github/skills/cicd/github-actions-cicd/references/cicd-common-spec.md](.github/skills/cicd/github-actions-cicd/references/cicd-common-spec.md)): HVE Step scoped CI/CD では `git push origin HEAD` と `main` / base branch への push を禁止し、push が不可欠な場合も `git push origin HEAD:<branch>` のみに限定する契約へ更新した。
- **Tests** ([hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py), [hve/tests/test_asdw_web_step_scoped_cicd_contract.py](hve/tests/test_asdw_web_step_scoped_cicd_contract.py)): remote Step branch が Agent により先行した場合に stale final push を行わないこと、current branch drift + 未コミット変更では fail-fast すること、Prompt / Skill が push 先制約を明文化していることを検証する回帰テストを追加した。
- **検証**: `python -m pytest hve/tests/test_asdw_web_step_scoped_cicd_contract.py hve/tests/test_orchestrator.py -k "step_scoped or remote_cicd" -q` → 12 passed, 154 deselected, 2 subtests passed。`python -m pytest hve/tests/test_orchestrator_git_encoding.py hve/tests/test_orchestrator_git_unmerged_guard.py -q` → 7 passed。

### Added — HVE GUI 下部に local Git リポジトリ / branch 表示を追加

**概要**: HVE GUI の画面下部ステータスバーに、現在の local Git リポジトリ名と local branch を表示するようにした。`github.com で CI/CD` 実行中にローカル checkout branch が変わる場合でも、画面下部で現在の作業ブランチを確認できる。remote branch / GitHub API は参照せず、表示のみに限定する。

- **GUI** ([hve/gui/main_window.py](hve/gui/main_window.py)): `QStatusBar` 左側に `Git: <repo> @ <branch>` ラベルを追加し、5秒間隔で local branch を再取得するようにした。branch 取得は `git branch --show-current` を優先し、detached HEAD では short SHA を `detached:<sha>` として表示する。取得できない場合は `不明` を表示する。
- **安全性** ([hve/gui/main_window.py](hve/gui/main_window.py)): remote branch は取得せず、`.git` が存在しないディレクトリでは git コマンドを起動しない。表示更新中の例外は `不明` 表示へ fallback し、`closeEvent` で更新 timer を停止する。
- **Tests** ([hve/gui/tests/test_main_window_git_status.py](hve/gui/tests/test_main_window_git_status.py)): 表示文言、local branch のみ取得すること、detached HEAD / 取得失敗 / 非 Git ディレクトリの fallback、ステータスバー表示、更新時の branch 表示変更を検証するテストを追加した。
- **検証**: `hve/gui/tests/test_main_window_git_status.py` → 8 passed。`hve/gui/tests/test_main_window_git_status.py` / `hve/gui/tests/test_main_window_model_status_label.py` / `hve/gui/tests/test_status_banner.py` → 30 passed。

### Fixed — ASDW-WEB Step scoped CI/CD の Git 未解決 index preflight

**概要**: ASDW-WEB の GUI/CLI `github.com で CI/CD` 経路で Step.3.4 / Step.4.3 用の一時ブランチを作成する前に、Git index の未解決コンフリクトを検出して fail-fast する preflight を追加した。未解決 index が残った状態では DAG 実行へ進まず、対象ファイル一覧付きの明確なエラーを返すことで、`git checkout -b` の生エラーや downstream Step の blocked 化による原因誤認を防ぐ。

- **Orchestrator** ([hve/orchestrator.py](hve/orchestrator.py)): `git diff --name-only --diff-filter=U` による未解決 index 検出を追加し、branch 作成前に対象ファイル一覧付きで停止するようにした。dirty worktree 全般は HVE の正常系でもあり得るため、検出対象は unmerged entry のみに限定した。
- **ASDW-WEB Step scoped CI/CD** ([hve/orchestrator.py](hve/orchestrator.py)): Step 専用 branch が必要な場合は DAG 実行前に同 preflight を行い、未解決 index がある場合は `blocked: []` の error return として停止することで、入力成果物不足の blocked 表示に root cause が隠れないようにした。
- **Tests** ([hve/tests/test_orchestrator_git_unmerged_guard.py](hve/tests/test_orchestrator_git_unmerged_guard.py), [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py)): `_git_checkout_new_branch` が未解決 index 時に `git fetch` / `git checkout` へ進まないこと、ASDW-WEB Step scoped CI/CD が DAG 実行前に停止して `_git_checkout_new_branch` を呼ばないことを検証するテストを追加した。
- **対象外（意図的）**: `/src` / `/docs` の run 生成物、Prompt / skill、Azure / GitHub 認証設定は今回の root cause ではないため変更しない。未解決 index の自動修復もユーザー成果物を失う可能性があるため実装しない。
- **検証**: `python -m pytest hve/tests/test_orchestrator_git_unmerged_guard.py -q` → 1 passed。`python -m pytest hve/tests/test_orchestrator.py -k "asdw_remote_cicd or unmerged" -q` → 4 passed, 154 deselected。`python -m pytest hve/tests/test_workflow_registry.py -k "remote_cicd_steps_are_limited" -q` → 1 passed, 109 deselected。

### Fixed — ASDW-WEB github.com CI/CD のブランチ lifecycle を Step 単位へ分離

**概要**: ASDW-WEB の GUI/CLI `github.com で CI/CD` 経路（内部 `enable_auto_merge`）で、workflow 開始時に 1 本の作業ブランチを作って全 Step を実行する挙動を改め、remote CI/CD が必要な Step.3.4（Azure Compute Deploy）/ Step.4.3（Web アプリ Deploy）の直前だけ Step 専用ブランチを作成し、push → PR 作成 → `auto-approve-ready` → merge 待機 → base branch 復帰を Step 単位で閉じるようにした。Step.1.3 / Step.2.2 は Azure 実在確認を持つ Deploy Step だが remote CI/CD 対象外として、ローカル `az` 直接実行の責務に留める。

- **Workflow metadata** ([hve/workflow_registry.py](hve/workflow_registry.py), [hve/fanout_expander.py](hve/fanout_expander.py)): `StepDef.requires_remote_cicd` を追加し、ASDW-WEB では Step.3.4 / Step.4.3 のみ `True` とした。fan-out 子 Step 互換オブジェクトにも同属性を継承させ、将来の StepDef 互換性を維持した。
- **Orchestrator** ([hve/orchestrator.py](hve/orchestrator.py)): ASDW-WEB + `enable_auto_merge` では DAG 前の workflow-wide branch 作成を行わず、remote CI/CD 対象 Step ごとに `copilot-sdk/asdw-web-step-<step>-<hash>` を割り当てるよう変更。Step prompt の `{branch}` へ Step 専用ブランチを注入し、Step 実行直前に branch 作成 + pre-push、Step 成功後に final push + PR 作成 + merge 待機 + local branch 削除 + `git pull --ff-only origin <base>` を実施する。失敗 Step では PR を作成せず、デバッグ用に remote branch を残して base branch へ戻る。
- **Prompt / template / skill** ([.github/prompts/Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.prompt.md](.github/prompts/Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.prompt.md), [.github/prompts/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md](.github/prompts/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md), [.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md), [.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md), [.github/scripts/templates/asdw-web/step-3.4.md](.github/scripts/templates/asdw-web/step-3.4.md), [.github/scripts/templates/asdw-web/step-4.3.md](.github/scripts/templates/asdw-web/step-4.3.md), [.github/skills/cicd/github-actions-cicd/SKILL.md](.github/skills/cicd/github-actions-cicd/SKILL.md)): Orchestrator が branch / PR / merge を担当し、Deploy Agent は提供された branch を `gh workflow run ... --ref <branch>` に使う責務境界を明文化した。Step.4.3 template の `デプロイブランチ: main` 固定記述を `{branch}` へ変更した。
- **GUI / i18n** ([hve/gui/page_options.py](hve/gui/page_options.py), [hve/gui/help_content.py](hve/gui/help_content.py), [hve/gui/i18n/hve_gui_en_US.ts](hve/gui/i18n/hve_gui_en_US.ts)): CI/CD トグル説明を Step 単位 branch lifecycle に同期し、英訳 TS を更新した。`pyside6-lrelease` による QM 再生成も実行したが、バイナリ差分は発生しなかった。
- **Tests** ([hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py), [hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py), [hve/tests/test_fanout.py](hve/tests/test_fanout.py), [hve/tests/test_asdw_web_step_scoped_cicd_contract.py](hve/tests/test_asdw_web_step_scoped_cicd_contract.py)): ASDW-WEB remote CI/CD 対象 Step が 3.4 / 4.3 のみであること、`asdw` alias でも workflow-wide branch を作らないこと、Step 専用 branch の prompt 注入・push・PR・merge 待機・base 更新を mock で検証するテスト、および prompt/template/skill 契約テストを追加した。
- **対象外（意図的）**: `/src` と `/docs` の生成物は run ごとに作成・更新されるため直接修正しない。ADFDV は今回の依頼対象外のため Step 単位 branch lifecycle へは変更しない。既存 reusable workflow 内の埋め込みテンプレートコピーは現行の out-of-sync 管理方針に従い同期しない。
- **検証**: `python -m pytest hve/tests/test_orchestrator.py::TestAsdwStepScopedCicd hve/tests/test_orchestrator.py::TestCreatePrIfNeeded hve/tests/test_workflow_registry.py hve/tests/test_fanout.py hve/tests/test_asdw_web_step_scoped_cicd_contract.py hve/gui/tests/test_page_options_github_cicd.py hve/gui/tests/test_github_section_grouping.py hve/gui/tests/test_i18n.py -q` → 212 passed, 2 subtests passed。

### Changed — ASDW-WEB Step.1.3 データサービス作成を並列実行化

**概要**: ASDW-WEB Step.1.3（Custom Agent `Dev-Microservice-Azure-DataDeploy`）が生成する `create-azure-data-resources.sh` について、entrypoint 自体は前景で完了待ちする既存規律を維持しつつ、内部の選定済みデータサービス作成をサービス単位のバックグラウンドジョブで並列実行する契約を追加した。並列化に伴う標準出力混線、終了コード集約漏れ、`data-deploy.env` 同時書き込み衝突を避けるため、サービス別ログ分離・全ジョブ `wait` 後の成否集約・env 断片ファイルの決定的結合を明文化した。

- **Prompt** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md)): 「データサービス作成の並列実行方針」を追加し、共有前提完了後に選定済みデータサービス単位で `&` + `wait` による並列作成を行うこと、各サービスログを `{WORK}artifacts/logs/data-create-<service>.log` に分離すること、各ジョブは `data-deploy.env` へ直接書き込まず `{WORK}artifacts/data-deploy.env.d/<service>.env` 断片を親スクリプトが決定的順序で結合すること、全ジョブ成功後のみデータ登録と verify へ進むことを規定した。
- **Step template** ([.github/scripts/templates/asdw-web/step-1.3.md](.github/scripts/templates/asdw-web/step-1.3.md)): Prompt 側の並列実行方針への参照を追加し、`create-azure-data-resources.sh` entrypoint は前景で完了待ちしつつ内部でデータサービス単位の並列実行を行うこと、全ジョブ成功・env 断片結合後にだけデータ登録と verify へ進むことを Step 指示にも反映した。
- **Tests** ([hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)): Step.1.3 の並列実行契約（entrypoint 前景維持、データサービス単位のバックグラウンドジョブ、`wait "$pid"`、サービス別ログ分離、`data-deploy.env.d` 断片による書き込み衝突防止、全ジョブ成功後のデータ登録・verify、template 参照ポインタ）を検証する5件の契約テストを追加した。
- **対象外（意図的）**: `/src` の生成済みスクリプトは次回 run で再生成されるため直接修正しない。DAG / Runner / AC gate の runtime ロジックは今回の責務外のため変更しない。実 Azure デプロイ smoke は環境・認証・コスト依存が大きいため実施せず、生成元 prompt/template の契約テストで回帰を固定した。
- **検証**: `.venv\Scripts\python.exe -m pytest hve/tests/test_asdw_web_data_deploy_contract.py hve/tests/test_asdw_web_addservice_deploy_contract.py hve/tests/test_azure_microsoft_learn_mcp_contract.py hve/tests/test_artifact_validation_deploy_gate.py -q` → 128 passed。追加で `.venv\Scripts\python.exe -m pytest hve/tests/test_prompt_templates.py -q` → 15 passed。

### Fixed — `test_workflow_registry_agentic.py` の ASDW-WEB ステップテストを現行 registry 構造へ同期

**概要**: ASDW-WEB ワークフローのステップ再編（Step.1.2 DataTestCoding 新設、旧 DataDeploy を 1.3 へ再採番、AddService 系 Step の番号確定）に対して [hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py) が未同期で、pre-existing テスト 4 件が失敗していた事象を是正した。テストを現行 registry（authoritative）に整合させ、カバレッジを維持した。

- **是正** ([hve/tests/test_workflow_registry_agentic.py](hve/tests/test_workflow_registry_agentic.py)):
  - `TestAsdwWebAgenticRetrievalSteps`: 旧番号（2.2=Design / 2.3=Deploy）を現行（`2.1=AddServiceDesign` / `2.2=AddServiceDeploy`）へ是正。存在・エージェント・`2.2→2.1` 依存を検証（冗長だった依存テスト 1 件を統合し 6→5 メソッド、除去分の上流依存カバレッジは `TestAsdwWebStepOrderIntegrity` 側で担保）。
  - `TestAsdwWebStepOrderIntegrity`: `test_step_2_1_depends_on_step_1_2` を現行の `test_step_2_1_depends_on_step_1_3`（依存先 1.2→1.3）へ是正。ASDW-WEB に存在しない `test_step_2_5_depends_on_step_2_4` を、実在する `test_step_2_4_depends_on_step_2_3`（AddService チェーン末尾）へ置換。
  - モジュール / クラス docstring の ASDW-WEB ステップ番号表記を現行構造へ更新。
- **対象外（意図的）**: 自動生成ベースライン `hve-dev/hve-test-inventory.csv`（`generate_tdd_inventory.py` の生成物・どのテストからも非消費）は旧テスト名/行番号を参照し stale だが、手編集は他テストの行番号一斉シフトにより不整合を悪化させ、全体再生成はリポジトリ全テスト再スキャンの大規模差分となるため据え置いた。
- **検証**: `.venv\Scripts\python.exe -m pytest hve/tests/test_workflow_registry_agentic.py hve/tests/test_workflow_registry.py -q` → 181 passed（従来 4 失敗を解消、回帰なし）。

### Fixed — ASDW-WEB `deploy_ac_gate_failed`（PostgreSQL 非選定設計で verify contract gate が偽陽性 fail）

**概要**: ASDW-WEB Step.1.2（`Dev-Microservice-Azure-DataTestCoding`）が `verify-data-resources.sh contract failed`（PostgreSQL 4 件）で停止した事象を調査し、根本原因を **静的 gate 側の PostgreSQL ハードコード前提**と特定して生成元（HVE コード）層に絞って修正した（2026-07-02 run `20260702T210246-8e585f`）。DataDesign（Step.1.1）はデータストアを要件に応じて動的に選定するが、`validate_asdw_data_verify_script()` は「PostgreSQL Flexible Server は必ず使われる」前提で PostgreSQL 検証ブロックの存在を**無条件に要求**していた。当該 run ではユーザーが全 Azure リソースを手動削除し新規設計を指示した結果、DataDesign が Azure SQL Database / Cosmos DB / Blob(Immutable)+ADX を選定（PostgreSQL は Alternatives 列のみ）し、Step.1.2 は設計どおり PostgreSQL 非依存の verify スクリプトを正しく生成したが、gate が 4 件の偽陽性で fail させた。

- **根本原因**: [hve/artifact_validation.py](hve/artifact_validation.py) の `validate_asdw_data_verify_script()` が PostgreSQL 検証ブロック / `az postgres flexible-server show` / `--query state` / `Ready` / ACI fallback を無条件に要求。データストアを動的選定する DataDesign と密結合しており、PostgreSQL を含まない設計では正しい生成物を拒否していた（会話全体で排除してきた「データストア別ハードコード」アンチパターン）。
- **修正** ([hve/artifact_validation.py](hve/artifact_validation.py), [hve/runner.py](hve/runner.py)): `_design_requires_postgresql()` を追加し、設計ドキュメント `docs/azure/azure-services-data.md` のエンティティ選定表「Chosen Azure service」列（header 位置で特定し Alternatives 列は除外）に PostgreSQL があるかで PostgreSQL 検証要求を条件化した。設計で PostgreSQL が非選定かつスクリプトにも PostgreSQL ブロックが不在なら PostgreSQL 検査を全スキップ（偽陽性解消）。設計で選定されている、またはスクリプトに PostgreSQL ブロックが実在する場合は従来どおり正当性（`state=Ready` / `--database-name` 誤用 / ACI fallback 安全性）を検査する（staleness / present-block 検査は維持）。runner の gate 呼び出しに `design_doc_path` を渡すよう更新。
- **対象外（意図的）**: 生成元 prompt / テンプレート（[Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md), [step-1.2.md](.github/scripts/templates/asdw-web/step-1.2.md)）は「選定された各データストア」「PostgreSQL / Cosmos / SQL / Storage / ADX 等」と既に複数データストアを正しく扱っており PostgreSQL を強制していないため変更不要。生成物 `verify-data-resources.sh` 実ファイルは毎 run 再生成のため直接修正しない。
- **回帰ガード** ([hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)): PostgreSQL 非選定設計 + PostgreSQL 非依存スクリプトを受理（本インシデント再現）、設計が PostgreSQL 選定時は欠落を検出（staleness 維持）、設計非選定でもスクリプトに PostgreSQL ブロックが実在すれば正当性検査、`_design_requires_postgresql` が Chosen 列と Alternatives 列を区別、の 4 テストを追加。
- **検証**: `.venv\Scripts\python.exe -m pytest hve/tests/test_asdw_web_data_deploy_contract.py hve/tests/test_artifact_validation_deploy_gate.py -q` → 95 passed。

### Fixed — TDD GREEN リトライ Skill の残作業（メトリクス凡例・テンプレート結線・ACI ログ抽出頑健化）を補完

**概要**: 直前に導入した TDD GREEN リトライ戦略 Skill（`tdd-green-retry-strategy`）の残作業を補完した。(A) メトリクス凡例の実態不整合の是正、(B-1) `tdd_max_retries` を使う GREEN テンプレート 4 件への Skill 結線、(B-2) PostgreSQL 件数取得の ACI ログ抽出頑健化を、生成元 prompt / テンプレート層に限定して実施した。

- **(A) メトリクス凡例の是正** ([.github/workflows/tdd-retry-metrics.yml](.github/workflows/tdd-retry-metrics.yml)): `:blocked` の凡例が `Deploy TDD（最大 3 回）超過` と単一値で記載されていたが、Step.1.3(DataDeploy) / Step.4.4(E2E) を 5 回へ統一した一方で他の Deploy 検証ループ（AddServiceDeploy 2.2 / ComputeDeploy 3.4 / UIDeploy 4.3 / AgentDeploy 等）は 3 回のままという混在実態を反映し、`Deploy / 検証ループ（Step 依存で最大 3〜5 回）超過` へ修正した（敵対的レビューで「凡例は特定 Step ではなく Deploy 検証ループ全般の総称」と判明したための正確化）。
- **(B-1) GREEN テンプレート 4 件への Skill 結線** ([.github/scripts/templates/asdw-web/step-3.3.md](.github/scripts/templates/asdw-web/step-3.3.md), [step-4.2.md](.github/scripts/templates/asdw-web/step-4.2.md), [.github/scripts/templates/aagd/step-2.3.md](.github/scripts/templates/aagd/step-2.3.md), [.github/scripts/templates/adfdv/step-2.2.md](.github/scripts/templates/adfdv/step-2.2.md)): prompt には結線済みだったテンプレート側の GREEN loop 記述に、Skill 参照（各回は異なるアプローチ・失敗の都度に言語別公式技術情報 MCP で根本原因調査）をコンパクトに追記した。回数（`{tdd_max_retries}`、既定 5）は変更なし。
- **(B-2) ACI ログ抽出の頑健化** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md) §5.3): 生成される `verify-data-resources.sh` の PostgreSQL 件数取得が `az container logs ... | tail -n 1`（最終行のみ）で、末尾空行やコンテナ終了直後のログ伝播遅延により間欠的に空文字を拾い `[ERROR]` になる問題（run `20260702T181844-1a8e06` で実測）に対し、`data-registration-script.sh` の登録経路（ログ全文から `grep -qE '^\s*[0-9]+\s*$'` で数値行を抽出・空時の診断情報付与）と**対称**に生成させる頑健化要件を追加した: (1) `tail -n 1` 決め打ち禁止、(2) 出力全文から数値行を抽出、(3) 空/非数値時に短時間待機して 1 回だけログ再取得、(4) 最終失敗時にコンテナ最終状態 / `exitCode` / create stderr を `[ERROR]` に含める。これは Skill の Layer 1（取得手段そのものの異アプローチ）の具体化。根本原因（ACI ログ欠落の間欠性）は 5 回の再現テストで再現できず未確定だが、確定した「抽出方法の非対称性」を是正する防御的修正である。
- **回帰ガード** ([hve/tests/test_tdd_green_retry_contract.py](hve/tests/test_tdd_green_retry_contract.py), [hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)): 4 テンプレートの Skill 参照（`test_tdd_max_retries_green_templates_reference_skill`）、固定回数 Step の Skill 参照（`test_count_change_green_templates_reference_skill`）、ACI ログ抽出頑健化契約（`test_data_testcoding_prompt_requires_robust_aci_log_extraction`）を固定するテストを追加。
- **対象外（意図的）**: 生成物 `verify-data-resources.sh` 実ファイルは毎 run 再生成のため直接修正しない。ACI ログ抽出の静的 gate は実装パターンが多様で文字列検証が脆弱化するため追加せず prompt 契約テストで代替。Cloud reusable YAML の埋め込みコピーは既存の OUT-OF-SYNC NOTICE 方針により対象外。
- **検証**: `.venv\Scripts\python.exe -m pytest hve/tests/test_tdd_green_retry_contract.py hve/tests/test_asdw_web_data_deploy_contract.py hve/tests/test_azure_microsoft_learn_mcp_contract.py hve/tests/test_tdd_red_green_reality_contract.py hve/tests/test_asdw_web_addservice_deploy_contract.py hve/tests/test_skill_resolver.py hve/tests/test_prompt_templates.py -q` → 103 passed。敵対的レビューで adfdv/step-2.2.md に `Azure Functions` を追記したことで `test_rendered_active_azure_step_templates_include_microsoft_learn_mcp_rule` が誤トリガーした regression を捕捉し、当該テンプレートから `Azure` キーワードを除去して修正済み。`test_template_engine.py` の対話入力テスト 1 件は既存の `StopIteration`（`collect_params` 未変更・pre-existing）として切り分け済み。

### Added — TDD GREEN フェーズの多層・異アプローチ・公式情報駆動リトライ規律を共通 Skill 化

**概要**: TDD GREEN フェーズ（テスト/検証を PASS させるまで反復する Step）のリトライを、「同一アプローチの単純反復」から「回ごとに異なるアプローチ＋失敗の都度に根本原因を特定し公式技術情報 MCP から解決策を得る」規律へ統一した。背景として、ASDW-WEB Step.1.3 で GREEN 化リトライが同一の取得アプローチを 3 回繰り返したため 3 回とも同じ弱点（ACI ログ取得の間欠的空文字）に当たり続け GREEN 未達になった実例（2026-07-02 run `20260702T181844-1a8e06`）がある。共通規律を 1 つの Skill に集約し、全ワークフローの GREEN フェーズ Step の prompt から参照する形で、重複記載（保守不能・トークン増大）を避けた。

- **新規 Skill** ([.github/skills/testing/tdd-green-retry-strategy/SKILL.md](.github/skills/testing/tdd-green-retry-strategy/SKILL.md)): 多層リトライ（Layer 1 検証/取得手段 → Layer 2 GREEN 化ループ → Layer 3 Step 全体、各層最大 5 回）、同一手段の単純反復の禁止と「異なるアプローチ」の一般軸、失敗の都度の根本原因特定＋公式技術情報 MCP 参照（Azure/C# → Microsoft Learn MCP、Python → Python 技術情報 MCP、JS/TS 等 → 当該技術の公式ドキュメント MCP、Web は最後の手段）、打ち切りと証跡の規律を定義。
- **ルーティング表** ([.github/skills/_routing/README.md](.github/skills/_routing/README.md)): テスト系 Skill に新 Skill を登録。
- **GREEN フェーズ prompt 7 件への結線**: [Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md)（1.3、固定 3 回→5 回）、[Dev-Microservice-Azure-AddServiceTesting.prompt.md](.github/prompts/Dev-Microservice-Azure-AddServiceTesting.prompt.md)（2.4）、[Dev-Microservice-Azure-ServiceCoding-AzureFunctions.prompt.md](.github/prompts/Dev-Microservice-Azure-ServiceCoding-AzureFunctions.prompt.md)（3.3）、[Dev-Microservice-Azure-UICoding.prompt.md](.github/prompts/Dev-Microservice-Azure-UICoding.prompt.md)（4.2）、[E2ETesting-Playwright.prompt.md](.github/prompts/E2ETesting-Playwright.prompt.md)（4.4、固定 3 回→5 回）、[Dev-Dataflow-ServiceCoding.prompt.md](.github/prompts/Dev-Dataflow-ServiceCoding.prompt.md)（2.2）、[Dev-Microservice-Azure-AgentCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-AgentCoding.prompt.md)（2.3）に、Skill 参照・異アプローチ・失敗時 MCP 調査の規律を追記。各 prompt 固有の原因分類（C1〜C5 等）・scope 境界（verify script 修正は Step.1.2 責務）・blocked 規律は保持した。
- **テンプレート** ([.github/scripts/templates/asdw-web/step-1.3.md](.github/scripts/templates/asdw-web/step-1.3.md), [.github/scripts/templates/asdw-web/step-4.4.md](.github/scripts/templates/asdw-web/step-4.4.md)): 固定 3 回だった 2 Step の反復上限を最大 5 回へ統一し Skill 参照を追記。
- **回帰ガード** ([hve/tests/test_tdd_green_retry_contract.py](hve/tests/test_tdd_green_retry_contract.py)（新規）, [hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)（既存 2 件を 5 回契約へ更新）): Skill の必須セクション・7 prompt への結線・言語別 MCP 参照・固定回数 Step の 5 回統一を固定するテストを追加。
- **対象外（意図的）**: `Dev-Microservice-Azure-ComputePostDeployTest`（Step.3.5）は「反復よりフィードバック重視で 1 回」という既存の明示的設計意図を尊重し対象外とした。`tdd_max_retries`（既定 5）を使う Step は既に 5 回のため回数変更なし。「一時エラー（429/503 等）再試行は最大 3 回」（`harness-error-recovery` 準拠）は GREEN 化ループとは別概念のため変更しない。
- **検証**: `.venv\Scripts\python.exe -m pytest hve/tests/test_tdd_green_retry_contract.py hve/tests/test_asdw_web_data_deploy_contract.py hve/tests/test_tdd_red_green_reality_contract.py hve/tests/test_azure_microsoft_learn_mcp_contract.py hve/tests/test_asdw_web_addservice_deploy_contract.py hve/tests/test_skill_resolver.py hve/tests/test_prompt_templates.py -q` → 100 passed。`test_template_engine.py` は既存の対話入力テスト `TestCollectParams::test_aad_collect_params_with_multiple_app_ids` が `StopIteration` で失敗するが、今回差分に `collect_params` 変更は無く（`git diff` で未変更を確認）、pre-existing として切り分け済み。

### Changed — ASDW-WEB Step.1.2 prompt の Azure CLI 構文ハードコードを Microsoft Learn MCP 動的参照へ移行

**概要**: `.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md` に記載していた個別データストア（PostgreSQL / ADX 等）固有の az CLI コマンド名・引数名・クエリ構文のハードコードを、Microsoft Learn MCP でその都度確認させる方針へ変更した。ユーザー指示により、HVE アプリケーション開発時の順守事項として、対象データストアの変更や CLI/SDK バージョンアップの度に prompt 追記が必要になる保守不能な設計（トークン増大）を避ける。背景として、prompt に ADX/Kusto 用の `--database-name` を明記した結果、LLM が構造の似た PostgreSQL の `db show` にも類推適用し `deploy_ac_gate_failed` が発生した実例（2026-07-02 run `20260702T155130-4a3032`）があり、個別コマンド構文のハードコードそのものが類推混同のリスク源になっていた。

- **Prompt** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md)): §Azure公式情報参照に「個々のデータストア固有の CLI 構文を prompt にハードコードしない・類似コマンド間で引数名を類推流用しない・既存ファイル再利用時も MCP 確認を省略しない」原則を追加。§3 リソース存在検証・データ件数検証、§5.3、§8 の Kusto/PostgreSQL 固有のコマンド名・引数名・SDK パッケージ名のハードコードを削除し、「対象サービスについて Microsoft Learn MCP で個別に確認する」一般原則に置き換えた。ACI フォールバックのアーキテクチャパターン（egress 遮断時の対応）や PostgreSQL の `state`/`provisioningState` に関する実測ベースの経験則（ドキュメントと実挙動の乖離、既往2回のバグ修正で確立）はプロジェクト固有の知見として維持した。
- **回帰ガード** ([hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)): 削除したハードコード文字列を検証していた `test_data_testcoding_prompt_has_adx_count_guidance` を新方針（ADX 等の MCP 都度確認・類推禁止）の検証に更新し、`test_data_testcoding_prompt_requires_mcp_lookup_for_command_syntax` を新規追加した。
- **対象外**: 静的 gate（[hve/artifact_validation.py](hve/artifact_validation.py) の `validate_asdw_data_verify_script()`）は Python コードによる決定論的な安全網であり本方針の対象外のため変更していない。`.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md` 内の同種の具体例列挙（Step.1.2 の既知バグカテゴリの例示）はコマンド生成を指示する文脈ではないため据え置いた。
- **検証**: `.venv\Scripts\python.exe -m pytest hve/tests/test_asdw_web_data_deploy_contract.py hve/tests/test_artifact_validation_deploy_gate.py hve/tests/test_tdd_red_green_reality_contract.py -q` → 97 passed。

### Fixed — ASDW-WEB Step.1.3 の `deploy_ac_gate_failed`（PostgreSQL `db show` の `--database-name` 誤用）を静的 gate と prompt 契約で抑止

**概要**: ASDW-WEB ワークフロー Step.1.3（`Dev-Microservice-Azure-DataDeploy`）が `deploy_ac_gate_failed`（`AC-1 is not GREEN`）で停止した事象を調査し、`/docs` `/src` は毎 run 再生成され直接修正が無効なため、生成元の **prompt 層**と **静的 gate** に絞って最小修正した。根本原因は、Step.1.2（`Dev-Microservice-Azure-DataTestCoding`）が生成/再利用する `verify-data-resources.sh` の PostgreSQL データベース存在確認が `az postgres flexible-server db show --database-name`（存在しない引数。正しくは `--name`/`-n`。[Microsoft Learn](https://learn.microsoft.com/cli/azure/postgres/flexible-server/db?view=azure-cli-latest) で確認済み）を使用していたこと。誘因は、同 prompt が ADX/Kusto 用に「`az kusto database show` は `--database-name`」と明記する一方、隣接する postgres の `db show` の正しい引数を明記しておらず、agent が構造的に類似する2コマンドの引数規約を混同したこと。加えて検証スクリプトの `az_tsv() { az "$@" -o tsv 2>/dev/null }` が stderr と終了コードを握り潰すため、「リソース未作成による正当な FAIL」と「引数エラーで恒久的に失敗するスクリプト欠陥」を区別できず、Step.1.2 の RED フェーズ自己レビューで見逃されていた（2026-07-02 run `20260702T155130-4a3032` で実証）。

- **Step.1.2 prompt（verify 生成元）** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md)): §3 出力（成果物）「1. リソース存在検証」に、PostgreSQL Flexible Server 配下のデータベース存在確認コマンド `az postgres flexible-server db show`（`--query name -o tsv` 込み）の正しい引数（`--name`/`-n`）を明記し、ADX/Kusto の `az kusto database show --database-name` とはコマンド体系が異なるため混同しないよう明示的に対比した。
- **ASDW verify contract gate** ([hve/artifact_validation.py](hve/artifact_validation.py)): `validate_asdw_data_verify_script()` に、PostgreSQL セクション内で `flexible-server db show` と `--database-name` が共起する場合を検出し fail にする静的チェックを追加した。Step.1.2（生成直後）・Step.1.3（入力として再利用時）の両方の gate 呼び出しに自動的に適用される。コメント行（`#` 以降）を除去してから判定するため、正しい引数を解説するコメント文言自体を誤検知しない（敵対的レビューで発見した false positive を修正済み）。
- **回帰ガード** ([hve/tests/test_artifact_validation_deploy_gate.py](hve/tests/test_artifact_validation_deploy_gate.py), [hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)): `test_asdw_data_verify_validator_rejects_postgresql_db_show_database_name_flag` / `test_asdw_data_verify_validator_accepts_postgresql_db_show_name_flag` / `test_asdw_data_verify_validator_accepts_postgresql_db_show_short_name_flag` / `test_asdw_data_verify_validator_does_not_flag_database_name_mentioned_only_in_comment`（静的 gate の誤用検出・`--name`/`-n` 正常系・コメント誤検知防止）、および `test_data_testcoding_prompt_has_postgres_db_show_flag_guidance`（prompt の新規ガイダンス文言）を追加した。
- **既知の制約**: 検証スクリプトの `az_tsv() { az "$@" -o tsv 2>/dev/null }` が stderr・終了コードを握り潰す設計自体は今回のスコープ外（オーバーエンジニアリング回避のため意図的に未修正）。将来、他の az CLI コマンドで同種の引数誤りが発生した場合も RED フェーズで見逃されうる。
- **検証**: `.venv\Scripts\python.exe -m pytest hve/tests/test_artifact_validation_deploy_gate.py hve/tests/test_asdw_web_data_deploy_contract.py -q` → 90 passed。修正前の静的チェックが実際の `src/infra/azure/verify-data-resources.sh`（本インシデントの実ファイル）を正しく検出すること、および修正後は同ファイルに対する誤検知が発生しないことを個別に実行して確認した。

### Changed — ASDW-WEB Step.2.2 追加Azureサービス作成を並列実行化

**概要**: ASDW-WEB Step.2.2（Custom Agent `Dev-Microservice-Azure-AddServiceDeploy`）が生成する `create.sh` のサービス作成タスク（`services/<service>.sh`）を、逐次呼び出しからバックグラウンドジョブによる並列実行に変更した。`docs/azure/azure-services-additional.md` に記載された「ネットワーク境界」カテゴリ（Private Endpoint 等）が同ステップ内の他サービス（Foundry / Key Vault / データストア等）のリソースIDに依存するという実在の制約を踏まえ、Wave A（ネットワーク境界以外を並列実行）→ Wave B（ネットワーク境界を Wave A 完了後に実行）の2段階構成とした。並列実行に伴うログ混線・`created-resources.json` 書き込み衝突・実行権限ビット欠落（Windows checkout 時）のリスクにも対応した。

- **Prompt** ([.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md)): §3.3.1 に「サービス作成の並列実行方針」節を新設し、2 waves 構成・`bash` 経由起動（実行権限ビット非依存）・サービス別ログファイル分離・全ジョブ `wait` 後の終了コード集約・サービス別断片ファイル経由での `created-resources.json` 結合（`jq` 利用可能時は `jq -s`、未導入環境は `python3` フォールバック）を規定した。§2 成果物節にログ/断片ファイルの出力先を追記した。
- **Step template** ([.github/scripts/templates/asdw-web/step-2.2.md](.github/scripts/templates/asdw-web/step-2.2.md)): 並列実行方針（Wave A/Wave B）への参照ポインタを1行追加した。
- **Tests** ([hve/tests/test_asdw_web_addservice_deploy_contract.py](hve/tests/test_asdw_web_addservice_deploy_contract.py)): 並列実行契約（並列実行文言・`wait "$pid"`・旧逐次実行文言の不在・Wave A/B・ネットワーク境界・`created-resources.d` 書き込み衝突防止・`bash` 起動・step-2.2 テンプレのポインタ）を検証する5件の契約テストを追加した。
- **対象外**: GitHub Cloud 経路の埋め込みコピー（`.github/workflows/auto-app-dev-microservice-web-reusable.yml` 等）は既存の OUT-OF-SYNC NOTICE 方針を踏襲し今回は同期しない。Step.1.3/3.4/4.3 はサービス単位のサブスクリプト分解構造を持たないため対象外。
- **検証**: `python -m pytest hve/tests/test_asdw_web_addservice_deploy_contract.py hve/tests/test_azure_microsoft_learn_mcp_contract.py hve/tests/test_artifact_validation_deploy_gate.py -q` → 82 passed。各編集後に敵対的レビューを実施し、Major 3件（見出しレベルの番号体系不整合、実行権限ビットに依存する起動方法、`jq` 未導入環境への未対応）と Minor 2件（中間ファイルの明記漏れ、テストの文言完全一致による脆性）を検出・修正した。

### Changed — HVE GUI ステータスバーの「使用するモデル」/「Effort」表示を選択可能な UI に変更

**概要**: 直前の変更でステータスバーに追加した「使用するモデル」/「Effort」の読み取り専用表示を、その場で選択できる UI に変更した。「HVE 設定」→「基本設定」と共有する実行時ウィジェット（`_page_options.c1.model` / `.effort`）をステータスバーへそのまま re-parent することで、選択肢投入・Effort 動的切替・モデル再取得対応ロジックを重複実装せずに転用した。選択変更は即座に `settings_store` へ保存し、「HVE 設定」ダイアログを開いている場合は同じ値をそちらのコンボへも反映する（反映しないと、後で当該ダイアログの別項目を保存した際にステータスバーでの選択が古い値で上書きされてしまうため）。

- **GUI** ([hve/gui/main_window.py](hve/gui/main_window.py)): `_setup_status_bar()` から読み取り専用の `_model_status_label`（QLabel）と `_refresh_model_status_label()` を削除し、代わりに `self._page_options.c1.model` / `.effort` を re-parent したコンテナ（「使用するモデル」/「Effort」キャプション付き）をステータスバーへ配置。新規メソッド `_on_execution_model_or_effort_changed()` を追加し、選択変更時に `settings_store.set_option("model", ...)` / `set_option("reasoning_effort", ...)` を即時実行、「HVE 設定」ダイアログが表示中であれば同ダイアログの C1 セクションのコンボへも同じ値を反映する（`getattr` で安全に取得し、値が既に一致する場合は再設定しない）。シグナル連鎖（設定ダイアログ側の autosave 再発火）は値が一致した時点で自然停止し無限ループにはならない。
- **ドキュメント** ([users-guide/hve-gui-getting-started.md](users-guide/hve-gui-getting-started.md), [users-guide/hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md), [users-guide/hve-technical-architecture.md](users-guide/hve-technical-architecture.md)): 「使用するモデル」表示に関する記述を「常に表示」から「選択可能・変更は即座に settings_store へ保存・設定ダイアログにも反映」に更新した。
- **Tests** ([hve/gui/tests/test_main_window_model_status_label.py](hve/gui/tests/test_main_window_model_status_label.py)): 旧・読み取り専用ラベルのテストを全面的に置き換え、re-parent されたコンボの同一性・選択可能性・Effort 動的切替の回帰・`settings_store` への即時永続化・開いている設定ダイアログへの同期・設定ダイアログ未表示時に例外が発生しないことを検証する12件のテストへ更新した。
- **検証**: `.venv\Scripts\python.exe -m pytest hve/gui/tests/test_main_window_model_status_label.py -q` → 12 passed。加えて `test_model_reload.py` / `test_page_options_context_tier.py` / `test_page_options_effort.py` / `test_page_options_effort_cost.py` / `test_settings_output_controls_relayout.py` / `test_github_section_consolidation.py` / `test_main_window_settings_fetch_wiring.py` / `test_status_banner.py` / `test_page_options_fetch_models_button.py` / `test_settings_window_fetch_models_signal.py` / `test_settings_apply_skip_keys.py` / `test_settings_apply_sources_persistence.py` の回帰確認で 68 passed。実装時に発見した型チェッカーの警告（`QWidget` に `.model`/`.effort` 属性なし）は既存の `getattr` パターンで解消した。各タスク完了ごとに敵対的レビューを実施し、テスト側の不備（テスト用モデルを片方のコンボにしか追加していなかった）を1件発見・修正した。

### Changed — HVE GUI ステータスバーと「HVE 設定」基本設定のモデル関連 UI を整理

**概要**: HVE GUI 画面最下部のステータスバーから認証専用ボタン「Copilot にログイン」を削除した（GitHub Copilot SDK への認証は CLI `python -m hve login` に一本化）。代わりに「利用できるモデルの取得」ボタンの右側へ、現在設定されているモデル名と Effort を読み取り専用で表示する「使用するモデル」表示を追加した。また「HVE 設定」→「基本設定」の一番上に、ステータスバーと全く同じ「利用できるモデルの取得」ボタンを追加し、モデル一覧取得をどちらの画面からも実行できるようにした。新規の表示・ボタンは独自のデータを持たず、既存の `_C1Basic`（`self._page_options.c1`）と `hve.models_cache` を単一の情報源として参照・共有する。

- **GUI** ([hve/gui/main_window.py](hve/gui/main_window.py)): ステータスバーから `_btn_copilot_login` および `_on_copilot_login_clicked` / `_on_copilot_login_finished` を削除。「利用できるモデルの取得」ボタンの右側に読み取り専用の「使用するモデル」表示ラベルを追加し、`_page_options.c1.model` / `.effort` の変更に追随する `_refresh_model_status_label()` を実装した（`reload_models()` は内部で `blockSignals` するため `_on_models_fetched()` からも明示的に呼び出す）。「HVE 設定」ダイアログの「利用できるモデルの取得」ボタン押下（`SettingsWindow.fetch_models_requested`）を既存の `_on_login_clicked()` に接続し、処理を完全に共通化した。
- **GUI** ([hve/gui/page_options.py](hve/gui/page_options.py)): `_C1Basic`（基本設定セクション）の最上部に「利用できるモデルの取得」ボタンを追加し、押下時に新規 `fetch_models_requested` シグナルを emit するようにした（実処理は MainWindow 側に一本化し重複コードを避けた）。
- **GUI** ([hve/gui/settings_window.py](hve/gui/settings_window.py)): `SettingsWindow` に `fetch_models_requested` シグナルを追加し、「基本設定」セクション（C1）生成時に `_C1Basic.fetch_models_requested` を中継するようにした。
- **i18n** ([hve/gui/i18n/hve_gui_en_US.ts](hve/gui/i18n/hve_gui_en_US.ts)): 新規追加した「利用できるモデルの取得」ボタン（`_C1Basic` コンテキスト）と「使用するモデル」表示関連文言（`MainWindow` コンテキスト）の英語訳エントリを追加し、`pyside6-lrelease` で `.qm` を再生成した。
- **ドキュメント** ([users-guide/hve-gui-getting-started.md](users-guide/hve-gui-getting-started.md), [users-guide/hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md), [users-guide/hve-technical-architecture.md](users-guide/hve-technical-architecture.md), [users-guide/plugin-mcp-auth.md](users-guide/plugin-mcp-auth.md)): 「Copilot にログイン」ボタンへの言及を、CLI ログイン（`python -m hve login`）と、共通化された「利用できるモデルの取得」ボタン・新設の「使用するモデル」表示の説明に置き換えた。`users-guide/images/` 配下の SVG 2 点は調査の結果「Copilot にログイン」への直接言及がなく、変更不要と判断した。
- **Tests**: [hve/gui/tests/test_page_options_fetch_models_button.py](hve/gui/tests/test_page_options_fetch_models_button.py)（新規）、[hve/gui/tests/test_settings_window_fetch_models_signal.py](hve/gui/tests/test_settings_window_fetch_models_signal.py)（新規）、[hve/gui/tests/test_main_window_model_status_label.py](hve/gui/tests/test_main_window_model_status_label.py)（新規）、[hve/gui/tests/test_main_window_settings_fetch_wiring.py](hve/gui/tests/test_main_window_settings_fetch_wiring.py)（新規）、[hve/gui/tests/test_status_banner.py](hve/gui/tests/test_status_banner.py)（Copilot ログイン関連テストを削除しボタン不在を確認する回帰テストへ置換）。
- **検証**: `.venv\Scripts\python.exe -m pytest hve/gui/tests/test_page_options_fetch_models_button.py hve/gui/tests/test_settings_window_fetch_models_signal.py hve/gui/tests/test_status_banner.py hve/gui/tests/test_main_window_model_status_label.py hve/gui/tests/test_main_window_settings_fetch_wiring.py hve/gui/tests/test_i18n.py -q` → 39 passed。加えて `test_model_reload.py` / `test_page_options_context_tier.py` / `test_page_options_effort.py` / `test_page_options_effort_cost.py` / `test_settings_output_controls_relayout.py` / `test_github_section_consolidation.py` / `test_settings_window_no_hscroll.py` / `test_settings_window_mdq_tabs.py` / `test_settings_window_mdq_persistence.py` を含む回帰確認で 70 passed、主要な `test_main_window_*.py` 群 12 ファイルと `test_footer_stats.py` の回帰確認で 100 passed。`pyside6-lrelease` による `.qm` 再生成成功（"Generated 364 translation(s)"、XML 破損なし）、`QTranslator` 実地検証で新規文言の英訳解決を確認。各タスク完了ごとに敵対的レビューを実施し指摘事項を都度反映した。

### Added — HVE GUI に実行中ワークフローへの割り込み送信（Steering）機能を追加

**概要**: HVE GUI の「GitHub Copilot Chat」パネルから、実行中のメインステップへ割り込みメッセージを送信できる Steering 機能を追加した。GitHub Copilot SDK の `session.send(mode="immediate")`（Steering）機能を活用し、オーケストレータ（別プロセス）が保持する既存の `CopilotSession` に対し、GUI からファイルベース IPC（既存の QA IPC パターンを踏襲）経由で割り込みテキストを渡す。オーケストレータは Phase 1 メインタスクの `send_and_wait` 待機と並行して IPC ディレクトリを polling し、検出したメッセージを `mode="immediate"` で注入する。並列ステップ実行中（対象 step が複数）や IPC ディレクトリ未生成時はトグルを無効化し、既存の使い捨て `copilot -p` 経路にはフォールバックせず安全側に倒す設計とした。

- **`hve/config.py`**: `SDKConfig.steering_ipc_dir` フィールドを追加。
- **`hve/__main__.py`**: `orchestrate` サブコマンドに `--steering-ipc-dir <path>` 引数を追加し `cfg.steering_ipc_dir` へ反映。
- **`hve/runner.py`**: 新規 `StepRunner._poll_steering_ipc()`（IPC ディレクトリを 1 秒間隔で polling し `steering-<step_id>-<epoch_ms>.request.json` を検出→ `session.send(text, mode="immediate")` →ファイル削除、`steering_ipc_dir` 未設定時は即終了）。既存 `_send_and_wait_with_model_call_failure_guard()` に `asyncio.create_task` で並行タスクとして組み込み、メインタスク完了時に確実にキャンセルするよう拡張。
- **`hve/gui/orchestrate_args.py`**: `OrchestrateArgs.steering_ipc_dir` フィールドと `to_argv()` への反映を追加。
- **`hve/gui/page_workbench.py`**: ワークフロー起動時に Steering IPC ディレクトリ（`<repo_root>/.hve/steering-ipc/<uuid>/`）を常時生成。新規公開メソッド `resolve_active_main_step_id()`（`running_step_ids` が単一要素の場合のみ対象 step_id を返す）、`active_steering_ipc_dir()` を追加。
- **`hve/gui/steering_ipc_writer.py`（新規）**: `write_steering_request(ipc_dir, step_id, text)` — `_poll_steering_ipc` と同一のファイル名規則・アトミック書き込みで IPC リクエストを生成する薄いヘルパー。
- **`hve/gui/main_window.py`**: `WorkbenchPage` 生成直後に `CopilotChatPanel.set_workbench_page()` を呼び出す配線を追加（メソッド未実装時も安全にスキップする防御的実装）。
- **`hve/gui/copilot_chat_panel.py`**: 「実行中ワークフローへ割り込む (Steering)」チェックボックスを追加（既定 OFF）。対象 step_id と IPC ディレクトリが揃っている場合のみ有効化（1秒間隔で動的判定）。ON 時の送信は `write_steering_request()` のみを呼び、既存の使い捨て `copilot -p` プロセスは起動しない。
- **Tests**: [hve/tests/test_runner_steering_ipc.py](hve/tests/test_runner_steering_ipc.py)（新規、7 tests）、[hve/gui/tests/test_orchestrate_args.py](hve/gui/tests/test_orchestrate_args.py)（`TestSteeringIpcDirToArgv` 追加）、[hve/gui/tests/test_page_workbench_active_session.py](hve/gui/tests/test_page_workbench_active_session.py)（新規、6 tests）、[hve/gui/tests/test_steering_ipc_writer.py](hve/gui/tests/test_steering_ipc_writer.py)（新規、6 tests）、[hve/gui/tests/test_main_window_dock_integration.py](hve/gui/tests/test_main_window_dock_integration.py)（2 tests 追加）、[hve/gui/tests/test_copilot_chat_panel_steering.py](hve/gui/tests/test_copilot_chat_panel_steering.py)（新規、6 tests）。
- **検証**: 各タスク完了時に既存テストの回帰確認を実施（regression なし）。加えて実 Copilot CLI を用いた PoC（`work/copilot-steering-poc/`）で、当初検討した「外部 CLI サーバーモード + `resume_session`」方式（方式1）は SDK 公式ドキュメント記載の「同一セッションへの同時アクセスは未定義動作」という制約により不採用と判断し、採用した「IPC 経由でオーケストレータ自身が `send(mode="immediate")` を呼ぶ」方式（方式2）は実 Copilot CLI を用いたエンドツーエンド検証（`work/copilot-steering-poc/t15_e2e_check.py`）で動作を実証（`steering_e2e_ok: True`）。

### Fixed — Azure 公式情報根拠の必須化と ASDW-WEB DataVerify false positive を抑止

**概要**: ASDW-WEB Step.1.2 (`Dev-Microservice-Azure-DataTestCoding`) が生成した `verify-data-resources.sh` の PostgreSQL Flexible Server `state=Ready` 判定を、HVE の静的契約 gate が `az_tsv` wrapper / `verify_postgres()` / `postgres_count_via_aci()` 分離構造として認識できず、`az postgres flexible-server show` 未検出および PostgreSQL への `provisioningState` 一律適用として誤検出する問題を修正した。あわせて Azure サービス選定・Azure CLI・SDK・REST API・SKU・状態プロパティ・サンプルコードを扱う ASDW-WEB / AAD-WEB / ADFDV / AAGD の active Step template、関連 prompt、共通 Skill に、Microsoft Learn MCP が利用可能な場合の必須参照と title / URL / 確認事項の根拠記録を明文化した。

- **ASDW DataVerify contract gate** ([hve/artifact_validation.py](hve/artifact_validation.py)): `az_tsv() { az "$@" -o tsv ... }` の薄い wrapper 経由の `postgres flexible-server show --query state` を PostgreSQL Flexible Server 状態確認として認識し、`verify_postgres()` と `postgres_count_via_aci()` に分離された ACI fallback も検査対象に含めるよう修正。PostgreSQL セクション外の Cosmos / Storage / Synapse `provisioningState` を PostgreSQL 違反として誤検出しないようにした。
- **Microsoft Learn MCP grounding** ([.github/skills/agent-common-preamble/SKILL.md](.github/skills/agent-common-preamble/SKILL.md), [.github/skills/testing/tdd-red-green-reality/SKILL.md](.github/skills/testing/tdd-red-green-reality/SKILL.md)): Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、Microsoft Learn MCP が利用可能なら必ず参照し、参照した title / URL / 確認事項を `{WORK}` または成果物の根拠欄に記録する共通規律を追加。未取得時は `要確認（Microsoft Learn MCP 未取得）` とし、推測で確定しないよう明記。
- **Azure workflow prompts/templates** ([.github/prompts/](.github/prompts/), [.github/scripts/templates/](.github/scripts/templates/)): ASDW-WEB Step.1/2/3/4/5 の Azure 関連 Step、AAD-WEB Step.2.5、ADFDV Azure データフロー系 Step、AAGD Azure AI Foundry 系 Step に Microsoft Learn MCP 参照・根拠記録・未取得時留保の契約を追加。render 時には Azure 関連 active Step template に同規律を重複なく補う最小注入も追加。
- **Single-step resume policy** ([.github/scripts/templates/_shared/existing-artifact-policy.md](.github/scripts/templates/_shared/existing-artifact-policy.md)): 単独 Step 実行でも `## 入力` に列挙されたファイルと現在の作業ツリーに存在する既存出力ファイルを読み、未決事項・TBD・制約・stale / 契約不一致を確認してから実行する規律を追加。
- **Tests** ([hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py), [hve/tests/test_artifact_validation_deploy_gate.py](hve/tests/test_artifact_validation_deploy_gate.py), [hve/tests/test_azure_microsoft_learn_mcp_contract.py](hve/tests/test_azure_microsoft_learn_mcp_contract.py), [hve/tests/test_tdd_red_green_reality_contract.py](hve/tests/test_tdd_red_green_reality_contract.py), [hve/tests/test_template_engine.py](hve/tests/test_template_engine.py)): `az_tsv` / `verify_postgres()` / `postgres_count_via_aci()` 形式の validator 回帰、Azure 関連 active Step template の Microsoft Learn MCP 契約、共通 Skill 契約、既存成果物ポリシーを固定するテストを追加。
- **検証**: `python -m pytest hve/tests/test_asdw_web_data_deploy_contract.py hve/tests/test_artifact_validation_deploy_gate.py hve/tests/test_azure_microsoft_learn_mcp_contract.py hve/tests/test_tdd_red_green_reality_contract.py hve/tests/test_template_engine.py::TestExistingArtifactPolicyTemplate hve/tests/test_template_engine.py::TestAzureOfficialInfoSectionInjection -q` → 105 passed。`python -m pytest hve/tests/test_template_engine.py` 全体では既存の対話入力テスト `TestCollectParams::test_aad_collect_params_with_multiple_app_ids` が `StopIteration` で失敗するが、今回差分に `collect_params` / `_prompt_yes_no` / `selected_steps` / `create_remote_mcp_server` 変更は無く、変更対象外として切り分け済み。

### Fixed — ASDW-WEB DataVerify の PostgreSQL ACI fallback と model.call_failure timeout を抑止

**概要**: ASDW-WEB Step.1.3 (`Dev-Microservice-Azure-DataDeploy`) が Step.1.2 責務成果物 `verify-data-resources.sh` の PostgreSQL 件数取得 ACI fallback 不備で GREEN 到達不能となり、その後 `model.call_failure` 連続発生を未知イベントとして扱ったまま `step-timeout` まで待ち続ける問題を、生成元 prompt と HVE gate / runner の最小修正で抑止した。`/docs` `/src` のラン固有再生成物は直接修正対象にせず、次回以降も効く契約・静的 gate・StepRunner 挙動に限定して修正した。

- **DataTestCoding prompt** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md)): PostgreSQL 件数取得の ACI fallback 生成時に `--os-type Linux`、`--secure-environment-variables PGPASSWORD=...`、`PGSSLMODE=require` を必須化し、アクセストークンや UPN を `--command-line` に直接展開しないよう明記。
- **ASDW verify contract gate** ([hve/artifact_validation.py](hve/artifact_validation.py)): `validate_asdw_data_verify_script()` を強化し、PostgreSQL ACI fallback が `postgres:16-alpine`、`--os-type Linux`、secure env、`PGSSLMODE` / `PGHOST` / `PGUSER` / `PGDATABASE` を満たさない場合に Step.1.2 を fail にするようにした。
- **DataDeploy prompt** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md)): AC-1 `❌` とブロッカー理由を `ac-verification.md` に確定した後は、`docs/` / `src/` 更新、service catalog 追記、追加 grep / diff / secret scan、firewall 調査、verify 再試行へ進まず、`{WORK}` 証跡付き fail として即終了する規律を追加。
- **StepRunner** ([hve/runner.py](hve/runner.py)): Phase 1 メインタスク中の `model.call_failure` を warning / stats event として記録し、同一 step で3回に達した場合は `send_and_wait` をキャンセルして Step を早期 fail させ、2時間の step timeout まで待ち続ける状態を避けるようにした。
- **Tests** ([hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py), [hve/tests/test_artifact_validation_deploy_gate.py](hve/tests/test_artifact_validation_deploy_gate.py), [hve/tests/test_runner.py](hve/tests/test_runner.py)): PostgreSQL ACI fallback 契約、AC-1 `❌` 後の即終了規律、`model.call_failure` fail-fast を固定するテストを追加。
- **検証**: `& .\.venv\Scripts\python.exe -m pytest hve/tests/test_asdw_web_data_deploy_contract.py hve/tests/test_artifact_validation_deploy_gate.py hve/tests/test_runner.py -q -k "not test_real_sdk_assistant_usage_data_extraction"` → 236 passed / 1 deselected。`test_runner.py` 全体実行では実 SDK の `AssistantUsageData.copilot_usage` 公開属性差異による既存契約テスト 1 件のみ失敗（今回変更と無関係）。

### Fixed — ASDW-WEB Step.1.3 の `⏳` スタブ放置と偽 GREEN 記録を prompt 契約で抑止

**概要**: ASDW-WEB Step.1.3 (`Dev-Microservice-Azure-DataDeploy`) が `ac-verification.md` を作成済みでも AC-1 を初期スタブの `⏳` のまま放置し、`deploy_ac_gate_failed` (`AC-1 is not GREEN`) で停止する再発を抑止した。`/docs` `/src` の再生成物は直接修正せず、生成元の DataDeploy prompt と契約テストに限定して、verify 直後に `ac-verification.md` を最優先で確定する規律、実 verify に基づかない GREEN 記録の禁止、tool failure / context 逼迫検知後の打ち切り、長時間コマンド出力の context 節約を明文化した。

- **DataDeploy prompt** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md)): `ac-verification.md` は verify 直後・最初のツール操作で確定し、cleanup / 完了報告 / docs 判定 / 一時ログ削除より前に AC-1 を `✅` または `❌` へ更新するよう明記。GREEN は `exit 0 + verify ログの PASS 確認` とし、`⏳` のまま他作業へ進むことを禁止した。
- **捏造防止 / 打ち切り規律** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md)): 未実行の firewall 復旧 / create 再実行 / verify 再試行 / 件数取得 / GREEN 到達を実行済みのように記録することを禁止。実 verify 結果が無い場合は AC-1 を `❌` とし、`verify 未実行 / 結果確認不能` を記録して終了するよう固定した。
- **Context 節約** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md)): `create` / `data-registration-script.sh` / `verify-data-resources.sh` などの長時間コマンド出力を会話へ全量貼らず、必要に応じて `{WORK}` 配下ログへ保存し、確認は exit code と末尾 / `[ERROR]` / `[FAIL]` / `[OK]` など必要最小限へ限定する規律を追加。
- **Tests** ([hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)): verify 直後の AC 確定、偽 GREEN 記録禁止、長時間コマンド出力の context 節約規律を固定する契約テストを追加・強化。
- **検証**: `& .\.venv\Scripts\python.exe -m pytest hve/tests/test_asdw_web_data_deploy_contract.py -q` → 22 passed。対象差分の `git diff --check` は指摘なし。

### Added — GUI 設定画面に `context_tier`（default / long_context）選択を追加し `create_session` へ伝播

**概要**: GUI 設定画面（C1「基本設定」）のモデル選択直下に、SDK の `create_session(context_tier=...)` を制御する選択ボックス `context_tier` を追加した。選択肢は `default` / `long_context` の 2 つで、既定は `long_context`（対応モデルでロングコンテキストを有効化）。設定値は GUI → CLI `--context-tier` → `SDKConfig.context_tier` → セッション生成（runner / orchestrator 共通ヘルパー）まで end-to-end で伝播し、全セッションの `create_session` に `contextTier` として渡る。`_C1Basic` は Step 1 右ペインと設定画面で共有されるため、両画面に表示される（既存の theme / verbosity と同じ挙動）。

- **GUI ウィジェット** ([hve/gui/page_options.py](hve/gui/page_options.py)): `_C1Basic` のメインモデル行直後に `context_tier` QComboBox（userData=`default` / `long_context`、既定 `long_context` を選択）を追加。`to_args()` で `args.context_tier = self.context_tier.currentData()` を反映。
- **設定の永続化** ([hve/gui/settings_store.py](hve/gui/settings_store.py), [hve/gui/settings_apply.py](hve/gui/settings_apply.py)): `defaults()` の C1 群に `"context_tier": "long_context"` を追加し、`_SECTION_FIELDS["C1"]` に `"context_tier": "context_tier"` マッピングを追加（autosave / load / save 経路に接続）。
- **GUI → CLI 引数** ([hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py)): `OrchestrateArgs.context_tier`（既定 `long_context`）を追加し、`to_argv()` で truthy 時に `--context-tier <値>` を出力。
- **CLI 引数 → SDKConfig** ([hve/__main__.py](hve/__main__.py), [hve/config.py](hve/config.py)): `orchestrate` パーサに `--context-tier`（`choices=["default", "long_context"]`）を追加し `cfg.context_tier` へ転送。`SDKConfig.context_tier: Optional[str] = None`（CLI 直接実行時の従来挙動を保つため既定 None。GUI 既定の long_context は GUI 層が担う）を追加。
- **セッション注入** ([hve/runner.py](hve/runner.py), [hve/orchestrator.py](hve/orchestrator.py)): 両モジュールの全セッション生成が経由する `_create_session_with_auto_reasoning_fallback` で、`config.context_tier` が truthy のとき `create_session` の opts に `context_tier` を注入。未サポート SDK（`TypeError: unexpected keyword argument`）に備え、`reasoning_effort` と同様に strip フォールバック対象へ `context_tier` を追加。
- **Tests** ([hve/gui/tests/test_orchestrate_args.py](hve/gui/tests/test_orchestrate_args.py), [hve/tests/test_context_tier_cli.py](hve/tests/test_context_tier_cli.py), [hve/tests/test_settings_store_context_tier.py](hve/tests/test_settings_store_context_tier.py), [hve/gui/tests/test_page_options_context_tier.py](hve/gui/tests/test_page_options_context_tier.py), [hve/tests/test_session_context_tier.py](hve/tests/test_session_context_tier.py)): to_argv 変換、CLI→config 往復・choices 検証、settings 既定/往復/マッピング、`_C1Basic` コンボの既定/項目/`to_args`、runner/orchestrator のセッション注入・未指定時非注入・未サポート SDK strip を検証。
- **検証**: `& .\.venv\Scripts\python.exe -m pytest hve/gui/tests/test_orchestrate_args.py hve/tests/test_context_tier_cli.py hve/tests/test_settings_store_context_tier.py hve/gui/tests/test_page_options_context_tier.py hve/tests/test_session_context_tier.py hve/tests/test_cloud_session_cli.py -q` → 37 passed。`context_tier` 既定 long_context が GUI→CLI→SDKConfig を往復し `create_session` へ到達することをモック検証。Footer の Context 上限実測（tokenLimit）は AI クレジット消費を伴うため対象外。

### Fixed — ASDW-WEB DataVerify の stale 成果物通過と DataDeploy 証跡未生成診断を抑止

**概要**: ASDW-WEB Step.1.2 (`Dev-Microservice-Azure-DataTestCoding`) が既存 `src/infra/azure/verify-data-resources.sh` を再生成せず、古い PostgreSQL `provisioningState=Succeeded` 判定を残したまま success になる問題を抑止した。Step.1.2 完了後に verify スクリプトの内容契約を検査し、PostgreSQL Flexible Server が `state=Ready` 判定になっていない stale 成果物を fail にする。あわせて Step.1.3 (`Dev-Microservice-Azure-DataDeploy`) のスコープ外タスク脱線を prompt/template で禁止し、`ac-verification.md` 未生成時の runner 診断を work root 不在 / Issue-* 不在で区別できるようにした。

- **ASDW verify contract gate** ([hve/artifact_validation.py](hve/artifact_validation.py), [hve/runner.py](hve/runner.py)): `validate_asdw_data_verify_script()` を追加し、Step.1.2 DataTestCoding 後に `verify-data-resources.sh` の PostgreSQL Flexible Server 判定が `--query state` + `Ready` であることを検査。`provisioningState` / `provisioningState=Succeeded` を PostgreSQL に一律適用している場合は Step を fail にする。
- **Prompt / Template** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md), [.github/scripts/templates/asdw-web/step-1.2.md](.github/scripts/templates/asdw-web/step-1.2.md), [.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md), [.github/scripts/templates/asdw-web/step-1.3.md](.github/scripts/templates/asdw-web/step-1.3.md)): 既存 verify が stale の場合は更新必須とし、Step.1.2 での docs 構成整理 / `docs/README.md` 提案 / カタログ再編成を禁止。DataDeploy では Word / docx / chart 作成、TODO / todos SQL query、docs 構成整理などスコープ外作業への脱線を禁止し、確認不能時も AC-1 `❌` を `ac-verification.md` に記録して終了するよう明記。
- **Deploy AC gate diagnostics** ([hve/runner.py](hve/runner.py)): `ac-verification.md` 未生成時の診断を、agent work root 自体が無い場合と Issue-* が無い場合で区別。console-log で Word/docx/chart / TODO/SQL query / `$null` 書き込みなどの脱線・実成果物未生成を確認するよう案内を補強。
- **Tests** ([hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py), [hve/tests/test_artifact_validation_deploy_gate.py](hve/tests/test_artifact_validation_deploy_gate.py)): stale PostgreSQL 判定の validator テスト、正常な `state=Ready` 判定の受け入れテスト、DataTestCoding Step.1.2 専用 gate、DataDeploy work root 未生成診断の回帰テストを追加。
- **検証**: `python -m pytest hve/tests/test_asdw_web_data_deploy_contract.py hve/tests/test_artifact_validation_deploy_gate.py -q` → 68 passed。

### Fixed — ASDW-WEB Data Verify の PostgreSQL 状態判定とラン固有証跡の記録先を修正

**概要**: ASDW-WEB Step.1.3 (`Dev-Microservice-Azure-DataDeploy`) が `AC-1 is not GREEN` で停止した事象について、毎 run 再生成される `/docs` `/src` 成果物ではなく生成元契約を修正した。Step.1.2 (`Dev-Microservice-Azure-DataTestCoding`) の verify 生成指示で、PostgreSQL Flexible Server に `provisioningState=Succeeded` を一律適用せず、実測で確認した `state=Ready` を確認するよう明記した。あわせて、再実行ログ・verify 失敗理由・AC 証跡などのラン固有情報は `work-status.md` / `ac-verification.md` に閉じ、`docs/` / `src/` へ追記しない方針を DataDeploy prompt/template に固定した。

- **DataTestCoding prompt / Step.1.2 template** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md), [.github/scripts/templates/asdw-web/step-1.2.md](.github/scripts/templates/asdw-web/step-1.2.md)): データストア状態確認を「サービス別正常状態」として定義し、PostgreSQL Flexible Server は `az postgres flexible-server show --query state -o tsv` が `Ready`、Cosmos DB / Storage / ADX は `provisioningState=Succeeded`、Azure SQL Database は `status=Online` を確認する契約へ更新。
- **DataDeploy prompt / Step.1.3 template** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md), [.github/scripts/templates/asdw-web/step-1.3.md](.github/scripts/templates/asdw-web/step-1.3.md)): GREEN 条件を「リソース存在 + サービス別正常状態 + 件数一致」に更新し、ラン固有の再実行ログ・検証失敗理由・AC 証跡は `{WORK}` 配下に記録して `docs/` / `src/` へ追記しないことを明文化。
- **Tests** ([hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)): PostgreSQL Flexible Server の `state=Ready` 契約と、ラン固有証跡を `work` に閉じる契約の回帰テストを追加。
- **検証**: `python -m pytest hve/tests/test_asdw_web_data_deploy_contract.py -q` → 17 passed。`python -m pytest hve/tests/test_artifact_validation_deploy_gate.py -q` → 46 passed。

### Fixed — ASDW-WEB Step.1.3 の `ac-verification.md` 未生成停止を prompt/template/io-contract 契約で抑止

**概要**: ASDW-WEB Step.1.3 (`Dev-Microservice-Azure-DataDeploy`) が GREEN 未達時に `ac-verification.md` を作成しないまま終了し、`deploy_ac_gate_failed`（`ac-verification.md not found`）で停止する再発を抑止した。`/docs` `/src` の再生成物は直接修正せず、生成元の契約に限定して、長時間 Azure 操作前に `work-status.md` / `ac-verification.md` の初期スタブを作る規律、`sample-data.json` に存在しない派生 Entity 件数を推測で GREEN 条件にしない規律、DataDeploy io-contract の work 成果物宣言を整備した。

- **DataDeploy prompt / Step template** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md), [.github/scripts/templates/asdw-web/step-1.3.md](.github/scripts/templates/asdw-web/step-1.3.md)): Azure 操作・依存インストール・verify 再実行へ進む前に `work-status.md` と `ac-verification.md` の初期スタブを作成し、AC-1 を `⏳` で仮記録する手順を追加。最終結果確定時は `work-artifacts-layout` の削除→新規作成ルールに従って `✅` / `❌` の最終版へ置き換える。
- **DataTestCoding prompt** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md)): `sample-data.json` に存在しない `ConversationTurn(派生)` / `AnswerLog(派生)` 等を推測で `EXPECT_*=1` にしないよう明文化。派生元・生成規則・期待件数を入力ファイルまたは Prompt / Template / io-contract 等の生成元契約で実証できない場合は、件数検証を `TBD（入力データなし）` とし GREEN 条件から外す。
- **io-contract** ([.github/io-contracts/Dev-Microservice-Azure-DataDeploy.yaml](.github/io-contracts/Dev-Microservice-Azure-DataDeploy.yaml), [.github/io-contracts/Dev-Microservice-Azure-DataDeploy--asdw-web--1.3.yaml](.github/io-contracts/Dev-Microservice-Azure-DataDeploy--asdw-web--1.3.yaml)): DataDeploy の `work-status.md` / `ac-verification.md` を top-level outputs として宣言し、Prompt / Template / Deploy AC gate の契約と整合させた。
- **Tests** ([hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)): 初期スタブ作成、派生件数の推測禁止、DataDeploy io-contract の work outputs を固定する契約テストを追加。
- **検証**: `test_asdw_web_data_deploy_contract.py` + `test_artifact_validation_deploy_gate.py` は **59 passed**。対象 DataDeploy io-contract 2件の YAML parse 成功（outputs=8 / outputs=3）。今回編集ファイルの `git diff --check` は指摘なし。

### Changed — GUI: CI/CD トグルを Deploy ステップ選択時のみ表示

**概要**: GUI Step 1 のワークフロー固有設定で常時表示していた「github.com で CI/CD を実行」「マージ後にローカル作業ブランチを削除」の 2 トグルを、Deploy ステップが選択された時のみ表示するよう変更した。表示トリガーは ASDW-WEB の Step 3.4 (Azure Compute Deploy) / 4.3 (Web アプリ Deploy) と ADFDV の Step 1.2 (Azure データリソース Deploy) / 3 (Azure Functions/コンテナ Deploy)。これにより CD を伴わないステップのみを実行する場合に、誤って自動 PR 作成・`auto-approve-ready` 付与・自動マージが走るのを防ぐ。Deploy ステップ未選択で 2 トグルが非表示になる際は内部状態を OFF にし、`enable_auto_merge` の双方向ミラーで設定画面（C5）側も OFF にする。「対象アプリケーション (APP-ID)」「Azure リソースグループ名」は従来どおり常時表示する。

- **GUI 表示条件** ([hve/gui/page_options.py](hve/gui/page_options.py)): `OptionsPage` に選択ステップ受信用の `set_selected_steps()` と `_selected_steps` を追加。`_refresh_specific_categories` で CI/CD 対応ワークフロー（`_CICD_TOGGLE_TRIGGER_STEPS`: `asdw-web`={3.4, 4.3} / `adfdv`={1.2, 3}）のいずれかで Deploy ステップが選択された時のみ 2 トグルを表示する集約判定を追加。CI/CD トグルは共通 LF（1 個）を asdw-web/adfdv で共有するため、ワークフロー個別ではなく集約で判定し、複数ワークフロー同時選択時に片方が Deploy 不要でも他方が Deploy 必要なら表示を維持する。CI/CD 対応ワークフロー未選択（初期状態・ard 等のみ選択）はトグルのデフォルト状態（`delete_local_merged_branch` の既定 ON 等）を保持する。非表示化時は `_set_cicd_toggles_off()` で OFF にする。
- **GUI 配線** ([hve/gui/main_window.py](hve/gui/main_window.py)): `WorkflowSelectPage.steps_selection_changed` を `_on_steps_selection_changed` に接続し、`all_enabled_steps()` を `OptionsPage.set_selected_steps()` へ転送（ステップのチェック変更で即時に表示条件を再評価）。ワークフロー選択変更時 (`_on_workflow_selection_changed`) も `set_workflows` の直後にステップ選択を反映。
- **テスト** ([hve/gui/tests/test_page_options_github_cicd.py](hve/gui/tests/test_page_options_github_cicd.py), [hve/gui/tests/test_main_window_cicd_steps_sync.py](hve/gui/tests/test_main_window_cicd_steps_sync.py)): ASDW-WEB(3.4/4.3) / ADFDV(1.2/3) の表示・非表示、非表示時 OFF、複数ワークフロー表示維持、CI/CD 非対応ワークフローのデフォルト保持、main_window のステップ選択 signal 配線を検証するテストを追加。
- **検証**: `test_page_options_github_cicd`（21 件）/ `test_main_window_cicd_steps_sync`（3 件）/ `test_workflow_select_options_sync` / `test_main_window_step_selection_autopilot` / `test_main_window_step_selection_plan` / `test_gui_imports` の計 74 件が PASS。

### Fixed — ASDW-WEB Step.1.3 の `deploy_ac_gate_failed`（ADX 検証スクリプトの非実在コマンド・ACI フォールバック非対称）を prompt 契約で抑止

**概要**: ASDW-WEB ワークフロー Step.1.3（`Dev-Microservice-Azure-DataDeploy`）が `deploy_ac_gate_failed`（`AC-1 is not GREEN`、ADX のみ未達）で停止した事象を調査し、`/docs` `/src` は毎 run 再生成され直接修正が無効なため、生成元の **prompt 層**に絞って最小修正した。根本原因は、Step.1.2（`Dev-Microservice-Azure-DataTestCoding`）が毎 run 再生成する `verify-data-resources.sh` の生成指針（prompt §3/§5.3/§8）が、件数検証手段を **Cosmos DB（SDK）と PostgreSQL（psql + ACI フォールバック）にのみ明示し、ADX (Kusto) を一切記述していなかった**こと。指針欠落により Agent は (1) 存在しない `az kusto query`（`az kusto` に `query` サブコマンドは無い）を件数取得に幻覚し、(2) `az kusto database show --name`（正=`--database-name`）を誤用し、(3) ADX データプレーン `*.kusto.windows.net:443` の egress 遮断に対する ACI フォールバック（PostgreSQL の `register_via_aci` と対称な経路）を欠いたスクリプトを生成していた。結果、egress 制約のローカル/CLI/GUI 環境では ADX 件数検証が構造的に GREEN 不能となり、`runner._run_deploy_ac_gate`（`_DEPLOY_AGENT_REALITY_AC["Dev-Microservice-Azure-DataDeploy"]=["AC-1"]`）が `AC-1 ❌` で fatal fail していた。これは過去に PostgreSQL 件数検証へ ACI フォールバックを追加した修正と同種の非対称欠落が ADX に残存していたもの。

- **Step.1.2 prompt（verify 生成元）** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md)): §3 データ件数検証・§5.3 検証スクリプト生成・§8 敵対的レビュー2回目に ADX 指針を追加。`az kusto query` 禁止（非実在コマンド）、件数取得は Kusto SDK（`azure-kusto-data`）+ `DefaultAzureCredential` または ADX REST `/v2/rest/query`、プロビジョニング状態は `az kusto database show --database-name`（`--name` 不可）、`*.kusto.windows.net:443` egress 遮断時は一時 ACI 経由フォールバック（`register_via_aci` と対称）で件数取得することを明文化（ACI は `postgres:16-alpine` 相当の既製 Kusto イメージが無いため汎用イメージ + REST/`curl` でクエリ可と明示）。
- **Step.1.3 prompt（register 生成元 / verify 実行）** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md)): step 4.5 GREEN 説明に ADX も egress 遮断されうる旨と、成果物 `data-registration-script.sh` の ADX 投入を ACI 経由フォールバックで完了させ verify の ADX 件数を GREEN へ到達可能に保つ指針を追加（verify スクリプト自体の不具合は Step.1.2 責務であり本 Agent は修正しないことも明記）。`<output_contract>` 必須セキュリティ要件に ADX 投入要件（成果物 `data-registration-script.sh` に限定し、件数取得＝verify は Step.1.2 成果物 `verify-data-resources.sh` の責務と明記、`az kusto query` 非依存 / Kusto SDK / ACI フォールバック）を Cosmos と対称に追加。
- **回帰ガード** ([hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)): `test_data_testcoding_prompt_has_adx_count_guidance` / `test_data_deploy_prompt_has_adx_aci_fallback_guidance` を追加し、両 prompt の ADX 指針（`az kusto query` 禁止・`--database-name`・`azure-kusto-data` / `azure-kusto-ingest`・`*.kusto.windows.net:443` ACI フォールバック）の消失を防止。DataDeploy テストは `az kusto query` を「存在しないコマンド」として禁止フレーミングする検証を含め、肯定（推奨）への反転も防御。
- **検証**: `test_asdw_web_data_deploy_contract`（9 件、新規2 件含む）/ `test_tdd_red_green_reality_contract` / `test_artifact_validation_deploy_gate` / `test_asdw_web_addservice_deploy_contract` 計 77 件 PASS。Azure CLI の事実（`az kusto` に `query` サブコマンド無し、`az kusto database show` は `--database-name`）は run ログの実測（`'query' is misspelled or not recognized`）と整合。

### Fixed — GUI/CLI: 失敗 Step 時の PR 作成抑止と ASDW-WEB DataDeploy timeout 抑止

**概要**: `enable_auto_merge` / `create_pr` 経路で Step 失敗後にも PR が作成され、`auto-approve-ready` 付与や自動マージ経路と混線し得る問題を是正した。失敗 Step がある場合は PR 作成を行わず、万一作成済みになった場合も自動化ラベル除去・PR close・head branch 削除を best-effort で試みる。あわせて ASDW-WEB Step.1.3 (`Dev-Microservice-Azure-DataDeploy`) が GREEN 未達時に timeout まで修正・実行を続けないよう、最大3回で打ち切って `AC-1 ❌` の `ac-verification.md` と `work-status.md` を必ず残す契約を prompt / template に固定し、`data-deploy.env` と `verify-data-resources.sh` の変数契約を明文化した。

- **PR 作成制御** ([hve/orchestrator.py](hve/orchestrator.py), [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py)): `executor.failed` が空でない場合は `_create_pr_if_needed()` を呼ばず、`_create_pr_if_needed()` 自体も `all_steps_succeeded=False` で fail-closed にした。失敗 Step がある場合の戻り値 `error` とサマリー文言も PR 作成スキップを明示するよう更新。
- **失敗 PR cleanup** ([hve/orchestrator.py](hve/orchestrator.py), [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py)): 作成済み失敗 PR に対して `auto-approve-ready` / `auto-qa` / `auto-context-review` ラベル削除、PR close、remote/local head branch 削除を best-effort で行う helper を追加。GitHub PR の物理削除は通常 API でできないため、supported な撤去手段として close + branch delete に限定。
- **DataDeploy 契約** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md), [.github/scripts/templates/asdw-web/step-1.3.md](.github/scripts/templates/asdw-web/step-1.3.md), [hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)): `verify-data-resources.sh` の GREEN 化試行を最大3回に固定し、GREEN 未達時は追加修正・追加実行を続けず `AC-1 ❌` を記録して終了する契約を追加。`data-deploy.env` には `SQL_SERVER_NAME` / `ADX_CLUSTER_NAME` / `STORAGE_IMMUTABLE_CONTAINER` など verify が参照する全変数を書き出すことを明記。
- **Deploy AC gate 診断 / GUI** ([hve/runner.py](hve/runner.py), [hve/tests/test_artifact_validation_deploy_gate.py](hve/tests/test_artifact_validation_deploy_gate.py), [hve/gui/page_options.py](hve/gui/page_options.py)): `ac-verification.md` 未生成時の診断に「GREEN 未達時も `AC-1 ❌` を記録して終了する必要がある」旨を追加し、GUI の `github.com で CI/CD を実行` 説明文も失敗 Step 時は PR を作成しない挙動へ更新。
- **検証**: `TestCreatePrIfNeeded` / `test_asdw_web_data_deploy_contract` / `test_artifact_validation_deploy_gate` / `test_page_options_github_cicd` / `test_gui_imports` の関連 99 件が PASS。

### Changed — GUI/CLI: Azure Deploy 検証ゲートと post-merge 確認を強化

**概要**: GUI/CLI の `enable_auto_merge` 経路で Azure Deploy step の検証妥当性を高めるため、ADFDV Deploy step を registry 駆動の実在系 AC gate 対象に追加し、Deploy Agent の `ac-verification.md` 契約を明確化した。auto-merge PR body には `ac-verification.md` の AC-ID / 内容 / 状態のみを転記し、`auto-approve-and-merge.yml` 側でも AC テーブル行を優先評価することで、StepRunner の AC gate と PR auto-merge gate の不整合を縮小した。PR merge 後は merge commit の check-runs を確認し、失敗または check-run 0 件の場合は検証成功扱いにしない。GUI の CI/CD トグル表示対象は、Deploy step を持つ `adfdv` に合わせた。

- **Deploy gate** ([hve/workflow_registry.py](hve/workflow_registry.py), [hve/tests/test_artifact_validation_deploy_gate.py](hve/tests/test_artifact_validation_deploy_gate.py)): ADFDV Step.1.2 (`Dev-Dataflow-DataDeploy`) に `reality_gate_acs=["AC-3"]`、Step.3 (`Dev-Dataflow-FunctionsDeploy`) に `reality_gate_acs=["AC-2", "AC-3"]` を追加し、allowlist 外 Agent でも registry 宣言で実在系 AC gate が効くことをテストで固定。
- **Prompt contract** ([.github/prompts/Dev-Dataflow-DataDeploy.prompt.md](.github/prompts/Dev-Dataflow-DataDeploy.prompt.md), [.github/prompts/Dev-Dataflow-FunctionsDeploy.prompt.md](.github/prompts/Dev-Dataflow-FunctionsDeploy.prompt.md), [hve/tests/test_adfdv_deploy_contract.py](hve/tests/test_adfdv_deploy_contract.py)): ADFDV Deploy Agent が `{WORK}ac-verification.md` を `Issue-<識別子>` 直下に作成し、実在系 AC を `✅` で記録する契約を明記。
- **PR body / Auto-approve gate** ([hve/orchestrator.py](hve/orchestrator.py), [.github/workflows/auto-approve-and-merge.yml](.github/workflows/auto-approve-and-merge.yml), [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py), [.github/scripts/python/tests/test_auto_approve_and_merge_workflow.py](.github/scripts/python/tests/test_auto_approve_and_merge_workflow.py)): auto-merge PR body に AC テーブルの先頭3列のみを転記し、workflow 側では AC テーブル行の未達 (`❌` / `⏳` / `NEEDS-VERIFICATION` 等) と agent-specific AC (`AC-2` / `AC-3` / `AC-6` / `AC-8` / `AC-9` / `AC4B-1`) を評価するようにした。AC テーブル行がない場合は既存の `AC-1` / `AC-13` fallback を維持。
- **Post-merge checks** ([hve/github_api.py](hve/github_api.py), [hve/orchestrator.py](hve/orchestrator.py), [hve/tests/test_github_api.py](hve/tests/test_github_api.py), [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py)): `list_check_runs_for_ref()` を追加し、PR merge 後の merge commit check-runs を確認。失敗系 conclusion または check-run 0 件は post-merge 検証失敗として扱い、ローカル作業ブランチ削除と成功扱いを抑止。
- **GUI / Docs** ([hve/gui/page_options.py](hve/gui/page_options.py), [hve/gui/tests/test_page_options_github_cicd.py](hve/gui/tests/test_page_options_github_cicd.py), [users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md), [users-guide/hve-technical-architecture.md](users-guide/hve-technical-architecture.md)): `github.com で CI/CD を実行` トグル対象を ASDW-WEB / ADFDV に整合し、Cloud Agent Orchestrator では `DAGExecutor` 内の post-merge check-run 待機が実行されない既知制約を明記。
- **検証**: `test_artifact_validation_deploy_gate` / `test_adfdv_deploy_contract` / `test_orchestrator::TestCreatePrIfNeeded` / `test_orchestrator::TestDeleteLocalMergedBranch` / `test_github_api::TestListCheckRunsForRef` / `test_auto_approve_and_merge_workflow` / `test_page_options_github_cicd` / `test_gui_imports` の関連テストが PASS。

### Added — GUI/CLI: マージ済みローカル作業ブランチの自動削除（FR-CLI-34）

**概要**: GUI/CLI のローカル実行で作成した作業ブランチ（`copilot-sdk/*`）が、繰り返し実行するうちにローカルへ多数残存する問題に対し、`enable_auto_merge` による github.com 側の auto-approve-and-merge 完了（PR が merged）を検知して、今回作成した作業ブランチを**ローカルのみ**削除するオプション `--delete-local-merged-branch`（既定: 有効、`--no-delete-local-merged-branch` で無効化）を追加した。GitHub の「Automatically delete head branches」設定はリモートの head branch のみを対象とし、ローカルブランチには作用しないため、ローカル削除を本機能で補う。リモートブランチは削除せず github.com の設定に委ねる。削除は `enable_auto_merge` 有効・全 Step 成功・今回実行で PR 作成済みの場合に限り、PR の `merged` を最大 600 秒（15 秒間隔）ポーリングして検知後に行う（squash マージではローカルが「マージ済み」と判定されないため、base へ checkout 後 `git branch -D`）。未マージ（closed 等）・タイムアウト・`checkout` 失敗・中断時は削除しない。過去に作成済みのブランチは対象外（今回実行分のみ）。

- **要件 / テスト仕様** ([hve-dev/requirement-definition.md](hve-dev/requirement-definition.md), [hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md)): FR-CLI-34 と対応テスト計画を追加。
- **Config** ([hve/config.py](hve/config.py)): `delete_local_merged_branch: bool = True` を追加。
- **GitHub API** ([hve/github_api.py](hve/github_api.py)): PR の `merged` 状態を取得する `get_pull_request()` を追加。
- **Orchestrator** ([hve/orchestrator.py](hve/orchestrator.py)): `_git_delete_local_branch()` と、PR の `merged` をポーリングして削除する `_wait_pr_merged_and_delete_local_branch()` を追加し、後処理フェーズ（PR 作成・コードレビュー後）に `enable_auto_merge` かつ全 Step 成功時のみ呼び出す。
- **CLI** ([hve/__main__.py](hve/__main__.py)): `--delete-local-merged-branch` / `--no-delete-local-merged-branch`（`BooleanOptionalAction`, 既定 True）を追加し `cfg` へ反映。
- **GUI** ([hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py), [hve/gui/page_options.py](hve/gui/page_options.py), [hve/gui/settings_apply.py](hve/gui/settings_apply.py), [hve/gui/settings_store.py](hve/gui/settings_store.py)): 削除トグルを共通ファクトリ `_make_delete_branch_field` で生成し、設定画面（C5）と主画面 ASDW-WEB/ADFD の「github.com で CI/CD を実行」の下（C10）へ配置。C5/C10 を `enable_auto_merge` と同じ双方向同期で 1 内部設定 `delete_local_merged_branch` に集約し、`to_argv` は off 時のみ `--no-delete-local-merged-branch` を出力。settings の永続化（既定 True）に追加。
- **i18n** ([hve/gui/help_content.py](hve/gui/help_content.py), [hve/gui/i18n/hve_gui_en_US.ts](hve/gui/i18n/hve_gui_en_US.ts), [hve/gui/i18n/hve_gui_en_US.qm](hve/gui/i18n/hve_gui_en_US.qm)): ヘルプ文言を追加し、削除トグルの title/description の英訳を `.ts` に追加して `.qm` を再生成。
- **検証**: `test_config` 109 件 / `test_github_api` 47 件 / `test_orchestrator::TestDeleteLocalMergedBranch` 7 件 / `test_main` 214 件 / GUI 全体 930 件（1 skip）/ settings・section・page_options・orchestrate_args サブセット 26 件 / `test_i18n` 15 件が PASS。`pyside6-lrelease` は 359 translations を生成（XML 破損なし）。

### Added — GUI/CLI: 起動前認証 preflight と GUI 認証導線を追加

**概要**: `hve orchestrate` / `hve cli` の本処理開始前に GitHub Copilot SDK、Work IQ、Azure CLI の認証状態を条件付きで確認する preflight を追加した。未認証のまま Step 実行へ進んで後段の SDK / MCP / 外部 CLI エラーになる問題を避けるため、Copilot 認証は `--dry-run` を除き実行前に確認し、Work IQ は有効化時のみ EULA / Microsoft 365 認証を確認する。Azure CLI は `--resource-group` 指定または Azure MCP Server を含む `--mcp-config` 指定時のみ確認する。GUI には起動後に操作できる **「Copilot にログイン」** と **「Work IQ 認証確認」** の導線を追加し、GitHub REST 用の既存 **「GitHub CLI でログイン」** と役割を分離した。

- **Auth / CLI** ([hve/auth.py](hve/auth.py), [hve/__main__.py](hve/__main__.py)): `ensure_authenticated()` を追加し、`orchestrate` / 対話型 `cli` の `run_workflow()` 直前で Copilot 認証を確認するようにした。未ログインかつ対話可能な端末では `copilot login` 実行確認を表示し、非対話環境では `hve login` の事前実行を案内して停止する。`--dry-run` は認証確認をスキップする。
- **Work IQ** ([hve/__main__.py](hve/__main__.py), [hve/workiq.py](hve/workiq.py)): Work IQ 使用時に既存 `workiq_login()` を再利用して EULA / M365 認証を本処理前に確認するようにした。失敗時、対話可能な端末では Work IQ を無効化して続行するかを選べる。無効化時は `SDKConfig` と `params["sources"]` の `workiq` 指定を同時に取り除く。
- **Azure** ([hve/__main__.py](hve/__main__.py)): `--resource-group` 指定または Azure MCP Server を含む MCP 設定がある場合のみ `az account show` 相当を確認する。未ログイン時、対話可能な端末では `az login` 実行確認を表示し、`az` 未インストール時は不要な入力を求めず停止する。
- **MCP Config** ([hve/__main__.py](hve/__main__.py)): `--mcp-config` が SDK 直接 map 形式に加え、`.github/.mcp.json` などの `mcpServers` wrapper 形式も受け付けるようにした。wrapper 付き JSON は内側の map に変換して SDK へ渡す。
- **GUI** ([hve/gui/main_window.py](hve/gui/main_window.py), [hve/gui/page_options.py](hve/gui/page_options.py)): ステータスバーに **「Copilot にログイン」** ボタンを追加し、成功後に既存モデル一覧取得を自動実行するようにした。Work IQ 設定欄には **「Work IQ 認証確認」** ボタンを追加し、既存 `workiq_login()` を UI スレッド外で実行する。MCP Server セクションは実行時 ON/OFF ではなく登録済み一覧と認証手順表示に整理し、実行時 MCP 利用は `--mcp-config` に一本化した。
- **Docs** ([users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md), [users-guide/hve-gui-getting-started.md](users-guide/hve-gui-getting-started.md), [users-guide/hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md), [users-guide/plugin-mcp-auth.md](users-guide/plugin-mcp-auth.md), [users-guide/hve-technical-architecture.md](users-guide/hve-technical-architecture.md)): Copilot SDK / GitHub CLI / Work IQ / MCP Server / Azure CLI の認証導線と責務分離を現行実装に合わせて更新した。
- **Tests** ([hve/tests/test_auth.py](hve/tests/test_auth.py), [hve/tests/test_main.py](hve/tests/test_main.py), [hve/gui/tests/test_status_banner.py](hve/gui/tests/test_status_banner.py), [hve/gui/tests/test_workiq_auth_button.py](hve/gui/tests/test_workiq_auth_button.py), [hve/gui/tests/test_mcp_server_list_display.py](hve/gui/tests/test_mcp_server_list_display.py)): Copilot / Work IQ / Azure preflight、MCP config wrapper、GUI Copilot ログイン導線、Work IQ 認証確認ボタン、MCP 一覧表示を mock ベースで検証。

### Changed — GUI/CLI: `github_cicd_enabled` を `enable_auto_merge` へ統合（CI/CD トグルの一本化）

**概要**: `github_cicd_enabled`（CLI `--github-cicd`、Deploy Step の GitHub Actions 委譲）と `enable_auto_merge`（PR 自動 Approve & Auto-merge）は併用前提の別設定だったが、ASDW-WEB/ADFD の全自動 CI/CD で常にセット利用されるため、影響範囲の小さい `github_cicd_enabled` を廃止し `enable_auto_merge` へ一本化した。GUI は「画面はそのまま」要件に従い、メイン画面（C10）の「github.com で CI/CD を実行」トグルと設定画面（C5）の「PR 自動 Approve & Auto-merge」トグルを双方向同期し、内部設定を `enable_auto_merge` に集約する。これに伴い `github_cicd ON + auto_merge OFF`（Deploy 委譲のみ・リポジトリ操作は手動）の中間モードは廃止し、ON=全自動の単一スイッチとした。`enable_auto_merge` は AKM 等でも引き続き PR 自動マージ用に使用される（挙動不変）。

- **Config** ([hve/config.py](hve/config.py)): `github_cicd_enabled` フィールドを削除。`enable_auto_merge` のコメントを「Deploy 委譲＋auto-merge の統合スイッチ」へ更新。
- **Orchestrator** ([hve/orchestrator.py](hve/orchestrator.py)): ブランチ作成条件・`_on_wave_start` の Deploy 前 push・最終 push 時の `src` 除外解除の3箇所を `github_cicd_enabled and enable_auto_merge` → `enable_auto_merge` に統合。AKM は `enable_auto_merge=True ⟹ create_pr=True` かつ Deploy Step 非保持のため挙動不変。
- **CLI** ([hve/__main__.py](hve/__main__.py)): `--github-cicd` 引数定義と `cfg.github_cicd_enabled` 設定を削除（`--enable-auto-merge` は維持）。
- **GUI** ([hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py), [hve/gui/page_options.py](hve/gui/page_options.py), [hve/gui/main_window.py](hve/gui/main_window.py)): `OrchestrateArgs.github_cicd_enabled` と `to_argv` の `--github-cicd` を削除。`OptionsPage` で C10 トグルと C5 `enable_auto_merge` を双方向同期（`blockSignals` で無限ループ防止）し、`_C10AppId.to_args` の `github_cicd_enabled` 書き込みを削除。`enable_auto_merge` は `settings_apply` が `blockSignals` なしで `setChecked` するため復元時も同期が働く。
- **Tests** ([hve/tests/test_gui_imports.py](hve/tests/test_gui_imports.py), [hve/tests/test_main.py](hve/tests/test_main.py), [hve/gui/tests/test_page_options_github_cicd.py](hve/gui/tests/test_page_options_github_cicd.py)): `github_cicd_enabled` / `--github-cicd` 前提の旧テストを削除し、C10⟷C5 双方向同期と `build_args` への `enable_auto_merge` 反映を検証するテストへ更新。
- **検証**: `test_gui_imports` + `test_page_options_github_cicd` 33件 / settings round-trip 16件 / Deploy 境界 `wave_has_deploy_step` 42件 / `test_main` 189件が PASS（既存の無関係 failure 1件 `TestParserBasic::test_workflow_required` は本変更前から存在＝`git stash` で確認済み、スコープ外）。

### Changed — 生成ドキュメントの履歴セクション（再実行ログ等）を文書末尾へ統一

**概要**: HVE の GUI/CLI ワークフローが繰り返し生成・更新する `docs/` 配下の設計書・カタログで、差分マージの記録（「再実行ログ」「再実行履歴」「変更履歴」）が文書の冒頭に作成されることがあった。共有の既存成果物更新方針に位置ルールを追加し、これらの履歴セクションを**文書末尾**へ配置（既存文書で冒頭・中間にある場合は末尾へ移動・集約）するよう統一した。生成元のみを修正し `docs/` ファイルは直接編集していないため、各ドキュメントは次回の再生成時に是正対象となる。

- **Policy** ([.github/scripts/templates/_shared/existing-artifact-policy.md](.github/scripts/templates/_shared/existing-artifact-policy.md)): 差分マージ記録（再実行ログ / 再実行履歴 / 変更履歴）を箇条書き・表いずれの形式でも独立セクションとして文書末尾へ配置し、冒頭・中間（front-matter 内の箇条書きを含む）にある場合は末尾へ移動・集約するルールを追加。`作成日`・`根拠`・`主入力` 等の front-matter メタデータ行と、ファイル全体が変更ログである履歴専用ファイル（`*-ChangeLog.md`）は対象外とした。
- **影響範囲**: 本方針は [hve/template_engine.py](hve/template_engine.py) の `{existing_artifact_policy}` プレースホルダ経由で全対象ワークフロー（aas / aad-web / asdw-web / adfd / adfdv / aag / aagd / akm / adoc / aqod）の body テンプレートへ伝播する。冒頭に履歴があった `docs/catalog/service-catalog-matrix.md` / `test-strategy.md` / `domain-analytics.md` / `app-catalog.md` / `data-model.md`（いずれも aas 生成）が次回再生成時の是正対象となる。`docs/azure/*` の再実行ログ（既に末尾配置）および既存挙動に回帰はない。
- **検証** ([hve/tests/test_template_engine.py](hve/tests/test_template_engine.py)): `TestExistingArtifactPolicyTemplate` / `TestExistingArtifactPolicyIntegration` を含む 119 件が PASS。プレースホルダ整合性テストに回帰なし（既存の無関係 failure 1 件 `TestCollectParams::test_aad_collect_params_with_multiple_app_ids` は本変更前から存在しスコープ外）。

### Fixed — Agent 作業ディレクトリが work/ 直下に作られる問題（run-id 配下へ統一）

**概要**: 各 Agent プロンプト（`.github/prompts/*.prompt.md`）の WORK 定義 `work/run/<run-id>/<Agent>/Issue-<識別子>/` は `<run-id>` `<識別子>` がリテラルのプレースホルダのまま LLM に渡っており（`load_prompt` は置換しない）、LLM が run-scoped の実パスを知らされず `work/` 直下（利用者報告例: `work/issue-2748`）へ作業ディレクトリを作りうる構造だった。プロンプト前置時にプレースホルダを実値へ置換し、`work/run/<run-id>/` 配下への作成を保証するよう修正。

- **Feature / Test** ([hve/prompt_loader.py](hve/prompt_loader.py), [hve/tests/test_prompt_loader.py](hve/tests/test_prompt_loader.py)): WORK プレースホルダを実値置換する純粋関数 `substitute_work_placeholders(text, *, run_id, identifier)` を追加（`<run-id>` / `<識別子>` を置換、空値はスキップして誤った空文字置換を防止）。ユニットテスト 6 件（実 Agent プロンプトに対する統合検証を含む）を追加。
- **Fix** ([hve/runner.py](hve/runner.py)): `StepRunner` が `load_prompt()` で読み込んだ Agent プロンプト本文へ `substitute_work_placeholders` を適用。`run_id` は `resolve_work_root()` の `<run-id>` と一致させるため `resolve_run_id()` を使用し、`<識別子>` は実例 `Issue-0` に合わせ `"0"` で置換する。

### Fixed — PR #2908 残作業解消: quality-gates fail-closed 対応 (follow-up)

- **Workflow** ([.github/workflows/auto-approve-and-merge.yml](.github/workflows/auto-approve-and-merge.yml)): check-runs API 取得失敗時に `|| echo '{}'` で fail-open だった箇所を fail-closed に修正。API 失敗時は `checks_passed=false` を出力し、idempotent な PR コメントを投稿してから Approve/Merge ステップをスキップする。
- **Workflow** ([.github/workflows/auto-approve-and-merge.yml](.github/workflows/auto-approve-and-merge.yml)): `AC-1` 判定の正規表現を `AC-10` / `AC-11` 等への部分一致を防ぐよう修正 (`AC-?1[^0-9[:cntrl:]][^[:cntrl:]]*✅`)。
- **Workflow** ([.github/workflows/auto-approve-and-merge.yml](.github/workflows/auto-approve-and-merge.yml)): `AC-13` 判定の正規表現を `AC-130` 等への部分一致を防ぐよう修正 (`AC-?13[^0-9[:cntrl:]][^[:cntrl:]]*(✅|N/A|NA|該当なし)`)。
- **Workflow** ([.github/workflows/auto-app-dev-microservice-web-reusable.yml](.github/workflows/auto-app-dev-microservice-web-reusable.yml)): Root done gate で Root Issue / Sub Issues / Issue body の API 取得失敗時に `|| echo '{}'` / `|| echo '[]'` / `|| echo ''` で fail-open だった箇所を fail-closed に修正。取得失敗時は `gate_failed=true` を設定し `asdw-web:done` の付与を停止する。
- **Workflow** ([.github/workflows/app009-red-tests.yml](.github/workflows/app009-red-tests.yml)): `on.pull_request.types` から `synchronize`, `reopened`, `ready_for_review` と `paths` フィルタを削除し、`labeled` イベントのみに限定。不要な PR で RED Tests が走らないようにした。

### Fixed — auto-approve / auto-merge の検証ゲート強化（Issue #2864）

- **Workflow** ([.github/workflows/auto-approve-and-merge.yml](.github/workflows/auto-approve-and-merge.yml)): `validation-confirmed` だけで判定せず、PR head SHA の check-runs を評価する `check-check-runs` ステップを追加。`failure` / `cancelled` / `timed_out` / `action_required` / `startup_failure` を検出した場合は自動 Approve/Merge を停止し、理由コメントを投稿する。
- **Workflow** ([.github/workflows/auto-approve-and-merge.yml](.github/workflows/auto-approve-and-merge.yml)): Deploy 系 PR 向け `check-deploy-ac` ステップを追加。`AC-1 ✅` 必須、AI/LLM 文脈では `AC-13 ✅`（または `N/A`）必須、`NEEDS-VERIFICATION` / `⏳` / `FAIL` / `未実行` / `手動実行が必要` / `残作業` を検出した場合は auto-merge を停止する。
- **Workflow** ([.github/workflows/auto-app-dev-microservice-web-reusable.yml](.github/workflows/auto-app-dev-microservice-web-reusable.yml)): Root done 直前 gate を追加し、`asdw-web:blocked` 残存または deploy/e2e 未検証キーワード残存時は Root への `asdw-web:done` 付与を停止する。
- **Workflow / Tests** ([.github/workflows/bats-tests.yml](.github/workflows/bats-tests.yml), [tests/bats/infra-scripts-smoke.bats](tests/bats/infra-scripts-smoke.bats)): `tests/bats/` 不在による Bats 失敗を解消するため最小 smoke test を追加。
- **Dependencies / Workflow** ([pyproject.toml](pyproject.toml), [.github/workflows/test-hve-python.yml](.github/workflows/test-hve-python.yml)): `rich` を正式依存に追加し、HVE Python workflow を `pip install -e .` ベースへ変更して collection 時の `ModuleNotFoundError: rich` を解消。

### Changed — APP-009 の RED/GREEN CI 判定を分離

- **Workflow** ([.github/workflows/app009-green-tests.yml](.github/workflows/app009-green-tests.yml)): APP-009 向け GREEN workflow を追加（UI/ API の PASS 必須）。
- **Workflow** ([.github/workflows/app009-red-tests.yml](.github/workflows/app009-red-tests.yml)): RED 専用 workflow を追加（`tdd-red` ラベル or 手動実行時のみ、失敗期待判定）。
- **Package** ([package.json](package.json)): `test:APP-009:green` を追加して GREEN 実行コマンドを固定化。

### Reliability — main branch protection 適用手順の明文化

- **Config / Docs** ([.github/branch-protection-main.json](.github/branch-protection-main.json), [docs/azure/main-branch-protection.md](docs/azure/main-branch-protection.md)): required checks を含む `main` branch protection 設定テンプレートと手動適用手順を追加。`GITHUB_TOKEN` での protection API は 403 となるため、本 PR では未適用（手順化のみ）。

### Fixed — state-transition-on-pr-merge の親 Issue 解決フォールバックを強化（ASDW-WEB 再発防止）

- **Workflow** ([.github/workflows/state-transition-on-pr-merge.yml](.github/workflows/state-transition-on-pr-merge.yml)): `resolve` ステップに Method 5（PR timeline の `cross-referenced` 参照）を追加。Method 1〜4 が解決できない場合のみ実行し、候補が単一かつ管理対象12系列（`aas` / `aad-web` / `asdw-web` / `adfd` / `adfdv` / `aag` / `aagd` / `akm` / `adoc` / `aqod` / `aad` / `asdw`）のタイトルまたは系列ラベルを持つ Issue のみ採用する安全ガードを追加。

### Changed — ASDW-WEB Step Issue 本文へ PR 紐付け必須ガイダンスを共通注入

- **Workflow** ([.github/workflows/auto-app-dev-microservice-web-reusable.yml](.github/workflows/auto-app-dev-microservice-web-reusable.yml)): `create_issue()` 共通処理に `<!-- asdw-web-pr-closing-guidance -->` マーカー付き文面を追加し、各 Step Issue 本文へ「`Closes #<本Issue番号>` を PR 本文に記載する」ガイダンスを 1 回だけ注入するようにした。

### Fixed — PR マージ後に [ASDW-WEB] 系列 Issue が未クローズで残る問題をワークフロー側で恒久対策

**概要**: Copilot PR に `Closes #N` / `<!-- parent-issue: #N -->` が補完されなかった場合、`[ASDW-WEB]` を含む系列 Issue がマージ後も open のまま残る構造的欠陥を修正した。`state-transition-on-pr-merge.yml` に多段 Issue 特定と冪等クローズを追加し、`link-copilot-pr-to-issue.yml` の冪等条件を「done マーカー有無」から「PR body に closing keyword が実在するか」を加味する判定へ是正した。

- **Workflow** ([.github/workflows/state-transition-on-pr-merge.yml](.github/workflows/state-transition-on-pr-merge.yml)): Issue 解決を `closingIssuesReferences` → PR body の `Closes/Fixes/Resolves #N` → PR title の `#N`（Issue 実在検証付き）→ `parent-issue` マーカーの順に多段化し、`<prefix>:done` 判定後のみ `<!-- auto-close-done -->` コメント冪等化付きで `gh issue close --reason completed` を実行する処理を追加。結果コメントにもクローズ実行状況（実行/既クローズ/スキップ）を追記。
- **Workflow** ([.github/workflows/link-copilot-pr-to-issue.yml](.github/workflows/link-copilot-pr-to-issue.yml)): guard ステップを修正し、done マーカーが存在しても PR body に closing keyword が無ければ `done=false` で再試行、closing keyword が存在すれば `done=true` でスキップするように変更（トリガー種別は据え置き）。
- **Tests** ([.github/scripts/tests/test-bash.sh](.github/scripts/tests/test-bash.sh)): `link-copilot-pr-to-issue` guard 判定の回帰テスト（「done マーカーあり+Closes なし→再試行」「Closes あり→スキップ」）を追加。

### Fixed — auto-draft-to-ready の HEAD=Initial plan ガード追加によるセッション追い越し（`The session was cancelled by the user.`）の恒久対策

**概要**: `auto-draft-to-ready.yml` の `activity-check` ステップが HEAD コミット subject の `Initial plan` チェックを持たないため、Copilot Agent のローカル作業中（GitHub 上に痕跡が残らない沈黙期間）に draft→ready 化が走り、続く `auto-approve-and-merge.yml` が成果物コミット push 前にマージしてセッションを強制終了させるレースコンディションが存在した（PR #2824 / task 64e1b9d5 / Issue #2802 で再現確認）。HEAD commit subject が `Initial plan` の間は ready 化を見送るガードを追加し、多層防御とリグレッションテストを整備した。

- **Workflow** ([.github/workflows/auto-draft-to-ready.yml](.github/workflows/auto-draft-to-ready.yml)): `activity-check` ステップで既存の `gh api /commits/{sha}` 呼び出しを活用して `.commit.message` 先頭行を取得し、`Initial plan` の場合に `proceed=false`（Agent 作業未完）として ready 化を見送るガードを追加。
- **Tests** ([.github/scripts/tests/test-bash.sh](.github/scripts/tests/test-bash.sh)): セクション `14. auto-draft-to-ready.yml — Initial plan ガード判定の回帰テスト` を追加。`Initial plan` → 見送り・非 `Initial plan` かつ窓外コミット → 続行の2ケースを検証。
- **Tests** ([.github/scripts/python/tests/test_auto_approve_and_merge_workflow.py](.github/scripts/python/tests/test_auto_approve_and_merge_workflow.py)): `auto-approve-and-merge.yml` の `Initial plan` スキップガード（`skip_reason=initial_plan`、Approve/Merge/コメント各ステップの `if` ガード）が保持されていることを静的検証するテストクラスを追加。
- **Knowledge** ([knowledge/copilot-session-cancelled-event.md](knowledge/copilot-session-cancelled-event.md)): PR #2824 事例のタイムライン・根本原因・恒久対策（対策A）を事実ベースで追記。

### Fixed — auto-draft-to-ready の完了判定にコミット活動を加味し、作業中 Copilot PR の早期 Ready 化を抑止

**概要**: `activity-check` ステップがコメントのみを見ておりコミット活動を見ていなかったため、コミット間隔がデバウンス窓（180秒）に収まる静寂期間に早期 Ready 化され、後続 `auto-approve-and-merge.yml` による早期自動マージを招いていた。HEAD コミットの `committer.date` がデバウンスのカットオフ以降ならコメントの有無に関わらず Ready 化を見送るよう修正した。

- **Workflow** ([.github/workflows/auto-draft-to-ready.yml](.github/workflows/auto-draft-to-ready.yml)): `activity-check` ステップに `GET /repos/{REPO}/commits/{HEAD_SHA}` の `committer.date` とカットオフ epoch の比較を追加。コメントまたはコミットがデバウンス窓内にある場合に `proceed=false`（見送り）とする。取得・パース失敗時は安全側で `proceed=false`。
- **Tests** ([.github/scripts/tests/test-bash.sh](.github/scripts/tests/test-bash.sh)): セクション `13. auto-draft-to-ready.yml — コミット活動デバウンス判定の回帰テスト` を追加。窓内コミット（見送り）・窓外コミット（続行）・パース失敗（安全側・見送り）の3ケースを検証。

**検証**:

- `shellcheck -S warning .github/scripts/tests/test-bash.sh` → PASS。
- `bash .github/scripts/tests/test-bash.sh` → 32 passed, 0 failed。
- `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/auto-draft-to-ready.yml'))"` → YAML OK。
- `git diff --stat` → 3 ファイルのみ変更（`.github/workflows/auto-draft-to-ready.yml` / `.github/scripts/tests/test-bash.sh` / `CHANGELOG.md`）。

<!-- validation-confirmed -->

### Fixed — Copilot 作成 PR の親 Issue 解決失敗による ASDW-WEB 等の状態遷移停止を補完ロジック強化で抑止

**概要**: Copilot 作成 PR の本文に `Closes #N` / `<!-- parent-issue: #N -->` が無いまま Draft で作成されると、`link-copilot-pr-to-issue.yml` の `opened` 単発実行時に `find_issue_number()` の全 Method が空振りし、`asdw-web:done` 付与と次ステップ遷移が停止していた。対策として、Issue 特定失敗コメントだけが残っている場合の `ready_for_review` 再試行を追加し、`sync-issue-labels` コメントの投稿者制限を外して、タイトル一致失敗時には Copilot アサイン Open Issue がちょうど 1 件のケースだけを最小フォールバックで採用するようにした。

- **Workflow** ([.github/workflows/link-copilot-pr-to-issue.yml](.github/workflows/link-copilot-pr-to-issue.yml), [.github/workflows/test-cli-scripts.yml](.github/workflows/test-cli-scripts.yml)): `link-copilot-pr-to-issue.yml` を `opened, ready_for_review` で再試行可能にし、失敗警告コメントだけでは冪等スキップしないよう調整した。`test-cli-scripts.yml` には `.github/scripts/pr-common.sh` の変更監視と shellcheck 対象を追加した。
- **Script** ([.github/scripts/pr-common.sh](.github/scripts/pr-common.sh)): Method 2.6 の `sync-issue-labels` コメント復元から Bot/login 制限を削除し、本文マーカーだけで `Issue #N` を復元できるようにした。Method 3 では既存のタイトル一致が不成立の後、`copilot-swe-agent` → `Copilot` の順で Open Issue がちょうど 1 件のときのみ採用する最小フォールバックを追加した。
- **Tests** ([.github/scripts/tests/test-bash.sh](.github/scripts/tests/test-bash.sh)): `parent-issue` 抽出、非 Bot の `sync-issue-labels` コメントからの Issue 復元、旧フィルタ退行検知、ノイズ耐性を検証する Bash 回帰テストを追加した。

**検証**:

- `shellcheck -S warning .github/scripts/pr-common.sh` → PASS。
- `bash .github/scripts/tests/test-bash.sh` → PASS。

<!-- validation-confirmed -->

### Changed — GUI: ASDW-WEB / ADFD の github.com CI/CD を Issue Template 起動フローへ変更

**概要**: GUI の `github.com で CI/CD を実行（ASDW-WEB / ADFD）` を有効にした場合の起動フローを、GitHub API による Issue 直接作成ではなく、github.com の Issue Template 画面をブラウザーで開く Cloud 版フローへ変更した。ローカルブランチに未コミット変更がある場合は commit / push するかを確認し、Yes の場合のみ自動 commit / push 後に Issue Template を開く。No の場合は何もせず終了する。対象 Dataflow workflow は既定プランに従い `ADFDV` ではなく `ADFD` とした。

- **GUI** ([hve/gui/github_cicd.py](hve/gui/github_cicd.py), [hve/gui/page_options.py](hve/gui/page_options.py)): github.com CI/CD 対象を `ASDW-WEB / ADFD` に更新し、`asdw-web` は `web-app-dev.yml`、`adfd` は `dataflow-design.yml` の Issue Template URL を開くようにした。トグル説明文も未コミット確認・Issue Template 上での選択前提へ更新。
- **GUI** ([hve/gui/main_window.py](hve/gui/main_window.py)): CI/CD 起動時に Git working tree を確認し、未コミット変更がある場合は yes/no 確認を表示。yes の場合は commit message を自動生成して commit / push し、成功後に Issue Template を開く。変更なしの場合は確認なしで Issue Template を開く。前段同時選択時は `AAD-WEB → ASDW-WEB`、`AAS → ADFD` の前段のみローカル実行する。
- **i18n / コメント** ([hve/gui/i18n/hve_gui_en_US.ts](hve/gui/i18n/hve_gui_en_US.ts), [hve/gui/i18n/hve_gui_en_US.qm](hve/gui/i18n/hve_gui_en_US.qm), [hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py)): 英語翻訳と内部コメントを Issue Template 起動フローへ同期。
- **Tests** ([hve/gui/tests/test_github_cicd.py](hve/gui/tests/test_github_cicd.py), [hve/gui/tests/test_github_cicd_git.py](hve/gui/tests/test_github_cicd_git.py), [hve/gui/tests/test_github_cicd_gui.py](hve/gui/tests/test_github_cicd_gui.py), [hve/gui/tests/test_i18n.py](hve/gui/tests/test_i18n.py)): `ADFD` 対象化、Issue Template URL 起動、未コミット変更なし/Yes/No選択、commit message、前段分岐、i18n を検証。

**検証**:

- `.\.venv\Scripts\python.exe -m pytest hve/gui/tests/test_github_cicd.py hve/gui/tests/test_github_cicd_git.py hve/gui/tests/test_github_cicd_gui.py hve/gui/tests/test_i18n.py -q` → **74 passed**。
- `.\.venv\Scripts\python.exe -m py_compile hve/gui/github_cicd.py hve/gui/main_window.py hve/gui/page_options.py hve/gui/orchestrate_args.py hve/gui/tests/test_github_cicd.py hve/gui/tests/test_github_cicd_gui.py` → OK。
- `.\.venv\Scripts\pyside6-lrelease.exe hve/gui/i18n/hve_gui_en_US.ts -qm hve/gui/i18n/hve_gui_en_US.qm` → **Generated 355 translation(s)**。

<!-- validation-confirmed -->

### Added — markdown-query / code-query への意味検索（密ベクトル）導入を実測評価し、いずれも見送りと判定した

Coding Agent が発行するクエリが「文ではなく単語の羅列」であるために意味検索の利点を活かせていないのではないか、という仮説を実測で検証した。結論として **mdq・cq のいずれも密ベクトル検索の導入を見送る**。**本エントリ自体で出荷コードは 1 行も変更していない**（追加したのは評価成果物と本エントリのみ。副次的に検出した既存欠陥の修正は直後の Fixed エントリに分離した）。なお `git status` には `mdq/cli.py` / `mdq/tokenize.py` / `cq/search.py` / `cq/repomap.py` の変更も出るが、**これらは本作業と並行する別セッションによるもので、本エントリおよび Fixed エントリの成果物ではない**。

**前提の実測**: Agent は実際に 100% キーワード羅列でクエリを投げていた（ローカル利用ログ `.mdq/usage.jsonl` の search 55 件〈調査時点〉+ GitHub Copilot Coding Agent の Cloud セッション 53 件 / distinct 27 種、自然文 0 件）。同時に、mdq は既存の `--strategy semantic_paragraph --late-chunking` + `--fusion-alpha` で密ベクトル経路が**実装済み・未有効化**であり、cq には**存在しない**ことを確認した。

**mdq の判定（NO-GO）**: `paraphrase-multilingual-MiniLM-L12-v2`（240.5 MiB、dim 384）で `semantic_paragraph` 索引を構築し（16,607 chunks / 4,128 embeddings / 467 秒）、`heading`+BM25 / `semantic`+BM25 / `semantic`+融合（α=1.0/0.7/0.5/0.3/0.0）の **3 アームを同一プロセス・同一索引スナップショットで**計測した（golden dev 40 + holdout 20 × filtered/broad、正解判定は `mdq.golden_eval` 単一実装、1,199 秒）。

| top-5 正解率 | dev/filtered | dev/broad | holdout/filtered | holdout/broad |
|---|---:|---:|---:|---:|
| `heading`+BM25（現行） | **87.5%** | **65.0%** | **100.0%** | **95.0%** |
| 融合 α=0.7（融合系で最良） | 82.5% | 60.0% | 95.0% | 90.0% |
| cosine のみ α=0.0 | 37.5% | 12.5% | 65.0% | 30.0% |

融合を伴う α（0.7 / 0.5 / 0.3 / 0.0）は top-5・MRR とも **4 条件すべてで現行を上回らなかった**。劣化の主因は融合ではなく `semantic_paragraph` チャンカ側にある（融合なしの `semantic`+BM25 が **top-5 では 4 条件すべてで負**（-3 / -4 / -1 / -1）、**MRR では 4 条件中 3 条件で負**）。α=1.0 が `semantic`+BM25 と全指標で完全一致することを恒等条件として確認しており、融合経路の配線は正しい。

**cq の判定（NO-GO）**: 既存 chunk（hve 14,171 / app 520）へ `name + signature + text 先頭 512 字` の埋め込みを付けて総当たり cosine で PoC した。判定基準に該当する**日本語 `natural` intent の golden クエリ 2 件は、2 件とも密ベクトルでも圏外**（hve `検索クエリから chunking strategy を選ぶルーティング判断` / app `同意ゲートの判定を行う実装`）。同じ着地点でも**英語クエリなら rank 2 で到達する**ため、失敗しているのは「日本語クエリ → 英語コード」の橋渡しであり、これは [.github/skills/code-query/SKILL.md](.github/skills/code-query/SKILL.md) が Non-goal として明記している内容そのものだった。**多言語埋め込みを足してもこの Non-goal は解消しない**ことを実測で確認した。日本語疑問形で包んだ 19 件は 11 件が到達したが、うち 9 件は「シンボル名を日本語で包んだだけ」の人工的なクエリ形で、包まなければ既存の `symbol` ルートが top-1 94.7% で解決する。コストは hve profile で **索引時間 +401.8 秒**・ベクトル 20.8 MiB・`SCHEMA_VERSION` bump による全再構築。

**Skill への記載方針**: 「この検索ツールは意味検索なので自然文で投げてほしい」という趣旨の記述は **追加しない**。実装は純 BM25 であり事実に反すること、および文形式にすると精度が落ちること（mdq の dev/broad で top-5 62.5% → 27.5%、cq で日本語疑問形が 19/19 で 0 ヒット）を実測したため。原因は、日本語の機能語が CJK バイグラム 18 語に展開され、技術文書コーパスでは希少＝高 IDF となって順位を乗っ取ることにある（`教え` は 15,759 chunks 中 2 件 = 0.0%）。なお 62.5% → 27.5% は上表の A3 計測とは**別の計測**（クエリ様式 A/B、`heading` 索引 15,759 chunks 時点のスナップショット）であり、索引が更新されているため上表のアーム A（65.0%）とは一致しない。

**副次的に検出した既存欠陥（4 件とも直後の Fixed エントリで修正済み）**:

| 欠陥 | 実測根拠 |
|---|---|
| `mdq/query_router.py::discover_available_strategies` の認識リストに `semantic_paragraph` / `pageindex` が欠落 | `ALL_STRATEGIES` は 6 種だが `known` は 3 種。DB が存在しても戻り値は `["heading"]` で、`--strategy auto` は該当戦略へ永久に到達できない |
| `--fusion-alpha` が索引構築時と異なる埋め込みモデルでクラッシュ | `ValueError: shapes (1024,) and (384,) not aligned`（`mdq/search.py` の `try` の外で発生し fail-soft しない）。索引にモデル名・次元が記録されていない |
| `semantic_paragraph` が反転行範囲チャンクを生成 | 75 / 4,128 md チャンク（1.82%）が `start_line > end_line`。`heading` は 0 件 |
| `mdq/embeddings.py::get_provider` にキャッシュが無い | 本計測で 565 回呼び出し。毎回 `TextEmbedding` を新規構築する |

**検証**: 全数値は再現可能なスクリプトによる実測（`probe-model.py` / `verify-index.py` / `measure-fusion.py` / `confound-check.py` / `cq-semantic-poc.py` / `C0-review-app-profile.py`）で、生結果を同ディレクトリの `.json` / `.log` に保存した。各タスク完了後に敵対的レビュー（6 軸）を実施し、A1〜A4 / C0 の 5 件すべてで指摘を反映して PASS とした（`*-adversarial-review.md`）。反転行範囲チャンクが golden 評価を歪めていないことは別途実測で確認済み（60 件中 0 件が影響）。`.mdq/` `.cq/` は [.gitignore](.gitignore) L38 / L43 で除外されておりリポジトリに影響しない。

**既知の制約**: (1) 計測はローカル Windows のみで、Cloud Agent（Linux runner）では未実測。(2) 1 クエリ = dev 2.5pt / holdout 5.0pt であり、Δtop-5 が ±1〜2 件の差は測定分解能の範囲内。判定は「上回るか」という基準で行っており分解能とは独立に成立する。(3) 埋め込みモデルは `paraphrase-multilingual-MiniLM-L12-v2` 1 種のみで評価した。`intfloat/multilingual-e5-large`（2.24 GB）は Cloud Agent が毎セッション索引を再構築する制約から候補外とした。(4) 検出した既存欠陥 4 件は本エントリでは扱わず、直後の Fixed エントリで別途 RED → 実装 → GREEN の順序で修正した。

<!-- validation-confirmed -->

### Fixed — markdown-query の既存欠陥 4 件（戦略検出漏れ・融合クラッシュ・反転行範囲・provider 再構築）

上の意味検索評価で副次的に検出した既存欠陥 4 件を修正した。いずれも「実装が自身の docstring / 不変条件に違反している」bugfix であり、統制する FR が存在しないため [.github/skills/hve-requirement-traceability/SKILL.md](.github/skills/hve-requirement-traceability/SKILL.md) の bugfix 規定に従い**新規要件 ID を起こさず** RED → 実装 → GREEN の順序で実施した。4 件それぞれに敵対的レビュー（6 軸）を実施し、指摘を反映のうえ PASS としている。

- **`--strategy auto` が `semantic_paragraph` / `pageindex` へ到達できない問題を修正** ([mdq/query_router.py](mdq/query_router.py)): `discover_available_strategies` が戦略名をハードコードした 3 要素タプルで判定しており、`ALL_STRATEGIES` の 6 種に追随していなかった。`ALL_STRATEGIES` から導出（索引を持たない `graphrag` を除外、長さ降順で最長サフィックス優先）するよう変更。これにより `narrative_query` → `semantic_paragraph`、`concept_overview` → `pageindex` のルールが初めて到達可能になる。
- **`--fusion-alpha` の次元不一致クラッシュを fail-soft 化** ([mdq/search.py](mdq/search.py)): 索引に埋め込みモデル名・次元が記録されていないため、索引構築時と検索時で `MDQ_EMBED_MODEL` が異なると `np.dot` が `ValueError: shapes (1024,) and (384,) not aligned` を送出していた。この例外は provider 不在を捕捉する `try` の外で起きるため縮退しなかった。次元不一致を検出して stderr に理由付き警告を出し BM25 スコアへ縮退するようにした（provider 不在時と同じ fail-soft 方針）。
- **`semantic_paragraph` の反転行範囲チャンクを修正** ([mdq/strategies_semantic.py](mdq/strategies_semantic.py)): 1 物理行に複数の文が載っている場合に行カーソルが親チャンクの `end_line` を追い越し、`start_line > end_line` のチャンクが生成されていた（実測 75 / 4,128 md チャンク = 1.82%）。`sub_start` も親の `end_line` でクランプし、全 consumer が前提としている `start <= end` を不変条件として保証した。
- **`mdq/embeddings.py::get_provider` に provider キャッシュを追加** ([mdq/embeddings.py](mdq/embeddings.py)): semantic チャンカがファイルごとに provider を要求するため、ONNX セッション構築が索引構築 1 回につき N 回発生していた（実測 565 回）。`(provider, model)` 単位でキャッシュし、テスト・設定変更用に `clear_provider_cache()` を公開した。構築失敗は例外が代入前に送出されるためキャッシュされない。

**検証**:

| 修正 | RED | GREEN |
|---|---|---|
| `discover_available_strategies` | 5 failed / 18 passed | 23 passed |
| 融合の次元不一致 | 1 failed / 6 passed | 7 passed |
| 反転行範囲 | 9 failed / 9 passed | 18 passed |
| provider キャッシュ | 5 failed / 9 passed / 1 skipped | `mdq/tests` 273 passed / 3 skipped |

- `.\.venv\Scripts\python.exe -m pytest mdq/tests hve/tests/test_mdq_vendor_sync.py -q` → **313 passed / 3 skipped**（`pwsh -NoLogo -NoProfile -File tools/skills/markdown_query/sync-vendor.ps1` による vendor 同期後）。
- 反転行範囲は実データでも確認: `hve-dev/requirement-definition.md` の反転チャンク **33 → 0**、意図的に文を詰めた検証用文書で **30 → 0**。
- provider キャッシュは索引全体の再構築で end-to-end 計測: **467.0 秒 → 385.5 秒**（-17.5%、162 ファイル / 16,611 チャンク）。
- HVE inventory を正規再生成し、`hve-test-inventory.csv` **9,589 rows / 488 files**、`hve-feature-inventory.csv` **301 rows**、`hve-surface-inventory.csv` **2,879 rows**。stale gate **1 passed**。E1〜E5 の敵対的レビューは全件指摘反映後 PASS。

**既知の制約**: (1) 反転行範囲の修正により、1 物理行に複数文が載る文書では複数チャンクが同一行範囲を共有する（実測: `hve-dev/requirement-definition.md` で 183 チャンク中 34 件が共有、最悪 `(239,239)` に 11 件）。行範囲は表示用のヒントであり検索一致には使われないため機能影響はないが、当該文書に限り引用範囲の粒度が粗くなる。通常の散文では 0 件。(2) provider キャッシュの 467.0 秒 / 385.5 秒は約 2 時間離れた別実行の比較であり、他プロセス負荷とチャンク数の差（16,607 / 16,611）を含む統制されていない比較である。改善方向は確実だが -17.5% という数値そのものには計測条件差が含まれる。(3) 索引に埋め込みモデル名を記録する設計変更は行っていないため、モデル不一致は検索時にしか検出できない。

<!-- validation-confirmed -->

## [0.2.0] - 2026-06-17

### Changed — GUI: ASDW-WEB / ADFDV の github.com CI/CD を Issue 直接作成で全自動化

**概要**: GUI Step 1 右ペインで ASDW-WEB / ADFDV を選択した際、当該ワークフロー枠に **PR 自動 Approve & Auto-merge** 設定も表示するようにした。さらに `github.com で CI/CD を実行（ASDW-WEB / ADFDV）` を有効にして実行した場合、従来の Issue Form ブラウザ起動と手動チェック / Submit 操作を廃止し、GUI が GitHub API で Cloud CI/CD Root Issue を直接作成するように変更した。作成する Issue body には既存 Cloud reusable workflow が読む `### PR完全自動化設定` を `- [x]` で埋め込み、Issue 作成後は Copilot Coding Agent 実行 → PR 作成 → 自動 Approve & Auto-merge まで自動発火する。前段ワークフロー同時選択時の安全ガード（前段のみローカル実行、commit / push 確認後に CI/CD 起動）は維持した。

- **GUI** ([hve/gui/page_options.py](hve/gui/page_options.py)): `ASDW-WEB` / `ADFDV` の右ペイン表示項目に、既存 C5 GitHub 設定の `PR 自動 Approve & Auto-merge` を追加。既存 `_LabeledField` 移設機構を再利用し、C5 全体は Step 1 右ペインで非表示のまま、対象フィールドだけをワークフロー枠へ表示する。
- **GUI** ([hve/gui/github_cicd.py](hve/gui/github_cicd.py)): Issue Form 互換の Markdown body 生成、CI/CD 起動ラベル / タイトル生成、GitHub API による Root Issue 直接作成 helper を追加。`enable_auto_merge=True` では `### PR完全自動化設定` を `- [x]` で生成する。
- **GUI** ([hve/gui/main_window.py](hve/gui/main_window.py)): CI/CD トグル ON 時の起動先を Issue Form ダイアログから Issue 直接作成へ変更。成功時は作成済み Issue URL を開き、失敗時は警告表示して auto-merge UI 状態を元に戻す。前段成果物 commit / push 後の遷移も同 helper へ接続。
- **Removed** ([hve/gui/github_cicd_dialog.py](hve/gui/github_cicd_dialog.py)): 手動 Issue Form 起動用ダイアログを削除。
- **GUI help / i18n / コメント** ([hve/gui/help_content.py](hve/gui/help_content.py), [hve/gui/i18n/hve_gui_en_US.ts](hve/gui/i18n/hve_gui_en_US.ts), [hve/gui/i18n/hve_gui_en_US.qm](hve/gui/i18n/hve_gui_en_US.qm), [hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py)): CI/CD 説明文を Issue 直接作成・全自動化の挙動に更新。英語翻訳の source / `.qm` も同期。
- **Tests** ([hve/gui/tests/test_github_cicd.py](hve/gui/tests/test_github_cicd.py), [hve/gui/tests/test_github_cicd_gui.py](hve/gui/tests/test_github_cicd_gui.py)): body 生成、複数 APP-ID、auto-merge `[x]`、Issue 作成 payload、右ペイン表示、複数 CI/CD ワークフロー選択時の重複表示防止、Issue 作成失敗時ロールバック、前段 commit / push 成功後の Issue 作成を検証。

**検証**:

- `.\.venv\Scripts\python.exe -m pytest hve/gui/tests/test_github_cicd.py -q` → **30 passed**。
- `.\.venv\Scripts\python.exe -m pytest hve/gui/tests/test_github_cicd_gui.py::TestOptionsPageVisibility -q` → **4 passed**。
- `.\.venv\Scripts\python.exe -m pytest hve/gui/tests/test_github_cicd_gui.py::TestMaybeLaunchGithubCicd::test_on_with_target_creates_issue hve/gui/tests/test_github_cicd_gui.py::TestMaybeLaunchGithubCicd::test_mixed_selection_picks_target_workflow hve/gui/tests/test_github_cicd_gui.py::TestMaybeLaunchGithubCicd::test_issue_create_failure_rolls_back_auto_merge hve/gui/tests/test_github_cicd_gui.py::TestRunClickedGithubCicdPrerequisiteFlow::test_target_without_prerequisite_continue_creates_issue hve/gui/tests/test_github_cicd_gui.py::TestRunClickedGithubCicdPrerequisiteFlow::test_commit_push_success_creates_issue_with_branch_and_repo -q` → **5 passed**。
- `.\.venv\Scripts\pyside6-lrelease.exe hve/gui/i18n/hve_gui_en_US.ts -qm hve/gui/i18n/hve_gui_en_US.qm` → **Generated 355 translation(s)**。

<!-- validation-confirmed -->

### Added — GUI: GitHub ログイン情報からリポジトリ / Issue 設定を取得・検証

**概要**: GUI 設定画面 C5「GitHub」の **リポジトリ / Issue 設定** に **リポジトリ取得** ボタンと状態表示を追加した。GitHub CLI ログイン後に注入済みの `GH_TOKEN` を使い、`REPO` 環境変数・ローカル `git remote origin`・GitHub REST API から `owner/repo` を補完または検証する。取得した repository metadata から Issues 有効状態・権限・default branch を画面へ反映する。既存入力済みの repo は上書きせず検証のみ行い、Issue タイトル（上書き）は GitHub API から決定できる情報ではないため自動補完しない。さらに **GitHub Copilot SDK 連携** の `Cloud repository owner` / `Cloud repository name` 入力欄を画面から削除し、`リポジトリ (owner/repo)` を source of truth として内部 owner/name を派生保持するようにした（`Cloud repository branch` は引き続き画面で指定可能）。

- **API** ([hve/github_api.py](hve/github_api.py)): `get_repository_metadata` / `list_viewer_repositories` を追加。既存 `api_call()` の REST 経路を再利用し、GraphQL や `gh` subprocess 経路は追加しない。
- **GUI** ([hve/gui/page_options.py](hve/gui/page_options.py)): GitHub remote URL parser と `git remote get-url origin` からの `owner/repo` 推定 helper を追加。`リポジトリ取得` ボタンで metadata を非同期取得し、repo 欄・ベースブランチ欄・状態ラベルへ反映。GitHub CLI ログイン成功後も repo metadata 取得を自動開始する。`Cloud repository owner` / `Cloud repository name` は UI から削除し、`repo` 欄から private な Cloud Session owner/name を同期して `OrchestrateArgs` へ反映する。
- **GUI settings** ([hve/gui/settings_apply.py](hve/gui/settings_apply.py), [hve/gui/settings_store.py](hve/gui/settings_store.py)): 画面削除済みの Cloud repository owner/name を GUI settings の apply / default 対象から除外。CLI/env/config 側の Cloud Session owner/name サポートは維持。
- **Tests** ([hve/tests/test_github_api.py](hve/tests/test_github_api.py), [hve/gui/tests/test_github_repo_autofill.py](hve/gui/tests/test_github_repo_autofill.py), [hve/gui/tests/test_gh_login_button.py](hve/gui/tests/test_gh_login_button.py), [hve/gui/tests/test_github_section_consolidation.py](hve/gui/tests/test_github_section_consolidation.py), [hve/gui/tests/test_github_section_grouping.py](hve/gui/tests/test_github_section_grouping.py)): REST helper、GitHub remote URL parser、repo metadata UI 反映、ログイン成功後の自動取得起動、Cloud owner/name UI 削除、repo 由来の Cloud owner/name 内部反映を mock ベースで検証。

**検証**:

- API: `.\.venv\Scripts\python.exe -m pytest hve/tests/test_github_api.py -q` → **43 passed**。
- Repo autofill / UI 削除関連: `.\.venv\Scripts\python.exe -m pytest hve/gui/tests/test_github_section_consolidation.py hve/gui/tests/test_github_section_grouping.py hve/gui/tests/test_github_repo_autofill.py -q` → **36 passed**。
- 直接関連 GUI: `.\.venv\Scripts\python.exe -m pytest hve/gui/tests/test_gh_login_button.py hve/gui/tests/test_github_branch_fetch.py hve/gui/tests/test_github_section_consolidation.py hve/gui/tests/test_github_section_grouping.py hve/gui/tests/test_github_repo_autofill.py -q` → **45 passed**。
- 構文: `.\.venv\Scripts\python.exe -m py_compile hve/gui/page_options.py hve/gui/settings_apply.py hve/gui/settings_store.py hve/gui/tests/test_github_section_consolidation.py hve/gui/tests/test_github_section_grouping.py hve/gui/tests/test_github_repo_autofill.py` → OK。

<!-- validation-confirmed -->

### Fixed — GUI: GitHub CLI ログイン時に Windows で設定画面が応答なしになる問題を修正

**概要**: GUI 設定画面 C5「GitHub」の **GitHub CLI でログイン** ダイアログで、Windows 環境の `pywinpty` 読み取りが GUI スレッドをブロックし、`gh auth login` の対話プロンプト待ち中に画面が「応答なし」になる問題を修正した。PTY 出力の `read_nowait()` ポーリングを `TerminalSessionController` 内の worker thread へ移し、端末出力の描画だけを GUI スレッドへ戻すことで、既存の埋め込み xterm.js 表示・入力転送・`GH_TOKEN` セッション注入フローを維持したまま UI 停止を避ける。

- **GUI** ([hve/gui/widgets/terminal_session.py](hve/gui/widgets/terminal_session.py)): `TerminalSessionController` に内部 worker thread を導入し、`PtySession.read_nowait()` / `write()` / `resize()` / `close()` を worker 側で処理。`view.feed_output()` と `finished(exit_code)` 通知は Qt signal 経由で GUI スレッドへ戻す構成に変更。
- **GUI** ([hve/gui/widgets/terminal_session.py](hve/gui/widgets/terminal_session.py)): 対話プロンプト待ちで worker thread の blocking read が継続している間、同じ worker event loop に queued 接続していた `write()` / `resize()` / `stop()` が処理されず、端末入力が `gh` に届かない starvation を修正。入力・リサイズ・停止要求は GUI 側から直接 `PtySession` へ渡し、blocking read と同一 event loop で競合しないようにした。
- **GUI** ([hve/gui/gh_login_dialog.py](hve/gui/gh_login_dialog.py)): `GhLoginDialog` の `accept()` / `reject()` 終了経路で `closeEvent()` が呼ばれず worker thread が残る lifecycle 問題を修正。停止処理を `_stop_terminal()` に集約し、`done()` と `closeEvent()` の両方から idempotent に呼ぶことで、ログインダイアログ終了時の `QThread: Destroyed while thread '' is still running` を防止。
- **Docs/コメント** ([hve/gui/pty_backend.py](hve/gui/pty_backend.py)): Windows の `pywinpty` 読み取りが短時間ブロックし得るため、GUI から利用する場合は UI スレッドで直接呼ばず worker thread 等で読み取る旨へコメントを更新（ロジック変更なし）。
- **Tests** ([hve/gui/tests/test_terminal_session.py](hve/gui/tests/test_terminal_session.py), [hve/gui/tests/test_gh_login_dialog.py](hve/gui/tests/test_gh_login_dialog.py)): PTY 読み取りが GUI スレッド外で行われ、描画は GUI スレッドへ戻ること、blocking read 中でも端末入力・停止が starvation しないこと、`XtermTerminalView.ready` が controller start に接続されること、および `accept()` / `reject()` / `close()` の各終了経路で session が一度だけ close されることを固定する回帰テストを追加・更新。

**検証**:

- 直接関連: `.venv\Scripts\python.exe -m pytest hve/gui/tests/test_terminal_session.py hve/gui/tests/test_gh_login_dialog.py hve/gui/tests/test_gh_login_button.py -q` → **27 passed**。
- 近接回帰: `.venv\Scripts\python.exe -m pytest hve/gui/tests/test_gh_cli.py hve/gui/tests/test_github_branch_fetch.py hve/gui/tests/test_github_section_consolidation.py -q` → **23 passed**。
- 構文: `python -m py_compile hve/gui/gh_login_dialog.py hve/gui/tests/test_gh_login_dialog.py hve/gui/widgets/terminal_session.py` → OK。

<!-- validation-confirmed -->

### Removed — CLI/GUI: Session State（Resume / セッション永続化）機能の全面削除

**概要**: `gui` と `cli` の「Session State（セッション永続化 / Resume）」機能を全面的に削除した。GitHub Copilot CLI SDK の複数デバイス間セッション管理の実装が不十分であり、現状の Resume 機構（ローカル `session-state/` への状態永続化と再開）が実運用で信頼できないため、機能ごと撤去する。run スコープの一意 `session_id` 生成（fork-on-retry が依存）と mdq usage 集計（mdq 定数に依存）は別機能のため保持した。

- **CLI サブコマンド廃止** ([hve/__main__.py](hve/__main__.py)): `hve resume`（`list` / `show` / `rename` / `delete` / `continue` / `reconcile` / `gc-orphans`）サブコマンドの登録・dispatch、起動時 recovery（`_run_startup_recovery`）、ウィザードの Resume プロンプト群（`_maybe_show_resume_prompt` / `_show_resume_menu` を含む 6 関数）、`session_name` 入力、Ctrl+R 用 `threading` を削除。
- **モジュール削除**: `hve/run_lock.py`（run_id クロスプロセスロック）/ `hve/reconciler.py`（state.json ⇔ SDK セッション整合・Orphan GC）/ `hve/recovery.py`（起動時 recovery）/ `hve/resume_cli.py`（resume サブコマンド実装）/ `hve/keybind.py`（Ctrl+R graceful pause 監視）の 5 モジュールを削除。
- **モジュール縮小**: [hve/run_state.py](hve/run_state.py) は `RunState` / `state.json` 永続化を削除し、保持必須の `make_session_id` / `DEFAULT_SESSION_ID_PREFIX` / `_safe_run_id_component` / `_safe_session_id_token` のみ残置。[hve/run_journal.py](hve/run_journal.py) は `RunJournal`（journal.jsonl）を削除し、mdq usage 定数（`KIND_MDQ_*` / `MDQ_USAGE_LOG_RELATIVE` / `read_mdq_usage_records`）のみ残置。
- **呼び出し側統合の除去** ([hve/orchestrator.py](hve/orchestrator.py), [hve/runner.py](hve/runner.py), [hve/dag_executor.py](hve/dag_executor.py)): `resume_state` / `RunJournal` 注入、ステップ checkpoint（`_record_checkpoint`）、`KeybindMonitor` / graceful pause、Resume 再開ショートカット、Resume 関連コールバック・コメントを除去。フォーク session_id 再構成（`make_session_id`）は維持。
- **永続化ディレクトリ削除**: git 追跡されていた `session-state/`（state.json / journal.jsonl / .lock / stats-history.json 計 357 ファイル）を削除。[.gitignore](.gitignore) と [mdq.toml](mdq.toml) の `session-state` 参照も除去。
- **mdq 指標の廃止** ([mdq/usage_stats.py](mdq/usage_stats.py), [tools/skills/markdown_query/vendor/mdq/usage_stats.py](tools/skills/markdown_query/vendor/mdq/usage_stats.py), [tools/skills/markdown_query/generate_usage_report.py](tools/skills/markdown_query/generate_usage_report.py)): `session-state/runs/*/state.json` を走査していた G1（step completion rate diff）/ G4（retry count diff）指標と関連ヘルパーを削除。他指標（E/F/A/B/C/D 系）は維持。
- **GUI 統計の永続化廃止** ([hve/gui/page_workbench.py](hve/gui/page_workbench.py)): `session-state/runs/<run_id>/stats-history.json` への統計履歴保存（`StatsHistoryStore`）を削除。Workbench のライブ統計表示（in-memory）は維持。
- **ドキュメント更新** ([hve-dev/requirement-definition.md](hve-dev/requirement-definition.md), [users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md), [users-guide/hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md), [users-guide/troubleshooting.md](users-guide/troubleshooting.md)): UC-05・FR-CLI（resume 系）・NFR（COMP/CONC/PERF/REL/OBS 系）を廃止マーク。CLI/GUI ガイド・トラブルシューティングの Resume 節を廃止注記へ置換。
- **テスト整理**: Resume 専用テスト（resume_cli / run_lock / reconciler / recovery / keybind / step_checkpoint / run_state 永続化系 等）を削除し、影響テストから Resume 依存箇所を除去（tool 伝播・blocked/error 終了コード判定など本来の検証意図は他テストで維持）。

**検証**:

- 残存参照 grep: 本番ソース（`hve/` / `mdq/` / `tools/`）に `RunState` / `RunJournal` / `run_lock` / `reconciler` / `recovery` / `resume_cli` / `keybind` / `_record_checkpoint` / `HVE_SESSION_STATE_*` の残存 0 を確認。
- テストコレクション: `python -m pytest hve/tests/ mdq/tests/ hve/gui/tests/ --collect-only` → **4545 件収集・0 エラー**。
- 回帰判定（pristine HEAD worktree との全 `hve/tests/` 失敗集合差分比較）: 本変更による新規失敗 **0**。差分で検出した 2 件（`test_resume_session_keys_includes_tools` / `test_main_source_includes_blocked_branch_before_error_branch`）は Resume 削除に追従して修正済み。残失敗は全て HEAD と同一の pre-existing（option parity fixture / model API ログイン / self-improve relative-import 等、本削除と無関係）。

**スコープ外（意図的に対象外）**:

- `hve/cloud_session.py`（Cloud Sessions = クラウドへのステップ・オフロード）、`hve/gui/session_menu.py`（プロセス制御）、`hve/gui/session_workdir.py`（`work/run/<id>/` 隔離）、`hve/gui/state_bridge.py`（subprocess stdout ブリッジ）: いずれも「セッション状態の永続化 / Resume」ではないため非対象。
- `make_session_id` 系 / mdq usage 定数: 別機能（fork-on-retry / mdq 集計）が依存するため保持。

<!-- validation-confirmed -->

### Changed — GUI: 設定画面 C5「GitHub」セクションの各項目をグループ枠（QGroupBox）で整理

**概要**: 設定画面の C5「GitHub」セクション（`_C5IssuePR`）に並ぶ各入力項目を、機能ごとの 6 つのグループ枠（`QGroupBox`）に整理した。従来は全項目が単一の縦並びで表示されていたため、認証・Issue/PR 作成・リポジトリ設定・ベースブランチ・PR 自動マージ・Copilot SDK 連携が視覚的に区別できなかった。グループは「認証」「ソースコード管理」「リポジトリ / Issue 設定」「ベースブランチ」「PR 自動 Approve & Auto-merge」「GitHub Copilot SDK 連携」の順で表示する。GitHub Issue 作成 / Pull Request 作成 / git add 除外パスの 3 項目は「ソースコード管理」グループにまとめた。

各入力ウィジェットの属性名・生成順・シグナル接続・`to_args()` は一切変更しておらず、表示のグルーピング（各ウィジェットの追加先レイアウトを `QGroupBox` の内部レイアウトへ変更）のみを行った。これにより `settings_apply`（`getattr` ベースの設定反映）および既存テスト（属性参照ベース）への影響はない。

- **GUI** ([hve/gui/page_options.py](hve/gui/page_options.py)): `_C5IssuePR.__init__` に、グループ枠を生成して内部レイアウトを返すローカルヘルパ `_group(title)` を追加し、各項目を 6 グループへ振り分けて追加。フィールドの定義内容（`tr()` 文字列・プレースホルダ・ツールチップ・ハンドラ接続）は従来のまま。
- **i18n** ([hve/gui/i18n/hve_gui_en_US.ts](hve/gui/i18n/hve_gui_en_US.ts), [hve/gui/i18n/hve_gui_en_US.qm](hve/gui/i18n/hve_gui_en_US.qm)): `_C5IssuePR` コンテキストに新規グループタイトル 6 件の英訳を追加（認証=Authentication / ソースコード管理=Source Code Management / リポジトリ / Issue 設定=Repository / Issue Settings / ベースブランチ=Base branch / PR 自動 Approve & Auto-merge=PR Auto Approve & Auto-merge / GitHub Copilot SDK 連携=GitHub Copilot SDK Integration）。`ベースブランチ` は既存訳 `Base branch` を再利用。その後 `pyside6-lupdate` で `.ts` の `location` 情報を現行ソースと同期・正規化し（6 件すべて翻訳維持・`finished`・正しい行番号付与）、`pyside6-lrelease` で `.qm` を再生成。
- **Tests/新規** ([hve/gui/tests/test_github_section_grouping.py](hve/gui/tests/test_github_section_grouping.py)): 6 グループの生成順・タイトル、「ソースコード管理」グループへの 3 項目（Issue 作成 / PR 作成 / git add 除外パス）の所属、代表ウィジェットのグループ帰属、全入力ウィジェット属性の保持を検証する 4 ケース。

**検証**:

- 新規テスト: `python -m pytest hve/gui/tests/test_github_section_grouping.py -q` → **4 passed**。
- 回帰確認（C5 機能・設定反映・OptionsPage 構築・i18n・github.com CI/CD 境界）: `python -m pytest hve/gui/tests/test_gh_login_button.py hve/gui/tests/test_github_branch_fetch.py hve/gui/tests/test_github_cicd_gui.py hve/gui/tests/test_page_options_reorder.py hve/gui/tests/test_settings_apply_sources_persistence.py hve/gui/tests/test_settings_apply_skip_keys.py hve/gui/tests/test_i18n.py -q` → **71 passed**。
- GUI 全スイート: `python -m pytest hve/gui/tests/ -q --continue-on-collection-errors` → **909 passed, 1 skipped**（唯一の 1 error は本変更と無関係な並行リファクタ由来の `test_stats_history_store.py` の `ModuleNotFoundError: hve.gui.stats_history_store`）。
- i18n 実機: `.qm` を `QTranslator` でロードし、`_C5IssuePR` コンテキストで 6 タイトルが英訳へ解決されること、既存翻訳が退行していないことを確認。
- i18n 正規化後の再検証: `pyside6-lupdate` で `.ts` を現行ソースと同期（translation 種別: finished 327 / unfinished 224 / vanished 135）した後、`python -m pytest hve/gui/tests/test_i18n.py hve/gui/tests/test_github_section_grouping.py hve/gui/tests/test_gh_login_button.py hve/gui/tests/test_github_branch_fetch.py -q` → **28 passed**。
- 構文: `python -c "import ast; ast.parse(...)"` → OK。

**スコープ外（オーバーエンジニアリング回避のため意図的に除外）**:

- グループ枠の折りたたみ（collapsible）化・並べ替え機能の追加: 指示は「分類して整理」であり、表示構造の変更のみで足りるため、開閉状態管理等の機構は追加しない（YAGNI）。
- `settings_apply` / `settings_store` / `settings_window` / `help_content` の変更: 属性名・既定値・節ヘルプは不変であり、グルーピングは表示層に閉じるため変更不要。
- github.com CI/CD トグルのグルーピング: 当該トグルは別変更で C5（`_C5IssuePR`）から APP-ID セクション（`_C10AppId`）へ移設済みのため、C5 セクションのスコープ外。
- `pyside6-lupdate` で判明した他コンテキストの未訳 224 件（MainWindow / _C1Basic / AttachmentPane / _C3AutoPrompt 等、並行リファクタで蓄積した既存 i18n 債務）の英訳投入: 本変更（C5 セクションのグルーピング）のスコープ外であり、各機能の文脈を要するため各担当の別タスクとする。`pyside6-lrelease` は `finished` のみ `.qm` に反映するため、未訳分はソース日本語へフォールバックし機能的退行はない。

<!-- validation-confirmed -->

### Changed — GUI: github.com CI/CD トグルを Step 1 右パネルのワークフロー枠内へ移動

**概要**: github.com CI/CD 実行トグル（A2 方式）の表示位置を、設定セクション（C5「GitHub」）から **Step 1 ワークフロー選択画面の右パネル**へ移した。ASDW-WEB / ADFDV のいずれかを選択すると、右パネルの当該ワークフロー枠（例「Web App Dev & Deploy (ASDW-WEB)」）内に、APP-ID やユースケース ID と並んでトグルが表示される。C5「GitHub」セクションは Step 1 右パネルでは常時非表示（`_STEP2_HIDDEN_CATEGORIES`）のため、従来位置ではワークフロー選択画面にトグルが現れなかった問題を解消する。トグルの説明文に、事前に github.com 側で必要な設定項目（COPILOT_PAT / Azure OIDC Secrets / Copilot Coding agent 有効化 / Workflow permissions）を明記した。

実装は既存の「ワークフロー固有フィールドを右パネル枠へ移設する機構」（`_STEP2_FIELDS_BY_WORKFLOW` + `_ensure_lf_registry` + `_refresh_specific_categories`）を再利用し、専用の枠生成ロジックは新設していない。

- **GUI** ([hve/gui/page_options.py](hve/gui/page_options.py)): `github_cicd_enabled` トグルを `_C5IssuePR` から `_C10AppId` へ移設（タイトルは `_C10AppId.GITHUB_CICD_FIELD_TITLE` 定数で固定し、レジストリ登録キーと一致させる）。`_STEP2_FIELDS_BY_WORKFLOW` の `asdw-web` / `adfdv` に当該フィールドを登録し、右パネルのワークフロー枠へ自動移設。C5 側の旧トグル定義・`set_github_cicd_visible()` メソッド・`set_workflows()` 内の呼び出し・`to_args()` の旧参照を削除。`_C10AppId.to_args()` で `args.github_cicd_enabled` に反映。説明文に前提 github 設定項目を追記。
- **GUI** ([hve/gui/main_window.py](hve/gui/main_window.py)): `_maybe_launch_github_cicd()` のトグル参照を `c5.github_cicd_enabled` → `c10.github_cicd_enabled` へ更新。非対象ワークフローでトグル状態が残っても「トグル ON かつ対象ワークフロー選択」の二重ガードで誤起動しない旨を docstring に明記。
- **Tests** ([hve/gui/tests/test_github_cicd_gui.py](hve/gui/tests/test_github_cicd_gui.py)): C5 前提のテスト（`TestC5Visibility`）を `_C10AppId` 前提の `TestC10Toggle` へ置換。`TestOptionsPageVisibility` の検証を、offscreen で不安定な `isVisible()` から `_workflow_group_boxes`（動的生成ワークフロー枠のみ）への所属判定へ変更し、非表示の元カテゴリ枠を誤検出しないよう修正。`TestMaybeLaunchGithubCicd` の `c5` 参照を `c10` へ更新。

**検証**:

- github_cicd 関連テスト: `python -m pytest hve/gui/tests/test_github_cicd_gui.py hve/gui/tests/test_github_cicd.py -q` → **29 passed**。
- 回帰確認: `python -m pytest hve/gui/tests/test_page_options_*.py hve/tests/test_gui_pages.py hve/tests/test_gui_help_content.py -q` → **75 passed**。
- 実機確認（offscreen）: ASDW-WEB / ADFDV 選択時にトグルが当該ワークフロー枠（`_workflow_group_boxes`）内へ移設されること、aad-web 等の非対象選択時は移設されないこと、`build_args` 経由で `github_cicd_enabled` が ON/OFF 反映されることを確認。
- 構文: `python -m py_compile hve/gui/page_options.py hve/gui/main_window.py` → OK。

<!-- validation-confirmed -->

### Added — TDD RED/GREEN リアリティ検証をプラットフォーム非依存に汎用化（reality gate の registry 駆動化＋汎用 Skill）

**概要**: デプロイ/実装の「実在」を強制する TDD reality gate が Azure 専用エージェント名 6 本のハードコード辞書（`hve/artifact_validation._DEPLOY_AGENT_REALITY_AC`）に閉じており、対象外の Azure サービス・新エージェント、および AWS / GCP / Windows / iOS など非 Azure プラットフォームでは gate が一切発火しない（allowlist 外＝リアリティ強制ゼロ）構造的な汎用性ギャップを是正した。あわせて、reality gate の必須 AC が各 prompt の AC テーブルと乖離していた問題（例: 前エントリで AddServiceDeploy prompt に追加した `AC-13`（Foundry モデルデプロイ実在）が gate では非強制だった穴）を、registry 宣言で gate に接続して塞いだ。Azure サービスの選定はワークフロー実行時に Microsoft Learn MCP 等で機能要件・非機能要件に応じて毎回更新される前提のため、生成物（`/docs`・`/src`）ではなく生成元（registry / gate ロジック / prompt / Skill）のみを変更した。

- **Skill 新設** ([.github/skills/testing/tdd-red-green-reality/SKILL.md](.github/skills/testing/tdd-red-green-reality/SKILL.md)): プラットフォーム非依存の RED/GREEN リアリティ原則を一元化。(1) RED/GREEN は実コマンド出力で証明する、(2) 恒真式アサーション（`count >= 0` 等・常に真の主張）を存在性/基本 I/O 判定に使わない、(3)「利用可能（カタログ/リージョン）」と「実在（デプロイ済み）」を混同しない、(4) verify コマンドは対象プラットフォーム（Azure=Microsoft Learn MCP / AWS=`aws` / GCP=`gcloud` / Windows=`dotnet test` / iOS=`xcodebuild test`）ごとに実行時の公式ドキュメントから確定し捏造しない、を規定。[routing 表](.github/skills/_routing/README.md) に登録。
- **Registry 駆動 gate** ([hve/workflow_registry.py](hve/workflow_registry.py), [hve/artifact_validation.py](hve/artifact_validation.py), [hve/runner.py](hve/runner.py)): `StepDef` に `reality_gate_acs: List[str]` を追加。`validate_deploy_ac_verification` に `required_acs` 引数を追加し、registry 宣言があれば Agent 名ハードコード辞書を介さず（＝**非 Azure エージェントでも**）実在系 AC を検証、無ければ後方互換で従来辞書にフォールバック。`_run_deploy_ac_gate` は `_resolved_workflow` から `reality_gate_acs` を解決（fan-out 子 step は基底 ID で照合）し、registry 宣言があれば allowlist 外でも gate を発火させる。条件付き実在系 AC（例: AI/LLM 採用時のみの AC-13）は状態欄 `N/A` / `該当なし` を GREEN 扱いとし、行ごと省略は「記録漏れ」として fail させる。
- **AC-13 の gate 接続** ([hve/workflow_registry.py](hve/workflow_registry.py), [.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md)): AddServiceDeploy（asdw-web Step.2.2）の StepDef に `reality_gate_acs=["AC-1", "AC-13"]` を宣言し、前エントリで prompt に追加済みの AC-13 を gate で実強制化。`ac-verification.md` フォーマット規約に「AC-13 は AI/LLM 採用時 `✅` のみ許容、非該当時は `N/A` 行を必ず残す」を明記し gate と整合。
- **TDD エージェントへの Skill 結線** (TestCoding 6 本 + Testing 系 2 本): [DataTestCoding](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md) / [ServiceTestCoding](.github/prompts/Dev-Microservice-Azure-ServiceTestCoding.prompt.md) / [AgentTestCoding](.github/prompts/Dev-Microservice-Azure-AgentTestCoding.prompt.md) / [UITestCoding](.github/prompts/Dev-Microservice-Azure-UITestCoding.prompt.md) / [AddServiceTestCoding](.github/prompts/Dev-Microservice-Azure-AddServiceTestCoding.prompt.md) / [Dataflow-TestCoding](.github/prompts/Dev-Dataflow-TestCoding.prompt.md) / [AddServiceTesting](.github/prompts/Dev-Microservice-Azure-AddServiceTesting.prompt.md) / [ComputePostDeployTest](.github/prompts/Dev-Microservice-Azure-ComputePostDeployTest.prompt.md) の「Agent 固有の Skills 依存」に `tdd-red-green-reality` を追加。
- **Tests**: [hve/tests/test_tdd_red_green_reality_contract.py](hve/tests/test_tdd_red_green_reality_contract.py)（新規 6 件）で Skill 実在・恒真式禁止・多プラットフォーム verify 指針・「利用可能 vs 実在」・routing 登録・8 本の結線を固定。[hve/tests/test_artifact_validation_deploy_gate.py](hve/tests/test_artifact_validation_deploy_gate.py)（新規 7 件）で registry 駆動の非 allowlist 発火・dict 上書き・N/A 許容・行欠落 fail・後方互換フォールバック・StepDef 宣言を固定。

**検証**:

- `.venv\Scripts\python.exe -m pytest hve/tests/test_artifact_validation_deploy_gate.py hve/tests/test_tdd_red_green_reality_contract.py hve/tests/test_asdw_web_addservice_deploy_contract.py hve/tests/test_workflow_registry.py -q` → **162 passed**。
- runner を含む広域回帰 `hve/tests/test_runner.py` 他 → **326 passed**（resume / checkpoint 系の回帰なし）。
- `.venv\Scripts\python.exe .github/scripts/validate-skill-routing.py` の ERROR 件数は新 Skill 追加前後で **23 → 23**（新規エラーゼロ。既存 23 件は未変更の `azure-skills/` 由来の pre-existing）。

**スコープ外（オーバーエンジニアリング回避のため意図的に除外）**:

- AWS / GCP / Windows / iOS の具体的な Deploy / TestCoding エージェントの新設: 実装先はワークフロー実行時の要件と Microsoft Learn MCP 等の選定で毎回変わるため、実需が生じるまで作らない（YAGNI）。汎用 Skill と registry 駆動 gate の足場のみを用意し、プラットフォーム固有コマンドは実行時に公式ドキュメントから確定させる。
- test-execution 系（GREEN テスト実行）への新規 gate 機構の追加: prompt 契約（恒真式禁止・実出力）と既存の verification-loop で足りるため、機械 gate の対象はデプロイ系の registry 駆動化に留める。
- 既存 6 エージェントの辞書廃止・registry 完全移行: 後方互換のため辞書はフォールバックとして温存。
- 実装系 Coding エージェント（ServiceCoding / UICoding / AgentCoding / Dataflow-ServiceCoding）への Skill 結線: GREEN を実装で達成する性質上、恒真式禁止・実出力 verify の主対象は TestCoding / Testing 系であり、結線価値が薄いため対象外。

<!-- validation-confirmed -->

### Added — GUI: ASDW-WEB / ADFDV を github.com 上で CI/CD 全自動実行する設定（A2 方式）

**概要**: GUI 設定画面（C5「GitHub」セクション）に「github.com で CI/CD を実行（ASDW-WEB / ADFDV）」トグルを追加した。ASDW-WEB / ADFDV ワークフロー選択時のみ表示され、ON にして実行すると、ローカル DAG 実行の代わりに、対応する Issue Template の new-issue フォーム（プリフィル付き）をブラウザで開くポップアップを表示する。フォーム送信後は github.com 上で Copilot Coding Agent と GitHub Actions が「Issue 作成 → branch 作成 → 作業 → commit → push → PR 作成 → 自動 Approve & squash merge」までを全自動実行する（既存 Cloud 機構を再利用）。

ローカルから API で Issue を直接作成する方式（A1）は採用しなかった。Cloud の reusable workflow が Issue body を Issue Template フォーム形式（`### PR完全自動化設定` + `- [x]` 等）でパースするのに対し、CLI の Issue body ビルダーは HTML コメント形式（`<!-- auto-merge: true -->`）を出力するため両者が不一致で、A1 では auto-merge が発火しない。A1 でフォーム形式を Python 側に複製すると Issue Template との二重実装になるため、正規の Issue Template 経路を再利用する A2 方式を採用した。

- **GUI/新規** ([hve/gui/github_cicd.py](hve/gui/github_cicd.py)): Issue Template の new-issue フォーム URL を構築する純粋関数（`build_issue_form_url` / `is_github_cicd_workflow` / `GITHUB_CICD_WORKFLOWS`）。`asdw-web` → `web-app-dev.yml`、`adfdv` → `dataflow-dev.yml` にマップし、`app_ids` / `branch` / `resource_group` をプリフィルする。`repo` のセグメントは `urllib.parse.quote(safe="")` でエンコードし URL 構造破壊を防ぐ。`auto_merge` チェックボックスは GitHub Issue Forms の仕様上 URL プリフィル不可のため対象外（ダイアログで手動操作を案内）。
- **GUI/新規** ([hve/gui/github_cicd_dialog.py](hve/gui/github_cicd_dialog.py)): 実行直前ポップアップ `GitHubCicdDialog`。前提条件（`COPILOT_PAT` / Azure OIDC Secrets / Copilot Cloud agent 有効化 / Workflow permissions）を案内し、リポジトリを確認・入力（`owner/repo` 形式が有効なときのみ「開く」ボタン活性化）してフォームをブラウザ起動する。秘密情報は入力させず登録場所の案内のみ。
- **GUI** ([hve/gui/page_options.py](hve/gui/page_options.py)): C5「GitHub」セクションに `github_cicd_enabled` トグル（`_LabeledField`、既定非表示）と `set_github_cicd_visible()` を追加。`OptionsPage.set_workflows()` で ASDW-WEB / ADFDV 選択時のみ表示し、非表示化時はチェックを外す。`to_args()` で `args.github_cicd_enabled` に反映。
- **GUI** ([hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py)): `github_cicd_enabled` フィールドを追加（GUI 内部フラグのため `to_argv()` には出力しない）。
- **GUI** ([hve/gui/main_window.py](hve/gui/main_window.py)): `_on_run_clicked` に `_maybe_launch_github_cicd()` 分岐を追加。トグル ON かつ対象ワークフロー選択時はダイアログを表示してローカル実行をスキップ（排他）。
- **Tests** ([hve/gui/tests/test_github_cicd.py](hve/gui/tests/test_github_cicd.py)): URL 生成・ワークフロー判定・プリフィル・URL エンコード・不正入力の 14 ケース。
- **Tests** ([hve/gui/tests/test_github_cicd_gui.py](hve/gui/tests/test_github_cicd_gui.py)): ダイアログのボタン活性制御・ブラウザ起動、C5 可視性、OptionsPage 連動、`_maybe_launch_github_cicd` 分岐（複数ワークフロー混在時の対象選択を含む）の 16 ケース。

**検証**:

- 新規テスト 2 ファイル: `python -m pytest hve/gui/tests/test_github_cicd.py hve/gui/tests/test_github_cicd_gui.py -q` → **30 passed**（14 + 16）。
- 回帰確認: `python -m pytest hve/gui/tests/test_page_options_*.py hve/tests/test_gui_pages.py -q` → **63 passed**。`python -m pytest hve/tests/test_gui_help_content.py -q` → **12 passed**（`OrchestrateArgs` 全フィールド照合を含む）。
- 構文: `python -m py_compile hve/gui/github_cicd.py hve/gui/github_cicd_dialog.py hve/gui/page_options.py hve/gui/orchestrate_args.py hve/gui/main_window.py` → OK。
- `OrchestrateArgs.github_cicd_enabled` が `to_argv()` に出力されないことを確認（GUI 内部フラグ）。
- 既知の pre-existing 失敗（本変更と無関係）: `hve/tests/test_phase6_option_parity.py` の 18 件は `batch-design.yml` / `batch-dev.yml` 不在および fixture 未登録の既存 SDKConfig フィールドに起因（本変更は `config.py` を変更していない）。

<!-- validation-confirmed -->

### Added — GUI 設定画面から GitHub CLI ログイン（埋め込み端末）

**概要**: GUI 設定画面の **[連携 > GitHub]**（`_C5IssuePR`）に **「GitHub CLI でログイン」** ボタンを追加した。押下すると埋め込み端末（xterm.js）で `gh auth login` を対話実行し、完了後に `gh auth token` で取得したトークンを **このセッション限り** `GH_TOKEN` 環境変数へ注入する。これにより同セクションの「ブランチ取得」や Issue / PR 作成（`hve.github_api` の GitHub REST 経路）が有効化される。従来 GUI 内に実装済みだが本番未配線だった PTY 抽象層（[hve/gui/pty_backend.py](hve/gui/pty_backend.py)）と xterm ターミナルビュー（[hve/gui/widgets/xterm_terminal_view.py](hve/gui/widgets/xterm_terminal_view.py)）を初めて結線する。`gh` 不在 / PTY バックエンド不在時は端末を起動せず案内文を表示する。トークンはディスクへ永続化しない。

- **Code** ([hve/gui/widgets/terminal_session.py](hve/gui/widgets/terminal_session.py)): 新規。`TerminalSessionController` — `PtySession` の出力を `QTimer` ポーリングで端末ビューへ流し、端末入力 / リサイズを PTY へ転送し、子プロセス終了を `finished(exit_code)` で通知する配線層（QWebEngine 非依存でテスト可能）。
- **Code** ([hve/gui/gh_cli.py](hve/gui/gh_cli.py)): 新規。`find_gh_binary` / `capture_gh_token`（`gh auth token`）/ `inject_token_into_env`（`GH_TOKEN` へセッション注入）。
- **Code** ([hve/gui/gh_login_dialog.py](hve/gui/gh_login_dialog.py)): 新規。`GhLoginDialog` — 事前チェック（gh / PTY）→ 埋め込み端末で `gh auth login` を実行するモーダルダイアログ。前提不足時は案内文へフォールバック。
- **Code** ([hve/gui/page_options.py](hve/gui/page_options.py)): `_C5IssuePR` に「GitHub CLI でログイン」ボタン・状態ラベル・`_on_gh_login_clicked`（ダイアログ実行 → トークン取得 → `GH_TOKEN` 注入 → 状態更新）を追加。成否は exit code でなくトークン取得可否で独立確認する。
- **Tests** ([hve/gui/tests/test_terminal_session.py](hve/gui/tests/test_terminal_session.py), [hve/gui/tests/test_gh_cli.py](hve/gui/tests/test_gh_cli.py), [hve/gui/tests/test_gh_login_dialog.py](hve/gui/tests/test_gh_login_dialog.py), [hve/gui/tests/test_gh_login_button.py](hve/gui/tests/test_gh_login_button.py)): 新規。配線・トークン取得・事前チェック分岐・ボタン挙動を mock で検証（実 `gh` / 実ダイアログ非起動、offscreen）。
- **Docs** ([users-guide/hve-gui-getting-started.md](users-guide/hve-gui-getting-started.md)): 「GitHub CLI で認証」節に GUI ボタンからのログイン手順・前提・セッション限りの注意・スコープ留保を追記。

**検証**:

- 新規 4 テスト + 既存 C5 テスト（[hve/gui/tests/test_github_branch_fetch.py](hve/gui/tests/test_github_branch_fetch.py) / [hve/gui/tests/test_github_section_consolidation.py](hve/gui/tests/test_github_section_consolidation.py)）の統合実行 `python -m pytest hve/gui/tests/test_terminal_session.py hve/gui/tests/test_gh_cli.py hve/gui/tests/test_gh_login_dialog.py hve/gui/tests/test_gh_login_button.py hve/gui/tests/test_github_branch_fetch.py hve/gui/tests/test_github_section_consolidation.py -q` → **44 passed**（ボタン追加による C5 回帰なし）。
- テストは実 `gh` / 実ダイアログを一切起動しない（`pty_backend.spawn` / `XtermTerminalView` / `GhLoginDialog` / `gh_cli` を mock）。
- `page_options.py` の型チェッカー指摘は PySide6 enum スタブに対する既存の誤検出（追加コード行に新規エラーなし）。

<!-- validation-confirmed -->

### Fixed — ASDW-WEB 追加サービス（Step.2.2〜2.4）の Microsoft Foundry が「クラシック作成のみ・モデル未デプロイ」でも GREEN になる構造的欠陥を生成元の品質契約で是正

**概要**: ASDW-WEB ワークフローのコンテナ2（追加サービス）で、AI/LLM 用 **Microsoft Foundry** が「クラシック（project 管理無効）な AIServices アカウント作成のみ」でデプロイされ、**モデルデプロイが一度も行われない**にもかかわらずテストが GREEN になる構造的欠陥を、生成元（prompt / テンプレート / 契約テスト）の修正で是正した。欠陥は 3 層すべてが「アカウント実在 + `provisioningState`」しか検証していなかったことに起因する: (1) デプロイ層（`Dev-Microservice-Azure-AddServiceDeploy`）の生成 prompt に Foundry のモデルデプロイ・project 管理対応の具体指示が無く、AC が `provisioningState=Succeeded` のみ、(2) テストコード生成層（`AddServiceTestCoding`）の生成 prompt が恒真式アサーション（`Assert.True(count >= 0)`、数学的に常に真）を許容し、`subscription.GetModelsAsync`（リージョン利用可能モデル）をデプロイ実在と混同、(3) テンプレート `step-2.3.md` が「全テスト FAIL（TDD RED）」を名乗る一方、生成 prompt は「FAIL を強制しない」と矛盾。生成物（`src/infra/`・`src/test/`・`docs/test-specs/` のスクリプト/テスト）は毎回再生成されるため**直接是正の対象外**とし、毎回正しく再生成されるよう生成元に品質契約を追加した。CLI 仕様（`az cognitiveservices account create --allow-project-management` / `az cognitiveservices account deployment create|list`）は Microsoft Learn 一次情報で確定。`--allow-project-management` は既定 true だが CLI バージョン依存の既定変化を排すため明示指定を必須化した。

- **Prompt** ([.github/prompts/Dev-Microservice-Azure-AddServiceDesign.prompt.md](.github/prompts/Dev-Microservice-Azure-AddServiceDesign.prompt.md)): §3.1 AI/LLM 強制ルールに、後続デプロイがモデルデプロイを決定論的に実行できるよう、デプロイ対象モデルの必須情報（`モデル名` / `モデルバージョン` / `モデルフォーマット` / `デプロイ種別(sku-name)` / `容量(sku-capacity)`）を定型キー（セル内 ` / ` 区切り・新列やセル内改行は追加しない）で構成要点欄へ明記する指示を追加。デプロイ種別とアカウント SKU（`S0`）の混同を防ぐ注記も追加。本 Agent は AAD-WEB Step.2.5 でも共有され、両ワークフローともデプロイへ供給するため波及は設計意図どおり。
- **Prompt** ([.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md)): §3.3.2「AI/LLM（Microsoft Foundry）サービスの追加デプロイ要件（必須）」を新設。(1) `--allow-project-management` 明示でのアカウント作成（既存スクリプトに無ければ欠陥として是正）、(2) `az cognitiveservices account deployment create` でのモデル冪等デプロイ（ad-hoc でなく再生成スクリプトに実装）、(3) モデル用 env 変数の決定的定義、(4) `verify-additional-resources.sh` への「デプロイ済みモデル >= 1（0 件 FAIL）」TC 追加、(5) テスト仕様書へのモデル TC を必須化。AC 表に **AC-13**（デプロイ済みモデル実在・AI/LLM 非該当は N/A）を追加し、`ac-verification.md` の実在系（✅ のみ許容）を AC-1 / AC-13 へ拡張。
- **Template** ([.github/scripts/templates/asdw-web/step-2.2.md](.github/scripts/templates/asdw-web/step-2.2.md)): デプロイ TDD フローに「AI/LLM 採用時は `--allow-project-management` 明示 + モデルデプロイ必須、検証はデプロイ済みモデル 1 件以上（0 件 FAIL）」の注記を追加（Prompt §3.3.2 / AC-13 参照）。
- **Prompt** ([.github/prompts/Dev-Microservice-Azure-AddServiceTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-AddServiceTestCoding.prompt.md)): 禁止事項に「恒真式アサーション禁止」（存在性・基本 I/O 判定に `Assert.True(count >= 0)` 等の恒真式を使わない。権限境界の no-exception 検証は許容）を追加。§5.3 に「Foundry は少なくとも 1 つのテストが `account.GetCognitiveServicesAccountDeployments()` でデプロイ済みモデル >= 1 を検証（0 件 FAIL）。`subscription.GetModelsAsync`（リージョン利用可能モデル）を合否判定に使わない」を追加。
- **Template** ([.github/scripts/templates/asdw-web/step-2.3.md](.github/scripts/templates/asdw-web/step-2.3.md)): 「全テスト FAIL（TDD RED）強制」表現を prompt 方針（実装未着手ゆえの FAIL は強制しないが、モデル未デプロイ等の実欠陥は FAIL）と整合。整備時の「本仕様作成は別タスク」スタブ注記を除去し、恒真式アサーション不使用を完了条件に明記。
- **Prompt** ([.github/prompts/Dev-Microservice-Azure-AddServiceTesting.prompt.md](.github/prompts/Dev-Microservice-Azure-AddServiceTesting.prompt.md)): 失敗分類 C3 に「Foundry モデル未デプロイ（`deployment list` が 0 件）はモデルデプロイ＝ Step.2.2 の責務のため自己対応せず即中断して Step.2.2 へフィードバック」、C4 に「モデル SKU / 容量の不一致は Step.2.1 へ」を追加。
- **Template** ([.github/scripts/templates/asdw-web/step-2.4.md](.github/scripts/templates/asdw-web/step-2.4.md)): Foundry モデル未デプロイ時に `asdw-web:blocked` で停止して RED を可視化（自動再実行なし）し Step.2.2 へフィードバックする旨を追記。「本仕様作成は別タスク」スタブ注記を除去。
- **Tests** ([hve/tests/test_asdw_web_addservice_deploy_contract.py](hve/tests/test_asdw_web_addservice_deploy_contract.py)): 契約テストの責務をコンテナ2（Step.2.2〜2.4）全体へ拡張。上記 7 ファイル（4 prompt + 3 テンプレート）の追加品質契約が消えないことをキーフレーズ部分一致で固定する 10 件を追加（脆性低減のため文言完全一致は避ける）。

**検証**:

- `.venv\Scripts\python.exe -m pytest hve/tests/test_asdw_web_addservice_deploy_contract.py -q` → **16 passed**（既存 6 + 新規 10）。
- 回帰: `test_workflow_registry.py` + `test_asdw_web_data_deploy_contract.py`（兄弟）→ **112 passed**。`test_template_engine.py` → **122 passed / 1 failed**。失敗 1 件は [hve/tests/test_template_engine.py](hve/tests/test_template_engine.py) の `TestCollectParams::test_aad_collect_params_with_multiple_app_ids`（AAD ワークフローの対話入力モック未追従による既知の pre-existing 失敗）。`git status` で `template_engine.py` / `workflow_registry.py` が未変更であることを確認し、本変更（asdw-web の prompt / テンプレ / 契約テストのみ）と無関係であることを物的に確定。
- CLI 仕様は Microsoft Learn 一次情報で確認（[az cognitiveservices account](https://learn.microsoft.com/cli/azure/cognitiveservices/account) の `--allow-project-management` / [az cognitiveservices account deployment](https://learn.microsoft.com/cli/azure/cognitiveservices/account/deployment) の `create` / [Foundry project 作成](https://learn.microsoft.com/azure/foundry/how-to/create-projects)）。

**既知の制約**:

- Cloud reusable workflow [.github/workflows/auto-app-dev-microservice-web-reusable.yml](.github/workflows/auto-app-dev-microservice-web-reusable.yml) は `AddServiceDeploy` の step 本文をインライン保持しており（OUT-OF-SYNC NOTICE 既定）、本タスクでは未同期。Cloud 経路でも同等の品質契約を反映する同期は別タスク推奨。

**スコープ外（オーバーエンジニアリング回避のため意図的に除外）**:

- 生成物（`src/infra/azure/`・`src/test/integration/add-service/`・`docs/test-specs/`・`docs/azure/`）の直接是正: 毎回再生成されるため生成元の修正で対応。
- live Azure 環境での実デプロイ検証: 実環境が必要なため本タスクは生成元の契約テスト + 文言固定までを検証範囲とする。
- verify TC の「全宣言モデル一致」検証: ユーザー指摘の核心（モデル 0 件）は「デプロイ済みモデル >= 1」で直接是正されるため、複数宣言時の部分デプロイ検出は YAGNI として見送り。

<!-- validation-confirmed -->

### Added — ローカル（GUI / CLI）からの CI/CD 有効化ガイドを追加

**概要**: GUI / CLI Orchestrator をローカル PC で実行した場合に、生成された GitHub Actions デプロイワークフロー（`.github/workflows/deploy-*.yml` 等）を GitHub 上で実際に動かして CI/CD を有効化する手順をまとめた新規ガイド [users-guide/local-cicd-enablement.md](users-guide/local-cicd-enablement.md) を追加した。Cloud は最初から GitHub.com 上でワークフローが生成・反映されるのに対し、ローカル実行では生成物がローカル作業ツリーに留まるため、`--create-pr` での PR 作成 → `main` マージ → ワークフロー発火という反映手順が別途必要になる点を説明する。OIDC Secrets の前提、`workflow_dispatch` による手動発火、対象ワークフロー（`asdw-web` / `adfdv`）と生成物の対応、`--create-pr` が自動マージしないこと等を記載した。CLI / GUI の各「はじめかた」ガイドの「次のステップ」から本ガイドへの導線も追加した。

- **Docs** ([users-guide/local-cicd-enablement.md](users-guide/local-cicd-enablement.md)): 新規作成。ローカル実行で CI/CD を有効化する手順・前提・対象ワークフロー・注意点・検証手順を記載。
- **Docs** ([users-guide/hve-cli-getting-started.md](users-guide/hve-cli-getting-started.md), [users-guide/hve-gui-getting-started.md](users-guide/hve-gui-getting-started.md)): 「次のステップ」セクションに本ガイドへのリンクを追加。

**検証**:

- 記載事実を一次情報と照合: `--workflow asdw-web` の有効性（[users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md) の使用例）、デプロイエージェント名・Step 番号（[hve/workflow_registry.py](hve/workflow_registry.py) の `asdw-web` / `adfdv` 定義）、生成ワークフローのファイル名（[.github/prompts/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md](.github/prompts/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md) / [.github/prompts/Dev-Dataflow-FunctionsDeploy.prompt.md](.github/prompts/Dev-Dataflow-FunctionsDeploy.prompt.md)）、`--create-pr` が自動マージしないこと（[users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md)）を確認。
- 追加リンクの相対パス整合を確認（新規ファイルは `users-guide/` 直下、各ガイドからのリンクは `./local-cicd-enablement.md`）。
- ドキュメントのみの変更でありコード変更なし。

<!-- validation-confirmed -->

### Fixed — GUI テストが実リポジトリ直下に `work/run/<run-id>/` を量産する問題（テスト隔離不全）

**概要**: GUI テストの実行ごとに、実リポジトリ直下の `work/run/<run-id>/`（中身は空の `gui-logs/log-0001.log` のみ）が大量に作成される問題を修正した。原因は GUI テストが `MainWindow()` を作業ディレクトリ隔離なしで構築していたこと。`MainWindow.__init__` は `GuiSessionWorkdir.create(repo_root or Path.cwd())` で `work/run/<run-id>/` を採番・mkdir し、`WorkbenchPage` のログ初期化が直後に `gui-logs/log-0001.log` を touch するため、`repo_root` 未指定（=`Path.cwd()`＝実リポジトリ）のテストが実行のたびに実リポジトリを汚染していた。一部の `_make_main_window` ヘルパーは `MainWindow()` 構築の**後**に `win._repo_root = str(tmp_path)` を代入していたが、`create()` は `__init__` 内で既に実行済みのため隔離が手遅れになっていた。本番の GUI 経路（1 セッション=1 run-id）は元から正常で、本修正はテストコードのみ（本番コード無変更）。

- **Tests** ([hve/gui/tests/test_main_window_autopilot_app_id_picker.py](hve/gui/tests/test_main_window_autopilot_app_id_picker.py), [hve/gui/tests/test_main_window_pre_phase_followup.py](hve/gui/tests/test_main_window_pre_phase_followup.py)): `_make_main_window` を構築後の `win._repo_root = str(tmp_path)` 代入から `MainWindow(repo_root=tmp_path)`（構築時隔離）へ変更。型も本番契約（`repo_root: Optional[Path]`）に一致。
- **Tests** ([hve/gui/tests/test_main_window_dock_integration.py](hve/gui/tests/test_main_window_dock_integration.py)): `main_window` フィクスチャに `tmp_path` 引数を追加し `MainWindow(repo_root=tmp_path)` で隔離。
- **Tests** ([hve/gui/tests/test_main_window_resize.py](hve/gui/tests/test_main_window_resize.py)): `_make_window` に `tmp_path` を渡して `MainWindow(repo_root=tmp_path)` で隔離し、2 つの呼び出し元（`test_main_window_minimum_width_is_at_most_threshold` / `test_persist_window_width_writes_settings`）を更新。
- **Tests** ([hve/tests/test_gui_pages.py](hve/tests/test_gui_pages.py)): `_GuiTestBase.setUp` を新設し、`GuiSessionWorkdir.create` をテストごとの一時ディレクトリへリダイレクトする patch を適用（`addCleanup` で解除）。一時ディレクトリは即時削除せず OS の `%TEMP%` クリーンアップへ委ねる（pytest の `tmp_path` と同様）。`MainWindow` が `gui-logs` を `QFileSystemWatcher` で監視するため、テスト終了時に即時 rmtree すると監視中ディレクトリ消滅で Qt が stderr 警告を出すのを避ける。

**検証**:

- 修正 5 ファイルの統合実行 `python -m pytest hve/gui/tests/test_main_window_autopilot_app_id_picker.py hve/gui/tests/test_main_window_pre_phase_followup.py hve/gui/tests/test_main_window_dock_integration.py hve/gui/tests/test_main_window_resize.py hve/tests/test_gui_pages.py -q` → **64 passed**。
- 各テスト実行の前後で `work/run/` のディレクトリ数を比較し **DELTA=0**（実リポジトリへの新規ディレクトリ作成ゼロ）を確認。修正前は 1 テストファイルごとに複数ディレクトリが増加していた。
- `QFileSystemWatcher` stderr 警告件数 **WATCHER_WARN=0**（`test_gui_pages.py` の一時ディレクトリ即時削除版で 2 件出ていた警告が、削除遅延化で解消）。

<!-- validation-confirmed -->

### Changed — GUI 統計情報「今回の実行履歴」の AI Credit 列を Step 単独消費分のみ表示に変更

**概要**: GUI「統計情報」ウィンドウ →「今回の実行履歴」タブの AI Credit 列で、Step 子行の表示を従来の `累積 (+差分)` 形式（例 `510.3437 AIU (+451.4413)`）から、**その Step 単独の消費分（直前 Step 完了からの差分）のみ**（例 `451.4413 AIU`）へ変更した。累計表示が各行で重複し読みにくいというフィードバックに対応する。Workflow 親行（累積合計）は従来どおり不変。差分の合算は親行の累積合計と一致する（例 `58.9024 + 451.4413 = 510.3437`）。並列実行時は差分に他 Step の消費分が混ざり得るため、厳密な単独消費量とは一致しない旨を凡例・docstring・ツールチップに明記して留保する。

- **GUI** ([hve/gui/stats_history_view.py](hve/gui/stats_history_view.py)): `_build_step_item` の AI Credit セル生成を 3 分岐（累積/累積+差分/`-`）から `credit_cell = _fmt_aiu(delta_nano)` の 1 行へ単純化。差分が計算不能（直前 Step 未取得・0/負値）の場合は `-`（累積値で代用しない＝捏造禁止）。AI Credit 列の数値ソートキーを累積値から差分値へ変更し表示と一致させる（親行のソートキーは累積のまま不変）。ツールチップを「累積＋差分」併記から「該当 Step の消費分（差分）のみ」へ簡素化。凡例ラベルとモジュール docstring を新仕様へ更新。差分のみ表示により未使用化した `_fmt_aiu_delta` ヘルパーを削除。CSV エクスポート（📋）は累積（`AiuTotal`）と差分（`AiuDeltaSincePrev`）を別列で維持するため不変。
- **Tests** ([hve/gui/tests/test_stats_history_view.py](hve/gui/tests/test_stats_history_view.py)): View の 4 テスト（計 8 assert）を差分のみ期待へ更新。子 Step の数値ソートテストは差分基準への変更で tie（差分 0.5 が 2 件）が生じるため、テストデータを差分一意（`s_mid` 累積 11.0＝差分 1.0）に調整し期待順序を `["s_small", "s_mid", "s_large"]` へ。`_fmt_aiu_delta` の import と専用テスト `test_fmt_aiu_delta` を削除。新規テスト `test_view_step_known_total_but_unknown_delta_shows_dash` を追加し「累積は既知でも直前 Step 未取得で差分計算不能な Step は `-`」を固定（累積で代用する旧挙動への回帰ガード）。

**検証**:

- `python -m pytest hve/gui/tests/test_stats_history_view.py -q` → **49 passed**。
- 広域回帰 `python -m pytest hve/gui/tests/` → **847 passed / 1 skipped / 1 failed**。失敗 1 件は [hve/gui/tests/test_br_generator.py](hve/gui/tests/test_br_generator.py) の `pydantic-core` バージョン不整合（`pydantic-core 2.47.0` が要求 `2.46.4` と非互換）による環境依存の事前障害で、本変更（pydantic 非依存の AI Credit 表示）とは無関係であることを当該テスト単体実行で確定。

<!-- validation-confirmed -->

### Changed — GUI Step 1「実行ステップ」の依存伝播を撤廃し各ステップ単独選択に統一

**概要**: GUI ワークフロー選択画面（Step 1）の「実行ステップ」チェックリストで、あるステップを ON/OFF すると `depends_on` を辿って前段（依存元）が自動 ON・後段（依存先）が自動 OFF される依存伝播を撤廃した。これにより前段ステップ（例: ASDW-WEB の `Step 1.x`）を OFF にしたまま、途中ステップ（例: `Step 2.1` 追加サービス）だけを選んで実行できる。従来は前段が完了済みでも途中ステップ単独選択ができず、毎回前段から実行する必要があった。挙動は CLI ウィザード（`template_engine._prompt_steps` は元々伝播なし）および ARD グループ選択（元々伝播なし）と統一される。実行レイヤー（`resolve_selected_steps` + DAG executor の非アクティブ依存 auto-skip）は元から選択ステップ単独実行に対応済みのため変更不要。選択ステップが必要とする入力ファイルの存在確認は、Step 1 [次へ] のプランレビュー（`build_step1_plan_review` が各ステップの `required_input_paths` を実測）で従来どおり per-step に行われる。

- **GUI** ([hve/gui/page_workflow_select.py](hve/gui/page_workflow_select.py)): `_WorkflowStepsGroup._on_step_toggled` から依存伝播ロジックを削除し、ARD/非 ARD を問わず「単独で ON/OFF + Cloud override 同期 + `steps_changed` emit」に統一。未使用化した `_depends_on` / `_dependents` / `_collect_transitive` / `_suppress_signals` を撤去。モジュール docstring とインラインコメントを更新。Autopilot のギャップ適用（`apply_plan_review_gaps`）は `GapSuggestion.transitive_steps`（依存閉包を独立計算）を明示 ON にするため UI 伝播に非依存で、本変更の影響を受けない。
- **Tests**: [hve/gui/tests/test_page_workflow_select_no_propagation.py](hve/gui/tests/test_page_workflow_select_no_propagation.py)（新規 2 件）で「前段 OFF が後段に波及しない」「途中ステップ ON が前段を自動 ON しない」を固定（ASDW-WEB の依存チェーン `2.1→1.3→1.2→1.1` を根拠に旧伝播なら失敗する回帰ガード）。[hve/tests/autopilot/test_plan_review_collector.py](hve/tests/autopilot/test_plan_review_collector.py)（追記 1 件）で前段非選択でも `Step 2.1` の `required_input_paths` が漏れなく列挙されることを固定。
- **Docs** ([users-guide/hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md)): Step 1 節に実行ステップの単独 ON/OFF（依存伝播なし・途中ステップから実行可）と、選択ステップの入力ファイルがプランレビューで存在確認される旨を追記。

**検証**:

- `python -m pytest hve/gui/tests/test_page_workflow_select_no_propagation.py hve/gui/tests/test_page_workflow_select_ard_defaults.py hve/gui/tests/test_page_workflow_select_step_order.py hve/gui/tests/test_page_workflow_select_autopilot.py hve/gui/tests/test_workflow_select_options_sync.py hve/gui/tests/test_workflow_requirements_banner.py hve/tests/autopilot/test_plan_review_collector.py hve/tests/autopilot/test_plan_review_gap.py` → **47 passed, 1 skipped**。
- ASDW-WEB の依存チェーン `2.1→1.3→1.2→1.1` を `workflow_registry` で実確認し、新規テストが旧伝播挙動では失敗する真の回帰ガードであることを実証。

<!-- validation-confirmed -->

### Fixed — GUI 統計情報の AI Credit が常に空表示になる問題（SDK 1.0.x フィールド改名による回帰）

**概要**: GUI「統計情報」ウィンドウの「今回の実行履歴」タブで AI Credit 列が常に `-`（未取得）表示となり、スナップショットタブの「累積 AI Credit (AIU)」も `-` のままになる回帰を修正した。根本原因は `github-copilot-sdk` 1.0.x で `AssistantUsageData` の `copilot_usage` / `quota_snapshots` が Internal 属性（`_copilot_usage` / `_quota_snapshots`、内側 quota も `_used_requests` 等）へ改名されたこと。[hve/runner.py](hve/runner.py) の `assistant.usage` ハンドラは `getattr(data, "copilot_usage"|"copilotUsage")` で抽出していたため両名とも `None` となり、`copilotUsage.totalNanoAiu`（AI Credit の直接値）と `quotaSnapshots` が一切取り出せず、`WorkbenchState.sdk_aiu_total_nano` が 0 のまま据え置かれていた。公開シリアライズ契約 `data.to_dict()` 経由で camelCase キー（`copilotUsage.totalNanoAiu` / `tokenDetails` / `quotaSnapshots`）を読むよう変更して修正した。`cost` / `model` / `apiCallId` は公開属性のままのため従来どおり `data` から直接取得する。

- **Runtime** ([hve/runner.py](hve/runner.py)): `assistant.usage` ハンドラに `usage_dict = data.to_dict()` 正規化を導入。`copilotUsage`（→ `totalNanoAiu` / `tokenDetails`）と `quotaSnapshots`（→ `usedRequests` 等）を dict キーアクセスで抽出するよう 3 ブロック（`assistant_usage` 詳細 / `usage_credit` / `quota_snapshot`）を修正。`copilotUsage` 欠落時の `unavailable_reason` 文言を、旧「Unlimited プラン」断定（実機 probe で全プラン共通の属性改名と判明）から事実ベースの「SDK assistant.usage provided no copilotUsage」へ修正（捏造排除）。
- **Tests** ([hve/tests/test_runner.py](hve/tests/test_runner.py)): `TestAssistantUsageCreditExtraction` を新設（4 件）。`to_dict()` のみで `copilotUsage` を提供し公開属性には持たない `_FakeUsageData`（getattr 依存なら未抽出になる回帰ガード）と、実 SDK `AssistantUsageData.from_dict()` 経由（`copilot` 未導入 CI では `skipUnless` で skip）で `nano_aiu` / `quota` / `token_details` の抽出を固定化。修正前は RED（3 件失敗: `nano_aiu` が `None`）、修正後 GREEN を実機で確認。

**スコープ外（オーバーエンジニアリング回避のため意図的に除外）**:

- StatsHistoryView / Footer への `mc`（multiplier cost）/「N/A」フォールバック追加: 実機 probe で当該アカウントの `totalNanoAiu` が実値（≈8.94 AIU）を返すと確定したため、表示は既存の AIU 経路で成立し追加実装は不要。
- `inter_token_latency_ms` の抽出名不一致（SDK 実属性は `inter_token_latency`、常に `None`）: AI Credit と無関係の別 pre-existing バグのため本修正に含めない。
- SDK 1.0.x で `session.disconnect()` が coroutine 化した件: AI Credit 表示とは無関係のため別タスク。

**検証**:

- 実機 probe（最小 1 ターンの実 SDK セッション）で `getattr(data,"copilot_usage")=None` かつ `data.to_dict()["copilotUsage"]["totalNanoAiu"]=8935775000.0`（≈8.94 AIU）を確認し、根本原因と修正方針を実証（probe スクリプトは使い捨てのため削除済み）。
- `.venv` の Python で `python -X utf8 -m unittest hve.tests.test_runner` → **160 passed**（既存 156 + 新規 4）。
- 回帰テストの有効性: 修正を旧 `getattr` 経路へ一時差し戻すと `TestAssistantUsageCreditExtraction` が **3 件 RED**、復元で **4 件 GREEN** を確認（RED→GREEN）。
- エンドツーエンド（runner 抽出 → `usage_credit` → `WorkbenchState` 累積 → View 表示）の既存 GUI/pricing テスト `test_workbench_logger_ai_credit.py` / `test_workbench_state_ai_credit.py` / `test_stats_history_view.py` → **93 passed**。

<!-- validation-confirmed -->

### Fixed — ASDW-WEB Step.2.2 の `deploy_ac_gate_failed`（AddServiceDeploy 成果物未生成・git/PR 脱線）を prompt/template/gate 診断で抑止

**概要**: ASDW-WEB ワークフロー Step.2.2（`Dev-Microservice-Azure-AddServiceDeploy`）が `deploy_ac_gate_failed`（`no Issue-* dirs under agent work root`）で停止した事象を調査し、HVE 側で抑止可能な要因に絞って最小修正した。停止の決定的要因は、Agent が必須成果物 `ac-verification.md` を実ファイルとして生成しないまま（`Files: 0 written`）ターンを終え、加えてローカル実行（CLI / GUI、`{completion_instruction}` が PR 提出を指示しないモード）にもかかわらず git / PR 操作（`git commit` → ブランチ → `git reset` → `gh pr create`）へ脱線したこと（git reflog はクリーンで、これら git 操作・コミットハッシュ・ブランチ・カタログ差分はいずれも実体が無く＝推論内の幻覚で未実行、最終ターンに `gh pr create` がリテラルテキストとして本文へ混入していた）。`Dev-Microservice-Azure-AddServiceDeploy` prompt には兄弟 `DataDeploy` に存在する「ac-verification.md 必達」「出力契約外成果物への脱線禁止」「同期完了済みコマンドの再取得禁止」が欠落しており、さらに §2 成果物の `ac-verification.md` 出力先が `{WORK}artifacts/...`（artifacts 配下）と、gate（`Issue-*/ac-verification.md` 直下のみ探索）・§7.2（`{WORK}ac-verification.md` 直下）とで割れていた。gate（`_run_deploy_ac_gate`）・パス解決ロジック・registry / io-contract は正常動作のため変更しない。

- **Prompt** ([.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md)): 禁止事項に「必須成果物 `ac-verification.md` 未生成での終了禁止」「出力契約外成果物（PR 用課題管理表等）の作成禁止」「同期完了済みコマンドの出力再取得禁止」「ローカル実行時の git / PR 操作禁止（§7.3 / §7.4 の PR 提出フローは GitHub Issue 起点モード限定）」を追加。あわせて §2 成果物の `ac-verification.md` パスを `{WORK}artifacts/...` から `{WORK}...`（gate 整合の `Issue-<識別子>` 直下）へ統一。
- **Template** ([.github/scripts/templates/asdw-web/step-2.2.md](.github/scripts/templates/asdw-web/step-2.2.md)): `## 出力` に run スコープの `ac-verification.md`（`Issue-<識別子>` 直下）を追加し、`{completion_instruction}` の自己完了チェック対象に含めた（`DataDeploy` step-1.3 と対称化）。
- **Runtime** ([hve/runner.py](hve/runner.py)): `_run_deploy_ac_gate` の `ac-verification.md` 未発見診断に actionable hint を追加。`no Issue-* dirs`（成果物丸ごと未生成）時は「Agent が生成しないままターン終了／git・PR 操作や推論ループへの脱線が無いか console-log を確認」、`Issue-*` 存在時は「出力先パスのドリフト確認」を付す。GREEN / 状態判定ロジックは不変。
- **Tests** ([hve/tests/test_asdw_web_addservice_deploy_contract.py](hve/tests/test_asdw_web_addservice_deploy_contract.py)): prompt 禁止事項 4 文言・step-2.2 テンプレ出力契約・ac-verification.md パスの gate 整合（artifacts 配下表記の不在）を検証する契約テストを新規追加（6 件）。
- **Tests** ([hve/tests/test_artifact_validation_deploy_gate.py](hve/tests/test_artifact_validation_deploy_gate.py)): gate 診断の両分岐（`Issue-*` 存在＝ドリフト hint / 皆無＝脱線 hint）を固定する回帰を追加（既存更新 1 件＋新規 1 件）。

**スコープ外（オーバーエンジニアリング回避のため意図的に除外）**:

- 他 deploy prompt（`DataDeploy` / `ComputeDeploy-AzureFunctions` / `UIDeploy-AzureStaticWebApps` / `AgentDeploy` / `AgenticRetrievalDeploy`）への git/PR 禁止文言の一括展開（脱線実績は AddServiceDeploy のみ。再発した Agent から個別対応）。
- 最終本文への literal tool-call 混入のランタイム検出（SDK / モデル側機序が未確定で HVE 側の安定検出可否が不明。YAGNI）。
- gate 失敗時の継続リカバリ 1 ターン（Azure 実状態不明時に AC 表の捏造を誘発しうるため）。
- Step.2.2 への `output_paths` 宣言（pre-flight 失敗時の明確な診断を `output-missing` が preempt する副作用があるため）。
- 失敗 run の Azure 残骸の自動撤去（破壊的操作・スコープ外。`az resource list -g <RG>` での手動確認に委ねる）。

**検証**:

- `.venv` の Python で `python -m pytest hve/tests/test_asdw_web_addservice_deploy_contract.py hve/tests/test_artifact_validation_deploy_gate.py -q` → 新規 6 件 + gate 回帰すべて pass。
- 回帰: `python -m pytest hve/tests/test_asdw_web_data_deploy_contract.py -q`（兄弟 DataDeploy 契約）が引き続き pass。

<!-- validation-confirmed -->

### Changed — GUI「実行中の課題」ペインの縦リサイズ追従を改善

**概要**: GUI Workbench 右下の「実行中の課題」ペインで、縦 splitter により当該エリアの高さを広げた際、見出し行は自然高さのまま維持し、下部のテキストボックスが追加領域を最大限使用するようにした。既存の親 splitter 比率や初期サイズは変更せず、UserActions 内部の固定最大高さのみを撤去して最小差分に留めた。

- **GUI** ([hve/gui/page_workbench.py](hve/gui/page_workbench.py)): `_EnhancedUserActionsPane` の `QPlainTextEdit` に設定されていた最大高さ 120px 固定を撤去し、ペイン内レイアウトで本文ビューを `stretch=1` として縦方向の追加領域を受け取るように変更。
- **Tests** ([hve/gui/tests/test_page_workbench_layout.py](hve/gui/tests/test_page_workbench_layout.py)): UserActions ペインの高さを変更したときに、見出し `QLabel` の高さが変わらず、本文 `QPlainTextEdit` の高さが増えることを検証する回帰テストを追加。

**スコープ外（オーバーエンジニアリング回避のため意図的に除外）**:

- 親 `QSplitter` の伸縮比変更（ウィンドウ全体の縦拡大時に UserActions 自体を自動拡大する仕様追加）。
- 設定項目・レイアウト抽象化・新規依存の追加。
- ログペインや CLI/Rich Workbench 側の UserActions 表示変更。

**検証**:

- `.venv` の Python で `python -m pytest hve/gui/tests/test_page_workbench_layout.py -q` → **7 passed**。
- 関連回帰: `python -m pytest hve/gui/tests/test_page_workbench_layout.py hve/tests/test_gui_pages.py -q` → **40 passed**。
- 目視相当確認: 右側縦 splitter で UserActions エリアを 120px → 240px に変更し、`pane.height` 120→240、見出し高さ 23→23、本文ビュー高さ 91→211、`maximumHeight` 16777215 を確認。
- 上記 pytest では既存の `hve/gui/fonts.py` 起因の `QFontDatabase.QFontDatabase()` deprecation warning が出るが、今回変更行ではないため本タスクでは未変更。

<!-- validation-confirmed -->

### Added — GUI「GitHub」セクションにブランチ取得機能を追加（入力簡便化・ミス削減）

**概要**: GUI 設定の「GitHub」セクション（C5）で、ベースブランチを自由入力する際の「実在しないブランチ名のタイポ → 実行時に branch not found で失敗」というミスを削減するため、GitHub API からリポジトリのブランチ一覧を取得してベースブランチ欄に候補補完（QCompleter）として反映する「ブランチ取得」ボタンを追加した。同じ 1 回の API 呼び出しがリポジトリ (owner/repo) の実在検証（404 = 誤り）も兼ねる。取得は非同期（QThread）で UI をブロックせず、結果はインライン状態ラベルに表示する。設定キー・永続化契約・CLI 引数は不変（`branch` は従来どおり QLineEdit）。

- **API** ([hve/github_api.py](hve/github_api.py)): 読み取り関数 `list_branches(repo, token, per_page=100)` を新設。`GET /repos/{owner}/{repo}/branches` を呼びブランチ名のリストを返す。`__all__` に登録。ページネーションは行わず先頭 1 ページ（最大 100 件）。
- **GUI** ([hve/gui/page_options.py](hve/gui/page_options.py)): `_C5IssuePR` に「ブランチ取得」ボタン・状態表示ラベル・`branch` 用 `QCompleter` を追加。`_on_fetch_branches_clicked()` が repo（入力欄 > `REPO` 環境変数）を解決し、未入力時は案内メッセージで早期終了、入力済みなら `QThread`（`main_window._FetchModelsThread` と同型）で `list_branches` を非同期取得。`_on_branches_fetched()` が取得結果を QCompleter へ反映し、件数 / 失敗理由 / 「見つかりません」を状態ラベルに表示する。
- **Help** ([hve/gui/help_content.py](hve/gui/help_content.py)): C5 カテゴリヘルプに「『ブランチ取得』でブランチ一覧を取得し候補表示できる」旨を追記。
- **Tests** ([hve/tests/test_github_api.py](hve/tests/test_github_api.py)): `TestListBranches` を追加（正常系・空リスト・明示 repo/token・404 伝播・非 list フォールバック・name 欠落スキップの 6 件）。
- **Tests** ([hve/gui/tests/test_github_branch_fetch.py](hve/gui/tests/test_github_branch_fetch.py)): 新規追加。取得成功時の QCompleter 反映、取得失敗時のエラー表示、空結果表示、repo 未入力時の早期案内（スレッド未起動）を検証。

**スコープ外（オーバーエンジニアリング回避のため意図的に除外）**:

- リポジトリ (owner/repo) のローカル git 自動補完（`git remote` はローカル設定であり GitHub API データではない）。repo 誤りはブランチ取得時の 404 で検出される。
- `cloud_session_repository_branch` への同機能展開（上級者 opt-in フィールドのため）。
- 100 件超のブランチ全ページ取得（候補補完に 100 件で十分・YAGNI）。
- トークン未設定の public repo 対応（`api_call` の Authorization 固定実装の改変が必要なため）。

**検証**:

- `python -m pytest hve/tests/test_github_api.py::TestListBranches hve/gui/tests/test_github_branch_fetch.py -q` → **10 passed**（`.venv` の Python で実行）。
- 回帰確認: `hve/tests/test_github_api.py`（**39 passed**）/ `hve/gui/tests/test_github_section_consolidation.py` / `hve/tests/test_gui_step2_refactor.py`（**16 passed**）/ `hve/tests/test_gui_help_content.py`（**12 passed**）。

<!-- validation-confirmed -->

### Changed — GUI 設定の GitHub / Git 関連項目を単一「GitHub」セクションへ統合

**概要**: GUI 設定画面と Step 2 オプションで GitHub / Git 関連項目が 2 箇所に分散していた問題を解消した。従来、Issue / PR 作成・リポジトリ・ベースブランチ・PR 自動 Approve & Auto-merge は「Git」セクション（C5 / `_C5IssuePR`）に、Fleet mode / Cloud Session（GitHub Copilot SDK）は「基本設定」セクション（C1 / `_C1Basic`）に置かれていた。Fleet mode / Cloud Session 関連ウィジェットを C5 へ移動し、セクションラベルを「Git」→「GitHub」に改称して 1 セクションへ集約した。設定キー名・既定値・CLI 引数マッピングは不変で、保存値の後方互換性を維持する。

- **GUI** ([hve/gui/page_options.py](hve/gui/page_options.py)): `_C1Basic` から Fleet mode (`fleet_mode_enabled`) / Cloud Session (`cloud_session_*` 9 項目) のウィジェット構築・`to_args` 反映・`_normalized_override_json` ヘルパーを `_C5IssuePR` へ移動。モデル / 並列上限 / タイムアウト / テーマ / コンソール出力レベルは C1 に残置。Step 2 のセクション見出しを `_add("C5", "Git", …)` → `"GitHub"` に変更。
- **GUI** ([hve/gui/settings_apply.py](hve/gui/settings_apply.py)): `_SECTION_FIELDS` の Fleet / Cloud Session キー 10 個を `"C1"` → `"C5"` へ移動。属性名ベースの保存・復元・自動保存経路を新しい所在に追従させた。
- **GUI** ([hve/gui/settings_window.py](hve/gui/settings_window.py)): 設定画面カテゴリツリー「連携」配下のノードラベルを `("Git", "C5")` → `("GitHub", "C5")` に変更。
- **GUI** ([hve/gui/help_content.py](hve/gui/help_content.py)): C5 カテゴリヘルプ短文を統合後の実態（Issue / PR・ベースブランチ・auto-merge・Fleet mode・Cloud Session）に合わせて更新。
- **Tests** ([hve/gui/tests/test_github_section_consolidation.py](hve/gui/tests/test_github_section_consolidation.py)): 新規追加。`_SECTION_FIELDS` のセクション割当（C5 在 / C1 不在）、ウィジェット属性の所在、設定画面ツリー / Step 2 のラベルが「GitHub」であること、C5 経由の Fleet (tri-state) / Cloud Session 値の round-trip、C1 経由で移動キーが収集されないことを検証。

**検証**:

- `python -m pytest hve/gui/tests/test_github_section_consolidation.py -v` → **7 passed**（`.venv` の Python で実行）。
- 回帰確認: `hve/gui/tests/test_section_fields_defaults_consistency.py` / `test_settings_output_controls_relayout.py` / `hve/tests/test_gui_settings_store.py` / `test_gui_help_content.py` / `test_settings_window_skills.py` / `test_gui_step2_refactor.py` / `test_gui_pages.py` → 全て passed。

<!-- validation-confirmed -->

### Fixed — ASDW-WEB Step.1.3 の再発 `deploy_ac_gate_failed`（幻覚脱線・テンプレ出力契約不足）を prompt/template 契約で抑止

**概要**: ASDW-WEB ワークフロー Step.1.3（`Dev-Microservice-Azure-DataDeploy`）が再び `deploy_ac_gate_failed` で停止した事象を調査し、HVE 側で抑止可能な要因に絞って最小修正した。今回の停止の決定的要因は、Agent が出力契約に無い「課題管理表」の作成を自己判断で開始して脱線し（指示の出所は prompt / step テンプレート / `.github` 配下のいずれにも存在せず、提示ログからも根拠が確認できない）、必須成果物 `ac-verification.md` を作成しないままターンを終了したこと。誘因として `Invalid shell ID`（同期完了済みコマンドへの出力取得ツール再呼び出し）・content exclusion によるログ不可視・出力トークン上限到達による応答破損が連鎖した。`Invalid shell ID` / content exclusion / 出力トークン上限は Copilot CLI ランタイム／プラットフォーム側の外部要因で HVE ソースに該当機構が無く直接修正できないため、HVE 側で抑止可能な「出力契約外成果物への脱線」と「同期完了済みコマンドの再読取」を prompt 禁止事項に明文化し、加えて step テンプレートの `## 出力` に必須 work 成果物を列挙して `{completion_instruction}` の自己完了チェック対象に含めた。gate（`_run_deploy_ac_gate`）・パス解決・registry / io-contract は正常動作のため変更しない。

- **Prompt** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md)): `<constraints>` 禁止事項に2項目を追加。(1) `<output_contract>` の出力先パスに無い成果物（課題管理表等）を出所が確認できない要求に基づいて作成すること（必須成果物 `work-status.md` / `ac-verification.md` の作成を優先）、(2) 同期実行で既に完了したコマンドへ出力取得ツールを再呼び出しすること（出力はコマンド実行時に取得し、再取得は背景実行コマンドに限る）。
- **Template** ([.github/scripts/templates/asdw-web/step-1.3.md](.github/scripts/templates/asdw-web/step-1.3.md)): `## 出力` に run スコープの `work-status.md` / `ac-verification.md`（`Issue-<識別子>` 規約・prompt `<output_contract>` と一致）を追加。`{completion_instruction}` の「上記の出力ファイルが全て生成されたか」確認がこれらを対象に含めるようにし、テンプレ自己完了チェックと gate 要件の齟齬を解消。
- **Tests** ([hve/tests/test_asdw_web_data_deploy_contract.py](hve/tests/test_asdw_web_data_deploy_contract.py)): 新規追加。prompt の2禁止事項の文言存在、step-1.3 テンプレ `## 出力` の work 成果物2件（run スコープパス）の列挙、および prompt `<output_contract>` と テンプレ `## 出力` の work 成果物パス一致を検証（4 関数）。

**スコープ外（オーバーエンジニアリング回避のため意図的に除外）**:

- `Invalid shell ID` / content exclusion / 出力トークン上限は Copilot CLI ランタイム／プラットフォーム側の挙動で HVE ソースに該当機構が無く直接修正不可。
- `data-registration-script.sh` のログ機密混入緩和（content exclusion 発生源の可能性が高いが、今回 fail の直接原因ではなくスクリプト精査でスコープが膨張するため別タスク）。
- `runner.py` への成果物未作成時の催促リトライ機構（SDK セッション継続を要し実装が重く、gate は既に正常動作のため不要）。
- 兄弟 deploy prompt（Compute / UI / Agent / AgenticRetrieval / AddService）への横断展開（今回 fail したのは DataDeploy のみ）。
- io-contract / registry の `outputs` への work 成果物追加（run スコープの ephemeral 成果物は cross-step deliverable ではなく gate が別途検査する設計。追加すると registry↔yaml の集合一致検証を破壊する）。

**検証**:

- `.venv` の Python で `python -m pytest hve/tests/test_asdw_web_data_deploy_contract.py` → **4 passed**。
- 影響範囲: `hve/tests/test_artifact_validation_deploy_gate.py` / `test_template_engine.py` / `test_prompt_loader.py` を併走 → **154 passed, 1 failed**。失敗は `test_template_engine.py::TestCollectParams::test_aad_collect_params_with_multiple_app_ids`（AAD ワークフローの対話入力モック未追従による既知の pre-existing 失敗。asdw-web テンプレ／DataDeploy prompt とは無関係）。
- gate / パス解決ロジック（`_run_deploy_ac_gate` / `validate_deploy_ac_verification`）は不変。

<!-- validation-confirmed -->

### Fixed — Deploy 系 Agent の phantom skill 除去・pre-flight マーカー実機構化・兄弟 prompt 横断ハードニング

**概要**: `deploy_ac_gate_failed` 是正の残作業として、(1) `Dev-Microservice-Azure-DataDeploy` プロンプトに残っていた実在しない参照 skill を除去、(2) deploy prompt が記載しながら未実装だった pre-flight 失敗マーカーを Orchestrator gate に実機構化、(3) 早期ターン終了で `ac-verification.md` を残さない潜在バグへのガードを兄弟 deploy prompt へ横断展開した。あわせて、規約パス不一致（gate `Issue-step-<id>` vs 出力 `Issue-<識別子>`）・Step.1.1 のハング/捏造・失敗 run の Azure 残骸・catalog 見出し WARNING を調査し、いずれも変更不要（既存対策済み / 意図的据え置き / 残骸なし）と確定した。

- **Prompt** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md)): `参照Skill` 一覧から実体不在の `azure-cli-deploy-scripts` / `azure-region-policy` / `azure-ac-verification` を除去（実指針 japaneast 優先・prep/create スクリプト・AC 表はインライン残存を確認）。残存は実在する `github-actions-cicd` / `app-scope-resolution` のみ。
- **Runtime** ([hve/runner.py](hve/runner.py)): `_run_deploy_ac_gate` に completion-report.md の pre-flight 失敗マーカー（`<!-- fatal: pre-flight-failed: {理由} -->`）検出を追加。ac-verification.md 不在判定より先に明確な理由で fail させる。未置換プレースホルダ `{理由}` の引用は誤検出しないよう除外。
- **Prompts**（兄弟 deploy 5本: [ComputeDeploy-AzureFunctions](.github/prompts/Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.prompt.md) / [UIDeploy-AzureStaticWebApps](.github/prompts/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md) / [AddServiceDeploy](.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md) / [AgentDeploy](.github/prompts/Dev-Microservice-Azure-AgentDeploy.prompt.md) / [AgenticRetrievalDeploy](.github/prompts/Dev-Microservice-Azure-AgenticRetrievalDeploy.prompt.md)）: 禁止事項に「`ac-verification.md` を作成しないままターンを終えない（ブロッカー/タイムアウト時も未達 AC を `❌` で記録して必ず作成）」を追加し、gate 強制とプロンプト指示を整合。
- **Tests** ([hve/tests/test_artifact_validation_deploy_gate.py](hve/tests/test_artifact_validation_deploy_gate.py)): pre-flight マーカー検出・マーカー無しフォールスルー・プレースホルダ無視の 3 回帰テストを追加。

**調査のみ・変更なし（disposition）**:

- **phantom skill 残り3件**（`azure-cli-deploy-scripts` / `azure-region-policy` / `azure-ac-verification`）: routing 表・ADR-0001・他 deploy prompt（AddServiceDeploy 等は `§1.2` / `§3.2` 等の節参照）で「正準/新設予定」として一貫参照されており、除去には skill 新設か大規模インライン書き換えの設計判断が必要なため別タスク。DataDeploy のみ（実体がインライン済みで情報損失なし）対応。
- **gate 規約パス不一致**: `work-artifacts-layout` が `Issue-<識別子>` の可変性（APP-ID / root-issue 番号等）を規定し、CHANGELOG でも意図的据え置き。glob `Issue-*` フォールバックが機能的にブリッジ（実証済み）のため変更なし。
- **catalog 見出し WARNING**（`## 2. Architecture Selection Summary`）: 生成元 [Arch-ArchitectureCandidateAnalyzer.prompt.md](.github/prompts/Arch-ArchitectureCandidateAnalyzer.prompt.md) に canonical 見出し要求が既に存在。当該カタログは生成物で手修正は再生成で失われるため変更なし（パーサ tolerance で機能正常・警告は表示のみ）。
- **Step.1.1 のハング/捏造/出力トークン上限**（run `20260611T001618-7b784b`）: tool 中断→モデルの結果誤認→捏造→`out=32000` 退行→出力破損の連鎖を特定。初因は未確定で修正は投機的のため調査に留める。
- **失敗 run の Azure 残骸**: RG `dahatake-membership` 不在・サブスク横断 `app009` 名リソース 0 件を読み取り専用確認し、残骸なし・対応不要を確定。

**検証**:

- `python -m pytest hve/tests/test_artifact_validation_deploy_gate.py -q` → **24 passed**（既存 21 + pre-flight 検出/フォールスルー/プレースホルダ無視の 3）。
- 関連広域: `test_app_arch_filter` / `test_prompt_loader` / `test_workflow_registry` / `test_work_path_regression` → **166 passed**（`hve/runner` import 健全性を含む）。`hve/tests` 全体は無関係なハング系テストで未完（本変更スコープ外）。
- `azure-cosmosdb` 含む phantom 4 件が DataDeploy から消えたこと・Cosmos 件数取得のインライン指示残存を grep 確認。本 checkout は `.venv` 不在のためシステム Python 3.14 を使用。

<!-- validation-confirmed -->

### Fixed — ASDW-WEB `verify-data-resources.sh` に ACI フォールバックを追加し Step.1.3 の構造的 GREEN 不可を解消

**概要**: ASDW-WEB ワークフロー Step.1.3（`Dev-Microservice-Azure-DataDeploy`）が再び `deploy_ac_gate_failed` で失敗した事象の根本誘因を是正。誘因は、`verify-data-resources.sh` の PostgreSQL 件数検証（C1/C2）が **psql によるローカル 5432 直接接続のみ**を前提とし、`data-registration-script.sh` の `register_via_aci` が持つ **ACI 経由フォールバックを欠いていた**こと。このため企業 NW の 5432 egress ブロック / psql 不在のローカル環境では register が成功しても verify は構造的に GREEN 不能となり、Agent が「GREEN 不可能」と誤認して手動 psql 導入・接続リトライに約 99 分を浪費し、必須成果物 `ac-verification.md` を未作成のままターンを終了して fail 降格していた。

- **Script** ([src/infra/azure/verify-data-resources.sh](src/infra/azure/verify-data-resources.sh)): C1/C2 を「5432 直接接続（psql）優先 → 到達不可 / psql 不在時は ACI（`postgres:16-alpine`）経由フォールバック」に変更（`register_via_aci` と対称）。一時 ACI（`aci-pgverify-<suffix>`）は読み取り専用 SELECT のみ実行し即削除。検証対象データストア・そのデータ・firewall 規則は変更しない（読み取り専用を維持）。トークンは `--secure-environment-variables` で渡しログ非出力。
- **Prompt** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md)): 生成する検証スクリプトに ACI フォールバックを含める指示を §3 / §5.3 / §8 へ追加。§6 禁止事項を「Agent 自身のデータストア プロビジョニング禁止」と「件数取得用一時 ACI 作成→即削除は許容」に明確化し、追加指示との矛盾を解消。
- **Prompt** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md)): ステップ4.5 に「ACI フォールバックによりローカル/制約環境でも GREEN 到達可能。5432 不通で GREEN 不可能と独断せず経路選択はスクリプトに委ねる」を追記。成果物作成必須化・禁止事項に「リソース作成・データ登録が確認済みなら verify GREEN 未達でもブロッカー理由を記録し速やかにターンを終える（同一検証の長時間リトライ・手動 psql 導入の試行錯誤でターンを浪費しない）」を追記。

**検証**:

- `bash -n src/infra/azure/verify-data-resources.sh` → exit 0（パース成功）。
- プロンプト3ファイルの追記文言・§6 矛盾解消・`register_via_aci` との対称性を `read_file` / `grep` で確認。

<!-- validation-confirmed -->

### Fixed — ASDW-WEB Step.1.3 の `deploy_ac_gate_failed`（ac-verification.md 未生成）の是正

**概要**: ASDW-WEB ワークフローの Step.1.3（`Dev-Microservice-Azure-DataDeploy`）が `❌ ac-verification.md not found` → `[hve:fatal] deploy_ac_gate_failed` で失敗した事象を是正。根本原因は、Agent が長時間の `create-azure-data-resources.sh`（PostgreSQL→Cosmos→Storage）を**背景実行したまま「完了通知を待ちます」というツール要求のない最終応答でメインタスクのターンを早期終了**し、必須成果物 `ac-verification.md` を作成しなかったこと（プロンプトはステップ4.5 GREEN / `ac-verification.md` 作成を必須化済みだったが、そこへ到達する前に終了）。あわせて Step.1.2 で発生した `Skill not found: azure-cosmosdb` と、gate の not-found 診断が誤解を招く問題を是正。

- **Prompt** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md)): ステップ3 に実行規律を追加（`create` は前景ブロッキング実行を推奨、やむを得ず背景実行する場合も完了通知を待つ、`Start-Sleep` 手動ポーリング禁止、完了前にステップ4以降を飛ばしてターンを終えない）。ステップ4.5 の後に「成果物作成の必須化（ターン終了前）」を追加し、GREEN 未達（ブロッカー・タイムアウト・権限不足）でも `work-status.md` / `ac-verification.md` を必ず作成（AC-1=`❌`＋理由）と明記。`<constraints>` 禁止事項に「`work-status.md` / `ac-verification.md` 未作成でターンを終える」「`create` 背景実行＋`Start-Sleep` ポーリング」を追加。実在しない `azure-cosmosdb` Skill 参照（`参照Skill` / 必須セキュリティ要件）を削除し、Cosmos 件数取得・登録の方法（SDK + `DefaultAzureCredential`、Bearer token curl 禁止）はインラインで保持。
- **Prompt** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md)): `## Agent 固有の Skills 依存` から実在しない `azure-cosmosdb` を削除し、生成する検証スクリプトの Cosmos 件数取得方法（SDK + `DefaultAzureCredential`、Bearer token curl 禁止）はインラインで保持。
- **Runtime** ([hve/runner.py](hve/runner.py)): `_run_deploy_ac_gate` の `ac-verification.md` 未発見時の診断を改善。規約パス（`Issue-step-<id>`）と glob フォールバック（`Issue-*/ac-verification.md`）の双方を探索した事実、および既存の `Issue-*` ディレクトリ（上限5件）を診断に含めることで「Agent が規約パスに書いた」という誤解を解消。GREEN / 状態判定ロジック（`validate_deploy_ac_verification`）は不変。
- **Tests** ([hve/tests/test_artifact_validation_deploy_gate.py](hve/tests/test_artifact_validation_deploy_gate.py)): Agent が `Issue-0/` に出力し gate が `Issue-step-1-3` を探す実バグ状況を再現し、診断メッセージが探索経路と既存 `Issue-0` を含むことを検証する回帰テストを追加。

**スコープ / 残課題**:

- `Skill not found` の是正は実害が出た `azure-cosmosdb`（routing 表・ADR にも不在の純 phantom）のみに限定。`azure-cli-deploy-scripts` / `azure-region-policy` / `azure-ac-verification` は（同様に SKILL.md 実体は不在だが）routing 表・ADR-0001・他 deploy prompt 全体で「正準 / 新設予定」として一貫参照されており、本 2 ファイルからのみ除去すると横断不整合を生むため据え置き（系統的解消は別タスク）。
- プロンプト強化は best-effort であり、Agent の早期ターン終了を完全には強制できない（旧版でも GREEN / `ac-verification.md` は必須化済みだった）。再発時は冪等な `create` の手動再実行でリカバリ。
- ステップ0 Pre-flight 失敗時の `<!-- fatal: pre-flight-failed -->` マーカーは現状どの Python コードもパースしておらず実機構がない（既存条件・本タスクのスコープ外）。
- 同種の早期ターン終了は兄弟 deploy prompt（Compute / UI / Agent / AgenticRetrieval / AddService）にも潜在。横断展開は別タスク。
- gate の規約パス（`Issue-step-<id>`）と prompt の出力先（`Issue-<識別子>`、実 run では `Issue-0`）の不一致は既知・意図的据え置き。T3 は glob フォールバックの事実を可視化するのみ。
- Step.1.1 のツール結果配送ハング・捏造・出力トークン上限到達（run `20260611T001618-7b784b`）は別途調査。

**検証**:

- `python -m pytest hve/tests/test_artifact_validation_deploy_gate.py -q` → **21 passed**（既存 19 + 診断メッセージ回帰 1 + glob フォールバック成功経路 1）。本 checkout は `.venv` 不在のためシステム Python 3.14 を使用。
- `azure-cosmosdb` 参照が両プロンプトから消えたこと、Cosmos 件数取得のインライン指示が残存することを grep で確認。

<!-- validation-confirmed -->

### Changed — ASDW-WEB データコンテナを完全な TDD（RED/GREEN）化

**概要**: ASDW-WEB ワークフローのデータコンテナ（コンテナ1）に TDD RED フェーズが欠落していた問題を解消した。新規 Custom Agent `Dev-Microservice-Azure-DataTestCoding`（Step.1.2 / TDD RED）を新設し、データストアの検証スクリプト `src/infra/azure/verify-data-resources.sh` を生成する責務を分離した。既存の `Dev-Microservice-Azure-DataDeploy` は Step.1.2 から Step.1.3 へ再採番し、RED 確認（旧ステップ0.5）と検証スクリプト生成を除去して TDD GREEN フェーズ（生成済みスクリプトを実行して PASS させる）に純化した。これにより ASDW-WEB の全コンテナが TDD RED/GREEN を備える。データコンテナの実ステップは 2 → 3、ASDW-WEB 全体の実ステップは 17 → 18 となった。

- **Prompts** ([.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md](.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md)): 新規作成（TDD RED）。`docs/azure/azure-services-data.md` から各データストアのリソース存在 / `provisioningState` / データ件数を検証する `verify-data-resources.sh` を生成。スクリプト生成をもって成功とし、リソース未作成での実行失敗（RED）は `ac-verification.md` に記録するのみでステップ成否条件にしない。リソース作成・データ登録は行わない。
- **Prompts** ([.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md](.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md)): RED（旧ステップ0.5）を除去し GREEN に純化。`verify-data-resources.sh` を必須入力（Step.1.2 生成物）として参照し、本 Agent では生成しない。ステップ4.5 GREEN で当該スクリプトを実行し全 `[OK]`（GREEN）を確認。
- **Registry** ([hve/workflow_registry.py](hve/workflow_registry.py)): ASDW-WEB に StepDef `1.2`（DataTestCoding、depends_on=`1.1`、output `verify-data-resources.sh`）を新設。旧 `1.2`（DataDeploy）を `1.3`（depends_on=`1.2`、verify を required 入力に追加）へ再採番。Step `2.1`（AddServiceDesign）の depends_on を `1.2` → `1.3` に更新。
- **io-contracts**: [Dev-Microservice-Azure-DataTestCoding--asdw-web--1.2.yaml](.github/io-contracts/Dev-Microservice-Azure-DataTestCoding--asdw-web--1.2.yaml) を新規作成、`Dev-Microservice-Azure-DataDeploy--asdw-web--1.2.yaml` を `--1.3.yaml` へリネーム（`verify-data-resources.sh` を producer `DataTestCoding--asdw-web--1.2` の入力として追加）、[Dev-Microservice-Azure-ComputeDesign--asdw-web--3.1.yaml](.github/io-contracts/Dev-Microservice-Azure-ComputeDesign--asdw-web--3.1.yaml) の `service-catalog.md` producer を `1.2` → `1.3` に更新。
- **Templates**: `.github/scripts/templates/asdw-web/step-1.2.md` を新規作成（DataTestCoding RED）、旧 `step-1.2.md` を `step-1.3.md` へリネームし GREEN フローに更新（テスト仕様書生成・検証スクリプト生成・RED 確認を除去）。
- **Docs** ([users-guide/05-app-dev-microservice-azure.md](users-guide/05-app-dev-microservice-azure.md), [.github/ISSUE_TEMPLATE/web-app-dev.yml](.github/ISSUE_TEMPLATE/web-app-dev.yml)): データコンテナの依存グラフ・ステップ表・手動実行ガイド・動作確認手順を `1.1 → 1.2 (RED) → 1.3 (GREEN)` に更新。Issue Template にデータ RED が test-spec を介さず `azure-services-data.md` から直接導出する旨を追記。
- **Tests** ([hve/tests/test_workflow_registry.py](hve/tests/test_workflow_registry.py)): ASDW-WEB の期待ステップ数を 22 → 23（総数）/ 17 → 18（非コンテナ）に更新し、データコンテナ DAG 連鎖（`1.1 → 1.2 → 1.3`）の検証を追加。

**検証**:

- `.venv\Scripts\python.exe -m pytest hve/tests/test_workflow_registry.py -q` → **108 passed**
- `.venv\Scripts\python.exe -m pytest hve/tests/test_dag_parity.py hve/tests/test_artifact_validation_deploy_gate.py hve/tests/test_phase8_s4_reinforcement.py hve/tests/test_template_engine_agentic.py -q` → **81 passed, 2 xfailed**（xfail は dag parity の旧 bash registry 比較で既存のソフトスキップ）
- `.venv\Scripts\python.exe -m pytest hve/gui/tests/test_autopilot_planner.py hve/tests/test_workflow_registry.py hve/tests/test_app_arch_filter.py -q` → **159 passed**
- `.venv\Scripts\python.exe .github/scripts/validate-io-contract.py`: 新規/変更した io-contract（`asdw-web/1.2`・`asdw-web/1.3`・`DataTestCoding`・`verify-data-resources`）にエラーゼロ（集合一致・producer 整合）。既存の baseline エラー（未変更ワークフロー横断）は OUT-OF-SYNC notice どおりで本変更は新規エラーを増やさない。

<!-- validation-confirmed -->

### Fixed — HVE CLI/GUI の work 作業ファイル入出力を `work/run/<run-id>/` へ統一

**概要**: `hve` の CLI / GUI 実行で確認済みの作業ファイル経路について、run スコープ外の `work/` を使う箇所を整理し、対象経路の既定を `work/run/<run-id>/` 配下へ統一した。CLI Rich Workbench の UserActions / TaskTree レポートは `resolve_work_root()` を既定出力先として使用し、Deploy AC gate は legacy `work/` を読まず run スコープ配下のみを検証する。あわせて、実行対象 Custom Agent / fan-out prompt と関連 Skill に残っていた bare `work/<Agent>/...` / `work/{run_id}/...` 指示を `work/run/<run-id>/...` へ修正し、prompt / workflow 定義の回帰テストを追加した。

- **Runtime** ([hve/workbench/report.py](hve/workbench/report.py)): `save_useractions_report()` / `save_tasktree_report()` の未指定 `base_dir` を `work/` 直下ではなく `resolve_work_root()` に変更。明示 `base_dir` 指定時の互換性は維持。
- **Runtime** ([hve/runner.py](hve/runner.py)): Deploy 系 Agent の `ac-verification.md` 探索から legacy `Path("work")` fallback を削除し、`HVE_WORK_ROOT` または `work/run/<run-id>/` 配下のみを対象化。
- **Prompts / Skills**: `.github/prompts/Arch-ApplicationAnalytics.prompt.md` / `Arch-ARD-BusinessAnalysis-{Targeted,Untargeted}.prompt.md` / `Arch-ARD-UseCaseCatalog.prompt.md` / `Arch-TDD-TestSpec.prompt.md` / `hve/prompt/fanout/ard/_common.md` と関連 Skill の作業ディレクトリ指示を `work/run/<run-id>/...` へ統一。
- **Tests**: `hve/tests/test_workbench_report_run_scope.py` と `hve/tests/test_work_path_regression.py` を追加し、`hve/tests/test_artifact_validation_deploy_gate.py` に Deploy AC gate が legacy `work/` を読まず run スコープ配下を読む回帰テストを追加。
- **入力側ルール（cross-step read 禁止）**: 標準ワークフロー Step が他 Step の `work/run/<run-id>/...` 配下の作業成果物（`plan.md` / `contracts/` / `artifacts/` / `completion-report.md` 等）を入力として読む経路を禁止し、Step 間受け渡しを `docs/`（テンプレート `## 入力`）経由に限定。[.github/copilot-instructions.md](.github/copilot-instructions.md) §0 に絶対ルールを追加、[hve/template_engine.py](hve/template_engine.py) `_build_qa_review_context_section` の「前 Step 成果物」参照先を `docs/` のみに明確化（`{additional_section}` 経由で各 Step に注入）、[.github/skills/work-artifacts-layout/SKILL.md](.github/skills/work-artifacts-layout/SKILL.md) に根拠サブセクションを追加。CLI/GUI（Python）と Cloud（GitHub Actions）の整合のため、reusable workflow 9 本（`auto-app-dev-microservice-web` / `auto-app-detail-design-web` / `auto-app-selection` / `auto-ai-agent-design` / `auto-ai-agent-dev` / `auto-app-documentation` / `auto-dataflow-dev` / `auto-dataflow-design` / `auto-knowledge-management`）の `QA_REVIEW_SECTION` と `auto-aqod.yml` の同等セクションにも同一の明確化を反映。SPLIT / Fleet の `dependency_completion_reports` 経由参照は従来どおり許可。`Issue-<識別子>` 命名規約と `hve/runner.py` の ac gate glob は予防的変更を避けて据え置き。実 run `20260610T034758-49d9df` で Step 2.2 が他 Step の `work/run` を参照し `Path does not exist` で失敗していた事象を抑止する。CLI/GUI 側と Cloud 側の文言ドリフト再発防止として、[hve/tests/test_issue_template_qa_parity.py](hve/tests/test_issue_template_qa_parity.py) に全10ワークフローの QA セクションが cross-step 読取り禁止文を含むことを検査する `test_workflow_qa_sections_prohibit_cross_step_work_run_read` を追加。

**検証**:

- `.venv\Scripts\python.exe -m pytest hve/tests/test_workbench_report_run_scope.py hve/tests/test_run_unified_workdir.py -q` → **11 passed**
- `.venv\Scripts\python.exe -m pytest hve/tests/test_artifact_validation_deploy_gate.py hve/tests/test_workbench_report_run_scope.py -q` → **23 passed**
- `.venv\Scripts\python.exe -m pytest hve/tests/test_work_path_regression.py -q` → **2 passed**
- `.venv\Scripts\python.exe -m pytest hve/tests/test_template_engine.py::TestQaReviewContextSection hve/tests/test_template_engine.py::TestRenderTemplate -q` → **21 passed**（cross-step read 禁止ルールの単体＋注入検証）
- `.venv\Scripts\python.exe -m pytest hve/tests/test_issue_template_qa_parity.py::TestWorkflowAutoQaParity::test_workflow_qa_sections_prohibit_cross_step_work_run_read -q` → **1 passed, 10 subtests passed**（全10ワークフロー YAML の QA セクションに cross-step read 禁止文が存在することを検査＝Python↔Cloud ドリフト防止）

<!-- validation-confirmed -->

### Fixed — GUI テスト群を現行仕様へ追従させ、テストハング・順序依存・実装登録漏れを解消（GUI テスト全緑化）

**概要**: `hve` GUI（`hve.gui`）のテスト群に対し、(1) 実装の仕様変更にテストが追従していない失敗、(2) モーダルダイアログ未モックによる pytest プロセス全体のハング、(3) テスト間の状態汚染（順序依存）、(4) テストが正しく検出していた実装側の登録漏れ、を実機 pytest（PySide6 6.11.1 / `QT_QPA_PLATFORM=offscreen`）と実コード突合に基づき網羅的に修正した。`hve/gui/tests`（`test_mdq_strategy_features.py` を除く）は **823 passed / 0 failed**、`hve/tests/test_gui_pages.py` は **33 passed / 0 failed** を確認。修正前は GUI 本体一括で 44 failed＋モーダル起因ハング、`hve/tests` 系で 16 failed＋ハングだった。捏造を避け、各修正は実装の現仕様（実コード行）を根拠に行った。

- **実装修正（テストが検出した登録漏れの補完）**:
  - [hve/gui/help_content.py](hve/gui/help_content.py): カテゴリヘルプ辞書 `_CATEGORY_HELP` に欠落していた `"C6"`（出力制御）エントリを追加。実在カテゴリ（[hve/gui/page_options.py](hve/gui/page_options.py) `_add("C6","出力制御",...)`）に対しヘルプのみ欠落しており、`test_category_help_all_16_present` が正しく検出していた。
  - [hve/gui/settings_store.py](hve/gui/settings_store.py): `defaults()["options"]` に `self_improve_max_iterations`(=3) / `self_improve_target_scope`(="") / `self_improve_goal`(="") を追加。3 キーは [hve/gui/settings_apply.py](hve/gui/settings_apply.py) `_SECTION_FIELDS["C3"]` に登録済・ウィジェットも実在するが `defaults()` に欠落しており、`_coerce(default=None)` フォールバックで型情報が失われる不整合を `test_section_fields_keys_exist_in_defaults` が検出していた。
- **テスト追従修正（実装が正・テストが旧仕様）**:
  - ログ行プレフィックス（`[WF] [step]`）付与（[hve/gui/workbench_state.py](hve/gui/workbench_state.py) `format_log_prefix`）に [hve/gui/tests/test_page_workbench_append_log.py](hve/gui/tests/test_page_workbench_append_log.py) / [test_workbench_state_workflows.py](hve/gui/tests/test_workbench_state_workflows.py) を追従。
  - テーマ既定値 `dark` → `light`（[hve/gui/settings_store.py](hve/gui/settings_store.py)）に [hve/tests/test_gui_settings_store.py](hve/tests/test_gui_settings_store.py) を追従（テスト名も `_is_light` へ）。
  - mdq strategy 数 4 → 6（`pageindex` / `graphrag` 追加、[mdq/strategies.py](mdq/strategies.py)）に [hve/gui/tests/test_mdq_strategy_features.py](hve/gui/tests/test_mdq_strategy_features.py) を追従。
  - ARD ステップ採番のグループ展開を registry SSOT（[hve/workflow_registry.py](hve/workflow_registry.py) `_WORKFLOW_GROUP_MAPS["ard"]`：グループ "4" → `["3.1","3.2","3.3"]`）に [hve/gui/tests/test_main_window_step_selection_autopilot.py](hve/gui/tests/test_main_window_step_selection_autopilot.py) / [test_main_window_step_selection_plan.py](hve/gui/tests/test_main_window_step_selection_plan.py) を追従。
  - 作業状況ウィジェットの `DagStatusWidget` 移行（QTreeWidget ベースの旧 `_tree` 廃止 → `_entries` / `node_selected` シグナル）に [hve/gui/tests/test_page_workbench_autopilot_tree.py](hve/gui/tests/test_page_workbench_autopilot_tree.py) / [test_page_workbench_layout.py](hve/gui/tests/test_page_workbench_layout.py) を追従。
  - `GuiSessionWorkdir.env_overrides()` の `HVE_RUN_ID_TZ` 条件付きキーに対し、[hve/gui/tests/test_session_workdir.py](hve/gui/tests/test_session_workdir.py) を `monkeypatch.delenv` で決定的に基本契約（3 キー）を検証する形へ修正（実行環境の env 残存によるフレーク解消）。
  - `REQUIREMENT_TABLE` への `autopilot` 仮想ワークフロー追加・`adfd` ステップ採番（6.1/6.2）に [hve/gui/tests/test_workflow_step_requirements.py](hve/gui/tests/test_workflow_step_requirements.py) を追従。
  - `MainWindow._start_autopilot` の `_session_workdir` / `_status_banner` 参照に [hve/gui/tests/test_start_autopilot_chain_branch.py](hve/gui/tests/test_start_autopilot_chain_branch.py) のモック構築を追従。
  - ウィンドウタイトル「HVE GUI Orchestrator」→「HVE Workbench」、`OptionsPage` 画面内タイトル（`_title_label`）廃止、`_LabeledField` の description が行内ラベル → 入力ウィジェットのツールチップへ統合、に [hve/tests/test_gui_pages.py](hve/tests/test_gui_pages.py) を追従。
- **モーダルハング修正（CI 破壊リスク最大）**:
  - [hve/gui/tests/test_main_window_pre_phase_followup.py](hve/gui/tests/test_main_window_pre_phase_followup.py): `build_plan` の patch 対象を実体経路 `hve.gui.autopilot.planner.build_plan`（re-export 先）へ是正。旧 patch（`hve.autopilot.planner.build_plan`）が無効で実 `build_plan` が空プラン → `QMessageBox.warning` モーダルでハングしていた。
  - [hve/tests/test_gui_pages.py](hve/tests/test_gui_pages.py): 2 ペイン再設計で「次へ」=実行起動となったため、`_run_step1_unified_precheck` の `dlg.exec()`（統合 precheck モーダル）/ 入力検証 / 子プロセス起動を patch し、ナビゲーション遷移のみ検証する形へ修正（`test_navigation_*` / `test_on_stop_all_clicked_*`）。
- **テスト独立性（順序依存）修正**:
  - [hve/gui/tests/test_i18n.py](hve/gui/tests/test_i18n.py): `TestInstallTranslator` が `QCoreApplication.instance() is None` のとき非 GUI の `QCoreApplication` を生成し、後続 GUI テストの `QApplication` 生成を恒久ブロックして「Cannot create a QWidget without QApplication」でクラッシュ/ハングさせていた汚染源を、`QApplication.instance() or QApplication(...)` の生成へ是正。加えて `test_en_us_loads_qm_if_present` に `try/finally` で en_US 翻訳をソース言語 `ja_JP` へ戻す後始末を追加し、後続テストの日本語文言検証（例: ステータスバナー「待機」）への翻訳汚染を防止。
  - [hve/gui/tests/test_main_window_autopilot_app_id_picker.py](hve/gui/tests/test_main_window_autopilot_app_id_picker.py): `test_returns_entries_when_all_conditions_met` が設定 `autopilot_show_app_id_picker` の実ファイル値に依存して順序汚染（先行 settings テストが `False` を残すと `None` 返し）していたため、`get_option` を ON へ明示 patch してテスト独立性を担保。

### Removed — 撤去済み機能・廃止ウィジェットに紐づく死蔵 GUI テストおよびデッドコードを削除

**概要**: 実装側で既に撤去された機能・置換済みウィジェットに対する、`pytest.skip(allow_module_level=True)` で常時スキップされるスタブや、撤去済み API/定数を参照する死蔵テストを削除し、対応する未使用デッドコードを除去した。現行仕様の回帰検知に必要なテストは保持し、削除は「撤去済み仕様の検証のみを行うテスト」に限定した（有効テストの巻き込み削除を回避）。

- **`ActivityStatusWidget` 撤去完遂**（本番は [hve/gui/page_workbench.py](hve/gui/page_workbench.py) で `DagStatusWidget` に完全移行済み・本番インスタンス化ゼロを grep で確認）:
  - [hve/gui/workbench_widgets.py](hve/gui/workbench_widgets.py): `ActivityStatusWidget` クラスおよび専用ヘルパ（`_ACTIVITY_EMOJI` / `_ACTIVITY_THEMES` / `_normalize_status` / `_fmt_elapsed` / `_PlanModeStateProxy`）を削除し、それに伴い未使用化した import（`Tuple` / `QEvent` / `QSizePolicy` / `QTreeWidget` / `QTreeWidgetItem` / `QColor` / `QFont` / `QFontMetrics` / `CopyButton` / `WordWrapDelegate` / `StepStatus`）を除去（`FooterWidget` / `WorkflowProgressWidget` / `Header2Widget` 等が使用する import は保持）。`FooterWidget` 等の依存テスト 31 件が緑であることを確認。
  - 削除した死蔵テスト: [hve/tests/test_activity_status_widget.py](hve/tests/test_activity_status_widget.py)（撤去クラスの単体テスト）、および module-level skip スタブ 4 ファイル（`test_activity_status_multi_workflow.py` / `test_activity_status_widget_timing.py` / `test_phase2_container_nest_subtask.py` / `test_workbench_multi_workflow.py`）。[hve/gui/tests/test_workbench_no_hscroll.py](hve/gui/tests/test_workbench_no_hscroll.py) の `@pytest.mark.skip` された空テストも削除。
- **precheck v2 で撤去された機能のテスト削除**（`run_step1_precheck` のシグネチャに `additional_prompts` / `use_llm_judge` / `implicit_required_paths` / `autopilot_required_artifacts` が存在しないことを [hve/autopilot/precheck_runner.py](hve/autopilot/precheck_runner.py) で確認）:
  - 削除: `test_main_window_precheck_additional_prompt.py` / `test_settings_precheck_llm_judge.py`。[hve/gui/tests/test_main_window_unified_precheck.py](hve/gui/tests/test_main_window_unified_precheck.py) は撤去引数を検証する 2 ケースを削除し、現仕様で有効な「ギャップ 0 件で Dialog skip」ケースを保持。
- **Step 2 フィールド刷新で陳腐化したテストの限定削除**:
  - [hve/tests/test_gui_step2_refactor.py](hve/tests/test_gui_step2_refactor.py): ワークフロー個別フィールドが「追加プロンプト」中心へ集約され個別フィールドが非表示化された現仕様（[hve/gui/page_options.py](hve/gui/page_options.py) `_refresh_specific_categories`）に対し、旧個別フィールド表示前提の 8 テストのみ削除。現仕様の回帰テスト（追加プロンプト常時表示・AAS 案内・depth 選択肢等）8 テストは保持。
  - [hve/tests/test_gui_pages.py](hve/tests/test_gui_pages.py): 撤去済み API（`_collect_unselected_dependencies` / `_format_missing_dependencies_message`）・撤去済み定数（`MODEL_CHOICES`、現行は `_load_model_choices()` 関数化・[hve/gui/tests/test_model_reload.py](hve/gui/tests/test_model_reload.py) でカバー）・廃止されたカテゴリ枠表示方式（ワークフロー枠移設へ変更・[hve/tests/test_gui_step2_refactor.py](hve/tests/test_gui_step2_refactor.py) でカバー）を参照する死蔵テスト 5 件を削除。

**既知の制約（本変更のスコープ外）**:
- `hve/gui/tests/test_mdq_strategy_features.py` は `graphrag` / `fastembed` 等の重依存のコールドインポートが 30〜60 秒を超えることがあり、`--timeout` 付き一括計測ではタイムアウトし得る（本修正と無関係の環境要因）。当該ファイル単体では全件 PASS する。一括計測時は `--ignore` で除外して計測した。
- 本修正は `pytest-timeout` をローカル `.venv` に導入して計測したが、リポジトリ依存（`pyproject.toml`）には追加していない。CI への恒久導入は別途判断とする。
- 残存する `ActivityStatusWidget` の文字列はコメント／docstring のみ（実害なし）。文言整理は本変更のスコープ外。

**検証**:

- `python -m pytest hve\gui\tests -p no:cacheprovider --timeout=60 --timeout-method=thread -p no:randomly --ignore=hve\gui\tests\test_mdq_strategy_features.py` → **823 passed, 1 skipped, 0 failed**（修正前 44 failed＋ハング）。`-p no:randomly` の固定順で順序依存の解消を確認。
- `python -m pytest hve\tests\test_gui_pages.py -p no:cacheprovider --timeout=45 --timeout-method=thread -p no:randomly` → **33 passed, 0 failed**（修正前はモーダルハングで計測不能＋隠れ 8 failed）。
- 削除した全テストファイルへの残存参照が 0 件であることを grep で確認。各タスク完了時に編集ファイル単体での PASS と新規失敗ゼロを確認済み。

<!-- validation-confirmed -->

### Fixed — GUI「実行中の課題」に毎ステップ出る split-fork 無効 WARN ノイズを発生源で解消

**概要**: GUI で `ASDW-WEB` 等を実行するたびに、各ステップ完了直後に「⚠️ `⏭ [<step>] legacy split-fork は無効です (split_fork_enabled=False)。…`」が「実行中の課題」ペインへ WARN として表示されていた問題を解消した。発生源は [hve/runner.py](hve/runner.py) `_maybe_run_split_fork` の `not ctx.split_fork_enabled` 分岐が `console.warning()` を使用していたこと。CLI / GUI 標準経路では `split_fork_enabled=False` が**設計どおりの正常値**（[hve/__main__.py](hve/__main__.py) で固定 `False`・[hve/orchestrator_context.py](hve/orchestrator_context.py) 既定 `False`）であり、正常状態を毎ステップ WARN 重大度で記録するのは不適切だった。`docs/` 配下は本問題と無関係（メッセージは f-string ハードコードで docs 非参照）。

- **Runtime** ([hve/runner.py](hve/runner.py)): `_maybe_run_split_fork` の無効分岐を `console.warning()` → `console.event()` に降格。直前の兄弟分岐（`ctx is None` の単独実行モード）が既に `console.event()` を使用しているのと同じ観測性レベルに揃えた。`console.event` の出力は `⚠️` プレフィックスを持たないため、GUI のログ解析 [hve/gui/workbench_logger.py](hve/gui/workbench_logger.py) `_EMOJI_WARN_PATTERN`（`⚠️` 始まり行のみ「実行中の課題」へ流す）にマッチせず、ノイズが解消する。`_record_checkpoint(step_id, "split-fork-skipped-disabled")` による Resume 観測性は維持（副作用・制御フロー・戻り値は不変）。
- **Tests** ([hve/tests/test_runner_split_fork.py](hve/tests/test_runner_split_fork.py)): 回帰テスト `test_split_fork_disabled_does_not_warn` を追加。`split_fork_enabled=False` 経路で `console.warning` が呼ばれず `console.event` が split-fork メッセージで1回呼ばれることを `unittest.mock.patch.object` で固定化。
- **Tests** ([hve/tests/test_workbench_logger_warning.py](hve/tests/test_workbench_logger_warning.py)): 本変更により runner.py が split-fork 無効を `⚠️` で出力しなくなったため、モジュール docstring の「split-fork 無効通知 (hve/runner.py, ⚠️ + ⏭)」例示を削除し、GUI パーサ単体・発生源非依存の検証である旨へ reframe。2 テスト（タイムスタンプ付き ⚠️ 抽出 / ステップ状態不変）に docstring を追加し、payload が発生源の実出力ではなくパーサ検証用サンプルであることを明記。テスト本体（パーサ挙動の検証）は不変。

**既知の制約（本変更のスコープ外）**: catalog 見出し WARNING（[hve/app_arch_filter.py](hve/app_arch_filter.py)）・dry-run 警告・`Session error` 等の真正な `⚠️` 警告は従来どおり「実行中の課題」へ表示される（0.1.1 の汎用 ⚠️ 表示機能は回帰しない）。本変更は split-fork 無効通知の重大度のみを是正する。

**検証**:

- `python -m pytest hve/tests/test_runner_split_fork.py hve/tests/test_workbench_logger_warning.py hve/tests/test_workbench_logger_emoji_errors.py hve/tests/test_workbench_logger_finding.py hve/tests/test_runner_split_required_guard.py -q` → **59 passed**
- runner 系全 7 ファイル（[hve/tests/test_runner.py](hve/tests/test_runner.py) 他）→ **230 passed**（波及なし。警告は既存の `datetime.utcnow` deprecation 等で本変更と無関係）
- 追加した回帰テストは、降格前（`console.warning`）へ戻すと `assert_not_called` が失敗する設計のため、本ノイズの再発を検知できる。

<!-- validation-confirmed -->

### Changed — Arch カタログ生成契約を厳密化し `app-arch-catalog.md` の見出し/列名揺れ（canonical WARN）の再発を生成側で防止

**概要**: GUI で `ASDW-WEB` / `AAD-WEB` / `ADFD` / `ADFDV` を実行するたびに「⚠️ WARNING: catalog の見出しが canonical (`## A) サマリ表（全APP横断）`) と異なります: `## 2. Architecture Selection Summary` を受理しました」が表示されていた。発生源は [hve/app_arch_filter.py](hve/app_arch_filter.py) `_parse_catalog` の `numbered_re` フォールバック（[hve/orchestrator.py](hve/orchestrator.py) Phase 2.5「推薦アーキテクチャ APP-ID フィルタ」が当該 4 ワークフローで `resolve_app_arch_scope` を無条件呼び出すため毎回発火）。直接原因は [docs/catalog/app-arch-catalog.md](docs/catalog/app-arch-catalog.md) の見出しが `## 2. Architecture Selection Summary`（英語・番号付き）・列名が `Primary Arch`（英語）で出力契約（[.github/skills/architecture-questionnaire/assets/output-format.md](.github/skills/architecture-questionnaire/assets/output-format.md) §7.2）に違反していたこと。当該カタログは決定論的コードではなく Arch エージェント（[.github/prompts/Arch-ArchitectureCandidateAnalyzer.prompt.md](.github/prompts/Arch-ArchitectureCandidateAnalyzer.prompt.md)）が生成する成果物のため、`docs/` の手修正は再生成で失われる。本変更は 0.1.1 のパーサ側 tolerance（`## 2.…Summary` 等を WARN 付きで受理する防御的措置）に対する **生成側の恒久対策** として、生成契約に「サマリ表見出し `## A) サマリ表（全APP横断）`(H2) と表ヘッダ `| APP-ID | APP名 | 推薦アーキテクチャ | Confidence | 入力ステータス |` の一字一句使用・英語化/番号付与/太字/語順変更の禁止・全セクション H2」を明記した。コード・パーサ挙動・出力契約の canonical 定義は変更しない（ドキュメント＝プロンプト/スペックのみの変更）。

- **生成プロンプト** ([.github/prompts/Arch-ArchitectureCandidateAnalyzer.prompt.md](.github/prompts/Arch-ArchitectureCandidateAnalyzer.prompt.md)): `<output_contract>` の「出力フォーマット」を、機械パース対象であることを明示した厳密版へ改訂。サマリ表見出し `## A) サマリ表（全APP横断）`(H2)・表ヘッダ行のリテラル指定・表セル値の装飾用太字（`**…**` / `**中**` / `**完了**`）禁止・B)〜E) を含む全セクション H2 化を要求し、実際に発生した契約違反（`## 2. Architecture Selection Summary` / `Primary Arch` / `**Webフロントエンド + クラウド**`）を禁止例として明記。B)〜E) の見出し文言はパース非依存のためリテラル強制せず（descriptive のまま）。
- **出力契約スペック** ([.github/skills/architecture-questionnaire/assets/output-format.md](.github/skills/architecture-questionnaire/assets/output-format.md)): §7.2 冒頭に同趣旨の「見出し・列名の機械パース要件（厳守）」注記を追加。本ドキュメント内の `#### A)` は §7.2 配下の階層表記であり生成ファイル側は H2 `## A)` である旨を明示。既存の `#### A)`〜`#### E)` 構造・サンプル表・入力ステータス定義は不変。

**既知の制約（本変更のスコープ外）**: 本変更は生成側の文言強化であり、(1) 既存の [docs/catalog/app-arch-catalog.md](docs/catalog/app-arch-catalog.md) は手修正しないため、Arch エージェントが canonical 形式で再生成するまで GUI の canonical WARN は継続する（0.1.1 のパーサ側 tolerance により機能は正常動作、警告は表示のみ）。(2) LLM 生成は確率的のため契約遵守を 100% 保証するものではない。(3) パーサ側の `numbered_re` / `Primary Arch` 別名による tolerance は後方互換のため撤去しない。なお [.github/skills/_evals/](.github/skills/_evals/) の eval 文言・[.github/ISSUE_TEMPLATE/](.github/ISSUE_TEMPLATE/) のワークフロー yml・[.github/skills/app-scope-resolution/SKILL.md](.github/skills/app-scope-resolution/SKILL.md) / [.github/skills/agent-common-preamble/SKILL.md](.github/skills/agent-common-preamble/SKILL.md) 本文は、確認の結果いずれも既に canonical（`## A) サマリ表（全APP横断）` / `推薦アーキテクチャ`）準拠で本変更と矛盾しないため追随更新は不要。

**検証**:

- ドキュメント（プロンプト/スペック）のみの変更でコード・テストは未改変。記述した canonical パーサ挙動が不変であることを `python -m pytest hve/tests/test_app_arch_filter.py -q` で確認 → **28 passed**。
- 生成プロンプトと output-format.md の厳密要求（A) 見出し `## A) サマリ表（全APP横断）`・列ヘッダ・全 H2）が両ファイルで一致し、B)〜E) 見出し文言を相互に矛盾なく descriptive のままとしたことを目視確認。

<!-- validation-confirmed -->

## [0.1.1] - 2026-06-09

### Changed — GUI 「実行中の課題」一覧に 汎用 ⚠️ WARNING と 成功ステップ内のテキスト指摘 を表示

**概要**: GUI Workbench の「実行中の課題」ペインが、`❌ ERROR` / `Session error` / `Sub-agent 失敗` / `✗ ツール失敗` の 4 系統しか拾わず、(1) `⚠️` で始まる汎用 WARNING（catalog 見出し不一致 [hve/app_arch_filter.py](hve/app_arch_filter.py) / split-fork 無効通知 [hve/runner.py](hve/runner.py) / dry-run 警告 等）と、(2) 成功ステップが応答本文に書く「指摘」（例: `- **status**: 成功（要修正判定）`）を一覧へ流せていなかった問題を解消した。いずれも表示専用の追加であり、ステップ状態・終了コード・中断制御は一切変更しない（タスクは継続する）。従来 `Session error` で始まる行に限定していた WARN 検知を、`⚠️` で始まる任意の警告行へ一般化した（CLI-TUI 版 [hve/console.py](hve/console.py) `warning()` が既に全警告を `append_user_action` 済みだった挙動と GUI 側を整合）。

- **GUI ルーティング** ([hve/gui/workbench_logger.py](hve/gui/workbench_logger.py)): `process_log_line` の fallback チェーンを拡張。`_EMOJI_SESSION_ERROR_PATTERN`（`Session error` 限定）を `_EMOJI_WARN_PATTERN`（`⚠️` 始まりの任意行）へ一般化し、`level="WARN"` で記録。新規 `_FINDING_PATTERN` を追加し、ラベル語（`status` / `判定` / `レビュー`）と指摘語（`要修正` / `要確認` / `FAIL` / `不整合`）の**両方**を含む行のみを `level="WARN"`・`category="指摘"` で記録（既存 `category="ツール失敗"` と同じ表示分類機構を再利用）。否定文（例: `不整合は無し`・`Critical: 0件`）はラベル語または指摘語を欠くため対象外。`add_user_action` の呼び出しのみで、制御フロー（return 構造・ステップ status）は不変。
- **Tests**: 既存 [hve/tests/test_workbench_logger_emoji_errors.py](hve/tests/test_workbench_logger_emoji_errors.py) の「`Session error` 以外の `⚠️` は無視」テストを、一般化挙動（WARN 記録）へ更新（8 件）。新規 [hve/tests/test_workbench_logger_warning.py](hve/tests/test_workbench_logger_warning.py)（4 件: catalog 見出し WARNING / split-fork 無効 / dry-run / ステップ状態不変）と [hve/tests/test_workbench_logger_finding.py](hve/tests/test_workbench_logger_finding.py)（9 件: status・判定+FAIL・判定+要確認・レビュー+不整合の肯定、Critical:0件・ラベル欠の不整合・通常見出しの否定、ステップ状態不変）を追加。

**既知の制約（本変更のスコープ外）**: 指摘検知はキーワード AND 方式のため、ラベル語と指摘語の両方を含む**否定文**（例: `レビューの結果、要確認事項はありません`）は誤って「指摘」として記録され得る（保守的設計の残存トレードオフ）。否定処理は本変更のスコープ外。また `app_arch_filter.py` の生 `print` 警告は console を経由しないため CLI-TUI 一覧には従来どおり出ない（GUI のサブプロセスログ解析経路でのみ捕捉）。`hve/gui/workbench_logger.py` の標準パス（`parse_log_line` 後）に存在する既存の型厳格性指摘（`message: Optional[str]`）は本変更の対象外で未変更。

**検証**:

- `python -m pytest hve/tests/test_workbench_logger_warning.py hve/tests/test_workbench_logger_finding.py -q` → **13 passed**
- 関連回帰（emoji_errors / tool_failed / subagent / warning / finding / console_workbench_injection）→ **47 passed**
- 実ログ形式（catalog 見出し WARNING・split-fork・`- **status**: 成功（要修正判定）`）での挙動を実データで確認し、肯定ケースは WARN 記録、否定ケース（`Critical: 0件` 等）は非記録であることを実証。

<!-- validation-confirmed -->

### Changed — GUI のローテーションログ出力先を `work/run/<run-id>/gui-logs/` に統一

**概要**: GUI（`hve/gui/page_workbench.py` の `_LogPane`）が画面ログを永続化するローテーションログファイルの出力先を、従来の `work/gui-logs/session-<timestamp>/log-NNNN.log`（`Path.cwd()` 基準・GUI セッションの `work/run/<run-id>/` 隔離を無視）から、GUI セッションの作業ディレクトリ配下 `work/run/<run-id>/gui-logs/log-NNNN.log` へ変更した。これにより同一 GUI セッションの成果物（`console-log.txt` 等）と同じ `work/run/<run-id>/` 配下にローテーションログが集約され、`work/` 直下に `gui-logs/` が散らばらなくなる。出力先は既存の `WorkbenchPage.set_session_work_root()` 注入経路（`MainWindow` が `GuiSessionWorkdir.work_root` を 1 度だけ注入）に相乗りし、`_LogPane` 構築時の cwd 直書きを廃止。未注入時（テスト等）はファイル永続化を行わない no-op とした（`console-log.txt` ダンプと同じ「未注入なら何もしない」方針に統一）。

- **GUI** ([hve/gui/page_workbench.py](hve/gui/page_workbench.py)): `_LogPane.__init__` から `_open_new_log_file()` の即時呼び出しと `_log_session_id`（および未使用化する `from datetime import datetime`）を撤去。`_LogPane` に `set_log_base_dir(run_dir)` を追加し、`run_dir/gui-logs/` を出力先として登録してから最初のログファイルを開く（`None` 注入で永続化無効化）。`_open_new_log_file()` は `_log_base_dir` 未設定時に no-op。`WorkbenchPage.set_session_work_root()` に `self._log_pane.set_log_base_dir(run_dir)` の 1 行転送を追加。
- **Tests** ([hve/gui/tests/test_console_log_dump.py](hve/gui/tests/test_console_log_dump.py)): `TestLogPaneBaseDir` を追加（5 件）。構築時に cwd 配下へ `gui-logs` を作らない／注入後に `<run_dir>/gui-logs/log-0001.log` を開く／`append_line` が gui-logs 配下へ永続化する／`None` 注入で永続化無効化／`WorkbenchPage.set_session_work_root` が gui-logs 出力先を配線する、を検証。
- **Removed**: 旧実装の名残である未追跡の空ディレクトリ群 `work/fleet/`（`work/run/` 外。現行 Fleet 実装は `work/run/<run-id>/` 配下へ出力するため不要）をローカル削除した。git 追跡対象ではなく（`git ls-files` 空・空ディレクトリのみ）コミット影響はない。

**既知の制約（本変更のスコープ外）**: `work/` 直下に残る他の出力（`work/archive/<id>.zip`＝GUI cleanup policy "archive" の退避先 / `work/dashboards/`＝CI ワークフロー生成物 / `work/gui-logs/` の旧残骸）は本変更のスコープ外で未変更。旧 `work/gui-logs/session-*/` の既存ファイルは移動・削除しない（次回以降の GUI セッションから新パスに出力される）。

**検証**:

- `python -m pytest hve/gui/tests/test_console_log_dump.py::TestLogPaneBaseDir -q` → **5 passed**
- 影響範囲の回帰（`_LogPane` / `WorkbenchPage` 構築テスト）: `test_console_log_dump.py` / `test_workbench_no_hscroll.py` / `test_autopilot_workbench_display.py` / `test_autopilot_stats_propagation.py` / `test_fatal_integration.py`（`hve/tests/test_gui_imports.py` 経由含む）/ `test_page_workbench_{fatal,artifacts,fanout_progress}.py` → 全 PASS
- 既存 failure の切り分け: `test_page_workbench_{append_log,autopilot_tree,layout}.py` の 9 件は本変更前（`git stash` で退避した baseline）でも同一に失敗するため、本変更と無関係な既存 failure であることを実証（`append_log` のプレフィックス整形期待の不一致等）。

<!-- validation-confirmed -->

### Fixed — GUI で AAD-WEB / ADFD 選択時に対象アプリケーション (APP-ID) チェックリストが表示されない問題

**概要**: GUI でワークフロー `AAD-WEB`（Web App Design）を選択しても、画面右側の [Software Engineering] に対象アプリケーション (APP-ID) チェックリストが表示されず、プレースホルダ付きの手入力欄のみが表示されていた（`ADFD` / `ADFDV` でも同症状）。真因は、カタログ生成 Sub-Agent が出力契約（[.github/skills/architecture-questionnaire/assets/output-format.md](.github/skills/architecture-questionnaire/assets/output-format.md) §7.2）に違反した [docs/catalog/app-arch-catalog.md](docs/catalog/app-arch-catalog.md) を生成していたこと。具体的には、推薦アーキテクチャ列の値が Markdown 太字マーカー付き（例: `**Webフロントエンド + クラウド**`）・列名が `推薦アーキテクチャ` ではなく `Primary Arch`・セクション見出しが `## A) サマリ表（全APP横断）` ではなく `## 2. Architecture Selection Summary`・batch 表記が規約の `データデータフロー処理`（データ2回）ではなく `データフロー処理`（データ1回）となっていた。この契約違反に対し 2 系統のパーサが異なる壊れ方をしていた（`.venv` 実行で確認）: **層1**（GUI チェックリスト web-cloud）＝位置ベースの [hve/gui/app_catalog_loader.py](hve/gui/app_catalog_loader.py) は 12 件読めるが、`**…**` 付き値を `classify_architecture` が分類できず（`None`）全件除外。**層2**（GUI チェックリスト batch）＝`**` を除去しても `データフロー処理`（1回）が分類マップ `データデータフロー処理`（2回）と不一致で除外。**層3**（autopilot / CLI の APP-ID 自動選択）＝列名・見出し厳格判定の [hve/app_arch_filter.py](hve/app_arch_filter.py) `_parse_catalog` が `Primary Arch` 列・`## 2.` 見出しを認識できず `catalog_found=False`。本修正は分類ロジックとパーサに防御的 tolerance を追加し、契約違反カタログでも正しく分類・パースできるようにした。出力契約（output-format.md）自体は変更せず、既存の loose+WARN 方式（黙認しつつ canonical 化を推奨）に揃えた。

- **分類ロジック** ([hve/app_arch_filter.py](hve/app_arch_filter.py)): `_classify_arch` で分類直前に先頭/末尾の Markdown 強調マーカー `*` を除去（`.strip("*").strip()`）。`_parse_catalog` の戻り値（生文字列）は変更しない。`_ARCH_KIND_MAP` に `"データフロー処理": "batch"`（データ1回）を**追加**（既存規約の `データデータフロー処理`（データ2回）は全システムで正本のため維持）。これにより層1・層2 が解消。
- **パーサ tolerance** ([hve/app_arch_filter.py](hve/app_arch_filter.py)): `_find_column_index` の arch 列別名に `Primary Arch` を追加。見出し受理に「番号付き＋`サマリ`/`Summary` キーワード必須」パターン（`numbered_re`）を WARN 付きで追加し、`## 2. Architecture Selection Summary` を受理。`サマリ`/`Summary` を必須としたことで `## 1. Metadata` / `## 3. …` 等の非 Summary 番号セクションは選ばれない。これにより層3 が解消。エラーメッセージ・canonical 判定・既存 loose 経路（`選定結果一覧` 等）は不変。
- **Tests** ([hve/tests/test_app_arch_filter.py](hve/tests/test_app_arch_filter.py)): classify 系 7 件（`**`付き web-cloud / `**`付き batch / `データフロー処理` 1回 / `**バッチ**` / canonical 維持 / 既存 `データデータフロー処理` 維持 / 語彙外 None）と parser tolerance 系 3 件（`Primary Arch` 列受理 / `## 2.…Summary` 見出し WARN 受理 / `## 1.` デコイ表を選ばない Critical ガード）を追加。既存 18 件は無改変。

**既知の制約（本修正のスコープ外）**: APP-001（`**BFF + 会員管理マイクロサービス**`）と APP-010（`**クラウドDWH + BI/Analytics Platform**`）は canonical 語彙（web-cloud / batch）外のため `None` 分類のままで、GUI チェックリストには表示されない（語彙拡張は意味判断を伴うため別途）。`**` は分類時のみ除去するため、`_parse_catalog` の戻り値および `excluded_app_ids[].actual_architecture`（生カタログセル由来の表示用文字列）には残存する（機能影響なし）。また `_ARCH_KIND_MAP` への batch 表記追加により、batch の `target_architectures`（マップキー由来・`**` を含まない）は `データデータフロー処理` / `データフロー処理` / `バッチ` の 3 件となり、autopilot / CLI が出力する Markdown スコープ表示が冗長化するが機能影響はない。本修正はカタログ契約違反に対する防御的 tolerance であり、恒久対策は当該カタログを canonical 形式（`## A) サマリ表（全APP横断）`・`推薦アーキテクチャ` 列・太字なし）で再生成すること。output-format.md / SKILL / `_evals` / ワークフロー yml の文言更新、および GUI 統合テストでの実カタログ形式カバーは別タスクとする。

**検証**:

- `python -m pytest hve/tests/test_app_arch_filter.py hve/gui/tests/test_app_id_checklist.py -q` → **34 passed**（既存 18 + 新規 10 + GUI 6）
- 層3 消費者の回帰: `python -m pytest hve/tests/test_fanout.py hve/gui/tests/test_autopilot_planner.py hve/tests/test_catalog_parsers_screen.py hve/tests/test_catalog_parsers_input_paths.py -q` → **73 passed**
- 実カタログ分類（`.venv` 実行）: web-cloud=8 件 `{APP-002,003,006,007,008,009,011,012}`、batch=2 件 `{APP-004,005}`、非分類=2 件 `{APP-001,010}`
- 実 `AppIdChecklist` ウィジェット（offscreen 起動）: web-cloud で 8 件のエントリが生成・表示（修正前は 0 件で手入力欄にフォールバック）、batch で 2 件
- `hve.catalog_parsers.parse_dataflow_catalog` → `['APP-004', 'APP-005']`

<!-- validation-confirmed -->

### Fixed — GUI Fleet モード実行中に子サブエージェント（worker）の作業ログが表示されない問題

**概要**: GUI / CLI で Fleet モード（workflow-level DAG wave の並列実行）を使うと、起動・待機・最終結果は表示される一方、各子サブエージェント（worker）の実行中の作業ログ（ツール実行・アシスタントの発話・ストリーミング）が一切表示されず、30 秒間隔の「completion-report 待機中」ハートビートだけが流れていた。原因は `hve/fleet_mode.py` の `FleetEventCollector.handle_event` が `subagent.started/completed/failed` 以外のイベントを早期 `return` で破棄しており、親 Fleet セッションに届く子 worker の `tool.execution_start` / `assistant.message` / `assistant.message_delta` 等が console（= サブプロセス stdout → GUI Workbench）へ転送されていなかったため。`FleetEventCollector` に任意の `console` / `wave_index` を注入できるようにし、子 worker の作業イベントを通常ステップ実行（`hve/runner.py` の `_handle_session_event`）と同じ console メソッド・同じ verbosity ゲートで転送するようにした。worker の判別は SDK イベントの `parent_tool_call_id` を `subagent.started` で記録した agent 表示名へ逆引きし、転送中だけ console の行帰属 ContextVar（`_CURRENT_EMIT_STEP_ID`）へ worker ラベルを設定することで、GUI 受信側が行頭 `[hve:ctx:<label>]` マーカーで worker ごとにログを帰属できるようにした。`console` 未注入（既定）時は従来どおり lifecycle 状態のみ追跡する（後方互換）。

- **Fleet 転送** ([hve/fleet_mode.py](hve/fleet_mode.py)): `FleetEventCollector` に `console: Any = None` / `wave_index: int = 0` を追加。`handle_event` を、lifecycle 状態の更新（従来どおり）に加えて、`console` 注入時に lifecycle（`subagent.started/completed/failed/selected`）・`tool.execution_start`・`assistant.message`・`assistant.message_delta` を `console.subagent_*` / `console.tool` / `console.final_message` / `console.stream_token` へ転送するよう拡張。worker ラベルは `parent_tool_call_id`（無ければ自身の `tool_call_id`）→ `running` 逆引き（解決不可時は `fleet-w{wave_index}` フォールバック）。`assistant.message`（全文）は `show_stream=True` 時に `assistant.message_delta`（逐次）と二重表示になるため、既定（`show_stream=False`）でのみ全文を出す。子の表示可否は通常ステップと同一の verbosity ゲートに従う（lifecycle / final_message は verbosity≥1、tool は verbosity≥3、stream_token は `show_stream` 有効時）。
- **配線** ([hve/orchestrator.py](hve/orchestrator.py)): DAG wave Fleet runner で `FleetEventCollector()` を `FleetEventCollector(console=console, wave_index=wave_index)` に変更。あわせて 30 秒ハートビートに「実行中 worker 名（重複排除）」と「完了数」を追加し、待機中の進捗を可視化。`collector.handle_event` は SDK が `call_soon_threadsafe` でイベントループへ戻すため同一スレッドで同期実行され、ハートビートの `set(...)` 区間に `await` が無いことから反復中の dict 変更は起こらない（追加ロック不要）。
- **Tests** ([hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py)): 転送の回帰テストを追加。lifecycle / `subagent.selected` / tool / message / delta の各転送、worker ラベルの `parent_tool_call_id` 逆引き（複数 worker での取り違え防止を含む）と `fleet-w{wave}` フォールバック、`show_stream` による全文/逐次の二重表示防止、転送中の ContextVar set/復元（例外時の `finally` 復元を含む）、console メソッド例外時も lifecycle 追跡が壊れないこと、`console=None` 時の後方互換（作業イベント無視）を検証。テスト間の ContextVar 汚染を防ぐ autouse fixture を追加。

**既知の制約（本修正のスコープ外）**: `hve/runner.py` の legacy split-fork 経路（`subissues.md` runtime fork、opt-in の実験用途）にも `FleetEventCollector()` を console 無しで生成する箇所が残る。今回ユーザーが遭遇した DAG wave 経路（`hve/orchestrator.py`）とは別経路で、`console=None` 既定により従来動作を維持（回帰なし）。同経路の子ログ転送は別途対応とする。

**検証**:

- `python -m pytest hve/tests/test_fleet_mode.py -q` → **33 passed**
- `python -m pytest hve/tests/test_orchestrator.py -q -k "fleet or Fleet"` → **5 passed**
- `python -m pytest hve/tests/test_fleet_mode.py hve/tests/test_orchestrator.py -q -k "fleet or Fleet or Collector"`（回帰）→ **38 passed**
- `python -m py_compile hve/fleet_mode.py hve/orchestrator.py` → OK

<!-- validation-confirmed -->

### Fixed — GUI 起動中にターミナルへ `qt.text.font.db: OpenType support missing ... script 11/12` 警告が多発する問題

**概要**: `hve` GUI 実行中、ターミナルに `qt.text.font.db: OpenType support missing for "Yu Gothic UI", script 12`（および script 11）等の警告が多発していた。調査の結果、`script 11`=Devanagari / `script 12`=Bengali で、エージェント（Copilot CLI サブプロセス）出力に**文字化けで混入したインド系文字**（例: `work/gui-logs/session-*/log-*.log` に観測された `ভিত্ত` / `हट`）を GUI のログビュー（既定フォント "Yu Gothic UI" を継承する `QPlainTextEdit`）が描画する際、Windows の既定フォントフォールバック列が当該スクリプトの OpenType 整形テーブルを持たないため Qt が出力する**無害な警告**だった。Qt は警告を出しつつ適切なフォントへフォールバックして描画を継続し（クラッシュせずアプリは継続動作）機能影響はなく、ターミナルを汚すノイズのみが問題であった。`run_app()` 起動時に Qt ロギングフィルタで当該カテゴリを無効化して抑止した。なお `qt.text.font.db.warning=false`（warning レベルのみ無効化）では当該メッセージは抑止されず（`isWarningEnabled()` は False を返すが警告は出力され続ける、実測で確認）、カテゴリ全体を無効化する `qt.text.font.db=false` のみが有効だった。エージェント出力の文字化け自体は LLM 出力側の別問題であり本修正のスコープ外。

- **GUI** ([hve/gui/app.py](hve/gui/app.py)): `QLoggingCategory` を import し、`_configure_qt_logging()`（`setFilterRules("qt.text.font.db=false")`）を追加。`run_app()` 冒頭（`QApplication` 生成前）で呼び出す。本番で `QApplication` を生成する経路は `run_app()` のみ（他は全てテスト）であり、唯一の GUI 入口を網羅。warning レベル限定では抑止できないため、フォント DB の診断ログ専用カテゴリ全体を無効化する（アプリ挙動・他カテゴリへの影響なし）。
- **Tests** ([hve/gui/tests/test_qt_logging_filter.py](hve/gui/tests/test_qt_logging_filter.py) 新規): `_configure_qt_logging()` 呼び出し後に `qt.text.font.db` カテゴリの info / warning / critical が**全て**無効化されることを検証。warning 限定ルールでは critical / info が True のまま残るため、壊れたルールへの差し戻しを回帰として検出できる。autouse fixture でグローバルなフィルタ状態を既定へ復元し、他テストへの汚染を防止。

**検証**:

- `python -m pytest hve/gui/tests/test_qt_logging_filter.py -q` → **1 passed**
- 実測（クリーン別プロセス）: 本番 `_configure_qt_logging()` 適用後に Devanagari/Bengali を描画し、`OpenType support missing` 警告が **14 → 0** に抑止されることを確認。
- 回帰捕捉の実証: app.py を一時的に `qt.text.font.db.warning=false` へ戻すと新規テストが **FAILED**（`isInfoEnabled() is False` で失敗）することを確認後、正しいルールへ復元。
- 非汚染確認: `test_qt_logging_filter.py` と `test_status_banner.py` の同時実行で **10 passed**。

<!-- validation-confirmed -->

### Fixed — GUI Markdown プレビューで Markdown 表が表形式にレンダリングされない問題

**概要**: GUI の Markdown プレビューで `| A | B |` 形式の Markdown パイプ表が HTML の `<table>` として描画されず、段落テキストとして表示されていた問題を修正。原因は `markdown-it-py` の `commonmark` preset では `table` ルールが無効であること。既存の `QWebEngineView` と `preview.html` は HTML table の表示に対応済みだったため、表示コンポーネントや依存パッケージは追加せず、既存 renderer で `table` ルールのみを有効化した。

- **GUI** ([hve/gui/markdown_preview/markdown_html_renderer.py](hve/gui/markdown_preview/markdown_html_renderer.py)): `MarkdownIt("commonmark", ...)` の既存設定を維持したまま `.enable("table")` を追加し、Markdown パイプ表を HTML table に変換できるようにした。
- **Tests** ([hve/gui/tests/test_markdown_html_renderer.py](hve/gui/tests/test_markdown_html_renderer.py)): 基本表が `<table>` / `<thead>` / `<tbody>` / `<th>` / `<td>` に変換されること、左寄せ・中央寄せ・右寄せが `style="text-align:..."` として保持されることを検証する回帰テストを追加。

**検証**:

- `.venv\Scripts\python.exe -m pytest hve/gui/tests/test_markdown_html_renderer.py -q` → **10 passed**
- `.venv\Scripts\python.exe -m pytest hve/gui/tests/test_markdown_loader.py hve/gui/tests/test_preview_panel.py -q` → **12 passed**

<!-- validation-confirmed -->

### Fixed — GUI ワークフロー実行中に `assistant.usage` イベントで `TypeError: int() argument must be ... not 'datetime.timedelta'` が多発する問題

**概要**: GUI で ARD ワークフローを実行中、各ターンで `Unhandled exception in session event handler ... TypeError: int() argument must be a string, a bytes-like object or a real number, not 'datetime.timedelta'` が多発していた。原因は `hve/runner.py` の `assistant.usage` ハンドラが SDK の `AssistantUsageData.duration`（型 `timedelta | None`）を `int(dur)` でそのまま整数化しようとしていたこと。現行 SDK の `duration` は `timedelta` 型であり、数値化を前提とした `int(dur)` と型が不整合だった。例外は SDK 側 `_dispatch_event` の try/except で捕捉されワークフロー自体は継続するものの、トークン使用時間（`duration_ms`）が記録されず、毎ターン Traceback がログを汚染していた。`timedelta.total_seconds() * 1000` でミリ秒へ変換するよう修正した。

- **Runtime** ([hve/runner.py](hve/runner.py)): `assistant.usage` ハンドラの `duration` 変換を `int(dur)` から `int(dur.total_seconds() * 1000) if dur else None` に変更。`timedelta(0)` は falsy のため従来どおり `None` を記録（挙動互換）。
- **Tests** ([hve/tests/test_runner.py](hve/tests/test_runner.py)): `TestStepRunnerStreamEvents` に回帰テスト 2 件を追加。`duration=timedelta(milliseconds=1500)` が `duration_ms=1500` に変換されること、`duration=None` が `duration_ms=None` で渡ることを検証。

**検証**:

- `python -m pytest hve/tests/test_runner.py -q` → **156 passed**（既存 154 + 新規 2）
- 修正前コードへ一時的に戻して新規 timedelta テストを実行し、元ログと同一の `TypeError` で失敗することを確認（回帰捕捉能力を検証）。

<!-- validation-confirmed -->

### Added — `<run-id>` 生成タイムゾーンの選択機能（既定 JST）

**概要**: `work/runs/<run-id>/` の `<run-id>` 内タイムスタンプ生成タイムゾーンを設定可能にした。これまでは `time.gmtime()` で UTC 固定だったため、日本国内の運用で実時刻と乖離して可読性が低かった。既定値を `Asia/Tokyo` (JST) に変更し、GUI 設定画面の C1「基本設定」で世界主要 33 タイムゾーンから選択可能とした。CLI 単独実行時も新既定 JST が適用され、環境変数 `HVE_RUN_ID_TZ` で上書きできる。

- **Runtime** ([hve/config.py](hve/config.py)): `generate_run_id()` にオプショナル引数 `tz` を追加。タイムゾーン解決順は `引数 tz` → 環境変数 `HVE_RUN_ID_TZ` → 既定 `Asia/Tokyo`。不正値は警告なしで JST フォールバック。Windows で `tzdata` 未導入の環境向けに JST 固定オフセット (UTC+9) フォールバックも保持。
- **GUI** ([hve/gui/timezones.py](hve/gui/timezones.py) 新規): IANA 名 33 件のキュレーション済みタイムゾーンリスト + 表示ラベル定義。
- **GUI** ([hve/gui/page_options.py](hve/gui/page_options.py)): C1「基本設定」に `run_id_timezone` `QComboBox` を追加。`addItem(label, iana)` で IANA 名を `userData` に保持し、`settings_apply` の `currentData()` 経由で永続化。
- **GUI** ([hve/gui/settings_store.py](hve/gui/settings_store.py), [hve/gui/settings_apply.py](hve/gui/settings_apply.py)): `[options].run_id_timezone` を `defaults()` および `_SECTION_FIELDS["C1"]` に追加。
- **GUI** ([hve/gui/main_window.py](hve/gui/main_window.py)): `GuiSessionWorkdir.create()` 直前で設定ファイルから `run_id_timezone` を読み `os.environ["HVE_RUN_ID_TZ"]` に注入。
- **GUI** ([hve/gui/settings_window.py](hve/gui/settings_window.py)): 設定保存時に `os.environ["HVE_RUN_ID_TZ"]` を即時更新（後続の `generate_run_id()` / 子プロセス launch で反映）。
- **GUI** ([hve/gui/session_workdir.py](hve/gui/session_workdir.py)): `env_overrides()` に `HVE_RUN_ID_TZ` を追加し子プロセスに伝播。
- **Tests** ([hve/tests/test_config_run_id_tz.py](hve/tests/test_config_run_id_tz.py) 新規): JST 既定・env 上書き・引数優先・不正値フォールバック・フォーマット安定性・一意性の 6 ケース。
- **Tests** ([hve/tests/test_settings_store_timezone.py](hve/tests/test_settings_store_timezone.py) 新規): 既定値・ラウンドトリップ・ファイル欠損時の 3 ケース。

**検証**:

- `python -m pytest hve/tests/test_config_run_id_tz.py hve/tests/test_settings_store_timezone.py -q` → **9 passed**
- `python -m pytest hve/tests/test_gui_settings_store.py hve/tests/test_session_id.py hve/tests/test_config.py -q --deselect hve/tests/test_gui_settings_store.py::TestSettingsStore::test_theme_default_is_dark` → **既存 143 passed**（除外 1 件は本変更と無関係の既存失敗）

<!-- validation-confirmed -->

### Fixed — ARD Step 3.x prompt が `docs/company-business-requirement.md` を必須扱いし `rg: os error 2` で失敗する問題

**概要**: GUI で ARD ワークフローを実行中、Step 3.2/UC-20 で `rg: docs\company-business-requirement.md: 指定されたファイルが見つかりません。 (os error 2)` が発生。`hve/workflow_registry.py` および io-contract 側では当該ファイルは既に `required: false` 化済み（Step 1.2 が `skip_fallback` 経路で生成されない設計）だが、Agent prompt 本文（`Arch-ARD-UseCaseCatalog.prompt.md` §2 入力欄および Skills 依存欄）に「任意・存在時のみ参照」の明記がなかったため、LLM が必須入力と誤認し存在確認なしで `rg` を実行していた。横断レビューの結果、`Arch-ARD-BusinessAnalysis-Targeted.prompt.md`（既に「任意の参考コンテキスト」明記済み）および `Arch-ARD-BusinessAnalysis-Untargeted.prompt.md`（Step 1.2 自身の出力定義）は追加修正不要と判断。

- **Prompt** ([.github/prompts/Arch-ARD-UseCaseCatalog.prompt.md](.github/prompts/Arch-ARD-UseCaseCatalog.prompt.md)): §2 を「必須参照」/「任意参照（存在時のみ）」のサブセクションに分割し、`docs/company-business-requirement.md` を任意参照側に移動。「ARD Step 1.2 が skip された経路では生成されないため、参照前に必ず `Test-Path`（PowerShell）/ `[ -f ... ]`（bash）で存在確認し、存在しない場合は `rg` / `read_file` を実行せず `docs/business-requirement.md`（Step 2 出力）を一次情報として使用する」と明示。Skills 依存欄の `input-file-validation` 説明にも同旨を追記。
- **Prompt** ([.github/prompts/Arch-ARD-KPIOKRDefinition.prompt.md](.github/prompts/Arch-ARD-KPIOKRDefinition.prompt.md)): §2 一次情報フォールバック欄に同等の存在確認指示を追記。

**検証**: 該当なし（理由: prompt `.md` 本文の文言変更のみで自動テスト対象外。代替: 横断 `grep` で他 ARD prompt の同類記述を確認し、追加修正不要であることを確認済み）。

<!-- validation-confirmed -->

### Fixed — `StepRunner` の `self.workflow` 未初期化による全 Step 失敗（ARD 等）

**概要**: GUI で ARD ワークフローを実行すると、各 Step のメインタスク完了直後に `'StepRunner' object has no attribute 'workflow'` が発生し全 Step が failed 化、後続 Wave が依存解決不能で skip され workflow が `blocked` で停止していた。直前の commit `7ec68158` で `_check_output_paths_gate(..., self.workflow, ...)` および Phase 4 自己改善ループ内 `_resolve_step_output_paths(self.workflow, ...)` / `_SI_SCOPE_DEFAULTS.get(self.workflow.id, ...)` が追加されたが、`StepRunner.__init__` / `run_step()` のどちらも `workflow` オブジェクトを受け取らないため `AttributeError` で run_step の except 節に落ちる構造となっていた。ユーザーログで実際に踏んだのは run_step 終端の gate（3211 行目）。Phase 4 内 2 箇所は `auto_self_improve=True` のときに踏む同根の潜在バグで、合わせて修正した。

- **Runtime** ([hve/runner.py](hve/runner.py)): `self.workflow` 参照 3 箇所を撤去。`run_step` 冒頭で `workflow_registry.get_workflow(workflow_id)` を 1 回だけ呼び `_resolved_workflow` に保持し、Phase 4 ループと終端 gate で共有する（モジュール辞書 O(1) lookup）。`workflow_id` が None / 未解決のケースでも `_check_output_paths_gate` / `_resolve_step_output_paths` が `getattr(None, "steps", [])` 経由で安全に空リストを返すため pass する。新たに `hve.workflow_registry.get_workflow` を runner から参照する。
- **Tests** ([hve/tests/test_runner_split_required_guard.py](hve/tests/test_runner_split_required_guard.py)): `_check_output_paths_gate(ctx, workflow=None, ...)` が `AttributeError` を投げず空リスト pass する回帰テストを 1 件追加（`run_step()` が `workflow_id` から workflow を解決できなかったケースを想定）。

**検証**:

- `python -m pytest hve/tests/test_runner_split_required_guard.py -q` → **10 passed**（既存 9 件 + 新規 1 件）

<!-- validation-confirmed -->

### Fixed — CLI/GUI Orchestrator 配下で Agent が SPLIT_REQUIRED 停止し後続 Step が空 fan-out skip される問題

**概要**: GUI Orchestrator で AAS を実行中、Step.1 (`Arch-ApplicationAnalytics`) が `context_size=large` を理由に SPLIT_REQUIRED と判定し `plan.md` / `subissues.md` のみ出力して終了したため、`docs/catalog/app-catalog.md` が未生成のまま success 扱いとなった。後続の Step.2 は `app_catalog` を fanout_parser に取るため依存解決後も 0 件展開で skip され、AAS 全体が事実上停止する連鎖が発生。CLI/GUI Orchestrator 配下 (fleet mode 以外) では SPLIT_REQUIRED 判定を行わず主成果物を必ず生成させる二重ガードを追加した。

- **Runtime** ([hve/runner.py](hve/runner.py)): 既存 `_resolve_step_output_paths` に加え `_build_execution_mode_constraint_suffix` / `_check_output_paths_gate` を追加。Agent prompt の末尾に `## 実行モード制約` セクションを注入して SPLIT 判定の停止を抑止 (T4)、Step 完了直前で `output_paths` が宣言かつ全欠落なら当該 Step を fail 化 (T5)。両ガードは `OrchestratorContext is not None and not split_fork_enabled` のときのみ有効で、Cloud Agent 経路 (`ctx is None`) と Copilot SDK fleet mode (`split_fork_enabled=True`) には影響しない。
- **Docs** ([.github/copilot-instructions.md](.github/copilot-instructions.md)): §0「CLI / GUI Orchestrator 配下モード」に SPLIT_REQUIRED 判定を行わない旨と、prompt 注入 / Python ゲートの二重防衛の説明を追加。
- **Tests** ([hve/tests/test_runner_split_required_guard.py](hve/tests/test_runner_split_required_guard.py)): T4 (3 ケース: ctx=None / fleet mode / CLI-GUI 既定) と T5 (6 ケース: ctx=None / fleet mode / 宣言なし / 全欠落で fail / 1 つ存在で pass / 不明 step_id) の単体テストを追加。

**検証**:

- `python -m pytest hve/tests/test_runner_split_required_guard.py -v` → **9 passed**

<!-- validation-confirmed -->

**既知の制約**:

- T4 (prompt 注入) は LLM の指示遵守に依存するため確実性は中。T5 (Python ゲート) が決定論的な最終防衛線。
- T5 fail 化により、Agent が同じ Step で繰り返し SPLIT 判定する場合は AAS 全体が停止する。自動リトライは別タスクで対応。
- 統合シナリオテスト (Step.1→Step.2 実行) は MCP / LLM コストのため未実施。単体ガードのテストでロジック回帰は捕捉。

### Fixed — Cloud Session GUI Mission Control URL 通知と catalog readiness 待機

**概要**: GUI Workbench が Cloud Session の Mission Control URL を受信した際、`MainWindow._on_cloud_session_url_changed()` が未定義の `delay` / `catalog_path` を参照して例外化し得る問題を修正。あわせて、隣接する `_wait_catalog_ready()` の retry 待機・再チェック・timeout 時 `False` 返却を復元し、遅延生成される catalog ファイルを既存テストどおり待機できるようにした。

- **GUI** ([hve/gui/main_window.py](hve/gui/main_window.py)): Cloud Session URL ハンドラをステータス更新のみへ戻し、未定義変数参照と `None` 戻り値契約に反する `True` / `False` 返却を削除。`_wait_catalog_ready()` は各 interval 待機後に catalog readiness を再確認し、最後まで未 ready なら `False` を返すよう修正。
- **Tests** ([hve/gui/tests/test_cloud_session_gui.py](hve/gui/tests/test_cloud_session_gui.py), [hve/gui/tests/test_main_window_catalog_wait.py](hve/gui/tests/test_main_window_catalog_wait.py)): Mission Control URL 受信時のステータス更新と `None` 戻り値を軽量 fake で固定。既存 catalog wait テストで即時成功 / 遅延成功 / timeout を検証。

**検証**:
- `.venv\Scripts\python.exe -m pytest hve/gui/tests/test_main_window_catalog_wait.py -q` → **6 passed**
- `.venv\Scripts\python.exe -m pytest hve/gui/tests/test_cloud_session_gui.py -q` → **6 passed**

<!-- validation-confirmed -->

### Added — Cloud Sessions 統合（SDK 1.0.0）

**概要**: GitHub Copilot SDK 1.0.0+ の Cloud Sessions を `hve` CLI / GUI に統合。既定 OFF の opt-in として、CLI / GUI 基本設定 / Step 単位上書き / サブタスク単位上書きから Cloud Session の使用を制御できるようにした。Mission Control URL は Workbench にリンク表示し、ステータスバーにも取得状態を表示する。DAG 実行時は 1 task の wave または実効並列数 1 を原則 local、複数並列 wave を local 最低 1 件 + Cloud 約半数（実効並列バッチごとに local 1 件を維持）に自動振り分ける。

- **Config / CLI** ([hve/config.py](hve/config.py), [`hve/__main__.py`](hve/__main__.py)): `cloud_session_*` 設定と `--cloud-session*` 引数群を追加。repository owner/name/branch、同時実行上限、integration ID、Mission Control base URL、Step / subtask override JSON をサポート。
- **Runtime** ([hve/cloud_session.py](hve/cloud_session.py), [hve/dag_executor.py](hve/dag_executor.py), [hve/runner.py](hve/runner.py), [hve/orchestrator.py](hve/orchestrator.py), [hve/self_improve.py](hve/self_improve.py)): Cloud Session option 構築、SDK 未対応 fallback、`policy_blocked` 明示停止、Cloud 注入前の `streaming` 値復元、active Cloud Session limiter、DAG wave 単位の local / Cloud 自動振り分けを追加。
- **GUI** ([hve/gui/page_options.py](hve/gui/page_options.py), [hve/gui/page_workflow_select.py](hve/gui/page_workflow_select.py), [hve/gui/page_workbench.py](hve/gui/page_workbench.py), [hve/gui/workbench_state.py](hve/gui/workbench_state.py), [hve/gui/workbench_window.py](hve/gui/workbench_window.py)): 基本設定タブに Cloud Session 設定を追加。Step 行の `☁ 継承 / ON / OFF`、Mission Control URL の安全なリンク表示、旧 WorkbenchWindow 互換表示を追加。
- **Docs / Tests** ([users-guide/cloud-session.md](users-guide/cloud-session.md), [hve/tests/test_cloud_session.py](hve/tests/test_cloud_session.py), [hve/tests/test_cloud_session_cli.py](hve/tests/test_cloud_session_cli.py), [hve/tests/test_cloud_session_runtime.py](hve/tests/test_cloud_session_runtime.py), [hve/gui/tests/test_cloud_session_gui.py](hve/gui/tests/test_cloud_session_gui.py)): Cloud Sessions の利用手順・制約・トラブルシューティングを追加し、設定 / CLI round-trip / runtime fallback / GUI helper をテスト。

**検証**:

- `python -m pytest hve/tests/test_cloud_session.py hve/tests/test_cloud_session_cli.py hve/tests/test_cloud_session_runtime.py hve/tests/test_config.py hve/tests/test_runner.py::TestCreateSessionAutoReasoningFallback hve/tests/test_dag_executor.py -q` → **165 passed, 1 warning, 7 subtests passed**
- `python -m pytest hve/gui/tests/test_cloud_session_gui.py -q` → **1 skipped**（PySide6 未導入環境）
- `python -m py_compile hve/cloud_session.py hve/config.py hve/dag_executor.py hve/orchestrator.py hve/tests/test_cloud_session.py hve/tests/test_dag_executor.py` → **OK**

**既知の制約**:

- 実 Cloud Sessions 通信 smoke は未実施。ローカル検証は fake SDK / helper / CLI round-trip / GUI helper を中心に実施。
- GUI テストは PySide6 未導入環境では skip。PySide6 ありの環境では `hve/gui/tests/test_cloud_session_gui.py` を実行すること。
- GUI Autopilot 複数プロセス時の Cloud Session 同時実行上限は各プロセス内で適用される。プロセス横断の総量制御は別タスク。

<!-- validation-confirmed -->

### Changed

**CLI / GUI 標準経路の SPLIT_REQUIRED runtime fork を無効化**

**概要**: HVE Cloud Agent Orchestrator（Issue Template + GitHub Actions + Copilot Cloud Agent）と CLI / GUI Orchestrator の責務を再整理。`SPLIT_REQUIRED` / `subissues.md` は Cloud 版の GitHub Sub-Issue 作成入力として維持し、CLI / GUI 標準経路では runtime split-fork を既定無効化した。CLI / GUI の分割・並列化は workflow DAG / fan-out に集約し、`_maybe_run_split_fork` は過去互換・実験用途の明示 opt-in (`OrchestratorContext.split_fork_enabled=True`) として残置。

- **Runtime** ([hve/orchestrator_context.py](hve/orchestrator_context.py), [hve/__main__.py](hve/__main__.py), [hve/runner.py](hve/runner.py), [hve/dag_validation.py](hve/dag_validation.py), [hve/dag_executor.py](hve/dag_executor.py), [hve/fleet_mode.py](hve/fleet_mode.py), [hve/orchestrator.py](hve/orchestrator.py)): `split_fork_enabled` 既定値を `False` に変更し、CLI `orchestrate` 生成時にも明示 OFF。`check_plan_md_metadata` の注記も Cloud Sub-Issue 経路 / CLI-GUI DAG-fanout 経路 / legacy opt-in に合わせて更新。加えて `--fleet-mode` opt-in 時に、複数 Step の DAG wave を Copilot SDK Fleet mode に委譲する backend hook と SDK 接続 runner を追加。
- **Fleet safety** ([hve/fleet_mode.py](hve/fleet_mode.py), [hve/orchestrator.py](hve/orchestrator.py)): DAG wave Fleet prompt に step 別 `completion-report.md` 出力先を追加し、親側で検証マーカーを polling。空 wave / 重複 step_id / report dir 衝突 / unsafe path を拒否し、run_id / step_id は path segment として安全化。Fleet parent session は SDK Cloud Sessions と MCP servers を使わない local session として作成する。
- **Docs / Skills** ([.github/copilot-instructions.md](.github/copilot-instructions.md), [.github/skills/task-dag-planning/references/detail.md](.github/skills/task-dag-planning/references/detail.md), [.github/skills/task-dag-planning/references/plan-template.md](.github/skills/task-dag-planning/references/plan-template.md), [users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md), [users-guide/cloud-session.md](users-guide/cloud-session.md)): Cloud版（Issue Template + GitHub Actions + Copilot Cloud Agent）と SDK Cloud Sessions を分離して説明し、CLI / GUI の `SPLIT_REQUIRED` runtime fork が標準経路ではないことを明記。
- **Tests** ([hve/tests/test_orchestrator_context.py](hve/tests/test_orchestrator_context.py), [hve/tests/test_runner_split_fork.py](hve/tests/test_runner_split_fork.py), [hve/tests/test_dag_validation.py](hve/tests/test_dag_validation.py), [hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py), [hve/tests/test_dag_executor.py](hve/tests/test_dag_executor.py), [hve/tests/test_cloud_subissue_workflows.py](hve/tests/test_cloud_subissue_workflows.py), [hve/tests/test_cloud_session_cli.py](hve/tests/test_cloud_session_cli.py)): 既定無効と legacy opt-in、DAG wave Fleet prompt、Fleet backend fallback/failed contract、Cloud Sub-Issue workflow contract、CLI/GUI `--fleet-mode` 伝搬を検証。

**検証**:

- `.venv\\Scripts\\python.exe -m py_compile hve/orchestrator_context.py hve/__main__.py hve/runner.py hve/dag_validation.py hve/fleet_mode.py hve/dag_executor.py hve/orchestrator.py hve/config.py hve/gui/orchestrate_args.py hve/gui/page_options.py hve/tests/test_orchestrator_context.py hve/tests/test_runner_split_fork.py hve/tests/test_dag_validation.py hve/tests/test_fleet_mode.py hve/tests/test_dag_executor.py hve/tests/test_cloud_subissue_workflows.py hve/tests/test_cloud_session_cli.py` → **OK**
- `.venv\\Scripts\\python.exe -m pytest hve/tests/test_orchestrator_context.py hve/tests/test_runner_split_fork.py hve/tests/test_dag_validation.py -q` → **53 passed**
- `.venv\\Scripts\\python.exe -m pytest hve/tests/test_cloud_session_cli.py hve/tests/test_fleet_mode.py hve/tests/test_dag_executor.py hve/tests/test_cloud_subissue_workflows.py hve/tests/test_orchestrator.py::TestRunWorkflowDryRun::test_fleet_mode_passes_wave_runner_to_dag_executor hve/tests/test_orchestrator.py::TestRunWorkflowDryRun::test_fleet_mode_disabled_passes_no_wave_runner -q` → **59 passed**
- `.venv\\Scripts\\python.exe -m pytest hve/tests/test_orchestrator_context.py hve/tests/test_runner_split_fork.py hve/tests/test_dag_validation.py hve/tests/test_continue_on_error_e2e.py hve/tests/test_fleet_mode.py hve/tests/test_dag_executor.py hve/tests/test_cloud_subissue_workflows.py hve/tests/test_dag_executor_fanout_deferred.py hve/tests/test_deferred_fanout.py hve/tests/test_cloud_session_cli.py hve/tests/test_orchestrator.py::TestRunWorkflowDryRun::test_fleet_mode_passes_wave_runner_to_dag_executor hve/tests/test_orchestrator.py::TestRunWorkflowDryRun::test_fleet_mode_disabled_passes_no_wave_runner -q` → **128 passed**

<!-- validation-confirmed -->

**Legacy SPLIT_REQUIRED runtime fork の Copilot SDK Fleet mode helper**

**概要**: `OrchestratorContext.split_fork_enabled=True` を明示した legacy / 実験経路では、`plan.md` で `split_decision: SPLIT_REQUIRED` が宣言され、同一 work ディレクトリに `subissues.md` が出力された場合のサブタスク実行を、複数サブタスクでは GitHub Copilot SDK Fleet mode（`FleetStartRequest` / `session.rpc.fleet.start(...)`）で起動できる。CLI / GUI 標準経路では本 runtime fork は既定無効であり、Cloud 版の正式な Sub-Issue 作成は GitHub Actions (`create-subissues-from-pr.yml` / `advance-subissues.yml`) が担う。

- **SDK 1.0.0 対応** ([pyproject.toml](pyproject.toml), [hve/copilot_client_factory.py](hve/copilot_client_factory.py)): `github-copilot-sdk>=1.0.0` を前提化。SDK 1.0.0 で廃止された旧 `SubprocessConfig` / `ExternalServerConfig` 経路を `RuntimeConnection.for_stdio` / `RuntimeConnection.for_uri` + `CopilotClient(connection=...)` へ移行し、既存 `cli_path` / `cli_url` / token / log_level / `cli_args` を共通 helper で橋渡しするよう統一。
- **Fleet helper 追加** ([hve/fleet_mode.py](hve/fleet_mode.py)): `build_split_fleet_prompt` / `start_fleet` / `FleetEventCollector` を追加。Fleet prompt には durable todo ID、`depends_on`、worker 固有 report dir、`completion-report.md` 必須条件、`1 worker = 1 todo`、repository-relative 成果物パスの扱い、validation marker 条件を明記。
- **Runner 置換** ([hve/runner.py](hve/runner.py)): `_maybe_run_split_fork` を parent `session` ベースに変更し、明示 opt-in 時のみ複数 subtask で Fleet mode を起動。Fleet 起動後は timeout 内で各 subtask の `completion-report.md` を polling し、失敗 event または marker 不足を Step 失敗に反映。単一 subtask は Fleet を使わず parent session で同期実行する。
- **テスト更新** ([hve/tests/test_fleet_mode.py](hve/tests/test_fleet_mode.py), [hve/tests/test_runner_split_fork.py](hve/tests/test_runner_split_fork.py), [hve/tests/test_copilot_client_factory.py](hve/tests/test_copilot_client_factory.py), [hve/tests/test_runner.py](hve/tests/test_runner.py), [hve/tests/test_deferred_fanout.py](hve/tests/test_deferred_fanout.py)): SDK 1.0.0 の `RuntimeConnection` 形状と Fleet parent session fake に追従。ARD Step ID 再編後の deferred fan-out テストも現行 `3.2` に更新。
- **Docs** ([users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md)): `SPLIT_REQUIRED` / `subissues.md` は Cloud Sub-Issue 作成入力であり、CLI / GUI の標準分割は workflow-level fan-out / DAG wave で扱う旨に更新。

**検証**:
- `pytest hve/tests/test_copilot_client_factory.py` → **3 passed**
- `pytest hve/tests/test_runner.py` → **149 passed**
- `pytest hve/tests/test_resume_cli.py hve/tests/test_workiq.py` → **194 passed**
- `pytest hve/tests/test_runner_split_fork.py hve/tests/test_fleet_mode.py` → **35 passed**
- `pytest hve/tests/test_split_fork.py` → **37 passed**
- `pytest hve/gui/tests/test_page_workbench_fanout_progress.py hve/gui/tests/test_autopilot_stats_propagation.py hve/gui/tests/test_dag_status_widget.py` → **48 passed**（Qt font deprecation warnings のみ）
- `pytest hve/tests/test_fanout.py hve/tests/test_dag_executor_fanout_deferred.py hve/tests/test_deferred_fanout.py hve/tests/test_resume_fanout.py` → **57 passed**
- `python -m hve --help` / `python -m hve orchestrate --help` → **OK**

**既知の制約**:
- Fleet mode の実通信 smoke は未実施。ローカル検証は generated RPC 型・helper・fake session・既存 completion-report contract を中心に実施。
- `test_orchestrator.py::TestRunWorkflowFanout::test_aad_web_fanout_meta_is_forwarded_to_step_runner` は単独実行でも `docs/catalog/app-arch-catalog.md` 欠損により失敗する。エラーメッセージ上は catalog fixture / repo docs 前提の問題と整合するが、本変更起因とは断定しない。

<!-- validation-confirmed -->

### Fixed — ARD/AAS 実行ログ問題への第 2 弾修正（subissues.md fan-out / blocked status / persona_catalog 既知キー登録 / rg ガイダンス参照 / ツール失敗ログのツール名前置）

**概要**: ARD/AAS ログ精査 (全 2706 行) で検出した残存問題への対処。前回 Fixed エントリ「ARD/AAS ワークフローのツール失敗ログ修正」でカバーしきれなかった以下 5 系統の問題を解消:

1. **C-1**: 分割計画後のサブタスク自動 fan-out 未実行 — Orchestrator が `subissues.md` を読込まずに次 Step へ進行し、依存 Step が「上流未完」で連鎖停止していた。
2. **H-1/H-2**: `validate_step_inputs` での missing 入力時の silent fallback — 情報不足のまま動作させ Token 浪費 + 後段 Step で不正出力を誘発。新 status `blocked` を導入して即座に処理停止する方針に変更（Q3=A: 情報不足での動作継続は Token 消費の無駄）。
3. **H-3**: `persona_catalog` が `consumed_artifacts` 既知キー集合に未登録だったことによる `UserWarning` (AAS Step 8 `["persona_catalog", "app_catalog"]` 経路)。
4. **M-3/M-4**: `agent-common-preamble` Skill から `copilot-instructions.md` §0 の Windows × ripgrep ガイドライン (前回追加済) への可視性不足 — 共通プリアンブル冒頭で再注意喚起。
5. **M-5**: `tool.execution_complete` 失敗時のログがツール名を含まないため、AAS Step 1 で発生した `✗ ツール失敗: timeout` の真因特定が不可能だった (Q8 調査結論: ツール名特定不可、SDK 側 tool timeout 推定、補助ログ記録のみ最小実装範囲)。

- **subissues.md 自動 fan-out 実装** ([hve/orchestrator.py](hve/orchestrator.py), [hve/fanout_expander.py](hve/fanout_expander.py), [hve/split_fork.py](hve/split_fork.py)): SPLIT_REQUIRED → deferred fan-out → `subissues.md` 読込・ランタイム子 Step seed の連結を実装。`_maybe_run_split_fork` が `subissues.md` 検出時に `depends_on` 解決で wave 分割したサブタスクを並列実行（Sub-issue 生成 / サブセッション fork）し、全完了後に親 Step の後続へ進む。T-C1.3 で関連テスト (`test_split_fork.py` / `test_dag_executor_fanout_deferred.py` / `test_deferred_fanout.py` / `test_fanout.py`) を追加・既存修正。
- **新 status `blocked` 追加** ([hve/run_state.py](hve/run_state.py), [hve/dag_executor.py](hve/dag_executor.py), [hve/gui/workbench_state.py](hve/gui/workbench_state.py) 等): RunState に `blocked` を新規追加し、`validate_step_inputs` で missing inputs 検出時に `BlockedStepError` を raise → DAGExecutor が当該 Step を `blocked` 状態で停止し、後段 Step は依存解決失敗で skip される。GUI 表示にも `blocked` カテゴリを追加。
- **persona_catalog 既知キー登録** ([hve/orchestrator.py](hve/orchestrator.py), [hve/tests/test_input_artifact_check.py](hve/tests/test_input_artifact_check.py), [hve/tests/test_consumed_artifacts.py](hve/tests/test_consumed_artifacts.py)): orchestrator.py の 3 つの dict (`_detect_existing_artifacts.catalog_files` / `_ARTIFACT_KEY_TO_EXPECTED_PATH` / `_ARTIFACT_KEY_TO_GENERATING_WORKFLOW`) に `persona_catalog → docs/catalog/persona-catalog.md` / `aas` を追加。CI 整合性テスト用に 2 つの frozenset (`_KNOWN_ARTIFACT_KEYS` / `KNOWN_ARTIFACT_KEYS`) にも同キーを追加し、将来の新規 catalog 追加時の登録漏れ自動検知を維持。
- **agent-common-preamble の rg ガイダンス参照追加** ([.github/skills/agent-common-preamble/SKILL.md](.github/skills/agent-common-preamble/SKILL.md)): `## 共通ルール` セクションに、`copilot-instructions.md` §0 で追加済の Windows × ripgrep ガイドライン 2 項目 (glob `/` 区切り必須 / `Test-Path` による事前パスチェック) への引用形式の再注意喚起を追加。本体ガイドラインの重複コピーを避け、Skill 経由でも参照可能にする最小実装。
- **ツール失敗ログのツール名前置** ([hve/runner.py](hve/runner.py)): `tool.execution_complete` イベントハンドラ (success=False 分岐) で `data` から `tool_name` / `toolName` / `name` / `mcp_tool_name` / `mcpToolName` の順で抽出し (workiq.py:689 と同じく MCP 系を legacy より優先)、`error_msg` に `<tool_name>: <error_msg>` 形式で前置。`extract_tool_name_from_event` は `tool.execution_start` 専用のため使用せず、runner 側 `_get` フォールバックに集約して最小実装に倒した。既存呼び出し側 (`console.tool_result` シグネチャ / `workbench_logger._TOOL_FAILED_PATTERN` 正規表現) は変更なし、tool_name 不在時は従来挙動維持。

**検証**:
- `pytest hve/tests/test_runner.py -q` → **154 passed** (T-M5 関連 5 件新規追加: `test_tool_execution_complete_failure_includes_tool_name` / `..._includes_mcp_tool_name` / `..._without_tool_name_unchanged` / `..._mcp_tool_name_camelcase` / `..._mcp_takes_priority_over_legacy`)
- `pytest hve/tests/test_input_artifact_check.py hve/tests/test_continue_on_error_e2e.py -q` → **56 passed** (T-H3 persona_catalog 登録後の回帰なし)
- `pytest hve/tests/test_consumed_artifacts.py hve/tests/test_input_artifact_check.py hve/tests/test_continue_on_error_e2e.py -q` → **106 passed, 3 failed** (3 failed は ADFD workflow Step 6.3 不在に起因する既存破損で本作業範囲外、`git stash` 比較で本セッション修正前から存在することを実測確認)
- 個別タスク完了時に rubber-duck 敵対的レビューを sync 実施 (`T-C1.3` / `T-H1H2b` / `T-H3` 第 2 回 / `T-M3M4` / `T-M5` 第 2 回) し全 PASS。Critical/Major 指摘は同セッション内で反映後に再レビューで PASS 確認。

**既知の制約**:
- 修正プラン v2 の `T-M7` (Skill `test-strategy-template` 新規作成) は調査の結果、既存ファイル `.github/skills/testing/test-strategy-template/SKILL.md` (Commit 13057c9e 由来) が存在し、かつ前回 Fixed エントリ「ARD/AAS ワークフローのツール失敗ログ修正」の `skill_directories` root + subdirs 列挙修正 / `_RESUME_SESSION_KEYS` の `skill_directories` 追加で既に解消済であったため対応不要と判定 (重複作成は捏造禁止違反のため回避)。現環境で `pytest hve/tests/test_runner.py::TestCreateSessionAutoReasoningFallback hve/tests/test_runner.py::TestAvailableExcludedToolsPropagation::test_resume_session_keys_includes_tools -q` → 4 passed で再確認。
- `Q8` 調査 (`AAS Step 1` の 88 秒経過 timeout) の真因確定は SDK 側 tool 呼び出しのデフォルト timeout 推定が最有力だが、ログ上は「ツール失敗: timeout」のみでツール名特定不可だったため確証なし。M-5 修正により次回再発時は `<tool_name>: timeout` 形式でログ記録され真因特定可能。
- `hve/self_improve.py:91-105` の `_WORKFLOW_SKILLS_MAP` に `planning/task-dag-planning` 等の存在しないプレフィックス付きパスが残っているが、L504-506 で `skill_resolver.get_skill_subpaths_for_workflow()` を優先し `_WORKFLOW_SKILLS_MAP` は legacy fallback のみのため機能的影響は限定的 (別タスク化推奨)。
- PySide6 不在環境のため GUI 系テスト (`test_workbench_logger_tool_failed.py` の T-M5 新規追加分含む) は本セッションでは未実行。runner 側の `_handle_session_event` 単体テスト (`test_runner.py` 5 件) で代替検証済。
- T-H3 関連で発見した既存 3 件失敗 (`TestPhase4ConsumedArtifactsValues::test_adfd_step6X_uses_aas_catalogs`) は ADFD workflow Step 6.3 不在に起因する別タスク扱いで、本セッション修正範囲外。

<!-- validation-confirmed -->

### Added — GUI セッション終了時のログ全文ダンプ (`console-log.txt`)

**概要**: `hve` GUI アプリケーション（`hve/gui`）で、ワークフローキューが完了 / fatal / 停止確定したタイミングで画面（ログタブの「全体」ビュー）に表示されている全ログを `work/runs/<session_run_id>/console-log.txt` に UTF-8 で 1 ファイルとしてダンプする機能を追加。既存の `work/gui-logs/session-*/log-NNNN.log`（10,000 行ローテーション付き永続化）はそのまま残置し、新ファイル `console-log.txt` を追加生成する。

- **実装**: [hve/gui/page_workbench.py](hve/gui/page_workbench.py) にモジュールレベル純関数 `_write_console_log(text, run_dir)` を追加（UTF-8 上書き、`OSError` 握りつぶしで GUI 動作を止めない）。`WorkbenchPage` に `set_session_work_root(run_dir)` setter と `_maybe_dump_console_log()` 内部メソッドを追加し、`_start_next_in_queue` のキュー消化完了分岐、`_on_process_finished` の fatal 分岐と停止要求分岐の 3 箇所で `process_finished.emit` 直前に呼び出す。
- **配線**: [hve/gui/main_window.py](hve/gui/main_window.py) で `WorkbenchPage` 生成直後に `self._session_workdir.work_root`（`GuiSessionWorkdir.work_root`）を `set_session_work_root` 経由で注入。
- **テスト**: [hve/gui/tests/test_console_log_dump.py](hve/gui/tests/test_console_log_dump.py) を新規追加。純関数の単体テスト 8 件（正常系 / 上書き / 空文字列 / `run_dir=None` / dir 不在 / dir がファイル / UTF-8 多バイト保持 / POSIX read-only dir 失敗）+ `WorkbenchPage` 統合テスト 4 件（setter / `_maybe_dump_console_log` / `set_session_work_root` 未呼び出し時の no-op / キュー完了時の dump 発火）の計 12 件、全 PASS（POSIX 限定 1 件 skip）。
- **検証**: 新規テスト 12 件 (`test_console_log_dump.py`) 全 PASS。直接関連する既存テスト群 (`test_log_tabs.py` / `test_workbench_no_hscroll.py` / `test_autopilot_stats_propagation.py` / `test_session_workdir.py` / `test_main_window_session_artifacts.py` / `test_main_window_resize.py`) で私の変更による regression なし（ベースラインで既に失敗している 5 件は本変更と無関係であることを `git stash` 比較で確認）。

<!-- validation-confirmed -->

### Added — 自動コンテキスト圧縮（Auto Compaction）オプション

**概要**: Copilot SDK v1.0.0 の `infinite_sessions`（バックグラウンド compaction）をサブステップ実行で有効化する `auto_compaction` オプションを追加。Context Window 使用量を SDK 側で自動圧縮させることで、長文 workflow が Context 上限で打ち切られるリスクを低減する。既定 OFF（オプトイン）。

- **Config**: `HVEConfig.auto_compaction: bool = False`（[hve/config.py](hve/config.py)）。
- **CLI**: `--auto-compaction` / `--no-auto-compaction`（`BooleanOptionalAction`）を `orchestrate` サブコマンドに追加（[hve/__main__.py](hve/__main__.py)）。
- **GUI**: 設定画面 Autopilot セクションに「自動コンテキスト圧縮 (auto_compaction)」チェックボックスを追加（[hve/gui/settings_window.py](hve/gui/settings_window.py)）。`build_args_for_workflow` の SSOT bridge 経由で subprocess へ `--auto-compaction` を伝播（[hve/gui/page_options.py](hve/gui/page_options.py), [hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py)）。
- **Runner**: `runner.py` のサブステップ実行で `auto_compaction=True` の場合に `create_session(..., infinite_sessions={"enabled": True})` を渡す（[hve/runner.py](hve/runner.py)）。しきい値は SDK 既定（background=0.80 / buffer=0.95）に委ねる。
- **Docs**: [users-guide/hve-cli-orchestrator-guide.md](users-guide/hve-cli-orchestrator-guide.md) に「自動コンテキスト圧縮」節を追加。
- **テスト**: `test_runner.py` に 2 件（True 時 `infinite_sessions` が渡る / 既定 OFF 時はキー不在）、`test_main.py` に 3 件（既定 False / `--auto-compaction` で True / `--no-auto-compaction` で False）を追加。全 PASS。

<!-- validation-confirmed -->

### Changed — Workflow ステップ番号体系再編（AAS / ADFD / ASDW-WEB / ARD）

**概要**: 4 ワークフローでステップ ID / コンテナ構成を再編。互換性のため GUI/CLI 側の ARD グループ ID ("1"/"2"/"3"/"4") は維持しつつ、`_WORKFLOW_GROUP_MAPS` の展開先のみを新 ID に切替。

- **AAS**: 旧ソース順 7→9→8 を 7→8→9 に並べ替え（Step ID は不変）。コメント "ARD は 7 step" → "8 step" 修正。
- **ADFD**: 旧 Step 6.1 / 6.2 / 6.3 → 1 / 2 / 3 に簡素化。`depends_on=["1","2"]` の AND ジョイン化。テンプレート (`templates/adfd/step-1.md` 等)・io-contracts・workflow YAML (`auto-dataflow-design-reusable.yml`) を一括 renumber。
- **ASDW-WEB**: 旧 18 ステップを 5 コンテナ (1=データ / 2=追加サービス / 3=Compute / 4=UI / 5=レビュー) + 17 実ステップ (1.1〜5.2) に再編。**新規 3 ステップ追加**: `Dev-Microservice-Azure-AddServiceTestCoding` (2.3), `Dev-Microservice-Azure-AddServiceTesting` (2.4), `Dev-Microservice-Azure-ComputePostDeployTest` (3.5)。テンプレート・io-contracts を git mv で renumber、producer 相互参照を更新。
- **ARD**: 旧 Step 3 (KPI/OKR) → 2.1、旧 4.1 / 4.2 / 4.3 → 3.1 / 3.2 / 3.3 に再採番。`_WORKFLOW_GROUP_MAPS["ard"]` の "3" → ["2.1"], "4" → ["3.1","3.2","3.3"] に更新（GUI/CLI 表示は不変）。`Arch-ARD-UseCaseCatalog.prompt.md` の Step 番号表記も同期。
- **AAGD**: 廃止予定のため現状維持。
- **検証**: `test_workflow_registry.py` / `test_workflow_registry_ard.py` / `test_main_ard.py` / `test_template_engine.py` / `test_plan_review_gap.py` / `test_plan_review_runner.py` を新 ID に追従更新し全合格 (171 + 167 件)。

### Added

- `.github/prompts/Dev-Microservice-Azure-{AddServiceTestCoding,AddServiceTesting,ComputePostDeployTest}.prompt.md` — 新規ステップの最小スタブ（本仕様は別タスクで作成予定）。

### Notes

- ASDW-WEB の reusable workflow YAML (`auto-app-dev-microservice-web-reusable.yml`) は AI Agent ブロックを温存するため OUT-OF-SYNC NOTICE コメントのみ追加し、本タスクでは再 renumber を見送り（別タスクで対応）。
- 新規 3 Agent の prompt 本体仕様は別タスクで確定済み（`Dev-Microservice-Azure-AddServiceTestCoding` / `AddServiceTesting` / `ComputePostDeployTest`）。それぞれ TDD RED 生成 / TDD GREEN テスト実行+設定補完 / post-deploy smoke+ヘルスチェック の責務を担う。

<!-- validation-confirmed -->

### Fixed — ARD/AAS ワークフローのツール失敗ログ修正

**概要**: `hve gui` での ARD/AAS ワークフロー実行時にログへ出力されていた 3 系統 5 件のツール失敗（`Skill not found: test-strategy-template` / `os error 2/3` for `docs/templates/testspec-vs-teststrategy.md` および `docs/catalog/{data-model,domain-analytics}.md` / `unopened alternate group` glob エラー）と、その背後にある 2 種の隠れた根本原因（`resume_session` 経路での `skill_directories` 脱落 / subissues.md 出力先パスドリフトによるオーケストレーション上流カスケード停止）を解消。CLI のスキル発見ロジック修正（初回 create + resume 両経路）、削除済テンプレートのインライン化、rg 利用衛生ガイダンス追加、AAS workflow 9 prompt の `**WORK**:` ヘッダを `work/runs/<run-id>/<agent>/Issue-<識別子>/` に統一の 5 点で対応。`/docs` 配下の per-run 生成物には触れず、上流 Step 部分完了に起因する `docs/catalog/*.md` の os error 2 系ノイズは衛生ガイダンスで抑制するに留める（オーケストレーション上流カスケード停止の根治は subissues.md パスドリフト修正側で達成）。

- **CLI スキル発見**（[hve/runner.py](hve/runner.py), [hve/orchestrator.py](hve/orchestrator.py)）: `_create_session_with_auto_reasoning_fallback` の `skill_directories` を root のみから「root + `.github/skills/` 直下サブフォルダ列挙」に変更。Copilot CLI のスキル発見は深さ 1（`<root>/<name>/SKILL.md`）のみ走査するため、`testing/test-strategy-template/` のようなネスト配置スキルがこれまで未登録だった。RPC probe で対象 10 スキル全 FOUND を実証（root のみで深さ 1 列挙 15 件 → root+subdirs で総列挙数増加、対象ネストスキル 10 件全 FOUND に転換）。
- **削除済テンプレート参照解消**（[.github/prompts/Arch-TDD-TestStrategy.prompt.md](.github/prompts/Arch-TDD-TestStrategy.prompt.md), [.github/io-contract-exceptions.yaml](.github/io-contract-exceptions.yaml)）: commit `bd503391` で削除済の `docs/templates/testspec-vs-teststrategy.md` への dangling 参照を、削除前の全文 17 行を prompt の「役割分離ルール（必読）」セクションへインライン展開して解消。`io-contract-exceptions.yaml` の `static_paths` から該当エントリも除去。
- **rg 利用衛生ガイダンス追加**（[.github/copilot-instructions.md](.github/copilot-instructions.md)）: §0 末尾に「ripgrep (rg) 利用ガイドライン（絶対）」を追加。(1) `-g` / `--glob` には `/` 区切りを使用、`\` 区切り・brace-glob のエスケープを禁止（`unopened alternate group; missing '{'` エラー回避）、(2) 上流 Step 部分完了で未生成の可能性があるパスは `Test-Path` / `[ -f ... ]` で事前確認してから rg 起動（`os error 2` / `os error 3` ノイズ抑制）。
- **resume 経路の skill_directories 脱落修正**（[hve/runner.py](hve/runner.py)）: `_RESUME_SESSION_KEYS` frozenset に `"skill_directories"` を追加。これまで初回 `create_session` 時にのみ root+subdirs のフル列挙が渡され、`resume_session` 経路では `skill_directories` が `session_opts` から脱落していたため、resume されたサブステップでネストスキル（`testing/test-strategy-template/` 等）が再び発見されない潜在 regression があった。コメントを「CLI スキル発見ロジック修正の resume 対称性確保」目的で拡張。既存 `except Exception → create_session` フォールバック（L1243-1252）が SDK 側で未対応キーだった場合の安全網として機能する旨を明記。
- **subissues.md / plan.md 出力先パスドリフト修正**（[.github/prompts/Arch-ArchitectureCandidateAnalyzer.prompt.md](.github/prompts/Arch-ArchitectureCandidateAnalyzer.prompt.md), [.github/prompts/Arch-Microservice-DomainAnalytics.prompt.md](.github/prompts/Arch-Microservice-DomainAnalytics.prompt.md), [.github/prompts/Arch-Microservice-ServiceIdentify.prompt.md](.github/prompts/Arch-Microservice-ServiceIdentify.prompt.md), [.github/prompts/Arch-DataModeling.prompt.md](.github/prompts/Arch-DataModeling.prompt.md), [.github/prompts/Arch-DataCatalog.prompt.md](.github/prompts/Arch-DataCatalog.prompt.md), [.github/prompts/Arch-Microservice-ServiceCatalog.prompt.md](.github/prompts/Arch-Microservice-ServiceCatalog.prompt.md), [.github/prompts/Arch-TDD-TestStrategy.prompt.md](.github/prompts/Arch-TDD-TestStrategy.prompt.md), [.github/prompts/Arch-UI-PersonaScreenList.prompt.md](.github/prompts/Arch-UI-PersonaScreenList.prompt.md), [.github/prompts/Arch-PersonaCatalog.prompt.md](.github/prompts/Arch-PersonaCatalog.prompt.md)）: AAS workflow で実行される 9 prompt の `**WORK**:` ヘッダを `/work/<agent>/Issue-<識別子>/` から `work/runs/<run-id>/<agent>/Issue-<識別子>/` に統一。これまで Agent が run-id 外（旧 `work/<agent>/Issue-0/`）に `subissues.md` / `plan.md` を出力すると、`hve.split_fork.discover_subissues_md_verbose()` が `work_root = work/runs/<run-id>/` 配下のみを検索する仕様により subissues.md を発見できず、`_maybe_run_split_fork` が SPLIT fork を起動しないまま `True` を返し、次 Step に進行 → 依存 Step が「上流未完」で連鎖停止する隠れた根本原因となっていた。`work-artifacts-layout` Skill §4.1 規約への完全準拠で解消。`Arch-ArchitectureCandidateAnalyzer.prompt.md` は ヘッダ以外の L26 / L95 の旧パス参照も同期修正。

**検証**:
- T1: `pytest hve/tests/test_runner.py::TestCreateSessionAutoReasoningFallback` 3 PASS、`skills.discover` RPC で root のみだとフラット 15 件のみ検出 → root+subdirs を渡すと対象 10 ネストスキル全 FOUND に転換することを実証。
- T2: 全リポ grep で `testspec-vs-teststrategy` 参照ゼロ（`work/log.txt` の過去エラー記録を除く）。`validate-io-contract.py` のベースライン比較で差分ゼロ（編集が新たな io-contract エラーを生まないことを確認、既存 258 行エラー数は不変）。
- T3: 既存 qa/ 専用 rg ガイダンス（`work-artifacts-layout` / `task-questionnaire/references/*.md`）は新規一般ルール「存在未確定パスの事前チェック」の個別ケースとして共存、矛盾なし。glob 区切りルールは新規（既存皆無）。
- R1: `pytest hve/tests/test_runner.py::TestAvailableExcludedToolsPropagation::test_resume_session_keys_includes_tools hve/tests/test_resume_phase3.py` 24 PASS（`_RESUME_SESSION_KEYS` 拡張による resume 経路の回帰なし）。
- R3: `pytest hve/tests/test_aas_template_parity.py hve/tests/test_workflow_registry.py hve/tests/test_dag_parity.py` 140 PASS / 2 xfail（既存）。`_maybe_run_split_fork` は元から SPLIT 子の完了を `asyncio.Semaphore` で await する実装であることを `hve/runner.py:2174-2196` で確認。R3 修正により subissues.md が run-id 配下に出力 → `discover_subissues_md_verbose` 成功 → 既存の semaphore-aware fork が機能 → 上流停止カスケード解消。
- R2 (D-1): コード変更なし。R3 で根本対処済（subissues.md が正しい場所に出力されれば既存の `_maybe_run_split_fork` が SPLIT 子を起動・await する）。`test_runner_split_fork.py` で 4 件失敗を確認したが、うち 1 件 (`test_other_step_split_required_does_not_trigger`) は `git stash` で本セッション修正退避後も同じ失敗を直接再現し、本セッション修正以前から既存であることを実測確認。残り 3 件 (`test_parse_failure_renames_work_dir` / `test_failed_dir_is_ignored` / `test_non_split_step_skips_discovery`) は同種のテスト環境固有挙動（`HVE_WORK_ROOT = tmpdir/work` で他 dir の plan.md を整合性チェックが拾う）が原因と推定（未直接検証）。いずれも本変更による回帰ではない。

**既知の制約**:
- ARD workflow の 4 prompt (`Arch-ARD-*`) および `Arch-ApplicationAnalytics` は `**WORK**:` ヘッダ無し → `work-artifacts-layout` Skill §4.1 規約を継承 → 元から正しい場所に出力 → R3 修正対象外。
- AAS / ARD 以外の workflow 用 prompt 群（`Arch-AIAgentDesign-*` / `Arch-AgenticRetrieval-*` / `Arch-Dataflow-*` / `Arch-ImprovementPlanner` / `Arch-Microservice-ServiceDetail` / `Arch-UI-Detail` / `Arch-UI-List` / `Dev-Dataflow-*` 5 件 / `Dev-Microservice-Azure-*` 19 件 / `Doc-*` 19 件 / `E2ETesting-Playwright` / `KnowledgeManager` / `QA-*` 6 件、計 **61 件**）の `**WORK**:` ヘッダ直書きと、3 件（`Dev-Microservice-Azure-{ComputeDeploy-AzureFunctions,DataDeploy,UIDeploy-AzureStaticWebApps}`）+ `E2ETesting-Playwright` / `KnowledgeManager` / `QA-{AzureArchitectureReview,AzureDependencyReview,CodeQualityScan,PostImproveVerify}` の Skill 参照行・成果物パス例 11 箇所も合わせて `work/runs/<run-id>/<agent>/Issue-<識別子>/` 形式に統一済（A-1 タスクで対応、本セッション継続）。リポジトリ全体の `WORK**:` ヘッダ 70 件すべて新書式統一を grep で実証。
- `test_runner_split_fork.py` の既存 4 件失敗（`test_parse_failure_renames_work_dir` / `test_failed_dir_is_ignored` / `test_non_split_step_skips_discovery` / `test_other_step_split_required_does_not_trigger`）は本セッション以前から存在し、`work_root` 整合性チェック (`work_root.glob("*/Issue-*/plan.md")`) が他 Step / 他 Agent の plan.md を検出して整合性違反扱いするテスト環境固有の挙動。本番環境では `HVE_WORK_ROOT = work/runs/<run-id>` で隔離されるため影響限定。別タスクで切り分け対応。

<!-- validation-confirmed -->

### Fixed — io-contract YAML の Step 番号体系再編追従漏れ解消 (A-3)

**概要**: Workflow ステップ番号体系再編 (本ファイル L29 の `Changed` エントリ完了後)、`.github/io-contracts/` 配下の YAML が producer フィールド・required input パス宣言で旧 Agent 形式 (per-Step suffix なし) のままだったため `validate-io-contract.py` で 227 件のエラーを発生させていた状態を解消。AAS/ARD/ADFD 3 workflow のうち Step 番号体系再編に直接起因する 37 件 (Integrity 27 / Registry 10) を修正。残り 190 件 (ASDW-WEB renumber 別タスク, AAGD/ADFDV/AAD-WEB/AAG ドリフト, Schema YAML parse 9 件, aas/8/aas/9 構造的欠落 2 件) は別タスク化推奨として「既知の制約」に記載。

- **ARD Step 3.1/3.2/3.3 self-input 修正** ([.github/io-contracts/Arch-ARD-UseCaseCatalog--ard--3.1.yaml](.github/io-contracts/Arch-ARD-UseCaseCatalog--ard--3.1.yaml) ほか 2 件): `docs/company-business-requirement.md` input を `required: true → false` に変更。`workflow_registry.py` L982-984/997-999/1010 のコメント (skip_fallback により片方しか生成されない経路あり) と整合。
- **ARD 3.3 を producer に指定する 6 consumer YAML 更新** ([.github/io-contracts/Arch-AIAgentDesign-Step1.yaml](.github/io-contracts/Arch-AIAgentDesign-Step1.yaml), `Step2.yaml`, `Step3.yaml`, [.github/io-contracts/Arch-ApplicationAnalytics.yaml](.github/io-contracts/Arch-ApplicationAnalytics.yaml), [.github/io-contracts/Dev-Microservice-Azure-UICoding.yaml](.github/io-contracts/Dev-Microservice-Azure-UICoding.yaml), [.github/io-contracts/QA-AzureArchitectureReview.yaml](.github/io-contracts/QA-AzureArchitectureReview.yaml)): `producer: Arch-ARD-UseCaseCatalog` → `--ard--3.3` に統一。
- **ADFD プレースホルダ統一** ([.github/io-contracts/Arch-Dataflow-AppSpec--adfd--1.yaml](.github/io-contracts/Arch-Dataflow-AppSpec--adfd--1.yaml), [.github/io-contracts/Arch-Dataflow-TDD-TestSpec--adfd--3.yaml](.github/io-contracts/Arch-Dataflow-TDD-TestSpec--adfd--3.yaml)): `{appId}` → `{key}` に統一 (3 箇所)。`workflow_registry.py` L611-630 (ADFD steps 全 `{key}`) と整合。
- **AAS producer 宣言 25 件更新** ([.github/io-contracts/Arch-AgenticRetrieval-Detail.yaml](.github/io-contracts/Arch-AgenticRetrieval-Detail.yaml), `Arch-AIAgentDesign-Step{1,2,3}.yaml`, [.github/io-contracts/Arch-Microservice-ServiceCatalog.yaml](.github/io-contracts/Arch-Microservice-ServiceCatalog.yaml), [.github/io-contracts/Arch-TDD-TestStrategy.yaml](.github/io-contracts/Arch-TDD-TestStrategy.yaml), `Dev-Microservice-Azure-{AgentCoding,ServiceCoding-AzureFunctions,UICoding,ServiceTestCoding}.yaml`): producer を path-context に応じて per-Step 形式 (`--aas--3.1` for DomainAnalytics, `--aas--3.2` for ServiceIdentify, `--aas--4.1` for `data-model.md` context, `--aas--4.2` for `sample-data.json` context) に統一。
- **AAS Step 3.1 input 追加** ([.github/io-contracts/Arch-Microservice-DomainAnalytics--aas--3.1.yaml](.github/io-contracts/Arch-Microservice-DomainAnalytics--aas--3.1.yaml)): `docs/catalog/app-catalog.md` を required input として追加 (producer: `Arch-ApplicationAnalytics--aas--1`)。`workflow_registry.py` L311 (required_input_paths 3 件) と整合。

**検証**:
- `python .github\scripts\validate-io-contract.py` 実行で総エラー数 227 → 190 (-37 件) を実測。新規エラー 0 を全 5 中間ステップ (a3-1〜a3-5) で確認。エラー推移: 227 → 224 (a3-1 ARD self -3) → 218 (a3-2 ARD producers -6) → 212 (a3-3 ADFD -6) → 191 (a3-4 AAS producers -21) → 190 (a3-5 AAS self -1)。
- 内訳: ベースライン (Schema 9 / Integrity 76 / Registry 142) → 修正後 (Schema 9 / Integrity 49 / Registry 132)。Schema 9 件は不変 (`Arch-TDD-TestSpec.yaml` の YAML parse error 等、Step 番号体系再編と無関係なため A-3 スコープ外)。
- 関連 pytest (`hve/tests/test_workflow_registry.py` / `test_aas_template_parity.py` / `test_dag_parity.py`) で 140 PASS / 2 xfail (既存)、regression なし。

**既知の制約**:
- 残存 190 件は以下の別タスクで対応推奨:
  - **ASDW-WEB**: 18→17 ステップ renumber に伴う io-contract 追従が別タスクで進行中 (約 42 件)。
  - **AAGD / ADFDV / AAD-WEB / AAG**: 各 workflow の独自 drift (約 80+ 件)。
  - **Schema YAML parse errors 9 件**: `Arch-TDD-TestSpec.yaml` の YAML インデント異常 (L46) 等、別タスクで対応。
  - **aas/8 / aas/9 構造的欠落 2 件**: `Arch-UI-PersonaScreenList--aas--*.yaml` / `Arch-PersonaCatalog--aas--*.yaml` の per-Step 形式 io-contract が一切存在しない (glob 結果ゼロ件)。renumber 起因ではなく per-Step contract 導入時の作成漏れまたは「これら Agent は generic のみで提供されている設計」のいずれか。別タスクで作成判断要。

<!-- validation-confirmed -->

---

## [Unreleased — 旧エントリ]

### Changed — 全オーケストレーター作業ファイル出力先を `work/runs/<run-id>/` に統一

**概要**: Cloud / GUI / CLI の全オーケストレーターで生成される作業ファイルを `work/runs/<run-id>/{既存パス}` 配下に隔離し、再実行ごとに成果物が独立 dir に分離されるよう統一した。これまで `work/Issue-*/`, `work/<agent>/Issue-*/`, `work/gui-runs/<gui-...>/`, `work/kpi/`, `work/self-improve/run-<id>/` 等にフラット出力されていた成果物が探しづらかった問題を解消。`<run-id>` は GUI/CLI 起動時に `hve.split_fork.resolve_run_id()` が採番し、env `HVE_WORK_ROOT` / `HVE_RUN_ID` 経由で子プロセスに伝播する。

- **コア**: `hve/split_fork.py` に `resolve_run_id()` 新設（env `HVE_RUN_ID` 優先 → GitHub Issue 検出 `issue-<N>` → `generate_run_id()` フォールバック、Cloud は `GITHUB_ISSUE_NUMBER` / `GITHUB_EVENT_PATH` を参照）。`resolve_work_root()` を `work/runs/<run-id>/` 返却に変更。
- **CLI**: `hve/__main__.py` の `orchestrate` / `resume` サブコマンドハンドラ冒頭で `_ensure_run_workdir_env()` を呼び、env を必ず設定。軽量サブコマンド（`--help`, `mdq` 等）は対象外。
- **GUI**: `hve/gui/session_workdir.py` の `SESSION_ID_PREFIX = ""` / `GUI_RUNS_DIRNAME = "runs"` に変更（`gui-` プレフィックス廃止）。`env_overrides()` に `HVE_RUN_ID` を追加。archive 配置を `work/archive/<run-id>.zip`（runs/ の sibling）に変更。
- **特殊パス統合**: `work/kpi/fork-kpi-<run_id>.jsonl` → `work/runs/<run-id>/kpi/fork-kpi.jsonl`（ファイル名から run_id 重複除去）。`work/self-improve/run-<id>/` → `work/runs/<run-id>/self-improve/`。
- **session-state/ は据え置き**: journal.jsonl / journal-archive/ は元から `session-state/runs/` 配下で `work/` と独立しているため変更なし。
- **ドキュメント網羅更新**: `.github/copilot-instructions.md`, `work-artifacts-layout` / `task-dag-planning` / `repo-onboarding-fast` SKILL 群, `.github/prompts/*.prompt.md` 5 件, `.github/io-contracts/*.yaml` 12 件のパス例を `work/runs/<run-id>/` ベースに更新。
- **テスト**: 新規 `test_cloud_run_id.py` (10) / `test_run_unified_workdir.py` (7) を追加、既存 `test_split_fork.py` / `test_self_improve.py` / `test_session_workdir.py` / `test_explorer_roots.py` を新仕様に追従更新。
- **マイグレーション**: `work/gui-runs/` 110 dir / `work/aas/` / `work/runs/` 内テスト残滓 を削除（ホワイトリスト方式、`completion-report.md` 未提出 dir 0 件確認後に実施）。

**検証**: `pytest hve/tests/test_split_fork.py test_cloud_run_id.py test_run_unified_workdir.py test_fork_kpi_logger.py test_self_improve.py test_prompt_templates.py hve/gui/tests/test_session_workdir.py test_explorer_roots.py` で 200 PASS。<!-- validation-confirmed -->

**既知の制約**:
- Cloud で `issue-<N>` を採用しているため、同一 Issue の再実行で同一 dir に上書きされる（過去履歴喪失）。必要時は `issue-<N>-<timestamp>` への後日拡張可能（YAGNI）。
- `test_orchestrator.py` 全件実行は別途要（self-improve 周りのテスト hang 懸念。本変更範囲外）。

### Fixed — Step 1 プランレビュー誤検知（[次へ] バナーとプランレビュー判定の二系統）の解消

**概要**: GUI Step 1 で「バナーは OK だが [次へ] 押下後のプランレビュー画面で本来不要な `docs/company-business-requirement.md` が必須扱いされ進行不可」となる二系統判定の不整合を解消。ブロッキング判定の SoT を Phase A Precheck（`run_step1_precheck` → `summarize_requirements_for_selection`）に一本化し、Phase B プランレビュー Dialog の `gaps` は補完サジェスト情報のみで [このプランで実行] ボタンを無効化しないようにした。あわせて fanout 未展開プレースホルダ（`docs/usecase/{key}-detail.md` 等）を gap 提案対象から除外して False positive を防止。

- `hve/autopilot/plan_review_model.py`: `AutopilotPlanReview.has_blocking_gaps` を常に `False` を返す実装に変更（ブロッキング判定は Phase A に統一済みであることを docstring に明記）。
- `hve/autopilot/plan_review_gap.py`: `_has_unexpanded_placeholder` ヘルパを追加し、`compute_gaps_and_resolve_inputs` 内で `{key}` `{jobId}` 等の未展開プレースホルダを含むパスを gap 提案対象から除外。入力一覧上は `MISSING_GAP` 表示のまま参考情報として残す。
- `hve/tests/autopilot/test_plan_review_runner.py`: `test_has_blocking_gaps_property` を新挙動（常に False）に更新。
- `hve/tests/autopilot/test_plan_review_gap.py`: `test_compute_gaps_skips_unexpanded_placeholder` を追加。

**Notes**: `collect_planned_inputs` の入力一覧側プレースホルダ表示は変更せず（ブロッキング動作には影響しないため）。`required_input_paths` メタデータの値はプロンプト生成・実行判定には直接使われず（`fanout_expander` で透過コピーされるのみ）、orchestrator のプロンプト本文生成は `hve/orchestrator.py` 側で直接ファイル読込して `{business_requirement_content}` 変数に渡すため、T4 での registry 削除による副作用なし。

### Changed — ARD Step 4.2 / 4.3 の `required_input_paths` から `docs/company-business-requirement.md` を削除

**概要**: ARD Step 4.1 のコメント（registry L957）で「`docs/business-requirement.md` (Step 2) と `docs/company-business-requirement.md` (Step 1.2) は `skip_fallback` により片方しか生成されない経路があるため `required_input_paths` には含めない」と明記されている方針に対し、Step 4.2 / 4.3 では含めてしまっている内部矛盾を解消。プロンプト本文への当該ファイル内容注入は `hve/orchestrator.py` 側で直接ファイル読込（`business_req_path.read_text`）して `{business_requirement_content}` 変数として渡しており、`required_input_paths` メタデータとは独立しているため orchestrator 実行への副作用なし。

- `hve/workflow_registry.py`: ARD Step 4.2 / 4.3 の `required_input_paths` から `docs/company-business-requirement.md` を削除。Step 4.1 と同方針である旨をコメントで明記。

**検証**: `pytest hve/tests/autopilot/ hve/tests/test_workflow_registry_ard.py hve/tests/test_ard_target_business_prompt.py hve/tests/test_main_ard.py hve/gui/tests/test_plan_review_dialog.py` で 122 PASS / 1 skip。

### Changed — 追加 Azure サービス選定で AI/LLM・RAG カテゴリに Foundry / Azure AI Search を強制

**概要**: ASDW-WEB / ASDW の `Step.2.2 追加 Azure サービス選定` および AAD-WEB に新設した `Step.2.5` で使用する `Dev-Microservice-Azure-AddServiceDesign` Prompt に、AI/LLM・検索カテゴリの強制ルールを追加。チャットボット / Prompt 処理 / AI Agent 要件を含むサービスでは第一候補を **Microsoft Foundry (Foundry Agent Service)** に固定し、**Azure OpenAI Service の直接利用を禁止**（Foundry resource 経由のモデル参照のみ許容）。Base RAG / Advanced RAG / ナレッジ検索を含む場合は検索カテゴリの第一候補を **Azure AI Search**（**Foundry IQ knowledge base** — Azure AI Search を knowledge ストアとして Foundry Agent Service と MCP 接続する仕組み— として `RemoteTool` 接続）に固定。判定は機能要件・外部依存・ユースケース記述本文に限定（コードコメント・URL リテラル等は対象外）。

- `.github/prompts/Dev-Microservice-Azure-AddServiceDesign.prompt.md`: §3.1「AI/LLM・検索カテゴリの強制ルール」を新設。禁止事項に「Azure OpenAI Service の直接利用禁止」を追加。Microsoft Learn 根拠 URL を 4 件埋め込み（Microsoft Foundry overview / Foundry Agent Service overview / Microsoft Foundry architecture / Foundry IQ knowledge base 接続）。
- `.github/scripts/templates/asdw-web/step-2.2.md` / `.github/scripts/templates/asdw/step-2.2.md`: Prompt §3.1 強制ルールへの参照行を追加。

### Added — AAD-Web に追加 Azure サービス選定 Step.2.5 を新設

**概要**: AAD-Web（Web App Design）ワークフローに、`Dev-Microservice-Azure-AddServiceDesign` を使用する `Step.2.5 追加 Azure サービス選定` を新設。マイクロサービス定義書（Step.2.2）の完了後に走り、`docs/azure/azure-services-additional.md` を出力する。ASDW-WEB Step.2.2 と同 Agent を共有しているため、ワークフロー併用時の出力モードは `append` で揃えた。整合性レビュー（Step.3）とは独立観点として並列実行可能。

- `.github/scripts/templates/aad-web/step-2.5.md`: 新規テンプレ。
- `.github/io-contracts/Dev-Microservice-Azure-AddServiceDesign--aad-web--2.5.yaml`: 新規 I/O 契約（output `mode: append`、producer は ASDW-WEB 契約に整合）。
- `hve/workflow_registry.py`: AAD_WEB に `StepDef(id="2.5", custom_agent="Dev-Microservice-Azure-AddServiceDesign", depends_on=["2.2"], ...)` 追加。
- `users-guide/workflow-reference.md`: AAD-WEB ステップ数 6→7、Step.2.5 行追加。
- `hve/tests/test_workflow_registry.py`: `EXPECTED_STEP_COUNTS` / `EXPECTED_NON_CONTAINER_COUNTS` の `aad-web` を 6→7、`test_aad_web_dag_walk` の期待値を Step.2.5 並列実行に整合させて更新。

**検証**: `pytest -k "aad_web or workflow_registry"` で 242 PASS / 1 既存失敗（本変更と無関係、`git stash` で切り分け済）。Microsoft Learn 根拠 URL は `work/investigation-azure-genai-selection/learn-evidence.md` に記録。

**Notes**: 既存失敗 `hve/tests/test_gui_step2_refactor.py::test_aad_web_resource_group_hidden` は GUI 表示ロジックの課題であり本タスクスコープ外。`docs/azure/azure-services-additional.md` / `azure-services-data.md` / `service-catalog.md` の手修正は本タスクスコープ外（次回ワークフロー再実行時に新 Prompt で自動再生成される前提）。

### Changed — Deploy 系 Agent prompt の TDD 完了フロー必須化

**概要**: `hve` ワークフローで Azure Functions / Static Web Apps 等の deploy Step が「スクリプトと workflow YAML を作成しただけ」で success と扱われていた構造を是正。Deploy 系 Agent prompt に Pre-flight → RED → Deploy → GREEN の TDD サイクルを必須化し、`NEEDS-VERIFICATION` で逃げて Step を success にする運用を禁止した。

- `.github/prompts/Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.prompt.md`: A-pre (Pre-flight) と A-exec (RED→Deploy→GREEN) を `<task>` に追加。AC-3 / AC-9 を `✅` 必須化。`gh workflow run` 発火と `timeout 1800 gh run watch --exit-status --interval 10` の 30 分ハードタイムアウトを明示。`ac-verification.md` を 1 行 1 AC のテーブル形式必須化。
- `.github/prompts/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md`: 同等の TDD フロー必須化。AC-1 / AC-6 / AC-8 を `✅` 必須化。`verify-webui-resources.sh` に DNS/CDN 伝播対策のリトライ要件追記。
- `.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md`: §3.3.0 Pre-flight / §3.3.1 RED→Deploy→GREEN を追加。AC-1 を `✅` 必須化。§7.3 完了判定から「AC-1 が `⏳` のまま PR Ready for Review」を排除。
- `.github/prompts/Dev-Microservice-Azure-AgenticRetrievalDeploy.prompt.md`: §4.3.0 / §4.3.1 で TDD サイクル必須化。AC4B-1 を `✅` 必須化。
- `.github/prompts/Dev-Microservice-Azure-AgentDeploy.prompt.md`: §8 AC 表の `#` 列を `AC-ID`（AC-1〜AC-10）に置換。§4 に A-pre Pre-flight / A-exec RED→Deploy→GREEN を追記。AC-1 / AC-2 / AC-3 を `✅` 必須化。`ac-verification.md` をテーブル形式必須化。
- `.github/prompts/Dev-Microservice-Azure-DataDeploy.prompt.md`: §3 Execution Mode にステップ0 Pre-flight / ステップ0.5 RED / ステップ4.5 GREEN を追加。`<output_contract>` に AC 表（AC-1〜AC-5）を明記し AC-1 を `✅` 必須化。`ac-verification.md` をテーブル形式必須化。

### Changed — GUI 「実行中の課題」一覧に ツール失敗 行を表示

**概要**: `hve/console.py` の `tool_result(success=False)` が出力する `✗ [step] ツール失敗: <msg>` 行が GUI 「実行中の課題」ペインに表示されず、長時間ランの障害検知を実害として見逃していた問題を修正。

- `hve/gui/workbench_logger.py`: 新規パターン `_TOOL_FAILED_PATTERN` を追加し、`process_log_line` の elif チェーン末尾で `add_user_action(level="ERROR", category="ツール失敗")` を呼ぶようにした。既存 ERROR / Session error / Sub-agent 失敗 パターンと排他的に動作。
- `hve/tests/test_workbench_logger_tool_failed.py`: 新規 4 件のユニットテスト（step_id 付き/なし / タイムスタンプ付き / 標準ログパターンとの二重カウントなし）を追加。

### Added — Orchestrator Deploy Step AC 検証 gate

**概要**: Agent の自己申告 success と独立に、Orchestrator (`hve/runner.py`) が `ac-verification.md` を機械的に検査し、実在系 AC が `❌` / `⏳` / `NEEDS-VERIFICATION` のままなら Step を fail に降格する gate を追加。`[hve:fatal]` マーカーを発行し既存 `stop_on_fatal` 経路で後続 wave を停止させる。

- `hve/artifact_validation.py`: `validate_deploy_ac_verification(report_path, agent_name) -> list[str]` と allowlist 定数 `_DEPLOY_AGENT_REALITY_AC` を追加（対象 6 Agent: Compute / SWA / AddService / AgenticRetrieval / AgentDeploy / DataDeploy）。
- `hve/runner.py`: Step 完了直前の success 判定にフックを追加。Deploy 系 Agent のレポートを検証し、未達なら `console.error` + `[hve:fatal]` 発行 + `step_end(failed)`。allowlist 外 Agent は既存挙動不変。
- `hve/tests/test_artifact_validation_deploy_gate.py`: 6 Agent 全対応の 17 件ユニットテスト（allowlist 外 / report 不在 / 各対象 Agent の PASS・FAIL・行欠落ケース）。

**Notes**: `azure-ac-verification` Skill は routing 表に記載はあるが実ファイル不在。DataDeploy の AC 定義は AddService 形式を踏襲（最小セット AC-1〜AC-5）した。AgentDeploy / DataDeploy は前バージョンでは allowlist 外としていたが、本リリースで対応完了。

### Changed — AAS への共通設計引き上げ（サービス／データ／ペルソナ別画面の SoT 集約）

**概要**: 別 APP-ID 間で同じデータを管理するサービスが重複作成されるリスクを排除するため、AAS（Application Architecture Selection）に APP-ID 横断の共通設計（サービス・データモデル・ペルソナ別共通画面）を引き上げた。ADFD（Architecture Design - Dataflow）は独立カタログ生成を廃止し、AAS の共通カタログ（`docs/catalog/*`）を SoT として参照する構成へ再設計した。AAS には新たに Step.8（ペルソナ別共通画面カタログ）と Step.9（ペルソナカタログ）を追加し、Use Case Catalog のアクター記述を一次ソースとして横断ペルソナ・横断共通画面を一元定義できるようにした。

**変更内容**:

- **Added** — AAS テンプレートのバッチ補強注記（最小差分）
  - `.github/scripts/templates/aas/step-3.1.md`: バッチドメイン補強（冪等性・トランザクション境界・最終的一貫性・チェックポイント）
  - `.github/scripts/templates/aas/step-3.2.md`: サービス候補にバッチジョブ（非同期ジョブ）を含める注記
  - `.github/scripts/templates/aas/step-4.1.md`: データソース/デスティネーション統合の注記
  - `.github/scripts/templates/aas/step-6.md`: ジョブ DAG・スケジュール・リトライ戦略を統合する旨の注記（service-catalog-matrix）
  - `.github/scripts/templates/aas/step-7.md`: 冪等性テスト・データ品質テスト・大量データテスト方針の統合注記
- **Added** — AAS 新ステップ（Step.8 / Step.9）
  - `.github/scripts/templates/aas/step-8.md`（新規）：ペルソナ別共通画面カタログ生成
  - `.github/scripts/templates/aas/step-9.md`（新規）：ペルソナカタログ生成（Use Case Catalog アクター抽出）
  - `.github/prompts/Arch-UI-PersonaScreenList.prompt.md`（新規）：Step.8 用 Custom Agent
  - `.github/prompts/Arch-PersonaCatalog.prompt.md`（新規）：Step.9 用 Custom Agent
  - `hve/workflow_registry.py` の AAS `WorkflowDef` に Step.8 / Step.9 を追加（Step 数 8 → 11、Step.4 を 4.1/4.2 に分割）
  - `.github/workflows/auto-app-selection-reusable.yml` に Step.8 / Step.9 の `create_issue` 呼び出しと Sub-issue 紐付け追加
- **Changed** — AAS Step.4 のテンプレ不整合修正（Q8）
  - `auto-app-selection-reusable.yml` の Step.4 を Step.4.1 / Step.4.2 の 2 呼び出しに分割
  - `.github/scripts/templates/aas/step-4.1.md` / `step-4.2.md` の参照を正常化
- **Changed** — Custom Agent プロンプトの最小注記追加
  - `.github/prompts/Arch-Microservice-DomainAnalytics.prompt.md`: §4.1 バッチドメイン補強追加 + §5 集約欄追記
  - `.github/prompts/Arch-Microservice-ServiceIdentify.prompt.md`: §3 サービス候補にジョブを含める追記 + §B 詳細欄に「種別」追加
  - `.github/prompts/Arch-DataModeling.prompt.md`: ## 1. Overview にデータソース／デスティネーション統合注記
  - `.github/prompts/Arch-Microservice-ServiceCatalog.prompt.md`: Table C に「種別／スケジュール DAG／リトライ戦略」3 列追加 + §5.2 抽出手順 6 追加
  - `.github/prompts/Arch-TDD-TestStrategy.prompt.md`: ## 5.1 バッチ／データフロー処理テスト方針（該当 SVC のみ）追加 + §7 網羅性チェック・§10 完了条件に反映
- **Removed** — ADFD 旧 Step（独立カタログ生成）の廃止
  - `.github/scripts/templates/adfd/step-1.1.md` / `step-1.2.md` / `step-2.md` / `step-3.md` / `step-4.md` / `step-5.md` を削除（6 ファイル）
  - `.github/prompts/Arch-Dataflow-DomainAnalytics.prompt.md` / `Arch-Dataflow-DataSourceAnalysis.prompt.md` / `Arch-Dataflow-DataModel.prompt.md` / `Arch-Dataflow-AppCatalog.prompt.md` / `Arch-Dataflow-ServiceCatalog.prompt.md` / `Arch-Dataflow-TestStrategy.prompt.md` を削除（6 ファイル）
  - `.github/io-contracts/Arch-Dataflow-DomainAnalytics--adfd--1.1.yaml` / `DataSourceAnalysis--adfd--1.2.yaml` / `DataModel--adfd--2.yaml` / `AppCatalog--adfd--3.yaml` / `ServiceCatalog--adfd--4.yaml` / `TestStrategy--adfd--5.yaml` / `DomainAnalytics.yaml`（無サフィックス版） / `DataSourceAnalysis.yaml`（無サフィックス版）を削除（8 ファイル）
  - `auto-dataflow-design-reusable.yml` から旧 Step.1.1〜5 の `BODY_S*` 生成と `create_issue` 呼び出しを削除（約 150 行削減）
  - ADFD ステップ数: 9 → 3（現行は Step.6.1 / Step.6.2 / Step.6.3 のみ）
- **Changed** — ADFD 残存ステップ（Step.6.1 / 6.2 / 6.3）の入力切替
  - `.github/io-contracts/Arch-Dataflow-AppSpec--adfd--6.1.yaml` / `MonitoringDesign--adfd--6.2.yaml` / `TDD-TestSpec--adfd--6.3.yaml` の `inputs.producers` を AAS 出力（`Arch-Microservice-ServiceCatalog` / `Arch-DataModeling` / `Arch-TDD-TestStrategy` 等）参照に更新
  - `hve/workflow_registry.py` 内の `output_paths_template` を `{key}-spec.md` / `{key}-test-spec.md` に統一（fanout エンジンの `{key}` 単独置換制約に合わせる。io-contract YAML 側は人間可読のメタ表現として `{appId}` を別レイヤーで保持）
- **Changed** — ADFD fanout 単位を JOB-* から APP-* に変更
  - `hve/catalog_parsers.py` `parse_dataflow_catalog`（行 262〜）: 入力を `docs/catalog/app-arch-catalog.md`（優先） + `docs/catalog/app-catalog.md`（フォールバック）に変更し、`hve/app_arch_filter.py` の `resolve_app_arch_scope` を適用してデータフロー APP のみ抽出
- **Changed** — 自己改善対象 Agent リスト更新
  - `hve/self_improve.py` の `_WORKFLOW_AGENT_MAP["adfd"]`（行 69〜）を `Arch-Dataflow-AppSpec` / `Arch-Dataflow-MonitoringDesign` / `Arch-Dataflow-TDD-TestSpec` の 3 件に更新
- **Changed** — 周辺レジストリ・Issue Template の Step 定義同期
  - `.github/ISSUE_TEMPLATE/app-architecture-design.yml` / `dataflow-design.yml` のチェックボックス項目を新 Step 構成に同期
  - `.github/scripts/bash/lib/workflow-registry.sh` / `.github/scripts/powershell/lib/workflow-registry.ps1` の AAS / ADFD Step 定義を新構成に同期
- **Changed** — users-guide / README への反映
  - `users-guide/04-app-design-dataflow.md` 冒頭に「ADFD 構成変更の移行ノート」を追加（旧 9 ステップ記述・SVG 図・依存グラフ・ステップ表・手動／自動実行ガイド配下の Step.1.1〜5 説明が未更新であることを明示）
  - `users-guide/06-app-dev-dataflow-azure.md` 冒頭に同移行ノート追加（ADFDV は旧 `dataflow-*.md` を必須依存に持つため追従修正が未完了）
  - `users-guide/workflow-reference.md` の Step 数表を更新（AAS: 8 → 11、ADFD: 9 → 3）。`auto-dataflow-design` ラベル説明（行 266）の「Step.1.1〜6.3」も「Step.6.1〜6.3」に修正
  - `README.md` 行 104 の Custom Agent 例示 `Arch-Dataflow-AppCatalog`（削除済）を `Arch-Dataflow-AppSpec` に置換

**テスト**:
- `hve/tests/test_fanout.py`: `parse_dataflow_catalog` 単体テスト 2 件 + ADFD 結合テスト 2 件を追加
- `hve/tests/test_template_engine.py`: `TestResolveSelectedSteps` の 2 件で Step.8 / Step.9 を含む期待値に更新
- 本タスクで触れた関連テストは PASS。全体回帰実行（`python -m pytest hve/tests/`）は未実施。スコープ外既知バグ（後述）への影響なし。

**動作確認**:
- YAML 構文チェック: `.github/workflows/` 配下の 55 YAML すべて `yaml.safe_load` OK
- テンプレ参照整合性: AAS 11 ステップ（Step.8/9 を含む）のテンプレファイル実在を手元作業ツリーで確認。ADFD は Step.6.1/6.2/6.3 のみ実在。なお `hve/tests/test_aas_template_parity.py` の依存参照・placeholder・rendering 固定リスト検証（`_AAS_STEP_DEPENDENCY_PATTERNS` 経由）は Step.1〜7 のみを対象とし、Step.8/9 は対象外。一方 StepDef 経由のテンプレ存在 (`TestAasStepDefBodyTemplatePath`) / Custom Agent 一致 (`TestAasStepDefCustomAgentConsistency`) / output_paths (`TestAasStepDefOutputPaths`) の各テストは `for step in AAS.steps` で Step.8/9 も含む全ステップを検証している。
- `auto-dataflow-design-reusable.yml` Step.6.1〜6.3 の Issue body 内入力欄が `docs/catalog/*`（AAS 出力）参照に切り替わっていることを確認

**Known Issues / Future Work（残存技術的負債）**:
- **ADFDV ワークフロー (`auto-dataflow-dev-reusable.yml` / `hve/workflow_registry.py` の `ADFDV`)** は旧 `docs/dataflow/dataflow-domain-analytics.md` / `dataflow-data-model.md` / `dataflow-app-catalog.md` / `dataflow-service-catalog.md` / `dataflow-test-strategy.md` を `required_artifacts` として要求している。さらに `.github/io-contracts/Dev-Dataflow-DataServiceSelect--adfdv--1.1.yaml` / `Dev-Dataflow-DataDeploy--adfdv--1.2.yaml` / `Dev-Dataflow-TestCoding--adfdv--2.1.yaml` / `Dev-Dataflow-ServiceCoding--adfdv--2.2.yaml` / `Dev-Dataflow-FunctionsDeploy--adfdv--3.yaml` 等の io-contract や対応する prompt が、削除済の `Arch-Dataflow-*--adfd--1.1〜5`（`AppCatalog--adfd--3` / `ServiceCatalog--adfd--4` 等）を producer として参照したままになっている。本タスクでは ADFD 上流を削除したため、ADFDV を AAS 共通カタログ（`docs/catalog/*`）＋ per-job 詳細（`docs/dataflow/apps/*.md`）参照に追従修正する必要がある（別タスクで実施）。
- **`users-guide/04-app-design-dataflow.md` / `06-app-dev-dataflow-azure.md`** の本文内ステップ表・依存グラフ・各 Step 詳細セクション・SVG 図（`chain-adfd.svg` / `infographic-adfd.svg` / `orchestration-task-data-flow-adfd.svg`）は旧 9 ステップ構成のまま未更新。冒頭の移行ノートで「未更新」を明示済み。SVG 更新を含む詳細書き換えは別タスクで実施予定。
- **`hve/tests/test_aas_template_parity.py`** の依存参照・placeholder の固定リスト検証 (`_AAS_STEP_DEPENDENCY_PATTERNS`) は Step.1〜7 のみを対象としており、Step.8（ペルソナ別共通画面）と Step.9（ペルソナカタログ）の依存参照・placeholder の自動検証は別タスクで追加予定。
- **`.github/scripts/powershell/tests/workflow-registry.Tests.ps1`** 行 60 で削除済の旧 ADFD `Step.1.1` (`Arch-Dataflow-DomainAnalytics`) を参照しているテストが残存。テスト実行時にエラーになる。本タスクスコープ外として残置。
- **`tools/fill_agent_skills.py`** 行 45-65 で削除済の `Arch-Dataflow-DomainAnalytics` / `Arch-Dataflow-DataSourceAnalysis` / `Arch-Dataflow-DataModel` / `Arch-Dataflow-AppCatalog` / `Arch-Dataflow-ServiceCatalog` / `Arch-Dataflow-TestStrategy` 6 件を参照する自動化スクリプトが残存。本タスクスコープ外として残置。
- 既存バグ（本タスク以前から存在、スコープ外）: `hve/tests/test_fanout.py::test_aad_collect_params_with_multiple_app_ids`（`StopIteration`）、`hve/tests/test_orchestrator.py::TestRunWorkflowSelfImprove` 5 件。

**スコープ外（既知）**:
- 既存 `docs/` 配下のカタログファイル（`docs/dataflow/dataflow-*.md` 等）の物理削除は行っていない。ワークフロー再実行で再生成される前提により、AAS 出力（`docs/catalog/*`）が SoT となった以降は旧ファイルは参照されなくなる。
- ペルソナ別共通画面（Step.8）の出力 `docs/catalog/persona-screen-catalog.md` は単一ファイル（APP-ID 横断）。APP 固有の画面詳細は AAD-WEB の `Arch-UI-List` / `Arch-UI-Detail` が引き続き担当する。

---

### Changed — ASDW-WEB の TDD テスト仕様生成ステップ (`Step.2.3T` / `Step.3.0T`) を AAD-WEB に移動

**概要**: 設計フェーズで作成すべき TDD RED テスト仕様書を、開発フェーズ (ASDW-WEB) から設計フェーズ (AAD-WEB) に移動。AAD-WEB の `Step.2.3` (サービス別 TDD テスト仕様書) と `Step.2.4` (画面別 TDD テスト仕様書、新規) として再配置し、並列実行可能とした。これによりテスト仕様の役割と作成タイミングが本来の TDD フローと一致する。

**変更内容**:

- **Removed**: ASDW-WEB から以下を削除
  - `Step.2.3T` (サービス TDD テスト仕様書) — `templates/asdw-web/step-2.3T.md` + `io-contracts/Arch-TDD-TestSpec--asdw-web--2.3T.yaml`
  - `Step.3.0T` (UI TDD テスト仕様書) — `templates/asdw-web/step-3.0T.md` + `io-contracts/Arch-TDD-TestSpec--asdw-web--3.0T.yaml`
  - ASDW-WEB の step 数: 20 → 18

- **Added**: AAD-WEB に画面別 TDD テスト仕様書ステップを新規追加
  - **[`Step.2.4`](.github/scripts/templates/aad-web/step-2.4.md)** (画面別 TDD テスト仕様書): `Arch-TDD-TestSpec` Custom Agent、`Step.2.1` (画面定義書) のみ依存、画面ごとに fan-out。
  - **[`.github/io-contracts/Arch-TDD-TestSpec--aad-web--2.4.yaml`](.github/io-contracts/Arch-TDD-TestSpec--aad-web--2.4.yaml)**: I/O contract 新規作成。
  - AAD-WEB の step 数: 5 → 6 (`Step.2.4` 追加)。

- **Changed**: AAD-WEB `Step.2.3` をサービス専用に変更
  - 依存関係: 旧 `[2.1, 2.2]` (AND join) → 新 `[2.2]` のみ
  - `consumed_artifacts`: `screen_specs` を削除（`Step.2.4` に分離）
  - `Step.2.3` と `Step.2.4` は **並列実行可能** (依存元が異なる)

- **Changed**: 関連リソースを新構造に同期
  - **Workflow YAML**: `.github/workflows/auto-app-detail-design-web-reusable.yml` に `S24_*` 系処理追加、`.github/workflows/auto-app-dev-microservice-web-reusable.yml` から `S23T_` / `S30T_` 系処理削除。
  - **Issue Template**: `.github/ISSUE_TEMPLATE/web-app-design.yml` にチェックボックス `Step.2.4` 追加、`.github/ISSUE_TEMPLATE/web-app-dev.yml` から `Step.2.3T` / `Step.3.0T` チェックボックス削除。
  - **Python Registry**: `hve/workflow_registry.py` の `AAD_WEB` に `Step.2.4` 追加、`ASDW_WEB` から `Step.2.3T` / `Step.3.0T` 削除。
  - **Prompts/Templates**: `Arch-TDD-TestSpec.prompt.md` と `templates/aad-web/step-2.3.md` を「サービス専用」に明確化。

- **Changed**: users-guide とビジュアル資産を更新
  - `users-guide/03-app-design-microservice-azure.md` (AAD-WEB ガイド) に `Step.2.4` 行追加 + 依存グラフ更新。
  - `users-guide/05-app-dev-microservice-azure.md` (ASDW-WEB ガイド) から `Step.2.3T` / `Step.3.0T` 削除 + 依存グラフ更新。
  - `users-guide/workflow-reference.md` で AAD-WEB step 数 4→5 / ASDW-WEB step 数 20→18 に修正。
  - SVG 5 ファイル更新: `chain-aad-web.svg`, `chain-asdw.svg`, `infographic-aad-web.svg`, `orchestration-task-data-flow-aad-web.svg`, `orchestration-task-data-flow-asdw.svg`。

**テスト**:
- `hve/tests/test_workflow_registry_agentic.py`: AAD-WEB Step.2.3/2.4 の独立依存性を検証する 6 テストに更新 (旧 AND join 前提のテストは削除)。
- `hve/tests/test_orchestrator.py`: `test_aad_web_step2_3_consumed_artifacts_include_service_specs` と `test_aad_web_step2_4_consumed_artifacts_include_screen_specs` に分割。
- `pytest hve/tests/ -k "aad_web"` で 18 件 PASS (回帰ゼロ)。

**動作確認**:
- YAML 構文チェック: `yaml.safe_load` で 6 ファイル (workflows 4 + Issue Template 2) OK。
- registry 整合性: AAD-WEB step 数 6, ASDW-WEB step 数 18 (`hve/workflow_registry.py` の登録ステップ数と一致)。
- ドキュメント・SVG・Workflow YAML・Python Registry の 4 系統で `Step.2.4` (新規) と `Step.2.3` (サービス専用化) が整合。

**スコープ外（既知）**:
- `.github/scripts/templates/asdw/` (レガシー ASDW テンプレート、Web 含まない旧仕様) に `Step.2.3T` / `Step.3.0T` 参照が残存。当該ディレクトリは現在の workflow yaml から呼び出されていない死蔵ファイル群のため本タスクスコープ外。
- AAD-WEB の `Step.3` (画面 ↔ サービス整合性レビュー, `QA-DocConsistency`) は `hve/workflow_registry.py` に登録されているが、`.github/ISSUE_TEMPLATE/web-app-design.yml` と `users-guide/03-app-design-microservice-azure.md` には記載がない。これは本タスク以前から存在する整合性問題で、`workflow-reference.md` のみ実数 6 ステップで記述するに留めた。

---

### Added — `mdq` に `graphrag` 戦略を追加（任意・LLM 必須、商用利用可能な LightRAG ベース）

**概要**: `markdown-query` Skill の `mdq` CLI に、エンティティ関係グラフを使った検索戦略 `graphrag` を追加した。バックエンドは商用利用可能な OSS の [LightRAG (lightrag-hku, MIT)](https://github.com/HKUDS/LightRAG) を採用し、独自実装は行わない。既定の SQLite-backed 戦略（`heading` / `semantic_paragraph` / `pageindex` 等）はそのまま動作し、`graphrag` は **任意の追加戦略** として `--strategy graphrag` 明示時のみ起動する（`--strategy auto` の候補には含めない）。

**追加された機能**:
- **[`mdq/strategies_graphrag.py`](mdq/strategies_graphrag.py)**: LightRAG への adapter（`GraphRAGConfig` dataclass、`insert_paths_sync` / `query_sync` 関数、`ALLOWED_QUERY_MODES = {"local", "naive"}` のクエリモード allow-list）。
- **[`mdq/graphrag_runtime.py`](mdq/graphrag_runtime.py)**: LightRAG が要求する LLM completion / embedding callable のファクトリ。Ollama HTTP backend（`urllib` ベース、loopback 限定）と決定論的な `mock` backend（CI / オフラインテスト用）を提供。
- **[`mdq/indexer.py`](mdq/indexer.py)**: `build_graphrag_index()` 関数を追加（LightRAG working_dir への索引化）。
- **[`mdq/cli.py`](mdq/cli.py)**: `index` / `search` サブコマンドに `graphrag` 早期分岐を追加（SQLite 接続を完全スキップ）。CLI フラグ: `--graphrag-working-dir` / `--graphrag-llm-provider` (`ollama` | `mock`) / `--graphrag-llm-model` / `--graphrag-embed-provider` / `--graphrag-embed-model` / `--graphrag-base-url` / `--graphrag-allow-remote-ollama` / `--graphrag-timeout` / `--graphrag-query-mode` (`local` | `naive`) / `--graphrag-top-k`。

> 注: `[project.optional-dependencies] graphrag = ["lightrag-hku>=1.4.16,<1.5"]` は本タスク以前の準備コミットで `pyproject.toml` に既に追加されており、本リリースでは変更していない。

**セキュリティ・運用上の制約**:
- Ollama backend は loopback 限定（`127.0.0.1` / `localhost` / `[::1]` のみ）。非 loopback URL は `mdq/graphrag_runtime.py` の `GraphRAGRuntimeUnavailable`（CLI 出力時は `mdq/strategies_graphrag.py` で `GraphRAGUnavailable` にラップ）で拒否し、`--graphrag-allow-remote-ollama` を併用した場合のみ `RuntimeWarning` 付きで許可する。
- `lightrag.llm.*` 配下のモジュールは **一切 import しない**（pipmaster の自動 `pip install` 副作用を回避）。LLM/embedding callable は `mdq` 側 adapter で完全制御する。
- LightRAG は lazy import（`mdq.strategies_graphrag` / `mdq.indexer` 内の関数本体内）で、graphrag extras 未インストール環境では他の戦略が影響を受けない。
- `QueryParam(mode=..., enable_rerank=False)` を明示し、rerank 警告を抑止 + global / hybrid / mix 等の禁止モード呼び出しを防ぐ。
- `build_graphrag_index(..., rebuild=True)` は LightRAG マーカーファイル（`kv_store_doc_status.json` / `vdb_entities.json` / `graph_chunk_entity_relation.graphml` 等）を含まない既存ディレクトリの削除を `ValueError` で拒否し、`--graphrag-working-dir` の誤指定による無関係ディレクトリ破壊を防ぐ（空ディレクトリは許可）。

**テスト**: 新規 68 件 PASS（[`mdq/tests/test_graphrag_runtime.py`](mdq/tests/test_graphrag_runtime.py) 42 件、[`mdq/tests/test_strategies_graphrag.py`](mdq/tests/test_strategies_graphrag.py) 19 件、[`mdq/tests/test_search_graphrag.py`](mdq/tests/test_search_graphrag.py) 7 件、うち 2 件は `build_graphrag_index(..., rebuild=True)` のディレクトリ削除安全性回帰テスト）。各テストは冒頭で `pytest.importorskip("numpy")` / `pytest.importorskip("lightrag")` を呼び、graphrag extras 未インストール環境ではモジュール全体をスキップする。

**ドキュメント**:
- 新規 [`.github/skills/markdown-query/references/graphrag-strategy.md`](.github/skills/markdown-query/references/graphrag-strategy.md): 戦略の詳細仕様（アルゴリズム / CLI フラグ / mock provider / セキュリティ制約 / 制限事項 / 既定値の出典）。
- 更新 [`.github/skills/markdown-query/SKILL.md`](.github/skills/markdown-query/SKILL.md): Non-goals に「graphrag は SQLite-backed 戦略のドロップイン置換ではない」を追記。詳細ガイドに graphrag-strategy.md へのリンクを追加。
- 更新 [`.github/skills/markdown-query/references/language-and-strategy.md`](.github/skills/markdown-query/references/language-and-strategy.md): 戦略一覧表に `graphrag` 行を追加し、表後の注記で別系統である旨を明示。
- 更新 [`.github/skills/markdown-query/references/query-routing.md`](.github/skills/markdown-query/references/query-routing.md): auto router の候補外であることを明記。
- 更新 [`users-guide/skills-markdown-query.md`](users-guide/skills-markdown-query.md): §3.4 を新設し、利用者向けに graphrag の特性・インストール・CLI 例・制約を要約。

**動作確認**:
- `python -m pytest mdq/tests/ -q`: 148 PASS（既存 80 件 + 新規 68 件、回帰ゼロ）。
- `python -m mdq index --strategy graphrag --graphrag-llm-provider mock --graphrag-embed-provider mock`: 索引化 OK、SQLite ファイルは作成されない（`.mdq/graphrag-<lang>/` 配下のみ書き込み）。
- `python -m mdq search --strategy graphrag --q "..." --graphrag-llm-provider mock --graphrag-embed-provider mock`: 検索 OK、JSON ライン形式で `{"strategy", "mode", "top_k", "answer"}` を返却。

---

### Fixed — Skills 読み込みの 2 件のエラー（`_routing/SKILL.md` 不正な Skill 名 / `markdown-query/SKILL.md` description 文字数超過 + BOM）

**根本原因**:
- **`_routing/SKILL.md`**: Skill ローダーは先頭アンダースコア (`_`) で始まる Skill 名を不正と判定して読み込みを拒否する。既存規約（例: `_evals/` は README.md のみ保持）と整合させるため、`_routing` ディレクトリも README.md 化が必要だった。
- **`markdown-query/SKILL.md`**: (1) description が 1085 文字で 1024 文字上限を超過し `validate-skills.py` でエラーになっていた。(2) ファイル先頭に BOM (U+FEFF) が混入しており `validate-skills.py` の frontmatter 検出 (`startswith("---\n")` 判定) を破って `MISSING_FRONTMATTER` も同時に発生させていた。

**修正内容**:
- **[`.github/skills/_routing/SKILL.md` → `.github/skills/_routing/README.md`](.github/skills/_routing/README.md)**: `git mv` でリネーム (SHA256 一致、内容無変更)。Skill ローダーの対象外化。
- **[`.github/scripts/validate-skill-routing.py`](.github/scripts/validate-skill-routing.py)**: モジュール docstring と `DEFAULT_ROUTING` 定数を `_routing/README.md` に更新。
- **[`.github/scripts/tests/test_validate_skill_routing.py`](.github/scripts/tests/test_validate_skill_routing.py)**: 5 箇所の fixture パスを `_routing/README.md` に置換。
- **[`mdq/usage_stats.py`](mdq/usage_stats.py)** + **[`tools/skills/markdown_query/vendor/mdq/usage_stats.py`](tools/skills/markdown_query/vendor/mdq/usage_stats.py)** (vendor SYNC.md 規約準拠の同期コピー): `_check_skill_routing_listed()` が読み取る routing ファイルパスを `_routing/README.md` に更新（リネームによる機能回帰防止）。
- **[`hve/tests/test_mdq_usage_stats.py`](hve/tests/test_mdq_usage_stats.py)**: `test_a4_skill_routing_listed_true` の fixture パスを `_routing/README.md` に更新。
- **[`.github/copilot-instructions.md`](.github/copilot-instructions.md)** §2: 文言を「Skill `_routing`」→「ルーティング表」、`SKILL.md` → `README.md` に更新。
- **[`.github/skills/CONTRIBUTING.md`](.github/skills/CONTRIBUTING.md)** 5 箇所: 新規 Skill 投稿者向けガイドのルーティング登録先パスを `_routing/README.md` に統一。
- **users-guide 系 3 ファイル**（[`users-guide/skills-markdown-query.md`](users-guide/skills-markdown-query.md), [`users-guide/hve-cloud-getting-started.md`](users-guide/hve-cloud-getting-started.md), [`users-guide/hve-cli-orchestrator-guide.md`](users-guide/hve-cli-orchestrator-guide.md)）+ ADR テンプレート（[`template/decisions/ADR-0001-agentic-retrieval-prerequisites.md`](template/decisions/ADR-0001-agentic-retrieval-prerequisites.md)）+ `_routing/README.md` 内の自己参照 1 箇所: パス記述を `_routing/README.md` に統一。
- **[`.github/skills/markdown-query/SKILL.md`](.github/skills/markdown-query/SKILL.md)**: (1) ファイル先頭 BOM (U+FEFF) を除去、(2) description を 1085 → 1002 文字に軽圧縮（4 構造 `USE FOR` / `PREFER OVER` / `DO NOT USE FOR` / `WHEN` と全トリガー語を温存。冗長表現のみ削減: 「repository documentation」→「repo docs」、PREFER OVER 節の補助節を簡潔化）。CRLF 改行は維持。

**動作確認**:
- `python .github/scripts/validate-skills.py`: `markdown-query` の `Description exceeds 1024 chars` および `MISSING_FRONTMATTER` 両エラーが解消（markdown-query 関連エラー 0 件）。
- `python .github/scripts/validate-skill-routing.py`: ベースライン 24 件のうち本タスクで対象とした 1 件（`_routing` ローディング）が解消。残存 23 件は azure-skills 系 `MISSING_REFERENCE`（本タスクスコープ外）のみで回帰ゼロ。
- `python -m pytest .github/scripts/tests/test_validate_skill_routing.py` 5/5 PASS（fixture パス更新後の回帰なし）。
- `python -m pytest hve/tests/test_mdq_usage_stats.py` 28/28 PASS（fixture と実コード両方を `_routing/README.md` に同期更新後）。

### Fixed — GUI Footer の Elapsed カウンタが全タスク完了後もカウントアップを停止しない問題

**根本原因**: `hve/gui/workbench_widgets.py` の `FooterWidget._update()` (修正前 Elapsed 計算行) で Workflow Elapsed を `now - self.state.workflow_started_at` で算出していたため、`WorkbenchState.mark_all_done()` / `mark_aborted()` で `all_done=True` および `task_tree.root.finished_at` が設定された後も、1Hz の QTimer により呼ばれる `_update()` が常に `now` を参照し、カウントが進み続けていた。同様に Step Elapsed も完了 Step に対して `now` を参照していた。さらに `WorkbenchState.set_step_status(step_id, "done")` は `StepView.finished_at` を更新せず `SimpleTaskNode.finished_at` (task_tree のノード) のみを更新する仕様 (`workbench_state.py` L.586/L.594) であるため、Step Elapsed フリーズには `state.task_tree.get(step_id).finished_at` 経路の参照が必須だった。

**修正内容**:
- **[hve/gui/workbench_widgets.py](hve/gui/workbench_widgets.py)** (`FooterWidget._update`):
  - **Workflow Elapsed**: `getattr(self.state, "all_done", False)` が True の場合、`state.task_tree.root.finished_at` を `end_time` として固定し、`elapsed = max(0.0, end_time - workflow_started_at)` でカウントを停止する。`root.finished_at` が None の異常経路は安全側として `now` にフォールバックする (例外を出さない防御)。
  - **Step Elapsed**: 表示中 Step (`current_running_step_id` or `last_known_step_id`) の `task_tree.get(step_id).finished_at` を **優先参照** し、未設定なら `StepView.finished_at` をフォールバック参照する (将来の経路追加用)。両方 None なら `now` を使用 (実行中は従来通り増加)。

**動作確認**:
- 新規回帰テスト 8 件 PASS (`hve/gui/tests/test_footer_elapsed_freeze.py`):
  - `test_elapsed_continues_before_mark_all_done` (対照: 実行中はカウント継続)
  - `test_elapsed_freezes_after_mark_all_done` (主要回帰)
  - `test_elapsed_freezes_after_mark_aborted` (abort 経路)
  - `test_elapsed_freezes_with_delayed_update_after_mark_all_done` (完了後初回 _update を遅延させる強化ケース)
  - `test_elapsed_continues_when_all_done_without_root_finished_at` (異常経路の挙動 documentation)
  - `test_step_elapsed_freezes_after_step_done` (CRITICAL: task_tree 経由フリーズ)
  - `test_step_elapsed_continues_when_running` (対照: Step 実行中はカウント継続)
  - `test_step_elapsed_freezes_with_delayed_update_after_step_done` (Step 完了後初回 _update を遅延させる強化ケース)
- `time.monotonic` を `monkeypatch` で仮想時間に置換し、フリーズ動作を決定論的に検証。
- 既存 Footer 関連テスト 14 件 (`hve/gui/tests/test_footer_stats.py`) も全 PASS、回帰なし。
- 合計 22 passed in 0.24s。
- 修正対象ファイルへのスタッシュ退避による事前検証で、本変更のスコープ外で発生している 9 件の事前 failure (`test_page_workbench_*`) と本修正の無関係性を確認済み。

### Added — GUI 統計情報「今回の実行履歴」タブに AI Credit 列と CSV クリップボードコピー機能を追加

**目的**: ユーザーが Step / Workflow ごとの AI Credit (AIU) 消費量を一覧で確認し、ツリー全体を CSV としてコピペで外部ツール (Excel / スプレッドシート / 課金分析) に取り込めるようにする。

**変更内容**:
- **[hve/gui/stats_history_view.py](hve/gui/stats_history_view.py)**:
  - ツリーに AI Credit 列を新設（表示上は左から 5 列目、内部定数 `COL_AI_CREDIT = 4`）。Workflow 親行は `WorkflowStatsSnapshot.sdk_aiu_total_nano` を AIU 単位で累積表示し、Step 子行は累積 + 直前 Step との差分を `0.0123 (+0.0045)` 形式で表示する。差分は `finished_at` 昇順で「全 Workflow 横断の直前 Step」との隣接差分を計算する (`_step_aiu_delta_nano` + `_compute_step_prev_map`)。`WorkbenchState.sdk_aiu_total_nano` は Workflow 切替時にもリセットされない通算累積のため、Workflow 跨ぎでも前 Step との差分を取らないと 2 つ目以降の Workflow の最初 Step に前 Workflow 分が混入してしまうことに対応。
  - 数値ソート対応のため `_StatsTreeItem(QTreeWidgetItem)` サブクラスを追加。AI Credit 列のみ Qt.UserRole に nano 値を格納して数値比較し、他列はデフォルトの text 比較を実装する (`super().__lt__()` 呼び出しは無限再帰のため使用不可)。ソートキーは `_aiu_sort_key()` で `None / 0 / 負値` を全て `-1` に統一し、表示の `-` と整合させる。
  - ツリー上部にヘッダ行を追加: 凡例ラベル「累積 (+差分 / 並列実行時は隣接 Step との差分のため目安)」と既存 `CopyButton` (📋 アイコン) を配置。クリックで全行 (Workflow 親 + Step 子フラット) を 14 列 CSV としてクリップボードへコピーする。
  - CSV 生成は `build_csv(history, now_monotonic=None)` 関数に分離。`now_monotonic` を指定すると `running` 中 Workflow の経過秒計算も決定的になり、テスト容易性が高い (`None` 既定では `time.monotonic()` を呼ぶ)。`csv.writer` + `QUOTE_MINIMAL` + `\r\n` で出力し、テキスト列には CSV formula injection 対策 (`=+-@\t\r` 始まりに `'` プレフィックス) を全列適用する。
  - 14 列: `Type, Workflow, Step, Context, Limit, Pct, Model, ElapsedSec, ElapsedHMS, AiuTotal, AiuDeltaSincePrev, ToolsTop, SkillsTop, Status`。
  - 未取得値の表示規約: UI は `-`、CSV は空欄。`sdk_aiu_total_nano` が `None` / `0` / 負値の場合は未取得扱いとする (`_fmt_aiu` / `_csv_aiu` / `_aiu_sort_key`)。
- **[hve/gui/tests/test_stats_history_view.py](hve/gui/tests/test_stats_history_view.py)**:
  - 新規テスト 39 件を追加 (フォーマッタ / ソート・差分計算 / `_compute_step_prev_map` / `_aiu_sort_key` / View セル描画 / CSV ヘルパー / `build_csv` 統合 / View 経由 CSV エクスポート)。
  - エッジケース: ゼロ差分・並列実行 (`finished_at` 同値)・複数 Workflow 横断 (累積動作前提)・カンマや改行を含むセル値・全列 sanitize・未取得値混在・大量データ (50 Workflow × 10 Step) を網羅。
  - `csv.reader(io.StringIO(...))` を使い引用内改行の保持を厳密に検証する。

**動作確認**:
- 新規 39 件 + 既存 10 件 = `hve/gui/tests/test_stats_history_view.py` 全 49 件 PASS。
- Stats 関連テスト 5 ファイル (`test_stats_history_view.py`, `test_stats_history_store.py`, `test_stats_history_state.py`, `test_stats_detail.py`, `test_stats_detail_popup_scroll.py`) 合計 78 件 PASS。
- バックエンド改修不要 (既存 `StepStatsSnapshot.sdk_aiu_total_nano` / `WorkflowStatsSnapshot.sdk_aiu_total_nano` をそのまま利用)。

### Fixed — GUI 「作業状況」DAG ウィジェットで Step / Workflow ノードのダブルクリック時に stderr へ shiboken RuntimeError が出力される問題

**根本原因**: `_StepNodeItem.mouseDoubleClickEvent` (`hve/gui/widgets/dag_status_widget.py` L.291-296) および `_WorkflowHeaderItem.mouseDoubleClickEvent` (L.449-451) 内で、`self._widget._toggle_step_expand(...)` / `self._widget._toggle_workflow(...)` が `DagStatusWidget._relayout()` → `self._scene.clear()` を呼び出す。これによりシーン上の全 `QGraphicsItem`（イベント処理中の `self` を含む）の C++ オブジェクトが破棄される。その後同メソッド内で `super().mouseDoubleClickEvent(event)` を呼ぼうとして shiboken が `RuntimeError: libshiboken: Internal C++ object (_StepNodeItem / _WorkflowHeaderItem) already deleted.` を投げていた。GUI 挙動自体には影響しないが stderr にエラースタックトレースのノイズが出ていた。

**修正内容**:
- **[hve/gui/widgets/dag_status_widget.py](hve/gui/widgets/dag_status_widget.py)**:
  - `_StepNodeItem.mouseDoubleClickEvent`: Fanout を持つ場合 (`self._fanout_total is not None`) は `_toggle_step_expand` 呼び出し後に `return` し super を呼ばないよう変更。Fanout を持たない場合は従来通り `super().mouseDoubleClickEvent(event)` に委譲（コメントを「Fanout を持たない Step ノードでは展開処理はせず、既定のクリック処理に委ねる」に書き換え、実装との整合性を確保）
  - `_WorkflowHeaderItem.mouseDoubleClickEvent`: `_toggle_workflow` 後の `super().mouseDoubleClickEvent(event)` 呼び出しを削除（Workflow ヘッダ側は分岐なしのため無条件で super 省略）
  - 両メソッドに「`_relayout` → `scene.clear()` で self の C++ オブジェクトが破棄されるため super を呼んではならない (shiboken: Internal C++ object already deleted を回避)」旨のコメントを追加

**動作確認**:
- 新規回帰テスト 3 件 PASS (`hve/gui/tests/test_dag_status_widget.py`):
  - `test_step_node_double_click_with_fanout_does_not_raise_runtime_error`
  - `test_step_node_double_click_without_fanout_does_not_raise_runtime_error`
  - `test_workflow_header_double_click_does_not_raise_runtime_error`
- 修正前コードに一時 revert した状態で新規 2 テスト（fanout あり Step / Workflow ヘッダ）が期待通り `RuntimeError: libshiboken: Internal C++ object (_StepNodeItem/_WorkflowHeaderItem) already deleted.` で FAIL することを確認。修正後コードで再度 18 件全 PASS を確認（バグ検出能力の実証）
- `hve/gui/tests/test_dag_status_widget.py` 全 18 件 PASS (既存 15 件 + 新規 3 件)
- `DagStatusWidget` を直接 import / 文字列参照しているテストファイル群（7 ファイル）合計 **33 passed, 5 skipped, 0 failed** (`test_dag_status_widget.py`, `test_activity_status_multi_workflow.py`, `test_activity_status_widget_timing.py`, `test_autopilot_prepopulate_tree.py`, `test_phase2_container_nest_subtask.py`, `test_workbench_multi_workflow.py`, `test_workbench_no_hscroll.py`)

### Fixed — GUI Step 1 で APP-ID を 1 件選択しても Step 2 で全 APP-ID が並列実行されるバグ

**根本原因**: 2 経路の合成バグ。

1. **orchestrator 後方互換 fallback**: `hve/orchestrator.py` L3101-3156 の「推薦アーキテクチャ APP-ID フィルタ」で `effective_params.get("app_ids")` および `get("app_id")` が共に空の場合、`resolve_app_arch_scope(requested_app_ids=None)` が catalog 対象 kind の全 APP-ID を返却 (CLI で `--app-ids` 省略時の従来挙動)。L3126 で `effective_params["app_ids"]` を全 APP-ID で上書き → L3242 `_expand_workflow_for_dag` が全件 fan-out。
2. **Settings dialog からの空文字上書き経路**: Settings dialog の C10 セクションは独立 `_C10AppId()` インスタンス (`settings_window.py`)。ユーザーが他フィールド (usecase_id 等) を編集すると autosave で settings に `app_ids=""` が永続化され、`settings_changed` emit → MainWindow `_on_settings_changed` → `apply_to_widgets({"C10": optionspage_c10})` で OptionsPage の `c10.app_ids` を空文字で上書き。結果として Step 1 で選択した APP-ID 1 件が失われ、orchestrator の後方互換 fallback で全件 fan-out される。

**修正内容** (GUI 側で完結、CLI 後方互換は維持):

- **[hve/gui/main_window.py](hve/gui/main_window.py)**:
  - `_on_next_clicked` に `_validate_app_ids_for_downstream(wf_ids)` 呼び出しを追加。downstream workflow (`aad-web`, `asdw-web`, `adfd`, `adfdv`) 選択時に APP-ID 未選択なら `QMessageBox.warning` で明示し Step 2 への遷移を停止する。
  - `_on_settings_changed` の `apply_to_widgets` 呼び出しに `skip_keys={("C10", "app_ids")}` を追加。Settings dialog 経由で OptionsPage の `c10.app_ids` が空文字上書きされる経路を遮断する (Settings dialog 内部での反映には影響しない)。
- **[hve/gui/settings_apply.py](hve/gui/settings_apply.py)**: `apply_to_widgets` にキーワード専用パラメータ `skip_keys: Optional[Iterable[Tuple[str, str]]] = None` を追加。`(section_key, option_key)` タプル集合で特定 key の widget 反映のみ skip 可能。既存呼び出しはデフォルト `None` で無影響。

**動作確認**:
- 新規テスト 11 件 PASS (`hve/gui/tests/test_main_window_app_id_required.py` 6 件 / `hve/gui/tests/test_settings_apply_skip_keys.py` 5 件)。
- 既存関連テスト 54 件 PASS。失敗 6 件 (`test_section_fields_defaults_consistency`, `test_settings_precheck_llm_judge` x5) は本変更前から発生している pre-existing failure (`_CAutopilotSection` に `precheck_use_llm_judge` 属性が無い別問題) で本修正のスコープ外。

### Fixed — AAD-WEB Step 2.1 (画面定義書) が Step 1 完了後に実行されない不具合 — 下流 io-contract / prompt / template の per-APP glob 統一

**根本原因**: Phase 1-7 で `Arch-UI-List--aad-web--1` の output を per-APP fan-out (`docs/catalog/screen-catalog-APP-NN.md`) に変更したことで Step 2.1 (`Arch-UI-Detail`) の skip 自体は解消済みだが、その下流に位置する 13 件の io-contract、7 件の prompt (うち 3 件は Phase 1-7 で対応済み)、2 件の template、1 件の ISSUE_TEMPLATE は旧形式 `docs/catalog/screen-catalog.md` (単一ファイル) を input として参照したまま残されていた。`validate-io-contract.py` の整合性検証で path 不整合が継続して報告される状態であり、今後 AAS Step 6 / AAG Step 1-3 / AAD-WEB Step 2.2 / ASDW-WEB Step 3.0TC・3.1 / AAGD Step 1 を実行した際に同種の skip / consumed_artifacts 不整合が再発するリスクがあった。本 Phase 8 はこの波及範囲の path 表記を per-APP glob に統一する。

**修正内容**:
- **[.github/io-contracts/*.yaml](.github/io-contracts) (13 ファイル)**: `inputs[].path` を `docs/catalog/screen-catalog.md` → `docs/catalog/screen-catalog-APP-*.md` (per-APP glob) に統一。
  - `Arch-Microservice-ServiceCatalog{,--aas--6}.yaml`, `Arch-AIAgentDesign-Step{1,2,3}{,--aag--{1,2,3},--aagd--1}.yaml`, `Arch-Microservice-ServiceDetail--aad-web--2.2.yaml`, `Dev-Microservice-Azure-UICoding{,--asdw-web--3.1}.yaml`, `Dev-Microservice-Azure-UITestCoding--asdw-web--3.0TC.yaml`
- **[.github/prompts/*.prompt.md](.github/prompts) (7 ファイル / 9 箇所)**: `Arch-AIAgentDesign-Step{1,2,3}`, `Arch-Microservice-ServiceCatalog`, `Arch-TDD-TestStrategy` (3 箇所), `Dev-Microservice-Azure-UICoding`, `Dev-Microservice-Azure-UITestCoding` の `screen-catalog.md` 言及を per-APP glob に統一し「全 APP の per-APP 分割された画面カタログ。`Arch-UI-List` Step 1 の per-APP fan-out 出力。全 APP 分を集約読みする」コメントを併記 (上流の `Arch-UI-List` / `Arch-UI-Detail` prompts は Phase 1-7 で per-APP fan-out 化対応済み、本エントリのスコープ外)。
- **[.github/scripts/templates/aas/step-6.md](.github/scripts/templates/aas/step-6.md), [.github/scripts/templates/asdw-web/step-3.1.md](.github/scripts/templates/asdw-web/step-3.1.md) (2 ファイル)**: `screen-catalog.md` 言及を per-APP glob 統一。
- **[.github/ISSUE_TEMPLATE/web-app-dev.yml](.github/ISSUE_TEMPLATE/web-app-dev.yml) L19**: 同様に per-APP glob 統一。

### Changed — `validate-io-contract.py`: per-key fan-out output (`{key}` placeholder) と per-APP glob input (`*`) の等価マッチを実装

**背景**: Phase 1-7 で per-APP fan-out 化した producer output は `docs/catalog/screen-catalog-{key}.md` の `{key}` placeholder 表記。consumer の per-APP glob input `docs/catalog/screen-catalog-APP-*.md` は既存の `fnmatch.fnmatchcase(producer, input_pattern)` 単方向マッチでは producer の `{key}` をリテラル 5 文字として扱うため失敗し、`no producer in inventory` error が新たに 11 件発生していた。

**修正内容**:
- **[.github/scripts/validate-io-contract.py](.github/scripts/validate-io-contract.py)** (`find_producers` 関数): wildcard マッチ失敗時に producer 側の `{key}` を `*` に置換 (`p_pat = p.replace("{key}", "*")`)、双方向 fnmatch (`fnmatchcase(p_pat, path) or fnmatchcase(path, p_pat)`) で per-APP glob input との等価マッチを実装。`hve/orchestrator.py:_step_produces_path` (Phase 1-7) と同一パターン。`{key}` を含まない producer path には影響しないため偽陽性リスクなし。

**動作確認**:
- `pytest hve/tests/test_dag_executor_fanout_deferred.py hve/tests/test_workflow_registry.py hve/tests/test_consumed_artifacts.py hve/tests/test_catalog_parsers_screen.py hve/tests/test_fanout.py hve/tests/test_deferred_fanout.py hve/tests/test_input_artifact_check.py hve/tests/test_split_fork.py hve/tests/test_orchestrator.py::TestRunWorkflowFanout hve/tests/test_orchestrator.py::TestDetectExistingArtifacts` — 280 件 PASS。
- `python .github/scripts/validate-io-contract.py` — 504 errors (Phase 7 完了直後の真の baseline と同等、net 増減なし)。Phase 8 の path 変更で一時的に 511 件まで増加した validator error は本 `find_producers` 修正で 504 件に戻り、新規発生していた 11 件「no producer in inventory」(per-APP glob input vs per-key fan-out output のマッチ失敗) を全件解消した。

**Known Limitations**:
- Phase 9 で screen-catalog 関連の残 12 件 validator error (4 件「declares producer mismatch」、8 件「declared in io-contract but not in StepDef」) を解消。本 Unreleased セクション下部の `### Changed — io-contract / StepDef 整合化 (Phase 9)` を参照。

### Changed — io-contract / StepDef 整合化 (Phase 9): screen-catalog 関連 12 件 validator error 解消

**背景**: Phase 8 完了時点で残存していた screen-catalog 関連 12 件 (Phase 1-7 修正前から存在する既存問題) を整理した。

**修正内容**:
- **[.github/io-contracts/Arch-AIAgentDesign-Step{1,2,3}.yaml](.github/io-contracts), [Dev-Microservice-Azure-UICoding.yaml](.github/io-contracts/Dev-Microservice-Azure-UICoding.yaml) (4 ファイル)**: グローバル io-contract の `screen-catalog-APP-*.md` input で `producer: Arch-UI-List` (グローバル名) を `producer: Arch-UI-List--aad-web--1` (per-instance 名) に統一。Phase 1-7 で per-instance のみが output を持つ実装に揃えた。
- **[hve/workflow_registry.py](hve/workflow_registry.py)** (8 step の `StepDef.required_input_paths` を追加):
  - AAD_WEB Step 2.1 (Arch-UI-Detail): `docs/catalog/screen-catalog-{key}.md` (per-key、io-contract と同表記)
  - AAD_WEB Step 2.2 (Arch-Microservice-ServiceDetail), ASDW_WEB Step 3.0TC/3.1, AAG Step 1/2/3, AAGD Step 1: `docs/catalog/screen-catalog-APP-*.md` (per-APP glob)
  - validator は strict set diff (`ri_paths - step_in`) で比較するため、io-contract input と StepDef.required_input_paths を同表記で揃えた。

**動作確認**:
- `pytest hve/tests/test_workflow_registry.py hve/tests/test_consumed_artifacts.py hve/tests/test_dag_executor_fanout_deferred.py hve/tests/test_catalog_parsers_screen.py hve/tests/test_fanout.py hve/tests/test_deferred_fanout.py hve/tests/test_input_artifact_check.py hve/tests/test_split_fork.py hve/tests/test_orchestrator.py::TestRunWorkflowFanout hve/tests/test_orchestrator.py::TestDetectExistingArtifacts` — 280 件 PASS。
- `python .github/scripts/validate-io-contract.py` — 492 errors (Phase 8 後 504 errors → 12 件減、screen-catalog 関連 0 件)。

**Known Limitations (Phase 9 後の残存事項)**:
- 各 step io-contract に required=true で宣言された screen-catalog 以外の input path (`app-catalog.md`, `data-model.md`, `domain-analytics.md`, `service-catalog.md`, `service-catalog-matrix.md`, `test-strategy.md` 等) は依然 StepDef.required_input_paths に未登録の step が多く、対応する mismatch error が残存。これらは本タスクのスコープ外 (screen-catalog 限定) のため別タスクで対応する。
- aad-web/2.1 の StepDef `{key}` placeholder は fanout_parser=screen_catalog の child step key (SC-### 等) と意味的にずれる可能性があるが、validator は文字列マッチのみで処理するため整合性は確保。意味整合は別 PR で検証する。

### Changed — io-contract / StepDef 整合化 (Phase 10): screen-catalog 以外の input path mismatch 解消 (288 件)

**背景**: Phase 9 後の残存事項として残されていた「screen-catalog 以外の input path mismatch」(289 件 / 38+ step) を解消する。Phase 8 の `validate-io-contract.py` strict set diff 修正により、io-contract の required=true / kind=agent_artifact な input が StepDef.required_input_paths に登録されていないものが大量に検出されていた。

**修正内容**:
- **[hve/workflow_registry.py](hve/workflow_registry.py)** (38 step の `StepDef.required_input_paths` を新規追加 / 更新):
  - `ard/4.2`, `aas/3.1/4.1/4.2/5/6`, `aad-web/1/2.1/2.2/2.3/3`, `asdw-web/1.1/1.2/2.1/2.2/2.3/2.3T/2.3TC/2.4/2.5/3.0T/3.0TC/3.1/3.2/3.3/4.1/4.2`, `aag/1/2/3`, `aagd/1/2.1/2.2/2.3/3`, `adfdv/1.1/1.2/2.1/2.2/3/4.1/4.2`, `adfd/1.1/1.2/2/3/4/5/6.1/6.2/6.3`, `adoc/2.1/2.2/2.3/2.4/2.5/3.1/4/5.1/5.2/5.3/5.4/6.1/6.2/6.3`, `aqod/2`
  - 各 step に対応する io-contract から `required: true` & `kind: agent_artifact` な input path を抽出し、StepDef.required_input_paths に merge (sorted)。
  - `ard/4.1` は test `test_workflow_registry_ard.py::test_step_4_1_skeleton_extraction` が `required_input_paths == []` を要求するため自動修正の SKIP_STEPS から除外 (skip_fallback_deps による設計: `business-requirement.md` (Step 2) と `company-business-requirement.md` (Step 1.2) の片方しか生成されないため、consumed_artifacts 経由でアクセスする方針)。
  - `akm/2`: 旧版スクリプトの (id, custom_agent) 重複バグで誤って追加された `qa/{key}-original-docs-questionnaire.md` を revert (akm/2 の io-contract には agent_artifact input なし)、`aqod/2` に正しく追加。
  - `aagd/1`: 旧版スクリプトの重複バグで未 patch だった 11 path を手動追加。
- **[hve/autopilot/plan_review_gap.py](hve/autopilot/plan_review_gap.py), [hve/gui/page_options.py](hve/gui/page_options.py)**: `_WORKFLOW_CANONICAL_ORDER` に `"aag"`, `"aagd"` を追加 (pre-existing test `test_implicit_constants_preserved` が要求する canonical order の同期)。

**動作確認**:
- `pytest hve/tests/autopilot hve/tests/test_workflow_registry.py hve/tests/test_workflow_registry_ard.py` — 181 件 PASS, 1 skipped。
- `python .github/scripts/validate-io-contract.py` — Total ERRORs: 492 → 204 (288 件解消)。
  - input contract→step mismatch: 289 → 1 件 (99.7% 削減、残 1 件は `ard/4.1` = test 要件 + skip_fallback 設計由来)
  - input step→contract mismatch: 3 件 (Phase 9 baseline と同じ、別タスク)

**Known Limitations (Phase 10 後の残存事項)**:
- `ard/4.1` の `docs/company-business-requirement.md` mismatch (1 件): io-contract 側が `required: true` だが、skip_fallback_deps により片方しか生成されない設計のため StepDef.required_input_paths から除外。io-contract 側を `required: false` 化するか、validator に skip_fallback 認識ロジックを追加するかの設計判断は別タスク。
- input step→contract mismatch (3 件 / aas/3.1, aad-web/3): StepDef にあるが io-contract に無い path (consumed_artifacts 経由で参照する設計)。io-contract 側更新は別タスク。
- output mismatch (142 件) / producer mismatch 等 (58 件): Phase 10 のスコープ外 (input mismatch 解消限定)、別タスクで対応。
- pre-existing GUI test fail `test_default_theme_is_dark` (`hve/tests/test_activity_status_widget.py::TestActivityStatusWidget::test_default_theme_is_dark`): 本タスク前から fail (git stash で確認)、本タスクのスコープ外。

### Fixed — `hve` GUI Step 1 で対象 APP-ID を 1 件選択しても Step 2 で全 APP-ID が実行される不具合 (AAD-WEB / ASDW-WEB ほか)

Step 1 設定画面でワークフロー (例: `AAD-WEB`) と対象 APP-ID (例: `APP-07`) を 1 件だけ選択しても、Step 2 実行画面で全 16 件の APP-ID 配下が fan-out 展開される不具合を修正した。

**根本原因**: `orchestrator.py` の `_expand_workflow_for_dag` が `effective_params["app_ids"]` を `hve/fanout_expander.py:expand_workflow_fanout` に伝播していなかった。`resolve_app_arch_scope.matched_app_ids` で APP-07 のみが選定されていても、fan-out 展開時に APP-ID フィルタが適用されず全カタログキーが展開されていた。`DAGExecutor` のランタイム再展開 (`_try_dynamic_expand` → `expand_single_step_fanout`) でも同様に未伝播。

**修正内容**:
- `hve/catalog_parsers.py`: `parse_service_app_mapping(repo_root) -> Dict[str, List[str]]` を新規追加。`docs/catalog/service-catalog.md` A 節サマリ表の「利用APP」列をヘッダから動的検出し、SVC-NN → [APP-NN, ...] mapping を抽出する (service_catalog 経由の fan-out で SVC を APP-ID で絞り込むため)。
- `hve/fanout_expander.py`: 定数 `_APP_ID_FILTERABLE_PARSERS = {"app_catalog", "screen_catalog", "service_catalog"}` と正規表現 `_SCREEN_KEY_PREFIX_RE = re.compile(r"^(APP-\d{2,3})-")` を追加 (APP-10 と APP-100 の誤マッチ防止)。`_filter_keys_by_app_ids(parser, keys, app_ids, repo_root)` を実装し、`_resolve_keys` / `expand_workflow_fanout` / `expand_single_step_fanout` に keyword-only 引数 `app_ids` を追加。`app_ids=None または []` 時はフィルタ無効化で後方互換維持。
- `hve/orchestrator.py`: `_expand_workflow_for_dag` に keyword-only 引数 `app_ids` を追加し、`expand_workflow_fanout` へ伝播。L3237 呼び出し側で `app_ids=effective_params.get("app_ids")` を渡す。`DAGExecutor` 生成箇所 (L3779) でも同じ `effective_params["app_ids"]` を `app_ids` kwarg で渡し、deferred fan-out のランタイム再展開時にも APP-ID フィルタが効くようにする。
- `hve/dag_executor.py`: `DAGExecutor.__init__` に keyword-only 引数 `app_ids` を追加し、`self._app_ids` で保持。`expand_workflow_fanout` (dag_plan=None fallback 経路) および `expand_single_step_fanout` (`_try_dynamic_expand` 内) の呼び出しに `app_ids=self._app_ids` を伝播。
- `hve/tests/test_fanout.py`: APP-ID フィルタの単体テスト 15 件を追加 (`_filter_keys_by_app_ids` の app_catalog/screen_catalog/service_catalog 各パターン、APP-10 vs APP-100 誤マッチ防止、service-catalog A 節不在ケース、後方互換 `app_ids=None/[]`、`expand_workflow_fanout` および `expand_single_step_fanout` の APP-ID フィルタ統合)。
- `hve/tests/test_orchestrator_app_id_filter.py`: 新規追加 (5 件)。`_expand_workflow_for_dag` への `app_ids` 伝播と `DAGExecutor → expand_single_step_fanout` への伝播を monkeypatch spy で検証。

**動作確認**:
- `pytest hve/tests/test_fanout.py hve/tests/test_orchestrator_app_id_filter.py hve/tests/test_dag_executor.py hve/tests/test_dag_executor_fanout_deferred.py hve/tests/test_dag_planner.py hve/tests/test_deferred_fanout.py hve/tests/test_e2e_akm_fanout_dryrun.py hve/tests/test_fork_flag_rollback.py hve/tests/test_resume_fanout.py hve/tests/test_resume_phase3.py` — 全 112 件 PASS。
- `pytest hve/tests/test_orchestrator.py -k "not run_workflow and not RunWorkflow"` — 104 PASS (workbench `wait_for_exit` の `time.sleep` ループは事前から存在する pre-existing issue で本変更とは無関係)。
- AAD-WEB × APP-07 (実 docs/ 参照): Step 1 = `1/APP-07` 1 件、Step 2.1 = APP-07 配下 10 件、Step 2.2/2.3 = `SVC-09` 1 件のみ展開 (期待通り絞り込み)。
- AAD-WEB × app_ids 未指定 (legacy): Step 1 = 16 件、Step 2.1 = 170 件、Step 2.2/2.3 = 19 件 (既存挙動維持)。

**Known Limitations**:
- `dataflow_catalog` / `agent_catalog` は対応カタログファイル (`docs/dataflow/dataflow-app-catalog.md` / `docs/agent/agent-application-definition.md`) が物理不在のため、APP-ID フィルタの対象外 (`_APP_ID_FILTERABLE_PARSERS` 未掲載)。これらの parser を使う workflow (`AAG` / `AAGD` 等) では当面 APP-ID フィルタが効かない (= 全件展開) ため、別 Issue でカタログスキーマ確定後に追加対応する。
- `aas` workflow は `_ARCH_FILTER_WORKFLOWS` (orchestrator.py) に未登録のため、本修正のスコープ外。

### Fixed — Workbench Footer の Reqs / AI Credit / Cost が常時「-」/「0」表示される不具合

Step 2 実行中画面で `Reqs` が `0`、`Cost` が `-` のまま動かず、Unlimited プラン契約者向けの `AI Credit (Nano AIU)` が GUI に一切表示されない問題を、GitHub Copilot CLI SDK v0.3.0 の `assistant.usage` イベントを直接抽出する経路を新設して修正した。根本原因は (1) `session.disconnect()` がイベントハンドラを即時クリアするため `session.shutdown.totalPremiumRequests` が永遠に届かない、(2) Unlimited プランでは SDK が `copilot_usage=None` を返し `total_nano_aiu` が取得不可、(3) `quota_snapshots.*.used_requests` も常に 0 で baseline 差分が出ない、の 3 点。`assistant.usage` ハンドラから `cost` / `copilot_usage.total_nano_aiu` / `quota_snapshots` / `api_call_id` を毎ターン抽出して `usage_credit` / `quota_snapshot` の新 stats_event を発火し、`WorkbenchState` で `api_call_id` 重複排除しつつ累積する。Unlimited プランでは `assistant_usage_count` をフォールバック Reqs として、`unavailable_reason` 文字列を AI Credit の「N/A (AIU unavailable)」表示根拠として伝達する。

さらに **SDK cost 取得時の Plan 非依存フォールバック表示** として、AI Credit Footer の表示優先順位を `total_nano_aiu > sdk_multiplier_cost_total > unavailable_reason > pricing` の 4 段階に拡張した。Unlimited プランで `total_nano_aiu` が取得できない場合でも、`assistant.usage.cost` (Multiplier cost) の累計が SDK から取れていれば `mc: X.X` 形式 (SDK multiplier cost を AIU/USD に換算せず生値累計をそのまま表示) で表示する。これにより `assistant.usage.cost=1.0` が 7 件届いた場合は `mc: 7.0` のように、ユーザーの使用量が Plan に関わらず Footer から把握できる (捏造禁止: SDK 生値そのままを累計表示、AIU/USD 換算は行わない)。

### Added — `Console.diag()` 診断専用ログメソッド

`final_only` 抑止時のみ非表示で、quiet/verbosity 非依存に通常ログ経路へ出力する `Console.diag(msg)` を追加。GUI 側の `[hve:stats]` 接頭辞フィルタ (`page_workbench.py:1300`) で診断ログが UI ログタブから除外される構造的問題を回避するため、SDK 生ペイロードや env 伝播状態を `HVE_DEBUG_ASSISTANT_USAGE=1` 環境変数 gate 付きで可視化する用途で使う。

- **[hve/console.py](hve/console.py)**:
  - メソッド `Console.diag(msg: str) -> None` を追加。`_emit(msg, always=True)` 経由で通常ログ経路に流す。
- **[hve/tests/test_console.py](hve/tests/test_console.py)**:
  - `TestConsoleDiag` 4 件を追加: `final_only` 抑止確認、quiet/verbosity 非依存、`always=True` 経由出力、空文字許容。

### Added — SDK `assistant.usage` 経由の AI Credit / Reqs / Quota Snapshot リアルタイム抽出

`hve/runner.py` の `assistant.usage` ハンドラを拡張し、`api_call_id` / `cost` (Model multiplier cost) / `copilot_usage.total_nano_aiu` (Nano AIU) / `quota_snapshots` を抽出して GUI へ流す新経路を実装。`session.shutdown` に依存しないため、CLI セッション切断後でもリアルタイムに料金/Reqs 情報が反映される。

- **[hve/runner.py](hve/runner.py)** (`assistant.usage` ハンドラ, line 3322-3540):
  - SDK 値抽出: `api_call_id`, `multiplier_cost`, `nano_aiu` (from `copilot_usage.total_nano_aiu`), `quota_snapshots[*]` (datetime は ISO 文字列化)。
  - 新 stats_event `usage_credit`: `{step_id, model, api_call_id, multiplier_cost?, nano_aiu?, unavailable_reason?}`。
  - 新 stats_event `quota_snapshot`: `{step_id, model, quota_id, used_requests, entitlement_requests, remaining_percentage, overage, is_unlimited_entitlement, reset_date_iso?}`。
  - `copilot_usage=None` (Unlimited プラン) 時に `unavailable_reason="SDK returned copilot_usage=None (Unlimited plan: total_nano_aiu not provided)"` を併送。
  - `HVE_DEBUG_ASSISTANT_USAGE=1` 環境変数 gate で `debug_env` / `assistant_usage_raw` / `assistant_usage_raw_err` の `Console.diag` 出力を実施。
- **[hve/gui/workbench_state.py](hve/gui/workbench_state.py)**:
  - 新フィールド: `sdk_aiu_total_nano: int = 0`, `sdk_multiplier_cost_total: Optional[float] = None`, `sdk_credit_per_model: Dict[str, Dict[str, float]]`, `quota_snapshots_latest: Dict[str, dict]`, `quota_snapshots_baseline: Dict[str, dict]`, `seen_api_call_ids: set`, `sdk_credit_unavailable_reason: str = ""`。
  - 派生プロパティ: `sdk_aiu_total` (`nano / 1e9`), `quota_used_delta(quota_id)`, `total_quota_used_delta`, `display_reqs` (優先順位: `premium_requests_total` > `total_quota_used_delta` > `assistant_usage_count` > 0)。
  - 新メソッド: `apply_assistant_credit(api_call_id, model, multiplier_cost, nano_aiu, unavailable_reason)` (`api_call_id` で `seen_api_call_ids` dedup、初回のみ `unavailable_reason` 保持)、`apply_quota_snapshot(quota_id, snap)` (baseline 未設定時に現在値保存)。
  - `assistant_usage_count` フィールドコメントを「`apply_assistant_usage` 発火回数 + `display_reqs` フォールバック源」の 2 用途明示に強化。
- **[hve/gui/workbench_logger.py](hve/gui/workbench_logger.py)**:
  - 新 stats kind ハンドラ: `usage_credit` (→ `apply_assistant_credit` 呼び出し、`unavailable_reason` 伝達)、`quota_snapshot` (→ `apply_quota_snapshot` 呼び出し)。
  - `assistant_usage_raw` / `assistant_usage_raw_err` / `debug_env` を body に追記する経路を追加 (診断用)。
- **[hve/gui/workbench_widgets.py](hve/gui/workbench_widgets.py)** (Footer 表示):
  - AI Credit 表示 (優先順位 4 段階): `sdk_aiu_total > 0` → `"X.XXXX AIU"`、`sdk_multiplier_cost_total > 0` → `"mc: X.X"` (SDK cost 取得時の Plan 非依存フォールバック)、`sdk_credit_unavailable_reason` 非空 → `"N/A (AIU unavailable)"`、それ以外 → pricing 経路 (USD/JPY) または `"-"`。
  - Reqs 表示は `display_reqs` 経由 (UI 側ロジック変更なし、優先順位は state 側で決定)。
- **[hve/gui/stats_detail_popup.py](hve/gui/stats_detail_popup.py)**:
  - 新セクション「AI Credit (SDK 直接)」: 累積 AIU / Nano AIU / multiplier cost / model 別内訳 / `assistant.usage 発火回数` / unavailable_reason。
  - 新セクション「Quota Snapshot」: quota_id ごとに used/entitlement/remaining%/overage と実行内 delta。
- **テスト**:
  - **[hve/tests/pricing/test_workbench_state_ai_credit.py](hve/tests/pricing/test_workbench_state_ai_credit.py)**: `apply_assistant_credit` / `apply_quota_snapshot` / `display_reqs` 優先順位を含む 23 件追加 (`api_call_id` dedup、baseline 設定、delta 計算、None 安全性、`unavailable_reason` 初回保持、`assistant_usage_count` フォールバック)。
  - **[hve/tests/pricing/test_workbench_logger_ai_credit.py](hve/tests/pricing/test_workbench_logger_ai_credit.py)**: `usage_credit` / `quota_snapshot` パーステスト 21 件追加 (`paired assistant_usage + usage_credit` 二重加算防止テストを含む)。
  - **[hve/tests/pricing/test_footer_cost.py](hve/tests/pricing/test_footer_cost.py)**: Footer AI Credit 表示テストを追加/更新: `N/A (AIU unavailable)` 表示テストを Unlimited プラン挙動に修正し、Multiplier cost フォールバック表示 (`mc: X.X`) と AIU 優先 (`aiu` と `mc` 同時取得時) の 2 件を新規追加。
  - **[hve/gui/tests/test_stats_detail.py](hve/gui/tests/test_stats_detail.py)**: `build_snapshot` 期待セクション一覧を新セクション (AI Credit / Quota Snapshot / Cost / Elapsed) に追従。

### Notes

- `cost` (Model multiplier cost) は SDK の `AssistantUsageData.cost` (Experimental) 値で、USD 金額ではなく Unlimited プランでは 1.0 固定。USD/JPY 換算用には別途 pricing 経路 (`cost_usd_total` / `cost_jpy_total`) が必要 (Phase B、本変更には含めない)。
- Unlimited プラン契約者では `total_nano_aiu` が SDK 仕様上付与されないため、AI Credit の絶対量表示は不可能。「N/A (AIU unavailable)」表記により「未取得」と「未提供」を区別し、捏造値の表示を防止する。
- 既存 `runner.py` の Reqs ゼロ時に Cost 計算をスキップする `if reqs > 0:` ガード（`session.shutdown` ハンドラ内）は維持し、`assistant_usage_count` フォールバック導入後も pricing 経路の挙動には影響しない。

### Fixed — Workbench「作業状況」で複数 Step を同時展開した際にサブプロセスノードが垂直方向で重なる不具合

DAG ベース「作業状況」ウィジェット (`DagStatusWidget`) で、複数の Step を同時に Fan-out 展開した時、サブプロセス（子）ノードの矩形が下行 Step ノード矩形と垂直方向で重なって描画される構造的バグを修正した。原因は `_relayout()` 内の `row_extra: Dict[int, int]` プレースホルダが宣言だけで一度も populated されないため、ある行の展開子ブロックが下の行を全く押し下げない設計欠陥だった。修正では `_relayout()` から呼び出される純関数 `compute_row_y_offsets(rank, order, child_heights, *, node_h, row_gap) -> (row_top_y, within_row_child_offset)` を `dag_layout.py` に新設し、行ごとの累積 y オフセットを事前計算した上で Step ノード配置と子ブロック配置の双方に同じ値を適用することで、同一行内の複数展開を rank 昇順で縦積みしつつ、下行を child_heights の合計ぶんだけ確実に押し下げる構造へ変更した。`cols_per_row` は Step ごとの `parent_x`（rank 位置）で再計算し、右端 Step での予約高過小による下行侵食も解消する。

- **[hve/gui/widgets/dag_layout.py](hve/gui/widgets/dag_layout.py)**:
  - 純関数 `compute_row_y_offsets(rank, order, child_heights, *, node_h, row_gap) -> (row_top_y, within_row_child_offset)` を新設。Qt 非依存・決定的・rank/order 両方にある step_id のみ処理、同一 (rank, order) は (rank, step_id) 昇順で tie-break する。
- **[hve/gui/widgets/dag_status_widget.py](hve/gui/widgets/dag_status_widget.py)**:
  - import に `compute_row_y_offsets` を追加。
  - 定数 `CHILD_BLOCK_PADDING_TOP = 4` を新設（親 Step 下端と子ブロック上端の余白 px、`compute_row_y_offsets` に渡す `child_heights` 値にも含まれる契約）。
  - `_relayout()` 内の不具合プレースホルダ `row_extra: Dict[int, int] = {}` を削除し、事前に `child_heights` dict を構築して `compute_row_y_offsets` を呼び出す方式に置換。
  - Step 配置の `base_y` を `stripe_top + row_top_y.get(o, 0)` に変更（旧: `o * (NODE_H + ROW_GAP)`）。
  - `_draw_fanout_children` 呼び出しに `block_top_override` を渡し、同一行内で先に展開された兄弟の下に積み上げる挙動を実現。
  - ストライプ高計算を `STRIPE_PADDING_Y + row_top_y[last_order] + NODE_H + last_row_child_total` に変更（`row_top_y` が行ごとの子ブロック高を既に反映するため、旧 `child_block_total` の別途加算を廃止）。
  - ヘルパーメソッド `_compute_cols_per_row(parent_x: float = 0.0) -> int` を新設し、`_relayout` と `_draw_fanout_children` で重複していた viewport 幅ベースの列数計算を共通化。
  - ヘルパーメソッド `_compute_child_block_height(sub_count: int, cols_per_row: int) -> int` を新設し、子ブロック高計算を一元化。
  - `_draw_fanout_children` シグネチャに `block_top_override: Optional[float] = None` を追加。
- **[hve/gui/tests/test_dag_layout.py](hve/gui/tests/test_dag_layout.py)**:
  - `compute_row_y_offsets` のユニットテスト 10 件を追加。空入力、no_expansion、single_expansion、same-row stack、multi-row 伝播、unknown step 無視、rank/order 不一致無視、決定性（dict 挿入順非依存）、tie-breaker（step_id 昇順）、シナリオ（multi-row × multi-expansion）、省略子高さ。
- **[hve/gui/tests/test_dag_status_widget.py](hve/gui/tests/test_dag_status_widget.py)**:
  - 矩形非重複ヘルパー `_rect_of` (`sceneBoundingRect()` 使用), `_rects_overlap_vertically`, `_assert_no_overlapping_rects` (Step↔child / Step↔Step / child↔child の三方向) を新設。
  - 非重複保証テスト 4 件を追加: `test_no_overlap_single_step_expanded_in_multi_row_workflow`, `test_no_overlap_high_rank_step_expanded_pushes_next_row` (高 rank Step の `parent_x` ベース cols_per_row 再計算を検証), `test_no_overlap_multiple_steps_expanded_same_workflow` (本不具合の主目的), `test_no_overlap_expansion_in_first_of_two_workflows`。

### Changed — Auto モデル選択を GitHub Copilot CLI/SDK の Auto Model Selection と完全一致

`hve` の `Auto` モデル選択を、これまでの「`claude-opus-4.7` + `reasoning_effort="high"` を強制適用するクライアント側固定」から、CLI/SDK と同じ「サーバ側 Auto Model Selection への委譲」に変更した。SDK の `create_session(model="auto")` （wire 値 `"auto"` は GitHub Copilot サーバの `models.list` が返す正規モデル ID）を渡し、`reasoning_effort` はクライアントから一切付与しない。これによりサーバ側がプラン・ポリシー・可用性に応じて最適モデル（GPT-5.4 / GPT-5.3-Codex / Sonnet 4.6 / Haiku 4.5 等、変動）へ動的ルーティングし、有料プランは 10% プレミアム乗数ディスカウントの恩恵を受ける。hve 内部センチネル `MODEL_AUTO_VALUE="Auto"`（大文字）は UI 表示・既存 Issue/PR・CLI 引数の後方互換のため維持し、`create_session` 呼び出し直前で `to_wire_model()` ヘルパーが `"auto"` （小文字 wire 値）へ変換する。

**BREAKING CHANGE**: 旧挙動で Auto を選択時は常に Opus 4.7 + high が走っていたが、新挙動では実際に使われるモデルは GitHub サーバ側の判定に依存する（CLI の `/model` と同等）。ユーザーが明示的に `reasoning_effort` を指定したケースは経路を問わず引き続き尊重する。

- **[hve/config.py](hve/config.py)**:
  - 定数 `MODEL_AUTO_REASONING_EFFORT = "high"` を削除（Auto 時の `reasoning_effort` 強制適用ロジックを廃止）。
  - 定数 `MODEL_AUTO_WIRE_VALUE = "auto"` を追加（SDK へ渡す Auto モデル wire 値、公式 `models.list` の正規 ID）。
  - 関数 `to_wire_model(model: Optional[str]) -> Optional[str]` を追加: `"Auto"` → `"auto"` 変換、空文字/None → None（呼び出し側で `model` キーを payload から省略）、明示モデル → そのまま。
  - `SDKConfig.reasoning_effort` フィールドの docstring を「Auto 時 high フォールバック」から「Auto 時はサーバ委譲」に修正。
- **[hve/orchestrator.py](hve/orchestrator.py)**:
  - `_apply_reasoning_effort` を簡略化: ユーザー指定 `reasoning_effort` のみ伝播し、未指定時は何もセットしない（旧: Auto モデル時に MODEL_AUTO_REASONING_EFFORT フォールバック）。
  - 6 箇所の `session_opts` 構築（workiq-prefetch / akm-verify / akm-ingest / ard-workiq / ard-target-business / code-review）を、`_wire_model = to_wire_model(config.model); if _wire_model: session_opts["model"] = _wire_model` パターンに統一。旧 defensive workaround の「`~/.copilot/settings.json` の -high バリアント上書き回避」コメントを削除。
  - import から `DEFAULT_MODEL`, `MODEL_AUTO_VALUE`, `MODEL_AUTO_REASONING_EFFORT` を削除し `to_wire_model` を追加。
- **[hve/runner.py](hve/runner.py)**:
  - `_build_sub_session_opts` およびメインセッション構築の 2 箇所を同パターンで置換。
  - `_RESUME_SESSION_KEYS` 周辺コメントから旧 `MODEL_AUTO_REASONING_EFFORT` 言及を削除。
  - resume_session フォールバック箇所のコメントを「Auto 時の reasoning_effort=high が含まれるため」→「ユーザー指定 reasoning_effort が含まれるケース」に修正（実態に合わせ整合化）。
  - import から `DEFAULT_MODEL`, `MODEL_AUTO_VALUE`, `MODEL_AUTO_REASONING_EFFORT` を削除し `to_wire_model` を追加。
- **[hve/self_improve.py](hve/self_improve.py)**:
  - LLM 判定セッション構築の Auto 経路を同パターンで置換（旧: Auto 時に `reasoning_effort="high"` のみセット）。
- **[hve/gui/br_generator.py](hve/gui/br_generator.py)**:
  - BR 章生成セッション構築の Auto 経路を同パターンで置換。
- **[hve/autopilot/precheck_llm_judge.py](hve/autopilot/precheck_llm_judge.py)**:
  - `MODEL_AUTO_REASONING_EFFORT` 参照をリテラル `"high"` に置換し、precheck 判定 LLM が常に Opus 4.7 + high に意図的固定される挙動を維持（Auto Model Selection は使わず、判定品質安定化のための固定）。
- **[hve/tests/test_runner.py](hve/tests/test_runner.py)** (テスト更新):
  - `TestSubSessionOptsReasoningEffort` クラスの docstring を新挙動に更新。
  - `test_auto_model_adds_reasoning_effort_high` → `test_auto_model_sends_wire_auto_no_reasoning` にリネーム + 新挙動検証（Auto 時 `opts["model"] == "auto"` かつ `"reasoning_effort"` 不在）。
  - `test_empty_string_treated_as_auto` → `test_empty_string_omits_model_and_reasoning` にリネーム + 新挙動検証（空文字時 `"model"` も `"reasoning_effort"` も不在）。
- **[hve/tests/test_orchestrator_effort.py](hve/tests/test_orchestrator_effort.py)** (テスト更新):
  - モジュール docstring を新挙動に更新。
  - `test_no_user_value_auto_model_uses_fallback` → `test_no_user_value_auto_model_leaves_unset` にリネーム + assertion 変更（Auto 時 `"reasoning_effort"` キー不在）。
  - `test_review_auto_model_fallback` → `test_review_auto_model_leaves_unset` にリネーム + 同様変更。
  - import から `MODEL_AUTO_REASONING_EFFORT` を削除。
- **[hve/tests/test_config.py](hve/tests/test_config.py)** (テスト追加):
  - 新 TestCase `TestToWireModel` を追加（6 テスト: `"Auto"` → `"auto"` 変換、明示モデル passthrough、None / 空文字 → None、定数値の固定検証）。
- **[hve-dev/requirement-definition.md](hve-dev/requirement-definition.md)** / **[hve-dev/requirement-test-mapping.md](hve-dev/requirement-test-mapping.md)** (要求定義書更新):
  - FR-MODEL-02 を新挙動（Auto 時は `model="auto"` を SDK へ送り Auto Model Selection に委譲、`reasoning_effort` は付与しない）に更新。対応テスト一覧も新テスト名（`TestToWireModel`, `TestApplyReasoningEffortMain.test_no_user_value_auto_model_leaves_unset` 等）に置換。

### Changed — Workbench の Fan-out 展開表示を「無地正方形列」から「ラベル付き小型ノード + エッジ」へ刷新

`DagStatusWidget`（GUI Workbench 左ペイン「作業状況」）で、Fan-out を持つ Step をダブルクリック展開した際の子表示を、無地正方形列（ID/タイトル/クリック反応無し）からラベル付き小型ノード + 親→子エッジへ刷新した。これにより ARD Step 4.2 のような 30+ 子を持つ Fan-out で、各子（例: `4.2/UC-01`）の ID・経過時間・ステータスを視覚的に確認でき、ホバーで Tooltip 表示、クリックで選択遷移が可能になる。同実装は全 Fan-out 利用箇所（`app_catalog` / `screen_catalog` / `service_catalog` / `dataflow_catalog` / `agent_catalog` / `business_candidate` / `use_case_skeleton` / 静的キー）に共通適用される。

- **[hve/gui/widgets/dag_status_widget.py](hve/gui/widgets/dag_status_widget.py)**:
  - 新クラス `_FanoutChildNodeItem` を追加。親ノードの 1/2 幅・0.7 倍高の小型 `QGraphicsRectItem` で、`<key>` 部分のみの短縮ラベル・経過時間・ステータスグリフ・Tooltip（フル ID/タイトル/status/elapsed）を持ち、クリックで `_select_node` へ伝搬する。
  - `_draw_subtask_dots()` を `_draw_fanout_children()` へ置換。viewport 幅に合わせて自動折り返しグリッド配置し、親下辺中央 → 各子上辺中央へ縦方向ルーティングのエッジ（矢印なし）を `_draw_fanout_edge()` で描画（Q4=B）。旧 `SUBTASK_DOT_R` / `SUBTASK_DOT_GAP` 定数を削除し、新たに `CHILD_NODE_W` / `CHILD_NODE_H` / `CHILD_GAP` / `CHILD_ROW_GAP` を追加。
  - `entry.subtasks` のタプルを 3 要素 `(id, title, status)` から 5 要素 `(id, title, status, started_at, finished_at)` に拡張し、子ノードの elapsed 表示を可能にした。`set_plan` の `subtask_status` 引数は短いタプルもデフォルト値で受け付ける後方互換を維持。
  - `_relayout` 内のストライプ高計算を、展開中の全親 Step の子描画高（行数 × 高さ）を合算する形に修正。複数 Step を同時に展開しても下のストライプと重ならない。
  - `_on_tick` で `self._child_items` を反復し、子ノードの経過時間ラベル・Tooltip を 1 Hz で更新する経路を追加。
  - `reset()` / `_relayout` 冒頭で新規辞書 `self._child_items` をクリア。
  - `_export_text` 内の subtasks タプル展開を 5 要素対応にインデックスアクセス化。
- **[hve/gui/tests/test_dag_status_widget.py](hve/gui/tests/test_dag_status_widget.py)** (テスト追加):
  - `test_fanout_children_rendered_as_child_nodes`: 展開時に `_FanoutChildNodeItem` が子数ぶん scene に追加されること。
  - `test_fanout_child_node_has_label_and_tooltip`: 短縮ラベル表示と Tooltip 内容（フル ID + タイトル + status）の検証。
  - `test_fanout_child_node_click_selects`: クリックで `node_selected` シグナルが発火し、選択ノードが切り替わること。
  - `test_fanout_edges_drawn_from_parent_to_each_child`: 展開時に親→各子のエッジ（line アイテム）が描画されること。
  - `test_fanout_children_wrap_into_multiple_rows`: viewport を狭くしたとき子ノードが複数行に折り返されること（Q6=A 検証）。

### Fixed — Workbench エクスプローラーで Agent 連続ファイル生成時に空名の幻行が表示される不具合の修正

GUI Workbench のエクスプローラーパネルで、Agent によるファイル連続生成中に、実ファイル行の下に `display_name` が空（`None`）の幻行が表示される不具合を修正。修正前は `QSortFilterProxyModel` 越しに実在より 1 行多く描画されていたものが、修正後は正確な行数のみが表示される。

- 原因: [hve/gui/file_explorer/multi_root_model.py](hve/gui/file_explorer/multi_root_model.py) の `MultiRootFileModel.refresh_directory()` がディレクトリ変更通知のたびに「全行 `beginRemoveRows` で消去 → 全行 `beginInsertRows` で挿入」の full reset を発行していたため、間に挟まる `_NameFilterProxy`（`QSortFilterProxyModel` + `recursiveFilteringEnabled=True`）が短時間に連続受信した際にマッピングテーブル末尾へ幻インデックスを残留させていた。
- **[hve/gui/file_explorer/multi_root_model.py](hve/gui/file_explorer/multi_root_model.py)**:
  - `refresh_directory()` を full reset から最小差分通知に変更。`new_children` に存在しない既存行のみ降順で個別 `beginRemoveRows`、不足行のみ正しいソート位置に個別 `beginInsertRows` を発行する。
  - 既存 `_Node` インスタンスを名前一致で保持するため、展開済みサブツリーの `_loaded` 状態と展開状態が refresh 後も失われない（副次改善）。
  - `_loaded = True` を関数冒頭で立てるよう変更。`beginInsertRows` 経由で Qt 側から `rowCount()` が逆呼び出しされた際の `_ensure_loaded` 再走査による二重ロードを防止。
  - docstring に「full reset 禁止」の注意書きを追記。
- **[hve/gui/tests/test_multi_root_model.py](hve/gui/tests/test_multi_root_model.py)** (回帰テスト追加):
  - `test_refresh_directory_incremental_no_phantom_rows`: 30 件連続追加でモデル直接の `rowCount` と全行 `display_name` が整合することを検証。
  - `test_refresh_directory_removes_missing_entries`: 削除分岐の回帰防止。
- **[hve/gui/tests/test_file_tree_panel.py](hve/gui/tests/test_file_tree_panel.py)** (回帰テスト追加):
  - `test_panel_no_phantom_rows_on_rapid_creation`: `QTreeView.expand()` 経由 + `QSortFilterProxyModel` 越しに 30 件連続追加し、プロキシ側 `rowCount==30` かつ全行非空を検証。修正前は `rowCount==31`（末尾 `None`）で再現していた現象を回帰テスト化。

### Fixed — 並列 fanout 実行時のログプリフィックスが誤った Step ID を表示する不整合の解消

GUI Workbench のログプリフィックス（`[wf]-[step.title]`）が並列 fanout 実行時に「1 つ前の Step」を指す off-by-one、および並列子の本文行（`▸ Phase 1/1: メインタスク` 等）が全て同一の Step ID にまとめられる不整合を解消した。原因は (a) `step_start` が可視行を `[hve:stats] step_status running` より先に出力していたこと、(b) 並列子の出力行に Step ID 属性が無く GUI 側の単一スロット `current_running_step_id` で後付け推定していたこと。`contextvars` ベースのインラインマーカー (`[hve:ctx:<step_id>]`) を導入し、行単位で発生元 Step ID を確定できるようにした。

- **[hve/console.py](hve/console.py)**:
  - module-level `ContextVar` `_CURRENT_EMIT_STEP_ID` と公開正規表現 `INLINE_CTX_PATTERN` を追加。
  - `_emit()` で ContextVar に値があれば行頭に `[hve:ctx:<step_id>] ` インラインマーカーを付与する。Workbench (`append_body`) 経路のみ可視で、CLI 単体（stdout）出力ではマーカー無しの文字列を渡し、表示を変えない（Q4=x）。
  - `[hve:stats]` / `[hve:ctx:` で始まる行にはマーカーを重ねない（GUI 側 `_STATS_PREFIX_PATTERN` との互換性確保、二重タグ防止）。
  - `step_start()` の出力順序を「`stats_event(step_status,running)` 発火 → `ContextVar.set()` → 可視行 `▶ [Step.X]` の `_print`」に入れ替え、可視行のプリフィックスが直前の Step ID を引きずる off-by-one を解消。
- **[hve/dag_executor.py](hve/dag_executor.py)**:
  - `_run_with_semaphore()` の冒頭で `_CURRENT_EMIT_STEP_ID.set(step.id)` を実施。`asyncio.create_task` 起点で context がコピーされるため、並列子タスク内の `_emit` 呼び出しがそれぞれ自タスクの Step ID を行頭マーカーに反映する。
- **[hve/gui/workbench_state.py](hve/gui/workbench_state.py)**:
  - `format_log_prefix()` のフォーマットを `[時間] [Workflow ID 大文字] [Step ID] [Sub Task 名]` に刷新（Q3=i）。timestamp 引数を追加し、CLI 出力の `[HH:MM:SS]` を抽出して再配置できるようにした。
  - `_extract_inline_ctx()` / `_extract_timestamp()` ヘルパーを追加。
  - `append_workflow_log()` で行頭インラインマーカーを最優先で Step ID として採用するロジックを追加。`step_log_buffers` への振り分けもインライン値で行うため、並列子の本文行が正しい Step バッファへ蓄積される。
- **[hve/gui/page_workbench.py](hve/gui/page_workbench.py)**:
  - `_apply_plan_mode_prefix()` でも行頭インラインマーカーを最優先で抽出し、`current_running_step_id` フォールバックより上位に採用するよう変更。
- **[hve/gui/tests/test_workbench_state_prefix.py](hve/gui/tests/test_workbench_state_prefix.py)**:
  - 新フォーマット（Q3=i）に対応した期待値へ更新。インラインマーカー抽出ヘルパー、timestamp 付き整形、並列取り違え防止のテストを追加。
- **[hve/tests/test_console_emit_step_context.py](hve/tests/test_console_emit_step_context.py)** (新規):
  - ContextVar 設定/未設定、stats 行スキップ、CLI stdout の strip、並列 asyncio タスクごとの context 独立性を検証する単体テストを追加。
- **[hve/tests/test_console_workbench_bridge.py](hve/tests/test_console_workbench_bridge.py)**:
  - autouse fixture で ContextVar をテスト間にリセットし、漏れ込みを防止。

### Fixed — 共有 Agent プロンプトの Step 別出力先不整合と fan-out プレースホルダ未置換バグの解消

A1 横断調査で判明した、複数 Step を再利用する Agent プロンプトの出力先記述不整合および `output_paths_template` のプレースホルダ未置換バグを解消（本件 `Arch-ARD-UseCaseCatalog` 同型問題の横展開）:

- **F-1 [.github/prompts/Arch-ARD-BusinessAnalysis-Untargeted.prompt.md](.github/prompts/Arch-ARD-BusinessAnalysis-Untargeted.prompt.md)**:
  - `## 1)` 目的部の単一出力先断定（Step 1.2 寄り）を Step 別参照に変更。
  - `## 3) 出力フォーマット` に Step 1（`docs/company-business-recommendation.md`）/ 1.1（`docs/business/{key}-analysis.md`）/ 1.2（`docs/company-business-requirement.md`）の Step 別テーブルを追加。ファイル名 `recommendation.md` と `requirement.md` の取り違え注意を明示。
  - LLM 直接指示部の単一断定 `# 最終出力` を Step 別テーブル参照に変更。

- **F-2 [.github/prompts/QA-DocConsistency.prompt.md](.github/prompts/QA-DocConsistency.prompt.md)**:
  - `## 0) モードディスパッチ` 表を 4 列（モード / 対応 workflow Step / 実行セクション / 出力先）に拡張。4 種の出力先（aad-web Step 3 / akm Step 2 / aqod Step 1 / aqod Step 2）を整理。
  - 旧固定パス記述（`qa/QA-DocConsistency-Issue-<N>.md` / `{WORK}artifacts/doc-consistency-report.md`）を Step 別テーブル参照に置換。`## 6.4` のローカル単独実行向け命名はフォールバックとして残置し、aqod workflow 経由時の優先順位を明示。

- **F-3 [.github/prompts/QA-AzureArchitectureReview.prompt.md](.github/prompts/QA-AzureArchitectureReview.prompt.md), [.github/prompts/QA-AzureDependencyReview.prompt.md](.github/prompts/QA-AzureDependencyReview.prompt.md)**:
  - 単一固定パス記述を、asdw-web 4.x / adfdv 4.x の workflow 別出力先テーブルに置換。adfdv 側の Body テンプレ（`docs/azure/waf-review.md` / `docs/azure/dependency-review.md`）と Agent プロンプトの不整合を解消。

- **F-4 [hve/workflow_registry.py](hve/workflow_registry.py), [.github/prompts/Arch-TDD-TestSpec.prompt.md](.github/prompts/Arch-TDD-TestSpec.prompt.md)**:
  - `hve/fanout_expander.py` の `_make_child` が `{key}` のみを置換する仕様に対し、`output_paths_template` で `{serviceId}` / `{screenId}` / `{agentId}` / `{serviceNameSlug}` / `{screenNameSlug}` を使用していた 6 Step（aad-web 2.1 / 2.2 / 2.3、asdw-web 2.3T / 3.0T、aagd 2.1）を `{key}` に統一。
  - aad-web 2.3 は 2 要素 `output_paths_template`（`{serviceId}` と `{screenId}` の併存）だったが、`fanout_parser="service_catalog"` は `SVC-*` のみ返すため `{screenId}` 用要素は構造的に機能しない設計だった。`{key}` 単一要素に整理（選択肢 α）。
  - Arch-TDD-TestSpec プロンプト `<output_contract>` の出力先記述を Step 別テーブル化（`{key}` 形式 + parser キー命名規約 `SVC-*` / `APP-NN-S###` / `AG-*` を明示）。
  - 既存テスト 141 件 PASS を確認（`test_fanout.py` / `test_existing_output_snapshot.py` / `test_recreate_existing.py` / `test_workflow_registry.py`）。

- **F-5 [hve/workflow_registry.py](hve/workflow_registry.py), [.github/prompts/Arch-AIAgentDesign-Step3.prompt.md](.github/prompts/Arch-AIAgentDesign-Step3.prompt.md), [.github/scripts/templates/aag/step-3.md](.github/scripts/templates/aag/step-3.md)**:
  - aag Step 3 の `output_paths_template=["docs/agent/agent-detail-{agentId}-{agentName}.md"]` を `["docs/agent/agent-detail-{key}.md"]` に修正（F-4 と同型の `{key}` 置換バグ）。プロンプトと workflow_registry でプレースホルダの大文字小文字（`{AgentID}` vs `{agentId}`）まで不一致だった問題も解消。
  - Agent プロンプト L1 / L80 / L102 および Body テンプレ `templates/aag/step-3.md` の `<Agent-ID>-<Agent名>` 表記を `{key}`（= `AG-*`）に統一。Agent 名はファイル名から除外し、`_make_child` が `{key}` のみを置換する仕様と整合。

- **F-6 [template/atdd-template.md](template/atdd-template.md)**:
  - F-4 の `output_paths_template` 修正に追随し、L27 / L37 の参照記述を `{key}-description.md` 形式（`{key}` = `SVC-*` / `APP-NN-S###`）に統一。L14 / L15 / L31 / L41 の AC-ID 命名規約（テスト仕様書内セクション ID、ファイルパスとは別文脈）は維持。

### Fixed — ARD Step 4.2 のユースケース詳細ファイルが `docs/catalog/use-cases/` に誤生成される問題

ARD Step 4.2（ユースケース詳細生成）は `output_paths_template=["docs/usecase/{key}-detail.md"]`（[hve/workflow_registry.py](hve/workflow_registry.py)）と Body テンプレート（`.github/scripts/templates/ard/step-4.2.md`）で正しい出力先を指定しているにもかかわらず、Agent プロンプト `.github/prompts/Arch-ARD-UseCaseCatalog.prompt.md` が Step 4.1/4.2/4.3 共通で「`docs/catalog/use-case-catalog.md` を出力する」とのみ記載していたため、LLM が Step 4.2 実行時に Agent プロンプトの強い文脈に引きずられ、`docs/catalog/use-cases/UC-*.md`（一部はスラッグ付き）に per-UC 詳細を誤生成していた。

- **`.github/prompts/Arch-ARD-UseCaseCatalog.prompt.md`**: `## 1) 目的と非目的` の出力先断定記述を Step 別参照に変更し、`## 3) 出力フォーマット` に Step 4.1 / 4.2 / 4.3 ごとの出力先テーブルと「`docs/catalog/` 配下に per-UC ファイルを作成してはならない」「ファイル名は必ず `{UC-ID}-detail.md` 形式」を明示。
- **`docs/usecase/UC-{02,06,13,14,17,18,19}-detail.md`**: 誤生成されていた 7 ファイル（`docs/catalog/use-cases/` 配下）を正規パス・正規ファイル名にリネーム移動。
- **`docs/usecase/UC-18-detail.md`**: 旧自己参照パス記述（`docs/catalog/use-cases/...`）を新パスに更新。
- **`docs/catalog/use-cases/`**: 空となったディレクトリを削除。

### Fixed — ARD Step 4.2 fan-out が DAG プランから脱落して Step 4.3 が先行起動する問題

GUI Workbench の作業状況ツリーが DAG 通りに起動しない根本原因を修正。ARD Step 4.2 は `fanout_parser="use_case_skeleton"` を持ち、その入力ファイル `docs/catalog/use-case-skeleton.md` は同一実行内の **Step 4.1** が生成する設計だが、`orchestrator._expand_workflow_for_dag()` はプランニング時点で fan-out を静的展開しており、parser が「ファイル不在」を 0 件として返した結果、Step 4.2 が `empty_fanout_ids` 経由で `active_step_ids` から discard されていた。これにより DAG プラン自体に Step 4.2 が含まれず、Step 4.3 (`depends_on=["4.2"]`) が `auto-skip-inactive` 経路で先行起動していた。

修正方針 (Option 1: 遅延展開): 「同一実行内の upstream step が parser 入力を生成する見込みの fan-out base」を `deferred_fanout_ids` として識別し、プランニング時には active に残したまま、`DAGExecutor.execute()` のメインループで upstream 完了後にランタイム再展開する。

- **`hve/catalog_parsers.py`**: parser 名 → 主入力ファイルパスの SSOT マッピング `_PARSER_INPUT_PATHS` と公開関数 `get_parser_input_path(name)` を追加。
- **`hve/fanout_expander.py`**:
  - `ExpandedWorkflow` に `deferred_fanout_ids: List[str]` フィールドを追加（orchestrator が後付けで設定）。
  - `expand_single_step_fanout(base_step, repo_root)` を新設し、単一 base step を runtime に再展開する API を公開。
- **`hve/orchestrator.py:_expand_workflow_for_dag`**: `empty_fanout_ids` のうち、base の `depends_on` 推移閉包に「parser の入力パス（`get_parser_input_path` 由来）を `output_paths` / `output_paths_template` に持つ step」が存在するものを `deferred_fanout_ids` に振り分け、`active_step_ids` から discard しないようガード。
- **`hve/orchestrator.run_workflow` 内 `DAGExecutor` 呼び出し**: `deferred_fanout_ids` / `on_dynamic_expand` / `workflow_id` を伝搬し、ランタイム展開時に `resume_state.step_states` と `selected_step_ids` を子 ID で更新するコールバックを実装。
- **`hve/dag_executor.py:DAGExecutor`**:
  - `__init__` に `deferred_fanout_ids` / `on_dynamic_expand` / `workflow_id` を追加。
  - 起動時 empty-skip ループで deferred ID を skip 対象から除外。
  - `_try_dynamic_expand(reason)` を新設。execute() メインループ先頭で deferred 集合を走査し、依存が解決済みの base に対して `expand_single_step_fanout` を呼び、成功時に `_expanded_steps` / `_workflow_step_index` / `active_step_ids` / `_fanout_map` / `_fanout_child_to_parent` / `_dynamic_fanout_remaining` / `_dynamic_child_ids` を mutate し、`stats_event("fanout_init", ...)` を再 emit し、`on_dynamic_expand` フックを呼ぶ。0 件確定時は `fanout-empty` で skip 化して deferred から外し無限リトライを防止。
  - `_maybe_mark_dynamic_fanout_parent_complete(child_id)` を新設。動的展開された子完了で残数を decrement し、全子完了時に base を `fanout-aggregated` reason で `completed` に昇格させ、下流 step の `depends_on=["<base>"]` を満たす。
  - executable フィルタに `s.id not in self._deferred_fanout_ids` と `s.id not in self._dynamic_fanout_remaining` を追加し、base 自体が通常 step として実行されないようガード。
  - `_get_next_steps` に動的展開された子 (`_dynamic_child_ids`) の overlay を追加し、`dag_plan.nodes` (frozen) に含まれない子も解決できるよう拡張。
  - execute() メインループに `_newly_expanded → continue` フェイルセーフを追加し、展開直後の早期 break を防止。
- **テスト**:
  - `hve/tests/test_catalog_parsers_input_paths.py` (新規): `get_parser_input_path` と `_PARSER_INPUT_PATHS` の SSOT 整合性。
  - `hve/tests/test_fanout.py` (追記): `expand_single_step_fanout` の 5 ケース（static_keys / non-fanout / empty parser / file present / 非破壊性）。
  - `hve/tests/test_deferred_fanout.py` (新規): `_expand_workflow_for_dag` の deferred 判定 5 ケース（ARD 実 case / 単独 / 非 fanout / 推移依存 / output_paths_template マッチ）。
  - `hve/tests/test_dag_executor_fanout_deferred.py` (新規): DAGExecutor の deferred fan-out ランタイム再展開 E2E 2 ケース（ハッピーパス / 入力空のまま完了→skip）。

### Fixed — GUI Workbench エクスプローラーでの動的ファイル追加時の Qt モデル契約違反

`MultiRootFileModel.refresh_directory` が `beginInsertRows()` を発行する**前に** `_ensure_loaded(node)` を呼び出し、`node._children.append(...)` で内部状態を直接変更してしまっていた問題を修正。Qt のモデル契約では `beginInsertRows` の呼び出し時点でモデルの `rowCount()` はまだ旧件数を返す必要があるが、旧実装では既に新しい子ノードを追加してから挿入通知を発行していたため、ビュー側のキャッシュ（行マッピング・`setUniformRowHeights=True` 時の行サイズキャッシュ）が不整合となり、起動中に新規追加されたファイルが空行のように見える可能性があった。

- **`hve/gui/file_explorer/multi_root_model.py`**:
  - 純粋関数ヘルパ `_scan_children(node)` を新設し、scandir 結果を新しい `_Node` リストとして返すだけでモデル状態を変更しない設計に分離。
  - `_ensure_loaded` を `_scan_children` 経由に統一。
  - `refresh_directory` を Qt 契約準拠の順序に修正: `beginRemoveRows → 子クリア → endRemoveRows → _scan_children でローカル構築 → beginInsertRows → 子リスト差し替え → endInsertRows`。

### Changed — GUI Workbench エクスプローラーの行間を圧縮

GUI Workbench の「エクスプローラー」ペインで、ファイルツリーのアイテム間に過剰な縦余白が発生していた問題を修正。`QTreeView` のデフォルト行高さがスタイル依存で大きく確保されていたため、アイコンサイズの固定とデリゲートでの行高さ制御により無駄な余白を排除した。

- **`hve/gui/file_explorer/file_tree_panel.py`**: `QTreeView` に `setIconSize(QSize(16, 16))` を追加し、アイコン高さを 16px に固定。
- **`hve/gui/file_explorer/file_tree_delegate.py`**: `FileTreeDelegate.sizeHint` で行高さを `max(fontMetrics.height() + 2, 16)` に設定し、フォントメトリクスベースのコンパクトな行高さを実現（アイコン切れ防止のため下限 16px を保証）。

### Fixed — GUI Workbench ワークフロー選択チェックボックス操作時の小ウィンドウフラッシュ

GUI Workbench の Step 1（ワークフロー選択）でチェックボックスをトグルするたびに、小さな空ウィンドウが一瞬表示されてすぐ閉じる挙動を修正。原因は、可視状態の `QWidget` に対して `setParent(None)` を呼んだ直後に `deleteLater()` する Qt のアンチパターンを 3 箇所で踏んでおり、`deleteLater()` が次イベントループまで遅延される間に orphan widget がトップレベルウィンドウとして一瞬描画されていたため。コードベース内には既に正解パターン（バナー救出処理、`hve/gui/page_options.py` の `_evacuate_labeled_fields`）が `setParent(self); setVisible(False)` を採用しており、それと整合する形に修正。

- **`hve/gui/page_options.py`**:
  - `_refresh_specific_categories`: 既存ワークフロー枠（`QGroupBox`）破棄ループで `box.setParent(None)` の直前に `box.setVisible(False)` を追加。
  - `_evacuate_labeled_fields`: AttachmentPane 救出処理が `setParent(None)` のみだった箇所を、バナー救出と同形の `setParent(self); setVisible(False)` に修正。
- **`hve/gui/page_workflow_select.py`**:
  - `_rebuild_steps_panel`: 選択解除されたワークフローのステップ群（`_WorkflowStepsGroup`）破棄処理で `grp.setParent(None)` の直前に `grp.setVisible(False)` を追加。

### Fixed — GUI Workbench Step 1 バナーの誤検知（Autopilot ON × ARD/AAS のみ選択時に `app-arch-catalog.md` を不要に警告）

GUI Workbench `Step 1` の必須要件サマリーバナーが、**Autopilot ON** かつ Software Engineering 系ワークフロー（`aad-web` / `asdw-web` / `adfd` / `adfdv`）が **未選択** の状態（例: `ARD` + `AAS` のみ選択）でも、無条件に `docs/catalog/app-arch-catalog.md` を warn 表示していた問題を修正。実 Autopilot 実装（`hve/autopilot/plan_review_gap.py` の `_AUTOPILOT_IMPLICIT_REQUIRED_PATHS` および `hve/autopilot/planner.py` の `pre_phase_only` モード）では当該カタログは SE 系ワークフロー選択時のみ必須であり、Autopilot ON/OFF で入力チェック結果が乖離していた。

- **`hve/gui/workflow_step_requirements.py`**:
  - 新規定数 `_AUTOPILOT_CATALOG_REQUIRING_WORKFLOWS = ("aad-web", "asdw-web", "adfd", "adfdv")` を追加。
  - `summarize_requirements_for_selection(autopilot_mode=True)` を改修: 選択中ワークフローに上記 SE 系がステップ 1 件以上選択されている場合のみ Autopilot 仮想ワークフローサマリーを返し、それ以外は通常モード（`pick_target_step` 経由）と同じ要件を返すフォールバック動作に変更。これにより Autopilot ON/OFF で同一選択時の入力チェック結果が一致する。

- **`hve/gui/page_options.py`**:
  - `_refresh_requirements_banner` を共通入口 `summarize_requirements_for_selection` 経由にリファクタ。従来は Autopilot 分岐で `summarize_requirements(AUTOPILOT_PSEUDO_WORKFLOW_ID, ...)` を直呼びしておりバナーと Precheck（`run_step1_precheck`）でロジック分岐が二重化していた問題も解消。未使用となった `pick_target_step` / `summarize_requirements` の import を削除。

- **テスト**:
  - `hve/gui/tests/test_workflow_requirements_banner.py`: 回帰防止テストを 3 件追加（Autopilot ON × ARD/AAS のみ→ARD 要件、Autopilot ON × `aad-web` 選択→Autopilot 仮想、SE 系 WF があってもステップ未選択なら Autopilot 仮想にならない）。
  - `hve/tests/autopilot/test_precheck_runner.py`: 既存の `test_runner_autopilot_mode_satisfied_when_catalog_exists` / `test_runner_autopilot_custom_catalog_path` を新仕様に合わせて更新（`aad-web` を選択 WF に追加）。Autopilot ON + ARD のみで catalog 不要を確認する `test_runner_autopilot_mode_no_se_workflow_skips_catalog_check` を新規追加。

### Changed — `infra/` および `test/` 配下を `src/infra/` および `src/test/` に統一（破壊的変更）

`asdw-web` / `adfdv` ワークフローを含む全ワークフローで生成・参照される `infra/azure/` 配下のスクリプトおよび `test/{api,ui,agent,dataflow,e2e}/` 配下のテストコードを、`src/infra/` および `src/test/` にパス変更。「全てのソースコード（インフラ・テスト含む）の出力先を `/src` 配下に統一」というユーザー要件への対応。Q1=A（階層温存）、Q2=P（物理移動）、Q3=R（旧パス削除）、Q4=U（root 直下出力の異常宣言も修正対象）、Q5=V（ignore_paths 整理）、Q6=X（コメント例示も更新）の決定に基づく。

- **Python ランタイム**:
  - [hve/config.py](hve/config.py) `SDKConfig.ignore_paths` から `"infra"` / `"test"` を削除（`"src"` が既に含まれており `src/infra/`・`src/test/` は自動 ignore）。
  - [hve/orchestrator.py](hve/orchestrator.py): `_collect_file_samples` に `exclude_prefixes` 引数を追加し、`src_files` 検出時に `src/test/` を除外（リグレッション対策）。`test_files` 検出を `_collect_file_samples("src/test", limit=30)` に、`_ARTIFACT_KEY_TO_EXPECTED_PATH["test_files"]` を `"src/test/**/*"` に変更。
  - [hve/tests/test_orchestrator.py](hve/tests/test_orchestrator.py): `test_ignore_paths_default_in_config` を新規定に合わせて `assertNotIn("infra")` / `assertNotIn("test")` 追加。
  - [hve/workflow_registry.py](hve/workflow_registry.py): asdw-web Step 4.2 のコメント `infra/` → `src/infra/`。

- **io-contract YAML（29 ファイル）**: adfdv 系 (6)、asdw-web 系 (9)、aagd 系 (3)、aas (1)、非バリアント親契約 (10) すべての `path:` を `src/infra/` / `src/test/` へ更新。`Dev-Dataflow-ServiceCoding--adfdv--2.2.yaml` のリポジトリルート直下出力 `batch-monitoring-design.md` および `Dev-Microservice-Azure-UITestCoding--asdw-web--3.0TC.yaml` の `test-strategy.md`、`Dev-Microservice-Azure-ComputeDeploy-AzureFunctions--asdw-web--2.5.yaml` の `compute-functions-rollback.md` を異常宣言として削除（重複入力で代替済み）。

- **io-contract-exceptions**: [.github/io-contract-exceptions.yaml](.github/io-contract-exceptions.yaml) の `static_paths` から `test/*`・`infra/*` を削除し `src/test/*`・`src/infra/*` に置換。

- **Prompts（16 本以上）**:
  - ADFDV 系 5 本 (`Dev-Dataflow-{DataServiceSelect,DataDeploy,TestCoding,ServiceCoding,FunctionsDeploy}.prompt.md`)。
  - ASDW-Web 系 8 本 (`Dev-Microservice-Azure-{DataDeploy,AddServiceDeploy,ServiceTestCoding,ServiceCoding-AzureFunctions,ComputeDeploy-AzureFunctions,UITestCoding,UICoding,UIDeploy-AzureStaticWebApps}.prompt.md`)。
  - AAGD/AAG 系 5 本 (`Dev-Microservice-Azure-{AgentTestCoding,AgentCoding,AgentDeploy,AgenticRetrievalDesign,AgenticRetrievalDeploy}.prompt.md`)。
  - Arch-TDD 系 3 本 (`Arch-TDD-TestStrategy`, `Arch-TDD-TestSpec`, `Arch-Dataflow-TDD-TestSpec`)。
  - `Dev-Dataflow-ServiceCoding.prompt.md` の `batch-monitoring-design.md` 3 箇所参照を `docs/dataflow/dataflow-monitoring-design.md`（入力リストに既存の正式パス）に修正。

- **Template / Fanout (12 ファイル)**: `.github/scripts/templates/asdw-web/` 7 本、`.github/scripts/templates/adfdv/` 2 本、`hve/prompt/fanout/{asdw-web,adfdv,aagd}/_common.md`。

- **GitHub Actions ワークフロー**:
  - `.github/workflows/auto-app-dev-microservice-web-reusable.yml` / `auto-ai-agent-dev-reusable.yml` / `auto-dataflow-dev-reusable.yml`: Issue body 埋め込みの printf テンプレート内パス更新（主要箇所をカバー、aagd の test/ui/ など一部 multi-match パターンは未完）。
  - `.github/workflows/bats-tests.yml`: `paths` フィルタ `infra/azure/**` → `src/infra/azure/**`。
  - `.github/workflows/e2e-playwright-reusable.yml`: デフォルト `test/e2e/playwright` → `src/test/e2e/playwright`。
  - `.github/workflows/rollback-drill.yml`: `infra/azure/rollback/...`, `infra/azure/verify-webui-resources.sh` → `src/infra/...`。

- **Issue Templates**: `.github/ISSUE_TEMPLATE/sourcecode-to-documentation.yml`（placeholder）、`.github/ISSUE_TEMPLATE/web-app-dev.yml`（説明文）。

- **ドキュメント / Skills**:
  - [.github/copilot-instructions.md](.github/copilot-instructions.md) §0 の `infra/.../README.md` 例 → `src/infra/.../README.md`。
  - [docs/catalog/test-strategy.md](docs/catalog/test-strategy.md) 既存テスト資産パス。
  - Skills references: `agent-common-preamble/references/agent-playbook.md`, `work-artifacts-layout/references/directory-structure-detail.md`, `cicd/github-actions-cicd/references/cicd-common-spec.md`, `harness/harness-safety-guard/references/danger-patterns.md`, `harness/harness-verification-loop/references/verification-commands.md`, `repo-onboarding-fast/references/onboarding-examples.md`。
  - Skills evals: `_evals/azure-prepare.eval.yaml`, `_evals/azure-deploy.eval.yaml`。
  - `users-guide/05-app-dev-microservice-azure.md`（残存: 06/08/agentic-retrieval-guide/hve-cloud-getting-started/SVG 画像は同パターン未完）。

- **.gitignore**: `test/api/*/{bin,obj}` → `src/test/api/*/{bin,obj}`、`!test/api/smoke-ui/...` → `!src/test/api/smoke-ui/...`、`infra/azure/create-azure-agent-resources/agent-ids.env` → `src/infra/azure/...`。

### Migration

- **物理ファイル移動は未実施**: `test/` 配下 259 ファイル（うち 23 .csproj、18 ファイルは `..\..\..\src\` / `..\..\..\docs\` の相対参照あり）の `git mv test src/test` は、`dotnet.exe` プロセス（PID 69460、VS Code C# 拡張機能等）が `test/` 配下のファイルをロックしていたため失敗。**手動で VS Code を閉じてから `git mv test src/test` を実行し、その後 csproj/README の相対パスを以下の規則で補正する必要がある**:
  - csproj `<ProjectReference Include="..\..\..\src\api\...">` → `..\..\..\api\...`（階層数は同じ、`src` を削除）
  - csproj `<None Include="..\..\..\docs\...">` および README Markdown リンク `../../../docs/...` → 階層 +1（`..\..\..\..\docs\...`）
  - 影響: `test/api/{AccountingService,CustomerSupportService,RewardReservation,SVC-01,SVC-02,SVC-05,SVC-06,SVC-07,SVC-13,SVC-14,SVC-15,SVC-16,SVC-17,SVC-18,SVC-19}.Tests/*.{csproj,md}` の 18 ファイル
- **既存ブランチ / Issue / PR の旧パス**: 本変更は破壊的変更。旧パス前提のブランチ・Issue body・PR body は手動 rebase / 編集が必要。
- **既存 docs/test-specs/, docs/services/ 配下の生成済みドキュメント**: 旧パスのまま残存。次回エージェント実行時に再生成されることで自然解消する想定（既存ファイルを手動修正する必要はなし）。
- **vestigial templates**: `.github/scripts/templates/asdw/`, `aagd/` は `workflow_registry.py` から参照されておらず未更新のまま残置（将来のクリーンアップ対象）。

### 検証

- `hve/tests/test_workflow_registry.py` + `test_consumed_artifacts.py` + `test_input_artifact_check.py`: **189/189 PASS**。
- `hve/tests/test_orchestrator.py::test_ignore_paths_default_in_config`: **PASS**。
- `validate-io-contract.py`: 既存の構造的エラー（path-prefix とは無関係）以外に新規エラーなし。
- `infra/`/`test/` 旧パス残存: 主要ランタイムコード・io-contract・主要 prompt・主要 template から消去確認。残存 105 ファイルはほぼ生成済み docs と vestigial templates、SVG 画像、users-guide 残ファイルで実行影響なし。

<!-- validation-confirmed -->

---

### Changed — `users-guide/plugin-mcp-auth.md` を全面リライト

旧版が参照していた `hve/gui/auth_providers/` 配下の manifest システム（2026-02 のコミットで削除済み）および `hve/gui/pty_auth_controller.py` / `hve/gui/pty_auth_session_widget.py`（過去・現在とも本リポジトリに存在せず）への参照を撤去し、現状の実装（[hve/gui/main_window.py](hve/gui/main_window.py) で 🔐 ボタンは廃止、認証は GitHub Copilot CLI 側で完結）に整合した内容へ更新。あわせて GitHub Copilot CLI 公式ドキュメントに基づく `/mcp add` / `/login` フローおよび `~/.copilot/mcp-config.json` への誘導を追加。

- **章構成**: バナー（ユーザー影響 / 実装状況 / 公式ルート）→ §1 概要（ユーザー影響サマリ・実装状況表・廃止済み設定キー）→ §2 公式ルート（`/mcp add`・保存先・`/login`・サービス別参照先・非対話セットアップ）→ §3 HVE GUI/CLI からの利用（`copilot_cli_bridge.py` の現状と公式ドキュメントとの差異・設定マイグレーション・CLI 引数経路）→ §4 トラブルシューティング（PTY/xterm.js/Azure CLI/検証済みバージョン/機密情報）→ §5 関連ドキュメント、の 5 章構成に再編。
- **削除した記述**: 同梱認証 manifest 表、`HVE_AUTH_MANIFESTS_DIR` / `load_all_manifests()` を前提とするカスタム manifest セクション、GUI 🔐 ボタン経由の操作手順（Azure MCP / GitHub MCP / Microsoft Work IQ / 任意の MCP サーバ）、`PtyAuthSessionWidget` を前提とするトラブルシュート Q、公式裏付けの取れない `copilot mcp add` / `copilot plugin install` のコマンド例。
- **追加した記述**: 削除済み・未実装ファイルを区別する実装状況表、[hve/gui/page_options.py](hve/gui/page_options.py) から [hve/gui/copilot_cli_bridge.py](hve/gui/copilot_cli_bridge.py) 経由で `copilot mcp list --json` / `copilot mcp get --json` / `copilot plugin list` / `copilot login` を呼び出している実装事実（公式ドキュメントには未掲載である旨を明記）、GUI 設定の `mcp_config` / `workiq_tenant_id` は `[options]` セクション限定で自動マイグレーション削除される挙動、CLI 引数 `--mcp-config` / `--workiq-tenant-id` および環境変数 `WORKIQ_TENANT_ID` 経路が引き続き有効である事実、Azure MCP の現行リポジトリ（`microsoft/mcp` モノレポ）と旧 `Azure/azure-mcp` のアーカイブ事実、`pywinpty>=2.0` / `ptyprocess>=0.7` の pyproject.toml 宣言。
- **根拠**: リポジトリ内コード（[hve/__main__.py](hve/__main__.py) の `--mcp-config` / `--workiq-tenant-id` 受理および `_load_mcp_config` 消費、[hve/config.py](hve/config.py) の `WORKIQ_TENANT_ID` 環境変数取得、[hve/gui/settings_store.py](hve/gui/settings_store.py) の `_OBSOLETE_KEYS`、[hve/gui/main_window.py](hve/gui/main_window.py) の 🔐 ボタン廃止コメント、[hve/gui/copilot_cli_bridge.py](hve/gui/copilot_cli_bridge.py) の subprocess 呼び出し）と pyproject.toml 宣言を突き合わせ、GitHub Copilot CLI 公式ドキュメント（`about-copilot-cli` / `use-copilot-cli/overview`）および Azure MCP / GitHub MCP の公式リポジトリ README を fetch で確認。

### Fixed — fan-out 親に依存する fan-out 親の子 step が依存元未完了で起動する不具合（aad-web Step 2.3 ほか）

`hve` GUI の Workbench 「作業状況」ツリーで、`aad-web` Step 2.3（TDDテスト仕様書）の fan-out 子（`2.3/SVC-*`）が依存元 Step 2.1（画面定義書）/ 2.2（マイクロサービス定義書）の fan-out 子完了を待たずに同一 Wave で起動される事象を修正。同型の依存（fan-out 親 → fan-out 親）を持つ他ワークフロー（`adoc` Step 3.1〜3.5、`asdw-web` の fan-out 連鎖、`adfdv` Step 2.1〜2.2、`aag`/`aagd` の `agent_catalog` 連鎖など）でも同様の症状が発生していた可能性があり、本修正で一括解消。

- **根本原因**: [hve/fanout_expander.py](hve/fanout_expander.py) の `expand_workflow_fanout` における depends_on の「ベース ID → 子 ID リスト」張り替え処理が、`pass_through`（非 fan-out 下流ステップ）にしか適用されていなかった。fan-out 子自身（`children_by_base` 側）は `_make_child` が親 StepDef の `depends_on` を raw な形でそのまま継承（例: 2.3 の各子が `depends_on=["2.1", "2.2"]`）したまま expanded_steps に追加されていた。展開後の workflow には `"2.1"` / `"2.2"` というベース ID は存在せず（`"2.1/APP-NN-S001"` 等の子 ID のみ）、[hve/workflow_registry.py](hve/workflow_registry.py) `get_next_steps` および [hve/dag_executor.py](hve/dag_executor.py) `_get_next_steps_from_expanded` の依存解決ルール「`dep not in existing_ids → 解決済み（自動スキップ）`」により、生 ID `"2.1"` / `"2.2"` が無条件で解決済み扱いとなり、2.3 子が Wave 1 に同時投入されていた。
- **修正内容**:
  - [hve/fanout_expander.py](hve/fanout_expander.py): depends_on 張り替え処理を `_remap_deps(step)` ヘルパに抽出し、`pass_through` ステップと `children_by_base` 配下の fan-out 子の両方に適用するよう変更。クロス積（fan-out 子 C は依存元 fan-out 親 A の全子 ID と B の全子 ID を待つ）を採用（fan-out キー体系が依存元と一致する保証がないため）。
  - [hve/tests/test_fanout.py](hve/tests/test_fanout.py): 回帰テスト `test_fanout_child_depends_on_fanout_parent_is_remapped` を追加。fan-out 親 A (keys=a1,a2), B (keys=b1) に依存する fan-out 親 C (keys=c1,c2) を展開したとき、C の各子の depends_on が `{A/a1, A/a2, B/b1}` に張り替えられ、生 ID `"A"` / `"B"` が残っていないことを assert。
- **検証**: `hve/tests/test_fanout.py` 全 20 件 PASS、`-k "dag or fanout or wave"` キーワードで 123 件 PASS、`test_orchestrator.py::TestRunWorkflowDryRun::test_aad_web_fanout_meta_is_forwarded_to_step_runner` PASS。

### Fixed — Workbench 作業状況ツリーで Autopilot 経路の fan-out 子進捗が反映されない不具合

`hve` GUI の Workbench 「作業状況」ツリーで、**Autopilot 経路**でのみ fan-out 親 step（例: `aad-web` の `2.3`）が `pending` 表示のままタイマー進行しない事象を修正。Plan モードでは下記の Plan モード対応エントリで既に修正済みだったが、Autopilot 経路（`MainWindow._build_autopilot_workflow_seeds` 由来の `instance_id = "{wf}#{app}"` 形式）では `_apply_log_line_to_instance_tree` 内で `<base>/<key>` 形式の `step_id` を解決できず無音破棄されていた。

- **根本原因**: [hve/gui/page_workbench.py](hve/gui/page_workbench.py) の `_resolve_step_id_for_instance` は dotted prefix の 1 段 bubble-up のみ対応で、`/` 区切りの fanout suffix を strip する経路がなかった。結果として `step_id="2.3/SVC-14"` の running イベントが state に反映されず、`DagStatusWidget` の `_step_started_at[(instance, "2.3")]` も発火せずタイマーが進行しなかった。
- **修正内容**:
  - [hve/gui/page_workbench.py](hve/gui/page_workbench.py): `_apply_fanout_init_in_instance` / `_apply_fanout_child_status_in_instance` を新規追加（Plan モード版と同等の集約ロジックを Instances 木 `state.workflows[instance_id].steps` 上で実行）。集約対象は `kind=="fanout_child"` の子のみフィルタ。集約規則は Plan 版と一致（子に running 1 件以上 → base=running／`_fanout_initialized[instance_id]` 登録済みで全子 terminal → base=`failed` if any failed else `done`／それ以外は早期完了防止）。
  - [hve/gui/page_workbench.py](hve/gui/page_workbench.py): `_apply_log_line_to_instance_tree` に `kind=="fanout_init"` 分岐と `step_status` の `/` 含み step_id 分岐を追加。`instance_id` 引数のみを使用し `_current_workflow_id` には依存しない（Autopilot 並列実行で複数 instance が共存するため）。
  - [hve/gui/tests/test_autopilot_stats_propagation.py](hve/gui/tests/test_autopilot_stats_propagation.py): Autopilot 経路の回帰テスト 5 ケースを新規追加（fanout_init seed / 子 running→base running / 全子 done→base done 集約 / plan 外 base 無視 / fanout_init 不在時の早期完了防止）。全 PASS を確認。

### Fixed — Workbench 作業状況ツリーで fan-out 子の進捗が反映されない不具合

`hve` GUI の Workbench 「作業状況」ツリーで、fan-out 親 step（例: `aad-web` の `2.1`「画面定義書」）が常に「実行中」のまま固定され、次の base step に進んでも前 step が完了状態へ遷移しない事象を修正。

- **根本原因**: fan-out 子の `step_id` は `<base>/<key>` 形式（例: `2.1/APP-09-S006`）で発火されるが、GUI 側の `_apply_stats_step_status` ([hve/gui/page_workbench.py](hve/gui/page_workbench.py)) は plan に登録された base ID（`2.1`）のみを `_workflow_step_status` のキーにしていたため、子イベントが `if step_id not in wf_step_map: return` で**無音破棄**されていた。同じく `_update_workflow_progress_from_line` のテキストパース経路でも同様。
- **影響範囲**: [hve/workflow_registry.py](hve/workflow_registry.py) で fan-out 定義は計 24 箇所（screen_catalog / service_catalog / dataflow_catalog / agent_catalog / app_catalog / 静的 D01〜D21 等）あり、全ワークフローで base step の進捗反映が壊れていた。
- **修正内容**:
  - [hve/orchestrator.py](hve/orchestrator.py): fan-out 展開直後に新規 `stats_event("fanout_init", workflow_id, base_id, child_ids)` を 1 回 emit。
  - [hve/gui/page_workbench.py](hve/gui/page_workbench.py): `_apply_stats_fanout_init` を新規追加し、`_workflow_subtask_status` に子を seed。`_apply_stats_step_status` を改修し、`<base>/<key>` 形式の step_id を `_apply_fanout_child_status` へルーティング。集約ルールは「子に running 1 件以上 → base=実行中／fanout_init 受信済みで全子 terminal → base=完了」。fanout_init 未受信時は早期完了を防ぐためゲートあり。`_update_workflow_progress_from_line` のテキストパース経路にも同等の正規化を追加。
  - [hve/gui/tests/test_page_workbench_fanout_progress.py](hve/gui/tests/test_page_workbench_fanout_progress.py): 集約ロジックの単体テスト（8 ケース）を新規追加し全 PASS を確認。

### Fixed — hve オーケストレーター入出力宣言の整合性是正（io-contracts × workflow_registry 二重宣言乖離・汚染 YAML・StepDef 循環依存）

監査対象 6 ワークフロー（ARD / AAS / AAD-Web / ASDW-Web / ADFD / ADFDV、計 54 非コンテナステップ）と関連 Agent の io-contract（77 ファイル中）を中心に、`hve/workflow_registry.py` の StepDef と `.github/io-contracts/*.yaml` の宣言乖離・汚染エントリ・StepDef レベルの循環依存を是正。HVE ランタイムの権威ソースは StepDef 側であることを `hve/existing_artifact_snapshot.py` / `hve/autopilot/plan_review_*.py` の参照から確定し、io-contract を StepDef に整合させる方向で修正。Phase 3 の path 置換と Phase 3.4 のプレースホルダ統一は対象外ワークフロー（AAG/AAGD等）の io-contract にも波及して整合性向上。

主な是正内容:

- **StepDef 構造的循環依存解消（A-1）**: AAS Step 6（Arch-Microservice-ServiceCatalog）が AAD-Web Step 1 出力 `docs/catalog/screen-catalog.md` を `required_input_paths` に列挙していた逆流を解除。`hve/workflow_registry.py` Step 6 から削除し、io-contract 側も `required: false` に降格。
- **設計フェーズへの dev フェーズ成果物逆流解消（A-2）**: `Arch-TDD-TestStrategy.yaml` inputs から `test/`、`test/api/<ServiceName>.Tests/`、`test/api/*.Tests/`、`test/SVC-*/smoke-test.sh`、`docs/catalog/screen-catalog.md` を削除。
- **ARD Step 4.1 skip 経路失敗解消**: `required_input_paths=["docs/business-requirement.md"]` を `[]` に変更。`docs/business-requirement.md`（Step 2 出力）と `docs/company-business-requirement.md`（Step 1.2 出力）はいずれも skip_fallback により片方しか生成されない経路があるため、`consumed_artifacts` 経由のオプション参照に降格。
- **汚染 io-contract YAML の清掃**: 自動生成由来と思われる以下の不正な `path:` エントリを除去:
  - `<details><summary>Prompt を表示</summary>` (4 ファイル: Arch-ARD-BusinessAnalysis-Untargeted/Targeted、Arch-ARD-UseCaseCatalog)
  - Markdown 見出し `# 推奨 KPI / OKR 定義書` (Arch-ARD-KPIOKRDefinition)
  - ステータス文字列 `❌未処理（矛盾検出/質問待ち）` (Arch-ArchitectureCandidateAnalyzer)
  - ログ書式例 `YYYY-MM-DD HH:MM (UTC): ...` / `[OK] / [FAIL] / [CRITICAL] / [ERROR]` (Dev-Microservice-Azure-DataDeploy)
  - CLI 引数・GitHub Action 識別子 `app_location=src/app/` / `Azure/static-web-apps-deploy@v1` 等 (Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps)
- **`kind` 種別の誤分類訂正**:
  - `work/kpi/fork-kpi-<run_id>.jsonl` を `agent_artifact` → `external` (QA-DocConsistency)
  - `infra/`、`config/`、`.github/workflows/` を `agent_artifact` → `external` (QA-AzureDependencyReview)
  - `src/api/` に正しい producer (Dev-Microservice-Azure-ServiceCoding-AzureFunctions) を設定
  - `docs/architectural-requirements-app-xx.md` を `agent_artifact` → `external` + `{appId}` プレースホルダ化 (Arch-ArchitectureCandidateAnalyzer)
- **path 命名統一（io-contract を StepDef 側に整合）**:
  - `docs/domain-analytics.md` → `docs/catalog/domain-analytics.md`（15 ファイル）
  - `docs/test-strategy.md` → `docs/catalog/test-strategy.md`（7 ファイル）
  - `data/sample-data.json` → `src/data/sample-data.json`（5 ファイル）+ `data/sample-data.{index.md,part-*.json}` を `src/data/` プレフィックスに正規化
- **プレースホルダ表記統一**: io-contract 内の日本語プレースホルダ `{画面ID}` / `{画面名スラッグ}` / `{サービス名}` / `{サービスID}` / `{ジョブID}` / `{ジョブ名スラッグ}` を英語 (`{screenId}` / `{screenNameSlug}` / `{serviceNameSlug}` / `{serviceId}` / `{jobId}` / `{jobNameSlug}`) に統一（10 ファイル）。
- **knowledge ファイル名の短縮表記訂正**: `knowledge/D01`、`knowledge/D08`、`knowledge/D15` 等の不完全パスを正式ファイル名（`D01-事業意図-成功条件定義書.md` 等）に修正。
- **`FULL_PIPELINE` 依存宣言の補完**: `aad-web` の AAS 依存に `docs/catalog/service-catalog-matrix.md` を追加。`ARTIFACT_DESCRIPTIONS` マスタにも対応エントリ「サービスカタログマトリクス」を追加。

### Changed — `.github/scripts/validate-io-contract.py` を StepDef 突き合わせ機能込みに拡張

`.github/io-contracts/*.yaml` 内部の producer/consumer 整合性のみを検査していたバリデーターを、`hve/workflow_registry.py` の StepDef との宣言突き合わせ機能込みに拡張。

- スキーマ検査強化: `required: true && kind: agent_artifact` のとき `producer` が非空文字列であることを必須化（従来は `producer: ''` を許容していたため汚染エントリがすり抜けていた）。
- 新カテゴリ `registry_mismatch_errors`: 全ワークフロー × 全 StepDef を走査し、各 Step の `output_paths` / `output_paths_template` / `required_input_paths` を対応 Agent の io-contract `outputs` / `inputs(required=true)` と path 文字列照合。差分を ERROR として報告。
- 既存 CI ワークフロー `.github/workflows/validate-io-contract.yml` はコマンド変更不要（同スクリプトを呼ぶだけ）。
- `--no-registry-check` オプションで registry 突き合わせをスキップ可能（互換性確保）。

### Changed — `.github/io-contracts/SCHEMA.md` を更新

命名規約に「`Issue-<識別子>`、`<NNN>`、`<run_id>` 等の work-artifacts-layout / 共通行動規約由来の山括弧プレースホルダは許容」を明示。SCHEMA.md と work-artifacts-layout Skill との整合を取った。

### Removed — `tools/check_io_contracts.py` を削除

StepDef × io-contract 突き合わせロジックを `.github/scripts/validate-io-contract.py` に統合したことに伴い、独立スクリプトを削除。本変更前は調査用に一時的に作成していた監査ツール。

### 検証

- `python .github/scripts/validate-io-contract.py` の指標推移:

| 指標 | v1〜v2 監査時 | v3 最終 |
|---|---|---|
| io-contract ファイル形式 | per-Agent 77 | per-Step 85 |
| Schema errors | 45（後 31） | **0** |
| Integrity errors | 0 | **0** |
| Registry mismatch | 732（新規導入時） | **394**（敵対的レビュー後の上流依存補完で 431）|

- `integrity_errors` は 0 を維持。
- 既存テストの実行結果: `hve/tests/test_workflow_registry_ard.py`、`hve/tests/test_phase8_s4_reinforcement.py`、`hve/tests/test_input_artifact_check.py`、`hve/tests/test_orchestrator_ard.py`、`hve/tests/autopilot/test_precheck_runner.py`、`hve/tests/autopilot/test_plan_review_runner.py` 合計 100 件全件 PASS。
- 既知の限界事項: registry_mismatch_errors 394 件残存（個別 input 精査が必要なケース）。CI は `--no-registry-check` フラグで暫定運用。詳細は [work/pipeline-io-consistency-check-v3.md](work/pipeline-io-consistency-check-v3.md) 参照。

### Changed — Stage 2: 全 11 ワークフロー io-contract の汚染清掃

監査対象外だった AAG / AAGD / AKM / AQOD / ADOC ワークフローの io-contract 31 件の schema errors（producer 空文字、`<details>` 等の汚染）を解消。`docs/services/SVC-*.md`、`docs/screen/{screenId}-*.md`、`docs/agent/agent-detail-{agentId}-*.md` 等の wildcard 入力に適切な producer を付与し、`infra/`、`.github/workflows/`、`docs/azure/azure-services-*.md` 等の複数 producer 集約パスは `kind: external` 化。`test/agent/`、`test/dataflow/`、`test/e2e/playwright/` 等の自己参照は `required: false` + 自己 producer に降格。

### Changed — Stage 3: io-contract を per-Step ファイル形式に再設計

同一 Agent を複数 Step で再利用する構造的問題を解消するため、`<Agent>.yaml` 形式から `<Agent>--<workflow>--<stepId>.yaml` 形式へ全面移行（Q-A2 確定）。

- 旧 per-Agent YAML 77 ファイルを削除し、per-Step YAML 85 ファイルを生成。
- producer 参照を `<Agent>--<workflow>--<stepId>` 形式に正規化。
- `validate-io-contract.py` を per-Step ファイル名対応に改修（`check_registry_mismatch` で `<Agent>--<workflow>--<stepId>` を構築して agents dict を参照）。`skip_agents` 照合も Agent short name + per-Step basename の両対応に拡張。
- 補助スクリプト `tools/split_io_contracts.py`、`tools/normalize_producers.py` を作成（再実行可能）。

### Changed — Stage 4 (A3): 全 io-contract から `{WORK}*` outputs を除去

work-artifacts-layout Skill による work artifact（`{WORK}plan.md`、`{WORK}subissues.md`、`{WORK}work-status.md` 等）は StepDef.output_paths の管轄外であるため、io-contract から除去（30 エントリを 19 ファイルから削除）。1 件の input 側 `{WORK}plan.md` 自己参照も併せて削除。

### Changed — Stage 4 (A4): prompt ファイル整合性監査

`.github/prompts/*.prompt.md`（77 ファイル中、計約 30 件を更新）の path・プレースホルダ表記を io-contract と整合:

- 日本語プレースホルダ→英語統一（10 ファイル、22 箇所）
- `docs/domain-analytics.md` → `docs/catalog/domain-analytics.md`、`docs/test-strategy.md` → `docs/catalog/test-strategy.md`、`data/sample-data.json` → `src/data/sample-data.json`（20 ファイル）
- `docs/architectural-requirements-app-xx.md` → `docs/architectural-requirements-app-{appId}.md`（Arch-ArchitectureCandidateAnalyzer.prompt.md）

### Fixed — Stage 4 (A5): `consumed_artifacts` 解決テーブル整合性確保

`hve/orchestrator.py` の `_ARTIFACT_KEY_TO_GENERATING_WORKFLOW` で `use_case_catalog` の生成元を `"user_provided"` → `"ard"` に訂正（ARD Step 4.3 で生成されるため）。テスト `hve/tests/test_input_artifact_check.py::test_missing_use_case_catalog_next_workflow_is_ard` を新仕様で更新。21 種の artifact key 全てが解決テーブルに存在し、解決パスが StepDef.output_paths と一致することを確認。

### Changed — Stage 4 (B 系): 個別 Major 残置事項の解消

- ASDW-Web Step 1.2 StepDef に `output_paths=["docs/azure/service-catalog.md"]` を追加（Dev-Microservice-Azure-DataDeploy io-contract と整合）
- ARD Step 3（Arch-ARD-KPIOKRDefinition）の `docs/business-requirement.md` と `docs/company-business-requirement.md` を `required: false` に降格（Step 2 / 1.2 の skip 経路でも落ちないようにする）
- SCHEMA.md の画面パス例 `{画面ID}-{画面名スラッグ}` → `{screenId}-{screenNameSlug}` 英語統一
- SCHEMA.md の `external` kind 定義を「外部システム入力 / 複数 Agent が生成する集約ディレクトリ・ワイルドカード等で単一 producer が特定できないもの。producer 検査をスキップ」に拡張

### Changed — Stage 1.C1: CI に `--no-registry-check` フラグを暫定付与

`.github/workflows/validate-io-contract.yml` に `--no-registry-check` フラグを暫定付与。registry_mismatch_errors 394 件の個別解消完了までは CI を fail させない運用。schema_errors と integrity_errors は引き続き厳格チェック。

### Fixed — Agent prompt の Skills 依存セクションで `.github/skills/azure-skills/...` 参照を訂正

リポジトリ内に存在しない `.github/skills/azure-skills/...` を「Agent 固有の Skills 依存」セクションに列挙していた 4 prompt ファイルを修正。`.github/skills/` 配下に実体がないため、Skill ローダや読み手から実在参照と区別できない捏造参照になっていた。

- ユーザー環境 `~/.agents/skills/` 配下に実在する 29 件は **「外部 Skill（ユーザー環境）」** サブセクションへ分離し、パスを `~/.agents/skills/<name>/...` 形式に書き換え。未配備時は prompt 本文の指示のみで動作する旨を注記。
- ユーザー環境にも存在しない 2 件（`azure-cli-deploy-scripts`, `azure-ac-verification`）は `Dev-Microservice-Azure-AddServiceDeploy.prompt.md` から削除。当該 Agent の Skills 依存は無しとなったため、セクションにその旨を明記。
- `Arch-AgenticRetrieval-Detail.prompt.md` の `.github/skills/azure-skills/azure-ai/SKILL.md` 参照（参考のみ扱い）は先行修正で削除済み。本エントリで併せて記録。
- 対象:
  - `.github/prompts/Arch-AgenticRetrieval-Detail.prompt.md`
  - `.github/prompts/Dev-Microservice-Azure-AgenticRetrievalDeploy.prompt.md`
  - `.github/prompts/Dev-Microservice-Azure-AgenticRetrievalDesign.prompt.md`
  - `.github/prompts/Dev-Microservice-Azure-AddServiceDeploy.prompt.md`

### Added — `template/atdd-template.md` 新規作成（Arch-TDD-TestSpec 必須静的入力）

`Arch-TDD-TestSpec` Agent の必須静的入力（`kind: static`）として宣言されていながら実体未配置だった ATDD テンプレートを新規作成。`Arch-TDD-TestSpec.prompt.md` `<output_contract>` の §1.5 ATDD(API) / §1.5 ATDD(UI) / §1.5 ATDD(AI Agent) 3 領域の表形式（AC-ID × Given / When / Then）と記述ルール（AC-ID 命名・双方向トレーサビリティ・出典明示・TBD 表記）を定義。これにより各 test-spec が「テンプレ未存在」を Q-A として継続記録していた状態を解消。

### Changed — ATDD テンプレート参照パスを `docs/templates/` → `template/` に変更

`docs/` 配下のファイルは Agent により再生成・削除される可能性があるため、静的同梱テンプレートの配置場所を `template/` に統一。以下の参照を更新:

- `.github/io-contracts/Arch-TDD-TestSpec.yaml`: 必須入力パス（`kind: static`）
- `.github/io-contract-exceptions.yaml`: `static_paths` 例外登録
- `.github/prompts/Arch-TDD-TestSpec.prompt.md`: 入力一覧 / 停止条件 / 必須適用指示の 3 箇所

既存 `docs/test-specs/SVC-*-test-spec.md` 内の旧パス文字列は、次回 Agent 再生成時に置換される想定のため本変更では更新しない（最小差分原則）。

### Fixed — `parse_screen_catalog` を per-APP カタログ直読みに修正（aad-web Step 2.1 スキップ問題）

`aad-web` Step 2.1 (`Arch-UI-Detail`) が `parse_screen_catalog` の戻り値 0 件で fan-out スキップされ、`docs/screen/*.md` が一切生成されず、後続 `asdw-web` の前提成果物チェックで「`docs/screen/*.md` (required by aad-web)`」エラーを引き起こしていた問題を修正。

- 旧実装は `docs/catalog/screen-catalog.md` 集約ファイルから `SC-*` 形式の ID を抽出していたが、実体は `docs/catalog/screen-catalog-APP-*.md`（per-APP ファイル）内の `S###` 形式（APP スコープ内で安定採番）に再設計されていたため、抽出結果が常に空だった。
- `hve/catalog_parsers.py` の `parse_screen_catalog` を per-APP カタログ（`screen-catalog-APP-*.md` glob）を走査し、ファイル名から抽出した `APP-NN` と本文の `S###` を合成した複合キー `APP-NN-S###` を返却するよう変更。
- `hve/prompt/fanout/aad-web/_common.md` の例示を `SC-*` → `APP-NN-S###` に更新。
- 単体テスト `hve/tests/test_catalog_parsers_screen.py` を新規追加（合成キー抽出 / 空ディレクトリ / APP 内重複排除）。

### Changed — セットアップスクリプト (`hve/setup-hve.*`) をゼロから再作成

OS のみが入った Windows / macOS / Linux からワンショットで HVE CLI / GUI の全機能を実行できる環境を構築するため、3 スクリプトを書き直した。

- **既定で導入する extras を全機能セットに統合**: `mdq-watch,mdq-ja,semantic,gui,gui-pty,gui-docconvert`
  - 旧版で抜けていた `[semantic]` (fastembed / nltk / numpy) と `[gui-pty]` (pywinpty / ptyprocess) を既定インストール対象に追加。GUI 設定画面の「[semantic] extra が未インストール」警告を解消。
  - 旧版で `-WithGui` 指定時のみ導入していた `[gui]` / `[gui-docconvert]` も既定 ON 化。
- **追加処理**: `pip install -e .` (editable)、`pip / setuptools / wheel` アップグレード、`nltk punkt_tab` 事前 DL、Mermaid/KaTeX アセット DL、GUI 翻訳 `.ts → .qm` コンパイル、17 項目の verify を全プラットフォームで統一。
- **OS prereq 案内**: `git` / `gh` / Python 3.11+ が無い場合に Windows (`winget`) / macOS (`brew`) / Ubuntu/Debian (`apt-get`) / Fedora/RHEL (`dnf`) のコマンドを表示。Linux では Qt/QtWebEngine 必須 system lib (`libxcb-cursor0` 等) を診断。
- **フラグを 3 プラットフォーム統一**（旧仕様から BREAKING CHANGE）:
  - 新フラグ: `-CheckOnly` / `--check-only`, `-NoGui` / `--no-gui`, `-Minimal` / `--minimal`, `-Force` / `--force`, `-SkipNltkDownload` / `--skip-nltk-download`, `-WithSkills` / `--with-skills`
  - 旧 `--with-gui` / `-WithGui` は廃止（GUI extras 既定 ON のため不要）。CLI 専用にしたい場合は `--no-gui` / `-NoGui`。base のみの最小構成は新フラグ `--minimal` / `-Minimal`。
  - 旧 `-WithWorkIQ` / `--with-workiq` / `-InstallExternalCopilotCli` / `--install-external-copilot-cli` / `-ForceRecreateVenv` / `--force-recreate-venv` / `-SkipMdq` / `--skip-mdq` / `-SkipMdqWatch` / `--skip-mdq-watch` は廃止。Work IQ / 外部 Copilot CLI は OS 標準のパッケージマネージャから個別導入する方針に変更。
- **`hve\setup-hve.cmd` は `.ps1` を呼ぶ薄ラッパに統一**。cmd の cp932 と Japanese テキストの相性問題を回避し、`.cmd` と `.ps1` の挙動差を解消。`.cmd` は全 PS フラグを verbatim 転送する。

### Added — bump-my-version 導入（バージョンアップ自動化）

- `pyproject.toml` に `[tool.bumpversion]` 設定を追加し、`pyproject.toml` / `hve/__init__.py` / `CHANGELOG.md` の 3 箇所を 1 コマンドで同時更新できるようにした。
- commit メッセージ `chore(release): bump version to <new>` と Git タグ `v<new>` を自動生成。
- 手順書: [hve-dev/hve-app-tools.md](hve-dev/hve-app-tools.md) 「1. バージョンアップ」セクションを参照。
- `mdq` および vendored コピーは独立ライフサイクルのため対象外。

### Fixed — GUI セッション毎の作業ディレクトリ分離 (Issue-gui-session-workdir-isolation)

GUI から ARD 等の Workflow を実行中に、過去タスク（例: `Issue-gui-unified-workbench/`）の `subissues.md` が誤って探索結果として採用され、テーブル形式パース失敗で Step が止まる問題を修正。

**根本原因**: `discover_subissues_md_verbose` (`hve/split_fork.py`) は `run_id`/`step_id` でのスコープフィルタを実装していたが、`runner.py` 側からの呼び出しで `None` のまま渡されており、`work/Issue-*/subissues.md` が glob で全件採用されていた。GUI 側も全セッションで `<repo>/work/` を共有していた。

**修正内容（二段防御）**:

- **L1 物理分離**: GUI MainWindow 1 インスタンス毎に `work/gui-runs/<session_run_id>/` を生成し、子プロセスへ `HVE_WORK_ROOT` / `HVE_GUI_SESSION_ID` env を注入。session_run_id は `gui-{hve.config.generate_run_id()}` 形式（独自実装ゼロ）。
- **L2 論理スコープ**: `runner.py` の `_maybe_run_split_fork` で `discover_subissues_md_verbose` に `run_id=self.config.run_id`, `step_id=step_id` を渡してスコープ外候補をフィルタ。
- **後処理ポリシー**: 設定パネル "GUI セッション作業ディレクトリ" で keep / archive (zip) / purge を選択可能（既定 keep）。`closeEvent` で適用。
- **起動バナー**: GUI 起動時に session_run_id と HVE_WORK_ROOT を 1 度だけログ出力。
- **後方互換**: CLI 単独実行（`HVE_WORK_ROOT` 未設定）の挙動は不変。

**新規ファイル**:

- `hve/gui/session_workdir.py` — `GuiSessionWorkdir` dataclass。
- `hve/gui/tests/test_session_workdir.py` — 10 ケースのユニットテスト。

**主な変更ファイル**: `hve/runner.py`, `hve/gui/state_bridge.py`, `hve/gui/autopilot/child_launcher.py`, `hve/gui/main_window.py`, `hve/gui/page_workbench.py`, `hve/gui/workbench_window.py`, `hve/gui/settings_window.py`, `hve/gui/settings_store.py`, `hve/gui/settings_apply.py`, `hve/tests/test_split_fork.py` (回帰テスト追加)。

---

### Fixed — GUI Autopilot: pre_phases と app_chains 直列連結実行 (DAG バグ修正)

GUI Workbench で **ARD + AAS + AAD-WEB + ASDW-WEB** など pre_phases（ARD/AAS）と downstream（aad-web/asdw-web 等）を同時選択し、かつ `docs/catalog/app-arch-catalog.md` が既に存在する状況で、Step 2 実行時に **ARD/AAS をスキップして AAD-WEB から実行開始** されていた問題を修正。

**根本原因**: `main_window._start_autopilot()` の分岐ロジックが、`pre_phases` 非空かつ `app_chains` も非空のケース（= `pre_phase_only` でも `has_main_workflows` でもないケース）を処理しておらず、`AutopilotController` に直接遷移して `plan.pre_phases` を消費しないまま実行を開始していた。旧仕様は catalog 不在時の `pre_phase_only` モードでのみ pre_phases を実行する設計であり、catalog 既存時の pre_phases 実行は想定外だった可能性がある（過去の意図は未確定）。

**修正内容**:

- **新規プラン判定**: `AutopilotPlan.needs_chain_continuation()` を追加し、`pre_phases` と `app_chains` が同時非空の状態を排他的に検出。
- **新規実行経路**: `main_window._continue_autopilot_with_app_chains()` を追加。`pre_phases` を `_launch_autopilot_main_workflow_queue` 経由で **ARD → AAS の順に直列実行** し、完了後 `_start_autopilot_app_chains_controller()` ヘルパで catalog を再読 → `AutopilotController` で app_chains（APP 単位並列、in-lane 直列）を起動。
- **失敗時挙動**: pre_phases の途中失敗（ARD/AAS）で app_chains は起動されない（既存 `_launch_autopilot_main_workflow_queue` の挙動と同等）。
- **継続 Dialog なし**: ユーザーが明示的に同時選択している前提のため、`pre_phase_only` 経路の Yes/No Dialog はスキップして自動継続。
- **共通ヘルパ抽出**: `_prompt_autopilot_downstream_continuation` 後半の `build_plan` 再実行〜`AutopilotController` 起動処理を `_start_autopilot_app_chains_controller()` にリファクタし、新旧両経路から共用。
- **Step 1 プランレビュー強化 (E=2)**: `AutopilotPlanReview.execution_order` を追加し、`Step1PlanReviewDialog` に「実行順序: ARD → AAS → AAD-WEB → ASDW-WEB」形式のラベルを表示。Step 1 時点で「選択 ≠ 実行順」の乖離を検出可能にした。

**テスト追加**:

- `hve/gui/tests/test_autopilot_planner.py`: `needs_chain_continuation()` 4 ケース、`execution_order()` 4 ケース計 8 件追加。
- `hve/gui/tests/test_plan_review_dialog.py`: `execution_order` ラベル表示 2 ケース追加。

### Changed — GUI 統一 Workbench レイアウト統合 (Issue-gui-unified-workbench, Wave 1〜6)

旧 `AutopilotQueuePage` と `ChainLogWindow` を撤去し、左ツリー / 右ログタブ構成の単一 `WorkbenchPage` に統一。Autopilot ON / OFF・単一 / 並列実行のいずれも同一レイアウトで操作・観測できるようにした。

**主な変更**:

- **撤去**: `hve/gui/page_autopilot_queue.py` (`AutopilotQueuePage`) / `hve/gui/chain_log_window.py` (`ChainLogWindow`) および関連テスト・参照を削除。
- **統一レイアウト**: `WorkbenchPage` が APP / Workflow / Step ツリー（左）と Step 単位のログタブ（右）を提供。中間ノード選択時は配下 Step のマージログを表示。
- **Autopilot ログ統一**: Autopilot 実行ログを `WorkbenchPage.append_log` へ統一配信。マルチ workflow 並列実行時は per-instance にログを分離。
- **メソッドリネーム**: `_activate_autopilot_queue_page` → `_activate_autopilot_workbench`、`_setup_autopilot_chain_log_windows` → `_setup_autopilot_log_routing`。
- **Plan dataclass フィールドリネーム**: `hve/autopilot/plan_model.py` の `run_adfd` / `run_adfdv` → `run_abd` / `run_abdv`（GUI 内部 plan 表現を統一）。
- **テスト追加**: `hve/gui/tests/test_workbench_multi_workflow.py` を新規追加（並列実行 6 ケース）。
- **手動スモーク手順**: `work/Issue-gui-unified-workbench/smoke-checklist.md` に OFF 単一 / ON シングル / ON 並列 (N=2) の 3 シナリオを記録。

### Changed (Breaking) — Batch → Dataflow 名称統一 (Issue-batch-to-dataflow-rename)

「バッチ」名称を全面的に「Dataflow」へ統一。**後方互換なし・即時削除方針** で実施（Q4 採用）。

- **ワークフロー ID**: `abd` → `adfd`, `abdv` → `adfdv`
- **タグ**: `[ABD]` → `[ADFD]`, `[ABDV]` → `[ADFDV]`
- **ディレクトリ削除**: `docs/batch/` 削除（生成先は `docs/dataflow/` へ）
- **Skill**: `.github/skills/batch-design-guide/` → `dataflow-design-guide/`（+ 配下 `batch-*.md` → `dataflow-*.md` 8 ファイル）
- **Custom Agents**: `Arch-Batch-*` (9) → `Arch-Dataflow-*`、`Dev-Batch-*` (5) → `Dev-Dataflow-*`（`JobCatalog`→`AppCatalog`、`JobSpec`→`AppSpec`）
- **Workflows**: `auto-batch-{design,dev}{,-reusable}.yml` → `auto-dataflow-*`、`batch-{design,dev}.yml` → `dataflow-*`、関数名 `check_abd_done`→`check_adfd_done`、`check_abdv_done`→`check_adfdv_done`、orchestrator 識別子 `abd-orchestrator`/`abdv-orchestrator` → `adfd-orchestrator`/`adfdv-orchestrator`
- **Issue Templates / Labels**: `batch-{design,dev}.yml` → `dataflow-*`、旧 `abd:*` / `abdv:*` / `auto-batch-*` ラベル即時削除、新 `adfd:*` / `adfdv:*` / `auto-dataflow-*` 追加
- **CLI**: `--batch-job-id` 引数削除（`--app-id` へ統合）
- **コード**: `batch_job_id` → `app_id`、`BATCH_JOB_IDS` → `APP_IDS`、`_BATCH_JOB_ID_PATTERN` → `_APP_ID_PATTERN_DATAFLOW`、`batch_job_specs` → `dataflow_specs`
- **Prompt fanout**: `hve/prompt/fanout/{abd,abdv}/` → `{adfd,adfdv}/`、`.github/scripts/templates/{abd,abdv}/` → `{adfd,adfdv}/`、`.github/scripts/abd-common.sh` → `adfd-common.sh`
- **Users-guide**: `04-app-design-batch.md` → `04-app-design-dataflow.md`、`06-app-dev-batch-azure.md` → `06-app-dev-dataflow-azure.md`、画像 6 ファイル (`{chain,infographic,orchestration-task-data-flow}-{abd,abdv}.svg` → `-{adfd,adfdv}.svg`)

**マイグレーション**: 既存 Issue / PR / ブランチ / ローカル `.settings.txt` の旧キーは利用不可。新 ID（`adfd` / `adfdv`）で再作成すること。

### Added — GUI 起動ウィザードへ Work IQ ページ追加 (Sub-002 / Phase 1)

`hve.gui.LaunchWizard` (QWizard) に独立した **Work IQ 設定ページ** を追加。従来 `page_options.py` の C4 カテゴリ内に閉じていた Work IQ UI を、新規モジュール `hve/gui/page_workiq.py` の `WorkIQPage` / `WorkIQWizardPage` として公開し、起動ウィザードから直接アクセス可能にした。

**新規 / 変更**:

- `hve/gui/page_workiq.py` (NEW): `WorkIQPage`（既存 `_C4WorkIQ` の公開エイリアス）と `WorkIQWizardPage`（`QWizardPage` ラッパ）を提供。`to_workiq_argv()` で `--workiq*` 系 CLI 引数のみを抽出可能。
- `hve/gui/wizard.py`: `WizardResult` に `workiq_argv: List[str]` フィールドを追加。`to_orchestrate_argv()` / `to_summary_text()` を更新し Work IQ 引数を CLI 引数列にスプライス。`LaunchWizard.__init__` に `WorkIQWizardPage` を `_OptionsPage` の後、`_ConfirmPage` の前に追加（読み込み失敗時は従来 3 ページ構成にフォールバック）。
- `users-guide/hve-gui-orchestrator-guide.md`: C4 行を更新し、Phase 1 ウィザード統合を明記。

**設計上の互換性**:

- `page_options.py` の `_C4WorkIQ` 実装には一切変更なし（最小差分）。`WorkIQPage` は `_C4WorkIQ` のエイリアスとして委譲。
- `OrchestrateArgs` の Work IQ 12 フィールドおよび `to_argv()` の `--workiq*` 生成ロジックは既存のまま。
- 旧コード（`_C4WorkIQ` を直接参照するコード）はそのまま動作。

**i18n の扱い**:

- 既存パターン (`self.tr(...)`) に従い文字列を埋め込み。`hve/gui/i18n/*.json` は存在せず、リポジトリは Qt Linguist `.ts/.qm` 形式のため `.ts` 反映は別タスクで `pyside6-lupdate` 実行予定。

### Added — リアルタイム統計 + AI Credit 料金表示 (Wave 1〜6)

GUI / CUI 両方で実行中のオーケストレーション統計 (Context Size / 経過時間 / AI Credit 料金) を ~1Hz で可視化する機能を追加。**捏造禁止**: 料金表未取得 / 不明モデル時はコストを `-` 表示し、推定値で埋めない。

**新規モジュール**:

- `hve/pricing/` (Wave 1): `models.py` (`CopilotPricing` / `ModelPricing` / `PlanPricing`), `crawler.py` (`fetch_copilot_pricing` — GitHub Docs + github.com/pricing), `cache.py` (`load_cached_pricing` / `save_cached_pricing` / `should_refresh` / `default_cache_path`), `calculator.py` (`calc_cost` — multiplier or additional_request_usd 欠落時は `cost_usd=None`, `method="unavailable"`, `notes["reason"]` 明記)
- `hve/gui/text_kinsoku.py` (Wave 4): `wrap_nowrap_unit` / `join_items` (ZWSP + `&nbsp;|&nbsp;` セパレータ) / `apply_cjk_kinsoku` (行頭禁則簡易) / `format_elapsed` / `format_cost` (`auto` / `usd` / `jpy` / `both`, None → `-`)。Qt 非依存。
- `hve/gui/settings_pricing_tab.py` (Wave 4): GUI 設定タブ。USD/JPY レート / 通貨モード / 月初自動取得 / ステータスライン有効化 / 「🔄 料金表を今すぐ更新」ボタン / 最終取得日時表示。
- `hve/statusline.py` (Wave 5): `StatusLineState` dataclass + `format_status_line()` 純粋関数 + `StatusLine` クラス (daemon thread, 1Hz, `\r\x1b[2K` 上書き, `isatty()` / `HVE_NO_STATUSLINE` / `enabled=False` で自動抑止)。

**設定**:

- `hve/config.py` (Wave 2) に `pricing_usd_jpy_rate` (既定 `150.0`) / `pricing_currency` (`auto`) / `pricing_auto_refresh` (`True`) / `pricing_cache_path` / `pricing_statusline_enabled` (`True`) を追加。環境変数 `HVE_PRICING_*` で上書き可。
- CLI: `hve pricing show` / `hve pricing refresh` サブコマンド (Wave 2)。

**ランタイム連携 (Wave 3)**:

- `WorkbenchState` に `cost_usd_total` / `cost_jpy_total` / `premium_requests_total` / `cost_method_last` / `cost_unavailable_reason` / `pricing_snapshot` / `pricing_usd_jpy_rate` / `pricing_plan_id` を追加。
- `set_pricing(pricing, *, usd_jpy_rate, plan_id)` / `apply_premium_requests(count, *, model)` メソッド追加。
- `hve/runner.py` の `session.shutdown` で `stats_event("premium_requests", count, model)` を emit。`workbench_logger.py` で `kind="premium_requests"` を `apply_premium_requests` に dispatch。

**GUI 拡張 (Wave 4)**:

- `FooterWidget` (`hve/gui/workbench_widgets.py`): 1Hz `QTimer` 化、Cost / Reqs / Workflow elapsed / Step elapsed 表示追加、ZWSP セパレータと行頭禁則適用。後方互換 (`_LABEL_COLOR` / `_VALUE_COLOR` / `_TOPN` / `_fmt_item` / `_fmt_counts` / "Tools (Step)" / "Skills (Step)" は維持)。
- `StatsDetailPopup` (`hve/gui/stats_detail_popup.py`): `build_snapshot()` に **Cost (AI Credit)** セクション (累積コスト / Premium Requests 累積 / 計算方式 / USD/JPY レート / 料金表 取得日時 / 料金表 ステータス / 未計算理由) と **Elapsed** セクション (Workflow 経過 / Step 経過) を追加。スナップショットタブを 1Hz で再構築する `QTimer` を追加。

**ドキュメント**:

- `users-guide/pricing-guide.md` (新規): 料金表データソース / CLI / 環境変数 / GUI 設定タブ / Footer・Popup 仕様 / StatusLine 仕様 / トラブルシュート / 関連ファイル一覧。

**テスト**:

- `hve/tests/pricing/` に計 67 件追加:
  - `test_pricing_models.py` / `test_pricing_calculator.py` / `test_pricing_cache.py` / `test_pricing_crawler.py` (Wave 1: 23)
  - `test_pricing_config.py` / `test_pricing_cli.py` (Wave 2: +4)
  - `test_workbench_state_pricing.py` (Wave 3: +7)
  - `test_text_kinsoku.py` / `test_footer_cost.py` / `test_stats_popup_cost.py` / `test_settings_pricing_tab.py` (Wave 4: +22)
  - `test_statusline.py` (Wave 5: +11)
- 既存 `hve/gui/tests/test_footer_stats.py` 14 件 PASS (回帰なし)。

**既知の制約 / 将来作業**:

- `hve/orchestrator.py` / `hve/console.py` への `StatusLine` 実呼び出し統合は未実施 (モジュール本体とテストまで完了)。次回の orchestrator 改修時に統合予定。
- StatsDetailPopup の Cost 行 `--force-rebuild` 個別チェックは未配線 (UI 状態のみ)。
- Qt linguist (`.ts` / `.qm`) ベースの動的 i18n インフラ未整備 (UI 文言は日本語ハードコード + `self.tr()` でラップ済み)。

### Removed — Phase 2 死コード削除（W7-12 / W7-15 反映）

`work/Arch-ARD-BusinessAnalysis-Targeted/Issue-orchestration-refactor/sub-003/` Sub-003 で実施した死コード削除:

- `hve/gui/page_options.py`: `_ToolBoxCompat` 後方互換シムクラス（旧 QToolBox API 用）と `OptionsPage._toolbox` インスタンス属性を物理削除。新 UI は QGroupBox 垂直スタックに完全移行済みで、シムは不要となっていた。
- `hve/tests/test_gui_pages.py`: `page._toolbox.isItemEnabled(...)` を `page._category_groups[key].isHidden()` 直接参照に書き換え。`_page_indices` 経由のインデックス変換も不要化。
- `.github/copilot-instructions.md`: `HVE_ORCHESTRATOR_ACTIVE` 環境変数言及を §0 から削除（環境変数自体は既に撤廃済みで、参照禁止注記も歴史的ノイズとなっていた）。

なお W7-12（`QA_APPLY_PROMPT` 削除）と W7-15（`hve/gui/login_dialog.py` 削除）の本体除去は既に先行 Phase で完了済みで、Sub-003 では残存していた `_ToolBoxCompat` / `HVE_ORCHESTRATOR_ACTIVE` 言及の整理が主スコープ。

### Changed — Autopilot 事前検証: プランレビュー導入と依存解決の刷新

Autopilot Step 1 [次へ] 押下時の事前検証を、従来の「不足アラートのみ」から「**プランレビュー**」へ刷新した。チェック済み全ステップの入出力 / パラメータを一覧化し、不足入力に対しては「追加すべきステップ」を提案する。

**新仕様**:
- 既存 precheck 通過後、`AutopilotPlanReviewDialog` を **常時表示**（不足ゼロでも表示）。4 タブで以下を提示:
  1. 入力一覧: 全 `required_input_paths` を Status(`existing_reusable` / `missing_produced` / `missing_gap` / `unknown`) 付きで列挙
  2. 出力一覧: 全 `output_paths` を mtime/size 付きで列挙。既存ファイルは「流用可」表示 + 行単位「再生成する」チェック（**注**: 現状 UI 状態のみ。orchestrator への `--force-rebuild` 伝播は未配線。将来対応予定）
  3. パラメータ: Wizard Step 2 必須入力 + Workflow Settings を全件 + 入力状態で列挙
  4. ギャップ提案: 不足入力に対し追加候補 Workflow / Step + depends_on 推移閉包を表示。**個別チェック → [選択した提案を適用]** で `page_workflow_select` に反映後、再検証ループ（最大 3 回）

**新規ファイル**:
- `hve/autopilot/plan_review_model.py`: `AutopilotPlanReview` / `PlannedInput` / `PlannedOutput` / `ParameterEntry` / `GapSuggestion` / `FileStatus` / `ParameterCategory`
- `hve/autopilot/plan_review_collector.py`: 入出力収集（Qt 非依存）
- `hve/autopilot/plan_review_gap.py`: ギャップ計算 + producer 提案（旧 `_AUTOPILOT_IMPLICIT_REQUIRED_PATHS` / `_ARD_STEP_TO_GROUP` / `_WORKFLOW_CANONICAL_ORDER` を移植）
- `hve/autopilot/plan_review_params.py`: パラメータ収集
- `hve/autopilot/plan_review_runner.py`: 統合ランナー `build_autopilot_plan_review()`
- `hve/gui/autopilot/plan_review_dialog.py`: 4 タブ Dialog

**廃止**:
- `hve/autopilot/dependency_resolver.py` を物理削除（`ResolutionResult` / `resolve_missing_dependencies` / `get_first_workflow_in_canonical_order` 等は新アルゴ `plan_review_gap` に統合）
- `hve/gui/autopilot/dependency_resolver.py`（後方互換シム）を物理削除
- `hve/gui/page_workflow_select.py` から `auto_enable_workflow` / `show_dependency_resolution_info` / `clear_dependency_resolution_info` / `_dependency_info_label` を削除。代わりに `apply_plan_review_gaps(suggestions)` を新設
- `hve/gui/main_window.py` の `_on_next_clicked` 内 dependency_resolver 経路（自動 ON）と `_autopilot_resolved_set` 状態を削除
- `hve/gui/tests/test_autopilot_dependency_resolver.py` を削除（カバレッジは `test_plan_review_gap.py` で代替）

**新規テスト**:
- `hve/tests/autopilot/test_plan_review_collector.py`
- `hve/tests/autopilot/test_plan_review_gap.py`（暗黙依存定数 / ARD グループ変換 / producer 解決の網羅）
- `hve/tests/autopilot/test_plan_review_runner.py`
- `hve/gui/tests/test_plan_review_dialog.py`

**互換性**:
- `AutopilotPrecheckDialog` / `run_autopilot_precheck` / `_run_autopilot_full_precheck` メソッド名は維持（内部実装のみ刷新）。
- Step 1 での「依存ワークフロー自動 ON」UX は廃止。代わりにユーザー確認後の手動適用へ変更（誤った範囲拡大の防止）。

### Added — markdown-query Skill 0.5.0: Auto Strategy Routing + Heading Recursive Overlap + Parent Chunk Chain

`mdq` パッケージおよび `markdown-query` Skill を 0.5.0 へ更新。クエリ I/F を `--strategy auto` に統一し、`heading_recursive` 戦略にパラグラフ overlap、`parent_chunk_id` 列による祖先チェーン取得を導入した。

**Schema 変更**:
- `mdq/store.py`: `SCHEMA_VERSION` を 3 → **4** へ。`chunks` テーブルに `parent_chunk_id TEXT` カラムと `idx_chunks_parent` インデックスを追加。v3 DB からは ALTER TABLE で自動マイグレーション（既存行は NULL → `_resolve_parent` が `heading_path` rsplit へフォールバック）。

**新規モジュール**:
- `mdq/query_router.py`: `--strategy auto` 時の純ルールベース戦略選択（7 ルール優先順位 + 在庫不在フォールバック `heading_recursive → heading → fixed_window`）。LLM 呼出なし、ローカル完結。

**CLI / Skill 強化**:
- `python -m mdq search` の `--strategy` が既定 **auto**（クエリから自動選択）。`index` は従来通り具体戦略を要求。
- `--overlap-paragraphs N`: `heading_recursive` 戦略専用。サブチャンク間で前から N 段落を引き継ぎ、文脈断絶を緩和（既定 1、コードフェンスは overlap 対象外）。
- `--with-parent-depth N`: ヒットの祖先見出しを最大 N 階層取得。`expansion.parent` は常に直近親 1 件の dict（後方互換）、N≥2 のときのみ `expansion.parents` に祖先列を追加。

**統計 / GUI**:
- `mdq.usage_stats` を `schema_version` 1 → **2** に拡張、`H1_auto_strategy_distribution`（auto 採用分布・フォールバック率）と `H2_parent_expansion_rate`（parent 展開率）を追加。
- HVE / 独立 GUI 設定画面に「Overlap (Paragraphs)」SpinBox を追加（`tools/skills/markdown_query/gui/`、`hve/gui/` 共通 SoT）。

**ドキュメント**:
- `.github/skills/markdown-query/SKILL.md` を 0.5.0 へ bump、`references/query-routing.md` を新設、`language-and-strategy.md` / `cli-reference.md` を更新。
- `users-guide/skills-markdown-query.md`、`tools/skills/markdown_query/USAGE.md`/`README.md` に新機能を反映。
- `tools/skills/markdown_query/vendor/` を同期、`SYNC.md` にモジュール表を追記。

**テスト**:
- `mdq/tests/` を新設（リポジトリ非依存、`python -m pytest mdq/tests` で完結）。24 件 PASS、既存 `hve/tests/test_mdq*.py` 99 件も全 PASS（回帰なし）。

### Changed — HVE オーケストレーション・リファクタリング Phase 5 / 6: Skills 依存填埋 + harness フェーズ明記

#### Phase 5: Agent Skills 依存セクション集約填埋（8 件）

Phase 0 W7-8 の網羅 grep で「`qa/` 参照を明示している Agent = 2 件のみ」が確定し、Phase 3 W3-5 の CI チェックで「`## Agent 固有の Skills 依存` 見出しが空の Agent」が判明（実測値で 32+ 件）。優先度の高い QA-* / 主要 Arch-* を集約的に填埋：

- `QA-CodeQualityScan.agent.md`: harness-verification-loop / harness-error-recovery / harness-safety-guard / work-artifacts-layout / karpathy-guidelines
- `QA-PostImproveVerify.agent.md`: harness-verification-loop / harness-error-recovery / harness-safety-guard / work-artifacts-layout
- `QA-DocConsistency.agent.md`: markdown-query / knowledge-lookup / harness-verification-loop / work-artifacts-layout
- `QA-AzureArchitectureReview.agent.md`: harness-verification-loop / work-artifacts-layout / karpathy-guidelines
- `QA-AzureDependencyReview.agent.md`: harness-verification-loop / harness-safety-guard / app-scope-resolution / work-artifacts-layout
- `Arch-Microservice-DomainAnalytics.agent.md`: microservice-design-guide / knowledge-lookup / markdown-query / task-dag-planning / work-artifacts-layout
- `Arch-Microservice-ServiceIdentify.agent.md`: microservice-design-guide / knowledge-lookup / task-dag-planning / work-artifacts-layout
- `Arch-ApplicationAnalytics.agent.md`: task-questionnaire / knowledge-lookup / markdown-query / task-dag-planning / work-artifacts-layout

残 27 件は次サイクル PR で集約填埋する（CI 警告で可視化済み）。なお、今サイクルで 8 件の填埋を試みたが、`validate-agents.py` の電点では 5 件の削減（32 → 27）と計測された（3 件はパターンの関係で依然 empty 判定）。

#### Phase 6 W6-1: harness-* Skill のフェーズ明記

Skill description に **PHASE: 実行前 / 実行後 / エラー発生時** を明記し、相互の使い分けを明確化：

- `harness-safety-guard` v2.0.0 → v2.1.0: `PHASE: 実行前（コマンド・スクリプト実行前に使用）` + DO NOT USE FOR で他 2 Skill へ誘導
- `harness-verification-loop` v2.0.0 → v2.1.0: `PHASE: 実行後（コード変更・生成・デプロイを行った**後**に使用）` + DO NOT USE FOR 強化
- `harness-error-recovery` v2.0.0 → v2.1.0: `PHASE: エラー発生時（実行中または検証中にエラーを検知したとき）` + DO NOT USE FOR 強化

#### Phase 6 W6-2: Skill Deprecation スキーマ追加

`.github/skills/_routing/SKILL.md` に **「Skill Deprecation スキーマ」セクション** を新規追加。frontmatter に `metadata.deprecation` を `status` / `since` / `replacement` / `removal_planned` / `reason` で記述する規約を明文化。「現在の廃止予定 Skill」表は空（該当なし）。

### Skipped / Deferred — Phase 4 / 4.5 / 4.6 / 5 残作業 / 6 深掘り

Phase 4 W4-1 / W4-2（ARD Agent Prompt 外部化）は **実体サイズが推定の 61%** であり、Agent File = LLM システムプロンプト本体であることを踏まえ「外部化しない」決定を確定。決定根拠と影響範囲を `work/Issue-orchestration-refactor/phase-4/decision-rationale.md` に記録。代わりに ARD Agent ファイル §4) 冒頭に「外部化しない理由」コメントを追加し、将来の調査時のブレを防止。

Phase 4 W4-3（prompts.py 9 区分テンプレ化）、4.5（全 Prompt BP 適用）、4.6（Copilot CLI BP 適用）、Phase 5 残 27 件 Agent 填埋、Phase 6 W6-4/W6-5（Agent 禁止事項一括追加・見出し統一）は次サイクル PR で実施。

### Fixed — HVE オーケストレーション・リファクタリング Phase 1: WorkIQ GUI 完全実装 + ドキュメント整合性

**重要な発見と訂正**: Phase 0 調査で「WorkIQ は CLI 限定」と結論していたが、再点検の結果 **GUI 側に `_C4WorkIQ` Qt ウィジェットが既に大部分実装済み**（`hve/gui/page_options.py` `_C4WorkIQ` クラス）。さらに Sub-002 サイクルで残 2 フィールドも GUI 追加され、**CLI の 12 オプションすべてが GUI / CLI 両対応** となった：

- ✅ GUI / CLI 両対応（12 個・完全）: `workiq`, `workiq_akm_review`, `workiq_akm_ingest`, `workiq_dxx`, `workiq_draft`, `workiq_draft_output_dir`, `workiq_tenant_id`, `workiq_prompt_qa`, `workiq_prompt_km`, `workiq_prompt_review`, `workiq_per_question_timeout`, `workiq_request_timeout`

`OrchestrateArgs.to_argv()` は 12 引数すべてを変換し、`_C4WorkIQ.to_args()` が 12 引数すべてを `OrchestrateArgs` へ反映する。GUI 起動時に 12 オプションすべて CLI へパススルー可能。

ドキュメント側の表記が古く「CLI 固有」と誤記されていたため、整合性修正も併せて実施：

- **`hve/gui/orchestrate_args.py`** の C4 セクションコメント「`C4: Work IQ — CLI 固有`」を「`C4: Work IQ — GUI / CLI 両対応`」に修正。
- **`hve/gui/page_options.py`** `_C4WorkIQ` クラス docstring を「CLI 固有オプション 11 個」→「GUI / CLI 両対応オプション 12 個（全フィールド列挙）」に更新（Sub-002 で実施）。
- **`users-guide/hve-gui-orchestrator-guide.md`** L246 の「C4 Work IQ ⚠ CLI 固有 ...」を「C4 Work IQ（GUI / CLI 両対応） ... `@microsoft/workiq` プラグインのインストールが必要」に訂正。

GUI smoke テストで動作確認済み: `_C4WorkIQ` → `OrchestrateArgs` → `to_argv()` が `--workiq --workiq-akm-review --workiq-dxx D01,D04 --workiq-draft --workiq-draft-output-dir ... --workiq-tenant-id contoso.onmicrosoft.com --workiq-prompt-qa ... --workiq-prompt-km ... --workiq-prompt-review ... --workiq-per-question-timeout 600.0 --workiq-request-timeout 120.0` の完全 12 フィールドパススルーを実機確認（QT_QPA_PLATFORM=offscreen）。

### Removed — HVE オーケストレーション・リファクタリング Phase 2: 死コード削除

- **`QA_APPLY_PROMPT` を `hve/prompts.py` から完全削除**。Phase 2（post-QA）は commit `8beb0a4d` (2026-05-11) で廃止済みだが、`prompts.py` 定義 / `__init__.py` export / 関連テスト 4 件が残存していた。`runner.py` / `orchestrator.py` / `__main__.py` からの参照は 0 件で、完全な死コードであることを確認のうえ削除。
  - 削除: `hve/prompts.py` `QA_APPLY_PROMPT` 定義
  - 削除: `hve/__init__.py` import / `__all__` から `QA_APPLY_PROMPT`
  - 削除: `hve/tests/test_prompts.py` の 3 テスト（`test_qa_apply_prompt_is_str`, `_not_empty`, `_has_placeholder`）
  - 削除: `hve/tests/test_aqod_qa_prompt.py` の `test_qa_apply_prompt_preserves_aqod_body_format`
- **`hve/gui/login_dialog.py` を削除**（DEPRECATED 明記済み・実体コードからの参照 0 件）。認証は `PluginAuthDialog` + `GitHubProvider` + `MainWindow._on_login_clicked` の分離実装で代替済み。
  - 削除: `hve/gui/login_dialog.py`
  - 削除: `hve/tests/test_gui_dynamic_models.py` の `TestLoginDialogImport` クラス

### Added — HVE オーケストレーション・リファクタリング Phase 3: QA/レビュー可視化

- **`hve/prompts.py` の `REVIEW_PROMPT` に「主タスク成果物への反映証跡」セクションを追加**。レビュー指摘を成果物に反映した場合、PR body / `completion-report.md` にどの指摘がどのファイルにどう反映されたかを表で記録する義務を明示。「レビュー結果が PR コメントだけで終わり、成果物にどう反映されたか不可視」という長年の問題を解決。
- **`.github/agents/_template.md` を新規追加**。全 Agent 共通の構造テンプレート。「### qa/ 参照」「## QA 回答の反映状況」セクションを必須化し、Phase 0 Pre-QA の回答が主タスクで採用/不採用されたかをトレース可能にする。`_` 接頭辞で実 Agent ディスパッチ対象外。
- **`.github/scripts/validate-agents.py` に空 Skills 依存セクション検出ルールを追加**。`## Agent 固有の Skills 依存` 見出しは存在するが本文が空の Agent を CI で警告検出（現状 32 件検出）。`--strict` モードでエラー化可能。`_template.md` は検証対象から除外。

### Fixed — HVE オーケストレーション・リファクタリング Phase 6: ドキュメント整合性

- **README.md の Issue Template 件数を 12 → 11 に訂正**。`.github/ISSUE_TEMPLATE/self-improve.yml` は存在しないが、README 表に誤って記載されていた。Self-Improve は他テンプレートの `enable_self_improve` オプション経由で起動する旨を補足追記。

### Notes — HVE オーケストレーション・リファクタリング Phase 0 / 7

- Phase 0（追加調査 W7-1〜W7-15）の調査レポートを `work/Issue-orchestration-refactor/research/phase-0-consolidated.md` に保存。トークン量実測、qa/ 参照網羅 grep、Phase 2 廃止経緯 git log、`section_text` 実測、`subissues.md` 影響範囲 80+ 箇所など。
- Phase 7（`subissues.md` リネーム）は実施しない判断書を `work/Issue-orchestration-refactor/research/W7-6-decision.md` に確定。`copilot-instructions.md` §0.5 で「歴史的経緯による残置」を既に明記済みのため可視性は確保。

### Deferred — Phase 1 / 4 / 4.5 / 4.6 / 5 / 6 残作業

以下は本リファクタリング・サイクルでは未着手（次サイクル以降）：

- **Phase 1**（GUI WorkIQ ページ追加）: UI 設計・i18n・MCP 認証フロー設計が必要なため別 PR で実施。
- **Phase 4 W4-1 / W4-2**（Arch-ARD-BusinessAnalysis-Untargeted / Targeted の埋め込み Prompt を users-guide へ外部化）: 650 行 + 350 行の大規模移動のため別 PR で実施。
- **Phase 4 W4-3**（prompts.py を 9 区分共通テンプレに再設計）: deprecated 並走を伴う段階移行のため別 PR で実施。
- **Phase 4 W4-4**（copilot-instructions.md と Skills の重複削減）: 敵対的レビュー #7 の方針反転（コアルールは本ファイルに残し、Skills 側で参照化）に従い Phase 6 と統合実施。
- **Phase 4.5 / 4.6**（全 Prompt BP 適用 / GitHub Copilot CLI BP 適用）: Prompt 工学観点の per-prompt 書き換えのため別 PR で実施。
- **Phase 5**（Autopilot を CLI に展開、Skills 依存空セクション 32 件の填埋）: モジュール分離 + CLI 引数追加 + 32 ファイル更新のため別 PR で実施。
- **Phase 6 深掘り**（harness Skill フェーズ明記、低参照頻度 Skill 統合判断、Agent 禁止事項一括追加）: 別 PR で実施。

### Added — `markdown-query` Skill: 独立 GUI ランチャー + ベンダリング

- `tools/skills/markdown-query/` → **`tools/skills/markdown_query/`** にディレクトリリネーム（Python パッケージ化のため。Skill 名 / CLI 名 `markdown-query` は維持）。
- 独立 GUI 起動経路を新規追加。フォルダごと他リポジトリへコピーすれば、HVE 本体非依存で同じ設定画面が起動できる。
  - `setup.ps1` / `setup.sh`: venv 作成 + 依存導入 + 任意で初期索引ビルド（`-BuildIndex` / `--build-index`）。`--repo-root` で任意ディレクトリを指定可能。
  - `launch.py` + `launch-gui.cmd` / `launch-gui.ps1` / `launch-gui.sh`: 任意パスへのコピーに追従する GUI ランチャー（`sys.path` 自動注入）。
  - `pyproject.toml`: 独立配布用パッケージ定義。コンソールスクリプト entry も `gui.__main__:main` に補正済み。
  - `vendor/mdq/`: `mdq/` 本体をベンダリング。同期手順は [vendor/SYNC.md](tools/skills/markdown_query/vendor/SYNC.md)。`vendor/mdq/usage_stats.py` は HVE 不在時でも動作するよう import ガード済み。
- GUI 画面の **単一 SoT** 化:
  - 実体を [`tools/skills/markdown_query/gui/settings_section.py`](tools/skills/markdown_query/gui/settings_section.py) の `MdqIndexSection` クラスへ移設（旧 `hve/gui/settings_window.py` 内 `_MdqIndexSection` 約 470 行を削除）。
  - HVE GUI 側は import 経由で参照するエイリアスだけを残す。両 GUI が常に同じ実装を使う。
  - 設定 INI の SoT 切替: HVE ソースツリー内では `hve/.settings.txt` を共有、他リポジトリへコピーした場合は `<repo>/.mdq-gui-settings.txt` に独立保存。
  - 利用統計レポート出力先も **Skill ディレクトリ相対に変更**（`<skill>/usage-report/`）し、コピー先でおよび HVE ツリー内両方で一貫して動作。
- スクリーンショット自動生成スクリプト `tools/capture_screenshots.py`（PySide6 offscreen レンダリング、CJK フォント自動検出）。出力先 `docs/images/screenshot-{basic,index,stats}.png`。
- ドキュメント追加: [SETUP.md](tools/skills/markdown_query/SETUP.md) / [USAGE.md](tools/skills/markdown_query/USAGE.md)。`README.md` / `users-guide/skills-markdown-query.md` も独立 GUI への導線を追記。

### Changed — GUI ARD オプション: KPI/OKR 定義チェックボックスを削除し Step 1 のグループ選択に統合

- GUI 設定画面（C14 ARD セクション）の **「KPI/OKR 定義を実行する（任意・Step 2.5）」** チェックボックスを削除。
- 同等機能は Step 1 ワークフロー選択画面の **「KPI/OKR 定義（任意）」グループ**（グループ ID = `3`）チェックで提供。GUI 経路の意思表示が 1 箇所に統一される。
- CLI `--include-kpi-okr` フラグおよび対話ウィザードの Yes/No プロンプトは保持（独立経路）。
- 関連変更:
  - [hve/gui/page_options.py](hve/gui/page_options.py): `_C14ARD.include_kpi_okr` QCheckBox 削除、`_STEP2_FIELDS_BY_WORKFLOW["ard"]` から `("c14", "KPI/OKR 定義（任意）")` エントリ削除。
  - [hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py): `OrchestrateArgs.include_kpi_okr` フィールドおよび `to_argv` の `--include-kpi-okr` 付与処理を削除。
  - [hve/tests/test_gui_step2_refactor.py](hve/tests/test_gui_step2_refactor.py): KPI/OKR チェックボックス可視性アサーションを削除。

### Breaking Changes — ARD Step ID リネーム

- ARD ワークフローの Step ID を以下にリネーム:
  - 旧 Step `2.5` → 新 Step `3`（KPI/OKR 定義・任意）
  - 旧 Step `3.1` → 新 Step `4.1`（ユースケース骨格抽出）
  - 旧 Step `3.2` → 新 Step `4.2`（ユースケース詳細生成・fan-out）
  - 旧 Step `3.3` → 新 Step `4.3`（ユースケースカタログ統合・join）
  - グループ ID も対応してリネーム（旧 group `3` → 新 group `4`、新 group `3` = Step `3` 単独）。
- **後方互換は提供しない**。CLI `--steps` で旧 ID（`2.5`, `3.1`, `3.2`, `3.3`）を指定すると `SystemExit` となる。
- 移行ガイド:
  - `--steps 3` を継続使用したい場合は `--steps 4` に書き換え。
  - `--steps 3.1` 等の実 Step 指定は `--steps 4.1` 等に書き換え。
  - `--include-kpi-okr` は引き続き有効（Step `3` を含めるショートカットとして等価）。`--steps 2,3,4` でも同等。
  - `session-state/runs/` の既存 journal に旧 ID が含まれる場合、resume は失敗する（再実行扱い）。
- 関連変更:
  - [hve/workflow_registry.py](hve/workflow_registry.py): `StepDef.id` / `depends_on` / `skip_fallback_deps` / `body_template_path` を新採番に更新。
  - [hve/orchestrator.py](hve/orchestrator.py): `_ARD_GROUP_MAP` のキーと展開先 ID を新採番に更新（`"4": ["4.1","4.2","4.3"]`）、Step 3 直接選択時の include_kpi_okr 自動同期ロジックを維持。
  - [hve/__main__.py](hve/__main__.py): `_valid_step_ids` を新採番に更新、ARD ウィザードを 4 グループ構成（既定選択 = `[2, 4]`）に変更。
  - [hve/gui/page_workflow_select.py](hve/gui/page_workflow_select.py): `_ARD_GROUPS` を 4 グループ構成に更新。
  - [hve/skill_manifest.json](hve/skill_manifest.json): ARD step → skill マップを新採番に更新。
  - テンプレート: `templates/ard/step-2.5.md` → `step-3.md`、`step-3.1.md` → `step-4.1.md`、`step-3.2.md` → `step-4.2.md`、`step-3.3.md` → `step-4.3.md`（git mv）。
  - Agent description: [.github/agents/Arch-ARD-KPIOKRDefinition.agent.md](.github/agents/Arch-ARD-KPIOKRDefinition.agent.md), [Arch-ARD-UseCaseCatalog.agent.md](.github/agents/Arch-ARD-UseCaseCatalog.agent.md), [Arch-ApplicationAnalytics.agent.md](.github/agents/Arch-ApplicationAnalytics.agent.md) の Step ID 参照を更新。
  - ユーザーガイド: [users-guide/01-business-requirement.md](users-guide/01-business-requirement.md) の Step.2.5 / Step.3.x 参照を新採番に更新。連番衝突解消のため qa/ フォルダー手順 Step.4 → Step.5 へずらした。
  - 関連テスト: `test_workflow_registry_ard.py` / `test_workflow_registry.py` / `test_main_ard.py` / `test_orchestrator_ard.py` を新採番に更新。

### Added — GUI Orchestrator: 致命的エラー（fatal）検知時の自動停止

- **GUI 実行中に orchestrator が致命的エラー（`KeyboardInterrupt` / `SystemExit` / `FileNotFoundError` 等、[hve/error_severity.py](hve/error_severity.py) で `fatal` 判定された例外）を検知した際、GUI が後続ワークフローのキュー実行を自動停止する機能を追加**。
- 連携プロトコル: orchestrator が stdout に 1 行の構造化マーカー `[hve:fatal] {"kind":"fatal_abort","exception_type":"...","message":"..."}` を raw `print()` で出力し、GUI が [hve/gui/page_workbench.py](hve/gui/page_workbench.py) `_detect_fatal_marker` で行頭一致検知する。
- GUI の振る舞い:
    - `QTimer.singleShot(0, _terminate_subprocess_for_fatal)` で subprocess を `terminate()` 送信 → 5 秒後に `kill()` の fallback も予約。post-DAG 処理（PR 作成 / Code Review / summary 等）の長時間待機を回避。
    - 後続ワークフローキューを切り詰めて自動停止。
    - `WorkbenchState.aborted=True` を立て、[hve/gui/header_bar.py](hve/gui/header_bar.py) の `HeaderBar.mark_aborted(True)` で ヘッダー ③ を赤い ✗ 表示に切替。
    - 専用ポップアップ（`setText` で要約、長文は `setDetailedText` に分離）を表示。
    - 「戻る」ボタンを fatal 時のみ例外的に有効化し、Step 2 へ戻って設定を見直せるようにする。
- 偽陽性対策: マーカー検知は `line.startswith("[hve:fatal]")` の行頭一致に限定し、ログ転写・モデル応答に含まれる同一文字列によるインジェクションを防ぐ。
- CLI 通常モードへのノイズ抑制: GUI モード（`cfg.no_workbench=True`）または `HVE_EMIT_FATAL_MARKER=1` 環境変数指定時のみマーカーを stdout 出力する。
- `stop_on_fatal` トグル: [hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py) に `OrchestrateArgs.stop_on_fatal: bool = True` を追加（GUI 内部利用）。環境変数 `HVE_GUI_STOP_ON_FATAL=0/false/no/off` で OFF、`1/true/yes/on` で ON を強制可能。
- Resume 連携: [hve/run_state.py](hve/run_state.py) `RunState` に `fatal: bool` / `fatal_reason: Optional[str]` を正式 dataclass フィールド化（後方互換: 既存 state.json は欠落時 `False` / `None` で復元）。[hve/resume_cli.py](hve/resume_cli.py) の `list` / `show` / `_state_summary_dict` (JSON) で fatal 情報を表示。
- 関連変更:
    - [hve/orchestrator.py](hve/orchestrator.py) — `_continue_on_error=True` の fatal 分岐に構造化マーカー出力を追加（`ensure_ascii=True` で cp932 環境での JSON 破損を防止）。`# type: ignore[attr-defined]` を整理。
    - [hve/gui/workbench_state.py](hve/gui/workbench_state.py) — `aborted` フィールドと `mark_aborted()` メソッドを追加（`mark_all_done` と区別し `root.status="failed"` を設定）。
    - [hve/gui/main_window.py](hve/gui/main_window.py) — `_on_process_finished` で fatal 分岐を追加し `_show_fatal_popup` (`setDetailedText` 対応) を表示。`HeaderBar.mark_aborted` 呼出と「戻る」ボタン有効化。
- 新規テスト:
    - [hve/gui/tests/test_page_workbench_fatal.py](hve/gui/tests/test_page_workbench_fatal.py) — マーカー検知（行頭一致 / JSON fallback / 冪等性 / Mapping 返却）、subprocess terminate（OSError 例外吸収含む）、キュー打ち切り、status ラベル、state リセット、stop_on_fatal トグル。
    - [hve/gui/tests/test_header_bar_aborted.py](hve/gui/tests/test_header_bar_aborted.py) — `mark_completed` / `mark_aborted` の状態遷移と排他制御。
    - [hve/gui/tests/test_workbench_state_aborted.py](hve/gui/tests/test_workbench_state_aborted.py) — `mark_aborted` の `all_done` 連動と `root.status="failed"` 設定。
    - [hve/gui/tests/test_fatal_integration.py](hve/gui/tests/test_fatal_integration.py) — 実 Python subprocess を spawn し SubprocessReader 経由で fatal マーカー流入から `proc.terminate()` までの統合フローを 2 ケースで検証。
    - [hve/tests/test_run_state_fatal_field.py](hve/tests/test_run_state_fatal_field.py) — `RunState.fatal` の save/load 往復、既存 state.json からの欠落キー復元、`to_dict` 含有。
- 後方互換性: orchestrator の既存挙動（`continue_on_error=True` / `resume_state.fatal=True` 保存 / `resume_state.fatal_reason` 設定）は維持。CLI Orchestrator の振る舞いも変更なし。
- 既知の制限:
    - GUI Step 2 への「fatal で停止/しない」設定トグル UI は未実装（環境変数 / プログラム引数経由でのみ切替可能）。
    - 翻訳ファイル `.qm` への変換は `pyside6-lrelease` でリリース時にまとめて実施する想定。

### Added — ARD Step 2.5: KPI/OKR Definition（任意・オプトイン）

- ARD ワークフローに **Step 2.5「KPI/OKR 定義」** を新規追加（任意ステップ）。
  - 既定では実行されず、CLI `--include-kpi-okr` / GUI チェックボックス / 対話ウィザードのいずれかで明示有効化した場合のみ実行される。
  - `docs/business-requirement.md`（または `docs/company-business-requirement.md`）の **戦略的記述** を根拠に、SMART KPI、OKR、計測データ定義（定量・定性）、目的志向のデータ収集設計（イベント名・属性スキーマ・計測実装手段）を作成し、`docs/recommended-kpi-okr.md` に出力。
  - ID 命名規約: `ST-*` / `KPI-*` / `OKR-*` / `KR-*-*` / `DAT-*`、各項目に信頼度区分（資料上確認できる事実 / 外部情報補足 / 合理的仮説 / 追加確認必要論点）を必須付与（捏造防止）。
- 新規 Custom Agent: [.github/agents/Arch-ARD-KPIOKRDefinition.agent.md](.github/agents/Arch-ARD-KPIOKRDefinition.agent.md)
- 新規 body template: [.github/scripts/templates/ard/step-2.5.md](.github/scripts/templates/ard/step-2.5.md)
- [hve/workflow_registry.py](hve/workflow_registry.py): `ARD.params` に `include_kpi_okr` 追加、Step 2.5 (`depends_on=["2"]`, `skip_fallback_deps=["1.2"]`) 登録。
- [hve/orchestrator.py](hve/orchestrator.py): ARD グループ展開で `include_kpi_okr=True` かつ Step 2 / Step 3 選択時に Step 2.5 を自動挿入。未選択時は warning 通知。serial bridge mode コメントに Step 2.5 の挙動を明記。
- [hve/__main__.py](hve/__main__.py): CLI `--include-kpi-okr` 追加、wizard 対話モードで `prompt_yes_no` プロンプト追加（Step 2/3 選択時のみ）、quick-auto モードでは自動 False。
- [hve/gui/orchestrate_args.py](hve/gui/orchestrate_args.py) / [hve/gui/page_options.py](hve/gui/page_options.py): `include_kpi_okr` フィールドと GUI チェックボックス追加、Step 2 表示マップに登録。
- 下流連携:
  - [.github/scripts/templates/ard/step-3.1.md](.github/scripts/templates/ard/step-3.1.md) / [step-3.2.md](.github/scripts/templates/ard/step-3.2.md): 入力に `docs/recommended-kpi-okr.md`（任意）追記。
  - [.github/agents/Arch-ARD-UseCaseCatalog.agent.md](.github/agents/Arch-ARD-UseCaseCatalog.agent.md): KPI/OKR 任意参照ルール追記。
  - [.github/agents/Arch-ApplicationAnalytics.agent.md](.github/agents/Arch-ApplicationAnalytics.agent.md): `app-catalog.md` の APP 行に対応 KPI/OKR ID 紐付け（ファイル未生成時は空欄許容、1 APP あたり 5 件超は省略表記可）。
  - [docs/catalog/app-catalog.md](docs/catalog/app-catalog.md): APP 一覧テーブル末尾に **「対応 KPI/OKR」** 列を追加（既存 APP-01〜APP-12 の値は空欄、再生成は別タスク）。
- 関連テスト: `test_workflow_registry_ard.py` / `test_workflow_registry.py` / `test_main_ard.py` / `test_orchestrator_ard.py` / `test_gui_step2_refactor.py` に Step 2.5 検証を追加。
- **注**: ユーザー指定の `recommanded-kpi-okr.md` 綴りは既存 docs/ 配下の英語表記慣例に合わせて `recommended-kpi-okr.md` に正規化。
- **Out-of-scope**（フォローアップ Issue で別途）: KPI モニタリング dashboard 実装、Application Insights / OpenTelemetry の実配線、Dev-* 工程 Agent の KPI 参照組込み、既存 APP-01〜APP-12 行への対応 KPI/OKR 値の充填。

### Changed (Breaking) — markdown-query 利用統計 D3 指標を全 workflow 横断化

- **D3「典型クエリ出現率」指標を `aad-web` 限定から全 workflow（`aad-web` / `asdw-web` / `abd` / `abdv`）横断対応へ拡張しました**。
- 出力 JSON のキー名変更（BREAKING CHANGE）:
    - 旧: `D3_aad_web_typical_query_rate`（フィールド: `value` / `matched_count` / `total_aad_search` / `per_pattern` / `note`）
    - 新: `D3_typical_query_rate`（フィールド: `value`(合算 micro-average) / `matched_count` / `total_search` / `per_workflow.<workflow_id>` / `note`）
- 合算値の算出方法: patterns 定義済み workflow のマッチ件数合計 ÷ patterns 定義済み workflow の search 総件数合計（micro-average）。patterns 未定義の workflow は分母から除外し、サンプル不足を 0% と誤読させない。
- `per_workflow.<workflow_id>` 配下に workflow 別の `value` / `matched_count` / `total_search` / `per_pattern` / `note` を保持。patterns 未定義 workflow も行は存在し、`note: "template/typical-queries.json に <workflow_id> エントリ未定義"` を返す。
- GUI 設定画面 [skills] → [Markdown-Query] のレポート Markdown 表示も workflow 別行 + 合算行に展開。
- 影響範囲:
    - [mdq/usage_stats.py](mdq/usage_stats.py) — `_group_typical_queries` をリファクタ、新ヘルパ `_compute_workflow_typical_query` 追加、定数 `_D3_TARGET_WORKFLOWS` 追加。
    - [tools/skills/markdown_query/generate_usage_report.py](tools/skills/markdown_query/generate_usage_report.py) — Markdown レンダリング更新。
    - [hve/tests/test_mdq_usage_stats.py](hve/tests/test_mdq_usage_stats.py) / [hve/tests/test_generate_usage_report.py](hve/tests/test_generate_usage_report.py) — 新キー名/スキーマに更新。
    - [users-guide/skills-markdown-query.md](users-guide/skills-markdown-query.md) / [tools/skills/markdown_query/usage-report/README.md](tools/skills/markdown_query/usage-report/README.md) — D3 説明と JSON スキーマ例を更新。
- 後方互換: なし。旧キー `D3_aad_web_typical_query_rate` を読む外部スクリプトは新キー/新構造へ移行が必要。既存の日付付きレポート (`tools/skills/markdown_query/usage-report/YYYY-MM-DD.json`) は履歴として残置（自動再生成しない）。
- `template/typical-queries.json` 自体は変更なし。`aad-web` 以外の workflow 用 patterns は同 JSON の `workflows.<workflow_id>` 配下にエントリを追加することで反映される（捏造防止のため本変更では追加していない）。

### Fixed

- **GitHub Copilot 認証が成功しても GUI が `not_authenticated` と誤判定するバグを修正** ([hve/auth.py](hve/auth.py))。
    - 原因: `copilot` SDK の `GetAuthStatusResponse` の属性は camelCase (`isAuthenticated` / `statusMessage`) だが、`_get_auth_status_async` が snake_case (`is_authenticated` / `status_message`) で `getattr` しており、`getattr` の既定値 `False` が常に返っていた。
    - 修正: camelCase を優先参照し、後方互換のため snake_case を fallback で参照するよう変更。
    - 回帰テスト: [hve/tests/test_auth.py](hve/tests/test_auth.py) に camelCase / snake_case fallback / camelCase 優先の検証を追加。[hve/gui/tests/test_auth_providers.py](hve/gui/tests/test_auth_providers.py) に `GitHubProvider.authenticate` を実 SDK 形式 (camelCase) で通す統合テストを追加。

### Changed (Breaking) — Plugin / MCP Server 認証を Copilot CLI 連動へ刷新

- **GUI Orchestrator の Plugin / MCP Server 認証画面が、GitHub Copilot CLI を唯一の信頼ソースとするようになりました**。GUI が独自に MCP レジストリを保持する仕組みは廃止です。
- 新規モジュール:
    - [hve/gui/copilot_cli_bridge.py](hve/gui/copilot_cli_bridge.py) — `CopilotCliBridge` クラス。`copilot mcp list --json` / `copilot mcp get --json` / `copilot plugin list` / `copilot login` を呼び出す薄いラッパ。
- 動作変更:
    - 認証ダイアログに表示されるプロバイダ一覧は **`copilot mcp list --json`** と **`copilot plugin list`** の出力から自動構築されるようになりました。
    - Microsoft Work IQ は `copilot plugin list` に `workiq@work-iq` が表示されているときのみ自動的に認証行として現れます。
    - `_StatusCheckThread` および `GitHubProvider.check_status` の既定タイムアウトを 10 秒 → 30 秒に延長（Copilot SDK の起動が遅い環境でも未認証誤判定が起きにくくなりました）。
- **Breaking — 設定キー削除**:
    - GUI 設定パネルの **「Entra テナント ID」 (`workiq_tenant_id`)** と **「MCP Server 設定 JSON」 (`mcp_config`)** ウィジェットを削除しました。
    - `hve/.settings.txt` に該当キーが残存する場合、GUI 初回起動時に **自動削除** されます (one-shot マイグレーション)。
    - `hve.config` / `hve.__main__` 側の CLI 引数 (`--workiq-tenant-id` / `--mcp-config`) は後方互換のため残置していますが、GUI からは値を渡しません。
- 影響を受けるユーザの移行手順:
    - 既存の `mcp_config` JSON で管理していた MCP サーバは `copilot mcp add <name> -- <command> [args...]` で Copilot CLI 側に登録し直してください。
    - Work IQ は `copilot plugin install` で Copilot CLI のプラグインとして登録してください。
- 関連ガイド:
    - [users-guide/plugin-mcp-auth.md](users-guide/plugin-mcp-auth.md) — 全面改訂
    - [users-guide/hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md#plugin--mcp-server-認証) — 「対象とする認証先」表を更新
- 新規 / 改修テスト (計 +27 ケース):
    - [hve/gui/tests/test_copilot_cli_bridge.py](hve/gui/tests/test_copilot_cli_bridge.py) — 20 (新規)
    - [hve/gui/tests/test_settings_store_migration.py](hve/gui/tests/test_settings_store_migration.py) — 5 (新規)
    - [hve/gui/tests/test_auth_providers.py](hve/gui/tests/test_auth_providers.py) — `discover_providers` / `WorkIQProvider.is_applicable` 系を bridge モックに置き換え

### Added (GitHub ログイン + 利用可能モデル動的取得)

- **アプリ起動時に GitHub Copilot 認証状態を確認し、利用可能なモデル一覧を動的に取得・キャッシュ** する仕組みを追加。
- 新規モジュール:
    - [hve/auth.py](hve/auth.py) — `get_auth_status()` / `is_authenticated()` / `run_login()` / `find_copilot_binary()`。OAuth Device Flow は SDK 同梱 `copilot login` へ委譲。
    - [hve/models_api.py](hve/models_api.py) — `CopilotClient.list_models()` の同期ラッパー（`fetch_models()` / `fetch_model_entries()`）。
    - [hve/models_cache.py](hve/models_cache.py) — JSON 永続キャッシュ。`platformdirs.user_cache_dir("hve") / "models.json"`、TTL 24h、stale フォールバック、アトミック書込。環境変数 `HVE_MODELS_CACHE_PATH` で上書き可。
    - [hve/gui/login_dialog.py](hve/gui/login_dialog.py) — `copilot login` を `QProcess` で起動し Device Flow 出力を表示するモーダル。完了時にバックグラウンドでモデル一覧取得・キャッシュ書込。
- 既存モジュール更新:
    - [hve/config.py](hve/config.py): `FALLBACK_MODEL_CHOICES` 別名追加。新規関数 `get_model_choices(force_refresh=False, include_auto=False, timeout=30.0)` — キャッシュ → SDK → stale → フォールバックの順で解決。
    - [hve/__main__.py](hve/__main__.py): `hve login` サブコマンド追加（`--host`, `--skip-fetch`, `--status`）。CLI ウィザードのモデル選択肢を `get_model_choices(include_auto=True)` に切替。
    - [hve/gui/page_options.py](hve/gui/page_options.py): モデル選択肢をキャッシュ優先で動的ロード（起動時 SDK ブロック回避）。
    - [hve/gui/main_window.py](hve/gui/main_window.py): ステータスバー右側に GitHub 認証インジケータ（`✅ <ユーザー名>` / `❌ 未ログイン`）と「GitHub ログイン」ボタン追加。起動時にバックグラウンドスレッドで認証確認。
- トークン参照優先順 (`COPILOT_GITHUB_TOKEN` > `GH_TOKEN` > `GITHUB_TOKEN`) を Copilot CLI 仕様に合わせて統一。
- 新規依存: `platformdirs>=4.0`（[pyproject.toml](pyproject.toml#L11)）。
- 新規テスト（計 73 + 5 = 78 ケース）:
    - [hve/tests/test_auth.py](hve/tests/test_auth.py) — 21
    - [hve/tests/test_models_api.py](hve/tests/test_models_api.py) — 9
    - [hve/tests/test_models_cache.py](hve/tests/test_models_cache.py) — 20
    - [hve/tests/test_get_model_choices.py](hve/tests/test_get_model_choices.py) — 9
    - [hve/tests/test_cli_login.py](hve/tests/test_cli_login.py) — 14
    - [hve/tests/test_gui_dynamic_models.py](hve/tests/test_gui_dynamic_models.py) — 5（要 PySide6）

### Added (GUI 多言語化 / Globalization — 日本語 / English)

- **HVE GUI Orchestrator を日本語（既定）/ 英語の 2 言語対応に**。Qt `QTranslator` ベース。
- 新規モジュール [hve/gui/i18n/](hve/gui/i18n/README.md):
    - `__init__.py` — `resolve_language()`（env `HVE_GUI_LANG` → 設定 → OS ロケール → フォールバック の優先順位）, `install_translator()`
    - `translations.pro` — `pyside6-lupdate` 用ソース列挙
    - `hve_gui_en_US.ts` — 英訳ソース（420 翻訳ユニット、AI 生成・要人手校閲）
    - `hve_gui_en_US.qm` — 実行時バイナリ
    - `README.md` — 翻訳更新ワークフロー
- `settings_store.py` に `options.language` キー（既定 `"auto"`）を追加。
- 設定ウィンドウに **「一般 → 言語 / Language」** セクション追加（自動 / 日本語 / English）。変更時は再起動案内ダイアログ表示。
- 22 ファイルの GUI 文字列を `self.tr(...)` / `QT_TRANSLATE_NOOP` でラップ（合計 420 翻訳ユニット）:
    - page_options.py / main_window.py / workbench_widgets.py / page_workbench.py / workbench_window.py / page_workflow_select.py / wizard.py / settings_window.py / page_options_ard.py / widgets/app_id_checklist.py / copilot_chat_panel.py / help_popup.py / stats_detail_popup.py / tasktre_widget.py / help_content.py（5 辞書のモジュールレベル文字列）/ header_bar.py / page_intro.py / session_menu.py 他
- 新規開発者向けツール:
    - [tools/wrap_tr.py](tools/wrap_tr.py) — AST ベースで Python ソース内の日本語文字列を `self.tr(...)` でラップ
    - [tools/apply_translations.py](tools/apply_translations.py) — Python 辞書を `.ts` の `<translation>` に投入
- `setup-hve.ps1` / `setup-hve.sh`: `.ts` が `.qm` より新しい場合に `pyside6-lrelease` を自動実行。`--check-only` で `pyside6-lupdate` 存在確認も実施。
- ドキュメント追記:
    - [README.md](README.md): 多言語対応の注記
    - [users-guide/hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md): 言語切替手順節を追加
- テスト: [hve/gui/tests/test_i18n.py](hve/gui/tests/test_i18n.py) — 15 ケース（言語決定優先順位 / Translator ロード / 設定 / アセット存在）。

### Changed (GUI Step 2 オプション画面の簡素化)

- **Step 2 をワークフロー固有の最小フィールドのみ表示** に再設計。共通項目（基本設定 / 並列実行 / 自動プロンプト / 出力制御 / Issue・PR / MCP・CLI 接続 / タイムアウト / ブランチ / 実行制御）は **[設定] ウィンドウへ集約**。
- カテゴリ見出しから `Cxx:` プレフィックスを除去（Step 2 グループタイトル、設定ウィンドウ左ツリー）。
- 設定ウィンドウに **「Work IQ」「ワークフロー固有設定（アプリ ID / リソース / AKM / AQOD / ADOC / ARD）」** セクションを追加。
- ワークフロー別 Step 2 表示項目（仕様確定版）:
    - **`ard`**: 業務エリア（旧「対象業務名」を改名）+ QA 回答ドラフト生成
    - **`aas`**: フィールド非表示 →「オプションは [設定] メニューで行ってください」案内 + `設定を開く` ボタン
    - **`aad-web`**: 対象アプリケーション (APP-ID) を **チェックボックスリスト化**（`docs/catalog/app-arch-catalog.md` §A サマリ表から動的生成 / プロセス内キャッシュ / 全選択トグル）
    - **`asdw-web`** / **`abdv`**: Azure リソースグループ名
    - **`abd`**: バッチジョブ ID
    - **`akm`**: QA 回答ドラフト生成 / QA・KM 用プロンプト上書き / 取り込みソース / 対象ファイル / **既存Knowledgeファイルの再生成**（旧「既存出力を再生成」）/ **追加ファイル**（旧「カスタムソースフォルダ」）
    - **`aqod`**: **チェック対象ファイルのフォルダパス**（旧「チェック対象スコープ」）/ 分析の深さ（選択肢を日本語化: `標準（standard）` / `軽量（lightweight）`）/ **分析の観点（任意）**（旧「重点観点」）
    - **`adoc`**: ドキュメント生成対象ディレクトリ / 除外パターン / ドキュメントの主目的
    - **共通**: `追加プロンプト` を全ワークフローの最下段に常時表示
- 複数ワークフロー選択時、**同一フィールド（内部 ID 一致）は 1 つに統合**して表示。
- **Work IQ セッション限定上書き**: `ard` / `akm` で「QA 回答ドラフト生成」 ON のとき、当該セッションのみ `args.workiq=True` を強制（設定ファイルへは保存しない）。
- 新規モジュール:
    - `hve/gui/app_catalog_loader.py`: `docs/catalog/app-arch-catalog.md` §A サマリ表パーサ + プロセス内キャッシュ
    - `hve/gui/widgets/app_id_checklist.py`: APP-ID チェックボックスリスト Widget
- 新規テスト: `hve/gui/tests/test_app_catalog_loader.py`（5 件）/ `hve/tests/test_gui_step2_refactor.py`（14 件）。
- 検証: `pytest hve/gui/tests/ hve/tests/ -k "gui or page_options or settings or workbench"` → **290 passed, 6 skipped, 0 failed**。

### Changed (GUI Orchestrator 添付ファイル変換エンジン)

- **`gui-docconvert` extras の中身を [microsoft/markitdown](https://github.com/microsoft/markitdown) に一本化**: 旧 `pypdf` / `mammoth` / `markdownify` / `openpyxl` 依存を廃止し、`markitdown[all]>=0.1.5` の単一依存に置き換え。extras 名 `gui-docconvert` は後方互換のため据え置き。
- `hve/gui/doc_convert.py` の per-format コンバータ（`_convert_html` / `_convert_docx` / `_convert_pdf` / `_convert_xlsx`）を削除し、`_convert_with_markitdown()` の単一経路に統合。`MarkItDown.convert_local()` のみを使用（URL / ストリーム経路は不採用、セキュリティ最小化）。
- 対応拡張子を **`.pptx` / `.xls` 追加**（合計 11 種: `.md` / `.markdown` / `.txt` / `.csv` は stdlib、`.html` / `.htm` / `.docx` / `.pdf` / `.xlsx` / `.xls` / `.pptx` は markitdown 経由）。
- セットアップスクリプトに `--with-gui` (`hve/setup-hve.sh`) / `-WithGui` (`hve/setup-hve.ps1`) フラグを追加。指定時に `.[gui,gui-docconvert]`（PySide6 + markitdown[all]）を自動インストール。
- 関連ドキュメントを更新: hve-gui-orchestrator-design.md §7.3 / §13.1（TBD → Resolved）、hve-cli-orchestrator-gui-design.md §7.3 / §13.1（両ファイルはその後 [hve-technical-architecture.md](users-guide/hve-technical-architecture.md) に統合）、[hve-gui-orchestrator-guide.md](users-guide/hve-gui-orchestrator-guide.md) インストール手順・トラブルシュート、[getting-started.md](users-guide/getting-started.md) 任意依存セクション。
- テスト `hve/tests/test_gui_doc_convert.py` を MarkItDown 統合テストに書き換え（`_has_markitdown()` の `skipUnless`/`skipIf` ガード採用、`.html` / `.docx` / `.xlsx` / `.pptx` / `.xls` の本文断片検証）。

### Removed

- **Resume 機能から OneDrive for Business 同期を削除**: `hve resume export` / `hve resume import` / `hve resume list --remote` コマンドを廃止。
- `hve/onedrive_sync.py` モジュールおよび関連テスト（`hve/tests/test_onedrive_sync.py`）を削除。
- `users-guide/hve-resume-onedrive-setup.md`（Phase 7 OneDrive セットアップガイド）を削除。
- セットアップスクリプトの `--with-onedrive` (Bash) / `-WithOneDrive` (PowerShell) オプションを削除。

### Changed

- `detect-qa-questionnaire-pr.yml` を opt-in 化し、`<!-- qa-questionnaire-pr: opt-in -->` が PR 本文先頭にある場合のみ `qa-questionnaire-pr` 付与 + `auto-qa` 除去を実行するよう変更。
- 影響: `auto-qa` Issue 由来 PR で発生していた `qa-questionnaire-pr` ラベルフリップによるデッドロックを解消。
- **Phase 5 (Issue C): `.github/agents/*.agent.md` frontmatter 正規化**（起動時 System/Tools トークン圧縮施策）
  - **BOM 除去**: UTF-8 BOM（`\xef\xbb\xbf`）が含まれていた 28 ファイルから BOM を除去した。YAML frontmatter のパース安定性向上を目的とする。
  - **description 短縮**: 150 字超だった 5 ファイルの `description` を簡潔化した（意味・役割情報は保持）。
    - `Arch-ArchitectureCandidateAnalyzer`: 185 → 102 字
    - `Dev-Microservice-Azure-ComputeDeploy-AzureFunctions`: 190 → 116 字
    - `Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps`: 181 → 113 字
    - `QA-DocConsistency`: 165 → 109 字
    - `QA-PostImproveVerify`: 166 → 115 字
  - **不変事項**: Agent 数（69 件）・`name`・`tools`・`prompt:` 本文はすべて変更なし。frontmatter 追加キーは元々存在せず、整理対象なし。

### Added

- `restore-auto-qa-label.yml` を追加。`qa-questionnaire-pr` が付与され `auto-qa` が無い誤分類 PR を、opt-in 非該当かつ linked Issue が `auto-qa` 起源の場合に復元可能とした。
- **Resume 機能（Phase 1〜6）の文書化**: `work/runs/<run_id>/state.json` へのアトミック保存、`Ctrl+R` による graceful pause、ウィザード起動時の再開選択、`hve resume` CLI（`list/show/rename/delete/continue`）を README / users-guide に明記。
- **Resume / Ctrl+R 拡張 (Phase 8)**: ウィザード中も Ctrl+R を押すと、保存済みセッション一覧メニューが即時表示され、その場から Resume 実行できるようになりました。オーケストレーター実行中の Ctrl+R（保存）の挙動は変更ありません。
- feat(console): `compact` (既定) / `normal` / `verbose` でアシスタント最終発話をマゼンタ `●` 行として表示するようになりました。`quiet` では引き続き非表示です。
- feat(runner): `final_message()` に渡すテキストを Phase 1 メイン応答から「最後に得られた非空 Phase 応答」に変更し、QA / Review / Self-Improve 後の改善内容が最終発話に反映されるようになりました。
- compat: `--final-only` 経路は既存挙動（`📝` 装飾）を維持しています。
- **Agentic Retrieval Phase 8 ドキュメント整備**:
  - AAD-WEB / ASDW-WEB の Agentic Retrieval 選択肢（Q1〜Q6）の
    利用ガイドを users-guide に追加
  - `Arch-AgenticRetrieval-Detail` および
    `Dev-Microservice-Azure-AddServiceDesign/Deploy` の
    ワークフロー参照導線を追記
  - Web UI ガイドに AAD-WEB / ASDW-WEB の
    Agentic Retrieval 質問表示差分を追記
  - workflow-reference に Agentic Retrieval 反映位置と
    `enable_agentic_retrieval` スキップ条件を追記
  - `users-guide/agentic-retrieval-guide.md` を新規追加

- **Issue Template でモデル選択を hve CLI とパリティ化（Phase 9+）**: `model` ドロップダウンを 5 種（`Auto` / `claude-opus-4.7` / `claude-opus-4.6` / `gpt-5.5` / `gpt-5.4`）に拡張。新たに `review_model` / `qa_model` ドロップダウンを追加（`self-improve.yml` を除く 10 テンプレート）。対応する `review-model/*` / `qa-model/*` ラベルを `.github/labels.json` に追加。
- **`extract-review-model.py` / `extract-qa-model.py` 新規作成**: Issue body から `### レビュー用モデル` / `### QA 用モデル` セクションを抽出する Python スクリプトを追加。
- **`assign-copilot.sh` に `extract_review_model` / `extract_qa_model` 関数追加**: 各抽出スクリプトのラッパー関数を追加。reusable workflows 10 件に `REVIEW_MODEL_RAW` / `SELECTED_REVIEW_MODEL` / `QA_MODEL_RAW` / `SELECTED_QA_MODEL` パターンおよびラベル付与を追加。
- **F5: `--final-only` フラグ**: DAG 実行終了時のサマリと各ステップの最終応答のみを出力するモードを追加（CI/スクリプト連携用途）。timestamp/カラー/スピナーは自動的に無効化される。`Console` に `final_only` 引数、`SDKConfig` に `final_only` フィールドを追加。
- **F6: `Console.file_diff()` メソッド**: hve 自身がファイル編集を行うときに diff を表示する新メソッドを追加。Copilot CLI 経由の編集は既存の `cli_log()` パススルーに任せる（二重表示回避）。`runner.py` の `QAMerger.save_merged()` 呼出箇所（pre-QA / post-QA の 2 箇所）で活用。verbosity に応じてサマリのみ/確定行/全行を表示。

### Changed

- **SDK バージョン検出のロバスト化（T7）**: `hve/run_state.py` の `_get_package_version` 利用箇所を `_get_copilot_sdk_version()` に統一し、配布名候補（`copilot-sdk` / `github-copilot-sdk` / `copilot`）を順に試行するよう変更。配布名差異で `is_resumable()` の major version 判定が機能しないケースを回避。
- **テスト確認結果サマリ（Resume）**: Resume 関連 7 テストファイルをローカルで実行し全件 PASS。加えて `_get_copilot_sdk_version()` と `is_resumable()` の呼び出し経路に対する新規テストを追加。
- Work IQ の質問ごとクエリタイムアウト（`workiq_per_question_timeout`）の既定値を **20 分（1200 秒）** に統一しました。
  - 以前は `SDKConfig` 既定値と `from_env()` 既定値が `900` 秒、CLI ヘルプと対話モードのプロンプトが `600` 秒と不揃いでした。
  - 影響: 環境変数 `WORKIQ_PER_QUESTION_TIMEOUT`、CLI 引数 `--workiq-per-question-timeout`、対話モード入力での明示指定があれば、これまで通りそちらが優先されます（後方互換）。

- **サポートモデルの絞り込み**: `claude-sonnet-4.6` / `gpt-5.3-codex` / `gemini-2.5-pro` を廃止。`hve/config.py` の `MODEL_CHOICES` から削除。`MODEL_CHOICES` の順序を `claude-opus-4.7` 先頭に変更。
- **`_normalize_model_with_warning` にフォールバック機能追加**: 許可リスト外のモデル名が来た場合、`warnings.warn` で WARNING を発出して `Auto` を返すよう拡張。既存 Issue/PR に残る廃止モデル指定（`claude-sonnet-4.6` 等）は自動的に `Auto` にフォールバック。
- **Phase 6 方針撤回**: 「Issue Template の model は Auto のみ維持」方針を撤回（社内合意済み）。`docs/design-discussions/orchestration-route-diff-spec.md` §13.4 および `docs/phase9-compatibility-inventory.md` §4 を更新。
- **F1: `--no-color` フラグ / `NO_COLOR` 環境変数対応**: ANSI カラー出力を明示的に無効化できるようになりました。[NO_COLOR デファクト規格](https://no-color.org/) 準拠（`NO_COLOR` 環境変数に空でない値が設定されていれば色を抑止）。`--no-color` フラグまたは `NO_COLOR` 環境変数で制御。既定挙動は変わりません（TTY 自動判定）。
- **F2: `--banner` / `--no-banner` フラグ**: 起動時バナー表示を明示的に制御できるようになりました。`SDKConfig.show_banner` フィールドが追加されました（`None` = 既存の自動判定を維持）。
- **F3: `--screen-reader` フラグ**: スクリーンリーダー対応モードを追加しました。有効時、出力中の絵文字（✅ ❌ ⏭️ 等）を日本語ラベル（[成功] [失敗] [スキップ] 等）に置換し、スピナーを無効化します。**注意**: 絵文字置換のラベル訳語は提案値であり、Copilot CLI 実機での確認は行っていません。
- **F4: `--timestamp-style {prefix,suffix,off}` フラグ**: タイムスタンプの表示位置を選択できるようになりました。既定は `prefix`（行頭表示、従来通り）。`suffix` で行末（DIM スタイル）、`off` で非表示。

### Changed

- **Work IQ プロンプトを Microsoft 365 Copilot ベストプラクティス準拠に改訂**: `hve/workiq.py` の Work IQ 用プロンプト 4 箇所（役割プライミング・QA/KM/Review タスク指示・診断プローブ）から、MCP ツール名 `` `ask_work_iq` `` および引数名 `` `question` `` の本文記述を全削除しました。これらは SDK が system prompt にツール schema を自動注入するため、本文に併記すると「合成語による外部環境説明」アンチパターンとなり Microsoft 365 Copilot のベストプラクティスに反します。あわせて以下を改善:
  - Goal / Context / Source の 3 要素構造を各モード（QA/KM/Review）に明示（[Best practices for effective prompts](https://learn.microsoft.com/copilot/security/prompting-tips)）
  - 「**検索結果に存在しない情報を一切作り出さない**」捏造禁止の明文化
  - 「目的との整合・引用元の有無・取得できなかったソース」を出力直前に**自己レビュー**する手順の明記
  - 公開定数名（`DEFAULT_WORKIQ_QA_PROMPT` 等）・組立構造・`{target_content}` プレースホルダ・環境変数（`WORKIQ_PROMPT_*`）の互換は維持
  - 詳細プランは [work/Issue-TBD-WorkIQPromptPlan/plan.md](work/Issue-TBD-WorkIQPromptPlan/plan.md) を参照

### Breaking Changes (opt-in)

- **自己改善 対象パスの仕様変更**: `HVE_SELF_IMPROVE_NEW_SCOPE_RESOLVER=1` 環境変数で **opt-in** で有効化される新仕様を追加しました。
  - 未入力時の挙動が「リポジトリ全体」から「そのステップの成果物（`work/` 配下は自動除外）」に変更されます。
  - `*` ワイルドカードで `data, docs, docs-generated, knowledge, src` を一括指定可能（実在するもののみ展開、存在しないパスは警告ログを出してスキップ）。
  - カンマ/空白区切りで複数パス指定可能。
  - `-` で始まるトークンは ValueError で拒否（コマンドインジェクション類似の防止）。
  - 旧挙動はフラグ OFF（デフォルト）で完全維持。

## [Major] AKM/AQOD QA フェーズ制御変更 — BREAKING CHANGES

### BREAKING CHANGES

#### AKM ワークフロー（事後 QA の廃止）

- **変更前**: AKM ワークフローの各ステップで事後 QA フェーズ（Phase 2）が強制実行されていました。
- **変更後**: AKM ワークフローの事後 QA フェーズ（Phase 2）を恒久的に廃止しました。
  - 代わりに事前 QA フェーズ（Phase 0）が `qa_phase` 設定に従って動作するようになり、その結果がメインタスクのプロンプト先頭に `pre_qa_context` として注入されます。
  - AKM Work IQ 検証（`_run_akm_workiq_verification`）は DAG 終了後に従来通り実行されます（別系統・変更なし）。
  - `qa/{run_id}-{step_id}-execution-qa-merged.md` は AKM では出力されなくなります。代わりに `qa/{run_id}-{step_id}-pre-execution-qa.md` を参照してください。

**マイグレーション**:
```bash
# 旧: AKM で事後 QA を実行（この挙動は廃止）
python -m hve orchestrate --workflow akm --auto-qa

# 新: AKM で事前 QA を実行してメインタスクへ注入
python -m hve orchestrate --workflow akm --auto-qa --qa-phase pre
```

#### AQOD ワークフロー（事後 QA のオプトイン化）

- **変更前**: AQOD ワークフローの各ステップで事後 QA フェーズ（Phase 2）が強制実行されていました。
- **変更後**: AQOD ワークフローの事後 QA フェーズ（Phase 2）はデフォルトで**無効**になりました。

**マイグレーション（従来挙動を維持するには）**:
```bash
# CLI フラグでオプトイン
python -m hve orchestrate --workflow aqod --auto-qa --aqod-post-qa

# 環境変数でオプトイン
HVE_AQOD_POST_QA=true python -m hve orchestrate --workflow aqod --auto-qa
```

### 新機能

- `SDKConfig.aqod_post_qa_enabled` フィールド追加（デフォルト: `False`）
- CLI フラグ `--aqod-post-qa` 追加（`orchestrate` サブコマンド）
- 環境変数 `HVE_AQOD_POST_QA` 対応（`true`/`1`/`yes` で有効化）
- AKM の事前 QA が `qa_phase` 設定に従って実行されるように変更（事前 QA の結果は Phase 1 プロンプト先頭に注入）

### QA フェーズ動作一覧

| ワークフロー | 事前 QA (Phase 0) | 事後 QA (Phase 2) | 備考 |
|---|---|---|---|
| AAD / その他通常 | `qa_phase ∈ {pre,both}` で実行 | `qa_phase ∈ {post,both}` で実行 | 既存通り（変更なし） |
| **AKM** | **`qa_phase` に従う** | **常時スキップ** | 事前 QA → Phase 1 注入で要件充足。DAG 終了後に `_run_akm_workiq_verification` が別途実行 |
| **AQOD** | 常時スキップ（変更なし） | **`aqod_post_qa_enabled=True` のときのみ実行** | `--aqod-post-qa` または `HVE_AQOD_POST_QA=true` でオプトイン |
