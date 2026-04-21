- 必須: 各ブロックは `<!-- subissue -->` の直後に `<!-- title: ... -->` を置く
- 必須: title は空値禁止。コピペ後に必ず置換する
- 必須: ブロック数を plan.md の `<!-- subissues_count: N -->` と一致させる

# Sub Issues: [タスク名]

> ⚠️ **コピペ後に必ず値を書き換えること（CI バリデーション必須）**
>
> - `<!-- title: ... -->` は必須（空値禁止）
> - `<!-- labels: ... -->` はカンマ区切り（任意）
> - `<!-- custom_agent: ... -->` は Agent 名（任意）
> - `<!-- depends_on: ... -->` は依存先 Sub 番号（カンマ区切り、任意）
> - Sub ブロック数は `plan.md` の `subissues_count` と一致させる

<!-- subissue -->
<!-- title: [REPLACE_ME_SUB_001_TITLE] -->
<!-- labels: aad:ready, copilot -->
<!-- custom_agent: Arch-Microservice-ServiceDetail -->
## Sub-001
- Title: Sub-001 のタイトル
- 対象: （対象ID）
- AC: （完了条件）
- 根拠: （参照ドキュメント）
- 見積: X分
- 不確実性: 低
- 依存: なし

---

<!-- subissue -->
<!-- title: [REPLACE_ME_SUB_002_TITLE] -->
<!-- labels: aad:ready, copilot -->
<!-- custom_agent: Arch-Microservice-ServiceDetail -->
<!-- depends_on: 1 -->
## Sub-002
- Title: Sub-002 のタイトル
- 対象: （対象ID）
- AC: （完了条件）
- 根拠: （参照ドキュメント）
- 見積: X分
- 不確実性: 低
- 依存: Sub-001
