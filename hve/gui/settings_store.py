"""hve.gui.settings_store — GUI のオプション既定値を `hve/.settings.txt` (INI) に永続化する。

設計:
  - 単一ファイル `hve/.settings.txt` (INI / configparser)。
  - セクション: `[options]` (フラットなキー=値)、`[mdq]` (Markdown Query)、`[cq]` (Code Query)。
    `[mdq]` の既定値は `mdq` パッケージが所有する (FR-GUI-05)。
  - 値型は文字列/真偽値/整数/浮動小数/リスト(セミコロン区切り)を扱う。
  - 書き込みは tmp + os.replace でアトミック。
  - 値が無い・破損時は `defaults()` の値を返す（捏造禁止 = 既定は明示）。

設定パネル（VS Code 風）が SoT。Step 2 はここから既定値を読み出す。
"""

from __future__ import annotations

import configparser
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from mdq.gui import settings_store as _mdq_settings_store

_logger = logging.getLogger(__name__)

# `hve/.settings.txt` 固定パス（hve パッケージ直下）。
_SETTINGS_PATH = Path(__file__).resolve().parent.parent / ".settings.txt"


def settings_path() -> Path:
    """設定ファイルパスを返す（テスト差し替え可能）。"""
    return _SETTINGS_PATH


# ---------------------------------------------------------------------------
# 既定値定義（ウィザード CLI の挙動と一致させること）
# ---------------------------------------------------------------------------
def defaults() -> Dict[str, Dict[str, Any]]:
    """設定既定値。ウィザード CLI の既定値と整合させる。"""
    return {
        "options": {
            # C1 基本
            "model": "Auto",
            "review_model": "",  # 空 = 継承
            "qa_model": "",
            # reasoning_effort (空 = 未指定)
            "reasoning_effort": "",
            "review_reasoning_effort": "",
            "qa_reasoning_effort": "",
            # context_tier: SDK create_session(context_tier=...) へ渡す値。
            # 設定画面の既定は long_context（要件）。
            "context_tier": "long_context",
            # `<run-id>` 生成時のタイムゾーン (IANA 名)。既定 JST。
            "run_id_timezone": "Asia/Tokyo",
            # C2
            "max_parallel": 15,
            # QA (質問票) / Knowledge Management / レビュー
            # auto_qa は必須選択のため既定は未選択（"" | "on" | "off"）。
            "auto_qa": "",
            "qa_answer_mode": "autopilot",  # "autopilot" | "user"（auto_qa=True 時のみ有効）
            # QA 回答を knowledge/ へバックグラウンドでマージするか（FR-QA-05、既定: 無効）。
            "qa_akm_background_merge": False,
            # QA 起点 AKM 子実行専用の実行品質（空 = メイン設定を継承）。
            "akm_model": "",
            "akm_reasoning_effort": "",
            "akm_context_tier": "",
            "auto_contents_review": False,
            "auto_coding_agent_review": False,
            "auto_coding_agent_review_auto_approval": False,
            # C5 Issue/PR
            "create_issues": False,
            "create_pr": False,
            "create_working_branch": True,
            "ignore_paths": "",
            "repo": "",
            "issue_title": "",
            # FR-GUI-25: Root Issue の扱い（"new" | "existing"）と連携先 Issue 番号
            "issue_mode": "new",
            "issue_number": "",
            # FR-GUI-32: コンソール出力の投稿先として使う PR 番号。
            # GUI セッション内限定で Orchestrator へは伝達しない。
            "linked_pr_number": "",
            # C6 出力制御。設定画面の「出力制御」ノードは撤去済みで、
            # `verbosity` 以外は Step 1 右ペインで選ぶセッション限りの値
            # （settings_apply._SECTION_FIELDS に C6 は無く往復しない）。
            "verbosity": "compact",
            # テーマ (Step 2 「作業状況」ツリーの表示色)
            "theme": "light",  # "dark" | "light"
            # GUI 表示言語 ("auto" | "ja_JP" | "en_US"). "auto" = OS ロケールから判定。
            "language": "auto",
            # C7 CLI 接続（設定パネル専用）
            # ※ mcp_config / workiq_tenant_id は Copilot CLI 側で管理されるため廃止済み (Wave 3 / Q9=b)。
            "cli_path": "",
            "cli_url": "",
            # C8 タイムアウト
            "timeout": 21600.0,
            "review_timeout": 7200.0,
            "workiq_per_question_timeout": 0.0,  # 0 = 未指定 (既定 1200)
            "workiq_request_timeout": 300.0,  # Work IQ MCP ツール呼び出し 1 回あたりのタイムアウト秒数（既定 5 分）
            # C9 ブランチ
            "branch": "main",
            # FR-GUI-38: 進捗を引き継ぐ再実行の run-id（空欄 = 通常実行）
            "resume_run": "",
            # C15
            "additional_prompt": "",
            "context_max_chars": 0,
            # C16
            "self_improve": "",
            # self_improve_* は _SECTION_FIELDS["SELFIMPROVE"] 登録済みだが defaults 未登録だった。
            # _coerce(default=None) フォールバックでの型喪失を防ぐため明示既定値を置く
            # (page_options の QSpinBox=3 / QLineEdit="" / QPlainTextEdit="" と整合)。
            "self_improve_max_iterations": 3,
            "self_improve_target_scope": "",
            "self_improve_goal": "",
            "mdq_watch": "",  # 空 = 未指定
            "mdq_watch_debounce_ms": 0,
            # cq リアルタイム索引更新（FR-GUI-04）。mdq 系と同じく
            # `[options]` 側に置き、`settings_apply` の autosave 経路へ乗せる。
            # debounce は 0 = 未指定（cq 側の既定を使う）。
            "cq_watch": "",
            "cq_watch_debounce_ms": 0,
            # C11 (AKM) sources チェックボックス 3 個の永続化既定値。
            # 旧実装では `_SECTION_FIELDS` に登録されておらず保存されなかったため、
            # ここに既定値を明示し autosave 経路に乗せる（_C11AKM の初期値と整合）。
            "sources_qa": True,
            "sources_original_docs": True,
            "sources_workiq": False,
            # C4 (Work IQ) 既定値。`_SECTION_FIELDS` に登録済みだが
            # `defaults()` に未登録だったため、_coerce(default=None) フォールバックで
            # 文字列 "false" が QCheckBox に渡り bool("false")=True で反転していた。
            # 明示既定値で型情報を確保する（_C4WorkIQ の初期値と整合）。
            # セクション C4 / C5 / C10 以下は UI グルーピング名で、
            # 保存先は全て [options] セクションとなる（collect_from_widgets の仕様）。
            "workiq": False,
            "workiq_draft": False,
            "workiq_akm_review": "",  # tri-state: "" = 未指定 / "on" / "off"
            "workiq_akm_ingest": "",
            "workiq_dxx": "",
            "workiq_draft_output_dir": "",
            "workiq_prompt_qa": "",
            "workiq_prompt_km": "",
            "workiq_prompt_review": "",
            # C5 (Issue/PR) 追加既定値。_SECTION_FIELDS 登録済みだが defaults 未登録だった。
            "enable_auto_merge": False,
            "delete_local_merged_branch": True,
            # FR-GUI-36: 自動進捗 Post の送信先。off / issue / pr / both。既定は off。
            "github_auto_post_target": "off",
            # C10 (App ID) 既定値。
            "app_ids": "",
            "usecase_id": "",
            # C11 (AKM) 既定値（sources_* 以外）。
            "target_files": "",
            "force_refresh": "",  # tri-state
            "custom_source_dir": "",
            # ADI で再利用する既定値（depth は既存）。
            "target_scope": "",
            "focus_areas": "",
            # C17 (ADI) 既定値。
            "purpose": "",
            # C13 (ADOC) 既定値（exclude_patterns/doc_purpose/max_file_lines は既存）。
            "target_dirs": "",
            # C14 (ARD) 既定値。
            "company_name": "",
            "target_business": "",
            "survey_base_date": "",
            "survey_period_years": 0,
            "target_region": "",
            "analysis_purpose": "",
            "target_recommendation_id": "",
            "attached_docs": "",
            # AZURE セクション既定値。
            # FR-GUI-03: 永続化するのは `default_params` を持たない必須パラメータだけ。
            # 既定値そのものはレジストリ側 `StepDef.default_params` が正本であり、
            # ここでは空文字を置いて二重管理を避ける。
            "resource_group": "",
            # ADOC 既定
            "doc_purpose": "all",
            "max_file_lines": 0,
            "exclude_patterns": "node_modules/,vendor/,dist/,*.lock,__pycache__/",
            # 既存キー互換の既定値
            "depth": "standard",
            # Autopilot 並列上限（GUI Orchestrator Autopilot モード）。
            # 範囲: 1〜16、既定 4。子 GUI プロセスの同時起動数を制限する。
            "autopilot_max_parallel": 4,
            # R5-c: プランレビュー Dialog の常時表示（Step 1 統合 precheck 共通）。
            # 旧名: autopilot_show_plan_review_always（_RENAMED_KEYS で自動移行）。
            # False（既定）: ギャップ 0 件時は Dialog を skip して直接実行へ進む。
            # True: ギャップ 0 件でも必ずプランレビュー Dialog を表示する
            # （実行プランの内訳確認を毎回行いたい上級ユーザー向け）。
            "step1_show_plan_review_always": False,
            # SDK 自動コンテキスト圧縮（infinite_sessions）をサブステップ実行で有効化するか。
            # False（既定）: 無効。True: --auto-compaction を subprocess に伝播し SDK に圧縮を委ねる。
            "auto_compaction": False,
            # SDK のツール定義遅延ロード（tool_search）を有効化するか。
            # True（既定）: 有効。False: `--no-tool-search` を subprocess へ伝搬する。
            # FR-MODEL-06: 保存済みの false は load() のマージで保持される。
            "tool_search": True,
            # 上記を有効にしたときのランキング実装（FR-TS-01）。
            # "sdk"（既定）: SDK 組み込み。"hve": HVE 実装へ差し替え、統計も収集する。
            "tool_search_ranking": "sdk",            # FR-LOCAL-SURFACE-01 (a): Agentic Retrieval の shared setting 6 項目。
            # 値は `page_options._CAgenticRetrieval` の userData と同じ文字列表現を
            # そのまま保存する（空文字 = 「既定に従う」= CLI へ渡さない）。
            "enable_agentic_retrieval": "auto",
            "agentic_data_source_modes": "",
            "foundry_mcp_integration": "",
            "agentic_data_sources_hint": "",
            "agentic_existing_design_diff_only": "",
            "foundry_sku_fallback_policy": "",
            # FR-LOCAL-SURFACE-01 (a): SDK tool search の 3 状態選択。
            # 上記 `tool_search`（TOOLSEARCH セクションの bool）とは別の
            # Step 1 側 3 状態 UI で、"auto" のとき CLI へ渡さない。
            "enable_tool_search": "auto",
            # FR-LOCAL-SURFACE-01 (a): CLI `--strict` と共通。
            # False（既定）: local 実行モードの continue-on-precheck を維持する。
            "strict": False,
            # Fleet mode（GitHub Copilot SDK 1.0.0+）。既定 OFF。
            # SPLIT_REQUIRED ではなく、複数 Step の DAG wave を対象にする。
            "fleet_mode_enabled": "",
            # Cloud Sessions（GitHub Copilot SDK 1.0.0+）。既定 OFF。
            "cloud_session_enabled": False,
            "cloud_session_repository_branch": "",
            "cloud_session_max_concurrency": 5,
            "cloud_session_integration_id": "",
            "cloud_session_mc_base_url": "",
            "cloud_session_step_overrides": "",
            "cloud_session_subtask_overrides": "",
            # AAS 完了後 / downstream 起動前の APP-ID 選択ダイアログ。
            # True（既定）: AAS が catalog を再生成した直後にダイアログを表示し、
            #   ユーザーが downstream 対象 APP-ID を絞り込めるようにする。
            # False: ダイアログを出さず catalog 全件を downstream に流す（旧挙動）。
            "autopilot_show_app_id_picker": True,
            # APP-ID 選択ダイアログのタイムアウト秒数。
            # 既定 300 秒 = 要件 5 分。UI 上は 30〜3600 秒の範囲で変更可能。
            # （store 側ではバリデーション無し。値域は SpinBox と main_window 側で担保）
            # タイムアウト経過時はその時点のチェック状態で自動 OK となる。
            "autopilot_app_id_picker_timeout_sec": 300,
            # ウィンドウ横幅の永続化（ユーザーが手動でリサイズした際のみ保存）。
            # 0 = 未設定（既定の 1100 を使用）。
            "main_window_width": 0,
            "workbench_window_width": 0,
            # Dock パネル表示状態（Phase D 追加）。
            # file_explorer_visible: 既定は表示（起動直後から左サイドバーを開く）。
            # markdown_preview_visible: 既定は非表示。エクスプローラーでファイルが
            #   選択された瞬間に MainWindow が setVisible(True) し、その後ユーザーが
            #   閉じるまで保持。
            "file_explorer_visible": True,
            "markdown_preview_visible": False,
            # Explorer ルート設定（Wave A 追加）。
            # ";" 区切りのリポジトリ相対 POSIX パスリスト。未存在のものは設定保存時と
            # 起動時に mkdir(parents=True, exist_ok=True) で自動作成する（.gitkeep は作らない）。
            # 既定値は本リポジトリ標準成果物ディレクトリ群。
            "explorer_roots": "docs;docs-generated;docs-original;knowledge;qa;users-guide",
            # Issue-gui-session-workdir-isolation T7/T8:
            # GUI セッション作業ディレクトリ (work/run/<id>/) の後処理。
            # "keep"   = 何もしない（既定）
            # "archive" = work/archive/<id>.zip に zip 化して元 dir 削除
            # "purge"  = 元 dir を削除
            "gui_session_cleanup_policy": "keep",
        },
        # FR-GUI-05 / FR-MAINT-07: strategy 固有パラメータを含む `[mdq]` の既定値は
        # `mdq` パッケージが単一の情報源であり、ここへ複写して二重管理しない。
        "mdq": _mdq_settings_store.defaults(),
        "cq": {
            # FR-GUI-04: cq 索引の GUI 運用設定。
            # 索引ルート・除外・最大ファイルサイズは cq の設定ファイルが SoT
            # であり、GUI からは書き換えないためここには持たない。
            # profile は空 = 未選択。特定の profile 名を既定値として持たない（他
            # リポジトリでは存在しないため）。未選択時は設定ファイルの先頭 profile を採る。
            "profile": "",
            # 一括ビルド対象 profile 群。";" 区切り。空 = 全 profile 選択扱い。
            "build_profiles": "",
        },
    }

