"""test_local_surface_option_parity.py — FR-LOCAL-SURFACE-01 の機械検査。

ローカル 3 面（直接 `orchestrate` CLI / GUI Orchestrator / Prompt 版）の設定が
どこかの面から欠落したまま気付かれない事故を防ぐ。

検証項目:
  1. `orchestrate` の全 CLI dest が 5 分類のいずれかへ属し、未分類が残らないこと
  2. 分類が排他であること
  3. shared setting が 4 箇所（設定ストア既定値 / セクション表 / `OrchestrateArgs` /
     Prompt allowlist）すべてへ登録されていること
  4. workflow param が CLI フラグと `WorkflowDef.params` の両方に存在すること
  5. 別名・除外の宣言が実態と一致すること（宣言だけ残る腐敗を防ぐ）

根拠: hve-dev/requirement-definition.md §5.21 FR-LOCAL-SURFACE-01
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import unittest
from dataclasses import fields
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = _REPO_ROOT / "hve" / "tests" / "fixtures" / "option_parity_matrix.yaml"

sys.path.insert(0, str(_REPO_ROOT / "hve"))
_spec = _ilu.spec_from_file_location(
    "hve_main_local_surface_parity", str(_REPO_ROOT / "hve" / "__main__.py")
)
assert _spec is not None and _spec.loader is not None
_main_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_main_mod)

from hve.gui import settings_apply, settings_store
from hve.gui.orchestrate_args import OrchestrateArgs
from hve.prompt_request import ALLOWED_SETTINGS_OVERRIDES
from hve.workflow_registry import list_workflows


def _fixture() -> dict:
    return yaml.safe_load(_FIXTURE.read_text(encoding="utf-8"))


def _orchestrate_actions() -> list:
    parser = _main_mod._build_parser()
    subparsers = parser._subparsers._group_actions[0]
    return list(subparsers.choices["orchestrate"]._actions)


def _orchestrate_dests() -> set:
    return {a.dest for a in _orchestrate_actions() if a.dest != "help"}


def _orchestrate_flags() -> set:
    flags = set()
    for action in _orchestrate_actions():
        flags.update(action.option_strings)
    return flags


def _args_fields() -> set:
    return {f.name for f in fields(OrchestrateArgs)}


def _persisted_settings_keys() -> set:
    return {key for fields_ in settings_apply._SECTION_FIELDS.values() for key in fields_}


class TestFixtureDeclarationsAreSound(unittest.TestCase):
    def test_all_declared_sections_exist(self) -> None:
        fx = _fixture()
        for key in (
            "local_surface_shared_settings",
            "local_surface_settings_key_aliases",
            "local_surface_workflow_params",
            "orchestrate_cli_dest_aliases",
            "local_surface_excluded_cli_dests",
        ):
            self.assertIn(key, fx, f"{key} が fixture にありません")

    def test_classifications_are_mutually_exclusive(self) -> None:
        fx = _fixture()
        shared = set(fx["local_surface_shared_settings"])
        workflow = set(fx["local_surface_workflow_params"])
        aliases = set(fx["orchestrate_cli_dest_aliases"])
        excluded = set(fx["local_surface_excluded_cli_dests"])
        groups = {
            "shared": shared,
            "workflow_param": workflow,
            "alias": aliases,
            "excluded": excluded,
        }
        names = sorted(groups)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                overlap = groups[a] & groups[b]
                self.assertFalse(overlap, f"{a} と {b} が重複: {sorted(overlap)}")

    def test_every_exclusion_states_a_reason(self) -> None:
        for dest, reason in _fixture()["local_surface_excluded_cli_dests"].items():
            with self.subTest(dest=dest):
                self.assertTrue(
                    isinstance(reason, str) and reason.strip(),
                    f"{dest} の除外に根拠が書かれていません",
                )


class TestEveryCliDestIsClassified(unittest.TestCase):
    """未分類の CLI dest が残ると、面ごとの欠落を検出できなくなる。"""

    def test_no_unclassified_dest_remains(self) -> None:
        fx = _fixture()
        classified = (
            _args_fields()
            | set(fx["orchestrate_cli_dest_aliases"])
            | set(fx["local_surface_excluded_cli_dests"])
        )
        unclassified = sorted(_orchestrate_dests() - classified)
        self.assertEqual(
            unclassified,
            [],
            "未分類の CLI dest があります。OrchestrateArgs へ追加するか、"
            "option_parity_matrix.yaml の orchestrate_cli_dest_aliases / "
            "local_surface_excluded_cli_dests へ根拠付きで登録してください。",
        )

    def test_declared_aliases_and_exclusions_still_exist_in_the_cli(self) -> None:
        """存在しない dest の宣言が残ると、分類表が実態から乖離する。"""
        fx = _fixture()
        dests = _orchestrate_dests()
        for dest in sorted(set(fx["orchestrate_cli_dest_aliases"])):
            with self.subTest(alias=dest):
                self.assertIn(dest, dests, f"{dest} は orchestrate に存在しません")
        for dest in sorted(set(fx["local_surface_excluded_cli_dests"])):
            with self.subTest(excluded=dest):
                self.assertIn(dest, dests, f"{dest} は orchestrate に存在しません")

    def test_alias_targets_resolve_to_args_fields(self) -> None:
        for dest, target in _fixture()["orchestrate_cli_dest_aliases"].items():
            with self.subTest(dest=dest):
                self.assertIn(
                    target,
                    _args_fields(),
                    f"{dest} の解決先 {target} が OrchestrateArgs にありません",
                )


class TestSharedSettingsAreRegisteredEverywhere(unittest.TestCase):
    """4 箇所のどこか 1 つでも欠けると、その面から指定できなくなる。"""

    def _settings_key(self, name: str) -> str:
        aliases = _fixture()["local_surface_settings_key_aliases"] or {}
        return aliases.get(name, name)

    def test_shared_settings_are_args_fields(self) -> None:
        for name in _fixture()["local_surface_shared_settings"]:
            with self.subTest(setting=name):
                self.assertIn(name, _args_fields())

    def test_shared_settings_have_store_defaults(self) -> None:
        options = settings_store.defaults()["options"]
        for name in _fixture()["local_surface_shared_settings"]:
            key = self._settings_key(name)
            with self.subTest(setting=name, key=key):
                self.assertIn(key, options, f"{key} が設定ストア既定値にありません")

    def test_shared_settings_are_persisted_by_a_section(self) -> None:
        persisted = _persisted_settings_keys()
        for name in _fixture()["local_surface_shared_settings"]:
            key = self._settings_key(name)
            with self.subTest(setting=name, key=key):
                self.assertIn(
                    key, persisted, f"{key} が _SECTION_FIELDS のどのセクションにもありません"
                )

    def test_shared_settings_are_overridable_from_prompt_requests(self) -> None:
        for name in _fixture()["local_surface_shared_settings"]:
            with self.subTest(setting=name):
                self.assertIn(
                    name,
                    ALLOWED_SETTINGS_OVERRIDES,
                    f"{name} が ALLOWED_SETTINGS_OVERRIDES にありません",
                )

    def test_prompt_allowlist_has_no_key_outside_the_shared_classification(self) -> None:
        """FR-PROMPT-02: allowlist は shared setting 集合そのものでなければならない。

        逆向き（shared -> allowlist）は
        `test_shared_settings_are_overridable_from_prompt_requests` が検査する。
        本テストは、分類表に無い key が allowlist だけへ増える経路を塞ぐ。
        """
        undeclared = sorted(
            set(ALLOWED_SETTINGS_OVERRIDES)
            - set(_fixture()["local_surface_shared_settings"])
        )

        self.assertEqual(
            undeclared,
            [],
            "ALLOWED_SETTINGS_OVERRIDES にあって shared 分類に無い key があります。"
            "option_parity_matrix.yaml の local_surface_shared_settings へ追加するか、"
            "allowlist から外してください。",
        )

    def test_settings_key_aliases_are_wired_in_the_bridge(self) -> None:
        """fixture の別名宣言と実装の別名表が一致すること。"""
        from hve.gui.orchestrate_args import _SETTINGS_KEY_ALIASES

        declared = {
            store_key: field_name
            for field_name, store_key in (
                _fixture()["local_surface_settings_key_aliases"] or {}
            ).items()
        }
        self.assertEqual(dict(_SETTINGS_KEY_ALIASES), declared)


class TestWorkflowParamsAreSpecifiableFromAllSurfaces(unittest.TestCase):
    def test_each_workflow_param_has_a_cli_flag(self) -> None:
        flags = _orchestrate_flags()
        for name, flag in _fixture()["local_surface_workflow_params"].items():
            with self.subTest(param=name):
                self.assertIn(flag, flags, f"{flag} が orchestrate にありません")

    def test_each_workflow_param_is_declared_by_a_workflow(self) -> None:
        declared = set()
        for wf in list_workflows():
            declared |= set(wf.params or [])
        for name in _fixture()["local_surface_workflow_params"]:
            with self.subTest(param=name):
                self.assertIn(
                    name,
                    declared,
                    f"{name} を宣言する Workflow がありません（WorkflowDef.params）",
                )

    def test_each_workflow_param_is_an_args_field(self) -> None:
        for name in _fixture()["local_surface_workflow_params"]:
            with self.subTest(param=name):
                self.assertIn(name, _args_fields())

    def test_workflow_params_are_not_persisted_as_global_settings(self) -> None:
        """全体設定へ保存すると、宣言の無い Workflow へも効く誤解を生む。"""
        persisted = _persisted_settings_keys()
        for name in _fixture()["local_surface_workflow_params"]:
            with self.subTest(param=name):
                self.assertNotIn(name, persisted)


class TestRequirementIsDeclared(unittest.TestCase):
    def test_fr_local_surface_01_is_declared(self) -> None:
        text = (_REPO_ROOT / "hve-dev" / "requirement-definition.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("**FR-LOCAL-SURFACE-01**", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
