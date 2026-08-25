"""Issue Template / Actions の auto-qa パリティ検証。"""

from __future__ import annotations

import unittest
import re
import textwrap
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
_WORKFLOW_DIR = _REPO_ROOT / ".github" / "workflows"


class TestIssueTemplateQaControls(unittest.TestCase):
    """今回対象の Issue Template が enable_qa を持つことを検証する。"""

    _TEMPLATES_WITH_QA = [
        "app-architecture-design.yml",
        "web-app-design.yml",
        "web-app-dev.yml",
        "ai-agent-design.yml",
        "ai-agent-dev.yml",
        "dataflow-design.yml",
        "dataflow-dev.yml",
        "sourcecode-to-documentation.yml",
        "knowledge-management.yml",
    ]

    _TEMPLATES_OUT_OF_SCOPE = [
        "setup-labels.yml",
    ]

    def _read_template(self, filename: str) -> str:
        return (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")

    def test_target_templates_have_enable_qa(self) -> None:
        for template in self._TEMPLATES_WITH_QA:
            with self.subTest(template=template):
                self.assertIn("id: enable_qa", self._read_template(template))

    def test_out_of_scope_templates_are_not_changed(self) -> None:
        for template in self._TEMPLATES_OUT_OF_SCOPE:
            with self.subTest(template=template):
                self.assertNotIn("id: enable_qa", self._read_template(template))

    def test_agent_templates_keep_qa_control_but_remove_self_improve_enable(self) -> None:
        """AAG/AAGDはQA任意制御を維持し、Post-DAG Self-ImproveだけCloud必須にする。"""
        for template in ("ai-agent-design.yml", "ai-agent-dev.yml"):
            with self.subTest(template=template):
                content = self._read_template(template)
                self.assertIn("id: enable_qa", content)
                self.assertNotIn("id: enable_self_improve", content)
                self.assertIn("id: self_improve_max_iterations", content)
                self.assertIn("id: self_improve_quality_threshold", content)


class TestWorkflowAutoQaParity(unittest.TestCase):
    """Cloud Actions が auto-qa を固定値ではなく入力から反映することを検証する。"""

    def _read_workflow(self, filename: str) -> str:
        return (_WORKFLOW_DIR / filename).read_text(encoding="utf-8")

    def test_akm_workflow_propagates_auto_qa(self) -> None:
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('("auto-qa", auto_qa)', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_aas_workflow_auto_qa_dynamic(self) -> None:
        """AAS ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-app-selection-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_aad_web_workflow_auto_qa_dynamic(self) -> None:
        """AAD-WEB ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-app-detail-design-web-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_asdw_web_workflow_auto_qa_dynamic(self) -> None:
        """ASDW-WEB ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-app-dev-microservice-web-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_asdw_web_workflow_has_e2e_step_and_dependencies(self) -> None:
        """ASDW-WEB の E2E は Step.4.4 で、4.3→4.4→5.1/5.2 の依存であること。"""
        content = self._read_workflow("auto-app-dev-microservice-web-reusable.yml")
        self.assertIn("[ASDW-WEB] Step.4.4: E2E テスト (Playwright)", content)
        self.assertIn('"4.4": ["4.3"]', content)
        self.assertIn('"5.1": ["4.4"], "5.2": ["4.4"]', content)

    def test_abd_workflow_auto_qa_dynamic(self) -> None:
        """ADFD ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-dataflow-design-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_abdv_workflow_auto_qa_dynamic(self) -> None:
        """ADFDV ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-dataflow-dev-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_aag_workflow_auto_qa_dynamic(self) -> None:
        """AAG ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-ai-agent-design-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_aagd_workflow_auto_qa_dynamic(self) -> None:
        """AAGD ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-ai-agent-dev-reusable.yml")
        self.assertIn("###\\s*質問票設定", content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_adoc_workflow_auto_qa_dynamic(self) -> None:
        """ADOC ワークフローが auto-qa を Issue 入力から動的に反映することを検証する。"""
        content = self._read_workflow("auto-app-documentation-reusable.yml")
        self.assertIn('質問票設定', content)
        self.assertIn('"auto_qa": auto_qa', content)
        self.assertIn('<!-- auto-qa: %s -->', content)
        self.assertIn('add_label "${ROOT_ISSUE}" "auto-qa"', content)

    def test_reusable_workflows_embed_validation_marker_in_prompt(self) -> None:
        """Copilot向け追加入力セクションに検証マーカー指示が含まれることを検証する。"""
        targets = [
            "auto-ai-agent-design-reusable.yml",
            "auto-ai-agent-dev-reusable.yml",
            "auto-app-detail-design-web-reusable.yml",
            "auto-app-dev-microservice-web-reusable.yml",
            "auto-app-documentation-reusable.yml",
            "auto-app-selection-reusable.yml",
            "auto-dataflow-design-reusable.yml",
            "auto-dataflow-dev-reusable.yml",
            "auto-knowledge-management-reusable.yml",
        ]
        for filename in targets:
            with self.subTest(filename=filename):
                content = self._read_workflow(filename)
                self.assertIn("## 検証結果（PR本文に必須）", content)
                self.assertIn("<!-- validation-confirmed -->", content)
                m = re.search(
                    r"QA_REVIEW_SECTION=\$\(printf '(?P<section>.*?)'\)",
                    content,
                    re.DOTALL,
                )
                if m is None:
                    self.fail("QA_REVIEW_SECTION が見つかりません")
                section = m.group("section")
                self.assertIn("## 追加コンテキストの参照", section)
                self.assertIn("## 検証結果（PR本文に必須）", section)
                self.assertIn("<!-- validation-confirmed -->", section)

    def test_workflow_qa_sections_prohibit_cross_step_work_run_read(self) -> None:
        """全 Cloud ワークフローの QA 参照セクションに work/run 横断参照禁止の明確化が含まれること。

        QA 参照セクションは CLI/GUI 側 (hve/template_engine.py の
        _build_qa_review_context_section) と Cloud 側 (各 auto-*.yml) の二重実装であり、
        片方だけ更新すると文言がドリフトする。両者の cross-step work/run 読取り禁止文の
        存在を担保してドリフトを防ぐ。
        """
        prohibition = "`work/run/<run-id>/...` 配下の作業ファイルは入力として読まないこと"
        targets = [
            "auto-ai-agent-design-reusable.yml",
            "auto-ai-agent-dev-reusable.yml",
            "auto-app-detail-design-web-reusable.yml",
            "auto-app-dev-microservice-web-reusable.yml",
            "auto-app-documentation-reusable.yml",
            "auto-app-selection-reusable.yml",
            "auto-dataflow-design-reusable.yml",
            "auto-dataflow-dev-reusable.yml",
            "auto-knowledge-management-reusable.yml",
        ]
        for filename in targets:
            with self.subTest(filename=filename):
                content = self._read_workflow(filename)
                self.assertIn(
                    prohibition,
                    content,
                    f"{filename} の QA セクションに cross-step work/run 読取り禁止文がありません",
                )

    def test_akm_python_heredoc_blocks_are_compilable(self) -> None:
        """AKM workflowのPython heredocブロックが構文的に有効であることを検証する。"""
        pattern = re.compile(
            r"<<'(?P<marker>PY(?:EOF|TAGS|MERGE))'\n(?P<code>.*?)\n\s*(?P=marker)",
            re.DOTALL,
        )
        for filename in ("auto-knowledge-management-reusable.yml",):
            content = self._read_workflow(filename)
            blocks = list(pattern.finditer(content))
            self.assertGreater(len(blocks), 0, filename)
            for idx, match in enumerate(blocks, start=1):
                with self.subTest(filename=filename, marker=match.group("marker"), idx=idx):
                    compile(
                        textwrap.dedent(match.group("code")),
                        f"{filename}:{match.group('marker')}:{idx}",
                        "exec",
                    )


class TestAkmModelCloudParity(unittest.TestCase):
    """FR-CLOUD-25: QA 起点 AKM Root Issue への AKM 用モデル継承。"""

    _SCRIPT_DIR = _REPO_ROOT / ".github" / "scripts" / "bash" / "lib"

    # QA→AKM 同期の対象となる Workflow のテンプレート（AKM 自身は再帰禁止で対象外）。
    _TEMPLATES_WITH_AKM_MODEL = [
        "app-architecture-design.yml",
        "web-app-design.yml",
        "web-app-dev.yml",
        "ai-agent-design.yml",
        "ai-agent-dev.yml",
        "dataflow-design.yml",
        "dataflow-dev.yml",
        "sourcecode-to-documentation.yml",
    ]

    def _read_template(self, filename: str) -> str:
        return (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")

    def _read_workflow(self, filename: str) -> str:
        return (_WORKFLOW_DIR / filename).read_text(encoding="utf-8")

    @staticmethod
    def _allowlist(script_text: str) -> set:
        match = re.search(r"allowed\s*=\s*\{([^}]*)\}", script_text)
        assert match, "allowlist が見つかりません"
        return set(re.findall(r'"([^"]+)"', match.group(1)))

    # -- Issue Form ------------------------------------------------------

    def test_target_templates_have_akm_model(self) -> None:
        for template in self._TEMPLATES_WITH_AKM_MODEL:
            with self.subTest(template=template):
                self.assertIn("id: akm_model", self._read_template(template))

    def test_akm_template_does_not_have_akm_model(self) -> None:
        """AKM 自身は QA 起点 AKM を再帰生成しないため対象外。"""
        self.assertNotIn(
            "id: akm_model", self._read_template("knowledge-management.yml"),
        )

    def test_akm_model_choices_match_qa_model_choices(self) -> None:
        block = re.compile(
            r"id: (?P<id>akm_model|qa_model)\b.*?options:\s*\n(?P<options>(?:\s+- \".*?\"\s*\n)+)",
            re.DOTALL,
        )
        for template in self._TEMPLATES_WITH_AKM_MODEL:
            with self.subTest(template=template):
                found = {
                    m.group("id"): re.findall(r'- "([^"]+)"', m.group("options"))
                    for m in block.finditer(self._read_template(template))
                }
                self.assertIn("akm_model", found)
                self.assertIn("qa_model", found)
                self.assertEqual(found["akm_model"], found["qa_model"])

    def test_akm_model_section_label_matches_extractor(self) -> None:
        for template in self._TEMPLATES_WITH_AKM_MODEL:
            with self.subTest(template=template):
                self.assertIn("AKM 用モデル", self._read_template(template))

    # -- extractor -------------------------------------------------------

    def test_extract_akm_model_script_exists(self) -> None:
        script = self._SCRIPT_DIR / "extract-akm-model.py"
        self.assertTrue(script.is_file(), "extract-akm-model.py が存在しません")
        text = script.read_text(encoding="utf-8")
        self.assertIn("AKM 用モデル", text)

    def test_extract_akm_model_allowlist_matches_extract_model(self) -> None:
        akm = (self._SCRIPT_DIR / "extract-akm-model.py").read_text(encoding="utf-8")
        main = (self._SCRIPT_DIR / "extract-model.py").read_text(encoding="utf-8")
        self.assertEqual(self._allowlist(akm), self._allowlist(main))

    def test_copilot_assign_exposes_extract_akm_model(self) -> None:
        text = (self._SCRIPT_DIR / "copilot-assign.sh").read_text(encoding="utf-8")
        self.assertIn("extract_akm_model()", text)
        self.assertIn("extract-akm-model.py", text)

    def test_transition_workflow_calls_extract_akm_model_wrapper(self) -> None:
        """wrapper をデッドコード化させない（python3 直呼びへの退行を禁じる）。"""
        content = self._read_workflow("auto-issue-qa-ready-transition.yml")
        self.assertIn(
            'source "${GITHUB_WORKSPACE}/.github/scripts/bash/lib/copilot-assign.sh"',
            content,
            "save-qa-answer が copilot-assign.sh を source していません",
        )
        self.assertIn('akm_model=$(extract_akm_model "${body}")', content)
        self.assertNotIn(
            "extract-akm-model.py", content,
            "extract-akm-model.py の python3 直呼びが残っています"
            "（copilot-assign.sh の extract_akm_model がデッドコード化します）",
        )

    # -- source workflow -------------------------------------------------

    def test_transition_workflow_outputs_akm_model(self) -> None:
        content = self._read_workflow("auto-issue-qa-ready-transition.yml")
        self.assertIn(
            "akm_model: ${{ steps.save.outputs.akm_model }}", content,
            "save-qa-answer が akm_model を output していません",
        )
        self.assertIn('echo "akm_model=', content)

    def test_transition_workflow_forwards_akm_model_to_dispatch(self) -> None:
        content = self._read_workflow("auto-issue-qa-ready-transition.yml")
        self.assertIn(
            "AKM_MODEL: ${{ needs.save-qa-answer.outputs.akm_model }}", content,
        )
        self.assertIn('-f "akm_model=${AKM_MODEL}"', content)

    # -- coordinator workflow --------------------------------------------

    def test_coordinator_accepts_akm_model_input(self) -> None:
        content = self._read_workflow("auto-akm-after-qa.yml")
        self.assertIn("akm_model:", content)
        self.assertIn("required: false", content)

    def test_coordinator_writes_model_section_into_root_issue(self) -> None:
        content = self._read_workflow("auto-akm-after-qa.yml")
        self.assertIn("### 使用するモデル", content)

    def test_coordinator_falls_back_to_auto(self) -> None:
        content = self._read_workflow("auto-akm-after-qa.yml")
        # 内部変数名に依存せず、許可リスト外を "Auto" へ丸める実装があることを検証する。
        self.assertRegex(content, r'[A-Z_]*AKM_MODEL[A-Z_]*="Auto"')
        self.assertIn("claude-opus-4.7", content, "許可リスト検証がありません")


if __name__ == "__main__":
    unittest.main()
