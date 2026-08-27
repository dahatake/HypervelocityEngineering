"""ASDW-WEB UI fan-out 子の共有設定ファイル保護契約テスト。"""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS = _REPO_ROOT / ".github" / "prompts"
_TEMPLATES = _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web"
_IO_CONTRACTS = _REPO_ROOT / ".github" / "io-contracts"
_FANOUT_COMMON = _REPO_ROOT / ".github" / "prompts" / "fanout" / "asdw-web" / "_common.prompt.md"


_ROOT_SHARED_GUARD = "リポジトリルートの `package.json` / `jest.config.js` を作成・更新しない"
_UNRESOLVED_CONTRACT_NOT_GREEN_TEST = "未確定契約は後続 GREEN Step で PASS 必須の実行テストにしない"
_UITEST_UNRESOLVED_CONTRACT_POLICY = "TBD（要確認）を含む未確定契約を GREEN 必達の実行テストとして生成しない"
_UICODING_BLOCKER_POLICY = "テスト側/共有設定側の確定ブロッカーで実装だけでは GREEN 化不能な場合は成功扱いせず"
_UITEST_RERUN_NO_FABRICATION = "RED を作るための失敗テストは捏造しない"
_UITEST_RERUN_RECONCILE = "再整合（置換）"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ui_testcoding_prompt_keeps_root_jest_and_package_readonly() -> None:
    text = _read(_PROMPTS / "Dev-Microservice-Azure-UITestCoding.prompt.md")

    assert _ROOT_SHARED_GUARD in text
    assert "src/test/ui/{screenId}/" in text
    assert "`package.json`（または相当のプロジェクト設定ファイル）がなければ作成する" not in text


def test_ui_testcoding_prompt_distinguishes_workflow_id_from_agent_name() -> None:
    text = _read(_PROMPTS / "Dev-Microservice-Azure-UITestCoding.prompt.md")

    assert "<workflow-id>` は HVE workflow id" in text
    assert "ASDW-WEB では `asdw-web`" in text
    assert "Agent 名 `Dev-Microservice-Azure-UITestCoding` を workflow id として使わない" in text
    assert "## TDD report 出力先（HVE gate 必須）" in text


def test_asdw_step41_template_prioritizes_hve_tdd_report_path() -> None:
    text = _read(_TEMPLATES / "step-4.1.prompt.md")

    assert "<workflow-id>` は HVE workflow id" in text
    assert "ASDW-WEB では `asdw-web`" in text
    assert "Agent 名 `Dev-Microservice-Azure-UITestCoding` を workflow id として使わない" in text
    assert "## TDD report 出力先（HVE gate 必須）" in text


def test_ui_coding_prompt_does_not_generate_or_expand_step41_tests() -> None:
    text = _read(_PROMPTS / "Dev-Microservice-Azure-UICoding.prompt.md")

    assert _ROOT_SHARED_GUARD in text
    assert "GREEN フェーズではテストコードを新規生成・拡張せず" in text
    assert "## 2.5) Step.4.1 RED テスト成果物の確認" in text
    assert "## 2.5) テスト仕様書 → テストコード変換" not in text
    assert "src/test/ui/` にテストコード（テスト仕様書から変換" not in text


def test_asdw_step_templates_repeat_fanout_shared_config_guard() -> None:
    for name in ["step-4.1.prompt.md", "step-4.2.prompt.md"]:
        text = _read(_TEMPLATES / name)
        assert "## fan-out 共有設定ファイル保護" in text
        assert "リポジトリルートの `package.json` / `jest.config.js` を作成・更新しない" in text


def test_uicoding_asdw_io_contract_treats_ui_tests_as_input_not_create_output() -> None:
    text = _read(_IO_CONTRACTS / "Dev-Microservice-Azure-UICoding--asdw-web--4.2.yaml")
    inputs, outputs = text.split("outputs:", 1)

    assert "- path: src/test/ui/" in inputs
    assert "producer: Dev-Microservice-Azure-UITestCoding--asdw-web--4.1" in inputs
    assert "- path: src/test/ui/\n  required: true\n  mode: create" not in outputs


def test_tdd_testspec_prompt_keeps_unresolved_contracts_out_of_green_required_tests() -> None:
    text = _read(_PROMPTS / "Arch-TDD-TestSpec.prompt.md")

    assert _UNRESOLVED_CONTRACT_NOT_GREEN_TEST in text
    assert "契約確定待ち" in text


def test_ui_testcoding_prompt_does_not_turn_unresolved_contracts_into_green_required_tests() -> None:
    text = _read(_PROMPTS / "Dev-Microservice-Azure-UITestCoding.prompt.md")

    assert _UITEST_UNRESOLVED_CONTRACT_POLICY in text
    assert "テスト内ローカル定数" in text
    assert "契約確定待ち" in text


def test_ui_testcoding_prompt_requires_pre_completion_unresolved_contract_scan() -> None:
    text = _read(_PROMPTS / "Dev-Microservice-Azure-UITestCoding.prompt.md")

    assert "完了前" in text
    assert "src/test/ui/{screenId}/" in text
    assert "非コメント" in text
    assert "TBD（要確認" in text


def test_ui_coding_prompt_records_unresolvable_test_blocker_as_blocked_not_success() -> None:
    text = _read(_PROMPTS / "Dev-Microservice-Azure-UICoding.prompt.md")

    assert _UICODING_BLOCKER_POLICY in text
    assert "TDD-Judgement: BLOCKED" in text
    assert "部分完了を成功として主張しない" in text


def test_asdw_ui_step_templates_repeat_unresolved_contract_policy() -> None:
    step41 = _read(_TEMPLATES / "step-4.1.prompt.md")
    step42 = _read(_TEMPLATES / "step-4.2.prompt.md")

    assert _UITEST_UNRESOLVED_CONTRACT_POLICY in step41
    assert _UICODING_BLOCKER_POLICY in step42


def test_asdw_step41_template_does_not_allow_src_app_stub_creation() -> None:
    text = _read(_TEMPLATES / "step-4.1.prompt.md")

    assert "最小スタブの配置" not in text
    assert "src/app/` 配下" not in text
    assert "配置してよい" not in text


def test_asdw_web_fanout_common_uses_actual_service_and_screen_key_paths() -> None:
    text = _read(_FANOUT_COMMON)

    assert "per-screen (`APP-*-S*`)" in text
    assert "docs/services/{{key}}-description.md" in text
    assert "docs/screen/{{key}}-description.md" in text
    assert "per-screen (`SC-*`)" not in text
    assert "docs/screen/{{key}}.md" not in text
    assert "docs/services/{{key}}.md" not in text


def test_ui_red_prompt_and_template_are_rerun_aware_with_tool_hygiene() -> None:
    """Step.4.1 RED prompt/template が再実行認識（canonical PASS 許容・失敗テスト捏造禁止・
    累積は再整合）とツール利用衛生を持つことを固定する。root cause B の main 反映を保護。"""
    prompt = _read(_PROMPTS / "Dev-Microservice-Azure-UITestCoding.prompt.md")
    step41 = _read(_TEMPLATES / "step-4.1.prompt.md")

    for text in (prompt, step41):
        assert _UITEST_RERUN_NO_FABRICATION in text
        assert _UITEST_RERUN_RECONCILE in text
        assert "*.red-gaps" in text
        assert "PASS し得る" in text
        assert "## ツール利用衛生（fan-out）" in text
        assert "view_range out of bounds" in text
        assert "markdown-query" in text
