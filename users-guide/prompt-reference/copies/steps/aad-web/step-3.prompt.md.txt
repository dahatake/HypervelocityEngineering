{root_ref}
## 目的
AAD-WEB Step 2.1（画面定義）/ Step 2.2（マイクロサービス定義）/ Step 2.3（TDDテスト仕様）の fan-out 子全件が完了した時点で、画面 ↔ サービス ↔ テスト仕様の整合性を横断レビューし、UI 要件・API 要件・テスト要件の不整合を検出する。

## Custom Agent
`QA-DocConsistency`

## 入力
- `docs/screen/*.md`（Step 2.1 の全 fan-out 子出力）
- `docs/services/*.md`（Step 2.2 の全 fan-out 子出力）
- `docs/test-specs/*-test-spec.md`（Step 2.3 の全 fan-out 子出力）
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/app-catalog.md`

## 出力
- `docs/catalog/screen-service-consistency-report.md`

{existing_artifact_policy}

## 依存
- Step 2.1, 2.2, 2.3 が全て完了していること（AND join）

## レビュー観点
1. **画面 → API 整合性**: 各画面定義の「呼び出すAPI」が `service_catalog_matrix` および `docs/services/*.md` に存在するか
2. **API → 画面整合性**: 各サービス定義が画面側で実際に利用されているか
3. **テスト仕様 ↔ 画面/サービス整合性**: 各 test-spec が対応する画面 or サービスに紐づき、ID 命名規約に従っているか
4. **APP-ID 配分一貫性**: `docs/catalog/app-catalog.md` の各 APP に紐づく画面・サービスがすべての fan-out 子で網羅されているか
5. **データモデル整合性**: 画面 I/O とサービス I/O が `docs/catalog/data-model.md` のエンティティと矛盾しないか

## 完了条件
- `docs/catalog/screen-service-consistency-report.md` が作成されている
- 検出された不整合項目が **明示** されている（捏造禁止: 確認できない項目は「要確認」と記載）
- ステータスサマリ（`OK` / `要修正` / `要確認`）が含まれている
{completion_instruction}{additional_section}
