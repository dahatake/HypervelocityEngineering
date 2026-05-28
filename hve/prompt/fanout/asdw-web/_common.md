# ASDW-WEB Fan-out per-element 追加指示

このサブタスクは ASDW-WEB の fan-out 子であり、要素 `{{key}}` のみ を対象とする。

## 対象
- per-service (`SVC-*`): `src/test/api/{{key}}.Tests/`, `src/api/{{key}}/`
- per-screen (`SC-*`): `src/test/ui/{{key}}/`, `src/app/{{key}}/`

## 必須参照
- `docs/catalog/service-catalog-matrix.md`
- `docs/services/{{key}}.md` または `docs/screen/{{key}}.md`
- `docs/test-specs/{{key}}-test-spec.md`

## 並列実行ルール
- 他要素のテスト/コードに書き込まない（並列競合回避）。
- `docs/azure/` 配下の追記は join ステップで実施。


## オーバーエンジニアリング禁止（共通ルール）

- **オーバーエンジニアリングは絶対に禁止**です。
- 指示・要件にない未来予測的な汎用化・抽象化・将来拡張点の先回り追加を行わないこと。
- YAGNI（必要になるまで実装しない原則）に違反する設計・記述を行わないこと。
- 未使用の設定オプション・フラグ・抽象レイヤー・予防的なエラーハンドリングを追加しないこと。
- 禁止事項の優先順位: 捏造禁止 > オーバーエンジニアリング禁止 > 最小差分原則。
