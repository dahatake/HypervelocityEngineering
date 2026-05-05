"""workflow_registry.py — ワークフロー定義レジストリ

10 個のオーケストレーションワークフロー (AAS/AAD-WEB/ASDW-WEB/ABD/ABDV/AAG/AAGD/AKM/AQOD/ADOC) の
ステップ DAG 定義をデータとして保持する。

Step ID スコープ規則:
  - Step ID はワークフロー内でのみ一意性が保証される
  - ワークフロー横断での一意性は保証しない
  - 将来、複数ワークフローの DAG を結合して単一 DAGExecutor で実行する場合は
    Step ID にワークフロー接頭辞が必要になる

依存パターン:
  - 順次 (sequential)   : A → B (B の depends_on = ["A"])
  - 並列 fork           : A → B‖C (B.depends_on = ["A"], C.depends_on = ["A"])
  - AND join            : A AND B → C (C.depends_on = ["A", "B"])
  - スキップフォールバック: ステップが存在しない場合に次候補へ進む
    (StepDef.skip_fallback_deps で「スキップ時の代替依存先」を定義)
  - ブロック            : 前提ステップ未完了時に xxx:blocked ラベルを付与して停止
    (StepDef.block_unless で「このステップが完了していなければブロック」を定義)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass
class StepDef:
    """1 ステップの定義。"""

    id: str
    """ステップ識別子 (例: "1", "1.1", "7.3")。"""

    title: str
    """Issue タイトルに使われるステップ名 (日本語)。"""

    custom_agent: Optional[str]
    """Copilot アサイン時に使う Custom Agent 名。コンテナは None。"""

    depends_on: List[str] = field(default_factory=list)
    """AND 依存先ステップ ID のリスト。空リストはルートノード。"""

    body_template_path: Optional[str] = None
    """Issue body テンプレートファイルのパス (templates/ 相対)。None は未定義。"""

    is_container: bool = False
    """True の場合、このステップは Sub-Issue を束ねるコンテナ Issue。"""

    skip_fallback_deps: List[str] = field(default_factory=list)
    """スキップフォールバック用メタデータ。"""

    block_unless: List[str] = field(default_factory=list)
    """ブロックパターン用メタデータ。"""

    consumed_artifacts: Optional[List[str]] = None
    """HVE_REUSE_CONTEXT_FILTERING=true 時に reuse_context へ含める成果物キーのリスト。
    None = 後方互換（全成果物を含める）。空リスト = このステップは既存成果物を参照しない。
    キーは _detect_existing_artifacts() が返す dict のキーに対応する
    (例: "app_catalog", "service_specs", "doc_generated")。
    """

    output_paths: List[str] = field(default_factory=list)
    """このステップが生成する成果物ファイルパスのリスト (リポジトリルート相対)。
    空リストの場合は workflow_default へフォールバック。
    Self-Improve の target scope 解決および Wave 3 以降の入力チェックで利用される。
    """

    required_input_paths: List[str] = field(default_factory=list)
    """このステップが必須とする入力ファイルパスのリスト (リポジトリルート相対)。
    テンプレートの ## 入力 内の（必須）項目に対応。オプション入力は含まない。
    将来の事前チェック・Wave 1 品質ゲートでの利用を想定。
    """


@dataclass
class WorkflowDef:
    """1 ワークフローの定義 (ステップ DAG + ラベル + パラメータ)。"""

    id: str
    """ワークフロー識別子 (小文字): "aas", "aad", "asdw", "abd", "abdv", "akm", "aqod", "adoc"。"""

    name: str
    """人間可読な正式名称。"""

    label_prefix: str
    """GitHub ラベルのプレフィックス (例: "aas", "aad")。"""

    state_labels: Dict[str, str]
    """状態ラベル名のマッピング。"""

    params: List[str]
    """ワークフロー固有のパラメータ名リスト。"""

    steps: List[StepDef]
    """ステップ定義のリスト (DAG ノード)。"""

    _step_index: Dict[str, StepDef] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._step_index = {s.id: s for s in self.steps}
        self._validate()

    def _validate(self) -> None:
        """ステップ定義の整合性を検証する (重複 ID のみ)。"""
        seen_ids: set = set()
        for s in self.steps:
            if s.id in seen_ids:
                raise ValueError(
                    f"Workflow '{self.id}': duplicate step id '{s.id}'"
                )
            seen_ids.add(s.id)

    def get_step(self, step_id: str) -> Optional[StepDef]:
        """ステップ ID からステップ定義を取得する。存在しない場合は None。"""
        return self._step_index.get(step_id)

    def get_root_steps(self) -> List[StepDef]:
        """ルートノード (依存先なし、かつ非コンテナ) のステップ一覧を返す。"""
        return [s for s in self.steps if not s.depends_on and not s.is_container]

    def get_next_steps(
        self,
        completed_step_ids: List[str],
        skipped_step_ids: Optional[List[str]] = None,
    ) -> List[StepDef]:
        """完了済みステップ ID のセットを受け取り、次に起動可能なステップを返す。

        「起動可能」とは:
          1. まだ完了していない
          2. スキップされていない
          3. 非コンテナ
          4. 依存するステップがすべて「解決済み」(AND 結合)

        依存解決ルール:
          - dep が completed に含まれる → 解決済み
          - dep が skipped に含まれる → 解決済み
          - dep がレジストリに存在しない → 解決済み (自動スキップ)
        """
        completed = set(completed_step_ids)
        skipped = set(skipped_step_ids or [])
        effective_done = completed | skipped
        existing_ids = set(self._step_index.keys())

        result: List[StepDef] = []
        for step in self.steps:
            if step.is_container:
                continue
            if step.id in completed or step.id in skipped:
                continue

            if not step.depends_on:
                result.append(step)
            else:
                deps_satisfied = all(
                    dep in effective_done or dep not in existing_ids
                    for dep in step.depends_on
                )
                if deps_satisfied:
                    result.append(step)

        return result


@dataclass
class WorkflowDependency:
    """ワークフロー間の依存定義。

    required_artifacts の glob 解決/検証は本モジュールでは行わず、
    利用側（依存チェック実装側）で評価する前提。
    """

    workflow_id: str
    """依存先ワークフロー ID。"""

    required_artifacts: List[str] = field(default_factory=list)
    """依存先が生成すべき成果物パス (glob パターン可)。"""

    soft: bool = False
    """True の場合、依存先未完了でも警告のみで続行可能。"""


@dataclass
class MetaWorkflowDef:
    """ワークフロー間の依存 DAG 定義。"""

    id: str
    """メタワークフロー識別子。"""

    workflows: List[str]
    """含まれるワークフロー ID のリスト。"""

    dependencies: Dict[str, List[WorkflowDependency]]
    """workflow_id → [依存先] のマッピング。"""


# ---------------------------------------------------------------------------
# ラベル定義ヘルパー
# ---------------------------------------------------------------------------


def _make_state_labels(prefix: str) -> Dict[str, str]:
    """プレフィックスから標準状態ラベルセットを生成する。"""
    return {
        "initialized": f"{prefix}:initialized",
        "ready": f"{prefix}:ready",
        "running": f"{prefix}:running",
        "done": f"{prefix}:done",
        "blocked": f"{prefix}:blocked",
    }


# ---------------------------------------------------------------------------
# ワークフロー定義
# ---------------------------------------------------------------------------

# --- AAS: App Architecture Design ---
AAS = WorkflowDef(
    id="aas",
    name="Architecture Design",
    label_prefix="aas",
    state_labels=_make_state_labels("aas"),
    params=[],
    steps=[
        StepDef(id="1", title="アプリケーションリストの作成",
                custom_agent="Arch-ApplicationAnalytics",
                consumed_artifacts=["use_case_catalog"],
                body_template_path="templates/aas/step-1.md",
                output_paths=["docs/catalog/app-catalog.md"],
                required_input_paths=["docs/catalog/use-case-catalog.md"]),
        StepDef(id="2", title="ソフトウェアアーキテクチャの推薦",
                custom_agent="Arch-ArchitectureCandidateAnalyzer",
                depends_on=["1"],
                # docs/architectural-requirements-app-xx.md は既知 key なし → app_catalog のみ
                consumed_artifacts=["app_catalog"],
                body_template_path="templates/aas/step-2.md",
                output_paths=["docs/catalog/app-arch-catalog.md"],
                required_input_paths=["docs/catalog/app-catalog.md"]),
        StepDef(id="3.1", title="ドメイン分析",
                custom_agent="Arch-Microservice-DomainAnalytics",
                depends_on=["2"],
                consumed_artifacts=["use_case_catalog", "app_catalog"],
                body_template_path="templates/aas/step-3.1.md",
                output_paths=["docs/catalog/domain-analytics.md"],
                required_input_paths=["docs/catalog/use-case-catalog.md",
                                      "docs/catalog/app-catalog.md"]),
        StepDef(id="3.2", title="サービス一覧抽出",
                custom_agent="Arch-Microservice-ServiceIdentify",
                depends_on=["3.1"],
                consumed_artifacts=["use_case_catalog", "domain_analytics", "app_catalog"],
                body_template_path="templates/aas/step-3.2.md",
                output_paths=["docs/catalog/service-catalog.md"],
                required_input_paths=["docs/catalog/use-case-catalog.md",
                                      "docs/catalog/domain-analytics.md",
                                      "docs/catalog/app-catalog.md"]),
        StepDef(id="4", title="データモデル",
                custom_agent="Arch-DataModeling",
                depends_on=["3.2"],
                consumed_artifacts=["domain_analytics", "service_catalog", "app_catalog"],
                body_template_path="templates/aas/step-4.md",
                output_paths=["docs/catalog/data-model.md",
                              "src/data/sample-data.json"],
                required_input_paths=["docs/catalog/domain-analytics.md",
                                      "docs/catalog/service-catalog.md",
                                      "docs/catalog/app-catalog.md"]),
        StepDef(id="5", title="データカタログ作成",
                custom_agent="Arch-DataCatalog",
                depends_on=["4"],
                skip_fallback_deps=["4"],
                # service_catalog / service_catalog_matrix は optional 入力のため除外
                consumed_artifacts=["data_model", "domain_analytics", "app_catalog"],
                body_template_path="templates/aas/step-5.md",
                output_paths=["docs/catalog/data-catalog.md"],
                required_input_paths=["docs/catalog/data-model.md",
                                      "docs/catalog/domain-analytics.md"]),
        StepDef(id="6", title="サービスカタログ",
                custom_agent="Arch-Microservice-ServiceCatalog",
                depends_on=["5"],
                skip_fallback_deps=["5"],
                consumed_artifacts=["service_catalog", "data_model", "screen_catalog", "domain_analytics", "app_catalog"],
                body_template_path="templates/aas/step-6.md",
                output_paths=["docs/catalog/service-catalog-matrix.md"],
                required_input_paths=["docs/catalog/service-catalog.md",
                                      "docs/catalog/data-model.md",
                                      "docs/catalog/screen-catalog.md",
                                      "docs/catalog/domain-analytics.md",
                                      "docs/catalog/app-catalog.md"]),
        StepDef(id="7", title="テスト戦略書",
                custom_agent="Arch-TDD-TestStrategy",
                depends_on=["6"],
                skip_fallback_deps=["6"],
                consumed_artifacts=["service_catalog_matrix", "data_model", "domain_analytics", "service_catalog", "app_catalog"],
                body_template_path="templates/aas/step-7.md",
                output_paths=["docs/catalog/test-strategy.md"],
                required_input_paths=["docs/catalog/service-catalog-matrix.md",
                                      "docs/catalog/data-model.md",
                                      "docs/catalog/domain-analytics.md",
                                      "docs/catalog/service-catalog.md",
                                      "docs/catalog/app-catalog.md"]),
    ],
)

# --- AAD-WEB: Web App Design ---
AAD_WEB = WorkflowDef(
    id="aad-web",
    name="Web App Design",
    label_prefix="aad-web",
    state_labels=_make_state_labels("aad-web"),
    params=["app_ids", "app_id"],
    steps=[
        StepDef(id="1", title="画面一覧と遷移図",
                custom_agent="Arch-UI-List",
                consumed_artifacts=["app_catalog", "service_catalog", "data_model", "domain_analytics"],
                body_template_path="templates/aad-web/step-1.md"),
        StepDef(id="2.1", title="画面定義書",
                custom_agent="Arch-UI-Detail",
                depends_on=["1"],
                consumed_artifacts=["screen_catalog", "app_catalog"],
                body_template_path="templates/aad-web/step-2.1.md"),
        StepDef(id="2.2", title="マイクロサービス定義書",
                custom_agent="Arch-Microservice-ServiceDetail",
                depends_on=["1"],
                consumed_artifacts=["app_catalog", "service_catalog", "data_model", "domain_analytics", "service_catalog_matrix"],
                body_template_path="templates/aad-web/step-2.2.md"),
        StepDef(id="2.3", title="TDDテスト仕様書",
                custom_agent="Arch-TDD-TestSpec",
                depends_on=["2.1", "2.2"],
                consumed_artifacts=["test_strategy", "screen_specs", "service_specs", "service_catalog_matrix", "data_model", "domain_analytics", "app_catalog"],
                body_template_path="templates/aad-web/step-2.3.md"),
    ],
)

# --- ASDW-WEB: Web App Dev & Deploy ---
ASDW_WEB = WorkflowDef(
    id="asdw-web",
    name="Web App Dev & Deploy",
    label_prefix="asdw-web",
    state_labels=_make_state_labels("asdw-web"),
    params=["app_ids", "app_id", "resource_group", "usecase_id", "tdd_max_retries"],
    steps=[
        # コンテナ
        StepDef(id="1", title="データ（コンテナ）", custom_agent=None, is_container=True),
        StepDef(id="2", title="マイクロサービス作成（コンテナ）", custom_agent=None, is_container=True),
        StepDef(id="3", title="UI 作成（コンテナ）", custom_agent=None, is_container=True),
        StepDef(id="4", title="アーキテクチャレビュー（コンテナ）", custom_agent=None, is_container=True),
        # 実ステップ
        StepDef(id="1.1", title="Azure データストア選定",
                custom_agent="Dev-Microservice-Azure-DataDesign",
                # docs/templates/agent-playbook.md は既知 key なし → スキップ
                consumed_artifacts=["data_model", "service_catalog", "domain_analytics", "app_catalog"],
                body_template_path="templates/asdw-web/step-1.1.md"),
        StepDef(id="1.2", title="Azure データサービス Deploy",
                custom_agent="Dev-Microservice-Azure-DataDeploy",
                depends_on=["1.1"],
                # docs/azure/azure-services-data.md は既知 key なし → スキップ
                # src/data/sample-data.json は src_files でカバー
                consumed_artifacts=["service_catalog_matrix", "app_catalog", "src_files"],
                body_template_path="templates/asdw-web/step-1.2.md"),
        StepDef(id="2.1", title="Azure コンピュート選定",
                custom_agent="Dev-Microservice-Azure-ComputeDesign",
                depends_on=["1.2"],
                consumed_artifacts=["service_catalog", "use_case_catalog", "data_model", "service_catalog_matrix", "app_catalog"],
                body_template_path="templates/asdw-web/step-2.1.md"),
        StepDef(id="2.2", title="追加 Azure サービス選定",
                custom_agent="Dev-Microservice-Azure-AddServiceDesign",
                depends_on=["2.1"],
                # docs/azure/azure-services-*.md は既知 key なし → スキップ
                consumed_artifacts=["use_case_catalog", "service_catalog", "service_specs", "app_catalog"],
                body_template_path="templates/asdw-web/step-2.2.md"),
        StepDef(id="2.3", title="追加 Azure サービス Deploy",
                custom_agent="Dev-Microservice-Azure-AddServiceDeploy",
                depends_on=["2.2"],
                skip_fallback_deps=["2.2"],
                # docs/azure/azure-services-additional.md は既知 key なし → app_catalog のみ
                consumed_artifacts=["app_catalog"],
                body_template_path="templates/asdw-web/step-2.3.md"),
        StepDef(id="2.3T", title="サービス テスト仕様書 (TDD RED)",
                custom_agent="Arch-TDD-TestSpec",
                depends_on=["2.3"],
                skip_fallback_deps=["2.3"],
                consumed_artifacts=["test_strategy", "service_catalog_matrix", "service_specs", "data_model", "domain_analytics", "app_catalog", "test_files"],
                body_template_path="templates/asdw-web/step-2.3T.md"),
        StepDef(id="2.3TC", title="サービス テストコード生成 (TDD RED)",
                custom_agent="Dev-Microservice-Azure-ServiceTestCoding",
                depends_on=["2.3T"],
                skip_fallback_deps=["2.3T"],
                consumed_artifacts=["test_specs", "service_specs", "service_catalog_matrix", "app_catalog"],
                body_template_path="templates/asdw-web/step-2.3TC.md"),
        StepDef(id="2.4", title="サービスコード実装 (TDD GREEN)",
                custom_agent="Dev-Microservice-Azure-ServiceCoding-AzureFunctions",
                depends_on=["2.3TC"],
                skip_fallback_deps=["2.3TC"],
                # docs/azure/azure-services-*.md は既知 key なし → スキップ
                consumed_artifacts=["service_specs", "service_catalog", "data_model", "service_catalog_matrix", "app_catalog", "test_files", "test_specs"],
                body_template_path="templates/asdw-web/step-2.4.md"),
        StepDef(id="2.5", title="Azure Compute Deploy",
                custom_agent="Dev-Microservice-Azure-ComputeDeploy-AzureFunctions",
                depends_on=["2.4"],
                consumed_artifacts=["service_catalog", "service_catalog_matrix", "app_catalog", "src_files"],
                body_template_path="templates/asdw-web/step-2.5.md"),
        StepDef(id="3.0T", title="UI テスト仕様書 (TDD RED)",
                custom_agent="Arch-TDD-TestSpec",
                depends_on=["2.5"],
                skip_fallback_deps=["2.5"],
                consumed_artifacts=["test_strategy", "service_catalog_matrix", "screen_specs", "data_model", "domain_analytics", "app_catalog"],
                body_template_path="templates/asdw-web/step-3.0T.md"),
        StepDef(id="3.0TC", title="UI テストコード生成 (TDD RED)",
                custom_agent="Dev-Microservice-Azure-UITestCoding",
                depends_on=["3.0T"],
                skip_fallback_deps=["3.0T"],
                consumed_artifacts=["test_specs", "screen_specs", "service_catalog_matrix", "app_catalog"],
                body_template_path="templates/asdw-web/step-3.0TC.md"),
        StepDef(id="3.1", title="UI 実装 (TDD GREEN)",
                custom_agent="Dev-Microservice-Azure-UICoding",
                depends_on=["3.0TC"],
                skip_fallback_deps=["3.0TC"],
                consumed_artifacts=["screen_specs", "screen_catalog", "service_catalog_matrix", "use_case_catalog", "app_catalog", "src_files", "test_files", "test_specs"],
                body_template_path="templates/asdw-web/step-3.1.md"),
        StepDef(id="3.2", title="Web アプリ Deploy (Azure SWA)",
                custom_agent="Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps",
                depends_on=["3.1"],
                consumed_artifacts=["app_catalog"],
                body_template_path="templates/asdw-web/step-3.2.md"),
        StepDef(id="4.1", title="WAF アーキテクチャレビュー",
                custom_agent="QA-AzureArchitectureReview",
                depends_on=["3.2"],
                # docs/azure/azure-services-*.md は既知 key なし → スキップ
                consumed_artifacts=["use_case_catalog", "service_catalog_matrix", "app_catalog"],
                body_template_path="templates/asdw-web/step-4.1.md"),
        StepDef(id="4.2", title="整合性チェック",
                custom_agent="QA-AzureDependencyReview",
                depends_on=["3.2"],
                # docs/azure/azure-services-*.md は既知 key なし、src/app/ src/api/ infra/ は src_files でカバー
                consumed_artifacts=["service_catalog_matrix", "app_catalog", "src_files"],
                body_template_path="templates/asdw-web/step-4.2.md"),
    ],
)

# --- ABD: Batch Design ---
ABD = WorkflowDef(
    id="abd",
    name="Batch Design",
    label_prefix="abd",
    state_labels=_make_state_labels("abd"),
    params=["app_ids", "app_id"],
    steps=[
        StepDef(id="1.1", title="バッチドメイン分析", custom_agent="Arch-Batch-DomainAnalytics", consumed_artifacts=["use_case_catalog"], body_template_path="templates/abd/step-1.1.md"),
        StepDef(id="1.2", title="データソース/デスティネーション分析", custom_agent="Arch-Batch-DataSourceAnalysis", consumed_artifacts=["use_case_catalog"], body_template_path="templates/abd/step-1.2.md"),
        # docs/batch/batch-data-source-analysis.md は既知 key なし → スキップ
        StepDef(id="2", title="バッチデータモデル", custom_agent="Arch-Batch-DataModel", depends_on=["1.1", "1.2"], consumed_artifacts=["batch_domain_analytics", "data_model"], body_template_path="templates/abd/step-2.md"),
        StepDef(id="3", title="ジョブ設計書", custom_agent="Arch-Batch-JobCatalog", depends_on=["2"], skip_fallback_deps=["2"], consumed_artifacts=["batch_domain_analytics", "batch_data_model"], body_template_path="templates/abd/step-3.md"),
        StepDef(id="4", title="サービスカタログ", custom_agent="Arch-Batch-ServiceCatalog", depends_on=["3"], skip_fallback_deps=["3"], consumed_artifacts=["batch_job_catalog", "batch_data_model", "batch_domain_analytics"], body_template_path="templates/abd/step-4.md"),
        StepDef(id="5", title="テスト戦略書", custom_agent="Arch-Batch-TestStrategy", depends_on=["4"], skip_fallback_deps=["4"], consumed_artifacts=["batch_service_catalog", "batch_data_model"], body_template_path="templates/abd/step-5.md"),
        StepDef(id="6.1", title="ジョブ詳細仕様書", custom_agent="Arch-Batch-JobSpec", depends_on=["5"], skip_fallback_deps=["4"], consumed_artifacts=["batch_service_catalog", "batch_job_catalog", "batch_data_model"], body_template_path="templates/abd/step-6.1.md"),
        StepDef(id="6.2", title="監視・運用設計書", custom_agent="Arch-Batch-MonitoringDesign", depends_on=["5"], skip_fallback_deps=["4"], consumed_artifacts=["batch_service_catalog", "batch_job_catalog"], body_template_path="templates/abd/step-6.2.md"),
        # docs/batch/batch-test-strategy.md, batch-monitoring-design.md は既知 key なし → スキップ
        StepDef(id="6.3", title="TDDテスト仕様書", custom_agent="Arch-Batch-TDD-TestSpec", depends_on=["6.1", "6.2"], consumed_artifacts=["batch_service_catalog", "batch_job_specs"], body_template_path="templates/abd/step-6.3.md"),
    ],
)

# --- ABDV: Batch Dev ---
ABDV = WorkflowDef(
    id="abdv",
    name="Batch Dev",
    label_prefix="abdv",
    state_labels=_make_state_labels("abdv"),
    params=["app_ids", "app_id", "resource_group", "batch_job_id", "tdd_max_retries"],
    steps=[
        # docs/batch/batch-data-source-analysis.md, batch-test-strategy.md は既知 key なし → スキップ
        StepDef(id="1.1", title="データサービス選定", custom_agent="Dev-Batch-DataServiceSelect", consumed_artifacts=["batch_domain_analytics", "batch_data_model", "batch_job_catalog", "batch_service_catalog"], body_template_path="templates/abdv/step-1.1.md"),
        # docs/azure/azure-services-data.md, batch-monitoring-design.md は既知 key なし → スキップ
        StepDef(id="1.2", title="Azure データリソース Deploy", custom_agent="Dev-Batch-DataDeploy", depends_on=["1.1"], consumed_artifacts=["batch_service_catalog"], body_template_path="templates/abdv/step-1.2.md"),
        # docs/batch/batch-test-strategy.md, batch-monitoring-design.md は既知 key なし → スキップ
        StepDef(id="2.1", title="TDD RED — テストコード作成", custom_agent="Dev-Batch-TestCoding", depends_on=["1.2"], consumed_artifacts=["test_specs", "batch_job_catalog", "batch_service_catalog", "batch_job_specs"], body_template_path="templates/abdv/step-2.1.md"),
        # docs/azure/azure-services-data.md, batch-test-strategy.md, batch-monitoring-design.md は既知 key なし → スキップ
        StepDef(id="2.2", title="TDD GREEN — バッチジョブ本実装", custom_agent="Dev-Batch-ServiceCoding", depends_on=["2.1"], consumed_artifacts=["test_files", "batch_job_specs", "batch_service_catalog"], body_template_path="templates/abdv/step-2.2.md"),
        # docs/azure/azure-services-data.md, batch-monitoring-design.md, azure-services-compute.md は既知 key なし → スキップ
        StepDef(id="3", title="Azure Functions/コンテナ Deploy", custom_agent="Dev-Batch-FunctionsDeploy", depends_on=["2.2"], consumed_artifacts=["src_files", "batch_service_catalog"], body_template_path="templates/abdv/step-3.md"),
        # docs/azure/azure-services-data.md, batch-monitoring-design.md, azure-services-compute.md は既知 key なし → スキップ
        StepDef(id="4.1", title="WAF レビュー", custom_agent="QA-AzureArchitectureReview", depends_on=["3"], consumed_artifacts=["batch_service_catalog"], body_template_path="templates/abdv/step-4.1.md"),
        StepDef(id="4.2", title="整合性チェック", custom_agent="QA-AzureDependencyReview", depends_on=["3"], consumed_artifacts=["batch_service_catalog"], body_template_path="templates/abdv/step-4.2.md"),
    ],
)

# --- AAG: AI Agent Design ---
AAG = WorkflowDef(
    id="aag",
    name="AI Agent Design",
    label_prefix="aag",
    state_labels=_make_state_labels("aag"),
    params=["app_ids", "app_id", "usecase_id"],
    steps=[
        StepDef(id="1", title="AI Agent アプリケーション定義",
                custom_agent="Arch-AIAgentDesign-Step1",
                # users-guide/08-ai-agent.md は既知 key なし → スキップ
                consumed_artifacts=["use_case_catalog", "service_catalog_matrix", "domain_analytics", "data_model", "service_catalog", "service_specs", "app_catalog"],
                body_template_path="templates/aag/step-1.md"),
        StepDef(id="2", title="AI Agent 粒度設計",
                custom_agent="Arch-AIAgentDesign-Step2",
                depends_on=["1"],
                # users-guide/08-ai-agent.md は既知 key なし → スキップ
                # agent-application-definition.md は docs/agent/ 配下 → agent_specs でカバー
                consumed_artifacts=["agent_specs", "service_catalog_matrix", "domain_analytics", "data_model", "app_catalog"],
                body_template_path="templates/aag/step-2.md"),
        StepDef(id="3", title="AI Agent 詳細設計",
                custom_agent="Arch-AIAgentDesign-Step3",
                depends_on=["2"],
                # users-guide/08-ai-agent.md は既知 key なし → スキップ
                consumed_artifacts=["agent_specs", "service_catalog_matrix", "service_specs", "app_catalog"],
                body_template_path="templates/aag/step-3.md"),
    ],
)

# --- AAGD: AI Agent Dev & Deploy ---
AAGD = WorkflowDef(
    id="aagd",
    name="AI Agent Dev & Deploy",
    label_prefix="aagd",
    state_labels=_make_state_labels("aagd"),
    params=["app_ids", "app_id", "resource_group", "usecase_id", "tdd_max_retries"],
    steps=[
        StepDef(id="1", title="AI Agent 構成設計",
                custom_agent="Arch-AIAgentDesign-Step1",
                # docs/azure/azure-services-data.md, azure-services-additional.md は既知 key なし → スキップ
                consumed_artifacts=["app_catalog", "service_catalog_matrix", "service_catalog", "data_model", "domain_analytics", "use_case_catalog", "service_specs"],
                body_template_path="templates/aagd/step-1.md"),
        StepDef(id="2.1", title="AI Agent テスト仕様書 (TDD RED)",
                custom_agent="Arch-TDD-TestSpec",
                depends_on=["1"],
                # docs/ai-agent-catalog.md は docs/agent/ 配下でないため agent_specs キーの対象外 → スキップ
                consumed_artifacts=["test_strategy", "agent_specs", "service_catalog_matrix", "data_model", "app_catalog"],
                body_template_path="templates/aagd/step-2.1.md"),
        StepDef(id="2.2", title="AI Agent テストコード生成 (TDD RED)",
                custom_agent="Dev-Microservice-Azure-AgentTestCoding",
                depends_on=["2.1"],
                consumed_artifacts=["test_specs", "agent_specs", "service_catalog_matrix", "app_catalog"],
                body_template_path="templates/aagd/step-2.2.md"),
        StepDef(id="2.3", title="AI Agent 実装 (TDD GREEN)",
                custom_agent="Dev-Microservice-Azure-AgentCoding",
                depends_on=["2.2"],
                # docs/ai-agent-catalog.md は agent_specs 対象外 → スキップ
                # docs/azure/azure-services-additional.md は既知 key なし → スキップ
                consumed_artifacts=["agent_specs", "test_files", "test_specs", "service_catalog_matrix", "app_catalog"],
                body_template_path="templates/aagd/step-2.3.md"),
        StepDef(id="3", title="AI Agent Deploy",
                custom_agent="Dev-Microservice-Azure-AgentDeploy",
                depends_on=["2.3"],
                # docs/ai-agent-catalog.md は agent_specs 対象外 → スキップ
                # docs/azure/azure-services-additional.md は既知 key なし → スキップ
                consumed_artifacts=["src_files", "app_catalog"],
                body_template_path="templates/aagd/step-3.md"),
    ],
)

# --- AKM: Knowledge Management ---
AKM = WorkflowDef(
    id="akm",
    name="Knowledge Management",
    label_prefix="akm",
    state_labels=_make_state_labels("akm"),
    params=["sources", "target_files", "force_refresh", "custom_source_dir", "enable_auto_merge"],
    steps=[
        StepDef(
            id="1",
            title="knowledge/ ドキュメント生成・管理",
            custom_agent="KnowledgeManager",
            depends_on=[],
            # qa/, original-docs/, template/, .github/skills/ は既知 key なし → 成果物参照なし
            consumed_artifacts=[],
            body_template_path="templates/akm/step-1.md",
        ),
    ],
)

# --- AQOD: Original Docs Review ---
AQOD = WorkflowDef(
    id="aqod",
    name="Original Docs Review",
    label_prefix="aqod",
    state_labels=_make_state_labels("aqod"),
    params=["target_scope", "depth", "focus_areas"],
    steps=[
        StepDef(
            id="1",
            title="original-docs 質問票生成",
            custom_agent="QA-DocConsistency",
            depends_on=[],
            # original-docs/ は既知 key なし; knowledge/D07-* は knowledge キーでカバー
            consumed_artifacts=["knowledge"],
            body_template_path="templates/aqod/step-1.md",
        ),
    ],
)

# --- ADOC: Source Codeからのドキュメント作成 ---
ADOC = WorkflowDef(
    id="adoc",
    name="Source Codeからのドキュメント作成",
    label_prefix="adoc",
    state_labels=_make_state_labels("adoc"),
    params=["target_dirs", "exclude_patterns", "doc_purpose", "max_file_lines"],
    steps=[
        # コンテナ
        StepDef(id="2", title="ファイルサマリー（コンテナ）", custom_agent=None, is_container=True),
        StepDef(id="3", title="コンポーネント分析（コンテナ）", custom_agent=None, is_container=True),
        StepDef(id="5", title="アーキテクチャ横断分析（コンテナ）", custom_agent=None, is_container=True),
        StepDef(id="6", title="目的特化ドキュメント（コンテナ）", custom_agent=None, is_container=True),
        # Step.1
        StepDef(id="1", title="ファイルインベントリ", custom_agent="Doc-FileInventory", depends_on=[], consumed_artifacts=[], body_template_path="templates/adoc/step-1.md"),
        # Step.2.x — 並列 fork
        StepDef(id="2.1", title="ファイルサマリー（プロダクションコード）", custom_agent="Doc-FileSummary", depends_on=["1"], consumed_artifacts=[], body_template_path="templates/adoc/step-2.1.md"),
        StepDef(id="2.2", title="ファイルサマリー（テストコード）", custom_agent="Doc-TestSummary", depends_on=["1"], consumed_artifacts=[], body_template_path="templates/adoc/step-2.2.md"),
        StepDef(id="2.3", title="ファイルサマリー（設定・IaC）", custom_agent="Doc-ConfigSummary", depends_on=["1"], consumed_artifacts=[], body_template_path="templates/adoc/step-2.3.md"),
        StepDef(id="2.4", title="ファイルサマリー（CI/CD）", custom_agent="Doc-CICDSummary", depends_on=["1"], consumed_artifacts=[], body_template_path="templates/adoc/step-2.4.md"),
        StepDef(id="2.5", title="ファイルサマリー（大規模ファイル分割）", custom_agent="Doc-LargeFileSummary", depends_on=["1"], consumed_artifacts=[], body_template_path="templates/adoc/step-2.5.md"),
        # Step.3.x — AND join + 並列 fork
        StepDef(id="3.1", title="コンポーネント設計書", custom_agent="Doc-ComponentDesign", depends_on=["2.1", "2.2", "2.3", "2.4", "2.5"], consumed_artifacts=[], skip_fallback_deps=["2.1"], body_template_path="templates/adoc/step-3.1.md"),
        StepDef(id="3.2", title="API 仕様書", custom_agent="Doc-APISpec", depends_on=["2.1", "2.2", "2.3", "2.4", "2.5"], consumed_artifacts=[], skip_fallback_deps=["2.1"], body_template_path="templates/adoc/step-3.2.md"),
        StepDef(id="3.3", title="データモデル定義書", custom_agent="Doc-DataModel", depends_on=["2.1", "2.2", "2.3", "2.4", "2.5"], consumed_artifacts=[], skip_fallback_deps=["2.1"], body_template_path="templates/adoc/step-3.3.md"),
        StepDef(id="3.4", title="テスト仕様サマリー", custom_agent="Doc-TestSpecSummary", depends_on=["2.2"], consumed_artifacts=[], body_template_path="templates/adoc/step-3.4.md"),
        StepDef(id="3.5", title="技術的負債一覧", custom_agent="Doc-TechDebt", depends_on=["2.1", "2.2", "2.3", "2.4", "2.5"], consumed_artifacts=[], skip_fallback_deps=["2.1"], body_template_path="templates/adoc/step-3.5.md"),
        # Step.4 — AND join
        StepDef(id="4", title="コンポーネントインデックス", custom_agent="Doc-ComponentIndex", depends_on=["3.1", "3.2", "3.3", "3.4", "3.5"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-4.md"),
        # Step.5.x — 並列 fork
        StepDef(id="5.1", title="アーキテクチャ概要", custom_agent="Doc-ArchOverview", depends_on=["4"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-5.1.md"),
        StepDef(id="5.2", title="依存関係マップ", custom_agent="Doc-DependencyMap", depends_on=["4"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-5.2.md"),
        StepDef(id="5.3", title="インフラ依存分析", custom_agent="Doc-InfraDeps", depends_on=["4"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-5.3.md"),
        StepDef(id="5.4", title="非機能要件現状分析", custom_agent="Doc-NFRAnalysis", depends_on=["4", "3.4", "3.5"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-5.4.md"),
        # Step.6.x — 並列 fork
        StepDef(id="6.1", title="オンボーディングガイド", custom_agent="Doc-Onboarding", depends_on=["5.1", "5.2"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-6.1.md"),
        StepDef(id="6.2", title="リファクタリングガイド", custom_agent="Doc-Refactoring", depends_on=["5.2", "5.4", "3.5"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-6.2.md"),
        StepDef(id="6.3", title="移行アセスメント", custom_agent="Doc-Migration", depends_on=["5.1", "5.3", "5.4"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-6.3.md"),
    ],
)


FULL_PIPELINE = MetaWorkflowDef(
    id="full-pipeline",
    workflows=["aas", "aad-web", "asdw-web", "abd", "abdv", "aag", "aagd"],
    dependencies={
        "aas": [],
        "aad-web": [
            WorkflowDependency(
                workflow_id="aas",
                required_artifacts=[
                    "docs/catalog/app-catalog.md",
                    "docs/catalog/domain-analytics.md",
                    "docs/catalog/service-catalog.md",
                    "docs/catalog/data-model.md",
                    "docs/catalog/test-strategy.md",
                ],
            ),
        ],
        "asdw-web": [
            WorkflowDependency(
                workflow_id="aad-web",
                required_artifacts=[
                    "docs/screen/*.md",
                    "docs/services/*.md",
                    "docs/test-specs/*-test-spec.md",
                ],
            ),
        ],
        "abd": [
            WorkflowDependency(
                workflow_id="aas",
                required_artifacts=[
                    "docs/catalog/app-catalog.md",
                    "docs/catalog/domain-analytics.md",
                ],
                soft=True,
            ),
        ],
        "abdv": [
            WorkflowDependency(
                workflow_id="abd",
                required_artifacts=[
                    "docs/batch/batch-domain-analytics.md",
                    "docs/batch/batch-data-model.md",
                    "docs/batch/batch-job-catalog.md",
                    "docs/batch/batch-service-catalog.md",
                    "docs/batch/batch-test-strategy.md",
                    "docs/batch/jobs/*.md",
                    "docs/test-specs/*-test-spec.md",
                ],
            ),
        ],
        "aag": [
            WorkflowDependency(
                workflow_id="aas",
                required_artifacts=["docs/catalog/service-catalog.md"],
            ),
            WorkflowDependency(
                workflow_id="aad-web",
                required_artifacts=[
                    "docs/screen/*.md",
                    "docs/services/*.md",
                    "docs/test-specs/*-test-spec.md",
                ],
            ),
        ],
        "aagd": [
            WorkflowDependency(
                workflow_id="aag",
                required_artifacts=["docs/agent/*.md"],
            ),
            WorkflowDependency(
                workflow_id="asdw-web",
                required_artifacts=[],
                soft=True,
            ),
        ],
    },
)


# ---------------------------------------------------------------------------
# レジストリ
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, WorkflowDef] = {
    wf.id: wf for wf in [AAS, AAD_WEB, ASDW_WEB, ABD, ABDV, AAG, AAGD, AKM, AQOD, ADOC]
}

_META_REGISTRY: Dict[str, MetaWorkflowDef] = {
    mwf.id: mwf for mwf in [FULL_PIPELINE]
}

# Phase 9 棚卸し結果 (2026-04-30):
# - "aad"  → "aad-web"  : 維持。auto-orchestrator-dispatcher.yml の done_map / closed_prefix_map /
#                          qa_ready_labels で参照。.github/labels.json に存在するラベルは
#                          aad:qa-ready / aad-web:done。aad:done は labels.json には無いが、
#                          既存 Issue に付いている可能性があるため互換目的で維持。
# - "asdw" → "asdw-web" : 維持。auto-orchestrator-dispatcher.yml の done_map / closed_prefix_map /
#                          qa_ready_labels で参照。labels.json にある asdw:qa-ready は存在するが
#                          asdw:done は存在しない。旧 Issue 互換として維持。
# - "aad_web"  (snake_case): 削除。GitHub ラベルにはアンダースコアなし。
#                             .github/ 配下のどのワークフロー・スクリプトからも呼ばれないことを確認済み。
# - "asdw_web" (snake_case): 同上。削除。
_ALIASES: Dict[str, str] = {
    "aad": "aad-web",
    "asdw": "asdw-web",
}

# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def get_workflow(workflow_id: str) -> Optional[WorkflowDef]:
    """ワークフロー ID からワークフロー定義を取得する。存在しない場合は None。"""
    key = workflow_id.lower()
    resolved = _ALIASES.get(key, key)
    return _REGISTRY.get(resolved)


def get_meta_dependencies(workflow_id: str) -> List[WorkflowDependency]:
    """指定ワークフローのメタワークフロー依存を返す。

    _META_REGISTRY は小規模運用を前提とし、全走査で依存定義を解決する。
    """
    key = workflow_id.lower()
    resolved = _ALIASES.get(key, key)
    for mwf in _META_REGISTRY.values():
        if resolved in mwf.dependencies:
            return mwf.dependencies[resolved]
    return []


def get_step(workflow_id: str, step_id: str) -> Optional[StepDef]:
    """ワークフロー ID とステップ ID からステップ定義を取得する。"""
    wf = get_workflow(workflow_id)
    if wf is None:
        return None
    return wf.get_step(step_id)


def get_next_steps(
    workflow_id: str,
    completed_step_ids: List[str],
    skipped_step_ids: Optional[List[str]] = None,
) -> List[StepDef]:
    """完了済みステップから次に起動可能なステップのリストを返す。"""
    wf = get_workflow(workflow_id)
    if wf is None:
        return []
    return wf.get_next_steps(completed_step_ids, skipped_step_ids)


def get_root_steps(workflow_id: str) -> List[StepDef]:
    """ルートノード (依存先なし・非コンテナ) のステップ一覧を返す。"""
    wf = get_workflow(workflow_id)
    if wf is None:
        return []
    return wf.get_root_steps()


def list_workflows() -> List[WorkflowDef]:
    """登録済みワークフロー定義をすべて返す。"""
    return list(_REGISTRY.values())
