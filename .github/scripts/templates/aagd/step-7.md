{root_ref}

{app_arch_scope_section}
## 目的
AG-CAP-09 の Microsoft 365 / Teams チャネルに従い、デプロイ済み Agent を
Microsoft 365 Copilot Chat / Teams から呼べる状態にするための公開手順と結果を確定する。

## なぜ必要か
Agent を Foundry へデプロイしただけでは、利用者のチャットクライアントからは呼べない。
「実装したが呼び出せない」状態を防ぐため、公開経路の設定と結果を成果物として残す。

## 入力
- `docs/ai-agent-catalog.md`（Agent 一覧）
- `docs/agent/agent-detail-{key}.md`（Section 7.8 `Distribution & Packaging` が正本）
- `src/agent/{key}/`（デプロイ済み実装と `plugin.json`）

## 出力
- `docs/agent/m365-publish-report.md`

## 実施要件
- 公開の可否は **Section 7.8 の `Channels` が正本**。`Microsoft 365` / `Teams` を採っていない場合は
  公開作業を行わず、採らなかった理由と再判定条件をレポートへ残す（判定 `NOT_SELECTED`）。
- 公開範囲（テナント全体 / 共有 / 個人）と、それに伴う管理者承認の要否を記録する。
  テナント全体への公開は管理者承認を伴うため、承認待ちで完了できない場合は `PENDING_APPROVAL` とする。
- **既に公開した版と同じ版を再公開できない**。採番規則と、今回採番した版を記録する。
- **公開メタデータは利用者に見える**。secret・API キー・接続文字列・内部 URL をどのフィールドにも入れない。
- 既存の認可スキームとプロトコル設定を**削除しない**。公開のために追加するのであって、置き換えない。
- API version / SKU / リージョン / リソース名は本 Step で固定値として文書化せず、
  参照した公式ドキュメントの URL と確認日を残す。

## レポートの固定フォーマット（HVE artifact gate が機械検証）
- 公開条件: `Schema-Version` / `Workflow` / `Step` / `Agent` / `Published-At` / `Publish-Scope` / `Auth-Scheme` / `Secret-Redaction`
- 公開表: `| Agent Key | Channel | Publish Scope | App Version | Judgement | Approval | Evidence |`（1 行以上必須、`Agent Key` は `plugin.json` の `name`（fan-out キーの小文字化））
- 判定語彙: `PUBLISHED` / `PENDING_APPROVAL` / `NOT_SELECTED` / `FAILED` の 4 値のみ
- 結論: `- Conclusion:` と `- Rationale:`
- 利用者向け接続手順: `- Consumer-Setup:`

## 禁止事項
- 公開していないのに `PUBLISHED` と書かない。
- 公開メタデータへ secret を書かない。
- 既存の認可設定・プロトコル設定を削除・置換しない。
- リソース名・SKU・API version を推測で確定しない。

{existing_artifact_policy}

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Microsoft Foundry の Microsoft 365 公開手順・Bot Service 設定・Azure サービス / CLI / SDK / SKU を扱うため、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログとレポートへ記録する。
- 利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。

## Custom Agent
`Dev-Agent-M365Publish` を使用

## 依存
- Step.3（AI Agent Deploy）が `aagd:done` であること

## 完了条件
- `docs/agent/m365-publish-report.md` が作成されている
- 公開条件ラベル 8 件がすべて記載されている
- 公開表が 1 行以上あり、各行の判定が 4 値のいずれかである
- `Conclusion` / `Rationale` / `Consumer-Setup` が記載されている
{completion_instruction}{app_id_section}{additional_section}
