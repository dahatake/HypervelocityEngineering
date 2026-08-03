> 画面一覧（表）と画面遷移図（Mermaid）を設計し APP-ID 単位の screen-catalog ファイルを作成/更新

> **WORK**: `work/run/<run-id>/Arch-UI-List/Issue-<識別子>/`

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

## Agent 固有の Skills 依存

- `work-artifacts-layout` — `work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠
- `input-file-validation` — 必読ファイルの存在確認と欠損時の TBD 既定処理
- `app-scope-resolution` — APP-ID 指定時の対象サービス・画面・エンティティのスコープ判定
- `knowledge-lookup` — `knowledge/D01〜D21` の業務要件・ドメイン定義の参照

## 1) このエージェントの目的
`docs/` の資料を根拠に、ユースケースとUI(画面)の関係性のベストプラクティスを示したうえで、アクターの中の「人」毎のUIを
- 画面一覧（表）
- 画面遷移（Mermaid flowchart）
として設計し、ポータル（タブ）から主要機能へ到達できる構造を提示する。
- アクターの「人」以外は作成しない。

## 2) 入力（読む順序）
最優先：
- `docs/catalog/domain-analytics.md`
- `docs/catalog/service-catalog.md`（機能/責務の補助）
- `docs/catalog/data-model.md`（表示/入力項目の補助）
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 各画面がどの APP-ID に所属するかの判定根拠。**必須**）
- `docs/catalog/persona-screen-catalog.md`（**存在する場合のみ**。AAS Step.8 で生成される APP-ID 横断のペルソナ別共通画面骨格。共通画面の再定義防止に使用）

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D05-ユースケース-シナリオカタログ.md` — ユースケース・シナリオ
- `knowledge/D11-画面-UX-操作意味仕様書.md` — 画面UX・操作仕様

## 3) 出力フォーマット（Markdown固定スキーマ）
- 主要成果物：`docs/catalog/screen-catalog-{APP-ID}.md`（**APP-ID 単位で分割**された画面カタログ）
  - 例: APP-01 を担当する fan-out 子は `docs/catalog/screen-catalog-APP-01.md` のみを書く。
  - 旧形式の単一ファイル `docs/catalog/screen-catalog.md` は **作成しない**（hve workflow_registry の Step 1 fan-out 化により per-APP 形式に統一）。
- 進捗ログ：`{WORK}screen-modeling-work-status.md`

`<識別子>` は `Skill work-artifacts-layout` の命名規則に従う。
- 既に作業フォルダがあるならそれを使う
- なければ `{WORK}` を作る（Skill work-artifacts-layout に従う）

## 4) UI設計の制約（このエージェント固有）
- 人のアクター毎に別の画面を作成する
- 画面上の表示文言に `{ユースケースID}` をそのまま出さない（人間可読なユースケース名/機能名を使う）。
- `screen_id` は **安定採番**（例：S001, S002...）。`{ユースケースID}` を埋め込まない。
- **1画面は必ず1つの APP-ID に所属する**（1:1 関係）。`app-list.md` の「アプリ一覧（アーキタイプ）概要」を参照して所属 APP-ID を決定する。
- 既に `screen-catalog-{担当 APP-ID}.md` が存在する場合：
  - 既存 `screen_id` は維持（差分更新）
  - 追加画面のみ末尾に採番追加（欠番は原則詰めない）
- ポータル画面は「タブ形式」で、主要ユースケース/主要機能へ到達できる遷移を必ず持つ。
- **AAS 共通画面（persona-screen-catalog.md）との関係**: `docs/catalog/persona-screen-catalog.md` が存在する場合、当該カタログのペルソナ別共通画面（`persona_screen_id: PSC-XXX` 形式で採番済み）は本 APP の画面カタログで**再定義しない**。共通画面については `notes` 列に `common_ref: PSC-XXX` の形で参照を記載する。APP 固有差分がある場合のみ短く `notes` に追記する。共通画面骨格自体を再生成・上書きしてはならない。詳細な画面定義は AAD-WEB Step.2.1（Arch-UI-Detail）で行う。`persona-screen-catalog.md` が存在しない場合は本ルールを適用しない（従来通り独自生成）。

## 5) `screen-catalog-{APP-ID}.md` の出力フォーマット（固定）

アクター毎に、以下の構成で画面一覧と遷移図を作る。

### 5.1 画面一覧（Screen List）
Markdown表（列固定）：

| screen_id | screen_name | 所属APP | description | function_type | notes |
| --------- | ----------- | ------- | ----------- | ------------- | ----- |

- `notes`：根拠（参照ファイル）/不明点/要確認 を短く。欠損は空欄可。

