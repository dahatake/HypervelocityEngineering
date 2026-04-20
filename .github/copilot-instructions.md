# Copilot 共通ルール

本ファイルは Copilot が最初に参照する **最上位の強制ルール（エントリーポイント）**。
詳細手順は各 Skill（`.github/skills/*/SKILL.md`）に委譲する。本ファイルが規範ルール、Skills が技術手順リファレンスであり、両者で正式ルールを構成する。なお Skills ファイルに移行過渡期の旧参照が残る場合があるが、本ファイルの記述が常に優先される。

---

## §0 最優先ルール（認知プライミング）

- **出力言語**: 出力は日本語。見出し＋箇条書き中心で簡潔に。
- **出力は最小限**: 長文は `work/` 配下（Skill work-artifacts-layout）。
- **変更は最小差分**: 無関係な整形・一括リファクタ・不要依存追加をしない。
- **捏造禁止**: ID/URL/固有名/数値/事実を根拠なく作らない。不明は `TBD` / `不明（要確認）` と明記する。
- **秘密情報禁止**: 鍵・トークン・個人情報・内部 URL 等を追加・出力しない。
- **推論補完時**: `TBD（推論: {根拠}）` + 「この回答はCopilot推論をしたものです。」と明記する。
- **15分超 or レビュー困難 → 実装開始禁止**: plan.md + subissues.md のみ作成して終了する。
- **plan.md 1-4行目にメタデータ必須**（Skill task-dag-planning §2.1.2）。欠落は CI で自動拒否。
- **最低1つの検証を実施**: テスト/ビルド/静的解析のいずれかを行い、できない場合は理由と代替を明記する。
- **ルート README.md 変更禁止**: `/README.md` を作成・変更してはならない。`README.md` のような裸パス表現は避け、ルート以外の README を指す必要がある場合は `infra/.../README.md` などの明示パスで記載する。
- **質問方針**：質問なしで進められる場合は質問しない。必要な質問は分類項目・重要度（最重要/高/中/低）付きで過不足なく行う。「最重要」「高」は回答を優先的に求め、「中」「低」は既定値で進行可能とする。Issue/PR body に `<!-- auto-context-review: true -->` が記載されている時は、コンテキストが十分な場合でも設計判断・技術選定・スコープの確認を目的として質問する。
- **推論許可**：「推論で進めてください」または「作業を進めてください」の意思表示を以降「**推論許可**」と呼ぶ。
- **書き込み失敗対策**：edit 後に read で空でないことを確認。空なら小チャンク（2,000〜5,000文字）に分割して再試行（最大3回）。
- **work/ および qa/ 書き込みルール（絶対）**：`work/` または `qa/` 配下へのファイル書き込みは Skill `work-artifacts-layout` §4.1 準拠。例外なし。
- **knowledge/ 書き込みルール（絶対）**：`knowledge/` 配下へのファイル書き込みも Skill `work-artifacts-layout` §4.1 準拠（削除→新規作成）。例外なし。
- **knowledge/ 同時更新防止（LOCK）**: `knowledge/` 本体ファイルへ LOCK 情報を埋め込んではならない。LOCK が必要な場合は `work/` 配下のロックファイル、または Issue ラベル等、`knowledge/` の「削除→新規作成」ルールと両立する方式を用いる。他の Agent により対象 D{NN} の LOCK が取得済みであることを検知した場合、後続 Agent は当該 `knowledge/` ファイルを **読み取り専用** とし、書き込みを中止して再実行に回す。
- **original-docs/ 読み取り専用（絶対）**: `original-docs/` 配下のファイルは全 Agent から **読み取り専用**。変更・削除・追記を禁止。

---

## §1 ワークフロー概要

Agent の標準作業フローは以下の 5 フェーズで構成される。各フェーズで参照すべき Skill を明示する。

```
[1. コンテキスト収集]
  - PR 連携: Skill: task-questionnaire（詳細）
  - 非 PR 連携: Skill: task-questionnaire（詳細）
        ↓
[2. 計画（DAG + 見積 + 分割判定）]
  - Skill: task-dag-planning
  - 15分超 → SPLIT_REQUIRED（実装禁止）
        ↓
[3. 実装]
  - work/ 構造: Skill: work-artifacts-layout
  - 大量出力: Skill: large-output-chunking
  - 安全ガード: Skill: harness-safety-guard
        ↓
[4. 検証]
  - Skill: harness-verification-loop（Build/Lint/Test/Security/Diff）
  - エラー発生時: Skill: harness-error-recovery
  - レビュー（ユーザー指定時のみ）: Skill: adversarial-review
        ↓
[5. PR]
  - 元 Issue リンク必須（Fixes #N / Closes #N / Resolves #N）。Issue 番号が不明な場合は `<!-- parent-issue: #N -->` を記載
  - §7 に従い PR description を記載
