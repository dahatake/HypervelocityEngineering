# UC × APP スライス（Part 1: UC-01〜UC-11）

> **目的**: 親 Step 6 (Arch-Microservice-ServiceCatalog) のサービススライス抽出のため、`docs/catalog/use-case-catalog.md` の前半（1〜430 行目目安）に該当する UC と、`docs/catalog/app-catalog.md` から導いた関連 APP-ID を N:N で整理する。
> **対象範囲**: `use-case-catalog.md` 行 61〜421（UC-01〜UC-11、計 11 件）。
> **根拠**: `docs/catalog/use-case-catalog.md` UC-01〜UC-11 各エントリ、`docs/catalog/app-catalog.md` §2（UC別実装手段）・§4（アプリ一覧）・§5（カバレッジ行列 R/S/N）。
> **APP-ID 判定方針**: app-catalog §5 の行を一次根拠とし、`R`=Primary、`S`=Secondary を関連 APP として採用。`N` は除外。判定不能時のみ `TBD` とし理由を記録（本スライスでは該当なし）。
> この回答はCopilot推論をしたものです。

## 0. サマリー

- 対象 UC: 11 件（UC-01〜UC-11）
- 優先度内訳: P0 = 8 件（UC-01, UC-03, UC-04, UC-05, UC-06, UC-08, UC-11, ※UC-09 は P1） / P1 = 3 件（UC-02, UC-07, UC-09, UC-10）→ 正味 P0=7、P1=4
- 出現する APP-ID（ユニーク）: APP-01, APP-02, APP-03, APP-04, APP-05, APP-06, APP-08, APP-09, APP-12（9 種）
- TBD 件数: 0（app-catalog §5 で全 UC×APP マッピングが確定済）

## 1. UC × APP-ID マッピング表（N:N、Primary/Secondary 区別あり）

| UC-ID | UC 名称 | 業務エリア | 提言 ID | 優先度 | UC 行（参照） | Primary APP（R） | Secondary APP（S） | 主要 SoR | 主な依存システム | TBD/根拠不足 |
|---|---|---|---|---|---|---|---|---|---|---|
| UC-01 | 会員として新規登録する（ソーシャル/ワンクリック含む） | 会員管理 | REC-04 / REC-01 | P0 | use-case-catalog.md:61-91 | APP-01 | APP-04, APP-12 | membership, consent | SNS IdP / メール・SMS GW / CDP / 同意管理基盤 / 不正検知 | なし |
| UC-02 | 既存顧客情報からワンクリックで会員化する | 会員管理 | REC-04 / REC-01 | P1 | use-case-catalog.md:94-122 | APP-01 | APP-04 | membership, analytics | 基幹顧客 DB / CDP / 同意管理基盤 / メール・SMS GW | なし |
| UC-03 | 会員プロファイルを参照・更新する | 会員管理 | REC-04 / REC-01 | P0 | use-case-catalog.md:126-154 | APP-01 | APP-04 | membership, consent | 認証基盤 / MFA / CDP / 同意管理基盤 | なし |
| UC-04 | 会員ランク・ポイント残高を即時確認する | 会員管理 / ロイヤルティ取引 | REC-04 | P0 | use-case-catalog.md:158-185 | APP-02 | （なし） | loyalty_ledger | ポイント・ランク台帳 / 認証基盤 / 通知基盤 | なし |
| UC-05 | 購買発生時にポイントを即時付与する | ロイヤルティ取引 | REC-01 / REC-04 | P0 | use-case-catalog.md:189-221 | APP-02 | APP-06, APP-12 | loyalty_ledger, transaction | POS / EC 決済 / 台帳 / 不正検知 / 通知基盤 | なし |
| UC-06 | 保有ポイントで特典・クーポンを引き換える | リワード・特典 / ロイヤルティ取引 | REC-02 / REC-04 | P0 | use-case-catalog.md:223-254 | APP-02 | APP-03 | loyalty_ledger, reward | リワードカタログ / クーポン基盤 / 決済 | なし |
| UC-07 | リワードカタログを閲覧・検索する | リワード・特典 | REC-02 / REC-01 | P1 | use-case-catalog.md:256-286 | APP-03 | APP-04, APP-05 | reward | レコメンド / CDP | なし |
| UC-08 | 有料プレミアム会員にアップグレード／継続課金する | リワード・特典 / ロイヤルティ取引 | REC-02 | P0 | use-case-catalog.md:288-320 | APP-03 | APP-01 | reward, membership | 決済 / サブスク / 会計 / 通知 | なし |
| UC-09 | 会員限定イベント・体験型リワードに申込する | リワード・特典 | REC-02 | P1 | use-case-catalog.md:322-353 | APP-03 | （なし） | reward, campaign | 抽選 / 通知 / 決済 | なし |
| UC-10 | 提携先ポイントと相互交換する | 提携・エコシステム | REC-05 | P1 | use-case-catalog.md:355-387 | APP-08 | APP-02, APP-12 | loyalty_ledger, identity_access | 提携先 API / 為替 / 不正検知 | なし |
| UC-11 | 統合顧客プロファイル（Single Customer View）を生成・維持する | 分析・KPI（基盤） | REC-01 | P0 | use-case-catalog.md:389-420 | APP-04 | APP-09 | analytics | 基幹各種 / MDM / 同意管理基盤 / DWH | なし |

