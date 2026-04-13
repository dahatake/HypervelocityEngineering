---
name: docs-output-format
description: >
  docs/ 成果物フォーマットの共通原則。固定章立て（見出し固定順序・不足は TBD・
  各表の各行に出典必須）と Mermaid erDiagram 記法指針を提供する。
  USE FOR: docs/ format, fixed heading order, citation required per row,
  TBD for missing items, Mermaid erDiagram notation guide,
  document output standardization.
  DO NOT USE FOR: work/ format (use work-artifacts-layout),
  test specification format (use test-strategy-template),
  agent-specific heading list definition.
  WHEN: docs/ 配下の成果物を作成する、固定章立てを確認する、
  出典必須ルールを確認する、Mermaid erDiagram を記述する、
  ドキュメントフォーマットの共通原則を参照する。
metadata:
  origin: user
  version: "2.0.0"
---

# docs-output-format

## 目的

`docs/` 配下の成果物フォーマットの **共通原則** を一元管理する。各 Agent は本 Skill を参照し、固有の章立て（見出しリスト）のみを Agent 側に記載する。

---

## Non-goals

- **`work/` 配下の作業成果物フォーマット** — Skill `work-artifacts-layout` が担当
- **テスト仕様書のフォーマット** — Skill `test-strategy-template` が担当
- **Agent 固有の見出しリスト定義** — 各成果物の具体的な見出し順序は Agent 側で定義する

---

## 3原則（詳細: `references/heading-and-mermaid-rules.md`）

1. **見出しを固定順序で列挙する** — Agent 定義の順序を守る。順序の入れ替え・省略は禁止
2. **不足は TBD** — 根拠が不足する項目は `TBD（要確認: {理由}）` と記載。空欄放置は禁止
3. **各表の各行に出典必須** — 出典形式: `ファイルパス#見出し名`（例: `docs/catalog/domain-analytics.md#BC-01`）

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/heading-and-mermaid-rules.md` | §1 固定章立て詳細（1.1〜1.3）、§2 Mermaid erDiagram 記法指針全体（2.1〜2.4） |

---

## 入出力例

> ※ 以下は説明用の架空例です

**例1（出典付き表）**: 各行に `出典` 列を設け、`docs/catalog/domain-analytics.md#BC-03, docs/catalog/service-catalog.md#SVC-05` 形式で記載。不明な行は `TBD（要確認）`。

**例2（Mermaid erDiagram）**: サービス単位で図を分割（10個以下のエンティティ）。エンティティ名は PascalCase、属性は `UUID campaign_id PK` 形式。

## 参照元

- `work/Issue-skills-migration-investigation/duplication-patterns.md` — P-08, P-07 の詳細

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `work-artifacts-layout` | 補完 | work/ 配下は work-artifacts-layout、docs/ 配下は本Skillが担当 |
| `test-strategy-template` | 補完 | テスト仕様書フォーマットは test-strategy-template が担当 |
| `large-output-chunking` | 関連 | docs/ 成果物が巨大な場合の分割ルール |