```

初見のリポジトリの場合は先に **Skill: repo-onboarding-fast** を参照すること。

---

## §2 Skills ルーティングテーブル

「いつ、どの Skill を参照すべきか」のルーティングテーブル。
各 Skill の詳細は `.github/skills/<category>/<name>/SKILL.md` を参照すること。

**【共通 / planning】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| Agent 作業開始（共通） | `agent-common-preamble` | `.github/skills/planning/agent-common-preamble/SKILL.md` | 全 Agent 共通ルール・Skills 参照リスト一元管理 |
| 入力ファイル確認 | `input-file-validation` | `.github/skills/planning/input-file-validation/SKILL.md` | 必読ファイル確認・欠損時処理ルール |
| APP-ID スコープ解決 | `app-scope-resolution` | `.github/skills/planning/app-scope-resolution/SKILL.md` | APP-ID からサービス/画面/エンティティ特定 |
| タスク開始 / 不明点あり | `task-questionnaire` | `.github/skills/planning/task-questionnaire/SKILL.md` | 選択式質問票で要件を明確化 |
| 計画 / DAG / 見積 | `task-dag-planning` | `.github/skills/planning/task-dag-planning/SKILL.md` | 依存関係分解・15分分割判定 |
| work/ 配下の構造設計 | `work-artifacts-layout` | `.github/skills/planning/work-artifacts-layout/SKILL.md` | 入口 README + contracts/artifacts |
| リポジトリ初見 | `repo-onboarding-fast` | `.github/skills/planning/repo-onboarding-fast/SKILL.md` | 高速オンボーディング（構造把握・規約確認） |

**【ドメイン設計 / planning】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| アーキテクチャ候補選定 | `architecture-questionnaire` | `.github/skills/planning/architecture-questionnaire/SKILL.md` | Q1-Q26 質問票・適合度評価 |
| knowledge/ 管理 | `knowledge-management` | `.github/skills/planning/knowledge-management/SKILL.md` | D01〜D21 分類・状態判定・ステータス管理 |
| タスク実行中に業務要件が不明瞭 | `knowledge-lookup` | `.github/skills/planning/knowledge-lookup/SKILL.md` | knowledge/ D01〜D21 の条件付き参照ルール |
| MCP Server 設計 | `mcp-server-design` | `.github/skills/planning/mcp-server-design/SKILL.md` | Skills と MCP Server の責務分離・API設計 |
| バッチ処理設計 | `batch-design-guide` | `.github/skills/planning/batch-design-guide/SKILL.md` | バッチ要件定義〜テスト仕様の統合ガイド |
| マイクロサービス設計 | `microservice-design-guide` | `.github/skills/planning/microservice-design-guide/SKILL.md` | サービス定義書テンプレート |
| original-docs/ 取り込み | `knowledge-management` | `.github/skills/planning/knowledge-management/SKILL.md` | original-docs/ → D01〜D21 分類・矛盾検出 |

**Workflow 一覧（Issue Template / hve）**
- `aas`, `aad`, `asdw`, `abd`, `abdv`, `akm`, `aqod`, `adoc`

**【出力 / output】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| 大量出力 / 50k超 | `large-output-chunking` | `.github/skills/output/large-output-chunking/SKILL.md` | index + part 分割 |
| docs/ 成果物フォーマット | `docs-output-format` | `.github/skills/output/docs-output-format/SKILL.md` | 固定章立て・出典必須・Mermaid erDiagram |
| SVG ダイアグラム生成 | `svg-renderer` | `.github/skills/output/svg-renderer/SKILL.md` | SVGコード生成・画面レンダリング |

**【ハーネス / harness】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| レビュー（ユーザー指定時） | `adversarial-review` | `.github/skills/harness/adversarial-review/SKILL.md` | 5軸 敵対的レビュー |
| ハーネス: 検証ループ | `harness-verification-loop` | `.github/skills/harness/harness-verification-loop/SKILL.md` | Build/Lint/Test/Security/Diff |
| ハーネス: 安全ガード | `harness-safety-guard` | `.github/skills/harness/harness-safety-guard/SKILL.md` | 破壊的操作検出・停止 |
| ハーネス: エラーリカバリ | `harness-error-recovery` | `.github/skills/harness/harness-error-recovery/SKILL.md` | 原因推定・再試行・停止宣言 |

**【Azure プラットフォーム / azure-platform】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| Deploy後 AC 検証 | `azure-ac-verification` | `.github/skills/azure-platform/azure-ac-verification/SKILL.md` | AC 検証フレームワーク・PASS/NEEDS-VERIFICATION/FAIL 判定・Azure CLI フォールバック |
| Azure AI サービス利用 | `azure-ai` | `.github/skills/azure-platform/azure-ai/SKILL.md` | Azure AI Search / Speech / OpenAI / Document Intelligence |
| AI Gateway 設定 | `azure-aigateway` | `.github/skills/azure-platform/azure-aigateway/SKILL.md` | APIM を AI Gateway として設定・セマンティックキャッシュ・トークン制御 |
| Azure CLI デプロイスクリプト生成 | `azure-cli-deploy-scripts` | `.github/skills/azure-platform/azure-cli-deploy-scripts/SKILL.md` | prep/create/verify 3点セット・冪等性パターン |
| クラウド間移行アセスメント | `azure-cloud-migrate` | `.github/skills/azure-platform/azure-cloud-migrate/SKILL.md` | AWS/GCP→Azure 移行アセスメント・コード変換 |
| コンプライアンス監査・セキュリティ評価 | `azure-compliance` | `.github/skills/azure-platform/azure-compliance/SKILL.md` | ベストプラクティス評価・Key Vault 有効期限・リソース設定検証 |
| VM サイズ・VMSS 選定 | `azure-compute` | `.github/skills/azure-platform/azure-compute/SKILL.md` | VM サイズ推奨・VMSS 構成・コスト見積 |
| Cosmos DB NoSQL 操作 | `azure-cosmosdb` | `.github/skills/azure-platform/azure-cosmosdb/SKILL.md` | DefaultAzureCredential・azure-cosmos SDK・CRUD/COUNT・サンプルデータ登録 |
| Azure コスト最適化 | `azure-cost-optimization` | `.github/skills/azure-platform/azure-cost-optimization/SKILL.md` | コスト削減分析・孤立リソース検出・VM リサイズ推奨 |
| Azure リソースへのデプロイ実行 | `azure-deploy` | `.github/skills/azure-platform/azure-deploy/SKILL.md` | azd up / azd deploy / terraform apply・エラーリカバリ付きデプロイ実行 |
| Azure 本番問題デバッグ | `azure-diagnostics` | `.github/skills/azure-platform/azure-diagnostics/SKILL.md` | AppLens・Azure Monitor・リソースヘルス・安全トリアージ |
| Copilot SDK アプリ構築・デプロイ | `azure-hosted-copilot-sdk` | `.github/skills/azure-platform/azure-hosted-copilot-sdk/SKILL.md` | GitHub Copilot SDK・BYOM・Azure OpenAI モデル・azd init |
| ADX KQL クエリ・分析 | `azure-kusto` | `.github/skills/azure-platform/azure-kusto/SKILL.md` | Azure Data Explorer・KQL・ログ分析・時系列データ |
| Event Hubs / Service Bus SDK トラブルシューティング | `azure-messaging` | `.github/skills/azure-platform/azure-messaging/SKILL.md` | AMQP エラー・接続障害・SDK 設定問題解決 |
| Azure デプロイ準備（IaC 生成） | `azure-prepare` | `.github/skills/azure-platform/azure-prepare/SKILL.md` | Bicep/Terraform・azure.yaml・Dockerfile 生成・マネージド ID |
| Azure クォータ確認・管理 | `azure-quotas` | `.github/skills/azure-platform/azure-quotas/SKILL.md` | クォータ確認・サービス制限・vCPU 上限・リージョン容量検証 |
| Azure RBAC ロール選定・割り当て | `azure-rbac` | `.github/skills/azure-platform/azure-rbac/SKILL.md` | 最小権限ロール選定・CLI コマンド/Bicep 生成 |
| Azure リージョン選択ポリシー | `azure-region-policy` | `.github/skills/azure-platform/azure-region-policy/SKILL.md` | Japan East 既定・フォールバック順序・SWA 例外・理由記録義務 |
| Azure リソース一覧・検索・確認 | `azure-resource-lookup` | `.github/skills/azure-platform/azure-resource-lookup/SKILL.md` | VM/Storage/WebApp/ContainerApps 等全リソース検索・Resource Graph |
| Azure リソース Mermaid 図生成 | `azure-resource-visualizer` | `.github/skills/azure-platform/azure-resource-visualizer/SKILL.md` | リソースグループ分析・依存関係可視化・アーキテクチャ図 |
| Azure Storage 操作 | `azure-storage` | `.github/skills/azure-platform/azure-storage/SKILL.md` | Blob/FileShare/Queue/Table/Data Lake・アクセス層・ライフサイクル管理 |
| Azure サービス プラン/SKU アップグレード | `azure-upgrade` | `.github/skills/azure-platform/azure-upgrade/SKILL.md` | Consumption→Flex Consumption 等プラン移行・アップグレード自動化 |
| デプロイ前 Azure 設定バリデーション | `azure-validate` | `.github/skills/azure-platform/azure-validate/SKILL.md` | Bicep/Terraform・権限・前提条件のプリフライトチェック |
| Entra ID アプリ登録・OAuth 認証設定 | `entra-app-registration` | `.github/skills/azure-platform/entra-app-registration/SKILL.md` | アプリ登録・OAuth 2.0・MSAL 統合・サービスプリンシパル生成 |
| Microsoft Foundry Agent デプロイ・評価・管理 | `microsoft-foundry` | `.github/skills/azure-platform/microsoft-foundry/SKILL.md` | Foundry Agent デプロイ・バッチ評価・プロンプト最適化・モデルデプロイ |

> 💡 各 Azure 系 Skill の詳細は各 SKILL.md を参照。

**【CI/CD / cicd】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| GitHub Actions CI/CD | `github-actions-cicd` | `.github/skills/cicd/github-actions-cicd/SKILL.md` | OIDC認証・workflow_dispatch・Copilot push制約対応・シークレット管理・デプロイ保護 |

**【オブザーバビリティ / observability】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| Application Insights 計装 | `appinsights-instrumentation` | `.github/skills/observability/appinsights-instrumentation/SKILL.md` | App Insights SDK・自動/手動計装ガイド |

**【テスト / testing】**

| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| テスト戦略テンプレート | `test-strategy-template` | `.github/skills/testing/test-strategy-template/SKILL.md` | テストピラミッド・テストダブル選択基準・テストデータ戦略・カバレッジ方針 |

---

## §3 コアルール参照テーブル

本ファイルの §0 に記載されたコアルールと、対応する Skill の対応表。

| ルール | 詳細を持つ Skill |
|---|---|
| コンテキスト収集（PR連携 / 非PR連携） | `task-questionnaire` |
| plan.md メタデータ・分割判定 | `task-dag-planning` |
| 成果物パス・work/qa/ 構造 | `work-artifacts-layout` |
| 巨大出力分割 | `large-output-chunking` |
| 敵対的レビュー | `adversarial-review` |
| 検証ループ (Build/Lint/Test/Security/Diff) | `harness-verification-loop` |
| 安全ガード (破壊的操作検出) | `harness-safety-guard` |
| エラーリカバリ (3要素出力) | `harness-error-recovery` |
| リポジトリ初見オンボーディング | `repo-onboarding-fast` |

---

## §4 アプリケーション粒度の参照ルール（`docs/catalog/app-catalog.md` + §4）

- 設計エージェントは `docs/catalog/app-catalog.md` の「アプリ一覧（アーキタイプ）概要」を参照し、成果物に APP-ID との紐付けを行う。
- APP × サービス / APP × エンティティ: N:N 関係（カンマ区切りで記載、例: `APP-01, APP-03`）
- APP × 画面: 1:1 関係（1画面は1つの APP-ID に所属）
- 1つの APP のみ利用のサービス/エンティティ/画面 → 成果物ファイルのアプリケーション単位での分割を検討する。
- 複数 APP で共有されるものは統一ファイルのまま「利用APP」列/項目をカンマ区切りで記載する。

### コード→要件→ADR トレーサビリティ

生成コードには、以下のいずれかの方法で要件・ルール・ADR への逆引きを埋め込む:

1. **コードコメント**: `// Ref: D06-rule-{ID}, knowledge/D06-*.md §2.1`
2. **PR description**: 「関連要件」セクションに D クラス + ルールID + ADR番号を記載
3. **テストコード**: テスト名またはテストコメントに `D{NN}` と要件IDを含める

