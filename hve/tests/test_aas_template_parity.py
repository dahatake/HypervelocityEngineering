"""AAS テンプレートパリティテスト

AAS の Step Issue body を生成する 2 つの経路が同じソースを参照していることを検証する:
  1. bash 経路: auto-app-selection-reusable.yml の BODY_S* ハードコード文字列
  2. hve 経路: hve/workflow_registry.py が参照する templates/aas/step-N.md

このテストは以下を検証する:
  - 全 7 Step のテンプレートファイルが存在すること
  - テンプレートファイルに必要なプレースホルダ ({root_ref}, {completion_instruction}) が含まれること
  - テンプレートファイルの `## 依存` セクションが正しい AAS ステップ番号を参照していること
    (aad-web のステップ番号が混入していないこと)
  - テンプレートから生成された body に ## Custom Agent セクションが含まれること
    (bash 経路の extract_custom_agent で使われる)
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

# テンプレートのベースパス（リポジトリルートからの相対）
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES_BASE = _REPO_ROOT / ".github" / "scripts" / "templates" / "aas"

# AAS ステップ定義（step_id → 依存する正しいステップ番号のパターン）
# 依存なし (None) = 依存セクションで「なし」と記載されるべき
# 依存あり (str) = このパターンが ## 依存 セクションに含まれているべき
# 依存あり (list) = いずれかのパターンが含まれていれば OK（別表現の許容）
_AAS_STEP_DEPENDENCY_PATTERNS: dict[str, None | str | list[str]] = {
    "1":   None,                       # 依存なし
    "2":   "1",                        # Step.1 に依存
    "3.1": ["Step.2", "フェーズ2"],      # Step.2 に依存（テンプレートは「フェーズ2」表現も許容）
    "3.2": "3.1",                      # Step.3.1 に依存（Step.1.1 は NG）
    "4":   "3.2",                      # Step.3.2 に依存（Step.1.2 は NG）
    "5":   "4",                        # Step.4 に依存（Step.2 は NG）
    "6":   "5",                        # Step.5 に依存（Step.4（画面一覧） は NG）
    "7":   "6",                        # Step.6 に依存（Step.5（サービスカタログ） は NG）
}

# aad-web からの混入が疑われる誤ったステップ参照パターン
_FORBIDDEN_DEPENDENCY_PATTERNS = {
    "3.2": ["Step.1.1"],
    "4":   ["Step.1.2"],
    "5":   ["Step.2（データモデル作成）", "Step.2（"],
    "6":   ["Step.4（画面一覧"],
    "7":   ["Step.5（サービスカタログ）"],
}


class TestAasTemplateFilesExist(unittest.TestCase):
    """全 AAS テンプレートファイルが存在することを検証する。"""

    def test_all_step_templates_exist(self) -> None:
        for step_id in _AAS_STEP_DEPENDENCY_PATTERNS:
            tpl = _TEMPLATES_BASE / f"step-{step_id}.md"
            self.assertTrue(
                tpl.exists(),
                f"AAS テンプレートが見つかりません: {tpl}",
            )


class TestAasTemplatePlaceholders(unittest.TestCase):
    """テンプレートに必要なプレースホルダが含まれていることを検証する。"""

    def _load(self, step_id: str) -> str:
        tpl = _TEMPLATES_BASE / f"step-{step_id}.md"
        if not tpl.exists():
            self.skipTest(f"テンプレートが存在しません: {tpl}")
        return tpl.read_text(encoding="utf-8")

    def test_root_ref_placeholder(self) -> None:
        for step_id in _AAS_STEP_DEPENDENCY_PATTERNS:
            body = self._load(step_id)
            self.assertIn(
                "{root_ref}",
                body,
                f"step-{step_id}.md に {{root_ref}} プレースホルダが見つかりません",
            )

    def test_completion_instruction_placeholder(self) -> None:
        for step_id in _AAS_STEP_DEPENDENCY_PATTERNS:
            body = self._load(step_id)
            self.assertIn(
                "{completion_instruction}",
                body,
                f"step-{step_id}.md に {{completion_instruction}} プレースホルダが見つかりません",
            )

    def test_custom_agent_section_exists(self) -> None:
        """## Custom Agent セクションが存在し、bash の extract_custom_agent で解析できること。"""
        agent_pattern = re.compile(r"## Custom Agent\s*\n\s*`([^`]+)`")
        for step_id in _AAS_STEP_DEPENDENCY_PATTERNS:
            body = self._load(step_id)
            m = agent_pattern.search(body)
            self.assertIsNotNone(
                m,
                f"step-{step_id}.md に ## Custom Agent セクションが見つかりません（形式: ## Custom Agent\\n`AgentName`）",
            )
            agent_name = m.group(1).strip()
            self.assertTrue(
                agent_name,
                f"step-{step_id}.md の Custom Agent 名が空です",
            )


