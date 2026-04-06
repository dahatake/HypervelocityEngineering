# SVC-01 マイクロサービス定義書：会員・同意管理サービス

> **根拠**：`docs/service-list.md` §SVC-01、`docs/service-catalog.md` §SVC-01、`docs/domain-analytics.md` §BC-01、`docs/app-list.md` §APP-01  
> **作成日**：2026-03-31  
> **バージョン**：v1.1（2026-03-31 Copilot 推論デフォルト回答適用）

> ⚠️ **この回答はCopilot推論をしたものです。**  
> コメント #4160205953「デフォルトの回答で作成してください」に基づき、質問票（70問）のデフォルト回答を適用しました。  
> 推論補完箇所は `（推論: Q{番号} デフォルト回答）` と明記します。

---

## 1. サービスメタ情報

| 項目 | 内容 |
|------|------|
| **サービス名** | 会員・同意管理サービス |
| **短縮名（英字）** | MemberConsentService（MCS） |
| **概要** | 会員（顧客）がロイヤルティプログラムに登録・管理され、個人情報利用に対する同意を目的別に記録・変更できる基盤サービス |
| **利用アプリケーション** | APP-01（主），APP-04（SVC-05 BFF 経由：認証連携），APP-08（SVC-10：会員照会） |
| **BC** | BC-01（会員・同意管理） |
| **サブドメイン** | サポートドメイン |
| **オーナー** | TBD |

**責務（Do）**:
- 会員プロフィールの登録・更新・照会（MemberAggregate）
- 同意記録の管理：目的別オプトイン/オプトアウト（ConsentRecord）
- 顧客 ID（memberId: UUID）の発行・ライフサイクル管理
- 会員登録時の監査ログイベント（MemberRegistered）発行
- 同意変更イベント（ConsentChanged）の発行 → 下流（SVC-15/SVC-08/SVC-07）へ通知
- CRM との連携（連携方式 TBD）

**非責務（Don't）**:
- 認証/トークン発行（外部 ID 基盤/SSO に委譲）
- アクセス制御・権限管理（SVC-15 の責務）
- 監査ログ集約（SVC-16 の責務）
- AI/ML 推論・配信制御（SVC-07/SVC-08 の責務）

**根拠**：`docs/service-list.md` §SVC-01、`docs/app-list.md` §APP-01

---

## 2. ビジネス能力・コンテキスト

| 項目 | 内容 |
|------|------|
| **対象ドメイン** | 会員・同意管理（BC-01） |
| **対応 UC** | UC-01（Primary: 会員登録・同意設定）、UC-16（Secondary: 同意記録参照） |
| **Capability** | CAP-01（会員ライフサイクル管理） |

**ライフサイクル（Member）**:

```
PENDING → ACTIVE → SUSPENDED → CLOSED
```

- PENDING: 登録処理中（メール確認待ち等）
- ACTIVE: 通常会員（ポイント付与・交換可能）
- SUSPENDED: 一時停止（同意撤回・不正検知等）
- CLOSED: 退会（SoR は保持。TBD: 保持期間・法域要件 ブロッカー）

**ライフサイクル（ConsentRecord: 目的別）**:

```
GRANTED → REVOKED
```

- 目的種別: MARKETING, AI_USAGE, THIRD_PARTY（TBD: 法域に応じた目的粒度 ブロッカー#1）

**根拠**：`docs/domain-analytics.md` §エンティティ「Member」「ConsentRecord」

---

## 3. 公開インターフェース（同期）

**API スタイル**: REST/JSON/UTF-8

| リソース | 操作 | メソッド | パス |
|---------|------|---------|------|
| 会員 | 登録 | POST | /members |
| 会員 | 照会 | GET | /members/{memberId} |
| 会員 | 更新 | PATCH | /members/{memberId} |
| 同意 | 付与 | POST | /members/{memberId}/consents |
| 同意 | 撤回 | DELETE | /members/{memberId}/consents/{purpose} |
| 同意一覧 | 照会 | GET | /members/{memberId}/consents |

**冪等性**: `POST /members` は Idempotency-Key ヘッダー使用。同一キーの重複作成は 409 を返す。

**エラー語彙（方針）**:
- MCS-VAL-001: 入力検証エラー
- MCS-STATE-001: 状態不正（例: CLOSED 会員への更新）
- MCS-EXT-001: 外部依存障害（CRM 連携エラー等）

**根拠**：`docs/service-list.md` §SVC-01「提供 I/F」、`docs/service-catalog.md` §SVC-01

---

## 4. 公開インターフェース（非同期）

**AsyncAPI 骨子**:

```yaml
channels:
  mcs.member.registered:
    publish:
      message: { name: MemberRegistered, key: memberId }
      # 購読: APP-12（SVC-16 監査ログ）, APP-04（通知）
  mcs.consent.changed:
    publish:
      message: { name: ConsentChanged, key: memberId }
      # 購読: SVC-15（配信/AI制御フラグ更新）, SVC-08（配信抑止）, SVC-07（AI利用フラグ）
      # 遅延要件: < 5分
```

