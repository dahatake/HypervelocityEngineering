"""S9: HVE Tool Search ランキング差し替えの CLI / GUI / runner 配線（FR-TS-01）。

`--tool-search`（FR-MODEL-04、SDK 組み込みの有効化）とは **直交する別設定**であることを固定する。
"""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hve.config import SDKConfig
from hve.toolsearch.policy import ToolSearchPolicy
from hve.toolsearch.session import (
    RANKING_HVE,
    RANKING_SDK,
    VALID_RANKING_MODES,
    build_session_toolset,
    default_skill_roots,
    is_ranking_override_enabled,
    load_skill_manifest,
    record_session_usage,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUI_SOURCE = _REPO_ROOT / "hve" / "gui" / "page_options.py"
_SECTION_SOURCE = _REPO_ROOT / "hve" / "gui" / "toolsearch_settings_section.py"
_RUNNER_SOURCE = _REPO_ROOT / "hve" / "runner.py"


def _parse(*extra: str):
    from hve.__main__ import _build_parser

    return _build_parser().parse_args(["orchestrate", "--workflow", "ard", *extra])


class TestConfigField(unittest.TestCase):
    def test_default_is_sdk(self) -> None:
        self.assertEqual(SDKConfig().tool_search_ranking, RANKING_SDK)

    def test_default_keeps_tool_search_enabled(self) -> None:
        """FR-MODEL-04 の既定（有効）を変えていないこと。"""
        self.assertTrue(SDKConfig().tool_search)

    def test_env_override(self) -> None:
        original = os.environ.get("HVE_TOOL_SEARCH_RANKING")
        os.environ["HVE_TOOL_SEARCH_RANKING"] = "hve"
        try:
            self.assertEqual(SDKConfig.from_env().tool_search_ranking, RANKING_HVE)
        finally:
            if original is None:
                os.environ.pop("HVE_TOOL_SEARCH_RANKING", None)
            else:
                os.environ["HVE_TOOL_SEARCH_RANKING"] = original

    def test_env_absent_falls_back_to_sdk(self) -> None:
        original = os.environ.pop("HVE_TOOL_SEARCH_RANKING", None)
        try:
            self.assertEqual(SDKConfig.from_env().tool_search_ranking, RANKING_SDK)
        finally:
            if original is not None:
                os.environ["HVE_TOOL_SEARCH_RANKING"] = original


class TestCliFlag(unittest.TestCase):
    def test_default_is_none(self) -> None:
        self.assertIsNone(_parse().tool_search_ranking)

    def test_accepts_documented_values(self) -> None:
        for value in VALID_RANKING_MODES:
            self.assertEqual(_parse("--tool-search-ranking", value).tool_search_ranking, value)

    def test_rejects_undocumented_value(self) -> None:
        with self.assertRaises(SystemExit):
            _parse("--tool-search-ranking", "bm25")

    def test_appears_in_orchestrate_help(self) -> None:
        from hve.__main__ import _build_parser

        parser = _build_parser()
        sub = next(
            action
            for action in parser._actions
            if hasattr(action, "choices") and isinstance(action.choices, dict)
        )
        self.assertIn("--tool-search-ranking", sub.choices["orchestrate"].format_help())

    def test_is_independent_from_tool_search_flag(self) -> None:
        ns = _parse("--tool-search-ranking", "hve")
        self.assertIsNone(ns.tool_search)


class TestCliOverrideReachesConfig(unittest.TestCase):
    """CLI 値が実際の構築経路（`_build_config`）で SDKConfig へ届くこと。"""

    def _build(self, *extra: str):
        from hve.__main__ import _build_config

        return _build_config(_parse(*extra))

    def test_value_reaches_config(self) -> None:
        self.assertEqual(
            self._build("--tool-search-ranking", "hve").tool_search_ranking, RANKING_HVE
        )

    def test_unspecified_keeps_the_default(self) -> None:
        self.assertEqual(self._build().tool_search_ranking, RANKING_SDK)

    def test_ranking_does_not_override_explicit_disable(self) -> None:
        """FR-MODEL-06: ranking 指定が明示的な無効化を上書きしない。"""
        cfg = self._build("--tool-search-ranking", "hve", "--no-tool-search")
        self.assertFalse(cfg.tool_search)
        self.assertEqual(cfg.tool_search_ranking, RANKING_HVE)


class TestGuiArgs(unittest.TestCase):
    def test_default_is_none(self) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        self.assertIsNone(OrchestrateArgs(workflow="ard").tool_search_ranking)

    def test_default_emits_no_flag(self) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        self.assertNotIn("--tool-search-ranking", OrchestrateArgs(workflow="ard").to_argv())

    def test_value_round_trips_through_cli(self) -> None:
        from hve.__main__ import _build_parser
        from hve.gui.orchestrate_args import OrchestrateArgs

        args = OrchestrateArgs(workflow="ard")
        args.tool_search_ranking = RANKING_HVE
        ns = _build_parser().parse_args(args.to_argv())
        self.assertEqual(ns.tool_search_ranking, RANKING_HVE)


class TestGuiWidget(unittest.TestCase):
    """FR-GUI-07: 設定入力欄は設定画面の Tool-Search セクションが単独で所有する。"""

    def setUp(self) -> None:
        self.source = _SECTION_SOURCE.read_text(encoding="utf-8")

    def test_widget_exists(self) -> None:
        self.assertIn("self.tool_search_ranking = QComboBox()", self.source)
        self.assertIn("self.tool_search = QCheckBox(", self.source)

    def test_widget_offers_both_modes(self) -> None:
        start = self.source.index("self.tool_search_ranking = QComboBox()")
        block = self.source[start:start + 2000]
        self.assertIn('userData="sdk"', block)
        self.assertIn('userData="hve"', block)

    def test_settings_apply_binds_both_keys(self) -> None:
        from hve.gui.settings_apply import _SECTION_FIELDS

        self.assertEqual(
            _SECTION_FIELDS["TOOLSEARCH"],
            {"tool_search": "tool_search", "tool_search_ranking": "tool_search_ranking"},
        )

    def test_widget_disambiguates_from_the_foundry_setting(self) -> None:
        """利用者が Foundry Toolbox 側の設定と取り違えないようにする。"""
        self.assertIn("別物", self.source)

    def test_step1_pane_bridges_the_stored_value(self) -> None:
        page_options = _GUI_SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("self.tool_search_ranking = QComboBox()", page_options)
        self.assertIn('args.tool_search_ranking = "hve"', page_options)


class TestEnablement(unittest.TestCase):
    def test_requires_both_tool_search_and_hve_ranking(self) -> None:
        self.assertTrue(
            is_ranking_override_enabled(SimpleNamespace(tool_search=True, tool_search_ranking="hve"))
        )

    def test_disabled_when_tool_search_is_off(self) -> None:
        """SDK が tool_search_tool を呼ばないので差し替えても意味がない。"""
        self.assertFalse(
            is_ranking_override_enabled(SimpleNamespace(tool_search=False, tool_search_ranking="hve"))
        )

    def test_disabled_for_sdk_ranking(self) -> None:
        self.assertFalse(
            is_ranking_override_enabled(SimpleNamespace(tool_search=True, tool_search_ranking="sdk"))
        )

    def test_missing_attribute_defaults_to_disabled(self) -> None:
        self.assertFalse(is_ranking_override_enabled(SimpleNamespace(tool_search=True)))


class TestBuildSessionToolset(unittest.TestCase):
    def _config(self, **kw):
        base = {"tool_search": True, "tool_search_ranking": RANKING_HVE, "excluded_tools": ()}
        base.update(kw)
        return SimpleNamespace(**base)

    def test_disabled_returns_nothing(self) -> None:
        tools, context = build_session_toolset(
            self._config(tool_search_ranking=RANKING_SDK), repo_root=_REPO_ROOT
        )
        self.assertEqual(tools, [])
        self.assertIsNone(context)

    def test_enabled_returns_override_first_then_skill_tools(self) -> None:
        with TemporaryDirectory() as tmp:
            tools, context = build_session_toolset(
                self._config(),
                repo_root=_REPO_ROOT,
                workflow_id="ard",
                step_id="1",
                skill_roots=[_REPO_ROOT / ".github" / "skills"],
                usage_path=Path(tmp) / "usage.jsonl",
            )
        self.assertIsNotNone(context)
        self.assertEqual(tools[0].name, "tool_search_tool")
        self.assertTrue(tools[0].overrides_built_in_tool)
        self.assertGreater(len(tools), 30)
        self.assertTrue(all(t.name.startswith("skill_") for t in tools[1:]))

    def test_manifest_pins_reach_the_context(self) -> None:
        with TemporaryDirectory() as tmp:
            _, context = build_session_toolset(
                self._config(),
                repo_root=_REPO_ROOT,
                workflow_id="akm",
                step_id="1",
                skill_roots=[_REPO_ROOT / ".github" / "skills"],
                usage_path=Path(tmp) / "usage.jsonl",
            )
        assert context is not None
        self.assertEqual(
            context.manifest_pins.get("skill:skills:skill_knowledge-management"), "always"
        )

    def test_core_skills_are_not_deferred(self) -> None:
        with TemporaryDirectory() as tmp:
            tools, _ = build_session_toolset(
                self._config(),
                repo_root=_REPO_ROOT,
                workflow_id="akm",
                step_id="1",
                skill_roots=[_REPO_ROOT / ".github" / "skills"],
                usage_path=Path(tmp) / "usage.jsonl",
            )
        by_name = {t.name: t for t in tools}
        self.assertEqual(by_name["skill_knowledge-management"].defer, "never")
        self.assertEqual(by_name["skill_work-artifacts-layout"].defer, "never")
        self.assertEqual(by_name["skill_repo-onboarding-fast"].defer, "auto")

    def test_excluded_tools_reach_the_context(self) -> None:
        with TemporaryDirectory() as tmp:
            _, context = build_session_toolset(
                self._config(excluded_tools=("bash",)),
                repo_root=_REPO_ROOT,
                skill_roots=[_REPO_ROOT / ".github" / "skills"],
                usage_path=Path(tmp) / "usage.jsonl",
            )
        assert context is not None
        self.assertIn("bash", context.excluded_tools)

    def test_missing_skill_roots_are_tolerated(self) -> None:
        tools, context = build_session_toolset(
            self._config(), repo_root=_REPO_ROOT, skill_roots=[Path("no-such-dir-xyz")]
        )
        self.assertEqual([t.name for t in tools], ["tool_search_tool"])
        self.assertIsNotNone(context)

    def test_repo_local_policy_override_is_used_at_runtime(self) -> None:
        """FR-TS-03: 実行時だけ `.toolsearch/policy.json` を無視すると、GUI の表示・保存先と食い違う。"""
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            local = repo / ".toolsearch" / "policy.json"
            local.parent.mkdir(parents=True)
            raw = json.loads(
                ToolSearchPolicy.default_path().read_text(encoding="utf-8")
            )
            raw["limit"] = 2
            raw["tau"] = 0.9
            local.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

            _, context = build_session_toolset(
                self._config(),
                repo_root=repo,
                skill_roots=[Path("no-such-dir-xyz")],
                usage_path=repo / "usage.jsonl",
            )
        assert context is not None
        self.assertEqual(context.policy.limit, 2)
        self.assertEqual(context.policy.tau, 0.9)

    def test_packaged_policy_is_used_when_the_repo_has_no_override(self) -> None:
        packaged = ToolSearchPolicy.load()
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _, context = build_session_toolset(
                self._config(),
                repo_root=repo,
                skill_roots=[Path("no-such-dir-xyz")],
                usage_path=repo / "usage.jsonl",
            )
        assert context is not None
        self.assertEqual(context.policy, packaged)


class TestToolSearchSkillsLayerUi(unittest.TestCase):
    def test_skill_layer_tab_exists(self) -> None:
        from PySide6.QtWidgets import QApplication
        from hve.gui.toolsearch_settings_section import ToolSearchSection

        app = QApplication.instance() or QApplication([])
        section = ToolSearchSection(repo_root=_REPO_ROOT)
        self.assertIn("Skill Layer", section.tab_labels())
        section.deleteLater()
        _ = app


class TestStandaloneEntryPoint(unittest.TestCase):
    """別リポジトリを対象に単独起動できること（GUI は起動しない範囲で検証）。"""

    def test_rejects_a_non_directory_repo_root(self) -> None:
        from hve.gui.toolsearch_standalone import main

        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "no-such-repo"
            self.assertEqual(main([str(missing)]), 2)

    def test_version_flag_exits_cleanly(self) -> None:
        from hve.gui.toolsearch_standalone import main

        with self.assertRaises(SystemExit) as ctx:
            main(["--version"])
        self.assertEqual(ctx.exception.code, 0)


class TestSupportHelpers(unittest.TestCase):
    def test_default_skill_roots_include_repo_and_user_scope(self) -> None:
        roots = default_skill_roots(_REPO_ROOT)
        self.assertIn(_REPO_ROOT / ".github" / "skills", roots)
        self.assertEqual(len(roots), 3)

    def test_skill_manifest_loads(self) -> None:
        self.assertIn("workflow_defaults", load_skill_manifest(_REPO_ROOT))

    def test_skill_manifest_missing_is_empty(self) -> None:
        with TemporaryDirectory() as tmp:
            self.assertEqual(load_skill_manifest(tmp), {})

    def test_record_session_usage_writes(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.jsonl"
            written = record_session_usage(
                ["mcp:azure:a"],
                session_id="s1",
                workflow_id="ard",
                step_id="1",
                usage_path=path,
            )
        self.assertEqual(written, 1)

    def test_record_session_usage_skips_without_scope(self) -> None:
        self.assertEqual(
            record_session_usage(["x"], session_id="s", workflow_id=None, step_id=None), 0
        )

    def test_record_session_usage_skips_empty(self) -> None:
        self.assertEqual(
            record_session_usage([], session_id="s", workflow_id="ard", step_id="1"), 0
        )


class _FakeConsole:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.events: list[str] = []

    def warning(self, message: str) -> None:
        self.warnings.append(str(message))

    def event(self, message: str) -> None:
        self.events.append(str(message))


class _FakeClient:
    def __init__(self, unsupported: tuple[str, ...]) -> None:
        self.unsupported = unsupported
        self.calls: list[dict] = []

    async def create_session(self, **kwargs):
        self.calls.append(dict(kwargs))
        for keyword in self.unsupported:
            if keyword in kwargs:
                raise TypeError(
                    f"create_session() got an unexpected keyword argument '{keyword}'"
                )
        return object()


class TestTypeErrorStripIsNotSilent(unittest.TestCase):
    """S9: 未サポート引数を無言で剥がすと機能が消えたことに気付けない。"""

    def _run(self, opts, unsupported):
        from hve.runner import _create_session_with_auto_reasoning_fallback

        client = _FakeClient(unsupported)
        console = _FakeConsole()
        session = asyncio.run(
            _create_session_with_auto_reasoning_fallback(
                client, dict(opts), console=console
            )
        )
        return session, client, console

    def test_stripped_keyword_is_warned(self) -> None:
        _, client, console = self._run({"tool_search": {"enabled": True}}, ("tool_search",))
        self.assertTrue(any("tool_search" in w for w in console.warnings))
        self.assertNotIn("tool_search", client.calls[-1])

    def test_cloud_keeps_its_dedicated_message(self) -> None:
        _, _, console = self._run({"cloud": {"x": 1}}, ("cloud",))
        self.assertTrue(any("Cloud Session" in w for w in console.warnings))

    def test_no_warning_when_everything_is_supported(self) -> None:
        _, _, console = self._run({"tool_search": {"enabled": True}}, ())
        self.assertEqual(console.warnings, [])


class TestRunnerWiring(unittest.TestCase):
    """runner がヘルパー経由で差し替えツールを注入していること。"""

    def setUp(self) -> None:
        self.source = _RUNNER_SOURCE.read_text(encoding="utf-8")

    def test_runner_imports_the_helper(self) -> None:
        self.assertIn("from .toolsearch.session import build_session_toolset", self.source)

    def test_injection_is_inside_the_tool_search_block(self) -> None:
        start = self.source.index('session_opts["tool_search"] = {"enabled": True}')
        block = self.source[start:start + 3200]
        self.assertIn("build_session_toolset(", block)
        self.assertIn('session_opts["tools"]', block)

    def test_injection_failure_does_not_break_the_step(self) -> None:
        start = self.source.index('session_opts["tool_search"] = {"enabled": True}')
        block = self.source[start:start + 3200]
        self.assertIn("except Exception", block)


class TestResolveCalledToolIds(unittest.TestCase):
    """FR-TS-07: 呼ばれたツール名を id へ解決する（名前から id を推測しない）。"""

    def _context(self):
        from hve.toolsearch.metatool import ToolSearchContext, decide_catalog
        from hve.toolsearch.policy import ToolSearchPolicy

        context = ToolSearchContext(policy=ToolSearchPolicy.load())
        decide_catalog(
            context,
            [
                SimpleNamespace(
                    name="azmcp_group_list",
                    description="d",
                    mcp_server_name="azure",
                    mcp_tool_name=None,
                    namespaced_name=None,
                    input_schema=None,
                    defer_loading=True,
                )
            ],
        )
        return context

    def test_known_names_resolve_to_ids(self) -> None:
        from hve.toolsearch.session import resolve_called_tool_ids

        self.assertEqual(
            resolve_called_tool_ids(self._context(), ["azmcp_group_list"]),
            ["mcp:azure:azmcp_group_list"],
        )

    def test_unknown_names_are_dropped_not_guessed(self) -> None:
        from hve.toolsearch.session import resolve_called_tool_ids

        self.assertEqual(resolve_called_tool_ids(self._context(), ["bash", "read_file"]), [])

    def test_duplicates_collapse(self) -> None:
        from hve.toolsearch.session import resolve_called_tool_ids

        resolved = resolve_called_tool_ids(
            self._context(), ["azmcp_group_list", "azmcp_group_list"]
        )
        self.assertEqual(len(resolved), 1)

    def test_missing_context_yields_nothing(self) -> None:
        from hve.toolsearch.session import resolve_called_tool_ids

        self.assertEqual(resolve_called_tool_ids(None, ["x"]), [])


class TestRunnerUsageRecording(unittest.TestCase):
    """runner が Step 終了時に利用履歴を記録する経路を持つこと。"""

    def setUp(self) -> None:
        self.source = _RUNNER_SOURCE.read_text(encoding="utf-8")

    def test_runner_defines_the_recording_hook(self) -> None:
        self.assertIn("def _record_toolsearch_usage(self, step_id: str) -> None:", self.source)

    def test_hook_runs_in_the_step_cleanup(self) -> None:
        start = self.source.index("self._clear_tool_start_state(step_id)\n            self._record")
        self.assertGreater(start, 0)

    def test_called_tool_names_are_accumulated(self) -> None:
        self.assertIn("self._toolsearch_called_tools.append(str(tool_name))", self.source)

    def test_recording_failure_does_not_break_the_step(self) -> None:
        start = self.source.index("def _record_toolsearch_usage")
        body = self.source[start:self.source.index("def _track_tool_files", start)]
        self.assertIn("except Exception", body)

    def test_session_id_is_not_deterministic_per_step(self) -> None:
        """決定論的 ID だと session 数が増えず、自動 pin のウォームアップに到達しない。"""
        start = self.source.index("def _record_toolsearch_usage")
        body = self.source[start:self.source.index("def _track_tool_files", start)]
        session_id_line = next(
            line for line in body.splitlines() if line.strip().startswith("session_id=")
        )
        self.assertIn("run_id", session_id_line)
        self.assertNotIn("_make_step_session_id", session_id_line)


class TestCloudIsGatedUntilMeasured(unittest.TestCase):
    """G4 未実測のため Cloud 経路では差し替えない。"""

    def test_explicit_enabled_false_disables_the_override(self) -> None:
        tools, context = build_session_toolset(
            SimpleNamespace(tool_search=True, tool_search_ranking=RANKING_HVE, excluded_tools=()),
            repo_root=_REPO_ROOT,
            enabled=False,
        )
        self.assertEqual(tools, [])
        self.assertIsNone(context)

    def test_runner_gates_on_cloud_session(self) -> None:
        source = _RUNNER_SOURCE.read_text(encoding="utf-8")
        start = source.index("build_session_toolset(")
        self.assertIn("should_use_cloud_session", source[start:start + 1200])


class TestRunnerStatsWiring(unittest.TestCase):
    """FR-TS-09: runner が統計収集シンクを `on_event` へ配線していること。"""

    def setUp(self) -> None:
        self.source = _RUNNER_SOURCE.read_text(encoding="utf-8")

    def test_runner_passes_on_event(self) -> None:
        start = self.source.index("build_session_toolset(")
        self.assertIn("on_event=", self.source[start:start + 800])

    def test_collector_is_built_from_the_stats_module(self) -> None:
        self.assertIn("StatsCollector", self.source)

    def test_build_session_toolset_accepts_a_sink(self) -> None:
        from hve.toolsearch.stats import StatsCollector

        with TemporaryDirectory() as tmp:
            tools, context = build_session_toolset(
                SimpleNamespace(
                    tool_search=True, tool_search_ranking=RANKING_HVE, excluded_tools=()
                ),
                repo_root=_REPO_ROOT,
                workflow_id="ard",
                step_id="1.1",
                on_event=StatsCollector(path=Path(tmp) / "events.jsonl"),
            )
        self.assertTrue(tools)
        self.assertIsNotNone(context)


if __name__ == "__main__":
    unittest.main()
