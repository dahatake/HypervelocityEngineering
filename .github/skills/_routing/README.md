---
name: _routing
description: >-
  Skill / reference 選択のルーティング表。USE FOR: ルート共通 instructions から、どのフェーズでどの Skill / reference を必要時参照するか判断するとき。
  DO NOT USE FOR: 実装手順、詳細仕様、manifest required/optional 集合の代替。
  WHEN: 作業内容に応じた既存 Skill と適用範囲を確認するとき。
metadata:
  version: 1.0.0
---

# Skills ルーティングテーブル

以下は `.github/copilot-instructions.md` から分離したルーティング一覧。

- ルート共通 instructions は `.github/copilot-instructions.md` を正本とし、この表は必要な Skill / reference を選ぶためだけに使う。
- Agent 作業開始時は `agent-common-preamble` で停止境界と対象範囲を確認し、必要条件に応じた Skill / reference だけ読む。
- 表の説明は要約に留め、field 詳細、全 Skill 本文、manifest の `required_skills` / `optional_skills` 集合は各正本へ委譲する。

**【共通 / planning】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| HVE アプリケーション自体の保守 / 要求トレーサビリティ | `hve-requirement-traceability` | `.github/skills/hve-requirement-traceability/SKILL.md` | active 要件と実在テストを選択取得 |
| HVE 本体のシステムテストを台帳で増分実行したい（「HVE の残りのシステムテスト」。HVE 生成アプリのテストは対象外） | `hve-system-test` | `.github/skills/hve-system-test/SKILL.md` | `tests/system-test-ledger/ledger.py` の `status --brief` / `run` / `run --execute` を使い、未実施ケースを予算内で実行して台帳へ記録 |
| 自然言語の Prompt から既存 Workflow を実行したい（Prompt 版） | `hve-prompt-edition` | `.github/skills/hve-prompt-edition/SKILL.md` | 登録済み Workflow の plan / run と自然言語 resume / request 事前ゲートの参照入口。対象外条件・field 詳細・9手順は Skill / references へ委譲 |
| 曖昧な HVE 実行意図（「設計」「APP の Web アプリ」「バッチを実装」「Azure にデプロイ」だけで Workflow / Step / APP-ID / resource group が不足） | `hve-prompt-edition` | `.github/skills/hve-prompt-edition/SKILL.md` | Workflow / Step / APP-ID / resource group 等の不足確認だけを inline で返す。request / run / write は行わず、direct `azd` / `azure.yaml` は対象外 |
| Agent 作業開始（共通） | `agent-common-preamble` | `.github/skills/agent-common-preamble/SKILL.md` | `.github/copilot-instructions.md` の共通境界を確認し、必要な Skill / reference だけを選ぶ入口 |
| 入力ファイル確認 | `input-file-validation` | `.github/skills/input-file-validation/SKILL.md` | 必読ファイル確認・欠損時処理ルール |
| APP-ID スコープ解決 | `app-scope-resolution` | `.github/skills/app-scope-resolution/SKILL.md` | APP-ID からサービス/画面/エンティティ特定 |
| 生成アプリの APP 別要求選択・追跡 | `application-requirement-traceability` | `.github/skills/application-requirement-traceability/SKILL.md` | APP-ID に対応する要求・ブロッカーを検証し、Requirement ID と根拠を記録 |
| タスク開始 / 不明点あり | `task-questionnaire` | `.github/skills/task-questionnaire/SKILL.md` | HVE の PR / standalone 質問票と Prompt Edition preflight 例外 |
| 計画 / DAG / 見積 | `task-dag-planning` | `.github/skills/task-dag-planning/SKILL.md` | 依存関係分解・受入条件・完了条件・分割単位・見積。HVE 固有の plan.md / subissues.md フォーマットと実行面の選択は `.github/skills/_hve-plan-artifacts/hve-binding.md` が正本 |
| work/ 配下の構造設計 / 一時ファイルの置き場所 | `work-artifacts-layout` | `.github/skills/work-artifacts-layout/SKILL.md` | 入口 README + contracts/artifacts、ルート直下作成禁止 |
| リポジトリ初見 | `repo-onboarding-fast` | `.github/skills/repo-onboarding-fast/SKILL.md` | HVE 作業 run の onboarding 入口と後続参照用5項目 |

