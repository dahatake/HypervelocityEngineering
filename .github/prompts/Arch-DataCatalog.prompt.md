> 概念データモデルと物理テーブルのマッピングを記録するデータカタログを生成

> **WORK**: `work/run/<run-id>/Arch-DataCatalog/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

- 完了報告には、実行したテストのコマンドと exit code を書いてください。HVE が合否の判定に使います。必要に応じて `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を含めます。

## Agent 固有の Skills 依存

- `work-artifacts-layout` — `work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠
- `input-file-validation` — 必読ファイルの存在確認と欠損時の TBD 既定処理
- `app-scope-resolution` — APP-ID 指定時の対象サービス・画面・エンティティのスコープ判定
- `knowledge-lookup` — `knowledge/D01〜D21` の業務要件・ドメイン定義の参照

## 2) 入力（必ず参照）

### 必須入力
- `docs/catalog/data-model.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — エンティティと APP-ID の紐付け判定根拠）

### 推奨入力（存在すれば読む）
- `docs/catalog/service-catalog.md`
- `docs/catalog/service-catalog-matrix.md`

### 入力解決ポリシー（汎用性の担保）
- 入力パスをハードコードせず、`search` で同等資料を動的に特定できる場合はその旨を明記する
- 特定のアーキテクチャスタイル（マイクロサービス/バッチ/モノリス）に依存した記述は避ける
- 推奨入力が存在しない場合でも停止しない。該当セクションを `TBD（<ファイル名> 未検出）` とする

### 質問ポリシー
- 不足が致命的でない場合は `TBD` を置いて進める

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D07-用語集-ドメインモデル定義書.md` — 用語・ドメインモデル
- `knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` — データモデル・SoR/SoT

## 3) 出力フォーマット（Markdown固定スキーマ）

### A) データカタログ
- `docs/catalog/data-catalog.md`（新規作成。既存ファイルがある場合は上書き）

### B) 進捗ログ（Skill work-artifacts-layout §4.1 準拠：read → delete → create）
- `{WORK}work-status.md`

### C) 分割が必要になった場合（共通ルール）
- `{WORK}plan.md`
- `{WORK}subissues.md`

## 3) 実行フロー

### 3.0 依存確認（必須・最初に実行）
- `docs/catalog/data-model.md` と `docs/catalog/domain-analytics.md` の両方を `read` で確認する
- いずれかが存在しない、空、または見出し構造が不完全な場合：
  - **「依存 Step が未完了のため、このタスクは実行不可です。不足: <ファイル名>」** と出力して **即座に停止** する
  - ⚠️ 他Agent呼出・不足ファイル自己作成は禁止（スコープ外）

### 3.1 Discovery（根拠の回収）
参照ドキュメントから以下を抽出し、根拠（ファイルパス + 見出し/節）を控える：
- エンティティ一覧（名前、説明、Owner Service）
- 集約一覧と集約ルート
- Bounded Context とサービス境界
- 値オブジェクト一覧
- データストア種別（data-model.md の `## 3.` または同等セクションから）
- テーブル/コレクション定義（主キー、属性、型）
- PII/機密マーキング

### 3.2 計画・分割
- 計画を書く場合は Skill `task-dag-planning` に従う。
- `work/` 構造: Skill work-artifacts-layout に従う（`{WORK}`）

### 3.3 Execution（成果物の作成）

#### `data-catalog.md` の章構造（固定・`docs-output-format` Skill §1 に従う）

