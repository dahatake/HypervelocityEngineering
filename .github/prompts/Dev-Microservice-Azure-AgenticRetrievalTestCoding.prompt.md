# Dev-Microservice-Azure-AgenticRetrievalTestCoding

Agentic Retrieval（Foundry IQ / Azure AI Search Knowledge Base）の実装設計書から、
デプロイ前に必ず失敗する統合テスト（TDD RED）を生成する。

## Skills 依存

- `agentic-retrieval-contract`（必須） — AR-CAP-01〜05 の契約定義。テストが検証すべき項目の正本。
- `agent-common-preamble`（共通ルール）

## 入力

| パス | 必須 | 用途 |
|---|---|---|
| `docs/test-specs/{serviceId}-agentic-retrieval-test-spec.md` | 必須 | テスト観点の正本 |
| `docs/azure/agentic-retrieval/{serviceId}-design.md` | 必須 | AR-CAP-01〜05 の確定値 |
| `docs/catalog/app-catalog.md` | 推奨 | APP-ID スコープ解決 |

入力が欠落している場合は Skill `input-file-validation` に従い、TBD を明記して続行する。

## 出力

- `src/test/integration/agentic-retrieval/` 配下のテストコード一式

## Non-goals

- Knowledge Base / Knowledge Source の**作成**（Step 5 の責務）
- 検索インデックス自体のチューニング
- テストを通すための実装コードの記述

## 1. TDD RED の定義

本 Step は **必ず全テストが失敗する状態** で完了する。

- Knowledge Base はまだ存在しないため、接続時点で失敗するのが正しい。
- 「まだリソースが無いから」という理由で `skip` してはならない。skip は RED ではない。
- 失敗理由が「接続不可」に集約されていることを実行ログで確認し、作業ログへ記録する。

## 2. 必須テストカテゴリ

設計書の AR-CAP 契約値を**ハードコードせず**、設計書から読み取った値と実リソースを突き合わせること。

| # | カテゴリ | 検証内容 | 対応契約 |
|---|---|---|---|
| 1 | Knowledge Base 実在 | 設計書の KB 名で取得でき、`retrievalReasoningEffort` が設計値と一致する | AR-CAP-01 |
| 2 | Knowledge Source 網羅 | 設計書の Knowledge Source が過不足なく登録されている | AR-CAP-02 |
| 3 | **横断 retrieve** | 1 リクエストで全 Knowledge Source に到達し、各 KS 由来の結果が最低 1 件返る | AR-CAP-02 |
| 4 | **クエリ回数** | 1 回の retrieve 呼び出しで完結し、クライアント側で KS ごとに呼び分けていない | AR-CAP-03 |
| 5 | 予算遵守 | 応答が設計書の token 予算・`maxRuntimeInSeconds` を超えない | AR-CAP-03 |
| 6 | 証跡 | 設計書が references / activity log を有効と宣言している場合、実応答に含まれる | AR-CAP-04 |
| 7 | MCP 公開 | Foundry Agent Service 経由の場合、`knowledge_base_retrieve` のみが解決できる | AR-CAP-05 |

### 2.1 カテゴリ 3・4 の重要性

ユーザー要件「複数のデータソースを横断」「最小限のクエリ回数」を**実測で裏付ける唯一のテスト**である。
省略・簡略化してはならない。

- カテゴリ 3 は、返却された `references` または activity log の Knowledge Source 名を集合として取り出し、
  設計書の Knowledge Source 集合と比較する。
- カテゴリ 4 は、テスト内で retrieve を呼ぶ回数を計測し、`1` であることを assert する。
  KS ごとにループして呼ぶ実装は、この時点で不合格とする。

## 3. 実装規約

- 認証は `DefaultAzureCredential` を用い、鍵をコードへ書かない。
- エンドポイント・KB 名は環境変数（例: `SEARCH_ENDPOINT` / `KNOWLEDGE_BASE_NAME`）から読む。
  未設定時は明示的に失敗させる（既定値へフォールバックしない）。
- 期待値は設計書のパースで得る。テストコード内へ数値を直書きしない。
- クライアント・資格情報は `finally` で確実に閉じる。
- 1 テスト 1 観点。複数カテゴリを 1 関数へ詰め込まない。

## 4. 作業ログ

`{WORK}work-status.md` へ以下を記録する。

- 対象サービス ID の一覧（0 件の場合は「対象なし」と明記して成果物なしで完了）
- 生成したテストファイルとカテゴリの対応表
- RED 実行結果（全件失敗の確認、失敗理由の内訳）

## 5. 完了条件

- 上記 7 カテゴリすべてに対応するテストが存在する
- テストを実行し、**全件失敗**することを確認した
- 失敗理由がリソース未作成に起因することを確認した
- 期待値が設計書由来であり、ハードコードされていない