**【ドメイン設計 / planning】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| アーキテクチャ候補選定 | `architecture-questionnaire` | `.github/skills/architecture-questionnaire/SKILL.md` | AAS の Q1-Q26・既定根拠・出力表構造 |
| knowledge/ 管理 | `knowledge-management` | `.github/skills/knowledge-management/SKILL.md` | D01〜D21 分類・状態判定・ステータス管理 |
| タスク実行中に業務要件が不明瞭 | `knowledge-lookup` | `.github/skills/knowledge-lookup/SKILL.md` | knowledge/ D01〜D21 の条件付き参照ルール |
| AAG / AAGD の AI Agent 設計・実装 | `ai-agent-capability-contract` | `.github/skills/ai-agent-capability-contract/SKILL.md` | AG-CAP-01〜10 の Goal Loop・Tool・Identity・評価契約 |
| Agentic Retrieval 設計・検証 | `agentic-retrieval-contract` | `.github/skills/agentic-retrieval-contract/SKILL.md` | AR-CAP-01〜05 の検索予算・Knowledge Source・HVE-specific MCP 契約 |
| Toolbox / tool search 設計・検証 | `foundry-toolbox-contract` | `.github/skills/foundry-toolbox-contract/SKILL.md` | TB-CAP-01〜05 の Toolbox 採否・pin・探索予算契約 |
| データフロー処理設計 | `dataflow-design-guide` | `.github/skills/dataflow-design-guide/SKILL.md` | HVE ADFD / ADFDV の8成果物契約への入口 |
| マイクロサービス設計 | `microservice-design-guide` | `.github/skills/microservice-design-guide/SKILL.md` | HVE サービス定義書の17章・必須フィールド契約 |
| docs-original/ 取り込み | `knowledge-management` | `.github/skills/knowledge-management/SKILL.md` | docs-original/ → D01〜D21 分類・矛盾検出 |
| Markdown 横断クエリ（ローカル） | `markdown-query` | `.github/skills/markdown-query/SKILL.md` | Markdown の所在・抜粋・必要チャンクを小さく取得する調査入口。`.md` 優先、完全 read-only 時の usage log / index / watch 副作用境界は Skill 本文へ委譲 |
| ソースコード横断クエリ（ローカル） | `code-query` | `.github/skills/code-query/SKILL.md` | ソース定義・参照・要件/テスト ID trace の抜粋取得入口。`.md` 以外のソース優先、profile / fidelity / index / usage log 副作用は Skill 本文へ委譲 |
**Workflow 一覧（Issue Template / hve）**
- `ard`, `aas`, `aad-web`, `asdw-web`, `adfd`, `adfdv`, `aag`, `aagd`, `akm`, `adi`, `adoc`

**【出力 / output】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| 大量出力 / 書き込み確認 | `large-output-chunking` | `.github/skills/large-output-chunking/SKILL.md` | terminal output を会話へ全文注入しない扱いと、書き込み読み戻しリトライ |
| docs/ 成果物フォーマット | `docs-output-format` | `.github/skills/docs-output-format/SKILL.md` | HVE docs 成果物の固定見出し・TBD・出典・Mermaid 規約 |

