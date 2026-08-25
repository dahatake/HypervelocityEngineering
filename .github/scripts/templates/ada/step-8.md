{root_ref}
## 目的
AI Agent が読む可能性のある非構造化データ資産を棚卸しし、資産ごとの検索経路候補を根拠付きで記録する。AG-CAP-03（Knowledge & Structured Data Routing）と AG-CAP-10（Evaluation & Route Right-sizing）の入力となる。

## 入力
- `docs/catalog/use-case-catalog.md`（必須）
- `docs/catalog/data-catalog.md`（必須）
- `docs/catalog/app-catalog.md`（必須）
- `docs/catalog/design-doc-catalog.md`（存在すれば参照。ADI 実行済みの場合）
- `docs/original-design-doc-ingest/*/card.md`（存在すれば参照）
- `docs/catalog/persona-catalog.md`（存在すれば参照）

## 出力
- `docs/catalog/unstructured-data-catalog.md`

{existing_artifact_policy}

## Custom Agent
`Arch-AgentDataAsset` を使用

## 依存
- Step.5（データカタログ作成）が `ada:done` であること

## 検索経路候補の判定
📋 Skill `ai-agent-capability-contract` の `references/search-routing.md` §4.1（コスト階段）〜§4.3 に従い、資産ごとに **第1候補と、それより下の段の第2候補** を記録すること。採用の確定は AAG の AG-CAP-03 が行うため、本 Step では候補までとする。

## 完了条件
- `docs/catalog/unstructured-data-catalog.md` が作成され、資産一覧と経路候補の 2 表が埋まっている
{completion_instruction}{additional_section}