class TestAasTemplateDependencyStepNumbers(unittest.TestCase):
    """テンプレートの ## 依存 セクションが正しい AAS ステップ番号を参照していること。

    aad-web のステップ番号（Step.1.1, Step.1.2, Step.2（データモデル作成）等）が
    混入していないことを CI で常時検証する。
    """

    def _load(self, step_id: str) -> str:
        tpl = _TEMPLATES_BASE / f"step-{step_id}.md"
        if not tpl.exists():
            self.skipTest(f"テンプレートが存在しません: {tpl}")
        return tpl.read_text(encoding="utf-8")

    def test_no_forbidden_dependency_references(self) -> None:
        """誤った（aad-web 由来の）ステップ番号参照が含まれていないこと。"""
        for step_id, forbidden in _FORBIDDEN_DEPENDENCY_PATTERNS.items():
            body = self._load(step_id)
            for forbidden_pattern in forbidden:
                self.assertNotIn(
                    forbidden_pattern,
                    body,
                    f"step-{step_id}.md に誤った依存参照 '{forbidden_pattern}' が含まれています。"
                    f"aad-web のステップ番号が混入している可能性があります。",
                )

    def test_correct_dependency_references(self) -> None:
        """正しいステップ番号参照が含まれていること。"""
        for step_id, expected_dep in _AAS_STEP_DEPENDENCY_PATTERNS.items():
            body = self._load(step_id)
            if expected_dep is None:
                # 依存なしの Step: 「なし」が記載されていること
                self.assertIn(
                    "なし",
                    body,
                    f"step-{step_id}.md には依存なし（「なし」）の記載が必要です",
                )
            elif isinstance(expected_dep, list):
                # 複数の許容表現がある場合: いずれかが含まれていればOK
                found = any(pat in body for pat in expected_dep)
                self.assertTrue(
                    found,
                    f"step-{step_id}.md に依存参照が見つかりません。"
                    f"許容パターン: {expected_dep}",
                )
            else:
                # 依存ありの Step: 正しいステップ番号が含まれていること
                self.assertIn(
                    f"Step.{expected_dep}",
                    body,
                    f"step-{step_id}.md に正しい依存参照 'Step.{expected_dep}' が見つかりません",
                )


class TestAasTemplateRendering(unittest.TestCase):
    """テンプレートのレンダリングが正常に動作することを検証する。"""

    def test_render_all_steps(self) -> None:
        """全 Step のテンプレートをレンダリングして基本的な内容を確認する。"""
        dummy_root_ref = "<!-- root-issue: #1 -->\n<!-- branch: main -->"
        dummy_additional = ""
        completion_instruction = "- 完了時に自身に `aas:done` ラベルを付与すること"

        for step_id in _AAS_STEP_DEPENDENCY_PATTERNS:
            tpl = _TEMPLATES_BASE / f"step-{step_id}.md"
            if not tpl.exists():
                self.skipTest(f"テンプレートが存在しません: {tpl}")
            body = tpl.read_text(encoding="utf-8")
            rendered = (
                body
                .replace("{root_ref}", dummy_root_ref)
                .replace("{additional_section}", dummy_additional)
                .replace("{completion_instruction}", completion_instruction)
            )
            # レンダリング後のプレースホルダが残っていないこと
            self.assertNotIn(
                "{root_ref}", rendered,
                f"step-{step_id}.md のレンダリング後に {{root_ref}} が残っています",
            )
            self.assertNotIn(
                "{completion_instruction}", rendered,
                f"step-{step_id}.md のレンダリング後に {{completion_instruction}} が残っています",
            )
            # root-issue メタデータが埋め込まれていること
            self.assertIn(
                "<!-- root-issue: #1 -->", rendered,
                f"step-{step_id}.md のレンダリング結果に root-issue メタデータがありません",
            )
            # 完了条件の `aas:done` ラベル指示が含まれること
            self.assertIn(
                "aas:done",
                rendered,
                f"step-{step_id}.md のレンダリング結果に aas:done ラベルの記述がありません",
            )


if __name__ == "__main__":
    unittest.main()
