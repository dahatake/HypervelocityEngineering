# マイクロサービス定義書テンプレ（記入ガイド付き）

> 目的：各サービスの詳細仕様を **一貫した粒度**で記述し、API/イベント/データ所有/セキュリティ/運用を「コード生成に耐える骨子」で揃える。

---

## 使い方（必読）
1. サービスごとの成果物 `docs/usecase/<usecaseId>/services/<serviceId>-<serviceNameSlug>-description.md` は、このテンプレを **コピーして**作成する。
2. 推測は禁止。根拠がない場合は `TBD` を置き、`根拠:` に参照ファイル（パス）を記す。
3. 例は **あくまで例**。ユースケース固有の用語/ID/イベント名に置き換える。
4. サンプルデータ（`data/.../sample-data.json`）の **値の転記は禁止**。必要なら「フィールド名/型/意味」を要約する。

---

## 記法ルール
- セクション見出しは削除しない（将来の自動処理/比較のため）。
- 各セクションは以下の構造を推奨：
  - **必須**：最低限埋めるべき項目
  - **任意**：あれば有益だが未確定でも可
  - **例**：短い例（2〜10行程度）
  - **根拠**：参照ファイル（パス）／決定理由
- キーワード：
  - `TBD`：未確定
  - `N/A`：該当なし（理由を併記）

---

## 1. サービスメタ情報
### 必須
- サービス名 / 短縮名（英字推奨）
- 概要（One-liner）：誰が・何を・なぜ
- 責務（Do）/ 非責務（Don't）
- オーナー（チーム/担当）※不明ならTBD

### 任意
- 主要ペルソナ（管理者/申請者/監査など）
- 境界（他サービスとの境界線）

### 例
- サービス名／短縮名：Template Service（TPL）
- 概要：申請テンプレを作成・公開し、申請者が利用できる状態にする
- Do：テンプレの版管理、公開/廃止、差分提示
- Don't：承認ルーティングの「実行」（承認エンジンの責務）
- オーナー：TBD

### 根拠
- docs/usecase/<usecaseId>/service-catalog.md

---

## 2. ビジネス能力・コンテキスト
### 必須
- 対象ドメイン（例：申請テンプレ管理）とユースケースとの対応
- ライフサイクル（状態と遷移イベント）：Draft → InReview → Published → Retired

### 任意
- 下位要件ID（FR-xxx 等）の対応表（トレーサビリティ）

### 例
- 状態：Draft / InReview / Published / Retired
- 遷移：publish / retire / rollback（可否はTBD）

### 根拠
- docs/usecase/<usecaseId>/usecase-description.md

---

## 3. 公開インターフェース（同期）
> ここは **OpenAPIの骨子のみ**：パス・メソッド・主要ステータス・代表スキーマ名（詳細スキーマ定義は書かない）

### 必須
- APIスタイル（例：REST/JSON/UTF-8）
- リソース一覧（名詞で統一）
- 操作粒度（作成/取得/検索/公開/廃止/差分/プレビュー等）
- 冪等性（Idempotency-Key の扱い、重複作成基準）
- エラー語彙（コード体系の方針）

### 任意
- フィルタ/ソート/ページング規約
- 認可スコープ（JWT等）骨子

### 例（OpenAPI骨子：最小）
```yaml
paths:
  /templates:
    get:
      responses:
        "200": { schema: TemplateList }
    post:
      headers: { Idempotency-Key: string }
      responses:
        "201": { schema: Template }
        "409": { schema: Error }
  /templates/{templateId}:
    get:
      responses:
        "200": { schema: Template }
        "404": { schema: Error }
````

### エラーコード例（方針のみ）

* TPL-VAL-001（入力検証）
* TPL-STATE-001（状態不正）
* TPL-EXT-001（外部依存障害）

### 根拠

* docs/usecase/<usecaseId>/services/service-list.md
* docs/usecase/<usecaseId>/service-catalog.md

---

## 4. 公開インターフェース（非同期）

> ここは **AsyncAPIの骨子のみ**：チャンネル名・イベント名・キー属性（詳細スキーマは書かない）

### 必須

* Produced Events（発行）：名称、発火条件、最小ペイロード項目、キー属性、配信保証
* Consumed Events（購読）：名称、ハンドラ名（論理名で可）、再試行/DLQ 方針、順序要件
* 互換性規約（後方互換など）と versioning（schemaVersion 等）

### 任意

* Outbox戦略（概念）
* 保持期間、PII方針（IDのみ等）

### 例（AsyncAPI骨子：最小）

```yaml
channels:
  tpl.template.published:
    publish:
      message: { name: TEMPLATE.PUBLISHED, key: templateId }
  tpl.template.retired:
    publish:
      message: { name: TEMPLATE.RETIRED, key: templateId }
  mdm.updated:
    subscribe:
      message: { name: MDM.UPDATED, key: orgId }
