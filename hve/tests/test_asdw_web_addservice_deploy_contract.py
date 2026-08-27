"""ASDW-WEB コンテナ2（追加サービス: Step.2.2〜2.4）の prompt/template 契約テスト。

前半（Step.2.2 deploy_ac_gate_failed 抑止）: Agent が必須成果物 `ac-verification.md` を
生成しないままターンを終え、ローカル実行にもかかわらず git/PR 操作へ脱線した事象への
再発抑止として追加した契約が消えないことを検証する:
  - prompt 禁止事項: ac-verification.md 必達 / 出力契約外成果物の作成禁止 /
    同期完了済みコマンドの再取得禁止 / ローカル実行時の git・PR 操作禁止
  - prompt の ac-verification.md 出力先が gate 整合（`Issue-<識別子>` 直下）で統一
  - step-2.2 テンプレの `## 出力` に ac-verification.md（直下）が列挙され、
    `{completion_instruction}` の自己完了チェック対象に含まれる

後半（Foundry モデルデプロイ品質）: 追加サービスの Microsoft Foundry が「クラシック
（project 管理無効）アカウント作成のみ・モデル未デプロイ」でも GREEN になる構造的欠陥
（aiservices.sh のアカウント作成のみ・テストの恒真式アサーション）の再発抑止として、
生成元（Design/Deploy/TestCoding/Testing の prompt とテンプレ step-2.2〜2.4）に追加した
品質契約が消えないことをキーフレーズ部分一致で検証する（脆性低減のため文言完全一致は避ける）。
本ファイルは生成元の指示契約を検証し、生成された shell artifact の実コマンド検証は
`artifact_validation.py` の専用 gate が担当する。
第三部（create.sh のサービス作成並列実行契約）: create.sh が services/<service>.sh を逆次実行ではなく
バックグラウンドジョブで並列実行する方針（2 waves構成・ログ分離・終了コード集約・
`created-resources.json` 書き込み衝突防止）が生成元（Deploy prompt と step-2.2 テンプレ）から
消えないことを検証する。"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_DIR = _REPO_ROOT / ".github" / "prompts"
_TEMPLATES_DIR = _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web"
_PROMPT = _PROMPTS_DIR / "Dev-Microservice-Azure-AddServiceDeploy.prompt.md"
_DESIGN_PROMPT = _PROMPTS_DIR / "Dev-Microservice-Azure-AddServiceDesign.prompt.md"
_TESTCODING_PROMPT = _PROMPTS_DIR / "Dev-Microservice-Azure-AddServiceTestCoding.prompt.md"
_TESTING_PROMPT = _PROMPTS_DIR / "Dev-Microservice-Azure-AddServiceTesting.prompt.md"
_COMPUTE_DESIGN_PROMPT = _PROMPTS_DIR / "Dev-Microservice-Azure-ComputeDesign.prompt.md"
_AAD_STEP_2_5 = _REPO_ROOT / ".github" / "prompts" / "steps" / "aad-web" / "step-2.5.prompt.md"
_STEP_2_1 = _TEMPLATES_DIR / "step-2.1.prompt.md"
_STEP_2_2 = _TEMPLATES_DIR / "step-2.2.prompt.md"
_STEP_2_3 = _TEMPLATES_DIR / "step-2.3.prompt.md"
_STEP_2_4 = _TEMPLATES_DIR / "step-2.4.prompt.md"
_STEP_3_1 = _TEMPLATES_DIR / "step-3.1.prompt.md"


def test_addservice_deploy_prompt_requires_ac_verification_before_turn_end() -> None:
    """必須成果物 ac-verification.md 未生成での終了禁止が prompt に明記されている。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "作成しないままターンを終えない" in text


def test_addservice_deploy_prompt_prohibits_out_of_contract_artifact() -> None:
    """出力契約外成果物（PR 用課題管理表等）の作成禁止が prompt に明記されている。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "出力先パスに無い成果物" in text


def test_addservice_deploy_prompt_prohibits_resync_completed_command() -> None:
    """同期完了済みコマンドへの出力取得ツール再呼び出し禁止が prompt に明記されている。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "同期実行で既に完了したコマンド" in text


