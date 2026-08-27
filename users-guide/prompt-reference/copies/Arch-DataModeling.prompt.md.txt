> ユースケースから全エンティティ・サービス境界・データモデル（Mermaid）とJSONサンプルを生成

> **WORK**: `work/run/<run-id>/Arch-DataModeling/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

> 共通行動規約 (`.github/copilot-instructions.md` §0 / Skill `agent-common-preamble`) の禁止事項を本 Agent でも明示する。詳細は継承元を参照。

- **捏造禁止**: ID / URL / 数値 / 固有名を根拠なく生成しない。不明は `TBD` または `不明（要確認）` と明記する。
- **無関係変更禁止**: スコープ外のファイル整形・一括リファクタ・不要依存追加を行わない（最小差分）。
- **検証マーカー欠落禁止**: 完了報告に `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を必ず含める。
- **work/ 直接編集禁止**: 既存 `work/` ファイルは「削除 → 新規作成」（Skill `work-artifacts-layout` §4.1）。
- **`docs-original/` 書き込み禁止**: 読み取り専用（追記・削除・変更不可）。
- **ルート `README.md` 変更禁止**: `/README.md` の作成・変更を行わない。
- **秘密情報禁止**: 鍵 / トークン / 個人情報 / 内部 URL 等を成果物に含めない。

## Agent 固有の Skills 依存

- `work-artifacts-layout` — `work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠
- `input-file-validation` — 必読ファイルの存在確認と欠損時の TBD 既定処理
- `app-scope-resolution` — APP-ID 指定時の対象サービス・画面・エンティティのスコープ判定
- `knowledge-lookup` — `knowledge/D01〜D21` の業務要件・ドメイン定義の参照

### Skill 適用境界
- `app-scope-resolution` は対象範囲の判定にだけ用いる。Data Model のファイル分割には同 Skill の一般的な APP 単位分割を採用せず、下流契約が固定パスを要求するため §3.3.1 の canonical 3件だけを用いる。
- Data Model には `large-output-chunking` の汎用 `index` / `part-NNNN` 命名を適用しない。サンプルデータの JSON 分割は別契約（§3 B）であり、Data Model の固定3 sidecar契約と混同しない。

## 2) 入力（必ず参照）
ユーザーからタスクを受け取ったら、まず以下を読む（存在しない場合は search で探し、見つからなければ質問へ）。
- `docs/catalog/domain-analytics.md`
- `docs/catalog/service-catalog.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — エンティティと APP-ID の紐付け判定根拠）

