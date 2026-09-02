"""hve.gui.orchestrate_args — `orchestrate` サブコマンドの全オプションを保持する dataclass。

設計書 §10.1 / §11.2 U7 に対応。

主な責務:
  - GUI のフォーム入力を `OrchestrateArgs` に集約する
  - `to_argv()` で `python -m hve orchestrate ...` の引数リストに変換する
  - `argparse.BooleanOptionalAction` の 3 状態（None / True / False）を正しくフラグに変換する
  - GUI モード固有の制約（`--workbench=off` 強制注入）を適用する

設計上の制約（設計書 §13.4）:
  - GUI モードでは `--workbench=off` を必ず注入する。
  - `--workbench-*` 系オプションは GUI から指定しない（C16 から除外）。

実装根拠:
  - 各オプション定義は `hve/__main__.py` L661-L1297 の `orch.add_argument(...)` を参照。
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Tuple


# `argparse.BooleanOptionalAction` 系オプションの 3 状態を表すリテラル
# - None        : 未指定（GUI 上では「継承」）
# - True        : 明示 ON
# - False       : 明示 OFF
TriState = Optional[bool]


@dataclass
class OrchestrateArgs:
    """`orchestrate` サブコマンドの全引数を保持する dataclass。

    設計書 §10.1 を実コードに展開。全 80+ オプションを網羅。
    """

    # ------------------------------------------------------------------
    # C1: 基本設定 (hve/__main__.py L661-L699)
    # ------------------------------------------------------------------
    workflow: str = ""
    """ワークフロー ID（必須）。"""

    model: Optional[str] = None
    review_model: Optional[str] = None
    qa_model: Optional[str] = None
    # QA 起点 AKM 子実行専用の実行品質（FR-QA-04）。None はメイン設定の継承。
    akm_model: Optional[str] = None

    # reasoning_effort: SDK が返す `supported_reasoning_efforts` から選択された値。
    # None は「未指定（モデル既定 / orchestrator 側のフォールバック値）」を意味する。
    reasoning_effort: Optional[str] = None
    review_reasoning_effort: Optional[str] = None
    qa_reasoning_effort: Optional[str] = None
    akm_reasoning_effort: Optional[str] = None

    # context_tier: SDK の create_session(context_tier=...) へ渡す値。
    # "default" | "long_context"。GUI 既定は long_context（設定画面の既定要件）。
    context_tier: Optional[str] = "long_context"
    akm_context_tier: Optional[str] = None

    # Agentic Retrieval Step（AAD-WEB 2.6 / ASDW-WEB 2.5・2.6）の有効化。
    # "auto" | "yes" | "no"。None は CLI へ渡さない（hve 既定の auto に委ねる）。
    enable_agentic_retrieval: Optional[str] = None

    # 以下 5 つは Step の実行可否ではなく、生成される設計内容に影響する。
    # いずれも None のときは CLI へ渡さず hve 側の既定値に任せる。
    agentic_data_source_modes: Optional[List[str]] = None
    foundry_mcp_integration: Optional[bool] = None
    agentic_data_sources_hint: Optional[str] = None
    agentic_existing_design_diff_only: Optional[bool] = None
    foundry_sku_fallback_policy: Optional[str] = None

    # Foundry Toolbox の tool search。"auto" | "yes" | "no"。None は CLI へ渡さない。
    enable_tool_search: Optional[str] = None

    # ------------------------------------------------------------------
    # C2: 並列実行 (L702-L708)
    # ------------------------------------------------------------------
    max_parallel: int = 15

    # ------------------------------------------------------------------
    # C3: QA (質問票) / Knowledge Management / レビュー (L711-L747)
    # ------------------------------------------------------------------
    auto_qa: bool = False
    # QA 回答を knowledge/ へバックグラウンドでマージするか（FR-QA-05、既定: 無効）。
    qa_akm_background_merge: bool = False
    auto_contents_review: bool = False
    auto_coding_agent_review: bool = False
    auto_coding_agent_review_auto_approval: bool = False
    # QA 回答モード (GUI 追加): "autopilot" | "gui-file" | None
    #  - None         : 未指定（既存挻動 = 非 TTY フォールバック）
    #  - "autopilot"  : 全問既定値採用（GUI Autopilot モード）
    #  - "gui-file"   : IPC ファイル経由で GUI から回答取得
    qa_answer_mode: Optional[str] = None
    qa_ipc_dir: Optional[str] = None  # qa_answer_mode="gui-file" 時の IPC ディレクトリパス
    steering_ipc_dir: Optional[str] = None  # Steering（実行中ワークフローへの割り込み送信）用 IPC ディレクトリパス

    # ------------------------------------------------------------------
    # C4: Work IQ — GUI / CLI 両対応 (L748-L824)
    # ------------------------------------------------------------------
    # 実装状況:
    #   - dataclass: 以下の 12 フィールド を保持
    #   - CLI:  hve/__main__.py `--workiq*` オプション群 で 12 フィールドすべて受付可能
    #   - GUI:  hve/gui/page_options.py `_C4WorkIQ` クラスが 11 フィールドのフォームを提供。
    #           `workiq_tenant_id` は GUI 入力経路を廃止済みで（同クラスに明記、
    #           settings_store._OBSOLETE_KEYS へ登録済み）、GUI からは常に None が入る。
    #   - to_argv() は 12 フィールドすべてを --workiq* 引数に変換可能。
    workiq: bool = False
    workiq_akm_review: TriState = None  # BooleanOptionalAction
    workiq_akm_ingest: TriState = None  # BooleanOptionalAction
    workiq_dxx: Optional[str] = None
    workiq_draft: bool = False
    workiq_draft_output_dir: Optional[str] = None
    workiq_tenant_id: Optional[str] = None
    workiq_prompt_qa: Optional[str] = None
    workiq_prompt_km: Optional[str] = None
    workiq_prompt_review: Optional[str] = None
    workiq_per_question_timeout: Optional[float] = None
    workiq_request_timeout: Optional[float] = None

    # ------------------------------------------------------------------
    # C5: Issue / PR 作成 (L827-L857)
    # ------------------------------------------------------------------
    # FR-LOCAL-SURFACE-01 (a): local 実行モード既定の continue-on-precheck を
    # 無効化し、pre-check 失敗時に中断する。既定は従来通り継続。
    strict: bool = False
    create_issues: bool = False
    create_pr: bool = False
    # FR-CLI-83: True=新規作業branch、False=current branch mode。
    create_working_branch: bool = True
    ignore_paths: List[str] = field(default_factory=list)
    repo: Optional[str] = None
    issue_title: Optional[str] = None
    # FR-GUI-25: 既存 Issue を Root Issue として使う場合の Issue 番号。
    issue_number: Optional[int] = None

    # ------------------------------------------------------------------
    # C6: 出力制御 (L860-L926)
    # ------------------------------------------------------------------
    verbose: bool = False
    quiet: bool = False
    verbosity: Optional[str] = None  # quiet/compact/normal/verbose
    show_stream: bool = False
    log_level: str = "error"  # none/error/warning/info/debug/all
    no_color: bool = False
    banner: TriState = None  # BooleanOptionalAction
    screen_reader: bool = False
    timestamp_style: str = "prefix"  # prefix/suffix/off
    final_only: bool = False

    # ------------------------------------------------------------------
    # C7: MCP / CLI 接続 (L929-L948)
    # ------------------------------------------------------------------
    mcp_config: Optional[str] = None
    cli_path: Optional[str] = None
    cli_url: Optional[str] = None

    # ------------------------------------------------------------------
    # Cloud Sessions (GitHub Copilot SDK 1.0.0+)
    # ------------------------------------------------------------------
    cloud_session_enabled: TriState = None
    cloud_session_owner: Optional[str] = None
    cloud_session_repository_name: Optional[str] = None
    cloud_session_branch: Optional[str] = None
    cloud_session_max_concurrency: Optional[int] = None
    cloud_session_integration_id: Optional[str] = None
    cloud_session_mc_base_url: Optional[str] = None
    cloud_session_step_overrides: Optional[str] = None
    cloud_session_subtask_overrides: Optional[str] = None
    fleet_mode_enabled: TriState = None

    # ------------------------------------------------------------------
    # C8: タイムアウト (L951-L964)
    # ------------------------------------------------------------------
    timeout: float = 21600.0
    review_timeout: float = 7200.0

    # ------------------------------------------------------------------
    # C9: ブランチ / ステップ選択 (L967-L980)
    # ------------------------------------------------------------------
    branch: str = "main"
    # `steps` は GUI 設定画面の入力欄からは削除済みだが、Step 1 のワークフロー別
    # ステップ選択（main_window._resolve_steps_for_workflow → args.steps = ...）の
    # 受け皿として残置。to_argv() で --steps として subprocess へ伝搬する。
    steps: Optional[str] = None

    # FR-GUI-38: FR-CLI-86 の `--resume-run`。空欄は未指定として扱う。
    resume_run: Optional[str] = None

    # FR-PROMPT-08: Prompt 版の実行時入力別名（canonical, actual）。
    # canonical 契約を変えず、その run に限って実ファイルへ読み替える。
    input_aliases: List[Tuple[str, str]] = field(default_factory=list)

    # ------------------------------------------------------------------
    # C10: アプリ ID 系 (L983-L1020)
    # ------------------------------------------------------------------
    app_id: Optional[str] = None
    app_ids: Optional[str] = None
    resource_group: Optional[str] = None
    usecase_id: Optional[str] = None

    # ------------------------------------------------------------------
    # C11: AKM 固有 (L1023-L1056)
    # ------------------------------------------------------------------
    sources: Optional[str] = None
    target_files: List[str] = field(default_factory=list)
    force_refresh: TriState = None  # BooleanOptionalAction
    custom_source_dir: List[str] = field(default_factory=list)
    # enable_auto_merge は元 AKM 用だが、案 P で github.com CI/CD の全自動化
    # マスタースイッチに転用（GUI では C5「GitHub」セクションで設定）。
    # to_argv() で --enable-auto-merge として subprocess へ伝搬する。
    enable_auto_merge: bool = False
    # FR-CLI-34: マージ済みローカル作業ブランチ削除（既定有効）。
    # to_argv() で off 時のみ --no-delete-local-merged-branch を出力する。
    delete_local_merged_branch: bool = True

    # ------------------------------------------------------------------
    # 原本入力 / ADI 固有（既存フラグ互換）
    # ------------------------------------------------------------------
    target_scope: Optional[str] = None
    depth: Optional[str] = None  # standard/lightweight
    focus_areas: Optional[str] = None

    # ------------------------------------------------------------------
    # ADI 固有
    # ------------------------------------------------------------------
    purpose: Optional[str] = None

    # ------------------------------------------------------------------
    # C13: ADOC 固有 (L1076-L1099)
    # ------------------------------------------------------------------
    target_dirs: Optional[str] = None
    exclude_patterns: Optional[str] = None
    doc_purpose: Optional[str] = None  # all/onboarding/refactoring/migration
    max_file_lines: Optional[int] = None

    # ------------------------------------------------------------------
    # C14: ARD 固有 (L1103-L1159)
    # ------------------------------------------------------------------
    company_name: Optional[str] = None
    target_business: Optional[str] = None
    survey_base_date: Optional[str] = None
    survey_period_years: Optional[int] = None
    target_region: Optional[str] = None
    analysis_purpose: Optional[str] = None
    target_recommendation_id: Optional[str] = None
    attached_docs: Optional[str] = None  # カンマ区切り

    # ------------------------------------------------------------------
    # FR-LOCAL-SURFACE-01 (b): registry 宣言済みの Workflow 固有パラメータ。
    # 宣言した Workflow を選んだときだけ適用される（GUI の全体設定
    # へは永続化しない）。
    # ------------------------------------------------------------------
    # ARD: Step 3 (KPI/OKR 定義)。FR-PARAM-10 の後方互換ショートカット。
    include_kpi_okr: bool = False
    # AAD-WEB / ASDW-WEB: Knowledge Base の Remote MCP Server 公開。
    create_remote_mcp_server: TriState = None
    # ASDW-WEB / ADFDV / AAGD: TDD ループの最大再試行回数。
    tdd_max_retries: Optional[int] = None

    # ------------------------------------------------------------------
    # C15: 追加プロンプト (L1169-L1201)
    # ------------------------------------------------------------------
    additional_prompt: Optional[str] = None
    context_max_chars: Optional[int] = None

    # ------------------------------------------------------------------
    # C16: 実行制御 / 拡張機能 (L1204-L1258)
    # ------------------------------------------------------------------
    dry_run: bool = False
    self_improve: bool = False
    no_self_improve: bool = False
    self_improve_max_iterations: Optional[int] = None
    self_improve_target_scope: Optional[str] = None
    self_improve_goal: Optional[str] = None
    mdq_watch: TriState = None  # BooleanOptionalAction (--mdq-watch / --no-mdq-watch)
    mdq_watch_debounce_ms: Optional[int] = None
    cq_watch: TriState = None  # BooleanOptionalAction (--cq-watch / --no-cq-watch)
    cq_watch_debounce_ms: Optional[int] = None
    auto_compaction: TriState = None  # BooleanOptionalAction (--auto-compaction / --no-auto-compaction)
    tool_search: TriState = None  # BooleanOptionalAction (--tool-search / --no-tool-search)
    # tool_search 有効時のランキング実装。"sdk" | "hve"。None は CLI へ渡さない。
    tool_search_ranking: Optional[str] = None

    # ------------------------------------------------------------------
    # GUI 内部利用（CLI には渡らない）
    # ------------------------------------------------------------------
    repo_root: Path = field(default_factory=Path.cwd)
    """リポジトリルート（添付ファイル保存先などで使用）。"""

    stop_on_fatal: bool = True
    """orchestrator が `[hve:fatal]` マーカーを出した際に GUI がキューを自動停止し、
    subprocess を ``terminate()`` するかどうか。既定 True。現状 GUI の Step 2 UI では
    設定しないが、テスト / プログラム使用 / 環境変数 `HVE_GUI_STOP_ON_FATAL=0` により
    OFF にできる。本フラグは CLI 側へは伝達しない。"""

    # ==================================================================
    # 変換ロジック
    # ==================================================================

    def to_argv(self) -> List[str]:
        """`["orchestrate", "--workflow", "ard", ...]` 形式に変換する。

        設計書 §8.3: GUI モードでは `--workbench=off` を必ず注入する。
        """
        if not self.workflow:
            raise ValueError("workflow が空です（Step 1 で選択してください）")

        argv: List[str] = ["orchestrate", "--workflow", self.workflow]

        # --- C1 ---
        if self.model:
            argv += ["--model", self.model]
        if self.review_model:
            argv += ["--review-model", self.review_model]
        if self.qa_model:
            argv += ["--qa-model", self.qa_model]
        if self.akm_model:
            argv += ["--akm-model", self.akm_model]
        if self.reasoning_effort:
            argv += ["--reasoning-effort", self.reasoning_effort]
        if self.review_reasoning_effort:
            argv += ["--review-reasoning-effort", self.review_reasoning_effort]
        if self.qa_reasoning_effort:
            argv += ["--qa-reasoning-effort", self.qa_reasoning_effort]
        if self.akm_reasoning_effort:
            argv += ["--akm-reasoning-effort", self.akm_reasoning_effort]
        if self.context_tier:
            argv += ["--context-tier", self.context_tier]
        if self.akm_context_tier:
            argv += ["--akm-context-tier", self.akm_context_tier]
        if self.enable_agentic_retrieval:
            argv += ["--enable-agentic-retrieval", self.enable_agentic_retrieval]
        if self.agentic_data_source_modes:
            argv += ["--agentic-data-source-modes", *self.agentic_data_source_modes]
        if self.foundry_mcp_integration is not None:
            argv.append(
                "--foundry-mcp-integration"
                if self.foundry_mcp_integration
                else "--no-foundry-mcp-integration"
            )
        if self.agentic_data_sources_hint:
            argv += ["--agentic-data-sources-hint", self.agentic_data_sources_hint]
        if self.agentic_existing_design_diff_only is not None:
            argv.append(
                "--agentic-existing-design-diff-only"
                if self.agentic_existing_design_diff_only
                else "--no-agentic-existing-design-diff-only"
            )
        if self.foundry_sku_fallback_policy:
            argv += ["--foundry-sku-fallback-policy", self.foundry_sku_fallback_policy]
        if self.enable_tool_search:
            argv += ["--enable-tool-search", self.enable_tool_search]

        # --- C2 ---
        if self.max_parallel != 15:
            argv += ["--max-parallel", str(self.max_parallel)]

        # --- C3 ---
        if self.auto_qa:
            argv.append("--auto-qa")
        if self.qa_akm_background_merge:
            argv.append("--qa-akm-background-merge")
        if self.auto_contents_review:
            argv.append("--auto-contents-review")
        if self.auto_coding_agent_review:
            argv.append("--auto-coding-agent-review")
        if self.auto_coding_agent_review_auto_approval:
            argv.append("--auto-coding-agent-review-auto-approval")
        if self.qa_answer_mode:
            argv += ["--qa-answer-mode", self.qa_answer_mode]
        if self.qa_ipc_dir:
            argv += ["--qa-ipc-dir", self.qa_ipc_dir]
        if self.steering_ipc_dir:
            argv += ["--steering-ipc-dir", self.steering_ipc_dir]

        # --- C4: Work IQ ---
        if self.workiq:
            argv.append("--workiq")
        _append_tristate(argv, "--workiq-akm-review", "--no-workiq-akm-review", self.workiq_akm_review)
        _append_tristate(argv, "--workiq-akm-ingest", "--no-workiq-akm-ingest", self.workiq_akm_ingest)
        if self.workiq_dxx:
            argv += ["--workiq-dxx", self.workiq_dxx]
        if self.workiq_draft:
            argv.append("--workiq-draft")
        if self.workiq_draft_output_dir:
            argv += ["--workiq-draft-output-dir", self.workiq_draft_output_dir]
        if self.workiq_tenant_id:
            argv += ["--workiq-tenant-id", self.workiq_tenant_id]
        if self.workiq_prompt_qa:
            argv += ["--workiq-prompt-qa", self.workiq_prompt_qa]
        if self.workiq_prompt_km:
            argv += ["--workiq-prompt-km", self.workiq_prompt_km]
        if self.workiq_prompt_review:
            argv += ["--workiq-prompt-review", self.workiq_prompt_review]
        if self.workiq_per_question_timeout is not None:
            argv += ["--workiq-per-question-timeout", str(self.workiq_per_question_timeout)]
        if self.workiq_request_timeout is not None:
            argv += ["--workiq-request-timeout", str(self.workiq_request_timeout)]

        # --- C5 ---
        if self.strict:
            argv.append("--strict")
        if self.create_issues:
            argv.append("--create-issues")
        if self.create_pr:
            argv.append("--create-pr")
        if not self.create_working_branch:
            argv.append("--no-create-working-branch")
        if self.ignore_paths:
            argv += ["--ignore-paths", *self.ignore_paths]
        if self.repo:
            argv += ["--repo", self.repo]
        if self.issue_title:
            argv += ["--issue-title", self.issue_title]
        if self.issue_number:
            argv += ["--issue-number", str(self.issue_number)]

        # --- C6 ---
        if self.verbose:
            argv.append("--verbose")
        if self.quiet:
            argv.append("--quiet")
        # GUI 既定の verbosity は normal。compact (CLI 既定) のままだと、GUI は
        # 非 TTY パイプでサブプロセスを起動するため、ステップ実行中の進捗
        # (action/intent/thinking 等) が spinner 経路へ振られて GUI ログに
        # 出力されない。明示指定 (verbosity/quiet/verbose) があればそれを優先する。
        effective_verbosity = self.verbosity
        if effective_verbosity is None and not self.quiet and not self.verbose:
            effective_verbosity = "normal"
        if effective_verbosity:
            argv += ["--verbosity", effective_verbosity]
        if self.show_stream:
            argv.append("--show-stream")
        if self.log_level != "error":
            argv += ["--log-level", self.log_level]
        if self.no_color:
            argv.append("--no-color")
        _append_tristate(argv, "--banner", "--no-banner", self.banner)
        if self.screen_reader:
            argv.append("--screen-reader")
        if self.timestamp_style != "prefix":
            argv += ["--timestamp-style", self.timestamp_style]
        if self.final_only:
            argv.append("--final-only")

        # --- C7 ---
        if self.mcp_config:
            argv += ["--mcp-config", self.mcp_config]
        if self.cli_path:
            argv += ["--cli-path", self.cli_path]
        if self.cli_url:
            argv += ["--cli-url", self.cli_url]

        # --- Cloud Sessions ---
        _append_tristate(argv, "--cloud-session", "--no-cloud-session", self.cloud_session_enabled)
        if self.cloud_session_owner:
            argv += ["--cloud-session-owner", self.cloud_session_owner]
        if self.cloud_session_repository_name:
            argv += ["--cloud-session-repository-name", self.cloud_session_repository_name]
        if self.cloud_session_branch:
            argv += ["--cloud-session-branch", self.cloud_session_branch]
        if self.cloud_session_max_concurrency is not None:
            argv += ["--cloud-session-max-concurrency", str(self.cloud_session_max_concurrency)]
        if self.cloud_session_integration_id:
            argv += ["--cloud-session-integration-id", self.cloud_session_integration_id]
        if self.cloud_session_mc_base_url:
            argv += ["--cloud-session-mc-base-url", self.cloud_session_mc_base_url]
        if self.cloud_session_step_overrides:
            argv += ["--cloud-session-step-overrides", self.cloud_session_step_overrides]
        if self.cloud_session_subtask_overrides:
            argv += ["--cloud-session-subtask-overrides", self.cloud_session_subtask_overrides]
        _append_tristate(argv, "--fleet-mode", "--no-fleet-mode", self.fleet_mode_enabled)

        # --- C8 ---
        if self.timeout != 21600.0:
            argv += ["--timeout", str(self.timeout)]
        if self.review_timeout != 7200.0:
            argv += ["--review-timeout", str(self.review_timeout)]

        # --- C9 ---
        if self.branch != "main":
            argv += ["--branch", self.branch]
        if self.steps:
            argv += ["--steps", self.steps]
        for canonical, actual in self.input_aliases:
            argv += ["--input-alias", canonical, actual]
        if self.resume_run and self.resume_run.strip():
            argv += ["--resume-run", self.resume_run.strip()]

        # --- C10 ---
        if self.app_id:
            argv += ["--app-id", self.app_id]
        if self.app_ids:
            argv += ["--app-ids", self.app_ids]
        if self.resource_group:
            argv += ["--resource-group", self.resource_group]
        if self.usecase_id:
            argv += ["--usecase-id", self.usecase_id]

        # --- C11: AKM ---
        if self.sources:
            argv += ["--sources", self.sources]
        if self.target_files:
            argv += ["--target-files", *self.target_files]
        _append_tristate(argv, "--force-refresh", "--no-force-refresh", self.force_refresh)
        if self.custom_source_dir:
            argv += ["--custom-source-dir", *self.custom_source_dir]
        # enable_auto_merge は AKM / 案 P（github.com CI/CD 全自動化）共用。
        if self.enable_auto_merge:
            argv.append("--enable-auto-merge")
        # FR-CLI-34: 既定有効のため off 時のみ --no-... を出力（CLI 既定 True と一致）。
        if not self.delete_local_merged_branch:
            argv.append("--no-delete-local-merged-branch")

        # --- ADI 原本入力 ---
        if self.target_scope:
            argv += ["--target-scope", self.target_scope]
        if self.depth:
            argv += ["--depth", self.depth]
        if self.focus_areas:
            argv += ["--focus-areas", self.focus_areas]

        # --- ADI ---
        if self.purpose:
            argv += ["--purpose", self.purpose]

        # --- C13: ADOC ---
        if self.target_dirs:
            argv += ["--target-dirs", self.target_dirs]
        if self.exclude_patterns:
            argv += ["--exclude-patterns", self.exclude_patterns]
        if self.doc_purpose:
            argv += ["--doc-purpose", self.doc_purpose]
        if self.max_file_lines is not None:
            argv += ["--max-file-lines", str(self.max_file_lines)]

        # --- C14: ARD ---
        if self.company_name:
            argv += ["--company-name", self.company_name]
        if self.target_business:
            argv += ["--target-business", self.target_business]
        if self.survey_base_date:
            argv += ["--survey-base-date", self.survey_base_date]
        if self.survey_period_years is not None:
            argv += ["--survey-period-years", str(self.survey_period_years)]
        if self.target_region:
            argv += ["--target-region", self.target_region]
        if self.analysis_purpose:
            argv += ["--analysis-purpose", self.analysis_purpose]
        if self.target_recommendation_id:
            argv += ["--target-recommendation-id", self.target_recommendation_id]
        if self.attached_docs:
            argv += ["--attached-docs", self.attached_docs]

        # --- Workflow 固有パラメータ（FR-LOCAL-SURFACE-01 (b)）---
        if self.include_kpi_okr:
            argv.append("--include-kpi-okr")
        _append_tristate(
            argv,
            "--create-remote-mcp-server",
            "--no-create-remote-mcp-server",
            self.create_remote_mcp_server,
        )
        if self.tdd_max_retries is not None:
            argv += ["--tdd-max-retries", str(self.tdd_max_retries)]

        # --- C15 ---
        if self.additional_prompt:
            argv += ["--additional-prompt", self.additional_prompt]
        if self.context_max_chars is not None:
            argv += ["--context-max-chars", str(self.context_max_chars)]

        # --- C16 ---
        if self.dry_run:
            argv.append("--dry-run")
        if self.self_improve:
            argv.append("--self-improve")
        if self.no_self_improve:
            argv.append("--no-self-improve")
        if self.self_improve_max_iterations is not None:
            argv += ["--self-improve-max-iterations", str(self.self_improve_max_iterations)]
        if self.self_improve_target_scope:
            argv += ["--self-improve-target-scope", self.self_improve_target_scope]
        if self.self_improve_goal:
            argv += ["--self-improve-goal", self.self_improve_goal]
        _append_tristate(argv, "--mdq-watch", "--no-mdq-watch", self.mdq_watch)
        if self.mdq_watch_debounce_ms is not None:
            argv += ["--mdq-watch-debounce-ms", str(self.mdq_watch_debounce_ms)]
        _append_tristate(argv, "--cq-watch", "--no-cq-watch", self.cq_watch)
        if self.cq_watch_debounce_ms is not None:
            argv += ["--cq-watch-debounce-ms", str(self.cq_watch_debounce_ms)]
        _append_tristate(argv, "--auto-compaction", "--no-auto-compaction", self.auto_compaction)
        _append_tristate(argv, "--tool-search", "--no-tool-search", self.tool_search)
        if self.tool_search_ranking:
            argv += ["--tool-search-ranking", self.tool_search_ranking]

        # --- GUI 強制 (設計書 §8.3) ---
        # GUI モードでは Rich Live のターミナル Workbench を無効化する。
        argv += ["--workbench", "off"]

        return argv

    def to_command_line(self) -> str:
        """`python -m hve orchestrate ...` の人間可読コマンドラインを返す。"""
        return "python -m hve " + " ".join(_shell_quote(a) for a in self.to_argv())

    def to_summary_text(self) -> str:
        """確認・コピー用のサマリーテキストを返す。"""
        lines = [f"# 起動パラメータ (workflow={self.workflow})"]
        for f in fields(self):
            if f.name == "repo_root":
                continue
            if f.name == "stop_on_fatal":
                # GUI 内部フラグは確認 / コピーテキストに出さない
                continue
            value = getattr(self, f.name)
            # 既定値と等しい場合はスキップ
            default = f.default
            if callable(getattr(f, "default_factory", None)) and f.default_factory is not None:  # type: ignore[truthy-function]
                default = f.default_factory()  # type: ignore[call-arg]
            if value == default:
                continue
            lines.append(f"- {f.name}: {value!r}")
        lines.append("")
        lines.append("# 実行コマンド")
        lines.append(self.to_command_line())
        return "\n".join(lines)


# --------------------------------------------------------------------------
# ヘルパー
# --------------------------------------------------------------------------


def _coerce_tristate(value: Any) -> TriState:
    """設定ストアの 3 状態値（``""`` / ``"on"`` / ``"off"``）を bool へ正規化する。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return {"on": True, "off": False}.get(value.strip().lower())
    return None


