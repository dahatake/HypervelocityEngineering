# ASDW-WEB Fan-out per-element 追加指示

このサブタスクは ASDW-WEB の fan-out 子であり、要素 `{{key}}` のみ を対象とする。

## 対象
- per-service (`SVC-*`): `test/api/{{key}}.Tests/`, `src/api/{{key}}/`
- per-screen (`SC-*`): `test/ui/{{key}}/`, `src/app/{{key}}/`

## 必須参照
- `docs/catalog/service-catalog-matrix.md`
- `docs/services/{{key}}.md` または `docs/screen/{{key}}.md`
- `docs/test-specs/{{key}}-test-spec.md`

## 並列実行ルール
- 他要素のテスト/コードに書き込まない（並列競合回避）。
- `docs/azure/` 配下の追記は join ステップで実施。
