"""runner.py — StepRunner: 1 ステップを CopilotSession で実行する"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 同時 stdin アクセスを防止し、全ステップで共有される sys.stdin を順番に利用させる。
# asyncio.Lock により同一イベントループ内の複数コルーチンからの同時入力を直列化する。
# Python 3.10+ の DeprecationWarning を回避するため、イベントループ起動後に遅延生成する。
_stdin_lock: Optional[asyncio.Lock] = None


def _get_stdin_lock() -> asyncio.Lock:
    """asyncio.Lock を遅延生成して返す（イベントループ起動後に初回生成）。"""
    global _stdin_lock
    if _stdin_lock is None:
        _stdin_lock = asyncio.Lock()
    return _stdin_lock


def _safe_run_id(run_id: str) -> str:
    """run_id を安全なパスコンポーネントに正規化する。

    - 空の場合は generate_run_id() で自動生成（StepRunner 単独使用への対応）
    - 許可文字: 英数字・ハイフン・アンダースコアのみ（`/` や `..` 等のパストラバーサル文字を除去）
    """
    rid = run_id or generate_run_id()
    # 安全でない文字を除去（英数字・ハイフン・アンダースコア以外）
    rid = re.sub(r"[^A-Za-z0-9\-_]", "", rid)
    # 除去の結果が空になった場合もフォールバック生成
    return rid or generate_run_id()

try:
    from .config import (
        DEFAULT_MODEL,
        MODEL_AUTO_VALUE,
        MODEL_AUTO_REASONING_EFFORT,
        SDKConfig,
        generate_run_id,
        SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS,
        DEFAULT_CONTEXT_INJECTION_MAX_CHARS,
    )
    from .console import Console, _ACTION_DISPLAY, timestamp_prefix
    from .prompts import (
        REVIEW_PROMPT, ADVERSARIAL_RECHECK_PROMPT,
        QA_PROMPT_V2,
        SELF_IMPROVE_SCAN_PROMPT, SELF_IMPROVE_PLAN_PROMPT, SELF_IMPROVE_VERIFY_PROMPT,
        PRE_EXECUTION_QA_PROMPT_V2, MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT,
    )
    from .qa_merger import QADocument, QAMerger
    from .run_state import DEFAULT_SESSION_ID_PREFIX, RunState, make_session_id
    from .self_improve import (
        scan_codebase, record_learning, get_learning_summary,
        ImprovementRecord, VerificationResult,
        DEFAULT_QUALITY_THRESHOLD, LEARNING_SUMMARY_MAX_LENGTH,
    )
    from .workiq import (
        is_workiq_available, build_workiq_mcp_config,
        query_workiq, query_workiq_detailed,
        get_workiq_prompt_template, save_workiq_result,
        WORKIQ_MCP_SERVER_NAME, WORKIQ_MCP_TOOL_NAMES,
        is_workiq_error_response,
        is_workiq_tool_name, extract_tool_name_from_event,
        extract_workiq_tool_name_from_event,
    )
except ImportError:
    from config import (  # type: ignore[no-redef]
        DEFAULT_MODEL,
        MODEL_AUTO_VALUE,
        MODEL_AUTO_REASONING_EFFORT,
        SDKConfig,
        generate_run_id,
        SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS,
        DEFAULT_CONTEXT_INJECTION_MAX_CHARS,
    )
    from console import Console, _ACTION_DISPLAY, timestamp_prefix  # type: ignore[no-redef]
    from prompts import (  # type: ignore[no-redef]
        REVIEW_PROMPT, ADVERSARIAL_RECHECK_PROMPT,
        QA_PROMPT_V2,
        SELF_IMPROVE_SCAN_PROMPT, SELF_IMPROVE_PLAN_PROMPT, SELF_IMPROVE_VERIFY_PROMPT,
        PRE_EXECUTION_QA_PROMPT_V2, MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT,
    )
    from qa_merger import QADocument, QAMerger  # type: ignore[no-redef]
    from run_state import DEFAULT_SESSION_ID_PREFIX, RunState, make_session_id  # type: ignore[no-redef]
    from self_improve import (  # type: ignore[no-redef]
        scan_codebase, record_learning, get_learning_summary,
        ImprovementRecord, VerificationResult,
        DEFAULT_QUALITY_THRESHOLD, LEARNING_SUMMARY_MAX_LENGTH,
    )
    from workiq import (  # type: ignore[no-redef]
        is_workiq_available, build_workiq_mcp_config,
        query_workiq, query_workiq_detailed,
        get_workiq_prompt_template, save_workiq_result,
        WORKIQ_MCP_SERVER_NAME, WORKIQ_MCP_TOOL_NAMES,
        is_workiq_error_response,
        is_workiq_tool_name, extract_tool_name_from_event,
        extract_workiq_tool_name_from_event,
    )

# Phase 4 プロンプト長の上限（長い出力を切り詰めてトークン消費を制御する）
_MAX_SCAN_OUTPUT_LENGTH: int = 8000
_MAX_PLAN_SCAN_LENGTH: int = 4000
_MAX_LEARNING_SUMMARY_LENGTH: int = 2000
_ACTION_DETAIL_MAX_LENGTH: int = 120
_ACTION_RESULT_SINGLE_LINE_MAX_LENGTH: int = 100

# Wave 2-6: Work IQ 優先度フィルタで優先扱いする重要度値
# priority_filter=True 時は "最重要"/"高" を先頭に寄せ、不足分は残りで補填して max 件に収める
_WORKIQ_HIGH_PRIORITY_VALUES: frozenset[str] = frozenset(["最重要", "高"])


def _filter_workiq_questions(
    questions: "List[Any]",
    max_questions: int,
    priority_filter: bool,
) -> "List[Any]":
    """Work IQ クエリ対象の質問を絞り込む。

    priority_filter=True の場合、重要度が "最重要"/"高" の質問を優先して先頭に寄せ、
    不足分は残りの質問で補填した上で max_questions 件に収める。
    priority_filter=False の場合は元の順番のまま max_questions 件を返す。
    max_questions が負の値の場合は 0 として扱う。
    """
    normalized_max = max(0, max_questions)
    if not priority_filter:
        return list(questions)[:normalized_max]

    high = [q for q in questions if getattr(q, "priority", "") in _WORKIQ_HIGH_PRIORITY_VALUES]
    rest = [q for q in questions if getattr(q, "priority", "") not in _WORKIQ_HIGH_PRIORITY_VALUES]
    combined = high + rest
    return combined[:normalized_max]

# ---------------------------------------------------------------------------
# Self-Improve スコープ解決ヘルパー
# ---------------------------------------------------------------------------

# SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS は config.py からインポート済み
# （_SI_SCOPE_DEFAULTS として後方互換エイリアスを公開）
_SI_SCOPE_DEFAULTS = SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS


def _resolve_step_output_paths(workflow: Any, step_id: str) -> List[str]:
    """ステップから成果物パスを取得する。

    workflow_registry.py の StepDef.output_paths を参照する。
    output_paths が未定義または空の場合は空リストを返し、
    呼び出し側で workflow_default にフォールバックする。
    """
    step = next(
        (s for s in getattr(workflow, "steps", []) if getattr(s, "id", None) == step_id),
        None,
    )
    if step is None:
        return []
    paths = getattr(step, "output_paths", None)
    return list(paths) if paths else []

# Auto-QA マージファイルのサフィックス（HVE 実行補助 QA。AQOD 本体成果物 QA-DocConsistency-*.md とは別物）
_EXECUTION_QA_MERGED_SUFFIX: str = "execution-qa-merged.md"
# 事前実行 QA ファイルのサフィックス（メインタスク実行前の質問票）
_PRE_EXECUTION_QA_SUFFIX: str = "pre-execution-qa.md"

# LLM が本文ではなく「成果物サマリー + artifacts: qa/foo.md」だけを返す場合の再パース用。
# セキュリティ上、相対 `qa/*.md` のみを許可し、絶対パスや `..` は読まない。
_QA_ARTIFACT_PATH_RE: re.Pattern[str] = re.compile(
    r"(?:^|[\s`\"'(\[])(qa[\\/][^\s`\"')\]]+?\.md)(?=[\s`\"')\],,。．、;；]|$)",
    re.IGNORECASE,
)


def _extract_safe_qa_artifact_paths(
    content: str,
    base_dir: "Path | str" = ".",
) -> List[Path]:
    """LLM 応答中の安全な `qa/*.md` artifacts パスを抽出する。

    絶対パス、`..` を含むパス、`qa/` 以外のパス、存在しないファイルは除外する。
    """
    base = Path(base_dir)
    base_resolved = base.resolve()
    paths: List[Path] = []
    seen: set[str] = set()
    for match in _QA_ARTIFACT_PATH_RE.finditer(content or ""):
        raw = match.group(1).strip().strip("`\"'").rstrip(".,、。;；")
        candidate = Path(raw.replace("\\", "/"))
        if candidate.is_absolute() or not candidate.parts:
            continue
        if candidate.parts[0].lower() != "qa":
            continue
        if any(part in ("..", "") for part in candidate.parts):
            continue

        full_path = base / candidate
        try:
            resolved = full_path.resolve()
            resolved.relative_to(base_resolved)
        except (OSError, ValueError):
            continue
        if not full_path.is_file():
            continue

        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        paths.append(full_path)
    return paths


def _parse_qa_content_with_artifact_fallback(
    qa_content: str,
    base_dir: "Path | str" = ".",
) -> Tuple["QADocument", Optional[Path]]:
    """QA 応答本文をパースし、失敗時は artifacts 参照先の QA ファイルを再パースする。"""
    parsed = QAMerger.parse_qa_content(qa_content)
    if parsed.questions:
        return parsed, None

    for artifact_path in _extract_safe_qa_artifact_paths(qa_content, base_dir=base_dir):
        try:
            artifact_content = artifact_path.read_text(encoding="utf-8")
        except OSError:
            continue
        candidate = QAMerger.parse_qa_content(artifact_content)
        if candidate.questions:
            return candidate, artifact_path

    return parsed, None


async def _create_session_with_auto_reasoning_fallback(client: Any, session_opts: Dict[str, Any]) -> Any:
    """create_session を呼び出し、SDK が reasoning_effort を未サポートの場合は除外して再試行する。

    SDK バージョン < 0.3.0 互換のための防御。reasoning_effort が opts に
    含まれない場合は単純な create_session 呼び出しと等価。

    検出条件は Python の組み込み TypeError 文言
    (`got an unexpected keyword argument`) と `reasoning_effort` の両方が
    含まれる場合に限定する。これにより、SDK 側の値検証エラー
    (例: `reasoning_effort must be one of ...`) や、別キーワードの
    エラーメッセージに `reasoning_effort` が偶然含まれるケースで
    誤って引数を剥がして再試行することを防ぐ。
    """
    try:
        return await client.create_session(**session_opts)
    except TypeError as exc:
        msg = str(exc)
        if (
            "unexpected keyword argument" in msg
            and "reasoning_effort" in msg
            and "reasoning_effort" in session_opts
        ):
            _opts = {k: v for k, v in session_opts.items() if k != "reasoning_effort"}
            return await client.create_session(**_opts)
        raise


def _truncate_context(text: str, max_length: int) -> str:
    """コンテキストを先頭 + 末尾で切り詰める。"""
    if len(text) <= max_length:
        return text
    head_size = max_length * 3 // 4
    omit_msg = f"\n\n... (中略: 全体 {len(text):,} 文字) ...\n\n"
    tail_size = max_length - head_size - len(omit_msg)
    if tail_size <= 0:
        return text[:max_length]
    return text[:head_size] + omit_msg + text[-tail_size:]


def _is_review_fail(content: str) -> bool:
    """合格判定行のトークンから FAIL 判定かどうかを判定する。

    - 「合格判定」を含む行のみを対象にすることで、
      本文中に "fail" が含まれる場合の誤検知を防ぐ。
    - 合否行は「✅ PASS」または「❌ FAIL」といった一意なトークンを前提とし、
      テンプレート由来の「PASS / FAIL」併記行は FAIL とみなさない。

    敵対的レビューではサマリー/合格判定が必須のため、
    合格判定行が 1 行も見つからない場合はフォーマット不備として
    FAIL 扱い（再レビュー実行側に倒す）とする。
    """
    has_judgement_line = False
    for line in content.splitlines():
        if "合格判定" not in line:
            continue
        has_judgement_line = True

        # 明示的な ✅ PASS トークンがあれば FAIL ではない
        if "✅" in line and "PASS" in line.upper():
            return False

        # 明示的な ❌ FAIL トークンがある場合は FAIL
        if "❌" in line and "FAIL" in line.upper():
            return True

        # フォールバック: 絵文字なしでも大文字小文字を問わず FAIL を検出
        if "FAIL" in line.upper():
            return True

    # 合格判定行が存在しない場合は安全側に倒して FAIL 扱いとする
    return not has_judgement_line


async def _collect_qa_answers(
    console: "Console",
    doc: "QADocument",
    step_id: str,
    config: "SDKConfig",
) -> Tuple[str, bool]:
    """Phase 2b: QA 質問票への回答を収集する。

    questions が空リストの場合は呼び出し元でフォールバック済みであること前提。

    TTY 時:
        questionnaire_table() → prompt_answer_mode() → "all"/"one" フロー → answer_summary()

    非 TTY 時:
        questionnaire_table() のみ表示し、既定値候補を全採用する。

    qa_auto_defaults 時:
        questionnaire_table() のみ表示し、全問既定値候補を自動採用する。
        ウィザードモードの auto_qa=y で設定される。

    Args:
        console: Console インスタンス。
        doc: パース済み QADocument（questions > 0 が前提）。
        step_id: ステップ識別子（プロンプト表示用）。
        config: SDKConfig（タイムアウト設定等）。

    Returns:
        (user_answers_raw, skip_input)
        - user_answers_raw: "番号: ラベル" 形式のテキスト、またはデフォルト採用時は ""。
        - skip_input: True のとき全問デフォルト採用。
    """
    console.questionnaire_table(doc.questions)

    _is_interactive = (
        not config.unattended
        and (config.force_interactive or sys.stdin.isatty())
    )
    if not _is_interactive:
        # 非 TTY または全自動モード: テーブル表示のみ行いデフォルト採用
        if config.unattended:
            console.warning(
                "全自動モードのため、全問既定値候補を自動採用します。"
            )
        else:
            console.warning(
                "stdin が非対話モード（TTY ではない）のため、全問既定値候補を自動採用します。\n"
                "  インタラクティブ入力を強制する場合は --force-interactive オプション（orchestrate コマンド）"
                " または wizard モードの「強制インタラクティブ」設定を有効にしてください。"
            )
        console.status("全問既定値候補を採用しました。")
        return "", True

    # QA 全問デフォルト自動採用モード（wizard の auto_qa=y で設定）
    # Issue Template Workflow (auto-qa-default-answer.yml) と同等の動作:
    # 質問票テーブルを表示した後、全問既定値候補を自動採用してステップを先に進める。
    if config.qa_auto_defaults:
        console.status(
            "QA 自動投入モード: 全問既定値候補を自動採用します。"
        )
        return "", True

    # TTY: フルインタラクティブフロー
    if config.qa_answer_mode:
        mode = config.qa_answer_mode
    else:
        mode = console.prompt_answer_mode()

    if mode == "all":
        # 4A. 全問一括入力モード
        user_answers_raw = await _read_stdin_multiline(
            prompt_msg=(
                f"[Step.{step_id}] QA 回答を入力してください\n"
                "  形式: 「番号: 選択肢」を1行1問で入力（例: 1: A）\n"
                "  空行で入力終了 / skip または何も入力せず Enter で既定値候補を採用:"
            ),
            console=console,
            timeout=config.qa_input_timeout_seconds,
        )
        if user_answers_raw.strip().lower() in ("", "skip"):
            # 全問空入力 → 既定値採用確認
            adopt = console.prompt_yes_no(
                "全問既定値候補を採用しますか？",
                default=True,
            )
            if adopt:
                skip_input = True
            else:
                # 再入力（もう一度同じ一括入力を試みる）
                user_answers_raw = await _read_stdin_multiline(
                    prompt_msg=(
                        f"[Step.{step_id}] QA 回答を再入力してください\n"
                        "  形式: 「番号: 選択肢」を1行1問で入力（例: 1: A）\n"
                        "  空行で入力終了:"
                    ),
                    console=console,
                    timeout=config.qa_input_timeout_seconds,
                )
                skip_input = user_answers_raw.strip().lower() in ("", "skip")
        else:
            skip_input = False
    else:
        # 4B. 1問ずつ入力モード
        answers_dict: Dict[int, str] = {}
        for q in doc.questions:
            ans = console.prompt_question_answer(q)
            answers_dict[q.no] = ans

        # "番号: ラベル" 形式で user_answers_raw を構築
        user_answers_raw = "\n".join(
            f"{no}: {label}" for no, label in answers_dict.items()
        )
        skip_input = False

    # 回答サマリー表示（skip_input 時は全問デフォルト採用のステータスのみ）
    if skip_input:
        console.status("全問既定値候補を採用しました。")
    else:
        _parsed_answers = QAMerger.parse_answers(user_answers_raw)
        console.answer_summary(doc.questions, _parsed_answers)

    return user_answers_raw, skip_input


# ------------------------------------------------------------------
# ファイル I/O 追跡 — ツール分類定数
# ------------------------------------------------------------------

# ツール引数からファイルパスを取得するキー（表示用の summary キーとは分離）
_FILE_PATH_KEYS: tuple = ("path", "filePath", "file_path")

# write 操作を行うツール名
_WRITE_TOOLS: frozenset = frozenset({
    "edit_file", "editFile",
    "write_file", "writeFile",
    "create_file", "createFile",
    "patch", "replace",
})

# read + write の両方を行うツール名（既存ファイルを読んでから書く）
_READ_WRITE_TOOLS: frozenset = frozenset({
    "edit_file", "editFile",
    "patch",
})

# ファイル追跡をスキップするツール名
_SKIP_TOOLS: frozenset = frozenset({
    "glob", "search", "grep", "rg",
})

# Work IQ ツール名（workiq.py の WORKIQ_MCP_TOOL_NAMES と同一）
_WORKIQ_TOOL_NAMES: frozenset = frozenset(WORKIQ_MCP_TOOL_NAMES)

# QA Draft の Work IQ 質問間隔（workiq._WORKIQ_QUERY_INTERVAL_SECONDS と同値のローカル定数）
_WORKIQ_DRAFT_QUERY_INTERVAL_SECONDS: float = 2.0

# QA Draft の Work IQ 結果マーカー文字列
# _clean_results フィルタとの一貫性を保つために定数化する
_WORKIQ_RESULT_NO_DATA = "関連情報なし"
_WORKIQ_RESULT_UNINVESTIGATED_PREFIX = "未調査"

_INTENT_DIAG_MAX_VALUE_LENGTH = 180
_INTENT_DIAG_MAX_ATTRS = 20
_INTENT_DIAG_SENSITIVE_TOKENS: tuple = (
    "token", "api_key", "apikey", "secret", "password", "authorization",
    "auth", "bearer", "cookie", "session", "credential", "private",
    "access_token",
)
_INTENT_DIAG_ALLOWED_KEYS: frozenset = frozenset({
    "intent", "description", "text", "content", "message", "kind", "details",
})

class StepRunner:
    """1 ステップを CopilotSession で実行する。

    フロー (1ステップ内、メイン + 必要時サブセッション):
    ┌──────────────────────────────────────────────────┐
    │ CopilotSession (同一セッション = コンテキスト保持)   │
    │                                                    │
    │  [auto_qa=True かつ AQOD でない場合]                │
    │  Phase 0: 事前 QA                                  │
    │    0a: session.send_and_wait(PRE_EXECUTION_QA_PROMPT_V2)│
    │       → Agent が実行前質問票を生成（成果物なし）    │
    │    0b: CLI stdin で複数行回答入力                   │
    │    0c: [Work IQ 有効時] query_workiq_detailed()    │
    │    0d: qa/{run_id}-{step_id}-pre-execution-qa.md 保存   │
    │       pre_qa_context 文字列を組み立てる             │
    │                                                    │
    │  Phase 1: session.send_and_wait(prompt)            │
    │    → [Phase 0 実行済みの場合] prompt 先頭に         │
    │       pre_qa_context を注入してから実行             │
    │    → Agent がメインタスク実行                        │
    │                                                    │
    │  注: Phase 2（事後 QA / post-QA モード）は廃止済み。 │
    │     旧 qa_phase="post"/"both" および                │
    │     aqod_post_qa_enabled は削除されました。         │
    │                                                    │
    │  [auto_contents_review=True の場合]                 │
    │  Phase 3: session.send_and_wait(REVIEW_PROMPT)     │
    │    → 敵対的レビュー（5軸検証 + PASS/FAIL判定）       │
    │    → FAIL時: 再レビューサイクル（最大2回）            │
    │                                                    │
    │  [auto_self_improve=True の場合]                    │
    │  Phase 4: 自己改善ループ（最大 N イテレーション）     │
    │    → 4a: scan_codebase()  ruff+pytest+markdownlint │
    │    → 4b: LLM 統合評価 + 改善計画生成                 │
    │    → 4c: session 内で改善実行                        │
    │    → 4d: 検証（Verification Loop §10.1）            │
    │    → 4e: record_learning() 学習ログ記録              │
    │    → 4f: デグレード検知（スコア悪化 or FAIL で停止） │
    │                                                    │
    │  session.disconnect()                              │
    └──────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        config: SDKConfig,
        console: Console,
        *,
        resume_state: Optional["RunState"] = None,
    ) -> None:
        self.config = config
        self.console = console
        # Phase 3 (Resume): 完了済みステップの skip / 失敗ステップの resume_session 分岐に使用する。
        # None の場合は新規実行モード（resume 機能を使わない既存挙動と完全互換）。
        self._resume_state = resume_state
        self._workiq_tool_called = False
        self._workiq_mcp_connection_failed = False
        self._workiq_called_tools: List[str] = []
        # Phase 6: サブセッション作成回数カウンター（observability）。
        # run_step() 開始時にリセットされる。テストから参照可能。
        self._sub_sessions_created: int = 0

    def _session_id_prefix(self) -> str:
        """SDKConfig.session_id_prefix が空ならデフォルト ("hve") を返す。"""
        prefix = (self.config.session_id_prefix or "").strip()
        return prefix or DEFAULT_SESSION_ID_PREFIX

    def _get_context_injection_max_chars(self) -> int:
        """コンテキスト注入上限を返す。None/不正値は既定値 20,000 に正規化する。"""
        value = getattr(self.config, "context_injection_max_chars", DEFAULT_CONTEXT_INJECTION_MAX_CHARS)
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            return DEFAULT_CONTEXT_INJECTION_MAX_CHARS
        return normalized if normalized > 0 else DEFAULT_CONTEXT_INJECTION_MAX_CHARS

    def _make_step_session_id(self, step_id: str, suffix: str = "") -> str:
        """このステップ用の決定論的 session_id を生成する。

        Phase 2 (Resume): 同 run_id × step_id × suffix の組み合わせは常に同じ
        session_id を返すため、Phase 3 で `client.resume_session(session_id)` を
        呼べる前提を作る。

        Args:
            step_id: ステップ識別子（"1.1" 等）
            suffix: サブセッション種別（"qa" / "review" / "pre-qa" 等）。空ならメインセッション。
        """
        return make_session_id(
            run_id=self.config.run_id,
            step_id=step_id,
            suffix=suffix,
            prefix=self._session_id_prefix(),
        )

    def _build_sub_session_opts(
        self,
        model: str,
        *,
        include_workiq: bool = False,
        step_id: Optional[str] = None,
        suffix: str = "",
    ) -> Dict[str, Any]:
        """レビュー/QA 用の別セッション構築オプションを生成する。

        メインセッションの custom_agent / custom_agents を除外した
        最小限のオプションセットを返す。Work IQ は QA フェーズ専用で、
        include_workiq=True の場合だけ追加する。

        Phase 2 (Resume): step_id + suffix が指定された場合は決定論的 session_id を
        付与する（make_session_id で生成）。後方互換のため step_id=None の場合は
        session_id を付与しない（SDK 側で自動生成）。
        """
        from copilot.session import PermissionHandler
        opts: Dict[str, Any] = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
        }
        # Auto 経路では DEFAULT_MODEL を明示して CLI ユーザー設定の -high バリアント上書きを回避する。
        if model and model != MODEL_AUTO_VALUE:
            opts["model"] = model
        else:
            opts["model"] = DEFAULT_MODEL
            opts["reasoning_effort"] = MODEL_AUTO_REASONING_EFFORT
        _mcp = {
            _k: _v
            for _k, _v in (self.config.mcp_servers or {}).items()
            if include_workiq or _k != WORKIQ_MCP_SERVER_NAME
        }

        # Work IQ MCP Server は QA フェーズ専用のサブセッションにだけ追加する。
        if include_workiq and self.config.is_workiq_qa_enabled() and is_workiq_available():
            _workiq_mcp = build_workiq_mcp_config(
                tenant_id=self.config.workiq_tenant_id,
            )
            for _k, _v in _workiq_mcp.items():
                if _k not in _mcp:
                    _mcp[_k] = _v

        if _mcp:
            opts["mcp_servers"] = _mcp

        # Phase 2: 決定論的 session_id を付与（step_id + suffix が指定された場合のみ）
        if step_id:
            opts["session_id"] = self._make_step_session_id(step_id, suffix=suffix)

        return opts

    # ------------------------------------------------------------------
    # Phase 6: サブセッション要否の判定ヘルパー（テスト容易性のために分離）
    # ------------------------------------------------------------------

    def _should_use_pre_qa_sub_session(self, qa_model: str, workiq_available: bool) -> bool:
        """事前 QA にサブセッションが必要かを判定する。

        以下のいずれかが True の場合にサブセッションを作成する:
        - qa_model が main_model と異なる（MODEL_AUTO_VALUE 同士なら同一とみなす）
        - WorkIQ MCP が利用可能（QA 専用セッションに WorkIQ を含める必要があるため）
        """
        return (qa_model != self.config.model) or workiq_available

    def _should_use_qa_sub_session(self, qa_model: str, workiq_available: bool) -> bool:
        """事後 QA にサブセッションが必要かを判定する。

        事前 QA と同一条件:
        - qa_model が main_model と異なる
        - WorkIQ MCP が利用可能
        """
        return (qa_model != self.config.model) or workiq_available

    def _should_use_review_sub_session(self, review_model: str) -> bool:
        """敵対的レビューにサブセッションが必要かを判定する。

        review_model が main_model と異なる場合にのみサブセッションを作成する。
        Review フェーズでは WorkIQ は使用しないためモデル差異のみを判定する。
        """
        return review_model != self.config.model

    def _log_sub_session_reason(
        self,
        step_id: str,
        phase: str,
        qa_model: Optional[str] = None,
        workiq_available: bool = False,
    ) -> None:
        """サブセッション作成理由を console.event() で記録する（secrets 非出力）。

        呼び出し元は必ずサブセッション作成条件（モデル差異 or WorkIQ 有効）が
        True のときのみ呼び出すこと。条件が全て False の状態で呼ばれた場合は
        "(内部エラー: 理由不明)" と記録する（呼び出しバグの早期検知用）。

        Args:
            step_id: ステップ識別子（ログ識別用）
            phase: フェーズ名（"Pre-QA" / "Post-QA" / "Review"）
            qa_model: QA/Review 用モデル名（Noneの場合はモデル差異ログを省略）
            workiq_available: WorkIQ が有効かどうか
        """
        _reasons: List[str] = []
        if qa_model is not None and qa_model != self.config.model:
            _reasons.append(
                f"モデル差異 (sub={qa_model!r}, main={self.config.model!r})"
            )
        if workiq_available:
            _reasons.append("WorkIQ 有効")
        # 呼び出し元の責務: _reasons が空になるのは呼び出し側のバグ
        _reason_str = "、".join(_reasons) if _reasons else "(内部エラー: 理由不明)"
        self.console.event(
            f"  ▶ [{step_id}] {phase} サブセッション作成 — 理由: {_reason_str}"
        )

    def _log_main_session_reuse(self, step_id: str, phase: str) -> None:
        """メインセッション再利用を console.event() で記録する。"""
        self.console.event(
            f"  🔄 [{step_id}] {phase} メインセッションを再利用"
        )

    # ------------------------------------------------------------------
    # Phase 3 (Resume): メインセッションの resume / create フォールバック
    # ------------------------------------------------------------------

    # `resume_session()` が受け付けるオプションのキー（SDK 仕様）。
    # `agent` / `model` / `mcp_servers` / `custom_agents` / `streaming` /
    # `on_permission_request` のみが伝搬可能で、`session_id` は位置引数で渡す。
    #
    # 注: `reasoning_effort` は意図的にここに含めない。Resume 経路では
    # サーバ側がセッション継続情報を保持する想定で、Auto モデル選択時の
    # reasoning_effort 制約 (claude-opus-4.7-high 等) は新規 create_session
    # 経路でのみ付与する設計（hve/config.py MODEL_AUTO_REASONING_EFFORT 参照）。
    # Resume 経由で 400 エラーが再発する場合は本セット見直しを検討する。
    _RESUME_SESSION_KEYS: frozenset[str] = frozenset({
        "on_permission_request",
        "model",
        "mcp_servers",
        "custom_agents",
        "agent",
        "streaming",
    })

    def _should_resume_main_session(self, step_id: str, session_id: str) -> bool:
        """resume_state に同 step が running/failed として記録されているか判定する。

        - resume_state が None（新規実行）の場合は常に False。
        - 該当 step が completed / skipped / blocked の場合は False（再実行不要）。
        - session_id が一致しない場合は False（前回と SDK 側の紐付けが切れているため
          新規 create のほうが安全）。
        """
        if self._resume_state is None:
            return False
        st = self._resume_state.step_states.get(step_id)
        if st is None:
            return False
        if st.status not in ("running", "failed"):
            return False
        if not st.session_id or st.session_id != session_id:
            return False
        return True

    async def _create_or_resume_main_session(
        self,
        *,
        client: Any,
        session_opts: Dict[str, Any],
        step_id: str,
    ) -> Any:
        """メインセッションを resume_session または create_session で構築する。

        Phase 3 (Resume): 完了/スキップ済みのステップは Resume 経路で
        ここに到達せず、ここに来るのは「未着手 / running 中で中断 / 失敗」のいずれか。
        前者は `create_session`、後二者は `resume_session` で再開を試みる。

        フォールバック: `resume_session` が SDK 側の理由（セッション削除、
        バージョン不整合など）で失敗した場合は新規 `create_session` に切り替える。

        副作用: resume_state がある場合、ステップを `running` 状態に更新し、
        `session_id` と `started_at` を記録する（後続のクラッシュ時に
        次回 resume の判定材料となる）。
        """
        session_id = session_opts.get("session_id", "")
        # Phase 3 (Resume): resume するか否かを判定 → その後 state を更新する。
        # 判定より先に _mark_step_running で status を上書きすると、
        # `_should_resume_main_session` の status 判定が常に "running" になってしまうバグになる。
        should_resume = self._should_resume_main_session(step_id, session_id)

        # state.json を "running" 状態にマーク（resume_state があるときのみ）。
        # 判定の後に呼ぶことで、resume 判定の入力（保存時 status / session_id）が壊れない。
        self._mark_step_running(step_id, session_id)

        if not should_resume:
            return await _create_session_with_auto_reasoning_fallback(client, session_opts)

        # Resume 経路: resume_session に渡せるキーだけ抽出する
        resume_opts = {
            k: v for k, v in session_opts.items()
            if k in self._RESUME_SESSION_KEYS
        }
        try:
            session = await client.resume_session(session_id, **resume_opts)
            self.console.event(
                f"  ↻ Step.{step_id} を session_id={session_id} から再開しました"
            )
            return session
        except Exception as exc:
            self.console.warning(
                f"resume_session 失敗 ({type(exc).__name__}): {exc}"
                f" → 新規 create_session にフォールバックします (step={step_id})"
            )
            # 注: session_opts には Auto モデル時 reasoning_effort='high' が含まれるため、
            # SDK バージョン < 0.3.0 環境では _create_session_with_auto_reasoning_fallback
            # の内部リトライが追加で発生し SDK 呼び出しが最大 4 回（resume 1 + create 2 + 内部 retry 1）になる。
            return await _create_session_with_auto_reasoning_fallback(client, session_opts)

    def _mark_step_running(self, step_id: str, session_id: str) -> None:
        """resume_state に step を `running` として記録する（resume_state なしなら no-op）。

        失敗しても実行を止めない（warn のみ）。state.json への書き込みエラーで
        ステップ実行をブロックすることは避ける（実行成功優先）。
        """
        if self._resume_state is None:
            return
        try:
            from datetime import datetime, timezone
            self._resume_state.update_step(
                step_id,
                status="running",
                session_id=session_id,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:  # pragma: no cover - I/O 例外パスは E2E で確認
            self.console.warning(
                f"state.json への running 状態更新に失敗しました (step={step_id}): {exc}"
            )

    # ------------------------------------------------------------------
    # メインタスク成果物改善ヘルパー（Phase 2c / Phase 3 / Phase 4 共通）
    # ------------------------------------------------------------------

    async def _apply_main_artifact_improvements(
        self,
        *,
        session: Any,
        step_id: str,
        title: str,
        workflow_id: Optional[str],
        custom_agent: Optional[str],
        original_prompt: str,
        main_output: str,
        source_phase: str,
        improvement_context: str,
        timeout: float,
    ) -> str:
        """改善材料に基づきメインタスク成果物を改善する共通ヘルパー。

        Args:
            session: メインセッション（Phase 1 と同じセッション）。
            step_id: ステップ識別子。
            title: ステップタイトル。
            workflow_id: ワークフロー識別子（AQOD ルール適用に使用）。
            custom_agent: Custom Agent 名。
            original_prompt: メインタスク実行時の元プロンプト。
            main_output: Phase 1 メインタスクの実行結果（参考）。Phase 2c/3/4 の改善適用後も
                再取得されないため、実際の最新成果物はセッションのコンテキストに蓄積されている。
            source_phase: 改善材料の出所フェーズ名。
            improvement_context: 改善材料のテキスト。
            timeout: セッションタイムアウト秒数。

        Returns:
            改善後の応答テキスト（失敗時は空文字）。
        """
        if not improvement_context or not improvement_context.strip():
            return ""

        try:
            _max_context_chars = self._get_context_injection_max_chars()
            _trunc_prompt = _truncate_context(original_prompt, _max_context_chars)
            _trunc_output = _truncate_context(main_output, _max_context_chars)
            _trunc_context = _truncate_context(improvement_context, _max_context_chars)

            _improve_prompt = MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT.format(
                source_phase=source_phase,
                workflow_id=workflow_id or "(未指定)",
                step_id=step_id,
                step_title=title,
                custom_agent=str(custom_agent) if custom_agent else "None",
                original_prompt=_trunc_prompt,
                main_output=_trunc_output,
                improvement_context=_trunc_context,
            )

            _response = await session.send_and_wait(_improve_prompt, timeout=timeout)
            _result = _extract_text(_response)

            if not _result or not _result.strip():
                self.console.warning(
                    f"[{step_id}] {source_phase}: メイン成果物改善の応答が空でした。"
                )

            return _result
        except Exception as exc:
            self.console.warning(
                f"[{step_id}] {source_phase}: メイン成果物改善に失敗しました（後続処理を継続）: {exc}"
            )
            return ""

    def _check_diff_after_improvement(self, step_id: str, source_phase: str) -> List[str]:
        """改善適用後に git diff を確認し、変更ファイルを返す。

        改善が必要と判定されたにもかかわらず差分がない場合は warning を出力する。

        Returns:
            変更されたファイルのリスト（差分なしの場合は空リスト）。
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                self.console.warning(
                    f"[{step_id}] {source_phase}: git diff の実行に失敗しました"
                    f" (exit={result.returncode}): {result.stderr.strip()}"
                )
                return []
            changed_files = [f for f in result.stdout.splitlines() if f.strip()]
            if changed_files:
                self.console.event(
                    f"  📝 [{step_id}] {source_phase}: 差分あり ({len(changed_files)} ファイル変更): "
                    + ", ".join(changed_files[:5])
                    + ("..." if len(changed_files) > 5 else "")
                )
            else:
                self.console.warning(
                    f"[{step_id}] {source_phase}: 改善が適用されましたが git diff に差分がありません。"
                    " 成果物がセッション内のみで更新された可能性があります。"
                )
            return changed_files
        except Exception as exc:
            self.console.warning(
                f"[{step_id}] {source_phase}: git diff 確認に失敗しました: {exc}"
            )
            return []

    # ------------------------------------------------------------------
    # ファイル I/O 追跡ヘルパー
    # ------------------------------------------------------------------

    def _track_tool_files(self, step_id: str, tool_name: str, args: dict) -> None:
        """ツール実行イベントからファイルパスを抽出し Console に記録・表示する。"""
        import os

        if tool_name in _SKIP_TOOLS:
            return

        # シェル系ツール: command キーからファイル操作を簡易抽出
        if tool_name == "bash":
            command = args.get("command", "")
            if isinstance(command, str) and command:
                self._track_bash_files(step_id, command)
            return

        if tool_name == "powershell":
            command = args.get("command", "")
            if isinstance(command, str) and command:
                self._track_powershell_files(step_id, command)
            return

        # ファイル操作ツール: 引数キーからパスを抽出
        for key in _FILE_PATH_KEYS:
            val = args.get(key)
            if val and isinstance(val, str):
                normalized = os.path.normpath(val)
                if tool_name in _READ_WRITE_TOOLS:
                    self.console.track_file(step_id, normalized, "read")
                    self.console.track_file(step_id, normalized, "write")
                    self.console.file_io(step_id, normalized, "read")
                    self.console.file_io(step_id, normalized, "write")
                elif tool_name in _WRITE_TOOLS:
                    self.console.track_file(step_id, normalized, "write")
                    self.console.file_io(step_id, normalized, "write")
                else:
                    self.console.track_file(step_id, normalized, "read")
                    self.console.file_io(step_id, normalized, "read")
                break

    def _track_bash_files(self, step_id: str, command: str) -> None:
        """bash コマンド文字列からファイル操作を簡易抽出する。"""
        import os
        import re

        for m in re.finditer(r'tee(?:\s+-a)?\s+([^\s;|&]+)', command):
            path = m.group(1).strip("'\"")
            if path and not path.startswith("-"):
                self.console.track_file(step_id, os.path.normpath(path), "write")
                self.console.file_io(step_id, os.path.normpath(path), "write")

        for m in re.finditer(r'(?:\d+>>?|>>?)\s*([^\s;|&]+)', command):
            path = m.group(1).strip("'\"")
            if path and not path.startswith("-"):
                self.console.track_file(step_id, os.path.normpath(path), "write")
                self.console.file_io(step_id, os.path.normpath(path), "write")

        for m in re.finditer(
            r'\b(?:cp|mv)\s+(?:-\w+\s+)*([^\s;|&]+)\s+([^\s;|&]+)', command
        ):
            dest = m.group(2).strip("'\"")
            if dest and not dest.startswith("-"):
                self.console.track_file(step_id, os.path.normpath(dest), "write")
                self.console.file_io(step_id, os.path.normpath(dest), "write")

        for m in re.finditer(
            r'\b(?:cat|head|tail|less|more)\s+(?:-\w+\s+)*([^\s;|&>]+)', command
        ):
            path = m.group(1).strip("'\"")
            if path and not path.startswith("-"):
                self.console.track_file(step_id, os.path.normpath(path), "read")
                self.console.file_io(step_id, os.path.normpath(path), "read")

    def _track_powershell_files(self, step_id: str, command: str) -> None:
        """PowerShell コマンド文字列からファイル操作を簡易抽出する（best-effort）。

        設計方針:
        - -Path / -FilePath / -LiteralPath 明示パラメータからのキャプチャを最優先
        - パイプライン/複文ごとに cmdlet を判定して read/write を決める
        - PowerShell のパラメータ構文の完全な網羅は目的としない
        - 未検出ケースがあっても step_io_summary が空になるだけで動作に影響しない
        """
        import os
        import re

        path_write_cmdlets = {"set-content", "add-content", "new-item"}
        file_path_write_cmdlets = {"out-file"}

        # パイプラインや複文ごとに判定（例: Get-Content ... | Out-File ...）
        for segment in re.split(r"[|;]", command):
            seg = segment.strip()
            if not seg:
                continue

            cmdlet_match = re.search(r"\b([A-Za-z]+-[A-Za-z][A-Za-z0-9]*)\b", seg)
            cmdlet = cmdlet_match.group(1).lower() if cmdlet_match else ""

            # -Path / -LiteralPath
            for m in re.finditer(
                r'-(?:Path|LiteralPath)\s+([^\s;|&]+)', seg, re.IGNORECASE
            ):
                path = m.group(1).strip("'\"")
                if path and not path.startswith("-"):
                    # 既知 write cmdlet 以外は read 扱い（best-effort）
                    mode = "write" if cmdlet in path_write_cmdlets else "read"
                    normalized = os.path.normpath(path)
                    self.console.track_file(step_id, normalized, mode)
                    self.console.file_io(step_id, normalized, mode)

            # -FilePath
            for m in re.finditer(r'-FilePath\s+([^\s;|&]+)', seg, re.IGNORECASE):
                path = m.group(1).strip("'\"")
                if path and not path.startswith("-"):
                    # 既知 write cmdlet 以外は read 扱い（best-effort）
                    mode = "write" if cmdlet in file_path_write_cmdlets else "read"
                    normalized = os.path.normpath(path)
                    self.console.track_file(step_id, normalized, mode)
                    self.console.file_io(step_id, normalized, mode)

            # -Destination（copy/move の出力先）
            for m in re.finditer(r'-Destination\s+([^\s;|&]+)', seg, re.IGNORECASE):
                path = m.group(1).strip("'\"")
                if path and not path.startswith("-"):
                    normalized = os.path.normpath(path)
                    self.console.track_file(step_id, normalized, "write")
                    self.console.file_io(step_id, normalized, "write")

        # PowerShell リダイレクト演算子 (>, >>)
        for m in re.finditer(r'(?:\d+)?>>?\s*([^\s;|&]+)', command):
            path = m.group(1).strip("'\"")
            if path and not path.startswith("-"):
                normalized = os.path.normpath(path)
                self.console.track_file(step_id, normalized, "write")
                self.console.file_io(step_id, normalized, "write")

    @staticmethod
    def _build_action_display(tool_name: str, args: Any) -> Tuple[str, str]:
        """ツール名と引数から Copilot CLI 風の action_name/detail を生成する。"""
        action_name = _ACTION_DISPLAY.get(tool_name, tool_name)
        detail = ""
        if not isinstance(args, dict):
            return action_name, detail

        if tool_name in ("grep", "rg", "search"):
            pattern = args.get("pattern") or args.get("query") or ""
            scope = (
                args.get("scope")
                or args.get("path")
                or args.get("paths")
                or args.get("glob")
                or args.get("include")
                or ""
            )
            if pattern:
                detail = f"\"{pattern}\""
                if scope:
                    detail = f"{detail} ({scope})"
            elif scope:
                detail = str(scope)
            return action_name, StepRunner._truncate_action_detail(detail)

        if tool_name in ("read_file", "readFile", "cat", "head", "tail"):
            path = args.get("path") or args.get("filePath") or args.get("file_path") or ""
            if path:
                action_name = f"Read {Path(str(path)).name}"
                detail = str(path)
            return action_name, StepRunner._truncate_action_detail(detail)

        if tool_name in ("edit_file", "editFile", "write_file", "writeFile", "create_file", "createFile"):
            path = args.get("path") or args.get("filePath") or args.get("file_path") or ""
            if path:
                action_name = f"{_ACTION_DISPLAY.get(tool_name, tool_name)} {Path(str(path)).name}"
                detail = str(path)
            return action_name, StepRunner._truncate_action_detail(detail)

        if tool_name in ("bash", "powershell"):
            command = args.get("command") or ""
            if command:
                detail = str(command)
            return action_name, StepRunner._truncate_action_detail(detail)

        for key in ("command", "path", "filePath", "file_path", "query", "pattern", "url", "intent"):
            val = args.get(key)
            if val:
                val_str = str(val)
                detail = val_str
                break
        return action_name, StepRunner._truncate_action_detail(detail)

    @staticmethod
    def _truncate_action_detail(text: str) -> str:
        """アクション詳細文字列を表示上限で切り詰める。"""
        if len(text) > _ACTION_DETAIL_MAX_LENGTH:
            return text[:_ACTION_DETAIL_MAX_LENGTH] + "..."
        return text

    @staticmethod
    def _build_tool_result_text(data: Any) -> str:
        """tool.execution_complete の data から結果サマリー文字列を生成する。"""
        get = StepRunner._get
        result_summary = get(data, "result_summary", "resultSummary", default="")
        if result_summary:
            return str(result_summary)

        output = get(data, "output", default="")
        if isinstance(output, str):
            stripped = output.strip()
            if not stripped:
                return ""
            lines = stripped.splitlines()
            if len(lines) == 1:
                return lines[0][:_ACTION_RESULT_SINGLE_LINE_MAX_LENGTH]
            return f"{len(lines)} lines"
        return ""

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    async def _run_pre_execution_qa(
        self,
        session: Any,
        client: Any,
        step_id: str,
        original_prompt: str,
        custom_agent: Optional[str],
        workflow_id: Optional[str],
        current_phase: int,
        total_phases: int,
    ) -> str:
        """Phase 0: 事前 QA 質問票生成・回答収集・Work IQ (optional)。

        PRE_EXECUTION_QA_PROMPT_V2 を使用し、メインタスク実行前に不明点を確認する。
        AKM/AQOD ワークフローでは呼び出し元でスキップすること。

        Returns:
            pre_qa_context: Phase 1 プロンプト先頭に注入する Markdown 文字列。
            空文字の場合は注入なし。
        """
        self.console.step_phase_start(step_id, current_phase, total_phases, "事前 QA")
        phase0_start = time.time()

        _qa_model = self.config.get_qa_model()
        _qa_workiq_requested = self.config.is_workiq_qa_enabled()
        _qa_workiq_configured = WORKIQ_MCP_SERVER_NAME in (self.config.mcp_servers or {})
        _qa_workiq_available = (
            _qa_workiq_requested
            and (_qa_workiq_configured or is_workiq_available())
        )
        if _qa_workiq_requested and not _qa_workiq_available:
            self.console.warning(
                "Work IQ が検出できません。事前 QA フェーズの Work IQ 連携をスキップします。"
            )

        _use_pre_qa_sub_session = self._should_use_pre_qa_sub_session(_qa_model, _qa_workiq_available)
        _pre_qa_session = None
        pre_qa_context = ""
        try:
            _effective_pre_qa_session = session
            # Phase 0a: 事前質問票生成 — 原プロンプトをコンテキストとして注入
            _max_context_chars = self._get_context_injection_max_chars()
            _prompt_context = _truncate_context(original_prompt, _max_context_chars)
            _effective_pre_qa_prompt = (
                "以下はこれから実行するタスクのプロンプトです。"
                "成果物はまだ存在しません。このプロンプトを前提として事前質問票を作成してください。\n\n"
                f"=== タスクプロンプト（最大{_max_context_chars:,}文字） ===\n"
                f"{_prompt_context}\n"
                "=== タスクプロンプトここまで ===\n\n"
                f"{PRE_EXECUTION_QA_PROMPT_V2}"
            )

            if _use_pre_qa_sub_session:
                self._log_sub_session_reason(
                    step_id, "Pre-QA",
                    qa_model=_qa_model,
                    workiq_available=_qa_workiq_available,
                )
                _pre_qa_session = await _create_session_with_auto_reasoning_fallback(
                    client,
                    self._build_sub_session_opts(
                        _qa_model,
                        include_workiq=_qa_workiq_available,
                        step_id=step_id,
                        suffix="pre-qa",
                    ),
                )
                _pre_qa_session.on(self._handle_session_event)
                _effective_pre_qa_session = _pre_qa_session
                self._sub_sessions_created += 1
                _qa_workiq_mcp_enabled = False  # デフォルト False: loop で server が見つかれば True に更新
                if _qa_workiq_available:
                    try:
                        _mcp_list = await _pre_qa_session.rpc.mcp.list()
                        for _srv in _mcp_list.servers:
                            if getattr(_srv, "name", "") == WORKIQ_MCP_SERVER_NAME:
                                _qa_workiq_mcp_enabled = True
                                break
                    except Exception:
                        _qa_workiq_mcp_enabled = False
            else:
                _qa_workiq_mcp_enabled = False
                self._log_main_session_reuse(step_id, "Pre-QA")

            # Phase 0a: 質問票生成
            pre_qa_response = await _effective_pre_qa_session.send_and_wait(
                _effective_pre_qa_prompt, timeout=self.config.timeout_seconds
            )
            pre_qa_raw = _extract_text(pre_qa_response)

            # フォールバック: LLM が質問票を qa/ ファイルに保存した場合の再取得
            if not pre_qa_raw or len(pre_qa_raw.strip()) < 50:
                for _artifact_path in _extract_safe_qa_artifact_paths(pre_qa_raw or "", base_dir="."):
                    try:
                        pre_qa_raw = _artifact_path.read_text(encoding="utf-8")
                        break
                    except Exception:
                        pass

            # QAMerger でパース
            _parse_succeeded = False
            parsed_pre_qa = QADocument(questions=[])
            if pre_qa_raw:
                try:
                    parsed_pre_qa = QAMerger.parse_qa(pre_qa_raw)
                    _parse_succeeded = bool(parsed_pre_qa.questions)
                except Exception:
                    pass

            # Phase 0b: 回答収集
            user_answers_raw = ""
            skip_input = True
            if _parse_succeeded and parsed_pre_qa.questions:
                user_answers_raw, skip_input = await _collect_qa_answers(
                    self.console, parsed_pre_qa, step_id, self.config
                )

            # Phase 0c: Work IQ（有効かつ質問が存在する場合）
            _workiq_pre_qa_context = ""
            if (
                _qa_workiq_available
                and _qa_workiq_mcp_enabled
                and _parse_succeeded
                and parsed_pre_qa.questions
            ):
                self.console.status("🔍 Work IQ: 事前 QA の質問ごとに M365 調査を開始します...")
                self.console.spinner_start("Work IQ 問い合わせ中...")
                try:
                    _wiq_template = get_workiq_prompt_template(
                        "qa", self.config.workiq_prompt_qa
                    )
                    # Wave 2-6: 重要度フィルタ + 上限適用でクエリ数を削減
                    _filtered_questions = _filter_workiq_questions(
                        parsed_pre_qa.questions,
                        self.config.workiq_max_draft_questions,
                        getattr(self.config, "workiq_priority_filter", True),
                    )
                    _question_items = [(q.no, q.question) for q in _filtered_questions]

                    _per_question_results: Dict[int, str] = {}
                    for _q_no, _q_text in _question_items:
                        _before_count = len(self._workiq_called_tools)
                        try:
                            # F6: 検索精度向上のため構造化（QAQuestion の category/priority/default_answer を活用）
                            _q_obj = next((q for q in parsed_pre_qa.questions if q.no == _q_no), None)
                            _meta_lines = [f"- No: Q{_q_no}", f"- 質問: {_q_text}"]
                            if _q_obj and getattr(_q_obj, "category", ""):
                                _meta_lines.append(f"- 分類: {_q_obj.category}")
                            if _q_obj and getattr(_q_obj, "priority", ""):
                                _meta_lines.append(f"- 重要度: {_q_obj.priority}")
                            if _q_obj and getattr(_q_obj, "default_answer", ""):
                                _meta_lines.append(f"- 既定値候補: {_q_obj.default_answer}")
                            _target_content = "\n".join(_meta_lines)
                            _query = _wiq_template.format(target_content=_target_content)
                            self.console.workiq_prompt(_query, label=f"Work IQ プロンプト [Q{_q_no}]")
                            _detail_result = await query_workiq_detailed(
                                _effective_pre_qa_session,
                                _query,
                                timeout=self.config.workiq_per_question_timeout,
                            )
                            if not self.console.show_stream:
                                self.console.workiq_response(
                                    _detail_result.content or "",
                                    label=f"Work IQ 応答 [Q{_q_no}]",
                                )
                            _after_tools = self._workiq_called_tools[_before_count:]
                            if _detail_result.error:
                                _per_question_results[_q_no] = (
                                    f"Work IQ 失敗: {_detail_result.error}"
                                )
                            elif _after_tools:
                                _per_question_results[_q_no] = _detail_result.content or ""
                            else:
                                _per_question_results[_q_no] = (
                                    f"（Work IQ: ツール呼び出しなし）\n{_detail_result.content or ''}"
                                )
                        except Exception as _wiq_exc:
                            _per_question_results[_q_no] = f"Work IQ エラー: {_wiq_exc}"

                    # 結果をマージ
                    _clean_results = {
                        _q_no: _res
                        for _q_no, _res in _per_question_results.items()
                        if _res and not is_workiq_error_response(_res)
                    }
                    parsed_pre_qa = QAMerger.merge_workiq_results(parsed_pre_qa, _clean_results)
                    _workiq_output_dir = self.config.workiq_draft_output_dir or "qa"
                    _raw_lines: List[str] = []
                    for q in parsed_pre_qa.questions[:self.config.workiq_max_draft_questions]:
                        _ctx = _per_question_results.get(
                            q.no,
                            "（Work IQ 未実行）",
                        )
                        _raw_lines.extend([f"### Q{q.no}: {q.question}", _ctx, ""])
                    save_workiq_result(
                        self.config.run_id, step_id, "pre-qa-draft",
                        "\n".join(_raw_lines).strip(),
                        base_dir=_workiq_output_dir,
                    )
                    _workiq_pre_qa_context = "\n".join(_raw_lines).strip()
                    self.console.status(
                        f"✅ Work IQ: {sum(1 for q in parsed_pre_qa.questions if q.workiq_answer)} 件の質問に回答案を統合しました"
                    )
                except Exception as draft_exc:
                    self.console.warning(f"Work IQ 事前 QA 連携に失敗しました: {draft_exc}")
                finally:
                    self.console.spinner_stop()

            # Phase 0d: QA 回答マージ + qa/ ファイル保存
            if _parse_succeeded and parsed_pre_qa.questions:
                try:
                    if skip_input:
                        answers: Dict[int, str] = {}
                        merged_pre_qa = QAMerger.merge_answers(parsed_pre_qa, answers, use_defaults=True)
                    else:
                        answers = QAMerger.parse_answers(user_answers_raw)
                        merged_pre_qa = QAMerger.merge_answers(parsed_pre_qa, answers)
                    merged_content = QAMerger.render_merged(merged_pre_qa)

                    _pre_qa_file_path = Path(
                        f"qa/{self.config.run_id}-{step_id}-{_PRE_EXECUTION_QA_SUFFIX}"
                    )
                    _pre_qa_old_content = ""
                    if _pre_qa_file_path.exists():
                        try:
                            _pre_qa_old_content = _pre_qa_file_path.read_text(encoding="utf-8")
                        except OSError as _e:
                            self.console.warning(f"事前 QA ファイルの旧コンテンツ読み込みに失敗しました ({_pre_qa_file_path}): {_e}。diff は全行追加として表示されます。")
                    _written = QAMerger.save_merged(merged_content, _pre_qa_file_path)
                    if _written:
                        self.console.status(
                            f"✅ 事前 QA 質問票を保存しました ({_pre_qa_file_path.as_posix()})"
                        )
                        self.console.file_diff(step_id, _pre_qa_file_path.as_posix(), _pre_qa_old_content, merged_content)

                    # pre_qa_context を組み立てる
                    _context_lines = [
                        "## 事前 QA 確認済み情報\n",
                        merged_content,
                    ]
                    if _workiq_pre_qa_context:
                        _context_lines.append("\n\n## Work IQ による補足情報\n")
                        _context_lines.append(_workiq_pre_qa_context)
                    pre_qa_context = "\n".join(_context_lines)
                except Exception as merge_exc:
                    self.console.warning(f"事前 QA マージ処理に失敗しました: {merge_exc}")
                    # pre_qa_context を生の質問票から組み立てるフォールバック
                    if pre_qa_raw:
                        pre_qa_context = f"## 事前 QA 質問票（未マージ）\n\n{pre_qa_raw}"

        finally:
            if _pre_qa_session is not None:
                await _pre_qa_session.disconnect()

        self.console.step_phase_end(
            step_id, current_phase, total_phases, "事前 QA",
            elapsed=time.time() - phase0_start,
        )
        return pre_qa_context

    async def run_step(
        self,
        step_id: str,
        title: str,
        prompt: str,
        custom_agent: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> bool:
        """ステップを実行する。

        Args:
            step_id: ステップ識別子（例: "1.1", "2.3"）
            title: ステップタイトル（表示用）
            prompt: メインタスクのプロンプト文字列
            custom_agent: 使用する Custom Agent 名（省略可）
            workflow_id: ワークフロー識別子（省略可）。AQOD 専用プロンプト切り替えに使用。

        Returns:
            True: 成功, False: 失敗
        """
        start = time.time()
        self._workiq_tool_called = False
        self._workiq_mcp_connection_failed = False
        self._workiq_called_tools = []
        # Phase 6: サブセッション作成回数カウンターをリセット
        self._sub_sessions_created = 0

        # run_id を1回だけ正規化して書き戻す（Phase 2/4 で別々に生成されるのを防ぐ）
        self.config.run_id = _safe_run_id(self.config.run_id)

        # --- dry_run ---
        if self.config.dry_run:
            self.console.step_start(step_id, title, agent=custom_agent)
            self.console.event(f"[DRY-RUN] Step.{step_id} would execute: {title}")
            elapsed = time.time() - start
            self.console.step_end(step_id, "success", elapsed=elapsed)
            return True

        # --- SDK インポート確認 ---
        try:
            from copilot import CopilotClient  # type: ignore[import]
            from copilot import SubprocessConfig, ExternalServerConfig  # type: ignore[import]
            from copilot.session import PermissionHandler  # type: ignore[import]
        except ImportError:
            self.console.error(
                "GitHub Copilot SDK がインストールされていません。\n"
                "  pip install github-copilot-sdk  # または適切なパッケージ名で再試行してください。"
            )
            return False

        self.console.step_start(step_id, title, agent=custom_agent)
        self._current_step_id = step_id

        session = None
        client = None
        try:
            # SDK v0.2.2: CopilotClient(config=SubprocessConfig|ExternalServerConfig)
            if self.config.cli_url:
                sdk_config = ExternalServerConfig(url=self.config.cli_url)
            else:
                # verbosity >= 3 (verbose) かつデフォルトの log_level ("error") の場合のみ debug に昇格。
                # ユーザーが明示的に log_level を指定している場合はそれを尊重する。
                _effective_log_level = (
                    "debug"
                    if self.config.verbosity >= 3 and self.config.log_level == "error"
                    else self.config.log_level
                )
                sdk_config = SubprocessConfig(
                    cli_path=self.config.cli_path,
                    github_token=self.config.resolve_token() or None,
                    log_level=_effective_log_level,
                    cli_args=self.config.cli_args,
                )
            client = CopilotClient(config=sdk_config)
            await client.start()

            # セッション構築オプション
            session_opts: Dict[str, Any] = {
                "on_permission_request": PermissionHandler.approve_all,
                "streaming": True,
            }
            # Auto 経路では DEFAULT_MODEL を明示して CLI ユーザー設定の -high バリアント上書きを回避する。
            if self.config.model and self.config.model != MODEL_AUTO_VALUE:
                session_opts["model"] = self.config.model
            else:
                session_opts["model"] = DEFAULT_MODEL
                session_opts["reasoning_effort"] = MODEL_AUTO_REASONING_EFFORT

            # MCP Servers
            if self.config.mcp_servers:
                _main_mcp_servers = {
                    _k: copy.deepcopy(_v)
                    for _k, _v in self.config.mcp_servers.items()
                    if _k != WORKIQ_MCP_SERVER_NAME
                }
                if _main_mcp_servers:
                    session_opts["mcp_servers"] = _main_mcp_servers

            # Custom Agents (グローバル定義)
            # 明示設定 (config.custom_agents_config) を最優先し、
            # `.github/agents/*.agent.md` から読み込んだファイルベース定義をマージする。
            # 同名 (name) がある場合は明示設定を優先し、ファイル側を破棄する。
            try:
                from .agent_loader import (
                    load_agent_definitions,
                    merge_with_explicit,
                )
            except ImportError:  # pragma: no cover
                from agent_loader import (  # type: ignore[no-redef]
                    load_agent_definitions,
                    merge_with_explicit,
                )
            _explicit = copy.deepcopy(self.config.custom_agents_config or [])
            _agents_dir = Path(__file__).resolve().parent.parent / ".github" / "agents"
            _file_based = load_agent_definitions(_agents_dir)
            custom_agents: List[Dict[str, Any]] = merge_with_explicit(
                _explicit, _file_based
            )

            # additional_prompt をグローバル定義の各 agent の prompt に追記
            if self.config.additional_prompt:
                suffix = self.config.additional_prompt
                for agent_def in custom_agents:
                    existing = agent_def.get("prompt", "")
                    if existing:
                        agent_def["prompt"] = existing + "\n\n" + suffix
                    else:
                        agent_def["prompt"] = suffix

            # ステップ固有 Custom Agent を先頭に追加し、agent で pre-select
            if custom_agent:
                # グローバル定義に同名がなければ最小定義を追加（fallback）
                existing_names = {a.get("name") for a in custom_agents}
                if custom_agent not in existing_names:
                    # Wave 4: fallback 発生時に警告を出力し、未定義 Agent を可観測にする。
                    # Custom Agent 定義が .github/agents/{custom_agent}.agent.md に存在するか確認し、
                    # 不足している場合は agent-common-preamble Skill の参照を促すこと。
                    self.console.warning(
                        f"Custom Agent '{custom_agent}' の定義が見つかりませんでした。"
                        f" 最小定義 (fallback) で実行します。\n"
                        f"  → .github/agents/{custom_agent}.agent.md を作成し、"
                        f"agent-common-preamble Skill を参照することを推奨します。"
                    )
                    base_prompt = (
                        f"You are {custom_agent}.\n\n"
                        f"# 参照: agent-common-preamble\n"
                        f"作業開始時は .github/skills/planning/agent-common-preamble/SKILL.md を参照し、"
                        f"共通ルールを確認してください。"
                    )
                    if self.config.additional_prompt:
                        base_prompt = base_prompt + "\n\n" + self.config.additional_prompt
                    custom_agents.insert(
                        0,
                        {
                            "name": custom_agent,
                            "display_name": custom_agent,
                            "description": f"Custom agent: {custom_agent}",
                            "tools": ["*"],
                            "prompt": base_prompt,
                        },
                    )
                session_opts["agent"] = custom_agent

            if custom_agents:
                session_opts["custom_agents"] = custom_agents

            # Phase 2 (Resume): メインセッションに決定論的 session_id を付与する。
            # 既存値（呼び出し元が明示指定したケース）は尊重する。
            if not session_opts.get("session_id"):
                session_opts["session_id"] = self._make_step_session_id(step_id)

            # Phase 3 (Resume): resume_state に同 step が running/failed として残っている場合、
            # 同じ session_id で resume_session() を試みる。失敗時は新規 create_session に
            # フォールバックする（セッション形式の不整合や SDK 側削除に耐えるため）。
            session = await self._create_or_resume_main_session(
                client=client,
                session_opts=session_opts,
                step_id=step_id,
            )

            # イベント購読 (常に購読 — Console 側で出力レベルを制御)
            session.on(self._handle_session_event)

            # ストリーム表示の開始マーカー
            if self.console.show_stream:
                self.console.stream_start(step_id)

            # フェーズ総数を動的算出
            # Phase 0 (事前 QA): auto_qa かつ AQOD でない場合
            _is_aqod_workflow = (
                workflow_id == "aqod"
                or (
                    custom_agent == "QA-DocConsistency"
                    and "original-docs-questionnaire" in (prompt or "")
                )
            )
            _is_akm_workflow = (workflow_id == "akm")

            # 事前 QA のスキップ判定:
            #   AKM: 事前 QA を実行（メインタスクに pre_qa_context を注入）
            #   AQOD: 事前 QA は引き続きスキップ（ワークフロー本体が事後の整合性チェック仕様のため）
            _skip_pre_qa = _is_aqod_workflow

            _run_pre_qa = (
                self.config.auto_qa
                and not _skip_pre_qa
            )

            # 事後 QA (post-QA モード) は廃止されました。
            # 旧 qa_phase="post"/"both"、aqod_post_qa_enabled は削除済み。
            total_phases = 1  # Phase 1: メインタスク
            if _run_pre_qa:
                total_phases += 1
            if self.config.auto_contents_review:
                total_phases += 1
            _si_scope = self.config.self_improve_scope
            _step_si_allowed = _si_scope in ("", "step")
            if self.config.auto_self_improve and not self.config.self_improve_skip and _step_si_allowed:
                total_phases += 1
            current_phase = 0

            # final_message に渡す最終応答テキスト（各 Phase 完了後に非空なら上書き）
            final_response_text: str = ""

            # Phase 0: 事前 QA（_run_pre_qa=True の場合）
            pre_qa_context = ""
            if _run_pre_qa:
                current_phase += 1
                pre_qa_context = await self._run_pre_execution_qa(
                    session=session,
                    client=client,
                    step_id=step_id,
                    original_prompt=prompt,
                    custom_agent=custom_agent,
                    workflow_id=workflow_id,
                    current_phase=current_phase,
                    total_phases=total_phases,
                )

            # Phase 1: メインタスク
            current_phase += 1
            phase1_start = time.time()
            self.console.step_phase_start(step_id, current_phase, total_phases, "メインタスク")
            # 事前 QA の結果をプロンプト先頭に注入
            if pre_qa_context:
                _injected_prompt = (
                    "## 事前確認済みの前提条件・補足情報\n\n"
                    f"{pre_qa_context}\n\n"
                    "## メインタスク\n\n"
                    f"{prompt}"
                )
            else:
                _injected_prompt = prompt
            main_response = await session.send_and_wait(_injected_prompt, timeout=self.config.timeout_seconds)
            main_output = _extract_text(main_response)
            if main_output and main_output.strip():
                final_response_text = main_output
            self.console.step_phase_end(
                step_id, current_phase, total_phases, "メインタスク",
                elapsed=time.time() - phase1_start,
            )

            # Phase 2 (post-QA / 事後 QA) は廃止されました。
            # 旧 qa_phase="post"/"both" / aqod_post_qa_enabled / --aqod-post-qa は削除済み。

            # Phase 3: 敵対的レビュー（auto_contents_review=True の場合）
            if self.config.auto_contents_review:
                current_phase += 1
                phase3_start = time.time()
                self.console.step_phase_start(step_id, current_phase, total_phases, "敵対的レビュー")
                _review_model = self.config.get_review_model()
                _use_review_sub_session = self._should_use_review_sub_session(_review_model)
                _review_session = None
                try:
                    _effective_review_session = session
                    _effective_review_prompt = REVIEW_PROMPT
                    if _use_review_sub_session:
                        self._log_sub_session_reason(
                            step_id, "Review",
                            qa_model=_review_model,
                        )
                        _review_session = await _create_session_with_auto_reasoning_fallback(
                            client,
                            self._build_sub_session_opts(
                                _review_model,
                                step_id=step_id,
                                suffix="review",
                            ),
                        )
                        _review_session.on(self._handle_session_event)
                        self._sub_sessions_created += 1
                        _max_context_chars = self._get_context_injection_max_chars()
                        _review_context = _truncate_context(main_output or "", _max_context_chars)
                        _effective_review_prompt = (
                            "以下は同一ステップのメインタスク出力です。"
                            "この内容を前提としてレビューしてください。\n\n"
                            f"=== メインタスク出力（最大{_max_context_chars:,}文字） ===\n"
                            f"{_review_context}\n"
                            "=== メインタスク出力ここまで ===\n\n"
                            f"{REVIEW_PROMPT}"
                        )
                        _effective_review_session = _review_session
                    else:
                        self._log_main_session_reuse(step_id, "Review")

                    # 1回目: 敵対的レビュー実行
                    review_response = await _effective_review_session.send_and_wait(
                        _effective_review_prompt, timeout=self.config.timeout_seconds
                    )
                    review_content = _extract_text(review_response)
                    self.console.review_result(review_content)

                    # 初回 PASS 判定
                    if not _is_review_fail(review_content):
                        self.console.status(
                            "✅ 敵対的レビュー PASS（初回） — 再レビュー不要"
                        )
                        self.console.step_phase_end(
                            step_id, current_phase, total_phases, "敵対的レビュー",
                            elapsed=time.time() - phase3_start, result="PASS",
                        )
                    else:
                        # 再レビューサイクル（最大2回）
                        review_passed = False
                        for cycle in range(1, 3):  # cycle 1, 2
                            self.console.status(
                                f"❌ 敵対的レビュー FAIL — 再レビューサイクル {cycle}/2 を実行"
                            )
                            # FAIL 時: メイン成果物改善（設定有効時）
                            if self.config.apply_review_improvements_to_main:
                                _phase3_result = await self._apply_main_artifact_improvements(
                                    session=session,
                                    step_id=step_id,
                                    title=title,
                                    workflow_id=workflow_id,
                                    custom_agent=custom_agent,
                                    original_prompt=prompt,
                                    main_output=main_output or "",
                                    source_phase="Phase 3 Adversarial Review",
                                    improvement_context=review_content,
                                    timeout=self.config.timeout_seconds,
                                )
                                if _phase3_result and _phase3_result.strip():
                                    final_response_text = _phase3_result
                                self._check_diff_after_improvement(
                                    step_id, "Phase 3 Adversarial Review"
                                )
                            recheck_prompt = ADVERSARIAL_RECHECK_PROMPT.format(cycle=cycle)
                            recheck_response = await _effective_review_session.send_and_wait(
                                recheck_prompt, timeout=self.config.timeout_seconds
                            )
                            review_content = _extract_text(recheck_response)
                            self.console.review_result(review_content)

                            if not _is_review_fail(review_content):
                                self.console.status(
                                    f"✅ 敵対的レビュー PASS（再レビューサイクル {cycle}/2 後）"
                                )
                                self.console.step_phase_end(
                                    step_id, current_phase, total_phases, "敵対的レビュー",
                                    elapsed=time.time() - phase3_start, result="PASS",
                                )
                                review_passed = True
                                break

                        if not review_passed:
                            self.console.step_phase_end(
                                step_id, current_phase, total_phases, "敵対的レビュー",
                                elapsed=time.time() - phase3_start, result="FAIL",
                            )
                            self.console.status(
                                "⚠️ 最大再レビューサイクル到達 — Critical が残存しています"
                            )
                            # Critical が残存している場合はステップ失敗として扱う
                            raise RuntimeError(
                                "Critical issues remain after maximum adversarial review cycles."
                            )
                finally:
                    if _review_session is not None:
                        await _review_session.disconnect()

            # Phase 4: 自己改善ループ（auto_self_improve=True かつ skip でない場合）
            # scope が "" または "step" の場合のみ実行。"workflow" / "disabled" の場合はスキップ。
            _si_scope = self.config.self_improve_scope
            _step_si_allowed = _si_scope in ("", "step")
            if self.config.auto_self_improve and not self.config.self_improve_skip and not _step_si_allowed:
                self.console.event(
                    f"  ⏭️ [{step_id}] Phase 4 自己改善ループをスキップ "
                    f"(self_improve_scope={_si_scope!r} — step-level は実行しない)"
                )
            if self.config.auto_self_improve and not self.config.self_improve_skip and _step_si_allowed:
                current_phase += 1
                phase4_start = time.time()
                self.console.step_phase_start(step_id, current_phase, total_phases, "自己改善ループ")

                # _work_dir は run_id + ステップ ID で分離されたパスを使用する（並列安全性）
                # run_id は run_step() 冒頭で正規化済みのため _safe_run_id() の再呼び出しは不要。
                _work_dir = Path(f"work/self-improve/run-{self.config.run_id}/step-{step_id}")
                _max_iter = self.config.self_improve_max_iterations

                for _iteration in range(1, _max_iter + 1):
                    _iter_start = time.time()

                    # Phase 4a: コードベーススキャン（subprocess）
                    self.console.event(
                        f"  🔍 [{step_id}] 自己改善 {_iteration}/{_max_iter}: コードベーススキャン中..."
                    )
                    _step_outputs = _resolve_step_output_paths(self.workflow, step_id)
                    _workflow_default = _SI_SCOPE_DEFAULTS.get(self.workflow.id, "")
                    _scan = scan_codebase(
                        target_scope=self.config.self_improve_target_scope,
                        step_output_paths=_step_outputs,
                        workflow_default=_workflow_default,
                    )
                    _before_score = _scan["quality_score"]
                    self.console.event(
                        f"  📊 [{step_id}] quality_score: {_before_score} "
                        f"(lint={_scan['summary']['lint_errors']}, "
                        f"test_fail={_scan['summary']['test_failures']}, "
                        f"coverage={_scan['summary']['coverage_pct']:.1f}%)"
                    )

                    # スコアが十分高く問題なし → 改善不要で終了
                    if _before_score >= DEFAULT_QUALITY_THRESHOLD and not _scan["summary"]["test_failures"]:
                        self.console.status(
                            f"✅ 自己改善ループ: quality_score={_before_score} ≥ {DEFAULT_QUALITY_THRESHOLD} — 改善不要"
                        )
                        break

                    # Phase 4b: LLM 統合評価 + 改善計画生成
                    _previous_learning = get_learning_summary(_work_dir, _iteration - 1)
                    _scan_prompt = SELF_IMPROVE_SCAN_PROMPT.format(
                        target_scope=self.config.self_improve_target_scope or "全体",
                        scan_output=_scan["raw_output"][:_MAX_SCAN_OUTPUT_LENGTH],
                    )
                    _scan_response = await session.send_and_wait(
                        _scan_prompt, timeout=self.config.timeout_seconds
                    )
                    _scan_content = _extract_text(_scan_response)

                    _plan_prompt = SELF_IMPROVE_PLAN_PROMPT.format(
                        iteration=_iteration,
                        scan_result_json=_scan_content[:_MAX_PLAN_SCAN_LENGTH],
                        previous_learning=_previous_learning[:_MAX_LEARNING_SUMMARY_LENGTH] if _previous_learning else "(初回)",
                    )
                    _plan_response = await session.send_and_wait(
                        _plan_prompt, timeout=self.config.timeout_seconds
                    )
                    _plan_content = _extract_text(_plan_response)

                    if "IMPROVEMENT_NOT_NEEDED" in _plan_content:
                        self.console.status(
                            "✅ 自己改善ループ: 改善不要と判定されました"
                        )
                        break

                    # Phase 4c: セッション内で改善実行
                    # 計画内容（_plan_content）を実行指示としてセッションに送信する
                    self.console.event(
                        f"  🔧 [{step_id}] 自己改善 {_iteration}/{_max_iter}: 改善実行中..."
                    )
                    if self.config.apply_self_improve_to_main:
                        _phase4_result = await self._apply_main_artifact_improvements(
                            session=session,
                            step_id=step_id,
                            title=title,
                            workflow_id=workflow_id,
                            custom_agent=custom_agent,
                            original_prompt=prompt,
                            main_output=main_output or "",
                            source_phase=f"Phase 4 Self-Improve iteration {_iteration}",
                            improvement_context=_plan_content[:_MAX_PLAN_SCAN_LENGTH],
                            timeout=self.config.timeout_seconds,
                        )
                        if _phase4_result and _phase4_result.strip():
                            final_response_text = _phase4_result
                        self._check_diff_after_improvement(
                            step_id, f"Phase 4 Self-Improve iteration {_iteration}"
                        )
                    else:
                        _exec_prompt = (
                            f"以下の改善計画を実行してください。\n\n{_plan_content[:_MAX_PLAN_SCAN_LENGTH]}"
                        )
                        await session.send_and_wait(
                            _exec_prompt, timeout=self.config.timeout_seconds
                        )

                    # Phase 4d: 改善後検証（Verification Loop §10.1 準拠）
                    _after_scan = scan_codebase(
                        target_scope=self.config.self_improve_target_scope,
                        step_output_paths=_step_outputs,
                        workflow_default=_workflow_default,
                    )
                    _verify_prompt = SELF_IMPROVE_VERIFY_PROMPT.format(
                        before_score=_before_score,
                        after_scan_output=_after_scan["raw_output"][:_MAX_SCAN_OUTPUT_LENGTH],
                    )
                    _verify_response = await session.send_and_wait(
                        _verify_prompt, timeout=self.config.timeout_seconds
                    )
                    _verify_content = _extract_text(_verify_response)

                    # 検証結果のパース: LLM JSON を解析し、取得できない場合は scan 結果で補完
                    _after_score = _after_scan["quality_score"]
                    _degraded = (
                        _after_score < _before_score
                        or _after_scan["summary"]["test_failures"] > _scan["summary"]["test_failures"]
                    )

                    # JSON ブロックを抽出してパース
                    _phases_from_llm: Dict[str, str] = {}
                    _json_match = _extract_json_block(_verify_content)
                    if _json_match:
                        try:
                            _parsed = json.loads(_json_match)
                            _after_score = int(_parsed.get("after_quality_score", _after_score))
                            _degraded = bool(_parsed.get("degraded", _degraded))
                            _phases_from_llm = _parsed.get("verification_phases", {})
                        except (json.JSONDecodeError, ValueError, TypeError):
                            pass  # パース失敗時は scan 結果ベースの値を使用

                    _verification: VerificationResult = {
                        "after_quality_score": _after_score,
                        "degraded": _degraded,
                        "verification_phases": {
                            "build": _phases_from_llm.get("build", "PASS"),
                            "lint": _phases_from_llm.get(
                                "lint", "PASS" if _after_scan["summary"]["lint_errors"] == 0 else "FAIL"
                            ),
                            "test": _phases_from_llm.get(
                                "test", "PASS" if _after_scan["summary"]["test_failures"] == 0 else "FAIL"
                            ),
                            "security": _phases_from_llm.get("security", "PASS"),
                            "diff": _phases_from_llm.get("diff", "SKIP"),
                        },
                        "overall": "FAIL" if _degraded else "PASS",
                        "notes": _verify_content[:LEARNING_SUMMARY_MAX_LENGTH],
                    }

                    # Phase 4e: 学習ログ記録
                    _record: ImprovementRecord = {
                        "iteration": _iteration,
                        "before_score": _before_score,
                        "after_score": _after_score,
                        "degraded": _degraded,
                        "plan_summary": _plan_content[:_MAX_PLAN_SCAN_LENGTH],
                        "verification": _verification,
                        "elapsed_seconds": time.time() - _iter_start,
                    }
                    record_learning(_work_dir, _iteration, _record)

                    self.console.event(
                        f"  📈 [{step_id}] 自己改善 {_iteration}/{_max_iter}: "
                        f"score {_before_score} → {_after_score} "
                        f"({'⚠️ デグレード' if _degraded else '✅ 改善'})"
                    )

                    # Phase 4f: デグレード検知 → 即時停止
                    if _degraded:
                        self.console.status(
                            f"⚠️ 自己改善ループ: デグレード検知 — イテレーション {_iteration} で停止"
                        )
                        break

                self.console.step_phase_end(
                    step_id, current_phase, total_phases, "自己改善ループ",
                    elapsed=time.time() - phase4_start,
                )

        except Exception as exc:
            self.console.error(f"Step.{step_id} 実行中にエラーが発生しました: {exc}")
            self.console.step_io_summary(step_id)
            elapsed = time.time() - start
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False
        finally:
            if session is not None:
                try:
                    await session.disconnect()
                except Exception as cleanup_exc:
                    self.console.warning(f"[cleanup] session.disconnect() failed: {cleanup_exc}")
            if client is not None:
                try:
                    await client.stop()
                except Exception as cleanup_exc:
                    self.console.warning(f"[cleanup] client.stop() failed: {cleanup_exc}")

        elapsed = time.time() - start
        self.console.step_io_summary(step_id)
        self.console.final_message(step_id, final_response_text or main_output or "")
        self.console.step_end(step_id, "success", elapsed=elapsed)
        return True

    # ------------------------------------------------------------------
    # 内部ヘルパー — SDK data 属性の安全取得
    # ------------------------------------------------------------------

    @staticmethod
    def _get(data: Any, *names: str, default: Any = "") -> Any:
        """data オブジェクトから属性を安全に取得する。

        SDK v0.2.2 Python では snake_case 属性名を使用するが、
        将来の変更に備え camelCase もフォールバックで試す。
        """
        if data is None:
            return default
        for name in names:
            val = getattr(data, name, None)
            if val is not None:
                return val
        return default

    # ------------------------------------------------------------------
    # 内部イベントハンドラー
    # ------------------------------------------------------------------

    def _handle_session_event(self, event: Any) -> None:
        """CopilotSession のイベントを受け取り Console に出力する。

        SDK v0.2.2 のイベントタイプ一覧:
        https://github.com/github/copilot-sdk/blob/main/docs/features/streaming-events.md
        """
        # SDK v0.2.2: event.type は SessionEventType enum、.value で文字列取得
        etype = getattr(getattr(event, "type", None), "value", "") or ""
        data = getattr(event, "data", None)
        step_id = getattr(self, "_current_step_id", "")
        _get = self._get

        # ディスパッチテーブルを使わず if-elif で処理する。
        # etype の出現頻度が高いものを上に配置。

        # --- ストリーム系 (高頻度、show_stream ガード) ---
        if etype == "assistant.message_delta":
            # SDK 仕様では deltaContent (camelCase) のみ。Python SDK の snake_case 変換に備え delta_content も受ける。
            token = _get(data, "delta_content", "deltaContent") or ""
            if token:
                self.console.stream_token(step_id, token)
            return

        if etype == "assistant.streaming_delta":
            # バイト進捗 — 表示不要
            return

        # --- ツール実行 (高頻度) ---
        if etype == "tool.execution_start":
            tool_name = extract_tool_name_from_event(event) or _get(data, "tool_name", "toolName", "name", default="unknown")
            args = _get(data, "arguments", default=None)

            # report_intent ツールは Thinking として表示する（通常のアクション表示をスキップ）
            if tool_name == "report_intent":
                if step_id:
                    self.console.increment_tool_count(step_id)
                intent_text = ""
                if isinstance(args, dict):
                    intent_text = (
                        args.get("intent")
                        or args.get("message")
                        or args.get("text")
                        or args.get("description")
                        or args.get("content")
                        or ""
                    )
                    if not intent_text:
                        # フォールバック: 最初の文字列値を使う
                        for v in args.values():
                            if v and isinstance(v, str):
                                intent_text = v
                                break
                elif isinstance(args, str):
                    intent_text = args
                if intent_text:
                    self.console.thinking(step_id, str(intent_text))
                return

            # task ツールは SDK 内部制御ツールのため表示を簡潔にする
            if tool_name == "task":
                if step_id:
                    self.console.increment_tool_count(step_id)
                # verbose 時のみ表示、それ以外はスキップ
                if self.console.verbose:
                    self.console.event(f"  🔧 [{step_id}] task (internal)")
                return

            action_name, detail = self._build_action_display(tool_name, args)
            if args and isinstance(args, dict):
                # 既存のファイル I/O 追跡ロジックは維持
                self._track_tool_files(step_id, tool_name, args)
            workiq_tool_name = extract_workiq_tool_name_from_event(event)
            if workiq_tool_name:
                self._workiq_called_tools.append(workiq_tool_name)
                if not self._workiq_tool_called:
                    self._workiq_tool_called = True
                    self.console.status(
                        f"🔍 Work IQ ツール '{workiq_tool_name}' が呼び出されました"
                    )
            self.console.action_start(step_id, action_name, detail)
            return

        if etype == "tool.execution_complete":
            success = _get(data, "success", default=False)
            error = _get(data, "error", default=None)
            if success:
                result_text = self._build_tool_result_text(data)
                if result_text:
                    self.console.action_result(step_id, result_text)
            else:
                error_msg = ""
                if error:
                    error_msg = _get(error, "message", default=str(error))
                self.console.tool_result(step_id, False, error_msg=error_msg)
            return

        if etype == "tool.execution_partial_result":
            output = _get(data, "partial_output", "partialOutput") or ""
            if output:
                self.console.tool_output(step_id, output)
            return

        if etype == "tool.execution_progress":
            msg = _get(data, "progress_message", "progressMessage") or ""
            if msg:
                self.console.event(f"  ⏳ [{step_id}] {msg}")
            return

        # --- アシスタント応答 ---
        if etype == "assistant.intent":
            def _normalize_intent_candidate(value: Any) -> str:
                if value is None:
                    return ""
                if isinstance(value, str):
                    return value
                return str(value)

            def _collect_detail_values(details: Any) -> List[str]:
                if details is None:
                    return []
                if isinstance(details, dict):
                    raw_values = details.values()
                elif isinstance(details, (list, tuple, set)):
                    raw_values = details
                else:
                    raw_values = [details]

                normalized_values: List[str] = []
                for raw_value in raw_values:
                    text_value = _normalize_intent_candidate(raw_value)
                    if text_value == "":
                        continue
                    normalized_values.append(text_value)
                return normalized_values

            def _sanitize_diag_value(key: str, value: Any) -> str:
                def _truncate_diag_text(text: str) -> str:
                    if len(text) > _INTENT_DIAG_MAX_VALUE_LENGTH:
                        return f"{text[:_INTENT_DIAG_MAX_VALUE_LENGTH]}...(truncated)"
                    return text

                key_l = str(key).lower()
                if any(t in key_l for t in _INTENT_DIAG_SENSITIVE_TOKENS):
                    return "<masked>"

                def _sanitize_nested(obj: Any) -> Any:
                    if isinstance(obj, dict):
                        sanitized = {}
                        for nested_k, nested_v in obj.items():
                            nested_k_str = str(nested_k)
                            nested_k_l = nested_k_str.lower()
                            if any(t in nested_k_l for t in _INTENT_DIAG_SENSITIVE_TOKENS):
                                sanitized[nested_k_str] = "<masked>"
                            else:
                                sanitized[nested_k_str] = _sanitize_nested(nested_v)
                        return sanitized
                    if isinstance(obj, (list, tuple, set)):
                        return [_sanitize_nested(v) for v in obj]
                    if obj is None:
                        return None
                    text_obj = str(obj)
                    return _truncate_diag_text(text_obj)

                try:
                    safe_value = _sanitize_nested(value) if key_l == "details" else value
                    text = repr(safe_value)
                except (TypeError, ValueError):
                    return "<error>"

                return _truncate_diag_text(text)

            # 診断ログ: intent イベントの data 構造を確認する（verbose 時のみ）
            is_verbose = self.config.verbosity >= 3
            if is_verbose and data is not None:
                _diag_attrs = {}
                _diag_reasons: List[str] = []
                _diag_items = None

                if isinstance(data, dict):
                    _diag_items = data.items()
                    _diag_reasons.append("source=dict")
                else:
                    try:
                        data_dict = vars(data)
                    except TypeError as exc:
                        data_dict = None
                        _diag_reasons.append(
                            f"vars_failed={type(exc).__name__}"
                        )
                    if isinstance(data_dict, dict):
                        _diag_items = data_dict.items()
                        _diag_reasons.append("source=vars")
                    else:
                        _fallback_attrs = {}
                        _fallback_errors = {}
                        for _a in dir(data):
                            if str(_a).startswith("_"):
                                continue
                            try:
                                _fallback_attrs[_a] = getattr(data, _a)
                            except Exception as exc:
                                _fallback_errors[_a] = f"{type(exc).__name__}"
                        _diag_items = _fallback_attrs.items()
                        _diag_reasons.append("source=dir/getattr")
                        if _fallback_errors:
                            _diag_reasons.append(
                                f"getattr_failed={len(_fallback_errors)}"
                            )

                if _diag_items is not None:
                    for _a, _v in _diag_items:
                        attr_name = str(_a)
                        if attr_name.startswith("_"):
                            continue
                        if len(_diag_attrs) >= _INTENT_DIAG_MAX_ATTRS:
                            _diag_attrs["__truncated__"] = "<max-attrs-reached>"
                            break
                        if attr_name in _INTENT_DIAG_ALLOWED_KEYS:
                            _diag_attrs[attr_name] = _sanitize_diag_value(attr_name, _v)
                        else:
                            _diag_attrs[attr_name] = "<omitted>"

                if not _diag_attrs:
                    _diag_reasons.append("no_public_attrs_extracted")
                self.console.event(
                    "🔍 [DIAG] assistant.intent data attrs: "
                    f"{_diag_attrs} "
                    f"(reasons: {', '.join(_diag_reasons) if _diag_reasons else 'none'})"
                )

            intent_text = ""
            for field_name in ("intent", "description", "text", "content", "message"):
                candidate_text = _normalize_intent_candidate(_get(data, field_name))
                if candidate_text:
                    intent_text = candidate_text
                    break

            if not intent_text:
                kind = _normalize_intent_candidate(_get(data, "kind"))
                if kind:
                    detail_values = _collect_detail_values(_get(data, "details"))
                    intent_text = (
                        f"{kind}: {', '.join(detail_values)}"
                        if detail_values
                        else kind
                    )

            if intent_text:
                self.console.thinking(step_id, str(intent_text))
            elif is_verbose:
                self.console.event(
                    f"⚠️ [DIAG] assistant.intent fired but no text extracted. "
                    f"data type={type(data).__name__}"
                )
            return

        if etype == "assistant.turn_start":
            turn_id = _get(data, "turn_id", "turnId") or ""
            self.console.turn_start(step_id, turn_id)
            return

        if etype == "assistant.turn_end":
            self.console.stream_end(step_id)
            self.console.turn_end(step_id)
            return

        if etype == "assistant.message":
            content = _get(data, "content") or ""
            tool_reqs = _get(data, "tool_requests", "toolRequests", default=None) or []
            self.console.assistant_message(step_id, len(content), len(tool_reqs))
            return

        if etype == "assistant.reasoning":
            content = _get(data, "content") or ""
            self.console.reasoning_complete(step_id, content)
            return

        if etype == "assistant.reasoning_delta":
            token = _get(data, "delta_content", "deltaContent") or ""
            if token:
                self.console.reasoning_token(step_id, token)
            return

        if etype == "assistant.usage":
            model = _get(data, "model") or "?"
            inp = _get(data, "input_tokens", "inputTokens", default=0) or 0
            out = _get(data, "output_tokens", "outputTokens", default=0) or 0
            dur = _get(data, "duration", default=None)
            self.console.usage(step_id, model, int(inp), int(out),
                               duration_ms=int(dur) if dur else None)
            return

        # --- サブエージェント / スキル ---
        if etype == "subagent.started":
            name = _get(data, "agent_display_name", "agentDisplayName") or etype
            self.console.subagent_started(step_id, name)
            return

        if etype == "subagent.completed":
            name = _get(data, "agent_display_name", "agentDisplayName") or etype
            self.console.subagent_completed(step_id, name)
            return

        if etype == "subagent.failed":
            name = _get(data, "agent_display_name", "agentDisplayName") or etype
            err = _get(data, "error") or ""
            self.console.subagent_failed(step_id, name, error=str(err))
            return

        if etype == "subagent.selected":
            name = _get(data, "agent_display_name", "agentDisplayName") or ""
            self.console.subagent_selected(step_id, name)
            return

        if etype == "subagent.deselected":
            self.console.event(f"🤖 [{step_id}] Agent 解除")
            return

        if etype == "skill.invoked":
            name = _get(data, "name") or ""
            self.console.skill_invoked(step_id, name)
            return

        # --- セッション ---
        if etype == "session.error":
            err_type = _get(data, "error_type", "errorType") or ""
            message = _get(data, "message") or ""
            self.console.session_error(err_type, message)
            return

        if etype == "session.log":
            level = _get(data, "level") or "info"
            message = _get(data, "message") or ""
            if message:
                self.console.cli_log(step_id, f"[{level}] {message}")
            return

        if etype == "session.usage_info":
            limit = int(_get(data, "token_limit", "tokenLimit", default=0) or 0)
            current = int(_get(data, "current_tokens", "currentTokens", default=0) or 0)
            msgs = int(_get(data, "messages_length", "messagesLength", default=0) or 0)
            self.console.context_usage(step_id, current, limit, msgs)
            return

        if etype == "session.compaction_start":
            self.console.compaction(step_id, "start")
            return

        if etype == "session.compaction_complete":
            pre = int(_get(data, "pre_compaction_tokens", "preCompactionTokens", default=0) or 0)
            post = int(_get(data, "post_compaction_tokens", "postCompactionTokens", default=0) or 0)
            self.console.compaction(step_id, "complete", pre_tokens=pre, post_tokens=post)
            return

        if etype == "session.task_complete":
            summary = _get(data, "summary") or ""
            self.console.task_complete(step_id, summary=str(summary))
            return

        if etype == "session.shutdown":
            changes = _get(data, "code_changes", "codeChanges", default=None)
            reqs = int(_get(data, "total_premium_requests", "totalPremiumRequests", default=0) or 0)
            dur_ms = int(_get(data, "total_api_duration_ms", "totalApiDurationMs", default=0) or 0)
            lines_added = int(_get(changes, "lines_added", "linesAdded", default=0) or 0) if changes else 0
            lines_removed = int(_get(changes, "lines_removed", "linesRemoved", default=0) or 0) if changes else 0
            files_mod = int(_get(changes, "files_modified", "filesModified", default=0) or 0) if changes else 0
            self.console.shutdown_stats(step_id, lines_added, lines_removed,
                                        files_mod, reqs, dur_ms)
            return

        # --- パーミッション ---
        if etype == "permission.requested":
            req = _get(data, "permission_request", "permissionRequest", default=None)
            kind_obj = _get(req, "kind", default="") if req else ""
            kind_str = getattr(kind_obj, "value", str(kind_obj)) if kind_obj else ""
            self.console.permission(step_id, kind_str, resolved=False)
            return

        if etype == "permission.completed":
            result_obj = _get(data, "result", default=None)
            kind_str = _get(result_obj, "kind", default="") if result_obj else ""
            kind_val = getattr(kind_str, "value", str(kind_str)) if kind_str else ""
            self.console.permission(step_id, "", resolved=True, result=kind_val)
            return

        if etype == "session.mcp_servers_loaded":
            servers = _get(data, "servers", default=[])
            for srv in servers:
                name = _get(srv, "name", default="?")
                status_obj = _get(srv, "status", default=None)
                status = getattr(status_obj, "value", str(status_obj)) if status_obj else "unknown"
                error = _get(srv, "error", default=None)
                if status == "connected":
                    self.console.status(f"✅ MCP サーバー '{name}' 接続成功")
                elif status in ("failed", "needs-auth"):
                    self.console.warning(
                        f"❌ MCP サーバー '{name}' 接続失敗 (status={status})"
                        + (f": {error}" if error else "")
                    )
                    if name == WORKIQ_MCP_SERVER_NAME:
                        self._workiq_mcp_connection_failed = True
                else:
                    self.console.event(f"ℹ️ MCP '{name}' status={status}")
            return

        if etype == "session.mcp_server_status_changed":
            server_name = _get(data, "server_name", "serverName", default="?")
            status_obj = _get(data, "status", default=None)
            status = getattr(status_obj, "value", str(status_obj)) if status_obj else "unknown"
            if status in ("failed", "needs-auth") and server_name == WORKIQ_MCP_SERVER_NAME:
                self._workiq_mcp_connection_failed = True
                self.console.warning(f"❌ Work IQ MCP サーバー接続状態変更: {status}")
            else:
                self.console.event(f"MCP '{server_name}' → {status}")
            return

        # --- その他 (既知だが詳細表示不要なイベント) ---
        if etype in (
            "session.idle",
            "session.title_changed",
            "session.context_changed",
            "user.message",
            "system.message",
            "tool.user_requested",
            "abort",
            "command.queued",
            "command.completed",
            "user_input.requested",
            "user_input.completed",
            "elicitation.requested",
            "elicitation.completed",
            "external_tool.requested",
            "external_tool.completed",
            "exit_plan_mode.requested",
            "exit_plan_mode.completed",
            # SDK 内部イベント: エンドユーザーへの付加価値がないため抑制
            "hook.start",
            "hook.end",
            "pending_messages.modified",
            "session.tools_updated",
        ):
            return

        # 未知のイベントタイプ: 将来の SDK 更新に備え verbose で表示
        self.console.event(f"[{step_id}] event: {etype}")


# ------------------------------------------------------------------
# 内部ヘルパー
# ------------------------------------------------------------------


def _blocking_stdin_read() -> str:
    """スレッドプール内で実行するブロッキング stdin 読み取り。"""
    try:
        return sys.stdin.readline().rstrip("\n")
    except (EOFError, OSError):
        return ""


async def _read_stdin_async(
    prompt_msg: str,
    console: Any,
    timeout: float = 300.0,
) -> str:
    """asyncio イベントループをブロックせずに stdin から1行読み取る。

    - 並列ステップ間の競合を asyncio.Lock で排他制御
    - stdin が非対話的（パイプ等）の場合はスキップしてデフォルト値を返す
    - タイムアウト付きで無限ブロックを防止
    - ブロッキング I/O は run_in_executor でスレッドプールに委譲
    """
    # stdin が非対話的（パイプ、リダイレクト等）の場合はスキップ
    if not sys.stdin.isatty():
        console.warning(
            f"{prompt_msg}\n"
            "  → stdin が非対話モードのため、デフォルト回答を自動適用します。"
        )
        return ""

    async with _get_stdin_lock():
        # 他のステップのストリーム出力と視覚的に分離
        _separator = "─" * 50
        print(flush=True)
        print(f"{timestamp_prefix()} {_separator}", flush=True)
        console.warning(prompt_msg)
        print(f"{timestamp_prefix()} {_separator}", flush=True)

        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _blocking_stdin_read),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            console.warning(
                f"入力タイムアウト ({timeout:.0f}s)。デフォルト回答を自動適用します。"
            )
            result = ""

        return result


async def _read_stdin_multiline(
    prompt_msg: str,
    console: Any,
    timeout: float = 300.0,
) -> str:
    """複数行の回答入力を受け付ける。

    入力形式: "番号: 選択肢ラベル" を1行1問で入力。
    空行で入力終了。stdin が非対話的な場合はデフォルト回答を自動適用。

    Args:
        prompt_msg: ユーザーへの入力促進メッセージ。
        console: Console インスタンス。
        timeout: タイムアウト秒数（デフォルト: 300 秒）。

    Returns:
        入力された複数行テキスト（空 = デフォルト回答採用）。
    """
    # stdin が非対話的（パイプ、リダイレクト等）の場合はスキップ
    if not sys.stdin.isatty():
        console.warning(
            f"{prompt_msg}\n"
            "  → stdin が非対話モードのため、デフォルト回答を自動適用します。"
        )
        return ""

    async with _get_stdin_lock():
        # 他のステップのストリーム出力と視覚的に分離
        print(flush=True)
        print(f"{timestamp_prefix()} {'─' * 50}", flush=True)
        console.warning(prompt_msg)
        print(f"{timestamp_prefix()} {'─' * 50}", flush=True)

        collected: List[str] = []
        loop = asyncio.get_running_loop()
        while True:
            try:
                line = await asyncio.wait_for(
                    loop.run_in_executor(None, _blocking_stdin_read),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                console.warning(
                    f"入力タイムアウト ({timeout:.0f}s)。デフォルト回答を自動適用します。"
                )
                return ""

            # 空行で入力終了
            if not line.strip():
                break
            # "skip" で即座にデフォルト採用
            if line.strip().lower() == "skip":
                return ""
            collected.append(line)

        return "\n".join(collected)


def _extract_text(response: Any) -> str:
    """SDK レスポンスからテキスト部分を取り出す。

    SDK v0.2.2: send_and_wait() は SessionEvent | None を返す。
    テキストは event.data.content に格納される。
    """
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    # SDK v0.2.2: SessionEvent.data.content
    data = getattr(response, "data", None)
    if data is not None:
        for attr in ("content", "message"):
            val = getattr(data, attr, None)
            if val is not None:
                return str(val)
    # フォールバック: response 直接の属性
    for attr in ("content", "text", "message"):
        val = getattr(response, attr, None)
        if val is not None:
            return str(val)
    # 未知の型の場合はフォールバックで空文字を返す（repr 文字列の混入を防止）
    return ""


def _extract_json_block(text: str) -> Optional[str]:
    """テキストから最初の JSON オブジェクト（`{...}`）を抽出して返す。

    LLM の検証レスポンスに含まれる JSON を取り出すために使用する。
    ネストされたオブジェクトも正しく処理するために、文字の深さカウントを使用する。

    Returns:
        JSON 文字列（抽出できない場合は None）。
    """
    # ```json ... ``` フェンス内を先に探す（フェンスの開始 `{` から深さカウント）
    _fence_start = re.compile(r"```(?:json)?\s*\n?")
    m = _fence_start.search(text)
    search_text = text[m.end():] if m else text

    # `{` から始まる最初の JSON オブジェクトを深さカウントで抽出
    start = search_text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(search_text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return search_text[start : i + 1]
    return None
