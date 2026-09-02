"""R02: 27 Agent の `## Agent 固有の Skills 依存` セクションを充足する。

各 Agent の責務に対応する Skill 依存を heading 直下に挿入する。
冪等: 既に bullets が入っている場合は skip。

Note: R02 タスク用のワンショットユーティリティ。マッピング表は Python 内に
埋め込んでいるが、将来は `tools/agent-skills-map.yaml` 等への分離を検討。
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / ".github" / "agents"
HEADING = "## Agent 固有の Skills 依存"

# 共通ブロック
DESIGN_BASE = [
    ("work-artifacts-layout", "`work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠"),
    ("input-file-validation", "必読ファイルの存在確認と欠損時の TBD 既定処理"),
    ("app-scope-resolution", "APP-ID 指定時の対象サービス・画面・エンティティのスコープ判定"),
    ("knowledge-lookup", "`knowledge/D01〜D21` の業務要件・ドメイン定義の参照"),
]

CODING_BASE = [
    ("work-artifacts-layout", "`work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠"),
    ("harness-verification-loop", "Build/Lint/Test/Security/Diff の 5 段階検証"),
    ("harness-error-recovery", "ビルド・テスト失敗時の E-01〜E-05 リカバリ"),
    ("harness-safety-guard", "ツール実行時の破壊的操作検出と中断"),
    ("karpathy-guidelines", "実装時の LLM 共通ミス防止指針"),
]

# Agent -> Skills 一覧（責務に応じて DESIGN_BASE / CODING_BASE に追加スキルを足す）
MAP: dict[str, list[tuple[str, str]]] = {
    # AI Agent 設計 (Step1/2/3)
    "Arch-AIAgentDesign-Step1": DESIGN_BASE + [
        ("task-questionnaire", "不明点の優先度付き質問票作成"),
    ],
    "Arch-AIAgentDesign-Step2": DESIGN_BASE + [
        ("task-questionnaire", "Agent 粒度・境界判断時の不明点確認"),
    ],
    "Arch-AIAgentDesign-Step3": DESIGN_BASE + [
        ("task-questionnaire", "詳細設計時の不明点確認"),
    ],
    # Dataflow 設計
    "Arch-Dataflow-DataModel": [
        ("dataflow-design-guide", "バッチ4層データモデル・冪等性キー・パーティション設計の手順"),
    ] + DESIGN_BASE,
    "Arch-Dataflow-DataSourceAnalysis": [
        ("dataflow-design-guide", "データソース/デスティネーション分析（スキーマ・変換・SLA）の手順"),
    ] + DESIGN_BASE,
    "Arch-Dataflow-DomainAnalytics": [
        ("dataflow-design-guide", "バッチ DDD 観点ドメイン分析（BC・冪等性・チェックポイント）の手順"),
    ] + DESIGN_BASE,
    "Arch-Dataflow-AppCatalog": [
        ("dataflow-design-guide", "ジョブ一覧・依存 DAG・スケジュール・リトライ設計の手順"),
    ] + DESIGN_BASE,
    "Arch-Dataflow-AppSpec": [
        ("dataflow-design-guide", "データフローアプリ詳細仕様（ジョブ単位）の作成手順"),
    ] + DESIGN_BASE,
    "Arch-Dataflow-MonitoringDesign": [
        ("dataflow-design-guide", "データフロー処理監視・運用設計の手順"),
    ] + DESIGN_BASE,
    "Arch-Dataflow-ServiceCatalog": [
        ("dataflow-design-guide", "データフローアプリサービスカタログ作成の手順"),
    ] + DESIGN_BASE,
    # Data
    "Arch-DataCatalog": DESIGN_BASE,
    "Arch-DataModeling": DESIGN_BASE,
    # Self-improve
    "Arch-ImprovementPlanner": [
        ("task-dag-planning", "改善タスクの DAG 分解・見積・分割判定"),
        ("work-artifacts-layout", "`work/` 配下に改善計画を出力"),
        ("task-questionnaire", "改善方針の不明点を優先度付き質問票として整理"),
        ("karpathy-guidelines", "計画策定時の LLM 共通ミス防止指針"),
    ],
    # Microservice 設計
    "Arch-Microservice-ServiceCatalog": [
        ("microservice-design-guide", "サービス定義・API 設計・境界コンテキスト対応の手順"),
    ] + DESIGN_BASE,
    "Arch-Microservice-ServiceDetail": [
        ("microservice-design-guide", "マイクロサービス詳細仕様テンプレートと API/イベント設計の手順"),
    ] + DESIGN_BASE,
    # UI 設計
    "Arch-UI-Detail": DESIGN_BASE,
    "Arch-UI-List": DESIGN_BASE,
    # Dataflow 実装
    "Dev-Dataflow-ServiceCoding": [
        ("dataflow-design-guide", "データフローアプリ実装時の設計指針（冪等性・チェックポイント）参照"),
    ] + CODING_BASE,
    "Dev-Dataflow-TestCoding": [
        ("dataflow-design-guide", "データフローテスト戦略（冪等性・データ品質・障害注入）の参照"),
    ] + CODING_BASE,
    # Azure 設計
    "Dev-Microservice-Azure-AddServiceDesign": [
        ("microservice-design-guide", "外部依存・統合サービス選定時の境界判断"),
    ] + DESIGN_BASE,
    "Dev-Microservice-Azure-ComputeDesign": [
        ("microservice-design-guide", "コンピュート選定時のサービス境界・非機能要件参照"),
    ] + DESIGN_BASE,
    "Dev-Microservice-Azure-DataDesign": [
        ("microservice-design-guide", "Polyglot Persistence のサービス境界・データ整合性参照"),
    ] + DESIGN_BASE,
    # Azure 実装（AI Agent Service / UI は microservice-design-guide を付けない）
    "Dev-Microservice-Azure-AgentCoding": CODING_BASE,
    "Dev-Microservice-Azure-AgentTestCoding": CODING_BASE,
    "Dev-Microservice-Azure-ServiceCoding-AzureFunctions": [
        ("microservice-design-guide", "サービス実装時の API/イベント契約参照"),
    ] + CODING_BASE,
    "Dev-Microservice-Azure-ServiceTestCoding": [
        ("microservice-design-guide", "サービステスト実装時の API/イベント契約参照"),
    ] + CODING_BASE,
    "Dev-Microservice-Azure-UICoding": CODING_BASE,
}


def format_bullets(skills: list[tuple[str, str]]) -> str:
    return "\n".join(f"- `{name}` — {desc}" for name, desc in skills)


def fill_file(agent_name: str, skills: list[tuple[str, str]]) -> str:
    path = AGENTS_DIR / f"{agent_name}.agent.md"
    content = path.read_text(encoding="utf-8")
    if HEADING not in content:
        return f"SKIP (no heading): {agent_name}"

    # Section: heading 行 〜 次の '## ' or '# ' まで
    idx = content.find(HEADING)
    end_h2 = content.find("\n## ", idx + len(HEADING))
    end_h1 = content.find("\n# ", idx + len(HEADING))
    candidates = [p for p in (end_h2, end_h1) if p >= 0]
    section_end = min(candidates) if candidates else len(content)
    section_body = content[idx + len(HEADING):section_end]
    # 既存 bullets があるか（空行除いて bullet 行が 1 行以上ある）
    has_bullets = any(
        line.strip().startswith(("-", "*", "1.")) for line in section_body.split("\n")
    )
    if has_bullets:
        return f"SKIP (already filled): {agent_name}"

    bullets = format_bullets(skills)
    new_section = f"{HEADING}\n\n{bullets}\n\n"
    # section_end+1: 次見出し直前の '\n' を 1 文字スキップ（EOF 時は空スライス）
    new_content = content[:idx] + new_section + content[section_end + 1:]
    # 旧 section_body は破棄され、bullets が挿入される
    path.write_text(new_content, encoding="utf-8")
    return f"OK: {agent_name} ({len(skills)} skills)"


def main() -> int:
    results = []
    for name, skills in MAP.items():
        results.append(fill_file(name, skills))
    for r in results:
        print(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
