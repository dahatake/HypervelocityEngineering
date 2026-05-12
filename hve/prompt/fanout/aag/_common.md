# AAG Fan-out per-agent 追加指示

このサブタスクは AAG Step 2 / 3 の fan-out 子であり、AI Agent `{{key}}` のみ を対象とする。

## 対象
- `docs/agent/agent-detail-{{key}}.md`

## 必須参照
- `docs/agent/agent-application-definition.md` の `{{key}}` 該当行
- `docs/agent/agent-architecture.md`（Step 3 のみ）

## 並列実行ルール
- 他 Agent のファイルに書き込まない。
- `docs/ai-agent-catalog.md` への追記は join ステップで実施。
