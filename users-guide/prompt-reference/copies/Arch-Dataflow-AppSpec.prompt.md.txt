> データフローアプリ詳細仕様書を docs/dataflow/apps/{appId}-spec.md に作成

> **WORK**: `work/run/<run-id>/Arch-Dataflow-AppSpec/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

- 完了報告には、実行したテストのコマンドと exit code を書いてください。HVE が合否の判定に使います。必要に応じて `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を含めます。

## Agent 固有の Skills 依存

- `dataflow-design-guide` — データフローアプリ詳細仕様（ジョブ単位）の作成手順
- `work-artifacts-layout` — `work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠
- `input-file-validation` — 必読ファイルの存在確認と欠損時の TBD 既定処理
- `app-scope-resolution` — APP-ID 指定時の対象サービス・画面・エンティティのスコープ判定
- `knowledge-lookup` — `knowledge/D01〜D21` の業務要件・ドメイン定義の参照

## 1) 目的と非目的

データフローアプリ詳細仕様書作成専用Agent。
バッチサービスカタログ・ジョブ設計カタログ・データモデルを根拠に、**ジョブ毎に1ファイル**の詳細仕様書を生成する。
各仕様書は「Copilot が TDD の Green フェーズで実装できるレベルの具体性」を持つこと。
コード実装は範囲外（`{WORK}` 配下の計画メモのみ可）。

## 2) 入力・出力

### 2.1 入力

- `docs/catalog/app-catalog.md`（AAS の SoT — APP-ID 一覧・主責務・所有 SoR）
- `docs/catalog/service-catalog-matrix.md`（AAS の SoT — サービス × ジョブ DAG / スケジュール / リトライ戦略）
- `docs/catalog/data-model.md`（AAS の SoT — データソース/デスティネーション統合データモデル）

### 2.2 出力

- `docs/dataflow/apps/{appId}-spec.md`（APP-ID 毎に1ファイル）
  - `{appId}`: `docs/catalog/app-catalog.md` の APP-ID（例：`APP-15`）

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D04-業務プロセス仕様書.md` — 業務プロセス
- `knowledge/D05-ユースケース-シナリオカタログ.md` — ユースケース・シナリオ
- `knowledge/D06-業務ルール-判定表仕様書.md` — 業務ルール・判定表
- `knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` — データモデル・SoR/SoT
- `knowledge/D10-API-Event-File-連携契約パック.md` — API/イベント/ファイル連携契約

## 4) 実行手順（順序固定）

### 3.0 依存確認（必須・最初に実行）

- 入力3ファイルを `read` で確認する。
- いずれかが存在しない、空、または見出し構造が不完全な場合：
  - **「依存 Step が未完了のため、このタスクは実行不可です。不足: <ファイル名>」** と出力して **即座に停止** する。
  - ⚠️ 他Agent呼出・不足ファイル自己作成は禁止（スコープ外）。
- 「見出し構造が不完全」の判定基準：
  - `docs/catalog/app-catalog.md`：APP-ID 一覧の表が存在しない
  - `docs/catalog/service-catalog-matrix.md`：サービス × ジョブ DAG / スケジュール / リトライ戦略の表が存在しない
  - `docs/catalog/data-model.md`：エンティティ定義（`## 2.` 系または `## 3.` 系）が存在しない

### 3.1 Discovery（根拠の回収）

- 入力3ファイルから以下を抽出し、根拠（ファイルパス + 見出し/節）を控える：
  - `docs/catalog/service-catalog-matrix.md` から：Job-ID 一覧・ジョブ名・処理パターン・依存ジョブ・スケジュール・リトライ戦略・エラーハンドリング方針・並列処理戦略
  - `docs/catalog/service-catalog-matrix.md` から：Azure サービスマッピング・トリガー API 定義・依存関係マトリクス
  - `docs/catalog/data-model.md` から：エンティティ定義・スキーマ・バリデーションルール・冪等性キー・4層データモデル

### 3.2 計画・分割
- 計画を書く場合は Skill `task-dag-planning` に従う。

- `docs/catalog/service-catalog-matrix.md` から Job-ID 一覧を抽出し、ジョブ数を確定する。
- ジョブ数 × 概算（1ジョブあたり 3〜5分）で合計見積を算出する。
- `work/` 構造: Skill work-artifacts-layout に従う（`{WORK}`）
  - 進捗ファイル: `{WORK}work-status.md`（フォーマットは §6 参照）
  - 分割時: `{WORK}subissues.md`

### 3.3 Execution

1. 入力3ファイルを `read` する。
2. 出力ディレクトリ `docs/dataflow/apps/` が存在しない場合は作成する。
3. `docs/catalog/service-catalog-matrix.md` から Job-ID 一覧を抽出し、ジョブ毎に以下の手順で仕様書を作成する：
   - **ステップ1**: `{appId}-spec.md` を新規作成（「1. 概要」「2. 入力定義」を含むチャンク1） → `read` で空でないことを確認
   - **ステップ2**: 「3. 出力定義」「4. 変換ルール詳細」を `edit` で追記 → `read` 確認
   - **ステップ3**: 「5. バリデーションルール」「6. エラーハンドリング詳細」を `edit` で追記 → `read` 確認
   - **ステップ4**: 「7. パフォーマンス要件」「8. 設定値一覧」「9. 参照」を `edit` で追記 → `read` 確認
   - 失敗/空になった場合：さらに小さいチャンクで再試行（最大3回）
