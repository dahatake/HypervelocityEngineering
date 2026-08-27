# AAD-WEB Step 1 (Arch-UI-List) Fan-out per-APP 追加指示

このサブタスクは AAD-WEB Step 1 (`Arch-UI-List`) の fan-out 子であり、
**アプリ `{{key}}` のみ** を対象とする。他の APP は対象外。

## 対象ファイル
- 本タスクの出力: `docs/catalog/screen-catalog-{{key}}.md`
  - 対象アプリ `{{key}}` に属する画面（`{{key}}-S###`）の一覧と画面間遷移図のみを記述する。
  - ファイル冒頭に `# {{key}} 画面カタログ` のような H1 を置く。
  - 他 APP（`APP-XX` for XX != `{{key}}` の数値部）の画面行を **絶対に含めない**。

## 必須参照
- `docs/catalog/app-catalog.md` の `{{key}}` 該当行（自分の APP のメタデータ）
- `docs/catalog/service-catalog.md` のうち `{{key}}` が利用するサービス
- `docs/catalog/data-model.md` / `docs/catalog/domain-analytics.md` の関連エンティティ

## 並列実行ルール
- **他 APP のファイル** (`docs/catalog/screen-catalog-APP-XX.md` for XX != 自分) には絶対に書き込まない。
- 旧形式の集約ファイル `docs/catalog/screen-catalog.md` は **作成しない**。
- 他 APP の画面 (`APP-XX-S###`) を自分のカタログ内に列挙しない。

## 命名規約
- 画面 ID: `{{key}}-S###`（例: `APP-01-S001`）
- 画面ファイル名のベース: `{{key}}-S###-{{画面名 slug}}`

## オーバーエンジニアリング禁止（共通ルール）

- **オーバーエンジニアリングは絶対に禁止**です。
- 指示・要件にない未来予測的な汎用化・抽象化・将来拡張点の先回り追加を行わないこと。
- YAGNI（必要になるまで実装しない原則）に違反する設計・記述を行わないこと。
- 未使用の設定オプション・フラグ・抽象レイヤー・予防的なエラーハンドリングを追加しないこと。
- 禁止事項の優先順位: 捏造禁止 > オーバーエンジニアリング禁止 > 最小差分原則。
