"""test_workiq.py — Work IQ の capability / tool lifecycle メタデータ抽出の残存契約。

Work IQ への問い合わせ・応答書式の検証は FR-KD-10 で廃止した（知識探索へ置換）。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import workiq  # type: ignore[import-untyped]


class TestWorkIQConstants(unittest.TestCase):
    def test_mcp_server_name_constant(self) -> None:
        self.assertEqual(workiq.WORKIQ_MCP_SERVER_NAME, "workiq")



class TestExtractToolNameFromEvent(unittest.TestCase):
    """extract_tool_name_from_event() のユニットテスト。"""

    def _make_event(self, etype, data):
        import types
        return types.SimpleNamespace(
            type=types.SimpleNamespace(value=etype),
            data=data,
        )

    def test_extracts_from_data_tool_name_attr(self) -> None:
        import types
        data = types.SimpleNamespace(tool_name="ask", toolName=None, name=None)
        event = self._make_event("tool.execution_start", data)
        self.assertEqual(workiq.extract_tool_name_from_event(event), "ask")

    def test_extracts_from_data_toolName_attr(self) -> None:
        import types
        data = types.SimpleNamespace(tool_name=None, toolName="search_emails", name=None)
        event = self._make_event("tool.execution_start", data)
        self.assertEqual(workiq.extract_tool_name_from_event(event), "search_emails")

    def test_extracts_from_data_name_attr(self) -> None:
        import types
        data = types.SimpleNamespace(tool_name=None, toolName=None, name="get_calendar")
        event = self._make_event("tool.execution_start", data)
        self.assertEqual(workiq.extract_tool_name_from_event(event), "get_calendar")

    def test_extracts_from_data_dict_tool_name(self) -> None:
        event = self._make_event("tool.execution_start", {"tool_name": "search_files"})
        self.assertEqual(workiq.extract_tool_name_from_event(event), "search_files")

    def test_extracts_from_data_dict_toolName(self) -> None:
        event = self._make_event("tool.execution_start", {"toolName": "search_people"})
        self.assertEqual(workiq.extract_tool_name_from_event(event), "search_people")

    def test_extracts_from_data_dict_name(self) -> None:
        event = self._make_event("tool.execution_start", {"name": "search_messages"})
        self.assertEqual(workiq.extract_tool_name_from_event(event), "search_messages")

    def test_extracts_from_mcp_tool_name_attr(self) -> None:
        import types
        data = types.SimpleNamespace(mcp_tool_name="ask", mcp_server_name="other-server")
        event = self._make_event("tool.execution_start", data)
        self.assertEqual(workiq.extract_tool_name_from_event(event), "ask")

    def test_extracts_from_mcp_toolName_dict(self) -> None:
        event = self._make_event(
            "tool.execution_start",
            {"mcpToolName": "search_emails", "mcpServerName": "other-server"},
        )
        self.assertEqual(workiq.extract_tool_name_from_event(event), "search_emails")

    def test_returns_none_for_non_tool_execution_event(self) -> None:
        import types
        data = types.SimpleNamespace(tool_name="ask")
        event = self._make_event("assistant.message_delta", data)
        self.assertIsNone(workiq.extract_tool_name_from_event(event))

    def test_returns_none_when_no_data(self) -> None:
        import types
        event = types.SimpleNamespace(
            type=types.SimpleNamespace(value="tool.execution_start"),
            data=None,
        )
        self.assertIsNone(workiq.extract_tool_name_from_event(event))

    def test_returns_none_when_no_type(self) -> None:
        import types
        event = types.SimpleNamespace(type=None, data={"tool_name": "ask"})
        self.assertIsNone(workiq.extract_tool_name_from_event(event))

    def test_handles_exception_gracefully(self) -> None:
        # 例外が発生しても None を返す
        self.assertIsNone(workiq.extract_tool_name_from_event(None))
        self.assertIsNone(workiq.extract_tool_name_from_event("not_an_event"))

    def test_event_type_as_string(self) -> None:
        """event.type が文字列の場合も対応すること。"""
        import types
        data = types.SimpleNamespace(tool_name="ask", toolName=None, name=None)
        # type が enum でなく文字列の場合: getattr(etype_obj, "value", str(etype_obj)) で str になる
        event = types.SimpleNamespace(type="tool.execution_start", data=data)
        self.assertEqual(workiq.extract_tool_name_from_event(event), "ask")


class TestWorkIQSDKOnlySurface(unittest.TestCase):
    """FR-CLI-91 / FR-KD-10: HVE-owned runtime と Work IQ 専用の問い合わせ処理を公開しない。"""

    _REMOVED_SYMBOLS = (
        "resolve_npx_command",
        "is_workiq_available",
        "workiq_login",
        "_is_safe_https_url",
        "_safe_remote_mcp_config",
        "_resolve_workiq_cli_path",
        "ensure_workiq_plugin_authenticated",
        "WorkIQDiagnosticCheck",
        "WorkIQDiagnosticReport",
        "build_workiq_mcp_config",
        "_workiq_diagnostic_permission_handler",
        "_append_workiq_tool_count_check",
        "probe_workiq_mcp_startup",
        "probe_workiq_copilot_session",
        "probe_workiq_copilot_tool_invocation",
        "run_workiq_diagnostics",
        "_run_legacy_workiq_diagnostics",
        "_is_headless_environment",
        "_has_cached_token",
        "query_workiq_per_question",
        "format_workiq_draft_answers",
        "enrich_prompt_with_workiq",
        "evaluate_workiq_qa_merge_decision",
        "run_workiq_event_extractor_self_test",
        "format_sdk_event_trace_line",
        "WORKIQ_MCP_QUERY_TOOL_NAMES",
        "WORKIQ_MCP_SERVER_NAMES",
        "_WORKIQ_MCP_TOOL_NAMES_BY_SERVER",
        "query_workiq",
        "query_workiq_detailed",
        "get_workiq_prompt_template",
        "save_workiq_result",
        "build_workiq_session_options",
        "inspect_workiq_session",
        "validate_workiq_content_contract",
        "is_workiq_result_mergeable",
        "build_akm_workiq_query_targets",
        "WORKIQ_MCP_TOOL_NAMES",
    )

    def test_hve_owned_runtime_and_legacy_alias_symbols_are_absent(self) -> None:
        for symbol in self._REMOVED_SYMBOLS:
            with self.subTest(symbol=symbol):
                self.assertFalse(hasattr(workiq, symbol), symbol)

    def test_capability_snapshot_does_not_retain_raw_mcp_config(self) -> None:
        self.assertNotIn("mcp_config", workiq.WorkIQCapability.__dataclass_fields__)

    def test_module_contains_no_legacy_runtime_markers(self) -> None:
        source = Path(workiq.__file__).read_text(encoding="utf-8")
        for marker in (
            "@microsoft/workiq",
            "WORKIQ_NPX_COMMAND",
            "workiq-doctor",
            "_hve_workiq",
            "workiq-preview",
            "oauth.login",
            "webbrowser",
            "subprocess",
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, source)


if __name__ == "__main__":
    unittest.main()