**イベント詳細**:

| イベント名 | 発火条件 | 最小ペイロード | 配信保証 |
|-----------|---------|------------|---------|
| MemberRegistered | 会員登録完了 | memberId, registeredAt | At-least-once |
| ConsentChanged | 同意付与または撤回 | memberId, purpose, newStatus, changedAt | At-least-once（< 5分 SLA） |

**互換性規約**: フィールド追加のみ許可（後方互換）。schemaVersion フィールド必須。

**根拠**：`docs/service-list.md` §SVC-01「提供 I/F」

---

## 5. データ所有・モデル（概念）

| エンティティ | 所有者 | 説明 |
|------------|-------|------|
| Member | 本サービス（SVC-01） | 会員プロフィール。memberId (UUID) で識別 |
| ConsentRecord | 本サービス（SVC-01）/ APP-12（統制ログ） | 目的別同意記録。DEC-005 参照 |

**SoR**:
- `membership`（Member エンティティ）
- `consent`（ConsentRecord エンティティ）
- 共有: APP-12（SVC-15）も consent の統制・変更ログを保持（DEC-005）

**一意性ルール**:
- 1会員に対して同意記録は目的別に 1 つ
- memberId は発行後変更不可（UUID）
- メールアドレスは会員間で一意（TBD: 名寄せキー ブロッカー#3）

**PII分類**: Member エンティティに個人情報含む（氏名・メール・電話番号）。TBD: 具体的な PII 分類・法域要件は ブロッカー#1

**根拠**：`docs/domain-analytics.md` §エンティティ「Member」「ConsentRecord」、DEC-005

---

## 6. セキュリティ・権限

| 項目 | 内容 |
|------|------|
| **認証方式** | OIDC/SSO（外部 ID 基盤に委譲） |
| **認可方式** | RBAC（APP-12 SVC-15 が一元管理）。会員自身の情報更新はセルフサービス許可 |
| **監査** | 会員登録・同意変更・プロフィール更新は必ず監査ログ（SVC-16 へ非同期送信） |
| **暗号化** | TBD（転送: TLS 必須。保存: PII フィールドは暗号化推奨。KMS 方針 TBD） |

**根拠**：`docs/domain-analytics.md` §BC-01、`docs/app-list.md` §APP-01「キー NFR」

---

## 7. 外部依存・統合

| 依存先 | 契約 | 障害時フォールバック |
|-------|------|-----------------|
| 外部 ID 基盤/SSO | 認証連携（ACL: C 連携） | TBD: ID 基盤仕様は ASS-03 |
| CRM | 会員属性連携（連携方式 TBD） | TBD: CRM 機能確認後に確定（推論: Q29） |
| SVC-15（アクセス制御） | 同意変更 → 配信/AI 制御フラグ更新 | 同意変更 Event は At-least-once 保証 |
| SVC-16（監査ログ） | 操作ログ送信（非同期 Event） | ローカルバッファ後リトライ（TBD） |

**根拠**：`docs/service-list.md` §SVC-01「依存先/連携」

---

## 8. 状態遷移・ビジネスルール

**会員ステータス遷移**:

```
[*] --> PENDING: 登録リクエスト受信
PENDING --> ACTIVE: 確認完了
ACTIVE --> SUSPENDED: 同意全撤回 or 不正検知
SUSPENDED --> ACTIVE: 復活申請承認
ACTIVE --> CLOSED: 退会申請
SUSPENDED --> CLOSED: 強制退会
```

**同意変更ゲート**:
- CLOSED 会員への同意変更: 拒否（MCS-STATE-001）
- 同意撤回は即時反映（< 5 分で下流へ通知）

**根拠**：`docs/domain-analytics.md` §集約「MemberAggregate」

---

## 9. 非機能・SLO（概念）

| 指標 | 目安 |
|------|------|
| 可用性 | 99.9%（TBD: Q49 推論。バックエンド登録処理はリカバリ可能） |
| 読み取りレイテンシ | p95 < 500ms（TBD） |
| 書き込みレイテンシ | p95 < 1s（TBD） |
| ConsentChanged 遅延 | < 5分（下流への Event 配信） |

**可観測性**:
- メトリクス: 登録成功/失敗率、同意変更件数、ConsentChanged 遅延
- トレース: Trace Context 伝播（memberId でコリレーション）
- ログ: 構造化ログ（memberId, eventType, timestamp, actor）

---

## 10. バージョニング／互換性

| 項目 | 方針 |
|------|------|
| API 版付け | `/api/v1` プレフィックス |
| イベント版付け | `schemaVersion` フィールド必須（例: `"1.0"`） |
| 後方互換ルール | フィールド追加のみ許可。フィールド削除/型変更は新バージョン |

---

## 11. エラー・レート制御・再試行

**エラー体系**:
- `MCS-VAL-xxx`: 入力検証エラー（クライアント責任、再試行不要）
- `MCS-STATE-xxx`: 状態不正エラー（クライアント責任、再試行不要）
- `MCS-EXT-xxx`: 外部依存エラー（サーバ側、再試行対象）

