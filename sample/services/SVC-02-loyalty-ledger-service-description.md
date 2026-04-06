# SVC-02 マイクロサービス定義書：ポイント台帳サービス

> **根拠**：`docs/service-list.md` §SVC-02、`docs/service-catalog.md` §SVC-02、`docs/domain-analytics.md` §BC-02、`docs/app-list.md` §APP-02  
> **作成日**：2026-03-31  
> **バージョン**：v1.1（2026-03-31 Copilot 推論デフォルト回答適用）

> ⚠️ **この回答はCopilot推論をしたものです。**  
> コメント #4160205953「デフォルトの回答で作成してください」に基づき、質問票（70問）のデフォルト回答を適用しました。  
> 推論補完箇所は `（推論: Q{番号} デフォルト回答）` と明記します。

---

## 1. サービスメタ情報

| 項目 | 内容 |
|------|------|
| **サービス名** | ポイント台帳サービス |
| **短縮名（英字）** | LoyaltyLedgerService（LLS） |
| **概要** | 購買取引に基づくポイント付与・消込・失効・残高計算・ランク計算を ACID 保証で処理する、ロイヤルティプログラムのコアサービス |
| **利用アプリケーション** | APP-02（主），APP-04（SVC-05 BFF 経由：残高/明細照会），APP-09（SVC-12：交換消込），APP-10（SVC-13：月次集計） |
| **BC** | BC-02（ロイヤルティ台帳・ルールエンジン） |
| **サブドメイン** | コアドメイン（差別化源泉） |
| **オーナー** | TBD |

**責務（Do）**:
- ポイント付与計算・台帳エントリ記録（PointLedgerEntry: Append-only）
- ポイント消込（特典交換時、引当→確定/ロールバック: 2フェーズ Saga）
- ポイント有効期限管理・失効バッチ実行
- 残高計算（balance = 台帳集計、マイナス残高不可）
- ランク計算・RankUpdated イベント発行（RankUpdateService）
- 不正取引検知（FraudDetectionService: MVP はルールベース）

**非責務（Don't）**:
- 付与ルール定義・版管理（SVC-03 の責務）
- 特典カタログ管理（SVC-04 の責務）
- 財務集計・breakage 算定（SVC-13 の責務）

**根拠**：`docs/service-list.md` §SVC-02、`docs/domain-analytics.md` §BC-02

---

## 2. ビジネス能力・コンテキスト

| 項目 | 内容 |
|------|------|
| **対象ドメイン** | ロイヤルティ台帳・ルールエンジン（BC-02） |
| **対応 UC** | UC-02（Primary: ポイント付与）、UC-07（Secondary: ルール評価）、UC-04（Secondary: 引当）、UC-14（Secondary: 集計提供） |
| **Capability** | CAP-02（ポイント台帳・付与ルール設計） |

**ライフサイクル（LoyaltyAccount）**:
```
ACTIVE: 通常状態（付与・消込・照会可能）
SUSPENDED: 一時停止（不正検知等）
CLOSED: 退会後（照会のみ。保持期間 TBD）
```

**ライフサイクル（RedemptionReservation: 引当）**:
```
RESERVED → CONFIRMED（確定消込）
RESERVED → CANCELLED（タイムアウト/ロールバック）
```

**根拠**：`docs/domain-analytics.md` §集約「LoyaltyLedgerAggregate」「RedemptionAggregate」

---

## 3. 公開インターフェース（同期）

**API スタイル**: REST/JSON/UTF-8

| リソース | 操作 | メソッド | パス |
|---------|------|---------|------|
| 残高 | 照会 | GET | /accounts/{memberId}/balance |
| 明細 | 照会 | GET | /accounts/{memberId}/entries |
| 付与 | ポイント付与 | POST | /accounts/{memberId}/awards |
| 引当 | 仮押さえ | POST | /accounts/{memberId}/reservations |
| 消込 | 確定消込 | POST | /accounts/{memberId}/redemptions |
| 引当取消 | ロールバック | DELETE | /accounts/{memberId}/reservations/{reservationId} |

**冪等性**: `POST /awards`、`POST /redemptions` は Idempotency-Key 使用。同一キーは 200 で既存結果を返す。

**エラー語彙**:
- LLS-VAL-001: 入力検証エラー
- LLS-BALANCE-001: 残高不足
- LLS-STATE-001: アカウント状態不正
- LLS-FRAUD-001: 不正取引検知
- LLS-EXT-001: 外部依存エラー

**根拠**：`docs/service-catalog.md` §SVC-02「提供 I/F」

---

## 4. 公開インターフェース（非同期）

**AsyncAPI 骨子**:

```yaml
channels:
  lls.points.awarded:
    publish:
      message: { name: PointsAwarded, key: memberId }
      # 購読: 通知基盤, APP-04（SVC-05）, APP-12（SVC-16）
  lls.rank.updated:
    publish:
      message: { name: RankUpdated, key: memberId }
      # 購読: APP-04（SVC-05）, 通知基盤, APP-12（SVC-16）
  lls.points.redeemed:
    publish:
      message: { name: PointsRedeemed, key: memberId }
      # 購読: APP-04（SVC-05）, SVC-13, APP-12（SVC-16）
  lls.points.expired:
    publish:
      message: { name: PointsExpired, key: memberId }
      # 購読: APP-04（SVC-05）, SVC-13, APP-12（SVC-16）
  pos.purchase.completed:
    subscribe:
      message: { name: PurchaseCompleted, key: transactionId }
      # 発行元: POS/EC（外部）
```

| イベント名 | 発火条件 | 最小ペイロード | 配信保証 |
|-----------|---------|------------|---------|
| PointsAwarded | 付与計算完了 | memberId, amount, transactionId, expiryDate | At-least-once |
| RankUpdated | ランク変更確定 | memberId, oldRank, newRank | At-least-once |
| PointsRedeemed | 消込確定 | memberId, amount, redemptionId | At-least-once |
| PointsExpired | 失効バッチ完了 | memberId, expiredAmount, expiredAt | At-least-once |

**根拠**：`docs/service-catalog.md` §SVC-02「提供 I/F」

---

## 5. データ所有・モデル（概念）

| エンティティ | 所有者 | 説明 |
|------------|-------|------|
| LoyaltyAccount | 本サービス | 会員ごとの残高・ランク集約ルート |
| PointLedgerEntry | 本サービス | 付与/消込/失効の Append-only 記録 |

**SoR**:
- `loyalty_ledger`（LoyaltyAccount, PointLedgerEntry）
- `transaction`（購買取引受信・付与/消込記録）

**一意性ルール**:
- LoyaltyAccount は memberId と 1:1
- balance ≥ 0（マイナス残高不可）
- 台帳エントリは Append-only（変更・削除不可）

**PII分類**: memberId を含むが個人情報は SVC-01 が SoR。ポイント台帳自体は PII 直接保持なし。TBD: エントリの保持期間

**根拠**：`docs/domain-analytics.md` §エンティティ「LoyaltyAccount」「PointLedgerEntry」

---

## 6. セキュリティ・権限

| 項目 | 内容 |
|------|------|
| **認証方式** | OIDC（SVC-05 BFF 経由）または サービス間 mTLS/Managed Identity |
| **認可方式** | RBAC（APP-12 SVC-15）。会員自身の残高照会はセルフサービス許可。付与操作はシステム権限のみ |
| **監査** | 付与・消込・失効・不正検知はすべて SVC-16 へ非同期監査ログ送信 |

**根拠**：`docs/domain-analytics.md` §BC-02

---

## 7. 外部依存・統合

| 依存先 | 契約 | 障害時フォールバック |
|-------|------|-----------------|
| POS/EC（外部） | 購買取引イベント受信（ACL） | At-least-once 保証。重複は冪等ID で排除 |
| SVC-03 | 付与計算時に有効ルール取得（REST, < 100ms） | キャッシュ利用（TBD: TTL） |
| SVC-04 | ポイント引当リクエスト受領（REST 2フェーズ Saga） | タイムアウト時はロールバック |
| SVC-12 | パートナー交換消込リクエスト（REST/冪等） | 冪等再試行 |
| SVC-13 | 月次集計データ提供（Batch API） | Batch リトライ |
| SVC-16 | 監査ログ送信（非同期 Event） | ローカルバッファ後リトライ |

**根拠**：`docs/service-catalog.md` §SVC-02「依存先/連携」

---

## 8. 状態遷移・ビジネスルール

**Redemption（引当→消込）フロー**:

```
[*] --> RESERVED: POST /reservations（ポイント仮押さえ）
RESERVED --> CONFIRMED: POST /redemptions（確定消込）
RESERVED --> CANCELLED: DELETE /reservations/{id} または タイムアウト
```

**ビジネスルール**:
- balance ≥ 0 を常に保証（原子的チェック&デクリメント）
- 有効期限切れポイントは失効バッチで Expire エントリ追記
- ランク再計算は台帳集計完了後に RankUpdateService が実行

**根拠**：`docs/domain-analytics.md` §集約「LoyaltyLedgerAggregate」「RedemptionAggregate」

---

## 9. 非機能・SLO（概念）

| 指標 | 目安 |
|------|------|
| 可用性 | 99.95%（コアドメイン。TBD） |
| 残高照会レイテンシ | p95 < 200ms（TBD） |
| 付与処理レイテンシ | p95 < 500ms（TBD） |
| 失効バッチ完了 | 月次締め前完了（TBD: 締め時刻） |

**可観測性**:
- メトリクス: 付与/消込/失効件数、残高照会レイテンシ、不正検知件数、DLQ 件数
- トレース: Trace Context（transactionId でコリレーション）
- ログ: 構造化ログ（memberId, entryType, amount, transactionId）

---

## 10. バージョニング／互換性

| 項目 | 方針 |
|------|------|
| API 版付け | `/api/v1` |
| イベント版付け | `schemaVersion` 必須 |
| 後方互換 | フィールド追加のみ。LedgerEntry は不変 |

