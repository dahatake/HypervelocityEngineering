{root_ref}
## 目的
TDD RED フェーズ: Agent テスト仕様書（`docs/test-specs/{agentId}-test-spec.md`）からテストコードのみを生成する（APP-ID 指定時はスコープ内の Agent のみ）。
全テストが FAIL（TDD RED 状態）であることを確認してから Step.2.7（GREEN フェーズ）へ進む。

## 入力
- `docs/test-specs/{agentId}-test-spec.md`（Step.2.7T で生成済みの Agent テスト仕様書）
- `docs/agent/agent-detail-*.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `test/agent/{AgentName}.Tests/` 配下にテストプロジェクト（テストコードのみ）

## Custom Agent
`Dev-Microservice-Azure-AgentTestCoding` を使用

## TDD RED 確認手順（必須）
1. テストを実行し、全テストが FAIL であることを確認する（RED 状態）
2. RED 確認結果（テスト実行ログ）を Issue コメントに記録する

## 依存
- Step.2.7T（AI Agent テスト仕様書）が `asdw:done` であること

## 完了条件
- `test/agent/{AgentName}.Tests/` 配下にテストコードが生成されている
- テストで全テストが FAIL（RED 状態）であることが確認されている
- 完了時に自身に `asdw:done` ラベルを付与すること{app_id_section}{additional_section}