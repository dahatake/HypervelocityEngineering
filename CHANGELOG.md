# CHANGELOG

## [Unreleased]

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
