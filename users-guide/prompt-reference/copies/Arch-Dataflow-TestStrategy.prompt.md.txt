> データフローテスト戦略書を docs/dataflow/dataflow-test-strategy.md に作成

> **WORK**: `work/run/<run-id>/Arch-Dataflow-TestStrategy/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

- 完了報告には、実行したテストのコマンドと exit code を書いてください。HVE が合否の判定に使います。必要に応じて `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を含めます。

## Agent 固有の Skills 依存

- `dataflow-design-guide` — データフローテスト戦略の作成手順。`references/dataflow-test-strategy.md`（テストピラミッド・テストデータ・テストダブル・データ品質）を参照する。**本 Prompt に手順を複製せず、Skill を読んで適用すること**
- `work-artifacts-layout` — `work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠
- `input-file-validation` — 必読ファイルの存在確認と欠損時の TBD 既定処理
- `app-scope-resolution` — APP-ID 指定時の対象サービス・画面・エンティティのスコープ判定
- `knowledge-lookup` — `knowledge/D01〜D21` の業務要件・ドメイン定義の参照

## 1) 目的と非目的

データフローテスト戦略書作成専用Agent。
AAS の全社テスト戦略と、データフローアプリカタログ・データフローサービスカタログを根拠に、**データフロー処理固有のテスト戦略**（テストピラミッド・テストデータ生成戦略・テストダブル戦略・データ品質テスト方針）を **1ファイル** にまとめる。
本書は ADFDV Step 2.1（TDD RED — テストコード作成）が「テストダブル戦略」から **Azurite（Azure Storage エミュレーター）・Testcontainers の利用有無**を確定するための唯一の参照先である。
ジョブ個別のテストケース列挙は範囲外（ADFD Step 3 = `Arch-Dataflow-TDD-TestSpec` が担当）。テストコード実装も範囲外（ADFDV Step 2.1 が担当）。

## 2) 入力・出力

### 2.1 入力

- `docs/catalog/test-strategy.md`（AAS の SoT — 全社テスト戦略・テストレイヤー・カバレッジ方針）
- `docs/dataflow/dataflow-app-catalog.md`（ADFD Step 0.2 の出力 — Job-ID 一覧・処理パターン・リトライ戦略）
- `docs/dataflow/dataflow-service-catalog.md`（ADFD Step 4 の出力 — Azure サービスマッピング・DLQ 設定）

### 2.2 出力

- `docs/dataflow/dataflow-test-strategy.md`

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D17-品質保証-UAT-受入パッケージ.md` — 品質保証・UAT
- `knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` — データモデル・データ品質

## 3) 実行手順（順序固定）

### 3.0 依存確認（必須・最初に実行）

- 入力3ファイルを `read` で確認する。
- いずれかが存在しない、空、または見出し構造が不完全な場合：
  - **「依存 Step が未完了のため、このタスクは実行不可です。不足: <ファイル名>」** と出力して **即座に停止** する。
  - ⚠️ 他Agent呼出・不足ファイル自己作成は禁止（スコープ外）。
- 「見出し構造が不完全」の判定基準：
  - `docs/catalog/test-strategy.md`：テストレイヤー／テストダブル方針の記載が存在しない
  - `docs/dataflow/dataflow-app-catalog.md`：「1. ジョブ一覧表」が存在しない
  - `docs/dataflow/dataflow-service-catalog.md`：「2. ジョブ → Azure サービスマッピング表」が存在しない

### 3.1 Discovery（根拠の回収）

- 入力3ファイルから以下を抽出し、根拠（ファイルパス + 見出し/節）を控える：
  - `docs/catalog/test-strategy.md` から：テストレイヤー定義・カバレッジ目標・テストダブル方針・CI 実行方針
  - `docs/dataflow/dataflow-app-catalog.md` から：Job-ID 一覧・処理パターン・リトライ戦略（障害注入・冪等性テストの対象決定に使う）
  - `docs/dataflow/dataflow-service-catalog.md` から：依存する Azure サービス（テストダブルが必要な外部依存の確定に使う）

### 3.2 計画・分割
- 計画を書く場合は Skill `task-dag-planning` に従う。

- `work/` 構造: Skill work-artifacts-layout に従う（`{WORK}`）

### 3.3 Execution

1. 入力3ファイルを `read` する。
2. 出力ディレクトリ `docs/dataflow/` が存在しない場合は作成する。
3. `docs/dataflow/dataflow-test-strategy.md` を以下のチャンク方式で作成する：
   - **チャンク1**: ヘッダ＋「1. 概要」「2. テストピラミッド」を新規作成 → `read` で空でないことを確認
   - **チャンク2**: 「3. テストデータ生成戦略」を `edit` で追記 → `read` 確認
   - **チャンク3**: 「4. テストダブル戦略」を `edit` で追記 → `read` 確認
   - **チャンク4**: 「5. データ品質テスト方針」「6. TDD 実行順序方針」「7. 参照」を `edit` で追記 → `read` 確認
   - 失敗/空になった場合：さらに小さく分割して再試行（最大3回）
4. べき等性（再実行耐性）：`docs/dataflow/dataflow-test-strategy.md` は上書き更新（重複作成しない）。

## 4) テスト戦略書の作り方（ルール）