# --------------------------------------------------------------------------
# 保存済み設定 → OrchestrateArgs（FR-PROMPT-07）
# --------------------------------------------------------------------------

# 設定ストアの汎用マッピングから除外するフィールド。
# Prompt CLI / GUI ランタイム所有値は保存値を使わず、AKM 固有値は下の
# workflow-aware な個別変換で `akm` のときだけ読み取る。
_RUNTIME_OWNED_FIELDS = frozenset(
    {
        "workflow",
        "steps",
        "dry_run",
        "input_aliases",
        "repo_root",
        "stop_on_fatal",
        "qa_ipc_dir",
        "steering_ipc_dir",
        "self_improve",
        "no_self_improve",
        "sources",
        "target_files",
        "force_refresh",
        "custom_source_dir",
    }
)

# `settings_store` のキー名が `OrchestrateArgs` と一致しない、または
# 型・意味の変換が要るもの。汎用マッピングから除外して個別に処理する。
_SPECIAL_SETTINGS_KEYS = frozenset(
    {
        "auto_qa",
        "self_improve",
        "qa_answer_mode",
        "issue_number",
        "sources_qa",
        "sources_original_docs",
        "sources_workiq",
        "tool_search_ranking",
    }
)

# 保存値 "auto" を CLI 未指定（None）へ正規化するフィールド。
# GUI の `to_args()` も "auto" を CLI へ渡さないため、両面の振る舞いを揃える。
_AUTO_MEANS_UNSET = frozenset({"enable_agentic_retrieval", "enable_tool_search"})