> 表中の R/S 区分は `docs/catalog/app-catalog.md` §5 カバレッジ行列を一次根拠とする。

## 2. APP-ID 出現サマリー（前半 UC 範囲）

| APP-ID | アーキタイプ名 | Primary（R）として登場する UC | Secondary（S）として登場する UC | カバー数（合計） |
|---|---|---|---|---|
| APP-01 | 会員・同意管理 | UC-01, UC-02, UC-03 | UC-08 | 4 |
| APP-02 | ロイヤルティ台帳 | UC-04, UC-05, UC-06 | UC-10 | 4 |
| APP-03 | 特典・プレミアム管理 | UC-07, UC-08, UC-09 | UC-06 | 4 |
| APP-04 | CDP・特徴量基盤 | UC-11 | UC-01, UC-02, UC-03, UC-07 | 5 |
| APP-05 | AI 意思決定・生成ゲートウェイ | （なし） | UC-07 | 1 |
| APP-06 | MA・配信オーケストレーション | （なし） | UC-05 | 1 |
| APP-08 | 提携 API・エコシステムゲートウェイ | UC-10 | （なし） | 1 |
| APP-09 | 分析・BI・実験基盤 | （なし） | UC-11 | 1 |
| APP-12 | 不正検知・監査ログ基盤 | （なし） | UC-01, UC-05, UC-10 | 3 |

> `APP-07`（キャンペーン・承認管理）、`APP-10`（会員サポート AI）、`APP-11`（コミュニティ基盤）は前半範囲では登場せず、後半（Sub-003 等）で扱う。

## 3. 候補サービススライス（後続 Sub-task への申し送り）

| 候補スライス | 含む APP-ID（Primary） | 含む UC | 一次 SoR | 残課題（後半結果との突合要） |
|---|---|---|---|---|
| 会員・同意ドメイン | APP-01 | UC-01, UC-02, UC-03 | membership, consent | UC-25 と統合可否（後半 Sub で確認） |
| ロイヤルティ台帳ドメイン | APP-02 | UC-04, UC-05, UC-06 | loyalty_ledger, transaction | UC-24（不正検知）との境界（後半 Sub） |
| 特典・プレミアムドメイン | APP-03 | UC-07, UC-08, UC-09 | reward | UC-21（施策管理）との関係（後半 Sub） |
| CDP・データ統合ドメイン | APP-04 | UC-11 | analytics | UC-12〜UC-20 の Secondary 利用（後半 Sub） |
| 提携・エコシステムドメイン | APP-08 | UC-10 | identity_access | UC-22, UC-23 と統合可否（後半 Sub） |

## 4. TBD・根拠不足

- 該当なし。前半範囲（UC-01〜UC-11）は `app-catalog.md` §5 で R/S が完全に定義済のため、APP-ID マッピングに不確定項目は存在しない。
- ただし、UC 自体の未確定事項（例: UC-01 の不正検知サービス選定、UC-11 の CDP 方針 等）は元の `use-case-catalog.md` 各 UC の「未確定事項」セクションに残存しており、サービス境界確定時には参照すること。

## 5. 受け入れ条件チェック

- [x] `docs/catalog/use-case-catalog.md` の前半（1〜430 行目目安、実体は行 61〜421 の UC-01〜UC-11）から対応 UC 候補（11 件）を抽出
- [x] `docs/catalog/app-catalog.md` から関連 APP-ID 候補（9 種）を抽出
- [x] APP-ID を判定できない候補は `TBD` とし根拠不足の理由を記録（本範囲では該当 0 件のため §4 に「該当なし」と明記）

## 6. 参照ファイル

- `docs/catalog/use-case-catalog.md`（行 61〜421）
- `docs/catalog/app-catalog.md`（§2, §4, §5）
