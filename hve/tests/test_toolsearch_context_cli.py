"""FR-TS-11: `hve toolsearch context` の CLI 配線。

実測そのものはセッションを張るため、`collect` を差し替えて配線だけを検証する。
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, patch

from hve.__main__ import _build_parser, _cmd_toolsearch
from hve.toolsearch.context_report import ContextReport, ContextReportError, Layer

_REPORT = ContextReport(
    model_name="claude-sonnet-4.5",
    limit=128000,
    total_tokens=43702,
    system_tokens=15168,
    tool_definitions_tokens=28763,
    mcp_tools_tokens=17217,
    conversation_tokens=0,
    system_prompt_tokens=13790,
    layers=(Layer(name="azure", tool_count=68, tokens=15022),),
    unconnected=(),
)


def _parse(*argv: str):
    return _build_parser().parse_args(["toolsearch", *argv])


class TestParser(unittest.TestCase):
    def test_context_subcommand_is_registered(self) -> None:
        args = _parse("context")
        self.assertEqual(args.toolsearch_command, "context")

    def test_context_accepts_the_json_flag(self) -> None:
        self.assertTrue(_parse("context", "--json").json)


class TestCommand(unittest.TestCase):
    def test_text_output_renders_the_report(self) -> None:
        with patch(
            "hve.toolsearch.context_report.collect", AsyncMock(return_value=_REPORT)
        ):
            with patch("builtins.print") as printer:
                code = _cmd_toolsearch(_parse("context"))
        self.assertEqual(code, 0)
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        self.assertIn("claude-sonnet-4.5", printed)
        self.assertIn("azure", printed)

    def test_json_flag_outputs_machine_readable_payload(self) -> None:
        with patch(
            "hve.toolsearch.context_report.collect", AsyncMock(return_value=_REPORT)
        ):
            with patch("builtins.print") as printer:
                code = _cmd_toolsearch(_parse("context", "--json"))
        self.assertEqual(code, 0)
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        payload = json.loads(printed)
        self.assertEqual(payload["model_name"], "claude-sonnet-4.5")
        self.assertEqual(payload["tool_definitions_tokens"], 28763)

    def test_measurement_failure_exits_non_zero_with_a_reason(self) -> None:
        failure = ContextReportError("Copilot CLI を起動できません: RuntimeError: boom")
        with patch(
            "hve.toolsearch.context_report.collect", AsyncMock(side_effect=failure)
        ):
            with patch("builtins.print") as printer:
                code = _cmd_toolsearch(_parse("context"))
        self.assertNotEqual(code, 0)
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        self.assertIn("起動できません", printed)


if __name__ == "__main__":
    unittest.main()
