"""workflow_registry.py — ワークフロー定義レジストリ

12 個のオーケストレーションワークフロー (ARD/AAS/AAD-WEB/ASDW-WEB/ADFD/ADFDV/AAG/AAGD/AAR/AKM/ADI/ADOC) の
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
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional


# ASDW-WEB Step 1.3 はこの 1 つの APP スコープに固定されている。
# リソース名の共通サフィックスもこの値から導出し、リテラルの二重管理を避ける。
ASDW_DATA_DEPLOY_SUPPORTED_APP_ID = "APP-009"


def asdw_data_deploy_resource_suffix() -> str:
    """`APP-009` のような APP-ID をリソース名用スラッグへ変換する。"""
    return ASDW_DATA_DEPLOY_SUPPORTED_APP_ID.replace("-", "").lower()


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

    output_paths_template: Optional[List[str]] = None
    """成果物パスのテンプレート宣言 (Sub-3 / Q3=b, FR-FANOUT-OUT-01)。

    io-contract (`.github/io-contracts/<Agent>--<workflow>--<stepId>.yaml`) の
    ``outputs`` と同じ表記で宣言する。fan-out ステップでは展開時に
    ``{key}`` および parser 別の ID 別名プレースホルダ
    （``{screenId}`` / ``{serviceId}`` / ``{appId}`` / ``{agentId}`` 等。
    ``fanout_expander._KEY_ALIAS_PLACEHOLDERS_BY_PARSER`` が SSOT）が
    fan-out キーへ置換され、合成 ``FanoutChildStep.output_paths`` に挿入される。

    例:
      ``output_paths_template=["docs/services/{serviceId}-spec.md"]``
      → fan-out キー ``SVC-billing`` で
         ``output_paths=["docs/services/SVC-billing-spec.md"]`` を生成。

    次のエントリは **確定ファイルパスへ解決できない** ため、fan-out 子の
    ``output_paths`` へは挿入されず、契約宣言としてのみ保持される
    （runner の output_paths ゲート FR-WF-OUT-01 を誤 fail させないための fail-closed 規則）:

      - キー別名プレースホルダを含まない（全 fan-out 子で同一パスになる）
      - 置換後もプレースホルダが残る（``{serviceNameSlug}`` 等、catalog parser から
        復元できない属性）
      - glob（``*`` / ``?``）を含む
      - ディレクトリ参照（末尾 ``/``）

    None の場合は ``output_paths`` をそのまま継承する (Sub-1 以前の挙動と等価)。
    fan-out 対象でない StepDef では展開が発生しないため、本フィールドは
    io-contract との契約整合のための宣言としてのみ機能する
    （``_check_output_paths_gate`` / ``collect_workflow_output_paths`` は
    ``output_paths`` のみを参照する）。
    """

    required_input_paths: List[str] = field(default_factory=list)
    """このステップが必須とする入力ファイルパスのリスト (リポジトリルート相対)。
    テンプレートの ## 入力 内の（必須）項目に対応。オプション入力は含まない。
    将来の事前チェック・Wave 1 品質ゲートでの利用を想定。
    """

    # --- Fan-out 拡張 (ADR-0002) ---------------------------------------
    fanout_static_keys: Optional[List[str]] = None
    """静的に既知の fan-out キー（例: AKM の ["D01", ..., "D21"]）。
    指定時、計画フェーズ（dag_planner）でこの StepDef は N 個のサブステップに展開される。
    展開後の step_id は ``{base_id}/{key}`` 形式（例 "1/D01"）。
    """

    fanout_parser: Optional[str] = None
    """動的解決パーサ名。catalog_parsers の登録済みキー
    ("app_catalog" / "screen_catalog" / "service_catalog"
     / "dataflow_catalog" / "agent_catalog")。
    指定時、依存元 step 完了後に dag_executor が動的展開する（F-2）。
    fanout_static_keys と同時指定された場合は静的優先。
    """

    additional_prompt_template_path: Optional[str] = None
    """fan-out キー別追加プロンプトのテンプレートパス。

    **パターン A（本リポジトリの標準規約）**: パスに ``{key}`` を含まず、1 ファイルを
    全キーで共有する。テンプレート本文内の ``{{key}}`` が実行時に fan-out キーへ置換される。
    例: ``hve/prompt/fanout/akm/_common.md``

    **パターン B（オプション）**: パス自体に ``{key}`` を含め、キーごとに異なるファイルを
    参照する。例: ``hve/prompt/fanout/akm/{key}.md``
    """

    per_key_mcp_servers: Optional[Dict[str, Dict[str, Any]]] = None
    """fan-out キーごとの MCP 上書き定義。例:
        {"D08": {"sql-mcp": {"url": "..."}}}
    指定キーは StepDef.fanout_*_keys に含まれている必要がある。
    """

    required_skills: List[str] = field(default_factory=list)
    """このステップの実行前に存在検証すべき Skill 名。

    例: ["knowledge-management"]
    空リストは「必須 skill 指定なし」を意味する。
    """

    requires_remote_cicd: bool = False
    """HVE Orchestrator が Step 単位の一時ブランチで remote CI/CD を行う対象か。

    Deploy 系 reality gate とは別概念。Azure リソース実在検証が必要な Step でも、
    GitHub Actions の `workflow_dispatch --ref <branch>` を必要としない Step は
    False のままとする。
    """

    reality_gate_acs: List[str] = field(default_factory=list)
    """Deploy 系 Agent の reality gate で「実在系」として GREEN を強制する AC-ID のリスト。

    `ac-verification.md` のテーブル行（`| AC-x | ... | 状態 | ... |`）を
    `hve/artifact_validation.validate_deploy_ac_verification` が解析し、ここで宣言した
    AC が `❌` / `⏳` / `NEEDS-VERIFICATION` のままなら Step を fail に降格する。
    空リストの場合は、後方互換のため `artifact_validation._DEPLOY_AGENT_REALITY_AC`
    （Agent 名ハードコード辞書）にフォールバックする。

    プラットフォーム非依存: ここで宣言する AC は「アカウント存在」だけでなく
    「実体がデプロイ済み」を実在で判定するもの（Skill `tdd-red-green-reality`）。
    Azure 以外（AWS / GCP / Windows / iOS 等）の Deploy 系 StepDef でも同様に宣言できる。
    """

    required_params: List[str] = field(default_factory=list)
    """この Step の実行に必要な Workflow パラメータ名のリスト（FR-DAG-07）。

    Workflow パラメータ契約の単一情報源。CLI wizard / CLI 非対話 / GUI の
    どの起動経路でも本宣言を参照し、DAG 実行前の pre-flight で検査する。
    空リストは「必須パラメータなし」を意味する。
    """

    default_params: Dict[str, str] = field(default_factory=dict)
    """`required_params` のうち、未指定時に適用する既定値（FR-DAG-07）。

    キーは `required_params` の部分集合でなければならない（`WorkflowDef._validate` が検証）。
    推測で既定値を作らないこと。環境固有値や承認が必要な値は既定値を持たず、
    pre-flight で利用者に入力を求める。
    """

    disabled_when_config: Dict[str, List[str]] = field(default_factory=dict)
    """設定値による Step 無効化条件。キー = `SDKConfig` の属性名、値 = 無効化する値のリスト。

    例: `{"enable_agentic_retrieval": ["no"]}` は `enable_agentic_retrieval` が `no` のとき
    当該 Step を実行対象から外す。無効化された Step は DAG 上で skip 扱いになり、
    依存先としては解決済みとみなされるため、下流 Step は到達不能にならない。

    空の場合は無条件に実行対象となる。
    """


@dataclass
class WorkflowDef:
    """1 ワークフローの定義 (ステップ DAG + ラベル + パラメータ)。"""

    id: str
    """ワークフロー識別子 (小文字): "aas", "aad-web", "asdw-web", "adfd", "adfdv", "akm", "adi", "adoc"。"""

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

    max_parallel: Optional[int] = None
    """このワークフロー実行時の最大並列数。None なら DAGExecutor の既定値 (15) を使う。
    例: AKM は D01〜D21 を 21 並列で起動するため 21 を指定する (ADR-0002 C-2)。
    """

    local_checkpoint_step_id: Optional[str] = None
    """local generation checkpoint となる Step ID。

    この Step とその推移的依存が local フェーズ（Azure live 操作なし）、
    残りが live フェーズ。live 失敗時に local 成果物を保持する判定に使う。
    None の workflow は phase 分割を行わない。
    """

    _step_index: Dict[str, StepDef] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._step_index = {s.id: s for s in self.steps}
        self._validate()

    def _validate(self) -> None:
        """ステップ定義の整合性を検証する (重複 ID / パラメータ契約)。"""
        seen_ids: set = set()
        for s in self.steps:
            if s.id in seen_ids:
                raise ValueError(
                    f"Workflow '{self.id}': duplicate step id '{s.id}'"
                )
            seen_ids.add(s.id)
            # FR-DAG-07: default_params のキーは required_params の部分集合であること。
            # 宣言されていないパラメータへ既定値を入れると pre-flight の検査対象外に
            # なり、誰も検証しない値が実行時まで残るため fail-closed で拒否する。
            # steps には fan-out 展開後の StepDef 互換オブジェクト（FanoutChildStep）も
            # 渡るため、属性の有無に依存しないよう getattr で参照する。
            required_params = getattr(s, "required_params", ()) or ()
            default_params = getattr(s, "default_params", {}) or {}
            undeclared = sorted(set(default_params) - set(required_params))
            if undeclared:
                raise ValueError(
                    f"Workflow '{self.id}' step '{s.id}': "
                    f"default_params key not in required_params: {undeclared[0]}"
                )
            for key, value in default_params.items():
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"Workflow '{self.id}' step '{s.id}': "
                        f"default_params['{key}'] must be a non-empty string"
                    )

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
                required_input_paths=["docs/catalog/app-catalog.md"],
                # ADR-0002 T4B: per-APP fan-out
                fanout_parser="app_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aas/_common.md"),
        StepDef(id="3.1", title="ドメイン分析",
                custom_agent="Arch-Microservice-DomainAnalytics",
                depends_on=["2"],
                consumed_artifacts=["use_case_catalog", "app_catalog"],
                body_template_path="templates/aas/step-3.1.md",
                output_paths=["docs/catalog/domain-analytics.md"],
                required_input_paths=["docs/catalog/app-arch-catalog.md", "docs/catalog/app-catalog.md", "docs/catalog/use-case-catalog.md"]),
        StepDef(id="3.2", title="サービス一覧抽出",
                custom_agent="Arch-Microservice-ServiceIdentify",
                depends_on=["3.1"],
                consumed_artifacts=["use_case_catalog", "domain_analytics", "app_catalog"],
                body_template_path="templates/aas/step-3.2.md",
                output_paths=["docs/catalog/service-catalog.md"],
                required_input_paths=["docs/catalog/use-case-catalog.md",
                                      "docs/catalog/domain-analytics.md",
                                      "docs/catalog/app-catalog.md"]),
        StepDef(id="4.1", title="データモデル設計",
                custom_agent="Arch-DataModeling",
                depends_on=["3.2"],
                consumed_artifacts=["domain_analytics", "service_catalog", "app_catalog"],
                body_template_path="templates/aas/step-4.1.md",
                output_paths=["docs/catalog/data-model.md"],
                required_input_paths=["docs/catalog/domain-analytics.md",
                                      "docs/catalog/service-catalog.md",
                                      "docs/catalog/app-catalog.md"]),
        StepDef(id="4.2", title="サンプルデータ生成",
                custom_agent="Arch-DataModeling",
                depends_on=["4.1"],
                consumed_artifacts=["data_model", "domain_analytics", "service_catalog", "app_catalog"],
                body_template_path="templates/aas/step-4.2.md",
                output_paths=["src/data/sample-data.json"],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/domain-analytics.md", "docs/catalog/service-catalog.md"]),
        StepDef(id="5", title="データカタログ作成",
                custom_agent="Arch-DataCatalog",
                depends_on=["4.1"],
                skip_fallback_deps=["4.1"],
                # service_catalog / service_catalog_matrix は optional 入力のため除外
                consumed_artifacts=["data_model", "domain_analytics", "app_catalog"],
                body_template_path="templates/aas/step-5.md",
                output_paths=["docs/catalog/data-catalog.md"],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/domain-analytics.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/service-catalog.md"]),
        StepDef(id="6", title="サービスカタログ",
                custom_agent="Arch-Microservice-ServiceCatalog",
                depends_on=["5"],
                skip_fallback_deps=["5"],
                consumed_artifacts=["service_catalog", "data_model", "screen_catalog", "domain_analytics", "app_catalog"],
                body_template_path="templates/aas/step-6.md",
                output_paths=["docs/catalog/service-catalog-matrix.md"],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/data-catalog.md", "docs/catalog/data-model.md", "docs/catalog/domain-analytics.md", "docs/catalog/service-catalog.md"]),
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
        # Step 8 — ペルソナカタログ（Use Case Catalog からアクター/ロールを抽出）
        # Q3=B 採用: docs/catalog/use-case-catalog.md を一次ソースとする
        StepDef(id="8", title="ペルソナカタログ",
                custom_agent="Arch-PersonaCatalog",
                depends_on=["7"],
                skip_fallback_deps=["7"],
                consumed_artifacts=["use_case_catalog", "app_catalog"],
                body_template_path="templates/aas/step-8.md",
                output_paths=["docs/catalog/persona-catalog.md"],
                required_input_paths=["docs/catalog/use-case-catalog.md",
                                      "docs/catalog/app-catalog.md"]),
        # Step 9 — ペルソナ別共通画面カタログ（Step 8 のペルソナ一覧を前提）
        StepDef(id="9", title="ペルソナ別共通画面カタログ",
                custom_agent="Arch-UI-PersonaScreenList",
                depends_on=["8"],
                skip_fallback_deps=["8"],
                consumed_artifacts=["persona_catalog", "app_catalog"],
                body_template_path="templates/aas/step-9.md",
                output_paths=["docs/catalog/persona-screen-catalog.md"],
                required_input_paths=["docs/catalog/persona-catalog.md",
                                      "docs/catalog/app-catalog.md"]),
    ],
)

# --- AAD-WEB: Web App Design ---
AAD_WEB = WorkflowDef(
    id="aad-web",
    name="Web App Design",
    label_prefix="aad-web",
    state_labels=_make_state_labels("aad-web"),
    params=["app_ids", "app_id", "create_remote_mcp_server"],
    steps=[
        StepDef(id="1", title="画面一覧と遷移図",
                custom_agent="Arch-UI-List",
                consumed_artifacts=["app_catalog", "service_catalog", "data_model", "domain_analytics"],
                body_template_path="templates/aad-web/step-1.md",
                # per-APP fan-out: 各 APP-NN ごとに `docs/catalog/screen-catalog-APP-NN.md` を生成。
                # 下流 Step 2.1 の screen_catalog parser (per-APP glob 入力) と契約整合する。
                fanout_parser="app_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aad-web/step-1-app.md",
                output_paths_template=["docs/catalog/screen-catalog-{key}.md"],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/domain-analytics.md", "docs/catalog/service-catalog.md"]),
        StepDef(id="2.1", title="画面定義書",
                custom_agent="Arch-UI-Detail",
                depends_on=["1"],
                consumed_artifacts=["screen_catalog", "app_catalog"],
                body_template_path="templates/aad-web/step-2.1.md",
                fanout_parser="screen_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aad-web/_common.md",
                # 根拠: templates/aad-web/step-2.1.md `## 出力` / Arch-UI-Detail.prompt.md
                # 「画面 ID + 画面名スラッグ」形式。``{screenNameSlug}`` は catalog parser から
                # 復元できないため fan-out 展開時に落ちる（実在しない path をゲートへ渡さない）。
                output_paths_template=["docs/screen/{screenId}-{screenNameSlug}-description.md"],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/domain-analytics.md", "docs/catalog/screen-catalog-{key}.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/service-catalog.md", "docs/catalog/test-strategy.md"]),
        StepDef(id="2.2", title="マイクロサービス定義書",
                custom_agent="Arch-Microservice-ServiceDetail",
                depends_on=["1"],
                consumed_artifacts=["app_catalog", "service_catalog", "data_model", "domain_analytics", "service_catalog_matrix"],
                body_template_path="templates/aad-web/step-2.2.md",
                fanout_parser="service_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aad-web/_common.md",
                # 根拠: templates/aad-web/step-2.2.md `## 出力`。``{serviceNameSlug}`` は
                # catalog parser から復元できないため fan-out 展開時に落ちる。
                output_paths_template=["docs/services/{serviceId}-{serviceNameSlug}-description.md"],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/domain-analytics.md", "docs/catalog/screen-catalog-APP-*.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/service-catalog.md", "docs/catalog/test-strategy.md"]),
        StepDef(id="2.3", title="サービス別 TDD テスト仕様書",
                custom_agent="Arch-TDD-TestSpec",
                depends_on=["2.2"],
                consumed_artifacts=["test_strategy", "service_specs", "service_catalog_matrix", "data_model", "domain_analytics", "app_catalog"],
                body_template_path="templates/aad-web/step-2.3.md",
                fanout_parser="service_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aad-web/_common.md",
                # ``{serviceId}`` は service_catalog parser の fan-out キー（``SVC-*``）そのもの。
                # Arch-TDD-TestSpec.prompt.md `<output_contract>` の「ファイル名 = parser キー」に従い、
                # 展開後は `docs/test-specs/SVC-01-test-spec.md` など実生成名と一致する。
                output_paths_template=["docs/test-specs/{serviceId}-test-spec.md"],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/domain-analytics.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/test-strategy.md", "docs/services/{serviceId}-{serviceNameSlug}-description.md"]),
        StepDef(id="2.4", title="画面別 TDD テスト仕様書",
                custom_agent="Arch-TDD-TestSpec",
                depends_on=["2.1"],
                consumed_artifacts=["test_strategy", "screen_specs", "service_catalog_matrix", "data_model", "domain_analytics", "app_catalog"],
                body_template_path="templates/aad-web/step-2.4.md",
                fanout_parser="screen_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aad-web/_common.md",
                # ``{screenId}`` は screen_catalog parser の fan-out キー（``APP-NN-S###``）そのもの。
                # 展開後は `docs/test-specs/APP-009-S001-test-spec.md` など実生成名と一致する。
                output_paths_template=["docs/test-specs/{screenId}-test-spec.md"],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/domain-analytics.md", "docs/catalog/screen-catalog-{key}.md", "docs/catalog/test-strategy.md", "docs/screen/{screenId}-{screenNameSlug}-description.md"]),
        # Step.2.5: AAD-Web 設計フェーズで追加 Azure サービス（AI/認証/統合/運用等）を選定する。
        # チャットボット/Prompt/AI Agent 要件は Microsoft Foundry を、RAG は Azure AI Search を強制（Prompt §3.1 参照）。
        # 出力先 `docs/azure/azure-services-additional.md` は ASDW-WEB Step.2.2 と同一パス。io-contract で `mode: append` を宣言している。
        StepDef(id="2.5", title="追加 Azure サービス選定",
                custom_agent="Dev-Microservice-Azure-AddServiceDesign",
                depends_on=["2.2"],
                consumed_artifacts=["use_case_catalog", "service_catalog", "service_specs", "app_catalog"],
                body_template_path="templates/aad-web/step-2.5.md",
                output_paths=["docs/azure/azure-services-additional.md"],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/service-catalog.md", "docs/catalog/use-case-catalog.md", "docs/services/{serviceId}-{serviceNameSlug}-description.md"]),
        # Step.2.6: 機能要件に Chat-Bot / AI Agent / RAG を含むサービスだけを対象に、
        # 製品非依存の Agentic Retrieval 機能要件詳細を作る（ADR-0001 Phase 5）。
        # Arch-Microservice-ServiceDetail.prompt.md §3.6 の委譲先。
        StepDef(id="2.6", title="Agentic Retrieval 機能要件詳細",
                custom_agent="Arch-AgenticRetrieval-Detail",
                depends_on=["2.2"],
                consumed_artifacts=["service_catalog", "service_specs", "domain_analytics", "app_catalog"],
                body_template_path="templates/aad-web/step-2.6.md",
                # サービス単位の成果物しか持たないため fan-out する。
                # AR 適用外のサービスでも spec を作り「適用外の理由」を記録することで
                # 成果物ゲートを決定的にし、除外判断のトレーサビリティも確保する。
                fanout_parser="service_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aad-web/_common.md",
                output_paths_template=["docs/services/{serviceId}-agentic-retrieval-spec.md"],
                required_skills=["agentic-retrieval-contract"],
                disabled_when_config={"enable_agentic_retrieval": ["no"]},
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/domain-analytics.md", "docs/catalog/service-catalog.md", "docs/services/{serviceId}-{serviceNameSlug}-description.md"]),
        StepDef(id="3", title="画面 ↔ サービス整合性レビュー",
                custom_agent="QA-DocConsistency",
                depends_on=["2.1", "2.2", "2.3", "2.4"],
                consumed_artifacts=["screen_specs", "service_specs", "test_specs", "service_catalog_matrix", "app_catalog", "data_model"],
                body_template_path="templates/aad-web/step-3.md",
                output_paths=["docs/catalog/screen-service-consistency-report.md"],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "docs/screen/{screenId}-{screenNameSlug}-description.md", "docs/services/{serviceId}-{serviceNameSlug}-description.md", "docs/test-specs/{screenId}-test-spec.md", "docs/test-specs/{serviceId}-test-spec.md"]),
    ],
)

# --- ASDW-WEB: Web App Dev & Deploy ---
ASDW_WEB = WorkflowDef(
    id="asdw-web",
    name="Web App Dev & Deploy",
    label_prefix="asdw-web",
    state_labels=_make_state_labels("asdw-web"),
    params=["app_ids", "app_id", "resource_group", "usecase_id", "tdd_max_retries", "create_remote_mcp_server"],
    # local-first / live-last: local 生成（1.1/1.2/2.1/2.3/3.1/3.2/3.3/4.1/4.2）を
    # 完了させてから live deploy（1.3/2.2/2.4/3.4/3.5/4.3/4.4/5.x）へ進む。
    # 初期版は同一 worktree の true parallel を避けるため逐次実行に固定する。
    max_parallel=1,
    local_checkpoint_step_id="4.2",
    steps=[
        # コンテナ
        StepDef(id="1", title="データ（コンテナ）", custom_agent=None, is_container=True),
        StepDef(id="2", title="追加サービス（コンテナ）", custom_agent=None, is_container=True),
        StepDef(id="3", title="Compute（コンテナ）", custom_agent=None, is_container=True),
        StepDef(id="4", title="UI（コンテナ）", custom_agent=None, is_container=True),
        StepDef(id="5", title="レビュー（コンテナ）", custom_agent=None, is_container=True),
        # ---- コンテナ 1: データ ----
        StepDef(id="1.1", title="Azure データストア選定",
                custom_agent="Dev-Microservice-Azure-DataDesign",
                # docs/templates/agent-playbook.md は既知 key なし → スキップ
                consumed_artifacts=["data_model", "service_catalog", "domain_analytics", "app_catalog"],
                body_template_path="templates/asdw-web/step-1.1.md",
                # 根拠: templates/asdw-web/step-1.1.md `## 出力`
                output_paths=["docs/azure/azure-services-data.md"],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/domain-analytics.md", "docs/catalog/service-catalog.md"]),
        StepDef(id="1.2", title="データストア検証テスト生成 (TDD RED)",
                custom_agent="Dev-Microservice-Azure-DataTestCoding",
                depends_on=["1.1"],
                # docs/azure/azure-services-data.md は既知 key なし → スキップ
                # src/data/sample-data.json は src_files でカバー
                consumed_artifacts=["app_catalog", "src_files"],
                body_template_path="templates/asdw-web/step-1.2.md",
                output_paths=["src/infra/azure/verify-data-resources.sh"],
                required_input_paths=["docs/azure/azure-services-data.md", "docs/catalog/app-catalog.md"]),
        StepDef(id="1.3", title="Azure データサービス Deploy (TDD GREEN)",
                custom_agent="Dev-Microservice-Azure-DataDeploy",
                # local generation checkpoint（Step 4.2 完了）後に実行する最初の live Step。
                depends_on=["1.2", "4.2"],
                # docs/azure/azure-services-data.md は既知 key なし → スキップ
                # src_files の概括宣言に加え、件数契約の正本はfail-closed用に明示する
                consumed_artifacts=["service_catalog_matrix", "app_catalog", "src_files"],
                body_template_path="templates/asdw-web/step-1.3.md",
                output_paths=["src/infra/azure/create-azure-data-resources-prep.sh", "src/infra/azure/create-azure-data-resources.sh", "src/data/azure/data-registration-script.sh", "docs/azure/service-catalog.md"],
            required_input_paths=["docs/azure/azure-services-data.md", "docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "src/data/sample-data.json", "src/infra/azure/verify-data-resources.sh"],
            # FR-WF-ASDW-01: Azure write 前の fail-closed 検証に必要な bootstrap 入力。
            # 根拠は hve/asdw_data_runtime_context.py build_asdw_data_deploy_bootstrap_context。
            required_params=[
                "resource_group",
                "data_location",
                "data_resource_suffix",
                "data_vnet_cidr",
                "data_private_endpoint_subnet_cidr",
                "data_aci_subnet_cidr",
            ],
            # 根拠のある値だけを既定値にする。
            # - data_location: Skill azure-region-policy §1 の標準リージョン第 1 位
            # - data_resource_suffix: Step 1.3 の単一 APP スコープから導出
            # - CIDR 3 件: RFC 1918 私用アドレス。新規 VNet 作成のため包含・非重複を満たす
            # resource_group は環境固有のため既定値を持たない。
            # 検証イメージは prep stage が作成するため入力項目ではない。
            default_params={
                "data_location": "japaneast",
                "data_resource_suffix": asdw_data_deploy_resource_suffix(),
                "data_vnet_cidr": "10.40.0.0/16",
                "data_private_endpoint_subnet_cidr": "10.40.1.0/24",
                "data_aci_subnet_cidr": "10.40.2.0/24",
            },
            reality_gate_acs=["AC-1", "AC-2", "AC-3"],
            requires_remote_cicd=False),
        # ---- コンテナ 2: 追加サービス ----
        StepDef(id="2.1", title="追加 Azure サービス選定",
                custom_agent="Dev-Microservice-Azure-AddServiceDesign",
                depends_on=["1.1"],
                # docs/azure/azure-services-*.md は既知 key なし → スキップ
                consumed_artifacts=["use_case_catalog", "service_catalog", "service_specs", "app_catalog"],
                body_template_path="templates/asdw-web/step-2.1.md",
                # 根拠: templates/asdw-web/step-2.1.md `## 出力`
                output_paths=["docs/azure/azure-services-additional.md"],
                required_input_paths=["docs/azure/azure-services-compute.md", "docs/azure/azure-services-data.md", "docs/catalog/app-catalog.md", "docs/catalog/service-catalog.md", "docs/catalog/use-case-catalog.md", "docs/services/{serviceId}-{serviceNameSlug}-description.md"]),
        StepDef(id="2.2", title="追加 Azure サービス Deploy",
                custom_agent="Dev-Microservice-Azure-AddServiceDeploy",
                depends_on=["1.3", "2.1"],
                skip_fallback_deps=["2.1"],
                # docs/azure/azure-services-additional.md は既知 key なし → app_catalog のみ
                consumed_artifacts=["app_catalog"],
                body_template_path="templates/asdw-web/step-2.2.md",
                # 根拠: templates/asdw-web/step-2.2.md `## 出力` の確定ファイル名 2 件。
                # services/<service>.sh は条件付き、service-catalog-matrix.md は更新のみのため除外。
                output_paths=["src/infra/azure/create-azure-additional-resources-prep.sh", "src/infra/azure/create-azure-additional-resources/create.sh"],
                # 根拠: Dev-Microservice-Azure-AddServiceDeploy.prompt.md `## 出力`。
                # いずれもサービス数・Secret 依存による条件付き / glob 表記のため
                # 確定ファイルパスとしてはゲートできない。io-contract との契約一致のために
                # template 側へ宣言する（非 fan-out Step の template は実行時に展開されない）。
                output_paths_template=[
                    "src/infra/azure/create-azure-additional-resources/services/<service>.sh",
                    "src/infra/azure/create-azure-additional-resources/verify-*.sh",
                    "src/infra/azure/verify-secrets-expiry.sh",
                ],
                required_input_paths=["docs/azure/azure-services-additional.md", "docs/catalog/app-catalog.md"],
                required_skills=[
                    "azure-cli-deploy-scripts",
                    "azure-ac-verification",
                    "azure-region-policy",
                ],
                # 実在系 reality gate: AC-1（全リソース存在）、AC-13（Foundry の
                # デプロイ済みモデル >= 1）、AC-14（Foundry Project 子リソース）を
                # registry で強制し、prompt の AC と gate を整合させる。
                reality_gate_acs=["AC-1", "AC-13", "AC-14"],
                requires_remote_cicd=False),
        StepDef(id="2.3", title="追加サービスのテストコード生成 (TDD RED)",
                custom_agent="Dev-Microservice-Azure-AddServiceTestCoding",
                # deploy 済みリソースではなく Step 2.1 の設計から baseline integration test を生成する。
                depends_on=["2.1"],
                consumed_artifacts=["app_catalog"],
                body_template_path="templates/asdw-web/step-2.3.md",
                # 根拠: templates/asdw-web/step-2.3.md `## 出力`。ディレクトリ参照のため
                # 確定ファイルパスとしてはゲートできない。
                output_paths_template=["src/test/integration/add-service/"],
                required_input_paths=["docs/azure/azure-services-additional.md", "docs/catalog/app-catalog.md"]),
        StepDef(id="2.4", title="追加サービスのテスト実施 (TDD GREEN)",
                custom_agent="Dev-Microservice-Azure-AddServiceTesting",
                depends_on=["2.2", "2.3"],
                consumed_artifacts=["app_catalog"],
                body_template_path="templates/asdw-web/step-2.4.md",
                # 根拠: Dev-Microservice-Azure-AddServiceTesting--asdw-web--2.4.yaml
                # （`mode: append` = Step 2.3 が生成したテストツリーへの追記）。
                output_paths_template=["src/test/integration/add-service/"],
                required_input_paths=["docs/azure/azure-services-additional.md", "docs/catalog/app-catalog.md", "src/test/integration/add-service/"]),
        # ---- コンテナ 2: Agentic Retrieval（ADR-0001 Phase 5）----
        # Step.2.5 は local 生成、Step.2.6 は live deploy。
        # local-first / live-last の規約に従い、2.6 は live 済みの 2.2 に依存させる。
        StepDef(id="2.5", title="Agentic Retrieval Azure 実装設計",
                custom_agent="Dev-Microservice-Azure-AgenticRetrievalDesign",
                depends_on=["2.1"],
                consumed_artifacts=["use_case_catalog", "service_catalog", "service_specs", "app_catalog"],
                body_template_path="templates/asdw-web/step-2.5.md",
                # 根拠: Dev-Microservice-Azure-AgenticRetrievalDesign.prompt.md `## Outputs`。
                # 成果物がサービス単位の設計書のため fan-out する（AAD-WEB Step.2.6 と同形）。
                # 共通カタログへの追記は並列子間で競合するため宣言しない。
                fanout_parser="service_catalog",
                additional_prompt_template_path="hve/prompt/fanout/asdw-web/_common.md",
                output_paths_template=["docs/azure/agentic-retrieval/{serviceId}-design.md"],
                required_skills=["agentic-retrieval-contract"],
                disabled_when_config={"enable_agentic_retrieval": ["no"]},
                required_input_paths=["docs/azure/azure-services-additional.md", "docs/catalog/app-catalog.md", "docs/catalog/service-catalog.md", "docs/services/{serviceId}-agentic-retrieval-spec.md"]),
        StepDef(id="2.6", title="Agentic Retrieval Deploy",
                custom_agent="Dev-Microservice-Azure-AgenticRetrievalDeploy",
                depends_on=["2.2", "2.5"],
                skip_fallback_deps=["2.5"],
                consumed_artifacts=["app_catalog"],
                body_template_path="templates/asdw-web/step-2.6.md",
                # 根拠: Dev-Microservice-Azure-AgenticRetrievalDeploy.prompt.md §3。
                # 本 Step は 1 回の実行で全サービス分を生成するため fan-out しない。
                # サービス別スクリプトは {serviceId} ではなくディレクトリ単位で宣言する。
                output_paths_template=[
                    "src/infra/azure/create-azure-agentic-retrieval/prep.sh",
                    "src/infra/azure/create-azure-agentic-retrieval/create.sh",
                    "src/infra/azure/create-azure-agentic-retrieval/services/",
                ],
                required_input_paths=["docs/azure/agentic-retrieval/{serviceId}-design.md", "docs/catalog/app-catalog.md"],
                required_skills=[
                    "agentic-retrieval-contract",
                    "azure-cli-deploy-scripts",
                    "azure-ac-verification",
                    "azure-region-policy",
                ],
                # AC4B-1: 全リソースが Succeeded / AC4B-14: reasoning effort 一致 /
                # AC4B-15: Knowledge Source 一致 / AC4B-18: 全 KS を横断する smoke retrieve。
                reality_gate_acs=["AC4B-1", "AC4B-14", "AC4B-15", "AC4B-18"],
                disabled_when_config={"enable_agentic_retrieval": ["no"]},
                requires_remote_cicd=False),
        # ---- コンテナ 3: Compute ----
        StepDef(id="3.1", title="Azure コンピュート選定",
                custom_agent="Dev-Microservice-Azure-ComputeDesign",
                # live service catalog（Step 1.3 出力）ではなく Step 1.1 の planned design を入力にする。
                depends_on=["2.3"],
                consumed_artifacts=["service_catalog", "use_case_catalog", "data_model", "service_catalog_matrix", "app_catalog"],
                body_template_path="templates/asdw-web/step-3.1.md",
                # 根拠: templates/asdw-web/step-3.1.md `## 出力`
                output_paths=["docs/azure/azure-services-compute.md"],
                required_input_paths=["docs/azure/azure-services-data.md", "docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/service-catalog.md", "docs/catalog/use-case-catalog.md"]),
        StepDef(id="3.2", title="サービス テストコード生成 (TDD RED)",
                custom_agent="Dev-Microservice-Azure-ServiceTestCoding",
                depends_on=["3.1"],
                skip_fallback_deps=[],
                consumed_artifacts=["test_specs", "service_specs", "service_catalog_matrix", "app_catalog"],
                body_template_path="templates/asdw-web/step-3.2.md",
                fanout_parser="service_catalog",
                additional_prompt_template_path="hve/prompt/fanout/asdw-web/_common.md",
                # 根拠: ASDW-WEB 実行後に実在する `src/test/api/SVC-01.Tests` 〜 `SVC-23.Tests`
                # の 8 ディレクトリ。テストプロジェクトは **serviceId** で命名される（
                # `src/api/SVC-01-member-consent-service/` の
                # `{serviceId}-{serviceNameSlug}` 形式とは規約が異なる）。
                output_paths_template=[
                    "src/test/api/{serviceId}.Tests/",
                    "src/test/api/{serviceId}.Tests/README.md",
                ],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/test-strategy.md", "docs/services/{serviceId}-{serviceNameSlug}-description.md", "docs/test-specs/{serviceId}-test-spec.md", "src/test/api/"]),
        StepDef(id="3.3", title="サービスコード実装 (TDD GREEN)",
                custom_agent="Dev-Microservice-Azure-ServiceCoding-AzureFunctions",
                depends_on=["3.2"],
                skip_fallback_deps=["3.2"],
                # docs/azure/azure-services-*.md は既知 key なし → スキップ
                consumed_artifacts=["service_specs", "service_catalog", "data_model", "service_catalog_matrix", "app_catalog", "test_files", "test_specs"],
                body_template_path="templates/asdw-web/step-3.3.md",
                fanout_parser="service_catalog",
                additional_prompt_template_path="hve/prompt/fanout/asdw-web/_common.md",
                # 根拠: templates/asdw-web/step-3.3.md `## 出力`。
                # いずれもディレクトリ参照 or 未解決スラッグ or 「任意推奨」のため
                # 確定ファイルパスとしてはゲートできない。
                output_paths_template=[
                    "src/api/{serviceId}-{serviceNameSlug}/",
                    "src/test/api/",
                    "src/test/api/smoke-ui/index.html",
                ],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/service-catalog.md", "docs/services/{serviceId}-{serviceNameSlug}-description.md", "docs/test-specs/{serviceId}-test-spec.md"]),
        StepDef(id="3.4", title="Azure Compute Deploy",
                custom_agent="Dev-Microservice-Azure-ComputeDeploy-AzureFunctions",
                depends_on=["2.4", "3.3"],
                consumed_artifacts=["service_catalog", "service_catalog_matrix", "app_catalog", "src_files"],
                body_template_path="templates/asdw-web/step-3.4.md",
            # 根拠: templates/asdw-web/step-3.4.md `## 出力` + Prompt
            # Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.prompt.md <output_contract>。
            # .github/workflows/ 配下と service-catalog-matrix.md 更新は
            # 確定ファイル名でないため除外。
            output_paths=["src/infra/azure/create-azure-api-resources-prep.sh", "src/infra/azure/create-azure-api-resources.sh"],
            # 根拠: 同 prompt `<output_contract>` の残り。glob / ディレクトリ参照 /
            # 更新のみのため確定ファイルパスとしてはゲートできない。
            # 本 Step は fan-out しないため、`{serviceId}` / `{serviceNameSlug}` は
            # 代入されず永久に解決できない。`src/test/` 直下に当該ディレクトリが
            # 作られた実績も無い（実在するのは api / integration / ui）ため宣言を削除した。
            output_paths_template=[
                ".github/workflows/*",
                "docs/catalog/service-catalog-matrix.md",
                "src/infra/README.md",
                "src/infra/azure/rollback/compute-functions-rollback.md",
                "src/infra/azure/verify-azure-resources.sh",
            ],
            required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/service-catalog.md", "src/api/{serviceId}-{serviceNameSlug}/"],
            requires_remote_cicd=True),
        StepDef(id="3.5", title="Deploy 後 再テスト",
                custom_agent="Dev-Microservice-Azure-ComputePostDeployTest",
                depends_on=["3.4"],
                consumed_artifacts=["service_catalog_matrix", "app_catalog", "src_files"],
                body_template_path="templates/asdw-web/step-3.5.md",
                # 根拠: templates/asdw-web/step-3.5.md `## 出力`。
                # 「必要に応じて」の条件付き生成物かつディレクトリ参照のためゲートできない。
                output_paths_template=["src/test/post-deploy/"],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "src/test/api/"]),
        # ---- コンテナ 4: UI ----
        StepDef(id="4.1", title="UI テストコード生成 (TDD RED)",
                custom_agent="Dev-Microservice-Azure-UITestCoding",
                depends_on=["3.3"],
                skip_fallback_deps=[],
                consumed_artifacts=["test_specs", "screen_specs", "service_catalog_matrix", "app_catalog"],
                body_template_path="templates/asdw-web/step-4.1.md",
                fanout_parser="screen_catalog",
                additional_prompt_template_path="hve/prompt/fanout/asdw-web/_common.md",
                # 根拠: templates/asdw-web/step-4.1.md `## 出力` と
                # Dev-Microservice-Azure-UITestCoding.prompt.md `## 出力`。
                # ``{screenId}`` は screen_catalog の fan-out キーそのもの。README.md のみ
                # 確定ファイルパスとして展開され、ディレクトリ参照 2 件は展開時に落ちる。
                output_paths_template=[
                    "src/test/ui/",
                    "src/test/ui/{screenId}/",
                    "src/test/ui/{screenId}/README.md",
                ],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/screen-catalog-APP-*.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/test-strategy.md", "docs/screen/{screenId}-{screenNameSlug}-description.md", "docs/test-specs/{screenId}-test-spec.md", "src/test/ui/"]),
        StepDef(id="4.2", title="UI 実装 (TDD GREEN)",
                custom_agent="Dev-Microservice-Azure-UICoding",
                # local generation checkpoint の直前 Step。データ検証テスト（1.2）と
                # Agentic Retrieval 実装設計（2.5）も揃った状態で実行する。
                depends_on=["1.2", "2.5", "4.1"],
                skip_fallback_deps=["4.1"],
                consumed_artifacts=["screen_specs", "screen_catalog", "service_catalog_matrix", "use_case_catalog", "app_catalog", "src_files", "test_files", "test_specs"],
                body_template_path="templates/asdw-web/step-4.2.md",
                fanout_parser="screen_catalog",
                additional_prompt_template_path="hve/prompt/fanout/asdw-web/_common.md",
                # 根拠: templates/asdw-web/step-4.2.md `## 出力`（`src/app/` 配下に UI 実装）と
                # Dev-Microservice-Azure-UICoding--asdw-web--4.2.yaml。いずれも画面別ではなく
                # アプリ共通の成果物のため fan-out 子別のゲート対象にはしない。
                output_paths_template=[
                    "src/app/",
                    "src/app/package.json",
                    "src/app/main.js",
                ],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/screen-catalog-APP-*.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/use-case-catalog.md", "docs/screen/{screenId}-{screenNameSlug}-description.md", "docs/test-specs/{screenId}-test-spec.md", "src/data/sample-data.json", "src/test/ui/"]),
        StepDef(id="4.3", title="Web アプリ Deploy (Azure SWA)",
                custom_agent="Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps",
                depends_on=["3.5", "4.2"],
                consumed_artifacts=["app_catalog"],
                body_template_path="templates/asdw-web/step-4.3.md",
            # 根拠: templates/asdw-web/step-4.3.md `## 出力` かつ Prompt
            # Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md <output_contract> の両方に存在するパス。
            # -prep.sh はテンプレートのみの記載で Prompt 契約に無いため除外（TBD 扱い）。
            output_paths=["src/infra/azure/create-azure-webui-resources.sh"],
            # 根拠: Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md `<output_contract>`
            # の残り 5 件。service-catalog-matrix.md は更新のみ、他はデプロイ経路依存のため
            # 確定ファイルパスとしてはゲートしない。
            output_paths_template=[
                "docs/catalog/service-catalog-matrix.md",
                "src/app/staticwebapp.config.json",
                "src/infra/azure/switch-swa-to-main.sh",
                "src/infra/azure/verify-webui-resources.sh",
                "src/infra/azure/rollback/ui-staticwebapps-rollback.md",
            ],
            required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "src/app/package.json"],
            requires_remote_cicd=True),
        StepDef(id="4.4", title="UI E2E テスト (Playwright)",
                custom_agent="E2ETesting-Playwright",
                depends_on=["4.3"],
                consumed_artifacts=["app_catalog", "service_catalog_matrix", "test_specs", "src_files"],
                body_template_path="templates/asdw-web/step-4.4.md",
                # 根拠: E2ETesting-Playwright.prompt.md `## 出力`。ディレクトリ参照のためゲートできない。
                output_paths_template=["src/test/e2e/playwright/"],
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "docs/test-specs/{screenId}-test-spec.md"]),
        # ---- コンテナ 5: レビュー ----
        StepDef(id="5.1", title="WAF アーキテクチャレビュー",
                custom_agent="QA-AzureArchitectureReview",
                depends_on=["4.4"],
                # docs/azure/azure-services-*.md は既知 key なし → スキップ
                consumed_artifacts=["use_case_catalog", "service_catalog_matrix", "app_catalog"],
                body_template_path="templates/asdw-web/step-5.1.md",
                # 根拠: templates/asdw-web/step-5.1.md `## 出力`
                output_paths=["docs/azure/azure-architecture-review-report.md"],
                required_input_paths=["docs/azure/azure-services-additional.md", "docs/azure/azure-services-compute.md", "docs/azure/azure-services-data.md", "docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/use-case-catalog.md"]),
        StepDef(id="5.2", title="整合性チェック",
                custom_agent="QA-AzureDependencyReview",
                depends_on=["4.4"],
                # docs/azure/azure-services-*.md は既知 key なし、src/app/ src/api/ src/infra/ は src_files でカバー
                consumed_artifacts=["service_catalog_matrix", "app_catalog", "src_files"],
                body_template_path="templates/asdw-web/step-5.2.md",
                # 根拠: templates/asdw-web/step-5.2.md `## 出力`
                output_paths=["docs/azure/dependency-review-report.md"],
                required_input_paths=["docs/azure/azure-services-compute.md", "docs/azure/azure-services-data.md", "docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "src/api/", "src/app/"]),
    ],
)

# --- ADFD: Dataflow Design (7 steps) ---
# Step ID 体系:
#   Step 0.1 / 0.2 / 4 / 5 は ADFDV が `required_input_paths` として要求しながら
#   producer Agent が存在しなかった 4 ドキュメントの生成 Step。既存 Step 1/2/3
#   （旧 ABD 6.1/6.2/6.3 相当）の ID は adfdv / 既存テストが依存するため不変とする。
#   ServiceCatalog=4 / TestStrategy=5 は、`.github/io-contracts/Dev-Dataflow-*.yaml`
#   が既に producer として宣言している `--adfd--4` / `--adfd--5` と一致させるため
#   旧 ABD 採番をそのまま採用する。DataModel / AppCatalog の旧 ABD 採番 2 / 3 は
#   既存 Step 2（MonitoringDesign）/ 3（TDD-TestSpec）と衝突するため、
#   「既存 Step ブロックの上流」を表す 0.1 / 0.2 を新規採番する。
ADFD = WorkflowDef(
    id="adfd",
    name="Dataflow Design",
    label_prefix="adfd",
    state_labels=_make_state_labels("adfd"),
    params=["app_ids", "app_id"],
    steps=[
        StepDef(id="0.1", title="データフローデータモデル定義書", custom_agent="Arch-Dataflow-DataModel", consumed_artifacts=["data_model", "app_catalog"], body_template_path="templates/adfd/step-0.1.md",
                # 根拠: templates/adfd/step-0.1.md `## 出力`
                output_paths=["docs/dataflow/dataflow-data-model.md"], required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/data-model.md"]),
        StepDef(id="0.2", title="データフローアプリカタログ", custom_agent="Arch-Dataflow-AppCatalog", depends_on=["0.1"], consumed_artifacts=["app_catalog", "service_catalog_matrix"], body_template_path="templates/adfd/step-0.2.md",
                # 根拠: templates/adfd/step-0.2.md `## 出力`
                output_paths=["docs/dataflow/dataflow-app-catalog.md"], required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "docs/dataflow/dataflow-data-model.md"]),
        StepDef(id="4", title="データフローサービスカタログ", custom_agent="Arch-Dataflow-ServiceCatalog", depends_on=["0.2"], consumed_artifacts=["service_catalog_matrix"], body_template_path="templates/adfd/step-4.md",
                # 根拠: templates/adfd/step-4.md `## 出力`
                output_paths=["docs/dataflow/dataflow-service-catalog.md"], required_input_paths=["docs/catalog/service-catalog-matrix.md", "docs/dataflow/dataflow-app-catalog.md"]),
        StepDef(id="5", title="データフローテスト戦略書", custom_agent="Arch-Dataflow-TestStrategy", depends_on=["4"], consumed_artifacts=["test_strategy"], body_template_path="templates/adfd/step-5.md",
                # 根拠: templates/adfd/step-5.md `## 出力`
                output_paths=["docs/dataflow/dataflow-test-strategy.md"], required_input_paths=["docs/catalog/test-strategy.md", "docs/dataflow/dataflow-app-catalog.md", "docs/dataflow/dataflow-service-catalog.md"]),
        StepDef(id="1", title="ジョブ詳細仕様書", custom_agent="Arch-Dataflow-AppSpec", depends_on=["5"], consumed_artifacts=["app_catalog", "service_catalog_matrix", "data_model"], body_template_path="templates/adfd/step-1.md",
                fanout_parser="dataflow_catalog",
                additional_prompt_template_path="hve/prompt/fanout/adfd/_common.md",
                output_paths_template=["docs/dataflow/apps/{key}-spec.md"], required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/service-catalog-matrix.md"]),
        StepDef(id="2", title="監視・運用設計書", custom_agent="Arch-Dataflow-MonitoringDesign", depends_on=["5"], consumed_artifacts=["app_catalog", "service_catalog_matrix"], body_template_path="templates/adfd/step-2.md",
                output_paths=["docs/dataflow/dataflow-monitoring-design.md"], required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md"]),
        StepDef(id="3", title="TDDテスト仕様書", custom_agent="Arch-Dataflow-TDD-TestSpec", depends_on=["1", "2"], consumed_artifacts=["test_strategy", "service_catalog_matrix", "dataflow_specs"], body_template_path="templates/adfd/step-3.md",
                fanout_parser="dataflow_catalog",
                additional_prompt_template_path="hve/prompt/fanout/adfd/_common.md",
                output_paths_template=["docs/test-specs/{key}-test-spec.md"], required_input_paths=["docs/catalog/test-strategy.md", "docs/catalog/service-catalog-matrix.md", "docs/dataflow/apps/{key}-spec.md", "docs/dataflow/dataflow-monitoring-design.md"]),
    ],
)

# --- ADFDV: Dataflow Dev ---
ADFDV = WorkflowDef(
    id="adfdv",
    name="Dataflow Dev",
    label_prefix="adfdv",
    state_labels=_make_state_labels("adfdv"),
    params=["app_ids", "app_id", "resource_group", "app_id", "tdd_max_retries"],
    steps=[
        # docs/dataflow/dataflow-data-source-analysis.md, dataflow-test-strategy.md は既知 key なし → スキップ
        # 注: `docs/dataflow/apps/{key}-spec.md` の ``{key}`` は ADFD Step 1 (Arch-Dataflow-AppSpec) の
        # fan-out キー（`dataflow_catalog` parser が返す ``APP-NN``）。producer 側の宣言と
        # 表記を揃える（io-contract の producer 解決は完全一致のみ）。
        StepDef(id="1.1", title="データサービス選定", custom_agent="Dev-Dataflow-DataServiceSelect", consumed_artifacts=["batch_domain_analytics", "batch_data_model", "dataflow_catalog", "batch_service_catalog"], body_template_path="templates/adfdv/step-1.1.md",
                # 根拠: templates/adfdv/step-1.1.md `## 出力`。ADFDV の DAG 根に `output_paths` を
                # 宣言すると Self-Improve の target scope が既定 `"."` からこの 2 件へ無言で縮小するため
                # （`workflow_output_paths_cover_workflow` が True に反転する）、契約宣言のみの
                # `output_paths_template` 側へ置く。
                output_paths_template=[
                    "src/infra/azure/dataflow/create-batch-resources.sh",
                    "src/infra/azure/dataflow/verify-batch-resources.sh",
                ],
                required_input_paths=["docs/dataflow/apps/{key}-spec.md", "docs/dataflow/dataflow-app-catalog.md", "docs/dataflow/dataflow-monitoring-design.md", "docs/dataflow/dataflow-service-catalog.md"]),
        # docs/azure/azure-services-data.md, batch-monitoring-design.md は既知 key なし → スキップ
        StepDef(id="1.2", title="Azure データリソース Deploy", custom_agent="Dev-Dataflow-DataDeploy", depends_on=["1.1"], consumed_artifacts=["batch_service_catalog"], body_template_path="templates/adfdv/step-1.2.md", required_input_paths=["docs/dataflow/apps/{key}-spec.md", "docs/dataflow/dataflow-app-catalog.md", "docs/dataflow/dataflow-monitoring-design.md", "docs/dataflow/dataflow-service-catalog.md", "src/infra/azure/dataflow/create-batch-resources.sh", "src/infra/azure/dataflow/verify-batch-resources.sh"], reality_gate_acs=["AC-3"]),
        # docs/dataflow/dataflow-test-strategy.md, batch-monitoring-design.md は既知 key なし → スキップ
        StepDef(id="2.1", title="TDD RED — テストコード作成", custom_agent="Dev-Dataflow-TestCoding", depends_on=["1.2"], consumed_artifacts=["test_specs", "dataflow_catalog", "batch_service_catalog", "dataflow_specs"], body_template_path="templates/adfdv/step-2.1.md",
                fanout_parser="dataflow_catalog",
                # 根拠: templates/adfdv/step-2.1.md `## 出力`。``{jobId}`` / ``{jobNameSlug}`` は
                # dataflow_catalog parser （APP-ID を返す）から復元できないため展開時に落ちる。
                output_paths_template=[
                    "src/test/dataflow/{jobId}-{jobNameSlug}.Tests/",
                    "src/test/dataflow/{jobId}-{jobNameSlug}.Tests/README.md",
                ],
                additional_prompt_template_path="hve/prompt/fanout/adfdv/_common.md", required_input_paths=["docs/dataflow/apps/{key}-spec.md", "docs/dataflow/dataflow-data-model.md", "docs/dataflow/dataflow-service-catalog.md", "docs/dataflow/dataflow-test-strategy.md", "docs/test-specs/{key}-test-spec.md"]),
        # docs/azure/azure-services-data.md, dataflow-test-strategy.md, batch-monitoring-design.md は既知 key なし → スキップ
        StepDef(id="2.2", title="TDD GREEN — データフローアプリ本実装", custom_agent="Dev-Dataflow-ServiceCoding", depends_on=["2.1"], consumed_artifacts=["test_files", "dataflow_specs", "batch_service_catalog"], body_template_path="templates/adfdv/step-2.2.md",
                fanout_parser="dataflow_catalog",
                # 根拠: templates/adfdv/step-2.2.md `## 出力` と
                # Dev-Dataflow-ServiceCoding--adfdv--2.2.yaml。同上の理由で展開時に落ちる。
                output_paths_template=[
                    "src/dataflow/{jobId}-{jobNameSlug}/",
                    "src/dataflow/{jobId}-{jobNameSlug}/README.md",
                    "src/test/dataflow/{jobId}-{jobNameSlug}.Tests/",
                ],
                additional_prompt_template_path="hve/prompt/fanout/adfdv/_common.md", required_input_paths=["docs/dataflow/apps/{key}-spec.md", "docs/dataflow/dataflow-app-catalog.md", "docs/dataflow/dataflow-data-model.md", "docs/dataflow/dataflow-monitoring-design.md", "docs/dataflow/dataflow-service-catalog.md", "docs/test-specs/{key}-test-spec.md"]),
        # docs/azure/azure-services-data.md, batch-monitoring-design.md, azure-services-compute.md は既知 key なし → スキップ
        StepDef(id="3", title="Azure Functions/コンテナ Deploy", custom_agent="Dev-Dataflow-FunctionsDeploy", depends_on=["2.2"], consumed_artifacts=["src_files", "batch_service_catalog"], body_template_path="templates/adfdv/step-3.md",
                # 根拠: templates/adfdv/step-3.md `## 出力`。CI/CD ファイル名は「等」付きの例示で
                # 確定でないため `output_paths` ではなく契約宣言側へ置く。
                output_paths_template=[
                    ".github/workflows/deploy-batch-functions.yml",
                    "src/infra/azure/dataflow/README.md",
                ],
                required_input_paths=["docs/dataflow/apps/{key}-spec.md", "docs/dataflow/dataflow-app-catalog.md", "docs/dataflow/dataflow-monitoring-design.md", "docs/dataflow/dataflow-service-catalog.md"], reality_gate_acs=["AC-2", "AC-3"]),
        # docs/azure/azure-services-data.md, batch-monitoring-design.md, azure-services-compute.md は既知 key なし → スキップ
        # 根拠: templates/adfdv/step-4.1.md `## 出力` および
        # QA-AzureArchitectureReview.prompt.md §2 Step 別出力テーブル（adfdv 4.1 = waf-review.md）。
        # ADFDV の DAG 根は Step 1.1 であり、根が具体 path を寄与しない限り
        # `workflow_output_paths_cover_workflow` は False のままなので、本宣言で
        # Self-Improve target scope は既定 `"."` のまま維持される。
        StepDef(id="4.1", title="WAF レビュー", custom_agent="QA-AzureArchitectureReview", depends_on=["3"], consumed_artifacts=["batch_service_catalog"], body_template_path="templates/adfdv/step-4.1.md", output_paths=["docs/azure/waf-review.md"], required_input_paths=["docs/azure/azure-services-additional.md", "docs/azure/azure-services-compute.md", "docs/azure/azure-services-data.md", "docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/use-case-catalog.md"]),
        # 根拠: templates/adfdv/step-4.2.md `## 出力` / `## 完了条件` および
        # QA-AzureDependencyReview.prompt.md Step 別出力テーブル（adfdv 4.2 = dependency-review.md）。
        StepDef(id="4.2", title="整合性チェック", custom_agent="QA-AzureDependencyReview", depends_on=["3"], consumed_artifacts=["batch_service_catalog"], body_template_path="templates/adfdv/step-4.2.md", output_paths=["docs/azure/dependency-review.md"], required_input_paths=["docs/azure/azure-services-compute.md", "docs/azure/azure-services-data.md", "docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "src/api/", "src/app/"]),
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
                body_template_path="templates/aag/step-1.md",
                output_paths=["docs/agent/agent-application-definition.md"],
                required_input_paths=["docs/azure/azure-services-additional.md", "docs/azure/azure-services-data.md", "docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/domain-analytics.md", "docs/catalog/screen-catalog-APP-*.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/service-catalog.md", "docs/catalog/use-case-catalog.md", "docs/screen/{screenId}-*.md", "docs/services/SVC-*.md", "src/data/sample-data.json"]),
        StepDef(id="2", title="AI Agent 粒度設計",
                custom_agent="Arch-AIAgentDesign-Step2",
                depends_on=["1"],
                # users-guide/08-ai-agent.md は既知 key なし → スキップ
                # agent-application-definition.md は docs/agent/ 配下 → agent_specs でカバー
                consumed_artifacts=["agent_specs", "service_catalog_matrix", "domain_analytics", "data_model", "app_catalog"],
                body_template_path="templates/aag/step-2.md",
                output_paths=["docs/agent/agent-architecture.md"],
                required_input_paths=["docs/agent/agent-application-definition.md", "docs/azure/azure-services-additional.md", "docs/azure/azure-services-data.md", "docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/domain-analytics.md", "docs/catalog/screen-catalog-APP-*.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/service-catalog.md", "docs/catalog/use-case-catalog.md", "docs/screen/{screenId}-*.md", "docs/services/SVC-*.md", "src/data/sample-data.json"]),
        StepDef(id="3", title="AI Agent 詳細設計",
                custom_agent="Arch-AIAgentDesign-Step3",
                depends_on=["2"],
                # users-guide/08-ai-agent.md は既知 key なし → スキップ
                consumed_artifacts=["agent_specs", "service_catalog_matrix", "service_specs", "app_catalog"],
                body_template_path="templates/aag/step-3.md",
                fanout_parser="agent_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aag/_common.md",
                # AG-CAP-03 で Foundry IQ / Azure AI Search Agentic Retrieval を選んだ場合の
                # AR-CAP-01〜05 契約を確定させるため、repo Skill を required 宣言で公開する。
                # TB-CAP-01〜05 は Tool 総数が閾値を超えたときの公開方式を確定させる。
                required_skills=["agentic-retrieval-contract", "foundry-toolbox-contract"],
                output_paths=["docs/ai-agent-catalog.md"],
                output_paths_template=["docs/agent/agent-detail-{key}.md"],
                required_input_paths=["docs/agent/agent-application-definition.md", "docs/agent/agent-architecture.md", "docs/azure/azure-services-additional.md", "docs/azure/azure-services-data.md", "docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/domain-analytics.md", "docs/catalog/screen-catalog-APP-*.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/service-catalog.md", "docs/catalog/use-case-catalog.md", "docs/screen/{screenId}-*.md", "docs/services/SVC-*.md", "src/data/sample-data.json"]),
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
                body_template_path="templates/aagd/step-1.md",
                output_paths=["docs/agent/agent-application-definition.md"],
                required_input_paths=["docs/azure/azure-services-additional.md",
                                      "docs/azure/azure-services-data.md",
                                      "docs/catalog/app-catalog.md",
                                      "docs/catalog/data-model.md",
                                      "docs/catalog/domain-analytics.md",
                                      "docs/catalog/screen-catalog-APP-*.md",
                                      "docs/catalog/service-catalog-matrix.md",
                                      "docs/catalog/service-catalog.md",
                                      "docs/catalog/use-case-catalog.md",
                                      "docs/screen/{screenId}-*.md",
                                      "docs/services/SVC-*.md",
                                      "src/data/sample-data.json"]),
        StepDef(id="2.1", title="AI Agent テスト仕様書 (TDD RED)",
                custom_agent="Arch-TDD-TestSpec",
                depends_on=["1"],
                # docs/ai-agent-catalog.md は docs/agent/ 配下でないため agent_specs キーの対象外 → スキップ
                consumed_artifacts=["test_strategy", "agent_specs", "service_catalog_matrix", "data_model", "app_catalog"],
                body_template_path="templates/aagd/step-2.1.md",
                fanout_parser="agent_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aagd/_common.md",
                # Foundry IQ 経路を選んだ Agent の AR-CAP-03 予算縮退・AR-CAP-04 引用を
                # テスト観点へ落とすため、検証観点の正本を TDD Step へも公開する。
                required_skills=["agentic-retrieval-contract"],
                output_paths_template=["docs/test-specs/{key}-test-spec.md"],
                required_input_paths=["docs/agent/agent-application-definition.md", "docs/catalog/app-catalog.md", "docs/catalog/data-model.md", "docs/catalog/domain-analytics.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/test-strategy.md", "docs/screen/{screenId}-{screenNameSlug}-description.md", "docs/services/{serviceId}-{serviceNameSlug}-description.md"]),
        StepDef(id="2.2", title="AI Agent テストコード生成 (TDD RED)",
                custom_agent="Dev-Microservice-Azure-AgentTestCoding",
                depends_on=["2.1"],
                consumed_artifacts=["test_specs", "agent_specs", "service_catalog_matrix", "app_catalog"],
                body_template_path="templates/aagd/step-2.2.md",
                fanout_parser="agent_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aagd/_common.md",
                # Step 2.1 と同じ理由で AR-CAP の検証観点をテストコードへ届ける。
                required_skills=["agentic-retrieval-contract"],
                # 根拠: templates/aagd/step-2.2.md `## 出力` と
                # Dev-Microservice-Azure-AgentTestCoding.prompt.md `## 出力`。
                # ディレクトリ参照は展開時に落ち、README.md だけが確定ファイルパスとして展開される。
                output_paths_template=[
                    "src/test/agent/{key}.Tests/",
                    "src/test/agent/{key}.Tests/README.md",
                ],
                required_input_paths=["docs/agent/agent-detail-{key}.md", "docs/ai-agent-catalog.md", "docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/test-strategy.md", "docs/test-specs/{key}-test-spec.md", "src/test/api/"]),
        StepDef(id="2.3", title="AI Agent 実装 (TDD GREEN)",
                custom_agent="Dev-Microservice-Azure-AgentCoding",
                depends_on=["2.2"],
                # docs/ai-agent-catalog.md は agent_specs 対象外 → スキップ
                # docs/azure/azure-services-additional.md は既知 key なし → スキップ
                consumed_artifacts=["agent_specs", "test_files", "test_specs", "service_catalog_matrix", "app_catalog"],
                body_template_path="templates/aagd/step-2.3.md",
                fanout_parser="agent_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aagd/_common.md",
                # 設計で Foundry IQ 経路を選んだ場合の実装境界（Tool allowlist / per-user 権限）を揃える。
                # Toolbox / tool search を選んだ場合の実装境界（pin / 検索メタデータ）も揃える。
                required_skills=["agentic-retrieval-contract", "foundry-toolbox-contract"],
                # 根拠: templates/aagd/step-2.3.md `## 出力` と
                # Dev-Microservice-Azure-AgentCoding.prompt.md `## 出力`。
                # `plugin.json` は Agent Plugins 1.0.0 の plugin root マニフェストで、
                # `skills/` と違い無条件に生成されるため宣言できる。
                output_paths_template=[
                    "src/agent/{key}/",
                    "src/agent/{key}/plugin.json",
                    "src/agent/{key}/README.md",
                ],
                required_input_paths=["docs/agent/agent-detail-{key}.md", "docs/ai-agent-catalog.md", "docs/azure/azure-services-additional.md", "docs/azure/azure-services-data.md", "docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "docs/catalog/service-catalog.md", "docs/test-specs/{key}-test-spec.md", "src/test/agent/{key}.Tests/"]),
        StepDef(id="3", title="AI Agent Deploy",
                custom_agent="Dev-Microservice-Azure-AgentDeploy",
                depends_on=["2.3"],
                # docs/ai-agent-catalog.md は agent_specs 対象外 → スキップ
                # docs/azure/azure-services-additional.md は既知 key なし → スキップ
                consumed_artifacts=["src_files", "app_catalog"],
                body_template_path="templates/aagd/step-3.md",
                fanout_parser="agent_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aagd/_common.md",
                # 選択 provider の事前審査・接続検証で AR-CAP-05 の allowlist / 権限境界を照合する。
                # 実 Toolbox の tool search / pin 設定と TB-CAP 設計値の一致も照合する。
                required_skills=["agentic-retrieval-contract", "foundry-toolbox-contract"],
                # 根拠: templates/aagd/step-3.md `## 出力` と
                # Dev-Microservice-Azure-AgentDeploy.prompt.md `## 出力`。
                # `.github/workflows/` をディレクトリ成果物として宣言することで、
                # その配下の Agent 別 workflow ファイルを含め全エントリが
                # 確定ファイルパスとしては展開されない（契約宣言のみ）。
                output_paths_template=[
                    ".github/workflows/",
                    ".github/workflows/deploy-agent-{key}.yml",
                    "src/infra/azure/create-azure-agent-resources-prep.sh",
                    "src/infra/azure/create-azure-agent-resources.sh",
                    "src/infra/azure/verify-agent-resources.sh",
                    "src/infra/azure/README-agent-deploy.md",
                    "docs/test-specs/deploy-step2-agent-test-spec.md",
                    "docs/azure/azure-service-catalog.md",
                ],
                required_input_paths=["docs/agent/agent-detail-{key}.md", "docs/ai-agent-catalog.md", "docs/azure/azure-services-additional.md", "docs/catalog/app-catalog.md", "docs/catalog/service-catalog-matrix.md", "src/agent/{key}/"]),
        # Step.4: tool search の on/off を実測比較する。
        # 公開ベンチマークの削減率は自社カタログの Tool 記述品質に依存するため、
        # TB-CAP-02 の判定は測定でしか裏付けられない。
        # enable_tool_search=no のときは Toolbox 自体を作らないので実測対象がない。
        StepDef(id="4", title="tool search 実測評価",
                custom_agent="QA-ToolSearchEval",
                depends_on=["3"],
                consumed_artifacts=["agent_specs", "app_catalog"],
                body_template_path="templates/aagd/step-4.md",
                fanout_parser="agent_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aagd/_common.md",
                output_paths_template=["docs/agent/tool-search-eval/{key}-eval-report.md"],
                required_skills=["foundry-toolbox-contract"],
                disabled_when_config={"enable_tool_search": ["no"]},
                required_input_paths=["docs/agent/agent-detail-{key}.md", "docs/catalog/app-catalog.md", "src/agent/{key}/"]),
    ],
)

# --- AAR: Agentic Retrieval Add-on ---
# 既に API / データ資産があるアプリへ、Agentic Retrieval 部分「だけ」を後付けするための
# 単独ワークフロー。AAD-WEB / ASDW-WEB を最初から流し直す必要をなくす。
#
# Step 1 / 2 / 5 は AAD-WEB Step.2.6・ASDW-WEB Step.2.5/2.6 と同じ Custom Agent を使う。
# AAR 固有の新規 Agent は Step 4（TestCoding）と Step 6（Eval）のみ。
#
# Step 6 の存在理由: reasoning effort（minimal / low / medium）の選択は
# recall・token・latency のトレードオフであり、測定なしには決められない。
# 「最小限のクエリ回数で返す」という要件を裏付ける唯一の Step。
AAR = WorkflowDef(
    id="aar",
    name="Agentic Retrieval Add-on",
    label_prefix="aar",
    state_labels=_make_state_labels("aar"),
    params=["app_ids", "app_id", "resource_group", "usecase_id"],
    # local 生成（1/2/3/4）を先に終え、live deploy（5）とその実測（6）を後段に置く。
    local_checkpoint_step_id="4",
    steps=[
        StepDef(id="1", title="Agentic Retrieval 機能要件詳細",
                custom_agent="Arch-AgenticRetrieval-Detail",
                consumed_artifacts=["service_catalog", "service_specs", "domain_analytics", "app_catalog"],
                body_template_path="templates/aar/step-1.md",
                # サービス単位の成果物しか持たないため fan-out する。
                fanout_parser="service_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aar/_common.md",
                output_paths_template=["docs/services/{serviceId}-agentic-retrieval-spec.md"],
                required_skills=["agentic-retrieval-contract"],
                disabled_when_config={"enable_agentic_retrieval": ["no"]},
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/domain-analytics.md", "docs/catalog/service-catalog.md", "docs/services/{serviceId}-{serviceNameSlug}-description.md"]),
        StepDef(id="2", title="Agentic Retrieval Azure 実装設計",
                custom_agent="Dev-Microservice-Azure-AgenticRetrievalDesign",
                depends_on=["1"],
                consumed_artifacts=["use_case_catalog", "service_catalog", "service_specs", "app_catalog"],
                body_template_path="templates/aar/step-2.md",
                # 共通カタログへの追記は並列子間で競合するため宣言しない。
                fanout_parser="service_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aar/_common.md",
                output_paths_template=["docs/azure/agentic-retrieval/{serviceId}-design.md"],
                required_skills=["agentic-retrieval-contract"],
                disabled_when_config={"enable_agentic_retrieval": ["no"]},
                required_input_paths=["docs/catalog/app-catalog.md", "docs/catalog/service-catalog.md", "docs/services/{serviceId}-agentic-retrieval-spec.md"]),
        StepDef(id="3", title="Agentic Retrieval テスト仕様",
                custom_agent="Arch-TDD-TestSpec",
                depends_on=["2"],
                consumed_artifacts=["service_specs", "app_catalog"],
                body_template_path="templates/aar/step-3.md",
                fanout_parser="service_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aar/_common.md",
                output_paths_template=["docs/test-specs/{serviceId}-agentic-retrieval-test-spec.md"],
                required_skills=["agentic-retrieval-contract"],
                disabled_when_config={"enable_agentic_retrieval": ["no"]},
                required_input_paths=["docs/azure/agentic-retrieval/{serviceId}-design.md", "docs/catalog/app-catalog.md"]),
        StepDef(id="4", title="Agentic Retrieval テストコード（TDD RED）",
                custom_agent="Dev-Microservice-Azure-AgenticRetrievalTestCoding",
                depends_on=["3"],
                consumed_artifacts=["app_catalog"],
                body_template_path="templates/aar/step-4.md",
                output_paths_template=["src/test/integration/agentic-retrieval/"],
                required_skills=["agentic-retrieval-contract"],
                disabled_when_config={"enable_agentic_retrieval": ["no"]},
                required_input_paths=["docs/catalog/app-catalog.md", "docs/test-specs/{serviceId}-agentic-retrieval-test-spec.md"]),
        StepDef(id="5", title="Agentic Retrieval Deploy",
                custom_agent="Dev-Microservice-Azure-AgenticRetrievalDeploy",
                depends_on=["4"],
                consumed_artifacts=["app_catalog"],
                body_template_path="templates/aar/step-5.md",
                output_paths_template=[
                    "src/infra/azure/create-azure-agentic-retrieval/prep.sh",
                    "src/infra/azure/create-azure-agentic-retrieval/create.sh",
                    "src/infra/azure/create-azure-agentic-retrieval/services/",
                ],
                required_input_paths=["docs/azure/agentic-retrieval/{serviceId}-design.md", "docs/catalog/app-catalog.md"],
                required_skills=[
                    "agentic-retrieval-contract",
                    "azure-cli-deploy-scripts",
                    "azure-ac-verification",
                    "azure-region-policy",
                ],
                reality_gate_acs=["AC4B-1", "AC4B-14", "AC4B-15", "AC4B-18"],
                disabled_when_config={"enable_agentic_retrieval": ["no"]}),
        StepDef(id="6", title="Retrieval 実測評価（reasoning effort 比較）",
                custom_agent="QA-AgenticRetrievalEval",
                depends_on=["5"],
                consumed_artifacts=["app_catalog"],
                body_template_path="templates/aar/step-6.md",
                fanout_parser="service_catalog",
                additional_prompt_template_path="hve/prompt/fanout/aar/_common.md",
                output_paths_template=["docs/azure/agentic-retrieval/{serviceId}-eval-report.md"],
                required_skills=["agentic-retrieval-contract"],
                disabled_when_config={"enable_agentic_retrieval": ["no"]},
                required_input_paths=["docs/azure/agentic-retrieval/{serviceId}-design.md", "docs/catalog/app-catalog.md", "src/test/integration/agentic-retrieval/"]),
    ],
)

# --- AKM: Knowledge Management ---
# ADR-0002 (T4A): D01〜D21 を 21 並列で生成し、横断レビュー (Step 2) で統合する。
_AKM_FANOUT_KEYS: List[str] = [f"D{n:02d}" for n in range(1, 22)]

AKM = WorkflowDef(
    id="akm",
    name="Knowledge Management",
    label_prefix="akm",
    state_labels=_make_state_labels("akm"),
    params=["sources", "target_files", "force_refresh", "custom_source_dir", "enable_auto_merge"],
    max_parallel=21,
    steps=[
        StepDef(
            id="1",
            title="knowledge/ ドキュメント生成・管理",
            custom_agent="KnowledgeManager",
            depends_on=[],
            # qa/, docs-original/, template/, .github/skills/ は既知 key なし → 成果物参照なし
            consumed_artifacts=[],
            required_skills=["knowledge-management"],
            body_template_path="templates/akm/step-1.md",
            fanout_static_keys=_AKM_FANOUT_KEYS,
            additional_prompt_template_path="hve/prompt/fanout/akm/_common.md",
            # 根拠: templates/akm/step-1.md `## 出力` と KnowledgeManager.prompt.md `## 出力`。
            # 3 件とも fan-out 子へは展開されない（status.md はキー別成果物ではなく、
            # 残り 2 件は glob）。これにより `collect_workflow_output_paths` は空のままで、
            # Self-Improve の target scope は既定 `"knowledge/"` を維持する。
            output_paths_template=[
                "knowledge/business-requirement-document-status.md",
                "knowledge/{key}-*.md",
                "knowledge/{key}-*-ChangeLog.md",
            ],
        ),
        StepDef(
            id="2",
            title="knowledge/ 横断整合性レビュー",
            custom_agent="QA-DocConsistency",
            depends_on=["1"],
            consumed_artifacts=["knowledge"],
            body_template_path="templates/akm/step-2.md",
            # 根拠: templates/akm/step-2.md `## 出力` の 2.。レビューレポート本体は
            # Issue コメントへの記録のため path を持たない。AKM の DAG 根は Step 1 であり、
            # 根が具体 path を寄与しない限り Self-Improve scope は既定 `"knowledge/"` のまま。
            output_paths=["knowledge/business-requirement-document-status.md"],
            required_input_paths=["knowledge/{key}-*.md"]),
    ],
)

# --- ADI: Auto Design-doc Ingestion ---
# docs-original/ の設計書を目録化し、下流ワークフローへ選別して渡す前処理。
_ADI_QUESTIONNAIRE_FANOUT_KEYS: List[str] = [f"D{n:02d}" for n in range(1, 22)]

ADI = WorkflowDef(
    id="adi",
    name="Auto Design-doc Ingestion",
    label_prefix="adi",
    state_labels=_make_state_labels("adi"),
    params=["purpose", "target_scope", "depth", "focus_areas"],
    # D01〜D21 の質問票を同一 wave で生成する。
    max_parallel=21,
    steps=[
        StepDef(
            id="1",
            title="原本インベントリ",
            custom_agent="Doc-OriginalInventory",
            depends_on=[],
            # docs-original/ と docs/original-design-doc-ingest/ は既知 key なし → 成果物参照なし
            consumed_artifacts=[],
            required_skills=["knowledge-lookup"],
            body_template_path="templates/adi/step-1.md",
            # index.json は Agent が `python -m hve ingest-docs` で生成する副次成果物。
            output_paths=[
                "docs/catalog/design-doc-inventory.md",
                "docs/original-design-doc-ingest/index.json",
            ],
            # 文書数に応じて増える glob は確定ファイルパスではないため、
            # runner の output_paths ゲートではなく I/O 契約宣言として保持する。
            output_paths_template=["docs/original-design-doc-ingest/*/content.md"],
        ),
        StepDef(
            id="1.1",
            title="原本質問票生成",
            custom_agent="QA-DocConsistency",
            depends_on=["1"],
            consumed_artifacts=["knowledge"],
            required_skills=["knowledge-lookup"],
            body_template_path="templates/adi/step-1.1.md",
            fanout_static_keys=_ADI_QUESTIONNAIRE_FANOUT_KEYS,
            additional_prompt_template_path="hve/prompt/fanout/adi/_questionnaire.md",
            output_paths_template=["qa/{key}-original-docs-questionnaire.md"],
            required_input_paths=[
                "docs/original-design-doc-ingest/index.json",
                "docs/original-design-doc-ingest/*/content.md",
            ],
        ),
        StepDef(
            id="1.2",
            title="原本質問票 join",
            custom_agent="QA-DocConsistency",
            depends_on=["1.1"],
            consumed_artifacts=["knowledge"],
            required_skills=["knowledge-lookup"],
            body_template_path="templates/adi/step-1.2.md",
            output_paths=["qa/original-docs-cross-questionnaire.md"],
            required_input_paths=["qa/{key}-original-docs-questionnaire.md"],
        ),
        StepDef(
            id="2",
            title="Doc Card 生成",
            custom_agent="Doc-OriginalDocCard",
            depends_on=["1.2"],
            consumed_artifacts=[],
            required_skills=["knowledge-lookup"],
            body_template_path="templates/adi/step-2.md",
            # Step 1 が出力する目録の第 1 列（DOC-NNNN）を fan-out キーにする。
            fanout_parser="design_doc_inventory",
            additional_prompt_template_path="hve/prompt/fanout/adi/_common.md",
            # 出力先は slug ディレクトリのため {key} では展開できない（glob で宣言）。
            output_paths_template=["docs/original-design-doc-ingest/*/card.md"],
            required_input_paths=[
                "docs/catalog/design-doc-inventory.md",
                "docs/original-design-doc-ingest/index.json",
                "qa/original-docs-cross-questionnaire.md",
            ],
        ),
        StepDef(
            id="3",
            title="関連性トリアージ・カタログ統合",
            custom_agent="Doc-OriginalTriage",
            depends_on=["2"],
            consumed_artifacts=[],
            required_skills=["knowledge-lookup"],
            body_template_path="templates/adi/step-3.md",
            output_paths=["docs/catalog/design-doc-catalog.md"],
            required_input_paths=[
                "docs/original-design-doc-ingest/*/card.md",
                "docs/catalog/design-doc-inventory.md",
            ],
        ),
        StepDef(
            id="4",
            title="下流ルーティング表",
            custom_agent="Doc-OriginalRouting",
            depends_on=["3"],
            consumed_artifacts=[],
            required_skills=["knowledge-lookup"],
            body_template_path="templates/adi/step-4.md",
            output_paths=["docs/catalog/design-doc-routing.md"],
            required_input_paths=[
                "docs/catalog/design-doc-catalog.md",
                "docs/original-design-doc-ingest/*/card.md",
            ],
        ),
        # Step 5.x は下流ワークフローの「最上流 Step の成果物」へ候補セクションを追記する。
        # ID 採番は下流の責務なので ADI は行わない。書き込み先が重ならないため並列実行する。
        StepDef(
            id="5.1",
            title="ARD 成果物への設計書由来候補の反映",
            custom_agent="Doc-OriginalDownstreamSeed",
            depends_on=["4"],
            consumed_artifacts=[],
            required_skills=["knowledge-lookup"],
            body_template_path="templates/adi/step-5.1.md",
            output_paths=["docs/catalog/use-case-skeleton.md"],
            required_input_paths=[
                "docs/catalog/design-doc-routing.md",
                "docs/original-design-doc-ingest/*/card.md",
            ],
        ),
        StepDef(
            id="5.2",
            title="AAS 成果物への設計書由来候補の反映",
            custom_agent="Doc-OriginalDownstreamSeed",
            depends_on=["4"],
            consumed_artifacts=[],
            required_skills=["knowledge-lookup"],
            body_template_path="templates/adi/step-5.2.md",
            output_paths=[
                "docs/catalog/app-catalog.md",
                "docs/catalog/domain-analytics.md",
                "docs/catalog/data-model.md",
            ],
            required_input_paths=[
                "docs/catalog/design-doc-routing.md",
                "docs/original-design-doc-ingest/*/card.md",
            ],
        ),
        StepDef(
            id="5.3",
            title="ADFD 成果物への設計書由来候補の反映",
            custom_agent="Doc-OriginalDownstreamSeed",
            depends_on=["4"],
            consumed_artifacts=[],
            required_skills=["knowledge-lookup"],
            body_template_path="templates/adi/step-5.3.md",
            output_paths=["docs/dataflow/dataflow-app-catalog.md"],
            required_input_paths=[
                "docs/catalog/design-doc-routing.md",
                "docs/original-design-doc-ingest/*/card.md",
            ],
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
        StepDef(id="1", title="ファイルインベントリ", custom_agent="Doc-FileInventory", depends_on=[], consumed_artifacts=[], body_template_path="templates/adoc/step-1.md",
                output_paths=["docs-generated/inventory.md"]),
        # Step.2.x — 並列 fork
        # 根拠: templates/adoc/step-2.1～2.5.md `## 出力`。`{relative-path}` は
        # 入力ファイルの相対パスから導出される動的パスで、fan-out キーではないため
        # 実行時に確定ファイルパスへ展開できない（契約宣言としてのみ保持）。
        StepDef(id="2.1", title="ファイルサマリー（プロダクションコード）", custom_agent="Doc-FileSummary", depends_on=["1"], consumed_artifacts=[], body_template_path="templates/adoc/step-2.1.md", output_paths_template=["docs-generated/files/{relative-path}.md"], required_input_paths=["docs-generated/inventory.md"]),
        StepDef(id="2.2", title="ファイルサマリー（テストコード）", custom_agent="Doc-TestSummary", depends_on=["1"], consumed_artifacts=[], body_template_path="templates/adoc/step-2.2.md", output_paths_template=["docs-generated/files/{relative-path}.md"], required_input_paths=["docs-generated/inventory.md"]),
        StepDef(id="2.3", title="ファイルサマリー（設定・IaC）", custom_agent="Doc-ConfigSummary", depends_on=["1"], consumed_artifacts=[], body_template_path="templates/adoc/step-2.3.md", output_paths_template=["docs-generated/files/{relative-path}.md"], required_input_paths=["docs-generated/inventory.md"]),
        StepDef(id="2.4", title="ファイルサマリー（CI/CD）", custom_agent="Doc-CICDSummary", depends_on=["1"], consumed_artifacts=[], body_template_path="templates/adoc/step-2.4.md", output_paths_template=["docs-generated/files/{relative-path}.md"], required_input_paths=["docs-generated/inventory.md"]),
        StepDef(id="2.5", title="ファイルサマリー（大規模ファイル分割）", custom_agent="Doc-LargeFileSummary", depends_on=["1"], consumed_artifacts=[], body_template_path="templates/adoc/step-2.5.md", output_paths_template=["docs-generated/files/{relative-path}.md"], required_input_paths=["docs-generated/inventory.md"]),
        # Step.3.x — AND join + 並列 fork
        # 根拠: templates/adoc/step-3.1.md `## 出力`（`docs-generated/components/{module-name}.md`）。
        StepDef(id="3.1", title="コンポーネント設計書", custom_agent="Doc-ComponentDesign", depends_on=["2.1", "2.2", "2.3", "2.4", "2.5"], consumed_artifacts=[], skip_fallback_deps=["2.1"], body_template_path="templates/adoc/step-3.1.md", output_paths_template=["docs-generated/components/{module-name}.md"]),
        StepDef(id="3.2", title="API 仕様書", custom_agent="Doc-APISpec", depends_on=["2.1", "2.2", "2.3", "2.4", "2.5"], consumed_artifacts=[], skip_fallback_deps=["2.1"], body_template_path="templates/adoc/step-3.2.md",
                output_paths=["docs-generated/components/api-spec.md"]),
        StepDef(id="3.3", title="データモデル定義書", custom_agent="Doc-DataModel", depends_on=["2.1", "2.2", "2.3", "2.4", "2.5"], consumed_artifacts=[], skip_fallback_deps=["2.1"], body_template_path="templates/adoc/step-3.3.md",
                output_paths=["docs-generated/components/data-model.md"]),
        StepDef(id="3.4", title="テスト仕様サマリー", custom_agent="Doc-TestSpecSummary", depends_on=["2.2"], consumed_artifacts=[], body_template_path="templates/adoc/step-3.4.md",
                output_paths=["docs-generated/components/test-spec-summary.md"]),
        StepDef(id="3.5", title="技術的負債一覧", custom_agent="Doc-TechDebt", depends_on=["2.1", "2.2", "2.3", "2.4", "2.5"], consumed_artifacts=[], skip_fallback_deps=["2.1"], body_template_path="templates/adoc/step-3.5.md",
                output_paths=["docs-generated/components/tech-debt.md"]),
        # Step.4 — AND join
        StepDef(id="4", title="コンポーネントインデックス", custom_agent="Doc-ComponentIndex", depends_on=["3.1", "3.2", "3.3", "3.4", "3.5"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-4.md",
                output_paths=["docs-generated/component-index.md"], required_input_paths=["docs-generated/components/api-spec.md", "docs-generated/components/data-model.md", "docs-generated/components/tech-debt.md", "docs-generated/components/test-spec-summary.md"]),
        # Step.5.x — 並列 fork
        StepDef(id="5.1", title="アーキテクチャ概要", custom_agent="Doc-ArchOverview", depends_on=["4"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-5.1.md",
                output_paths=["docs-generated/architecture/overview.md"], required_input_paths=["docs-generated/component-index.md"]),
        StepDef(id="5.2", title="依存関係マップ", custom_agent="Doc-DependencyMap", depends_on=["4"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-5.2.md",
                output_paths=["docs-generated/architecture/dependency-map.md"], required_input_paths=["docs-generated/component-index.md"]),
        StepDef(id="5.3", title="インフラ依存分析", custom_agent="Doc-InfraDeps", depends_on=["4"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-5.3.md",
                output_paths=["docs-generated/architecture/infra-deps.md"], required_input_paths=["docs-generated/component-index.md"]),
        StepDef(id="5.4", title="非機能要件現状分析", custom_agent="Doc-NFRAnalysis", depends_on=["4", "3.4", "3.5"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-5.4.md",
                output_paths=["docs-generated/architecture/nfr-analysis.md"], required_input_paths=["docs-generated/component-index.md", "docs-generated/components/tech-debt.md", "docs-generated/components/test-spec-summary.md"]),
        # Step.6.x — 並列 fork
        StepDef(id="6.1", title="オンボーディングガイド", custom_agent="Doc-Onboarding", depends_on=["5.1", "5.2"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-6.1.md",
                output_paths=["docs-generated/guides/onboarding.md"], required_input_paths=["docs-generated/architecture/dependency-map.md", "docs-generated/architecture/overview.md"]),
        StepDef(id="6.2", title="リファクタリングガイド", custom_agent="Doc-Refactoring", depends_on=["5.2", "5.4", "3.5"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-6.2.md",
                output_paths=["docs-generated/guides/refactoring.md"], required_input_paths=["docs-generated/architecture/dependency-map.md", "docs-generated/architecture/nfr-analysis.md", "docs-generated/components/tech-debt.md"]),
        StepDef(id="6.3", title="移行アセスメント", custom_agent="Doc-Migration", depends_on=["5.1", "5.3", "5.4"], consumed_artifacts=["doc_generated"], body_template_path="templates/adoc/step-6.3.md",
                output_paths=["docs-generated/guides/migration-assessment.md"], required_input_paths=["docs-generated/architecture/infra-deps.md", "docs-generated/architecture/nfr-analysis.md", "docs-generated/architecture/overview.md"]),
    ],
)

# --- ARD: Auto Requirement Definition ---
ARD = WorkflowDef(
    id="ard",
    name="Auto Requirement Definition",
    label_prefix="ard",
    state_labels=_make_state_labels("ard"),
    params=[
        "company_name",
        "target_business",
        "survey_base_date",
        "survey_period_years",
        "target_region",
        "analysis_purpose",
        "attached_docs",
        "include_kpi_okr",
    ],
    steps=[
        # Sub-10 (ADR-0003): ARD は 8 step (1, 1.1, 1.2, 2, 2.1, 3.1, 3.2, 3.3) に再設計され、Step 1.1 / 3.2 で fan-out する。
        # 旧 step_id (1, 2, 3) からの resume は warning + 新規実行扱い (ADR-0003 §3.4)。
        # 注: Step 3 (KPI/OKR) は新体系で Step 2.1 に、旧 Step 4.1/4.2/4.3 は新 Step 3.1/3.2/3.3 に整理。
        StepDef(
            id="1",
            title="事業分野候補列挙",
            custom_agent="Arch-ARD-BusinessAnalysis-Untargeted",
            consumed_artifacts=[],
            required_skills=["knowledge-management"],
            output_paths=["docs/company-business-recommendation.md"],
            body_template_path="templates/ard/step-1.md",
        ),
        StepDef(
            id="1.1",
            title="事業分野別深掘り分析",
            custom_agent="Arch-ARD-BusinessAnalysis-Untargeted",
            depends_on=["1"],
            consumed_artifacts=[],
            required_skills=["knowledge-management"],
            fanout_parser="business_candidate",
            output_paths_template=["docs/business/{key}-analysis.md"],
            body_template_path="templates/ard/step-1.1.md",
            additional_prompt_template_path="hve/prompt/fanout/ard/_common.md",
                required_input_paths=["docs/company-business-recommendation.md"]),
        StepDef(
            id="1.2",
            title="事業分析統合",
            custom_agent="Arch-ARD-BusinessAnalysis-Untargeted",
            depends_on=["1.1"],
            consumed_artifacts=[],
            required_skills=["knowledge-management"],
            output_paths=["docs/company-business-requirement.md"],
            body_template_path="templates/ard/step-1.2.md",
                required_input_paths=["docs/business/{key}-analysis.md"]),
        StepDef(
            id="2",
            title="対象業務深掘り分析",
            custom_agent="Arch-ARD-BusinessAnalysis-Targeted",
            # target_business 指定時に直接実行可能（ルートノード扱い）。
            # 未指定経路では Step 1.2 完了後の skip_fallback で 3.1 にバイパス。
            skip_fallback_deps=["1.2"],
            consumed_artifacts=[],
            required_skills=["knowledge-management"],
            output_paths=["docs/business-requirement.md"],
            body_template_path="templates/ard/step-2.md",
        ),
        # Step 2.1: KPI/OKR 定義（任意ステップ）
        # ARD パラメータ `include_kpi_okr=true` の場合のみ active_steps に含まれる
        # （orchestrator 側で展開）。後続 Step 3.1 / 3.2 / aas が任意参照する。
        # Step 2 経路がスキップされた場合は Step 1.2 出力をソースとしてフォールバック。
        StepDef(
            id="2.1",
            title="KPI/OKR 定義（任意）",
            custom_agent="Arch-ARD-KPIOKRDefinition",
            depends_on=["2"],
            skip_fallback_deps=["1.2"],
            consumed_artifacts=[],
            required_skills=["knowledge-management"],
            output_paths=["docs/recommended-kpi-okr.md"],
            body_template_path="templates/ard/step-2.1.md",
        ),
        StepDef(
            id="3.1",
            title="ユースケース骨格抽出",
            custom_agent="Arch-ARD-UseCaseCatalog",
            depends_on=["2"],
            skip_fallback_deps=["1.2"],
            consumed_artifacts=[],
            required_skills=["knowledge-management"],
            output_paths=["docs/catalog/use-case-skeleton.md"],
            # docs/business-requirement.md (Step 2) と docs/company-business-requirement.md (Step 1.2) は
            # いずれも skip_fallback により片方しか生成されない経路があるため、required_input_paths には
            # 含めない（存在する方を consumed_artifacts 経由で参照する）。
            body_template_path="templates/ard/step-3.1.md"),
        StepDef(
            id="3.2",
            title="ユースケース詳細生成",
            custom_agent="Arch-ARD-UseCaseCatalog",
            depends_on=["3.1"],
            consumed_artifacts=[],
            required_skills=["knowledge-management"],
            fanout_parser="use_case_skeleton",
            output_paths_template=["docs/usecase/{key}-detail.md"],
            body_template_path="templates/ard/step-3.2.md",
            additional_prompt_template_path="hve/prompt/fanout/ard/_common.md",
                # 注: docs/business-requirement.md (Step 2) と docs/company-business-requirement.md (Step 1.2) は
                # skip_fallback により片方しか生成されない経路があるため required_input_paths には含めない。
                # 存在する方を consumed_artifacts 経由で参照する（Step 3.1 / 3.3 も同一方針）。
                required_input_paths=["docs/catalog/use-case-skeleton.md"]),
        StepDef(
            id="3.3",
            title="ユースケースカタログ統合",
            custom_agent="Arch-ARD-UseCaseCatalog",
            depends_on=["3.2"],
            consumed_artifacts=[],
            required_skills=["knowledge-management"],
            output_paths=["docs/catalog/use-case-catalog.md"],
            body_template_path="templates/ard/step-3.3.md",
                # 注: company-business-requirement.md は Step 3.1 / 3.2 と同一方針で除外（skip_fallback 詳細は Step 3.1 コメント参照）。
                required_input_paths=["docs/usecase/{key}-detail.md"]),
    ],
    max_parallel=15,
)


FULL_PIPELINE = MetaWorkflowDef(
    id="full-pipeline",
    workflows=["aas", "aad-web", "asdw-web", "adfd", "adfdv", "aag", "aagd"],
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
                    "docs/catalog/service-catalog-matrix.md",
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
        "adfd": [
            WorkflowDependency(
                workflow_id="aas",
                required_artifacts=[
                    "docs/catalog/app-catalog.md",
                    "docs/catalog/domain-analytics.md",
                ],
                soft=True,
            ),
        ],
        "adfdv": [
            WorkflowDependency(
                workflow_id="adfd",
                required_artifacts=[
                    "docs/dataflow/dataflow-domain-analytics.md",
                    "docs/dataflow/dataflow-data-model.md",
                    "docs/dataflow/dataflow-app-catalog.md",
                    "docs/dataflow/dataflow-service-catalog.md",
                    "docs/dataflow/dataflow-test-strategy.md",
                    "docs/dataflow/apps/*.md",
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
    wf.id: wf for wf in [ARD, AAS, AAD_WEB, ASDW_WEB, ADFD, ADFDV, AAG, AAGD, AAR, AKM, ADI, ADOC]
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


def canonicalize_workflow_id(workflow_id: str) -> str:
    """workflow ID を小文字化し、registry の正式 ID へ解決する。"""
    key = (workflow_id or "").lower()
    return _ALIASES.get(key, key)


def get_workflow(workflow_id: str) -> Optional[WorkflowDef]:
    """ワークフロー ID からワークフロー定義を取得する。存在しない場合は None。"""
    return _REGISTRY.get(canonicalize_workflow_id(workflow_id))


def get_meta_dependencies(workflow_id: str) -> List[WorkflowDependency]:
    """指定ワークフローのメタワークフロー依存を返す。

    _META_REGISTRY は小規模運用を前提とし、全走査で依存定義を解決する。
    """
    resolved = canonicalize_workflow_id(workflow_id)
    for mwf in _META_REGISTRY.values():
        if resolved in mwf.dependencies:
            return mwf.dependencies[resolved]
    return []


# ---------------------------------------------------------------------------
# 必須入力ファイル (required_artifacts) の説明文マスタ
# ---------------------------------------------------------------------------
# 各 path / glob に対して 1 行の文書名（説明文）を対応付ける。
# GUI の Step 2 → Step 3 遷移時の precheck と、users-guide/workflow-reference.md
# の表生成に使用する。FULL_PIPELINE.dependencies の required_artifacts に出現
# する全 path / glob を網羅する。新規 required_artifacts を追加する際は本マス
# タにも対応エントリを追加すること（未登録は precheck で path 文字列をそのま
# ま表示する）。
ARTIFACT_DESCRIPTIONS: Dict[str, str] = {
    "docs/catalog/app-catalog.md": "アプリケーションカタログ",
    "docs/catalog/domain-analytics.md": "ドメイン分析",
    "docs/catalog/service-catalog.md": "サービスカタログ",
    "docs/catalog/data-model.md": "データモデル",
    "docs/catalog/service-catalog-matrix.md": "サービスカタログマトリクス",
    "docs/catalog/test-strategy.md": "TDD テスト戦略",
    "docs/screen/*.md": "画面定義書（一覧）",
    "docs/services/*.md": "サービス定義書（一覧）",
    "docs/test-specs/*-test-spec.md": "TDD テスト仕様書（一覧）",
    "docs/dataflow/dataflow-domain-analytics.md": "バッチドメイン分析",
    "docs/dataflow/dataflow-data-model.md": "バッチデータモデル",
    "docs/dataflow/dataflow-app-catalog.md": "データフローアプリカタログ",
    "docs/dataflow/dataflow-service-catalog.md": "バッチサービスカタログ",
    "docs/dataflow/dataflow-test-strategy.md": "データフローテスト戦略",
    "docs/dataflow/dataflow-data-source-analysis.md": "バッチデータソース/デスティネーション分析",
    "docs/dataflow/dataflow-monitoring-design.md": "バッチ監視・運用設計",
    "docs/dataflow/apps/*.md": "データフローアプリ詳細仕様書（一覧）",
    "docs/agent/*.md": "AI Agent 設計書（一覧）",
}


# ---------------------------------------------------------------------------
# Workflow ステップ ID グループマップ (SSOT)
# ---------------------------------------------------------------------------
# GUI / CLI 側で表示するグループ ID と registry の実 Step ID の対応表。
# 旧 hve/orchestrator.py:_ARD_GROUP_MAP / hve/autopilot/plan_review_gap.py:
# _ARD_STEP_TO_GROUP / hve/gui/page_workflow_select.py:_ARD_GROUPS の
# 重複定義を本モジュールに集約する（SSOT）。
#
# 未登録 workflow / 未登録 group ID は素通し（``[sid]`` フォールバック）。
# これにより orchestrator の旧挙動 ``_ARD_GROUP_MAP.get(_sid, [_sid])`` と
# 完全に等価となる。
_WORKFLOW_GROUP_MAPS: Dict[str, Dict[str, List[str]]] = {
    "ard": {
        "1": ["1", "1.1", "1.2"],
        "2": ["2"],
        # GUI/CLI 側のグループ ID "3" は KPI/OKR 任意ステップ。registry 上は "2.1" に再採番済み。
        "3": ["2.1"],
        # GUI/CLI 側のグループ ID "4" はユースケース系。registry 上は "3.1/3.2/3.3" に再採番済み。
        "4": ["3.1", "3.2", "3.3"],
    },
}


def expand_group_step_ids(workflow_id: str, step_ids: List[str]) -> List[str]:
    """GUI/CLI 形式のグループ step ID を registry の実 step ID 列に展開する。

    未登録 workflow / 未登録 group ID は元の ID をそのまま返す（順序保持、
    重複排除なし。旧 ``_ARD_GROUP_MAP.get(sid, [sid])`` と等価）。

    Args:
        workflow_id: 対象 workflow ID（小文字想定）。
        step_ids: GUI または CLI から渡された step ID 列（グループ ID 含む）。

    Returns:
        実 step ID の列。順序は入力順、重複は維持する（呼び出し側で必要なら排除）。

    Examples:
        >>> expand_group_step_ids("ard", ["1", "2", "4"])
        ['1', '1.1', '1.2', '2', '3.1', '3.2', '3.3']
        >>> expand_group_step_ids("aas", ["1", "3.1"])
        ['1', '3.1']
    """
    group_map = _WORKFLOW_GROUP_MAPS.get(workflow_id.lower(), {})
    if not group_map:
        return list(step_ids)
    expanded: List[str] = []
    for sid in step_ids:
        expanded.extend(group_map.get(sid, [sid]))
    return expanded


def group_id_for_step(workflow_id: str, step_id: str) -> Optional[str]:
    """実 step ID から GUI グループ ID への逆引き。未登録は None。

    旧 ``hve.autopilot.plan_review_gap._ARD_STEP_TO_GROUP`` の代替。
    """
    group_map = _WORKFLOW_GROUP_MAPS.get(workflow_id.lower(), {})
    for group_id, member_step_ids in group_map.items():
        if step_id in member_step_ids:
            return group_id
    return None


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


def get_local_phase_step_ids(workflow_id: str) -> FrozenSet[str]:
    """local generation checkpoint までに完了する Step ID 集合を返す。

    checkpoint Step とその推移的依存で構成される。checkpoint 未宣言の
    workflow では空集合を返す（phase 分割を行わない）。
    """
    wf = get_workflow(workflow_id)
    if wf is None or not wf.local_checkpoint_step_id:
        return frozenset()
    collected: set = set()
    pending = [wf.local_checkpoint_step_id]
    while pending:
        current = pending.pop()
        if current in collected:
            continue
        step = wf.get_step(current)
        if step is None:
            continue
        collected.add(current)
        pending.extend(step.depends_on)
    return frozenset(collected)


def get_live_phase_step_ids(workflow_id: str) -> FrozenSet[str]:
    """local generation checkpoint 後に実行する Step ID 集合を返す。"""
    local_ids = get_local_phase_step_ids(workflow_id)
    if not local_ids:
        return frozenset()
    wf = get_workflow(workflow_id)
    assert wf is not None  # get_local_phase_step_ids が非空なら workflow は存在する
    return frozenset(
        s.id for s in wf.steps if not s.is_container and s.id not in local_ids
    )


def list_workflows() -> List[WorkflowDef]:
    """登録済みワークフロー定義をすべて返す。"""
    return list(_REGISTRY.values())


# Issue Form / ウィザードの UI 表示値がそのまま config へ入る経路があるため、
# `disabled_when_config` の照合前に内部値へ寄せる（template_engine と同じ対応関係）。
_DISABLED_WHEN_VALUE_ALIASES: Dict[str, str] = {
    "する": "yes",
    "しない": "no",
    "自動判定に従う": "auto",
}


def _normalize_disabled_when_value(value: Any) -> str:
    text = str(value).strip()
    return _DISABLED_WHEN_VALUE_ALIASES.get(text, text).casefold()


def resolve_disabled_step_ids(
    workflow_id: str,
    config_values: Mapping[str, Any],
) -> FrozenSet[str]:
    """設定値により無効化される Step ID 集合を返す。

    `StepDef.disabled_when_config` の宣言と `config_values` を突き合わせる。
    宣言キーが `config_values` に無い場合、その Step は無効化しない。

    Args:
        workflow_id: ワークフロー ID（後方互換エイリアス可）。
        config_values: `SDKConfig` 属性名 → 値のマッピング。

    Returns:
        無効化する Step ID の集合。該当なしなら空集合。
    """
    wf = get_workflow(workflow_id)
    if wf is None:
        return frozenset()
    disabled: set = set()
    for step in wf.steps:
        for key, values in (step.disabled_when_config or {}).items():
            if key not in config_values:
                continue
            actual = _normalize_disabled_when_value(config_values[key])
            if any(actual == _normalize_disabled_when_value(v) for v in values):
                disabled.add(step.id)
                break
    return frozenset(disabled)


# ---------------------------------------------------------------------------
# Step パラメータ契約（FR-DAG-07）
# ---------------------------------------------------------------------------

def _base_step_id(step_id: str) -> str:
    """fan-out 子 step ID (`{base}/{key}`) を base step ID へ正規化する。"""
    return str(step_id).split("/", 1)[0]


def _is_unset_param(value: Any) -> bool:
    """既定値で補完すべき「未設定」値かを返す。

    `None` と空白のみの文字列だけを未設定とする。型不正の値（int 等）は
    既定値で握り潰さず、pre-flight が検出できるよう False を返す。
    """
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def steps_declaring_params(
    wf: WorkflowDef,
    active_steps: Iterable[str],
) -> List[StepDef]:
    """active step のうち `required_params` を宣言している Step を wf.steps 順で返す。

    Args:
        wf: 対象 WorkflowDef。
        active_steps: 実行対象 step ID の iterable。fan-out 子 ID も受け付ける。
    """
    active_base_ids = {_base_step_id(step_id) for step_id in (active_steps or ())}
    return [
        step
        for step in wf.steps
        if getattr(step, "required_params", None) and step.id in active_base_ids
    ]


def apply_step_default_params(
    wf: WorkflowDef,
    active_steps: Iterable[str],
    params: Dict[str, Any],
) -> List[str]:
    """active step の `default_params` を未設定パラメータへ適用する（FR-DAG-07）。

    補完対象は「キー未存在」「値が None」「空白のみの文字列」の 3 ケースのみ。
    非空の文字列や型不正の値は上書きせず、pre-flight が検出できるよう温存する。

    Args:
        wf: 対象 WorkflowDef。
        active_steps: 実行対象 step ID の iterable。
        params: Workflow パラメータ辞書。**破壊的に更新される**。

    Returns:
        既定値を適用したキー名の昇順リスト。
    """
    applied: set = set()
    for step in steps_declaring_params(wf, active_steps):
        for key, default_value in step.default_params.items():
            if key in params and not _is_unset_param(params[key]):
                continue
            params[key] = default_value
            applied.add(key)
    return sorted(applied)
