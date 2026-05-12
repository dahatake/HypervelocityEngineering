# AAGD Fan-out per-agent 追加指示

このサブタスクは AAGD の fan-out 子であり、AI Agent `{{key}}` のみ を対象とする。

## 対象
- Step 2.1: `docs/test-specs/{{key}}-test-spec.md`
- Step 2.2: `test/agent/{{key}}.Tests/`
- Step 2.3: `src/agent/{{key}}/`
- Step 3: 当該 Agent の Deploy（Azure AI Foundry）

## 必須参照
- `docs/agent/agent-detail-{{key}}.md`
- `docs/agent/agent-application-definition.md`

## 並列実行ルール
- 他 Agent のテスト/コード/デプロイ設定に触らない。
