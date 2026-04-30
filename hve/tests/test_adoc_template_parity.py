"""ADOC テンプレートパリティテスト

ADOC (Source Code からのドキュメント作成) の Step Issue body 生成が
templates/adoc/step-*.md をシングルソースとして正しく機能していることを検証する。

ADOC は既にテンプレートファイル方式で動作しており:
  - auto-app-documentation-reusable.yml が step-1.md を使用
  - advance-subissues.yml の advance_adoc ジョブが step-2.1.md〜step-6.3.md を使用

このテストは以下を検証する:
  - 全 19 Step のテンプレートファイルが存在すること
  - テンプレートに必要なプレースホルダ ({root_ref}, {target_dirs} 等) が含まれること
  - テンプレートから Custom Agent 名が正しく抽出できること
  - テンプレートのレンダリングが正常に動作すること
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES_BASE = _REPO_ROOT / ".github" / "scripts" / "templates" / "adoc"

# ADOC ステップ一覧（advance-subissues.yml の ADOC_DAG と同期させること）
_ADOC_STEP_IDS = [
    "1",
    "2.1", "2.2", "2.3", "2.4", "2.5",
    "3.1", "3.2", "3.3", "3.4", "3.5",
    "4",
    "5.1", "5.2", "5.3", "5.4",
    "6.1", "6.2", "6.3",
]

# ADOC テンプレートの必須プレースホルダ
_ADOC_REQUIRED_PLACEHOLDERS = [
    "{root_ref}",
    "{target_dirs}",
    "{exclude_patterns}",
    "{doc_purpose}",
    "{max_file_lines}",
]


class TestAdocTemplateFilesExist(unittest.TestCase):
    """全 ADOC テンプレートファイルが存在することを検証する。"""

    def test_all_step_templates_exist(self) -> None:
        for step_id in _ADOC_STEP_IDS:
            tpl = _TEMPLATES_BASE / f"step-{step_id}.md"
            self.assertTrue(
                tpl.exists(),
                f"ADOC テンプレートが見つかりません: {tpl}",
            )


class TestAdocTemplatePlaceholders(unittest.TestCase):
    """テンプレートに必要なプレースホルダが含まれていることを検証する。"""

    def _load(self, step_id: str) -> str:
        tpl = _TEMPLATES_BASE / f"step-{step_id}.md"
        if not tpl.exists():
            self.skipTest(f"テンプレートが存在しません: {tpl}")
        return tpl.read_text(encoding="utf-8")

    def test_root_ref_placeholder_in_all_steps(self) -> None:
        for step_id in _ADOC_STEP_IDS:
            body = self._load(step_id)
            self.assertIn(
                "{root_ref}",
                body,
                f"step-{step_id}.md に {{root_ref}} プレースホルダが見つかりません",
            )

    def test_adoc_specific_placeholders_in_step1(self) -> None:
        """Step.1 に ADOC 固有プレースホルダが含まれていることを検証する。"""
        body = self._load("1")
        for placeholder in _ADOC_REQUIRED_PLACEHOLDERS:
            self.assertIn(
                placeholder,
                body,
                f"step-1.md に {placeholder} プレースホルダが見つかりません",
            )

    def test_custom_agent_section_in_non_container_steps(self) -> None:
        """コンテナステップ以外に ## Custom Agent セクションが存在することを検証する。

        advance-subissues.yml の extract_custom_agent() で使われる形式:
        ## Custom Agent\n`AgentName`
        """
        agent_pattern = re.compile(r"## Custom Agent\s*\n\s*`([^`]+)`")
        for step_id in _ADOC_STEP_IDS:
            body = self._load(step_id)
            m = agent_pattern.search(body)
            self.assertIsNotNone(
                m,
                f"step-{step_id}.md に ## Custom Agent セクションが見つかりません"
                f"（形式: ## Custom Agent\\n`AgentName`）",
            )
            agent_name = m.group(1).strip()
            self.assertTrue(
                agent_name,
                f"step-{step_id}.md の Custom Agent 名が空です",
            )


class TestAdocTemplateRendering(unittest.TestCase):
    """テンプレートのレンダリングが正常に動作することを検証する。

    advance-subissues.yml の render パターンと同一の置換ロジックでテスト:
        body.replace('{root_ref}', ROOT_REF)
        body.replace('{target_dirs}', TARGET_DIRS)
        body.replace('{exclude_patterns}', EXCLUDE_PATTERNS)
        body.replace('{doc_purpose}', DOC_PURPOSE)
        body.replace('{max_file_lines}', MAX_FILE_LINES)
        body.replace('{additional_section}', '')
        body.replace('{completion_instruction}', ...)  # advance-subissues.yml では暗黙置換
    """

    _DUMMY_PARAMS = {
        "root_ref": "<!-- root-issue: #1 -->\n<!-- branch: main -->",
        "target_dirs": "src",
        "exclude_patterns": "node_modules/,vendor/",
        "doc_purpose": "all",
        "max_file_lines": "500",
        "additional_section": "",
        "completion_instruction": "- 完了時に自身に `adoc:done` ラベルを付与すること",
    }

    def test_render_all_steps(self) -> None:
        for step_id in _ADOC_STEP_IDS:
            tpl = _TEMPLATES_BASE / f"step-{step_id}.md"
            if not tpl.exists():
                self.skipTest(f"テンプレートが存在しません: {tpl}")
            body = tpl.read_text(encoding="utf-8")
            rendered = body
            for key, val in self._DUMMY_PARAMS.items():
                rendered = rendered.replace(f"{{{key}}}", val)

            # root-issue メタデータが埋め込まれていること
            self.assertIn(
                "<!-- root-issue: #1 -->",
                rendered,
                f"step-{step_id}.md のレンダリング結果に root-issue メタデータがありません",
            )
            # 主要なプレースホルダが残っていないこと
            for placeholder in ["{root_ref}", "{target_dirs}", "{additional_section}", "{completion_instruction}"]:
                self.assertNotIn(
                    placeholder,
                    rendered,
                    f"step-{step_id}.md のレンダリング後に {placeholder} が残っています",
                )


class TestAdocStepCountMatchesRegistry(unittest.TestCase):
    """ADOC テンプレートファイル数が hve の workflow_registry.py の定義と一致すること。"""

    def test_adoc_step_count_matches_hve(self) -> None:
        try:
            from hve.workflow_registry import get_workflow  # type: ignore[import]
        except ImportError:
            self.skipTest("hve モジュールが利用できません")
        wf = get_workflow("adoc")
        if wf is None:
            self.skipTest("adoc ワークフローが hve に登録されていません")
        hve_step_ids = {s.id for s in wf.steps if not s.is_container}
        template_step_ids = set(_ADOC_STEP_IDS)
        self.assertEqual(
            hve_step_ids,
            template_step_ids,
            f"hve の adoc ステップ定義とテストの _ADOC_STEP_IDS が一致しません。\n"
            f"hve のみ: {hve_step_ids - template_step_ids}\n"
            f"テストのみ: {template_step_ids - hve_step_ids}",
        )


if __name__ == "__main__":
    unittest.main()
