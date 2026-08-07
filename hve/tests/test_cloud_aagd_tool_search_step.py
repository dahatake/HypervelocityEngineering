"""AAGD Cloud（`auto-ai-agent-dev-reusable.yml`）の tool search 実測 Step の契約。

再利用 YAML は SSoT（`workflow-registry.sh`）へ統一済み。
Cloud も registry と同じ `Step.4` を使う。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = "auto-ai-agent-dev-reusable.yml"


@pytest.fixture(scope="module")
def text() -> str:
    path = _REPO_ROOT / ".github" / "workflows" / _WORKFLOW
    assert path.exists(), f"{_WORKFLOW} が存在しない"
    return path.read_text(encoding="utf-8")


def _case_body(text: str, step_id: str) -> str:
    marker = f'            "{step_id}")\n'
    start = text.index(marker) + len(marker)
    return text[start:].split("\n              ;;", 1)[0]


class TestStepIssueCreation:
    def test_creates_step_4(self, text):
        assert "[AAGD] Step.4: tool search 実測評価" in text

    def test_uses_the_eval_agent(self, text):
        assert "QA-ToolSearchEval" in text

    def test_declares_the_variables(self, text):
        """未宣言のままだと `set -u` 環境で落ちる。"""
        assert 'S4_NUM=""  S4_ID=""' in text

    def test_output_path_matches_registry(self, text):
        """registry の `output_paths_template` と同じ場所へ書かせる。"""
        assert "docs/agent/tool-search-eval/" in text

    def test_created_after_deploy_step(self, text):
        """Toolbox が無い状態で測っても意味がない。"""
        deploy = text.index("[AAGD] Step.3: AI Agent Deploy")
        eval_step = text.index("[AAGD] Step.4: tool search 実測評価")
        assert deploy < eval_step

    def test_is_independently_skippable(self, text):
        """Issue Form の Step.4 チェックがそのまま効くこと。"""
        assert 'if ! skip_step "4"; then' in text


class TestTransitionChain:
    def test_3_activates_4(self, text):
        section = _case_body(text, "3")
        assert r"\[AAGD\] Step\.4:" in section
        assert "activate_issue" in section

    def test_4_ends_the_workflow(self, text):
        """最終 Step が Self-Improve へ渡らないと Root が閉じない。"""
        section = _case_body(text, "4")
        assert "mark_root_self_improve_ready" in section

    def test_3_falls_back_when_4_absent(self, text):
        """skip 等で Step.4 が無い場合に停止しない。"""
        section = _case_body(text, "3")
        assert "mark_root_self_improve_ready" in section

    def test_step_2_container_is_closed_by_2_3(self, text):
        section = _case_body(text, "2.3")
        assert 'add_label "${S2_NUM}" "aagd:done"' in section

    def test_deploy_transition_is_shared(self, text):
        """Step.1 / 2.1 / 2.2 / 2.3 が同じ遷移先関数を使う。"""
        assert text.count("activate_deploy_or_eval_or_finish() {") == 1
        assert text.count("activate_deploy_or_eval_or_finish\n") >= 4

    def test_helper_reaches_deploy_then_eval(self, text):
        helper = text.split("activate_deploy_or_eval_or_finish() {", 1)[1]
        helper = helper.split("\n          }", 1)[0]
        assert r"\[AAGD\] Step\.3:" in helper
        assert r"\[AAGD\] Step\.4:" in helper
        assert "mark_root_self_improve_ready" in helper


class TestRegistryParity:
    """SSoT と実行 YAML が同じ Step を指すこと。"""

    def test_ssot_declares_step_4(self):
        from hve.dag_parity import extract_bash_workflow_steps

        path = (
            _REPO_ROOT / ".github" / "scripts" / "bash" / "lib" / "workflow-registry.sh"
        )
        assert "4" in extract_bash_workflow_steps(path, "aagd")

    @pytest.mark.parametrize(
        "legacy", ["Step.2.6", "Step.2.7", "Step.2.8", "Step.2.9", "Step.2.3TC"]
    )
    def test_no_legacy_numbering_left(self, text, legacy):
        assert legacy not in text, f"旧採番 {legacy} が残存"

    def test_agent_name_is_identical_across_ssot_and_yaml(self, text):
        registry = (
            _REPO_ROOT / ".github" / "scripts" / "bash" / "lib" / "workflow-registry.sh"
        ).read_text(encoding="utf-8")
        assert "QA-ToolSearchEval" in registry
        assert "QA-ToolSearchEval" in text


class TestStepMatchCompatibility:
    def test_step_match_regex_accepts_4(self, text):
        """title から Step 番号を取り出す正規表現が 4 を拾えること。"""
        pattern = re.search(r"re\.search\(r?['\"](.+?Step\\\..+?)['\"]", text)
        assert pattern, "STEP_MATCH の抽出パターンが見つからない"
        compiled = re.compile(pattern.group(1))
        assert compiled.search("[AAGD] Step.4: tool search 実測評価").group(1) == "4"
        assert compiled.search("[AAGD] Step.2.1: x").group(1) == "2.1"


class TestMeasurementIntegrity:
    """Issue 本文だけを読む Agent にも捏造禁止が伝わること。"""

    def test_forbids_citing_benchmark_as_own_measurement(self, text):
        assert "公開ベンチマークの数値を自社の実測値として引用しない" in text

    def test_forbids_unmeasured_numbers(self, text):
        assert "測定していない数値を書かない" in text

    def test_requires_both_tokens_and_accuracy(self, text):
        assert "両方を並記する" in text

    def test_names_the_benchmark(self, text):
        assert "ToolRet" in text

    def test_requires_a_reasoned_na_report(self, text):
        """io-contract の output は required。省略を許すと矛盾する。"""
        assert "理由付き N/A レポート" in text
        assert "成果物なしで完了する" not in text

    def test_declares_the_fixed_report_labels(self, text):
        body = text.split("BODY_S4=$(printf '", 1)[1].split("' \\", 1)[0]
        for label in ("Query ID", "Expected tools", "Measured off", "Conclusion"):
            assert label in body, f"{label} が Step.4 本文に無い"

    def test_percent_sign_is_not_emitted_raw(self, text):
        """printf 書式内の `%` は引数対応を壊す。文言側で避けている。"""
        body = text.split("BODY_S4=$(printf '", 1)[1].split("' \\", 1)[0]
        assert "%" not in body.replace("%s", ""), "printf 書式に %s 以外の % がある"


class TestToolSearchPolicyPropagation:
    """FR-WF-AAG-01: Issue Form の方針が Root タグと各 Step 本文へ届く。"""

    def test_parses_the_form_value(self, text):
        assert "tool_search_policy" in text

    def test_missing_value_defaults_to_auto(self, text):
        assert 'tool_search_policy = "auto"' in text

    def test_invalid_value_fails(self, text):
        assert "Invalid tool search policy" in text

    def test_writes_the_root_metadata_tag(self, text):
        assert "tool-search-policy" in text

    def test_injects_into_implementation_deploy_and_eval(self, text):
        """設計・実装・デプロイ・評価で方針が割れないようにする。"""
        assert text.count('"${TOOL_SEARCH_SECTION}"') == 3

    def test_does_not_inject_into_unrelated_steps(self, text):
        for marker in ("BODY_S1=$(printf", "BODY_S21=$(printf"):
            if marker not in text:
                continue
            body = text.split(marker, 1)[1].split("create_issue", 1)[0]
            assert "TOOL_SEARCH_SECTION" not in body

    def test_forbids_agent_side_override(self, text):
        section = text.split("TOOL_SEARCH_SECTION=$(printf", 1)[1].split("\n", 1)[0]
        assert "上書きしない" in section

    def test_no_policy_skips_step_4(self, text):
        """Toolbox が無い構成で実測 Step を作ると必ず空振りする。"""
        assert 'if [[ "${TOOL_SEARCH_POLICY}" == "no" ]]; then' in text

    def test_no_policy_keeps_implementation_and_deploy(self, text):
        """tool search を切っただけで Agent 実装・デプロイまで止めない。"""
        for marker in ('skip_step "2"', 'skip_step "3"'):
            assert marker in text
        guard = text.split('if [[ "${TOOL_SEARCH_POLICY}" == "no" ]]; then', 1)[1]
        guard = guard.split("fi", 1)[0]
        assert "2.3" not in guard and "Step.3" not in guard


class TestPostDagArtifactRevalidation:
    """FR-WF-AAGD-04: label が全 done でも artifact が不正なら Self-Improve へ進ませない。"""

    def test_gate_receives_the_checked_out_repo_root(self, text):
        assert "--repo-root" in text

    def test_gate_receives_the_policy(self, text):
        assert "--tool-search-policy" in text

    def test_post_dag_parse_reads_the_policy_tag(self, text):
        assert "tool_search_policy=" in text

    def test_gate_runs_before_self_improve(self, text):
        gate = text.index("Revalidate AAGD TDD and Deploy gates before mutation")
        self_improve = text.index("Run mandatory AAGD Post-DAG Self-Improve")
        assert gate < self_improve