**【ハーネス / harness】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| 敵対的レビュー（marker / label / 明示依頼 / HVE Phase 3） | `adversarial-review` | `.github/skills/adversarial-review/SKILL.md` | HVE の明示発動時だけ行う6軸レビューと PASS/FAIL 出力。通常レビュー・品質確認は `harness-verification-loop` の対象検証とは別に扱う |
| ハーネス: 検証ループ | `harness-verification-loop` | `.github/skills/harness-verification-loop/SKILL.md` | 要求定義から導いた対象コマンドの exit code と実出力による完了判定 |
| ハーネス: 安全ガード | `harness-safety-guard` | `.github/skills/harness-safety-guard/SKILL.md` | HVE 作業時の危険操作レベル判定・停止/確認・白リスト |
| ハーネス: エラーリカバリ | `harness-error-recovery` | `.github/skills/harness-error-recovery/SKILL.md` | HVE エラー時の原因・再試行条件・停止条件の記録 |

**【Azure プラットフォーム / azure-skills】**

`.github/skills/azure-skills/` はリポジトリ同梱 Skill、`~/.agents/skills/` はユーザー環境にインストール済みの場合だけ利用できる外部 Skill を表す。`validate-skill-routing.py` は外部パスが canonical な形式（例: `~/.agents/skills/azure-ai/SKILL.md`）かを検証するが、ユーザーごとに配備状態が異なるためファイル存在確認は行わない。外部 Sub-skill は `~/.agents/skills/` 以下の多階層を許容する。同じ Skill を異なるトリガーの複数行から参照する N:1 routing も許容する。

### Active HVE の JIT ルーティング方針（規範）

以下の一覧は **Skill カタログであり、session に全 Azure Skill を無条件にロードする一覧ではない**。active HVE Step の実行時 routing は `hve/skill_manifest.json` の `required_skills` / `optional_skills` を正本とする。

| 分類 | session routing | 未導入時 |
|---|---|---|
| repository Skill | 既存の repository resolver に従う | 既存の required Skill 契約に従う |
| required external Skill | active Step が指定した正確な directory だけを渡す。`~/.agents/skills` 全体は渡さない | session 作成前に fail-closed |
| optional external Skill | active workflow / Step の候補かつインストール済みの正確な directory だけを JIT 公開する。選定サービス・操作に一致しない candidate は読まない | 設計・read-only・review は Microsoft Learn MCP へfallbackし、Azure write は block |

