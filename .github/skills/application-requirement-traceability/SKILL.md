---
name: application-requirement-traceability
description: "Use when: generated application design or development must select, validate, cite, and trace APP-specific requirements without loading every requirement document."
metadata:
  origin: user
  version: 1.0.0
---

# application-requirement-traceability

## 目的

AAS / ADA / AAD-WEB / ASDW-WEB / ADFD / ADFDV / AAG / AAGD / AAR で、対象 APP-ID に対応する要求だけを設計・実装根拠として使用し、完了報告へ追跡可能な証跡を残す。

## 必須手順

1. Skill `app-scope-resolution` で、実効 `app_ids` または fan-out key から対象 APP-ID を確定する。
2. 各 APP-ID の canonical path `docs/architectural-requirements-app-NNN.md` を必須入力として扱う。
3. 対象文書の欠落、schema不正、APP-ID不一致、または `TBD` かつ `Blocker=yes` があれば fail-closed で停止する。既定案へ降格しない。
4. プロンプトに注入された APP-ID と canonical path を使い、必要な要求行だけを Skill `markdown-query` で選択取得する。
5. `confirmed` / `source-backed` の Requirement ID だけを設計・実装根拠として引用する。`TBD` は未解決事項として扱い、根拠にしない。
6. 完了報告へ次の block を正確に1つ記録する。

```markdown
<!-- app-requirements:start -->
- APP-IDs: APP-001
- Requirement-IDs: APP-001-FR-001, APP-001-NFR-001
- Requirement-Documents: docs/architectural-requirements-app-001.md
- Unresolved-Blockers: none
<!-- app-requirements:end -->
```

## コンテキスト節約

- 要求書全文を全 Step へ常時注入しない。
- 対象外 APP の要求書を読まない。
- まず `markdown-query` で Requirement ID、Requirement、Acceptance Criteria の該当箇所だけを取得する。
- 0ヒットまたは索引stale時だけ、注入済みcanonical pathの必要範囲を直接読む。

## 禁止事項

- APP-ID、Requirement ID、Source、Acceptance Criteriaを推測・捏造しない。
- `TBD` を実装済み要件として扱わない。
- path解決やschema検証を実行面ごとに再実装しない。HVE local実行は `hve.application_requirements` を正本とする。
- 新規設定、新規外部依存、要求書全文の常時入力を追加しない。

## Related Skills

| Skill | 関係 |
|---|---|
| `agent-common-preamble` | Cloudを含む全Agentの共通ルーター |
| `app-scope-resolution` | APP-IDとfan-out scopeの解決 |
| `markdown-query` | 対象要求行の選択取得 |
| `input-file-validation` | 必須文書の存在確認 |
