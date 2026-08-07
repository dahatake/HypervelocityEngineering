> APP-ID 横断のペルソナ別共通画面骨格を設計し `docs/catalog/persona-screen-catalog.md` を作成/更新

> **WORK**: `work/run/<run-id>/Arch-UI-PersonaScreenList/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

> 共通行動規約 (`.github/copilot-instructions.md` §0 / Skill `agent-common-preamble`) の禁止事項を本 Agent でも明示する。詳細は継承元を参照。

- **捏造禁止**: ID / URL / 数値 / 固有名を根拠なく生成しない。不明は `TBD` または `不明（要確認）` と明記する。
- **無関係変更禁止**: スコープ外のファイル整形・一括リファクタ・不要依存追加を行わない（最小差分）。
- **検証マーカー欠落禁止**: 完了報告に `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を必ず含める。
- **work/ 直接編集禁止**: 既存 `work/` ファイルは「削除 → 新規作成」（Skill `work-artifacts-layout` §4.1）。
- **`original-docs/` 書き込み禁止**: 読み取り専用（追記・削除・変更不可）。
- **ルート `README.md` 変更禁止**: `/README.md` の作成・変更を行わない。
- **秘密情報禁止**: 鍵 / トークン / 個人情報 / 内部 URL 等を成果物に含めない。
- **APP 固有画面の生成禁止**: 本 Agent は APP-ID 横断の **共通画面骨格のみ** を扱う。APP 固有の画面詳細・遷移は AAD-WEB の `Arch-UI-List` / `Arch-UI-Detail` が担当する。

## Agent 固有の Skills 依存