---

## 11. エラー・レート制御・再試行

**エラー体系**:
- `LLS-VAL-xxx`: 入力検証（クライアント責任）
- `LLS-BALANCE-xxx`: 残高不足（クライアント責任）
- `LLS-FRAUD-xxx`: 不正検知（調査要）
- `LLS-EXT-xxx`: 外部依存エラー（サーバ側リトライ）

**冪等性**: 全書き込み操作は Idempotency-Key 必須。

---

## 12. 設定・フラグ

**機能フラグ候補**:
- `fraudDetectionEnabled`: 不正検知有効化（MVP はルールベース）
- `mlFraudDetectionEnabled`: ML ベース不正検知（P1 以降）

**構成キー候補**:
- `awardRuleCacheTtlMs`: 付与ルールキャッシュ TTL
- `reservationTimeoutMs`: 引当タイムアウト時間
- `expiryBatchSchedule`: 失効バッチスケジュール（Cron）

---

## 13. 移行・初期データ

TBD（現行ポイント残高の移行有無・旧台帳データの取り込み方式は現行システム台帳確認後に決定）。

---

## 14. テスト指針（概念）

| 観点 | 方針 |
|------|------|
| 契約テスト | SVC-04（Consumer: 引当 API）、SVC-12（Consumer: 消込 API）が Provider テストを保持 |
| 残高整合テスト | balance ≥ 0 の不変条件を並行アクセス条件下で検証 |
| Saga テスト | 引当→確定/ロールバックの全パスを検証 |
| 失効バッチテスト | 有効期限切れポイントの正確な失効処理検証 |

**根拠**：`docs/test-strategy.md`

---

## 15. 運用・リリース（概念）

| 項目 | 方針 |
|------|------|
| デプロイ戦略 | **Blue/Green デプロイ**（台帳整合性を最優先: 推論: Q66 デフォルト回答。ローリング中の二重書き込みリスクを避けるため） |
| DLQ 運用 | 未処理 PurchaseCompleted → DLQ → **アラート → 手動再投入**（推論: Q65 デフォルト回答） |
| リプレイ | PointLedgerEntry（Append-only）から残高再計算可能 |

---

## 16. リスク・オープン課題

| No. | 課題 | 種別 | ブロッカー |
|----|------|------|---------|
| 1 | POS/EC イベント粒度（確定/取消の定義） | 仕様未確定 | ブロッカー#2 |
| 2 | ランク閾値・更新タイミング定義 | 仕様未確定 | ブロッカー#4 |
| 3 | 台帳データ保持期間 | 法務 | TBD |
| 4 | ML ベース不正検知の精度・閾値 | AI 仕様 | P1 以降 |

---

## 17. 画面・操作・API・イベント マッピング

| 画面/操作 | API | イベント | 備考 |
|---------|-----|---------|------|
| 残高・ランク確認（APP-04） | GET /accounts/{id}/balance | — | SVC-05 BFF 経由 |
| 明細照会（APP-04） | GET /accounts/{id}/entries | — | SVC-05 BFF 経由 |
| 購買完了（POS/EC） | POST /accounts/{id}/awards | PointsAwarded | 冪等ID付 |
| 特典交換引当（SVC-04） | POST /accounts/{id}/reservations | — | Saga Phase 1 |
| 特典交換確定（SVC-04） | POST /accounts/{id}/redemptions | PointsRedeemed | Saga Phase 2 |
| 月次失効バッチ | — | PointsExpired | スケジュール実行 |

**根拠**：`docs/service-catalog.md` §SVC-02、`docs/screen-list.md`

---

## 付録A：コード生成用の骨子

### OpenAPI 骨子（paths のみ）

```yaml
paths:
  /accounts/{memberId}/balance:
    get:
      responses:
        "200": { schema: Balance }
  /accounts/{memberId}/entries:
    get:
      parameters: [fromDate, toDate, type]
      responses:
        "200": { schema: LedgerEntryList }
  /accounts/{memberId}/awards:
    post:
      headers: { Idempotency-Key: string }
      responses:
        "201": { schema: LedgerEntry }
        "409": { schema: Error }
  /accounts/{memberId}/reservations:
    post:
      headers: { Idempotency-Key: string }
      responses:
        "201": { schema: Reservation }
        "422": { schema: Error }  # 残高不足
  /accounts/{memberId}/reservations/{reservationId}:
    delete:
      responses:
        "204": {}
  /accounts/{memberId}/redemptions:
    post:
      headers: { Idempotency-Key: string }
      responses:
        "201": { schema: LedgerEntry }
```

---

## 最終チェックリスト

- [x] 1〜12、14〜17 を埋めた（未確定は TBD ＋根拠）
- [x] OpenAPI/AsyncAPI は「骨子のみ」で詳細スキーマを書いていない
- [x] sample-data の値を転記していない
- [x] PII 分類は推測していない（TBD + ブロッカー参照）
