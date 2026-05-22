"""hve.gui.business_requirement_template — `docs/business-requirement.md` の章構造定義。

`sample/business-requirement.md` の H2 見出しに基づく 7 章構成を定義する。
章単位 fan-out（並列実行）の単位として使用する。

設計判断:
- H2 単位（7 章並列）を採用。H3 を独立 LLM 呼び出しすると章内の論理的一貫性
  （例: 3.1 〜 3.5 の連動）が壊れる可能性があり、また Copilot SDK セッション
  数の同時並列を 7 に抑えることでレート制限/タイムアウトリスクを下げる。
- 出典: `sample/business-requirement.md` の H2 / H3 抽出結果（grep_search）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


BR_TEMPLATE_VERSION = "1.0"


@dataclass(frozen=True)
class BRSection:
    """`docs/business-requirement.md` の 1 章を表す。"""

    section_id: str  # "S1" .. "S7"
    heading: str  # H2 見出し（"## " を含まない本文のみ）
    subheadings: List[str]  # H3 見出しのリスト（"### " を含まない）
    description: str  # LLM プロンプトに渡すヒント


# `sample/business-requirement.md` の H2 構成（出典: 当該ファイルの grep_search 結果）
BR_SECTIONS: List[BRSection] = [
    BRSection(
        section_id="S1",
        heading="1. Executive Summary（要約）",
        subheadings=[],
        description=(
            "背景と目的、主な示唆（Key Insights）、推奨アクション概要を経営層向けに要約する。"
            "10行以内ではなく、根拠付きで詳細に記述してよい。"
        ),
    ),
    BRSection(
        section_id="S2",
        heading="2. Company Overview（企業概要）",
        subheadings=[],
        description=(
            "企業基本情報、事業領域と主要サービス、経営理念・ビジョンを整理する。"
            "添付資料に企業情報が無い場合は「資料上確認できる事実のみ」として記述。"
        ),
    ),
    BRSection(
        section_id="S3",
        heading="3. As-Is Analysis（現状分析）",
        subheadings=[
            "3.1 外部環境分析（PEST / 5 Forces）",
            "3.2 内部環境分析（リソース・ケイパビリティ）",
            "3.3 事業ポートフォリオ分析（BCGマトリクス等）",
            "3.4 競合分析（ベンチマーク）",
            "3.5 SWOT分析",
        ],
        description=(
            "外部環境（PEST / 5 Forces）、内部環境、事業ポートフォリオ、競合、SWOT を統合的に分析する。"
            "全サブ章を本章内で完結させること。"
        ),
    ),
    BRSection(
        section_id="S4",
        heading="4. To-Be Vision（あるべき姿）",
        subheadings=[
            "4.1 ビジョンと戦略的方向性",
            "4.2 戦略的課題と優先順位",
            "4.3 成長機会の特定",
        ],
        description=(
            "中長期的な目指す姿、戦略的方向性、戦略課題と優先順位、成長機会を整理する。"
        ),
    ),
    BRSection(
        section_id="S5",
        heading="5. Gap分析（As-IsとTo-Beの差分）",
        subheadings=[],
        description=(
            "As-Is と To-Be の差分を領域別（戦略・収益・組織・IT 等）に整理し、必要な打ち手を示す。"
        ),
    ),
    BRSection(
        section_id="S6",
        heading="6. Strategic Recommendations（戦略提言）",
        subheadings=[
            "推奨戦略と根拠",
            "実行ステップ（短期・中期・長期）",
            "KPIとモニタリング体制",
        ],
        description=(
            "推奨戦略・実行ステップ（短期/中期/長期）・KPI を、経営判断に使える具体性で記述する。"
        ),
    ),
    BRSection(
        section_id="S7",
        heading="7. Appendix（補足資料）",
        subheadings=[],
        description=(
            "使用データソース、分析上の制約、追加で確認すべき情報を列挙する。"
            "出典の無い記述は本章にも記載しない。"
        ),
    ),
]


def section_count() -> int:
    """章数を返す（テスト用）。"""
    return len(BR_SECTIONS)


def section_headings() -> List[str]:
    """H2 見出しのリストを返す。"""
    return [s.heading for s in BR_SECTIONS]