---

## §5 Custom Agent との関係

Custom Agent（`.github/agents/*.agent.md`）は、本ファイルのルールを継承し、固有の追加ルールのみを記載する。

**優先順位（高 → 低）**:
1. **本ファイル（copilot-instructions.md）**（最優先・常に適用）
2. **Custom Agent のジョブ定義**（リポジトリ固有の方針）
3. **Skills**（技術リファレンス）

> 本ファイルの記述と Custom Agent の記述が矛盾する場合は本ファイルが優先される。
> SKILL.md と Custom Agent の記述が矛盾する場合は Custom Agent が優先される。
> `agent-common-preamble` Skill の共通ルールは、Agent 側で明示的にオーバーライドしない限り適用される（デフォルト継承モデル）。

**Skills 参照ルール（Custom Agent 向け）**:
- `.github/skills/` 配下の SKILL.md は、技術リファレンス（手順・コマンド・トラブルシューティング）を提供する。
- Custom Agent は、作業開始時に `agent-common-preamble` Skill を参照し、共通ルールを確認すること。
- Custom Agent 固有の追加 Skills は `## Agent 固有の Skills 依存` セクションに明示する。
- SKILL.md の情報を採用しない場合は、Custom Agent 側でその理由を明記すること（Non-goals 等で）。