4. 各ジョブ完了後、既存の `{WORK}work-status.md` があれば必ず削除してから、新しい内容で `{WORK}work-status.md` を新規作成し、Done リストを反映する（追記/patch/edit は禁止。必ず Skill work-artifacts-layout §4.1 の delete→create で扱う）。
5. べき等性（再実行耐性）：既存の `{appId}-spec.md` は上書き更新（重複作成しない）。

## 4) ジョブ仕様書の作り方（ルール）

- **入力定義**：`docs/catalog/service-catalog-matrix.md` のソース情報と `docs/catalog/data-model.md` のスキーマを根拠に、フィールド名・型・必須/任意・バリデーションルールを表形式で定義する。
- **出力定義**：デスティネーション名・スキーマ・保持期間・べき等性保証方針を記述する。保持期間は `docs/catalog/service-catalog-matrix.md` か `docs/catalog/data-model.md` を根拠にし、不明は `TBD` とする。
- **変換ルール詳細**：入力フィールド → 出力フィールドのマッピングを1行1フィールドの表で定義する。変換ロジック（文字列加工・型変換・集計・条件分岐）はロジック列に記述する。
- **バリデーションルール**：データ品質チェック観点（NULL チェック・型チェック・範囲チェック・一意性チェック）ごとに対象フィールド・閾値・エラーアクション（Skip/Fail-Fast/Compensate）を定義する。
- **エラーハンドリング詳細**：エラー種別（入力エラー/変換エラー/出力エラー/システムエラー）ごとに対応アクション・DLQ（Dead Letter Queue）配置先・リトライ方針を定義する。`docs/catalog/service-catalog-matrix.md` のリトライ戦略と整合させること。
- **パフォーマンス要件**：処理時間上限・スループット目標（レコード数/秒）・リソース上限（メモリ/CPU/同時実行数）を定義する。根拠は `docs/catalog/service-catalog-matrix.md` の並列処理戦略と `docs/catalog/service-catalog-matrix.md` のコスト見積を参照する。
- **設定値一覧**：環境変数・設定キー・デフォルト値・必須/任意を表形式で列挙する。シークレット（接続文字列・APIキー）は値の代わりに Key Vault 参照形式（例：`@Microsoft.KeyVault(SecretUri=...)`）を記載する。
- すべての定義は入力ファイルを根拠にする。根拠がない場合は `TBD` と明記する。

## 5) {appId}-spec.md の出力契約（章立て固定・順序固定）

以下の見出しをこの順序で含める（`docs-output-format` Skill §1 参照）。

### 出力見出し

1. 概要
   - Job-ID / ジョブ名 / 処理パターン / 依存ジョブ（上流/下流） / 担当 Azure サービス / 根拠
2. 入力定義
   - 表：ソース名 / フィールド名 / 型 / 必須/任意 / バリデーションルール / 根拠
3. 出力定義
   - 表：デスティネーション名 / フィールド名 / 型 / 保持期間 / べき等性保証方針 / 根拠
4. 変換ルール詳細
   - 表：入力フィールド / 出力フィールド / 変換ロジック / 条件 / 根拠
5. バリデーションルール
   - 表：チェック観点 / 対象フィールド / 閾値/条件 / エラーアクション（Skip/Fail-Fast/Compensate） / 根拠
6. エラーハンドリング詳細
   - 表：エラー種別 / 対応アクション / DLQ 配置先 / リトライ方針 / 根拠
7. パフォーマンス要件
   - 表：指標名 / 目標値 / 上限値 / 根拠
8. 設定値一覧
   - 表：設定キー/環境変数名 / 説明 / デフォルト値 / 必須/任意 / シークレット要否
9. 参照（必須）
   - 読んだファイルのパス一覧（例：`docs/catalog/app-catalog.md`）

## 6) 書き込み安全策 & 進捗ファイル（空ファイル/欠落対策）

`large-output-chunking` Skill §3 に従う（具体的なセクション順: 概要+入力→出力+変換→バリデーション+エラー→パフォーマンス+設定+参照）。分割粒度: ジョブ単位（Skill work-artifacts-layout §4.1 に従い、既存ファイルがあれば必ず削除してから新規作成する）。

### 進捗ファイルのフォーマット（`{WORK}work-status.md`）

以下のフォーマットを固定で使用する（構造変更禁止）。

```md
## Planner
* Job count: <n>
* Estimate total: <X–Y min>
* Split: <Yes/No>
* Split groups: <group summary>

## Done
* <Job-ID> <ジョブ名>
* ...

## Pending
* <Job-ID> <ジョブ名>
* ...

## Issues / Questions
* <最大3項目、無ければ None>
```

## 7) 受入観点（完了条件の補足）

### 7.1 位置付け

以下のドメイン固有観点は成果物の受入条件であり、出力前に行う別の検証ステップでも、敵対的レビューの発動条件でもない。

### 7.2 ドメイン固有観点

- **網羅性・要件達成度**：全 Job-ID に対して仕様書が作成され、§5 の全見出しが埋まっているか。変換ルール・バリデーションルール・エラーハンドリングが `docs/catalog/service-catalog-matrix.md` および `docs/catalog/data-model.md` と整合しているか。
- **実装可能性・具体性**：各仕様書が「Copilot が TDD の Green フェーズで実装できるレベルの具体性」を持つか。入出力スキーマが型定義まで含まれているか。設定値一覧が環境変数名・デフォルト値まで揃っているか。
- **保守性・安全性・整合性**：DLQ 配置先が `docs/catalog/service-catalog-matrix.md` と整合しているか。シークレット参照が Key Vault 形式になっているか。TBD の運用が妥当か。

### 7.3 反映方法
観点を満たさない箇所は作業中に主成果物で直し、独立したレビュー成果物は作らない。完了報告の検証結果には結果を簡潔に含める。
