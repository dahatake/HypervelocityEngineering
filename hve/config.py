"""config.py — SDKConfig: 全オプションを集約する dataclass"""

from __future__ import annotations

import sys
import time
import uuid
from dataclasses import InitVar, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from cq.watcher import DEFAULT_DEBOUNCE_MS as _CQ_DEFAULT_DEBOUNCE_MS

DEFAULT_MODEL: str = "claude-opus-5.5"
DEFAULT_CONTEXT_INJECTION_MAX_CHARS: int = 20_000

# --- Phase 8 S-3: 旧 Custom Agent の tools frontmatter audit 記録用定数 ---
# 【重要】本定数は **ドキュメント用**。SDK にそのまま渡してはいけない。
# 旧 `.github/agents/*.agent.md` の `tools:` frontmatter は「カテゴリ名」
# (edit / execute / read / search / todo / web) を使っていたが、SDK は
# `str_replace_editor`, `bash`, `glob`, `web_search` 等の「実ツール名」を
# `available_tools` / `excluded_tools` に期待するため、カテゴリ名を
# そのまま SDK に渡すと全ツールがブロックされる。
# Phase 6 T-6.1c の audit (77 agent) で 75/77 が要求していた union:
#   edit, execute, read, search, todo, web
# クラスタリングとしての記録としてり、将来 SDK 側で
# カテゴリ名 ↔ 実ツール名のマッピング表が提供された際に
# `available_tools` へポーティングするための参照値として使う。
# 詳細は work/custom-agent-tasks-phase8/completion-report.md を参照。
DEFAULT_AVAILABLE_TOOL_CATEGORIES: tuple[str, ...] = (
    "edit",
    "execute",
    "read",
    "search",
    "todo",
    "web",
)

MODEL_AUTO_VALUE: str = "Auto"
"""hve 内部センチネル（UI 表示・既存 Issue/PR/CLI 引数の後方互換）。"""

MODEL_AUTO_WIRE_VALUE: str = "auto"
"""GitHub Copilot SDK の create_session(model=...) に渡す Auto モデル ID。

GitHub Copilot サーバの models.list レスポンスに正規モデル ID として
``{"id": "auto", "name": "Auto"}`` が含まれており、CLI の ``--model auto``
および SDK の ``create_session(model="auto")`` で Auto Model Selection
（サーバ側動的ルーティング）が発動する。
"""

def to_wire_model(model: Optional[str]) -> Optional[str]:
    """hve 内部センチネル ``"Auto"`` を SDK が受理する ``"auto"`` に変換する。

    - ``MODEL_AUTO_VALUE`` ("Auto") → ``MODEL_AUTO_WIRE_VALUE`` ("auto")
    - その他の文字列 → そのまま返す
    - None / 空文字 → None（呼び出し側で「model キーを payload から省略」と判断）
    """
    if not model:
        return None
    if model == MODEL_AUTO_VALUE:
        return MODEL_AUTO_WIRE_VALUE
    return model


MODEL_CHOICES: tuple[str, ...] = (
    "claude-opus-5.5",
    "claude-opus-4.7",
    "claude-opus-4.6",
    "gpt-5.5",
    "gpt-5.4",
)

# `MODEL_CHOICES` のフォールバック用途を明示する別名。
# オンライン取得（get_model_choices）失敗時・オフライン環境でこの値を使用する。
FALLBACK_MODEL_CHOICES: tuple[str, ...] = MODEL_CHOICES


def get_model_choices(
    *,
    force_refresh: bool = False,
    include_auto: bool = False,
    timeout: float = 30.0,
) -> list[str]:
    """利用可能なモデル ID 一覧を取得する。

    解決順:
        1. force_refresh=False かつキャッシュが TTL 内 → キャッシュを返す
        2. SDK `list_models()` で取得 → 成功時はキャッシュへ保存して返す
        3. SDK 失敗時 stale キャッシュ（TTL 切れ）があれば返す
        4. それも無ければ `FALLBACK_MODEL_CHOICES` を返す

    Args:
        force_refresh: True で 1. をスキップし強制再取得する。
        include_auto: True で表示用の MODEL_AUTO_VALUE ("Auto") を先頭に付加し、
            SDK由来の同じAuto wire値は重複表示しない。
        timeout: SDK 取得タイムアウト秒。

    Returns:
        モデル ID のリスト（include_auto=True 時は表示用 "Auto" が1件だけ先頭）。
    """
    from hve import models_api, models_cache

    ids: Optional[list[str]] = None

    # 1) フレッシュなキャッシュ
    if not force_refresh:
        cached = models_cache.load()
        if cached and cached.models:
            ids = list(cached.models)

    # 2) SDK 再取得
    if ids is None:
        try:
            entries = models_api.fetch_model_entries(timeout=timeout)
            if entries:
                ids = [e.id for e in entries]
                try:
                    models_cache.save_entries(entries)
                except OSError:
                    # キャッシュ書込失敗は致命的でない
                    pass
        except models_api.ModelsAPIError:
            ids = None

    # 3) stale キャッシュ
    if ids is None:
        stale = models_cache.load(allow_stale=True)
        if stale and stale.models:
            ids = list(stale.models)

    # 4) 最終フォールバック
    if ids is None:
        ids = list(FALLBACK_MODEL_CHOICES)

    if include_auto:
        return [
            MODEL_AUTO_VALUE,
            *(model_id for model_id in ids if model_id.casefold() != MODEL_AUTO_WIRE_VALUE),
        ]
    return ids


def normalize_model(name: str) -> str:
    """モデル ID を正規化する（パススルー実装）。
    Wave 4: claude-opus-4-7 後方互換レイヤ削除済み。現在は入力をそのまま返す。
    """
    if not name:
        return name
    return name


