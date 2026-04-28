{root_ref}

{app_arch_scope_section}
## 目的
TDD RED フェーズ: テスト仕様書（`docs/test-specs/{serviceId}-test-spec.md`）からテストコードのみを生成する（APP-ID 指定時はスコープ内のサービスのみ）。
全テストが FAIL（TDD RED 状態）であることを確認してから Step.2.4（GREEN フェーズ）へ進む。

## 入力
- `docs/test-specs/{serviceId}-test-spec.md`（Step.2.3T で生成済みのサービス別テスト仕様書）
- `docs/services/{serviceId}-*.md`（サービス定義書）
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `test/api/{サービス名}.Tests/` 配下に xUnit テストプロジェクト（テストコードのみ）

## Custom Agent
`Dev-Microservice-Azure-ServiceTestCoding` を使用

## TDD RED 確認手順（必須）
1. `cd test/api/{サービス名}.Tests` のように、生成したテストプロジェクトのディレクトリに移動する
2. 移動先ディレクトリで `dotnet build` を実行し、コンパイル成功を確認する
3. 同じディレクトリで `dotnet test` を実行し、そのテストプロジェクト内の全テストが FAIL であることを確認する（RED 状態）
4. RED 確認結果（テスト実行ログ）を Issue コメントに記録する

## 依存
- Step.2.3T（サービス テスト仕様書）が `asdw-web:done` であること

## 完了条件
- `test/api/{サービス名}.Tests/` 配下にテストコードが生成されている
- `dotnet test` で全テストが FAIL（RED 状態）であることが確認されている
{completion_instruction}{app_id_section}{additional_section}