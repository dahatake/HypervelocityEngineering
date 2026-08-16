"""FR-TS-03: ポリシー解決と Core / Long-tail 振り分けのテスト。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hve.toolsearch import build_catalog
from hve.toolsearch.policy import (
    _POLICY_FILE,
    POLICY_KEY_RE,
    PolicyError,
    ToolSearchPolicy,
    apply_policy,
)
from hve.toolsearch.types import ToolEntry

_BASE = {
    "version": 1,
    "limit": 5,
    "max_limit": 10,
    "tau": 0.4,
    "field_weights": {
        "name": 3.0,
        "additional_search_text": 2.5,
        "description": 2.0,
        "arg_terms": 1.0,
    },
    "pins": {},
    "additional_search_text": {},
    "step_overrides": {},
}


def _policy(**overrides) -> ToolSearchPolicy:
    raw = dict(_BASE)
    raw.update(overrides)
    return ToolSearchPolicy.from_dict(raw)


def _entry(name: str, *, kind: str = "mcp", server: str = "azure") -> ToolEntry:
    return ToolEntry(
        id=ToolEntry.make_id(kind, server, name),  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        server=server,
        name=name,
        description=f"desc of {name}",
    )


class TestPolicyValidation(unittest.TestCase):
    def test_rejects_bare_tool_name_key_at_load_time(self) -> None:
        with self.assertRaises(PolicyError) as ctx:
            _policy(pins={"execute_query": "always"})
        self.assertIn("bare tool names are rejected", str(ctx.exception))

    def test_accepts_id_and_server_wildcard_keys(self) -> None:
        policy = _policy(pins={"mcp:azure:x": "always", "skill:skills:*": "auto"})
        self.assertEqual(policy.pin_for("mcp:azure:x"), "always")

    def test_rejects_unknown_pin_mode(self) -> None:
        with self.assertRaises(PolicyError):
            _policy(pins={"mcp:azure:x": "pinned"})

    def test_rejects_missing_required_field(self) -> None:
        raw = dict(_BASE)
        del raw["tau"]
        with self.assertRaises(PolicyError):
            ToolSearchPolicy.from_dict(raw)

    def test_rejects_incomplete_field_weights(self) -> None:
        with self.assertRaises(PolicyError):
            _policy(field_weights={"name": 1.0})

    def test_rejects_limit_greater_than_max_limit(self) -> None:
        with self.assertRaises(PolicyError):
            _policy(limit=20)

    def test_rejects_tau_outside_unit_interval(self) -> None:
        with self.assertRaises(PolicyError):
            _policy(tau=1.5)

    def test_rejects_unknown_step_mode(self) -> None:
        with self.assertRaises(PolicyError):
            _policy(step_overrides={"asdw-web:1.2": {"mode": "off"}})

    def test_load_reports_missing_file_as_policy_error(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(PolicyError):
                ToolSearchPolicy.load(Path(tmp) / "nope.json")

    def test_load_reports_broken_json_as_policy_error(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text("{ not json", encoding="utf-8")
            with self.assertRaises(PolicyError):
                ToolSearchPolicy.load(path)


class TestShippedPolicy(unittest.TestCase):
    """同梱 policy.json が契約を満たし、Core / Long-tail が振り分けられていること。"""

    def setUp(self) -> None:
        self.policy = ToolSearchPolicy.load()

    def test_shipped_policy_loads(self) -> None:
        self.assertEqual(self.policy.version, 1)
        self.assertEqual(self.policy.limit, 5)
        self.assertEqual(self.policy.max_limit, 10)

    def test_every_key_matches_the_published_pattern(self) -> None:
        raw = json.loads(_POLICY_FILE.read_text(encoding="utf-8"))
        for table in ("pins", "additional_search_text"):
            for key in raw[table]:
                self.assertRegex(key, POLICY_KEY_RE, msg=f"{table}.{key}")

    def test_native_hve_tools_are_core(self) -> None:
        self.assertEqual(self.policy.pin_for("native:hve:search_markdown"), "always")

    def test_azure_mcp_is_long_tail(self) -> None:
        self.assertEqual(self.policy.pin_for("mcp:azure:azmcp_group_list"), "auto")

    def test_mandatory_skills_are_core(self) -> None:
        for skill in ("skill_agent-common-preamble", "skill_work-artifacts-layout", "skill_task-dag-planning"):
            self.assertEqual(self.policy.pin_for(f"skill:skills:{skill}"), "always", msg=skill)

    def test_other_skills_stay_searchable(self) -> None:
        self.assertEqual(self.policy.pin_for("skill:skills:skill_azure-kusto"), "auto")

    def test_vague_native_names_have_search_vocabulary(self) -> None:
        text = self.policy.search_text_for("native:hve:search_markdown")
        self.assertIn("仕様", text)

    def test_fail_closed_steps_are_pin_only(self) -> None:
        self.assertEqual(self.policy.mode_for_step("asdw-web", "1.2"), "pin_only")
        self.assertEqual(self.policy.mode_for_step("asdw-web", "1.3"), "pin_only")
        self.assertEqual(self.policy.mode_for_step("asdw-web", "2.1"), "search")
        self.assertEqual(self.policy.mode_for_step(None, None), "search")


class TestEffectiveLimit(unittest.TestCase):
    def test_defaults_to_policy_limit(self) -> None:
        self.assertEqual(_policy().effective_limit(None), 5)

    def test_clamps_to_max_limit(self) -> None:
        self.assertEqual(_policy().effective_limit(99), 10)

    def test_floors_at_one(self) -> None:
        self.assertEqual(_policy().effective_limit(0), 1)


class TestApplyPolicy(unittest.TestCase):
    def test_splits_pinned_and_searchable(self) -> None:
        decision = apply_policy(
            [_entry("core"), _entry("tail")],
            _policy(pins={"mcp:azure:core": "always"}),
        )
        self.assertEqual([e.name for e in decision.pinned], ["core"])
        self.assertEqual([e.name for e in decision.searchable], ["tail"])

    def test_never_means_never_pinned_not_hidden(self) -> None:
        """`never` は「pin しない」であって「隠す」ではない（S2 レビュー Critical）。"""
        decision = apply_policy([_entry("tail")], _policy(pins={"mcp:azure:tail": "never"}))
        self.assertEqual(decision.pinned, ())
        self.assertEqual([e.name for e in decision.searchable], ["tail"])
        self.assertEqual(decision.dropped, ())

    def test_never_is_excluded_from_auto_pin_candidates(self) -> None:
        decision = apply_policy(
            [_entry("a"), _entry("b")],
            _policy(pins={"mcp:azure:a": "never"}),
        )
        self.assertEqual([e.name for e in decision.auto_pin_candidates], ["b"])

    def test_only_excluded_tools_remove_entries_from_the_index(self) -> None:
        decision = apply_policy([_entry("blocked"), _entry("ok")], _policy(), excluded_tools=["blocked"])
        self.assertIn("mcp:azure:blocked", decision.dropped)
        self.assertEqual([e.name for e in decision.searchable], ["ok"])

    def test_pin_only_empties_searchable_but_keeps_pinned(self) -> None:
        decision = apply_policy(
            [_entry("core"), _entry("tail")],
            _policy(pins={"mcp:azure:core": "always"}),
            pin_only=True,
        )
        self.assertEqual([e.name for e in decision.pinned], ["core"])
        self.assertEqual(decision.searchable, ())

    def test_applies_additional_search_text_from_policy(self) -> None:
        decision = apply_policy(
            [_entry("execute_query")],
            _policy(additional_search_text={"mcp:azure:execute_query": "分析 ダッシュボード SQL"}),
        )
        self.assertIn("ダッシュボード", decision.searchable[0].additional_search_text)

    def test_server_wildcard_does_not_leak_across_servers(self) -> None:
        decision = apply_policy(
            [_entry("x", server="azure"), _entry("x", server="other")],
            _policy(pins={"mcp:azure:*": "always"}),
        )
        self.assertEqual([e.server for e in decision.pinned], ["azure"])
        self.assertEqual([e.server for e in decision.searchable], ["other"])

    def test_manifest_pins_take_precedence_over_policy_pins(self) -> None:
        """FR-TS-03: skill_manifest 由来 pin > policy.json の pins。"""
        entry = _entry("skill_knowledge-management", kind="skill", server="skills")
        decision = apply_policy(
            [entry],
            _policy(pins={"skill:skills:*": "auto"}),
            manifest_pins={"skill:skills:skill_knowledge-management": "always"},
        )
        self.assertEqual([e.name for e in decision.pinned], ["skill_knowledge-management"])

    def test_manifest_pins_do_not_affect_unrelated_entries(self) -> None:
        decision = apply_policy(
            [_entry("other", kind="skill", server="skills")],
            _policy(),
            manifest_pins={"skill:skills:skill_x": "always"},
        )
        self.assertEqual([e.name for e in decision.searchable], ["other"])


class TestEnforcementBoundary(unittest.TestCase):
    """FR-TS-03: ランカーは安全境界ではないことを明示する。"""

    def test_module_documents_that_it_is_not_a_security_boundary(self) -> None:
        from hve.toolsearch import policy as policy_module

        doc = policy_module.__doc__ or ""
        self.assertIn("excluded_tools", doc)
        self.assertIn("安全境界として扱ってはならない", doc)

    def test_apply_policy_cannot_block_a_call_it_only_filters_output(self) -> None:
        """pin_only でも dropped 以外のエントリは実在し続ける（呼び出し禁止ではない）。"""
        entries = [_entry("tail")]
        decision = apply_policy(entries, _policy(), pin_only=True)
        self.assertEqual(decision.searchable, ())
        self.assertNotIn("mcp:azure:tail", decision.dropped)


class TestSkillKindRouting(unittest.TestCase):
    """FR-TS-06 の前提: skill_ 接頭辞のツールが skill 種別へ分類されること。"""

    def test_skill_prefixed_tool_becomes_skill_kind(self) -> None:
        meta = SimpleNamespace(
            name="skill_adversarial-review",
            description="",
            mcp_server_name=None,
            input_schema=None,
            defer_loading=True,
        )
        catalog = build_catalog([meta])
        self.assertEqual(catalog[0].kind, "skill")
        self.assertEqual(catalog[0].id, "skill:skills:skill_adversarial-review")


class TestSave(unittest.TestCase):
    """FR-GUI-07: `policy.json` の保存 API（GUI からの編集を支える書き込み経路）。"""

    def _write(self, path: Path, raw: dict) -> None:
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_to_dict_round_trips_through_from_dict(self) -> None:
        original = _policy(
            pins={"mcp:azure:x": "always"},
            additional_search_text={"native:hve:search_code": "実装 定義"},
            step_overrides={"asdw-web:1.2": {"mode": "pin_only"}},
        )
        self.assertEqual(ToolSearchPolicy.from_dict(original.to_dict()), original)

    def test_round_trip_preserves_every_field(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            self._write(path, _BASE)
            original = _policy(
                limit=3,
                max_limit=7,
                tau=0.25,
                pins={"mcp:azure:*": "never"},
                additional_search_text={"native:hve:search_markdown": "仕様 要件"},
                step_overrides={"asdw-web:1.3": {"mode": "pin_only"}},
            )
            original.save(path)
            self.assertEqual(ToolSearchPolicy.load(path), original)

    def test_preserves_unknown_top_level_keys(self) -> None:
        """同梱ファイルの `_comment` を保存で失わないこと。"""
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            self._write(path, {**_BASE, "_comment": "キー形式の説明"})
            _policy(limit=2).save(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["_comment"], "キー形式の説明")
            self.assertEqual(raw["limit"], 2)

    def test_writes_lf_without_bom(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            self._write(path, _BASE)
            _policy().save(path)
            data = path.read_bytes()
            self.assertNotIn(b"\r\n", data)
            self.assertFalse(data.startswith(b"\xef\xbb\xbf"))

    def test_keeps_non_ascii_readable(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            self._write(path, _BASE)
            _policy(additional_search_text={"native:hve:search_code": "実装 定義"}).save(path)
            self.assertIn("実装 定義", path.read_text(encoding="utf-8"))

    def test_invalid_payload_raises_and_leaves_the_file_untouched(self) -> None:
        """検証を経ずに組み立てた不正なポリシーでファイルを壊さないこと（fail-closed）。"""
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            self._write(path, _BASE)
            before = path.read_bytes()
            invalid = ToolSearchPolicy(
                version=1,
                limit=20,
                max_limit=10,
                tau=0.4,
                field_weights=dict(_BASE["field_weights"]),
                pins={},
                additional_search_text={},
                step_overrides={},
            )
            with self.assertRaises(PolicyError):
                invalid.save(path)
            self.assertEqual(path.read_bytes(), before)

    def test_invalid_key_is_rejected_before_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            self._write(path, _BASE)
            before = path.read_bytes()
            invalid = ToolSearchPolicy(
                version=1,
                limit=5,
                max_limit=10,
                tau=0.4,
                field_weights=dict(_BASE["field_weights"]),
                pins={"execute_query": "always"},
                additional_search_text={},
                step_overrides={},
            )
            with self.assertRaises(PolicyError):
                invalid.save(path)
            self.assertEqual(path.read_bytes(), before)

    def test_broken_existing_file_is_not_silently_overwritten(self) -> None:
        """既存ファイルを読めないと未知キーの保持を保証できないため書かない。"""
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text("{ not json", encoding="utf-8")
            with self.assertRaises(PolicyError):
                _policy().save(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "{ not json")


if __name__ == "__main__":
    unittest.main()
