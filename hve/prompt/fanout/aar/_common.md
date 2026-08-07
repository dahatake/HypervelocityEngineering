# AAR Fan-out per-element 追加指示

このサブタスクは AAR（Agentic Retrieval Add-on）の fan-out 子であり、サービス `{{key}}` のみを対象とする。

## 対象
- 機能要件詳細: `docs/services/{{key}}-agentic-retrieval-spec.md`
- Azure 実装設計: `docs/azure/agentic-retrieval/{{key}}-design.md`
- テスト仕様: `docs/test-specs/{{key}}-agentic-retrieval-test-spec.md`
- 実測評価: `docs/azure/agentic-retrieval/{{key}}-eval-report.md`

## 適用外サービスの扱い（重要）

`{{key}}` が Agentic Retrieval の適用対象でない場合も、**成果物ファイルは必ず作成する**。

- 本文に `## 適用判定` セクションを設け、`適用外` と明記する。
- 適用外と判断した根拠（機能要件に検索・RAG・Chat-Bot 要素が無い等）を 1〜3 行で書く。
- 適用外の場合、AR-CAP-01〜05 の記載は不要。

ファイルを作らずに終了してはならない。作らないと後続 Step が判断根拠を失い、
「未処理」と「適用外」を区別できなくなる。

## 必須参照
- `docs/catalog/service-catalog.md`
- `docs/services/{{key}}-*-description.md`

## 並列実行ルール
- 自身の対象 `{{key}}` 以外には書き込まない。
- 共通カタログ（`docs/azure/azure-services-additional.md` 等）への追記は join ステップ側で実施。

## オーバーエンジニアリング禁止（共通ルール）

- **オーバーエンジニアリングは絶対に禁止**です。
- 指示・要件にない未来予測的な汎用化・抽象化・将来拡張点の先回り追加を行わないこと。
- YAGNI（必要になるまで実装しない原則）に違反する設計・記述を行わないこと。
- 未使用の設定オプション・フラグ・抽象レイヤー・予防的なエラーハンドリングを追加しないこと。
- 禁止事項の優先順位: 捏造禁止 > オーバーエンジニアリング禁止 > 最小差分原則。