**original-docs/ に関するルール（全 Agent 必須）**:
- `original-docs/` 配下は全 Agent から読み取り専用（変更・削除・追記禁止）
- `original-docs/` のファイルを knowledge/ に取り込む作業は `KnowledgeManager` Agent が担当
- 他の Agent は、ユースケースに応じて以下のいずれかの参照方式を選択できる:
  - **直接参照**: `original-docs/` を直接読み取る（横断分析・質問票作成・早期フィードバック等で有効）
  - **knowledge/ 経由参照**: `KnowledgeManager` が生成した `knowledge/D01〜D21-*.md` を参照
  - **ハイブリッド**: 両方を参照
- どの参照方式を採用したかは Agent 仕様の `## 入力` セクションに明記すること

---

## §6 直列/並列の判断と共有（衝突を避ける）

直列（同一Subに寄せる）：
- 同じファイル/同じ公開I/F（API/スキーマ/設定キー）を高確率で触る
- 移行/互換/後戻り困難な変更
- 仕様確定→実装の依存が強い

並列（別Sub/別PRに分離）：
- 対象ディレクトリ/サービスが分離している
- 追記中心で衝突しにくい（例：モジュール別ドキュメント）
- テスト追加が独立

共有方法（必須）：
- 共有すべき前提（契約/一覧/決定事項）は **PRコメントではなくファイル** に残す（後続が確実に読める形）。