def _catalog_model_ids() -> frozenset[str]:
    """SDK `list_models()` のキャッシュにあるモデル ID（FR-MODEL-03）。

    ネットワークへ出ず、キャッシュが無い・読めない場合は空集合を返す。
    """
    try:
        from hve import models_cache

        cached = models_cache.load(allow_stale=True)
    except Exception:  # pragma: no cover - キャッシュ読込失敗は許可リストを広げないだけ
        return frozenset()
    if not cached or not cached.models:
        return frozenset()
    return frozenset(str(model_id) for model_id in cached.models)


def _normalize_model_with_warning(name: Optional[str]) -> Optional[str]:
    """モデル名を正規化する（後方互換ラッパー）。

    許可リスト（MODEL_CHOICES + MODEL_AUTO_VALUE + SDK の model catalog キャッシュ）に含まれない値が来た場合、
    WARNING を発出して MODEL_AUTO_VALUE を返す。
    これにより既存 Issue/PR の廃止モデル指定（claude-sonnet-4.6 等）は Auto にフォールバックされる。
    """
    if name is None:
        return None
    normalized = normalize_model(name)
    allowed = set(MODEL_CHOICES) | {MODEL_AUTO_VALUE}
    if normalized and normalized not in allowed and normalized in _catalog_model_ids():
        return normalized
    if normalized and normalized not in allowed:
        import warnings
        warnings.warn(
            f"モデル '{normalized}' はサポートされていません。"
            f"有効なモデル: {sorted(allowed)}。"
            f"'{MODEL_AUTO_VALUE}' にフォールバックします。",
            stacklevel=3,
        )
        return MODEL_AUTO_VALUE
    return normalized


def generate_run_id(tz: Optional[str] = None) -> str:
    """ワークフロー実行ごとのユニークID。

    タイムスタンプ（人間可読 + ソート可能）+ UUID短縮（衝突防止）
    例: "20260413T143022-a1b2c3"

    タイムゾーン解決順:
      1. 引数 ``tz`` (IANA 名)
      2. 環境変数 ``HVE_RUN_ID_TZ``
      3. ``Asia/Tokyo`` (JST 既定)

    不正なタイムゾーン名は警告なしで既定 ``Asia/Tokyo`` にフォールバックする。
    """
    import os
    from datetime import datetime, timezone, timedelta
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    except ImportError:  # pragma: no cover - Python 3.9+ 想定
        ZoneInfo = None  # type: ignore[assignment]
        ZoneInfoNotFoundError = Exception  # type: ignore[assignment,misc]

    tz_name = (tz or os.environ.get("HVE_RUN_ID_TZ", "")).strip() or "Asia/Tokyo"
    tzobj = None
    if ZoneInfo is not None:
        for candidate in (tz_name, "Asia/Tokyo"):
            try:
                tzobj = ZoneInfo(candidate)
                break
            except (ZoneInfoNotFoundError, ValueError, OSError):
                continue
    if tzobj is None and tz_name == "Asia/Tokyo":
        # Windows で tzdata 未導入時の JST 既定フォールバック (UTC+9 固定)。
        tzobj = timezone(timedelta(hours=9))
    if tzobj is not None:
        ts = datetime.now(tzobj).strftime("%Y%m%dT%H%M%S")
    else:
        ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    short_uuid = uuid.uuid4().hex[:6]
    return f"{ts}-{short_uuid}"