**再試行の責務分界**:
- 外部 ID 基盤エラー: サーバ側でリトライ（指数バックオフ、TBD: 回数）
- CRM 連携エラー: 非同期リトライ + DLQ（TBD）

**冪等性**: `POST /members` は Idempotency-Key ヘッダーで重複防止。

---

## 12. 設定・フラグ

**機能フラグ候補**:
- `emailVerificationEnabled`: メール確認フロー有効化
- `crmSyncEnabled`: CRM 連携有効化（フェーズ移行用）

**構成キー候補**:
- `externalIdpBaseUrl`: 外部 ID 基盤 URL（環境別）
- `consentChangeEventDelayMaxMs`: ConsentChanged 最大遅延閾値

---

## 13. 移行・初期データ

TBD（現行システム台帳の有無・名寄せキー未確定: ブロッカー#3）。  
既存 ID 基盤との C 連携（ASS-03）が前提となるため、移行方式は ID 基盤仕様確定後に決定。

---

## 14. テスト指針（概念）

| 観点 | 方針 |
|------|------|
| 契約テスト | SVC-05/SVC-10 が Consumer として `/members/{id}` の Provider テストを保持 |
| 状態遷移テスト | Member ステータス遷移（PENDING→ACTIVE→CLOSED 等）の全パス検証 |
| 同意変更テスト | ConsentChanged Event の発行タイミング・ペイロード正確性検証 |
| 監査ログテスト | 登録・同意変更操作後に監査ログ Event が発行されることを検証 |

**根拠**：`docs/test-strategy.md`

---

## 15. 運用・リリース（概念）

| 項目 | 方針 |
|------|------|
| デプロイ戦略 | ローリングデプロイ（推論: Q66 デフォルト回答。非台帳系サービスのためローリングで十分） |
| DLQ 運用 | ConsentChanged 未配信 → DLQ → アラート通知 → 手動再投入 |
| リプレイ | TBD（同意記録の再処理は下流への影響大。要慎重設計） |

---

## 16. リスク・オープン課題

| No. | 課題 | 種別 | ブロッカー |
|----|------|------|---------|
| 1 | 同意要件（法域/目的別オプトイン粒度） | 仕様未確定 | ブロッカー#1 |
| 2 | 名寄せキー（メール/電話/会員番号の組合せ） | 仕様未確定 | ブロッカー#3 |
| 3 | 外部 ID 基盤仕様（SSO/OIDC 方式） | 外部依存 | ASS-03 |
| 4 | CRM 連携方式（API vs バッチ等） | 外部依存 | TBD |
| 5 | 会員データ保持期間（退会後の法令保持要件） | 法務 | TBD |
| 6 | PII 暗号化方式・KMS 設計 | セキュリティ | TBD |

---

## 17. 画面・操作・API・イベント マッピング

| 画面/操作 | API | イベント | 備考 |
|---------|-----|---------|------|
| 会員登録フォーム送信 | POST /members | MemberRegistered | 冪等ID付 |
| プロフィール更新 | PATCH /members/{id} | — | 監査ログ必須 |
| 同意付与 | POST /members/{id}/consents | ConsentChanged | < 5分で下流反映 |
| 同意撤回 | DELETE /members/{id}/consents/{purpose} | ConsentChanged | 即時下流通知 |
| BFF 経由会員照会 | GET /members/{id} | — | SVC-05/SVC-10 から参照 |

**根拠**：`docs/screen-list.md`（APP-01 対応画面）、`docs/service-catalog.md` §SVC-01

---

## 付録A：コード生成用の骨子

### OpenAPI 骨子（paths のみ）

```yaml
paths:
  /members:
    post:
      operationId: createMember
      headers: { Idempotency-Key: string }
      responses:
        "201": { schema: Member }
        "409": { schema: Error }  # 重複
  /members/{memberId}:
    get:
      responses:
        "200": { schema: Member }
        "404": { schema: Error }
    patch:
      responses:
        "200": { schema: Member }
  /members/{memberId}/consents:
    get:
      responses:
        "200": { schema: ConsentList }
    post:
      responses:
        "201": { schema: ConsentRecord }
  /members/{memberId}/consents/{purpose}:
    delete:
      responses:
        "204": {}
        "404": { schema: Error }
```

### エラーコード辞書

| コード | 意味 |
|-------|------|
| MCS-VAL-001 | 必須フィールド欠落 |
| MCS-VAL-002 | フォーマット不正 |
| MCS-STATE-001 | ステータス不正（例: CLOSED 会員） |
| MCS-EXT-001 | 外部 ID 基盤障害 |
| MCS-EXT-002 | CRM 連携エラー |

---

## 最終チェックリスト

- [x] 1〜12、14〜17 を埋めた（未確定は TBD ＋根拠）
- [x] OpenAPI/AsyncAPI は「骨子のみ」で詳細スキーマを書いていない
- [x] sample-data の値を転記していない
- [x] PII 分類は推測していない（TBD + ブロッカー#1 参照）