# 設定ストアの key 名 → `OrchestrateArgs` のフィールド名。
# 名前が一致しないものだけを列挙する（FR-PROMPT-07 / FR-LOCAL-SURFACE-01 (a)）。
# 列挙しない限り名前不一致の保存値は無言で捨てられるため、
# 新規の不一致を作ったときは必ずここへ追加する。
_SETTINGS_KEY_ALIASES: Mapping[str, str] = {
    "cloud_session_repository_branch": "cloud_session_branch",
}

# 0 を「未指定」として扱うフィールド（GUI の QSpinBox 既定 0 に対応）。
_ZERO_MEANS_UNSET = frozenset(
    {
        "context_max_chars",
        "max_file_lines",
        "workiq_per_question_timeout",
        "mdq_watch_debounce_ms",
        "cq_watch_debounce_ms",
        "survey_period_years",
        "cloud_session_max_concurrency",
    }
)


def _split_semicolon_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    if not isinstance(value, str):
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def _split_whitespace_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    if not isinstance(value, str):
        return []
    return value.split()


def _field_map() -> Mapping[str, Any]:
    return {f.name: f for f in fields(OrchestrateArgs)}


def _is_tristate_field(f: Any) -> bool:
    # `TriState = Optional[bool]`。dataclass のアノテーションは文字列で保持される。
    return str(f.type).replace(" ", "") in {"TriState", "Optional[bool]", "bool|None"}