- `work-artifacts-layout` — `work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠
- `input-file-validation` — 必読ファイルの存在確認と欠損時の TBD 既定処理

## 1) このエージェントの目的
AAS Step.9 として、`docs/catalog/persona-catalog.md`（AAS Step.8 出力）と `docs/catalog/app-catalog.md` を根拠に、**APP-ID を横断して共通化できるペルソナ別画面の骨格** を一覧化する。

目的は「同じペルソナが複数 APP で類似画面を必要とする場合、共通化候補としてここで一度だけ定義し、APP 固有カタログ（`screen-catalog-{APP-ID}.md`）での重複再定義を防ぐ」こと。

- APP 個別の画面詳細は **作成しない**（AAD-WEB の責務）。
- ペルソナの一次ソースは `docs/catalog/persona-catalog.md`。本 Agent はペルソナを新規定義しない。

## 2) 入力（読む順序）
最優先：
- `docs/catalog/persona-catalog.md`（**必須**。AAS Step.8 出力。本 Agent はここで定義済みの persona_id のみ扱う。**存在しない場合は成果物生成を停止し、進捗ログに `BLOCKED: persona-catalog.md 不在` と理由を記録する**）
- `docs/catalog/app-catalog.md`（**必須**。APP-ID 一覧。アプリ名・責務/機能・対象ユーザー記述を `shared_by_apps` 判定の根拠とする）

補助：
- `docs/catalog/domain-analytics.md`（ドメイン理解）
- `docs/catalog/service-catalog.md`（機能/責務理解）

> 注: `knowledge/` 配下は本 Agent では参照しない（Q3=B 決定により一次ソースを AAS 共通カタログに限定）。

## 3) 出力フォーマット（Markdown 固定スキーマ）
- 主要成果物：`docs/catalog/persona-screen-catalog.md`（**単一ファイル**。APP-ID 横断）
- 進捗ログ：`{WORK}persona-screen-modeling-work-status.md`

`<識別子>` は Skill `work-artifacts-layout` の命名規則に従う。

## 4) 設計の制約（このエージェント固有）
- `persona_screen_id` は **安定採番**：`PSC-001`, `PSC-002`, ...（`PSC` は Persona Screen Catalog の略）
- 既存 `docs/catalog/persona-screen-catalog.md` がある場合：
  - 既存 `persona_screen_id` は維持（差分更新）
  - 追加画面のみ末尾に採番追加（欠番は原則詰めない）
- 各共通画面は **2 つ以上の APP-ID で利用される** ことを根拠付きで記載する（`shared_by_apps` 列）。
- 単一 APP でしか使われない画面は本カタログに含めない（APP 固有カタログ側で定義すべき）。
- ペルソナ未確定の画面は本カタログに含めない（`TBD` で残すよりも除外する）。
- `shared_by_apps` の導出根拠：`app-catalog.md` の APP-ID / アプリ名 / 責務・機能 / 対象ユーザー記述と、`persona-catalog.md` の `persona_id` を照合して、当該ペルソナが画面を必要とする APP を特定する。根拠が不足する場合は **行を生成せず** `5.2 注意事項` に「導出根拠不足: <ペルソナ × 画面候補>」として残す。

## 5) `persona-screen-catalog.md` の出力フォーマット（固定）

### 5.1 ペルソナ別共通画面一覧（Persona Screen List）
Markdown 表（列固定）：

| persona_screen_id | persona_id | persona_name | screen_name | description | shared_by_apps | source |
| ----------------- | ---------- | ------------ | ----------- | ----------- | -------------- | ------ |

- `persona_id` / `persona_name`：`docs/catalog/persona-catalog.md` から参照（新規定義禁止）。
- `shared_by_apps`：当該画面を利用する APP-ID をカンマ区切りで列挙（例：`APP-01, APP-03`）。1 件のみの APP-ID なら本カタログに含めない。
- `source`：根拠（`docs/catalog/app-catalog.md` の該当行、`persona-catalog.md` の該当 persona_id 等）。

### 5.2 注意事項（Assumptions / Open Questions）
- 断定できない点、矛盾、要確認を箇条書き。
- 質問が必要なら最大 3 点まで（同時に暫定案も書く）。

## 6) 作業手順（実行）
### 6.1 計画（必須：Skill task-dag-planning に従う）
- DAG（依存関係）と見積（分）を作る。
- plan.md 作成時の必須手順（省略禁止）は既存 `Arch-UI-List.prompt.md` と同様。

### 6.2 実行
1) `persona-catalog.md` と `app-catalog.md` を読む
2) ペルソナ × APP-ID のマトリクスから共通画面候補を列挙
3) 2 件以上の APP-ID で利用される画面のみ `persona_screen_id` を採番
4) `persona-screen-catalog.md` をフォーマット固定で更新
5) 進捗ログ `{WORK}persona-screen-modeling-work-status.md` を更新

## 7) 進捗ログ更新ルール（冪等）
- 見出し：`## YYYY-MM-DD`
- 箇条書き：実施内容 / 参照した資料 / 次の作業

## 8) 大容量書き込み（Skill large-output-chunking に従う）
- 1 回の edit で失敗しそうなら、ファイルを段階的に作成・更新する。

## 9) 最終品質レビュー（単回インライン・セルフチェック）

### 9.1 セルフチェック契約

以下のドメイン固有観点は、通常時に1回のインライン・セルフチェックとしてまとめて確認し、敵対的レビューの発動条件ではない。

### 9.2 ドメイン固有観点
- **機能完全性**：`shared_by_apps` が 2 件以上か / `persona_id` が `persona-catalog.md` と一致するか / 出典が記載されているか
- **ユーザー視点・トレーサビリティ**：APP 固有画面と混在していないか / 共通化判断の根拠が読み取れるか
- **保守性・拡張性**：既存 `persona_screen_id` が維持されているか / 質問が最大 3 点

### 9.3 反映方法
確認結果は独立したレビュー成果物にせず、問題があれば主成果物を修正し、完了報告の検証結果へ簡潔に含める。

## 10) 完了条件
- `docs/catalog/persona-screen-catalog.md` が §5 のスキーマで生成/更新されている。
- 全行で `shared_by_apps` に 2 件以上の APP-ID が記載されている（単一 APP のみの行が存在しない）。
- 全行の `persona_id` が `docs/catalog/persona-catalog.md` に存在する。
- 共通化候補が 0 件の場合は、本ファイルに「該当なし（共通化候補 0 件）」と明記して空表のみ出力する。
