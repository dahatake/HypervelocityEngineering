"""runner.py — StepRunner: 1 ステップを CopilotSession で実行する"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import re
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
    from .config import MODEL_AUTO_VALUE, SDKConfig, generate_run_id
    from .console import Console, _ACTION_DISPLAY, timestamp_prefix
    from .prompts import (
        QA_APPLY_PROMPT, REVIEW_PROMPT, ADVERSARIAL_RECHECK_PROMPT,
        QA_PROMPT_V2, QA_MERGE_SAVE_PROMPT, QA_CONSOLIDATE_PROMPT,
        SELF_IMPROVE_SCAN_PROMPT, SELF_IMPROVE_PLAN_PROMPT, SELF_IMPROVE_VERIFY_PROMPT,
    )
    from .qa_merger import QADocument, QAMerger
    from .self_improve import (
        scan_codebase, record_learning, get_learning_summary,
        ImprovementRecord, VerificationResult,
        DEFAULT_QUALITY_THRESHOLD, LEARNING_SUMMARY_MAX_LENGTH,
    )
    from .workiq import (
        is_workiq_available, build_workiq_mcp_config,
        query_workiq, enrich_prompt_with_workiq,
        get_workiq_prompt_template, save_workiq_result,
        query_workiq_per_question, format_workiq_draft_answers,
    )
except ImportError:
    from config import MODEL_AUTO_VALUE, SDKConfig, generate_run_id  # type: ignore[no-redef]
    from console import Console, _ACTION_DISPLAY, timestamp_prefix  # type: ignore[no-redef]
    from prompts import (  # type: ignore[no-redef]
        QA_APPLY_PROMPT, REVIEW_PROMPT, ADVERSARIAL_RECHECK_PROMPT,
        QA_PROMPT_V2, QA_MERGE_SAVE_PROMPT, QA_CONSOLIDATE_PROMPT,
        SELF_IMPROVE_SCAN_PROMPT, SELF_IMPROVE_PLAN_PROMPT, SELF_IMPROVE_VERIFY_PROMPT,
    )
    from qa_merger import QADocument, QAMerger  # type: ignore[no-redef]
    from self_improve import (  # type: ignore[no-redef]
        scan_codebase, record_learning, get_learning_summary,
        ImprovementRecord, VerificationResult,
        DEFAULT_QUALITY_THRESHOLD, LEARNING_SUMMARY_MAX_LENGTH,
    )
    from workiq import (  # type: ignore[no-redef]
        is_workiq_available, build_workiq_mcp_config,
        query_workiq, enrich_prompt_with_workiq,
        get_workiq_prompt_template, save_workiq_result,
        query_workiq_per_question, format_workiq_draft_answers,
    )

# Phase 4 プロンプト長の上限（長い出力を切り詰めてトークン消費を制御する）
_MAX_SCAN_OUTPUT_LENGTH: int = 8000
_MAX_PLAN_SCAN_LENGTH: int = 4000
_MAX_LEARNING_SUMMARY_LENGTH: int = 2000
_MAX_CONTEXT_INJECTION_LENGTH: int = 50_000
_ACTION_DETAIL_MAX_LENGTH: int = 120
_ACTION_RESULT_SINGLE_LINE_MAX_LENGTH: int = 100


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

# Work IQ ツール名
_WORKIQ_TOOL_NAMES: frozenset = frozenset({
    "search_emails", "search_messages", "search_meetings",
    "search_files", "search_people", "get_calendar", "ask",
})

class StepRunner:
    """1 ステップを CopilotSession で実行する。

    フロー (1ステップ内、メイン + 必要時サブセッション):
    ┌──────────────────────────────────────────────────┐
    │ CopilotSession (同一セッション = コンテキスト保持)   │
    │                                                    │
    │  Phase 1: session.send_and_wait(prompt)            │
    │    → Agent がメインタスク実行                        │
    │                                                    │
    │  [auto_qa=True の場合]                              │
    │  Phase 2a: session.send_and_wait(QA_PROMPT_V2)     │
    │    → Agent が構造化形式の質問票を生成                │
    │  Phase 2b: CLI stdin で複数行回答入力               │
    │    → "番号: 選択肢" 形式 / 空行で終了               │
    │    → skip/空 入力で既定値候補適用                    │
    │  Phase 2c: QA 回答マージ + qa/ ファイル永続化        │
    │    → QAMerger でパース → マージ → Markdown 生成     │
    │    → session.send_and_wait(QA_MERGE_SAVE_PROMPT)   │
    │       Agent がマージ済みファイルを qa/ に保存        │
    │    → session.send_and_wait(QA_CONSOLIDATE_PROMPT)  │
    │       Agent が統合ドキュメント(-consolidated.md)生成 │
    │    → 失敗時: QA_APPLY_PROMPT にフォールバック        │
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

    def __init__(self, config: SDKConfig, console: Console) -> None:
        self.config = config
        self.console = console
        self._workiq_tool_called = False
        self._workiq_mcp_connection_failed = False

    def _build_sub_session_opts(self, model: str) -> Dict[str, Any]:
        """レビュー/QA 用の別セッション構築オプションを生成する。

        メインセッションの custom_agent / custom_agents を除外した
        最小限のオプションセットを返す。MCP servers はツール利用のため引き継ぐ。
        """
        from copilot.session import PermissionHandler
        opts: Dict[str, Any] = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
        }
        # Auto 選択時は model 引数を省略し、GitHub 側の Auto model selection に委譲する。
        if model and model != MODEL_AUTO_VALUE:
            opts["model"] = model
        _mcp = dict(self.config.mcp_servers or {})

        # Work IQ MCP Server をサブセッションにも追加
        if self.config.workiq_enabled and is_workiq_available():
            _workiq_mcp = build_workiq_mcp_config(
                tenant_id=self.config.workiq_tenant_id,
            )
            for _k, _v in _workiq_mcp.items():
                if _k not in _mcp:
                    _mcp[_k] = _v

        if _mcp:
            opts["mcp_servers"] = _mcp
        return opts

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

        for key in ("command", "path", "filePath", "file_path", "query", "pattern", "url"):
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

    async def run_step(
        self,
        step_id: str,
        title: str,
        prompt: str,
        custom_agent: Optional[str] = None,
    ) -> bool:
        """ステップを実行する。

        Args:
            step_id: ステップ識別子（例: "1.1", "2.3"）
            title: ステップタイトル（表示用）
            prompt: メインタスクのプロンプト文字列
            custom_agent: 使用する Custom Agent 名（省略可）

        Returns:
            True: 成功, False: 失敗
        """
        start = time.time()
        self._workiq_tool_called = False
        self._workiq_mcp_connection_failed = False

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
            # Auto 選択時は model 引数を省略し、GitHub 側の Auto model selection に委譲する。
            if self.config.model and self.config.model != MODEL_AUTO_VALUE:
                session_opts["model"] = self.config.model

            # MCP Servers
            if self.config.mcp_servers:
                session_opts["mcp_servers"] = copy.deepcopy(self.config.mcp_servers)

            # Work IQ MCP Server 自動追加
            _workiq_mcp_enabled = False
            if self.config.workiq_enabled:
                if is_workiq_available():
                    _workiq_mcp = build_workiq_mcp_config(
                        tenant_id=self.config.workiq_tenant_id,
                    )
                    _existing_mcp = session_opts.get("mcp_servers") or {}
                    for _wiq_key in _workiq_mcp:
                        if _wiq_key in _existing_mcp:
                            self.console.warning(
                                f"MCP サーバー設定のキー '{_wiq_key}' が重複しています。"
                                " ユーザー設定を優先し、Work IQ の自動設定をスキップします。"
                            )
                        else:
                            _existing_mcp[_wiq_key] = _workiq_mcp[_wiq_key]
                    session_opts["mcp_servers"] = _existing_mcp
                    _workiq_mcp_enabled = "_hve_workiq" in _existing_mcp
                    if _workiq_mcp_enabled:
                        self.console.status(
                            "✅ Work IQ MCP サーバーをセッションに追加しました"
                        )
                else:
                    self.console.warning(
                        "Work IQ が検出できません。Work IQ 連携をスキップします。"
                    )

            # Custom Agents (グローバル定義)
            custom_agents: List[Dict[str, Any]] = copy.deepcopy(
                self.config.custom_agents_config or []
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
                # グローバル定義に同名がなければ最小定義を追加
                existing_names = {a.get("name") for a in custom_agents}
                if custom_agent not in existing_names:
                    base_prompt = f"You are {custom_agent}."
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

            session = await client.create_session(**session_opts)
            if _workiq_mcp_enabled:
                try:
                    _mcp_list = await session.rpc.mcp.list()
                    for _srv in _mcp_list.servers:
                        if _srv.name == "_hve_workiq":
                            _srv_status = _srv.status.value if hasattr(_srv.status, "value") else str(_srv.status)
                            if _srv_status != "connected":
                                self.console.warning(
                                    f"Work IQ MCP サーバー状態: {_srv_status}"
                                    + (f" — {_srv.error}" if _srv.error else "")
                                )
                                _workiq_mcp_enabled = False
                                self._workiq_mcp_connection_failed = True
                            break
                    else:
                        self.console.warning(
                            "Work IQ MCP サーバー '_hve_workiq' がサーバー一覧に存在しません"
                        )
                        _workiq_mcp_enabled = False
                        self._workiq_mcp_connection_failed = True
                except Exception as _mcp_err:
                    self.console.warning(f"MCP サーバー一覧の取得に失敗: {_mcp_err}")
                    _workiq_mcp_enabled = False
                    self._workiq_mcp_connection_failed = True

            # イベント購読 (常に購読 — Console 側で出力レベルを制御)
            session.on(self._handle_session_event)

            # ストリーム表示の開始マーカー
            if self.console.show_stream:
                self.console.stream_start(step_id)

            # フェーズ総数を動的算出
            total_phases = 1
            if self.config.auto_qa:
                total_phases += 1
            if self.config.auto_contents_review:
                total_phases += 1
            if self.config.auto_self_improve and not self.config.self_improve_skip:
                total_phases += 1
            current_phase = 0

            # Phase 1: メインタスク
            current_phase += 1
            phase1_start = time.time()
            self.console.step_phase_start(step_id, current_phase, total_phases, "メインタスク")
            main_response = await session.send_and_wait(prompt, timeout=self.config.timeout_seconds)
            main_output = _extract_text(main_response)
            self.console.step_phase_end(
                step_id, current_phase, total_phases, "メインタスク",
                elapsed=time.time() - phase1_start,
            )
            if self.config.workiq_enabled and _workiq_mcp_enabled and not self._workiq_tool_called:
                if self._workiq_mcp_connection_failed:
                    self.console.warning(
                        "❌ Work IQ MCP サーバーの接続に失敗したため、ツールが利用できませんでした。\n"
                        "   CLI モード (npx -y @microsoft/workiq ask) は正常でも、\n"
                        "   MCP モード (npx -y @microsoft/workiq mcp) では別のエラーが発生します。\n"
                        "   対処: 以下を手動実行して MCP サーバーの起動を確認してください:\n"
                        "     npx -y @microsoft/workiq mcp"
                    )
                else:
                    self.console.warning(
                        "⚠️ Work IQ MCP ツールが1度も呼び出されませんでした。"
                        "エージェントが Work IQ 指示を実行しなかった可能性があります。"
                    )

            # Phase 2: QA（auto_qa=True の場合）
            if self.config.auto_qa:
                current_phase += 1
                phase2_start = time.time()
                # Phase 2a: QA 質問票生成（QA_PROMPT_V2 で構造化形式）
                self.console.step_phase_start(step_id, current_phase, total_phases, "QA レビュー")
                _qa_model = self.config.get_qa_model()
                _use_qa_sub_session = (_qa_model != self.config.model)
                _qa_session = None
                try:
                    _effective_qa_session = session
                    _effective_qa_prompt = QA_PROMPT_V2
                    if _use_qa_sub_session:
                        _qa_session = await client.create_session(**self._build_sub_session_opts(_qa_model))
                        _qa_session.on(self._handle_session_event)
                        _qa_context = _truncate_context(main_output or "", _MAX_CONTEXT_INJECTION_LENGTH)
                        _effective_qa_prompt = (
                            "以下は同一ステップのメインタスク出力です。"
                            "この内容を前提として QA 質問票を作成してください。\n\n"
                            f"=== メインタスク出力（最大{_MAX_CONTEXT_INJECTION_LENGTH:,}文字） ===\n"
                            f"{_qa_context}\n"
                            "=== メインタスク出力ここまで ===\n\n"
                            f"{QA_PROMPT_V2}"
                        )
                        _effective_qa_session = _qa_session

                    qa_response = await _effective_qa_session.send_and_wait(
                        _effective_qa_prompt, timeout=self.config.timeout_seconds
                    )
                    qa_content = _extract_text(qa_response)
                    if not qa_content:
                        self.console.warning("QA 質問票の生成に失敗しました（LLM の応答が空）。")

                    # Phase 2b: 回答収集（新フロー）
                    # まず QADocument をパースして questions が存在するか確認する
                    parsed_qa_preview = QAMerger.parse_qa_content(qa_content)
                    _parse_succeeded = bool(parsed_qa_preview.questions)
                    if not _parse_succeeded:
                        # パース失敗フォールバック: 旧フロー（生 Markdown を表示してから入力待ち）
                        self.console.qa_prompt(qa_content)
                        user_answers_raw = await _read_stdin_multiline(
                            prompt_msg=(
                                f"[Step.{step_id}] QA 回答を入力してください\n"
                                "  形式: 「番号: 選択肢」を1行1問で入力（例: 1: A）\n"
                                "  空行で入力終了 / skip または何も入力せず Enter で既定値候補を採用:"
                            ),
                            console=self.console,
                            timeout=self.config.qa_input_timeout_seconds,
                        )
                        skip_input = user_answers_raw.strip().lower() in ("", "skip")
                    else:
                        user_answers_raw, skip_input = await _collect_qa_answers(
                            self.console, parsed_qa_preview, step_id, self.config
                        )

                    # Work IQ による補助情報取得（QA 質問票のデフォルト回答補強）
                    _workiq_qa_context = ""
                    _workiq_draft_path: Optional[Path] = None
                    if (
                        self.config.workiq_enabled
                        and _workiq_mcp_enabled
                        and _parse_succeeded
                        and parsed_qa_preview.questions
                    ):
                        async def _query_workiq_bulk_once() -> str:
                            _questions_summary = "\n".join(
                                f"- Q{q.no}: {q.question[:100]}"
                                for q in parsed_qa_preview.questions[:30]
                            )
                            _wiq_template = get_workiq_prompt_template(
                                "qa", self.config.workiq_prompt_qa
                            )
                            _wiq_query = _wiq_template.format(target_content=_questions_summary)
                            _bulk_context = await query_workiq(
                                _effective_qa_session,
                                _wiq_query,
                                timeout=self.config.workiq_query_timeout_seconds,
                            )
                            if _bulk_context:
                                save_workiq_result(
                                    self.config.run_id, step_id, "qa",
                                    _bulk_context,
                                )
                            return _bulk_context

                        if self.config.workiq_draft_mode:
                            self.console.status("🔍 Work IQ: 質問ごとに回答ドラフトを生成中...")
                            self.console.spinner_start("Work IQ 問い合わせ中...")
                            try:
                                _wiq_template = get_workiq_prompt_template(
                                    "qa", self.config.workiq_prompt_qa
                                )
                                _question_items = [
                                    (q.no, q.question)
                                    for q in parsed_qa_preview.questions
                                ]
                                _per_question_results = await query_workiq_per_question(
                                    _effective_qa_session,
                                    _question_items,
                                    _wiq_template,
                                    timeout=self.config.workiq_per_question_timeout,
                                    max_questions=self.config.workiq_max_draft_questions,
                                )

                                _raw_lines: List[str] = []
                                for q in parsed_qa_preview.questions[:self.config.workiq_max_draft_questions]:
                                    _ctx = _per_question_results.get(q.no, "").strip() or "関連情報なし"
                                    _raw_lines.extend([
                                        f"### Q{q.no}: {q.question}",
                                        _ctx,
                                        "",
                                    ])
                                save_workiq_result(
                                    self.config.run_id, step_id, "qa-draft",
                                    "\n".join(_raw_lines).strip(),
                                )

                                _draft_questions = [
                                    {"no": q.no, "question": q.question, "default": q.default}
                                    for q in parsed_qa_preview.questions[:self.config.workiq_max_draft_questions]
                                ]
                                _draft_content = format_workiq_draft_answers(
                                    _draft_questions, _per_question_results
                                )
                                _draft_dir = Path(
                                    self.config.workiq_draft_output_dir or "qa"
                                )
                                _draft_dir.mkdir(parents=True, exist_ok=True)
                                _workiq_draft_path = _draft_dir / f"{self.config.run_id}-{step_id}-workiq-draft.md"
                                _workiq_draft_path.write_text(_draft_content, encoding="utf-8")
                                self.console.status(
                                    f"✅ Work IQ: 回答ドラフトを保存しました ({_workiq_draft_path.as_posix()})"
                                )
                            except Exception as draft_exc:
                                self.console.warning(
                                    f"Work IQ ドラフト生成に失敗したため、一括問い合わせにフォールバックします: {draft_exc}"
                                )
                                _workiq_qa_context = await _query_workiq_bulk_once()
                            finally:
                                self.console.spinner_stop()
                        else:
                            self.console.status("🔍 Work IQ: M365 データから関連情報を調査中...")
                            self.console.spinner_start("Work IQ 問い合わせ中...")
                            _workiq_qa_context = await _query_workiq_bulk_once()
                            self.console.spinner_stop()
                            if _workiq_qa_context:
                                self.console.status("✅ Work IQ: 関連情報を取得しました")
                            else:
                                self.console.status("ℹ️ Work IQ: 関連情報は見つかりませんでした")

                    # Phase 2c: QA 回答マージ + qa/ ファイル永続化
                    # パース失敗時は質問が 0 件のためマージ処理をスキップし、フォールバックに移行する。
                    merge_succeeded = False
                    if not _parse_succeeded:
                        self.console.warning(
                            "QA 質問票のパースに失敗したため、マージ処理をスキップします。"
                            " QA_APPLY_PROMPT にフォールバックします。"
                        )
                    else:
                        try:
                            parsed_qa = parsed_qa_preview
                            if skip_input:
                                # 既定値候補を全問採用
                                answers: Dict[int, str] = {}
                                merged_qa = QAMerger.merge_answers(parsed_qa, answers, use_defaults=True)
                            else:
                                answers = QAMerger.parse_answers(user_answers_raw)
                                merged_qa = QAMerger.merge_answers(parsed_qa, answers)
                            merged_content = QAMerger.render_merged(merged_qa)

                            # Agent にマージ済みファイル保存を指示
                            # 並列安全性: ファイルパスは run_id + ステップ ID で分離されているため
                            # 並列ステップ間・再実行間での同一ファイルへの同時書き込みは発生しない。
                            # run_id は run_step() 冒頭で正規化済みのため _safe_run_id() の再呼び出しは不要。
                            save_prompt = QA_MERGE_SAVE_PROMPT.format(
                                merged_content=merged_content,
                                qa_file_path=f"qa/{self.config.run_id}-{step_id}-qa-merged.md",
                            )
                            if _workiq_draft_path:
                                save_prompt += (
                                    "\n\n## Work IQ 回答ドラフト（要レビュー）\n"
                                    f"- 参考ファイル: `{_workiq_draft_path.as_posix()}`\n"
                                    "- このドラフトを参照しつつ、最終内容は必ず人間レビューで確定してください。\n"
                                )
                            # Work IQ 結果をマージ保存プロンプトに注入
                            if _workiq_qa_context:
                                save_prompt = enrich_prompt_with_workiq(
                                    _workiq_qa_context,
                                    save_prompt,
                                    context_type="QA デフォルト回答の補強情報",
                                )
                            save_response = await _effective_qa_session.send_and_wait(
                                save_prompt, timeout=self.config.timeout_seconds
                            )
                            if save_response is None:
                                self.console.warning(
                                    "マージ済みファイルの保存指示に対する応答がありませんでした。"
                                )

                            # 統合ドキュメント生成
                            try:
                                consolidate_prompt = QA_CONSOLIDATE_PROMPT.format(
                                    merged_qa_content=merged_content,
                                )
                                consolidate_response = await _effective_qa_session.send_and_wait(
                                    consolidate_prompt, timeout=self.config.timeout_seconds
                                )
                                if consolidate_response is None:
                                    self.console.warning(
                                        "統合ドキュメント生成の応答がありませんでした（マージ済みファイルは保存済み）。"
                                    )
                            except Exception as consolidate_exc:
                                self.console.warning(
                                    f"統合ドキュメント生成に失敗しました（マージ済みファイルは保存済み）: {consolidate_exc}"
                                )

                            merge_succeeded = True
                        except Exception as merge_exc:
                            self.console.warning(
                                f"QA マージ処理に失敗しました。従来の QA_APPLY_PROMPT にフォールバックします: {merge_exc}"
                            )

                    if not merge_succeeded:
                        # フォールバック: 既存の QA_APPLY_PROMPT
                        if skip_input:
                            fallback_answers = "(既定値候補を採用)"
                        else:
                            fallback_answers = user_answers_raw
                        apply_prompt = QA_APPLY_PROMPT.format(user_answers=fallback_answers)
                        await _effective_qa_session.send_and_wait(
                            apply_prompt, timeout=self.config.timeout_seconds
                        )
                finally:
                    if _qa_session is not None:
                        await _qa_session.disconnect()

                self.console.step_phase_end(
                    step_id, current_phase, total_phases, "QA レビュー",
                    elapsed=time.time() - phase2_start,
                )

            # Phase 3: 敵対的レビュー（auto_contents_review=True の場合）
            if self.config.auto_contents_review:
                current_phase += 1
                phase3_start = time.time()
                self.console.step_phase_start(step_id, current_phase, total_phases, "敵対的レビュー")
                _review_model = self.config.get_review_model()
                _use_review_sub_session = (_review_model != self.config.model)
                _review_session = None
                try:
                    _effective_review_session = session
                    _effective_review_prompt = REVIEW_PROMPT
                    if _use_review_sub_session:
                        _review_session = await client.create_session(
                            **self._build_sub_session_opts(_review_model)
                        )
                        _review_session.on(self._handle_session_event)
                        _review_context = _truncate_context(main_output or "", _MAX_CONTEXT_INJECTION_LENGTH)
                        _effective_review_prompt = (
                            "以下は同一ステップのメインタスク出力です。"
                            "この内容を前提としてレビューしてください。\n\n"
                            f"=== メインタスク出力（最大{_MAX_CONTEXT_INJECTION_LENGTH:,}文字） ===\n"
                            f"{_review_context}\n"
                            "=== メインタスク出力ここまで ===\n\n"
                            f"{REVIEW_PROMPT}"
                        )
                        _effective_review_session = _review_session

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
            if self.config.auto_self_improve and not self.config.self_improve_skip:
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
                    _scan = scan_codebase(
                        target_scope=self.config.self_improve_target_scope,
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
                    _exec_prompt = (
                        f"以下の改善計画を実行してください。\n\n{_plan_content[:_MAX_PLAN_SCAN_LENGTH]}"
                    )
                    await session.send_and_wait(
                        _exec_prompt, timeout=self.config.timeout_seconds
                    )

                    # Phase 4d: 改善後検証（Verification Loop §10.1 準拠）
                    _after_scan = scan_codebase(
                        target_scope=self.config.self_improve_target_scope,
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
            token = _get(data, "delta_content", "content") or ""
            if token:
                self.console.stream_token(step_id, token)
            return

        if etype == "assistant.streaming_delta":
            # バイト進捗 — 表示不要
            return

        # --- ツール実行 (高頻度) ---
        if etype == "tool.execution_start":
            tool_name = _get(data, "tool_name", "toolName", default="unknown")
            args = _get(data, "arguments", default=None)
            action_name, detail = self._build_action_display(tool_name, args)
            if args and isinstance(args, dict):
                # 既存のファイル I/O 追跡ロジックは維持
                self._track_tool_files(step_id, tool_name, args)
            if tool_name in _WORKIQ_TOOL_NAMES and not self._workiq_tool_called:
                self._workiq_tool_called = True
                self.console.status(
                    f"🔍 Work IQ ツール '{tool_name}' が呼び出されました"
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
            intent_text = _get(data, "intent") or ""
            if intent_text:
                self.console.thinking(step_id, intent_text)
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
            self.console.event(f"💭 [{step_id}] 推論完了 ({len(content)} chars)")
            return

        if etype == "assistant.reasoning_delta":
            # 推論ストリーム — Console 側で show_stream を制御
            token = _get(data, "delta_content", "deltaContent") or ""
            if token:
                self.console.stream_token(step_id, token)
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
                    if name == "_hve_workiq":
                        self._workiq_mcp_connection_failed = True
                else:
                    self.console.event(f"ℹ️ MCP '{name}' status={status}")
            return

        if etype == "session.mcp_server_status_changed":
            server_name = _get(data, "server_name", "serverName", default="?")
            status_obj = _get(data, "status", default=None)
            status = getattr(status_obj, "value", str(status_obj)) if status_obj else "unknown"
            if status in ("failed", "needs-auth") and server_name == "_hve_workiq":
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
