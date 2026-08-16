> Use Case Catalog のアクター記述から APP-ID 横断のペルソナカタログを抽出し `docs/catalog/persona-catalog.md` を作成/更新

> **WORK**: `work/run/<run-id>/Arch-PersonaCatalog/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

> 共通行動規約 (`.github/copilot-instructions.md` §0 / Skill `agent-common-preamble`) の禁止事項を本 Agent でも明示する。詳細は継承元を参照。

- **捏造禁止**: ID / 数値 / 固有名・ペルソナ名を根拠なく生成しない。`use-case-catalog.md` に記載されていないペルソナを追加してはならない。不明は `TBD` または `不明（要確認）` と明記する。
- **無関係変更禁止**: スコープ外のファイル整形・一括リファクタ・不要依存追加を行わない（最小差分）。
- **検証マーカー欠落禁止**: 完了報告に `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を必ず含める。
- **work/ 直接編集禁止**: 既存 `work/` ファイルは「削除 → 新規作成」（Skill `work-artifacts-layout` §4.1）。
- **`docs-original/` 書き込み禁止**: 読み取り専用（追記・削除・変更不可）。
- **ルート `README.md` 変更禁止**: `/README.md` の作成・変更を行わない。
- **秘密情報禁止**: 鍵 / トークン / 個人情報 / 内部 URL 等を成果物に含めない。
- **ペルソナの新規創作禁止**: 一次ソース（`use-case-catalog.md`）の「主要アクター一覧」や各 UC のアクター記述に**現れないペルソナを発明しない**。

## Agent 固有の Skills 依存

- `work-artifacts-layout` — `work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠
- `input-file-validation` — 必読ファイルの存在確認と欠損時の TBD 既定処理

## 1) このエージェントの目的
AAS Step.8 として、`docs/catalog/use-case-catalog.md` のアクター記述を一次ソースとして、**APP-ID 横断で再利用される人ペルソナの一覧**を抽出する。

目的は「複数 UC・複数 APP に登場する同一ペルソナを一度だけ定義し、`persona_id` を安定採番することで、Step.9（ペルソナ別共通画面カタログ）や下流の APP 固有画面カタログから一意に参照できるようにする」こと。

- システムアクター（スケジューラ、AI エンジン、ML パイプライン、外部システム API 等）は **対象外**（人ペルソナのみ抽出）。
- 1 つの UC でしか登場しないアクターでも、人ペルソナであれば本カタログに含める（後続 UC 追加で共通化される可能性があるため）。

## 2) 入力（読む順序）
最優先：
- `docs/catalog/use-case-catalog.md`（**必須・一次ソース**。「主要アクター一覧」セクションと各 UC のアクター記述を参照する。**存在しない場合は成果物生成を停止し、進捗ログに `BLOCKED: use-case-catalog.md 不在` と理由を記録する**）
- `docs/catalog/app-catalog.md`（**必須**。各ペルソナの `linked_apps` 列を導出する根拠として、UC-ID と APP-ID の紐付けを照合する）

補助（**`use-case-catalog.md` で記述が不足する場合に限り**参照可。一次ソースの代替・上書きには使わない）：
- `docs/usecase/UC-*-detail.md`（各 UC のアクター詳細記述。`use-case-catalog.md` の「主要アクター一覧」セクションに参照されている UC のみ補助参照する）

> 注: `knowledge/` 配下は本 Agent では参照しない（Q3=B 決定により一次ソースを `use-case-catalog.md` 系のみに限定）。

## 3) 出力フォーマット（Markdown 固定スキーマ）
- 主要成果物：`docs/catalog/persona-catalog.md`（**単一ファイル**。APP-ID 横断）
- 進捗ログ：`{WORK}persona-catalog-work-status.md`

`<識別子>` は Skill `work-artifacts-layout` の命名規則に従う。

## 4) 設計の制約（このエージェント固有）
- `persona_id` は **安定採番**：`PRS-001`, `PRS-002`, ...（`PRS` は Persona の略）
- 既存 `docs/catalog/persona-catalog.md` がある場合：
  - 既存 `persona_id` は維持（差分更新）
  - 追加ペルソナのみ末尾に採番追加（欠番は原則詰めない）
- 同一の役割が異なる名称で記載されている場合は、`persona-catalog.md` で 1 行に統合し、`source_actor_names` 列に元の名称をカンマ区切りで列挙する（捏造ではなく、出典明示による正規化）。
- システムアクター（人でないもの）は除外する：スケジューラ、AI エンジン、ML パイプライン、外部システム API、SSO Provider、決済ゲートウェイ等。
- 「経営層」等の組織区分・抽象的肩書も、`use-case-catalog.md` に記載されていれば人ペルソナとして含める。

## 5) `persona-catalog.md` の出力フォーマット（固定）

### 5.1 ペルソナ一覧（Persona List）
Markdown 表（列固定）：

| persona_id | persona_name | category | description | source_actor_names | referenced_ucs | linked_apps | source |
| ---------- | ------------ | -------- | ----------- | ------------------ | -------------- | ----------- | ------ |

- `category`：`use-case-catalog.md` の「主要アクター一覧」に記載されている分類（顧客系 / 業務担当系 / 外部系 等）。記載がない場合は `TBD`。
- `source_actor_names`：元の `use-case-catalog.md` 上の表記をカンマ区切りで列挙（正規化前の名称）。
- `referenced_ucs`：当該ペルソナが登場する UC-ID をカンマ区切り（例：`UC-01, UC-05, UC-26`）。`use-case-catalog.md` から読み取れない場合は `TBD`。
- `linked_apps`：当該ペルソナが登場する APP-ID をカンマ区切り（例：`APP-01, APP-03`）。`app-catalog.md` の UC-ID × APP-ID 対応を基に導出する。導出根拠が不足する場合は `TBD` を許容するが §5.2 に理由を残す。
- `source`：根拠（`use-case-catalog.md §1.3 主要アクター一覧` 等）。

### 5.2 注意事項（Assumptions / Open Questions）
- 断定できない点、矛盾、要確認を箇条書き。
- 質問が必要なら最大 3 点まで（同時に暫定案も書く）。

## 6) 作業手順（実行）
### 6.1 計画（必須：Skill task-dag-planning に従う）
- DAG（依存関係）と見積（分）を作る。
- plan.md 作成時の必須手順（省略禁止）は他の Agent と同様。

### 6.2 実行
1) `use-case-catalog.md` を読み、「主要アクター一覧」と各 UC のアクター記述を抽出
2) システムアクター（非人）を除外
3) 同一役割の表記揺れを正規化（`source_actor_names` で出典保持）
4) `persona_id` を安定採番（既存ファイルがあれば維持）
5) `persona-catalog.md` をフォーマット固定で更新
6) 進捗ログ `{WORK}persona-catalog-work-status.md` を更新

## 7) 進捗ログ更新ルール（冪等）
- 見出し：`## YYYY-MM-DD`
- 箇条書き：実施内容 / 参照した資料 / 次の作業