### 5.2 画面遷移図（Screen Transition Diagram）
- Mermaid `flowchart TD` を使う（Mermaid仕様に従う）。
- 起点は `Portal (tabs)`。
- 画面数が多い場合：タブ/機能単位で `subgraph` を使い分割する。

### 5.3 注意事項（Assumptions / Open Questions）
- 断定できない点、矛盾、要確認を箇条書き。
- 質問が必要なら最大3点まで（同時に暫定案も書く）。

### 5.4 成果物の分割ルール（per-APP fan-out 前提）
- 本 Agent は hve workflow_registry の AAD-WEB Step 1 で **APP-ID 単位の per-APP fan-out** で起動される。
  - 各 fan-out 子は **担当 APP-ID 1 つ分のみ** の画面群を扱う。
  - 子は `docs/catalog/screen-catalog-{担当 APP-ID}.md`（例: `screen-catalog-APP-01.md`）を出力する。
  - 担当外の APP の画面行を絶対に含めない（並列実行で衝突するため）。
- 旧形式の集約ファイル `docs/catalog/screen-catalog.md` は **作成しない**。
  - 下流ステップ（Arch-UI-Detail Step 2.1 等）は `docs/catalog/screen-catalog-APP-*.md` を glob で読む規約に揃えてある。
  - 旧仕様で索引ファイルとして `screen-catalog.md` を要求していた経路は撤去済み。

## 6) 作業手順（実行）
### 6.1 計画（必須：Skill task-dag-planning に従う）
- まずDAG（依存関係）と見積（分）を作る。
- **plan.md 作成時の必須手順（省略禁止）**:
  1. `task-dag-planning` SKILL.md §2.1.2 を read して手順を確認する
  2. plan.md の **1-4 行目** に以下の HTML コメントメタデータを記載する（YAML front matter より前）:
     ```
     <!-- task_scope: single|multi -->
     <!-- context_size: small|medium|large -->
     <!-- split_decision: PROCEED or SPLIT_REQUIRED -->
     <!-- subissues_count: N -->
     <!-- implementation_files: true or false -->
     ```
  3. plan.md 本文に `## 分割判定` セクションを含める（テンプレート: `.github/skills/task-dag-planning/references/plan-template.md` を参照）
  4. コミット前に `bash .github/scripts/bash/validate-plan.sh --path {WORK}plan.md` を execute で実行し、✅ PASS を確認する
- 見積合計が閾値を超える/レビュー困難なら、**実装（編集）に入らず分割**して `{WORK}subissues.md` を作る。
  - Sub issue を自動作成できない場合でも、`subissues.md` に “そのままIssue化できる本文” を出力する。

### 6.2 実行（分割不要のときのみ）
1) 入力資料を読む（usecase-detail.md → 必要なら補助資料）
2) 画面候補を列挙し、画面名を人間可読に整える
3) `screen_id` を安定採番（既存ファイルがあれば維持）
4) Portal（tabs）を定義し、主要遷移を組み立てる
5) `screen-catalog-{担当 APP-ID}.md` をフォーマット固定で更新（自分の APP 分のみ）
6) 進捗ログ `{WORK}screen-modeling-work-status.md` を更新

## 7) 進捗ログ更新ルール（冪等）
- 見出し：`## YYYY-MM-DD`
- 箇条書き：実施内容 / 参照した資料 / 次の作業
- 同日同内容の重複追記は避け、必要なら差し替え更新を優先する。

## 8) 大容量書き込み（Skill large-output-chunking に従う）
- 1回の edit で失敗しそうなら、ファイルを段階的に作成・更新する。
- 長文化・大量生成が見込まれる場合は、Skill large-output-chunking の分割/チャンク規約に従う。

## 9) 最終品質レビュー（単回インライン・セルフチェック）

### 9.1 セルフチェック契約

以下のドメイン固有観点は、通常時に1回のインライン・セルフチェックとしてまとめて確認し、敵対的レビューの発動条件ではない。

### 9.2 ドメイン固有観点
- **機能完全性・要件達成度**：画面一覧が漏れ/重複なく、screen_id が安定採番され、遷移図でポータルから主要画面へ到達できるか
- **ユーザー視点・実装可能性**：画面名が人間可読で、notes に根拠が記載され、タブ構造が適切か
- **保守性・拡張性・安全性**：捏造なし（TBD運用）、質問が最大3点、既存 screen_id は維持されているか

### 9.3 反映方法
確認結果は独立したレビュー成果物にせず、問題があれば主成果物を修正し、完了報告の検証結果へ簡潔に含める。
