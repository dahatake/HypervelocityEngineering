# Agentic Retrieval 利用ガイド

← [README](../README.md)

---

## 目次

- [対象読者・前提・次のステップ](#対象読者前提次のステップ)
- [概要](#概要)
- [実装状況](#実装状況)
- [どのワークフローで何が追加されたか](#どのワークフローで何が追加されたか)
- [入力項目（Q1〜Q6）](#入力項目q1q6)
- [Indexer と Push API の選び方](#indexer-と-push-api-の選び方)
- [Microsoft Foundry 連携の考え方](#microsoft-foundry-連携の考え方)
- [生成される成果物](#生成される成果物)
- [用語表](#用語表)
- [注意事項](#注意事項)

---

## 対象読者・前提・次のステップ

- 対象読者: AAD-WEB / ASDW-WEB で Agentic Retrieval を有効化する設計・実装担当者
- 前提: `.github/ISSUE_TEMPLATE/web-app-design.yml` / `web-app-dev.yml` の入力項目を使って起票できること
- 次のステップ:
  - 全体の AI Agent 設計・実装: [08-ai-agent.md](./08-ai-agent.md)
  - プロンプト実例: [prompt-examples.md](./prompt-examples.md)

## 概要

- Agentic Retrieval は、Chat-Bot / AI Agent / RAG / 対話型応答を
  要件に含むサービス向けの拡張機能です。
- 本リポジトリでは、設計フェーズと実装フェーズで役割を分けます。
  - AAD-WEB: 製品非依存の機能要件詳細を作成
  - ASDW-WEB: Azure 実装設計と実 Azure デプロイを実施

## 実装状況

| 要素 | 状態 | 備考 |
| --- | --- | --- |
| 入力項目（Issue Form / CLI ウィザード） | 実装済み | AAD-WEB は Q1・Q3、ASDW-WEB は Q1〜Q6 |
| Custom Agent（Prompt） 3 本 | 実装済み | `Arch-AgenticRetrieval-Detail` / `Dev-Microservice-Azure-AgenticRetrievalDesign` / `...Deploy` |
| ワークフローへの Step 登録 | 実装済み | AAD-WEB `2.6` / ASDW-WEB `2.5` `2.6`（ADR-0001 Phase 5） |
| Knowledge Base / Knowledge Source の作成 | 実装済み | ASDW-WEB `2.6` が担当。実在検証は AC4B-1 / 14 / 15 / 18 |
| 検索契約（AR-CAP-01〜05）の自動検査 | 実装済み | `hve.artifact_validation` が設計・実装・Deploy の各段で検査 |
| GUI の入力項目 | 実装済み | 設定画面の「Agentic Retrieval」セレクタ（3 状態） |
| `enable_agentic_retrieval` による Step 無効化 | 実装済み（CLI / GUI / Cloud） | CLI / GUI は `StepDef.disabled_when_config` で実行対象から除外。Cloud はワークフロー内の条件分岐で Sub-Issue を作成しない |

## どのワークフローで何が追加されたか

### AAD-WEB

- **Step.2.6**（`Arch-AgenticRetrieval-Detail`）が、**製品非依存**の機能要件詳細を作成します。
  - 依存: Step.2.2（マイクロサービス定義書）
  - 出力: `docs/services/{serviceId}-agentic-retrieval-spec.md`（対象サービスのみ）
- Step.2.2（`Arch-Microservice-ServiceDetail`）は委譲を 1 行記録するのみで、spec.md は作成しません。

### ASDW-WEB

- **Step.2.5**（`Dev-Microservice-Azure-AgenticRetrievalDesign`）が Azure 実装設計を作成します。
  - 依存: Step.2.1（追加 Azure サービス選定）
  - 出力: `docs/azure/agentic-retrieval/{serviceId}-design.md`。第 8 章に AR-CAP-01〜05 を記載
  - local 生成 Step であり、local generation checkpoint（Step.4.2）の前に完了します
- **Step.2.6**（`Dev-Microservice-Azure-AgenticRetrievalDeploy`）が Knowledge Source / Knowledge Base を作成します。
  - 依存: Step.2.2（追加 Azure サービス Deploy）、Step.2.5
  - Foundry resource / Project / モデル deployment は Step.2.2 が作成します（本 Step の責務外）

### AAR（Agentic Retrieval Add-on）

既に API / データ資産が動いているアプリへ、**Agentic Retrieval 部分だけ**を後付けするための単独ワークフローです。
AAD-WEB / ASDW-WEB を最初から流し直す必要がありません。

```
hve orchestrate --workflow aar --resource-group <RG> --app-ids APP-001
```

HVE GUI では Step 1 の **AI Agent** カテゴリから `Agentic Retrieval Add-on (AAR)` を選択します。
Cloud では Issue Template **Agentic Retrieval Add-on**（`agentic-retrieval.yml`）から起動します。
`auto-agentic-retrieval` ラベルを dispatcher が検出し、Step.1〜7 を順次実行します。

> **Cloud の機能差**: Cloud の AAR は Step の逐次実行に特化しており、ASDW-WEB 等が持つ
> QA ジョブ・敌対的レビュー・自動マージ・Self-Improve・モデル選択を含みません。
> また Step.7 完了後の Step / Root Issue の自動クローズも行いません（Root に `aar:done` を付与して完了を通知します）。
> これらが必要な場合は CLI / GUI を使ってください。

| Step | Custom Agent | 出力 |
|---|---|---|
| 1 | `Arch-AgenticRetrieval-Detail` | `docs/services/{serviceId}-agentic-retrieval-spec.md` |
| 2 | `Dev-Microservice-Azure-AgenticRetrievalDesign` | `docs/azure/agentic-retrieval/{serviceId}-design.md` |
| 3 | `Arch-TDD-TestSpec` | `docs/test-specs/{serviceId}-agentic-retrieval-test-spec.md` |
| 4 | `Dev-Microservice-Azure-AgenticRetrievalTestCoding` | `src/test/integration/agentic-retrieval/`（TDD RED） |
| 5 | `Dev-Microservice-Azure-AgenticRetrievalDeploy` | `src/infra/azure/create-azure-agentic-retrieval/` |
| 6 | `QA-AgenticRetrievalEval` | `docs/azure/agentic-retrieval/{serviceId}-eval-report.md` |
| 7 | `QA-RequirementsConformanceEval` | `docs/azure/agentic-retrieval/requirements-conformance-report.md` |

- Step 1・2・5 は AAD-WEB / ASDW-WEB と同じ Custom Agent を再利用します。
- **Step.6 が本ワークフロー固有の価値**です。`minimal` と `low` を同一クエリ集合で実測比較し、
  「複数データソース横断」「最小限のクエリ回数」を推測ではなく測定で裏付けます。
  reasoning effort は recall・token・レイテンシのトレードオフであり、測定なしに正しい値は決められません。
- 既存の API / データストアは変更せず、接続設定のみを追加します。

### AAGD（AI Agent）

- Step.3（`Dev-Microservice-Azure-AgentDeploy`）は Knowledge Base / Knowledge Source を**作成せず**、存在と接続を確認します。未作成の場合は blocked として ASDW-WEB Step.2.6 へフィードバックします。

### スキップ条件

- **CLI**: `--enable-agentic-retrieval no`（またはウィザードで「使用しない」）のとき、AAD-WEB `2.6` / ASDW-WEB `2.5` `2.6` は実行対象から除外されます。
  指定できる値は `auto` / `yes` / `no` の 3 つで、CLI フラグがウィザード回答より優先されます。
  除外された Step は DAG 上 skip 扱いになり、依存先としては解決済みとみなされるため、下流 Step（例: `4.2`）は影響を受けません。
- **GUI**: 設定画面の「Agentic Retrieval」で「使用しない」を選ぶと、CLI の `--enable-agentic-retrieval no` と同じ動作になります。既定の「自動判定に従う」ではフラグを付与しません。
- **Cloud（Issue Form）**: 「しない」を選ぶと、Agentic Retrieval の Sub-Issue が**生成されません**。
  Cloud は `python -m hve orchestrate` を起動せず GitHub Issue を作成して Copilot Cloud Agent が処理する方式のため、
  Python 側の `StepDef.disabled_when_config` ではなく、ワークフロー内の条件分岐で Issue 作成を抑止します。
  - ASDW-WEB は Cloud と CLI / GUI で同じ Step 採番です。AAD-WEB Cloud は現行 reusable の採番を確認してください。

    | 役割 | Cloud | CLI / GUI |
    |---|---|---|
    | 機能要件詳細 | AAD-WEB `Step.7.5` | AAD-WEB `2.6` |
    | Azure 実装設計 | ASDW-WEB `Step.2.5` | ASDW-WEB `2.5` |
    | Deploy | ASDW-WEB `Step.2.6` | ASDW-WEB `2.6` |

  - Cloud の依存は registry と同じで、`2.1` → `2.5`、かつ `2.2` + `2.5` → `2.6` です。
    無効時は `2.5` / `2.6` の Issue を生成せず、下流依存では解決済みとして扱います。
- 対象サービスが 0 件の場合、各 Step は「対象なし」を作業ログへ記録して成果物なしで完了します。
- 実行 Step を限定したい場合は CLI の `--steps` で明示指定してください。

<a id="入力項目q1q6"></a>

## 入力項目（Q1〜Q6）

以下は `web-app-design.yml` / `web-app-dev.yml` と `hve/template_engine.py` の項目定義に準拠しています。

| 項目 | 説明 | 既定値 | 適用 |
| --- | --- | --- | --- |
| Agentic Retrieval を使用する | `auto` は自動判定、`yes` は明示有効、`no` は明示無効 | `auto` | AAD / ASDW |
| データソース投入方式 | Indexer（Pull）優先、非対応は Push API、必要に応じて併用 | `Indexer` | ASDW |
| Microsoft Foundry 連携 | Foundry プロジェクト + モデル + MCP 接続を扱う | `する` | AAD / ASDW |
| 想定データソース | 起点となるデータソースを自由記述（1 行 1 件） | 空 | ASDW |
| 既存設計の差分更新 | 既存設計を全上書きせず差分で更新する | OFF | ASDW |
| Foundry モデル SKU フォールバック | `Global 必須` か `Standard 許容` を選択 | `Standard 許容` | ASDW |

## Indexer と Push API の選び方

- Indexer 優先:
  - 標準コネクタで安定運用したい
  - 定期クロールで十分
- Push API を使う:
  - アプリ側イベントで即時反映したい
  - Indexer 非対応ソースを扱う
- 併用する:
  - 基本データは Indexer、速報データは Push API で運用したい

> [!IMPORTANT]
> 対応データソースの最新一覧、具体的 SKU / モデル名 / API バージョンは
> 本ガイドに固定値を記載しません。実行時に Microsoft Learn MCP または
> 公式ドキュメントを参照してください。

## Microsoft Foundry 連携の考え方

- Foundry 連携を ON にすると、Foundry プロジェクト連携と
  MCP 接続設定（例: `azure_ai_search`）の設計・構成対象が有効化されます。
- Remote MCP Server は、外部ツールや知識ベースを
  Agent 実行コンテキストに接続するための構成概念です。
- `Global 必須` は Global SKU 前提で厳格に扱う方針、
  `Standard 許容` は Standard SKU へのフォールバックを許可する方針です。
- 機密情報管理、認証・認可、秘密情報注入は既存 Skill /
  既存運用基盤に委譲してください。

## カスタマイズと完了確認

- 設定の正本は Cloud では `web-app-design.yml` / `web-app-dev.yml` と各 reusable workflow、CLI / GUI では `hve/workflow_registry.py` の `aad-web` / `asdw-web` 定義です。Cloud の Step ID を CLI / GUI の `StepDef.id` として指定しないでください。
- `enable_agentic_retrieval`、データソース投入方式、Foundry 連携、既存設計の差分更新、SKU フォールバックを変更する場合は、既存の Issue Form または CLI / GUI 設定を使います。Prompt や Skill の本文をコピーして設定の代わりにしません。
- 完了時は対象サービスごとの spec、Azure 実装設計、Deploy スクリプト、AC4B-1 / 14 / 15 / 18 の証跡を確認します。対象サービスがない場合は、成果物を捏造せず「対象なし」の作業ログで完了します。
- Cloud で Sub-Issue が生成されない、または CLI / GUI で Step が skip された場合は、まず `enable_agentic_retrieval` の値と対象サービス判定を確認します。Cloud の制御は workflow 条件分岐、CLI / GUI の制御は `disabled_when_config` であり、片方の番号や設定をもう片方へ読み替えません。

## 生成される成果物

- `docs/services/{serviceId}-agentic-retrieval-spec.md`（AAD-WEB Step.2.6）
- `docs/azure/agentic-retrieval/{serviceId}-design.md`（ASDW-WEB Step.2.5）
- `src/infra/azure/create-azure-agentic-retrieval/prep.sh` / `create.sh` / `services/{serviceId}.sh`（ASDW-WEB Step.2.6）
- `work/.../artifacts/cli-evidence.md`
- `work/.../artifacts/created-resources.json`
- `work/.../artifacts/ac-verification.md`

いずれも**対象サービスが存在する場合のみ**生成されます。

## 用語表

| 英語 | 日本語 | 本リポジトリでの意味 |
| --- | --- | --- |
| Knowledge Source | ナレッジソース | 取り込み元データソース／インデックスの論理参照 |
| Knowledge Base | ナレッジベース | Agentic Retrieval が問い合わせる知識基盤 |
| Indexer | インデクサー | Pull 型取り込み |
| Push API | Push API | アプリ側が直接投入する方式 |
| Vector Search | ベクトル検索 | 類似検索 |
| Semantic Search | セマンティック検索 | 意味ベースのランキング |
| MCP | Model Context Protocol | 外部ツール／知識ベース連携のためのプロトコル |
| Foundry | Microsoft Foundry | モデル・エージェント・接続管理基盤 |
| Connection topology | 接続トポロジ | Agent が Knowledge Base へ到達する経路。`direct-kb` / `via-toolbox` |

## Knowledge Base への接続トポロジ

AR-CAP-05 は接続経路によって制約が変わる。設計書には必ず `Connection topology` を宣言する。

| 値 | 接続先 | Tool 制約 |
| --- | --- | --- |
| `direct-kb` | Knowledge Base 自身の MCP エンドポイント | `knowledge_base_retrieve` **のみ**（Foundry Agent Service の制約） |
| `via-toolbox` | Toolbox の MCP エンドポイント | Knowledge Base を含む複数 Tool を同居可。tool search / pin が使える |

`via-toolbox` を選ぶ場合は TB-CAP-01〜05 も併せて宣言する。
AR-CAP 側と TB-CAP 側で `Connection topology` が食い違うと検証で FAIL する。

詳細は [tool-search-guide.md](tool-search-guide.md) を参照。

## 注意事項

- SKU / モデル名 / API バージョン / 対応データソース一覧は固定値を書かない
- Microsoft Learn MCP / 公式 Learn URL を都度参照する
- 入力項目 Q1〜Q6 は収集されるが、現時点では実行に影響しない
- 参照導線としてのみ利用し、ルート `/README.md` は変更していません