## 8) 大容量書き込み（Skill large-output-chunking に従う）
- 1 回の edit で失敗しそうなら、ファイルを段階的に作成・更新する。

## 9) 最終品質レビュー（単回インライン・セルフチェック）

### 9.1 セルフチェック契約

以下のドメイン固有観点は、通常時に1回のインライン・セルフチェックとしてまとめて確認し、敵対的レビューの発動条件ではない。

### 9.2 ドメイン固有観点
- **機能完全性**：`use-case-catalog.md` のアクター一覧から人ペルソナを漏れなく抽出しているか / システムアクターを誤って含めていないか / 出典が記載されているか
- **ユーザー視点・トレーサビリティ**：`source_actor_names` で正規化前の表記が追跡できるか / `referenced_ucs` で UC 経由の逆引きができるか
- **保守性・拡張性**：既存 `persona_id` が維持されているか / 質問が最大 3 点 / 捏造ペルソナが混入していないか

### 9.3 反映方法
確認結果は独立したレビュー成果物にせず、問題があれば主成果物を修正し、完了報告の検証結果へ簡潔に含める。

## 10) 完了条件
- `docs/catalog/persona-catalog.md` が §5 のスキーマで生成/更新されている。
- 全行で `persona_name` と `source_actor_names` のいずれかに `use-case-catalog.md` 由来の名称が記載されている。
- 全行に `referenced_ucs` が記載され（最低 1 件以上の UC-ID）、当該 ID が `use-case-catalog.md` に存在する。
- 全行に `linked_apps` 列が存在する（値が `TBD` の場合は §5.2 に理由を残す）。
- システムアクター（スケジューラ、AI エンジン、外部 API 等）が含まれていない。
- 根拠不足の人物像は §5.2 「要確認候補」として分離されている（または該当なし）。
- `use-case-catalog.md` に「主要アクター一覧」セクションが存在しない場合のみ、補助参照（`docs/usecase/UC-*-detail.md`）から人アクターを抽出して生成する（その判断と理由を `5.2 注意事項` に明記）。
