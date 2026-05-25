# AAD-WEB Fan-out per-element 追加指示

このサブタスクは AAD-WEB の fan-out 子であり、要素 `{{key}}` のみ を対象とする。

## 対象
- 画面の場合 (`SC-*`): `docs/screen/{{key}}.md`
- サービスの場合 (`SVC-*`): `docs/services/{{key}}.md`
- テスト仕様の場合: `docs/test-specs/{{key}}-test-spec.md`

## 必須参照
- `docs/catalog/screen-catalog.md` / `docs/catalog/service-catalog.md` / `docs/catalog/service-catalog-matrix.md`
- 関連 D 文書（`docs/agent/`, `knowledge/D11`, `knowledge/D09` 等）

## 並列実行ルール
- 自身の対象 `{{key}}` 以外には書き込まない。
- 共通カタログ（screen-catalog.md / service-catalog.md）への追記は join ステップ側で実施。


## オーバーエンジニアリング禁止（共通ルール）

- **オーバーエンジニアリングは絶対に禁止**です。
- 指示・要件にない未来予測的な汎用化・抽象化・将来拡張点の先回り追加を行わないこと。
- YAGNI（必要になるまで実装しない原則）に違反する設計・記述を行わないこと。
- 未使用の設定オプション・フラグ・抽象レイヤー・予防的なエラーハンドリングを追加しないこと。
- 禁止事項の優先順位: 捏造禁止 > オーバーエンジニアリング禁止 > 最小差分原則。