```

### 根拠

* docs/usecase/<usecaseId>/service-catalog.md
* docs/usecase/<usecaseId>/data-model.md

---

## 5. データ所有・モデル（概念）

### 必須

* 主エンティティ（名前）と所有者（本サービス/他サービス）
* 一意性/整合性ルール（例：同一typeIdで有効版は1つ）
* データ分類（PII/非PII）※推測禁止

### 任意

* マルチテナンシのスコープ（全社/部門/ロール等）

### 例

* 所有：Template（本サービス）、RequestType（本サービス）、Org（MDM所有）
* PII：TBD（根拠が必要）

### 根拠

* docs/usecase/<usecaseId>/data-model.md

---

## 6. セキュリティ・権限

### 必須

* 認証方式（例：OIDC/SSO）
* 認可方式（RBAC/ABAC）と主要属性
* 監査（何を/誰が/いつ/どこから を不可改ざんで残す方針）

### 任意

* 暗号化（転送/保存）の方針（KMS等は概念）

### 例

* 認可：ABAC（departmentId, role）
* 監査：publish/retire/rollback を必ず記録

### 根拠

* docs/usecase/<usecaseId>/usecase-description.md

---

## 7. 外部依存・統合

### 必須

* 依存先一覧と契約（何を参照/何を更新）
* 障害時フォールバック（概念）

### 任意

* タイムアウト/リトライ方針（概念）

### 例

* 依存：MDM（組織属性参照）、承認エンジン（ルール参照のみ）
* 障害時：暫定許可→後続検証キュー（TBD）

### 根拠

* docs/usecase/<usecaseId>/service-catalog.md

---

## 8. 状態遷移・ビジネスルール

### 必須

* 状態機械（状態と遷移条件）
* 公開可否ゲート（例：必須キー欠落は公開不可）

### 任意

* 安全側フォールバック原則

### 例

* Published は「必須検索キーOK」「外部検証OK」が前提（詳細TBD）

### 根拠

* docs/usecase/<usecaseId>/usecase-description.md

---

## 9. 非機能・SLO（概念）

### 必須

* 可用性/性能の“目安”（p50/p95等、未定はTBD）
* 可観測性（メトリクス/トレース/ログの最小セット）

### 任意

* スケーラビリティ方針（読み主体/書き主体）

### 例

* メトリクス：処理遅延、DLQ件数、エラー率
* トレース：Trace Context を伝播（概念）

---

## 10. バージョニング／互換性

### 必須

* API版付け方針（/v1 等）
* イベント版付け方針（schemaVersion 等）
* 後方互換ルール（追加のみ等）

### 例

* API：/api/v1
* Event：schemaVersion 必須、後方互換（フィールド追加のみ）

---

## 11. エラー・レート制御・再試行

### 必須

* エラー体系（命名規約）
* 再試行の責務分界（クライアント/サーバ）
* 冪等性キーの再送許容

### 任意

* レート制限（読み/書きの差）

### 例

* エラー：TPL-VAL-xxx / TPL-STATE-xxx / TPL-EXT-xxx

---

## 12. 設定・フラグ

### 必須

* 機能フラグの候補（名称と目的のみ）
* 構成キーの候補（名称のみ、値は未記載）

### 例

* featureFlags: localizationEnabled, destructiveChangeGuard
* configKeys: externalApiTimeoutMs, maxAttachmentBytes

---

## 13. 移行・初期データ（任意）

* 初期投入/旧システム対応が必要なら記述。不要なら N/A。

---

## 14. テスト指針（概念）

### 必須

* 契約テスト（Provider/Consumer）方針
* 状態遷移テストの観点
* 監査ログ/権限制御の観点

### 例

* Published への遷移条件を単体＋統合で検証

---

## 15. 運用・リリース（概念）

### 必須

* デプロイ戦略（ローリング/カナリア等）
* DLQ運用（隔離→分類→再投入）

### 任意

* リプレイ戦略（投影再構築）

---

## 16. リスク・オープン課題

### 必須

* 未決事項、外部SLA未定、属性欠落、互換性判断 などを列挙（TBD歓迎）

---

## 17. 画面・操作・API・イベント マッピング

### 必須

* UI/操作 → 呼び出すAPI/イベント の対応（表形式推奨）
* 原則（必要ならBFF等の方針を明記）

### 例（表）

| 画面/操作  | API                          | イベント               | 備考   |
| ------ | ---------------------------- | ------------------ | ---- |
| テンプレ公開 | POST /templates/{id}:publish | TEMPLATE.PUBLISHED | 監査必須 |

---

## 付録A：コード生成用の骨子（貼り付け領域）

* OpenAPI骨子（pathsのみ）
* AsyncAPI骨子（channelsのみ）
* 用語/語彙（状態名、エラーコード辞書）

---

## 最終チェックリスト（必須）

* [ ] 1〜12、14〜17 を埋めた（未確定はTBD＋根拠）
* [ ] OpenAPI/AsyncAPIは「骨子のみ」で詳細スキーマを書いていない
* [ ] sample-data の値を転記していない
* [ ] PII分類は推測していない（根拠がない場合TBD）

````