def test_addservice_deploy_prompt_prohibits_local_git_pr_ops() -> None:
    """ローカル実行時の git / PR 操作禁止が prompt に明記されている。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "ローカル実行時の git / PR 操作禁止" in text
    assert "gh pr create" in text


def test_prompt_ac_verification_path_is_issue_root_not_artifacts() -> None:
    """prompt の ac-verification.md 出力先が gate 整合（Issue 直下）で統一されている。

    gate（`_run_deploy_ac_gate`）は `Issue-*/ac-verification.md`（直下）のみを探索し
    `artifacts/` 配下に非マッチ。`{WORK}artifacts/ac-verification.md` という表記が
    残っていると Agent がそこに出力して gate が fail するため、直下表記に統一する。
    """
    text = _PROMPT.read_text(encoding="utf-8")
    assert "{WORK}artifacts/ac-verification.md" not in text
    assert "{WORK}ac-verification.md" in text


def test_step_2_2_template_lists_ac_verification_as_output() -> None:
    """Step.2.2 テンプレートの出力に ac-verification.md が run スコープ直下パスで列挙されている。

    `{completion_instruction}`（ローカル実行時の「上記の出力ファイルが全て生成されたか」
    確認）が ac-verification.md を対象に含めるため。gate は `Issue-<識別子>` 直下を
    検査するため、`artifacts/` 配下ではなく直下パスで列挙されていることを検証する。
    """
    text = _STEP_2_2.read_text(encoding="utf-8")
    assert "Issue-<識別子>/ac-verification.md" in text


# --- Foundry モデルデプロイ品質契約（コンテナ2: Step.2.1〜2.4） ---


def test_design_prompt_requires_model_deployment_keys() -> None:
    """T1: Design prompt が AI/LLM のモデルデプロイ必須情報（定型キー）の記載を要求する。

    クラシック AIServices アカウント作成のみ・モデル未デプロイで GREEN になる欠陥の
    上流対策として、設計書にデプロイ対象モデルの必須情報を残させる契約。
    """
    text = _DESIGN_PROMPT.read_text(encoding="utf-8")
    assert "デプロイ対象モデルの必須情報を定型キー" in text
    # アカウント SKU と混同しないよう sku-name を明示している
    assert "デプロイ種別(sku-name)" in text


def test_design_prompt_requires_foundry_project_contract_keys() -> None:
    """T1: Design prompt が account と別に Foundry Project 契約を残す。"""
    text = _DESIGN_PROMPT.read_text(encoding="utf-8")
    for key in ("Foundry Project名", "Project location", "Project作成方針"):
        assert key in text


def test_design_prompt_requires_explicit_model_selection_mode() -> None:
    """T1: Design prompt が Model Router／固定モデルの選択方式を明示させる。"""
    text = _DESIGN_PROMPT.read_text(encoding="utf-8")
    assert "モデル選択方式" in text
    assert "model-router" in text
    assert "fixed" in text


def test_design_prompt_does_not_anchor_selection_to_gpt4o_example() -> None:
    """T1: モデル選定を旧モデルの例示にアンカーしない。"""
    text = _DESIGN_PROMPT.read_text(encoding="utf-8")
    assert "gpt-4o" not in text


def test_design_step_templates_require_project_and_model_selection_contract() -> None:
    """T1: AAD/ASDW 両入口が Project とモデル選定契約を明示する。"""
    for path in (_AAD_STEP_2_5, _STEP_2_1):
        text = path.read_text(encoding="utf-8")
        assert "Foundry Project" in text, path
        assert "モデル選択方式" in text, path


def test_deploy_prompt_requires_foundry_project_and_model_deployment() -> None:
    """T2a: Deploy prompt が Foundry の project 管理対応作成とモデルデプロイを必須化する。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "--allow-project-management" in text
    assert "az cognitiveservices account deployment create" in text


def test_deploy_prompt_requires_foundry_project_show_create_show_flow() -> None:
    """T2a: 存在確認と作成後確認の2回の show で Project を冪等作成する。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "az cognitiveservices account project show" in text
    assert "az cognitiveservices account project create" in text
    assert text.count("az cognitiveservices account project show") >= 2


def test_deploy_prompt_separates_project_and_model_reality_acs() -> None:
    """T2a: Project 実在とモデル実在を別 AC として扱う。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert re.search(r"\|\s*\*\*AC-13\*\*\s*\|[^|\n]*デプロイ済みモデル", text)
    assert re.search(r"\|\s*\*\*AC-14\*\*\s*\|[^|\n]*Foundry Project", text)


def test_deploy_step_template_requires_project_child_resource() -> None:
    """T2b: Step.2.2 template も Project create/show を省略させない。"""
    text = _STEP_2_2.read_text(encoding="utf-8")
    assert "az cognitiveservices account project show" in text
    assert "az cognitiveservices account project create" in text


