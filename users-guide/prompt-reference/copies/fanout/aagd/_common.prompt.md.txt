# AAGD Fan-out per-agent 追加指示

このサブタスクは AAGD の fan-out 子であり、AI Agent `{{key}}` のみ を対象とする。

## 対象
- Step 2.1: `docs/test-specs/{{key}}-test-spec.md`
- Step 2.2: `src/test/agent/{{key}}.Tests/`
- Step 2.3: `src/agent/{{key}}/`
- Step 3: 当該 Agent の Deploy（Azure AI Foundry）

## 必須参照
- `docs/agent/agent-detail-{{key}}.md`
- `docs/agent/agent-application-definition.md`

## 並列実行ルール
- 他 Agent のテスト/コード/デプロイ設定に触らない。


## オーバーエンジニアリング禁止（共通ルール）

- **オーバーエンジニアリングは絶対に禁止**です。
- 指示・要件にない未来予測的な汎用化・抽象化・将来拡張点の先回り追加を行わないこと。
- YAGNI（必要になるまで実装しない原則）に違反する設計・記述を行わないこと。
- 未使用の設定オプション・フラグ・抽象レイヤー・予防的なエラーハンドリングを追加しないこと。
- 禁止事項の優先順位: 捏造禁止 > オーバーエンジニアリング禁止 > 最小差分原則。
