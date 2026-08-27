{root_ref}

{app_arch_scope_section}
## 目的
Step.2 の Azure 実装設計書に基づき、Agentic Retrieval の統合テスト仕様書を作成する（TDD RED の前段）。

## 入力
- `docs/catalog/app-catalog.md`
- `docs/azure/agentic-retrieval/{serviceId}-design.md`（Step.2 出力）

## 出力
- `docs/test-specs/{serviceId}-agentic-retrieval-test-spec.md`

## 必須テストカテゴリ（全 7 種を含めること）
Skill `agentic-retrieval-contract` の AR-CAP-01〜05 に対応させる。

1. **Knowledge Base 実在** — 設計値の KB 名で取得でき `retrievalReasoningEffort` が一致（AR-CAP-01）
2. **Knowledge Source 網羅** — 設計書の Knowledge Source が過不足なく登録済み（AR-CAP-02）
3. **横断 retrieve** — 1 リクエストで全 Knowledge Source に到達し、各 KS 由来の結果が最低 1 件返る（AR-CAP-02）
4. **クエリ回数** — 1 回の retrieve で完結し、KS ごとに呼び分けていない（AR-CAP-03）
5. **予算遵守** — token 予算 / `maxRuntimeInSeconds` を超えない（AR-CAP-03）
6. **証跡** — references / activity log の有効宣言が実応答と一致（AR-CAP-04）
7. **MCP 公開** — Foundry Agent Service 経由なら `knowledge_base_retrieve` のみ解決可（AR-CAP-05）

カテゴリ 3・4 は「複数データソース横断」「最小限のクエリ回数」という要件を実測で裏付ける中核であり、省略・簡略化しない。

## 期待値の扱い
- 期待値は設計書から読み取る。テスト仕様書へ数値を直書きせず、参照元の章・項目名を明記する。
- 設計書に無い値を推測で補わない。不明は `TBD（要確認）` と記す。

{existing_artifact_policy}

## Custom Agent
`Arch-TDD-TestSpec` を使用

## 依存
- Step.2（Agentic Retrieval Azure 実装設計）が `aar:done` であること

## 完了条件
- 対象サービスごとにテスト仕様書が作成されている
- 上記 7 カテゴリすべてが含まれている
{completion_instruction}{app_id_section}{additional_section}