- repository と external で同名の Skill は repository を優先する。external Skill が未導入でも、ローカル Skill が存在するものとして扱わない。
- `microsoft-foundry` は meta skill であり、HVE は sub-skill routing を複製しない。AAGD `2.3` / `3` では required external Skill とし、repository-pinned `azure` と `microsoft-learn` MCP が connected であることを main turn 前に確認する。
- `azure-prepare` と `azure-deploy` は現行 HVE の script / AC / CI lifecycle と二重化するため active optional candidate に入れない。`azure-validate` はread-only readiness reviewに限り `asdw-web:5.2` / `adfdv:4.2` のactive optional candidateとして許可し、deploy lifecycleまたはAzure writeの迂回経路に使わない。
- 詳細な操作別missing policyは `agent-common-preamble` の「Azure External Skill の JIT ルーティング（必須）」に従う。

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| Deploy後 AC 検証 | `azure-ac-verification` | `.github/skills/azure-ac-verification/SKILL.md` | HVE Deploy 成果物の AC 判定・実在証跡・未検証扱い |
| Azure AI サービス利用 | `azure-ai` | `~/.agents/skills/azure-ai/SKILL.md` | Azure AI Search / Speech / OpenAI / Document Intelligence（外部・任意） |
| AI Gateway 設定 | `azure-aigateway` | `~/.agents/skills/azure-aigateway/SKILL.md` | APIM を AI Gateway として設定・セマンティックキャッシュ・トークン制御（外部・任意） |
| Azure CLI デプロイスクリプト生成 | `azure-cli-deploy-scripts` | `.github/skills/azure-cli-deploy-scripts/SKILL.md` | HVE prep/create/verify スクリプトの冪等性・stage 責務・禁止 fallback |
| クラウド間移行アセスメント | `azure-cloud-migrate` | `~/.agents/skills/azure-cloud-migrate/SKILL.md` | AWS/GCP→Azure 移行アセスメント・コード変換（外部・任意） |
| コンプライアンス監査・セキュリティ評価 | `azure-compliance` | `~/.agents/skills/azure-compliance/SKILL.md` | ベストプラクティス評価・Key Vault 有効期限・リソース設定検証（外部・任意） |
| VM サイズ・VMSS 選定 | `azure-compute` | `~/.agents/skills/azure-compute/SKILL.md` | VM サイズ推奨・VMSS 構成・コスト見積（外部・任意） |
| Cosmos DB を含む Azure データサービス準備 | `azure-prepare` | `~/.agents/skills/azure-prepare/SKILL.md` | データサービスを含む IaC 生成・前提条件整理（外部・任意） |
| Azure コスト最適化 | `azure-cost` | `~/.agents/skills/azure-cost/SKILL.md` | コスト削減分析・孤立リソース検出・VM リサイズ推奨（外部・任意） |
| Azure リソースへのデプロイ実行 | `azure-deploy` | `~/.agents/skills/azure-deploy/SKILL.md` | azd up/deploy・terraform apply・エラーリカバリ付きデプロイ（外部・任意） |
| Azure 本番問題デバッグ | `azure-diagnostics` | `~/.agents/skills/azure-diagnostics/SKILL.md` | AppLens・Azure Monitor・リソースヘルス・安全トリアージ（外部・任意） |
| Copilot SDK アプリ構築・デプロイ | `azure-hosted-copilot-sdk` | `~/.agents/skills/azure-hosted-copilot-sdk/SKILL.md` | GitHub Copilot SDK・BYOM・Azure OpenAI モデル・azd init（外部・任意） |
| ADX KQL クエリ・分析 | `azure-kusto` | `~/.agents/skills/azure-kusto/SKILL.md` | Azure Data Explorer・KQL・ログ分析・時系列データ（外部・任意） |
| Event Hubs / Service Bus SDK トラブルシューティング | `azure-messaging` | `~/.agents/skills/azure-messaging/SKILL.md` | AMQP エラー・接続障害・SDK 設定問題解決（外部・任意） |
| Azure デプロイ準備（IaC 生成） | `azure-prepare` | `~/.agents/skills/azure-prepare/SKILL.md` | Bicep/Terraform・azure.yaml・Dockerfile 生成・マネージド ID（外部・任意） |
| Azure クォータ確認・管理 | `azure-quotas` | `~/.agents/skills/azure-quotas/SKILL.md` | クォータ確認・サービス制限・vCPU 上限・リージョン容量検証（外部・任意） |
| Azure RBAC ロール選定・割り当て | `azure-rbac` | `~/.agents/skills/azure-rbac/SKILL.md` | 最小権限ロール選定・CLI コマンド/Bicep 生成（外部・任意） |
| Azure リージョン選択ポリシー | `azure-region-policy` | `.github/skills/azure-region-policy/SKILL.md` | HVE Azure 成果物の location 優先順位・非対応確認・例外理由記録 |
| Azure リソース一覧・検索・確認 | `azure-resource-lookup` | `~/.agents/skills/azure-resource-lookup/SKILL.md` | 全 Azure リソース検索・Resource Graph（外部・任意） |
| Azure リソース Mermaid 図生成 | `azure-resource-visualizer` | `~/.agents/skills/azure-resource-visualizer/SKILL.md` | リソースグループ分析・依存関係可視化・アーキテクチャ図（外部・任意） |
| Azure Storage 操作 | `azure-storage` | `~/.agents/skills/azure-storage/SKILL.md` | Blob/Queue/Table/Data Lake・アクセス層・ライフサイクル管理（外部・任意） |
| Azure サービス プラン/SKU アップグレード | `azure-upgrade` | `~/.agents/skills/azure-upgrade/SKILL.md` | Consumption→Flex Consumption 等プラン移行・アップグレード自動化（外部・任意） |
| デプロイ前 Azure 設定バリデーション | `azure-validate` | `~/.agents/skills/azure-validate/SKILL.md` | Bicep/Terraform・権限・前提条件のプリフライトチェック（外部・任意） |
| Entra ID アプリ登録・OAuth 認証設定 | `entra-app-registration` | `~/.agents/skills/entra-app-registration/SKILL.md` | アプリ登録・OAuth 2.0・MSAL 統合・サービスプリンシパル生成（外部・任意） |
| Microsoft Foundry Agent デプロイ・評価・管理 | `microsoft-foundry` | `~/.agents/skills/microsoft-foundry/SKILL.md` | Foundry Agent デプロイ・バッチ評価・プロンプト最適化・モデルデプロイ（外部・任意） |