def _coerce_for_field(f: Any, value: Any) -> Any:
    name = f.name
    if name in _AUTO_MEANS_UNSET and isinstance(value, str):
        text = value.strip()
        return text if text in {"yes", "no"} else None
    # GUI は path list を空白区切り、Agentic data source modes を
    # "indexer;push" のセミコロン区切りで保存する。
    if name == "ignore_paths":
        return _split_whitespace_list(value)
    if name == "agentic_data_source_modes":
        return _split_semicolon_list(value)
    if _is_tristate_field(f):
        return _coerce_tristate(value)

    annotation = str(f.type)
    if isinstance(value, str) and not value.strip() and "Optional" in annotation:
        return None
    if name in _ZERO_MEANS_UNSET and isinstance(value, (int, float)) and not value:
        return None
    if "Optional[int]" in annotation and isinstance(value, str):
        text = value.strip()
        return int(text) if text.isdigit() else None
    if annotation.endswith("bool") and not annotation.startswith("Optional"):
        if isinstance(value, str):
            return value.strip().lower() in {"true", "on", "1", "yes"}
        return bool(value)
    return value


def args_from_settings(
    settings: Mapping[str, Mapping[str, Any]],
    *,
    workflow: str,
    overrides: Optional[Mapping[str, Any]] = None,
    steps: Optional[Sequence[str]] = None,
    goal: Optional[str] = None,
    input_aliases: Optional[Sequence[Tuple[str, str]]] = None,
    repo_root: Optional[Path] = None,
) -> "OrchestrateArgs":
    """保存済み GUI 設定から `OrchestrateArgs` を構築する（Qt に依存しない）。

    Args:
        settings: `settings_store.load()` / `defaults()` と同じ構造の dict。
        workflow: 対象 Workflow ID（必須）。
        overrides: Prompt 版 request の `settings_overrides`（allowlist 検証済みでなくてよい）。
        steps: 実行対象 Step ID。空なら `--steps` を渡さない。
        goal: `--additional-prompt` へ渡す文字列。
        input_aliases: `(canonical, actual)` の並び。
        repo_root: GUI 内部利用のリポジトリルート。

    Raises:
        ValueError: `workflow` が空、または `overrides` に許可外のキーがある場合。
    """
    if not (workflow or "").strip():
        raise ValueError("workflow が空です。")

    from ..prompt_request import ALLOWED_SETTINGS_OVERRIDES

    merged_overrides = dict(overrides or {})
    rejected = sorted(set(merged_overrides) - ALLOWED_SETTINGS_OVERRIDES)
    if rejected:
        raise ValueError(
            "settings_overrides に許可されていないキーがあります: " + ", ".join(rejected)
        )

    options: Mapping[str, Any] = dict((settings or {}).get("options", {}))
    field_by_name = _field_map()

    args = OrchestrateArgs(
        workflow=workflow.strip(),
        repo_root=repo_root or Path.cwd(),
    )

    for key, value in options.items():
        if key in _RUNTIME_OWNED_FIELDS or key in _SPECIAL_SETTINGS_KEYS:
            continue
        field_name = _SETTINGS_KEY_ALIASES.get(key, key)
        f = field_by_name.get(field_name)
        if f is None:
            continue
        setattr(args, field_name, _coerce_for_field(f, value))

    # --- 個別変換 ---
    args.auto_qa = _coerce_tristate(options.get("auto_qa")) is True

    self_improve = _coerce_tristate(options.get("self_improve"))
    args.self_improve = self_improve is True
    args.no_self_improve = self_improve is False

    issue_number = str(options.get("issue_number") or "").strip()
    args.issue_number = int(issue_number) if issue_number.isdigit() else None

    if workflow.strip() == "akm":
        selected_sources = [
            name
            for key, name in (
                ("sources_workiq", "workiq"),
                ("sources_qa", "qa"),
                ("sources_original_docs", "original-docs"),
            )
            if options.get(key)
        ]
        args.sources = ",".join(selected_sources) if selected_sources else None
        args.target_files = _split_whitespace_list(options.get("target_files"))
        args.force_refresh = _coerce_tristate(options.get("force_refresh"))
        args.custom_source_dir = _split_whitespace_list(
            options.get("custom_source_dir")
        )

    if not args.self_improve:
        args.self_improve_max_iterations = None
        args.self_improve_target_scope = None
        args.self_improve_goal = None

    if options.get("tool_search_ranking") == "hve":
        args.tool_search_ranking = "hve"

    # --- Prompt 版が所有する値 ---
    for key, value in merged_overrides.items():
        f = field_by_name.get(key)
        if f is None:
            continue
        setattr(args, key, _coerce_for_field(f, value))

    # GUI 保存値 "user" は IPC を持たない Prompt 経路では既定の対話判定へ落とす。
    qa_mode = str(options.get("qa_answer_mode") or "").strip()
    args.qa_answer_mode = (
        qa_mode if args.auto_qa and qa_mode == "autopilot" else None
    )

    if steps:
        args.steps = ",".join(s for s in steps if s)
    if goal:
        args.additional_prompt = goal
    if input_aliases:
        args.input_aliases = [(c, a) for c, a in input_aliases]
    args.dry_run = False

    return args


