"""Generated test runtime environment contract tests.

These tests pin the Prompt/Skill contract that HVE-generated tests must be
runnable locally by default, while integration/post-deploy/E2E tests may use
configured external services via environment variables or test settings.
Prompt checks use keywords; migrated Skill policies bind values to their table
fields and conditional clauses rather than unrelated mentions elsewhere.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_DIR = _REPO_ROOT / ".github" / "skills"
_PROMPTS_DIR = _REPO_ROOT / ".github" / "prompts"
_TEMPLATES_DIR = _REPO_ROOT / ".github" / "prompts" / "steps"

_TDD_REALITY_SKILL = _SKILLS_DIR / "tdd-red-green-reality" / "SKILL.md"
_TDD_RUNTIME_REF = _SKILLS_DIR / "tdd-red-green-reality" / "references" / "generated-test-runtime.md"
_TDD_POLICY_REF = _SKILLS_DIR / "tdd-red-green-reality" / "references" / "generated-test-policy.md"
_VERIFICATION_COMMANDS = (
    _SKILLS_DIR
    / "harness-verification-loop"
    / "references"
    / "verification-commands.md"
)

_LOCAL_RUNTIME_PROMPTS = [
    "Dev-Microservice-Azure-DataTestCoding.prompt.md",
    "Dev-Microservice-Azure-ServiceTestCoding.prompt.md",
    "Dev-Microservice-Azure-ServiceCoding-AzureFunctions.prompt.md",
    "Dev-Microservice-Azure-UITestCoding.prompt.md",
    "Dev-Microservice-Azure-UICoding.prompt.md",
    "Dev-Microservice-Azure-AgentTestCoding.prompt.md",
    "Dev-Microservice-Azure-AgentCoding.prompt.md",
    "Dev-Dataflow-TestCoding.prompt.md",
    "Dev-Dataflow-ServiceCoding.prompt.md",
]

_EXTERNAL_RUNTIME_PROMPTS = [
    "Dev-Microservice-Azure-DataDeploy.prompt.md",
    "Dev-Microservice-Azure-AddServiceTestCoding.prompt.md",
    "Dev-Microservice-Azure-AddServiceTesting.prompt.md",
    "Dev-Microservice-Azure-ComputePostDeployTest.prompt.md",
    "E2ETesting-Playwright.prompt.md",
]

_LOCAL_RUNTIME_TEMPLATES = [
    _TEMPLATES_DIR / "asdw-web" / "step-1.2.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-3.2.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-3.3.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-4.1.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-4.2.prompt.md",
    _TEMPLATES_DIR / "adfdv" / "step-2.1.prompt.md",
    _TEMPLATES_DIR / "adfdv" / "step-2.2.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.2.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.3.prompt.md",
]

_EXTERNAL_RUNTIME_TEMPLATES = [
    _TEMPLATES_DIR / "asdw-web" / "step-1.3.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-2.3.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-2.4.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-3.5.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-4.4.prompt.md",
]

_AAGD_AGENT_DETAIL_CONSUMERS = [
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentTestCoding.prompt.md",
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentCoding.prompt.md",
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentDeploy.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.1.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.2.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.3.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-3.prompt.md",
]

_AAGD_TDD_RED_FILES = [
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentTestCoding.prompt.md",
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentCoding.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.2.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.3.prompt.md",
]

_AAGD_AGENT_KEY_FILES = [
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentTestCoding.prompt.md",
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentCoding.prompt.md",
    _PROMPTS_DIR / "Dev-Microservice-Azure-AgentDeploy.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.1.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.2.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.3.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-3.prompt.md",
]


def _policy_section(text: str, heading: str) -> str:
    matches = list(re.finditer(rf"(?m)^{re.escape(heading)}[ \t]*$", text))
    assert len(matches) == 1, f"retained TDD skill missing/duplicated section: {heading}"
    level = len(heading) - len(heading.lstrip("#"))
    body = text[matches[0].end():]
    return re.split(rf"(?m)^#{{1,{level}}} ", body, maxsplit=1)[0]


def _policy_table(
    text: str, headers: tuple[str, ...]
) -> dict[str, tuple[str, ...]]:
    """Bind each layer to its own fields, ignoring only Markdown presentation."""
    rows = [
        tuple(
            " ".join(cell.replace("**", "").replace("`", "").replace("–", "-").split())
            for cell in line.strip().strip("|").split("|")
        )
        if line.lstrip().startswith("|") else ()
        for line in text.splitlines()
    ]
    starts = [index for index, row in enumerate(rows) if row == headers]
    assert len(starts) == 1, f"retained TDD skill missing/duplicated policy table: {headers}"
    start = starts[0]
    assert start + 1 < len(rows), f"missing table separator: {headers}"
    separator = rows[start + 1]
    assert len(separator) == len(headers), f"invalid table separator: {headers}"
    for cell in separator:
        assert re.fullmatch(r":?-{3,}:?", cell), f"invalid table separator: {cell}"
    result: dict[str, tuple[str, ...]] = {}
    for row in rows[start + 2:]:
        if not row:
            break
        assert len(row) == len(headers), f"wrong policy field count: {row[0]}"
        assert row[0] not in result, f"duplicated policy row: {row[0]}"
        result[row[0]] = row[1:]
    assert result, f"empty policy table: {headers}"
    return result


def test_tdd_reality_skill_defines_runtime_environment_contract() -> None:
    text = _TDD_REALITY_SKILL.read_text(encoding="utf-8")
    runtime = _TDD_RUNTIME_REF.read_text(encoding="utf-8")
    for token in (
        "生成テストの実行環境契約",
        "references/generated-test-runtime.md",
    ):
        assert token in text
    for token in (
        "ローカル実行可能",
        "外部サービス",
        "環境変数",
        "デプロイ先",
        "fake GREEN",
        "秘密情報",
    ):
        assert token in runtime


def test_tdd_reality_preserves_runtime_environment_policy() -> None:
    """FR-CLI-73 / V02: migrate both former strategy runtime checks to §1.6."""
    text = _TDD_RUNTIME_REF.read_text(encoding="utf-8")
    runtime = _policy_section(text, "## 1.6) 生成テストの実行環境契約")
    assert "実行環境の分類" in runtime, "§1.6 missing migrated runtime classification"
    rows = _policy_table(
        runtime, ("分類", "既定の実行場所", "外部サービス", "設定の渡し方")
    )
    expected_rows = {
        "Unit / Component": (
            "ローカル / CI",
            "Mock / Stub / Emulator / Testcontainers に置換",
            "テストプロジェクト内の fixture / test settings",
        ),
        "実装コード向け TDD RED / GREEN": (
            "ローカル / CI",
            "原則テストダブル化。実装コード側は本番設定を外部化",
            "dotnet test / pytest / npm test 等で決定的に実行",
        ),
        "Integration": (
            "ローカル / CI / デプロイ先",
            "構成済み外部サービスを利用可",
            "Endpoint / Resource 名 / 認証情報を環境変数またはテスト設定ファイルで注入",
        ),
        "Post-deploy / E2E": (
            "ローカル / CI / デプロイ先",
            "デプロイ済み URL / 実サービスを利用",
            "*_BASE_URL / E2E_BASE_URL 等の環境変数を優先",
        ),
    }
    for classification, fields in expected_rows.items():
        assert rows.get(classification) == fields, f"runtime policy changed: {classification}"

    policy = " ".join(runtime.replace("**", "").replace("`", "").split())
    for clause in (
        "単体テスト / 実装コード向け TDD RED / TDD GREEN はローカル実行可能を既定",
        "接続先・認証・base URL は環境変数またはテスト設定ファイルから取得し、"
        "ローカル端末・CI・デプロイ先のいずれでも同じ設定キーで実行できるようにする",
        "外部サービス未設定を PASS 扱いしない",
        "未構成の外部サービスを成功扱いしない。"
        "必須の URL / Endpoint / Resource 名 / 認証経路が未設定の場合は、"
        "fake GREEN にせず Expected Outcome / Failure Analysis に環境ブロッカーとして記録する",
        "秘密情報をテストコード・README・ログへハードコードしない",
        "接続文字列、アカウントキー、SAS、Function Key、Bearer token は"
        "環境変数または実行環境の secret store から渡す",
        "ローカル専用の mock テストと、構成済み外部サービスを使う integration テストを混同しない。"
        "どちらのカテゴリかを README / tdd-test-report.md に明記する",
    ):
        assert clause in policy, f"§1.6 missing runtime condition: {clause}"


def test_tdd_reality_preserves_adopted_numeric_and_test_double_policy() -> None:
    """FR-CLI-73 / V02 / Q03: preserve adopted values, scopes and safety conditions."""
    text = _TDD_POLICY_REF.read_text(encoding="utf-8")
    pyramid = _policy_table(
        text, ("テスト層", "定義", "推奨比率", "実行タイミング", "特徴")
    )
    expected_pyramid = {
        "Unit Test": (
            "単一クラス/関数の振る舞いを検証。外部依存はすべてテストダブルに置換",
            "70-80%",
            "PR 時（必須）",
            "高速・安定・低コスト",
        ),
        "Integration Test": (
            "複数コンポーネントまたは外部依存（DB・キュー等）を含む結合を検証",
            "15-20%",
            "PR 時またはマージ時",
            "中速・環境依存あり",
        ),
        "E2E Test": (
            "ユーザー操作シナリオをエンドツーエンドで検証（UI → API → DB）",
            "5-10%",
            "マージ時または定期実行",
            "低速・高コスト・高信頼",
        ),
    }
    for layer, pyramid_fields in expected_pyramid.items():
        assert pyramid.get(layer) == pyramid_fields, f"adopted test pyramid policy changed: {layer}"

    coverage = _policy_table(text, ("テスト層", "カバレッジ目標", "対象", "除外対象"))
    expected_coverage = {
        "Unit Test（ビジネスロジック / 変換ロジック）": (
            "80% 以上（変換ロジックは 100% 目標）",
            "ドメインロジック・バリデーション・変換処理",
            "—",
        ),
        "Integration Test": (
            "主要パスの網羅", "DB アクセス・外部 API 呼び出し・メッセージング", "—",
        ),
        "E2E Test": ("クリティカルパスの網羅", "ユーザー操作シナリオ・画面遷移", "—"),
        "I/O 層（Extract / Load）": (
            "Integration Test で検証",
            "ファイル読み書き・DB 接続",
            "Unit Test のカバレッジ対象から除外",
        ),
    }
    for layer, fields in expected_coverage.items():
        assert coverage.get(layer) == fields, f"adopted coverage policy changed: {layer}"

    policy = text.replace("**", "").replace("`", "")
    priorities = re.findall(
        r"(?m)^[1-3]\. (?:エミュレーター（Azurite）|Testcontainers|Mock / Stub): [^\n]+$",
        policy,
    )
    assert priorities == [
        "1. エミュレーター（Azurite）: Azure Storage 依存の場合は最優先で採用",
        "2. Testcontainers: DB・外部サービスのコンテナ化が可能な場合に採用",
        "3. Mock / Stub: 上記が適用できない場合、または Unit Test レベルで十分な場合に採用",
    ], "test-double precedence or its applicability conditions changed"

    doubles = _policy_table(
        text, ("依存パターン", "テストダブル種別", "推奨ツール", "選択理由・使い分け基準")
    )
    expected_doubles = {
        "Azure Storage（Blob / Queue / Table）": (
            "エミュレーター",
            "Azurite",
            "ローカル開発・CI 環境で Azure Storage の振る舞いを忠実に再現",
        ),
        "Azure SQL Database": (
            "コンテナ",
            "Testcontainers",
            "実際の SQL Server インスタンスをコンテナで起動。スキーマ・トランザクション検証に最適",
        ),
        "Azure Cosmos DB": (
            "コンテナ",
            "Testcontainers（Cosmos DB エミュレーター）",
            "結果整合性・パーティションキー設計の検証に使用",
        ),
        "外部 HTTP API（REST）": (
            "Mock HTTP Server",
            "WireMock または言語標準のモックライブラリ",
            "外部 API の契約を再現。異常系（タイムアウト・5xx）のシミュレーションにも使用",
        ),
        "非同期メッセージング（Service Bus 等）": (
            "Mock / Stub",
            "言語標準のモックライブラリ",
            "発行側: メッセージ送信の検証。購読側: メッセージハンドラの単体テスト",
        ),
        "内部サービス間呼び出し": (
            "Mock / Stub",
            "言語標準のモックライブラリ",
            "サービス境界でモック化。Contract Test と併用",
        ),
    }
    for dependency, fields in expected_doubles.items():
        assert doubles.get(dependency) == fields, f"test-double selection policy changed: {dependency}"

    data = _policy_table(text, ("生成方式", "用途", "特徴", "適用場面"))
    expected_data = {
        "Faker（ランダム生成）": (
            "正常系・バリエーションテスト",
            "多様なデータを自動生成。実行ごとに異なるデータ",
            "Unit Test・探索的テスト",
        ),
        "シード管理（固定シード）": (
            "再現可能テスト",
            "Faker + 固定シードで再現性を確保",
            "CI での回帰テスト・デバッグ時",
        ),
        "本番データサニタイズ": (
            "大量データテスト・パフォーマンステスト",
            "本番データから PII を除去・マスキングして使用",
            "E2E テスト・負荷テスト",
        ),
    }
    for method, fields in expected_data.items():
        assert data.get(method) == fields, f"test-data safety policy changed: {method}"

    edge_cases = _policy_section(policy, "### エッジケース（必ず含める）")
    for clause in (
        "NULL / 空文字 / 空配列 / 境界値（最小値・最大値・桁あふれ）",
        "重複レコード / 文字化けデータ（マルチバイト・特殊文字）",
        "PII データのマスキング検証（PII を含むサービスの場合）",
    ):
        assert f"- {clause}" in edge_cases, f"required edge-case condition missing: {clause}"


def test_verification_commands_do_not_skip_missing_external_service_config() -> None:
    text = _VERIFICATION_COMMANDS.read_text(encoding="utf-8")
    assert "JavaScript / UI" in text
    assert "FAIL(環境ブロッカー)" in text
    assert "未実行のまま成功扱いしない" in text


def test_local_runtime_prompts_require_local_execution_contract() -> None:
    for name in _LOCAL_RUNTIME_PROMPTS:
        text = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
        assert "TDD テスト結果レポート" in text, f"{name} is not a TDD/runtime prompt"
        assert "ローカル" in text or "local" in text, f"{name} missing local runtime wording"
        assert "環境変数" in text, f"{name} missing environment variable wording"
        assert "秘密情報" in text, f"{name} missing secret handling wording"


def test_external_runtime_prompts_require_configured_service_contract() -> None:
    for name in _EXTERNAL_RUNTIME_PROMPTS:
        text = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
        assert "環境変数" in text, f"{name} missing environment variable wording"
        assert "秘密情報" in text, f"{name} missing secret handling wording"
        assert (
            "実環境" in text or "デプロイ済み" in text or "構成済み" in text or "E2E_BASE_URL" in text
        ), f"{name} missing configured external service wording"


def test_local_runtime_templates_require_local_execution_contract() -> None:
    for path in _LOCAL_RUNTIME_TEMPLATES:
        text = path.read_text(encoding="utf-8")
        assert "TDD-Judgement" in text or "TDD" in text, f"{path.relative_to(_REPO_ROOT)} is not TDD-related"
        assert "ローカル" in text or "local" in text, f"{path.relative_to(_REPO_ROOT)} missing local runtime wording"
        assert "環境変数" in text, f"{path.relative_to(_REPO_ROOT)} missing environment variable wording"
        assert "秘密情報" in text, f"{path.relative_to(_REPO_ROOT)} missing secret handling wording"


def test_external_runtime_templates_require_configured_service_contract() -> None:
    for path in _EXTERNAL_RUNTIME_TEMPLATES:
        text = path.read_text(encoding="utf-8")
        assert "環境変数" in text, f"{path.relative_to(_REPO_ROOT)} missing environment variable wording"
        assert "秘密情報" in text, f"{path.relative_to(_REPO_ROOT)} missing secret handling wording"
        assert (
            "実環境" in text or "デプロイ済み" in text or "構成済み" in text or "E2E_BASE_URL" in text
        ), f"{path.relative_to(_REPO_ROOT)} missing configured external service wording"


def test_aagd_agent_detail_consumers_use_canonical_key_path() -> None:
    assert _TEMPLATES_DIR / "aagd" / "step-2.3.prompt.md" in _AAGD_AGENT_DETAIL_CONSUMERS
    for path in _AAGD_AGENT_DETAIL_CONSUMERS:
        text = path.read_text(encoding="utf-8")
        assert "docs/agent/agent-detail-{key}.md" in text, (
            f"{path.relative_to(_REPO_ROOT)} missing canonical Agent detail path"
        )
        assert "docs/agent/agent-detail-{agentId}-*.md" not in text
        assert "docs/agent/agent-detail-{agentId}.md" not in text


def test_aagd_step_chain_preserves_test_spec_red_green_and_deploy_inputs() -> None:
    step21 = (_TEMPLATES_DIR / "aagd" / "step-2.1.prompt.md").read_text(encoding="utf-8")
    step22 = (_TEMPLATES_DIR / "aagd" / "step-2.2.prompt.md").read_text(encoding="utf-8")
    step23 = (_TEMPLATES_DIR / "aagd" / "step-2.3.prompt.md").read_text(encoding="utf-8")
    step3 = (_TEMPLATES_DIR / "aagd" / "step-3.prompt.md").read_text(encoding="utf-8")

    assert "docs/test-specs/{key}-test-spec.md" in step21
    assert "docs/test-specs/{key}-test-spec.md" in step22
    assert "src/test/agent/{key}.Tests/" in step22
    assert "src/test/agent/{key}.Tests/" in step23
    assert "未実装production behavior" in step22
    assert "TDD GREEN" in step23
    assert "src/agent/{key}/" in step23
    assert "src/agent/{key}/" in step3


def test_aagd_tdd_red_contract_does_not_require_every_test_to_fail() -> None:
    fail_all_pattern = re.compile(
        r"(?:全\s*テスト(?![^\n]*PASS)[^\n]*FAIL|"
        r"テスト(?:が|は)?\s*全て(?![^\n]*PASS)[^\n]*FAIL|"
        r"全\s*FAIL)",
        re.IGNORECASE,
    )
    for path in _AAGD_TDD_RED_FILES:
        text = path.read_text(encoding="utf-8")
        assert "未実装production behavior" in text, (
            f"{path.relative_to(_REPO_ROOT)} missing behavior-based RED contract"
        )
        assert "全テストが FAIL" not in text
        assert "全テスト FAIL" not in text
        assert "テストが全て FAIL" not in text
        assert not fail_all_pattern.search(text), path


def test_agent_coding_prompt_pins_capability_safety_boundaries() -> None:
    """Sub-15 の実装境界をPrompt契約として直接固定する。"""
    text = (_PROMPTS_DIR / "Dev-Microservice-Azure-AgentCoding.prompt.md").read_text(
        encoding="utf-8"
    )
    required_tokens = (
        "Section 7.0のPreferred / Fallbackに選択されたrouteだけを実装",
        "単一SELECT",
        "parameterization",
        "table/view/column allowlist",
        "INSERT / UPDATE / DELETE / MERGE / DDL / stored procedure",
        "Create / Update / Deleteは既存API契約に対応するREST Function Toolだけをprimary経路",
        "SQL/direct DB writeやMCP mutation迂回を禁止",
        "Agentは選択されたMCP Serverのclientとして接続",
        "Agent自身のRemote MCP Server化を既定で行わない",
        "有限のPLAN / ACT / OBSERVE / EVALUATE / REPLAN",
        "Section 7.4の恒久的な`Decision source`で承認されていないLocation",
        "`not-required`ではSkill、loader、hook、設定flagを作らない",
    )
    for token in required_tokens:
        assert token in text, f"AgentCoding capability contract missing: {token}"

    forbidden_tokens = (
        "Section 6: Knowledge Source",
        "D16で承認",
        "src/agent/{AgentID}-{AgentName}/",
        "src/test/agent/{AgentName}.Tests/",
        "docs/test-specs/{agentId}-test-spec.md",
    )
    for token in forbidden_tokens:
        assert token not in text, f"AgentCoding stale contract remains: {token}"


def test_aagd_capability_tests_use_selected_deterministic_test_doubles() -> None:
    """TestSpec→TestCodingが選択能力だけを外部接続なしで決定的に検証する。"""
    test_spec = (_TEMPLATES_DIR / "aagd" / "step-2.1.prompt.md").read_text(encoding="utf-8")
    test_coding = (
        _PROMPTS_DIR / "Dev-Microservice-Azure-AgentTestCoding.prompt.md"
    ).read_text(encoding="utf-8")
    assert "AG-CAP-01〜10" in test_spec
    assert "AG-CAP-01〜10" in test_coding
    for contract_id in ("AG-CAP-01 / 02", "AG-CAP-03", "AG-CAP-04", "AG-CAP-05", "AG-CAP-06"):
        assert contract_id in test_coding
    for token in (
        "Contract ID、入力、test double、期待結果、必要なevidence",
        "mock / stub / fake",
        "全providerのmockを先回り生成せず",
    ):
        assert token in test_spec
    for token in (
        "Preferred / Fallbackに選択されたproviderだけをmock/stub化",
        "全provider用fixture、依存、mockを先回り生成しない",
        "実接続しない",
        "呼出順・回数",
    ):
        assert token in test_coding


def test_aag_aagd_contract_files_forbid_stale_section6_knowledge_reference() -> None:
    """旧Section 6 Knowledge Source参照を能力契約chainへ再導入しない。"""
    files = [
        _PROMPTS_DIR / "Arch-AIAgentDesign-Step1.prompt.md",
        _PROMPTS_DIR / "Arch-AIAgentDesign-Step2.prompt.md",
        _PROMPTS_DIR / "Arch-AIAgentDesign-Step3.prompt.md",
        *_AAGD_AGENT_DETAIL_CONSUMERS,
    ]
    for path in files:
        assert "Section 6: Knowledge Source" not in path.read_text(encoding="utf-8"), path


def test_aagd_agent_specific_contracts_use_only_canonical_key() -> None:
    """fan-out後も残るAgent名placeholderをAAGD契約へ再導入しない。"""
    stale_tokens = (
        "{agentId}",
        "{agentName}",
        "{AgentID}",
        "{AgentName}",
        "agent-detail-*",
    )
    for path in _AAGD_AGENT_KEY_FILES:
        text = path.read_text(encoding="utf-8")
        for token in stale_tokens:
            assert token not in text, (
                f"{path.relative_to(_REPO_ROOT)} contains stale Agent placeholder: {token}"
            )
        assert "{key}" in text, f"{path.relative_to(_REPO_ROOT)} missing canonical key"

    deploy_prompt = (
        _PROMPTS_DIR / "Dev-Microservice-Azure-AgentDeploy.prompt.md"
    ).read_text(encoding="utf-8")
    deploy_template = (_TEMPLATES_DIR / "aagd" / "step-3.prompt.md").read_text(
        encoding="utf-8"
    )
    assert ".github/workflows/deploy-agent-{key}.yml" in deploy_prompt
    assert ".github/workflows/deploy-agent-{key}.yml" in deploy_template