def test_addservice_contract_does_not_use_legacy_az_ai_project_commands() -> None:
    """T2: 旧 `az ai project` コマンドを生成契約へ戻さない。"""
    for path in (_PROMPT, _STEP_2_2):
        text = path.read_text(encoding="utf-8")
        assert "az ai project" not in text, path


def test_deploy_prompt_requires_deployed_model_verify_tc() -> None:
    """T2a: Deploy prompt が verify スクリプトにデプロイ済みモデル検証 TC を要求する。

    `deployment list` でアカウントにデプロイ済みのモデルを検証する（リージョンで
    利用可能なモデル一覧とは別概念）。0 件 FAIL の意図を含む。
    """
    text = _PROMPT.read_text(encoding="utf-8")
    assert "az cognitiveservices account deployment list" in text
    assert "アカウントにデプロイ済みのモデル" in text


def test_deploy_prompt_has_ac13_for_deployed_model() -> None:
    """T2a: Deploy prompt の AC 表に AC-13（デプロイ済みモデル実在）が存在し、実在系として扱われる。

    AC-13 は AI/LLM 採用時は ✅ のみ許容（実在系）、AI/LLM 非該当時は N/A 行を残す
    （G3 で reality gate が AC-13 行の不在を記録漏れ扱いするため）。
    """
    text = _PROMPT.read_text(encoding="utf-8")
    assert "AC-13" in text
    # 実在系として AC-1 は ✅ のみ許容、AC-13 は AI/LLM 採用時 ✅ のみ・非該当時 N/A 行
    assert "AC-1 は `✅` のみ許容" in text
    assert "AC-13 は AI/LLM 採用時は `✅` のみ許容" in text


def test_step_2_2_template_requires_foundry_model_deployment() -> None:
    """T2b: step-2.2 テンプレが AI/LLM のモデルデプロイ＋デプロイ済みモデル検証を明記する。"""
    text = _STEP_2_2.read_text(encoding="utf-8")
    assert "--allow-project-management" in text
    assert "デプロイ済みモデル 1 件以上" in text


def test_testcoding_prompt_prohibits_tautological_assertion() -> None:
    """T3: TestCoding prompt が恒真式アサーション（count>=0 等）を禁止する。"""
    text = _TESTCODING_PROMPT.read_text(encoding="utf-8")
    assert "恒真式アサーション禁止" in text


def test_testcoding_prompt_requires_deployed_model_check() -> None:
    """T3: TestCoding prompt が Foundry のデプロイ済みモデル検証（GetCognitiveServicesAccountDeployments）を要求する。"""
    text = _TESTCODING_PROMPT.read_text(encoding="utf-8")
    assert "GetCognitiveServicesAccountDeployments" in text


def test_testcoding_prompt_requires_foundry_project_child_resource_check() -> None:
    """T3: account の存在ではなく Project 子リソースの実在を検証する。"""
    text = _TESTCODING_PROMPT.read_text(encoding="utf-8")
    assert "Microsoft.CognitiveServices/accounts/projects" in text
    assert "Foundry Project 子リソース" in text


def test_step_2_3_template_requires_foundry_project_check() -> None:
    """T3: Step.2.3 template が Project 実在テストを明示する。"""
    text = _STEP_2_3.read_text(encoding="utf-8")
    assert "Foundry Project 子リソース" in text


def test_step_2_3_template_expects_genuine_red_before_deploy() -> None:
    """P13: Step.2.3 は Deploy 前に実行され、リソース未作成の FAIL を正常な RED として扱う。"""
    text = _STEP_2_3.read_text(encoding="utf-8")
    assert "リソース未作成による FAIL は正常な RED" in text
    assert "Step.2.1（追加 Azure サービス選定）が `asdw-web:done` であること" in text
    assert "別タスク" not in text
    assert "Step.2.2（追加 Azure サービス Deploy）が `asdw-web:done` であること" not in text


def test_addservice_testcoding_docs_do_not_depend_on_prior_deploy() -> None:
    """P13: Step.2.3 の Prompt / template が Deploy 済みリソースを前提にしない。"""
    for path in (_TESTCODING_PROMPT, _STEP_2_3):
        text = path.read_text(encoding="utf-8")
        assert "Step.2.2" in text, path
        assert "より前" in text, path
        assert "Step.2.2 成果物" in text or "Step.2.2 成果物を入力にしない" in text, path
    prompt_text = _TESTCODING_PROMPT.read_text(encoding="utf-8")
    assert "`created-resources.json` 等の Step.2.2 成果物や live リソース照会結果を入力にしない" in prompt_text


