"""T2: precheck_llm_judge の単体テスト。

実 LLM 呼び出しは行わず、`_judge_async` をモックして以下を検証する:
  - 正常な JSON 応答 → 期待通りの JudgeResult dict
  - JSON 解析失敗 (raw text) → 空 dict
  - タイムアウト → 空 dict
  - 追加プロンプト空 / 候補空 → 即時 空 dict (LLM 未呼出)
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from hve.autopilot.precheck_llm_judge import (
    JudgeResult,
    _build_judge_prompt,
    _extract_json,
    judge_overrides_with_llm,
)


def test_empty_prompt_returns_empty_without_calling_llm() -> None:
    with patch("hve.autopilot.precheck_llm_judge._judge_async") as mock_async:
        result = judge_overrides_with_llm("", [{"pattern": "a.md", "description": "A"}])
    assert result == {}
    mock_async.assert_not_called()


def test_empty_items_returns_empty_without_calling_llm() -> None:
    with patch("hve.autopilot.precheck_llm_judge._judge_async") as mock_async:
        result = judge_overrides_with_llm("一部のファイル名は変えます", [])
    assert result == {}
    mock_async.assert_not_called()


def test_whitespace_only_prompt_returns_empty() -> None:
    with patch("hve.autopilot.precheck_llm_judge._judge_async") as mock_async:
        result = judge_overrides_with_llm("   \n  ", [{"pattern": "a.md", "description": "A"}])
    assert result == {}
    mock_async.assert_not_called()


def test_successful_judge_parses_results() -> None:
    expected = {
        "docs/a.md": JudgeResult(is_satisfied=True, reason="別ファイル名で指定済み"),
        "docs/b.md": JudgeResult(is_satisfied=False, reason="言及なし"),
    }

    async def fake_async(prompt, items, timeout):  # type: ignore[no-untyped-def]
        return expected

    with patch("hve.autopilot.precheck_llm_judge._judge_async", side_effect=fake_async):
        result = judge_overrides_with_llm(
            "docs/a.md は docs/alternative.md に置き換えてください",
            [
                {"pattern": "docs/a.md", "description": "A"},
                {"pattern": "docs/b.md", "description": "B"},
            ],
        )
    assert result == expected


def test_timeout_returns_empty() -> None:
    async def fake_async(prompt, items, timeout):  # type: ignore[no-untyped-def]
        raise asyncio.TimeoutError()

    with patch("hve.autopilot.precheck_llm_judge._judge_async", side_effect=fake_async):
        result = judge_overrides_with_llm(
            "何らかの追加指示",
            [{"pattern": "a.md", "description": "A"}],
        )
    assert result == {}


def test_unexpected_exception_returns_empty() -> None:
    async def fake_async(prompt, items, timeout):  # type: ignore[no-untyped-def]
        raise RuntimeError("SDK 失敗")

    with patch("hve.autopilot.precheck_llm_judge._judge_async", side_effect=fake_async):
        result = judge_overrides_with_llm(
            "追加指示",
            [{"pattern": "a.md", "description": "A"}],
        )
    assert result == {}


def test_extract_json_plain() -> None:
    obj = _extract_json('{"results": [{"pattern": "a", "satisfied": true, "reason": "r"}]}')
    assert obj is not None
    assert obj["results"][0]["pattern"] == "a"


def test_extract_json_with_code_fence() -> None:
    text = 'ここは前置きです。\n```json\n{"results": []}\n```\n後ろは無視。'
    obj = _extract_json(text)
    assert obj == {"results": []}


def test_extract_json_with_surrounding_text() -> None:
    text = "考えました。結論: {\"results\": [{\"pattern\": \"x\", \"satisfied\": false, \"reason\": \"\"}]} 以上。"
    obj = _extract_json(text)
    assert obj is not None
    assert obj["results"][0]["pattern"] == "x"


def test_extract_json_invalid_returns_none() -> None:
    assert _extract_json("これは JSON ではありません") is None
    assert _extract_json("") is None
    assert _extract_json("{ broken") is None


def test_build_judge_prompt_contains_inputs() -> None:
    prompt = _build_judge_prompt(
        "docs/a.md を docs/alt.md に変えてください",
        [{"pattern": "docs/a.md", "description": "A 設計書"}],
    )
    assert "docs/a.md" in prompt
    assert "docs/alt.md" in prompt
    assert "A 設計書" in prompt
    assert '"results"' in prompt  # 出力スキーマ指示