# Q9=b: 廃止済みキー。読み込み時に検出し、ファイルから削除して再保存する。
_OBSOLETE_KEYS: Dict[str, set[str]] = {
    "options": {
        "mcp_config",
        "workiq_tenant_id",
        # FR-WF-ASDW-02: GUI 入力欄を廃止した ASDW-WEB Step 1.3 の既定値付きパラメータ。
        # 保存値を残すと UI から修正できないままレジストリ既定値を上書きし続ける。
        "data_location",
        "data_resource_suffix",
        "data_vnet_cidr",
        "data_private_endpoint_subnet_cidr",
        "data_aci_subnet_cidr",
        # 参照元の無いキー。値を残すと「編集しても効かない設定」になる。
        # app_id: 入力欄は `app_ids` のみで、実行時はその先頭から補完される。
        # tdd_max_retries: FR-LOCAL-SURFACE-01 (b) の workflow param であり、
        #   宣言した Workflow を選んだときだけ Step 1 で指定する。全体設定として
        #   永続化すると、宣言の無い Workflow にも効く誤解を生むため保存しない。
        # data_verify_aci_image: 検証イメージ参照は `resource_group` /
        #   `data_resource_suffix` から導出する値で、Workflow パラメータではない
        #   （FR-WF-ASDW-02）。
        # workbench_layout_state: settings_store 以外から参照されない。
        "app_id",
        "tdd_max_retries",
        "data_verify_aci_image",
        "workbench_layout_state",
        # C6 出力制御: 設定画面には表示するが保存・復元は行わない
        # （settings_apply._SECTION_FIELDS に C6 は無い）。実行結果の意味論を
        # 変えないコンソール表示制御であり、FR-LOCAL-SURFACE-01 (e) の除外対象。
        "log_level",
        "timestamp_style",
        "verbose",
        "quiet",
        "show_stream",
        "no_color",
        "banner",
        "screen_reader",
        "final_only",
    },
}

