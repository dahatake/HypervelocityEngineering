"""汎用 TDD RED/GREEN リアリティ契約テスト（G1/G4）。

`tdd-red-green-reality` Skill の新設と、TDD 系 Agent prompt への結線が消えないことを
キーフレーズ部分一致で固定する（脆性低減のため文言完全一致は避ける）。プラットフォーム
非依存の RED/GREEN リアリティ原則（実出力で検証・恒真式禁止・platform 別 verify コマンド
確定）を、Azure 以外（AWS / GCP / Windows / iOS）も含めて維持するための回帰ガード。
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL = _REPO_ROOT / ".github" / "skills" / "testing" / "tdd-red-green-reality" / "SKILL.md"
_COMMON_PREAMBLE = _REPO_ROOT / ".github" / "skills" / "agent-common-preamble" / "SKILL.md"
_ROUTING = _REPO_ROOT / ".github" / "skills" / "_routing" / "README.md"
_PROMPTS_DIR = _REPO_ROOT / ".github" / "prompts"
_TDD_REPORT_PATH = "tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md"

# tdd-red-green-reality を結線した TDD 系 Agent prompt（TestCoding 6 + Testing 系 2）。
_WIRED_PROMPTS = [
    "Dev-Microservice-Azure-DataTestCoding.prompt.md",
    "Dev-Microservice-Azure-ServiceTestCoding.prompt.md",
    "Dev-Microservice-Azure-AgentTestCoding.prompt.md",
    "Dev-Microservice-Azure-UITestCoding.prompt.md",
    "Dev-Microservice-Azure-AddServiceTestCoding.prompt.md",
    "Dev-Dataflow-TestCoding.prompt.md",
    "Dev-Microservice-Azure-AddServiceTesting.prompt.md",
    "Dev-Microservice-Azure-ComputePostDeployTest.prompt.md",
]


def test_skill_file_exists() -> None:
    """汎用 skill ファイルが実在する。"""
    assert _SKILL.is_file()


def test_skill_prohibits_tautological_assertion() -> None:
    """skill が恒真式アサーション禁止の原則を含む。"""
    text = _SKILL.read_text(encoding="utf-8")
    assert "恒真式アサーション禁止" in text


def test_skill_covers_multiple_platforms() -> None:
    """skill が Azure 以外（AWS / GCP / iOS）の verify コマンド確定方針を含む。

    汎用化の核心: 実装先が Azure とは限らない（AWS / GCP / Windows / iOS）。
    """
    text = _SKILL.read_text(encoding="utf-8")
    for token in ["Microsoft Learn MCP", "aws ", "gcloud ", "xcodebuild"]:
        assert token in text, f"skill に {token!r} の verify 指針が無い"


def test_azure_microsoft_learn_mcp_rule_is_common_and_strict() -> None:
    """Azure 公式情報は共通 preamble と TDD reality skill の両方で Microsoft Learn MCP を必須化する。"""
    for path in (_COMMON_PREAMBLE, _SKILL):
        text = path.read_text(encoding="utf-8")
        assert "Microsoft Learn MCP" in text, f"{path.name} に Microsoft Learn MCP 参照規律が無い"
        assert "利用可能なら必ず参照" in text, f"{path.name} に利用可能時の必須参照規律が無い"
        assert "title / URL / 確認事項" in text, f"{path.name} に根拠記録形式が無い"
        assert "要確認（Microsoft Learn MCP 未取得）" in text, f"{path.name} に未取得時の留保表現が無い"
        assert "推測で確定しない" in text, f"{path.name} に推測確定禁止が無い"


def test_common_preamble_retries_safe_microsoft_learn_redirect_once() -> None:
    """Learn Web fallbackは同一HTTPS hostの最終URLへ一度だけ再試行する。"""
    text = _COMMON_PREAMBLE.read_text(encoding="utf-8")
    section = text.split(
        "### Microsoft Learn Web redirect の単回再試行",
        1,
    )[1].split("\n## ", 1)[0]
    for phrase in (
        "Microsoft Learn MCP を優先",
        "`WebFetchRedirectError`",
        "最終 `Location`",
        "`Location` が `/en-us/...` のような相対URLなら",
        "元URLのorigin `https://learn.microsoft.com` と結合",
        "HTTPSかつ同一host `learn.microsoft.com`",
        "別host・HTTP・認証情報を含むURLは拒否",
        "一度だけ",
        "エラーが示した最終絶対URL",
        "元URLを再試行せず",
        "redirectを連鎖追跡せず",
        "同じ取得を反復しない",
        "単回再試行もredirect / 404 / permission error / その他の失敗",
        "場合は停止し、別のMicrosoft公式ソースまたはMicrosoft Learn MCPへ切り替える",
        "要確認（Microsoft Learn MCP 未取得）",
        "推測で確定しない",
        "302例",
        "https://learn.microsoft.com/azure/cosmos-db/partitioning",
        "`/en-us/azure/cosmos-db/partitioning`",
        "https://learn.microsoft.com/en-us/azure/cosmos-db/partitioning",
        "さらにredirectなら追跡せず停止",
    ):
        assert phrase in section


def test_skill_distinguishes_available_from_deployed() -> None:
    """skill が「利用可能」と「実在（デプロイ済み）」の混同禁止を含む。"""
    text = _SKILL.read_text(encoding="utf-8")
    assert "利用可能" in text and "実在" in text


def test_skill_defines_standard_tdd_report_path() -> None:
    """skill が TDD RED/GREEN の標準レポート出力先を定義している。"""
    text = _SKILL.read_text(encoding="utf-8")
    assert _TDD_REPORT_PATH in text
    assert "TDD-Judgement" in text
    assert "Secret-Redaction" in text


def test_skill_referenced_in_routing() -> None:
    """skill が routing 表に登録されている（CI の routing 整合に必要）。"""
    text = _ROUTING.read_text(encoding="utf-8")
    assert "testing/tdd-red-green-reality/SKILL.md" in text


def test_tdd_agents_reference_skill() -> None:
    """TDD 系 Agent prompt が tdd-red-green-reality を Skills 依存に列挙している。"""
    for name in _WIRED_PROMPTS:
        text = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
        assert "tdd-red-green-reality" in text, f"{name} に skill 結線が無い"
