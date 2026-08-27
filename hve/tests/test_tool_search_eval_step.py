"""AAGD Step.4 (QA-ToolSearchEval) の契約テスト。

この Step の存在意義は「公開ベンチマークの数値を自社の効果として信じない」こと。
したがって検証の中心は、Step が配線されていることだけでなく、
Prompt / テンプレートが**実測を強制し、ベンチマーク値の流用を禁止している**こと。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from hve.workflow_registry import get_workflow

_REPO = Path(__file__).resolve().parents[2]
_PROMPT = _REPO / ".github" / "prompts" / "QA-ToolSearchEval.prompt.md"
_TEMPLATE = _REPO / ".github" / "prompts" / "steps" / "aagd" / "step-4.prompt.md"
_CONTRACT = _REPO / ".github" / "io-contracts" / "QA-ToolSearchEval--aagd--4.yaml"


def _step() -> object:
    aagd = get_workflow("aagd")
    for step in aagd.steps:
        if step.id == "4":
            return step
    raise AssertionError("aagd に Step.4 が存在しない")


@pytest.fixture(scope="module")
def prompt_text() -> str:
    return _PROMPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def template_text() -> str:
    return _TEMPLATE.read_text(encoding="utf-8")


class TestRegistryWiring:
    """レジストリ上の配線。"""

    def test_step_exists_with_expected_agent(self):
        assert _step().custom_agent == "QA-ToolSearchEval"

    def test_runs_after_deploy(self):
        """デプロイ前に実測はできない。"""
        assert _step().depends_on == ["3"]

    def test_is_fanout_per_agent(self):
        """Agent ごとに Tool 構成が違うので、Agent 単位で測る。"""
        assert _step().fanout_parser == "agent_catalog"

    def test_output_is_per_agent(self):
        assert _step().output_paths_template == [
            "docs/agent/tool-search-eval/{key}-eval-report.md"
        ]

    def test_output_does_not_collide_with_design_doc_glob(self, tmp_path, monkeypatch):
        """`docs/agent/*.md` は aagd ← aag のメタ依存ゲートの判定 glob。

        評価レポートを直下に置くと、設計書が無いのにゲートが通る偽 GREEN になる。
        ゲートと同じ `glob.iglob` で確かめる（fnmatch は `/` を跨ぐため意味が違う）。
        """
        import glob as _glob

        for template in _step().output_paths_template:
            target = tmp_path / template.replace("{key}", "sample-agent")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        assert next(_glob.iglob("docs/agent/*.md"), None) is None, (
            "評価レポートだけで aag の前提成果物チェックが通ってしまう"
        )

    def test_requires_toolbox_skill(self):
        """TB-CAP-02 の判定を評価するので Skill が必要。"""
        assert "foundry-toolbox-contract" in _step().required_skills

    def test_skipped_when_tool_search_disabled(self):
        """tool search を使わない構成では Toolbox 自体が無く、測る対象がない。"""
        assert _step().disabled_when_config == {"enable_tool_search": ["no"]}

    def test_not_skipped_on_auto(self):
        """auto は「設計側で判定」であって「無効」ではない。

        auto で skip すると、有効化した Agent の効果測定が永久に走らない。
        """
        disabled = _step().disabled_when_config or {}
        assert "auto" not in disabled.get("enable_tool_search", [])
        assert "yes" not in disabled.get("enable_tool_search", [])

    def test_design_artifact_is_an_input(self):
        """設計値 (TB-CAP) と実測を突き合わせるため設計書が要る。"""
        assert "docs/agent/agent-detail-{key}.md" in _step().required_input_paths


class TestSkipResolutionActuallyWorks:
    """宣言だけでなく、解決関数が実際に Step.4 を落とすこと。

    `disabled_when_config` は宣言と解決が別モジュールにあるため、
    宣言しただけで効いていると誤認しやすい。
    """

    def test_no_disables_step_4(self):
        from hve.workflow_registry import resolve_disabled_step_ids

        disabled = resolve_disabled_step_ids("aagd", {"enable_tool_search": "no"})
        assert "4" in disabled

    @pytest.mark.parametrize("value", ["auto", "yes"])
    def test_auto_and_yes_keep_step_4(self, value):
        from hve.workflow_registry import resolve_disabled_step_ids

        disabled = resolve_disabled_step_ids("aagd", {"enable_tool_search": value})
        assert "4" not in disabled

    def test_config_exposes_the_key(self):
        """解決は `getattr(config, key)` に依存する。属性名の綴りを固定する。"""
        from hve.config import SDKConfig

        assert hasattr(SDKConfig(), "enable_tool_search")

    def test_other_aagd_steps_are_not_affected(self):
        """tool search を切っただけで Agent 実装・デプロイまで止めない。"""
        from hve.workflow_registry import resolve_disabled_step_ids

        disabled = resolve_disabled_step_ids("aagd", {"enable_tool_search": "no"})
        assert disabled == {"4"}


class TestSurfaceParityOfTheStep:
    """CLI/GUI(registry) と Cloud(bash registry / Issue Form) の三者一致。

    registry にだけ Step を足すと Cloud が追随せず、
    「GUI では走るが Cloud では走らない」状態になる。
    """

    def test_bash_registry_declares_the_same_step(self):
        from hve.dag_parity import extract_bash_workflow_steps

        path = _REPO / ".github" / "scripts" / "bash" / "lib" / "workflow-registry.sh"
        assert "4" in extract_bash_workflow_steps(path, "aagd")

    def test_bash_registry_uses_the_same_agent_and_template(self):
        registry = (
            _REPO / ".github" / "scripts" / "bash" / "lib" / "workflow-registry.sh"
        ).read_text(encoding="utf-8")
        line = next(
            ln for ln in registry.splitlines()
            if '"id":"4"' in ln and "QA-ToolSearchEval" in ln
        )
        assert '"custom_agent":"QA-ToolSearchEval"' in line
        assert '"depends_on":["3"]' in line
        assert _step().body_template_path in line

    def test_issue_form_lists_the_step(self):
        form = (
            _REPO / ".github" / "ISSUE_TEMPLATE" / "ai-agent-dev.yml"
        ).read_text(encoding="utf-8")
        assert "**Step.4**" in form
        assert "Step.4 — tool search 実測評価" in form

    def test_issue_form_dependency_note_includes_step_4(self):
        """skip 判定は top-level 番号で行うため、Step.4 が一覧に無いと選べない。"""
        form = (
            _REPO / ".github" / "ISSUE_TEMPLATE" / "ai-agent-dev.yml"
        ).read_text(encoding="utf-8")
        assert "Step.3 → Step.4" in form


class TestIoContract:
    """io-contract の内容がレジストリと一致すること。"""

    def test_contract_file_exists(self):
        assert _CONTRACT.exists()

    def test_output_matches_registry(self):
        data = yaml.safe_load(_CONTRACT.read_text(encoding="utf-8"))
        paths = [o["path"] for o in data["outputs"]]
        assert paths == _step().output_paths_template

    def test_inputs_cover_registry_required_inputs(self):
        data = yaml.safe_load(_CONTRACT.read_text(encoding="utf-8"))
        declared = {i["path"] for i in data["inputs"]}
        for path in _step().required_input_paths:
            assert path in declared, f"{path} が io-contract に無い"


class TestPromptForbidsBenchmarkReuse:
    """本 Step の中核。ベンチマーク値の自社実績化を禁じているか。"""

    def test_forbids_citing_benchmark_as_own_measurement(self, prompt_text):
        assert "公開ベンチマークの数値を自社の実測値として引用しない" in prompt_text

    def test_names_the_benchmark_so_readers_can_verify(self, prompt_text):
        """出典を書かないと「誰かが言っていた数値」になる。"""
        assert "ToolRet" in prompt_text

    def test_forbids_unmeasured_numbers(self, prompt_text):
        assert "測定していない数値" in prompt_text

    def test_requires_marking_unmeasured_metrics(self, prompt_text):
        assert "未測定" in prompt_text

    def test_forbids_rounding_to_match_design(self, prompt_text):
        """設計書に実測を合わせると測定した意味が消える。"""
        assert "丸めない" in prompt_text

    def test_forbids_reporting_tokens_without_accuracy(self, prompt_text):
        """トークンだけ報告して精度低下を隠す経路を塞ぐ。"""
        assert "両方を並記" in prompt_text


class TestPromptMeasurementDesign:
    """測定設計が実用に耐えるか。"""

    def test_requires_both_on_and_off(self, prompt_text):
        assert "on / off" in prompt_text

    def test_requires_identical_query_set(self, prompt_text):
        assert "同一クエリ集合" in prompt_text or "同一の Toolbox・同一クエリ集合" in prompt_text

    def test_requires_expected_tool_set_recorded_in_advance(self, prompt_text):
        """事後に期待値を決めると正解率が作為的になる。"""
        assert "事前に記録" in prompt_text

    def test_requires_negative_queries(self, prompt_text):
        """該当 Tool が無いタスクを入れないと過剰呼び出しを検出できない。"""
        assert "実行すべき Tool が存在しないタスク" in prompt_text
        assert "過剰呼び出し" in prompt_text

    def test_requires_multi_tool_queries(self, prompt_text):
        assert "複数 Tool" in prompt_text

    def test_keeps_prompt_caching_on_in_baseline(self, prompt_text):
        """caching を切って比べるとトークン削減が過大に出る。"""
        assert "prompt caching" in prompt_text
        assert "無効化して比較しない" in prompt_text

    @pytest.mark.parametrize(
        "metric",
        [
            "tools/list",
            "総入力トークン",
            "正解率",
            "tool_search",
            "レイテンシ",
            "過剰呼び出し率",
        ],
    )
    def test_metric_is_listed(self, prompt_text, metric):
        assert metric in prompt_text

    def test_latency_uses_percentiles(self, prompt_text):
        """平均だけでは検索ラウンドトリップの尾を捉えられない。"""
        assert "p50" in prompt_text and "p95" in prompt_text


class TestPromptJudgement:
    """判定基準が行動につながるか。"""

    def test_low_reduction_leads_to_description_fix(self, prompt_text):
        assert "20%" in prompt_text
        assert "additional_search_text" in prompt_text

    def test_accuracy_drop_leads_to_pinning_review(self, prompt_text):
        assert "10%" in prompt_text
        assert "pin" in prompt_text

    def test_conclusion_targets_tb_cap_02(self, prompt_text):
        """測って終わりにせず、TB-CAP-02 の判定へ戻す。"""
        assert "TB-CAP-02" in prompt_text

    def test_declares_skill_dependency(self, prompt_text):
        assert "foundry-toolbox-contract" in prompt_text

    def test_declares_non_goals(self, prompt_text):
        """測定 Step が Tool を書き換え始めると原因と結果が混ざる。"""
        assert "Non-goals" in prompt_text

    def test_records_measurement_conditions(self, prompt_text):
        """条件が無い測定値は再現も比較もできない。"""
        assert "測定条件" in prompt_text
        assert "version" in prompt_text

    def test_requires_a_reasoned_na_report_without_toolbox(self, prompt_text):
        """io-contract の output は required なので、省略を許すと矛盾する。"""
        assert "成果物を省略しない" in prompt_text
        assert "Recheck condition" in prompt_text

    def test_declares_the_fixed_report_labels(self, prompt_text):
        for label in ("Query ID", "Expected tools", "Measured off", "Conclusion"):
            assert label in prompt_text, f"{label} が Prompt に無い"


class TestTemplate:
    """Issue 本文テンプレート。"""

    def test_has_additional_section_placeholder(self, template_text):
        assert "{additional_section}" in template_text

    def test_has_completion_instruction_placeholder(self, template_text):
        assert "{completion_instruction}" in template_text

    def test_does_not_hardcode_legacy_done_label_instruction(self, template_text):
        """done ラベル指示は completion_instruction が注入する。二重化を防ぐ。"""
        assert "完了時に自身に" not in template_text

    def test_placeholders_are_supported_by_template_engine(self, template_text):
        """未対応プレースホルダは Issue 本文へ生のまま残る。"""
        supported = {
            "root_ref",
            "app_arch_scope_section",
            "existing_artifact_policy",
            "completion_instruction",
            "app_id_section",
            "additional_section",
            "resource_group",
            "key",
            "WORK",
        }
        used = set(re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", template_text))
        assert used <= supported, f"未対応のプレースホルダ: {used - supported}"

    def test_template_forbids_benchmark_reuse_too(self, template_text):
        """Prompt を読まずテンプレートだけ見る経路でも禁止事項が伝わること。"""
        assert "公開ベンチマークの数値を自社の実測値として引用しない" in template_text

    def test_template_declares_dependency_on_deploy(self, template_text):
        assert "Step.3" in template_text

    def test_template_requires_a_reasoned_na_report(self, template_text):
        """TB-CAP を持たない Agent でも、成果物を省略しては判断が残らない。"""
        assert "理由付き N/A レポート" in template_text
        assert "成果物なしで完了" not in template_text

    def test_template_declares_the_fixed_report_labels(self, template_text):
        for label in ("Query ID", "Expected tools", "Measured off", "Conclusion"):
            assert label in template_text, f"{label} がテンプレートに無い"
