<!-- DEPRECATED: このテンプレートは templates/asdw-web/step-2.4.md に移動しました。 -->
{root_ref}
## 目的
TDD GREEN フェーズ: テスト仕様書 (`docs/test-specs/`) を参照しながらテストファーストで実装する。
マイクロサービス定義書から対象サービスの Azure Functions を実装し、テスト/最小ドキュメント/設定雛形まで揃える（APP-ID 指定時はスコープ内のサービスのみ）。

## 入力
- `docs/services/{serviceId}-*.md`（サービス定義書）
- Azure Functions プログラミング言語: `C#（最新版のAzure Functionsでサポートされているもの）`
- `docs/catalog/service-catalog.md`
- `docs/catalog/data-model.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/azure/azure-services-*.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- TDD テストコード（RED状態）: `test/api/{サービス名}.Tests/`（Step.2.3TC の成果物）
- テスト仕様書: `docs/test-specs/{serviceId}-test-spec.md`（Step.2.3T で生成済み。TDD RED フェーズのテストケース定義）

## 出力
- `src/api/{サービスID}-{サービス名}/` 配下に Azure Functions を作成/更新
- （任意推奨）`test/api/smoke-ui/index.html`

## TDD GREEN フロー（反復）
1. `dotnet test` で全テスト FAIL（RED 状態）を確認する
2. テストケースを GREEN にするための最小実装を作成する
3. `dotnet test` を実行する
4. 全テスト PASS なら REFACTOR へ進む。FAIL があれば実装を修正して手順3に戻る
5. 最大 5 回反復する
6. 5 回で全 PASS にならない場合: `asdw:blocked` ラベルを付与し、未 PASS テスト一覧を Issue コメントで報告する

## テストコード保護ルール
- GREEN フェーズでは実装コードのみを修正する（`test/api/` のテストコードは原則変更禁止）

## Custom Agent
`Dev-Microservice-Azure-ServiceCoding-AzureFunctions` を使用

## 依存
- Step.2.3TC（サービス テストコード生成）が `asdw:done` であること

## 完了条件
- `src/api/` 配下に Azure Functions が実装されている
- `dotnet test` の全テストが PASS であること（TDD GREEN 確認）
{completion_instruction}{app_id_section}{additional_section}