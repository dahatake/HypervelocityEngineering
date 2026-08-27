{root_ref}

{app_arch_scope_section}
## 目的
TDD RED フェーズ: テスト仕様書に基づき、デプロイ前に**必ず失敗する**統合テストコードを生成する。

## 入力
- `docs/catalog/app-catalog.md`
- `docs/test-specs/{serviceId}-agentic-retrieval-test-spec.md`（Step.3 出力）

## 出力
- `src/test/integration/agentic-retrieval/` 配下のテストコード一式

## TDD RED の要件
- Knowledge Base 未作成のため、**全テストが失敗**する状態で完了する。
- 「リソースが無いから」という理由で `skip` してはならない。skip は RED ではない。
- テストを実行し、全件失敗することと失敗理由の内訳を `{WORK}work-status.md` に記録する。

## 実装規約
- 認証は `DefaultAzureCredential`。鍵をコードへ書かない。
- エンドポイント / KB 名は環境変数から読む。未設定時は明示的に失敗させ、既定値へフォールバックしない。
- 期待値は設計書のパースで得る。テストコード内へ数値を直書きしない。
- クライアント・資格情報は `finally` で確実に閉じる。
- 1 テスト 1 観点。複数カテゴリを 1 関数に詰め込まない。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-AgenticRetrievalTestCoding` を使用

## 依存
- Step.3（Agentic Retrieval テスト仕様）が `aar:done` であること

## 完了条件
- テスト仕様書の 7 カテゴリすべてに対応するテストが存在する
- 全テストの実行結果が失敗であり、理由がリソース未作成に起因することを確認した
{completion_instruction}{app_id_section}{additional_section}