- **テストピラミッド**：ユニット / 統合 / E2E / データ品質の各レイヤーについて、対象・カバレッジ目標・実行タイミング（CI / ステージング / 本番毎実行）を定義する。`docs/catalog/test-strategy.md` の全社方針と矛盾させない。差異がある場合は差異と理由を明記する。
- **テストデータ生成戦略**：生成方法（ファクトリ / フィクスチャ / 本番データのサニタイズ）・ボリューム方針（ユニットは少量、E2E は本番相当）・エッジケースデータの定義方針を記述する。
- **テストダブル戦略**：`docs/dataflow/dataflow-service-catalog.md` の依存 Azure サービスごとに、テストダブル種別（Stub / Mock / Fake / Spy）・スタブの振る舞い・利用テストレイヤーを表で定義する。
  **Azurite（Azure Storage エミュレーター）と Testcontainers の利用有無は本節で必ず明示的に確定する**（ADFDV Step 2.1 がここから読み取るため、`利用する` / `利用しない` / `TBD（理由）` のいずれかを断定的に記載する）。
- **データ品質テスト方針**：入出力データのバリデーション観点（件数一致・NULL 率・重複率・参照整合性）と、判定閾値・失敗時アクションを定義する。
- **TDD 実行順序方針**：RED → GREEN → REFACTOR の適用範囲と、冪等性テスト・障害注入テスト・大量データテスト・チェックポイント/リスタートテストの実施順序方針を定義する。
- 詳細な表項目とテンプレートは Skill `dataflow-design-guide` の `references/dataflow-test-strategy.md`（§1 テストピラミッド / §2 テストデータ生成戦略 / §3 テストダブル設計）に従う。本書へ複製しない。
- すべての定義は入力ファイルを根拠にする。根拠がない場合は `TBD` と明記する。

## 5) dataflow-test-strategy.md の出力契約（章立て固定・順序固定）

以下の見出しをこの順序で含める（`docs-output-format` Skill §1 参照）。
**「4. テストダブル戦略」は ADFDV Step 2.1 が読み取る節であり、名称を変更してはならない。**

### 出力見出し

1. 概要
   - 対象スコープ・全社テスト戦略との差異と理由・前提/注意（推測禁止・TBD の扱い・参照できなかった資料）
2. テストピラミッド
   - 表：テストレイヤー / 対象 / カバレッジ目標 / 実行タイミング / 根拠
3. テストデータ生成戦略
   - 生成方法・ボリューム方針・エッジケースデータ方針（説明 + 表）
4. テストダブル戦略
   - 表：外部依存（Azure サービス） / テストダブル種別（Stub/Mock/Fake/Spy） / スタブの振る舞い / 利用テストレイヤー / 根拠
   - Azurite 利用有無：`利用する` / `利用しない` / `TBD（理由）` を明記
   - Testcontainers 利用有無：`利用する` / `利用しない` / `TBD（理由）` を明記
5. データ品質テスト方針
   - 表：品質観点 / 対象 / 判定閾値 / 失敗時アクション / 根拠
6. TDD 実行順序方針
   - RED → GREEN → REFACTOR の適用範囲と、冪等性 / 障害注入 / 大量データ / チェックポイント・リスタートの実施順序
7. 参照（必須）
   - 読んだファイルのパス一覧（例：`docs/catalog/test-strategy.md`）

## 6) 書き込み安全策（空ファイル/欠落対策）

`large-output-chunking` Skill §3 に従う（具体的なセクション順: 概要→テストピラミッド→テストデータ→テストダブル→データ品質→TDD 順序→参照）。分割粒度: §5 の出力セクション単位。

## 7) 受入観点（完了条件の補足）

### 7.1 位置付け

以下のドメイン固有観点は成果物の受入条件であり、出力前に行う別の検証ステップでも、敵対的レビューの発動条件でもない。

### 7.2 ドメイン固有観点

- **網羅性・要件達成度**：§5 の全見出しが埋まり、`docs/dataflow/dataflow-service-catalog.md` の全依存サービスがテストダブル戦略表に登場しているか。
- **下流適合性**：「4. テストダブル戦略」に Azurite / Testcontainers の利用有無が断定的に記載され、ADFDV Step 2.1 が判断を保留せずテスト基盤を選べるか。
- **保守性・拡張性・安全性**：全社テスト戦略との差異が理由付きで説明されているか。根拠のないカバレッジ目標・閾値を発明していないか。TBD の運用が適切か。

### 7.3 反映方法
観点を満たさない箇所は作業中に主成果物で直し、独立したレビュー成果物は作らない。完了報告の検証結果には結果を簡潔に含める。

<output_contract>
- 出力先パス:
  - 本体: `docs/dataflow/dataflow-test-strategy.md`（1 件のみ）
  - 分割時: `work/run/<run-id>/Arch-Dataflow-TestStrategy/Issue-<識別子>/plan.md`, `subissues.md`
- 出力フォーマット（必須セクション・順序固定）:
  1) 概要 2) テストピラミッド 3) テストデータ生成戦略 4) テストダブル戦略 5) データ品質テスト方針 6) TDD 実行順序方針 7) 参照
- 必須ルール:
  - 見出し `## 4. テストダブル戦略` に Azurite 利用有無と Testcontainers 利用有無を断定形で明記する（ADFDV Step 2.1 の参照先）
  - 各表に `根拠`（ファイルパス + 見出し/節）列を付与する
  - 全社テスト戦略（`docs/catalog/test-strategy.md`）と矛盾する場合は差異と理由を「1. 概要」に明記する
- 文字数/粒度目安:
  - ADFDV Step 2.1 が、テスト基盤・テストダブル・データ品質判定を追加確認なしに実装できる粒度
</output_contract>