---

## §7 PRに必ず書く（短くてよい）

- **元 Issue リンク（必須）**: PR の起点となった Issue 番号を `Fixes #N` / `Closes #N` / `Resolves #N` で記載する（分割モード・PROCEED モード問わず全 PR に適用。Issue 番号が不明な場合は `<!-- parent-issue: #N -->` を記載）。
- **PR body 更新時の保持義務（必須）**: PR body を更新する場合、既存の `Fixes #N` / `Closes #N` / `Resolves #N` および `<!-- parent-issue: #N -->` を **絶対に削除しないこと**。PR body を全置換する場合は、元の body からこれらを抽出して新しい body の先頭に再挿入すること。
- 目的 / 変更点 / 影響範囲 / 検証結果 / 既知の制約 / 次にやるSub（残作業）

---

## §8 出力品質 (Observation Quality)

全 Agent の成果物に以下4要素を含める。

```
## 成果物サマリー
- status:       [成功/失敗/部分完了]
- summary:      [何を行い何が変わったか（3行以内）]
- next_actions: [後続で必要な作業（あれば Agent 名を推奨付き）]
- artifacts:    [生成/変更したファイルの一覧]
```

**§7 PR description との関係**:
- §7 の「目的/変更点/影響範囲/検証結果/既知の制約/次にやるSub」はそのまま維持する
- §8 は §7 の構造化補完版。PR description 内に統合して記載する

---

## §9 差分品質評価 (Diff Quality Assessment)

PR 提出前に以下を実施する。

1. `git diff --stat` で変更サマリーを取得する
2. 変更ファイルが Issue/AC の対象スコープ内か確認する
3. 無関係な変更（整形のみ、コメント追加のみ等）が含まれていないか確認する
4. 結果を `work-artifacts-layout` Skill で定義される作業ディレクトリ直下の `verification-report.md`（例: `work/Issue<識別子>/verification-report.md`）の Diff セクションに記録する

---

## §10 例外（下位ディレクトリ固有ルールを置く場合）

- 置くのは「そのディレクトリ固有の追加ルール」だけ。
- 必ず「ルート copilot-instructions.md を継承し、追加/上書き点のみ記載」と明記する。
