# subissues.md テンプレート

> ⚠️ **コピペ後に必ず全プレースホルダー `{REPLACE_ME_...}` を書き換えること（CI バリデーション必須）**
> `REPLACE_ME` の残存は運用上禁止（少なくとも `title` は CI で空値検知により拒否される）。
>
> ## 必須ルール
>
> - `<!-- parent_issue: ... -->` はファイル先頭に **1つだけ** 記載（必須）。作業対象Issueの番号を記載する。**推論・捏造禁止**。Issue 番号が不明な場合は `TBD（要確認）` と記載し、作業を停止すること。
> - `<!-- subissue -->` は各ブロックの開始マーカー（必須区切り）。`---`（水平線）は可読性向上のオプション。
> - `<!-- title: ... -->` は必須（空値禁止。`REPLACE_ME` 等のプレースホルダーも空値扱い）
> - `<!-- labels: ... -->` はカンマ区切り（任意。親Issueのラベルを引き継ぐ場合に記載）
> - `<!-- custom_agent: ... -->` は Copilot アサイン時の Custom Agent 名。**省略すると Copilot がアサインされない。** 親Issueの `## Custom Agent` セクションに記載されている Agent 名を記載すること。
> - `<!-- depends_on: ... -->` は依存先 Sub のブロック番号（= `<!-- subissue -->` マーカーの出現順、1始まり）。カンマ区切り。**省略 = ルートノード = Copilot 即時アサイン**。plan.md の DAG で依存がある場合は必ず記載すること。
> - Sub ブロック数は `plan.md` の `subissues_count` と一致させる

<!-- parent_issue: {REPLACE_ME_PARENT_ISSUE_NUMBER} -->

<!-- subissue -->
<!-- title: {REPLACE_ME_SUB_001_TITLE} -->
<!-- labels: {REPLACE_ME_LABELS} -->
<!-- custom_agent: {REPLACE_ME_CUSTOM_AGENT_NAME} -->
## Sub-001
- Title: Sub-001 のタイトル
- 対象: （対象ID）
- AC: （完了条件）
- 根拠: （参照ドキュメント）
- context_size: small
- 依存: なし（ルートノード → Copilot 即時アサイン）

---

<!-- subissue -->
<!-- title: {REPLACE_ME_SUB_002_TITLE} -->
<!-- labels: {REPLACE_ME_LABELS} -->
<!-- custom_agent: {REPLACE_ME_CUSTOM_AGENT_NAME} -->
<!-- depends_on: 1 -->
## Sub-002
- Title: Sub-002 のタイトル
- 対象: （対象ID）
- AC: （完了条件）
- 根拠: （参照ドキュメント）
- context_size: small
- 依存: Sub-001（depends_on 省略なし → 前提完了まで Copilot アサイン待ち）