# リネーム済みキー: 旧キー名 -> 新キー名。読み込み時に旧キー値を新キーへ移行し、
# 旧キーは削除して再保存する（後方互換マイグレーション）。
_RENAMED_KEYS: Dict[str, Dict[str, str]] = {
    "options": {
        # Step 1 [次へ] 統合 precheck へマージした際にキー名を中立化。
        "autopilot_show_plan_review_always": "step1_show_plan_review_always",
    },
}


def _migrate_obsolete_keys(cp: configparser.ConfigParser) -> bool:
    """読み込んだ ``ConfigParser`` から廃止キーを削除する。

    Returns:
        何らかのキーを削除したら ``True``。
    """
    changed = False
    for section, keys in _OBSOLETE_KEYS.items():
        if section not in cp:
            continue
        for key in list(cp[section].keys()):
            if key in keys:
                del cp[section][key]
                changed = True
    return changed


def _migrate_renamed_keys(cp: configparser.ConfigParser) -> bool:
    """読み込んだ ``ConfigParser`` で、旧キー名を新キー名へ移行する。

    新キーが既にある場合は新キー側を優先し、旧キーだけを削除する。

    Returns:
        何らかのマイグレーションを実施したら ``True``。
    """
    changed = False
    for section, mapping in _RENAMED_KEYS.items():
        if section not in cp:
            continue
        for old_key, new_key in mapping.items():
            if old_key not in cp[section]:
                continue
            if new_key not in cp[section]:
                cp[section][new_key] = cp[section][old_key]
            del cp[section][old_key]
            changed = True
    return changed


