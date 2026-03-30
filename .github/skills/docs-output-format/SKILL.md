---
name: docs-output-format
description: "docs/ 成果物フォーマットの共通原則。固定章立て（見出し固定順序・不足は TBD・各表の各行に出典必須）と Mermaid erDiagram 記法指針を提供する。Arch-* 系 Agent が docs/ 配下の設計書を生成する際に参照する。"
---

# docs-output-format

## 目的

`docs/` 配下の成果物フォーマットの **共通原則** を一元管理する。
各 Agent は本 Skill を参照し、固有の章立て（見出しリスト）のみを Agent 側に記載する。

本 Skill は以下のパターンを統合して提供する:
- **P-08**: `docs/` 成果物フォーマット（固定章立て + 出典必須）
- **P-07**: Mermaid `erDiagram` 記法指針

---

## 1. 固定章立ての原則（P-08）

`docs/` 配下の成果物は、以下の3原則に従う。

### 1.1 見出しを固定順序で列挙する

- 成果物の見出し（Markdown `##` / `###`）は **Agent が定義した固定順序** で出力する
- 順序の入れ替え・省略は禁止。Agent 定義の見出しリストをそのまま守る
- 見出しの追加は、Agent 定義の末尾に限り許可（既存の順序を崩さない）

### 1.2 不足は TBD

- 根拠が不足する項目・未確定の項目は **`TBD`** と記載する
- 空欄放置は禁止。不明であることを明示する
- `TBD` には可能な限り「確認方法」または「推定される根拠」を添える
- 例: `TBD（要確認: SVC-03 の API 仕様書が未作成）`

### 1.3 各表の各行に出典必須

- 表形式の成果物では、各行に **出典（ファイル#見出し）** 列を設ける
- 出典形式: `ファイルパス#見出し名`（例: `docs/domain-analytics.md#BC-01`）
- 根拠が複数ある場合はカンマ区切りで列挙する
- 出典が特定できない行は `TBD（要確認）` と明記する
- 根拠のない情報の記載は禁止（捏造禁止原則と連動）

---

## 2. Mermaid `erDiagram` 記法指針（P-07）

### 2.1 基本方針

- エンティティ関連図は Mermaid `erDiagram` 記法で記述する
- **サービス単位**（または Bounded Context 単位）で図を分割する（1図に詰め込まない）
- **読みやすさを最優先** とする（巨大な1枚の図よりも、サービスごとの小さな図の集合を優先）

### 2.2 記法ルール

- エンティティ名: PascalCase（例: `Campaign`, `DeliveryPlan`）
- 属性: `型名 属性名 制約` の順（例: `UUID campaign_id PK`, `string name`）
- リレーション: 標準の Mermaid 記法（`||--o{`, `}o--||` 等）を使用
- 他サービスのエンティティを参照する場合は「ID 参照」で表現し、直接結合は避ける

### 2.3 分割の目安

- 1つの `erDiagram` ブロックに含めるエンティティは **10 個以下** を目安とする
- 超える場合はサービスまたはドメイン境界で分割する
- 分割した場合は、全体の関連を示す概要図を別途用意する（推奨）

### 2.4 Mermaid 図全般の注意

- `erDiagram` 以外の Mermaid 図（`flowchart`, `sequenceDiagram` 等）を使用する場合も、読みやすさ優先・分割の原則は同様に適用する
- 図のタイトルやコメントで、対象サービス/BC 名を明示する

---

## 参照元

- `work/Issue-skills-migration-investigation/duplication-patterns.md` — P-08, P-07 の詳細
- `work/Issue-skills-migration-investigation/extraction-candidates.md` — 抽出判定
- `work/Issue-skills-migration-investigation/migration-matrix.md` — GO-2 評価