> 💡 各 Azure 系 Skill の詳細は各 SKILL.md を参照。

**【CI/CD / cicd】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| GitHub Actions CI/CD | `github-actions-cicd` | `.github/skills/github-actions-cicd/SKILL.md` | HVE Step 単位 CI/CD の branch / PR 境界・OIDC / secret-less 方針 |

**【テスト / testing】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| TDD RED/GREEN リアリティ | `tdd-red-green-reality` | `.github/skills/tdd-red-green-reality/SKILL.md` | 実出力で RED/GREEN を証明し、HVE 生成テストの実行環境・採用方針（§1.6/§1.7）を保持 |
| TDD GREEN リトライ戦略 | `tdd-green-retry-strategy` | `.github/skills/tdd-green-retry-strategy/SKILL.md` | HVE GREEN 化ループの層別上限・異アプローチ・根本原因/出典記録 |
| 要件適合の実測 | `requirements-conformance-measurement` | `.github/skills/requirements-conformance-measurement/SKILL.md` | HVE deploy 後の既存資産による要件適合・Headroom・証跡レポート |

## Skill Deprecation スキーマ（W6-2: 廃止予定 Skill の標準マーカー）

Skill を非推奨化する場合、その SKILL.md の frontmatter に以下のメタデータを追加すること：

```yaml
---
name: <skill-name>
description: >
  ⚠️ DEPRECATED — <代替 Skill 名> を使用してください。
  （元の description は維持。先頭に DEPRECATED マーカーを追加）
metadata:
  origin: user
  version: <現バージョン>
  deprecation:
    status: deprecated          # values: deprecated | legacy | removed-planned
    since: YYYY-MM-DD            # 非推奨化した日付
    replacement: <skill-name>    # 代替先 Skill 名（無い場合は null）
    removal_planned: YYYY-MM-DD  # 削除予定日（無い場合は null）
    reason: |
      非推奨化の理由を 1-3 行で記述
---
```

**運用ルール**:

1. `deprecation.status` が設定された Skill は **本ルーティング表から削除し**、別途「廃止予定 Skill」セクション（下記）へ移動する。
2. `removal_planned` 経過後、**次マイナーリリースまたは関係者合意** をもってファイルを削除してよい（固定 SLA は設けない）。
3. Skill 参照側（Agent / 他 Skill / copilot-instructions.md）は `replacement` への置換コミットを優先する。
4. `validate-skills.yml` CI で deprecation メタデータの形式を検証する（実装は次サイクル）。

### 廃止予定 Skill の記録（W6-2 時点の履歴）

| Skill | status | since | replacement | removal_planned |
|---|---|---|---|---|
| （該当なし） | - | - | - | - |

> 当時の Phase 0 W7-14 では、参照頻度低 Skill（`svg-renderer`, `appinsights-instrumentation`, `input-file-validation`）を意図的なニッチユースケースとして保持し、「過去 6 ヶ月 0 参照 AND 機能代替可能 AND deprecated 標記でユーザー影響なし」を削除判断の条件としていた。これは当時の履歴であり、現行一覧ではない。2026-09-11 の明示承認による整理で前二者の同梱を終了した。現行の登録は上の routing 表、変更概要は `CHANGELOG.md` を参照する。
