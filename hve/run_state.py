"""run_state.py — Resume 機能のための Run State Manager 基盤。

Phase 1 (Resume): ワークフロー実行の進行状況を
`<session-state-dir>/runs/<run_id>/state.json` に永続化するレイヤ。
Resume は本モジュール上に Phase 2 以降で構築する。

`<session-state-dir>` は環境変数 `HVE_SESSION_STATE_DIR` で上書き可能。
既定はリポジトリルート配下の `session-state/` ディレクトリ
（CWD 非依存。詳細は `get_session_state_dir()` 参照）。

== Git 管理ポリシー ==

`session-state/` は **Git にコミットする** 運用を採用する（他デバイス間で
resume を継続できるようにするため）。`.gitignore` には追加しない。
ただし 1 ステップごとに頻繁に更新されるため、qa_merger.py と同パターン
（tempfile + os.replace によるアトミック上書き）で保存する。

並列安全性: `<session-state-dir>/runs/<run_id>/` は run_id で隔離されており
他ジョブとの衝突は発生しない。

== 公開 API ==

- StepState   : ステップ単位の実行状態 dataclass
- HostInfo    : 実行ホスト情報 dataclass（互換性検証用）
- RunState    : Run 全体の状態 dataclass（I/O メソッド付き）
- list_resumable_runs(work_dir) -> list[RunState]
- is_resumable(state) -> bool
- make_session_id(run_id, step_id, suffix="", prefix=...) -> str  (Phase 2)
- DEFAULT_SESSION_ID_PREFIX : セッション ID の既定 prefix（"hve"）
- _SAFE_CONFIG_FIELDS : SDKConfig snapshot 時のホワイトリスト
- to_safe_config_dict(config) -> dict
- default_session_name(workflow_id, params, ...) -> str         (Phase 4)
- to_local_time_str(iso_utc, fmt=...) -> str                    (Phase 4)
- get_current_sdk_version() -> str                              (Phase 4)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

SCHEMA_VERSION: str = "2.0"
"""state.json スキーマバージョン。

Resume の 2 層トランザクション保護導入により 1.0 → 2.0 へ bump。
旧 1.0 は `_from_dict` で ValueError 拒否（マイグレーション未提供）。
2.0 で追加されたフィールド:
  - RunState: `journal_path` / `intent_log` / `sdk_session_index` / `lock_holder`
  - StepState: `checkpoint_marker` / `last_journal_seq` / `sdk_session_exists`
"""

_SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"2.0"})
"""読み込み可能な schema_version 集合。旧バージョンは拒否される。"""

# ---------------------------------------------------------------------------
# Session-state ディレクトリ解決
# ---------------------------------------------------------------------------
# Resume / Session 関連ファイル（state.json / journal.jsonl / .lock /
# journal-archive）の保存先ルート。
#
# 解決優先順位:
#   1. 環境変数 HVE_SESSION_STATE_DIR が空でなければそれを使用
#   2. それ以外は <repo-root>/session-state/  (リポジトリルート基準で決定論的)
#
# 「リポジトリルート」は本ファイル (`hve/run_state.py`) の親ディレクトリの
# 親、すなわち hve パッケージを含むディレクトリと定義する。CWD には依存しない。
# これにより `hve/` から起動しても `<repo-root>/` から起動しても同じ場所に
# 出力される（旧実装の CWD 相対 `work/runs/` による二重出力問題を解消）。

HVE_SESSION_STATE_DIR_ENV: str = "HVE_SESSION_STATE_DIR"
DEFAULT_SESSION_STATE_DIRNAME: str = "session-state"


def _resolve_repo_root() -> Path:
    """`hve/` パッケージを含むディレクトリ（= リポジトリルート）を返す。"""
    return Path(__file__).resolve().parent.parent


def get_session_state_dir() -> Path:
    """Session-state ディレクトリのルートパスを返す（環境変数 > 既定）。"""
    env = os.environ.get(HVE_SESSION_STATE_DIR_ENV, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return _resolve_repo_root() / DEFAULT_SESSION_STATE_DIRNAME


def get_default_runs_dir() -> Path:
    """Run ごとの state.json / journal.jsonl / .lock を格納するディレクトリ。"""
    return get_session_state_dir() / "runs"


def get_default_archive_dir() -> Path:
    """Recovery 完了済み journal の archive ディレクトリ。"""
    return get_session_state_dir() / "journal-archive"


DEFAULT_RUNS_DIR: Path = get_default_runs_dir()
"""モジュール import 時点での既定 runs ディレクトリ。

