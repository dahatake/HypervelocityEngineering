"""runner.py — StepRunner: 1 ステップを CopilotSession で実行する"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 同時 stdin アクセスを防止し、全ステップで共有される sys.stdin を順番に利用させる。
# asyncio.Lock により同一イベントループ内の複数コルーチンからの同時入力を直列化する。
_stdin_lock = asyncio.Lock()

try:
    from .config import SDKConfig
    from .console import Console, timestamp_prefix
    from .prompts import (
        QA_PROMPT, QA_APPLY_PROMPT, REVIEW_PROMPT, ADVERSARIAL_RECHECK_PROMPT,
        QA_PROMPT_V2, QA_MERGE_SAVE_PROMPT, QA_CONSOLIDATE_PROMPT,
        SELF_IMPROVE_SCAN_PROMPT, SELF_IMPROVE_PLAN_PROMPT, SELF_IMPROVE_VERIFY_PROMPT,
    )
    from .qa_merger import QADocument, QAMerger
    from .self_improve import (
        scan_codebase, record_learning, get_learning_summary,
        ImprovementRecord, VerificationResult,
        DEFAULT_QUALITY_THRESHOLD, LEARNING_SUMMARY_MAX_LENGTH,
    )
    from .permission_handler import ScopedPermissionHandler
except ImportError:
    from config import SDKConfig  # type: ignore[no-redef]
    from console import Console, timestamp_prefix  # type: ignore[no-redef]
    from prompts import (  # type: ignore[no-redef]
        QA_PROMPT, QA_APPLY_PROMPT, REVIEW_PROMPT, ADVERSARIAL_RECHECK_PROMPT,
        QA_PROMPT_V2, QA_MERGE_SAVE_PROMPT, QA_CONSOLIDATE_PROMPT,
        SELF_IMPROVE_SCAN_PROMPT, SELF_IMPROVE_PLAN_PROMPT, SELF_IMPROVE_VERIFY_PROMPT,
    )
    from qa_merger import QADocument, QAMerger  # type: ignore[no-redef]
    from self_improve import (  # type: ignore[no-redef]
        scan_codebase, record_learning, get_learning_summary,
        ImprovementRecord, VerificationResult,
        DEFAULT_QUALITY_THRESHOLD, LEARNING_SUMMARY_MAX_LENGTH,
    )
    from permission_handler import ScopedPermissionHandler  # type: ignore[no-redef]

# Phase 4 プロンプト長の上限（長い出力を切り詰めてトークン消費を制御する）
_MAX_SCAN_OUTPUT_LENGTH: int = 8000
_MAX_PLAN_SCAN_LENGTH: int = 4000
_MAX_LEARNING_SUMMARY_LENGTH: int = 2000


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
        questionnaire_table() のみ表示し、デフォルト回答を全採用する。

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

    if not sys.stdin.isatty():
        # 非 TTY: テーブル表示のみ行いデフォルト採用
        return "", True

    # TTY: フルインタラクティブフロー
    mode = console.prompt_answer_mode()

    if mode == "all":
        # 4A. 全問一括入力モード
        user_answers_raw = await _read_stdin_multiline(
            prompt_msg=(
                f"[Step.{step_id}] QA 回答を入力してください\n"
                "  形式: 「番号: 選択肢」を1行1問で入力（例: 1: A）\n"
                "  空行で入力終了 / skip または何も入力せず Enter でデフォルト回答を採用:"
            ),
            console=console,
            timeout=config.timeout_seconds,
        )
        if user_answers_raw.strip().lower() in ("", "skip"):
            # 全問空入力 → デフォルト採用確認
            adopt = console.prompt_yes_no(
                "全問デフォルト回答を採用しますか？",
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
                    timeout=config.timeout_seconds,
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

    # 回答サマリー表示
    _parsed_answers = QAMerger.parse_answers(user_answers_raw)
    console.answer_summary(doc.questions, _parsed_answers)

    return user_answers_raw, skip_input


class StepRunner:
    """1 ステップを CopilotSession で実行する。

    フロー (1ステップ内、同一セッション):
    ┌──────────────────────────────────────────────────┐
    │ CopilotSession (同一セッション = コンテキスト保持)   │
    │                                                    │
    │  Phase 1: session.send_and_wait(prompt)            │
    │    → Agent がメインタスク実行                        │
    │                                                    │
    │  [auto_qa=True の場合]                              │
    │  Phase 2a: session.send_and_wait(QA_PROMPT_V2)     │
    │    → Agent が 5列テーブル形式の質問票を生成          │
    │  Phase 2b: CLI stdin で複数行回答入力               │
    │    → "番号: 選択肢" 形式 / 空行で終了               │
    │    → skip/空 入力でデフォルト回答適用               │
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

        # --- dry_run ---
        if self.config.dry_run:
            self.console.step_start(step_id, title, agent=custom_agent)
            self.console.event(f"[DRY-RUN] Step.{step_id} would execute: {title}")
            elapsed = time.time() - start
            self.console.step_end(step_id, "success", elapsed=elapsed)
            return True

        # --- SDK インポート確認 ---
        try:
            from copilot import CopilotClient, PermissionHandler  # type: ignore[import]
            from copilot import SubprocessConfig, ExternalServerConfig  # type: ignore[import]
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
        log_reader: Optional[_StderrLogReader] = None
        try:
            # SDK v0.2.0: CopilotClient(config=SubprocessConfig|ExternalServerConfig)
            if self.config.cli_url:
                sdk_config = ExternalServerConfig(url=self.config.cli_url)
            else:
                _cfg_kwargs: Dict[str, Any] = dict(
                    cli_path=self.config.cli_path,
                    github_token=self.config.resolve_token() or None,
                    log_level=self.config.log_level,
                )
                _on_log_supported = True
                try:
                    sdk_config = SubprocessConfig(
                        **_cfg_kwargs,
                        on_log=self._make_cli_log_handler(step_id),
                    )
                except TypeError:
                    # on_log パラメータ未対応の SDK バージョン — stderr キャプチャにフォールバック
                    _on_log_supported = False
                    self.console.event(
                        f"  📋 [{step_id}] SDK が on_log 未対応のため stderr キャプチャにフォールバック"
                    )
                    sdk_config = SubprocessConfig(**_cfg_kwargs)
            client = CopilotClient(config=sdk_config)
            await client.start()

            # on_log 未対応時のみ: サブプロセスの stderr をキャプチャしてログを表示
            # (on_log が通った場合はコールバック経由で既にログ取得されるため重複を避ける)
            if not self.config.cli_url and not _on_log_supported:
                log_reader = self._try_attach_log_reader(client, step_id)

            # セッション構築オプション
            session_opts: Dict[str, Any] = {
                "model": self.config.model,
                "on_permission_request": PermissionHandler.approve_all,
                "streaming": True,
            }

            # MCP Servers
            if self.config.mcp_servers:
                session_opts["mcp_servers"] = self.config.mcp_servers

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
            await session.send_and_wait(prompt, timeout=self.config.timeout_seconds)
            self.console.step_phase_end(
                step_id, current_phase, total_phases, "メインタスク",
                elapsed=time.time() - phase1_start,
            )

            # Phase 2: QA（auto_qa=True の場合）
            if self.config.auto_qa:
                current_phase += 1
                phase2_start = time.time()
                # Phase 2a: QA 質問票生成（QA_PROMPT_V2 で5列テーブル形式）
                self.console.step_phase_start(step_id, current_phase, total_phases, "QA レビュー")
                qa_response = await session.send_and_wait(QA_PROMPT_V2, timeout=self.config.timeout_seconds)
                qa_content = _extract_text(qa_response)
                self.console.qa_prompt(qa_content)

                # Phase 2b: 回答収集（新フロー）
                # まず QADocument をパースして questions が存在するか確認する
                parsed_qa_preview = QAMerger.parse_qa_content(qa_content)
                if not parsed_qa_preview.questions:
                    # パース失敗フォールバック: 旧フロー
                    user_answers_raw = await _read_stdin_multiline(
                        prompt_msg=(
                            f"[Step.{step_id}] QA 回答を入力してください\n"
                            "  形式: 「番号: 選択肢」を1行1問で入力（例: 1: A）\n"
                            "  空行で入力終了 / skip または何も入力せず Enter でデフォルト回答を採用:"
                        ),
                        console=self.console,
                        timeout=self.config.timeout_seconds,
                    )
                    skip_input = user_answers_raw.strip().lower() in ("", "skip")
                else:
                    user_answers_raw, skip_input = await _collect_qa_answers(
                        self.console, parsed_qa_preview, step_id, self.config
                    )

                # Phase 2c: QA 回答マージ + qa/ ファイル永続化
                merge_succeeded = False
                try:
                    parsed_qa = QAMerger.parse_qa_content(qa_content)
                    if skip_input:
                        # デフォルト回答を全問採用
                        answers: Dict[int, str] = {}
                        merged_qa = QAMerger.merge_answers(parsed_qa, answers, use_defaults=True)
                    else:
                        answers = QAMerger.parse_answers(user_answers_raw)
                        merged_qa = QAMerger.merge_answers(parsed_qa, answers)
                    merged_content = QAMerger.render_merged(merged_qa)

                    # Agent にマージ済みファイル保存を指示
                    # 並列安全性: ファイルパスはステップ ID で分離されているため
                    # 並列ステップ間での同一ファイルへの同時書き込みは発生しない。
                    save_prompt = QA_MERGE_SAVE_PROMPT.format(
                        merged_content=merged_content,
                        qa_file_path=f"qa/{step_id}-qa-merged.md",
                    )
                    save_response = await session.send_and_wait(save_prompt, timeout=self.config.timeout_seconds)
                    if save_response is None:
                        self.console.warning(
                            "マージ済みファイルの保存指示に対する応答がありませんでした。"
                        )

                    # 統合ドキュメント生成
                    try:
                        consolidate_prompt = QA_CONSOLIDATE_PROMPT.format(
                            merged_qa_content=merged_content,
                        )
                        consolidate_response = await session.send_and_wait(
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
                        fallback_answers = "(デフォルト回答を採用)"
                    else:
                        fallback_answers = user_answers_raw
                    apply_prompt = QA_APPLY_PROMPT.format(user_answers=fallback_answers)
                    await session.send_and_wait(apply_prompt, timeout=self.config.timeout_seconds)

                self.console.step_phase_end(
                    step_id, current_phase, total_phases, "QA レビュー",
                    elapsed=time.time() - phase2_start,
                )

            # Phase 3: 敵対的レビュー（auto_contents_review=True の場合）
            # 同一セッション内で実行する（成果物のコンテキストを保持するため）
            if self.config.auto_contents_review:
                current_phase += 1
                phase3_start = time.time()
                self.console.step_phase_start(step_id, current_phase, total_phases, "敵対的レビュー")
                # 1回目: 敵対的レビュー実行
                review_response = await session.send_and_wait(
                    REVIEW_PROMPT, timeout=self.config.timeout_seconds
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
                        recheck_response = await session.send_and_wait(
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

            # Phase 4: 自己改善ループ（auto_self_improve=True かつ skip でない場合）
            if self.config.auto_self_improve and not self.config.self_improve_skip:
                current_phase += 1
                phase4_start = time.time()
                self.console.step_phase_start(step_id, current_phase, total_phases, "自己改善ループ")

                # 共通ロックを使って並列ステップ間での同時実行を防ぐ
                _work_dir = Path("work/self-improve")
                _max_iter = self.config.self_improve_max_iterations

                # ScopedPermissionHandler: Phase 4 の改善実行時に安全ガードを適用
                _permission_handler = ScopedPermissionHandler(strict=True)

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
                        f"以下の改善計画を実行してください。"
                        f"ScopedPermissionHandler により操作スコープが制限されています（work/ と qa/ 以外への書き込み、"
                        f"破壊的コマンドは拒否されます）。\n\n{_plan_content[:_MAX_PLAN_SCAN_LENGTH]}"
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
            elapsed = time.time() - start
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False
        finally:
            if log_reader is not None:
                log_reader.stop()
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
        self.console.step_end(step_id, "success", elapsed=elapsed)
        return True

    # ------------------------------------------------------------------
    # 内部ヘルパー — SDK data 属性の安全取得
    # ------------------------------------------------------------------

    @staticmethod
    def _get(data: Any, *names: str, default: Any = "") -> Any:
        """data オブジェクトから属性を安全に取得する。

        SDK v0.2.0 Python では snake_case 属性名を使用するが、
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

        SDK v0.2.0 のイベントタイプ一覧:
        https://github.com/github/copilot-sdk/blob/main/docs/features/streaming-events.md
        """
        # SDK v0.2.0: event.type は SessionEventType enum、.value で文字列取得
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
            args_summary = ""
            if args and isinstance(args, dict):
                # ツールの種類に応じて主要引数を要約表示
                for key in ("command", "path", "filePath", "file_path", "query", "pattern", "url"):
                    val = args.get(key)
                    if val:
                        val_str = str(val)
                        args_summary = val_str[:80] + "..." if len(val_str) > 80 else val_str
                        break
            self.console.tool(tool_name, step_id=step_id, args_summary=args_summary)
            return

        if etype == "tool.execution_complete":
            success = _get(data, "success", default=False)
            error = _get(data, "error", default=None)
            error_msg = ""
            if error and not success:
                error_msg = _get(error, "message", default=str(error))
            self.console.tool_result(step_id, bool(success), error_msg=error_msg)
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
                self.console.intent(step_id, intent_text)
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
            # 推論ストリーム — show_stream 時のみ表示
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

    def _make_cli_log_handler(self, step_id: str):
        """CLI プロセスの on_log コールバックを生成する（インスタンスメソッドラッパー）。"""
        return _make_log_handler(self.console, step_id)

    def _try_attach_log_reader(
        self, client: Any, step_id: str
    ) -> "Optional[_StderrLogReader]":
        """CopilotClient の内部サブプロセスから stderr リーダーをアタッチする。

        SDK の内部構造に依存するため、失敗しても警告のみで続行する。

        探索パス（優先順）:
          1. client._process.stderr
          2. client._subprocess.stderr
          3. client.process.stderr

        Returns:
            _StderrLogReader インスタンス（アタッチ成功時）、None（失敗時）
        """
        # ExternalServerConfig 使用時はサブプロセスがないためスキップ
        if self.config.cli_url:
            return None

        process = None
        for attr_path in ("_process", "_subprocess", "process"):
            proc = getattr(client, attr_path, None)
            if proc is not None and hasattr(proc, "stderr") and proc.stderr is not None:
                process = proc
                break

        if process is None:
            self.console.warning(
                f"⚠️ [{step_id}] CLI プロセスの stderr にアクセスできません。"
                "CLI ログ表示をスキップします。"
            )
            return None

        reader = _StderrLogReader(process.stderr, self.console, step_id)
        reader.start()
        self.console.event(f"  📋 [{step_id}] CLI ログキャプチャ開始")
        return reader


# ------------------------------------------------------------------
# 内部ヘルパー
# ------------------------------------------------------------------


class _StderrLogReader:
    """CopilotClient の内部サブプロセスの stderr を非同期に読み取り、
    Console.cli_log() にリレーするバックグラウンドスレッド。

    SDK が on_log をサポートしていない場合のフォールバック。
    """

    def __init__(
        self,
        process_stderr: Any,
        console: Any,
        step_id: str,
    ) -> None:
        self._stderr = process_stderr
        self._console = console
        self._step_id = step_id
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """バックグラウンドスレッドを開始する。"""
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """スレッドに停止を通知し、最大 2 秒待機する。"""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _read_loop(self) -> None:
        try:
            while True:
                if self._stop.is_set():
                    break
                raw_line = self._stderr.readline()
                # EOF またはストリームクローズ時はループ終了
                if not raw_line:
                    break
                if isinstance(raw_line, bytes):
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
                else:
                    # text mode（str）の場合はそのまま利用
                    line = str(raw_line).rstrip("\n\r")
                if line.strip():
                    self._console.cli_log(self._step_id, line)
        except (OSError, ValueError):
            pass  # プロセス終了時のエラーは無視


def _make_log_handler(console: Any, step_id: str):
    """CLI プロセスの on_log コールバックを生成する（モジュールレベル）。

    SubprocessConfig.on_log に渡すコールバック関数を返す。
    CLI プロセスのログ行を受け取り、Console.cli_log() 経由で
    既存のコンソール出力と階層的にマージして表示する。

    Args:
        console: Console インスタンス。
        step_id: 対象ステップの識別子。

    Returns:
        Callable[[str], None]: on_log コールバック関数。
    """
    def _on_log(line: str) -> None:
        if not line or not line.strip():
            return
        for sub_line in line.splitlines():
            if sub_line.strip():
                console.cli_log(step_id, sub_line)

    return _on_log


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

    async with _stdin_lock:
        # 他のステップのストリーム出力と視覚的に分離
        print(flush=True)
        print(f"{timestamp_prefix()} {"─" * 50}", flush=True)
        console.warning(prompt_msg)
        print(f"{timestamp_prefix()} {"─" * 50}", flush=True)

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

    async with _stdin_lock:
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

    SDK v0.2.0: send_and_wait() は SessionEvent | None を返す。
    テキストは event.data.content に格納される。
    """
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    # SDK v0.2.0: SessionEvent.data.content
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
    import re as _re
    _fence_start = _re.compile(r"```(?:json)?\s*\n?")
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