### 質問ポリシー（共通ルールに従う）
- 不足が致命的でない場合は `TBD` を置いて進める。

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D07-用語集-ドメインモデル定義書.md` — 用語・ドメインモデル
- `knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` — データモデル・SoR/SoT

## 3) 出力フォーマット（Markdown固定スキーマ）
### A) モデリングドキュメント
- `docs/catalog/data-model.md`
- 条件付き sidecar は §3.3.1 の固定3件だけとする。

### B) サンプルデータ
- 原則：`src/data/sample-data.json`
- ただし、エンティティ数が多く **巨大化（レビュー困難 / 書き込み失敗リスク）**する場合は分割してよい：
  - `data/sample-data.index.md`
  - `data/sample-data.part-0001.json` など（複数）
  - この場合、`sample-data.json` は **最小メタ + parts 参照**のJSONにする（後続が辿れるようにする）

### C) 進捗ログ（追記のみ）
- `{WORK}work-status.md`

### D) 分割が必要になった場合（共通ルール）
- `{WORK}plan.md`
- `{WORK}subissues.md`

## 3) 実行フロー（task_scope=multi または context_size=large は“実装開始前”に分割）
### 3.0 依存確認（必須・最初に実行）
- `docs/catalog/domain-analytics.md` と `docs/catalog/service-catalog.md` の両方を `read` で確認する。
- いずれかが存在しない、空、または見出し構造が不完全な場合：
  - **「依存 Step が未完了のため、このタスクは実行不可です。不足: <ファイル名>」** と質問して **即座に停止** する。
  - ⚠️ 他Agent呼出・不足ファイル自己作成は禁止（スコープ外）。

### 3.1 Discovery（根拠の回収）
- 参照ドキュメントから以下を抽出し、根拠（ファイルパス + 見出し/節）を控える：
  - エンティティ候補（名詞句）
  - サービス一覧と責務
  - 主要な処理フロー（作成/更新/参照/削除）
  - PII/機密の示唆（あれば）

### 3.2 計画・分割
- Skill task-dag-planning に従う。
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
- `work/` 構造: Skill work-artifacts-layout に従う（`{WORK}`）

### 3.3 Execution（成果物の作成）
#### (1) `data-model.md` を作る（まず骨子→章ごとに埋める）
章構造は固定（`docs-output-format` Skill §1 に従う）：

# Data Model for <USECASE_ID>

## 1. Overview
- モデリング方針（根拠/所有権/整合性の前提）
- 非対象（分かっている範囲）
- **バッチ／データフロー処理エンティティ補強（該当 APP のみ）**：データソース（例：S3 / RDB / SaaS API）とデスティネーション（例：DWH テーブル / 配信先 API）も `Entity Catalog` に含める。`主要属性` 欄に `種別: DataSource` または `種別: Destination` と明記し、`スキーマ概要 / 提供元（外部所有者）/ SLA（鮮度・到着保証）` を併記する（`Owner Service` 列は AAS 内責任サービスを記載し、`主要属性` の `提供元` と意味を分ける）。リアルタイム同期や Web APP のみ利用するエンティティには適用しない。

## 2. Entity Catalog
- 表形式（列固定）：
  - Entity / 説明 / Owner Service / 利用APP / 主キー / 主要属性 / PII有無 / 永続化方式(推定可) / 根拠
  - `利用APP`：`app-list.md` を根拠に判定した APP-ID（N:N のためカンマ区切り、例: `APP-01, APP-03`）。不明な場合は `TBD`
- 不確実なものは「候補」と明示し、根拠と不足点を書く

## 3. Service Data Stores
各サービスごとに：
- データストア種別（根拠があればそれを優先、なければ「仮定」を明記）
- テーブル/コレクション定義（主キー、必須制約、ユニーク、代表インデックス）
- 他サービス参照は原則「ID参照」（強結合は根拠がある場合のみ）

## 4. Consistency & Events（必要最小限）
- 即時整合/最終整合の要否と理由（根拠がある範囲）
- 主要イベント（producer/consumer、イベント名、キー項目）
- CQRS/Event Sourcing は「根拠がある場合のみ」

## 5. Diagrams（Mermaid）
- 必須：サービス単位の `erDiagram`（`docs-output-format` Skill §2 参照）
- 任意：必要ならフロー図（`sequenceDiagram` 等）

## 6. Open Questions / Assumptions
- 未確定点と仮定（最大10程度、質問にすべきものを優先）

#### (2) `sample-data.json` を作る（架空・日本語・整合）
- トップレベル（原則固定）：
  - `meta.usecaseId`, `meta.generatedAt`（ISO-8601）, `meta.notes`
  - `entities.<EntityName>` は **各10件**（難しい場合は理由を notes に書き、件数を減らすより先に分割を検討）
- 値は **架空**。実在の個人情報（実在の住所/電話/メール等）は作らない。
- ID は衝突しない一貫形式（例：`<entity>-0001`）。参照関係（外部キー相当）は整合させる。

#### (3) 進捗を追記する（append only）
`{WORK}work-status.md` に以下形式で追記：
- 日時:
- 完了:
- 次:
- ブロッカー/質問:

### 3.3.1 成果物の分割ルール
- 本節は Data Model 専用の固定3 sidecar契約であり、§3 B のサンプルデータ `index` / `part-NNNN` 分割とは異なる。
- **`docs/catalog/data-model.md` は常に索引/統合版として維持すること。**
  - ASD の後続 Step は `docs/catalog/data-model.md` を必須入力としているため、分割しても本ファイルを削除・置換しない。
  - 分割時も親は見出し `1`〜`6` を固定順で維持する。見出し `3`〜`5` はリンクだけにせず、主キー・主要制約・代表インデックス・整合性判断・主要イベント・図の要旨を含む統合ビューを残し、下流 Step が親単独で必要情報を取得できるようにする。
- **分割は、単一ファイル版が 50,000 文字を超える見込みの場合だけ行う。** 固定章 `1`〜`6` のドラフトを単一Markdownとして組み立て、改行を含む Unicode 文字数で判定する。前回runの分割状態を閾値判定より優先しない。その場合は次の canonical sidecar 3 件を**すべて**作成または更新する。
  - `docs/catalog/data-model-service-stores.md` — Service Data Stores
  - `docs/catalog/data-model-consistency-events.md` — Consistency & Events
  - `docs/catalog/data-model-diagrams.md` — Diagrams
- **上記 3 件以外の名前・粒度（追加の章別・APP-ID別を含む）で Data Model を分割してはならない。** 下流 Step と io-contract は親と canonical 3 件だけを宣言しており、別名の分割ファイルはどの契約にも現れず検証されないまま残る。
- **相互リンクを必ず張る。** 親ファイル `docs/catalog/data-model.md` は各 sidecar へのリンク一覧と全体要約を保持し、各 sidecar は親ファイルへの戻りリンクを保持する。
- **分割不要になった再実行では、親から sidecar リンクを除いて固定章を親へ統合し、canonical sidecar 3 件の古い（stale）ファイルを削除する。**
- 複数 APP で共有されるエンティティは統一ファイルのまま「利用APP」列をカンマ区切りで記載する。

### 3.4 最終品質レビュー（単回インライン・セルフチェック）

以下のドメイン固有観点は、通常時に1回のインライン・セルフチェックとしてまとめて確認し、敵対的レビューの発動条件ではない。

### 3.4.2 ドメイン固有観点
- **網羅性・要件達成度**：エンティティ漏れ/サービス割当/根拠が充足しているか
- **整合性・妥当性**：主キー/参照/イベント/PII表記/命名/Mermaid可読性が一貫しているか
- **実用性・保守性**：JSONサンプル/表の有用性/将来の拡張可能性は妥当か
- **分割契約**：分割時はcanonical sidecar 3件がすべて存在して相互リンクが有効か、分割不要時は親未リンクのstale sidecarが残っていないか

### 3.4.3 反映方法
確認結果は独立したレビュー成果物にせず、問題があれば主成果物を修正し、完了報告の検証結果へ簡潔に含める。
