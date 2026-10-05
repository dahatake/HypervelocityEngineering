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
        args = _parse("context", "--workflow", "ard")
        self.assertEqual(args.toolsearch_command, "context")

    def test_context_accepts_the_json_flag(self) -> None:
        self.assertTrue(_parse("context", "--workflow", "ard", "--json").json)

    def test_context_requires_workflow(self) -> None:
        with self.assertRaises(SystemExit):
            _parse("context")

    def test_context_accepts_the_compare_flag(self) -> None:
        args = _parse("context", "--workflow", "ard", "--compare")
        self.assertTrue(args.compare)
        self.assertEqual(args.workflow, "ard")

    def test_context_accepts_an_optional_step(self) -> None:
        args = _parse("context", "--workflow", "aagd", "--step", "2.3")
        self.assertEqual(args.workflow, "aagd")
        self.assertEqual(args.step, "2.3")


class TestCommand(unittest.TestCase):
    def test_text_output_renders_the_report(self) -> None:
        with patch(
            "hve.toolsearch.context_report.collect",
            AsyncMock(return_value=_REPORT),
        ) as collect:
            with patch("builtins.print") as printer:
                code = _cmd_toolsearch(_parse("context", "--workflow", "ard"))
        self.assertEqual(code, 0)
        self.assertEqual(collect.await_args.kwargs["workflow_id"], "ard")
        self.assertIsNone(collect.await_args.kwargs["step_id"])
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        self.assertIn("claude-sonnet-4.5", printed)
        self.assertIn("azure", printed)

    def test_json_flag_outputs_machine_readable_payload(self) -> None:
        with patch(
            "hve.toolsearch.context_report.collect", AsyncMock(return_value=_REPORT)
        ):
            with patch("builtins.print") as printer:
                code = _cmd_toolsearch(_parse("context", "--workflow", "ard", "--json"))
        self.assertEqual(code, 0)
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        payload = json.loads(printed)
        self.assertEqual(payload["model_name"], "claude-sonnet-4.5")
        self.assertEqual(payload["tool_definitions_tokens"], 28763)

    def test_step_is_forwarded_to_collection(self) -> None:
        with patch(
            "hve.toolsearch.context_report.collect",
            AsyncMock(return_value=_REPORT),
        ) as collect:
            code = _cmd_toolsearch(
                _parse("context", "--workflow", "aagd", "--step", "2.3")
            )

        self.assertEqual(code, 0)
        self.assertEqual(collect.await_args.kwargs["workflow_id"], "aagd")
        self.assertEqual(collect.await_args.kwargs["step_id"], "2.3")

    def test_measurement_failure_exits_non_zero_with_a_reason(self) -> None:
        failure = ContextReportError("Copilot CLI を起動できません: RuntimeError: boom")
        with patch(
            "hve.toolsearch.context_report.collect", AsyncMock(side_effect=failure)
        ):
            with patch("builtins.print") as printer:
                code = _cmd_toolsearch(_parse("context", "--workflow", "ard"))
        self.assertNotEqual(code, 0)
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        self.assertIn("起動できません", printed)

    def test_compare_json_outputs_machine_readable_payload(self) -> None:
        with patch(
            "hve.toolsearch.context_report.collect_comparison",
            AsyncMock(return_value=object()),
        ) as collect_compare, patch(
            "hve.toolsearch.context_report.render_comparison_json",
            return_value='{"comparable": true, "reason": null}',
        ):
            with patch("builtins.print") as printer:
                code = _cmd_toolsearch(
                    _parse("context", "--workflow", "ard", "--compare", "--json")
                )
        self.assertEqual(code, 0)
        self.assertEqual(collect_compare.await_args.kwargs["workflow_id"], "ard")
        self.assertIsNone(collect_compare.await_args.kwargs["step_id"])
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        payload = json.loads(printed)
        self.assertTrue(payload["comparable"])

    def test_compare_side_failure_prints_payload_and_exits_non_zero(self) -> None:
        comparison = type(
            "ComparisonStub",
            (),
            {"has_failures": lambda self: True},
        )()
        with patch(
            "hve.toolsearch.context_report.collect_comparison",
            AsyncMock(return_value=comparison),
        ), patch(
            "hve.toolsearch.context_report.render_comparison_text",
            return_value="comparable: false\nreason: off_failed",
        ):
            with patch("builtins.print") as printer:
                code = _cmd_toolsearch(_parse("context", "--workflow", "ard", "--compare"))
        self.assertNotEqual(code, 0)
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        self.assertIn("off_failed", printed)


if __name__ == "__main__":
    unittest.main()