def _env_bool(name: str, default: bool = False) -> bool:
    """環境変数を bool として読む。

    - 未設定（None）の場合は default を返す。
    - "true"・"1"・"yes" (大小文字不問) → True。
    - それ以外（"false"・"0"・"no"・空文字・その他の値） → False。
    - 例: "maybe" や "2" などの未知値も False として扱う。
    """
    import os
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes")


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """bool / 文字列を bool に正規化する。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in ("true", "1", "yes", "on"):
            return True
        if raw in ("false", "0", "no", "off", ""):
            return False
    return bool(value)


def _parse_bool_mapping(value: Any) -> Dict[str, bool]:
    """JSON 文字列または dict を ``{str: bool}`` に正規化する。

    Cloud Session の Step / subtask override 用。無効値は安全側で除外する。
    """
    if value is None or value == "":
        return {}
    parsed: Any = value
    if isinstance(value, str):
        try:
            import json as _json
            parsed = _json.loads(value)
        except (TypeError, ValueError):
            return {}
    if not isinstance(parsed, dict):
        return {}
    result: Dict[str, bool] = {}
    for key, raw_value in parsed.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        if isinstance(raw_value, bool):
            result[key_text] = raw_value
        elif isinstance(raw_value, str):
            lowered = raw_value.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                result[key_text] = True
            elif lowered in ("false", "0", "no", "off"):
                result[key_text] = False
    return result


def _parse_knowledge_sources(value: str) -> List[str]:
    """FR-KD-01: ``HVE_KNOWLEDGE_SOURCES`` を知識源名へ分解する（不正トークンと空トークンは無視）。"""
    try:
        from .knowledge_discovery import parse_source_names
    except ImportError:  # pragma: no cover - flat import compatibility
        from knowledge_discovery import parse_source_names  # type: ignore[no-redef]
    return parse_source_names([value or ""], strict=False)


def _workiq_enabled_from_env(value: Optional[str]) -> bool:
    """FR-KD-11: ``WORKIQ_ENABLED`` が ``false`` / ``0`` / ``no`` のときだけ無効（未設定は有効）。"""
    return (value or "").strip().lower() not in ("false", "0", "no")


DEFAULT_IGNORE_PATHS: Tuple[str, ...] = ("docs", "images", "qa", "src", "work")


@dataclass
class SDKConfig:
    """HVE の SDK セッション設定。

    ``mcp_servers`` は旧呼び出しとのコンストラクタ互換のためだけに受理し、
    runtime state には保持しない。MCP の公開範囲は SDK resource snapshot と
    Tool Search policy から解決する。
    """

    # --- 基本設定 ---
    model: str = DEFAULT_MODEL              # デフォルトモデル
    review_model: Optional[str] = None      # レビュー専用モデル（未指定時は model）
    qa_model: Optional[str] = None          # QA 専用モデル（未指定時は model）
    # QA 起点 AKM 子実行専用モデル（FR-QA-04。未指定時は model）。
    # 適用されるのは qa_akm_dispatch の子プロセス引数生成だけで、
    # メイン / review / QA のセッション生成には影響しない。
    akm_model: Optional[str] = None
    # --- reasoning_effort (SDK が返す supported_reasoning_efforts から選択された値) ---
    # None: 未指定。Auto モデル時は何も指定せず、サーバ側 Auto Model Selection が
    # モデル毎に適切な effort を選ぶ。明示モデル時も None は SDK 既定振る舞いを使う。
    reasoning_effort: Optional[str] = None
    review_reasoning_effort: Optional[str] = None
    qa_reasoning_effort: Optional[str] = None
    akm_reasoning_effort: Optional[str] = None
    # --- context_tier (SDK の create_session(context_tier=...) へ渡す) ---
    # "default" | "long_context" | None。None は未指定（SDK/サーバ既定）。
    # GUI 設定の既定値 (long_context) は GUI 層 (settings_store / OrchestrateArgs) が
    # 担い、本フィールドの既定は None として CLI 直接実行時の従来振る舞いを保つ。
    context_tier: Optional[str] = None
    akm_context_tier: Optional[str] = None
    timeout_seconds: float = 21600.0        # セッションの idle タイムアウト
    # per-step wall-clock タイムアウト（秒）。DAG の 1 ステップ実行が本値を超えたら
    # 当該ステップを失敗扱いで打ち切り、ハングによる DAG 全体の無期限停止を防ぐ。
    # idle タイムアウト(timeout_seconds)とは別物。None または <=0 で無効化。
    step_timeout_seconds: Optional[float] = 7200.0  # 既定 2h
    base_branch: str = "main"               # ベースブランチ
    cli_path: Optional[str] = None          # Copilot CLI のパス (COPILOT_CLI_PATH)
    cli_url: Optional[str] = None           # 外部 CLI サーバー URL (例: localhost:4321)
    github_token: str = ""                  # GH_TOKEN / GITHUB_TOKEN
    repo: str = ""                          # owner/repo 形式

    # --- 並列実行 ---
    max_parallel: int = 15                  # 並列上限 (デフォルト: 15)

    # --- Post-step 自動プロンプト ---
    auto_qa: bool = False                   # QA 自動投入（デフォルト: 無効）
    # QA 回答を knowledge/ へバックグラウンドでマージするか（FR-QA-05、既定: 無効）。
    qa_akm_background_merge: bool = False
    auto_contents_review: bool = False      # Review 自動投入（デフォルト: 無効）
    qa_answer_mode: Optional[str] = None    # QA 回答モード: "all" = 全問まとめて, "one" = 1問ずつ, "autopilot" = 全問既定値自動採用（GUI）, "gui-file" = GUI 経由 IPC ファイル, None = 実行時に選択
    qa_auto_defaults: bool = False          # True: QA Phase 2b で全問デフォルト値を自動採用（設定元: __main__.py wizard / 消費先: runner.py _collect_qa_answers）
    qa_ipc_dir: Optional[str] = None        # qa_answer_mode="gui-file" 時の IPC ディレクトリパス（GUI ↔ CLI ファイルベース通信）
    steering_ipc_dir: Optional[str] = None  # Steering（実行中ワークフローへの割り込み送信）用 IPC ディレクトリパス（GUI ↔ CLI ファイルベース通信）

    force_interactive: bool = False         # True のとき sys.stdin.isatty() 判定をバイパスしてインタラクティブモードを強制する（--force-interactive）
    qa_input_timeout_seconds: float = 300.0  # QA 回答入力専用タイムアウト秒数（デフォルト: 300 秒）
    qa_gui_input_timeout_seconds: float = 3600.0  # GUI 経由 QA 回答待ちタイムアウト秒数（デフォルト: 3600 秒 = 1 時間）

    # --- Code Review Agent ---
    auto_coding_agent_review: bool = False              # Code Review Agent 呼び出し（デフォルト: 無効）
    auto_coding_agent_review_auto_approval: bool = False  # 自動承認（デフォルト: 無効）
    review_timeout_seconds: float = 7200.0              # Code Review Agent レビュー待ちタイムアウト（セッション idle タイムアウトとは別設定）
    review_base_ref: str = "HEAD~1"                     # git diff の基点 (例: "HEAD~1", "main", "origin/main")

    # --- Issue/PR 作成 ---
    create_issues: bool = False             # デフォルト: 作成しない
    assign_copilot_agent: bool = False      # 新規 Root Issue の Copilot cloud agent 割当
    create_pr: bool = False                 # デフォルト: 作成しない
    # FR-CLI-83: workflow-wide PR 用の作業branchを新規作成するか。
    # False は安全なcurrent branchを使う。起動前検査はstartup_preflightが担う。
    create_working_branch: bool = True
    # FR-GUI-25: 既存 Issue を Root Issue として使う場合の Issue 番号。
    # None のときは従来どおり Root Issue を新規作成する。create_issues または create_pr と併用したときだけ効力を持つ。
    issue_number: Optional[int] = None
    # PR 自動 Approve & Auto-merge。単独で branch 作成を有効にするのは
    # ASDW-WEB（Step 単位）と ADFDV（workflow 単位）のみ。他 workflow で
    # branch を作るには create_issues/create_pr の明示指定が必要で、この設定は
    # その結果作成される PR の自動マージにだけ使用する。
    # GUI/CLI から --enable-auto-merge として渡される。
    enable_auto_merge: bool = False
    # FR-CLI-34: enable_auto_merge による auto-approve-and-merge 完了（PR が merged）を
    # ポーリング検知後、今回作成した作業ブランチをローカルのみ削除する（既定: 有効）。
    # GUI/CLI から --no-delete-local-merged-branch で無効化。enable_auto_merge 無効時は作動しない。
    delete_local_merged_branch: bool = True
    ignore_paths: List[str] = field(default_factory=lambda: list(DEFAULT_IGNORE_PATHS))
    # qa/ は PR commit 対象外（ignore_paths に含まれる）。
    # 例外: ADI Step 1.1 / 1.2 の原本質問票は main 成果物のため、
    #   orchestrator.py が安全な明示パスだけを commit 対象へ追加する。
    #   → runner.py は qa/ に質問票・QA マージファイルを保存するが、
    #     それらは hve ローカル実行時の作業ファイルであり、通常は commit しない。
    # Skill work-artifacts-layout §4.1 の delete→create ルールは Git 上の成果物更新フローを指す。
    # runner.py の qa/ ファイル書き込みは QAMerger.save_merged() を使用し、
    #   - 実行時ファイル: run_id + step_id を含むユニークパスに保存（通常は衝突しない）
    #   - 同一 run_id/step_id での再実行時: 一時ファイル書き込み → read-back 検証 → os.replace() による
    #     アトミック rename（既存ファイルの原子的上書き）で保存する。

    # --- Console 出力 ---
    verbose: bool = True                    # レガシー互換。出力レベルは verbosity が主制御
    quiet: bool = False                     # レガシー互換。出力レベルは verbosity が主制御
    show_stream: bool = False               # トークンストリーム表示（デフォルト: 無効）
    show_reasoning: bool = True             # 推論（Thinking）表示（デフォルト: 有効）
    log_level: str = "error"                # CLI ログレベル (none/error/warning/info/debug/all)
    verbosity: int = 1                      # Console verbosity: 0=quiet, 1=compact, 2=normal, 3=verbose
    no_color: Optional[bool] = None         # F1: ANSI カラー出力を無効化（None=NO_COLOR 環境変数を参照）
    show_banner: Optional[bool] = None      # F2: バナー表示制御（None=既存の自動判定, True=表示, False=抑止）
    screen_reader: bool = False             # F3: スクリーンリーダーモード（絵文字→日本語ラベル置換、スピナー無効化）
    timestamp_style: str = "prefix"        # F4: タイムスタンプ表示位置: prefix/suffix/off
    final_only: bool = False                # F5: 最終出力のみ表示（DAG サマリ＋各 step の final_message）

    # --- Workbench UI（Phase 5）---
    no_workbench: bool = False              # True: Workbench UI を無効化（--workbench off 相当）
    workbench_body_lines: int = 10          # Body コンテンツ行数（10〜20 にクランプ）
    workbench_history: int = 10000          # 履歴バッファ容量
    workbench_flush_on_exit: bool = True    # 終了時に履歴を stdout フラッシュ

    # --- SDK ---
    cli_args: List[str] = field(default_factory=list)
    # SubprocessConfig.cli_args に渡す追加 CLI 引数。例:
    # ["--log-dir", "/path/to/logs"]  でログファイル永続化
    # ["--some-flag"]                 で診断オプション有効化

    # --- ツール制限（GitHub Copilot SDK の available_tools / excluded_tools へ伝搬）---
    # SDK 0.1.0 のシグネチャ:
    #   create_session(..., available_tools: list[str] | None = None,
    #                       excluded_tools: list[str] | None = None, ...)
    # available_tools: 指定したツール名のみを許可（None = 全許可）
    # excluded_tools:  指定したツール名を除外（available_tools 適用後に評価される想定）
    # サブセッション (Pre-QA / Review) にも同じ値を伝搬する。
    #
    # Phase 8 S-3 所見: 旧 `.github/agents/*.agent.md` の `tools:` frontmatter は
    # 「カテゴリ名」(edit/execute/read/search/todo/web) を採用しており、SDK の
    # 実ツール名 (str_replace_editor / bash / glob / web_search 等) と一致しない。
    # そのため「グローバルにデフォルト値を固定」すると SDK ツールを
    # 完全ブロックしてしまうリスクがあるため、デフォルトは None のまま保持し、
    # audit 記録は `DEFAULT_AVAILABLE_TOOL_CATEGORIES` 定数にドキュメントとして残す。
    # SDK 側でカテゴリ名 ↔ 実ツール名のマッピングが今後提供された場合に初めて
    # ポーティングを検討する。
    available_tools: Optional[List[str]] = None
    excluded_tools: Optional[List[str]] = None

    # --- Auto Compaction ---
    # True 時: サブステップ実行の create_session に infinite_sessions={"enabled": True}
    # を渡し、SDK 側の自動コンテキスト圧縮（compaction）を有効化する。既定 OFF。
    auto_compaction: bool = False

    # --- Tool Search (FR-MODEL-04) ---
    # True 時: create_session に tool_search={"enabled": True} を渡し、SDK 側の
    # ツール定義遅延ロードを有効化する。既定 ON。
    # FR-MODEL-06: `--no-tool-search` / `HVE_TOOL_SEARCH` の falsy 値による明示的な
    # 無効化は既定 ON で上書きしない。
    # 注: AAGD ワークフローの `enable_tool_search`（生成する AI Agent の
    # Foundry Toolbox 設定）とは別ドメイン。本フィールドは HVE 自身の
    # Copilot SDK セッションにだけ作用する。
    tool_search: bool = True

    # --- Tool Search のランキング実装 (FR-TS-01) ---
    # "sdk": SDK 組み込みのランキングをそのまま使う（既定）
    # "hve": `tool_search_tool` を HVE 実装（hve/toolsearch/）へ差し替える。
    #        日本語対応 BM25 / pin ポリシー / Skill のカタログ合流が有効になる。
    # 上の `tool_search` とは直交する。`tool_search` が False のとき SDK は
    # `tool_search_tool` を呼ばないため、差し替えても何も起きない。
    tool_search_ranking: str = "sdk"

    # --- Tool Search の遅延ロード閾値 (FR-MODEL-04) ---
    # 正の整数を指定した場合だけ create_session の tool_search dict へ
    # `defer_threshold` として渡す。None（既定）ではキー自体を送らず SDK 既定へ委譲する。
    # 0 以下・非整数は「未指定」と同じ扱いにして SDK 既定へ委譲する（fail-open）。
    # `tool_search` が False のときは tool_search dict 自体を送らないため作用しない。
    tool_search_defer_threshold: Optional[int] = None

    # --- Fleet mode (GitHub Copilot SDK 1.0.0+) ---
    # True 時: 複数 Step の DAG wave を Copilot SDK Fleet mode に委譲する。
    # 既定 OFF。subissues.md ではなく workflow-level fan-out / DAG wave が対象。
    fleet_mode_enabled: bool = False

    # --- Cloud Sessions (GitHub Copilot SDK 1.0.0+) ---
    cloud_session_enabled: bool = False
    cloud_session_repository_owner: Optional[str] = None
    cloud_session_repository_name: Optional[str] = None
    cloud_session_repository_branch: Optional[str] = None
    cloud_session_max_concurrency: int = 5
    cloud_session_integration_id: Optional[str] = None
    cloud_session_mc_base_url: Optional[str] = None
    cloud_session_step_overrides: Dict[str, bool] = field(default_factory=dict)
    cloud_session_subtask_overrides: Dict[str, bool] = field(default_factory=dict)
    cloud_session_runtime_step_overrides: Dict[str, bool] = field(default_factory=dict)
    # 実行中の DAG wave ごとに自動算出される local/cloud ルーティング。
    # CLI/GUI 永続設定ではなく、Cloud Session 自動振り分けの runtime 状態。

    # --- Legacy MCP session config (compat input only; no runtime field) ---
    mcp_servers: InitVar[Optional[Dict[str, Any]]] = None

    # --- 追加プロンプト ---
    # Phase 2 で SDK へ `custom_agents` キーを渡さなくなったため、本フィールドは
    # 現状 no-op（caller が設定しても何も作用しない）。Phase 8 S-2 では
    # `custom_agents_config` 上位フィールドを撤去したが、`additional_prompt` は
    # 他途用との区別が付けるまでフィールドを残す。次回の清掎候補。
    additional_prompt: Optional[str] = None  # 全 Custom Agent の prompt 末尾に追記する文字列

    # --- 知識源（FR-KD-01）---
    workiq_enabled: bool = False                          # `workiq` を知識源へ加える（--workiq / WORKIQ_ENABLED）
    knowledge_sources: List[str] = field(default_factory=list)  # 知識源の MCP server 名（--knowledge-source / HVE_KNOWLEDGE_SOURCES）

    # 注: 旧 post-QA モードは廃止済み。事前 QA のみが提供される。

    tdd_max_retries: int = 5                    # TDD GREEN フェーズの最大リトライ回数。HVE_TDD_MAX_RETRIES 環境変数で上書き可能

    # --- Pricing / Cost 表示 ---
    pricing_usd_jpy_rate: float = 150.0        # USD → JPY 換算レート（固定値）。HVE_USD_JPY_RATE で上書き可能
    pricing_currency: str = "auto"             # "auto" (locale=ja → both, それ以外 → usd) / "usd" / "jpy" / "both"
    pricing_auto_refresh: bool = True          # 月初判定で価格表を自動再取得する。HVE_PRICING_AUTO_REFRESH で上書き可能
    pricing_statusline_enabled: bool = True    # HVE_PRICING_STATUSLINE_ENABLED / HVE_NO_STATUSLINE=1 で上書き可。※本フラグを読む実装は現在なく（hve/statusline.py は未配線）、CLI オプションも存在しない
    pricing_plan_id: str = ""                  # 料金計算で使う plan_id (空=自動推定)。HVE_PRICING_PLAN_ID で上書き可能

    # --- 実行 ID ---
    run_id: str = ""                        # ワークフロー実行ごとのユニークID（空の場合は run_workflow() で自動生成）
    session_id_prefix: str = ""             # SDK session_id の prefix。固定値を強制したい場合のみ非空にする。
    # 空文字（デフォルト）: hve.run_state.DEFAULT_SESSION_ID_PREFIX ("hve") を使用する。
    # make_session_id() に渡され、`{prefix}-{run_id}-step-{step_id}` 形式の
    # 決定論的 session_id を生成する基底となる。HVE_SESSION_ID_PREFIX 環境変数で上書き可能。

    # --- Fork-on-Retry (T2.7) ---
    fork_on_retry: bool = False
    """失敗ステップを 1 回だけフォーク (新 session_id) で自動リトライするかどうか。
    既定: False（旧挙動と完全一致）。HVE_FORK_ON_RETRY 環境変数で上書き可能。
    フォーク発火時は KPI ログ (`work/run/<run-id>/kpi/fork-kpi.jsonl`) を出力する。
    """

    # --- その他 ---
    max_diff_chars: int = 80_000            # git diff の最大文字数（トークン上限対策）。HVE_MAX_DIFF_CHARS 環境変数で上書き可能
    context_injection_max_chars: int = DEFAULT_CONTEXT_INJECTION_MAX_CHARS  # 各フェーズで注入するコンテキストの最大文字数。HVE_CONTEXT_INJECTION_MAX_CHARS で上書き可能

    # --- コンテキスト最適化 ---
    reuse_context_filtering: Optional[bool] = True    # True: ステップ依存関係ベースの reuse_context フィルタリング（HVE_REUSE_CONTEXT_FILTERING）
    # デフォルト true（consumed_artifacts アノテーション済みのステップのみフィルタリング）。
    # consumed_artifacts=None のステップは後方互換で全成果物を渡す。false にすると全ステップに全成果物を渡す（旧挙動）。

    # --- セキュリティ ---
    model_override: Optional[str] = None    # 緊急回避用モデル上書き。設定時は Issue Template の選択より優先される。HVE_MODEL_OVERRIDE 環境変数で設定

    # --- mdq リアルタイム索引更新（HVE CLI Orchestrator 限定） ---
    mdq_watch: bool = True
    """``True`` で run_workflow 起動時に mdq.watcher を起動し、Markdown
    ファイルの追加/更新/削除を ``.mdq/index.sqlite`` へ逐次反映する。

    - 既定 ON。watchdog 未導入時は自動で無効化（警告ログのみ）。
    - ``--no-mdq-watch`` / 環境変数 ``HVE_MDQ_WATCH=0`` で OFF。
    - Cloud Agent / GitHub Actions では使用しない（本機能は CLI 専用）。
    - 既存の ``python -m mdq index`` による手動索引更新は維持される。
    """
    mdq_watch_debounce_ms: int = 500
    """watcher のデバウンス間隔（ms）。既定 500ms。"""

    # --- cq リアルタイム索引更新（HVE CLI Orchestrator 限定） ---
    cq_watch: bool = True
    """``True`` で run_workflow 起動時に cq.watcher を起動し、ソース
    ファイルの追加/更新/削除を ``.cq/index-<profile>.sqlite`` へ逐次反映する。

    - 監視対象は cq 設定ファイルで最初に宣言された profile。
    - 既定 ON。watchdog 未導入時や cq 設定不在時は自動で無効化（警告のみ）。
    - ``--no-cq-watch`` / 環境変数 ``HVE_CQ_WATCH=0`` で OFF。
    - Cloud Agent / GitHub Actions では使用しない（本機能は CLI 専用）。
    """
    cq_watch_debounce_ms: int = _CQ_DEFAULT_DEBOUNCE_MS
    """watcher のデバウンス間隔（ms）。既定値は ``cq.watcher`` が SoT。"""
    # ※ プロンプトサニタイズの有効/無効は HVE_PROMPT_SANITIZATION 環境変数で直接制御する（security.is_sanitization_enabled() 参照）

    # --- メイン成果物改善制御 ---
    apply_qa_improvements_to_main: bool = False   # QA 結果をメイン成果物へ反映（デフォルト: 無効）
    apply_review_improvements_to_main: bool = True  # レビュー指摘をメイン成果物へ反映（デフォルト: 有効）

    # --- 前提成果物チェック（Phase 8） ---
    require_input_artifacts: bool = False
    # False (デフォルト): 不足 artifact を warning として出力して続行する。
    # True (strict mode): 不足 artifact がある場合に実行を中断する。
    # 設定方法: HVE_REQUIRE_INPUT_ARTIFACTS 環境変数（"true"/"1"/"yes"）。
    # consumed_artifacts=None のステップは後方互換としてチェック対象外。
    # consumed_artifacts=[] のステップは前提成果物なしとして扱い、不足なし。

    # --- 全自動モード ---
    unattended: bool = False                # True の場合、実行中のインタラクティブ入力を全てスキップ
    # FR-PROMPT-13: Prompt 版 execution_policy で宣言された事前承認の範囲。
    pre_approved_operations: Tuple[str, ...] = ()
    allow_public_exposure: bool = False
    budget_note: str = ""

    # --- その他 ---
    dry_run: bool = False                   # ドライラン

    # --- Agentic Retrieval（Phase 2）---
    # AAD-WEB / ASDW-WEB 向け Agentic Retrieval 設定
    enable_agentic_retrieval: str = "auto"
    # "auto": Arch-AgenticRetrieval-Detail Custom Agent の自動判定に従う（既定）
    # "yes" : Agentic Retrieval を使用する
    # "no"  : Agentic Retrieval を使用しない（関連ステップを生成しない）
    agentic_data_source_modes: List[str] = field(default_factory=lambda: ["indexer"])
    # データソース投入方式。"indexer" / "push" の組み合わせ。既定: ["indexer"]
    foundry_mcp_integration: bool = True
    # Microsoft Foundry 連携（Remote MCP Server）。True = する（既定）
    agentic_data_sources_hint: str = ""
    # 想定データソースのヒント（任意・自由記述）
    agentic_existing_design_diff_only: bool = False
    # True: 既存設計を上書きせず差分更新する
    foundry_sku_fallback_policy: str = "standard_allowed"
    # "standard_allowed" : Standard SKU へのフォールバックを許容（既定）
    # "global_required"  : Global Standard 必須（Standard 拒否）

    # --- Foundry Toolbox / tool search ---
    enable_tool_search: str = "auto"
    # "auto": Tool 総数が 15 を超えたら有効化する（既定。Learn / ブログが示す 10〜15 の閾値）
    # "yes" : Tool 数に関係なく Toolbox と tool search を使う
    # "no"  : tool search を使わない（全 Tool を毎ターン渡す）

    def __post_init__(self, mcp_servers: Optional[Dict[str, Any]]) -> None:
        """値を正規化し、legacy ``mcp_servers`` を意図的に破棄する。

        exact MCP 要件は resource routing の ``required_mcp_servers`` または
        ``required_skills`` へ渡す。raw MCP config を session state へ複製しない
        FR-TS-13 の境界を維持するため、この互換入力の値は使用しない。
        """
        # FR-TS-13: legacy constructor input is accepted for source compatibility
        # only.  Raw MCP configuration must not survive as runtime session state.
        del mcp_servers
        # SDKConfig は from_env() 以外（直接コンストラクタ呼び出し）でも利用されるため、
        # 空文字モデルはここでも DEFAULT_MODEL に寄せて挙動を統一する（FR-MODEL-01）。
        if not self.model:
            self.model = DEFAULT_MODEL
        # "Auto" は GitHub 側の Auto Model Selection に委譲するため固定モデルへ解決しない。
        # 正規化後に空文字になった場合も DEFAULT_MODEL へ固定せず Auto にフォールバックする。
        if self.model != MODEL_AUTO_VALUE:
            self.model = _normalize_model_with_warning(self.model) or MODEL_AUTO_VALUE
        if self.review_model != MODEL_AUTO_VALUE:
            self.review_model = _normalize_model_with_warning(self.review_model)
        if self.qa_model != MODEL_AUTO_VALUE:
            self.qa_model = _normalize_model_with_warning(self.qa_model)
        if self.akm_model != MODEL_AUTO_VALUE:
            self.akm_model = _normalize_model_with_warning(self.akm_model)
        # model_override が設定されている場合、model フィールドを上書きする。
        # Issue Template の選択（AUTO 含む）よりも優先される緊急回避手段。
        if self.model_override:
            normalized = _normalize_model_with_warning(self.model_override) or None
            self.model_override = normalized  # 正規化後の値を self.model_override にも反映
            if normalized:
                self.model = normalized
        if self.reuse_context_filtering is None:
            self.reuse_context_filtering = True
        if not isinstance(self.context_injection_max_chars, int) or self.context_injection_max_chars <= 0:
            self.context_injection_max_chars = DEFAULT_CONTEXT_INJECTION_MAX_CHARS
        self.cloud_session_enabled = _coerce_bool(self.cloud_session_enabled, default=False)
        for _attr in (
            "cloud_session_repository_owner",
            "cloud_session_repository_name",
            "cloud_session_repository_branch",
            "cloud_session_integration_id",
            "cloud_session_mc_base_url",
        ):
            _value = getattr(self, _attr)
            if isinstance(_value, str):
                _value = _value.strip() or None
                setattr(self, _attr, _value)
        try:
            self.cloud_session_max_concurrency = int(self.cloud_session_max_concurrency)
        except (TypeError, ValueError):
            self.cloud_session_max_concurrency = 5
        if self.cloud_session_max_concurrency < 1:
            self.cloud_session_max_concurrency = 1
        # per-step wall-clock タイムアウトの正規化: <=0 / 不正値は無効(None)扱い
        if self.step_timeout_seconds is not None:
            try:
                self.step_timeout_seconds = float(self.step_timeout_seconds)
            except (TypeError, ValueError):
                self.step_timeout_seconds = None
            else:
                if self.step_timeout_seconds <= 0:
                    self.step_timeout_seconds = None
        self.fleet_mode_enabled = _coerce_bool(self.fleet_mode_enabled, default=False)
        self.cloud_session_step_overrides = _parse_bool_mapping(self.cloud_session_step_overrides)
        self.cloud_session_subtask_overrides = _parse_bool_mapping(self.cloud_session_subtask_overrides)
        self.cloud_session_runtime_step_overrides = _parse_bool_mapping(self.cloud_session_runtime_step_overrides)

    def effective_knowledge_sources(self, *extra: str) -> List[str]:
        """FR-KD-01: 実効知識源を ``workiq``（有効時）→ ``knowledge_sources`` → ``extra`` の順で返す。

        完全一致の重複は最初の 1 件だけ残し、名前規則に合わない値は除外する。
        """
        try:
            from .knowledge_discovery import merge_source_names
        except ImportError:  # pragma: no cover - flat import compatibility
            from knowledge_discovery import merge_source_names  # type: ignore[no-redef]
        return merge_source_names(
            ["workiq"] if self.workiq_enabled else [],
            list(self.knowledge_sources or []),
            list(extra),
        )

    def tool_search_session_option(self) -> Optional[Dict[str, Any]]:
        """FR-MODEL-04: ``create_session`` へ渡す ``tool_search`` dict を組み立てる。

        すべてのローカルセッション（メイン / サブ / ARD 補助 /
        Fleet 親 / Code Review）が本メソッドを唯一の組み立て口として使い、
        同一の値が伝搬することを保証する。

        戻り値:
            - ``tool_search`` が False のとき ``None``（呼び出し側はキーを送らない）
            - 有効かつ閾値未指定のとき ``{"enabled": True}``
            - 有効かつ正の整数閾値のとき ``{"enabled": True, "defer_threshold": N}``
        """
        if not self.tool_search:
            return None
        option: Dict[str, Any] = {"enabled": True}
        threshold = self.tool_search_defer_threshold
        if isinstance(threshold, int) and not isinstance(threshold, bool) and threshold > 0:
            option["defer_threshold"] = threshold
        return option

    @classmethod
    def from_env(cls) -> "SDKConfig":
        """環境変数から SDKConfig を構築する。"""
        import os
        raw_model = os.environ.get("MODEL")
        if raw_model is None or raw_model.strip() == "":
            env_model = DEFAULT_MODEL
        else:
            env_model = _normalize_model_with_warning(raw_model) or MODEL_AUTO_VALUE
        # 旧 post-QA 用環境変数は廃止済み。

        try:
            env_max_diff_chars = int(os.environ.get("HVE_MAX_DIFF_CHARS", "80000"))
        except (TypeError, ValueError):
            env_max_diff_chars = 80_000
        try:
            env_context_injection_max_chars = int(
                os.environ.get("HVE_CONTEXT_INJECTION_MAX_CHARS", str(DEFAULT_CONTEXT_INJECTION_MAX_CHARS))
            )
        except (TypeError, ValueError):
            env_context_injection_max_chars = DEFAULT_CONTEXT_INJECTION_MAX_CHARS
        try:
            env_cloud_session_max_concurrency = int(
                os.environ.get("HVE_CLOUD_SESSION_MAX_CONCURRENCY", "5") or "5"
            )
        except (TypeError, ValueError):
            env_cloud_session_max_concurrency = 5

        def _parse_tool_list(value: str) -> Optional[List[str]]:
            """HVE_AVAILABLE_TOOLS / HVE_EXCLUDED_TOOLS をパースしてリスト化する。

            空 / 未設定時は None を返す（= SDK デフォルト = 制限なし）。
            区切り文字: カンマ または 空白。
            """
            if not value or not value.strip():
                return None
            import re as _re
            tokens = [t for t in _re.split(r"[,\s]+", value.strip()) if t]
            return tokens or None

        def _parse_defer_threshold(value: str) -> Optional[int]:
            """HVE_TOOL_SEARCH_DEFER_THRESHOLD をパースする（FR-MODEL-04）。

            正の整数だけを採用し、未設定 / 非整数 / 0 以下はすべて None を返して
            SDK 既定へ委譲する（キー自体を create_session へ送らない）。
            """
            text = (value or "").strip()
            if not text:
                return None
            try:
                parsed = int(text)
            except ValueError:
                return None
            return parsed if parsed > 0 else None

        def _env_bool_or_none(name: str) -> Optional[bool]:
            raw = os.environ.get(name)
            if raw is None or raw.strip() == "":
                return None
            return raw.strip().lower() in ("true", "1", "yes")

        return cls(
            model=env_model,
            github_token=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "",
            repo=os.environ.get("REPO", ""),
            cli_path=os.environ.get("COPILOT_CLI_PATH"),
            review_model=_normalize_model_with_warning(os.environ.get("REVIEW_MODEL") or None),
            qa_model=_normalize_model_with_warning(os.environ.get("QA_MODEL") or None),
            show_reasoning=os.environ.get("SHOW_REASONING", "true").lower() in ("true", "1", "yes"),
            workiq_enabled=_workiq_enabled_from_env(os.environ.get("WORKIQ_ENABLED")),
            knowledge_sources=_parse_knowledge_sources(os.environ.get("HVE_KNOWLEDGE_SOURCES", "")),
            tdd_max_retries=int(os.environ.get("HVE_TDD_MAX_RETRIES", "5")),
            max_diff_chars=env_max_diff_chars,
            context_injection_max_chars=env_context_injection_max_chars,
            available_tools=_parse_tool_list(os.environ.get("HVE_AVAILABLE_TOOLS", "")),
            excluded_tools=_parse_tool_list(os.environ.get("HVE_EXCLUDED_TOOLS", "")),
            tool_search=_env_bool("HVE_TOOL_SEARCH", default=True),
            tool_search_ranking=(
                os.environ.get("HVE_TOOL_SEARCH_RANKING", "").strip().lower() or "sdk"
            ),
            tool_search_defer_threshold=_parse_defer_threshold(
                os.environ.get("HVE_TOOL_SEARCH_DEFER_THRESHOLD", "")
            ),
            reuse_context_filtering=_env_bool("HVE_REUSE_CONTEXT_FILTERING", default=True),
            model_override=_normalize_model_with_warning(os.environ.get("HVE_MODEL_OVERRIDE") or None),
            apply_qa_improvements_to_main=_env_bool("HVE_APPLY_QA_IMPROVEMENTS_TO_MAIN", default=False),
            apply_review_improvements_to_main=_env_bool("HVE_APPLY_REVIEW_IMPROVEMENTS_TO_MAIN", default=True),
            require_input_artifacts=_env_bool("HVE_REQUIRE_INPUT_ARTIFACTS", default=False),
            run_id=(os.environ.get("HVE_RUN_ID", "") or "").strip(),
            session_id_prefix=os.environ.get("HVE_SESSION_ID_PREFIX", "").strip(),
            fork_on_retry=_env_bool("HVE_FORK_ON_RETRY", default=False),
            mdq_watch=_env_bool("HVE_MDQ_WATCH", default=True),
            mdq_watch_debounce_ms=int(os.environ.get("HVE_MDQ_WATCH_DEBOUNCE_MS", "500") or "500"),
            cq_watch=_env_bool("HVE_CQ_WATCH", default=True),
            cq_watch_debounce_ms=int(
                os.environ.get("HVE_CQ_WATCH_DEBOUNCE_MS", "") or _CQ_DEFAULT_DEBOUNCE_MS
            ),
            fleet_mode_enabled=_env_bool("HVE_FLEET_MODE_ENABLED", default=False),
            pricing_usd_jpy_rate=float(os.environ.get("HVE_USD_JPY_RATE", "150.0") or "150.0"),
            pricing_currency=(os.environ.get("HVE_PRICING_CURRENCY", "auto") or "auto").strip().lower(),
            pricing_auto_refresh=_env_bool("HVE_PRICING_AUTO_REFRESH", default=True),
            pricing_statusline_enabled=(
                False
                if os.environ.get("HVE_NO_STATUSLINE", "").strip().lower() in ("1", "true", "yes")
                else _env_bool("HVE_PRICING_STATUSLINE_ENABLED", default=True)
            ),
            pricing_plan_id=(os.environ.get("HVE_PRICING_PLAN_ID", "") or "").strip(),
            cloud_session_enabled=_env_bool("HVE_CLOUD_SESSION_ENABLED", default=False),
            cloud_session_repository_owner=(os.environ.get("HVE_CLOUD_SESSION_REPOSITORY_OWNER", "") or "").strip() or None,
            cloud_session_repository_name=(os.environ.get("HVE_CLOUD_SESSION_REPOSITORY_NAME", "") or "").strip() or None,
            cloud_session_repository_branch=(os.environ.get("HVE_CLOUD_SESSION_REPOSITORY_BRANCH", "") or "").strip() or None,
            cloud_session_max_concurrency=env_cloud_session_max_concurrency,
            cloud_session_integration_id=(os.environ.get("GITHUB_COPILOT_INTEGRATION_ID", "") or "").strip() or None,
            cloud_session_mc_base_url=(os.environ.get("COPILOT_MC_BASE_URL", "") or "").strip() or None,
            cloud_session_step_overrides=_parse_bool_mapping(os.environ.get("HVE_CLOUD_SESSION_STEP_OVERRIDES", "")),
            cloud_session_subtask_overrides=_parse_bool_mapping(os.environ.get("HVE_CLOUD_SESSION_SUBTASK_OVERRIDES", "")),
        )

    def get_review_model(self) -> str:
        """レビュー用モデルを返す。

        敵対的レビュー（auto_contents_review）および
        Code Review Agent（auto_coding_agent_review）で使用する。
        """
        return self.review_model or self.model

    def get_qa_model(self) -> str:
        """QA 用モデルを返す。

        QA 質問票生成（auto_qa）で使用する。
        """
        return self.qa_model or self.model

    def get_akm_model(self) -> str:
        """QA 起点 AKM 子実行用モデルを返す（FR-QA-04）。"""
        return self.akm_model or self.model

    def resolve_token(self) -> str:
        """有効なトークンを返す。"""
        if self.github_token:
            return self.github_token
        import os
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
