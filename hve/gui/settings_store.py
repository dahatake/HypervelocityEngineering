"""hve.gui.settings_store — GUI のオプション既定値を `hve/.settings.txt` (INI) に永続化する。

設計:
  - 単一ファイル `hve/.settings.txt` (INI / configparser)。
  - セクション: `[options]` (フラットなキー=値) と `[mdq]` (MDQ 関連)。
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
from typing import Any, Dict, Optional

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
            # C2
            "max_parallel": 15,
            # C3 自動プロンプト
            "auto_qa": False,
            "qa_answer_mode": "autopilot",  # "autopilot" | "user"（auto_qa=True 時のみ有効）
            "force_interactive": False,
            "auto_contents_review": False,
            "auto_coding_agent_review": False,
            "auto_coding_agent_review_auto_approval": False,
            # C5 Issue/PR
            "create_issues": False,
            "create_pr": False,
            "ignore_paths": "",
            "repo": "",
            "issue_title": "",
            # C6 出力制御（ウィザード非露出は設定パネル専用）
            "verbosity": "compact",
            "log_level": "error",
            "timestamp_style": "prefix",
            "verbose": False,
            "quiet": False,
            "show_stream": False,
            "no_color": False,
            "banner": "",  # 空 = 未指定 (inherit)
            "screen_reader": False,
            "final_only": False,
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
            # C15
            "additional_prompt": "",
            "context_max_chars": 0,
            # C16
            "self_improve": False,
            "no_self_improve": False,
            "mdq_watch": "",  # 空 = 未指定
            "mdq_watch_debounce_ms": 0,
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
            # C10 (App ID) 既定値。
            "app_id": "",
            "app_ids": "",
            "usecase_id": "",
            # C11 (AKM) 既定値（sources_* 以外）。
            "target_files": "",
            "force_refresh": "",  # tri-state
            "custom_source_dir": "",
            # C12 (AQOD) 既定値（depth は既存）。
            "target_scope": "",
            "focus_areas": "",
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
            "resource_group": "",
            # ADOC 既定
            "doc_purpose": "all",
            "max_file_lines": 0,
            "exclude_patterns": "node_modules/,vendor/,dist/,*.lock,__pycache__/",
            # AQOD 既定
            "depth": "standard",
            # tdd_max_retries は設定パネル送り
            "tdd_max_retries": 0,
            # Autopilot 並列上限（GUI Orchestrator Autopilot モード）。
            # 範囲: 1〜16、既定 4。子 GUI プロセスの同時起動数を制限する。
            "autopilot_max_parallel": 4,
            # R5-c: プランレビュー Dialog の常時表示（Step 1 統合 precheck 共通）。
            # 旧名: autopilot_show_plan_review_always（_RENAMED_KEYS で自動移行）。
            # False（既定）: ギャップ 0 件時は Dialog を skip して直接実行へ進む。
            # True: ギャップ 0 件でも必ずプランレビュー Dialog を表示する
            # （実行プランの内訳確認を毎回行いたい上級ユーザー向け）。
            "step1_show_plan_review_always": False,
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
            "explorer_roots": "docs;docs-generated;knowledge;original-docs;qa;users-guide",
            # 全 Dock レイアウトの永続化（QMainWindow.saveState() の base64 文字列）。
            # 空文字列 = 未保存（既定レイアウトで起動）。
            "workbench_layout_state": "",
            # Issue-gui-session-workdir-isolation T7/T8:
            # GUI セッション作業ディレクトリ (work/gui-runs/<id>/) の後処理。
            # "keep"   = 何もしない（既定）
            # "archive" = work/gui-runs/.archive/<id>.zip に zip 化して元 dir 削除
            # "purge"  = 元 dir を削除
            "gui_session_cleanup_policy": "keep",
        },
        "mdq": {
            # MDQ インデックスの自動更新ポリシー等の将来拡張用
            "auto_refresh_on_start": False,
            # Tokenize 言語。FTS5 トークナイザと per-language DB インスタンス
            # の選択に使用する。"ja-jp" / "en-us"。
            "tokenize_language": "ja-jp",
            # Markdown chunking strategy。`.mdq/index-<lang>-<strategy>.sqlite`
            # の <strategy> 部分。"heading" / "heading_recursive" / "fixed_window"。
            "chunk_strategy": "heading",
            # Markdown-Query 対象フォルダ（リポジトリ相対 POSIX パス、";" 区切り）。
            # 空 = 未指定（mdq CLI 既定の DEFAULT_ROOTS を使用、Agent への強制プロンプトも注入しない）。
            # 非空 = 索引対象と Agent への mdq 利用強制の両方に使用する。
            "target_folders": "",
            # 一括ビルド対象 Strategy 群 (T17)。";" 区切り Strategy 名リスト。
            # 空 = 全 Strategy 選択扱い (Q3「全 Strategy アクティブ」と整合)。
            "build_strategies": "",
            # heading_recursive 戦略の overlap 段落数（既存 standalone GUI と
            # 同期）。0 で overlap 無効。既定 1。
            "overlap_paragraphs": 1,
            # --- semantic_paragraph 戦略専用 (Q3=A 単一プロファイル) -----------
            # CLI フラグと 1:1 対応。0 / 0.0 / "" / False の値は
            # mdq.strategies_semantic の SEMANTIC_* 既定値にフォールバック。
            "semantic_max_chunk_chars": 0,
            "semantic_min_chars": 0,
            "semantic_breakpoint_percentile_lo": 0.0,
            "semantic_breakpoint_percentile_hi": 0.0,
            "semantic_embed_provider": "",
            "semantic_embed_model": "",
            "semantic_contextualize": True,
            "semantic_late_chunking": False,
            "semantic_fusion_alpha": 0.5,
            "semantic_bge_m3_warning_dismissed": False,
        },
    }


# Q9=b: 廃止済みキー。読み込み時に検出し、ファイルから削除して再保存する。
_OBSOLETE_KEYS: Dict[str, set[str]] = {
    "options": {"mcp_config", "workiq_tenant_id"},
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
# Markdown-Query 対象フォルダ ([mdq] target_folders)
# ---------------------------------------------------------------------------
def _normalize_target_folder(raw: str) -> Optional[str]:
    """フォルダパス1件を正規化する。

    - 前後空白・引用符を除去
    - バックスラッシュを '/' に変換
    - 末尾 '/' を除去
    - 空文字や '.' は ``None``
    """
    s = (raw or "").strip().strip('"').strip("'")
    if not s:
        return None
    s = s.replace("\\", "/")
    while s.endswith("/") and len(s) > 1:
        s = s[:-1]
    if s in ("", "."):
        return None
    return s


def parse_target_folders(raw: str) -> list[str]:
    """';' 区切り文字列を正規化済みパスのリストに変換する（重複除去・順序保持）。"""
    out: list[str] = []
    seen: set[str] = set()
    for part in (raw or "").split(";"):
        norm = _normalize_target_folder(part)
        if norm is None or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def serialize_target_folders(folders: list[str]) -> str:
    """正規化済みリストを ';' 区切り文字列にシリアライズする。"""
    normed: list[str] = []
    seen: set[str] = set()
    for item in folders or []:
        norm = _normalize_target_folder(str(item))
        if norm is None or norm in seen:
            continue
        seen.add(norm)
        normed.append(norm)
    return ";".join(normed)


def get_mdq_target_folders(
    *, settings: Optional[Dict[str, Dict[str, Any]]] = None
) -> list[str]:
    """``[mdq] target_folders`` を正規化済みリストで取得する。

    未設定または空のときは空リストを返す（呼び出し側で「何もしない」判定に使用）。
    """
    s = settings if settings is not None else load()
    raw = s.get("mdq", {}).get("target_folders", "")
    return parse_target_folders(str(raw))


# ---------------------------------------------------------------------------
# T5 (Wave 1 / C2): MCP Server 利用 ON/OFF (mcp_enabled セクション)
# ---------------------------------------------------------------------------
def load_mcp_enabled() -> Dict[str, bool]:
    """``[mcp_enabled]`` セクションを ``{server_name: bool}`` で読み込む。

    セクション欠落・ファイル無し・破損時は ``{}`` を返す (捏造禁止)。
    """
    path = settings_path()
    if not path.exists():
        return {}
    cp = configparser.ConfigParser()
    try:
        cp.read(path, encoding="utf-8")
    except (configparser.Error, OSError):
        return {}
    if "mcp_enabled" not in cp:
        return {}
    out: Dict[str, bool] = {}
    for key, raw in cp.items("mcp_enabled"):
        out[key] = raw.strip().lower() in ("1", "true", "yes", "on")
    return out


def save_mcp_enabled(mcp_enabled: Dict[str, bool]) -> None:
    """``[mcp_enabled]`` セクションをアトミックに更新する (他セクションは保持)。"""
    cp = configparser.ConfigParser()
    path = settings_path()
    if path.exists():
        try:
            cp.read(path, encoding="utf-8")
        except (configparser.Error, OSError):
            cp = configparser.ConfigParser()
    # 敵対的レビュー #15: 廃止キーをこの機会に migration
    _migrate_obsolete_keys(cp)
    cp["mcp_enabled"] = {name: ("true" if bool(v) else "false") for name, v in mcp_enabled.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        cp.write(f)
    os.replace(tmp, path)