```markdown
# Data Catalog

## 1. 概要（Overview）
- データカタログの目的と範囲
- 対象アーキテクチャスタイル（マイクロサービス/バッチ/モノリス等、入力に基づく）
- 本カタログの更新タイミング（DevOpsの各フェーズでの参照・更新方針）

## 2. エンティティ × 物理テーブルマッピング（Entity-Table Mapping）
表形式（列固定）：
| Entity ID | エンティティ名（論理） | Bounded Context | Owner Service | 利用APP | 物理テーブル/コレクション名 | データストア種別 | 主キー（物理） | 根拠 |
|---|---|---|---|---|---|---|---|---|
- `利用APP`：`app-list.md` を根拠に判定した APP-ID（N:N のためカンマ区切り、例: `APP-01, APP-03`）。不明な場合は `TBD`
- data-model.md の §2 と §3 相当を突合する
- マッピングが確定できない場合は「TBD」と明記し理由を書く

## 3. 属性 × 列マッピング（Attribute-Column Mapping）
エンティティごとに：
| 属性名（論理） | 列名（物理） | データ型 | NULL許容 | PII | 暗号化要否 | 制約 | 備考 |

## 4. サービス × データストア所有権マトリクス（Ownership Matrix）
表形式：
| サービス名 | データストア種別 | 利用APP | 所有エンティティ | 参照のみのエンティティ | 根拠 |
|---|---|---|---|---|---|

## 5. 値オブジェクト × 列マッピング（Value Object Mapping）
表形式：
| 値オブジェクト名 | 所属エンティティ | 展開先列（物理） | データ型 | 備考 |

## 6. ID体系・採番規則（ID Schema）
表形式：
| エンティティ | ID属性名 | 採番方式 | フォーマット | 一意性スコープ | 備考 |

## 7. データライフサイクル（Data Lifecycle）
表形式：
| エンティティ | 作成トリガー | 更新トリガー | 削除/アーカイブ方針 | 保持期間 | 根拠 |

## 8. Mermaid 図（Physical ER Diagram）
- サービス/Bounded Context 単位で物理ERダイアグラムを作成
- 物理テーブル名・物理列名を使用

## 9. Open Questions / Assumptions
- 未確定点と仮定（最大10程度）
```

#### 進捗ログを更新する（Skill work-artifacts-layout §4.1 準拠：delete + create）
`{WORK}work-status.md` を以下の手順で更新する：
1. 既存ファイルが存在する場合は `read` で現在の内容を取得する
2. 既存ファイルを削除する
3. 既存内容に以下エントリを追記した形で新規作成する：
   - 日時:
   - 完了:
   - 次:
   - ブロッカー/質問:

## 3.5) 成果物の分割ルール
- どのような分割を行う場合でも、**`docs/catalog/data-catalog.md` は常に索引/統合版として維持し、ワークフローの入出力契約とする。**
- 1つの APP-ID のみが利用するエンティティ群がある場合、APP-ID 単位の「ビュー」を追加生成してもよいが、元データは `docs/catalog/data-catalog.md` に集約する。
  - 追加ビューの例: `docs/data-catalog-app-01.md`（APP-01 が利用するエンティティおよびそれに関連するサービス所有権・属性マッピングを `docs/catalog/data-catalog.md` から抽出・整形した派生物）
  - 複数 APP で共有されるエンティティは `docs/catalog/data-catalog.md` 上で管理し、「利用APP」列をカンマ区切りで記載して区別する（別ファイルには分割しない）。

## 4) 書き込み安全策（空ファイル/欠落対策）

`large-output-chunking` Skill §3 に従う（具体的なセクション順: ## 1. 〜 ## 9.）。エンティティ数が多く 20,000 文字を超える見込みの場合は `large-output-chunking` スキルの分割手順（§1–§2）を適用する。

## 5) 完了条件
- `docs/catalog/data-catalog.md` が作成され、§1〜§9 の全セクションを含む
- 全エンティティが data-model.md と1:1対応している（TBD は許容するが理由を明記）
- 完了時に自身の Issue に `aad:done` ラベルを付与する

### 5.1 受入観点（完了条件の補足）

以下のドメイン固有観点は成果物の受入条件であり、出力前に行う別の検証ステップでも、敵対的レビューの発動条件でもない。

### 5.2 ドメイン固有観点
- **網羅性・一貫性**：全エンティティが data-model.md と1:1対応しているか
- **論理-物理整合性**：論理名と物理名のマッピングに矛盾がないか、PII/暗号化が一貫しているか
- **実用性・DevOps活用性**：開発者がDDL生成・マイグレーション・テストデータ作成に直接使える精度か

### 5.3 反映方法
観点を満たさない箇所は作業中に主成果物で直し、独立したレビュー成果物は作らない。完了報告の検証結果には結果を簡潔に含める。