def _migrate_legacy_explorer_roots(cp: configparser.ConfigParser) -> bool:
    """旧ルート ``original-docs`` を ``docs-original`` へ置換する。"""
    if "options" not in cp:
        return False

    options = cp["options"]
    raw = options.get("explorer_roots")
    if raw is None:
        return False

    migrated: list[str] = []
    changed = False
    for token in raw.split(";"):
        normalized = token.strip().replace("\\", "/").rstrip("/")
        if normalized == "original-docs":
            migrated.append("docs-original")
            changed = True
        else:
            migrated.append(token)

    if changed:
        options["explorer_roots"] = ";".join(migrated)
    return changed


def _migrate_self_improve_tristate(cp: configparser.ConfigParser) -> bool:
    """旧boolean pairを ``self_improve = on/off/''`` へ移行する。

    優先順位はCLIと同じく旧 ``no_self_improve=true`` が最優先。新形式の
    ``on`` / ``off`` / 空値は保持し、旧キーだけを削除する。
    """
    if "options" not in cp:
        return False
    options = cp["options"]
    if "self_improve" not in options and "no_self_improve" not in options:
        return False

    raw_enabled = options.get("self_improve", "").strip().lower()
    raw_disabled = options.get("no_self_improve", "").strip().lower()
    truthy = {"1", "true", "yes", "on"}
    legacy_boolean = raw_enabled in {
        "1", "0", "true", "false", "yes", "no",
    }

    if raw_disabled in truthy:
        normalized = "off"
    elif raw_enabled in truthy:
        normalized = "on"
    elif legacy_boolean or raw_enabled in {"", "inherit"}:
        normalized = ""
    elif raw_enabled == "off":
        normalized = "off"
    else:
        # 不明値は既定継承へ縮退し、暗黙の変更実行を避ける。
        normalized = ""

    changed = options.get("self_improve", "") != normalized
    options["self_improve"] = normalized
    if "no_self_improve" in options:
        del options["no_self_improve"]
        changed = True
    return changed


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
def load() -> Dict[str, Dict[str, Any]]:
    """設定を読み込む。ファイル無し/壊れている場合は defaults() を返す。

    読み込み時に廃止キー (mcp_config / workiq_tenant_id) を検出したら
    自動マイグレーション（ファイルから削除して再保存）を実行する。
    """
    base = defaults()
    path = settings_path()
    if not path.exists():
        return base

    cp = configparser.ConfigParser()
    try:
        cp.read(path, encoding="utf-8")
    except (configparser.Error, OSError):
        return base

    # Q9=b: 廃止キーを削除し、検出したらファイルを更新する。
    # 加えて、リネーム済みキーを新キー名へ移行する。
    changed = False
    if _migrate_obsolete_keys(cp):
        changed = True
    if _migrate_renamed_keys(cp):
        changed = True
    if _migrate_legacy_explorer_roots(cp):
        changed = True
    if _migrate_self_improve_tristate(cp):
        changed = True
    if changed:
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                cp.write(f)
            os.replace(tmp, path)
        except OSError:
            # 書き出し失敗は致命的ではない（次回起動時に再試行）。ログには残す。
            _logger.warning(
                "settings migration write-back failed: %s", path, exc_info=True
            )

    merged: Dict[str, Dict[str, Any]] = {sec: dict(vals) for sec, vals in base.items()}
    for section in cp.sections():
        if section not in merged:
            merged[section] = {}
        for key, raw_value in cp.items(section):
            default_value = base.get(section, {}).get(key)
            merged[section][key] = _coerce(raw_value, default_value)
    return merged


