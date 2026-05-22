"""hve.autopilot.precheck_llm_judge — 追加プロンプトの自然言語判定（Qt 非依存）。

Step 1 precheck で「不足ファイル」と検出された項目に対し、ユーザーが入力した
追加プロンプト本文を LLM に渡して「自然言語で参照／代替指定されているか」を
判定する。GitHub Copilot SDK (CopilotClient) 経由で 1 回の呼び出しで全項目を
一括判定する。

判定方針 (Q1-Q6 確定):
  - Q1: github-copilot-sdk 経由
  - Q2: 同期呼び出し（タイムアウト 10s）、呼び出し側で追加プロンプト空時はスキップ
  - Q3: 1 回の呼び出しで全項目を判定（JSON 配列を返させる）
  - Q4: 各項目に reason 文字列を返させ、ログ出力
  - Q5: キャッシュなし
  - Q6: 失敗時は空 dict を返す（呼び出し側で従来の部分文字列マッチへフォールバック）
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

__all__ = ["JudgeResult", "judge_overrides_with_llm", "DEFAULT_TIMEOUT_SEC"]

DEFAULT_TIMEOUT_SEC: float = 10.0

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JudgeResult:
    """LLM 判定結果。

    Attributes:
        is_satisfied: True のとき「追加プロンプトで言及されており不足扱いを解除可能」。
        reason: LLM が返した日本語の理由文字列（ログ／デバッグ用）。
    """

    is_satisfied: bool
    reason: str


def _build_judge_prompt(additional_prompt: str, items: List[Dict[str, str]]) -> str:
    """LLM へ送るプロンプト本文を組み立てる。

    items は [{"pattern": str, "description": str}] のリスト。
    """
    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    return (
        "あなたはソフトウェア要件チェッカーです。"
        "以下の「追加プロンプト」本文と「不足ファイル候補」一覧を照合し、"
        "各候補について「追加プロンプト本文中で、別ファイル名の指定／参照ファイルの追加指定／"
        "代替手段の指示などによって、その不足が実質的に解消されているか」を自然言語で判断してください。\n\n"
        "判定基準:\n"
        "- パスそのものが一致していなくても、ファイルの内容・役割・場所が自然言語で言及されていれば satisfied=true。\n"
        "- 単に「あとで作る」「不要」等の表明だけでは satisfied=false。\n"
        "- 確信が持てない場合は satisfied=false。\n\n"
        "出力は次の JSON 形式のみ（前後に余計な文字を含めない）:\n"
        '{"results": [{"pattern": "<候補のpattern文字列>", "satisfied": true/false, "reason": "<日本語の理由>"}, ...]}\n\n'
        f"--- 追加プロンプト ---\n{additional_prompt}\n--- 追加プロンプトここまで ---\n\n"
        f"--- 不足ファイル候補 ---\n{items_json}\n--- 不足ファイル候補ここまで ---\n"
    )


def _extract_json(text: str) -> Optional[dict]:
    """LLM 応答から JSON オブジェクトを抽出する。

    応答が ```json ... ``` で囲まれている場合や、前後に余計な文字がある場合にも
    最初の `{` から最後の `}` までを取り出して json.loads する。
    """
    if not text:
        return None
    # コードフェンス除去
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence_match.group(1) if fence_match else None
    if candidate is None:
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            return None
        candidate = text[first : last + 1]
    try:
        obj = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


async def _judge_async(
    additional_prompt: str,
    items: List[Dict[str, str]],
    timeout_sec: float,
) -> Dict[str, JudgeResult]:
    """SDK 経由で 1 回の send_and_wait により全項目判定を実施する。"""
    from copilot import CopilotClient  # type: ignore[import-not-found]
    from copilot.session import PermissionHandler  # type: ignore[import-not-found]

    # 遅延 import: 循環回避と GUI/CLI 共通の最小化
    from ..config import DEFAULT_MODEL, MODEL_AUTO_REASONING_EFFORT
    from ..orchestrator import _create_session_with_auto_reasoning_fallback  # type: ignore
    from ..runner import _extract_text  # type: ignore

    client = CopilotClient()
    await client.start()
    try:
        session_opts: dict = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
            # ユニーク session_id: 連続呼出で SDK 側セッション再利用による
            # 前回コンテキスト混入を防ぐ。
            "session_id": f"precheck-llm-judge-{uuid.uuid4().hex[:12]}",
            "model": DEFAULT_MODEL,
            "reasoning_effort": MODEL_AUTO_REASONING_EFFORT,
        }
        session = await _create_session_with_auto_reasoning_fallback(client, session_opts)
        try:
            prompt = _build_judge_prompt(additional_prompt, items)
            # send_and_wait 自身にも timeout を伝えるが、判定全体（client.start /
            # session 作成含む）は judge_overrides_with_llm 側の asyncio.wait_for
            # で囲んでいる。
            response = await session.send_and_wait(prompt, timeout=timeout_sec)
            text = (_extract_text(response) or "").strip()
        finally:
            try:
                await session.disconnect()
            except Exception:
                pass
    finally:
        try:
            await client.stop()
        except Exception:
            pass

    parsed = _extract_json(text)
    if not parsed or not isinstance(parsed.get("results"), list):
        _logger.warning("precheck LLM judge: JSON 解析失敗 (raw=%r)", text[:200])
        return {}

    out: Dict[str, JudgeResult] = {}
    for entry in parsed["results"]:
        if not isinstance(entry, dict):
            continue
        pat = entry.get("pattern")
        if not isinstance(pat, str) or not pat:
            continue
        satisfied = bool(entry.get("satisfied", False))
        reason = entry.get("reason", "")
        if not isinstance(reason, str):
            reason = str(reason)
        out[pat] = JudgeResult(is_satisfied=satisfied, reason=reason)
    return out


def judge_overrides_with_llm(
    additional_prompt: str,
    missing_items: List[Dict[str, str]],
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> Dict[str, JudgeResult]:
    """追加プロンプト本文に基づいて不足ファイル候補を一括判定する（同期ラッパ）。

    Args:
        additional_prompt: ユーザー入力の追加プロンプト本文。空文字列の場合は
            呼び出し側でスキップする想定だが、本関数も空文字なら即座に空 dict を返す。
        missing_items: ``[{"pattern": <必須入力 path>, "description": <成果物 description>}]``
            のリスト。
        timeout_sec: LLM 呼び出しタイムアウト秒数。

    Returns:
        ``{pattern: JudgeResult}`` の dict。LLM 呼び出し失敗・タイムアウト・
        JSON 解析失敗時は空 dict を返す（呼び出し側で従来挙動へフォールバック）。
    """
    if not additional_prompt or not additional_prompt.strip():
        return {}
    if not missing_items:
        return {}
    try:
        # 判定全体（client.start / session 作成 / send_and_wait / disconnect）を
        # 1 つの timeout で囲むことで、SDK のどの段階で hang しても確実に打ち切る。
        return asyncio.run(
            asyncio.wait_for(
                _judge_async(additional_prompt, missing_items, timeout_sec),
                timeout=timeout_sec,
            )
        )
    except asyncio.TimeoutError:
        _logger.warning("precheck LLM judge: timeout (%.1fs)", timeout_sec)
        return {}
    except Exception as exc:  # noqa: BLE001
        _logger.warning("precheck LLM judge: 失敗 %s: %s", type(exc).__name__, exc)
        return {}