def apply_watch_settings(args: "OrchestrateArgs", options: Mapping[str, Any]) -> None:
    """設定ストアの ``[options]`` から watch 系の値を ``OrchestrateArgs`` へ反映する。

    mdq / cq のリアルタイム索引更新は同じ 3 状態 + debounce の構造を持つため、
    ブリッジは 1 実装に集約する（FR-MAINT-07）。設定ストアは 3 状態を文字列で
    保持するため、`_append_tristate` が解釈できる bool / None へ正規化する。
    """
    for prefix in ("mdq", "cq"):
        watch_key = f"{prefix}_watch"
        debounce_key = f"{prefix}_watch_debounce_ms"
        if watch_key in options:
            setattr(args, watch_key, _coerce_tristate(options[watch_key]))
        if debounce_key in options:
            raw = options[debounce_key]
            setattr(
                args, debounce_key,
                raw if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0
                else None,
            )


def _append_tristate(
    argv: List[str],
    enable_flag: str,
    disable_flag: str,
    value: TriState,
) -> None:
    """3 状態フラグ（BooleanOptionalAction）を argv に追加する。

    Args:
        argv: 構築中の引数リスト
        enable_flag: ON 時のフラグ名（例: `--banner`）
        disable_flag: OFF 時のフラグ名（例: `--no-banner`）
        value: True=ON / False=OFF / None=未指定（追加しない）
    """
    if value is True:
        argv.append(enable_flag)
    elif value is False:
        argv.append(disable_flag)
    # value is None → 未指定なので何も追加しない


def _shell_quote(s: str) -> str:
    """空白や特殊文字を含む引数を Windows / POSIX 両対応で簡易クォートする。

    純粋表示用（コピー&ペースト時の利便性）。shlex 等は使わず、
    空白 or " or ' を含む場合に二重引用符で囲む簡易方式。
    """
    if not s:
        return '""'
    if any(c in s for c in (" ", "\t", '"', "'", "\\")):
        # 内部の二重引用符はエスケープ
        return '"' + s.replace('"', '\\"') + '"'
    return s