def save(settings: Dict[str, Dict[str, Any]]) -> None:
    """設定をアトミックに保存する。"""
    cp = configparser.ConfigParser()
    for section, vals in settings.items():
        cp[section] = {k: _to_str(v) for k, v in vals.items()}

    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        cp.write(f)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 型変換ヘルパー
# ---------------------------------------------------------------------------
def _to_str(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _coerce(raw: str, default: Any) -> Any:
    """既定値の型に合わせて文字列を変換する。"""
    if isinstance(default, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(raw)
        except ValueError:
            return default
    if isinstance(default, float):
        try:
            return float(raw)
        except ValueError:
            return default
    # str / None
    return raw


def get_option(key: str, *, settings: Optional[Dict[str, Dict[str, Any]]] = None) -> Any:
    """単一オプション値を取得する（既定値フォールバック付）。"""
    s = settings if settings is not None else load()
    return s.get("options", {}).get(key, defaults()["options"].get(key))


def set_option(key: str, value: Any) -> None:
    """単一オプション値を保存する（load -> 変更 -> save のショートカット）。

    既定値セクションに含まれないキーも書き込めるが、再読込時に defaults に
    マージされるため呼び出し側は ``defaults()`` への追記とセットで運用すること。
    """
    s = load()
    if "options" not in s:
        s["options"] = {}
    s["options"][key] = value
    save(s)


# ---------------------------------------------------------------------------
# ';' 区切りリスト（[mdq] target_folders / [cq] build_profiles など）
# ---------------------------------------------------------------------------
def _strip_quotes(raw: str) -> Optional[str]:
    s = (raw or "").strip().strip('"').strip("'")
    return s or None


def parse_semicolon_list(
    raw: str, *, normalize: Callable[[str], Optional[str]] = _strip_quotes
) -> list[str]:
    """';' 区切り文字列を要素リストへ分解する（重複除去・順序保持）。

    ``normalize`` が ``None`` を返した要素は捨てる。GUI が扱う ';' 区切り値は
    すべてこの単一実装を通す（FR-MAINT-07）。
    """
    out: list[str] = []
    seen: set[str] = set()
    for part in (raw or "").split(";"):
        norm = normalize(part)
        if norm is None or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def serialize_semicolon_list(
    items: Iterable[Any], *, normalize: Callable[[str], Optional[str]] = _strip_quotes
) -> str:
    """要素リストを ';' 区切り文字列へ整形する（重複除去・順序保持）。"""
    out: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        norm = normalize(str(item))
        if norm is None or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return ";".join(out)


# ---------------------------------------------------------------------------
# Markdown-Query 対象フォルダ ([mdq] target_folders)
# ---------------------------------------------------------------------------
def _normalize_target_folder(raw: str) -> Optional[str]:
    """フォルダパス1件を正規化する。

    - 前後空白・引用符を除去
    - バックスラッシュを '/' に変換
    - 末尾 '/' を除去
    - 空文字や '.' は ``None``
    """
    s = _strip_quotes(raw)
    if s is None:
        return None
    s = s.replace("\\", "/")
    while s.endswith("/") and len(s) > 1:
        s = s[:-1]
    if s in ("", "."):
        return None
    return s


def parse_target_folders(raw: str) -> list[str]:
    """';' 区切り文字列を正規化済みパスのリストに変換する（重複除去・順序保持）。"""
    return parse_semicolon_list(raw, normalize=_normalize_target_folder)


def serialize_target_folders(folders: list[str]) -> str:
    """正規化済みリストを ';' 区切り文字列にシリアライズする。"""
    return serialize_semicolon_list(folders, normalize=_normalize_target_folder)


def get_mdq_target_folders(
    *, settings: Optional[Dict[str, Dict[str, Any]]] = None
) -> list[str]:
    """``[mdq] target_folders`` を正規化済みリストで取得する。

    未設定または空のときは空リストを返す（呼び出し側で「何もしない」判定に使用）。
    """
    s = settings if settings is not None else load()
    raw = s.get("mdq", {}).get("target_folders", "")
    return parse_target_folders(str(raw))