ランタイムで環境変数を変更したい場合は `get_default_runs_dir()` を直接
呼び出すこと。テストで mock.patch する場合は本シンボルを差し替える。
"""

STATE_FILENAME: str = "state.json"

# RunState.status / StepState.status の許可値（Literal の代わりに集合で検証）
_RUN_STATUSES: tuple[str, ...] = (
    "pending", "running", "paused", "completed", "failed",
)
_STEP_STATUSES: tuple[str, ...] = (
    "pending", "running", "completed", "failed", "skipped", "blocked",
)
_RESUMABLE_RUN_STATUSES: frozenset[str] = frozenset({"paused", "running", "failed"})

# error_summary の最大保存文字数（無制限な失敗メッセージで state.json が肥大化しないよう制限）
_ERROR_SUMMARY_MAX: int = 500


# ---------------------------------------------------------------------------
# SDKConfig snapshot のホワイトリスト
# ---------------------------------------------------------------------------
# 「拒否リスト」方式は SDK 進化で漏れが出るリスクがあるため、
# 明示的に許可したフィールドのみを snapshot に含める（ホワイトリスト方式）。
#
# 明示的に除外しているフィールド:
#   - github_token : 機密
#   - repo         : 環境変数 REPO から再取得（テナント情報の混入防止）
#   - cli_path     : 環境固有
#   - cli_url      : 環境固有
#   - mcp_servers  : API キーや絶対パスを含む可能性が高い
_SAFE_CONFIG_FIELDS: frozenset[str] = frozenset({
    # 基本
    "model", "review_model", "qa_model",
    "timeout_seconds", "base_branch",
    # 並列
    "max_parallel",
    # QA / Review
    "auto_qa", "qa_answer_mode", "qa_auto_defaults",
    "auto_contents_review", "auto_coding_agent_review",
    "auto_coding_agent_review_auto_approval",
    "review_timeout_seconds", "review_base_ref",
    # Issue/PR
    "create_issues", "create_pr",
    # Console
    "verbose", "quiet", "show_stream", "show_reasoning",
    "log_level", "verbosity",
    "no_color", "show_banner", "screen_reader",
    "timestamp_style", "final_only",
    # Work IQ（テナント ID は含めない方針）
    "workiq_enabled", "workiq_qa_enabled", "workiq_akm_review_enabled",
    "workiq_akm_ingest_enabled", "workiq_akm_ingest_dxx",
    "workiq_draft_mode", "workiq_draft_output_dir",
    "workiq_per_question_timeout", "workiq_max_draft_questions",
    "workiq_priority_filter",
    # Self-Improve
    "auto_self_improve", "self_improve_max_iterations",
    "self_improve_quality_threshold", "self_improve_max_tokens",
    "self_improve_max_requests", "self_improve_target_scope",
    "self_improve_goal", "self_improve_skip", "self_improve_scope",
    "tdd_max_retries",
    # 追加
    "additional_prompt", "ignore_paths",
    "force_interactive", "qa_input_timeout_seconds",
    "max_diff_chars", "reuse_context_filtering",
    "apply_qa_improvements_to_main",
    "apply_review_improvements_to_main",
    "apply_self_improve_to_main",
    "require_input_artifacts",
    "unattended", "dry_run",
    # 実行 ID（snapshot 時点の run_id）
    "run_id",
    # Phase 2: Resume 時に固定 prefix を強制するため snapshot に含める
    "session_id_prefix",
    # Fork-integration (T2.7): フォーク機能フラグ
    "fork_on_retry",
    # Agentic Retrieval（Phase 2）
    "enable_agentic_retrieval",
    "agentic_data_source_modes",
    "foundry_mcp_integration",
    "agentic_data_sources_hint",
    "agentic_existing_design_diff_only",
    "foundry_sku_fallback_policy",
})


def to_safe_config_dict(config: Any) -> Dict[str, Any]:
    """SDKConfig（または dict）から `_SAFE_CONFIG_FIELDS` のフィールドのみ抽出する。

    config は dataclass / 辞書のいずれでも受け付ける。snapshot 不能な型
    （Path 等）は文字列に変換する。
    """
    if config is None:
        return {}
    if isinstance(config, dict):
        items = config.items()
    else:
        items = ((k, getattr(config, k)) for k in vars(config))
    safe: Dict[str, Any] = {}
    for key, value in items:
        if key not in _SAFE_CONFIG_FIELDS:
            continue
        safe[key] = _to_jsonable(value)
    return safe


def _to_jsonable(value: Any) -> Any:
    """JSON 直列化可能な値に正規化する（list/dict/プリミティブはそのまま）。"""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, Path):
        return str(value)
    # フォールバック: 文字列化
    return str(value)


# ---------------------------------------------------------------------------
# Host 情報
# ---------------------------------------------------------------------------

def _get_package_version(package_name: str, fallback: str = "unknown") -> str:
    """インストール済みパッケージのバージョンを取得する。失敗時は fallback。"""
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover - Python 3.8 未満は対象外
        return fallback
    try:
        return version(package_name)
    except PackageNotFoundError:
        return fallback
    except Exception:  # pragma: no cover - 想定外例外も握り潰す
        return fallback


_COPILOT_SDK_DIST_CANDIDATES: tuple[str, ...] = (
    "copilot-sdk",
    "github-copilot-sdk",
    "copilot",
)


def _get_copilot_sdk_version() -> str:
    """Copilot SDK のバージョン文字列を返す。

    PyPI 配布名の差異を吸収するため、複数の候補を順に試行する。
    いずれの候補でも取得できない場合は ``"unknown"`` を返す。
    """
    for name in _COPILOT_SDK_DIST_CANDIDATES:
        ver = _get_package_version(name, fallback="")
        if ver and ver != "unknown":
            return ver
    return "unknown"


def _hostname_hash() -> str:
    """ホスト名 + ユーザー名から固定長ハッシュを生成（PII 漏洩回避）。"""
    import getpass
    import socket
    try:
        host = socket.gethostname()
    except Exception:  # pragma: no cover
        host = "unknown-host"
    try:
        user = getpass.getuser()
    except Exception:  # pragma: no cover
        user = "unknown-user"
    digest = hashlib.sha256(f"{host}|{user}".encode("utf-8")).hexdigest()
    return digest[:16]


def _python_version() -> str:
    info = sys.version_info
    return f"{info.major}.{info.minor}.{info.micro}"


def _utc_now_iso() -> str:
    """ISO 8601 形式の UTC タイムスタンプを返す。"""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HostInfo:
    """実行ホストのメタ情報（互換性検証用）。"""

    hostname_hash: str = ""
    platform: str = ""
    hve_version: str = ""
    copilot_sdk_version: str = ""
    python_version: str = ""

    @classmethod
    def current(cls) -> "HostInfo":
        return cls(
            hostname_hash=_hostname_hash(),
            platform=sys.platform,
            hve_version=_get_package_version("hve", fallback="0.0.0+unknown"),
            copilot_sdk_version=_get_copilot_sdk_version(),
            python_version=_python_version(),
        )


# ---------------------------------------------------------------------------
# Phase 1 (Resume 2-layer txn): Intent Log / Lock Info
# ---------------------------------------------------------------------------

@dataclass
class Intent:
    """Write-Ahead Intent Log のレコード。

    `journal.jsonl` 上の `begin → step* → end` 区間を表現する。
    `completed_at is None` のものが未完了の意図（Phase 4 で recovery 対象）。

    Phase 3 の `RunJournal` 実装側で詳細フォーマットを決定するが、
    本データクラスは `RunState.intent_log` に保持する集約ビューを提供する。
    """

    seq: int
    """journal.jsonl 内での単調増加 seq。"""
    kind: str
    """意図種別。例: `delete-hard` / `step-checkpoint` / `rename`。"""
    target: str = ""
    """対象 ID（run_id / step_id / session_id 等）。"""
    started_at: str = ""
    """ISO 8601 UTC タイムスタンプ。"""
    completed_at: Optional[str] = None
    """完了 ISO 8601 UTC タイムスタンプ。None なら in-flight。"""
    payload: Dict[str, Any] = field(default_factory=dict)
    """意図種別ごとの任意パラメータ。"""


@dataclass
class LockInfo:
    """`<session-state-dir>/runs/<run_id>/.lock` ファイル内容の表現（Phase 2 で永続化）。

    本データクラスは `RunState.lock_holder` として保持され、
    state.json save 時に最後のロック取得者情報を併せて記録する
    （監査・stale 判定の根拠）。
    """

    pid: int
    """ロック取得プロセスの PID。"""
    hostname_hash: str
    """`_hostname_hash()` と同一形式の固定長ハッシュ（PII 漏洩回避）。"""
    acquired_at: str
    """取得時刻（ISO 8601 UTC）。"""
    heartbeat_at: str = ""
    """最終 heartbeat 時刻（ISO 8601 UTC）。120 秒以上更新なし → stale 判定。"""


# ---------------------------------------------------------------------------
# Step 状態
# ---------------------------------------------------------------------------

@dataclass
class StepState:
    """ステップ単位の実行状態。"""

    status: str = "pending"  # _STEP_STATUSES のいずれか
    session_id: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    error_summary: Optional[str] = None
    artifact_paths: List[str] = field(default_factory=list)
    skip_reason: Optional[str] = None
    # Fork-integration (T2.2): フォーク親子リンク。
    # 旧 state.json には存在しないが `_from_dict` で既定値で復元される（後方互換）。
    retry_count: int = 0
    """このステップが自動リトライされた回数（0 = リトライなし）。"""
    forked_session_id: Optional[str] = None
    """リトライ時に使われた fork session_id。リトライ未発火なら None。"""

    # Phase 1 (Resume 2-layer txn): ステップ内 fine-grained progress と SDK セッション状態追跡用。
    checkpoint_marker: Optional[str] = None
    """ステップ内の最終チェックポイント名。例: `main-task-response-received` / `qa-phase-done`。
    Phase 6 で runner が書き込む。Resume 時に checkpoint に応じてフェーズスキップ判定。。"""
    last_journal_seq: int = 0
    """`journal.jsonl` での最終記録 seq。Phase 3 で使用。"""
    sdk_session_exists: Optional[bool] = None
    """最終 reconciliation 時点での SDK セッション存在フラグ。Phase 5 で更新。None = 未チェック。"""

    def __post_init__(self) -> None:
        if self.status not in _STEP_STATUSES:
            raise ValueError(
                f"StepState.status='{self.status}' は無効です。"
                f"有効値: {_STEP_STATUSES}"
            )
        if self.error_summary is not None and len(self.error_summary) > _ERROR_SUMMARY_MAX:
            self.error_summary = self.error_summary[:_ERROR_SUMMARY_MAX]
        # Fork-integration (T2.2): 不正値の正規化
        if not isinstance(self.retry_count, int) or self.retry_count < 0:
            self.retry_count = 0
        # Phase 1: 不正値の正規化
        if not isinstance(self.last_journal_seq, int) or self.last_journal_seq < 0:
            self.last_journal_seq = 0


# ---------------------------------------------------------------------------
# Run 状態
# ---------------------------------------------------------------------------

def _safe_run_id_component(run_id: str) -> str:
    """run_id をパス安全な文字列に正規化する（hve/runner.py の _safe_run_id と同等規則）。

    - 許可文字: 英数字 / ハイフン / アンダースコア
    - 空文字や全削除になった場合は ValueError（呼び出し側で fallback 生成すべき）
    """
    rid = re.sub(r"[^A-Za-z0-9\-_]", "", run_id or "")
    if not rid:
        raise ValueError(f"run_id='{run_id}' はパス安全に正規化できません（空または不正文字のみ）")
    return rid


@dataclass
class RunState:
    """ワークフロー実行 1 回分の状態。

    `state_path` プロパティで `<work_dir>/<run_id>/state.json` を返す。
    work_dir はインスタンス変数 `_work_dir` で保持し、デフォルトは
    `DEFAULT_RUNS_DIR` (= `<session-state-dir>/runs`)。
    """

    schema_version: str = SCHEMA_VERSION
    run_id: str = ""
    session_name: str = ""
    workflow_id: str = ""
    status: str = "pending"
    created_at: str = ""
    last_updated_at: str = ""
    pause_reason: Optional[str] = None
    host: HostInfo = field(default_factory=HostInfo)
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    params_snapshot: Dict[str, Any] = field(default_factory=dict)
    selected_step_ids: List[str] = field(default_factory=list)
    step_states: Dict[str, StepState] = field(default_factory=dict)

    # Phase 1 (Resume 2-layer txn): 新規フィールド。
    journal_path: Optional[str] = None
    """`<session-state-dir>/runs/<run_id>/journal.jsonl` への相対パス。Phase 3 で書き込まれる。"""
    intent_log: List[Intent] = field(default_factory=list)
    """未完了の Intent ビュー。Phase 3 で journal から派生。"""
    sdk_session_index: Dict[str, str] = field(default_factory=dict)
    """`session_id` → 最終確認時刻（ISO 8601 UTC）。Phase 5 reconciler が更新。"""
    lock_holder: Optional[LockInfo] = None
    """最後にロックを保持したプロセスの情報。Phase 2 で更新される。"""

    # asdict で除外するためアンダースコア prefix
    _work_dir: Path = field(default=DEFAULT_RUNS_DIR, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.status not in _RUN_STATUSES:
            raise ValueError(
                f"RunState.status='{self.status}' は無効です。有効値: {_RUN_STATUSES}"
            )
        # 同一インスタンスへの並行 save() を直列化するためのロック。
        # Windows では os.replace() が他スレッドの open 中ターゲットに対して
        # PermissionError を投げ得るため、save 区間全体をロックで保護する。
        # `object.__setattr__` 経由で設定（@dataclass は frozen=True ではないが
        # 念のため）し、`asdict()` には影響しない（dataclass field ではないため）。
        import threading as _threading
        object.__setattr__(self, "_save_lock", _threading.Lock())

    # ------------------------------------------------------------------ I/O
    @classmethod
    def new(
        cls,
        run_id: str,
        workflow_id: str,
        config: Any = None,
        params: Optional[Dict[str, Any]] = None,
        selected_step_ids: Optional[List[str]] = None,
        *,
        session_name: Optional[str] = None,
        work_dir: Optional[Path] = None,
    ) -> "RunState":
        """新規 RunState を構築する（save は呼ばない）。"""
        if not run_id:
            raise ValueError("run_id は必須です")
        # パス安全性検証（不正な run_id はここで弾く）
        _safe_run_id_component(run_id)

        now = _utc_now_iso()
        params_dict = dict(params or {})
        steps = list(selected_step_ids or [])
        step_states = {sid: StepState(status="pending") for sid in steps}

        return cls(
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            session_name=session_name or f"{workflow_id} {run_id}",
            workflow_id=workflow_id,
            status="pending",
            created_at=now,
            last_updated_at=now,
            pause_reason=None,
            host=HostInfo.current(),
            config_snapshot=to_safe_config_dict(config),
            params_snapshot=_to_jsonable(params_dict) or {},
            selected_step_ids=steps,
            step_states=step_states,
            _work_dir=Path(work_dir) if work_dir is not None else DEFAULT_RUNS_DIR,
        )

    @classmethod
    def load(cls, run_id: str, *, work_dir: Optional[Path] = None) -> "RunState":
        """既存 state.json を読み込む。"""
        wd = Path(work_dir) if work_dir is not None else DEFAULT_RUNS_DIR
        safe_id = _safe_run_id_component(run_id)
        path = wd / safe_id / STATE_FILENAME
        if not path.exists():
            raise FileNotFoundError(f"state.json が見つかりません: {path}")
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls._from_dict(data, work_dir=wd)

    @classmethod
    def _from_dict(cls, data: Dict[str, Any], *, work_dir: Path) -> "RunState":
        """dict から RunState を再構築する。

        Phase 1 (Resume 2-layer txn): `schema_version` が `_SUPPORTED_SCHEMA_VERSIONS`
        に含まれない場合は `ValueError` で拒否する（マイグレーション非提供）。
        旧 schema_version="1.0" の state.json は破壊的変更で読み込み不可になる。
        """
        ver = str(data.get("schema_version", "") or "")
        if ver not in _SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"state.json の schema_version='{ver}' は本バージョンの hve では"
                f"サポートされていません（対応: {sorted(_SUPPORTED_SCHEMA_VERSIONS)}）。"
                f" Resume 2-layer transaction protection 導入に伴う破壊的変更です。"
                f" 既存の <session-state-dir>/runs/<run_id>/ は削除してください。"
            )
        host_data = data.get("host") or {}
        host = HostInfo(
            hostname_hash=host_data.get("hostname_hash", ""),
            platform=host_data.get("platform", ""),
            hve_version=host_data.get("hve_version", ""),
            copilot_sdk_version=host_data.get("copilot_sdk_version", ""),
            python_version=host_data.get("python_version", ""),
        )
        steps_raw = data.get("step_states") or {}
        step_states: Dict[str, StepState] = {}
        for sid, st in steps_raw.items():
            if not isinstance(st, dict):
                continue
            try:
                step_states[sid] = StepState(
                    status=st.get("status", "pending"),
                    session_id=st.get("session_id"),
                    started_at=st.get("started_at"),
                    completed_at=st.get("completed_at"),
                    elapsed_seconds=st.get("elapsed_seconds"),
                    error_summary=st.get("error_summary"),
                    artifact_paths=list(st.get("artifact_paths") or []),
                    skip_reason=st.get("skip_reason"),
                    # Fork-integration (T2.2): 後方互換のため get with default
                    retry_count=int(st.get("retry_count") or 0),
                    forked_session_id=st.get("forked_session_id"),
                    # Phase 1: 新フィールド復元
                    checkpoint_marker=st.get("checkpoint_marker"),
                    last_journal_seq=int(st.get("last_journal_seq") or 0),
                    sdk_session_exists=st.get("sdk_session_exists"),
                )
            except ValueError:
                # 無効 status は pending として復元
                step_states[sid] = StepState(status="pending")

        status = data.get("status", "pending")
        if status not in _RUN_STATUSES:
            status = "pending"

        # Phase 1: intent_log / lock_holder の復元
        intent_log_raw = data.get("intent_log") or []
        intent_log: List[Intent] = []
        for rec in intent_log_raw:
            if not isinstance(rec, dict):
                continue
            try:
                intent_log.append(Intent(
                    seq=int(rec.get("seq", 0)),
                    kind=str(rec.get("kind", "")),
                    target=str(rec.get("target", "")),
                    started_at=str(rec.get("started_at", "")),
                    completed_at=rec.get("completed_at"),
                    payload=dict(rec.get("payload") or {}),
                ))
            except (TypeError, ValueError):
                # 破損レコードは黙ってスキップ
                continue

        lock_holder_raw = data.get("lock_holder")
        lock_holder: Optional[LockInfo] = None
        if isinstance(lock_holder_raw, dict):
            try:
                lock_holder = LockInfo(
                    pid=int(lock_holder_raw.get("pid", 0)),
                    hostname_hash=str(lock_holder_raw.get("hostname_hash", "")),
                    acquired_at=str(lock_holder_raw.get("acquired_at", "")),
                    heartbeat_at=str(lock_holder_raw.get("heartbeat_at", "")),
                )
            except (TypeError, ValueError):
                lock_holder = None

        return cls(
            schema_version=ver,
            run_id=data.get("run_id", ""),
            session_name=data.get("session_name", ""),
            workflow_id=data.get("workflow_id", ""),
            status=status,
            created_at=data.get("created_at", ""),
            last_updated_at=data.get("last_updated_at", ""),
            pause_reason=data.get("pause_reason"),
            host=host,
            config_snapshot=dict(data.get("config_snapshot") or {}),
            params_snapshot=dict(data.get("params_snapshot") or {}),
            selected_step_ids=list(data.get("selected_step_ids") or []),
            step_states=step_states,
            # Phase 1: 新フィールド
            journal_path=data.get("journal_path"),
            intent_log=intent_log,
            sdk_session_index=dict(data.get("sdk_session_index") or {}),
            lock_holder=lock_holder,
            _work_dir=work_dir,
        )

    # ------------------------------------------------------------ プロパティ
    @property
    def state_path(self) -> Path:
        """`<work_dir>/<run_id>/state.json` への Path。"""
        return self._work_dir / _safe_run_id_component(self.run_id) / STATE_FILENAME

    @property
    def total_count(self) -> int:
        return len(self.selected_step_ids) or len(self.step_states)

    @property
    def completed_count(self) -> int:
        return sum(1 for st in self.step_states.values() if st.status == "completed")

    # ------------------------------------------------------------------ 永続化
    def to_dict(self) -> Dict[str, Any]:
        """JSON シリアライズ用の dict を返す（_work_dir は除外）。"""
        d = asdict(self)
        # field(repr=False, compare=False) でも asdict には含まれるため明示削除
        d.pop("_work_dir", None)
        return d

    def save(self) -> None:
        """state.json を原子的に保存する（tempfile + os.replace）。

        work-artifacts-layout §4.1 の delete→create ルールは Git 上の成果物に
        対するものであり、state.json のような実行時メタデータには適用しない
        （詳細はモジュール docstring 参照）。

        並行 save() の安全性:
        - 同一 RunState インスタンスへの save() は `_save_lock` で直列化する
          （Windows では os.replace() が同時実行で PermissionError を起こすため）。
        - tmp ファイル名に PID + thread id + ランダムサフィックスを付与し、
          別プロセス/別インスタンスとも tmp 名は衝突しない。
        - Windows では reader が `open` 中の target に対して `os.replace`
          が `PermissionError` を投げ得るため、短スリープ + 最大5回までの
          リトライで吸収する（POSIX では rename は常に成功するため即終了）。
        - 最終 os.replace() は POSIX/Windows ともにアトミックなので、
          リトライ後に成功した時点で reader は常に valid な JSON を読める。
        """
        import threading
        import time
        import uuid

        lock = getattr(self, "_save_lock", None)
        if lock is None:
            # `_from_dict` 等で __post_init__ がスキップされた場合の保険
            lock = threading.Lock()
            object.__setattr__(self, "_save_lock", lock)

        with lock:
            self.last_updated_at = _utc_now_iso()
            target = self.state_path
            target.parent.mkdir(parents=True, exist_ok=True)
            unique = f"{os.getpid()}-{threading.get_ident()}-{uuid.uuid4().hex[:4]}"
            tmp = target.with_suffix(target.suffix + f".{unique}.tmp")
            payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
            try:
                with tmp.open("w", encoding="utf-8") as f:
                    f.write(payload)
                    try:
                        f.flush()
                        os.fsync(f.fileno())
                    except (OSError, AttributeError):  # pragma: no cover
                        pass

                # Windows での reader/writer 競合を吸収するためのリトライ。
                # 1 ステップ完了ごとの save が現実的頻度であり、reader（wizard 起動時の
                # list_resumable_runs）と稀に競合する。実用上は数回のリトライで収束する。
                last_exc: Optional[BaseException] = None
                for attempt in range(10):
                    try:
                        os.replace(tmp, target)
                        last_exc = None
                        break
                    except PermissionError as exc:  # pragma: no cover - Windows 固有
                        last_exc = exc
                        time.sleep(0.01 * (attempt + 1))
                if last_exc is not None:  # pragma: no cover - 全リトライ失敗時のみ
                    raise last_exc
            except Exception:
                try:
                    if tmp.exists():
                        tmp.unlink()
                except OSError:  # pragma: no cover
                    pass
                raise

    def update_step(self, step_id: str, **kwargs: Any) -> None:
        """ステップ状態を更新し即座に save する。

        kwargs は StepState のフィールドを直接指定する。未知ステップの場合は
        新規 StepState を生成する（DAG 動的追加への保険）。
        """
        st = self.step_states.get(step_id)
        if st is None:
            st = StepState(status="pending")
            self.step_states[step_id] = st
        for key, value in kwargs.items():
            if not hasattr(st, key):
                raise AttributeError(f"StepState に '{key}' フィールドはありません")
            setattr(st, key, value)
        # status 検証 / error_summary 切り詰め
        st.__post_init__()
        self.save()


# ---------------------------------------------------------------------------
# Phase 1 (v1.0.3, Major #15/#16): intent_log / lock_holder 同期ヘルパー
# ---------------------------------------------------------------------------

def sync_intent_log_from_journal(state: "RunState", journal: Any) -> None:
    """`journal.pending_intents()` から `state.intent_log` を派生し更新する。

    Major #15 (v1.0.3): `intent_log` field を実利用する経路を提供する。
    呼び出し側は orchestrator / resume CLI の Resume 開始時に
    `sync_intent_log_from_journal(state, journal); state.save()` を実行する想定。

    failures は warn せず握り潰す（state I/O 失敗で実行を止めない原則）。
    """
    try:
        pending = journal.pending_intents()
    except Exception:
        return
    intents: List[Intent] = []
    for rec in pending:
        if not isinstance(rec, dict):
            continue
        try:
            intents.append(Intent(
                seq=int(rec.get("seq", 0)),
                kind=str(rec.get("kind", "")),
                target=str(rec.get("target", "")),
                started_at=str(rec.get("ts", "")),
                completed_at=None,
                payload=dict(rec.get("payload") or {}),
            ))
        except (TypeError, ValueError):
            continue
    state.intent_log = intents


def record_lock_holder(state: "RunState", lock: Any) -> None:
    """`RunLock` 取得直後に `state.lock_holder` を更新する。

    Major #16 (v1.0.3): `lock_holder` field を実利用する経路を提供する。
    `lock` は `RunLock` インスタンス（`_pid` / `_hostname_hash` / `_acquired_at` 属性を持つ）。
    `state.save()` は呼ばないため、呼び出し側で save する必要がある。
    """
    try:
        state.lock_holder = LockInfo(
            pid=int(getattr(lock, "_pid", 0)),
            hostname_hash=str(getattr(lock, "_hostname_hash", "")),
            acquired_at=str(getattr(lock, "_acquired_at", "") or _utc_now_iso()),
            heartbeat_at=str(getattr(lock, "_acquired_at", "") or _utc_now_iso()),
        )
    except Exception:
        # 失敗は静かに無視（lock_holder は監査情報であり、欠落しても実行に影響しない）
        pass


# ---------------------------------------------------------------------------
# 検索 / 互換性チェック
# ---------------------------------------------------------------------------

def list_resumable_runs(work_dir: Optional[Path] = None) -> List[RunState]:
    """`work_dir` 配下の `<run_id>/state.json` を全て列挙し、新しい順に返す。

    - `work_dir` 配下が存在しない場合は空 list を返す。
    - 破損 state.json は warn + skip（import 安全性のため、warn は print）。
    - ソート順: `last_updated_at` 降順、欠落時は `created_at` 降順、
      それも欠落時は run_id 文字列降順。
    """
    wd = Path(work_dir) if work_dir is not None else DEFAULT_RUNS_DIR
    if not wd.exists():
        return []

    runs: List[RunState] = []
    for entry in sorted(wd.iterdir()):
        if not entry.is_dir():
            continue
        state_file = entry / STATE_FILENAME
        if not state_file.exists():
            continue
        try:
            with state_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            state = RunState._from_dict(data, work_dir=wd)
        except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError) as exc:
            # 破損ファイルはスキップ（実行を止めない）
            print(
                f"[run_state] WARN: state.json の読み込み失敗 (skip): {state_file} ({exc})",
                file=sys.stderr,
            )
            continue
        runs.append(state)

    def _sort_key(s: RunState) -> tuple[str, str, str]:
        return (
            s.last_updated_at or "",
            s.created_at or "",
            s.run_id or "",
        )

    runs.sort(key=_sort_key, reverse=True)
    return runs


def _major_version(ver: str) -> str:
    """セマンティックバージョンから major 部分を抽出する（非数値は ver そのまま返す）。"""
    if not ver:
        return ""
    head = ver.split("+", 1)[0].split("-", 1)[0]
    parts = head.split(".")
    return parts[0] if parts and parts[0] else ver


def is_resumable(state: RunState) -> bool:
    """`state` が現環境で再開可能かを判定する。

    判定基準:
      1. status が paused / running / failed のいずれか
      2. SDK のメジャーバージョンが現環境と一致する
         （unknown 同士は一致扱い、片方のみ unknown は不一致扱い）
    """
    if state is None:
        return False
    if state.status not in _RESUMABLE_RUN_STATUSES:
        return False

    saved_sdk = state.host.copilot_sdk_version or ""
    current_sdk = _get_copilot_sdk_version()

    saved_major = _major_version(saved_sdk)
    current_major = _major_version(current_sdk)
    # 完了 0 / unknown 同士は許容（SDK 未インストールでも互換）
    if saved_major != current_major:
        return False
    return True


# ---------------------------------------------------------------------------
# Phase 2: SDK セッション ID 安定化
# ---------------------------------------------------------------------------

# session_id のデフォルト prefix。SDKConfig.session_id_prefix が空の場合に使用する。
DEFAULT_SESSION_ID_PREFIX: str = "hve"

# session_id 構成要素の最大長（SDK 側の長さ制限を想定した安全マージン）。
# Copilot SDK の `~/.copilot/session-state/` は OS のファイル名長制限（通常 255 byte）に
# 依存するため、prefix + run_id + step_id + suffix 合計で 200 文字以内に収める。
_SESSION_ID_MAX_RUN_ID: int = 64
_SESSION_ID_MAX_STEP_ID: int = 48
_SESSION_ID_MAX_SUFFIX: int = 32


def _safe_session_id_token(value: str, *, allow_underscore_dot: bool = True) -> str:
    """session_id の構成要素をパストラバーサル安全に正規化する。

    - 許可文字: 英数字・ハイフン
    - allow_underscore_dot=True の場合はアンダースコア・ドットも許可する
      （step_id の "1.1" のような表記を保持するため）。
    - 不正文字は "-" に置換し、連続する "-" は 1 個に圧縮する。
    """
    if not value:
        return ""
    if allow_underscore_dot:
        cleaned = re.sub(r"[^A-Za-z0-9\-_.]", "-", value)
    else:
        cleaned = re.sub(r"[^A-Za-z0-9\-]", "-", value)
    # 連続するハイフンを 1 個に圧縮し、両端のハイフン/ドットを除去
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-.")
    return cleaned


def make_session_id(
    run_id: str,
    step_id: str,
    suffix: str = "",
    *,
    prefix: str = DEFAULT_SESSION_ID_PREFIX,
) -> str:
    """SDK `client.create_session(session_id=...)` 用の決定論的 ID を生成する。

    Phase 2 (Resume): Run 内の各 Step に対して安定した session_id を割り当て、
    Copilot SDK の `~/.copilot/session-state/<session_id>/` ディレクトリと
    Run/Step を 1:1 で紐付ける。これにより Phase 3 以降の `resume_session()`
    呼び出しが可能になる。

    形式:
      `{prefix}-{run_id}-step-{step_id}[-{suffix}]`

    注意:
      Copilot SDK の sessionId バリデーションは `^[A-Za-z0-9_-]+$` のみ許可する
      （ドット `.` 不許可）。そのため step_id 中の `.` は `-` に正規化する。

    例:
      make_session_id("20260507T153012-abc123", "1.1")
        -> "hve-20260507T153012-abc123-step-1-1"
      make_session_id("20260507T153012-abc123", "1.1", suffix="qa")
        -> "hve-20260507T153012-abc123-step-1-1-qa"

    Args:
        run_id: Run 識別子（_safe_session_id_token で正規化される）。空の場合は
            "unknown" にフォールバックする（呼び出し側のクラッシュを防ぐ）。
        step_id: Step 識別子（"1.1" 等のドット表記を保持）。
        suffix: サブセッション種別（"qa" / "review" / "workiq-prefetch" 等）。
        prefix: 先頭固定文字列。デフォルト "hve"。SDKConfig.session_id_prefix が
            非空の場合は呼び出し側で上書きする。

    Returns:
        パストラバーサル安全な ASCII 文字列。長さは prefix によるが
        通常 60〜120 文字程度。
    """
    safe_prefix = _safe_session_id_token(prefix or DEFAULT_SESSION_ID_PREFIX, allow_underscore_dot=False) or DEFAULT_SESSION_ID_PREFIX
    # SDK の sessionId バリデーション `^[A-Za-z0-9_-]+$` はドット不許可のため、
    # run_id / step_id / suffix 内のドットを `-` に置換する（アンダースコアは許可）。
    safe_run = _safe_session_id_token(run_id or "").replace(".", "-")[:_SESSION_ID_MAX_RUN_ID] or "unknown"
    safe_step = _safe_session_id_token(step_id or "").replace(".", "-")[:_SESSION_ID_MAX_STEP_ID] or "unknown"
    base = f"{safe_prefix}-{safe_run}-step-{safe_step}"
    if suffix:
        safe_suffix = _safe_session_id_token(suffix, allow_underscore_dot=False)[:_SESSION_ID_MAX_SUFFIX]
        if safe_suffix:
            base = f"{base}-{safe_suffix}"
    return base


# ---------------------------------------------------------------------------
# Phase 4: Wizard Resume プロンプト用ヘルパー
# ---------------------------------------------------------------------------

# session_name の最大表示長（wizard / 一覧で長すぎる名前を切り詰める）
_SESSION_NAME_DISPLAY_MAX: int = 60


def default_session_name(
    workflow_id: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    workflow_display_name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """Resume 用の RunState に付与するセッション名を自動生成する。

    Phase 4 (Resume): Wizard で `session_name` がユーザー入力されなかった場合の
    既定値として使用する。例:

      default_session_name("aad", {"app_ids": ["APP-05", "APP-06"]})
        -> "AAD [APP-05,APP-06] 05/07 15:30"
      default_session_name("akm")
        -> "AKM 05/07 15:30"

    Args:
        workflow_id: ワークフロー識別子（"aad", "akm" 等）。
        params: 実行パラメータ。`app_ids` または `app_id` があれば付加する。
        workflow_display_name: 表示名（"AAD - App Architecture Design" 等）。
            未指定時は workflow_id の大文字を使用する。
        now: タイムスタンプ生成時刻（テスト用に注入可能）。未指定時は現在ローカル時刻。

    Returns:
        パネル表示・wizard プロンプトに表示しやすい長さに収めた文字列。
    """
    label = (workflow_display_name or workflow_id or "workflow").strip()
    if not label:
        label = "workflow"
    # 表示名にスペースが含まれる場合は短縮（"AAD - ..." → "AAD"）
    short_label = label.split(" ", 1)[0].split("—", 1)[0].strip() or label
    timestamp = (now or datetime.now()).strftime("%m/%d %H:%M")

    app_ids: List[str] = []
    if params:
        raw = params.get("app_ids")
        if isinstance(raw, list):
            app_ids = [str(a).strip() for a in raw if str(a).strip()]
        elif isinstance(raw, str) and raw.strip():
            app_ids = [a.strip() for a in raw.split(",") if a.strip()]
        if not app_ids:
            single = params.get("app_id")
            if isinstance(single, str) and single.strip():
                app_ids = [single.strip()]

    if app_ids:
        # 表示が肥大化しないよう先頭 2 件のみ
        app_disp = ",".join(app_ids[:2])
        if len(app_ids) > 2:
            app_disp += f"+{len(app_ids) - 2}"
        name = f"{short_label} [{app_disp}] {timestamp}"
    else:
        name = f"{short_label} {timestamp}"

    if len(name) > _SESSION_NAME_DISPLAY_MAX:
        name = name[: _SESSION_NAME_DISPLAY_MAX - 1] + "…"
    return name


def to_local_time_str(iso_utc: Optional[str], *, fmt: str = "%m/%d %H:%M") -> str:
    """ISO 8601 UTC タイムスタンプをローカルタイムの短縮表示に変換する。

    Phase 4 (Resume): Wizard の Resume 一覧で `last_updated_at` 等を
    人間に読みやすい形式で表示するために使用する。

    Args:
        iso_utc: `_utc_now_iso()` が生成した ISO 8601 文字列。空 / None / 不正値は
            "(不明)" を返す。
        fmt: `datetime.strftime` フォーマット。デフォルトは "MM/DD HH:MM"。

    Returns:
        ローカルタイム表記の文字列。タイムゾーン情報は表示しない（短縮表示のため）。
    """
    if not iso_utc:
        return "(不明)"
    try:
        # `fromisoformat` は Python 3.11+ で 'Z' suffix にも対応するが、互換性のため変換
        normalized = iso_utc.replace("Z", "+00:00") if iso_utc.endswith("Z") else iso_utc
        dt = datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return "(不明)"
    if dt.tzinfo is None:
        # naive datetime は UTC とみなす
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        local_dt = dt.astimezone()  # システムローカルタイムへ変換
    except (ValueError, OSError):  # pragma: no cover - 異常系
        local_dt = dt
    return local_dt.strftime(fmt)


def get_current_sdk_version() -> str:
    """現在インストールされている Copilot SDK のバージョン文字列を返す。

    Phase 4 (Resume): Wizard の Resume プロンプトで保存時 SDK バージョンと
    比較するために公開する（`is_resumable` の内部実装と同じロジック）。
    """
    return _get_copilot_sdk_version()
