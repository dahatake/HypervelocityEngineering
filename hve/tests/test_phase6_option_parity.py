"""Phase 6 — Issue Template / hve オプション整合性の静的検証テスト。

外部 API / 実 GitHub Actions 実行に依存しない静的検証のみを行う。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
_WORKFLOW_DIR = _REPO_ROOT / ".github" / "workflows"
_OPTION_PARITY_FIXTURE = (
    _REPO_ROOT / "hve" / "tests" / "fixtures" / "option_parity_matrix.yaml"
)

# Issue Template のうち enable_review を持つべきファイル
_TEMPLATES_WITH_REVIEW = [
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

# model ドロップダウンを持つ全 Issue Template (setup-labels.yml は除外)
_TEMPLATES_WITH_MODEL = [
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

# enable_auto_merge を持つべき Issue Template（全ワークフロー対象テンプレート）
_TEMPLATES_WITH_AUTO_MERGE = [
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

_TEMPLATES_WITH_RUNNER_TYPE = [
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

_MAX_TEMPLATE_SECTION_INDENT = 4


def _extract_dropdown_options(content: str, field_id: str) -> list[str]:
    """指定 id のドロップダウン options リストを抽出する。"""
    # options セクションを抽出し、次のトップレベルキー（最大4スペースインデント）または EOF までを対象にする
    m = re.search(
        rf'id:\s*{re.escape(field_id)}.*?options:\s*\n(.*?)(?:\n\s{{0,{_MAX_TEMPLATE_SECTION_INDENT}}}\w|\Z)',
        content,
        re.DOTALL,
    )
    if not m:
        return []
    options_text = m.group(1)
    return [
        line.strip().lstrip("- ").strip('"')
        for line in options_text.splitlines()
        if line.strip().startswith("- ")
    ]


def _extract_template_field_block(content: str, field_id: str) -> str:
    """Issue Template 内の指定 id を持つ field ブロック全体を抽出する。"""
    m = re.search(
        rf"""
        ^\s*-\s*type:\s*\w+\s*\n           # field 開始行
        (?:[ ]+.*\n)*?                     # id 行までの同一 field 内の行
        [ ]+id:\s*{re.escape(field_id)}\s*\n
        (?:[ ]+.*\n)*                      # id 行以降の同一 field 内の行
        (?=^\s*-\s*type:|\Z)               # 次 field 開始またはファイル末尾
        """,
        content,
        re.MULTILINE | re.VERBOSE,
    )
    return m.group(0) if m else ""


class TestAkmEnableReview(unittest.TestCase):
    """AKM テンプレートが enable_review を持つことを検証する。"""

    def _read_template(self, filename: str) -> str:
        return (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")

    def test_akm_template_has_enable_review(self) -> None:
        """AKM テンプレートが enable_review チェックボックスを持つこと。"""
        content = self._read_template("knowledge-management.yml")
        self.assertIn("id: enable_review", content)

    def test_all_target_templates_have_enable_review(self) -> None:
        """全対象テンプレートが enable_review を持つこと。"""
        for template in _TEMPLATES_WITH_REVIEW:
            with self.subTest(template=template):
                content = self._read_template(template)
                self.assertIn("id: enable_review", content)

    def test_akm_review_label_text(self) -> None:
        """AKM テンプレートの enable_review ラベルが正しいこと。"""
        content = self._read_template("knowledge-management.yml")
        self.assertIn("レビュー設定", content)
        self.assertIn("adversarial-review", content)

class TestAkmWorkflowEnableReview(unittest.TestCase):
    """AKM ワークフローが enable_review を正しくパース・適用することを検証する（Phase 6 追加）。"""

    def _read_workflow(self, filename: str) -> str:
        return (_WORKFLOW_DIR / filename).read_text(encoding="utf-8")

    def test_akm_workflow_parses_review_section(self) -> None:
        """AKM ワークフローが ### レビュー設定 セクションをパースすること。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn("レビュー設定", content)
        self.assertIn("adversarial_review", content)

    def test_akm_workflow_has_adversarial_review_variable(self) -> None:
        """AKM ワークフローが ADVERSARIAL_REVIEW bash 変数を持つこと。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn("ADVERSARIAL_REVIEW", content)

    def test_akm_workflow_embeds_adversarial_review_tag(self) -> None:
        """AKM ワークフローが Root Issue body に専用レビュータグを埋め込むこと。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn('("adversarial-review", adversarial_review)', content)

    def test_akm_workflow_adds_adversarial_review_label_conditionally(self) -> None:
        """AKM ワークフローが ADVERSARIAL_REVIEW 条件付きでラベルを付与すること。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn('add_label "${ROOT_ISSUE}" "adversarial-review"', content)
        # 条件付き（if [[ "${ADVERSARIAL_REVIEW}" == "true" ]]）であること
        self.assertIn('ADVERSARIAL_REVIEW}" == "true"', content)

    def test_akm_workflow_includes_adversarial_review_in_root_ref(self) -> None:
        """AKM ワークフローの ROOT_REF に専用レビュータグが含まれること。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn("adversarial-review: %s", content)

    def test_akm_workflow_creates_adversarial_review_label(self) -> None:
        """AKM ワークフローのラベル bootstrap で専用レビューラベルが作成されること。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn('create_label "adversarial-review"', content)

    def test_akm_step_labels_include_adversarial_review_conditionally(self) -> None:
        """AKM ワークフローの Step Issue に専用レビューラベルが条件付きで含まれること。"""
        content = self._read_workflow("auto-knowledge-management-reusable.yml")
        self.assertIn('"adversarial-review"', content)


class TestEnableAutoMerge(unittest.TestCase):
    """enable_auto_merge のIssue Form / SDKConfig / CLI対応を検証する。"""

    def _read_template(self, filename: str) -> str:
        return (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")

    @staticmethod
    def _load_fixture() -> dict:
        import yaml  # type: ignore[import-untyped]

        return yaml.safe_load(_OPTION_PARITY_FIXTURE.read_text(encoding="utf-8"))

    def test_all_target_templates_have_enable_auto_merge(self) -> None:
        """全対象 Issue Template が enable_auto_merge を持つこと。"""
        for template in _TEMPLATES_WITH_AUTO_MERGE:
            with self.subTest(template=template):
                content = self._read_template(template)
                self.assertIn("id: enable_auto_merge", content)

    def test_fixture_documents_enable_auto_merge_as_common(self) -> None:
        fixture = self._load_fixture()
        entry = next(
            item for item in fixture["options"]
            if item["option_key"] == "enable_auto_merge"
        )
        self.assertEqual(entry["applies_to"], "common")
        self.assertEqual(entry["issue_form_field_id"], "enable_auto_merge")
        self.assertEqual(entry["hve_config_attr"], "enable_auto_merge")
        self.assertEqual(entry["hve_cli_flag"], "--enable-auto-merge")
        self.assertIn("意図的なroute差", entry["notes"])

    def test_enable_auto_merge_preserves_intentional_cloud_cli_default_difference(self) -> None:
        from hve.config import SDKConfig

        for template in _TEMPLATES_WITH_AUTO_MERGE:
            field = next(
                item for item in self._load_fixture_document(template)["body"]
                if item.get("id") == "enable_auto_merge"
            )
            self.assertEqual(field["attributes"]["options"][field["attributes"]["default"]], "有効にする")
        self.assertFalse(SDKConfig().enable_auto_merge)
        self.assertIn("--enable-auto-merge", TestOptionParityMatrix._cli_option_strings())

    @staticmethod
    def _load_fixture_document(filename: str) -> dict:
        import yaml  # type: ignore[import-untyped]

        return yaml.safe_load((_TEMPLATE_DIR / filename).read_text(encoding="utf-8"))


class TestModelDropdown(unittest.TestCase):
    """model ドロップダウンが5種選択肢を持つことを検証する（Phase 9+ 更新）。"""

    _EXPECTED_OPTIONS = ["Auto", "claude-opus-4.7", "claude-opus-4.6", "gpt-5.5", "gpt-5.4"]

    def _read_template(self, filename: str) -> str:
        return (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")

    @staticmethod
    def _read_fixture() -> str:
        return _OPTION_PARITY_FIXTURE.read_text(encoding="utf-8")

    def test_all_templates_have_model_dropdown_with_5_options(self) -> None:
        """全対象テンプレートの model ドロップダウンが5種選択肢を持つこと。"""
        for template in _TEMPLATES_WITH_MODEL:
            with self.subTest(template=template):
                content = self._read_template(template)
                options = _extract_dropdown_options(content, "model")
                self.assertEqual(
                    options,
                    self._EXPECTED_OPTIONS,
                    f"{template}: model options が期待値と異なります",
                )

    def test_templates_have_review_model_and_qa_model(self) -> None:
        """全テンプレートに review_model / qa_model ドロップダウンが存在すること。"""
        for template in _TEMPLATES_WITH_MODEL:
            with self.subTest(template=template):
                content = self._read_template(template)
                review_options = _extract_dropdown_options(content, "review_model")
                qa_options = _extract_dropdown_options(content, "qa_model")
                self.assertEqual(
                    review_options,
                    self._EXPECTED_OPTIONS,
                    f"{template}: review_model options が期待値と異なります",
                )
                self.assertEqual(
                    qa_options,
                    self._EXPECTED_OPTIONS,
                    f"{template}: qa_model options が期待値と異なります",
                )

    def test_model_choices_parity_with_templates(self) -> None:
        """hve/config.py の MODEL_CHOICES と Issue Template options（Auto を除く）が完全一致すること。"""
        import sys as _sys
        _sys.path.insert(0, str(_REPO_ROOT / "hve"))
        from config import MODEL_CHOICES  # type: ignore
        template_options_without_auto = [o for o in self._EXPECTED_OPTIONS if o != "Auto"]
        self.assertEqual(list(MODEL_CHOICES), template_options_without_auto)

    def test_fixture_documents_model_auto_and_override_policy(self) -> None:
        content = self._read_fixture()
        self.assertIn("Auto", content)
        self.assertIn("model_override", content)


class TestOptionParityFixtureCompleteness(unittest.TestCase):
    """現行option parity SSoT fixtureの分類を検証する。"""

    def _load_fixture(self) -> dict:
        import yaml  # type: ignore[import-untyped]

        return yaml.safe_load(_OPTION_PARITY_FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_has_supported_schema_version(self) -> None:
        self.assertEqual(self._load_fixture()["schema_version"], "1.0")

    def test_fixture_has_hve_only_options(self) -> None:
        fixture = self._load_fixture()
        hve_only = {
            item["option_key"] for item in fixture["options"]
            if item["applies_to"] == "hve_only"
        }
        self.assertTrue({
            "apply_qa_improvements_to_main",
            "apply_review_improvements_to_main",
            "apply_self_improve_to_main",
            "reuse_context_filtering",
            "auto_coding_agent_review",
        } <= hve_only)

    def test_fixture_classifies_enable_auto_merge_as_common(self) -> None:
        fixture = self._load_fixture()
        entry = next(
            item for item in fixture["options"]
            if item["option_key"] == "enable_auto_merge"
        )
        self.assertEqual(entry["applies_to"], "common")

    def test_issue_form_internal_fields_are_unique(self) -> None:
        fields = self._load_fixture()["issue_form_internal_fields"]
        self.assertEqual(len(fields), len(set(fields)))

    def test_fixture_work_iq_is_hve_only(self) -> None:
        fixture = self._load_fixture()
        workiq_entries = [
            item for item in fixture["options"]
            if item["option_key"].startswith("workiq_")
        ]
        self.assertTrue(workiq_entries)
        self.assertTrue(all(item["applies_to"] == "hve_only" for item in workiq_entries))


class TestAgentSelfImproveRouteParity(unittest.TestCase):
    """AAG/AAGD Cloud必須とCLI緊急opt-outの意図的な差分を固定する。"""

    @staticmethod
    def _load_template(filename: str) -> dict:
        import yaml  # type: ignore[import-untyped]

        return yaml.safe_load((_TEMPLATE_DIR / filename).read_text(encoding="utf-8"))

    @classmethod
    def _field(cls, filename: str, field_id: str) -> dict:
        document = cls._load_template(filename)
        return next(item for item in document["body"] if item.get("id") == field_id)

    def test_agent_cloud_forms_are_mandatory_with_only_tuning_controls(self) -> None:
        for filename in ("ai-agent-design.yml", "ai-agent-dev.yml"):
            with self.subTest(filename=filename):
                document = self._load_template(filename)
                ids = {item.get("id") for item in document["body"]}
                self.assertNotIn("enable_self_improve", ids)
                self.assertIn("self_improve_max_iterations", ids)
                self.assertIn("self_improve_quality_threshold", ids)

                iterations = self._field(filename, "self_improve_max_iterations")
                threshold = self._field(filename, "self_improve_quality_threshold")
                self.assertEqual(
                    iterations["attributes"]["options"][iterations["attributes"]["default"]],
                    "3 (デフォルト)",
                )
                self.assertEqual(
                    threshold["attributes"]["options"][threshold["attributes"]["default"]],
                    "80（標準）",
                )

    def test_aagd_tdd_retry_is_distinct_from_self_improve_iteration(self) -> None:
        tdd = self._field("ai-agent-dev.yml", "tdd_max_retries")
        self_improve = self._field("ai-agent-dev.yml", "self_improve_max_iterations")
        self.assertEqual(
            tdd["attributes"]["options"][tdd["attributes"]["default"]],
            "5 (デフォルト)",
        )
        self.assertEqual(
            self_improve["attributes"]["options"][self_improve["attributes"]["default"]],
            "3 (デフォルト)",
        )
        self.assertIn("TDD GREENリトライとは別", self_improve["attributes"]["description"])

    def test_agent_self_improve_defaults_match_sdk_and_workflow_fallbacks(self) -> None:
        from hve.config import SDKConfig

        config = SDKConfig()
        self.assertEqual(config.self_improve_max_iterations, 3)
        self.assertEqual(config.self_improve_quality_threshold, 80)
        for filename in (
            "auto-ai-agent-design-reusable.yml",
            "auto-ai-agent-dev-reusable.yml",
        ):
            content = (_WORKFLOW_DIR / filename).read_text(encoding="utf-8")
            self.assertIn('self_improve_max_iterations = "3"', content)
            self.assertIn('self_improve_quality_threshold = "80"', content)

    def test_cloud_workflows_are_mandatory_without_enable_parser(self) -> None:
        expectations = {
            "auto-ai-agent-design-reusable.yml": "Run mandatory AAG Post-DAG Self-Improve",
            "auto-ai-agent-dev-reusable.yml": "Run mandatory AAGD Post-DAG Self-Improve",
        }
        for filename, marker in expectations.items():
            with self.subTest(filename=filename):
                content = (_WORKFLOW_DIR / filename).read_text(encoding="utf-8")
                self.assertIn(marker, content)
                self.assertNotIn("enable-self-improve", content)
                self.assertNotIn("outputs.enable", content)

    def test_cli_keeps_explicit_emergency_opt_out(self) -> None:
        flags = TestOptionParityMatrix._cli_option_strings()
        self.assertIn("--self-improve", flags)
        self.assertIn("--no-self-improve", flags)

        orchestrator = (_REPO_ROOT / "hve" / "orchestrator.py").read_text(encoding="utf-8")
        self.assertIn('workflow_id in {"aag", "aagd"}', orchestrator)
        self.assertIn("and not config.self_improve_skip", orchestrator)
        self.assertIn('config.self_improve_scope != "disabled"', orchestrator)
        self.assertIn("config = copy.copy(config)", orchestrator)
        self.assertIn("config.auto_self_improve = True", orchestrator)


class TestRunnerTypeOptionParity(unittest.TestCase):
    """Runner 選択欄と dispatcher 配線の Phase 1 実装を静的検証する。"""

    def _read_template(self, filename: str) -> str:
        return (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")

    def _read_workflow(self, filename: str) -> str:
        return (_WORKFLOW_DIR / filename).read_text(encoding="utf-8")

    def test_target_templates_have_runner_type_dropdown(self) -> None:
        for template in _TEMPLATES_WITH_RUNNER_TYPE:
            with self.subTest(template=template):
                content = self._read_template(template)
                runner_block = _extract_template_field_block(content, "runner_type")
                self.assertTrue(runner_block, f"{template}: runner_type field block が見つかりません")
                self.assertIn('label: "実行 Runner"', runner_block)
                self.assertIn("required: true", runner_block)
                self.assertIn("default: 0", runner_block)
                self.assertEqual(
                    _extract_dropdown_options(content, "runner_type"),
                    ["GitHub Hosted", "Self-hosted (ACA)"],
                )

    def test_out_of_scope_templates_do_not_have_runner_type(self) -> None:
        self.assertNotIn("id: runner_type", self._read_template("setup-labels.yml"))

    def test_dispatcher_detect_extracts_and_outputs_runner_type(self) -> None:
        content = self._read_workflow("auto-orchestrator-dispatcher.yml")
        self.assertIn("runner_type: ${{ steps.detect.outputs.runner_type }}", content)
        self.assertIn("runner_type = 'github-hosted'", content)
        self.assertIn('runner_section = section_text(r"###\\s*実行 Runner\\s*\\n(.*?)(?=###|\\Z)")', content)
        self.assertIn("runner_type = 'self-hosted'", content)
        self.assertIn("f.write(f'runner_type={runner_type}", content)

    def test_dispatcher_forwards_runner_type_for_eight_targets_only(self) -> None:
        """Cloud非対応Workflowを除き、runner_type伝搬先は8ターゲット。"""
        content = self._read_workflow("auto-orchestrator-dispatcher.yml")
        marker = "runner_type: ${{ needs.detect.outputs.runner_type }}"
        self.assertEqual(content.count(marker), 8)
        self.assertIn("setup_labels:", content)
        setup_labels_block = content.split("setup_labels:", 1)[1]
        self.assertNotIn("runner_type", setup_labels_block)

    def test_pr4_reusable_workflows_accept_runner_type_and_switch_all_jobs(self) -> None:
        expected_job_counts = {
            "auto-app-documentation-reusable.yml": 2,
            "auto-knowledge-management-reusable.yml": 2,
        }
        for filename, expected_job_count in expected_job_counts.items():
            with self.subTest(workflow=filename):
                content = self._read_workflow(filename)
                self.assertIn('description: "実行 Runner 種別: github-hosted | self-hosted"', content)
                self.assertIn('default: "github-hosted"', content)
                self.assertEqual(content.count('runs-on:'), expected_job_count)
                self.assertEqual(content.count("runs-on: ${{ fromJSON(inputs.runner_type == 'self-hosted'"), expected_job_count)


class TestAgenticRetrievalWorkflowWiring(unittest.TestCase):
    """Phase 6 の Agentic Retrieval 入力配線（dispatcher/reusable）を静的検証する。"""

    def _read_workflow(self, filename: str) -> str:
        return (_WORKFLOW_DIR / filename).read_text(encoding="utf-8")

    def test_dispatcher_has_agentic_outputs_and_safety_valve(self) -> None:
        content = self._read_workflow("auto-orchestrator-dispatcher.yml")
        self.assertIn("enable_agentic_retrieval: ${{ steps.detect.outputs.enable_agentic_retrieval }}", content)
        self.assertIn("agentic_data_source_modes: ${{ steps.detect.outputs.agentic_data_source_modes }}", content)
        self.assertIn("foundry_mcp_integration: ${{ steps.detect.outputs.foundry_mcp_integration }}", content)
        self.assertIn("agentic_existing_design_diff_only", content)
        self.assertIn("foundry_sku_fallback_policy", content)
        self.assertIn("if enable_agentic_retrieval == 'no':", content)
        self.assertIn("foundry_mcp_integration = 'false'", content)
        self.assertIn("foundry_sku_fallback_policy = 'standard_allowed'", content)

    def test_dispatcher_passes_agentic_inputs_to_aad(self) -> None:
        """FR-CLOUD-06: ASDW-WEB の Cloud 起動は停止済みのため AAD-WEB への伝搬のみ検証する。"""
        content = self._read_workflow("auto-orchestrator-dispatcher.yml")
        self.assertIn("uses: ./.github/workflows/auto-app-detail-design-web-reusable.yml", content)
        self.assertNotIn("uses: ./.github/workflows/auto-app-dev-microservice-web-reusable.yml", content)
        self.assertIn("enable_agentic_retrieval: ${{ needs.detect.outputs.enable_agentic_retrieval }}", content)
        self.assertIn("agentic_data_source_modes: ${{ needs.detect.outputs.agentic_data_source_modes }}", content)
        self.assertIn("foundry_mcp_integration: ${{ needs.detect.outputs.foundry_mcp_integration }}", content)

    def test_aad_reusable_declares_and_embeds_three_agentic_inputs(self) -> None:
        content = self._read_workflow("auto-app-detail-design-web-reusable.yml")
        self.assertIn("enable_agentic_retrieval:", content)
        self.assertIn("agentic_data_source_modes:", content)
        self.assertIn("foundry_mcp_integration:", content)
        self.assertIn('if [[ "${ENABLE_AGENTIC_RETRIEVAL}" == "no" ]]; then', content)
        self.assertIn('FOUNDRY_MCP_INTEGRATION="false"', content)
        self.assertIn("<!-- enable-agentic-retrieval: %s -->", content)
        self.assertIn("<!-- agentic-data-source-modes: %s -->", content)
        self.assertIn("<!-- foundry-mcp-integration: %s -->", content)

    def test_asdw_reusable_declares_and_embeds_six_agentic_inputs(self) -> None:
        content = self._read_workflow("auto-app-dev-microservice-web-reusable.yml")
        self.assertIn("enable_agentic_retrieval:", content)
        self.assertIn("agentic_data_source_modes:", content)
        self.assertIn("foundry_mcp_integration:", content)
        self.assertIn("agentic_data_sources_hint:", content)
        self.assertIn("agentic_existing_design_diff_only:", content)
        self.assertIn("foundry_sku_fallback_policy:", content)
        self.assertIn("<!-- enable-agentic-retrieval: %s -->", content)
        self.assertIn("<!-- agentic-data-sources-hint: %s -->", content)
        self.assertIn("<!-- foundry-sku-fallback-policy: %s -->", content)
        self.assertIn('value = value.replace("<", "＜").replace(">", "＞")', content)
        self.assertIn('value = re.sub(r"--+"', content)


class TestOptionParityMatrix(unittest.TestCase):
    """option_parity_matrix.yaml を基準に Issue Form / SDKConfig / CLI の整合性を検証する。

    根拠ファイル:
      hve/tests/fixtures/option_parity_matrix.yaml （本テストの SSoT fixture）
      hve/config.py:111-      （SDKConfig dataclass フィールド定義）
      hve/__main__.py:566-    （orchestrate サブコマンド CLI 引数定義）
      .github/ISSUE_TEMPLATE/*.yml  （Issue Form フィールド ID）
      docs/design-discussions/orchestration-route-diff-spec.md
    """

    _FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "option_parity_matrix.yaml"
    _TEMPLATE_DIR = _REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
    # setup-labels.yml は選択式オプションを持たない管理用テンプレートなので除外
    _EXCLUDED_TEMPLATES = {"setup-labels.yml"}

    # ------------------------------------------------------------------ helpers

    @classmethod
    def _load_fixture(cls) -> dict:
        import yaml  # PyYAML
        with cls._FIXTURE_PATH.open(encoding="utf-8") as f:
            return yaml.safe_load(f)

    @classmethod
    def _all_form_ids(cls) -> set[str]:
        """全 Issue Template ファイルに現れる id: フィールドを列挙する。"""
        ids: set[str] = set()
        for tmpl in cls._TEMPLATE_DIR.glob("*.yml"):
            if tmpl.name in cls._EXCLUDED_TEMPLATES:
                continue
            content = tmpl.read_text(encoding="utf-8")
            for m in re.finditer(r"^\s+id:\s+(\w+)", content, re.MULTILINE):
                ids.add(m.group(1))
        return ids

    @classmethod
    def _sdkconfig_fields(cls) -> set[str]:
        """SDKConfig の全フィールド名を返す。"""
        import dataclasses
        import sys
        _sdk_dir = str(_REPO_ROOT / "hve")
        if _sdk_dir not in sys.path:
            sys.path.insert(0, _sdk_dir)
        from config import SDKConfig  # type: ignore[import]
        return {f.name for f in dataclasses.fields(SDKConfig)}

    @classmethod
    def _cli_option_strings(cls) -> set[str]:
        """orchestrate サブコマンドの全 CLI オプション文字列を返す（'--model' 形式）。"""
        import sys
        _repo_dir = str(_REPO_ROOT)
        if _repo_dir not in sys.path:
            sys.path.insert(0, _repo_dir)
        from hve.__main__ import _build_parser  # type: ignore[import]
        parser = _build_parser()
        flags: set[str] = set()
        for action in parser._actions:
            if hasattr(action, "_name_parser_map"):
                orch = action._name_parser_map.get("orchestrate")
                if orch:
                    for a in orch._actions:
                        if hasattr(a, "option_strings"):
                            flags.update(a.option_strings)
        return flags

    # ------------------------------------------------------------------ common

    def test_common_entries_have_issue_form_field(self) -> None:
        """common エントリの issue_form_field_id が少なくとも 1 つの Issue Template に存在すること。"""
        fixture = self._load_fixture()
        form_ids = self._all_form_ids()
        common = [e for e in fixture["options"] if e["applies_to"] == "common"]
        for entry in common:
            field_id = entry["issue_form_field_id"]
            with self.subTest(option_key=entry["option_key"], field_id=field_id):
                self.assertIsNotNone(field_id, "common エントリの issue_form_field_id は null にできません")
                self.assertIn(
                    field_id,
                    form_ids,
                    f"Issue Form に '{field_id}' が見つかりません（option_key={entry['option_key']}）",
                )

    def test_common_entries_have_sdkconfig_attr(self) -> None:
        """common エントリの hve_config_attr が SDKConfig のフィールドとして存在すること。"""
        fixture = self._load_fixture()
        sdk_fields = self._sdkconfig_fields()
        common = [e for e in fixture["options"] if e["applies_to"] == "common"]
        for entry in common:
            attr = entry["hve_config_attr"]
            with self.subTest(option_key=entry["option_key"], attr=attr):
                self.assertIsNotNone(attr, "common エントリの hve_config_attr は null にできません")
                self.assertIn(
                    attr,
                    sdk_fields,
                    f"SDKConfig に '{attr}' フィールドが見つかりません（option_key={entry['option_key']}）",
                )

    def test_common_entries_with_cli_flag_exist_in_cli(self) -> None:
        """common エントリで hve_cli_flag が設定されている場合、orchestrate CLI に存在すること。"""
        fixture = self._load_fixture()
        cli_flags = self._cli_option_strings()
        common_with_flag = [
            e for e in fixture["options"]
            if e["applies_to"] == "common" and e.get("hve_cli_flag")
        ]
        for entry in common_with_flag:
            flag = entry["hve_cli_flag"]
            with self.subTest(option_key=entry["option_key"], flag=flag):
                self.assertIn(
                    flag,
                    cli_flags,
                    f"CLI に '{flag}' が見つかりません（option_key={entry['option_key']}）",
                )

    # ------------------------------------------------------------------ issue_form_only

    def test_issue_form_only_entries_have_issue_form_field(self) -> None:
        """issue_form_only エントリの issue_form_field_id が少なくとも 1 つの Issue Template に存在すること。"""
        fixture = self._load_fixture()
        form_ids = self._all_form_ids()
        issue_only = [e for e in fixture["options"] if e["applies_to"] == "issue_form_only"]
        for entry in issue_only:
            field_id = entry["issue_form_field_id"]
            with self.subTest(option_key=entry["option_key"], field_id=field_id):
                self.assertIsNotNone(field_id, "issue_form_only エントリの issue_form_field_id は null にできません")
                self.assertIn(
                    field_id,
                    form_ids,
                    f"Issue Form に '{field_id}' が見つかりません（option_key={entry['option_key']}）",
                )

    def test_issue_form_only_entries_absent_from_sdkconfig(self) -> None:
        """issue_form_only エントリは hve_config_attr が null（SDKConfig に対応フィールドなし）であること。"""
        fixture = self._load_fixture()
        issue_only = [e for e in fixture["options"] if e["applies_to"] == "issue_form_only"]
        for entry in issue_only:
            with self.subTest(option_key=entry["option_key"]):
                self.assertIsNone(
                    entry.get("hve_config_attr"),
                    f"issue_form_only エントリ '{entry['option_key']}' の hve_config_attr は null でなければなりません",
                )

    # ------------------------------------------------------------------ hve_only

    def test_hve_only_entries_absent_from_issue_form(self) -> None:
        """hve_only エントリは issue_form_field_id が null（Issue Form に対応フィールドなし）であること。"""
        fixture = self._load_fixture()
        form_ids = self._all_form_ids()
        hve_only = [e for e in fixture["options"] if e["applies_to"] == "hve_only"]
        for entry in hve_only:
            with self.subTest(option_key=entry["option_key"]):
                field_id = entry.get("issue_form_field_id")
                self.assertIsNone(
                    field_id,
                    f"hve_only エントリ '{entry['option_key']}' の issue_form_field_id は null でなければなりません",
                )
                # 安全確認: null であることに加え Issue Form にも存在しないことを確認
                if field_id is not None:
                    self.assertNotIn(
                        field_id,
                        form_ids,
                        f"hve_only エントリ '{entry['option_key']}' が Issue Form に存在します",
                    )

    def test_hve_only_entries_have_sdkconfig_attr(self) -> None:
        """hve_only エントリの hve_config_attr が SDKConfig のフィールドとして存在すること。"""
        fixture = self._load_fixture()
        sdk_fields = self._sdkconfig_fields()
        hve_only = [e for e in fixture["options"] if e["applies_to"] == "hve_only"]
        for entry in hve_only:
            attr = entry.get("hve_config_attr")
            with self.subTest(option_key=entry["option_key"], attr=attr):
                self.assertIsNotNone(attr, "hve_only エントリの hve_config_attr は null にできません")
                self.assertIn(
                    attr,
                    sdk_fields,
                    f"SDKConfig に '{attr}' フィールドが見つかりません（option_key={entry['option_key']}）",
                )

    def test_hve_only_entries_with_cli_flag_exist_in_cli(self) -> None:
        """hve_only エントリで hve_cli_flag が設定されている場合、orchestrate CLI に存在すること。"""
        fixture = self._load_fixture()
        cli_flags = self._cli_option_strings()
        hve_only_with_flag = [
            e for e in fixture["options"]
            if e["applies_to"] == "hve_only" and e.get("hve_cli_flag")
        ]
        for entry in hve_only_with_flag:
            flag = entry["hve_cli_flag"]
            with self.subTest(option_key=entry["option_key"], flag=flag):
                self.assertIn(
                    flag,
                    cli_flags,
                    f"CLI に '{flag}' が見つかりません（option_key={entry['option_key']}）",
                )

    # ------------------------------------------------------------------ coverage (漏れ検知)

    def test_coverage_all_issue_form_ids_registered(self) -> None:
        """Issue Form の全フィールド ID（内部フィールド除く）が fixture に登録されていること。

        未登録のフィールドが存在すると fail するため、新規オプション追加時に fixture の
        更新が強制される（漏れ検知）。
        """
        fixture = self._load_fixture()
        internal_form_ids: set[str] = set(fixture.get("issue_form_internal_fields", []))
        registered_form_ids: set[str] = {
            e["issue_form_field_id"]
            for e in fixture["options"]
            if e.get("issue_form_field_id") is not None
        }
        actual_form_ids = self._all_form_ids()
        unregistered = actual_form_ids - internal_form_ids - registered_form_ids
        self.assertEqual(
            unregistered,
            set(),
            f"fixture に未登録の Issue Form フィールド ID があります: {sorted(unregistered)}\n"
            "option_parity_matrix.yaml の options または issue_form_internal_fields に追加してください。",
        )

    def test_each_issue_form_has_unique_field_ids(self) -> None:
        for template in self._TEMPLATE_DIR.glob("*.yml"):
            if template.name in self._EXCLUDED_TEMPLATES:
                continue
            ids = re.findall(
                r"^\s+id:\s+(\w+)",
                template.read_text(encoding="utf-8"),
                re.MULTILINE,
            )
            with self.subTest(template=template.name):
                duplicates = {field_id for field_id in ids if ids.count(field_id) > 1}
                self.assertEqual(duplicates, set())

    def test_dataflow_dev_keeps_app_and_job_ids_distinct(self) -> None:
        template = (
            self._TEMPLATE_DIR / "dataflow-dev.yml"
        ).read_text(encoding="utf-8")
        workflow = (
            _WORKFLOW_DIR / "auto-dataflow-dev-reusable.yml"
        ).read_text(encoding="utf-8")
        self.assertEqual(template.count("id: app_ids"), 1)
        self.assertEqual(template.count("id: job_ids"), 1)
        self.assertIn('"job_ids": job_ids', workflow)
        self.assertEqual(workflow.count('"app_ids": app_ids_list'), 1)
        self.assertIn("JOB_IDS=$(echo", workflow)
        self.assertIn('JOB_SECTION=$(printf', workflow)
        self.assertIn('"${JOB_IDS}")', workflow)

    def test_coverage_all_sdkconfig_fields_registered(self) -> None:
        """SDKConfig の全フィールド（内部フィールド除く）が fixture に登録されていること。

        未登録のフィールドが存在すると fail するため、新規 SDKConfig フィールド追加時に
        fixture の更新が強制される（漏れ検知）。
        """
        fixture = self._load_fixture()
        internal_sdk_fields: set[str] = set(fixture.get("sdkconfig_internal_fields", []))
        registered_sdk_attrs: set[str] = {
            e["hve_config_attr"]
            for e in fixture["options"]
            if e.get("hve_config_attr") is not None
        }
        actual_sdk_fields = self._sdkconfig_fields()
        unregistered = actual_sdk_fields - internal_sdk_fields - registered_sdk_attrs
        self.assertEqual(
            unregistered,
            set(),
            f"fixture に未登録の SDKConfig フィールドがあります: {sorted(unregistered)}\n"
            "option_parity_matrix.yaml の options または sdkconfig_internal_fields に追加してください。",
        )

    def test_fixture_option_keys_are_unique(self) -> None:
        """fixture の option_key が重複していないこと。"""
        fixture = self._load_fixture()
        keys = [e["option_key"] for e in fixture["options"]]
        duplicates = {k for k in keys if keys.count(k) > 1}
        self.assertEqual(duplicates, set(), f"fixture に重複する option_key があります: {sorted(duplicates)}")

    def test_fixture_applies_to_values_are_valid(self) -> None:
        """fixture の applies_to 値がすべて有効であること（common / issue_form_only / hve_only）。"""
        fixture = self._load_fixture()
        valid = {"common", "issue_form_only", "hve_only"}
        for entry in fixture["options"]:
            with self.subTest(option_key=entry["option_key"]):
                self.assertIn(
                    entry["applies_to"],
                    valid,
                    f"不正な applies_to 値: '{entry['applies_to']}' (option_key={entry['option_key']})",
                )


if __name__ == "__main__":
    unittest.main()