def test_compute_design_docs_use_planned_design_not_live_catalog() -> None:
    """P13: Step.3.1 の Prompt / template が live service catalog を入力にしない。"""
    for path in (_COMPUTE_DESIGN_PROMPT, _STEP_3_1):
        text = path.read_text(encoding="utf-8")
        assert "docs/azure/azure-services-data.md" in text, path
        assert "planned design" in text, path
        assert "- `docs/azure/service-catalog.md`" not in text, path


def test_testing_prompt_classifies_foundry_model_not_deployed() -> None:
    """T4: Testing prompt の失敗分類が Foundry モデル未デプロイを Step.2.2 責務として扱う。"""
    text = _TESTING_PROMPT.read_text(encoding="utf-8")
    assert "az cognitiveservices account deployment list" in text
    assert "モデルデプロイ＝ Step.2.2" in text


def test_testing_prompt_classifies_foundry_project_not_created() -> None:
    """T4: Project 未作成を Step.2.2 の責務として即時中断する。"""
    text = _TESTING_PROMPT.read_text(encoding="utf-8")
    assert "az cognitiveservices account project show" in text
    assert re.search(r"Project 作成＝ Step\.2\.2[^\n]*asdw-web:blocked", text)


def test_step_2_4_template_visualizes_missing_foundry_project() -> None:
    """T4: Step.2.4 template が Project 未作成の RED を可視化する。"""
    text = _STEP_2_4.read_text(encoding="utf-8")
    assert "az cognitiveservices account project show" in text
    assert re.search(r"Project 作成＝ Step\.2\.2[^\n]*RED", text)


def test_step_2_4_template_visualizes_red_and_removes_stub_note() -> None:
    """T4: step-2.4 が Foundry モデル未デプロイ時の RED 可視化を明記し「別タスク」注記を除去している。"""
    text = _STEP_2_4.read_text(encoding="utf-8")
    assert "RED を可視化" in text
    assert "別タスク" not in text


# --- サービス作成の並列実行契約（Step.2.2 create.sh） ---


def test_deploy_prompt_requires_parallel_service_creation() -> None:
    """T5: Deploy prompt が create.sh 内のサービス作成をバックグラウンドジョブで並列実行させる。

    「サービス別スクリプトを順に呼ぶ」という逐次実行の記述が復活しないことも合わせて確認する。
    """
    text = _PROMPT.read_text(encoding="utf-8")
    assert "並列実行" in text
    assert 'wait "$pid"' in text
    assert "サービス別スクリプトを順に呼ぶ" not in text


def test_deploy_prompt_requires_two_wave_network_boundary_ordering() -> None:
    """T5: Deploy prompt が「ネットワーク境界」カテゴリを Wave A 完了後の Wave B で実行させる。

    docs/azure/azure-services-additional.md に記載された Private Endpoint の
    他サービスリソースID参照という実在の依存関係への対応。
    """
    text = _PROMPT.read_text(encoding="utf-8")
    assert "Wave A" in text
    assert "Wave B" in text
    assert "ネットワーク境界" in text


def test_deploy_prompt_requires_created_resources_conflict_prevention() -> None:
    """T5: Deploy prompt が並列実行時の created-resources.json 書き込み衝突を防止する。

    各サービスが専用の断片ファイルに出力し、全 wave 完了後に結合する設計であること。
    """
    text = _PROMPT.read_text(encoding="utf-8")
    assert "created-resources.d" in text
    assert "書き込み衝突防止" in text


def test_deploy_prompt_parallel_execution_uses_bash_invocation() -> None:
    """T5: Deploy prompt が実行権限ビットに依存しない `bash` 経由のサービススクリプト起動を明記する。

    Windows 上で checkout した場合に実行ビットが失われるケースへの対応。
    文言完全一致による脆性を避けるため、構成要素（bash 起動・対象パス）を分けて検証する。
    """
    text = _PROMPT.read_text(encoding="utf-8")
    assert "bash" in text
    assert 'services/<service>.sh"' in text
    assert "実行権限ビット" in text


def test_step_2_2_template_points_to_parallel_execution_policy() -> None:
    """T5: step-2.2 テンプレが並列実行方針への参照を明記する（詳細は Deploy prompt 側に一本化）。"""
    text = _STEP_2_2.read_text(encoding="utf-8")
    assert "並列実行" in text
    assert "Wave A" in text
    assert "Wave B" in text

